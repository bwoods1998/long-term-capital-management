"""Test doubles for the league: a clock and a venue that behaves like the adapters' contract."""

from __future__ import annotations

from decimal import Decimal

from ltcm.broker import Balance, Fill, Instrument, Order, OrderIntent, Position, Quote, RejectedOrder, UnknownOutcome, money

from league.fees import Fees, received

ZERO = Decimal(0)


class Clock:
    def __init__(self, start: float = 1789000000.0):
        self.now = float(start)

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> float:
        self.now += seconds
        return self.now


def iso(clock) -> str:
    from league.ledger import now_iso

    return now_iso(clock)


class FakeBroker:
    """A venue account: cash, positions, quotes, resting orders. Market orders fill at the touch
    (all of it, or `fill_fraction` of it); limit orders rest unless they cross. It charges what
    `league.fees` says the real venue charges, so a book that attributes correctly reconciles."""

    def __init__(self, venue: str = "alpaca-paper", *, cash: str = "100000", family: str = "alpaca", caps=None):
        self.venue = venue
        self.cash = money(cash)
        self.fees = Fees(family)
        self.caps = set(caps or {"equity", "option", "crypto", "event", "limit", "gtc", "ioc", "fractional", "short"})
        self.quotes: dict[str, tuple[Decimal, Decimal]] = {}
        self.held: dict[str, tuple[Instrument, Decimal]] = {}
        self.orders: dict[str, Order] = {}
        self.submitted: list[OrderIntent] = []
        self.cancelled: list[str] = []
        self.fill_fraction: Decimal | None = None
        self.raise_on_submit: Exception | None = None
        self.lose_next_submit = False
        #: Alpaca's habits: an order is accepted first and filled on a later read, and a crypto
        #: position comes back as `BTCUSD` though the order was for `BTC/USD`.
        self.asynchronous = False
        self.rename_crypto = False
        self.reserve_open_buys = False
        self._pending: dict[str, tuple] = {}
        self.clock_iso = "2026-09-10T00:26:40.000Z"
        self._n = 0

    # -- scripting
    def set_quote(self, instrument: Instrument, bid: str, ask: str) -> None:
        self.quotes[instrument.key] = (money(bid), money(ask))

    def fill_resting(self, order_id: str, quantity: str, price: str | None = None) -> None:
        order = self.orders[order_id]
        self._fill(order, money(quantity), money(price) if price is not None else order.limit_price, "maker")

    # -- Broker protocol
    def capabilities(self) -> set[str]:
        return set(self.caps)

    def balance(self) -> Balance:
        cash = self.cash
        if self.reserve_open_buys:  # Alpaca's habit: the cash behind a resting crypto bid leaves `cash` until it fills or is cancelled
            cash -= sum((o.remaining * o.limit_price for o in self.open_orders() if o.instrument.asset_class == "crypto" and o.side == "buy" and o.limit_price), ZERO)
        return Balance(self.venue, cash, cash, cash, self.clock_iso)

    def positions(self) -> list[Position]:
        out = []
        for inst, qty in self.held.values():
            if qty == 0:
                continue
            if self.rename_crypto and inst.asset_class == "crypto":
                inst = Instrument("crypto", inst.symbol.replace("-", "").replace("/", ""), inst.venue)
            out.append(Position(inst, qty, ZERO))
        return out

    def quote(self, instrument: Instrument) -> Quote:
        if instrument.key not in self.quotes:
            raise RejectedOrder(f"no quote for {instrument.key}")
        bid, ask = self.quotes[instrument.key]
        return Quote(instrument, bid, ask, None, self.clock_iso, "fake", delayed=False)

    def submit(self, intent: OrderIntent) -> Order:
        self.submitted.append(intent)
        if self.raise_on_submit is not None:
            raise self.raise_on_submit
        order = Order.from_intent(intent, venue=self.venue)
        if order.id in self.orders:
            return self.orders[order.id]
        self._n += 1
        order.broker_order_id = f"venue-{self._n}"
        order.status = "accepted"
        order.submitted_at = self.clock_iso
        if self.lose_next_submit:
            self.lose_next_submit = False
            raise UnknownOutcome("the answer was lost")
        self.orders[order.id] = order
        bid, ask = self.quotes.get(intent.instrument.key, (None, None))
        if intent.order_type == "market":
            if bid is None:
                order.status = "rejected"
                order.reason = "no market"
                return order
            quantity = intent.quantity if self.fill_fraction is None else (intent.quantity * self.fill_fraction)
            if intent.instrument.asset_class in ("event", "option"):
                quantity = quantity.to_integral_value()
            if self.asynchronous:
                self._pending[order.id] = (quantity, ask if intent.side == "buy" else bid)
                return order
            self._fill(order, quantity, ask if intent.side == "buy" else bid, "taker")
            if order.status != "filled" and intent.instrument.asset_class == "event":
                order.status = "cancelled"  # an IOC's unfilled remainder
        else:
            crosses = bid is not None and (
                (intent.side == "buy" and intent.limit_price >= ask) or (intent.side == "sell" and intent.limit_price <= bid)
            )
            if crosses and intent.post_only:
                order.status = "rejected"
                order.reason = "post-only order would cross"
            elif crosses:
                self._fill(order, intent.quantity, ask if intent.side == "buy" else bid, "taker")
        return order

    def _fill(self, order: Order, quantity: Decimal, price: Decimal, liquidity: str) -> None:
        if quantity <= 0:
            return
        instrument = order.instrument
        charge = self.fees.charge(instrument, order.side, quantity, price, liquidity=liquidity, filled_before=order.filled_quantity)
        gross = quantity * price * instrument.multiplier
        inst, held = self.held.get(instrument.key, (instrument, ZERO))
        if order.side == "buy":
            self.cash -= gross + charge.usd
            held += received(quantity, charge) if charge.quantity else quantity
        else:
            self.cash += gross - charge.usd
            held -= quantity
        self.held[instrument.key] = (inst, held)
        before = order.filled_quantity
        average = order.average_price or ZERO
        order.filled_quantity = before + quantity
        order.average_price = (average * before + price * quantity) / order.filled_quantity
        order.fees = order.fees + charge.usd
        order.status = "filled" if order.filled_quantity >= order.quantity else "partially_filled"

    def get_order(self, order_id: str) -> Order:
        for order in self.orders.values():
            if order_id in (order.id, order.broker_order_id):
                if order.id in self._pending:
                    self._fill(order, *self._pending.pop(order.id), "taker")
                return order
        raise RejectedOrder(f"no order {order_id}")

    def cancel(self, order_id: str) -> Order:
        order = self.get_order(order_id)
        if not order.terminal:
            order.status = "cancelled"
            self.cancelled.append(order.id)
        return order

    def open_orders(self) -> list[Order]:
        return [o for o in self.orders.values() if not o.terminal]

    def fills(self, since: str | None = None) -> list[Fill]:
        return []


def old_ladder():
    """The ladder as it stood before capital was the ladder (Sept 23, 2026): the allocator switched
    off, exactly as its rollback (`allocator.enabled: False`) would. For the tests of the old rungs'
    screen, micro stake, tuition and Kelly sizing, which still guard that rollback path."""
    from unittest.mock import patch

    from league.constitution import CONSTITUTION

    return patch.dict(CONSTITUTION["allocator"], {"enabled": False})
