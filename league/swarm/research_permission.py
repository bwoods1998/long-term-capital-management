"""Host-only ordinary research permission; Gate work and free readback are independent.

The operator publishes an atomic deny flag before waiting in ``operator_lock``;
permission increases require that lock. Ordinary paid calls hold a shared lock
through the call; a host exclusivity check takes the exclusive lock, so
it cannot mistake an already dispatched ordinary call for drained work. This covers
the reviewed stock routes only, never other processes using the same credentials.
"""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
from functools import wraps
from typing import Any, Iterator

FLAG = "research-dispatch.json"
LOCK = "research-dispatch.lock"
GATE_ROLES = ("review", "audit")
WIRED = ("research_permission.py", "models.py", "pool.py", "loop.py")


class ResearchDispatchDenied(RuntimeError):
    pass


def is_denial(error: BaseException) -> bool:
    """Drivers may wrap a permission error; it still proves no replacement dispatch."""
    seen: set[int] = set()
    while id(error) not in seen:
        seen.add(id(error))
        if isinstance(error, ResearchDispatchDenied):
            return True
        following = error.__cause__
        if following is None:
            return False
        error = following
    return False


def protected(method: Any) -> Any:
    """Mark loaded entry points so an old in-memory actor cannot claim new source wiring."""
    method.__research_permission_schema__ = 1
    return method


def runtime_wired(router: Any, pool: Any) -> bool:
    routes = ((router, ("_sail_dispatch", "ask", "_ask_claude", "_ask_openai", "_claude_turn_once")),
              (pool, ("_start_box", "run_batch")))
    for actor, names in routes:
        for name in names:
            seen = getattr(getattr(actor, name, None), "__research_permission_schema__", None)
            if type(seen) is not int or seen != 1:
                return False
    return True


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("duplicate permission field")
        out[key] = value
    return out


def _private_file(fd: int) -> None:
    seen = os.fstat(fd)
    if not stat.S_ISREG(seen.st_mode) or seen.st_uid != os.geteuid() or stat.S_IMODE(seen.st_mode) & 0o077:
        raise ResearchDispatchDenied("research permission file is not owner-private")


def _read(root: str | Path | None) -> tuple[bool, str | None, str]:
    if root is None:
        return True, None, "legacy absent root"
    try:
        fd = os.open(Path(root) / FLAG, os.O_RDONLY | os.O_NOFOLLOW)
    except FileNotFoundError:
        return True, None, "legacy absent flag"
    except OSError:
        return False, None, "unreadable permission"
    try:
        _private_file(fd)
        with os.fdopen(fd, "rb") as stream:
            fd = -1
            raw = stream.read(4097)
        if len(raw) > 4096:
            raise ValueError("permission too large")
        value = json.loads(raw, object_pairs_hook=_object)
        if (not isinstance(value, dict) or set(value) != {"schema", "ordinary_allowed"}
                or type(value["schema"]) is not int or value["schema"] != 1
                or type(value["ordinary_allowed"]) is not bool):
            raise ValueError("invalid permission")
        return value["ordinary_allowed"], hashlib.sha256(raw).hexdigest(), "explicit owner flag"
    except (OSError, ValueError, UnicodeError, ResearchDispatchDenied):
        return False, None, "malformed permission"
    finally:
        if fd >= 0:
            os.close(fd)


def ordinary_allowed(root: str | Path | None) -> bool:
    """Fresh scheduler hint; the paid boundary checks again under its dispatch lock."""
    return _read(root)[0]


def status(root: str | Path | None) -> dict[str, Any]:
    allowed, identity, why = _read(root)
    return {"ordinary_allowed": allowed, "permission_sha256": identity, "basis": why,
            "loaded_wiring_sha256": LOADED_WIRING_SHA}


def require(root: str | Path | None, *, role: str | None = None, kind: str | None = None) -> None:
    if kind == "gate" or kind is None and role in GATE_ROLES:
        return
    allowed, _, why = _read(root)
    if not allowed:
        raise ResearchDispatchDenied(f"ordinary research dispatch is fenced ({why})")


