"""Alpaca: US equities, options and crypto, paper and live, over the same code path.

Auth is two headers, `APCA-API-KEY-ID` and `APCA-API-SECRET-KEY`
(https://docs.alpaca.markets/reference/getaccount-1). The trading host differs between paper and
live; market data is always `https://data.alpaca.markets`.

Endpoints used, each verified against the reference:

    GET    /v2/account                          https://docs.alpaca.markets/reference/getaccount-1
    GET    /v2/positions                        https://docs.alpaca.markets/us/reference/getallopenpositions.md
    POST   /v2/orders                           https://docs.alpaca.markets/reference/postorder
                                                (and a level-3 structure as ONE multi-leg order,
                                                `order_class: "mleg"`: see "Structures" below)
    GET    /v2/orders?status=open&nested=true   https://docs.alpaca.markets/reference/getallorders-1
    GET    /v2/orders/{order_id}?nested=true    https://docs.alpaca.markets/reference/getorderbyorderid-1
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

**Structures (level 3, Sept 25, 2026, the options-desk run).** A book holds a defined-risk structure
as ONE option-class instrument whose `market_id` names its type and legs (`league/structures.py`, the
one implementation of the spec), priced at S = its net value + its collateral K; the venue holds its
legs. This adapter is where the two meet:

- `submit` sends a buy (open) or sell (close) of a held structure as ONE multi-leg order: no top-level
  symbol, `order_class: "mleg"`, `qty` the structures, a `day` limit, and `legs` of `{symbol,
  ratio_qty, side, position_intent}` (`structures.mleg_legs`). Its `limit_price` is the NET in
  Alpaca's sign: "A positive value indicates a debit, representing a cost or payment to be made. A
  negative value signifies a credit, reflecting an amount to be received"
  (https://docs.alpaca.markets/reference/postorder, `limit_price`; the shapes are
  https://docs.alpaca.markets/docs/options-level-3-trading). So net = S - K to open and K - S to close
  (`mleg_limit`). A leg is never sent alone.
- `parse_order` reads the parent's `legs` (each with its own `id`, `ratio_qty`, `qty` = ratio x the
  parent's qty, `filled_qty`, `filled_avg_price`, `status`: the documented 200 response of
  `POST /v2/orders`) and reports the WHOLE structure: filled only as far as every leg has filled
  quantity x ratio, at S = K + sum(sign x ratio x leg average). A leg ahead of the others is pending.
- `fills` groups the FILL activities of a structure's legs, whichever order id they carry (the leg's
  own or the parent's), into ONE fill of the held instrument per tranche of whole structures.
- `quote` of a held structure is its touch from every leg's quote in one request (`structures.quote`).
- `positions` reports the legs as the venue shows them (a short leg negative): the book, which knows
  what it holds, folds them (`league/book.py`), because Alpaca nets one contract's position across
  every structure and single contract on the account and only the whole book can explain a net.

Unverified until an agent's first order in a session (no test orders are sent): whether the practice
account takes each type, whether `GET /v2/orders:by_client_order_id` carries `legs`, and which order id
a leg's FILL activity carries. The first venue answer of each kind for each type is kept for the
owner's record (`drain_structure_answers`).
"""

from __future__ import annotations

import re
import threading
import time
import urllib.parse
from decimal import ROUND_FLOOR, Decimal
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
    # Level-3 structures (Sept 25, 2026): `mleg`, a structure goes to the venue as one multi-leg
    # order; `structure_legs`, the venue holds its legs, so `positions` reports legs and the book
    # folds them against the structures it holds (`league/book.py`).
    "mleg",
    "structure_legs",
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


