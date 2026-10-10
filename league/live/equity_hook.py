"""THE ONE DOOR from league/live to the equity lane (A8.8): every league/live module reaches league.equity through here.

Owner: hooks. `league/live` imports `league.equity` in exactly two places: this module, and the decider's kind table
(`league/live/decider.py` -> `league.equity.kinds`). A CI test (league/tests/test_equity_isolation.py) holds that, and
that `league/live/step.py` calls `self.equity.tick(` exactly once. Each function here is a thin forward that FAILS
CLOSED: an equity reading that cannot be made is a refusal of opens (never an exit's), and with no equity book (a House
without real money, or before E1's tables exist) the answers are the empty ones (nothing owned, nothing at risk).

Callers:
- league/live/step.py: `build_book` (OptionsLive.__init__: `self.equity`), `expected_shares` (`_close_shares`, the
  assignment latch), `frozen` (`real_block`), `busy` (one working order a symbol across both books);
- league/live/real.py: `is_equity_client_id` (`ingest`), `expected_shares` (`reconcile`), `probe_figures` (`probe_tally`,
  `probe_realized`, `probe_figures`), `working_buys_worst` (the options reservation's available cash, A8.1),
  `orders_today` (`count_refusal`, A8.3), `invested` and `open_risk` (`RealBook.exposure`);
- league/live/money.py: `band_for` (`band_for`'s first line, swarm's edit: an equity row never gets an options band).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Callable, Mapping

from .. import equity as E

CLIENT_PREFIX = E.CLIENT_PREFIX
LANES = E.LANES


def build_book(live: Any) -> Any | None:
    """The House's `EquityBook` for an `OptionsLive` (its state, real account, market data, money table, decider, paper
    account through `league.live.paper.StockPaperProof`, `sizing_equity`, options book, clock, record and alert), or
    None when the House has no real account."""
    raise NotImplementedError("hooks: league/live/equity_hook.py build_book")


def is_equity_client_id(client_id: str) -> bool:
    """Whether a venue order's client id is the equity book's (`lq-`)."""
    raise NotImplementedError("hooks: league/live/equity_hook.py is_equity_client_id")


def is_equity_row(row: Mapping[str, Any] | None) -> bool:
    """Whether a families row is an equity lane's (`row["lane"]` in `LANES`)."""
    raise NotImplementedError("hooks: league/live/equity_hook.py is_equity_row")


def expected_shares(book: Any | None) -> dict[str, Decimal]:
    """{symbol: shares} the equity book owns now ({} with no book); raises when the book cannot be read (the caller
    then treats every share as unexplained and opens nothing)."""
    raise NotImplementedError("hooks: league/live/equity_hook.py expected_shares")


def frozen(book: Any | None) -> str:
    """The equity book's freeze ("" none; "the equity book cannot be read" when it raises)."""
    raise NotImplementedError("hooks: league/live/equity_hook.py frozen")


def busy(book: Any | None) -> set[str]:
    """Symbols with a working equity order (set() with no book)."""
    raise NotImplementedError("hooks: league/live/equity_hook.py busy")


def probe_figures(rows: Callable[..., list], *, table: Any) -> Any:
    """The equity rows' Probe figures (`league.equity.live.ProbeFigures`) under the money table's equity weights;
    all zeros when the table carries no equity block or the state has no eq_lots table."""
    raise NotImplementedError("hooks: league/live/equity_hook.py probe_figures")


def working_buys_worst(rows: Callable[..., list]) -> Decimal:
    """Every working equity buy's worst cost (dollars): `league.equity.live.working_buys_worst`."""
    raise NotImplementedError("hooks: league/live/equity_hook.py working_buys_worst")


def orders_today(rows: Callable[..., list], day: str) -> int:
    """The equity orders of the New York `day`: `league.equity.live.orders_today`."""
    raise NotImplementedError("hooks: league/live/equity_hook.py orders_today")


def invested(rows: Callable[..., list]) -> Decimal:
    """Equity long value plus working buys (dollars): `league.equity.live.invested`."""
    raise NotImplementedError("hooks: league/live/equity_hook.py invested")


def open_risk(rows: Callable[..., list], *, table: Any) -> Decimal:
    """The equity rows' open risk in dollars (`probe_figures(...).open_risk`)."""
    raise NotImplementedError("hooks: league/live/equity_hook.py open_risk")


def band_for(row: Mapping[str, Any]) -> tuple[str, str]:
    """`league.equity.bands.band_for_row`: an equity row's band, unchanged, and why."""
    raise NotImplementedError("hooks: league/live/equity_hook.py band_for")


__all__ = ["CLIENT_PREFIX", "LANES", "build_book", "is_equity_client_id", "is_equity_row", "expected_shares", "frozen",
           "busy", "probe_figures", "working_buys_worst", "orders_today", "invested", "open_risk", "band_for"]