@contextmanager
def _lock(root: str | Path, *, exclusive: bool, nonblocking: bool = False) -> Iterator[dict[str, Any]]:
    try:
        fd = os.open(Path(root) / LOCK, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        _private_file(fd)
        fcntl.flock(fd, (fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH) | (fcntl.LOCK_NB if nonblocking else 0))
    except OSError:
        if "fd" in locals():
            os.close(fd)
        raise ResearchDispatchDenied("ordinary research lock is busy or unreadable") from None
    except ResearchDispatchDenied:
        if "fd" in locals():
            os.close(fd)
        raise
    try:
        identity = os.fstat(fd)
        yield {"state_root": str(Path(root).resolve()), "device": identity.st_dev, "inode": identity.st_ino}
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


@contextmanager
def dispatch(root: str | Path | None, *, role: str | None = None, kind: str | None = None) -> Iterator[None]:
    if kind == "gate" or kind is None and role in GATE_ROLES or root is None:
        require(root, role=role, kind=kind)
        yield
        return
    # An installed deny must not wait behind a host admission or add new shared
    # lock contenders while the operator drains previously admitted work.
    require(root, role=role, kind=kind)
    with _lock(root, exclusive=False):
        require(root, role=role, kind=kind)
        yield


class GymClient:
    """Guard each driver exec/upload retry; download and stop/cleanup remain usable."""
    def __init__(self, client: Any, root: str | Path, kind: str):
        self._client, self._root, self._kind = client, root, kind

    def __getattr__(self, name: str) -> Any:
        value = getattr(self._client, name)
        if name not in ("exec", "upload", "resume", "from_checkpoint") or not callable(value):
            return value
        @wraps(value)
        def guarded(*args: Any, **kwargs: Any) -> Any:
            with dispatch(self._root, kind=self._kind):
                return value(*args, **kwargs)
        return guarded


def wiring_sha() -> str:
    """Exact source transport identity; this is not proof those bytes run remotely."""
    here = Path(__file__).resolve().parent
    values = {name: hashlib.sha256((here / name).read_bytes()).hexdigest() for name in WIRED}
    return hashlib.sha256(json.dumps(values, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@contextmanager
def operator_lock(root: str | Path) -> Iterator[None]:
    """Drain/prove restriction, or serialize a permission increase; no provider calls.

    Publish an atomic deny before waiting here, so new ordinary work cannot keep
    this lock busy forever. Never claim drain until this exclusive lock succeeds.
    """
    with _lock(root, exclusive=True):
        yield


@contextmanager
def fenced_host_scope(root: str | Path, *, permission_sha: str, code_sha: str) -> Iterator[dict[str, Any]]:
    """Fresh, nonblocking explicit-deny attestation held through host paid admission.

    The operator must independently verify the active legacy release and all other
    research writers. Missing flags, stale/tampered bytes or in-flight patched calls
    never establish an exclusive scope. This neither releases nor values old bills.
    """
    if any(not isinstance(x, str) or len(x) != 64 or any(c not in "0123456789abcdef" for c in x)
           for x in (permission_sha, code_sha)):
        raise ResearchDispatchDenied("research fence identity is invalid")
    with _lock(root, exclusive=True, nonblocking=True) as lock_resource:
        allowed, seen_sha, why = _read(root)
        if (allowed or seen_sha is None or seen_sha != permission_sha
                or LOADED_WIRING_SHA != code_sha or wiring_sha() != code_sha):
            raise ResearchDispatchDenied("explicit research fence does not match its reviewed identity")
        receipt = {"schema": 1, "ordinary_allowed": False, "permission_sha256": seen_sha,
                   "wiring_sha256": code_sha, "drain": "patched ordinary dispatch lock exclusive",
                   "lock_resource": lock_resource,
                   "scope": "reviewed stock research routes; external writers require independent proof"}
        canonical = json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode()
        yield {**receipt, "receipt_sha256": hashlib.sha256(canonical).hexdigest()}


# Captured at import, not recomputed from files after a process has already loaded another release.
LOADED_WIRING_SHA = wiring_sha()
