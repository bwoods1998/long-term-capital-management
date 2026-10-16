"""THE OPTIONS SIZING-UP STEP IS PARKED (C2 (A45) of the scaling plan, its options row; the constitution's comment above
`options_money`): `options_money.sized.min_trades` 20 -> 1000 at its bound's tight end, so no options family reaches
Sized, and `OPTIONS_MONEY_BOUNDS` `probe.max_loss_share`'s tight end 0.02 -> 0.005, so a later step's row may hold one
Probe structure at today's dollars while E grows. Both are tightenings and neither changes a size at today's E: the
row moves the money digest and the constitution digest once (the older pins still hold with it set back), the bound
moves none. Every figure is synthetic (no account's). Standard library only."""

import copy
import dataclasses
import unittest
from decimal import Decimal as D

from league.constitution import (CONSTITUTION, OPTIONS_MONEY_BOUNDS, PINNED_DIGEST, digest, money_digest,
                                 options_money_problems)
from league.live import money as M
from league.tests import equity_design as X

#: Synthetic sizing equities (dollars): none is the account's.
EQUITIES = (D("1000"), D("5000"), D("40000"))


def row(**kw):
    base = {"family": "f", "band": "probe", "structure": "debit_vertical", "holdout_passed": True,
            "typical_max_loss_usd": 50.0}
    base.update(kw)
    return base


def record(n: int, *, real: int = 10) -> M.Forward:
    """A strong forward record of `n` decision days, the last `real` of them real Probe trades: a positive mean and a
    positive lower bound at every n here, and real trades that win (never `real_bad`)."""
    rows = []
    for i in range(n):
        source = "real" if i >= n - real else "shadow"
        rows.append({"day": f"d{i:05d}", "source": source, "pnl": (30.0 if i % 4 else -10.0), "max_loss": 100.0})
    return M.forward_stats(rows, 0.8)


class TheRowIsParked(unittest.TestCase):
    def test_the_row_is_a_thousand_at_its_bounds_tight_end(self):
        self.assertEqual(CONSTITUTION["options_money"]["sized"]["min_trades"], 1000)
        self.assertEqual(OPTIONS_MONEY_BOUNDS["sized.min_trades"], ("20", "1000"), "inside its bound, at its tight end")
        self.assertEqual(M.Table.from_constitution().sized_min_trades, 1000)
        self.assertEqual(options_money_problems(), [])
        # The switch back (the rule's own 20) stays allowed; one past either end is refused, as before.
        for count, ok in ((1000, True), (20, True), (1001, False), (19, False), (1000.0, False)):
            c = copy.deepcopy(CONSTITUTION)
            c["options_money"]["sized"]["min_trades"] = count
            self.assertEqual(not any("sized.min_trades" in p for p in options_money_problems(c)), ok, count)

    def test_no_options_family_reaches_sized(self):
        """A record that the rule as pre-registered (20 forward trades) sizes up is held at Probe by the park: at 999
        trades too, and a family the swarm holds at Sized is read back to Probe (`band_for`), whatever its record."""
        t = M.Table.from_constitution()
        pre = dataclasses.replace(t, sized_min_trades=20)
        for n in (20, 25, 200, 999):
            f = record(n)
            self.assertTrue(f.mean > 0 and f.lcb > 0 and not f.real_bad, n)
            self.assertTrue(M.sized_ok(pre, f), n)
            self.assertFalse(M.sized_ok(t, f), n)
            for band in ("probe", "sized"):
                got, why = M.band_for(t, row(band=band), D("5000"), f, probe_sessions=5)
                self.assertEqual(got, "probe", (n, band, why))
                self.assertEqual(M.band_for(pre, row(band=band), D("5000"), f, probe_sessions=5)[0], "sized", (n, band))
        # The count is the only check it moves: at 1000 the rule's other checks decide, as written.
        self.assertTrue(M.sized_ok(t, record(1000)))
        self.assertEqual(M.band_for(t, row(), D("5000"), record(1000), probe_sessions=5)[0], "sized")

    def test_nothing_changes_size_at_todays_equity(self):
        """A Probe open is planned the same with the row parked or not: the Probe's cap, its family share, the window
        and the total read no Sized row. Only a Sized open differs, and none is reached (above)."""
        t = M.Table.from_constitution()
        before = M.Table.from_constitution(X.before_options_park())
        self.assertEqual(dataclasses.replace(before, sized_min_trades=1000), t, "the count is the only row that moved")
        exposure = M.Exposure(family_open=0, probe_open=2, probe_at_risk=D("120"), probe_realized=D("30"))
        for E in EQUITIES:
            self.assertEqual(M.probe_cap(t, E), D("0.10") * E)
            self.assertEqual(M.probe_room(t, E), M.probe_room(before, E))
            for unit in ("10", "45", "99.99", "150"):
                a = M.plan_open(t, band="probe", tuition=False, equity=E, unit=D(unit), fwd=None, exposure=exposure)
                b = M.plan_open(before, band="probe", tuition=False, equity=E, unit=D(unit), fwd=None, exposure=exposure)
                self.assertEqual(a, b, (E, unit))


