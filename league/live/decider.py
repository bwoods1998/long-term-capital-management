"""Agent programs run in a separate process: the live path's `decide(ctx)`, isolated from the House.

The options-swarm run, Wave 5 (Sept 26, 2026). On the House box a program meets live quotes, and a program is code a
model wrote. So it never runs inside the House process: one child process (`python -m league.live.decider`) holds every
live program instance (`league.gym.runtime.Runner`: its module globals are its memory) and answers one batch of
decisions a minute. What that buys:

- **Time.** The Gym's runner times each call with SIGALRM, which works only on a process's main thread: in the child it
  does (1 s a call, 25 errors and the instance is disqualified, as in the Gym). If the child still does not answer by
  the batch's deadline (a loop inside numpy's C code, say), the House kills it. Reloads happen in the next request's
  budget, never as unbounded cleanup after the deadline. Program memory starts again.
- **Memory.** The child's address space is capped (`RLIMIT_AS`), shared by all its programs. One program can exhaust
  that shared allowance and cost the other programs their decision for this minute.
- **Secrets.** The child starts with an empty environment (no GATEWAY_TOKEN, no SAIL_API_KEY) and `-E -s`; the House
  process is undumpable (its `/proc/<pid>/environ` is root's); the child runs in its own network namespace (loopback
  only) wherever the box allows one; answers are JSON, never pickle. These measures are defense in depth, not an OS
  security boundary on an ordinary-user developer machine, where an escape retains that user's filesystem access.
  On the root production House the child uses uid/gid 65534, no supplementary groups, a mandatory private network
  namespace and a dedicated root-owned read-only runtime. No namespace means no child. The secret env must stay
  root-owned mode 0600; the state and deployment directories must not allow group/other writes.

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
import shutil
import struct
import subprocess
import sys
import threading
import tempfile
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
                lines = Path("/proc/self/net/dev").read_text().splitlines()[2:]
                interfaces = sorted(line.split(":", 1)[0].strip() for line in lines if ":" in line)
                routes = {line.split()[0] for line in Path("/proc/self/net/route").read_text().splitlines()[1:] if line.strip()}
                ipv6_routes, ipv6_addresses = Path("/proc/self/net/ipv6_route"), Path("/proc/self/net/if_inet6")
                routes.update(line.split()[-1] for line in (ipv6_routes.read_text().splitlines() if ipv6_routes.exists() else []) if line.strip())
                import fcntl
                import ipaddress
                import socket

                addresses = [str(ipaddress.IPv6Address(int(line.split()[0], 16)))
                             for line in (ipv6_addresses.read_text().splitlines() if ipv6_addresses.exists() else []) if line.strip()]
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                    for interface in interfaces:
                        try:
                            response = fcntl.ioctl(sock.fileno(), 0x8915, struct.pack("256s", interface.encode()[:15]))
                            addresses.append(socket.inet_ntoa(response[20:24]))
                        except OSError:  # a dormant tunnel such as sit0 has no IPv4 address
                            pass
            except OSError:
                interfaces, routes, addresses = None, None, None
            reply({"ok": True, "pid": os.getpid(), "env": sorted(os.environ), "interfaces": interfaces,
                   "routed_interfaces": None if routes is None else sorted(routes), "addresses": addresses})
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
    if sys.platform.startswith("linux"):
        import ctypes

        if ctypes.CDLL(None, use_errno=True).prctl(38, 1, 0, 0, 0) != 0:  # PR_SET_NO_NEW_PRIVS
            raise RuntimeError("the decider could not disable privilege gains")
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


def batch_deadline(timeout: float, jobs: int, budget_seconds: float | None = None) -> float:
    """How long the House waits for a batch: 5 s plus each call's limit and a margin, never past `MAX_BATCH_SECONDS`."""
    return max(0.0, min(MAX_BATCH_SECONDS, 5.0 + (float(timeout) + 0.25) * int(jobs),
                        float(budget_seconds) if budget_seconds is not None else MAX_BATCH_SECONDS))


