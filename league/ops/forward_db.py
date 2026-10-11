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
  exists before a forward screen is pinned can be given a larger alpha (D2). (Release E4, package J: a PANEL
  program's row, one whose `ugroup` begins `PANEL_UGROUP`, carries `XS_ROUTE` at the same alpha, and no other row
  does: league/ops/forward_xs.py.)
- `fwd_tags`: facts learned later (`TAGS`); ops only, never to a generator.
- `fwd_days`, `fwd_checks`, `fwd_runs`: the nightly recompute's daily rows, its checkpoints at `CHECKPOINTS` counted
  days (then every `CHECKPOINT_EVERY`), and one row a night (league/ops/forward_shadow.py).
- `fwd_cey`, `fwd_meter`, `fwd_groups`: the day's meters (league/ops/forward_report.py).
- `fwd_ll`, `fwd_fillgap`, `fwd_lotgap`, `fwd_twins`, `fwd_part`: the live-like re-price, the timing table, the fill gap
  of each closed live lot, live and shadow intent agreement and participation (league/ops/forward_twins.py).
- `fwd_events`: the forward log (`EVENT_KINDS`), through `event`; `fwd_engines`: the engine labels, through `engine_id`;
  `fwd_kv`: the one table that can be overwritten (`KV_KEYS`).

APPEND-ONLY: a trigger aborts UPDATE and DELETE on every table but `fwd_kv` (`APPEND_ONLY`), a replace included (the
schema turns recursive triggers on for its connection: SQLite fires no delete trigger for a replaced row without
them). The first value written for a key stands; a later different value is an event, never an overwrite. AN EVENT
IS WRITTEN ONCE: every event that restates a standing fact goes through `event(..., once=<key>)` (`ONCE_KINDS`: a
kind of that list written without its key is refused, and so is a kind outside `EVENT_KINDS`), so none repeats night
after night for one cause. A FAILURE OF THE HOUSE NEVER MARKS A PROGRAM: a decider that cannot start, a store being
rewritten, a missing bar or minute end nobody's forward record and tag nobody; they are events and alarms.

TRANSACTIONS: a writable connection is in sqlite3's default transaction mode, as the in-memory databases the packages
test on. Each write of this module (`event`, `tag`, `append_registry`, `kv_put`, `kv_first`, `engine_id`) is its own
transaction, committed before it returns, unless the caller already holds one, which it then joins; `with
transaction(db):` makes several of them one. A row a job writes with `execute` is the job's to commit.

THE REGISTRY'S OWN REFUSALS (`append_registry`, before anything is written): a row outside release E3's route and
alpha, a control or a program carrying the other's, a `program_sha` that is not its code's, a row with no event that
claims a time before the registry saw it, and a forward window that opens before its code existed (D2).

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

import contextlib
import datetime as dt
import hashlib
import json
import math
import os
import re
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

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
#: RELEASE E4 (package J, league/ops/forward_xs.py): the route a PANEL program's row carries, at the same alpha (a row
#: registered before its forward screen is pinned). A panel row is one whose `ugroup` begins `PANEL_UGROUP`; a row
#: carries this route if and only if it is one.
XS_ROUTE = "XS1"
PANEL_UGROUP = "panel:"

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
#: `run_behind` (B; the review's fix) is an ORDER, never a mark: a program whose run failed in the night's child and
#: again alone in a fresh one on a night no other program's run completed (so `run_failed` is not written: the
#: House's) stands behind its class in the next nights' queue until a run of it completes; no rule counts it.
#: `twin_retired` and `twin_revived` (D; the review's fix): the session a live instance was retired at, kept the night
#: the book shows it (a revival clears `retired_at` in the book), and the session it ran again from.
#: `meter_partial` (C; the review's fix): a day whose meters were written after their wait with programs still without
#: their row for it (league/ops/forward_report.py: FW5 reads no such day).
EVENT_KINDS: dict[str, str] = {
    "prereg": "A", "registered": "A", "register_skipped": "A", "stopped": "A", "suspect": "A", "resumed": "A",
    "identity_moved": "A",
    "night_failed": "B", "engine_moved": "B", "run_failed": "B", "run_behind": "B", "data_failed": "B",
    "run_disqualified": "B", "restated": "B", "budget_hit": "B", "audit_mismatch": "B", "chain_ok": "B",
    "chain_broken": "B",
    "no_minute": "D", "twin_unregistered": "D", "twin_sha_mismatch": "D", "twin_interrupted": "D", "live_bars": "D",
    "twin_retired": "D", "twin_revived": "D", "meter_partial": "C"}