class TheBoundsTightEnd(unittest.TestCase):
    def test_the_tight_end_is_half_a_percent_and_the_loose_end_the_goals_ten(self):
        self.assertEqual(OPTIONS_MONEY_BOUNDS["probe.max_loss_share"], ("0.005", "0.10"))
        self.assertEqual(CONSTITUTION["options_money"]["probe"]["max_loss_share"], "0.10", "the row in force is unchanged")
        for value, ok in (("0.005", True), ("0.01", True), ("0.0199", True), ("0.02", True), ("0.10", True),
                          ("0.0049", False), ("0.004", False), ("0", False), ("-0.01", False), ("0.1001", False),
                          ("NaN", False)):
            c = copy.deepcopy(CONSTITUTION)
            c["options_money"]["probe"]["max_loss_share"] = value
            self.assertEqual(not any("probe.max_loss_share" in p for p in options_money_problems(c)), ok, value)
            if ok:
                self.assertEqual(M.Table.from_constitution(c).probe_share, D(value))
            else:
                with self.assertRaises(ValueError):
                    M.Table.from_constitution(c)

    def test_a_tighter_row_holds_one_structure_at_the_same_dollars_while_e_grows(self):
        """What the extension is for (the plan's 3.3): a row of `share` x a larger E is the same dollars of maximum loss
        a structure as 0.10 x today's. Synthetic: 0.10 of 1000 is 0.005 of 20000, both 100."""
        small = M.Table.from_constitution()
        c = copy.deepcopy(CONSTITUTION)
        c["options_money"]["probe"]["max_loss_share"] = "0.005"
        tight = M.Table.from_constitution(c)
        self.assertEqual(M.probe_cap(small, D("1000")), M.probe_cap(tight, D("20000")))
        self.assertEqual(M.probe_cap(tight, D("20000")), D("100"))
        self.assertTrue(M.fits_probe(tight, D("20000"), D("100")))
        self.assertFalse(M.fits_probe(tight, D("20000"), D("100.01")))


class TheDigests(unittest.TestCase):
    def test_the_row_moved_both_digests_once_and_the_bound_moved_none(self):
        self.assertEqual((money_digest(), PINNED_DIGEST), X.DIGESTS[X.in_force()])
        self.assertEqual(digest(), PINNED_DIGEST)
        for pair in X.CANDIDATES:
            at = X.constitution_at(*pair)
            self.assertEqual((money_digest(at), digest(at)), X.DIGESTS[pair], pair)
            back = X.before_options_park(at)
            self.assertEqual((money_digest(back), digest(back)), X.DIGESTS_OPF1[pair], f"{pair}: before the park")
        self.assertEqual(set(X.DIGESTS.values()) & set(X.DIGESTS_OPF1.values()), set(), "every pin moved with the row")
        # The tree before C2 (main e136c251) is on the OPF1 pins of the pair in force: with the row set back the digests
        # are exactly its, though the bound's tight end has moved, because the bounds are no row of the constitution.
        self.assertEqual(X.DIGESTS_OPF1[(6, "0.33")],
                         ("cfcc94b14973a174c522928012df1b3aea97dabda171679b1566841ecdb2de0c",
                          "60796aed0c82235b802fa925f865daf10d6eca6d355ddd80ae044380edd4d93d"))
        # C2's own pins of the pair in force (C3's Scaled block, `equity_money.scaled`, moved them once more: with it left
        # out, `before_scaled`, the digests are C2's exactly).
        self.assertEqual(X.DIGESTS_C2[(6, "0.33")],
                         ("4cd610a542397fbc78cade6f0d3fd9054faab2ea8395c07b19160e200c840014",
                          "18636b3f13d5746d25b80a06a0413d1ffccf675968f0b5bed9e94b1d9ac0265e"))
        for pair in X.CANDIDATES:
            back = X.before_scaled(X.constitution_at(*pair))
            self.assertEqual((money_digest(back), digest(back)), X.DIGESTS_C2[pair], f"{pair}: before the Scaled block")
        # Every older table's helper sets the row back too: one open structure a Probe family's pins still hold.
        for pair in X.CANDIDATES:
            back = X.before_opf1(X.constitution_at(*pair))
            self.assertEqual((money_digest(back), digest(back)), X.DIGESTS_E4S2[pair], pair)


if __name__ == "__main__":
    unittest.main()
