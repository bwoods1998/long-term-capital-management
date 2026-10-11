"""THE ONE DOOR from league/live to the equity lane (A8.8): every league/live module reaches league.equity through here.

Owner: hooks. `league/live` imports `league.equity` in exactly two places: this module, and the decider's kind table
(`league/live/decider.py` -> `league.equity.kinds`). A CI test (league/tests/test_equity_isolation.py) holds that, and
that `league/live/step.py` calls `self.equity.tick(` exactly once. Each function here is a thin forward that FAILS
CLOSED: an equity reading that cannot be made is a refusal of opens (never an exit's), and with no equity book (a House
without real money, or before E1's tables exist) the answers are the empty ones (nothing owned, nothing at risk).

The row readers (`probe_figures`, `working_buys_worst`, `orders_today`, `invested`, `open_risk`) take the live state's
own rows (`rows(sql, params)` returns dicts, as `league.live.real.probe_tally`'s) and answer the empty figure for a state
without the equity book's tables (a state from before E1: they never reach league.equity then). Every league.equity
import is made inside a function: league/equity/live.py imports `league.live.real`, which imports this module.

Callers:
- league/live/step.py: `build_book` (OptionsLive.__init__: `self.equity`), `expected_shares` (`_close_shares`, the
  assignment latch, both reconciliations), `frozen` (`real_block`), `busy` (one working order a symbol across both
  books), `shares_taken` (`_lots_taken`: lots an assignment swallowed, closed once the House's cover has filled),
  `health` (`OptionsLive.health`);
- league/live/real.py: `is_equity_client_id` (`ingest`), `probe_figures` (`probe_tally`, `probe_realized`,
  `probe_figures`), `working_buys_worst` (the options reservation's available cash, A8.1), `orders_today`
  (`count_refusal`, `path_refusal`: the one day order count, A8.3), `invested` and `open_risk` (`RealBook.exposure`);
- league/live/money.py: `band_for` (`band_for`'s first line, swarm's edit: an equity row never gets an options band).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Callable, Mapping

from .. import equity as E

CLIENT_PREFIX = E.CLIENT_PREFIX
LANES = E.LANES
#: The share tolerance of every equity comparison (league/equity/live.py `SHARE_TOLERANCE`; a test holds them equal):
#: the venue keeps nine places of a fractional share.
SHARE_TOLERANCE = Decimal("1e-9")
ZERO = Decimal(0)
#: The `open_risk_weight` of a class when the money table carries no equity block (a hand-built table): the whole mark
#: value (fail closed: an equity lot is never free of the shared loss budget).
FULL_WEIGHT = Decimal(1)
#: Why the equity book cannot be read (`frozen`, `real_block`): no new real open in either lane until it can.
UNREADABLE = "the equity book cannot be read"


class Unreadable:
    """The House's equity book when it could not be built while the live state shows it holds or works shares (a bad
    release, a table that cannot be parsed): every reading fails closed. `frozen` names why (real_block refuses every
    real open, both lanes), `expected_shares` raises (reconciliation then sees every share as a mismatch, and
    `_close_shares` sells no long share, since what is owned cannot be told), `busy` and `shares_taken` raise, `tick`
    does nothing. A restart with a working book is the way out; nothing here ever sends an order."""

    def __init__(self, why: str):
        self.why = str(why)[:300]

    @property
    def frozen(self) -> str:
        return self.why

    def expected_shares(self) -> dict[str, Decimal]:
        raise RuntimeError(self.why)

    def busy(self) -> set[str]:
        raise RuntimeError(self.why)

    def shares_taken(self, symbol: str, qty: Decimal, px: Decimal | None, *, why: str) -> Decimal:
        raise RuntimeError(self.why)

    def tick(self, now: float, **_: Any) -> dict[str, Any]:
        return {"error": self.why}

    def health(self) -> dict[str, Any]:
        return {"frozen": self.why, "error": self.why}

    def flatten(self, why: str) -> int:
        return 0


def _has(rows: Callable[..., list], table: str) -> bool:
    """Whether the live state holds `table` (the equity book creates its tables when it is built)."""
    return bool(rows("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)))


def _holds(rows: Callable[..., list]) -> bool:
    """Whether the equity book's rows show a lot not closed or an order that may still fill (raw SQL: the book's code is
    not needed to see it)."""
    if _has(rows, "eq_lots") and rows("SELECT lid FROM eq_lots WHERE status != 'closed' LIMIT 1"):
        return True
    return _has(rows, "eq_orders") and bool(rows("SELECT eid FROM eq_orders WHERE status IN ('pending', 'working', "
                                                 "'unknown') LIMIT 1"))


def build_book(live: Any) -> Any | None:
    """The House's `EquityBook` for an `OptionsLive` (its state, real account, market data, money table, decider, paper
    account through `league.live.paper.StockPaperProof`, `sizing_equity`, options book, clock, record and alert), or
    None when the House has no real account.

    Also None (the lane does not run; nothing equity exists to protect) when the money table carries no equity block
    and the live state holds no equity lot or working order. When the book cannot be built, or the table carries no
    equity block, while the state DOES hold one: `Unreadable` (fail closed), with an error alert."""
    if getattr(live, "real", None) is None:
        return None
    table = getattr(live, "table", None)
    try:
        holds = _holds(live.state.rows)
    except Exception as exc:  # noqa: BLE001 - the state itself cannot be read: nothing is assumed clear
        live.alert("error", f"live: the equity book's rows could not be read ({type(exc).__name__}); real opens are "
                            "refused until a restart reads them")
        return Unreadable(f"{UNREADABLE}: its rows could not be read ({type(exc).__name__})")
    if getattr(table, "equity", None) is None:
        if not holds:
            return None
        live.alert("error", "live: the money table carries no equity block while the equity book holds shares; real "
                            "opens are refused")
        return Unreadable(f"{UNREADABLE}: the money table carries no equity block while it holds shares")
    try:
        from ..equity.families import EquityFamilies, MemoryEquityFamilies
        from ..equity.live import EquityBook
        from .families import SwarmFamilies
        from .paper import StockPaperProof

        families = EquityFamilies(live.root) if isinstance(live.families, SwarmFamilies) else MemoryEquityFamilies()
        earlier = tuple(p for p in (getattr(live, "proof", None), getattr(live, "proof_single", None)) if p is not None)
        proof = (StockPaperProof(live.state, live.paper, record=live.record, clock=live.clock, alert=live.alert,
                                 after=lambda: all(p.passed() for p in earlier))
                 if getattr(live, "paper", None) is not None else None)
        return EquityBook(live.state, live.real, live.market, table, families, decider=live.decider, stock_proof=proof,
                          sizing_equity=live.sizing_equity, options_book=live.book, root=live.root, clock=live.clock,
                          record=live.record, alert=live.alert)
    except Exception as exc:  # noqa: BLE001 - never the options path's end
        why = f"{type(exc).__name__}: {str(exc)[:200]}"
        if not holds:
            live.alert("error", f"live: the equity book could not be built ({why}); the equity lane does not run")
            return None
        live.alert("error", f"live: the equity book could not be built ({why}) while it holds shares; real opens are "
                            "refused")
        return Unreadable(f"{UNREADABLE}: it could not be built ({why})")


def is_equity_client_id(client_id: str) -> bool:
    """Whether a venue order's client id is the equity book's (`lq-`)."""
    return str(client_id or "").startswith(CLIENT_PREFIX)


def is_equity_row(row: Mapping[str, Any] | None) -> bool:
    """Whether a families row is an equity lane's (`row["lane"]` in `LANES`)."""
    return isinstance(row, Mapping) and row.get("lane") in LANES


