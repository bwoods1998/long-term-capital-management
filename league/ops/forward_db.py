"""THE FORWARD RECORD's store (release E3, "record and measure"): its schema, hash chain, shared types and settings.

Owner: A (league/ops/E3_INTERFACES.md). Protected (league/ops/ is FORBIDDEN to every role). E3 records clean evidence
and measures it: it moves no money, gates nothing, shows no generator anything new and writes no verdict. This module
is the one home of `<state>/forward.sqlite` (0600, WAL; House only; never committed): every E3 ops job opens the store
through `open_db` and writes its own tables (`WRITERS`), and the swarm process never opens it (the seal by process:
league/swarm, league/equity, league/live and league/gym import no E3 ops module and never name the store or one of its
tables; league/tests/test_e3_seal_imports.py).

THE STORE (`SCHEMA`; each table's columns are commented there):
- `fwd_registry`: every equity version judged on the Train bar, passed or failed, each seed, each live instance and
  the skill-free controls: its code frozen, the row hash-chained (`HASHED`, `row_hash`, `append_registry`,
  `verify_chain`; `GENESIS` before the first row). The forward route and its alpha are IN the hashed row (`route`,
  `alpha_f`: `E3_ROUTE`, `E3_ALPHA_F` on every program row of E3; "none", "0" on a control), so no forward outcome that
  exists before a forward screen is pinned can be given a larger alpha (D2).
- `fwd_tags`: facts learned later (`TAGS`); ops only, never to a generator.
- `fwd_days`, `fwd_checks`, `fwd_runs`: the nightly recompute's daily rows, its checkpoints at `CHECKPOINTS` counted
  days (then every `CHECKPOINT_EVERY`), and one row a night (league/ops/forward_shadow.py).
- `fwd_cey`, `fwd_meter`, `fwd_groups`: the day's meters (league/ops/forward_report.py).
- `fwd_ll`, `fwd_fillgap`, `fwd_lotgap`, `fwd_twins`, `fwd_part`: the live-like re-price, the timing table, the fill gap
  of each closed live lot, live and shadow intent agreement and participation (league/ops/forward_twins.py).
- `fwd_events`: the forward log (`EVENT_KINDS`), through `event`; `fwd_engines`: the engine labels, through `engine_id`;
  `fwd_kv`: the one table that can be overwritten (`KV_KEYS`).

APPEND-ONLY: a trigger aborts UPDATE and DELETE on every table but `fwd_kv` (`APPEND_ONLY`). The first value written
for a key stands; a later different value is an event, never an overwrite. AN EVENT IS WRITTEN ONCE: every event that
restates a standing fact goes through `event(..., once=<key>)` (`ONCE_KINDS`), so none repeats night after night for
one cause. A FAILURE OF THE HOUSE NEVER MARKS A PROGRAM: a decider that cannot start, a store being rewritten, a
missing bar or minute end nobody's forward record and tag nobody; they are events and alarms.

TIMES AND DAYS: days are ISO `YYYY-MM-DD` New York session days; times are epoch seconds UTC (REAL) here and ISO text
(one-second resolution) in the swarm store. Calendar questions go to `league.equity.schedule` (`moments`, which is
None for a day that is not a session, `next_session`, `previous_session`, `is_session`) and `store.nyse_sessions`,
never to a literal date. Returns, exposures and statistics are float64: research figures on the Gym sleeve E0
(`config.SLEEVE_USD`), never money. Every statistic is summed with `math.fsum` (the built-in `sum` is not exact on
Python 3.11; CI runs 3.11 and 3.14).

FORWARD DAYS (D1, D2): `t0()` = `schedule.next_session(config.LOOK_CAP)`; a forward day is a session d with `t0() <= d
<=` the store's `fetched_through`. A program's window starts at `first_day(first_close(created_at))`: it first decides
at the close of `first_close` (the earliest session whose close is after its code existed, never before the look cap)
and has no fill, mark or P&L before `first_day`.

THE ENGINE LABEL (`fwd_engine`): `EQUITY_ENGINE_VERSION + "+" + evaluator.equity_fingerprint()[:12] + "+" +
FWD_SERIES`. A forward row is computed under the whole equity evidence identity, so a change to any evidence module
opens a NEW labelled series; the rows hold the label's small integer (`engine_id`).

THE FORWARD SCREEN'S SHAPE, pinned before any forward day exists (`FGS`, `FGS_SHA`): written once to `fwd_kv` at the
store's creation, with one `prereg` event. E3 computes no verdict; it is the rule a later release may apply to E3-era
rows, at alpha_f 0.03 only.

THE BARS HASH (`bars_hash`; found after the spec, binding): the vendor rounds adjustment=all prices to cents, so the
as-of prices a live decision read and the ones a later store gives are not always byte-identical, and a shadow
decision can differ from the live one for that cause alone. The forward shadow records the bars hash each shadow
decision used (`fwd_days.bars`), the twins record the shadow's and the live decision's (`fwd_twins.shadow_bars`,
`live_bars`), and an intent disagreement is DATA: counted, with its `cause` (`CAUSES`) when the bars differ, never an
error. A14's pre-registered rule (95% of the counted sessions) is not changed by it.

SETTINGS (`cfg`, `mode`): policy.json `elane.forward.*`, swarm.json over it (`DEFAULTS`, `BOUNDS`); a malformed value
is its code default and an unreadable block is "off". Changing a constant of this module is a captain's release with
its cost stated, never a setting.

Standard library and numpy only (numpy inside functions).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from ..equity import results

DB = "forward.sqlite"
#: `prev_hash` of the registry's first row.
GENESIS = hashlib.sha256(b"ltcm-forward-registry-1").hexdigest()
#: `elane.forward.mode`: "record" is the only mode above "off" in E3 (a later release adds "rank" and "route").
MODES = ("off", "record")
#: `fwd_registry.reason`.
REASONS = ("train_pass", "train_fail", "seed", "live", "control")
#: `fwd_registry.lane`.
LANES = ("beta", "equity", "control")

# ------------------------------------------------------------------------------------------- pre-registered constants
#: A checkpoint row is written at these counts of counted days, then every `CHECKPOINT_EVERY` (D4).
CHECKPOINTS = (20, 60, 120, 250)
CHECKPOINT_EVERY = 250
#: The series tag in the engine label (`fwd_engine`).
FWD_SERIES = "fwd-1"
#: The live-like fill's version (D10: the VWAP of the first whole minute at or after the send).
FILL_VERSION = "livelike-1"
#: A stored day whose r or w differs from tonight's recompute by more than this is `restated`.
TOL = 1e-6
#: N_eff's window in forward days, the fewest sessions a member needs, and "provisional" below this (D6).
NEFF_WINDOW = 60
NEFF_MIN_DAYS = 10
NEFF_PROVISIONAL = 20
#: The BH/BY meter's q (D8).
Q = 0.10
#: A pair's reads are taken on its 60th, 120th and 250th usable session; a session is usable with this many a side (D9).
RC_READS = (60, 120, 250)
RC_MIN_GROUP = 5
#: Nights running before a `run_failed` program is tagged suspect, and a `run_disqualified` one is stopped.
SUSPECT_NIGHTS = 3
DQ_NIGHTS = 3
#: A14 as coded (D13): the size of the mean fill gap in bp a side, either way, and the share of sessions agreeing.
A14_GAP_BP = 15.0
A14_AGREE = 0.95
#: The forward route and alpha every program row of E3 carries in its hashed row (D2); a control carries the second pair.
E3_ROUTE = "S2"
E3_ALPHA_F = "0.03"
CONTROL_ROUTE = "none"
CONTROL_ALPHA_F = "0"

#: THE FORWARD SCREEN'S SHAPE (the module docstring). A receipt that differs from it in any field judges only days
#: after its own pin; E3-era rows are judged at alpha_f 0.03 on the checkpoint of record (D4).
FGS: dict[str, Any] = {
    "version": "fgs-prereg-1", "stat": "t_r over the first n counted days", "n": [20, 60, 120, 250], "then_every": 250,
    "pass": "t_r >= c_F and sum_r > 0 and sum_r15 > 0", "row": "the first fwd_checks row written for (pid, n)",
    "null": "N0", "block_sessions": 21, "worlds": 20000, "pools": ["IND22", "IND1622"],
    "c_F": "the smallest c whose pass rate at ANY of the four checkpoints under the null is <= alpha_f, the maximum "
           "over the pools",
    "alpha_e3_rows": "0.03", "alpha_fresh_route_F": "0.12"}
FGS_SHA = hashlib.sha256(results.canonical(FGS).encode()).hexdigest()

#: The registry columns the chain hashes (`row_hash`), in this order; `code` enters through its own sha256.
HASHED = ("pid", "key", "family", "version", "lane", "reason", "ugroup", "lineage", "program_sha", "run_sha", "params",
          "needs", "author", "created_at", "evidence", "first_close", "first_day", "registered_at", "route", "alpha_f")

# ------------------------------------------------------------------------------------------------------------ settings
#: `elane.forward.*` (policy.json ships "record"; the code default is "off"). `stop_after_sessions`: reasons train_pass,
#: seed and live; `stop_fail_after_sessions`: reason train_fail; both count STORED days of any status. `fill_minutes`
#: False: no minute fetch, no `fwd_fillgap`, no `fwd_ll`, no `no_minute` event.
DEFAULTS: dict[str, Any] = {"mode": "off", "controls_per_group": 50, "cpu_seconds_night": 1800, "run_budget_seconds": 120,
                            "stop_after_sessions": 500, "stop_fail_after_sessions": 250, "neff_max_members": 1500,
                            "fill_minutes": True, "twins": True}
BOUNDS: dict[str, tuple[float, float]] = {"controls_per_group": (0, 50), "cpu_seconds_night": (60, 2400),
                                          "run_budget_seconds": (10, 600), "stop_after_sessions": (20, 2000),
                                          "stop_fail_after_sessions": (20, 2000), "neff_max_members": (50, 3000)}

# -------------------------------------------------------------------------------------------------------------- vocabulary
#: `fwd_tags.tag`.
TAGS = ("review_pass", "review_fail", "try", "try_entered", "look_pass", "look_fail", "live", "stopped", "resumed",
        "suspect")
#: `fwd_events.kind` -> the package that writes it. `live_bars` (D) holds the bars hash of a live decision, taken the
#: night of the decision (THE BARS HASH: the book's adjusted rows are fetched again at the next session's decide).
EVENT_KINDS: dict[str, str] = {
    "prereg": "A", "registered": "A", "register_skipped": "A", "stopped": "A", "suspect": "A", "resumed": "A",
    "identity_moved": "A",
    "night_failed": "B", "engine_moved": "B", "run_failed": "B", "data_failed": "B", "run_disqualified": "B",
    "restated": "B", "budget_hit": "B", "audit_mismatch": "B", "chain_ok": "B", "chain_broken": "B",
    "no_minute": "D", "twin_unregistered": "D", "twin_sha_mismatch": "D", "twin_interrupted": "D", "live_bars": "D"}
#: The kinds written through `event(..., once=<key>)`: a second call for the same kind, pid, day and key writes nothing.
ONCE_KINDS = ("prereg", "register_skipped", "identity_moved", "engine_moved", "night_failed", "run_failed", "data_failed",
              "run_disqualified", "restated", "budget_hit", "audit_mismatch", "no_minute", "twin_unregistered",
              "twin_sha_mismatch", "twin_interrupted", "live_bars")
#: `fwd_kv` keys: the equity fingerprint last seen; `FGS_SHA` (written once through `kv_first`); the swarm event cursor.
KV_KEYS = ("equity_sha", "fgs_prereg", "scored_seq")
#: `fwd_twins.cause` of a session the live and the shadow intents disagree on (THE BARS HASH): "bars" when both bars
#: hashes are known and differ, "program" when they are equal, "unknown" when the live decision's is not known.
CAUSES = ("bars", "program", "unknown")
#: The hex characters of a bars hash (64 bits: about 17 bytes a `fwd_days` row).
BARS_HEX = 16

# ------------------------------------------------------------------------------------------------------------------ DDL
TABLES = ("fwd_kv", "fwd_engines", "fwd_registry", "fwd_tags", "fwd_days", "fwd_ll", "fwd_checks", "fwd_events",
          "fwd_runs", "fwd_cey", "fwd_meter", "fwd_groups", "fwd_fillgap", "fwd_lotgap", "fwd_twins", "fwd_part")
#: Every table but `fwd_kv`: UPDATE and DELETE abort.
APPEND_ONLY = tuple(t for t in TABLES if t != "fwd_kv")
#: table -> the package whose code writes it ("all": through `event` and `engine_id`).
WRITERS: dict[str, str] = {
    "fwd_kv": "A", "fwd_registry": "A", "fwd_tags": "A", "fwd_days": "B", "fwd_checks": "B", "fwd_runs": "B",
    "fwd_cey": "C", "fwd_meter": "C", "fwd_groups": "C", "fwd_ll": "D", "fwd_fillgap": "D", "fwd_lotgap": "D",
    "fwd_twins": "D", "fwd_part": "D", "fwd_events": "all", "fwd_engines": "all"}
APPEND_ONLY_ERROR = "forward.sqlite is append-only"

_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS fwd_kv (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS fwd_engines (                -- the engine labels (`fwd_engine`); the rows hold the small id
  id INTEGER PRIMARY KEY AUTOINCREMENT, label TEXT UNIQUE NOT NULL, at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS fwd_registry (
  pid INTEGER PRIMARY KEY, key TEXT UNIQUE NOT NULL,   -- <family>@<version> | control:<group>:<n>
  family TEXT, version INTEGER, lane TEXT NOT NULL,     -- beta | equity | control
  reason TEXT NOT NULL,                                 -- train_pass | train_fail | seed | live | control
  ugroup TEXT NOT NULL,                                 -- elane_train.symbols_group(NEEDS symbols); a control's own group
  lineage TEXT NOT NULL,                                -- elane.lineage_key(lane, families.lineage); a control's own key
  code TEXT NOT NULL, params TEXT NOT NULL, needs TEXT NOT NULL,   -- program text; canonical JSON (results.canonical)
  program_sha TEXT NOT NULL, run_sha TEXT NOT NULL,     -- sha256(code); gate.run_sha(version)
  author TEXT NOT NULL DEFAULT '',                      -- versions.author (ops only)
  created_at REAL NOT NULL, evidence TEXT NOT NULL,     -- "event:<seq>" | "registry"
  first_close TEXT NOT NULL, first_day TEXT NOT NULL, registered_at REAL NOT NULL,
  route TEXT NOT NULL, alpha_f TEXT NOT NULL,           -- D2: "S2", "0.03" on every program row of E3; "none", "0" a control
  prev_hash TEXT NOT NULL, row_hash TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS fwd_tags (                   -- facts learned later; ops only, never to a generator
  pid INTEGER NOT NULL, tag TEXT NOT NULL, value TEXT NOT NULL DEFAULT '', at REAL NOT NULL,
  PRIMARY KEY (pid, tag, value));  -- review_pass | review_fail | try | try_entered | look_pass | look_fail | live |
                                   -- stopped | resumed | suspect
CREATE TABLE IF NOT EXISTS fwd_days (
  pid INTEGER NOT NULL, day TEXT NOT NULL, engine INTEGER NOT NULL,
  r REAL NOT NULL, w REAL NOT NULL, b REAL NOT NULL,    -- net return on E0, exposure, benchmark return (D3)
  r15 REAL, r0 REAL,                                    -- the k 1.5 return; a CONTROL's cost-free return (D5), else NULL
  entries INTEGER NOT NULL, exits INTEGER NOT NULL,
  status TEXT NOT NULL,                                 -- ok | disqualified
  at REAL NOT NULL,
  bars TEXT,                                            -- THE BARS HASH of the decision this day's orders came from (the
                                                        -- close of the session before it); a control reads no bar: NULL
  PRIMARY KEY (pid, day, engine)) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS fwd_ll (                     -- the live-like re-price of the same day (D10)
  pid INTEGER NOT NULL, day TEXT NOT NULL, engine INTEGER NOT NULL, r_ll REAL NOT NULL, at REAL NOT NULL,
  PRIMARY KEY (pid, day, engine)) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS fwd_checks (                 -- recorded, never a verdict (D4)
  pid INTEGER NOT NULL, n INTEGER NOT NULL, day TEXT NOT NULL, engine INTEGER NOT NULL,
  t_r REAL, sum_r REAL NOT NULL, sum_r15 REAL, t_x REAL, mean_w REAL NOT NULL, p_x REAL,
  t_x0 REAL, p_x0 REAL,                                 -- a CONTROL's cost-free excess (D5, D8), else NULL
  final INTEGER NOT NULL DEFAULT 0,                     -- 1: written when the program stopped off the checkpoint grid
  at REAL NOT NULL, PRIMARY KEY (pid, n, engine)) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS fwd_events (                 -- the forward log and its marks (EVENT_KINDS)
  seq INTEGER PRIMARY KEY AUTOINCREMENT, at REAL NOT NULL, kind TEXT NOT NULL, pid INTEGER, day TEXT,
  payload TEXT NOT NULL DEFAULT '{}');
CREATE INDEX IF NOT EXISTS fwd_events_kind ON fwd_events(kind, pid, day);
CREATE TABLE IF NOT EXISTS fwd_runs (                   -- one row when a NIGHT ends (a run past its preflight)
  run INTEGER PRIMARY KEY AUTOINCREMENT, job TEXT NOT NULL, through TEXT, engine INTEGER, started REAL NOT NULL,
  finished REAL NOT NULL, seconds REAL NOT NULL, programs INTEGER, sessions INTEGER, errors INTEGER, stale INTEGER,
  budget_hit INTEGER, head TEXT);                       -- programs: those whose run completed that night
CREATE TABLE IF NOT EXISTS fwd_cey (day TEXT PRIMARY KEY, n_w INTEGER NOT NULL, members INTEGER NOT NULL,
  neff REAL NOT NULL, neff_raw REAL, cey_day REAL NOT NULL, cey_total REAL NOT NULL, sim_py REAL, hist_iy REAL,
  replay_multiple REAL, at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS fwd_meter (day TEXT PRIMARY KEY, m INTEGER NOT NULL, bh INTEGER NOT NULL, by_ INTEGER NOT NULL,
  min_p REAL, controls_m INTEGER NOT NULL, controls_bh INTEGER NOT NULL, controls_by INTEGER NOT NULL,
  controls_p10 REAL, at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS fwd_groups (day TEXT NOT NULL, grp TEXT NOT NULL, n INTEGER NOT NULL, mean_x REAL,
  mean_r REAL, mean_w REAL, mean_x0 REAL,               -- mean_x0: control groups only (D5)
  ugroups TEXT NOT NULL DEFAULT '',                     -- the base groups its pids' ugroups name that day, sorted, "+"
  PRIMARY KEY (day, grp));
CREATE TABLE IF NOT EXISTS fwd_fillgap (                -- the timing table: every store symbol, both fill points
  day TEXT NOT NULL, symbol TEXT NOT NULL, at TEXT NOT NULL, official REAL NOT NULL, livelike REAL NOT NULL,
  drift_bp REAL NOT NULL, bar TEXT NOT NULL, field TEXT NOT NULL, PRIMARY KEY (day, symbol, at));
CREATE TABLE IF NOT EXISTS fwd_lotgap (                 -- one closed LIVE lot (D11)
  lid INTEGER PRIMARY KEY, instance TEXT NOT NULL, pid INTEGER, symbol TEXT NOT NULL, opened_day TEXT NOT NULL,
  exit_day TEXT NOT NULL, entry_at TEXT NOT NULL, exit_at TEXT NOT NULL, model_bp REAL NOT NULL,
  entry_slip_bp REAL, exit_slip_bp REAL, timing_entry_bp REAL, timing_exit_bp REAL, exec_entry_bp REAL,
  exec_exit_bp REAL, side_gap_bp REAL, twin_gap_bp REAL, at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS fwd_twins (                  -- one live instance and decision session (D12)
  instance TEXT NOT NULL, day TEXT NOT NULL, pid INTEGER NOT NULL, live_keys TEXT NOT NULL, shadow_keys TEXT NOT NULL,
  agree INTEGER,                                        -- 1 | 0 | NULL (unreadable: `why` says which rule)
  why TEXT, at REAL NOT NULL,
  live_bars TEXT, shadow_bars TEXT,                     -- THE BARS HASH of the live decision's bars (NULL: not known) and
                                                        -- of the twin's decision
  cause TEXT CHECK (cause IS NULL OR cause IN ('bars','program','unknown')),   -- agree 0 only (CAUSES); else NULL
  PRIMARY KEY (instance, day));
CREATE TABLE IF NOT EXISTS fwd_part (instance TEXT NOT NULL, through TEXT NOT NULL, pid INTEGER NOT NULL,
  matched INTEGER NOT NULL, missed INTEGER NOT NULL, extra INTEGER NOT NULL, at REAL NOT NULL,
  PRIMARY KEY (instance, through));
"""
_TRIGGERS_SQL = "".join(
    f"CREATE TRIGGER IF NOT EXISTS {t}_no_{verb.lower()} BEFORE {verb} ON {t} BEGIN SELECT RAISE(ABORT, "
    f"'{APPEND_ONLY_ERROR}'); END;\n" for t in APPEND_ONLY for verb in ("UPDATE", "DELETE"))
