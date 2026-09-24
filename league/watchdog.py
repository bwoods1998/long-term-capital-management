"""The in-box watchdog: which release of the code runs the House, and how a new one earns it.

Until now a deploy untarred the working tree over the running code and restarted the loop: a bad
release was live the moment it landed, and the way back was a human. This module makes a deploy
a staged thing with a way back that needs nobody:

    <base>/releases/<id>/    a full code tree (league/, ltcm/, scripts/ ...), never edited again
    <base>/current           symlink -> releases/<id>: what the supervisor loop starts
    <base>/previous          symlink -> releases/<id>: what `current` was before the last promotion
    <base>/state/            the House's real state directory (never touched by a canary)
    <base>/canary/<run>/     a canary's throwaway state, a fresh one for every deploy
    <base>/deploys.jsonl     append-only: every stage, reading, verdict and reason, with its time

`Watchdog.deploy` does four things and records each one:

1. STAGE   copy the tree into `releases/<id>` (an id names one content for ever);
2. CANARY  run the release as a whole House, `python3 -m league tick --root <canary> --no-publish
           --canary`, a few times in a subprocess with a hard timeout, then `verify`, then read
           its health. A non-zero exit, a traceback, a timeout or bad health: the release is
           REFUSED and `current` is not touched;
3. PROMOTE swap `current` atomically and restart the House (`<base>/restart.sh`);
4. WATCH   read the real House's health every `watch_every` seconds for `watch_seconds`. After a
           grace of two readings, the first bad one ROLLS BACK: `current` goes back to the
           release before, the House is restarted again, and the verdict says why.

There are two watchdogs and they do not fight. The EXTERNAL one (`gateway/lib/watchdog.mjs`)
keeps the box alive: it resumes a paused Sailbox and runs `/workspace/restart.sh` when the
published checkpoint goes stale. This one never touches Sail, never resumes or pauses anything
and never publishes: it only decides which release `current` points at, and asks the same
`restart.sh` to restart the loop. A restart from either is the same harmless signal.

It never writes the ledger. It reads `health.json`, and the SQLite ledger through a read-only
connection. Standard library only, and nothing here imports the rest of the package at import
time: a release whose House cannot even be imported can still be refused by this file.
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
import re
import shutil
import signal
import sqlite3
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Mapping, Sequence

DEFAULT_BASE = "/workspace"
RELEASE_ID = re.compile(r"^[A-Za-z0-9._-]{4,64}$")
MANIFEST = ".release.json"
GRACE_READINGS = 2
VERDICTS = ("promoted", "refused", "rolled_back", "failed")
EXIT_CODES = {"promoted": 0, "refused": 2, "rolled_back": 3, "failed": 4}

#: Never part of a release, whatever the source tree looks like (the uploader's list, and then
#: some): anything whose name starts with a dot (`.env`, `.git`, `.data`, `.venv`, the manifest),
#: caches, key directories, key and database files, and every symlink.
SKIP_DIRS = frozenset({"__pycache__", "node_modules", "keys"})
SKIP_SUFFIXES = (".pyc", ".pyo", ".pem", ".key", ".p8", ".pfx", ".crt", ".der", ".sqlite", ".sqlite-wal", ".sqlite-shm")


class ReleaseError(RuntimeError):
    """A release cannot be staged, promoted or rolled back as asked."""


class DeployBusy(ReleaseError):
    """Another deploy or rollback holds the lock."""


# --------------------------------------------------------------------------------------- time
def iso(ts: float) -> str:
    return datetime.fromtimestamp(float(ts), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + f"{int((float(ts) % 1) * 1000):03d}Z"


def epoch(value: Any) -> float | None:
    """An ISO-8601 stamp (a trailing Z or no zone reads as UTC) as epoch seconds, or None."""
    if not isinstance(value, str) or len(value.strip()) < 19:
        return None
    raw = value.strip()
    if raw[-1] in "Zz":
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


# ------------------------------------------------------------------------------------- health
@dataclass(frozen=True)
class Health:
    ok: bool
    reasons: tuple[str, ...] = ()
    detail: dict = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "reasons": list(self.reasons), "detail": dict(self.detail)}


class _ChainBroken(Exception):
    pass


@contextlib.contextmanager
def _ledger_ro(path: Path) -> Iterator[sqlite3.Connection]:
    """The ledger through a connection that cannot write it."""
    db = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True, timeout=10, isolation_level=None)
    try:
        db.execute("PRAGMA query_only=ON")
        yield db
    finally:
        db.close()


def ledger_head(root: str | Path) -> int | None:
    """The ledger's last sequence number, read-only. None when there is no ledger to read."""
    path = Path(root) / "ledger.sqlite"
    if not path.exists():
        return None
    try:
        with _ledger_ro(path) as db:
            row = db.execute("SELECT MAX(seq) FROM ledger").fetchone()
            return int(row[0] or 0)
    except sqlite3.Error:
        return None


def _verify_chain(db: sqlite3.Connection) -> int:
    """`Ledger.verify()` over a read-only connection: every digest, every link, no gaps."""
    from .ledger import GENESIS, canonical, digest_for  # the ledger's own definition of a digest

    previous, expected, checked = GENESIS, None, 0
    cursor = db.execute("SELECT seq, id, kind, agent, at, public, payload, previous_hash, digest FROM ledger ORDER BY seq ASC")
    for seq, entry_id, kind, agent, at, public, payload, previous_hash, digest in cursor:
        if previous_hash != previous:
            raise _ChainBroken(f"seq {seq}: previous hash mismatch")
        try:
            text = canonical(json.loads(payload))
        except ValueError as exc:
            raise _ChainBroken(f"seq {seq}: payload is not JSON") from exc
        if digest_for(entry_id, kind, agent, at, bool(public), text, previous_hash) != digest:
            raise _ChainBroken(f"seq {seq}: digest mismatch")
        if expected is not None and seq != expected:
            raise _ChainBroken(f"seq {seq}: a row is missing before it")
        expected, previous, checked = seq + 1, digest, checked + 1
    return checked


