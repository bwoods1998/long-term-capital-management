"""THE FORWARD SCREEN's job (FWD1-R, the captain's A33): one append-only verdict a lineage of the forward record, from
the sessions after its code and the screen were pinned. The rule is league/ops/fwd1_rule.py; this module reads the
forward record, keeps the verdicts and writes the permit file the swarm reads.

Owner: the FWD1-R build. Protected (league/ops/ is FORBIDDEN to every role). Ops only (no module of league/swarm,
league/equity, league/live or league/gym imports it): it reads `<state>/forward.sqlite` READ-ONLY (E3's record and E4's
panel twin, league/ops/forward_db.py, forward_xs.py) and the swarm store read-only, and writes only its own
`<state>/forward-screen.sqlite` (0600, WAL, append-only: `SCHEMA`), the permit file (`PERMITS`: ids and words only)
and the operator's report (`REPORT`). It moves no money, opens no seat and edits no setting: a seat is the swarm's
(league/swarm/elane_forward.py), through the lane's own seat machinery, behind a switch that ships OFF.

WITH ITS SWITCHES OFF NOTHING IS JUDGED: the job is a `skipped` receipt while `elane.fwd1.mode` is "off" (the code's
default; policy.json ships "record"), while `elane.forward.mode` is "off" (no record), with no pin
(`fwd1_rule.rule()`: NO PIN, NO VERDICT; the forward record keeps recording), and inside 09:00-17:30 New York on a
session (it may run the decider child).

THE CLOCK (`pinned`, the table `fwd1_pins`): the first time the job runs under a pin, the time the release that carries
it began running (`funnel.release_start` of the running release; the sighting's own time when the deploy record has
none) is written once a receipt sha, with FWD1_START = `fwd1_rule.start_after(pinned_at)`. Nothing before it is ever
judged, and a lineage registered earlier enters mid-run from it.

THE NIGHT (`night`; after each of the record's two nights, E3's and the panel's, in the registry):
1. THE LINEAGES (`fwd1_lineages`, one row a lineage). Every lineage of the registry but the controls, at its first
   sighting: its representative (`representative`), type, case (`case_of`: the sealed facts of every family and pid of
   the lineage; a panel pre-check record counts only when it says `reached`), FWD1_START and its mechanism cell (lane
   / agenda / universe group). Not judged, with the reason: an ETF lineage that reached a sealed pre-check (no forward
   verdict for an S1/S2 look), a lineage that already trades (a live row: it passed a sealed look), a type FWD1-R does
   not cover (a stock program); a representative with no counted day yet is simply pending.
   THE REPRESENTATIVE BEFORE ANY FORWARD DAY (`repick`, after `register` each run). The rule fixes the representative
   before any forward day of the lineage exists, not at its first sighting. A sighting can come between a failed
   version's registration and a passing one's with the same first_day (Oct 15: five lineages sighted on a
   Train-failed v1, four of them families whose later version passed and one through a rebirth in the same lineage).
   So each run re-reads the representative of a sighted lineage while NO FORWARD DAY of it exists (`frozen`): no row
   of the forward record for any pid of the lineage (`RECORD_DAY_TABLES`), no night of the record through its
   first_day (`fwd_runs.through`), its first_day's session not yet open, and no judge row for it (a checkpoint, a
   pending reading, a verdict, sides, a floor, or any event but `registered`, `repicked` and `kept`). The job is
   quiet from 09:00 New York on a session, so the last run that can re-pick is the night before the first_day (or
   a run before that morning's pre-open). When the rule now gives another pid with the same first_day and start, and
   that pid keeps the row's type, case, judged flag and reason, the row is rewritten in place to it, in one
   transaction with an append-only `repicked` event (old pid, new pid, the old row's ids and words). A re-pick
   changes which version is judged, never what it is judged as: a case or judged flag read again from sealed facts
   learned after the sighting would give the lineage another record than one whose better version was registered
   before it (that one is voided by the judge, 4). The store's trigger allows that UPDATE alone (`REPICK_ONLY`).
   Once any forward day or judge row exists the row is frozen. A better pid that is not taken (frozen, or another
   type, case, flag or reason) is written once as a `kept` event and the job warns (`repick_kept`). A forward record
   that cannot be read re-picks nothing (fail closed). The placebo seed reads the representative's row hash
   (`fwd1_rule.placebo_seed`): a re-pick before any day changes the seed, and it is fixed from then on.
2. THE CHECKPOINTS (`fwd1_checks`, written once a lineage and checkpoint: the checkpoint of record, never recomputed).
   The representative's counted days (`forward_db.counted_days`) under ONE engine id from FWD1_START; each day's SIDES
   (`fwd1_sides`: the weights of the shadow's lots in and out that session, which the record does not keep: read from
   the representative's own forward run in this job's child, E3's `Shadow` slice or package J's panel run, over every
   counted day it has, once a day) kept where that run IS the record's day: its r reproduces the stored one to
   `forward_db.TOL`, or THE DAY WAS RESTATED (the vendor rescales the whole adjusted history at a dividend or a split,
   E3 keeps the first write, so no later run reproduces the stored r of a day before an ex-day: the run made the same
   orders that session, its lots in and out as the record counts them, from inputs the restatement moved, its bars
   hash of the day's decision not the stored one); `fwd_ll` (ETF); `fwd_lotgap` for g. At each checkpoint the
   representative has reached, in order: t_k, S_k, S15_k (THE CHECKPOINT'S READING: a would-be pass's is kept in
   `fwd1_pending` on the night it is first read, and a checkpoint that waits on its floor or its placebo leg is judged
   on it, never on a second read of inputs that changed since); below the global bar it fails that checkpoint with no
   floor read; at or above, the own floor (`fwd1_floors`, computed once a representative on its Train-era runs in the
   job's own decider child) gives c_used, and a PANEL lineage at or above it draws its placebo leg (one panel run over
   its judged sessions, 999 draws under the FWD1 seed; THE PLACEBO SPAN: a session of the span that is not counted
   fails the leg closed only when it is the program's own, a disqualified row; one the House left out waits). The
   first checkpoint that passes is the PASS; none by 60 is the FAIL.
3. AN ENGINE CHANGE (`engine_reading`): a pending lineage whose checkpoints were read under an older id is read on,
   under the newest, only once the newest holds its rows for every judged day; until then it WAITS (E3's night opens
   a new id and writes the ETF rows, the panel night writes the panel rows hours later, a program the budget left
   stale is written a night later: never a void for a row not written yet). Then each judged day is compared on r,
   w, b and r15 (`ENGINE_TOUCH`): one that moved only because the vendor restated the store's history (both bars
   hashes known and different, and the record's own `restated` event of the pid under the old id, bars "moved",
   covering the day) is carried with the rest, with an `engine_switched` event naming the pid; any other move, or a
   judged day not counted under the new id, is a touch.
4. THE VERDICT (`fwd1_verdicts`, one a lineage, for good): "pass", "fail" or "void" (a case-N lineage that reached a
   sealed pre-check after FWD1_START; an engine change that touched a pending representative's judged days: one engine
   id a verdict). A pass keeps its sentence (`fwd1_rule.beside`, operator-only: it holds the t and the shadow P&L) and
   its words (`fwd1_rule.words`: ids and words, the permit's). Nothing judges a lineage after it.
5. THE PERMIT FILE (`write_permits`, `PERMITS`): every lineage FWD1 judges with its status (`STATUSES`), its
   FWD1_START ("start", an ISO date: L5, A48) and, for a pass, its family, version, run sha, cell and words. IDS AND
   WORDS ONLY: no t, no P&L, no figure of a program (a date is none). The swarm reads it for two things only
   (league/swarm/elane_forward.py): a lineage pending, passed or failed takes no sealed Validation try while the seat
   switch is on, and a pass may take a seat, one live forward seat a mechanism cell, while it is on. L5 (A48): an
   index-only case-N lineage keeps its S2 try until the close of its FWD1_START session; the judge then voids it
   (A33 (4), 4 above: a case-N lineage that reached a sealed pre-check after FWD1_START). A loosening of A39's stated
   cost "while on, a lineage FWD1 lists takes no sealed S2 try". The swarm grants it only to the row's own family
   (the representative's, whose registry rows the void reads) and only for a row "start" after the file's top-level
   "start" (the pin's: an earlier first_day has forward days already); a row without "start" (a file of the earlier
   job) is refused as before (`elane_forward.untried`: fail closed). A lineage stopped (its representative stopped in
   the record), stalled (THE STALL RULE) or superseded (registered under another receipt) is listed as such and keeps
   its sealed path, as a void or an ineligible one does.
6. THE REPORT (`REPORT`, operator-only): per type and case the lineages by status, the registry's expected zero-edge
   passes against the observed (`fwd1_rule.expected_passes`), each pass's sentence and each stalled lineage's cause.
   POOL1 (A55a): a lineage on the pooled screen's POOL-route or hold list is left out of all of it until its unit's
   verdict is final, counted only as `pool_route` (`report`); every ETF lineage while that file fails closed.

A FAILURE OF THE HOUSE NEVER MARKS A PROGRAM: a run the child could not finish, a store under a lock, a run that does
not reproduce the record's day, rows not yet written under a new engine id, a placebo span the House left a session
out of: the checkpoint is left unwritten, and the next night reads the same first k counted days again. THE STALL RULE
(`STALL_NIGHTS`) bounds it: a lineage whose next step waited on the House on that many of the record's nights under
one engine id is STALLED (`stalled`): it costs no run and is reported, nothing marks it, and a new engine id (a whole
recompute) asks it again; a lineage that waited goes after those that did not, so it never takes the night's budget
from them. NOTHING OF E3's NIGHT CHANGES: no line of forward_shadow.py, forward_xs.py or forward_db.py is touched (E3's
seal holds its modules' imports to its list), and the record's store is opened read-only.

THE ONE CORE (`HouseRuns`, `night`, `run`): ONE OPEN OF THE PANEL STORE A JOB RUN (one panel night reused by every
panel run: the ops child's address space is capped 500 MB above its start, and each open maps the two bar arrays);
E4's CLOCK RULE (`elane_xs.steady`) on every panel run; ONE BUDGET A NIGHT (`elane.fwd1.cpu_seconds_night` of child
seconds shared by the night's two runs: `fwd1_runs`, `night_spent`); THE DEADLINE (the earlier of the job's wall and
the next pre-open, less `MARGIN_S`: no run is started, and none is given seconds, past it; a start too near the
pre-open is a skipped receipt). A lineage left over waits a night.

Standard library at import; numpy, league.equity and league.xs inside the functions that run programs.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import os
import sqlite3
import time
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Collection, Mapping, Sequence

from . import forward_db
from . import fwd1_rule as R

JOB = "forward_screen"
DB = "forward-screen.sqlite"
#: The permit file (ids and words only) the swarm reads: league/swarm/elane_forward.py `PERMITS` (a test holds the two
#: equal), and the operator's report. Its version stays 1 with each row's added "start" (L5, A48): the swarm reads a
#: row without it as before (refused while listed pending, pass or fail).
PERMITS = "forward-screen-permits.json"
PERMITS_VERSION = 1
REPORT = "forward-screen-report.json"
#: `elane.fwd1.*` (policy.json ships mode "record", seats "off"; the code defaults are both off).
MODES = ("off", "record")
SEATS = ("off", "on")
DEFAULTS: dict[str, Any] = {"mode": "off", "seats": "off", "cpu_seconds_night": 900, "run_budget_seconds": 300}
BOUNDS: dict[str, tuple[int, int]] = {"cpu_seconds_night": (60, 2400), "run_budget_seconds": (30, 600)}
VERDICTS = ("pass", "fail", "void")
#: Why a lineage is not judged (`fwd1_lineages.why`).
NOT_JUDGED = {
    "sealed": "an ETF lineage that reached a sealed pre-check: no forward verdict for an S1/S2 look (FWD1-R F3)",
    "live": "a lineage that already trades (a live row: it passed a sealed look)",
    "type": "a program type FWD1-R does not judge (an ETF or a panel lineage only)",
    "family": "its family cannot be read in the swarm store",
}
#: The registry reasons a representative is chosen among first (FWD1-R: the lowest pid of these, else the lowest pid).
PREFERRED = ("train_pass", "seed", "live")
#: The tags of the forward record that say a version reached a sealed pre-check or look (forward_register.py).
SEALED_TAGS = ("try", "try_entered", "look_pass", "look_fail")
#: An engine change touches a judged day when its r, w, b or r15 moves by more than this (forward_db.TOL).
ENGINE_TOUCH = forward_db.TOL
#: The swarm-store family-state keys that say a family reached a sealed pre-check or look (league/swarm/elane.py
#: `TRY_KEY`, `VERDICTS_KEY`, `LOOK_KEY`; league/swarm/elane_xs.py `PRECHECK_KEY`, `LOOK_KEY`: a test holds them).
#: The panel's pre-check record counts only when it says `reached` True: elane_xs writes `reached` False when it
#: refuses a version before any Validation read (a Train segment its own errors ended, the same lineage as a twin).
SEALED_STATE = ("elane_try", "elane_verdicts", "elane_look", "elane_xs_precheck", "elane_xs_look")
PRECHECK_STATE = "elane_xs_precheck"
EVENT_KINDS = ("pinned", "registered", "repicked", "kept", "engine_switched", "ineligible", "void", "house", "waited",
               "stalled")
#: THE REPRESENTATIVE BEFORE ANY FORWARD DAY (`repick`, `frozen`): the forward record's per-pid rows (league/ops/
#: forward_db.py: E3's night and the panel night write `fwd_days` and `fwd_checks`, the twins `fwd_ll` and `fwd_twins`,
#: a live instance's closed real lots `fwd_lotgap` and its participation `fwd_part`). Any one of them for any pid of a
#: lineage counts as a forward day of it.
RECORD_DAY_TABLES = ("fwd_days", "fwd_checks", "fwd_ll", "fwd_twins", "fwd_lotgap", "fwd_part")
#: The events of a lineage that are no step of the judge: any other kind freezes its representative.
UNJUDGED_EVENTS = ("registered", "repicked", "kept")
#: The columns a re-pick keeps (`repick`, `REPICK_ONLY`): it changes which version is judged, never what it is
#: judged as.
REPICK_KEEPS = ("type", "case_", "judged", "why")
REPICK_WHY = "a better version registered before any forward day of the lineage"
KEPT_WHY = "a better version of the same first_day was not taken: the representative stays as sighted"
APPEND_ONLY_ERROR = "forward-screen.sqlite is append-only"
#: THE STALL RULE (the reviews' fix): a lineage whose next step waits on the House (its sides cannot be read from its
#: own forward run, its rows under a new engine id have not come, a placebo span holds a session the House left out)
#: on this many of the forward record's nights under one engine id is STALLED: it costs no run and is reported, and
#: nothing marks it, until the record opens a new engine id (a whole recompute on the store as it then is), when it is
#: asked again. A night is a night of the record (`MAX(fwd_runs.through)`, E3's and the panel's): a weekend, or a
#: second run of the job on one night, counts none.
STALL_NIGHTS = 5
#: The statuses a lineage the job judges can stand at besides its verdict (`status_rows`): "pending" (asked each
#: night), "ineligible" (no own floor, stated), "stopped" (its representative is stopped in the forward record: no row
#: comes; pending again once it is resumed), "stalled" (THE STALL RULE) and "superseded" (registered under another
#: receipt's pin: this receipt judges it no further).
STATUSES = ("pending", "pass", "fail", "void", "ineligible", "stopped", "stalled", "superseded", "not_judged")
#: ONE BUDGET A NIGHT: the child seconds of the job's runs (`fwd1_runs`) that ended in this window count against
#: `cpu_seconds_night`, so the night's two runs (after each of the record's two nights) share it.
NIGHT_WINDOW_S = 12 * 3600.0
#: THE DEADLINE: no run is started, and none is given seconds, past the earlier of the job's own wall (the registry's,
#: a test holds them equal) less `MARGIN_S` from its start and the next pre-open (league/ops/registry.py `preopen`:
#: an hour before the open) less `MARGIN_S`. A run's budget is the lower of `run_budget_seconds` and what is left.
WALL_S = 1800
MARGIN_S = 120.0
PREOPEN_BEFORE_S = 3600.0
#: Less room than this before the deadline starts no run (the House's: asked again the next night).
MIN_RUN_S = 30.0

_TABLES = """
CREATE TABLE IF NOT EXISTS fwd1_pins (sha TEXT PRIMARY KEY, release TEXT NOT NULL, pinned_at REAL NOT NULL,
  start TEXT NOT NULL, evidence TEXT NOT NULL, at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS fwd1_sides (pid INTEGER NOT NULL, day TEXT NOT NULL, engine INTEGER NOT NULL,
  sides REAL NOT NULL, at REAL NOT NULL, PRIMARY KEY (pid, day, engine)) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS fwd1_lineages (lineage TEXT PRIMARY KEY, type TEXT, rep INTEGER, family TEXT,
  version INTEGER, run_sha TEXT, row_hash TEXT, case_ TEXT, judged INTEGER NOT NULL, why TEXT, start TEXT,
  cell TEXT, receipt TEXT NOT NULL, versions INTEGER NOT NULL, at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS fwd1_floors (pid INTEGER PRIMARY KEY, case_ TEXT NOT NULL, k_own INTEGER, cells TEXT,
  drift REAL, why TEXT, seconds REAL, at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS fwd1_checks (lineage TEXT NOT NULL, k INTEGER NOT NULL, pid INTEGER NOT NULL,
  engine INTEGER NOT NULL, day TEXT NOT NULL, t REAL, s REAL NOT NULL, s15 REAL NOT NULL, g_bp REAL NOT NULL,
  ll INTEGER NOT NULL, count INTEGER, draws INTEGER, c_used REAL, passed INTEGER NOT NULL, why TEXT,
  at REAL NOT NULL, PRIMARY KEY (lineage, k)) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS fwd1_verdicts (lineage TEXT PRIMARY KEY, pid INTEGER NOT NULL,
  verdict TEXT NOT NULL CHECK (verdict IN ('pass','fail','void')), k INTEGER, day TEXT, c_used REAL, why TEXT,
  beside TEXT, words TEXT, at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS fwd1_events (seq INTEGER PRIMARY KEY AUTOINCREMENT, at REAL NOT NULL, kind TEXT NOT NULL,
  lineage TEXT, pid INTEGER, once TEXT, payload TEXT NOT NULL DEFAULT '{}');
CREATE UNIQUE INDEX IF NOT EXISTS fwd1_events_once ON fwd1_events(kind, lineage, once) WHERE once IS NOT NULL;
CREATE TABLE IF NOT EXISTS fwd1_pending (lineage TEXT NOT NULL, k INTEGER NOT NULL, engine INTEGER NOT NULL,
  pid INTEGER NOT NULL, day TEXT NOT NULL, t REAL, s REAL NOT NULL, s15 REAL NOT NULL, g_bp REAL NOT NULL,
  ll INTEGER NOT NULL, at REAL NOT NULL, PRIMARY KEY (lineage, k, engine)) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS fwd1_runs (seq INTEGER PRIMARY KEY AUTOINCREMENT, started REAL NOT NULL,
  finished REAL NOT NULL, seconds REAL NOT NULL, lineages INTEGER, at REAL NOT NULL);
"""
#: `fwd1_pending`: A CHECKPOINT'S READING, first write stands (the review's fix): its t, sums, haircut and live-like
#: flag read on the night the representative first has k counted days, kept while the checkpoint waits on its floor or
#: placebo leg (the budget, the House), so a later night judges those values and never a second read of inputs that
#: changed since (a late `fwd_ll` row, a lot gap, an audit mark). `fwd1_runs`: one row a run of the job, its child
#: seconds (ONE BUDGET A NIGHT).
TABLES = ("fwd1_pins", "fwd1_sides", "fwd1_lineages", "fwd1_floors", "fwd1_checks", "fwd1_verdicts", "fwd1_events",
          "fwd1_pending", "fwd1_runs")
#: THE ONE UPDATE THE STORE ALLOWS (`repick`): a `fwd1_lineages` row may change only to a new representative, with its
#: lineage, start, receipt, first-sighting time, type, case, judged flag and reason kept, after its `repicked` event
#: (once "<old pid>><new pid>") in the same transaction, and only while the judge holds no checkpoint, pending reading
#: or verdict of the lineage and no sides or floor of either pid. Every other UPDATE aborts as before. A store written
#: by an earlier build loses its unconditional `fwd1_lineages_no_update` trigger to this one on its next writable open
#: (no row is touched).
REPICK_ONLY = (
    "CREATE TRIGGER IF NOT EXISTS fwd1_lineages_repick_only BEFORE UPDATE ON fwd1_lineages WHEN NOT ("
    "NEW.lineage IS OLD.lineage AND NEW.start IS OLD.start AND NEW.receipt IS OLD.receipt AND NEW.at IS OLD.at "
    "AND NEW.type IS OLD.type AND NEW.case_ IS OLD.case_ AND NEW.judged IS OLD.judged AND NEW.why IS OLD.why "
    "AND NEW.rep IS NOT OLD.rep "
    "AND EXISTS (SELECT 1 FROM fwd1_events e WHERE e.kind = 'repicked' AND e.lineage = OLD.lineage "
    "AND e.pid = NEW.rep AND e.once = (OLD.rep || '>' || NEW.rep)) "
    "AND NOT EXISTS (SELECT 1 FROM fwd1_checks c WHERE c.lineage = OLD.lineage) "
    "AND NOT EXISTS (SELECT 1 FROM fwd1_pending p WHERE p.lineage = OLD.lineage) "
    "AND NOT EXISTS (SELECT 1 FROM fwd1_verdicts v WHERE v.lineage = OLD.lineage) "
    "AND NOT EXISTS (SELECT 1 FROM fwd1_sides s WHERE s.pid IN (OLD.rep, NEW.rep)) "
    "AND NOT EXISTS (SELECT 1 FROM fwd1_floors f WHERE f.pid IN (OLD.rep, NEW.rep))) "
    f"BEGIN SELECT RAISE(ABORT, '{APPEND_ONLY_ERROR}'); END;\n"
    "DROP TRIGGER IF EXISTS fwd1_lineages_no_update;\n")
SCHEMA = "PRAGMA recursive_triggers=ON;\n" + _TABLES + "".join(
    f"CREATE TRIGGER IF NOT EXISTS {t}_no_{verb.lower()} BEFORE {verb} ON {t} BEGIN SELECT RAISE(ABORT, "
    f"'{APPEND_ONLY_ERROR}'); END;\n" for t in TABLES for verb in ("UPDATE", "DELETE")
    if (t, verb) != ("fwd1_lineages", "UPDATE")) + REPICK_ONLY


# ------------------------------------------------------------------------------------------------------------ settings
def cfg(settings: Mapping[str, Any] | None) -> dict[str, Any]:
    """`elane.fwd1` in the swarm's settings: `mode` ("off" | "record"), `seats` ("off" | "on"), the night's child
    seconds and one run's. A malformed value is its default; an unreadable block is `DEFAULTS` (everything off)."""
    out = dict(DEFAULTS)
    raw = settings.get("elane") if isinstance(settings, Mapping) else None
    raw = raw.get("fwd1") if isinstance(raw, Mapping) else None
    if not isinstance(raw, Mapping):
        return out
    if raw.get("mode") in MODES:
        out["mode"] = raw["mode"]
    if raw.get("seats") in SEATS:
        out["seats"] = raw["seats"]
    for key, (low, high) in BOUNDS.items():
        value = raw.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) \
                or float(value) != int(value):
            continue
        out[key] = int(min(high, max(low, value)))
    return out


# --------------------------------------------------------------------------------------------------------- the store
def open_store(root: str | Path, *, readonly: bool = False) -> sqlite3.Connection:
    """`<root>/forward-screen.sqlite`, rows as `sqlite3.Row`: created 0600 (WAL) with `SCHEMA` when writable;
    `readonly`: `guard.connect_ro` (OperationalError when absent)."""
    path = Path(root) / DB
    if readonly:
        from . import guard

        db = guard.connect_ro(path)
        db.row_factory = sqlite3.Row
        return db
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        os.close(os.open(path, os.O_RDWR | os.O_CREAT, 0o600))
    db = sqlite3.connect(str(path), timeout=30.0)
    try:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=NORMAL")
        db.executescript(SCHEMA)
    except BaseException:
        db.close()
        raise
    return db


def event(store: sqlite3.Connection, kind: str, *, at: float, lineage: str | None = None, pid: int | None = None,
          once: str | None = None, payload: Mapping[str, Any] | None = None) -> bool:
    """One `fwd1_events` row (ids, counts and words only); with `once` at most one a (kind, lineage, once). Whether it
    was written. The caller commits."""
    if kind not in EVENT_KINDS:
        raise ValueError(f"no forward screen event kind {kind!r}")
    cursor = store.execute("INSERT OR IGNORE INTO fwd1_events(at, kind, lineage, pid, once, payload) VALUES (?,?,?,?,?,?)",
                           (float(at), kind, lineage, None if pid is None else int(pid), once,
                            json.dumps(dict(payload or {}), sort_keys=True, separators=(",", ":"))))
    return cursor.rowcount == 1


# ---------------------------------------------------------------------------------------------------------- the sides
def lot_sides(result: Mapping[str, Any]) -> dict[str, float]:
    """{ISO day: the sum of the weights of the run's lots entering or exiting that session} (a lot entering and one
    exiting the same session both count; the haircut is taken a side). ValueError on a weight that is not finite."""
    out: dict[str, float] = {}
    for lot in result.get("lots") or ():
        weight = lot.get("weight")
        if isinstance(weight, bool) or not isinstance(weight, (int, float)) or not math.isfinite(float(weight)):
            raise ValueError(f"lot {lot.get('lid')}: a weight that is not a number")
        for key in ("entry_day", "exit_day"):
            day = lot.get(key)
            if day not in (None, ""):
                day = str(day)[:10]
                out[day] = out.get(day, 0.0) + abs(float(weight))
    return out


# ------------------------------------------------------------------------------------------------------- the clock
def pinned(store: sqlite3.Connection, rule: Any, *, base: str | Path | None, release: str | Path | None,
           now: float) -> dict[str, Any]:
    """THE CLOCK (the module docstring): the pin's row, written once a receipt sha: {sha, release, pinned_at, start,
    evidence ("deploys" | "sighting")}. The deploy record's start of the running release when it has one at or before
    `now`, else `now`."""
    row = store.execute("SELECT * FROM fwd1_pins WHERE sha=?", (rule.receipt_sha256,)).fetchone()
    if row is not None:
        return dict(row)
    name = Path(release).name if release is not None else ""
    on_record = None
    if base is not None and name:
        try:
            from . import funnel

            on_record = funnel.release_start(base, name)
        except Exception:  # noqa: BLE001 - no record: the sighting's time
            on_record = None
    if on_record is not None and on_record > now:
        on_record = None
    at = float(now if on_record is None else on_record)
    start = R.start_after(at)
    with store:
        store.execute("INSERT OR IGNORE INTO fwd1_pins(sha, release, pinned_at, start, evidence, at) VALUES (?,?,?,?,?,?)",
                      (rule.receipt_sha256, name, at, start.isoformat(), "sighting" if on_record is None else "deploys",
                       float(now)))
        event(store, "pinned", at=now, once=rule.receipt_sha256,
              payload={"why": "the forward screen's pin was first seen running: nothing before its start is judged",
                       "release": name, "start": start.isoformat()})
    return dict(store.execute("SELECT * FROM fwd1_pins WHERE sha=?", (rule.receipt_sha256,)).fetchone())


# --------------------------------------------------------------------------------------------------- the lineages
def representative(rows: Sequence[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    """FWD1-R's representative of one lineage's registry rows (each {pid, reason, first_day, ...}): of the rows whose
    first_day is the lineage's earliest (the rows that existed before any forward day of the lineage could: no
    version is chosen after a forward day exists), the lowest pid whose reason is train_pass, seed or live, else the
    lowest pid. None for no row."""
    if not rows:
        return None
    first = min(str(r["first_day"]) for r in rows)
    batch = sorted((r for r in rows if str(r["first_day"]) == first), key=lambda r: int(r["pid"]))
    preferred = [r for r in batch if str(r["reason"]) in PREFERRED]
    return (preferred or batch)[0]


def _state(fam: Mapping[str, Any] | None) -> Mapping[str, Any]:
    state = (fam or {}).get("state")
    return state if isinstance(state, Mapping) else {}


def family_sealed(fam: Mapping[str, Any] | None) -> bool:
    """Whether a family's state says it reached a sealed pre-check or look (`SEALED_STATE`, any version): a Validation
    try, a Validation verdict, a pre-check record that says it was reached, or a look. A panel pre-check record with
    `reached` False is a refusal BEFORE any Validation read (league/swarm/elane_xs.py: a Train segment its own errors
    ended, the same lineage as a twin): no sealed data was read, so it is not a sealed pre-check."""
    state = _state(fam)
    for key in SEALED_STATE:
        value = state.get(key)
        if not isinstance(value, Mapping) or not value:
            continue
        if key == PRECHECK_STATE and value.get("reached") is False:
            continue
        return True
    return False


def type_of(row: Mapping[str, Any], fam: Mapping[str, Any] | None) -> str | None:
    """"PANEL" for a panel row, "ETF" for a row whose family's structure is "etf", else None (FWD1-R judges neither a
    stock program nor a control)."""
    from . import forward_xs

    if forward_xs.is_panel(row):
        return "PANEL"
    return "ETF" if str((fam or {}).get("structure") or "") == "etf" else None


def case_of(typ: str, sealed: bool) -> str | None:
    """The case at FWD1_START: "N" never sealed; a sealed PANEL lineage "XS1"; a sealed ETF lineage None (not judged)."""
    if not sealed:
        return "N"
    return "XS1" if typ == "PANEL" else None


def cell_of(typ: str, row: Mapping[str, Any], fam: Mapping[str, Any] | None) -> str:
    """The lineage's MECHANISM CELL (lane / agenda mechanism / universe group: the lane's own Train-map cell), as text."""
    spec = (fam or {}).get("spec")
    spec = spec if isinstance(spec, Mapping) else {}
    try:
        if typ == "PANEL":
            from ..swarm import elane_xs

            return elane_xs.cell_text(elane_xs.family_cell(fam))
        from ..swarm import elane_train

        symbols = (row.get("needs") or {}).get("symbols") if isinstance(row.get("needs"), Mapping) else None
        return elane_train.cell_text(elane_train.cell_of(spec.get("lane") or row.get("lane"), spec.get("agenda"),
                                                         list(symbols or [])))
    except Exception:  # noqa: BLE001 - a cell that cannot be read is its registry columns
        return f"{row.get('lane')} / {spec.get('agenda') or 'other'} / {row.get('ugroup')}"


def _registry(fdb: sqlite3.Connection) -> dict[str, list[dict[str, Any]]]:
    """{lineage: its registry rows but the controls (pid, key, family, version, lane, reason, ugroup, needs, run_sha,
    row_hash, first_day, created_at), pid order}."""
    out: dict[str, list[dict[str, Any]]] = {}
    for row in fdb.execute("SELECT pid, key, family, version, lane, reason, ugroup, lineage, needs, run_sha, row_hash, "
                           "first_day, created_at FROM fwd_registry WHERE reason != 'control' ORDER BY pid"):
        held = dict(row)
        try:
            held["needs"] = json.loads(held["needs"])
        except (TypeError, ValueError):
            held["needs"] = {}
        out.setdefault(str(held["lineage"]), []).append(held)
    return out


def _sealed_pids(fdb: sqlite3.Connection) -> set[int]:
    return {int(r[0]) for r in fdb.execute(
        f"SELECT DISTINCT pid FROM fwd_tags WHERE tag IN ({', '.join('?' * len(SEALED_TAGS))})", SEALED_TAGS)}


def sighting(lineage: str, rows: Sequence[Mapping[str, Any]], families: Mapping[str, Mapping[str, Any]], *,
             sealed_pids: set[int], pin_start: dt.date) -> dict[str, Any] | None:
    """A lineage's `fwd1_lineages` columns as a sighting now reads them (the module docstring, 1): its representative
    over `rows`, type, case, why it is not judged, FWD1_START, cell and how many versions, with the representative's
    `first_day` beside them (not a column). None for no row."""
    rep = representative(rows)
    if rep is None:
        return None
    fam = families.get(str(rep["family"]))
    typ = type_of(rep, fam)
    why = None
    case = None
    if fam is None:
        why = "family"
    elif typ is None:
        why = "type"
    elif any(str(r["reason"]) == "live" for r in rows):
        why = "live"
    else:
        sealed = any(int(r["pid"]) in sealed_pids for r in rows) or any(
            family_sealed(families.get(str(r["family"]))) for r in rows)
        case = case_of(typ, sealed)
        if case is None:
            why = "sealed"
    start = R.forward_start(dt.date.fromisoformat(str(rep["first_day"])), pin_start)
    return {"lineage": lineage, "type": typ, "rep": int(rep["pid"]), "family": rep["family"], "version": rep["version"],
            "run_sha": rep["run_sha"], "row_hash": rep["row_hash"], "case_": case, "judged": 0 if why else 1,
            "why": None if why is None else NOT_JUDGED[why], "start": start.isoformat(),
            "cell": cell_of(typ or "ETF", rep, fam), "versions": len(rows), "first_day": str(rep["first_day"])}


def register(store: sqlite3.Connection, fdb: sqlite3.Connection, families: Mapping[str, Mapping[str, Any]], *,
             rule: Any, pin_start: dt.date, now: float) -> int:
    """THE LINEAGES' first sightings (the module docstring, 1): one `fwd1_lineages` row each (`repick` alone may
    rewrite one, before any forward day of it). How many it wrote."""
    known = {str(r[0]) for r in store.execute("SELECT lineage FROM fwd1_lineages")}
    sealed_pids = _sealed_pids(fdb)
    wrote = 0
    for lineage, rows in sorted(_registry(fdb).items()):
        if lineage in known:
            continue
        seen = sighting(lineage, rows, families, sealed_pids=sealed_pids, pin_start=pin_start)
        if seen is None:
            continue
        with store:
            cursor = store.execute(
                "INSERT OR IGNORE INTO fwd1_lineages(lineage, type, rep, family, version, run_sha, row_hash, case_, "
                "judged, why, start, cell, receipt, versions, at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (lineage, seen["type"], seen["rep"], seen["family"], seen["version"], seen["run_sha"], seen["row_hash"],
                 seen["case_"], seen["judged"], seen["why"], seen["start"], seen["cell"], rule.receipt_sha256,
                 seen["versions"], float(now)))
            if cursor.rowcount:
                wrote += 1
                event(store, "registered", at=now, lineage=lineage, pid=seen["rep"], once="first",
                      payload={"why": "first sighting under the forward screen", "case": seen["case_"],
                               "type": seen["type"], "judged": bool(seen["judged"]), "versions": seen["versions"]})
    return wrote


def frozen(store: sqlite3.Connection, fdb: sqlite3.Connection, lineage: str, pids: Sequence[int], first_day: str,
           now: float) -> str | None:
    """Why a sighted lineage's representative can no longer be re-picked (THE REPRESENTATIVE BEFORE ANY FORWARD DAY,
    the module docstring, 1), or None while it can. `pids`: every registry pid of the lineage; `first_day`: its
    representative's (the lineage's earliest).
    - "judged": the judge holds a row for it: a checkpoint, a pending reading, a verdict, sides or a floor of one of its
      pids, or an event of it but `registered`, `repicked` and `kept` (a wait, a stall, a House failure, a void...).
    - "forward_day": the forward record holds a per-pid row for one of its pids (`RECORD_DAY_TABLES`, any engine id,
      any status: a day, a checkpoint, a live-like re-price, a twin, a closed live lot, a participation row).
    - "counted": a night of the record ran through its first_day (`MAX(fwd_runs.through)`): the day is being counted.
    - "begun": its first_day's session has opened (or the calendar does not know it).
    - "unreadable": a store or the calendar could not be read. FAIL CLOSED: nothing is re-picked."""
    pids = [int(p) for p in pids]
    marks = ", ".join("?" * len(pids)) or "NULL"
    try:
        for sql, args in (
                ("SELECT 1 FROM fwd1_checks WHERE lineage=? LIMIT 1", (lineage,)),
                ("SELECT 1 FROM fwd1_pending WHERE lineage=? LIMIT 1", (lineage,)),
                ("SELECT 1 FROM fwd1_verdicts WHERE lineage=? LIMIT 1", (lineage,)),
                (f"SELECT 1 FROM fwd1_sides WHERE pid IN ({marks}) LIMIT 1", tuple(pids)),
                (f"SELECT 1 FROM fwd1_floors WHERE pid IN ({marks}) LIMIT 1", tuple(pids)),
                (f"SELECT 1 FROM fwd1_events WHERE lineage=? AND kind NOT IN "
                 f"({', '.join('?' * len(UNJUDGED_EVENTS))}) LIMIT 1", (lineage, *UNJUDGED_EVENTS))):
            if store.execute(sql, args).fetchone() is not None:
                return "judged"
    except sqlite3.Error:
        return "unreadable"
    try:
        for table in RECORD_DAY_TABLES:
            if fdb.execute(f"SELECT 1 FROM {table} WHERE pid IN ({marks}) LIMIT 1", tuple(pids)).fetchone() is not None:
                return "forward_day"
        row = fdb.execute("SELECT MAX(through) FROM fwd_runs").fetchone()
    except sqlite3.Error:
        return "unreadable"
    if row is not None and row[0] is not None and str(row[0]) >= str(first_day):
        return "counted"
    try:
        from ..equity import schedule

        moments = schedule.moments(dt.date.fromisoformat(str(first_day)))
    except Exception:  # noqa: BLE001 - a calendar that cannot answer: fail closed
        return "unreadable"
    if moments is None or float(now) >= float(moments.open_at):
        return "begun"
    return None


#: Why a better pid of a sighted lineage was not taken (`repick`, the `kept` event's "because"): `frozen`'s reasons
#: and the re-pick's own.
KEPT_BECAUSE = {
    "judged": "the judge holds a row of the lineage",
    "forward_day": "the forward record holds a row of a pid of the lineage",
    "counted": "a night of the record ran through its first_day",
    "begun": "its first_day's session had opened",
    "first_day": "the better pid is not of the representative's first_day",
    "start": "the better pid gives another FWD1_START",
    "keeps": "the better pid would change the row's type, case, judged flag or reason",
    "refused": "the store refused the update (a judge row came)"}


def _kept(store: sqlite3.Connection, row: Mapping[str, Any], best: Mapping[str, Any], because: str, *,
          now: float, changes: Sequence[str] = ()) -> int:
    """The `kept` event of a lineage whose better pid `repick` did not take, once "<rep>><better pid>" (ids and
    words only). 1 when written now, 0 when it was already written or the store refused it (the next run asks
    again)."""
    try:
        with store:
            wrote = event(store, "kept", at=now, lineage=str(row["lineage"]), pid=int(best["pid"]),
                          once=f"{int(row['rep'])}>{int(best['pid'])}",
                          payload={"why": KEPT_WHY, "because": KEPT_BECAUSE[because], "rep": int(row["rep"]),
                                   "rep_version": row["version"], "better": int(best["pid"]),
                                   "better_family": best["family"], "better_version": best["version"],
                                   "changes": list(changes)})
    except sqlite3.Error:
        return 0
    return int(wrote)


def repick(store: sqlite3.Connection, fdb: sqlite3.Connection, families: Mapping[str, Mapping[str, Any]], *,
           rule: Any, pin_start: dt.date, now: float) -> dict[str, int]:
    """THE REPRESENTATIVE BEFORE ANY FORWARD DAY (the module docstring, 1): every lineage sighted under this receipt
    whose representative the rule now gives as another pid, with the same first_day and FWD1_START, while `frozen` says
    none and the new sighting keeps the row's type, case, judged flag and reason (`REPICK_KEEPS`): its row rewritten
    in place to the new representative (rep, family, version, run_sha, row_hash, cell, versions) with one `repicked`
    event (once "<old pid>><new pid>": the old row's ids and words, the new pid's), in one transaction.
    {"repicked": rows rewritten, "repick_frozen": lineages that keep a representative the rule no longer gives,
    "repick_kept": those of them whose `kept` event was first written in this run (the job warns), "repick_unread":
    lineages left as they were because a store could not be read}."""
    out = {"repicked": 0, "repick_frozen": 0, "repick_kept": 0, "repick_unread": 0}
    held = [dict(r) for r in store.execute("SELECT * FROM fwd1_lineages WHERE receipt=? ORDER BY lineage",
                                           (rule.receipt_sha256,))]
    if not held:
        return out
    try:
        registry = _registry(fdb)
        sealed_pids = _sealed_pids(fdb)
    except sqlite3.Error:
        out["repick_unread"] = len(held)
        return out
    for row in held:
        lineage = str(row["lineage"])
        rows = registry.get(lineage) or []
        best = representative(rows)
        if best is None or int(best["pid"]) == int(row["rep"]):
            continue                                  # the representative is already the rule's: untouched
        old = next((r for r in rows if int(r["pid"]) == int(row["rep"])), None)
        changes: list[str] = []
        if old is None or str(old["first_day"]) != str(best["first_day"]):
            why = "first_day"                         # not a better row of the same first_day: kept (fail closed)
        else:
            why = frozen(store, fdb, lineage, [int(r["pid"]) for r in rows], str(old["first_day"]), now)
        if why == "unreadable":
            out["repick_unread"] += 1
            continue
        seen = None
        if why is None:
            seen = sighting(lineage, rows, families, sealed_pids=sealed_pids, pin_start=pin_start)
            if seen is None or seen["rep"] != int(best["pid"]) or seen["start"] != str(row["start"]):
                why = "start"
            else:
                changes = [key for key in REPICK_KEEPS if seen[key] != row[key]]
                if changes:
                    why = "keeps"                     # which version, never what it is judged as: the judge decides
        if why is None and seen is not None:
            was = {key: row[key] for key in ("type", "family", "version", "run_sha", "row_hash", "case_", "judged",
                                             "why", "cell", "versions")}
            try:
                with store:
                    event(store, "repicked", at=now, lineage=lineage, pid=seen["rep"],
                          once=f"{int(row['rep'])}>{seen['rep']}",
                          payload={"why": REPICK_WHY, "from": int(row["rep"]), "to": seen["rep"],
                                   "from_version": row["version"], "to_version": seen["version"],
                                   "first_day": seen["first_day"], "was": was})
                    cursor = store.execute(
                        "UPDATE fwd1_lineages SET rep=?, family=?, version=?, run_sha=?, row_hash=?, cell=?, "
                        "versions=? WHERE lineage=? AND rep=?",
                        (seen["rep"], seen["family"], seen["version"], seen["run_sha"], seen["row_hash"], seen["cell"],
                         seen["versions"], lineage, int(row["rep"])))
            except sqlite3.Error:                     # the trigger refused it (a judge row came): nothing is written
                why = "refused"
            else:
                out["repicked"] += int(cursor.rowcount)
                continue
        out["repick_frozen"] += 1
        out["repick_kept"] += _kept(store, row, best, why, now=now, changes=changes)
    return out


# ------------------------------------------------------------------------------------------------------- the runs
class OwnFloorRefused(Exception):
    """The PROGRAM's own reason it has no own floor (a Train-era run its own errors ended: a partial series; a decide
    that ran past its limit the same way in every run, E4's `TooSlow`; a Train-era series that cannot be read from its
    own runs, which is as deterministic as the runs: asked again it fails again): the lineage is ineligible for good,
    stated. Every other failure of the runs is the House's (asked again)."""


class Late(RuntimeError):
    """THE DEADLINE (`MIN_RUN_S` or less before it): no run is started. The House's: asked again the next night."""


def _capital(result: Mapping[str, Any], default: Any) -> float:
    """A run's capital as league/swarm/elane.py `_capital` reads it (a number or its text), else `default`."""
    try:
        value = float(str(result.get("capital")))
    except (TypeError, ValueError):
        value = float(default)
    return value if math.isfinite(value) and value > 0 else float(default)


class HouseRuns:
    """The Train-era runs of a representative's own floor, a representative's forward run (its sides) and a panel
    representative's placebo leg, in the job's own decider child (`forward_shadow._decider`), started on first use and
    closed by `close`. Each method raises the child's or the data's failure (never a program's mark: the checkpoint is
    left unwritten), or `OwnFloorRefused` for the program's own.

    ONE OPEN OF THE PANEL STORE A JOB RUN (league/ops/forward_xs.py's own rule; the review's major): every panel run of
    the job (a forward run's sides, a Train segment of the own floor, the placebo leg) reads THE ONE store of one
    panel night (`panel_night`, built on first use with the forward record `fdb`), never a store opened for it: each
    open maps the two bar arrays again (about 120-160 MB of address space at the real panel's size, freed only by a
    full collection) and the ops child's address space is capped 500 MB above its start. `close` lets it go.

    THE CLOCK RULE (E4's `elane_xs.steady`) holds every panel run: a run whose runtime shows a decide timeout is made
    again and never read; `ClockUnsteady` is the House's (asked again), `TooSlow` the program's.

    THE DEADLINE (`deadline`, epoch seconds; the job sets it): each run's budget is the lower of `budget_seconds` and
    the seconds left before it, and none is started with `MIN_RUN_S` or less left (`Late`)."""

    def __init__(self, root: str | Path, *, budget_seconds: float, decider: Any = None,
                 clock: Callable[[], float] = time.time, fdb: sqlite3.Connection | None = None,
                 settings: Mapping[str, Any] | None = None, deadline: float = float("inf")):
        self.root = Path(root)
        self.budget_seconds = float(budget_seconds)
        self.decider = decider
        self.clock = clock
        self.fdb = fdb
        self.settings = settings
        self.deadline = float(deadline)
        self._own = decider is None
        self._night: Any = None
        self.opens = 0                       # how many panel stores this object opened (a test reads it: one)

    def _child(self) -> Any:
        if self.decider is None:
            from . import forward_shadow

            self.decider = forward_shadow._decider(self.root)
        return self.decider

    def close(self) -> None:
        import gc

        self._night = None
        gc.collect()                         # the panel store's two maps go with it (its store and universe name each other)
        if self._own and self.decider is not None:
            try:
                self.decider.close()
            except Exception:  # noqa: BLE001 - closing a dead child
                pass
            self.decider = None

    def budget(self) -> float:
        """One run's seconds: the lower of `budget_seconds` and what is left before the deadline; `Late` with
        `MIN_RUN_S` or less left."""
        left = self.deadline - self.clock()
        if left <= MIN_RUN_S:
            raise Late("the night's deadline is too near to start a run: asked again the next night")
        return max(1.0, min(self.budget_seconds, left))

    def panel_night(self, fdb: sqlite3.Connection | None = None, settings: Mapping[str, Any] | None = None) -> Any:
        """THE ONE PANEL NIGHT of this job run (`forward_xs.panel_shadow` on the forward record READ-ONLY: it writes
        nothing before `night`), built on first use; its `panel` is the job run's one panel store."""
        if self._night is None:
            from . import forward_xs

            db = fdb if fdb is not None else self.fdb
            if db is None:
                db = forward_db.open_db(self.root, readonly=True)
                db.row_factory = sqlite3.Row
                self.fdb = db
            self._night = forward_xs.panel_shadow(self.root, db, decider=self._child(),
                                                  settings=settings if settings is not None else self.settings,
                                                  clock=self.clock)
            self.opens += 1
        self._night.decider = self._child()
        return self._night

    def _panel_iso(self) -> Any:
        """The panel's runner over THE ONE STORE (`panel_night`), at this run's budget."""
        from ..xs import runner as XR

        panel = self.panel_night().panel

        class OneStore(XR.Isolated):
            def _store(self, gate: Any = None) -> Any:
                return panel

        return OneStore(self._child(), self.root / "equity-daily", budget_seconds=self.budget(), nice=None)

    def etf_pools(self, program: Any) -> tuple[Any, Any]:
        """(the 2016-19 pool, the 2022-24 pool), each (r, r15, w, b) float64 arrays from `screen.POOL_SKIP` (S2's
        convention), or None for a span the program has no history in: its runs at k 1.0 and 1.5 over each of
        `config.TRAIN_ERA_SEGMENTS` (E1's runner in this job's child), each read by `screen.series`. A series the runs
        do not give (a ValueError of `screen.series`, two runs that differ in their sessions) is the program's own."""
        import numpy as np

        from ..equity import config as econfig
        from ..equity import screen as S
        from ..equity.runner import Isolated
        from ..equity.store import EquityStore

        iso = Isolated(self._child(), self.root / "equity-daily", budget_seconds=self.budget())
        needs = iso._needs(program.code, program.params, program.key)
        store = EquityStore(self.root / "equity-daily")
        pools: list[Any] = []
        for first, last in econfig.TRAIN_ERA_SEGMENTS:
            bars = store.span(needs.symbols, first, last, history=needs.history)
            runs = []
            for k in (econfig.K_BASE, econfig.K_STRESS):
                iso.budget_seconds = self.budget()
                runs.append(iso._run(program.code, program.params, program.key, bars, k))
            statuses = [str(run.result.get("status")) for run in runs]
            if any(s == "no_data" for s in statuses):
                pools.append(None)
                continue
            if any(s != "ok" for s in statuses):
                raise OwnFloorRefused(f"a Train-era run ended {statuses}: its series is partial")
            series = []
            try:
                for run in runs:
                    result = run.result
                    universe = [str(s) for s in (result.get("symbols") or needs.symbols)]
                    series.append(S.series(result.get("lots") or [], run.bars, universe=universe,
                                           capital=_capital(result, econfig.SLEEVE_USD)))
            except ValueError as exc:
                raise OwnFloorRefused(f"its Train-era series cannot be read from its own runs ({str(exc)[:120]})") \
                    from None
            base, stress = series
            if len(base.r) != len(stress.r):
                raise OwnFloorRefused("its two Train-era runs differ in their sessions")
            skip = S.POOL_SKIP
            pools.append(tuple(np.asarray(a, dtype=np.float64)[skip:] for a in (base.r, stress.r, base.w, base.b)))
        return pools[0], pools[1]

    def panel_pools(self, program: Any) -> tuple[Any, Any]:
        """(the first Train segment's pool, the second's), each (x, x15, w) float64 arrays from XS1's `POOL_SKIP`: the
        program's one run over each of `league.xs.config.TRAIN_SEGMENTS` (XS1's floor runs, `Isolated.segments`'
        slices and run keys), one segment at a time on THE ONE STORE, each through THE CLOCK RULE, its slice let go
        before the next is cut."""
        import numpy as np

        from ..swarm import elane_xs
        from ..xs import config as XC
        from ..xs import runner as XR
        from ..xs import screen as XS
        from . import forward_xs

        iso = self._panel_iso()
        needs, run_sha = iso._program(program.code, program.params, program.key)
        store = iso._store()
        sessions = store.sessions("train")
        pools: list[Any] = []
        for start, end in XC.TRAIN_SEGMENTS:
            first = iso._first([d for d in sessions if start <= d <= end], f"the Train segment {start}..{end}")

            def one(start: Any = start, end: Any = end, first: Any = first) -> Any:
                iso.budget_seconds = self.budget()
                piece = store.train(start, end, history=needs.history, run_key=XR.gym_key(run_sha, "train", first))
                return iso._run(program.code, program.params, program.key, piece, 1.0)

            try:
                run = elane_xs.steady(one, what="Train segment run")
            except elane_xs.TooSlow as exc:
                raise OwnFloorRefused(f"a Train-era panel run's decides ran past the limit in every run: "
                                      f"{str(exc)[:120]}") from None
            status = str(run.result.get("status"))
            if status == "no_data":
                pools.append(None)
                continue
            if status != "ok":
                raise OwnFloorRefused(f"a Train-era panel run ended {status!r}: its series is partial")
            try:
                found = forward_xs.series(run.result)
            except ValueError as exc:
                raise OwnFloorRefused(f"its Train-era panel series cannot be read from its own run "
                                      f"({str(exc)[:120]})") from None
            del run
            skip = XS.POOL_SKIP
            pools.append(tuple(np.asarray(a, dtype=np.float64)[skip:] for a in (found.x, found.x15, found.w)))
        while len(pools) < 2:
            pools.append(None)
        return pools[0], pools[1]

    def forward_sides(self, program: Any, typ: str, *, settings: Mapping[str, Any] | None,
                      fdb: sqlite3.Connection | None = None) -> dict[str, Any]:
        """THE SIDES of the representative's forward days: its own forward run in this job's child, as the record's
        night runs it (ETF: E3's `Shadow.slice` and its k 1.0 run; PANEL: package J's `run_program` on THE ONE
        STORE), opened on the forward record READ-ONLY. {"r": {ISO day: the run's r}, "sides": {ISO day: the weights in
        and out}, "entries": {ISO day: lots entering}, "exits": {ISO day: lots exiting, as the record counts them},
        "bars": {ISO day: THE BARS HASH of the decision behind the day's orders, as the record's night computes it}}:
        the judge keeps a day's sides only where this run is the record's day (`Night.read_sides`)."""
        from ..equity import config as econfig
        from . import forward_shadow

        own = fdb is None and self.fdb is None
        if own:
            fdb = forward_db.open_db(self.root, readonly=True)
            fdb.row_factory = sqlite3.Row
        fdb = fdb if fdb is not None else self.fdb
        try:
            if typ == "PANEL":
                night = self.panel_night(fdb, settings)
                night.cfg = {**night.cfg, "run_budget_seconds": self.budget()}
                run, _ = night.run_program(program)
                days, r = list(run.series.iso), list(run.series.r)
                exits = [int(v) for v in run.series.exits]
                result = run.result
                hashes = {day: night.bars_hash(day) for day in days}
            else:
                from ..equity import ctx as eq_ctx
                from ..equity.program import parse_needs

                night = forward_shadow.Shadow(self.root, fdb, decider=self._child(), settings=settings, clock=self.clock)
                night.cfg = {**night.cfg, "run_budget_seconds": self.budget()}
                whole = night._whole(program)
                bars = night.slice(whole)
                if bars is None:
                    raise ValueError(f"{program.key} has no forward day in the House's store")
                result = night._child(night.decider, code=whole.code, params=whole.params, name=whole.key, bars=bars,
                                      k=econfig.K_BASE)
                series = night._series(whole, result, bars)
                epoch = dt.date(1970, 1, 1)
                days = [(epoch + dt.timedelta(days=int(d))).isoformat() for d in series.days]
                r = [float(v) for v in series.r]
                exits = [int(v) for v in series.exits]
                needs = parse_needs(whole.needs)
                hashes = {day: forward_db.bars_hash(eq_ctx.inputs_from_bars(
                    bars, int(bars.first) + i - 1, needs=needs, cash=0.0, equity=0.0, budget=0.0, caps={}, params={}))
                    for i, day in enumerate(days)}
        finally:
            if own:
                fdb.close()
        entered = Counter(str(lot.get("entry_day"))[:10] for lot in result.get("lots") or [])
        return {"r": dict(zip(days, (float(v) for v in r))), "sides": lot_sides(result),
                "entries": {day: int(entered.get(day, 0)) for day in days}, "exits": dict(zip(days, exits)),
                "bars": hashes}

    def panel_placebo(self, program: Any, *, start: dt.date, end: dt.date, seed: int) -> dict[str, Any]:
        """THE PLACEBO LEG's draws: one panel run of the representative over the forward sessions [start, end] (its
        judged sessions, flat at start: the forward days need the gate's capability, which THE ONE STORE was opened
        with), with `fwd1_rule.PLACEBO_DRAWS` matched placebos under `seed` (XS1's law, league/xs/placebo.py), through
        THE CLOCK RULE. {"t": [the draws' t on the run's sessions], "days": how many sessions they were read on, "n":
        the draws}. `elane_xs.TooSlow` (the program's) and `ClockUnsteady` (the House's) pass through."""
        from ..swarm import elane_xs
        from ..xs import runner as XR

        iso = self._panel_iso()
        store = iso._store()
        needs, run_sha = iso._program(program.code, program.params, program.key)
        first = iso._first([d for d in store.sessions("forward") if start <= d <= end],
                           f"the forward days {start}..{end}")

        def one() -> Any:
            iso.budget_seconds = self.budget()
            piece = store.bars("forward", history=needs.history, run_key=XR.gym_key(run_sha, "forward", first),
                               start=first, end=end)
            return iso._run(program.code, program.params, program.key, piece, 1.0, placebos=R.PLACEBO_DRAWS,
                            seed=int(seed))

        run = elane_xs.steady(one, what="placebo leg run")
        block = run.result.get("placebo") if isinstance(run.result.get("placebo"), Mapping) else {}
        span = (block.get("spans") or {}).get("run") or {}
        return {"t": list(span.get("t") or []), "days": int(span.get("days") or 0), "n": int(block.get("n") or 0),
                "seed": block.get("seed")}


# ---------------------------------------------------------------------------------------------------- the judge
def _lotgaps(fdb: sqlite3.Connection) -> dict[str, list[float]]:
    """{type: the measured gaps a side of its closed live lots} (`fwd_lotgap.side_gap_bp`, a lot whose registry row
    is a panel row is PANEL's, one of any other row ETF's; a lot with no registry row is not a measurement here)."""
    out: dict[str, list[float]] = {"ETF": [], "PANEL": []}
    for row in fdb.execute("SELECT g.side_gap_bp AS gap, r.ugroup AS ugroup FROM fwd_lotgap g JOIN fwd_registry r ON "
                           "r.pid = g.pid WHERE g.side_gap_bp IS NOT NULL"):
        typ = "PANEL" if str(row["ugroup"]).startswith(forward_db.PANEL_UGROUP) else "ETF"
        out[typ].append(float(row["gap"]))
    return out


def _counted(fdb: sqlite3.Connection, pid: int, engine: int, start: str) -> list[dict[str, Any]]:
    return [row for row in forward_db.counted_days(fdb, pid, engine=engine) if str(row["day"]) >= start]


def _restated_spans(fdb: sqlite3.Connection, pid: int, engine: int) -> list[tuple[str, str]]:
    """The [first, last] day spans of the record's `restated` events of `pid` under `engine` whose cause is the
    store's history (`bars` "moved": every restated day's decision read inputs the vendor restated; league/ops/
    forward_shadow.py, A RESTATED RECORD)."""
    out: list[tuple[str, str]] = []
    for row in fdb.execute("SELECT payload FROM fwd_events WHERE kind='restated' AND pid=?", (int(pid),)):
        try:
            payload = json.loads(row["payload"])
        except (TypeError, ValueError):
            continue
        if not isinstance(payload, Mapping) or payload.get("bars") != "moved":
            continue
        try:
            same_engine = int(payload.get("engine")) == int(engine)
        except (TypeError, ValueError):
            same_engine = False
        if same_engine and payload.get("first") and payload.get("last"):
            out.append((str(payload["first"]), str(payload["last"])))
    return out


def _moved(a: Mapping[str, Any], b: Mapping[str, Any]) -> bool:
    """Whether a day's r, w, b or r15 differs between two rows by more than `ENGINE_TOUCH` (a missing r15 on one side
    only is a difference)."""
    for column in ("r", "w", "b", "r15"):
        x, y = a.get(column), b.get(column)
        if x is None and y is None:
            continue
        if x is None or y is None or abs(float(x) - float(y)) > ENGINE_TOUCH:
            return True
    return False


def engine_reading(fdb: sqlite3.Connection, pid: int, old: int, new: int, days: Sequence[str]) -> tuple[str, int]:
    """AN ENGINE CHANGE AND A PENDING LINEAGE (the module docstring, 3): `days` are the judged days its checkpoints of
    record read under `old`; `new` the record's newest engine id.
    - ("wait", 0): a judged day has no row under `new` YET. E3's night opens the new id and writes the ETF rows; the
      panel night writes the panel rows hours later; a program the night's budget left stale is written a night later.
      No checkpoint and no void: asked again (THE STALL RULE bounds the wait).
    - ("touched", 0): a judged day under `new` is not counted (another status, an audit mark), or its r, w, b or r15
      moved past `ENGINE_TOUCH` and no restatement of the store explains it: the engine moved a judged day (one engine
      id a verdict: the lineage is void).
    - ("carried", n): every judged day is as it was, but for n days that moved only because the vendor restated the
      store's history since the old row was written: both rows' bars hashes are known and differ, and the record's
      own `restated` event of the pid under `old`, bars "moved", covers the day (a dividend or a split rescales the
      whole adjusted history; the new id's rows are a whole recompute on today's store). A judged day moved with the
      same bars hash, or with no such event (the engine and the restatement on one night), is a touch."""
    news = {str(r["day"]): dict(r) for r in fdb.execute("SELECT * FROM fwd_days WHERE pid=? AND engine=?",
                                                         (int(pid), int(new)))}
    if any(day not in news for day in days):
        return "wait", 0
    olds = {str(r["day"]): r for r in forward_db.counted_days(fdb, pid, engine=old)}
    counted_new = {str(r["day"]) for r in forward_db.counted_days(fdb, pid, engine=new)}
    spans: list[tuple[str, str]] | None = None
    restated = 0
    for day in days:
        a, b = olds.get(day), news[day]
        if a is None or day not in counted_new:
            return "touched", 0
        if not _moved(a, b):
            continue
        if spans is None:
            spans = _restated_spans(fdb, pid, old)
        hashes_differ = a.get("bars") is not None and b.get("bars") is not None and str(a["bars"]) != str(b["bars"])
        if not hashes_differ or not any(first <= day <= last for first, last in spans):
            return "touched", 0
        restated += 1
    return "carried", restated


def preopen_deadline(now: float) -> float:
    """THE DEADLINE's second term: the next pre-open (an hour before the open of the session whose close is after
    `now`) less `MARGIN_S`; in the past while that pre-open has begun and its session is not over. +inf when the
    calendar does not reach one."""
    from ..equity import schedule

    day = schedule.ny_day(float(now))
    for _ in range(schedule.HORIZON_DAYS + 1):
        moments = schedule.moments(day)
        if moments is not None and moments.close_at > float(now):
            return float(moments.open_at) - PREOPEN_BEFORE_S - MARGIN_S
        day += dt.timedelta(days=1)
    return float("inf")


def night_spent(store: sqlite3.Connection, now: float) -> float:
    """ONE BUDGET A NIGHT: the child seconds of the job's runs (`fwd1_runs`) that ended in the last `NIGHT_WINDOW_S`."""
    row = store.execute("SELECT COALESCE(SUM(seconds), 0) FROM fwd1_runs WHERE finished >= ?",
                        (float(now) - NIGHT_WINDOW_S,)).fetchone()
    return float(row[0] or 0.0)


class Night:
    """One night of the judge (the module docstring): `store` (the screen's own, writable), `fdb` (the forward record,
    read-only), `families` (the equity families of the swarm store, read-only), `runs` (`HouseRuns` or a test's fake),
    `rule` (`fwd1_rule.Rule`), `pin` (the clock's row), `budget` (child seconds left tonight), `deadline` (epoch
    seconds: no run starts with `MIN_RUN_S` or less before it)."""

    def __init__(self, store: sqlite3.Connection, fdb: sqlite3.Connection, families: Mapping[str, Mapping[str, Any]], *,
                 runs: Any, rule: Any, pin: Mapping[str, Any], budget: float, clock: Callable[[], float] = time.time,
                 settings: Mapping[str, Any] | None = None, deadline: float = float("inf")):
        self.store, self.fdb, self.families, self.runs, self.rule = store, fdb, families, runs, rule
        self.settings = settings
        self.pin = dict(pin)
        self.pin_start = dt.date.fromisoformat(str(pin["start"]))
        self.budget = float(budget)
        self.deadline = float(deadline)
        self.clock = clock
        self.spent = 0.0
        self.tally: Counter = Counter()
        self.gaps = _lotgaps(fdb)
        self.engine_now = forward_db.engine_now(fdb)
        self.sealed_pids = _sealed_pids(fdb)
        row = fdb.execute("SELECT MAX(through) FROM fwd_runs").fetchone()
        #: THE STALL RULE's night: the record's newest night (`fwd_runs.through`, one row a night of either job).
        self.record_day = None if row is None or row[0] is None else str(row[0])

    # ------------------------------------------------------------------------------------------------ helpers
    def _timed(self, call: Callable[[], Any]) -> Any:
        began = self.clock()
        try:
            return call()
        finally:
            self.spent += max(0.0, self.clock() - began)

    def _over(self) -> bool:
        """The night's child seconds are spent, or THE DEADLINE leaves no room for a run."""
        return self.spent >= self.budget or self.clock() >= self.deadline - MIN_RUN_S

    def _deferred(self) -> None:
        self.tally["deferred"] += 1

    def _program(self, pid: int) -> Any:
        row = self.fdb.execute("SELECT key FROM fwd_registry WHERE pid=?", (int(pid),)).fetchone()
        return None if row is None else forward_db.program(self.fdb, str(row["key"]))

    def _verdict(self, lineage: str) -> Mapping[str, Any] | None:
        row = self.store.execute("SELECT * FROM fwd1_verdicts WHERE lineage=?", (lineage,)).fetchone()
        return None if row is None else dict(row)

    def _checks(self, lineage: str) -> dict[int, dict[str, Any]]:
        return {int(r["k"]): dict(r) for r in self.store.execute("SELECT * FROM fwd1_checks WHERE lineage=?", (lineage,))}

    def _floor(self, pid: int) -> Mapping[str, Any] | None:
        row = self.store.execute("SELECT * FROM fwd1_floors WHERE pid=?", (int(pid),)).fetchone()
        return None if row is None else dict(row)

    def _pending(self, lineage: str, k: int, engine: int) -> Mapping[str, Any] | None:
        row = self.store.execute("SELECT * FROM fwd1_pending WHERE lineage=? AND k=? AND engine=?",
                                 (lineage, int(k), int(engine))).fetchone()
        return None if row is None else dict(row)

    def _sides(self, pid: int, engine: int, days: Sequence[str]) -> list[float] | None:
        held = {str(r["day"]): float(r["sides"]) for r in self.store.execute(
            "SELECT day, sides FROM fwd1_sides WHERE pid=? AND engine=?", (int(pid), int(engine)))}
        out = [held.get(day) for day in days]
        return None if any(v is None for v in out) else [float(v) for v in out]   # type: ignore[arg-type]

    def stalled(self, lineage: str) -> bool:
        """THE STALL RULE: whether the lineage stalled under the record's newest engine id."""
        return self.engine_now is not None and self.store.execute(
            "SELECT 1 FROM fwd1_events WHERE kind='stalled' AND lineage=? AND once=?",
            (lineage, str(self.engine_now))).fetchone() is not None

    def missed(self, lin: Mapping[str, Any], cause: str, engine: Any, why: str) -> bool:
        """One of the record's nights a lineage's next step waited on the House (`waited`, once a lineage, cause,
        engine id and record day: the job's second run of a night counts none); at `STALL_NIGHTS` such nights the
        lineage is STALLED under the newest engine id (`stalled`, once). Whether it is stalled now. Nothing marks it."""
        lineage, pid = str(lin["lineage"]), int(lin["rep"])
        key = f"{cause}:{engine}"
        with self.store:
            event(self.store, "waited", at=self.clock(), lineage=lineage, pid=pid, once=f"{key}:{self.record_day}",
                  payload={"why": why, "cause": cause, "engine": engine, "day": self.record_day})
        nights = int(self.store.execute(
            "SELECT COUNT(*) FROM fwd1_events WHERE kind='waited' AND lineage=? AND substr(once, 1, ?) = ?",
            (lineage, len(key) + 1, key + ":")).fetchone()[0])
        if nights < STALL_NIGHTS or self.engine_now is None:
            return False
        with self.store:
            if event(self.store, "stalled", at=self.clock(), lineage=lineage, pid=pid, once=str(self.engine_now),
                     payload={"why": f"{why}: on {nights} of the record's nights, so it costs no run until the "
                                     "record opens a new engine id; nothing marks it", "cause": cause,
                              "nights": nights, "engine": self.engine_now}):
                self.tally["stalled"] += 1
        return True

    def read_sides(self, lin: Mapping[str, Any], program: Any, engine: int,
                   rows: Sequence[Mapping[str, Any]]) -> int | None:
        """THE SIDES of the representative's counted days not yet kept (the module docstring, 2): its own forward run
        (`runs.forward_sides`), each day kept (first write stands, under the record's engine id) where the run IS the
        record's day: its r is the record's to `forward_db.TOL`, or THE DAY WAS RESTATED (the run made the same orders
        that session, its lots in and out counted as the record counts them, from inputs the vendor's restatement of
        the store's history moved: the run's bars hash of the day's decision is not the stored one; E3 keeps the first
        write of every day, and a dividend or a split rescales the whole adjusted history, so the stored r of every
        day before an ex-day is never reproduced again). How many days it kept (0 and a `house` event when the run
        failed or matched none); None when THE DEADLINE left no room to start it (nothing written)."""
        lineage, pid = str(lin["lineage"]), int(lin["rep"])
        try:
            found = self._timed(lambda: self.runs.forward_sides(program, str(lin["type"]), settings=self.settings,
                                                                fdb=self.fdb))
        except Late:
            self._deferred()
            return None
        except Exception as exc:  # noqa: BLE001 - the child's or the data's: nobody is marked
            self.tally["house"] += 1
            with self.store:
                event(self.store, "house", at=self.clock(), lineage=lineage, pid=pid,
                      payload={"why": "the forward run that reads the sides did not finish", "error": type(exc).__name__})
            return 0
        ran, sides = found.get("r") or {}, found.get("sides") or {}
        entries, exits, hashes = found.get("entries") or {}, found.get("exits") or {}, found.get("bars") or {}
        kept = 0
        with self.store:
            for row in rows:
                day = str(row["day"])
                if day not in ran:
                    continue
                if abs(float(ran[day]) - float(row["r"])) > forward_db.TOL:
                    restated = (row.get("bars") is not None and day in hashes and str(hashes[day]) != str(row["bars"])
                                and day in entries and day in exits and int(entries[day]) == int(row["entries"])
                                and int(exits[day]) == int(row["exits"]))
                    if not restated:
                        continue
                cursor = self.store.execute(
                    "INSERT OR IGNORE INTO fwd1_sides(pid, day, engine, sides, at) VALUES (?,?,?,?,?)",
                    (pid, day, int(engine), float(sides.get(day, 0.0)), self.clock()))
                kept += cursor.rowcount
                if cursor.rowcount and abs(float(ran[day]) - float(row["r"])) > forward_db.TOL:
                    self.tally["sides_restated"] += 1          # a restated day's sides kept tonight
        if not kept:
            self.tally["house"] += 1
            with self.store:
                event(self.store, "house", at=self.clock(), lineage=lineage, pid=pid,
                      payload={"why": "the forward run reproduced none of the record's days: no sides are read from it",
                               "days": len(rows)})
        self.tally["sides_runs"] += 1
        return kept

    def _live_like(self, pid: int, engine: int) -> dict[str, float]:
        return {str(r["day"]): float(r["r_ll"]) for r in self.fdb.execute(
            "SELECT day, r_ll FROM fwd_ll WHERE pid=? AND engine=?", (int(pid), int(engine)))}

    def _void(self, lin: Mapping[str, Any], why: str, *, at: float) -> None:
        with self.store:
            self.store.execute("INSERT OR IGNORE INTO fwd1_verdicts(lineage, pid, verdict, k, day, c_used, why, beside, "
                               "words, at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                               (lin["lineage"], int(lin["rep"]), "void", None, None, None, why, None, None, float(at)))
            event(self.store, "void", at=at, lineage=str(lin["lineage"]), pid=int(lin["rep"]), once="void",
                  payload={"why": why})
        self.tally["void"] += 1

    def span_cause(self, pid: int, engine: int, start: str, names: Sequence[str]) -> tuple[str | None, list[str]]:
        """THE PLACEBO SPAN (the review's fix): the placebo leg is one panel run over every session of [start, the
        k-th counted day], and the rule reads the draws on the SAME k sessions, so a session of the span that is not a
        counted day decides the leg. (None, []) when there is none; ("own", days) when each is the program's own (a
        row of status "disqualified": its own run's doing), and the leg fails closed; ("house", days) when any is the
        House's (no row of the record for it, or a morning audit mark): the checkpoint waits, nothing marks it."""
        from ..equity import schedule

        counted = set(names)
        day, last = dt.date.fromisoformat(str(start)), dt.date.fromisoformat(str(names[-1]))
        extra: list[str] = []
        while day <= last:
            if schedule.is_session(day) and day.isoformat() not in counted:
                extra.append(day.isoformat())
            day += dt.timedelta(days=1)
        if not extra:
            return None, []
        house = False
        for name in extra:
            row = self.fdb.execute("SELECT status FROM fwd_days WHERE pid=? AND day=? AND engine=?",
                                   (int(pid), name, int(engine))).fetchone()
            marked = self.fdb.execute("SELECT 1 FROM fwd_events WHERE kind='audit_mismatch' AND pid=? AND day=?",
                                      (int(pid), name)).fetchone() is not None
            if row is None or marked or str(row["status"]) != "disqualified":
                house = True
        return ("house" if house else "own"), extra

    # ------------------------------------------------------------------------------------------ the own floor
    def floor(self, lin: Mapping[str, Any], program: Any) -> Mapping[str, Any] | None:
        """The representative's own floor row, computed once (None while it cannot be: the budget, the deadline, or the
        House's failure: no row, asked again the next night)."""
        held = self._floor(int(lin["rep"]))
        if held is not None:
            return held
        if self._over():
            self._deferred()
            return None
        typ, case = str(lin["type"]), str(lin["case_"])
        began = self.clock()
        try:
            pools = self._timed(lambda: (self.runs.etf_pools(program) if typ == "ETF" else self.runs.panel_pools(program)))
        except OwnFloorRefused as exc:       # the program's own: ineligible for good, stated
            pools, why = None, f"no own floor: {str(exc)[:160]}"
        except Late:
            self._deferred()
            return None
        except Exception as exc:  # noqa: BLE001 - the child's or the data's: no row, the next night asks again
            self.tally["house"] += 1
            with self.store:
                event(self.store, "house", at=self.clock(), lineage=str(lin["lineage"]), pid=int(lin["rep"]),
                      payload={"why": "the own floor's Train-era runs did not finish", "error": type(exc).__name__})
            return None
        k_own = drift = None
        cells: dict[str, int] = {}
        if pools is not None:
            pool_d, pool_c = pools
            cells_in = R.floor_cells(typ, pool_d, pool_c)
            three = [[p[:3] for p in cell] for cell in cells_in]
            found = R.own_floor_k(three, R.OWN_CAP[case])
            k_own, cells, why = found["k_own"], found["cells"], found["why"]
            ku = R.k_used(typ, case, k_own)
            if typ == "ETF" and ku is not None:
                drift = R.drift_kept(cells_in, ku)
            if k_own is not None and ku is None:
                why = f"c_used above {R.K_MAX / 100:.2f}: no grid bar holds the cap"
        with self.store:
            self.store.execute("INSERT OR IGNORE INTO fwd1_floors(pid, case_, k_own, cells, drift, why, seconds, at) "
                               "VALUES (?,?,?,?,?,?,?,?)",
                               (int(lin["rep"]), case, k_own, json.dumps(cells, sort_keys=True), drift, why,
                                round(self.clock() - began, 3), self.clock()))
            if R.k_used(typ, case, k_own) is None:
                event(self.store, "ineligible", at=self.clock(), lineage=str(lin["lineage"]), pid=int(lin["rep"]),
                      once="floor", payload={"why": why or "no own floor"})
        self.tally["floors"] += 1
        return self._floor(int(lin["rep"]))

    # --------------------------------------------------------------------------------------------- one lineage
    def judge(self, lin: Mapping[str, Any]) -> str | None:
        """One judged lineage's night; the verdict written tonight, or None."""
        lineage, pid, typ, case = str(lin["lineage"]), int(lin["rep"]), str(lin["type"]), str(lin["case_"])
        now = self.clock()
        if self._verdict(lineage) is not None:
            return None                                   # nothing judges a lineage after its verdict
        if self.stalled(lineage):
            self.tally["stalled_skipped"] += 1            # THE STALL RULE: no run until a new engine id
            return None
        if not forward_db.active(self.fdb, pid):
            self.tally["stopped"] += 1                    # no row comes while its representative is stopped
            return None
        rows = self.fdb.execute("SELECT pid, family FROM fwd_registry WHERE lineage=? AND reason != 'control'",
                                (lineage,)).fetchall()
        if case == "N":
            sealed = bool({int(r["pid"]) for r in rows} & self.sealed_pids) or any(
                family_sealed(self.families.get(str(r["family"]))) for r in rows)
            if sealed:
                self._void(lin, "a case-N lineage reached a sealed pre-check after FWD1_START: it is judged no further",
                           at=now)
                return "void"
        floor_row = self._floor(pid)
        if floor_row is not None and R.k_used(typ, case, floor_row["k_own"]) is None:
            return None                                   # ineligible: no verdict, stated (its event)
        checks = self._checks(lineage)
        engine = self.engine_now if not checks else int(checks[max(checks)]["engine"])
        if engine is None:
            return None
        start = str(lin["start"])
        if checks and self.engine_now is not None and engine != self.engine_now:
            judged_days = [str(r["day"]) for r in _counted(self.fdb, pid, engine, start)][:max(checks)]
            reading, restated = engine_reading(self.fdb, pid, engine, self.engine_now, judged_days)
            if reading == "wait":
                self.tally["engine_wait"] += 1
                self.missed(lin, "engine", self.engine_now, "its judged days have no rows under the record's new "
                                                            "engine id yet")
                return None
            touched = reading == "touched"
            with self.store:
                event(self.store, "engine_switched", at=now, lineage=lineage, pid=pid, once=f"{engine}>{self.engine_now}",
                      payload={"why": "an engine change touched a pending representative's judged days" if touched else
                               "an engine change left its judged days as they were", "from": engine,
                               "to": self.engine_now, "pids": [pid], "touched": touched, "restated": restated})
            if touched:
                self._void(lin, "an engine change touched its judged days: one engine id a verdict", at=now)
                return "void"
            engine = self.engine_now
        days = _counted(self.fdb, pid, engine, start)
        if not days:
            return None
        program = None
        for k in R.PLAN:
            if k in checks:
                held = checks[k]
                if held["passed"]:
                    # A checkpoint of record that passed is written with its verdict in one transaction; one found
                    # alone (a store written by an earlier build) gets its verdict from its own row now.
                    self._write(None, self._pass_row(lin, k=k, day=str(held["day"]), t=float(held["t"]),
                                                     c_value=float(held["c_used"]), g=float(held["g_bp"]),
                                                     pnl=float(held["s"]), floor_row=self._floor(pid) or {}))
                    return "pass"
                if k == R.PLAN[-1]:
                    self._write(None, self._fail_row(lin, k=k, day=str(held["day"]), c_value=held["c_used"]))
                    return "fail"
                continue
            if len(days) < k:
                return None                               # the checkpoint of record is read when it is reached
            head = days[:k]
            names = [str(r["day"]) for r in head]
            c_g = R.C_G[typ][case]
            kept = self._pending(lineage, k, engine)
            if kept is not None:
                # THE CHECKPOINT'S READING as it was first read (the module docstring, 2): never read again
                point = {"t": kept["t"], "S": float(kept["s"]), "S15": float(kept["s15"])}
                g, used_ll = float(kept["g_bp"]), int(kept["ll"])
            else:
                sides = self._sides(pid, engine, names)
                if sides is None:
                    if program is None:
                        program = self._program(pid)
                    if program is None:
                        return None
                    if self._over():
                        self._deferred()
                        return None
                    if self.read_sides(lin, program, engine, days[:R.KMAX]) is None:
                        return None                       # THE DEADLINE: not started, nothing written
                    sides = self._sides(pid, engine, names)
                    if sides is None:
                        self.tally["no_sides"] += 1
                        self.missed(lin, "sides", engine, "the sides of its judged days could not be read from its own "
                                                          "forward run")
                        return None                       # asked again the next night
                g = R.haircut_bp(typ, self.gaps.get(typ, []))
                ll = self._live_like(pid, engine) if typ == "ETF" else {}
                used_ll = int(any(n in ll for n in names))
                try:
                    x, x15 = R.series(typ, head, g_bp=g, sides=sides, live_like=ll)
                except ValueError:
                    self.tally["unreadable"] += 1
                    return None
                point = R.checkpoint(x, x15, k)
                if R.legs_pass(point, c_g):
                    # a would-be pass waits on its floor or its placebo leg: its reading is kept as it is now
                    with self.store:
                        self.store.execute(
                            "INSERT OR IGNORE INTO fwd1_pending(lineage, k, engine, pid, day, t, s, s15, g_bp, ll, at) "
                            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                            (lineage, k, int(engine), pid, names[-1], point["t"], float(point["S"]),
                             float(point["S15"]), float(g), used_ll, self.clock()))
            c_value = count = draws = None
            why = None
            passed = False
            if not R.legs_pass(point, c_g):
                why = "below the global bar or a sum at or below zero"
            else:
                if program is None:
                    program = self._program(pid)
                if program is None:
                    return None
                floor_row = self.floor(lin, program)
                if floor_row is None:
                    return None                           # the floor waits: the checkpoint is not written tonight
                c_value = R.c_used(typ, case, floor_row["k_own"])
                if c_value is None:
                    return None                           # ineligible (its event)
                if not R.legs_pass(point, c_value):
                    why = "below c_used (the own floor + 0.05)"
                elif typ == "PANEL":
                    cause, extra = self.span_cause(pid, engine, start, names)
                    if cause == "house":
                        self.tally["house"] += 1
                        with self.store:
                            event(self.store, "house", at=self.clock(), lineage=lineage, pid=pid,
                                  payload={"why": "the placebo span holds a session the House left out of the counted "
                                                  "days (no row, or a morning audit mark): the checkpoint waits",
                                           "days": len(extra)})
                        self.missed(lin, "span", engine, "its placebo span holds a session the House left out of its "
                                                         "counted days")
                        return None
                    if cause == "own":
                        draws = 0
                        why = (f"the placebo span holds {len(extra)} session(s) the program's own run disqualified: the "
                               f"leg cannot be read on the {k} judged sessions and fails closed")
                    else:
                        if self._over():
                            self._deferred()
                            return None
                        from ..swarm import elane_xs

                        block = None
                        try:
                            seed = R.placebo_seed(self.rule.receipt_sha256, str(lin["row_hash"]))
                            block = self._timed(lambda: self.runs.panel_placebo(
                                program, start=dt.date.fromisoformat(start), end=dt.date.fromisoformat(names[-1]),
                                seed=seed))
                        except elane_xs.TooSlow as exc:   # the program's own: its decides ran past the limit each run
                            draws = 0
                            why = f"the placebo leg's run: {str(exc)[:160]}: the leg fails closed"
                        except Late:
                            self._deferred()
                            return None
                        except Exception as exc:  # noqa: BLE001 - the child's or the data's: asked again tomorrow
                            self.tally["house"] += 1
                            with self.store:
                                event(self.store, "house", at=self.clock(), lineage=lineage, pid=pid,
                                      payload={"why": "the placebo leg's run did not finish", "error": type(exc).__name__})
                            return None
                        if block is not None:
                            draws = int(block.get("n") or 0)
                            if int(block.get("days") or 0) != k:
                                self.tally["house"] += 1
                                with self.store:
                                    event(self.store, "house", at=self.clock(), lineage=lineage, pid=pid,
                                          payload={"why": "the placebo leg was read on other sessions than the judged "
                                                          "ones: the checkpoint waits", "days": block.get("days"),
                                                   "k": k})
                                self.missed(lin, "span", engine, "its placebo run was read on other sessions than its "
                                                                 "judged ones")
                                return None
                            count = R.placebo_count(point["t"], block.get("t") or [])
                            passed = R.placebo_holds(count, draws)
                            if not passed:
                                why = f"the placebo leg: {count} of {draws} draws at or above t"
                else:
                    passed = True
            check = (lineage, k, pid, engine, names[-1], point["t"], point["S"], point["S15"], float(g), used_ll, count,
                     draws, c_value, 1 if passed else 0, why, self.clock())
            verdict = None
            if passed:
                verdict = self._pass_row(lin, k=k, day=names[-1], t=float(point["t"]), c_value=float(c_value), g=g,
                                         pnl=point["S"], floor_row=floor_row)
            elif k == R.PLAN[-1]:
                verdict = self._fail_row(lin, k=k, day=names[-1], c_value=c_value)
            self._write(check, verdict)                  # the checkpoint of record and its verdict: one transaction
            self.tally["checks"] += 1
            if verdict is not None:
                return str(verdict[2])
        return None

    def _write(self, check: Sequence[Any] | None, verdict: Sequence[Any] | None) -> None:
        """A checkpoint of record and the verdict it makes (either may be None), in ONE transaction: first write
        stands for both."""
        with self.store:
            if check is not None:
                self.store.execute(
                    "INSERT OR IGNORE INTO fwd1_checks(lineage, k, pid, engine, day, t, s, s15, g_bp, ll, count, draws, "
                    "c_used, passed, why, at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", tuple(check))
            if verdict is not None:
                cursor = self.store.execute(
                    "INSERT OR IGNORE INTO fwd1_verdicts(lineage, pid, verdict, k, day, c_used, why, beside, words, at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)", tuple(verdict))
                if cursor.rowcount:
                    self.tally[str(verdict[2])] += 1

    def _fail_row(self, lin: Mapping[str, Any], *, k: int, day: str, c_value: Any) -> tuple[Any, ...]:
        return (str(lin["lineage"]), int(lin["rep"]), "fail", k, day, c_value,
                "no checkpoint of 5-60 passed: failed for good", None, None, self.clock())

    def registry_counts(self, typ: str, case: str, *, also: tuple[str, int] | None = None
                        ) -> tuple[int, int, float | None]:
        """(the PASS verdicts, the lineages judged so far, the expected zero-edge passes) of one type and case: the
        lineages with a checkpoint of record, each at the last one read; `also` (lineage, k): one more read (the
        checkpoint being written), counted at k, and its PASS among the passes."""
        rows = self.store.execute(
            "SELECT l.lineage AS lineage, MAX(c.k) AS k FROM fwd1_lineages l JOIN fwd1_checks c ON c.lineage = l.lineage "
            "WHERE l.type=? AND l.case_=? AND l.judged=1 GROUP BY l.lineage", (typ, case)).fetchall()
        last = {str(r["lineage"]): int(r["k"]) for r in rows}
        passes = int(self.store.execute(
            "SELECT COUNT(*) FROM fwd1_verdicts v JOIN fwd1_lineages l ON l.lineage = v.lineage WHERE v.verdict='pass' "
            "AND l.type=? AND l.case_=?", (typ, case)).fetchone()[0])
        if also is not None:
            last[str(also[0])] = max(int(also[1]), last.get(str(also[0]), 0))
            passes += 0 if self._verdict(str(also[0])) is not None else 1
        read = [(typ, case, k) for k in last.values()]
        expected = R.expected_passes(self.rule, read).get(f"{typ}|{case}") if read else 0.0
        return passes, len(read), expected

    def _pass_row(self, lin: Mapping[str, Any], *, k: int, day: str, t: float, c_value: float, g: float, pnl: float,
                  floor_row: Mapping[str, Any]) -> tuple[Any, ...]:
        """The PASS verdict's row: its sentence (operator-only) and its words (the permit's), the registry's counts
        read as they stand with this pass among them."""
        typ, case = str(lin["type"]), str(lin["case_"])
        observed, judged, expected = self.registry_counts(typ, case, also=(str(lin["lineage"]), k))
        common = dict(typ=typ, case=case, k=k, start=lin["start"], c_used_value=c_value, k_own=floor_row["k_own"],
                      observed=observed, judged=judged, expected=expected)
        text = R.beside(self.rule, t=t, g_bp=g, pnl=pnl, drift=floor_row.get("drift"), **common)
        said = R.words(self.rule, **common)
        return (str(lin["lineage"]), int(lin["rep"]), "pass", k, day, c_value, f"passed at checkpoint {k}", text, said,
                self.clock())

    # ---------------------------------------------------------------------------------------------- the night
    def run(self) -> dict[str, Any]:
        """Every judged lineage without a verdict registered under THIS receipt (a lineage registered under another
        pin is judged no further by this one: a receipt judges only the days after its own pin), the lineages that
        waited on the House the fewest of the record's nights under the newest engine id first, then in lineage
        order (a lineage that keeps waiting never takes the night's budget from one that does not). A panel
        lineage's runs are collected after it (THE ONE STORE stays; what its runs cut goes)."""
        import gc

        lineages = [dict(r) for r in self.store.execute(
            "SELECT * FROM fwd1_lineages WHERE judged=1 AND receipt=? AND lineage NOT IN (SELECT lineage FROM "
            "fwd1_verdicts) ORDER BY lineage", (self.rule.receipt_sha256,))]
        waited: Counter = Counter()
        for row in self.store.execute("SELECT lineage, once FROM fwd1_events WHERE kind='waited'"):
            parts = str(row["once"] or "").split(":")
            if len(parts) >= 2 and parts[1] == str(self.engine_now):
                waited[str(row["lineage"])] += 1
        lineages.sort(key=lambda lin: (waited[str(lin["lineage"])], str(lin["lineage"])))
        for lin in lineages:
            try:
                self.judge(lin)
            except sqlite3.Error:
                self.tally["house"] += 1
            if lin.get("type") == "PANEL":
                gc.collect()
        return dict(self.tally)


# ----------------------------------------------------------------------------------------------- permits and report
def status_rows(store: sqlite3.Connection, *, fdb: sqlite3.Connection | None = None,
                rule: Any = None) -> list[dict[str, Any]]:
    """Every lineage with its status (`STATUSES`), its last checkpoint read and its verdict's words. With the forward
    record `fdb`: "stopped" (its representative is stopped there) and "stalled" (THE STALL RULE, under the record's
    newest engine id); with the `rule` in force: "superseded" (a pending lineage registered under another receipt)."""
    verdicts = {str(r["lineage"]): dict(r) for r in store.execute("SELECT * FROM fwd1_verdicts")}
    last = {str(r["lineage"]): int(r["k"]) for r in store.execute(
        "SELECT lineage, MAX(k) AS k FROM fwd1_checks GROUP BY lineage")}
    engines = {(str(r["lineage"]), int(r["k"])): int(r["engine"]) for r in store.execute(
        "SELECT lineage, k, engine FROM fwd1_checks WHERE passed=1")}
    floors = {int(r["pid"]): dict(r) for r in store.execute("SELECT * FROM fwd1_floors")}
    engine_now = None if fdb is None else forward_db.engine_now(fdb)
    stalled = {str(r["lineage"]) for r in store.execute(
        "SELECT lineage FROM fwd1_events WHERE kind='stalled' AND once=?", (str(engine_now),))} \
        if engine_now is not None else set()
    out = []
    for lin in store.execute("SELECT * FROM fwd1_lineages ORDER BY lineage"):
        lin = dict(lin)
        v = verdicts.get(str(lin["lineage"]))
        if not lin["judged"]:
            status = "not_judged"
        elif v is not None:
            status = str(v["verdict"])
        else:
            fl = floors.get(int(lin["rep"]))
            if fl is not None and R.k_used(str(lin["type"]), str(lin["case_"]), fl["k_own"]) is None:
                status = "ineligible"
            elif rule is not None and str(lin["receipt"]) != str(rule.receipt_sha256):
                status = "superseded"
            elif fdb is not None and not forward_db.active(fdb, int(lin["rep"])):
                status = "stopped"
            elif str(lin["lineage"]) in stalled:
                status = "stalled"
            else:
                status = "pending"
        k = (v or {}).get("k") or last.get(str(lin["lineage"]))
        out.append({**lin, "status": status, "k": k, "words": (v or {}).get("words"),
                    "beside": (v or {}).get("beside"),
                    "engine": engines.get((str(lin["lineage"]), int(k))) if status == "pass" and k is not None else None})
    return out


def write_permits(root: str | Path, store: sqlite3.Connection, *, rule: Any, pin: Mapping[str, Any], at: float,
                  labels: Mapping[int, str] | None = None, fdb: sqlite3.Connection | None = None) -> Path:
    """THE PERMIT FILE (the module docstring, 5), atomically, 0600: {"version", "receipt", "start", "at", "lineages":
    {lineage: {"status", "type", "case", "cell", "family", "version", "start", "run_sha", "k", "weak", "engine",
    "words"}}}. Every FWD1-judged lineage is listed (its status, `STATUSES`), so the swarm knows which take no sealed
    try; each row carries its lineage's FWD1_START ("start", the `fwd1_lineages` row's ISO date; L5, A48: the swarm
    keeps an index-only case-N lineage's S2 try until that session's close, and refuses a row without it); a pass
    names its program and the forward record's engine label its verdict was read under (`labels`: {engine id:
    label}). No t, no P&L and no figure of a program crosses. `PERMITS_VERSION` stays 1: "start" is an added key."""
    from .context import write_json

    lineages: dict[str, Any] = {}
    for row in status_rows(store, fdb=fdb, rule=rule):
        if row["status"] == "not_judged":
            continue
        passed = row["status"] == "pass"
        lineages[str(row["lineage"])] = {
            "status": row["status"], "type": row["type"], "case": row["case_"], "cell": row["cell"],
            "family": row["family"], "version": row["version"],
            "start": str(row["start"]) if row.get("start") else None,
            "run_sha": row["run_sha"] if passed else None,
            "k": int(row["k"]) if passed and row["k"] is not None else None,
            "weak": R.weak(str(row["type"]), int(row["k"])) if passed and row["k"] is not None else None,
            "engine": (labels or {}).get(row["engine"]) if passed and row["engine"] is not None else None,
            "words": row["words"] if passed else None}
    doc = {"version": PERMITS_VERSION, "screen": R.SCREEN, "receipt": rule.receipt_sha256, "start": pin["start"],
           "at": dt.datetime.fromtimestamp(float(at), dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "lineages": lineages}
    return write_json(Path(root) / PERMITS, doc)


def beside_for(root: str | Path | None, lineage: str) -> str | None:
    """The sentence of a lineage's forward PASS (its verdict row's), read-only within a second; None when there is none
    or the store cannot be read (the direction report then states that none is recorded). What stands beside every
    trade of a program seated on a forward pass (league/ops/dlane_report.py `EquityScreens`)."""
    if root is None or not lineage or not (Path(root) / DB).exists():
        return None
    try:
        db = open_store(root, readonly=True)
        try:
            row = db.execute("SELECT beside FROM fwd1_verdicts WHERE lineage=? AND verdict='pass'", (lineage,)).fetchone()
        finally:
            db.close()
    except sqlite3.Error:
        return None
    return None if row is None or not row["beside"] else str(row["beside"])


def report(store: sqlite3.Connection, *, rule: Any, pin: Mapping[str, Any], fdb: sqlite3.Connection | None = None,
           withheld: Collection[str] = (), withhold_etf: bool = False) -> dict[str, Any]:
    """THE OPERATOR'S REPORT (the module docstring, 5): counts by type and case and status, the expected zero-edge
    passes against the observed, every pass's sentence, and the lineages stalled under the newest engine id with the
    cause. Operator-only (it holds each pass's t and shadow P&L).
    POOL1 (A55a: PREREG-POOL1 sections 8 and 11 P1 item 5; a judge-module edit of this operator view only: FWD1-R's
    rule, checkpoints, verdicts and permit file are unchanged): a lineage on the pooled screen's POOL-route or hold
    list whose unit's verdict is not final (`withheld`, from league/ops/pool_screen.py `withheld`) has no pass
    sentence, no status count, no stall row and no entry in the registry's observed and expected passes; such
    lineages appear only as the count `pool_route`. With the pool's permit file failing closed (`withhold_etf`) every
    ETF lineage is withheld so. Once its unit is final it is shown again."""
    held = {str(x) for x in withheld}
    pooled = 0
    rows = []
    for row in status_rows(store, fdb=fdb, rule=rule):
        if row["judged"] and (str(row["lineage"]) in held or (withhold_etf and str(row["type"]) == "ETF")):
            pooled += 1
            continue
        rows.append(row)
    by: dict[str, Counter] = {}
    read: list[tuple[str, str, int]] = []
    for row in rows:
        key = f"{row['type']}|{row['case_']}" if row["judged"] else "not_judged"
        by.setdefault(key, Counter())[row["status"]] += 1
        if row["judged"] and row["k"] is not None:
            read.append((str(row["type"]), str(row["case_"]), int(row["k"])))
    expected = R.expected_passes(rule, read)
    causes: dict[str, str] = {}
    for row in store.execute("SELECT lineage, payload FROM fwd1_events WHERE kind='stalled' ORDER BY seq"):
        try:
            causes[str(row["lineage"])] = str(json.loads(row["payload"]).get("cause"))
        except (TypeError, ValueError):
            continue
    return {"screen": R.SCREEN, "receipt": rule.receipt_sha256, "start": pin["start"], "release": pin["release"],
            "counts": {key: dict(c) for key, c in sorted(by.items())},
            "registry": {key: {"observed": int(by.get(key, Counter())["pass"]), "expected": expected.get(key, 0.0)}
                         for key in sorted({f"{t}|{c}" for t, cs in R.CASES.items() for c in cs})},
            "passes": [{"lineage": r["lineage"], "family": r["family"], "version": r["version"], "k": r["k"],
                        "beside": r["beside"]} for r in rows if r["status"] == "pass"],
            "stalled": [{"lineage": r["lineage"], "k": r["k"], "cause": causes.get(str(r["lineage"]))}
                        for r in rows if r["status"] == "stalled"],
            "pool_route": pooled}


# --------------------------------------------------------------------------------------------------------- the job
def night(root: str | Path, *, rule: Any, settings: Mapping[str, Any] | None, now: float, base: str | Path | None,
          release: str | Path | None, runs: Any = None, families: Mapping[str, Mapping[str, Any]] | None = None,
          clock: Callable[[], float] = time.time, deadline: float = float("inf")) -> dict[str, Any]:
    """One night over the state root (the module docstring): the clock's row, the lineages' first sightings, their
    representatives before any forward day (`repick`: "repicked", "repick_frozen", "repick_kept", "repick_unread" in
    the receipt when not 0), the judge, the permit file and the report, and the run's own `fwd1_runs` row. The
    receipt (counts only). `families` (tests): the equity families by id, in place of the swarm store's (read-only).
    `deadline`: THE DEADLINE (the job passes it; +inf for a test). The child seconds are what ONE BUDGET A NIGHT
    leaves (`night_spent`)."""
    root = Path(root)
    c = cfg(settings)
    began = clock()
    store = open_store(root)
    fdb = forward_db.open_db(root, readonly=True)
    fdb.row_factory = sqlite3.Row
    own_runs = runs is None
    runs = runs if runs is not None else HouseRuns(root, budget_seconds=c["run_budget_seconds"], clock=clock, fdb=fdb,
                                                   settings=settings, deadline=deadline)
    try:
        pin = pinned(store, rule, base=base, release=release, now=now)
        if families is None:
            from ..swarm.store import SwarmStore
            from . import forward_register

            families = forward_register._families(SwarmStore(root, readonly=True))
        registered = register(store, fdb, families, rule=rule, pin_start=dt.date.fromisoformat(str(pin["start"])),
                              now=now)
        repicked = {k: v for k, v in repick(store, fdb, families, rule=rule,
                                            pin_start=dt.date.fromisoformat(str(pin["start"])), now=now).items() if v}
        budget = max(0.0, float(c["cpu_seconds_night"]) - night_spent(store, now))
        judge = Night(store, fdb, families, runs=runs, rule=rule, pin=pin, budget=budget, clock=clock,
                      settings=settings, deadline=deadline)
        tally = judge.run()
        labels = {int(r["id"]): str(r["label"]) for r in fdb.execute("SELECT id, label FROM fwd_engines")}
        write_permits(root, store, rule=rule, pin=pin, at=clock(), labels=labels, fdb=fdb)
        from .context import write_json
        from .pool_screen import withheld as pool_withheld

        held, all_etf = pool_withheld(root, settings)
        write_json(root / REPORT, report(store, rule=rule, pin=pin, fdb=fdb, withheld=held, withhold_etf=all_etf))
        with store:
            store.execute("INSERT INTO fwd1_runs(started, finished, seconds, lineages, at) VALUES (?,?,?,?,?)",
                          (float(began), float(clock()), round(judge.spent, 3),
                           int(store.execute("SELECT COUNT(*) FROM fwd1_lineages WHERE judged=1").fetchone()[0]),
                           float(clock())))
        return {"start": pin["start"], "registered": registered, **repicked, **{k: int(v) for k, v in tally.items()},
                "seconds": round(judge.spent, 3), "budget": round(budget, 3)}
    finally:
        if own_runs:
            runs.close()
        fdb.close()
        store.close()


def run(ctx: Any) -> dict[str, Any]:
    """THE JOB (league/ops/registry.py, after `forward_shadow` and after `forward_xs`): skipped with its switch off,
    with the forward record off or absent, with no pin, inside 09:00-17:30 New York on a session, and with THE
    DEADLINE too near (the next pre-open less `MARGIN_S`, within `WALL_S` of the start: a run is never at work when
    the pre-open starts); else `night` with that deadline. A House failure (a store under a lock, a child that could
    not start) is a failed receipt: the runner starts it again inside its grace."""
    from ..swarm import settings as swarm_settings
    from . import forward_shadow

    root = Path(ctx.root)
    settings = swarm_settings.load(root, config=getattr(ctx, "config", None))
    if cfg(settings)["mode"] == "off":
        return {"status": "skipped", "why": "elane.fwd1.mode is off"}
    if forward_db.mode(settings) == "off":
        return {"status": "skipped", "why": "elane.forward.mode is off: no forward record to judge"}
    rule, why = R.rule()
    if rule is None:
        return {"status": "skipped", "why": f"no verdict is read: {why}"}
    now = ctx.now()
    if forward_shadow.quiet(now):
        return {"status": "skipped", "why": "inside 09:00-17:30 New York time on a session: the night's run does it"}
    deadline = min(float(now) + WALL_S - MARGIN_S, preopen_deadline(now))
    if deadline - float(now) <= 10 * MIN_RUN_S:
        return {"status": "skipped", "why": "too near the next pre-open for a run to finish: the next night's run "
                                            "does it"}
    if not (root / forward_db.DB).exists():
        return {"status": "skipped", "why": "no forward record yet"}
    try:
        receipt = night(root, rule=rule, settings=settings, now=now, base=getattr(ctx, "base", None),
                        release=getattr(ctx, "release", None), clock=ctx.now, deadline=deadline)
    except sqlite3.Error as exc:
        return {"status": "failed", "error": f"a store could not be read or written ({type(exc).__name__})"}
    if int(receipt.get("house") or 0):
        ctx.alert("warning", f"forward_screen: {receipt['house']} checkpoints waited on the House's own failures (a run "
                             "the child did not finish): no program is marked, the next night asks again")
    if int(receipt.get("repick_kept") or 0):
        ctx.alert("warning", f"forward_screen: {receipt['repick_kept']} lineages keep a representative the rule no "
                             "longer picks: a better version of the same first_day was not taken (a forward day or "
                             "a judge row of the lineage came first, or it would change the lineage's type, case or "
                             "judged flag); each one's `kept` event names both pids, and the judge reads the one kept")
    if int(receipt.get("repick_unread") or 0):
        ctx.alert("warning", f"forward_screen: {receipt['repick_unread']} lineages' representatives could not be read "
                             "again before their first forward day (a store could not be read): each is kept as first "
                             "sighted tonight, and the next run asks again while no forward day exists")
    if int(receipt.get("stalled") or 0):
        ctx.alert("warning", f"forward_screen: {receipt['stalled']} lineages STALLED tonight: their next step waited on "
                             f"the House on {STALL_NIGHTS} of the record's nights (the report's 'stalled' names the "
                             "cause); they cost no run until the record opens a new engine id, and nothing marks them")
    return receipt


__all__ = ["JOB", "DB", "PERMITS", "PERMITS_VERSION", "REPORT", "MODES", "SEATS", "DEFAULTS", "BOUNDS", "VERDICTS",
           "NOT_JUDGED", "PREFERRED", "SEALED_TAGS", "SEALED_STATE", "PRECHECK_STATE", "ENGINE_TOUCH", "EVENT_KINDS",
           "STALL_NIGHTS", "STATUSES", "NIGHT_WINDOW_S", "WALL_S", "MARGIN_S", "PREOPEN_BEFORE_S", "MIN_RUN_S",
           "TABLES", "SCHEMA", "REPICK_ONLY", "RECORD_DAY_TABLES", "UNJUDGED_EVENTS", "REPICK_KEEPS", "REPICK_WHY",
           "KEPT_WHY", "KEPT_BECAUSE", "cfg",
           "open_store", "event", "lot_sides", "pinned", "representative", "family_sealed", "type_of", "case_of",
           "cell_of", "sighting", "register", "frozen", "repick", "OwnFloorRefused", "Late", "HouseRuns",
           "engine_reading", "preopen_deadline", "night_spent", "Night", "status_rows", "write_permits", "beside_for",
           "report", "night", "run"]
