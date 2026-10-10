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

    def test_the_probe_total_at_800_moved_the_money_digest_to_the_one_the_grant_re_ratifies(self):
        """Fast lane v2 (Oct 7, 2026; the owner's goal item 4): the Probe row (one structure within 10% of E, at most 3 Probe
        positions, the $400 Probe loss budget) moved the money digest (42c4a3af before it, Release B's incubator row) to
        da5c7542 and the full digest (595228a6 before it) to 5edc8956. The incubator cap (Oct 8, 2026, under the same
        goal item) moved only `incubator.max_loss_usd`, $50 -> $75: money digest da5c7542 -> 1665c385, full digest
        5edc8956 -> 5698a2f9. Release L-D (Oct 9, 2026, under the same goal item and the owner's goal as re-set that day,
        item 4) moved only the Probe row: `max_open` 3 -> 8 and the new `loss_basis` "net", `demotion` "dm1", and THE
        ROLLING PROBE BUDGET's `loss_window_sessions` 20 and `loss_total_usd` "400" (the operator's setting of Oct 9 inside
        the owner's $800 ceiling): money digest 1665c385 -> 0310779c, full digest 5698a2f9 -> ca89ff8a (b212d4e6 /
        4a1705b6 on the branch before the rolling budget, fdf2ac7c / 0adb4f0e with an $800 total; neither deployed).
        Its CON-only rollback (`loss_basis` "gross", `max_open` 3, `demotion` "dm0", `loss_total_usd` "400",
        `loss_window_sessions` 2000) is money digest 320899d6, full digest c9d8ef5b, digests of their own (the new keys
        stay). THE PROBE TOTAL AT $800 (Oct 10, 2026; PREREG-T, under the owner's goal as re-set on Oct 9, item 4)
        moved only `loss_total_usd`, "400" -> "800", the owner's ceiling: money digest 0310779c -> fdf2ac7c, full digest
        ca89ff8a -> 0adb4f0e (the $800 pair named above); its rollback, `loss_total_usd` "400", is L-D's pair again. The
        standing grant re-ratifies on each at the House's start on the owner's deploy (league/ops/grant.py)."""
        import copy

        from league.constitution import money_digest

        self.assertEqual(money_digest(), "fdf2ac7c1a446e39df9e27c8626fb86a954a3f5a939460406507a9b735f1d4c7")
        self.assertEqual(PINNED_DIGEST, "0adb4f0ed7d9f20fc05cb3ce73590b5a2dfdfe38e5d6aa6759e071d1beb4d5b2")
        # The $800 total is the only money rule it moved: at "400", the money digest and the full digest are L-D's.
        ld = copy.deepcopy(CONSTITUTION)
        ld["options_money"]["probe"]["loss_total_usd"] = "400"
        self.assertEqual(money_digest(ld), "0310779c2f58eaf453835f1c989f130cf92a74198198b624cf021298a9e43945")
        self.assertEqual(digest(ld), "ca89ff8af1dc45d58e3b6af3b8eba4f82afa4d0d73b9d2fb5d28e6d4d749aae3")
        # L-D's rows are the only money rules it moved: without them, the money digest is the incubator cap's.
        before = copy.deepcopy(ld)
        probe = before["options_money"]["probe"]
        del probe["loss_basis"], probe["demotion"], probe["loss_window_sessions"], probe["loss_total_usd"]
        probe["max_open"] = 3
        self.assertEqual(money_digest(before), "1665c3858bce937617a339dfa56ae9a38a51e9fd763225ec10a645d3d5bafa08")
        self.assertEqual(digest(before), "5698a2f9a4055ed067128b5804a0fd4c2fd00b9d5b7a0a0eedeef92e29ddfda7")
        # And with the incubator's row at $50 again, it is fast lane v2's.
        before["options_money"]["incubator"]["max_loss_usd"] = "50"
        self.assertEqual(money_digest(before), "da5c7542d7b78f967c12c3b2d98140153026c98b5fea9de27b6cf912eff85694")
        # The CON-only rollback: its own digest, which the grant re-ratifies on the owner's deploy like any other.
        from league.tests.money_fakes import FAST_LANE_V2, constitution

        self.assertEqual(money_digest(constitution(**FAST_LANE_V2)),
                         "320899d675059182509a62b67d122afd2fdc54b08c59b2053a684d88fc8b55f2")
        self.assertEqual(digest(constitution(**FAST_LANE_V2)),
                         "c9d8ef5bd5e55544884924c8ef0c309e03d89fd230945f346103db3bea18c31f")
        self.assertEqual(CONSTITUTION["options_money"]["probe"],
                         {"max_loss_share": "0.10", "contracts": 1, "open_per_family": 3, "family_share": "0.15",
                          "floor_usd": "0", "max_open": 8, "loss_budget_usd": "400", "loss_window_sessions": 20,
                          "loss_total_usd": "800", "loss_basis": "net", "demotion": "dm1"})

    def test_the_fast_lane_probe_rows_stay_inside_the_goals_bounds(self):
        import copy

        from league.constitution import options_money_problems

        for key, value in (("max_loss_share", "0.1001"), ("contracts", 2), ("contracts", 0), ("max_open", 9),
                           ("max_open", 2.0), ("max_open", 8.0), ("loss_budget_usd", "400.01"), ("floor_usd", "100.01"),
                           ("loss_basis", "Net"), ("loss_basis", ""), ("loss_basis", "NET"), ("loss_basis", " net"),
                           ("loss_basis", None), ("loss_basis", True), ("loss_basis", 1), ("loss_basis", "hwm"),
                           ("demotion", "DM1"), ("demotion", ""), ("demotion", "dm2"), ("demotion", None),
                           ("demotion", 1), ("demotion", ["dm1"]), ("loss_window_sessions", 19),
                           ("loss_window_sessions", 2001), ("loss_window_sessions", 20.0), ("loss_window_sessions", "20.5"),
                           ("loss_window_sessions", None), ("loss_total_usd", "800.01"), ("loss_total_usd", "-1"),
                           ("loss_total_usd", None)):
            changed = copy.deepcopy(CONSTITUTION)
            changed["options_money"]["probe"][key] = value
            self.assertTrue(any(f"probe.{key}" in p for p in options_money_problems(changed)), (key, value))
        for key in ("loss_basis", "demotion", "loss_window_sessions", "loss_total_usd"):   # missing: refused, no default
            changed = copy.deepcopy(CONSTITUTION)
            del changed["options_money"]["probe"][key]
            self.assertTrue(any(f"probe.{key}" in p for p in options_money_problems(changed)), key)
        for key, value in (("max_open", 0), ("max_open", 3), ("max_open", 8), ("loss_budget_usd", "0"),
                           ("max_loss_share", "0.02"), ("loss_basis", "gross"), ("loss_basis", "net"),
                           ("demotion", "dm0"), ("demotion", "dm1"), ("loss_window_sessions", 20),
                           ("loss_window_sessions", 2000), ("loss_total_usd", "0"), ("loss_total_usd", "800")):
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
