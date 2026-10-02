"""Observer process ownership and recovery, without starting paid work or signaling host processes."""
import fcntl
import json
import os
import signal
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from league.swarm.harness_runtime import HarnessSupervisor, read_json, write_json
from league.watchdog import tree_digest
from scripts import harness_improve


class Runtime(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.state = self.base / 'state'
        self.code = self.base / 'release'
        self.code.mkdir()
        (self.code / 'source.py').write_text('immutable = True\n')
        self.now = 1000.0
        self.processes, self.spawned, self.signals = {}, [], []
        self.fds, self.closed = {}, []
        self.supervisor = self.make()

    def make(self):
        return HarnessSupervisor(self.state, code_dir=self.code, clock=lambda: self.now,
            python='/usr/bin/python3', spawn=self.spawn, proc=self.processes.get,
            pidfd_open=self.open_pidfd, pidfd_signal=self.signal_pidfd, close_fd=self.closed.append)

    def open_pidfd(self, pid, flags):
        if pid not in self.processes:
            raise ProcessLookupError
        fd = len(self.fds) + 10
        self.fds[fd] = (pid, self.processes[pid][1])
        return fd

    def signal_pidfd(self, fd, sig, info, flags):
        pid, start = self.fds[fd]
        if pid not in self.processes or self.processes[pid][1] != start:
            raise ProcessLookupError
        self.signals.append((pid, sig))

    def enable(self, **changes):
        directory = self.state / 'harness'
        directory.mkdir(parents=True, exist_ok=True)
        value = {'schema': 1, 'enabled': True, 'mode': 'observe', 'base': 'a' * 40,
                 'release_digest': tree_digest(self.code)[0], **changes}
        write_json(directory / 'runtime.json', value)
        return value

    def spawn(self, argv, **kwargs):
        pid = 900000 + len(self.spawned)
        self.spawned.append((argv, kwargs))
        self.processes[pid] = (argv, str(pid + 99))
        return SimpleNamespace(pid=pid, poll=lambda: None,
            terminate=lambda: self.signals.append((pid, signal.SIGTERM)))

    def heartbeat(self, *, at=None, pid=None, **extra):
        record = read_json(self.state / 'harness/runtime-process.json')
        pulse = {key: record[key] for key in ('pid', 'start', 'release', 'base', 'release_digest', 'policy')}
        write_json(self.state / 'harness/observer-heartbeat.json', {**pulse,
            'at': self.now if at is None else at, 'session_started_at': record['launched_at'],
            'pid': record['pid'] if pid is None else pid, **extra})

    def test_absent_policy_does_not_start_or_create_state(self):
        self.assertEqual(self.supervisor.tick(), {'enabled': False, 'running': False})
        self.assertFalse(self.state.exists())
        self.assertFalse(self.spawned)

    def test_explicit_policy_starts_only_observer_and_survives_house_restart(self):
        self.enable()
        first = self.supervisor.tick()
        self.assertTrue(first['started'])
        argv, kwargs = self.spawned[0]
        self.assertIn('watch', argv)
        self.assertNotIn('evaluate', argv)
        self.assertNotIn('deploy', argv)
        self.assertTrue(kwargs['start_new_session'])
        self.now += 60
        self.heartbeat()
        self.assertTrue(self.make().tick()['running'])
        self.assertEqual(len(self.spawned), 1)
        self.assertFalse(self.signals)

    def test_crash_backoff_then_restart_uses_persistent_record(self):
        self.enable()
        first = self.supervisor.tick()
        del self.processes[first['pid']]
        self.now += 10
        self.assertIn('backoff', self.make().tick()['waiting'])
        self.now += 51
        self.assertTrue(self.make().tick()['started'])
        self.assertEqual(len(self.spawned), 2)

    def test_stale_observer_is_terminated_then_killed_before_replacement(self):
        self.enable()
        first = self.supervisor.tick()
        self.now += 181
        self.assertTrue(self.make().tick()['stopping'])
        self.assertEqual(self.signals[-1], (first['pid'], signal.SIGTERM))
        self.now += 16
        self.assertTrue(self.make().tick()['stopping'])
        self.assertEqual(self.signals[-1], (first['pid'], signal.SIGKILL))
        del self.processes[first['pid']]
        self.assertTrue(self.make().tick()['started'])

    def test_reused_pid_is_never_signaled(self):
        self.enable()
        first = self.supervisor.tick()
        old_argv, old_start = self.processes[first['pid']]
        self.processes[first['pid']] = (old_argv, old_start + '-different-process')
        self.now += 200
        self.assertTrue(self.make().tick()['started'])
        self.assertFalse(self.signals)

    def test_wrong_root_or_foreign_command_is_never_signaled(self):
        self.enable()
        first = self.supervisor.tick()
        argv, start = self.processes[first['pid']]
        self.processes[first['pid']] = (['/usr/bin/sleep', '600'], start)
        self.now += 200
        self.assertTrue(self.make().tick()['started'])
        self.assertFalse(self.signals)

    def test_different_release_needs_a_reviewed_new_base(self):
        self.enable()
        first = self.supervisor.tick()
        (self.code / 'source.py').write_text('immutable = False\n')
        self.now += 1
        result = self.make().tick()
        self.assertTrue(result['stopping'])
        self.assertIn('reviewed base', result['reason'])
        self.assertEqual(self.signals[-1], (first['pid'], signal.SIGTERM))

    def deployed(self, *, sha='b' * 40, digest=None, attested=True, promoted=True, state='passed', release=None):
        """The watchdog's rows for one deploy of the running release (`league/watchdog.py` `_deploy`)."""
        release = release or self.code.name
        digest = digest or tree_digest(self.code)[0]
        key = f'{release}@{int(self.now)}'
        rows = [{'deploy': key, 'release': release, 'stage': 'start',
                 **({'sha': sha, 'attestation': {'sha': sha, 'ok': state == 'passed', 'state': state, 'tree_digest': digest}} if attested else {})},
                {'deploy': key, 'release': release, 'stage': 'canary', 'ok': True}]
        if promoted:
            rows.append({'deploy': key, 'release': release, 'stage': 'promote', 'ok': True, 'at': '2026-10-03T21:00:00.000Z'})
        with (self.base / 'deploys.jsonl').open('a') as log:
            for row in rows:
                log.write(json.dumps(row) + '\n')

    def test_an_updater_release_is_followed_by_its_attested_commit(self):
        """V3-A: an updater release no longer stops the observer until the operator re-points the policy."""
        policy = self.enable()
        first = self.supervisor.tick()
        self.assertEqual(self.spawned[0][0][self.spawned[0][0].index('--base') + 1], 'a' * 40)
        (self.code / 'source.py').write_text('immutable = "the next release"\n')
        self.deployed()
        self.now += 1
        self.assertTrue(self.make().tick()['stopping'])  # the old base's observer goes
        self.assertEqual(self.signals[-1], (first['pid'], signal.SIGTERM))
        del self.processes[first['pid']]
        self.now += 61
        result = self.make().tick()
        self.assertTrue(result['started'])
        argv = self.spawned[-1][0]
        self.assertEqual(argv[argv.index('--base') + 1], 'b' * 40)
        self.assertEqual(argv[argv.index('--release-digest') + 1], tree_digest(self.code)[0])
        self.assertEqual(read_json(self.state / 'harness/runtime.json'), policy)  # the operator's file is never rewritten
        self.now += 60
        self.heartbeat()
        self.assertTrue(self.make().tick()['running'])

    def test_only_a_promoted_attested_deploy_of_this_very_tree_is_followed(self):
        self.enable()
        (self.code / 'source.py').write_text('immutable = "the next release"\n')
        for changes in ({'attested': False}, {'promoted': False}, {'digest': '0' * 64}, {'state': 'pending'}, {'sha': 'main'},
                        {'release': 'another-release'}):
            (self.base / 'deploys.jsonl').unlink(missing_ok=True)
            self.deployed(**changes)
            self.now += 1
            self.assertIn('reviewed base', self.make().tick()['error'], changes)
        self.assertFalse(self.spawned)

    def test_stop_and_explicit_disable_preserve_journal(self):
        self.enable()
        first = self.supervisor.tick()
        journal = self.state / 'harness/harness.sqlite'
        journal.write_bytes(b'keep evidence')
        (self.state / 'STOP').write_text('operator stop')
        self.assertTrue(self.make().tick()['stopping'])
        del self.processes[first['pid']]
        self.assertFalse(self.make().tick()['running'])
        (self.state / 'STOP').unlink()
        self.enable(enabled=False)
        self.assertFalse(self.make().tick()['running'])
        self.assertEqual(journal.read_bytes(), b'keep evidence')

    def test_unknown_mode_invalid_commit_and_wrong_digest_do_not_start(self):
        for changes in ({'mode': 'author-and-deploy'}, {'base': 'main'}, {'release_digest': '0' * 64}):
            self.enable(**changes)
            self.assertIsNotNone(self.make().tick()['error'])
        self.assertFalse(self.spawned)

    def test_foreign_heartbeat_cannot_keep_a_hung_observer_alive(self):
        self.enable()
        first = self.supervisor.tick()
        self.now += 200
        self.heartbeat(pid=first['pid'] + 1)
        self.assertTrue(self.make().tick()['stopping'])

    def test_clock_regression_does_not_strand_a_crashed_observer(self):
        self.enable()
        first = self.supervisor.tick()
        del self.processes[first['pid']]
        self.now -= 100
        self.assertTrue(self.make().tick()['started'])

    def test_lost_process_record_is_recovered_from_verified_heartbeat(self):
        self.enable()
        first = self.supervisor.tick()
        self.heartbeat()
        (self.state / 'harness/runtime-process.json').unlink()
        result = self.make().tick()
        self.assertEqual(result['pid'], first['pid'])
        self.assertEqual(len(self.spawned), 1)
        self.assertEqual(read_json(self.state / 'harness/runtime-process.json')['base'], 'a' * 40)

    def test_child_lock_covers_process_record_write_failure_and_missing_first_heartbeat(self):
        self.enable()
        original_spawn = self.supervisor.spawn
        def spawning(argv, **kwargs):
            child = original_spawn(argv, **kwargs)
            lock = (self.state / 'harness/watch.lock').open('a')
            self.addCleanup(lock.close)
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return child
        self.supervisor.spawn = spawning
        with patch('league.swarm.harness_runtime.write_json', side_effect=OSError('disk unavailable')):
            with self.assertRaisesRegex(OSError, 'disk unavailable'):
                self.supervisor.tick()
        result = self.make().tick()
        self.assertIn('verified heartbeat', result['waiting'])
        self.assertTrue(result['observer_present'])
        self.assertEqual(len(self.spawned), 1)
        self.assertFalse(self.signals)

    def test_recovery_does_not_stamp_a_new_policy_on_an_old_observer(self):
        self.enable()
        first = self.supervisor.tick()
        self.heartbeat()
        old = read_json(self.state / 'harness/runtime-process.json')
        (self.state / 'harness/runtime-process.json').unlink()
        self.enable(base='b' * 40)
        result = self.make().tick()
        self.assertTrue(result['stopping'])
        self.assertEqual(self.signals[-1], (first['pid'], signal.SIGTERM))
        saved = read_json(self.state / 'harness/runtime-process.json')
        self.assertEqual(saved['base'], old['base'])
        self.assertEqual(saved['policy'], old['policy'])

    def test_heartbeat_with_wrong_start_or_base_does_not_recover_foreign_process(self):
        for field in ('start', 'base'):
            with self.subTest(field=field):
                self.enable()
                self.supervisor.tick()
                self.heartbeat(**{field: 'foreign'})
                (self.state / 'harness/runtime-process.json').unlink()
                self.now += 200
                self.assertTrue(self.make().tick()['started'])
                self.assertFalse(self.signals)

    def test_capture_error_and_lock_wait_remain_visible_without_restarting_a_responsive_observer(self):
        self.enable()
        self.supervisor.tick()
        for extra in ({'error': 'journal unavailable'}, {'waiting': 'another harness transition holds controller.lock'}):
            self.now += 600
            self.heartbeat(**extra)
            result = self.make().tick()
            self.assertTrue(result['running'])
            for key, value in extra.items():
                self.assertEqual(result[key], value)
        self.assertFalse(self.signals)
        self.assertEqual(len(self.spawned), 1)

    def test_pid_reuse_after_identity_check_cannot_redirect_a_signal(self):
        self.enable()
        first = self.supervisor.tick()
        record = read_json(self.state / 'harness/runtime-process.json')
        owns = self.supervisor._owns
        def reuse_after_check(value):
            result = owns(value)
            argv, start = self.processes[first['pid']]
            self.processes[first['pid']] = (argv, start + '-replacement')
            return result
        with patch.object(self.supervisor, '_owns', side_effect=reuse_after_check):
            self.assertFalse(self.supervisor._signal(record, signal.SIGTERM))
        self.assertFalse(self.signals)
        self.assertEqual(self.closed, list(self.fds))


class ObserverCLI(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.release = self.root / 'release'
        self.release.mkdir()
        (self.release / 'source.py').write_text('immutable = True\n')
        self.argv = ['harness_improve.py', '--root', str(self.root), 'watch', '--swarm', str(self.root / 'swarm'),
                     '--base', 'a' * 40, '--deploy-base', str(self.root), '--release', str(self.release)]

    def test_watch_keeps_heartbeating_when_evaluation_holds_the_transition_lock(self):
        with (self.root / 'controller.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with patch('sys.argv', self.argv), patch.object(harness_improve, 'HarnessImprovement') as lab, \
                    patch.object(harness_improve.time, 'sleep', side_effect=KeyboardInterrupt):
                self.assertEqual(harness_improve.main(), 0)
                lab.assert_not_called()
        pulse = read_json(self.root / 'observer-heartbeat.json')
        self.assertIn('controller.lock', pulse['waiting'])
        self.assertEqual(pulse['pid'], os.getpid())
        self.assertEqual(pulse['base'], 'a' * 40)
        self.assertTrue(pulse['start'])

    def test_a_second_watcher_cannot_scan_or_overwrite_the_first_heartbeat(self):
        write_json(self.root / 'observer-heartbeat.json', {'pid': 123, 'at': 100})
        with (self.root / 'watch.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with patch('sys.argv', self.argv), patch.object(harness_improve, 'transition') as transition:
                self.assertEqual(harness_improve.main(), 1)
                transition.assert_not_called()
        self.assertEqual(read_json(self.root / 'observer-heartbeat.json'), {'pid': 123, 'at': 100})

    def test_capture_is_bound_to_reviewed_release_instead_of_following_a_new_heartbeat(self):
        args = harness_improve.parser().parse_args(self.argv[1:])
        with patch.object(harness_improve, 'HarnessImprovement') as factory:
            lab = factory.return_value
            lab.worklist.queue.return_value = []
            harness_improve.step(lab, args)
            lab.capture.assert_called_once_with(args.swarm, base=args.base, seconds=args.seconds, release=self.release)

    def test_wrong_release_digest_refuses_before_observation(self):
        with patch('sys.argv', self.argv + ['--release-digest', '0' * 64]), \
                patch.object(harness_improve, 'transition') as transition:
            self.assertEqual(harness_improve.main(), 1)
            transition.assert_not_called()
        self.assertFalse((self.root / 'observer-heartbeat.json').exists())

    def test_failed_journal_open_is_reported_in_a_fresh_heartbeat(self):
        with patch('sys.argv', self.argv), \
                patch.object(harness_improve, 'HarnessImprovement', side_effect=OSError('journal unavailable')), \
                patch.object(harness_improve.time, 'sleep', side_effect=KeyboardInterrupt):
            self.assertEqual(harness_improve.main(), 0)
        pulse = read_json(self.root / 'observer-heartbeat.json')
        self.assertEqual(pulse['error'], 'journal unavailable')
        self.assertIsInstance(pulse['at'], float)

    def test_successful_capture_cannot_hide_nested_reconciliation_errors(self):
        args = harness_improve.parser().parse_args(self.argv[1:])
        with patch.object(harness_improve, 'HarnessImprovement') as factory, \
                patch.object(harness_improve, 'reconcile', side_effect=OSError('watchdog receipt unavailable')):
            lab = factory.return_value
            lab.worklist.queue.return_value = [SimpleNamespace(key='candidate-a'), SimpleNamespace(key='candidate-b')]
            lab.capture.return_value = []
            result = harness_improve.step(lab, args)
        self.assertNotIn('error', result)
        harness_improve.heartbeat(args, {}, result)
        pulse = read_json(self.root / 'observer-heartbeat.json')
        self.assertEqual(pulse['reconciliation_error_count'], 2)
        self.assertIn('watchdog receipt unavailable', pulse['error'])
        self.assertLessEqual(len(pulse['error']), 512)


if __name__ == '__main__':
    unittest.main()
