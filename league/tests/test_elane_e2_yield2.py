"""Release E2.2, E2'S OWN PACE INSIDE THE HOUSE'S SAIL DAY (league/swarm/elane_yield.py `pace_hour`, `usd_hour`,
`sail_day`, `hold`): `elane.e2.pace_share` is held to 0-4 (it was 0-0.5: at the ceiling the equity lanes stood still
for most of each hour while most of the day's Sail research dollars went unspent), and what bounds E2 in place of half
the researchers' line is held here:

- E2's pace is its own (`pace_share` x the Sail model line), its day `elane.e2.usd_day`, and never more than a day at
  that pace;
- THE LINE'S SHARE: whatever E2 spent in the hour, the loop's own `Swarm.pace_status` (league/swarm/loop.py, unchanged)
  takes at most half the line off the researchers' limit, so E2's dollars never pause them;
- THE HOUSE'S SAIL DAY: on the real Sail guard (league/swarm/guard.py `SailGuard`, the budget's `sail_caps`), E2 at four
  lines an hour stops a question's dollar before the line where the guard holds new research, read fresh before each
  call; the guard never has to hold anyone on E2's account; the day's Sail total never passes the guard's cap; and at
  the guard's cap E2 asks nothing, on the real loop too.

Every family, dollar and reading here is invented; no market data is read."""

from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from unittest import mock

from league.swarm import elane_births, elane_train, elane_yield
from league.swarm import guard as guard_mod
from league.swarm import settings as S
from league.swarm.guard import SailGuard
from league.swarm.loop import Swarm
from league.tests import REAL_POLICY_PATH
from league.tests import elane_e2_fakes as fx
from league.tests.test_swarm_loop import LoopCase

#: A UTC midnight (the fakes' clock starts 05:20 into this day).
MIDNIGHT = 1_790_380_800.0
#: The owner's ceiling as the budget hands it down: Sail $20 a research day, two fifths of it the hourly model line.
SAIL_DAY_USD = 20.0
LINE = SAIL_DAY_USD * 0.4 / 24


def lined(line: float = LINE, *, sail_usd_day: float | None = SAIL_DAY_USD, guard: dict | None = None, **e2) -> dict:
    """Settings with the Sail model line, the budget's block (None: no block) and E2's keys."""
    out = {**fx.settings(**e2), "researcher": {"sail_usd_per_hour": line, "usd_per_hour": 5},
           "guard": {"house_burn_usd_day": 1.0, "margin_usd": 30.0, "release_margin_usd": 5.0, **(guard or {})}}
    if sail_usd_day is not None:
        out["budget"] = {"sail_usd_day": sail_usd_day, "claude_usd_day": 5.0, "source": "an invented budget"}
    return out


