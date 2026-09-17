"""Deterministic pre-trade risk rules and circuit breakers.

No model is consulted here. Every rule is a pure function of the intent and a `RiskContext`
snapshot assembled by the service. A rule returns a reason string to reject or `None` to pass.
All rules run so the decision lists every violated rule, which is what the public sees.

Rules are ordered from cheapest and most absolute (kill switch) to most data-dependent.
"""

from __future__ import annotations

import functools
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
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
    #: Instrument key -> quantity the desk's working sells (resting, or in flight on another
    #: thread) already offer. A position is sold once: an exit and a strategy selling it at the
    #: same moment sold 200 of 100 held (Sept 16, 2026 audit).
    working_sells: dict[str, Decimal] = field(default_factory=dict)
    #: Kalshi market id -> cash the desk's working buys on that market (either leg) commit.
    working_event_buys: dict[str, Decimal] = field(default_factory=dict)
    #: Firm-wide event rules (Sept 17, 2026: the floor's real losses were 1-3 cent longshots and
    #: single markets holding 8% of the firm). Zero switches a rule off.
    min_event_price: Decimal = ZERO
    max_event_market_pct: Decimal = ZERO
    max_event_market_floor_pct: Decimal = ZERO
    #: Sept 17, 2026: what markets that settle together (one `event_cluster`) may put at risk
    #: across every live desk, as a share of the live floor. Zero switches it off.
    max_event_cluster_floor_pct: Decimal = ZERO
    #: What the live desks together hold at cost and commit in working buys, keyed by Kalshi
    #: market id and by `cluster_key(event_cluster(market))`. The gateway fills it for a live
    #: desk's event buy; an empty map means only this desk's own book is known.
    floor_event_exposure: dict[str, Decimal] = field(default_factory=dict)

    def __post_init__(self):
        for name in ("min_event_price", "max_event_market_pct", "max_event_market_floor_pct", "max_event_cluster_floor_pct"):
            setattr(self, name, money(getattr(self, name) or 0))
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
    held_qty = (held.quantity if held else ZERO) - (ctx.working_sells or {}).get(intent.instrument.key, ZERO)
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
    return bool(held_qty and 0 < intent.quantity <= abs(held_qty)
                and (intent.side == "sell") == (held_qty > 0))


def rule_exit_plan(intent: OrderIntent, ctx: RiskContext) -> str | None:
    """A stop sits on the losing side of the entry and a target on the winning side.

    leap: exits. The entry price is the limit when there is one, else the quote's reference
    for the side. With neither there is nothing to compare against and the plan stands as
    written; a plan naming neither a stop nor a target is allowed -- the playbook may forbid
    it, the engine does not. An inverted level would fire the moment the entry filled.
    """
    if intent.purpose != "entry":
        held = ctx.positions.get(intent.instrument.key)
        if (held is None or held.quantity == 0 or intent.quantity > abs(held.quantity)
                or (intent.side == "sell") != (held.quantity > 0)):
            return "an exit must reduce an existing position without reversing it"
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


def _event_entry_price(intent: OrderIntent, ctx: RiskContext) -> Decimal | None:
    """What an event buy pays per contract: its limit when it has one (a resting bid never pays
    the ask), else the quote's reference."""
    if intent.order_type == "limit" and intent.limit_price is not None and intent.limit_price > 0:
        return intent.limit_price
    return reference_price(intent, ctx)


def _opens_event(intent: OrderIntent, ctx: RiskContext) -> bool:
    return (
        intent.instrument.asset_class == "event"
        and intent.side == "buy"
        and intent.purpose != "exit"
        and not reduces_exposure(intent, ctx)
    )


def rule_event_longshot(intent: OrderIntent, ctx: RiskContext) -> str | None:
    """No desk buys an event contract under `min_event_price`. Buyers of Kalshi longshots lose:
    makers who bought at 10 cents or less lost 0.9 to 6.7 cents a contract across 1,054
    program-days (Sept 16, 2026 study), and the floor's own 1-3 cent weather tails lost 60% of
    what they cost in a day. Exits and closing trades are never refused."""
    if ctx.min_event_price <= 0 or not _opens_event(intent, ctx):
        return None
    price = _event_entry_price(intent, ctx)
    if price is not None and price < ctx.min_event_price:
        return (
            f"buying a longshot at {price}: the floor buys no event contract under {ctx.min_event_price} "
            "(longshot buyers lose on Kalshi; sell the longshot by buying the other side instead)"
        )
    return None


