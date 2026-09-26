"""Supervise the optional nightly data collector without blocking a House tick.

The operator installs the private data/image records in <state>/data and enables
<state>/data-nightly.json. The collector owns a lifetime flock and an atomic
heartbeat. A House restart adopts it; a release change waits for a healthy job
to finish. Process identity includes argv, state directory and Linux start ticks.
This module does not place orders or handle a ThetaData/venue credential.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from typing import Any, Callable


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def process_info(pid: int) -> tuple[list[str], str] | None:
    try:
        base = Path('/proc') / str(pid)
        argv = [part.decode('utf-8', 'replace') for part in (base / 'cmdline').read_bytes().split(b'\0') if part]
        start = (base / 'stat').read_text().rsplit(')', 1)[1].split()[19]
        return argv, start
    except (OSError, ValueError, IndexError):
        return None


def lock_held(path: Path) -> bool:
    """An unreadable existing lock is occupied, never permission to duplicate work."""
    import fcntl

    try:
        handle = path.open('r+')
    except FileNotFoundError:
        return False
    except OSError:
        return True
    with handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return True
        fcntl.flock(handle, fcntl.LOCK_UN)
        return False


class NightlySupervisor:
    """File/process checks only; actual data work stays in the child process."""

    def __init__(self, root: str | Path, *, code_dir: str | Path, python: str = sys.executable,
                 clock: Callable[[], float] = time.time, spawn: Callable[[], Any] | None = None,
                 kill: Callable[[int, int], None] = os.kill,
                 proc: Callable[[int], tuple[list[str], str] | None] = process_info):
        self.root = Path(root)
        self.data = self.root / 'data'
        self.code_dir = Path(code_dir).resolve()
        self.python, self.clock, self.kill, self.proc = python, clock, kill, proc
        self.spawn = spawn or self._popen
        self.child: Any = None
        self.child_identity: dict[str, Any] = {}
        self.last_start = float('-inf')
        self.failures = 0
        self.accounted = True
        self.terminating: tuple[dict[str, Any], float] | None = None
        self.first_seen: tuple[int, str, float] | None = None

    def verified(self, record: dict[str, Any]) -> bool:
        try:
            pid = int(record['pid'])
            start = str(record['start'])
        except (KeyError, TypeError, ValueError):
            return False
        if pid <= 1 or pid in (os.getpid(), os.getppid()) or not start:
            return False
        seen = self.proc(pid)
        if seen is None or seen[1] != start:
            return False
        argv = seen[0]
        try:
            script = next(Path(arg) for arg in argv if Path(arg).name == 'nightly.py')
            state = argv[argv.index('--state') + 1]
        except (StopIteration, ValueError, IndexError):
            return False
        release = record.get('release')
        return ('daemon' in argv and state == str(self.data)
                and script.is_absolute() and release is not None
                and script == Path(str(release)) / 'scripts' / 'data' / 'nightly.py')

    def _stop(self, record: dict[str, Any], reason: str, out: dict[str, Any]) -> None:
        if not self.verified(record):
            out['action'] = f'{reason}; process identity unverified, not signalling'
            return
        pid, start = int(record['pid']), str(record['start'])
        try:
            self.kill(pid, signal.SIGTERM)
            self.terminating = (dict(record, pid=pid, start=start), self.clock())
            out['action'] = 'stopping: ' + reason
        except ProcessLookupError:
            out['action'] = 'process exited'
        except OSError as error:
            out['action'] = f'signal failed: {type(error).__name__}'

    def tick(self, *, may_start: bool = True) -> dict[str, Any]:
        now = self.clock()
        config = read_json(self.root / 'data-nightly.json')
        enabled = config.get('enabled') is True
        beat = read_json(self.data / 'nightly.heartbeat')
        record = read_json(self.data / 'nightly.lock')
        held = lock_held(self.data / 'nightly.lock')
        own_alive = self.child is not None and self.child.poll() is None
        running = held or own_alive
        if not held and own_alive:
            record = self.child_identity
        out: dict[str, Any] = {'enabled': enabled, 'running': running, 'pid': record.get('pid') if running else None}
        same_beat = bool(record.get('start')) and all(beat.get(key) == record.get(key) for key in ('pid', 'start', 'release'))
        try:
            age = now - float(beat['at']) if same_beat else None
            if age is not None and not math.isfinite(age):
                age = None
        except (KeyError, ValueError, TypeError):
            age = None
        out['heartbeat_age'] = round(age, 1) if age is not None else None
        for key in ('state', 'day', 'next_due', 'next_wake', 'last_success', 'error'):
            if same_beat and key in beat:
                out[key] = beat[key]

        if self.terminating:
            identity, since = self.terminating
            pid = int(identity['pid'])
            if self.verified(identity):
                if now - since >= 120 and self.verified(identity):
                    try:
                        self.kill(pid, signal.SIGKILL)
                    except OSError:
                        pass
                out['action'] = 'waiting for collector to stop'
                return out
            self.terminating = None

        stops = [path for path in (self.root / 'STOP', self.root.parent / 'STOP', self.data / 'nightly.stop') if path.exists()]
        if not enabled or stops:
            reason = f'{stops[0].name} is set' if stops else 'disabled'
            out['idle'] = reason
            if running:
                self._stop(record, reason, out)
            return out

        if running:
            if not self.verified(record):
                out['action'] = 'collector lock/child is occupied; process identity unverified'
                return out
            identity = (int(record['pid']), str(record['start']))
            if self.first_seen is None or self.first_seen[:2] != identity:
                self.first_seen = (*identity, now)
            if held and age is not None and -5 <= age < 300:
                self.failures = 0
                if record.get('release') != str(self.code_dir):
                    if beat.get('busy'):
                        out['action'] = 'waiting for current data job before release change'
                    else:
                        self._stop(record, 'another release', out)
                return out
            # An adopted collector without a matching heartbeat gets a startup grace from
            # its own start timestamp, never from a stale predecessor's heartbeat.
            try:
                started = float(record.get('started_at', self.first_seen[2]))
                if not math.isfinite(started):
                    started = self.first_seen[2]
            except (TypeError, ValueError):
                started = self.first_seen[2]
            if (age is not None and (age >= 300 or age < -5)) or now - started >= 90:
                self._stop(record, 'heartbeat missing or stale', out)
            return out

        if not may_start:
            out['idle'] = 'the House is not open for business'
            return out
        if self.child is not None and not self.accounted:
            self.failures += 1
            self.accounted = True
        backoff = min(1800, 30 * 2 ** min(self.failures, 6))
        if now - self.last_start < backoff:
            out['action'] = 'start backoff'
            return out
        script = self.code_dir / 'scripts' / 'data' / 'nightly.py'
        if not script.is_file():
            out['idle'] = 'collector script is not in this release'
            return out
        self.last_start = now
        try:
            self.child = self.spawn()
            self.accounted = False
            seen = self.proc(self.child.pid)
            self.child_identity = {'pid': self.child.pid, 'start': seen[1] if seen else None,
                                   'release': str(self.code_dir), 'started_at': now}
            out.update(action='started', running=True, pid=self.child.pid)
        except Exception as error:
            self.failures += 1
            out['action'] = f'start failed: {type(error).__name__}'
        return out

    def _popen(self) -> Any:
        self.data.mkdir(parents=True, exist_ok=True, mode=0o700)
        log_path = self.data / 'nightly.log'
        if log_path.exists() and log_path.stat().st_size > 10 * 2 ** 20:
            log_path.replace(log_path.with_name('nightly.log.1'))
        # Trusted House code relays SIP reads through the gateway. It never copies
        # either token to the data box, which holds only its own ThetaData key.
        names = ('PATH', 'LANG', 'LC_ALL', 'TZ', 'SAIL_API_KEY', 'GATEWAY_TOKEN', 'SSL_CERT_FILE', 'SSL_CERT_DIR')
        env = {name: os.environ[name] for name in names if name in os.environ}
        with log_path.open('ab') as log:
            return subprocess.Popen([self.python, '-u', str(self.code_dir / 'scripts' / 'data' / 'nightly.py'),
                                     'daemon', '--state', str(self.data), '--ready-file', str(self.root / 'gym-forward.json')],
                                    cwd=str(self.code_dir), env=env, stdin=subprocess.DEVNULL,
                                    stdout=log, stderr=subprocess.STDOUT, close_fds=True, start_new_session=True)