#: The whole store: `sqlite3.Connection.executescript(SCHEMA)` (idempotent). Complete from step 0: every package tests
#: on an in-memory database made from it.
SCHEMA = _TABLES_SQL + _TRIGGERS_SQL


# ------------------------------------------------------------------------------------------------------- shared types
@dataclass(frozen=True)
class Program:
    """One registry row as the jobs read it: `key` ("<family>@<version>" | "control:<group>:<n>"); `family` and
    `version` None for a control; `lane` ("beta" | "equity" | "control"); `reason` (`REASONS`); `ugroup`
    (`elane_train.symbols_group` of its NEEDS symbols; a control's own group); `lineage` (`elane.lineage_key(lane,
    families.lineage)`; a control's own key); `code` (the frozen program text; a control's is the canonical JSON of its
    `forward_controls.spec`); `params` and `needs` (dicts: {"symbols", "history", "max_hold_sessions"}); `program_sha`
    (sha256 of the code); `run_sha` (`gate.run_sha(version)`; a control's is its `program_sha`); `created_at` (epoch:
    D2's T); `first_close` and `first_day` (dates, D2); `route` and `alpha_f` (the hashed forward route and alpha)."""

    pid: int
    key: str
    family: str | None
    version: int | None
    lane: str
    reason: str
    ugroup: str
    lineage: str
    code: str
    params: dict[str, Any]
    needs: dict[str, Any]
    program_sha: str
    run_sha: str
    created_at: float
    first_close: dt.date
    first_day: dt.date
    route: str
    alpha_f: str


