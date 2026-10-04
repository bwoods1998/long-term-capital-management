"""The options money table (the plan's "Money", Sept 26, 2026): every row, at its boundary, as `league/live/money.py`
applies it. Standard library only."""

import copy
import tempfile
import unittest
from decimal import Decimal as D
from pathlib import Path

from league.constitution import CONSTITUTION, OPTIONS_MONEY_BOUNDS, options_money_problems
from league.live import money as M


def table(**changes):
    c = copy.deepcopy(CONSTITUTION)
    for path, value in changes.items():
        node = c["options_money"]
        keys = path.split("__")
        for k in keys[:-1]:
            node = node[k]
        node[keys[-1]] = value
    return M.Table.from_constitution(c)


def fwd(returns, *, max_loss=100.0, negative=None, confidence=0.8):
    """A record of REAL fills, one a day (evidence v3: Sized reads the real fills alone)."""
    return M.forward_stats([{"day": f"d{i:04d}", "source": "real", "pnl": r * max_loss, "max_loss": max_loss}
                            for i, r in enumerate(returns)], confidence, negative=negative)


def row(**kw):
    base = {"family": "f", "band": "candidate", "structure": "debit_vertical", "holdout_passed": True, "typical_max_loss_usd": 50.0}
    base.update(kw)
    return base


#: The five multi-leg types the venue closes in one order: the table's real types once a deposit brings credit back.
FIVE = ["debit_vertical", "credit_vertical", "iron_condor", "iron_butterfly", "long_butterfly"]


class TheTable(unittest.TestCase):
    def test_the_defaults_are_the_sprints(self):
        """The sprint (Sept 26, 2026), owner decision D4: the bold end of the plan's ranges; D3's calibration cap; the four
        debit types under $2,000 (the long call and put among them, B4)."""
        t = M.Table.from_constitution()
        self.assertEqual(t.real_types, ("debit_vertical", "long_butterfly", "long_call", "long_put"))
        self.assertEqual(t.credit_types, ("credit_vertical", "iron_condor", "iron_butterfly"))
        self.assertEqual((t.probe_share, t.probe_open, t.probe_family_share, t.probe_floor), (D("0.05"), 3, D("0.15"), D("100")))
        self.assertEqual((t.sized_min_trades, t.sized_confidence, t.kelly_fraction), (20, 0.8, 0.25))
        self.assertEqual((t.sized_share, t.sized_family_share, t.book_share), (D("0.10"), D("0.30"), D("0.90")))
        self.assertEqual((t.daily_stop_share, t.drawdown_stop_share), (D("0.35"), D("0.60")))
        self.assertEqual((t.tuition_day, t.tuition_week, t.calibration_day), (D("200"), D("300"), D("50")))
        # The House live test (the owner, Sept 28, 2026): its pre-registered bounds.
        self.assertEqual((t.house_test_structure, t.house_test_open, t.house_test_envelope, t.house_test_stop,
                          t.house_test_sessions, t.house_test_round_trips), (D("100"), 3, D("300"), D("150"), 20, 30))
        self.assertEqual((t.max_orders_day, t.max_requests_minute, t.bp_buffer), (250, 150, D("0.10")))
        self.assertEqual((t.gateway_order_max_loss, t.gateway_order_share, t.gateway_day_share, t.gateway_max_orders),
                         (D("1000"), D("0.25"), D("1.0"), 300))
        self.assertEqual(t.credit_min_equity, D("2000"))
        self.assertEqual(options_money_problems(), [])
        # A $100 Probe fits the gateway's per-order cap at the account's $481.63: 25% of it is $120.40.
        self.assertGreaterEqual(t.gateway_order_share * D("481.63"), t.probe_floor)

    def test_every_d4_row_is_at_the_bold_end_and_inside_the_plans_range(self):
        c = CONSTITUTION["options_money"]
        for path, value in (("probe.max_loss_share", "0.05"), ("probe.floor_usd", "100"), ("probe.family_share", "0.15"),
                            ("book_share", "0.90"), ("daily_stop_share", "0.35"), ("drawdown_stop_share", "0.60"),
                            ("tuition.day_usd", "200"), ("calibration.day_usd", "50")):
            node = c
            for key in path.split("."):
                node = node[key]
            self.assertEqual(node, value, path)
            self.assertEqual(D(OPTIONS_MONEY_BOUNDS[path][1]), D(value), f"{path} is the bold end of its range")
        self.assertEqual(OPTIONS_MONEY_BOUNDS["gateway.order_equity_share"], ("0", "0.25"))

    def test_every_row_outside_its_range_is_refused(self):
        for path, (low, high) in OPTIONS_MONEY_BOUNDS.items():
            c = copy.deepcopy(CONSTITUTION)
            node = c["options_money"]
            keys = path.split(".")
            for k in keys[:-1]:
                node = node[k]
            node[keys[-1]] = str(D(high) + 1) if D(high) < 1000 else str(D(low) - 1)
            self.assertTrue(any(path in p for p in options_money_problems(c)), path)
            with self.assertRaises(ValueError):
                M.Table.from_constitution(c)
        c = copy.deepcopy(CONSTITUTION)
        c["options_money"]["real_types"] = ["debit_vertical", "calendar"]
        self.assertTrue(options_money_problems(c))
        c = copy.deepcopy(CONSTITUTION)
        del c["options_money"]
        self.assertEqual(options_money_problems(c), ["options_money: the table is missing"])

    def test_the_table_is_part_of_the_money_digest(self):
        from league.constitution import money_digest

        c = copy.deepcopy(CONSTITUTION)
        c["options_money"]["probe"]["max_loss_share"] = "0.04"
        self.assertNotEqual(money_digest(c), money_digest())

    def test_credit_waits_for_two_thousand_dollars_on_equity_alone(self):
        # As it stands (the sprint): no credit type is a real type, at any equity; they come back with a deposit.
        t = M.Table.from_constitution()
        for equity in ("1999.99", "2000", "9000"):
            self.assertIn("credit structure", t.type_allowed("iron_condor", D(equity)))
            self.assertIn("ratified again", t.type_allowed("credit_vertical", D(equity)))
        # With the credit types listed again, they open at $2,000 of equity on equity alone (the gateway's own rule).
        t = table(real_types=FIVE)
        self.assertIn("credit structure", t.type_allowed("iron_condor", D("1999.99")))
        self.assertIsNone(t.type_allowed("iron_condor", D("2000")))
        # The gateway refuses a credit open under $2,000 on equity alone: no latch from an earlier fill opens it here.
        self.assertIn("credit structure", t.type_allowed("iron_condor", D("1999.99")))
        self.assertIsNone(t.type_allowed("debit_vertical", D("100")))
        self.assertIn("closes in more than one order", t.type_allowed("calendar", D("9000")))
        self.assertIn("closes in more than one order", t.type_allowed("long_call", D("9000")), "unless it is listed")

    def test_a_long_call_and_a_long_put_are_real_types_at_any_equity(self):
        t = M.Table.from_constitution()
        for type_ in ("long_call", "long_put", "debit_vertical", "long_butterfly"):
            self.assertIsNone(t.type_allowed(type_, D("100")), type_)
        self.assertIn("closes in more than one order", t.type_allowed("long_straddle", D("9000")))


