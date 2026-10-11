"""How a live panel program trades through E1's EquityBook: the parent-side adapter (plumbing, outside the xs identity).

Owner: package H. STEP 0 STUB: `SCHEMA`, the constants and `Columns` / `Fetched` are the contract (package A's nightly
I6 and package J's twin read the table and the kept file); every function raises NotImplementedError until H lands.

The live process reaches the panel only through `league/equity/kinds.py`: the decider's `KINDS["panel"]` (the child,
league/xs/child.py) and H's `BOOKS["panel"]` = this module (the parent side). E1's book keeps every wall it has for a
share program (long only, cash only, a stock at most 20% of equity, the shared loss budget with stocks weighing 0.40,
the kill switch and the stops, never a forced or hand-placed trade); this module only turns a panel decision into
E1's intents and back. With no live panel instance nothing here runs, fetches or spends.

THE PARENT KNOWS THE NAMES, THE CHILD NEVER DOES. `columns` builds a day's columns: REF, then the day's members, then
EVERY symbol of a lot of the instance that is open or was closed that day and is no member (a name that left the index
keeps a column, a bar, a mark and the id its lot was bought under; `elig0` False, so it is never a candidate), the
member columns in ascending id (D8, run key = the instance id). The child receives arrays and ids; a target comes back
as ids (JSON string keys, read with `int()`), and `intents` names the symbols.

A SESSION OF A LIVE PANEL PROGRAM (E4-SPEC 10.3): from 16:20 ET the chunked `fetch` (28 gateway calls for about 515
columns, a few chunks a tick, each chunk turned into numpy before the next is asked for), read again while not
`complete`; then the bars are kept (`keep`: live-bars/<day>.npz, the bytes a decision read), the lots marked
(`marks`), and the decide runs in the live process's decider (no program code on a hold day; `ctx.derive` every day:
the ineligible lots and the standing target's buys). At 08:30 the day's columns are fetched again and compared with
the kept file (`same`, by E1's own `_bars_verdict`, handed in by the caller: this module imports nothing of the book).

A17 (the captain's amendment, granted for this build): for a panel program a HOLD-day fetch failure of a held name is
an alarm and never counts toward A8.5's two-failed-decides exit; a failed decide on a REBALANCE day still counts.
`HOLD_DAY_FAILS_EXIT` is that rule's one constant.

THE LIVE RULES READ A PANEL PROGRAM BY CLOSE DATE (`date_record`; E4-SPEC 10.5, pre-registered before mode "live"):
one observation a close date for EDM1, for sizing up and for the twin-gap leg; E1's `edm1` and `sized_up` are
unchanged as functions and as numbers.

Plumbing: NOT in the xs identity (`identity.XS_PLUMBING`); a fix here retires no panel lineage. It imports
`league.equity.schedule` and the evidence modules of this package; nothing of league.live, league.swarm or league.ops.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import numpy as np

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
#: At the last ask before the pre-open, at most this many names (none of them held) may still lack a bar.
MISSING_MAX = 2
#: A17: a hold day's failure counts toward no exit (False). True would be A8.5 read literally.
HOLD_DAY_FAILS_EXIT = False
#: The tag of every intent a panel decision plans.
TAG = "xs"
#: The House exit of a lot whose name is no longer eligible.
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
    ctx_sha TEXT, bars_sha TEXT, fetch TEXT NOT NULL DEFAULT '{}',   -- {calls, seconds, symbols, missing, late}
    audit TEXT,                         -- NULL | ok | mismatch | unread (the 08:30 re-read)
    status TEXT NOT NULL,               -- planned | hold | failed | late
    why TEXT, created_at REAL NOT NULL,
    UNIQUE (instance, decided_day));
CREATE INDEX IF NOT EXISTS eq_rebalances_day ON eq_rebalances(decided_day);
"""
#: `eq_instances` (E1's table) gains this column, by ALTER TABLE guarded by PRAGMA table_info (`INSTANCE_KIND_DDL` is
#: run only when the column is absent). An E1 row reads "equity".
INSTANCE_KIND_COLUMN = "kind"
INSTANCE_KIND_DDL = "ALTER TABLE eq_instances ADD COLUMN kind TEXT NOT NULL DEFAULT 'equity'"

