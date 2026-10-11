"""THE PRE-REGISTERED SIZING-UP AND DEMOTION RULES of the equity lane (`league/equity/bands.py`, money's functions:
`sized_up`, `sized_sleeve_share`, `edm1`; the constitution's `equity_money.sized` and `.demotion`), on the money table in
force. THE SIZING-UP STEP IS PARKED at that table (`sized.min_trades` 1000: `TheSizingUpStepIsParked`), so the rule as
pre-registered is held on `PRE_REGISTERED`, the same table with the rule's own 20 closes. Invented returns only (no
market figure); standard library only."""

import math
import unittest
from dataclasses import replace
from decimal import Decimal as D

from league import stats
from league.equity import bands as B
from league.equity.bands import EquityRecord, edm1, sized_sleeve_share, sized_up
from league.live.money import EquityTable

TABLE = EquityTable.from_constitution()
#: The Sized sleeve's own arithmetic needs a Probe sleeve UNDER the Sized cap, where the Kelly leg and the cap can be
#: reached: the quarter of E the block carried before the captain's A20 (Oct 11, 2026), stated here as a table of its
#: own. Where the Probe sleeve is the cap itself (`A20`: 0.50) the rule answers the Probe's for every record. The Probe
#: sleeve in force is one of release E5-S's two numbers and no test here names it (`AtTheTableInForce`).
#: THE SIZING-UP RULE AS PRE-REGISTERED: at least 20 real closes. The table in force parks the step at 1000 (the
#: captain's decision on the review of A20's study), so the rule's legs are held on this one.
PRE_REGISTERED = replace(TABLE, sized_min_trades=20)
UNDER_THE_CAP = replace(PRE_REGISTERED, probe_sleeve_share=D("0.25"))
#: A20's design, row by row: the Probe sleeve at the Sized cap's own 0.50.
A20 = replace(TABLE, probe_sleeve_share=D("0.50"), probe_max_programs=3)


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
        ok, why = sized_up(record(GOOD), PRE_REGISTERED)
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
        self.assertTrue(sized_up(first[0], PRE_REGISTERED)[0], "the count's line is 20")
        for rec, said in rest:
            ok, why = sized_up(rec, PRE_REGISTERED)
            self.assertFalse(ok, said)
            self.assertIn(said, why)

    def test_the_bound_is_the_tables_confidence(self):
        rec = record(alternating(0.0012, 0.006, 24))
        bounds = stats.mean_bounds(list(rec.returns), 0.2)
        self.assertGreater(bounds["lcb"], 0)
        self.assertTrue(sized_up(rec, PRE_REGISTERED)[0])
        strict = replace(PRE_REGISTERED, sized_confidence=0.99)
        self.assertLess(stats.mean_bounds(list(rec.returns), 0.01)["lcb"], 0)
        self.assertFalse(sized_up(rec, strict)[0])
        self.assertTrue(sized_up(record(GOOD, bh_pnl=None), replace(PRE_REGISTERED, sized_beat_bh=False))[0],
                        "beat_bh off (never, by the bounds) would not read the buy-and-hold")


#: Records across the rule's legs: a strong bound (the cap), a Kelly between a quarter and a half of E, a bound barely
#: above zero, a losing record, one close (no bound) and none.
BETWEEN = alternating(0.0025, 0.03, 400)
RECORDS = (GOOD, BETWEEN, alternating(0.0002, 0.06, 40), alternating(-0.01, 0.02, 40), [0.01], [])


