"""THE EQUITY BOOK: every lot real money holds for an equity program, its order path, reconciliation and exports.

Owner: book. The House's live equity path, outside the options fingerprint. `league/live/step.py` calls `tick` exactly
once a minute (league/live/equity_hook.py builds the book; a CI string test holds that call site to one); everything
else the book does follows its own clock (league/equity/schedule.py).

TABLES in `<state>/live.sqlite` (`SCHEMA`; money and share quantities are Decimal strings, never floats): `eq_lots`,
`eq_orders`, `eq_fills`, `eq_intents` (decisions recorded at 16:30 ET, executed next session), `eq_bars` (the bars each
decision used, A8.11), `eq_activities` (dividends, splits and corporate actions booked, A8.10), `eq_exports` (lots
exported to the forward record), `eq_instances` (the program each equity instance runs; never the options
`instances` table, which the options path restores and loads).

THE ORDER PATH (the options path's discipline): a row is written `pending` BEFORE the POST, client id
`lq-<eid>-<family>` (`client_id`); a lost answer is `unknown` and is looked up by its client id, never re-sent blind;
one working order per symbol across BOTH books (wash-trade protection: the options book's `busy()` symbols and the
equity book's). CANCEL THEN RESEND (A8.4): a replacement goes only once the old order is terminal (filled, canceled,
expired, rejected), sized target minus filled; the old order's remaining quantity stays in exposure until then.
ONE DAY ORDER COUNT (A8.3): at most `order_path.max_orders_day` (60) equity orders a day, and none while the House-wide
count would leave less than the options book's `exit_reserve()`.

THE WINDOWS (`schedule`): OPEN: exits first at open+30 s (09:30:30 ET), entries after the exits filled or 2 minutes,
sized on cash after the exit fills (no entry is funded by an exit that has not filled); collar `entry_collar_bp` (10
ETF / 25 stock) widening each minute to `max_collar_bp` (50 / 100); entries stop at open+15 min (09:45); exits continue
to close-5 min (15:55), then go at the bid. CLOSE (A2): at close-5 min (15:55:00) exits first then entries, marketable
limits re-priced every 30 s to close-30 s (15:59:30), then recorded missed. A missed entry is recorded, never chased.
MIN HOLD: a lot never sells in the session it was bought (kill switch and stops included; the gateway's kill blocks
sells too). NO STUCK LOTS (A8.5): a lot held its program's `max_hold_sessions` exits at the next open; a demoted,
retired or band-dropped program's lots exit at the next open; 2 sessions of failed decides exit the program's lots at
the next open; on a restart a catch-up decide runs for the last close if it was missed.

SIZING: `league.equity.sizing.size_entry` (money's; never re-implemented here), with the House-wide available cash of
`league.live.money.available_cash` (A8.1). Every real open asks `real_block(opening=True)` first (grant, kill switch,
stops, both books' reconciliation, the assignment latch, the House pause, the account read), then its own gates:
`equity_money.enabled`, the stock paper proof passed (`paper_proof_stock`, A8.7), its own freeze, the program's band
and seat, the shared loss budget's room.

ATTRIBUTION: lots are per instance; the venue nets per symbol. A sale is FIFO within the instance's own lots, never
another program's. DIVIDENDS and SPLITS and the other corporate actions (A8.10): league/equity/actions.py.
RECONCILIATION: every minute in session and once pre-open, the account's us_equity quantity per symbol against
`expected_shares()` plus the share-event ledger (assignment and exercise shares, A8.2), as Decimal with a 1e-9 share
tolerance. Two mismatched readings freeze equity entries (exits go on); two clean readings lift it. The freeze also
blocks options opens (league/live/step.py `real_block`).
EXPORTS: a closed lot goes to the forward record (league/equity/families.py `add_forward`) with net cash, fees,
dividends, notional, hold and its twin key `eq:<lid>`.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .. import equity as _pkg

#: The book's tables (created by `EquityBook.__init__`, one statement at a time through `LiveState.execute`).
SCHEMA = """
CREATE TABLE IF NOT EXISTS eq_lots (
    lid INTEGER PRIMARY KEY, instance TEXT NOT NULL, family TEXT NOT NULL, version INTEGER NOT NULL, lane TEXT NOT NULL,
    symbol TEXT NOT NULL, class TEXT NOT NULL, qty TEXT NOT NULL, opened_qty TEXT NOT NULL, entry_px TEXT NOT NULL,
    entry_notional TEXT NOT NULL, entry_at TEXT NOT NULL, fees TEXT NOT NULL DEFAULT '0', div TEXT NOT NULL DEFAULT '0',
    mark TEXT, marked_at REAL, opened_at REAL NOT NULL, opened_day TEXT NOT NULL, status TEXT NOT NULL,
    exit_px TEXT, exit_at TEXT, exit_day TEXT, closed_at REAL, cash TEXT NOT NULL DEFAULT '0', reason TEXT,
    probe INTEGER NOT NULL DEFAULT 0, tag TEXT, iid INTEGER, info TEXT NOT NULL DEFAULT '{}');
