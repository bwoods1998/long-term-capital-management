"""The standard-library core of level-3 structures: what `league/structures.py` means, over OCC codes.

Sept 25, 2026 (the options-desk run, builder S3). `league/structures.py` is the House's one
implementation of the structure spec, and it speaks `ltcm.broker.Instrument`; the options replay runs
inside the agent's sealed box with the standard library only (`league/sandbox.py` uploads its kit of
files beside `replay.py`), where neither `ltcm` nor `league` can be imported. So the rules live HERE,
over OCC strings and Decimals, and `structures.py` delegates every one of them to this module: which
types are admitted and why the rest are refused (`classify`), the canonical code of the held instrument
(`Spec.code`, `spec_of_code`), the natural-to-held limit (`held_limit`), the touch (`quote`), the value
at expiry (`intrinsic`), the fee (`fee_per_unit`), the venue's legs (`mleg_legs`) and the ready-made
candidates a strategy is shown (`candidates`). One implementation, so the replay and the House can never
disagree about what a structure is or what it costs; `league/tests/test_structure_parity.py` pins that
for every type and every refusal anyway.

The held price S a share = K + sum(ratio x long leg) - sum(ratio x short leg), K the collateral (zero
for a debit structure, the widest wing for a credit one): its cost is its maximum loss, an open buys it
and a close sells it (the module docstring of `structures.py` says why).

Money is Decimal and `money` refuses floats, as `ltcm.broker.money` does; the replay, whose estimates
are floats, converts with `dec`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Sequence

ZERO = Decimal(0)
CENT = Decimal("0.01")
HUNDRED = Decimal(100)
#: The assumed fee, a contract a leg a fill (Alpaca charges no options commission; the regulatory
#: pass-through is assumed, as `league/options_history.py` FEE_PER_CONTRACT_USD).
FEE_PER_CONTRACT = Decimal("0.05")

DEBIT_TYPES = ("debit_vertical", "long_butterfly", "calendar", "diagonal", "long_straddle", "long_strangle")
CREDIT_TYPES = ("credit_vertical", "iron_condor", "iron_butterfly")
TYPES = DEBIT_TYPES + CREDIT_TYPES
#: Types whose value a share never exceeds a known bound (the width, the wing or the collateral).
BOUNDED = ("debit_vertical", "long_butterfly", "credit_vertical", "iron_condor", "iron_butterfly")
#: Types with more than one expiry: no value at the near expiry without the far leg's market.
TWO_EXPIRIES = ("calendar", "diagonal")

OCC_PATTERN = r"[A-Z]{1,6}[0-9]{6}[CP][0-9]{8}"
_OCC = re.compile(rf"^{OCC_PATTERN}$")
CODE = re.compile(rf"^({'|'.join(TYPES)})((?:\|[+-][12]{OCC_PATTERN}){{2,4}})$")
_LEG = re.compile(rf"\|([+-])([12])({OCC_PATTERN})")


def money(value: Any) -> Decimal:
    """Parse a price or quantity strictly: finite, from str/int/Decimal, never float (as `ltcm.broker.money`)."""
    if isinstance(value, bool) or isinstance(value, float):
        raise ValueError(f"floats and bools are not money: {value!r}")
    try:
        result = Decimal(str(value)) if not isinstance(value, Decimal) else value
    except InvalidOperation as exc:
        raise ValueError(f"not a decimal: {value!r}") from exc
    if not result.is_finite():
        raise ValueError(f"not finite: {value!r}")
    return result


def dec(value: Any) -> Decimal:
    """A float estimate as a Decimal (its shortest repr), for the replay; anything else as `money`."""
    return Decimal(repr(value)) if isinstance(value, float) else money(value)


def occ_code(root: str, expiry: str, right: str, strike: Any) -> str:
    """The OCC 21-character symbol (as `ltcm.adapters.alpaca.alpaca_symbol` spells an option)."""
    day = str(expiry or "").replace("-", "")
    if len(day) != 8:
        raise ValueError(f"alpaca: option expiry {expiry!r} is not YYYY-MM-DD")
    thousandths = (money(strike) * 1000).quantize(Decimal(1))
    return f"{root.strip().upper()}{day[2:]}{'C' if str(right or '').lower() == 'call' else 'P'}{int(thousandths):08d}"


@dataclass(frozen=True)
class Leg:
    """One contract of a structure: `sign` +1 long, -1 short; `ratio` contracts a structure. The
    asset class, venue and multiplier are carried so a leg that is not an option contract of the
    structure's venue is refused with the same reason whoever built it."""

    occ: str
    sign: int
    ratio: int = 1
    root: str = ""
    expiry: str = ""
    right: str = ""
    strike: Decimal | None = None
    asset_class: str = "option"
    venue: str = ""
    multiplier: Decimal = HUNDRED

    @property
    def role(self) -> str:
        return "long" if self.sign > 0 else "short"