#: The kinds written through `event(..., once=<key>)`: a second call for the same kind, pid, day and key writes nothing.
ONCE_KINDS = ("prereg", "register_skipped", "identity_moved", "engine_moved", "night_failed", "run_failed", "run_behind",
              "data_failed", "run_disqualified", "restated", "budget_hit", "audit_mismatch", "no_minute",
              "twin_unregistered", "twin_sha_mismatch", "twin_interrupted", "live_bars", "twin_retired",
              "twin_revived", "meter_partial")
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
#: SQLite's REPLACE (`INSERT OR REPLACE`, `REPLACE INTO`) deletes the row it conflicts with WITHOUT firing a delete
#: trigger unless recursive triggers are on, so with the triggers alone a replace would overwrite a row of an
#: append-only table in silence. The pragma is a connection's own setting (never stored in the file), so it rides at
#: the top of `SCHEMA`: every connection that runs the schema (a writable `open_db`, a package's in-memory test
#: database) refuses a replace as it refuses UPDATE and DELETE.
_PRAGMAS_SQL = "PRAGMA recursive_triggers=ON;\n"
#: The whole store: `sqlite3.Connection.executescript(SCHEMA)` (idempotent). Complete from step 0: every package tests
#: on an in-memory database made from it.
SCHEMA = _PRAGMAS_SQL + _TABLES_SQL + _TRIGGERS_SQL


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
    is `DEFAULTS` (mode "off").

    A bounded value is a whole number: one outside its bound is held at the bound it passed (as `elane.cfg` holds the
    lane's own numbers), and anything that is no whole number (a string, a boolean, a fraction, NaN) is malformed."""
    out = dict(DEFAULTS)
    raw = settings.get("elane") if isinstance(settings, Mapping) else None
    raw = raw.get("forward") if isinstance(raw, Mapping) else None
    if not isinstance(raw, Mapping):
        return out
    if isinstance(raw.get("mode"), str) and raw["mode"] in MODES:
        out["mode"] = raw["mode"]
    for key, (low, high) in BOUNDS.items():
        value = raw.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) \
                or float(value) != int(value):
            continue
        out[key] = int(min(high, max(low, value)))
    for key in ("fill_minutes", "twins"):
        if isinstance(raw.get(key), bool):
            out[key] = raw[key]
    return out


def mode(settings: Mapping[str, Any] | None) -> str:
    """`cfg(settings)["mode"]`: "off" | "record"."""
    return str(cfg(settings)["mode"])


# ------------------------------------------------------------------------------------------------------- forward days
def t0() -> dt.date:
    """D1: the first forward day, `schedule.next_session(config.LOOK_CAP)` (computed, never a literal date)."""
    from ..equity import config, schedule

    return schedule.next_session(config.LOOK_CAP)


def first_close(created_at: float) -> dt.date:
    """D2: the earliest session d with `schedule.moments(d).close_at > created_at` and d >= `config.LOOK_CAP`: the
    close a program first decides at (a half day closes at 13:00; a weekend or a holiday moves it to the next
    session). ValueError for a time that is not a finite number, or one the calendar does not reach."""
    from ..equity import config, schedule

    if isinstance(created_at, bool) or not isinstance(created_at, (int, float)) or not math.isfinite(created_at):
        raise ValueError(f"created_at is an epoch time: {created_at!r}")
    try:
        day = max(schedule.ny_day(float(created_at)), config.LOOK_CAP)
    except (OverflowError, OSError) as exc:      # a time no calendar holds
        raise ValueError(f"created_at is outside the calendar: {created_at!r}") from exc
    for _ in range(schedule.HORIZON_DAYS + 1):
        moments = schedule.moments(day)          # None: not a session
        if moments is not None and moments.close_at > float(created_at):
            return day
        day += dt.timedelta(days=1)
    raise ValueError(f"no NYSE session closes within {schedule.HORIZON_DAYS} days after {created_at!r}")


def first_day(first_close: dt.date) -> dt.date:
    """D2: `schedule.next_session(first_close)`: the first session a program has a fill, a mark or P&L on; always
    on or after `t0()`."""
    from ..equity import schedule

    return schedule.next_session(first_close)


