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

**Legs.** The v2 endpoint quotes everything from the YES side. From the `BookSide` schema
(https://docs.kalshi.com/api-reference/orders/create-order-v2): *"Side of the book for an order
or trade. For event markets, this refers to the YES leg only: `bid` means buy YES, `ask` means
sell YES. (Selling YES is economically equivalent to buying NO at `1 - price`, but this endpoint
quotes everything from the YES side.)"* and, from
https://docs.kalshi.com/getting_started/order_direction, *"`bid` = yes, `ask` = no, always"*
with *"buy-no and sell-yes both produce long no"*. **There is no `no_price` field on v2.**

So a desk that wants the NO leg names it on the instrument (`right="no"`) and quotes its own
price in NO dollars; `order_body` sends `side` from the table below and `price = 1 - that`, once:

    desk side   leg    book_side   wire price
    buy         yes    bid         p
    sell        yes    ask         p
    buy         no     ask         1 - p
    sell        no     bid         1 - p

A market order has no price of its own, so it is crossed as an immediate-or-cancel limit at the
touch **read from the YES leg**, which is already the wire's scale and is therefore never
complemented again. Buying NO is selling YES, so the book side decides which touch is crossed.
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

CAPABILITIES = {"event", "limit", "gtc", "ioc", "no_leg"}

#: How long a market's `price_ranges` is trusted before it is read again.
PRICE_RANGE_TTL_SECONDS = 600.0

#: The grid every Kalshi market priced in whole cents accepts, used only when a market
#: publishes no `price_ranges` of its own.
DEFAULT_PRICE_RANGES: tuple[dict[str, Decimal], ...] = (
    {"start": Decimal("0.01"), "end": Decimal("0.99"), "step": Decimal("0.01")},
)

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


def yes_leg(instrument: Instrument) -> Instrument:
    """The same contract named on its YES leg, for reading the wire's own price scale."""
    if str(getattr(instrument, "right", "") or "yes").lower() == "yes":
        return instrument
    import dataclasses

    return dataclasses.replace(instrument, right="yes")


def on_grid(price: Decimal, bands: "list[dict[str, Decimal]] | tuple[dict[str, Decimal], ...]") -> bool:
    """True when `price` sits on one of the market's `{start, end, step}` bands, inclusive.

    A band is a closed interval and a step, so 0.01..0.99 step 0.01 accepts $0.37 and refuses
    $0.375, while a centi-cent band accepts both. The arithmetic is exact `Decimal` remainder;
    a float here would reject a legitimate price roughly one time in a thousand.
    """
    for band in bands:
        start, end, step = band["start"], band["end"], band["step"]
        if step <= 0 or not (start <= price <= end):
            continue
        if (price - start) % step == 0:
            return True
    return False


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
        #: ticker -> (read_at_epoch_seconds, bands). A market's grid does not move intraday,
        #: so one read covers every order on it for ten minutes.
        self._price_ranges: dict[str, tuple[float, tuple[dict[str, Decimal], ...]]] = {}

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

    def upgrade_api_tier(self) -> Any:
        """`POST /account/api_usage_level/upgrade`: the free, permanent Advanced tier.

        https://docs.kalshi.com/api-reference/account/upgrade-account-api-usage-level:
        "Grants a permanent Advanced API usage-level grant... Criteria: at least 1 of the
        user's last 100 Predictions orders was created via API." Basic's write budget is 100
        tokens a second and Advanced's 300; an order costs 10. A 403 means the criteria are
        not met yet and is raised as a `BrokerError` for the caller to retry later.
        """
        return self._call(
            "POST", "/account/api_usage_level/upgrade", body={}, what="kalshi api tier upgrade",
            ok=(200, 201, 204),
        )

    # --------------------------------------------------------------- account
    def balance(self) -> Balance:
        """`GET /portfolio/balance`. `balance` is integer cents; `balance_dollars` is a string."""
        row = self._call("GET", "/portfolio/balance", what="kalshi balance", ok=(200,))
        if not isinstance(row, dict):
            raise VenueUnavailable("kalshi balance: unexpected response")
        cash = dec(row.get("balance_dollars")) or dollars_from_cents(row.get("balance"))
        if cash is None:
            raise VenueUnavailable("kalshi balance: no balance field")
        # `portfolio_value` is the positions' value alone (it read 0 with $492 of cash and no
        # positions), so equity is cash plus positions. Reading it as the whole equity made the
        # venue show $16 of equity the moment the first live positions existed (Sept 16, 2026).
        positions_value = (
            dec(row.get("portfolio_value_dollars"))
            or dollars_from_cents(row.get("portfolio_value"))
            or Decimal(0)
        )
        equity = cash + positions_value
        return Balance(
            venue=self.venue,
            cash=cash,
            equity=equity,
            buying_power=cash,
            as_of=iso(self.clock()),
        )

    # ------------------------------------------------------------------ exchange shards
    def shard_balances(self) -> dict[int, Decimal]:
        """Cash per exchange shard from `GET /portfolio/balance`'s `balance_breakdown`: crypto and
        commodities markets settle on shard 2, exotics on 1, some sports on 3, the rest on 0, and
        an order fails with `insufficient_shard_balance` when its shard holds no collateral."""
        row = self._call("GET", "/portfolio/balance", what="kalshi balance", ok=(200,))
        out: dict[int, Decimal] = {}
        for item in (row.get("balance_breakdown") or []) if isinstance(row, dict) else []:
            if not isinstance(item, dict):
                continue
            try:
                index = int(item.get("exchange_index"))
            except (TypeError, ValueError):
                continue
            cash = dec(item.get("balance_dollars")) if item.get("balance_dollars") is not None else None
            if cash is None:
                raw = item.get("balance")
                cash = dec(raw) if isinstance(raw, str) else dollars_from_cents(raw)
            if cash is not None:
                out[index] = cash
        return out

    def transfer_between_shards(self, usd: Decimal, source: int, destination: int) -> str | None:
        """`POST /portfolio/intra_exchange_instance_transfer`: move collateral between shards.
        The amount is in hundredths of a cent. A cross-shard move runs in up to three steps that
        are not undone on failure, so the caller reads `shard_balances` again afterwards."""
        amount = Decimal(str(usd))
        if amount <= 0 or source == destination:
            raise ValueError("a shard transfer needs a positive amount and two different shards")
        body = {
            "source": "event_contract",
            "destination": "event_contract",
            "amount": int((amount * 10_000).to_integral_value()),
            "source_exchange_shard": int(source),
            "destination_exchange_shard": int(destination),
        }
        payload = self._call("POST", "/portfolio/intra_exchange_instance_transfer", body=body, what="kalshi shard transfer", ok=(200, 201))
        return str(payload.get("transfer_id")) if isinstance(payload, dict) and payload.get("transfer_id") else None

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
        time_in_force = TIF_V2.get(intent.time_in_force, "good_till_canceled")
        if intent.order_type == "limit":
            # The desk always quotes its own leg, so a NO limit is in NO dollars and crosses to
            # the YES scale exactly once. Buying NO at $0.30 is `side: "ask"`, `price: 0.7000`.
            price = money(intent.limit_price)
            if side == "no":
                price = ONE - price
        else:
            # v2 has no market order: cross the touch with an immediate-or-cancel limit. The
            # reference is read from the YES leg, which is already the wire's scale, so it is
            # never complemented -- `book_side` alone says which touch this order crosses.
            quote = self.quote(yes_leg(intent.instrument))
            price = quote.reference("buy" if book_side == "bid" else "sell")
            if price is None or price <= 0:
                raise RejectedOrder("kalshi v2: no quote to price a market order against")
            time_in_force = "immediate_or_cancel"
        self.require_on_grid(ticker, price)
        body = {
            "ticker": ticker,
            "side": book_side,
            "count": format(Decimal(count).quantize(Decimal("0.01")), "f"),
            "price": format(price.quantize(Decimal("0.0001")), "f"),
            "time_in_force": time_in_force,
            "self_trade_prevention_type": "taker_at_cross",
            "client_order_id": intent.id,
            # Kalshi runs several exchange shards (crypto and commodities on 2, exotics on 1,
            # some sports on 3); -1 routes by the ticker and never falls back to shard 0. The
            # shard must already hold collateral: scripts/kalshi_shard.py moves it.
            "exchange_index": -1,
        }
        if intent.side == "sell":
            body["reduce_only"] = True
        if getattr(intent, "post_only", False):
            body["post_only"] = True  # rest or be rejected; a maker pays no fee here
        return body

    def price_ranges(self, ticker: str) -> tuple[dict[str, Decimal], ...]:
        """The market's valid order price bands, cached for ten minutes per ticker.

        *"Valid price ranges for orders on this market"*, an array of `{start, end, step}` in
        dollars on `GET /markets/{ticker}`. There is **no scalar tick size** on a Kalshi market
        and some price in centi-cents, so a hardcoded penny grid rejects legitimate orders.
        A market that publishes none, or a read that fails, falls back to the penny grid rather
        than letting an unpriced order through.
        """
        now = float(self.clock())
        cached = self._price_ranges.get(ticker)
        if cached is not None and now - cached[0] < PRICE_RANGE_TTL_SECONDS:
            return cached[1]
        bands: tuple[dict[str, Decimal], ...] = DEFAULT_PRICE_RANGES
        reader = getattr(self.market_data, "price_ranges", None)
        if reader is not None:
            try:
                found = reader(ticker)
            except Exception:
                # A market-data failure must not decide an order's price. Fall back, and let
                # the venue have the last word on the grid.
                found = None
            if found:
                bands = tuple(found)
        self._price_ranges[ticker] = (now, bands)
        return bands

    def require_on_grid(self, ticker: str, price: Decimal) -> None:
        """Refuse a price the market cannot accept, before it costs a rejected order."""
        if not on_grid(price, self.price_ranges(ticker)):
            raise RejectedOrder(
                f"kalshi v2: {format(price, 'f')} is not on {ticker}'s price grid"
            )

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
        # An order id alone cannot name its exchange shard; the ticker routes the cancel.
        params = None
        if self.order_api != "legacy":
            ticker = getattr(order.instrument, "market_id", None) or getattr(order.instrument, "symbol", None)
            params = {"market_ticker": ticker, "exchange_index": -1} if ticker else None
        self._call("DELETE", path, params=params, what="kalshi cancel", ok=(200, 201, 204))
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
        # The fixed-point surface replaced `action` with `book_side`, which only means buy or
        # sell together with the leg (see `_action_of`).
        action = _action_of(row, None, leg)
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

    # ----------------------------------------------------------- settlements
    def settlements(self, since: "str | None" = None) -> list[dict[str, Any]]:
        """`GET /portfolio/settlements`, oldest first: which side won, and what it paid.

        https://docs.kalshi.com/api-reference/portfolio/get-portfolio-settlements. A settled
        binary contract is worth $1.00 or $0.00 and the venue pays it without a trade, so no
        fill is ever reported for it -- this endpoint is the only record that a position closed.

        Each row is normalized to dollars and this runtime's vocabulary:
        `{"ticker", "result", "yes_count", "no_count", "revenue", "settled_time"}`, where
        `result` is `yes`, `no` or `""` for a market that resolved to neither (a scalar, or a
        void).
        """
        params: dict[str, Any] = {"limit": 1000}
        if since:
            params["min_ts"] = int(_epoch_seconds(since))
        payload = self._call(
            "GET", "/portfolio/settlements", params=params, what="kalshi settlements", ok=(200,)
        )
        rows = payload.get("settlements") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            return []
        out: list[dict[str, Any]] = []
        for row in rows:
            parsed = self.parse_settlement(row)
            if parsed is not None:
                out.append(parsed)
        out.sort(key=lambda row: (row["settled_time"], row["ticker"]))
        return out

    def parse_settlement(self, row: Any) -> "dict[str, Any] | None":
        """One settlement row, or None when it names no market or carries no settled time."""
        if not isinstance(row, dict):
            return None
        ticker = str(row.get("ticker") or row.get("market_ticker") or "").strip().upper()
        settled = row.get("settled_time") or row.get("settled_ts") or row.get("determined_time")
        if not ticker or not settled:
            return None
        result = str(row.get("market_result") or row.get("result") or "").strip().lower()
        if result not in ("yes", "no"):
            result = ""
        revenue = (
            dec(row.get("revenue_dollars"))
            or dollars_from_cents(row.get("revenue"))
            or money(0)
        )
        try:
            stamp = iso(settled)
        except Exception:
            return None
        return {
            "ticker": ticker,
            "result": result,
            "yes_count": dec(row.get("yes_count_fp")) or dec(row.get("yes_count")) or money(0),
            "no_count": dec(row.get("no_count_fp")) or dec(row.get("no_count")) or money(0),
            "revenue": revenue,
            "settled_time": stamp,
        }

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
            side=_action_of(row, intent, leg),
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


def _action_of(row: dict[str, Any], intent: "OrderIntent | None", leg: "str | None" = None) -> str:
    """buy or sell, from `action` when the row carries it, else from the book side and the leg.

    The v2 book is the YES book: a bid is the YES side and an ask the NO side, always. So a
    NO order rests on the ask, and a fill of it with `book_side: "ask"` is a *buy* of NO. Read
    without the leg, every NO buy on Sept 16, 2026 was recorded as a sell, and the desks'
    books went short contracts they had bought."""
    action = str(row.get("action") or "").lower()
    if action in ("buy", "sell"):
        return action
    book_side = str(row.get("book_side") or "").lower()
    if book_side in ("bid", "ask"):
        leg = (leg or str(row.get("outcome_side") or row.get("side") or "yes")).lower()
        if leg == "no":
            return "buy" if book_side == "ask" else "sell"
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
    "yes_leg",
    "on_grid",
    "DEFAULT_PRICE_RANGES",
    "PRICE_RANGE_TTL_SECONDS",
    "ORDERS_PATH",
    "ORDERS_PATH_V2",
    "STATUS_MAP",
    "CAPABILITIES",
    "HOST",
    "PREFIX",
]
