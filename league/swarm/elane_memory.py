"""THE EQUITY MEMORY's tables (release E3): what every scored version showed, seen and out of fold; recorded, not read.

Owner: E (league/ops/E3_INTERFACES.md). Three append-only tables in the swarm store (`SCHEMA`, `ensure`; House only;
UPDATE and DELETE abort, and an insert of a key already written is dropped: the first write stands, `KEYS`):

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

THE HIDDEN RUN'S OWN CHILD (`hidden_runner`). A program's memory outlives a run wherever the interpreter does: a
module of the child (a class-level array of numpy that a call's result exposes, say) is one object for every program
the child ever runs, and E2's static checks allow the call. The swarm has ONE evidence child
(league/swarm/elane.py `isolated_runner`), and it runs the family's next version's SEEN runs: a hidden run made
there could leave a mark the next version reads, and the hidden year would reach the family's own researcher through
that version's record. So the hidden run is never made on the runner the seen runs were made on. `ingest` starts a
decider child OF ITS OWN for one version's hidden runs (E1's `Isolated` over the same store on a new decider of the
seen child's class, limits and hash seed; its log `HIDDEN_LOG` beside the evidence child's), and closes it when they
are in: the process that held the hidden year's bars is dead before any other run starts, and no seen run, Validation
run or look is ever made in it. What stays out of reach by other rules, not this one: a file (numpy's doors to files
are shut by name, league/gym/safety.py `NUMPY_BANNED`). A runner that is not E1's `Isolated` on E1's decider must say
itself how its hidden runs are kept apart (a `hidden_runner()` method: the tests' invented markets, which hold no
process); with neither, `HiddenRunRefused`: the hidden year is run nowhere and no out-of-fold row is written.

WHAT A ROW HOLDS BESIDE THE SPEC'S WORDS. `seen_sha` hashes the verdict's Train FIGURES as `elane_train.compact`
shapes them (objective, passed, fails, score, the years, the summary, the figures beside and the restart check's
counts), without the clock's `at` and the `identity`: the same figures give the same sha whenever they were judged.
`mem_contrib.run_sha` is the hidden run's own (E1's `EquityProgram.run_sha`: the code with its merged PARAMS), never
the swarm's `gate.run_sha`. `fails` is a JSON list. A hidden run already recorded at a k is not run again.

`league.swarm.elane_train` and `elane_seal` are imported INSIDE FUNCTIONS only (`elane_train` imports this module at
the top), and so are E1's `league.equity.runner` and `league.live.decider` (`hidden_runner` alone: the child it
starts). Standard library and numpy only (numpy inside functions).
"""

from __future__ import annotations

import contextlib
import json
import math
import sqlite3
from pathlib import Path
from typing import Any, Iterator, Mapping

TABLES = ("mem_seen", "mem_contrib", "mem_series")
#: The tables that hold a hidden year's results: named only here, in `elane_seal` and in league/ops/.
SEALED_TABLES = ("mem_contrib", "mem_series")
#: `mem_contrib.kind` and `symset` in E3 (a later release adds transfer runs).
KIND_OWN = "own"
APPEND_ONLY_ERROR = "the equity memory is append-only"
#: The log of THE HIDDEN RUN'S OWN CHILD, beside the evidence child's (<state>/equity-decider.log).
HIDDEN_LOG = "equity-hidden-decider.log"

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
#: Each table's key. THE FIRST WRITE STANDS: SQLite fires no DELETE trigger for the row an `INSERT OR REPLACE` displaces
#: (unless `recursive_triggers` is on), so the two triggers above alone would let a REPLACE overwrite a row. A third
#: trigger a table drops any insert of a key already written, whatever its conflict clause.
KEYS: dict[str, tuple[str, ...]] = {"mem_seen": ("family", "version"),
                                    "mem_contrib": ("family", "version", "symset", "k"), "mem_series": ("sha",)}
_FIRST_WRITE_SQL = "".join(
    f"CREATE TRIGGER IF NOT EXISTS {t}_first_write BEFORE INSERT ON {t} WHEN EXISTS (SELECT 1 FROM {t} WHERE "
    + " AND ".join(f"{column} = NEW.{column}" for column in KEYS[t]) + ") BEGIN SELECT RAISE(IGNORE); END;\n"
    for t in TABLES)
#: The three tables, their append-only triggers and their first-write triggers (idempotent). Tests make an in-memory
#: database from it.
SCHEMA = _TABLES_SQL + _TRIGGERS_SQL + _FIRST_WRITE_SQL


def _statements(script: str) -> list[str]:
    """`script` cut into its statements (`sqlite3.complete_statement`: a trigger's body keeps its own semicolons)."""
    out, held = [], ""
    for line in script.splitlines():
        held += line + "\n"
        if sqlite3.complete_statement(held):
            if held.strip():
                out.append(held.strip())
            held = ""
    if held.strip():
        raise ValueError("the equity memory's schema does not end on a whole statement")
    return out


