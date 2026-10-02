"""Funding cliffs said ahead (league/swarm/funding.py; Release A, Sept 30, 2026): runway tiers for Claude's room and the Sail
guard from measured burn, the OpenAI month's calendar rollover (the burst's end is retired: LTCM v3's budget), the Claude
fallbacks the router counts
(league/swarm/models.py), the dedupe that says each tier once, and the House hearing each alert as a warning."""

from __future__ import annotations

import copy
import datetime as dt
import json
import tempfile
import time
import unittest
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from league.swarm.funding import DEFAULTS as FUNDING_DEFAULTS, FundingWatch, month_end, tier_for
from league.swarm.models import ModelError, ModelRouter
from league.swarm.settings import DEFAULTS
from league.swarm.store import SwarmStore
from league.tests.swarm_fakes import Clock, FakeMonth
from league.tests.test_swarm_loop import LoopCase

UTC = dt.timezone.utc
#: 15:00Z Wed Sept 30 2026: nine hours before the OpenAI month ends.
T0 = dt.datetime(2026, 9, 30, 15, 0, tzinfo=UTC).timestamp()
HOUR = 3600.0
TOOLS = [{"name": "notebook", "description": "a note", "input_schema": {"type": "object", "properties": {}}}]


class Meter:
    """The gateway's Claude meter: `remaining()` and the last block's `spent_usd`."""

    def __init__(self, remaining=None, spent=None):
        self.value = remaining
        self.last = {"spent_usd": spent}

    def remaining(self):
        return None if self.value is None else Decimal(str(self.value))


