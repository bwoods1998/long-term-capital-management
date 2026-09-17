"""The evidence gate: luck and edge told apart on a strategy's settled record (leap: evidence)."""

from __future__ import annotations

import random
import unittest

from ltcm import evidence
from ltcm.evidence import assess, block_bootstrap_lower, lopsided_n_needed, passes, settings, wilson_upper


def favorites(n, losses, price="0.93", fee="0"):
    """A lopsided record: `n` event positions bought at `price`, `losses` of them lost."""
    return {"settled": n, "losses": losses, "asset_class": "event", "avg_entry_price": price, "avg_fee_per_contract": fee}


class WilsonTests(unittest.TestCase):
    def test_the_upper_bound_matches_known_values(self):
        # Wilson score interval, upper limit: (p + z^2/2n + z sqrt(p(1-p)/n + z^2/4n^2)) / (1 + z^2/n)
        self.assertAlmostEqual(wilson_upper(1, 40, 0.84), 0.055377, places=5)
        self.assertAlmostEqual(wilson_upper(2, 40, 0.84), 0.087536, places=5)
        self.assertAlmostEqual(wilson_upper(3, 45, 0.84), 0.105063, places=5)
        self.assertAlmostEqual(wilson_upper(0, 10, 1.96), 3.8416 / 13.8416, places=9)  # 0 of n: z^2 / (n + z^2)
        self.assertAlmostEqual(wilson_upper(5, 10, 1.96), 0.763410, places=5)
        # 1 loss in the 43 a 0.93 favorite needs, z 0.84: under the 0.07 breakeven, so it passes.
        self.assertAlmostEqual(wilson_upper(1, 43, 0.84), 0.0515913, places=6)

    def test_the_upper_bound_is_where_the_score_test_stops_rejecting(self):
        """Checked against its definition, not its formula: the p at which (phat - p) / sqrt(p(1-p)/n)
        is exactly -z, found by bisection."""
        import math

        for losses, n, z in ((1, 43, 0.84), (3, 80, 0.84), (0, 40, 0.84), (7, 135, 1.28)):
            lo, hi = losses / n, 1.0
            for _ in range(200):
                mid = (lo + hi) / 2
                if (losses / n - mid) / math.sqrt(mid * (1 - mid) / n) > -z:
                    lo = mid
                else:
                    hi = mid
            self.assertAlmostEqual(wilson_upper(losses, n, z), lo, places=9, msg=(losses, n, z))

    def test_edges(self):
        self.assertEqual(wilson_upper(0, 0), 1.0, "no observations never look safe")
        self.assertEqual(wilson_upper(40, 40), 1.0)
        self.assertLess(wilson_upper(0, 1000), 0.001)
        self.assertEqual(wilson_upper(-3, 10), wilson_upper(0, 10))


