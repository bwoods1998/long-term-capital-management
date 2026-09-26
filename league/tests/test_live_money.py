"""The options money table (the plan's "Money", Sept 26, 2026): every row, at its boundary, as `league/live/money.py`
applies it. Standard library only."""

import copy
import unittest
from decimal import Decimal as D

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
    return M.forward_stats([{"pnl": r * max_loss, "max_loss": max_loss} for r in returns], confidence, negative=negative)


def row(**kw):
    base = {"family": "f", "band": "candidate", "structure": "debit_vertical", "holdout_passed": True, "typical_max_loss_usd": None}
    base.update(kw)
    return base


class TheTable(unittest.TestCase):
    def test_the_defaults_are_the_plans(self):
        t = M.Table.from_constitution()
        self.assertEqual(t.real_types, ("debit_vertical", "credit_vertical", "iron_condor", "iron_butterfly", "long_butterfly"))
        self.assertEqual((t.probe_share, t.probe_open, t.probe_family_share, t.probe_floor), (D("0.03"), 3, D("0.12"), D("60")))
        self.assertEqual((t.sized_min_trades, t.sized_confidence, t.kelly_fraction), (20, 0.8, 0.25))
        self.assertEqual((t.sized_share, t.sized_family_share, t.book_share), (D("0.10"), D("0.30"), D("0.70")))
        self.assertEqual((t.daily_stop_share, t.drawdown_stop_share), (D("0.25"), D("0.50")))
        self.assertEqual((t.tuition_day, t.tuition_week), (D("100"), D("300")))
        self.assertEqual((t.max_orders_day, t.max_requests_minute, t.bp_buffer), (250, 150, D("0.10")))
        self.assertEqual((t.gateway_order_max_loss, t.gateway_order_share, t.gateway_day_share, t.gateway_max_orders),
                         (D("1000"), D("0.15"), D("1.0"), 300))
        self.assertEqual(t.credit_min_equity, D("2000"))
        self.assertEqual(options_money_problems(), [])

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

    def test_credit_waits_for_two_thousand_dollars(self):
        t = M.Table.from_constitution()
        self.assertIn("credit structure", t.type_allowed("iron_condor", D("1999.99")))
        self.assertIsNone(t.type_allowed("iron_condor", D("2000")))
        self.assertIsNone(t.type_allowed("iron_condor", D("500"), credit_accepted=True))
        self.assertIsNone(t.type_allowed("debit_vertical", D("100")))
        self.assertIn("closes in more than one order", t.type_allowed("calendar", D("9000")))
        self.assertIn("closes in more than one order", t.type_allowed("long_call", D("9000")))


