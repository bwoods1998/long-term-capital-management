"""Where agent-written code runs: never in the House's process, always in a box of its own.

`SailSandbox` gives each agent one Sailbox, forked from a clean image, with no network and no
credential: the House uploads the strategy and the data, runs `runner.py` or `replay.py` there over
Sail's exec API, reads one token-marked line back, and puts the box to sleep (a sleeping box costs
nothing). A fork is a Sail checkpoint of the parent's box restored under the child's name.

`LocalSandbox` runs the same two programs in a subprocess in a private directory. It is for tests
and for a developer's machine; it is a process boundary, not a security boundary, and the House
refuses to use it for real money.
"""

from __future__ import annotations

import json
import os
import queue
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Mapping

from . import replay as replay_module
from . import runner as runner_module
from . import safety as safety_module

KIT_FILES = {"runner.py": runner_module.__file__, "replay.py": replay_module.__file__, "safety.py": safety_module.__file__,
             # The options desk's simulator and the estimates it shares with the House's tape builder.
             "options_replay.py": str(Path(__file__).resolve().parent / "options_replay.py"),
             "options_history.py": str(Path(__file__).resolve().parent / "options_history.py")}
TOOLS_DIR = Path(__file__).resolve().parent / "tools"


def kit_files() -> dict[str, str]:
    """What is placed beside a strategy in its box: the runner, the replay simulator, the safety
    check, and the toolsmith's helper modules (as the package `tools`)."""
    files = dict(KIT_FILES)
    for path in sorted(TOOLS_DIR.glob("*.py")):
        files[f"tools/{path.name}"] = str(path)
    return files
REMOTE_DIR = "/agent"
#: Sail's egress policy is an allowlist and refuses an empty one. `.invalid` is reserved by RFC 2606
#: and never resolves, so a box allowed to reach only this host can reach nothing.
SEALED = ["sealed.invalid"]


class SandboxError(RuntimeError):
    """The box could not run the program (not a strategy error: those come back in the result)."""


class SandboxBusy(SandboxError):
    """Another caller holds this box (a background replay, a probe in hand, a sleep) and this
    caller would not wait for it: nothing ran and nothing was charged. It says nothing about the
    strategy; the caller defers its work to a later tick."""


@dataclass(frozen=True)
class Run:
    result: dict[str, Any]
    seconds: float
    created: bool = False  # a box was created for this run (it costs a creation fee)


def _kit_digest() -> str:
    import hashlib

    h = hashlib.sha256()
    for name, source in sorted(kit_files().items()):
        h.update(name.encode())
        h.update(Path(source).read_bytes())
    return h.hexdigest()[:16]


