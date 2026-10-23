"""Release 1019c (the review of r2/alarms, its major 1): EVERY LINE ON ONE DAY, and THE CAP BREACH HOLD.

Budget rule 3 holds each metered line by its own holder (Sail research by the Sail guard, the Claude roles by the router,
the event lane's verdicts by the House's lane) and judges the cap on league/ops/metered.py's day. "Every line together
with the fixed costs is the cap" (league/ops/budget.py) is true only when every holder holds the SAME day as the one
judged. Here each holder spends as much as its own code lets it, every ten minutes for two days around a judged UTC day,
with the budget job writing budget.json after 00:30 UTC and the stall job reading the meters into metered.json, as on
the House; then what each spent inside the judged day is added up. A lane held on New York days (as it was) spends two
lines in one UTC day, and the sum passes the cap: the test that adds the lines catches it. A leak the budget cannot hold
puts the day over its cap, and the hold then stops every line until 00:00 UTC. Invented balances and spend only: no
market price, no account."""

from __future__ import annotations

import copy
import datetime as dt
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from league.events import house as H
from league.events import store as ES
from league.ops import budget as B
from league.ops import metered as MT
from league.swarm import settings as SS
from league.swarm.guard import SailGuard
from league.swarm.models import ModelRouter
from league.swarm.store import SwarmStore
from league.tests.v2_cost import on_v2_cost
from league.tests.swarm_fakes import Clock
from league.tests.test_ops_budget import Meter, inputs

UTC = dt.timezone.utc
NY = H.C.NY
MON, TUE, WED = dt.date(2026, 10, 19), dt.date(2026, 10, 20), dt.date(2026, 10, 21)
STEP = 600.0   # ten minutes: the holders spend, then the next step's stall run reads the meters
#: A profitable trading week: the cap at rule 3's ceiling of $25 (fixed 1.66, the lane 3.00, Sail research 16.27, the
#: Claude roles 4.07; `EveryLineOnOneDay`, on rule 3's figures), and under goal V3's rule 4 a $30 cap ($10 + $20: fixed
#: 1.66, the lane 6.00, Sail research 17.87, the Claude roles 4.47; `EveryLineOnOneDayGoalV3`), every prefund far above
#: its runway, so no meter tapers.
WEEK = dict(week_net=280.0, sail=5000.0, claude=5000.0, lane_peak=2.0)


def utc(day: dt.date, hhmm: str) -> float:
    h, m = (int(x) for x in hhmm.split(":"))
    return dt.datetime.combine(day, dt.time(h, m), tzinfo=UTC).timestamp()


def ny_verdict_day(now: dt.datetime):
    """THE LANE'S OLD DAY (before the review of r2/alarms): the New York day, as house.py held it."""
    day = now.astimezone(NY).date()
    start = dt.datetime.combine(day, dt.time(0, 0), tzinfo=NY)
    end = dt.datetime.combine(day + dt.timedelta(days=1), dt.time(0, 0), tzinfo=NY)
    return day, (ES.iso(start), ES.iso(end))


class FakeHouse:
    def __init__(self, clock):
        self.clock = clock
        self._closing = threading.Event()
        self.alerts = []

    def alert(self, level, text, **payload):
        self.alerts.append((level, text))

    def paused(self):
        return None


