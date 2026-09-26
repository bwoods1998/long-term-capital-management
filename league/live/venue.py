"""The live path's reads and writes at the Brokerage Account and its practice twin, through the gateway.

The options-swarm run, Wave 5 (Sept 26, 2026). The House holds no venue key: every call below goes through the
Cloudflare gateway (`ltcm.adapters.VenueClient` in gateway mode, the bearer token only), which signs it, enforces the
caps and the kill switch, and refuses any path it does not list. Two accounts: `alpaca` (the Brokerage Account, real
money) and `alpaca-paper` (the practice account: it proves the multi-leg route, never the calibration). Market data
reads through the real account's credential (the kill switch stops orders, never reads).

Shapes read Sept 26, 2026 through the gateway (kept out of git; the tests' fixtures copy the SHAPES with invented
numbers, since the data licence forbids publishing quotes):

- `GET v1beta1/options/snapshots/<U>?feed=opra&limit=1000&expiration_date_gte=&expiration_date_lte=&strike_price_gte=
  &strike_price_lte=&page_token=` answers `{"snapshots": {<OCC>: {"latestQuote": {"ap", "as", "bp", "bs", "t", ...},
  ...}}, "next_page_token": <str|null>}`, the symbols in no particular order. SPXW's chain is under `SPXW` (`SPX`
  lists the monthly AM-settled SPX contracts); XSP's under `XSP`. A price is a JSON number (an int when whole, as `"bp":
  0`); `t` is RFC 3339 with nanoseconds.
- `GET v1beta1/options/snapshots?symbols=<a,b>&feed=opra`: the same rows for named contracts (held legs).
- `GET v2/stocks/snapshots?symbols=SPY,QQQ&feed=sip`: `{<SYM>: {"latestTrade": {"p", "t"}, "latestQuote": {"ap",
  "bp", "t"}, "minuteBar", "dailyBar", "prevDailyBar"}}`.
- `GET v2/account`: strings for every number: `equity`, `last_equity` (the equity at the previous session's 16:00 ET),
  `options_buying_power`, `buying_power`, `cash`, `multiplier`, `options_trading_level`.
- `GET v2/positions`: `[{symbol, asset_class ("us_option", "us_equity", "crypto"), qty (signed), qty_available, side
  ("long"/"short"), avg_entry_price, current_price, ...}]` (the legacy LTC dust is `LTCUSD`, crypto).
- `GET v2/orders?status=all&nested=true&after=&limit=500`: order rows; a multi-leg parent (`order_class` "mleg")
  carries `legs`, each with its own `id`, `symbol`, `side`, `position_intent`, `ratio_qty`, `qty`, `filled_qty`,
  `filled_avg_price`, `status` (Alpaca's documented response; no multi-leg order has been sent on either account yet).
- `GET v2/account/activities?activity_types=...&after=&direction=asc&page_size=100&page_token=<last id>`: `{id,
  activity_type, date | transaction_time, net_amount, qty, symbol, ...}`; funding types are `league.performance.
  ALPACA_FUNDING`, and the option events OPASN (assigned), OPEXC (exercised), OPEXP (expired).

Rate: the trading API allows 200 requests a minute; the House keeps under the constitution's
`order_path.max_requests_minute` (150), counted here over a sliding minute per account (`Rate`). A call that would pass
it waits (`Rate.room`) unless it is an exit's order or cancel, which always goes. Market data (10,000 a minute with the
subscription) is counted but not held back.
"""

from __future__ import annotations

import collections
import threading
import time
import urllib.parse
from datetime import datetime
from decimal import Decimal
from typing import Any, Callable, Iterable, Mapping, Sequence

from league.data import TransportError