# ------------------------------------------------------------------------------------ structures
CENT = Decimal("0.01")
#: A leg's part in its structure from the `position_intent` the venue reports on it: an open buys a
#: long leg and sells a short one; a close sells the long leg and buys the short one back.
LEG_SIGN = {"buy_to_open": 1, "sell_to_close": 1, "sell_to_open": -1, "buy_to_close": -1}
#: What the owner's record keeps of a venue answer: never an account number, never a key.
ORDER_FIELDS = ("id", "client_order_id", "status", "order_class", "qty", "filled_qty", "filled_avg_price", "limit_price", "type",
                "time_in_force", "side", "submitted_at", "filled_at", "canceled_at", "expired_at", "failed_at")
LEG_FIELDS = ("id", "symbol", "side", "position_intent", "ratio_qty", "qty", "filled_qty", "filled_avg_price", "status", "asset_class")
ACTIVITY_FIELDS = ("id", "order_id", "symbol", "side", "qty", "price", "cum_qty", "leaves_qty", "order_status", "transaction_time", "type")
#: How many structure orders the adapter remembers by id (a session's are a few dozen).
REMEMBERED_ORDERS = 2000


def _structures() -> Any:
    """`league.structures`, the one implementation of the structure spec. Imported when first needed,
    not at the top: it imports this module (`alpaca_symbol`), and nothing here needs it until a
    structure is traded."""
    from league import structures

    return structures


def is_structure(instrument: Any) -> bool:
    """Is this a structure held as one position? A single contract carries no `market_id`, so the
    spec's module is only read for an instrument that could be one."""
    market_id = getattr(instrument, "market_id", None)
    return (getattr(instrument, "asset_class", None) == "option" and isinstance(market_id, str) and "|" in market_id
            and _structures().is_structure(instrument))


def mleg_limit(spec: Any, held: Any, opening: bool) -> Decimal:
    """Alpaca's signed net `limit_price` for a multi-leg order on a structure held at `held` (S): a
    debit positive and a credit negative (https://docs.alpaca.markets/reference/postorder). Opening
    buys the held instrument, so net = S - K (a debit structure's debit; a credit structure's credit,
    negative); closing sells it, so net = K - S (a debit structure's proceeds, negative; the most a
    credit structure's buy-back may cost, positive). Whole cents, or refused: a limit is never moved."""
    net = (money(held) - spec.collateral) if opening else (spec.collateral - money(held))
    if net != net.quantize(CENT):
        raise RejectedOrder(f"alpaca: a structure's net limit is whole cents, not {net}")
    return net.quantize(CENT)


def mleg_body(intent: OrderIntent) -> dict[str, Any]:
    """The multi-leg order for a buy (open) or sell (close) of a held structure, as `POST /v2/orders`
    documents it (https://docs.alpaca.markets/docs/options-level-3-trading): no top-level symbol or
    side, `order_class: "mleg"`, `qty` the structures, a `day` limit at the signed net, and every leg
    with its ratio, side and `position_intent`. Refused before anything is sent: a market order (a
    structure has no touch to take), a part of a structure, a tampered code (`spec_of` validates)."""
    s = _structures()
    try:
        spec = s.spec_of(intent.instrument)
    except ValueError as exc:
        raise RejectedOrder(f"alpaca: {exc}") from exc
    if intent.order_type != "limit" or intent.limit_price is None:
        raise RejectedOrder("alpaca: a structure is a limit order at its net price")
    if money(intent.quantity) % 1 != 0:
        raise RejectedOrder("alpaca: structures trade whole")
    if getattr(intent, "post_only", False):
        raise RejectedOrder("alpaca: a multi-leg order cannot be post-only")
    opening = intent.side == "buy"
    return {
        "order_class": "mleg",
        "qty": text(money(intent.quantity)),
        "type": "limit",
        "limit_price": text(mleg_limit(spec, intent.limit_price, opening)),
        "time_in_force": "day",
        "client_order_id": intent.id,
        "legs": s.mleg_legs(spec, "open" if opening else "close"),
    }


def _pick(row: Any, fields: tuple[str, ...]) -> dict[str, Any]:
    """The named fields of a venue row, as plain text, for the owner's record."""
    if not isinstance(row, dict):
        return {}
    return {k: (None if row.get(k) is None else str(row.get(k))) for k in fields if k in row}