class Bands(unittest.TestCase):
    def setUp(self):
        self.t = M.Table.from_constitution()

    def test_a_candidate_that_passed_the_holdout_and_fits_is_a_probe(self):
        self.assertEqual(M.band_for(self.t, row(typical_max_loss_usd=150.0), D("5481.65"), fwd([]))[0], "probe")
        # 3% of 5,000 is 150.00: at the line, and a cent over is not a Probe (and not under the $60 floor).
        self.assertEqual(M.band_for(self.t, row(typical_max_loss_usd="150.00"), D("5000"), fwd([]))[0], "probe")
        band, why = M.band_for(self.t, row(typical_max_loss_usd="150.01"), D("5000"), fwd([]))
        self.assertEqual(band, "candidate")
        self.assertIn("over the Probe's cap of $150.00", why)

    def test_the_floor_lets_a_small_account_probe_one_contract(self):
        self.assertEqual(M.band_for(self.t, row(typical_max_loss_usd=60.0), D("481.65"), fwd([]))[0], "probe")
        self.assertEqual(M.band_for(self.t, row(typical_max_loss_usd=60.01), D("481.65"), fwd([]))[0], "candidate")

    def test_what_keeps_a_family_shadow_only(self):
        self.assertIn("holdout", M.band_for(self.t, row(holdout_passed=False), D("5000"), fwd([]))[1])
        self.assertIn("more than one order", M.band_for(self.t, row(structure="long_strangle"), D("5000"), fwd([]))[1])
        self.assertIn("credit structure", M.band_for(self.t, row(structure="iron_condor"), D("1999"), fwd([]))[1])
        self.assertEqual(M.band_for(self.t, row(structure="iron_condor"), D("2000"), fwd([]))[0], "probe")
        self.assertEqual(M.band_for(self.t, row(band="gym"), D("5000"), fwd([]))[0], "gym")

    def test_sized_needs_twenty_trades_a_positive_mean_and_a_positive_lower_bound(self):
        good = [0.2, 0.1, 0.3, -0.1, 0.25] * 4
        self.assertEqual(M.band_for(self.t, row(band="probe"), D("5000"), fwd(good))[0], "sized")
        self.assertEqual(M.band_for(self.t, row(band="probe"), D("5000"), fwd(good[:19]))[0], "probe")
        noisy = [1.0, -0.95] * 10 + [0.01]
        f = fwd(noisy)
        self.assertGreater(f.mean, 0)
        self.assertLess(f.lcb, 0)
        self.assertEqual(M.band_for(self.t, row(band="sized"), D("5000"), f)[0], "probe")

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
        # 3% of 5,481.65 = 164.4495: two structures of $80.00 (with fees) fit, three do not.
        self.assertEqual(self.plan(80.00).qty, 2)
        self.assertEqual(self.plan(164.44).qty, 1)
        self.assertEqual(self.plan(54.8165).qty, 3)
        refused = self.plan(164.46)
        self.assertEqual(refused.qty, 0)
        self.assertIn("over its cap of $164.44", refused.reason)

    def test_the_floor_is_one_contract_of_at_most_sixty_dollars(self):
        self.assertEqual(self.plan(60.00, equity="481.65").qty, 1)
        self.assertEqual(self.plan(60.01, equity="481.65").qty, 0)
        self.assertEqual(self.plan(14.00, equity="481.65").qty, 1)    # 3% of 481.65 is 14.44: one by the share
        self.assertEqual(self.plan(7.00, equity="481.65").qty, 2)

    def test_three_open_structures_a_probe_family(self):
        self.assertEqual(self.plan(50, family_open=2).qty, 3)
        self.assertIn("the most a Probe family holds is 3", self.plan(50, family_open=3).reason)

    def test_the_family_total(self):
        # 12% of 5,481.65 = 657.798; 600 open leaves 57.79: one $50 structure, not two.
        self.assertEqual(self.plan(50, family_loss="600").qty, 1)
        self.assertEqual(self.plan(50, family_loss="657.80").qty, 0)
        # The floor: a small account's family may hold one floor contract (12% of 481.65 is 57.80 < 60).
        self.assertEqual(self.plan(59.00, equity="481.65").qty, 1)
        self.assertEqual(self.plan(59.00, equity="481.65", family_loss="59").qty, 0)

    def test_sized_is_quarter_kelly_on_the_lower_bound_between_the_probe_and_ten_percent(self):
        f = fwd([0.3, 0.1, 0.2, 0.15, 0.25] * 4)
        cap = M.structure_cap(self.t, "sized", D("10000"), f)
        self.assertLessEqual(cap, D("1000"))           # 10%
        self.assertGreaterEqual(cap, D("300"))         # never below the Probe's 3%
        import league.stats as S
        expect = min(0.10, 0.25 * f.lcb / f.variance) * 10000
        self.assertAlmostEqual(float(cap), max(300.0, expect), places=6)
        weak = fwd([0.02, 0.01, 0.03, -0.01] * 5)
        self.assertEqual(M.structure_cap(self.t, "sized", D("10000"), weak), max(D("300"), M.structure_cap(self.t, "sized", D("10000"), weak)))
        self.assertEqual(self.plan(100, band="sized", equity="10000", fwd_=f, family_loss="2950").qty, 0)  # 30% family

    def test_the_book_and_the_gateways_caps(self):
        self.assertIn("the book's open maximum loss", self.plan(50, book_loss="3837.16").reason)   # 70% = 3837.155
        self.assertEqual(self.plan(50, book_loss="3780").qty, 1)
        # The gateway's order cap: min(1,000, 15% of equity) = 822.24 at 5,481.65; a Sized family's 10% is 548.16.
        big = M.plan_open(self.t, band="sized", tuition=False, equity=D("20000"), unit=D("300"),
                          fwd=fwd([0.9, 0.8, 1.0, 0.7] * 5), exposure=M.Exposure())
        self.assertEqual(big.qty, 3)                   # 10% of 20,000 = 2,000 but the gateway's $1,000 binds: 3 x 300
        self.assertIn("gateway's day cap", self.plan(50, day_opened="5450").reason)

    def test_tuition_is_one_structure_under_the_day_and_week_budgets(self):
        self.assertEqual(self.plan(40, band="gym", tuition=True).qty, 1)
        self.assertIn("the day's $100", self.plan(40, band="gym", tuition=True, tuition_day="70").reason)
        self.assertEqual(self.plan(40, band="gym", tuition=True, tuition_day="60").qty, 1)
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
        s.observe(self.t, at=300, day="d1", equity=D("5481.65"), last_equity=D("481.65"), flows=f)
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
        s.observe(self.t, at=900, day="d1", equity=D("4111.23"), last_equity=D("481.65"), flows=f)
        # base = 481.65 + 5,000 = 5,481.65; day P&L = 4,111.23 - 481.65 - 5,000 = -1,370.42 = -25.0001%: tripped.
        self.assertTrue(s.daily_tripped)
        self.assertIn("no new entry today", s.blocked())
        s2 = M.Stops(start_equity=D("481.65"))
        s2.observe(self.t, at=100, day="d1", equity=D("481.65"), last_equity=D("481.65"), flows=self.flows(200))
        s2.observe(self.t, at=900, day="d1", equity=D("4111.24"), last_equity=D("481.65"), flows=f)
        self.assertFalse(s2.daily_tripped)            # -1,370.41 is under 25% of 5,481.65 (1,370.4125)
        # A deposit that had already landed at the session's first reading is in its base, whatever the venue's
        # last_equity says: no stop on a deposit.
        s3 = M.Stops(start_equity=D("481.65"))
        s3.observe(self.t, at=900, day="d1", equity=D("5481.65"), last_equity=D("5481.65"), flows=f)
        s3.observe(self.t, at=950, day="d1", equity=D("5481.65"), last_equity=D("481.65"), flows=self.flows(1000, [(500, "5000")]))
        self.assertFalse(s3.daily_tripped)
        self.assertEqual(s3.day_pnl, D(0))
        # The next session starts clean.
        s.observe(self.t, at=1900, day="d2", equity=D("4111.23"), last_equity=D("4111.23"), flows=self.flows(2000, [(500, "5000")]))
        self.assertFalse(s.daily_tripped)

    def test_the_drawdown_stop_latches_on_a_settled_reading_and_only_the_owner_releases_it(self):
        s = self.stops
        f = self.flows(100)
        s.observe(self.t, at=50, day="d1", equity=D("1000"), last_equity=D("1000"), flows=f)   # a profit of 518.35: the peak
        self.assertEqual(s.peak_profit, D("518.35"))
        s.observe(self.t, at=150, day="d2", equity=D("500.01"), last_equity=D("500.01"), flows=self.flows(200, closes=(120.0,)))
        self.assertFalse(s.drawdown_tripped)           # 49.999%
        s.observe(self.t, at=250, day="d3", equity=D("500"), last_equity=D("500"), flows=self.flows(300, closes=(220.0,)))
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
        s.observe(self.t, at=170, day="d1", equity=D("400"), last_equity=D("1000"), flows=self.flows(200, [(150, "-600")]))
        self.assertFalse(s.drawdown_tripped)
        self.assertFalse(s.daily_tripped)
        self.assertIsNone(s.blocked())

    def test_no_flows_read_blocks_entries(self):
        s = self.stops
        s.observe(self.t, at=10, day="d1", equity=D("481.65"), last_equity=D("481.65"), flows=None)
        self.assertIn("funding history has not been read", s.blocked())

    def test_the_state_round_trips(self):
        s = self.stops
        s.observe(self.t, at=50, day="d1", equity=D("1000"), last_equity=D("1000"), flows=self.flows(40))
        again = M.Stops.from_state(s.as_state(), D("481.65"))
        self.assertEqual(again.as_state(), s.as_state())


if __name__ == "__main__":
    unittest.main()