def leg(occ: str, sign: int, ratio: int = 1, *, venue: str = "") -> Leg:
    """A leg from its OCC code."""
    code = str(occ or "").strip().upper()
    if not _OCC.match(code):
        raise ValueError(f"not an OCC option symbol: {occ!r}")
    return Leg(code, sign, ratio, code[:-15], f"20{code[-15:-13]}-{code[-13:-11]}-{code[-11:-9]}",
               "call" if code[-9] == "C" else "put", Decimal(int(code[-8:])) / 1000, "option", venue, HUNDRED)


def _canonical(legs: Sequence[Leg]) -> tuple[Leg, ...]:
    return tuple(sorted(legs, key=lambda x: (x.expiry or "", x.right or "", x.strike if x.strike is not None else ZERO, x.sign)))


@dataclass(frozen=True)
class Spec:
    """A structure's type and legs, validated (`classify`): what it is, not how many or at what price."""

    type: str
    legs: tuple[Leg, ...]

    @property
    def underlying(self) -> str:
        return self.legs[0].root.upper()

    @property
    def expiry(self) -> str:
        """The EARLIEST expiry: the structure's clock."""
        return min(x.expiry for x in self.legs)

    @property
    def credit(self) -> bool:
        return self.type in CREDIT_TYPES

    @property
    def collateral(self) -> Decimal:
        """K a share: zero for a debit structure; the widest wing for a credit one."""
        if self.type == "credit_vertical":
            return abs(self.legs[0].strike - self.legs[1].strike)
        if self.type in ("iron_condor", "iron_butterfly"):
            puts = [x.strike for x in self.legs if x.right == "put"]
            calls = [x.strike for x in self.legs if x.right == "call"]
            return max(max(puts) - min(puts), max(calls) - min(calls))
        return ZERO

    @property
    def max_value(self) -> Decimal | None:
        """The most the held price S can be worth a share, where it is bounded."""
        if self.type == "debit_vertical":
            return abs(self.legs[0].strike - self.legs[1].strike)
        if self.type == "long_butterfly":
            strikes = sorted(x.strike for x in self.legs)
            return strikes[1] - strikes[0]
        if self.credit:
            return self.collateral
        return None

    @property
    def code(self) -> str:
        """The `market_id` of the held instrument: the type and every leg in canonical order."""
        return self.type + "".join(f"|{'+' if x.sign > 0 else '-'}{x.ratio}{x.occ}" for x in self.legs)

    @property
    def contracts(self) -> int:
        """Contracts a structure (a condor 4, a butterfly 4, a vertical 2)."""
        return sum(x.ratio for x in self.legs)

    def intent_legs(self) -> list[dict[str, Any]]:
        """The legs as an intent names them (to close what is held, for instance)."""
        return [{"occ": x.occ, "role": x.role, **({"ratio": x.ratio} if x.ratio != 1 else {})} for x in self.legs]


