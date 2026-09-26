"""Agent programs run in a separate process: the live path's `decide(ctx)`, isolated from the House.

The options-swarm run, Wave 5 (Sept 26, 2026). On the House box a program meets live quotes, and a program is code a
model wrote. So it never runs inside the House process: one child process (`python -m league.live.decider`) holds every
live program instance (`league.gym.runtime.Runner`: its module globals are its memory) and answers one batch of
decisions a minute. What that buys:

- **Time.** The Gym's runner times each call with SIGALRM, which works only on a process's main thread: in the child it
  does (1 s a call, 25 errors and the instance is disqualified, as in the Gym). If the child still does not answer by
  the batch's deadline (a loop inside numpy's C code, say), the House kills it, starts a fresh one, reloads every
  program (their memory starts again) and counts the batch as errors: the House's own minute is never held.
- **Memory.** The child's address space is capped (`RLIMIT_AS`).
- **Secrets.** The child starts with an empty environment (no GATEWAY_TOKEN, no SAIL_API_KEY) and `-E -s`; the House
  process is undumpable (its `/proc/<pid>/environ` is root's); the child runs in its own network namespace (loopback
  only) wherever the box allows one; the House reads its answers as JSON, never pickle, so a program that escaped the
  Gym's sandbox still could not hand the House an object to run, reach the gateway, or read the token.

The parent sends each minute's `Snapshot`s once (pickled; the House is the trusted side), keyed by (root, minute
index), and each instance's account rows with the minute index it decides on; the child slices each instance's chain with the Gym's own `Snapshot.view(slice_index(...))`, builds the ctx with
the Gym's own `build_ctx` and calls `Runner.decide`, exactly as `league.gym.engine.Account._decide` does, so a program
sees the same ctx live as in the replay. `InlineDecider` is the same API in one process, for tests.
"""

from __future__ import annotations

import json
import os
import pickle
import select
import struct
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

REPO = Path(__file__).resolve().parents[2]
HEADER = struct.Struct(">I")
MAX_FRAME = 256 * 1024 * 1024
MEMORY_MB = 2048


class DeciderError(RuntimeError):
    """The child failed or did not answer in time (it has been killed and restarted)."""


class ProgramRefused(ValueError):
    """The program did not load (its safety check, NEEDS or PARAMS)."""


# ---------------------------------------------------------------------------------------------- the child's side
def _handle(message: Any, runners: dict, reply: Any) -> bool:
    """One message from the House; False when it says to stop. Mirrors `league.gym.engine.Account._decide`."""
    from ..gym import runtime as R
    from ..gym.ctx import build_ctx

    kind = message[0]
    try:
        if kind == "load":
            _, key, code, params, name, timeout, max_errors = message
            program = R.load_program(code, name=name, params=params)
            runners[key] = program.start(timeout=timeout, max_errors=max_errors)
            reply({"ok": True, "needs": program.needs.as_dict(), "sha": program.sha, "run_sha": program.run_sha})
        elif kind == "drop":
            runners.pop(message[1], None)
            reply({"ok": True})
        elif kind == "decide":
            _, snaps, unders, jobs = message
            out = {}
            for job in jobs:
                runner = runners.get(job["key"])
                if runner is None:
                    out[job["key"]] = {"intents": [], "stats": None, "missing": True}
                    continue
                needs = runner.program.needs
                mi = job.get("mi")
                chains = {}
                for root in job["roots"]:
                    snap = snaps.get((root, mi))
                    if snap is not None:
                        chains[root] = snap.view(snap.slice_index(needs.dte_min, needs.dte_max, needs.band),
                                                 key=(needs.dte_min, needs.dte_max, needs.band))
                if not chains:
                    out[job["key"]] = {"intents": [], "stats": runner.stats(), "skipped": True}
                    continue
                ctx = build_ctx(minute=job["minute"], open_minute=job["open_minute"], close_minute=job["close_minute"],
                                weekday=job["weekday"], chains=chains,
                                underlyings={r: unders[(r, needs.history, mi)] for r in chains},
                                positions=job["positions"], orders=job["orders"], cash=job["cash"], equity=job["equity"],
                                budget=job["budget"], buying_power=job["buying_power"], params=runner.program.params,
                                rules={r: job["rules"][r] for r in chains}, events=job["events"],
                                events_next=job["events_next"], closed=job["closed"], rejects=job["rejects"],
                                roots=tuple(chains))
                intents = runner.decide(ctx)
                out[job["key"]] = {"intents": intents, "stats": runner.stats()}
            reply({"ok": True, "results": out})
        elif kind == "ping":
            try:  # the child's own network namespace's interfaces (/proc/self/net is per namespace; /sys is not remounted)
                lines = open("/proc/self/net/dev", encoding="utf-8").read().splitlines()[2:]
                interfaces = sorted(line.split(":", 1)[0].strip() for line in lines if ":" in line)
            except OSError:
                interfaces = None
            reply({"ok": True, "pid": os.getpid(), "env": sorted(os.environ), "interfaces": interfaces})
        elif kind == "quit":
            reply({"ok": True})
            return False
        else:
            reply({"ok": False, "error": f"unknown message {kind!r}"})
    except R.CodeRefused as exc:
        reply({"ok": False, "refused": True, "error": str(exc)[:500]})
    except Exception as exc:  # noqa: BLE001 - one bad message never ends the child
        reply({"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:500]}"})
    return True


