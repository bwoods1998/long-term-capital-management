"""The equity lane's constants: one row each, read by the engine, the book, the twins and the screen alike.

Owner: core (league/equity/INTERFACES.md). Every figure here is a rule or a cost assumption, never a market result.
The constitution's `equity_money` block is the money rule the live path obeys; `league/tests/test_equity_money.py`
holds its universe and position shares equal to `UNIVERSE` and `POSITION_SHARE` here, and `league.ci` holds the
constitution's universe equal to the gateway's `STOCK_UNIVERSE` (gateway/lib/caps.mjs).

- THE UNIVERSE (`UNIVERSE`): symbol -> class ("etf" | "stock"), the gateway's `STOCK_UNIVERSE` exactly.
- HALF-SPREADS (`HALF_SPREAD_BP`, `half_spread`): 1 bp for the index ETFs (SPY QQQ IWM DIA), 3 bp for the sector ETFs
  and the stocks, 5 bp for TLT and GLD (the census's cost table). A fill is the official open or close x (1 +/- k x hs),
  k = `K_BASE` (1.0), and `K_STRESS` (1.5) for the robustness twin.
- FEES ON SELLS (`sell_fees`): SEC `SEC_FEE_PER_MILLION` dollars per $1,000,000 of proceeds and FINRA TAF
  `TAF_PER_SHARE` a share capped at `TAF_MAX`, each rounded UP to the cent; no commission. Checked against the first
  real confirmations (the design's fact 4).
- CAPS: `POSITION_SHARE` of the sizing equity per instrument class; `SLEEVE_USD` is the Gym's sleeve E0 (a round
  constant, part of every run's identity, never the account's equity).
- HOLDS: `MIN_HOLD_SESSIONS` (a lot never sells in the session it was bought), `DEFAULT_MAX_HOLD` and `MAX_HOLD_CAP`
  (NEEDS `max_hold_sessions`, A8.5), `FAILED_DECIDES_EXIT` (2 sessions of failed decides exit the program's lots).
- WINDOWS: Train 2016-01-04..2024-12-31 (SIP history starts in 2016), Validation 2025, holdout
  2026-01-02..2026-09-25, forward after; the holdout and forward are sealed (`store.EquityGateCapability`). The one
  sealed look reads 2026-01-02 through min(the last close before the look, 2026-12-31) (A9 D6: `LOOK_FIRST`,
  `LOOK_CAP`).
- TRAIN-ERA SEGMENTS for the screen's per-program floor (`TRAIN_ERA_SEGMENTS`): 2016-2019 and 2022-2024, never
  2020-2021, never 2025-2026 (A9 D5: the floor's world sets IND22 and IND1622).

Standard library only.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

ETF, STOCK = "etf", "stock"
CLASSES = (ETF, STOCK)

#: symbol -> class: the gateway's STOCK_UNIVERSE (gateway/lib/caps.mjs) exactly, in its order.
UNIVERSE: dict[str, str] = {
    "SPY": ETF, "QQQ": ETF, "IWM": ETF, "DIA": ETF,
    "XLB": ETF, "XLC": ETF, "XLE": ETF, "XLF": ETF, "XLI": ETF, "XLK": ETF, "XLP": ETF, "XLRE": ETF, "XLU": ETF,
    "XLV": ETF, "XLY": ETF,
    "TLT": ETF, "GLD": ETF,
    "AAPL": STOCK, "MSFT": STOCK, "NVDA": STOCK, "AMZN": STOCK, "GOOGL": STOCK, "META": STOCK, "BRK.B": STOCK,
    "JPM": STOCK, "V": STOCK, "UNH": STOCK, "XOM": STOCK, "JNJ": STOCK, "PG": STOCK, "MA": STOCK, "HD": STOCK,
    "AVGO": STOCK, "LLY": STOCK, "COST": STOCK,
}
INDEX_ETFS = ("SPY", "QQQ", "IWM", "DIA")
#: Half-spreads in basis points (the census's cost table): index ETFs, other ETFs and stocks, and TLT and GLD.
HALF_SPREAD_BP: dict[str, int] = {**{s: 3 for s in UNIVERSE}, **{s: 1 for s in INDEX_ETFS}, "TLT": 5, "GLD": 5}
K_BASE = 1.0
K_STRESS = 1.5

#: SEC Section 31 fee: dollars per $1,000,000 of sale proceeds; FINRA TAF: dollars a share sold, capped per trade.
SEC_FEE_PER_MILLION = Decimal("27.80")
TAF_PER_SHARE = Decimal("0.000166")
TAF_MAX = Decimal("8.30")

#: The largest share of the sizing equity one instrument may hold (the owner's lines: 50% an ETF, 20% a stock).
POSITION_SHARE: dict[str, Decimal] = {ETF: Decimal("0.50"), STOCK: Decimal("0.20")}
#: The Gym's sleeve E0 in dollars (part of every run's identity).
SLEEVE_USD = Decimal("1000")

MAX_SYMBOLS = 20
MAX_HISTORY = 504
MAX_INTENTS = 20
MIN_HOLD_SESSIONS = 1
DEFAULT_MAX_HOLD = 20
MAX_HOLD_CAP = 60
FAILED_DECIDES_EXIT = 2
#: Share quantities are floored to this many decimals (the venue takes nine; the House sends six).
QTY_PLACES = 6

WINDOWS: dict[str, tuple[dt.date, dt.date | None]] = {
    "train": (dt.date(2016, 1, 4), dt.date(2024, 12, 31)),
    "validation": (dt.date(2025, 1, 2), dt.date(2025, 12, 31)),
    "holdout": (dt.date(2026, 1, 2), dt.date(2026, 9, 25)),
    "forward": (dt.date(2026, 9, 26), None),
}
SEALED = ("holdout", "forward")
#: THE LOOK'S HOLDOUT (A9 D6): from LOOK_FIRST through min(the last close before the look, LOOK_CAP): the store's
#: holdout window and, after 2026-09-25, its forward days (both sealed: the look holds the gate's capability).
LOOK_FIRST = dt.date(2026, 1, 2)
LOOK_CAP = dt.date(2026, 12, 31)
#: The Train-era spans the screen's per-program floor builds its null worlds from (league/equity/screen.py).
TRAIN_ERA_SEGMENTS: tuple[tuple[dt.date, dt.date], ...] = (
    (dt.date(2016, 1, 4), dt.date(2019, 12, 31)),
    (dt.date(2022, 1, 3), dt.date(2024, 12, 31)),
)


def class_of(symbol: str) -> str | None:
    """"etf", "stock", or None when `symbol` is not in `UNIVERSE`."""
    raise NotImplementedError("core: league/equity/config.py class_of")


def half_spread(symbol: str) -> float:
    """The symbol's half-spread as a fraction (1 bp = 0.0001); KeyError for a symbol outside `UNIVERSE`."""
    raise NotImplementedError("core: league/equity/config.py half_spread")


def sell_fees(proceeds: Decimal, shares: Decimal) -> Decimal:
    """SEC + TAF on one sale of `shares` for `proceeds` dollars: each fee rounded UP to the cent, TAF capped at
    `TAF_MAX`. Decimal in, Decimal out (dollars). The engine, the book's fee estimate and the twins all call this."""
    raise NotImplementedError("core: league/equity/config.py sell_fees")


__all__ = ["ETF", "STOCK", "CLASSES", "UNIVERSE", "INDEX_ETFS", "HALF_SPREAD_BP", "K_BASE", "K_STRESS",
           "SEC_FEE_PER_MILLION", "TAF_PER_SHARE", "TAF_MAX", "POSITION_SHARE", "SLEEVE_USD", "MAX_SYMBOLS",
           "MAX_HISTORY", "MAX_INTENTS", "MIN_HOLD_SESSIONS", "DEFAULT_MAX_HOLD", "MAX_HOLD_CAP", "FAILED_DECIDES_EXIT",
           "QTY_PLACES", "WINDOWS", "SEALED", "LOOK_FIRST", "LOOK_CAP", "TRAIN_ERA_SEGMENTS", "class_of", "half_spread",
           "sell_fees"]