#: Every object `SCHEMA` creates: the three tables and their three triggers each.
_OBJECTS = frozenset({*TABLES, *(f"{t}_{name}" for t in TABLES for name in ("no_update", "no_delete", "first_write"))})


def ensure(store: Any) -> None:
    """Create the three tables and their triggers in the swarm store (`SCHEMA`; idempotent; a writable `SwarmStore`,
    under its lock). One statement at a time inside the store's own transaction, never `executescript` (which would
    commit a transaction the caller holds)."""
    made = {str(r["name"]) for r in store._all("SELECT name FROM sqlite_master WHERE name LIKE 'mem%'")}
    if _OBJECTS <= made:
        return
    with store.atomic():
        for statement in _statements(SCHEMA):
            store._exec(statement)


def seen_sha(verdict: Mapping[str, Any]) -> str:
    """`results.sha` of a verdict's Train figures as the record keeps them (`elane_train.compact`), less the clock's
    `at` and the `identity` (the module docstring)."""
    from ..equity import results
    from . import elane_train

    kept = elane_train.compact(verdict, at="", ident=None)
    return results.sha({k: v for k, v in kept.items() if k not in ("at", "identity")})


def _real(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) else None


def _results(runs: Any) -> list[dict[str, Any]]:
    """The results of a k's seen runs (each a `runner.Run`, or a bare result)."""
    out = []
    for run in runs if isinstance(runs, (list, tuple)) else ():
        result = getattr(run, "result", run)
        if isinstance(result, Mapping):
            out.append(dict(result))
    return out


class HiddenRunRefused(RuntimeError):
    """The hidden run has no child of its own to be made in (`hidden_runner`): it is made nowhere."""


@contextlib.contextmanager
def hidden_runner(runner: Any) -> Iterator[Any]:
    """THE HIDDEN RUN'S OWN CHILD (the module docstring): a runner for ONE version's hidden runs that shares no process
    with `runner`, the one its seen runs were made on. For E1's `Isolated` on E1's `Decider`: a new `Isolated` over
    the same store on a NEW `Decider` with the seen child's limits, interpreter and hash seed (the hidden run is the
    seen runs' run in another process), started at its first request and CLOSED when the block ends. An
    `InlineDecider` (tests only: one process, no child to keep apart) gets a new one. A runner with a
    `hidden_runner()` method of its own is asked (the tests' invented markets). Anything else: `HiddenRunRefused`."""
    from ..equity.runner import Isolated
    from ..live.decider import Decider, InlineDecider

    own = getattr(runner, "hidden_runner", None)
    if callable(own):
        yield own()
        return
    seen = getattr(runner, "decider", None)
    if not isinstance(runner, Isolated) or not isinstance(seen, (Decider, InlineDecider)):
        raise HiddenRunRefused(f"no child of its own for the hidden run: the seen runs' runner is a "
                               f"{type(runner).__name__} on a {type(seen).__name__}")
    if isinstance(seen, Decider):
        child: Any = Decider(timeout=seen.timeout, max_errors=seen.max_errors, memory_mb=seen.memory_mb,
                             python=seen.python, log=Path(seen.log).with_name(HIDDEN_LOG) if seen.log else None,
                             allow_unisolated=seen.allow_unisolated)
        child.hash_seed = seen.hash_seed
    else:
        child = InlineDecider(timeout=seen.timeout, max_errors=seen.max_errors)
    try:
        yield Isolated(child, runner.store_root, budget_seconds=runner.budget_seconds)
    finally:
        child.close()  # the process that held the hidden year's bars ends here, before any other run is made