CREATE INDEX IF NOT EXISTS eq_lots_status ON eq_lots(status);
CREATE TABLE IF NOT EXISTS eq_orders (
    eid INTEGER PRIMARY KEY, client_id TEXT UNIQUE NOT NULL, venue_id TEXT, instance TEXT NOT NULL, family TEXT NOT NULL,
    lid INTEGER, iid INTEGER, side TEXT NOT NULL, symbol TEXT NOT NULL, class TEXT NOT NULL, at TEXT NOT NULL,
    qty TEXT NOT NULL, limit_px TEXT NOT NULL, collar_bp INTEGER NOT NULL, status TEXT NOT NULL, placed_at REAL NOT NULL,
    day TEXT NOT NULL, filled_qty TEXT NOT NULL DEFAULT '0', avg_px TEXT, fees_est TEXT NOT NULL DEFAULT '0',
    replaces INTEGER, probe INTEGER NOT NULL DEFAULT 0, why TEXT, answer TEXT, updated_at REAL NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0);
CREATE INDEX IF NOT EXISTS eq_orders_status ON eq_orders(status);
CREATE TABLE IF NOT EXISTS eq_fills (
    fid INTEGER PRIMARY KEY AUTOINCREMENT, eid INTEGER NOT NULL, lid INTEGER, venue_fill_id TEXT, qty TEXT NOT NULL,
    px TEXT NOT NULL, fees TEXT NOT NULL DEFAULT '0', at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS eq_intents (
    iid INTEGER PRIMARY KEY, instance TEXT NOT NULL, family TEXT NOT NULL, version INTEGER NOT NULL,
    decided_day TEXT NOT NULL, exec_day TEXT NOT NULL, at TEXT NOT NULL, kind TEXT NOT NULL, symbol TEXT, lid INTEGER,
    share TEXT, usd TEXT, tag TEXT, status TEXT NOT NULL, why TEXT, ctx_sha TEXT, bars_sha TEXT,
    created_at REAL NOT NULL, updated_at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS eq_intents_exec ON eq_intents(exec_day, status);
CREATE TABLE IF NOT EXISTS eq_bars (
    day TEXT NOT NULL, symbol TEXT NOT NULL, adjustment TEXT NOT NULL, o TEXT, h TEXT, l TEXT, c TEXT, v TEXT,
    fetched_at REAL NOT NULL, sha TEXT NOT NULL, audit TEXT, PRIMARY KEY (day, symbol, adjustment));
CREATE TABLE IF NOT EXISTS eq_activities (
    id TEXT PRIMARY KEY, type TEXT NOT NULL, symbol TEXT, day TEXT, qty TEXT, net TEXT, booked TEXT NOT NULL,
    at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS eq_exports (lid INTEGER PRIMARY KEY, exported_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS eq_instances (
    id TEXT PRIMARY KEY, family TEXT NOT NULL, version INTEGER NOT NULL, lane TEXT NOT NULL, run_sha TEXT NOT NULL,
    code TEXT NOT NULL, params TEXT NOT NULL, band TEXT NOT NULL, seeded INTEGER NOT NULL DEFAULT 0,
    max_hold INTEGER NOT NULL, failed_decides INTEGER NOT NULL DEFAULT 0, last_decided_day TEXT, created_at REAL NOT NULL,
    retired_at REAL, why TEXT);
"""

#: Order statuses that still hold quantity or may yet fill.
WORKING = ("pending", "working", "unknown")
#: Terminal order statuses (a replacement may go only after one of these: A8.4).
TERMINAL = ("filled", "canceled", "expired", "rejected", "lost", "missed", "refused")
#: Lot statuses.
LOT_OPEN, LOT_CLOSING, LOT_CLOSED = "open", "closing", "closed"
#: The real (evidence) route's instance suffix, as the options book's (`league.live.real.REAL_SUFFIX`).
REAL_SUFFIX = ":r"
#: The share tolerance of every equity reconciliation (fractional shares, nine places at the venue).
SHARE_TOLERANCE = Decimal("1e-9")
CLIENT_PREFIX = _pkg.CLIENT_PREFIX


def client_id(eid: int, family: str) -> str:
    """`lq-<eid>-<family slug>`, at most 48 characters (the venue's limit), unique by `eid`."""
    raise NotImplementedError("book: league/equity/live.py client_id")


@dataclass(frozen=True)
class ProbeFigures:
    """The equity rows' part of THE PROBE LOSS BUDGET (league/live/real.py `probe_tally`, `probe_realized`,
    `probe_figures` union them; A8.6): `programs` open (ONE slot a program with any open ":r" lot or working ":r" buy,
    never one a lot); `closes`: ((NY close day ISO or None, net cash Decimal), ...) of every closed ":r" lot with
    `probe` 1; `open_risk`: sum of open_risk_weight[class] x mark value of every open ":r" lot (entry price when never
    marked) plus weight x remaining qty x limit of every working ":r" buy."""

    programs: int
    closes: tuple[tuple[str | None, Decimal], ...]
    open_risk: Decimal


def probe_figures(rows: Callable[..., list], *, weights: Mapping[str, Decimal]) -> ProbeFigures:
    """The equity rows' Probe figures from the live state's own rows (`rows(sql, params)` returns dicts, as
    `league.live.real.probe_tally`'s), so a restart reads the same numbers. `weights`: {"etf": Decimal("0.20"), "stock":
    Decimal("0.40")}. No eq_lots table (a state from before E1) is all zeros."""
    raise NotImplementedError("book: league/equity/live.py probe_figures")


def expected_shares_rows(rows: Callable[..., list]) -> dict[str, Decimal]:
    """{symbol: shares} the equity book owns, from the rows alone: its open lots' qty plus the filled part of its working
    buys, less the filled part of its working sells not yet booked. What `_close_shares` and both reconciliations read
    (A8.2: "read in the same pass")."""
    raise NotImplementedError("book: league/equity/live.py expected_shares_rows")


def working_buys_worst(rows: Callable[..., list]) -> Decimal:
    """Every working equity buy's worst cost: remaining qty x limit (dollars), for the House-wide available cash (A8.1)."""
    raise NotImplementedError("book: league/equity/live.py working_buys_worst")


def orders_today(rows: Callable[..., list], day: str) -> int:
    """Equity orders sent (or pending) on the New York `day` (ISO), cancels counted as the options book counts its own:
    the shared day order count (A8.3)."""
    raise NotImplementedError("book: league/equity/live.py orders_today")


def invested(rows: Callable[..., list]) -> Decimal:
    """Equity long value (open lots at their mark, entry price when never marked) plus working buys' worst cost
    (dollars): `league.live.money.Exposure.equity_invested`."""
    raise NotImplementedError("book: league/equity/live.py invested")


class EquityBook:
    """The equity book and its order path (the module docstring).

    `state`: the House's `LiveState` (live.sqlite). `account`: the real `Account` (None: a House without real money;
    the book then only keeps its tables). `market`: `MarketData` (snapshots for limits; 1Day bars at 16:20).
    `table`: the money `Table` in force (`table.equity`: the parsed `equity_money`; the shared loss budget's rows).
    `families`: league/equity/families.py `EquityFamilies` (or `MemoryEquityFamilies`). `decider`: the live decider
    (its "equity" kind runs decide). `stock_proof`: `league.live.paper.StockPaperProof` (None: no paper account; then
    no real equity open, ever). `sizing_equity`: the House's `OptionsLive.sizing_equity`. `options_book`: the options
    `RealBook` (its `busy()` symbols, `exit_reserve()`, `count_today()`; None in tests). `clock`, `record`, `alert` as
    the options book's."""

    def __init__(self, state: Any, account: Any, market: Any, table: Any, families: Any, *, decider: Any,
                 stock_proof: Any = None, sizing_equity: Callable[[], Decimal | None] | None = None,
                 options_book: Any = None, root: str | Path | None = None, clock: Callable[[], float] | None = None,
                 record: Callable[..., Any] | None = None, alert: Callable[[str, str], Any] | None = None):
        raise NotImplementedError("book: league/equity/live.py EquityBook")

    # ------------------------------------------------------------------ the minute
    def tick(self, now: float, *, account_row: Mapping[str, Any] | None, positions: Sequence[Mapping[str, Any]] | None,
             open_orders: Sequence[Mapping[str, Any]] | None, real_block: Callable[..., str | None],
             killed: Callable[[], bool]) -> dict[str, Any]:
        """THE ONE ENTRY a minute (league/live/step.py): whatever `schedule.phase(now)` says is due (bars, decide,
        pre-open, the open window, the close window, the morning audit, reconciliation, activities, exports). The
        minute's own reads are passed when the options path made them (None: not read this minute; the book reads
        what it needs itself, within the Account's rate). `real_block(opening=True)`: why no real open may go now
        (None: it may); `killed()`: the gateway's kill switch (exits wait only on it: the gateway's kill blocks sells
        too). Never raises: an error is recorded and the next minute tries again. Returns a summary for the minute's
        `out["equity"]`."""
        raise NotImplementedError("book: league/equity/live.py EquityBook.tick")

    # ------------------------------------------------------------------ what the hooks read
    @property
    def frozen(self) -> str:
        """Why equity entries are frozen by reconciliation or an unexplained corporate action ("" none)."""
        raise NotImplementedError("book: league/equity/live.py EquityBook.frozen")

    def expected_shares(self) -> dict[str, Decimal]:
        """{symbol: shares} this book owns now (`expected_shares_rows` over its state)."""
        raise NotImplementedError("book: league/equity/live.py EquityBook.expected_shares")

    def busy(self) -> set[str]:
        """Symbols with a working equity order (one working order a symbol across both books)."""
        raise NotImplementedError("book: league/equity/live.py EquityBook.busy")

    def health(self) -> dict[str, Any]:
        """The book's line for health.json and the site: {enabled, frozen, lots, working, orders_today, phase,
        proof, programs: [...], last_decide, last_bars}."""
        raise NotImplementedError("book: league/equity/live.py EquityBook.health")

    def flatten(self, why: str) -> int:
        """The rollback's first step (docs/operations.md): every open lot queued to exit at the next window through the
        normal path; returns the lots queued. Never a market order."""
        raise NotImplementedError("book: league/equity/live.py EquityBook.flatten")


__all__ = ["SCHEMA", "WORKING", "TERMINAL", "LOT_OPEN", "LOT_CLOSING", "LOT_CLOSED", "REAL_SUFFIX", "SHARE_TOLERANCE",
           "CLIENT_PREFIX", "client_id", "ProbeFigures", "probe_figures", "expected_shares_rows", "working_buys_worst",
           "orders_today", "invested", "EquityBook"]
