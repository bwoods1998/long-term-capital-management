"""Venue-neutral trading contracts.

Every live adapter and the shadow book implement the `Broker` protocol. Desks never see a broker:
they emit `OrderIntent`s, the risk engine decides, and the gateway routes approved intents -- to
the venue named on the instrument for a live desk, and to the shadow book for a shadow one.

Money and quantities are `Decimal`. Serialized forms use strings. Nothing here performs I/O.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field, asdict
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol, runtime_checkable

ASSET_CLASSES = ("equity", "option", "crypto", "future", "event")
SIDES = ("buy", "sell")
ORDER_TYPES = ("market", "limit")
TIME_IN_FORCE = ("day", "gtc", "ioc")
ORDER_STATUSES = (
    "new",  # created locally, not yet sent
    "accepted",  # venue acknowledged
    "partially_filled",
    "filled",
    "cancelled",
    "rejected",
    "expired",
    "unknown",  # submission outcome could not be confirmed; reconcile before retrying
)
TERMINAL_STATUSES = ("filled", "cancelled", "rejected", "expired")

MONEY_PLACES = Decimal("0.00000001")


class BrokerError(RuntimeError):
    """Base class for venue failures."""


class RejectedOrder(BrokerError):
    """The venue refused the order."""


class UnknownOutcome(BrokerError):
    """The venue may or may not have accepted the order. Reconcile, never retry blindly."""


class VenueUnavailable(BrokerError):
    """Transport or authentication failure before submission."""


def money(value: Any) -> Decimal:
    """Parse a price or quantity strictly: finite, from str/int/Decimal, never float."""
    if isinstance(value, bool) or isinstance(value, float):
        raise ValueError(f"floats and bools are not money: {value!r}")
    try:
        result = Decimal(str(value)) if not isinstance(value, Decimal) else value
    except InvalidOperation as exc:
        raise ValueError(f"not a decimal: {value!r}") from exc
    if not result.is_finite():
        raise ValueError(f"not finite: {value!r}")
    return result


def text(value: Decimal | None) -> str | None:
    return None if value is None else format(value, "f")


@dataclass(frozen=True)
class Instrument:
    asset_class: str
    symbol: str
    venue: str
    multiplier: Decimal = Decimal(1)
    expiry: str | None = None  # YYYY-MM-DD for options/futures
    strike: Decimal | None = None
    right: str | None = None  # "call" | "put"
    market_id: str | None = None  # event contracts (Kalshi ticker), crypto pair ids
    currency: str = "USD"

    def __post_init__(self):
        if self.asset_class not in ASSET_CLASSES:
            raise ValueError(f"unknown asset class {self.asset_class!r}")
        if not isinstance(self.symbol, str) or not 1 <= len(self.symbol) <= 40:
            raise ValueError("invalid symbol")
        if not isinstance(self.venue, str) or not 1 <= len(self.venue) <= 30:
            raise ValueError("invalid venue")
        object.__setattr__(self, "multiplier", money(self.multiplier))
        if self.multiplier <= 0:
            raise ValueError("multiplier must be positive")
        if self.asset_class == "option":
            if not (self.expiry and self.strike is not None and self.right in ("call", "put")):
                raise ValueError("options need expiry, strike and right")
            object.__setattr__(self, "strike", money(self.strike))
        if self.asset_class == "event" and not self.market_id:
            raise ValueError("event contracts need a market_id")

    @property
    def key(self) -> str:
        parts = [self.asset_class, self.symbol, self.venue]
        if self.expiry:
            parts.append(self.expiry)
        if self.strike is not None:
            parts.append(format(self.strike, "f"))
        if self.right:
            parts.append(self.right)
        if self.market_id:
            parts.append(self.market_id)
        return ":".join(parts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset_class": self.asset_class,
            "symbol": self.symbol,
            "venue": self.venue,
            "multiplier": text(self.multiplier),
            "expiry": self.expiry,
            "strike": text(self.strike),
            "right": self.right,
            "market_id": self.market_id,
            "currency": self.currency,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Instrument":
        return cls(
            asset_class=data["asset_class"],
            symbol=data["symbol"],
            venue=data["venue"],
            multiplier=money(data.get("multiplier", "1")),
            expiry=data.get("expiry"),
            strike=money(data["strike"]) if data.get("strike") is not None else None,
            right=data.get("right"),
            market_id=data.get("market_id"),
            currency=data.get("currency", "USD"),
        )


@dataclass(frozen=True)
class Quote:
    instrument: Instrument
    bid: Decimal | None
    ask: Decimal | None
    last: Decimal | None
    as_of: str  # ISO timestamp of the observation
    source: str  # e.g. "alpaca:iex", "yahoo:delayed", "kalshi", "sim"
    delayed: bool = True

    @property
    def mid(self) -> Decimal | None:
        if self.bid is not None and self.ask is not None and self.bid > 0 and self.ask > 0:
            return (self.bid + self.ask) / 2
        return self.last

    def reference(self, side: str) -> Decimal | None:
        """Price a taker would pay: ask for buys, bid for sells, else last, else mid."""
        if side == "buy" and self.ask:
            return self.ask
        if side == "sell" and self.bid:
            return self.bid
        return self.last if self.last is not None else self.mid

    def to_dict(self) -> dict[str, Any]:
        return {
            "instrument": self.instrument.to_dict(),
            "bid": text(self.bid),
            "ask": text(self.ask),
            "last": text(self.last),
            "as_of": self.as_of,
            "source": self.source,
            "delayed": self.delayed,
        }


@dataclass(frozen=True)
class OrderIntent:
    """What a desk wants. Immutable; identity is derived so retries are safe."""

    id: str
    desk_id: str
    instrument: Instrument
    side: str
    quantity: Decimal
    order_type: str
    limit_price: Decimal | None
    time_in_force: str
    rationale: str
    created_at: str
    session_id: str | None = None

    def __post_init__(self):
        if self.side not in SIDES:
            raise ValueError("side must be buy or sell")
        if self.order_type not in ORDER_TYPES:
            raise ValueError("order_type must be market or limit")
        if self.time_in_force not in TIME_IN_FORCE:
            raise ValueError("time_in_force must be day, gtc or ioc")
        object.__setattr__(self, "quantity", money(self.quantity))
        if self.quantity <= 0:
            raise ValueError("quantity must be positive")
        if self.order_type == "limit":
            if self.limit_price is None:
                raise ValueError("limit orders need a limit_price")
            object.__setattr__(self, "limit_price", money(self.limit_price))
            if self.limit_price <= 0:
                raise ValueError("limit_price must be positive")
        elif self.limit_price is not None:
            raise ValueError("market orders cannot carry a limit_price")
        if not isinstance(self.rationale, str) or not 1 <= len(self.rationale) <= 2000:
            raise ValueError("rationale must be 1-2000 characters")
        if not isinstance(self.desk_id, str) or not self.desk_id:
            raise ValueError("desk_id required")

    @classmethod
    def new(
        cls,
        *,
        desk_id: str,
        instrument: Instrument,
        side: str,
        quantity: Any,
        order_type: str = "market",
        limit_price: Any = None,
        time_in_force: str = "day",
        rationale: str,
        created_at: str,
        session_id: str | None = None,
        nonce: str | None = None,
    ) -> "OrderIntent":
        """Derive a stable id from the desk, session, instrument, side and nonce.

        Two identical proposals within one session collapse to one intent, which is what we
        want when a model repeats itself after a transport retry.
        """
        material = "|".join(
            [
                desk_id,
                session_id or "",
                instrument.key,
                side,
                format(money(quantity), "f"),
                order_type,
                format(money(limit_price), "f") if limit_price is not None else "",
                nonce or "",
            ]
        )
        intent_id = "oi-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]
        return cls(
            id=intent_id,
            desk_id=desk_id,
            instrument=instrument,
            side=side,
            quantity=money(quantity),
            order_type=order_type,
            limit_price=money(limit_price) if limit_price is not None else None,
            time_in_force=time_in_force,
            rationale=rationale,
            created_at=created_at,
            session_id=session_id,
        )

    @property
    def notional_hint(self) -> Decimal | None:
        """Limit notional when known; market orders are priced by the risk engine's quote."""
        if self.limit_price is None:
            return None
        return self.quantity * self.limit_price * self.instrument.multiplier

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "desk_id": self.desk_id,
            "instrument": self.instrument.to_dict(),
            "side": self.side,
            "quantity": text(self.quantity),
            "order_type": self.order_type,
            "limit_price": text(self.limit_price),
            "time_in_force": self.time_in_force,
            "rationale": self.rationale,
            "created_at": self.created_at,
            "session_id": self.session_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "OrderIntent":
        return cls(
            id=data["id"],
            desk_id=data["desk_id"],
            instrument=Instrument.from_dict(data["instrument"]),
            side=data["side"],
            quantity=money(data["quantity"]),
            order_type=data["order_type"],
            limit_price=money(data["limit_price"]) if data.get("limit_price") is not None else None,
            time_in_force=data["time_in_force"],
            rationale=data["rationale"],
            created_at=data["created_at"],
            session_id=data.get("session_id"),
        )


