"""Deterministic pre-trade risk rules and circuit breakers.

No model is consulted here. Every rule is a pure function of the intent and a `RiskContext`
snapshot assembled by the service. A rule returns a reason string to reject or `None` to pass.
All rules run so the decision lists every violated rule, which is what the public sees.

Rules are ordered from cheapest and most absolute (kill switch) to most data-dependent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Callable

from .broker import OrderIntent, Position, Quote, money
from .manifest import DeskManifest

Rule = Callable[[OrderIntent, "RiskContext"], "str | None"]

ZERO = Decimal(0)


@dataclass
class RiskContext:
    manifest: DeskManifest
    desk_equity: Decimal
    desk_cash: Decimal
    positions: dict[str, Position]  # keyed by Instrument.key
    quote: Quote | None
    now: str  # ISO timestamp
    desk_daily_pnl: Decimal = ZERO  # realized + unrealized since the last daily mark
    desk_orders_today: int = 0
    floor_equity: Decimal = ZERO
    floor_daily_pnl: Decimal = ZERO
    floor_max_daily_loss_pct: Decimal = Decimal("0.08")
    kill_switch: bool = False
    market_open: bool | None = None  # None when unknown (crypto, events)
    adv_usd: Decimal | None = None  # average daily dollar volume when known
    open_orders: int = 0
    venue_capabilities: set[str] = field(default_factory=set)

    def __post_init__(self):
        for name in ("desk_equity", "desk_cash", "desk_daily_pnl", "floor_equity", "floor_daily_pnl"):
            setattr(self, name, money(getattr(self, name)))


@dataclass(frozen=True)
class Decision:
    intent_id: str
    desk_id: str
    approved: bool
    reasons: tuple[str, ...]
    reference_price: Decimal | None
    notional: Decimal | None
    checked_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent_id": self.intent_id,
            "desk_id": self.desk_id,
            "approved": self.approved,
            "reasons": list(self.reasons),
            "reference_price": None if self.reference_price is None else format(self.reference_price, "f"),
            "notional": None if self.notional is None else format(self.notional, "f"),
            "checked_at": self.checked_at,
        }


# ------------------------------------------------------------------ helpers

def reference_price(intent: OrderIntent, ctx: RiskContext) -> Decimal | None:
    if ctx.quote is not None:
        price = ctx.quote.reference(intent.side)
        if price is not None and price > 0:
            return price
    if intent.limit_price is not None:
        return intent.limit_price
    return None


def notional_of(intent: OrderIntent, ctx: RiskContext) -> Decimal | None:
    """The cash the order can commit. A limit buy never pays above its limit, so a bid resting
    under the ask is sized at the bid, not at the ask it does not cross (a $10 resting quote
    read as $18 against the ask on Sept 16, 2026); a limit sell never gives below its limit."""
    price = reference_price(intent, ctx)
    if price is None:
        return None
    if intent.order_type == "limit" and intent.limit_price is not None and intent.limit_price > 0:
        price = min(price, intent.limit_price) if intent.side == "buy" else max(price, intent.limit_price)
    return intent.quantity * price * intent.instrument.multiplier


def signed_quantity(intent: OrderIntent) -> Decimal:
    return intent.quantity if intent.side == "buy" else -intent.quantity


def gross_exposure(positions: dict[str, Position]) -> Decimal:
    total = ZERO
    for position in positions.values():
        value = position.market_value
        if value is None:
            value = position.cost_basis
        total += abs(value)
    return total


# -------------------------------------------------------------------- rules

def rule_kill_switch(intent: OrderIntent, ctx: RiskContext) -> str | None:
    return "kill switch engaged" if ctx.kill_switch else None


def rule_venue(intent: OrderIntent, ctx: RiskContext) -> str | None:
    # An intent always names the real venue, whether the desk is live or shadow: where the order
    # actually goes is the gateway's decision, made from the desk's capital mode, not the model's.
    if intent.instrument.venue not in ctx.manifest.venues:
        return f"venue {intent.instrument.venue} not permitted for desk"
    if ctx.venue_capabilities and intent.instrument.asset_class not in ctx.venue_capabilities:
        return f"venue does not support {intent.instrument.asset_class}"
    return None


def rule_instrument(intent: OrderIntent, ctx: RiskContext) -> str | None:
    rules = ctx.manifest.instruments
    if intent.instrument.asset_class not in rules.asset_classes:
        return f"asset class {intent.instrument.asset_class} not in mandate"
    if not rules.permits_symbol(intent.instrument.symbol):
        return f"symbol {intent.instrument.symbol} not permitted by mandate"
    return None


def rule_quantity(intent: OrderIntent, ctx: RiskContext) -> str | None:
    if intent.quantity <= 0:
        return "quantity must be positive"
    fractional = intent.quantity != intent.quantity.to_integral_value()
    if fractional and intent.instrument.asset_class in ("equity", "option", "future", "event"):
        if "fractional" not in ctx.venue_capabilities or intent.instrument.asset_class != "equity":
            return "fractional quantity not permitted for this instrument"
    return None


def rule_short(intent: OrderIntent, ctx: RiskContext) -> str | None:
    if intent.side != "sell":
        return None
    held = ctx.positions.get(intent.instrument.key)
    held_qty = held.quantity if held else ZERO
    if held_qty - intent.quantity < 0:
        if not ctx.manifest.instruments.allow_short:
            return f"sell exceeds position and shorting is not permitted ({_held_on_market(intent, ctx, held_qty)})"
        if "short" not in ctx.venue_capabilities:
            return "venue does not support short sales"
    return None


def _held_on_market(intent: OrderIntent, ctx: RiskContext, held_qty: Decimal) -> str:
    """What the desk holds on the market it tried to sell, in words it can act on."""
    names = {str(n).upper() for n in (intent.instrument.symbol, intent.instrument.market_id) if n}
    legs = []
    for position in ctx.positions.values():
        other = position.instrument
        if position.quantity == 0 or other.venue != intent.instrument.venue:
            continue
        if names & {str(n).upper() for n in (other.symbol, other.market_id) if n}:
            leg = f" {other.right.upper()}" if other.right else ""
            legs.append(f"{format(position.quantity.normalize(), 'f')}{leg}")
    if not legs:
        return f"you hold {format(held_qty.normalize(), 'f')} of this contract and nothing else on this market"
    return f"you hold {', '.join(legs)} on this market; sell at most that on the same leg"


def rule_price_known(intent: OrderIntent, ctx: RiskContext) -> str | None:
    if ctx.manifest.live and ctx.quote is None:
        return "no quote available for a live order"
    if reference_price(intent, ctx) is None:
        return "no reference price"
    return None


def rule_min_price(intent: OrderIntent, ctx: RiskContext) -> str | None:
    if intent.instrument.asset_class not in ("equity",):
        return None
    price = reference_price(intent, ctx)
    if price is not None and price < ctx.manifest.instruments.min_price:
        return f"price {price} below mandate minimum {ctx.manifest.instruments.min_price}"
    return None


def rule_liquidity(intent: OrderIntent, ctx: RiskContext) -> str | None:
    if ctx.adv_usd is None or intent.instrument.asset_class != "equity":
        return None
    if ctx.adv_usd < ctx.manifest.instruments.min_adv_usd:
        return f"average daily volume {ctx.adv_usd} below mandate minimum"
    notional = notional_of(intent, ctx)
    if notional is not None and ctx.adv_usd > 0 and notional > ctx.adv_usd * Decimal("0.01"):
        return "order exceeds 1% of average daily dollar volume"
    return None


#: An event contract pays one dollar. A limit this far through the touch is a typo, not a bid.
EVENT_LIMIT_TOLERANCE = Decimal("0.05")


def rule_limit_sanity(intent: OrderIntent, ctx: RiskContext) -> str | None:
    if intent.order_type != "limit" or ctx.quote is None:
        return None
    reference = ctx.quote.reference(intent.side)
    if reference is None or reference <= 0:
        return None
    if intent.instrument.asset_class == "event":
        # Prices live in cents on a dollar, so a percentage of a four-cent ask means nothing (a
        # seven-cent bid against it read as "75% away" and was refused). A buy at or under the
        # ask, or a sell at or over the bid, is a resting order and always sane; through the
        # touch by more than a few cents is a mistake.
        through = (intent.limit_price - reference) if intent.side == "buy" else (reference - intent.limit_price)
        if through > EVENT_LIMIT_TOLERANCE:
            touch = "ask" if intent.side == "buy" else "bid"
            return f"limit price is {through:.2f} through the {touch} of {reference:.2f}"
        return None
    deviation = abs(intent.limit_price - reference) / reference
    if deviation > ctx.manifest.limits.max_limit_deviation_pct:
        return f"limit price deviates {deviation:.2%} from reference"
    return None


def reduces_exposure(intent: OrderIntent, ctx: RiskContext) -> bool:
    held = ctx.positions.get(intent.instrument.key)
    held_qty = held.quantity if held else ZERO
    after = held_qty + signed_quantity(intent)
    return abs(after) <= abs(held_qty)


def rule_exit_plan(intent: OrderIntent, ctx: RiskContext) -> str | None:
    """A stop sits on the losing side of the entry and a target on the winning side.

    leap: exits. The entry price is the limit when there is one, else the quote's reference
    for the side. With neither there is nothing to compare against and the plan stands as
    written; a plan naming neither a stop nor a target is allowed -- the playbook may forbid
    it, the engine does not. An inverted level would fire the moment the entry filled.
    """
    if intent.purpose != "entry":
        return None
    if intent.target_price is None and intent.stop_price is None:
        return None
    entry = intent.limit_price if intent.limit_price is not None else reference_price(intent, ctx)
    if entry is None or entry <= 0:
        return None
    if intent.side == "buy":
        if intent.stop_price is not None and intent.stop_price >= entry:
            return f"stop price {intent.stop_price} must be below the entry {entry} for a buy"
        if intent.target_price is not None and intent.target_price <= entry:
            return f"target price {intent.target_price} must be above the entry {entry} for a buy"
    else:
        if intent.stop_price is not None and intent.stop_price <= entry:
            return f"stop price {intent.stop_price} must be above the entry {entry} for a sell"
        if intent.target_price is not None and intent.target_price >= entry:
            return f"target price {intent.target_price} must be below the entry {entry} for a sell"
    return None


def rule_order_notional(intent: OrderIntent, ctx: RiskContext) -> str | None:
    if reduces_exposure(intent, ctx):
        return None  # a desk may always exit a position in one order
    notional = notional_of(intent, ctx)
    if notional is None:
        return None
    cap = ctx.desk_equity * ctx.manifest.limits.max_order_notional_pct
    if notional > cap:
        return f"order notional {notional:.2f} exceeds {ctx.manifest.limits.max_order_notional_pct:.0%} of desk equity"
    return None


def rule_cash(intent: OrderIntent, ctx: RiskContext) -> str | None:
    if intent.side != "buy":
        return None
    notional = notional_of(intent, ctx)
    if notional is None:
        return None
    if notional > ctx.desk_cash:
        return f"insufficient desk cash: need {notional:.2f}, have {ctx.desk_cash:.2f}"
    return None


def rule_position_limit(intent: OrderIntent, ctx: RiskContext) -> str | None:
    price = reference_price(intent, ctx)
    if price is None or ctx.desk_equity <= 0:
        return None
    held = ctx.positions.get(intent.instrument.key)
    held_qty = held.quantity if held else ZERO
    after = held_qty + signed_quantity(intent)
    value_after = abs(after) * price * intent.instrument.multiplier
    cap = ctx.desk_equity * ctx.manifest.limits.max_position_pct
    if value_after > cap and abs(after) > abs(held_qty):
        return f"position would be {value_after / ctx.desk_equity:.0%} of desk equity, cap {ctx.manifest.limits.max_position_pct:.0%}"
    return None


def rule_gross_limit(intent: OrderIntent, ctx: RiskContext) -> str | None:
    price = reference_price(intent, ctx)
    if price is None or ctx.desk_equity <= 0:
        return None
    held = ctx.positions.get(intent.instrument.key)
    held_qty = held.quantity if held else ZERO
    after = held_qty + signed_quantity(intent)
    if abs(after) <= abs(held_qty):
        return None  # reducing exposure is always allowed
    others = gross_exposure({k: v for k, v in ctx.positions.items() if k != intent.instrument.key})
    gross_after = others + abs(after) * price * intent.instrument.multiplier
    cap = ctx.desk_equity * ctx.manifest.limits.max_gross_pct
    if gross_after > cap:
        return f"gross exposure would be {gross_after / ctx.desk_equity:.0%} of desk equity, cap {ctx.manifest.limits.max_gross_pct:.0%}"
    return None


def rule_order_count(intent: OrderIntent, ctx: RiskContext) -> str | None:
    """The count throttles a desk's own churn. The floor's exits (stops, targets, time stops)
    are not churn: on Sept 16, 2026 a shadow desk that had quoted 120 times was refused its
    stop every five minutes while the position kept falling. They are retried on a slow
    cadence by the exit book, and the gateway's own daily order cap still binds."""
    if intent.purpose == "exit":
        return None
    if ctx.desk_orders_today >= ctx.manifest.limits.max_orders_per_day:
        return f"desk reached {ctx.manifest.limits.max_orders_per_day} orders today"
    return None


