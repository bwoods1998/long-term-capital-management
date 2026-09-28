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
   `agent.*` and `eval.*` kinds are never written here (its roster and evaluator read those). A kind the ledger
   does not know (`league.ledger.KINDS`) is skipped and counted, never written: the ledger refuses an unknown kind
   and rolls back the whole batch, so one new swarm kind would otherwise stall every row behind it (Sept 26-27,
   2026: `swarm.diagnostician` and `swarm.robustness` held the site's swarm news back for 14 hours). The first
   time a kind is dropped, the House gets one warning naming it. A batch the ledger refuses for any other reason
   is written again row by row. A row the ledger refuses on its content (a `LedgerError`) is skipped and counted,
   with one warning per distinct reason. A failure of the ledger itself stops there, and the cursor moves only
   past the rows handled before it. A mirror that fails with the same error (`league.house.alert_key`)
   `MIRROR_ALERT_AFTER` ticks in a row is ONE House error alert, at most one per error every
   `MIRROR_ERROR_COOLDOWN_SECONDS`, and an info when it works again.
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

from . import HEARTBEAT, LOCK_FILE, LOG_FILE, bands as bands_mod, public, settings as settings_mod, sitefeed
from .store import SwarmStore
from .cleanup import StoppedPoolCleanup
from ..data_job import NightlySupervisor, read_json
from ..ledger import KINDS as LEDGER_KINDS, LedgerError, now_iso

CODE_DIR = Path(__file__).resolve().parents[2]
PUBLIC_KINDS = ("swarm.born", "swarm.retired", "swarm.band", "swarm.note")
#: Kept in the swarm's own table only: a cycle a minute a family is thousands of rows an hour (and the pool's rows follow
#: the boxes), and the House ledger is append-only on a small disk. The hourly `swarm.tournament` row carries their totals.
#: The diagnostician's calls and the robustness demotions (R1, Sept 26, 2026) are private diagnostics: route, cost,
#: stop reason and a version's evidence, which the swarm's store keeps.
SKIPPED_KINDS = ("swarm.cycle", "swarm.pool", "swarm.diagnostician", "swarm.robustness")
MIRROR_CURSOR = "swarm-mirror.json"
#: The run of failed mirrors in a row (its folded error, since when, how many, whether the House heard it). Kept on disk so
#: a restart (a deploy) neither forgets a run nor dates it from the new process: the alert's `began_at` is the run's first
#: failure, so a watch counts a failure that began before a promotion as inherited, never as the new release's doing.
MIRROR_FAILING = "swarm-mirror-failing.json"
#: Failed mirrors in a row with the same error before the House hears of it: one tick's lock or blip is not an alert.
MIRROR_ALERT_AFTER = 3
#: At most one error alert per folded mirror error in this long. A mirror that fails and recovers again and again is one
#: error (and its info), not one every few ticks.
MIRROR_ERROR_COOLDOWN_SECONDS = 6 * 3600
#: What the House has already been told about the mirror, kept across runs and restarts: `kinds` (each dropped unknown
#: kind, warned of once), `reasons` (each folded reason a row was refused for, warned of once) and `errors` (when each
#: folded mirror error was last an error alert, for the cooldown).
MIRROR_NOTICES = "swarm-mirror-notices.json"
#: The most kinds and reasons `MIRROR_NOTICES` remembers, each (the oldest are forgotten first).
MIRROR_NOTICES_KEPT = 200


def _alert_key(text: Any) -> str:
    """The House's own fold of an alert's text (`league.house.alert_key`: UUIDs and every token with a digit folded), so
    the mirror's alerts count as the House's own do. Imported when called: the swarm's own process imports this module
    (`loop.py` reads `read_proc`) and never needs the House."""
    from ..house import alert_key

    return alert_key(text)


class SwarmStep:
    """The House's swarm step (the module docstring)."""

    def __init__(self, root: str | Path, *, config: Mapping[str, Any] | None = None, python: str = sys.executable,
                 code_dir: Path = CODE_DIR, clock: Callable[[], float] = time.time, spawn: Callable[..., Any] | None = None,
                 kill: Callable[[int, int], None] = os.kill, mirror_limit: int = 200,
                 proc: Callable[[int], tuple[str, str] | None] | None = None):
        self.root = Path(root)
        self.config = config
        self.python = python
        self.code_dir = Path(code_dir)
        self.clock = clock
        self.spawn = spawn or self._popen
        self.kill = kill
        self.proc = proc or read_proc
        self.mirror_limit = int(mirror_limit)
        self.last_start = float("-inf")
        self.failed_starts = 0
        self.terminating: tuple[int, float, str | None] | None = None
        self.child: Any = None
        self.child_locked = False
        self.child_accounted = True
        self.alerts: list[str] = []
        #: Rows the last `mirror` skipped because the ledger does not know their kind, by kind (see the module docstring).
        self.unknown_kinds: dict[str, int] = {}
        #: Rows the last `mirror` skipped because the ledger refused them one by one, by folded reason: its `count`, the
        #: first such row's `kind` and the reason's `text`.
        self.failed_rows: dict[str, dict[str, Any]] = {}
        self.nightly = NightlySupervisor(self.root, code_dir=self.code_dir, python=self.python)
        self.pool_cleanup = StoppedPoolCleanup(self.root)

    # ------------------------------------------------------------------ the House calls this
    def tick(self, house: Any = None, open_for_business: bool = True) -> dict[str, Any]:
        # A House paused for maintenance (or with its meter stopped) starts no new paid work: it starts no swarm. One
        # already running goes on (the Gym trains through a pause); `<state>/swarm.stop` is how to stop it.
        out: dict[str, Any] = {"process": self.supervise(may_start=open_for_business)}
        out["pool_cleanup"] = self.pool_cleanup.tick(stopped=(
            (not out["process"].get("enabled") or bool(self.stopped())) and not out["process"].get("running")))
        try:
            out["nightly"] = self.nightly.tick(may_start=open_for_business)
        except Exception as exc:  # the collector never blocks the House's trading/marking path
            out["nightly"] = {"error": f"{type(exc).__name__}: {str(exc)[:160]}"}
        ledger = getattr(house, "ledger", None)
        if ledger is not None:
            mirrored = False
            try:
                out["mirrored"] = self.mirror(ledger)
                mirrored = True
            except Exception as exc:  # noqa: BLE001 - a mirror failure is reported, never raised into the tick
                out["mirror_error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
            # What the rows the mirror handled said, even when a failure of the ledger stopped it part way.
            if self.unknown_kinds:
                out["mirror_unknown_kinds"] = dict(self.unknown_kinds)
            if self.failed_rows:
                out["mirror_failed_rows"] = {key: entry["count"] for key, entry in self.failed_rows.items()}
            try:
                self.mirror_notices(house)
            except Exception as exc:  # noqa: BLE001 - telling the House never breaks the tick
                out["mirror_notice_error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
            try:
                self.mirror_health(house, None if mirrored else out.get("mirror_error"))
            except Exception as exc:  # noqa: BLE001 - reporting on the mirror never breaks the tick either
                out["mirror_health_error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
        return out

    # ------------------------------------------------------------------ supervise
    def heartbeat(self) -> dict[str, Any] | None:
        try:
            return json.loads((self.root / HEARTBEAT).read_text())
        except (OSError, ValueError):
            return None

    def lock_info(self) -> dict[str, Any]:
        try:
            return json.loads((self.root / LOCK_FILE).read_text() or "{}")
        except (OSError, ValueError):
            return {}

    def locked(self) -> bool:
        """A swarm process holds the single-instance lock (`<state>/swarm.lock`, an exclusive flock it keeps for its life):
        the one test of "a swarm is running" that a reused pid or a slow first heartbeat cannot fool."""
        return lock_held(self.root / LOCK_FILE)

    def child_alive(self) -> bool:
        return self.child is not None and self.child.poll() is None

    def verified(self, pid: Any, start: Any) -> bool:
        """`pid` is the swarm this House runs: never this process or its parent, its command line is `league.swarm` on
        this state root, and it started when the lock says it did (a reused pid fails that)."""
        try:
            pid = int(pid)
        except (TypeError, ValueError):
            return False
        if pid <= 1 or pid in (os.getpid(), os.getppid()):
            return False
        seen = self.proc(pid)
        if not seen:
            return False
        cmdline, started = seen
        return "league.swarm" in cmdline and str(self.root) in cmdline and (start is None or str(started) == str(start))

    def stopped(self) -> str:
        for stop in (self.root / "STOP", self.root.parent / "STOP", self.root / "swarm.stop"):
            if stop.exists():
                return f"{stop.name} is down"
        return ""

    def supervise(self, *, may_start: bool = True) -> dict[str, Any]:
        settings = settings_mod.load(self.root, config=self.config)
        now = self.clock()
        beat = self.heartbeat() or {}
        lock = self.lock_info()
        held = self.locked()
        if held and self.child_alive():
            self.child_locked = True
        running = held or self.child_alive()
        age = now - float(beat.get("at") or 0.0) if beat else None
        info: dict[str, Any] = {"enabled": bool(settings.get("enabled")), "running": running, "pid": lock.get("pid") if held else None,
                                "heartbeat_age": None if age is None else round(age, 1), "release": beat.get("release")}
        if self.terminating is not None:
            tpid, since, tstart = self.terminating
            if running:
                if now - since >= 30 and self.verified(tpid, tstart):
                    self._signal(tpid, signal.SIGKILL)
                info["action"] = "terminating"
                return info
            self.terminating = None
        why_not = "" if settings.get("enabled") else "disabled"
        why_not = why_not or self.stopped()
        if why_not:
            info["idle"] = why_not
            return info  # the swarm leaves by itself on a STOP file or when disabled; nothing to start
        if running:
            if not held:
                return info  # our child, still starting: it has not taken the lock yet
            stale = age is not None and age >= float(settings.get("stale_heartbeat_seconds", 240)) and \
                now - self.last_start >= float(settings.get("stale_heartbeat_seconds", 240))
            release = lock.get("release") or beat.get("release")
            other = release not in (None, str(self.code_dir)) and now - float(beat.get("started_at") or 0) > 60
            if stale or other:
                why = "its heartbeat is stale" if stale else "it runs another release"
                if self.verified(lock.get("pid"), lock.get("start")):
                    self._signal(int(lock["pid"]), signal.SIGTERM)
                    self.terminating = (int(lock["pid"]), now, lock.get("start"))
                    info["action"] = "restart: " + why
                else:
                    info["action"] = f"restart wanted ({why}), but it cannot verify the lock's pid as the swarm: not signalling"
            return info
        if not may_start:
            info["idle"] = "the House is not open for business"
            return info
        if self.child is not None and not self.child_accounted:
            self.child_accounted = True  # the last start has ended: did it ever take the lock (run), or die first?
            self.failed_starts = 0 if self.child_locked else self.failed_starts + 1
        backoff = min(1800.0, 30.0 * (2 ** max(0, min(self.failed_starts, 7) - 1)))
        if now - self.last_start < backoff:
            info["action"] = f"waiting {backoff - (now - self.last_start):.0f} s to start"
            return info
        self.last_start = now
        self.child_locked = False
        self.child_accounted = False
        try:
            rotate_log(self.root / LOG_FILE)
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
        """The swarm's new events into the House ledger (at most `mirror_limit`), idempotent by id. Returns the rows read
        (the cursor moves past all of them).

        - A row whose kind the ledger does not know is skipped and counted in `unknown_kinds`: the ledger would refuse it
          and roll the whole batch back, and the cursor would never move.
        - A batch the ledger refuses for another reason is written again row by row (`_one_by_one`). A row refused on its
          content (a `LedgerError`: a reused id with other content, a payload that is not canonical JSON or too big, a
          bad agent) is skipped and counted in `failed_rows`. Any other failure is the ledger's own (a locked or full
          disk). Then the cursor moves only past the rows handled before it, and the failure is raised, so
          `mirror_health` counts it.
        - `unknown_kinds`, `failed_rows` and `alerts` (a swarm status row's alert) cover the handled rows only, so a row
          the next tick reads again is not counted twice."""
        self.unknown_kinds, self.failed_rows, self.alerts = {}, {}, []
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
        # One entry per row read, in order: its seq, the ledger row to write (None: nothing to write), the unknown kind
        # it was dropped for (None: known) and the House alert its payload asks for (None: none).
        plan: list[tuple[int, dict[str, Any] | None, str | None, str | None]] = []
        names: dict[str, list[str]] = {}
        for r in rows:
            if r["kind"] in SKIPPED_KINDS:
                plan.append((r["seq"], None, None, None))
                continue
            if r["kind"] not in LEDGER_KINDS:
                plan.append((r["seq"], None, str(r["kind"])[:80], None))
                continue
            payload = dict(r["payload"]) if isinstance(r["payload"], dict) else {"value": r["payload"]}
            said = None
            if r["kind"] == "swarm.status" and payload.get("alert"):
                said = str(payload.get("text") or payload.get("action") or "an alert")[:300]
            if r["kind"] in PUBLIC_KINDS:
                # The second wall (the researcher filtered the note first): a public row carries words only.
                fid = r["family"] or ""
                if fid not in names:
                    names[fid] = self._param_names(fid)
                payload = public_payload(r["kind"], payload, names[fid])
                if payload is None:
                    plan.append((r["seq"], None, None, said))
                    continue
            payload["swarm_seq"] = r["seq"]
            payload["swarm_at"] = r["at"]
            plan.append((r["seq"], {"kind": r["kind"], "payload": payload, "agent": r["family"] or "house",
                                    "id": f"swarm:{r['seq']}", "public": r["kind"] in PUBLIC_KINDS}, None, said))
        batch = [row for _, row, _, _ in plan if row is not None]
        handled, failure = len(plan), None
        if batch:
            try:
                ledger.append_many(batch)
            except Exception:  # noqa: BLE001 - the ledger rolled the batch back; row by row says which row, or the ledger
                handled, failure = self._one_by_one(ledger, plan)
        for _, _, unknown, said in plan[:handled]:
            if unknown is not None:
                self.unknown_kinds[unknown] = self.unknown_kinds.get(unknown, 0) + 1
            if said is not None:
                self.alerts.append(said)
        if handled:
            tmp = self.root / (MIRROR_CURSOR + ".tmp")
            tmp.write_text(json.dumps({"seq": plan[handled - 1][0], "at": self.clock()}))
            tmp.replace(self.root / MIRROR_CURSOR)
        if failure is not None:
            raise failure
        return len(rows)

    def _one_by_one(self, ledger: Any, plan: list[tuple[int, dict[str, Any] | None, str | None, str | None]]
                    ) -> tuple[int, Exception | None]:
        """Write `plan`'s rows one at a time, after the ledger refused them as one batch. A row the ledger refuses on its
        content (`LedgerError`) is skipped and counted in `failed_rows` by its folded reason. Returns how many of `plan`'s
        entries were handled, and the failure that stopped it (None when every entry was handled): any other exception
        is the ledger's own, and the rows from there on wait for the next tick."""
        for index, (_, row, _, _) in enumerate(plan):
            if row is None:
                continue
            try:
                ledger.append_many([row])
            except LedgerError as exc:
                reason = f"{type(exc).__name__}: {str(exc)[:200]}"
                entry = self.failed_rows.setdefault(_alert_key(reason), {"count": 0, "kind": row["kind"], "text": reason})
                entry["count"] += 1
            except Exception as exc:  # noqa: BLE001 - the ledger itself failed: stop, and let the tick report it
                return index, exc
        return len(plan), None

    def _failing(self) -> dict[str, Any]:
        return self._read_state(MIRROR_FAILING)

    def _read_state(self, name: str) -> dict[str, Any]:
        try:
            state = json.loads((self.root / name).read_text())
            return state if isinstance(state, dict) else {}
        except (OSError, ValueError):
            return {}

    def _write_state(self, name: str, state: Mapping[str, Any]) -> None:
        tmp = self.root / (name + ".tmp")
        tmp.write_text(json.dumps(state))
        tmp.replace(self.root / name)

    def _notices(self) -> dict[str, dict[str, Any]]:
        """`MIRROR_NOTICES`, each of its three maps present (see the constant)."""
        notes = self._read_state(MIRROR_NOTICES)
        return {part: dict(notes[part]) if isinstance(notes.get(part), dict) else {} for part in ("kinds", "reasons", "errors")}

    def _save_notices(self, notes: dict[str, dict[str, Any]]) -> None:
        now = self.clock()
        notes["errors"] = {key: at for key, at in notes["errors"].items()
                           if isinstance(at, (int, float)) and now - at < MIRROR_ERROR_COOLDOWN_SECONDS}
        for part in ("kinds", "reasons"):  # oldest first: dicts keep the order they were told in
            notes[part] = dict(list(notes[part].items())[-MIRROR_NOTICES_KEPT:])
        self._write_state(MIRROR_NOTICES, notes)

    def mirror_notices(self, house: Any) -> None:
        """Tell the House what the last `mirror` handled: each swarm status row's alert (a warning each, as always), ONE
        warning the first time a kind the ledger does not know is dropped (naming the kind), and ONE warning for each new
        reason the ledger refused a row for (`failed_rows`). What it has said is kept in `MIRROR_NOTICES`, so neither a
        later tick nor a restart says it again. A kind or reason is marked told only once its alert is written, so an
        alert that fails is tried again when the next such row comes."""
        alert = getattr(house, "alert", None)
        if not callable(alert):
            return
        for text in self.alerts:
            alert("warning", f"swarm: {text}")  # the owner hears it (the House's ops.alert)
        if not (self.unknown_kinds or self.failed_rows):
            return
        notes = self._notices()
        told = False
        try:
            for kind, count in self.unknown_kinds.items():
                if kind in notes["kinds"]:
                    continue
                alert("warning", f"swarm: the mirror dropped {count} row(s) of kind {kind}, which the House ledger does not "
                                 "know. It keeps dropping them (the swarm's own table keeps them). To mirror them, add the kind "
                                 "to league.ledger.KINDS; to keep them private, add it to hook.SKIPPED_KINDS.",
                      swarm_kind=kind, dropped=count)
                notes["kinds"][kind], told = now_iso(self.clock), True
            for key, entry in self.failed_rows.items():
                if key in notes["reasons"]:
                    continue
                alert("warning", f"swarm: the House ledger refused {entry['count']} mirrored row(s) one by one, first a "
                                 f"{entry['kind']} row ({entry['text']}). The mirror skipped them and moved on; it skips any "
                                 "row refused for this reason again without a new alert.",
                      reason=key, swarm_kind=entry["kind"], skipped=entry["count"])
                notes["reasons"][key], told = now_iso(self.clock), True
        finally:
            if told:  # what was said before an alert failed stays said
                self._save_notices(notes)

    def mirror_health(self, house: Any, error: str | None) -> None:
        """Count one mirror, failed (`error`) or not, into the run of failures in a row (`MIRROR_FAILING`), and tell the
        House once. The same error (`league.house.alert_key`, the House's own fold: UUIDs and every token with a digit)
        `MIRROR_ALERT_AFTER` times in a row is ONE error alert carrying the run's `began_at` and its length. A success
        after that is an info with how long it lasted. An error already said within `MIRROR_ERROR_COOLDOWN_SECONDS` is not
        said again (`MIRROR_NOTICES` `errors`), so a mirror that keeps failing and recovering is not an error every few
        ticks; a run whose error was held back is said once the cooldown is over, if the run goes on. Sept 26-27, 2026:
        every batch failed for 14 hours on two kinds the ledger did not know, the error went only into the tick's
        summary, and the site's swarm news stopped without a word."""
        path = self.root / MIRROR_FAILING
        alert = getattr(house, "alert", None)
        if error is None:
            if not path.exists():
                return
            run = self._failing()
            path.unlink(missing_ok=True)
            if run.get("alerted") and callable(alert):
                began = float(run.get("since") or self.clock())
                alert("info", f"swarm: the mirror into the House ledger works again after {int(run.get('count') or 0)} failed "
                              f"tick(s) since {now_iso(lambda: began)}; the swarm's news reaches the site again.",
                      began_at=now_iso(lambda: began), failures=int(run.get("count") or 0))
            return
        now = self.clock()
        key = _alert_key(error)
        run = self._failing()
        if run.get("key") != key:
            run = {"key": key, "since": now, "count": 0, "alerted": False}
        run.update(count=int(run.get("count") or 0) + 1, error=str(error)[:300], last=now)
        if run["count"] >= MIRROR_ALERT_AFTER and not run.get("alerted") and callable(alert):
            notes = self._notices()
            said = notes["errors"].get(key)
            if not isinstance(said, (int, float)) or now - said >= MIRROR_ERROR_COOLDOWN_SECONDS:
                began = float(run["since"])
                try:
                    alert("error", f"swarm: the mirror into the House ledger has failed {run['count']} ticks in a row since "
                                   f"{now_iso(lambda: began)} ({str(error)[:200]}); the site gets no swarm notes, births or "
                                   "retirements until it works again.",
                          began_at=now_iso(lambda: began), failures=run["count"])
                    run["alerted"] = True
                    notes["errors"][key] = now
                    self._save_notices(notes)
                except Exception:  # noqa: BLE001 - a ledger that cannot take the alert is tried again next tick
                    pass
        self._write_state(MIRROR_FAILING, run)

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


def lock_held(path: Path) -> bool:
    """Someone holds an exclusive flock on `path` (tried without waiting, released at once)."""
    import fcntl

    if not path.exists():
        return False
    try:
        with open(path, "a+") as handle:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                return True
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            return False
    except OSError:
        return False


def read_proc(pid: int) -> tuple[str, str] | None:
    """(the command line, the start time in clock ticks) of a live process, from /proc; None when it is gone."""
    try:
        cmdline = Path(f"/proc/{int(pid)}/cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8", "replace").strip()
        stat = Path(f"/proc/{int(pid)}/stat").read_text()
        return cmdline, stat.rsplit(")", 1)[1].split()[19]
    except (OSError, IndexError, ValueError):
        return None


def rotate_log(path: Path, *, max_bytes: int = 20 * 2 ** 20) -> None:
    """Keep the swarm's log bounded: over `max_bytes` it becomes `<log>.1` (the one before is dropped)."""
    try:
        if path.stat().st_size > max_bytes:
            path.replace(path.with_name(path.name + ".1"))
    except OSError:
        pass


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
    """Set `house.swarm` when the swarm is enabled. The live path's House (#362) has its own `site_inputs()`, which
    merges `house.swarm.site_inputs()` with its own; a House without one gets the swarm's feed as its `site_inputs`
    (the publisher's hook), so the page shows the swarm's agents, Gym and compute until then. Its compute is the
    swarm's own spend only: in swarm mode the House's Sail meter (`Budget`) is off."""
    if (not settings_mod.load(root, config=config).get("enabled")
            and read_json(Path(root) / "data-nightly.json").get("enabled") is not True):
        return None
    step = SwarmStep(root, config=config)
    house.swarm = step
    if not hasattr(house, "site_inputs"):
        house.site_inputs = step.site_inputs
    return step


__all__ = ["SwarmStep", "attach", "PUBLIC_KINDS"]