LIVE_BASE = "https://api.alpaca.markets"
PAPER_BASE = "https://paper-api.alpaca.markets"
DATA_BASE = "https://data.alpaca.markets"
PURPOSE_HEADER = "X-LTCM-Purpose"
#: The option events the live path reads for assignments and expiries.
OPTION_EVENTS = ("OPASN", "OPEXC", "OPEXP")
#: Alpaca's order states that end an order (anything else is working).
TERMINAL = frozenset({"filled", "canceled", "expired", "rejected", "done_for_day", "replaced", "stopped", "suspended"})
WORKING = frozenset({"new", "accepted", "pending_new", "accepted_for_bidding", "partially_filled", "pending_cancel",
                     "pending_replace", "calculated", "held"})
MAX_PAGES = 50


class VenueError(RuntimeError):
    """A read that did not answer as documented (the message says which)."""


def parse_time(value: Any) -> float | None:
    """Epoch seconds from an RFC 3339 stamp (nanoseconds cut to microseconds), or None."""
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    if "." in text:
        head, _, rest = text.partition(".")
        n = 0
        while n < len(rest) and rest[n].isdigit():
            n += 1
        text = f"{head}.{rest[:n][:6].ljust(6, '0')}{rest[n:]}"
    try:
        stamp = datetime.fromisoformat(text)
    except ValueError:
        return None
    if stamp.tzinfo is None:
        return None  # a time with no zone is no time: never read as this machine's local time
    return stamp.timestamp()


def occ_parts(symbol: str) -> tuple[str, str, bool, float] | None:
    """(root, "YYYY-MM-DD", is_call, strike) of a standard OCC symbol, or None."""
    s = str(symbol or "").strip().upper()
    if len(s) < 16 or s[-9] not in "CP" or not s[-15:-9].isdigit() or not s[-8:].isdigit() or not s[:-15].isalpha():
        return None
    return s[:-15], f"20{s[-15:-13]}-{s[-13:-11]}-{s[-11:-9]}", s[-9] == "C", int(s[-8:]) / 1000.0


def occ_symbol(root: str, expiry: str, is_call: bool, strike: float) -> str:
    day = str(expiry).replace("-", "")
    return f"{root.upper()}{day[2:]}{'C' if is_call else 'P'}{int(round(float(strike) * 1000)):08d}"


def num(value: Any) -> float:
    """A venue number as a float (NaN when absent or unreadable)."""
    try:
        out = float(value)
    except (TypeError, ValueError):
        return float("nan")
    return out


def dec(value: Any) -> Decimal | None:
    try:
        out = Decimal(str(value))
    except Exception:  # noqa: BLE001
        return None
    return out if out.is_finite() else None


class Rate:
    """Requests over a sliding minute (thread-safe)."""

    def __init__(self, limit: int, *, clock: Callable[[], float] = time.monotonic):
        self.limit, self.clock = int(limit), clock
        self.times: collections.deque[float] = collections.deque()
        self.lock = threading.Lock()
        self.refused = 0

    def _trim(self, now: float) -> None:
        while self.times and now - self.times[0] >= 60.0:
            self.times.popleft()

    def used(self) -> int:
        with self.lock:
            self._trim(self.clock())
            return len(self.times)

    def take(self, *, force: bool = False) -> bool:
        """Count one request; False (and nothing counted) when the minute is full, unless `force`."""
        with self.lock:
            now = self.clock()
            self._trim(now)
            if len(self.times) >= self.limit and not force:
                self.refused += 1
                return False
            self.times.append(now)
            return True


class RateLimited(RuntimeError):
    """The House's own request budget for the minute is spent (nothing was sent)."""


