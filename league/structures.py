"""Level-3 option structures with defined risk, each held as ONE position.

Sept 25, 2026 (the options-desk run, `docs/goals/LTCM_OPTIONS_DESK.md` and the owner's amendment of
06:01Z in `docs/runs/2026-09-25-options-desk.md`). The Alpaca accounts are approved for level 3 and the
House used level 2: single long contracts under a $0.75 affordability line, which put every options
agent on penny contracts of $10-30 stocks with spreads up to 20%. A structure puts SPY, QQQ and IWM
inside the $75 order cap: a $1-wide vertical or iron condor can lose $30-70.

**What is admitted** (`TYPES`; anything else is refused with the reason): debit and credit verticals,
iron condors and iron butterflies, long butterflies, calendars and diagonals, long straddles and long
strangles. Every one has a loss bounded by what it costs to hold (below). Refused always: a naked short
leg, a ratio other than a butterfly's body, a broken wing, a diagonal whose long leg is less favourable
than its short one, mixed underlyings, a contract twice.

**How a book holds one: ONE long option-class instrument, priced at S = net value + K.** The net value
a share is the long legs' prices less the short legs' (x their ratios); K is the structure's collateral,
zero for a debit structure and the widest wing for a credit one. So:

- a DEBIT structure is held at its net value, and opening it costs its debit, its maximum loss;
- a CREDIT structure is held at K less what buying it back would cost, and opening it "costs" K less
  the credit received, which is again its maximum loss: exactly what a cash account sets aside;
- for every type, an open is a BUY of the held instrument and a close is a SELL, maximum loss in dollars
  is the held price paid x 100 x quantity (the order and position caps meter exactly that, as they
  meter a long contract's premium), the mark is the structure's bid, realized P&L is (S sold - S paid)
  x 100 x quantity, and a sale that leaves it flat is ONE closed trade for the evaluator, the allocator
  and the family record. No book holds a negative leg, so none can freeze on adopting one.

The instrument (`instrument`) is on the underlying, at the EARLIEST leg's expiry (the House's expiry
rules read it), with the first leg's strike and right, a multiplier of 100, and a `market_id` naming
the type and every leg in canonical order (`code`): `iron_condor|+1SPY260928P00580000|-1SPY...`.
`spec_of` reads it back. Strategies write the natural intent (`parse`): `limit_price` is the most to pay
or the least credit to take, as a trader says it, and `held_limit` converts it.

`quote` is the structure's touch from its legs' touches, what all legs trade at AT ONCE: to open, long
legs at the ask and short legs at the bid; to close, the reverse. `intrinsic` is its value at expiry
(single-expiry types). The replay's fee is `FEE_PER_CONTRACT` a contract a leg a fill (`fee_per_unit`).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Mapping, Sequence

from ltcm.adapters.alpaca import alpaca_symbol
from ltcm.broker import Instrument, money

from .venues import instrument_for

ZERO = Decimal(0)
CENT = Decimal("0.01")
HUNDRED = Decimal(100)
#: The replay's assumed fee, a contract a leg a fill (`league/options_replay.py`).
FEE_PER_CONTRACT = Decimal("0.05")

DEBIT_TYPES = ("debit_vertical", "long_butterfly", "calendar", "diagonal", "long_straddle", "long_strangle")
CREDIT_TYPES = ("credit_vertical", "iron_condor", "iron_butterfly")
TYPES = DEBIT_TYPES + CREDIT_TYPES
#: Types whose value a share never exceeds a known bound (the width, the wing or the collateral).
BOUNDED = ("debit_vertical", "long_butterfly", "credit_vertical", "iron_condor", "iron_butterfly")
#: Types with more than one expiry: no value at the near expiry without the far leg's market.
TWO_EXPIRIES = ("calendar", "diagonal")

_OCC = r"[A-Z]{1,6}[0-9]{6}[CP][0-9]{8}"
_CODE = re.compile(rf"^({'|'.join(TYPES)})((?:\|[+-][12]{_OCC}){{2,4}})$")
_LEG = re.compile(rf"\|([+-])([12])({_OCC})")


@dataclass(frozen=True)
class Leg:
    """One contract of a structure: `sign` +1 long, -1 short; `ratio` contracts a structure."""

    instrument: Instrument
    sign: int
    ratio: int = 1

    @property
    def occ(self) -> str:
        return alpaca_symbol(self.instrument)

    @property
    def strike(self) -> Decimal:
        return money(self.instrument.strike)

    @property
    def right(self) -> str:
        return str(self.instrument.right)

    @property
    def expiry(self) -> str:
        return str(self.instrument.expiry)

    @property
    def role(self) -> str:
        return "long" if self.sign > 0 else "short"


def _canonical(legs: Sequence[Leg]) -> tuple[Leg, ...]:
    return tuple(sorted(legs, key=lambda leg: (leg.expiry, leg.right, leg.strike, leg.sign)))


@dataclass(frozen=True)
class Spec:
    """A structure's type and legs, validated (`classify`): what it is, not how many or at what price."""

    type: str
    legs: tuple[Leg, ...]

    @property
    def underlying(self) -> str:
        return self.legs[0].instrument.symbol.upper()

    @property
    def venue(self) -> str:
        return self.legs[0].instrument.venue

    @property
    def expiry(self) -> str:
        """The EARLIEST expiry: the structure's clock."""
        return min(leg.expiry for leg in self.legs)

    @property
    def credit(self) -> bool:
        return self.type in CREDIT_TYPES

    @property
    def collateral(self) -> Decimal:
        """K a share: zero for a debit structure; the widest wing for a credit one."""
        if self.type == "credit_vertical":
            return abs(self.legs[0].strike - self.legs[1].strike)
        if self.type in ("iron_condor", "iron_butterfly"):
            puts = [leg.strike for leg in self.legs if leg.right == "put"]
            calls = [leg.strike for leg in self.legs if leg.right == "call"]
            return max(max(puts) - min(puts), max(calls) - min(calls))
        return ZERO

    @property
    def max_value(self) -> Decimal | None:
        """The most the held price S can be worth a share, where it is bounded."""
        if self.type == "debit_vertical":
            return abs(self.legs[0].strike - self.legs[1].strike)
        if self.type == "long_butterfly":
            strikes = sorted(leg.strike for leg in self.legs)
            return strikes[1] - strikes[0]
        if self.credit:
            return self.collateral
        return None

    @property
    def code(self) -> str:
        """The `market_id` of the held instrument: the type and every leg in canonical order."""
        return self.type + "".join(f"|{'+' if leg.sign > 0 else '-'}{leg.ratio}{leg.occ}" for leg in self.legs)

    @property
    def contracts(self) -> int:
        """Contracts a structure (a condor 4, a butterfly 4, a vertical 2)."""
        return sum(leg.ratio for leg in self.legs)

    def intent_legs(self) -> list[dict[str, Any]]:
        """The legs as an intent names them (to close what is held, for instance)."""
        return [{"occ": leg.occ, "role": leg.role, **({"ratio": leg.ratio} if leg.ratio != 1 else {})} for leg in self.legs]