def _serve(stdin: Any, stdout: Any) -> None:
    runners: dict[str, Any] = {}

    def reply(obj: Any) -> None:
        data = json.dumps(_finite(obj), default=_plain_default, allow_nan=False).encode("utf-8")
        stdout.write(HEADER.pack(len(data)) + data)
        stdout.flush()

    while True:
        head = stdin.read(HEADER.size)
        if len(head) < HEADER.size:
            return
        (size,) = HEADER.unpack(head)
        if not _handle(pickle.loads(stdin.read(size)), runners, reply):
            return


def _finite(value: Any, depth: int = 0) -> Any:
    """A JSON-safe copy: a float that is not finite becomes None (a program may return NaN; one bad number must not
    cost the batch)."""
    if depth > 12:
        return None
    if isinstance(value, float):
        return value if value == value and value not in (float("inf"), float("-inf")) else None
    if isinstance(value, dict):
        return {str(k): _finite(v, depth + 1) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_finite(v, depth + 1) for v in value]
    return value


def _plain_default(value: Any) -> Any:
    item = getattr(value, "item", None)
    if callable(item):
        return item()
    tolist = getattr(value, "tolist", None)
    if callable(tolist):
        return tolist()
    return str(value)


def child_main() -> None:  # pragma: no cover - run as a subprocess
    try:
        import resource

        limit = int(os.environ.get("LIVE_DECIDER_MEMORY_MB") or MEMORY_MB) * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
    except (ImportError, ValueError, OSError):
        pass
    try:
        os.nice(5)
    except OSError:
        pass
    _serve(sys.stdin.buffer, sys.stdout.buffer)


# --------------------------------------------------------------------------------------------- the House's side
#: The longest a minute's batch may hold the House's minute (the live step runs a few seconds past the minute).
MAX_BATCH_SECONDS = 40.0


def batch_deadline(timeout: float, jobs: int) -> float:
    """How long the House waits for a batch: 5 s plus each call's limit and a margin, never past `MAX_BATCH_SECONDS`."""
    return min(MAX_BATCH_SECONDS, 5.0 + (float(timeout) + 0.25) * int(jobs))


