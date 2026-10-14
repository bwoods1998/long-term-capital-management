"""How a live panel program trades through E1's EquityBook: the parent-side adapter (plumbing, outside the xs identity).

Owner: package H. `SCHEMA`, the constants and `Columns` / `Fetched` are the contract (package A's nightly I6 and
package J's twin read the table and the kept file).

The live process reaches the panel only through `league/equity/kinds.py`: the decider's `KINDS["panel"]` (the child,
league/xs/child.py) and H's `BOOKS["panel"]` = this module (the parent side). E1's book keeps every wall it has for a
share program (long only, cash only, a stock at most 20% of equity, the shared loss budget with stocks weighing 0.40,
the kill switch and the stops, never a forced or hand-placed trade); this module only turns a panel decision into
E1's intents and back. With no live panel instance nothing here runs, fetches or spends.

THE PARENT KNOWS THE NAMES, THE CHILD NEVER DOES. `columns` builds a day's columns: REF, then the day's members and
EVERY symbol of a lot of the instance that is open or was closed since its last called decision and is no member (a
name that left the index keeps a column, a bar, a mark and the id its lot was bought under; `elig0` False, so it is
never a candidate), the member-side columns in ascending id (D8, run key = the instance id). The child receives arrays
and ids; a target comes back as ids (JSON string keys, read with `int()`), and `intents` names the symbols.

A SESSION OF A LIVE PANEL PROGRAM (E4-SPEC 10.3): from 16:20 ET the chunked `fetch` (28 gateway calls for about 515
columns, a few chunks a tick, each chunk turned into numpy before the next is asked for), ONE fetch for the `union` of
the live panel instances' columns, read again while not `complete`; then the bars are kept (`keep`: live-bars/<day>.npz,
the bytes a decision read), the lots marked (`marks`), and the decide runs in the live process's decider (no program
code on a hold day; `ctx.derive` every day: the ineligible lots and the standing target's buys). At 08:30 the kept
symbols are fetched again and compared with the kept file (`same`, by E1's own `_bars_verdict`, handed in by the
caller: this module imports nothing of the book).

WHEN A FETCH MAY BE DECIDED ON (`complete`; E4-SPEC B13). SPY has a bar of the day, always. Every `elig0` column that
had a bar the session before has one (a row served counts, the vendor's flat volume-0 bar too: the child's `derive`
then reads it as no valid bar), except at most `MISSING_MAX` names, NONE OF THEM HELD. At the last ask before the
pre-open (`last_ask`) a held name may be among those `MISSING_MAX`: seventeen hours after the close it is read as the
Gym reads a store with no bar (not eligible, out at the open), so a halted name never blocks a rebalance and a bar that
was merely served late never sells a lot the replay keeps.

THE CLASS OF THE MONTH (`eligible`; D4): of a company's two share classes (`config.CLASS_PAIRS`) one is eligible,
chosen at the month's first session by the higher median raw dollar volume over the `config.CLASS_SESSIONS` sessions
through the session before it (ties: the lower aid). The live fetch holds those sessions, so the choice is read from
the same raw tape the store keeps.

A17 (the captain's amendment, granted for this build): for a panel program a HOLD-day fetch failure of a held name is
an alarm and never counts toward A8.5's two-failed-decides exit; a failed decide on a REBALANCE day still counts.
`HOLD_DAY_FAILS_EXIT` is that rule's one constant.

THE LIVE RULES READ A PANEL PROGRAM BY CLOSE DATE (`date_record`; E4-SPEC 10.5, pre-registered before mode "live"):
one observation a close date for EDM1, for sizing up and for the twin-gap leg; E1's `edm1` and `sized_up` are
unchanged as functions and as numbers.

Plumbing: NOT in the xs identity (`identity.XS_PLUMBING`); a fix here retires no panel lineage. It imports
`league.equity.schedule` and the evidence modules of this package and of league.equity; nothing of league.live,
league.swarm or league.ops.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import os
import time
from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import numpy as np

from ..equity import schedule as S
from ..equity import store as ES
from ..equity.ctx import as_of
from . import config
from . import ctx as X
from . import program as P
from . import store as XS

KIND = "panel"
#: A panel instance's intents a session (12 sells and 12 buys: `config.MAX_ORDERS`).
MAX_INTENTS = 24
#: Symbols a bars call: 39 x 253 bars is one page of 10,000 (40 would make every chunk two calls).
FETCH_CHUNK = 39
#: The most seconds of gateway calls the fetch makes in one of the House's ticks.
FETCH_TICK_S = 20
#: The sessions whose 16:20 fetch is kept (live-bars/<day>.npz).
KEEP_SESSIONS = 5
LIVE_BARS_DIR = "live-bars"
#: At most this many names may still lack a bar when a fetch is decided on (none of them held, but at the last ask
#: before the pre-open).
MISSING_MAX = 2
#: A17: a hold day's failure counts toward no exit (False). True would be A8.5 read literally.
HOLD_DAY_FAILS_EXIT = False
#: The tag of every intent a panel decision plans.
TAG = "xs"
#: The House exit of a lot whose name is no longer eligible (the exit intent's tag, and the closed lot's reason).
INELIGIBLE = "ineligible"
#: THE TWIN MARKER (package J writes it after its nightly twins; package G's `elane_xs.live_ready` reads it and nothing
#: else of the forward record): `<root>/xs-twins.json` = {"version": `TWINS_VERSION`, "through": day, "at",
#: "instances": {id: {"due": day | null, "last": day | null}}}: which live panel instance has its twin row. Ids and
#: days only: never an agreement bit, a return or a symbol; outside every manifest. No marker, or one two sessions
#: behind: mode "live" reads as "gate".
TWINS_FILE = "xs-twins.json"
TWINS_VERSION = "xs-twins-1"
REBALANCE_STATUS = ("planned", "hold", "failed", "late")
AUDIT_STATUS = ("ok", "mismatch", "unread")
#: The label every figure of a panel program carries in a report.
LABEL = "EQUITY (PANEL)"

#: live.sqlite's panel table, created by `EquityBook.__init__` beside E1's `SCHEMA`. One row an instance and decision
#: session. Symbols appear here (House only); nothing of this table is ever exported or committed.
SCHEMA = """
CREATE TABLE IF NOT EXISTS eq_rebalances (
    rid INTEGER PRIMARY KEY, instance TEXT NOT NULL, family TEXT NOT NULL, version INTEGER NOT NULL,
    decided_day TEXT NOT NULL, exec_day TEXT NOT NULL, at TEXT NOT NULL,        -- open | close
    called INTEGER NOT NULL,            -- 1: the program was asked (a rebalance decision day, D9); 0: a hold day
    targets TEXT NOT NULL,              -- JSON [[symbol, weight]] (symbols: House only): the target this day's orders
                                        -- were planned from (a called day's own; on a hold day THE STANDING TARGET)
    standing INTEGER NOT NULL DEFAULT 0,-- 1: a hold day that planned buys from the standing target
    n_names INTEGER NOT NULL, n_sells INTEGER NOT NULL, n_buys INTEGER NOT NULL, n_skipped INTEGER NOT NULL,
    skipped TEXT NOT NULL DEFAULT '[]', -- JSON [[symbol, why]]
    equity TEXT,                        -- the sleeve equity the decision's ctx carried
    budget TEXT,                        -- the sleeve budget the decision's ctx carried (a buy's weight = usd / budget)
    extra TEXT NOT NULL DEFAULT '[]',   -- JSON [symbol]: the columns beside REF and the day's members (lots held or
                                        -- closed that day whose name is no member): what rebuilds the decision's columns
    ctx_sha TEXT, bars_sha TEXT, fetch TEXT NOT NULL DEFAULT '{}',   -- {calls, seconds, symbols, missing, late, dropped}
    audit TEXT,                         -- NULL | ok | mismatch | unread (the 08:30 re-read)
    status TEXT NOT NULL,               -- planned | hold | failed | late
    why TEXT, created_at REAL NOT NULL,
    UNIQUE (instance, decided_day));
