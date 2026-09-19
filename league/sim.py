"""A simulated Alpaca account: the venue a CANARY House trades on.

A release is tried out as a canary before it runs the floor (`league/watchdog.py`). The canary is
a whole House, and a House trades. It must never trade on the shared Alpaca paper account: the
real House reconciles that account to the cent, and a second trader on it would break the
reconciliation within one fill. So the canary's `alpaca-paper` book is given a `SimBroker`.

`SimBroker` is a `Broker` (`ltcm/broker.py`). It holds no credential and has no transport: the
only thing it reads from outside is `quotes(instrument) -> (bid, ask) | None`, which in
production is `touch_from(AlpacaData)` (live quotes through the gateway, read-only) and in a test
is a dictionary. `league.book.Book` drives it exactly as it drives the real adapter.

It behaves as the real paper venue was MEASURED to behave (`league/fees.py`, Sept 19, 2026, and
`league/tests/fakes.py`), not as one would assume:

1. An order is accepted first and filled a moment later. `submit` never fills: it answers
   `accepted` (or `rejected`), and the order's fate is decided on the next READ of it:
   `get_order`, `open_orders`, `cancel` (which reads first) or `advance()`.
2. A market order fills in full at the touch of that read: a buy at the ask, a sell at the bid,
   as a taker. With no two-sided quote at submission it is `rejected` ("no market"); with none at
   a later read it waits for the next one.
3. A limit order that crosses the touch the first time it is read (buy limit >= ask, sell limit
   <= bid) fills in full AT THE TOUCH as a taker; an immediate-or-cancel one that does not cross
   is `cancelled`. Otherwise it rests, and every later read checks it again: once the touch
   crosses it, it fills in full at ITS OWN price as a maker. A post-only order that would cross
   at submission is `rejected` ("post-only order would cross"); accepted, it is resting from
   that moment, because it can only ever make. A read with no two-sided quote decides nothing.
4. Fees are `league.fees.Fees("alpaca")`: on crypto the fee (0.25% taker, 0.15% maker) comes out
   of the coins on a buy and out of the proceeds, rounded up to the cent, on a sell. Equities
   pay nothing. Like the real adapter, `Order.fees` reports zero: the Book applies its own model,
   and what this account really took is kept on the order's private record and on the `Fill`.
5. Positions come back in Alpaca's spelling: an order for `BTC/USD` is a position in `BTCUSD`.
6. `submit` is idempotent on the intent id: the same intent again returns the stored order,
   whatever became of it, and nothing is accepted twice.
7. No leverage and no shorts at the account level (the Book checks each agent; this is the
   backstop): a buy needs free cash, a sell needs free units, and open orders hold theirs. What
   cannot be carried is `rejected` at submission, or `cancelled` if it cannot be carried when
   its fill comes.

NOT modelled: depth, partial fills, the trading day (a `day` order never expires here, and an
order is filled whatever the hour: the Book refuses equities outside market hours before they
get this far), options (no quote source; the capability is not claimed, so the risk engine
refuses them first) and short sales.

State (cash, positions, every order, every fill, the counters) is one JSON file, money as decimal
strings, rewritten atomically (temp file, fsync, `os.replace`, mode 0600) after every mutation
and loaded on construction. A write that fails takes the mutation back in memory and raises
`VenueUnavailable`. `starting_cash` only matters when the file does not exist yet. One lock
guards the account; quotes are read while it is held.
"""

from __future__ import annotations

import dataclasses
import json
import os
import threading
import time
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Optional, Tuple

from ltcm.broker import (
    Balance,
    BrokerError,
    Fill,
    Instrument,
    Order,
    OrderIntent,
    Position,
    Quote,
    RejectedOrder,
    VenueUnavailable,
    instant,
    money,
)

from .fees import QTY_PLACES, Fees, received
from .ledger import now_iso

ZERO = Decimal(0)
CASH_PLACES = Decimal("0.00000001")  # the Book's own grid, so the two agree to the last place
STATE_VERSION = 1
ASSET_CLASSES = ("equity", "crypto")
CAPABILITIES = frozenset({"equity", "crypto", "limit", "gtc", "ioc", "fractional", "shadow"})

Touch = Optional[Tuple[Decimal, Decimal]]
QuoteSource = Callable[[Instrument], Any]


def _text(value: Decimal | None) -> str | None:
    return None if value is None else format(value, "f")


