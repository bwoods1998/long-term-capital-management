"""THE PRE-REGISTERED SIZING-UP AND DEMOTION RULES of the equity lane (`league/equity/bands.py`, money's functions:
`sized_up`, `sized_sleeve_share`, `edm1`; the constitution's `equity_money.sized` and `.demotion`), on the money table in
force. Invented returns only (no market figure); standard library only."""

import math
import unittest
from decimal import Decimal as D

from league import stats
from league.equity import bands as B
from league.equity.bands import EquityRecord, edm1, sized_sleeve_share, sized_up
from league.live.money import EquityTable

TABLE = EquityTable.from_constitution()


def record(returns, *, pnl="50", bh_pnl="20", probe_sessions=10, realized_net="50", gaps=(), sd=None):
    returns = tuple(returns)
    return EquityRecord(n=len(returns), returns=returns, pnl=D(pnl), bh_pnl=None if bh_pnl is None else D(bh_pnl),
                        probe_sessions=probe_sessions, realized_net=D(realized_net), twin_gaps_bp=tuple(gaps),
                        validation_r_sd=sd)


def alternating(mean, spread, n):
    """n returns alternating mean + spread and mean - spread (n even: their mean is exactly `mean`)."""
    return [mean + spread if i % 2 == 0 else mean - spread for i in range(n)]


GOOD = alternating(0.004, 0.006, 24)        # mean 0.4% a close, an 80% bound above zero


class SizingUp(unittest.TestCase):
    def test_a_record_that_meets_every_leg_sizes_up(self):
        ok, why = sized_up(record(GOOD), TABLE)
        self.assertTrue(ok, why)
        self.assertIn("24 real closes", why)
        self.assertIn("beating the buy-and-hold's $20.00", why)

    def test_each_leg_alone_holds_it_at_probe(self):
        cases = (
            (record(GOOD[:19] + [0.01]), "20"),                           # 20 closes: passes the count...
            (record(GOOD[:19]), "19 real closes, under the 20 sizing up needs"),
            (record(alternating(-0.001, 0.006, 24)), "is not above zero"),
            (record(alternating(0.0005, 0.02, 24)), "lower bound"),
            (record([0.003] * 24), "no spread"),
            (record(GOOD, bh_pnl=None), "could not be priced"),
            (record(GOOD, pnl="20", bh_pnl="20"), "does not beat the same-risk buy-and-hold's $20.00"),
            (record(GOOD, pnl="10", bh_pnl="30"), "does not beat"),
            (record(GOOD, probe_sessions=4), "4 sessions at Probe, under the 5 it needs"),
        )
        first, *rest = cases
        self.assertTrue(sized_up(first[0], TABLE)[0], "the count's line is 20")
        for rec, said in rest:
            ok, why = sized_up(rec, TABLE)
            self.assertFalse(ok, said)
            self.assertIn(said, why)

    def test_the_bound_is_the_tables_confidence(self):
        rec = record(alternating(0.0012, 0.006, 24))
        bounds = stats.mean_bounds(list(rec.returns), 0.2)
        self.assertGreater(bounds["lcb"], 0)
        self.assertTrue(sized_up(rec, TABLE)[0])
        from dataclasses import replace

        strict = replace(TABLE, sized_confidence=0.99)
        self.assertLess(stats.mean_bounds(list(rec.returns), 0.01)["lcb"], 0)
        self.assertFalse(sized_up(rec, strict)[0])
        self.assertTrue(sized_up(record(GOOD, bh_pnl=None), replace(TABLE, sized_beat_bh=False))[0],
                        "beat_bh off (never, by the bounds) would not read the buy-and-hold")


class SizedSleeve(unittest.TestCase):
    def test_quarter_kelly_on_the_lower_bound_between_the_probes_and_the_cap(self):
        returns = alternating(0.0025, 0.03, 400)
        bounds = stats.mean_bounds(returns, 0.2)
        kelly = stats.quarter_kelly(bounds["lcb"], bounds["sd"] ** 2, fraction=0.25, cap=0.5)
        self.assertTrue(0.25 < kelly < 0.5, kelly)
        share = sized_sleeve_share(record(returns), TABLE)
        self.assertEqual(share, D(repr(kelly)).quantize(D("0.0001"), rounding="ROUND_DOWN"))

    def test_never_above_the_cap_nor_below_the_probes(self):
        self.assertEqual(sized_sleeve_share(record(GOOD), TABLE), D("0.50"), "a strong bound is capped at 0.50 x E")
        self.assertEqual(sized_sleeve_share(record(alternating(0.0002, 0.06, 40)), TABLE), D("0.25"), "the Probe's floor")
        self.assertEqual(sized_sleeve_share(record(alternating(-0.01, 0.02, 40)), TABLE), D("0.25"))
        self.assertEqual(sized_sleeve_share(record([0.01]), TABLE), D("0.25"), "one close: no bound, the Probe's share")


