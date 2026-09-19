"""The Kalshi shadow account: rung 1, the forward paper test for Kalshi strategies.

`KalshiShadowBroker` is a `Broker` (`ltcm/broker.py`) over a simulated Kalshi account. It reads
real, live Kalshi quotes, fills under the conservative rules below, charges the venue's real fee
model (`league.fees.Fees("kalshi")`) and never sends an order anywhere: it holds no credential
and has no transport of its own. `league.book.Book` drives it exactly as it drives the real
adapters, so a strategy's paper record is kept by the same code that will keep its real one.

Legs are the real adapter's (`ltcm/adapters/kalshi.py`): `Instrument.right` is `"yes"` or `"no"`
(none is YES), symbol and `market_id` are the market ticker, a price is dollars on the order's
own leg, quantities are whole contracts. A NO order is priced and quoted in NO dollars.

Fill rules. Conservative means: where the tape cannot say whether a real order would have
filled, this account says it did not.

1. Only event contracts of this venue, in whole contracts, at a limit strictly between $0 and $1
   that sits on the market's own price grid (`price_ranges`, else whole cents), exactly as the
   real adapter refuses them: anything else raises `RejectedOrder` and no order is recorded.
2. `submit` is idempotent on the intent id. The same intent again returns the stored order,
   whatever became of it; nothing is quoted or filled twice.
3. A market order needs a two-sided quote, else it is `rejected`. It fills in full at the touch
   (a buy at the leg's ask, a sell at the leg's bid) as a taker.
4. A limit order that crosses the touch (buy limit >= ask, sell limit <= bid) is `rejected` when
   it is post-only ("post-only order would cross"); otherwise it fills in full AT THE TOUCH, not
   at its limit, as a taker.
5. A limit order that does not cross rests (`accepted`); an immediate-or-cancel one is
   `cancelled` instead. A resting order fills only in `advance()`, in full, at its own price, as
   a maker, and only when the market has traded THROUGH it: a resting buy at p when the leg's
   ask is strictly below p, a resting sell at p when the leg's bid is strictly above p. A real
   resting order sits behind everyone who bid that price first, so a touch at p proves nothing;
   an ask under p cannot exist while a bid at p is still there.
6. An order whose `expires_at` has passed, or whose market is no longer open (a status other
   than active/open, a result, or a `close_time` in the past), becomes `expired`. Expiry is
   checked before a fill: whatever traded through after the venue would have cancelled the
   order is not the order's. A new order on such a market is `rejected`.
7. No leverage and no shorts, at the account level (the Book checks each agent; this is the
   backstop). A buy needs free cash for price x quantity plus the fee, a sell needs the free
   position; resting buys hold their cash and resting sells their contracts, as Kalshi
   collateralizes a resting order. Otherwise the order is `rejected`. Betting against a market
   is buying its NO leg.
8. Fees are `Fees("kalshi").charge(...)`: a taker pays 0.07 x C x P x (1 - P) times the series
   multiplier, rounded up to $0.0001 an order; a maker pays nothing except on the series that
   charge makers. The fee is on `Order.fees` and `Fill.fee`, and cash moves by
   price x quantity plus the fee on a buy, less the fee on a sell.
9. A market that reports a result of yes or no pays $1.00 for each contract of the winning leg
   and nothing for the other (`settlements()`); its resting orders expire.

What is NOT modelled: depth and queue position. Every order here is $1 to $75, so a fill is all
or nothing at one price, and two resting orders at one price both fill when the market trades
through them. A voided or scalar result is not settled: the position stays until someone looks.

State (cash, positions, every order, every fill, every settlement applied, the order counter)
is one JSON file, money as decimal strings, rewritten atomically (temp file, fsync,
`os.replace`, mode 0600) after every mutation and loaded on construction, so a House restart
loses nothing. A write that fails undoes the mutation in memory and raises `VenueUnavailable`.
`starting_cash` only matters when the file does not exist yet.

One lock guards the account. `submit`, `advance` and `settlements` read market data while they
hold it, so two threads never see half an order; `quote` alone reads without it.
"""

