"""Live venue feeds: the floor's ears.

Both venues deliver fills, resolutions and prices over WebSockets at a latency no poll can
match. This package keeps those sockets open on their own threads and turns what they say into
three things the tick can use without ever trusting the socket as a record:

* **Prices.** The newest bid, ask and last per instrument, with the time they were seen. The
  service consults `FeedHub.quote()` before any broker or market-data source, but only while
  the price is fresh (`max_age`); a stale socket price is worse than a REST one.
* **Fill candidates.** A socket says an order filled; the hub notes the venue, and the tick
  runs the existing REST fills sweep for that venue at once. The REST record is the only
  thing that reaches the hash-chained ledger. The socket only makes it happen sooner.
* **Resolutions.** A Kalshi market the floor holds was determined or settled; the tick's
  settlement sweep runs on the same tick instead of waiting for its turn.

Each feed reconnects forever with backoff and never raises into the tick. When a feed has been
down for a while the hub says so once an hour at most, as an `ops.alert`, through the callback
the service hands it. Credential material comes from the order gateway and is short-lived:
this process never holds a venue key (contract v2, section 5).
"""

from __future__ import annotations

import json
import threading
import time
from decimal import Decimal
from typing import Any, Callable, Mapping

from ..broker import Instrument, Quote
from ..data import HttpTransport, TransportError
from ..events import now_iso

#: A socket price older than this is not used as a quote at all.
DEFAULT_MAX_AGE_SECONDS = 60.0
#: A feed down for longer than this is worth a line in public, at most once per `ALERT_EVERY`.
DISCONNECT_ALERT_AFTER_SECONDS = 300.0
ALERT_EVERY_SECONDS = 3600.0


class FeedError(RuntimeError):
    """A feed could not do what it was asked. Feeds recover by reconnecting; nothing else does."""


def _dec(value: Any) -> Decimal | None:
    """A decimal from a venue field, or None for anything that is not a positive number."""
    if value is None or value == "":
        return None
    try:
        number = Decimal(str(value))
    except Exception:
        return None
    if not number.is_finite() or number <= 0:
        return None
    return number


class GatewayCredentials:
    """Short-lived WebSocket credential material, fetched from the order gateway.

    `GET /v1/kalshi/ws-auth` returns the three handshake headers Kalshi wants, signed by the
    gateway over `timestamp + "GET" + "/trade-api/ws/v2"`, good for thirty seconds.
    `GET /v1/coinbase/ws-jwt` returns a two-minute JWT for the Coinbase user channel. The
    bearer token is the only credential this process holds, exactly as in `GatewaySigner`.
    """

    def __init__(self, gateway_url: str, token: str, *, transport: Any = None, timeout: float = 10.0):
        if not isinstance(gateway_url, str) or not gateway_url.startswith("https://"):
            raise ValueError("gateway_url must be an https URL")
        if not isinstance(token, str) or len(token.strip()) < 32:
            raise ValueError("gateway token must be at least 32 characters")
        self.gateway_url = gateway_url.rstrip("/")
        self._token = token.strip()
        self.transport = transport or HttpTransport()
        self.timeout = float(timeout)

    def __repr__(self) -> str:  # never print the token
        return f"GatewayCredentials({self.gateway_url})"

    def _get(self, path: str) -> dict[str, Any]:
        url = self.gateway_url + path
        headers = {"Accept": "application/json", "Authorization": "Bearer " + self._token}
        try:
            status, _, raw = self.transport.request("GET", url, headers=headers, timeout=self.timeout)
        except TransportError as exc:
            raise FeedError(f"gateway {path} unreachable: {exc}") from exc
        if status != 200:
            raise FeedError(f"gateway {path} answered {status}")
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise FeedError(f"gateway {path} answered non-JSON") from exc
        if not isinstance(payload, dict):
            raise FeedError(f"gateway {path} answered the wrong shape")
        return payload

    def kalshi_headers(self) -> dict[str, str]:
        payload = self._get("/v1/kalshi/ws-auth")
        headers = payload.get("headers")
        if not isinstance(headers, dict) or not all(
            isinstance(headers.get(name), str) and headers.get(name)
            for name in ("KALSHI-ACCESS-KEY", "KALSHI-ACCESS-TIMESTAMP", "KALSHI-ACCESS-SIGNATURE")
        ):
            raise FeedError("gateway ws-auth carried no handshake headers")
        return {name: str(value) for name, value in headers.items()}

    def coinbase_jwt(self) -> str:
        payload = self._get("/v1/coinbase/ws-jwt")
        token = payload.get("jwt")
        if not isinstance(token, str) or token.count(".") != 2:
            raise FeedError("gateway ws-jwt carried no token")
        return token