def fwd_engine() -> str:
    """Tonight's engine label (the module docstring): `EQUITY_ENGINE_VERSION + "+" +
    evaluator.equity_fingerprint()[:12] + "+" + FWD_SERIES`, read once a night by the forward shadow."""
    from ..equity import EQUITY_ENGINE_VERSION
    from ..swarm import evaluator

    return f"{EQUITY_ENGINE_VERSION}+{evaluator.equity_fingerprint()[:12]}+{FWD_SERIES}"


# ------------------------------------------------------------------------------------------------------------ the store
@contextlib.contextmanager
def _tx(db: sqlite3.Connection) -> Iterator[None]:
    """One write of this module: its own transaction when the caller holds none (begun and committed here, rolled
    back whole on any error), else a part of the caller's, which the caller commits (`transaction` is this, by its
    public name: the forward shadow's one transaction a program)."""
    if db.in_transaction:
        yield
        return
    db.execute("BEGIN IMMEDIATE")
    try:
        yield
    except BaseException:
        db.rollback()
        raise
    db.commit()


def transaction(db: sqlite3.Connection) -> Any:
    """`with transaction(db):` makes the writes inside it ONE transaction: begun here and committed at its end (rolled
    back whole on any error) when the caller holds none, else a part of the caller's. Every write of this module
    (`event`, `tag`, `append_registry`, `kv_put`, `kv_first`, `engine_id`) joins it; a plain `with db:` begins nothing
    by itself, so the first of them would commit alone."""
    return _tx(db)


