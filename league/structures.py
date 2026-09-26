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

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Mapping, Sequence

from league.adapters.alpaca import alpaca_symbol
from league.broker import Instrument, RejectedOrder, money

from . import structure_core as core
from .venues import instrument_for

# THE RULES LIVE IN `league/structure_core.py` (Sept 25, 2026, builder S3): the options replay runs in
# the agent's box with the standard library only, so the one implementation of the spec is written over
# OCC codes there, and this module is its House face: the same names over `league.broker.Instrument`.
# Every rule below delegates; `league/tests/test_structure_parity.py` pins the two for every type and
# refusal.
ZERO = core.ZERO
CENT = core.CENT
HUNDRED = core.HUNDRED
#: The replay's assumed fee, a contract a leg a fill (`league/options_replay.py`).
FEE_PER_CONTRACT = core.FEE_PER_CONTRACT

DEBIT_TYPES = core.DEBIT_TYPES
CREDIT_TYPES = core.CREDIT_TYPES
TYPES = core.TYPES
#: Types whose value a share never exceeds a known bound (the width, the wing or the collateral).
BOUNDED = core.BOUNDED
#: Types with more than one expiry: no value at the near expiry without the far leg's market.
TWO_EXPIRIES = core.TWO_EXPIRIES


def _occ(inst: Instrument) -> str:
    """The option's OCC code; a leg the venue could not spell (a malformed expiry) is a ValueError, as in
    `structure_core.occ_code`, never the venue's `RejectedOrder` (review of Sept 25, 2026: the House dropped
    such a row where the replay counted a refusal)."""
    try:
        return alpaca_symbol(inst)
    except RejectedOrder as exc:
        raise ValueError(str(exc)) from exc


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

    def core(self) -> core.Leg:
        """This leg as the core reads it (OCC code, sign, ratio, and what it is: asset class, venue,
        multiplier), so a leg that is not an option contract is refused by the core's own rule."""
        inst = self.instrument
        option = inst.asset_class == "option"
        return core.Leg(_occ(inst) if option else inst.symbol, self.sign, self.ratio, inst.symbol,
                        str(inst.expiry or ""), str(inst.right or ""), inst.strike if option else None,
                        inst.asset_class, inst.venue, inst.multiplier)


@dataclass(frozen=True)
class Spec:
    """A structure's type and legs, validated (`classify`): what it is, not how many or at what price."""

    type: str
    legs: tuple[Leg, ...]

    def core(self) -> core.Spec:
        return core.Spec(self.type, tuple(leg.core() for leg in self.legs))

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
        return self.core().collateral

    @property
    def max_value(self) -> Decimal | None:
        """The most the held price S can be worth a share, where it is bounded."""
        return self.core().max_value

    @property
    def code(self) -> str:
        """The `market_id` of the held instrument: the type and every leg in canonical order."""
        return self.core().code

    @property
    def contracts(self) -> int:
        """Contracts a structure (a condor 4, a butterfly 4, a vertical 2)."""
        return self.core().contracts

    def intent_legs(self) -> list[dict[str, Any]]:
        """The legs as an intent names them (to close what is held, for instance)."""
        return self.core().intent_legs()


def classify(type_: str, legs: Sequence[Leg]) -> Spec:
    """The `Spec` of `legs` as a `type_`, or ValueError saying why it is not one (and never a structure
    whose loss is unbounded: every admitted type's loss is bounded by what it costs to hold). The rules
    are `structure_core.classify`'s; the legs come back in its canonical order."""
    checked = core.classify(type_, [leg.core() for leg in legs])
    by_code: dict[tuple[str, int, int], Leg] = {}
    for leg in legs:
        by_code.setdefault((leg.core().occ, leg.sign, leg.ratio), leg)
    return Spec(type_, tuple(by_code[(leg.occ, leg.sign, leg.ratio)] for leg in checked.legs))


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
    return core.held_limit(spec.core(), action, natural)


def natural_price(spec: Spec, held: Any) -> Decimal:
    """The inverse of `held_limit`: a held price S as a trader says it (the debit value, or the cost to
    buy a credit structure back)."""
    return core.natural_price(spec.core(), held)


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
        if inst.asset_class == "option":
            # Read back from its OCC code, as the core reads every leg: a malformed expiry is this leg's
            # error, worded as the core words it, and one spelled another way ("20260928") is the same
            # contract as its code says, never a second expiry.
            inst = instrument_for(venue, {"occ": _occ(inst)})
    except ValueError as exc:
        raise ValueError(f"a {role} leg: {exc}") from exc
    return Leg(inst, 1 if role == "long" else -1, ratio)