def classify(type_: str, legs: Sequence[Leg]) -> Spec:
    """The `Spec` of `legs` as a `type_`, or ValueError saying why it is not one (and never a structure
    whose loss is unbounded: every admitted type's loss is bounded by what it costs to hold)."""
    if type_ not in TYPES:
        raise ValueError(f"a structure is one of {', '.join(TYPES)}; {type_!r} is not admitted")
    legs = _canonical(legs)
    if not 2 <= len(legs) <= 4:
        raise ValueError("a structure has two to four legs")
    for x in legs:
        if x.asset_class != "option":
            raise ValueError("every leg of a structure is an option contract")
        if x.sign not in (1, -1):
            raise ValueError("a leg is long or short")
        if x.ratio not in (1, 2):
            raise ValueError("a leg's ratio is 1, or 2 for a long butterfly's body")
    if len({x.root.upper() for x in legs}) != 1 or len({x.venue for x in legs}) != 1:
        raise ValueError("every leg is on one underlying")
    if len({x.occ for x in legs}) != len(legs):
        raise ValueError("a contract appears twice")
    if len({x.multiplier for x in legs}) != 1:
        raise ValueError("every leg has the same multiplier")
    if any(x.ratio != 1 for x in legs) and type_ != "long_butterfly":
        raise ValueError(f"a {type_} is 1:1 on every leg: a ratio leaves a leg uncovered")
    longs = [x for x in legs if x.sign > 0]
    shorts = [x for x in legs if x.sign < 0]
    expiries = {x.expiry for x in legs}
    rights = {x.right for x in legs}

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
        puts = [x for x in legs if x.right == "put"]
        calls = [x for x in legs if x.right == "call"]
        need(len(puts) == 2 and len(calls) == 2, "two puts and two calls")
        lp = [x for x in puts if x.sign > 0]
        sp = [x for x in puts if x.sign < 0]
        sc = [x for x in calls if x.sign < 0]
        lc = [x for x in calls if x.sign > 0]
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
        return self.held_limit * self.spec.legs[0].multiplier * self.quantity if self.action == "open" else ZERO


def leg_from_row(row: Mapping[str, Any], *, venue: str = "") -> Leg:
    """An intent's leg `{occ | symbol [+ expiry, strike, right], role, ratio?}` as `league.venues.instrument_for`
    reads an Alpaca option (the OCC code, a chain row's `symbol`, or the four fields spelled out)."""
    role = str(row.get("role") or "").lower()
    if role not in ("long", "short"):
        raise ValueError("every leg has a role, long or short")
    ratio = row.get("ratio", 1)
    try:
        ratio = int(ratio)
    except (TypeError, ValueError) as exc:
        raise ValueError("a leg's ratio is a whole number") from exc
    sign = 1 if role == "long" else -1
    try:
        occ = str(row.get("occ") or "").strip().upper()
        if not occ and not (row.get("expiry") or row.get("strike")):
            named = str(row.get("symbol") or "").strip().upper()
            if re.fullmatch(OCC_PATTERN, named):
                occ = named
        if occ:
            return leg(occ, sign, ratio, venue=venue)
        symbol = str(row.get("symbol") or "").strip().upper()
        if not symbol:
            raise ValueError("an Alpaca instrument needs a symbol")
        if row.get("expiry") or row.get("strike"):
            right = str(row.get("right") or "").lower()
            if not (row.get("expiry") and row.get("strike") is not None and right in ("call", "put")):
                raise ValueError("options need expiry, strike and right")
            strike = money(row.get("strike"))
            return leg(occ_code(symbol, str(row.get("expiry")), right, strike), sign, ratio, venue=venue)
        return Leg(symbol, sign, ratio, symbol, "", "", None, "equity", venue, Decimal(1))
    except ValueError as exc:
        raise ValueError(f"a {role} leg: {exc}") from exc