def classify(type_: str, legs: Sequence[Leg]) -> Spec:
    """The `Spec` of `legs` as a `type_`, or ValueError saying why it is not one (and never a structure
    whose loss is unbounded: every admitted type's loss is bounded by what it costs to hold)."""
    if type_ not in TYPES:
        raise ValueError(f"a structure is one of {', '.join(TYPES)}; {type_!r} is not admitted")
    legs = _canonical(legs)
    if not 2 <= len(legs) <= 4:
        raise ValueError("a structure has two to four legs")
    for leg in legs:
        if leg.instrument.asset_class != "option":
            raise ValueError("every leg of a structure is an option contract")
        if leg.sign not in (1, -1):
            raise ValueError("a leg is long or short")
        if leg.ratio not in (1, 2):
            raise ValueError("a leg's ratio is 1, or 2 for a long butterfly's body")
    if len({leg.instrument.symbol.upper() for leg in legs}) != 1 or len({leg.instrument.venue for leg in legs}) != 1:
        raise ValueError("every leg is on one underlying")
    if len({leg.occ for leg in legs}) != len(legs):
        raise ValueError("a contract appears twice")
    if len({leg.instrument.multiplier for leg in legs}) != 1:
        raise ValueError("every leg has the same multiplier")
    if any(leg.ratio != 1 for leg in legs) and type_ != "long_butterfly":
        raise ValueError(f"a {type_} is 1:1 on every leg: a ratio leaves a leg uncovered")
    longs = [leg for leg in legs if leg.sign > 0]
    shorts = [leg for leg in legs if leg.sign < 0]
    expiries = {leg.expiry for leg in legs}
    rights = {leg.right for leg in legs}

    def need(ok: bool, why: str) -> None:
        if not ok:
            raise ValueError(f"not a {type_}: {why}")

    if type_ in ("debit_vertical", "credit_vertical"):
        need(len(legs) == 2 and len(longs) == 1 and len(shorts) == 1, "one long and one short leg")
        need(len(expiries) == 1 and len(rights) == 1, "one expiry and one right")
        long, short = longs[0], shorts[0]
        need(long.strike != short.strike, "two strikes")
        long_dearer = long.strike < short.strike if long.right == "call" else long.strike > short.strike
        if type_ == "debit_vertical":
            need(long_dearer, "the long leg must be the dearer strike (the lower call, the higher put); reversed it is a credit vertical")
        else:
            need(not long_dearer, "the short leg must be the dearer strike (the lower call, the higher put); reversed it is a debit vertical")
    elif type_ in ("long_straddle", "long_strangle"):
        need(len(legs) == 2 and len(longs) == 2, "two long legs, nothing sold")
        need(rights == {"call", "put"} and len(expiries) == 1, "a call and a put of one expiry")
        same = legs[0].strike == legs[1].strike
        need(same if type_ == "long_straddle" else not same, "one strike" if type_ == "long_straddle" else "two strikes")
    elif type_ in ("iron_condor", "iron_butterfly"):
        need(len(legs) == 4 and len(longs) == 2 and len(shorts) == 2, "four legs, two long and two short")
        need(len(expiries) == 1, "one expiry")
        puts = [leg for leg in legs if leg.right == "put"]
        calls = [leg for leg in legs if leg.right == "call"]
        need(len(puts) == 2 and len(calls) == 2, "two puts and two calls")
        lp = [leg for leg in puts if leg.sign > 0]
        sp = [leg for leg in puts if leg.sign < 0]
        sc = [leg for leg in calls if leg.sign < 0]
        lc = [leg for leg in calls if leg.sign > 0]
        need(len(lp) == len(sp) == len(sc) == len(lc) == 1, "one long and one short put, one short and one long call")
        need(lp[0].strike < sp[0].strike, "the long put below the short put")
        need(sc[0].strike < lc[0].strike, "the long call above the short call")
        if type_ == "iron_condor":
            need(sp[0].strike < sc[0].strike, "the short put below the short call (equal strikes are an iron butterfly)")
        else:
            need(sp[0].strike == sc[0].strike, "the short put and the short call at one strike")
    elif type_ == "long_butterfly":
        need(len(legs) == 3 and len(expiries) == 1 and len(rights) == 1, "three legs of one expiry and right")
        low, mid, high = legs  # canonical order: by strike within one expiry and right
        need(low.strike < mid.strike < high.strike, "three strikes")
        need((low.sign, low.ratio, mid.sign, mid.ratio, high.sign, high.ratio) == (1, 1, -1, 2, 1, 1),
             "long one low, short two middle, long one high")
        need(mid.strike - low.strike == high.strike - mid.strike, "equal wings (a broken wing's loss is not its debit)")
    elif type_ in ("calendar", "diagonal"):
        need(len(legs) == 2 and len(longs) == 1 and len(shorts) == 1, "one long and one short leg")
        need(len(rights) == 1, "one right")
        long, short = longs[0], shorts[0]
        need(short.expiry < long.expiry, "the short leg expires first, the long leg later")
        if type_ == "calendar":
            need(long.strike == short.strike, "one strike (two strikes are a diagonal)")
        else:
            need(long.strike != short.strike, "two strikes (one strike is a calendar)")
            covered = long.strike < short.strike if long.right == "call" else long.strike > short.strike
            need(covered, "the long leg's strike must be at least as favourable as the short's "
                          "(a lower call, a higher put), or its loss is more than its debit")
    return Spec(type_, legs)


