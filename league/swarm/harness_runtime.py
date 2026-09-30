"""Supervise the read-only harness observer from the House, using an explicit release-bound policy.

This starts no patch author, evaluator, deployment or paid call. The controller owns its separate
journal; the supervisor reads a small heartbeat and process record on the House's trading path.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
from typing import Any

from ..watchdog import tree_digest

REPO = Path(__file__).resolve().parents[2]


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def write_json(path: Path, value: dict) -> None:
    """Private, whole-file replacement; neither settings nor the shared trading ledger are touched."""
    part = path.with_name(path.name + f".{os.getpid()}.part")
    fd = os.open(part, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as handle:
        json.dump(value, handle, sort_keys=True, allow_nan=False)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(part, path)


def process(pid: int) -> tuple[list[str], str] | None:
    try:
        base = Path('/proc') / str(pid)
        argv = [p.decode() for p in (base / 'cmdline').read_bytes().split(b'\0') if p]
        fields = (base / 'stat').read_text().rsplit(')', 1)[1].split()
        return (argv, fields[19]) if fields[0] != 'Z' else None
    except (OSError, ValueError, IndexError, UnicodeError):
        return None


class HarnessSupervisor:
    def __init__(self, root: Path, *, code_dir: Path = REPO, python: str = sys.executable,
                 clock=time.time, spawn=subprocess.Popen, proc=process,
                 pidfd_open=os.pidfd_open, pidfd_signal=signal.pidfd_send_signal, close_fd=os.close):
        self.root, self.code = Path(root).resolve(), Path(code_dir).resolve()
        self.directory = self.root / 'harness'
        self.python, self.clock, self.spawn, self.proc = python, clock, spawn, proc
        self.pidfd_open, self.pidfd_signal, self.close_fd = pidfd_open, pidfd_signal, close_fd
        self.child: Any = None
        self._digest: str | None = None

    def _policy(self) -> tuple[dict, str | None]:
        policy = read_json(self.directory / 'runtime.json')
        if policy.get('enabled') is not True:
            return policy, None
        if (policy.get('schema') != 1 or policy.get('mode') != 'observe'
                or not re.fullmatch(r'[0-9a-f]{40}', str(policy.get('base') or ''))
                or not re.fullmatch(r'[0-9a-f]{64}', str(policy.get('release_digest') or ''))):
            return policy, 'invalid observer policy'
        if self._digest is None:
            self._digest = tree_digest(self.code)[0]  # immutable release, hashed only once per House process
        if policy['release_digest'] != self._digest:
            return policy, 'observer policy needs the reviewed base of this release'
        return policy, None

    def _owns(self, record: dict) -> bool:
        try:
            pid = int(record['pid'])
            if pid <= 1 or pid in (os.getpid(), os.getppid()) or not record.get('start'):
                return False
            found = self.proc(pid)
            if found is None or found[1] != record['start']:
                return False
            argv = found[0]
            def arg(name):
                return argv[argv.index(name) + 1] if argv.count(name) == 1 else None
            return (str(Path(record['release']) / 'scripts/harness_improve.py') in argv
                    and argv.count('watch') == 1
                    and arg('--root') == str(self.directory) and arg('--swarm') == str(self.root)
                    and arg('--base') == record['base'] and arg('--release') == record['release']
                    and arg('--release-digest') == record['release_digest']
                    and arg('--policy-signature') == record['policy'])
        except (KeyError, TypeError, ValueError, IndexError):
            return False

    def _signal(self, record: dict, sig: int) -> bool:
        """Bind the signal before checking /proc so PID reuse cannot redirect it to another process."""
        try:
            fd = self.pidfd_open(int(record['pid']), 0)
        except ProcessLookupError:
            return False
        try:
            if not self._owns(record):
                return False
            self.pidfd_signal(fd, sig, None, 0)
            return True
        except ProcessLookupError:
            return False
        finally:
            self.close_fd(fd)

    def _recover(self, pulse: dict) -> dict:
        """Recover only the identity the observer actually received; never relabel an old policy."""
        record = {key: pulse.get(key) for key in ('pid', 'start', 'release', 'base', 'release_digest', 'policy')}
        record.update(schema=1, launched_at=pulse.get('session_started_at'))
        return record if self._owns(record) else {}

    def _watch_busy(self) -> bool:
        with (self.directory / 'watch.lock').open('a') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return False
            except BlockingIOError:
                return True

    def tick(self) -> dict:
        # With no operator policy, the existing deployment remains unchanged and creates no files.
        if not self.directory.exists():
            return {'enabled': False, 'running': False}
        with (self.directory / 'runtime.lock').open('a') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return {'waiting': 'another supervisor is checking the observer'}
            return self._tick()

    def _tick(self) -> dict:
        now = self.clock()
        policy, error = self._policy()
        enabled = policy.get('enabled') is True
        stopped = any(p.exists() for p in (self.root / 'STOP', self.root.parent / 'STOP'))
        wanted = enabled and error is None and not stopped
        signature = hashlib.sha256(json.dumps(policy, sort_keys=True).encode()).hexdigest()
        path = self.directory / 'runtime-process.json'
        record = read_json(path)
        pulse = read_json(self.directory / 'observer-heartbeat.json')
        if self.child is not None:
            self.child.poll()  # reap a child after a crash or a requested stop
        owned = self._owns(record)
        if not owned:
            recovered = self._recover(pulse)
            if recovered:
                record, owned = recovered, True
                write_json(path, record)
        if owned:
            pulse_matches = all(pulse.get(key) == record.get(key)
                                for key in ('pid', 'start', 'release', 'base', 'release_digest', 'policy'))
            last = pulse.get('at') if pulse_matches else record.get('launched_at')
            fresh = isinstance(last, (int, float)) and math.isfinite(last) and 0 <= now - last <= 180
            same = (record.get('policy') == signature and record.get('release') == str(self.code)
                    and record.get('base') == policy.get('base')
                    and record.get('release_digest') == policy.get('release_digest'))
            if wanted and same and fresh and not record.get('stopping_at'):
                status = {'enabled': True, 'running': True, 'pid': record['pid'],
                          'heartbeat_age_seconds': now - last, 'mode': 'observe'}
                if pulse_matches:
                    status.update({key: pulse[key] for key in ('error', 'waiting', 'reconciliation_error_count')
                                   if pulse.get(key)})
                return status
            if not record.get('stopping_at'):
                signaled = self._signal(record, signal.SIGTERM)
                record['stopping_at'] = now
            elif now - record['stopping_at'] >= 15:
                signaled = self._signal(record, signal.SIGKILL)
            else:
                signaled = True
            write_json(path, record)
            return {'enabled': enabled, 'running': signaled, 'stopping': True,
                    'reason': error or ('stopped' if stopped else 'policy changed or observer heartbeat stale')}
        if not wanted:
            return {'enabled': enabled, 'running': False, 'error': error, 'stopped': stopped}
        if self._watch_busy():
            return {'enabled': True, 'running': False, 'observer_present': True,
                    'waiting': 'observer holds its lifetime lock; awaiting a verified heartbeat'}
        if 0 <= now - float(record.get('launched_at') or 0) < 60:
            return {'enabled': True, 'running': False, 'waiting': 'observer restart backoff'}
        argv = [self.python, str(self.code / 'scripts/harness_improve.py'), '--root', str(self.directory),
                'watch', '--swarm', str(self.root), '--base', policy['base'],
                '--release', str(self.code), '--release-digest', policy['release_digest'],
                '--policy-signature', signature,
                '--deploy-base', str(self.root.parent), '--interval', '60']
        fd = os.open(self.directory / 'observer.log', os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, 'ab') as log:
            child = self.spawn(argv, cwd=str(self.code), stdin=subprocess.DEVNULL, stdout=log,
                               stderr=subprocess.STDOUT, start_new_session=True, close_fds=True)
        self.child = child
        found = self.proc(child.pid)
        record = {'schema': 1, 'pid': child.pid, 'start': found[1] if found else None,
                  'release': str(self.code), 'policy': signature, 'base': policy['base'],
                  'release_digest': policy['release_digest'], 'launched_at': now}
        write_json(path, record)
        if not self._owns(record):
            return {'enabled': True, 'running': False, 'error': 'observer exited or could not be identified'}
        return {'enabled': True, 'running': True, 'started': True, 'pid': child.pid, 'mode': 'observe'}


__all__ = ['HarnessSupervisor', 'process', 'write_json']
