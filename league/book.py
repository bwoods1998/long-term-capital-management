"""One netting book per venue account.

Every agent that trades on a venue trades through that venue's one `Book`. The book

- keeps each agent's cash and holdings, folded from the ledger and from nothing else, so a
  restart rebuilds exactly the state the ledger records;
- runs every intent through the first run's deterministic risk engine (`ltcm/risk.py`, all 21
  rules, unchanged) plus the league's own rules: the $75 order cap the gateway also enforces, a
  per-agent position cap set by the agent's rung, no leverage, no shorts, and no order that
  could trade against one of the House's own resting orders;
- nets the market orders of one batch: opposite sides on one instrument are crossed inside the
  House and only the difference is sent to the venue, so two agents on one account never trade
  against each other (a wash trade, and double fees). A crossed agent is filled exactly as the
  venue would have filled it alone: the buyer pays the ask, the seller receives the bid, both
  pay the taker fee. The spread and fees the account did not actually pay accrue to the House
  row of the book, which is what keeps the agents' books summing to the venue's.
- attributes venue fills back to the intents behind an order pro rata, by largest remainder on
  the instrument's quantity step;
- reconciles its total cash and positions to the venue's, and books sub-cent differences as dust.

Limit orders are never pooled: each is one venue order owned by one agent, so its fills need no
apportioning. An intent that would cross one of the House's own resting orders is refused, as a
venue refuses a post-only order that would cross: the agent re-prices or waits.

Kalshi legs: an agent holds YES or NO contracts of a market as separate long holdings, never a
short. For crossing checks both legs are read in YES price space, because a NO bid at q is a YES
offer at 1 - q and would trade against a resting YES bid at or above it.
"""

from __future__ import annotations

import hashlib
import threading
import time
from dataclasses import dataclass, field
from decimal import ROUND_DOWN, Decimal
from types import SimpleNamespace
from typing import Any, Iterable, Mapping, Sequence

from ltcm.broker import (
    Broker,
    BrokerError,
    Instrument,
    Order,
    OrderIntent,
    Position,
    Quote,
    RejectedOrder,
    UnknownOutcome,
    money,
)
from ltcm.risk import RiskContext, RiskEngine, add_event_exposure, cluster_key, event_cluster

from .fees import QTY_PLACES, Charge, Fees, received
from .ledger import HOUSE, Ledger, now_iso

ZERO = Decimal(0)
ONE = Decimal(1)
CASH_PLACES = Decimal("0.00000001")
DUST_USD = Decimal("0.01")

#: What the adapters' open statuses look like to the book.
OPEN_STATUSES = ("new", "accepted", "partially_filled", "unknown")


class BookError(RuntimeError):
    """The book cannot do what was asked (not a refusal of one intent: those are outcomes)."""


def q_cash(value: Decimal) -> Decimal:
    return money(value).quantize(CASH_PLACES)


def text(value: Decimal | None) -> str | None:
    return None if value is None else format(value, "f")


def step_of(instrument: Instrument, order_type: str = "market") -> Decimal:
    """The smallest quantity increment the venue takes for this instrument."""
    if instrument.asset_class in ("event", "option", "future"):
        return ONE
    if instrument.asset_class == "equity" and order_type == "limit":
        return ONE  # fractional shares are for market orders; a limit order is whole shares
    return QTY_PLACES


def yes_space(instrument: Instrument, side: str, price: Decimal | None) -> tuple[str, Decimal | None]:
    """An order's side and price in the market's YES price space (identity for everything else)."""
    if instrument.asset_class != "event" or (instrument.right or "yes") == "yes":
        return side, price
    flipped = "sell" if side == "buy" else "buy"
    return flipped, (None if price is None else ONE - price)


def position_key(instrument: Instrument) -> str:
    """One spelling for one position, however the venue or an agent wrote it. Alpaca reports a
    crypto position as `BTCUSD` and takes orders for `BTC/USD`; a strike comes back `650.000`."""
    symbol = instrument.symbol.upper()
    if instrument.asset_class == "crypto":
        return f"crypto:{symbol.replace('/', '').replace('-', '')}:{instrument.venue}"
    if instrument.asset_class == "option":
        strike = format(money(instrument.strike).normalize(), "f")
        return f"option:{symbol}:{instrument.venue}:{instrument.expiry}:{strike}:{instrument.right}"
    if instrument.asset_class == "event":
        ticker = (instrument.market_id or symbol).upper()
        return f"event:{ticker}:{instrument.venue}:{instrument.right or 'yes'}"
    return f"{instrument.asset_class}:{symbol}:{instrument.venue}"


def market_key(instrument: Instrument) -> str:
    """What two orders must share to be able to trade against each other."""
    if instrument.asset_class == "event":
        return f"event:{(instrument.market_id or instrument.symbol).upper()}:{instrument.venue}"
    return instrument.key


# --------------------------------------------------------------------------------------- data
@dataclass(frozen=True)
class Intent:
    """One agent's wish to trade. `id` is derived, so a retried batch is the same batch."""

    id: str
    agent: str
    instrument: Instrument
    side: str
    quantity: Decimal
    order_type: str
    limit_price: Decimal | None
    post_only: bool
    time_in_force: str
    reason: str
    created_at: str
    expires_at: str | None = None

    @classmethod
    def new(
        cls,
        *,
        agent: str,
        instrument: Instrument,
        side: str,
        quantity: Any,
        order_type: str = "market",
        limit_price: Any = None,
        post_only: bool = False,
        time_in_force: str | None = None,
        reason: str,
        created_at: str,
        nonce: str = "",
        expires_at: str | None = None,
    ) -> "Intent":
        quantity = money(quantity)
        limit = None if limit_price is None else money(limit_price)
        if time_in_force is None:
            time_in_force = default_tif(instrument, order_type)
        material = "|".join(
            [agent, instrument.key, side, format(quantity, "f"), order_type, text(limit) or "", nonce]
        )
        return cls(
            id="in-" + hashlib.sha256(material.encode()).hexdigest()[:32],
            agent=agent,
            instrument=instrument,
            side=side,
            quantity=quantity,
            order_type=order_type,
            limit_price=limit,
            post_only=bool(post_only),
            time_in_force=time_in_force,
            reason=str(reason or "").strip()[:2000] or "no reason given",
            created_at=created_at,
            expires_at=expires_at,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "agent": self.agent,
            "instrument": self.instrument.to_dict(),
            "side": self.side,
            "quantity": text(self.quantity),
            "order_type": self.order_type,
            "limit_price": text(self.limit_price),
            "post_only": self.post_only,
            "time_in_force": self.time_in_force,
            "reason": self.reason,
            "created_at": self.created_at,
        }