def _desk_market_at_risk(intent: OrderIntent, ctx: RiskContext, market: str, price: Decimal) -> Decimal:
    """This desk's own cost on one market: both legs held at cost, its working buys there, and
    this order."""
    held = ZERO
    for position in ctx.positions.values():
        ins = position.instrument
        if ins.asset_class == "event" and (ins.market_id or ins.symbol) == market and position.quantity > 0:
            held += position.quantity * position.average_cost * ins.multiplier
    return held + ctx.working_event_buys.get(market, ZERO) + intent.quantity * price * intent.instrument.multiplier


def rule_event_market_cap(intent: OrderIntent, ctx: RiskContext) -> str | None:
    """What one Kalshi market can cost the desk: both legs held at cost, its working buys, and
    this order, at most `max_event_market_pct` of desk equity, and for a desk on real money at
    most `max_event_market_floor_pct` of the live floor's equity. A single $70 macro position was
    8% of the firm on Sept 16, 2026. It reads this desk's book only; what the other live desks
    hold on the same market is `rule_event_floor_cluster`'s."""
    if not _opens_event(intent, ctx) or (ctx.max_event_market_pct <= 0 and ctx.max_event_market_floor_pct <= 0):
        return None
    market = intent.instrument.market_id or intent.instrument.symbol
    price = _event_entry_price(intent, ctx)
    if not market or price is None:
        return None
    at_risk = _desk_market_at_risk(intent, ctx, market, price)
    caps = []
    if ctx.max_event_market_pct > 0 and ctx.desk_equity > 0:
        caps.append((ctx.desk_equity * ctx.max_event_market_pct, f"{ctx.max_event_market_pct:.0%} of desk equity"))
    if ctx.manifest.live and ctx.max_event_market_floor_pct > 0 and ctx.floor_equity > 0:
        caps.append((ctx.floor_equity * ctx.max_event_market_floor_pct, f"{ctx.max_event_market_floor_pct:.1%} of the live floor"))
    for cap, label in caps:
        if at_risk > cap:
            return f"{market} would put {at_risk:.2f} at risk on one market, cap {cap:.2f} ({label})"
    return None


#: Series roots whose markets settle on one underlying move, grouped as one cluster. Sept 17, 2026:
#: bitcoin and ether hourly markets that close in the same hour are one bet on crypto that hour.
EVENT_CLUSTER_ROOTS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("KXBTC", "KXETH", "KXSOL", "KXXRP", "KXDOGE"), "crypto"),
    (("KXGOLD", "KXSILVER", "KXBRENT", "KXWTI", "KXCOPPER"), "commod"),
    (("KXHIGH",), "weather"),
)
#: A Kalshi event code after the series: `26SEP1717` (Sept 17 2026, 17:00 New York time),
#: `26SEP17H1600`, `26SEP161910NYYBOS` (19:10), or a date alone, `26SEP17`.
_TICKER_CODE = re.compile(r"^(\d{2})([A-Z]{3})(\d{2})(?:H?(\d{2})(\d{2})?)?")
_MONTHS = {m: i for i, m in enumerate(("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"), start=1)}


def _new_york_to_utc(moment: datetime) -> datetime:
    """A naive New York wall-clock time as UTC. Kalshi writes a ticker's hour in New York time:
    KXBTCD-26SEP1017 closes at 21:00 UTC."""
    try:
        from zoneinfo import ZoneInfo

        return moment.replace(tzinfo=ZoneInfo("America/New_York")).astimezone(timezone.utc)
    except Exception:  # no tz database: US daylight time runs from March's second Sunday to November's first
        march = datetime(moment.year, 3, 8)
        begins = march + timedelta(days=(6 - march.weekday()) % 7, hours=2)
        november = datetime(moment.year, 11, 1)
        ends = november + timedelta(days=(6 - november.weekday()) % 7, hours=2)
        offset = 4 if begins <= moment < ends else 5
        return (moment + timedelta(hours=offset)).replace(tzinfo=timezone.utc)