class LopsidedTests(unittest.TestCase):
    def test_n_needed_is_three_expected_losses_at_breakeven_and_never_under_forty(self):
        self.assertEqual(lopsided_n_needed(0.93), 43)
        self.assertEqual(lopsided_n_needed(0.925), 40, "3 / 0.075 is 40, not 41 on a float's last digit")
        self.assertEqual(lopsided_n_needed(0.85), 40)
        self.assertEqual(lopsided_n_needed(0.97), 100)

    def test_at_ninety_three_cents_one_loss_passes_and_two_fail(self):
        """The plan's check at 0.93, at the 43 settlements the rule needs there (the plan said 40,
        under its own n_needed of max(40, ceil(3 / 0.07)) = 43)."""
        self.assertEqual(passes(favorites(43, 1)), (True, passes(favorites(43, 1))[1], 43))
        ok, reason, need = passes(favorites(43, 2))
        self.assertFalse(ok)
        self.assertIn("breakeven", reason)
        self.assertEqual(need, 43)
        ok, reason, need = passes(favorites(6, 0))
        self.assertFalse(ok, "six wins in six is below n_needed")
        self.assertIn("6 of 43", reason)
        self.assertFalse(passes(favorites(40, 1))[0], "40 is under the 43 a 0.93 favorite needs")
        self.assertTrue(passes(favorites(40, 1, price="0.92"))[0], "at 0.92, 40 settled with one loss passes")
        self.assertFalse(passes(favorites(40, 2, price="0.92"))[0])

    def test_fees_lower_the_breakeven_loss_rate(self):
        verdict = assess(favorites(80, 3, fee="0.0046"))  # a taker's fee at 0.93
        self.assertAlmostEqual(verdict["breakeven_loss_rate"], 0.0654, places=4)
        self.assertTrue(verdict["passes"])
        self.assertFalse(assess(favorites(80, 3, fee="0.03"))["passes"], "a breakeven of 4% is under the bound")
        self.assertGreater(verdict["lower"], 0, "the per-dollar lower bound is positive when it passes")
        self.assertLess(assess(favorites(80, 6))["lower"], 0)

    def test_a_cheap_event_strategy_or_a_mixed_one_is_judged_by_the_bootstrap(self):
        self.assertEqual(assess(favorites(60, 0, price="0.50"))["kind"], "bootstrap")
        self.assertEqual(assess({**favorites(60, 0), "asset_class": "mixed"})["kind"], "bootstrap")
        self.assertEqual(assess({**favorites(60, 0), "asset_class": None})["kind"], "bootstrap")
        self.assertEqual(assess(favorites(60, 0, price="0.79"))["kind"], "bootstrap")
        self.assertEqual(assess(favorites(60, 0, price="0.79"), skew_price="0.75")["kind"], "lopsided", "skew_price is configurable")

    def test_a_breakeven_variant_passes_rarely_and_a_real_edge_passes_more_often(self):
        """The documented trade-off, simulated: at n = 100 and 0.93, breakeven passes about a
        fifth of the time, a +2 cent favorite about half."""
        rng = random.Random(5)

        def rate(loss_rate, n=100, trials=2000):
            hits = 0
            for _ in range(trials):
                losses = sum(1 for _ in range(n) if rng.random() < loss_rate)
                hits += passes(favorites(n, losses))[0]
            return hits / trials

        breakeven, edge = rate(0.07), rate(0.05)
        self.assertTrue(0.10 <= breakeven <= 0.35, breakeven)
        self.assertTrue(0.35 <= edge <= 0.70, edge)


