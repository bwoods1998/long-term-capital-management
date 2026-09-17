import unittest
from decimal import Decimal
from ltcm.feeds import FeedHub
from ltcm.feeds.depth import DepthBook
from ltcm.feeds.coinbase import CoinbaseMarketFeed
from ltcm.broker import Instrument


def level(side, price, quantity):
    return {"side": side, "price_level": str(price), "new_quantity": str(quantity)}


class DepthTests(unittest.TestCase):
    def test_snapshot_then_absolute_updates_delete_and_replace(self):
        book = DepthBook()
        with self.assertRaises(ValueError):
            book.apply({"type": "update", "updates": []})
        book.apply({"type": "snapshot", "updates": [level("bid", 99, 2), level("offer", 101, 3)]})
        book.apply({"type": "update", "updates": [level("bid", 99, 1), level("bid", 98, 4)]})
        self.assertEqual(book.summary()["bids"], [["99", "1"], ["98", "4"]])
        book.apply({"type": "update", "updates": [level("bid", 99, 0)]})
        self.assertEqual(book.summary()["bid"], "98")
        book.apply({"type": "snapshot", "updates": [level("bid", 95, 1), level("offer", 96, 1)]})
        self.assertEqual(book.summary()["bid"], "95")
        self.assertEqual(len(book.bids), 1)

    def test_invalid_and_unbounded_books_are_refused(self):
        for row in [level("bid", "NaN", 1), level("offer", 1, -1), level("oops", 1, 1)]:
            with self.assertRaises(ValueError):
                DepthBook().apply({"type": "snapshot", "updates": [row]})
        with self.assertRaises(ValueError):
            DepthBook(max_levels=1).apply({"type": "snapshot", "updates": [level("bid", 1, 1), level("offer", 2, 1)]})

    def test_feed_publishes_fresh_bounded_features_and_invalidates_on_disconnect(self):
        now = [100.0]
        hub = FeedHub(clock=lambda: now[0])
        feed = CoinbaseMarketFeed(hub, clock=lambda: now[0])
        feed.products = {"BTC-USD"}
        feed.handle(None, "l2_data", {"events": [{"type": "snapshot", "product_id": "BTC-USD", "updates": [level("bid", 99, 2), level("offer", 101, 3)]}]})
        self.assertEqual(hub.depth("coinbase")["BTC-USD"]["bid_depth_usd"], "198")
        instrument = Instrument("crypto", "BTC-USD", "coinbase")
        self.assertEqual(hub.quote(instrument).bid, Decimal("99"))
        now[0] += 6
        self.assertEqual(hub.depth("coinbase"), {})
        hub.invalidate_depth("coinbase")
        self.assertIsNone(hub.quote(instrument))

    def test_account_events_wake_but_market_prints_do_not(self):
        wakes = []
        hub = FeedHub(wake=lambda: wakes.append(True))
        hub.on_fill_candidate("coinbase", {})
        hub.on_resolution("kalshi", {})
        self.assertEqual(len(wakes), 2)