@dataclass
class Order:
    id: str  # internal order id, derived from the intent: "ord-" + intent id suffix
    intent_id: str
    desk_id: str
    instrument: Instrument
    side: str
    quantity: Decimal
    order_type: str
    limit_price: Decimal | None
    time_in_force: str
    status: str
    venue: str
    broker_order_id: str | None = None
    filled_quantity: Decimal = Decimal(0)
    average_price: Decimal | None = None
    fees: Decimal = Decimal(0)
    submitted_at: str | None = None
    updated_at: str | None = None
    reason: str | None = None  # rejection or cancellation reason
    _raw: dict[str, Any] = field(default_factory=dict, repr=False)

    def __post_init__(self):
        if self.status not in ORDER_STATUSES:
            raise ValueError(f"unknown order status {self.status!r}")
        self.quantity = money(self.quantity)
        self.filled_quantity = money(self.filled_quantity)
        self.fees = money(self.fees)
        if self.average_price is not None:
            self.average_price = money(self.average_price)
        if self.limit_price is not None:
            self.limit_price = money(self.limit_price)

    @property
    def terminal(self) -> bool:
        return self.status in TERMINAL_STATUSES

    @property
    def remaining(self) -> Decimal:
        return self.quantity - self.filled_quantity

    @classmethod
    def from_intent(cls, intent: OrderIntent, *, venue: str | None = None) -> "Order":
        return cls(
            id="ord-" + intent.id[3:],
            intent_id=intent.id,
            desk_id=intent.desk_id,
            instrument=intent.instrument,
            side=intent.side,
            quantity=intent.quantity,
            order_type=intent.order_type,
            limit_price=intent.limit_price,
            time_in_force=intent.time_in_force,
            status="new",
            venue=venue or intent.instrument.venue,
        )

    def to_dict(self, *, private: bool = False) -> dict[str, Any]:
        data = {
            "id": self.id,
            "intent_id": self.intent_id,
            "desk_id": self.desk_id,
            "instrument": self.instrument.to_dict(),
            "side": self.side,
            "quantity": text(self.quantity),
            "order_type": self.order_type,
            "limit_price": text(self.limit_price),
            "time_in_force": self.time_in_force,
            "status": self.status,
            "venue": self.venue,
            "broker_order_id": self.broker_order_id,
            "filled_quantity": text(self.filled_quantity),
            "average_price": text(self.average_price),
            "fees": text(self.fees),
            "submitted_at": self.submitted_at,
            "updated_at": self.updated_at,
            "reason": self.reason,
        }
        if private:
            data["_raw"] = self._raw
        return data


