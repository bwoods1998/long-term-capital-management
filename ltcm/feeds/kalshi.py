"""Kalshi over WebSocket: fills, market lifecycle and tickers for the markets the floor holds.

Verified against https://docs.kalshi.com/websockets and the quick start
(`docs/proposals/2026-09-15-push-the-limits.md`, T7):

* Authentication is in the HTTP upgrade: the three `KALSHI-ACCESS-*` headers over
  `timestamp + "GET" + "/trade-api/ws/v2"`. The gateway signs them; this process never holds
  the key (`GatewayCredentials.kalshi_headers`).
* Kalshi sends ping frames with body `heartbeat` every ten seconds; the client answers with
  pong frames. Thirty seconds of silence therefore means the socket is dead, not quiet.
* Subscribe: `{"id": 1, "cmd": "subscribe", "params": {"channels": ["fill"]}}`; the answer is
  `{"id": 1, "type": "subscribed", "msg": {"channel": "fill", "sid": 1}}`.
* `fill` messages carry `market_ticker`, `order_id`, `trade_id`, `yes_price_dollars`,
  `count_fp`, `outcome_side`, `book_side`, `ts_ms`, and no `seq`, so gaps are undetectable:
  the REST fills sweep stays the record and the socket only makes it run sooner.
* `market_lifecycle_v2` is a firehose (no ticker filter); `result` exists only when
  `event_type` is `determined`; `settled` follows the settlement timer. The floor scores at
  `settled` through the REST settlements endpoint; `determined` only prompts the sweep early.
* Channel errors 10 and 25 are terminal for that subscription: resubscribe.

UNVERIFIED (parsed defensively, never relied on): the exact field names of `ticker` messages
(`yes_bid_dollars` / `yes_ask_dollars` / `last_price_dollars`, or cents as `yes_bid` /
`yes_ask` / `last_price` / `price`), and the `unsubscribe` command shape
`{"cmd": "unsubscribe", "params": {"sids": [...]}}`. A refused unsubscribe simply reconnects.
"""

from __future__ import annotations

import json
import threading
from decimal import Decimal
from typing import Any, Mapping

from . import Feed, FeedHub, GatewayCredentials

WS_URL = "wss://api.elections.kalshi.com/trade-api/ws/v2"
TERMINAL_CHANNEL_ERRORS = (10, 25)
CHANNELS = ("fill", "market_lifecycle_v2")


def dollars(row: Mapping[str, Any], name: str) -> Decimal | None:
    """A price from `<name>_dollars` (decimal string) or `<name>` (integer cents)."""
    value = row.get(f"{name}_dollars")
    if value not in (None, ""):
        try:
            number = Decimal(str(value))
            return number if number.is_finite() and number > 0 else None
        except Exception:
            return None
    cents = row.get(name)
    if isinstance(cents, bool) or not isinstance(cents, (int, float, str)) or cents in ("", None):
        return None
    try:
        number = Decimal(str(cents)) / Decimal(100)
    except Exception:
        return None
    return number if number.is_finite() and number > 0 else None


