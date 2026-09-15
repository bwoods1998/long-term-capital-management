"""Kalshi: binary event contracts that settle at $1.00 or $0.00.

Host `https://api.elections.kalshi.com`, every path under `/trade-api/v2`
(https://docs.kalshi.com/getting_started/api_environments).

Auth is three headers and an RSA-PSS signature over `timestamp + method + path`, where the
timestamp is in **milliseconds**, the path **includes** the `/trade-api/v2` prefix and
**excludes** the query string (https://docs.kalshi.com/getting_started/api_keys):

    KALSHI-ACCESS-KEY        the key id
    KALSHI-ACCESS-TIMESTAMP  milliseconds since the epoch, as a decimal string
    KALSHI-ACCESS-SIGNATURE  base64(RSA-PSS-SHA256(timestamp + METHOD + path))

Endpoints:

    GET    /trade-api/v2/portfolio/balance      https://docs.kalshi.com/api-reference/portfolio/get-balance
    GET    /trade-api/v2/portfolio/positions    https://docs.kalshi.com/api-reference/portfolio/get-positions
    GET    /trade-api/v2/portfolio/orders       https://docs.kalshi.com/api-reference/orders/get-orders
    POST   /trade-api/v2/portfolio/orders       (legacy create; see the note below)
    DELETE /trade-api/v2/portfolio/orders/{id}  (legacy cancel)
    GET    /trade-api/v2/portfolio/fills        https://docs.kalshi.com/api-reference/portfolio/get-fills

**Deprecation note, current as of 2026-09-15.** Order *reads* still live at
`/portfolio/orders`, but Kalshi's changelog (https://docs.kalshi.com/changelog/) moved the order
*mutations* to `/portfolio/events/orders`
(https://docs.kalshi.com/api-reference/orders/create-order-v2 and
https://docs.kalshi.com/api-reference/orders/cancel-order-v2), where `action` + `side` collapse
into one `side` of `bid`/`ask`, prices are decimal-dollar strings rather than integer cents, and
`type` is replaced by `time_in_force`. Both request shapes are implemented here and chosen with
`order_api=`; `"v2"` is the default because the legacy mutation endpoints were retired in June 2026
verified against, and `"v2"` is a one-argument migration once an account confirms it.

Money: the balance endpoint reports integer **cents**; contract prices on the legacy order
surface are integer cents from 1 to 99. Everything crossing this module's boundary is dollars as
a `Decimal`, converted by `ltcm.data.kalshi.cents_from_dollars` and its inverse.
"""

from __future__ import annotations

import urllib.parse
from decimal import Decimal
from typing import Any

from ..broker import (
    Balance,
    Fill,
    Instrument,
    Order,
    OrderIntent,
    Position,
    Quote,
    RejectedOrder,
    UnknownOutcome,
    VenueUnavailable,
    money,
)
from ..data import TransportError, iso
from ..data.kalshi import (
    HOST,
    PREFIX,
    KalshiMarketData,
    cents_from_dollars,
    dollars_from_cents,
)
from . import (
    KalshiCredentials,
    VenueClient,
    confirm_or_unknown,
    dec,
    message_of,
    require_ok,
)

VENUE = "kalshi"
ONE = Decimal(1)
HUNDRED = Decimal(100)

ORDERS_PATH = "/portfolio/orders"
ORDERS_PATH_V2 = "/portfolio/events/orders"

CAPABILITIES = {"event", "limit", "gtc", "ioc"}

#: Kalshi's three order states mapped onto this runtime's vocabulary.
STATUS_MAP: dict[str, str] = {
    "resting": "accepted",
    "pending": "accepted",
    "canceled": "cancelled",
    "cancelled": "cancelled",
    "executed": "filled",
}

TIF_V2 = {
    "gtc": "good_till_canceled",
    "day": "good_till_canceled",
    "ioc": "immediate_or_cancel",
}