@dataclass(frozen=True)
class ShadowRun:
    """One shadow run of a registered program (D3): `program`; `result` (the k 1.0 engine result, as the decider
    child's "run" returned it); `bars` (the `league.equity.store.Bars` slice it ran on); `series` (the
    `league.equity.screen.Series` of its lots on those bars). What league/ops/forward_shadow.py hands to
    league/ops/forward_twins.py (`on_run`, the twin runs)."""

    program: Program
    result: Mapping[str, Any]
    bars: Any
    series: Any


def bars_hash(inputs: Any) -> str:
    """THE BARS HASH of one decision (the module docstring): the first `BARS_HEX` hex characters of the sha256 of
    `league.equity.ctx.ctx_bytes` of a ctx that holds ONLY what `ctx.build(inputs)` gives for `symbols`, `bars` and
    `prices` (the as-of history a program reads at that close, rounded as the program sees it). `inputs` is a
    `league.equity.ctx.Inputs`: the Gym's (`ctx.inputs_from_bars`, `elane_train.state_inputs`) or the live path's
    (`ctx.inputs_from_fetch`). Positions, orders, cash, caps, params and the calendar fields do not enter it, so two
    decisions on the same as-of bars hash the same whatever book they hold. Complete from step 0 (the forward shadow
    and the twins must agree on it byte for byte); ValueError as `ctx.build` raises it."""
    from ..equity import ctx as C

    built = C.build(inputs)
    return hashlib.sha256(C.ctx_bytes(C.Ctx(symbols=built.symbols, bars=built.bars,
                                            prices=built.prices))).hexdigest()[:BARS_HEX]