@dataclass(frozen=True)
class Order:
    """A parsed structure intent: open or close `quantity` structures at a natural net `limit_price`."""

    spec: Spec
    action: str
    quantity: Decimal
    limit_price: Decimal
    reason: str

    @property
    def side(self) -> str:
        """The side of the held instrument: an open buys it, a close sells it."""
        return "buy" if self.action == "open" else "sell"

    @property
    def held_limit(self) -> Decimal:
        return held_limit(self.spec, self.action, self.limit_price)

    @property
    def max_loss_usd(self) -> Decimal:
        """What an open can lose in all (zero for a close, which takes risk off)."""
        return self.held_limit * self.spec.legs[0].instrument.multiplier * self.quantity if self.action == "open" else ZERO


def held_limit(spec: Spec, action: str, natural: Any) -> Decimal:
    """A natural limit (the most debit to pay or least credit to take on an open; the least to receive
    or most to pay on a close) as the held instrument's limit S, with the checks that make an order
    meaningful: an open that could never pay, or a credit at or over its collateral, is refused."""
    price = money(natural)
    if price <= 0 or price != price.quantize(CENT):
        raise ValueError("a structure's limit is a positive net price a share in whole cents")
    price = price.quantize(CENT)
    k = spec.collateral
    if not spec.credit:
        if action == "open" and spec.max_value is not None and price >= spec.max_value:
            raise ValueError(f"a debit of {price:.2f} on a {spec.type} worth at most {spec.max_value:.2f} can never pay")
        return price
    if price >= k:
        what = "a credit" if action == "open" else "a buy-back"
        raise ValueError(f"{what} of {price:.2f} on a {spec.type} with {k:.2f} of collateral is not a defined-risk order")
    return k - price


