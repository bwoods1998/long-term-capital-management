"""Coinbase Advanced Trade over WebSocket: prices on the public feed, order state on the user feed.

Verified against the WebSocket overview and endpoints pages
(`docs/proposals/2026-09-15-push-the-limits.md`, T6):

* Market data: `wss://advanced-trade-ws.coinbase.com`, no auth. Order data:
  `wss://advanced-trade-ws-user.coinbase.com`, one connection per user, `user` channel with a
  JWT in every subscribe message. The gateway mints that JWT (`GET /v1/coinbase/ws-jwt`);
  it carries no `uri` claim and lives two minutes, so it is fetched per subscribe message.
* "To receive feed messages, you must send a `subscribe` message or you are disconnected in
  5 seconds." The first thing sent on either socket is a subscribe.
* Subscribe `heartbeats` too: "Most channels close within 60-90 seconds when no updates
  arrive."
* Every message carries `channel`, `timestamp`, `sequence_num` and `events[]`;
  `sequence_num` is per connection, and a gap means resubscribe with a fresh snapshot, so a
  gap here reconnects.
* The `user` channel is not a fill feed: it sends order snapshots and updates with
  `cumulative_quantity`, `status`, `order_id`, `product_id`. A rise in `cumulative_quantity`
  between two updates is a fill *candidate*; the REST fills endpoint is the record. Open
  orders arrive in the snapshot batched by 50; the first batch under 50 ends the snapshot.
* "WebSocket connections and unauthenticated messages are each limited to 8 per second per
  IP": reconnects back off.

UNVERIFIED: the exact `ticker` event field names are taken from the channel reference as
`product_id`, `price`, `best_bid`, `best_ask`; anything missing is simply not recorded.
"""

from __future__ import annotations

import json
import threading
from typing import Any, Mapping

from . import Feed, FeedHub, GatewayCredentials
from .depth import DepthBook

MARKET_URL = "wss://advanced-trade-ws.coinbase.com"
USER_URL = "wss://advanced-trade-ws-user.coinbase.com"
SNAPSHOT_BATCH = 50


class _CoinbaseFeed(Feed):
    venue = "coinbase"

    def __init__(self, hub: FeedHub, *, url: str, **kw: Any):
        super().__init__(hub, **kw)
        self.url = url
        self.last_sequence: int | None = None
        self.gaps = 0

    def _check_sequence(self, envelope: Mapping[str, Any]) -> None:
        sequence = envelope.get("sequence_num")
        if not isinstance(sequence, int):
            return
        if self.last_sequence is not None and sequence != self.last_sequence + 1:
            self.gaps += 1
            raise ConnectionError(f"coinbase sequence gap: {self.last_sequence} -> {sequence}")
        self.last_sequence = sequence

    def _read(self, sock: Any, stop: threading.Event) -> None:
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
            if not isinstance(envelope, dict):
                continue
            channel = str(envelope.get("channel") or "")
            if channel in ("subscriptions", "heartbeats"):
                self._check_sequence(envelope)
                continue
            self._check_sequence(envelope)
            self.handle(sock, channel, envelope)
            self.maybe_resubscribe(sock)
        raise ConnectionError("coinbase socket closed or went idle")

    def handle(self, sock: Any, channel: str, envelope: Mapping[str, Any]) -> None:  # pragma: no cover
        raise NotImplementedError

    def maybe_resubscribe(self, sock: Any) -> None:
        return