class SizedSleeve(unittest.TestCase):
    """The rule as pre-registered: max(the Probe's sleeve, min(quarter Kelly on the lower bound, the Sized cap)), on a
    table whose Probe sleeve is under the cap (`UNDER_THE_CAP`)."""

    def test_quarter_kelly_on_the_lower_bound_between_the_probes_and_the_cap(self):
        bounds = stats.mean_bounds(BETWEEN, 0.2)
        kelly = stats.quarter_kelly(bounds["lcb"], bounds["sd"] ** 2, fraction=0.25, cap=0.5)
        self.assertTrue(0.25 < kelly < 0.5, kelly)
        share = sized_sleeve_share(record(BETWEEN), UNDER_THE_CAP)
        self.assertEqual(share, D(repr(kelly)).quantize(D("0.0001"), rounding="ROUND_DOWN"))

    def test_never_above_the_cap_nor_below_the_probes(self):
        self.assertEqual(sized_sleeve_share(record(GOOD), UNDER_THE_CAP), D("0.50"), "a strong bound is capped at 0.50 x E")
        self.assertEqual(sized_sleeve_share(record(alternating(0.0002, 0.06, 40)), UNDER_THE_CAP), D("0.25"),
                         "the Probe's floor")
        self.assertEqual(sized_sleeve_share(record(alternating(-0.01, 0.02, 40)), UNDER_THE_CAP), D("0.25"))
        self.assertEqual(sized_sleeve_share(record([0.01]), UNDER_THE_CAP), D("0.25"),
                         "one close: no bound, the Probe's share")


class AtTheTableInForce(unittest.TestCase):
    """THE SIZED SLEEVE AT THE TABLE IN FORCE, whatever its two numbers (release E5-S): `sized.sleeve_share` stays 0.50
    and is never under `probe.sleeve_share`, and the rule never sizes under the Probe's nor above the cap. WHERE THE
    PROBE SLEEVE IS 0.50 (the captain's A20, Oct 11, 2026: `A20`) the cap EQUALS the floor, so a Sized program keeps
    the Probe sleeve."""

    def test_the_table_in_force(self):
        from league.tests.equity_design import CANDIDATES, in_force

        seats, sleeve = in_force()
        self.assertIn((seats, sleeve), CANDIDATES)
        self.assertEqual((TABLE.probe_sleeve_share, TABLE.probe_max_programs), (D(sleeve), seats))
        self.assertEqual(TABLE.sized_sleeve_share, D("0.50"), "the row no design moves")
        self.assertGreaterEqual(TABLE.sized_sleeve_share, TABLE.probe_sleeve_share, "the cap is never under the floor")

    def test_a_sized_programs_sleeve_is_the_probes_whatever_its_record_where_the_probe_sleeve_is_the_cap(self):
        self.assertEqual(A20.sized_sleeve_share, A20.probe_sleeve_share)
        for returns in RECORDS:
            self.assertEqual(sized_sleeve_share(record(returns), A20), D("0.50"), returns[:2])
        # ...the record that would size up among them (every leg of the pre-registered rule met), and one whose
        # quarter Kelly alone is far past E.
        self.assertTrue(sized_up(record(GOOD), PRE_REGISTERED)[0])
        bounds = stats.mean_bounds(GOOD, 0.2)
        self.assertGreater(stats.quarter_kelly(bounds["lcb"], bounds["sd"] ** 2, fraction=0.25, cap=10.0), 1.0)
        self.assertEqual(sized_sleeve_share(record(GOOD), A20), D("0.50"), "the cap, then the Probe's floor: never E")

    def test_at_the_table_in_force_it_is_between_the_probes_and_the_cap(self):
        """The same rule on the rows in force: every record's share is at least the Probe's and at most the cap; the
        record whose quarter Kelly is past E gets the cap; a record that sizes nothing gets the Probe's."""
        floor, cap = TABLE.probe_sleeve_share, TABLE.sized_sleeve_share
        for returns in RECORDS:
            share = sized_sleeve_share(record(returns), TABLE)
            self.assertTrue(floor <= share <= cap, (returns[:2], share))
        self.assertEqual(sized_sleeve_share(record(GOOD), TABLE), cap)
        self.assertEqual(sized_sleeve_share(record([0.01]), TABLE), floor, "one close: no bound, the Probe's share")
        self.assertEqual(sized_sleeve_share(record(alternating(-0.01, 0.02, 40)), TABLE), floor)

    def test_a_sized_sleeve_is_never_below_the_probes_at_any_probe_sleeve_inside_the_bound(self):
        """Never under the Probe's, and never above the larger of the Probe's and the Sized cap: at each Probe sleeve
        from zero to the bound's loose end, for every record."""
        from league.constitution import EQUITY_MONEY_BOUNDS

        self.assertEqual(EQUITY_MONEY_BOUNDS["probe.sleeve_share"], ("0", "0.50"))
        for probe in ("0", "0.10", "0.25", "0.4999", "0.50"):
            table = replace(TABLE, probe_sleeve_share=D(probe))
            for returns in RECORDS:
                share = sized_sleeve_share(record(returns), table)
                self.assertGreaterEqual(share, D(probe), (probe, returns[:2]))
                self.assertLessEqual(share, max(D(probe), table.sized_sleeve_share), (probe, returns[:2]))
            # A strong record reaches the cap while the Probe's is under it, and is the Probe's from there on.
            self.assertEqual(sized_sleeve_share(record(GOOD), table), max(D(probe), D("0.50")), probe)