def compact_order(row: Any) -> dict[str, Any]:
    """A multi-leg order as the venue answered it, legs included, without anything private."""
    out = _pick(row, ORDER_FIELDS)
    if isinstance(row, dict) and isinstance(row.get("legs"), list):
        out["legs"] = [_pick(leg, LEG_FIELDS) for leg in row["legs"]]
    return out


def _first_cost(rows: "list[tuple[Decimal, Decimal]]", contracts: Decimal) -> Decimal:
    """What the first `contracts` of a leg's fills cost, a share, first in first out."""
    left, cost = contracts, Decimal(0)
    for quantity, price in rows:
        take = min(left, quantity)
        cost += take * price
        left -= take
        if left <= 0:
            break
    return cost


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
        # Structures (Sept 25, 2026). What the adapter has learned of multi-leg orders, in memory: the
        # held instrument by the parent's venue id and client id, the parent's venue id by each id a
        # leg or the parent carries, and whether it opened (buy) or closed (sell). A restart forgets
        # it and reads it back from the next answer that names the legs (`_identify`).
        self._structure_lock = threading.Lock()
        self._structure_ids: dict[str, Instrument] = {}
        self._leg_parent: dict[str, str] = {}
        self._parent_side: dict[str, str] = {}
        self._simple_ids: set[str] = set()
        #: FILL activity rows of structure legs by parent venue id, then by activity id: a leg that
        #: arrived before the others waits here until the whole structure has filled.
        self._activity_legs: dict[str, dict[str, dict[str, Any]]] = {}
        #: The first venue answer of each kind (`submit`, `fill`, `activity`, `uneven`, `refused`) for
        #: each structure type, for the owner's record: `drain_structure_answers`.
        self._answers: list[dict[str, Any]] = []
        self._answered: set[tuple[str, str]] = set()

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
        if is_structure(instrument):
            return self._structure_quote(instrument)
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

    def _structure_quote(self, instrument: Instrument) -> Quote:
        """A held structure's touch, a share in the held price S: every leg's latest quote in ONE
        request (`symbols` takes a comma-separated list), then `structures.quote` -- bid = K + long
        bids - short asks (never under zero), ask = K + long asks - short bids, what all legs trade at
        at once. A leg the feed does not quote leaves that side None; the quote's time is the OLDEST
        leg's, so a stale leg makes the whole structure stale."""
        s = _structures()
        spec = s.spec_of(instrument)
        symbols = [leg.occ for leg in spec.legs]
        payload = self._call(
            "GET",
            "/v1beta1/options/quotes/latest",
            params={"symbols": ",".join(symbols), "feed": self.option_feed},
            base=self.data,
            what=f"alpaca structure quote {spec.type} {spec.underlying}",
        )
        quotes = payload.get("quotes") if isinstance(payload, dict) else None
        if not isinstance(quotes, dict) or not any(isinstance(quotes.get(occ), dict) for occ in symbols):
            raise VenueUnavailable(f"alpaca structure quote {spec.underlying}: no leg quoted in the response")
        touches: dict[str, tuple[Any, Any]] = {}
        stamps: list[str] = []
        for occ in symbols:
            row = quotes.get(occ)
            if not isinstance(row, dict):
                stamps.append(iso(0))
                continue
            bid, ask = dec(row.get("bp")), dec(row.get("ap"))
            touches[occ] = (bid if bid and bid > 0 else None, ask if ask and ask > 0 else None)
            stamps.append(iso(row.get("t") or 0))
        bid, ask = s.quote(spec, touches)
        return Quote(
            instrument=instrument,
            bid=bid,
            ask=ask,
            last=None,
            as_of=min(stamps),
            source=f"alpaca:options:{self.option_feed}:structure",
            delayed=self.option_feed != "opra",
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
        if is_structure(intent.instrument):
            return self._submit_structure(intent)
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
            # A BUY that is an EXIT closes a short leg: the one short an account of the House can
            # hold is a leg a broken structure left at the venue (an assignment, a leg filled
            # alone), which the book closes at once (`Book._close_broken`, Sept 25, 2026). It
            # buys back, never writes.
            if intent.side == "buy":
                body["position_intent"] = "buy_to_close" if intent.purpose == "exit" else "buy_to_open"
            else:
                body["position_intent"] = "sell_to_close"
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

    def _submit_structure(self, intent: OrderIntent) -> Order:
        """ONE multi-leg order for a buy (open) or sell (close) of a held structure (`mleg_body`),
        with the refusals and the lost-write handling of any order (`submit`). The venue's first
        answer for each type, and every refusal, is kept for the owner's record."""
        body = mleg_body(intent)
        kind = str(intent.instrument.market_id).split("|", 1)[0]
        try:
            payload = self._call("POST", "/v2/orders", body=body, headers={PURPOSE_HEADER: intent.purpose},
                                 what="alpaca submit structure", refused=(401, 403))
        except TransportError as exc:
            return confirm_or_unknown(
                lambda: self.order_by_client_id(intent.id),
                what="alpaca submit structure",
                detail=f"no response ({type(exc).__name__})",
            )
        except RejectedOrder as exc:
            self._answer("refused", kind, {"sent": body, "answer": str(exc)[:500]}, always=True)
            raise
        if not isinstance(payload, dict):
            raise UnknownOutcome("alpaca submit structure: unreadable response; reconcile before retrying")
        self._answer("submit", kind, {"sent": body, "answer": compact_order(payload)})
        return self.parse_order(payload, intent=intent)

    def order_by_client_id(self, client_order_id: str) -> "Order | None":
        """`GET /v2/orders:by_client_order_id`. The colon is a literal path segment.

        A multi-leg order read this way without its `legs` (the docs do not say this lookup nests
        them) is read again by its venue id with `nested=true`, the lookup that does: its fills are
        in its legs, and without them nothing could be booked."""
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
        if isinstance(payload, dict) and payload.get("order_class") == "mleg" and not payload.get("legs") and payload.get("id"):
            nested = self._call("GET", f"/v2/orders/{urllib.parse.quote(str(payload['id']))}", params={"nested": "true"},
                                what="alpaca order", ok=(200,))
            if isinstance(nested, dict) and nested.get("legs"):
                payload = nested
        return self.parse_order(payload) if isinstance(payload, dict) else None

    def get_order(self, order_id: str) -> Order:
        """Look an order up by our own id (`ord-...`) or by the venue's UUID."""
        if isinstance(order_id, str) and order_id.startswith("ord-"):
            found = self.order_by_client_id("oi-" + order_id[4:])
            if found is None:
                raise RejectedOrder(f"alpaca: no order for {order_id}")
            return found
        # `nested=true` rolls a multi-leg order's legs up under it (their fills are there); a simple
        # order is the same with or without it.
        payload = self._call(
            "GET", f"/v2/orders/{urllib.parse.quote(str(order_id))}", params={"nested": "true"}, what="alpaca order", ok=(200,)
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
        """`GET /v2/orders?status=open`, newest first, capped at the venue's 500. `nested=true`: a
        multi-leg order is one row with its legs under it, never its legs as orders of their own (a
        book would take a leg for an order it never sent and cancel it, which the venue refuses:
        "cannot cancel individual legs of a mleg order")."""
        rows = self._call(
            "GET",
            "/v2/orders",
            params={"status": "open", "limit": 500, "direction": "desc", "nested": "true"},
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

        A structure's legs (Sept 25, 2026) are not fills of their own: an option row whose order id
        is a multi-leg order's (the parent's, or one of its legs' own ids: which one Alpaca writes on
        a leg's FILL is not documented, so both are read) waits with its structure's other legs and is
        reported as ONE fill of the held instrument per tranche of whole structures
        (`_structure_fills`). An option row whose order the adapter does not know is asked about once
        (`_parent_of`); what is not a structure's is a fill as before.
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
        touched: dict[str, set[str]] = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            quantity = dec(row.get("qty"))
            price = dec(row.get("price"))
            if quantity is None or price is None or quantity <= 0:
                continue
            instrument = instrument_for(row, venue=self.venue)
            parent = self._parent_of(str(row.get("order_id") or "")) if instrument.asset_class == "option" else None
            if parent is not None:
                activity = str(row.get("id") or "")
                with self._structure_lock:
                    self._activity_legs.setdefault(parent, {})[activity] = {
                        "id": activity, "symbol": str(row.get("symbol") or "").upper(), "qty": quantity, "price": price,
                        "at": iso(row.get("transaction_time") or 0), "raw": _pick(row, ACTIVITY_FIELDS),
                    }
                touched.setdefault(parent, set()).add(activity)
                continue
            out.append(
                Fill(
                    id=str(row.get("id") or ""),
                    order_id=str(row.get("order_id") or ""),
                    desk_id="",
                    instrument=instrument,
                    side=str(row.get("side") or "buy"),
                    quantity=quantity,
                    price=price,
                    # Alpaca reports no per-fill commission on this activity; equities and
                    # crypto trade at zero commission and options are billed separately.
                    fee=money(0),
                    at=iso(row.get("transaction_time") or 0),
                )
            )
        for parent, completing in touched.items():
            out.extend(self._structure_fills(parent, completing))
        out.sort(key=lambda fill: fill.at)
        return out

    def _parent_of(self, order_id: str) -> "str | None":
        """The venue id of the multi-leg order an option FILL belongs to, or None when it is a single
        contract's. An id not yet seen is read once (`GET /v2/orders/{id}?nested=true`); a simple
        order is remembered as simple, and a read that fails is asked again at the next call."""
        if not order_id:
            return None
        with self._structure_lock:
            if order_id in self._leg_parent:
                return self._leg_parent[order_id]
            if order_id in self._simple_ids:
                return None
        try:
            payload = self._call("GET", f"/v2/orders/{urllib.parse.quote(order_id)}", params={"nested": "true"},
                                 what="alpaca order", ok=(200,))
        except Exception:  # noqa: BLE001 - unknown now; the row is a leg or a contract, asked again next time
            return None
        if isinstance(payload, dict) and payload.get("order_class") == "mleg" and payload.get("legs"):
            self.parse_order(payload)  # registers the parent and its legs' ids
        with self._structure_lock:
            if order_id not in self._leg_parent:
                self._simple_ids.add(order_id)
            return self._leg_parent.get(order_id)

    def _structure_fills(self, parent: str, completing: "set[str]") -> list[Fill]:
        """The held structure's fills from its legs' FILL rows seen so far: walked in the order they
        arrived (each call's rows are oldest first, and a row read again keeps its first place, so a
        tranche is completed by the row that really completed it even when the legs share a
        timestamp), a tranche is complete when every leg has filled (tranche structures) x its ratio, and is priced
        S = K + sum(sign x ratio x what that leg's contracts cost, first in first out), so a leg that
        filled at two prices pairs its first contracts with the first structures. A tranche is
        reported by the call whose rows include the leg fill that completed it (`completing`), under
        the id `<parent>:<structures filled>`, so asking again for the same rows gives the same fill
        and a leg still missing gives none."""
        with self._structure_lock:
            instrument = self._structure_ids.get(parent)
            side = self._parent_side.get(parent, "buy")
            rows = list(self._activity_legs.get(parent, {}).values())  # as they arrived: oldest first, call by call
        if instrument is None or not rows:
            return []
        spec = _structures().spec_of(instrument)
        legs = {leg.occ: leg for leg in spec.legs}
        taken: dict[str, list[tuple[Decimal, Decimal]]] = {occ: [] for occ in legs}
        units = Decimal(0)
        paid = Decimal(0)
        out: list[Fill] = []
        for row in rows:
            if row["symbol"] not in legs:
                continue
            taken[row["symbol"]].append((row["qty"], row["price"]))
            now = min((sum((q for q, _ in taken[occ]), Decimal(0)) / leg.ratio).to_integral_value(rounding=ROUND_FLOOR)
                      for occ, leg in legs.items())
            if now <= units:
                continue
            total = spec.collateral * now + sum((leg.sign * _first_cost(taken[occ], now * leg.ratio) for occ, leg in legs.items()), Decimal(0))
            price = (total - paid) / (now - units)
            if row["id"] in completing:
                if price < 0:
                    self._answer("uneven", spec.type, {"parent": parent, "why": f"a tranche priced {price} under zero", "rows": [r["raw"] for r in rows]},
                                 always=True)
                else:
                    out.append(Fill(id=f"{parent}:{text(now)}", order_id=parent, desk_id="", instrument=instrument, side=side,
                                    quantity=now - units, price=price, fee=money(0), at=row["at"]))
            units, paid = now, total
        if out:
            self._answer("activity", spec.type, {"parent": parent, "rows": [r["raw"] for r in rows]})
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
        if row.get("order_class") == "mleg" or (intent is not None and is_structure(intent.instrument)):
            return self._parse_structure_order(row, intent)
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


    # ------------------------------------------------------------ structures
    def _parse_structure_order(self, row: dict[str, Any], intent: "OrderIntent | None") -> Order:
        """A multi-leg order as ONE order of the held structure.

        The structure is the intent's, or the one this adapter sent under this id, or else read back
        from the legs' `position_intent` and `ratio_qty` (`_identify`: after a restart). Filled is the
        whole structures every leg has filled (`filled_qty` / ratio, the least of them): a leg ahead
        of the others is pending, never booked alone. The average is the held price S = K + sum(sign
        x ratio x the leg's `filled_avg_price`). The legs are what executed, so where they are all in
        the answer the parent's own `filled_qty` is not used (a leg behind is booked at the next read).
        An answer without its legs is reported with the parent's `filled_qty` and NO average, which a
        book reads as "not yet": it books nothing and asks again. A parent the venue calls filled
        while its legs are not all complete is reported partially filled for the same reason. A parent that
        ended (cancelled, expired, rejected) with its legs filled unevenly is an ERROR: the reason
        says so, and the answer is kept for the owner (`uneven`); the legs left over show at the
        next reconciliation, where the book closes them (`Book._close_broken`)."""
        s = _structures()
        legs = [leg for leg in (row.get("legs") or []) if isinstance(leg, dict)]
        ids = [str(row.get("id") or ""), str(row.get("client_order_id") or "")]
        instrument = intent.instrument if intent is not None and is_structure(intent.instrument) else None
        if instrument is None:
            with self._structure_lock:
                instrument = next((self._structure_ids[i] for i in ids if i and i in self._structure_ids), None)
        spec = s.spec_of(instrument) if instrument is not None else self._identify(legs)
        client_order_id = str(row.get("client_order_id") or (intent.id if intent else ""))
        order_id = ("ord-" + client_order_id[3:] if client_order_id.startswith("oi-") else
                    ("ord-" + client_order_id if client_order_id else "ord-" + str(row.get("id") or "")))
        status = STATUS_MAP.get(str(row.get("status") or ""), "unknown")
        parent_filled = dec(row.get("filled_qty"), "0")
        if spec is None:
            # Not a structure this code can name: its legs' intents are missing or it is no admitted
            # type. Reported against its first leg with NO average, so no book ever books it.
            first = next((leg for leg in legs if leg.get("symbol")), None)
            order = Order(
                id=order_id, intent_id=client_order_id, desk_id=intent.desk_id if intent else "",
                instrument=instrument_for({"symbol": first["symbol"], "asset_class": "us_option"}, venue=self.venue) if first else
                Instrument("option", "UNKNOWN", self.venue, multiplier=money(100), expiry="1970-01-01", strike=money(0), right="call"),
                side=str(row.get("side") or "buy"), quantity=dec(row.get("qty")) or money(0), order_type="limit",
                limit_price=None, time_in_force=str(row.get("time_in_force") or "day"), status=status, venue=self.venue,
                broker_order_id=str(row.get("id") or "") or None, filled_quantity=parent_filled, average_price=None, fees=money(0),
                submitted_at=_stamp(row.get("submitted_at") or row.get("created_at")),
                updated_at=_stamp(row.get("updated_at") or row.get("created_at")),
                reason="a multi-leg order this adapter cannot name as a structure; nothing of it is booked",
            )
            order._raw = {"status": row.get("status"), "order_class": "mleg", "unidentified": compact_order(row)}
            return order
        if instrument is None:
            instrument = s.instrument(spec, self.venue)
        if intent is not None:
            opening = intent.side == "buy"
        elif legs:
            opening = any(str(leg.get("position_intent") or "").endswith("_to_open") for leg in legs)
        else:  # an answer without its legs: what this adapter sent under this id, else the parent's own side
            with self._structure_lock:
                known = self._parent_side.get(str(row.get("id") or ""))
            opening = (known or str(row.get("side") or "buy")) == "buy"
        side = "buy" if opening else "sell"
        self._remember(row, legs, instrument, side)
        k = spec.collateral
        quantity = dec(row.get("qty")) or (intent.quantity if intent else money(0))
        by_symbol = {str(leg.get("symbol") or "").upper(): leg for leg in legs}
        leg_units: "Decimal | None" = None
        average: "Decimal | None" = None
        filled_by_leg: dict[str, Decimal] = {}
        if legs and all(leg.occ in by_symbol for leg in spec.legs):
            filled_by_leg = {leg.occ: dec(by_symbol[leg.occ].get("filled_qty"), "0") for leg in spec.legs}
            leg_units = min((filled_by_leg[leg.occ] / leg.ratio).to_integral_value(rounding=ROUND_FLOOR) for leg in spec.legs)
            prices = {leg.occ: dec(by_symbol[leg.occ].get("filled_avg_price")) for leg in spec.legs}
            if leg_units > 0 and all(prices[leg.occ] is not None for leg in spec.legs):
                average = k + sum((leg.sign * leg.ratio * prices[leg.occ] for leg in spec.legs), Decimal(0))
        if leg_units is None:
            filled, average = parent_filled, None
        else:
            filled = leg_units
        uneven = {occ: text(n) for occ, n in filled_by_leg.items()
                  if leg_units is not None and n != leg_units * next(leg.ratio for leg in spec.legs if leg.occ == occ)}
        reason = None
        if status == "filled" and (leg_units is None or filled < quantity or uneven):
            status = "partially_filled" if filled > 0 else "accepted"
        elif status in ("cancelled", "expired", "rejected") and uneven:
            reason = f"ERROR: the structure's legs filled unevenly ({', '.join(f'{k_}: {v}' for k_, v in sorted(uneven.items()))} contracts)"
            self._answer("uneven", spec.type, compact_order(row), always=True)
        elif status == "rejected":
            reason = message_of(row)
        if filled > 0 and average is not None:
            self._answer("fill", spec.type, compact_order(row))
        net = dec(row.get("limit_price"))
        limit = (k + net if opening else k - net) if net is not None else (intent.limit_price if intent else None)
        order = Order(
            id=order_id,
            intent_id=client_order_id,
            desk_id=intent.desk_id if intent else "",
            instrument=instrument,
            side=side,
            quantity=quantity,
            order_type="limit",
            limit_price=limit,
            time_in_force=str(row.get("time_in_force") or "day"),
            status=status,
            venue=self.venue,
            broker_order_id=str(row.get("id") or "") or None,
            filled_quantity=filled,
            average_price=average,
            fees=money(0),
            submitted_at=_stamp(row.get("submitted_at") or row.get("created_at")),
            updated_at=_stamp(row.get("updated_at") or row.get("created_at")),
            reason=reason,
        )
        order._raw = {"status": row.get("status"), "order_class": "mleg", "structure": spec.type,
                      "legs": [_pick(leg, LEG_FIELDS) for leg in legs], **({"uneven_legs": uneven} if uneven else {})}
        return order

    def _identify(self, legs: "list[dict[str, Any]]") -> Any:
        """The structure a multi-leg order's legs make, read from each leg's OCC symbol, `ratio_qty`
        and `position_intent` (long: `buy_to_open`/`sell_to_close`; short: `sell_to_open`/
        `buy_to_close`), or None. The admitted types are disjoint, so at most one `classify` holds."""
        s = _structures()
        parsed = []
        for row in legs:
            symbol = str(row.get("symbol") or "").upper()
            sign = LEG_SIGN.get(str(row.get("position_intent") or ""))
            ratio = dec(row.get("ratio_qty"))
            if not re.fullmatch(r"[A-Z]{1,6}[0-9]{6}[CP][0-9]{8}", symbol) or sign is None or ratio is None or ratio % 1 != 0:
                return None
            parsed.append(s.Leg(instrument_for({"symbol": symbol, "asset_class": "us_option"}, venue=self.venue), sign, int(ratio)))
        for type_ in s.TYPES:
            try:
                return s.classify(type_, parsed)
            except ValueError:
                continue
        return None

    def _remember(self, row: dict[str, Any], legs: "list[dict[str, Any]]", instrument: Instrument, side: str) -> None:
        """Keep what a multi-leg answer said of its ids, for `fills` and for a read without the intent."""
        parent = str(row.get("id") or "")
        with self._structure_lock:
            for key in (parent, str(row.get("client_order_id") or "")):
                if key:
                    self._structure_ids[key] = instrument
            if parent:
                self._parent_side[parent] = side
                self._leg_parent[parent] = parent
                for leg in legs:
                    if leg.get("id"):
                        self._leg_parent[str(leg["id"])] = parent
                        self._simple_ids.discard(str(leg["id"]))
            while len(self._structure_ids) > REMEMBERED_ORDERS:
                self._structure_ids.pop(next(iter(self._structure_ids)))
            while len(self._leg_parent) > 4 * REMEMBERED_ORDERS:
                self._leg_parent.pop(next(iter(self._leg_parent)))

    def _answer(self, stage: str, kind: str, detail: Any, *, always: bool = False) -> None:
        """Keep the first venue answer of `stage` for structure type `kind` (every one if `always`)."""
        with self._structure_lock:
            if not always and (stage, kind) in self._answered:
                return
            self._answered.add((stage, kind))
            if len(self._answers) < 200:
                self._answers.append({"stage": stage, "structure": kind, "venue": self.venue, "detail": detail})

    def drain_structure_answers(self) -> "list[dict[str, Any]]":
        """The venue answers kept since the last call, for the owner's record (the book writes them to
        the ledger as `ops.alert` rows): the first multi-leg order the venue answered for each type
        (`submit`), its first fill as the order shows it (`fill`) and as FILL activities (`activity`),
        and every refusal (`refused`) and uneven fill (`uneven`)."""
        with self._structure_lock:
            out, self._answers = self._answers, []
        return out


def _stamp(value: Any) -> "str | None":
    if not value:
        return None
    try:
        return iso(value)
    except Exception:
        return None


__all__ = [
    "AlpacaBroker",
    "is_structure",
    "mleg_body",
    "mleg_limit",
    "AlpacaCredentials",
    "alpaca_symbol",
    "instrument_for",
    "PAPER_BASE",
    "LIVE_BASE",
    "DATA_BASE",
    "STATUS_MAP",
    "CAPABILITIES",
]
