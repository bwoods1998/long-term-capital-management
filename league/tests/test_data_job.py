"""Collector supervision: no duplicate daemon and no signal to an unrelated PID."""
import fcntl
import json
import os
from pathlib import Path
import signal
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from league.data_job import NightlySupervisor, lock_held
from league.swarm.cleanup import StoppedPoolCleanup


class Supervisor(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.root = base / 'state'
        self.data = self.root / 'data'
        self.data.mkdir(parents=True)
        self.release = base / 'release'
        script = self.release / 'scripts' / 'data' / 'nightly.py'
        script.parent.mkdir(parents=True)
        script.write_text('# test collector\n')
        self.now = 1000.0
        self.procs = {}
        self.children = []
        self.signals = []
        self.lock = None
        self.addCleanup(self.unlock)
        self.enable()

    def enable(self, value=True):
        (self.root / 'data-nightly.json').write_text(json.dumps({'enabled': value}))

    def argv(self, release=None, state=None):
        return ['/usr/bin/python3', '-u', str((release or self.release) / 'scripts' / 'data' / 'nightly.py'),
                'daemon', '--state', str(state or self.data), '--ready-file', str(self.root / 'gym-forward.json')]

    def spawn(self):
        pid = 900001 + len(self.children)
        child = SimpleNamespace(pid=pid, returncode=None)
        child.poll = lambda: child.returncode
        self.children.append(child)
        self.procs[pid] = (self.argv(), str(pid * 2))
        return child

    def step(self):
        return NightlySupervisor(self.root, code_dir=self.release, clock=lambda: self.now,
                                 spawn=self.spawn, kill=lambda p, s: self.signals.append((p, s)),
                                 proc=self.procs.get)

    def hold(self, pid=900050, release=None, age=0, busy=False):
        self.unlock()
        release = release or self.release
        self.procs[pid] = (self.argv(release=release), str(pid * 2))
        row = {'pid': pid, 'start': str(pid * 2), 'release': str(release)}
        path = self.data / 'nightly.lock'
        self.lock = path.open('a+')
        fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        path.write_text(json.dumps(row))
        (self.data / 'nightly.heartbeat').write_text(json.dumps(dict(row, at=self.now-age, state='waiting', busy=busy)))
        return row

    def unlock(self):
        if self.lock is not None:
            self.lock.close()
            self.lock = None

    def test_disabled_by_default_and_truthy_strings_do_not_enable(self):
        (self.root / 'data-nightly.json').unlink()
        step = self.step()
        self.assertEqual(step.tick()['idle'], 'disabled')
        self.enable('true')
        self.assertFalse(step.tick()['enabled'])
        self.assertEqual(self.children, [])

    def test_live_child_without_heartbeat_or_lock_is_not_duplicated(self):
        step = self.step()
        self.assertEqual(step.tick()['action'], 'started')
        for _ in range(3):
            self.now += 20
            step.tick()
        self.assertEqual(len(self.children), 1)
        self.assertEqual(self.signals, [])

    def test_new_house_adopts_healthy_locked_daemon(self):
        self.hold()
        out = self.step().tick()
        self.assertTrue(out['running'])
        self.assertEqual(out['heartbeat_age'], 0)
        self.assertEqual(self.children, [])
        self.assertEqual(self.signals, [])

    def test_occupied_unreadable_identity_never_spawns_or_signals(self):
        self.hold()
        (self.data / 'nightly.lock').write_text('{')
        out = self.step().tick()
        self.assertTrue(out['running'])
        self.assertEqual(self.children, [])
        self.assertEqual(self.signals, [])

    def test_recycled_pid_and_other_state_never_signalled(self):
        row = self.hold(age=500)
        self.procs[row['pid']] = (self.argv(), 'different-start')
        self.step().tick()
        self.procs[row['pid']] = (self.argv(state=self.root / 'other'), row['start'])
        self.enable(False)
        self.step().tick()
        self.assertEqual(self.signals, [])
        self.assertEqual(self.children, [])

    def test_startup_grace_ignores_old_heartbeat(self):
        self.hold()
        (self.data / 'nightly.heartbeat').write_text(json.dumps({'pid': 1, 'at': 1}))
        step = self.step()
        step.tick()
        self.now += 89
        step.tick()
        self.assertEqual(self.signals, [])
        self.now += 2
        step.tick()
        self.assertEqual(self.signals, [(900050, signal.SIGTERM)])

    def test_stale_worker_gets_term_then_verified_kill(self):
        self.hold(age=301)
        step = self.step()
        step.tick()
        self.assertEqual(self.signals, [(900050, signal.SIGTERM)])
        self.now += 121
        step.tick()
        self.assertEqual(self.signals[-1], (900050, signal.SIGKILL))
        self.procs[900050] = (['unrelated-program'], 'reused')
        self.now += 121
        step.tick()
        self.assertEqual(len(self.signals), 2)

    def test_release_change_waits_for_work_then_restarts(self):
        old = self.release.parent / 'old-release'
        self.hold(release=old, busy=True)
        step = self.step()
        self.assertIn('waiting for current data job', step.tick()['action'])
        self.assertEqual(self.signals, [])
        self.hold(release=old, busy=False)
        self.assertIn('another release', step.tick()['action'])
        self.assertEqual(self.signals, [(900050, signal.SIGTERM)])

    def test_disabled_and_stop_files_stop_existing_daemon(self):
        self.hold()
        self.enable(False)
        self.assertEqual(self.step().tick()['idle'], 'disabled')
        self.assertEqual(self.signals[-1], (900050, signal.SIGTERM))
        self.enable()
        (self.data / 'nightly.stop').touch()
        self.assertEqual(self.step().tick()['idle'], 'nightly.stop is set')

    def test_pause_prevents_start_but_does_not_kill_healthy_collector(self):
        step = self.step()
        self.assertIn('not open', step.tick(may_start=False)['idle'])
        self.hold()
        self.assertTrue(step.tick(may_start=False)['running'])
        self.assertEqual(self.signals, [])

    def test_rapid_failure_backs_off(self):
        step = self.step()
        step.tick()
        child = self.children[-1]
        child.returncode = 1
        del self.procs[child.pid]
        self.now += 10
        self.assertEqual(step.tick()['action'], 'start backoff')
        self.assertEqual(len(self.children), 1)

    def test_spawn_inherits_required_house_clients_not_other_credentials(self):
        step = NightlySupervisor(self.root, code_dir=self.release)
        with patch.dict(os.environ, {'SAIL_API_KEY': 'test-sail', 'GATEWAY_TOKEN': 'test-gateway',
                                     'CAPITAL_PUBLISH_TOKEN': 'test-publish', 'UNRELATED_SECRET': 'test-secret'}), \
                patch('league.data_job.subprocess.Popen') as popen:
            step._popen()
        args, kw = popen.call_args
        self.assertIn(str(self.data), args[0])
        self.assertEqual(kw['env']['SAIL_API_KEY'], 'test-sail')
        self.assertEqual(kw['env']['GATEWAY_TOKEN'], 'test-gateway')
        self.assertFalse({'CAPITAL_PUBLISH_TOKEN', 'UNRELATED_SECRET'} & kw['env'].keys())
        self.assertTrue(kw['start_new_session'])

    def test_hook_can_supervise_data_when_swarm_disabled(self):
        from league.swarm.hook import attach
        house = SimpleNamespace()
        self.assertIsNotNone(attach(house, self.root, {'swarm': {'enabled': False}}))

    def test_lock_lifecycle(self):
        self.assertFalse(lock_held(self.data / 'nightly.lock'))
        self.hold()
        self.assertTrue(lock_held(self.data / 'nightly.lock'))
        self.unlock()
        self.assertFalse(lock_held(self.data / 'nightly.lock'))


class PoolCleanup(unittest.TestCase):
    def test_slow_cleanup_runs_once_off_thread_and_only_while_stopped(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'swarm.sqlite').touch()
            started, finish = threading.Event(), threading.Event()
            calls = []
            def work():
                calls.append(1)
                started.set()
                finish.wait(5)
                return {'confirmed': 1}
            now = [100.0]
            cleaner = StoppedPoolCleanup(root, clock=lambda: now[0], work=work)
            cleaner.tick(stopped=False)
            self.assertEqual(calls, [])
            try:
                self.assertTrue(cleaner.tick(stopped=True)['running'])
                self.assertTrue(started.wait(2))
                now[0] += 65
                for _ in range(10):
                    self.assertTrue(cleaner.tick(stopped=True)['running'])
                self.assertEqual(calls, [1])
            finally:
                finish.set()
                if cleaner.worker:
                    cleaner.worker.join(5)
            self.assertEqual(cleaner.tick(stopped=False)['confirmed'], 1)

    def test_inventory_failure_is_visible_and_retried_with_backoff(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'swarm.sqlite').touch()
            calls = []
            def work():
                calls.append(1)
                raise RuntimeError('inventory unavailable')
            now = [100.0]
            cleaner = StoppedPoolCleanup(root, clock=lambda: now[0], work=work)
            cleaner.tick(stopped=True)
            cleaner.worker.join(5)
            self.assertIn('inventory unavailable', cleaner.tick(stopped=True)['errors'][0])
            self.assertEqual(len(calls), 1)
            now[0] += 60
            cleaner.tick(stopped=True)
            cleaner.worker.join(5)
            self.assertEqual(len(calls), 2)