def _price(value: Any) -> Decimal | None:
    """A price from a quote source, which may hand over floats (`AlpacaData.quotes` does)."""
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = Decimal(str(value)) if isinstance(value, float) else money(value)
    except (ValueError, ArithmeticError):
        return None
    return parsed if parsed.is_finite() and parsed > 0 else None


def position_key(instrument: Instrument) -> str:
    """One key for one position however the order spelled it (`BTC/USD`, `BTC-USD`, `BTCUSD`)."""
    symbol = instrument.symbol.strip().upper()
    if instrument.asset_class == "crypto":
        symbol = symbol.replace("/", "").replace("-", "")
    return f"{instrument.asset_class}:{symbol}"


def alpaca_symbol(instrument: Instrument) -> str:
    """The symbol Alpaca's market data takes: `BTC/USD` for a pair, the ticker for a share."""
    if instrument.asset_class == "crypto":
        return str(instrument.market_id or instrument.symbol).strip().upper().replace("-", "/")
    return instrument.symbol.strip().upper()


def touch_from(data: Any, *, ttl: float = 5.0, clock: Callable[[], float] = time.time) -> QuoteSource:
    """The production quote source: `league.tapes.AlpacaData.quotes`, one symbol at a time, held
    for `ttl` seconds so a pass over several open orders is one request a symbol. A symbol the
    venue has no two-sided quote for is None; a request that fails raises, and the account
    treats that as no quote."""
    cache: dict[str, tuple[float, Touch]] = {}
    lock = threading.Lock()

    def quotes(instrument: Instrument) -> Touch:
        if instrument.asset_class not in ASSET_CLASSES:
            return None
        symbol = alpaca_symbol(instrument)
        with lock:
            hit = cache.get(symbol)
            if hit is not None and clock() - hit[0] < ttl:
                return hit[1]
        row = (data.quotes([symbol]) or {}).get(symbol)
        bid, ask = (_price(row.get("bid")), _price(row.get("ask"))) if isinstance(row, dict) else (None, None)
        touch = (bid, ask) if bid is not None and ask is not None else None
        with lock:
            cache[symbol] = (clock(), touch)
        return touch

    return quotes