CREATE INDEX IF NOT EXISTS eq_rebalances_day ON eq_rebalances(decided_day);
"""
#: The columns of `eq_rebalances` a `rebalance_row` carries (everything but `rid`, which the table gives, and `audit`,
#: which only the 08:30 re-read writes).
REBALANCE_COLUMNS = ("instance", "family", "version", "decided_day", "exec_day", "at", "called", "targets", "standing",
                     "n_names", "n_sells", "n_buys", "n_skipped", "skipped", "equity", "budget", "extra", "ctx_sha",
                     "bars_sha", "fetch", "status", "why", "created_at")
#: `eq_instances` (E1's table) gains this column, by ALTER TABLE guarded by PRAGMA table_info (`INSTANCE_KIND_DDL` is
#: run only when the column is absent). An E1 row reads "equity".
INSTANCE_KIND_COLUMN = "kind"
INSTANCE_KIND_DDL = "ALTER TABLE eq_instances ADD COLUMN kind TEXT NOT NULL DEFAULT 'equity'"

ZERO = Decimal(0)
CENT = Decimal("0.01")
#: A weight as `eq_rebalances.targets` keeps it (a target's own weight, to the float's last useful place).
WEIGHT_PLACES = 9
#: A sd of per-date returns at or under this is no sd (the screen's own floor for one).
SD_FLOOR = 1e-12


class ColumnsRefused(ValueError):
    """A day's columns cannot be built for an instance (a held symbol the universe does not know, an asset table that
    cannot be read): the House could not ask, never the program's failure."""


@dataclass(frozen=True)
class Columns:
    """One instance's columns of one decision day, in the order every array of that day is in.

    `symbols`: REF, then the member columns in ascending id, then nothing else: `extra` names which of the member-side
    symbols are no member today (a held or just-closed name that left the index). `aids` int32 (m,). `ids` int32 (m -
    12,): D8, from the whole asset table under the run key (the instance id). `elig0` bool (m,): the parent's part of
    eligibility (`store.PanelBars.elig0`'s row for the day, the class of the month still to come: `eligible`; False
    for REF and for `extra`). `sector_perm`, `dither_key`: the run's. Parent side only: never pickled to a child."""

    symbols: tuple[str, ...]
    aids: np.ndarray
    ids: np.ndarray
    elig0: np.ndarray
    sector_perm: np.ndarray
    dither_key: bytes
    extra: tuple[str, ...]


@dataclass(frozen=True)
class Fetched:
    """A day's fetch as arrays in a `Columns`' order: `days` int32 (n,) (the 253 sessions through the day), `raw`
    float64 (n, m, 5), `all` float64 (n, m, 4), `meta` {calls, seconds, symbols, missing, late, dropped (rows the
    venue served on a day that is no session or with a field that is no number: `ctx.rows_to_arrays`), fetched_at}."""

    days: np.ndarray
    raw: np.ndarray
    all: np.ndarray
    meta: Mapping[str, Any]


# ------------------------------------------------------------------------------------------------------ small readers
def _day(value: Any) -> dt.date:
    return value if isinstance(value, dt.date) else dt.date.fromisoformat(str(value)[:10])


def _get(row: Any, name: str, default: Any = None) -> Any:
    """A field of a lot or a row, whichever it is (E1's `Lot` dataclass, or its `eq_lots` row)."""
    if isinstance(row, Mapping):
        return row.get(name, default)
    return getattr(row, name, default)


def _dec(value: Any) -> Decimal | None:
    """A finite Decimal from a row's string or number (str first: never a float's binary noise), else None."""
    if value is None or isinstance(value, bool) or value == "":
        return None
    try:
        out = value if isinstance(value, Decimal) else Decimal(str(value).strip())
    except (ArithmeticError, ValueError):
        return None
    return out if out.is_finite() else None


def _open(lot: Any) -> bool:
    return str(_get(lot, "status") or "open") in ("open", "closing")


def _side(cols: Columns) -> tuple[str, ...]:
    """The member-side symbols of `cols` (everything after REF), in the columns' own order."""
    return tuple(cols.symbols[len(config.REF):])


def slots(cols: Columns) -> dict[str, int]:
    """{symbol: its salted id} of the member-side columns (the parent's own map: never sent, never recorded)."""
    return {symbol: int(i) for symbol, i in zip(_side(cols), np.asarray(cols.ids).tolist())}


def sessions_through(day: dt.date, n: int = config.DERIVE_SESSIONS) -> list[dt.date]:
    """The last `n` NYSE sessions through `day` (the window a decision of `day` reads: 253 closes, 252 returns)."""
    day = _day(day)
    first = day - dt.timedelta(days=2 * int(n) + 30)
    return [d for d, _ in ES.nyse_sessions(first, day)][-int(n):]