def event_cluster(ticker: str, close_time: Any = None) -> str:
    """The cluster a Kalshi market settles with: a group (`crypto`, `commod`, `weather`, else the
    series) and the hour it closes in UTC, as `crypto:2026-09-17T21`.

    `close_time` (ISO) gives the hour when it is known. Without it the hour comes from the
    ticker's event code, read as New York time. A code with a date and no hour gives the date
    (`weather:2026-09-17`: every city's high that day). A ticker with no readable code gives the
    group alone. A key with less time in it than another is not a different cluster: it is one
    whose hour is unknown, so `clusters_overlap` counts it with every hour it could be, and
    `cluster_at_risk` sums a cluster that way (Sept 17, 2026 review: an undated key was counted
    only against other undated keys, so its exposure never reached an hourly cluster's cap).
    The gateway keys every position, working buy and order from its ticker."""
    return _event_cluster(str(ticker or ""), None if not close_time else str(close_time))


@functools.lru_cache(maxsize=8192)
def _event_cluster(ticker: str, close_time: str | None) -> str:
    """`event_cluster`, cached: the gateway keys every live desk's legs on every live event buy."""
    parts = ticker.strip().upper().split("-")
    series = parts[0]
    group = series
    for roots, name in EVENT_CLUSTER_ROOTS:
        if series.startswith(roots):
            group = name
            break
    if close_time:
        try:
            moment = datetime.fromisoformat(str(close_time).strip().replace("Z", "+00:00"))
            if moment.tzinfo is None:
                moment = moment.replace(tzinfo=timezone.utc)
            return f"{group}:{moment.astimezone(timezone.utc).strftime('%Y-%m-%dT%H')}"
        except (TypeError, ValueError):
            pass
    match = _TICKER_CODE.match(parts[1]) if len(parts) > 1 else None
    if match is None or match.group(2) not in _MONTHS:
        return group
    year, month, day, hour = 2000 + int(match.group(1)), _MONTHS[match.group(2)], int(match.group(3)), match.group(4)
    try:
        if hour is not None and int(hour) <= 23:
            return f"{group}:{_new_york_to_utc(datetime(year, month, day, int(hour))).strftime('%Y-%m-%dT%H')}"
        return f"{group}:{datetime(year, month, day).strftime('%Y-%m-%d')}"
    except ValueError:
        return group


CLUSTER_PREFIX = "cluster:"
#: Set in `floor_event_exposure` when a live desk's book could not be read: its exposure is
#: unknown, so no live event buy is approved against a total that leaves it out.
FLOOR_BOOK_UNREADABLE = "floor:unreadable"


def cluster_key(cluster: str) -> str:
    """How a cluster sits in `floor_event_exposure`, beside market ids."""
    return f"{CLUSTER_PREFIX}{cluster}"


def clusters_overlap(a: str, b: str) -> bool:
    """True when markets keyed `a` and `b` could settle together: the same group, and times that
    could be the same hour. The same hour or the same date compare equal; a date (a ticker's
    local day) meets every UTC hour on that date or the next, since a US day ends by 11:00 UTC
    the day after; a key with no time (an unreadable code) meets every key of its group. Anything
    this cannot read overlaps: the conservative answer."""
    group_a, _, when_a = str(a).partition(":")
    group_b, _, when_b = str(b).partition(":")
    if group_a != group_b:
        return False
    if not when_a or not when_b:
        return True
    if len(when_a) == len(when_b):
        return when_a == when_b
    day, hour = (when_a, when_b) if len(when_a) < len(when_b) else (when_b, when_a)
    try:
        start = datetime.strptime(day, "%Y-%m-%d")
    except ValueError:
        return True
    return hour[:10] in (day, (start + timedelta(days=1)).strftime("%Y-%m-%d"))