class TheSizingUpStepIsParked(unittest.TestCase):
    """PARKED (the captain's decision on the review of A20's study, Oct 11, 2026): `equity_money.sized.min_trades` is
    1000, inside its bound and a tightening. The owner's loss budget ($400 net in any rolling 20 sessions, $800 net in
    total) covers all real money, and a Sized program's lots carry no Probe mark, so their closes would sit outside
    the Probe window, the total and the program's -$300 line. With 1000 no equity program is Sized, at any Probe
    sleeve. The rule itself stays as pre-registered."""

    WINNING = alternating(0.004, 0.006, 998) + [0.004]          # 999 winning real closes, every other leg met

    def test_the_row_in_force_and_its_bound(self):
        from league.constitution import CONSTITUTION, EQUITY_MONEY_BOUNDS

        self.assertEqual(CONSTITUTION["equity_money"]["sized"]["min_trades"], 1000)
        self.assertEqual(TABLE.sized_min_trades, 1000)
        self.assertEqual(EQUITY_MONEY_BOUNDS["sized.min_trades"], ("20", "1000"), "inside its bound, at its tight end")
        # Nothing else of the pre-registered rule moved.
        self.assertEqual((TABLE.sized_confidence, TABLE.sized_kelly_fraction, TABLE.sized_sleeve_share, TABLE.sized_beat_bh,
                          TABLE.sized_min_probe_sessions), (0.80, 0.25, D("0.50"), True, 5))

    def test_a_program_with_999_winning_real_closes_is_still_probe(self):
        rec = record(self.WINNING, pnl="5000", bh_pnl="20", probe_sessions=400, realized_net="5000")
        self.assertEqual(rec.n, 999)
        self.assertTrue(sized_up(rec, PRE_REGISTERED)[0], "every leg of the pre-registered rule is met")
        ok, why = sized_up(rec, TABLE)
        self.assertFalse(ok)
        self.assertEqual(why, "999 real closes, under the 1000 sizing up needs")
        row = {"band": "probe", "holdout_passed": True}
        self.assertEqual(B.next_band(row, rec, TABLE, seat_free=True), ("probe", why))
        self.assertEqual(B.next_band(row, rec, PRE_REGISTERED, seat_free=True)[0], "sized", "what parking holds back")

    def test_no_record_the_first_weeks_can_hold_sizes_up(self):
        for n in (20, 24, 100, 500, 998):
            rec = record(alternating(0.004, 0.006, n), pnl="5000", probe_sessions=400)
            self.assertFalse(sized_up(rec, TABLE)[0], n)
            self.assertTrue(sized_up(rec, PRE_REGISTERED)[0], n)


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
        # Equal returns whose rounding leaves a tiny sd (the built-in sum on Python 3.11): still no sd of its own.
        noisy = [-0.01 + (1e-18 if i % 2 else -1e-18) for i in range(10)]
        self.assertEqual(B.edm1_sigma(record(noisy))[0], B.EDM1_FALLBACK_SIGMA)
        for equal in (0.1, 0.07, 1 / 3, -0.0123456789):
            self.assertEqual(B.edm1_sigma(record([equal] * 10))[0], B.EDM1_FALLBACK_SIGMA, equal)
        # Nine closes: the record's own sd is not yet read; with the table's line at 5 the fallback is the sigma.
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