class Case(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = Path(self.dir.name)
        self.clock = Clock(T0)
        self.store = SwarmStore(self.root, clock=self.clock)
        self.addCleanup(self.store.close)
        self.settings = copy.deepcopy(DEFAULTS)
        self.settings["claude"]["usd_cap"] = 10_000.0  # the gateway's room binds, not the swarm's own cap
        self.meter = Meter()
        self.month = FakeMonth(None)
        self.guard = SimpleNamespace(last={})
        self.logs: list[str] = []
        self.router = self.make_router()

    def make_router(self, *, claude=True, month=True):
        router = ModelRouter(self.store, None, settings=self.settings, month=self.month if month else None,
                             frontier_factory=(lambda model: None) if month else None,
                             claude_factory=(lambda model: None) if claude else None, claude_meter=self.meter if claude else None)
        self.sail_calls = []

        def sail(profile, *args, **kwargs):
            self.sail_calls.append(profile)
            return SimpleNamespace(output_text='{"fallback": true}', cost_usd=Decimal("0.02"))

        router.sail = sail
        return router

    def watch(self, **kw):
        return FundingWatch(self.store, self.settings, router=kw.get("router", self.router), guard=self.guard, clock=self.clock,
                            log=self.logs.append)

    def said(self, action="funding_alert", cliff=None):
        return [e["payload"] for e in self.store.events_after(0, limit=10_000) if e["kind"] == "swarm.status"
                and e["payload"].get("action") == action and (cliff is None or e["payload"].get("cliff") == cliff)]

    def burn(self, kind, usd, hours_ago=0.0):
        """Book `usd` of `kind` spend `hours_ago` before the clock."""
        now = self.clock.t
        self.clock.t = now - hours_ago * HOUR
        self.store.add_spend(kind, usd, family=None, detail={"role": "architect"})
        self.clock.t = now

    def cfg(self):
        return self.watch().cfg


class Tiers(Case):
    def test_leads_make_the_tiers_most_severe_first_whatever_their_order(self):
        leads = [48.0, 24.0, 6.0]
        self.assertEqual(tier_for(None, leads), "ok", "no burn: not in sight")
        self.assertEqual(tier_for(60, leads), "ok")
        self.assertEqual(tier_for(48, leads), "notice")
        self.assertEqual(tier_for(24.5, leads), "notice")
        self.assertEqual(tier_for(24, leads), "warning")
        self.assertEqual(tier_for(6, leads), "urgent")
        self.assertEqual(tier_for(0.1, leads), "urgent")
        self.assertEqual(tier_for(0, leads), "out")
        self.assertEqual(tier_for(-3, leads), "out")
        self.assertEqual(tier_for(20, [6, 48, 24]), "warning")
        self.assertEqual(tier_for(20, [48, 24]), "warning", "two leads: notice and warning only")

    def test_the_month_ends_at_the_next_utc_month_boundary(self):
        self.assertEqual(month_end(T0), dt.datetime(2026, 10, 1, tzinfo=UTC).timestamp())
        self.assertEqual(month_end(dt.datetime(2026, 12, 31, 23, 59, tzinfo=UTC).timestamp()),
                         dt.datetime(2027, 1, 1, tzinfo=UTC).timestamp())
        self.assertEqual(month_end(dt.datetime(2026, 10, 1, tzinfo=UTC).timestamp()),
                         dt.datetime(2026, 11, 1, tzinfo=UTC).timestamp(), "the boundary itself starts the new month")

    def test_a_bad_setting_is_its_default_and_enabled_false_turns_it_off(self):
        self.settings["funding"] = {"repeat_hours": -1, "every_seconds": "soon", "claude_out_usd": True,
                                    "lead_hours": {"claude_room": [48, -2], "sail_guard": [100, 50, 10]}}
        cfg = self.cfg()
        self.assertEqual(cfg["repeat_hours"], FUNDING_DEFAULTS["repeat_hours"])
        self.assertEqual(cfg["every_seconds"], FUNDING_DEFAULTS["every_seconds"])
        self.assertEqual(cfg["claude_out_usd"], FUNDING_DEFAULTS["claude_out_usd"])
        self.assertEqual(cfg["lead_hours"]["claude_room"], FUNDING_DEFAULTS["lead_hours"]["claude_room"])
        self.assertEqual(cfg["lead_hours"]["sail_guard"], [100.0, 50.0, 10.0])
        self.settings["funding"] = {"enabled": False}
        self.meter.value = 3
        self.burn("claude", 30, 1)
        self.assertEqual(self.watch().tick(), {})
        self.assertEqual(self.said(), [])


class Dedupe(Case):
    """The dedupe alone (`_decide`), on synthetic assessments."""

    def found(self, tier, hours, *, cliff="claude_room", calendar=False, key=None):
        return {"cliff": cliff, "key": key or cliff, "tier": tier, "hours": hours, "calendar": calendar, "text": f"{tier} {hours}"}

    def decide(self, watch, tier, hours, **kw):
        return watch._decide(self.found(tier, hours, **kw), self.clock.t, watch.cfg)

    def test_a_notice_is_said_once_and_a_standing_warning_is_a_reminder_every_repeat_hours(self):
        w = self.watch()
        self.assertIsNotNone(self.decide(w, "notice", 40))
        self.clock.advance(13 * HOUR)
        self.assertIsNone(self.decide(w, "notice", 30), "a standing notice is never said again")
        said = self.decide(w, "warning", 20)
        self.assertEqual((said["tier"], said["repeat"], said["alert"]), ("warning", False, True))
        self.clock.advance(HOUR)
        self.assertIsNone(self.decide(w, "warning", 19))
        self.clock.advance(11 * HOUR)
        again = self.decide(w, "warning", 8)
        self.assertEqual((again["tier"], again["repeat"]), ("warning", True), "12 hours on, a standing warning is said again")

    def test_a_runway_flapping_across_a_lead_says_each_tier_once_per_repeat_hours(self):
        w = self.watch()
        self.assertIsNotNone(self.decide(w, "urgent", 5.9))
        self.clock.advance(HOUR)
        self.assertIsNone(self.decide(w, "warning", 6.1), "a fall is silent")
        self.clock.advance(HOUR)
        self.assertIsNone(self.decide(w, "urgent", 5.8), "urgent was said two hours ago")
        self.clock.advance(11 * HOUR)
        self.assertIsNotNone(self.decide(w, "urgent", 5.5))

    def test_a_top_up_that_falls_two_tiers_makes_the_next_rise_news_but_a_one_tier_flap_does_not(self):
        w = self.watch()
        self.assertIsNotNone(self.decide(w, "out", 0))
        self.clock.advance(HOUR)
        self.assertIsNone(self.decide(w, "urgent", 3), "one tier down: a flap, silent")
        self.assertIsNone(self.decide(w, "out", 0), "and back: said an hour ago")
        self.assertIsNone(self.decide(w, "notice", 40), "a top-up: silent")
        self.assertIsNotNone(self.decide(w, "warning", 20), "the next rise after a top-up is news")
        self.assertIsNotNone(self.decide(w, "out", 0), "and so is running out again, within the hour")

    def test_no_burn_measured_is_not_a_recovery(self):
        w = self.watch()
        self.assertIsNotNone(self.decide(w, "warning", 20))
        before = self.store.get("funding_alerts")
        self.clock.advance(300)
        self.assertIsNone(self.decide(w, "ok", None))
        self.assertEqual(self.store.get("funding_alerts"), before, "a quiet meter is not a top-up: nothing forgotten or moved")
        self.clock.advance(300)
        self.assertIsNone(self.decide(w, "warning", 20), "burn measured again: the warning said ten minutes ago stands")
        self.clock.advance(12 * HOUR)
        self.assertIsNone(self.decide(w, "ok", None))
        again = self.decide(w, "warning", 8)
        self.assertEqual((again["tier"], again["repeat"]), ("warning", True), "only the twice-a-day reminder")

    def test_a_calendar_out_is_said_once_and_a_restart_says_nothing_again(self):
        w = self.watch()
        self.assertIsNotNone(self.decide(w, "out", 0, cliff="openai_month", calendar=True, key="openai_month:x"))
        self.clock.advance(13 * HOUR)
        self.assertIsNone(self.decide(w, "out", 0, cliff="openai_month", calendar=True, key="openai_month:x"))
        self.assertIsNotNone(self.decide(w, "warning", 10))
        self.assertIsNone(self.decide(self.watch(), "warning", 10), "a new watch on the same store (a restart) is quiet")

    def test_a_recovery_past_the_hysteresis_is_one_ok_without_an_alert_and_a_later_decline_is_news_again(self):
        w = self.watch()
        self.assertIsNotNone(self.decide(w, "warning", 20))
        self.assertIsNone(self.decide(w, "ok", 60), "inside 1.5 x the first lead (72 h): not yet recovered")
        ok = self.decide(w, "ok", 80)
        self.assertEqual((ok["action"], ok["alert"], ok["was"]), ("funding_ok", False, "warning"))
        self.assertIsNone(self.decide(w, "ok", 90), "said once, then forgotten")
        self.assertIsNotNone(self.decide(w, "notice", 40), "a decline after a recovery is news")


class ClaudeRoom(Case):
    def test_the_runway_warns_ahead_from_measured_burn_and_escalates_to_out(self):
        self.burn("claude", 30, 20)  # $1.25 an hour over the last 24 h
        self.meter.value = 41  # $36 above the $5 reserve
        w = self.watch()
        w.tick()
        [notice] = self.said(cliff="claude_room")
        self.assertEqual(notice["tier"], "notice")
        self.assertAlmostEqual(notice["hours"], (36 - 2) / 1.25, places=1)
        self.assertIn("Claude's room runs out in about 27 h", notice["text"])
        self.assertIn("architect", notice["text"])
        self.assertTrue(notice["alert"])
        self.clock.advance(300)
        w.tick()
        self.assertEqual(len(self.said(cliff="claude_room")), 1, "the next check says nothing new")
        self.meter.value = 30
        self.clock.advance(300)
        w.tick()
        self.assertEqual([p["tier"] for p in self.said(cliff="claude_room")], ["notice", "warning"])
        self.meter.value = 12  # $7 above the reserve: (7 - 2) / 1.25 = 4 hours
        self.clock.advance(300)
        w.tick()
        self.assertEqual(self.said(cliff="claude_room")[-1]["tier"], "urgent")
        self.meter.value = 6
        self.clock.advance(300)
        w.tick()
        out = self.said(cliff="claude_room")[-1]
        self.assertEqual(out["tier"], "out")
        self.assertIn("Claude's room is spent", out["text"])
        self.assertEqual(w.last["claude_room"]["tier"], "out", "the heartbeat's status.funding")

    def test_without_claude_configured_or_readable_nothing_is_said(self):
        self.burn("claude", 30, 1)
        self.watch(router=self.make_router(claude=False)).check()
        self.meter.value = None  # the gateway cannot be read: unknown, never a cliff
        w = self.watch()
        w.check()
        self.assertEqual(self.said(), [])
        self.assertEqual(w.last["claude_room"]["state"], "unreadable")

    def test_no_burn_is_no_tier_and_keeps_what_was_said(self):
        """Claude's room low with a burn, then a day with no Claude spend (the roles fell back): the runway is not in sight,
        which neither clears the urgent already said nor says it again as news once the burn comes back."""
        self.burn("claude", 30, 20)
        self.meter.value = 11  # $6 above the reserve: (6 - 2) / 1.25 = 3.2 hours
        w = self.watch()
        w.check()
        self.assertEqual([p["tier"] for p in self.said(cliff="claude_room")], ["urgent"])
        self.clock.advance(25 * HOUR)  # the $30 leaves the window; nothing booked, the meter still
        w.check()
        self.assertEqual(w.last["claude_room"]["state"], "no burn")
        self.assertNotIn("tier", w.last["claude_room"], "the heartbeat never shows a quiet meter as ok")
        self.assertEqual(self.store.get("funding_alerts")["claude_room"]["tier"], "urgent")
        self.burn("claude", 6, 1)  # $1 an hour over the 6-hour window: 4 hours left, urgent again
        self.clock.advance(300)
        w.check()
        self.assertEqual(len(self.said(cliff="claude_room")), 2, "the burn is back: the standing urgent's 12 h reminder")
        self.assertTrue(self.said(cliff="claude_room")[-1]["repeat"])
        self.clock.advance(300)
        w.check()
        self.assertEqual(len(self.said(cliff="claude_room")), 2, "and nothing more")

    def test_the_meters_own_fall_counts_when_the_swarm_booked_nothing(self):
        """The gateway's `spent_usd` rises with every consumer (the House too): sampled every ten minutes, its rate over
        the last hours is the burn even when the swarm's own rows are empty."""
        self.meter.value, self.meter.last = 30, {"spent_usd": "100.00"}
        w = self.watch()
        w.check()
        self.assertEqual(self.said(), [], "no burn yet: not in sight")
        for step in range(1, 7):
            self.clock.advance(HOUR / 2)
            self.meter.last = {"spent_usd": f"{100 + step:.2f}"}  # $2 an hour
            w.check()
        [warning] = self.said(cliff="claude_room")
        self.assertEqual(warning["tier"], "warning")
        self.assertAlmostEqual(warning["burn_usd_per_hour"], 2.0, places=2)
        self.assertAlmostEqual(warning["hours"], (25 - 2) / 2.0, places=1)


class SailGuard(Case):
    def reading(self, balance, *, line=32.0, burn_day=48.0, at=None):
        self.guard.last = {"balance": balance, "line": line, "burn_day": burn_day, "house_day": 1.0,
                           "at": self.clock.t if at is None else at}

    def test_the_runway_to_the_guards_line_from_sails_own_burn(self):
        self.reading(171.86, burn_day=48.69)
        w = self.watch()
        w.check()
        [notice] = self.said(cliff="sail_guard")
        self.assertEqual(notice["tier"], "notice")
        self.assertAlmostEqual(notice["hours"], (171.86 - 32) / (48.69 / 24), places=1)
        self.assertIn("the Sail guard brakes the swarm in about 69 h", notice["text"])
        self.reading(40)
        self.clock.advance(300)
        w.check()
        self.assertEqual(self.said(cliff="sail_guard")[-1]["tier"], "urgent")
        self.reading(31)
        self.clock.advance(300)
        w.check()
        out = self.said(cliff="sail_guard")[-1]
        self.assertEqual(out["tier"], "out")
        self.assertIn("the House keeps running", out["text"])

    def test_a_braked_guard_under_its_release_line_stays_out_after_a_small_top_up(self):
        self.reading(31)
        self.guard.last["braked"] = True
        w = self.watch()
        w.check()
        self.assertEqual([p["tier"] for p in self.said(cliff="sail_guard")], ["out"])
        self.reading(34)  # over the $32 line, under the $37 release line (the default $5 margin)
        self.guard.last["braked"] = True
        self.clock.advance(300)
        w.check()
        self.assertEqual(len(self.said(cliff="sail_guard")), 1)
        self.assertEqual((w.last["sail_guard"]["tier"], w.last["sail_guard"]["state"], w.last["sail_guard"]["release_usd"]),
                         ("out", "braked", 37.0), "the heartbeat says the brake still holds")
        self.clock.advance(12 * HOUR)
        self.reading(34)
        self.guard.last["braked"] = True
        w.check()
        reminder = self.said(cliff="sail_guard")[-1]
        self.assertEqual((reminder["tier"], reminder["repeat"]), ("out", True))
        self.assertIn("still braked", reminder["text"])
        self.reading(38)  # past the release line: the guard releases at its next check; the runway is to the line again
        self.guard.last["braked"] = False
        self.clock.advance(300)
        w.check()
        self.assertEqual((w.last["sail_guard"]["state"], w.last["sail_guard"]["tier"]), ("measured", "urgent"))

    def test_no_sail_burn_is_no_tier(self):
        self.reading(40, burn_day=0.0)
        w = self.watch()
        w.check()
        self.assertEqual(self.said(cliff="sail_guard"), [])
        self.assertEqual((w.last["sail_guard"]["state"], w.last["sail_guard"]["hours"]), ("no burn", None))
        self.assertNotIn("tier", w.last["sail_guard"])

    def test_a_stale_or_missing_reading_says_nothing(self):
        self.reading(40, at=T0 - 2 * HOUR)
        self.watch().check()
        self.guard.last = {}
        self.watch().check()
        self.assertEqual(self.said(cliff="sail_guard"), [])


class OpenAIMonth(Case):
    def test_the_funded_month_warns_before_its_end_and_says_the_rollover_once(self):
        self.month.value = 20.16
        w = self.watch()
        w.check()
        [warning] = self.said(cliff="openai_month")
        self.assertEqual((warning["tier"], warning["ends_at"]), ("warning", "2026-10-01T00:00Z"))
        self.assertIn("architect.openai_model=gpt-6-astra", warning["text"], "the defaults name OpenAI models")
        self.assertIn("gate.audit_openai_model=gpt-6-astra", warning["text"], "the audit's model when the key is absent")
        self.clock.t = dt.datetime(2026, 9, 30, 18, 30, tzinfo=UTC).timestamp()
        w.check()
        self.assertEqual(self.said(cliff="openai_month")[-1]["tier"], "urgent")
        self.clock.t = dt.datetime(2026, 10, 1, 0, 5, tzinfo=UTC).timestamp()
        w.check()  # a cached reading from before the boundary still shows room: wait
        self.assertEqual(len(self.said(cliff="openai_month")), 2)
        self.month.value = 0
        self.clock.advance(600)
        w.check()
        out = self.said(cliff="openai_month")[-1]
        self.assertEqual((out["tier"], out["ended_at"]), ("out", "2026-10-01T00:00Z"))
        self.assertIn("its cap is now $0", out["text"])
        self.clock.advance(13 * HOUR)
        w.check()
        self.assertEqual(len(self.said(cliff="openai_month")), 3, "the rollover is said once; an empty month says nothing")

    def test_no_role_naming_openai_says_so_and_a_funded_next_month_is_no_cliff(self):
        for section, key in (("architect", "openai_model"), ("gate", "review_openai_model"), ("gate", "audit_openai_model")):
            self.settings[section][key] = None
        self.month.value = 10.89
        w = self.watch()
        w.check()
        self.assertIn("no swarm role names an OpenAI model", self.said(cliff="openai_month")[0]["text"])
        self.clock.t = dt.datetime(2026, 10, 1, 1, 0, tzinfo=UTC).timestamp()
        self.month.value = 25  # the owner funded October
        w.check()
        self.assertEqual(len(self.said(cliff="openai_month")), 1, "no out, and November is weeks away")

    def test_an_empty_month_says_nothing(self):
        self.month.value = 0
        self.watch().check()
        self.assertEqual(self.said(cliff="openai_month"), [])


class BudgetIsNotACliff(Case):
    """LTCM v3: the burst's end is retired (the Sail guard's daily cap is the budget's, league/ops/budget.py), and the
    budget's daily Claude line running out is the rule working, not a funding cliff."""

    def test_the_bursts_end_is_never_assessed(self):
        self.settings["guard"]["burst_until"] = "2026-10-05T00:00:00Z"  # a swarm.json that still names it changes nothing
        self.burn("sail_model", 60, 1)
        w = self.watch()
        w.check()
        self.assertNotIn("burst_end", w.last)
        self.assertNotIn("burst_end", w.cfg["lead_hours"])
        self.assertEqual(self.said(cliff="burst_end"), [])

    def test_a_spent_budget_line_is_not_claudes_room_running_out(self):
        self.settings["budget"] = {"source": "budget.json", "sail_usd_day": 3.0, "claude_usd_day": 2.0}
        self.burn("claude", 30, 2)  # today (UTC)
        self.meter.value = 1000  # funded: hundreds of hours at the measured burn
        self.assertEqual(self.router.claude_room(), 0.0, "the budget's $2 today is spent")
        self.assertGreater(self.router.claude_funded_room(), 900)
        w = self.watch()
        w.check()
        self.assertEqual(self.said(cliff="claude_room"), [], "no alert: the funded room is far from its cliff")
        self.assertEqual(w.last["claude_room"]["tier"], "ok")


class Fallbacks(Case):
    def ask(self, **kw):
        args = dict(role="architect", system="THE RULES", user="the packet", family=None, key="call-1", openai_model=None,
                    sail_profile="k3_balanced", max_output=12000, effort="high", need_usd=0.01, claude=True)
        args.update(kw)
        return self.router.ask(**args)

    def test_a_role_that_falls_from_claude_to_sail_for_want_of_room_is_an_alert_counted_not_repeated(self):
        self.meter.value = 3  # under the $5 reserve: no room
        self.assertEqual(self.ask()["route"], "sail")
        self.assertEqual(self.ask(key="call-2")["route"], "sail")
        w = self.watch()
        w.tick()
        [said] = self.said("claude_fallback")
        self.assertEqual((said["role"], said["kind"], said["to"], said["calls"], said["alert"]),
                         ("architect", "no_room", "sail", 2, True))
        self.assertIn("2 architect call(s) fell back from Claude to Sail", said["text"])
        self.assertIn("no room", said["reason"])
        self.ask(key="call-3")
        self.clock.advance(60)
        w.tick()
        self.assertEqual(len(self.said("claude_fallback")), 1, "within six hours: counted, not said")
        self.clock.advance(6 * HOUR)
        w.tick()
        again = self.said("claude_fallback")[-1]
        self.assertEqual(again["calls"], 1, "the count since the last time it was said")
        self.clock.advance(6 * HOUR)
        w.tick()
        self.assertEqual(len(self.said("claude_fallback")), 2, "nothing new: nothing said")

    def test_a_roles_own_daily_line_is_an_event_without_an_alert_and_no_sail_profile_is_no_route(self):
        self.meter.value = 500
        self.settings["claude"]["role_usd_day"] = {"architect": 0}
        self.assertEqual(self.ask()["route"], "sail")
        with self.assertRaises(ModelError):  # a call bigger than the room, for a role with no Sail profile
            self.router.ask(role="strategist", system="s", user="u", family=None, key="k", openai_model=None, sail_profile=None,
                            claude=True, need_usd=10_000.0)
        self.watch().tick()
        said = {(p["role"], p["kind"], p["to"]): p for p in self.said("claude_fallback")}
        self.assertFalse(said[("architect", "line", "sail")]["alert"])
        self.assertTrue(said[("strategist", "no_room", "none")]["alert"])

    def test_a_researchers_claude_turn_that_is_refused_counts_as_its_sail_turn_and_off_does_not(self):
        self.meter.value = 20  # $15 above the reserve, less than the $25 the researcher leaves to the other roles
        with self.assertRaises(ModelError) as refused:
            self.router.claude_turn(role="researcher", family="fam-1", key="turn-1", system="s", tools=TOOLS,
                                    messages=[{"role": "user", "content": "go"}], keep_usd=25.0)
        self.assertEqual(refused.exception.kind, "no_room")
        self.assertEqual(list(self.router.drain_fallbacks()), [("researcher", "no_room", "sail")])
        with self.assertRaises(ModelError) as off:
            self.make_router(claude=False).claude_turn(role="researcher", family="fam-1", key="turn-2", system="s", tools=TOOLS,
                                                       messages=[{"role": "user", "content": "go"}])
        self.assertEqual(off.exception.kind, "off")
        self.assertEqual(self.router.drain_fallbacks(), {})

    def test_an_answered_claude_call_is_no_fallback(self):
        self.meter.value = 500

        class Answer:
            text, cost_usd, cost_verified, stop_reason, usage, data = '{"ok": 1}', Decimal("0.10"), True, "end_turn", {}, None

        class Client:
            def ask(self, *args, **kwargs):
                return Answer()

        self.router.claude_factory = lambda model: Client()
        self.assertEqual(self.ask()["route"], "claude")
        self.assertEqual(self.router.drain_fallbacks(), {})


class HouseHearsIt(Case):
    def test_a_funding_alert_reaches_the_house_as_a_warning_never_an_error(self):
        from league.ledger import Ledger
        from league.swarm.hook import SwarmStep

        self.guard.last = {"balance": 31.0, "line": 32.0, "burn_day": 48.0, "at": self.clock.t}
        self.watch().check()
        alerts = []

        class House:
            ledger = Ledger(self.root / "ledger.sqlite")

            def alert(self, level, text, **payload):
                alerts.append((level, text))

        house = House()
        self.addCleanup(house.ledger.close)
        step = SwarmStep(self.root, config={"swarm": {"enabled": True}}, clock=self.clock)
        step.mirror(house.ledger)
        step.mirror_notices(house)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0][0], "warning")
        self.assertTrue(alerts[0][1].startswith("swarm: funding: the Sail guard's line is reached"))
        rows = house.ledger.read(kinds="swarm.status", limit=10, newest=True)
        self.assertEqual(rows[0].payload["cliff"], "sail_guard")
        self.assertFalse(rows[0].public, "a funding row is private: never on the site")


class InTheLoop(LoopCase):
    def test_a_step_runs_the_watch_after_the_guard_and_the_heartbeat_carries_it(self):
        sw = self.swarm()
        sw.seed()
        self.guard.last = {"balance": 31.0, "line": 32.0, "burn_day": 48.0, "at": time.time()}
        sw.step()
        for thread in list(sw.rounds.values()):
            thread.join(30)
        beat = json.loads((self.root / "swarm.heartbeat").read_text())
        self.assertEqual(beat["status"]["funding"]["sail_guard"]["tier"], "out")
        alerts = [e["payload"] for e in self.store.events_after(0, limit=10_000) if e["kind"] == "swarm.status"
                  and e["payload"].get("action") == "funding_alert"]
        self.assertEqual([a["cliff"] for a in alerts], ["sail_guard"])
        sw.step()
        self.assertEqual(len([e for e in self.store.events_after(0, limit=10_000) if e["kind"] == "swarm.status"
                              and e["payload"].get("action") == "funding_alert"]), 1, "the next step says nothing again")


if __name__ == "__main__":
    unittest.main()