class Bands(unittest.TestCase):
    def setUp(self):
        self.t = M.Table.from_constitution()

    def test_a_candidate_that_passed_the_holdout_and_fits_is_a_probe(self):
        self.assertEqual(M.band_for(self.t, row(typical_max_loss_usd=150.0), D("5481.65"), fwd([]))[0], "probe")
        # 5% of 5,000 is 250.00: at the line, and a cent over is not a Probe (and not under the $100 floor).
        self.assertEqual(M.band_for(self.t, row(typical_max_loss_usd="250.00"), D("5000"), fwd([]))[0], "probe")
        band, why = M.band_for(self.t, row(typical_max_loss_usd="250.01"), D("5000"), fwd([]))
        self.assertEqual(band, "candidate")
        self.assertIn("over the Probe's cap of $250.00", why)

    def test_an_unknown_typical_loss_keeps_a_candidate_shadow_only(self):
        band, why = M.band_for(self.t, row(typical_max_loss_usd=None), D("5481.65"), fwd([]))
        self.assertEqual(band, "candidate")
        self.assertIn("typical maximum loss is unknown", why)

    def test_an_already_proven_probe_does_not_lose_its_band_when_legacy_typical_metadata_is_missing(self):
        band, _ = M.band_for(self.t, row(band="probe", typical_max_loss_usd=None), D("5481.65"), fwd([]))
        self.assertEqual(band, "probe")

    def test_the_floor_lets_a_small_account_probe_one_contract(self):
        self.assertEqual(M.band_for(self.t, row(typical_max_loss_usd=100.0), D("481.65"), fwd([]))[0], "probe")
        self.assertEqual(M.band_for(self.t, row(typical_max_loss_usd=100.01), D("481.65"), fwd([]))[0], "candidate")
        self.assertEqual(M.band_for(self.t, row(structure="long_put", typical_max_loss_usd=95.0), D("481.63"), fwd([]))[0],
                         "probe", "a long put under the floor is a Probe at the account's $481.63")

    def test_what_keeps_a_family_shadow_only(self):
        self.assertIn("holdout", M.band_for(self.t, row(holdout_passed=False), D("5000"), fwd([]))[1])
        self.assertIn("more than one order", M.band_for(self.t, row(structure="long_strangle"), D("5000"), fwd([]))[1])
        self.assertIn("credit structure", M.band_for(self.t, row(structure="iron_condor"), D("1999"), fwd([]))[1])
        self.assertEqual(M.band_for(self.t, row(structure="iron_condor"), D("2000"), fwd([]))[0], "candidate",
                         "no credit type is real until a deposit re-ratifies the grant")
        self.assertEqual(M.band_for(table(real_types=FIVE), row(structure="iron_condor"), D("2000"), fwd([]))[0], "probe")
        self.assertEqual(M.band_for(self.t, row(structure="long_call"), D("5000"), fwd([]))[0], "probe")
        self.assertEqual(M.band_for(self.t, row(band="gym"), D("5000"), fwd([]))[0], "gym")

    def test_a_candidate_becomes_a_probe_first_never_sized_at_once(self):
        good = [0.2, 0.1, 0.3, -0.1, 0.25] * 5
        self.assertEqual(M.band_for(self.t, row(band="candidate"), D("5000"), fwd(good), probe_sessions=5)[0], "probe")
        shadow = M.forward_stats([{"day": f"d{i:04d}", "source": "shadow", "pnl": r * 100.0, "max_loss": 100.0}
                                  for i, r in enumerate(good)], 0.8)
        self.assertEqual(M.band_for(self.t, row(band="probe"), D("5000"), shadow, probe_sessions=5)[0], "probe",
                         "no real Probe trade yet: the Probe stage is real, never a formality")

    def test_sized_needs_twenty_real_probe_trades_and_five_sessions_at_probe(self):
        """Evidence v3 (the owner's D2, Oct 2, 2026): Sized reads the Probe's REAL fills alone: at least 20 of them, their
        mean above zero and their 80% lower bound above zero, after at least 5 whole sessions at Probe. A winning shadow
        or nightly record sizes nothing."""
        t = self.t
        self.assertEqual((t.min_probe_real_trades, t.min_probe_sessions), (20, 5))
        shadow = [{"day": f"2026-09-{d:02d}", "source": "shadow", "pnl": 20.0, "max_loss": 100.0} for d in range(1, 29)]
        self.assertEqual(M.band_for(t, row(band="probe"), D("5000"), M.forward_stats(shadow, 0.8), probe_sessions=20)[0],
                         "probe", "no real fill: never Sized")
        real = [{"day": f"2026-10-{d:02d}", "source": "real", "pnl": 3.0 + d % 3, "max_loss": 20.0} for d in range(1, 20)]
        nineteen = M.forward_stats(shadow + real, 0.8)
        self.assertEqual(M.band_for(t, row(band="probe"), D("5000"), nineteen, probe_sessions=20)[0], "probe")
        twenty = M.forward_stats(shadow + real + [{"day": "2026-10-20", "source": "real", "pnl": 3.0, "max_loss": 20.0}],
                                 0.8)
        self.assertEqual(twenty.real_n, 20)
        self.assertEqual(M.band_for(t, row(band="probe"), D("5000"), twenty, probe_sessions=4)[0], "probe")
        band, why = M.band_for(t, row(band="probe"), D("5000"), twenty, probe_sessions=5)
        self.assertEqual(band, "sized")
        self.assertIn("20 real Probe trades", why)

    def test_sized_needs_twenty_trades_a_positive_mean_and_a_positive_lower_bound(self):
        def real(returns):
            return M.forward_stats([{"day": f"2026-10-{i + 1:02d}", "source": "real", "pnl": r * 100.0, "max_loss": 100.0}
                                    for i, r in enumerate(returns)], 0.8)
        good = [0.2, 0.1, 0.3, -0.1, 0.25] * 4
        self.assertEqual(M.band_for(self.t, row(band="probe"), D("5000"), real(good), probe_sessions=5)[0], "sized")
        self.assertEqual(M.band_for(self.t, row(band="probe"), D("5000"), real(good[:19]), probe_sessions=5)[0], "probe")
        noisy = [1.0, -0.95] * 10 + [0.01]
        f = fwd(noisy)
        self.assertGreater(f.mean, 0)
        self.assertLess(f.lcb, 0)
        self.assertEqual(M.band_for(self.t, row(band="sized"), D("5000"), f, probe_sessions=1)[0], "probe")

    def test_one_decision_counts_once_preferring_real_then_shadow_then_nightly(self):
        shadow = [{"day": f"2026-10-{d:02d}", "source": "shadow", "pnl": 10.0, "max_loss": 100.0} for d in range(1, 13)]
        nightly = [{"day": f"2026-10-{d:02d}", "source": "nightly", "pnl": 12.0, "max_loss": 100.0} for d in range(1, 16)]
        real = [{"day": f"2026-10-{d:02d}", "source": "real", "pnl": 2.0, "max_loss": 20.0} for d in range(1, 11)]
        f = M.forward_stats(shadow + nightly + real, 0.8)
        # 10 real days, then 2 shadow-only days, then 3 nightly-only days: 15, each day once, the real fills first.
        self.assertEqual(f.n, 15)
        self.assertAlmostEqual(f.pnl, 10 * 2.0 + 2 * 10.0 + 3 * 12.0)
        self.assertEqual(f.real_n, 10)

    def test_real_losses_are_never_hidden_behind_winning_shadow_days(self):
        rows = []
        for d in range(1, 26):
            rows.append({"day": f"2026-10-{d:02d}", "source": "shadow", "pnl": 100.0, "max_loss": 500.0})
            rows.append({"day": f"2026-10-{d:02d}", "source": "nightly", "pnl": 100.0, "max_loss": 500.0})
            rows.append({"day": f"2026-10-{d:02d}", "source": "real", "pnl": -30.0, "max_loss": 60.0})
        f = M.forward_stats(rows, 0.8)
        self.assertLess(f.mean, 0)
        self.assertFalse(M.sized_ok(M.Table.from_constitution(), f))
        self.assertTrue(f.negative)

    def test_a_real_record_that_loses_holds_the_family_at_probe(self):
        t = M.Table.from_constitution()
        rows = [{"day": f"2026-09-{d:02d}", "source": "shadow", "pnl": 30.0, "max_loss": 100.0} for d in range(1, 21)]
        rows += [{"day": f"2026-10-{d:02d}", "source": "real", "pnl": -1.0, "max_loss": 50.0} for d in range(1, 11)]
        rows += [{"day": f"2026-10-{d:02d}", "source": "shadow", "pnl": 30.0, "max_loss": 100.0} for d in range(11, 31)]
        f = M.forward_stats(rows, 0.8)
        self.assertGreater(f.lcb, 0)                        # the whole record is positive
        self.assertFalse(M.sized_ok(t, f))                  # but Sized reads the real fills alone (evidence v3)
        self.assertTrue(f.real_bad)                         # and its 10 real trades lose
        self.assertEqual(M.band_for(t, row(band="probe"), D("5000"), f, probe_sessions=5)[0], "probe")
        band, why = M.band_for(t, row(band="sized"), D("5000"), f, probe_sessions=5)
        self.assertEqual(band, "probe")
        self.assertIn("real", why)

    def test_sized_and_kelly_read_the_real_fills_alone(self):
        rows = [{"day": f"2026-09-{d:02d}", "source": "shadow", "pnl": 30.0, "max_loss": 100.0} for d in range(1, 29)]
        real = [{"day": f"2026-10-{d:02d}", "source": "real", "pnl": (0.3, 0.1, 0.2, 0.15, 0.25)[d % 5] * 100.0,
                 "max_loss": 100.0} for d in range(1, 21)]
        f = M.forward_stats(rows + real, 0.8)
        alone = M.forward_stats(real, 0.8)
        self.assertEqual((f.real_n, f.real_mean, f.real_lcb, f.real_sd), (alone.n, alone.mean, alone.lcb, alone.sd))
        self.assertTrue(M.sized_ok(self.t, f))
        self.assertEqual(M.kelly_cap(self.t, D("10000"), f), M.kelly_cap(self.t, D("10000"), alone),
                         "Kelly on the real lower bound, whatever the shadow days add")
        self.assertEqual(M.kelly_cap(self.t, D("10000"), M.forward_stats(rows, 0.8)), D(0), "no real fill: no Kelly stake")

    def test_the_session_bound_reads_the_trailing_sessions(self):
        rows = [{"day": f"2026-10-{d:02d}", "source": "real", "pnl": 10.0 if d % 2 else -2.0, "max_loss": 100.0,
                 "version": 1} for d in range(1, 21)]
        days, lcb = M.session_bound(rows, sessions=20, confidence=0.8, version=1)
        self.assertEqual(days, 20)
        self.assertGreater(lcb, 0)
        self.assertEqual(M.session_bound(rows[:19], sessions=20, confidence=0.8, version=1), (19, None))
        losing = [dict(r, pnl=-r["pnl"]) for r in rows]
        self.assertLess(M.session_bound(losing, sessions=20, confidence=0.8, version=1)[1], 0)
        self.assertEqual(M.session_bound(rows, sessions=20, confidence=0.8, version=2), (0, None), "its own version")
        older = [dict(r, day=f"2026-09-{i + 1:02d}", pnl=-50.0) for i, r in enumerate(rows)]
        self.assertGreater(M.session_bound(older + rows, sessions=20, confidence=0.8, version=1)[1], 0, "the trailing 20")

    def test_a_new_program_version_starts_its_own_record(self):
        rows = [{"day": f"2026-09-{d:02d}", "source": "shadow", "pnl": 30.0, "max_loss": 100.0, "version": 1} for d in range(1, 25)]
        rows += [{"day": "2026-10-01", "source": "shadow", "pnl": 5.0, "max_loss": 100.0, "version": 2}]
        self.assertEqual(M.forward_stats(rows, 0.8, version=2).n, 1)
        self.assertEqual(M.forward_stats(rows, 0.8, version=1).n, 24)

    def test_a_negative_forward_record_loses_the_band(self):
        band, why = M.band_for(self.t, row(band="sized"), D("5000"), fwd([0.5] * 25, negative=True))
        self.assertEqual(band, "candidate")
        self.assertIn("negative", why)
        self.assertTrue(fwd([-0.1] * 20).negative)
        self.assertFalse(fwd([-0.1] * 19).negative)