# ------------------------------------------------------------------------------------------------------- the columns
def columns(root: str | Path, instance: str, day: dt.date, *, held: Sequence[str] | Mapping[str, Any] = (),
            renamed: Mapping[str, str] | None = None) -> Columns:
    """The instance's columns of `day` (`store.Universe`, the House salt, run key = the instance id). `held`: the
    symbols of its lots that are open, or were closed since its last called decision; as a mapping {symbol: the day its
    lot was opened} a name the universe no longer lists on `day` is found by the day it was bought. A held symbol no
    asset ever traded under is `ColumnsRefused`. The class of the month is not applied here (`eligible`: it reads the
    fetch).

    `renamed` {the lot's symbol now: the symbol it was bought under} (A TICKER CHANGE INSIDE A HELD LOT: E1 books the
    venue's NC activity onto the lot the day it posts, and the membership job reads the new ticker days later, after
    two reads of its sources). A held symbol the universe does not know is then found by the one it was bought
    under, and its column carries the lot's symbol NOW (the name the venue serves its bars by): the member column of
    its asset when the index still lists the old ticker, else a column of its own. Its id is its asset's, so the lot
    keeps the slot it was bought under. Without this every decide of the instance was "the House could not ask"
    until the universe caught up: the lot was judged by nothing but its maximum hold."""
    day = _day(day)
    universe = XS.Universe(root)
    members: dict[str, int] = {}
    for aid, symbol in universe.members(day):
        if str(symbol) not in config.REF:
            members[str(symbol)] = int(aid)
    ahead = set(members.values())
    probe = day
    for _ in range(config.MEMBER_AHEAD):
        probe = S.next_session(probe)
        try:
            ahead &= {int(aid) for aid, _ in universe.members(probe)}
        except (LookupError, ValueError):
            break   # past what the membership knows: as at the last day it knows (the pre-registration's 3.1)
    opened = dict(held) if isinstance(held, Mapping) else {str(s): None for s in held}
    before = {str(new).upper(): str(old).upper() for new, old in (renamed or {}).items() if old}
    extra: dict[str, int] = {}

    def find(name: str, lot_symbol: str) -> int | None:
        for when in (day, opened.get(lot_symbol)):
            if when is None:
                continue
            try:
                return int(universe.aid(name, _day(when)))
            except (LookupError, ValueError):
                continue
        return None

    for symbol in sorted(str(s).upper() for s in opened):
        if symbol in members or symbol in config.REF:
            continue
        aid = find(symbol, symbol)
        if aid is None and symbol in before:
            old = before[symbol]
            if old in members:                 # the index still lists the old ticker: the asset's column, renamed
                members[symbol] = members.pop(old)
                continue
            aid = find(old, symbol)
        if aid is None:
            raise ColumnsRefused(f"the held symbol {symbol} is no asset of the panel's universe on {day.isoformat()}")
        if aid in members.values():
            raise ColumnsRefused(f"the held symbol {symbol} names an asset the day's members hold under another ticker")
        extra[symbol] = aid
    tradable = {str(s) for s in universe.tradable(day)}
    side = {**members, **extra}
    names = sorted(side, key=lambda s: side[s])
    key = XS.run_salt(XS.read_salt(root), str(instance))
    ids = np.asarray(XS.ids_for([side[s] for s in names], key, table=universe.table()), dtype=np.int64)
    if ids.shape != (len(names),) or len(set(ids.tolist())) != len(names):
        raise ColumnsRefused("the panel's ids are not one a column")
    order = np.argsort(ids, kind="stable")
    names = [names[int(k)] for k in order]
    ref = len(config.REF)
    elig0 = np.zeros(ref + len(names), dtype=bool)
    for k, symbol in enumerate(names):
        elig0[ref + k] = symbol in members and members[symbol] in ahead and symbol in tradable
    aids = np.array([*range(1, ref + 1), *(side[s] for s in names)], dtype=np.int32)
    return Columns(symbols=(*config.REF, *names), aids=aids, ids=ids[order].astype(np.int32), elig0=elig0,
                   sector_perm=np.asarray(XS.sector_perm(key)), dither_key=bytes(XS.dither_key(key)),
                   extra=tuple(sorted(extra)))


def union(many: Sequence[Columns]) -> Columns:
    """ONE fetch for every live panel instance: REF, then every member-side symbol of `many` in symbol order, `elig0`
    true where any instance's is, `extra` the union of theirs. It names no run: no id, no aid, no key (a fetch needs
    symbols only, and `complete` their `elig0`)."""
    elig: dict[str, bool] = {}
    extra: set[str] = set()
    for cols in many:
        flags = np.asarray(cols.elig0, dtype=bool)[len(config.REF):].tolist()
        for symbol, flag in zip(_side(cols), flags):
            elig[symbol] = bool(flag) or elig.get(symbol, False)
        extra |= set(cols.extra)
    names = sorted(elig)
    return Columns(symbols=(*config.REF, *names), aids=np.zeros(0, dtype=np.int32), ids=np.zeros(0, dtype=np.int32),
                   elig0=np.array([False] * len(config.REF) + [elig[s] for s in names], dtype=bool),
                   sector_perm=np.zeros(0, dtype=np.int8), dither_key=b"", extra=tuple(sorted(extra)))


def view(fetched: Fetched, symbols: Sequence[str], cols: Columns) -> Fetched:
    """The columns of `cols`, in its order, out of a fetch whose columns are `symbols` (the union's, or a kept file's).
    KeyError names a symbol the fetch does not hold."""
    where = {str(s): k for k, s in enumerate(symbols)}
    lacking = [s for s in cols.symbols if s not in where]
    if lacking:
        raise KeyError(f"the fetch holds no column of {', '.join(lacking[:5])}")
    take = np.array([where[s] for s in cols.symbols], dtype=np.int64)
    return Fetched(days=fetched.days, raw=np.asarray(fetched.raw)[:, take, :], all=np.asarray(fetched.all)[:, take, :],
                   meta=dict(fetched.meta))


def called(day: dt.date, needs: Mapping[str, Any]) -> bool:
    """D9: whether the program is asked at the close of `day` (`config.decision_due` on its NEEDS)."""
    return bool(config.decision_due(_day(day), str(needs["rebalance"]), int(needs.get("weekday") or 0)))


def needs_of(needs: Any) -> P.Needs:
    """NEEDS as the child's load answered them (a dict) as a `program.Needs`."""
    if isinstance(needs, P.Needs):
        return needs
    return P.Needs(**{name: needs[name] for name in P.NEEDS_KEYS})


# --------------------------------------------------------------------------------------------------------- the fetch
def fetch(market: Any, cols: Columns | Sequence[str], day: dt.date, *, progress: dict | None = None,
          now: Callable[[], float] | None = None) -> Fetched | None:
    """The day's bars for `cols.symbols`, raw then all, 253 sessions ending `day`, through `market.bars` in chunks of
    `FETCH_CHUNK` symbols, each chunk turned into numpy (`ctx.rows_to_arrays`) and its dicts dropped before the next
    is asked for. It keeps its place in `progress` between calls and makes at most `FETCH_TICK_S` seconds of calls a
    call (always one chunk): None while unfinished. A call that raises keeps its place: the next call asks the same
    chunk again. (So `progress` is filled before the first call is made: a caller tells "still being read" from
    "could not be read" by whether the call RETURNED None, never by `progress` alone.)"""
    day = _day(day)
    symbols = tuple(str(s) for s in getattr(cols, "symbols", cols))
    clock = now or time.time
    state = progress if progress is not None else {}
    key = (day.isoformat(), symbols)
    if state.get("key") != key:
        sessions = sessions_through(day)
        state.clear()
        state.update(key=key, next=0, calls=0, seconds=0.0, dropped=0, start=sessions[0].isoformat(),
                     end=(day + dt.timedelta(days=1)).isoformat(),
                     days=np.array([ES.ordinal(d) for d in sessions], dtype=np.int32),
                     raw=np.full((len(sessions), len(symbols), 5), np.nan, dtype=np.float64),
                     all=np.full((len(sessions), len(symbols), 4), np.nan, dtype=np.float64))
    began = clock()
    first = True
    while state["next"] < len(symbols):
        if not first and clock() - began >= FETCH_TICK_S:
            return None
        first = False
        at = int(state["next"])
        chunk = list(symbols[at:at + FETCH_CHUNK])
        t0 = clock()
        raw_rows = market.bars(chunk, timeframe="1Day", start=state["start"], end=state["end"], adjustment="raw")
        all_rows = market.bars(chunk, timeframe="1Day", start=state["start"], end=state["end"], adjustment="all")
        days, raw, adj = X.rows_to_arrays(raw_rows or {}, all_rows or {}, day=day, columns=chunk, count=state)
        del raw_rows, all_rows
        _place(state, at, np.asarray(days), np.asarray(raw, dtype=np.float64), np.asarray(adj, dtype=np.float64))
        state["calls"] += 2
        state["seconds"] += max(0.0, clock() - t0)
        state["next"] = at + len(chunk)
    meta = {"calls": int(state["calls"]), "seconds": round(float(state["seconds"]), 3), "symbols": len(symbols),
            "missing": None, "late": False, "dropped": int(state.get("dropped") or 0), "fetched_at": float(clock())}
    return Fetched(days=state["days"], raw=state["raw"], all=state["all"], meta=meta)