from __future__ import annotations

import dataclasses
import json
import os
import threading
import time
from decimal import Decimal
from pathlib import Path
from typing import Any

from ltcm.adapters.kalshi import DEFAULT_PRICE_RANGES, contract_side, on_grid, ticker_of, whole_contracts
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
from ltcm.data.kalshi import parse_price_ranges

from .fees import Fees
from .ledger import now_iso

ZERO = Decimal(0)
ONE = Decimal(1)
STATE_VERSION = 1
CAPABILITIES = frozenset({"event", "limit", "gtc", "ioc", "no_leg", "shadow"})
#: `GET /markets/{ticker}` says `active`; the listing filter says `open`. Anything else that is
#: named (`initialized`, `inactive`, `paused`, `closed`, `determined`, `settled`, `finalized`
#: ...) is a market that takes no orders.
OPEN_MARKET_STATUSES = ("active", "open")
RESULTS = ("yes", "no")


def _text(value: Decimal | None) -> str | None:
    return None if value is None else format(value, "f")


def _positive(value: Decimal | None) -> Decimal | None:
    """A price that is there: Kalshi shows an empty side as zero or as nothing."""
    return value if value is not None and value > 0 else None


class KalshiShadowBroker:
    """A simulated Kalshi account on live quotes. See the module docstring for the fill rules."""

    def __init__(
        self,
        state_path: str | os.PathLike,
        market_data: Any,
        *,
        venue: str = "kalshi-shadow",
        starting_cash: Any = "100000",
        clock=time.time,
        fees: Fees | None = None,
    ):
        self.venue = venue
        self.state_path = Path(state_path)
        self.market_data = market_data
        self.clock = clock
        self.fees = fees or Fees("kalshi")
        self._lock = threading.RLock()
        self._cash = money(starting_cash)
        if self._cash < 0:
            raise ValueError("starting_cash must not be negative")
        #: instrument key -> {"instrument", "quantity", "cost"}; cost is price x quantity, fees apart
        self._positions: dict[str, dict[str, Any]] = {}
        self._orders: dict[str, Order] = {}  # by "ord-..." id, in submission order
        self._by_broker_id: dict[str, str] = {}
        self._fills: list[Fill] = []
        self._settlements: list[dict[str, Any]] = []
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
                key: {
                    "instrument": held["instrument"].to_dict(),
                    "quantity": _text(held["quantity"]),
                    "cost": _text(held["cost"]),
                }
                for key, held in self._positions.items()
            },
            "orders": [_order_to_dict(order) for order in self._orders.values()],
            "fills": [fill.to_dict() for fill in self._fills],
            "settlements": [
                {**row, "yes_count": _text(row["yes_count"]), "no_count": _text(row["no_count"]), "revenue": _text(row["revenue"])}
                for row in self._settlements
            ],
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
        """Write the mutation just made, or take it back. A disk that cannot be written (the floor's
        filled once, on Sept 16, 2026) must not leave an order that is filled in memory and unknown
        to the file the next process starts from: memory goes back to what the file says, and the
        caller is told the venue was unavailable, which the Book records as an order that never was."""
        try:
            self._save()
        except OSError as exc:
            self._load()
            raise VenueUnavailable(f"{self.venue}: the account could not be written, nothing was changed: {exc}") from exc

    def _load(self) -> None:
        """Read the account back. A file that cannot be read is an error, never a fresh account:
        quietly starting again at `starting_cash` would erase a strategy's whole paper record."""
        try:
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
            if not isinstance(state, dict) or state.get("version") != STATE_VERSION:
                raise ValueError(f"not a version {STATE_VERSION} shadow account")
            if state.get("venue") != self.venue:
                raise ValueError(f"it is the account of {state.get('venue')!r}, not {self.venue!r}")
            self._cash = money(state["cash"])
            self._next_order = int(state["next_order"])
            self._next_fill = int(state["next_fill"])
            self._positions = {
                key: {
                    "instrument": Instrument.from_dict(held["instrument"]),
                    "quantity": money(held["quantity"]),
                    "cost": money(held["cost"]),
                }
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
            self._settlements = [
                {
                    "ticker": str(row["ticker"]),
                    "result": str(row["result"]),
                    "yes_count": money(row["yes_count"]),
                    "no_count": money(row["no_count"]),
                    "revenue": money(row["revenue"]),
                    "settled_time": str(row["settled_time"]),
                }
                for row in state["settlements"]
            ]
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
            raise BrokerError(f"shadow account {self.state_path} cannot be read: {exc}") from exc

    # ------------------------------------------------------------ market data
    def _read_quote(self, instrument: Instrument) -> Quote:
        """The leg's own bid and ask. `KalshiMarketData.quote` reads only the ticker and the leg,
        never the venue, so the shadow venue's instrument goes to it as it is; a source that
        answers about another instrument object is re-wrapped so the quote names ours."""
        quote = self.market_data.quote(instrument)
        if not isinstance(quote, Quote):
            raise VenueUnavailable(f"{self.venue}: market data returned no quote for {instrument.key}")
        if quote.instrument != instrument:
            quote = dataclasses.replace(quote, instrument=instrument)
        return quote

    def _try_quote(self, instrument: Instrument) -> tuple[Quote | None, str]:
        try:
            return self._read_quote(instrument), ""
        except Exception as exc:  # noqa: BLE001 - a source that cannot quote decides no fill
            return None, f"{type(exc).__name__}: {exc}"

    def _try_market(self, ticker: str) -> dict[str, Any] | None:
        """The parsed market row, or None when it cannot be read (which decides nothing)."""
        reader = getattr(self.market_data, "market", None)
        if reader is None:
            return None
        try:
            row = reader(ticker)
        except Exception:  # noqa: BLE001
            return None
        return row if isinstance(row, dict) else None

    @staticmethod
    def _result_of(row: dict[str, Any] | None) -> str:
        if not row:
            return ""
        result = str(row.get("result") or row.get("market_result") or "").strip().lower()
        return result if result in RESULTS else ""

    def _closed_reason(self, row: dict[str, Any] | None, now: str) -> str:
        """Why this market takes no orders now, or "" when it is open as far as anyone can say."""
        if not row:
            return ""
        result = self._result_of(row)
        if result:
            return f"the market has resolved {result}"
        status = str(row.get("status") or "").strip().lower()
        if status and status not in OPEN_MARKET_STATUSES:
            return f"the market is {status}"
        closes, moment = instant(row.get("close_time")), instant(now)
        if closes is not None and moment is not None and closes <= moment:
            return f"the market closed at {row.get('close_time')}"
        return ""

    # ------------------------------------------------------------- accounting
    def _maker_hold(self, order: Order) -> Decimal:
        """What a resting buy keeps aside: its cost at its limit and the fee it would pay."""
        fee = self.fees.charge(order.instrument, "buy", order.remaining, order.limit_price, liquidity="maker").usd
        return order.remaining * order.limit_price + fee

    def _free_cash(self, *, excluding: str | None = None) -> Decimal:
        held = ZERO
        for order in self._orders.values():
            if order.status == "accepted" and order.side == "buy" and order.id != excluding:
                held += self._maker_hold(order)
        return self._cash - held

    def _free_position(self, key: str, *, excluding: str | None = None) -> Decimal:
        quantity = self._positions[key]["quantity"] if key in self._positions else ZERO
        for order in self._orders.values():
            if order.status == "accepted" and order.side == "sell" and order.id != excluding and order.instrument.key == key:
                quantity -= order.remaining
        return quantity

    def _refusal(self, order: Order, price: Decimal, liquidity: str) -> str:
        """Why the account cannot carry this order at this price, or ""."""
        if order.side == "buy":
            fee = self.fees.charge(order.instrument, "buy", order.remaining, price, liquidity=liquidity).usd
            need = order.remaining * price + fee
            free = self._free_cash(excluding=order.id)
            if need > free:
                return f"insufficient cash: needs ${need:.4f} with fees, the account has ${free:.4f} free"
            return ""
        free = self._free_position(order.instrument.key, excluding=order.id)
        if order.remaining > free:
            return f"no position to sell: {order.remaining} asked, {free} held and free (shorts are not allowed; buy the other leg)"
        return ""

    def _fill(self, order: Order, price: Decimal, liquidity: str, now: str) -> None:
        """All of the order, at one price. The caller has checked `_refusal`."""
        instrument, quantity = order.instrument, order.remaining
        fee = self.fees.charge(instrument, order.side, quantity, price, liquidity=liquidity).usd
        gross = quantity * price
        key = instrument.key
        if order.side == "buy":
            self._cash -= gross + fee
            held = self._positions.setdefault(key, {"instrument": instrument, "quantity": ZERO, "cost": ZERO})
            held["quantity"] += quantity
            held["cost"] += gross
        else:
            self._cash += gross - fee
            held = self._positions[key]
            held["cost"] -= held["cost"] * quantity / held["quantity"]
            held["quantity"] -= quantity
            if held["quantity"] <= 0:
                del self._positions[key]
        order.filled_quantity = order.filled_quantity + quantity
        order.average_price = price
        order.fees = order.fees + fee
        order.status = "filled"
        order.updated_at = now
        order._raw["liquidity"] = liquidity
        self._fills.append(
            Fill(
                id=f"shadow-fill-{self._next_fill}",
                order_id=order.id,
                desk_id=order.desk_id,
                instrument=instrument,
                side=order.side,
                quantity=quantity,
                price=price,
                fee=fee,
                at=now,
            )
        )
        self._next_fill += 1

    @staticmethod
    def _close(order: Order, status: str, reason: str, now: str) -> None:
        order.status = status
        order.reason = reason
        order.updated_at = now

    @staticmethod
    def _copy(order: Order) -> Order:
        """Callers get their own object: nothing outside the lock can edit the account's record."""
        return dataclasses.replace(order, _raw=dict(order._raw))

    # --------------------------------------------------------------- protocol
    def capabilities(self) -> set[str]:
        return set(CAPABILITIES)

    def balance(self) -> Balance:
        """Equity is cash plus positions at cost: no quote is read, so it never fails."""
        with self._lock:
            at_cost = sum((held["cost"] for held in self._positions.values()), ZERO)
            return Balance(self.venue, self._cash, self._cash + at_cost, self._cash, self._now())

    def positions(self) -> list[Position]:
        with self._lock:
            now = self._now()
            return [
                Position(held["instrument"], held["quantity"], held["cost"] / held["quantity"], as_of=now)
                for held in self._positions.values()
                if held["quantity"] != 0
            ]

    def quote(self, instrument: Instrument) -> Quote:
        try:
            return self._read_quote(instrument)
        except BrokerError:
            raise
        except Exception as exc:  # noqa: BLE001 - one error family for every caller
            raise VenueUnavailable(f"{self.venue}: no quote for {instrument.key}: {exc}") from exc

    def _validate(self, intent: OrderIntent) -> str:
        """Refuse what the real adapter refuses before it sends. Returns the market ticker."""
        instrument = intent.instrument
        if instrument.asset_class != "event":
            raise RejectedOrder(f"{self.venue} trades event contracts, not {instrument.asset_class}")
        if instrument.venue != self.venue:
            raise RejectedOrder(f"instrument venue {instrument.venue!r} is not {self.venue!r}")
        if instrument.multiplier != ONE:
            raise RejectedOrder("an event contract pays one dollar: the multiplier must be 1")
        contract_side(instrument)
        whole_contracts(intent.quantity)
        if intent.order_type == "limit" and not ZERO < intent.limit_price < ONE:
            raise RejectedOrder(f"an event contract price is between $0 and $1, not {intent.limit_price}")
        return ticker_of(instrument)

    def submit(self, intent: OrderIntent) -> Order:
        with self._lock:
            order = Order.from_intent(intent, venue=self.venue)
            stored = self._orders.get(order.id)
            if stored is not None:
                return self._copy(stored)
            ticker = self._validate(intent)
            row = self._try_market(ticker)
            if intent.order_type == "limit":
                # The grid is the market's, on the YES scale the wire uses, as the real adapter checks it.
                bands = tuple(parse_price_ranges((row or {}).get("price_ranges"))) or DEFAULT_PRICE_RANGES
                wire = intent.limit_price if contract_side(intent.instrument) == "yes" else ONE - intent.limit_price
                if not on_grid(wire, bands):
                    raise RejectedOrder(f"{format(intent.limit_price, 'f')} is not on {ticker}'s price grid")
            now = self._now()
            order.broker_order_id = f"shadow-{self._next_order}"
            self._next_order += 1
            order.submitted_at = order.updated_at = now
            order._raw = {"post_only": bool(intent.post_only), "expires_at": intent.expires_at, "liquidity": None}
            self._orders[order.id] = order
            self._by_broker_id[order.broker_order_id] = order.id
            self._decide(order, row, now)
            self._commit()
            return self._copy(order)

    def _decide(self, order: Order, row: dict[str, Any] | None, now: str) -> None:
        """A new order's fate: rejected, filled at the touch, cancelled (ioc), expired or resting."""
        closed = self._closed_reason(row, now)
        if closed:
            return self._close(order, "rejected", closed, now)
        if self._expired(order, now):
            return self._close(order, "expired", f"expired at {order._raw.get('expires_at')}", now)
        quote, problem = self._try_quote(order.instrument)
        if quote is None:
            return self._close(order, "rejected", f"no quote to price the order against ({problem})", now)
        bid, ask = _positive(quote.bid), _positive(quote.ask)
        touch = ask if order.side == "buy" else bid
        if order.order_type == "market":
            if bid is None or ask is None:
                return self._close(order, "rejected", "no two-sided quote to fill a market order against", now)
            crosses = True
        else:
            crosses = touch is not None and (order.limit_price >= touch if order.side == "buy" else order.limit_price <= touch)
        if crosses:
            if order._raw.get("post_only"):
                return self._close(order, "rejected", "post-only order would cross", now)
            refusal = self._refusal(order, touch, "taker")
            if refusal:
                return self._close(order, "rejected", refusal, now)
            return self._fill(order, touch, "taker", now)
        if order.time_in_force == "ioc":
            return self._close(order, "cancelled", "immediate-or-cancel order did not cross", now)
        refusal = self._refusal(order, order.limit_price, "maker")
        if refusal:
            return self._close(order, "rejected", refusal, now)
        order.status = "accepted"

    @staticmethod
    def _expired(order: Order, now: str) -> bool:
        expires, moment = instant(order._raw.get("expires_at")), instant(now)
        return expires is not None and moment is not None and expires <= moment

    def _find(self, order_id: str) -> Order:
        order = self._orders.get(order_id) or self._orders.get(self._by_broker_id.get(order_id, ""))
        if order is None:
            raise RejectedOrder(f"{self.venue} has no order {order_id}")
        return order

    def get_order(self, order_id: str) -> Order:
        with self._lock:
            return self._copy(self._find(order_id))

    def cancel(self, order_id: str) -> Order:
        with self._lock:
            order = self._find(order_id)
            if not order.terminal:
                self._close(order, "cancelled", "cancelled by request", self._now())
                self._commit()
            return self._copy(order)

    def open_orders(self) -> list[Order]:
        with self._lock:
            return [self._copy(order) for order in self._orders.values() if not order.terminal]

    def fills(self, since: str | None = None) -> list[Fill]:
        floor = _cursor(since)
        with self._lock:
            return [fill for fill in self._fills if _at_or_after(fill.at, floor)]

    # ---------------------------------------------------------------- advance
    def advance(self) -> int:
        """Re-quote every instrument with a resting order; expire and fill by rules 5 and 6.
        Returns how many orders changed. A market or a quote that cannot be read changes nothing:
        the order waits for the next call."""
        with self._lock:
            resting = [order for order in self._orders.values() if order.status == "accepted"]
            if not resting:
                return 0
            now = self._now()
            markets: dict[str, dict[str, Any] | None] = {}
            quotes: dict[str, Quote | None] = {}
            changed = 0
            for order in resting:
                if self._expired(order, now):
                    self._close(order, "expired", f"expired at {order._raw.get('expires_at')}", now)
                    changed += 1
                    continue
                ticker = ticker_of(order.instrument)
                if ticker not in markets:
                    markets[ticker] = self._try_market(ticker)
                row = markets[ticker]
                if row is None:
                    continue
                closed = self._closed_reason(row, now)
                if closed:
                    self._close(order, "expired", closed, now)
                    changed += 1
                    continue
                key = order.instrument.key
                if key not in quotes:
                    quotes[key] = self._try_quote(order.instrument)[0]
                quote = quotes[key]
                if quote is None:
                    continue
                bid, ask = _positive(quote.bid), _positive(quote.ask)
                if order.side == "buy":
                    through = ask is not None and ask < order.limit_price
                else:
                    through = bid is not None and bid > order.limit_price
                if not through:
                    continue
                refusal = self._refusal(order, order.limit_price, "maker")
                if refusal:  # holds make this unreachable; an account that cannot pay still never fills
                    self._close(order, "cancelled", refusal, now)
                else:
                    self._fill(order, order.limit_price, "maker", now)
                changed += 1
            if changed:
                self._commit()
            return changed

    # ------------------------------------------------------------ settlements
    def settlements(self, since: str | None = None) -> list[dict[str, Any]]:
        """Settle every held market that reports a result, once, and return every settlement
        recorded at or after `since` (all of them when None), oldest first, shaped like the real
        adapter's `parse_settlement`.

        `settled_time` is when THIS account applied the settlement, not the market's own stamp:
        a caller that keeps the last `settled_time` it handled as its cursor can then never be
        handed a settlement dated before its cursor. Rows applied on earlier calls come back
        too, so a caller that crashed between this call and its own bookkeeping reads them again.
        """
        floor = _cursor(since)
        with self._lock:
            held: dict[str, dict[str, Decimal]] = {}
            for position in self._positions.values():
                legs = held.setdefault(ticker_of(position["instrument"]), {"yes": ZERO, "no": ZERO})
                legs[contract_side(position["instrument"])] += position["quantity"]
            applied = False
            for ticker in sorted(held):
                result = self._result_of(self._try_market(ticker))
                if not result:
                    continue
                now = self._now()
                revenue = held[ticker][result] * ONE
                self._cash += revenue
                for key in [k for k, p in self._positions.items() if ticker_of(p["instrument"]) == ticker]:
                    del self._positions[key]
                for order in self._orders.values():
                    if order.status == "accepted" and ticker_of(order.instrument) == ticker:
                        self._close(order, "expired", f"the market has resolved {result}", now)
                self._settlements.append(
                    {
                        "ticker": ticker,
                        "result": result,
                        "yes_count": held[ticker]["yes"],
                        "no_count": held[ticker]["no"],
                        "revenue": revenue,
                        "settled_time": now,
                    }
                )
                applied = True
            if applied:
                self._commit()
            rows = [dict(row) for row in self._settlements if _at_or_after(row["settled_time"], floor)]
            rows.sort(key=lambda row: (row["settled_time"], row["ticker"]))
            return rows


# ------------------------------------------------------------------------------- serialization
def _cursor(since: str | None):
    """`since` as a moment, or None for "everything". A cursor that is not a time is an error: an
    empty answer would read as "nothing settled" to a caller that had simply mangled its cursor."""
    if since is None:
        return None
    floor = instant(since)
    if floor is None:
        raise ValueError(f"since must be an ISO-8601 timestamp, not {since!r}")
    return floor


def _at_or_after(stamp: str, floor) -> bool:
    moment = instant(stamp)
    return floor is None or moment is None or moment >= floor


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


__all__ = ["KalshiShadowBroker", "CAPABILITIES", "OPEN_MARKET_STATUSES"]
