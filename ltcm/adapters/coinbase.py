"""Coinbase Advanced Trade: spot crypto on `api.coinbase.com`.

Auth is a short-lived CDP JWT in `Authorization: Bearer`
(https://docs.cdp.coinbase.com/api-reference/v2/authentication). The header carries
`alg` (`ES256` for an ECDSA PEM key, `EdDSA` for an Ed25519 secret), `typ`, `kid` = the key id
and a random `nonce`; the payload carries `sub` = the key id, `iss` = `"cdp"`, `nbf` = now,
`exp` = now + 120 and `uri` = `"METHOD api.coinbase.com/path"`. A fresh token is minted per
request because the `uri` claim binds it to that one method and path.

Endpoints:

    GET  /api/v3/brokerage/accounts                 .../rest-api/accounts/list-accounts
    POST /api/v3/brokerage/orders                   .../rest-api/orders/create-order
    GET  /api/v3/brokerage/orders/historical/{id}   .../rest-api/orders/get-order
    GET  /api/v3/brokerage/orders/historical/batch  .../rest-api/orders/list-orders
    GET  /api/v3/brokerage/orders/historical/fills  .../rest-api/orders/list-fills
    POST /api/v3/brokerage/orders/batch_cancel      .../rest-api/orders/cancel-order

    all under https://docs.cdp.coinbase.com/api-reference/advanced-trade-api/

Order configuration is the one place the venue's vocabulary really differs:
a market order is `market_market_ioc` with a `base_size` (or `quote_size` to spend a dollar
amount), and a resting limit is `limit_limit_gtc` with `base_size` and `limit_price`, or
`limit_limit_gtd` with an `end_time` when the entry states an expiry. Coinbase has no day order
and no immediate-or-cancel *limit* in this adapter, so `capabilities()` does not claim them.

The create-order response carries **no top-level `order_id`**: it is
`success_response.order_id`, and `success: false` means the order was refused, with the reason in
`error_response`.
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
    money,
    rfc3339,
    text,
)
from ..data import TransportError, iso
from ..data.coinbase import HOST, PREFIX, CoinbaseMarketData, expiry_of, is_future, product_id
from . import (
    CoinbaseCredentials,
    VenueClient,
    confirm_or_unknown,
    dec,
    jws,
    message_of,
    new_nonce,
    require_ok,
)

VENUE = "coinbase"
API_HOST = "api.coinbase.com"
JWT_LIFETIME = 120

#: `short` is for the CDE futures only: a spot coin the desk does not hold cannot be sold
#: (`risk.rule_short` refuses a short on a crypto instrument whatever the venue lists).
CAPABILITIES = {"crypto", "future", "limit", "gtc", "fractional", "short"}
#: Sept 17, 2026: Coinbase Financial Markets' nano contracts are charged per contract, not as a
#: percentage of notional; the schedule is not in the API. UNVERIFIED until the first fill, which
#: carries the real commission and corrects the record.
FUTURES_FEE_PER_CONTRACT = Decimal("0.20")

#: Coinbase's ten order states mapped onto this runtime's vocabulary.
STATUS_MAP: dict[str, str] = {
    "PENDING": "accepted",
    "QUEUED": "accepted",
    "OPEN": "accepted",
    "EDIT_QUEUED": "accepted",
    "CANCEL_QUEUED": "accepted",
    "FILLED": "filled",
    "CANCELLED": "cancelled",
    "EXPIRED": "expired",
    "FAILED": "rejected",
    "UNKNOWN_ORDER_STATUS": "unknown",
}


def order_configuration(intent: OrderIntent) -> dict[str, Any]:
    """The `order_configuration` object for one intent.

    Market orders become `market_market_ioc` with a `base_size`: the desk's quantity is always a
    quantity of the base asset, never a dollar amount, so `quote_size` is deliberately not used.
    Limit orders become `limit_limit_gtc`; Coinbase has no `day` order, so a day limit would
    silently outlive its session and is refused instead. A limit with an `expires_at` becomes
    `limit_limit_gtd`, which the venue cancels at `end_time` whether or not the floor is running.
    """
    size = text(intent.quantity)
    expires_at = getattr(intent, "expires_at", None)
    if intent.order_type == "market":
        if expires_at is not None:
            raise RejectedOrder("coinbase: only a resting limit can carry an end time")
        if intent.time_in_force not in ("ioc", "day", "gtc"):
            raise RejectedOrder(f"coinbase: unsupported time in force {intent.time_in_force!r}")
        return {"market_market_ioc": {"base_size": size}}
    if intent.time_in_force != "gtc":
        raise RejectedOrder(
            "coinbase limit orders are good-till-cancelled only; "
            f"{intent.time_in_force!r} would not expire when this desk expects"
        )
    if expires_at is not None:
        return {
            "limit_limit_gtd": {
                "base_size": size,
                "limit_price": text(intent.limit_price),
                "end_time": rfc3339(expires_at),
                "post_only": bool(getattr(intent, "post_only", False)),
            }
        }
    return {
        "limit_limit_gtc": {
            "base_size": size,
            "limit_price": text(intent.limit_price),
            # A post-only limit rests or is rejected; it never takes, so it pays the maker rate.
            "post_only": bool(getattr(intent, "post_only", False)),
        }
    }


# leap: exits. Coinbase's own failure reasons for an attached take-profit/stop-loss, from the
# `FailureReason` enum in the Advanced Trade spec. A refusal naming one of these is the bracket's
# fault, not the entry's, so the entry is retried bare and the floor enforces the plan itself.
BRACKET_FAILURES = ("ATTACHED", "BRACKET", "TPSL", "TP_SL")


def attached_bracket(intent: OrderIntent) -> dict[str, Any] | None:
    """The `attached_order_configuration` for an entry that names both a target and a stop.

    Coinbase: *"Include `attached_order_configuration` in the Create Order request body with
    `trigger_bracket_gtc` to create a TP/SL order. Do not include size as the attached TP/SL
    order will have the same size as the originating order."* Both legs are required
    (`SINGLE_LEGGED_ATTACHED_ORDER_CONFIGURATION_NOT_ALLOWED`), only market and limit parents
    are eligible, and the stop is a stop-*limit* with a hard-coded five percent cushion, so a
    gap larger than that can leave it unfilled -- which is why the floor also keeps its own
    stop in `ltcm/exits.py`. UNVERIFIED against a live order: the shape is from the spec.

    An entry with an end time carries no bracket. Only GTC orders can carry an attached order,
    and the edit docs list end-time failures for them; the floor keeps that entry's plan itself.
    """
    if intent.purpose != "entry" or intent.target_price is None or intent.stop_price is None:
        return None
    if getattr(intent, "expires_at", None) is not None:
        return None
    return {
        "trigger_bracket_gtc": {
            "limit_price": text(intent.target_price),
            "stop_trigger_price": text(intent.stop_price),
        }
    }


def bracket_refused(message: str) -> bool:
    """True when a refusal blames the attached bracket rather than the entry itself."""
    upper = str(message or "").upper()
    return any(token in upper for token in BRACKET_FAILURES)


class CoinbaseBroker:
    """A `Broker` over Coinbase Advanced Trade, with a fresh JWT per request."""

    def __init__(
        self,
        credentials: CoinbaseCredentials,
        *,
        transport: Any = None,
        client: Any = None,
        market_data: Any = None,
        clock: Any = None,
        nonce: Any = new_nonce,
        venue: str = VENUE,
        host: str = HOST,
        timeout: float = 20.0,
    ):
        self.credentials = credentials
        self.venue = venue
        self.host = host.rstrip("/")
        self.api_host = urllib.parse.urlsplit(self.host).netloc or API_HOST
        self.client = client or VenueClient(transport, timeout=timeout)
        if clock is None:
            import time as _time

            clock = _time.time
        self.clock = clock
        self.nonce = nonce
        self.market_data = market_data or CoinbaseMarketData(
            getattr(self.client, "transport", None), host=self.host, clock=clock
        )

    # ------------------------------------------------------------------- jwt
    def token(self, method: str, path: str) -> str:
        """One CDP JWT bound to `"METHOD host/path"`, valid for 120 seconds."""
        now = int(float(self.clock()))
        key_id = self.credentials.key_id
        header = {
            "alg": self.credentials.signer.algorithm,
            "typ": "JWT",
            "kid": key_id,
            "nonce": self.nonce() if callable(self.nonce) else str(self.nonce),
        }
        payload = {
            "sub": key_id,
            "iss": "cdp",
            "nbf": now,
            "exp": now + JWT_LIFETIME,
            "uri": f"{method.upper()} {self.api_host}{path}",
        }
        return jws(header, payload, self.credentials.signer)

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
        """One authenticated request. The JWT `uri` claim covers the path without its query."""
        url = self.host + path
        if params:
            pairs = [(k, v) for k, v in params.items() if v is not None and v != ""]
            if pairs:
                url += "?" + urllib.parse.urlencode(pairs, doseq=True)
        headers = {"Authorization": "Bearer " + self.token(method, path)}
        status, payload = self.client.request(method, url, headers=headers, body=body, what=what)
        return require_ok(status, payload, what=what, ok=ok)

    def capabilities(self) -> set[str]:
        return set(CAPABILITIES)

    # --------------------------------------------------------------- account
    def accounts(self) -> list[dict[str, Any]]:
        """`GET /api/v3/brokerage/accounts`, following the cursor to the end."""
        rows: list[dict[str, Any]] = []
        cursor: "str | None" = None
        for _ in range(20):  # 20 pages of 250 is far more than this floor will ever hold
            payload = self._call(
                "GET",
                PREFIX + "/accounts",
                params={"limit": 250, "cursor": cursor},
                what="coinbase accounts",
                ok=(200,),
            )
            page = payload.get("accounts") if isinstance(payload, dict) else None
            if not isinstance(page, list):
                break
            rows.extend(row for row in page if isinstance(row, dict))
            if not payload.get("has_next"):
                break
            cursor = payload.get("cursor") or None
            if not cursor:
                break
        return rows

    def fee_rates(self) -> dict[str, str]:
        """The account's actual current tier; read-only, no default invented on failure."""
        payload = self._call("GET", PREFIX + "/transaction_summary", what="coinbase fee tier", ok=(200,))
        tier = payload.get("fee_tier") or {}
        result = {}
        for side in ("maker", "taker"):
            value = money(tier.get(side + "_fee_rate"))
            if not value.is_finite() or not 0 <= value <= Decimal("0.1"):
                raise ValueError("invalid Coinbase fee tier")
            result[side] = str(value)
        result["future_contract"] = str(FUTURES_FEE_PER_CONTRACT)
        return result

    # ------------------------------------------------------------- futures (CDE)
    def futures_summary(self) -> dict[str, Any]:
        """`GET /api/v3/brokerage/cfm/balance_summary`: the futures wallet's USD, unrealized P&L
        and buying power. Empty when the account has no derivatives access."""
        payload = self._call("GET", PREFIX + "/cfm/balance_summary", what="coinbase futures balance", ok=(200,))
        summary = payload.get("balance_summary") if isinstance(payload, dict) else None
        return summary if isinstance(summary, dict) else {}

    def contract_size(self, product: str) -> Decimal:
        """A CDE contract's size in its underlying (BIP: 0.01 BTC), from the product listing and
        cached: the size is the instrument's multiplier everywhere the floor prices it."""
        cache = getattr(self, "_contract_sizes", None)
        if cache is None:
            cache = self._contract_sizes = {}
        pid = product_id(product)
        if pid not in cache:
            row = self.market_data.product(pid)
            size = row.get("contract_size")
            if size is None or size <= 0:
                raise RejectedOrder(f"coinbase: {pid} lists no contract size")
            cache[pid] = money(size)
        return cache[pid]

    def futures_positions(self) -> list[Position]:
        """`GET /api/v3/brokerage/cfm/positions` as positions: contracts signed by side, the
        venue's average entry as cost, its current price as the mark, the contract size as the
        multiplier so `market_value` and `cost_basis` are the position's notional."""
        payload = self._call("GET", PREFIX + "/cfm/positions", what="coinbase futures positions", ok=(200,))
        rows = payload.get("positions") if isinstance(payload, dict) else None
        out: list[Position] = []
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict) or not row.get("product_id"):
                continue
            pid = str(row["product_id"])
            contracts = dec(row.get("number_of_contracts"))
            if contracts is None or contracts == 0:
                continue
            side = str(row.get("side") or "").upper()
            signed = -abs(contracts) if side in ("SHORT", "SELL", "FUTURES_POSITION_SIDE_SHORT") else abs(contracts)
            try:
                size = self.contract_size(pid)
            except Exception:
                size = money(1)
            instrument = Instrument("future", pid, self.venue, multiplier=size, expiry=expiry_of(pid), market_id=pid)
            mark = dec(row.get("current_price")) or self._mark(instrument)
            out.append(
                Position(
                    instrument=instrument,
                    quantity=signed,
                    average_cost=dec(row.get("avg_entry_price")) or (mark if mark is not None else money(0)),
                    mark=mark,
                    as_of=iso(self.clock()),
                )
            )
        return out

    def balance(self) -> Balance:
        """Cash is the available USD balance; equity adds every crypto holding at its mark."""
        cash = money(0)
        held = money(0)
        positions = self.positions()
        for row in self.accounts():
            available = row.get("available_balance") or {}
            currency = str(available.get("currency") or row.get("currency") or "")
            if currency.upper() == "USD":
                cash += dec(available.get("value"), "0")
                # USD behind resting bids sits in `hold`, still ours: without it the floor read a
                # $25 loss for every maker bid it posted (Sept 16, 2026, the first spot quotes).
                held += dec((row.get("hold") or {}).get("value"), "0") or money(0)
        equity = cash + held
        for position in positions:
            if position.instrument.asset_class == "future":
                continue  # a future's notional is not equity; its P&L comes with the futures wallet
            value = position.market_value
            if value is not None:
                equity += value
        # leap: futures -- the CFM wallet: margin moved there and the unrealized P&L of the
        # contracts it backs. Unreadable (no derivatives access) means nothing there, not an error.
        futures_cash = money(0)
        try:
            summary = self.futures_summary()
        except Exception:
            summary = {}
        if summary:
            futures_cash = dec((summary.get("cfm_usd_balance") or {}).get("value"), "0") or money(0)
            unrealized = dec((summary.get("unrealized_pnl") or {}).get("value"), "0") or money(0)
            equity += futures_cash + unrealized
        return Balance(
            venue=self.venue,
            cash=cash + held + futures_cash,
            equity=equity,
            buying_power=cash + futures_cash,
            as_of=iso(self.clock()),
        )

    def positions(self) -> list[Position]:
        """Non-USD balances as positions.

        Advanced Trade accounts report a balance, not a cost basis, so `average_cost` is set to
        the current mark and the unrealized P&L on these objects reads zero. The floor's own
        ledger, which has every fill, is the source of truth for cost and profit.
        """
        out: list[Position] = []
        for row in self.accounts():
            available = row.get("available_balance") or {}
            currency = str(available.get("currency") or row.get("currency") or "").upper()
            quantity = dec(available.get("value"))
            hold = dec((row.get("hold") or {}).get("value"), "0") or money(0)
            if not currency or currency == "USD" or quantity is None:
                continue
            total = quantity + hold
            if total <= 0:
                continue
            instrument = Instrument(
                "crypto", f"{currency}-USD", self.venue, market_id=f"{currency}-USD"
            )
            mark = self._mark(instrument)
            out.append(
                Position(
                    instrument=instrument,
                    quantity=total,
                    average_cost=mark if mark is not None else money(0),
                    mark=mark,
                    as_of=iso(self.clock()),
                )
            )
        try:
            out.extend(self.futures_positions())
        except Exception:
            pass  # no derivatives access, or the futures endpoint is down: the spot book stands
        return out

    def _mark(self, instrument: Instrument) -> "Decimal | None":
        try:
            quote = self.market_data.quote(instrument)
        except Exception:
            return None
        return quote.mid if quote.mid is not None else quote.last

    def quote(self, instrument: Instrument) -> Quote:
        """Public market data; the product book needs no credential."""
        return self.market_data.quote(instrument)

    # ---------------------------------------------------------------- orders
    def order_body(self, intent: OrderIntent) -> dict[str, Any]:
        """The create-order request body, with the intent id as `client_order_id`."""
        body = {
            "client_order_id": intent.id,
            "product_id": product_id(intent.instrument),
            "side": intent.side.upper(),
            "order_configuration": order_configuration(intent),
        }
        bracket = attached_bracket(intent)  # leap: exits
        if bracket is not None:
            body["attached_order_configuration"] = bracket
        return body

    def submit(self, intent: OrderIntent) -> Order:
        """`POST /api/v3/brokerage/orders`. A refusal arrives as `success: false`, not a 4xx."""
        if intent.instrument.asset_class == "future":
            if not is_future(product_id(intent.instrument)):
                raise RejectedOrder(f"coinbase futures are CDE products, not {intent.instrument.symbol!r}")
            if intent.quantity != intent.quantity.to_integral_value():
                raise RejectedOrder("coinbase futures trade in whole contracts")
        elif intent.instrument.asset_class != "crypto":
            raise RejectedOrder(f"coinbase trades crypto and its CDE futures, not {intent.instrument.asset_class}")
        body = self.order_body(intent)
        attached = "attached_order_configuration" in body
        try:
            payload = self._call("POST", PREFIX + "/orders", body=body, what="coinbase submit")
        except TransportError as exc:
            return confirm_or_unknown(
                lambda: self.order_by_client_id(intent.id),
                what="coinbase submit",
                detail=f"no response ({type(exc).__name__})",
            )
        if not isinstance(payload, dict):
            raise UnknownOutcome("coinbase submit: unreadable response; reconcile before retrying")
        if not payload.get("success"):
            error = payload.get("error_response") or payload.get("error") or {}
            message = message_of(error) or "refused"
            if attached and bracket_refused(message):
                # leap: exits. The venue refused the bracket, not the trade: send the entry
                # bare and let the floor hold the stop and the target itself.
                bare = {k: v for k, v in body.items() if k != "attached_order_configuration"}
                try:
                    payload = self._call("POST", PREFIX + "/orders", body=bare, what="coinbase submit")
                except TransportError as exc:
                    return confirm_or_unknown(
                        lambda: self.order_by_client_id(intent.id),
                        what="coinbase submit",
                        detail=f"no response ({type(exc).__name__})",
                    )
                attached = False
                if not isinstance(payload, dict):
                    raise UnknownOutcome("coinbase submit: unreadable response; reconcile before retrying")
                if not payload.get("success"):
                    error = payload.get("error_response") or payload.get("error") or {}
                    raise RejectedOrder(f"coinbase submit: {message_of(error) or 'refused'}")
            else:
                raise RejectedOrder(f"coinbase submit: {message}")
        success = payload.get("success_response")
        if not isinstance(success, dict) or not success.get("order_id"):
            raise UnknownOutcome("coinbase submit: no order id in a successful response")
        order = Order.from_intent(intent, venue=self.venue)
        order.status = "accepted"
        order.broker_order_id = str(success["order_id"])
        order.submitted_at = iso(self.clock())
        order.updated_at = order.submitted_at
        order._raw = {"success": True}
        if "attached_order_configuration" in body:
            order._raw["bracket"] = attached  # the floor reads this into the order record
        return order

    def get_order(self, order_id: str) -> Order:
        if isinstance(order_id, str) and order_id.startswith("ord-"):
            found = self.order_by_client_id("oi-" + order_id[4:])
            if found is None:
                raise RejectedOrder(f"coinbase: no order for {order_id}")
            return found
        payload = self._call(
            "GET",
            f"{PREFIX}/orders/historical/{urllib.parse.quote(str(order_id))}",
            what="coinbase order",
            ok=(200,),
        )
        row = payload.get("order") if isinstance(payload, dict) else None
        if not isinstance(row, dict):
            raise RejectedOrder(f"coinbase: no order for {order_id}")
        return self.parse_order(row)

    def list_orders(self, *, order_status: "str | None" = None, limit: int = 100) -> list[Order]:
        """`GET /api/v3/brokerage/orders/historical/batch`."""
        payload = self._call(
            "GET",
            PREFIX + "/orders/historical/batch",
            params={"order_status": order_status, "limit": max(1, min(int(limit), 1000))},
            what="coinbase orders",
            ok=(200,),
        )
        rows = payload.get("orders") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            return []
        return [self.parse_order(row) for row in rows if isinstance(row, dict)]

    def open_orders(self) -> list[Order]:
        return self.list_orders(order_status="OPEN")

    def order_by_client_id(self, client_order_id: str) -> "Order | None":
        """Coinbase has no lookup by client order id, so recent orders are scanned locally."""
        for status in ("OPEN", None):
            for order in self.list_orders(order_status=status, limit=250):
                if order.intent_id == client_order_id:
                    return order
        return None

    def cancel(self, order_id: str) -> Order:
        """`POST /api/v3/brokerage/orders/batch_cancel` with a single id."""
        order = self.get_order(order_id)
        if order.terminal:
            return order
        venue_id = order.broker_order_id or order_id
        payload = self._call(
            "POST",
            PREFIX + "/orders/batch_cancel",
            body={"order_ids": [str(venue_id)]},
            what="coinbase cancel",
        )
        results = payload.get("results") if isinstance(payload, dict) else None
        first = results[0] if isinstance(results, list) and results else {}
        if isinstance(first, dict) and not first.get("success"):
            reason = str(first.get("failure_reason") or "")
            if reason not in ("ORDER_IS_FULLY_FILLED", "UNKNOWN_CANCEL_ORDER", "DUPLICATE_CANCEL_REQUEST"):
                raise RejectedOrder(f"coinbase cancel: {reason or 'refused'}")
        order.status = "cancelled"
        order.reason = "cancelled by request"
        order.updated_at = iso(self.clock())
        return order

    # ----------------------------------------------------------------- fills
    def fills(self, since: "str | None" = None) -> list[Fill]:
        """`GET /api/v3/brokerage/orders/historical/fills`, oldest first."""
        params: dict[str, Any] = {"limit": 250}
        if since:
            params["start_sequence_timestamp"] = iso(since)
        payload = self._call(
            "GET",
            PREFIX + "/orders/historical/fills",
            params=params,
            what="coinbase fills",
            ok=(200,),
        )
        rows = payload.get("fills") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            return []
        out: list[Fill] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            size = dec(row.get("size"))
            price = dec(row.get("price"))
            pid = str(row.get("product_id") or "")
            if size is None or price is None or size <= 0 or not pid:
                continue
            out.append(
                Fill(
                    id=str(row.get("trade_id") or row.get("entry_id") or ""),
                    order_id=str(row.get("order_id") or ""),
                    desk_id="",
                    instrument=Instrument("crypto", pid, self.venue, market_id=pid),
                    side=str(row.get("side") or "BUY").lower(),
                    quantity=size,
                    price=price,
                    fee=abs(dec(row.get("commission"), "0") or money(0)),
                    at=iso(row.get("trade_time") or row.get("sequence_timestamp") or 0),
                )
            )
        out.sort(key=lambda fill: fill.at)
        return out

    # --------------------------------------------------------------- parsing
    def parse_order(self, row: dict[str, Any]) -> Order:
        pid = str(row.get("product_id") or "")
        instrument = Instrument("crypto", pid or "UNKNOWN-USD", self.venue, market_id=pid or None)
        client_order_id = str(row.get("client_order_id") or "")
        configuration = row.get("order_configuration") or {}
        limit_price = None
        size = None
        if isinstance(configuration, dict):
            for name, leg in configuration.items():
                if not isinstance(leg, dict):
                    continue
                limit_price = dec(leg.get("limit_price")) or limit_price
                size = dec(leg.get("base_size")) or size
        filled = dec(row.get("filled_size"), "0") or money(0)
        order = Order(
            id="ord-" + client_order_id[3:] if client_order_id.startswith("oi-") else
               ("ord-" + client_order_id if client_order_id else "ord-" + str(row.get("order_id") or "")),
            intent_id=client_order_id,
            desk_id="",
            instrument=instrument,
            side=str(row.get("side") or "BUY").lower(),
            quantity=size if size is not None else filled,
            order_type="limit" if str(row.get("order_type") or "") == "LIMIT" else "market",
            limit_price=limit_price,
            time_in_force="gtc",
            status=STATUS_MAP.get(str(row.get("status") or ""), "unknown"),
            venue=self.venue,
            broker_order_id=str(row.get("order_id") or "") or None,
            filled_quantity=filled,
            average_price=dec(row.get("average_filled_price")),
            fees=dec(row.get("total_fees"), "0") or money(0),
            submitted_at=_stamp(row.get("created_time")),
            updated_at=_stamp(row.get("last_update_time") or row.get("created_time")),
            reason=_reason_of(row),
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
    "CoinbaseBroker",
    "CoinbaseCredentials",
    "order_configuration",
    "STATUS_MAP",
    "CAPABILITIES",
    "HOST",
    "PREFIX",
    "JWT_LIFETIME",
]


def _reason_of(row: "dict[str, Any]") -> "str | None":
    """A human reason only for orders that were actually refused or cancelled."""
    status = str(row.get("status") or "").upper()
    if status in ("CANCELLED", "CANCEL_QUEUED", "FAILED", "EXPIRED", "REJECTED"):
        text = str(row.get("reject_reason") or row.get("cancel_message") or "").strip()
        return text if text and text != "REJECT_REASON_UNSPECIFIED" else (status.lower() or None)
    return None