class Feed:
    """One venue socket, kept open forever on its own thread. Subclasses implement `run_once`."""

    venue = ""
    name = ""

    def __init__(
        self,
        hub: "FeedHub",
        *,
        connect: Callable[..., Any] = None,
        clock: Callable[[], float] = time.time,
        sleep: Callable[[float], None] = time.sleep,
        idle_timeout: float = 30.0,
    ):
        from ..data import ws as ws_module

        self.hub = hub
        self.connect = connect or ws_module.connect
        self.clock = clock
        self.sleep = sleep
        self.idle_timeout = float(idle_timeout)
        self.attempts = 0
        self.connected_at: float | None = None
        self.last_message_at: float | None = None
        self.last_error: str | None = None
        self.messages = 0

    def run_once(self, stop: threading.Event) -> None:  # pragma: no cover - abstract
        raise NotImplementedError

    def run_forever(self, stop: threading.Event) -> None:
        """Reconnect until told to stop. Every failure is a delay, never an exception."""
        from ..data import ws as ws_module

        while not stop.is_set():
            try:
                self.run_once(stop)
                self.attempts = 0
            except Exception as exc:  # any socket, protocol or venue failure
                self.last_error = f"{type(exc).__name__}: {str(exc)[:160]}"
                self.hub.on_status(self, connected=False, detail=self.last_error)
                self.attempts += 1
            if stop.is_set():
                break
            self.sleep(ws_module.backoff_seconds(self.attempts))

    # ---------------------------------------------------------------- helpers
    def opened(self, sock: Any) -> None:
        self.connected_at = float(self.clock())
        self.last_error = None
        self.hub.on_status(self, connected=True, detail=None)

    def saw(self) -> None:
        self.last_message_at = float(self.clock())
        self.messages += 1


