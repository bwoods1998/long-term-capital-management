"""The venue's rules, fees and ticks: one table for the Gym's replay and the House's live path.

From the plan's "The venue" and "Fees" (verified Sept 26, 2026), as the House enforces them:

- Options trade 09:30-16:00 ET only (13:00 on a half day).
- On an EXPIRING contract (a leg that expires today): no new opening order from 15:00 ET; closing
  orders until 15:10 ET (15:25 for SPY and QQQ). An expiring EQUITY structure with a leg that expires
  today in the money or within 1% of it (`near_money`), or an expiring long call or put with a bid,
  is closed at the natural price by the House from 10 minutes before the close cutoff until the
  cutoff; one in or near the money is liquidated at the natural by the venue from 15:30 ET; the rest
  is left to expire (worth its intrinsic value at the close, normally zero, with no closing fee), as
  the live path does
  (`league/live/step.py` `_expiry_close` and `_end_of_day`, the constitution's `order_path`
  `near_money_share` 0.01 and `expiry_close_lead_minutes` 10). On a half day the same offsets are
  taken from the 13:00 close.
- Equity options (SPY, QQQ, IWM, single names) are American and physically settled: auto-exercise at
  $0.01 in the money, so an assigned short leg becomes shares (the engine marks them to the next
  open). Index options (XSP, SPXW) are European and cash-settled from the settlement price (SPXW's
  PM settlement is the close's SPX), carry no assignment, and may be held into the close.
- Calendars and diagonals are equity-only (every leg of an index multi-leg order has one expiry).
- Buying power: an open reserves its maximum loss plus fees plus 10%.
- Fees a contract, both sides: OCC $0.025, ORF $0.015, CAT $0.0003; on sells also TAF $0.00329 and
  the SEC fee on the premium. Index options add $0.50 a contract plus the exchange's fee (XSP: $0
  under 10 contracts). Each leg's fee is rounded UP to the cent a fill (the venue never rounds a fee
  in the trader's favour). Figures marked ASSUMED are not in the plan's table and are deliberately
  high; replace them when a real fill's activity shows the real number.
- Ticks: a single option $0.05 under $3 and $0.10 from $3, except penny-class contracts ($0.01 under
  $3, $0.05 from $3) and SPY, QQQ and IWM ($0.01 everywhere). A multi-leg order's net price trades
  in $0.01 (complex order books). ASSUMED: every root in the universe other than SPXW is penny-class.

numpy is not needed here: the live path imports this with the standard library alone.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

INDEX_ROOTS = frozenset({"XSP", "SPXW", "SPX", "VIX", "VIXW", "DJX"})
PENNY_ALL = frozenset({"SPY", "QQQ", "IWM"})
NICKEL = frozenset({"SPXW", "SPX", "VIX", "VIXW", "DJX"})
#: Roots whose expiring closes may go on to 15:25 ET (the House's rule; the venue's is 15:30).
LATE_CLOSE = frozenset({"SPY", "QQQ"})
#: The House's expiry-day rule for equity options (the constitution's `order_path` defaults): an
#: expiring structure with a leg in or within this share of the money is closed at the natural from
#: `EXPIRY_CLOSE_LEAD` minutes before the close cutoff.
NEAR_MONEY_SHARE = 0.01
EXPIRY_CLOSE_LEAD = 10
MULTIPLIER = 100
NET_TICK = 0.01

OCC_FEE = 0.025
ORF_FEE = 0.015
CAT_FEE = 0.0003
TAF_FEE = 0.00329
#: SEC Section 31 fee on sells, dollars per dollar of premium: $20.60 a million, the rate for covered
#: sales from April 4, 2026 until 60 days after the fiscal 2027 appropriation is enacted (it was $0.00
#: from May 14, 2025 to April 3, 2026, $27.80 before that). Verified Sept 26, 2026: SEC fee rate
#: advisory "Section 31 Transaction Fee Rate Advisory for Fiscal Year 2026" (Feb 27, 2026,
#: https://www.sec.gov/rules-regulations/fee-rate-advisories/2026-2) and FINRA Information Notice
#: 20260317 (https://www.finra.org/rules-guidance/notices/information-notice-20260317). The Gym charges
#: today's rate on every window: it prices what a trade would cost now, not what it cost then.
SEC_RATE = 20.60e-6
INDEX_FEE = 0.50
#: The exchange's fee a contract on index options. XSP is $0 under 10 contracts (the plan); the
#: others are ASSUMED.
EXCHANGE_FEE = {"SPXW": 0.66, "SPX": 0.66, "VIX": 0.45, "VIXW": 0.45, "DJX": 0.18}
XSP_LARGE_ORDER_FEE = 0.07  # ASSUMED: XSP at 10 or more contracts a leg

STRUCTURE_TYPES = ("long_call", "long_put", "debit_vertical", "credit_vertical", "iron_condor", "iron_butterfly",
                   "long_butterfly", "long_straddle", "long_strangle", "calendar", "diagonal")
#: The five types the venue closes in one order (the only ones real money trades for now).
ONE_ORDER_CLOSE = ("debit_vertical", "credit_vertical", "iron_condor", "iron_butterfly", "long_butterfly")


def is_index(root: str) -> bool:
    return str(root).upper() in INDEX_ROOTS


@dataclass(frozen=True)
class Rules:
    """One root's venue rules on one session. Minutes are since midnight ET."""

    root: str
    kind: str                 # "equity" (physical, American) or "index" (cash, European)
    open_minute: int          # the session's first minute
    close_minute: int         # the session's last minute (16:00, or 13:00 on a half day)
    open_cutoff: int          # from this minute no new opening order on an expiring contract
    close_cutoff: int         # from this minute no closing order on an expiring contract
    liquidation: int | None   # from this minute expiring equity positions in or near the money are closed at natural; None for index
    calendars: bool           # calendars and diagonals admitted (equity only)
    multiplier: int = MULTIPLIER
    net_tick: float = NET_TICK
    bp_buffer: float = 0.10
    max_legs: int = 4
    expiry_close: int | None = None   # from this minute to close_cutoff the House closes them (equity); None for index
    near_money_share: float = NEAR_MONEY_SHARE  # "near the money": in it, or out of it by at most this share of the strike

    def as_dict(self) -> dict:
        row = asdict(self)
        row["types"] = tuple(t for t in STRUCTURE_TYPES if self.calendars or t not in ("calendar", "diagonal"))
        return row


