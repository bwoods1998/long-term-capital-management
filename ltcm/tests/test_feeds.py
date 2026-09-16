"""The feeds: what the sockets say, what the hub keeps, and what the tick is handed."""

from __future__ import annotations

import json
import threading
import unittest
from decimal import Decimal

from ltcm.broker import Instrument
from ltcm.data import ws
from ltcm.feeds import FeedError, FeedHub, GatewayCredentials
from ltcm.feeds.coinbase import CoinbaseMarketFeed, CoinbaseUserFeed
from ltcm.feeds.kalshi import KalshiFeed, dollars
from ltcm.tests.fakes import Clock, FakeTransport

GATEWAY = "https://ltcm-gateway.example.workers.dev"
TOKEN = "gateway-token-that-is-long-enough-1234567890"
KALSHI_HEADERS = {"KALSHI-ACCESS-KEY": "k1", "KALSHI-ACCESS-TIMESTAMP": "1", "KALSHI-ACCESS-SIGNATURE": "sig"}


class FakeSocket:
    """A connected socket that plays a script of server messages, then closes."""

    def __init__(self, script, *, idle_after: bool = False):
        self.script = [json.dumps(m) if isinstance(m, dict) else m for m in script]
        self.sent: list[dict] = []
        self.closed = False
        self.idle_after = idle_after

    def send(self, text: str) -> None:
        self.sent.append(json.loads(text))

    def messages(self, *, idle_timeout=None, deadline=None):
        for text in self.script:
            yield ws.Message(ws.OP_TEXT, text.encode())
        if self.idle_after:
            raise TimeoutError("idle")

    def close(self) -> None:
        self.closed = True


class Connector:
    """Stands in for `ws.connect`: hands out scripted sockets in order and records the calls."""

    def __init__(self, *sockets):
        self.sockets = list(sockets)
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, url, headers=None, *, timeout=None, **kw):
        self.calls.append((url, dict(headers or {})))
        if not self.sockets:
            raise ConnectionError("no more sockets")
        return self.sockets.pop(0)


def credentials(transport=None):
    transport = transport or FakeTransport(
        {
            GATEWAY + "/v1/kalshi/ws-auth": {"headers": KALSHI_HEADERS, "path": "/trade-api/ws/v2", "expires_in": 30},
            GATEWAY + "/v1/coinbase/ws-jwt": {"jwt": "h.p.s", "expires_in": 120},
        }
    )
    return GatewayCredentials(GATEWAY, TOKEN, transport=transport), transport


class HubCase(unittest.TestCase):
    def setUp(self):
        self.clock = Clock("2026-09-15T18:00:00Z")
        self.alerts: list[tuple[str, str]] = []
        self.held = {"kalshi": {"KXFED-26SEP-T3.75"}, "coinbase": {"BTC-USD"}}
        self.allowed = {"coinbase": {"BTC-USD", "ETH-USD"}}
        self.hub = FeedHub(
            clock=self.clock,
            alert=lambda level, text: self.alerts.append((level, text)),
            held=lambda: self.held,
            allowed=lambda: self.allowed,
        )
        self.stop = threading.Event()


class GatewayCredentialsTests(unittest.TestCase):
    def test_the_bearer_token_is_the_only_credential_and_the_answers_are_checked(self):
        creds, transport = credentials()
        self.assertEqual(creds.kalshi_headers(), KALSHI_HEADERS)
        self.assertEqual(creds.coinbase_jwt(), "h.p.s")
        for call in transport.calls:
            self.assertEqual(call["headers"]["Authorization"], "Bearer " + TOKEN)
            self.assertNotIn("KALSHI", json.dumps(call["headers"]))
        self.assertNotIn(TOKEN, repr(creds))

    def test_a_bad_answer_is_a_feed_error_not_a_crash(self):
        creds, _ = credentials(FakeTransport({GATEWAY + "/v1/kalshi/ws-auth": (503, {}, b"down")}))
        with self.assertRaises(FeedError):
            creds.kalshi_headers()
        creds, _ = credentials(FakeTransport({GATEWAY + "/v1/coinbase/ws-jwt": {"jwt": "not-a-jwt"}}))
        with self.assertRaises(FeedError):
            creds.coinbase_jwt()

    def test_a_short_token_or_a_plain_http_gateway_is_refused(self):
        with self.assertRaises(ValueError):
            GatewayCredentials(GATEWAY, "short")
        with self.assertRaises(ValueError):
            GatewayCredentials("http://gateway.example", TOKEN)