def rule_daily_loss(intent: OrderIntent, ctx: RiskContext) -> str | None:
    if ctx.desk_equity <= 0:
        return "desk has no equity"
    start_equity = ctx.desk_equity - ctx.desk_daily_pnl
    if start_equity > 0 and ctx.desk_daily_pnl < 0:
        loss = -ctx.desk_daily_pnl / start_equity
        if loss >= ctx.manifest.limits.max_daily_loss_pct:
            held = ctx.positions.get(intent.instrument.key)
            reducing = held is not None and (
                (held.quantity > 0 and intent.side == "sell") or (held.quantity < 0 and intent.side == "buy")
            )
            if not reducing:
                return f"desk daily loss {loss:.1%} reached limit {ctx.manifest.limits.max_daily_loss_pct:.0%}; only risk-reducing orders allowed"
    return None


def rule_floor_loss(intent: OrderIntent, ctx: RiskContext) -> str | None:
    """The floor's own daily loss halts new risk on the live sleeves. It never refuses an order
    that reduces exposure (an exit is the point of a bad day), and it does not reach a shadow
    desk, whose book adds no risk to the floor: on Sept 16, 2026 a 2.5% live loss refused three
    time-stop exits and froze every shadow explorer."""
    if not ctx.manifest.live or reduces_exposure(intent, ctx):
        return None
    if ctx.floor_equity <= 0:
        return None
    start_equity = ctx.floor_equity - ctx.floor_daily_pnl
    if start_equity > 0 and ctx.floor_daily_pnl < 0:
        loss = -ctx.floor_daily_pnl / start_equity
        if loss >= ctx.floor_max_daily_loss_pct:
            return f"floor daily loss {loss:.1%} reached limit {ctx.floor_max_daily_loss_pct:.0%}"
    return None