def _place(state: dict, at: int, days: np.ndarray, raw: np.ndarray, adj: np.ndarray) -> None:
    """One chunk's arrays into the day's, by session: a session the chunk does not carry stays NaN, one the day's
    window does not hold is dropped."""
    want = state["days"]
    if days.ndim != 1 or raw.shape[:1] != days.shape or adj.shape[:1] != days.shape or raw.shape[1] != adj.shape[1]:
        raise ValueError("a chunk's arrays do not agree on their shapes")
    spot = np.searchsorted(want, days)
    ok = (spot < want.shape[0]) & (want[np.minimum(spot, want.shape[0] - 1)] == days)
    state["raw"][spot[ok], at:at + raw.shape[1], :] = raw[ok]
    state["all"][spot[ok], at:at + adj.shape[1], :] = adj[ok]


def _served(raw: np.ndarray, row: int) -> np.ndarray:
    """Which columns were served a bar of session `row` (a finite raw close: the vendor's flat volume-0 bar counts)."""
    return np.isfinite(np.asarray(raw)[row, :, 3])


def complete(fetched: Fetched, cols: Columns, lots: Sequence[Any], *, last_ask: bool = False) -> tuple[bool, list[str]]:
    """Whether the fetch may be decided on, and the symbols still missing (the module docstring): SPY has a bar of the
    day AND every `elig0` column that had a bar the session before has one, except at most `MISSING_MAX` names, none
    of them held (`lots`: the open lots; their symbols). With `last_ask` (the last ask before the pre-open) a held name
    may be among the `MISSING_MAX`. SPY never."""
    raw = np.asarray(fetched.raw)
    if raw.shape[0] < 2 or raw.shape[1] != len(cols.symbols):
        return False, [config.REF[config.MARKET_COLUMN]]
    today, before = _served(raw, -1), _served(raw, -2)
    elig0 = np.asarray(cols.elig0, dtype=bool)
    missing = [cols.symbols[int(k)] for k in np.flatnonzero(elig0 & before & ~today)]
    held = {str(_get(lot, "symbol") or "").upper() for lot in lots if _open(lot)}
    # A held name is watched whether or not it is still a candidate (a name that left keeps its column and its bar).
    where = {s: k for k, s in enumerate(cols.symbols)}
    for symbol in sorted(held):
        k = where.get(symbol)
        if k is not None and before[k] and not today[k] and symbol not in missing:
            missing.append(symbol)
    if not today[config.MARKET_COLUMN]:
        return False, [config.REF[config.MARKET_COLUMN], *missing]
    if len(missing) > MISSING_MAX:
        return False, missing
    if not last_ask and any(symbol in held for symbol in missing):
        return False, missing
    return True, missing


def _canonical(array: np.ndarray) -> bytes:
    """An array's bytes with one NaN and one zero (a NaN made by arithmetic may carry another bit pattern)."""
    out = np.array(array, dtype=np.float64, copy=True)
    out[np.isnan(out)] = np.nan
    return np.ascontiguousarray(out + 0.0).tobytes()


def bars_sha(fetched: Fetched, cols: Columns | Sequence[str]) -> str:
    """One decision's provenance: sha256 over the columns' symbols, the sessions, the raw array's bytes and the as-of
    OHLC (`league.equity.ctx.as_of`: 4 decimals; a column with no bar of the day takes its last bar's factor), columns
    in `cols` order."""
    symbols = tuple(str(s) for s in getattr(cols, "symbols", cols))
    raw, adj = np.asarray(fetched.raw, dtype=np.float64), np.asarray(fetched.all, dtype=np.float64)
    h = hashlib.sha256()
    h.update(json.dumps(list(symbols), separators=(",", ":")).encode())
    h.update(np.ascontiguousarray(np.asarray(fetched.days, dtype=np.int32)).tobytes())
    h.update(_canonical(raw))
    for k in range(raw.shape[1]):
        ok = np.isfinite(raw[:, k, 3]) & np.isfinite(adj[:, k, 3]) & (raw[:, k, 3] > 0) & (adj[:, k, 3] > 0)
        hits = np.flatnonzero(ok)
        if not hits.size:
            h.update(b"-")
            continue
        row = int(hits[-1])
        h.update(_canonical(as_of(adj[:, k, :], raw[row, k, 3], adj[row, k, 3])))
    return h.hexdigest()


# ------------------------------------------------------------------------------------------------- the kept fetch
def _kept_path(root: str | Path, day: dt.date) -> Path:
    return Path(root) / LIVE_BARS_DIR / f"{_day(day).isoformat()}.npz"


def keep(root: str | Path, day: dt.date, fetched: Fetched, symbols: Sequence[str]) -> Path:
    """Write the fetch a decision of `day` read to `<root>/live-bars/<day>.npz` (symbols, days, raw, all, fetched_at;
    600; atomic) and drop the files older than `KEEP_SESSIONS` sessions. House only; outside every manifest."""
    path = _kept_path(root, day)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path.parent, 0o700)
    except OSError:
        pass
    names = [str(s) for s in symbols]
    if np.asarray(fetched.raw).shape[1] != len(names):
        raise ValueError("the fetch and its symbols differ in their columns")
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as out:
        np.savez(out, symbols=np.array(names, dtype=np.str_), days=np.asarray(fetched.days, dtype=np.int32),
                 raw=np.asarray(fetched.raw, dtype=np.float64), all=np.asarray(fetched.all, dtype=np.float64),
                 fetched_at=np.float64((fetched.meta or {}).get("fetched_at") or 0.0))
        out.flush()
        os.fsync(out.fileno())
    os.replace(tmp, path)
    files = sorted(p for p in path.parent.glob("*.npz") if _is_day(p.stem))
    for old in files[:-KEEP_SESSIONS]:
        try:
            old.unlink()
        except OSError:
            pass
    return path


def _is_day(text: str) -> bool:
    try:
        dt.date.fromisoformat(text)
    except ValueError:
        return False
    return True


def kept(root: str | Path, day: dt.date) -> tuple[tuple[str, ...], Fetched] | None:
    """The kept file of `day` as (symbols, Fetched), or None when there is none or it cannot be read (the morning
    audit's and the nightly I6's reader)."""
    path = _kept_path(root, day)
    if not path.is_file():
        return None
    try:
        with np.load(path, allow_pickle=False) as data:
            symbols = tuple(str(s) for s in data["symbols"].tolist())
            fetched = Fetched(days=data["days"], raw=data["raw"], all=data["all"],
                              meta={"fetched_at": float(data["fetched_at"]), "symbols": len(symbols), "source": "kept"})
    except (OSError, ValueError, KeyError):
        return None
    if fetched.raw.ndim != 3 or fetched.raw.shape[1] != len(symbols) or fetched.all.shape[:2] != fetched.raw.shape[:2]:
        return None
    return symbols, fetched