def default_tif(instrument: Instrument, order_type: str) -> str:
    """Crypto and event orders have no trading day; a fractional equity market order must be `day`."""
    if instrument.asset_class in ("crypto", "event"):
        return "gtc"
    return "day"


@dataclass
class Holding:
    instrument: Instrument
    quantity: Decimal = ZERO
    cost: Decimal = ZERO  # what the units still held cost, fees included
    opened_at: str | None = None
    reason: str = ""

    @property
    def average_cost(self) -> Decimal:
        per = self.quantity * self.instrument.multiplier
        return self.cost / per if per else ZERO


@dataclass
class Account:
    agent: str
    staked: Decimal = ZERO
    cash: Decimal = ZERO
    realized: Decimal = ZERO
    fees: Decimal = ZERO
    holdings: dict[str, Holding] = field(default_factory=dict)


@dataclass
class Share:
    """One intent's part of a venue order."""

    intent_id: str
    agent: str
    quantity: Decimal
    reason: str
    filled: Decimal = ZERO


@dataclass
class Working:
    """A venue order the book sent and is still responsible for."""

    order_id: str
    broker_order_id: str | None
    instrument: Instrument
    side: str
    quantity: Decimal
    order_type: str
    limit_price: Decimal | None
    post_only: bool
    status: str
    shares: list[Share]
    submitted_at: str
    liquidity: str = "taker"  # decided when routed: a limit order that did not cross is a maker
    rested: bool = False
    filled: Decimal = ZERO
    notional: Decimal = ZERO  # sum of price x quantity attributed so far
    fees_seen: Decimal = ZERO  # venue-reported fees attributed so far

    @property
    def open(self) -> bool:
        return self.status in OPEN_STATUSES

    @property
    def remaining(self) -> Decimal:
        return self.quantity - self.filled


@dataclass(frozen=True)
class Limits:
    """What one agent may do on one book. Set by the House from the agent's rung."""

    max_position_usd: Decimal
    max_order_usd: Decimal
    asset_classes: tuple[str, ...] = ("equity", "option", "crypto", "event")
    max_orders_per_day: int = 200


@dataclass(frozen=True)
class Outcome:
    intent_id: str
    agent: str
    status: str  # refused | crossed | sent | filled | partial | resting | rejected | unknown | duplicate
    detail: str = ""
    order_id: str | None = None
    filled: Decimal = ZERO


@dataclass(frozen=True)
class Reconciliation:
    ok: bool
    cash_venue: Decimal
    cash_ledger: Decimal
    cash_diff: Decimal
    position_diffs: dict[str, str]
    dust_booked: Decimal
    detail: str = ""


#: The first run's firm rules, kept. See `ltcm/config.json` `event_rules`.
DEFAULT_RULES: dict[str, Any] = {
    "max_order_usd": "75",  # the gateway refuses more; the book refuses first and says why
    "min_event_price": "0.15",
    "max_event_market_pct": "0.30",
    "max_event_market_floor_pct": "0.10",
    "max_event_cluster_floor_pct": "0.25",
    "max_position_pct": "0.50",
    "max_gross_pct": "1.0",
    "max_order_notional_pct": "0.50",
    "max_daily_loss_pct": "0.10",
    "max_limit_deviation_pct": "0.10",
    "floor_max_daily_loss_pct": "0.08",
    "max_quote_age_seconds": 900,
    "market_slippage_pct": "0.005",
}


def allocate(total: Decimal, weights: Sequence[Decimal], step: Decimal) -> list[Decimal]:
    """Split `total` across `weights` pro rata on a grid of `step`, by largest remainder.

    Never allocates more than a weight (a share cannot fill beyond what it asked for) and the
    parts always sum to `total` when the weights can hold it. Ties go to the earlier weight.
    """
    total = money(total)
    capacity = sum(weights, ZERO)
    if total <= 0 or capacity <= 0:
        return [ZERO for _ in weights]
    if total >= capacity:
        return [money(w) for w in weights]
    raw = [total * w / capacity for w in weights]
    parts = [(r / step).to_integral_value(rounding=ROUND_DOWN) * step for r in raw]
    left = total - sum(parts, ZERO)
    order = sorted(range(len(weights)), key=lambda i: (-(raw[i] - parts[i]), i))
    while left > 0:
        moved = False
        for i in order:
            room = weights[i] - parts[i]
            if room <= 0:
                continue
            add = min(step, left, room)
            parts[i] += add
            left -= add
            moved = True
            if left <= 0:
                break
        if not moved:
            break
    return parts