# ------------------------------------------------------------------------------------------------------------ settings
def cfg(settings: Mapping[str, Any] | None) -> dict[str, Any]:
    """`elane.forward` in the swarm's settings: every key of `DEFAULTS`, each value inside its bound (`BOUNDS`; `mode`
    one of `MODES`; `fill_minutes` and `twins` booleans). A malformed value is its code default; an unreadable block
    is `DEFAULTS` (mode "off")."""
    raise NotImplementedError("A: league/ops/forward_db.py cfg")


def mode(settings: Mapping[str, Any] | None) -> str:
    """`cfg(settings)["mode"]`: "off" | "record"."""
    raise NotImplementedError("A: league/ops/forward_db.py mode")


# ------------------------------------------------------------------------------------------------------- forward days
def t0() -> dt.date:
    """D1: the first forward day, `schedule.next_session(config.LOOK_CAP)` (computed, never a literal date)."""
    raise NotImplementedError("A: league/ops/forward_db.py t0")


def first_close(created_at: float) -> dt.date:
    """D2: the earliest session d with `schedule.moments(d).close_at > created_at` and d >= `config.LOOK_CAP`: the
    close a program first decides at (a half day closes at 13:00; a weekend or a holiday moves it to the next
    session)."""
    raise NotImplementedError("A: league/ops/forward_db.py first_close")


