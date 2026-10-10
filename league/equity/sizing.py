"""The one sizing function of an equity entry: the book (live) and the engine (the Gym) both call `size_entry`.

Owner: money. Pure, Decimal in and out (dollars and shares as Decimal; never a float), no clock, no I/O, no import of
league.live (it is evidence code: inside the equity fingerprint, `league.swarm.evaluator.equity_fingerprint`).

THE RULE (the design's section 4b with amendments A1, A5 and A8.1), in order; the first that binds is named in
`Sized.binding`:

1. REFUSED outright (usd 0) when `cash` < 0 ("cash_negative") or `any_short` ("short_held"): no equity open while the
   account owes cash or holds any us_equity short.
2. target = the intent's share of the program's sleeve equity (`sleeve_equity` x `share`), or its `usd` ("intent").
3. capped by THE INSTRUMENT CAP on the account: `position_share` x E minus the account's holding of the symbol and its
   open buys across all programs ("instrument"); and by the same share of the SLEEVE minus this program's own holding
   (`sleeve_symbol_value`), so a live position is never a larger share of its sleeve than the Gym allows ("sleeve_cap");
4. capped by the sleeve's free cash ("sleeve_cash");
5. capped by THE INVESTED CAP: equity long value + open equity buys + the options' open maximum loss + this entry <=
   `invested_share` x E (A1: "1.00", cash only by choice) ("invested");
6. capped by THE HOUSE-WIDE AVAILABLE CASH (A8.1: `league.live.money.available_cash`, the caller's figure) ("cash");
7. cut to fit THE LOSS BUDGET: target <= `budget_room` / `weight` (A5: the room left in the shared Probe budget, the
   lower of the window's and the total's, over the class's open-risk weight 0.20 ETF / 0.40 stock) ("budget"); None
   (the Gym) skips it;
8. SKIPPED (usd 0) under `min_order_usd` ("min_order").
qty = floor(usd / `limit_price`, `config.QTY_PLACES` places); usd = qty x limit_price (never more than the target).

E is the sizing equity: min(account equity, the grant's ratified capital) live (`OptionsLive.sizing_equity`), the
sleeve E0 in the Gym.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class SizingInputs:
    """One entry's sizing facts (dollars and shares as Decimal). `share` XOR `usd` is set (the intent's)."""

    symbol: str
    klass: str                       # "etf" | "stock"
    share: Decimal | None            # the intent's share of the sleeve equity, (0, 1]
    usd: Decimal | None              # or its dollars, > 0
    limit_price: Decimal             # the order's limit a share (the Gym: the fill price)
    E: Decimal                       # the sizing equity
    sleeve_equity: Decimal           # the program's sleeve equity (sleeve_share x E live; E0 in the Gym)
    sleeve_free_cash: Decimal        # the sleeve's cash not in lots or working buys
    sleeve_symbol_value: Decimal     # this program's own holding of the symbol (marked) + its open buys of it
    position_share: Decimal          # the class's share of E (0.50 / 0.20)
    account_symbol_value: Decimal    # every program's holding of the symbol (marked) + every open buy of it
    invested_now: Decimal            # equity long value + open equity buys + options open maximum loss
    invested_share: Decimal          # "1.00" in E1 (A1)
    available_cash: Decimal          # the House-wide figure (A8.1); the Gym: the sleeve's free cash
    cash: Decimal                    # the account's cash (refuse when < 0)
    any_short: bool                  # any us_equity short on the account
    budget_room: Decimal | None      # the loss budget's room (None: the Gym, no budget)
    weight: Decimal                  # open_risk_weight of the class (0.20 / 0.40)
    min_order_usd: Decimal           # "10"


@dataclass(frozen=True)
class Sized:
    """The answer: `usd` and `qty` (Decimal; 0 when refused or skipped), `binding` (the rule that set it: one of
    "intent", "instrument", "sleeve_cap", "sleeve_cash", "invested", "cash", "budget", "min_order", "cash_negative",
    "short_held"), and `reason` (a sentence for the record)."""

    usd: Decimal
    qty: Decimal
    binding: str
    reason: str


def size_entry(x: SizingInputs) -> Sized:
    """THE RULE (the module docstring)."""
    raise NotImplementedError("money: league/equity/sizing.py size_entry")


__all__ = ["SizingInputs", "Sized", "size_entry"]