def natural_price(spec: Spec, held: Any) -> Decimal:
    """The inverse of `held_limit`: a held price S as a trader says it (the debit value, or the cost to
    buy a credit structure back)."""
    held = money(held)
    return held if not spec.credit else spec.collateral - held


def _leg_from(venue: str, row: Mapping[str, Any]) -> Leg:
    role = str(row.get("role") or "").lower()
    if role not in ("long", "short"):
        raise ValueError("every leg has a role, long or short")
    ratio = row.get("ratio", 1)
    try:
        ratio = int(ratio)
    except (TypeError, ValueError) as exc:
        raise ValueError("a leg's ratio is a whole number") from exc
    try:
        inst = instrument_for(venue, {k: v for k, v in row.items() if k not in ("role", "ratio")})
    except ValueError as exc:
        raise ValueError(f"a {role} leg: {exc}") from exc
    return Leg(inst, 1 if role == "long" else -1, ratio)


def parse(venue: str, row: Mapping[str, Any]) -> Order:
    """A strategy's structure intent (the spec's schema), validated; ValueError says what is wrong.
    The verticals schema `{"spread": "debit_vertical", "side": "buy"|"sell", ...}` is read as an alias."""
    type_ = row.get("structure") or row.get("spread")
    if not type_:
        raise ValueError("a structure intent names its `structure`")
    action = str(row.get("action") or "").lower()
    if not action and row.get("spread"):
        action = {"buy": "open", "sell": "close"}.get(str(row.get("side") or "").lower(), "")
    if action not in ("open", "close"):
        raise ValueError("`action` is open or close")
    if str(row.get("type") or "limit").lower() != "limit" or row.get("limit_price") is None:
        raise ValueError("a structure is a limit order at its net price a share: it has no touch to take")
    legs = row.get("legs")
    if not isinstance(legs, (list, tuple)) or not all(isinstance(leg, Mapping) for leg in legs):
        raise ValueError("`legs` is a list of {occ, role}")
    spec = classify(str(type_), [_leg_from(venue, leg) for leg in legs])
    try:
        quantity = money(str(row.get("quantity", "")))
    except ValueError as exc:
        raise ValueError(f"quantity is a number: {exc}") from exc
    if quantity <= 0 or quantity % 1 != 0:
        raise ValueError("quantity is a whole number of structures, at least one")
    reason = row.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("every intent needs a reason")
    order = Order(spec, action, quantity, money(str(row["limit_price"])), reason.strip())
    order.held_limit  # noqa: B018 - the limit's own checks, now
    return order


# ------------------------------------------------------------------------ the one held instrument
def instrument(spec: Spec, venue: str | None = None) -> Instrument:
    """The ONE instrument a book holds for `spec` (the module's docstring says why)."""
    first = spec.legs[0]
    return Instrument("option", spec.underlying, venue or spec.venue, multiplier=first.instrument.multiplier,
                      expiry=spec.expiry, strike=first.strike, right=first.right, market_id=spec.code)