class Account:
    """One Alpaca account through the gateway: `alpaca` (real) or `alpaca-paper` (practice)."""

    def __init__(self, client: Any, *, venue: str, max_requests_minute: int = 150, clock: Callable[[], float] = time.time):
        if venue not in ("alpaca", "alpaca-paper"):
            raise ValueError(venue)
        self.client, self.venue, self.clock = client, venue, clock
        self.base = LIVE_BASE if venue == "alpaca" else PAPER_BASE
        self.rate = Rate(max_requests_minute)
        self.calls = 0

    @property
    def real(self) -> bool:
        return self.venue == "alpaca"

    def _call(self, method: str, path: str, *, params: Mapping[str, Any] | None = None, body: Any = None,
              headers: Mapping[str, str] | None = None, force: bool = False, what: str = "") -> tuple[int, Any]:
        if not self.rate.take(force=force):
            raise RateLimited(f"{self.venue}: {self.rate.limit} requests this minute already")
        query = ("?" + urllib.parse.urlencode({k: v for k, v in (params or {}).items() if v is not None})) if params else ""
        self.calls += 1
        return self.client.request(method, self.base + path + query, body=body, headers=dict(headers or {}),
                                   what=what or f"{self.venue} {path}")

    def _ok(self, status: int, payload: Any, what: str) -> Any:
        if 200 <= status < 300:
            return payload
        message = payload.get("message") if isinstance(payload, dict) else payload
        raise VenueError(f"{self.venue} {what}: HTTP {status} {str(message or '')[:200]}")

    # ---------------------------------------------------------------- reads
    def account(self) -> dict[str, Any]:
        row = self._ok(*self._call("GET", "/v2/account"), "account")
        if not isinstance(row, dict) or dec(row.get("equity")) is None:
            raise VenueError(f"{self.venue} account: no equity")
        return row

    def positions(self) -> list[dict[str, Any]]:
        rows = self._ok(*self._call("GET", "/v2/positions"), "positions")
        if not isinstance(rows, list):
            raise VenueError(f"{self.venue} positions: not a list")
        return rows

    def orders(self, *, status: str = "all", after: str | None = None, limit: int = 500) -> list[dict[str, Any]]:
        rows = self._ok(*self._call("GET", "/v2/orders", params={"status": status, "nested": "true", "after": after,
                                                                  "limit": limit, "direction": "asc"}), "orders")
        if not isinstance(rows, list):
            raise VenueError(f"{self.venue} orders: not a list")
        return rows

    def order_by_client_id(self, client_order_id: str) -> dict[str, Any] | None:
        status, payload = self._call("GET", "/v2/orders:by_client_order_id",
                                     params={"client_order_id": client_order_id, "nested": "true"}, force=True)
        if status == 404:
            return None
        return self._ok(status, payload, "order by client id")

    def activities(self, types: Sequence[str], *, after: str | None = None) -> list[dict[str, Any]]:
        """Every activity of `types` after `after` (oldest first), every page."""
        out, token, seen = [], None, set()
        for _ in range(MAX_PAGES):
            rows = self._ok(*self._call("GET", "/v2/account/activities", params={
                "activity_types": ",".join(types), "after": after, "direction": "asc", "page_size": 100,
                "page_token": token}), "activities")
            if not isinstance(rows, list):
                raise VenueError(f"{self.venue} activities: not a list")
            fresh = [r for r in rows if isinstance(r, dict) and r.get("id") not in seen]
            if not fresh:
                return out
            for r in fresh:
                seen.add(r.get("id"))
            out.extend(fresh)
            if len(rows) < 100:
                return out
            token = rows[-1].get("id")
            if not token:
                return out
        raise VenueError(f"{self.venue} activities: more than {MAX_PAGES} pages")

    # ---------------------------------------------------------------- writes
    def submit(self, body: Mapping[str, Any], *, exit: bool) -> "Submitted":
        """POST one order. Never retried: a lost answer is `unknown`, and the caller looks it up by its client id."""
        try:
            status, payload = self._call("POST", "/v2/orders", body=dict(body), force=exit,
                                         headers={PURPOSE_HEADER: "exit" if exit else "entry"}, what=f"{self.venue} order")
        except RateLimited as exc:
            return Submitted(False, None, str(exc), sent=False)
        except TransportError as exc:
            return Submitted(False, None, f"no answer: {str(exc)[:200]}", unknown=True)
        if 200 <= status < 300 and isinstance(payload, dict) and payload.get("id"):
            return Submitted(True, payload, "", status=status)
        if 200 <= status < 300:
            # Accepted, but no order id to track it by: the order may exist. Unknown, looked up by its client id.
            return Submitted(False, None, f"HTTP {status} without an order id", unknown=True, status=status)
        message = str((payload.get("message") or payload.get("error") if isinstance(payload, dict) else payload) or "")[:300]
        # A refusal the gateway made before forwarding names the cap it hit (`cap`: "equity", "order", "day_orders", ...):
        # nothing reached the venue. Its own 502 ("did not answer") and any other 5xx or timeout after dispatch may still
        # have made an order: unknown, looked up by the client order id.
        if (status >= 500 or status == 408) and not (isinstance(payload, dict) and payload.get("cap")):
            return Submitted(False, None, f"HTTP {status} {message}", unknown=True, status=status)
        return Submitted(False, payload if isinstance(payload, dict) else None, f"HTTP {status} {message}", status=status)

    def cancel(self, venue_id: str) -> tuple[bool, str]:
        """DELETE one order (always sent: a cancel takes risk off). (done, why)."""
        try:
            status, payload = self._call("DELETE", f"/v2/orders/{urllib.parse.quote(str(venue_id), safe='')}", force=True)
        except TransportError as exc:
            return False, f"no answer: {str(exc)[:160]}"
        if status in (200, 204):
            return True, ""
        message = str((payload.get("message") if isinstance(payload, dict) else payload) or "")[:200]
        # 422: the order is already filled or cancelled; the next read of the orders says which.
        return False, f"HTTP {status} {message}"