def read_health(  # noqa: PLR0913 - one reading, one place
    root: str | Path,
    *,
    now: float,
    max_age_seconds: float = 300,
    previous: Health | None = None,
    since_seq: int | None = None,
    verify: bool = False,
    stall_seconds: float = 450,
    inherited_frozen: "Iterable[str] | None" = None,
    inherited_before: float | None = None,
) -> Health:
    """Is the House whose state directory is `root` healthy, and if not, why not.

    From `<root>/health.json` (written at the end of every tick): a missing, unreadable or stale
    file, any book that is `frozen` and not named in `inherited_frozen` (what was already
    frozen before the release under watch was promoted), and each health failure the House
    reports (`failures`: `{check, text, since}`; since Sept 24, 2026 "the lab evaluated nothing in
    the last hour while its queue is not empty"). Against `previous` (an earlier reading of the same
    House; hand each reading to the next and the baselines carry): more than half of the living
    agents gone since the first reading of the chain, a `ledger_seq` that went backwards, and a
    `ledger_seq` that has not advanced for `stall_seconds` (0: it must advance between any two
    readings). From the ledger, when there is one, read-only: error-level `ops.alert` rows after
    `since_seq`, `ops.started` rows after it (reported in `detail`, for the caller that wants to
    know the House really restarted), and, only when `verify` is asked because it is O(n), the
    whole hash chain.

    `inherited_before` (the watch after a promotion passes the promotion's moment): a health
    failure whose `since`, or an error alert whose `began_at` (a warning that repeated, a health
    failure the House announced), is earlier than it began under the release before and is
    reported in `detail` as inherited, not as a reason -- the Sept 19-20 lesson of the frozen books
    applied to conditions that last. So an hour of lab idleness can never roll a release back (it
    cannot begin inside a ten-minute watch), a canary (which inherits nothing, and runs no lab)
    still refuses on any of them, and `status` shows them all.

    A House stopped on purpose (`<root>/STOP`) is not stale and not stalled: it is stopped.
    """
    root = Path(root)
    reasons: list[str] = []
    frozen_books: list[tuple[str, str]] = []  # (book, reason), placed at `frozen_at` below
    frozen_at = 0
    restarted_at: float | None = None  # the first `ops.started` after `since_seq`, when the ledger has one
    stopped = (root / "STOP").exists()
    detail: dict[str, Any] = {"root": str(root), "read_at": now, "stopped": stopped}

    raw: Any = None
    try:
        raw = json.loads((root / "health.json").read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("not an object")
    except FileNotFoundError:
        raw = None
        if not stopped:
            reasons.append("there is no health.json: no tick has finished")
    except (OSError, ValueError) as exc:
        raw = None
        reasons.append(f"health.json cannot be read ({type(exc).__name__}: {str(exc)[:120]})")

    living = seq = None
    if raw is not None:
        at = epoch(raw.get("at"))
        living = raw.get("living") if isinstance(raw.get("living"), int) and not isinstance(raw.get("living"), bool) else None
        seq = raw.get("ledger_seq") if isinstance(raw.get("ledger_seq"), int) and not isinstance(raw.get("ledger_seq"), bool) else None
        books = raw.get("books") if isinstance(raw.get("books"), dict) else {}
        detail.update(at=raw.get("at"), living=living, dead=raw.get("dead"), ledger_seq=seq, real_money=raw.get("real_money"),
                      release=raw.get("release"), books={str(name): (book or {}).get("frozen") if isinstance(book, dict) else None for name, book in books.items()})
        if at is None:
            reasons.append("health.json carries no readable time")
        else:
            age = now - at
            detail["age_seconds"] = round(age, 1)
            if age > max_age_seconds and not stopped:
                reasons.append(f"health.json is {int(age)}s old (the limit is {int(max_age_seconds)}s): ticks are not finishing")
            elif age < -max(60.0, float(max_age_seconds)):
                reasons.append(f"health.json is dated {int(-age)}s in the future")
    if raw is not None:
        # A book already frozen before a release was promoted is not that release's doing, and
        # blaming it makes a release that REPAIRS a freeze impossible to deploy (found Sept 19,
        # 2026: the fix for a frozen paper book was rolled back by the freeze it fixed). Only the
        # watch after a promotion inherits anything; a canary runs a House of its own, so every
        # book it freezes is its own doing and `inherited_frozen` is left None.
        inherited = set(inherited_frozen or ())
        frozen_at = len(reasons)  # where the freezes go once the ledger says whose process wrote them
        for name, book in sorted(books.items()):
            frozen = book.get("frozen") if isinstance(book, dict) else None
            if not frozen:
                continue
            if name in inherited:
                detail.setdefault("frozen_before", []).append(str(name))
            else:
                frozen_books.append((str(name), f"the {name} book is frozen: {str(frozen)[:200]}"))
        failures = raw.get("failures") if isinstance(raw.get("failures"), list) else []
        for failure in failures:
            if not isinstance(failure, dict):
                continue
            began = epoch(failure.get("since"))
            if inherited_before is not None and began is not None and began < float(inherited_before):
                detail.setdefault("inherited_failures", []).append(str(failure.get("check")))
            else:
                reasons.append(f"health failure ({failure.get('check')}): {str(failure.get('text') or '')[:300]}")

    before = previous.detail if previous is not None else {}

    baseline = before.get("living_baseline", before.get("living"))
    if not isinstance(baseline, int):
        baseline = living
    detail["living_baseline"] = baseline
    if isinstance(baseline, int) and isinstance(living, int) and (baseline - living) * 2 > baseline:
        reasons.append(f"{living} agents are alive where there were {baseline}: more than half are gone")
    earlier = before.get("ledger_seq")
    detail["seq_since"] = now
    if isinstance(seq, int) and isinstance(earlier, int):
        if seq < earlier:
            reasons.append(f"ledger_seq went backwards, from {earlier} to {seq}")
        elif seq == earlier:
            since = before.get("seq_since", before.get("read_at", now))
            since = float(since) if isinstance(since, (int, float)) else now
            detail["seq_since"] = since
            if now - since >= stall_seconds and not stopped:
                reasons.append(f"ledger_seq has not advanced from {seq} in {int(now - since)}s: the House is recording nothing")

    ledger = root / "ledger.sqlite"
    if ledger.exists():
        try:
            with _ledger_ro(ledger) as db:
                detail["ledger_head"] = int(db.execute("SELECT MAX(seq) FROM ledger").fetchone()[0] or 0)
                if since_seq is not None:
                    detail["since_seq"] = int(since_seq)
                    detail["started_since"] = int(db.execute("SELECT COUNT(*) FROM ledger WHERE kind = 'ops.started' AND seq > ?", (int(since_seq),)).fetchone()[0])
                    first_start = db.execute("SELECT at FROM ledger WHERE kind = 'ops.started' AND seq > ? ORDER BY seq ASC LIMIT 1",
                                             (int(since_seq),)).fetchone()
                    restarted_at = epoch(first_start[0]) if first_start else None
                    errors, inherited_alerts = [], 0
                    for row_seq, payload in db.execute("SELECT seq, payload FROM ledger WHERE kind = 'ops.alert' AND seq > ? ORDER BY seq ASC", (int(since_seq),)):
                        try:
                            alert = json.loads(payload)
                        except ValueError:
                            alert = {"level": "error", "text": "an alert that is not JSON"}
                        if str(alert.get("level") or "").lower() in ("error", "critical", "fatal"):
                            text = str(alert.get("text") or "")[:300]
                            # A book that was already failing to reconcile before this release goes
                            # on saying so every few minutes, and those alerts are not the new
                            # release's doing any more than the freeze itself is. Sept 20, 2026:
                            # two releases in a row were rolled back on them -- including the one
                            # carrying the fix for that very book, so the floor could not heal
                            # itself and no release of any kind could land. A canary inherits
                            # nothing and still catches everything it causes.
                            if any(text.startswith(book) for book in inherited):
                                inherited_alerts += 1
                                continue
                            # A condition that began before the promotion (Sept 24, 2026): a warning
                            # that had been repeating, or a health failure already under way.
                            began = epoch(alert.get("began_at"))
                            if inherited_before is not None and began is not None and began < float(inherited_before):
                                inherited_alerts += 1
                                continue
                            errors.append((row_seq, text))
                    detail["error_alerts"] = len(errors)
                    if inherited_alerts:
                        detail["inherited_alerts"] = inherited_alerts
                    if errors:
                        reasons.append(f"{len(errors)} error alert(s) since seq {int(since_seq)}; the first, at seq {errors[0][0]}: {errors[0][1]}")
                if verify:
                    detail["ledger_rows_verified"] = _verify_chain(db)
        except _ChainBroken as exc:
            reasons.append(f"the ledger's hash chain does not verify: {exc}")
        except sqlite3.Error as exc:
            reasons.append(f"the ledger cannot be read ({type(exc).__name__}: {str(exc)[:160]})")
    elif verify:
        reasons.append("there is no ledger to verify")
    if frozen_books:
        # A freeze in a health.json the PREVIOUS process wrote is not the release's doing either
        # (Sept 24, 2026, 15:37-15:39Z): Deploy C was promoted at 15:37:57Z and rolled back at
        # 15:39:27Z on "reading 3: the alpaca-paper book is frozen: cash differs by -0.0269". The
        # freeze began at 15:37:27Z in the OLD House's last tick, which wrote its health (dated
        # 15:35:14Z, the tick's start) after the reading taken before the promotion; the new House
        # had not finished a tick, so all three readings read the old process's file (193-253 s
        # old) and judged the new release on it. The watch after a promotion (`inherited_before`
        # set, the ledger read from `since_seq`) therefore counts a frozen book only in a
        # health.json dated at or after the House's first `ops.started` since the promotion: before
        # it, the file is the old process's, reported in `frozen_by_previous_process`. Nothing else
        # softens: a House that never restarts is caught by `HouseHealth.restart_within`, a file
        # that goes on being the old one by `max_age_seconds`, and a ledger that cannot say when the
        # House started leaves the freeze counted.
        health_at = epoch(raw.get("at")) if isinstance(raw, dict) else None
        # No restart recorded yet: the file is certainly the old process's. A restart recorded at a
        # time that cannot be read says nothing about whose file this is, so the freeze counts.
        previous_process = (inherited_before is not None and since_seq is not None and health_at is not None
                            and "started_since" in detail
                            and (detail["started_since"] == 0 or (restarted_at is not None and health_at < restarted_at)))
        if previous_process:
            detail["frozen_by_previous_process"] = [name for name, _ in frozen_books]
        else:
            reasons[frozen_at:frozen_at] = [reason for _, reason in frozen_books]
    return Health(not reasons, tuple(reasons), detail)


# ----------------------------------------------------------------------------------- releases
def _skipped(directory: str, name: str) -> bool:
    path = os.path.join(directory, name)
    if name.startswith(".") or os.path.islink(path):
        return True  # a link can point out of the tree; a release is files, all of them its own
    if os.path.isdir(path):
        return name in SKIP_DIRS
    return name.endswith(SKIP_SUFFIXES)


def tree_digest(root: str | Path) -> tuple[str, int]:
    """One sha256 over a code tree: every file's path, executable bit and content, in order.
    Bytecode, caches, state, secrets and links are not part of a release and not of its digest."""
    root = Path(root)
    hasher = hashlib.sha256()
    count = 0
    for directory, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if not _skipped(directory, d))
        for name in sorted(files):
            if _skipped(directory, name):
                continue
            path = Path(directory) / name
            relative = path.relative_to(root).as_posix()
            executable = "x" if os.stat(path).st_mode & 0o100 else "-"
            hasher.update(f"{relative}\0{executable}\0{hashlib.sha256(path.read_bytes()).hexdigest()}\n".encode("utf-8"))
            count += 1
    return hasher.hexdigest(), count