def _series(days: Sequence[str], raw: np.ndarray, adj: np.ndarray) -> tuple[dict, dict]:
    """One column as E1's audit reads a symbol: ({day: (o, h, l, c, v)}, {day: (o, h, l, c)}), sessions with no bar
    left out."""
    rows = raw.tolist()
    alls = adj.tolist()
    old_raw = {d: tuple(r) for d, r in zip(days, rows) if not math.isnan(r[3])}
    old_all = {d: tuple(r) for d, r in zip(days, alls) if not math.isnan(r[3])}
    return old_raw, old_all


def _fresh(series: Mapping[str, tuple], keys: Sequence[str]) -> dict[str, dict]:
    return {d: dict(zip(keys, values)) for d, values in series.items()}


def _same(a: np.ndarray, b: np.ndarray) -> bool:
    return a.shape == b.shape and bool(np.array_equal(a, b, equal_nan=True))


def same(old: Fetched, again: Fetched, cols: Columns | Sequence[str], *,
         verdict: Callable[..., str]) -> dict[str, list[str]]:
    """The kept fetch against a later reading of the same columns: {"mismatch": [symbols], "volume": [symbols], "late":
    [symbols]}. `verdict` is E1's `league.equity.live._bars_verdict`, handed in by the caller: its rule, its tolerance
    (the vendor's rounding) and nothing of the panel's; a volume-only difference is a note, never a mismatch. A column
    whose prices are bit for bit the same is not handed to it (its answer is then "ok", or "volume"). LATE: a column
    the kept fetch held no bar of the day for and the later reading does (the decision read it as no bar: `complete`
    let at most `MISSING_MAX` such names by, and the row's `fetch` counts them): a note, never a mismatch. A column
    with no bar of the day in either reading is compared at its own last bar (the as-of factor's row)."""
    symbols = tuple(str(s) for s in getattr(cols, "symbols", cols))
    out: dict[str, list[str]] = {"mismatch": [], "volume": [], "late": []}
    a_raw, a_all = np.asarray(old.raw, dtype=np.float64), np.asarray(old.all, dtype=np.float64)
    b_raw, b_all = np.asarray(again.raw, dtype=np.float64), np.asarray(again.all, dtype=np.float64)
    if not _same(np.asarray(old.days), np.asarray(again.days)) or a_raw.shape != b_raw.shape \
            or a_raw.shape[1] != len(symbols):
        out["mismatch"] = list(symbols)
        return out
    days = [ES.from_ordinal(int(d)).isoformat() for d in np.asarray(old.days).tolist()]
    for k, symbol in enumerate(symbols):
        if _same(a_raw[:, k, :4], b_raw[:, k, :4]) and _same(a_all[:, k, :], b_all[:, k, :]):
            if not _same(a_raw[:, k, 4], b_raw[:, k, 4]):
                out["volume"].append(symbol)
            continue
        old_raw, old_all = _series(days, a_raw[:, k, :], a_all[:, k, :])
        new_raw, new_all = _series(days, b_raw[:, k, :], b_all[:, k, :])
        if days[-1] not in old_raw and days[-1] in new_raw:
            out["late"].append(symbol)
            continue
        if not old_raw and not new_raw:
            continue
        day = days[-1] if days[-1] in old_raw else (max(old_raw) if old_raw else days[-1])
        answer = verdict(old_raw, old_all, _fresh(new_raw, ("o", "h", "l", "c", "v")),
                         _fresh(new_all, ("o", "h", "l", "c")), day)
        if answer == "volume":
            out["volume"].append(symbol)
        elif answer != "ok":
            out["mismatch"].append(symbol)
    return out


# ------------------------------------------------------------------------------------------------ the decide's job
def eligible(cols: Columns, fetched: Fetched, day: dt.date) -> np.ndarray:
    """`cols.elig0` with THE CLASS OF THE MONTH applied (the module docstring; D4): of each pair of `config.CLASS_PAIRS`
    whose two classes are members on `day`, the one with the lower median raw dollar volume (close x volume, valid
    bars only) over the `config.CLASS_SESSIONS` sessions before the month's first session is not eligible (ties: the
    higher aid is not). A pair with one member class is left as it is."""
    day = _day(day)
    out = np.array(cols.elig0, dtype=bool, copy=True)
    where = {s: k for k, s in enumerate(cols.symbols)}
    days = np.asarray(fetched.days)
    raw = np.asarray(fetched.raw, dtype=np.float64)
    start = int(np.searchsorted(days, ES.ordinal(day.replace(day=1))))
    lo = max(0, start - config.CLASS_SESSIONS)
    aids = np.asarray(cols.aids).tolist()

    def volume(k: int) -> float:
        close, shares = raw[lo:start, k, 3], raw[lo:start, k, 4]
        ok = np.isfinite(close) & np.isfinite(shares) & (close > 0) & (shares > 0)
        return float(np.median(close[ok] * shares[ok])) if ok.any() else 0.0

    for a, b in config.CLASS_PAIRS:
        if a not in where or b not in where or a in cols.extra or b in cols.extra:
            continue
        ka, kb = where[a], where[b]
        va, vb = volume(ka), volume(kb)
        first = va > vb or (va == vb and aids[ka] <= aids[kb])
        out[kb if first else ka] = False
    return out


def _column_of(cols: Columns) -> dict[str, int]:
    return {s: k for k, s in enumerate(cols.symbols)}


def _ctx_tag(lot: Any) -> str:
    """A lot's tag AS A PROGRAM IS TOLD IT: what the Gym's engine tells it, which tags no lot of its own orders ("")
    and tags a House exit of an ineligible name `INELIGIBLE`. Every intent of a panel decision is stamped `TAG` (the
    book's own mark of who planned it), E1's fill copies the intent's tag onto the lot, and the ctx's bytes hash a
    lot's tag: handed through, a live program read "xs" on every lot it held where its replay reads "", so no live
    decision's `ctx_sha` with a position could equal its twin's, and one line of program code could tell live from
    replay (the pre-registration's C1: what a program sees is identical live and in replay)."""
    tag = str(_get(lot, "tag") or "")
    return "" if tag == TAG else tag