def rules_for(root: str, *, open_minute: int = 570, close_minute: int = 960) -> Rules:
    """The rules a program trading `root` meets on a session that runs open_minute..close_minute."""
    root = str(root).upper()
    index = is_index(root)
    close_cutoff = int(close_minute) - (35 if root in LATE_CLOSE else 50)
    return Rules(
        root=root, kind="index" if index else "equity", open_minute=int(open_minute), close_minute=int(close_minute),
        open_cutoff=int(close_minute) - 60,
        close_cutoff=close_cutoff,
        liquidation=None if index else int(close_minute) - 30,
        calendars=not index,
        expiry_close=None if index else close_cutoff - EXPIRY_CLOSE_LEAD,
    )


def near_money(strike: float, is_call: bool, spot: float, share: float = NEAR_MONEY_SHARE) -> bool:
    """In the money, or out of it by no more than `share` of the strike (the live path's `_near_money`);
    True when there is no price to tell."""
    spot = float(spot)
    if not math.isfinite(spot) or spot <= 0:
        return True
    if is_call:
        return spot >= float(strike) * (1.0 - share)
    return spot <= float(strike) * (1.0 + share)


def leg_tick(root: str, price: float) -> float:
    """The price increment of ONE option contract of `root` at `price`."""
    root = str(root).upper()
    if root in PENNY_ALL:
        return 0.01
    if root in NICKEL:
        return 0.05 if price < 3.0 else 0.10
    return 0.01 if price < 3.0 else 0.05


def round_price(price: float, tick: float, *, up: bool) -> float:
    """`price` to a whole number of ticks, up or down (a small epsilon keeps 1.10 at 1.10)."""
    units = price / tick
    units = math.ceil(units - 1e-7) if up else math.floor(units + 1e-7)
    return round(units * tick, 6)


def leg_fee(root: str, contracts: int, price: float, *, sell: bool) -> float:
    """The fee of one leg's fill: `contracts` contracts at `price` a share, bought or sold. Rounded up
    to the cent."""
    contracts = int(contracts)
    if contracts <= 0:
        return 0.0
    root = str(root).upper()
    per = OCC_FEE + ORF_FEE + CAT_FEE
    if sell:
        per += TAF_FEE
    fee = per * contracts
    if sell:
        fee += SEC_RATE * max(0.0, float(price)) * MULTIPLIER * contracts
    if is_index(root):
        fee += INDEX_FEE * contracts
        if root == "XSP":
            fee += 0.0 if contracts < 10 else XSP_LARGE_ORDER_FEE * contracts
        else:
            fee += EXCHANGE_FEE.get(root, 0.66) * contracts
    return math.ceil(fee * 100.0 - 1e-9) / 100.0


__all__ = ["Rules", "rules_for", "near_money", "leg_tick", "round_price", "leg_fee", "is_index", "STRUCTURE_TYPES",
           "ONE_ORDER_CLOSE", "MULTIPLIER", "NET_TICK", "INDEX_ROOTS"]
