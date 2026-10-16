"""POOL1's job, THE RECORD HALF P1 (the owner's A55, pre-registered in A55a: scratch/pooled-screen/PREREG-POOL1.md
sha256 f42bcdc1..., section 11 P1; the receipt contract POOL1-RECEIPT-1, scratch/pooled-screen/RECEIPT-CONTRACT.md,
section 9): the pooled-by-mechanism forward screen's units, members, route list and looks, kept append-only, and the
permit file of ids and words the swarm reads. The rule is league/ops/pool_rule.py; every definition the calibration
gates is computed with the calibration's own pinned code (league/ops/pool_calib/, `pool_rule.calib`).

Owner: the POOL1 build. Protected (league/ops/ is FORBIDDEN to every role). Ops only (no module of league/swarm,
league/equity, league/live or league/gym imports it): it reads `<state>/forward.sqlite` (E3's record),
`<state>/forward-screen.sqlite` (FWD1-R's judge) and the swarm store READ-ONLY, the repository's pin and receipt, and
writes only its own `<state>/pool-screen.sqlite` (0600, WAL, append-only by trigger: `SCHEMA`), the permit file
(`PERMITS`: ids and words only) and the operator's report (`REPORT`). It moves no money, opens no seat and edits no
setting. MODE RECORD ONLY: `elane.pool.seats` is P2's switch and nothing here reads it; no seat exists in P1.

WITH ITS SWITCH OFF NOTHING RUNS (`elane.pool.mode` "off", the code's default; policy.json ships "record"): a `skipped`
receipt, and THE PERMIT FILE IS KEPT (mode off stops the job, not the file: the POOL-route refusal never lifts).
WITHOUT A PIN, ITS RECEIPT AND ITS CONFORMANCE NOTHING IS JUDGED (`pool_rule.rule`: `elane.pool_screen` of the
repository's policy.json, docs/benchmarks/pool_screen_1.json at the pin's sha256, the vendored code at the receipt's
shas, and every conformance vector reproduced on this box once a (receipt, code, numpy, Python), `pool_conform`): no
clock, no unit, no route list, no look; the job still writes the permit file from what its store and the existing
file hold, so the swarm reads a file of the job's.

THE NIGHT (`Night.run`, once a record night: a second start on the same `MAX(fwd_runs.through)` writes nothing):
1. THE CLOCK AND THE ROUTE LIST (`Night.clock_row`, PREREG 7.2, 9, 12; the contract's 6.4): the job's first sighting
   of the receipt is stored once (`pool_sighting`: the release's start from the deploys record, else the sighting's
   own time); the first NEW record night written after it is the clock night. FIRST THE CLOCK-START CONFORMANCE
   (`Night.clock_check`): every founding cluster that could be clocked (not refuted, not ineligible, not report-only)
   has its floors recomputed with the vendored `cluster_floor` steps on the House's own Train series (`pool_train`:
   the vendored House job's `one_run` records, founders first, over nights inside the budget), the receipt's members,
   joins 0, its boot seed, the pin's caps and B 2000 (its resamples kept in `pool_boot`, so the work spans nights);
   every value of the receipt's `c_own_at_pin` must be equal, or the cluster is NONCONFORMING: not clocked, its members
   per-program, an alarm. Then, in ONE transaction, the founding units (`pool_units`: the receipt's cells and clusters,
   stage 1, each cluster's U_u at the FWD1-R checkpoint count its members read before the clock (P1 D7), the caps,
   report-only, ineligible, conforming), the founders' membership (`pool_members`), a REFUTED or INELIGIBLE verdict for
   each such unit and THE POOL-ROUTE LIST (`pool_routes`) from FWD1's lineages as of that night. The clock starts at
   the next session (`next_session(night)`). A night that cannot finish this writes nothing and the next night is the
   first (each later night moves the clock a session; after `CLOCK_ALARM_NIGHTS` such nights an alarm). A founder FWD1
   has no row for yet is decided later, once it has one (a missing row is a wait, never a route). A STORE LOST: a
   permit file that already names this receipt with a clock while the store holds no clock refuses the clock (no
   judging, an alarm; the file's lists are carried whole).
2. THE LATER LINEAGES (`Night.sight`, `Night.decide`; section 1.1, 1.3): a registry lineage the receipt does not list,
   with a passing version, is read once: a panel, a stocks symbol, the beta class, no declared class or an event reader
   (its card, or `pool_rule.reads_events` on its frozen code) is out (`pool_members`, why); otherwise, while FWD1 judges
   it as case N it is HELD (`pool_holds`: no FWD1-R seat, no sealed try) until the House decides it. It is decided once
   FWD1 has its row (a missing row is a wait), its own `pool_train` series and every earlier member's (by pid) exist or
   are out: out by the vendored `member_from_runs` (its exposure, its group, a stock); merged into an earlier member
   (vendored `merge_copies`: it follows that member's route, never a member); assigned (`pool_rule.assign`) to the cell
   of its group whose founders' Train D its Train z correlates with most at >= rho_assign: a member from its first
   counted day after the clock (staggered), on the POOL route when the unit is pending and its cluster is clocked. One
   assigned to a final, ineligible or nonconforming unit is not a member and stays per-program; so is one of a
   report-only cluster (a member there, on FWD1-R). A held lineage leaves the hold by its release or the route.
3. THE HOUSE'S TRAIN SERIES (`pool_train`, `pool_params`, the contract's 4.6): each member's four Train parts (e0k10,
   e0k15, e1k10, e1k15) are the vendored House job's `one_run` records in the job's own decider child (`PoolRuns`),
   written once a part; K's Train counts from the same runs' lots; its constants (mu, wbar, sigma, abar, abar_v), its
   House group and its status from the vendored `member_from_runs` (`fit_constants` at the 2 bp floor haircut). The
   market is the vendored `prices()` record per era (`pool_market`). A run the House cannot finish on two nights is
   the program's own failure (out). A member without its Train series at a look is a House wait, never z = 0.
4. THE CELL SESSIONS (`Night.classify`; `pool_sessions`, first write stands): each session from the clock, in order,
   once the record holds a later night, every active member's row for it has come (or `STALL_NIGHTS` record nights
   have passed) and every lineage registered by its close is decided: a CELL SESSION when at least `M_MIN` active
   members have counted rows.
5. THE LOOKS (`Night.look`; section 2, 3; `pool_checks`, `pool_verdicts`, `pool_floors`, `pool_boot`): at 40, 60 and
   120 cell sessions, on exactly D_1..k. Each member-day's reading (`pool_fwd`: the record's r, r15, w, b with the
   live-like re-price, the haircut, the sides and the House's per-symbol exposure (screen.series of that symbol's lots,
   the House job's accounting) and returns from its own forward run, kept where that run IS the record's day) is
   written once and D is computed only at looks. The cluster is re-tested by the vendored member rule (a join's U_u is
   the union bound of its parts: a cap only falls; a recorded pass is re-derived at the joint bar, LOST never gained);
   c_own by the vendored floor pipeline on the cluster's members active through k, their joins, the receipt's boot seed
   and the caps of the count read (`pool_rule.house_floor`, its 2,000 resamples spread over nights); c_used with the
   matched minimum of the receipt's table; the stress leg; the placebo leg (999 pseudo-cells of the group's skill-free
   controls on the same sessions); the zeroed-days void. A non-final look writes the word and the sha256 of D_1..k
   only (no interim figure); a PASS, a FAIL at 120 and a VOID write the series with the verdict, once.
6. THE DEMOTION (`Night.demotions`, section 7.1): a PASS cell's post-pass sessions, read on the members active at the
   pass, every 20th: DEMOTED (sticky) on the rule; an engine move that touches judged days voids a pending cell and
   loses a pass (re-derived at the same k and bar), never gains one.
7. THE PERMIT FILE (`write_permits`, `PERMITS`), written right after the routes and holds of the night (in a finally)
   and again at its end: the receipt's sha, the clock, each unit's word, THE POOL-ROUTE LIST and the hold list, every
   registry lineage's pool cell and cluster id, and the eligible lineages after a PASS. IDS AND FIXED WORDS ONLY
   (`pool_rule.figure_free`; a reason is a word of `WHY_WORDS`, its detail goes to the report). NEVER SHORTER: the
   existing readable file's routes are carried whole and its holds unless the store records their release; an
   existing file that cannot be read is never overwritten (an alarm). The job never deletes it.
8. THE REPORT (`REPORT`, operator-only): units by word (final words only), counts, waits and stalls, the
   conformance and the clock's reasons in words, "X passes of J units; Y expected at zero edge". No interim figure.

A FAILURE OF THE HOUSE NEVER MARKS A CELL: a child that did not finish, a store under a lock, a run that does not
reproduce the record: nothing is written, and the next night reads the same D_1..k. THE STALL RULE (`STALL_NIGHTS`):
a cell whose look waited on the House on that many record nights under one engine id is STALLED (a House warning; it
is asked again each night). A pool-job failure is an ops alarm, never a stall cause of league/ops/stall.py. The
DEADLINE is forward_screen's (the earlier of the job's wall and the next pre-open, less `MARGIN_S`); quiet 09:00-17:30
New York on a session. THE STATED LIMITS OF P1 (scratch/pooled-screen/DEVIATIONS.log P1 D3, D4): a cell first judged
after the clock is not clocked here, and a later lineage with FWD1-R checkpoints read before its hold is released to
FWD1-R. A CODE ROLLBACK to a release below P1 has no reader of the permit file and lifts the refusal: while the route
list is non-empty it needs a captain amendment (docs/operations.md).

Standard library at import; numpy, league.equity, the swarm and the vendored calibration inside the functions that
need them.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import os
import platform
import sqlite3
import time
import zlib
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from . import forward_db
from . import forward_screen as FS
from . import fwd1_rule as F
from . import pool_rule as P

JOB = "pool_screen"
DB = "pool-screen.sqlite"
#: The permit file (ids and words only) the swarm reads: league/swarm/elane_forward.py `POOL_PERMITS`, and the
#: forward report's and FWD1's report readers (`forward_report.POOL_PERMITS`); tests hold the names equal.
PERMITS = "pool-screen-permits.json"
PERMITS_VERSION = 1
REPORT = "pool-screen-report.json"
#: `elane.pool.*` (policy.json ships mode "record", seats "off"; the code defaults are both off).
MODES = ("off", "record")
SEATS = ("off", "on")
DEFAULTS: dict[str, Any] = {"mode": "off", "seats": "off", "cpu_seconds_night": 600}
BOUNDS: dict[str, tuple[int, int]] = {"cpu_seconds_night": (60, 1200)}
#: THE STALL RULE: record nights a cell's look may wait on the House under one engine id before it is STALLED.
STALL_NIGHTS = 5
#: Record nights the clock may wait (a receipt pinned, the clock not started) before an alarm fires each night.
CLOCK_ALARM_NIGHTS = 5
#: Nights a member's Train run may fail on the House before it is the program's own failure (the calibration's C5).
TRAIN_FAILS = 2
#: THE DEADLINE (forward_screen's): no run past the earlier of the job's wall less `MARGIN_S` and the next pre-open less
#: `MARGIN_S` (a test holds `WALL_S` to the registry's).
WALL_S = 1500
MARGIN_S = FS.MARGIN_S
MIN_RUN_S = FS.MIN_RUN_S
#: A member enters as z = 0 throughout when more than this share of its days does not reproduce (section 2, step 1).
UNREPRODUCED_MAX = 0.10
#: The route words of `pool_members.route` ("per_program": a founder of a cell below M_MIN or of a cluster that is not
#: clocked; it stays on its per-program route).
ROUTES = ("pool", "fwd1", "sealed", "merged", "out", "new_cell", "final_unit", "per_program")
#: The FIXED WORDS a permit file's "why" may carry (never a figure; the detail goes to the report and an alarm).
WHY_WORDS = ("no_receipt", "no_record", "nonconforming_receipt", "store_lost", "clock_wait", "pool_off")
EVENT_KINDS = ("pinned", "clock_wait", "sighting", "sighted", "held", "released", "routed", "train", "train_failed",
               "decided", "waited", "stalled", "house", "look", "verdict", "lost", "demoted", "engine_switched", "joined",
               "unreproduced", "ineligible", "new_cell", "conformance", "nonconforming", "store_lost", "permits_kept",
               "permits_refused", "clock_alarm", "look_failed", "market")
APPEND_ONLY_ERROR = "pool-screen.sqlite is append-only"

_TABLES = """
CREATE TABLE IF NOT EXISTS pool_sighting (sha TEXT PRIMARY KEY, release TEXT NOT NULL, release_start REAL NOT NULL,
  evidence TEXT NOT NULL, at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS pool_conform (key TEXT PRIMARY KEY, sha TEXT NOT NULL, ok INTEGER NOT NULL, why TEXT,
  results TEXT NOT NULL, at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS pool_pins (sha TEXT PRIMARY KEY, release TEXT NOT NULL, release_start REAL NOT NULL,
  before TEXT, night TEXT NOT NULL, clock TEXT NOT NULL, evidence TEXT NOT NULL, at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS pool_clockcheck (cluster TEXT PRIMARY KEY, conforming INTEGER NOT NULL, row TEXT NOT NULL,
  at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS pool_units (cell TEXT PRIMARY KEY, cls TEXT NOT NULL, grp TEXT NOT NULL, cluster TEXT NOT NULL,
  founders TEXT NOT NULL, clock TEXT NOT NULL, origin TEXT NOT NULL, refuted INTEGER NOT NULL, stage1 TEXT NOT NULL,
  u_point REAL NOT NULL, u_bound REAL NOT NULL, cap REAL NOT NULL, wall REAL NOT NULL, report_only INTEGER NOT NULL,
  report_why TEXT, ineligible INTEGER NOT NULL, conforming INTEGER NOT NULL, clocked INTEGER NOT NULL,
  fwd1_count INTEGER NOT NULL, at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS pool_members (lineage TEXT PRIMARY KEY, pid INTEGER, cell TEXT, route TEXT NOT NULL,
  joins TEXT, declared TEXT, assigned INTEGER NOT NULL, merged_into TEXT, infer_key TEXT, why TEXT, corr TEXT,
  at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS pool_routes (lineage TEXT PRIMARY KEY, cell TEXT, cluster TEXT, night TEXT NOT NULL,
  why TEXT NOT NULL, at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS pool_holds (lineage TEXT PRIMARY KEY, night TEXT NOT NULL, why TEXT NOT NULL,
  at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS pool_releases (lineage TEXT PRIMARY KEY, why TEXT NOT NULL, at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS pool_train (pid INTEGER NOT NULL, part TEXT NOT NULL, record TEXT NOT NULL, sha TEXT NOT NULL,
  k TEXT, at REAL NOT NULL, PRIMARY KEY (pid, part)) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS pool_trainfail (pid INTEGER NOT NULL, night TEXT NOT NULL, why TEXT NOT NULL, at REAL NOT NULL,
  PRIMARY KEY (pid, night)) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS pool_params (pid INTEGER PRIMARY KEY, status TEXT NOT NULL, symbols TEXT, mu TEXT, wbar TEXT,
  sigma REAL, abar REAL, abar_v TEXT, grp TEXT, why TEXT, k_close INTEGER, k_sessions INTEGER, at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS pool_sigma (cell TEXT PRIMARY KEY, sigma_tilde REAL NOT NULL, at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS pool_market (era INTEGER PRIMARY KEY, record TEXT NOT NULL, sha TEXT NOT NULL,
  at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS pool_controls (pid INTEGER PRIMARY KEY, grp TEXT NOT NULL, symbols TEXT NOT NULL,
  mu TEXT NOT NULL, wbar TEXT NOT NULL, sigma REAL, at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS pool_fwd (pid INTEGER NOT NULL, day TEXT NOT NULL, engine INTEGER NOT NULL, row TEXT NOT NULL,
  at REAL NOT NULL, PRIMARY KEY (pid, day, engine)) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS pool_sessions (cell TEXT NOT NULL, day TEXT NOT NULL, engine INTEGER NOT NULL,
  counted INTEGER NOT NULL, active INTEGER NOT NULL, session INTEGER NOT NULL, at REAL NOT NULL,
  PRIMARY KEY (cell, day, engine)) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS pool_clusters (look TEXT NOT NULL, cluster TEXT NOT NULL, cells TEXT NOT NULL,
  u_point REAL NOT NULL, u_bound REAL NOT NULL, report_only INTEGER NOT NULL, at REAL NOT NULL,
  PRIMARY KEY (look, cluster)) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS pool_floors (cluster TEXT NOT NULL, look TEXT NOT NULL, row TEXT NOT NULL, at REAL NOT NULL,
  PRIMARY KEY (cluster, look)) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS pool_boot (cluster TEXT NOT NULL, look TEXT NOT NULL, null_ TEXT NOT NULL, era INTEGER NOT NULL,
  key TEXT NOT NULL, shape TEXT NOT NULL, blob BLOB NOT NULL, at REAL NOT NULL,
  PRIMARY KEY (cluster, look, null_, era, key)) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS pool_checks (cell TEXT NOT NULL, k INTEGER NOT NULL, engine INTEGER NOT NULL, word TEXT NOT NULL,
  sha TEXT NOT NULL, look TEXT NOT NULL, at REAL NOT NULL, PRIMARY KEY (cell, k)) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS pool_verdicts (cell TEXT PRIMARY KEY,
  word TEXT NOT NULL CHECK (word IN ('PASS','FAIL','VOID','REFUTED','INELIGIBLE')), k INTEGER, day TEXT, engine INTEGER,
  t REAL, c_used REAL, series TEXT, mar TEXT, placebo INTEGER, why TEXT, at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS pool_post (cell TEXT NOT NULL, n INTEGER NOT NULL, sha TEXT NOT NULL, word TEXT NOT NULL,
  at REAL NOT NULL, PRIMARY KEY (cell, n)) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS pool_demotions (cell TEXT PRIMARY KEY, n_post INTEGER, why TEXT NOT NULL, at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS pool_runs (seq INTEGER PRIMARY KEY AUTOINCREMENT, night TEXT, started REAL NOT NULL,
  finished REAL NOT NULL, seconds REAL NOT NULL, at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS pool_events (seq INTEGER PRIMARY KEY AUTOINCREMENT, at REAL NOT NULL, kind TEXT NOT NULL,
  cell TEXT, lineage TEXT, once TEXT, payload TEXT NOT NULL DEFAULT '{}');
CREATE UNIQUE INDEX IF NOT EXISTS pool_events_once ON pool_events(kind, IFNULL(cell, ''), IFNULL(lineage, ''), once)
  WHERE once IS NOT NULL;
"""
TABLES = ("pool_sighting", "pool_conform", "pool_pins", "pool_clockcheck", "pool_units", "pool_members", "pool_routes",
          "pool_holds", "pool_releases", "pool_train", "pool_trainfail", "pool_params", "pool_sigma", "pool_market",
          "pool_controls", "pool_fwd", "pool_sessions", "pool_clusters", "pool_floors", "pool_boot", "pool_checks",
          "pool_verdicts", "pool_post", "pool_demotions", "pool_runs", "pool_events")
#: APPEND-ONLY BY TRIGGER: UPDATE and DELETE abort on every table (a replace too: recursive triggers are on).
SCHEMA = "PRAGMA recursive_triggers=ON;\n" + _TABLES + "".join(
    f"CREATE TRIGGER IF NOT EXISTS {t}_no_{verb.lower()} BEFORE {verb} ON {t} BEGIN SELECT RAISE(ABORT, "
    f"'{APPEND_ONLY_ERROR}'); END;\n" for t in TABLES for verb in ("UPDATE", "DELETE"))


# ------------------------------------------------------------------------------------------------------------ settings
def cfg(settings: Mapping[str, Any] | None) -> dict[str, Any]:
    """`elane.pool` in the swarm's settings: `mode` ("off" | "record"), `seats` ("off" | "on": P2's; read by nothing
    here) and the night's child seconds. A malformed value is its default; an unreadable block is `DEFAULTS`."""
    out = dict(DEFAULTS)
    raw = settings.get("elane") if isinstance(settings, Mapping) else None
    raw = raw.get("pool") if isinstance(raw, Mapping) else None
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
    """`<root>/pool-screen.sqlite`, rows as `sqlite3.Row`: created 0600 (WAL) with `SCHEMA` when writable; `readonly`:
    `guard.connect_ro` (OperationalError when absent)."""
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


def _dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def record_sha(record: Mapping[str, Any]) -> str:
    """A House job record's sha (the receipt's `train_sha256` rule): sha256 of its sorted, compact JSON."""
    return hashlib.sha256(_dumps(record).encode()).hexdigest()


def event(store: sqlite3.Connection, kind: str, *, at: float, cell: str | None = None, lineage: str | None = None,
          once: str | None = None, payload: Mapping[str, Any] | None = None) -> bool:
    """One `pool_events` row (ids, counts and words only); with `once` at most one a (kind, cell, lineage, once).
    Whether it was written. The caller commits."""
    if kind not in EVENT_KINDS:
        raise ValueError(f"no pool screen event kind {kind!r}")
    cursor = store.execute("INSERT OR IGNORE INTO pool_events(at, kind, cell, lineage, once, payload) VALUES (?,?,?,?,?,?)",
                           (float(at), kind, cell, lineage, once, _dumps(dict(payload or {}))))
    return cursor.rowcount == 1


def conformance_key(receipt: P.Receipt) -> str:
    """The key a conformance result is kept under (the contract's 6.3): the receipt's sha, the vendored code's shas,
    numpy's and Python's versions."""
    import numpy as np

    text = _dumps({"receipt": receipt.sha256, "calib": dict(P.CALIB_SHA256), "numpy": np.__version__,
                   "python": platform.python_version()})
    return hashlib.sha256(text.encode()).hexdigest()


def conformed(root: str | Path, at: float) -> Callable[[P.Receipt, P.Calib], tuple[bool, str | None]]:
    """`pool_rule.load_receipt`'s conformance, run ONCE a (receipt, vendored code, numpy, Python) and kept in this
    store's `pool_conform` (the contract's 6.3): a later night reads the kept result."""

    def check(receipt: P.Receipt, cal: P.Calib) -> tuple[bool, str | None]:
        key = conformance_key(receipt)
        store = open_store(root)
        try:
            row = store.execute("SELECT ok, why FROM pool_conform WHERE key=?", (key,)).fetchone()
            if row is not None:
                return bool(row["ok"]), row["why"]
            ok, why, results = P.conform(receipt, cal)
            with store:
                store.execute("INSERT OR IGNORE INTO pool_conform(key, sha, ok, why, results, at) VALUES (?,?,?,?,?,?)",
                              (key, receipt.sha256, int(ok), why, _dumps(results), float(at)))
                event(store, "conformance", at=float(at), once=key, payload={"ok": bool(ok), "why": why})
            return ok, why
        finally:
            store.close()

    return check


# ------------------------------------------------------------------------------------------------------- the readings
def _iso(t: float) -> str:
    return dt.datetime.fromtimestamp(float(t), dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fwd1_facts(root: str | Path, fdb: sqlite3.Connection) -> dict[str, dict[str, Any]] | None:
    """FWD1-R's facts of every lineage it sighted (forward-screen.sqlite READ-ONLY): its `fwd1_lineages` row, its
    status (`forward_screen.status_rows`), the last checkpoint it read (`k_read`, 0 for none) and when its first
    checkpoint was read (`first_check_at`). {} with no FWD1 store yet; None when it cannot be read."""
    path = Path(root) / FS.DB
    if not path.exists():
        return {}
    try:
        sdb = FS.open_store(root, readonly=True)
    except sqlite3.Error:
        return None
    try:
        rows = FS.status_rows(sdb, fdb=fdb)
        checks = {str(r["lineage"]): (int(r["k"]), float(r["at"])) for r in sdb.execute(
            "SELECT lineage, MAX(k) AS k, MIN(at) AS at FROM fwd1_checks GROUP BY lineage")}
    except sqlite3.Error:
        return None
    finally:
        sdb.close()
    out = {}
    for row in rows:
        k, at = checks.get(str(row["lineage"]), (0, None))
        out[str(row["lineage"])] = {**row, "k_read": int(k), "first_check_at": at}
    return out


def fwd1_case_n(row: Mapping[str, Any] | None) -> bool:
    """FWD1 judges this lineage as case N (an ETF lineage, never sealed, judged; not voided)."""
    return isinstance(row, Mapping) and str(row.get("type")) == "ETF" and str(row.get("case_")) == "N" \
        and int(row.get("judged") or 0) == 1 and str(row.get("status")) != "void"


def _registry(fdb: sqlite3.Connection) -> dict[str, list[dict[str, Any]]]:
    """{lineage: its registry rows but the controls, pid order} (forward_screen's reader)."""
    return FS._registry(fdb)


def record_night(fdb: sqlite3.Connection) -> str | None:
    row = fdb.execute("SELECT MAX(through) FROM fwd_runs").fetchone()
    return None if row is None or row[0] is None else str(row[0])


def first_night(fdb: sqlite3.Connection, release_start: float) -> tuple[str | None, str | None]:
    """(the record's night tonight when it is a NEW night written after the release began, the record's last night
    before it): a weekend release's first such night is the next session's (section 12)."""
    before = fdb.execute("SELECT MAX(through) FROM fwd_runs WHERE finished < ?", (float(release_start),)).fetchone()
    before = None if before is None or before[0] is None else str(before[0])
    now = record_night(fdb)
    if now is None:
        return None, before
    after = fdb.execute("SELECT 1 FROM fwd_runs WHERE through = ? AND finished >= ? LIMIT 1",
                        (now, float(release_start))).fetchone()
    if after is None or (before is not None and not now > before):
        return None, before
    return now, before


def counted_by_day(fdb: sqlite3.Connection, pid: int, engine: int) -> dict[str, dict[str, Any]]:
    return {str(r["day"]): r for r in forward_db.counted_days(fdb, int(pid), engine=int(engine))}


def stored_days(fdb: sqlite3.Connection, pid: int, engine: int) -> set[str]:
    return {str(r[0]) for r in fdb.execute("SELECT day FROM fwd_days WHERE pid=? AND engine=?", (int(pid), int(engine)))}


def _card(swarm: Any, fid: str | None) -> dict[str, Any] | None:
    """A family's immutable birth card (`cards.card_of`: its own row, else its fork parent's by card_sha), or None."""
    if swarm is None or not fid:
        return None
    try:
        from ..swarm import cards

        found = cards.card_of(swarm, str(fid))
    except Exception:  # noqa: BLE001 - no card table: no card
        return None
    return dict(found["card"]) if found and isinstance(found.get("card"), Mapping) else None


def _infer(fam: Mapping[str, Any] | None) -> str | None:
    """`cards.infer_key`'s class of the family's mechanism text, reported beside only (section 1.1)."""
    if not isinstance(fam, Mapping) or not fam.get("mechanism"):
        return None
    try:
        from ..swarm import cards

        found = cards.infer_key(fam.get("mechanism"), fam.get("structure"))
    except Exception:  # noqa: BLE001
        return None
    return None if not found else found.get("class")




# --------------------------------------------------------------------------------------------------------- the runs
class _Capture:
    """A decider handing every call on unchanged, keeping the last engine run's result (its lots: K's Train counts of
    the very run the House job's `one_run` reads)."""

    def __init__(self, decider: Any):
        self._decider = decider
        self.result: Mapping[str, Any] | None = None

    def kind(self, kind: str, op: str, payload: Mapping[str, Any], **kw: Any) -> Any:
        answer = self._decider.kind(kind, op, payload, **kw)
        if op == "run":
            self.result = answer.get("result") if isinstance(answer, Mapping) else None
        return answer

    def __getattr__(self, name: str) -> Any:
        return getattr(self._decider, name)


class PoolRuns(FS.HouseRuns):
    """THE POOL'S OWN RUNNER (section 11 P1 item 2; the contract's 4.6), a subclass of forward_screen's `HouseRuns`
    (whose runner is unchanged), in the job's own decider child: a member's Train parts by the VENDORED House job's
    `one_run` (so the series is the calibration's by construction), the market by its `prices()`, and the forward run
    with the House job's per-symbol accounting. Each method raises the child's or the data's failure (the House's:
    nothing is written, asked again)."""

    def train_part(self, cal: P.Calib, pid: int, part: str) -> tuple[dict[str, Any], dict[str, int] | None]:
        """(the vendored `one_run` record of one Train part of the member's registered version, K's counts of that
        run {"close_days", "sessions"} for a k 1.0 part that ended ok, else None)."""
        from ..equity import bands as eq_bands

        decider = _Capture(self._child())
        rec = cal.house_job.one_run(self.root, decider, self.fdb, int(pid), str(part), [], run_budget=self.budget())
        k = None
        if str(part).endswith("k10") and rec.get("status") == "ok" and isinstance(decider.result, Mapping):
            floor = eq_bands.seat_settings().k_floor
            k = {"close_days": int(eq_bands.close_days(decider.result.get("lots") or [], floor=floor)),
                 "sessions": int(eq_bands.run_sessions(decider.result))}
        return dict(rec), k

    def market(self, cal: P.Calib) -> dict[str, Any]:
        """The vendored House job's `prices()`: each ETF's cost-free close-to-close return on every Train-era session."""
        return dict(cal.house_job.prices(self.root))

    def forward_series(self, program: Any, *, settings: Mapping[str, Any] | None,
                       fdb: sqlite3.Connection | None = None) -> dict[str, Any]:
        """THE FORWARD RUN of a member (E3's `Shadow.slice` and its k 1.0 run, as `HouseRuns.forward_sides` reads it),
        with the House job's own per-symbol accounting (`one_run`'s: each symbol's exposure the `screen.series` of
        that symbol's lots, the sides `forward_screen.lot_sides`, each symbol's close-to-close return, 0 where a close
        is missing): {"symbols", "r": {day: r}, "ws": {day: [w_s]}, "R": {day: [R_s]}, "sides", "entries", "exits",
        "bars"}."""
        import numpy as np

        from ..equity import config as econfig
        from ..equity import ctx as eq_ctx
        from ..equity import screen as S
        from ..equity.program import parse_needs
        from . import forward_shadow

        fdb = fdb if fdb is not None else self.fdb
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
        needs = parse_needs(whole.needs)
        universe = [str(s) for s in (result.get("symbols") or needs.symbols)]    # one_run's universe rule
        lots = result.get("lots") or []
        capital = result.get("capital") or econfig.SLEEVE_USD
        ws = np.zeros((len(universe), len(days)))
        for j, sym in enumerate(universe):
            mine = [lot for lot in lots if str(lot.get("symbol")) == sym]
            if mine:
                ws[j] = np.asarray(S.series(mine, bars, universe=universe, capital=capital).w, dtype=np.float64)
        R = np.asarray(_returns(bars, universe))
        sides = FS.lot_sides({"lots": lots})
        entered = Counter(str(lot.get("entry_day"))[:10] for lot in lots)
        hashes = {day: forward_db.bars_hash(eq_ctx.inputs_from_bars(
            bars, int(bars.first) + i - 1, needs=needs, cash=0.0, equity=0.0, budget=0.0, caps={}, params={}))
            for i, day in enumerate(days)}
        return {"symbols": universe, "r": {d: float(v) for d, v in zip(days, series.r)},
                "ws": {d: ws[:, i].tolist() for i, d in enumerate(days)},
                "R": {d: R[:, i].tolist() for i, d in enumerate(days)},
                "sides": {d: float(sides.get(d, 0.0)) for d in days},
                "entries": {d: int(entered.get(d, 0)) for d in days},
                "exits": {d: int(v) for d, v in zip(days, series.exits)}, "bars": hashes,
                "lots": [dict(lot) for lot in lots]}

    def control_train(self, spec: Mapping[str, Any]) -> list[dict[str, Any] | None]:
        """A control's Train-era replay of its hash law (section 2.1; reads no price for its lots): each era's
        {"days", "symbols", "r0", "ws", "R"} (its cost-free r0 by `forward_controls.cost_free`, from the pools' third
        session). A lot the law draws in a symbol with no price on some session of the era (XLC before its 2018 listing)
        is no position there and is left out of that era's replay (it feeds sigma alone, a scale constant)."""
        import numpy as np

        from ..equity import config as econfig
        from ..equity import screen as S
        from ..equity.store import EquityStore, MissingData
        from . import forward_controls

        store = EquityStore(self.root / "equity-daily")
        symbols = [str(s) for s in spec.get("symbols") or ()]
        out: list[dict[str, Any] | None] = []
        epoch = dt.date(1970, 1, 1)
        for first, last in econfig.TRAIN_ERA_SEGMENTS:
            held = []
            for sym in symbols:
                try:
                    one = store.span([sym], first, last, history=1)
                except MissingData:
                    continue
                if np.isfinite(np.asarray(one.adj[sym], dtype=np.float64)[:, [0, 3]]).all():
                    held.append(sym)
            if not held:
                out.append(None)
                continue
            bars = store.span(held, first, last, history=1)
            sessions = [bars.day(i) for i in range(int(bars.first) - 1, bars.n)]
            lots0 = [lot for lot in forward_controls.control_lots(spec, sessions, k=0.0) if lot["symbol"] in held]
            r0 = forward_controls.cost_free(lots0, bars, capital=econfig.SLEEVE_USD)
            days = [(epoch + dt.timedelta(days=int(d))).isoformat() for d in bars.days[int(bars.first):]]
            ws = control_exposure(lots0, bars, symbols)
            R = _returns(bars, symbols)                        # a symbol left out: no bar, return 0, exposure 0
            skip = S.POOL_SKIP
            out.append({"days": days[skip:], "symbols": symbols, "r0": np.asarray(r0)[skip:].tolist(),
                        "ws": np.asarray(ws)[:, skip:].tolist(), "R": np.asarray(R)[:, skip:].tolist()})
        return out

    def control_forward(self, program: Any, *, settings: Mapping[str, Any] | None,
                        fdb: sqlite3.Connection | None = None) -> dict[str, Any]:
        """A control's forward per-symbol exposure (its hash law replayed on its own sessions, as E3's night draws
        it) and the symbols' returns: {"symbols", "ws": {day: [w_s]}, "R": {day: [R_s]}}."""
        import numpy as np

        from . import forward_controls, forward_shadow

        fdb = fdb if fdb is not None else self.fdb
        night = forward_shadow.Shadow(self.root, fdb, decider=None, settings=settings, clock=self.clock)
        spec = json.loads(program.code)
        symbols = [str(s) for s in spec.get("symbols") or ()]
        bars = night.store.bars(symbols, "forward", history=1, start=program.first_day, end=None)
        if bars.n <= bars.first or bars.first < 1:
            return {"symbols": symbols, "ws": {}, "R": {}}
        sessions = [bars.day(i) for i in range(int(bars.first) - 1, bars.n)]
        lots = forward_controls.control_lots(spec, sessions, k=0.0)
        epoch = dt.date(1970, 1, 1)
        days = [(epoch + dt.timedelta(days=int(d))).isoformat() for d in bars.days[int(bars.first):]]
        ws = np.asarray(control_exposure(lots, bars, symbols))
        R = np.asarray(_returns(bars, symbols))
        return {"symbols": symbols, "ws": {d: ws[:, i].tolist() for i, d in enumerate(days)},
                "R": {d: R[:, i].tolist() for i, d in enumerate(days)}}


def control_exposure(lots: Sequence[Mapping[str, Any]], bars: Any, symbols: Sequence[str]) -> Any:
    """A CONTROL's per-symbol exposure ((S, n) over the bars' run sessions): its hash law's lots by weight and day only
    (no price: a control's lots are drawn, never filled), screen.series' rule a symbol: a lot entered at the open counts
    half its weight on its entry session, one at the close nothing; it counts its weight on each session held through;
    an exit at the open counts half, one at the close all of it. ValueError for a lot of another symbol or a day that
    is no session of the bars."""
    import numpy as np

    epoch = dt.date(1970, 1, 1)
    days = [(epoch + dt.timedelta(days=int(d))).isoformat() for d in bars.days[int(bars.first):]]
    where = {d: i for i, d in enumerate(days)}
    n = len(days)
    first, last = (days[0], days[-1]) if n else ("", "")
    rows = {str(s): i for i, s in enumerate(symbols)}
    out = np.zeros((len(symbols), n))

    def at(day: Any, what: str) -> int | None:
        d = str(day)[:10]
        if d in where:
            return where[d]
        if d < first:
            return -1
        if d > last:
            return None
        raise ValueError(f"a lot's {what} day {d} is not a session of the series")

    for lot in lots:
        sym = str(lot.get("symbol"))
        if sym not in rows:
            raise ValueError(f"lot {lot.get('lid')}: {sym} is outside the symbols")
        om = float(lot.get("weight") or 0.0)
        if not math.isfinite(om) or om <= 0:
            raise ValueError(f"lot {lot.get('lid')}: a weight that is not a positive number")
        e = at(lot.get("entry_day"), "entry")
        if e is None:
            continue
        x = None if lot.get("exit_day") in (None, "") else at(lot["exit_day"], "exit")
        if x is not None and x < 0:
            continue
        row = out[rows[sym]]
        if e >= 0 and (lot.get("entry_at") or "open") == "open":
            row[e] += om / 2.0
        h0 = max(e + 1, 0)
        h1 = n - 1 if x is None else min(x - 1, n - 1)
        if h1 >= h0:
            row[h0:h1 + 1] += om
        if x is not None and 0 <= x < n:
            row[x] += om / 2.0 if (lot.get("exit_at") or "open") == "open" else om
    return out


def _by_symbol(row: Mapping[str, Any], symbols: Sequence[str]) -> tuple[list[float], list[float]] | None:
    """A day reading's per-symbol exposure and returns in the member's Train symbol order (the forward run's symbols
    are the same set in its own order); None when the reading holds none or another set of symbols."""
    names = [str(s) for s in row.get("symbols") or []]
    ws, R = row.get("ws"), row.get("R")
    if ws is None or R is None or sorted(names) != sorted(str(s) for s in symbols) or len(ws) != len(names):
        return None
    at = {s: i for i, s in enumerate(names)}
    return [float(ws[at[s]]) for s in symbols], [float(R[at[s]]) for s in symbols]


def _returns(bars: Any, symbols: Sequence[str], *, nan: bool = False) -> Any:
    """Each symbol's cost-free close-to-close return over the bars' run sessions ((S, n); 0, or NaN with `nan`, where
    a close is missing: the House job's close-ratio rule)."""
    import numpy as np

    lo = int(bars.first)
    rows = []
    for sym in symbols:
        if sym not in bars.adj:
            rows.append(np.full(bars.n - lo, np.nan if nan else 0.0))
            continue
        c = np.asarray(bars.adj[sym], dtype=np.float64)[:, 3]
        prev = c[lo - 1:bars.n - 1] if lo >= 1 else np.concatenate([[np.nan], c[:bars.n - 1]])
        now = c[lo:bars.n]
        ok = np.isfinite(now) & np.isfinite(prev) & (prev > 0)
        with np.errstate(divide="ignore", invalid="ignore"):
            ret = np.where(ok, now / np.where(ok, prev, 1.0) - 1.0, np.nan if nan else 0.0)
        rows.append(ret)
    return np.vstack(rows) if rows else np.zeros((0, bars.n - lo))


# ---------------------------------------------------------------------------------------------------------- the night
class Wait(Exception):
    """A step that waits (the House's, or an input not there yet): nothing is written, it is asked again."""

    def __init__(self, cause: str, why: str):
        super().__init__(why)
        self.cause = cause
        self.why = why


def read_permit_file(root: str | Path) -> tuple[dict[str, Any] | None, bool]:
    """THE EXISTING PERMIT FILE: (its document when it exists and is the job's shape, whether it exists at all). A file
    that exists but cannot be read or is not the job's shape is (None, True): it is never overwritten."""
    path = Path(root) / PERMITS
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, False
    except (OSError, ValueError):
        return None, True
    if not isinstance(doc, Mapping) or doc.get("version") != PERMITS_VERSION or not isinstance(doc.get("routes"), Mapping) \
            or not isinstance(doc.get("holds"), list) or not isinstance(doc.get("units"), Mapping) \
            or not all(isinstance(k, str) and isinstance(v, Mapping) for k, v in doc["routes"].items()) \
            or not all(isinstance(x, str) for x in doc["holds"]):
        return None, True
    return dict(doc), True


class Night:
    """One night of the pool (the module docstring): `store` (the pool's own, writable), `fdb` (the forward record,
    read-only), `receipt` (`pool_rule.Receipt`), `cal` (the vendored calibration, `pool_rule.calib`), `runs`
    (`PoolRuns` or a test's fake), `families` (the equity families by id), `swarm` (the swarm store, read-only, for the
    cards; None: no card read), `budget` (child seconds tonight), `deadline`."""

    def __init__(self, root: str | Path, store: sqlite3.Connection, fdb: sqlite3.Connection, *, receipt: P.Receipt,
                 runs: Any, families: Mapping[str, Mapping[str, Any]], swarm: Any = None, settings: Any = None,
                 budget: float = 600.0, clock: Callable[[], float] = time.time, deadline: float = float("inf"),
                 base: str | Path | None = None, release: str | Path | None = None, cal: P.Calib | None = None):
        self.root = Path(root)
        self.store, self.fdb, self.receipt, self.runs = store, fdb, receipt, runs
        self.families, self.swarm, self.settings = families, swarm, settings
        self.budget, self.clock, self.deadline = float(budget), clock, float(deadline)
        self.base, self.release = base, release
        if cal is None:
            cal, why = P.calib()
            if cal is None:
                raise ValueError(f"the vendored calibration cannot be loaded: {why}")
        self.cal = cal
        self.spent = 0.0
        self.tally: Counter = Counter()
        self.notes: list[str] = []
        self.engine_now = forward_db.engine_now(fdb)
        self.night = record_night(fdb)
        self.registry = _registry(fdb)
        self._fwd1: dict[str, dict[str, Any]] | None = None
        self._fwd1_read = False
        self._members: dict[int, Any] = {}
        self._hc: dict[str, Any] | None = None
        self._by_pid = {f.pid: f for f in receipt.founders.values()}

    # ------------------------------------------------------------------------------------------------ helpers
    def fwd1(self) -> dict[str, dict[str, Any]] | None:
        if not self._fwd1_read:
            self._fwd1 = fwd1_facts(self.root, self.fdb)
            self._fwd1_read = True
        return self._fwd1

    def _over(self) -> bool:
        return self.spent >= self.budget or self.clock() >= self.deadline - MIN_RUN_S

    def _timed(self, call: Callable[[], Any]) -> Any:
        began = self.clock()
        try:
            return call()
        finally:
            self.spent += max(0.0, self.clock() - began)

    def _ev(self, kind: str, **kw: Any) -> bool:
        with self.store:
            return event(self.store, kind, at=self.clock(), **kw)

    def note(self, why: str) -> None:
        """A reason in words for the operator's report (never the permit file)."""
        if why not in self.notes:
            self.notes.append(why)

    def pin_row(self) -> dict[str, Any] | None:
        row = self.store.execute("SELECT * FROM pool_pins WHERE sha=?", (self.receipt.sha256,)).fetchone()
        return None if row is None else dict(row)

    def program(self, pid: int) -> Any:
        row = self.fdb.execute("SELECT key FROM fwd_registry WHERE pid=?", (int(pid),)).fetchone()
        return None if row is None else forward_db.program(self.fdb, str(row["key"]))

    def members_row(self, lineage: str) -> dict[str, Any] | None:
        row = self.store.execute("SELECT * FROM pool_members WHERE lineage=?", (lineage,)).fetchone()
        return None if row is None else dict(row)

    def routes(self) -> dict[str, dict[str, Any]]:
        return {str(r["lineage"]): dict(r) for r in self.store.execute("SELECT * FROM pool_routes")}

    def units(self) -> dict[str, dict[str, Any]]:
        return {str(r["cell"]): dict(r) for r in self.store.execute("SELECT * FROM pool_units")}

    def judged_units(self) -> dict[str, dict[str, Any]]:
        """The units whose looks run: clocked, or of a report-only cluster (its verdict to the operator's report), and
        neither refuted, ineligible nor nonconforming."""
        return {c: u for c, u in self.units().items()
                if (int(u["clocked"]) or int(u["report_only"])) and not int(u["refuted"]) and not int(u["ineligible"])
                and int(u["conforming"]) != 0}

    def verdict(self, cell: str) -> dict[str, Any] | None:
        row = self.store.execute("SELECT * FROM pool_verdicts WHERE cell=?", (cell,)).fetchone()
        return None if row is None else dict(row)

    def word(self, cell: str) -> str:
        """A unit's word: its final verdict's (a lost or demoted pass: DEMOTED; an ineligible end: ineligible), a
        nonconforming cluster's "nonconforming", else pending."""
        if self.store.execute("SELECT 1 FROM pool_demotions WHERE cell=?", (cell,)).fetchone() is not None:
            return "DEMOTED"
        v = self.verdict(cell)
        if v is not None:
            return P.INELIGIBLE if v["word"] == "INELIGIBLE" else str(v["word"])
        u = self.units().get(cell)
        if u is not None and int(u["conforming"]) == 0:
            return P.NONCONFORMING
        return P.PENDING

    def final(self, cell: str) -> bool:
        """Whether a unit's looks are over (a final word, an ineligible end, a nonconforming cluster): no lineage joins
        it."""
        return self.word(cell) in OVER

    def params(self, pid: int) -> dict[str, Any] | None:
        row = self.store.execute("SELECT * FROM pool_params WHERE pid=?", (int(pid),)).fetchone()
        return None if row is None else dict(row)

    def lineage_of_pid(self, pid: int) -> str | None:
        row = self.fdb.execute("SELECT lineage FROM fwd_registry WHERE pid=?", (int(pid),)).fetchone()
        return None if row is None else str(row["lineage"])

    # ------------------------------------------------------------------------------------------------ the stall rule
    def missed(self, cell: str, cause: str, why: str) -> bool:
        """One record night a cell's look waited (`waited`, once a cell, cause, engine and night); at `STALL_NIGHTS`
        such nights it is STALLED (`stalled`, once a cell, cause and engine; a House warning). Nothing marks it."""
        key = f"{cause}:{self.engine_now}"
        with self.store:
            event(self.store, "waited", at=self.clock(), cell=cell, once=f"{key}:{self.night}",
                  payload={"why": why, "cause": cause, "engine": self.engine_now, "night": self.night})
        nights = int(self.store.execute(
            "SELECT COUNT(*) FROM pool_events WHERE kind='waited' AND cell=? AND substr(once, 1, ?) = ?",
            (cell, len(key) + 1, key + ":")).fetchone()[0])
        self.tally["waited"] += 1
        if nights < STALL_NIGHTS:
            return False
        with self.store:
            if event(self.store, "stalled", at=self.clock(), cell=cell, once=key,
                     payload={"why": f"{why}: on {nights} record nights; it is asked again each night and nothing "
                                     "marks it", "cause": cause, "nights": nights}):
                self.tally["stalled"] += 1
        self.tally["stalled_now"] += 1
        return True

    # ------------------------------------------------------------------------------------- the House's Train data
    def prices(self) -> dict[str, Any]:
        """The Train eras' market (`pool_market`: the vendored House job's `prices()` record per era, written once);
        its sha beside the receipt's `market` ids (a difference is an event and a line of the report, not a refusal:
        the clock-start conformance binds). Raises `Wait`."""
        rows = {int(r["era"]): json.loads(r["record"]) for r in self.store.execute("SELECT era, record FROM pool_market")}
        if len(rows) == 2:
            return {"e0": rows[0], "e1": rows[1]}
        if self._over():
            raise Wait("budget", "the night's budget is spent: the market series wait")
        try:
            found = self._timed(lambda: self.runs.market(self.cal))
            recs = {e: found[f"e{e}"] for e in (0, 1)}
            texts = {e: P.canonical(recs[e]) for e in (0, 1)}
        except FS.Late:
            raise Wait("budget", "the deadline is too near for the market series") from None
        except Exception as exc:  # noqa: BLE001 - the House's
            self._ev("house", once=f"market:{self.night}", payload={"why": "the Train eras' market series could not "
                                                                            "be read", "error": type(exc).__name__})
            raise Wait("house", "the Train eras' market series could not be read") from None
        with self.store:
            for e in (0, 1):
                sha = hashlib.sha256(texts[e].encode()).hexdigest()
                self.store.execute("INSERT OR IGNORE INTO pool_market(era, record, sha, at) VALUES (?,?,?,?)",
                                   (e, texts[e], sha, self.clock()))
                want = (self.receipt.market.get(f"e{e}") or {}).get("sha256")
                if sha != want:
                    event(self.store, "market", at=self.clock(), once=f"e{e}",
                          payload={"why": "the House's Train-era market record is not the receipt's (a diagnostic: "
                                          "the clock-start conformance binds)", "era": e})
                    self.note(f"the House's Train-era market record of e{e} is not the receipt's (its sha differs; a "
                              "diagnostic: the clock-start conformance binds)")
        return {"e0": json.loads(texts[0]), "e1": json.loads(texts[1])}

    def hc(self) -> dict[str, Any]:
        """The House's Train calendar and regime cells at the receipt's cutpoints (vendored `house_context`)."""
        if self._hc is None:
            self._hc = P.house_context(self.cal, self.prices(), self.receipt)
        return self._hc

    def records(self, pid: int) -> dict[str, dict[str, Any]]:
        """A member's stored Train parts ({part: the House job's one_run record})."""
        return {str(r["part"]): json.loads(r["record"]) for r in self.store.execute(
            "SELECT part, record FROM pool_train WHERE pid=?", (int(pid),))}

    def meta(self, pid: int) -> dict[str, Any] | None:
        """A member's House meta row: a founder's from the receipt; a later lineage's from its registry row, its card,
        its frozen code's event scan and FWD1's row."""
        f = self._by_pid.get(int(pid))
        if f is not None:
            return P.founder_meta(f)
        reg = self.fdb.execute("SELECT * FROM fwd_registry WHERE pid=?", (int(pid),)).fetchone()
        if reg is None:
            return None
        reg = dict(reg)
        card = _card(self.swarm, reg.get("family"))
        program = self.program(pid)
        facts = (self.fwd1() or {}).get(str(reg["lineage"])) or {}
        return P.member_meta(lineage=str(reg["lineage"]), pid=int(pid), family=str(reg.get("family") or ""),
                             version=reg.get("version"), lane=str(reg.get("lane") or ""), ugroup=str(reg.get("ugroup") or ""),
                             first_day=str(reg.get("first_day") or ""),
                             declared_class=(card or {}).get("mechanism_class") or None,
                             program_sha=reg.get("program_sha"),
                             panel=str(reg.get("ugroup") or "").startswith(forward_db.PANEL_UGROUP),
                             inputs=[str(x) for x in ((card or {}).get("inputs") or [])],
                             event_word=P.reads_events(None if program is None else program.code),
                             infer_key_class=_infer(self.families.get(str(reg.get("family")))),
                             fwd1_type=facts.get("type"), fwd1_case=facts.get("case_"))

    def member(self, pid: int) -> Any:
        """A member's vendored `Member` on the House eras (`pool_rule.house_member` on its four stored parts), None while
        its parts are not all written or when it is out."""
        pid = int(pid)
        if pid in self._members:
            return self._members[pid]
        recs = self.records(pid)
        if any(part not in recs for part in P.PARTS):
            return None
        meta = self.meta(pid)
        if meta is None:
            return None
        _, mm = P.house_member(self.cal, meta, recs, self.hc())
        self._members[pid] = mm
        return mm

    def train_member(self, pid: int) -> None:
        """A member's Train parts, the missing ones in order inside the budget (`pool_train`, one row a part, written
        once), then its constants, group and status (`pool_params`). Raises `Wait` (budget, deadline, the House's); a
        run the House failed on `TRAIN_FAILS` nights is the program's own failure (out)."""
        pid = int(pid)
        if self.params(pid) is not None:
            return
        have = self.records(pid)
        for part in P.PARTS:
            if part in have:
                continue
            if self._over():
                raise Wait("budget", "the night's budget is spent: the Train series continue the next night")
            try:
                rec, k = self._timed(lambda part=part: self.runs.train_part(self.cal, pid, part))
            except FS.Late:
                raise Wait("budget", "the deadline is too near for a Train run") from None
            except Exception as exc:  # noqa: BLE001 - the House's: nothing written, asked again (twice: out)
                self.train_failed(pid, f"{type(exc).__name__}")
                raise Wait("house", "a member's Train run did not finish") from None
            text = _dumps(rec)
            with self.store:
                self.store.execute("INSERT OR IGNORE INTO pool_train(pid, part, record, sha, k, at) VALUES (?,?,?,?,?,?)",
                                   (pid, part, text, hashlib.sha256(text.encode()).hexdigest(),
                                    None if k is None else _dumps(k), self.clock()))
            have[part] = rec
        self.freeze(pid)

    def train_failed(self, pid: int, error: str) -> None:
        """One night the House could not finish a member's Train run; at `TRAIN_FAILS` such nights it is OUT, the
        program's own failure (the calibration's C5)."""
        with self.store:
            self.store.execute("INSERT OR IGNORE INTO pool_trainfail(pid, night, why, at) VALUES (?,?,?,?)",
                               (int(pid), str(self.night), error, self.clock()))
            event(self.store, "house", once=f"train:{pid}:{self.night}", at=self.clock(),
                  payload={"why": "a member's Train-era runs did not finish", "pid": pid, "error": error})
        self.tally["house"] += 1
        nights = int(self.store.execute("SELECT COUNT(*) FROM pool_trainfail WHERE pid=?", (int(pid),)).fetchone()[0])
        if nights >= TRAIN_FAILS:
            self.freeze(int(pid), out="its Train run failed twice on the House (counted as the program's own failure)")

    def freeze(self, pid: int, *, out: str | None = None) -> None:
        """A member's constants, group and status from its four parts (`pool_params`, written once): the vendored
        `member_from_runs` (`fit_constants` at the 2 bp floor haircut), K's Train counts from its k 1.0 runs."""
        at = self.clock()
        if out is None:
            meta = self.meta(pid)
            recs = self.records(pid)
            rec, mm = P.house_member(self.cal, meta or {"pid": pid, "lineage": "", "panel": True}, recs, self.hc())
            status = str(rec.get("status"))
        else:
            mm, status = None, f"out: {out}"
        ks = [json.loads(r["k"]) for r in self.store.execute("SELECT k FROM pool_train WHERE pid=? AND k IS NOT NULL",
                                                             (int(pid),))]
        with self.store:
            if mm is None:
                self.store.execute("INSERT OR IGNORE INTO pool_params(pid, status, why, at) VALUES (?,?,?,?)",
                                   (int(pid), "out", status[5:] if status.startswith("out: ") else status, at))
            else:
                self.store.execute(
                    "INSERT OR IGNORE INTO pool_params(pid, status, symbols, mu, wbar, sigma, abar, abar_v, grp, why, "
                    "k_close, k_sessions, at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (int(pid), "member", _dumps(list(mm.syms)), _dumps([float(x) for x in mm.mu]),
                     _dumps([float(x) for x in mm.wbar]), float(mm.sigma), float(mm.abar),
                     _dumps([float(x) for x in mm.abar_v]), str(mm.group), None,
                     sum(int(k.get("close_days") or 0) for k in ks), sum(int(k.get("sessions") or 0) for k in ks), at))
            event(self.store, "train", at=at, once=f"{pid}", payload={"pid": pid, "status": status[:120]})
        self._members.pop(int(pid), None)
        self.tally["train"] += 1

    def founder_pids(self) -> list[int]:
        """The founders the House owes Train series to, in order: the members of the clusters that could be clocked
        (not refuted, ineligible or report-only at the pin), then every other founding member, each by pid."""
        rec = self.receipt
        first = sorted({rec.founders[x].pid for cid, cl in rec.clusters.items()
                        if not (cl.refuted or cl.ineligible or cl.report_only) for x in cl.members})
        rest = sorted({f.pid for f in rec.founders.values() if f.member} - set(first))
        return first + rest

    def needing_train(self) -> list[int]:
        """The pids whose Train series the House owes: the founders (`founder_pids`), then the later lineages that are
        not decided (pid order)."""
        have = {int(r[0]) for r in self.store.execute("SELECT pid FROM pool_params")}
        first = [p for p in self.founder_pids() if p not in have]
        decided = {str(r[0]) for r in self.store.execute("SELECT lineage FROM pool_members")}
        later = []
        for lineage, rows in self._candidate_rows():
            if lineage in decided:
                continue
            pid = P.member_pid(rows)
            if pid is not None and pid not in have:
                later.append(pid)
        return first + sorted(set(later) - set(first))

    def train_step(self, *, founders_only: bool = False) -> bool:
        """THE HOUSE'S TRAIN SERIES (the module docstring, 3), inside the night's budget; whether every series owed
        (the founders' alone with `founders_only`) is written."""
        todo = [p for p in (self.founder_pids() if founders_only else self.needing_train())
                if self.params(p) is None]
        for pid in todo:
            if self._over():
                self.tally["deferred"] += 1
                return False
            try:
                self.train_member(pid)
            except Wait as w:
                if w.cause == "budget":
                    self.tally["deferred"] += 1
                    return False
        return all(self.params(p) is not None for p in todo)

    # ------------------------------------------------------------------------------------------------ the resamples
    @staticmethod
    def floor_key(look_key: str, judged: Mapping[tuple[str, str], Sequence[Any]], joins: Mapping[str, int] | None,
                  B: int, seed: int) -> str:
        """The key a floor's resamples are kept under: the look and a digest of everything they depend on (the
        members by cell, their joins, B and the boot seed), so a resample kept on one night is never read for another
        member set."""
        text = _dumps({"cells": {f"{k[0]}/{k[1]}": [m.name for m in ms] for k, ms in sorted(judged.items())},
                       "joins": dict(sorted((joins or {}).items())), "B": int(B), "seed": int(seed)})
        return f"{look_key}#{hashlib.sha256(text.encode()).hexdigest()[:16]}"

    def boot_hook(self, cid: str, look_key: str) -> P.BootHook:
        """`house_floor`'s resamples, so a floor can span nights: a variant kept in `pool_boot` is read back; a new one
        is computed while the budget lasts and held in memory; when the budget runs out every one computed tonight is
        written (one row a cluster, look, null, era and variant) and the floor waits (`Wait`). A floor that finishes in
        its night writes none (at B 2000 a cluster takes seconds, its resamples megabytes)."""
        import numpy as np

        pending: dict[tuple[str, int, str], Any] = {}

        def keep() -> None:
            with self.store:
                for (null, e, key), arr in pending.items():
                    self.store.execute("INSERT OR IGNORE INTO pool_boot(cluster, look, null_, era, key, shape, blob, at) "
                                       "VALUES (?,?,?,?,?,?,?,?)",
                                       (cid, look_key, null, int(e), key, ",".join(str(x) for x in arr.shape),
                                        zlib.compress(arr.tobytes(), 6), self.clock()))
            pending.clear()

        def hook(null: str, e: int, key: str, compute: Callable[[], Any]) -> Any:
            row = self.store.execute("SELECT shape, blob FROM pool_boot WHERE cluster=? AND look=? AND null_=? AND era=? "
                                     "AND key=?", (cid, look_key, null, int(e), key)).fetchone()
            if row is not None:
                shape = tuple(int(x) for x in str(row["shape"]).split(","))
                return np.frombuffer(zlib.decompress(row["blob"]), dtype=np.int16).reshape(shape).copy()
            if (null, int(e), key) in pending:
                return pending[(null, int(e), key)]
            if self._over():
                keep()
                raise Wait("budget", "the floor's resamples continue the next night")
            arr = np.asarray(self._timed(compute), dtype=np.int16)
            pending[(null, int(e), key)] = arr
            return arr

        return hook

    # --------------------------------------------------------------------------- 1. the clock and the conformance
    def sighting(self, now: float) -> dict[str, Any]:
        """THE FIRST SIGHTING of this receipt (`pool_sighting`, written once): the release's start from the deploys
        record, else this night's own time (`evidence` "sighting"); read back on every later night."""
        row = self.store.execute("SELECT * FROM pool_sighting WHERE sha=?", (self.receipt.sha256,)).fetchone()
        if row is not None:
            return dict(row)
        name = Path(self.release).name if self.release is not None else ""
        started = None
        if self.base is not None and name:
            try:
                from . import funnel

                started = funnel.release_start(self.base, name)
            except Exception:  # noqa: BLE001 - no record: the sighting's time
                started = None
        if started is not None and started > now:
            started = None
        evidence = "deploys" if started is not None else "sighting"
        start = float(now if started is None else started)
        with self.store:
            self.store.execute("INSERT OR IGNORE INTO pool_sighting(sha, release, release_start, evidence, at) "
                               "VALUES (?,?,?,?,?)", (self.receipt.sha256, name, start, evidence, self.clock()))
            event(self.store, "sighting", at=self.clock(), once=self.receipt.sha256,
                  payload={"release": name, "evidence": evidence})
        return dict(self.store.execute("SELECT * FROM pool_sighting WHERE sha=?", (self.receipt.sha256,)).fetchone())

    def clock_waited(self, why: str, cause: str = "clock") -> None:
        """A record night the clock waited (`clock_wait`, once a night); from `CLOCK_ALARM_NIGHTS` such nights on an
        alarm each night (`clock_alarm`)."""
        sha = self.receipt.sha256
        with self.store:
            event(self.store, "clock_wait", at=self.clock(), once=f"{sha}:{self.night}",
                  payload={"why": why, "cause": cause, "night": self.night})
        self.tally["clock_wait"] += 1
        self.note(f"the clock waits: {why}")
        nights = int(self.store.execute("SELECT COUNT(*) FROM pool_events WHERE kind='clock_wait' AND substr(once, 1, ?) "
                                        "= ?", (len(sha) + 1, sha + ":")).fetchone()[0])
        if nights >= CLOCK_ALARM_NIGHTS:
            with self.store:
                event(self.store, "clock_alarm", at=self.clock(), once=f"{sha}:{self.night}",
                      payload={"why": why, "nights": nights})
            self.tally["clock_alarm"] += 1

    def clock_check(self) -> dict[str, dict[str, Any]]:
        """THE CLOCK-START CONFORMANCE (the contract's 6.4), before the route list: for each founding cluster that
        could be clocked, its floors recomputed with the vendored floor pipeline on the House's own Train series (the
        receipt's members, joins 0, its boot seed, the pin's caps, the receipt's B) must equal every value of the
        receipt's `c_own_at_pin` (each null's floor, c_own, the minimum and the bar, both floor definitions); else it
        is NONCONFORMING. The founders' Train sha and the market sha are diagnostics beside. {cluster: {"conforming",
        "why", ...}} (kept once a cluster in `pool_clockcheck`). Raises `Wait` while it cannot finish tonight."""
        rec = self.receipt
        out: dict[str, dict[str, Any]] = {}
        for cid, cl in sorted(rec.clusters.items()):
            held = self.store.execute("SELECT conforming, row FROM pool_clockcheck WHERE cluster=?", (cid,)).fetchone()
            if held is not None:
                out[cid] = {"conforming": bool(held["conforming"]), **json.loads(held["row"])}
                continue
            if cl.refuted or cl.ineligible or cl.report_only:
                out[cid] = {"conforming": None, "why": "not a candidate"}
                continue
            judged: dict[tuple[str, str], list[Any]] = {}
            why = None
            diag = []
            for cell in cl.cells:
                ms = []
                for lin in rec.units[cell].members:
                    f = rec.founders[lin]
                    self.train_member(f.pid)
                    prm = self.params(f.pid)
                    mm = self.member(f.pid) if prm is not None and prm["status"] == "member" else None
                    if mm is None:
                        why = f"founder {lin} is out on this House's own Train series"
                        break
                    ms.append(mm)
                    mine = {part: record_sha(r) for part, r in self.records(f.pid).items()}
                    if f.train_sha256 is not None and mine != dict(f.train_sha256):
                        diag.append(lin)
                if why:
                    break
                judged[P.cell_key(cell)] = ms
            if why is None:
                caps_ = P.caps(*cl.U[P.U_PIN_COUNT], cl.dropped)
                look = self.floor_key("clock", judged, None, rec.B, cl.boot_seed)
                fl = P.house_floor(self.cal, cid=cid, keys=[P.cell_key(c) for c in cl.cells], judged=judged, hc=self.hc(),
                                   B=rec.B, boot_seed=cl.boot_seed, caps_=caps_, boot=self.boot_hook(cid, look))
                minimum = P.minimum_of(rec, {c: rec.units[c].m for c in cl.cells})
                mine_floors = P.pin_floors(fl, rec, minimum)
                want = {fd: {k: cl.c_own_at_pin[fd].get(k) for k in P.PIN_FLOOR_KEYS} for fd in P.FLOORS}
                conforming = mine_floors == want
                row = {"why": None if conforming else "its floors at the clock are not the receipt's at the pin",
                       "floors": mine_floors, "train_sha_differs": sorted(diag)}
            else:
                conforming = False
                row = {"why": why, "floors": None, "train_sha_differs": sorted(diag)}
            with self.store:
                self.store.execute("INSERT OR IGNORE INTO pool_clockcheck(cluster, conforming, row, at) VALUES (?,?,?,?)",
                                   (cid, int(conforming), _dumps(row), self.clock()))
                event(self.store, "conformance" if conforming else "nonconforming", at=self.clock(), cell=None,
                      once=f"clock:{cid}", payload={"cluster": cid, "conforming": conforming, "why": row["why"]})
            if diag:
                self.note(f"cluster {cid}: the House's Train records of {len(diag)} founders are not the receipt's "
                          "(their shas differ; a diagnostic beside the floors)")
            if not conforming:
                self.tally["nonconforming"] += 1
                self.note(f"cluster {cid} is NONCONFORMING at the clock ({row['why']}): not clocked, its members stay "
                          "on their per-program routes; only a captain amendment can clock it")
            out[cid] = {"conforming": conforming, **row}
        return out

    def cluster_states(self, facts: Mapping[str, Mapping[str, Any]], checks: Mapping[str, Mapping[str, Any]]
                       ) -> dict[str, dict[str, Any]]:
        """Each founding cluster at the clock: its U_u at the FWD1-R checkpoint count its members read before it (P1
        D7: the largest among its members FWD1 judges as case N or that hold an FWD1-R pass; above the table: report-only),
        its caps (`pool_rule.caps`, dropped tickets included), report-only (the receipt's or the count's), refuted,
        ineligible, conforming and CLOCKED (none of those, and conforming)."""
        rec = self.receipt
        out = {}
        for cid, cl in sorted(rec.clusters.items()):
            count = P.u_count(facts.get(x) for x in cl.members)
            u = rec.u_at(cid, count)
            caps_ = P.caps(None, None) if u is None else P.caps(u[0], u[1], cl.dropped)
            report_only = bool(cl.report_only or caps_.report_only)
            if report_only and not caps_.report_only:
                caps_ = P.caps(None, None)
            chk = checks.get(cid) or {}
            conforming = chk.get("conforming")
            clocked = not (cl.refuted or cl.ineligible or report_only) and conforming is True
            out[cid] = {"count": count, "u": (1.0, 1.0) if u is None else (float(u[0]), float(u[1])), "caps": caps_,
                        "report_only": report_only, "refuted": cl.refuted, "ineligible": cl.ineligible,
                        "conforming": conforming, "clocked": clocked}
        return out

    def founder_route(self, lineage: str, row: Mapping[str, Any] | None, state: Mapping[str, Any] | None,
                      unit_final: bool = False) -> tuple[str | None, str | None]:
        """A founder's route (PREREG 7.2): (route, why), or (None, None) while FWD1 has no row for a founder of a
        clocked unit (a WAIT: decided once it has one)."""
        f = self.receipt.founders[lineage]
        if f.merged_into:
            return "merged", f"merged into {f.merged_into} (the receipt's copy merge)"
        if not f.member:
            return "out", f.why
        unit = self.receipt.units.get(f.cell or "")
        if unit is None:
            return "per_program", "its cell is below M_MIN at the pin: it stays on its per-program route"
        st = state or {}
        if not st.get("clocked"):
            why = ("its unit was refuted by stage 1" if st.get("refuted") else
                   "its cluster has no bar on the grid (ineligible)" if st.get("ineligible") else
                   "its cluster is report-only" if st.get("report_only") else
                   "its cluster is nonconforming at the clock")
            return "per_program", f"{why}: it stays on its per-program route"
        if not isinstance(row, Mapping):
            return None, None
        if unit_final:
            return "final_unit", "FWD1 sighted it after its unit's verdict was final: it stays on its per-program route"
        if P.on_pool_route(row, unit_judged=True, refuted=False, report_only=False):
            return "pool", None
        if int(row.get("judged") or 0) == 1 and str(row.get("status")) != "void":
            return "fwd1", "an FWD1-R pass before the clock: a member, its FWD1-R ticket in U_u"
        return "sealed", "FWD1 does not judge it (a sealed pre-check, or a voided lineage): a member, evidence only"

    def clock_row(self, now: float) -> dict[str, Any] | None:
        """THE CLOCK AND THE ROUTE LIST (the module docstring, 1): the pin's row, written once with the founding units,
        the founders' membership, the REFUTED and INELIGIBLE verdicts and the POOL-route list in one transaction, on the
        job's first new record night after the receipt's first sighting once the clock-start conformance is done;
        None while there is none (the night, FWD1's store, the House's series or the conformance waits), or when the
        store was lost (an existing permit file already names this receipt's clock)."""
        held = self.pin_row()
        if held is not None:
            return held
        sight = self.sighting(now)
        existing, exists = read_permit_file(self.root)
        if existing is not None and existing.get("receipt") == self.receipt.sha256 and existing.get("clock"):
            with self.store:
                event(self.store, "store_lost", at=self.clock(), once=f"{self.night}",
                      payload={"why": "the permit file already names this receipt's clock but the store holds none: "
                                      "the store was lost or reset; no clock, no judging, the file's lists are carried "
                                      "whole"})
            self.tally["store_lost"] += 1
            self.note("STORE LOST: the permit file names this receipt's clock but pool-screen.sqlite holds none; nothing "
                      "is judged and no clock starts (a captain's step)")
            return None
        night, before = first_night(self.fdb, float(sight["release_start"]))
        if night is None:
            self.clock_waited("no record night written since the receipt was first sighted")
            return None
        facts = self.fwd1()
        if facts is None:
            self._ev("house", once=f"clock:{night}", payload={"why": "FWD1's store could not be read on the first "
                                                                     "night: the route list waits a night"})
            self.tally["house"] += 1
            self.clock_waited("FWD1's store could not be read", cause="house")
            return None
        try:
            self.hc()
            if not self.train_step(founders_only=True):
                raise Wait("train", "the founders' Train series are not all written yet")
            checks = self.clock_check()
        except Wait as w:
            self.clock_waited(f"the clock-start conformance is not done ({w.why})", cause=w.cause)
            return None
        from ..equity import schedule

        clock = schedule.next_session(dt.date.fromisoformat(night)).isoformat()
        rec = self.receipt
        at = self.clock()
        states = self.cluster_states(facts, checks)
        routes: dict[str, tuple[str, str, str]] = {}
        member_rows = []
        for lineage, f in sorted(rec.founders.items()):
            unit = rec.units.get(f.cell or "")
            state = states.get(unit.cluster) if unit is not None else None
            route, why = self.founder_route(lineage, facts.get(lineage), state)
            if route is None:
                continue                                  # FWD1 has no row yet: decided once it has one
            judged = unit is not None and state is not None and (state["clocked"] or state["report_only"]) \
                and not state["refuted"] and not state["ineligible"]
            if route == "pool":
                routes[lineage] = (unit.cell, unit.cluster, "a founder FWD1 judges as case N, with no FWD1-R pass")
            member_rows.append((lineage, f.pid, f.cell if judged else None, route, clock if judged else None, f.cls, 0,
                                f.merged_into, f.infer_key_class, why, None, at))
        for lineage, f in sorted(rec.founders.items()):
            if f.merged_into and f.merged_into in routes:             # a merged copy follows its member's route
                cell, cid, _ = routes[f.merged_into]
                routes[lineage] = (cell, cid, f"merged into {f.merged_into}, which is on the POOL route")
        with self.store:
            self.store.execute("INSERT OR IGNORE INTO pool_pins(sha, release, release_start, before, night, clock, "
                               "evidence, at) VALUES (?,?,?,?,?,?,?,?)",
                               (rec.sha256, str(sight["release"]), float(sight["release_start"]), before, night, clock,
                                str(sight["evidence"]), at))
            for cell, unit in sorted(rec.units.items()):
                st = states[unit.cluster]
                caps_ = st["caps"]
                conforming = -1 if st["conforming"] is None else int(bool(st["conforming"]))
                self.store.execute(
                    "INSERT OR IGNORE INTO pool_units(cell, cls, grp, cluster, founders, clock, origin, refuted, stage1, "
                    "u_point, u_bound, cap, wall, report_only, report_why, ineligible, conforming, clocked, fwd1_count, "
                    "at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (cell, unit.cls, unit.group, unit.cluster, _dumps(list(unit.members)), clock, "receipt",
                     int(st["refuted"]), _dumps(dict(rec.clusters[unit.cluster].stage1)), st["u"][0], st["u"][1],
                     float(caps_.cap), float(caps_.wall), int(st["report_only"]), caps_.why, int(st["ineligible"]),
                     conforming, int(st["clocked"]), int(st["count"]), at))
                if st["refuted"]:
                    self.store.execute("INSERT OR IGNORE INTO pool_verdicts(cell, word, why, at) VALUES (?,?,?,?)",
                                       (cell, "REFUTED", "stage 1 refuted the cluster on its seen-span Train runs", at))
                elif st["ineligible"]:
                    self.store.execute("INSERT OR IGNORE INTO pool_verdicts(cell, word, why, at) VALUES (?,?,?,?)",
                                       (cell, "INELIGIBLE", "the receipt's cluster has no bar on the grid at the pin", at))
            for row in member_rows:
                self.store.execute("INSERT OR IGNORE INTO pool_members(lineage, pid, cell, route, joins, declared, "
                                   "assigned, merged_into, infer_key, why, corr, at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                                   row)
            for lineage, (cell, cid, why) in sorted(routes.items()):
                self.store.execute("INSERT OR IGNORE INTO pool_routes(lineage, cell, cluster, night, why, at) "
                                   "VALUES (?,?,?,?,?,?)", (lineage, cell, cid, night, why, at))
            event(self.store, "pinned", at=at, once=rec.sha256,
                  payload={"why": "the pooled screen's first night under the release that carries its receipt: the "
                                  "units, the founders and the POOL-route list are written; the clock starts at the "
                                  "next session", "night": night, "clock": clock, "routes": len(routes),
                           "units": len(rec.units),
                           "clocked": sorted(cid for cid, st in states.items() if st["clocked"])})
        self.tally["routes_written"] += len(routes)
        return self.pin_row()

    # ---------------------------------------------------------------------------------------- 2. later lineages
    def _candidate_rows(self) -> list[tuple[str, list[dict[str, Any]]]]:
        founders = set(self.receipt.founders)
        return [(lin, rows) for lin, rows in sorted(self.registry.items()) if lin not in founders]

    def sight(self, pin: Mapping[str, Any]) -> None:
        """THE LATER LINEAGES' first reading (the module docstring, 2): out by type, symbols, class or event reading;
        HELD while FWD1 judges it as case N and the House has not decided it."""
        facts = self.fwd1() or {}
        decided = {str(r[0]) for r in self.store.execute("SELECT lineage FROM pool_members")}
        held = {str(r[0]) for r in self.store.execute("SELECT lineage FROM pool_holds")}
        for lineage, rows in self._candidate_rows():
            if lineage in decided:
                continue
            pid = P.member_pid(rows)
            if pid is None:
                continue                                  # Train-fail only: not a member (a later pass is read then)
            row = next(r for r in rows if int(r["pid"]) == pid)
            fam = self.families.get(str(row["family"]))
            program = self.program(pid)
            symbols = list((row.get("needs") or {}).get("symbols") or [])
            why = P.excluded(panel=str(row.get("ugroup") or "").startswith(forward_db.PANEL_UGROUP), symbols=symbols,
                             card=_card(self.swarm, row["family"]),
                             code=None if program is None else program.code)
            if why is not None:
                self._member(lineage, pid, cell=None, route="out", why=why, fam=fam, row=row)
                self._release(lineage, why)
                continue
            if lineage not in held and fwd1_case_n(facts.get(lineage)):
                with self.store:
                    self.store.execute("INSERT OR IGNORE INTO pool_holds(lineage, night, why, at) VALUES (?,?,?,?)",
                                       (lineage, str(self.night), "a later lineage FWD1 judges as case N: held off "
                                                                  "FWD1-R seats and sealed tries until the House "
                                                                  "decides it", self.clock()))
                    event(self.store, "held", at=self.clock(), lineage=lineage, once="held", payload={"pid": pid})
                held.add(lineage)
                self.tally["held"] += 1

    def _member(self, lineage: str, pid: int | None, *, cell: str | None, route: str, why: str | None,
                fam: Mapping[str, Any] | None, row: Mapping[str, Any] | None, assigned: bool = False,
                merged: str | None = None, joins: str | None = None, corr: Mapping[str, Any] | None = None,
                declared: str | None = None) -> None:
        card = _card(self.swarm, (row or {}).get("family")) if row is not None else None
        with self.store:
            self.store.execute("INSERT OR IGNORE INTO pool_members(lineage, pid, cell, route, joins, declared, assigned, "
                               "merged_into, infer_key, why, corr, at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                               (lineage, pid, cell, route, joins, declared or (card or {}).get("mechanism_class"),
                                int(assigned),
                                merged, _infer(fam), why, None if corr is None else _dumps(corr), self.clock()))
            event(self.store, "decided", at=self.clock(), lineage=lineage, once="decided",
                  payload={"route": route, "cell": cell, "why": why})
        self.tally[f"decided_{route}"] += 1

    def _release(self, lineage: str, why: str) -> None:
        if self.store.execute("SELECT 1 FROM pool_holds WHERE lineage=?", (lineage,)).fetchone() is None:
            return
        with self.store:
            self.store.execute("INSERT OR IGNORE INTO pool_releases(lineage, why, at) VALUES (?,?,?)",
                               (lineage, why, self.clock()))
            event(self.store, "released", at=self.clock(), lineage=lineage, once="released", payload={"why": why})
        self.tally["released"] += 1

    def _route(self, lineage: str, cell: str, cluster: str, why: str) -> None:
        with self.store:
            self.store.execute("INSERT OR IGNORE INTO pool_routes(lineage, cell, cluster, night, why, at) "
                               "VALUES (?,?,?,?,?,?)", (lineage, cell, cluster, str(self.night), why, self.clock()))
            event(self.store, "routed", at=self.clock(), lineage=lineage, once="routed", payload={"cell": cell})
        self.tally["routed"] += 1

    def train_z(self, pid: int) -> Any:
        """A member's raw Train z on the House calendar (vendored `z_on_calendar`), or None without its Train series."""
        mm = self.member(pid)
        return None if mm is None else P.train_z(self.cal, mm, self.hc())

    def founders_z(self, cell: str) -> list[Any] | None:
        """A unit's founders' Train z (their nanmean is the cell's Train D an assignment correlates with: the contract's
        3.5), or None while a founder lacks its Train series."""
        unit = self.receipt.units.get(cell)
        if unit is None:
            return None
        zs = []
        for lineage in unit.members:
            z = self.train_z(self.receipt.founders[lineage].pid)
            if z is None:
                return None
            zs.append(z)
        return zs or None

    def decide_founders(self) -> None:
        """A founder of a clocked unit FWD1 had no row for at the clock, decided once it has one (a missing row is a
        wait, never a route): on the POOL route when its unit is still pending and FWD1 judges it as case N."""
        facts = self.fwd1() or {}
        decided = {str(r[0]) for r in self.store.execute("SELECT lineage FROM pool_members")}
        units = self.units()
        for lineage, f in sorted(self.receipt.founders.items()):
            if lineage in decided or not f.member or f.cell not in units:
                continue
            u = units[f.cell]
            state = {"clocked": bool(int(u["clocked"])), "refuted": bool(int(u["refuted"])),
                     "ineligible": bool(int(u["ineligible"])), "report_only": bool(int(u["report_only"]))}
            route, why = self.founder_route(lineage, facts.get(lineage), state, unit_final=self.final(f.cell))
            if route is None:
                continue
            self._member(lineage, f.pid, cell=f.cell, route=route, why=why, fam=self.families.get(f.family), row=None,
                         joins=str(u["clock"]), declared=f.cls)
            if route == "pool":
                self._route(lineage, f.cell, str(u["cluster"]), "a founder FWD1 sighted after the clock as case N")
                for other, g in sorted(self.receipt.founders.items()):
                    if g.merged_into == lineage:
                        self._route(other, f.cell, str(u["cluster"]), f"merged into {lineage}, which is on the POOL route")

    def _earlier_ready(self, pid: int) -> bool:
        """THE COPY MERGE WAITS (the P1 review's F13): every earlier member (by pid) is settled first: a founding member
        has its Train series written, and a later lineage with a passing version is decided (it has its Train series,
        or is out), so a copy is never assigned or routed past an earlier member it could merge into. `decide` reads the
        later lineages in pid order, so a night settles an earlier one before a later one."""
        for f in self.receipt.founders.values():
            if f.member and f.pid < pid and self.params(f.pid) is None:
                return False
        decided = {str(r[0]) for r in self.store.execute("SELECT lineage FROM pool_members")}
        for lineage, rows in self._candidate_rows():
            other = P.member_pid(rows)
            if other is None or other >= pid:
                continue
            if lineage not in decided:
                return False
        return True

    def _earlier_members(self, pid: int) -> list[Any]:
        """Every earlier kept member by pid (the founding members and the decided later lineages that are neither out
        nor merged), as vendored `Member`s."""
        out = []
        for f in sorted(self.receipt.founders.values(), key=lambda x: x.pid):
            if f.member and f.pid < pid:
                mm = self.member(f.pid)
                if mm is not None:
                    out.append(mm)
        for r in self.store.execute("SELECT pid FROM pool_members WHERE route NOT IN ('out', 'merged') AND pid IS NOT NULL "
                                    "AND pid < ? ORDER BY pid", (int(pid),)):
            if int(r["pid"]) in self._by_pid:
                continue
            mm = self.member(int(r["pid"]))
            if mm is not None:
                out.append(mm)
        return sorted(out, key=lambda m: int(m.meta.get("pid") or 0))

    def decide(self) -> None:
        """THE LATER LINEAGES' House decision (the module docstring, 2), once FWD1 has its row, its own Train series
        and every earlier member's exist."""
        facts = self.fwd1() or {}
        units = self.units()
        decided = {str(r[0]) for r in self.store.execute("SELECT lineage FROM pool_members")}
        order = sorted(((P.member_pid(rows), lineage, rows) for lineage, rows in self._candidate_rows()
                        if P.member_pid(rows) is not None), key=lambda x: (x[0], x[1]))
        for pid, lineage, rows in order:
            if lineage in decided:
                continue
            fwd1 = facts.get(lineage)
            if not isinstance(fwd1, Mapping):
                continue                                  # FWD1 has not sighted it: a wait, never a route (the P1 review's F5)
            prm = self.params(pid)
            if prm is None:
                continue                                  # its Train series first (`train_step`)
            row = next(r for r in rows if int(r["pid"]) == pid)
            fam = self.families.get(str(row["family"]))
            if prm["status"] != "member":
                why = str(prm.get("why") or "no Train-era series")
                self._member(lineage, pid, cell=None, route="out", why=why, fam=fam, row=row)
                self._release(lineage, why)
                continue
            if not self._earlier_ready(pid):
                continue                                  # every earlier lineage settled first (the P1 review's F13)
            mm = self.member(pid)
            if mm is None:
                continue
            into = P.merge_copy(self.cal, mm, self._earlier_members(pid), self.hc())
            if into is not None:
                target = self.lineage_of_pid(int(str(into)[1:])) or str(into)
                routes = self.routes()
                self._member(lineage, pid, cell=None, route="merged", why=f"merged into {target}", fam=fam, row=row,
                             merged=target)
                if target in routes:
                    self._route(lineage, str(routes[target]["cell"]), str(routes[target]["cluster"]),
                                f"merged into {target}, which is on the POOL route")
                else:
                    self._release(lineage, f"merged into {target}, which is not on the POOL route")
                continue
            grp = str(prm["grp"])
            cells: dict[str, Any] | None = {}
            for cell, unit in units.items():
                if unit["grp"] != grp:
                    continue
                zs = self.founders_z(cell)
                if zs is None:
                    cells = None
                    break
                cells[cell] = zs                                                    # type: ignore[index]
            if cells is None:
                continue                                  # its group's founders' Train series first
            target, corrs = P.assign(self.cal, self.train_z(pid), cells, self.receipt.rho_assign)
            corr = {c: (None if not math.isfinite(v) else round(v, 6)) for c, v in corrs.items()}
            if target is None:
                self._member(lineage, pid, cell=None, route="new_cell", fam=fam, row=row, corr=corr,
                             why="under rho_assign with every cell of its group (or no rho_assign): it counts toward a "
                                 "new cell under its declared class (not clocked in P1: it stays on its per-program "
                                 "route)")
                self._release(lineage, "counts toward a new cell (not clocked in P1)")
                continue
            unit = units[target]
            if self.final(target) or not (int(unit["clocked"]) or int(unit["report_only"])):
                self._member(lineage, pid, cell=None, route="final_unit", fam=fam, row=row, corr=corr,
                             why=f"assigned to {target}, whose verdict is final or which is not clocked: not a member, "
                                 "it stays on its per-program route")
                self._release(lineage, f"assigned to {target}, whose verdict is final or which is not clocked")
                continue
            spend = int(fwd1.get("k_read") or 0) > 0 and (
                fwd1.get("first_check_at") is None or self._held_at(lineage) is None
                or float(fwd1["first_check_at"]) < float(self._held_at(lineage)))
            if int(unit["report_only"]):
                self._member(lineage, pid, cell=target, route="fwd1", fam=fam, row=row, assigned=True, corr=corr,
                             joins=str(unit["clock"]), why="assigned to a report-only cluster's cell: a member, on FWD1-R")
                self._release(lineage, "a member of a report-only cluster: on FWD1-R")
            elif fwd1_case_n(fwd1) and spend:
                self._member(lineage, pid, cell=None, route="fwd1", fam=fam, row=row, corr=corr,
                             why="FWD1-R checkpoints read before its hold: its U_u recompute needs the calibration's "
                                 "pinned code (not in P1), so it is released to FWD1-R and is not a member")
                self._release(lineage, "FWD1-R spend before its hold (P1's stated limit)")
            elif fwd1_case_n(fwd1):
                # ASSIGNED INTO A PENDING UNIT: on the POOL route from its first counted day there (section 7.2),
                # whatever FWD1 read while it was held (a pass then could never seat it)
                self._member(lineage, pid, cell=target, route="pool", fam=fam, row=row, assigned=True, corr=corr,
                             joins=str(unit["clock"]), why=None)
                self._route(lineage, target, str(unit["cluster"]), "a later lineage assigned to a pending unit")
            elif int(fwd1.get("judged") or 0) == 0 or str(fwd1.get("status")) == "void":
                self._member(lineage, pid, cell=target, route="sealed", fam=fam, row=row, assigned=True, corr=corr,
                             joins=str(unit["clock"]),
                             why="assigned to a pending unit; FWD1 does not judge it (a sealed pre-check): a member, "
                                 "evidence only")
                self._release(lineage, "a member that FWD1 does not judge: its sealed path, evidence only")
            else:
                self._member(lineage, pid, cell=None, route="fwd1", fam=fam, row=row, corr=corr,
                             why="FWD1 judges it outside case N: not a member, it stays on FWD1-R")
                self._release(lineage, "FWD1 judges it outside case N")

    def _held_at(self, lineage: str) -> float | None:
        row = self.store.execute("SELECT at FROM pool_holds WHERE lineage=?", (lineage,)).fetchone()
        return None if row is None else float(row[0])

    def sigma_tilde(self, cell: str) -> float | None:
        """A cell's frozen sigma_tilde (its receipt founders'), written once every founder has its sigma."""
        row = self.store.execute("SELECT sigma_tilde FROM pool_sigma WHERE cell=?", (cell,)).fetchone()
        if row is not None:
            return float(row[0])
        unit = self.receipt.units.get(cell)
        if unit is None:
            return None
        sigmas = []
        for lineage in unit.members:
            prm = self.params(self.receipt.founders[lineage].pid)
            if prm is None or prm.get("sigma") is None:
                return None
            sigmas.append(float(prm["sigma"]))
        tilde = float(self.cal.stat.sigma_tilde(sigmas))
        with self.store:
            self.store.execute("INSERT OR IGNORE INTO pool_sigma(cell, sigma_tilde, at) VALUES (?,?,?)",
                               (cell, tilde, self.clock()))
        return tilde

    def founders_sigma(self, cell: str) -> list[float]:
        """The cell's receipt founders' sigma (`cluster_cells`' founders_sigma: a joiner takes the founders')."""
        out = []
        for lineage in self.receipt.units[cell].members:
            prm = self.params(self.receipt.founders[lineage].pid)
            if prm is None or prm.get("sigma") is None:
                raise Wait("train", "a founder's Train series is not written yet")
            out.append(float(prm["sigma"]))
        return out
    # --------------------------------------------------------------------------------------- 4. the cell sessions
    def cell_members(self, cell: str) -> list[dict[str, Any]]:
        """A unit's members: its founders and the later lineages assigned to it (each {lineage, pid, joins})."""
        unit = self.units()[cell]
        out = [{"lineage": lin, "pid": self.receipt.founders[lin].pid, "joins": str(unit["clock"]), "founder": True}
               for lin in json.loads(unit["founders"])]
        for r in self.store.execute("SELECT lineage, pid, joins FROM pool_members WHERE cell=? AND assigned=1 ORDER BY "
                                    "pid", (cell,)):
            out.append({"lineage": str(r["lineage"]), "pid": int(r["pid"]), "joins": str(r["joins"]), "founder": False})
        return out

    def unit_engine(self, cell: str) -> int | None:
        """The engine id a cell's series is read under (one engine id a judged series): before its first look the
        record's newest; after it, its looks' id, or the id an engine move carried it to (`engine_switched`)."""
        row = self.store.execute("SELECT MAX(engine) FROM pool_checks WHERE cell=?", (cell,)).fetchone()
        if row is None or row[0] is None:
            return self.engine_now
        engine = int(row[0])
        for ev in self.store.execute("SELECT payload FROM pool_events WHERE kind='engine_switched' AND cell=?", (cell,)):
            to = json.loads(ev["payload"]).get("to")
            if isinstance(to, int) and to > engine:
                engine = to
        return engine

    def join_day(self, member: Mapping[str, Any], engine: int) -> str | None:
        """A member's first counted day at or after its cell's clock (it is active from it), None before it has one."""
        counted = counted_by_day(self.fdb, int(member["pid"]), engine)
        return min((d for d in counted if d >= str(member["joins"])), default=None)

    def _undecided_by(self, day: str) -> bool:
        """Whether a lineage registered by `day`'s close is still undecided (a look waits until each is assigned)."""
        from ..equity import schedule

        moments = schedule.moments(dt.date.fromisoformat(day))
        close = float(moments.close_at) if moments is not None else float("inf")
        decided = {str(r[0]) for r in self.store.execute("SELECT lineage FROM pool_members")}
        for lineage, rows in self._candidate_rows():
            if lineage in decided:
                continue
            pid = P.member_pid(rows)
            if pid is None:
                continue
            if min(float(r["created_at"]) for r in rows if int(r["pid"]) == pid) <= close:
                return True
        return False

    def classify(self, cell: str) -> None:
        """THE CELL SESSIONS (the module docstring, 4), from the clock, in order, first write stands."""
        from ..equity import schedule

        engine = self.unit_engine(cell)
        if engine is None or self.night is None:
            return
        unit = self.units()[cell]
        held = {str(r["day"]) for r in self.store.execute("SELECT day FROM pool_sessions WHERE cell=? AND engine=?",
                                                          (cell, engine))}
        members = self.cell_members(cell)
        counted = {m["pid"]: counted_by_day(self.fdb, m["pid"], engine) for m in members}
        stored = {m["pid"]: stored_days(self.fdb, m["pid"], engine) for m in members}
        joins = {m["pid"]: min((d for d in counted[m["pid"]] if d >= m["joins"]), default=None) for m in members}
        nights = sorted({str(r[0]) for r in self.fdb.execute("SELECT DISTINCT through FROM fwd_runs WHERE through IS NOT "
                                                             "NULL")})
        day = dt.date.fromisoformat(str(unit["clock"]))
        last = dt.date.fromisoformat(self.night)
        while day < last:                                 # settled: the record holds a later night
            iso = day.isoformat()
            if schedule.is_session(day) and iso not in held:
                active = [m for m in members if joins[m["pid"]] is not None and joins[m["pid"]] <= iso]
                waiting = [m for m in active if iso not in stored[m["pid"]] and forward_db.active(self.fdb, m["pid"])]
                later = sum(1 for n in nights if n > iso)
                if (waiting and later < STALL_NIGHTS) or self._undecided_by(iso):
                    return                                # this session and every later one wait
                n_counted = sum(1 for m in active if iso in counted[m["pid"]])
                with self.store:
                    self.store.execute("INSERT OR IGNORE INTO pool_sessions(cell, day, engine, counted, active, session, "
                                       "at) VALUES (?,?,?,?,?,?,?)",
                                       (cell, iso, engine, n_counted, len(active), int(n_counted >= P.M_MIN),
                                        self.clock()))
            day += dt.timedelta(days=1)

    def sessions(self, cell: str, engine: int) -> list[str]:
        return [str(r[0]) for r in self.store.execute(
            "SELECT day FROM pool_sessions WHERE cell=? AND engine=? AND session=1 ORDER BY day", (cell, engine))]

    # ------------------------------------------------------------------------------------------ 5. the looks
    def readings(self, member: Mapping[str, Any], engine: int, last: str) -> dict[str, dict[str, Any]] | None:
        """A member's day readings (`pool_fwd`, written once) for its counted days from its join through `last`: the
        record's row (the live-like re-price in place of r), the haircut, the sides and the House's per-symbol
        exposure and returns where its own forward run IS the record's day. Raises `Wait` on the House's failure."""
        pid = int(member["pid"])
        counted = counted_by_day(self.fdb, pid, engine)
        join = min((d for d in counted if d >= member["joins"]), default=None)
        if join is None:
            return {}
        days = [d for d in sorted(counted) if join <= d <= last]
        held = {str(r["day"]): json.loads(r["row"]) for r in self.store.execute(
            "SELECT day, row FROM pool_fwd WHERE pid=? AND engine=?", (pid, engine))}
        missing = [d for d in days if d not in held]
        if missing:
            if self._over():
                raise Wait("budget", "the night's budget is spent: the readings wait")
            program = self.program(pid)
            if program is None:
                raise Wait("registry", "the member's registry row cannot be read")
            try:
                run = self._timed(lambda: self.runs.forward_series(program, settings=self.settings, fdb=self.fdb))
            except FS.Late:
                raise Wait("budget", "the deadline is too near for a forward run") from None
            except Exception as exc:  # noqa: BLE001 - the House's
                self._ev("house", lineage=str(member["lineage"]), once=f"forward:{pid}:{self.night}",
                         payload={"why": "a member's forward run did not finish", "error": type(exc).__name__})
                self.tally["house"] += 1
                raise Wait("house", "a member's forward run did not finish") from None
            g_bp = F.haircut_bp("ETF", FS._lotgaps(self.fdb).get("ETF", []))
            ll = {str(r["day"]): float(r["r_ll"]) for r in self.fdb.execute(
                "SELECT day, r_ll FROM fwd_ll WHERE pid=? AND engine=?", (pid, engine))}
            fsides = {str(r["day"]): float(r["sides"]) for r in self._fwd1_sides(pid, engine)}
            with self.store:
                for d in missing:
                    rec = counted[d]
                    r = float(ll.get(d, rec["r"]))
                    r15 = float(rec["r15"]) + (r - float(rec["r"])) if rec.get("r15") is not None else None
                    ran = run.get("r") or {}
                    reproduced = d in ran and abs(float(ran[d]) - float(rec["r"])) <= forward_db.TOL
                    if not reproduced and d in ran:
                        # THE DAY WAS RESTATED (FWD1's reading of "the run is the record's day": the same orders, from
                        # inputs a vendor restatement moved): its exposure is the record's (DEVIATIONS.log D2)
                        hashes = run.get("bars") or {}
                        reproduced = (rec.get("bars") is not None and d in hashes and str(hashes[d]) != str(rec["bars"])
                                      and int((run.get("entries") or {}).get(d, -1)) == int(rec["entries"])
                                      and int((run.get("exits") or {}).get(d, -1)) == int(rec["exits"]))
                    row = {"r": r, "r15": r15, "w": float(rec["w"]), "b": float(rec["b"]), "ll": int(d in ll),
                           "g_bp": float(g_bp), "sides": float(fsides.get(d, (run.get("sides") or {}).get(d, 0.0))),
                           "rep": int(bool(reproduced) and r15 is not None),
                           "symbols": list(run.get("symbols") or []),
                           "ws": (run.get("ws") or {}).get(d) if reproduced else None,
                           "R": (run.get("R") or {}).get(d) if reproduced else None}
                    self.store.execute("INSERT OR IGNORE INTO pool_fwd(pid, day, engine, row, at) VALUES (?,?,?,?,?)",
                                       (pid, d, int(engine), _dumps(row), self.clock()))
                    held[d] = row
            self.tally["readings"] += len(missing)
        return {d: held[d] for d in days}

    def _fwd1_sides(self, pid: int, engine: int) -> list[Any]:
        """FWD1's `fwd1_sides` of the same pid and engine (reused where they exist), [] when there are none."""
        if not (self.root / FS.DB).exists():
            return []
        try:
            sdb = FS.open_store(self.root, readonly=True)
        except sqlite3.Error:
            return []
        try:
            return list(sdb.execute("SELECT day, sides FROM fwd1_sides WHERE pid=? AND engine=?", (int(pid), int(engine))))
        except sqlite3.Error:
            return []
        finally:
            sdb.close()

    def series(self, cell: str, engine: int, sessions: Sequence[str], *, members: Sequence[Mapping[str, Any]] | None = None
               ) -> dict[str, Any]:
        """THE CELL'S D and D15 over `sessions` (section 2): each active member's z on its counted days (0 on a
        session with no counted row, on a day its run does not reproduce, and throughout for a member over
        `UNREPRODUCED_MAX`), averaged over the members active each session (a member is active from its first
        counted day after the clock; a stopped member stays in at z = 0). Raises `Wait`. -> {"D", "D15", "active",
        "mar": [(|b|, zeroed, slots)] a session (a stopped member's days counted apart), "warned": [lineage]}."""
        import numpy as np

        tilde = self.sigma_tilde(cell)
        if tilde is None:
            raise Wait("train", "a founder's Train series is not written yet")
        members = list(members if members is not None else self.cell_members(cell))
        last = sessions[-1]
        per: list[tuple[dict[str, float], dict[str, float], dict[str, Any], str | None, str | None, set[str]]] = []
        warned = []
        for m in members:
            pid = int(m["pid"])
            prm = self.params(pid)
            if prm is None or prm.get("mu") is None or prm.get("sigma") is None:
                raise Wait("train", f"{m['lineage']}'s Train series is not written yet")
            reads = self.readings(m, engine, last) or {}
            stop_after = None if forward_db.active(self.fdb, pid) else (forward_db.last_stored_day(self.fdb, pid) or "")
            if not reads:
                per.append(({}, {}, {}, None, stop_after, set()))
                continue
            days = sorted(reads)
            symbols = [str(s) for s in json.loads(prm["symbols"])]
            mu = np.array(json.loads(prm["mu"]), dtype=np.float64)
            wbar = np.array(json.loads(prm["wbar"]), dtype=np.float64)
            ws = np.zeros((len(symbols), len(days)))
            R = np.zeros((len(symbols), len(days)))
            rep = np.zeros(len(days), dtype=bool)
            rg = np.zeros(len(days))
            gap = np.zeros(len(days))
            for i, d in enumerate(days):
                row = reads[d]
                got = _by_symbol(row, symbols)
                if row["rep"] and got is not None:
                    ws[:, i], R[:, i] = got
                    rep[i] = True
                rg[i] = float(row["r"]) - float(row["g_bp"]) * 1e-4 * float(row["sides"])
                gap[i] = float(row["r"]) - float(row["r15"]) if row["r15"] is not None else 0.0
            a, a15 = P.alpha(rg, gap, ws, R, mu, wbar, include=rep)
            sigma = P.sigma_used(float(prm["sigma"]), tilde)
            z = np.where(rep, a / sigma, 0.0)
            z15 = np.where(rep, a15 / sigma, 0.0)
            if (1.0 - float(rep.mean())) > UNREPRODUCED_MAX:
                z, z15 = np.zeros_like(z), np.zeros_like(z15)
                warned.append(str(m["lineage"]))
            per.append((dict(zip(days, z.tolist())), dict(zip(days, z15.tolist())), reads, days[0], stop_after,
                        {d for d, ok in zip(days, rep.tolist()) if ok}))
        D: list[float] = []
        D15: list[float] = []
        act: list[int] = []
        mar: list[tuple[float, int, int]] = []
        for s in sessions:
            vals: list[float] = []
            vals15: list[float] = []
            bs: list[float] = []
            zeroed = slots = 0
            for zmap, z15map, reads, join, stop_after, reproduced in per:
                if join is None or join > s:
                    continue                              # not active yet: not in the mean
                vals.append(zmap.get(s, 0.0))
                vals15.append(z15map.get(s, 0.0))
                if s in reads:
                    bs.append(float(reads[s]["b"]))
                if stop_after is not None and stop_after < s:
                    continue                              # a stopped member's zeroed days are counted apart
                slots += 1
                if s not in reads or s not in reproduced:
                    zeroed += 1                           # an absent row, an audit mark, a day not reproduced
            D.append(math.fsum(vals) / len(vals) if vals else 0.0)
            D15.append(math.fsum(vals15) / len(vals15) if vals15 else 0.0)
            act.append(len(vals))
            mar.append((abs(math.fsum(bs) / len(bs)) if bs else 0.0, zeroed, slots))
        return {"D": D, "D15": D15, "active": act, "mar": mar, "warned": warned}

    def clusters_now(self) -> dict[str, list[str]]:
        """Every cluster as it stands: the receipt's (`pool_units.cluster`), joined by every join a look recorded
        (`pool_clusters`, in order; a join only tightens and no cluster is ever split). {id: its cells}; a joined
        cluster's id is its parts' ids joined by "+" (the vendored `join_clusters`' naming)."""
        groups: dict[str, set[str]] = {}
        for c, u in self.units().items():
            groups.setdefault(str(u["cluster"]), set()).add(c)
        for r in self.store.execute("SELECT cluster, cells FROM pool_clusters ORDER BY at, look, cluster"):
            joined = set(json.loads(r["cells"]))
            touched = [cid for cid, cells in groups.items() if cells & joined]
            if len(touched) < 2:
                continue
            union = set().union(*(groups.pop(cid) for cid in touched))
            groups["+".join(sorted(touched))] = union
        return {cid: sorted(cells) for cid, cells in sorted(groups.items())}

    def u_of(self, cells: Sequence[str]) -> tuple[tuple[float, float], list[Any]]:
        """U_u of a cluster of these cells and the tickets its parts dropped: its receipt cluster's at the clock, or,
        for a cluster joined at a look, the union bound over the receipt clusters it holds (`pool_rule.joined_u`: a cap
        only falls)."""
        units = self.units()
        parts: dict[str, tuple[float, float]] = {}
        dropped: list[Any] = []
        for c in cells:
            u = units[c]
            cid = str(u["cluster"])
            if cid not in parts:
                parts[cid] = (float(u["u_point"]), float(u["u_bound"]))
                found = self.receipt.clusters.get(cid)
                dropped.extend(found.dropped if found is not None else ())
        values = [parts[k] for k in sorted(parts)]
        return (values[0] if len(values) == 1 else P.joined_u(values)), dropped

    def effective_cluster(self, cell: str) -> tuple[str, list[str], P.Caps]:
        """The cluster a cell is judged in now (`clusters_now`): (its id, its cells, its caps (`u_of` through
        `pool_rule.caps`: a report-only unit's or a join's report-only caps included))."""
        for cid, cells in self.clusters_now().items():
            if cell in cells:
                u, dropped = self.u_of(cells)
                caps_ = P.caps(u[0], u[1], dropped)
                if any(int(self.units()[c]["report_only"]) for c in cells) and not caps_.report_only:
                    caps_ = P.caps(None, None)
                return cid, cells, caps_
        raise KeyError(cell)

    def judged_members(self, cells: Sequence[str], members_at: Mapping[str, Sequence[Mapping[str, Any]]]
                       ) -> dict[tuple[str, str], list[Any]]:
        """{cell key: [Member]} of these cells (the looking cell's members active through its look, `members_at`;
        every other cell's as they stand), by pid; `Wait` while a member lacks its Train series."""
        out: dict[tuple[str, str], list[Any]] = {}
        for c in cells:
            ms = []
            for m in members_at.get(c, self.cell_members(c)):
                mm = self.member(int(m["pid"]))
                if mm is None:
                    raise Wait("train", f"{m['lineage']}'s Train series is not written yet")
                ms.append(mm)
            out[P.cell_key(c)] = sorted(ms, key=lambda x: int(x.meta.get("pid") or 0))
        return out

    def retest(self, cell: str, look_key: str, members_at: Mapping[str, Sequence[Mapping[str, Any]]]) -> None:
        """THE CLUSTERS RE-TESTED at a look (section 1.4) on Train only by the vendored member rule (`pool_rule.cluster`:
        `join_clusters`), with the members then active (the looking cell's through its look, every other cell's as it
        stands): clusters it joins are recorded (`pool_clusters`) from this look; their joint floor and U_u follow
        (`effective_cluster`), a join that makes its caps report-only makes it report-only from this look on (sticky),
        and a recorded pass of either is re-derived at the joint bar (`demotions`)."""
        current = self.clusters_now()
        all_cells = [c for cells in current.values() for c in cells]
        judged = self.judged_members(all_cells, members_at)
        clusters = {cid: [P.cell_key(c) for c in cells] for cid, cells in current.items()}
        joined, _ = P.cluster(self.cal, clusters, judged, self.hc())
        for name, keys in sorted(joined.items()):
            if name in current:
                continue
            cells = sorted(f"{k[0]}/{k[1]}" for k in keys)
            u, dropped = self.u_of(cells)
            ro = P.caps(u[0], u[1], dropped).report_only or any(int(self.units()[c]["report_only"]) for c in cells)
            with self.store:
                self.store.execute("INSERT OR IGNORE INTO pool_clusters(look, cluster, cells, u_point, u_bound, "
                                   "report_only, at) VALUES (?,?,?,?,?,?,?)",
                                   (look_key, name, _dumps(cells), u[0], u[1], int(ro), self.clock()))
                event(self.store, "joined", at=self.clock(), cell=cell, once=f"{look_key}:{name}",
                      payload={"cluster": name, "cells": cells, "report_only": bool(ro)})
            self.tally["joined"] += 1

    def c_own(self, cid: str, cells: Sequence[str], look_key: str, engine: int, through: Mapping[str, str],
              caps: P.Caps) -> int | None:
        """THE BAR of the cluster at a look (the contract's 4.1; `pool_floors`, once a cluster and look): the vendored
        floor pipeline (`pool_rule.house_floor`) on the cluster's members active through the look (each joined at the
        cell session it joined its cell at; each cell's founders' sigma), the receipt's boot seed (a cluster made by a
        join takes `pool_rule.joined_seed`), the receipt's B and the caps of the count read; c_own of the receipt's
        floor definition, the matched minimum of the receipt's table at each cell's active m, and the bar
        (`pool_rule.k_used`; None: ineligible). Its resamples are kept in `pool_boot` across nights; raises `Wait`
        while it cannot be finished tonight or a cell's m has no row (above 60)."""
        held = self.store.execute("SELECT row FROM pool_floors WHERE cluster=? AND look=?", (cid, look_key)).fetchone()
        if held is not None:
            return json.loads(held[0]).get("k_used")
        judged: dict[tuple[str, str], list[Any]] = {}
        joins: dict[str, int] = {}
        fsig: dict[tuple[str, str], list[float]] = {}
        m_by_cell: dict[str, int] = {}
        for c in cells:
            sess = self.sessions(c, engine)
            cutoff = through.get(c)
            sess = [s for s in sess if cutoff is None or s <= cutoff]
            ms = []
            for m in self.cell_members(c):
                counted = counted_by_day(self.fdb, int(m["pid"]), engine)
                join_day = min((d for d in counted if d >= m["joins"]), default=None)
                if join_day is None or (cutoff is not None and join_day > cutoff):
                    continue                              # not active by the look: not in the floor
                mm = self.member(int(m["pid"]))
                if mm is None:
                    raise Wait("train", f"{m['lineage']}'s Train series is not written yet (the own floor)")
                ms.append(mm)
                joins[mm.name] = sum(1 for s in sess if s < join_day)
            judged[P.cell_key(c)] = sorted(ms, key=lambda x: int(x.meta.get("pid") or 0))
            fsig[P.cell_key(c)] = self.founders_sigma(c)
            m_by_cell[c] = len(ms)
        minimum = P.minimum_of(self.receipt, m_by_cell)
        fd = self.receipt.rule.floor_def
        if minimum.get(fd) is None:
            raise Wait("receipt", "a cell's active members have no row of the receipt's matched-family table (m above "
                                  "60): no bar, the look waits")
        found = self.receipt.clusters.get(cid)
        seed = found.boot_seed if found is not None else P.joined_seed(cid, look_key)
        look = self.floor_key(look_key, judged, joins, self.receipt.B, seed)
        fl = P.house_floor(self.cal, cid=cid, keys=[P.cell_key(c) for c in cells], judged=judged, hc=self.hc(),
                           B=self.receipt.B, boot_seed=seed, caps_=caps, joins=joins, founders_sigma=fsig,
                           boot=self.boot_hook(cid, look))
        floors = P.pin_floors(fl, self.receipt, minimum)
        ku = floors[fd]["k_used"]
        with self.store:
            self.store.execute("INSERT OR IGNORE INTO pool_floors(cluster, look, row, at) VALUES (?,?,?,?)",
                               (cid, look_key, _dumps({"k_used": ku, "floors": floors, "seed": seed,
                                                       "cap": caps.cap, "wall": caps.wall,
                                                       "report_only": caps.report_only, "m": m_by_cell,
                                                       "joins": joins}), self.clock()))
        return ku

    def placebo(self, cell: str, engine: int, sessions: Sequence[str], m: int, T: float, k: int) -> tuple[int | None, int]:
        """THE PLACEBO LEG (section 2.1): (how many of 999 pseudo-cells of the cell's group's skill-free controls have
        T_k at or above the cell's, the draws). Raises `Wait` on the House's failure."""
        import numpy as np

        unit = self.units()[cell]
        grp = str(unit["grp"])
        controls = [forward_db.program(self.fdb, str(r["key"])) for r in self.fdb.execute(
            "SELECT key FROM fwd_registry WHERE reason='control' AND ugroup=? ORDER BY pid", (grp,))]
        controls = [c for c in controls if c is not None][:P.PLACEBO_CONTROLS]
        if len(controls) < m:
            raise Wait("controls", f"fewer than {m} skill-free controls of {grp}")
        zs = []
        for prog in controls:
            row = self.store.execute("SELECT * FROM pool_controls WHERE pid=?", (prog.pid,)).fetchone()
            spec = json.loads(prog.code)
            if row is None:
                if self._over():
                    raise Wait("budget", "the controls' Train replays continue the next night")
                try:
                    eras = self._timed(lambda: self.runs.control_train(spec))
                except Exception as exc:  # noqa: BLE001 - the House's
                    self._ev("house", cell=cell, once=f"control:{prog.pid}:{self.night}",
                             payload={"why": "a control's Train replay did not finish", "error": type(exc).__name__})
                    raise Wait("house", "a control's Train replay did not finish") from None
                held = [e for e in eras if e is not None]
                names = list(held[0]["symbols"]) if held else [str(x) for x in spec.get("symbols") or ()]
                wbar = np.array([P.control_wbar(spec).get(x, 0.0) for x in names])
                if held:
                    mu = np.concatenate([np.asarray(e["R"]) for e in held], axis=1).mean(axis=1)
                    sigma = P.train_sigma([(np.asarray(e["r0"]), np.zeros(len(e["r0"])), np.asarray(e["ws"]),
                                            np.asarray(e["R"])) for e in held], mu, wbar)
                else:
                    mu, sigma = np.zeros(len(names)), None       # no Train history: its sigma is the 5 bp floor
                with self.store:
                    self.store.execute("INSERT OR IGNORE INTO pool_controls(pid, grp, symbols, mu, wbar, sigma, at) "
                                       "VALUES (?,?,?,?,?,?,?)", (prog.pid, grp, _dumps(names), _dumps(mu.tolist()),
                                                                  _dumps(wbar.tolist()), sigma, self.clock()))
                row = self.store.execute("SELECT * FROM pool_controls WHERE pid=?", (prog.pid,)).fetchone()
            try:
                fwd = self._timed(lambda: self.runs.control_forward(prog, settings=self.settings, fdb=self.fdb))
            except Exception as exc:  # noqa: BLE001 - the House's
                self._ev("house", cell=cell, once=f"control_fwd:{prog.pid}:{self.night}",
                         payload={"why": "a control's forward replay did not finish", "error": type(exc).__name__})
                raise Wait("house", "a control's forward replay did not finish") from None
            counted = counted_by_day(self.fdb, prog.pid, engine)
            clock = str(unit["clock"])
            days = sorted(d for d in counted if clock <= d <= sessions[-1])
            symbols = json.loads(row["symbols"])
            mu, wbar = np.array(json.loads(row["mu"])), np.array(json.loads(row["wbar"]))
            ws = np.array([fwd["ws"].get(d, [0.0] * len(symbols)) for d in days]).T if days else np.zeros((len(symbols), 0))
            R = np.array([fwd["R"].get(d, [0.0] * len(symbols)) for d in days]).T if days else np.zeros((len(symbols), 0))
            r0 = np.array([float(counted[d]["r0"] if counted[d].get("r0") is not None else 0.0) for d in days])
            a, _ = P.alpha(r0, np.zeros(len(days)), ws, R, mu, wbar)
            sigma = max(float(row["sigma"] or 0.0), P.SIGMA_FLOOR)
            zmap = dict(zip(days, (a / sigma).tolist()))
            zs.append([zmap.get(s, 0.0) for s in sessions[:k]])
        Z = np.array(zs)
        seed = P.placebo_seed(self.receipt.sha256, cell, k)
        draws = P.placebo_draws(len(controls), m, seed)
        pseudo = [P.t_stat(Z[list(d)].mean(axis=0).tolist()) for d in draws]
        return P.placebo_count(T, pseudo), len(draws)

    def look(self, cell: str) -> str | None:
        """One cell's next look, when its k-th cell session has come (the module docstring, 5); the word written, or
        None (no look due, or a wait: nothing written)."""
        if self.verdict(cell) is not None:
            return None
        engine = self.unit_engine(cell)
        if engine is None:
            return None
        checks = {int(r["k"]): dict(r) for r in self.store.execute("SELECT * FROM pool_checks WHERE cell=?", (cell,))}
        if checks and self.engine_now is not None and engine != self.engine_now:
            moved = self.engine_move(cell, engine, checks)
            if moved != "carried":
                return moved
            engine = self.engine_now
        sess = self.sessions(cell, engine)
        due = [k for k in P.PLAN if k not in checks and len(sess) >= k]
        if not due:
            return None
        k = due[0]
        look_key = f"{cell}:{k}"
        head = sess[:k]
        try:
            members = self.cell_members(cell)
            out = self.series(cell, engine, head, members=members)
            # D_1..k' of every earlier look, read again: a moved series is VOID (the judged days moved)
            for kk, row in sorted(checks.items()):
                if int(row["engine"]) != engine:
                    continue
                again = self.series(cell, engine, sess[:kk], members=members)
                if P.series_sha(sess[:kk], again["D"], again["D15"]) != row["sha"]:
                    self._final(cell, "VOID", k=kk, day=sess[kk - 1], engine=engine, why="a later look read D_1..k "
                                "again and it is not the stored series: the judged days moved")
                    return "VOID"
            mar = P.mar_void(out["mar"])
            if mar["void"]:
                self._final(cell, "VOID", k=k, day=head[-1], engine=engine, series=out, mar=mar,
                            why="its zeroed member-days cluster on the sessions of large benchmark moves (section 2.2)")
                return "VOID"
            point = P.look(out["D"], out["D15"], k)
            members_at = {cell: [m for m in members if (self.join_day(m, engine) or "9999") <= head[-1]]}
            self.retest(cell, look_key, members_at)
            cid, cells, caps = self.effective_cluster(cell)
            through = {cell: head[-1]}
            ku = self.c_own(cid, cells, look_key, engine, through, caps)
            c_value = None if ku is None else ku / 100.0
            passed = False
            count = draws = None
            why = None
            if c_value is None:
                why = "ineligible: no own floor holds the caps on the grid (above 5.00): no verdict at this look"
                self._ev("ineligible", cell=cell, once=look_key, payload={"why": why})
            elif P.legs_pass(point, c_value):
                count, draws = self.placebo(cell, engine, head, max(1, out["active"][-1]), float(point["T"]), k)
                passed = P.placebo_holds(count, draws)
                if not passed:
                    why = "the placebo leg"
            else:
                why = "below the bar or the stress leg at or under zero"
        except Wait as w:
            self.missed(cell, w.cause, w.why)
            return None
        for lineage in out["warned"]:
            if self._ev("unreproduced", cell=cell, lineage=lineage, once=look_key,
                        payload={"why": "more than 10% of its days do not reproduce: it enters as z = 0 throughout"}):
                self.tally["unreproduced"] += 1
        sha = P.series_sha(head, out["D"], out["D15"])
        word = "PASS" if passed else ("FAIL" if k == P.PLAN[-1] else ("ineligible" if c_value is None else "not_passed"))
        with self.store:
            self.store.execute("INSERT OR IGNORE INTO pool_checks(cell, k, engine, word, sha, look, at) VALUES "
                               "(?,?,?,?,?,?,?)", (cell, k, int(engine), word, sha, look_key, self.clock()))
            if passed or k == P.PLAN[-1]:
                self.store.execute(
                    "INSERT OR IGNORE INTO pool_verdicts(cell, word, k, day, engine, t, c_used, series, mar, placebo, "
                    "why, at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (cell, "PASS" if passed else ("INELIGIBLE" if c_value is None else "FAIL"), k, head[-1], int(engine),
                     point["T"], c_value, _dumps({"days": head, "D": out["D"], "D15": out["D15"]}), _dumps(mar), count,
                     "passed at look " + str(k) if passed else (why or "no look of 40, 60, 120 passed: failed for good"),
                     self.clock()))
            event(self.store, "look", at=self.clock(), cell=cell, once=look_key, payload={"k": k, "word": word})
        self.tally["looks"] += 1
        if passed or k == P.PLAN[-1]:
            self.tally["verdicts"] += 1
            return "PASS" if passed else "FAIL"
        return word

    def _final(self, cell: str, word: str, *, k: int | None, day: str | None, engine: int, why: str,
               series: Mapping[str, Any] | None = None, mar: Mapping[str, Any] | None = None) -> None:
        with self.store:
            self.store.execute("INSERT OR IGNORE INTO pool_verdicts(cell, word, k, day, engine, series, mar, why, at) "
                               "VALUES (?,?,?,?,?,?,?,?,?)",
                               (cell, word, k, day, int(engine),
                                None if series is None else _dumps({"D": series["D"], "D15": series["D15"]}),
                                None if mar is None else _dumps(mar), why, self.clock()))
            event(self.store, "verdict", at=self.clock(), cell=cell, once="verdict", payload={"word": word, "why": why})
        self.tally["verdicts"] += 1

    def engine_move(self, cell: str, old: int, checks: Mapping[int, Mapping[str, Any]], *, passed: bool = False) -> str:
        """AN ENGINE MOVE after a look (section 7.1 (3)): each member's judged days (its `pool_fwd` days under `old`)
        compared under the newest id (`forward_screen.engine_reading`): "wait" (rows not written yet: nothing
        changes), "VOID" (a judged day moved beyond a vendor restatement: a pending cell is VOID; a passed one's pass
        is LOST, never gained), else "carried" (the cell reads on under the new id, `engine_switched`)."""
        new = int(self.engine_now)  # type: ignore[arg-type]
        for m in self.cell_members(cell):
            days = [str(r[0]) for r in self.store.execute("SELECT day FROM pool_fwd WHERE pid=? AND engine=? ORDER BY day",
                                                          (int(m["pid"]), int(old)))]
            if not days:
                continue
            reading, _ = FS.engine_reading(self.fdb, int(m["pid"]), int(old), new, days)
            if reading == "wait":
                self.missed(cell, "engine", "its judged days have no rows under the record's new engine id yet")
                return "wait"
            if reading == "touched":
                why = "an engine change touched its judged days: one engine id a judged series"
                if passed:
                    self._lost(cell, None, f"{why}: the pass is lost")
                else:
                    self._final(cell, "VOID", k=max(checks) if checks else None, day=None, engine=old, why=why)
                return "VOID"
        self._ev("engine_switched", cell=cell, once=f"{old}>{new}",
                 payload={"why": "an engine change left its judged days as they were", "from": int(old), "to": new})
        return "carried"

    # ---------------------------------------------------------------------------------------- 6. the demotion
    def demotions(self, cell: str) -> None:
        """A PASS cell (the module docstring, 6): its pass re-derived after a join at the cluster's joint bar and after
        an engine move at the same k and bar on the new series (LOST, never gained); then THE CELL DEMOTION on its
        post-pass sessions, read on the members active at the pass, every 20th (DEMOTED, sticky)."""
        v = self.verdict(cell)
        if v is None or v["word"] != "PASS" or v["engine"] is None:
            return
        if self.store.execute("SELECT 1 FROM pool_demotions WHERE cell=?", (cell,)).fetchone() is not None:
            return
        k, day, c_value = int(v["k"]), str(v["day"]), float(v["c_used"])
        # a join after the pass: the pass re-derived at the joint bar (its own T against the joint floor's c_used)
        cid, cells, _ = self.effective_cluster(cell)
        if len(cells) > 1:
            for r in self.store.execute("SELECT look FROM pool_clusters ORDER BY at DESC"):
                held = self.store.execute("SELECT row FROM pool_floors WHERE cluster=? AND look=?", (cid, str(r[0]))).fetchone()
                if held is None:
                    continue
                ku = json.loads(held[0]).get("k_used")
                if ku is None or v["t"] is None or float(v["t"]) < ku / 100.0:
                    self._lost(cell, None, "re-derived at the joint bar of the cluster it joined: the pass is lost")
                    return
                break
        engine = self.unit_engine(cell)
        checks = {int(r["k"]): dict(r) for r in self.store.execute("SELECT * FROM pool_checks WHERE cell=?", (cell,))}
        if engine is not None and self.engine_now is not None and engine != self.engine_now:
            if self.engine_move(cell, engine, checks, passed=True) != "carried":
                return
            return                                        # the new id's sessions are read from the next night
        if engine != int(v["engine"]):
            # carried to a new engine id: the pass re-derived once at the same k and bar on the new series
            key = f"rederived:{engine}"
            if self.store.execute("SELECT 1 FROM pool_events WHERE kind='look' AND cell=? AND once=?",
                                  (cell, key)).fetchone() is None:
                sess = self.sessions(cell, engine)
                if len(sess) < k:
                    return
                try:
                    out = self.series(cell, engine, sess[:k])
                    point = P.look(out["D"], out["D15"], k)
                    held = P.legs_pass(point, c_value)
                    if held:
                        count, draws = self.placebo(cell, engine, sess[:k], max(1, out["active"][-1]),
                                                    float(point["T"]), k)
                        held = P.placebo_holds(count, draws)
                except Wait as w:
                    self.missed(cell, w.cause, w.why)
                    return
                self._ev("look", cell=cell, once=key, payload={"k": k, "word": "PASS" if held else "LOST"})
                if not held:
                    self._lost(cell, None, "re-derived at the same look and bar on the new engine id's series: the pass "
                                           "is lost")
                    return
            day = self.sessions(cell, engine)[k - 1]
        sess = self.sessions(cell, engine)
        post = [s for s in sess if s > day]
        passing = [m for m in self.cell_members(cell) if (self.join_day(m, engine) or "9999") <= day]
        done = {int(r["n"]) for r in self.store.execute("SELECT n FROM pool_post WHERE cell=?", (cell,))}
        upto = [s for s in sess if s <= day]
        for n in range(P.DEMOTE_EVERY, len(post) + 1, P.DEMOTE_EVERY):
            if n in done:
                continue
            try:
                out_post = self.series(cell, engine, post[:n], members=passing)
                out_all = self.series(cell, engine, upto + post[:n], members=passing)
            except Wait as w:
                self.missed(cell, w.cause, w.why)
                return
            why = P.demote(out_post["D"], out_post["D15"], out_all["D"])
            with self.store:
                self.store.execute("INSERT OR IGNORE INTO pool_post(cell, n, sha, word, at) VALUES (?,?,?,?,?)",
                                   (cell, n, P.series_sha(post[:n], out_post["D"], out_post["D15"]),
                                    "DEMOTED" if why else "held", self.clock()))
            if why:
                self._lost(cell, n, why)
                return

    def _lost(self, cell: str, n: int | None, why: str) -> None:
        with self.store:
            self.store.execute("INSERT OR IGNORE INTO pool_demotions(cell, n_post, why, at) VALUES (?,?,?,?)",
                               (cell, n, why, self.clock()))
            event(self.store, "demoted", at=self.clock(), cell=cell, once="demoted", payload={"why": why})
        self.tally["demoted"] += 1

    # ------------------------------------------------------------------------------------------------ the night
    def run_routes(self, now: float) -> dict[str, Any] | None:
        """THE NIGHT'S FIRST HALF: the clock and the route list (1), the later lineages' sightings and holds, the
        founders waiting on an FWD1 row, the Train series and the decisions (2, 3); the pin's row, or None while there
        is no clock. The permit file is written right after it (`night`, in a finally)."""
        pin = self.clock_row(now)
        if pin is None:
            return None
        self.sight(pin)
        self.decide_founders()
        self.train_step()
        self.decide()
        return pin

    def run_looks(self) -> None:
        """THE NIGHT'S SECOND HALF: every judged unit's sessions, look and demotion (4-6); a cell whose step fails is an
        alarm (`look_failed`, once a cell and night) and the others go on."""
        for cell in sorted(self.judged_units()):
            v = self.verdict(cell)
            if v is not None and v["word"] != "PASS":
                continue
            try:
                self.classify(cell)
                self.look(cell)
                self.demotions(cell)
            except sqlite3.Error:
                self.tally["house"] += 1
            except Exception as exc:  # noqa: BLE001 - one cell's failure never stops the others; an alarm
                self.tally["look_failed"] += 1
                self._ev("look_failed", cell=cell, once=f"{self.night}", payload={"error": type(exc).__name__,
                                                                                 "why": str(exc)[:200]})
                self.note(f"cell {cell}: its look failed tonight ({type(exc).__name__}); asked again the next night")

    def run(self, now: float) -> dict[str, Any]:
        """Both halves of one night (`run_routes`, then `run_looks` when there is a clock); the tally."""
        if self.run_routes(now) is not None:
            self.run_looks()
        return dict(self.tally)


# ----------------------------------------------------------------------------------------------- permits and report
def pool_on(settings: Mapping[str, Any] | None) -> bool:
    """`elane.pool.mode` is not "off" (an absent block or key is the code's "off"; any other value is not): the reading
    under which a missing permit file fails closed (league/swarm/elane_forward.py `pool_on`; a test holds the two
    equal)."""
    raw = settings.get("elane") if isinstance(settings, Mapping) else None
    raw = raw.get("pool") if isinstance(raw, Mapping) else None
    if not isinstance(raw, Mapping) or "mode" not in raw:
        return False
    return raw.get("mode") != "off"


#: The words after which a unit's looks are over (its verdict is final, it ended ineligible, or its cluster is
#: nonconforming): its lineages are shown again in FWD1's report and the BH/BY meter
#: (league/ops/forward_report.py `POOL_OVER`; a test holds the two equal).
OVER = (*P.FINAL, P.INELIGIBLE, P.NONCONFORMING)


def withheld(root: str | Path, settings: Mapping[str, Any] | None) -> tuple[frozenset[str], bool]:
    """THE OPERATOR VIEWS' WITHHOLDING (section 8; 11 P1 item 5): (the lineages on the permit file's POOL-route or hold
    list whose unit's verdict is not final (a held lineage has no unit yet), False). FAIL CLOSED: (frozenset(), True),
    "withhold every ETF lineage", when the file cannot be read or is not the job's shape, or is missing while
    `elane.pool.mode` is not "off" (`pool_on`) or while this job's store exists (the job never deletes the file).
    league/ops/forward_report.py keeps its own copy (release E3's seal: it imports no pool module); a test holds the
    two equal."""
    path = Path(root) / PERMITS
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return frozenset(), pool_on(settings) or (Path(root) / DB).exists()
    except (OSError, ValueError):
        return frozenset(), True
    if not isinstance(doc, Mapping) or doc.get("version") != PERMITS_VERSION or not isinstance(doc.get("routes"), Mapping) \
            or not isinstance(doc.get("holds"), list) or not isinstance(doc.get("units"), Mapping):
        return frozenset(), True
    out = {str(x) for x in doc["holds"]}
    for lineage, row in doc["routes"].items():
        cell = row.get("cell") if isinstance(row, Mapping) else None
        unit = doc["units"].get(cell) if cell is not None else None
        if not isinstance(unit, Mapping) or unit.get("word") not in OVER:
            out.add(str(lineage))
    return frozenset(out), False


def unit_words(store: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    """Every unit's cluster and word: REFUTED or "ineligible" when the clock found it so; "report_only" for a
    report-only cluster's unit, or one a join made report-only (its verdict goes to the operator's report alone);
    "nonconforming" for a cluster the clock-start conformance did not hold; else its final verdict's (a lost or demoted
    pass DEMOTED; an ineligible end "ineligible"), else pending."""
    demoted = {str(r[0]) for r in store.execute("SELECT cell FROM pool_demotions")}
    verdicts = {str(r["cell"]): str(r["word"]) for r in store.execute("SELECT cell, word FROM pool_verdicts")}
    joined_ro: set[str] = set()
    for r in store.execute("SELECT cells FROM pool_clusters WHERE report_only=1"):
        joined_ro.update(str(c) for c in json.loads(r["cells"]))
    out = {}
    for u in store.execute("SELECT cell, cluster, report_only, refuted, ineligible, conforming FROM pool_units "
                           "ORDER BY cell"):
        cell = str(u["cell"])
        if int(u["refuted"]):
            word = "REFUTED"
        elif int(u["ineligible"]):
            word = P.INELIGIBLE
        elif int(u["report_only"]) or cell in joined_ro:
            word = P.REPORT_ONLY
        elif int(u["conforming"]) == 0:
            word = P.NONCONFORMING
        elif cell in demoted:
            word = "DEMOTED"
        elif cell in verdicts:
            word = P.INELIGIBLE if verdicts[cell] == "INELIGIBLE" else verdicts[cell]
        else:
            word = P.PENDING
        out[cell] = {"cluster": str(u["cluster"]), "word": word}
    return out


def held_lineages(store: sqlite3.Connection) -> list[str]:
    """The hold list: every lineage held and neither released nor routed."""
    return sorted(str(r[0]) for r in store.execute(
        "SELECT lineage FROM pool_holds WHERE lineage NOT IN (SELECT lineage FROM pool_releases) AND lineage NOT IN "
        "(SELECT lineage FROM pool_routes)"))


def eligible_rows(store: sqlite3.Connection, fdb: sqlite3.Connection, fwd1: Mapping[str, Mapping[str, Any]] | None
                  ) -> list[dict[str, Any]]:
    """THE ELIGIBLE LINEAGES of a PASS (section 6.1, the job's half: (a) its counted rows cover at least
    `NO_FREE_RIDE` of the cell sessions up to the passing look and it has no disqualified row in its last 20 sessions,
    (b) it is on the POOL route and a member (a merged copy never is), (e) it never reached a sealed pre-check (FWD1
    voids such a lineage), (f) its cluster is not report-only; the swarm asks the rest in P2), within the cell in
    Train-era K order (close days per 250 sessions, the larger first) then the lower pid. Ids only: no K is written."""
    from fractions import Fraction

    words = unit_words(store)
    out: list[dict[str, Any]] = []
    for v in store.execute("SELECT * FROM pool_verdicts WHERE word='PASS' ORDER BY cell"):
        cell = str(v["cell"])
        if (words.get(cell) or {}).get("word") != "PASS" or v["engine"] is None:
            continue
        engine = int(v["engine"])
        sessions = [str(r[0]) for r in store.execute(
            "SELECT day FROM pool_sessions WHERE cell=? AND engine=? AND session=1 AND day <= ? ORDER BY day",
            (cell, engine, str(v["day"])))]
        rows = []
        for m in store.execute("SELECT m.lineage AS lineage, m.pid AS pid FROM pool_members m JOIN pool_routes r ON "
                               "r.lineage = m.lineage WHERE m.cell=? AND m.route='pool' AND m.merged_into IS NULL",
                               (cell,)):
            pid = int(m["pid"])
            counted = {str(r["day"]) for r in forward_db.counted_days(fdb, pid, engine=engine)}
            if sum(1 for s in sessions if s in counted) < P.NO_FREE_RIDE:
                continue
            last = [str(r[0]) for r in fdb.execute("SELECT status FROM fwd_days WHERE pid=? AND engine=? ORDER BY day "
                                                   "DESC LIMIT ?", (pid, engine, P.NO_FREE_RIDE))]
            if "disqualified" in last:
                continue
            facts = (fwd1 or {}).get(str(m["lineage"])) or {}
            if str(facts.get("status")) == "void":
                continue
            prm = store.execute("SELECT k_close, k_sessions FROM pool_params WHERE pid=?", (pid,)).fetchone()
            k = Fraction(int(prm["k_close"]) * 250, int(prm["k_sessions"])) if prm is not None and prm["k_sessions"] \
                else Fraction(0)
            reg = fdb.execute("SELECT family, version, run_sha FROM fwd_registry WHERE pid=?", (pid,)).fetchone()
            rows.append((-k, pid, {"lineage": str(m["lineage"]), "cell": cell, "cluster": (words.get(cell) or {}).get("cluster"),
                                    "family": None if reg is None else reg["family"],
                                    "version": None if reg is None else reg["version"],
                                    "run_sha": None if reg is None else reg["run_sha"],
                                    "fwd1_cell": facts.get("cell")}))
        out.extend(r[2] for r in sorted(rows, key=lambda r: (r[0], r[1])))
    return out


def permits_doc(store: sqlite3.Connection | None, *, receipt: P.Receipt | None, at: float,
                fdb: sqlite3.Connection | None = None, why: str | None = None,
                fwd1: Mapping[str, Mapping[str, Any]] | None = None,
                existing: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """THE PERMIT FILE's document (the module docstring, 7): ids and fixed words only. NEVER SHORTER than `existing`
    (the readable file on disk): its routes are carried whole, its holds unless the store records the lineage's
    release (or route), its units' words where the store has none, and its receipt sha and clock while the store has
    none (a lost store lifts nothing). `why` is a word of `WHY_WORDS` (another text is written "unreadable_reason")."""
    routes: dict[str, Any] = {}
    holds: set[str] = set()
    units: dict[str, Any] = {}
    lineages: dict[str, Any] = {}
    released: set[str] = set()
    clock = None
    sha = None
    if store is not None:
        for r in store.execute("SELECT lineage, cell, cluster FROM pool_routes ORDER BY lineage"):
            routes[str(r["lineage"])] = {"cell": r["cell"], "cluster": r["cluster"]}
        holds = set(held_lineages(store))
        released = {str(r[0]) for r in store.execute("SELECT lineage FROM pool_releases")}
        units = unit_words(store)
        pin = store.execute("SELECT sha, clock FROM pool_pins ORDER BY at LIMIT 1").fetchone()
        if pin is not None:
            clock, sha = str(pin["clock"]), str(pin["sha"])
        for r in store.execute("SELECT lineage, cell FROM pool_members ORDER BY lineage"):
            cell = r["cell"]
            lineages[str(r["lineage"])] = {"cell": cell, "cluster": None if cell is None else
                                           (units.get(str(cell)) or {}).get("cluster")}
    if existing:
        for lineage, row in (existing.get("routes") or {}).items():
            if str(lineage) not in routes:
                routes[str(lineage)] = {"cell": (row or {}).get("cell"), "cluster": (row or {}).get("cluster")}
        for lineage in existing.get("holds") or []:
            if str(lineage) not in released and str(lineage) not in routes:
                holds.add(str(lineage))
        for cell, row in (existing.get("units") or {}).items():
            if str(cell) not in units and isinstance(row, Mapping):
                units[str(cell)] = {"cluster": row.get("cluster"), "word": row.get("word")}
        for lineage, row in (existing.get("lineages") or {}).items():
            if isinstance(row, Mapping):
                lineages.setdefault(str(lineage), {"cell": row.get("cell"), "cluster": row.get("cluster")})
        if sha is None and existing.get("clock"):
            sha, clock = existing.get("receipt"), existing.get("clock")
    holds -= set(routes)
    if fdb is not None:
        for lineage in sorted(_registry(fdb)):
            lineages.setdefault(lineage, {"cell": None, "cluster": None})
    eligible = eligible_rows(store, fdb, fwd1) if store is not None and fdb is not None else []
    doc = {"version": PERMITS_VERSION, "screen": P.SCREEN, "receipt": sha or (None if receipt is None else receipt.sha256),
           "clock": clock, "at": _iso(at), "routes": dict(sorted(routes.items())), "holds": sorted(holds), "units": units,
           "lineages": dict(sorted(lineages.items())), "eligible": eligible}
    if why:
        doc["why"] = why if why in WHY_WORDS else "unreadable_reason"
    return doc


def write_permits(root: str | Path, store: sqlite3.Connection | None, *, receipt: P.Receipt | None, at: float,
                  fdb: sqlite3.Connection | None = None, why: str | None = None) -> Path | None:
    """THE PERMIT FILE, atomically, 0600 (`permits_doc`, never shorter than the readable file on disk). NOTHING IS
    WRITTEN (None, and an event when there is a store) when the existing file cannot be read (it is never overwritten:
    the swarm keeps failing closed) or the document would carry a figure."""
    from .context import write_json

    existing, exists = read_permit_file(root)
    if exists and existing is None:
        if store is not None:
            with store:
                event(store, "permits_kept", at=at, once=_iso(at)[:10],
                      payload={"why": "the permit file on disk cannot be read: it is never overwritten (the swarm "
                                      "fails closed); an operator's step"})
        return None
    fwd1 = fwd1_facts(root, fdb) if fdb is not None else None
    doc = permits_doc(store, receipt=receipt, at=at, fdb=fdb, why=why, fwd1=fwd1, existing=existing)
    problems = P.figure_free(doc)
    if problems:
        if store is not None:
            with store:
                event(store, "permits_refused", at=at, once=_iso(at)[:10],
                      payload={"why": "the permit file would carry a figure: not written", "places": len(problems)})
        return None
    return write_json(Path(root) / PERMITS, doc)


def report(store: sqlite3.Connection | None, *, receipt: P.Receipt | None, notes: Sequence[str] = ()) -> dict[str, Any]:
    """THE OPERATOR'S REPORT (the module docstring, 8): no interim word or figure; the reasons in words (`notes`: the
    clock's waits, a nonconforming cluster, a refused receipt, a lost store)."""
    if store is None:
        return {"screen": P.SCREEN, "receipt": None if receipt is None else receipt.sha256, "clock": None, "units": {},
                "notes": list(notes)}
    words = unit_words(store)
    final = {c: w for c, w in words.items() if w["word"] in P.FINAL}
    report_words = {str(r["cell"]): (str(r["word"]) if str(r["word"]) != "INELIGIBLE" else P.INELIGIBLE)
                    for r in store.execute("SELECT cell, word FROM pool_verdicts")}
    read = []
    for r in store.execute("SELECT c.cell AS cell, c.k AS k, u.cluster AS cluster FROM pool_checks c JOIN pool_units u ON "
                           "u.cell = c.cell"):
        read.append((str(r["cluster"]), int(r["k"])))
    expected = P.expected_passes(read, receipt) if receipt is not None else None
    stalled = [{"cell": r["cell"], "cause": json.loads(r["payload"]).get("cause")} for r in store.execute(
        "SELECT cell, payload FROM pool_events WHERE kind='stalled' ORDER BY seq")]
    checks = {str(r["cluster"]): {"conforming": bool(r["conforming"]), "why": json.loads(r["row"]).get("why")}
              for r in store.execute("SELECT cluster, conforming, row FROM pool_clockcheck ORDER BY cluster")}
    waits = int(store.execute("SELECT COUNT(*) FROM pool_events WHERE kind='clock_wait'").fetchone()[0])
    return {"screen": P.SCREEN, "receipt": None if receipt is None else receipt.sha256,
            "clock": (store.execute("SELECT clock FROM pool_pins LIMIT 1").fetchone() or [None])[0],
            "units": {c: {"cluster": w["cluster"], "word": w["word"]} for c, w in words.items()},
            "report_only_verdicts": {c: report_words[c] for c, w in words.items()
                                     if w["word"] == P.REPORT_ONLY and c in report_words},
            "routes": int(store.execute("SELECT COUNT(*) FROM pool_routes").fetchone()[0]),
            "holds": len(held_lineages(store)),
            "members": int(store.execute("SELECT COUNT(*) FROM pool_members WHERE cell IS NOT NULL").fetchone()[0]),
            "beside": f"{sum(1 for w in final.values() if w['word'] == 'PASS')} passes of {len(words)} units; "
                      f"{'n/a' if expected is None else f'{expected:.2f}'} expected at zero edge",
            "clock_check": checks, "clock_waits": waits,
            "store_lost": store.execute("SELECT 1 FROM pool_events WHERE kind='store_lost' LIMIT 1").fetchone() is not None,
            "stalled": stalled, "notes": list(notes)}


# --------------------------------------------------------------------------------------------------------- the job
def night(root: str | Path, *, receipt: P.Receipt, settings: Mapping[str, Any] | None, now: float,
          base: str | Path | None = None, release: str | Path | None = None, runs: Any = None,
          families: Mapping[str, Mapping[str, Any]] | None = None, swarm: Any = None,
          clock: Callable[[], float] = time.time, deadline: float = float("inf"), cal: P.Calib | None = None
          ) -> dict[str, Any]:
    """One night over the state root (the module docstring): skipped when this record night already ran; else the
    night's first half, THE PERMIT FILE (in a finally: written even when a later step fails), the looks, the permit
    file and the report again, and the run's own `pool_runs` row. The receipt of counts only."""
    from .context import write_json

    root = Path(root)
    c = cfg(settings)
    began = clock()
    store = open_store(root)
    fdb = forward_db.open_db(root, readonly=True)
    fdb.row_factory = sqlite3.Row
    own_runs = runs is None
    opened = None
    judge = None
    try:
        tonight = record_night(fdb)
        if tonight is not None and store.execute("SELECT 1 FROM pool_runs WHERE night=?", (tonight,)).fetchone():
            return {"status": "skipped", "why": "this record night already ran: a second start writes nothing"}
        if own_runs:
            runs = PoolRuns(root, budget_seconds=300, clock=clock, fdb=fdb, settings=settings, deadline=deadline)
        if families is None or swarm is None:
            from ..swarm.store import SwarmStore
            from . import forward_register

            opened = SwarmStore(root, readonly=True)                 # read-only: the cards and the families
            swarm = opened if swarm is None else swarm
            families = forward_register._families(opened) if families is None else families
        judge = Night(root, store, fdb, receipt=receipt, runs=runs, families=families, swarm=swarm, settings=settings,
                      budget=float(c["cpu_seconds_night"]), clock=clock, deadline=deadline, base=base, release=release,
                      cal=cal)
        try:
            pin = judge.run_routes(now)
        finally:
            write_permits(root, store, receipt=receipt, at=clock(), fdb=fdb,
                          why=None if judge.pin_row() is not None else "clock_wait")
        if pin is not None:
            try:
                judge.run_looks()
            finally:
                write_permits(root, store, receipt=receipt, at=clock(), fdb=fdb)
        write_json(root / REPORT, report(store, receipt=receipt, notes=judge.notes))
        with store:
            store.execute("INSERT INTO pool_runs(night, started, finished, seconds, at) VALUES (?,?,?,?,?)",
                          (tonight, float(began), float(clock()), round(judge.spent, 3), float(clock())))
        return {**{k: int(v) for k, v in judge.tally.items()}, "seconds": round(judge.spent, 3)}
    finally:
        if own_runs and runs is not None:
            runs.close()
        if opened is not None:
            try:
                opened.close()
            except Exception:  # noqa: BLE001 - closing a read-only store
                pass
        fdb.close()
        store.close()


def keep_permits(root: Path, receipt: P.Receipt | None, why: str, now: float, *, detail: str | None = None) -> bool:
    """The permit file written from what the store and the readable file on disk hold (no judging): with no pin, no
    receipt, no conformance or no record, so the swarm reads a file of the job's and every POOL-route entry ever
    written stays listed. `why` is a word of `WHY_WORDS`; `detail` (words) goes to the operator's report. Whether the
    file was written (an unreadable file on disk is never overwritten)."""
    from .context import write_json

    store = open_store(root) if (root / DB).exists() else None
    fdb = None
    try:
        if (root / forward_db.DB).exists():
            try:
                fdb = forward_db.open_db(root, readonly=True)
                fdb.row_factory = sqlite3.Row
            except sqlite3.Error:
                fdb = None
        wrote = write_permits(root, store, receipt=receipt, at=now, fdb=fdb, why=why)
        write_json(root / REPORT, report(store, receipt=receipt, notes=[detail] if detail else []))
        return wrote is not None
    finally:
        if store is not None:
            store.close()
        if fdb is not None:
            fdb.close()


def run(ctx: Any) -> dict[str, Any]:
    """THE JOB (league/ops/registry.py, after `forward_shadow`, listed after `forward_screen`): skipped with its switch
    off (the permit file kept), inside 09:00-17:30 New York on a session, too near the next pre-open; with no pin, no
    receipt, a receipt whose conformance fails on this box, or no forward record, it writes the permit file from its
    store and the file on disk and judges nothing (an alarm when a pin is set and its receipt is refused); else
    `night`."""
    from ..swarm import settings as swarm_settings
    from . import forward_shadow

    root = Path(ctx.root)
    settings = swarm_settings.load(root, config=getattr(ctx, "config", None))
    if cfg(settings)["mode"] == "off":
        return {"status": "skipped", "why": "elane.pool.mode is off: the job stops, the permit file is kept"}
    now = ctx.now()
    if forward_shadow.quiet(now):
        return {"status": "skipped", "why": "inside 09:00-17:30 New York time on a session: the night's run does it"}
    deadline = min(float(now) + WALL_S - MARGIN_S, FS.preopen_deadline(now))
    if deadline - float(now) <= 10 * MIN_RUN_S:
        return {"status": "skipped", "why": "too near the next pre-open for a run to finish"}
    pinned = bool(P.pin())
    receipt, why = P.rule(conformed=conformed(root, float(now)))
    if receipt is None:
        word = "nonconforming_receipt" if "conformance" in str(why) else "no_receipt"
        keep_permits(root, None, word, float(now), detail=f"nothing is judged: {why}")
        if pinned:
            ctx.alert("warning", f"pool_screen: a POOL1 pin is set but nothing is judged: {why}")
        return {"status": "skipped", "why": f"nothing is judged: {why}"}
    if forward_db.mode(settings) == "off" or not (root / forward_db.DB).exists():
        keep_permits(root, receipt, "no_record", float(now), detail="no forward record to judge")
        return {"status": "skipped", "why": "no forward record to judge"}
    try:
        receipt_ = night(root, receipt=receipt, settings=settings, now=now, base=getattr(ctx, "base", None),
                         release=getattr(ctx, "release", None), clock=ctx.now, deadline=deadline)
    except sqlite3.Error as exc:
        return {"status": "failed", "error": f"a store could not be read or written ({type(exc).__name__})"}
    if int(receipt_.get("house") or 0):
        ctx.alert("warning", f"pool_screen: {receipt_['house']} steps waited on the House's own failures: no cell is "
                             "marked, the next night asks again")
    if int(receipt_.get("unreproduced") or 0):
        ctx.alert("warning", f"pool_screen: {receipt_['unreproduced']} members' own forward runs did not reproduce more "
                             "than 10% of their days: each enters its look as z = 0 throughout (the events name them)")
    if int(receipt_.get("stalled_now") or 0):
        ctx.alert("warning", f"pool_screen: {receipt_['stalled_now']} cells STALLED: their look waited on the House on "
                             f"{STALL_NIGHTS} record nights (the report names the cause); nothing marks them")
    if int(receipt_.get("clock_alarm") or 0):
        ctx.alert("warning", f"pool_screen: the clock has waited on {CLOCK_ALARM_NIGHTS} or more record nights with a "
                             "receipt pinned (the report names why); each later night moves it a session")
    if int(receipt_.get("store_lost") or 0):
        ctx.alert("error", "pool_screen: the permit file names this receipt's clock but pool-screen.sqlite holds none "
                           "(a lost or reset store): nothing is judged and no clock starts; the file's lists are kept")
    if int(receipt_.get("nonconforming") or 0):
        ctx.alert("warning", f"pool_screen: {receipt_['nonconforming']} founding clusters are NONCONFORMING at the clock "
                             "(their floors are not the receipt's): not clocked, their members stay per-program")
    if int(receipt_.get("look_failed") or 0):
        ctx.alert("warning", f"pool_screen: {receipt_['look_failed']} cells' looks failed tonight (the events name the "
                             "error); the permit file was written first, the next night asks again")
    return receipt_


__all__ = ["JOB", "DB", "PERMITS", "PERMITS_VERSION", "REPORT", "MODES", "SEATS", "DEFAULTS", "BOUNDS", "STALL_NIGHTS",
           "CLOCK_ALARM_NIGHTS", "TRAIN_FAILS", "WALL_S", "MARGIN_S", "UNREPRODUCED_MAX", "ROUTES", "WHY_WORDS",
           "EVENT_KINDS", "TABLES", "SCHEMA", "cfg", "open_store", "record_sha", "event", "conformance_key", "conformed",
           "fwd1_facts", "fwd1_case_n", "record_night", "first_night", "PoolRuns", "control_exposure", "Wait",
           "read_permit_file", "Night", "pool_on", "OVER", "withheld", "unit_words", "held_lineages", "eligible_rows",
           "permits_doc", "write_permits", "report", "night", "keep_permits", "run"]