class Sizing(unittest.TestCase):
    def setUp(self):
        self.t = M.Table.from_constitution()

    def plan(self, unit, *, band="probe", equity="5481.65", fwd_=None, tuition=False, **exposure):
        return M.plan_open(self.t, band=band, tuition=tuition, equity=D(equity), unit=D(str(unit)), fwd=fwd_,
                           exposure=M.Exposure(**{k: (D(str(v)) if k not in ("family_open",) else v) for k, v in exposure.items()}))

    def test_a_probe_is_sized_by_maximum_loss(self):
        # 5% of 5,481.65 = 274.0825: two structures of $137.00 (with fees) fit, three do not.
        self.assertEqual(self.plan(137.00).qty, 2)
        self.assertEqual(self.plan(137.05).qty, 1)
        self.assertEqual(self.plan(274.08).qty, 1)
        self.assertEqual(self.plan(91.36).qty, 3)
        refused = self.plan(274.09)
        self.assertEqual(refused.qty, 0)
        self.assertIn("over its cap of $274.08", refused.reason)

    def test_the_floor_is_one_contract_of_at_most_a_hundred_dollars(self):
        self.assertEqual(self.plan(100.00, equity="481.65").qty, 1)
        self.assertEqual(self.plan(100.01, equity="481.65").qty, 0)
        self.assertEqual(self.plan(24.00, equity="481.65").qty, 1)    # 5% of 481.65 is 24.08: one by the share
        self.assertEqual(self.plan(12.00, equity="481.65").qty, 2)
        # At the account's $481.63 a $100 floor contract fits every cap: the gateway's 25% is $120.40.
        self.assertEqual(self.plan(100.00, equity="481.63").qty, 1)

    def test_three_open_structures_a_probe_family(self):
        self.assertEqual(self.plan(50, family_open=2).qty, 5)
        self.assertIn("the most a Probe family holds is 3", self.plan(50, family_open=3).reason)

    def test_the_family_total(self):
        # 15% of 5,481.65 = 822.2475; 770 open leaves 52.24: one $50 structure, not two.
        self.assertEqual(self.plan(50, family_loss="770").qty, 1)
        self.assertEqual(self.plan(50, family_loss="822.25").qty, 0)
        # The floor: a small account's family may hold one floor contract (15% of 481.65 is 72.25 < 100).
        self.assertEqual(self.plan(99.00, equity="481.65").qty, 1)
        self.assertEqual(self.plan(99.00, equity="481.65", family_loss="99").qty, 0)

    def test_sized_is_quarter_kelly_on_the_lower_bound_between_the_probe_and_ten_percent(self):
        f = fwd([0.3, 0.1, 0.2, 0.15, 0.25] * 4)
        cap = M.structure_cap(self.t, "sized", D("10000"), f)
        self.assertLessEqual(cap, D("1000"))           # 10%
        self.assertGreaterEqual(cap, D("500"))         # never below the Probe's 5%
        import league.stats as S
        expect = min(0.10, 0.25 * f.lcb / f.variance) * 10000
        self.assertAlmostEqual(float(cap), max(500.0, expect), places=6)
        self.assertEqual(self.plan(100, band="sized", equity="10000", fwd_=f, family_loss="2950").qty, 0)  # 30% family

    def test_a_sized_family_whose_kelly_is_under_the_probes_cap_keeps_the_probes_limits(self):
        weak = fwd([0.44, -0.28] * 10)                 # mean 0.08, sd 0.37: LCB barely positive, quarter-Kelly under 5%
        self.assertTrue(M.sized_ok(self.t, weak))
        self.assertLess(M.kelly_cap(self.t, D("5481.65"), weak), M.probe_cap(self.t, D("5481.65")))
        self.assertEqual(M.sizing_band(self.t, "sized", D("5481.65"), weak), "probe")
        self.assertEqual(M.structure_cap(self.t, "sized", D("5481.65"), weak), M.probe_cap(self.t, D("5481.65")))
        # Sized at a Probe-sized stake never gets the Sized family limits: three open, 15%.
        self.assertIn("the most a Probe family holds is 3", self.plan(10, band="sized", fwd_=weak, family_open=3).reason)
        self.assertEqual(self.plan(10, band="sized", fwd_=weak, family_loss="815").qty, 0)

    def test_the_book_and_the_gateways_caps(self):
        self.assertIn("the book's open maximum loss", self.plan(50, book_loss="4933.49").reason)   # 90% = 4933.485
        self.assertEqual(self.plan(50, book_loss="4880").qty, 1)
        # The gateway's order cap: min(1,000, 25% of equity) = 1,000 at 5,481.65; a Sized family's 10% is 548.16.
        big = M.plan_open(self.t, band="sized", tuition=False, equity=D("20000"), unit=D("300"),
                          fwd=fwd([0.9, 0.8, 1.0, 0.7] * 5), exposure=M.Exposure())
        self.assertEqual(big.qty, 3)                   # 10% of 20,000 = 2,000 but the gateway's $1,000 binds: 3 x 300
        self.assertIn("gateway's day cap", self.plan(50, day_opened="5450").reason)

    def test_tuition_is_one_structure_under_the_day_and_week_budgets(self):
        self.assertEqual(self.plan(40, band="gym", tuition=True).qty, 1)
        self.assertIn("the day's $200", self.plan(40, band="gym", tuition=True, tuition_day="170").reason)
        self.assertEqual(self.plan(40, band="gym", tuition=True, tuition_day="160").qty, 1)
        self.assertIn("the week's $300", self.plan(40, band="gym", tuition=True, tuition_week="270").reason)

    def test_a_candidate_trades_no_real_money(self):
        self.assertIn("shadow only", self.plan(10, band="candidate").reason)