def parse(venue: str, row: Mapping[str, Any]) -> Order:
    """A strategy's structure intent (the spec's schema), validated; ValueError says what is wrong.
    The verticals schema `{"spread": "debit_vertical", "side": "buy"|"sell", ...}` is read as an alias.
    The checks are `structure_core.parse`'s, in its order; the legs are read on `venue` here."""
    type_, action, legs = core.parse_fields(row)
    spec = classify(type_, [_leg_from(venue, leg) for leg in legs])
    quantity, limit, reason = core.parse_rest(row)
    order = Order(spec, action, quantity, limit, reason)
    order.held_limit  # noqa: B018 - the limit's own checks, now
    return order


# ------------------------------------------------------------------------ the one held instrument
def instrument(spec: Spec, venue: str | None = None) -> Instrument:
    """The ONE instrument a book holds for `spec` (the module's docstring says why)."""
    first = spec.legs[0]
    return Instrument("option", spec.underlying, venue or spec.venue, multiplier=first.instrument.multiplier,
                      expiry=spec.expiry, strike=first.strike, right=first.right, market_id=spec.code)


def is_structure(inst: Any) -> bool:
    return getattr(inst, "asset_class", None) == "option" and core.is_code(getattr(inst, "market_id", None))


def spec_of(inst: Instrument) -> Spec:
    """The `Spec` a held instrument names, on the instrument's venue (validated again: a reversed or
    tampered code can never be traded)."""
    found = core.CODE.match(str(inst.market_id or ""))
    if inst.asset_class != "option" or not found:
        raise ValueError(f"not a structure held as one position: {inst.key}")
    checked = core.spec_of_code(str(inst.market_id), venue=inst.venue)
    return classify(checked.type, [Leg(instrument_for(inst.venue, {"occ": leg.occ}), leg.sign, leg.ratio) for leg in checked.legs])


def quote(spec: Spec, touches: Mapping[str, tuple[Any, Any]]) -> tuple[Decimal | None, Decimal | None]:
    """The held instrument's touch (bid, ask) a share from each leg's (bid, ask), keyed by OCC code:
    what every leg trades at AT ONCE. bid = K + long bids - short asks (never under zero); ask = K +
    long asks - short bids. A side missing any leg's price is None."""
    return core.quote(spec.core(), touches)


def intrinsic(spec: Spec, spot: Any) -> Decimal:
    """The held price S a share at the (single) expiry with the underlying at `spot`."""
    return core.intrinsic(spec.core(), spot)


def max_gain(spec: Spec, held_paid: Any) -> Decimal | None:
    """What a structure bought at `held_paid` can make a share, where bounded (None where not)."""
    return core.max_gain(spec.core(), held_paid)


def fee_per_unit(spec: Spec) -> Decimal:
    """The assumed fee of one structure's fill: a contract a leg (a vertical $0.10, a condor $0.20)."""
    return core.fee_per_unit(spec.core())


def mleg_legs(spec: Spec, action: str) -> list[dict[str, str]]:
    """The legs of the venue's multi-leg order (Alpaca's documented `legs` shape): on an open the long
    legs `buy`/`buy_to_open` and the short legs `sell`/`sell_to_open`; on a close the reverse."""
    return core.mleg_legs(spec.core(), action)


# ------------------------------------------------------------------------ what a strategy is shown
def candidates(chain: Sequence[Mapping[str, Any]], *, max_loss_usd: Any, today: str, venue: str = "alpaca-paper",
               limit: int = 60) -> list[dict[str, Any]]:
    """Ready-made structures a strategy may send as they are (`ctx["structures"]`): `structure_core.candidates`,
    the same function the options replay shows in the agent's box (its docstring says what each row holds)."""
    return core.candidates(chain, max_loss_usd=max_loss_usd, today=today, venue=venue, limit=limit)


__all__ = ["TYPES", "DEBIT_TYPES", "CREDIT_TYPES", "BOUNDED", "TWO_EXPIRIES", "FEE_PER_CONTRACT", "Leg", "Spec", "Order",
           "classify", "parse", "held_limit", "natural_price", "instrument", "is_structure", "spec_of", "quote", "intrinsic",
           "max_gain", "fee_per_unit", "mleg_legs", "candidates"]
