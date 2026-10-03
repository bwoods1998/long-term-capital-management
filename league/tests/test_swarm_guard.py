"""The Sail guard (league/swarm/guard.py): the swarm brakes to zero before the House is at risk, and inside THE BUDGET's
day (league/ops/budget.py, LTCM v3: the burst trio is gone)."""

from __future__ import annotations

import copy
import datetime as dt
import tempfile
import unittest
from pathlib import Path

from league.swarm import settings as S
from league.swarm.guard import SailGuard
from league.swarm.store import SwarmStore
from league.tests.swarm_fakes import Clock

T = dt.datetime(2026, 10, 7, 15, 0, tzinfo=dt.timezone.utc).timestamp()


class GuardCase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.clock = Clock(T)
        self.store = SwarmStore(Path(self.dir.name), clock=self.clock)
        self.addCleanup(self.store.close)
        self.reading = (118.79, 34.0)
        self.settings = copy.deepcopy(S.DEFAULTS)
        # A budget too large to bind, so each test meets only the line it is about (the Budget tests set their own).
        self.settings["budget"] = {"source": "budget.json", "sail_usd_day": 10_000.0, "claude_usd_day": 0.0,
                                   "fixed_sail_usd_day": None}

    def guard(self):
        return SailGuard(self.store, self.settings, lambda: self.reading, clock=self.clock, disk_free=lambda: 100.0 * 2 ** 30)


class Defaults(GuardCase):
    def test_by_default_the_line_is_two_days_of_the_configured_house_burn_plus_thirty(self):
        self.reading = (40.0, 31.0)  # Sail's 24-hour burn still holds a stopped House's history
        g = self.guard()
        out = g.check()
        self.assertEqual((out["house_day"], out["line"]), (1.0, 32.0))
        self.assertTrue(g.allows())
        self.reading = (31.0, 31.0)
        g.check()
        self.assertFalse(g.allows())


class Guard(GuardCase):
    """The measured-burn line (guard.measured_burn true)."""

    def setUp(self):
        super().setUp()
        self.settings["guard"].update(measured_burn=True, house_burn_usd_day=2.0)

    def test_a_healthy_balance_spends(self):
        g = self.guard()
        out = g.check()
        self.assertTrue(g.allows())
        # The non-swarm burn is Sail's 24-hour burn less the swarm's own: 2 x 34 + 30.
        self.assertEqual(out["line"], 98.0)

    def test_below_two_days_of_the_house_plus_thirty_it_brakes_and_says_why(self):
        self.reading = (90.0, 34.0)
        g = self.guard()
        g.check()
        self.assertFalse(g.allows())
        self.assertIn("under the House's line", g.reason)
        events = [e for e in self.store.events_after(0) if e["kind"] == "swarm.guard"]
        self.assertEqual(events[-1]["payload"]["action"], "brake")

    def test_the_swarms_own_burn_does_not_count_as_the_houses(self):
        self.store.add_spend("sail_model", 30.0)
        self.reading = (80.0, 34.0)
        g = self.guard()
        out = g.check()
        self.assertEqual(out["house_day"], 4.0)
        self.assertTrue(g.allows(), out)

    def test_the_house_burn_never_counts_below_its_floor(self):
        self.reading = (40.0, 0.0)
        g = self.guard()
        out = g.check()
        self.assertEqual(out["house_day"], 2.0)
        self.assertEqual(out["line"], 34.0)
        self.assertTrue(g.allows())

    def test_the_operator_may_trust_the_configured_house_burn(self):
        self.reading = (80.0, 34.0)
        self.settings["guard"].update(measured_burn=False, house_burn_usd_day=3.0)
        g = self.guard()
        out = g.check()
        self.assertEqual((out["house_day"], out["line"]), (3.0, 36.0))
        self.assertTrue(g.allows())

    def test_release_needs_the_line_plus_a_margin(self):
        self.reading = (90.0, 34.0)
        g = self.guard()
        g.check()
        self.reading = (100.0, 34.0)
        g.check()
        self.assertFalse(g.allows(), "98 + 5 not yet reached")
        self.reading = (104.0, 34.0)
        g.check()
        self.assertTrue(g.allows())
        kinds = [e["payload"]["action"] for e in self.store.events_after(0) if e["kind"] == "swarm.guard"]
        self.assertEqual(kinds, ["brake", "release"])

    def test_an_unreadable_balance_brakes_at_once_and_only_a_good_reading_releases(self):
        g = self.guard()
        g.check()
        self.assertTrue(g.allows())
        self.reading = (None, None)
        self.clock.advance(180)
        g.check()
        self.assertFalse(g.allows(), "fail closed: no new cycle or box on a failed read")
        self.assertIn("could not be read", g.reason)
        self.reading = (118.79, 34.0)
        self.clock.advance(180)
        g.check()
        self.assertTrue(g.allows())

    def test_the_last_good_reading_outlives_a_failed_read(self):
        g = self.guard()
        g.check()
        good_at = self.clock()
        self.reading = (None, None)
        self.clock.advance(180)
        g.check()
        saved = self.store.get("guard")
        self.assertIsNone(saved["last"]["balance"], "the latest check failed")
        self.assertEqual(saved["last_good"], {"balance": 118.79, "at": good_at}, "the budget job reads this one")
        self.assertEqual(self.guard().last_good["balance"], 118.79, "a restart keeps it")

    def test_a_failed_read_while_braked_keeps_the_brake(self):
        self.reading = (20.0, 34.0)
        g = self.guard()
        g.check()
        self.assertFalse(g.allows())
        for _ in range(3):
            self.reading = (None, None)
            self.clock.advance(180)
            g.check()
            self.assertFalse(g.allows())
        self.reading = (99.0, 34.0)  # above the line but not above line + the release margin
        self.clock.advance(180)
        g.check()
        self.assertFalse(g.allows())
        actions = [e["payload"]["action"] for e in self.store.events_after(0) if e["kind"] == "swarm.guard"]
        self.assertEqual(actions, ["brake"], "never released by a failed read")

    def test_a_stale_reading_does_not_allow(self):
        g = self.guard()
        g.check()
        self.assertTrue(g.allows())
        self.clock.advance(601)
        self.assertFalse(g.allows(), "no reading for ten minutes: no new cycle or box")

    def test_a_filling_disk_brakes(self):
        g = SailGuard(self.store, self.settings, lambda: self.reading, clock=self.clock, disk_free=lambda: 2.0 * 2 ** 30)
        g.check()
        self.assertFalse(g.allows())
        self.assertIn("disk", g.reason)

    def test_a_restart_remembers_the_brake(self):
        self.reading = (10.0, 34.0)
        self.guard().check()
        self.assertFalse(self.guard().allows())

    def test_due_every_few_minutes(self):
        g = self.guard()
        self.assertTrue(g.due())
        g.check()
        self.assertFalse(g.due())
        self.clock.advance(181)
        self.assertTrue(g.due())