class BootstrapTests(unittest.TestCase):
    DAYS = {"2026-09-16": [0.1, 0.2, -0.05], "2026-09-17": [0.05, -0.1], "2026-09-18": [0.3], "2026-09-19": [-0.2, 0.0, 0.1]}

    def test_the_bootstrap_is_deterministic_with_a_seed(self):
        # The resampling is cached, so a second call with the same arguments would read the cache
        # and prove nothing (Sept 17, 2026 review): the cache is cleared before every repeat.
        evidence._bootstrap.cache_clear()
        first = block_bootstrap_lower(self.DAYS, q=0.20, n=1000, seed=11)
        evidence._bootstrap.cache_clear()
        self.assertEqual(first, block_bootstrap_lower(self.DAYS, q=0.20, n=1000, seed=11))
        evidence._bootstrap.cache_clear()
        self.assertEqual(block_bootstrap_lower(list(self.DAYS.values()), seed=11), first, "a list of days works as well")
        evidence._bootstrap.cache_clear()
        few = [block_bootstrap_lower(self.DAYS, q=0.20, n=9, seed=seed) for seed in (11, 12)]
        evidence._bootstrap.cache_clear()
        self.assertEqual(few, [block_bootstrap_lower(self.DAYS, q=0.20, n=9, seed=seed) for seed in (11, 12)])
        self.assertNotEqual(few[0], few[1], "the seed decides the draws")
        blocks = ((0.25, 3), (-0.05, 2), (0.3, 1), (-0.1, 3))
        self.assertEqual(evidence._bootstrap.__wrapped__(blocks, 0.2, 1000, 17), evidence._bootstrap.__wrapped__(blocks, 0.2, 1000, 17), "uncached, run twice")

    def test_the_bootstrap_matches_a_value_computed_by_hand(self):
        """A fixed seed gives a fixed answer in any process: `random.Random(17)` is Mersenne Twister
        seeded from the integer, which Python keeps stable across versions."""
        import random as stdlib_random

        days = [[0.1, 0.1, 0.05], [0.0, -0.05], [0.3], [-0.2, 0.05, 0.05]]
        blocks = [(sum(day), len(day)) for day in days]
        rng = stdlib_random.Random(17)
        means = []
        for _ in range(200):
            picks = [blocks[int(rng.random() * 4)] for _ in range(4)]
            means.append(sum(p[0] for p in picks) / sum(p[1] for p in picks))
        means.sort()
        evidence._bootstrap.cache_clear()
        self.assertEqual(block_bootstrap_lower(days, q=0.2, n=200, seed=17), means[int(0.2 * 199)])

    def test_the_quantile_sits_below_the_mean_and_one_day_is_one_block(self):
        pooled = [v for day in self.DAYS.values() for v in day]
        mean = sum(pooled) / len(pooled)
        self.assertLess(block_bootstrap_lower(self.DAYS), mean)
        self.assertGreater(block_bootstrap_lower(self.DAYS, q=0.80), mean)
        self.assertAlmostEqual(block_bootstrap_lower({"d": [0.1, -0.3, 0.5]}), 0.1, places=9, msg="a single block resamples to itself")
        self.assertIsNone(block_bootstrap_lower({}))
        self.assertIsNone(block_bootstrap_lower({"d": []}))

    def record(self, returns, settled=None):
        return {"settled": len(returns) if settled is None else settled, "asset_class": "crypto", "returns": returns}

    def test_the_bootstrap_rule_needs_min_n_several_days_and_a_positive_bound(self):
        steady = [[f"2026-09-{16 + i % 4:02d}", 0.02 + 0.01 * (i % 3)] for i in range(30)]
        ok, reason, need = passes(self.record(steady))
        self.assertTrue(ok, reason)
        self.assertEqual(need, 25)
        self.assertFalse(passes(self.record(steady[:24]))[0], "24 of 25")
        one_day = [["2026-09-16", 0.05] for _ in range(40)]
        self.assertIn("day", passes(self.record(one_day))[1])
        self.assertTrue(passes(self.record(one_day), min_days=1)[0], "min_days is configurable")
        bad_day = [[f"2026-09-{16 + i % 3:02d}", -0.32 if i % 3 == 2 else 0.2] for i in range(30)]
        verdict = assess(self.record(bad_day))
        self.assertGreater(sum(r[1] for r in bad_day), 0, "a positive mean")
        self.assertFalse(verdict["passes"], "and one bad day in three")
        self.assertLessEqual(verdict["lower"], 0)
        self.assertFalse(passes({"settled": 50})[0], "no returns, no evidence")
        self.assertFalse(passes({})[0])
        self.assertFalse(passes(None)[0])


class SettingsTests(unittest.TestCase):
    def test_config_strings_are_parsed_and_unknown_keys_dropped(self):
        cfg = settings({"z": "1.28", "min_n": "30", "skew_price": "0.85", "nonsense": 1, "min_days": None})
        self.assertEqual((cfg["z"], cfg["min_n"], cfg["skew_price"], cfg["min_days"]), (1.28, 30, 0.85, 3))
        self.assertNotIn("nonsense", cfg)
        self.assertEqual(settings(None), {**evidence.DEFAULTS, "skew_price": 0.80, "z": 0.84})
        self.assertEqual(settings({"z": "abc"})["z"], 0.84)
        self.assertEqual(settings({"full_size_multiple": "2.5"})["full_size_multiple"], 2.5)
        self.assertEqual(settings(None)["full_size_multiple"], 3.0)


if __name__ == "__main__":
    unittest.main()