def ingest(store: Any, fam: Mapping[str, Any], version: int, *, runner: Any, code: str, params: Mapping[str, Any],
           seen: Mapping[float, Any], verdict: Mapping[str, Any], settings: Mapping[str, Any] | None,
           now: str | None = None) -> dict[str, Any]:
    """THE INGEST (the module docstring) of one scored version: {"seen" (rows written: 0 | 1), "contrib" (rows
    written), "hidden_year"}. `seen`: {k: [Run, ...]}, the version's Train runs as `EquityResearcher.score` made them
    (one a seen span); `runner`: E1's `Isolated`, the one THE SEEN RUNS were made on: no hidden run is made on it
    (`hidden_runner` gives the hidden runs a child of their own); `verdict`: the bar's verdict (`train_score`, with its
    restart check's); `now`: the rows' `at` (ISO text; the store's clock when None)."""
    from ..equity import config
    from . import elane_effects, elane_folds, elane_seal, elane_train

    out: dict[str, Any] = {"seen": 0, "contrib": 0, "hidden_year": None}
    if elane_folds.mode(settings) != "record":
        return out
    if not isinstance(verdict, Mapping) or verdict.get("pnl_10") is None:
        return out  # RUN, DQ, LOAD, WINDOW: judged on nothing, so there is no figure to record
    fid, n = str(fam["id"]), int(version)
    at = str(now) if now else store.now()
    hidden = elane_folds.hidden_year(fam)
    out["hidden_year"] = hidden
    ensure(store)
    facts = elane_seal.train_facts(fam, elane_train.STATE_KEY)
    cell = elane_train.cell_text(elane_train.cell_of(facts["lane"], facts["agenda"], facts["symbols"]))
    spec = fam.get("spec") if isinstance(fam.get("spec"), Mapping) else {}
    gid = spec.get("gid") if isinstance(spec.get("gid"), str) and spec.get("gid") else elane_folds.GID0
    seen = seen if isinstance(seen, Mapping) else {}
    by_k = {float(k): _results(runs) for k, runs in seen.items()}
    base, stress = by_k.get(float(config.K_BASE), []), by_k.get(float(config.K_STRESS), [])
    cost = elane_effects.costs(base, stress)
    beside = verdict.get("beside") if isinstance(verdict.get("beside"), Mapping) else {}
    row = (fid, n, cell, elane_effects.horizon([lot for r in base for lot in (r.get("lots") or ())]), hidden, gid,
           int(bool(verdict.get("passed"))), json.dumps([str(f) for f in (verdict.get("fails") or [])]),
           _real(beside.get("drift_share")), _real(cost["gross_bp"]), _real(cost["cost_bp"]),
           _real(cost["rt_per_year"]), seen_sha(verdict), at)
    with store.atomic():
        out["seen"] = max(0, int(store._exec(
            "INSERT OR IGNORE INTO mem_seen(family, version, cell, horizon, hidden_year, gid, bar_passed, fails, "
            "drift_share, gross_bp, cost_bp, rt_per_year, seen_sha, at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            row).rowcount))
    if hidden is None:
        return out
    # THE HIDDEN RUN, after the verdict is recorded: its result goes to `contribution` and nowhere else.
    first, last = elane_folds.hidden_span(hidden)
    owed = [k for k in (float(config.K_BASE), float(config.K_STRESS))
            if store._one("SELECT 1 AS ok FROM mem_contrib WHERE family=? AND version=? AND symset=? AND k=?",
                          (fid, n, KIND_OWN, k)) is None]  # recorded once: a second ingest runs nothing, changes nothing
    if not owed:
        return out
    with hidden_runner(runner) as own:  # THE HIDDEN RUN'S OWN CHILD: never the one a seen run is made in
        for k in owed:
            c = elane_effects.contribution(own.train(code, params, name=fid, start=first, end=last, k=k), k=k)
            if c["year"] != hidden:
                raise ValueError(f"the hidden run of {hidden} came back with sessions of {c['year']}")
            with store.atomic():
                store._exec("INSERT OR IGNORE INTO mem_series(sha, days, x, w) VALUES(?,?,?,?)",
                            (c["series_sha"], c["days"], c["x"], c["w"]))
                out["contrib"] += max(0, int(store._exec(
                    "INSERT OR IGNORE INTO mem_contrib(family, version, cell, kind, year, symset, k, status, n_days, "
                    "n_lots, exp_mean, e_ann, se_ann, t_x, series_sha, run_sha, at) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (fid, n, cell, KIND_OWN, hidden, KIND_OWN, k, c["status"], c["n_days"], c["n_lots"], c["exp_mean"],
                     c["e_ann"], c["se_ann"], c["t_x"], c["series_sha"], c["run_sha"], at)).rowcount))
    return out


def counts(db: sqlite3.Connection) -> dict[str, Any]:
    """Row counts for ops' reader, on a read-only connection to the swarm store: {"seen", "contrib", "families"
    (families with a contribution), "by_year": {year: contributions}}. Zeros when the tables do not exist. Counts
    only: never a figure of a row."""
    out: dict[str, Any] = {"seen": 0, "contrib": 0, "families": 0, "by_year": {}}
    have = {str(r[0]) for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name IN (?, ?)",
                                          ("mem_seen", "mem_contrib")).fetchall()}
    if "mem_seen" in have:
        out["seen"] = int(db.execute("SELECT COUNT(*) FROM mem_seen").fetchone()[0])
    if "mem_contrib" in have:
        out["contrib"] = int(db.execute("SELECT COUNT(*) FROM mem_contrib").fetchone()[0])
        out["families"] = int(db.execute("SELECT COUNT(DISTINCT family) FROM mem_contrib").fetchone()[0])
        out["by_year"] = {str(int(year)): int(n) for year, n in db.execute(
            "SELECT year, COUNT(*) FROM mem_contrib GROUP BY year ORDER BY year").fetchall()}
    return out


__all__ = ["TABLES", "SEALED_TABLES", "KIND_OWN", "KEYS", "SCHEMA", "APPEND_ONLY_ERROR", "HIDDEN_LOG",
           "HiddenRunRefused", "ensure", "seen_sha", "hidden_runner", "ingest", "counts"]