class SimBroker:
    """A simulated Alpaca account on live quotes. See the module docstring for the fill rules."""

    def __init__(
        self,
        state_path: str | os.PathLike,
        quotes: QuoteSource,
        *,
        venue: str = "alpaca-paper",
        starting_cash: Any = "100000",
        clock: Callable[[], float] = time.time,
    ):
        if not callable(quotes):
            raise TypeError("quotes must be a callable: (instrument) -> (bid, ask) | None")
        self.venue = venue
        self.state_path = Path(state_path)
        self.quotes = quotes
        self.clock = clock
        self.fees = Fees("alpaca")
        self._lock = threading.RLock()
        self._cash = money(starting_cash)
        if self._cash < 0:
            raise ValueError("starting_cash must not be negative")
        #: position key -> {"instrument" (as first ordered), "quantity", "cost" (fees included)}
        self._positions: dict[str, dict[str, Any]] = {}
        self._orders: dict[str, Order] = {}  # by "ord-..." id, in submission order
        self._by_broker_id: dict[str, str] = {}
        self._fills: list[Fill] = []
        self._next_order = 1
        self._next_fill = 1
        with self._lock:
            if self.state_path.exists():
                self._load()
            else:
                self._save()

    # ------------------------------------------------------------------ state
    def _now(self) -> str:
        return now_iso(self.clock)

    def _save(self) -> None:
        state = {
            "version": STATE_VERSION,
            "venue": self.venue,
            "cash": _text(self._cash),
            "next_order": self._next_order,
            "next_fill": self._next_fill,
            "positions": {
                key: {"instrument": held["instrument"].to_dict(), "quantity": _text(held["quantity"]), "cost": _text(held["cost"])}
                for key, held in self._positions.items()
            },
            "orders": [_order_to_dict(order) for order in self._orders.values()],
            "fills": [fill.to_dict() for fill in self._fills],
        }
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state_path.with_name(f".{self.state_path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(state, handle, separators=(",", ":"), sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, self.state_path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def _commit(self) -> None:
        """Write the mutation just made, or take it back: memory never runs ahead of the file the
        next process starts from."""
        try:
            self._save()
        except OSError as exc:
            self._load()
            raise VenueUnavailable(f"{self.venue}: the account could not be written, nothing was changed: {exc}") from exc

    def _load(self) -> None:
        """Read the account back. A file that cannot be read is an error, never a fresh account."""
        try:
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
            if not isinstance(state, dict) or state.get("version") != STATE_VERSION:
                raise ValueError(f"not a version {STATE_VERSION} simulated account")
            if state.get("venue") != self.venue:
                raise ValueError(f"it is the account of {state.get('venue')!r}, not {self.venue!r}")
            self._cash = money(state["cash"])
            self._next_order = int(state["next_order"])
            self._next_fill = int(state["next_fill"])
            self._positions = {
                key: {"instrument": Instrument.from_dict(held["instrument"]), "quantity": money(held["quantity"]), "cost": money(held["cost"])}
                for key, held in state["positions"].items()
            }
            self._orders = {}
            self._by_broker_id = {}
            for row in state["orders"]:
                order = _order_from_dict(row)
                self._orders[order.id] = order
                if order.broker_order_id:
                    self._by_broker_id[order.broker_order_id] = order.id
            self._fills = [_fill_from_dict(row) for row in state["fills"]]
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
            raise BrokerError(f"simulated account {self.state_path} cannot be read: {exc}") from exc

    # ----------------------------------------------------------------- quotes
    def _touch(self, instrument: Instrument) -> Touch:
        """The two-sided touch, or None when there is none to be had (which decides no fill)."""
        try:
            raw = self.quotes(instrument)
        except Exception:  # noqa: BLE001 - a source that cannot quote decides nothing
            return None
        if raw is None:
            return None
        try:
            bid, ask = raw
        except (TypeError, ValueError):
            return None
        bid, ask = _price(bid), _price(ask)
        if bid is None or ask is None or bid > ask:
            return None
        return bid, ask

    # ------------------------------------------------------------- accounting
    def _free_cash(self, *, excluding: str | None = None) -> Decimal:
        held = ZERO
        for order in self._orders.values():
            if not order.terminal and order.side == "buy" and order.id != excluding:
                held += money(order._raw.get("hold") or "0")
        return self._cash - held

    def _free_units(self, key: str, *, excluding: str | None = None) -> Decimal:
        quantity = self._positions[key]["quantity"] if key in self._positions else ZERO
        for order in self._orders.values():
            if not order.terminal and order.side == "sell" and order.id != excluding and position_key(order.instrument) == key:
                quantity -= order.remaining
        return quantity

    def _refusal(self, order: Order, price: Decimal) -> str:
        """Why the account cannot carry this order at this price, or ""."""
        if order.side == "buy":
            need = order.remaining * price * order.instrument.multiplier
            free = self._free_cash(excluding=order.id)
            if need > free:
                return f"insufficient buying power: needs ${need:.2f}, the account has ${free:.2f} free"
            return ""
        free = self._free_units(position_key(order.instrument), excluding=order.id)
        if order.remaining > free:
            return f"insufficient quantity: {format(order.remaining, 'f')} asked, {format(free, 'f')} held and free (no shorts)"
        return ""

    def _fill(self, order: Order, price: Decimal, liquidity: str, now: str) -> None:
        """All of the order, at one price. The caller has checked `_refusal`."""
        instrument, quantity = order.instrument, order.remaining
        charge = self.fees.charge(instrument, order.side, quantity, price, liquidity=liquidity)
        gross = quantity * price * instrument.multiplier
        key = position_key(instrument)
        if order.side == "buy":
            paid = (gross + charge.usd).quantize(CASH_PLACES)
            self._cash -= paid
            held = self._positions.setdefault(key, {"instrument": instrument, "quantity": ZERO, "cost": ZERO})
            held["quantity"] += received(quantity, charge) if charge.quantity else quantity
            held["cost"] += paid
        else:
            self._cash += (gross - charge.usd).quantize(CASH_PLACES)
            held = self._positions[key]
            held["cost"] -= held["cost"] * quantity / held["quantity"]
            held["quantity"] -= quantity
            if held["quantity"] <= 0:
                del self._positions[key]
        order.filled_quantity = order.filled_quantity + quantity
        order.average_price = price
        order.status = "filled"
        order.updated_at = now
        # The real adapter reports a fee of zero, so `order.fees` stays zero; this is the truth.
        order._raw.update(liquidity=liquidity, fee_usd=_text(charge.usd), fee_quantity=_text(charge.quantity), hold="0")
        self._fills.append(
            Fill(
                id=f"sim-fill-{self._next_fill}", order_id=order.id, desk_id=order.desk_id, instrument=instrument,
                side=order.side, quantity=quantity, price=price, fee=charge.usd, at=now,
            )
        )
        self._next_fill += 1

    @staticmethod
    def _close(order: Order, status: str, reason: str, now: str) -> None:
        order.status = status
        order.reason = reason
        order.updated_at = now
        order._raw["hold"] = "0"

    @staticmethod
    def _copy(order: Order) -> Order:
        """Callers get their own object: nothing outside the lock can edit the account's record."""
        return dataclasses.replace(order, _raw=dict(order._raw))

    def _read(self, order: Order, touch: Touch, now: str) -> bool:
        """Decide an open order against the touch of this read. True when the order changed."""
        if order.terminal or touch is None:
            return False
        bid, ask = touch
        if order.order_type == "market":
            price, liquidity = (ask if order.side == "buy" else bid), "taker"
        else:
            level = ask if order.side == "buy" else bid
            crosses = order.limit_price >= level if order.side == "buy" else order.limit_price <= level
            if not crosses:
                if order._raw.get("rested"):
                    return False
                if order.time_in_force == "ioc":
                    self._close(order, "cancelled", "immediate-or-cancel order did not cross", now)
                else:
                    order._raw["rested"] = True
                return True
            # Marketable when it was first read: it takes the touch. Crossed after it rested: a
            # maker's fill at its own price, which is all a resting order is ever owed.
            price, liquidity = (order.limit_price, "maker") if order._raw.get("rested") else (level, "taker")
        refusal = self._refusal(order, price)
        if refusal:
            self._close(order, "cancelled", refusal, now)
        else:
            self._fill(order, price, liquidity, now)
        return True

    def _read_all(self, orders: list[Order]) -> int:
        """Read every open order in `orders`, one quote an instrument, and write what changed."""
        now = self._now()
        touches: dict[str, Touch] = {}
        changed = 0
        for order in orders:
            if order.terminal:
                continue
            key = order.instrument.key
            if key not in touches:
                touches[key] = self._touch(order.instrument)
            changed += 1 if self._read(order, touches[key], now) else 0
        if changed:
            self._commit()
        return changed

    # --------------------------------------------------------------- protocol
    def capabilities(self) -> set[str]:
        return set(CAPABILITIES)

    def balance(self) -> Balance:
        """Equity is cash plus positions at cost: no quote is read, so it never fails."""
        with self._lock:
            at_cost = sum((held["cost"] for held in self._positions.values()), ZERO)
            return Balance(self.venue, self._cash, self._cash + at_cost, self._free_cash(), self._now())

    def positions(self) -> list[Position]:
        """In Alpaca's spelling: a crypto pair comes back without its slash (`BTCUSD`)."""
        with self._lock:
            now = self._now()
            out = []
            for held in self._positions.values():
                instrument, quantity = held["instrument"], held["quantity"]
                if quantity == 0:
                    continue
                if instrument.asset_class == "crypto":
                    symbol = instrument.symbol.upper().replace("/", "").replace("-", "")
                    instrument = Instrument("crypto", symbol, self.venue, market_id=symbol)
                out.append(Position(instrument, quantity, held["cost"] / (quantity * instrument.multiplier), as_of=now))
            return out

    def quote(self, instrument: Instrument) -> Quote:
        touch = self._touch(instrument)
        if touch is None:
            raise VenueUnavailable(f"{self.venue}: no two-sided quote for {instrument.key}")
        return Quote(instrument, touch[0], touch[1], None, self._now(), "sim:alpaca", delayed=False)

    def _validate(self, intent: OrderIntent) -> None:
        instrument = intent.instrument
        if instrument.venue != self.venue:
            raise RejectedOrder(f"instrument venue {instrument.venue!r} is not {self.venue!r}")
        if instrument.asset_class not in ASSET_CLASSES:
            raise RejectedOrder(f"{self.venue} (simulated) trades equities and crypto, not {instrument.asset_class}")
        whole = intent.quantity == intent.quantity.to_integral_value()
        if instrument.asset_class == "equity" and intent.order_type == "limit" and not whole:
            raise RejectedOrder("fractional shares are for market orders; a limit order is whole shares")
        if intent.quantity != intent.quantity.quantize(QTY_PLACES):
            raise RejectedOrder("a quantity has at most nine decimals")

    def submit(self, intent: OrderIntent) -> Order:
        with self._lock:
            order = Order.from_intent(intent, venue=self.venue)
            stored = self._orders.get(order.id)
            if stored is not None:
                return self._copy(stored)
            self._validate(intent)
            now = self._now()
            order.broker_order_id = f"sim-{self._next_order}"
            self._next_order += 1
            order.submitted_at = order.updated_at = now
            # A post-only order can only ever make: it is resting from the moment it is accepted.
            order._raw = {"post_only": bool(intent.post_only), "rested": bool(intent.post_only), "liquidity": None, "hold": "0"}
            self._orders[order.id] = order
            self._by_broker_id[order.broker_order_id] = order.id
            self._accept(order, now)
            self._commit()
            return self._copy(order)

    def _accept(self, order: Order, now: str) -> None:
        """Accepted or rejected; never filled. What a buy may cost is held from here on."""
        touch = self._touch(order.instrument)
        if order.order_type == "market":
            if touch is None:
                return self._close(order, "rejected", "no market: no two-sided quote to fill a market order against", now)
            price = touch[1] if order.side == "buy" else touch[0]
        else:
            price = order.limit_price
            if touch is not None and order._raw.get("post_only"):
                level = touch[1] if order.side == "buy" else touch[0]
                if (order.side == "buy" and price >= level) or (order.side == "sell" and price <= level):
                    return self._close(order, "rejected", "post-only order would cross", now)
        refusal = self._refusal(order, price)
        if refusal:
            return self._close(order, "rejected", refusal, now)
        order.status = "accepted"
        if order.side == "buy":
            order._raw["hold"] = _text((order.quantity * price * order.instrument.multiplier).quantize(CASH_PLACES))

    def _find(self, order_id: str) -> Order:
        order = self._orders.get(order_id) or self._orders.get(self._by_broker_id.get(order_id, ""))
        if order is None:
            raise RejectedOrder(f"{self.venue} has no order {order_id}")
        return order

    def get_order(self, order_id: str) -> Order:
        with self._lock:
            order = self._find(order_id)
            self._read_all([order])
            return self._copy(order)

    def cancel(self, order_id: str) -> Order:
        """A read first, as at the venue: an order that filled a moment ago cannot be cancelled."""
        with self._lock:
            order = self._find(order_id)
            self._read_all([order])
            if not order.terminal:
                self._close(order, "cancelled", "cancelled by request", self._now())
                self._commit()
            return self._copy(order)

    def open_orders(self) -> list[Order]:
        with self._lock:
            self._read_all(list(self._orders.values()))
            return [self._copy(order) for order in self._orders.values() if not order.terminal]

    def advance(self) -> int:
        """Read every open order now (the House calls this at the top of a tick, before it polls).
        Returns how many orders changed."""
        with self._lock:
            return self._read_all(list(self._orders.values()))

    def fills(self, since: str | None = None) -> list[Fill]:
        floor = None
        if since is not None:
            floor = instant(since)
            if floor is None:
                raise ValueError(f"since must be an ISO-8601 timestamp, not {since!r}")
        with self._lock:
            return [fill for fill in self._fills if floor is None or (instant(fill.at) or floor) >= floor]


# ------------------------------------------------------------------------------- serialization
def _order_to_dict(order: Order) -> dict[str, Any]:
    data = order.to_dict(private=True)
    data.update({"purpose": order.purpose, "exit_reason": order.exit_reason, "exit_of": order.exit_of})
    return data


def _order_from_dict(data: dict[str, Any]) -> Order:
    return Order(
        id=data["id"],
        intent_id=data["intent_id"],
        desk_id=data["desk_id"],
        instrument=Instrument.from_dict(data["instrument"]),
        side=data["side"],
        quantity=money(data["quantity"]),
        order_type=data["order_type"],
        limit_price=None if data.get("limit_price") is None else money(data["limit_price"]),
        time_in_force=data["time_in_force"],
        status=data["status"],
        venue=data["venue"],
        broker_order_id=data.get("broker_order_id"),
        filled_quantity=money(data.get("filled_quantity") or "0"),
        average_price=None if data.get("average_price") is None else money(data["average_price"]),
        fees=money(data.get("fees") or "0"),
        submitted_at=data.get("submitted_at"),
        updated_at=data.get("updated_at"),
        reason=data.get("reason"),
        purpose=data.get("purpose") or "entry",
        exit_reason=data.get("exit_reason"),
        exit_of=data.get("exit_of"),
        _raw=dict(data.get("_raw") or {}),
    )


def _fill_from_dict(data: dict[str, Any]) -> Fill:
    return Fill(
        id=data["id"],
        order_id=data["order_id"],
        desk_id=data["desk_id"],
        instrument=Instrument.from_dict(data["instrument"]),
        side=data["side"],
        quantity=money(data["quantity"]),
        price=money(data["price"]),
        fee=money(data["fee"]),
        at=data["at"],
    )


__all__ = ["SimBroker", "CAPABILITIES", "touch_from", "alpaca_symbol", "position_key"]