class Submitted:
    __slots__ = ("ok", "order", "error", "unknown", "sent", "status")

    def __init__(self, ok: bool, order: dict | None, error: str, *, unknown: bool = False, sent: bool = True, status: int = 0):
        self.ok, self.order, self.error, self.unknown, self.sent, self.status = ok, order, error, unknown, sent, status


class MarketData:
    """Live option chains and underlying prices (market-data GETs through the real account's credential)."""

    def __init__(self, client: Any, *, option_feed: str = "opra", stock_feed: str = "sip", clock: Callable[[], float] = time.time):
        self.client, self.option_feed, self.stock_feed, self.clock = client, option_feed, stock_feed, clock
        self.calls = 0
        self.minute_calls = Rate(100000)

    def _get(self, path: str, params: Mapping[str, Any], what: str) -> Any:
        query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        self.calls += 1
        self.minute_calls.take(force=True)
        status, payload = self.client.request("GET", f"{DATA_BASE}{path}?{query}", what=what)
        if not 200 <= status < 300:
            message = payload.get("message") if isinstance(payload, dict) else payload
            raise VenueError(f"market data {what}: HTTP {status} {str(message or '')[:200]}")
        return payload

    def chain(self, underlying: str, *, expiry_from: str, expiry_to: str, strike_from: float | None = None,
              strike_to: float | None = None) -> dict[str, dict[str, Any]]:
        """Every contract of `underlying` in the window: {OCC: snapshot row}, all pages."""
        out: dict[str, dict[str, Any]] = {}
        token = None
        for _ in range(MAX_PAGES):
            page = self._get(f"/v1beta1/options/snapshots/{urllib.parse.quote(underlying.upper(), safe='')}", {
                "feed": self.option_feed, "limit": 1000, "expiration_date_gte": expiry_from, "expiration_date_lte": expiry_to,
                "strike_price_gte": None if strike_from is None else f"{strike_from:.3f}",
                "strike_price_lte": None if strike_to is None else f"{strike_to:.3f}", "page_token": token}, f"chain {underlying}")
            if not isinstance(page, dict) or not isinstance(page.get("snapshots") or {}, dict):
                raise VenueError(f"chain {underlying}: no snapshots map")
            out.update(page.get("snapshots") or {})
            token = page.get("next_page_token")
            if not token:
                return out
        raise VenueError(f"chain {underlying}: more than {MAX_PAGES} pages")

    def contracts(self, symbols: Iterable[str]) -> dict[str, dict[str, Any]]:
        """Snapshots of named contracts (100 a request)."""
        names = sorted({str(s).upper() for s in symbols if s})
        out: dict[str, dict[str, Any]] = {}
        for i in range(0, len(names), 100):
            page = self._get("/v1beta1/options/snapshots", {"symbols": ",".join(names[i:i + 100]), "feed": self.option_feed},
                             "contracts")
            out.update((page or {}).get("snapshots") or {})
        return out

    def stocks(self, symbols: Iterable[str]) -> dict[str, dict[str, Any]]:
        names = sorted({str(s).upper() for s in symbols if s})
        if not names:
            return {}
        page = self._get("/v2/stocks/snapshots", {"symbols": ",".join(names), "feed": self.stock_feed}, "stock snapshots")
        if not isinstance(page, dict):
            raise VenueError("stock snapshots: not a map")
        return page

    def bars(self, symbols: Iterable[str], *, timeframe: str, start: str, end: str | None = None) -> dict[str, list[dict]]:
        names = sorted({str(s).upper() for s in symbols if s})
        out: dict[str, list[dict]] = {name: [] for name in names}
        token = None
        for _ in range(MAX_PAGES):
            page = self._get("/v2/stocks/bars", {"symbols": ",".join(names), "timeframe": timeframe, "start": start,
                                                 "end": end, "limit": 10000, "feed": self.stock_feed, "adjustment": "raw",
                                                 "page_token": token}, f"bars {timeframe}")
            for name, rows in ((page or {}).get("bars") or {}).items():
                out.setdefault(name, []).extend(rows or [])
            token = (page or {}).get("next_page_token")
            if not token:
                return out
        raise VenueError(f"bars: more than {MAX_PAGES} pages")


