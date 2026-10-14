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
session (it may run the decider child). The nights' hook (`on_run`) writes nothing without a pin either.

THE CLOCK (`pinned`, the table `fwd1_pins`): the first time the job runs under a pin, the time the release that carries
it began running (`funnel.release_start` of the running release; the sighting's own time when the deploy record has
none) is written once a receipt sha, with FWD1_START = `fwd1_rule.start_after(pinned_at)`. Nothing before it is ever
judged, and a lineage registered earlier enters mid-run from it.

THE NIGHT (`night`; after `forward_xs`, the later of the record's two nights, in the registry):
1. THE LINEAGES (`fwd1_lineages`, written once a lineage, first write stands). Every lineage of the registry but the
   controls, at its first sighting: its representative (`representative`), type, case (`case_of`: the sealed facts of
   every family and pid of the lineage), FWD1_START and its mechanism cell (lane / agenda / universe group). Not judged,
   with the reason: an ETF lineage that reached a sealed pre-check (no forward verdict for an S1/S2 look), a lineage
   that already trades (a live row: it passed a sealed look), a type FWD1-R does not cover (a stock program), a
   representative with no counted day yet is simply pending.
2. THE CHECKPOINTS (`fwd1_checks`, written once a lineage and checkpoint: the checkpoint of record, never recomputed).
   The representative's counted days (`forward_db.counted_days`) under ONE engine id from FWD1_START; each day's sides
   (`fwd1_sides`, the nights' hook); `fwd_ll` (ETF); `fwd_lotgap` for g. At each checkpoint the representative has
   reached, in order: t_k, S_k, S15_k; below the global bar it fails that checkpoint with no floor read; at or above,
   the own floor (`fwd1_floors`, computed once a representative on its Train-era runs in the job's own decider child)
   gives c_used, and a PANEL lineage at or above it draws its placebo leg (one panel run over its judged sessions, 999
   draws under the FWD1 seed). The first checkpoint that passes is the PASS; none by 60 is the FAIL.
3. THE VERDICT (`fwd1_verdicts`, one a lineage, for good): "pass", "fail" or "void" (a case-N lineage that reached a
   sealed pre-check after FWD1_START; an engine change that touched a pending representative's judged days: one engine
   id a verdict, `ENGINE_TOUCH`). A pass keeps its sentence (`fwd1_rule.beside`, operator-only: it holds the t and the
   shadow P&L) and its words (`fwd1_rule.words`: ids and words, the permit's). Nothing judges a lineage after it.
4. THE PERMIT FILE (`write_permits`, `PERMITS`): every lineage FWD1 judges with its status and, for a pass, its family,
   version, run sha, cell and words. IDS AND WORDS ONLY: no t, no P&L, no figure of a program. The swarm reads it for
   two things only (league/swarm/elane_forward.py): a FWD1-judged lineage takes no sealed Validation try while the
   seat switch is on, and a pass may take a seat, one live forward seat a mechanism cell, while it is on.
5. THE REPORT (`REPORT`, operator-only): per type and case the lineages registered, pending, passed, failed, void and
   not judged, and the registry's expected zero-edge passes against the observed (`fwd1_rule.expected_passes`).

A FAILURE OF THE HOUSE NEVER MARKS A PROGRAM: a run the child could not finish, a store under a lock, a missing sides row
leave the checkpoint unwritten, and the next night reads the same first k counted days again. The budget
(`elane.fwd1.cpu_seconds_night`) bounds the child's seconds a night; a lineage left over waits a night.

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
from typing import Any, Callable, Mapping, Sequence

from . import forward_db
from . import fwd1_rule as R

JOB = "forward_screen"
DB = "forward-screen.sqlite"
#: The permit file (ids and words only) the swarm reads: league/swarm/elane_forward.py `PERMITS` (a test holds the two
#: equal), and the operator's report.
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
#: An engine change touches a judged day when its r or w moves by more than this (forward_db.TOL).
ENGINE_TOUCH = forward_db.TOL
#: The swarm-store family-state keys that say a family reached a sealed pre-check or look (league/swarm/elane.py
#: `TRY_KEY`, `VERDICTS_KEY`, `LOOK_KEY`; league/swarm/elane_xs.py `PRECHECK_KEY`, `LOOK_KEY`: a test holds them).
SEALED_STATE = ("elane_try", "elane_verdicts", "elane_look", "elane_xs_precheck", "elane_xs_look")
EVENT_KINDS = ("pinned", "registered", "engine_switched", "ineligible", "void", "house")
APPEND_ONLY_ERROR = "forward-screen.sqlite is append-only"

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
"""
TABLES = ("fwd1_pins", "fwd1_sides", "fwd1_lineages", "fwd1_floors", "fwd1_checks", "fwd1_verdicts", "fwd1_events")
SCHEMA = "PRAGMA recursive_triggers=ON;\n" + _TABLES + "".join(
    f"CREATE TRIGGER IF NOT EXISTS {t}_no_{verb.lower()} BEFORE {verb} ON {t} BEGIN SELECT RAISE(ABORT, "
    f"'{APPEND_ONLY_ERROR}'); END;\n" for t in TABLES for verb in ("UPDATE", "DELETE"))


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


# --------------------------------------------------------------------------------------------- the nights' hook: sides
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


def _run_days(run: Any) -> list[str]:
    """The ISO days of a shadow run's series (E3's `screen.Series` holds int ordinals; the panel's `Series` its iso)."""
    series = run.series
    iso = getattr(series, "iso", None)
    if iso:
        return [str(d) for d in iso]
    return [(dt.date(1970, 1, 1) + dt.timedelta(days=int(d))).isoformat() for d in getattr(series, "days", ())]


_PIN_CACHE: dict[str, Any] = {}


def _pinned_rule() -> Any:
    """The repository's pin, read once a process (the nights' hook asks it for every program)."""
    if "rule" not in _PIN_CACHE:
        _PIN_CACHE["rule"] = R.rule()[0]
    return _PIN_CACHE["rule"]


def on_run(root: str | Path, run: Any, *, engine: int, now: float, settings: Mapping[str, Any] | None,
           rule: Any = None) -> int:
    """THE NIGHTS' HOOK (league/ops/forward_shadow.py `_attempt`, E3's night and the panel night alike, after a
    program's rows are written): each day of the run's series gets its sides under tonight's engine id (first write
    stands). Nothing without a pin or with `elane.fwd1.mode` "off" (no store is made). How many rows it wrote."""
    if cfg(settings)["mode"] == "off":
        return 0
    if (rule if rule is not None else _pinned_rule()) is None:
        return 0
    days = _run_days(run)
    if not days:
        return 0
    sides = lot_sides(run.result)
    store = open_store(root)
    try:
        wrote = 0
        with store:
            for day in days:
                cursor = store.execute("INSERT OR IGNORE INTO fwd1_sides(pid, day, engine, sides, at) VALUES (?,?,?,?,?)",
                                       (int(run.program.pid), day, int(engine), float(sides.get(day, 0.0)), float(now)))
                wrote += cursor.rowcount
        return wrote
    finally:
        store.close()


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
    try, a Validation verdict, a pre-check record or a look."""
    state = _state(fam)
    for key in SEALED_STATE:
        value = state.get(key)
        if isinstance(value, Mapping) and value:
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


def register(store: sqlite3.Connection, fdb: sqlite3.Connection, families: Mapping[str, Mapping[str, Any]], *,
             rule: Any, pin_start: dt.date, now: float) -> int:
    """THE LINEAGES' first sightings (the module docstring, 1): one `fwd1_lineages` row each, first write stands. How
    many it wrote."""
    known = {str(r[0]) for r in store.execute("SELECT lineage FROM fwd1_lineages")}
    sealed_pids = _sealed_pids(fdb)
    wrote = 0
    for lineage, rows in sorted(_registry(fdb).items()):
        if lineage in known:
            continue
        rep = representative(rows)
        if rep is None:
            continue
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
        with store:
            cursor = store.execute(
                "INSERT OR IGNORE INTO fwd1_lineages(lineage, type, rep, family, version, run_sha, row_hash, case_, "
                "judged, why, start, cell, receipt, versions, at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (lineage, typ, int(rep["pid"]), rep["family"], rep["version"], rep["run_sha"], rep["row_hash"], case,
                 0 if why else 1, None if why is None else NOT_JUDGED[why], start.isoformat(),
                 cell_of(typ or "ETF", rep, fam), rule.receipt_sha256, len(rows), float(now)))
            if cursor.rowcount:
                wrote += 1
                event(store, "registered", at=now, lineage=lineage, pid=int(rep["pid"]), once="first",
                      payload={"why": "first sighting under the forward screen", "case": case, "type": typ,
                               "judged": not why, "versions": len(rows)})
    return wrote


# ------------------------------------------------------------------------------------------------------- the runs
class OwnFloorRefused(Exception):
    """The PROGRAM's own reason it has no own floor (a Train-era run its own errors ended: a partial series): the
    lineage is ineligible for good, stated. Every other failure of the runs is the House's (asked again)."""


def _capital(result: Mapping[str, Any], default: Any) -> float:
    """A run's capital as league/swarm/elane.py `_capital` reads it (a number or its text), else `default`."""
    try:
        value = float(str(result.get("capital")))
    except (TypeError, ValueError):
        value = float(default)
    return value if math.isfinite(value) and value > 0 else float(default)


class HouseRuns:
    """The Train-era runs of a representative's own floor and a panel representative's placebo leg, in the job's own
    decider child (`forward_shadow._decider`), started on first use and closed by `close`. Each method raises the
    child's or the data's failure (never a program's mark: the checkpoint is left unwritten)."""

    def __init__(self, root: str | Path, *, budget_seconds: float, decider: Any = None,
                 clock: Callable[[], float] = time.time):
        self.root = Path(root)
        self.budget_seconds = float(budget_seconds)
        self.decider = decider
        self.clock = clock
        self._own = decider is None

    def _child(self) -> Any:
        if self.decider is None:
            from . import forward_shadow

            self.decider = forward_shadow._decider(self.root)
        return self.decider

    def close(self) -> None:
        if self._own and self.decider is not None:
            try:
                self.decider.close()
            except Exception:  # noqa: BLE001 - closing a dead child
                pass
            self.decider = None

    def etf_pools(self, program: Any) -> tuple[Any, Any]:
        """(the 2016-19 pool, the 2022-24 pool), each (r, r15, w, b) float64 arrays from `screen.POOL_SKIP` (S2's
        convention), or None for a span the program has no history in: its runs at k 1.0 and 1.5 over each of
        `config.TRAIN_ERA_SEGMENTS` (E1's runner in this job's child), each read by `screen.series`."""
        import numpy as np

        from ..equity import config as econfig
        from ..equity import screen as S
        from ..equity.runner import Isolated
        from ..equity.store import EquityStore

        iso = Isolated(self._child(), self.root / "equity-daily", budget_seconds=self.budget_seconds)
        needs = iso._needs(program.code, program.params, program.key)
        store = EquityStore(self.root / "equity-daily")
        pools: list[Any] = []
        for first, last in econfig.TRAIN_ERA_SEGMENTS:
            bars = store.span(needs.symbols, first, last, history=needs.history)
            runs = [iso._run(program.code, program.params, program.key, bars, k)
                    for k in (econfig.K_BASE, econfig.K_STRESS)]
            statuses = [str(run.result.get("status")) for run in runs]
            if any(s == "no_data" for s in statuses):
                pools.append(None)
                continue
            if any(s != "ok" for s in statuses):
                raise OwnFloorRefused(f"a Train-era run ended {statuses}: its series is partial")
            series = []
            for run in runs:
                result = run.result
                universe = [str(s) for s in (result.get("symbols") or needs.symbols)]
                series.append(S.series(result.get("lots") or [], run.bars, universe=universe,
                                       capital=_capital(result, econfig.SLEEVE_USD)))
            base, stress = series
            if len(base.r) != len(stress.r):
                raise ValueError("the two Train-era runs differ in their sessions")
            skip = S.POOL_SKIP
            pools.append(tuple(np.asarray(a, dtype=np.float64)[skip:] for a in (base.r, stress.r, base.w, base.b)))
        return pools[0], pools[1]

    def panel_pools(self, program: Any) -> tuple[Any, Any]:
        """(the first Train segment's pool, the second's), each (x, x15, w) float64 arrays from XS1's `POOL_SKIP`: the
        program's one run over each of `league.xs.config.TRAIN_SEGMENTS` (XS1's floor runs) in this job's child."""
        import numpy as np

        from ..xs import runner as XR
        from ..xs import screen as XS
        from . import forward_xs

        iso = XR.Isolated(self._child(), self.root / "equity-daily", budget_seconds=self.budget_seconds, nice=None)
        pools: list[Any] = []
        for run in iso.segments(program.code, program.params, name=program.key):
            status = str(run.result.get("status"))
            if status == "no_data":
                pools.append(None)
                continue
            if status != "ok":
                raise OwnFloorRefused(f"a Train-era panel run ended {status!r}: its series is partial")
            found = forward_xs.series(run.result)
            skip = XS.POOL_SKIP
            pools.append(tuple(np.asarray(a, dtype=np.float64)[skip:] for a in (found.x, found.x15, found.w)))
        while len(pools) < 2:
            pools.append(None)
        return pools[0], pools[1]

    def panel_placebo(self, program: Any, *, start: dt.date, end: dt.date, seed: int) -> dict[str, Any]:
        """THE PLACEBO LEG's draws: one panel run of the representative over the forward sessions [start, end] (its
        judged sessions, flat at start: the forward days need the gate's capability), with `fwd1_rule.PLACEBO_DRAWS`
        matched placebos under `seed` (XS1's law, league/xs/placebo.py). {"t": [the draws' t on the run's sessions],
        "days": how many sessions they were read on, "n": the draws}."""
        from ..equity.store import mint_equity_gate_capability
        from ..xs import runner as XR

        store_root = self.root / "equity-daily"
        gate = mint_equity_gate_capability(store_root, "forward-screen placebo leg")

        class Span(XR.Isolated):
            def span(self, code: str, params: Any, *, name: str) -> Any:
                store = self._store(gate)
                needs, run_sha = self._program(code, params, name)
                first = self._first([d for d in store.sessions("forward") if start <= d <= end],
                                    f"the forward days {start}..{end}")
                piece = store.bars("forward", history=needs.history, run_key=XR.gym_key(run_sha, "forward", first),
                                   start=first, end=end)
                return self._run(code, params, name, piece, 1.0, placebos=R.PLACEBO_DRAWS, seed=int(seed))

        run = Span(self._child(), store_root, budget_seconds=self.budget_seconds, nice=None).span(
            program.code, program.params, name=program.key)
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


def _touched(fdb: sqlite3.Connection, pid: int, old: int, new: int, days: Sequence[str]) -> bool:
    """Whether an engine change touched the judged days: a day missing under the new id, or its r or w moved."""
    rows = {str(r["day"]): r for r in forward_db.counted_days(fdb, pid, engine=new)}
    olds = {str(r["day"]): r for r in forward_db.counted_days(fdb, pid, engine=old)}
    for day in days:
        a, b = olds.get(day), rows.get(day)
        if a is None or b is None or abs(float(a["r"]) - float(b["r"])) > ENGINE_TOUCH or \
                abs(float(a["w"]) - float(b["w"])) > ENGINE_TOUCH:
            return True
    return False


class Night:
    """One night of the judge (the module docstring): `store` (the screen's own, writable), `fdb` (the forward record,
    read-only), `families` (the equity families of the swarm store, read-only), `runs` (`HouseRuns` or a test's fake),
    `rule` (`fwd1_rule.Rule`), `pin` (the clock's row), `budget` (child seconds)."""

    def __init__(self, store: sqlite3.Connection, fdb: sqlite3.Connection, families: Mapping[str, Mapping[str, Any]], *,
                 runs: Any, rule: Any, pin: Mapping[str, Any], budget: float, clock: Callable[[], float] = time.time):
        self.store, self.fdb, self.families, self.runs, self.rule = store, fdb, families, runs, rule
        self.pin = dict(pin)
        self.pin_start = dt.date.fromisoformat(str(pin["start"]))
        self.budget = float(budget)
        self.clock = clock
        self.spent = 0.0
        self.tally: Counter = Counter()
        self.gaps = _lotgaps(fdb)
        self.engine_now = forward_db.engine_now(fdb)
        self.sealed_pids = _sealed_pids(fdb)

    # ------------------------------------------------------------------------------------------------ helpers
    def _timed(self, call: Callable[[], Any]) -> Any:
        began = self.clock()
        try:
            return call()
        finally:
            self.spent += max(0.0, self.clock() - began)

    def _over(self) -> bool:
        return self.spent >= self.budget

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

    def _sides(self, pid: int, engine: int, days: Sequence[str]) -> list[float] | None:
        held = {str(r["day"]): float(r["sides"]) for r in self.store.execute(
            "SELECT day, sides FROM fwd1_sides WHERE pid=? AND engine=?", (int(pid), int(engine)))}
        out = [held.get(day) for day in days]
        return None if any(v is None for v in out) else [float(v) for v in out]   # type: ignore[arg-type]

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

    # ------------------------------------------------------------------------------------------ the own floor
    def floor(self, lin: Mapping[str, Any], program: Any) -> Mapping[str, Any] | None:
        """The representative's own floor row, computed once (None while it cannot be: the budget, or the House's
        failure: no row, asked again the next night)."""
        held = self._floor(int(lin["rep"]))
        if held is not None:
            return held
        if self._over():
            self.tally["deferred"] += 1
            return None
        typ, case = str(lin["type"]), str(lin["case_"])
        began = self.clock()
        try:
            pools = self._timed(lambda: (self.runs.etf_pools(program) if typ == "ETF" else self.runs.panel_pools(program)))
        except OwnFloorRefused as exc:       # the program's own partial series: ineligible for good, stated
            pools, why = None, f"no own floor: {str(exc)[:160]}"
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
            if _touched(self.fdb, pid, engine, self.engine_now, judged_days):
                with self.store:
                    event(self.store, "engine_switched", at=now, lineage=lineage, pid=pid, once=f"{engine}>{self.engine_now}",
                          payload={"why": "an engine change touched a pending representative's judged days", "from": engine,
                                   "to": self.engine_now, "pids": [pid], "touched": True})
                self._void(lin, "an engine change touched its judged days: one engine id a verdict", at=now)
                return "void"
            with self.store:
                event(self.store, "engine_switched", at=now, lineage=lineage, pid=pid, once=f"{engine}>{self.engine_now}",
                      payload={"why": "an engine change left its judged days as they were", "from": engine,
                               "to": self.engine_now, "pids": [pid], "touched": False})
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
            sides = self._sides(pid, engine, names)
            if sides is None:
                self.tally["no_sides"] += 1
                return None                               # the nights' hook writes them: asked again tomorrow
            g = R.haircut_bp(typ, self.gaps.get(typ, []))
            ll = self._live_like(pid, engine) if typ == "ETF" else {}
            used_ll = int(any(n in ll for n in names))
            try:
                x, x15 = R.series(typ, head, g_bp=g, sides=sides, live_like=ll)
            except ValueError:
                self.tally["unreadable"] += 1
                return None
            point = R.checkpoint(x, x15, k)
            c_g = R.C_G[typ][case]
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
                    if self._over():
                        self.tally["deferred"] += 1
                        return None
                    try:
                        seed = R.placebo_seed(self.rule.receipt_sha256, str(lin["row_hash"]))
                        block = self._timed(lambda: self.runs.panel_placebo(
                            program, start=dt.date.fromisoformat(start), end=dt.date.fromisoformat(names[-1]), seed=seed))
                    except Exception as exc:  # noqa: BLE001 - the child's or the data's: asked again tomorrow
                        self.tally["house"] += 1
                        with self.store:
                            event(self.store, "house", at=self.clock(), lineage=lineage, pid=pid,
                                  payload={"why": "the placebo leg's run did not finish", "error": type(exc).__name__})
                        return None
                    draws = int(block.get("n") or 0)
                    if int(block.get("days") or 0) != k:
                        why = (f"the placebo leg was read on {block.get('days')} sessions, not the {k} judged ones (a "
                               "day left the counted days inside the span): the leg fails closed")
                    else:
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
        pin is judged no further by this one: a receipt judges only the days after its own pin), in lineage order."""
        lineages = [dict(r) for r in self.store.execute(
            "SELECT * FROM fwd1_lineages WHERE judged=1 AND receipt=? AND lineage NOT IN (SELECT lineage FROM "
            "fwd1_verdicts) ORDER BY lineage", (self.rule.receipt_sha256,))]
        for lin in lineages:
            try:
                self.judge(lin)
            except sqlite3.Error:
                self.tally["house"] += 1
        return dict(self.tally)


# ----------------------------------------------------------------------------------------------- permits and report
def status_rows(store: sqlite3.Connection) -> list[dict[str, Any]]:
    """Every lineage with its status ("pending" | "pass" | "fail" | "void" | "ineligible" | "not_judged"), its last
    checkpoint read and its verdict's words."""
    verdicts = {str(r["lineage"]): dict(r) for r in store.execute("SELECT * FROM fwd1_verdicts")}
    last = {str(r["lineage"]): int(r["k"]) for r in store.execute(
        "SELECT lineage, MAX(k) AS k FROM fwd1_checks GROUP BY lineage")}
    engines = {(str(r["lineage"]), int(r["k"])): int(r["engine"]) for r in store.execute(
        "SELECT lineage, k, engine FROM fwd1_checks WHERE passed=1")}
    floors = {int(r["pid"]): dict(r) for r in store.execute("SELECT * FROM fwd1_floors")}
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
            status = "ineligible" if fl is not None and R.k_used(str(lin["type"]), str(lin["case_"]), fl["k_own"]) is None \
                else "pending"
        k = (v or {}).get("k") or last.get(str(lin["lineage"]))
        out.append({**lin, "status": status, "k": k, "words": (v or {}).get("words"),
                    "beside": (v or {}).get("beside"),
                    "engine": engines.get((str(lin["lineage"]), int(k))) if status == "pass" and k is not None else None})
    return out


def write_permits(root: str | Path, store: sqlite3.Connection, *, rule: Any, pin: Mapping[str, Any], at: float,
                  labels: Mapping[int, str] | None = None) -> Path:
    """THE PERMIT FILE (the module docstring, 4), atomically, 0600: {"version", "receipt", "start", "at", "lineages":
    {lineage: {"status", "type", "case", "cell", "family", "version", "run_sha", "k", "weak", "engine", "words"}}}.
    Every FWD1-judged lineage is listed (its status), so the swarm knows which take no sealed try; a pass names its
    program and the forward record's engine label its verdict was read under (`labels`: {engine id: label}). No t, no
    P&L and no figure of a program crosses."""
    from .context import write_json

    lineages: dict[str, Any] = {}
    for row in status_rows(store):
        if row["status"] == "not_judged":
            continue
        passed = row["status"] == "pass"
        lineages[str(row["lineage"])] = {
            "status": row["status"], "type": row["type"], "case": row["case_"], "cell": row["cell"],
            "family": row["family"], "version": row["version"], "run_sha": row["run_sha"] if passed else None,
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


def report(store: sqlite3.Connection, *, rule: Any, pin: Mapping[str, Any]) -> dict[str, Any]:
    """THE OPERATOR'S REPORT (the module docstring, 5): counts by type and case, the expected zero-edge passes against
    the observed, and every pass's sentence. Operator-only (it holds each pass's t and shadow P&L)."""
    rows = status_rows(store)
    by: dict[str, Counter] = {}
    read: list[tuple[str, str, int]] = []
    for row in rows:
        key = f"{row['type']}|{row['case_']}" if row["judged"] else "not_judged"
        by.setdefault(key, Counter())[row["status"]] += 1
        if row["judged"] and row["k"] is not None:
            read.append((str(row["type"]), str(row["case_"]), int(row["k"])))
    expected = R.expected_passes(rule, read)
    return {"screen": R.SCREEN, "receipt": rule.receipt_sha256, "start": pin["start"], "release": pin["release"],
            "counts": {key: dict(c) for key, c in sorted(by.items())},
            "registry": {key: {"observed": int(by.get(key, Counter())["pass"]), "expected": expected.get(key, 0.0)}
                         for key in sorted({f"{t}|{c}" for t, cs in R.CASES.items() for c in cs})},
            "passes": [{"lineage": r["lineage"], "family": r["family"], "version": r["version"], "k": r["k"],
                        "beside": r["beside"]} for r in rows if r["status"] == "pass"]}


# --------------------------------------------------------------------------------------------------------- the job
def night(root: str | Path, *, rule: Any, settings: Mapping[str, Any] | None, now: float, base: str | Path | None,
          release: str | Path | None, runs: Any = None, families: Mapping[str, Mapping[str, Any]] | None = None,
          clock: Callable[[], float] = time.time) -> dict[str, Any]:
    """One night over the state root (the module docstring): the clock's row, the lineages' first sightings, the
    judge, the permit file and the report. The receipt (counts only). `families` (tests): the equity families by id,
    in place of the swarm store's (read-only)."""
    root = Path(root)
    c = cfg(settings)
    store = open_store(root)
    fdb = forward_db.open_db(root, readonly=True)
    fdb.row_factory = sqlite3.Row
    own_runs = runs is None
    runs = runs if runs is not None else HouseRuns(root, budget_seconds=c["run_budget_seconds"], clock=clock)
    try:
        pin = pinned(store, rule, base=base, release=release, now=now)
        if families is None:
            from ..swarm.store import SwarmStore
            from . import forward_register

            families = forward_register._families(SwarmStore(root, readonly=True))
        registered = register(store, fdb, families, rule=rule, pin_start=dt.date.fromisoformat(str(pin["start"])),
                              now=now)
        judge = Night(store, fdb, families, runs=runs, rule=rule, pin=pin, budget=c["cpu_seconds_night"], clock=clock)
        tally = judge.run()
        labels = {int(r["id"]): str(r["label"]) for r in fdb.execute("SELECT id, label FROM fwd_engines")}
        write_permits(root, store, rule=rule, pin=pin, at=clock(), labels=labels)
        from .context import write_json

        write_json(root / REPORT, report(store, rule=rule, pin=pin))
        return {"start": pin["start"], "registered": registered, **{k: int(v) for k, v in tally.items()},
                "seconds": round(judge.spent, 3)}
    finally:
        if own_runs:
            runs.close()
        fdb.close()
        store.close()


def run(ctx: Any) -> dict[str, Any]:
    """THE JOB (league/ops/registry.py, after `forward_xs`): skipped with its switch off, with the forward record off or
    absent, with no pin, and inside 09:00-17:30 New York on a session; else `night`. A House failure (a store under a
    lock, a child that could not start) is a failed receipt: the runner starts it again inside its grace."""
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
    if forward_shadow.quiet(ctx.now()):
        return {"status": "skipped", "why": "inside 09:00-17:30 New York time on a session: the night's run does it"}
    if not (root / forward_db.DB).exists():
        return {"status": "skipped", "why": "no forward record yet"}
    try:
        receipt = night(root, rule=rule, settings=settings, now=ctx.now(), base=getattr(ctx, "base", None),
                        release=getattr(ctx, "release", None), clock=ctx.now)
    except sqlite3.Error as exc:
        return {"status": "failed", "error": f"a store could not be read or written ({type(exc).__name__})"}
    if int(receipt.get("house") or 0):
        ctx.alert("warning", f"forward_screen: {receipt['house']} checkpoints waited on the House's own failures (a run "
                             "the child did not finish): no program is marked, the next night asks again")
    return receipt


__all__ = ["JOB", "DB", "PERMITS", "PERMITS_VERSION", "REPORT", "MODES", "SEATS", "DEFAULTS", "BOUNDS", "VERDICTS",
           "NOT_JUDGED", "PREFERRED", "SEALED_TAGS", "SEALED_STATE", "ENGINE_TOUCH", "EVENT_KINDS", "TABLES", "SCHEMA",
           "cfg", "open_store", "event", "lot_sides", "on_run", "pinned", "representative", "family_sealed", "type_of",
           "case_of", "cell_of", "register", "OwnFloorRefused", "HouseRuns", "Night", "status_rows", "write_permits", "beside_for",
           "report", "night",
           "run"]
