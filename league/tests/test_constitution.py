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
        # The incubator (the owner, Sept 29, 2026, 14:51:12Z; the reading of Sept 30): one lot, at most $50 of maximum loss
        # each, at most 4 open, $150 a week net, after a first look of 3 sessions, 10 program closes and 0.80 coverage.
        self.assertEqual(CONSTITUTION["options_money"]["incubator"],
                         {"max_loss_usd": "50", "contracts": 1, "max_open": 4, "week_loss_usd": "150",
                          "min_sessions": 3, "min_trades": 10, "min_coverage": "0.80"})

    def test_money_rules_v3_moved_the_money_digest_to_the_one_the_owner_ratifies(self):
        """Release V3-A's money digest (42c4a3af, release B's incubator row, before it) and the full digest (595228a6
        before it): the credit types among `options_money.real_types` (D3). The grant is ratified again on this one right
        after the deploy (the standing grant, or the owner's `--ratify`)."""
        from league.constitution import money_digest

        self.assertEqual(money_digest(), "e4a5f7a6781645fddc91ac82053ea7fdaf03dc3d92c933abf4f452aa3a2254a3")
        self.assertEqual(PINNED_DIGEST, "545759375c479f19d684d112c106da9b10c3a9b410c46bb97bfc7bc4a2bea742")

    def test_money_rules_v3_open_the_credit_types_gated_by_equity(self):
        """D3: the three credit types are real types, gated by `credit_min_equity_usd` ($2,000, pinned: no other value is
        inside its bounds), and no type outside the venue's one-order closes and the long singles may join them."""
        import copy

        from league.constitution import OPTIONS_CREDIT_TYPES, OPTIONS_MONEY_BOUNDS, options_money_problems

        table = CONSTITUTION["options_money"]
        self.assertTrue(set(OPTIONS_CREDIT_TYPES) <= set(table["real_types"]))
        self.assertEqual(table["credit_types"], list(OPTIONS_CREDIT_TYPES))
        self.assertEqual(table["credit_min_equity_usd"], "2000")
        self.assertEqual(OPTIONS_MONEY_BOUNDS["credit_min_equity_usd"], ("2000", "2000"))
        for value in ("1999.99", "0", "2000.01"):
            changed = copy.deepcopy(CONSTITUTION)
            changed["options_money"]["credit_min_equity_usd"] = value
            self.assertTrue(any("credit_min_equity_usd" in p for p in options_money_problems(changed)), value)
        for extra in ("calendar", "diagonal", "long_straddle", "long_strangle", "short_put", "naked_call"):
            changed = copy.deepcopy(CONSTITUTION)
            changed["options_money"]["real_types"].append(extra)
            self.assertTrue(any("real_types" in p for p in options_money_problems(changed)), extra)

    def test_the_incubator_row_may_only_tighten(self):
        import copy

        from league.constitution import options_money_problems

        self.assertEqual(options_money_problems(), [])
        for key, value in (("max_loss_usd", "50.01"), ("max_open", 5), ("week_loss_usd", "150.01"), ("min_sessions", 2),
                           ("min_trades", 9), ("min_coverage", "0.79"), ("contracts", 2), ("contracts", 0),
                           ("max_open", 1.0)):
            changed = copy.deepcopy(CONSTITUTION)
            changed["options_money"]["incubator"][key] = value
            self.assertTrue(any(f"incubator.{key}" in p for p in options_money_problems(changed)), (key, value))
        for key, value in (("max_loss_usd", "0"), ("max_open", 0), ("week_loss_usd", "0"), ("min_sessions", 5),
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
