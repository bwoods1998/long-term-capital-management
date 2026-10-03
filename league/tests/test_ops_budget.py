"""THE BUDGET RULE (league/ops/budget.py, LTCM v3, D4): the rule's arithmetic both ways (a cut and a raise), the card line,
the no-forward-edge stop, the fail-closed reads, the tighten-only overlay in `settings.load`, Claude's room under the
budget's daily line, the funding notice (once per meter a week) and the drill. Fakes only: no network, no Sail."""

from __future__ import annotations

import copy
import datetime as dt
import json
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from league.ops import budget as B
from league.swarm import settings as S
from league.swarm.models import ModelRouter
from league.swarm.store import SwarmStore
from league.tests.swarm_fakes import Clock, FakeFrontier, FakeMonth

UTC = dt.timezone.utc
DAY = 86400.0
#: Tuesday Oct 20, 2026, 21:30Z: after that day's close.
NOW = dt.datetime(2026, 10, 20, 21, 30, tzinfo=UTC).timestamp()


def at(*args) -> float:
    return dt.datetime(*args, tzinfo=UTC).timestamp()


def inputs(*, sail=600.0, fixed=1.5, claude=100.0, p30=0.0, stop=False, need_sail=0.0, need_claude=0.0):
    return {"p30_usd": p30, "p30_source": "test", "edge": {"stop": stop, "why": "test edge"},
            "meters": {"sail": {"balance_usd": sail, "fixed_usd_day": fixed, "need_usd": need_sail},
                       "claude": {"balance_usd": claude, "fixed_usd_day": 0.0, "need_usd": need_claude}}}


class Rule(unittest.TestCase):
    def test_the_floor_with_a_full_prefund_and_no_profit(self):
        doc = B.compute(inputs(), now=NOW)
        sail, claude = doc["meters"]["sail"], doc["meters"]["claude"]
        self.assertEqual(sail["research_usd_day"], 3.0, "the floor's Sail share: 5 x 0.6")
        self.assertEqual(sail["limited_by"], "floor")
        self.assertEqual(sail["runway_days"], round(590 / 4.5, 1))
        self.assertEqual(sail["card_date"], (dt.date(2026, 10, 20) + dt.timedelta(days=590 / 4.5 - 60)).isoformat())
        self.assertEqual(sail["restore_usd"], 0.0, "already more than R days")
        # Claude: $95 above the reserve funds only 95/90 a day for R days, under the floor's $2.
        self.assertAlmostEqual(claude["research_usd_day"], 95 / 90, places=4)
        self.assertEqual(claude["limited_by"], "sustainable")
        self.assertEqual(claude["runway_days"], 90.0, "at the rate the rule holds it to")
        self.assertEqual(claude["restore_usd"], 85.0, "5 + 90 x the full floor of 2 - 100")
        # The card line is at the rate it WANTS (its full floor share): $95 lasts 47.5 days at $2 a day.
        self.assertEqual((claude["demand_usd_day"], claude["card_runway_days"]), (2.0, 47.5))
        self.assertEqual(claude["card_date"], "2026-10-20", "already under the card line")
        self.assertEqual(sail["card_runway_days"], round(590 / 4.5, 1))
        self.assertEqual(B.short(doc), ["claude"])
        self.assertEqual(doc["earned_usd_day"], 0.0)
        self.assertEqual(doc["state"], "research at floor")
        self.assertEqual(doc["direction"], "same")

    def test_a_raise_from_realized_profit_split_by_need(self):
        before = B.compute(inputs(), now=NOW - DAY)
        doc = B.compute(inputs(p30=120.0, need_sail=30.0, need_claude=10.0), now=NOW, previous=before)
        self.assertEqual(doc["earned_usd_day"], 2.0, "0.5 x 120 / 30")
        self.assertEqual(doc["meters"]["sail"]["research_usd_day"], 4.5, "3 + 0.75 x 2")
        self.assertEqual(doc["meters"]["sail"]["limited_by"], "floor + earned")
        self.assertAlmostEqual(doc["meters"]["claude"]["research_usd_day"], 95 / 90 + 0.5, places=4)
        self.assertEqual((doc["direction"], doc["meters"]["sail"]["direction"]), ("raise", "raise"))
        self.assertEqual(doc["state"], "research at floor + profit share")

    def test_a_cut_when_profit_falls_away(self):
        before = B.compute(inputs(p30=120.0), now=NOW - DAY)
        doc = B.compute(inputs(p30=-40.0), now=NOW, previous=before)
        self.assertEqual(doc["earned_usd_day"], 0.0, "a loss earns nothing (and never takes from the floor)")
        self.assertEqual(doc["meters"]["sail"]["research_usd_day"], 3.0)
        self.assertEqual((doc["direction"], doc["meters"]["sail"]["direction"]), ("cut", "cut"))

    def test_a_cut_when_the_prefund_drains(self):
        before = B.compute(inputs(sail=600.0), now=NOW - DAY)
        doc = B.compute(inputs(sail=300.0), now=NOW, previous=before)
        self.assertAlmostEqual(doc["meters"]["sail"]["research_usd_day"], (290 - 135) / 90, places=4)
        self.assertEqual(doc["meters"]["sail"]["direction"], "cut")

    def test_the_card_line_binds_earned_research(self):
        doc = B.compute(inputs(p30=3000.0, claude=2000.0), now=NOW)
        sail = doc["meters"]["sail"]
        self.assertEqual(sail["limited_by"], "W")
        self.assertAlmostEqual(sail["research_usd_day"], (590 - 60 * 1.5) / 60, places=4)
        self.assertEqual(sail["runway_days"], 60.0, "the throttled rate holds exactly W days")
        # ...so the card line reads the rate research wants: 1.5 + 3 + 0.6 x 50 a day.
        self.assertEqual(sail["demand_usd_day"], 34.5)
        self.assertEqual(sail["card_runway_days"], round(590 / 34.5, 1))
        self.assertEqual(sail["restore_usd"], round(10 + 90 * 34.5 - 600, 2))
        self.assertEqual(B.short(doc), ["sail"], "profit wants more than Sail's prefund holds for W days")
        self.assertEqual(doc["meters"]["claude"]["card_runway_days"], round(1995 / 22, 1), "Claude's 2000 holds 2 + 20")

    def test_a_throttled_meter_still_asks_for_a_card(self):
        """The review's case: research throttled to the W cap or to `sustainable` keeps the throttled runway at W or R
        days, so the card line must be judged at the rate the meter wants."""
        # Claude, fixed 0, $95 funded, no profit: `sustainable` holds research at 1 a day (runway exactly R).
        doc = B.compute(inputs(claude=95.0), now=NOW)
        claude = doc["meters"]["claude"]
        self.assertEqual((claude["limited_by"], claude["research_usd_day"], claude["runway_days"]), ("sustainable", 1.0, 90.0))
        self.assertEqual(claude["card_runway_days"], 45.0, "95 - 5 over the floor's 2 a day")
        self.assertIn("claude", B.short(doc))
        facts = B.notice_facts(doc, "claude", NOW)
        self.assertEqual((facts["balance_usd"], facts["usd_day"], facts["research_usd_day"], facts["runway_days"]),
                         ("95.00", "2.00", "2.00", "45.0"))
        self.assertEqual((facts["current_usd_day"], facts["current_runway_days"], facts["restore_usd"]),
                         ("1.00", "90.0", "90.00"))
        # With profit to spend, the W cap binds instead (runway exactly W), and the card line reads 2 + 0.4 x 10.
        doc = B.compute(inputs(claude=95.0, p30=600.0), now=NOW)
        claude = doc["meters"]["claude"]
        self.assertEqual((claude["limited_by"], claude["research_usd_day"], claude["runway_days"]), ("W", 1.5, 60.0))
        self.assertEqual((claude["demand_usd_day"], claude["card_runway_days"]), (6.0, 15.0))
        self.assertIn("claude", B.short(doc))
        # Sail between the lines: research is already 0, its own runway at fixed alone 80 days, its card line 26.7.
        doc = B.compute(inputs(sail=130.0, fixed=1.5), now=NOW)
        sail = doc["meters"]["sail"]
        self.assertEqual((sail["research_usd_day"], sail["runway_days"], sail["card_runway_days"]), (0.0, 80.0, 26.7))
        self.assertIn("sail", B.short(doc))
        # A day later the decayed balance is still told: nothing the rule throttles hides it.
        for balance in (95.0, 80.0, 60.0, 40.0, 20.0, 6.0):
            self.assertIn("claude", B.short(B.compute(inputs(claude=balance), now=NOW)), balance)
        self.assertNotIn("claude", B.short(B.compute(inputs(claude=126.0), now=NOW)), "121 / 2 > 60 days")

    def test_research_never_takes_a_meter_under_w_days(self):
        for balance in (0.0, 5.0, 20.0, 90.0, 150.0, 400.0, 2000.0):
            for fixed in (0.0, 0.5, 1.5, 4.0):
                for p30 in (None, -10.0, 0.0, 50.0, 900.0, 50_000.0):
                    doc = B.compute(inputs(sail=balance, fixed=fixed, claude=balance, p30=p30), now=NOW)
                    for m in B.METERS:
                        row = doc["meters"][m]
                        self.assertGreaterEqual(row["research_usd_day"], 0.0)
                        if row["research_usd_day"] > 0:
                            self.assertGreaterEqual(row["runway_days"], B.W_DAYS - 0.05, (m, balance, fixed, p30))
                        self.assertLessEqual(row["research_usd_day"], B.floor_usd_day(m) + doc["earned_usd_day"] + 1e-6)

    def test_the_no_forward_edge_stop_earns_nothing(self):
        doc = B.compute(inputs(p30=600.0, stop=True), now=NOW)
        self.assertEqual(doc["earned_usd_day"], 0.0)
        self.assertEqual(doc["state"], "no forward edge; research at floor")
        self.assertTrue(doc["no_forward_edge"])
        self.assertEqual(doc["meters"]["sail"]["research_usd_day"], 3.0, "the floor stays")

    def test_unknown_is_never_money(self):
        doc = B.compute(inputs(p30=None), now=NOW)
        self.assertEqual(doc["earned_usd_day"], 0.0)
        self.assertIn("p30 unreadable: nothing earned", doc["why"])
        doc = B.compute(inputs(sail=None, p30=900.0), now=NOW)
        self.assertEqual(doc["meters"]["sail"]["research_usd_day"], 0.0)
        self.assertEqual(doc["meters"]["sail"]["limited_by"], "unreadable")
        no_edge = B.compute({**inputs(p30=900.0), "edge": None}, now=NOW)
        self.assertEqual(no_edge["earned_usd_day"], 0.0, "no edge state: the stop stands")

    def test_an_empty_meter_is_short_with_the_amount_that_restores_r_days(self):
        doc = B.compute(inputs(sail=60.0, fixed=1.5), now=NOW)
        sail = doc["meters"]["sail"]
        self.assertEqual(sail["research_usd_day"], 0.0)
        self.assertEqual(sail["runway_days"], round(50 / 1.5, 1))
        self.assertEqual(sail["card_runway_days"], round(50 / 4.5, 1))
        self.assertEqual(sail["card_date"], "2026-10-20", "already under the card line")
        self.assertEqual(sail["restore_usd"], 355.0, "10 + 90 x (1.5 + 3) - 60")
        self.assertEqual(B.short(doc), ["sail", "claude"], "Claude's 95 over its reserve is 47.5 days at the 2 it wants")
        empty = B.compute(inputs(claude=3.0), now=NOW)
        claude = empty["meters"]["claude"]
        self.assertEqual((claude["runway_days"], claude["card_runway_days"]), (0.0, 0.0), "under the reserve at either rate")
        self.assertIn("claude", B.short(empty))

    def test_an_unreadable_balance_reads_its_card_line_elsewhere_but_never_research(self):
        given = inputs(sail=None)
        given["meters"]["sail"].update(notice_balance_usd=60.0, notice_balance_source="the gateway's Sail reading")
        sail = B.compute(given, now=NOW)["meters"]["sail"]
        self.assertEqual((sail["research_usd_day"], sail["limited_by"]), (0.0, "unreadable"))
        self.assertEqual((sail["card_runway_days"], sail["restore_usd"]), (round(50 / 4.5, 1), 355.0))
        doc = B.compute(given, now=NOW)
        self.assertIn("sail", B.short(doc))
        self.assertEqual(B.notice_facts(doc, "sail", NOW)["balance_usd"], "60.00")
        self.assertNotIn("sail", B.short(B.compute(inputs(sail=None), now=NOW)), "no reading at all: nothing to say")


