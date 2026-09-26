"""The Sail guard (league/swarm/guard.py): the swarm brakes to zero before the House is at risk."""

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

BURST_END = dt.datetime(2026, 9, 28, 13, 30, tzinfo=dt.timezone.utc).timestamp()


class GuardCase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.clock = Clock(BURST_END - 2 * 86400)
        self.store = SwarmStore(Path(self.dir.name), clock=self.clock)
        self.addCleanup(self.store.close)
        self.reading = (118.79, 34.0)
        self.settings = copy.deepcopy(S.DEFAULTS)

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

    def test_the_burst_cap(self):
        self.reading = (5000.0, 34.0)
        g = self.guard()
        self.store.add_spend("sail_model", 349.0)
        g.check()
        self.assertTrue(g.allows())
        self.store.add_spend("gym_box", 1.5)
        g.check()
        self.assertFalse(g.allows())
        self.assertIn("burst", g.reason)

    def test_after_the_burst_a_daily_allowance(self):
        self.clock.advance(BURST_END + 86400 * 3 + 3600 - self.clock())
        self.reading = (5000.0, 5.0)
        g = self.guard()
        self.store.add_spend("sail_model", 9.0)
        g.check()
        self.assertTrue(g.allows())
        self.store.add_spend("sail_model", 1.5)
        g.check()
        self.assertFalse(g.allows(), "12 a day less the House's 2")

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

    def test_the_burst_cap_also_reads_sails_own_meter(self):
        g = self.guard()
        self.reading = (5000.0, 34.0)
        g.check()
        for balance in (4900.0, 4800.0, 4700.0, 4640.0):  # $360 metered by Sail, none of it booked by the swarm
            self.reading = (balance, 34.0)
            self.clock.advance(180)
            g.check()
        self.assertFalse(g.allows())
        self.assertIn("burst", g.reason)
        self.reading = (6000.0, 34.0)  # a top-up is not negative spend
        self.clock.advance(180)
        out = g.check()
        self.assertEqual(out["metered_spent"], 360.0)

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


if __name__ == "__main__":
    unittest.main()