class EDM1(unittest.TestCase):
    def test_a_record_inside_every_line_is_not_demoted(self):
        self.assertIsNone(edm1(record(GOOD, sd=0.01, gaps=[-3, 2, -5, 1, 0]), TABLE))

    def test_the_sum_line_with_the_validation_sigma(self):
        sigma = 0.01
        n = 10
        line = -1.645 * sigma * math.sqrt(n)                        # -0.05202
        below = [line / n - 0.0001] * n
        above = [line / n + 0.0001] * n
        why = edm1(record(below, sd=sigma, realized_net="-10"), TABLE)
        self.assertIsNotNone(why)
        self.assertIn("EDM1: its 10 real closes returned", why)
        self.assertIn("the per-trade sd of its Validation run", why)
        self.assertIsNone(edm1(record(above, sd=sigma, realized_net="-10"), TABLE))
        self.assertIsNone(edm1(record(below[:9], sd=sigma, realized_net="-10"), TABLE), "under 10 closes the leg waits")

    def test_sigma_falls_back_to_its_own_then_to_the_rule(self):
        own = alternating(-0.012, 0.004, 10)
        sigma, source = B.edm1_sigma(record(own))
        mean = sum(own) / len(own)
        self.assertAlmostEqual(sigma, math.sqrt(sum((r - mean) ** 2 for r in own) / 9))
        self.assertIn("its own 10 real closes", source)
        for bad in (None, 0, -0.1, float("nan"), float("inf"), True, "0.01"):
            self.assertEqual(B.edm1_sigma(record(own, sd=bad))[0], sigma, bad)
        self.assertIn("EDM1", edm1(record(own), TABLE))                    # sum -0.12 < -1.645 x 0.0042 x sqrt(10)
        sigma, source = B.edm1_sigma(record([-0.01] * 10))
        self.assertEqual((sigma, source.startswith("the rule's fallback")), (B.EDM1_FALLBACK_SIGMA, True))
        # Nine closes: the record's own sd is not yet read; with the table's line at 5 the fallback is the sigma.
        from dataclasses import replace

        five = replace(TABLE, demotion_min_trades=5)
        self.assertEqual(B.edm1_sigma(record([-0.02, -0.01] * 3))[0], B.EDM1_FALLBACK_SIGMA)
        self.assertIn("rule's fallback", edm1(record([-0.03] * 5), five))   # -0.15 < -1.645 x 0.02 x sqrt(5) = -0.0736
        self.assertIsNone(edm1(record([-0.03] * 5), TABLE), "five closes are under the table's 10")

    def test_the_program_loss_line(self):
        self.assertIn("reached the program loss line $-300.00", edm1(record(GOOD, realized_net="-300"), TABLE))
        self.assertIn("program loss line", edm1(record([0.01], realized_net="-412.50"), TABLE), "at any count")
        self.assertIsNone(edm1(record(GOOD, realized_net="-299.99"), TABLE))

    def test_the_twin_shortfall(self):
        worse = [-16, -16, -16, -16, -16]
        why = edm1(record(GOOD, gaps=worse), TABLE)
        self.assertIn("ran 16.0 bp a side below their replay twins on average over 5 priced closes", why)
        self.assertIsNone(edm1(record(GOOD, gaps=worse[:4]), TABLE), "four priced closes are not enough")
        self.assertIsNone(edm1(record(GOOD, gaps=[-15] * 5), TABLE), "at the line: not above it")
        self.assertIsNone(edm1(record(GOOD, gaps=[40] * 6), TABLE), "fills better than the replay never demote")
        self.assertIsNotNone(edm1(record(GOOD, gaps=[-40, -40, -40, 10, 20]), TABLE), "the mean decides: -18")

    def test_a_record_that_cannot_be_read_is_refused(self):
        for rec in (EquityRecord(n=3, returns=(0.01, 0.02), pnl=D(0), bh_pnl=D(0), probe_sessions=1, realized_net=D(0)),
                    record([0.01, float("nan")]), record([0.01, "0.02"]), record([0.01, True]),
                    record(GOOD, gaps=[float("inf")] * 5)):
            for rule in (edm1, sized_up, sized_sleeve_share):
                if rule is not edm1 and rec.twin_gaps_bp:
                    continue
                with self.assertRaises(ValueError, msg=(rule.__name__, rec)):
                    rule(rec, TABLE)


if __name__ == "__main__":
    unittest.main()