class Knobs(unittest.TestCase):
    def test_the_floor_buys_one_box_and_a_slow_architect(self):
        k = B.knobs(3.0, 2.0)
        self.assertEqual(k["researcher.sail_usd_per_hour"], round(3.0 * 0.4 / 24, 6))
        self.assertEqual(k["gym.max_boxes"], 1)
        self.assertEqual(k["claude.role_usd_day"], 2.0)
        self.assertEqual(k["population.ceiling"], 8)
        self.assertEqual(k["architect.every_seconds"], 14400)

    def test_more_dollars_buy_more_and_none_buy_almost_nothing(self):
        k = B.knobs(32.0, 8.0)
        self.assertEqual(k["gym.max_boxes"], 12, "32 x 0.6 / (0.2 x 8)")
        self.assertEqual(k["population.ceiling"], 40)
        self.assertEqual(k["architect.every_seconds"], 1800)
        zero = B.knobs(0, 0)
        self.assertEqual((zero["researcher.sail_usd_per_hour"], zero["claude.role_usd_day"]), (0.0, 0.0))
        self.assertEqual(zero["architect.every_seconds"], 86400)
        self.assertEqual(B.knobs("junk", None), zero)


class Overlay(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = Path(self.dir.name)

    def write(self, sail=10.0, claude=6.0, *, at_=NOW - 3600, fixed=1.2, **extra):
        doc = {"schema": 1, "at": at_, "state": "research at floor + profit share",
               "meters": {"sail": {"research_usd_day": sail, "fixed_usd_day": fixed}, "claude": {"research_usd_day": claude}},
               **extra}
        (self.root / "budget.json").write_text(json.dumps(doc))

    def overlay(self, settings=None):
        return B.overlay(copy.deepcopy(settings or S.DEFAULTS), self.root, now=NOW)

    def test_tighten_only(self):
        self.write(sail=10.0, claude=6.0)
        out = self.overlay()
        k = B.knobs(10.0, 6.0)
        self.assertEqual(out["gym"]["max_boxes"], min(8, k["gym.max_boxes"]))
        self.assertEqual(out["population"]["ceiling"],
                         max(k["population.ceiling"], S.DEFAULTS["population"]["floor"] + B.BIRTH_MARGIN))
        self.assertEqual(out["population"]["start"], out["population"]["ceiling"], "the start is held under the ceiling")
        self.assertEqual(out["architect"]["every_seconds"], 14400, "max(): the configured 4 h is slower than the budget's")
        self.assertEqual(out["architect"]["refill_seconds"], k["architect.every_seconds"],
                         "a refill never runs faster than the budget's cadence (4500 s: the configured hourly is lifted)")
        self.assertEqual(out["researcher"]["usd_per_hour"], k["researcher.sail_usd_per_hour"],
                         "sail_usd_per_hour unset: the combined pace that then governs Sail is capped")
        self.assertIsNone(out["researcher"]["sail_usd_per_hour"])
        self.assertEqual(out["claude"]["role_usd_day"]["researcher"], 6.0, "100 capped")
        self.assertEqual(out["claude"]["role_usd_day"]["strategist"], 4.0, "4 is already under 6")
        for role in S.DEFAULTS["claude"]["roles"]:
            self.assertLessEqual(out["claude"]["role_usd_day"][role], 6.0, f"{role} gets a line")
        self.assertEqual((out["budget"]["source"], out["budget"]["sail_usd_day"], out["budget"]["claude_usd_day"]),
                         ("budget.json", 10.0, 6.0))

    def test_a_raise_never_loosens_a_configured_value(self):
        self.write(sail=500.0, claude=400.0)
        settings = copy.deepcopy(S.DEFAULTS)
        settings["researcher"]["sail_usd_per_hour"] = 0.5
        settings["population"]["ceiling"] = 12
        settings["architect"]["every_seconds"] = 900
        out = self.overlay(settings)
        self.assertEqual(out["researcher"]["sail_usd_per_hour"], 0.5)
        self.assertEqual(out["researcher"]["usd_per_hour"], 4.0, "the combined pace is not the one in force")
        self.assertEqual(out["gym"]["max_boxes"], 8)
        self.assertEqual(out["population"]["ceiling"], 12)
        self.assertEqual(out["architect"]["every_seconds"], 1800, "the budget never makes the architect faster than 30 min")
        self.assertEqual(out["claude"]["role_usd_day"]["researcher"], 100.0)

    def test_a_start_over_the_ceiling_cannot_bypass_it(self):
        """The review's case: the floor's ceiling under a configured start of 16 kept the architect refilling hourly
        and reseeding toward 16. (The ceiling is the production floor of 8 + BIRTH_MARGIN: it never falls to the floor.)"""
        settings = copy.deepcopy(S.DEFAULTS)
        settings["population"].update(start=16, ceiling=96, floor=8, reseed_max=4)
        out = self.overlay(settings)  # no budget.json: the floor
        self.assertEqual((out["population"]["ceiling"], out["population"]["start"]), (8 + B.BIRTH_MARGIN, 8 + B.BIRTH_MARGIN))
        self.assertEqual(out["architect"]["refill_seconds"], 14400)
        settings["population"].update(start=5)
        self.assertEqual(self.overlay(settings)["population"]["start"], 5, "a start under the ceiling stays")
        settings["architect"]["refill_seconds"] = 90000
        self.assertEqual(self.overlay(settings)["architect"]["refill_seconds"], 90000, "a slower refill stays")

    def test_a_configured_value_that_is_not_a_number_is_left_to_its_reader(self):
        self.write()
        settings = copy.deepcopy(S.DEFAULTS)
        settings["gym"]["max_boxes"] = "many"
        settings["claude"]["role_usd_day"] = "lots"  # the router reads a line of 0 for every role
        settings["claude"]["roles"] = ["architect", 7]
        out = self.overlay(settings)
        self.assertEqual(out["gym"]["max_boxes"], "many")
        self.assertEqual(out["claude"]["role_usd_day"], "lots")
        settings["claude"]["role_usd_day"] = {"architect": True, "audit": None}
        out = self.overlay(settings)
        self.assertIs(out["claude"]["role_usd_day"]["architect"], True, "a bool is a line of 0 to the router already")
        self.assertEqual(out["claude"]["role_usd_day"]["audit"], 6.0)

    def test_no_usable_file_is_the_floor(self):
        floor = (B.floor_usd_day("sail"), B.floor_usd_day("claude"))
        cases = {"missing": None, "future": dict(at_=NOW + 3600),
                 "negative": dict(sail=-1.0), "not a number": dict(claude="lots")}
        for name, kw in cases.items():
            (self.root / "budget.json").unlink(missing_ok=True)
            if kw is not None:
                self.write(**kw)
            out = self.overlay()
            self.assertEqual(out["budget"]["source"], "floor", name)
            self.assertEqual((out["budget"]["sail_usd_day"], out["budget"]["claude_usd_day"]), floor, name)
            self.assertEqual(out["gym"]["max_boxes"], 1, name)
        (self.root / "budget.json").write_text("{not json")
        self.assertIn("cannot be read", self.overlay()["budget"]["why"])
        (self.root / "budget.json").write_text(json.dumps({"schema": 2, "at": NOW}))
        self.assertEqual(self.overlay()["budget"]["source"], "floor")

    def test_a_stale_file_never_loosens(self):
        """A budget job that stopped: each meter is the lower of the floor and the stale file, never the floor alone."""
        for sail, claude, want in ((0.0, 0.0, (0.0, 0.0)), (0.33, 50.0, (0.33, B.floor_usd_day("claude"))),
                                   (10.0, 6.0, (B.floor_usd_day("sail"), B.floor_usd_day("claude")))):
            self.write(sail=sail, claude=claude, at_=NOW - 37 * 3600)
            out = self.overlay()
            self.assertEqual(out["budget"]["source"], "stale budget.json")
            self.assertIn("stale", out["budget"]["why"])
            self.assertEqual((out["budget"]["sail_usd_day"], out["budget"]["claude_usd_day"]), want, (sail, claude))
            self.assertEqual(B.sail_caps(out)["research"], want[0])
        doc = {"schema": 1, "at": NOW - 40 * 3600, "meters": {"sail": {"research_usd_day": 0.0, "limited_by": "unreadable"},
                                                             "claude": {"research_usd_day": "x"}}}
        (self.root / "budget.json").write_text(json.dumps(doc))
        out = self.overlay()
        self.assertEqual((out["budget"]["sail_usd_day"], out["budget"]["claude_usd_day"]), (0.0, 0.0),
                         "a meter the stale file could not read (or did not say) is 0, not the floor")

    def test_the_ceiling_never_falls_to_the_population_floor(self):
        """Births and forks stay possible at the floor's dollars (the production floor of 8 and BUILD-2's 8/16)."""
        settings = copy.deepcopy(S.DEFAULTS)
        settings["population"].update(start=16, ceiling=16, floor=8)
        out = self.overlay(settings)  # no budget.json: the floor
        self.assertEqual(out["budget"]["source"], "floor")
        self.assertEqual(out["population"]["ceiling"], 8 + B.BIRTH_MARGIN)
        self.assertGreater(out["population"]["ceiling"], out["population"]["floor"])
        settings["population"]["ceiling"] = 10
        self.assertEqual(self.overlay(settings)["population"]["ceiling"], 10, "still tighten-only: a lower ceiling stands")

    def test_openai_is_closed_by_the_budget(self):
        """OpenAI is no meter of the rule: the overlay leaves it no room, whatever the layers under it say."""
        self.write(sail=500.0, claude=400.0)
        out = self.overlay()
        self.assertEqual(out["guard"]["openai_cap_usd"], 0.0)
        self.assertEqual(out["budget"]["openai_usd_day"], 0.0)

    def test_the_operators_budget_key_is_replaced(self):
        settings = copy.deepcopy(S.DEFAULTS)
        settings["budget"] = {"source": "budget.json", "sail_usd_day": 9999.0, "claude_usd_day": 9999.0}
        out = self.overlay(settings)
        self.assertEqual(out["budget"]["source"], "floor")
        self.assertEqual(out["budget"]["sail_usd_day"], B.floor_usd_day("sail"))


class SettingsLoad(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = Path(self.dir.name)

    def test_a_state_root_always_carries_a_budget_and_none_without_one(self):
        loaded = S.load(self.root, config={})
        self.assertEqual(loaded["budget"]["source"], "floor")
        self.assertEqual(loaded["population"]["ceiling"], loaded["population"]["floor"] + B.BIRTH_MARGIN)
        self.assertGreater(loaded["population"]["ceiling"], loaded["population"]["floor"])
        self.assertEqual(loaded["population"]["start"], loaded["population"]["ceiling"], "the start is held under the ceiling")
        self.assertEqual(loaded["guard"]["openai_cap_usd"], 0.0, "no OpenAI room under the budget")
        self.assertNotIn("budget", S.load(None, config={}))
        self.assertEqual(S.load(None, config={})["population"]["ceiling"], 96)

    def test_budget_json_is_applied_last_over_swarm_json(self):
        import time

        (self.root / "swarm.json").write_text(json.dumps({"gym": {"max_boxes": 30}, "budget": {"sail_usd_day": 1e6},
                                                           "guard": {"after_burst_usd_day": 500}}))
        (self.root / "budget.json").write_text(json.dumps({"schema": 1, "at": time.time() - 60, "meters": {
            "sail": {"research_usd_day": 16.0}, "claude": {"research_usd_day": 4.0}}}))
        loaded = S.load(self.root, config={})
        self.assertEqual(loaded["gym"]["max_boxes"], 6, "16 x 0.6 / 1.6: the operator's 30 is tightened")
        self.assertEqual(loaded["budget"]["sail_usd_day"], 16.0)
        self.assertNotIn("burst_until", loaded["guard"])
        self.assertNotIn("after_burst_usd_day", S.DEFAULTS["guard"])

    def test_a_rule_that_cannot_run_is_no_research(self):
        with mock.patch.object(B, "overlay", side_effect=RuntimeError("boom")):
            loaded = S.load(self.root, config={})
        self.assertEqual((loaded["budget"]["sail_usd_day"], loaded["budget"]["claude_usd_day"]), (0.0, 0.0))
        self.assertEqual(loaded["budget"]["source"], "unavailable")


class Meter:
    def __init__(self, remaining):
        self.value = remaining
        self.last = {}

    def remaining(self):
        from decimal import Decimal

        return Decimal(str(self.value))


class ClaudeRoom(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.clock = Clock(NOW)
        self.store = SwarmStore(Path(self.dir.name), clock=self.clock)
        self.addCleanup(self.store.close)
        self.settings = copy.deepcopy(S.DEFAULTS)
        self.settings["claude"]["usd_cap"] = 10_000.0
        self.router = ModelRouter(self.store, None, settings=self.settings, claude_factory=lambda model: None,
                                  claude_meter=Meter(500))

    def admit(self, required):
        errors = []
        out = self.router._claude_admit(role="architect", family=None, key="k", model="claude-opus-5-5",
                                        body={"max_tokens": 100, "output_config": {"effort": "high"}}, required=required,
                                        errors=errors)
        return out, errors

    def test_no_block_is_the_routers_own_read(self):
        """Settings handed in without the block (a scheduler change that dropped it) never lift the budget: the router
        reads its store root's budget.json itself, the floor when there is none."""
        self.assertEqual(self.router.claude_budget_room(), B.floor_usd_day("claude"))
        self.assertEqual(self.router.claude_room(), B.floor_usd_day("claude"))
        (Path(self.dir.name) / "budget.json").write_text(json.dumps({"schema": 1, "at": NOW - 60, "meters": {
            "sail": {"research_usd_day": 1.0}, "claude": {"research_usd_day": 0.5}}}))
        self.assertEqual(self.router.claude_budget_room(), 0.5)

    def test_the_budgets_claude_dollars_today_cap_the_room_and_admission(self):
        self.settings["budget"] = {"source": "budget.json", "sail_usd_day": 3.0, "claude_usd_day": 2.0}
        self.assertEqual(self.router.claude_room(), 2.0)
        (request, kind), _ = self.admit(1.5)
        self.assertIsNotNone(request)
        (request, kind), errors = self.admit(1.0)
        self.assertEqual((request, kind), (None, "line"), "a budget line, not a funding cliff (no_room)")
        self.assertIn("research budget", errors[0])
        self.assertEqual(self.router.claude_funded_room(), 495.0, "the funded room is the gateway's (a fake meter here)")
        self.clock.advance(DAY)  # a new UTC day: its own dollars
        self.assertEqual(self.router.claude_budget_room(), 2.0)

    def test_openai_spend_today_counts_against_the_line_and_openai_is_refused_by_it(self):
        self.settings["budget"] = {"source": "budget.json", "sail_usd_day": 3.0, "claude_usd_day": 2.0}
        self.store.add_spend("openai", 1.25)
        self.assertEqual(self.router.claude_budget_room(), 0.75)
        errors: list[str] = []
        out = self.router._ask_openai(role="architect", system="s", user="u", family=None, key="k", openai_model="gpt-6-astra",
                                      max_output=1000, effort="medium", need_usd=1.0, errors=errors)
        self.assertIsNone(out)
        self.assertIn("paid-model line", errors[0])
        self.assertEqual(self.store.spent(["openai"]), 1.25, "nothing admitted")

    def test_an_openai_hold_released_after_midnight_lifts_no_line(self):
        """OpenAI's spend counts on the day its hold was booked, as Claude's does: the true-up or the refusal of a hold
        booked before 00:00 UTC is a negative row today, and it pays for neither model's spend today."""
        self.settings["budget"] = {"source": "budget.json", "sail_usd_day": 3.0, "claude_usd_day": 2.0}
        releases = ((0.4 - 3.0, {"settles": "k0"}), (-3.0, {"refused": 429, "releases": "k1"}),
                    (-3.0, {"refused": 429}))  # the last: a refusal row from before it named its hold
        for day, (usd, detail) in enumerate(releases, start=1):
            with self.subTest(detail=detail):
                midnight = NOW - NOW % DAY + day * DAY
                self.clock.t = midnight - 60
                self.store.add_spend("openai", 3.0, detail={"role": "audit", "hold": f"k{day - 1}"})
                self.clock.t = midnight + 60
                self.store.add_spend("openai", usd, detail={"role": "audit", **detail})
                self.assertLess(self.store.spent(["openai"], since=midnight), 0, "today's OpenAI rows sum under 0")
                self.assertEqual(self.router.openai_spent(since=midnight), 0.0)
                self.assertEqual(self.router.claude_budget_room(), 2.0)
                (request, _), _ = self.admit(1.5)
                self.assertIsNotNone(request)
                self.assertEqual(self.router.claude_budget_room(), 0.5, "the line less Claude's own spend today")
                (request, kind), errors = self.admit(1.0)
                self.assertEqual((request, kind), (None, "line"), "yesterday's release bought no Claude today")
                self.assertIn("research budget", errors[0])
                self.store.add_spend("openai", 0.25, detail={"role": "audit", "hold": f"today{day}"})
                self.assertEqual(self.router.claude_budget_room(), 0.25, "nor does it hide OpenAI's spend today")
        # Two calls on one key across 00:00 UTC: the older, larger hold's release meets today's hold and counts for no
        # more than it, so it hides none of today's other OpenAI spend.
        midnight = NOW - NOW % DAY + (len(releases) + 1) * DAY
        self.clock.t = midnight - 60
        self.store.add_spend("openai", 3.0, detail={"role": "audit", "hold": "same"})
        self.clock.t = midnight + 60
        self.store.add_spend("openai", 1.0, detail={"role": "audit", "hold": "same"})
        self.store.add_spend("openai", -3.0, detail={"role": "audit", "refused": 429, "releases": "same"})
        self.store.add_spend("openai", 0.5, detail={"role": "audit", "hold": "other"})
        self.assertEqual(self.router.openai_spent(since=midnight), 0.5)
        self.assertEqual(self.router.claude_budget_room(), 1.5)

    def openai(self, *, takes=0.0, **answer):
        """One `_ask_openai` call (a $1 hold) on a fake client that answers `takes` seconds after the hold is booked."""
        clock = self.clock

        class Slow(FakeFrontier):
            def ask(self, **kw):
                clock.advance(takes)
                return super().ask(**kw)

        self.router.month, self.router.frontier_factory = FakeMonth(1000), lambda model: Slow(model, **answer)
        return self.router._ask_openai(role="architect", system="s", user="u", family=None, key="k", max_output=1000,
                                       openai_model="gpt-6-astra", effort="medium", need_usd=1.0, errors=[])

    def test_an_openai_call_counts_on_its_holds_day_at_its_settled_cost(self):
        """The router's own rows: a refusal names the hold it releases, so a call refused or settled on its hold's day
        counts at its cost that day, and one answered after 00:00 UTC still counts on the day it was held."""
        from league.frontier import FrontierError

        self.settings["budget"] = {"source": "budget.json", "sail_usd_day": 3.0, "claude_usd_day": 2.0}
        refusal = FrontierError("refused", status=429)
        self.assertIsNone(self.openai(fail=refusal))
        self.assertEqual(self.store.spent(["openai"]), 0.0)
        self.assertEqual(self.router.claude_budget_room(), 2.0, "refused on its hold's own day: the line is whole again")
        self.assertEqual(self.openai(cost="0.40")["cost_usd"], 0.4)
        self.assertAlmostEqual(self.router.claude_budget_room(), 1.6, places=6, msg="settled that day: its cost")
        # Held a minute before 00:00 UTC, answered a minute after it: the release is booked on the new day.
        for day, answer in enumerate(({"cost": "0.25"}, {"fail": refusal}), start=1):
            with self.subTest(answer=answer):
                midnight = NOW - NOW % DAY + day * DAY
                self.clock.t = midnight - 60
                self.openai(takes=120.0, **answer)
                self.assertEqual(self.clock(), midnight + 60)
                self.assertLess(self.store.spent(["openai"], since=midnight), 0, "held yesterday, released today")
                self.assertEqual(self.router.claude_budget_room(), 2.0)
                (request, _), _ = self.admit(0.5)
                self.assertIsNotNone(request)
                self.assertEqual(self.router.claude_budget_room(), 1.5, "the line less Claude's own spend today")
                (request, kind), errors = self.admit(1.75)
                self.assertEqual((request, kind), (None, "line"))
                self.assertIn("research budget", errors[0])

    def test_the_line_is_the_protected_rules_arithmetic(self):
        self.settings["budget"] = {"source": "budget.json", "sail_usd_day": 3.0, "claude_usd_day": 2.0}
        with mock.patch.object(B, "paid_model_room", return_value=0.42) as rule:
            self.assertEqual(self.router.claude_budget_room(), 0.42)
        rule.assert_called_once()
        with mock.patch.object(B, "paid_model_room", side_effect=RuntimeError("boom")):
            self.assertEqual(self.router.claude_budget_room(), 0.0, "a rule that cannot run is no paid research")
        self.assertIsNone(B.paid_model_room(None, 5.0))
        self.assertEqual(B.paid_model_room({"claude_usd_day": 2.0}, 0.5), 1.5)
        self.assertEqual(B.paid_model_room({"claude_usd_day": 2.0}, float("nan")), 0.0)
        self.assertEqual(B.paid_model_room({"claude_usd_day": 2.0}, 1.5, -2.6), 0.5, "each model's spend floored on its own")
        self.assertEqual(B.paid_model_room({"claude_usd_day": 2.0}, 0.5, 0.25), 1.25)
        self.assertEqual(B.paid_model_room({"claude_usd_day": 2.0}, 0.5, float("nan")), 0.0)
        self.assertEqual(B.paid_model_room({"claude_usd_day": 2.0}, 0.5, None), 0.0)
        self.assertEqual(B.paid_model_room({"claude_usd_day": 2.0}), 0.0, "no spend given is no room")

    def test_a_malformed_block_is_no_claude(self):
        for bad in ({"claude_usd_day": "lots"}, {"claude_usd_day": -3}, [], "budget"):
            self.settings["budget"] = bad
            self.assertEqual(self.router.claude_room(), 0.0, bad)
            self.assertEqual(self.admit(0.01)[0], (None, "line"))

    def test_no_reading_of_the_line_is_no_room_never_no_line(self):
        """`claude_budget_room` answers a number whatever it is handed. Were it ever to answer None, that is no room for
        either paid model, at the first read and at the read inside the write transaction: never "no line, admit"."""
        self.settings["budget"] = {"source": "budget.json", "sail_usd_day": 3.0, "claude_usd_day": 2.0}
        asked: list[dict] = []
        self.router.month, self.router.frontier_factory = FakeMonth(1000), lambda model: FakeFrontier(model, asked=asked)

        def unread(*first):
            reads = iter(first)  # the line as it reads first, then None for ever
            return mock.patch.object(self.router, "claude_budget_room", side_effect=lambda: next(reads, None))

        for first in ((), (2.0,)):
            with self.subTest(first=first):
                with unread(*first):
                    (request, kind), errors = self.admit(0.5)
                self.assertEqual((request, kind), (None, "line"))
                self.assertIn("research budget's Claude line for today has no room", errors[0])
                errors = []
                with unread(*first):
                    out = self.router._ask_openai(role="architect", system="s", user="u", family=None, key="k", max_output=1000,
                                                  openai_model="gpt-6-astra", effort="medium", need_usd=1.0, errors=errors)
                self.assertIsNone(out)
                self.assertEqual(["paid-model line" in e for e in errors], [] if first else [True])
        with unread():
            self.assertEqual(self.router.claude_room(), 0.0)
        self.assertEqual(asked, [], "no call was sent")
        self.assertEqual((self.store.spent(["claude"]), self.store.spent(["openai"])), (0.0, 0.0), "and no hold was booked")
        self.assertIsNotNone(self.admit(0.5)[0][0], "the same call is admitted once the line reads")
        self.assertEqual(self.openai()["route"], "openai")


class OwnRead(unittest.TestCase):
    """The protected budget does not rest on the scheduler lane passing the block: the Sail guard and the router read
    the store root's budget.json themselves when the settings carry none, and every Swarm step's settings carry it."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = Path(self.dir.name)

    def test_the_guard_reads_the_budget_itself_without_a_block(self):
        from league.swarm.guard import budget_caps

        settings = {"guard": {"house_burn_usd_day": 1.0}}
        self.assertEqual(budget_caps(settings, self.root, NOW)["research"], B.floor_usd_day("sail"))
        (self.root / "budget.json").write_text(json.dumps({"schema": 1, "at": NOW - 60, "meters": {
            "sail": {"research_usd_day": 0.0}, "claude": {"research_usd_day": 0.0}}}))
        caps = budget_caps(settings, self.root, NOW)
        self.assertEqual(caps["research"], 0.0, "a budget of 0 on disk is 0, not the floor")
        self.assertIn("own read", caps["source"])

    def test_every_swarm_step_carries_the_budget_block(self):
        from league.swarm.loop import Swarm
        from league.tests import test_swarm_loop as L

        case = L.LoopCase("run")
        case.setUp()
        self.addCleanup(case.doCleanups)
        sw = Swarm(case.root, settings=case.settings, config={}, store=case.store, router=case.router, pool=case.pool,
                   sleep=lambda s: None)
        self.assertIs(sw.guard.settings, sw.settings, "the guard reads the Swarm's own settings dict")
        sw.guard = case.guard
        sw.step()
        self.assertIn("budget", sw.settings)
        self.assertEqual(sw.settings["budget"]["source"], "floor")
        self.assertEqual(sw.settings["guard"]["openai_cap_usd"], 0.0)
        self.assertGreater(sw.settings["population"]["ceiling"], sw.settings["population"]["floor"])


class Edge(unittest.TestCase):
    def test_sessions_are_counted_from_the_first_monday(self):
        self.assertEqual(B.edge_state(at(2026, 10, 5, 19, 0), [])["sessions"], 0, "before Monday's close")
        self.assertEqual(B.edge_state(at(2026, 10, 5, 21, 0), [])["sessions"], 1)
        self.assertEqual(B.edge_state(at(2026, 10, 12, 21, 0), [])["sessions"], 6)

    def test_sixty_sessions_without_a_promotion_stop_the_profit_share(self):
        before = B.edge_state(at(2026, 12, 28, 22, 0), [])
        self.assertEqual((before["sessions"], before["stop"]), (59, False))
        after = B.edge_state(at(2026, 12, 29, 21, 30), [])
        self.assertEqual((after["sessions"], after["stop"]), (60, True), "Thanksgiving and Christmas are not sessions")
        self.assertIn("no forward edge", after["why"])

    def test_a_promotion_lifts_it_and_restarts_the_count(self):
        lifted = B.edge_state(at(2026, 12, 29, 21, 30), [at(2026, 10, 9, 15, 0), at(2026, 12, 1, 15, 0)])
        self.assertEqual((lifted["anchor"], lifted["stop"]), ("2026-12-02", False))
        self.assertEqual(lifted["sessions"], 19)

    def test_an_unreadable_record_counts_as_none(self):
        out = B.edge_state(at(2026, 12, 29, 21, 30), None)
        self.assertTrue(out["stop"])
        self.assertIn("could not be read", out["why"])


class FakeSail:
    def __init__(self, per_day=None, fail=False):
        self.per_day = per_day or {"sb_house": 1.2, "sb_data": 0.3}
        self.fail = fail
        self.calls = []

    def spend(self, *, sailbox=None, since=None, until=None, app=None):
        self.calls.append((sailbox, since, until))
        if self.fail:
            raise OSError("sail is down")
        return {"estimated_total_cost_usd_nanos": int(self.per_day[sailbox] * 7 * 1e9)}


class Job(unittest.TestCase):
    """`run(ctx)` end to end over a state root of fakes."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = Path(self.dir.name)
        self.clock = Clock(NOW)
        store = SwarmStore(self.root, clock=self.clock)
        store.put("guard", {"braked": False, "last": {"balance": 600.0, "at": NOW - 120}})
        self.clock.t = NOW - 2 * DAY
        store.add_spend("sail_model", 9.0)
        store.add_spend("gym_box", 12.0)
        store.add_spend("claude", 7.0)
        self.clock.t = NOW - 9 * DAY
        store.add_spend("claude", 500.0)  # outside the need window
        self.clock.t = NOW
        store.close()
        (self.root / "data").mkdir()
        (self.root / "data" / "data_box.json").write_text(json.dumps({"box_id": "sb_data"}))
        self.book([(1, 50.0, NOW - 6 * DAY, NOW - 5 * DAY), (2, -10.0, NOW - 3 * DAY, NOW - 2 * DAY),
                   (3, 400.0, NOW - 41 * DAY, NOW - 40 * DAY), (4, 99.0, at(2026, 9, 25), at(2026, 9, 27))])
        (self.root / "publish.json").write_text(json.dumps({"activity": {"reading": {"fees_by_pid": {"1": "-0.02", "3": "-1"}}}}))
        self.sent: list[dict] = []
        self.answer = {"sent": True}
        self.health = {"claude": {"cap_usd": 400, "spent_usd": 185, "inflight_usd": 10, "configured": True}}
        self.alerts: list[tuple[str, str]] = []
        self.sail = FakeSail()

    def book(self, rows, *, qty=0):
        from league.live.state import LiveState

        state = LiveState(self.root / "live.sqlite", clock=self.clock)
        for pid, cash, opened, closed in rows:
            state.db.execute(
                "INSERT INTO positions(pid, instance, family, type, root, legs, qty, opened_qty, entry, max_loss_share, "
                "collateral, fees, cash, opened_at, opened_day, opened_minute, status, closed_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (pid, "i", "f", "debit_vertical", "SPY", "[]", qty, 1, 1.0, 0.1, 0.0, 0.1, cash, opened, "d", 0, "closed", closed))
        state.close()

    def ctx(self, **kw):
        return {"root": self.root, "now": kw.get("now", NOW), "config": {"backup": {"box_id": "sb_house"}},
                "sail": kw.get("sail", self.sail), "gateway_health": kw.get("health", lambda: self.health),
                "notify": kw.get("notify", self.notify), "alert": lambda level, text: self.alerts.append((level, text))}

    def notify(self, facts):
        self.sent.append(dict(facts))
        return self.answer

    def doc(self):
        return json.loads((self.root / "budget.json").read_text())

    def test_the_day_is_computed_from_the_houses_own_reads(self):
        from league.ops import economics
        # A clean day: the close economics ran and reads what the book reads (no summary yet is said, as a warning).
        with mock.patch.object(economics, "latest", lambda root: self.summary("39.98")):
            receipt = B.run(self.ctx())
        doc = self.doc()
        self.assertEqual(doc["inputs"]["p30_usd"], 39.98, "50 - 0.02 + (-10): the 40-day and pre-basis closes are out")
        self.assertIn("the live book", doc["inputs"]["p30_source"])
        self.assertAlmostEqual(doc["earned_usd_day"], 0.5 * 39.98 / 30, places=4)
        sail, claude = doc["inputs"]["meters"]["sail"], doc["inputs"]["meters"]["claude"]
        self.assertEqual((sail["balance_usd"], sail["fixed_usd_day"], sail["need_usd"]), (600.0, 1.5, 21.0))
        # 400 - 185: the gateway's spent_usd already holds the 10 in flight, so it is not subtracted twice.
        self.assertEqual((claude["balance_usd"], claude["need_usd"]), (215.0, 7.0), "cap - spent: the holds are in spent")
        self.assertEqual(sorted(c[0] for c in self.sail.calls), ["sb_data", "sb_house"])
        self.assertEqual(doc["meters"]["sail"]["need_share"], 0.75)
        self.assertEqual(receipt["errors"], [])
        self.assertEqual(self.alerts, [], "a clean day raises nothing")
        self.assertEqual(self.sent, [], "no meter is short")
        block, why = B.read(self.root, NOW + 3600)  # what the next settings.load reads
        self.assertIsNone(why)
        self.assertEqual(block["sail_usd_day"], doc["meters"]["sail"]["research_usd_day"])
        self.assertEqual(block["fixed_sail_usd_day"], 1.5)

    def test_every_read_that_fails_is_closed(self):
        (self.root / "live.sqlite").unlink()
        self.book([(9, 50.0, NOW - 6 * DAY, NOW - 5 * DAY)], qty=1)  # a "closed" row still holding contracts
        receipt = B.run(self.ctx(sail=FakeSail(fail=True), health=lambda: (_ for _ in ()).throw(OSError("down"))))
        doc = self.doc()
        self.assertIsNone(doc["inputs"]["p30_usd"])
        self.assertEqual(doc["earned_usd_day"], 0.0)
        self.assertEqual(doc["meters"]["claude"]["research_usd_day"], 0.0)
        self.assertEqual(doc["inputs"]["meters"]["sail"]["fixed_usd_day"], 1.0, "guard.house_burn_usd_day")
        self.assertTrue(receipt["warning"])
        self.assertTrue(any("box spend" in e for e in receipt["errors"]))
        self.assertEqual(len(self.alerts), 1, "fail-closed is a House warning, not silence")
        self.assertEqual(self.alerts[0][0], "warning")
        self.assertIn("Claude's balance", self.alerts[0][1])

    def test_a_stale_guard_reading_gives_sail_no_research(self):
        store = SwarmStore(self.root, clock=self.clock)
        store.put("guard", {"last": {"balance": 600.0, "at": NOW - 7 * 3600}})
        store.close()
        receipt = B.run(self.ctx())
        self.assertEqual(self.doc()["meters"]["sail"]["research_usd_day"], 0.0)
        self.assertTrue(any("no fresh reading" in e for e in receipt["errors"]))
        self.assertEqual(len(self.alerts), 1)

    def test_one_failed_guard_read_before_the_job_keeps_the_last_good_balance(self):
        """The review's case: a single Sail blip just before 00:30Z must not zero the day's Sail research."""
        store = SwarmStore(self.root, clock=self.clock)
        store.put("guard", {"last": {"balance": None, "at": NOW - 60}, "last_good": {"balance": 600.0, "at": NOW - 240}})
        store.close()
        B.run(self.ctx())
        doc = self.doc()
        self.assertEqual(doc["inputs"]["meters"]["sail"]["balance_usd"], 600.0)
        self.assertIn("last good", doc["inputs"]["meters"]["sail"]["balance_source"])
        self.assertGreater(doc["meters"]["sail"]["research_usd_day"], 0.0)

    def test_a_paused_swarm_still_tells_the_owner_from_the_gateways_sail_reading(self):
        """The review's case: the swarm paused, the guard's reading goes stale while the House box burns Sail."""
        self.reading(600.0, NOW - 7 * 3600)
        self.health["sail"] = {"balance_usd": 40.0, "checked_at": B._iso(NOW - 600)}
        self.answer = {"sent": True}
        receipt = B.run(self.ctx())
        doc = self.doc()
        self.assertEqual(doc["meters"]["sail"]["research_usd_day"], 0.0, "the gateway's reading is never research")
        self.assertEqual([n["meter"] for n in receipt["notices"]], ["sail"])
        self.assertEqual(self.sent[0]["balance_usd"], "40.00")
        self.health["sail"] = {"balance_usd": 40.0, "checked_at": B._iso(NOW - 8 * 3600)}
        (self.root / B.NOTICES_FILE).unlink()
        self.assertEqual(B.run(self.ctx())["notices"], [], "a stale gateway reading is no reading either")

    def economics(self, summary, *, p30=None):
        """A stand-in for league/ops/economics.py's two readers with WP2's own shapes: `latest(root)` -> the newest
        summary or None, `p30(summary, *, days=30)` -> {"usd": "<decimal>", ...}. On the module itself: it is in the
        release, so `budget._p30` finds the real one whatever `sys.modules` says."""
        from league.ops import economics

        return mock.patch.multiple(economics, latest=lambda root: summary,
                                   p30=p30 or (lambda summary, *, days=30: {"usd": summary["p30"]["usd"], "days": days}))

    def summary(self, usd="300.00", *, cutoff=NOW - 3600, **extra):
        """A close summary as far as the budget and the economics' own `p30` read it: one close day worth `usd`."""
        closes = [{"day": B._ny_day(cutoff).isoformat(), "total_usd": usd, "closed_positions": 1}]
        return {"cutoff": B._iso(cutoff), "p30": {"usd": usd}, "positions": [], "reconciliation": {"blocking": []},
                "realized": {"by_close_day": closes}, **extra}

    #: The source the budget names when the close economics (a summary cut three hours before NOW) cuts the book's read.
    CUT = f"league.ops.economics.p30 (cutoff {B._iso(NOW - 3 * 3600)}): below the live book's own read, which caps it"

    def test_the_close_economics_p30_may_cut_what_was_earned_never_raise_it(self):
        """The close economics (league/ops/economics.py) is a second source: an inflated p30 there must not lift the
        budget past the live book's own read (the D4 rule), but a smaller one (more fees found) is used."""
        from league.ops import economics
        with mock.patch.object(economics, "latest", lambda root: self.summary("300.00", cutoff=NOW - 3 * 3600)):
            B.run(self.ctx())
        self.assertEqual(self.doc()["inputs"]["p30_usd"], 39.98)
        self.assertIn("the live book", self.doc()["inputs"]["p30_source"])
        with mock.patch.object(economics, "latest", lambda root: self.summary("12.50", cutoff=NOW - 3 * 3600)):
            B.run(self.ctx())
        self.assertEqual(self.doc()["inputs"]["p30_usd"], 12.5)
        self.assertEqual(self.doc()["inputs"]["p30_source"], self.CUT)

    def test_an_unreadable_book_earns_nothing_whatever_the_economics_says(self):
        from league.ops import economics
        (self.root / "live.sqlite").unlink()
        self.book([(9, 50.0, NOW - 6 * DAY, NOW - 5 * DAY)], qty=1)  # a "closed" row still holding contracts
        with mock.patch.object(economics, "latest", lambda root: self.summary("300.00", cutoff=NOW - 3 * 3600)):
            B.run(self.ctx())
        self.assertIsNone(self.doc()["inputs"]["p30_usd"])
        self.assertEqual(self.doc()["earned_usd_day"], 0.0)

    def test_a_losing_month_in_the_close_economics_is_a_number_not_a_fallback(self):
        """A negative p30 is a loss, never "no number": the book (which can read positive) does not stand in for it."""
        from league.ops import economics
        with mock.patch.object(economics, "latest", lambda root: self.summary("-3.10", cutoff=NOW - 3 * 3600)):
            receipt = B.run(self.ctx())
        doc = self.doc()
        self.assertEqual((doc["inputs"]["p30_usd"], doc["inputs"]["p30_source"]), (-3.1, self.CUT))
        self.assertEqual(doc["earned_usd_day"], 0.0)
        self.assertEqual(receipt["errors"], [])

    def test_a_job_that_reports_failed_is_a_failed_receipt(self):
        """The grant's refusal ({"status": "failed"}) is never recorded as ok."""
        from league.ops.__main__ import run_job

        fake = types.ModuleType("fake_grant")
        fake.run = lambda ctx: {"status": "failed", "action": "none", "error": "the digest moved with no owner deploy"}
        with mock.patch("importlib.import_module", return_value=fake):
            out = run_job("grant", root=self.root, due_at=NOW, ctx=types.SimpleNamespace(alerts=[]))
        self.assertEqual(out["status"], "failed")
        self.assertIn("the digest moved", out["error"])
        fake.run = lambda ctx: {"status": "ok", "action": "none"}
        with mock.patch("importlib.import_module", return_value=fake):
            self.assertEqual(run_job("grant", root=self.root, due_at=NOW, ctx=types.SimpleNamespace(alerts=[]))["status"], "ok")

    def test_a_stale_close_economics_falls_back_to_the_book(self):
        from league.ops import economics
        with mock.patch.object(economics, "latest", lambda root: self.summary("300.00", cutoff=NOW - 3 * DAY)):
            receipt = B.run(self.ctx())
        self.assertEqual(self.doc()["inputs"]["p30_usd"], 39.98)
        self.assertIn("the close economics is stale: the live book's own read is used", receipt["errors"])

    def test_unknown_close_economics_is_never_replaced_by_the_book(self):
        """The review's case: the economics says unknown; the book's read (+39.98 here) must not stand in for it."""
        cases = {"not a number": self.summary(usd=None),
                 "unpriced close": self.summary(positions=[{"pid": 7, "status_at_cutoff": "unpriced_close"}]),
                 "blocking": self.summary(reconciliation={"blocking": ["an expiry the book has not settled"]}),
                 "pending at the cutoff": self.summary(reconciliation={"blocking": [], "pending_orders_at_cutoff": [3]}),
                 # A summary too malformed to inspect (its positions are no list) is unknown, not a crashed job.
                 "malformed": self.summary(positions=7)}
        for name, summary in cases.items():
            self.alerts.clear()
            with self.economics(summary):
                B.run(self.ctx())
            self.assertIsNone(self.doc()["inputs"]["p30_usd"], name)
            self.assertEqual(self.doc()["earned_usd_day"], 0.0, name)
            self.assertEqual(len(self.alerts), 1, name)
        with self.economics(self.summary(), p30=lambda summary, *, days=30: (_ for _ in ()).throw(KeyError("cutoff"))):
            B.run(self.ctx())
        self.assertIsNone(self.doc()["inputs"]["p30_usd"], "a p30 that raises is unknown, not the book")

    def test_no_fresh_summary_falls_back_to_the_book_and_says_so(self):
        for summary in (None, self.summary(cutoff=NOW - 5 * DAY)):
            with self.economics(summary):
                receipt = B.run(self.ctx())
            self.assertEqual(self.doc()["inputs"]["p30_usd"], 39.98)
            self.assertTrue(any("live book's own read is used" in e for e in receipt["errors"]))
        # Monday 00:30Z: Friday's close is still the latest (counted in sessions, not hours). Its 12.50 is under the
        # book's 39.98, so it is the number (a larger one would be capped by the book and show nothing).
        with self.economics(self.summary("12.50", cutoff=at(2026, 10, 16, 20, 10))):
            B.run(self.ctx(now=at(2026, 10, 19, 0, 30)))
        self.assertEqual(self.doc()["inputs"]["p30_usd"], 12.5, "a weekend's summary is still read")
        self.assertTrue(B.economics_fresh(at(2026, 10, 16, 20, 10), at(2026, 10, 20, 0, 30)) is False,
                        "Monday's close came and went: Friday's summary is stale")

    def test_a_fresh_summary_without_its_closes_by_day_is_unknown_and_says_so(self):
        """`realized.by_close_day` is the list the economics' own p30 sums. A fresh summary without it would read 0.00
        from nothing: it is unknown (never that 0.00, never the book's +39.98), and the job says so."""
        from league.ops import economics
        said = "the close economics' summary holds no closes by day (realized.by_close_day): p30 is unknown"
        shapes = {"no realized": None, "no by_close_day": {}, "a null": {"by_close_day": None},
                  "not a list": {"by_close_day": {}}}
        for name, realized in shapes.items():
            self.alerts.clear()
            summary = self.summary("12.50", cutoff=NOW - 3 * 3600, realized=realized)
            self.assertEqual(economics.p30(summary)["usd"], "0.00", f"{name}: what the economics' p30 makes of it")
            with mock.patch.object(economics, "latest", lambda root: summary):
                receipt = B.run(self.ctx())
            doc = self.doc()
            self.assertEqual((doc["inputs"]["p30_usd"], doc["inputs"]["p30_source"]), (None, said), name)
            self.assertEqual(doc["earned_usd_day"], 0.0, name)
            self.assertEqual(receipt["errors"], [said], name)
            self.assertEqual(len(self.alerts), 1, name)
        quiet = self.summary("12.50", cutoff=NOW - 3 * 3600, realized={"by_close_day": []})
        with mock.patch.object(economics, "latest", lambda root: quiet):
            receipt = B.run(self.ctx())
        self.assertEqual((self.doc()["inputs"]["p30_usd"], receipt["errors"]), (0.0, []), "no closes in the window is a number")

    def test_a_close_summary_that_is_not_a_summary_is_said_and_the_book_stands(self):
        """`economics.latest` answering anything but a summary or None is never passed over in silence."""
        from league.ops import economics
        for summary in (["2026-10-20"], "summary.json", 0, False):
            self.alerts.clear()
            with mock.patch.object(economics, "latest", lambda root: summary):
                receipt = B.run(self.ctx())
            self.assertEqual(self.doc()["inputs"]["p30_usd"], 39.98, repr(summary))
            self.assertIn("the live book", self.doc()["inputs"]["p30_source"])
            self.assertEqual(receipt["errors"], [f"the close economics' summary is not a mapping ({type(summary).__name__}): "
                                                 "the live book's own read is used"], repr(summary))
            self.assertEqual(len(self.alerts), 1, repr(summary))
        with mock.patch.object(economics, "latest", side_effect=OSError("gone")):
            receipt = B.run(self.ctx())
        self.assertEqual(receipt["errors"], ["the close economics could not be read (OSError): the live book's own read is used"],
                         "a read that failed is said once")

    def test_the_books_own_read_is_unknown_on_what_profit_calls_unknown(self):
        """The review's case: an expired structure closed at the venue but not priced (unpriced_close, a real -80) must
        not leave +60 of other closes to fund research."""
        from league.live.state import LiveState

        state = LiveState(self.root / "live.sqlite", clock=self.clock)
        state.db.execute("UPDATE positions SET status='unpriced_close', closed_at=NULL WHERE pid=2")
        state.close()
        value, why = B.book_p30(self.root, NOW)
        self.assertIsNone(value)
        self.assertIn("unpriced_close", why)
        B.run(self.ctx())
        self.assertIsNone(self.doc()["inputs"]["p30_usd"])
        state = LiveState(self.root / "live.sqlite", clock=self.clock)
        state.db.execute("UPDATE positions SET status='closed', closed_at=? WHERE pid=2", (NOW - 2 * DAY,))
        state.db.execute("INSERT INTO kv(key, value) VALUES('recon', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                         (json.dumps({"frozen": "a fill the venue does not show"}),))
        state.close()
        self.assertEqual(B.book_p30(self.root, NOW), (None, "reconciliation is frozen: p30 is unknown"))
        state = LiveState(self.root / "live.sqlite", clock=self.clock)
        state.db.execute("DELETE FROM kv WHERE key='recon'")
        state.close()
        self.assertEqual(B.book_p30(self.root, NOW)[0], 39.98)
        (self.root / "publish.json").write_text(json.dumps({"activity": {"reading": {"fees_by_pid": {}, "blocking": ["x"]}}}))
        self.assertIsNone(B.book_p30(self.root, NOW)[0], "a blocking account reading is unknown")

    def test_only_a_ladder_promotion_lifts_the_stop(self):
        store = SwarmStore(self.root, clock=Clock(at(2026, 12, 1, 15, 0)))
        # The Money table's own moves (a holdout pass, a re-promotion after a demotion) are not ladder promotions.
        store.event("swarm.band", "f1", {"band_from": "candidate", "band_to": "probe", "reason": "holdout pass"})
        store.event("swarm.band", "f2", {"band_from": "sized", "band_to": "probe", "reason": "demoted"})
        store.close()
        B.run(self.ctx(now=at(2026, 12, 29, 21, 30)))
        edge = self.doc()["inputs"]["edge"]
        self.assertEqual((edge["anchor"], edge["stop"]), ("2026-10-05", True))
        store = SwarmStore(self.root, clock=Clock(at(2026, 12, 1, 15, 0)))
        store.event("swarm.band", "f3", {"band_from": "gym", "band_to": "probe",
                                         "reason": "the forward ladder promoted it (practice receipt 12)"})
        store.close()
        B.run(self.ctx(now=at(2026, 12, 29, 21, 30)))
        edge = self.doc()["inputs"]["edge"]
        self.assertEqual((edge["anchor"], edge["stop"]), ("2026-12-02", False))

    def test_a_ladder_decision_to_promote_counts_too(self):
        import sqlite3

        db = sqlite3.connect(self.root / "observe.sqlite")
        db.execute("CREATE TABLE ladder_decisions (id INTEGER PRIMARY KEY, day TEXT, family TEXT, version INTEGER, "
                   "verdict TEXT NOT NULL, at REAL NOT NULL)")
        db.executemany("INSERT INTO ladder_decisions(day, family, version, verdict, at) VALUES (?,?,?,?,?)",
                       [("2026-11-30", "f1", 1, "would_promote", at(2026, 11, 30, 21, 0)),
                        ("2026-12-01", "f2", 1, "promote", at(2026, 12, 1, 21, 0)),
                        ("2026-12-02", "f3", 1, "blocked", at(2026, 12, 2, 21, 0))])
        db.commit()
        db.close()
        B.run(self.ctx(now=at(2026, 12, 29, 21, 30)))
        self.assertEqual(self.doc()["inputs"]["edge"]["anchor"], "2026-12-02")

    def reading(self, balance, at_):
        store = SwarmStore(self.root, clock=self.clock)
        store.put("guard", {"last": {"balance": balance, "at": at_}})
        store.close()

    def test_a_short_meter_is_told_once_a_week_and_only_when_sent(self):
        self.reading(60.0, NOW - 60)
        self.answer = {"sent": False, "reason": "no mail binding"}
        receipt = B.run(self.ctx())
        self.assertEqual(len(self.sent), 1)
        self.assertFalse(receipt["notices"][0]["sent"])
        facts = self.sent[0]
        self.assertEqual(facts["kind"], "funding")
        self.assertEqual(facts["notice_id"], "funding:sail:2026-W43")
        # At the rate it wants: 1.5 fixed + the floor's 3 + 0.75 of 0.5 x 39.98 / 30 earned.
        self.assertEqual((facts["meter"], facts["balance_usd"], facts["usd_day"], facts["runway_days"]),
                         ("sail", "60.00", "5.00", "10.0"))
        self.assertEqual((facts["current_usd_day"], facts["current_runway_days"]), ("1.50", "33.3"))
        self.assertEqual((facts["restore_usd"], facts["restore_days"], facts["card_date"]), ("399.98", 90, "2026-10-20"))
        self.assertIs(facts["test"], False)
        self.answer = {"sent": True}
        B.run(self.ctx(now=NOW + 3600))
        self.assertEqual(len(self.sent), 2, "not told yet: tried again")
        self.reading(59.0, NOW + 2 * DAY - 60)
        B.run(self.ctx(now=NOW + 2 * DAY))
        self.assertEqual(len(self.sent), 2, "told: at most once every 7 days")
        self.assertIn("at most once", self.doc()["notices"][0]["why"])
        self.reading(58.0, NOW + 8 * DAY - 60)
        B.run(self.ctx(now=NOW + 8 * DAY))
        self.assertEqual(len(self.sent), 3)
        self.assertEqual(self.sent[-1]["notice_id"], "funding:sail:2026-W44")

    def test_a_failing_gateway_is_an_error_not_a_crash(self):
        self.reading(60.0, NOW - 60)

        def down(facts):
            raise OSError("gateway down")
        receipt = B.run(self.ctx(notify=down))
        self.assertFalse(receipt["notices"][0]["sent"])
        self.assertTrue(any("funding notice" in e for e in receipt["errors"]))
        self.assertFalse((self.root / B.NOTICES_FILE).exists())

    def test_the_drill_sends_a_test_notice_and_checks_the_closed_read(self):
        out = B.drill(self.ctx(), "claude")
        self.assertTrue(out["ok"], out)
        self.assertTrue(out["checks"]["throttled_and_still_seen"], "the production shape: Claude's fixed cost is 0")
        self.assertEqual(self.sent[-1]["test"], True)
        self.assertEqual(self.sent[-1]["notice_id"], f"funding-test:claude:2026-W43:{int(NOW // 60)}")
        self.assertEqual(self.sent[-1]["meter"], "claude")
        self.assertFalse((self.root / "budget.json").exists(), "a drill writes no budget")
        self.assertFalse((self.root / B.NOTICES_FILE).exists())
        with self.assertRaises(ValueError):
            B.drill(self.ctx(), "openai")

    def test_a_second_drill_in_the_week_has_its_own_id_and_a_duplicate_is_not_delivered(self):
        B.drill(self.ctx(), "claude")
        B.drill(self.ctx(now=NOW + 3600), "claude")
        self.assertNotEqual(self.sent[0]["notice_id"], self.sent[1]["notice_id"], "the gateway remembers ids 8 days")
        self.answer = {"sent": True, "duplicate": True}
        out = B.drill(self.ctx(), "claude")
        self.assertFalse(out["sent"], "a duplicate sent no mail: the drill proves nothing")
        self.assertFalse(out["ok"])

    def test_the_claude_balance_never_subtracts_the_holds_twice(self):
        self.assertEqual(B._claude_balance({"claude": {"cap_usd": "300", "spent_usd": "185", "inflight_usd": "10",
                                                       "remaining_usd": "115"}}), 115.0)
        self.assertEqual(B._claude_balance({"claude": {"cap_usd": 300, "spent_usd": 185, "inflight_usd": 10}}), 115.0)
        self.assertIsNone(B._claude_balance({"claude": {"configured": False}}))
        self.assertIsNone(B._claude_balance({"claude": {"cap_usd": "x", "spent_usd": 1}}))


if __name__ == "__main__":
    unittest.main()