@dataclass(frozen=True)
class Fill:
    id: str
    order_id: str
    desk_id: str
    instrument: Instrument
    side: str
    quantity: Decimal
    price: Decimal
    fee: Decimal
    at: str

    def __post_init__(self):
        object.__setattr__(self, "quantity", money(self.quantity))
        object.__setattr__(self, "price", money(self.price))
        object.__setattr__(self, "fee", money(self.fee))
        if self.quantity <= 0 or self.price < 0 or self.fee < 0:
            raise ValueError("invalid fill amounts")

    @property
    def notional(self) -> Decimal:
        return self.quantity * self.price * self.instrument.multiplier

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "order_id": self.order_id,
            "desk_id": self.desk_id,
            "instrument": self.instrument.to_dict(),
            "side": self.side,
            "quantity": text(self.quantity),
            "price": text(self.price),
            "fee": text(self.fee),
            "at": self.at,
        }


@dataclass
class Position:
    instrument: Instrument
    quantity: Decimal  # negative for short
    average_cost: Decimal
    mark: Decimal | None = None
    as_of: str | None = None

    def __post_init__(self):
        self.quantity = money(self.quantity)
        self.average_cost = money(self.average_cost)
        if self.mark is not None:
            self.mark = money(self.mark)

    @property
    def market_value(self) -> Decimal | None:
        if self.mark is None:
            return None
        return self.quantity * self.mark * self.instrument.multiplier

    @property
    def cost_basis(self) -> Decimal:
        return self.quantity * self.average_cost * self.instrument.multiplier

    @property
    def unrealized_pnl(self) -> Decimal | None:
        value = self.market_value
        return None if value is None else value - self.cost_basis

    def to_dict(self) -> dict[str, Any]:
        return {
            "instrument": self.instrument.to_dict(),
            "quantity": text(self.quantity),
            "average_cost": text(self.average_cost),
            "mark": text(self.mark),
            "market_value": text(self.market_value),
            "unrealized_pnl": text(self.unrealized_pnl),
            "as_of": self.as_of,
        }