def inputs(cols: Columns, fetched: Fetched, *, day: dt.date, needs: Mapping[str, Any], lots: Sequence[Any],
           closed: Sequence[Any], rejects: Sequence[str], cash: Any, equity: Any, budget: Any,
           params: Mapping[str, Any]) -> Any:
    """The decision's `league.xs.ctx.Inputs` (`ctx.inputs_from_arrays`): what the child is sent. `lots`: the
    instance's open lots (E1's `Lot`, or its row); `closed`: its lots closed since its last called decision. A row
    names its lot's COLUMN, never its symbol; the dollars and the quantity reach the child (which turns them into the
    dithered weight and return a program sees), never a program."""
    day = _day(day)
    where = _column_of(cols)
    iso = day.isoformat()
    positions = []
    for lot in lots:
        if not _open(lot):
            continue
        symbol = str(_get(lot, "symbol") or "").upper()
        if symbol not in where:
            raise ColumnsRefused(f"an open lot's symbol has no column on {iso}")
        qty = _dec(_get(lot, "qty")) or ZERO
        entry = _dec(_get(lot, "entry_px")) or ZERO
        mark = _dec(_get(lot, "mark"))
        price = mark if mark is not None and mark > 0 else entry
        positions.append({"lid": int(_get(lot, "lid")), "col": where[symbol], "qty": float(qty),
                          "value": float(qty * price), "entry_value": float(_dec(_get(lot, "entry_notional")) or ZERO),
                          "held_sessions": S.sessions_between(str(_get(lot, "opened_day")), iso),
                          "at": str(_get(lot, "entry_at") or "open"), "tag": _ctx_tag(lot)})
    done = []
    for lot in closed:
        symbol = str(_get(lot, "symbol") or "").upper()
        if symbol not in where:
            continue   # its name has no column today (closed before the columns were built): the program reads no slot
        notional = _dec(_get(lot, "entry_notional")) or ZERO
        net = (_dec(_get(lot, "cash")) or ZERO) / notional if notional > 0 else ZERO
        reason = str(_get(lot, "reason") or "")
        done.append({"lid": int(_get(lot, "lid")), "col": where[symbol], "net_ret": round(float(net), 4),
                     "held_sessions": S.sessions_between(str(_get(lot, "opened_day")),
                                                         str(_get(lot, "exit_day") or iso)),
                     "reason": reason if reason in ("program", "max_hold") else "house",
                     "tag": INELIGIBLE if reason == INELIGIBLE else _ctx_tag(lot)})
    return X.inputs_from_arrays(np.asarray(fetched.days), np.asarray(fetched.raw), np.asarray(fetched.all), day=day,
                                elig0=eligible(cols, fetched, day), ids=np.asarray(cols.ids),
                                dither_key=cols.dither_key, sector_perm=np.asarray(cols.sector_perm),
                                needs=needs_of(needs), positions=tuple(positions), closed=tuple(done),
                                rejects=tuple(str(r) for r in rejects), cash=float(cash), equity=float(equity),
                                budget=float(budget), params=params)


def committed(lots: Sequence[Any], *, symbol: str | None = None, working: Sequence[Any] = ()) -> Decimal:
    """THE CONSTANT-WEIGHT SIZING BOOK, live as in the Gym (the pinned pre-registration's C3 and C8; league/xs/engine.py
    `_committed`): the ENTRY notionals of the instance's open lots (of one symbol's, with `symbol`), plus `working`:
    the dollars of its buys still working. What a panel buy's room is read on: no mark and no P&L is in it, so a
    held name that rose takes no room from the next lot and a loss gives none back. (E1's own book reads a sleeve at
    its marks, which is right for one ETF lot and cut the fifth name of a basket whose four held names had gained.)"""
    want = None if symbol is None else str(symbol).upper()
    total = ZERO
    for lot in lots:
        if _open(lot) and (want is None or str(_get(lot, "symbol") or "").upper() == want):
            total += _dec(_get(lot, "entry_notional")) or ZERO
    for usd in working:
        total += _dec(usd) or ZERO
    return total


def sleeve_room(budget: Any, lots: Sequence[Any], *, working: Sequence[Any] = ()) -> Decimal:
    """The sleeve's free room for new lots: `budget` less `committed`, never below zero. What the sizing reads as
    the sleeve's free cash, and what a program is told as `ctx.cash` (its `ctx.equity` is this plus its lots at
    their marks)."""
    return max(ZERO, (_dec(budget) or ZERO) - committed(lots, working=working))


def last_called(rows: Sequence[Mapping[str, Any]], *, before: str | None = None) -> str:
    """The day of the instance's last decision in which its program was asked (a called row with a `ctx_sha`), "" when
    none: what "since the last call" means for a ctx's `closed` and `rejects`."""
    days = [str(r["decided_day"]) for r in rows if int(r.get("called") or 0) and r.get("ctx_sha")
            and (before is None or str(r["decided_day"]) < before)]
    return max(days) if days else ""


def standing(rows: Sequence[Mapping[str, Any]], cols: Columns, lots: Sequence[Any], day: dt.date, *,
             pending: Sequence[str] = ()) -> dict | None:
    """THE STANDING TARGET for a hold day: the instance's last CALLED `eq_rebalances` row whose status is "planned",
    as {target {id: w}, at, exited [id]} (`exited`: the ids the House has exited since that row: a lot of the id closed
    after it for any reason but the program's own sale); None when there is none or every id is held, has a buy
    working (`pending`: symbols) or was exited. A decide recorded late never becomes it (its status is "late"), nor
    one whose bars read again in the morning differed (its `audit` is "mismatch": its buys were cancelled, and a target
    made on bars that did not hold is not planned again); a hold, a None or a failed decide leaves the one before
    standing. `lots`: every lot of the instance, open and closed."""
    iso = _day(day).isoformat()
    row = None
    for r in sorted(rows, key=lambda r: str(r["decided_day"])):
        if int(r.get("called") or 0) and r.get("status") == "planned" and str(r["decided_day"]) < iso \
                and r.get("audit") != "mismatch":
            row = r
    if row is None:
        return None
    ids = slots(cols)
    since = str(row["decided_day"])
    try:
        pairs = json.loads(row.get("targets") or "[]")
    except ValueError:
        return None
    target = {ids[str(s)]: float(w) for s, w in pairs if str(s) in ids and str(s) not in cols.extra}
    held = {str(_get(lot, "symbol") or "").upper() for lot in lots if _open(lot)}
    exited = sorted({ids[symbol] for lot in lots for symbol in (str(_get(lot, "symbol") or "").upper(),)
                     if not _open(lot) and symbol in ids and str(_get(lot, "reason") or "") != "program"
                     and str(_get(lot, "exit_day") or "") > since})
    waiting = {str(s).upper() for s in pending}
    by_id = {i: s for s, i in ids.items()}
    wanted = [i for i in target if by_id[i] not in held and by_id[i] not in waiting and i not in exited]
    if not wanted:
        return None
    return {"target": {i: w for i, w in target.items() if by_id[i] not in waiting},
            "at": str(row.get("at") or "open"), "exited": exited}


def intents(answer: Mapping[str, Any], cols: Columns, lots: Sequence[Any]) -> list[dict[str, Any]]:
    """The child's orders as E1 intents: `{"sell": lid, "at", "tag": "xs"}`, `{"buy": SYM, "usd", "at", "tag": "xs"}`.
    An order that names no lot of the instance, an id with no column or one that is no candidate today is left out
    (`skipped` says why)."""
    out, _ = _orders(answer, cols, lots)
    return out