class CoinbaseMarketFeed(_CoinbaseFeed):
    """Public `ticker` for every product a desk may hold or trade."""

    name = "coinbase-market"

    def __init__(self, hub: FeedHub, *, url: str = MARKET_URL, **kw: Any):
        super().__init__(hub, url=url, **kw)
        self.products: set[str] = set()
        self.books: dict[str, DepthBook] = {}
        self.depth_published: dict[str, float] = {}

    def wanted(self) -> set[str]:
        return {p.upper() for p in self.hub.held_symbols(self.venue) | self.hub.allowed_symbols(self.venue)}

    def run_once(self, stop: threading.Event) -> None:
        # CDE futures ids are not subscribed here (their support on the market channels is
        # unverified and one refused id could cost the spot feed); their quotes come by REST.
        products = sorted(p for p in self.wanted() if not p.endswith("-CDE"))
        if not products:
            # Nothing to watch: check again shortly rather than hold an idle socket.
            self.sleep(15.0)
            return
        # A full BTC depth snapshot exceeds the ticker transport's 4 MiB default. This
        # connection alone gets a bounded 16 MiB frame budget; books also cap price levels.
        sock = self.connect(self.url, timeout=15.0, max_message_bytes=16 * 1024 * 1024)
        self.opened(sock)
        self.last_sequence = None
        self.products = set(products)
        self.books.clear()
        self.depth_published.clear()
        try:
            sock.send(json.dumps({"type": "subscribe", "product_ids": products, "channel": "heartbeats"}))
            sock.send(json.dumps({"type": "subscribe", "product_ids": products, "channel": "ticker"}))
            sock.send(json.dumps({"type": "subscribe", "product_ids": products, "channel": "market_trades"}))
            sock.send(json.dumps({"type": "subscribe", "product_ids": products, "channel": "level2"}))
            self._read(sock, stop)
        finally:
            self.hub.invalidate_depth(self.venue)
            sock.close()

    def maybe_resubscribe(self, sock: Any) -> None:
        # "To add products, unsubscribe and open a new connection with the expanded list."
        if self.wanted() != self.products:
            raise ConnectionError("coinbase product list changed; reconnecting")

    def handle(self, sock: Any, channel: str, envelope: Mapping[str, Any]) -> None:
        if channel == "l2_data":
            for event in envelope.get("events") or []:
                product = str(event.get("product_id") or "").upper()
                if product not in self.products:
                    continue
                book = self.books.setdefault(product, DepthBook())
                try:
                    book.apply(event)
                except ValueError as exc:
                    raise ConnectionError(str(exc)) from exc
                now = float(self.clock())
                if now - self.depth_published.get(product, -1e30) >= 1:
                    summary = book.summary()
                    if summary:
                        self.hub.on_depth(self.venue, product, summary)
                        self.depth_published[product] = now
            return
        if channel == "market_trades":
            # Public prints. Coinbase's `side` is the MAKER's side ("each market trade belongs
            # to a side, which refers to the maker's side"), so a BUY print is a taker selling
            # into a resting bid. The hub wants the taker's side.
            for event in envelope.get("events") or []:
                if not isinstance(event, dict):
                    continue
                for row in event.get("trades") or []:
                    if not isinstance(row, dict):
                        continue
                    product = str(row.get("product_id") or "").upper()
                    maker = str(row.get("side") or "").upper()
                    taker = "sell" if maker == "BUY" else "buy" if maker == "SELL" else ""
                    if product and taker:
                        self.hub.on_trade(self.venue, product, price=row.get("price"), size=row.get("size"), taker_side=taker)
            return
        if channel != "ticker":
            return
        for event in envelope.get("events") or []:
            if not isinstance(event, dict):
                continue
            for row in event.get("tickers") or []:
                if not isinstance(row, dict):
                    continue
                product = str(row.get("product_id") or "").upper()
                if not product:
                    continue
                self.hub.on_price(
                    self.venue,
                    product,
                    bid=row.get("best_bid"),
                    ask=row.get("best_ask"),
                    last=row.get("price"),
                    source="coinbase:ws",
                )


class CoinbaseUserFeed(_CoinbaseFeed):
    """The `user` channel: order state in milliseconds, turned into fill candidates."""

    name = "coinbase-user"

    def __init__(self, hub: FeedHub, credentials: GatewayCredentials, *, url: str = USER_URL, **kw: Any):
        super().__init__(hub, url=url, **kw)
        self.credentials = credentials
        self.orders: dict[str, dict[str, Any]] = {}
        self.snapshot_complete = False

    def run_once(self, stop: threading.Event) -> None:
        sock = self.connect(self.url, timeout=15.0)
        self.opened(sock)
        self.last_sequence = None
        self.orders = {}
        self.snapshot_complete = False
        try:
            # A fresh JWT per subscribe message: they expire in two minutes and are never reused.
            sock.send(json.dumps({"type": "subscribe", "channel": "heartbeats", "jwt": self.credentials.coinbase_jwt()}))
            sock.send(json.dumps({"type": "subscribe", "channel": "user", "jwt": self.credentials.coinbase_jwt()}))
            self._read(sock, stop)
        finally:
            sock.close()

    def handle(self, sock: Any, channel: str, envelope: Mapping[str, Any]) -> None:
        if channel != "user":
            return
        for event in envelope.get("events") or []:
            if not isinstance(event, dict):
                continue
            rows = [row for row in (event.get("orders") or []) if isinstance(row, dict)]
            kind = str(event.get("type") or "")
            if kind == "snapshot":
                for row in rows:
                    order_id = str(row.get("order_id") or "")
                    if order_id:
                        self.orders[order_id] = dict(row)
                if len(rows) < SNAPSHOT_BATCH:
                    self.snapshot_complete = True
                continue
            for row in rows:
                order_id = str(row.get("order_id") or "")
                if not order_id:
                    continue
                previous = self.orders.get(order_id)
                if _filled_more(previous, row):
                    self.hub.on_fill_candidate(self.venue, row)
                self.orders[order_id] = dict(row)


def _quantity(row: Mapping[str, Any] | None) -> float:
    if not row:
        return 0.0
    try:
        return float(row.get("cumulative_quantity") or 0)
    except (TypeError, ValueError):
        return 0.0


def _filled_more(previous: Mapping[str, Any] | None, current: Mapping[str, Any]) -> bool:
    """True when this update shows more filled quantity than the last one, or a first fill."""
    now = _quantity(current)
    if now <= 0:
        return False
    return now > _quantity(previous)


__all__ = ["CoinbaseMarketFeed", "CoinbaseUserFeed", "MARKET_URL", "SNAPSHOT_BATCH", "USER_URL"]