def first_day(first_close: dt.date) -> dt.date:
    """D2: `schedule.next_session(first_close)`: the first session a program has a fill, a mark or P&L on; always
    on or after `t0()`."""
    raise NotImplementedError("A: league/ops/forward_db.py first_day")


def fwd_engine() -> str:
    """Tonight's engine label (the module docstring): `EQUITY_ENGINE_VERSION + "+" +
    evaluator.equity_fingerprint()[:12] + "+" + FWD_SERIES`, read once a night by the forward shadow."""
    raise NotImplementedError("A: league/ops/forward_db.py fwd_engine")


# ------------------------------------------------------------------------------------------------------------ the store
def open_db(root: str | Path, *, readonly: bool = False) -> sqlite3.Connection:
    """`<root>/forward.sqlite`, rows as `sqlite3.Row`. Writable: creates the file 0600 (WAL), runs `SCHEMA` and, when
    `fgs_prereg` is absent, writes that kv (`kv_first`: `FGS_SHA`) and one `prereg` event holding the sha and `FGS`.
    `readonly`: `guard.connect_ro` (it raises `sqlite3.OperationalError` when the file is absent)."""
    raise NotImplementedError("A: league/ops/forward_db.py open_db")


def row_hash(prev_hash: str, row: Mapping[str, Any]) -> str:
    """The chain link of one registry row: `sha256((prev_hash + "\\n" + results.canonical({k: row[k] for k in HASHED})
    + "\\n" + sha256(row["code"].encode()).hexdigest()).encode()).hexdigest()`."""
    raise NotImplementedError("A: league/ops/forward_db.py row_hash")