def skipped(answer: Mapping[str, Any], cols: Columns, lots: Sequence[Any]) -> list[list[str]]:
    """[[symbol or "", why]]: the child's own rejects of this decision (the KEEP rule's: under the minimum order, the
    order cap) and the orders `intents` left out. `eq_rebalances.skipped`; the program reads the whys in its next
    ctx's rejects."""
    _, out = _orders(answer, cols, lots)
    return [["", str(r)[:200]] for r in (answer.get("rejects") or [])][:MAX_INTENTS] + out


def _orders(answer: Mapping[str, Any], cols: Columns, lots: Sequence[Any]) -> tuple[list[dict], list[list[str]]]:
    by_id = {i: s for s, i in slots(cols).items()}
    elig0 = dict(zip(cols.symbols, np.asarray(cols.elig0, dtype=bool).tolist()))
    mine = {int(_get(lot, "lid")) for lot in lots if _open(lot)}
    out: list[dict] = []
    left: list[list[str]] = []
    for order in list(answer.get("orders") or [])[:MAX_INTENTS]:
        if not isinstance(order, Mapping):
            left.append(["", "an order that is not a dict"])
            continue
        at = order.get("at")
        if at not in P.AT:
            left.append(["", f"at {at!r}: an order fills at the open or the close"])
            continue
        if "sell" in order:
            try:
                lid = int(order["sell"])
            except (TypeError, ValueError):
                lid = -1
            if lid not in mine:
                left.append(["", "a sell that names no open lot of this program"])
                continue
            out.append({"sell": lid, "at": at, "tag": TAG})
        elif "buy_id" in order:
            try:
                symbol = by_id.get(int(order["buy_id"]))
            except (TypeError, ValueError):
                symbol = None
            usd = _dec(order.get("usd"))
            if symbol is None or not elig0.get(symbol):
                left.append([symbol or "", "a buy of a slot that is no candidate today"])
            elif usd is None or usd <= 0:
                left.append([symbol, "a buy names dollars above 0"])
            else:
                out.append({"buy": symbol, "usd": format(usd.quantize(CENT, rounding=ROUND_DOWN), "f"), "at": at,
                            "tag": TAG})
        else:
            left.append(["", "an order is a sell or a buy"])
    return out, left


def target_pairs(target: Mapping[Any, Any] | None, cols: Columns) -> list[list[Any]]:
    """A target {id: w} (ids as the child answered them: JSON strings, read with `int()`) as [[symbol, weight]] in
    symbol order: `eq_rebalances.targets` (House only)."""
    by_id = {i: s for s, i in slots(cols).items()}
    out = []
    for key, w in (target or {}).items():
        symbol = by_id.get(int(key))
        if symbol is not None:
            out.append([symbol, round(float(w), WEIGHT_PLACES)])
    return sorted(out)


def marks(fetched: Fetched, cols: Columns, lots: Sequence[Any], day: dt.date) -> dict[int, Decimal]:
    """{lid: the day's raw close of the lot's symbol} for every open lot of the instance: a panel lot is marked on a
    day only panel programs decide too (the sleeve's free cash, the invested cap and the loss budget's open risk read
    the mark). A late decide never marks a lot bought since the close; a lot whose name was served no bar of the day
    keeps its last mark."""
    iso = _day(day).isoformat()
    where = _column_of(cols)
    days = np.asarray(fetched.days)
    out: dict[int, Decimal] = {}
    if not days.size or int(days[-1]) != ES.ordinal(_day(day)):
        return out
    last = np.asarray(fetched.raw)[-1]
    for lot in lots:
        k = where.get(str(_get(lot, "symbol") or "").upper())
        if k is None or not _open(lot) or str(_get(lot, "opened_day") or "") > iso:
            continue
        close = float(last[k, 3])
        if math.isfinite(close) and close > 0:
            out[int(_get(lot, "lid"))] = Decimal(repr(close))
    return out


def rebalance_row(*, instance: str, family: str, version: int, decided_day: str, exec_day: str, at: str,
                  called: bool, targets: Sequence[Sequence[Any]], standing: bool, intents: Sequence[Mapping[str, Any]],
                  skipped: Sequence[Sequence[Any]], equity: Any, budget: Any, cols: Columns | None, ctx_sha: str | None,
                  bars_sha: str | None, fetch: Mapping[str, Any], status: str, why: str | None,
                  now: float) -> dict[str, Any]:
    """One `eq_rebalances` row (`REBALANCE_COLUMNS`), ready to insert. `intents`: the E1 intents this decision
    planned; `cols` None for a decision whose columns could not be built."""
    if status not in REBALANCE_STATUS:
        raise ValueError(f"a rebalance's status is one of {REBALANCE_STATUS}, not {status!r}")
    targets = [[str(s), float(w)] for s, w in targets]
    money = lambda value: None if _dec(value) is None else format(_dec(value), "f")  # noqa: E731
    return {"instance": str(instance), "family": str(family), "version": int(version),
            "decided_day": str(decided_day), "exec_day": str(exec_day), "at": at if at in P.AT else "open",
            "called": int(bool(called)), "targets": json.dumps(targets, separators=(",", ":")),
            "standing": int(bool(standing)), "n_names": len(targets),
            "n_sells": sum(1 for i in intents if "sell" in i), "n_buys": sum(1 for i in intents if "buy" in i),
            "n_skipped": len(skipped), "skipped": json.dumps([[str(s), str(w)[:200]] for s, w in skipped],
                                                              separators=(",", ":")),
            "equity": money(equity), "budget": money(budget),
            "extra": json.dumps(list(cols.extra) if cols is not None else [], separators=(",", ":")),
            "ctx_sha": ctx_sha, "bars_sha": bars_sha,
            "fetch": json.dumps({k: fetch[k] for k in ("calls", "seconds", "symbols", "missing", "late", "dropped", "sha")
                                 if k in fetch}, separators=(",", ":"), default=str),
            "status": status, "why": None if why is None else str(why)[:400], "created_at": float(now)}


def event(row: Mapping[str, Any]) -> dict[str, Any]:
    """An `eq_rebalances` row as its `equity.rebalance` event: COUNTS AND VERDICTS ONLY (no symbol, no id, no weight,
    no dollar figure of a name)."""
    return {"instance": row["instance"], "day": row["decided_day"], "exec_day": row["exec_day"], "at": row["at"],
            "called": bool(row["called"]), "standing": bool(row["standing"]), "names": int(row["n_names"]),
            "sells": int(row["n_sells"]), "buys": int(row["n_buys"]), "skipped": int(row["n_skipped"]),
            "status": row["status"]}


# ----------------------------------------------------------------------------------------- the live record, by date
def spy_closes(market: Any, first: dt.date, last: dt.date) -> dict[str, Decimal]:
    """{day: SPY's adjustment=all close} from ONE fetch over the whole span (one basis, as E1's `_closes_again`); {}
    when it cannot be read."""
    symbol = config.REF[config.MARKET_COLUMN]
    try:
        fetched = market.bars([symbol], timeframe="1Day", start=_day(first).isoformat(),
                              end=(_day(last) + dt.timedelta(days=1)).isoformat(), adjustment="all")
    except Exception:  # noqa: BLE001 - unpriced: sizing up fails `beat_bh` and reads again at the next sync
        return {}
    out: dict[str, Decimal] = {}
    for row in (fetched or {}).get(symbol) or []:
        close = _dec(row.get("c"))
        stamp = str(row.get("t") or "")[:10]
        if close is not None and close > 0 and _is_day(stamp):
            out[stamp] = close
    return out


