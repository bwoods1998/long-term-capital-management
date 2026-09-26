"""Resolving a program's intent into concrete legs, a limit, a quantity and a maximum loss.

One implementation for the replay and the live path (the House calls these on its live `Snapshot`):

    order = resolve_open(intent, snap, rules, buying_power=bp)            # an "open" intent
    order = resolve_close(intent, legs, qty, snap, rules)                  # a "close" of a held position
    value, cap = natural_value(snap, legs, "open")                         # what it costs at the touch now

A structure's VALUE a share is the sum over its legs of side x ratio x price (long +1, short -1): a
debit structure is worth a positive value, a credit structure a negative one. An open PAYS its value
(a negative value is a credit received); a close RECEIVES its value (a negative value is paid). So
one signed number is every limit, entry, mark and exit, and the P&L of a trade is always
(exit value - entry value) x 100 x quantity, less fees.

The natural price of an open buys every long leg at its ask and sells every short leg at its bid;
of a close, the reverse. Limit rules: "natural"; "mid"; {"mid": k} (k ticks from the mid toward the
natural, never past it); {"price": v} (an explicit value). Multi-leg values trade in $0.01; a single
long call or put in its contract's tick (`venue.leg_tick`). A limit off the tick is rounded to the
passive side (less paid on an open, more asked on a close).

The type of a multi-leg structure is validated by `league/structure_core.classify`, the House's own
definition, so a structure the Gym admits is one the House would; a long call or put is one long
leg. Calendars and diagonals are refused on index roots. Maximum loss a share: a debit structure's
value; a credit structure's collateral (its widest wing) less the credit. Quantity is `qty`, or the
most whole structures whose maximum loss plus fees fits `max_loss` dollars. Buying power reserves
(maximum loss + open and close fees) x (1 + 10%).

numpy only (plus the standard-library `structure_core`); Python 3.11+.
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

import numpy as np

from .. import structure_core as core
from . import venue
from .ctx import Snapshot

DEBIT = ("long_call", "long_put", "debit_vertical", "long_butterfly", "long_straddle", "long_strangle", "calendar", "diagonal")
CREDIT = ("credit_vertical", "iron_condor", "iron_butterfly")
SELECTORS = ("id", "strike", "delta", "moneyness", "atm", "rel")
_BASE = dt.date(2000, 1, 3)  # the expiry a leg's days-to-expiry is written against for the House's classifier
MAX_QTY = 500


class Refused(ValueError):
    """An intent cannot become an order (the message says why, in a program's terms)."""


@dataclass(frozen=True)
class LegFill:
    """One resolved leg: the contract's index in the snapshot, its identity, side and ratio."""

    idx: int
    key: int
    side: int      # +1 long, -1 short
    ratio: int
    dte: int
    strike: float
    is_call: bool

    def row(self, idx: int | None = None) -> dict:
        return {"id": int(self.idx if idx is None else idx), "dte": int(self.dte), "strike": float(self.strike),
                "is_call": bool(self.is_call), "side": "long" if self.side > 0 else "short", "ratio": int(self.ratio)}


@dataclass
class Order:
    """A resolved intent: what the engine (or the House) works."""

    action: str                 # "open" or "close"
    type: str
    root: str
    legs: tuple[LegFill, ...]
    qty: int
    limit: float                # the value a share (see the module docstring)
    natural: float              # the natural value at the decision
    mid: float                  # the mid value at the decision
    max_loss_share: float       # at the limit (an open), dollars a share
    collateral: float           # a credit structure's widest wing (0 for a debit one)
    fees: float                 # the estimated fee of this order's fills
    reserve: float              # buying power held while it works (an open)
    tif: int | None             # minutes to work; None = the day; 0 = immediate or cancel
    tag: str = ""
    note: str = ""
    position: int | None = None  # the position a close closes
    extra: dict = field(default_factory=dict)

    @property
    def credit(self) -> bool:
        return self.type in CREDIT

    @property
    def max_loss(self) -> float:
        return self.max_loss_share * venue.MULTIPLIER * self.qty


# --------------------------------------------------------------------------- prices
def natural_value(snap: Snapshot, legs: Sequence[LegFill], action: str, *, stress: float = 1.0) -> tuple[float, int]:
    """(the natural value a share, the most structures the quoted sizes fill) of opening or closing
    `legs` at this snapshot; (nan, 0) when a leg has no quote. `stress` widens every half-spread."""
    value = 0.0
    cap = 1 << 30
    for leg in legs:
        bid, ask = float(snap.bid[leg.idx]), float(snap.ask[leg.idx])
        if not (math.isfinite(bid) and math.isfinite(ask)):
            return math.nan, 0
        if stress != 1.0:
            mid, half = 0.5 * (bid + ask), 0.5 * (ask - bid) * stress
            bid, ask = max(0.0, mid - half), mid + half
        buying = (leg.side > 0) == (action == "open")
        price = ask if buying else bid
        size = int(snap.ask_size[leg.idx] if buying else snap.bid_size[leg.idx])
        value += leg.side * leg.ratio * price
        cap = min(cap, size // leg.ratio)
    return value, max(0, cap)


def mid_value(snap: Snapshot, legs: Sequence[LegFill]) -> float:
    value = 0.0
    for leg in legs:
        m = float(snap.mid[leg.idx])
        if not math.isfinite(m):
            return math.nan
        value += leg.side * leg.ratio * m
    return value


def tick_of(root: str, legs: Sequence[LegFill], value: float) -> float:
    return venue.leg_tick(root, abs(value)) if len(legs) == 1 else venue.NET_TICK


def limit_value(rule: Any, action: str, natural: float, mid: float, tick: float) -> float:
    """The limit a share for a limit rule (the module docstring), on the tick, rounded passively."""
    opening = action == "open"
    if rule is None or rule == "natural":
        return natural
    if rule == "mid":
        target = mid
    elif isinstance(rule, Mapping) and set(rule) == {"mid"}:
        k = float(rule["mid"])
        if not math.isfinite(k) or k < 0 or k > 100:
            raise Refused("limit {'mid': k} takes 0 <= k <= 100 ticks")
        target = mid + k * tick if opening else mid - k * tick
        target = min(target, natural) if opening else max(target, natural)
    elif isinstance(rule, Mapping) and set(rule) == {"price"}:
        target = float(rule["price"])
        if not math.isfinite(target):
            raise Refused("limit {'price': v} needs a number")
    else:
        raise Refused("limit is 'natural', 'mid', {'mid': k} or {'price': value}")
    rounded = venue.round_price(target, tick, up=not opening)
    return rounded


def _tif(raw: Any) -> int | None:
    if raw is None or raw == "day":
        return None
    if raw == "ioc":
        return 0
    if isinstance(raw, (int, float)) and not isinstance(raw, bool) and 0 <= raw <= 400:
        return int(raw)
    raise Refused("tif is 'day', 'ioc' or a number of minutes (0-400)")


# --------------------------------------------------------------------------- choosing contracts
def _expiry(snap: Snapshot, pool: np.ndarray, want: Any) -> int:
    if isinstance(want, bool) or not isinstance(want, (int, float)) or want < 0:
        raise Refused("a leg's 'dte' is a number of days to expiry, 0 or more")
    listed = np.unique(snap.dte[pool])
    later = listed[listed >= int(want)]
    if later.size == 0:
        raise Refused(f"no quoted expiry at or after {int(want)} days")
    return int(later[0])


def _pick(snap: Snapshot, spec: Mapping[str, Any], chosen: list[LegFill | None], rules: venue.Rules) -> LegFill:
    side = {"long": 1, "short": -1}.get(str(spec.get("side", "")).lower())
    if side is None:
        raise Refused("every leg has 'side': 'long' or 'short'")
    ratio = spec.get("ratio", 1)
    if isinstance(ratio, bool) or not isinstance(ratio, (int, float)) or int(ratio) != ratio or ratio not in (1, 2):
        raise Refused("a leg's 'ratio' is 1, or 2 for a long butterfly's body")
    ratio = int(ratio)
    present = [s for s in SELECTORS if s in spec]
    if len(present) != 1:
        raise Refused(f"a leg names exactly one of {', '.join(SELECTORS)}")
    how = present[0]
    if how == "id":
        i = spec["id"]
        if isinstance(i, bool) or not isinstance(i, (int, float)) or int(i) != i or not 0 <= int(i) < snap.n:
            raise Refused("a leg's 'id' is one of ctx.chain.id")
        i = int(i)
        if not snap.valid[i]:
            raise Refused(f"contract {i} has no two-sided quote now")
        if "right" in spec and _is_call(spec["right"]) != bool(snap.is_call[i]):
            raise Refused(f"contract {i} is not a {'call' if _is_call(spec['right']) else 'put'}")
        return LegFill(i, int(snap.keys[i]), side, ratio, int(snap.dte[i]), float(snap.strike[i]), bool(snap.is_call[i]))
    if "right" not in spec:
        raise Refused("a leg names its 'right', 'C' or 'P'")
    call = _is_call(spec["right"])
    base = snap.valid & (snap.is_call == call)
    if how == "rel":
        j = spec["rel"]
        if isinstance(j, bool) or not isinstance(j, int) or not 0 <= j < len(chosen) or chosen[j] is None:
            raise Refused("'rel' names an earlier-resolved leg by its position in 'legs' (a leg with an absolute selector)")
        ref = chosen[j]
        offset = spec.get("offset", 0.0)
        if isinstance(offset, bool) or not isinstance(offset, (int, float)) or not math.isfinite(offset):
            raise Refused("'offset' is dollars from the referenced leg's strike")
        dte = _expiry(snap, np.flatnonzero(base), spec["dte"]) if "dte" in spec else ref.dte
        pool = np.flatnonzero(base & (snap.dte == dte))
        if pool.size == 0:
            raise Refused(f"no quoted {'call' if call else 'put'} at {dte} days")
        target = ref.strike + float(offset)
        i = int(pool[np.argmin(np.abs(snap.strike[pool] - target))])
        return LegFill(i, int(snap.keys[i]), side, ratio, int(snap.dte[i]), float(snap.strike[i]), call)
    if "dte" not in spec:
        raise Refused("a leg names its 'dte' (days to expiry; the nearest quoted expiry at or after it is used)")
    dte = _expiry(snap, np.flatnonzero(base), spec["dte"])
    pool = np.flatnonzero(base & (snap.dte == dte))
    if pool.size == 0:
        raise Refused(f"no quoted {'call' if call else 'put'} at {dte} days")
    strikes = snap.strike[pool]
    value = spec[how]
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise Refused(f"'{how}' takes a number")
    if how == "strike":
        i = int(pool[np.argmin(np.abs(strikes - float(value)))])
    elif how == "moneyness":
        if not math.isfinite(snap.spot):
            raise Refused("no underlying price now")
        i = int(pool[np.argmin(np.abs(strikes - snap.spot * (1.0 + float(value))))])
    elif how == "atm":
        if not math.isfinite(snap.spot):
            raise Refused("no underlying price now")
        order = np.argsort(strikes, kind="stable")
        ranked = strikes[order]
        at = int(np.argmin(np.abs(ranked - snap.spot)))
        k = at + int(value)
        if int(value) != value or not 0 <= k < ranked.size:
            raise Refused(f"'atm': {value} steps from the money leaves the quoted strikes")
        i = int(pool[order[k]])
    else:  # delta
        _, deltas, _, _, _ = snap.greeks_for(pool)
        ok = np.isfinite(deltas)
        if not ok.any():
            raise Refused("no delta is known for that expiry now")
        dist = np.where(ok, np.abs(np.abs(deltas) - abs(float(value))), np.inf)
        i = int(pool[np.argmin(dist)])
    return LegFill(i, int(snap.keys[i]), side, ratio, int(snap.dte[i]), float(snap.strike[i]), call)


def _is_call(right: Any) -> bool:
    text = str(right).strip().upper()
    if text in ("C", "CALL"):
        return True
    if text in ("P", "PUT"):
        return False
    raise Refused("a leg's 'right' is 'C' or 'P'")


def resolve_legs(snap: Snapshot, specs: Any, rules: venue.Rules) -> list[LegFill]:
    """The contracts an intent's `legs` name, absolute selectors first, then the `rel` ones."""
    if not isinstance(specs, (list, tuple)) or not 1 <= len(specs) <= rules.max_legs:
        raise Refused(f"'legs' is a list of 1 to {rules.max_legs} legs")
    chosen: list[LegFill | None] = [None] * len(specs)
    for pass_rel in (False, True):
        for i, spec in enumerate(specs):
            if not isinstance(spec, Mapping):
                raise Refused("each leg is a dict")
            if ("rel" in spec) == pass_rel:
                chosen[i] = _pick(snap, spec, chosen, rules)
    return [c for c in chosen if c is not None]


# --------------------------------------------------------------------------- structure rules
def classify(type_: str, root: str, legs: Sequence[LegFill], rules: venue.Rules) -> float:
    """Validate the structure (the House's own classifier for multi-leg types); return its collateral a share."""
    if type_ not in venue.STRUCTURE_TYPES:
        raise Refused(f"'open' is one of {', '.join(venue.STRUCTURE_TYPES)}")
    if type_ in ("calendar", "diagonal") and not rules.calendars:
        raise Refused(f"{root} options are index options: every leg has one expiry (no calendars or diagonals)")
    if type_ in ("long_call", "long_put"):
        if len(legs) != 1 or legs[0].side != 1 or legs[0].ratio != 1:
            raise Refused(f"a {type_} is one long leg")
        if legs[0].is_call != (type_ == "long_call"):
            raise Refused(f"a {type_}'s leg is a {'call' if type_ == 'long_call' else 'put'}")
        return 0.0
    occ_root = "".join(ch for ch in root.upper() if ch.isalpha())[:6] or "X"
    try:
        spec = core.classify(type_, [
            core.leg(core.occ_code(occ_root, (_BASE + dt.timedelta(days=int(x.dte))).isoformat(), "call" if x.is_call else "put",
                                   core.money(f"{x.strike:.3f}")), x.side, x.ratio)
            for x in legs])
    except ValueError as exc:
        raise Refused(str(exc)) from None
    return float(spec.collateral)


def max_loss_share(type_: str, value: float, collateral: float) -> float:
    """What one structure opened at `value` can lose, a share (Refused when it could never pay)."""
    if type_ in CREDIT:
        if not value < 0:
            raise Refused(f"credit structure: a {type_} opens for a credit (a negative value); {value:.2f} is not one")
        loss = collateral + value
        if loss <= 0:
            raise Refused(f"credit structure: a credit of {-value:.2f} on {collateral:.2f} of collateral is not defined risk")
        return loss
    if not value > 0:
        raise Refused(f"debit structure: a {type_} opens for a debit (a positive value); {value:.2f} is not one")
    return value


def order_fees(root: str, legs: Sequence[LegFill], snap_prices: Sequence[float], qty: int, action: str) -> float:
    """The fees of filling `qty` structures: each leg's contracts at its price, buys and sells as the action makes them."""
    total = 0.0
    for leg, price in zip(legs, snap_prices):
        selling = (leg.side > 0) != (action == "open")
        total += venue.leg_fee(root, leg.ratio * qty, price, sell=selling)
    return round(total, 2)


def _leg_prices(snap: Snapshot, legs: Sequence[LegFill], action: str) -> list[float]:
    out = []
    for leg in legs:
        buying = (leg.side > 0) == (action == "open")
        out.append(float(snap.ask[leg.idx] if buying else snap.bid[leg.idx]))
    return out


# --------------------------------------------------------------------------- orders
def resolve_open(intent: Mapping[str, Any], snap: Snapshot, rules: venue.Rules, *, buying_power: float) -> Order:
    """An "open" intent as an order (Refused says why not). `snap` is the intent's root at the decision minute."""
    type_ = str(intent.get("open") or "")
    root = snap.root
    if str(intent.get("root", root)).upper() != root:
        raise Refused(f"the intent's root {intent.get('root')!r} is not {root}")
    legs = resolve_legs(snap, intent.get("legs"), rules)
    collateral = classify(type_, root, legs, rules)
    natural, _ = natural_value(snap, legs, "open")
    mid = mid_value(snap, legs)
    if not (math.isfinite(natural) and math.isfinite(mid)):
        raise Refused("a leg has no quote now")
    limit = limit_value(intent.get("limit", "natural"), "open", natural, mid, tick_of(root, legs, natural))
    loss = max_loss_share(type_, limit, collateral)
    prices = _leg_prices(snap, legs, "open")
    unit_fees = order_fees(root, legs, prices, 1, "open") * 2.0  # open and close, a structure
    if "qty" in intent and "max_loss" in intent:
        raise Refused("an open names 'qty' or 'max_loss', not both")
    if "qty" in intent:
        q = intent["qty"]
        if isinstance(q, bool) or not isinstance(q, (int, float)) or int(q) != q or not 1 <= q <= MAX_QTY:
            raise Refused(f"'qty' is a whole number from 1 to {MAX_QTY}")
        qty = int(q)
    elif "max_loss" in intent:
        budget = intent["max_loss"]
        if isinstance(budget, bool) or not isinstance(budget, (int, float)) or not budget > 0:
            raise Refused("'max_loss' is dollars, more than zero")
        qty = min(MAX_QTY, int(float(budget) // (loss * venue.MULTIPLIER + unit_fees)))
        if qty < 1:
            raise Refused(f"one structure risks {loss * venue.MULTIPLIER + unit_fees:.2f} with fees; max_loss {float(budget):.2f} buys none")
    else:
        raise Refused("an open names 'qty' or 'max_loss'")
    fees = order_fees(root, legs, prices, qty, "open")
    reserve = (loss * venue.MULTIPLIER * qty + 2.0 * fees) * (1.0 + rules.bp_buffer)
    if reserve > buying_power + 1e-9:
        raise Refused(f"buying power: it reserves {reserve:.2f} (max loss + fees + {rules.bp_buffer:.0%}); {max(0.0, buying_power):.2f} is free")
    return Order("open", type_, root, tuple(legs), qty, limit, natural, mid, loss, collateral, fees, reserve,
                 _tif(intent.get("tif")), str(intent.get("tag") or "")[:80], str(intent.get("note") or "")[:300])


def resolve_close(intent: Mapping[str, Any], type_: str, legs: Sequence[LegFill], held_qty: int, snap: Snapshot,
                  rules: venue.Rules, *, position: int) -> Order:
    """A "close" intent for a held position whose `legs` carry today's snapshot indices."""
    if any(leg.idx < 0 for leg in legs):
        raise Refused("a leg of this position is not in today's chain (no quote to close against)")
    qty = intent.get("qty", held_qty)
    if isinstance(qty, bool) or not isinstance(qty, (int, float)) or int(qty) != qty or not 1 <= qty <= held_qty:
        raise Refused(f"'qty' closes 1 to {held_qty} of this position")
    natural, _ = natural_value(snap, legs, "close")
    mid = mid_value(snap, legs)
    if not (math.isfinite(natural) and math.isfinite(mid)):
        raise Refused("a leg has no quote now")
    limit = limit_value(intent.get("limit", "natural"), "close", natural, mid, tick_of(snap.root, legs, natural))
    fees = order_fees(snap.root, legs, _leg_prices(snap, legs, "close"), int(qty), "close")
    return Order("close", type_, snap.root, tuple(legs), int(qty), limit, natural, mid, 0.0, 0.0, fees, 0.0,
                 _tif(intent.get("tif")), str(intent.get("tag") or "")[:80], str(intent.get("note") or "")[:300],
                 position=int(position))


__all__ = ["Order", "LegFill", "Refused", "resolve_open", "resolve_close", "resolve_legs", "natural_value", "mid_value",
           "limit_value", "classify", "max_loss_share", "order_fees", "tick_of", "DEBIT", "CREDIT"]
