"""POOL1's job, THE RECORD HALF P1 (the owner's A55, pre-registered in A55a: scratch/pooled-screen/PREREG-POOL1.md
sha256 f42bcdc1..., section 11 P1): the pooled-by-mechanism forward screen's units, members, route list and looks,
kept append-only, and the permit file of ids and words the swarm reads. The rule is league/ops/pool_rule.py.

Owner: the POOL1 build. Protected (league/ops/ is FORBIDDEN to every role). Ops only (no module of league/swarm,
league/equity, league/live or league/gym imports it): it reads `<state>/forward.sqlite` (E3's record),
`<state>/forward-screen.sqlite` (FWD1-R's judge) and the swarm store READ-ONLY, the repository's pin and receipt, and
writes only its own `<state>/pool-screen.sqlite` (0600, WAL, append-only by trigger: `SCHEMA`), the permit file
(`PERMITS`: ids and words only) and the operator's report (`REPORT`). It moves no money, opens no seat and edits no
setting. MODE RECORD ONLY: `elane.pool.seats` is P2's switch and nothing here reads it; no seat exists in P1.

WITH ITS SWITCH OFF NOTHING RUNS (`elane.pool.mode` "off", the code's default; policy.json ships "record"): a `skipped`
receipt, and THE PERMIT FILE IS KEPT (mode off stops the job, not the file: the POOL-route refusal never lifts).
WITHOUT A PIN AND ITS RECEIPT NOTHING IS JUDGED (`pool_rule.rule`: `elane.pool_screen` of the repository's policy.json
and docs/benchmarks/pool_screen_1.json at the pin's sha256): no clock, no unit, no route list, no look; the job still
writes the permit file from what its store holds (empty before any clock), so the swarm reads a file of the job's.

THE NIGHT (`Night.run`, once a record night: a second start on the same `MAX(fwd_runs.through)` writes nothing):
1. THE CLOCK AND THE ROUTE LIST (`Night.clock`, section 7.2, 9, 12; `pool_pins`, written ONCE a receipt sha): on the
   job's first night under the release that carries the pin (a record night written after the release began: its
   `through` later than the record's last night before the release), the founding units (`pool_units`: the
   receipt's cells, clusters and stage 1; each cluster's U_u at the FWD1-R checkpoint count its candidates read
   before the clock, CAP_u, WALL_u, report-only), the founders' membership (`pool_members`), a REFUTED verdict for each
   unit stage 1 refuted and THE POOL-ROUTE LIST (`pool_routes`) from FWD1's lineages, checkpoints and verdicts as of
   that night, in ONE transaction. The clock starts at the next session (`next_session(night)`). A night FWD1's store
   cannot be read writes nothing and the next night is the first (each later night moves the clock a session).
2. THE LATER LINEAGES (`Night.sight`, `Night.decide`; section 1.1, 1.3): a registry lineage the receipt does not list,
   with a passing version, is read once: a panel, a stocks symbol, the beta class or an event reader (its card, or a
   static scan of its frozen code) is out (`pool_members`, why); otherwise, while FWD1 judges it as case N it is HELD
   (`pool_holds`: no FWD1-R seat, no sealed try) until the House assigns it. Once its own `pool_train` rows and its
   group's founders' rows exist: out by its Train exposure (under 1%, no base group above 2/3); merged into an
   earlier member (Train z correlation >= 0.7 or the same program sha: it follows that member's route, never a
   member); assigned to the clocked cell of its group its Train z correlates with most at >= rho_assign: a member
   from its first counted day after the clock (staggered), on the POOL route when the unit is pending and its cluster
   not report-only. One assigned to a final unit is not a member and stays on FWD1-R; so is one of a report-only
   cluster (a member there, on FWD1-R). A held lineage leaves the hold by its release (`pool_releases`) or the route.
3. THE HOUSE'S TRAIN SERIES (`pool_train`, `pool_params`, section 2 and 11): each member's per-symbol Train-era runs
   (`PoolRuns.train_series`, its k 1.0 and 1.5 runs over 2016-19 and 2022-24 in the job's own decider child from the
   pools' third session; per-symbol exposure by `pool_rule.lot_exposure`, which is `screen.series`' accounting a
   symbol), written once, founders first, then later lineages in pid order, inside the night's budget; mu_s, wbar_s,
   sigma, the House group, the exposure and K's Train counts frozen with them. A member without them at a look is a
   House wait, never z = 0.
4. THE CELL SESSIONS (`Night.classify`; `pool_sessions`, first write stands): each session from the clock, in order,
   once the record holds a later night, every active member's row for it has come (or `STALL_NIGHTS` record nights
   have passed) and every lineage registered by its close is decided: a CELL SESSION when at least `M_MIN` active
   members have counted rows.
5. THE LOOKS (`Night.look`; section 2, 3; `pool_checks`, `pool_verdicts`, `pool_floors`, `pool_boot`): at 40, 60 and
   120 cell sessions, on exactly D_1..k. Each member-day's reading (`pool_fwd`: the record's r, r15, w, b with the
   live-like re-price, the haircut, the sides and the House's per-symbol exposure and returns from its own forward
   run, kept where that run IS the record's day) is written once and D is computed only at looks. The cluster is
   re-tested by the member rule (a join's U_u is the union bound of its parts: a cap only falls; a recorded pass is
   re-derived at the joint bar, LOST never gained); c_own on the cluster's members (`pool_rule.own_floor`, its 2,000
   resamples spread over nights); c_used; the stress leg; the placebo leg (999 pseudo-cells of the group's skill-free
   controls on the same sessions); the zeroed-days void. A non-final look writes the word and the sha256 of D_1..k
   only (no interim figure); a PASS, a FAIL at 120 and a VOID write the series with the verdict, once. A later look
   reads D_1..k again from the store and checks it against the stored sha (a mismatch is a moved series: VOID).
6. THE DEMOTION (`Night.demotions`, section 7.1): a PASS cell's post-pass sessions, read on the members active at the
   pass, every 20th: DEMOTED (sticky) on the rule; an engine move that touches judged days voids a pending cell and
   loses a pass (re-derived at the same k and bar), never gains one.
7. THE PERMIT FILE (`write_permits`, `PERMITS`): the receipt's sha, the clock, each unit's word (pending, report_only
   or its final word), THE POOL-ROUTE LIST and the hold list (every entry ever written, from the store: never
   removed), every registry lineage's pool cell and cluster id, and the eligible lineages after a PASS. IDS AND WORDS
   ONLY (`pool_rule.figure_free`). The job never deletes it.
8. THE REPORT (`REPORT`, operator-only): units by word (final words only), counts, waits and stalls, "X passes of J
   units; Y expected at zero edge". No interim word or figure.

A FAILURE OF THE HOUSE NEVER MARKS A CELL: a child that did not finish, a store under a lock, a run that does not
reproduce the record: nothing is written, and the next night reads the same D_1..k. THE STALL RULE (`STALL_NIGHTS`):
a cell whose look waited on the House on that many record nights under one engine id is STALLED (a House warning; it
is asked again each night). A pool-job failure is an ops alarm, never a stall cause of league/ops/stall.py. The
DEADLINE is forward_screen's (the earlier of the job's wall and the next pre-open, less `MARGIN_S`); quiet 09:00-17:30
New York on a session. THE STATED LIMITS OF P1 (scratch/pooled-screen/DEVIATIONS.log): a cell first judged after the
clock (a later lineage under rho_assign, or a cell below `M_MIN` that grows) is not clocked here: its members stay on
FWD1-R until a release that recomputes U_u, G6 and the floor-wide expected seats with the calibration's pinned code;
a later lineage with FWD1-R checkpoints read before its hold is released to FWD1-R for the same reason.

Standard library at import; numpy, league.equity and the swarm inside the functions that need them.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import os
import sqlite3
import time
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
#: THE DEADLINE (forward_screen's): no run past the earlier of the job's wall less `MARGIN_S` and the next pre-open less
#: `MARGIN_S` (a test holds `WALL_S` to the registry's).
WALL_S = 1500
MARGIN_S = FS.MARGIN_S
MIN_RUN_S = FS.MIN_RUN_S
#: A member enters as z = 0 throughout when more than this share of its days does not reproduce (section 2, step 1).
UNREPRODUCED_MAX = 0.10
#: The route words of `pool_members.route`.
ROUTES = ("pool", "fwd1", "sealed", "merged", "out", "new_cell", "final_unit")
EVENT_KINDS = ("pinned", "clock_wait", "sighted", "held", "released", "routed", "train", "decided", "waited",
               "stalled", "house", "look", "verdict", "lost", "demoted", "engine_switched", "joined", "unreproduced",
               "ineligible", "new_cell")
APPEND_ONLY_ERROR = "pool-screen.sqlite is append-only"

_TABLES = """
CREATE TABLE IF NOT EXISTS pool_pins (sha TEXT PRIMARY KEY, release TEXT NOT NULL, release_start REAL NOT NULL,
  before TEXT, night TEXT NOT NULL, clock TEXT NOT NULL, evidence TEXT NOT NULL, at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS pool_units (cell TEXT PRIMARY KEY, cls TEXT NOT NULL, grp TEXT NOT NULL, cluster TEXT NOT NULL,
  founders TEXT NOT NULL, clock TEXT NOT NULL, origin TEXT NOT NULL, refuted INTEGER NOT NULL, stage1 TEXT NOT NULL,
  u_point REAL NOT NULL,
  u_bound REAL NOT NULL, cap REAL NOT NULL, wall REAL NOT NULL, report_only INTEGER NOT NULL, fwd1_count INTEGER NOT NULL,
  at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS pool_members (lineage TEXT PRIMARY KEY, pid INTEGER, cell TEXT, route TEXT NOT NULL,
  joins TEXT, declared TEXT, assigned INTEGER NOT NULL, merged_into TEXT, infer_key TEXT, why TEXT, corr TEXT,
  at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS pool_routes (lineage TEXT PRIMARY KEY, cell TEXT, cluster TEXT, night TEXT NOT NULL,
  why TEXT NOT NULL, at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS pool_holds (lineage TEXT PRIMARY KEY, night TEXT NOT NULL, why TEXT NOT NULL,
  at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS pool_releases (lineage TEXT PRIMARY KEY, why TEXT NOT NULL, at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS pool_train (pid INTEGER NOT NULL, era INTEGER NOT NULL, days TEXT NOT NULL,
  arrays TEXT NOT NULL, sha TEXT NOT NULL, at REAL NOT NULL, PRIMARY KEY (pid, era)) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS pool_params (pid INTEGER PRIMARY KEY, symbols TEXT, mu TEXT, wbar TEXT, sigma REAL,
  g_bp REAL, exposure TEXT, mean_exposure REAL, grp TEXT, why TEXT, k_close INTEGER, k_sessions INTEGER,
  at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS pool_sigma (cell TEXT PRIMARY KEY, sigma_tilde REAL NOT NULL, at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS pool_market (era INTEGER PRIMARY KEY, days TEXT NOT NULL, arrays TEXT NOT NULL,
  sha TEXT NOT NULL, at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS pool_controls (pid INTEGER PRIMARY KEY, grp TEXT NOT NULL, symbols TEXT NOT NULL,
  mu TEXT NOT NULL, wbar TEXT NOT NULL, sigma REAL, at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS pool_fwd (pid INTEGER NOT NULL, day TEXT NOT NULL, engine INTEGER NOT NULL, row TEXT NOT NULL,
  at REAL NOT NULL, PRIMARY KEY (pid, day, engine)) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS pool_sessions (cell TEXT NOT NULL, day TEXT NOT NULL, engine INTEGER NOT NULL,
  counted INTEGER NOT NULL, active INTEGER NOT NULL, session INTEGER NOT NULL, at REAL NOT NULL,
  PRIMARY KEY (cell, day, engine)) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS pool_clusters (look TEXT NOT NULL, cluster TEXT NOT NULL, cells TEXT NOT NULL,
  u_point REAL NOT NULL, u_bound REAL NOT NULL, at REAL NOT NULL, PRIMARY KEY (look, cluster)) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS pool_floors (cluster TEXT NOT NULL, look TEXT NOT NULL, row TEXT NOT NULL, at REAL NOT NULL,
  PRIMARY KEY (cluster, look)) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS pool_boot (cluster TEXT NOT NULL, look TEXT NOT NULL, null_ TEXT NOT NULL, draw INTEGER NOT NULL,
  row TEXT NOT NULL, at REAL NOT NULL, PRIMARY KEY (cluster, look, null_, draw)) WITHOUT ROWID;
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
TABLES = ("pool_pins", "pool_units", "pool_members", "pool_routes", "pool_holds", "pool_releases", "pool_train",
          "pool_params", "pool_sigma", "pool_market", "pool_controls", "pool_fwd", "pool_sessions", "pool_clusters",
          "pool_floors", "pool_boot", "pool_checks", "pool_verdicts", "pool_post", "pool_demotions", "pool_runs",
          "pool_events")
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


def event(store: sqlite3.Connection, kind: str, *, at: float, cell: str | None = None, lineage: str | None = None,
          once: str | None = None, payload: Mapping[str, Any] | None = None) -> bool:
    """One `pool_events` row (ids, counts and words only); with `once` at most one a (kind, cell, lineage, once).
    Whether it was written. The caller commits."""
    if kind not in EVENT_KINDS:
        raise ValueError(f"no pool screen event kind {kind!r}")
    cursor = store.execute("INSERT OR IGNORE INTO pool_events(at, kind, cell, lineage, once, payload) VALUES (?,?,?,?,?,?)",
                           (float(at), kind, cell, lineage, once, _dumps(dict(payload or {}))))
    return cursor.rowcount == 1


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
class PoolRuns(FS.HouseRuns):
    """THE POOL'S OWN RUNNER (section 11 P1 item 2), a subclass of forward_screen's `HouseRuns` (whose runner is
    unchanged), in the job's own decider child: per Train era and for the forward run, the series' days, r, r15, w, b
    and per-symbol exposure and returns. Each method raises the child's or the data's failure (the House's: nothing
    is written) or `forward_screen.OwnFloorRefused` for the program's own."""

    def train_series(self, program: Any) -> list[dict[str, Any] | None]:
        """Each Train era's series (`config.TRAIN_ERA_SEGMENTS`, from the pools' third session, `screen.POOL_SKIP`;
        None for an era the program has no history in): {"days", "symbols", "r", "r15", "w", "b", "ws" (S x n), "R"
        (S x n), "sides", "k_close", "k_sessions"} from its k 1.0 and 1.5 runs (E1's runner in this job's child)."""
        import numpy as np

        from ..equity import bands as eq_bands
        from ..equity import config as econfig
        from ..equity import screen as S
        from ..equity.runner import Isolated
        from ..equity.store import EquityStore

        iso = Isolated(self._child(), self.root / "equity-daily", budget_seconds=self.budget())
        needs = iso._needs(program.code, program.params, program.key)
        store = EquityStore(self.root / "equity-daily")
        floor = eq_bands.seat_settings().k_floor
        out: list[dict[str, Any] | None] = []
        epoch = dt.date(1970, 1, 1)
        for first, last in econfig.TRAIN_ERA_SEGMENTS:
            bars = store.span(needs.symbols, first, last, history=needs.history)
            runs = []
            for k in (econfig.K_BASE, econfig.K_STRESS):
                iso.budget_seconds = self.budget()
                runs.append(iso._run(program.code, program.params, program.key, bars, k))
            statuses = [str(run.result.get("status")) for run in runs]
            if any(s == "no_data" for s in statuses):
                out.append(None)
                continue
            if any(s != "ok" for s in statuses):
                raise FS.OwnFloorRefused(f"a Train-era run ended {statuses}: its series is partial")
            universe = [str(s) for s in (runs[0].result.get("symbols") or needs.symbols)]
            try:
                base, stress = (S.series(run.result.get("lots") or [], run.bars, universe=universe,
                                         capital=FS._capital(run.result, econfig.SLEEVE_USD)) for run in runs)
                days = [(epoch + dt.timedelta(days=int(d))).isoformat() for d in base.days]
                lots = runs[0].result.get("lots") or []
                ws = P.lot_exposure(lots, days, universe)
                R = _returns(runs[0].bars, universe)
                sides = P.lot_sides(lots, days)
                k_close = eq_bands.close_days(lots, floor=floor)
                k_sessions = eq_bands.run_sessions(runs[0].result)
            except ValueError as exc:
                raise FS.OwnFloorRefused(f"its Train-era series cannot be read from its own runs ({str(exc)[:120]})") \
                    from None
            if len(base.r) != len(stress.r):
                raise FS.OwnFloorRefused("its two Train-era runs differ in their sessions")
            skip = S.POOL_SKIP
            out.append({"days": days[skip:], "symbols": universe, "r": base.r[skip:].tolist(),
                        "r15": stress.r[skip:].tolist(), "w": base.w[skip:].tolist(), "b": base.b[skip:].tolist(),
                        "ws": np.asarray(ws)[:, skip:].tolist(), "R": np.asarray(R)[:, skip:].tolist(),
                        "sides": np.asarray(sides)[skip:].tolist(), "k_close": int(k_close),
                        "k_sessions": int(k_sessions), "lots": [dict(lot) for lot in lots]})
        return out

    def forward_series(self, program: Any, *, settings: Mapping[str, Any] | None,
                       fdb: sqlite3.Connection | None = None) -> dict[str, Any]:
        """THE FORWARD RUN of a member (E3's `Shadow.slice` and its k 1.0 run, as `HouseRuns.forward_sides` reads it):
        {"symbols", "r": {day: r}, "ws": {day: [w_s]}, "R": {day: [R_s]}, "sides", "entries", "exits", "bars"}."""
        import numpy as np

        from ..equity import config as econfig
        from ..equity import ctx as eq_ctx
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
        universe = [str(s) for s in needs.symbols]
        lots = result.get("lots") or []
        ws = np.asarray(P.lot_exposure(lots, days, universe))
        R = np.asarray(_returns(bars, universe))
        sides = P.lot_sides(lots, days)
        entered = Counter(str(lot.get("entry_day"))[:10] for lot in lots)
        hashes = {day: forward_db.bars_hash(eq_ctx.inputs_from_bars(
            bars, int(bars.first) + i - 1, needs=needs, cash=0.0, equity=0.0, budget=0.0, caps={}, params={}))
            for i, day in enumerate(days)}
        return {"symbols": universe, "r": {d: float(v) for d, v in zip(days, series.r)},
                "ws": {d: ws[:, i].tolist() for i, d in enumerate(days)},
                "R": {d: R[:, i].tolist() for i, d in enumerate(days)},
                "sides": {d: float(sides[i]) for i, d in enumerate(days)},
                "entries": {d: int(entered.get(d, 0)) for d in days},
                "exits": {d: int(v) for d, v in zip(days, series.exits)}, "bars": hashes,
                "lots": [dict(lot) for lot in lots]}

    def market(self) -> list[dict[str, Any]]:
        """Each Train era's market series for the regime cells (SPY, the sector ETFs, TLT, GLD: cost-free close-to-close
        returns from the pools' third session; NaN where a symbol has no bar)."""
        import numpy as np

        from ..equity import config as econfig
        from ..equity import screen as S
        from ..equity.store import EquityStore

        from ..equity.store import MissingData

        store = EquityStore(self.root / "equity-daily")
        out = []
        epoch = dt.date(1970, 1, 1)
        for first, last in econfig.TRAIN_ERA_SEGMENTS:
            spy = store.span(["SPY"], first, last, history=1)
            days = [(epoch + dt.timedelta(days=int(d))).isoformat() for d in spy.days[int(spy.first):]]
            rows = {"SPY": np.asarray(_returns(spy, ["SPY"], nan=True))[0]}
            for sym in (*P.SECTOR_ETFS, "TLT", "GLD"):
                try:
                    bars = store.span([sym], first, last, history=1)       # a symbol the store lacks is NaN
                except MissingData:
                    rows[sym] = np.full(len(days), np.nan)
                    continue
                ret = np.asarray(_returns(bars, [sym], nan=True))[0]
                own = {(epoch + dt.timedelta(days=int(d))).isoformat(): float(v)
                       for d, v in zip(bars.days[int(bars.first):], ret)}
                rows[sym] = np.array([own.get(d, np.nan) for d in days])
            skip = S.POOL_SKIP
            out.append({"days": days[skip:], "spy": rows["SPY"][skip:].tolist(),
                        "sectors": [rows[s][skip:].tolist() for s in P.SECTOR_ETFS],
                        "tlt": rows["TLT"][skip:].tolist(), "gld": rows["GLD"][skip:].tolist()})
        return out

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
            ws = P.lot_exposure(lots0, days, symbols)
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
        ws = np.asarray(P.lot_exposure(lots, days, symbols))
        R = np.asarray(_returns(bars, symbols))
        return {"symbols": symbols, "ws": {d: ws[:, i].tolist() for i, d in enumerate(days)},
                "R": {d: R[:, i].tolist() for i, d in enumerate(days)}}


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
    a close is missing)."""
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


class Night:
    """One night of the pool (the module docstring): `store` (the pool's own, writable), `fdb` (the forward record,
    read-only), `receipt` (`pool_rule.Receipt`), `runs` (`PoolRuns` or a test's fake), `families` (the equity families
    by id), `swarm` (the swarm store, read-only, for the cards; None: no card read), `budget` (child seconds tonight),
    `deadline`."""

    def __init__(self, root: str | Path, store: sqlite3.Connection, fdb: sqlite3.Connection, *, receipt: P.Receipt,
                 runs: Any, families: Mapping[str, Mapping[str, Any]], swarm: Any = None, settings: Any = None,
                 budget: float = 600.0, clock: Callable[[], float] = time.time, deadline: float = float("inf"),
                 base: str | Path | None = None, release: str | Path | None = None):
        self.root = Path(root)
        self.store, self.fdb, self.receipt, self.runs = store, fdb, receipt, runs
        self.families, self.swarm, self.settings = families, swarm, settings
        self.budget, self.clock, self.deadline = float(budget), clock, float(deadline)
        self.base, self.release = base, release
        self.spent = 0.0
        self.tally: Counter = Counter()
        self.engine_now = forward_db.engine_now(fdb)
        self.night = record_night(fdb)
        self.registry = _registry(fdb)
        self._fwd1: dict[str, dict[str, Any]] | None = None
        self._fwd1_read = False
        self._z: dict[int, tuple[list[str], list[float]] | None] = {}

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

    def verdict(self, cell: str) -> dict[str, Any] | None:
        row = self.store.execute("SELECT * FROM pool_verdicts WHERE cell=?", (cell,)).fetchone()
        return None if row is None else dict(row)

    def word(self, cell: str) -> str:
        """A unit's word: its final verdict's (a lost or demoted pass: DEMOTED; an ineligible end: ineligible), else
        pending."""
        if self.store.execute("SELECT 1 FROM pool_demotions WHERE cell=?", (cell,)).fetchone() is not None:
            return "DEMOTED"
        v = self.verdict(cell)
        if v is None:
            return P.PENDING
        return P.INELIGIBLE if v["word"] == "INELIGIBLE" else str(v["word"])

    def final(self, cell: str) -> bool:
        """Whether a unit's looks are over (a final word, or an ineligible end): no lineage joins it."""
        return self.word(cell) in (*P.FINAL, P.INELIGIBLE)

    def params(self, pid: int) -> dict[str, Any] | None:
        row = self.store.execute("SELECT * FROM pool_params WHERE pid=?", (int(pid),)).fetchone()
        return None if row is None else dict(row)

    def train(self, pid: int) -> list[dict[str, Any] | None]:
        eras: dict[int, dict[str, Any]] = {}
        for r in self.store.execute("SELECT era, days, arrays FROM pool_train WHERE pid=? ORDER BY era", (int(pid),)):
            arrays = json.loads(r["arrays"])
            eras[int(r["era"])] = {"days": json.loads(r["days"]), **arrays}
        n = max(eras) + 1 if eras else 0
        return [eras.get(e) for e in range(max(n, 2))]

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

    # --------------------------------------------------------------------------------------------- 1. the clock
    def clock_row(self, now: float) -> dict[str, Any] | None:
        """THE CLOCK AND THE ROUTE LIST (the module docstring, 1): the pin's row, written once with the founding units,
        the founders' membership, the REFUTED verdicts and the POOL-route list in one transaction, on the job's first
        new record night after the release began; None while there is none (or FWD1's store cannot be read)."""
        held = self.pin_row()
        if held is not None:
            return held
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
        release_start = float(now if started is None else started)
        night, before = first_night(self.fdb, release_start)
        if night is None:
            self._ev("clock_wait", once=f"{before}", payload={"why": "no record night written since the release that "
                                                                     "carries the receipt began: the clock waits"})
            self.tally["clock_wait"] += 1
            return None
        facts = self.fwd1()
        if facts is None:
            self._ev("house", once=f"clock:{night}", payload={"why": "FWD1's store could not be read on the first "
                                                                     "night: the route list waits a night"})
            self.tally["house"] += 1
            return None
        from ..equity import schedule

        clock = schedule.next_session(dt.date.fromisoformat(night)).isoformat()
        rec = self.receipt
        at = self.clock()
        # each founding cluster's U_u at the FWD1-R checkpoint count its candidates read before the clock
        cluster_caps: dict[str, tuple[P.Caps, int]] = {}
        for cid, cl in rec.clusters.items():
            count = 0
            for cell in cl.cells:
                for lineage in rec.units[cell].founders:
                    row = facts.get(lineage)
                    if fwd1_case_n(row) or str((row or {}).get("status")) == "pass":
                        count = max(count, int((row or {}).get("k_read") or 0))
            u = rec.u_at(cid, count)
            caps = P.caps(1.0, 1.0) if u is None else P.caps(*u)
            cluster_caps[cid] = (caps, count)
        routes: dict[str, tuple[str, str, str]] = {}
        member_rows = []
        for lineage, f in sorted(rec.founders.items()):
            unit = rec.units.get(f.cell or "")
            row = facts.get(lineage)
            judged = isinstance(row, Mapping) and int(row.get("judged") or 0) == 1
            why = f.why
            if f.merged_into:
                route = "merged"
            elif f.why:
                route = "out"
            elif unit is None:
                route, why = ("fwd1" if judged else "sealed"), ("its cell is below M_MIN at the clock: it stays on "
                                                                "its per-program route")
            else:
                caps, _ = cluster_caps[unit.cluster]
                if P.on_pool_route(row, unit_judged=True, refuted=unit.refuted, report_only=caps.report_only):
                    route = "pool"
                    routes[lineage] = (unit.cell, unit.cluster, "a founder FWD1 judges as case N, with no FWD1-R pass")
                elif judged:
                    route = "fwd1"
                    why = ("its unit was refuted by stage 1" if unit.refuted else
                           "its cluster is report-only" if caps.report_only else
                           "an FWD1-R pass before the clock: a member, its FWD1-R ticket in U_u")
                else:
                    route, why = "sealed", "FWD1 does not judge it (a sealed pre-check, or a live row): evidence only"
            member_rows.append((lineage, f.pid, f.cell if unit is not None else None, route,
                                clock if unit is not None else None, f.cls, 0, f.merged_into, None, why, None, at))
        for lineage, f in sorted(rec.founders.items()):
            if f.merged_into and f.merged_into in routes:            # a merged copy follows its member's route
                cell, cid, _ = routes[f.merged_into]
                routes[lineage] = (cell, cid, f"merged into {f.merged_into}, which is on the POOL route")
        with self.store:
            self.store.execute("INSERT OR IGNORE INTO pool_pins(sha, release, release_start, before, night, clock, "
                               "evidence, at) VALUES (?,?,?,?,?,?,?,?)",
                               (rec.sha256, name, release_start, before, night, clock, evidence, at))
            for cell, unit in sorted(rec.units.items()):
                caps, count = cluster_caps[unit.cluster]
                self.store.execute(
                    "INSERT OR IGNORE INTO pool_units(cell, cls, grp, cluster, founders, clock, origin, refuted, stage1, "
                    "u_point, u_bound, cap, wall, report_only, fwd1_count, at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (cell, unit.cls, unit.group, unit.cluster, _dumps(list(unit.founders)), clock, "receipt",
                     int(unit.refuted), _dumps(dict(unit.stage1)), caps.u_point, caps.u_bound, caps.cap, caps.wall,
                     int(caps.report_only), count, at))
                if unit.refuted:
                    self.store.execute("INSERT OR IGNORE INTO pool_verdicts(cell, word, why, at) VALUES (?,?,?,?)",
                                       (cell, "REFUTED", "stage 1 refuted the unit on its seen-span Train runs", at))
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
                           "units": len(rec.units)})
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
                                                                  "FWD1-R seats until the House assigns it",
                                        self.clock()))
                    event(self.store, "held", at=self.clock(), lineage=lineage, once="held", payload={"pid": pid})
                held.add(lineage)
                self.tally["held"] += 1

    def _member(self, lineage: str, pid: int | None, *, cell: str | None, route: str, why: str | None,
                fam: Mapping[str, Any] | None, row: Mapping[str, Any] | None, assigned: bool = False,
                merged: str | None = None, joins: str | None = None, corr: Mapping[str, Any] | None = None) -> None:
        card = _card(self.swarm, (row or {}).get("family")) if row is not None else None
        with self.store:
            self.store.execute("INSERT OR IGNORE INTO pool_members(lineage, pid, cell, route, joins, declared, assigned, "
                               "merged_into, infer_key, why, corr, at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                               (lineage, pid, cell, route, joins, (card or {}).get("mechanism_class"), int(assigned),
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

    def train_z(self, pid: int) -> tuple[list[str], list[float]] | None:
        """A member's Train z (era-restart alpha over its pools / sigma_used at its own sigma), or None without its
        Train series."""
        import numpy as np

        if int(pid) in self._z:
            return self._z[int(pid)]
        prm = self.params(pid)
        if prm is None or prm.get("sigma") is None or prm.get("mu") is None:
            return None
        mu, wbar = np.array(json.loads(prm["mu"])), np.array(json.loads(prm["wbar"]))
        g = float(prm["g_bp"]) * 1e-4
        days: list[str] = []
        zs: list[float] = []
        for era in self.train(pid):
            if era is None:
                continue
            rg = np.asarray(era["r"]) - g * np.asarray(era["sides"])
            a = P.era_alpha(rg, np.asarray(era["r"]) - np.asarray(era["r15"]), np.asarray(era["ws"]),
                            np.asarray(era["R"]), mu, wbar)
            sigma = P.sigma_used(float(prm["sigma"]), None)
            days.extend(era["days"])
            zs.extend((a / sigma).tolist())
        out = (days, zs) if days else None
        self._z[int(pid)] = out
        return out

    def cell_D(self, cell: str) -> tuple[list[str], list[float]] | None:
        """A clocked cell's founders' Train D (the mean of their Train z each Train session), or None while a founder
        lacks its Train series."""
        unit = self.units().get(cell)
        if unit is None:
            return None
        series = []
        for lineage in json.loads(unit["founders"]):
            f = self.receipt.founders.get(lineage)
            z = None if f is None else self.train_z(f.pid)
            if z is None:
                return None
            series.append(z)
        return P.mean_series(series) if series else None

    def decide(self) -> None:
        """THE LATER LINEAGES' House decision (the module docstring, 2), once each one's Train series and its group's
        founders' exist."""
        facts = self.fwd1() or {}
        units = self.units()
        decided = {str(r[0]) for r in self.store.execute("SELECT lineage FROM pool_members")}
        for lineage, rows in self._candidate_rows():
            if lineage in decided:
                continue
            pid = P.member_pid(rows)
            if pid is None:
                continue
            prm = self.params(pid)
            if prm is None:
                continue                                  # its Train series first (`train_step`)
            row = next(r for r in rows if int(r["pid"]) == pid)
            fam = self.families.get(str(row["family"]))
            if prm.get("why"):
                self._member(lineage, pid, cell=None, route="out", why=str(prm["why"]), fam=fam, row=row)
                self._release(lineage, str(prm["why"]))
                continue
            why = P.excluded(panel=False, symbols=[], card=None, code="", mean_exposure=prm.get("mean_exposure"),
                             group_why=None if prm.get("grp") else "no base group holds more than 2/3 of its Train-era "
                                                                   "exposure")
            if why is not None:
                self._member(lineage, pid, cell=None, route="out", why=why, fam=fam, row=row)
                self._release(lineage, why)
                continue
            grp = str(prm["grp"])
            z = self.train_z(pid)
            if z is None:
                continue
            # THE COPY MERGE against every earlier member (founders and decided members) with a Train series
            earlier = []
            for other, f in self.receipt.founders.items():
                if f.why or f.merged_into or f.pid >= pid:
                    continue
                prog = self.program(f.pid)
                earlier.append((other, f.pid, self.train_z(f.pid), "" if prog is None else prog.program_sha))
            for m in self.store.execute("SELECT lineage, pid FROM pool_members WHERE cell IS NOT NULL AND merged_into IS "
                                        "NULL AND assigned=1"):
                if m["pid"] is None or int(m["pid"]) >= pid:
                    continue
                prog = self.program(int(m["pid"]))
                earlier.append((str(m["lineage"]), int(m["pid"]), self.train_z(int(m["pid"])),
                                "" if prog is None else prog.program_sha))
            me = self.program(pid)
            into = P.merge_copy(z, "" if me is None else me.program_sha, earlier)
            if into is not None:
                routes = self.routes()
                self._member(lineage, pid, cell=None, route="merged", why=f"merged into {into}", fam=fam, row=row,
                             merged=into)
                if into in routes:
                    self._route(lineage, str(routes[into]["cell"]), str(routes[into]["cluster"]),
                                f"merged into {into}, which is on the POOL route")
                else:
                    self._release(lineage, f"merged into {into}, which is not on the POOL route")
                continue
            # THE ASSIGNMENT among the clocked cells of its group
            cells = {}
            for cell, unit in units.items():
                if unit["grp"] != grp:
                    continue
                d = self.cell_D(cell)
                if d is None:
                    cells = None
                    break
                cells[cell] = d
            if cells is None:
                continue                                  # its group's founders' Train series first
            target, corrs = P.assign(z, cells, self.receipt.rho_assign)
            corr = {c: (None if v is None else round(v, 6)) for c, v in corrs.items()}
            if target is None:
                self._member(lineage, pid, cell=None, route="new_cell", fam=fam, row=row, corr=corr,
                             why="under rho_assign with every clocked cell of its group: it counts toward a new cell "
                                 "under its declared class (not clocked in P1: it stays on its per-program route)")
                self._release(lineage, "counts toward a new cell (not clocked in P1)")
                continue
            unit = units[target]
            if self.final(target):
                self._member(lineage, pid, cell=None, route="final_unit", fam=fam, row=row, corr=corr,
                             why=f"assigned to {target}, whose verdict is final: not a member, it stays on FWD1-R")
                self._release(lineage, f"assigned to {target}, whose verdict is final")
                continue
            fwd1 = facts.get(lineage)
            spend = fwd1 is not None and int(fwd1.get("k_read") or 0) > 0 and (
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
            else:
                self._member(lineage, pid, cell=target, route="sealed", fam=fam, row=row, assigned=True, corr=corr,
                             joins=str(unit["clock"]),
                             why="assigned to a pending unit; FWD1 does not judge it (a sealed pre-check): a member, "
                                 "evidence only")
                self._release(lineage, "a member that FWD1 does not judge: its sealed path, evidence only")

    def _held_at(self, lineage: str) -> float | None:
        row = self.store.execute("SELECT at FROM pool_holds WHERE lineage=?", (lineage,)).fetchone()
        return None if row is None else float(row[0])

    # --------------------------------------------------------------------------------------- 3. the Train series
    def needing_train(self) -> list[int]:
        """The pids whose Train series the House owes: founders of judged units first (pid order), then the later
        lineages that are not decided (pid order)."""
        have = {int(r[0]) for r in self.store.execute("SELECT pid FROM pool_params")}
        first = sorted({f.pid for cell, u in self.receipt.units.items() for lin in u.founders
                        for f in [self.receipt.founders[lin]]} - have)
        decided = {str(r[0]) for r in self.store.execute("SELECT lineage FROM pool_members")}
        later = []
        for lineage, rows in self._candidate_rows():
            if lineage in decided:
                continue
            pid = P.member_pid(rows)
            if pid is not None and pid not in have:
                later.append(pid)
        return first + sorted(set(later) - set(first))

    def train_step(self) -> None:
        """THE HOUSE'S TRAIN SERIES (the module docstring, 3), inside the night's budget."""
        for pid in self.needing_train():
            if self._over():
                self.tally["deferred"] += 1
                return
            program = self.program(pid)
            if program is None:
                continue
            try:
                eras = self._timed(lambda: self.runs.train_series(program))
            except FS.OwnFloorRefused as exc:         # the program's own: no Train series for good, stated
                self._freeze(pid, None, why=f"no Train series: {str(exc)[:160]}")
                continue
            except FS.Late:
                self.tally["deferred"] += 1
                return
            except Exception as exc:  # noqa: BLE001 - the House's: nothing written, asked again
                self.tally["house"] += 1
                self._ev("house", once=f"train:{pid}:{self.night}",
                         payload={"why": "a member's Train-era runs did not finish", "pid": pid,
                                  "error": type(exc).__name__})
                continue
            self._freeze(pid, eras)

    def _freeze(self, pid: int, eras: Sequence[Mapping[str, Any] | None] | None, *, why: str | None = None) -> None:
        """A member's Train series and its constants, written once (`pool_train`, `pool_params`): mu_s and wbar_s over
        its pools, sigma (era-restart alpha, the haircut of tonight), its House group, its total exposure by symbol, its
        mean total exposure and K's Train counts."""
        import numpy as np

        at = self.clock()
        g_bp = F.haircut_bp("ETF", FS._lotgaps(self.fdb).get("ETF", []))
        if eras is None or not any(e is not None for e in eras):
            with self.store:
                self.store.execute("INSERT OR IGNORE INTO pool_params(pid, why, g_bp, at) VALUES (?,?,?,?)",
                                   (int(pid), why or "no Train-era history", float(g_bp), at))
                event(self.store, "train", at=at, once=f"{pid}", payload={"pid": pid, "why": why or "no history"})
            return
        held = [e for e in eras if e is not None]
        symbols = list(held[0]["symbols"])
        ws = np.concatenate([np.asarray(e["ws"], dtype=np.float64) for e in held], axis=1)
        R = np.concatenate([np.asarray(e["R"], dtype=np.float64) for e in held], axis=1)
        mu = R.mean(axis=1)
        wbar = ws.mean(axis=1)
        g = float(g_bp) * 1e-4
        sigma = P.train_sigma([(np.asarray(e["r"]) - g * np.asarray(e["sides"]),
                                np.asarray(e["r"]) - np.asarray(e["r15"]), np.asarray(e["ws"]), np.asarray(e["R"]))
                               for e in held], mu, wbar)
        exposure = {s: float(np.abs(ws[i]).sum()) for i, s in enumerate(symbols)}
        grp, gwhy = P.group_of(exposure, symbols)
        mean_exposure = float(np.abs(ws).sum(axis=0).mean()) if ws.size else 0.0
        k_close = sum(int(e.get("k_close") or 0) for e in held)
        k_sessions = sum(int(e.get("k_sessions") or 0) for e in held)
        with self.store:
            for era, e in enumerate(eras):
                if e is None:
                    continue
                arrays = {k: e[k] for k in ("symbols", "r", "r15", "w", "b", "ws", "R", "sides")}
                text = _dumps(arrays)
                self.store.execute("INSERT OR IGNORE INTO pool_train(pid, era, days, arrays, sha, at) VALUES (?,?,?,?,?,?)",
                                   (int(pid), era, _dumps(list(e["days"])), text,
                                    hashlib.sha256(text.encode()).hexdigest(), at))
            self.store.execute(
                "INSERT OR IGNORE INTO pool_params(pid, symbols, mu, wbar, sigma, g_bp, exposure, mean_exposure, grp, why, "
                "k_close, k_sessions, at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (int(pid), _dumps(symbols), _dumps(mu.tolist()), _dumps(wbar.tolist()), sigma, float(g_bp),
                 _dumps(exposure), mean_exposure, grp,
                 "no Train-era sigma (fewer than two Train sessions)" if sigma is None else gwhy, k_close, k_sessions,
                 at))
            event(self.store, "train", at=at, once=f"{pid}", payload={"pid": pid, "group": grp, "why": gwhy})
        self.tally["train"] += 1

    def sigma_tilde(self, cell: str) -> float | None:
        """A cell's frozen sigma_tilde (its founders'), written once every founder has its sigma."""
        row = self.store.execute("SELECT sigma_tilde FROM pool_sigma WHERE cell=?", (cell,)).fetchone()
        if row is not None:
            return float(row[0])
        unit = self.units().get(cell)
        if unit is None:
            return None
        sigmas = []
        for lineage in json.loads(unit["founders"]):
            prm = self.params(self.receipt.founders[lineage].pid)
            if prm is None or prm.get("sigma") is None:
                return None
            sigmas.append(float(prm["sigma"]))
        tilde = P.sigma_tilde(sigmas)
        if tilde is None:
            return None
        with self.store:
            self.store.execute("INSERT OR IGNORE INTO pool_sigma(cell, sigma_tilde, at) VALUES (?,?,?)",
                               (cell, tilde, self.clock()))
        return tilde

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
        cluster's id is its parts' ids joined by "+"."""
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

    def u_of(self, cells: Sequence[str]) -> tuple[float, float]:
        """U_u of a cluster of these cells: its receipt cluster's at the clock, or, for a cluster joined at a look,
        the union bound over the receipt clusters it holds (`pool_rule.joined_u`: a cap only falls)."""
        units = self.units()
        parts: dict[str, tuple[float, float]] = {}
        for c in cells:
            u = units[c]
            parts[str(u["cluster"])] = (float(u["u_point"]), float(u["u_bound"]))
        values = [parts[k] for k in sorted(parts)]
        return values[0] if len(values) == 1 else P.joined_u(values)

    def effective_cluster(self, cell: str) -> tuple[str, list[str], tuple[float, float]]:
        """The cluster a cell is judged in now (`clusters_now`): (its id, its cells, its U_u (`u_of`))."""
        for cid, cells in self.clusters_now().items():
            if cell in cells:
                return cid, cells, self.u_of(cells)
        raise KeyError(cell)

    def retest(self, cell: str, look_key: str, members_at: Mapping[str, Sequence[Mapping[str, Any]]]) -> None:
        """THE CLUSTERS RE-TESTED at a look (section 1.4) on Train only, with the members then active (the looking
        cell's through its look, every other cell's as it stands): clusters the member rule joins are recorded
        (`pool_clusters`) from this look; their joint floor and U_u follow (`effective_cluster`), and a recorded pass of
        either is re-derived at the joint bar (`demotions`)."""
        current = self.clusters_now()
        payload: dict[str, dict[str, list[Any]]] = {}
        for cid, cells in current.items():
            payload[cid] = {}
            for c in cells:
                zs = []
                for m in members_at.get(c, self.cell_members(c)):
                    z = self.train_z(int(m["pid"]))
                    if z is None:
                        raise Wait("train", "a member's Train series is not written yet (the cluster re-test)")
                    zs.append(z)
                payload[cid][c] = zs
        for g in P.member_join(payload):
            if len(g) < 2:
                continue
            cells = sorted(set().union(*(set(current[cid]) for cid in g)))
            u = self.u_of(cells)
            name = "+".join(sorted(g))
            with self.store:
                self.store.execute("INSERT OR IGNORE INTO pool_clusters(look, cluster, cells, u_point, u_bound, at) "
                                   "VALUES (?,?,?,?,?,?)", (look_key, name, _dumps(cells), u[0], u[1], self.clock()))
                event(self.store, "joined", at=self.clock(), cell=cell, once=f"{look_key}:{name}",
                      payload={"clusters": sorted(g), "cells": cells})
            self.tally["joined"] += 1

    def floor_members(self, cells: Sequence[str], engine: int, through: Mapping[str, str]) -> list[P.FloorMember]:
        """The cluster's members as the own floor reads them (their Train series, constants and join offsets: the
        cell session each joined its cell at, through each cell's look)."""
        import numpy as np

        from ..equity import config as econfig

        out = []
        for c in cells:
            tilde = self.sigma_tilde(c)
            if tilde is None:
                raise Wait("train", "a founder's Train series is not written yet (the own floor)")
            sess = self.sessions(c, engine)
            cutoff = through.get(c)
            sess = [s for s in sess if cutoff is None or s <= cutoff]
            for m in self.cell_members(c):
                prm = self.params(int(m["pid"]))
                if prm is None or prm.get("mu") is None or prm.get("sigma") is None:
                    raise Wait("train", f"{m['lineage']}'s Train series is not written yet (the own floor)")
                counted = counted_by_day(self.fdb, int(m["pid"]), engine)
                join_day = min((d for d in counted if d >= m["joins"]), default=None)
                if join_day is None or (cutoff is not None and join_day > cutoff):
                    continue                              # not active by the look: not in the floor
                offset = sum(1 for s in sess if s < join_day)
                symbols = json.loads(prm["symbols"])
                hs = np.array([econfig.half_spread(s) for s in symbols])
                g = float(prm["g_bp"]) * 1e-4
                eras = []
                for era in self.train(int(m["pid"])):
                    if era is None:
                        eras.append(None)
                        continue
                    r = np.asarray(era["r"])
                    eras.append(P.Era(days=tuple(era["days"]), rg=r - g * np.asarray(era["sides"]),
                                      gap=r - np.asarray(era["r15"]), ws=np.asarray(era["ws"]), R=np.asarray(era["R"]),
                                      hs=hs))
                out.append(P.FloorMember(key=str(m["lineage"]), cell=c, join=offset,
                                         mu=np.array(json.loads(prm["mu"])), wbar=np.array(json.loads(prm["wbar"])),
                                         sigma=P.sigma_used(float(prm["sigma"]), tilde), g=g, eras=tuple(eras)))
        return out

    def markets(self) -> list[P.Market]:
        """The Train eras' market series (`pool_market`, written once from the House's store)."""
        import numpy as np

        rows = list(self.store.execute("SELECT era, days, arrays FROM pool_market ORDER BY era"))
        if not rows:
            if self._over():
                raise Wait("budget", "the night's budget is spent: the market series wait")
            try:
                found = self._timed(lambda: self.runs.market())
            except Exception as exc:  # noqa: BLE001 - the House's
                self._ev("house", once=f"market:{self.night}", payload={"why": "the Train eras' market series could not "
                                                                                "be read", "error": type(exc).__name__})
                raise Wait("house", "the Train eras' market series could not be read") from None
            with self.store:
                for era, m in enumerate(found):
                    text = _dumps({k: m[k] for k in ("spy", "sectors", "tlt", "gld")})
                    self.store.execute("INSERT OR IGNORE INTO pool_market(era, days, arrays, sha, at) VALUES (?,?,?,?,?)",
                                       (era, _dumps(list(m["days"])), text, hashlib.sha256(text.encode()).hexdigest(),
                                        self.clock()))
            rows = list(self.store.execute("SELECT era, days, arrays FROM pool_market ORDER BY era"))
        out = []
        for r in rows:
            arr = json.loads(r["arrays"])
            out.append(P.Market(days=tuple(json.loads(r["days"])), spy=np.array(arr["spy"], dtype=np.float64),
                                sectors=np.array(arr["sectors"], dtype=np.float64), tlt=np.array(arr["tlt"], dtype=np.float64),
                                gld=np.array(arr["gld"], dtype=np.float64)))
        return out

    def c_own(self, cid: str, cells: Sequence[str], look_key: str, engine: int, through: Mapping[str, str],
              caps: P.Caps) -> int | None:
        """THE OWN FLOOR of the cluster at a look (`pool_floors`, once a cluster and look; its bootstrap resamples
        spread over nights in `pool_boot`). Raises `Wait` while it cannot be finished tonight."""
        held = self.store.execute("SELECT row FROM pool_floors WHERE cluster=? AND look=?", (cid, look_key)).fetchone()
        if held is not None:
            return json.loads(held[0]).get("k_own")
        members = self.floor_members(cells, engine, through)
        markets = self.markets()
        aligned_members, aligned_markets = P.aligned(members, markets)
        axes = P.unit_axes(cells)
        cuts = self.receipt.regimes
        hists: dict[str, dict[int, Any]] = {}
        for null in P.NULLS:
            done = {int(r["draw"]): json.loads(r["row"]) for r in self.store.execute(
                "SELECT draw, row FROM pool_boot WHERE cluster=? AND look=? AND null_=?", (cid, look_key, null))}
            todo = [d for d in range(P.BOOT_RESAMPLES) if d not in done]
            while todo:
                if self._over():
                    raise Wait("budget", "the own floor's bootstrap resamples continue the next night")
                chunk, todo = todo[:50], todo[50:]
                found = self._timed(lambda: P.bootstrap_histograms(aligned_members, aligned_markets, null,
                                                                    unit=f"{cid}@{look_key}", draws=chunk, cuts=cuts,
                                                                    axes=axes))
                with self.store:
                    for draw, row in found.items():
                        self.store.execute("INSERT OR IGNORE INTO pool_boot(cluster, look, null_, draw, row, at) "
                                           "VALUES (?,?,?,?,?,?)", (cid, look_key, null, int(draw), _dumps(row),
                                                                    self.clock()))
                done.update(found)
            hists[null] = done
        units = self.units()
        m_by_cell = Counter(m.cell for m in members)
        matched = []
        for c in cells:
            k = self.receipt.matched(str(units[c]["grp"]), str(units[c]["cls"]), m_by_cell.get(c, 0))
            matched.append(k)
        if any(k is None for k in matched):
            raise Wait("receipt", "the receipt holds no matched stand-in family's N1 floor for a cell of the cluster")
        matched_k = max(matched)                                                  # type: ignore[type-var]
        result = self._timed(lambda: P.own_floor(members, markets, unit=f"{cid}@{look_key}",
                                                 floor_def=self.receipt.floor, caps_=caps, cuts=cuts,
                                                 matched_k=matched_k, hists=hists))
        if result["k_own"] is None and "resamples" in str(result.get("why")):
            raise Wait("budget", str(result["why"]))
        with self.store:
            self.store.execute("INSERT OR IGNORE INTO pool_floors(cluster, look, row, at) VALUES (?,?,?,?)",
                               (cid, look_key, _dumps({"k_own": result["k_own"], "why": result["why"],
                                                       "nulls": result["nulls"], "matched": matched_k}), self.clock()))
        return result["k_own"]

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
            cid, cells, u = self.effective_cluster(cell)
            members_at = {cell: members}
            self.retest(cell, look_key, members_at)
            cid, cells, u = self.effective_cluster(cell)
            caps = P.caps(*u)
            through = {cell: head[-1]}
            k_own = self.c_own(cid, cells, look_key, engine, through, caps)
            ku = P.k_used(self.receipt.c_G, self.receipt.margin, k_own)
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
                ku = P.k_used(self.receipt.c_G, self.receipt.margin, json.loads(held[0]).get("k_own"))
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
    def run(self, now: float) -> dict[str, Any]:
        pin = self.clock_row(now)
        if pin is None:
            return dict(self.tally)
        self.sight(pin)
        self.train_step()
        self.decide()
        for cell in sorted(self.units()):
            if self.verdict(cell) is not None and self.verdict(cell)["word"] != "PASS":
                continue
            try:
                self.classify(cell)
                self.look(cell)
                self.demotions(cell)
            except sqlite3.Error:
                self.tally["house"] += 1
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


#: The words after which a unit's looks are over (its verdict is final, or it ended ineligible): its lineages are
#: shown again in FWD1's report and the BH/BY meter.
OVER = (*P.FINAL, P.INELIGIBLE)


def withheld(root: str | Path, settings: Mapping[str, Any] | None) -> tuple[frozenset[str], bool]:
    """THE OPERATOR VIEWS' WITHHOLDING (section 8; 11 P1 item 5): (the lineages on the permit file's POOL-route or hold
    list whose unit's verdict is not final (a held lineage has no unit yet), False). FAIL CLOSED: (frozenset(), True),
    "withhold every ETF lineage", when the file cannot be read or is not the job's shape, or is missing while
    `elane.pool.mode` is not "off" (`pool_on`). league/ops/forward_report.py keeps its own copy (release E3's seal:
    it imports no pool module); a test holds the two equal."""
    path = Path(root) / PERMITS
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return frozenset(), pool_on(settings)
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
    """Every unit's cluster and word: its final verdict's (a lost or demoted pass DEMOTED; an ineligible end
    "ineligible"), "report_only" for a report-only cluster's unit (its verdict goes to the operator's report alone),
    else pending."""
    demoted = {str(r[0]) for r in store.execute("SELECT cell FROM pool_demotions")}
    verdicts = {str(r["cell"]): str(r["word"]) for r in store.execute("SELECT cell, word FROM pool_verdicts")}
    out = {}
    for u in store.execute("SELECT cell, cluster, report_only FROM pool_units ORDER BY cell"):
        cell = str(u["cell"])
        if int(u["report_only"]):
            word = P.REPORT_ONLY
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
                fwd1: Mapping[str, Mapping[str, Any]] | None = None) -> dict[str, Any]:
    """THE PERMIT FILE's document (the module docstring, 7): ids and words only."""
    routes: dict[str, Any] = {}
    holds: list[str] = []
    units: dict[str, Any] = {}
    lineages: dict[str, Any] = {}
    clock = None
    sha = None
    if store is not None:
        for r in store.execute("SELECT lineage, cell, cluster FROM pool_routes ORDER BY lineage"):
            routes[str(r["lineage"])] = {"cell": r["cell"], "cluster": r["cluster"]}
        holds = held_lineages(store)
        units = unit_words(store)
        pin = store.execute("SELECT sha, clock FROM pool_pins ORDER BY at LIMIT 1").fetchone()
        if pin is not None:
            clock, sha = str(pin["clock"]), str(pin["sha"])
        for r in store.execute("SELECT lineage, cell FROM pool_members ORDER BY lineage"):
            cell = r["cell"]
            lineages[str(r["lineage"])] = {"cell": cell, "cluster": None if cell is None else
                                           (units.get(str(cell)) or {}).get("cluster")}
    if fdb is not None:
        for lineage in sorted(_registry(fdb)):
            lineages.setdefault(lineage, {"cell": None, "cluster": None})
    eligible = eligible_rows(store, fdb, fwd1) if store is not None and fdb is not None else []
    doc = {"version": PERMITS_VERSION, "screen": P.SCREEN, "receipt": sha or (None if receipt is None else receipt.sha256),
           "clock": clock, "at": _iso(at), "routes": routes, "holds": holds, "units": units, "lineages": lineages,
           "eligible": eligible}
    if why:
        doc["why"] = why
    return doc


def write_permits(root: str | Path, store: sqlite3.Connection | None, *, receipt: P.Receipt | None, at: float,
                  fdb: sqlite3.Connection | None = None, why: str | None = None) -> Path:
    """THE PERMIT FILE, atomically, 0600 (`permits_doc`). Refused (ValueError) when it would carry a figure."""
    from .context import write_json

    fwd1 = fwd1_facts(root, fdb) if fdb is not None else None
    doc = permits_doc(store, receipt=receipt, at=at, fdb=fdb, why=why, fwd1=fwd1)
    problems = P.figure_free(doc)
    if problems:
        raise ValueError(f"the pool's permit file would carry a figure at {problems[:3]}")
    return write_json(Path(root) / PERMITS, doc)


def report(store: sqlite3.Connection, *, receipt: P.Receipt | None) -> dict[str, Any]:
    """THE OPERATOR'S REPORT (the module docstring, 8): no interim word or figure."""
    words = unit_words(store)
    final = {c: w for c, w in words.items() if w["word"] in P.FINAL}
    report_words = {str(r["cell"]): (str(r["word"]) if str(r["word"]) != "INELIGIBLE" else P.INELIGIBLE)
                    for r in store.execute("SELECT cell, word FROM pool_verdicts")}
    read = []
    for r in store.execute("SELECT cell, MAX(k) AS k FROM pool_checks GROUP BY cell"):
        cid = str(store.execute("SELECT cluster FROM pool_units WHERE cell=?", (str(r["cell"]),)).fetchone()[0])
        read.append((cid, int(r["k"])))
    expected = P.expected_passes(read, receipt) if receipt is not None else None
    stalled = [{"cell": r["cell"], "cause": json.loads(r["payload"]).get("cause")} for r in store.execute(
        "SELECT cell, payload FROM pool_events WHERE kind='stalled' ORDER BY seq")]
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
            "stalled": stalled}


# --------------------------------------------------------------------------------------------------------- the job
def night(root: str | Path, *, receipt: P.Receipt, settings: Mapping[str, Any] | None, now: float,
          base: str | Path | None = None, release: str | Path | None = None, runs: Any = None,
          families: Mapping[str, Mapping[str, Any]] | None = None, swarm: Any = None,
          clock: Callable[[], float] = time.time, deadline: float = float("inf")) -> dict[str, Any]:
    """One night over the state root (the module docstring): skipped when this record night already ran; else the
    night, the permit file and the report, and the run's own `pool_runs` row. The receipt of counts only."""
    root = Path(root)
    c = cfg(settings)
    began = clock()
    store = open_store(root)
    fdb = forward_db.open_db(root, readonly=True)
    fdb.row_factory = sqlite3.Row
    own_runs = runs is None
    opened = None
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
                      budget=float(c["cpu_seconds_night"]), clock=clock, deadline=deadline, base=base, release=release)
        tally = judge.run(now)
        write_permits(root, store, receipt=receipt, at=clock(), fdb=fdb)
        from .context import write_json

        write_json(root / REPORT, report(store, receipt=receipt))
        with store:
            store.execute("INSERT INTO pool_runs(night, started, finished, seconds, at) VALUES (?,?,?,?,?)",
                          (tonight, float(began), float(clock()), round(judge.spent, 3), float(clock())))
        return {**{k: int(v) for k, v in tally.items()}, "seconds": round(judge.spent, 3)}
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


def keep_permits(root: Path, receipt: P.Receipt | None, why: str, now: float) -> None:
    """The permit file written from what the store holds (no judging): with no pin, no receipt or no record, so the
    swarm reads a file of the job's and every POOL-route entry ever written stays listed."""
    store = open_store(root) if (root / DB).exists() else None
    fdb = None
    try:
        if (root / forward_db.DB).exists():
            try:
                fdb = forward_db.open_db(root, readonly=True)
                fdb.row_factory = sqlite3.Row
            except sqlite3.Error:
                fdb = None
        write_permits(root, store, receipt=receipt, at=now, fdb=fdb, why=why)
    finally:
        if store is not None:
            store.close()
        if fdb is not None:
            fdb.close()


def run(ctx: Any) -> dict[str, Any]:
    """THE JOB (league/ops/registry.py, after `forward_shadow`, listed after `forward_screen`): skipped with its switch
    off (the permit file kept), inside 09:00-17:30 New York on a session, too near the next pre-open; with no pin, no
    receipt or no forward record it writes the permit file from its store and judges nothing; else `night`."""
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
    receipt, why = P.rule()
    if receipt is None:
        keep_permits(root, None, f"no POOL1 receipt is pinned: {why}", float(now))
        return {"status": "skipped", "why": f"nothing is judged: {why}"}
    if forward_db.mode(settings) == "off" or not (root / forward_db.DB).exists():
        keep_permits(root, receipt, "no forward record to judge", float(now))
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
    return receipt_


__all__ = ["JOB", "DB", "PERMITS", "PERMITS_VERSION", "REPORT", "MODES", "SEATS", "DEFAULTS", "BOUNDS", "STALL_NIGHTS",
           "WALL_S", "MARGIN_S", "UNREPRODUCED_MAX", "ROUTES", "EVENT_KINDS", "TABLES", "SCHEMA", "cfg", "open_store",
           "event", "fwd1_facts", "fwd1_case_n", "record_night", "first_night", "PoolRuns", "Wait", "Night", "pool_on",
           "OVER", "withheld", "unit_words", "held_lineages", "eligible_rows", "permits_doc", "write_permits", "report",
           "night", "keep_permits", "run"]