class FeedHubTests(HubCase):
    def test_a_fresh_price_is_a_quote_and_a_stale_one_is_nothing(self):
        self.hub.on_price("coinbase", "BTC-USD", bid="76790", ask="76800", last="76795", source="coinbase:ws")
        quote = self.hub.quote(Instrument("crypto", "BTC-USD", "coinbase", market_id="BTC-USD"))
        self.assertEqual((quote.bid, quote.ask, quote.last), (Decimal("76790"), Decimal("76800"), Decimal("76795")))
        self.assertEqual(quote.source, "coinbase:ws")
        self.assertFalse(quote.delayed)
        self.clock.advance(61)
        self.assertIsNone(self.hub.quote(Instrument("crypto", "BTC-USD", "coinbase", market_id="BTC-USD")))

    def test_a_partial_update_keeps_the_sides_it_did_not_bring(self):
        self.hub.on_price("kalshi", "kxfed-26sep-t3.75", bid="0.55", ask="0.57")
        self.hub.on_price("kalshi", "KXFED-26SEP-T3.75", last="0.56")
        quote = self.hub.quote(Instrument("event", "KXFED-26SEP-T3.75", "kalshi", market_id="KXFED-26SEP-T3.75"))
        self.assertEqual((quote.bid, quote.ask, quote.last), (Decimal("0.55"), Decimal("0.57"), Decimal("0.56")))
        self.hub.on_price("kalshi", "KXFED-26SEP-T3.75", bid="garbage")
        self.assertEqual(self.hub.quote(Instrument("event", "X", "kalshi", market_id="KXFED-26SEP-T3.75")).bid, Decimal("0.55"))

    def test_the_no_leg_is_quoted_in_no_dollars(self):
        # The socket carries the YES leg; the REST quote complements it for a NO instrument, and
        # so must this one, or the risk engine judges a NO bid against the YES ask (Sept 16, 2026).
        self.hub.on_price("kalshi", "KXETH-26SEP1617-B2390", bid="0.24", ask="0.28", last="0.26")
        no = self.hub.quote(Instrument("event", "KXETH-26SEP1617-B2390", "kalshi", market_id="KXETH-26SEP1617-B2390", right="no"))
        self.assertEqual((no.bid, no.ask, no.last), (Decimal("0.72"), Decimal("0.76"), Decimal("0.74")))
        self.assertEqual(no.reference("buy"), Decimal("0.76"))
        yes = self.hub.quote(Instrument("event", "KXETH-26SEP1617-B2390", "kalshi", market_id="KXETH-26SEP1617-B2390", right="yes"))
        self.assertEqual((yes.bid, yes.ask), (Decimal("0.24"), Decimal("0.28")))

    def test_drain_hands_the_tick_fill_venues_and_resolutions_once(self):
        self.hub.on_fill_candidate("kalshi", {"order_id": "o1"})
        self.hub.on_fill_candidate("kalshi", {"order_id": "o2"})
        self.hub.on_resolution("kalshi", {"ticker": "KXFED-26SEP-T3.75", "event_type": "settled", "result": "yes"})
        drained = self.hub.drain()
        self.assertEqual(drained["fill_venues"], ["kalshi"])
        self.assertEqual(drained["resolutions"][0]["ticker"], "KXFED-26SEP-T3.75")
        self.assertEqual(self.hub.drain(), {"fill_venues": [], "resolutions": []})

    def test_a_feed_down_for_five_minutes_is_said_once_an_hour(self):
        feed = KalshiFeed(self.hub, credentials()[0], clock=self.clock)
        self.hub.add(feed)
        self.hub.on_status(feed, connected=False, detail="ConnectionError: refused")
        self.assertEqual(self.hub.check_health(), [])
        self.clock.advance(301)
        said = self.hub.check_health()
        self.assertEqual(len(said), 1)
        self.assertIn("kalshi has been down for 5 minutes", said[0])
        self.assertEqual(self.alerts[0][0], "warning")
        self.clock.advance(600)
        self.assertEqual(self.hub.check_health(), [], "not again inside the hour")
        self.hub.on_status(feed, connected=True, detail=None)
        self.clock.advance(4000)
        self.assertEqual(self.hub.check_health(), [], "a feed that came back is not down")
        self.assertEqual(self.hub.status()["feeds"]["kalshi"]["connected"], True)


