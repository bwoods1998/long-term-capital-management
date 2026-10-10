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

Which rule binds: the caps of steps 3-7 are each computed on the same facts and the entry is their minimum; the binding
named is the first, in the order above, whose cap is that minimum ("intent" when none cuts the target). A cap that
leaves nothing (zero or below) refuses the entry under its own name; a remainder above zero but under `min_order_usd`
(after the share count is floored) is skipped as "min_order", its reason naming the cap that cut it.

Two code ceilings, as the gateway keeps its own: `position_share` is never read above `config.POSITION_SHARE` of its
class (0.50 an ETF, 0.20 a stock, the owner's lines), and a class outside `config.CLASSES` is refused (ValueError), as
are malformed facts (a share outside (0, 1], both or neither of `share` and `usd`, a limit or a weight not above zero, a
value that is not a finite Decimal): the caller refuses the open and records why.

E is the sizing equity: min(account equity, the grant's ratified capital) live (`OptionsLive.sizing_equity`), the
sleeve E0 in the Gym.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from decimal import ROUND_DOWN, Decimal

from . import config

ZERO = Decimal(0)
#: The order the caps are named in when two tie (the module docstring's steps 3-7).
CAPS = ("instrument", "sleeve_cap", "sleeve_cash", "invested", "cash", "budget")


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


def _usd(value: Decimal) -> str:
    return f"${value.quantize(Decimal('0.01'), rounding=ROUND_DOWN)}"


def _checked(x: SizingInputs) -> None:
    """ValueError when the facts are malformed (the module docstring): never a size from a fact that cannot be read."""
    if x.klass not in config.CLASSES:
        raise ValueError(f"{x.symbol}: the class {x.klass!r} is not one of {config.CLASSES}")
    for f in fields(x):
        value = getattr(x, f.name)
        if f.name in ("symbol", "klass", "any_short") or (value is None and f.name in ("share", "usd", "budget_room")):
            continue
        if not isinstance(value, Decimal) or not value.is_finite():
            raise ValueError(f"{x.symbol}: {f.name} is not a finite Decimal: {value!r}")
    if not isinstance(x.any_short, bool):
        raise ValueError(f"{x.symbol}: any_short is not a bool: {x.any_short!r}")
    if (x.share is None) == (x.usd is None):
        raise ValueError(f"{x.symbol}: an intent sets exactly one of share and usd")
    if x.share is not None and not ZERO < x.share <= 1:
        raise ValueError(f"{x.symbol}: an intent's share is in (0, 1], not {x.share}")
    if x.usd is not None and x.usd <= 0:
        raise ValueError(f"{x.symbol}: an intent's usd is above zero, not {x.usd}")
    if x.limit_price <= 0 or x.weight <= 0:
        raise ValueError(f"{x.symbol}: the limit price and the open-risk weight are above zero")


def size_entry(x: SizingInputs) -> Sized:
    """THE RULE (the module docstring): the entry's dollars and shares, the rule that set them, and why."""
    _checked(x)
    if x.cash < 0:
        return Sized(ZERO, ZERO, "cash_negative", f"no equity open while the account's cash is below zero ({_usd(x.cash)}): "
                                                  "the account would be borrowing")
    if x.any_short:
        return Sized(ZERO, ZERO, "short_held", "no equity open while any us_equity position is short")
    target = x.sleeve_equity * x.share if x.share is not None else x.usd
    share = min(x.position_share, config.POSITION_SHARE[x.klass])
    caps = {
        "instrument": share * x.E - x.account_symbol_value,
        "sleeve_cap": share * x.sleeve_equity - x.sleeve_symbol_value,
        "sleeve_cash": x.sleeve_free_cash,
        "invested": x.invested_share * x.E - x.invested_now,
        "cash": x.available_cash,
    }
    if x.budget_room is not None:
        caps["budget"] = x.budget_room / x.weight
    why = {
        "instrument": f"{x.symbol} may hold {_usd(caps['instrument'])} more on the account ({share} x E {_usd(x.E)}, less "
                      f"{_usd(x.account_symbol_value)} held and working across all programs)",
        "sleeve_cap": f"{x.symbol} may hold {_usd(caps['sleeve_cap'])} more in this program's sleeve ({share} x "
                      f"{_usd(x.sleeve_equity)}, less {_usd(x.sleeve_symbol_value)} of its own)",
        "sleeve_cash": f"the sleeve has {_usd(x.sleeve_free_cash)} of free cash",
        "invested": f"the invested cap leaves {_usd(caps['invested'])} ({x.invested_share} x E {_usd(x.E)}, less "
                    f"{_usd(x.invested_now)} of equity held and working and options' open maximum loss)",
        "cash": f"the House-wide available cash is {_usd(x.available_cash)} (after the reserve and every working buy)",
        "budget": (f"the shared loss budget has {_usd(x.budget_room)} of room, {_usd(caps['budget'])} of {x.klass} at "
                   f"weight {x.weight}") if x.budget_room is not None else "",
    }
    if target <= 0:
        return Sized(ZERO, ZERO, "intent", f"refused: the intent asks for nothing (its share of a sleeve of "
                                           f"{_usd(x.sleeve_equity)})")
    usd, binding = target, "intent"
    lowest = min(caps.values())
    if lowest < target:
        usd = lowest
        binding = next(name for name in CAPS if name in caps and caps[name] == lowest)
    if usd <= 0:
        return Sized(ZERO, ZERO, binding, f"refused: {why[binding]}")
    quantum = Decimal(1).scaleb(-config.QTY_PLACES)
    qty = (usd / x.limit_price).quantize(quantum, rounding=ROUND_DOWN)
    usd = qty * x.limit_price
    cut = f" ({why[binding]})" if binding != "intent" else ""
    if usd < x.min_order_usd:
        return Sized(ZERO, ZERO, "min_order", f"skipped: {_usd(usd)} is under the {_usd(x.min_order_usd)} minimum{cut}")
    if binding == "intent":
        return Sized(usd, qty, binding, f"{qty} {x.symbol} at {x.limit_price}: the intent's {_usd(target)}")
    return Sized(usd, qty, binding, f"{qty} {x.symbol} at {x.limit_price}: cut from {_usd(target)}: {why[binding]}")


__all__ = ["SizingInputs", "Sized", "CAPS", "size_entry"]