class KalshiFeed(Feed):
    venue = "kalshi"
    name = "kalshi"

    def __init__(self, hub: FeedHub, credentials: GatewayCredentials, *, url: str = WS_URL, **kw: Any):
        super().__init__(hub, **kw)
        self.credentials = credentials
        self.url = url
        self.sids: dict[str, int] = {}
        self._next_id = 1
        self._subscribed_tickers: set[str] = set()
        self.resubscribes = 0

    # ------------------------------------------------------------- commands
    def _command(self, sock: Any, cmd: str, params: Mapping[str, Any]) -> int:
        request_id = self._next_id
        self._next_id += 1
        sock.send(json.dumps({"id": request_id, "cmd": cmd, "params": dict(params)}))
        return request_id

    def _subscribe_ticker(self, sock: Any, tickers: set[str]) -> None:
        # The ticker and the public trade prints ride one subscription per set of markets: the
        # prints are what the shadow books fill their resting quotes against (leap: taker model).
        previous = [sid for sid in (self.sids.pop("ticker", None), self.sids.pop("trade", None)) if sid is not None]
        if previous:
            try:
                self._command(sock, "unsubscribe", {"sids": previous})
            except Exception:
                raise  # a broken socket reconnects; the next connection subscribes afresh
        if tickers:
            self._command(sock, "subscribe", {"channels": ["ticker", "trade"], "market_tickers": sorted(tickers)})
        self._subscribed_tickers = set(tickers)

    # ------------------------------------------------------------- the loop
    def run_once(self, stop: threading.Event) -> None:
        headers = self.credentials.kalshi_headers()
        sock = self.connect(self.url, headers, timeout=15.0)
        self.opened(sock)
        self.sids = {}
        try:
            for channel in CHANNELS:
                self._command(sock, "subscribe", {"channels": [channel]})
            self._subscribe_ticker(sock, self.hub.held_symbols(self.venue))
            for message in sock.messages(idle_timeout=self.idle_timeout):
                if stop.is_set():
                    return
                self.saw()
                text = message.text
                if text is None:
                    continue
                try:
                    envelope = json.loads(text)
                except ValueError:
                    continue
                if isinstance(envelope, dict):
                    self.handle(sock, envelope)
                wanted = self.hub.held_symbols(self.venue)
                if wanted != self._subscribed_tickers:
                    self._subscribe_ticker(sock, wanted)
            raise ConnectionError("kalshi socket closed or went idle")
        finally:
            sock.close()

    def handle(self, sock: Any, envelope: Mapping[str, Any]) -> None:
        kind = envelope.get("type")
        msg = envelope.get("msg") if isinstance(envelope.get("msg"), dict) else {}
        if kind == "subscribed":
            channel = str(msg.get("channel") or "")
            if channel and isinstance(msg.get("sid"), int):
                self.sids[channel] = int(msg["sid"])
            return
        if kind == "error":
            code = msg.get("code")
            if code in TERMINAL_CHANNEL_ERRORS:
                # The subscription is gone; ask for everything again on the same socket.
                self.resubscribes += 1
                self.sids = {}
                for channel in CHANNELS:
                    self._command(sock, "subscribe", {"channels": [channel]})
                self._subscribed_tickers = set()
                self._subscribe_ticker(sock, self.hub.held_symbols(self.venue))
            return
        if kind == "fill":
            self.hub.on_fill_candidate(self.venue, msg)
            return
        if kind == "market_lifecycle_v2":
            ticker = str(msg.get("market_ticker") or "").upper()
            event_type = str(msg.get("event_type") or "")
            if event_type not in ("determined", "settled") or not ticker:
                return
            if ticker not in self.hub.held_symbols(self.venue):
                return  # the firehose carries every market on the exchange
            self.hub.on_resolution(
                self.venue,
                {
                    "ticker": ticker,
                    "event_type": event_type,
                    "result": msg.get("result"),
                    "settlement_value": msg.get("settlement_value"),
                    # `determined` can still be disputed or amended; only `settled` is final.
                    "provisional": event_type != "settled",
                },
            )
            return
        if kind == "trade":
            ticker = str(msg.get("market_ticker") or msg.get("ticker") or "").upper()
            price = dollars(msg, "yes_price")
            count = msg.get("count_fp") if msg.get("count_fp") is not None else msg.get("count")
            if ticker and price is not None and count is not None:
                self.hub.on_trade(self.venue, ticker, price=price, size=count, taker_side=str(msg.get("taker_side") or ""))
            return
        if kind == "ticker":
            ticker = str(msg.get("market_ticker") or msg.get("ticker") or "").upper()
            if not ticker:
                return
            self.hub.on_price(
                self.venue,
                ticker,
                bid=dollars(msg, "yes_bid"),
                ask=dollars(msg, "yes_ask"),
                last=dollars(msg, "last_price") or dollars(msg, "price"),
                source="kalshi:ws",
            )


__all__ = ["CHANNELS", "KalshiFeed", "TERMINAL_CHANNEL_ERRORS", "WS_URL", "dollars"]
