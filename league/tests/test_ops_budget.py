"""THE BUDGET RULE (league/ops/budget.py, LTCM v3, D4): the rule's arithmetic both ways (a cut and a raise), the card line,
the no-forward-edge stop, the fail-closed reads, the tighten-only overlay in `settings.load`, Claude's room under the
budget's daily line, the funding notice (once per meter a week) and the drill. Fakes only: no network, no Sail."""

from __future__ import annotations

import copy
import datetime as dt
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from league.ops import budget as B
from league.swarm import settings as S
from league.swarm.models import ModelRouter
from league.swarm.store import SwarmStore
from league.tests.swarm_fakes import Clock

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
        self.assertEqual(claude["runway_days"], 90.0)
        self.assertEqual(claude["restore_usd"], 85.0, "5 + 90 x the full floor of 2 - 100")
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
        doc = B.compute(inputs(p30=3000.0), now=NOW)
        sail = doc["meters"]["sail"]
        self.assertEqual(sail["limited_by"], "W")
        self.assertAlmostEqual(sail["research_usd_day"], (590 - 60 * 1.5) / 60, places=4)
        self.assertEqual(sail["runway_days"], 60.0)
        self.assertEqual(B.short(doc), [], "exactly W days is not short")

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
        self.assertEqual(sail["card_date"], "2026-10-20", "already under the card line")
        self.assertEqual(sail["restore_usd"], 355.0, "10 + 90 x (1.5 + 3) - 60")
        self.assertEqual(B.short(doc), ["sail"])
        empty = B.compute(inputs(claude=3.0), now=NOW)
        self.assertEqual(empty["meters"]["claude"]["runway_days"], 0.0)
        self.assertIn("claude", B.short(empty))


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
        self.assertEqual(out["population"]["ceiling"], k["population.ceiling"])
        self.assertEqual(out["architect"]["every_seconds"], 14400, "max(): the configured 4 h is slower than the budget's")
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
        cases = {"missing": None, "stale": dict(at_=NOW - 37 * 3600), "future": dict(at_=NOW + 3600),
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
        self.assertEqual(loaded["population"]["ceiling"], 8)
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

    def test_no_block_no_budget_line(self):
        self.assertIsNone(self.router.claude_budget_room())
        self.assertEqual(self.router.claude_room(), 495.0)

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

    def test_a_malformed_block_is_no_claude(self):
        for bad in ({"claude_usd_day": "lots"}, {"claude_usd_day": -3}, [], "budget"):
            self.settings["budget"] = bad
            self.assertEqual(self.router.claude_room(), 0.0, bad)
            self.assertEqual(self.admit(0.01)[0], (None, "line"))


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
        self.health = {"claude": {"cap_usd": 300, "spent_usd": 185, "inflight_usd": 10, "configured": True}}
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
                "notify": kw.get("notify", self.notify)}

    def notify(self, facts):
        self.sent.append(dict(facts))
        return self.answer

    def doc(self):
        return json.loads((self.root / "budget.json").read_text())

    def test_the_day_is_computed_from_the_houses_own_reads(self):
        receipt = B.run(self.ctx())
        doc = self.doc()
        self.assertEqual(doc["inputs"]["p30_usd"], 39.98, "50 - 0.02 + (-10): the 40-day and pre-basis closes are out")
        self.assertIn("the live book", doc["inputs"]["p30_source"])
        self.assertAlmostEqual(doc["earned_usd_day"], 0.5 * 39.98 / 30, places=4)
        sail, claude = doc["inputs"]["meters"]["sail"], doc["inputs"]["meters"]["claude"]
        self.assertEqual((sail["balance_usd"], sail["fixed_usd_day"], sail["need_usd"]), (600.0, 1.5, 21.0))
        self.assertEqual((claude["balance_usd"], claude["need_usd"]), (105.0, 7.0))
        self.assertEqual(sorted(c[0] for c in self.sail.calls), ["sb_data", "sb_house"])
        self.assertEqual(doc["meters"]["sail"]["need_share"], 0.75)
        self.assertEqual(receipt["errors"], [])
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

    def test_a_stale_guard_reading_gives_sail_no_research(self):
        store = SwarmStore(self.root, clock=self.clock)
        store.put("guard", {"last": {"balance": 600.0, "at": NOW - 7 * 3600}})
        store.close()
        B.run(self.ctx())
        self.assertEqual(self.doc()["meters"]["sail"]["research_usd_day"], 0.0)

    def test_the_close_economics_p30_is_preferred_when_present(self):
        from league.ops import economics
        with mock.patch.object(economics, "latest", lambda root: {"cutoff": B._iso(NOW - 3 * 3600), "p30": {"usd": "300.00"}}):
            B.run(self.ctx())
        self.assertEqual((self.doc()["inputs"]["p30_usd"], self.doc()["inputs"]["p30_source"]),
                         (300.0, "league.ops.economics.p30"))

    def test_a_stale_close_economics_falls_back_to_the_book(self):
        from league.ops import economics
        with mock.patch.object(economics, "latest", lambda root: {"cutoff": B._iso(NOW - 3 * DAY), "p30": {"usd": "300.00"}}):
            receipt = B.run(self.ctx())
        self.assertEqual(self.doc()["inputs"]["p30_usd"], 39.98)
        self.assertIn("the close economics is stale: the live book's own read is used", receipt["errors"])

    def test_a_probe_promotion_is_read_from_the_swarm_store(self):
        store = SwarmStore(self.root, clock=Clock(at(2026, 12, 1, 15, 0)))
        store.event("swarm.band", "f1", {"band_from": "candidate", "band_to": "probe", "reason": "ladder"})
        store.event("swarm.band", "f2", {"band_from": "sized", "band_to": "probe", "reason": "demoted"})
        store.close()
        B.run(self.ctx(now=at(2026, 12, 29, 21, 30)))
        edge = self.doc()["inputs"]["edge"]
        self.assertEqual((edge["anchor"], edge["stop"]), ("2026-12-02", False))

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
        self.assertEqual((facts["meter"], facts["balance_usd"], facts["usd_day"], facts["runway_days"]),
                         ("sail", "60.00", "1.50", "33.3"))
        self.assertEqual((facts["restore_usd"], facts["restore_days"], facts["card_date"]), ("355.00", 90, "2026-10-20"))
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
        self.assertEqual(self.sent[-1]["test"], True)
        self.assertEqual(self.sent[-1]["notice_id"], "funding-test:claude:2026-W43")
        self.assertEqual(self.sent[-1]["meter"], "claude")
        self.assertFalse((self.root / "budget.json").exists(), "a drill writes no budget")
        self.assertFalse((self.root / B.NOTICES_FILE).exists())
        with self.assertRaises(ValueError):
            B.drill(self.ctx(), "openai")


if __name__ == "__main__":
    unittest.main()
