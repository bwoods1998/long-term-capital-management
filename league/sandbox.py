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
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from . import replay as replay_module
from . import runner as runner_module
from . import safety as safety_module

KIT_FILES = {"runner.py": runner_module.__file__, "replay.py": replay_module.__file__, "safety.py": safety_module.__file__}
REMOTE_DIR = "/agent"
#: Sail's egress policy is an allowlist and refuses an empty one. `.invalid` is reserved by RFC 2606
#: and never resolves, so a box allowed to reach only this host can reach nothing.
SEALED = ["sealed.invalid"]


class SandboxError(RuntimeError):
    """The box could not run the program (not a strategy error: those come back in the result)."""


@dataclass(frozen=True)
class Run:
    result: dict[str, Any]
    seconds: float
    created: bool = False  # a box was created for this run (it costs a creation fee)


def _kit_digest() -> str:
    import hashlib

    h = hashlib.sha256()
    for name in sorted(KIT_FILES):
        h.update(Path(KIT_FILES[name]).read_bytes())
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
            for name, source in KIT_FILES.items():
                shutil.copyfile(source, path / name)
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

    def needs(self, agent: str, code: str) -> Run:
        return self._run(agent, "runner.py", {"code": code, "mode": "needs"}, runner_module.MARKER, 30)

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

    def __init__(self, client: Any, state_path: str | Path, *, image_checkpoint: str, name_prefix: str = "league", clock=time.time):
        self.client = client
        self.state_path = Path(state_path)
        self.image_checkpoint = image_checkpoint
        self.name_prefix = name_prefix
        self.clock = clock
        self._lock = threading.RLock()
        self._agent_locks: dict[str, threading.Lock] = {}
        self._state = self._load()

    # ------------------------------------------------------------------ state
    def _load(self) -> dict[str, Any]:
        try:
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            state = {}
        state.setdefault("boxes", {})
        state.setdefault("kit", {})
        return state

    def _save(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._state, indent=1, sort_keys=True), encoding="utf-8")
        os.chmod(tmp, 0o600)
        os.replace(tmp, self.state_path)

    def _agent_lock(self, agent: str) -> threading.Lock:
        with self._lock:
            return self._agent_locks.setdefault(agent, threading.Lock())

    def box_of(self, agent: str) -> str | None:
        return self._state["boxes"].get(agent)

    # ------------------------------------------------------------------- boxes
    def _ensure(self, agent: str, *, checkpoint: str | None = None) -> tuple[str, bool]:
        box = self.box_of(agent)
        created = False
        if box is None:
            row = self.client.from_checkpoint(checkpoint or self.image_checkpoint, name=f"{self.name_prefix}-{agent}"[:60])
            box = str(row.get("sailbox_id") or row.get("id"))
            created = True
            with self._lock:
                self._state["boxes"][agent] = box
                self._save()
            # No network at all: everything a strategy sees is handed to it as data.
            try:
                self.client.set_egress(box, SEALED)
            except Exception as exc:  # noqa: BLE001
                raise SandboxError(f"could not close the network of {agent}'s box: {exc}") from exc
        else:
            status = str((self.client.get(box) or {}).get("status") or "")
            if status in ("sleeping", "paused", "asleep"):
                self.client.resume(box)
            elif status in ("terminated", "terminating", "failed", "create_failed"):
                with self._lock:
                    self._state["boxes"].pop(agent, None)
                    self._state["kit"].pop(box, None)
                    self._save()
                return self._ensure(agent, checkpoint=checkpoint)
        digest = _kit_digest()
        if self._state["kit"].get(box) != digest:
            for name, source in KIT_FILES.items():
                self.client.upload(box, f"{REMOTE_DIR}/{name}", Path(source).read_bytes(), mode=0o644)
            with self._lock:
                self._state["kit"][box] = digest
                self._save()
        return box, created

    def _run(self, agent: str, command: str, spec: Mapping[str, Any], marker: str, timeout: int) -> Run:
        with self._agent_lock(agent):
            started = time.monotonic()
            try:
                box, created = self._ensure(agent)
                token = secrets.token_hex(16)
                self.client.upload(box, f"{REMOTE_DIR}/spec.json", json.dumps({**spec, "token": token}).encode("utf-8"), mode=0o600)
                done = self.client.exec(box, ["sh", "-c", f"cd {REMOTE_DIR} && timeout {timeout} python3 -E -s {command}"], timeout=timeout + 30)
            except SandboxError:
                raise
            except Exception as exc:  # noqa: BLE001 - the Sail API failing is not the strategy failing
                raise SandboxError(f"{agent}: {type(exc).__name__}: {str(exc)[:300]}") from exc
            finally:
                self._sleep(agent)
            seconds = time.monotonic() - started
            result = runner_module.parse_result(done.stdout, token, marker)
            if result is None:
                result = {"ok": False, "error": f"no result line (exit {done.return_code}): {str(done.stderr)[-300:]}"}
            return Run(result, seconds, created)

    def _sleep(self, agent: str) -> None:
        box = self.box_of(agent)
        if box:
            try:
                self.client.sleep(box)
            except Exception:  # noqa: BLE001 - auto-sleep is the backstop
                pass

    def decide(self, agent: str, code: str, ctx: Mapping[str, Any]) -> Run:
        return self._run(agent, "runner.py spec.json", {"code": code, "ctx": ctx}, runner_module.MARKER, 30)

    def needs(self, agent: str, code: str) -> Run:
        return self._run(agent, "runner.py spec.json", {"code": code, "mode": "needs"}, runner_module.MARKER, 30)

    def replay(self, agent: str, code: str, params: Mapping[str, Any], tape: Mapping[str, Any], *, stake: float, limits: Mapping[str, Any], timeout: float = 600) -> Run:
        spec = {"code": code, "params": dict(params), "tape": tape, "stake": stake, "limits": dict(limits)}
        return self._run(agent, "replay.py --spec spec.json", spec, "REPLAY-RESULT", int(timeout))

    def fork(self, parent: str, child: str) -> bool:
        """A child is its parent's box, checkpointed and restored under a new name: same disk,
        same memory. When the parent has no box yet the child simply starts from the clean image."""
        with self._agent_lock(parent):
            box = self.box_of(parent)
            if box is None or self.box_of(child) is not None:
                return False
            try:
                status = str((self.client.get(box) or {}).get("status") or "")
                if status in ("sleeping", "paused", "asleep"):
                    self.client.resume(box)
                row = self.client.checkpoint(box, name=f"{self.name_prefix}-fork-{child}"[:60], ttl_seconds=86400)
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

    def sleep_all(self) -> int:
        count = 0
        for agent in list(self._state["boxes"]):
            self._sleep(agent)
            count += 1
        return count