def expected_shares(book: Any | None) -> dict[str, Decimal]:
    """{symbol: shares} the equity book owns now ({} with no book); raises when the book cannot be read (the caller
    then treats every share as unexplained and opens nothing)."""
    if book is None:
        return {}
    owned = book.expected_shares()
    return {str(symbol).upper(): Decimal(str(qty)) for symbol, qty in dict(owned).items()}


def frozen(book: Any | None) -> str:
    """The equity book's freeze ("" none; "the equity book cannot be read" when it raises)."""
    if book is None:
        return ""
    try:
        return str(book.frozen or "")
    except Exception as exc:  # noqa: BLE001
        return f"{UNREADABLE} ({type(exc).__name__})"


def busy(book: Any | None) -> set[str]:
    """Symbols with a working equity order (set() with no book); raises when the book cannot be read."""
    if book is None:
        return set()
    return {str(symbol).upper() for symbol in book.busy()}


def shares_taken(book: Any | None, symbol: str, qty: Decimal, px: Decimal | None, *, why: str) -> Decimal:
    """`EquityBook.shares_taken`: `qty` shares of `symbol` the book's lots held left the account in an option
    assignment or exercise and the House's cover of the short has filled at `px` (None: unreadable); the lots are
    closed for them as "forced". Returns the shares closed (0 with no book); raises when the book cannot be read (the
    caller asks again at its next reading)."""
    if book is None:
        return ZERO
    try:
        price = None if px in (None, "") else Decimal(str(px))
    except ArithmeticError:             # a price that is no number is no price: the book prices at its own mark
        price = None
    return Decimal(book.shares_taken(str(symbol).upper(), Decimal(str(qty)), price, why=str(why)))


