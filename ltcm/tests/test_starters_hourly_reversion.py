"""Fee-aware crypto entries: known costs, adequate target and no duplicate working buys."""
import unittest

from ltcm.backtest import check_code
from ltcm.starters import hourly_reversion as strategy
from ltcm.strategies import STARTERS_DIR


class Kit:
    def __init__(self, last=95, ask=None):
        self.last = last
        self.ask = last if ask is None else ask
        self.context = {"fee_rates": {"coinbase": {"maker": "0.005", "taker": "0.009", "age_seconds": 0}}}
        self.log = []

    def bars(self, *args):
        return [{"close": 100}] * 24 + [{"close": self.last}]

    def quote(self, *args):
        return {"ask": self.ask, "bid": self.ask - 0.01}

    def say(self, text):
        self.log.append(text)


class ReversionTests(unittest.TestCase):
    def decide(self, kit, **params):
        return strategy.decide(kit, {"symbols": ["BTC-USD"], **params})

    def test_dip_without_fee_positive_target_is_not_a_trade(self):
        kit = Kit(last=99)
        self.assertEqual(self.decide(kit)["intents"], [])
        self.assertTrue(any("target net" in s for s in kit.log))

    def test_sufficient_target_proposes_capped_limit_with_complete_exit_plan(self):
        order = self.decide(Kit())["intents"][0]
        self.assertEqual(order["side"], "buy")
        self.assertEqual(order["expire_after_seconds"], 120)
        self.assertIn("0.90% fees each way", order["rationale"])
        self.assertGreater(float(order["target_price"]), float(order["limit_price"]))
        self.assertLess(float(order["stop_price"]), float(order["limit_price"]))
        self.assertAlmostEqual(float(order["quantity"]) * float(order["limit_price"]), 25, places=3)

    def test_missing_stale_invalid_fees_never_become_free(self):
        for fees in ({}, {"taker": "0.009", "age_seconds": 901}, {"taker": "NaN", "age_seconds": 0},
                     {"taker": "-0.01", "age_seconds": 0}, {"taker": "0.009", "age_seconds": -1}):
            kit = Kit()
            kit.context["fee_rates"] = {"coinbase": fees}
            self.assertEqual(self.decide(kit)["intents"], [])
            self.assertIn("fee tier unavailable", kit.log[0])

    def test_fee_tier_change_changes_eligibility_without_code_change(self):
        kit = Kit(last=96.5)
        self.assertTrue(self.decide(kit)["intents"])
        kit.context["fee_rates"]["coinbase"]["taker"] = "0.012"
        self.assertEqual(self.decide(kit)["intents"], [])

    def test_resting_buy_or_held_position_prevents_duplicate_entry(self):
        for field, value in (("open_orders", [{"symbol": "BTC-USD", "side": "buy"}]),
                             ("positions", [{"symbol": "BTC-USD", "quantity": "1"}])):
            kit = Kit()
            kit.context[field] = value
            self.assertEqual(self.decide(kit)["intents"], [])

    def test_margin_cannot_be_removed_and_code_passes_sandbox_screen(self):
        self.assertEqual(self.decide(Kit(last=97.5), min_margin=0, slippage_buffer=0)["intents"], [])
        check_code((STARTERS_DIR / "hourly_reversion.py").read_text())

    def test_buy_rounds_up_to_the_quote_tick_and_sizes_at_that_price(self):
        order = self.decide(Kit(ask=95.001))["intents"][0]
        self.assertEqual(order["limit_price"], "95.01")
        kit = Kit(ask=0.95001)
        kit.products = lambda count: [{"symbol": "BTC-USD", "quote_increment": "0.0001"}]
        order = self.decide(kit, symbols="top:1")["intents"][0]
        self.assertEqual(order["limit_price"], "0.9501")