# --------------------------------------------------------------------------------------- book
class Book:
    """The one path from an agent's intent to a venue, and the only writer of `book.*` rows."""

    def __init__(
        self,
        name: str,
        broker: Broker,
        ledger: Ledger,
        *,
        fees: Fees,
        real_money: bool,
        rules: Mapping[str, Any] | None = None,
        clock=time.time,
        market_open: Any = None,
        kill_switch: Any = None,
    ):
        self.name = name
        self.broker = broker
        self.ledger = ledger
        self.fees = fees
        self.real_money = bool(real_money)
        self.rules = {**DEFAULT_RULES, **dict(rules or {})}
        self.clock = clock
        self.market_open = market_open  # callable(instrument, iso) -> bool | None
        self.kill_switch = kill_switch  # callable() -> bool
        self.engine = RiskEngine()
        self.limits: dict[str, Limits] = {}
        self.accounts: dict[str, Account] = {}
        self.orders: dict[str, Working] = {}
        self.seen_intents: set[str] = set()
        self.marks: dict[str, Decimal] = {}  # instrument key -> last liquidation mark
        self.day_open: dict[str, tuple[str, Decimal]] = {}  # agent -> (day, equity at its start)
        self.orders_today: dict[tuple[str, str], int] = {}
        self.frozen: str | None = None  # a reconciliation mismatch stops new entries
        #: What the venue account held that is not the book's: cash and positions from before the
        #: book opened (the paper account's $100,000; the real account's unallocated cash).
        self.baseline_cash: Decimal | None = None
        self.baseline_positions: dict[str, Decimal] = {}
        self.venue_cash: Decimal | None = None
        self._fills_since_reconcile = 0
        self._lock = threading.RLock()
        self._cursor = 0
        self._fold()

    # ----------------------------------------------------------------- folding
    def _fold(self) -> None:
        """Rebuild state from the ledger. Every mutation below appends first and applies the
        appended row through `_apply`, so the live state and a rebuilt one are the same state."""
        kinds = ("book.stake", "book.fill", "book.settle", "book.order", "book.baseline", "agent.intent")
        for entry in self.ledger.iter(kinds=kinds):
            if entry.payload.get("book") == self.name:
                self._apply(entry.kind, entry.agent, entry.payload, entry.at)

    def _account(self, agent: str) -> Account:
        account = self.accounts.get(agent)
        if account is None:
            account = self.accounts[agent] = Account(agent)
        return account

    def _apply(self, kind: str, agent: str, p: Mapping[str, Any], at: str) -> None:
        if kind == "agent.intent":
            self.seen_intents.add(str(p["id"]))
            day = str(p.get("created_at") or at)[:10]
            self.orders_today[(agent, day)] = self.orders_today.get((agent, day), 0) + 1
        elif kind == "book.stake":
            account = self._account(agent)
            usd = money(p["usd"])
            account.staked += usd
            account.cash += usd
        elif kind == "book.fill":
            if agent == HOUSE:
                self._apply_house(p)
            else:
                self._apply_fill(agent, p, at)
        elif kind == "book.baseline":
            self.baseline_cash = money(p["cash"])
            self.baseline_positions = {k: money(v) for k, v in dict(p.get("positions") or {}).items()}
        elif kind == "book.settle":
            account = self._account(agent)
            instrument = Instrument.from_dict(p["instrument"])
            holding = account.holdings.get(instrument.key)
            payout = money(p["payout"])
            account.cash += payout
            if holding is not None:
                account.realized += payout - holding.cost
                del account.holdings[instrument.key]
        elif kind == "book.order":
            self._apply_order(p)

    def _apply_fill(self, agent: str, p: Mapping[str, Any], at: str) -> None:
        account = self._account(agent)
        cash_delta = money(p["cash_delta"])
        position_delta = money(p["position_delta"])
        account.cash += cash_delta
        account.fees += money(p.get("fee_usd") or 0)
        if position_delta != 0:
            instrument = Instrument.from_dict(p["instrument"])
            holding = account.holdings.get(instrument.key)
            if holding is None:
                holding = account.holdings[instrument.key] = Holding(instrument)
            if position_delta > 0:
                if holding.quantity <= 0:
                    holding.opened_at = at
                    holding.reason = str(p.get("reason") or "")
                holding.quantity += position_delta
                holding.cost += -cash_delta
            else:
                sold = -position_delta
                basis = holding.cost * sold / holding.quantity if holding.quantity > 0 else ZERO
                account.realized += cash_delta - basis
                holding.quantity -= sold
                holding.cost -= basis
            if holding.quantity <= 0:
                del account.holdings[instrument.key]
        order_id = p.get("order_id")
        working = self.orders.get(order_id) if order_id else None
        if working is not None and p.get("source") == "venue":
            self._fills_since_reconcile += 1
            traded = money(p["quantity"])
            working.filled += traded
            working.notional += traded * money(p["price"])
            working.fees_seen += money(p.get("venue_fee") or 0)
            for share in working.shares:
                if share.intent_id == p.get("intent_id"):
                    share.filled += traded

    def _apply_order(self, p: Mapping[str, Any]) -> None:
        order_id = str(p["order_id"])
        working = self.orders.get(order_id)
        if working is None:
            working = self.orders[order_id] = Working(
                order_id=order_id,
                broker_order_id=p.get("broker_order_id"),
                instrument=Instrument.from_dict(p["instrument"]),
                side=p["side"],
                quantity=money(p["quantity"]),
                order_type=p["order_type"],
                limit_price=None if p.get("limit_price") is None else money(p["limit_price"]),
                post_only=bool(p.get("post_only")),
                status=p["status"],
                shares=[
                    Share(s["intent_id"], s["agent"], money(s["quantity"]), str(s.get("reason") or ""))
                    for s in p["shares"]
                ],
                submitted_at=p.get("submitted_at") or "",
                liquidity=str(p.get("liquidity") or "taker"),
            )
        working.status = p["status"]
        working.rested = bool(p.get("rested", working.rested))
        if p.get("broker_order_id"):
            working.broker_order_id = p["broker_order_id"]

    # ------------------------------------------------------------------ stakes
    def stake(self, agent: str, usd: Any, *, note: str = "") -> None:
        """Lend an agent capital on this book (negative takes it back). On a real-money book the
        stakes are slices of the venue's actual cash; on a paper book they are the live account's
        size, not the paper account's $100,000."""
        usd = money(usd)
        with self._lock:
            account = self._account(agent)
            if usd < 0 and account.cash - self._reserved_cash(agent) + usd < 0:
                raise BookError(f"{agent} does not have {-usd} of free cash on {self.name}")
            if usd > 0 and self.real_money:
                # A real stake is a slice of cash the venue actually holds, never a promise.
                if self.venue_cash is None:
                    raise BookError(f"{self.name} has not been reconciled to its venue yet")
                lent = sum((a.staked for name, a in self.accounts.items() if name != HOUSE), ZERO)
                if lent + usd > self.venue_cash:
                    raise BookError(f"{self.name} holds ${self.venue_cash:.2f}; ${lent + usd:.2f} of stakes would exceed it")
            payload = {"book": self.name, "usd": text(usd), "note": note, "real_money": self.real_money}
            entry = self.ledger.append("book.stake", payload, agent=agent)
            self._apply(entry.kind, agent, entry.payload, entry.at)

    # ------------------------------------------------------------------- reads
    def account(self, agent: str) -> Account:
        with self._lock:
            return self._account(agent)

    def agents(self) -> list[str]:
        with self._lock:
            return sorted(a for a in self.accounts if a != HOUSE)

    def open_orders(self, agent: str | None = None) -> list[Working]:
        with self._lock:
            return [
                w
                for w in self.orders.values()
                if w.open and (agent is None or any(s.agent == agent for s in w.shares))
            ]

    def _reserved_cash(self, agent: str) -> Decimal:
        total = ZERO
        for working in self.orders.values():
            if not working.open or working.side != "buy":
                continue
            price = working.limit_price or self.marks.get(working.instrument.key) or ZERO
            for share in working.shares:
                if share.agent == agent:
                    total += (share.quantity - share.filled) * price * working.instrument.multiplier
        return total

    def _reserved_sells(self, agent: str) -> dict[str, Decimal]:
        out: dict[str, Decimal] = {}
        for working in self.orders.values():
            if not working.open or working.side != "sell":
                continue
            for share in working.shares:
                if share.agent == agent:
                    key = working.instrument.key
                    out[key] = out.get(key, ZERO) + (share.quantity - share.filled)
        return out

    def _working_event_buys(self, agent: str) -> dict[str, Decimal]:
        out: dict[str, Decimal] = {}
        for working in self.orders.values():
            if not working.open or working.side != "buy" or working.instrument.asset_class != "event":
                continue
            market = (working.instrument.market_id or working.instrument.symbol).upper()
            for share in working.shares:
                if share.agent == agent and working.limit_price is not None:
                    out[market] = out.get(market, ZERO) + (share.quantity - share.filled) * working.limit_price
        return out

    def equity(self, agent: str) -> Decimal:
        """Cash plus holdings at their last liquidation mark (cost when never marked)."""
        with self._lock:
            account = self._account(agent)
            total = account.cash
            for key, holding in account.holdings.items():
                mark = self.marks.get(key)
                if mark is None:
                    total += holding.cost
                else:
                    total += holding.quantity * mark * holding.instrument.multiplier
            return total

    def total_equity(self) -> Decimal:
        with self._lock:
            return sum((self.equity(a) for a in self.accounts), ZERO)

    def _event_exposure(self) -> dict[str, Decimal]:
        """Every agent's event contracts at cost, by market and by cluster: the floor-wide view
        the first run's cluster rule reads."""
        book: dict[str, Decimal] = {}
        for account in self.accounts.values():
            for holding in account.holdings.values():
                if holding.instrument.asset_class == "event" and holding.cost > 0:
                    market = (holding.instrument.market_id or holding.instrument.symbol).upper()
                    add_event_exposure(book, market, holding.cost)
        for working in self.orders.values():
            if working.open and working.side == "buy" and working.instrument.asset_class == "event":
                market = (working.instrument.market_id or working.instrument.symbol).upper()
                if working.limit_price is not None:
                    add_event_exposure(book, market, working.remaining * working.limit_price)
        return book

    # -------------------------------------------------------------------- risk
    def _manifest(self, agent: str, limits: Limits) -> Any:
        r = self.rules
        return SimpleNamespace(
            id=agent,
            venues=(self.broker.venue,),
            live=self.real_money,
            instruments=SimpleNamespace(
                asset_classes=tuple(limits.asset_classes),
                permits_symbol=lambda symbol: True,
                allow_short=False,
                min_price=ZERO,
                min_adv_usd=ZERO,
            ),
            limits=SimpleNamespace(
                max_position_pct=money(r["max_position_pct"]),
                max_gross_pct=money(r["max_gross_pct"]),
                max_order_notional_pct=money(r["max_order_notional_pct"]),
                max_daily_loss_pct=money(r["max_daily_loss_pct"]),
                max_orders_per_day=int(limits.max_orders_per_day),
                max_limit_deviation_pct=money(r["max_limit_deviation_pct"]),
            ),
        )

    def _order_intent(self, intent: Intent, *, quantity: Decimal | None = None, nonce: str = "") -> OrderIntent:
        return OrderIntent.new(
            desk_id=f"book-{self.name}"[:60],
            instrument=intent.instrument,
            side=intent.side,
            quantity=intent.quantity if quantity is None else quantity,
            order_type=intent.order_type,
            limit_price=intent.limit_price,
            time_in_force=intent.time_in_force,
            rationale=intent.reason,
            created_at=intent.created_at,
            nonce=nonce or intent.id,
            post_only=intent.post_only,
            expires_at=intent.expires_at,
        )

    def _day_pnl(self, agent: str, now: str) -> Decimal:
        day = now[:10]
        equity = self.equity(agent)
        opened = self.day_open.get(agent)
        if opened is None or opened[0] != day:
            self.day_open[agent] = (day, equity)
            return ZERO
        return equity - opened[1]

    def check(self, intent: Intent, quote: Quote | None, now: str) -> list[str]:
        """Every reason this intent may not trade. Empty means it may."""
        reasons: list[str] = []
        limits = self.limits.get(intent.agent)
        if limits is None:
            return [f"{intent.agent} has no seat on the {self.name} book"]
        if intent.instrument.venue != self.broker.venue:
            return [f"instrument venue {intent.instrument.venue!r} is not this book's {self.broker.venue!r}"]
        try:
            order_intent = self._order_intent(intent)
        except (ValueError, ArithmeticError) as exc:
            return [f"malformed intent: {exc}"]
        account = self._account(intent.agent)
        reducing = intent.side == "sell"
        if self.frozen and not reducing:
            reasons.append(f"the {self.name} book is frozen until it reconciles: {self.frozen}")
        step = step_of(intent.instrument, intent.order_type)
        if (intent.quantity / step) % 1 != 0:
            reasons.append(f"quantity {intent.quantity} is not a multiple of {step}")
        positions = {
            key: Position(h.instrument, h.quantity, h.average_cost, self.marks.get(key))
            for key, h in account.holdings.items()
        }
        capabilities = set(self.broker.capabilities()) - {"short"}  # the live account cannot short
        equity = self.equity(intent.agent)
        floor_equity = self.total_equity()
        ctx = RiskContext(
            manifest=self._manifest(intent.agent, limits),
            desk_equity=equity,
            desk_cash=account.cash - self._reserved_cash(intent.agent),
            positions=positions,
            quote=quote,
            now=now,
            desk_daily_pnl=self._day_pnl(intent.agent, now),
            desk_orders_today=self.orders_today.get((intent.agent, now[:10]), 0),
            floor_equity=floor_equity,
            floor_daily_pnl=sum((self._day_pnl(a, now) for a in list(self.accounts)), ZERO),
            floor_max_daily_loss_pct=money(self.rules["floor_max_daily_loss_pct"]),
            kill_switch=bool(self.kill_switch and self.kill_switch()),
            market_open=self.market_open(intent.instrument, now) if self.market_open else None,
            adv_usd=None,
            open_orders=len(self.open_orders(intent.agent)),
            venue_capabilities=capabilities,
            working_sells=self._reserved_sells(intent.agent),
            working_event_buys=self._working_event_buys(intent.agent),
            min_event_price=money(self.rules["min_event_price"]),
            max_event_market_pct=money(self.rules["max_event_market_pct"]),
            max_event_market_floor_pct=money(self.rules["max_event_market_floor_pct"]),
            max_event_cluster_floor_pct=money(self.rules["max_event_cluster_floor_pct"]),
            floor_event_exposure=self._event_exposure(),
        )
        decision = self.engine.check(order_intent, ctx)
        reasons.extend(decision.reasons)
        # The league's own rules.
        reference = decision.reference_price
        notional = decision.notional
        if notional is None and reference is not None:
            notional = intent.quantity * reference * intent.instrument.multiplier
        if quote is not None and not reducing:
            age = _age_seconds(quote.as_of, now)
            if age is not None and age > int(self.rules["max_quote_age_seconds"]):
                reasons.append(f"the quote is {int(age)}s old")
        if notional is not None and intent.side == "buy" and reference is not None:
            # No leverage, to the cent: the fee and a market order's slippage must be covered too.
            charge = self.fees.charge(intent.instrument, "buy", intent.quantity, reference)
            slack = notional * money(self.rules["market_slippage_pct"]) if intent.order_type == "market" else ZERO
            need = notional + charge.usd + slack
            if need > ctx.desk_cash:
                reasons.append(f"needs ${need:.2f} with fees; free cash is ${ctx.desk_cash:.2f}")
        if notional is not None and not reducing:
            if notional > money(self.rules["max_order_usd"]):
                reasons.append(f"order of ${notional:.2f} is over the ${self.rules['max_order_usd']} order cap")
            if notional > limits.max_order_usd:
                reasons.append(f"order of ${notional:.2f} is over this rung's ${limits.max_order_usd} an order")
            held = account.holdings.get(intent.instrument.key)
            held_value = (held.quantity * reference * intent.instrument.multiplier) if held and reference else ZERO
            if held_value + notional > limits.max_position_usd:
                reasons.append(
                    f"position of ${held_value + notional:.2f} would be over this rung's ${limits.max_position_usd}"
                )
        crossing = self._would_cross_own(intent, quote)
        if crossing:
            reasons.append(crossing)
        return reasons

    def _would_cross_own(self, intent: Intent, quote: Quote | None) -> str | None:
        """An order that could execute against one of the House's own resting orders is refused."""
        side, price = yes_space(intent.instrument, intent.side, intent.limit_price)
        key = market_key(intent.instrument)
        for working in self.orders.values():
            if not working.open or market_key(working.instrument) != key:
                continue
            other_side, other_price = yes_space(working.instrument, working.side, working.limit_price)
            if other_side == side:
                continue
            if price is None or other_price is None:
                return "a market order here could trade against the House's own resting order"
            if (side == "buy" and price >= other_price) or (side == "sell" and price <= other_price):
                return "this price would trade against the House's own resting order; re-price or wait"
        return None

    # ------------------------------------------------------------------ submit
    def submit(self, intents: Iterable[Intent]) -> list[Outcome]:
        """Take one batch of intents: record, check, net the market orders, route, attribute."""
        outcomes: list[Outcome] = []
        with self._lock:
            now = now_iso(self.clock)
            market_groups: dict[str, list[tuple[Intent, Quote]]] = {}
            for intent in intents:
                if intent.id in self.seen_intents:
                    outcomes.append(Outcome(intent.id, intent.agent, "duplicate", "already recorded"))
                    continue
                entry = self.ledger.append(
                    "agent.intent", {"book": self.name, **intent.to_dict()}, agent=intent.agent, id=f"intent:{intent.id}"
                )
                self._apply(entry.kind, intent.agent, entry.payload, entry.at)
                quote = self._quote(intent.instrument)
                reasons = self.check(intent, quote, now)
                if reasons:
                    outcomes.append(self._refuse(intent, reasons))
                    continue
                if intent.order_type == "market":
                    if quote is None or quote.bid is None or quote.ask is None or quote.bid <= 0:
                        outcomes.append(self._refuse(intent, ["no two-sided quote to price a market order against"]))
                        continue
                    market_groups.setdefault(intent.instrument.key, []).append((intent, quote))
                else:
                    outcomes.append(self._route([intent], [intent.quantity], now))
            for group in market_groups.values():
                outcomes.extend(self._net(group, now))
        return outcomes

    def _refuse(self, intent: Intent, reasons: Sequence[str]) -> Outcome:
        self.ledger.append(
            "book.refused",
            {"book": self.name, "intent_id": intent.id, "reasons": list(reasons), "instrument": intent.instrument.to_dict()},
            agent=intent.agent,
            id=f"refused:{intent.id}",
        )
        return Outcome(intent.id, intent.agent, "refused", "; ".join(reasons))

    def _quote(self, instrument: Instrument) -> Quote | None:
        try:
            quote = self.broker.quote(instrument)
        except Exception:  # noqa: BLE001 - a venue that cannot quote is a refusal, not a crash
            return None
        if quote is not None and quote.bid is not None and quote.bid > 0:
            self.marks[instrument.key] = quote.bid
        return quote

    def _net(self, group: list[tuple[Intent, Quote]], now: str) -> list[Outcome]:
        """Cross the opposite market orders of one instrument; send only the difference."""
        outcomes: list[Outcome] = []
        quote = group[-1][1]
        buys = [i for i, _ in group if i.side == "buy"]
        sells = [i for i, _ in group if i.side == "sell"]
        instrument = group[0][0].instrument
        step = step_of(instrument, "market")
        crossed = min(sum((i.quantity for i in buys), ZERO), sum((i.quantity for i in sells), ZERO))
        buy_cross = allocate(crossed, [i.quantity for i in buys], step)
        sell_cross = allocate(crossed, [i.quantity for i in sells], step)
        residual: dict[str, Decimal] = {}
        for intents, parts in ((buys, buy_cross), (sells, sell_cross)):
            for intent, part in zip(intents, parts):
                if part > 0:
                    self._cross(intent, part, quote, now)
                residual[intent.id] = intent.quantity - part
        for intents in (buys, sells):
            rest = [i for i in intents if residual[i.id] > 0]
            if rest:
                result = self._route(rest, [residual[i.id] for i in rest], now)
                for intent in rest:
                    outcomes.append(
                        Outcome(intent.id, intent.agent, result.status, result.detail, result.order_id, result.filled)
                    )
            for intent in intents:
                if residual[intent.id] <= 0:
                    outcomes.append(Outcome(intent.id, intent.agent, "crossed", "netted inside the House", None, intent.quantity))
        return outcomes

    def _cross(self, intent: Intent, quantity: Decimal, quote: Quote, now: str) -> None:
        """Fill part of a market order inside the House, priced as the venue would have."""
        price = quote.ask if intent.side == "buy" else quote.bid
        charge = self.fees.charge(intent.instrument, intent.side, quantity, price, liquidity="taker")
        self._book_fill(
            intent.agent,
            intent,
            quantity=quantity,
            price=price,
            charge=charge,
            source="cross",
            order_id=None,
            fill_id=f"cross:{intent.id}",
            at=now,
        )
        # What the account did not actually pay stays with the House: nothing went to the venue,
        # so the agents' cash moves must sum to zero with this row.
        multiplier = intent.instrument.multiplier
        if intent.side == "buy":
            house_cash = quantity * price * multiplier + charge.usd
            house_units = -(quantity - charge.quantity)
        else:
            house_cash = -(quantity * price * multiplier - charge.usd)
            house_units = quantity
        entry = self.ledger.append(
            "book.fill",
            {
                "book": self.name,
                "source": "cross-house",
                "intent_id": intent.id,
                "instrument": intent.instrument.to_dict(),
                "side": "sell" if intent.side == "buy" else "buy",
                "quantity": text(quantity),
                "price": text(price),
                "fee_usd": "0",
                "cash_delta": text(q_cash(house_cash)),
                "position_delta": text(house_units),
                "real_money": self.real_money,
            },
            agent=HOUSE,
            id=f"cross-house:{intent.id}",
        )
        self._apply(entry.kind, HOUSE, entry.payload, entry.at)

    def _apply_house(self, p: Mapping[str, Any]) -> None:
        """The House row carries balancing cash and units; its units net to dust, never a position
        it meant to take, so they are held without cost-basis bookkeeping."""
        account = self._account(HOUSE)
        account.cash += money(p["cash_delta"])
        delta = money(p["position_delta"])
        if delta != 0 and p.get("instrument"):
            instrument = Instrument.from_dict(p["instrument"])
            holding = account.holdings.get(instrument.key)
            if holding is None:
                holding = account.holdings[instrument.key] = Holding(instrument)
            holding.quantity += delta
            if holding.quantity == 0:
                del account.holdings[instrument.key]

    def _book_fill(
        self,
        agent: str,
        intent: Intent | None,
        *,
        quantity: Decimal,
        price: Decimal,
        charge: Charge,
        source: str,
        order_id: str | None,
        fill_id: str,
        at: str,
        instrument: Instrument | None = None,
        side: str | None = None,
        reason: str = "",
        intent_id: str | None = None,
        liquidity: str = "taker",
        venue_fee: Decimal = ZERO,
    ) -> None:
        instrument = instrument or intent.instrument
        side = side or intent.side
        multiplier = instrument.multiplier
        gross = quantity * price * multiplier
        if side == "buy":
            cash_delta = -(gross + charge.usd)
            position_delta = received(quantity, charge) if charge.quantity else quantity
        else:
            cash_delta = gross - charge.usd
            position_delta = -quantity
        payload = {
            "book": self.name,
            "source": source,
            "order_id": order_id,
            "intent_id": intent_id or (intent.id if intent else None),
            "instrument": instrument.to_dict(),
            "side": side,
            "quantity": text(quantity),
            "price": text(price),
            "fee_usd": text(charge.usd),
            "fee_quantity": text(charge.quantity),
            "venue_fee": text(venue_fee),
            "liquidity": liquidity,
            "cash_delta": text(q_cash(cash_delta)),
            "position_delta": text(position_delta),
            "reason": reason or (intent.reason if intent else ""),
            "real_money": self.real_money,
        }
        entry = self.ledger.append("book.fill", payload, agent=agent, id=fill_id, at=at)
        self._apply(entry.kind, agent, entry.payload, entry.at)

    def _route(self, intents: Sequence[Intent], quantities: Sequence[Decimal], now: str) -> Outcome:
        """Send one venue order for these intents' quantities, then attribute what filled at once."""
        first = intents[0]
        total = sum(quantities, ZERO)
        nonce = hashlib.sha256("|".join(sorted(i.id for i in intents)).encode()).hexdigest()[:24]
        order_intent = self._order_intent(first, quantity=total, nonce=nonce)
        order_id = "ord-" + order_intent.id[3:]
        shares = [Share(i.id, i.agent, q, i.reason) for i, q in zip(intents, quantities)]
        base = {
            "book": self.name,
            "order_id": order_id,
            "instrument": first.instrument.to_dict(),
            "side": first.side,
            "quantity": text(total),
            "order_type": first.order_type,
            "limit_price": text(first.limit_price),
            "post_only": first.post_only,
            "shares": [{"intent_id": s.intent_id, "agent": s.agent, "quantity": text(s.quantity), "reason": s.reason} for s in shares],
            "submitted_at": now,
            "liquidity": self._liquidity(first),
            "real_money": self.real_money,
        }
        # The order is on the ledger before it is on the wire: a crash between the two leaves an
        # `unknown` order the next poll resolves by its client id, never an order nobody recorded.
        self._order_row(base, "new", None, suffix="new")
        try:
            order = self.broker.submit(order_intent)
        except UnknownOutcome as exc:
            self._order_row(base, "unknown", None, suffix="unknown", reason=str(exc))
            return Outcome(first.id, first.agent, "unknown", str(exc), order_id)
        except (RejectedOrder, BrokerError, ValueError) as exc:
            self._order_row(base, "rejected", None, suffix="rejected", reason=str(exc))
            return Outcome(first.id, first.agent, "rejected", str(exc), order_id)
        self._order_row(base, order.status, order.broker_order_id, suffix=f"sent:{order.status}")
        working = self.orders[order_id]
        self._attribute(working, order, now)
        if working.open and not working.rested:
            self._order_row(base, working.status, working.broker_order_id, suffix="rested", rested=True)
        if working.filled >= working.quantity:
            status = "filled"
        elif working.filled > 0:
            status = "partial"
        elif working.open:
            # Alpaca accepts every order first and fills it a moment later: the next poll has it.
            status = "resting" if first.order_type == "limit" else "sent"
        else:
            status = working.status
        return Outcome(first.id, first.agent, status, order.reason or "", order_id, working.filled)

    def _liquidity(self, intent: Intent) -> str:
        """A market order takes. A limit order makes unless it crossed the touch when it was sent
        (Alpaca accepts every order asynchronously, so "it was still open" says nothing)."""
        if intent.order_type == "market":
            return "taker"
        if intent.post_only:
            return "maker"
        quote = self._quote(intent.instrument)
        if quote is None or intent.limit_price is None:
            return "taker"
        if intent.side == "buy":
            return "taker" if quote.ask is not None and intent.limit_price >= quote.ask else "maker"
        return "taker" if quote.bid is not None and intent.limit_price <= quote.bid else "maker"

    def _order_row(self, base: Mapping[str, Any], status: str, broker_order_id: str | None, *, suffix: str, reason: str = "", rested: bool | None = None) -> None:
        payload = {**base, "status": status, "broker_order_id": broker_order_id, "reason": reason}
        if rested is not None:
            payload["rested"] = rested
        entry = self.ledger.append("book.order", payload, id=f"order:{base['order_id']}:{suffix}")
        self._apply(entry.kind, HOUSE, entry.payload, entry.at)

    def _base_of(self, working: Working) -> dict[str, Any]:
        return {
            "book": self.name,
            "order_id": working.order_id,
            "instrument": working.instrument.to_dict(),
            "side": working.side,
            "quantity": text(working.quantity),
            "order_type": working.order_type,
            "limit_price": text(working.limit_price),
            "post_only": working.post_only,
            "shares": [{"intent_id": s.intent_id, "agent": s.agent, "quantity": text(s.quantity), "reason": s.reason} for s in working.shares],
            "submitted_at": working.submitted_at,
            "liquidity": working.liquidity,
            "real_money": self.real_money,
        }

    def _attribute(self, working: Working, order: Order, now: str) -> None:
        """Give each intent behind an order its part of what the venue has filled since last time."""
        filled = money(order.filled_quantity)
        delta = filled - working.filled
        if delta > 0 and order.average_price is not None:
            total_notional = money(order.average_price) * filled
            price = (total_notional - working.notional) / delta
            venue_fees = money(order.fees or 0)
            fee_delta = max(venue_fees - working.fees_seen, ZERO)
            liquidity = working.liquidity
            step = step_of(working.instrument, working.order_type)
            rooms = [s.quantity - s.filled for s in working.shares]
            parts = allocate(delta, rooms, step)
            fee_parts = _split_cash(fee_delta, parts)
            before = working.filled
            for share, part, venue_fee in zip(list(working.shares), parts, fee_parts):
                if part <= 0:
                    continue
                if self.fees.family == "kalshi" and self.real_money:
                    charge = Charge(usd=venue_fee)  # the venue's own number
                else:
                    charge = self.fees.charge(
                        working.instrument, working.side, part, price, liquidity=liquidity, filled_before=before
                    )
                self._book_fill(
                    share.agent,
                    None,
                    quantity=part,
                    price=price,
                    charge=charge,
                    source="venue",
                    order_id=working.order_id,
                    fill_id=f"fill:{working.order_id}:{share.intent_id}:{text(share.filled + part)}",
                    at=now,
                    instrument=working.instrument,
                    side=working.side,
                    reason=share.reason,
                    intent_id=share.intent_id,
                    liquidity=liquidity,
                    venue_fee=venue_fee,
                )
                before += part
        if order.status != working.status:
            self._order_row(self._base_of(working), order.status, order.broker_order_id or working.broker_order_id, suffix=f"{order.status}:{text(filled)}")

    # -------------------------------------------------------------------- poll
    def poll(self) -> int:
        """Ask the venue about every open order and attribute new fills. Returns orders checked."""
        checked = 0
        with self._lock:
            now = now_iso(self.clock)
            for working in list(self.orders.values()):
                if not working.open:
                    continue
                try:
                    order = self.broker.get_order(working.broker_order_id or working.order_id)
                except RejectedOrder:
                    if working.status in ("new", "unknown"):
                        # The venue has no such order: the submit never arrived.
                        self._order_row(self._base_of(working), "rejected", None, suffix="never-arrived", reason="the venue has no such order")
                    continue
                except BrokerError:
                    continue
                checked += 1
                self._attribute(working, order, now)
        return checked

    def cancel(self, agent: str, order_id: str) -> Outcome:
        with self._lock:
            working = self.orders.get(order_id)
            if working is None or not any(s.agent == agent for s in working.shares):
                return Outcome("", agent, "refused", "no such order of yours", order_id)
            if not working.open:
                return Outcome("", agent, "refused", f"order is already {working.status}", order_id)
            now = now_iso(self.clock)
            try:
                order = self.broker.cancel(working.broker_order_id or working.order_id)
            except BrokerError as exc:
                return Outcome("", agent, "rejected", str(exc), order_id)
            self.ledger.append("book.cancel", {"book": self.name, "order_id": order_id}, agent=agent, id=f"cancel:{order_id}")
            self._attribute(working, order, now)
            return Outcome("", agent, working.status, "", order_id, working.filled)

    def cancel_all(self, agent: str) -> int:
        return sum(1 for w in self.open_orders(agent) if self.cancel(agent, w.order_id).status == "cancelled")

    # ------------------------------------------------------------------ settle
    def settle(self, market_id: str, result: str, *, at: str | None = None) -> int:
        """A Kalshi market resolved: every holding of it pays $1 or $0 a contract."""
        result = str(result).lower()
        if result not in ("yes", "no"):
            raise BookError(f"settlement result must be yes or no, not {result!r}")
        settled = 0
        with self._lock:
            for agent, account in list(self.accounts.items()):
                for key, holding in list(account.holdings.items()):
                    inst = holding.instrument
                    if inst.asset_class != "event" or (inst.market_id or inst.symbol).upper() != market_id.upper():
                        continue
                    wins = (inst.right or "yes") == result
                    payout = holding.quantity * inst.multiplier if wins else ZERO
                    payload = {
                        "book": self.name,
                        "instrument": inst.to_dict(),
                        "result": result,
                        "quantity": text(holding.quantity),
                        "cost": text(q_cash(holding.cost)),
                        "payout": text(q_cash(payout)),
                        "pnl": text(q_cash(payout - holding.cost)),
                        "reason": holding.reason,
                        "opened_at": holding.opened_at,
                        "real_money": self.real_money,
                    }
                    entry = self.ledger.append("book.settle", payload, agent=agent, id=f"settle:{self.name}:{agent}:{key}", at=at)
                    self._apply(entry.kind, agent, entry.payload, entry.at)
                    self.marks.pop(key, None)
                    settled += 1
        return settled

    # -------------------------------------------------------------------- mark
    def mark(self) -> dict[str, Decimal]:
        """Re-quote every held instrument and record each agent's equity. Returns agent -> equity."""
        with self._lock:
            now = now_iso(self.clock)
            held: dict[str, Instrument] = {}
            for account in self.accounts.values():
                for key, holding in account.holdings.items():
                    held[key] = holding.instrument
            for instrument in held.values():
                self._quote(instrument)
            out: dict[str, Decimal] = {}
            for agent in self.agents():
                account = self._account(agent)
                equity = self.equity(agent)
                out[agent] = equity
                self.ledger.append(
                    "book.mark",
                    {
                        "book": self.name,
                        "equity": text(q_cash(equity)),
                        "cash": text(q_cash(account.cash)),
                        "staked": text(account.staked),
                        "realized": text(q_cash(account.realized)),
                        "fees": text(q_cash(account.fees)),
                        "holdings": len(account.holdings),
                        "real_money": self.real_money,
                    },
                    agent=agent,
                    at=now,
                )
            return out

    # --------------------------------------------------------------- reconcile
    def _venue(self) -> tuple[Decimal, dict[str, Decimal]]:
        balance = self.broker.balance()
        positions: dict[str, Decimal] = {}
        for position in self.broker.positions():
            key = position_key(position.instrument)
            positions[key] = positions.get(key, ZERO) + money(position.quantity)
        return money(balance.cash), positions

    def _ledger_totals(self) -> tuple[Decimal, dict[str, Decimal], dict[str, Instrument]]:
        """The book's own cash (profit and loss, fees, dust: stakes are slices, not deposits) and
        its positions, summed over every agent and the House row."""
        cash = sum((a.cash - a.staked for a in self.accounts.values()), ZERO)
        positions: dict[str, Decimal] = {}
        instruments: dict[str, Instrument] = {}
        for account in self.accounts.values():
            for holding in account.holdings.values():
                key = position_key(holding.instrument)
                positions[key] = positions.get(key, ZERO) + holding.quantity
                instruments[key] = holding.instrument
        return cash, positions, instruments

    def open_baseline(self) -> None:
        """Record, once, what the venue account holds that is not the book's. Everything the
        venue shows beyond this baseline must be explained by the ledger, to the cent."""
        with self._lock:
            if self.baseline_cash is not None:
                return
            venue_cash, venue_positions = self._venue()
            cash, positions, _ = self._ledger_totals()
            baseline = {
                key: venue_positions.get(key, ZERO) - positions.get(key, ZERO)
                for key in set(venue_positions) | set(positions)
            }
            self._baseline_row(venue_cash - cash, {k: v for k, v in baseline.items() if v != 0}, "opened")
            self.venue_cash = venue_cash

    def adjust_baseline(self, cash_delta: Any, note: str) -> None:
        """The owner moved money (a deposit or a withdrawal the venue's own record confirms)."""
        with self._lock:
            if self.baseline_cash is None:
                raise BookError(f"{self.name} has no baseline yet")
            self._baseline_row(self.baseline_cash + money(cash_delta), self.baseline_positions, note)

    def _baseline_row(self, cash: Decimal, positions: Mapping[str, Decimal], note: str) -> None:
        entry = self.ledger.append(
            "book.baseline",
            {"book": self.name, "cash": text(q_cash(cash)), "positions": {k: text(v) for k, v in positions.items()}, "note": note},
        )
        self._apply(entry.kind, HOUSE, entry.payload, entry.at)

    def _position_dust(self, instrument: Instrument, diff: Decimal) -> None:
        """The venue rounds an in-kind fee its own way. Under a cent of value, the ledger takes the
        venue's number: a shortfall comes off the largest holder (so its sell-all is a quantity the
        venue really has), a surplus goes to the House row."""
        agent = HOUSE
        if diff < 0:
            holders = [
                (account.holdings[instrument.key].quantity, name)
                for name, account in self.accounts.items()
                if instrument.key in account.holdings and account.holdings[instrument.key].quantity >= -diff
            ]
            if holders:
                agent = max(holders)[1]
        entry = self.ledger.append(
            "book.fill",
            {
                "book": self.name,
                "source": "dust",
                "instrument": instrument.to_dict(),
                "side": "sell" if diff < 0 else "buy",
                "quantity": text(abs(diff)),
                "price": "0",
                "fee_usd": "0",
                "cash_delta": "0",
                "position_delta": text(diff),
                "real_money": self.real_money,
            },
            agent=agent,
        )
        self._apply(entry.kind, agent, entry.payload, entry.at)

    def reconcile(self) -> Reconciliation:
        """Compare the book to the venue: venue cash must equal the baseline plus the book's own
        cash, and every venue position the baseline's plus the agents'. A difference under a cent
        is booked to the House row as dust; anything larger freezes new entries until it clears."""
        with self._lock:
            self.open_baseline()
            venue_cash, venue_positions = self._venue()
            self.venue_cash = venue_cash
            cash, positions, instruments = self._ledger_totals()
            # A baseline position the venue no longer shows has settled or been closed by the
            # owner: it leaves the baseline, and the cash it paid (at most $1 a contract for an
            # event contract) joins the baseline with it.
            for key, held in list(self.baseline_positions.items()):
                if key not in venue_positions and key not in positions and key.startswith("event:"):
                    paid = venue_cash - (self.baseline_cash + cash)
                    if ZERO <= paid <= abs(held) + DUST_USD:
                        remaining = {k: v for k, v in self.baseline_positions.items() if k != key}
                        self._baseline_row(self.baseline_cash + paid, remaining, f"baseline position {key} settled")
            expected = self.baseline_cash + cash
            cash_diff = venue_cash - expected
            diffs: dict[str, str] = {}
            for key in sorted(set(venue_positions) | set(positions) | set(self.baseline_positions)):
                diff = venue_positions.get(key, ZERO) - positions.get(key, ZERO) - self.baseline_positions.get(key, ZERO)
                if diff == 0:
                    continue
                instrument = instruments.get(key)
                mark = self.marks.get(instrument.key) if instrument is not None else None
                if instrument is None or mark is None or abs(diff) * mark * instrument.multiplier >= DUST_USD:
                    diffs[key] = text(diff)
                else:
                    self._position_dust(instrument, diff)
            pending = any(w.status in ("new", "unknown") for w in self.orders.values())
            # A venue shows cash to the cent and rounds each fill's fee its own way: allow a cent
            # of drift for each venue fill since the last reconciliation, and book it as dust.
            tolerance = DUST_USD * max(1, self._fills_since_reconcile)
            ok = abs(cash_diff) < tolerance and not diffs and not pending
            problems = []
            if abs(cash_diff) >= tolerance:
                problems.append(f"cash differs by {cash_diff:.4f}")
            if diffs:
                problems.append("positions differ: " + ", ".join(f"{k} {v}" for k, v in diffs.items()))
            if pending:
                problems.append("an order's outcome is unknown")
            detail = "; ".join(problems)
            dust = ZERO
            if ok and q_cash(cash_diff) != 0:
                dust = q_cash(cash_diff)
                entry = self.ledger.append(
                    "book.fill",
                    {
                        "book": self.name,
                        "source": "dust",
                        "instrument": None,
                        "quantity": "0",
                        "price": "0",
                        "fee_usd": "0",
                        "cash_delta": text(dust),
                        "position_delta": "0",
                        "real_money": self.real_money,
                    },
                    agent=HOUSE,
                )
                self._apply(entry.kind, HOUSE, entry.payload, entry.at)
            self.frozen = None if ok else detail
            if ok:
                self._fills_since_reconcile = 0
            head_seq, head_digest = self.ledger.head()
            self.ledger.append(
                "book.reconciled",
                {
                    "book": self.name,
                    "ok": ok,
                    "cash_venue": text(venue_cash),
                    "cash_expected": text(q_cash(expected)),
                    "cash_diff": text(q_cash(cash_diff)),
                    "position_diffs": diffs,
                    "dust_booked": text(dust),
                    "detail": detail,
                    "ledger_seq": head_seq,
                    "ledger_digest": head_digest,
                    "real_money": self.real_money,
                },
            )
            return Reconciliation(ok, venue_cash, q_cash(expected), q_cash(cash_diff), diffs, dust, detail)


def _split_cash(total: Decimal, parts: Sequence[Decimal]) -> list[Decimal]:
    """Split a venue-reported fee across the parts of a fill, to $0.0001, summing exactly."""
    whole = sum(parts, ZERO)
    if total <= 0 or whole <= 0:
        return [ZERO for _ in parts]
    grid = Decimal("0.0001")
    out = [(total * p / whole).quantize(grid, rounding=ROUND_DOWN) for p in parts]
    left = total - sum(out, ZERO)
    for i in sorted(range(len(parts)), key=lambda i: -parts[i]):
        if left <= 0:
            break
        if parts[i] > 0:
            out[i] += left
            left = ZERO
    return out


def _age_seconds(as_of: str, now: str) -> float | None:
    from ltcm.broker import instant

    a, b = instant(as_of), instant(now)
    if a is None or b is None:
        return None
    return (b - a).total_seconds()