class Budget(GuardCase):
    """THE BUDGET's day (league/ops/budget.py `sail_caps`): the swarm's own Sail under the research dollars, Sail's own
    meter under research + fixed; no block is the floor, a malformed one is no research."""

    def budget(self, sail, fixed=None):
        self.settings["budget"] = {"source": "budget.json", "sail_usd_day": sail, "claude_usd_day": 2.0,
                                   "fixed_sail_usd_day": fixed}

    def test_the_swarms_sail_today_is_capped_by_the_research_dollars(self):
        self.budget(6.0)
        self.reading = (5000.0, 5.0)
        g = self.guard()
        self.store.add_spend("sail_model", 5.0)
        out = g.check()
        self.assertTrue(g.allows(), g.reason)
        self.assertEqual((out["budget_research_usd_day"], out["budget_account_usd_day"]), (6.0, 7.0))
        self.store.add_spend("gym_box", 1.0)
        g.check()
        self.assertFalse(g.allows())
        self.assertIn("research budget is spent", g.reason)
        self.clock.advance(86400)  # a new UTC day: its own budget
        g.check()
        self.assertTrue(g.allows(), g.reason)

    def test_sails_own_meter_is_capped_by_research_plus_fixed(self):
        self.budget(6.0, fixed=2.5)  # measured fixed above the configured House burn of 1.0
        self.reading = (5000.0, 5.0)
        g = self.guard()
        g.check()
        for balance in (4995.0, 4991.5):  # $8.50 metered by Sail today, none of it booked by the swarm
            self.reading = (balance, 5.0)
            self.clock.advance(180)
            g.check()
        self.assertFalse(g.allows())
        self.assertIn("by Sail's meter", g.reason)
        self.assertIn("8.50 of 8.50", g.reason)

    def test_a_raise_lifts_the_cap_and_a_cut_brakes_at_once(self):
        self.budget(2.0)
        self.reading = (5000.0, 5.0)
        g = self.guard()
        self.store.add_spend("sail_model", 3.0)
        g.check()
        self.assertFalse(g.allows())
        self.budget(9.0)  # the next settings.load carries a raise
        self.clock.advance(180)
        g.check()
        self.assertTrue(g.allows(), g.reason)
        self.budget(1.0)
        self.clock.advance(180)
        g.check()
        self.assertFalse(g.allows())

    def test_a_budget_of_zero_brakes_with_no_spend_at_all(self):
        self.budget(0.0)
        self.reading = (5000.0, 5.0)
        g = self.guard()
        g.check()
        self.assertFalse(g.allows())

    def test_no_block_is_the_floor_and_a_malformed_block_is_no_research(self):
        from league.ops import budget as B

        del self.settings["budget"]
        self.reading = (5000.0, 5.0)
        g = self.guard()
        out = g.check()
        self.assertEqual(out["budget_research_usd_day"], B.floor_usd_day("sail"))
        self.assertTrue(g.allows())
        self.store.add_spend("sail_model", B.floor_usd_day("sail"))
        g.check()
        self.assertFalse(g.allows(), "the floor binds")
        for bad in ({"sail_usd_day": "lots"}, {"sail_usd_day": -1}, {"sail_usd_day": float("nan")}, "budget", {}):
            self.settings["budget"] = bad
            self.assertEqual(g.check()["budget_research_usd_day"], 0.0, bad)

    def test_the_burst_trio_changes_nothing(self):
        self.budget(2.0)
        self.settings["guard"].update(burst_cap_usd=900.0, burst_until="2026-12-31T00:00:00Z", after_burst_usd_day=500.0)
        self.reading = (5000.0, 5.0)
        g = self.guard()
        self.store.add_spend("sail_model", 2.5)
        out = g.check()
        self.assertFalse(g.allows())
        self.assertNotIn("in_burst", out)
        self.assertNotIn("burst_spent", out)

    def test_the_sites_meter_since_the_start_is_still_kept(self):
        g = self.guard()
        self.reading = (5000.0, 34.0)
        g.check()
        for balance in (4900.0, 4800.0):
            self.reading = (balance, 34.0)
            self.clock.advance(180)
            g.check()
        self.reading = (6000.0, 34.0)  # a top-up is not negative spend
        self.clock.advance(180)
        out = g.check()
        self.assertEqual(out["metered_spent"], 200.0)
        self.assertIsNotNone(self.store.get("burst_started_at"))


if __name__ == "__main__":
    unittest.main()