_STUB = "league.xs.book is a Step 0 stub: package H builds it (league/xs/E4_INTERFACES.md)"


@dataclass(frozen=True)
class Columns:
    """One instance's columns of one decision day, in the order every array of that day is in.

    `symbols`: REF, then the member columns in ascending id, then nothing else: `extra` names which of the member-side
    symbols are no member today (a held or just-closed name that left the index). `aids` int32 (m,). `ids` int32 (m -
    12,): D8, from the whole asset table under the run key (the instance id). `elig0` bool (m,): the parent's part of
    eligibility (`store.PanelBars.elig0`'s row for the day; False for REF and for `extra`). `sector_perm`,
    `dither_key`: the run's. Parent side only: never pickled to a child."""

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
    float64 (n, m, 5), `all` float64 (n, m, 4), `meta` {calls, seconds, symbols, missing, late, fetched_at}."""

    days: np.ndarray
    raw: np.ndarray
    all: np.ndarray
    meta: Mapping[str, Any]


def columns(root: str | Path, instance: str, day: dt.date, *, held: Sequence[str]) -> Columns:
    """The instance's columns of `day` (`store.Universe`, the month's class choice, the House salt, run key = the
    instance id). `held`: the symbols of its lots that are open or were closed on `day`."""
    raise NotImplementedError(_STUB)


def called(day: dt.date, needs: Mapping[str, Any]) -> bool:
    """D9: whether the program is asked at the close of `day` (`config.decision_due` on its NEEDS)."""
    raise NotImplementedError(_STUB)


def fetch(market: Any, cols: Columns, day: dt.date, *, progress: dict | None = None,
          now: Callable[[], float] | None = None) -> Fetched | None:
    """The day's bars for `cols.symbols`, raw then all, 253 sessions ending `day`, through `market.bars` in chunks of
    `FETCH_CHUNK` symbols, each chunk turned into numpy (`ctx.rows_to_arrays`) and its dicts dropped before the next
    is asked for. It keeps its place in `progress` between calls and makes at most `FETCH_TICK_S` seconds of calls a
    call: None while unfinished."""
    raise NotImplementedError(_STUB)


def complete(fetched: Fetched, cols: Columns, lots: Sequence[Any], *, last_ask: bool = False) -> tuple[bool, list[str]]:
    """Whether the fetch may be decided on, and the symbols still missing: SPY has a bar of the day AND every `elig0`
    column that had a bar the session before has one (a row served counts, the vendor's flat volume-0 bar too). With
    `last_ask` (from 09:15 ET, the last ask before the pre-open): at most `MISSING_MAX` names may be missing, none of
    them held, and SPY never."""
    raise NotImplementedError(_STUB)


def bars_sha(fetched: Fetched, cols: Columns) -> str:
    """One decision's provenance: sha256 over the raw array's bytes and the as-of OHLC rounded to 4 decimals, columns
    in `cols` order."""
    raise NotImplementedError(_STUB)


def keep(root: str | Path, day: dt.date, fetched: Fetched, symbols: Sequence[str]) -> Path:
    """Write the fetch a decision of `day` read to `<root>/live-bars/<day>.npz` (symbols, days, raw, all, fetched_at;
    600; atomic) and drop the files older than `KEEP_SESSIONS` sessions. House only; outside every manifest."""
    raise NotImplementedError(_STUB)


def kept(root: str | Path, day: dt.date) -> tuple[tuple[str, ...], Fetched] | None:
    """The kept file of `day` as (symbols, Fetched), or None when there is none (the morning audit's and the nightly
    I6's reader)."""
    raise NotImplementedError(_STUB)


def same(old: Fetched, again: Fetched, cols: Columns, *, verdict: Callable[..., str]) -> dict[str, list[str]]:
    """The kept fetch against a later reading of the same columns: {"mismatch": [symbols], "volume": [symbols]}.
    `verdict` is E1's `league.equity.live._bars_verdict`, handed in by the caller: its rule, its tolerance (the
    vendor's cents) and nothing of the panel's; a volume-only difference is a note, never a mismatch."""
    raise NotImplementedError(_STUB)


def inputs(cols: Columns, fetched: Fetched, *, day: dt.date, needs: Mapping[str, Any], lots: Sequence[Any],
           closed: Sequence[Any], rejects: Sequence[str], cash: Any, equity: Any, budget: Any,
           params: Mapping[str, Any]) -> Any:
    """The decision's `league.xs.ctx.Inputs` (`ctx.inputs_from_arrays`): what the child is sent."""
    raise NotImplementedError(_STUB)


def standing(rows: Sequence[Mapping[str, Any]], cols: Columns, lots: Sequence[Any], day: dt.date) -> dict | None:
    """THE STANDING TARGET for a hold day: the instance's last CALLED `eq_rebalances` row whose status is "planned",
    as {target {id: w}, at, exited [id]} (`exited`: the ids the House has exited since that row); None when there is
    none or every id is held. A decide recorded late never becomes it."""
    raise NotImplementedError(_STUB)


def intents(answer: Mapping[str, Any], cols: Columns, lots: Sequence[Any]) -> list[dict[str, Any]]:
    """The child's orders as E1 intents: `{"sell": lid, "at", "tag": "xs"}`, `{"buy": SYM, "usd", "at", "tag": "xs"}`.
    A target's keys are read with `int()` (the child answers JSON)."""
    raise NotImplementedError(_STUB)


def marks(fetched: Fetched, cols: Columns, lots: Sequence[Any], day: dt.date) -> dict[int, Decimal]:
    """{lid: the day's raw close of the lot's symbol} for every open lot of the instance: a panel lot is marked on a
    day only panel programs decide too (the sleeve's free cash, the invested cap and the loss budget's open risk read
    the mark). A late decide never marks a lot bought since the close."""
    raise NotImplementedError(_STUB)


def rebalance_row(*, instance: str, family: str, version: int, decided_day: str, exec_day: str, at: str,
                  called: bool, targets: Sequence[Sequence[Any]], standing: bool, intents: Sequence[Mapping[str, Any]],
                  skipped: Sequence[Sequence[Any]], equity: Any, budget: Any, cols: Columns, ctx_sha: str | None,
                  bars_sha: str | None, fetch: Mapping[str, Any], status: str, why: str | None,
                  now: float) -> dict[str, Any]:
    """One `eq_rebalances` row (the columns of `SCHEMA`), ready to insert."""
    raise NotImplementedError(_STUB)


def spy_closes(market: Any, first: dt.date, last: dt.date) -> dict[str, Decimal]:
    """{day: SPY's adjustment=all close} from ONE fetch over the whole span (one basis, as E1's `_closes_again`)."""
    raise NotImplementedError(_STUB)


def date_record(lots: Sequence[Any], twins: Mapping[Any, Any], spy: Mapping[str, Decimal] | None) -> dict[str, Any]:
    """THE LIVE RECORD BY CLOSE DATE (E4-SPEC 10.5): the version's closed ":r" lots grouped by exit day: `returns` (one
    a date, in date order: the date's summed lot cash over its summed entry notional), `n` (the close dates),
    `twin_gaps_bp` (one a date: the entry-notional-weighted mean gap of that date's lots with a priced twin), `pnl`
    and `realized_net` (dollars), `bh_pnl` (the lots' dollars held in SPY over their own sessions, from `spy`; None
    before sizing up needs it or when a close is missing). The fields of E1's `league.equity.bands.EquityRecord`."""
    raise NotImplementedError(_STUB)


__all__ = ["KIND", "MAX_INTENTS", "FETCH_CHUNK", "FETCH_TICK_S", "KEEP_SESSIONS", "LIVE_BARS_DIR", "MISSING_MAX",
           "HOLD_DAY_FAILS_EXIT", "TAG", "INELIGIBLE", "TWINS_FILE", "TWINS_VERSION", "REBALANCE_STATUS", "AUDIT_STATUS", "SCHEMA",
           "INSTANCE_KIND_COLUMN", "INSTANCE_KIND_DDL", "Columns", "Fetched", "columns", "called", "fetch", "complete",
           "bars_sha", "keep", "kept", "same", "inputs", "standing", "intents", "marks", "rebalance_row", "spy_closes",
           "date_record"]