def contract_side(instrument: Instrument) -> str:
    """Which leg of the market an instrument names: `yes` unless it says `no`.

    `Instrument.right` is only constrained for options, so event contracts use it to carry the
    outcome leg. An instrument with no `right` is the yes side, which is how every desk on this
    floor expresses a position.
    """
    right = str(getattr(instrument, "right", "") or "yes").lower()
    if right not in ("yes", "no"):
        raise RejectedOrder(f"kalshi: {right!r} is not a contract side; use 'yes' or 'no'")
    return right


def ticker_of(instrument: Instrument) -> str:
    ticker = (instrument.market_id or instrument.symbol or "").strip().upper()
    if not ticker:
        raise RejectedOrder("kalshi: the instrument carries no market ticker")
    return ticker


def whole_contracts(quantity: Decimal) -> int:
    """Kalshi's legacy order surface counts whole contracts."""
    value = money(quantity)
    if value != value.to_integral_value() or value <= 0:
        raise RejectedOrder(f"kalshi: {value} is not a whole number of contracts")
    return int(value)


class KalshiBroker:
    """A `Broker` over Kalshi's portfolio API, signed per request."""

    def __init__(
        self,
        credentials: KalshiCredentials,
        *,
        transport: Any = None,
        client: Any = None,
        market_data: Any = None,
        clock: Any = None,
        venue: str = VENUE,
        host: str = HOST,
        timeout: float = 20.0,
        order_api: str = "v2",
    ):
        if order_api not in ("legacy", "v2"):
            raise ValueError("order_api must be 'legacy' or 'v2'")
        self.credentials = credentials
        self.venue = venue
        self.host = host.rstrip("/")
        self.order_api = order_api
        self.client = client or VenueClient(transport, timeout=timeout)
        if clock is None:
            import time as _time

            clock = _time.time
        self.clock = clock
        self.market_data = market_data or KalshiMarketData(
            getattr(self.client, "transport", None), host=self.host, clock=clock
        )

    # --------------------------------------------------------------- signing
    def timestamp_ms(self) -> str:
        """Milliseconds since the epoch, the only form the signature header accepts."""
        return str(int(float(self.clock()) * 1000))

    def headers(self, method: str, path: str) -> dict[str, str]:
        """The three auth headers for one request. `path` must carry the prefix and no query."""
        stamp = self.timestamp_ms()
        message = (stamp + method.upper() + path).encode("utf-8")
        import base64

        signature = base64.b64encode(self.credentials.signer.sign(message)).decode("ascii")
        return {
            "KALSHI-ACCESS-KEY": self.credentials.key_id,
            "KALSHI-ACCESS-TIMESTAMP": stamp,
            "KALSHI-ACCESS-SIGNATURE": signature,
        }

    def _call(
        self,
        method: str,
        path: str,
        *,
        params: "dict[str, Any] | None" = None,
        body: Any = None,
        what: str,
        ok: tuple[int, ...] = (200, 201, 204),
    ) -> Any:
        """One signed request. The signature covers the prefixed path without its query."""
        signed_path = PREFIX + path
        url = self.host + signed_path
        if params:
            pairs = [(k, v) for k, v in params.items() if v is not None and v != ""]
            if pairs:
                url += "?" + urllib.parse.urlencode(pairs)
        status, payload = self.client.request(
            method, url, headers=self.headers(method, signed_path), body=body, what=what
        )
        return require_ok(status, payload, what=what, ok=ok)

    def capabilities(self) -> set[str]:
        return set(CAPABILITIES)

    # --------------------------------------------------------------- account
    def balance(self) -> Balance:
        """`GET /portfolio/balance`. `balance` is integer cents; `balance_dollars` is a string."""
        row = self._call("GET", "/portfolio/balance", what="kalshi balance", ok=(200,))
        if not isinstance(row, dict):
            raise VenueUnavailable("kalshi balance: unexpected response")
        cash = dec(row.get("balance_dollars")) or dollars_from_cents(row.get("balance"))
        if cash is None:
            raise VenueUnavailable("kalshi balance: no balance field")
        equity = (
            dec(row.get("portfolio_value_dollars"))
            or dollars_from_cents(row.get("portfolio_value"))
            or cash
        )
        return Balance(
            venue=self.venue,
            cash=cash,
            equity=equity,
            buying_power=cash,
            as_of=iso(self.clock()),
        )

    def positions(self) -> list[Position]:
        """`GET /portfolio/positions`. `position` is signed: positive yes, negative no."""
        payload = self._call(
            "GET", "/portfolio/positions", params={"limit": 1000}, what="kalshi positions", ok=(200,)
        )
        rows = payload.get("market_positions") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            return []
        out: list[Position] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            quantity = dec(row.get("position_fp")) or dec(row.get("position"))
            ticker = str(row.get("ticker") or "").strip().upper()
            if not ticker or quantity is None or quantity == 0:
                continue
            exposure = (
                dec(row.get("market_exposure_dollars"))
                or dollars_from_cents(row.get("market_exposure"))
                or money(0)
            )
            average = abs(exposure) / abs(quantity) if quantity else money(0)
            out.append(
                Position(
                    instrument=Instrument("event", ticker, self.venue, market_id=ticker),
                    quantity=quantity,
                    average_cost=average,
                )
            )
        return out

    def quote(self, instrument: Instrument) -> Quote:
        """Public market data; no signature is needed to read a price."""
        return self.market_data.quote(instrument)

    # ---------------------------------------------------------------- orders
    def order_body(self, intent: OrderIntent) -> dict[str, Any]:
        """The create-order request body for the configured order API."""
        ticker = ticker_of(intent.instrument)
        count = whole_contracts(intent.quantity)
        side = contract_side(intent.instrument)
        if self.order_api == "legacy":
            body: dict[str, Any] = {
                "ticker": ticker,
                "action": intent.side,  # buy | sell
                "side": side,  # yes | no
                "count": count,
                "type": intent.order_type,  # market | limit
                "client_order_id": intent.id,
            }
            if intent.order_type == "limit":
                body["yes_price" if side == "yes" else "no_price"] = cents_from_dollars(
                    intent.limit_price
                )
            elif intent.side == "buy":
                # A market buy must declare the worst it may cost. One contract can never settle
                # above $1.00, so `count` dollars, in cents, is the true ceiling.
                body["buy_max_cost"] = count * 100
            return body
        # v2: one `side` names the book side, and "bid" is yes, "ask" is no, always
        # (https://docs.kalshi.com/getting_started/order_direction).
        book_side = "bid" if side == "yes" else "ask"
        if intent.side == "sell":
            book_side = "ask" if side == "yes" else "bid"
        if side != "yes":
            # Price scaling for the NO leg on the v2 surface is not documented unambiguously;
            # until a live test settles it, this floor expresses every view on the YES leg.
            raise RejectedOrder("kalshi v2: only YES-leg contracts are traded on this floor")
        time_in_force = TIF_V2.get(intent.time_in_force, "good_till_canceled")
        if intent.order_type == "limit":
            price = money(intent.limit_price)
        else:
            # v2 has no market order: cross the touch with an immediate-or-cancel limit.
            quote = self.quote(intent.instrument)
            price = quote.reference(intent.side)
            if price is None or price <= 0:
                raise RejectedOrder("kalshi v2: no quote to price a market order against")
            time_in_force = "immediate_or_cancel"
        if not (Decimal("0.01") <= price <= Decimal("0.99")):
            raise RejectedOrder("kalshi v2: price must be between 0.01 and 0.99 dollars")
        body = {
            "ticker": ticker,
            "side": book_side,
            "count": format(Decimal(count).quantize(Decimal("0.01")), "f"),
            "price": format(price.quantize(Decimal("0.0001")), "f"),
            "time_in_force": time_in_force,
            "self_trade_prevention_type": "taker_at_cross",
            "client_order_id": intent.id,
        }
        if intent.side == "sell":
            body["reduce_only"] = True
        return body

    def submit(self, intent: OrderIntent) -> Order:
        """Create an order. `client_order_id` is the intent id, so a retry is never a new order."""
        if intent.instrument.asset_class != "event":
            raise RejectedOrder(f"kalshi trades event contracts, not {intent.instrument.asset_class}")
        path = ORDERS_PATH if self.order_api == "legacy" else ORDERS_PATH_V2
        body = self.order_body(intent)
        try:
            payload = self._call("POST", path, body=body, what="kalshi submit")
        except TransportError as exc:
            return confirm_or_unknown(
                lambda: self.order_by_client_id(intent.id),
                what="kalshi submit",
                detail=f"no response ({type(exc).__name__})",
            )
        row = payload.get("order") if isinstance(payload, dict) and "order" in payload else payload
        if not isinstance(row, dict):
            raise UnknownOutcome("kalshi submit: unreadable response; reconcile before retrying")
        return self.parse_order(row, intent=intent)

    def orders(self, *, status: "str | None" = None, limit: int = 200) -> list[Order]:
        """`GET /portfolio/orders`. `status` is `resting`, `canceled` or `executed`."""
        payload = self._call(
            "GET",
            ORDERS_PATH,
            params={"status": status, "limit": max(1, min(int(limit), 1000))},
            what="kalshi orders",
            ok=(200,),
        )
        rows = payload.get("orders") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            return []
        return [self.parse_order(row) for row in rows if isinstance(row, dict)]

    def open_orders(self) -> list[Order]:
        return self.orders(status="resting")

    def order_by_client_id(self, client_order_id: str) -> "Order | None":
        """Kalshi cannot filter by client order id, so recent orders are scanned locally."""
        for status in ("resting", "executed", "canceled"):
            for order in self.orders(status=status, limit=200):
                if order.intent_id == client_order_id:
                    return order
        return None

    def get_order(self, order_id: str) -> Order:
        if isinstance(order_id, str) and order_id.startswith("ord-"):
            found = self.order_by_client_id("oi-" + order_id[4:])
        else:
            found = next(
                (
                    order
                    for status in ("resting", "executed", "canceled")
                    for order in self.orders(status=status, limit=200)
                    if order.broker_order_id == order_id
                ),
                None,
            )
        if found is None:
            raise RejectedOrder(f"kalshi: no order for {order_id}")
        return found

    def cancel(self, order_id: str) -> Order:
        """`DELETE /portfolio/orders/{id}` reduces a resting order to zero."""
        order = self.get_order(order_id)
        if order.terminal:
            return order
        venue_id = order.broker_order_id or order_id
        path = (ORDERS_PATH if self.order_api == "legacy" else ORDERS_PATH_V2) + "/" + str(venue_id)
        self._call("DELETE", path, what="kalshi cancel", ok=(200, 201, 204))
        order.status = "cancelled"
        order.reason = "cancelled by request"
        order.updated_at = iso(self.clock())
        return order

    # ----------------------------------------------------------------- fills
    def fills(self, since: "str | None" = None) -> list[Fill]:
        """`GET /portfolio/fills`, oldest first. Prices are cents; `fee_cost` is dollars."""
        params: dict[str, Any] = {"limit": 1000}
        if since:
            params["min_ts"] = int(_epoch_seconds(since))
        payload = self._call("GET", "/portfolio/fills", params=params, what="kalshi fills", ok=(200,))
        rows = payload.get("fills") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            return []
        out: list[Fill] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            parsed = self.parse_fill(row)
            if parsed is not None:
                out.append(parsed)
        out.sort(key=lambda fill: fill.at)
        return out

    def parse_fill(self, row: dict[str, Any]) -> "Fill | None":
        ticker = str(row.get("ticker") or row.get("market_ticker") or "").strip().upper()
        count = dec(row.get("count_fp")) or dec(row.get("count"))
        if not ticker or count is None or count <= 0:
            return None
        leg = str(row.get("outcome_side") or row.get("side") or "yes").lower()
        field = "no_price" if leg == "no" else "yes_price"
        price = dec(row.get(field + "_dollars")) or dollars_from_cents(row.get(field))
        if price is None:
            return None
        action = str(row.get("action") or "").lower()
        if action not in ("buy", "sell"):
            # The fixed-point surface replaced `action` with `book_side`: bid is a buy.
            action = "buy" if str(row.get("book_side") or "bid").lower() == "bid" else "sell"
        fee = dec(row.get("fee_cost_dollars")) or dec(row.get("fee_cost")) or money(0)
        return Fill(
            id=str(row.get("fill_id") or row.get("trade_id") or ""),
            order_id=str(row.get("order_id") or ""),
            desk_id="",
            instrument=Instrument(
                "event", ticker, self.venue, market_id=ticker, right=leg
            ),
            side=action,
            quantity=count,
            price=price,
            fee=abs(fee),
            at=iso(row.get("created_time") or row.get("ts") or 0),
        )

    # --------------------------------------------------------------- parsing
    def parse_order(self, row: dict[str, Any], *, intent: "OrderIntent | None" = None) -> Order:
        ticker = str(row.get("ticker") or (ticker_of(intent.instrument) if intent else "")).upper()
        leg = str(row.get("outcome_side") or row.get("side") or "yes").lower()
        if leg not in ("yes", "no"):
            leg = "yes"
        instrument = (
            intent.instrument
            if intent is not None
            else Instrument("event", ticker, self.venue, market_id=ticker, right=leg)
        )
        client_order_id = str(row.get("client_order_id") or (intent.id if intent else ""))
        field = "no_price" if leg == "no" else "yes_price"
        limit_price = dec(row.get(field + "_dollars")) or dollars_from_cents(row.get(field))
        filled = dec(row.get("fill_count_fp")) or dec(row.get("fill_count")) or money(0)
        remaining = dec(row.get("remaining_count_fp")) or dec(row.get("remaining_count"))
        initial = (
            dec(row.get("initial_count_fp"))
            or dec(row.get("initial_count"))
            or (filled + remaining if remaining is not None else None)
            or (intent.quantity if intent else filled)
        )
        raw_status = str(row.get("status") or "").lower()
        if raw_status:
            status = STATUS_MAP.get(raw_status, "unknown")
        else:
            # The v2 create response has no status; a full fill is the only terminal outcome
            # it can report inline.
            status = "filled" if remaining == 0 and filled > 0 else "accepted"
        fees = (
            (dec(row.get("taker_fees_dollars")) or money(0))
            + (dec(row.get("maker_fees_dollars")) or money(0))
        )
        order = Order(
            id="ord-" + client_order_id[3:] if client_order_id.startswith("oi-") else
               ("ord-" + client_order_id if client_order_id else "ord-" + str(row.get("order_id") or "")),
            intent_id=client_order_id,
            desk_id=intent.desk_id if intent else "",
            instrument=instrument,
            side=_action_of(row, intent),
            quantity=initial or money(0),
            order_type=str(row.get("type") or (intent.order_type if intent else "limit")),
            limit_price=limit_price,
            time_in_force=intent.time_in_force if intent else "gtc",
            status=status,
            venue=self.venue,
            broker_order_id=str(row.get("order_id") or "") or None,
            filled_quantity=filled,
            average_price=dec(row.get("average_fill_price")) or limit_price if filled else None,
            fees=fees,
            submitted_at=_stamp(row.get("created_time")) or iso(self.clock()),
            updated_at=_stamp(row.get("last_update_time") or row.get("created_time")),
            reason=message_of(row) if status == "rejected" else None,
        )
        order._raw = {"status": row.get("status")}
        return order


def _action_of(row: dict[str, Any], intent: "OrderIntent | None") -> str:
    action = str(row.get("action") or "").lower()
    if action in ("buy", "sell"):
        return action
    book_side = str(row.get("book_side") or "").lower()
    if book_side in ("bid", "ask"):
        return "buy" if book_side == "bid" else "sell"
    return intent.side if intent else "buy"


def _stamp(value: Any) -> "str | None":
    if not value:
        return None
    try:
        return iso(value)
    except Exception:
        return None


def _epoch_seconds(value: Any) -> float:
    from ..data import to_datetime

    return to_datetime(value).timestamp()


__all__ = [
    "KalshiBroker",
    "KalshiCredentials",
    "contract_side",
    "ticker_of",
    "whole_contracts",
    "ORDERS_PATH",
    "ORDERS_PATH_V2",
    "STATUS_MAP",
    "CAPABILITIES",
    "HOST",
    "PREFIX",
]