class Releases:
    """The release directory, the two symlinks and the deploy record under one base directory."""

    def __init__(self, base: str | Path = DEFAULT_BASE, *, clock: Callable[[], float] = time.time):
        self.base = Path(base)
        self.clock = clock
        self.releases_dir = self.base / "releases"
        self.state_dir = self.base / "state"
        self.canary_dir = self.base / "canary"
        self.log_path = self.base / "deploys.jsonl"
        self._log_lock = threading.Lock()

    # ------------------------------------------------------------------ paths
    @staticmethod
    def check_id(release_id: str) -> str:
        if not isinstance(release_id, str) or not RELEASE_ID.match(release_id) or not release_id[0].isalnum():
            raise ReleaseError(f"a release id is 4 to 64 of A-Z a-z 0-9 . _ - and starts with a letter or a digit, not {release_id!r}")
        return release_id

    def path(self, release_id: str) -> Path:
        return self.releases_dir / self.check_id(release_id)

    def _link(self, name: str) -> str | None:
        try:
            target = os.readlink(self.base / name)
        except OSError:
            return None
        release_id = Path(target).name
        if not RELEASE_ID.match(release_id) or not (self.releases_dir / release_id).is_dir():
            return None  # a link to nothing is no release; `status` shows the raw target
        return release_id

    def current(self) -> str | None:
        return self._link("current")

    def previous(self) -> str | None:
        return self._link("previous")

    def list(self) -> list[dict[str, Any]]:
        """Every staged release, newest first."""
        rows = []
        if self.releases_dir.is_dir():
            for entry in self.releases_dir.iterdir():
                if entry.is_symlink() or not entry.is_dir() or not RELEASE_ID.match(entry.name) or not entry.name[0].isalnum():
                    continue
                manifest = self._manifest(entry)
                staged = manifest.get("staged_ts")
                rows.append({"id": entry.name, "digest": manifest.get("digest"), "files": manifest.get("files"),
                             "staged_at": manifest.get("staged_at"), "staged_ts": float(staged) if isinstance(staged, (int, float)) else entry.stat().st_mtime})
        rows.sort(key=lambda row: (row["staged_ts"], row["id"]), reverse=True)
        return rows

    @staticmethod
    def _manifest(path: Path) -> dict[str, Any]:
        try:
            data = json.loads((path / MANIFEST).read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    # ------------------------------------------------------------------ stage
    def stage(self, source: str | Path, release_id: str) -> Path:
        """Copy a code tree into `releases/<id>`. An id names one content for ever: staging it
        again with the same content is the release already there, with anything else an error."""
        target = self.path(release_id)
        source = Path(source)
        if not (source / "league" / "__main__.py").is_file():
            raise ReleaseError(f"{source} is not a code tree: it has no league/__main__.py")
        inside, outside = self.releases_dir.resolve(), source.resolve()
        if outside == inside or outside in inside.parents:
            raise ReleaseError(f"{source} contains the releases directory; a release cannot contain the releases")
        wanted, files = tree_digest(source)
        if target.exists():
            have, _ = tree_digest(target)
            if have != wanted:
                raise ReleaseError(f"release {release_id} is already staged with different content ({have[:12]}, not {wanted[:12]}): give new code a new id")
            return target
        self.releases_dir.mkdir(parents=True, exist_ok=True)
        staging = self.releases_dir / f".staging-{release_id}-{os.getpid()}-{threading.get_ident()}"
        shutil.rmtree(staging, ignore_errors=True)
        try:
            shutil.copytree(source, staging, symlinks=True, ignore=lambda directory, names: [n for n in names if _skipped(directory, n)])
            copied, _ = tree_digest(staging)
            if copied != wanted:
                raise ReleaseError(f"the copy of {source} does not match it: the source changed while it was read")
            now = self.clock()
            manifest = {"id": release_id, "digest": wanted, "files": files, "staged_at": iso(now), "staged_ts": now, "source": str(source)}
            (staging / MANIFEST).write_text(json.dumps(manifest, sort_keys=True, indent=1) + "\n", encoding="utf-8")
            try:
                os.rename(staging, target)  # atomic, and refuses to land on a release someone else just staged
            except OSError as exc:
                raise ReleaseError(f"release {release_id} appeared while it was being staged: {exc}") from exc
        finally:
            shutil.rmtree(staging, ignore_errors=True)
        return target

    # ---------------------------------------------------------------- symlinks
    def _point(self, name: str, release_id: str) -> None:
        """Make `<base>/<name>` a link to the release, atomically: the new link is written beside
        it and renamed over it, so a reader sees the old release or the new one, never neither."""
        link = self.base / name
        if link.exists() and not link.is_symlink():
            raise ReleaseError(f"{link} is not a symlink; this directory is not laid out for releases")
        tmp = self.base / f".{name}.{os.getpid()}.{threading.get_ident()}.tmp"
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp)
        os.symlink(os.path.join("releases", release_id), tmp)
        try:
            os.replace(tmp, link)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
            raise

    def promote(self, release_id: str) -> None:
        """`current` := the release; `previous` := what `current` was. `previous` moves first: a
        crash between the two leaves a rollback that goes nowhere, never one that goes back too far."""
        if not self.path(release_id).is_dir():
            raise ReleaseError(f"release {release_id} is not staged")
        old = self.current()
        if old == release_id:
            return
        if old is not None:
            self._point("previous", old)
        self._point("current", release_id)

    def rollback(self) -> str:
        """`current` := `previous`. Returns the id now current. `previous` is then cleared: the
        release rolled back from is kept on disk but is nothing to roll back TO."""
        target = self.previous()
        if target is None:
            raise ReleaseError("there is no previous release to roll back to")
        if target != self.current():
            self._point("current", target)
        with contextlib.suppress(FileNotFoundError):
            os.unlink(self.base / "previous")
        return target

    def prune(self, keep: int = 5) -> list[str]:
        """Remove all but the `keep` newest releases. Never removes `current` or `previous`."""
        protected = {self.current(), self.previous()}
        removed = []
        for index, row in enumerate(self.list()):
            if index < max(0, int(keep)) or row["id"] in protected:
                continue
            shutil.rmtree(self.releases_dir / row["id"], ignore_errors=True)
            removed.append(row["id"])
        if self.releases_dir.is_dir():
            for entry in self.releases_dir.glob(".staging-*"):
                with contextlib.suppress(OSError):
                    if self.clock() - entry.stat().st_mtime > 3600:
                        shutil.rmtree(entry, ignore_errors=True)
        return removed

    # ------------------------------------------------------------------ canary
    def canary_root(self, release_id: str, *, keep: int = 3) -> Path:
        """A fresh, empty state directory for one canary run; older runs beyond `keep` are removed."""
        self.check_id(release_id)
        self.canary_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(self.canary_dir, 0o700)
        stamp = time.strftime("%Y%m%dT%H%M%S", time.gmtime(self.clock()))
        n = 0
        while True:
            root = self.canary_dir / (f"{stamp}-{release_id}" + (f"-{n}" if n else ""))
            try:
                root.mkdir(mode=0o700)
                break
            except FileExistsError:
                n += 1
        runs = sorted((p for p in self.canary_dir.iterdir() if p.is_dir() and not p.is_symlink() and p != root),
                      key=lambda p: (p.stat().st_mtime, p.name), reverse=True)
        for old in runs[max(0, int(keep) - 1):]:
            shutil.rmtree(old, ignore_errors=True)
        return root

    # -------------------------------------------------------------------- log
    def record(self, row: Mapping[str, Any]) -> dict[str, Any]:
        """Append one row to `deploys.jsonl` (owner-only, one write a line, flushed to disk)."""
        now = self.clock()
        entry = {"at": iso(now), "ts": round(now, 3), **dict(row)}
        line = (json.dumps(entry, sort_keys=True, default=str) + "\n").encode("utf-8")
        self.base.mkdir(parents=True, exist_ok=True)
        with self._log_lock:
            fd = os.open(self.log_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            try:
                os.write(fd, line)
                os.fsync(fd)
            finally:
                os.close(fd)
        return entry

    def history(self, limit: int | None = None) -> list[dict[str, Any]]:
        try:
            lines = self.log_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        rows = []
        for line in lines:
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue  # a torn last line after a power cut is not a reason to lose the rest
        return rows if limit is None else rows[-int(limit):]

    @contextlib.contextmanager
    def lock(self) -> Iterator[None]:
        """One deploy or rollback at a time. The kernel drops the lock if the holder dies."""
        self.base.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.base / ".deploy.lock", os.O_RDWR | os.O_CREAT, 0o600)
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                holder = os.pread(fd, 64, 0).decode("ascii", "replace").strip()
                raise DeployBusy(f"another deploy or rollback is running (pid {holder or 'unknown'})") from exc
            os.ftruncate(fd, 0)
            os.pwrite(fd, str(os.getpid()).encode("ascii"), 0)
            yield
        finally:
            os.close(fd)