def rule_market_hours(intent: OrderIntent, ctx: RiskContext) -> str | None:
    if ctx.market_open is False and intent.instrument.asset_class in ("equity", "option"):
        if intent.order_type == "market":
            return "market orders outside regular hours are not permitted"
    return None


DEFAULT_RULES: tuple[Rule, ...] = (
    rule_kill_switch,
    rule_venue,
    rule_instrument,
    rule_quantity,
    rule_short,
    rule_price_known,
    rule_min_price,
    rule_liquidity,
    rule_limit_sanity,
    rule_exit_plan,
    rule_order_notional,
    rule_cash,
    rule_position_limit,
    rule_gross_limit,
    rule_order_count,
    rule_daily_loss,
    rule_floor_loss,
    rule_market_hours,
)


class RiskEngine:
    def __init__(self, rules: tuple[Rule, ...] = DEFAULT_RULES):
        self.rules = rules

    def check(self, intent: OrderIntent, ctx: RiskContext) -> Decision:
        reasons: list[str] = []
        for rule in self.rules:
            reason = rule(intent, ctx)
            if reason:
                reasons.append(reason)
        return Decision(
            intent_id=intent.id,
            desk_id=intent.desk_id,
            approved=not reasons,
            reasons=tuple(reasons),
            reference_price=reference_price(intent, ctx),
            notional=notional_of(intent, ctx),
            checked_at=ctx.now,
        )