def _json(value: Any, default: Any = None) -> Any:
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def open_db(root: str | Path, *, readonly: bool = False) -> sqlite3.Connection:
    """`<root>/forward.sqlite`, rows as `sqlite3.Row`. Writable: creates the file 0600 (WAL), runs `SCHEMA` and, when
    `fgs_prereg` is absent, writes that kv (`kv_first`: `FGS_SHA`) and one `prereg` event holding the sha and `FGS`.
    `readonly`: `guard.connect_ro` (it raises `sqlite3.OperationalError` when the file is absent).

    THE FIRST VALUE STANDS: a store whose `fgs_prereg` is another sha than this release's `FGS_SHA` keeps it, and this
    release's sha is one more `prereg` event (once a sha), never an overwrite: a forward screen that differs from the
    pinned shape judges only days after its own pin. A writable connection is in sqlite3's default transaction mode,
    as the in-memory databases the packages test on: a write made with `execute` is the caller's to commit; this
    module's own writes commit themselves unless the caller already holds a transaction (`transaction`)."""
    path = Path(root) / DB
    if readonly:
        from . import guard

        return guard.connect_ro(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        os.close(os.open(path, os.O_RDWR | os.O_CREAT, 0o600))
    db = sqlite3.connect(str(path), timeout=30.0)
    try:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=NORMAL")
        db.executescript(SCHEMA)
        pinned = kv_get(db, "fgs_prereg")
        if pinned != FGS_SHA:
            with _tx(db):
                first = kv_first(db, "fgs_prereg", FGS_SHA)
                why = ("the forward screen's shape, pinned before any forward day exists" if first else
                       "this release's forward screen shape differs from the one pinned at the store's creation: the "
                       "pinned one stands, and this one judges only days after its own pin")
                event(db, "prereg", payload={"fgs_sha": FGS_SHA, "fgs": FGS, "pinned": FGS_SHA if first else pinned,
                                             "why": why}, at=time.time(), once=FGS_SHA)
    except BaseException:
        db.close()
        raise
    return db


def _stored(row: Mapping[str, Any]) -> dict[str, Any]:
    """A registry row's hashed columns as the store holds them (TEXT, INTEGER and REAL), so a row hashes the same
    before its insert and read back: `version` an integer or None, the two times floats, `family` text or None, every
    other column text."""
    out: dict[str, Any] = {}
    for key in HASHED:
        value = row[key]
        if key in ("pid", "version"):
            out[key] = None if value is None else int(value)
        elif key in ("created_at", "registered_at"):
            out[key] = float(value)
        elif key == "family":
            out[key] = None if value is None else str(value)
        else:
            out[key] = str(value)
    return out


def row_hash(prev_hash: str, row: Mapping[str, Any]) -> str:
    """The chain link of one registry row: `sha256((prev_hash + "\\n" + results.canonical({k: row[k] for k in HASHED})
    + "\\n" + sha256(row["code"].encode()).hexdigest()).encode()).hexdigest()` (each hashed column as the store holds
    it: `_stored`)."""
    code_sha = hashlib.sha256(str(row["code"]).encode()).hexdigest()
    return hashlib.sha256((str(prev_hash) + "\n" + results.canonical(_stored(row)) + "\n" + code_sha).encode()).hexdigest()


def _text(value: Any, name: str) -> str:
    """A canonical JSON object as text: a mapping is encoded (`results.canonical`), a string must already be one."""
    if isinstance(value, Mapping):
        return results.canonical(value)
    if not isinstance(value, str) or not isinstance(_json(value), dict):
        raise ValueError(f"a registry row's {name} is a JSON object")
    return value


def _day(value: Any, name: str) -> dt.date:
    if isinstance(value, dt.datetime):
        raise ValueError(f"a registry row's {name} is a session day, not a time")
    if isinstance(value, dt.date):
        return value
    try:
        return dt.date.fromisoformat(str(value))
    except ValueError:
        raise ValueError(f"a registry row's {name} is an ISO session day: {value!r}") from None


_EVIDENCE = re.compile(r"^(?:event:[1-9][0-9]*|registry)$")
#: Why each registry reason is registered (the `registered` event's `why`).
_REGISTERED_WHY = {"train_pass": "judged on the Train bar: passed", "train_fail": "judged on the Train bar: failed",
                   "seed": "a captain-seeded program", "live": "a live instance the registry did not hold yet",
                   "control": "a skill-free control of its universe group"}


def append_registry(db: sqlite3.Connection, row: Mapping[str, Any]) -> int:
    """One registry row in one transaction: pid = the largest + 1; `prev_hash` = the last row's `row_hash` (`GENESIS`
    for the first); the insert; a `registered` event. The new pid. `sqlite3.IntegrityError` on a known key. A row
    whose (`route`, `alpha_f`) is neither (`E3_ROUTE`, `E3_ALPHA_F`) nor (`CONTROL_ROUTE`, `CONTROL_ALPHA_F`) is a
    ValueError in E3.

    `row` holds every column of `fwd_registry` but `pid`, `prev_hash` and `row_hash` (`params` and `needs` as mappings
    or canonical JSON text; `first_close` and `first_day` as dates or ISO days; `author` "" when left out). REFUSED
    with a ValueError, before anything is written (fail closed: the chain never holds a row that breaks its own
    pre-registration): a reason, lane or evidence outside its vocabulary; a control without the control's route and
    alpha, or a program with them; a `program_sha` that is not sha256 of `code`; and D2's window: a row with evidence
    "registry" whose `created_at` is before its `registered_at` (no row claims a time before its evidence), a
    `first_close` before `first_close(created_at)`, or a `first_day` that is not `first_day(first_close)`."""
    reason, lane = str(row["reason"]), str(row["lane"])
    if reason not in REASONS or lane not in LANES:
        raise ValueError(f"a registry row's reason is one of {', '.join(REASONS)} and its lane one of {', '.join(LANES)}")
    pair = (str(row["route"]), str(row["alpha_f"]))
    if pair not in ((E3_ROUTE, E3_ALPHA_F), (XS_ROUTE, E3_ALPHA_F), (CONTROL_ROUTE, CONTROL_ALPHA_F)):
        raise ValueError(f"a registry row of release E3 carries route {E3_ROUTE} and alpha_f {E3_ALPHA_F} (a control "
                         f"{CONTROL_ROUTE} and {CONTROL_ALPHA_F}), not {pair[0]!r} and {pair[1]!r}")
    if (pair[0] == XS_ROUTE) != str(row["ugroup"]).startswith(PANEL_UGROUP):
        raise ValueError(f"a panel program's row, and only a panel program's, carries route {XS_ROUTE}")
    control = reason == "control"
    if control != (lane == "control") or control != (pair == (CONTROL_ROUTE, CONTROL_ALPHA_F)):
        raise ValueError("a control, and only a control, carries the control's lane, route and alpha_f")
    if control != (row.get("family") is None) or control != (row.get("version") is None):
        raise ValueError("a control, and only a control, has no family and no version")
    code = row["code"]
    if not isinstance(code, str) or hashlib.sha256(code.encode()).hexdigest() != str(row["program_sha"]):
        raise ValueError("a registry row's program_sha is sha256 of its code")
    evidence = str(row["evidence"])
    if not _EVIDENCE.match(evidence):
        raise ValueError(f'a registry row\'s evidence is "event:<seq>" or "registry", not {evidence!r}')
    created, registered = float(row["created_at"]), float(row["registered_at"])
    if not (math.isfinite(created) and math.isfinite(registered)):
        raise ValueError("a registry row's times are finite epoch seconds")
    if evidence == "registry" and created < registered:
        raise ValueError("a registry row with no event claims a time before the registry first saw it")
    close, day = _day(row["first_close"], "first_close"), _day(row["first_day"], "first_day")
    if close < first_close(created) or day != first_day(close):
        raise ValueError(f"a registry row's forward window opens before its code existed (D2): first_close {close}, "
                         f"first_day {day}")
    values = {"key": str(row["key"]), "family": row.get("family"), "version": row.get("version"), "lane": lane,
              "reason": reason, "ugroup": str(row["ugroup"]), "lineage": str(row["lineage"]), "code": code,
              "params": _text(row["params"], "params"), "needs": _text(row["needs"], "needs"),
              "program_sha": str(row["program_sha"]), "run_sha": str(row["run_sha"]),
              "author": str(row.get("author") or ""), "created_at": created, "evidence": evidence,
              "first_close": close.isoformat(), "first_day": day.isoformat(), "registered_at": registered,
              "route": pair[0], "alpha_f": pair[1]}
    with _tx(db):
        last = db.execute("SELECT pid, row_hash FROM fwd_registry ORDER BY pid DESC LIMIT 1").fetchone()
        values["pid"] = (int(last["pid"]) if last is not None else 0) + 1
        values["prev_hash"] = str(last["row_hash"]) if last is not None else GENESIS
        values = {**values, **_stored(values)}
        values["row_hash"] = row_hash(values["prev_hash"], values)
        names = list(values)
        db.execute(f"INSERT INTO fwd_registry({', '.join(names)}) VALUES({', '.join('?' * len(names))})",
                   [values[name] for name in names])
        event(db, "registered", pid=values["pid"], day=values["first_day"],
              payload={"key": values["key"], "reason": reason, "evidence": evidence, "why": _REGISTERED_WHY[reason]},
              at=registered)
    return int(values["pid"])


def verify_chain(db: sqlite3.Connection) -> dict[str, Any]:
    """The registry's chain read whole: {"ok", "rows", "head" (the last row's hash; `GENESIS` when empty),
    "first_bad" (the pid of the first row whose `prev_hash` or `row_hash` does not hold; None)}. A tampered column of
    `HASHED` (its `route` or `alpha_f` among them) or a changed `code` is found; so is a row taken out from the
    middle (the next row's `prev_hash` no longer holds, and the pids are no longer 1, 2, 3, ...)."""
    rows, prev, first_bad, head_ = 0, GENESIS, None, GENESIS
    cursor = db.execute("SELECT * FROM fwd_registry ORDER BY pid")
    try:
        for row in cursor:
            rows += 1
            held = dict(row)
            head_ = str(held["row_hash"])
            if first_bad is None and (int(held["pid"]) != rows or held["prev_hash"] != prev
                                      or row_hash(prev, held) != held["row_hash"]):
                first_bad = int(held["pid"])
            prev = head_
    finally:
        cursor.close()
    return {"ok": first_bad is None, "rows": rows, "head": head_, "first_bad": first_bad}


def head(db: sqlite3.Connection) -> str:
    """The last registry row's `row_hash` (`GENESIS` when the registry is empty)."""
    row = db.execute("SELECT row_hash FROM fwd_registry ORDER BY pid DESC LIMIT 1").fetchone()
    return str(row[0]) if row is not None else GENESIS


def _once_seen(db: sqlite3.Connection, kind: str, pid: int | None, day: str | None, once: str) -> bool:
    """Whether a row of that kind, pid and day already carries `once` in its payload."""
    where, params = "kind=? AND pid IS ? AND day IS ?", (kind, pid, day)
    try:
        return db.execute(f"SELECT 1 FROM fwd_events WHERE {where} AND json_extract(payload, '$.once')=? LIMIT 1",
                          (*params, once)).fetchone() is not None
    except sqlite3.OperationalError:          # an SQLite built without its JSON functions: read the payloads here
        return any((_json(r[0], {}) or {}).get("once") == once
                   for r in db.execute(f"SELECT payload FROM fwd_events WHERE {where}", params).fetchall())


def event(db: sqlite3.Connection, kind: str, *, pid: int | None = None, day: str | None = None,
          payload: Mapping[str, Any] | None = None, at: float, once: str | None = None) -> int:
    """One `fwd_events` row; its seq. With `once` (a short string) the row is written only when no row of that kind,
    pid and day carries the same `once` in its payload (it then returns 0); the payload holds it under "once". A
    payload is small JSON with a `why`: ids, counts and dates only, never a price or a return.

    ValueError for a kind outside `EVENT_KINDS`, and for a kind of `ONCE_KINDS` written without `once` (an event that
    restates a standing fact is written once, never night after night)."""
    if kind not in EVENT_KINDS:
        raise ValueError(f"no forward event kind {kind!r}; one of {', '.join(EVENT_KINDS)}")
    if once is None and kind in ONCE_KINDS:
        raise ValueError(f"a {kind} event is written once: it names its `once` key")
    if payload is not None and not isinstance(payload, Mapping):
        raise ValueError("a forward event's payload is a mapping")
    pid = None if pid is None else int(pid)
    day = None if day is None else (day.isoformat() if isinstance(day, dt.date) else str(day))
    body = dict(payload or {})
    with _tx(db):
        if once is not None:
            body["once"] = once = str(once)
            if _once_seen(db, kind, pid, day, once):
                return 0
        cursor = db.execute("INSERT INTO fwd_events(at, kind, pid, day, payload) VALUES(?, ?, ?, ?, ?)",
                            (float(at), kind, pid, day, results.canonical(body)))
        return int(cursor.lastrowid or 0)


def events(db: sqlite3.Connection, kind: str, *, pid: int | None = None, since: float | None = None
           ) -> list[dict[str, Any]]:
    """The `kind` events in seq order (of `pid` only when given; those with `at` >= `since` only when given): each
    {"seq", "at", "kind", "pid", "day", "payload" (a dict)}."""
    sql, params = "SELECT seq, at, kind, pid, day, payload FROM fwd_events WHERE kind=?", [kind]
    if pid is not None:
        sql += " AND pid=?"
        params.append(int(pid))
    if since is not None:
        sql += " AND at>=?"
        params.append(float(since))
    out = []
    for row in db.execute(sql + " ORDER BY seq", params).fetchall():
        held = _json(row["payload"], {})
        out.append({"seq": int(row["seq"]), "at": float(row["at"]), "kind": row["kind"], "pid": row["pid"],
                    "day": row["day"], "payload": held if isinstance(held, dict) else {}})
    return out


def kv_get(db: sqlite3.Connection, key: str, default: Any = None) -> Any:
    """`fwd_kv[key]` (JSON), `default` when absent."""
    row = db.execute("SELECT value FROM fwd_kv WHERE key=?", (str(key),)).fetchone()
    return default if row is None else _json(row[0], default)


def kv_put(db: sqlite3.Connection, key: str, value: Any) -> None:
    """`fwd_kv[key] = value` (JSON; the one table that can be overwritten)."""
    with _tx(db):
        db.execute("INSERT INTO fwd_kv(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                   (str(key), json.dumps(value, sort_keys=True, separators=(",", ":"))))


def kv_first(db: sqlite3.Connection, key: str, value: Any) -> bool:
    """`fwd_kv[key] = value` only when the key is absent (True); never overwrites (False)."""
    with _tx(db):
        cursor = db.execute("INSERT OR IGNORE INTO fwd_kv(key, value) VALUES(?, ?)",
                            (str(key), json.dumps(value, sort_keys=True, separators=(",", ":"))))
        return cursor.rowcount == 1


def engine_id(db: sqlite3.Connection, label: str, *, at: float) -> tuple[int, bool]:
    """(the label's id in `fwd_engines`, whether this call created it)."""
    label = str(label)
    if not label:
        raise ValueError("an engine label is not empty")
    with _tx(db):
        row = db.execute("SELECT id FROM fwd_engines WHERE label=?", (label,)).fetchone()
        if row is not None:
            return int(row[0]), False
        cursor = db.execute("INSERT INTO fwd_engines(label, at) VALUES(?, ?)", (label, float(at)))
        return int(cursor.lastrowid), True


def engine_now(db: sqlite3.Connection) -> int | None:
    """The newest engine id (None before the first night)."""
    row = db.execute("SELECT MAX(id) FROM fwd_engines").fetchone()
    return None if row is None or row[0] is None else int(row[0])


def engine_label(db: sqlite3.Connection, id: int) -> str | None:  # noqa: A002 - the contract's name
    """The label of an engine id (None when unknown)."""
    row = db.execute("SELECT label FROM fwd_engines WHERE id=?", (int(id),)).fetchone()
    return None if row is None else str(row[0])


# ---------------------------------------------------------------------------------------------------------- programs
def _program(row: Mapping[str, Any]) -> Program:
    params, needs = _json(row["params"], {}), _json(row["needs"], {})
    return Program(pid=int(row["pid"]), key=str(row["key"]), family=row["family"],
                   version=None if row["version"] is None else int(row["version"]), lane=str(row["lane"]),
                   reason=str(row["reason"]), ugroup=str(row["ugroup"]), lineage=str(row["lineage"]),
                   code=str(row["code"]), params=params if isinstance(params, dict) else {},
                   needs=needs if isinstance(needs, dict) else {}, program_sha=str(row["program_sha"]),
                   run_sha=str(row["run_sha"]), created_at=float(row["created_at"]),
                   first_close=dt.date.fromisoformat(str(row["first_close"])),
                   first_day=dt.date.fromisoformat(str(row["first_day"])), route=str(row["route"]),
                   alpha_f=str(row["alpha_f"]))


def _stopped(db: sqlite3.Connection, pid: int | None = None) -> set[int]:
    """The pids (of `pid` alone when given) with a "stopped" tag newer than their latest "resumed" tag."""
    sql = ("SELECT pid, MAX(CASE WHEN tag='stopped' THEN at END) AS stopped, MAX(CASE WHEN tag='resumed' THEN at END) "
           "AS resumed FROM fwd_tags WHERE tag IN ('stopped', 'resumed')")
    params: tuple[Any, ...] = ()
    if pid is not None:
        sql, params = sql + " AND pid=?", (int(pid),)
    return {int(r["pid"]) for r in db.execute(sql + " GROUP BY pid", params).fetchall()
            if r["stopped"] is not None and (r["resumed"] is None or r["stopped"] > r["resumed"])}


#: What `programs` reads of a row: everything a `Program` holds (the chain's hashes and the author are not in it).
_PROGRAM_COLUMNS = ("pid", "key", "family", "version", "lane", "reason", "ugroup", "lineage", "params", "needs",
                    "program_sha", "run_sha", "created_at", "first_close", "first_day", "route", "alpha_f")


def programs(db: sqlite3.Connection, *, reasons: Sequence[str] | None = None, active: bool = True,
             code: bool = True) -> list[Program]:
    """The registry's rows as `Program`s in pid order (of `reasons` only when given; `active` True: those `active`
    says are; False: every row).

    `code` False: A LISTING. Each `Program.code` is "" (never a registered program's text: the registry's job
    refuses a version whose text declares no NEEDS), and whoever runs one loads it whole first (`program(db, key)`;
    league/ops/forward_shadow.py `_whole`). WHAT IS HELD (the review's
    fix): the rows are read one at a time and a stopped row is dropped as it is read, so the list holds the rows it
    answers with and no other, and a listing holds no program text at all. Fetched whole with every row's code
    (about 6 KB a row, the stopped ones too) the nightly queue outgrew the ops child's address space at some 60,000
    registry rows, after which the job failed every night."""
    columns = ", ".join(_PROGRAM_COLUMNS) + (", code" if code else ", '' AS code")
    sql, params = f"SELECT {columns} FROM fwd_registry", []
    if reasons is not None:
        params = [str(r) for r in reasons]
        if not params:
            return []
        sql += f" WHERE reason IN ({', '.join('?' * len(params))})"
    stopped = _stopped(db) if active else set()
    out = []
    for row in db.execute(sql + " ORDER BY pid", params):     # the cursor, never `fetchall`: one row in hand at a time
        if int(row["pid"]) not in stopped:
            out.append(_program(row))
    return out


def active(db: sqlite3.Connection, pid: int) -> bool:
    """No "stopped" tag newer than its latest "resumed" tag (a control never stops)."""
    return int(pid) not in _stopped(db, int(pid))


def last_stored_day(db: sqlite3.Connection, pid: int) -> str | None:
    """The latest day a pid has a `fwd_days` row for, under any engine (None with no row)."""
    row = db.execute("SELECT MAX(day) FROM fwd_days WHERE pid=?", (int(pid),)).fetchone()
    return None if row is None or row[0] is None else str(row[0])


def suspect(db: sqlite3.Connection, pid: int) -> bool:
    """A "suspect" tag whose value, a night, is on or after its last stored day (a suspect is not stopped: it runs
    last and is counted in the report). A night it completes a run again stores a later day, and it is suspect no
    more."""
    row = db.execute("SELECT MAX(value) FROM fwd_tags WHERE pid=? AND tag='suspect'", (int(pid),)).fetchone()
    if row is None or row[0] is None:
        return False
    last = last_stored_day(db, pid)
    return last is None or str(row[0]) >= last


def program(db: sqlite3.Connection, key: str) -> Program | None:
    """The registry row of `key` (None when not registered)."""
    row = db.execute("SELECT * FROM fwd_registry WHERE key=?", (str(key),)).fetchone()
    return None if row is None else _program(row)


def tags(db: sqlite3.Connection, pid: int) -> dict[str, list[dict[str, Any]]]:
    """{tag: [{"value", "at"}, ...]} of a pid, each list by `at`."""
    out: dict[str, list[dict[str, Any]]] = {}
    for row in db.execute("SELECT tag, value, at FROM fwd_tags WHERE pid=? ORDER BY at, value", (int(pid),)).fetchall():
        out.setdefault(str(row["tag"]), []).append({"value": str(row["value"]), "at": float(row["at"])})
    return out


def tag(db: sqlite3.Connection, pid: int, tag: str, value: str = "", *, at: float) -> bool:
    """One `fwd_tags` row (`tag` one of `TAGS`); False when (pid, tag, value) is already there."""
    if tag not in TAGS:
        raise ValueError(f"no forward tag {tag!r}; one of {', '.join(TAGS)}")
    with _tx(db):
        cursor = db.execute("INSERT OR IGNORE INTO fwd_tags(pid, tag, value, at) VALUES(?, ?, ?, ?)",
                            (int(pid), tag, str(value), float(at)))
        return cursor.rowcount == 1


def counted_days(db: sqlite3.Connection, pid: int, *, engine: int | None = None) -> list[dict[str, Any]]:
    """D4's COUNTED days of a pid, in day order: its `fwd_days` rows of `engine` (the newest engine id when None) with
    status "ok" and no `audit_mismatch` event for that (pid, day); each a dict of the row's columns."""
    engine = engine_now(db) if engine is None else int(engine)
    if engine is None:
        return []
    return [dict(row) for row in db.execute(
        "SELECT d.* FROM fwd_days d WHERE d.pid=? AND d.engine=? AND d.status='ok' AND NOT EXISTS (SELECT 1 FROM "
        "fwd_events e WHERE e.kind='audit_mismatch' AND e.pid=d.pid AND e.day=d.day) ORDER BY d.day",
        (int(pid), engine)).fetchall()]


def stored_days(db: sqlite3.Connection, pid: int, *, engine: int | None = None) -> int:
    """How many `fwd_days` rows a pid has under `engine` (the newest engine id when None), any status: what the session
    caps count."""
    engine = engine_now(db) if engine is None else int(engine)
    if engine is None:
        return 0
    return int(db.execute("SELECT COUNT(*) FROM fwd_days WHERE pid=? AND engine=?", (int(pid), engine)).fetchone()[0])


__all__ = ["DB", "SCHEMA", "GENESIS", "MODES", "REASONS", "LANES", "CHECKPOINTS", "CHECKPOINT_EVERY", "FWD_SERIES",
           "FILL_VERSION", "TOL", "NEFF_WINDOW", "NEFF_MIN_DAYS", "NEFF_PROVISIONAL", "Q", "RC_READS", "RC_MIN_GROUP",
           "SUSPECT_NIGHTS", "DQ_NIGHTS", "A14_GAP_BP", "A14_AGREE", "E3_ROUTE", "E3_ALPHA_F", "CONTROL_ROUTE",
           "CONTROL_ALPHA_F", "XS_ROUTE", "PANEL_UGROUP", "FGS", "FGS_SHA", "HASHED", "DEFAULTS", "BOUNDS", "TAGS", "EVENT_KINDS", "ONCE_KINDS",
           "KV_KEYS", "CAUSES", "BARS_HEX", "TABLES", "APPEND_ONLY", "WRITERS", "APPEND_ONLY_ERROR", "Program",
           "ShadowRun", "bars_hash", "cfg", "mode", "t0", "first_close", "first_day", "fwd_engine", "open_db",
           "row_hash", "append_registry", "verify_chain", "head", "event", "events", "kv_get", "kv_put", "kv_first",
           "engine_id", "engine_now", "engine_label", "programs", "active", "suspect", "program", "tags", "tag",
           "counted_days", "stored_days", "last_stored_day", "transaction"]