def quote_of(row: Mapping[str, Any]) -> tuple[float, float, int, int, float | None]:
    """(bid, ask, bid size, ask size, quote time) of one option snapshot row; NaN prices when absent."""
    q = row.get("latestQuote") if isinstance(row, Mapping) else None
    if not isinstance(q, Mapping):
        return float("nan"), float("nan"), 0, 0, None
    def size(v: Any) -> int:
        try:
            return max(0, int(v))
        except (TypeError, ValueError):
            return 0
    return num(q.get("bp")), num(q.get("ap")), size(q.get("bs")), size(q.get("as")), parse_time(q.get("t"))


def stock_price(row: Mapping[str, Any], *, not_before: float | None = None) -> float:
    """The underlying's price now: the latest trade when it is from this session (at or after `not_before`), else the
    quote's mid; NaN when neither is usable."""
    trade = row.get("latestTrade") if isinstance(row, Mapping) else None
    if isinstance(trade, Mapping):
        t = parse_time(trade.get("t"))
        p = num(trade.get("p"))
        if p > 0 and (not_before is None or (t is not None and t >= not_before)):
            return p
    quote = row.get("latestQuote") if isinstance(row, Mapping) else None
    if isinstance(quote, Mapping):
        t = parse_time(quote.get("t"))
        bid, ask = num(quote.get("bp")), num(quote.get("ap"))
        if bid > 0 and ask >= bid and (not_before is None or (t is not None and t >= not_before)):
            return 0.5 * (bid + ask)
    return float("nan")


__all__ = ["Account", "MarketData", "Submitted", "VenueError", "RateLimited", "Rate", "occ_parts", "occ_symbol", "quote_of",
           "stock_price", "parse_time", "TERMINAL", "WORKING", "OPTION_EVENTS", "LIVE_BASE", "PAPER_BASE", "DATA_BASE"]