class KalshiFeedTests(HubCase):
    def feed(self, *sockets):
        creds, transport = credentials()
        connector = Connector(*sockets)
        feed = KalshiFeed(self.hub, creds, connect=connector, clock=self.clock, sleep=lambda s: None)
        return feed, connector, transport

    def test_the_handshake_carries_the_gateway_signed_headers_and_subscribes_first(self):
        sock = FakeSocket([{"id": 1, "type": "subscribed", "msg": {"channel": "fill", "sid": 7}}])
        feed, connector, _ = self.feed(sock)
        with self.assertRaises(ConnectionError):
            feed.run_once(self.stop)
        url, headers = connector.calls[0]
        self.assertEqual(url, "wss://api.elections.kalshi.com/trade-api/ws/v2")
        self.assertEqual(headers, KALSHI_HEADERS)
        self.assertEqual([m["params"]["channels"] for m in sock.sent[:2]], [["fill"], ["market_lifecycle_v2"]])
        self.assertEqual(sock.sent[2]["params"], {"channels": ["ticker"], "market_tickers": ["KXFED-26SEP-T3.75"]})
        self.assertEqual(feed.sids, {"fill": 7})
        self.assertTrue(sock.closed)

    def test_a_fill_becomes_a_candidate_and_a_held_market_resolving_prompts_the_sweep(self):
        sock = FakeSocket(
            [
                {"type": "fill", "sid": 1, "msg": {"market_ticker": "KXFED-26SEP-T3.75", "order_id": "o1", "count_fp": "10.00"}},
                {"type": "market_lifecycle_v2", "sid": 2, "seq": 4, "msg": {"market_ticker": "KXOTHER-1", "event_type": "determined", "result": "no"}},
                {"type": "market_lifecycle_v2", "sid": 2, "seq": 5, "msg": {"market_ticker": "KXFED-26SEP-T3.75", "event_type": "determined", "result": "yes"}},
                {"type": "market_lifecycle_v2", "sid": 2, "seq": 6, "msg": {"market_ticker": "KXFED-26SEP-T3.75", "event_type": "created"}},
                {"type": "ticker", "sid": 3, "msg": {"market_ticker": "KXFED-26SEP-T3.75", "yes_bid_dollars": "0.88", "yes_ask_dollars": "0.89", "last_price_dollars": "0.89"}},
            ]
        )
        feed, _, _ = self.feed(sock)
        with self.assertRaises(ConnectionError):
            feed.run_once(self.stop)
        drained = self.hub.drain()
        self.assertEqual(drained["fill_venues"], ["kalshi"])
        self.assertEqual(len(drained["resolutions"]), 1, "the firehose is filtered to held markets")
        self.assertEqual(drained["resolutions"][0]["result"], "yes")
        self.assertTrue(drained["resolutions"][0]["provisional"], "determined can still be disputed")
        quote = self.hub.quote(Instrument("event", "KXFED-26SEP-T3.75", "kalshi", market_id="KXFED-26SEP-T3.75"))
        self.assertEqual((quote.bid, quote.ask, quote.last), (Decimal("0.88"), Decimal("0.89"), Decimal("0.89")))

    def test_a_terminal_channel_error_resubscribes_on_the_same_socket(self):
        sock = FakeSocket([{"type": "error", "id": 2, "msg": {"code": 25, "msg": "Subscription buffer overflow"}}])
        feed, _, _ = self.feed(sock)
        with self.assertRaises(ConnectionError):
            feed.run_once(self.stop)
        subscribes = [m for m in sock.sent if m["cmd"] == "subscribe"]
        self.assertEqual(len(subscribes), 6, "three subscriptions, twice")
        self.assertEqual(feed.resubscribes, 1)

    def test_a_change_in_held_markets_moves_the_ticker_subscription(self):
        sock = FakeSocket([{"type": "subscribed", "id": 3, "msg": {"channel": "ticker", "sid": 9}}, {"type": "noop"}])
        feed, _, _ = self.feed(sock)
        original = self.hub.held_symbols
        calls = {"n": 0}

        def held_symbols(venue):
            calls["n"] += 1
            # The first call subscribes at connect time; the desk buys a second market after that.
            return {"KXFED-26SEP-T3.75", "KXCPI-26OCT"} if calls["n"] > 1 else {"KXFED-26SEP-T3.75"}

        self.hub.held_symbols = held_symbols
        try:
            with self.assertRaises(ConnectionError):
                feed.run_once(self.stop)
        finally:
            self.hub.held_symbols = original
        unsubscribe = [m for m in sock.sent if m["cmd"] == "unsubscribe"]
        self.assertEqual(unsubscribe[0]["params"], {"sids": [9]})
        self.assertEqual(sock.sent[-1]["params"]["market_tickers"], ["KXCPI-26OCT", "KXFED-26SEP-T3.75"])

    def test_run_forever_reconnects_with_backoff_and_stops_when_told(self):
        sleeps: list[float] = []
        creds, _ = credentials()
        connector = Connector(FakeSocket([]), FakeSocket([]))
        feed = KalshiFeed(self.hub, creds, connect=connector, clock=self.clock, sleep=lambda s: sleeps.append(s) or (self.stop.set() if len(sleeps) == 2 else None))
        feed.run_forever(self.stop)
        self.assertEqual(len(connector.calls), 2)
        self.assertEqual(feed.attempts, 2)
        self.assertTrue(all(s >= 0 for s in sleeps))
        self.assertIn("ConnectionError", feed.last_error)
        self.assertEqual(self.hub.status()["feeds"].get("kalshi", {}).get("connected"), False)

    def test_dollars_reads_decimal_strings_and_integer_cents(self):
        self.assertEqual(dollars({"yes_bid_dollars": "0.55"}, "yes_bid"), Decimal("0.55"))
        self.assertEqual(dollars({"yes_bid": 55}, "yes_bid"), Decimal("0.55"))
        self.assertIsNone(dollars({"yes_bid": True}, "yes_bid"))
        self.assertIsNone(dollars({}, "yes_bid"))