# --------------------------------------------------------------- breakers

@dataclass(frozen=True)
class Breaker:
    scope: str  # "desk:<id>" or "floor"
    rule: str
    detail: str
    action: str  # "halt_new_orders" | "flatten" | "pause_desk"

    def to_dict(self) -> dict[str, Any]:
        return {"scope": self.scope, "rule": self.rule, "detail": self.detail, "action": self.action}


def circuit_breakers(
    *,
    desk: DeskManifest,
    desk_equity: Decimal,
    desk_daily_pnl: Decimal,
    floor_equity: Decimal,
    floor_daily_pnl: Decimal,
    floor_max_daily_loss_pct: Decimal = Decimal("0.08"),
    data_stale_seconds: int | None = None,
    max_stale_seconds: int = 900,
    reconciliation_mismatch: bool = False,
) -> list[Breaker]:
    """Evaluate after every mark. The service halts new orders for the scope of each breaker."""
    out: list[Breaker] = []
    desk_start = desk_equity - desk_daily_pnl
    if desk_start > 0 and desk_daily_pnl < 0:
        loss = -desk_daily_pnl / desk_start
        if loss >= desk.limits.max_daily_loss_pct:
            out.append(Breaker(f"desk:{desk.id}", "daily_loss", f"{loss:.1%}", "halt_new_orders"))
    if desk_equity <= 0:
        out.append(Breaker(f"desk:{desk.id}", "bankrupt", "desk equity is zero or negative", "pause_desk"))
    floor_start = floor_equity - floor_daily_pnl
    if floor_start > 0 and floor_daily_pnl < 0:
        loss = -floor_daily_pnl / floor_start
        if loss >= floor_max_daily_loss_pct:
            out.append(Breaker("floor", "daily_loss", f"{loss:.1%}", "halt_new_orders"))
    if data_stale_seconds is not None and data_stale_seconds > max_stale_seconds:
        out.append(Breaker("floor", "stale_data", f"{data_stale_seconds}s since last market observation", "halt_new_orders"))
    if reconciliation_mismatch:
        out.append(Breaker("floor", "reconciliation", "broker positions do not match the ledger", "halt_new_orders"))
    return out
