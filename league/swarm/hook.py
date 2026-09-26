"""The House's side of the swarm: `SwarmStep`, the House's `swarm` step (`House.PLUGGABLE_STEPS`).

    house.swarm = SwarmStep(root)          # league/service.py, when config "swarm" is enabled
    house.swarm.tick(house, open_for_business=True)   # the House calls it once a tick, in its own try

Each tick, cheaply and never waiting on the swarm:

1. SUPERVISE. The swarm is its own process (`python -m league.swarm run --root <state>`, niced, its own
   session, logging to `<state>/swarm.log`). The step starts it when it is not running, and restarts it when
   its heartbeat (`<state>/swarm.heartbeat`) is older than `stale_heartbeat_seconds` (a hang) or it runs a
   release other than the House's (a deploy or a rollback). It never starts one while a STOP file is down or
   the swarm is disabled, and backs off after failed starts. A swarm crash or hang never touches the House:
   the House only reads files and a SQLite store read-only.
2. MIRROR. The swarm's events (its own append-only table) go into the House ledger as `swarm.*` rows, at
   most `mirror_limit` a tick, idempotent by id (`swarm:<seq>`): the public ones (`swarm.born`,
   `swarm.retired`, `swarm.band`, `swarm.note`) feed the site's tape; the rest are private. The House's own
   `agent.*` and `eval.*` kinds are never written here (its roster and evaluator read those).
3. READ. `bands()` (what the live path may run: `bands.read`) and `site_inputs()` (the site's agents, the
   Gym's pace and the swarm's compute), which the House's own `site_inputs()` merges with the live path's.

Standard library only.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Mapping

from . import HEARTBEAT, LOG_FILE, bands as bands_mod, public, settings as settings_mod, sitefeed
from .store import SwarmStore

CODE_DIR = Path(__file__).resolve().parents[2]
PUBLIC_KINDS = ("swarm.born", "swarm.retired", "swarm.band", "swarm.note")
#: Kept in the swarm's own table only: a cycle a minute a family is thousands of rows an hour, and the House ledger is
#: append-only on a small disk. The hourly `swarm.tournament` row carries their totals (cycles, trials, spend).
SKIPPED_KINDS = ("swarm.cycle",)
MIRROR_CURSOR = "swarm-mirror.json"


class SwarmStep:
    """The House's swarm step (the module docstring)."""

    def __init__(self, root: str | Path, *, config: Mapping[str, Any] | None = None, python: str = sys.executable,
                 code_dir: Path = CODE_DIR, clock: Callable[[], float] = time.time, spawn: Callable[..., Any] | None = None,
                 kill: Callable[[int, int], None] = os.kill, mirror_limit: int = 200):
        self.root = Path(root)
        self.config = config
        self.python = python
        self.code_dir = Path(code_dir)
        self.clock = clock
        self.spawn = spawn or self._popen
        self.kill = kill
        self.mirror_limit = int(mirror_limit)
        self.last_start = float("-inf")
        self.failed_starts = 0
        self.terminating: tuple[int, float] | None = None
        self.child: Any = None

    # ------------------------------------------------------------------ the House calls this
    def tick(self, house: Any = None, open_for_business: bool = True) -> dict[str, Any]:
        # A House paused for maintenance (or with its meter stopped) starts no new paid work: it starts no swarm. One
        # already running goes on (the Gym trains through a pause); `<state>/swarm.stop` is how to stop it.
        out: dict[str, Any] = {"process": self.supervise(may_start=open_for_business)}
        ledger = getattr(house, "ledger", None)
        if ledger is not None:
            try:
                out["mirrored"] = self.mirror(ledger)
            except Exception as exc:  # noqa: BLE001 - a mirror failure is reported, never raised into the tick
                out["mirror_error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
        return out

    # ------------------------------------------------------------------ supervise
    def heartbeat(self) -> dict[str, Any] | None:
        try:
            return json.loads((self.root / HEARTBEAT).read_text())
        except (OSError, ValueError):
            return None

    def alive(self, pid: int | None) -> bool:
        if not pid:
            return False
        if self.child is not None and getattr(self.child, "pid", None) == pid:
            if self.child.poll() is not None:  # our own child that exited: reap it
                return False
        try:
            self.kill(int(pid), 0)
        except (OSError, ProcessLookupError):
            return False
        return True

    def stopped(self) -> str:
        for stop in (self.root / "STOP", self.root.parent / "STOP", self.root / "swarm.stop"):
            if stop.exists():
                return f"{stop.name} is down"
        return ""

    def supervise(self, *, may_start: bool = True) -> dict[str, Any]:
        settings = settings_mod.load(self.root, config=self.config)
        now = self.clock()
        beat = self.heartbeat() or {}
        pid = beat.get("pid")
        try:
            pid = int(pid) if pid else int((self.root / "swarm.pid").read_text().strip())
        except (OSError, ValueError):
            pid = None
        running = self.alive(pid)
        age = now - float(beat.get("at") or 0.0) if beat else None
        info: dict[str, Any] = {"enabled": bool(settings.get("enabled")), "pid": pid if running else None,
                                "heartbeat_age": None if age is None else round(age, 1), "release": beat.get("release")}
        if self.terminating is not None:
            tpid, since = self.terminating
            if self.alive(tpid):
                if now - since >= 30:
                    self._signal(tpid, signal.SIGKILL)
                info["action"] = "terminating"
                return info
            self.terminating = None
            running = False
        why_not = "" if settings.get("enabled") else "disabled"
        why_not = why_not or self.stopped()
        if why_not:
            info["idle"] = why_not
            return info  # the swarm leaves by itself on a STOP file or when disabled; nothing to start
        if running:
            stale = age is not None and age >= float(settings.get("stale_heartbeat_seconds", 240)) and \
                now - self.last_start >= float(settings.get("stale_heartbeat_seconds", 240))
            other = beat.get("release") not in (None, str(self.code_dir)) and now - float(beat.get("started_at") or 0) > 60
            if stale or other:
                self._signal(int(pid), signal.SIGTERM)
                self.terminating = (int(pid), now)
                info["action"] = "restart: " + ("its heartbeat is stale" if stale else "it runs another release")
            return info
        if not may_start:
            info["idle"] = "the House is not open for business"
            return info
        backoff = min(1800.0, 30.0 * (2 ** min(self.failed_starts, 6)))
        if now - self.last_start < backoff:
            info["action"] = f"waiting {backoff - (now - self.last_start):.0f} s to start"
            return info
        if self.last_start > float("-inf") and (not beat or float(beat.get("at") or 0) < self.last_start):
            self.failed_starts += 1  # the last start never beat
        else:
            self.failed_starts = 0
        self.last_start = now
        try:
            self.child = self.spawn()
            info["action"] = "started"
            info["pid"] = getattr(self.child, "pid", None)
        except Exception as exc:  # noqa: BLE001
            info["action"] = f"start failed: {type(exc).__name__}: {exc}"
        return info

    def _signal(self, pid: int, sig: int) -> None:
        try:
            self.kill(pid, sig)
        except (OSError, ProcessLookupError):
            pass

    def _popen(self) -> Any:
        log = open(self.root / LOG_FILE, "ab")  # noqa: SIM115 - the child owns it
        try:
            return subprocess.Popen([self.python, "-m", "league.swarm", "run", "--root", str(self.root)], cwd=str(self.code_dir),
                                    stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True,
                                    env=dict(os.environ))
        finally:
            log.close()

    # ------------------------------------------------------------------ mirror
    def _cursor(self) -> int:
        try:
            return int(json.loads((self.root / MIRROR_CURSOR).read_text()).get("seq", 0))
        except (OSError, ValueError, AttributeError):
            return 0

    def mirror(self, ledger: Any) -> int:
        """The swarm's new events into the House ledger (at most `mirror_limit`), idempotent by id."""
        if not (self.root / "swarm.sqlite").exists():
            return 0
        cursor = self._cursor()
        store = SwarmStore(self.root, readonly=True)
        try:
            rows = store.events_after(cursor, limit=self.mirror_limit)
        finally:
            store.close()
        if not rows:
            return 0
        batch = []
        names: dict[str, list[str]] = {}
        for r in rows:
            if r["kind"] in SKIPPED_KINDS:
                continue
            payload = dict(r["payload"]) if isinstance(r["payload"], dict) else {"value": r["payload"]}
            if r["kind"] in PUBLIC_KINDS:
                # The second wall (the researcher filtered the note first): a public row carries words only.
                fid = r["family"] or ""
                if fid not in names:
                    names[fid] = self._param_names(fid)
                payload = public_payload(r["kind"], payload, names[fid])
                if payload is None:
                    continue
            payload["swarm_seq"] = r["seq"]
            payload["swarm_at"] = r["at"]
            batch.append({"kind": r["kind"], "payload": payload, "agent": r["family"] or "house", "id": f"swarm:{r['seq']}",
                          "public": r["kind"] in PUBLIC_KINDS})
        if batch:
            ledger.append_many(batch)
        tmp = self.root / (MIRROR_CURSOR + ".tmp")
        tmp.write_text(json.dumps({"seq": rows[-1]["seq"], "at": self.clock()}))
        tmp.replace(self.root / MIRROR_CURSOR)
        return len(rows)

    def _param_names(self, fid: str) -> list[str]:
        if not fid:
            return []
        store = SwarmStore(self.root, readonly=True)
        try:
            latest = store.latest_version(fid) or {}
        finally:
            store.close()
        return public.param_names_of(latest.get("code")) + list((latest.get("params") or {}).keys())

    # ------------------------------------------------------------------ read
    def bands(self) -> list[dict[str, Any]]:
        return bands_mod.read(self.root)

    def site_inputs(self) -> dict[str, Any]:
        return sitefeed.site_inputs(self.root)


def public_payload(kind: str, payload: dict[str, Any], names: list[str]) -> dict[str, Any] | None:
    """A public row's payload with its words filtered (`public.py`); None drops the row (a note with nothing left).
    Its other fields are kept only when they are names, bands, structures or roots."""
    keep = {k: payload[k] for k in ("parent", "structure", "roots", "origin", "founder", "band_from", "band_to", "swarm_seq", "swarm_at")
            if k in payload}
    if kind == "swarm.note":
        text = public.note_text(payload.get("text"), param_names=names)
        return {**keep, "text": text} if text else None
    for field in ("mechanism", "reason", "cause"):
        if field in payload:
            text = public.news_text(payload.get(field), param_names=names)
            if text:
                keep[field] = text
    return keep


def attach(house: Any, root: str | Path, config: Mapping[str, Any]) -> SwarmStep | None:
    """Set `house.swarm` when the swarm is enabled (the House's `site_inputs()` reads `house.swarm.site_inputs()`)."""
    if not settings_mod.load(root, config=config).get("enabled"):  # config.json "swarm" < <root>/swarm.json
        return None
    step = SwarmStep(root, config=config)
    house.swarm = step
    return step


__all__ = ["SwarmStep", "attach", "PUBLIC_KINDS"]