class FeedHub:
    """The one object the service talks to. Thread-safe; feeds push, the tick pulls."""

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.time,
        alert: Callable[[str, str], None] | None = None,
        held: Callable[[], Mapping[str, set[str]]] | None = None,
        allowed: Callable[[], Mapping[str, set[str]]] | None = None,
        max_age: float = DEFAULT_MAX_AGE_SECONDS,
        disconnect_alert_after: float = DISCONNECT_ALERT_AFTER_SECONDS,
        alert_every: float = ALERT_EVERY_SECONDS,
    ):
        self.clock = clock
        self.alert = alert
        self._held = held or (lambda: {})
        self._allowed = allowed or (lambda: {})
        self.max_age = float(max_age)
        self.disconnect_alert_after = float(disconnect_alert_after)
        self.alert_every = float(alert_every)
        self.feeds: list[Feed] = []
        self._threads: list[threading.Thread] = []
        self._stop = threading.Event()
        self._lock = threading.RLock()
        self._prices: dict[tuple[str, str], dict[str, Any]] = {}
        self._fill_venues: set[str] = set()
        self._resolutions: list[dict[str, Any]] = []
        self._trades: list[dict[str, Any]] = []  # leap: taker model -- prints the shadow books fill against
        self._prints_seen: dict[str, int] = {}  # per venue, since start: says whether the trade channels deliver
        self._status: dict[str, dict[str, Any]] = {}
        self._down_since: dict[str, float] = {}
        self._last_alert_at: dict[str, float] = {}
        self.started = False

    # --------------------------------------------------------------- lifecycle
    def add(self, feed: Feed) -> Feed:
        self.feeds.append(feed)
        self._status[feed.name] = {"venue": feed.venue, "connected": False, "detail": None}
        return feed

    def start(self) -> None:
        if self.started:
            return
        self.started = True
        self._stop.clear()
        for feed in self.feeds:
            thread = threading.Thread(target=feed.run_forever, args=(self._stop,), name=f"feed-{feed.name}", daemon=True)
            self._threads.append(thread)
            thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        self._stop.set()
        for thread in self._threads:
            thread.join(timeout=timeout)
        self._threads = []
        self.started = False

    # ------------------------------------------------------------ what is wanted
    def held_symbols(self, venue: str) -> set[str]:
        try:
            return {str(s) for s in (self._held() or {}).get(venue, ())}
        except Exception:
            return set()

    def allowed_symbols(self, venue: str) -> set[str]:
        try:
            return {str(s) for s in (self._allowed() or {}).get(venue, ())}
        except Exception:
            return set()

    # -------------------------------------------------------------- from feeds
    def on_price(
        self,
        venue: str,
        symbol: str,
        *,
        bid: Any = None,
        ask: Any = None,
        last: Any = None,
        source: str = "ws",
        at: float | None = None,
    ) -> None:
        bid_d, ask_d, last_d = _dec(bid), _dec(ask), _dec(last)
        if bid_d is None and ask_d is None and last_d is None:
            return
        key = (venue, str(symbol).upper())
        with self._lock:
            previous = self._prices.get(key) or {}
            self._prices[key] = {
                "bid": bid_d if bid_d is not None else previous.get("bid"),
                "ask": ask_d if ask_d is not None else previous.get("ask"),
                "last": last_d if last_d is not None else previous.get("last"),
                "at": float(at if at is not None else self.clock()),
                "source": source,
            }

    def on_trade(self, venue: str, symbol: str, *, price: Any, size: Any, taker_side: str, at: float | None = None) -> None:
        """A trade the venue printed. The shadow books fill a resting quote against it the way
        a real queue would: a taker who sold at or through our bid hit us. Bounded; the tick
        drains it (`drain_trades`)."""
        price_d, size_d = _dec(price), _dec(size)
        if price_d is None or size_d is None or price_d <= 0 or size_d <= 0:
            return
        row = {"venue": venue, "symbol": str(symbol).upper(), "price": price_d, "size": size_d,
               "taker_side": str(taker_side or "").lower(), "at": float(at if at is not None else self.clock())}
        with self._lock:
            self._prints_seen[venue] = self._prints_seen.get(venue, 0) + 1
            self._trades.append(row)
            if len(self._trades) > 5000:
                del self._trades[: len(self._trades) - 5000]

    def drain_trades(self) -> list[dict[str, Any]]:
        with self._lock:
            trades, self._trades = self._trades, []
        return trades

    def on_fill_candidate(self, venue: str, payload: Mapping[str, Any]) -> None:
        with self._lock:
            self._fill_venues.add(venue)

    def on_resolution(self, venue: str, payload: Mapping[str, Any]) -> None:
        with self._lock:
            self._resolutions.append({"venue": venue, **dict(payload)})

    def on_status(self, feed: Feed, *, connected: bool, detail: str | None) -> None:
        now = float(self.clock())
        with self._lock:
            row = self._status.setdefault(feed.name, {"venue": feed.venue})
            row.update({"connected": connected, "detail": detail, "at": now_iso(self.clock)})
            if connected:
                self._down_since.pop(feed.name, None)
            else:
                self._down_since.setdefault(feed.name, now)

    # ------------------------------------------------------------- for the tick
    def quote(self, instrument: Instrument) -> Quote | None:
        """A fresh socket quote for this instrument, or None. Never raises."""
        symbol = str(instrument.market_id or instrument.symbol or "").upper()
        with self._lock:
            row = self._prices.get((instrument.venue, symbol))
        if row is None:
            return None
        age = float(self.clock()) - float(row["at"])
        if age < 0 or age > self.max_age:
            return None
        bid, ask, last = row.get("bid"), row.get("ask"), row.get("last")
        if instrument.asset_class == "event" and str(instrument.right or "").lower() == "no":
            # The socket carries the YES leg. A NO instrument is priced in NO dollars, exactly
            # as the REST quote does it: on Sept 16, 2026 the unconverted feed let the risk
            # engine judge a NO bid against the YES ask and the exit engine stop a NO position
            # out at the YES mark thirteen seconds after it filled.
            one = Decimal(1)
            bid, ask, last = (
                None if ask is None else one - ask,
                None if bid is None else one - bid,
                None if last is None else one - last,
            )
        return Quote(
            instrument,
            bid,
            ask,
            last,
            now_iso(lambda: row["at"]),
            row.get("source") or "ws",
            False,
        )

    def drain(self) -> dict[str, Any]:
        """What the sockets saw since the last drain: venues with fills to confirm, resolutions."""
        with self._lock:
            venues = sorted(self._fill_venues)
            resolutions = list(self._resolutions)
            self._fill_venues.clear()
            self._resolutions.clear()
        return {"fill_venues": venues, "resolutions": resolutions}

    def check_health(self) -> list[str]:
        """Say once an hour, per feed, when a feed has been down for a while. Returns what was said."""
        now = float(self.clock())
        said: list[str] = []
        with self._lock:
            items = list(self._down_since.items())
            statuses = dict(self._status)
        for name, since in items:
            if now - since < self.disconnect_alert_after:
                continue
            last = self._last_alert_at.get(name)
            if last is not None and now - last < self.alert_every:
                continue
            self._last_alert_at[name] = now
            detail = (statuses.get(name) or {}).get("detail") or "no detail"
            text = f"feed {name} has been down for {int((now - since) // 60)} minutes: {detail}"
            said.append(text)
            if self.alert is not None:
                try:
                    self.alert("warning", text)
                except Exception:
                    pass
        return said

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "feeds": {name: dict(row) for name, row in self._status.items()},
                "prices": len(self._prices),
                "pending_fill_venues": sorted(self._fill_venues),
                "pending_resolutions": len(self._resolutions),
                "prints_seen": dict(self._prints_seen),
            }


__all__ = [
    "ALERT_EVERY_SECONDS",
    "DEFAULT_MAX_AGE_SECONDS",
    "DISCONNECT_ALERT_AFTER_SECONDS",
    "Feed",
    "FeedError",
    "FeedHub",
    "GatewayCredentials",
]