class Holders(unittest.TestCase):
    """A House state root with each holder of a metered line on one clock: the Sail guard and the router over the swarm
    store (their settings refreshed from budget.json every step, as every swarm step does), the House's event lane over
    its store; the budget job's budget.json and the stall job's metered.json and cap-hold.json."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.clock = Clock(utc(MON, "12:05"))
        self.store = SwarmStore(self.root, clock=self.clock)
        self.addCleanup(self.store.close)
        self.base = SS.load()                  # the settings with no state root: the budget block comes from overlay
        self.settings = copy.deepcopy(self.base)
        self.sail_total = 0.0                  # every dollar Sail has billed: research, the fixed boxes
        self.sail_seen = 0.0                   # ... as its balance shows it (a step's bills show at the next step)
        self.claude_total = 0.0                # the gateway's settled Claude dollars: verdicts, roles, a leak
        self.guard = SailGuard(self.store, self.settings, lambda: (5000.0 - self.sail_seen, None), clock=self.clock,
                               disk_free=lambda: 1e12)
        self.router = ModelRouter(self.store, None, settings=self.settings, claude_factory=lambda model: None,
                                  claude_meter=Meter(5000))
        self.events = ES.Store(self.root / "events")
        self.addCleanup(self.events.close)
        # The lane's own config line far above the budget's allowance: the budget's lines are what this test adds up.
        self.lane = H.EventLane(FakeHouse(self.clock), self.root / "events", settings={"verdict_usd_day": 25.0})
        self.doc = None
        self.spent: list[tuple[str, float, float]] = []   # (holder, epoch, dollars)
        self.holds: list[tuple[float, dict | None]] = []

    # -- the House's jobs ---------------------------------------------------------------------------------------------
    def budget_job(self, now: float) -> None:
        """budget.json from the rule (the job's daily 00:30 UTC run; the day's figure set once a UTC day)."""
        self.doc = B.compute(inputs(fixed=1.5, **WEEK), now=now, previous=self.doc)
        B._write_json(self.root / B.BUDGET_FILE, self.doc)

    def swarm_step(self, now: float) -> None:
        """Every swarm step's settings (league/swarm/loop.py `step`: `settings.load` updates the dict in place, its budget
        block and knobs from `budget.overlay`)."""
        fresh = copy.deepcopy(self.base)
        B.overlay(fresh, self.root, now=now)
        self.settings.update(fresh)

    def stall_run(self, now: float) -> dict | None:
        """The stall job's meters (league/ops/metered.py `update`): Sail's meter as the guard keeps it, Claude's as the
        gateway reports it, budget.json's cap; and the hold it writes."""
        ledger = MT.update(self.root, now, health={"claude": {"settled_usd": f"{self.claude_total:.6f}"}},
                           budget=self.doc)
        self.holds.append((now, ledger.get("hold")))
        return ledger

    # -- the holders, each as far as its own code lets it -------------------------------------------------------------
    def sail_research(self, now: float, most: float) -> None:
        """The Sail guard's day: book Sail research while the guard lets the gate's work go on (it goes on to the day's
        cap; the gate's reserve and the even pace hold only new research)."""
        left = most
        while left > 1e-9:
            record = self.guard.check()
            if self.guard.braked:
                return
            room = record["budget_research_usd_day"] - record["today_spent"]
            usd = min(left, room)
            if usd <= 1e-9:
                return
            self.store.add_spend("sail_model", usd, detail={"what": "the gate's round (invented)"})
            self.sail_total += usd
            self.spent.append(("sail", now, usd))
            left -= usd

    def claude_roles(self, now: float, most: float) -> None:
        """The router's day: book a role's Claude call of the room the budget leaves (no role named: the line itself)."""
        usd = min(most, self.router.claude_budget_room())
        if usd > 1e-9:
            self.store.add_spend("claude", usd, detail={"role": "strategist"})
            self.claude_total += usd
            self.spent.append(("roles", now, usd))

    def lane_verdicts(self, now: float, most: float) -> None:
        """The House lane's day: verdicts answered while `claude_refusal` lets one be asked (`_spend_today`: the day's
        verdict dollars from the store, and the line)."""
        at = dt.datetime.fromtimestamp(now, UTC)
        self.lane._spend_today(self.events, at)
        left = most
        while left > 1e-9 and self.lane.claude_refusal(None) is None:
            usd = min(left, 0.25, self.lane._line["usd_day"] - self.lane._usd["usd"])
            if usd <= 1e-9:
                return
            self.events.db.execute("INSERT INTO verdicts(event, prompt_sha, model, asked_at, answered_at, status, usd) "
                                   "VALUES(?, 'p', 'claude-haiku-4-5-20251001', ?, ?, 'ok', ?)",
                                   (f"8k:{now:.0f}:{left:.4f}", ES.iso(at), ES.iso(at), usd))
            self.lane.spent(usd)
            self.claude_total += usd
            self.spent.append(("lane", now, usd))
            left -= usd

    def simulate(self, until: float, *, rate: dict | None = None, leak: tuple[float, float] | None = None,
                 down_until: float | None = None) -> None:
        """Every STEP to `until`: Sail's balance shows what was billed before the step; the budget job after 00:30 UTC
        (and at the start), the stall run reading the meters, the swarm step's settings and the Sail guard's check, then
        each holder spending (at most `rate[holder]` a step, else all it may; none before `down_until`, a gateway
        outage), Sail's fixed boxes, and `leak` (epoch, dollars) once: a Claude spend no line holds."""
        rate = rate or {}
        last_day = None
        while self.clock() < until:
            now = self.clock()
            self.sail_seen = self.sail_total
            day = MT.utc_day(now)
            if self.doc is None or (day != last_day and now >= utc(day, "00:30")):
                self.budget_job(now)
                last_day = day
            self.stall_run(now)
            self.swarm_step(now)
            self.guard.check()
            if down_until is None or now >= down_until:
                self.lane_verdicts(now, rate.get("lane", 1e9))
                self.claude_roles(now, rate.get("roles", 1e9))
                self.sail_research(now, rate.get("sail", 1e9))
            self.sail_total += 1.5 * STEP / 86400        # the House box and the data box, by the hour
            if leak is not None and leak[0] <= now < leak[0] + STEP:
                self.claude_total += leak[1]
            self.clock.advance(STEP)

    def within(self, day: dt.date, holder: str | None = None, *, after: float | None = None) -> float:
        lo, hi = MT.day_bounds(day)
        lo = lo if after is None else max(lo, after)
        return sum(usd for who, at, usd in self.spent if lo <= at < hi and (holder is None or who == holder))