def parse_fields(row: Mapping[str, Any]) -> tuple[str, str, list[Mapping[str, Any]]]:
    """The type, action and leg rows of a structure intent, with the checks that come before its legs."""
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
    if not isinstance(legs, (list, tuple)) or not all(isinstance(x, Mapping) for x in legs):
        raise ValueError("`legs` is a list of {occ, role}")
    return str(type_), action, list(legs)


def parse_rest(row: Mapping[str, Any]) -> tuple[Decimal, Decimal, str]:
    """The quantity, natural limit and reason of a structure intent, with the checks that come after its legs."""
    try:
        quantity = money(str(row.get("quantity", "")))
    except ValueError as exc:
        raise ValueError(f"quantity is a number: {exc}") from exc
    if quantity <= 0 or quantity % 1 != 0:
        raise ValueError("quantity is a whole number of structures, at least one")
    reason = row.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("every intent needs a reason")
    return quantity, money(str(row["limit_price"])), reason.strip()


def parse(row: Mapping[str, Any], *, venue: str = "") -> Order:
    """A strategy's structure intent (the spec's schema), validated; ValueError says what is wrong.
    The verticals schema `{"spread": "debit_vertical", "side": "buy"|"sell", ...}` is read as an alias."""
    type_, action, legs = parse_fields(row)
    spec = classify(type_, [leg_from_row(x, venue=venue) for x in legs])
    quantity, limit, reason = parse_rest(row)
    order = Order(spec, action, quantity, limit, reason)
    order.held_limit  # noqa: B018 - the limit's own checks, now
    return order


def is_code(code: Any) -> bool:
    return bool(CODE.match(str(code or "")))


def spec_of_code(code: str, *, venue: str = "") -> Spec:
    """The `Spec` a held instrument's code names (validated again: a reversed or tampered code can
    never be traded)."""
    found = CODE.match(str(code or ""))
    if not found:
        raise ValueError(f"not a structure held as one position: {code}")
    return classify(found.group(1), [leg(occ, 1 if sign == "+" else -1, int(ratio), venue=venue)
                                     for sign, ratio, occ in _LEG.findall(found.group(2))])


def quote(spec: Spec, touches: Mapping[str, tuple[Any, Any]]) -> tuple[Decimal | None, Decimal | None]:
    """The held instrument's touch (bid, ask) a share from each leg's (bid, ask), keyed by OCC code:
    what every leg trades at AT ONCE. bid = K + long bids - short asks (never under zero); ask = K +
    long asks - short bids. A side missing any leg's price is None."""
    bid: Decimal | None = spec.collateral
    ask: Decimal | None = spec.collateral
    for x in spec.legs:
        leg_bid, leg_ask = (touches.get(x.occ) or (None, None))[:2]
        leg_bid = None if leg_bid is None else money(leg_bid)
        leg_ask = None if leg_ask is None else money(leg_ask)
        if x.sign > 0:
            bid = None if bid is None or leg_bid is None else bid + x.ratio * leg_bid
            ask = None if ask is None or leg_ask is None else ask + x.ratio * leg_ask
        else:
            bid = None if bid is None or leg_ask is None else bid - x.ratio * leg_ask
            ask = None if ask is None or leg_bid is None else ask - x.ratio * leg_bid
    return (None if bid is None else max(ZERO, bid)), ask


def leg_intrinsic(x: Leg, spot: Decimal) -> Decimal:
    return max(ZERO, spot - x.strike) if x.right == "call" else max(ZERO, x.strike - spot)


def intrinsic(spec: Spec, spot: Any) -> Decimal:
    """The held price S a share at the (single) expiry with the underlying at `spot`."""
    if spec.type in TWO_EXPIRIES:
        raise ValueError(f"a {spec.type} has no value at its near expiry without the far leg's market: close it before")
    spot = money(spot)
    value = spec.collateral
    for x in spec.legs:
        value += x.sign * x.ratio * leg_intrinsic(x, spot)
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
    for x in spec.legs:
        buys = (x.sign > 0) == opening
        intent = ("buy_to_open" if x.sign > 0 else "sell_to_open") if opening else ("sell_to_close" if x.sign > 0 else "buy_to_close")
        rows.append({"symbol": x.occ, "ratio_qty": str(x.ratio), "side": "buy" if buys else "sell", "position_intent": intent})
    return rows


