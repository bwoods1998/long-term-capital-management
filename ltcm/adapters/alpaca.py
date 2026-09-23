"""Alpaca: US equities, options and crypto, paper and live, over the same code path.

Auth is two headers, `APCA-API-KEY-ID` and `APCA-API-SECRET-KEY`
(https://docs.alpaca.markets/reference/getaccount-1). The trading host differs between paper and
live; market data is always `https://data.alpaca.markets`.

Endpoints used, each verified against the reference:

    GET    /v2/account                          https://docs.alpaca.markets/reference/getaccount-1
    GET    /v2/positions                        https://docs.alpaca.markets/us/reference/getallopenpositions.md
    POST   /v2/orders                           https://docs.alpaca.markets/reference/postorder
    GET    /v2/orders?status=open               https://docs.alpaca.markets/reference/getallorders-1
    GET    /v2/orders:by_client_order_id        https://docs.alpaca.markets/reference/getorderbyclientorderid
    DELETE /v2/orders/{order_id}  -> 204        https://docs.alpaca.markets/reference/deleteorderbyorderid-1
    GET    /v2/account/activities/FILL          https://docs.alpaca.markets/reference/getaccountactivitiesbyactivitytype-1
    GET    https://data.alpaca.markets/v2/stocks/{symbol}/quotes/latest?feed=iex
                                                https://docs.alpaca.markets/reference/stocklatestquotesingle-1
    GET    https://data.alpaca.markets/v1beta3/crypto/us/latest/quotes?symbols=BTC%2FUSD
                                                https://docs.alpaca.markets/reference/cryptolatestquotes-1
    GET    /v2/assets/{symbol}                  https://docs.alpaca.markets/reference/get-v2-assets-symbol_or_asset_id
                                                (not yet read on the live venue: see `asset`)

Two parsing traps this code encodes. Every numeric field on the **trading** API is a JSON string
(`"cash": "12345.67"`), while every numeric field on the **market data** API is a JSON number, so
the two are never parsed by the same helper. And the stock quote wrapper is `quote` (singular,
beside a `symbol` key) while the crypto wrapper is `quotes`, a map keyed by symbol.
"""

from __future__ import annotations

import re
import threading
import time
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
    text,
)
from ..data import TransportError, iso
from . import (
    AlpacaCredentials,
    PURPOSE_HEADER,
    VenueClient,
    confirm_or_unknown,
    dec,
    message_of,
    require_ok,
)

PAPER_BASE = "https://paper-api.alpaca.markets"
LIVE_BASE = "https://api.alpaca.markets"
DATA_BASE = "https://data.alpaca.markets"

VENUE = "alpaca"
DEFAULT_FEED = "iex"

#: The facts of an asset record `asset` reads, when the venue states them.
ASSET_FACTS = ("price_increment", "min_order_size", "min_trade_increment")
#: How long an asset record that could not be read is left before it is asked for again. One that
#: was read is kept for the life of the process: a pair's increments do not move intraday.
ASSET_RETRY_SECONDS = 600.0

#: Alpaca's seventeen order states collapsed onto the eight this runtime knows.
STATUS_MAP: dict[str, str] = {
    "new": "accepted",
    "pending_new": "accepted",
    "accepted": "accepted",
    "accepted_for_bidding": "accepted",
    "held": "accepted",
    "calculated": "accepted",
    "suspended": "accepted",
    "replaced": "accepted",
    "pending_replace": "accepted",
    "stopped": "accepted",
    "partially_filled": "partially_filled",
    "filled": "filled",
    "canceled": "cancelled",
    "pending_cancel": "accepted",
    "expired": "expired",
    "done_for_day": "expired",
    "rejected": "rejected",
}

CAPABILITIES = {
    "equity",
    "option",
    "crypto",
    "limit",
    "gtc",
    "ioc",
    "fractional",
    "extended_hours",
    "short",
}


def alpaca_symbol(instrument: Instrument) -> str:
    """The venue's spelling of an instrument.

    Equities are the plain ticker. Crypto pairs carry a slash (`BTC/USD`). Options use the OCC
    21-character symbol: root, `YYMMDD`, `C`/`P`, then the strike in thousandths, eight digits.
    """
    symbol = instrument.symbol.strip().upper()
    if instrument.asset_class == "crypto":
        if instrument.market_id:
            return instrument.market_id.strip().upper().replace("-", "/")
        return symbol.replace("-", "/") if "/" in symbol or "-" in symbol else f"{symbol}/USD"
    if instrument.asset_class == "option":
        expiry = (instrument.expiry or "").replace("-", "")
        if len(expiry) != 8:
            raise RejectedOrder(f"alpaca: option expiry {instrument.expiry!r} is not YYYY-MM-DD")
        strike = (money(instrument.strike) * 1000).quantize(Decimal(1))
        right = "C" if (instrument.right or "").lower() == "call" else "P"
        return f"{symbol}{expiry[2:]}{right}{int(strike):08d}"
    return symbol