@on_v2_cost
class EveryLineOnOneDay(Holders):
    """Every line on one day, on budget rule 3's figures (league/tests/v2_cost.py: the $25 the week reaches)."""

    #: The cap the week's $280 of net gives: rule 3's ceiling.
    CAP = 25.0

    def lines(self) -> dict[str, float]:
        claude = self.doc["meters"]["claude"]
        return {"lane": claude["lane_usd_day"], "roles": claude["research_usd_day"],
                "sail": self.doc["meters"]["sail"]["research_usd_day"]}

    def judged(self, **run) -> None:
        """Tuesday (UTC), judged: each holder spent exactly one line in it, and with the fixed costs they are the cap;
        metered.py measures the day at the cap, never over it, and nothing was held."""
        self.simulate(utc(WED, "12:05"), **run)
        lines, cap = self.lines(), self.doc["cap_usd_day"]
        self.assertEqual((cap, self.doc["cap"]["fixed_usd_day"]), (self.CAP, 1.6644))
        for holder, line in lines.items():
            self.assertAlmostEqual(self.within(TUE, holder), line, places=6, msg=holder)
        fixed = self.doc["cap"]["fixed_usd_day"]
        self.assertLessEqual(fixed + self.within(TUE), cap + 1e-6, "every line and the fixed costs: the cap at most")
        self.assertAlmostEqual(fixed + self.within(TUE), cap, places=3, msg="and at it: nothing of the cap is lost")
        ledger = MT.load(self.root)
        figure = ledger["days"][TUE.isoformat()]
        self.assertTrue(figure["whole"] and figure["final"])
        self.assertEqual(figure["cap"], self.CAP)
        self.assertFalse(figure["over"], figure)
        self.assertLessEqual(figure["spent"], cap + MT.OVER_EPSILON)
        self.assertFalse(MT.cap_check(ledger, utc(WED, "12:05"))["stalled"])
        self.assertFalse(any(hold for _, hold in self.holds), "no hold on a day within its lines")

    def test_each_holders_line_over_the_judged_day_adds_up_to_the_cap_at_most(self):
        """Every holder spends all its line as early as it may, each on its own day."""
        self.judged()

    def test_after_an_evening_outage_too(self):
        """Every holder down (a gateway outage) until 20:05 ET Monday, 00:05 UTC Tuesday: a backlog answered after an
        evening recovery, the review's case. Each holder's Monday is over by then; Tuesday has one line of each."""
        self.judged(down_until=utc(TUE, "00:05"))

    def test_a_lane_held_on_new_york_days_spends_two_lines_in_the_judged_day(self):
        """The lane as it was (`_spend_today` on the New York day), after the same evening outage: Monday's line after
        20:00 ET and Tuesday's from 00:00 ET both fall in Tuesday UTC, so the lines add up past the cap and metered.py
        measures it over: what the review of r2/alarms found, and what this test exists to catch."""
        with mock.patch.object(H, "verdict_day", ny_verdict_day):
            self.simulate(utc(WED, "12:05"), down_until=utc(TUE, "00:05"))
        lines, cap = self.lines(), self.doc["cap_usd_day"]
        self.assertAlmostEqual(self.within(TUE, "lane"), 2 * lines["lane"], places=6)
        self.assertGreater(self.doc["cap"]["fixed_usd_day"] + self.within(TUE), cap + 1.0)
        figure = MT.load(self.root)["days"][TUE.isoformat()]
        self.assertTrue(figure["over"], figure)
        self.assertTrue(any(hold for _, hold in self.holds), "the day over its cap was held")

    def test_the_holders_day_is_the_judged_day_at_both_edges(self):
        """At 23:55 UTC and 00:05 UTC (19:55 and 20:05 ET), and at 03:55 and 04:05 UTC (23:55 and 00:05 ET): each holder
        counts its spend from metered.py's 00:00 UTC, never from New York's midnight."""
        lo, hi = MT.day_bounds(TUE)
        self.assertEqual((lo, hi), (utc(TUE, "00:00"), utc(WED, "00:00")))
        for at in (utc(TUE, "00:05"), utc(TUE, "03:55"), utc(TUE, "04:05"), utc(TUE, "23:55")):
            day, (start, end) = H.verdict_day(dt.datetime.fromtimestamp(at, UTC))
            self.assertEqual((day, ES.parse_iso(start).timestamp(), ES.parse_iso(end).timestamp()), (TUE, lo, hi))
            self.assertEqual(at - at % 86400, lo, "the Sail guard's and the router's own midnight")
            self.assertEqual(MT.utc_day(at), TUE)