# ------------------------------------------------------------------------ what a strategy is shown
def _day_count(today: str, expiry: str) -> int:
    return (date.fromisoformat(expiry) - date.fromisoformat(today)).days


def candidates(chain: Sequence[Mapping[str, Any]], *, max_loss_usd: Any, today: str, venue: str = "alpaca-paper",
               limit: int = 60) -> list[dict[str, Any]]:
    """Ready-made structures a strategy may send as they are (`ctx["structures"]`), built from the
    chain rows it is shown, the same function live (`House._chain`) and in the options replay so a
    strategy sees one context in both: adjacent-strike DEBIT verticals (the long leg the dearer), OUT OF
    THE MONEY adjacent-strike CREDIT verticals (the short leg the dearer), and iron condors pairing an
    out-of-the-money put credit vertical with a call credit vertical of the same width and the nearest
    short delta. Only those whose maximum loss x 100 is within `max_loss_usd` (the agent's order and
    position caps, the smaller) and whose touches make a positive debit under the width or a positive
    credit under the collateral.

    Each row: `structure`, `kind` (debit or credit), `legs` (as an intent names them), `width`,
    `net_ask`/`net_bid` in the trader's sense (a debit structure: the debit to open at the touches /
    what closing gets; a credit structure: `net_bid` the credit taken opening at the touches, `net_ask`
    what buying it back costs), `open_limit` (the natural limit that opens it at the touches),
    `max_loss_usd` and `max_gain_usd` a structure at that limit, `days_to_expiry`, `underlying`,
    `underlying_price`, and `long_delta` or `short_delta` where the feed gives deltas. Nearest the
    money first, at most `limit` rows."""
    cap = money(max_loss_usd)
    groups: dict[tuple[str, str, str], list[Mapping[str, Any]]] = {}
    spots: dict[str, float] = {}
    for row in chain:
        try:
            if row.get("bid") is None or row.get("ask") is None or float(row["ask"]) <= 0:
                continue
            under = str(row.get("underlying") or "").upper()
            groups.setdefault((under, str(row["expiry"]), str(row["right"])), []).append(row)
            if row.get("underlying_price"):
                spots[under] = float(row["underlying_price"])
        except (KeyError, TypeError, ValueError):
            continue
    out: list[tuple[float, dict[str, Any]]] = []
    credits: dict[tuple[str, str], dict[str, list[dict[str, Any]]]] = {}

    def code(row: Mapping[str, Any]) -> str:
        return str(row.get("occ") or row.get("symbol"))

    def delta(row: Mapping[str, Any]) -> float | None:
        value = row.get("delta")
        return None if value is None else float(value)

    for (under, expiry, right), rows in groups.items():
        rows = sorted(rows, key=lambda r: float(r["strike"]))
        spot = spots.get(under)
        dte = _day_count(today, expiry)
        for low, high in zip(rows, rows[1:]):
            width = money(str(high["strike"])) - money(str(low["strike"]))
            if width <= 0:
                continue
            dearer, cheaper = (low, high) if right == "call" else (high, low)
            # the debit vertical: long the dearer at its ask, short the cheaper at its bid
            debit = money(str(dearer["ask"])) - money(str(cheaper["bid"]))
            value = max(ZERO, money(str(dearer["bid"])) - money(str(cheaper["ask"])))
            if ZERO < debit < width and debit * HUNDRED <= cap:
                row = {"structure": "debit_vertical", "kind": "debit",
                       "legs": [{"occ": code(dearer), "role": "long"}, {"occ": code(cheaper), "role": "short"}],
                       "width": float(width), "net_ask": float(debit), "net_bid": float(value), "open_limit": float(debit),
                       "max_loss_usd": float(debit * HUNDRED), "max_gain_usd": float((width - debit) * HUNDRED),
                       "days_to_expiry": dte, "underlying": under, "underlying_price": spot, "long_delta": delta(dearer)}
                out.append((abs(float(dearer["strike"]) - spot) if spot else 0.0, row))
            # the credit vertical: short the dearer at its bid, long the cheaper at its ask; out of the money only
            out_of_money = spot is None or (float(dearer["strike"]) >= spot if right == "call" else float(dearer["strike"]) <= spot)
            credit = money(str(dearer["bid"])) - money(str(cheaper["ask"]))
            buy_back = money(str(dearer["ask"])) - money(str(cheaper["bid"]))
            if out_of_money and ZERO < credit < width and (width - credit) * HUNDRED <= cap:
                row = {"structure": "credit_vertical", "kind": "credit",
                       "legs": [{"occ": code(dearer), "role": "short"}, {"occ": code(cheaper), "role": "long"}],
                       "width": float(width), "net_bid": float(credit), "net_ask": float(max(ZERO, buy_back)), "open_limit": float(credit),
                       "max_loss_usd": float((width - credit) * HUNDRED), "max_gain_usd": float(credit * HUNDRED),
                       "days_to_expiry": dte, "underlying": under, "underlying_price": spot, "short_delta": delta(dearer)}
                out.append((abs(float(dearer["strike"]) - spot) if spot else 0.0, row))
                credits.setdefault((under, expiry), {}).setdefault(right, []).append(
                    {"row": row, "credit": credit, "buy_back": max(ZERO, buy_back), "width": width, "short": float(dearer["strike"]), "delta": delta(dearer)})
    for (under, expiry), sides in credits.items():
        puts, calls = sides.get("put") or [], sides.get("call") or []
        for put in puts:
            same = [c for c in calls if c["width"] == put["width"] and c["short"] > put["short"]]
            if not same:
                continue
            if put["delta"] is not None and all(c["delta"] is not None for c in same):
                call = min(same, key=lambda c: abs(abs(c["delta"]) - abs(put["delta"])))
            else:
                spot = spots.get(under) or 0.0
                call = min(same, key=lambda c: abs((c["short"] - spot) - (spot - put["short"])))
            credit = put["credit"] + call["credit"]
            width = put["width"]
            if not ZERO < credit < width or (width - credit) * HUNDRED > cap:
                continue
            row = {"structure": "iron_condor", "kind": "credit", "legs": put["row"]["legs"] + call["row"]["legs"],
                   "width": float(width), "net_bid": float(credit), "net_ask": float(put["buy_back"] + call["buy_back"]), "open_limit": float(credit),
                   "max_loss_usd": float((width - credit) * HUNDRED), "max_gain_usd": float(credit * HUNDRED),
                   "days_to_expiry": put["row"]["days_to_expiry"], "underlying": under, "underlying_price": spots.get(under),
                   "short_delta": put["delta"], "call_short_delta": call["delta"]}
            spot = spots.get(under)
            out.append((abs((put["short"] + call["short"]) / 2 - spot) if spot else 0.0, row))
    out.sort(key=lambda pair: (pair[1]["days_to_expiry"], pair[0]))
    return [row for _, row in out[: max(0, int(limit))]]


__all__ = ["TYPES", "DEBIT_TYPES", "CREDIT_TYPES", "BOUNDED", "TWO_EXPIRIES", "FEE_PER_CONTRACT", "CODE", "OCC_PATTERN", "Leg",
           "Spec", "Order", "money", "dec", "occ_code", "leg", "leg_from_row", "classify", "parse", "parse_fields", "parse_rest",
           "held_limit", "natural_price", "is_code", "spec_of_code", "quote", "leg_intrinsic", "intrinsic", "max_gain",
           "fee_per_unit", "mleg_legs", "candidates"]