def _netns_available() -> bool:
    """Whether this box lets an unprivileged process make a network namespace (probed once)."""
    import shutil

    if not shutil.which("unshare"):
        return False
    try:
        return subprocess.run(["unshare", "--net", "--map-root-user", "true"], capture_output=True, timeout=10).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def protect_house_process() -> bool:
    """The House's process made undumpable (Linux `prctl(PR_SET_DUMPABLE, 0)`): its `/proc/<pid>/environ` and memory,
    where the gateway token lives, are then root's, not readable by a child of the same user (a program that escaped
    the Gym's sandbox in the decider). True when set. The child runs as the House's user and in its network: this
    closes the one path to the token that needs no escape past the interpreter (the review of #362, m16)."""
    import sys as _sys

    if not _sys.platform.startswith("linux"):
        return False
    try:
        import ctypes

        libc = ctypes.CDLL(None, use_errno=True)
        return libc.prctl(4, 0, 0, 0, 0) == 0           # PR_SET_DUMPABLE = 4
    except (OSError, AttributeError):
        return False


class _Base:
    def __init__(self, *, timeout: float = 1.0, max_errors: int = 25):
        self.timeout, self.max_errors = float(timeout), int(max_errors)
        self.loaded: dict[str, tuple[str, dict, str]] = {}
        self.info: dict[str, dict] = {}
        self.restarts = 0
        self.lock = threading.RLock()

    def load(self, key: str, code: str, params: Mapping[str, Any] | None, name: str) -> dict:
        """Load a program instance (fresh memory). Its NEEDS, sha and run sha; ProgramRefused when it does not load."""
        with self.lock:
            answer = self._ask(("load", key, code, dict(params or {}), name, self.timeout, self.max_errors), 30.0)
            if not answer.get("ok"):
                raise ProgramRefused(answer.get("error") or "the program did not load")
            self.loaded[key] = (code, dict(params or {}), name)
            self.info[key] = {"needs": answer["needs"], "sha": answer["sha"], "run_sha": answer["run_sha"]}
            return self.info[key]

    def drop(self, key: str) -> None:
        with self.lock:
            if self.loaded.pop(key, None) is not None:
                self.info.pop(key, None)
                try:
                    self._ask(("drop", key), 10.0)
                except DeciderError:
                    pass

    def decide(self, snaps: Mapping[str, Any], unders: Mapping[Any, Any], jobs: Sequence[Mapping[str, Any]]) -> dict[str, dict]:
        """One minute's batch. {key: {"intents": [...], "stats": {...}}}; DeciderError when the child failed (it was
        restarted, every program reloaded with fresh memory)."""
        if not jobs:
            return {}
        with self.lock:
            answer = self._ask(("decide", dict(snaps), dict(unders), list(jobs)), batch_deadline(self.timeout, len(jobs)))
            if not answer.get("ok"):
                raise DeciderError(answer.get("error") or "the decider failed")
            return answer["results"]

    def _ask(self, message: Any, deadline: float) -> dict:  # pragma: no cover - abstract
        raise NotImplementedError

    def ping(self) -> dict:
        with self.lock:
            return self._ask(("ping",), 30.0)

    def close(self) -> None:
        pass