def instrument_for(row: dict[str, Any], *, venue: str = VENUE) -> Instrument:
    """Rebuild an `Instrument` from a position or activity row."""
    symbol = str(row.get("symbol") or "").strip().upper()
    asset_class = str(row.get("asset_class") or "us_equity")
    if asset_class == "crypto" or "/" in symbol:
        return Instrument("crypto", symbol.replace("/", "-"), venue, market_id=symbol)
    if asset_class == "us_option" or (len(symbol) >= 15 and symbol[-9] in ("C", "P")):
        root = symbol[:-15]
        expiry = f"20{symbol[-15:-13]}-{symbol[-13:-11]}-{symbol[-11:-9]}"
        right = "call" if symbol[-9] == "C" else "put"
        strike = money(int(symbol[-8:])) / 1000
        return Instrument(
            "option", root, venue, multiplier=money(100), expiry=expiry, strike=strike, right=right
        )
    return Instrument("equity", symbol, venue)


class AlpacaBroker:
    """A `Broker` over Alpaca's trading and market-data APIs."""

    def __init__(
        self,
        credentials: AlpacaCredentials,
        *,
        transport: Any = None,
        client: Any = None,
        venue: str = VENUE,
        timeout: float = 20.0,
        feed: str = DEFAULT_FEED,
        base_url: "str | None" = None,
        data_url: str = DATA_BASE,
        option_feed: str = "indicative",
    ):
        self.credentials = credentials
        self.venue = venue
        self.feed = feed
        #: `indicative` has modified quotes and delayed trades, not executable OPRA NBBO.
        #: `opra` is live and needs the OPRA agreement signed on the account.
        #: https://docs.alpaca.markets/us/reference/optionlatestquotes
        self.option_feed = option_feed
        self.base = (base_url or (PAPER_BASE if credentials.paper else LIVE_BASE)).rstrip("/")
        self.data = data_url.rstrip("/")
        self.client = client or VenueClient(transport, timeout=timeout)
        #: symbol -> (monotonic time read, its facts or None when the read failed); see `asset`.
        self._assets: dict[str, tuple[float, "dict[str, Decimal] | None"]] = {}
        self._assets_lock = threading.Lock()

    # ------------------------------------------------------------------- http
    def _call(
        self,
        method: str,
        path: str,
        *,
        params: "dict[str, Any] | None" = None,
        body: Any = None,
        headers: "dict[str, str] | None" = None,
        base: "str | None" = None,
        what: str,
        ok: tuple[int, ...] = (200, 201, 204),
        refused: tuple[int, ...] = (),
    ) -> Any:
        """One request. A status in `refused` is the venue refusing THIS request -- `RejectedOrder`
        with its message -- where `require_ok` would read it as the venue being unreachable."""
        url = (base or self.base) + path
        if params:
            pairs = [(k, v) for k, v in params.items() if v is not None and v != ""]
            if pairs:
                url += "?" + urllib.parse.urlencode(pairs)
        status, payload = self.client.request(
            method, url, headers={**self.credentials.headers(), **(headers or {})}, body=body, what=what
        )
        if status in refused:
            detail = message_of(payload)
            raise RejectedOrder(f"{what}: HTTP {status}{(' ' + detail) if detail else ''}")
        return require_ok(status, payload, what=what, ok=ok)

    def capabilities(self) -> set[str]:
        caps = set(CAPABILITIES)
        if self.credentials.paper:
            caps.add("paper")
        return caps

    # ---------------------------------------------------------------- account
    def balance(self) -> Balance:
        """`GET /v2/account`. Every figure arrives as a string; `portfolio_value` is deprecated."""
        row = self._call("GET", "/v2/account", what="alpaca account")
        if not isinstance(row, dict):
            raise VenueUnavailable("alpaca account: unexpected response")
        return Balance(
            venue=self.venue,
            cash=dec(row.get("cash"), "0"),
            equity=dec(row.get("equity"), "0"),
            buying_power=dec(row.get("buying_power"), "0"),
            as_of=iso(row.get("balance_asof") or row.get("created_at") or 0),
            currency=str(row.get("currency") or "USD"),
        )

    def positions(self) -> list[Position]:
        """`GET /v2/positions`. A short position reports `side: "short"` and a negative `qty`."""
        rows = self._call("GET", "/v2/positions", what="alpaca positions")
        if not isinstance(rows, list):
            return []
        out: list[Position] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            quantity = dec(row.get("qty"))
            if quantity is None or quantity == 0:
                continue
            if str(row.get("side") or "long") == "short" and quantity > 0:
                quantity = -quantity
            out.append(
                Position(
                    instrument=instrument_for(row, venue=self.venue),
                    quantity=quantity,
                    average_cost=dec(row.get("avg_entry_price"), "0"),
                    mark=dec(row.get("current_price")),
                )
            )
        return out

    # ------------------------------------------------------------------ quote
    def quote(self, instrument: Instrument) -> Quote:
        """Latest quote. Equities come from the IEX feed by default; crypto from `us`."""
        symbol = alpaca_symbol(instrument)
        if instrument.asset_class == "crypto":
            payload = self._call(
                "GET",
                "/v1beta3/crypto/us/latest/quotes",
                params={"symbols": symbol},
                base=self.data,
                what=f"alpaca crypto quote {symbol}",
            )
            quotes = payload.get("quotes") if isinstance(payload, dict) else None
            row = quotes.get(symbol) if isinstance(quotes, dict) else None
            source = "alpaca:crypto"
        elif instrument.asset_class == "option":
            payload = self._call(
                "GET",
                "/v1beta1/options/quotes/latest",
                params={"symbols": symbol, "feed": self.option_feed},
                base=self.data,
                what=f"alpaca option quote {symbol}",
            )
            quotes = payload.get("quotes") if isinstance(payload, dict) else None
            row = quotes.get(symbol) if isinstance(quotes, dict) else None
            source = f"alpaca:options:{self.option_feed}"
        else:
            payload = self._call(
                "GET",
                f"/v2/stocks/{urllib.parse.quote(symbol)}/quotes/latest",
                params={"feed": self.feed},
                base=self.data,
                what=f"alpaca quote {symbol}",
            )
            row = payload.get("quote") if isinstance(payload, dict) else None
            source = f"alpaca:{self.feed}"
        if not isinstance(row, dict):
            raise VenueUnavailable(f"alpaca quote {symbol}: no quote in the response")
        bid = dec(row.get("bp"))
        ask = dec(row.get("ap"))
        return Quote(
            instrument=instrument,
            bid=bid if bid and bid > 0 else None,
            ask=ask if ask and ask > 0 else None,
            last=None,
            as_of=iso(row.get("t") or 0),
            source=source,
            # IEX is a real-time single-venue feed; it is not the consolidated tape, but it is
            # not a delayed feed either. SIP under a paid plan is likewise real time.
            delayed=(self.option_feed != "opra") if instrument.asset_class == "option" else self.feed not in ("iex", "sip"),
        )

    # ----------------------------------------------------------------- assets
    def asset(self, symbol: str) -> "dict[str, Decimal] | None":
        """`GET /v2/assets/{symbol}`: the venue's own `price_increment`, `min_order_size` and
        `min_trade_increment` for a crypto pair, each only when the record states it (an equity's
        states none), or None when the record cannot be read. `BTC-USD` and `BTC/USD` are one pair.

        Optional by design: a caller that finds nothing here must not guess. The House snaps a
        crypto limit price to `price_increment` only when this says what it is (Sept 22, 2026: the
        frontier auditor vetoed a crypto agent whose prices were rounded to a cent). Not yet read
        through the gateway on the live venue; the gateway allows the path (`gateway/lib/caps.mjs`).
        A pair is asked for as `BTC%2FUSD` and then, if that is not answered, in the venue's older
        spelling `BTCUSD`; a record that names another symbol is not this pair's. A record read is
        kept for the life of the process; a failed read is asked again after `ASSET_RETRY_SECONDS`."""
        name = str(symbol or "").strip().upper()
        if "-" in name and "/" not in name:
            name = name.replace("-", "/")
        if not name:
            return None
        now = time.monotonic()
        with self._assets_lock:
            hit = self._assets.get(name)
        if hit is not None and (hit[1] is not None or now - hit[0] < ASSET_RETRY_SECONDS):
            return None if hit[1] is None else dict(hit[1])
        facts: "dict[str, Decimal] | None" = None
        for spelling in [name] + ([name.replace("/", "")] if "/" in name else []):
            try:
                row = self._call("GET", f"/v2/assets/{urllib.parse.quote(spelling, safe='')}", what=f"alpaca asset {name}", ok=(200,))
            except Exception:  # noqa: BLE001 - an unreadable record is an unknown increment, never a guessed one
                continue
            if not isinstance(row, dict) or str(row.get("symbol") or name).upper().replace("/", "") != name.replace("/", ""):
                continue
            facts = {}
            for key in ASSET_FACTS:
                value = dec(row.get(key))
                if value is not None and value > 0:
                    facts[key] = value
            break
        with self._assets_lock:
            self._assets[name] = (now, facts)
        return None if facts is None else dict(facts)

    # ----------------------------------------------------------------- orders
    def submit(self, intent: OrderIntent) -> Order:
        """`POST /v2/orders` with `client_order_id` = the intent id.

        `qty` and `notional` are mutually exclusive and this adapter always sends `qty`, so a
        desk's quantity is never reinterpreted as dollars.

        A 401 or 403 answer to the POST is a refusal of this order (`RejectedOrder`, with the
        message), not an unreachable venue: no order exists. Measured Sept 20-22, 2026 on the paper
        book: 55 orders refused "cost basis must be >= minimal amount of order 10" and 63
        "insufficient balance for AVAX", both HTTP 403. Read as `VenueUnavailable`, each was booked
        `unknown` and a poll later "rejected: the venue has no such order" -- 118 rows that hid the
        venue's own reason. The gateway answers its own refusals (a spent cap, a path it does not
        sign, a bad token) with 401 or 403 too, before anything is forwarded. A 401 or 403 on a READ
        still means the venue cannot be reached with these credentials (`require_ok`).
        """
        if getattr(intent, "expires_at", None) is not None:
            # Alpaca has no good-till-date order. Sent as plain gtc, the order would outlive the
            # expiry the desk relied on, so it is refused before anything is sent.
            raise RejectedOrder("alpaca has no order that expires at a stated time; drop expires_at")
        body: dict[str, Any] = {
            "symbol": alpaca_symbol(intent.instrument),
            "qty": text(intent.quantity),
            "side": intent.side,
            "type": intent.order_type,
            "time_in_force": intent.time_in_force,
            "client_order_id": intent.id,
        }
        if intent.limit_price is not None:
            body["limit_price"] = text(intent.limit_price)
        if intent.instrument.asset_class == "equity" and money(intent.quantity) % 1 != 0 and intent.time_in_force != "day":
            # Alpaca takes a fractional share order, market or limit, as a `day` order only (Sept 23,
            # 2026, A7: fractional one-day limit orders for the stock bunts). The quantity is sent as
            # given, never rounded: `qty` above is the intent's own text.
            raise RejectedOrder(f"alpaca: a fractional share order must be a day order, not {intent.time_in_force}")
        if intent.instrument.asset_class == "option":
            # Long premium only: an option is opened by buying it and closed by selling it. The
            # venue enforces the intent (a sell_to_close with nothing to close is rejected), and
            # the gateway refuses any other, so no order from here can write an option.
            if intent.order_type != "limit" or intent.limit_price is None:
                raise RejectedOrder("alpaca: an option order must be a limit order")
            if money(intent.quantity) % 1 != 0:
                raise RejectedOrder("alpaca: options trade in whole contracts")
            body["position_intent"] = "buy_to_open" if intent.side == "buy" else "sell_to_close"
            body["time_in_force"] = "day"  # the only one Alpaca takes for options
        try:
            payload = self._call("POST", "/v2/orders", body=body, headers={PURPOSE_HEADER: intent.purpose}, what="alpaca submit",
                                 refused=(401, 403))
        except TransportError as exc:
            return confirm_or_unknown(
                lambda: self.order_by_client_id(intent.id),
                what="alpaca submit",
                detail=f"no response ({type(exc).__name__})",
            )
        if not isinstance(payload, dict):
            raise UnknownOutcome("alpaca submit: unreadable response; reconcile before retrying")
        return self.parse_order(payload, intent=intent)

    def order_by_client_id(self, client_order_id: str) -> "Order | None":
        """`GET /v2/orders:by_client_order_id`. The colon is a literal path segment."""
        try:
            payload = self._call(
                "GET",
                "/v2/orders:by_client_order_id",
                params={"client_order_id": client_order_id},
                what="alpaca order lookup",
                ok=(200,),
            )
        except RejectedOrder:  # 404: the venue never saw it
            return None
        return self.parse_order(payload) if isinstance(payload, dict) else None

    def get_order(self, order_id: str) -> Order:
        """Look an order up by our own id (`ord-...`) or by the venue's UUID."""
        if isinstance(order_id, str) and order_id.startswith("ord-"):
            found = self.order_by_client_id("oi-" + order_id[4:])
            if found is None:
                raise RejectedOrder(f"alpaca: no order for {order_id}")
            return found
        payload = self._call(
            "GET", f"/v2/orders/{urllib.parse.quote(str(order_id))}", what="alpaca order", ok=(200,)
        )
        if not isinstance(payload, dict):
            raise RejectedOrder(f"alpaca: no order for {order_id}")
        return self.parse_order(payload)

    def cancel(self, order_id: str) -> Order:
        """`DELETE /v2/orders/{id}` answers 204; 422 means it was already uncancelable."""
        order = self.get_order(order_id)
        venue_id = order.broker_order_id or order_id
        status, payload = self.client.request(
            "DELETE",
            f"{self.base}/v2/orders/{urllib.parse.quote(str(venue_id))}",
            headers=self.credentials.headers(),
            what="alpaca cancel",
        )
        if status in (200, 204):
            return self.get_order(order_id)
        if status in (404, 422):  # already terminal; report what the venue actually holds
            return self.get_order(order_id)
        require_ok(status, payload, what="alpaca cancel", ok=(200, 204))
        return self.get_order(order_id)

    def open_orders(self) -> list[Order]:
        """`GET /v2/orders?status=open`, newest first, capped at the venue's 500."""
        rows = self._call(
            "GET",
            "/v2/orders",
            params={"status": "open", "limit": 500, "direction": "desc"},
            what="alpaca open orders",
            ok=(200,),
        )
        if not isinstance(rows, list):
            return []
        return [self.parse_order(row) for row in rows if isinstance(row, dict)]

    # ------------------------------------------------------------------ fills
    def fills(self, since: "str | None" = None) -> list[Fill]:
        """`GET /v2/account/activities/FILL`, oldest first.

        The activity `id` is `"<timestamp>::<uuid>"` and is stable, so it is the fill id.
        """
        rows = self._call(
            "GET",
            "/v2/account/activities/FILL",
            params={"after": since, "direction": "asc", "page_size": 100},
            what="alpaca fills",
            ok=(200,),
        )
        if not isinstance(rows, list):
            return []
        out: list[Fill] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            quantity = dec(row.get("qty"))
            price = dec(row.get("price"))
            if quantity is None or price is None or quantity <= 0:
                continue
            out.append(
                Fill(
                    id=str(row.get("id") or ""),
                    order_id=str(row.get("order_id") or ""),
                    desk_id="",
                    instrument=instrument_for(row, venue=self.venue),
                    side=str(row.get("side") or "buy"),
                    quantity=quantity,
                    price=price,
                    # Alpaca reports no per-fill commission on this activity; equities and
                    # crypto trade at zero commission and options are billed separately.
                    fee=money(0),
                    at=iso(row.get("transaction_time") or 0),
                )
            )
        return out

    def fee_activities(self, since_date: "str | None" = None) -> "list[dict[str, Any]]":
        """`GET /v2/account/activities/FEE`, oldest first: what the venue took that no fill shows.

        Alpaca charges no commission, and passes on the regulators' fees (SEC and TAF on equity
        sales, ORF and OCC on option contracts): it adds a day's up, rounds UP to a cent and takes
        it at the end of the day as one FEE activity. `{"id", "usd" (positive: money taken), "date",
        "description"}` for each."""
        rows = self._call(
            "GET",
            "/v2/account/activities/FEE",
            params={"after": since_date, "direction": "asc", "page_size": 100},
            what="alpaca fees",
            ok=(200,),
        )
        out: list[dict[str, Any]] = []
        for row in rows if isinstance(rows, list) else []:
            amount = dec(row.get("net_amount")) if isinstance(row, dict) else None
            if amount is None or amount >= 0 or not row.get("id"):
                continue
            out.append({"id": str(row["id"]), "usd": -amount, "date": str(row.get("date") or ""), "description": str(row.get("description") or "")})
        return out

    def option_chain(self, underlying: str, *, expiry_from: str, expiry_to: str, limit: int = 1000) -> "list[dict[str, Any]]":
        """The contracts of one underlying expiring in [expiry_from, expiry_to] with a two-sided
        quote, nearest expiry and lowest strike first: `{"symbol" (OCC), "underlying", "expiry",
        "strike", "right", "bid", "ask", "as_of", "iv", "delta", "volume"}` (floats; greeks are
        None when the feed does not carry them)."""
        rows: dict[str, Any] = {}
        token = None
        for _ in range(10):
            payload = self._call(
                "GET",
                f"/v1beta1/options/snapshots/{urllib.parse.quote(underlying.upper())}",
                params={"feed": self.option_feed, "limit": min(int(limit), 1000), "expiration_date_gte": expiry_from,
                        "expiration_date_lte": expiry_to, "page_token": token},
                base=self.data,
                what=f"alpaca option chain {underlying}",
            )
            if not isinstance(payload, dict):
                break
            rows.update(payload.get("snapshots") or {})
            token = payload.get("next_page_token")
            if not token or len(rows) >= limit:
                break
        out = []
        for occ, snap in rows.items():
            quote = (snap or {}).get("latestQuote") or {}
            bid, ask = dec(quote.get("bp")), dec(quote.get("ap"))
            if bid is None or ask is None or bid <= 0 or ask <= bid:
                continue
            if not re.fullmatch(r"[A-Z]{1,6}[0-9]{6}[CP][0-9]{8}", str(occ)):
                continue
            inst = instrument_for({"symbol": occ, "asset_class": "us_option"}, venue=self.venue)
            greeks = (snap or {}).get("greeks") or {}
            number = lambda v: None if v is None else float(v)  # noqa: E731
            out.append({
                "symbol": occ, "underlying": inst.symbol, "expiry": inst.expiry, "strike": float(inst.strike), "right": inst.right,
                "bid": float(bid), "ask": float(ask), "as_of": iso(quote.get("t") or 0),
                "iv": number((snap or {}).get("impliedVolatility")), "delta": number(greeks.get("delta")),
                "volume": number(((snap or {}).get("dailyBar") or {}).get("v")),
            })
        out.sort(key=lambda r: (r["expiry"], r["strike"], r["right"]))
        return out

    # ---------------------------------------------------------------- parsing
    def parse_order(self, row: dict[str, Any], *, intent: "OrderIntent | None" = None) -> Order:
        """One Alpaca order object as an `Order`. `filled_*` fields are nullable."""
        client_order_id = str(row.get("client_order_id") or (intent.id if intent else ""))
        instrument = intent.instrument if intent is not None else instrument_for(row, venue=self.venue)
        status = STATUS_MAP.get(str(row.get("status") or ""), "unknown")
        quantity = dec(row.get("qty")) or (intent.quantity if intent else money(0))
        order = Order(
            id="ord-" + client_order_id[3:] if client_order_id.startswith("oi-") else
               ("ord-" + client_order_id if client_order_id else "ord-" + str(row.get("id") or "")),
            intent_id=client_order_id,
            desk_id=intent.desk_id if intent else "",
            instrument=instrument,
            side=str(row.get("side") or (intent.side if intent else "buy")),
            quantity=quantity,
            order_type=str(row.get("type") or (intent.order_type if intent else "market")),
            limit_price=dec(row.get("limit_price")),
            time_in_force=str(row.get("time_in_force") or (intent.time_in_force if intent else "day")),
            status=status,
            venue=self.venue,
            broker_order_id=str(row.get("id") or "") or None,
            filled_quantity=dec(row.get("filled_qty"), "0"),
            average_price=dec(row.get("filled_avg_price")),
            fees=money(0),
            submitted_at=_stamp(row.get("submitted_at") or row.get("created_at")),
            updated_at=_stamp(row.get("updated_at") or row.get("created_at")),
            reason=message_of(row) if status == "rejected" else None,
        )
        order._raw = {"status": row.get("status")}
        return order


def _stamp(value: Any) -> "str | None":
    if not value:
        return None
    try:
        return iso(value)
    except Exception:
        return None


__all__ = [
    "AlpacaBroker",
    "AlpacaCredentials",
    "alpaca_symbol",
    "instrument_for",
    "PAPER_BASE",
    "LIVE_BASE",
    "DATA_BASE",
    "STATUS_MAP",
    "CAPABILITIES",
]