def cluster_at_risk(book: dict[str, Decimal], cluster: str) -> Decimal:
    """What `book` (`floor_event_exposure`'s shape) holds on every cluster that overlaps `cluster`."""
    total = ZERO
    for key, amount in book.items():
        if key.startswith(CLUSTER_PREFIX) and clusters_overlap(key[len(CLUSTER_PREFIX):], cluster):
            total += amount
    return total


def add_event_exposure(book: dict[str, Decimal], market: str, amount: Decimal) -> None:
    """Count `amount` at risk on `market` and on its cluster."""
    if not market or amount <= 0:
        return
    for key in (market, cluster_key(event_cluster(market))):
        book[key] = book.get(key, ZERO) + amount


def rule_event_floor_cluster(intent: OrderIntent, ctx: RiskContext) -> str | None:
    """What every live desk together puts at risk on one market, and on one cluster of markets
    that settle together: at most `max_event_market_floor_pct` (3.5%) and
    `max_event_cluster_floor_pct` (8%) of the live floor. Legs held at cost, working buys and this
    order all count; a leg whose close hour is unknown counts against every hour it could close in
    (`cluster_at_risk`), and a live desk whose book could not be read refuses the buy. A shadow desk
    is never checked and never counted, and exits are never refused.

    Sept 17, 2026: `rule_event_market_cap` read only the desk's own book. `mullins` and `mullins-4`
    run nearly the same favorites settings, so each could put 3.5% of the floor on the same
    market, and bitcoin and ether markets closing in the same hour counted as unrelated bets."""
    if not ctx.manifest.live or not _opens_event(intent, ctx) or ctx.floor_equity <= 0:
        return None
    if ctx.max_event_market_floor_pct <= 0 and ctx.max_event_cluster_floor_pct <= 0:
        return None
    market = intent.instrument.market_id or intent.instrument.symbol
    price = _event_entry_price(intent, ctx)
    if not market or price is None:
        return None
    exposure = ctx.floor_event_exposure or {}
    if FLOOR_BOOK_UNREADABLE in exposure:
        return "a live desk's book could not be read, so what the live desks hold across the floor is unknown: no event buy until it can"
    cost = intent.quantity * price * intent.instrument.multiplier
    if ctx.max_event_market_floor_pct > 0:
        cap = ctx.floor_equity * ctx.max_event_market_floor_pct
        own = _desk_market_at_risk(intent, ctx, market, price)
        at_risk = max(own, exposure.get(market, ZERO) + cost)
        # The desk over the cap on its own is `rule_event_market_cap`'s refusal; one reason will do.
        if at_risk > cap and own <= cap:
            return (
                f"{market} would put {at_risk:.2f} at risk across the live desks, cap {cap:.2f} "
                f"({ctx.max_event_market_floor_pct:.1%} of the live floor)"
            )
    if ctx.max_event_cluster_floor_pct > 0:
        cluster = event_cluster(market)
        cap = ctx.floor_equity * ctx.max_event_cluster_floor_pct
        # This desk's own book counts even when the floor's map is missing.
        own_book: dict[str, Decimal] = {}
        for position in ctx.positions.values():
            ins = position.instrument
            if ins.asset_class == "event" and position.quantity > 0:
                add_event_exposure(own_book, ins.market_id or ins.symbol, position.quantity * position.average_cost * ins.multiplier)
        for working, amount in ctx.working_event_buys.items():
            add_event_exposure(own_book, working, amount)
        # Keys with less time in them (a date, or none) are counted with every hour they could be.
        at_risk = max(cluster_at_risk(own_book, cluster), cluster_at_risk(exposure, cluster)) + cost
        if at_risk > cap:
            return (
                f"{cluster} would put {at_risk:.2f} at risk across the live desks, cap {cap:.2f} "
                f"({ctx.max_event_cluster_floor_pct:.0%} of the live floor on markets that settle together)"
            )
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
    # Withdrawing a sleeve while inventory winds down can leave its accounting equity at
    # zero or below. That must block new risk, not trap the inventory by refusing its exit.
    if reduces_exposure(intent, ctx):
        return None
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
    rule_event_longshot,
    rule_event_market_cap,
    rule_event_floor_cluster,
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
