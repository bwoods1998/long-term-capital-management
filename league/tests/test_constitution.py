import unittest

from league.constitution import CONSTITUTION, PINNED_DIGEST, digest


class ConstitutionTest(unittest.TestCase):
    def test_the_constitution_is_pinned(self):
        """A change to any threshold changes the digest, and this test, the ledger's `ops.started`
        rows and CI's path guard all notice. Only the owner re-pins it."""
        self.assertEqual(digest(), PINNED_DIGEST)

    def test_the_numbers_the_owner_set(self):
        self.assertEqual(CONSTITUTION["budgets"]["sail_month_usd"], "100")
        self.assertEqual(CONSTITUTION["budgets"]["openai_month_usd"], "100")
        self.assertEqual(CONSTITUTION["order_caps"]["max_order_usd"], "75")
        self.assertEqual(CONSTITUTION["rungs"]["2"]["max_position_usd"], "30")  # the learning surge, Sept 21, 2026
        self.assertEqual(CONSTITUTION["rungs"]["3"]["kelly_fraction"], 1.0)  # swing and bunt, Sept 23, 2026
        self.assertEqual(CONSTITUTION["rungs"]["3"]["max_share_of_venue"], 0.6)  # swing and bunt
        self.assertEqual(CONSTITUTION["ladder"]["alpha"], 0.05)  # death's budget
        self.assertEqual(CONSTITUTION["ladder"]["promotion_alpha"], 0.20)  # promotion's budget, swing and bunt
        self.assertEqual(CONSTITUTION["ladder"]["replay"]["min_oos_growth"], -0.0005)  # swing and bunt
        # No probe on a losing family (R5, the close-the-gaps run, Sept 24, 2026: the run's third money-digest change).
        # The forward-first run's M5 (Sept 25, 2026): the hold turns on an 80% bound, one observation a block period.
        self.assertEqual(CONSTITUTION["allocator"]["family_probe"],
                         {"losing_min_blocks": 6, "reseat": "bound_since_demotion", "reseat_confidence": "0.8"})
        # The House live test's pre-registered bounds (the owner, Sept 28, 2026: a new money digest).
        self.assertEqual(CONSTITUTION["options_money"]["house_test"],
                         {"structure_usd": "100", "open": 3, "envelope_usd": "300", "stop_usd": "150", "sessions": 20,
                          "round_trips": 30})
        # The incubator (the owner, Sept 29, 2026, 14:51:12Z; the reading of Sept 30): one lot, at most 4 open, $150 a week
        # net, after a first look of 3 sessions, 10 program closes and 0.80 coverage; at most $75 of maximum loss each since
        # the incubator cap (Oct 8, 2026, under the owner's goal item 4; $50 before it).
        self.assertEqual(CONSTITUTION["options_money"]["incubator"],
                         {"max_loss_usd": "75", "contracts": 1, "max_open": 4, "week_loss_usd": "150",
                          "min_sessions": 3, "min_trades": 10, "min_coverage": "0.80"})

    def test_the_incubator_cap_moved_the_money_digest_to_the_one_the_grant_re_ratifies(self):
        """Fast lane v2 (Oct 7, 2026; the owner's goal item 4): the Probe row (one structure within 10% of E, at most 3 Probe
        positions, the $400 Probe loss budget) moved the money digest (42c4a3af before it, Release B's incubator row) to
        da5c7542 and the full digest (595228a6 before it) to 5edc8956. The incubator cap (Oct 8, 2026, under the same
        goal item) moved only `incubator.max_loss_usd`, $50 -> $75: money digest da5c7542 -> 1665c385, full digest
        5edc8956 -> 5698a2f9. The standing grant re-ratifies on it at the House's start on the owner's deploy
        (league/ops/grant.py)."""
        import copy

        from league.constitution import money_digest

        self.assertEqual(money_digest(), "1665c3858bce937617a339dfa56ae9a38a51e9fd763225ec10a645d3d5bafa08")
        self.assertEqual(PINNED_DIGEST, "5698a2f9a4055ed067128b5804a0fd4c2fd00b9d5b7a0a0eedeef92e29ddfda7")
        # The cap is the only money rule it moved: with the row at $50 again, the money digest is fast lane v2's.
        before = copy.deepcopy(CONSTITUTION)
        before["options_money"]["incubator"]["max_loss_usd"] = "50"
        self.assertEqual(money_digest(before), "da5c7542d7b78f967c12c3b2d98140153026c98b5fea9de27b6cf912eff85694")
        self.assertEqual(CONSTITUTION["options_money"]["probe"],
                         {"max_loss_share": "0.10", "contracts": 1, "open_per_family": 3, "family_share": "0.15",
                          "floor_usd": "0", "max_open": 3, "loss_budget_usd": "400"})

    def test_the_fast_lane_probe_rows_stay_inside_the_goals_bounds(self):
        import copy

        from league.constitution import options_money_problems

        for key, value in (("max_loss_share", "0.1001"), ("contracts", 2), ("contracts", 0), ("max_open", 4),
                           ("max_open", 2.0), ("loss_budget_usd", "400.01"), ("floor_usd", "100.01")):
            changed = copy.deepcopy(CONSTITUTION)
            changed["options_money"]["probe"][key] = value
            self.assertTrue(any(f"probe.{key}" in p for p in options_money_problems(changed)), (key, value))
        for key, value in (("max_open", 0), ("loss_budget_usd", "0"), ("max_loss_share", "0.02")):
            changed = copy.deepcopy(CONSTITUTION)
            changed["options_money"]["probe"][key] = value
            self.assertEqual(options_money_problems(changed), [], (key, value))

    def test_the_incubator_row_may_only_tighten(self):
        import copy

        from league.constitution import options_money_problems

        self.assertEqual(options_money_problems(), [])
        for key, value in (("max_loss_usd", "75.01"), ("max_open", 5), ("week_loss_usd", "150.01"), ("min_sessions", 2),
                           ("min_trades", 9), ("min_coverage", "0.79"), ("contracts", 2), ("contracts", 0),
                           ("max_open", 1.0)):
            changed = copy.deepcopy(CONSTITUTION)
            changed["options_money"]["incubator"][key] = value
            self.assertTrue(any(f"incubator.{key}" in p for p in options_money_problems(changed)), (key, value))
        for key, value in (("max_loss_usd", "0"), ("max_loss_usd", "50"), ("max_open", 0), ("week_loss_usd", "0"), ("min_sessions", 5),
                           ("min_trades", 20), ("min_coverage", "0.9")):
            changed = copy.deepcopy(CONSTITUTION)
            changed["options_money"]["incubator"][key] = value
            self.assertEqual(options_money_problems(changed), [], (key, value))
        changed = copy.deepcopy(CONSTITUTION)
        del changed["options_money"]["incubator"]
        self.assertTrue(any("incubator" in p for p in options_money_problems(changed)))

    def test_sizing_stays_on_the_lower_bound_and_death_keeps_its_budget(self):
        """Whatever the owner's appetite, two properties hold: the scaled rung is never sized above
        full Kelly (on a LOWER bound), and a promotion budget never loosens death."""
        self.assertLessEqual(CONSTITUTION["rungs"]["3"]["kelly_fraction"], 1.0)
        self.assertLessEqual(CONSTITUTION["rungs"]["3"]["max_share_of_venue"], 1.0)
        self.assertLessEqual(CONSTITUTION["ladder"]["alpha"], CONSTITUTION["ladder"]["promotion_alpha"])

    def test_a_changed_threshold_changes_the_digest(self):
        import copy

        changed = copy.deepcopy(CONSTITUTION)
        changed["ladder"]["alpha"] = 0.5
        self.assertNotEqual(digest(changed), PINNED_DIGEST)


if __name__ == "__main__":
    unittest.main()