def append_registry(db: sqlite3.Connection, row: Mapping[str, Any]) -> int:
    """One registry row in one transaction: pid = the largest + 1; `prev_hash` = the last row's `row_hash` (`GENESIS`
    for the first); the insert; a `registered` event. The new pid. `sqlite3.IntegrityError` on a known key. A row
    whose (`route`, `alpha_f`) is neither (`E3_ROUTE`, `E3_ALPHA_F`) nor (`CONTROL_ROUTE`, `CONTROL_ALPHA_F`) is a
    ValueError in E3."""
    raise NotImplementedError("A: league/ops/forward_db.py append_registry")


def verify_chain(db: sqlite3.Connection) -> dict[str, Any]:
    """The registry's chain read whole: {"ok", "rows", "head" (the last row's hash; `GENESIS` when empty),
    "first_bad" (the pid of the first row whose `prev_hash` or `row_hash` does not hold; None)}. A tampered column of
    `HASHED` (its `route` or `alpha_f` among them) or a changed `code` is found."""
    raise NotImplementedError("A: league/ops/forward_db.py verify_chain")


def head(db: sqlite3.Connection) -> str:
    """The last registry row's `row_hash` (`GENESIS` when the registry is empty)."""
    raise NotImplementedError("A: league/ops/forward_db.py head")