class Decider(_Base):
    """The child process (the module docstring)."""

    def __init__(self, *, timeout: float = 1.0, max_errors: int = 25, memory_mb: int = MEMORY_MB,
                 python: str = sys.executable, log: str | Path | None = None):
        super().__init__(timeout=timeout, max_errors=max_errors)
        self.memory_mb, self.python, self.log = int(memory_mb), python, log
        self.proc: subprocess.Popen | None = None
        self.pid: int | None = None
        #: The child runs in its own network namespace (`unshare --net --map-root-user`: loopback only, no route to the
        #: gateway, Sail or anywhere) wherever the box allows an unprivileged one; decided once, at the first spawn.
        self.netns: bool | None = None

    def _spawn(self) -> None:
        protect_house_process()
        err = open(self.log, "ab") if self.log else subprocess.DEVNULL  # noqa: SIM115
        env = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "HOME": "/tmp", "LIVE_DECIDER_MEMORY_MB": str(self.memory_mb),
               "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"}
        if self.netns is None:
            self.netns = _netns_available()
        command = [self.python, "-E", "-s", "-m", "league.live.decider"]
        if self.netns:
            command = ["unshare", "--net", "--map-root-user", *command]
        self.proc = subprocess.Popen(command, cwd=str(REPO), env=env,
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=err, close_fds=True)
        if err is not subprocess.DEVNULL:
            err.close()
        self.pid = self.proc.pid

    def _kill(self) -> None:
        proc, self.proc = self.proc, None
        if proc is None:
            return
        try:
            proc.kill()
            proc.wait(timeout=5)
        except Exception:  # noqa: BLE001
            pass

    def _raw(self, message: Any, deadline: float) -> dict:
        if self.proc is None or self.proc.poll() is not None:
            self._spawn()
        assert self.proc is not None and self.proc.stdin is not None and self.proc.stdout is not None
        data = pickle.dumps(message, protocol=pickle.HIGHEST_PROTOCOL)
        try:
            self.proc.stdin.write(HEADER.pack(len(data)) + data)
            self.proc.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise DeciderError(f"the decider's pipe broke: {exc}") from None
        end = time.monotonic() + deadline
        head = self._read(HEADER.size, end)
        (size,) = HEADER.unpack(head)
        if size > MAX_FRAME:
            raise DeciderError(f"the decider answered {size} bytes")
        return json.loads(self._read(size, end).decode("utf-8"))

    def _read(self, n: int, end: float) -> bytes:
        assert self.proc is not None and self.proc.stdout is not None
        fd = self.proc.stdout.fileno()
        chunks, got = [], 0
        while got < n:
            left = end - time.monotonic()
            if left <= 0:
                raise DeciderError("the decider did not answer in time")
            ready, _, _ = select.select([fd], [], [], left)
            if not ready:
                raise DeciderError("the decider did not answer in time")
            chunk = os.read(fd, n - got)
            if not chunk:
                raise DeciderError("the decider exited")
            chunks.append(chunk)
            got += len(chunk)
        return b"".join(chunks)

    def _ask(self, message: Any, deadline: float) -> dict:
        try:
            return self._raw(message, deadline)
        except (DeciderError, ValueError, struct.error) as exc:
            self._kill()
            self.restarts += 1
            self._reload()
            raise DeciderError(f"{exc}; the decider was restarted and its programs reloaded (their memory is new)") from None

    def _reload(self) -> None:
        for key, (code, params, name) in list(self.loaded.items()):
            try:
                answer = self._raw(("load", key, code, params, name, self.timeout, self.max_errors), 30.0)
                if not answer.get("ok"):
                    self.loaded.pop(key, None)
                    self.info.pop(key, None)
            except Exception:  # noqa: BLE001 - a reload that fails leaves the rest for the next batch
                self._kill()
                return

    def close(self) -> None:
        with self.lock:
            if self.proc is not None and self.proc.poll() is None:
                try:
                    self._raw(("quit",), 5.0)
                except Exception:  # noqa: BLE001
                    pass
            self._kill()


class InlineDecider(_Base):
    """The same API in this process, for tests: the same `_handle`, the same JSON round trip of its answers (a
    program's time limit then needs the main thread)."""

    def __init__(self, *, timeout: float = 1.0, max_errors: int = 25):
        super().__init__(timeout=timeout, max_errors=max_errors)
        self._runners: dict[str, Any] = {}

    def _ask(self, message: Any, deadline: float) -> dict:
        answers: list[dict] = []
        _handle(pickle.loads(pickle.dumps(message)), self._runners,
                lambda obj: answers.append(json.loads(json.dumps(_finite(obj), default=_plain_default, allow_nan=False))))
        return answers[0]


if __name__ == "__main__":  # pragma: no cover
    child_main()
