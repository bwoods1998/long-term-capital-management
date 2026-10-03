"""The Sail guard (league/swarm/guard.py): the swarm brakes to zero before the House is at risk, and inside THE BUDGET's
day (league/ops/budget.py, LTCM v3: the burst trio is gone)."""

from __future__ import annotations

import copy
import datetime as dt
import tempfile
import unittest
from pathlib import Path

from league.ops import budget as B
from league.swarm import settings as S
from league.swarm.guard import BUDGET_CAUSES, CAUSES, RESEARCH_KINDS, SailGuard, causes_of, house_line
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
        # The largest budget there is (the owner's ceiling: a block that says more is held to it), and nothing booked
        # today, so each test meets only the line it is about (the Budget tests set their own).
        self.settings["budget"] = {"source": "budget.json", "sail_usd_day": B.ceiling_usd_day("sail"), "claude_usd_day": 0.0,
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

    def test_the_line_and_its_release_are_one_arithmetic(self):
        """`house_line`: what `check` brakes and releases by, and what THE BUDGET's Sail reserve is read from
        (league/ops/budget.py), so the rule's zero point cannot drift from the guard's line."""
        self.assertEqual(house_line(S.DEFAULTS["guard"]), {"house": 1.0, "line": 32.0, "release": 37.0})
        self.assertEqual(house_line({}), {"house": 1.0, "line": 32.0, "release": 37.0}, "the guard's own defaults")
        self.assertEqual(house_line(None), house_line({}))
        self.assertEqual(house_line({"house_burn_usd_day": 2.0, "margin_usd": 10.0, "release_margin_usd": 1.0}, 34.0),
                         {"house": 34.0, "line": 78.0, "release": 79.0}, "a measured burn over the configured one")
        self.assertEqual(house_line({"house_burn_usd_day": 2.0}, 0.5)["house"], 2.0, "never below the configured burn")
        # (Each line is over the last one's release line: the balance only rises, so Sail's meter books nothing.)
        for cfg, reading in (({"margin_usd": 12.0, "release_margin_usd": 3.0}, 5.0), ({}, 5.0),
                             ({"measured_burn": True, "house_burn_usd_day": 2.0}, 34.0)):
            self.settings["guard"] = {**S.DEFAULTS["guard"], **cfg}
            lines = house_line(self.settings["guard"], reading if cfg.get("measured_burn") else 0.0)
            self.reading = (lines["line"] - 0.01, reading)
            g = self.guard()
            out = g.check()
            self.assertEqual((out["line"], g.causes), (round(lines["line"], 2), ["under_line"]), cfg)
            self.reading = (lines["release"] - 0.01, reading)
            self.clock.advance(180)
            g.check()
            self.assertEqual(g.causes, ["under_line"], "over the line and under the release line: a braked guard stays")
            self.reading = (lines["release"], reading)
            self.clock.advance(180)
            g.check()
            self.assertEqual((g.allows(), g.causes), (True, []), cfg)


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
        self.clock.t = T - 16 * 3600  # in the trailing 24 hours and before 00:00 UTC: none of today's budget
        self.store.add_spend("sail_model", 30.0)
        self.clock.t = T
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


class Reserve(GuardCase):
    """THE GATE NEVER WAITS FOR MIDNIGHT: the last tenth of the day's Sail research dollars (at least $0.50) is kept for
    the tournament's validation round, the gate round and the nightly forward. Researcher cycles, births and the
    architect stop at the line under it (a hold, no brake); those three go on to the day's cap."""

    #: What `Swarm` asks the guard for: its rounds and the Gym's boxes by the default kind and the box kinds, new research
    #: by `RESEARCH_KINDS`.
    GATE = ("any", "gym", "gate", "tournament", "forward")

    def budget(self, sail, fixed=None):
        self.settings["budget"] = {"source": "budget.json", "sail_usd_day": sail, "claude_usd_day": 2.0,
                                   "fixed_sail_usd_day": fixed}

    def allowed(self, g):
        """(the gate's kinds allowed, the research kinds allowed): each all or none."""
        gate, research = {g.allows(kind) for kind in self.GATE}, {g.allows(kind) for kind in RESEARCH_KINDS}
        self.assertEqual((len(gate), len(research)), (1, 1))
        self.assertEqual(g.allows(), g.allows("any"))
        return gate.pop(), research.pop()

    def actions(self):
        return [e["payload"]["action"] for e in self.store.events_after(0) if e["kind"] == "swarm.guard"]

    def test_the_reserve_is_a_tenth_of_the_day_and_at_least_fifty_cents(self):
        from league.ops import budget as B

        self.assertEqual((B.GATE_RESERVE_SHARE, B.GATE_RESERVE_MIN_USD), (0.10, 0.50))
        self.assertEqual([B.gate_reserve(usd) for usd in (15.0, 7.2, 5.0, 3.0, 0.6, 0.5, 0.4, 0.0)],
                         [1.5, 0.72, 0.5, 0.5, 0.5, 0.5, 0.4, 0.0], "never more than the day's own dollars")
        self.assertEqual([B.gate_reserve(bad) for bad in ("lots", None, -1, float("nan"), True)], [0.0] * 5)
        self.assertEqual(RESEARCH_KINDS, ("research", "architect", "birth", "diagnostician"))

    def test_research_stops_at_ninety_percent_and_the_gate_goes_on_to_the_cap(self):
        self.budget(15.0)  # the owner's ceiling on Sail: the last $1.50 is the gate's
        self.reading = (5000.0, 5.0)
        g = self.guard()
        self.store.add_spend("gym_box", 9.0)
        self.store.add_spend("sail_model", 4.49)
        out = g.check()
        self.assertEqual((out["gate_reserve_usd"], out["research_held"], out["held"]), (1.5, False, ""))
        self.assertEqual(self.allowed(g), (True, True), "13.49 of 15.00: everything runs")
        self.store.add_spend("sail_model", 0.01)
        self.clock.advance(180)
        out = g.check()
        self.assertEqual(self.allowed(g), (True, False), "13.50 of 15.00: no new research, and the gate goes on")
        self.assertEqual((g.braked, g.reason, g.causes), (False, "", []), "a hold is no brake: no cause, no reason")
        self.assertEqual(out["held"], "today's Sail research is at its line (13.50 of 15.00): the last 1.50 is kept for "
                                      "validation, the gate and the nightly forward")
        saved = self.store.get("guard")
        self.assertEqual((saved["braked"], saved["research_held"], saved["held"]), (False, True, out["held"]))
        self.store.add_spend("gym_box", 1.49)  # validation, the look and the forward spend inside the reserve
        self.clock.advance(180)
        g.check()
        self.assertEqual(self.allowed(g), (True, False), "14.99 of 15.00: the gate still runs")
        self.store.add_spend("gym_box", 0.01)
        self.clock.advance(180)
        g.check()
        self.assertEqual(self.allowed(g), (False, False), "the day's cap: everything stops until 00:00 UTC")
        self.assertEqual(g.causes, ["research_budget"])
        self.clock.advance(86400)  # a new UTC day: its own budget and its own reserve
        g.check()
        self.assertEqual(self.allowed(g), (True, True))
        self.assertEqual((g.research_held, g.held), (False, ""))
        self.assertEqual(self.actions(), ["release", "research_hold", "brake", "release", "research_release"],
                         "each change is said: the first reading, the hold, the cap, the new day and its hold's end")

    def test_sails_own_meter_holds_research_at_the_same_reserve(self):
        self.budget(6.0, fixed=2.5)  # the account cap is 8.50; the reserve of a $6 day is $0.60
        self.reading = (5000.0, 5.0)
        g = self.guard()
        g.check()
        self.reading = (4992.5, 5.0)  # $7.50 metered by Sail today, none of it booked by the swarm
        self.clock.advance(180)
        g.check()
        self.assertEqual(self.allowed(g), (True, True), "7.50 of 8.50: under the line at 7.90")
        self.reading = (4992.0, 5.0)
        self.clock.advance(180)
        out = g.check()
        self.assertEqual(self.allowed(g), (True, False), "8.00 of 8.50: inside the reserve by Sail's meter")
        self.assertIn("by Sail's meter (8.00 of 8.50 for the account)", out["held"])
        self.reading = (4991.5, 5.0)
        self.clock.advance(180)
        g.check()
        self.assertEqual(self.allowed(g), (False, False))
        self.assertEqual(g.causes, ["account_budget"])

    def test_a_small_day_is_the_gates_first(self):
        """Under a dollar a day the reserve's fifty cents are most of it; under fifty cents all of it: the research that
        is left to do is the gate's."""
        self.reading = (5000.0, 5.0)
        self.budget(0.6)
        g = self.guard()
        g.check()
        self.assertEqual(self.allowed(g), (True, True))
        self.store.add_spend("sail_model", 0.10)
        self.clock.advance(180)
        g.check()
        self.assertEqual(self.allowed(g), (True, False), "0.10 of 0.60: the last 0.50 is the gate's")
        self.budget(0.4)
        self.clock.advance(86400)
        out = g.check()
        self.assertEqual((out["gate_reserve_usd"], self.allowed(g)), (0.4, (True, False)), "nothing spent: all of it is the gate's")
        self.budget(0.0)
        self.clock.advance(180)
        g.check()
        self.assertEqual((self.allowed(g), g.causes), ((False, False), ["research_budget"]), "no dollars brake at once, as ever")

    def test_a_low_or_unreadable_balance_still_stops_everything(self):
        self.budget(15.0)
        self.reading = (40.0, 5.0)  # over the House's line of 32 (and the 37 a braked guard releases at)
        g = self.guard()
        self.store.add_spend("gym_box", 14.0)
        g.check()
        self.assertEqual(self.allowed(g), (True, False), "inside the reserve: the gate runs")
        for reading, cause in (((31.5, 5.0), "under_line"), ((None, None), "balance_unreadable")):
            self.reading = reading
            self.clock.advance(180)
            g.check()
            self.assertEqual((self.allowed(g), g.causes), ((False, False), [cause]), "the House at risk: the gate stops too")
            self.assertTrue(g.research_held, "the hold stands under the brake: it is the brake that answers")
            self.reading = (40.0, 5.0)
            self.clock.advance(180)
            g.check()
            self.assertEqual(self.allowed(g), (True, False))
        # A reading gone stale and a full disk are the same: nothing is allowed, reserve or not.
        self.clock.advance(float(self.settings["guard"].get("stale_seconds", 600)) + 1)
        self.assertEqual(self.allowed(g), (False, False))
        low = SailGuard(self.store, self.settings, lambda: self.reading, clock=self.clock, disk_free=lambda: 1.0 * 2 ** 30)
        low.check()
        self.assertEqual((self.allowed(low), low.causes), ((False, False), ["disk"]))

    def test_a_raise_ends_the_hold_and_a_restart_keeps_it(self):
        self.budget(6.0)
        self.reading = (5000.0, 5.0)
        g = self.guard()
        self.store.add_spend("sail_model", 5.5)
        g.check()
        self.assertEqual(self.allowed(g), (True, False), "5.50 of 6.00 with 0.60 kept")
        again = self.guard()  # a restarted swarm reads the record before its first check
        self.assertEqual((again.braked, again.research_held, again.held), (False, True, g.held))
        self.budget(9.0)  # the next settings.load carries a raise: 5.50 of 9.00 with 0.90 kept
        self.clock.advance(180)
        g.check()
        self.assertEqual(self.allowed(g), (True, True))
        self.assertEqual(self.actions(), ["release", "research_hold", "research_release"],
                         "the first reading releases the guard and finds the hold in the same check")

    def test_caps_that_are_no_reading_of_the_rule_keep_nothing_and_brake(self):
        self.reading = (5000.0, 5.0)
        self.settings["budget"] = {"sail_usd_day": "lots"}
        g = self.guard()
        out = g.check()
        self.assertEqual((out["gate_reserve_usd"], out["research_held"], g.causes), (0.0, False, ["budget_unreadable"]))
        self.assertEqual(self.allowed(g), (False, False))

    def job(self, balance, previous=None):
        """One run of the budget job's rule on a Sail balance (its reserve the guard's own release line, as the job reads
        it), and the `budget` block the next `settings.load` carries."""
        doc = B.compute({"p30_usd": 0.0, "p30_source": "test", "edge": {"stop": False, "why": "test"}, "meters": {
            "sail": {"balance_usd": balance, "fixed_usd_day": 1.0, "need_usd": 0.0,
                     "reserve_usd": house_line(self.settings["guard"])["release"]},
            "claude": {"balance_usd": 500.0, "fixed_usd_day": 0.0, "need_usd": 0.0}}}, now=self.clock(), previous=previous)
        self.budget(doc["meters"]["sail"]["research_usd_day"], fixed=1.0)
        return doc

    def test_the_jobs_second_run_of_the_day_leaves_the_gate_its_reserve(self):
        """The budget job runs at 00:30 UTC and again after the close economics, on a balance that has paid for the
        day's research. On a taper day a cap recomputed from that reading lands under what the day has booked, and the
        guard would brake the gate with everything else until 00:00 UTC. The day's figure is set once
        (league/ops/budget.py): the cap stands, and the gate goes on to it."""
        self.clock.t = T - T % 86400 + 1800  # 00:30 UTC
        self.reading = (100.0, 5.0)
        morning = self.job(100.0)
        g = self.guard()
        g.check()
        self.assertEqual((morning["meters"]["sail"]["research_usd_day"], self.allowed(g)), (11.6, (True, True)),
                         "(100 - 37 - 5 x 1) / 5: a taper day")
        self.clock.advance(19 * 3600 + 2400)  # 20:10 UTC, after the close economics
        self.store.add_spend("gym_box", 6.0)
        self.store.add_spend("sail_model", 4.0)  # 10.00 booked: 86% of the day's cap, under its hold line at 10.44
        self.reading = (100.0 - 10.0 - 0.85, 5.0)
        g.check()
        self.assertEqual(self.allowed(g), (True, True))
        evening = self.job(self.reading[0], previous=morning)
        sail = evening["meters"]["sail"]
        self.assertEqual((sail["research_usd_day"], sail["would_set_usd_day"]), (11.6, 9.43),
                         "this reading alone would set (89.15 - 42) / 5: under the 10.00 the day has booked")
        self.clock.advance(180)
        g.check()
        self.assertEqual((self.allowed(g), g.braked, g.causes), ((True, True), False, []), "the day's cap stands")
        self.store.add_spend("gym_box", 0.5)
        self.reading = (self.reading[0] - 0.5, 5.0)
        self.clock.advance(180)
        g.check()
        self.assertEqual(self.allowed(g), (True, False), "10.50 of 11.60: the hold, and the gate goes on to the cap")
        # The control: the same reading as a day's first run (no earlier run today) is the cap the old rule set here.
        naive = self.job(self.reading[0])
        self.assertLess(naive["meters"]["sail"]["research_usd_day"], 10.5)
        self.clock.advance(180)
        g.check()
        self.assertEqual((self.allowed(g), g.causes), ((False, False), ["research_budget"]))

    def test_the_taper_never_meets_the_houses_line(self):
        """A prefund left alone, each day spent whole: the guard stops each day at the day's cap (the budget's own
        designed stop) and releases the next morning, down to a day with no research at all. The balance is then still
        over the line a braked guard releases at: research never drains the meter until the House's line stops the gate."""
        lines = house_line(self.settings["guard"])
        self.clock.t = T - T % 86400 + 1800  # 00:30 UTC
        balance, days, g = 150.0, 0, None
        while True:
            research = self.job(balance)["meters"]["sail"]["research_usd_day"]  # each day's first run
            self.reading = (balance, 5.0)
            g = g or self.guard()
            g.check()
            if research == 0.0:
                break
            # (A day of under fifty cents is all the gate's: `test_a_small_day_is_the_gates_first`.)
            self.assertEqual((self.allowed(g), g.causes), ((True, research > B.gate_reserve(research)), []), (days, balance))
            self.store.add_spend("gym_box", research)
            balance -= research + 1.0
            self.reading = (balance, 5.0)
            self.clock.advance(23 * 3600)
            g.check()
            self.assertEqual(g.causes, ["research_budget"], f"day {days}: the day's cap, never the House's line")
            self.clock.advance(3600)
            days += 1
            self.assertLess(days, 100)
        self.assertEqual(g.causes, ["research_budget"], "no research dollars: the budget's own stop, not the House at risk")
        self.assertGreater(days, 10)
        self.assertGreater(balance, lines["release"])
        self.assertGreater(lines["release"], lines["line"])


class Causes(GuardCase):
    """The brake's causes by name beside the human reason (`CAUSES`, one per braking branch of `check`): the record, its
    `last` and the event carry the same list, and a record kept before the list reads as cause unknown."""

    def budget(self, sail, fixed=None):
        self.settings["budget"] = {"source": "budget.json", "sail_usd_day": sail, "claude_usd_day": 2.0,
                                   "fixed_sail_usd_day": fixed}

    def check(self, g):
        """One check; wherever the list is kept it is the same list, named from CAUSES, and empty exactly when unbraked."""
        out = g.check()
        saved = self.store.get("guard")
        self.assertEqual((out["causes"], saved["causes"], saved["last"]["causes"], causes_of(saved)), (g.causes,) * 4)
        self.assertLessEqual(set(g.causes), set(CAUSES))
        self.assertEqual((bool(g.causes), bool(g.reason)), (g.braked, g.braked))
        return g.causes

    def test_the_budgets_causes_are_two_of_the_names(self):
        self.assertEqual(CAUSES, ("balance_unreadable", "under_line", "research_budget", "account_budget", "budget_unreadable",
                                  "disk", "no_reading"))
        self.assertEqual(BUDGET_CAUSES, ("research_budget", "account_budget"), "a rule that could not be read is not one")

    def test_before_a_first_check_the_cause_is_no_reading(self):
        g = self.guard()
        self.assertEqual((g.braked, g.reason, g.causes, g.last), (True, "no reading yet", ["no_reading"], {}))
        self.assertIsNone(self.store.get("guard"), "nothing is stored before a check")

    def test_a_guard_that_allows_names_no_cause(self):
        g = self.guard()
        self.assertEqual(self.check(g), [])
        self.assertTrue(g.allows())

    def test_an_unreadable_balance(self):
        g = self.guard()
        self.reading = (None, None)
        self.assertEqual(self.check(g), ["balance_unreadable"], "on the first check")
        self.reading = (118.79, 34.0)
        self.clock.advance(180)
        self.assertEqual(self.check(g), [])
        self.reading = (None, None)
        self.clock.advance(180)
        self.assertEqual(self.check(g), ["balance_unreadable"], "and from an unbraked guard")

    def test_a_reader_that_raises_is_an_unreadable_balance(self):
        def down():
            raise OSError("no route to Sail")

        g = SailGuard(self.store, self.settings, down, clock=self.clock, disk_free=lambda: 100.0 * 2 ** 30)
        self.assertEqual(self.check(g), ["balance_unreadable"])

    def test_a_balance_under_the_line(self):
        self.reading = (31.0, 31.0)
        self.assertEqual(self.check(self.guard()), ["under_line"])

    def test_the_days_research_budget(self):
        self.budget(6.0)
        self.reading = (5000.0, 5.0)
        g = self.guard()
        self.store.add_spend("sail_model", 6.0)
        self.assertEqual(self.check(g), ["research_budget"])
        self.assertIn("research budget is spent", g.reason)

    def test_the_days_account_budget_by_sails_meter(self):
        self.budget(6.0, fixed=2.5)
        self.reading = (5000.0, 5.0)
        g = self.guard()
        self.assertEqual(self.check(g), [])
        self.reading = (4991.5, 5.0)  # $8.50 metered by Sail today, none of it booked by the swarm
        self.clock.advance(180)
        self.assertEqual(self.check(g), ["account_budget"])
        self.assertIn("by Sail's meter", g.reason)
        self.store.add_spend("sail_model", 6.0)  # the research cap is read first: one budget cause at a time
        self.clock.advance(180)
        self.assertEqual(self.check(g), ["research_budget"])

    def test_a_budget_of_zero_the_rule_itself_gives_is_the_budgets_own(self):
        from league.ops import budget as B

        self.reading = (5000.0, 5.0)
        for block in ({"source": "budget.json", "sail_usd_day": 0.0, "claude_usd_day": 0.0, "fixed_sail_usd_day": None},
                      {"sail_usd_day": 0}):
            self.settings["budget"] = block
            g = self.guard()
            self.assertEqual(self.check(g), ["research_budget"], block)
            self.clock.advance(180)
        del self.settings["budget"]  # the guard's own read of the root's budget.json: none is the floor, which binds
        g = self.guard()
        self.assertEqual(self.check(g), [])
        self.store.add_spend("sail_model", B.floor_usd_day("sail"))
        self.clock.advance(180)
        self.assertEqual(self.check(g), ["research_budget"])

    def unread(self, source):
        """One check of a guard on a balance far above the line: braked at no research, as it always was, and named
        apart from the budget's own daily stop."""
        self.reading = (5000.0, 5.0)
        g = self.guard()
        self.assertEqual(self.check(g), ["budget_unreadable"])
        self.assertEqual((g.braked, g.allows(), g.reason),
                         (True, False, f"today's Sail research budget is spent (0.00 of 0.00; {source})"))
        self.assertEqual(g.last["budget_research_usd_day"], 0.0)
        self.assertFalse(set(g.causes) & set(BUDGET_CAUSES))
        return g

    def test_a_rule_that_could_not_run_is_not_the_budgets_own(self):
        from unittest import mock

        from league.ops import budget as B

        with mock.patch.object(B, "overlay", side_effect=RuntimeError("boom")):
            self.settings = S.load(Path(self.dir.name), config={})  # the block `settings.load` writes for it
        self.assertEqual((self.settings["budget"]["sail_usd_day"], self.settings["budget"]["read"]), (0.0, False))
        self.unread("unavailable")

    def test_a_malformed_block_is_not_the_budgets_own(self):
        for bad in ({"sail_usd_day": "lots"}, {"sail_usd_day": -1}, {"sail_usd_day": float("nan")}, "budget", {},
                    {"source": "budget.json"}):
            self.settings["budget"] = bad
            self.unread("malformed budget block: no research")
            self.clock.advance(180)

    def test_a_rule_that_cannot_be_read_is_not_the_budgets_own(self):
        from unittest import mock

        from league.ops import budget as B

        with mock.patch.object(B, "sail_caps", side_effect=RuntimeError("boom")):
            g = self.unread("the budget rule could not be read (RuntimeError)")
        self.clock.advance(180)
        self.assertEqual(self.check(g), [], "the rule reads again: the guard releases as it always did")

    def test_caps_that_do_not_say_they_were_read_are_not_the_budgets_own(self):
        from unittest import mock

        from league.swarm import guard as G

        self.reading = (5000.0, 5.0)
        g = self.guard()
        self.check(g)
        self.reading = (4990.0, 5.0)  # $10 by Sail's meter today, none of it booked
        for caps, want in (({"research": 0.0, "fixed": 1.0, "account": 1.0, "source": "x"}, ["budget_unreadable"]),
                           ({"research": 0.0, "fixed": 1.0, "account": 1.0, "source": "x", "read": None}, ["budget_unreadable"]),
                           ({"research": 0.0, "fixed": 1.0, "account": 1.0, "source": "x", "read": "yes"}, ["budget_unreadable"]),
                           ({"research": 0.0, "fixed": 1.0, "account": 1.0, "source": "x", "read": True}, ["research_budget"]),
                           ({"research": 6.0, "fixed": 1.0, "account": 7.0, "source": "x", "read": False}, ["budget_unreadable"]),
                           ({"research": 6.0, "fixed": 1.0, "account": 7.0, "source": "x", "read": True}, ["account_budget"]),
                           ({"research": 6.0, "fixed": 9.0, "account": 15.0, "source": "x", "read": False}, [])):
            self.clock.advance(180)
            with mock.patch.object(G, "budget_caps", return_value=caps):
                self.assertEqual(self.check(g), want, caps)

    def test_a_filling_disk(self):
        g = SailGuard(self.store, self.settings, lambda: self.reading, clock=self.clock, disk_free=lambda: 2.0 * 2 ** 30)
        self.assertEqual(self.check(g), ["disk"])

    def test_several_causes_are_all_named_in_the_checks_order(self):
        self.budget(2.0)
        self.store.add_spend("gym_box", 2.0)
        self.reading = (None, None)
        g = SailGuard(self.store, self.settings, lambda: self.reading, clock=self.clock, disk_free=lambda: 2.0 * 2 ** 30)
        self.assertEqual(self.check(g), ["balance_unreadable", "research_budget", "disk"])
        self.reading = (20.0, 5.0)
        self.clock.advance(180)
        self.assertEqual(self.check(g), ["under_line", "research_budget", "disk"])
        self.settings["budget"] = "budget"  # a block that is no budget, in the budget's place in the order
        self.clock.advance(180)
        self.assertEqual(self.check(g), ["under_line", "budget_unreadable", "disk"])

    def test_a_budget_brake_under_the_release_line_names_the_line_too(self):
        self.budget(2.0)
        self.reading = (5000.0, 5.0)
        g = self.guard()
        self.assertEqual(self.check(g), [])
        self.store.add_spend("sail_model", 3.0)
        self.clock.advance(180)
        self.assertEqual(self.check(g), ["research_budget"], "the budget alone: the balance is far above the line")
        self.reading = (35.0, 5.0)  # over the $32 line, under the $37 a braked guard releases at
        self.clock.advance(180)
        self.assertEqual(self.check(g), ["under_line", "research_budget"])
        self.clock.advance(86400)  # a new UTC day lifts the budget's cause, never the line's
        self.assertEqual(self.check(g), ["under_line"])
        self.reading = (37.0, 5.0)
        self.clock.advance(180)
        self.assertEqual(self.check(g), [])

    def test_the_brake_and_release_events_carry_the_causes(self):
        self.budget(6.0)
        self.reading = (5000.0, 5.0)
        g = self.guard()
        self.store.add_spend("sail_model", 6.0)
        self.check(g)
        self.clock.advance(86400)
        self.check(g)
        events = [e["payload"] for e in self.store.events_after(0) if e["kind"] == "swarm.guard"]
        self.assertEqual([(e["action"], e["causes"], causes_of(e)) for e in events],
                         [("brake", ["research_budget"], ["research_budget"]), ("release", [], [])])
        self.assertIn("research budget is spent", events[0]["reason"], "the human reason is still beside them")

    def test_a_restart_remembers_the_causes(self):
        self.reading = (10.0, 34.0)
        self.check(self.guard())
        again = self.guard()
        self.assertEqual((again.braked, again.causes), (True, ["under_line"]))

    def test_a_record_kept_before_the_list_reads_as_cause_unknown_and_decides_as_before(self):
        reason = "today's Sail research budget is spent (5.00 of 5.00; budget.json)"
        last = {"balance": 118.79, "line": 32.0, "braked": True, "reason": reason, "at": T - 60}
        old = {"braked": True, "reason": reason, "last_ok": T - 60, "last": last, "last_good": {"balance": 118.79, "at": T - 60}}
        self.store.put("guard", old)
        g = self.guard()
        self.assertIsNone(g.causes, "unknown: never guessed from the reason's words")
        self.assertEqual((causes_of(old), causes_of(last)), (None, None))
        self.assertEqual((g.braked, g.reason, g.last, g.last_good), (True, reason, last, old["last_good"]), "the old fields read as before")
        self.assertFalse(g.allows())
        self.assertEqual(self.check(g), [], "the next check writes the list: 118.79 is above the release line")
        self.assertTrue(g.allows())

    def test_a_list_that_is_not_names_is_cause_unknown(self):
        for bad in (None, "research_budget", {"research_budget": True}, ["research_budget", 3], [None], ("research_budget",), 7):
            self.assertIsNone(causes_of({"braked": True, "causes": bad}), bad)
        for record in (None, "braked", [], 0):
            self.assertIsNone(causes_of(record), record)
        self.assertEqual(causes_of({"causes": []}), [], "an empty list is no brake, not unknown")
        self.store.put("guard", {"braked": True, "reason": "x", "causes": "research_budget"})
        self.assertIsNone(self.guard().causes)


if __name__ == "__main__":
    unittest.main()