@dataclass(frozen=True)
class Balance:
    venue: str
    cash: Decimal
    equity: Decimal
    buying_power: Decimal
    as_of: str
    currency: str = "USD"

    def __post_init__(self):
        for name in ("cash", "equity", "buying_power"):
            object.__setattr__(self, name, money(getattr(self, name)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "venue": self.venue,
            "cash": text(self.cash),
            "equity": text(self.equity),
            "buying_power": text(self.buying_power),
            "as_of": self.as_of,
            "currency": self.currency,
        }


@runtime_checkable
class Broker(Protocol):
    """What every venue adapter provides. Implementations must be idempotent on order ids:
    submitting the same `OrderIntent` twice must not create two venue orders."""

    venue: str

    def capabilities(self) -> set[str]:
        """Subset of {"equity", "option", "crypto", "future", "event", "short", "fractional",
        "limit", "gtc", "ioc", "extended_hours", "shadow"}.

        `"shadow"` marks a book that scores orders instead of sending them; an adapter that
        reaches a real venue never claims it.
        """

    def balance(self) -> Balance: ...

    def positions(self) -> list[Position]: ...

    def quote(self, instrument: Instrument) -> Quote: ...

    def submit(self, intent: OrderIntent) -> Order:
        """Send the order. Raise RejectedOrder, VenueUnavailable or UnknownOutcome."""

    def cancel(self, order_id: str) -> Order: ...

    def get_order(self, order_id: str) -> Order: ...

    def open_orders(self) -> list[Order]: ...

    def fills(self, since: str | None = None) -> list[Fill]: ...


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4()}"


def as_dict(obj: Any) -> dict[str, Any]:
    """Dataclass to plain dict, for logging; prefer the explicit to_dict methods for wire use."""
    return asdict(obj)