class LocalSandbox:
    secure = False

    def __init__(self, root: str | Path | None = None, *, python: str | None = None):
        self.root = Path(root) if root else Path(tempfile.mkdtemp(prefix="league-sandbox-"))
        self.python = python or sys.executable
        self.forks: list[tuple[str, str]] = []
        self.retired: list[str] = []

    def _dir(self, agent: str) -> Path:
        path = self.root / agent
        if not path.exists():
            path.mkdir(parents=True)
        wanted = kit_files()
        for name, source in wanted.items():
            target = path / name
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists() or target.read_bytes() != Path(source).read_bytes():
                shutil.copyfile(source, target)
        for stale in (path / "tools").glob("*.py"):
            if f"tools/{stale.name}" not in wanted:
                stale.unlink()  # a tool withdrawn from the repository is withdrawn from every box
        return path

    def _run(self, agent: str, program: str, spec: Mapping[str, Any], marker: str, timeout: float) -> Run:
        directory = self._dir(agent)
        token = secrets.token_hex(16)
        (directory / "spec.json").write_text(json.dumps({**spec, "token": token}), encoding="utf-8")
        started = time.monotonic()
        try:
            done = subprocess.run(
                [self.python, "-E", "-s", program, "spec.json"] if program == "runner.py" else [self.python, "-E", "-s", program, "--spec", "spec.json"],
                cwd=directory, capture_output=True, text=True, timeout=timeout, env={"PATH": os.environ.get("PATH", "")},
            )
        except subprocess.TimeoutExpired:
            return Run({"ok": False, "error": f"timed out after {timeout:.0f}s"}, time.monotonic() - started)
        seconds = time.monotonic() - started
        result = runner_module.parse_result(done.stdout, token, marker)
        if result is None:
            return Run({"ok": False, "error": f"no result line (exit {done.returncode}): {done.stderr[-300:]}"}, seconds)
        return Run(result, seconds)

    def decide(self, agent: str, code: str, ctx: Mapping[str, Any]) -> Run:
        return self._run(agent, "runner.py", {"code": code, "ctx": ctx}, runner_module.MARKER, 30)

    def needs(self, agent: str, code: str, *, keep_awake: bool = False) -> Run:
        return self._run(agent, "runner.py", {"code": code, "mode": "needs"}, runner_module.MARKER, 30)

    def rest(self, agent: str) -> None:
        pass

    def replay(self, agent: str, code: str, params: Mapping[str, Any], tape: Mapping[str, Any], *, stake: float, limits: Mapping[str, Any], timeout: float = 600) -> Run:
        spec = {"code": code, "params": dict(params), "tape": tape, "stake": stake, "limits": dict(limits)}
        return self._run(agent, "replay.py", spec, "REPLAY-RESULT", timeout)

    def fork(self, parent: str, child: str) -> bool:
        source, target = self._dir(parent), self.root / child
        if not target.exists():
            shutil.copytree(source, target)
        self.forks.append((parent, child))
        return True

    def retire(self, agent: str) -> None:
        shutil.rmtree(self.root / agent, ignore_errors=True)
        self.retired.append(agent)

    def sleep_all(self) -> int:
        return 0