class EveryLineOnOneDayGoalV3(Holders):
    """Every line on one day on the figures in force, goal V3's budget rule 4 (release 1019m-cost): the same week's $280
    of net is a $30 cap ($10 plus half the week over its 7 days), the lane's part $6.00; each holder spends exactly its
    line in the judged UTC day and, with the fixed costs, they are the cap, never over it."""

    CAP = 30.0
    lines = EveryLineOnOneDay.lines
    judged = EveryLineOnOneDay.judged

    def test_each_holders_line_over_the_judged_day_adds_up_to_goal_v3s_cap_at_most(self):
        self.judged()
        self.assertEqual((B.BASE_USD_DAY, B.CEILING_USD_DAY, self.lines()["lane"]), (10.0, 50.0, 6.0))


class TheCapBreachHold(Holders):
    def test_a_leak_over_the_cap_holds_every_line_until_00_00_utc(self):
        """Each holder spends a little each step; at 02:05 UTC Tuesday $30 of Claude spend no line holds (a role outside
        the router, say) puts the day over its $25 cap. The stall run after it writes the hold, and from then to 00:00
        UTC the lane asks no verdict, the router admits no role and the Sail guard brakes research; Wednesday has no
        hold and every line spends again."""
        rate = {"lane": 0.05, "roles": 0.05, "sail": 0.2}
        leak_at = utc(TUE, "02:05")
        self.simulate(utc(WED, "06:05"), rate=rate, leak=(leak_at, 30.0))
        held = [(at, hold) for at, hold in self.holds if hold]
        self.assertTrue(held)
        first = held[0][0]
        self.assertEqual(first, leak_at + STEP, "held at the first stall run that read the leak")
        self.assertEqual({hold["day"] for _, hold in held}, {TUE.isoformat()})
        self.assertEqual({hold["since"] for _, hold in held}, {MT._iso(first)}, "the onset kept, run to run")
        for holder in ("lane", "roles", "sail"):
            self.assertGreater(self.within(TUE, holder), 0.0, holder)
            self.assertEqual(self.within(TUE, holder, after=first), 0.0, f"{holder} spent nothing once held")
            self.assertGreater(self.within(WED, holder), 0.0, f"{holder} spends again on Wednesday")
        self.assertFalse([hold for at, hold in self.holds if hold and at >= utc(WED, "00:00")])
        self.assertIsNone(B.cap_hold(self.root, utc(WED, "06:05")))
        self.assertFalse((self.root / B.HOLD_FILE).exists(), "Wednesday under its cap: the file is gone")
        # What each holder read while held: the lane's line 0, the guard's research 0, the router's room 0.
        self.clock.t = utc(TUE, "12:00")
        MT.write_hold(self.root, {"day": TUE.isoformat(), "certainly_over": True, "certain": 31.0, "cap": 25.0},
                      self.clock())
        self.assertEqual(B.lane_allowance(self.root, self.clock())["usd_day"], 0.0)
        self.assertEqual(B.sail_caps(self.settings, self.root, self.clock())["research"], 0.0)
        self.swarm_step(self.clock())
        self.assertEqual(self.router.claude_budget_room(), 0.0)
        self.assertEqual(self.settings["budget"]["source"], f"the cap breach hold ({B.HOLD_FILE})")

    def test_the_stall_job_says_the_hold_and_keeps_its_file_private(self):
        self.simulate(utc(TUE, "03:05"), rate={"lane": 0.05, "roles": 0.05, "sail": 0.2}, leak=(utc(TUE, "02:05"), 30.0))
        ledger = self.stall_run(self.clock())
        check = MT.cap_check(ledger, self.clock(), hold=ledger["hold"])
        self.assertTrue(check["stalled"])
        self.assertTrue(check["numbers"]["held"])
        self.assertIn("The House holds the lane's verdict line, Sail research and the Claude roles at 0 until 00:00 UTC",
                      check["what"])
        self.assertIn("HOLDS the lane's verdict line, Sail research and the Claude roles at 0 until 00:00 UTC",
                      check["doing"])
        self.assertEqual((self.root / B.HOLD_FILE).stat().st_mode & 0o777, 0o600)
        self.assertLessEqual(len(check["doing"]), 700, "the gateway mails at most 700 characters of it")


if __name__ == "__main__":
    unittest.main()
