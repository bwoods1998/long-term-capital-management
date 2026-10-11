"""THE EQUITY MEMORY's tables (release E3): what every scored version showed, seen and out of fold; recorded, not read.

Owner: E (league/ops/E3_INTERFACES.md). Three append-only tables in the swarm store (`SCHEMA`, `ensure`; House only):

- `mem_seen`: one row a scored version, its SEEN-year facts (the cell, the measured horizon, whether the bar passed
  and its fails, the drift share, gross and cost in bp a round trip, round trips a year, `seen_sha`). No reader in
  E3. `cell` is `elane_train.cell_text(elane_train.cell_of(lane, agenda, symbols))`; `seen_sha` = `results.sha` of
  the version's verdict as the record keeps it (`elane_train.compact`'s figures: seen years only by construction).
- `mem_contrib` and `mem_series` (`SEALED_TABLES`): THE HIDDEN YEAR's out-of-fold contribution of a version, at each
  k, and its daily series (league/swarm/elane_effects.py `contribution`). `kind` and `symset` are always "own" in E3.
  `days` is int32 little-endian ordinals; `x` and `w` float32 little-endian; `series_sha` = sha256 of the three byte
  strings joined.

THE SEAL. A family's hidden Train year is never a session of its Train runs (league/swarm/elane_folds.py), and its
results reach no generator, its own researcher included: this module and ops alone name the two sealed tables
(`elane_seal.SEALED_TABLES`; league/tests/test_e3_seal_imports.py scans for it), and nothing in the swarm reads any
of the three in E3. A later release pools them; this one only records. Two House states that differ only in these
rows give byte for byte the same architect request, researcher brief and route choice
(league/tests/test_elane_memory_seal.py).

THE INGEST (`ingest`, called by `EquityResearcher.score` after the verdict is recorded, inside its own guard: a
failure here leaves the verdict standing and raises a `swarm.status` alert, action "elane_memory"). Nothing with the
mode "off" (`elane_folds.mode`) or a verdict not judged on the bar (`pnl_10` None). Else one `mem_seen` row and, for a
family with a hidden year, THE HIDDEN RUN at each k (`runner.train(code, params, name=family, start, end, k)` over
`elane_folds.hidden_span`, flat, made after the verdict is recorded) with one `mem_series` and one `mem_contrib` row
each. The hidden run's result is held in no other place and passed to no other function: never `add_run`, never the
record. INSERT OR IGNORE throughout (a rescore changes nothing). A hidden run that raises leaves the `mem_seen` row
and raises to the caller's guard; a disqualified hidden year is recorded as it traded.

`league.swarm.elane_train` and `elane_seal` are imported INSIDE FUNCTIONS only (`elane_train` imports this module at
the top). Standard library and numpy only (numpy inside functions).
"""

from __future__ import annotations

import sqlite3
from typing import Any, Mapping

TABLES = ("mem_seen", "mem_contrib", "mem_series")
#: The tables that hold a hidden year's results: named only here, in `elane_seal` and in league/ops/.
SEALED_TABLES = ("mem_contrib", "mem_series")
#: `mem_contrib.kind` and `symset` in E3 (a later release adds transfer runs).
KIND_OWN = "own"
APPEND_ONLY_ERROR = "the equity memory is append-only"

_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS mem_seen (       -- one row a scored version: seen-year facts (no reader in E3)
  family TEXT NOT NULL, version INTEGER NOT NULL, cell TEXT NOT NULL, horizon TEXT, hidden_year INTEGER,
  gid TEXT NOT NULL, bar_passed INTEGER NOT NULL, fails TEXT NOT NULL, drift_share REAL, gross_bp REAL, cost_bp REAL,
  rt_per_year REAL, seen_sha TEXT NOT NULL, at TEXT NOT NULL, PRIMARY KEY (family, version));
CREATE TABLE IF NOT EXISTS mem_contrib (    -- SEALED: the hidden year's out-of-fold contribution (D15)
  family TEXT NOT NULL, version INTEGER NOT NULL, cell TEXT NOT NULL, kind TEXT NOT NULL CHECK (kind IN ('own','transfer')),
  year INTEGER NOT NULL, symset TEXT NOT NULL, k REAL NOT NULL, status TEXT NOT NULL CHECK (status IN ('ok','disqualified')),
  n_days INTEGER NOT NULL, n_lots INTEGER NOT NULL, exp_mean REAL NOT NULL, e_ann REAL, se_ann REAL, t_x REAL,
  series_sha TEXT NOT NULL, run_sha TEXT NOT NULL, at TEXT NOT NULL, PRIMARY KEY (family, version, symset, k));
CREATE TABLE IF NOT EXISTS mem_series (sha TEXT PRIMARY KEY, days BLOB NOT NULL, x BLOB NOT NULL, w BLOB NOT NULL);  -- SEALED
"""
_TRIGGERS_SQL = "".join(
    f"CREATE TRIGGER IF NOT EXISTS {t}_no_{verb.lower()} BEFORE {verb} ON {t} BEGIN SELECT RAISE(ABORT, "
    f"'{APPEND_ONLY_ERROR}'); END;\n" for t in TABLES for verb in ("UPDATE", "DELETE"))
#: The three tables and their append-only triggers (idempotent). Complete from step 0: tests make an in-memory
#: database from it.
SCHEMA = _TABLES_SQL + _TRIGGERS_SQL


def ensure(store: Any) -> None:
    """Create the three tables and their triggers in the swarm store (`SCHEMA`; idempotent; a writable `SwarmStore`,
    under its lock)."""
    raise NotImplementedError("E: league/swarm/elane_memory.py ensure")


def ingest(store: Any, fam: Mapping[str, Any], version: int, *, runner: Any, code: str, params: Mapping[str, Any],
           seen: Mapping[float, Any], verdict: Mapping[str, Any], settings: Mapping[str, Any] | None,
           now: str | None = None) -> dict[str, Any]:
    """THE INGEST (the module docstring) of one scored version: {"seen" (rows written: 0 | 1), "contrib" (rows
    written), "hidden_year"}. `seen`: {k: [Run, ...]}, the version's Train runs as `EquityResearcher.score` made them
    (one a seen span); `runner`: E1's `Isolated`; `verdict`: the bar's verdict (`train_score`, with its restart
    check's); `now`: the rows' `at` (ISO text; the store's clock when None)."""
    raise NotImplementedError("E: league/swarm/elane_memory.py ingest")


def counts(db: sqlite3.Connection) -> dict[str, Any]:
    """Row counts for ops' reader, on a read-only connection to the swarm store: {"seen", "contrib", "families"
    (families with a contribution), "by_year": {year: contributions}}. Zeros when the tables do not exist. Counts
    only: never a figure of a row."""
    raise NotImplementedError("E: league/swarm/elane_memory.py counts")


__all__ = ["TABLES", "SEALED_TABLES", "KIND_OWN", "SCHEMA", "APPEND_ONLY_ERROR", "ensure", "ingest", "counts"]