class Stops(unittest.TestCase):
    def setUp(self):
        self.t = M.Table.from_constitution()
        self.stops = M.Stops(start_equity=D("481.65"))

    def flows(self, read_at, rows=(), closes=(0.0,)):
        return M.FlowBook(read_at=read_at, rows=tuple((t, D(a)) for t, a in rows), closes=tuple(closes))

    def test_a_deposit_is_not_profit_and_does_not_raise_the_peak(self):
        s = self.stops
        s.observe(self.t, at=100, day="d1", equity=D("481.65"), last_equity=D("481.65"), flows=self.flows(200))
        # $5,000 lands; equity is 5,481.65: no profit, no new peak, no drawdown, no daily move.
        f = self.flows(400, [(250, "5000")])
        s.observe(self.t, at=300, day="d1", equity=D("5481.65"), last_equity=D("481.65"), flows=f, funding_confirmed=True)
        self.assertEqual(s.peak_profit, D(0))
        self.assertEqual(s.drawdown, D(0))
        self.assertEqual(s.day_pnl, D(0))
        self.assertIsNone(s.blocked())
        # A $300 loss is 5.5% of the capital at the peak, not 62% of the account before the deposit.
        s.observe(self.t, at=350, day="d1", equity=D("5181.65"), last_equity=D("481.65"), flows=f)
        self.assertAlmostEqual(float(s.drawdown), 300 / 5481.65, places=6)
        self.assertFalse(s.drawdown_tripped)

    def test_the_daily_stop_nets_the_days_deposits(self):
        s = self.stops
        # The session's first reading is the start of the day; a $5,000 deposit lands at 500.
        s.observe(self.t, at=100, day="d1", equity=D("481.65"), last_equity=D("481.65"), flows=self.flows(200))
        f = self.flows(1000, [(500, "5000")])
        s.observe(self.t, at=900, day="d1", equity=D("3563.07"), last_equity=D("481.65"), flows=f, funding_confirmed=True)
        # base = 481.65 + 5,000 = 5,481.65; day P&L = 3,563.07 - 481.65 - 5,000 = -1,918.58 = -35.00005%: tripped.
        self.assertTrue(s.daily_tripped)
        self.assertIn("no new entry today", s.blocked())
        s2 = M.Stops(start_equity=D("481.65"))
        s2.observe(self.t, at=100, day="d1", equity=D("481.65"), last_equity=D("481.65"), flows=self.flows(200))
        s2.observe(self.t, at=900, day="d1", equity=D("3563.08"), last_equity=D("481.65"), flows=f, funding_confirmed=True)
        self.assertFalse(s2.daily_tripped)            # -1,918.57 is under 35% of 5,481.65 (1,918.5775)
        # A deposit that had already landed at the session's first reading is in its base, whatever the venue's
        # last_equity says: no stop on a deposit.
        s3 = M.Stops(start_equity=D("481.65"))
        s3.observe(self.t, at=900, day="d1", equity=D("5481.65"), last_equity=D("5481.65"), flows=f)
        s3.observe(self.t, at=950, day="d1", equity=D("5481.65"), last_equity=D("481.65"), flows=self.flows(1000, [(500, "5000")]))
        self.assertFalse(s3.daily_tripped)
        self.assertEqual(s3.day_pnl, D(0))
        # The next session starts clean.
        s.observe(self.t, at=1900, day="d2", equity=D("3563.07"), last_equity=D("3563.07"), flows=self.flows(2000, [(500, "5000")]))
        self.assertFalse(s.daily_tripped)

    def test_the_drawdown_stop_latches_on_a_settled_reading_and_only_the_owner_releases_it(self):
        s = self.stops
        f = self.flows(100)
        s.observe(self.t, at=50, day="d1", equity=D("1000"), last_equity=D("1000"), flows=f)   # a profit of 518.35: the peak
        self.assertEqual(s.peak_profit, D("518.35"))
        s.observe(self.t, at=150, day="d2", equity=D("400.01"), last_equity=D("400.01"), flows=self.flows(200, closes=(120.0,)))
        self.assertFalse(s.drawdown_tripped)           # 59.999%
        s.observe(self.t, at=250, day="d3", equity=D("400"), last_equity=D("400"), flows=self.flows(300, closes=(220.0,)))
        self.assertTrue(s.drawdown_tripped)
        self.assertIn("real money paused", s.blocked())
        s.observe(self.t, at=350, day="d3", equity=D("2000"), last_equity=D("500"), flows=self.flows(400, closes=(220.0,)))
        self.assertTrue(s.drawdown_tripped)            # latched: only the owner's release lifts it
        s.release_drawdown()
        self.assertIsNone(s.blocked())

    def test_a_reading_newer_than_the_flows_blocks_but_never_latches(self):
        s = self.stops
        s.observe(self.t, at=50, day="d1", equity=D("1000"), last_equity=D("1000"), flows=self.flows(100))
        # A $600 withdrawal at 150 that the flows (read at 100) have not seen yet looks like a 60% loss.
        s.observe(self.t, at=160, day="d1", equity=D("400"), last_equity=D("1000"), flows=self.flows(100))
        self.assertFalse(s.drawdown_tripped)
        self.assertFalse(s.daily_tripped)
        self.assertIn("deposits are not read yet", s.blocked())
        # Once the withdrawal is read the reading is settled, and it was no loss at all.
        s.observe(self.t, at=170, day="d1", equity=D("400"), last_equity=D("1000"),
                  flows=self.flows(200, [(150, "-600")]), funding_confirmed=True)
        self.assertFalse(s.drawdown_tripped)
        self.assertFalse(s.daily_tripped)
        self.assertIsNone(s.blocked())

    def test_the_owners_release_restarts_the_peak_from_now(self):
        s = self.stops
        s.observe(self.t, at=50, day="d1", equity=D("1000"), last_equity=D("1000"), flows=self.flows(100))
        s.observe(self.t, at=150, day="d2", equity=D("400"), last_equity=D("400"), flows=self.flows(200))
        self.assertTrue(s.drawdown_tripped)
        s.release_drawdown()
        s.observe(self.t, at=250, day="d3", equity=D("400"), last_equity=D("400"), flows=self.flows(300))
        self.assertFalse(s.drawdown_tripped, "the peak restarted at the release: no new drawdown")
        s.observe(self.t, at=300, day="d4", equity=D("160.01"), last_equity=D("160.01"), flows=self.flows(310))
        self.assertFalse(s.drawdown_tripped, "59.99% from the restarted peak")
        s.observe(self.t, at=350, day="d5", equity=D("160"), last_equity=D("160"), flows=self.flows(400))
        self.assertTrue(s.drawdown_tripped, "a new 60% fall from the restarted peak trips it again")

    def test_a_pending_deposit_or_withdrawal_settles_nothing(self):
        s = self.stops
        s.observe(self.t, at=50, day="d1", equity=D("1000"), last_equity=D("1000"), flows=self.flows(100))
        pending = M.FlowBook(read_at=300, rows=(), closes=(0.0,), unsettled=("a CSW of -600 queued",))
        s.observe(self.t, at=250, day="d1", equity=D("400"), last_equity=D("1000"), flows=pending)
        self.assertFalse(s.drawdown_tripped)
        self.assertFalse(s.daily_tripped)
        self.assertIn("pending", s.blocked())

    def test_the_days_base_is_the_last_reading_of_the_previous_session(self):
        s = self.stops
        s.observe(self.t, at=100, day="d1", equity=D("1000"), last_equity=D("1000"), flows=self.flows(150))
        # The House was down at the open of d2 and first reads the account mid-session, $300 lower.
        s.observe(self.t, at=500, day="d2", equity=D("650"), last_equity=D("1000"), flows=self.flows(600))
        self.assertTrue(s.daily_tripped)
        self.assertEqual(s.day_base, D("1000"))

    def test_readings_taken_while_a_flow_was_pending_are_never_settled(self):
        s = self.stops
        s.observe(self.t, at=50, day="d1", equity=D("3000"), last_equity=D("3000"), flows=self.flows(100))
        pending = M.FlowBook(read_at=250, rows=(), closes=(0.0,), unsettled=("CSD 3000 queued",))
        for t in (200, 260, 300):
            s.observe(self.t, at=t, day="d1", equity=D("3000"), last_equity=D("3000"), flows=pending)
        # It executes overnight: the flow is timed at its request (200), equity moved only at execution (after 300).
        done = self.flows(400, [(200, "3000")])
        s.observe(self.t, at=350, day="d2", equity=D("6000"), last_equity=D("6000"), flows=done)
        self.assertFalse(s.drawdown_tripped, "the readings taken while it was pending were never settled against it")
        self.assertEqual(s.peak_profit, D("3000") - D("481.65"))

    def test_no_flows_read_blocks_entries(self):
        s = self.stops
        s.observe(self.t, at=10, day="d1", equity=D("481.65"), last_equity=D("481.65"), flows=None)
        self.assertIn("funding history has not been read", s.blocked())

    def test_the_state_round_trips(self):
        s = self.stops
        s.observe(self.t, at=50, day="d1", equity=D("1000"), last_equity=D("1000"), flows=self.flows(40))
        again = M.Stops.from_state(s.as_state(), D("481.65"))
        self.assertEqual(again.as_state(), s.as_state())