# ----------------------------------------------------------------------------------- watchdog
class Watchdog:
    """Stage, canary, promote, watch, and roll back. Everything that touches the world is
    injected: `run_canary(release_dir, canary_root, ticks) -> Health`, `restart_house()`,
    `read_house_health() -> Health`, the clock and the sleep."""

    def __init__(
        self,
        releases: Releases,
        *,
        run_canary: Callable[[Path, Path, int], Health],
        restart_house: Callable[[], Any],
        read_house_health: Callable[[], Health],
        clock: Callable[[], float] = time.time,
        sleep: Callable[[float], Any] = time.sleep,
        log: Callable[[str], Any] | None = None,
    ):
        self.releases = releases
        self.run_canary = run_canary
        self.restart_house = restart_house
        self.read_house_health = read_house_health
        self.clock = clock
        self.sleep = sleep
        self.log = log

    # ---------------------------------------------------------------- helpers
    def _say(self, text: str) -> None:
        if self.log is not None:
            with contextlib.suppress(Exception):
                self.log(text)

    def _read_house(self) -> Health:
        try:
            health = self.read_house_health()
        except Exception as exc:  # noqa: BLE001 - a reader that fails is a reading that is bad
            return Health(False, (f"the House's health could not be read ({type(exc).__name__}: {str(exc)[:200]})",), {})
        if not isinstance(health, Health):
            return Health(False, (f"the health reader returned {type(health).__name__}, not a Health",), {})
        return health

    def _restart(self, stages: list, base: Mapping[str, Any], *, after: str) -> str | None:
        """Restart the House; returns why it could not be, or None."""
        try:
            outcome = self.restart_house()
        except Exception as exc:  # noqa: BLE001
            problem = f"{type(exc).__name__}: {str(exc)[:300]}"
            stages.append(self.releases.record({**base, "stage": "restart", "after": after, "ok": False, "error": problem}))
            return problem
        stages.append(self.releases.record({**base, "stage": "restart", "after": after, "ok": True, "outcome": outcome if isinstance(outcome, (dict, str, int, float, bool, type(None))) else str(outcome)}))
        return None

    # ----------------------------------------------------------------- deploy
    def deploy(self, source: str | Path, release_id: str, *, canary_ticks: int = 3, watch_seconds: int = 600, watch_every: int = 30,
               attestation: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """Returns `{"verdict": "promoted" | "refused" | "rolled_back" | "failed", "reasons": [...],
        "current", "previous", "stages": [...]}`. `refused`: the release never became current.
        `rolled_back`: it did, the House went bad, and the release before it is current again.
        `failed`: it went bad and there was nothing to go back to, so it is still current.

        `attestation` is the updater's record of what GitHub said about the exact commit this tree
        came from (`league/updater.py`). It is written into the deploy's first row, every row of the
        deploy carries its sha, and a staged tree whose digest is not the attested one is refused:
        what runs must be what was attested. The owner's own deploy (`floor_box.py`) has none."""
        try:
            with self.releases.lock():
                return self._deploy(Path(source), release_id, max(1, int(canary_ticks)), max(0, int(watch_seconds)), max(1, int(watch_every)),
                                    dict(attestation) if attestation else None)
        except DeployBusy as exc:
            started = self.clock()
            # `busy` marks a refusal that says nothing about the release: the lock was held, the
            # code was never unpacked, let alone judged. `Updater.tried` must not retire a commit
            # on one of these (see there: the promotion's own restart makes the race the norm).
            row = self.releases.record({"deploy": f"{release_id}@{int(started)}", "release": release_id, "stage": "verdict",
                                        "verdict": "refused", "busy": True, "reasons": [str(exc)]})
            return {"deploy": row["deploy"], "release": release_id, "verdict": "refused", "busy": True, "reasons": [str(exc)], "current": self.releases.current(),
                    "previous": self.releases.previous(), "started_at": iso(started), "finished_at": iso(started), "readings": 0, "stages": [row]}

    def _deploy(self, source: Path, release_id: str, canary_ticks: int, watch_seconds: int, watch_every: int,
                attestation: dict[str, Any] | None = None) -> dict[str, Any]:
        started = self.clock()
        base = {"deploy": f"{release_id}@{int(started)}", "release": release_id}
        if attestation and attestation.get("sha"):
            base["sha"] = str(attestation["sha"])
        stages: list[dict[str, Any]] = []
        readings = 0

        def note(**row: Any) -> dict[str, Any]:
            entry = self.releases.record({**base, **row})
            stages.append(entry)
            return entry

        def verdict(name: str, reasons: Sequence[str]) -> dict[str, Any]:
            note(stage="verdict", verdict=name, reasons=list(reasons), current=self.releases.current(), previous=self.releases.previous())
            self._say(f"{release_id}: {name}" + (f" ({'; '.join(reasons)})" if reasons else ""))
            return {**base, "verdict": name, "reasons": list(reasons), "current": self.releases.current(), "previous": self.releases.previous(),
                    "started_at": iso(started), "finished_at": iso(self.clock()), "readings": readings, "stages": stages}

        was_current = self.releases.current()
        note(stage="start", source=str(source), current=was_current, previous=self.releases.previous(),
             canary_ticks=canary_ticks, watch_seconds=watch_seconds, watch_every=watch_every,
             **({"attestation": attestation} if attestation else {}))

        # 1. stage
        try:
            if was_current == self.releases.check_id(release_id):
                raise ReleaseError(f"release {release_id} is already current; to restart the House run restart.sh")
            path = self.releases.stage(source, release_id)
        except (ReleaseError, OSError) as exc:
            note(stage="stage", ok=False, error=str(exc))
            return verdict("refused", [f"staging failed: {exc}"])
        staged = self.releases._manifest(path).get("digest")
        note(stage="stage", ok=True, path=str(path), digest=staged)
        if attestation and attestation.get("tree_digest") and attestation["tree_digest"] != staged:
            return verdict("refused", [f"the staged tree ({str(staged)[:12]}) is not the attested one ({str(attestation['tree_digest'])[:12]})"])
        self._say(f"{release_id}: staged at {path}")

        # 2. canary
        canary_root: Path | None = None
        try:
            canary_root = self.releases.canary_root(release_id)
            health = self.run_canary(path, canary_root, canary_ticks)
            if not isinstance(health, Health):
                health = Health(False, (f"the canary returned {type(health).__name__}, not a Health",), {})
        except Exception as exc:  # noqa: BLE001 - a canary that cannot run has not passed
            health = Health(False, (f"the canary could not be run ({type(exc).__name__}: {str(exc)[:300]})",), {})
        note(stage="canary", ok=health.ok, reasons=list(health.reasons), detail=health.detail, canary_root=str(canary_root), ticks=canary_ticks)
        if not health.ok:
            return verdict("refused", [f"canary: {reason}" for reason in health.reasons] or ["canary: it did not pass"])
        self._say(f"{release_id}: the canary passed {canary_ticks} tick(s)")

        # 3. promote. The reading before it is the record of what the House looked like under the
        #    old release, and it is where the reader's baselines (living agents, ledger seq) start.
        before = self._read_house()
        note(stage="house_before", ok=before.ok, reasons=list(before.reasons), detail=before.detail)
        try:
            self.releases.promote(release_id)
        except (ReleaseError, OSError) as exc:
            note(stage="promote", ok=False, error=str(exc))
            return verdict("refused", [f"promotion failed: {exc}"])
        note(stage="promote", ok=True, current=release_id, previous=was_current)
        self._say(f"{release_id}: promoted (was {was_current})")

        try:
            problem = self._restart(stages, base, after="promote")
            if problem is not None:
                return self._back_out(base, stages, verdict, release_id, [f"the House could not be restarted into {release_id}: {problem}"])

            # 4. watch
            if watch_seconds > 0:
                deadline = self.clock() + watch_seconds
                while True:
                    self.sleep(watch_every)
                    reading = self._read_house()
                    readings += 1
                    in_grace = readings <= GRACE_READINGS
                    note(stage="watch", reading=readings, grace=in_grace, ok=reading.ok, reasons=list(reading.reasons), detail=reading.detail)
                    if not reading.ok and not in_grace:
                        self._say(f"{release_id}: reading {readings} is bad: {'; '.join(reading.reasons)}")
                        return self._back_out(base, stages, verdict, release_id, [f"reading {readings}: {reason}" for reason in reading.reasons])
                    if self.clock() >= deadline and readings > GRACE_READINGS:
                        break
        except BaseException as exc:
            # Killed or interrupted mid-watch: the release stays current and unjudged. Say so.
            note(stage="interrupted", error=f"{type(exc).__name__}: {str(exc)[:200]}", current=self.releases.current())
            raise
        result = verdict("promoted", [])
        removed = self.releases.prune()
        if removed:
            note(stage="prune", removed=removed)
        return result

    def _back_out(self, base: Mapping[str, Any], stages: list, verdict: Callable[..., dict[str, Any]], release_id: str, reasons: list[str]) -> dict[str, Any]:
        try:
            now_current = self.releases.rollback()
        except (ReleaseError, OSError) as exc:
            stages.append(self.releases.record({**base, "stage": "rollback", "ok": False, "error": str(exc)}))
            return verdict("failed", reasons + [f"and it could not be rolled back: {exc}"])
        stages.append(self.releases.record({**base, "stage": "rollback", "ok": True, "from": release_id, "to": now_current}))
        self._say(f"{release_id}: rolled back to {now_current}")
        problem = self._restart(stages, base, after="rollback")
        if problem is not None:
            reasons = reasons + [f"rolled back to {now_current}, but the House could not be restarted: {problem}"]
        return verdict("rolled_back", reasons)

    # --------------------------------------------------------------- rollback
    def rollback(self, reason: str = "asked for by the operator") -> dict[str, Any]:
        """The operator's rollback: `current` := `previous`, restart, record."""
        with self.releases.lock():
            started = self.clock()
            was = self.releases.current()
            base = {"deploy": f"rollback@{int(started)}", "release": was}
            stages: list[dict[str, Any]] = []
            try:
                now_current = self.releases.rollback()
            except ReleaseError as exc:
                stages.append(self.releases.record({**base, "stage": "rollback", "ok": False, "error": str(exc), "reason": reason}))
                return {"ok": False, "error": str(exc), "current": was, "stages": stages}
            stages.append(self.releases.record({**base, "stage": "rollback", "ok": True, "from": was, "to": now_current, "reason": reason}))
            problem = self._restart(stages, base, after="rollback")
            return {"ok": problem is None, "error": problem, "current": now_current, "rolled_back_from": was, "stages": stages}


# --------------------------------------------------------------------------------- production
def _tail(text: Any, limit: int) -> str:
    if isinstance(text, bytes):
        text = text.decode("utf-8", "replace")
    text = str(text or "")
    return text if len(text) <= limit else "..." + text[-limit:]


class SubprocessCanary:
    """The production `run_canary`: the release run as a House of its own, in its own process.

    `python3 -m league tick --root <canary_root> --no-publish --canary`, `ticks` times, each with
    `cwd` the release and a hard timeout (the whole process group is killed at it), a health
    reading after each; then `python3 -m league verify` the same way; then one last reading that
    walks the canary ledger's whole hash chain. `--canary` is the House's promise to trade on a
    simulated Alpaca account (`league.sim.SimBroker`) and a throwaway Kalshi shadow, publish
    nothing, research nothing and touch no real money; `LEAGUE_CANARY=1` says the same thing in
    the environment, for code that has no argv to read.
    """

    def __init__(self, *, python: str | None = None, tick_timeout: float = 600, verify_timeout: float = 300, max_age_seconds: float = 300,
                 env: Mapping[str, str] | None = None, env_file: str | Path | None = None, protected: Sequence[str | Path] = (),
                 clock: Callable[[], float] = time.time):
        self.python = python or sys.executable or "python3"
        self.tick_timeout = float(tick_timeout)
        self.verify_timeout = float(verify_timeout)
        self.max_age_seconds = float(max_age_seconds)
        self.env = dict(os.environ if env is None else env)
        self.env_file = Path(env_file) if env_file else None
        self.protected = [Path(p).resolve() for p in protected]
        self.clock = clock

    def _env(self, release_dir: Path) -> dict[str, str]:
        env = dict(self.env)
        env.pop("PYTHONSAFEPATH", None)  # `-m league` must find the release in its cwd
        env.pop("PYTHONHOME", None)
        env["PYTHONPATH"] = str(release_dir)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["PYTHONUNBUFFERED"] = "1"
        env["LEAGUE_CANARY"] = "1"
        if self.env_file is not None and self.env_file.exists():
            env.setdefault("LEAGUE_ENV", str(self.env_file))
        return env

    def _run(self, release_dir: Path, command: Sequence[str], timeout: float) -> dict[str, Any]:
        started = self.clock()
        argv = [self.python, "-m", "league", *command]
        try:
            process = subprocess.Popen(argv, cwd=str(release_dir), env=self._env(release_dir), stdin=subprocess.DEVNULL,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        except OSError as exc:
            return {"command": " ".join(command), "problem": f"it could not be started ({type(exc).__name__}: {exc})"}
        try:
            out, err = process.communicate(timeout=timeout)
            timed_out = False
        except subprocess.TimeoutExpired:
            timed_out = True
            with contextlib.suppress(OSError):
                os.killpg(process.pid, signal.SIGKILL)
            out, err = process.communicate()
        run = {"command": " ".join(command), "exit": process.returncode, "seconds": round(self.clock() - started, 1),
               "stdout": _tail(out, 1500), "stderr": _tail(err, 3000)}
        text = (out or b"").decode("utf-8", "replace") + (err or b"").decode("utf-8", "replace")
        if timed_out:
            run["problem"] = f"it did not finish in {int(timeout)}s and was killed"
        elif process.returncode != 0:
            last = [line for line in (err or out or b"").decode("utf-8", "replace").strip().splitlines() if line.strip()]
            run["problem"] = f"it exited {process.returncode}" + (f": {last[-1][:300]}" if last else "")
        elif "Traceback (most recent call last)" in text:
            run["problem"] = "it printed a traceback"
        return run

    def __call__(self, release_dir: str | Path, canary_root: str | Path, ticks: int) -> Health:
        release_dir, canary_root = Path(release_dir).resolve(), Path(canary_root).resolve()
        for kept in self.protected:
            if canary_root == kept or kept in canary_root.parents or canary_root in kept.parents:
                return Health(False, (f"the canary root {canary_root} is not apart from {kept}: a canary never runs on the House's state",), {})
        canary_root.mkdir(parents=True, exist_ok=True)
        flags = ["--root", str(canary_root), "--no-publish", "--canary"]
        runs: list[dict[str, Any]] = []
        reasons: list[str] = []
        detail: dict[str, Any] = {"release_dir": str(release_dir), "canary_root": str(canary_root), "runs": runs}
        previous: Health | None = None
        for n in range(1, max(1, int(ticks)) + 1):
            run = self._run(release_dir, ["tick", *flags], self.tick_timeout)
            runs.append(run)
            if run.get("problem"):
                reasons.append(f"tick {n}: {run['problem']}")
                break
            previous = read_health(canary_root, now=self.clock(), max_age_seconds=self.max_age_seconds, previous=previous, since_seq=0, stall_seconds=0)
            if not previous.ok:
                reasons.extend(f"after tick {n}: {reason}" for reason in previous.reasons)
                break
        if not reasons:
            run = self._run(release_dir, ["verify", *flags], self.verify_timeout)
            runs.append(run)
            if run.get("problem"):
                reasons.append(f"verify: {run['problem']}")
        if not reasons:
            final = read_health(canary_root, now=self.clock(), max_age_seconds=self.max_age_seconds, since_seq=0, verify=True)
            reasons.extend(f"at the end: {reason}" for reason in final.reasons)
            previous = final
        if previous is not None:
            detail["health"] = previous.detail
        return Health(not reasons, tuple(reasons), detail)


class RestartScript:
    """The production `restart_house`: run `<base>/restart.sh` if it is there, and nothing else.
    The script signals the running loop; the supervisor starts the next one from `current`."""

    def __init__(self, base: str | Path, *, timeout: float = 120):
        self.script = Path(base) / "restart.sh"
        self.timeout = float(timeout)

    def __call__(self) -> dict[str, Any]:
        if not self.script.is_file():
            return {"ran": False, "why": f"{self.script} does not exist"}
        done = subprocess.run(["sh", str(self.script)], cwd=str(self.script.parent), stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=self.timeout)
        output = _tail(done.stdout, 500).strip()
        if done.returncode != 0:
            raise RuntimeError(f"{self.script} exited {done.returncode}: {output}")
        return {"ran": True, "exit": 0, "output": output}


class HouseHealth:
    """The production `read_house_health`: `read_health` on the House's real state directory,
    each reading handed to the next. The FIRST reading is the one `deploy` takes just before it
    promotes, and it fixes the baselines: error alerts count from the ledger's head at that
    moment, the living agents are compared with that moment's, and a condition that began before
    it (a health failure's `since`, an error's `began_at`) is inherited. A House that has recorded
    no `ops.started` since then, `restart_within` seconds on, never restarted into the new release:
    healthy readings of the OLD process say nothing about the new code, so that is a bad reading."""

    def __init__(self, root: str | Path, *, clock: Callable[[], float] = time.time, max_age_seconds: float = 300,
                 stall_seconds: float = 450, restart_within: float | None = 300):
        self.root = Path(root)
        self.clock = clock
        self.max_age_seconds = max_age_seconds
        self.stall_seconds = stall_seconds
        self.restart_within = restart_within
        self.previous: Health | None = None
        self.since_seq: int | None = None
        self.first_at: float | None = None
        self.inherited_frozen: tuple[str, ...] = ()

    def __call__(self) -> Health:
        now = self.clock()
        first = self.first_at is None
        if first:
            self.first_at = now
            self.since_seq = ledger_head(self.root) or 0
            # What was already broken before this release was promoted. It is judged on what it
            # breaks, not on what it inherited, or a release that mends a frozen book could never
            # be deployed while that book is frozen.
            inherited = read_health(self.root, now=now, max_age_seconds=self.max_age_seconds, since_seq=0, stall_seconds=0)
            self.inherited_frozen = tuple(name for name, frozen in (inherited.detail.get("books") or {}).items() if frozen)
        health = read_health(self.root, now=now, max_age_seconds=self.max_age_seconds, previous=self.previous,
                             since_seq=self.since_seq, stall_seconds=self.stall_seconds, inherited_frozen=self.inherited_frozen,
                             inherited_before=self.first_at)
        waited = now - float(self.first_at)
        if (not first and self.restart_within is not None and waited >= self.restart_within and not health.detail.get("stopped")
                and health.detail.get("started_since") == 0):
            reasons = health.reasons + (f"the House has not restarted in the {int(waited)}s since the promotion (no ops.started after seq {self.since_seq})",)
            health = Health(False, reasons, health.detail)
        self.previous = health
        return health


def production(base: str | Path = DEFAULT_BASE, *, state: str | Path | None = None, python: str | None = None,
               tick_timeout: float = 600, max_age_seconds: float = 300, restart_within: float | None = 300,
               log: Callable[[str], Any] | None = None) -> Watchdog:
    """The watchdog as it runs on the House box."""
    releases = Releases(base)
    state_dir = Path(state) if state else releases.state_dir
    return Watchdog(
        releases,
        run_canary=SubprocessCanary(python=python, tick_timeout=tick_timeout, env_file=releases.base / ".env", protected=[state_dir]),
        restart_house=RestartScript(releases.base),
        read_house_health=HouseHealth(state_dir, max_age_seconds=max_age_seconds, restart_within=restart_within),
        log=log,
    )


# ---------------------------------------------------------------------------------------- cli
def status(releases: Releases, state: Path, *, now: float | None = None) -> dict[str, Any]:
    def raw(name: str) -> str | None:
        try:
            return os.readlink(releases.base / name)
        except OSError:
            return None

    verdicts = [row for row in releases.history() if row.get("stage") == "verdict"]
    return {
        "base": str(releases.base),
        "current": releases.current(), "current_link": raw("current"),
        "previous": releases.previous(), "previous_link": raw("previous"),
        "releases": [{k: row[k] for k in ("id", "staged_at", "digest", "files")} for row in releases.list()],
        "house": read_health(state, now=time.time() if now is None else now).to_dict(),
        "last_deploys": [{k: row.get(k) for k in ("at", "release", "verdict", "reasons")} for row in verdicts[-5:]],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="league.watchdog", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--base", default=DEFAULT_BASE, help="the directory that holds releases/, current, state/ (default /workspace)")
        p.add_argument("--state", default=None, help="the House's state directory (default <base>/state)")

    deploy = sub.add_parser("deploy", help="stage, canary, promote and watch a release; exit 0 only when it is promoted")
    common(deploy)
    deploy.add_argument("--source", required=True, help="the code tree to release")
    deploy.add_argument("--id", required=True, help="the release id: 4-64 of A-Z a-z 0-9 . _ -")
    deploy.add_argument("--canary-ticks", type=int, default=3)
    deploy.add_argument("--watch-seconds", type=int, default=600, help="0 promotes without watching (a first deploy onto a box whose loop is not up)")
    deploy.add_argument("--watch-every", type=int, default=30)
    deploy.add_argument("--tick-timeout", type=int, default=600, help="the hard limit on one canary tick, in seconds")
    deploy.add_argument("--python", default=None, help="the interpreter the canary runs under (default: this one)")
    deploy.add_argument("--max-age-seconds", type=int, default=300, help="how old the House's health.json may be before a reading is bad")
    deploy.add_argument("--restart-within", type=int, default=300,
                        help="a House that has recorded no ops.started this long after the promotion is a bad reading (0: do not ask)")
    deploy.add_argument("--attestation", default=None,
                        help="a JSON file: the updater's record of GitHub's checks on the exact commit (league/updater.py)")
    common(sub.add_parser("status", help="current, previous, the staged releases, the House's health, the last verdicts"))
    rollback = sub.add_parser("rollback", help="current := previous, and restart the House")
    common(rollback)
    rollback.add_argument("--reason", default="asked for by the operator")
    prune = sub.add_parser("prune", help="remove old releases (never current or previous)")
    common(prune)
    prune.add_argument("--keep", type=int, default=5)
    args = parser.parse_args(argv)

    releases = Releases(args.base)
    state = Path(args.state) if args.state else releases.state_dir
    if args.command == "status":
        print(json.dumps(status(releases, state), indent=1, default=str))
        return 0
    if args.command == "prune":
        with releases.lock():
            print(json.dumps({"removed": releases.prune(args.keep)}))
        return 0
    say = lambda text: print(f"{iso(time.time())}  watchdog: {text}", file=sys.stderr, flush=True)  # noqa: E731
    dog = production(args.base, state=state, python=getattr(args, "python", None), tick_timeout=getattr(args, "tick_timeout", 600),
                     max_age_seconds=getattr(args, "max_age_seconds", 300), restart_within=getattr(args, "restart_within", 300) or None, log=say)
    if args.command == "rollback":
        try:
            result = dog.rollback(args.reason)
        except DeployBusy as exc:
            print(json.dumps({"ok": False, "error": str(exc)}))
            return 5
        print(json.dumps(result, indent=1, default=str))
        return 0 if result["ok"] else 1
    attestation = None
    if args.attestation:
        try:
            attestation = json.loads(Path(args.attestation).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            # An attested deploy whose record cannot be read is not attested: refuse, and say so.
            # `unjudged`: the tree was never looked at, so `Updater.tried` must not retire it.
            row = releases.record({"release": args.id, "stage": "verdict", "verdict": "refused", "unjudged": True,
                                   "reasons": [f"the attestation {args.attestation} cannot be read: {type(exc).__name__}"]})
            print(json.dumps({k: v for k, v in row.items()}, indent=1, default=str))
            return EXIT_CODES["refused"]
    result = dog.deploy(args.source, args.id, canary_ticks=args.canary_ticks, watch_seconds=args.watch_seconds, watch_every=args.watch_every,
                        attestation=attestation)
    print(json.dumps({k: v for k, v in result.items() if k != "stages"}, indent=1, default=str))
    return EXIT_CODES.get(result["verdict"], 1)


if __name__ == "__main__":
    raise SystemExit(main())
