"""Quote-informed execution: the tape's own touch where it has one, conservative where it is stale."""

from __future__ import annotations

import unittest

from league.replay import STALE_QUOTE_SECONDS
from league.tests.test_replay import WIDE, alpaca_tape, buy, limit, log_of
from league.tests.test_replay import play as _play


def play(plan, tape, **kw):
    return _play(plan, tape, limits=WIDE, **kw)


def quoted(tape, index, bid, ask, age=0.3, symbol="BTC/USD"):
    tape["steps"][index].setdefault("quotes", {})[symbol] = {"bid": bid, "ask": ask, "age": age}
    return tape


class QuoteTouchTest(unittest.TestCase):
    def test_a_fresh_quote_is_the_touch_a_market_order_pays(self):
        tape = quoted(alpaca_tape([100, 100], half_spread_bps=1.0), 0, 99.90, 100.10)
        result = play({0: [buy(quantity=1)]}, tape)
        fill = result["fill_log"][0]
        self.assertAlmostEqual(fill["price"], 100.10)  # the quoted ask, not close x (1 + 1bp)
        shown = log_of(result)[0]["quotes"]["BTC/USD"]
        self.assertEqual((shown["bid"], shown["ask"]), (99.90, 100.10))
        self.assertEqual(shown["t"], "2026-09-10T12:59:59.700000Z")  # dated when quoted: now less its 0.3 s age
        self.assertEqual(result["execution"]["touch"], {"assumed": 1, "quoted": 1})

    def test_a_stale_quote_is_centred_on_the_close_and_at_least_twice_the_assumed_spread(self):
        tape = quoted(alpaca_tape([100, 100], half_spread_bps=5.0), 0, 90.0, 90.02, age=STALE_QUOTE_SECONDS + 1)
        result = play({0: [buy(quantity=1)]}, tape)
        self.assertAlmostEqual(result["fill_log"][0]["price"], 100 * (1 + 2 * 5e-4))
        self.assertEqual(result["execution"]["touch"]["stale"], 1)

    def test_the_double_spread_variant_doubles_every_touch(self):
        base = play({0: [buy(quantity=1)]}, quoted(alpaca_tape([100, 100], half_spread_bps=1.0), 0, 99.9, 100.1))
        stressed_tape = quoted(alpaca_tape([100, 100], half_spread_bps=1.0), 0, 99.9, 100.1)
        stressed_tape["spread_stress"] = 2.0
        stressed = play({0: [buy(quantity=1)]}, stressed_tape)
        self.assertAlmostEqual(base["fill_log"][0]["price"], 100.1)
        self.assertAlmostEqual(stressed["fill_log"][0]["price"], 100.2)
        self.assertEqual(stressed["execution"]["spread_stress"], 2.0)
        unquoted = alpaca_tape([100, 100], half_spread_bps=1.0)
        unquoted["spread_stress"] = 2.0
        self.assertAlmostEqual(play({0: [buy(quantity=1)]}, unquoted)["fill_log"][0]["price"], 100 * (1 + 2e-4))

    def test_a_crossed_or_one_sided_quote_falls_back_to_the_assumption(self):
        for bid, ask in ((100.2, 100.1), (None, 100.1), (0, 100.1)):
            tape = quoted(alpaca_tape([100, 100], half_spread_bps=1.0), 0, bid, ask)
            result = play({0: [buy(quantity=1)]}, tape)
            self.assertAlmostEqual(result["fill_log"][0]["price"], 100.01)
            self.assertNotIn("execution", result)

    def test_a_tape_without_quotes_or_stress_reports_nothing_new(self):
        result = play({0: [buy(quantity=1)]}, alpaca_tape([100, 100], half_spread_bps=1.0))
        self.assertNotIn("execution", result)


class TouchedLimitTest(unittest.TestCase):
    def test_a_touched_limit_is_not_a_fill_and_a_traded_through_one_is(self):
        # Rest a buy at 99 at step 0. Step 1's low touches 99 exactly: no fill. Step 2 trades through.
        touched = alpaca_tape([100, {"o": 100, "h": 100, "l": 99.0, "c": 99.5, "v": 1}, 100])
        result = play({0: [limit("buy", 1, 99.0)]}, touched)
        self.assertEqual(result["fills"], 0)
        through = alpaca_tape([100, {"o": 100, "h": 100, "l": 99.0, "c": 99.5, "v": 1}, {"o": 99.5, "h": 99.6, "l": 98.9, "c": 99.2, "v": 1}])
        result = play({0: [limit("buy", 1, 99.0)]}, through)
        self.assertEqual(result["fills"], 1)
        self.assertAlmostEqual(result["fill_log"][0]["price"], 99.0)  # at its own price, as a maker

    def test_a_quote_at_the_limit_is_not_a_fill_either(self):
        tape = alpaca_tape([100, 100, 100])
        quoted(tape, 1, 98.5, 99.0)  # the ask comes down to the resting bid: still no print through it
        result = play({0: [limit("buy", 1, 99.0)]}, tape)
        self.assertEqual(result["fills"], 0)


if __name__ == "__main__":
    unittest.main()