class TheSwarmsStore(unittest.TestCase):
    """The interface agreed with Wave 4, against the swarm's real store (`league/swarm/store.py`, `bands.read`)."""

    def test_the_live_path_reads_the_bands_writes_versioned_forward_trades_and_moves_bands(self):
        from league.live.families import SwarmFamilies
        from league.swarm.store import SwarmStore
        from league.tests.swarm_fakes import Clock as SwarmClock
        from league.tests.evaluator_fakes import band_proof, passed_look

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            store = SwarmStore(root, clock=SwarmClock())
            store.add_family({"id": "vert", "mechanism": "Calls after a quiet open.", "structure": "debit_vertical",
                              "roots": ["SPY"], "dte": [0, 2]}, origin="seed")
            store.add_version("vert", "# vert\nNEEDS = {}\n", {"k": 1}, author="seed")
            store.set_state("vert", banded_version=1, validation_version=1, validation_line={"passed": True},
                            typical_max_loss_usd=60.0, banded_evaluator=band_proof(store.version("vert", 1)))
            store.set_band("vert", "candidate", reason="passed the holdout")
            passed_look(store, "vert", store.version("vert", 1))  # the look its band stands on (`bands.read`)
            store.close()
            families = SwarmFamilies(root)
            [row] = families.read()
            self.assertEqual((row["family"], row["band"], row["version"], row["holdout_passed"]), ("vert", "candidate", 1, True))
            trades = [{"id": f"t{i}", "day": "2026-09-28", "pnl": 3.0, "max_loss": 50.0, "version": 1} for i in range(2)]
            self.assertEqual(families.add_forward("vert", "shadow", trades), 2)
            self.assertEqual(families.add_forward("vert", "shadow", trades), 0, "each trade once by id")
            families.add_forward("vert", "real", [{"id": "r1", "day": "2026-09-28", "pnl": -2.0, "max_loss": 40.0, "version": 1}])
            families.add_forward("vert", "shadow", [{"id": "old", "day": "2026-09-25", "pnl": 9.0, "max_loss": 50.0, "version": 0}])
            rows = families.forward_rows("vert")
            self.assertEqual({(r["source"], r["version"]) for r in rows}, {("shadow", 1), ("real", 1), ("shadow", 0)})
            fwd = M.forward_stats(rows, D("0.80"), version=1)
            self.assertEqual((fwd.n, fwd.real_n), (1, 1), "the version's own record, one source a day, real first")
            families.set_band("vert", "probe", "passed the holdout and fits the Probe's cap")
            self.assertEqual(families.read()[0]["band"], "probe")
            store = SwarmStore(root, clock=SwarmClock())
            store.add_version("vert", "# newer\nNEEDS = {}\n", {"k": 2}, author="researcher")
            store.set_state("vert", validation_version=2, validation_line={"passed": False}, typical_max_loss_usd=900.0,
                            typical_by_version={"1": 60.0, "2": 900.0})
            store.close()
            [banded] = families.read()
            self.assertEqual((banded["version"], banded["typical_max_loss_usd"]), (1, 60.0))


if __name__ == "__main__":
    unittest.main()
