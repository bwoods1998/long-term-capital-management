import json
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
        standing grant re-ratifies on each at the House's start on the owner's deploy (league/ops/grant.py). Release E1
        (the equity lane) moved both again by adding `equity_money` (`test_the_equity_lane_moved_the_money_digest`):
        these are the digests of the constitution without that block, as each release before E1 had it."""
        import copy

        from league.constitution import money_digest

        t800 = copy.deepcopy(CONSTITUTION)
        del t800["equity_money"]
        t800["options_money"]["probe"]["open_per_family"] = 3     # every release before E1 held three a family
        self.assertEqual(money_digest(t800), "fdf2ac7c1a446e39df9e27c8626fb86a954a3f5a939460406507a9b735f1d4c7")
        self.assertEqual(digest(t800), "0adb4f0ed7d9f20fc05cb3ce73590b5a2dfdfe38e5d6aa6759e071d1beb4d5b2")
        # The $800 total is the only money rule it moved: at "400", the money digest and the full digest are L-D's.
        ld = copy.deepcopy(t800)
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

        rollback = constitution(**FAST_LANE_V2)
        del rollback["equity_money"]
        self.assertEqual(money_digest(rollback), "320899d675059182509a62b67d122afd2fdc54b08c59b2053a684d88fc8b55f2")
        self.assertEqual(digest(rollback), "c9d8ef5bd5e55544884924c8ef0c309e03d89fd230945f346103db3bea18c31f")
        self.assertEqual(CONSTITUTION["options_money"]["probe"],
                         {"max_loss_share": "0.10", "contracts": 1, "open_per_family": 1, "family_share": "0.15",
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

    def test_the_equity_lane_moved_the_money_digest_to_the_one_the_grant_re_ratifies(self):
        """Release E1 (the equity lane, Oct 2026; league/equity/INTERFACES.md 7.1) added the constitution's `equity_money`
        and moved nothing else: money digest fdf2ac7c (THE PROBE TOTAL AT $800) -> 7e41909a, full digest 0adb4f0e ->
        e909eb10, the block as E1 deploys it WITH THE PROBE SLEEVE AT 0.50 AND THE SIZING-UP STEP PARKED (the
        captain's A20 and his decision on its study's review, Oct 11, 2026: one money-digest move with the block). With
        the sleeve at the 0.25 and the 20 closes it had on the branch before A20 the pair was ad8c761b / 65b0e025,
        never deployed; A20's rollback, the sleeve alone back at 0.25, is 3a7c52d5 / 6d19fddd. Every row of the
        block is a money rule (none is in `RISK_FREE`), so each moves the money digest and the standing grant
        re-ratifies on the owner's deploy (league/tests/test_equity_money.py). THE SWITCH SHIPS ON (the captain's
        A10.2): `enabled` True is the block as deployed; its stop, `enabled` False, is a digest of its own (23f17a14),
        ratified the same way; the rollback to a release before E1 brings fdf2ac7c back.

        SINCE RELEASE E5-S THE SEATS AND THE SLEEVE ARE TWO NUMBERS (`set_design SEATS SLEEVE`): every figure above
        is A20's design's (three seats at 0.50), read here with the two rows at that design (`reference`) whatever
        pair is in force, so `set_design 3 0.50` is shown to bring E1's digests back to the last hex; the pair in
        force is one of the pre-registered grid's, and its own digests are the grid's pins
        (league/tests/equity_design.py `DIGESTS`), `PINNED_DIGEST` among them. No other row may move with it.

        SINCE RELEASE E5-A THE TABLE CARRIES THE SEAT RULE'S BLOCK (`equity_money.probe.seat`, the captain's A24), a
        money rule like every other row: it moved every pair's digests once, by itself. So each pair WITH THE BLOCK
        LEFT OUT is still on release E5-S's pin (`DIGESTS_E5S`), and E1's own digests are read at A20's design with
        the block left out (`e1`). The rollback of the pair, `set_design 3 0.50`, lands on the reference's pin of
        `DIGESTS` (the block stays); the rollback of the rule is the block's own row, "first-come"."""
        import copy

        from league.constitution import RISK_FREE, money_digest
        from league.equity import config
        from league.tests.equity_design import (CANDIDATES, DIGESTS, DIGESTS_E5S, REFERENCE, constitution_at, e1,
                                                in_force, without_seat)

        # RELEASE E4's UNIVERSE (R-E4b; scripts/gen_universe.py) grows `equity_money.universe.stock` around E1's 18 names
        # and moves both digests of every pair again, AND NOTHING ELSE MOVES WITH IT: every pinned figure below is read
        # on the constitution with E1's universe put back (`league.equity.config.UNIVERSE`, which E4 never changes), so
        # it holds before the universe deploy and after it, and a row that moved with the list would fail them.
        # (`narrow` is that copy; `e1` is the design module's: A20's design with the seat rule's block left out.)
        def narrow(constitution: dict | None = None) -> dict:
            out = copy.deepcopy(CONSTITUTION if constitution is None else constitution)
            out["equity_money"]["universe"] = {klass: [s for s, k in config.UNIVERSE.items() if k == klass]
                                               for klass in config.CLASSES}
            return out

        pair = in_force()
        self.assertIn(pair, CANDIDATES, "the seats and the sleeve in force are one of the grid's pairs")
        self.assertEqual((money_digest(narrow()), digest(narrow())), DIGESTS[pair], "the pair in force is on its pinned digests")
        self.assertEqual(digest(), PINNED_DIGEST)
        if CONSTITUTION["equity_money"]["universe"] != narrow()["equity_money"]["universe"]:
            self.assertNotEqual(money_digest(), money_digest(narrow()), "the universe is a money rule: the grant re-ratifies")
        else:
            self.assertEqual((money_digest(), PINNED_DIGEST), DIGESTS[pair], "the pair in force is on its pinned digests")
        for candidate in CANDIDATES:
            at = narrow(constitution_at(*candidate))
            self.assertEqual((money_digest(at), digest(at)), DIGESTS[candidate], candidate)
            bare = without_seat(at)
            self.assertEqual((money_digest(bare), digest(bare)), DIGESTS_E5S[candidate],
                             f"{candidate}: the seat rule's block alone moved the pair's digests")
        self.assertEqual(len({money for money, _ in DIGESTS.values()}), len(CANDIDATES), "every pair is a digest of its own")
        self.assertEqual(set(DIGESTS.values()) & set(DIGESTS_E5S.values()), set(), "every pin moved with the block")
        self.assertEqual(DIGESTS_E5S[REFERENCE], ("7e41909a9da3e3f44cb4edd8f37921d7f6edba5a9de84e328624570d94ca146a",
                                                  "e909eb1040231bc078e878df2d87fad7a1001d86ab3eac32be5f45f2b82c1895"),
                         "A20's design before the seat rule's block is E1's pair, exactly")
        with e1():
            self.assertEqual(money_digest(narrow()), "7e41909a9da3e3f44cb4edd8f37921d7f6edba5a9de84e328624570d94ca146a")
            self.assertEqual(digest(narrow()), "e909eb1040231bc078e878df2d87fad7a1001d86ab3eac32be5f45f2b82c1895")
            before = copy.deepcopy(CONSTITUTION)
            del before["equity_money"]
            self.assertEqual(money_digest(before), "fdf2ac7c1a446e39df9e27c8626fb86a954a3f5a939460406507a9b735f1d4c7")
            off = narrow()
            off["equity_money"]["enabled"] = False
            self.assertEqual(money_digest(off), "23f17a1467610f8d252b55c6d6748f8fb1311a0142e3f92c43d4bff710886579")
            # A20's rollback: the sleeve back at a quarter of E, the sizing-up step still parked, is a pair of its own...
            quarter = narrow()
            quarter["equity_money"]["probe"]["sleeve_share"] = "0.25"
            self.assertEqual(money_digest(quarter), "3a7c52d58911d0c1a39f58cbe79547e343683a18004355b52a9390c8aec04fd2")
            self.assertEqual(digest(quarter), "6d19fddd271cc46682e48e09ae14364976b76077ca084198874f47dbf4340b43")
            self.assertEqual((money_digest(quarter), digest(quarter)), DIGESTS_E5S[(3, "0.25")],
                             "the grid's own pair, before the seat rule's block")
            # ...and with the rule's own 20 closes back too it is the pair the branch carried before A20, and nothing else.
            quarter["equity_money"]["sized"]["min_trades"] = 20
            self.assertEqual(money_digest(quarter), "ad8c761bccc49033c3fdeca78c7b962f58272d192a2dd6e0626682ccdf6ac367")
            self.assertEqual(digest(quarter), "65b0e025a08d4c3a8f78e487eb1a0f83ad9bfed307563c02acbd50ac4a6308bb")
            # The row alone (the sleeve at 0.50, sizing up as pre-registered) is the digest of the commit before the park.
            unparked = narrow()
            unparked["equity_money"]["sized"]["min_trades"] = 20
            self.assertEqual(money_digest(unparked), "d8c96f66d556c2123b9e797c901075f43af34ad182de3b965fceeca0a7c97f14")
        self.assertFalse(any(path[0] == "equity_money" for path in RISK_FREE))
        seats, sleeve = pair
        for path, value in ((("invested_share",), "0.90"), (("cash_reserve_usd",), "60"), (("probe", "max_programs"), seats - 1),
                            (("probe", "sleeve_share"), "0.49"), (("sized", "min_trades"), 999),
                            (("open_risk_weight", "etf"), "0.25"), (("demotion", "program_loss_usd"), "-200"),
                            (("order_path", "close_until_before_close_s"), 60)):
            moved = copy.deepcopy(CONSTITUTION)
            node = moved["equity_money"]
            for key in path[:-1]:
                node = node[key]
            node[path[-1]] = value
            self.assertNotEqual(money_digest(moved), money_digest(), path)
        # The block as E1 deploys it (INTERFACES 7.1, the captain's amendments A1, A5, A8, A10.2: the switch ships on;
        # nothing trades until a look passes with `elane.mode` "gate" and the stock proof's BUY stage passes), with the
        # two numbers of release E5-S in its `probe` row and no other row moved: the owner's lines are the same strings.
        em = CONSTITUTION["equity_money"]
        self.assertIs(em["enabled"], True)
        self.assertEqual((em["invested_share"], em["cash_reserve_usd"]), ("1.00", "50"))
        self.assertEqual(em["probe"], {"sleeve_share": sleeve, "max_programs": seats, "min_order_usd": "10",
                                       # THE SEAT RULE (release E5-A, the captain's A24): its three rows, as registered.
                                       "seat": {"rule": "activity-1-free", "k_floor": "0.25", "idle_sessions": 10}})
        self.assertEqual(em["position_share"], {"etf": "0.50", "stock": "0.20"})
        self.assertEqual(em["open_risk_weight"], {"etf": "0.20", "stock": "0.40"})
        self.assertEqual(em["sized"]["sleeve_share"], "0.50", "left as pre-registered at every design: never under the Probe's")
        self.assertEqual(em["sized"], {"min_trades": 1000, "confidence": "0.80", "kelly_fraction": "0.25",
                                       "sleeve_share": "0.50", "beat_bh": True, "min_probe_sessions": 5},
                         "THE SIZING-UP STEP IS PARKED: 1000 closes, a tightening inside its bound; nothing else moved")
        probe = CONSTITUTION["options_money"]["probe"]
        self.assertEqual((probe["loss_budget_usd"], probe["loss_window_sessions"], probe["loss_total_usd"]),
                         ("400", 20, "800"), "the shared loss budget is the options table's, untouched")

    def test_the_equity_rows_stay_inside_the_owners_lines(self):
        """`equity_money_problems` (EQUITY_MONEY_BOUNDS): each row is accepted inside its range and at its owner's line,
        and refused one step past it; the loss budget is the options table's, shared (no row of its own here)."""
        import copy

        from league.constitution import EQUITY_MONEY_BOUNDS, equity_money_problems

        self.assertEqual(equity_money_problems(), [])
        self.assertNotIn("loss_budget_usd", json.dumps(CONSTITUTION["equity_money"]))
        loose = {"position_share.etf": ("0.50", "0.5001"), "position_share.stock": ("0.20", "0.2001"),
                 "invested_share": ("1.00", "1.01"), "cash_reserve_usd": ("50", "49.99"),
                 "open_risk_weight.etf": ("0.20", "0.19"), "open_risk_weight.stock": ("0.40", "0.39"),
                 "probe.sleeve_share": ("0.50", "0.51"), "probe.max_programs": (6, 7), "probe.min_order_usd": ("10", "9.99"),
                 "sized.min_trades": (20, 19), "sized.confidence": ("0.80", "0.79"), "sized.kelly_fraction": ("0.25", "0.26"),
                 "sized.sleeve_share": ("0.50", "0.51"), "sized.min_probe_sessions": (5, 4),
                 "demotion.min_trades": (10, 11), "demotion.z": ("1.645", "1.65"),
                 "demotion.program_loss_usd": ("-300", "-300.01"), "demotion.twin_gap_bp": ("15", "15.5"),
                 "demotion.twin_min_closes": (5, 6), "holds.min_hold_sessions": (1, 0),
                 "holds.max_hold_sessions": (60, 61), "holds.failed_decides_exit": (2, 3),
                 "order_path.entry_collar_bp.etf": (10, 51), "order_path.max_collar_bp.etf": (50, 51),
                 "order_path.max_collar_bp.stock": (100, 101), "order_path.max_orders_day": (60, 61)}
        self.assertTrue(set(loose) <= set(EQUITY_MONEY_BOUNDS))
        # A20 (Oct 11, 2026) loosened ONE bound, the Probe sleeve's, to 0.50; release E5-S (the same day) loosened ONE
        # more, the seats', to six, so that the two rows are set together inside them. The owner's lines beside them
        # (an ETF's share, the invested share) and the Sized sleeve's cap are where they were, and the rows in force
        # are inside the two bounds, wherever the study's verdict puts them.
        from decimal import Decimal

        self.assertEqual(EQUITY_MONEY_BOUNDS["probe.sleeve_share"], ("0", "0.50"))
        self.assertEqual(EQUITY_MONEY_BOUNDS["probe.max_programs"], ("0", "6"))
        row = CONSTITUTION["equity_money"]["probe"]
        self.assertLessEqual(Decimal(row["sleeve_share"]), Decimal(EQUITY_MONEY_BOUNDS["probe.sleeve_share"][1]))
        self.assertLessEqual(row["max_programs"], int(EQUITY_MONEY_BOUNDS["probe.max_programs"][1]))
        self.assertLessEqual(Decimal(row["sleeve_share"]), Decimal(CONSTITUTION["equity_money"]["sized"]["sleeve_share"]),
                             "the Sized cap is never under the Probe sleeve")
        self.assertEqual((EQUITY_MONEY_BOUNDS["position_share.etf"], EQUITY_MONEY_BOUNDS["invested_share"],
                          EQUITY_MONEY_BOUNDS["sized.sleeve_share"]), (("0", "0.50"), ("0", "1.00"), ("0", "0.50")))
        # THE SIZING-UP STEP IS PARKED at the other end of its bound: 1000 closes is the row in force, the rule's own
        # 20 stays allowed (the switch back), and one past either end is refused.
        self.assertEqual((CONSTITUTION["equity_money"]["sized"]["min_trades"], EQUITY_MONEY_BOUNDS["sized.min_trades"]),
                         (1000, ("20", "1000")))
        for count, ok in ((1000, True), (20, True), (1001, False), (19, False)):
            parked = copy.deepcopy(CONSTITUTION)
            parked["equity_money"]["sized"]["min_trades"] = count
            self.assertEqual(not any("sized.min_trades " in p for p in equity_money_problems(parked)), ok, count)
        for path, (line, past) in loose.items():
            for value, ok in ((line, True), (past, False)):
                changed = copy.deepcopy(CONSTITUTION)
                node = changed["equity_money"]
                *parents, last = path.split(".")
                for key in parents:
                    node = node[key]
                node[last] = value
                problems = equity_money_problems(changed)
                if ok:
                    self.assertEqual(problems, [], (path, value))
                else:
                    self.assertTrue(any(f"equity_money.{path} " in p for p in problems), (path, value, problems))

    def test_a_changed_threshold_changes_the_digest_equity_too(self):
        import copy

        changed = copy.deepcopy(CONSTITUTION)
        changed["equity_money"]["probe"]["sleeve_share"] = "0.20"
        self.assertNotEqual(digest(changed), PINNED_DIGEST)

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