def health(book: Any | None) -> dict[str, Any] | None:
    """The equity book's health line (None with no book; {"error": ...} when it cannot be read)."""
    if book is None:
        return None
    try:
        return dict(book.health())
    except Exception as exc:  # noqa: BLE001 - the health page never fails for it
        return {"error": f"{type(exc).__name__}: {str(exc)[:200]}"}


def _weights(table: Any) -> dict[str, Decimal]:
    """The money table's `equity_money.open_risk_weight` ({"etf": 0.20, "stock": 0.40}); `table` None is the table in
    force; with no equity block every class weighs `FULL_WEIGHT`."""
    if table is None:
        from . import money as M

        table = M.Table.from_constitution()
    equity = getattr(table, "equity", None)
    if equity is None:
        return {"etf": FULL_WEIGHT, "stock": FULL_WEIGHT}
    return {str(k): Decimal(str(v)) for k, v in dict(equity.open_risk_weight).items()}


def probe_figures(rows: Callable[..., list], *, table: Any) -> Any:
    """The equity rows' Probe figures (`league.equity.live.ProbeFigures`) under the money table's equity weights
    (`table` None: the table in force); all zeros when the state has no eq_lots table. With a table that carries no
    equity block every lot weighs its whole mark value (fail closed)."""
    from ..equity import live as B

    if not _has(rows, "eq_lots"):
        return B.ProbeFigures(programs=0, closes=(), open_risk=ZERO)
    return B.probe_figures(rows, weights=_weights(table))


def working_buys_worst(rows: Callable[..., list]) -> Decimal:
    """Every working equity buy's worst cost (dollars): `league.equity.live.working_buys_worst`."""
    if not _has(rows, "eq_orders"):
        return ZERO
    from ..equity import live as B

    return Decimal(B.working_buys_worst(rows))


def orders_today(rows: Callable[..., list], day: str) -> int:
    """The equity orders of the New York `day`: `league.equity.live.orders_today`."""
    if not _has(rows, "eq_orders"):
        return 0
    from ..equity import live as B

    return int(B.orders_today(rows, day))


def invested(rows: Callable[..., list]) -> Decimal:
    """Equity long value plus working buys (dollars): `league.equity.live.invested`."""
    if not _has(rows, "eq_lots"):
        return ZERO
    from ..equity import live as B

    return Decimal(B.invested(rows))


def open_risk(rows: Callable[..., list], *, table: Any) -> Decimal:
    """The equity rows' open risk in dollars (`probe_figures(...).open_risk`)."""
    return Decimal(probe_figures(rows, table=table).open_risk)


def band_for(row: Mapping[str, Any]) -> tuple[str, str]:
    """`league.equity.bands.band_for_row`: an equity row's band, unchanged, and why."""
    from ..equity.bands import band_for_row

    return band_for_row(row)


__all__ = ["CLIENT_PREFIX", "LANES", "SHARE_TOLERANCE", "UNREADABLE", "Unreadable", "build_book", "is_equity_client_id",
           "is_equity_row", "expected_shares", "frozen", "busy", "shares_taken", "health", "probe_figures",
           "working_buys_worst", "orders_today", "invested", "open_risk", "band_for"]