def spy_span(lots: Sequence[Any]) -> tuple[dt.date, dt.date] | None:
    """The one span `date_record`'s buy-and-hold needs of SPY: from the session before the first entry to the last
    exit, over the closed lots; None when there is none."""
    closed = [lot for lot in lots if _get(lot, "exit_day") and not _open(lot)]
    if not closed:
        return None
    try:
        first = S.previous_session(min(str(_get(lot, "opened_day")) for lot in closed))
    except ValueError:
        return None
    return first, _day(max(str(_get(lot, "exit_day")) for lot in closed))


def date_record(lots: Sequence[Any], twins: Mapping[Any, Any], spy: Mapping[str, Decimal] | None) -> dict[str, Any]:
    """THE LIVE RECORD BY CLOSE DATE (E4-SPEC 10.5): the version's closed ":r" lots grouped by exit day: `returns` (one
    a date, in date order: the date's summed lot cash over its summed entry notional), `n` (the close dates),
    `twin_gaps_bp` (one a date: the entry-notional-weighted mean gap of that date's lots with a priced twin; a date
    with none gives none), `pnl` and `realized_net` (dollars, Decimal), `bh_pnl` (the lots' dollars held in SPY over
    their own sessions: the sum over closed lots of entry notional x (SPY's close on the exit day / on the session
    before the entry day - 1), every close from `spy`, ONE fetch; None when `spy` is None, as before sizing up needs
    it, or when a close is missing), `dates` (the close dates). The fields of E1's `league.equity.bands
    .EquityRecord`, less `probe_sessions` and `validation_r_sd` (the book's own)."""
    closed = [lot for lot in lots if _get(lot, "exit_day") and not _open(lot)]
    closed.sort(key=lambda lot: (str(_get(lot, "exit_day")), float(_get(lot, "closed_at") or 0.0), int(_get(lot, "lid"))))
    by_date: dict[str, list[Any]] = {}
    for lot in closed:
        by_date.setdefault(str(_get(lot, "exit_day")), []).append(lot)
    returns: list[float] = []
    dates: list[str] = []
    gaps: list[float] = []
    for day in sorted(by_date):
        cash = sum((_dec(_get(lot, "cash")) or ZERO for lot in by_date[day]), ZERO)
        notional = sum((_dec(_get(lot, "entry_notional")) or ZERO for lot in by_date[day]), ZERO)
        if notional <= 0:
            continue
        returns.append(float(cash / notional))
        dates.append(day)
        weights, values = [], []
        for lot in by_date[day]:
            twin = twins.get(f"eq:{int(_get(lot, 'lid'))}") or {}
            gap = twin.get("gap_bp") if isinstance(twin, Mapping) else None
            weight = float(_dec(_get(lot, "entry_notional")) or ZERO)
            if isinstance(twin, Mapping) and twin.get("status") == "priced" and not isinstance(gap, bool) \
                    and isinstance(gap, (int, float)) and math.isfinite(float(gap)) and weight > 0:
                weights.append(weight)
                values.append(weight * float(gap))
        if weights:
            gaps.append(math.fsum(values) / math.fsum(weights))
    bh: Decimal | None = None
    if spy is not None:
        bh = ZERO
        for lot in closed:
            try:
                before = S.previous_session(str(_get(lot, "opened_day"))).isoformat()
            except ValueError:
                bh = None
                break
            start, end = spy.get(before), spy.get(str(_get(lot, "exit_day")))
            if not start or not end or start <= 0:
                bh = None
                break
            bh += (_dec(_get(lot, "entry_notional")) or ZERO) * (Decimal(end) / Decimal(start) - 1)
    return {"n": len(returns), "returns": tuple(returns), "dates": tuple(dates),
            "pnl": sum((_dec(_get(lot, "cash")) or ZERO for lot in closed), ZERO), "bh_pnl": bh,
            "realized_net": sum((_dec(_get(lot, "cash")) or ZERO for lot in closed if _get(lot, "probe")), ZERO),
            "twin_gaps_bp": tuple(gaps)}


def date_t(returns: Sequence[float]) -> float | None:
    """THE DATE-CLUSTERED t (the captain's A14, beside Done): mean / sd (ddof 1) x sqrt(n) over the per-date returns;
    None under two dates or without a spread."""
    values = [float(r) for r in returns]
    n = len(values)
    if n < 2:
        return None
    mean = math.fsum(values) / n
    sd = math.sqrt(math.fsum((r - mean) ** 2 for r in values) / (n - 1))
    if not sd > SD_FLOOR:
        return None
    return mean / sd * math.sqrt(n)


def cost_sentence(*, min_dates: Any, loss_usd: Any, sleeve_usd: Any = None) -> str:
    """THE COST OF READING BY DATE, stated beside every live panel program (E4-SPEC 10.5): what cannot demote it yet,
    and what bounds its loss meanwhile. `min_dates`: `demotion.min_trades`; `loss_usd`: `demotion.program_loss_usd`;
    `sleeve_usd`: the program's sleeve in dollars (None: no share is stated)."""
    loss = abs(_dec(loss_usd) or ZERO)
    sleeve = _dec(sleeve_usd)
    share = f" ({float(loss / sleeve):.0%} of its ${sleeve.quantize(CENT)} sleeve: a backstop, not a tight leash)" \
        if sleeve is not None and sleeve > 0 else " (a backstop, not a tight leash)"
    return (f"A panel program is read ONE OBSERVATION A CLOSE DATE: EDM1's statistical leg cannot demote it before its "
            f"{int(min_dates)}th close date ({int(min_dates)} weeks for a weekly program, {int(min_dates)} months for a "
            f"monthly one). Until then what bounds its loss counts lots in dollars: the program loss line -${loss:.0f} on "
            f"realized Probe net{share}, the shared loss budgets with open risk at 0.40, the daily and drawdown stops "
            "and the kill switch.")


__all__ = ["KIND", "MAX_INTENTS", "FETCH_CHUNK", "FETCH_TICK_S", "KEEP_SESSIONS", "LIVE_BARS_DIR", "MISSING_MAX",
           "HOLD_DAY_FAILS_EXIT", "TAG", "INELIGIBLE", "TWINS_FILE", "TWINS_VERSION", "REBALANCE_STATUS", "AUDIT_STATUS",
           "LABEL", "SCHEMA", "REBALANCE_COLUMNS", "INSTANCE_KIND_COLUMN", "INSTANCE_KIND_DDL", "ColumnsRefused",
           "Columns", "Fetched", "slots", "sessions_through", "columns", "union", "view", "called", "needs_of", "fetch",
           "complete", "bars_sha", "keep", "kept", "same", "eligible", "inputs", "committed", "sleeve_room", "last_called", "standing", "intents",
           "skipped", "target_pairs", "marks", "rebalance_row", "event", "spy_closes", "spy_span", "date_record",
           "date_t", "cost_sentence"]