class SailSandbox:
    """One Sailbox per agent. `client` is an `ltcm.sailbox.SailboxClient`."""

    secure = True

    def __init__(self, client: Any, state_path: str | Path, *, image_checkpoint: str, name_prefix: str = "league", clock=time.time,
                 background_sleep: bool = False):
        self.client = client
        self.state_path = Path(state_path)
        self.image_checkpoint = image_checkpoint
        self.name_prefix = name_prefix
        self.clock = clock
        self._lock = threading.RLock()
        # Reentrant, so a caller that has claimed a box (`claim`) can run programs in it.
        self._agent_locks: dict[str, Any] = {}
        # How long THIS thread waits for a box another caller holds (`patience`); None waits.
        self._patience = threading.local()
        self._state = self._load()
        # Putting a box to sleep is a Sail call that can take many seconds, and every run ends with
        # one. Measured Sept 22, 2026 with py-spy: the House's tick thread sat in `client.sleep` for
        # a newborn's box across three samples 17 s apart, and ticks alternated 60 s / 210-250 s
        # because every other tick carried a birth. With `background_sleep` the call goes to a
        # small pool instead; it takes the agent's own lock, so a sleep and a run of the same box
        # never overlap, and nothing waits for Sail to finish.
        self._sleeper = ThreadPoolExecutor(max_workers=4, thread_name_prefix="box-sleep") if background_sleep else None
        self._sleeps_queued: set[tuple[str, str]] = set()  # one queued sleep a box is enough: a second would only wait behind it

    # ------------------------------------------------------------------ state
    def _load(self) -> dict[str, Any]:
        try:
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            state = {}
        state.setdefault("boxes", {})
        state.setdefault("kit", {})
        state.setdefault("sealed", {})
        return state

    def _save(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._state, indent=1, sort_keys=True), encoding="utf-8")
        os.chmod(tmp, 0o600)
        os.replace(tmp, self.state_path)

    #: Seconds a Sail call may take before it is abandoned as infrastructure (`SandboxError`, never
    #: the strategy's result). The client's defaults are five minutes for a resume and for each
    #: upload: measured Sept 23, 2026, 05:07Z, a probe's Sail calls hung for about seven minutes
    #: and the House's first tick, waiting for the probe box, for about twelve. An upload gets a
    #: minute plus four seconds a megabyte (a replay's spec carries its whole tape).
    RESUME_TIMEOUT = 120.0
    UPLOAD_TIMEOUT = 60.0
    UPLOAD_SECONDS_PER_MB = 4.0
    #: A checkpoint of a parent's box (a fork) and a box started from a checkpoint (every new box):
    #: the client waits ten and fifteen minutes. Measured on the floor Sept 23, 2026: an agent's
    #: first run, its box's creation included, took 8.7 s at the median and 10.7 s at p90 over 514
    #: agents, and 182 s at the slowest.
    CHECKPOINT_TIMEOUT = 120.0
    CREATE_TIMEOUT = 180.0
    #: How long a background sleep waits for a box another caller holds. The holder is a run,
    #: which puts the box to sleep itself when it ends, so giving up loses nothing; waiting for
    #: ever would hold a pool thread, and the process's exit, behind a hung Sail call.
    SLEEP_WAIT = 60.0
    #: At shutdown, boxes are put to sleep side by side for at most this long; Sail's auto-sleep
    #: is the backstop for the rest.
    SHUTDOWN_SECONDS = 60.0

    def _agent_lock(self, agent: str) -> Any:
        with self._lock:
            return self._agent_locks.setdefault(agent, threading.RLock())

    @contextmanager
    def patience(self, seconds: float | None) -> Iterator[None]:
        """Within this block, a call from this thread waits at most `seconds` for a box another
        caller holds, then raises `SandboxBusy` (the House's tick: it never waits on background
        work). None restores waiting."""
        previous = getattr(self._patience, "seconds", None)
        self._patience.seconds = seconds
        try:
            yield
        finally:
            self._patience.seconds = previous

    @contextmanager
    def claim(self, agent: str, *, wait: float = 0.0) -> Iterator[bool]:
        """Hold `agent`'s box for a block of work (runs inside it reenter), waiting at most `wait`
        seconds for another caller to let go. Yields False, holding nothing, when it could not."""
        lock = self._agent_lock(agent)
        if not lock.acquire(timeout=max(0.0, float(wait))):
            yield False
            return
        try:
            yield True
        finally:
            lock.release()

    @contextmanager
    def _turn(self, agent: str) -> Iterator[None]:
        """The box, for one call: waited for, or refused within this thread's `patience`."""
        lock = self._agent_lock(agent)
        seconds = getattr(self._patience, "seconds", None)
        if seconds is None:
            lock.acquire()
        elif not lock.acquire(timeout=max(0.0, float(seconds))):
            raise SandboxBusy(f"{agent}: its box is in use by other work (waited {float(seconds):g}s); nothing ran")
        try:
            yield
        finally:
            lock.release()

    def busy(self, agent: str) -> bool:
        """Is another caller holding this box right now (a reading, not a reservation)?"""
        lock = self._agent_lock(agent)
        if not lock.acquire(blocking=False):
            return True
        lock.release()
        return False

    def box_of(self, agent: str) -> str | None:
        return self._state["boxes"].get(agent)

    # ------------------------------------------------------------------- boxes
    def _ensure(self, agent: str, *, checkpoint: str | None = None) -> tuple[str, bool]:
        box = self.box_of(agent)
        created = False
        if box is None:
            row = self.client.from_checkpoint(checkpoint or self.image_checkpoint, name=f"{self.name_prefix}-{agent}"[:60],
                                              timeout=self.CREATE_TIMEOUT)
            box = str(row.get("sailbox_id") or row.get("id"))
            created = True
            # No network at all: everything a strategy sees is handed to it as data. The box is
            # recorded only once it is sealed; one that cannot be sealed is destroyed, never used.
            try:
                self.client.set_egress(box, SEALED)
            except Exception as exc:  # noqa: BLE001
                try:
                    self.client.terminate(box)
                except Exception:  # noqa: BLE001
                    pass
                raise SandboxError(f"could not close the network of {agent}'s box: {exc}") from exc
            with self._lock:
                self._state["boxes"][agent] = box
                self._state.setdefault("sealed", {})[box] = True
                self._save()
        else:
            status = str((self.client.get(box) or {}).get("status") or "")
            if status in ("sleeping", "paused", "asleep"):
                self.client.resume(box, timeout=self.RESUME_TIMEOUT)
            elif status in ("terminated", "terminating", "failed", "create_failed"):
                with self._lock:
                    self._state["boxes"].pop(agent, None)
                    self._state["kit"].pop(box, None)
                    self._state.setdefault("sealed", {}).pop(box, None)
                    self._save()
                return self._ensure(agent, checkpoint=checkpoint)
            if not self._state.setdefault("sealed", {}).get(box):
                # A box from before sealing was recorded: seal it again before anything runs in it.
                try:
                    self.client.set_egress(box, SEALED)
                except Exception as exc:  # noqa: BLE001
                    raise SandboxError(f"could not close the network of {agent}'s box: {exc}") from exc
                with self._lock:
                    self._state["sealed"][box] = True
                    self._save()
        digest = _kit_digest()
        if self._state["kit"].get(box) != digest:
            # Each version of the kit gets a directory of its own, and programs run from it: a tool
            # withdrawn from the repository is simply not there, whatever older kits left behind.
            for name, source in kit_files().items():
                self._upload(box, f"{self.kit_dir()}/{name}", Path(source).read_bytes(), mode=0o644)
            with self._lock:
                self._state["kit"][box] = digest
                self._save()
        return box, created

    @staticmethod
    def kit_dir() -> str:
        return f"{REMOTE_DIR}/kit-{_kit_digest()}"

    def _upload(self, box: str, path: str, content: bytes, *, mode: int) -> None:
        timeout = self.UPLOAD_TIMEOUT + self.UPLOAD_SECONDS_PER_MB * len(content) / 1e6
        self.client.upload(box, path, content, mode=mode, timeout=timeout)

    def _run(self, agent: str, command: str, spec: Mapping[str, Any], marker: str, timeout: int, *, keep_awake: bool = False) -> Run:
        with self._turn(agent):
            started = time.monotonic()
            try:
                box, created = self._ensure(agent)
                token = secrets.token_hex(16)
                self._upload(box, f"{self.kit_dir()}/spec.json", json.dumps({**spec, "token": token}).encode("utf-8"), mode=0o600)
                done = self.client.exec(box, ["sh", "-c", f"cd {self.kit_dir()} && timeout {timeout} python3 -E -s {command}"], timeout=timeout + 30)
            except SandboxError:
                raise
            except Exception as exc:  # noqa: BLE001 - the Sail API failing is not the strategy failing
                raise SandboxError(f"{agent}: {type(exc).__name__}: {str(exc)[:300]}") from exc
            finally:
                if not keep_awake:
                    self._sleep(agent)
            seconds = time.monotonic() - started
            result = runner_module.parse_result(done.stdout, token, marker)
            if result is None:
                result = {"ok": False, "error": f"no result line (exit {done.return_code}): {str(done.stderr)[-300:]}"}
            return Run(result, seconds, created)

    def _sleep(self, agent: str) -> None:
        box = self.box_of(agent)
        if not box:
            return
        if self._sleeper is None:
            self._sleep_box(box)
            return
        with self._lock:
            if (agent, box) in self._sleeps_queued:
                return
            self._sleeps_queued.add((agent, box))
        try:
            self._sleeper.submit(self._sleep_later, agent, box)
        except RuntimeError:  # the pool is shut down: sleep here instead
            with self._lock:
                self._sleeps_queued.discard((agent, box))
            self._sleep_box(box)

    def _sleep_later(self, agent: str, box: str) -> None:
        with self.claim(agent, wait=self.SLEEP_WAIT) as held:
            # Until now any run of this box that ended was followed by this sleep, so its own was not
            # queued; from here on, a run that ends queues one of its own.
            with self._lock:
                self._sleeps_queued.discard((agent, box))
            # Not held: a run has the box, and puts it to sleep itself when it ends.
            if held and self.box_of(agent) == box:  # retired or replaced meanwhile: nothing to put to sleep
                self._sleep_box(box)

    def _sleep_box(self, box: str) -> None:
        try:
            self.client.sleep(box)
        except Exception:  # noqa: BLE001 - auto-sleep is the backstop
            pass

    def drain(self, timeout: float | None = None) -> None:
        """Wait for background sleeps (tests, shutdown)."""
        if self._sleeper is not None:
            self._sleeper.shutdown(wait=True)
            self._sleeper = ThreadPoolExecutor(max_workers=4, thread_name_prefix="box-sleep")

    def decide(self, agent: str, code: str, ctx: Mapping[str, Any]) -> Run:
        return self._run(agent, "runner.py spec.json", {"code": code, "ctx": ctx}, runner_module.MARKER, 30)

    def needs(self, agent: str, code: str, *, keep_awake: bool = False) -> Run:
        """`keep_awake` leaves the box running for the next call (a founding reads twelve files in a
        row, and most of each call is the box waking); the caller then calls `rest`."""
        return self._run(agent, "runner.py spec.json", {"code": code, "mode": "needs"}, runner_module.MARKER, 30, keep_awake=keep_awake)

    def rest(self, agent: str) -> None:
        self._sleep(agent)

    def replay(self, agent: str, code: str, params: Mapping[str, Any], tape: Mapping[str, Any], *, stake: float, limits: Mapping[str, Any], timeout: float = 600) -> Run:
        spec = {"code": code, "params": dict(params), "tape": tape, "stake": stake, "limits": dict(limits)}
        return self._run(agent, "replay.py --spec spec.json", spec, "REPLAY-RESULT", int(timeout))

    def fork(self, parent: str, child: str) -> bool:
        """A child is its parent's box, checkpointed and restored under a new name: same disk,
        same memory. When the parent has no box yet the child simply starts from the clean image."""
        with self._turn(parent):
            box = self.box_of(parent)
            if box is None or self.box_of(child) is not None:
                return False
            try:
                status = str((self.client.get(box) or {}).get("status") or "")
                if status in ("sleeping", "paused", "asleep"):
                    self.client.resume(box, timeout=self.RESUME_TIMEOUT)
                row = self.client.checkpoint(box, name=f"{self.name_prefix}-fork-{child}"[:60], ttl_seconds=86400,
                                             timeout=self.CHECKPOINT_TIMEOUT)
                self._ensure(child, checkpoint=str(row.get("checkpoint_id")))
                return True
            except SandboxError:
                raise
            except Exception as exc:  # noqa: BLE001
                raise SandboxError(f"fork {parent} -> {child}: {type(exc).__name__}: {str(exc)[:300]}") from exc
            finally:
                self._sleep(parent)
                self._sleep(child)

    def retire(self, agent: str) -> None:
        """Death is a platform fact: the box is terminated, not merely ignored."""
        box = self.box_of(agent)
        if box is None:
            return
        try:
            self.client.terminate(box)
        except Exception:  # noqa: BLE001 - a box already gone is a box gone
            pass
        with self._lock:
            self._state["boxes"].pop(agent, None)
            self._state["kit"].pop(box, None)
            self._save()

    def sleep_all(self, *, seconds: float | None = None) -> int:
        """At shutdown: every box, side by side, for at most `seconds` (SHUTDOWN_SECONDS).

        Sleeps still queued in the pool are dropped and done here instead. A box another caller
        holds -- a background replay hung in a Sail call -- is skipped: the run that holds it puts
        it to sleep when it ends, and Sail's auto-sleep is the backstop. Until Sept 23, 2026 this
        waited for the pool, and a queued sleep of a box whose run was hung held the House's exit
        on TERM for as long as the run."""
        if self._sleeper is not None:
            self._sleeper.shutdown(wait=False, cancel_futures=True)
        with self._lock:
            self._sleeps_queued.clear()
        agents = list(self._state["boxes"])
        work: "queue.Queue[str]" = queue.Queue()
        for agent in agents:
            work.put(agent)

        def worker() -> None:
            while True:
                try:
                    agent = work.get_nowait()
                except queue.Empty:
                    return
                with self.claim(agent, wait=0.5) as held:
                    box = self.box_of(agent)
                    if held and box:
                        self._sleep_box(box)

        threads = [threading.Thread(target=worker, name="box-sleep-all", daemon=True) for _ in range(min(8, len(agents)))]
        for thread in threads:
            thread.start()
        deadline = time.monotonic() + (self.SHUTDOWN_SECONDS if seconds is None else float(seconds))
        for thread in threads:
            thread.join(max(0.0, deadline - time.monotonic()))
        return len(agents)
