"""`ShadowBook`: a deterministic scoring book with the live `Broker` surface.

This is the engine behind a **shadow desk**. No order it accepts is ever sent anywhere: it prices
the desk's proposal against the real venue's quote, charges the real venue's fee model, and keeps
the result as a hypothetical book. It holds its state in one SQLite file (`account`, `positions`,
`orders`, `fills`, `marks`), keeps all money as TEXT decimals, and takes its prices from any
`MarketData` implementation and its time from an injected clock, so a test and a live shadow
session run exactly the same code path.

The book's own `venue` is `"shadow"` -- the gateway's routing key -- while `market_venue` names the
real venue it prices and charges like, which is the venue the desk would trade on once it is
promoted. Instruments keep the real venue, so nothing about the fill is a fiction except that it
never happened.

What is modelled
  - Market orders fill immediately at `Quote.reference(side)` moved by `slippage_bps`.
  - Limit orders rest and fill at the limit price when the reference crosses it on `tick()`.
  - `ioc` cancels at once when it is not marketable, `day` expires at the session close of the day
    it was submitted, `gtc` persists until cancelled or filled.
  - Cash, average cost, realized profit, fees and equity marks.
  - Event contracts settle at $1 or $0 per contract through `settle_event()`.
  - Options through `Instrument.multiplier`; crypto fractionally.

What is not modelled: partial fills, queue position, borrow, margin, assignment, and any latency
other than "the next tick". Nothing here reaches the network; the `MarketData` source does.

Fee defaults follow the venues the floor actually uses; see `FeeModel` for the sources.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_HALF_EVEN, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Callable

from .broker import (
    Balance,
    Fill,
    Instrument,
    Order,
    OrderIntent,
    Position,
    Quote,
    RejectedOrder,
    money,
    text,
)
from .data import MarketData, next_session, to_datetime, iso, us_equity_session

ZERO = Decimal(0)
ONE = Decimal(1)
CENT = Decimal("0.01")
PRICE_PLACES = Decimal("0.00000001")
BPS = Decimal(10_000)

SHADOW_CAPABILITIES = {
    "equity",
    "option",
    "crypto",
    "future",
    "event",
    "limit",
    "gtc",
    "ioc",
    "fractional",
    "shadow",
}

#: The routing key of the scoring book, matching `manifest.SHADOW_VENUE`.
SHADOW_VENUE = "shadow"

SCHEMA = """
CREATE TABLE IF NOT EXISTS account (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    venue TEXT NOT NULL,
    currency TEXT NOT NULL,
    cash TEXT NOT NULL,
    initial_cash TEXT NOT NULL,
    realized_pnl TEXT NOT NULL,
    fees_paid TEXT NOT NULL,
    equity TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS positions (
    key TEXT PRIMARY KEY,
    instrument TEXT NOT NULL,
    quantity TEXT NOT NULL,
    average_cost TEXT NOT NULL,
    mark TEXT,
    as_of TEXT
);
CREATE TABLE IF NOT EXISTS orders (
    id TEXT PRIMARY KEY,
    intent_id TEXT NOT NULL UNIQUE,
    desk_id TEXT NOT NULL,
    instrument TEXT NOT NULL,
    side TEXT NOT NULL,
    quantity TEXT NOT NULL,
    order_type TEXT NOT NULL,
    limit_price TEXT,
    time_in_force TEXT NOT NULL,
    status TEXT NOT NULL,
    venue TEXT NOT NULL,
    broker_order_id TEXT,
    filled_quantity TEXT NOT NULL,
    average_price TEXT,
    fees TEXT NOT NULL,
    submitted_at TEXT,
    updated_at TEXT,
    reason TEXT,
    expires_at TEXT,
    seq INTEGER
);
CREATE INDEX IF NOT EXISTS orders_status ON orders(status);
CREATE TABLE IF NOT EXISTS fills (
    id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL,
    desk_id TEXT NOT NULL,
    instrument TEXT NOT NULL,
    side TEXT NOT NULL,
    quantity TEXT NOT NULL,
    price TEXT NOT NULL,
    fee TEXT NOT NULL,
    at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS fills_at ON fills(at);
CREATE TABLE IF NOT EXISTS marks (
    at TEXT PRIMARY KEY,
    cash TEXT NOT NULL,
    equity TEXT NOT NULL,
    realized_pnl TEXT NOT NULL,
    positions TEXT NOT NULL
);
"""


def quantize_price(value: Decimal) -> Decimal:
    return money(value).quantize(PRICE_PLACES, rounding=ROUND_HALF_EVEN)


def quantize_cash(value: Decimal) -> Decimal:
    return money(value).quantize(CENT, rounding=ROUND_HALF_UP)


def ceil_cents(value: Decimal) -> Decimal:
    """Round a charge up to the next whole cent. Venues never round a fee in our favour."""
    return money(value).quantize(CENT, rounding=ROUND_CEILING)


def _dec_or_none(value: Any) -> "Decimal | None":
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return d if d.is_finite() else None


@dataclass(frozen=True)
class FeeModel:
    """Per-venue commission defaults, all overridable per desk.

    Defaults as published by the venues the floor uses:
      - US equities: $0 commission (Alpaca, Schwab, most retail brokers since 2019).
      - US options: $0.65 per contract (the common retail rate; Alpaca charges $0).
      - Crypto: 0.25% taker (the rate this floor budgets for; Coinbase Advanced Trade's
        actual tier depends on 30-day volume, https://www.coinbase.com/advanced-fees).
      - Kalshi event contracts: ceil(0.07 x contracts x price x (1 - price)) to the next cent,
        the published trading-fee formula (https://kalshi.com/docs/kalshi-fee-schedule.pdf).
      - Futures: a flat per-contract round-turn placeholder; no floor desk trades futures yet.
    """

    equity_per_share: Decimal = ZERO
    equity_flat: Decimal = ZERO
    option_per_contract: Decimal = Decimal("0.65")
    crypto_taker_pct: Decimal = Decimal("0.0025")
    crypto_maker_pct: Decimal = Decimal("0.0025")
    future_per_contract: Decimal = Decimal("2.50")
    event_fee_rate: Decimal = Decimal("0.07")

    def __post_init__(self):
        for name in (
            "equity_per_share",
            "equity_flat",
            "option_per_contract",
            "crypto_taker_pct",
            "crypto_maker_pct",
            "future_per_contract",
            "event_fee_rate",
        ):
            value = money(getattr(self, name))
            if value < 0:
                raise ValueError(f"{name} must not be negative")
            object.__setattr__(self, name, value)

    @classmethod
    def for_venue(cls, venue: str) -> "FeeModel":
        """The default model for a venue. Unknown venues get the conservative defaults."""
        if venue == "alpaca":
            return cls(option_per_contract=Decimal("0.65"), crypto_taker_pct=Decimal("0.0025"))
        if venue == "kalshi":
            return cls(event_fee_rate=Decimal("0.07"))
        if venue in ("coinbase", "kraken"):
            return cls(crypto_taker_pct=Decimal("0.0025"), crypto_maker_pct=Decimal("0.0015"))
        if venue in ("schwab", "tastytrade"):
            return cls(option_per_contract=Decimal("0.65"))
        return cls()

    def kalshi_fee(self, count: Decimal, price: Decimal) -> Decimal:
        """ceil to the cent of 0.07 x C x P x (1 - P), with P the yes price in dollars."""
        count = money(count)
        price = money(price)
        if price < 0 or price > ONE:
            raise ValueError("event contract prices are dollars between 0 and 1")
        return ceil_cents(self.event_fee_rate * count * price * (ONE - price))

    def fee(
        self,
        instrument: Instrument,
        side: str,
        quantity: Decimal,
        price: Decimal,
        *,
        liquidity: str = "taker",
    ) -> Decimal:
        """Commission for one fill. Always non-negative and quantized to the cent."""
        quantity = money(quantity)
        price = money(price)
        asset = instrument.asset_class
        if asset == "equity":
            charged = self.equity_flat + self.equity_per_share * quantity
        elif asset == "option":
            charged = self.option_per_contract * quantity
        elif asset == "crypto":
            rate = self.crypto_taker_pct if liquidity == "taker" else self.crypto_maker_pct
            charged = rate * quantity * price * instrument.multiplier
        elif asset == "future":
            charged = self.future_per_contract * quantity
        elif asset == "event":
            # Kalshi charges the taker; a resting order that is filled pays nothing (every
            # maker fill on Sept 16, 2026 came back with fee 0, every taker fill with the
            # formula's). A shadow record that charged makers the taker fee would have punished
            # the quoting strategies for an edge the venue actually pays them.
            return ZERO if liquidity == "maker" else self.kalshi_fee(quantity, price)
        else:  # pragma: no cover - Instrument already rejects unknown classes
            charged = ZERO
        return quantize_cash(charged) if charged > 0 else ZERO


def _loads_instrument(blob: str) -> Instrument:
    return Instrument.from_dict(json.loads(blob))


def _dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


class ShadowBook:
    """A `Broker` over scored state. Deterministic given the same data, clock and inputs.

    Nothing here reaches a venue. `market_venue` is the real venue whose quotes price the fills
    and whose fee schedule charges them, so a shadow result is comparable with a live one.
    """

    def __init__(
        self,
        path: "str | Path",
        *,
        venue: str = SHADOW_VENUE,
        market_venue: "str | None" = None,
        data: MarketData,
        clock: Callable[[], Any],
        initial_cash: Any = Decimal("100000"),
        fee_model: "FeeModel | None" = None,
        slippage_bps: Any = Decimal(5),
        allow_short: bool = False,
        currency: str = "USD",
    ):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.venue = venue
        #: The real venue this book prices and charges like. Defaults to its own name.
        self.market_venue = market_venue or venue
        self.data = data
        self.clock = clock
        self.fee_model = fee_model or FeeModel.for_venue(self.market_venue)
        self.slippage_bps = money(slippage_bps)
        if self.slippage_bps < 0:
            raise ValueError("slippage_bps must not be negative")
        self.allow_short = bool(allow_short)
        self.currency = currency
        self._lock = threading.RLock()
        self._db = sqlite3.connect(
            str(self.path), isolation_level=None, check_same_thread=False, timeout=30
        )
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=FULL")
        self._db.executescript(SCHEMA)
        initial = money(initial_cash)
        if initial < 0:
            raise ValueError("initial_cash must not be negative")
        row = self._db.execute("SELECT * FROM account WHERE id = 1").fetchone()
        if row is None:
            stamp = self.now()
            self._db.execute(
                "INSERT INTO account (id, venue, currency, cash, initial_cash, realized_pnl,"
                " fees_paid, equity, updated_at) VALUES (1, ?, ?, ?, ?, '0', '0', ?, ?)",
                (venue, currency, text(initial), text(initial), text(initial), stamp),
            )

    # ------------------------------------------------------------------- basics
    def close(self) -> None:
        with self._lock:
            self._db.close()

    def now(self) -> str:
        """The injected clock as an ISO-8601 UTC stamp."""
        return iso(self.clock())

    def accepts(self, venue: str) -> bool:
        """An instrument routes here when it names this book or the venue it stands in for."""
        return venue in (self.venue, self.market_venue)

    def capabilities(self) -> set[str]:
        caps = set(SHADOW_CAPABILITIES)
        if self.allow_short:
            caps.add("short")
        return caps

    def quote(self, instrument: Instrument) -> Quote:
        return self.data.quote(instrument)

    # ------------------------------------------------------------------ account
    def _account(self) -> sqlite3.Row:
        return self._db.execute("SELECT * FROM account WHERE id = 1").fetchone()

    @property
    def cash(self) -> Decimal:
        return money(self._account()["cash"])

    @property
    def realized_pnl(self) -> Decimal:
        return money(self._account()["realized_pnl"])

    def balance(self) -> Balance:
        account = self._account()
        cash = money(account["cash"])
        equity = cash + self._positions_value()
        return Balance(
            venue=self.venue,
            cash=cash,
            equity=equity,
            buying_power=cash if not self.allow_short else cash * Decimal(2),
            as_of=account["updated_at"],
            currency=self.currency,
        )

    def positions(self) -> list[Position]:
        rows = self._db.execute("SELECT * FROM positions ORDER BY key").fetchall()
        return [self._row_to_position(row) for row in rows if money(row["quantity"]) != 0]

    def position(self, instrument: Instrument) -> "Position | None":
        row = self._db.execute(
            "SELECT * FROM positions WHERE key = ?", (instrument.key,)
        ).fetchone()
        if row is None or money(row["quantity"]) == 0:
            return None
        return self._row_to_position(row)

    @staticmethod
    def _row_to_position(row: sqlite3.Row) -> Position:
        return Position(
            instrument=_loads_instrument(row["instrument"]),
            quantity=money(row["quantity"]),
            average_cost=money(row["average_cost"]),
            mark=money(row["mark"]) if row["mark"] is not None else None,
            as_of=row["as_of"],
        )

    def _positions_value(self) -> Decimal:
        total = ZERO
        for position in self.positions():
            value = position.market_value
            total += value if value is not None else position.cost_basis
        return total

    # ------------------------------------------------------------------- orders
    def _row_to_order(self, row: sqlite3.Row) -> Order:
        order = Order(
            id=row["id"],
            intent_id=row["intent_id"],
            desk_id=row["desk_id"],
            instrument=_loads_instrument(row["instrument"]),
            side=row["side"],
            quantity=money(row["quantity"]),
            order_type=row["order_type"],
            limit_price=money(row["limit_price"]) if row["limit_price"] is not None else None,
            time_in_force=row["time_in_force"],
            status=row["status"],
            venue=row["venue"],
            broker_order_id=row["broker_order_id"],
            filled_quantity=money(row["filled_quantity"]),
            average_price=money(row["average_price"]) if row["average_price"] is not None else None,
            fees=money(row["fees"]),
            submitted_at=row["submitted_at"],
            updated_at=row["updated_at"],
            reason=row["reason"],
        )
        order._raw = {"expires_at": row["expires_at"]}
        return order

    def get_order(self, order_id: str) -> Order:
        row = self._db.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        if row is None:
            raise RejectedOrder(f"unknown order {order_id}")
        return self._row_to_order(row)

    def order_for_intent(self, intent_id: str) -> "Order | None":
        row = self._db.execute(
            "SELECT * FROM orders WHERE intent_id = ?", (intent_id,)
        ).fetchone()
        return self._row_to_order(row) if row else None

    def open_orders(self) -> list[Order]:
        rows = self._db.execute(
            "SELECT * FROM orders WHERE status IN ('new', 'accepted', 'partially_filled')"
            " ORDER BY seq ASC"
        ).fetchall()
        return [self._row_to_order(row) for row in rows]

    def orders(self, *, desk_id: "str | None" = None) -> list[Order]:
        if desk_id is None:
            rows = self._db.execute("SELECT * FROM orders ORDER BY seq ASC").fetchall()
        else:
            rows = self._db.execute(
                "SELECT * FROM orders WHERE desk_id = ? ORDER BY seq ASC", (desk_id,)
            ).fetchall()
        return [self._row_to_order(row) for row in rows]

    def fills(self, since: "str | None" = None) -> list[Fill]:
        if since is None:
            rows = self._db.execute("SELECT * FROM fills ORDER BY at ASC, id ASC").fetchall()
        else:
            rows = self._db.execute(
                "SELECT * FROM fills WHERE at >= ? ORDER BY at ASC, id ASC", (since,)
            ).fetchall()
        return [
            Fill(
                id=row["id"],
                order_id=row["order_id"],
                desk_id=row["desk_id"],
                instrument=_loads_instrument(row["instrument"]),
                side=row["side"],
                quantity=money(row["quantity"]),
                price=money(row["price"]),
                fee=money(row["fee"]),
                at=row["at"],
            )
            for row in rows
        ]

    # ------------------------------------------------------------------ submit
    def submit(self, intent: OrderIntent) -> Order:
        """Route an approved intent. Idempotent: one order per intent id, ever."""
        with self._lock:
            existing = self.order_for_intent(intent.id)
            if existing is not None:
                return existing
            if not self.accepts(intent.instrument.venue):
                raise RejectedOrder(
                    f"instrument routes to {intent.instrument.venue}, not {self.market_venue}"
                )
            self._check_quantity(intent)
            stamp = self.now()
            order = Order.from_intent(intent, venue=self.venue)
            order.status = "accepted"
            order.broker_order_id = "sim-" + order.id[4:]
            order.submitted_at = stamp
            order.updated_at = stamp
            expires_at = self._expiry_for(intent, stamp)
            self._insert_order(order, expires_at)
            quote = self._quote_or_none(intent.instrument)
            if intent.order_type == "market":
                if quote is None:
                    return self._reject(order, "no quote available for a market order")
                reference = quote.reference(intent.side)
                if reference is None or reference <= 0:
                    return self._reject(order, "quote carries no usable reference price")
                price = self._with_slippage(reference, intent.side)
                return self._fill(order, price, stamp)
            if getattr(intent, "post_only", False) and quote is not None:
                # A post-only limit that would take is refused, as the venues refuse it.
                reference = quote.reference(intent.side)
                crosses = reference is not None and reference > 0 and (
                    (intent.side == "buy" and reference <= order.limit_price)
                    or (intent.side == "sell" and reference >= order.limit_price)
                )
                if crosses:
                    return self._reject(order, "post-only order would cross the book")
            filled = self._try_limit(order, quote, stamp, aggressive=True)
            if filled is not None:
                return filled
            if intent.time_in_force == "ioc":
                return self._cancel(order, "ioc order was not marketable", status="cancelled")
            return self.get_order(order.id)

    def _check_quantity(self, intent: OrderIntent) -> None:
        whole = intent.quantity == intent.quantity.to_integral_value()
        if not whole and intent.instrument.asset_class not in ("crypto", "equity"):
            raise RejectedOrder(
                f"{intent.instrument.asset_class} contracts cannot be fractional"
            )

    def _expiry_for(self, intent: OrderIntent, stamp: str) -> "str | None":
        """When a `day` order dies. `ioc` and `gtc` never expire on the clock.

        For equities and options that is the close of the session the order lives in: the one
        already under way, or - when the order arrives outside hours, at a weekend or on a
        holiday - the close of the next session, which is the first one that can fill it.
        """
        if intent.time_in_force != "day":
            return None
        moment = to_datetime(stamp)
        if intent.instrument.asset_class in ("equity", "option", "future"):
            session = us_equity_session(moment)
            if session is not None and to_datetime(session.close_at) > moment:
                return session.close_at
            upcoming = next_session(moment)
            if upcoming is not None:
                return upcoming.close_at
        # Crypto and event venues trade around the clock: a day order dies at the UTC midnight
        # after it was placed.
        return iso(moment.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1))

    def _quote_or_none(self, instrument: Instrument) -> "Quote | None":
        try:
            quote = self.data.quote(instrument)
        except Exception:  # a source failure is a missing quote, never a crash
            return None
        return quote if isinstance(quote, Quote) else None

    def _with_slippage(self, reference: Decimal, side: str) -> Decimal:
        move = reference * self.slippage_bps / BPS
        price = reference + move if side == "buy" else reference - move
        if price <= 0:
            price = reference
        return quantize_price(price)

    def _try_limit(
        self, order: Order, quote: "Quote | None", stamp: str, *, aggressive: bool = False
    ) -> "Order | None":
        """Fill a limit order when the reference price is at or through its limit.

        `aggressive` is True only on submission, when the order arrives already marketable and
        takes the resting side of the book: it pays the touch, which is at least as good as its
        limit. A limit that had to wait for the market to come to it fills at the limit itself,
        which is the price a real queue would have given us.
        """
        if quote is None:
            return None
        reference = quote.reference(order.side)
        if reference is None or reference <= 0:
            return None
        limit = order.limit_price
        liquidity = "taker" if aggressive else "maker"
        if order.side == "buy" and reference <= limit:
            return self._fill(order, quantize_price(reference if aggressive else limit), stamp, liquidity=liquidity)
        if order.side == "sell" and reference >= limit:
            return self._fill(order, quantize_price(reference if aggressive else limit), stamp, liquidity=liquidity)
        return None

    # -------------------------------------------------------------- execution
    def _fill(self, order: Order, price: Decimal, stamp: str, *, liquidity: str = "taker", quantity: "Decimal | None" = None) -> Order:
        quantity = order.remaining if quantity is None else min(order.remaining, quantity)
        if quantity <= 0:
            return order
        fee = self.fee_model.fee(order.instrument, order.side, quantity, price, liquidity=liquidity)
        notional = quantity * price * order.instrument.multiplier
        account = self._account()
        cash = money(account["cash"])
        if order.side == "buy" and notional + fee > cash:
            return self._reject(
                order, f"insufficient cash: need {notional + fee:f}, have {cash:f}"
            )
        if order.side == "sell":
            held = self.position(order.instrument)
            held_qty = held.quantity if held else ZERO
            if held_qty - quantity < 0 and not self.allow_short:
                return self._reject(
                    order, f"insufficient position: hold {held_qty:f}, selling {quantity:f}"
                )
        fill_id = "fl-" + hashlib.sha256(
            f"{order.id}|{stamp}|{quantity:f}|{price:f}".encode("utf-8")
        ).hexdigest()[:32]
        realized = self._apply_to_position(order.instrument, order.side, quantity, price)
        delta = -(notional + fee) if order.side == "buy" else notional - fee
        self._db.execute(
            "UPDATE account SET cash = ?, realized_pnl = ?, fees_paid = ?, updated_at = ?"
            " WHERE id = 1",
            (
                text(cash + delta),
                text(money(account["realized_pnl"]) + realized - fee),
                text(money(account["fees_paid"]) + fee),
                stamp,
            ),
        )
        self._db.execute(
            "INSERT OR IGNORE INTO fills (id, order_id, desk_id, instrument, side, quantity,"
            " price, fee, at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                fill_id,
                order.id,
                order.desk_id,
                _dumps(order.instrument.to_dict()),
                order.side,
                text(quantity),
                text(price),
                text(fee),
                stamp,
            ),
        )
        filled_quantity = order.filled_quantity + quantity
        status = "filled" if filled_quantity >= order.quantity else "partially_filled"
        # The average price weighs every partial fill; a single fill is its own average.
        average = price if order.filled_quantity == 0 else quantize_price(
            ((order.average_price or ZERO) * order.filled_quantity + price * quantity) / filled_quantity
        )
        self._db.execute(
            "UPDATE orders SET status = ?, filled_quantity = ?, average_price = ?,"
            " fees = ?, updated_at = ?, reason = NULL WHERE id = ?",
            (status, text(filled_quantity), text(average), text(order.fees + fee), stamp, order.id),
        )
        return self.get_order(order.id)

    # ----------------------------------------------------------- taker model
    def on_trade(self, venue: str, symbol: str, price: Any, size: Any, taker_side: str, now: Any = None) -> list[Order]:
        """leap: taker model -- a print on the venue fills the resting quotes it would have hit.

        Until Sept 16, 2026 a resting shadow quote filled only when the quote itself crossed
        it, so a maker strategy never filled in shadow while its live twin filled ninety
        times: the takers who cross the spread to hit a resting bid are exactly what the
        shadow book could not see. A print of `size` at `price` by a taker on `taker_side`
        fills, at the order's own limit and as a maker, every resting buy on the leg the taker
        sold at or through its limit, and every resting sell on the leg the taker bought at or
        through its limit, up to the printed size. Event prints carry the YES price and a taker
        side of yes/no; a crypto print carries the product price and buy/sell."""
        price_d, size_d = _dec_or_none(price), _dec_or_none(size)
        if price_d is None or size_d is None or size_d <= 0:
            return []
        taker = str(taker_side or "").lower()
        wanted = str(symbol or "").upper()
        with self._lock:
            stamp = iso(now) if now is not None else self.now()
            changed: list[Order] = []
            for order in self.open_orders():
                inst = order.instrument
                if order.order_type != "limit" or inst.venue != venue:
                    continue
                if inst.asset_class == "event":
                    if str(inst.market_id or inst.symbol).upper() != wanted:
                        continue
                    leg = str(inst.right or "yes").lower()
                    leg_price = price_d if leg == "yes" else (ONE - price_d)
                    taker_bought_leg = taker == leg
                    if taker not in ("yes", "no"):
                        continue
                else:
                    if str(inst.symbol).upper() != wanted or taker not in ("buy", "sell"):
                        continue
                    leg_price = price_d
                    taker_bought_leg = taker == "buy"
                hit = (order.side == "buy" and not taker_bought_leg and leg_price <= order.limit_price) or (
                    order.side == "sell" and taker_bought_leg and leg_price >= order.limit_price
                )
                if not hit:
                    continue
                take = min(size_d, order.remaining)
                try:
                    filled = self._fill(order, quantize_price(order.limit_price), stamp, liquidity="maker", quantity=take)
                except RejectedOrder:
                    changed.append(self.get_order(order.id))
                    continue
                changed.append(filled)
                size_d -= take
                if size_d <= 0:
                    break
            return changed

    def _apply_to_position(
        self, instrument: Instrument, side: str, quantity: Decimal, price: Decimal
    ) -> Decimal:
        """Update the position book. Returns realized profit on the closed portion."""
        signed = quantity if side == "buy" else -quantity
        row = self._db.execute(
            "SELECT * FROM positions WHERE key = ?", (instrument.key,)
        ).fetchone()
        held = money(row["quantity"]) if row else ZERO
        average = money(row["average_cost"]) if row else ZERO
        realized = ZERO
        after = held + signed
        if held == 0 or (held > 0) == (signed > 0):  # opening or adding
            new_average = (
                price if held == 0 else (average * abs(held) + price * abs(signed)) / abs(after)
            )
        else:  # reducing, closing or flipping
            closed = min(abs(signed), abs(held))
            direction = ONE if held > 0 else -ONE
            realized = (price - average) * closed * direction * instrument.multiplier
            new_average = average if after != 0 and (after > 0) == (held > 0) else price
            if after == 0:
                new_average = ZERO
        if row is None:
            self._db.execute(
                "INSERT INTO positions (key, instrument, quantity, average_cost, mark, as_of)"
                " VALUES (?, ?, ?, ?, NULL, NULL)",
                (instrument.key, _dumps(instrument.to_dict()), text(after), text(new_average)),
            )
        else:
            self._db.execute(
                "UPDATE positions SET quantity = ?, average_cost = ? WHERE key = ?",
                (text(after), text(new_average), instrument.key),
            )
        if after == 0:
            self._db.execute("DELETE FROM positions WHERE key = ?", (instrument.key,))
        return realized

    def _insert_order(self, order: Order, expires_at: "str | None") -> None:
        self._db.execute(
            "INSERT INTO orders (id, intent_id, desk_id, instrument, side, quantity, order_type,"
            " limit_price, time_in_force, status, venue, broker_order_id, filled_quantity,"
            " average_price, fees, submitted_at, updated_at, reason, expires_at, seq)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,"
            " (SELECT COALESCE(MAX(seq), 0) + 1 FROM orders))",
            (
                order.id,
                order.intent_id,
                order.desk_id,
                _dumps(order.instrument.to_dict()),
                order.side,
                text(order.quantity),
                order.order_type,
                text(order.limit_price),
                order.time_in_force,
                order.status,
                order.venue,
                order.broker_order_id,
                text(order.filled_quantity),
                text(order.average_price),
                text(order.fees),
                order.submitted_at,
                order.updated_at,
                order.reason,
                expires_at,
            ),
        )

    def _reject(self, order: Order, reason: str) -> Order:
        self._db.execute(
            "UPDATE orders SET status = 'rejected', reason = ?, updated_at = ? WHERE id = ?",
            (reason, self.now(), order.id),
        )
        raise RejectedOrder(reason)

    def _cancel(self, order: Order, reason: str, *, status: str = "cancelled") -> Order:
        self._db.execute(
            "UPDATE orders SET status = ?, reason = ?, updated_at = ? WHERE id = ?",
            (status, reason, self.now(), order.id),
        )
        return self.get_order(order.id)

    def cancel(self, order_id: str) -> Order:
        with self._lock:
            order = self.get_order(order_id)
            if order.terminal:
                return order
            return self._cancel(order, "cancelled by request")

    # -------------------------------------------------------------------- tick
    def tick(self, now: Any = None) -> list[Order]:
        """Advance the simulation: cross resting limits, expire day orders.

        Returns every order whose status changed, in submission order.
        """
        with self._lock:
            stamp = iso(now) if now is not None else self.now()
            changed: list[Order] = []
            for order in self.open_orders():
                expires_at = order._raw.get("expires_at")
                if expires_at is not None and stamp >= expires_at:
                    changed.append(self._cancel(order, "day order expired", status="expired"))
                    continue
                if order.order_type != "limit":  # market orders never rest here
                    continue
                quote = self._quote_or_none(order.instrument)
                try:
                    filled = self._try_limit(order, quote, stamp)
                except RejectedOrder:
                    changed.append(self.get_order(order.id))
                    continue
                if filled is not None:
                    changed.append(filled)
            return changed

    # -------------------------------------------------------------------- mark
    def mark(self, now: Any = None) -> Balance:
        """Re-mark every position from the data source and record the equity point."""
        with self._lock:
            stamp = iso(now) if now is not None else self.now()
            for position in self.positions():
                quote = self._quote_or_none(position.instrument)
                price = None
                if quote is not None:
                    price = quote.mid if quote.mid is not None else quote.last
                if price is None or price <= 0:
                    price = position.mark if position.mark is not None else position.average_cost
                self._db.execute(
                    "UPDATE positions SET mark = ?, as_of = ? WHERE key = ?",
                    (text(money(price)), stamp, position.instrument.key),
                )
            account = self._account()
            cash = money(account["cash"])
            positions = self.positions()
            equity = cash + sum(
                (p.market_value if p.market_value is not None else p.cost_basis) for p in positions
            )
            self._db.execute(
                "UPDATE account SET equity = ?, updated_at = ? WHERE id = 1", (text(equity), stamp)
            )
            self._db.execute(
                "INSERT OR REPLACE INTO marks (at, cash, equity, realized_pnl, positions)"
                " VALUES (?, ?, ?, ?, ?)",
                (
                    stamp,
                    text(cash),
                    text(equity),
                    account["realized_pnl"],
                    _dumps([p.to_dict() for p in positions]),
                ),
            )
            return Balance(
                venue=self.venue,
                cash=cash,
                equity=equity,
                buying_power=cash if not self.allow_short else cash * Decimal(2),
                as_of=stamp,
                currency=self.currency,
            )

    def marks(self, since: "str | None" = None) -> list[dict[str, Any]]:
        if since is None:
            rows = self._db.execute("SELECT * FROM marks ORDER BY at ASC").fetchall()
        else:
            rows = self._db.execute(
                "SELECT * FROM marks WHERE at > ? ORDER BY at ASC", (since,)
            ).fetchall()
        return [
            {
                "at": row["at"],
                "cash": row["cash"],
                "equity": row["equity"],
                "realized_pnl": row["realized_pnl"],
                "positions": json.loads(row["positions"]),
            }
            for row in rows
        ]

    # ---------------------------------------------------------------- settle
    def settle_event(self, market_id: str, payout_per_contract: Any, *, now: Any = None) -> list[Fill]:
        """Settle every event position on one market. `payout_per_contract` is the **yes** value.

        Yes contracts pay $1 or $0; a `right="no"` instrument on the same market pays the
        complement, `1 - payout`, because exactly one of the two legs is worth a dollar. Open
        orders on the market are cancelled first: a resolved market cannot trade.
        """
        payout = money(payout_per_contract)
        if payout < 0 or payout > ONE:
            raise ValueError("payout_per_contract must be between 0 and 1 dollars")
        with self._lock:
            stamp = iso(now) if now is not None else self.now()
            for order in self.open_orders():
                if order.instrument.market_id == market_id:
                    self._cancel(order, f"market {market_id} settled")
            settled: list[Fill] = []
            for position in self.positions():
                instrument = position.instrument
                if instrument.asset_class != "event" or instrument.market_id != market_id:
                    continue
                quantity = position.quantity
                leg_payout = (
                    ONE - payout
                    if str(instrument.right or "yes").lower() == "no"
                    else payout
                )
                side = "sell" if quantity > 0 else "buy"
                order_id = "ord-st" + hashlib.sha256(
                    f"settle|{market_id}|{instrument.key}|{stamp}".encode("utf-8")
                ).hexdigest()[:26]
                order = Order(
                    id=order_id,
                    intent_id="settle-" + order_id[6:],
                    desk_id="settlement",
                    instrument=instrument,
                    side=side,
                    quantity=abs(quantity),
                    order_type="market",
                    limit_price=None,
                    time_in_force="ioc",
                    status="accepted",
                    venue=self.venue,
                    broker_order_id="sim-settle",
                    submitted_at=stamp,
                    updated_at=stamp,
                )
                if self._db.execute(
                    "SELECT 1 FROM orders WHERE id = ?", (order_id,)
                ).fetchone() is None:
                    self._insert_order(order, None)
                realized = self._apply_to_position(instrument, side, abs(quantity), leg_payout)
                proceeds = abs(quantity) * leg_payout * instrument.multiplier
                delta = proceeds if side == "sell" else -proceeds
                account = self._account()
                self._db.execute(
                    "UPDATE account SET cash = ?, realized_pnl = ?, updated_at = ? WHERE id = 1",
                    (
                        text(money(account["cash"]) + delta),
                        text(money(account["realized_pnl"]) + realized),
                        stamp,
                    ),
                )
                fill_id = "fl-" + hashlib.sha256(
                    f"settle|{order_id}|{stamp}".encode("utf-8")
                ).hexdigest()[:32]
                self._db.execute(
                    "INSERT OR IGNORE INTO fills (id, order_id, desk_id, instrument, side,"
                    " quantity, price, fee, at) VALUES (?, ?, ?, ?, ?, ?, ?, '0', ?)",
                    (
                        fill_id,
                        order_id,
                        "settlement",
                        _dumps(instrument.to_dict()),
                        side,
                        text(abs(quantity)),
                        text(leg_payout),
                        stamp,
                    ),
                )
                self._db.execute(
                    "UPDATE orders SET status = 'filled', filled_quantity = ?, average_price = ?,"
                    " updated_at = ?, reason = 'settled' WHERE id = ?",
                    (text(abs(quantity)), text(leg_payout), stamp, order_id),
                )
                settled.append(
                    Fill(
                        id=fill_id,
                        order_id=order_id,
                        desk_id="settlement",
                        instrument=instrument,
                        side=side,
                        quantity=abs(quantity),
                        price=leg_payout,
                        fee=ZERO,
                        at=stamp,
                    )
                )
            return settled

    # ------------------------------------------------------------- bookkeeping
    def deposit(self, amount: Any, *, now: Any = None) -> Balance:
        """Add (or, negative, withdraw) capital. The committee allocates this way."""
        with self._lock:
            value = money(amount)
            account = self._account()
            cash = money(account["cash"]) + value
            if cash < 0:
                raise ValueError("withdrawal exceeds cash")
            stamp = iso(now) if now is not None else self.now()
            self._db.execute(
                "UPDATE account SET cash = ?, initial_cash = ?, updated_at = ? WHERE id = 1",
                (text(cash), text(money(account["initial_cash"]) + value), stamp),
            )
            return self.balance()

    def snapshot(self) -> dict[str, Any]:
        """Everything the ledger stream needs for one `ledger.mark` event."""
        account = self._account()
        positions = self.positions()
        cash = money(account["cash"])
        equity = cash + self._positions_value()
        return {
            "venue": self.venue,
            "cash": text(cash),
            "equity": text(equity),
            "initial_cash": account["initial_cash"],
            "realized_pnl": account["realized_pnl"],
            "fees_paid": account["fees_paid"],
            "positions": [p.to_dict() for p in positions],
            "as_of": account["updated_at"],
        }


#: The book was called `PaperBroker` before the floor dropped the word "paper". Same class.
PaperBroker = ShadowBook
PAPER_CAPABILITIES = SHADOW_CAPABILITIES

__all__ = [
    "ShadowBook",
    "PaperBroker",
    "FeeModel",
    "SHADOW_CAPABILITIES",
    "SHADOW_VENUE",
    "ceil_cents",
    "quantize_cash",
    "quantize_price",
]