def event(db: sqlite3.Connection, kind: str, *, pid: int | None = None, day: str | None = None,
          payload: Mapping[str, Any] | None = None, at: float, once: str | None = None) -> int:
    """One `fwd_events` row; its seq. With `once` (a short string) the row is written only when no row of that kind,
    pid and day carries the same `once` in its payload (it then returns 0); the payload holds it under "once". A
    payload is small JSON with a `why`: ids, counts and dates only, never a price or a return."""
    raise NotImplementedError("A: league/ops/forward_db.py event")


def events(db: sqlite3.Connection, kind: str, *, pid: int | None = None, since: float | None = None
           ) -> list[dict[str, Any]]:
    """The `kind` events in seq order (of `pid` only when given; those with `at` >= `since` only when given): each
    {"seq", "at", "kind", "pid", "day", "payload" (a dict)}."""
    raise NotImplementedError("A: league/ops/forward_db.py events")


def kv_get(db: sqlite3.Connection, key: str, default: Any = None) -> Any:
    """`fwd_kv[key]` (JSON), `default` when absent."""
    raise NotImplementedError("A: league/ops/forward_db.py kv_get")


def kv_put(db: sqlite3.Connection, key: str, value: Any) -> None:
    """`fwd_kv[key] = value` (JSON; the one table that can be overwritten)."""
    raise NotImplementedError("A: league/ops/forward_db.py kv_put")


def kv_first(db: sqlite3.Connection, key: str, value: Any) -> bool:
    """`fwd_kv[key] = value` only when the key is absent (True); never overwrites (False)."""
    raise NotImplementedError("A: league/ops/forward_db.py kv_first")