def is_structure(inst: Any) -> bool:
    return getattr(inst, "asset_class", None) == "option" and bool(_CODE.match(str(getattr(inst, "market_id", None) or "")))


def spec_of(inst: Instrument) -> Spec:
    """The `Spec` a held instrument names, on the instrument's venue (validated again: a reversed or
    tampered code can never be traded)."""
    found = _CODE.match(str(inst.market_id or ""))
    if inst.asset_class != "option" or not found:
        raise ValueError(f"not a structure held as one position: {inst.key}")
    legs = [Leg(instrument_for(inst.venue, {"occ": occ}), 1 if sign == "+" else -1, int(ratio))
            for sign, ratio, occ in _LEG.findall(found.group(2))]
    return classify(found.group(1), legs)


def quote(spec: Spec, touches: Mapping[str, tuple[Any, Any]]) -> tuple[Decimal | None, Decimal | None]:
    """The held instrument's touch (bid, ask) a share from each leg's (bid, ask), keyed by OCC code:
    what every leg trades at AT ONCE. bid = K + long bids - short asks (never under zero); ask = K +
    long asks - short bids. A side missing any leg's price is None."""
    bid: Decimal | None = spec.collateral
    ask: Decimal | None = spec.collateral
    for leg in spec.legs:
        leg_bid, leg_ask = (touches.get(leg.occ) or (None, None))[:2]
        leg_bid = None if leg_bid is None else money(leg_bid)
        leg_ask = None if leg_ask is None else money(leg_ask)
        if leg.sign > 0:
            bid = None if bid is None or leg_bid is None else bid + leg.ratio * leg_bid
            ask = None if ask is None or leg_ask is None else ask + leg.ratio * leg_ask
        else:
            bid = None if bid is None or leg_ask is None else bid - leg.ratio * leg_ask
            ask = None if ask is None or leg_bid is None else ask - leg.ratio * leg_bid
    return (None if bid is None else max(ZERO, bid)), ask


def intrinsic(spec: Spec, spot: Any) -> Decimal:
    """The held price S a share at the (single) expiry with the underlying at `spot`."""
    if spec.type in TWO_EXPIRIES:
        raise ValueError(f"a {spec.type} has no value at its near expiry without the far leg's market: close it before")
    spot = money(spot)
    value = spec.collateral
    for leg in spec.legs:
        worth = max(ZERO, spot - leg.strike) if leg.right == "call" else max(ZERO, leg.strike - spot)
        value += leg.sign * leg.ratio * worth
    return max(ZERO, value)


def max_gain(spec: Spec, held_paid: Any) -> Decimal | None:
    """What a structure bought at `held_paid` can make a share, where bounded (None where not)."""
    top = spec.max_value
    return None if top is None else max(ZERO, top - money(held_paid))


def fee_per_unit(spec: Spec) -> Decimal:
    """The assumed fee of one structure's fill: a contract a leg (a vertical $0.10, a condor $0.20)."""
    return FEE_PER_CONTRACT * spec.contracts


def mleg_legs(spec: Spec, action: str) -> list[dict[str, str]]:
    """The legs of the venue's multi-leg order (Alpaca's documented `legs` shape): on an open the long
    legs `buy`/`buy_to_open` and the short legs `sell`/`sell_to_open`; on a close the reverse."""
    opening = action == "open"
    rows = []
    for leg in spec.legs:
        buys = (leg.sign > 0) == opening
        intent = ("buy_to_open" if leg.sign > 0 else "sell_to_open") if opening else ("sell_to_close" if leg.sign > 0 else "buy_to_close")
        rows.append({"symbol": leg.occ, "ratio_qty": str(leg.ratio), "side": "buy" if buys else "sell", "position_intent": intent})
    return rows


__all__ = ["TYPES", "DEBIT_TYPES", "CREDIT_TYPES", "BOUNDED", "TWO_EXPIRIES", "FEE_PER_CONTRACT", "Leg", "Spec", "Order",
           "classify", "parse", "held_limit", "natural_price", "instrument", "is_structure", "spec_of", "quote", "intrinsic",
           "max_gain", "fee_per_unit", "mleg_legs"]
