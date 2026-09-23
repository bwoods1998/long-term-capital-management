"""Level-3 debit verticals: the pure pieces, on a branch that nothing in the House imports.

Sept 23, 2026 (the learn-and-unblock run, workstream O). Both Alpaca accounts are approved for
options level 3 and the House uses level 2: it buys calls and puts and sells them back. A debit
vertical is the first level-3 strategy the proposal admits (`docs/proposals/
2026-09-23-alpaca-stocks-and-level-3-options.md`, B1), and `docs/design/
2026-09-24-level-3-debit-verticals.md` is its design against the code as it is. This module is the
part of that design that can be written and tested without a venue: what a debit vertical IS, what
it can lose, whether it fits the caps, the multi-leg order it would be, and how one spread's
per-leg fills count as one trade.

**Nothing in the House imports this module** (`league/tests/test_verticals.py` pins it), and no
multi-leg order goes to either account from this branch, practice included. A vertical's sold leg
is a negative position, which the practice book refuses to adopt (`league/book.py`
`_adopt_the_venue`: "a negative baseline leaves phantom holdings"), so a spread reaching the shared
practice account would freeze every Alpaca practice agent for as long as it was open. The gateway
refuses multi-leg orders before pricing (#187, `gateway/lib/caps.mjs` `alpacaShapeError`) and keeps
refusing them until the owner ratifies maximum-loss metering (the proposal's B2).

**A debit vertical** is two option contracts on one underlying, one expiry and one right (two calls
or two puts), one bought and one sold in equal numbers, opened and closed as ONE multi-leg order.
The bought leg is the dearer contract: the lower strike of two calls, the higher strike of two
puts. That is what makes the order a net DEBIT and bounds its loss at that debit, and it is the
proposal's "long leg nearer the money" exactly when both legs are out of the money (the usual case
inside the chain's 20% moneyness filter) and the rule that needs no spot price in every case. The
same two legs the other way round are a credit spread, a written option with a hedge, which B1
does not admit and `parse_vertical` refuses.

**Maximum loss** is the net debit x 100 x quantity. On a cash account it is paid in full when the
spread is opened, and it is all a debit vertical can ever lose, however far the underlying moves,
provided both legs are closed together and before expiry day (the design's exit rules). **Maximum
gain** is the strike width less the debit, x 100 x quantity. The caps mean this: the gateway's and
the rung's ORDER cap bounds the maximum loss of one opening order (what it can spend, as a long
option's premium x 100 is today); the rung's POSITION cap bounds the maximum loss of the spreads
held plus this one. Neither is the gross of the two legs' premiums. A close is never metered: it
takes risk off, as `ltcm.risk.reduces_exposure` lets an exit through the single-leg rules.

**One spread is one trade.** `count_trades` folds per-leg fills into per-contract positions and
counts one closed trade each time a pair that was open (one leg long, its partner short, same
underlying, expiry and right) is flat on both legs, however many fill rows the open and the close
took. A contract bought and sold on its own is never a spread and is not counted here: the
allocator's `closed_trades` counts it, as it does today. The fill shape assumed is Alpaca's
documented one, one FILL activity per leg with the leg's own OCC symbol, side and quantity
(`ltcm/adapters/alpaca.py` `fills`), and it is UNVERIFIED until the first practice multi-leg order.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Iterable, Mapping

from ltcm.adapters.alpaca import alpaca_symbol
from ltcm.broker import Instrument, money, text

from .venues import instrument_for

ZERO = Decimal(0)
ONE = Decimal(1)
CENT = Decimal("0.01")
#: The one spread B1 admits. Credit verticals, iron condors and calendars are B3 (the proposal).
SPREADS = ("debit_vertical",)
#: A leg's part in the spread. Given as `role`, never as a side: the sides follow from `side`
#: at the top of the intent (buy opens the spread, sell closes it), so a strategy cannot write
#: a close whose legs point the wrong way.
ROLES = ("long", "short")


@dataclass(frozen=True)
class DebitVertical:
    """One debit vertical as an agent wants it: the two contracts, how many spreads, the net
    price a share, and whether the intent opens (`buy`) or closes (`sell`) the spread.

    `net_debit` is the limit on the net price a share, always positive: on a buy the most the
    spread may cost (its debit, which is its maximum loss a share); on a sell the least the close
    must receive. The invariants below hold whether the value came through `parse_vertical` or was
    built directly, so no credit spread can be represented by this type at all."""

    long: Instrument
    short: Instrument
    quantity: Decimal
    net_debit: Decimal
    side: str = "buy"
    reason: str = ""

    def __post_init__(self) -> None:
        if self.long.asset_class != "option" or self.short.asset_class != "option":
            raise ValueError("both legs of a vertical are option contracts")
        same = [(a, b) for a, b in ((self.long.symbol.upper(), self.short.symbol.upper()), (self.long.expiry, self.short.expiry),
                                    (self.long.right, self.short.right), (self.long.venue, self.short.venue),
                                    (self.long.multiplier, self.short.multiplier)) if a != b]
        if same:
            raise ValueError(
                "both legs share one underlying, expiry and right: "
                f"{self.long.symbol} {self.long.expiry} {self.long.right} against {self.short.symbol} {self.short.expiry} {self.short.right}"
            )
        if self.long.strike == self.short.strike:
            raise ValueError("a vertical's legs are two strikes, not one")
        dearer = self.long.strike < self.short.strike if self.right == "call" else self.long.strike > self.short.strike
        if not dearer:
            raise ValueError(
                "the long leg must be the dearer contract (the lower strike of two calls, the higher of two puts): "
                "reversed, this is a credit spread, which is not admitted"
            )
        object.__setattr__(self, "quantity", money(self.quantity))
        if self.quantity <= 0 or self.quantity % 1 != 0:
            raise ValueError("quantity is a whole number of spreads, at least one")
        object.__setattr__(self, "net_debit", money(self.net_debit))
        if self.net_debit <= 0 or self.net_debit != self.net_debit.quantize(CENT):
            raise ValueError("a net debit is positive and in whole cents")
        object.__setattr__(self, "net_debit", self.net_debit.quantize(CENT))  # `0.6` from JSON is the venue's `0.60`
        if self.side not in ("buy", "sell"):
            raise ValueError("side is buy (open the spread) or sell (close it)")
        if self.side == "buy" and self.net_debit >= self.width:
            raise ValueError(f"a debit of {self.net_debit:.2f} on a {self.width:.2f}-wide spread can never pay")

    @property
    def underlying(self) -> str:
        return self.long.symbol.upper()

    @property
    def expiry(self) -> str:
        return str(self.long.expiry)

    @property
    def right(self) -> str:
        return str(self.long.right)

    @property
    def venue(self) -> str:
        return self.long.venue

    @property
    def multiplier(self) -> Decimal:
        return self.long.multiplier

    @property
    def width(self) -> Decimal:
        """The distance between the strikes, a share: the most the spread can be worth."""
        return abs(self.long.strike - self.short.strike)

    @property
    def key(self) -> str:
        """One spelling for one spread position, in the style of `book.position_key`."""
        return f"spread:{self.underlying}:{self.venue}:{self.expiry}:{self.right}:{_strike(self.long)}/{_strike(self.short)}"


def _strike(instrument: Instrument) -> str:
    return format(money(instrument.strike).normalize(), "f")


def parse_vertical(venue: str, spec: Mapping[str, Any]) -> DebitVertical:
    """An agent's spread intent, in plain data, as the design gives it to strategies:

        {"spread": "debit_vertical", "side": "buy", "quantity": 1, "type": "limit", "limit_price": 0.35,
         "legs": [{"occ": "F261016C00013000", "role": "long"}, {"occ": "F261016C00014000", "role": "short"}],
         "reason": "..."}

    A leg is named as any option is (`league.venues.instrument_for`: an `occ` code, or `symbol`,
    `expiry`, `strike`, `right`) plus its `role`. `side` buy opens the spread and sell closes it;
    `limit_price` is the net price a share. Everything else is refused with the reason, as the
    House refuses a malformed single-leg intent."""
    if str(spec.get("spread") or "") not in SPREADS:
        raise ValueError("a spread is \"debit_vertical\"; nothing else is admitted")
    legs = spec.get("legs")
    if not isinstance(legs, (list, tuple)) or len(legs) != 2 or not all(isinstance(leg, Mapping) for leg in legs):
        raise ValueError("a debit vertical is two legs, one long and one short")
    roles = [str(leg.get("role") or "").lower() for leg in legs]
    if sorted(roles) != sorted(ROLES):
        raise ValueError("a debit vertical's legs are one long and one short (`role`), never sides of their own")
    by_role = {}
    for role, leg in zip(roles, legs):
        try:
            by_role[role] = instrument_for(venue, {k: v for k, v in leg.items() if k != "role"})
        except ValueError as exc:
            raise ValueError(f"the {role} leg: {exc}") from exc
    if any(inst.asset_class != "option" for inst in by_role.values()):
        raise ValueError("both legs of a vertical are option contracts")
    side = str(spec.get("side") or "").lower()
    if side not in ("buy", "sell"):
        raise ValueError("side is buy (open the spread) or sell (close it)")
    if str(spec.get("type") or "").lower() != "limit" or spec.get("limit_price") is None:
        raise ValueError("a debit vertical is a limit order at its net price: a spread has no touch to take")
    try:
        net = money(str(spec["limit_price"]))
        quantity = money(str(spec.get("quantity", "")))
    except ValueError as exc:
        raise ValueError(f"net price and quantity are numbers: {exc}") from exc
    if quantity <= 0 or quantity % 1 != 0:
        raise ValueError("quantity is a whole number of spreads, at least one")
    reason = spec.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("every intent needs a reason")
    return DebitVertical(long=by_role["long"], short=by_role["short"], quantity=quantity, net_debit=net, side=side, reason=reason.strip())


# ---------------------------------------------------------------------------------- arithmetic
def max_loss(vertical: DebitVertical) -> Decimal:
    """What the spread can lose in all: the net debit x the multiplier x the quantity, paid in full
    when it is opened. A close (`side` sell) can lose nothing more: zero."""
    if vertical.side != "buy":
        return ZERO
    return vertical.net_debit * vertical.multiplier * vertical.quantity


def max_gain(vertical: DebitVertical) -> Decimal:
    """What the spread can make in all: the width less the debit, x the multiplier x the quantity.
    Zero for a close, which realises rather than risks."""
    if vertical.side != "buy":
        return ZERO
    return (vertical.width - vertical.net_debit) * vertical.multiplier * vertical.quantity


def cap_refusal(vertical: DebitVertical, order_cap: Decimal, position_cap: Decimal, *, held_max_loss: Decimal = ZERO) -> str | None:
    """Why the caps refuse this spread, or None when it fits. The order cap is the gateway's $75
    (`gateway/wrangler.jsonc` MAX_ORDER_USD_ALPACA) or the rung's `max_order_usd`, whichever the
    caller holds; the position cap is the rung's `max_position_usd`; `held_max_loss` is the maximum
    loss of the spreads the agent already holds. Both are met by MAXIMUM LOSS, never by the legs'
    gross. A close is never refused here: it takes risk off."""
    if vertical.side != "buy":
        return None
    loss = max_loss(vertical)
    if loss > money(order_cap):
        return f"a spread that can lose ${loss:.2f} is over the ${money(order_cap):f} order cap"
    together = money(held_max_loss) + loss
    if together > money(position_cap):
        return f"spreads that can lose ${together:.2f} together would be over the ${money(position_cap):f} position cap"
    return None


def fits_caps(vertical: DebitVertical, order_cap: Decimal, position_cap: Decimal, *, held_max_loss: Decimal = ZERO) -> bool:
    return cap_refusal(vertical, order_cap, position_cap, held_max_loss=held_max_loss) is None


# ------------------------------------------------------------------------------------- the order
def mleg_body(vertical: DebitVertical, *, client_order_id: str) -> dict[str, Any]:
    """The multi-leg order Alpaca documents for `POST /v2/orders`, as the adapter would send it: no
    top-level symbol, `order_class` mleg, `qty` spreads, a day limit at the net price, and two legs
    of `ratio_qty` 1 with their `position_intent`. It is the shape the gateway's tests refuse
    (`gateway/test/caps.test.mjs`, "a multi-leg order is never priced as a stock"), pinned here so
    the adapter change has a spec. The sign of a credit (negative, on a close) is Alpaca's
    documented convention and, like the rest, is UNVERIFIED until the first practice order. Never
    sent from this module: it is a dict."""
    opening = vertical.side == "buy"
    net = vertical.net_debit if opening else -vertical.net_debit
    return {
        "order_class": "mleg",
        "qty": text(vertical.quantity),
        "type": "limit",
        "limit_price": text(net),
        "time_in_force": "day",
        "client_order_id": client_order_id,
        "legs": [
            {"symbol": alpaca_symbol(vertical.long), "ratio_qty": "1", "side": "buy" if opening else "sell",
             "position_intent": "buy_to_open" if opening else "sell_to_close"},
            {"symbol": alpaca_symbol(vertical.short), "ratio_qty": "1", "side": "sell" if opening else "buy",
             "position_intent": "sell_to_open" if opening else "buy_to_close"},
        ],
    }


# ------------------------------------------------------------------------------------- evidence
def count_trades(fills: Iterable[Any]) -> int:
    """One spread's open and close, counted as ONE closed trade from per-leg fills.

    `fills` are `ltcm.broker.Fill`-shaped rows (an `instrument`, a `side`, a `quantity`, an `at`),
    one per leg per execution, in any order; they are read in time order. Per underlying, expiry
    and right the contracts' signed positions are folded fill by fill; the group is a spread once
    it holds a long leg and a short leg at the same time, and each time such a group is flat on
    every contract one trade is counted. So partial fills, a leg closed first (assigned away, or
    sold on its own) and a close in several orders all count once, and a contract traded on its
    own counts nothing. Rows of any other asset class are ignored.

    Assumed and unverified: Alpaca reports each leg's fill as its own FILL activity carrying the
    LEG's OCC symbol, side (`buy` or `sell`) and quantity, which is what `fills` returns today for
    a single contract. Nothing here reads order ids, so how the venue stamps a leg's `order_id`
    (its own, or its parent's) does not matter to the count. One spread at a time per underlying,
    expiry and right is the design's rule: two overlapping spreads that share a strike would net
    that leg and be read as one."""
    legs: dict[tuple[str, str, str, str], dict[str, Decimal]] = {}
    spread_seen: set[tuple[str, str, str, str]] = set()
    trades = 0
    for fill in sorted(fills, key=lambda f: str(getattr(f, "at", "") or "")):
        instrument = fill.instrument
        if instrument.asset_class != "option":
            continue
        group = (instrument.symbol.upper(), instrument.venue, str(instrument.expiry), str(instrument.right))
        held = legs.setdefault(group, {})
        contract = _strike(instrument)
        signed = money(fill.quantity) if str(fill.side).lower() == "buy" else -money(fill.quantity)
        held[contract] = held.get(contract, ZERO) + signed
        if held[contract] == 0:
            del held[contract]
        if any(q > 0 for q in held.values()) and any(q < 0 for q in held.values()):
            spread_seen.add(group)
        if not held and group in spread_seen:
            spread_seen.discard(group)
            trades += 1
    return trades


__all__ = ["DebitVertical", "SPREADS", "ROLES", "parse_vertical", "max_loss", "max_gain", "cap_refusal", "fits_caps", "mleg_body", "count_trades"]
