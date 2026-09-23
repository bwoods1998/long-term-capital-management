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

import gzip
import hashlib
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


class TapeMissing(SandboxError):
    """The box does not hold the tape this digest names: call again with the tape itself."""


class TapeRefused(ValueError):
    """A tape that may not enter a batch box: it reaches into the sealed holdout, or it is not the
    tape its digest names. Unavailable data, never a result against a strategy."""


#: Where a box keeps the development tapes a batch reads, one gzipped file per digest, and where
#: a batch leaves its full results for the House to download.
TAPE_DIR = f"{REMOTE_DIR}/tapes"
RESULT_DIR = f"{REMOTE_DIR}/results"


def tape_bytes(tape: Any) -> bytes:
    """The canonical JSON of a tape: the bytes `league.experiments.Archive` hashes, so a tape's digest
    here is its artifact id there."""
    return json.dumps(tape, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def tape_digest(tape: Any) -> str:
    return hashlib.sha256(tape_bytes(tape)).hexdigest()


def tape_span(tape: Any) -> tuple[float, float] | None:
    """(first, last) moment any data on the tape is stamped: its steps, the bars before and inside
    them, what it observes, its option features and its feeds."""
    from .replay import _parse_ts

    stamps: list[float] = []

    def add(value: Any) -> None:
        stamp = _parse_ts(value)
        if stamp is not None:
            stamps.append(stamp)

    def rows(series: Any) -> None:
        if isinstance(series, dict):
            for bars in series.values():
                if isinstance(bars, (list, tuple)):
                    for bar in bars:
                        if isinstance(bar, dict):
                            add(bar.get("t"))

    if not isinstance(tape, dict):
        return None
    for step in tape.get("steps") or []:
        if isinstance(step, dict):
            add(step.get("t"))
            rows(step.get("history_bars"))
    for name in ("warmup_bars", "observed_bars", "options_features"):
        rows(tape.get(name))
    feeds = tape.get("feeds")
    if isinstance(feeds, dict):
        for keys in feeds.values():
            rows(keys)
    return (min(stamps), max(stamps)) if stamps else None


def holdout_problem(tape: Any, window: tuple[str, str] | None = None) -> str | None:
    """Why this tape may not enter a batch box, or None. A batch evaluates development data only:
    a tape any of whose data falls in, or spans, the sealed holdout (`deep_replay.HOLDOUT`, a fixed
    [start, end) of UTC days) is refused whole. The holdout is served by `HoldoutSeal` alone."""
    from datetime import datetime, timezone

    if window is None:
        from .deep_replay import HOLDOUT as window  # noqa: N811
    def day(text: Any) -> float:
        return datetime.fromisoformat(str(text)[:10]).replace(tzinfo=timezone.utc).timestamp()

    start, end = day(window[0]), day(window[1])
    sealed = f"the sealed holdout [{window[0]}, {window[1]}); a batch evaluates development data only"
    source = tape.get("source") if isinstance(tape, dict) else None
    covers = source.get("window") if isinstance(source, dict) else None
    if isinstance(covers, (list, tuple)) and len(covers) == 2:  # the [start, end) days it was built over
        try:
            if day(covers[0]) < end and day(covers[1]) > start:
                return f"the tape was built over [{covers[0]}, {covers[1]}), which reaches into {sealed}"
        except ValueError:
            return "the tape's window is not a pair of days"
    span = tape_span(tape)
    if span is None:
        return "the tape carries no dated data"
    first, last = span
    if first < end and last >= start:
        return (f"the tape's data runs {datetime.fromtimestamp(first, timezone.utc):%Y-%m-%d %H:%M} to "
                f"{datetime.fromtimestamp(last, timezone.utc):%Y-%m-%d %H:%M} and reaches into {sealed}")
    return None


def _checked_tape(tape: Any, digest: str, holdout: tuple[str, str] | None) -> bytes:
    """The gzipped canonical bytes of a tape that may enter a batch box under this digest."""
    problem = holdout_problem(tape, holdout)
    if problem:
        raise TapeRefused(f"unsupported input: {problem}")
    raw = tape_bytes(tape)
    if hashlib.sha256(raw).hexdigest() != digest:
        raise TapeRefused("unsupported input: the tape is not the one its digest names")
    return gzip.compress(raw, 6, mtime=0)


def _digest_of(value: Any) -> str:
    text = str(value or "")
    if len(text) != 64 or any(c not in "0123456789abcdef" for c in text):
        raise SandboxError("a tape digest is 64 lowercase hex characters")
    return text


def _batch_spec(candidates: Any, *, token: str, tape_path: str, digest: str, stake: float, limits: Mapping[str, Any],
                oos_fraction: float, max_decide_seconds: float, budget_seconds: float | None, result_path: str,
                workers: int | None, candidate_seconds: float | None) -> dict[str, Any]:
    spec = {"token": token, "candidates": [dict(c) if isinstance(c, Mapping) else c for c in candidates], "tape_path": tape_path,
            "tape_digest": digest, "stake": stake, "limits": dict(limits), "oos_fraction": oos_fraction,
            "max_decide_seconds": max_decide_seconds, "result_path": result_path}
    for name, value in (("budget_seconds", budget_seconds), ("workers", workers), ("candidate_seconds", candidate_seconds)):
        if value is not None:
            spec[name] = value
    return spec


def _batch_result(body: Mapping[str, Any], seconds: float, uploaded: bool) -> dict[str, Any]:
    """`Run.result` of a batch: the results, in the candidates' order, and how the run went."""
    return {"results": body["results"], "seconds": seconds, "evaluated": int(body.get("evaluated") or 0),
            "box_seconds": body.get("seconds"), "load_seconds": body.get("load_seconds"), "workers": body.get("workers"),
            "uploaded": uploaded}


def _batch_answer(summary: dict[str, Any] | None, fetch: Any, candidates: Any, where: str) -> dict[str, Any]:
    """The batch's results from its summary line and the result file `fetch()` returns (the path the
    spec named, never one the box reports). A missing tape is `TapeMissing`; anything else wrong is
    the box's failure (`SandboxError`), never a strategy's."""
    if summary is None:
        raise SandboxError(f"the batch printed no result line ({where})")
    if summary.get("tape_missing"):
        raise TapeMissing(str(summary.get("error") or "tape missing"))
    if not summary.get("ok"):
        raise SandboxError(f"the batch failed: {str(summary.get('error'))[:300]}")
    raw = fetch()
    if hashlib.sha256(raw).hexdigest() != summary.get("sha256"):
        raise SandboxError("the batch's result file is not the one it reported")
    body = json.loads(gzip.decompress(raw))
    results = body.get("results") if isinstance(body, dict) else None
    ids = [c.get("id") if isinstance(c, Mapping) else None for c in candidates]
    if not isinstance(results, list) or [r.get("id") if isinstance(r, dict) else None for r in results] != ids:
        raise SandboxError("the batch answered for other candidates than it was given")
    return body


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

    def replay_batch(self, box_key: str, candidates: list[dict], tape: Mapping[str, Any] | None, *, tape_digest: str,
                     stake: float, limits: Mapping[str, Any], timeout: float = 600, oos_fraction: float = 0.34,
                     max_decide_seconds: float = 5.0, budget_seconds: float | None = None, workers: int | None = None,
                     candidate_seconds: float | None = None, keep_awake: bool = False,
                     holdout: tuple[str, str] | None = None) -> Run:
        """`SailSandbox.replay_batch` in a subprocess: the tape is kept in `<root>/<box_key>/tapes`."""
        digest = _digest_of(tape_digest)
        packed = None if tape is None else _checked_tape(tape, digest, holdout)
        directory = self._dir(box_key)
        path = directory / "tapes" / f"{digest}.json.gz"
        uploaded = False
        if not path.exists():
            if packed is None:
                raise TapeMissing(f"{box_key} holds no tape {digest[:12]}")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.with_suffix(".tmp").write_bytes(packed)
            os.replace(path.with_suffix(".tmp"), path)
            uploaded = True
        token = secrets.token_hex(16)
        name = f"batch-{token[:12]}.json"
        result_path = directory / "results" / f"{token}.json.gz"
        spec = _batch_spec(candidates, token=token, tape_path=str(path), digest=digest, stake=stake, limits=limits,
                           oos_fraction=oos_fraction, max_decide_seconds=max_decide_seconds,
                           budget_seconds=budget_seconds if budget_seconds is not None else max(10.0, float(timeout) - 30.0),
                           result_path=str(result_path), workers=workers, candidate_seconds=candidate_seconds)
        (directory / name).write_text(json.dumps(spec), encoding="utf-8")
        started = time.monotonic()
        try:
            done = subprocess.run([self.python, "-E", "-s", "replay.py", "--batch", name], cwd=directory, capture_output=True,
                                  text=True, timeout=timeout, env={"PATH": os.environ.get("PATH", "")})
        except subprocess.TimeoutExpired as exc:
            raise SandboxError(f"{box_key}: the batch timed out after {timeout:.0f}s") from exc
        finally:
            (directory / name).unlink(missing_ok=True)
        seconds = time.monotonic() - started
        summary = replay_module.parse_result(done.stdout, token)
        if summary is not None and summary.get("tape_missing"):
            path.unlink(missing_ok=True)
        try:
            body = _batch_answer(summary, result_path.read_bytes, candidates, f"exit {done.returncode}: {done.stderr[-300:]}")
        finally:
            result_path.unlink(missing_ok=True)
        return Run(_batch_result(body, seconds, uploaded), seconds)

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
        state.setdefault("tapes", {})  # box -> {tape digest: when it was uploaded}
        state.setdefault("bound", {})  # box key -> a box made elsewhere (the lab box): never terminated here
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
    #: A batch's result file (`replay_batch`): gzipped JSON, a few hundred kilobytes at most.
    DOWNLOAD_TIMEOUT = 120.0
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

    def bind(self, box_key: str, box_id: str) -> None:
        """Adopt a box made elsewhere under `box_key`: the lab box, which `scripts/lab_box.py` creates
        larger than an agent's. Its seal is not taken on trust: this state has not recorded it, so
        `_ensure` closes its network again before anything runs there, exactly as for a box from
        before sealing. `retire` never terminates a bound box; it only forgets it."""
        with self._lock:
            if self._state["boxes"].get(box_key) == box_id and self._state["bound"].get(box_key) == box_id:
                return
            old = self._state["boxes"].get(box_key)
            if old and old != box_id:
                for table in ("kit", "sealed", "tapes"):
                    self._state[table].pop(old, None)
            self._state["boxes"][box_key] = box_id
            self._state["bound"][box_key] = box_id
            for table in ("kit", "sealed", "tapes"):
                self._state[table].pop(box_id, None)
            self._save()

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
                    self._state.setdefault("tapes", {}).pop(box, None)
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
        """Death is a platform fact: the box is terminated, not merely ignored. (A bound box -- the
        lab's -- belongs to whoever made it, and is only forgotten.)"""
        box = self.box_of(agent)
        if box is None:
            return
        if self._state["bound"].get(agent) != box:
            try:
                self.client.terminate(box)
            except Exception:  # noqa: BLE001 - a box already gone is a box gone
                pass
        with self._lock:
            self._state["boxes"].pop(agent, None)
            self._state["kit"].pop(box, None)
            self._state["tapes"].pop(box, None)
            self._state["bound"].pop(agent, None)
            self._save()

    def replay_batch(self, box_key: str, candidates: list[dict], tape: Mapping[str, Any] | None, *, tape_digest: str,
                     stake: float, limits: Mapping[str, Any], timeout: float = 600, oos_fraction: float = 0.34,
                     max_decide_seconds: float = 5.0, budget_seconds: float | None = None, workers: int | None = None,
                     candidate_seconds: float | None = None, keep_awake: bool = False,
                     holdout: tuple[str, str] | None = None) -> Run:
        """Replay many candidates over one tape in the sealed box `box_key` (`replay.run_batch`).

        The tape is uploaded once per box, gzipped, under its digest (`tape_digest`, the SHA-256 of
        its canonical JSON, checked here and again in the box), and reused: pass `tape=None` to reuse
        it. A box that does not hold it raises `TapeMissing`, and the caller passes the tape. A tape
        that reaches into the sealed holdout is refused (`TapeRefused`) before anything is sent: a
        batch box sees development data only. The box is sealed like every agent's (`_ensure`).

        `Run.result` is `{"results": [...], "seconds", "evaluated", ...}`: one result per candidate,
        in order, each exactly what a single replay of it returns, plus its `id`. A failure of the
        box or of Sail raises `SandboxError`; it is never a candidate's result. The batch answers
        within `budget_seconds` (by default the timeout less half a minute): candidates it did not
        reach come back `not evaluated: batch budget`. `keep_awake` leaves the box running for the
        next batch (its own auto-sleep is the backstop; `rest` puts it to sleep).

        The box is held like any other (`_turn`): within this thread's `patience` a batch box that
        another caller holds raises `SandboxBusy` (nothing ran), and every Sail call carries the
        tighter timeouts (`_upload`, `DOWNLOAD_TIMEOUT`)."""
        digest = _digest_of(tape_digest)
        packed = None if tape is None else _checked_tape(tape, digest, holdout)
        with self._turn(box_key):
            started = time.monotonic()
            uploaded = False
            try:
                box, created = self._ensure(box_key)
                path = f"{TAPE_DIR}/{digest}.json.gz"
                if digest not in self._state["tapes"].get(box, {}):
                    if packed is None:
                        raise TapeMissing(f"{box_key} holds no tape {digest[:12]}")
                    self._upload(box, path, packed, mode=0o644)
                    uploaded = True
                    with self._lock:
                        self._state["tapes"].setdefault(box, {})[digest] = self.clock()
                        self._save()
                token = secrets.token_hex(16)
                name = f"batch-{token[:12]}.json"
                result_path = f"{RESULT_DIR}/{token}.json.gz"
                spec = _batch_spec(candidates, token=token, tape_path=path, digest=digest, stake=stake, limits=limits,
                                   oos_fraction=oos_fraction, max_decide_seconds=max_decide_seconds,
                                   budget_seconds=budget_seconds if budget_seconds is not None else max(10.0, float(timeout) - 30.0),
                                   result_path=result_path, workers=workers, candidate_seconds=candidate_seconds)
                self._upload(box, f"{self.kit_dir()}/{name}", json.dumps(spec).encode("utf-8"), mode=0o600)
                # Old result files (a batch whose answer was never collected) go first; then the batch.
                command = (f"find {RESULT_DIR} -name '*.json.gz' -mmin +60 -delete 2>/dev/null; cd {self.kit_dir()} && "
                           f"timeout {int(timeout)} python3 -E -s replay.py --batch {name}; rm -f {name}")
                done = self.client.exec(box, ["sh", "-c", command], timeout=int(timeout) + 30)
                summary = replay_module.parse_result(done.stdout, token)
                if summary is not None and summary.get("tape_missing"):
                    with self._lock:
                        self._state["tapes"].get(box, {}).pop(digest, None)
                        self._save()
                body = _batch_answer(summary, lambda: self.client.download(box, result_path, timeout=self.DOWNLOAD_TIMEOUT), candidates,
                                     f"exit {done.return_code}: {str(done.stderr)[-300:]}")
            except (SandboxError, TapeRefused):
                raise
            except Exception as exc:  # noqa: BLE001 - the Sail API failing is not the strategies failing
                raise SandboxError(f"{box_key}: {type(exc).__name__}: {str(exc)[:300]}") from exc
            finally:
                if not keep_awake:
                    self._sleep(box_key)
            seconds = time.monotonic() - started
            return Run(_batch_result(body, seconds, uploaded), seconds, created)

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
