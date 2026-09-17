"""The spot quoting starter's fee guard: no bids unless the spread clears two maker fees and a
margin, offers that clear them, and no sub-dollar coins. A fake kit; no network."""

from __future__ import annotations

import importlib.util
import unittest
from decimal import Decimal

from ltcm.backtest import check_code
from ltcm.strategies import QUOTE_LIVE_PARAMS, QUOTE_VARIANTS, STARTERS_DIR

NOW = "2026-09-17T04:10:00.000Z"


def load():
    spec = importlib.util.spec_from_file_location("starter_spot_quotes_guard", STARTERS_DIR / "spot_quotes.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class QuoteKit:
    """A flat book: BTC 76,000 and ETH 2,400 a dollar wide, and a twelve-cent coin."""

    QUOTES = {
        "BTC-USD": ("75999.50", "76000.50"),
        "ETH-USD": ("2399.50", "2400.50"),
        "JASMY-USD": ("0.1199", "0.1201"),
        "BIG-USD": ("100.00", "100.02"),
    }

    def __init__(self, *, positions=(), orders=(), products=()):
        self.context = {"now": NOW, "positions": list(positions), "open_orders": list(orders), "learning_usd": "25", "live": True}
        self.rows = list(products)
        self.log = []

    def say(self, text):
        self.log.append(text)

    def quote(self, symbol, asset_class="crypto", venue="coinbase"):
        bid, ask = self.QUOTES[symbol]
        return {"bid": bid, "ask": ask, "last": bid}

    def products(self, limit=25, quote="USD", min_volume_usd=250000.0):
        return self.rows[:limit]


def sides(out):
    return [(i["instrument"]["symbol"], i["side"]) for i in out["intents"]]


class FeeGuardTests(unittest.TestCase):
    def test_a_one_percent_spread_places_no_bid_and_cancels_the_resting_one(self):
        orders = [{"order_id": "ord-bid", "strategy": "spot_quotes", "symbol": "BTC-USD", "side": "buy", "limit_price": "75240.00", "submitted_at": "2026-09-17T04:09:00Z"}]
        kit = QuoteKit(orders=orders)
        out = load().decide(kit, {"symbols": ["BTC-USD", "ETH-USD"], "spread": 0.01, "maker_fee": 0.005})
        self.assertEqual(out["intents"], [], "1% does not clear two 0.5% maker fees and a 0.2% margin")
        self.assertEqual(out["cancels"], ["ord-bid"], "a bid with no target is gone")
        self.assertIn("bids off: spread 1.00% < 2*fee+margin 1.20%", kit.log)

    def test_a_held_coin_is_offered_over_cost_by_both_fees_and_the_margin(self):
        kit = QuoteKit(positions=[{"symbol": "BTC-USD", "asset_class": "crypto", "quantity": "0.001", "average_cost": "76000"}])
        out = load().decide(kit, {"symbols": ["BTC-USD"], "spread": 0.01})
        self.assertEqual(sides(out), [("BTC-USD", "sell")])
        offer = out["intents"][0]
        self.assertGreaterEqual(Decimal(offer["limit_price"]), Decimal("76000") * Decimal("1.012"))
        self.assertEqual(offer["limit_price"], "76912.00", "cost x 1.012 is above mid x 1.005 and the ask")
        self.assertTrue(offer["post_only"])
        self.assertEqual(offer["quantity"], "0.001000")

    def test_the_offer_never_prints_under_its_floor(self):
        kit = QuoteKit(positions=[{"symbol": "BTC-USD", "asset_class": "crypto", "quantity": "0.001", "average_cost": "75500.01"}])
        offer = load().decide(kit, {"symbols": ["BTC-USD"], "spread": 0.004})["intents"][0]
        self.assertGreaterEqual(Decimal(offer["limit_price"]), Decimal("75500.01") * Decimal("1.012"), "76406.01012 rounds up to the cent")
        self.assertEqual(offer["limit_price"], "76406.02")

    def test_a_three_percent_spread_bids(self):
        kit = QuoteKit()
        out = load().decide(kit, {"symbols": ["BTC-USD"], "spread": 0.03})
        self.assertEqual(sides(out), [("BTC-USD", "buy")])
        bid = out["intents"][0]
        self.assertLessEqual(Decimal(bid["limit_price"]), Decimal("76000") * Decimal("0.97"))
        self.assertAlmostEqual(float(bid["quantity"]) * float(bid["limit_price"]), 25.0, delta=0.1)
        self.assertFalse([line for line in kit.log if line.startswith("bids off")])

    def test_a_spread_exactly_at_the_round_trip_bids(self):
        self.assertEqual(sides(load().decide(QuoteKit(), {"symbols": ["BTC-USD"], "spread": 0.012})), [("BTC-USD", "buy")])

    def test_bid_false_places_no_bid_at_any_spread_but_still_offers_inventory(self):
        positions = [{"symbol": "ETH-USD", "asset_class": "crypto", "quantity": "0.01", "average_cost": "2300"}]
        kit = QuoteKit(positions=positions)
        out = load().decide(kit, {"symbols": ["BTC-USD", "ETH-USD"], "spread": 0.03, "bid": False})
        self.assertEqual(sides(out), [("ETH-USD", "sell")], "exit-only")
        self.assertIn("bids off: params", kit.log)

    def test_a_twelve_cent_coin_is_skipped(self):
        kit = QuoteKit(positions=[{"symbol": "JASMY-USD", "asset_class": "crypto", "quantity": "500", "average_cost": "0.11"}])
        out = load().decide(kit, {"symbols": ["JASMY-USD", "BTC-USD"], "spread": 0.03})
        self.assertEqual(sides(out), [("BTC-USD", "buy")])
        self.assertTrue(any(line.startswith("JASMY-USD: mid 0.1200 is under 1.00") for line in kit.log), kit.log)

    def test_a_listed_quote_increment_coarser_than_a_cent_is_the_tick(self):
        positions = [{"symbol": "BIG-USD", "asset_class": "crypto", "quantity": "1", "average_cost": "50"}]
        rows = [{"symbol": "BIG-USD", "price": 100.01, "volume_usd": 1e7, "quote_increment": 0.5}]
        offer = load().decide(QuoteKit(positions=positions, products=rows), {"symbols": "top:1", "spread": 0.002})["intents"][0]
        self.assertEqual(offer["limit_price"], "100.52", "ask 100.02 plus a 0.50 tick beats mid x 1.001 and cost x 1.012")
        rows[0]["quote_increment"] = 0.0001
        offer = load().decide(QuoteKit(positions=positions, products=rows), {"symbols": "top:1", "spread": 0.002})["intents"][0]
        self.assertEqual(offer["limit_price"], "100.12", "a finer increment still steps a cent: prices print to the cent")

    def test_the_starter_passes_the_backtest_code_screen(self):
        check_code((STARTERS_DIR / "spot_quotes.py").read_text(encoding="utf-8"))


class QuoteSettingsTests(unittest.TestCase):
    def test_the_live_desk_is_exit_only_and_every_shadow_variant_clears_the_guard(self):
        self.assertEqual(QUOTE_LIVE_PARAMS["crypto"], {"symbols": ["BTC-USD", "ETH-USD"], "bid": False})
        self.assertEqual(QUOTE_VARIANTS["crypto"], [{"spread": 0.015}, {"spread": 0.02, "requote_seconds": 1800}, {"spread": 0.03}])
        self.assertEqual(sides(load().decide(QuoteKit(), dict(QUOTE_LIVE_PARAMS["crypto"]))), [])
        for variant in QUOTE_VARIANTS["crypto"]:
            kit = QuoteKit()
            out = load().decide(kit, {**variant, "symbols": ["BTC-USD"]})
            self.assertEqual(sides(out), [("BTC-USD", "buy")], variant)


if __name__ == "__main__":
    unittest.main()
