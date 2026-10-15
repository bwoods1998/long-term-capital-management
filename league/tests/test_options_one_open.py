"""ONE OPEN STRUCTURE A PROBE FAMILY (Oct 15, 2026; `options_money.probe.open_per_family` 3 -> 1, the constitution's
comment above `options_money`): the row in force, its bound, what `money.plan_open` does with it, and the digests it
moved (the older pins still hold with the row set back). Standard library only."""

import copy
import unittest
from decimal import Decimal as D

from league.constitution import CONSTITUTION, OPTIONS_MONEY_BOUNDS, PINNED_DIGEST, digest, money_digest, options_money_problems
from league.live import money as M
from league.tests import equity_design as X

E = D("2000")


class OneOpenStructure(unittest.TestCase):
    def setUp(self):
        self.t = M.Table.from_constitution()

    def plan(self, unit, **exposure):
        values = {k: (v if k in ("family_open", "probe_open") else D(str(v))) for k, v in exposure.items()}
        return M.plan_open(self.t, band="probe", tuition=False, equity=E, unit=D(str(unit)), fwd=None,
                           exposure=M.Exposure(**values))

    def test_the_row_is_one_inside_its_bound(self):
        self.assertEqual(CONSTITUTION["options_money"]["probe"]["open_per_family"], 1)
        self.assertEqual(OPTIONS_MONEY_BOUNDS["probe.open_per_family"], ("1", "5"), "the row sits at the bound's tight end")
        self.assertEqual(self.t.probe_open, 1)
        self.assertEqual(options_money_problems(), [])

    def test_a_second_structure_of_the_family_waits_for_the_first(self):
        # One long call, $90 of maximum loss with its fees, at E = $2,000 (the cap: $200).
        self.assertEqual(self.plan("90", probe_open=4, probe_at_risk="260", probe_realized="40").qty, 1)
        held = self.plan("90", family_open=1, family_loss="90", probe_open=5, probe_at_risk="260",
                         probe_realized="40")
        self.assertEqual(held.qty, 0)
        self.assertIn("the most a Probe family holds is 1", held.reason)
        # Another family is not held by this one's structure.
        self.assertEqual(self.plan("90", family_open=0, probe_open=5, probe_at_risk="350",
                                   probe_realized="40").qty, 0, "the $400 window still binds first: 40 + 350 + 90")
        self.assertEqual(self.plan("50", family_open=0, probe_open=5, probe_at_risk="260", probe_realized="40").qty, 1)

    def test_at_three_the_family_would_hold_three(self):
        c = copy.deepcopy(CONSTITUTION)
        c["options_money"]["probe"]["open_per_family"] = 3
        t3 = M.Table.from_constitution(c)

        def at3(family_loss):
            values = dict(family_open=2, family_loss=D(family_loss), probe_open=6, probe_at_risk=D(family_loss),
                          probe_realized=D("0"))
            return M.plan_open(t3, band="probe", tuition=False, equity=E, unit=D("100"), fwd=None,
                               exposure=M.Exposure(**values))
        self.assertEqual(at3("176").qty, 1, "at 3 a third $100 call goes while the family holds $176")
        self.assertEqual(at3("210").qty, 0, "the family share (0.15 x E = $300) stops it at $210 held")
        held = self.plan("100", family_open=2, family_loss="176", probe_open=6, probe_at_risk="176",
                         probe_realized="0")
        self.assertEqual(held.qty, 0)
        self.assertIn("the most a Probe family holds is 1", held.reason)

    def test_the_digests_moved_once_and_the_older_pins_still_hold_with_the_row_set_back(self):
        self.assertEqual((money_digest(), PINNED_DIGEST), X.DIGESTS[X.in_force()])
        self.assertEqual(digest(), PINNED_DIGEST)
        for pair in X.CANDIDATES:
            at = X.constitution_at(*pair)
            self.assertEqual((money_digest(at), digest(at)), X.DIGESTS[pair], pair)
            back = X.before_opf1(at)
            self.assertEqual((money_digest(back), digest(back)), X.DIGESTS_E4S2[pair], f"{pair}: before the row")
        self.assertEqual(set(X.DIGESTS.values()) & set(X.DIGESTS_E4S2.values()), set(), "every pin moved with the row")
        # Release U's own pins (main aec0c8a5) are the E4S2 pins of A32's pair.
        self.assertEqual(X.DIGESTS_E4S2[(6, "0.50")],
                         ("de5ed74e5180f9ed6316f46b45941a57d00cacb2b12716738d095fccf909f582",
                          "111ede85f9b401c9af74f0f1967f9390c37ccd35a47f6fb048257db3c691ce6f"))


if __name__ == "__main__":
    unittest.main()