class PaceCase(unittest.TestCase):
    def setUp(self):
        fx.switch_on(self)
        self.clock = fx.Clock(MIDNIGHT + 6 * 3600.0)
        self.store = fx.new_store(self, self.clock)
        self.n = 0

    def e2_row(self, usd: float) -> None:
        """A model call of E2's as the router books it (kind `sail_model`, its request key in the detail)."""
        self.n += 1
        key = f"swarm:elane:train:f:{self.n}:sail:pro_asap"
        self.store.add_spend("sail_model", usd, family="f", detail={"profile": "pro_asap", "key": key, "desk": "f"})

    def other_row(self, usd: float, kind: str = "sail_model") -> None:
        """A dollar of another lane's: an options researcher's model call, or a Gym box."""
        self.n += 1
        self.store.add_spend(kind, usd, family="opt", detail={"key": f"swarm:opt-family:c{self.n}:m0:0", "desk": "opt"})

    def sail_guard(self, settings: dict, balance: float = 500.0) -> SailGuard:
        """The real Sail guard on this store: a healthy balance and disk, so only THE BUDGET's day can hold or brake."""
        return SailGuard(self.store, settings, lambda: (balance, None), clock=self.clock, disk_free=lambda: 1e12)

    def sail_today(self) -> float:
        return self.store.spent(list(guard_mod.SWARM_SAIL_KINDS), since=MIDNIGHT + 86400.0 * ((self.clock() - MIDNIGHT) // 86400.0))

    def researchers(self, settings: dict) -> dict:
        """The options researchers' pace exactly as the loop computes it: league/swarm/loop.py `Swarm.pace_status`, the
        real function, on this store and these settings (read fresh: its spend is cached for 10 s)."""
        return Swarm.pace_status(SimpleNamespace(settings=settings, clock=self.clock, store=self.store,
                                                 _pace=(float("-inf"), "", 0.0, 0.0)))


class TheBound(PaceCase):
    def test_the_share_is_held_to_four_lines_and_ships_a_quarter(self):
        self.assertEqual(elane_yield.BOUNDS["pace_share"], (0.0, 4.0))
        self.assertEqual(elane_yield.BOUNDS["usd_day"], (0.0, 100.0))
        self.assertEqual((elane_yield.DEFAULTS["pace_share"], elane_yield.DEFAULTS["usd_day"]), (0.25, 8.0))
        self.assertEqual(elane_yield.cfg({})["pace_share"], 0.25)
        for raw, want in ((0.0, 0.0), (0.5, 0.5), (0.75, 0.75), (2, 2.0), (4.0, 4.0), (4.5, 0.25), (-1, 0.25), ("2", 0.25),
                          (True, 0.25), (float("inf"), 0.25)):
            self.assertEqual(elane_yield.cfg(lined(pace_share=raw))["pace_share"], want, raw)
        for raw, want in ((0.0, 0.0), (15, 15.0), (100, 100.0), (100.5, 8.0), (-1, 8.0)):
            self.assertEqual(elane_yield.cfg(lined(usd_day=raw))["usd_day"], want, raw)

    def test_the_committed_policy_still_ships_the_default(self):
        with open(REAL_POLICY_PATH, encoding="utf-8") as handle:
            policy = json.load(handle)
        self.assertEqual(policy["elane"]["e2"]["pace_share"], 0.25)
        self.assertEqual(policy["elane"]["e2"]["usd_day"], 8.0)

    def test_the_pace_is_e2s_own_and_the_day_is_usd_day_under_a_day_at_the_pace(self):
        four = lined(pace_share=4.0, usd_day=100.0)
        self.assertAlmostEqual(elane_yield.pace_hour(four), 4 * LINE)
        self.assertAlmostEqual(elane_yield.day_line(four), 4 * LINE * 24, msg="a day at the pace: $32 at the ceiling")
        self.assertAlmostEqual(elane_yield.day_line(lined(pace_share=4.0, usd_day=15.0)), 15.0, msg="usd_day is the cap")
        self.assertAlmostEqual(elane_yield.day_line(lined(pace_share=4.0)), 8.0, msg="the shipped day, unless it is raised")
        self.assertAlmostEqual(elane_yield.pace_hour(four, 1.0), 4.0, msg="a line handed in")
        # The budget tightens the pace with the line: at the floor's line four lines are four of the floor's.
        floor = lined(4.0 * 0.4 / 24, pace_share=4.0, usd_day=100.0)
        self.assertAlmostEqual(elane_yield.day_line(floor), 4 * 4.0 * 0.4)
        # E2 over its old bound and under its new pace is not held; at the pace it is, by its own pace.
        self.e2_row(0.5 * LINE + 0.05)
        self.assertIsNone(elane_yield.hold(self.store, four, self.clock()), "past half the line: no longer the bound")
        pace = elane_yield.pace(self.store, four, self.clock())
        self.assertEqual((pace["paused"], pace["share"]), (False, 4.0))
        self.assertAlmostEqual(pace["limit_usd_per_hour"], round(4 * LINE, 6))
        self.e2_row(3.5 * LINE)
        held = elane_yield.hold(self.store, four, self.clock())
        self.assertIn("at their $1.3333 pace", held)
        self.assertFalse(held.startswith(elane_yield.SAIL_DAY))
        rep = elane_yield.report(self.store, four, train_key=elane_train.STATE_KEY)
        self.assertEqual((rep["pace_share"], rep["usd_day"]), (4.0, 100.0))
        self.assertAlmostEqual(rep["usd_hour"], round(4 * LINE, 6), msg="the operator reads E2's own pace")
        self.assertAlmostEqual(rep["line_share_usd_hour"], round(0.5 * LINE, 6))


class TheLinesShare(PaceCase):
    """E2's dollars never pause the researchers: `Swarm.pace_status` (unchanged) takes what E2 spent in the hour, at most
    `elane_yield.usd_hour`, off their limit, and that is never more than half the line whatever E2's pace."""

    def test_what_the_loop_takes_is_the_share_up_to_a_half_and_never_more(self):
        self.assertEqual(elane_yield.LINE_SHARE_MAX, 0.5)
        for share, want in ((0.0, 0.0), (0.25, 0.25), (0.5, 0.5), (0.51, 0.5), (1.0, 0.5), (4.0, 0.5)):
            s = lined(pace_share=share)
            self.assertAlmostEqual(elane_yield.usd_hour(s), want * LINE, msg=share)
            self.assertAlmostEqual(elane_yield.usd_hour(s, 1.0), want, msg="the loop hands in its own reading of the line")
            self.assertLessEqual(elane_yield.usd_hour(s), elane_yield.pace_hour(s) + 1e-12)
        self.assertEqual(elane_yield.usd_hour(lined("x", pace_share=4.0)), 0.0, "an unreadable line: nothing")

    def test_e2_at_four_lines_in_the_hour_never_pauses_the_researchers(self):
        four = lined(pace_share=4.0, usd_day=100.0)
        # E2 spent four whole lines in the hour: before LINE_SHARE_MAX that came off the researchers' limit entire and
        # every options researcher slept (their limit less four lines is under zero).
        self.e2_row(4 * LINE)
        pace = self.researchers(four)
        self.assertEqual((pace["spent_last_hour_usd"], pace["paused"]), (0.0, False), pace)
        self.assertAlmostEqual(pace["equity"]["taken_usd"], 0.5 * LINE, places=6)
        self.assertAlmostEqual(pace["equity"]["spent_last_hour_usd"], 4 * LINE, places=6)
        # The researchers keep half their line whatever E2 spent over it: under it they run, at it they pause.
        self.other_row(0.5 * LINE - 0.001)
        self.assertFalse(self.researchers(four)["paused"])
        self.e2_row(40 * LINE)
        self.assertFalse(self.researchers(four)["paused"], "ten times more of E2's dollars move nothing of theirs")
        self.other_row(0.002)
        pace = self.researchers(four)
        self.assertTrue(pace["paused"], "their own spend, at their own half")
        self.assertAlmostEqual(pace["spent_last_hour_usd"], 0.5 * LINE + 0.001, places=6)
        # E2 itself waits, at its own pace.
        self.assertIn("pace", elane_yield.hold(self.store, four, self.clock()))

    def test_at_the_shipped_quarter_nothing_moved(self):
        quarter = lined()
        self.e2_row(3 * LINE)
        pace = self.researchers(quarter)
        self.assertAlmostEqual(pace["equity"]["taken_usd"], 0.25 * LINE, places=6)
        self.assertAlmostEqual(pace["equity"]["limit_usd_per_hour"], 0.25 * LINE, places=6)
        self.other_row(0.75 * LINE - 0.001)
        self.assertFalse(self.researchers(quarter)["paused"])
        self.other_row(0.002)
        self.assertTrue(self.researchers(quarter)["paused"], "the two together fit the line, as before")


class TheSailDay(PaceCase):
    """THE HOUSE'S SAIL DAY on the real Sail guard and the budget's own caps."""

    def setUp(self):
        super().setUp()
        self.settings = lined(pace_share=4.0, usd_day=100.0)
        self.guard = self.sail_guard(self.settings)

    def test_the_guards_kinds_and_record_are_the_ones_e2_reads(self):
        self.assertEqual(elane_yield.SAIL_KINDS, guard_mod.SWARM_SAIL_KINDS)
        self.assertIsNone(self.store.get(elane_yield.GUARD_KEY), "no guard has checked on this store")
        self.assertIsNone(elane_yield.sail_day(self.store, self.settings, self.clock()), "no record: nothing held here")
        last = self.guard.check()
        record = self.store.get(elane_yield.GUARD_KEY)
        self.assertEqual((record["braked"], record["research_held"]), (False, False), record)
        caps = guard_mod.budget_caps(self.settings, self.store.root, self.clock())
        self.assertEqual((caps["research"], caps["gate_reserve"], caps["read"]), (20.0, 2.0, True))
        self.assertEqual((last["budget_research_usd_day"], last["gate_reserve_usd"]), (20.0, 2.0),
                         "the keys of the record `sail_day` reads")
        self.assertIsNone(elane_yield.sail_day(self.store, self.settings, self.clock()))
        self.assertEqual(elane_yield.SAIL_ROOM_USD, 1.0)

    def test_e2_stops_a_dollar_before_the_guards_line_between_two_of_its_checks(self):
        # 06:00 UTC: the day's even pace is 20 x (0.25 + 0.05) = $6.00 due by now; the research line is $18.
        self.guard.check()
        self.assertTrue(self.guard.allows("research"))
        self.other_row(4.99, kind="gym_box")
        self.assertIsNone(elane_yield.hold(self.store, self.settings, self.clock()), "4.99 of 6.00 less a dollar")
        self.other_row(0.02)
        held = elane_yield.hold(self.store, self.settings, self.clock())
        self.assertTrue(held.startswith(elane_yield.SAIL_DAY), held)
        self.assertIn("the day's even pace", held)
        # The guard's own record still allows new research (it last checked before those dollars): E2 read the day fresh.
        self.assertEqual(self.store.get(elane_yield.GUARD_KEY)["research_held"], False)
        self.assertTrue(self.guard.allows("research"))
        self.assertLess(self.sail_today(), 6.0, "and E2 stopped before the guard's own line")
        # With the even pace off the line is the cap less the gate's reserve: 18.00, so E2 stops at 17.00.
        flat = lined(pace_share=4.0, usd_day=100.0, guard={"pace_day": False})
        self.assertIsNone(elane_yield.sail_day(self.store, flat, self.clock()))
        self.other_row(11.97, kind="gym_box")
        self.assertIsNone(elane_yield.sail_day(self.store, flat, self.clock()), "16.98")
        self.other_row(0.04)
        held = elane_yield.sail_day(self.store, flat, self.clock())
        self.assertIn("its research line $18.00", held)

    def test_at_the_guards_cap_e2_asks_nothing(self):
        asked: list = []
        router = fx.FakeRouter(lambda call: asked.append(call) or fx.answer([]))
        researcher = elane_train.EquityResearcher(self.store, router, self.settings, runner=fx.FakeRunner(), clock=self.clock)
        fx.e2_family(self.store, "needs-a-program")
        # THE GATE'S RESERVE: the day's spend inside the reserve under the cap. The guard holds new research.
        self.other_row(18.0, kind="gym_box")
        self.guard.check()
        self.assertEqual((self.guard.braked, self.guard.research_held), (False, True))
        held = elane_yield.hold(self.store, self.settings, self.clock())
        self.assertTrue(held.startswith(elane_yield.SAIL_DAY) and "holds new research" in held, held)
        step = researcher.step(self.store.family("needs-a-program"))
        self.assertEqual(step.get("skipped"), held)
        self.assertTrue(researcher.idle(), "a family that must ask a model is no work while the Sail day holds E2")
        births = elane_births.EquityPass(SimpleNamespace(store=self.store, router=router, settings=self.settings,
                                                         clock=self.clock)).run()
        self.assertEqual((births.get("skipped"), births.get("why")), ("sail_day", held))
        self.assertFalse(elane_births.due(self.store, self.settings, now=self.clock()))
        # The cap itself: the guard brakes, and E2 reads the brake.
        self.other_row(2.0, kind="gym_box")
        self.guard.check()
        self.assertTrue(self.guard.braked)
        self.assertIn("research_budget", self.guard.causes)
        held = elane_yield.hold(self.store, self.settings, self.clock())
        self.assertIn("the Sail guard is braked", held)
        self.assertEqual(researcher.step(self.store.family("needs-a-program")).get("skipped"), held)
        self.assertEqual(asked, [], "no model was asked")
        self.assertEqual(elane_yield.spent_today(self.store, self.clock()), 0.0)
        # A new UTC day: the guard's next check releases, and E2 may ask again.
        self.clock.advance(86400.0)
        self.assertIsNotNone(elane_yield.hold(self.store, self.settings, self.clock()), "until the guard has checked again")
        self.guard.check()
        self.assertFalse(self.guard.braked or self.guard.research_held, self.guard.last)
        self.assertIsNone(elane_yield.hold(self.store, self.settings, self.clock()))

    def test_a_record_that_cannot_be_trusted_holds_e2(self):
        self.guard.check()
        now = self.clock()
        record = dict(self.store.get(elane_yield.GUARD_KEY))
        self.assertIsNone(elane_yield.sail_day(self.store, self.settings, now))
        # No good reading for `guard.stale_seconds` (the guard itself then allows nothing).
        self.assertIn("no good reading", elane_yield.sail_day(self.store, self.settings, now + 600.0))
        self.assertIsNone(elane_yield.sail_day(self.store, self.settings, now + 599.0))
        # A record with no research cap, and a meter that cannot be read: unknown is never money.
        self.store.put(elane_yield.GUARD_KEY, {**record, "last": {k: v for k, v in record["last"].items()
                                                                   if k != "budget_research_usd_day"}})
        self.assertIn("no research cap", elane_yield.sail_day(self.store, self.settings, now))
        self.store.put(elane_yield.GUARD_KEY, record)
        with mock.patch.object(type(self.store), "spent", side_effect=RuntimeError("the table is gone")):
            self.assertIn("could not be read", elane_yield.sail_day(self.store, self.settings, now))
        # Sail's own meter (the whole account), as the guard last read it: a dollar under the account's line.
        metered = {**record, "last": {**record["last"], "metered_today": 18.0}}
        self.store.put(elane_yield.GUARD_KEY, metered)
        self.assertIn("Sail's own meter", elane_yield.sail_day(self.store, self.settings, now))
        self.store.put(elane_yield.GUARD_KEY, {**record, "last": {**record["last"], "metered_today": 17.99}})
        self.assertIsNone(elane_yield.sail_day(self.store, self.settings, now), "21.00 for the account, 19.00 its line")
        # A budget too small to leave a question's dollar under the guard's line: E2 asks nothing (the floor has room).
        for usd_day, held in ((1.4, True), (4.0, False)):
            settings = lined(usd_day * 0.4 / 24, sail_usd_day=usd_day, pace_share=4.0, usd_day=100.0, guard={"pace_day": False})
            store = fx.new_store(self, self.clock)
            SailGuard(store, settings, lambda: (500.0, None), clock=self.clock, disk_free=lambda: 1e12).check()
            self.assertEqual(elane_yield.sail_day(store, settings, now) is not None, held, usd_day)

    def day(self, settings: dict, *, e2_call: float, others_hour: float, minutes: int = 24 * 60) -> dict:
        """One invented UTC day, a minute at a time, as the loop runs it: the guard checks when it is due; E2's rounds
        start only while it allows new research, and E2 reads `hold` before each question, asks it through
        `elane_yield.ask` on a router that books the call as the real one does, and asks again until it is held; the
        options lanes spend `others_hour` dollars an hour (two fifths on models, the rest on Gym boxes) while the guard
        allows research and their own pace does. HELD AT EVERY MINUTE AND EVERY QUESTION: the day's Sail total is under
        the guard's cap; E2 asks only with a question's dollar of room under the line where the guard holds new
        research (the test's own arithmetic of that line), so no question of E2's carries the day to it; and the
        options researchers are paused only at half their line or more of THEIR OWN spend."""
        self.clock.t = MIDNIGHT
        guard = self.sail_guard(settings)
        caps = guard_mod.budget_caps(settings, self.store.root, self.clock())
        line = float(settings["researcher"]["sail_usd_per_hour"])

        def guards_line() -> float:
            due = caps["research"] * min(1.0, (self.clock() - MIDNIGHT) / 86400.0 + 0.05)
            return min(caps["research"] - caps["gate_reserve"], due)

        def script(call):
            self.store.add_spend("sail_model", e2_call, family="f",
                                 detail={"profile": call["sail_profile"], "key": call["key"][:120], "desk": "f"})
            return {**fx.answer([]), "cost_usd": e2_call}
        router = fx.FakeRouter(script)
        out = {"e2": 0.0, "asked": 0, "reasons": set(), "guard_held": 0, "guard_braked": 0, "paused": 0, "peak": 0.0,
               "e2_hours": {}, "caps": caps, "held_first": 0}
        e2_held = None
        for minute in range(minutes):
            self.clock.t = MIDNIGHT + 60.0 * minute
            if guard.due():
                was = guard.research_held
                guard.check()
                out["guard_held"] += int(guard.research_held)
                out["guard_braked"] += int(guard.braked)
                if guard.research_held and not was:
                    # The guard begins to hold new research: E2 was already stopped, by the Sail day.
                    self.assertEqual(e2_held, "sail_day", f"minute {minute}: the guard held while E2 was still asking")
                    out["held_first"] += 1
            pace = self.researchers(settings)
            out["paused"] += int(pace["paused"])
            if pace["paused"]:
                self.assertGreaterEqual(pace["spent_last_hour_usd"], 0.5 * line - 1e-6,
                                        f"minute {minute}: the researchers paused under half their line of their own")
            if guard.allows("research") and not pace["paused"]:
                self.other_row(others_hour / 60.0 * 0.4)
                self.other_row(others_hour / 60.0 * 0.6, kind="gym_box")
            while guard.allows("research"):
                held = elane_yield.hold(self.store, settings, self.clock())
                if held is not None:
                    e2_held = ("sail_day" if held.startswith(elane_yield.SAIL_DAY) else
                               "usd_day" if held == elane_yield.DAY_SPENT else "pace")
                    out["reasons"].add(e2_held)
                    break
                e2_held = None
                self.assertLess(self.sail_today(), guards_line() - elane_yield.SAIL_ROOM_USD + 1e-9,
                                f"minute {minute}: E2 asked without a dollar of room under the guard's line")
                answer, route, errors = elane_yield.ask(
                    router, self.store, settings, first=None, role=elane_yield.ROLE, system="s", user="u",
                    key=f"swarm:elane:train:f:{minute}:{out['asked']}", max_output=4000, effort="medium", purpose="research",
                    now=self.clock())
                self.assertIsNotNone(answer, errors)
                self.assertLess(self.sail_today(), guards_line(), f"minute {minute}: E2's question reached the guard's line")
                out["asked"] += 1
                out["e2"] += e2_call
                hour = minute // 60
                out["e2_hours"][hour] = out["e2_hours"].get(hour, 0.0) + e2_call
            today = self.sail_today()
            out["peak"] = max(out["peak"], today)
            self.assertLess(today, caps["research"], f"minute {minute}: the day's Sail total passed the guard's cap")
        out["total"] = self.sail_today()
        return out

    def test_a_day_at_four_lines_never_reaches_the_guards_line_and_never_pauses_a_researcher(self):
        # The options lanes small (a dime an hour), E2 at four lines an hour with a day far over the Sail day: what
        # stops E2 is the House's Sail day, before the guard holds anyone.
        out = self.day(self.settings, e2_call=0.07, others_hour=0.10)
        caps = out["caps"]
        line = caps["research"] - caps["gate_reserve"]
        self.assertEqual((caps["research"], line), (20.0, 18.0))
        self.assertEqual(out["guard_held"], 0, "the guard never had to hold new research")
        self.assertEqual(out["guard_braked"], 0)
        self.assertEqual(out["paused"], 0, "nor were the options researchers ever paused")
        self.assertEqual(out["reasons"], {"sail_day"}, "the Sail day is what held E2, every time")
        self.assertLess(out["peak"], line, "the day's Sail total stayed under the guard's research line")
        # No longer starved: far more than the old bound's day ($4.00: half the line), and hours well over its old
        # hourly pace; still inside its own pace every hour.
        self.assertGreater(out["e2"], 12.0, out)
        self.assertGreater(max(out["e2_hours"].values()), 4 * (0.5 * LINE))
        self.assertLessEqual(max(out["e2_hours"].values()), 4 * LINE + 0.07 + 1e-9)
        self.assertAlmostEqual(elane_yield.spent_today(self.store, self.clock()), out["e2"], places=6)

    def test_with_busy_options_lanes_e2_yields_first_and_takes_what_the_day_leaves(self):
        # The options lanes at more than their whole pace with their boxes busy. The guard holds new research when THEY
        # reach its line, late in the day; E2 had stopped a dollar before (`day` holds it at each such check), and the
        # researchers were paused only at half their line or more of their own spend (`day` holds that too).
        small = self.day(self.settings, e2_call=0.07, others_hour=0.10)
        self.setUp()
        out = self.day(self.settings, e2_call=0.07, others_hour=0.95)
        self.assertLess(out["peak"], out["caps"]["research"])
        self.assertEqual(out["guard_braked"], 0)
        self.assertGreater(out["held_first"], 0, "the guard did hold new research, on the options lanes' own dollars")
        self.assertGreater(out["paused"], 0, "and the researchers did pause, at their own half of the line")
        self.assertIn("sail_day", out["reasons"])
        self.assertLess(out["e2"], small["e2"], "E2 took what the day's pace left over, less than on the quiet day")
        # Options lanes that alone outrun the day's even pace leave E2 nothing: it never asks, and the day still ends
        # under the cap.
        self.setUp()
        out = self.day(self.settings, e2_call=0.07, others_hour=1.5)
        self.assertEqual((out["asked"], out["reasons"]), (0, {"sail_day"}))
        self.assertLess(out["peak"], out["caps"]["research"])

    def test_at_the_shipped_quarter_e2s_own_day_binds_long_before_the_sail_day(self):
        quarter = lined(usd_day=8.0)
        out = self.day(quarter, e2_call=0.07, others_hour=0.10)
        self.assertLessEqual(out["e2"], 0.25 * LINE * 24 + 0.07, "a quarter of the line's day: $2.00")
        self.assertGreater(out["e2"], 1.9)
        self.assertIn("usd_day", out["reasons"])
        self.assertIn("pace", out["reasons"])
        self.assertEqual((out["guard_held"], out["paused"]), (0, 0))
        self.assertLess(out["peak"], 6.0)


class OnTheRealLoop(LoopCase):
    """The same stop on the loop production runs (league/swarm/loop.py `Swarm.step`, E1's real store, settings layers and
    router) with the real Sail guard in place of the loop tests' stand-in."""

    def setUp(self):
        super().setUp()
        patch = mock.patch.object(S, "POLICY_PATH", REAL_POLICY_PATH)
        patch.start()
        self.addCleanup(patch.stop)

    def started(self) -> tuple[list[str], Swarm]:
        # The even pace is off here: this loop runs on the wall clock, and the hour of the day is not the test's.
        doc = {"enabled": True, "gym": self.settings["gym"], "researcher": {"idle_seconds": 0},
               "guard": {"pace_day": False},
               "elane": {"mode": "gate", "birth_share": 0.25, "e2": {"usd_day": 100.0, "pace_share": 4.0}}}
        (self.root / "swarm.json").write_text(json.dumps(doc))
        sw = self.swarm()
        sw.guard = self.guard = SailGuard(sw.store, sw.settings, lambda: (500.0, None), clock=sw.clock,
                                          disk_free=lambda: 1e12)
        names: list[str] = []
        sw._round = lambda name, fn: names.append(name)
        sw.step()
        return names, sw

    def again(self, names: list[str], sw: Swarm) -> list[str]:
        names.clear()
        self.guard.checked_at = 0.0  # the guard is due: the loop checks it in this pass
        self.store.put(elane_births.BIRTHS_AT_KEY, 0)
        self.store.put(elane_train.TRAIN_AT_KEY, 0)
        sw.elane_train._looked = (float("-inf"), None)
        sw.step()
        return list(names)

    def test_at_the_guards_cap_neither_round_of_e2s_starts_and_no_researcher_is_paused(self):
        fx.e2_family(self.store, "e2-needs-a-program")
        names, sw = self.started()
        caps = guard_mod.budget_caps(sw.settings, self.store.root, sw.clock())
        self.assertEqual((elane_yield.cfg(sw.settings)["pace_share"], elane_yield.cfg(sw.settings)["usd_day"]), (4.0, 100.0))
        self.assertTrue(self.guard.allows("research"), self.guard.last)
        self.assertIsNone(elane_yield.hold(self.store, sw.settings, sw.clock()))
        after = self.again(names, sw)
        self.assertIn("elane", after)
        self.assertIn("elane_train", after)
        # E2 spends the day down to a dollar under the guard's research line, in calls of its own (sixty lines' worth
        # an hour ago would be its pace; here the rows are older than the hour, so only the Sail day reads them).
        line = caps["research"] - caps["gate_reserve"]
        self.assertGreater(line, elane_yield.SAIL_ROOM_USD)
        now = sw.clock()
        midnight = now - now % 86400.0
        key = "swarm:elane:train:e2-needs-a-program:1:sail:pro_asap"
        with mock.patch.object(self.store, "clock", lambda: max(midnight, now - 3700.0)):
            self.store.add_spend("sail_model", line - elane_yield.SAIL_ROOM_USD, family="e2-needs-a-program",
                                 detail={"profile": "pro_asap", "key": key, "desk": "e2-needs-a-program"})
        held = elane_yield.hold(self.store, sw.settings, sw.clock())
        self.assertTrue(held is not None and held.startswith(elane_yield.SAIL_DAY), held)
        after = self.again(names, sw)
        self.assertFalse(self.guard.research_held or self.guard.braked, "the guard holds nobody: E2 stopped first")
        self.assertNotIn("elane", after, "no equity pass is due while the Sail day holds E2")
        self.assertNotIn("elane_train", after, "nor a Train round whose only work asks a model")
        asked = len(self.sail.bodies)
        self.assertEqual(sw.architect.equity_pass().get("skipped"), "sail_day")
        steps = {s["family"]: s for s in sw.elane_train.run()["steps"]}
        self.assertEqual(steps["e2-needs-a-program"].get("skipped"), held)
        self.assertEqual(len(self.sail.bodies), asked, "no model was asked")
        sw._pace = (float("-inf"), "", 0.0, 0.0)
        pace = sw.pace_status()
        self.assertFalse(pace["paused"], pace)
        self.assertFalse(sw.over_pace())
        self.assertLess(self.store.spent(list(guard_mod.SWARM_SAIL_KINDS), since=midnight), caps["research"])
        # The options lanes then reach the guard's own line: the guard holds new research, E2's rounds with it.
        self.store.add_spend("gym_box", elane_yield.SAIL_ROOM_USD, detail={"key": "a-box"})
        after = self.again(names, sw)
        self.assertTrue(self.guard.research_held, self.guard.last)
        self.assertNotIn("elane", after)
        self.assertNotIn("elane_train", after)
        self.assertIn("holds new research", elane_yield.hold(self.store, sw.settings, sw.clock()))


if __name__ == "__main__":
    unittest.main()