class CoinbaseFeedTests(HubCase):
    def test_the_market_feed_subscribes_heartbeats_first_then_tickers_for_held_and_allowed_products(self):
        sock = FakeSocket(
            [
                {"channel": "subscriptions", "sequence_num": 0, "events": [{"subscriptions": {"ticker": ["BTC-USD", "ETH-USD"]}}]},
                {"channel": "ticker", "sequence_num": 1, "events": [{"type": "snapshot", "tickers": [{"product_id": "BTC-USD", "price": "76795.1", "best_bid": "76790", "best_ask": "76800"}]}]},
                {"channel": "heartbeats", "sequence_num": 2, "events": [{"current_time": "x", "heartbeat_counter": 1}]},
                {"channel": "ticker", "sequence_num": 3, "events": [{"type": "update", "tickers": [{"product_id": "ETH-USD", "price": "2431.2"}]}]},
            ]
        )
        connector = Connector(sock)
        feed = CoinbaseMarketFeed(self.hub, connect=connector, clock=self.clock)
        with self.assertRaises(ConnectionError):
            feed.run_once(self.stop)
        self.assertEqual(connector.calls[0][0], "wss://advanced-trade-ws.coinbase.com")
        self.assertEqual(sock.sent[0], {"type": "subscribe", "product_ids": ["BTC-USD", "ETH-USD"], "channel": "heartbeats"})
        self.assertEqual(sock.sent[1]["channel"], "ticker")
        self.assertEqual(self.hub.quote(Instrument("crypto", "BTC-USD", "coinbase", market_id="BTC-USD")).ask, Decimal("76800"))
        self.assertEqual(self.hub.quote(Instrument("crypto", "ETH-USD", "coinbase", market_id="ETH-USD")).last, Decimal("2431.2"))

    def test_a_sequence_gap_reconnects_rather_than_trusting_the_stream(self):
        sock = FakeSocket(
            [
                {"channel": "ticker", "sequence_num": 1, "events": []},
                {"channel": "ticker", "sequence_num": 3, "events": []},
            ]
        )
        feed = CoinbaseMarketFeed(self.hub, connect=Connector(sock), clock=self.clock)
        with self.assertRaises(ConnectionError) as caught:
            feed.run_once(self.stop)
        self.assertIn("sequence gap", str(caught.exception))
        self.assertEqual(feed.gaps, 1)
        self.assertTrue(sock.closed)

    def test_the_user_feed_mints_a_jwt_per_subscribe_and_derives_fill_candidates_from_deltas(self):
        creds, transport = credentials()
        order = {"order_id": "ord-1", "product_id": "BTC-USD", "status": "OPEN", "cumulative_quantity": "0"}
        sock = FakeSocket(
            [
                {"channel": "user", "sequence_num": 1, "events": [{"type": "snapshot", "orders": [order]}]},
                {"channel": "user", "sequence_num": 2, "events": [{"type": "update", "orders": [{**order, "cumulative_quantity": "0.0001", "status": "OPEN"}]}]},
                {"channel": "user", "sequence_num": 3, "events": [{"type": "update", "orders": [{**order, "cumulative_quantity": "0.0001", "status": "FILLED"}]}]},
            ]
        )
        connector = Connector(sock)
        feed = CoinbaseUserFeed(self.hub, creds, connect=connector, clock=self.clock)
        with self.assertRaises(ConnectionError):
            feed.run_once(self.stop)
        self.assertEqual(connector.calls[0][0], "wss://advanced-trade-ws-user.coinbase.com")
        self.assertEqual([m["channel"] for m in sock.sent], ["heartbeats", "user"])
        self.assertTrue(all(m["jwt"] == "h.p.s" for m in sock.sent))
        self.assertEqual(len([c for c in transport.calls if c["url"].endswith("/ws-jwt")]), 2, "one JWT per message")
        self.assertTrue(feed.snapshot_complete)
        drained = self.hub.drain()
        self.assertEqual(drained["fill_venues"], ["coinbase"])
        self.assertEqual(feed.orders["ord-1"]["status"], "FILLED")

    def test_a_snapshot_of_fifty_orders_is_not_yet_complete(self):
        creds, _ = credentials()
        rows = [{"order_id": f"o{n}", "cumulative_quantity": "0"} for n in range(50)]
        sock = FakeSocket([{"channel": "user", "sequence_num": 1, "events": [{"type": "snapshot", "orders": rows}]}])
        feed = CoinbaseUserFeed(self.hub, creds, connect=Connector(sock), clock=self.clock)
        with self.assertRaises(ConnectionError):
            feed.run_once(self.stop)
        self.assertFalse(feed.snapshot_complete)
        self.assertEqual(len(feed.orders), 50)
        self.assertEqual(self.hub.drain()["fill_venues"], [], "a snapshot is state, not a fill")


if __name__ == "__main__":
    unittest.main()