def _netns_available(timeout: float = 10.0, *, credentials: Mapping[str, Any] | None = None) -> bool:
    """Whether this box lets an unprivileged process make a network namespace (probed once)."""
    if not shutil.which("unshare"):
        return False
    try:
        return subprocess.run(["unshare", "--net", "--map-root-user", "true"], capture_output=True, timeout=timeout,
                               **dict(credentials or {})).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def protect_house_process() -> bool:
    """The House's process made undumpable (Linux `prctl(PR_SET_DUMPABLE, 0)`): its `/proc/<pid>/environ` and memory,
    where the gateway token lives, are then root's, not readable by a child of the same user (a program that escaped
    the Gym's sandbox in the decider). True when set. This narrows the paths to the House's secrets, it does not close
    them for a same-user child. The production root House also drops the child's host uid/gid and requires a private
    network namespace; the module docstring describes that additional boundary."""
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

    def load(self, key: str, code: str, params: Mapping[str, Any] | None, name: str,
             *, budget_seconds: float | None = None) -> dict:
        """Load a program instance (fresh memory). Its NEEDS, sha and run sha; ProgramRefused when it does not load."""
        with self.lock:
            answer = self._ask(("load", key, code, dict(params or {}), name, self.timeout, self.max_errors),
                               min(30.0, budget_seconds) if budget_seconds is not None else 30.0)
            if not answer.get("ok"):
                raise ProgramRefused(answer.get("error") or "the program did not load")
            self.loaded[key] = (code, dict(params or {}), name)
            self.info[key] = {"needs": answer["needs"], "sha": answer["sha"], "run_sha": answer["run_sha"]}
            return self.info[key]

    def drop(self, key: str, *, budget_seconds: float = 10.0) -> None:
        with self.lock:
            if self.loaded.pop(key, None) is not None:
                self.info.pop(key, None)
                try:
                    self._ask(("drop", key), max(0.0, min(10.0, budget_seconds)))
                except DeciderError:
                    pass

    def decide(self, snaps: Mapping[str, Any], unders: Mapping[Any, Any], jobs: Sequence[Mapping[str, Any]],
               *, budget_seconds: float | None = None) -> dict[str, dict]:
        """One minute's batch. {key: {"intents": [...], "stats": {...}}}; DeciderError when the child failed (it was
        restarted, every program reloaded with fresh memory)."""
        if not jobs:
            return {}
        with self.lock:
            answer = self._ask(("decide", dict(snaps), dict(unders), list(jobs)),
                               batch_deadline(self.timeout, len(jobs), budget_seconds))
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
        self._ready: set[str] = set()
        self.isolated = os.geteuid() == 0
        self._runtime: Path | None = None
        #: The child runs in its own network namespace (`unshare --net --map-root-user`: loopback only, no route to the
        #: gateway, Sail or anywhere) wherever the box allows an unprivileged one; decided once, at the first spawn.
        self.netns: bool | None = None

    def _spawn(self, budget_seconds: float = 10.0) -> None:
        protect_house_process()
        credentials = {"user": 65534, "group": 65534, "extra_groups": []} if self.isolated else {}
        env = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "HOME": "/tmp", "LIVE_DECIDER_MEMORY_MB": str(self.memory_mb),
               "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"}
        if self.netns is None:
            self.netns = _netns_available(timeout=max(0.001, min(10.0, budget_seconds)), credentials=credentials)
        if self.isolated and not self.netns:
            raise DeciderError("the production decider requires a network namespace under its separate uid")
        cwd = REPO
        if self.isolated:
            if self._runtime is None:
                self._runtime = Path(tempfile.mkdtemp(prefix="ltcm-decider-runtime-"))
                files = ("league/__init__.py", "league/safety.py", "league/structure_core.py", "league/live/__init__.py",
                         "league/live/decider.py", "league/gym/__init__.py", "league/gym/runtime.py", "league/gym/safety.py",
                         "league/gym/ctx.py", "league/gym/greeks.py", "league/gym/venue.py")
                for name in files:
                    path = self._runtime / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(REPO / name, path)
                    path.chmod(0o444)
                for path in self._runtime.rglob("*"):
                    if path.is_dir():
                        path.chmod(0o555)
                self._runtime.chmod(0o555)
            cwd = self._runtime
        command = [self.python, "-E", "-s", "-m", "league.live.decider"]
        if self.netns:
            command = ["unshare", "--net", "--map-root-user", *command]
        err = open(self.log, "ab") if self.log else subprocess.DEVNULL  # noqa: SIM115
        try:
            self.proc = subprocess.Popen(command, cwd=str(cwd), env=env, **credentials,
                                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=err, close_fds=True)
        finally:
            if err is not subprocess.DEVNULL:
                err.close()
        self.pid = self.proc.pid
        self._ready.clear()

    def _kill(self) -> None:
        proc, self.proc = self.proc, None
        self._ready.clear()
        if proc is None:
            return
        try:
            proc.kill()
            proc.wait(timeout=0.1)
        except Exception:  # noqa: BLE001
            pass
        finally:
            for stream in (proc.stdin, proc.stdout):
                if stream is not None:
                    stream.close()

    def _raw(self, message: Any, deadline: float) -> dict:
        end = time.monotonic() + deadline
        if deadline <= 0:
            raise DeciderError("the decider's minute budget is exhausted")
        if self.proc is None or self.proc.poll() is not None:
            self._spawn(budget_seconds=deadline)
        assert self.proc is not None and self.proc.stdin is not None and self.proc.stdout is not None
        data = pickle.dumps(message, protocol=pickle.HIGHEST_PROTOCOL)
        if len(data) > MAX_FRAME:
            raise DeciderError(f"the decider input exceeds {MAX_FRAME} bytes")
        try:
            # A child that does not consume stdin can otherwise hold the House before the response deadline starts.
            fd = self.proc.stdin.fileno()
            os.set_blocking(fd, False)
            frame = memoryview(HEADER.pack(len(data)) + data)
            while frame:
                left = end - time.monotonic()
                if left <= 0 or not select.select([], [fd], [], left)[1]:
                    raise DeciderError("the decider did not consume its input in time")
                try:
                    frame = frame[os.write(fd, frame):]
                except BlockingIOError:
                    continue
        except (BrokenPipeError, OSError) as exc:
            raise DeciderError(f"the decider's pipe broke: {exc}") from None
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
        end = time.monotonic() + deadline
        try:
            if message[0] == "decide":
                if self.proc is None or self.proc.poll() is not None:
                    self._ready.clear()
                for job in message[3]:
                    key = job["key"]
                    if key in self._ready or key not in self.loaded:
                        continue
                    code, params, name = self.loaded[key]
                    answer = self._raw(("load", key, code, params, name, self.timeout, self.max_errors), end - time.monotonic())
                    if not answer.get("ok"):
                        continue
                    self._ready.add(key)
            answer = self._raw(message, end - time.monotonic())
            if message[0] == "load" and answer.get("ok"):
                self._ready.add(message[1])
            elif message[0] == "drop":
                self._ready.discard(message[1])
            return answer
        except (DeciderError, ValueError, struct.error) as exc:
            self._kill()
            self.restarts += 1
            raise DeciderError(f"{exc}; the child was killed; programs reload within the next request's budget") from None

    def close(self) -> None:
        with self.lock:
            if self.proc is not None and self.proc.poll() is None:
                try:
                    self._raw(("quit",), 5.0)
                except Exception:  # noqa: BLE001
                    pass
            self._kill()
            if self._runtime is not None:
                shutil.rmtree(self._runtime)
                self._runtime = None


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