def engine_id(db: sqlite3.Connection, label: str, *, at: float) -> tuple[int, bool]:
    """(the label's id in `fwd_engines`, whether this call created it)."""
    raise NotImplementedError("A: league/ops/forward_db.py engine_id")


def engine_now(db: sqlite3.Connection) -> int | None:
    """The newest engine id (None before the first night)."""
    raise NotImplementedError("A: league/ops/forward_db.py engine_now")


def engine_label(db: sqlite3.Connection, id: int) -> str | None:  # noqa: A002 - the contract's name
    """The label of an engine id (None when unknown)."""
    raise NotImplementedError("A: league/ops/forward_db.py engine_label")


# ---------------------------------------------------------------------------------------------------------- programs
def programs(db: sqlite3.Connection, *, reasons: Sequence[str] | None = None, active: bool = True) -> list[Program]:
    """The registry's rows as `Program`s in pid order (of `reasons` only when given; `active` True: those `active`
    says are; False: every row)."""
    raise NotImplementedError("A: league/ops/forward_db.py programs")


def active(db: sqlite3.Connection, pid: int) -> bool:
    """No "stopped" tag newer than its latest "resumed" tag (a control never stops)."""
    raise NotImplementedError("A: league/ops/forward_db.py active")


def suspect(db: sqlite3.Connection, pid: int) -> bool:
    """A "suspect" tag whose value, a night, is on or after its last stored day (a suspect is not stopped: it runs
    last and is counted in the report)."""
    raise NotImplementedError("A: league/ops/forward_db.py suspect")


def program(db: sqlite3.Connection, key: str) -> Program | None:
    """The registry row of `key` (None when not registered)."""
    raise NotImplementedError("A: league/ops/forward_db.py program")


def tags(db: sqlite3.Connection, pid: int) -> dict[str, list[dict[str, Any]]]:
    """{tag: [{"value", "at"}, ...]} of a pid, each list by `at`."""
    raise NotImplementedError("A: league/ops/forward_db.py tags")


def tag(db: sqlite3.Connection, pid: int, tag: str, value: str = "", *, at: float) -> bool:
    """One `fwd_tags` row (`tag` one of `TAGS`); False when (pid, tag, value) is already there."""
    raise NotImplementedError("A: league/ops/forward_db.py tag")


def counted_days(db: sqlite3.Connection, pid: int, *, engine: int | None = None) -> list[dict[str, Any]]:
    """D4's COUNTED days of a pid, in day order: its `fwd_days` rows of `engine` (the newest engine id when None) with
    status "ok" and no `audit_mismatch` event for that (pid, day); each a dict of the row's columns."""
    raise NotImplementedError("A: league/ops/forward_db.py counted_days")


def stored_days(db: sqlite3.Connection, pid: int, *, engine: int | None = None) -> int:
    """How many `fwd_days` rows a pid has under `engine` (the newest engine id when None), any status: what the session
    caps count."""
    raise NotImplementedError("A: league/ops/forward_db.py stored_days")


__all__ = ["DB", "SCHEMA", "GENESIS", "MODES", "REASONS", "LANES", "CHECKPOINTS", "CHECKPOINT_EVERY", "FWD_SERIES",
           "FILL_VERSION", "TOL", "NEFF_WINDOW", "NEFF_MIN_DAYS", "NEFF_PROVISIONAL", "Q", "RC_READS", "RC_MIN_GROUP",
           "SUSPECT_NIGHTS", "DQ_NIGHTS", "A14_GAP_BP", "A14_AGREE", "E3_ROUTE", "E3_ALPHA_F", "CONTROL_ROUTE",
           "CONTROL_ALPHA_F", "FGS", "FGS_SHA", "HASHED", "DEFAULTS", "BOUNDS", "TAGS", "EVENT_KINDS", "ONCE_KINDS",
           "KV_KEYS", "CAUSES", "BARS_HEX", "TABLES", "APPEND_ONLY", "WRITERS", "APPEND_ONLY_ERROR", "Program",
           "ShadowRun", "bars_hash", "cfg", "mode", "t0", "first_close", "first_day", "fwd_engine", "open_db",
           "row_hash", "append_registry", "verify_chain", "head", "event", "events", "kv_get", "kv_put", "kv_first",
           "engine_id", "engine_now", "engine_label", "programs", "active", "suspect", "program", "tags", "tag",
           "counted_days", "stored_days"]
