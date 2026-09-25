"""Compute follows yield (Y, Sept 25, 2026, the forward-first run).

In the 24 hours to T0 (04:23Z Sept 25) the floor spent $118.88 of compute against $21.35 of real settled
profit. Replayed on the T0 snapshot's 24 hourly yield rows (the lab's calls read from lab.sqlite): the lab
bought a positive forward block for $0.038, the foundry for $0.052, the engineer for $0.18 (4.7x), research
for $0.29 (7.5x), the consultant for $0.51 after its consults (13.2x, F4's reading) and the architect's $7.38
bought none. These tests pin Y1 (the lane throttle and every lane that reads it), J2's trigger skip for
practice agents (research_gate rule 13), Y2 (unit economics on the row and in health.json) and the contract
sent by section (merton.contract_for: 37.9 KB of core against the whole file's 67.3 KB).
"""

from __future__ import annotations

import json
import tempfile
import threading
import unittest
from decimal import Decimal as D
from pathlib import Path
from types import SimpleNamespace

from league.engineer import Engineer, hold_usd
from league.frontier import Answer, FrontierError
from league.ledger import Ledger, now_iso
from league.merton import (CONTRACT, Merton, ask_with_contract, asked_sections, contract_for, contract_sections,
                           contract_topics)
from league.tests.fakes import Clock
from league.tests.test_jev_sensor import GateCase, summary
from league.tests.test_research_outcomes import RealBook
from league.worklist import Worklist
from league.yield_ledger import (THROTTLE_WHAT, UnitEconomics, YieldLedger, lane_prices, plan_throttle, throttle_state,
                                 throttled)

#: The day to T0, as its 24 yield rows summed it (the lab's own calls from lab.sqlite).
T0_ROW = {"spend_usd": {"research": "51.3290", "foundry": "2.5257", "lab": "4.4965", "engineer": "10.0852", "consultant": "35.4400",
                        "architect": "7.3777", "teacher": "2.4969", "toolsmith": "0.4678", "operator": "0.5158", "audits": "0.2200"},
          "evidence": {"research": {"positive_blocks": 178}, "foundry": {"positive_blocks": 49}, "lab": {"positive_blocks": 115},
                       "engineer": {"positive_blocks": 56}}}
T0_LIFT = {"days": 7, "consultant": {"judged_blocks": 31, "usd": "60.1500", "positive_blocks_after": 119, "usd_per_positive_block": "0.5055"},
           "teacher": {"verdict": "not_started"}}


class F2Case(GateCase):
    """The research gate under F2's rules (`clock_runs: real_positions`), as test_research_outcomes sets it."""

    def f2(self, **settings):
        return self.ready(legacy=False, settings={"clock_runs": "real_positions", "abstain_lock_after": 3, "practice_pause_after": 3,
                                                  "max_skip_hours": 24, "practice_max_skip_hours": 72, "idle_runs": "barren",
                                                  "sample_hours": 6, "lesson_arm": "parity", "refusal_dedupe": True,
                                                  "practice_skip_triggers": [], **settings})

    def setUp(self):
        super().setUp()
        self.real_books = {}

    def on_real_money(self, *agents, holding=True):
        book = RealBook()
        for agent in agents:
            (book.hold if holding else book.seat)(agent)
            self.real_books[agent.id] = book
        if not getattr(self, "_patched", False):
            practice, self._patched = self.house.book_of, True
            self.house.book_of = lambda a: self.real_books.get(a.id) or practice(a)
        return book


class LedgerCase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.clock = Clock()
        self.ledger = Ledger(Path(self.dir.name) / "l.sqlite", clock=self.clock)

    def tearDown(self):
        self.ledger.close()
        self.dir.cleanup()

    def throttle(self, lane, on=True):
        return self.ledger.append("ops.budget", {"what": THROTTLE_WHAT, "lane": lane, "throttled": on, "ratio": 7.5})


class ThePlan(unittest.TestCase):
    def test_the_t0_day_halves_research_the_engineer_the_consultant_and_the_architect(self):
        plan = plan_throttle(lane_prices([T0_ROW], T0_LIFT), 3)
        self.assertEqual(plan["best"], {"lane": "lab", "usd_per_positive_block": "0.0391"})
        lanes = plan["lanes"]
        self.assertEqual(sorted(lane for lane, row in lanes.items() if row["throttled"]), ["architect", "consultant", "engineer", "research"])
        self.assertEqual((lanes["research"]["ratio"], lanes["engineer"]["ratio"], lanes["consultant"]["ratio"]), (7.38, 4.61, 12.93))
        self.assertEqual(lanes["architect"]["why"], "bought no positive forward block")
        self.assertIn("under $1.00", lanes["toolsmith"]["why"], "halving $0.47 saves nothing")
        self.assertIn("not_started", lanes["teacher"]["why"], "the teacher is judged by its lift, and it is not measured yet")
        self.assertNotIn("audits", lanes, "audits are never throttled")
        self.assertNotIn("lab", lanes, "the lab's dials are league/lab.py's: priced, never halved here")

    def test_the_best_lane_needs_ten_positive_blocks_and_none_is_throttled_without_one(self):
        row = {"spend_usd": {"research": "10", "foundry": "0.01", "architect": "5"},
               "evidence": {"research": {"positive_blocks": 20}, "foundry": {"positive_blocks": 3}}}
        plan = plan_throttle(lane_prices([row]), 3)
        self.assertEqual(plan["best"]["lane"], "research", "three blocks for a cent is luck, not a price")
        self.assertTrue(plan["lanes"]["architect"]["throttled"])
        self.assertFalse(plan["lanes"]["research"]["throttled"])
        empty = plan_throttle(lane_prices([{"spend_usd": {"architect": "5"}, "evidence": {}}]), 3)
        self.assertIsNone(empty["best"])
        self.assertFalse(empty["lanes"]["architect"]["throttled"])

    def test_the_consultant_is_priced_on_f4_and_never_throttled_before_it_is_measured(self):
        prices = lane_prices([T0_ROW], {"consultant": {"judged_blocks": 0}})
        self.assertIn("unmeasured", prices["consultant"])
        self.assertFalse(plan_throttle(prices, 3)["lanes"]["consultant"]["throttled"])
        cheap = {"consultant": {"judged_blocks": 12, "usd": "3.00", "positive_blocks_after": 30, "usd_per_positive_block": "0.1000"}}
        self.assertFalse(plan_throttle(lane_prices([T0_ROW], cheap), 3)["lanes"]["consultant"]["throttled"], "2.6x is under 3x")
        self.assertTrue(plan_throttle(lane_prices([T0_ROW], cheap), 2)["lanes"]["consultant"]["throttled"], "and over 2x")


class TheHourlyRow(LedgerCase):
    def house(self, **economy):
        lab = SimpleNamespace(_q=lambda sql, params: [{"usd": self.lab_usd}])
        return SimpleNamespace(ledger=self.ledger, clock=self.clock, _state={}, _state_lock=threading.RLock(), lab=lab,
                               game={"economy": {"lane_throttle": 3, **economy}, "merton": {}}, jev_floor=None,
                               alert=lambda level, text: self.alerts.append(text))

    def blocks(self, agent, n, growth=0.01):
        for _ in range(n):
            self.clock.advance(1)
            self.ledger.append("eval.block", {"active": True, "log_growth": growth, "book": "alpaca-paper"}, agent=agent)

    def test_a_throttle_row_is_written_when_a_lane_crosses_the_line_and_again_when_it_comes_back(self):
        self.alerts, self.lab_usd = [], "0.12"
        self.ledger.append("agent.born", {"founder": "lab:l1", "reason": "graduate"}, agent="lab-born")
        self.clock.advance(3600)
        self.blocks("lab-born", 12)  # the lab: $0.01 a positive block
        self.blocks("research-born", 10)
        self.ledger.append("credit.charge", {"what": "research tokens", "usd": "5.00", "detail": {"session": "s1"}}, agent="research-born")
        self.ledger.append("merton.pass", {"role": "architect", "cost_usd": "2.00", "files": 0, "at_epoch": self.clock()})
        house = self.house()
        self.clock.advance(60)
        YieldLedger(house).tick()
        self.assertEqual(self.alerts, [])
        row = [e.payload for e in self.ledger.iter(kinds="ops.budget") if e.payload.get("what") == "yield"][-1]
        self.assertEqual(row["spend_usd"]["lab"], "0.1200", "the lab's own calls price its blocks")
        self.assertEqual(row["throttle"]["best"], {"lane": "lab", "usd_per_positive_block": "0.0100"})
        changes = [e.payload for e in self.ledger.iter(kinds="ops.budget") if e.payload.get("what") == THROTTLE_WHAT]
        self.assertEqual(sorted((c["lane"], c["throttled"]) for c in changes), [("architect", True), ("research", True)])
        research = next(c for c in changes if c["lane"] == "research")
        self.assertEqual((research["ratio"], research["usd_per_positive_block"]), (50.0, "0.5000"))
        self.assertIn("never past one session a day", research["how"])
        self.assertNotIn("cost_usd", research, "a throttle row is not a frontier probe's cost (scripts/economics.py)")
        self.assertTrue(throttled(self.ledger, "research"))
        self.assertFalse(throttled(self.ledger, "engineer"))
        self.clock.advance(3600)
        YieldLedger(house).tick()
        self.assertEqual(len([e for e in self.ledger.iter(kinds="ops.budget") if e.payload.get("what") == THROTTLE_WHAT]), 2,
                         "a lane still over the line writes nothing new")
        self.clock.advance(1800)
        self.blocks("research-born", 1000)
        self.clock.advance(1800)
        YieldLedger(house).tick()
        self.assertFalse(throttled(self.ledger, "research"), "$5.00 for 1,010 blocks is under 3x the lab's price")
        last = [e.payload for e in self.ledger.iter(kinds="ops.budget") if e.payload.get("what") == THROTTLE_WHAT][-1]
        self.assertEqual((last["lane"], last["throttled"]), ("research", False))

    def test_without_the_dial_nothing_is_throttled(self):
        self.alerts, self.lab_usd = [], "0"
        house = self.house()
        house.game["economy"].pop("lane_throttle")
        self.ledger.append("merton.pass", {"role": "architect", "cost_usd": "9.00", "files": 0, "at_epoch": self.clock()})
        self.clock.advance(3600)
        YieldLedger(house).tick()
        self.assertEqual(throttle_state(self.ledger), {})
        row = [e.payload for e in self.ledger.iter(kinds="ops.budget") if e.payload.get("what") == "yield"][-1]
        self.assertNotIn("throttle", row)


    def test_removing_the_dial_puts_every_halved_lane_back(self):
        """The review of Deploy C (Sept 25, 2026): `economy.lane_throttle` removed is the documented off switch, but with no
        plan made nothing wrote the rows that lift a throttle, and `throttled()` reads each lane's newest row: every lane
        halved stayed halved."""
        self.alerts, self.lab_usd = [], "0"
        self.throttle("research")
        self.throttle("engineer")
        self.throttle("toolsmith", on=False)
        house = self.house()
        house.game["economy"].pop("lane_throttle")
        self.clock.advance(3600)
        YieldLedger(house).tick()
        self.assertFalse(throttled(self.ledger, "research"))
        self.assertFalse(throttled(self.ledger, "engineer"))
        lifted = [e.payload for e in self.ledger.iter(kinds="ops.budget") if e.payload.get("what") == THROTTLE_WHAT][3:]
        self.assertEqual([(r["lane"], r["throttled"], r["why"]) for r in lifted],
                         [("engineer", False, "economy.lane_throttle is off"), ("research", False, "economy.lane_throttle is off")])
        self.clock.advance(3600)
        YieldLedger(house).tick()
        self.assertEqual(len([e for e in self.ledger.iter(kinds="ops.budget") if e.payload.get("what") == THROTTLE_WHAT]), 5,
                         "a lane already back writes nothing more")

    def test_the_day_is_the_day_s_yield_rows_however_many_budget_rows_came_between(self):
        """The review of Deploy C (Sept 25, 2026): the day was the newest 200 `ops.budget` rows, 18.1 hours at T0 (246 a
        day, most of them Sail meter readings and absorbed holds)."""
        self.alerts, self.lab_usd = [], "0"
        self.ledger.append("ops.budget", {"what": "yield", "spend_usd": {"architect": "5.00", "research": "0.10"},
                                          "evidence": {"research": {"positive_blocks": 20}}})
        for _ in range(250):
            self.clock.advance(60)
            self.ledger.append("ops.budget", {"what": "holds absorbed", "usd": "0.01"})
        house = self.house()
        self.clock.advance(3600)
        YieldLedger(house).tick()
        self.assertEqual(self.alerts, [])
        self.assertTrue(throttled(self.ledger, "architect"), "$5.00 five hours ago, for no positive block, is in the day")

class UnitEconomicsOnTheRow(LedgerCase):
    def test_compute_and_profit_a_day_are_counted_as_the_scoreboard_counts_them(self):
        """T0 by this fold: $118.88 of compute and $21.35 of profit a day, to the cent the scoreboard's."""
        self.ledger.append("provider.request", {"cost_usd": "0.004", "cost_verified": True})
        self.ledger.append("provider.request", {"held_usd": "0.05", "cost_verified": False})  # a hold, not a bill
        self.ledger.append("merton.pass", {"role": "engineer", "cost_usd": "0.20"})
        self.ledger.append("audit.verdict", {"cost_usd": "0.30", "approve": True}, agent="a")
        self.ledger.append("agent.research", {"tool": "research_grant", "status": "completed", "cost_usd": "0.10"}, agent="a")
        self.ledger.append("credit.charge", {"what": "research tokens", "usd": "0.40", "detail": {"session": "s"}}, agent="a")
        self.ledger.append("ops.budget", {"what": "sail", "spent_usd": "0.70"})
        self.ledger.append("credit.charge", {"what": "jev classification", "usd": "0.01"}, agent="a")
        self.ledger.append("book.settle", {"book": "kalshi", "pnl": "2.50"}, agent="a")
        self.ledger.append("book.settle", {"book": "kalshi-shadow", "pnl": "9.00"}, agent="a")  # practice: never profit
        self.ledger.append("book.fill", {"book": "alpaca", "realized": "-0.50"}, agent="a")
        unit = UnitEconomics(self.ledger, self.clock, lab_usd=lambda start, end: D("0.05")).reading()
        self.assertEqual(unit["providers_usd"], {"jev": 0.01, "openai-astra": 0.6, "openai-lab": 0.05, "openai-luna": 0.004, "sail": 0.7},
                         "the Sail meter, not the research tokens it already counts")
        self.assertEqual((unit["compute_per_day_usd"], unit["profit_per_day_usd"], unit["real_closes"]), (1.36, 2.0, 2))
        self.assertEqual(unit["compute_over_profit"], 0.68)

    def test_rows_older_than_a_day_leave_the_line(self):
        self.ledger.append("merton.pass", {"role": "engineer", "cost_usd": "1.00"})
        unit = UnitEconomics(self.ledger, self.clock)
        self.assertEqual(unit.reading()["compute_per_day_usd"], 1.0)
        self.clock.advance(86400 + 60)
        self.ledger.append("merton.pass", {"role": "engineer", "cost_usd": "0.25"})
        self.assertEqual(unit.reading()["compute_per_day_usd"], 0.25)
        self.assertEqual(UnitEconomics(self.ledger, self.clock).reading()["compute_per_day_usd"], 0.25, "a fresh fold agrees")


class UnitEconomicsInHealth(F2Case):
    def test_health_json_carries_the_keys_the_site_reads(self):
        self.f2()
        self.house.ledger.append("merton.pass", {"role": "engineer", "cost_usd": "2.40"})
        self.house.ledger.append("book.settle", {"book": "kalshi", "pnl": "1.20"}, agent="x")
        self.clock.advance(3600)
        self.house.hypotheses = None
        YieldLedger(self.house).tick()
        self.house._health({"at": now_iso(self.clock)})
        health = json.loads((self.house.root / "health.json").read_text())
        self.assertEqual((health["unit_economics"]["compute_per_day_usd"], health["unit_economics"]["profit_per_day_usd"]), (2.4, 1.2))


class ResearchThrottle(F2Case):
    """Rule 14: a throttled research lane doubles a practice agent's interval, never past a day."""

    def setUp(self):
        super().setUp()
        self.agent = self.f2()
        self.clock.advance(self.interval)
        self.assertFalse(self.house.research_due(self.agent), "first sight: nothing new")
        self.house._state["last_research"][self.agent.id] = self.clock()

    def block(self, agent):
        self.house.ledger.append("eval.block", {"agent": agent.id, "log_growth": 0.01, "active": True, "book": "alpaca-paper", "block": "b"},
                                 agent=agent.id)

    def test_a_practice_agent_waits_twice_its_interval_and_its_trigger_waits_with_it(self):
        self.house.ledger.append("ops.budget", {"what": THROTTLE_WHAT, "lane": "research", "throttled": True})
        self.block(self.agent)
        self.clock.advance(self.interval)
        rows = len(self.gates())
        self.assertFalse(self.house.research_due(self.agent), "the block is news, but the lane is halved")
        for _ in range(5):
            self.clock.advance(60)
            self.assertFalse(self.house.research_due(self.agent))
        held = self.gates()[rows:]
        self.assertEqual([(r["decision"], r["reason"]) for r in held], [("skip", "lane_throttle:research")], "one row a held slot")
        self.clock.advance(self.interval)
        self.assertTrue(self.house.research_due(self.agent), "twice the interval: the block it waited on runs it")
        self.assertEqual(self.gates()[-1]["trigger"], "eval.block")

    def test_never_past_a_day_and_never_an_agent_on_real_money(self):
        self.house.ledger.append("ops.budget", {"what": THROTTLE_WHAT, "lane": "research", "throttled": True})
        self.house.research_interval_hours = lambda agent=None: 18.0
        self.block(self.agent)
        self.clock.advance(18 * 3600)
        self.assertFalse(self.house.research_due(self.agent))
        self.clock.advance(6 * 3600)
        self.assertTrue(self.house.research_due(self.agent), "36 hours would be past one session a day")
        real = self.seated("real")
        self.house._state["last_research"][real.id] = self.clock()
        self.on_real_money(real)
        self.clock.advance(18 * 3600)
        self.assertTrue(self.house.research_due(real), "real money keeps its pace")
        self.assertEqual(self.gates(real.id)[-1]["reason"], "clock")

    def test_unthrottled_it_runs_on_its_interval(self):
        self.house.ledger.append("ops.budget", {"what": THROTTLE_WHAT, "lane": "research", "throttled": True})
        self.house.ledger.append("ops.budget", {"what": THROTTLE_WHAT, "lane": "research", "throttled": False})
        self.block(self.agent)
        self.clock.advance(self.interval)
        self.assertTrue(self.house.research_due(self.agent))


class PracticeTriggerSkip(F2Case):
    """Rule 13 (J2): a practice agent's own fills and settlements do not wake it; anything else does."""

    def fill(self, agent, book="alpaca-paper"):
        return self.house.ledger.append("book.fill", {"book": book, "source": "venue"}, agent=agent.id)

    def seen(self, agent):
        """The gate's first sight of `agent` (its baseline), a slot before the evidence under test."""
        self.clock.advance(self.interval)
        self.assertFalse(self.house.research_due(agent), "first sight: nothing new")
        self.house._state["last_research"][agent.id] = self.clock()
        return agent

    def test_a_practice_fill_or_settlement_does_not_wake_it_and_is_not_read_again(self):
        agent = self.seen(self.f2(practice_skip_triggers=["book.fill", "book.settle"]))
        self.fill(agent)
        self.house.ledger.append("book.settle", {"book": "alpaca-paper", "pnl": "0.40"}, agent=agent.id)
        self.clock.advance(self.interval)
        self.assertFalse(self.house.research_due(agent), "J2: $0.62 and $0.44 a replay pass on Sept 22-23")
        row = self.gates()[-1]
        self.assertEqual((row["decision"], row["reason"]), ("skip", "trigger_skip:book.settle"))
        self.house.ledger.append("eval.block", {"agent": agent.id, "log_growth": 0.01, "active": True, "book": "alpaca-paper", "block": "b"},
                                 agent=agent.id)
        self.clock.advance(self.interval)
        self.assertTrue(self.house.research_due(agent), "the forward block that sums its fills still wakes it")
        self.assertEqual(self.gates()[-1]["triggers"], ["eval.block:1"], "the fill was seen and passed, not carried")

    def test_anything_else_found_still_runs_it_and_real_money_keeps_every_trigger(self):
        agent = self.seen(self.f2(practice_skip_triggers=["book.fill", "book.settle"]))
        self.fill(agent)
        self.house.ledger.append("library.note", {"niche": agent.niche, "title": "a desk note", "text": "spreads widen at 14:00"},
                                 agent="a-desk-mate")
        self.clock.advance(self.interval)
        self.assertTrue(self.house.research_due(agent))
        self.assertEqual(self.gates()[-1]["triggers"], ["library.note:niche:1"])
        real = self.seated("real")
        self.on_real_money(real, holding=False)
        self.seen(real)
        self.fill(real, book="alpaca")
        self.clock.advance(self.interval)
        self.assertTrue(self.house.research_due(real), "a real fill is what real research is for")
        self.assertEqual(self.gates(real.id)[-1]["trigger"], "book.fill")

    def test_a_paused_agent_s_fill_does_not_spend_its_trade_of_the_day(self):
        """The review of #311 wakes a paused practice agent on its own trading once a UTC day; rule 13 takes
        its fills out first, so what remains of that is its active forward block (the merge into
        c/integration, Sept 25, 2026)."""
        agent = self.seen(self.f2(practice_skip_triggers=["book.fill", "book.settle"]))
        for _ in range(3):
            summary(self.house.ledger, agent.id)
        self.fill(agent)
        self.clock.advance(self.interval)
        self.assertFalse(self.house.research_due(agent), "paused, and its fill is not news")
        self.assertEqual(self.gates()[-1]["reason"], "practice_pause:3")
        self.assertIsNone(self.house.jev_floor.gate.state.agent(agent.id).get("pause_trade_day"), "the fill spent nothing")
        self.house.ledger.append("eval.block", {"agent": agent.id, "log_growth": -0.01, "active": True, "book": "alpaca-paper", "block": "b"},
                                 agent=agent.id)
        self.clock.advance(self.interval)
        self.assertTrue(self.house.research_due(agent), "its active block is its trade of the day")
        self.assertEqual(self.gates()[-1]["triggers"], ["eval.block:1"])

    def test_the_dial_empty_is_f2(self):
        agent = self.seen(self.f2(practice_skip_triggers=[]))
        self.fill(agent)
        self.clock.advance(self.interval)
        self.assertTrue(self.house.research_due(agent))
        self.assertEqual(self.gates()[-1]["trigger"], "book.fill")


class JevRelevanceSwitch(GateCase):
    """Rule 4's switch (Sept 25, 2026): Jev's relevance answer woke 169 sessions at o2 4.7%, the random
    sample's rate (4.5%) and a fifth of the free triggers'; game.json turns it off."""

    def note(self):
        self.house.ledger.append("library.note", {"title": "Spread lesson", "text": "x" * 80, "niche": "alpaca-crypto-alts"}, agent="peer")

    def test_off_a_note_jev_rates_relevant_wakes_nothing_and_jev_is_not_asked(self):
        agent = self.ready(p=0.9)
        self.assertIs(self.house.game["research"]["gate"]["jev_relevance"], False, "game.json turns it off")
        summary(self.house.ledger, agent.id)
        summary(self.house.ledger, agent.id)
        self.researched(agent)
        self.note()
        self.clock.advance(self.interval)
        self.assertFalse(self.house.research_due(agent))
        self.assertEqual(self.gates()[-1]["decision"], "skip")
        self.assertNotIn("jev_unavailable", self.gates()[-1]["reason"])
        self.assertEqual(self.jev.calls, [], "nothing was asked")

    def test_on_it_wakes_the_session_as_before(self):
        agent = self.ready(p=0.9, settings={"jev_relevance": True})
        summary(self.house.ledger, agent.id)
        summary(self.house.ledger, agent.id)
        self.researched(agent)
        self.note()
        self.clock.advance(self.interval)
        self.assertTrue(self.house.research_due(agent))
        self.assertEqual(self.gates()[-1]["reason"], "jev_relevant_note")


class MertonLanes(LedgerCase):
    def merton(self):
        return Merton(SimpleNamespace(), None, self.ledger, evidence=lambda role: {}, clock=self.clock,
                      schedule_hours={"architect": 3, "toolsmith": 3, "operator": 3, "designer": 3, "teacher": 3},
                      first_after_hours={}, paused_until_profit=[])

    def test_a_throttled_role_sits_down_half_as_often(self):
        merton = self.merton()
        for role in ("architect", "teacher"):
            self.ledger.append("merton.pass", {"role": role, "at_epoch": self.clock(), "cost_usd": "1", "files": 1})
        self.throttle("architect")
        self.clock.advance(3 * 3600)
        self.assertNotIn("architect", merton.due())
        self.assertIn("teacher", merton.due())
        self.clock.advance(3 * 3600)
        self.assertIn("architect", merton.due())

    def test_a_throttled_consultant_costs_twice_as_much(self):
        merton = self.merton()
        self.assertEqual(merton.consult_price_multiple("haghani-63"), (1, 0))
        self.throttle("consultant")
        self.assertEqual(merton.consult_price_multiple("haghani-63"), (2, 0))


class EngineerLane(LedgerCase):
    def engineer(self, answers):
        frontier = SimpleNamespace(model="gpt-6-astra", asked=[])

        def ask(**kw):
            frontier.asked.append(kw)
            return Answer(json.dumps(answers.pop(0)), D("0.10"), {}, "gpt-6-astra")

        frontier.ask = ask
        self.worklist = Worklist(self.ledger, clock=self.clock)
        return frontier, Engineer(frontier, None, self.ledger, self.worklist, clock=self.clock,
                                  settings={"min_seconds_between_calls": 900, "max_job_usd": "5.00"},
                                  code_of=lambda a: {"needs": {"venue": "kalshi", "feeds": ["weather"]}, "niche": "kalshi-weather", "code": "x"})

    def report(self, key, kind="bug_report", agents=("a",)):
        self.worklist.report(key=key, kind=kind, summary="s", agents=list(agents), source="triage", severity="high",
                             evidence=[{"seq": 1, "at": "2026-09-25T00:00:00.000Z", "agent": agents[0], "excerpt": "x"}])
        self.worklist.admit(threshold=0)

    def nothing(self):
        return {"summary": "no change", "role": "teacher", "files": [], "needs_core": None}

    def test_a_throttled_engineer_waits_twice_as_long_except_for_real_money(self):
        frontier, engineer = self.engineer([self.nothing(), self.nothing(), self.nothing()])
        self.ledger.append("merton.pass", {"role": "engineer", "at_epoch": self.clock(), "cost_usd": "0.10"})
        self.throttle("engineer")
        self.report("bug_report:alpaca-megacaps:1")
        self.clock.advance(900)
        engineer.step()
        self.assertEqual(frontier.asked, [], "a practice job waits two intervals while the lane is halved")
        self.report("order_refusal:kalshi:one event may hold at most #% of the stake", kind="order_refusal", agents=("b",))
        engineer.step()
        self.assertEqual(len(frontier.asked), 1, "a refusal on the real Kalshi book is never throttled")
        self.clock.advance(1800)
        engineer.step()
        self.assertEqual(len(frontier.asked), 2)

    def test_an_agent_whose_last_wake_was_on_a_real_book_is_real_money(self):
        _, engineer = self.engineer([])
        self.report("strategy_defect:c:abc", kind="strategy_defect", agents=("c",))
        job = self.worklist.get("strategy_defect:c:abc")
        self.assertFalse(engineer._real_money(job))
        self.ledger.append("agent.woke", {"ok": True, "book": "kalshi"}, agent="c")
        self.assertTrue(engineer._real_money(job))

    def test_its_hold_is_priced_on_the_sections_it_is_sent(self):
        frontier, engineer = self.engineer([self.nothing()])
        self.report("bug_report:kalshi-weather:1")
        engineer.step()
        system = frontier.asked[0]["system"]
        whole = CONTRACT.read_text(encoding="utf-8")
        self.assertIn("THE STRATEGY CONTRACT", system)
        self.assertIn("## The file", system)
        self.assertIn("Feeds: scoreboards", system, "its agents' NEEDS name feeds: the feeds sections come whole")
        self.assertNotIn("## Your seat", system, "the seat is the researcher's, not a repair's")
        self.assertLess(len(system.encode()), len(whole.encode()) - 10_000)
        worst_now = hold_usd("gpt-6-astra", len(system.encode()), 16000)
        worst_whole = hold_usd("gpt-6-astra", len(whole.encode()), 16000)
        self.assertGreater(worst_whole - worst_now, D("0.25"))


    def test_sections_an_attempt_asked_for_are_sent_whole_to_the_next(self):
        """The review of Deploy C (Sept 25, 2026): an attempt that asked for contract sections and had no room under the
        per-job ceiling to ask again wrote them on its `repair.status` row (`_contract_sections`), but the worklist's fold
        never carried them, so the next attempt was sent the index again and asked again."""
        frontier, engineer = self.engineer([self.nothing()])
        self.report("bug_report:kalshi-weather:1")
        job = self.worklist.get("bug_report:kalshi-weather:1")
        engineer._after_failure(job, 1, D("0.10"), "patch 1 asked for contract sections the-alpha-lab; no room", _contract_sections=["the-alpha-lab"])
        job = self.worklist.get("bug_report:kalshi-weather:1")
        self.assertEqual(job.carry.get("_contract_sections"), ["the-alpha-lab"])
        self.clock.advance(3600)
        engineer.step()
        self.assertEqual(len(frontier.asked), 1)
        self.assertIn("## The Alpha Lab", frontier.asked[0]["system"], "the section it asked for comes whole")

class ContractBySection(unittest.TestCase):
    TEXT = ("# The contract\n\nIntro.\n\n## The file\n\n```python\n# not a heading\nNEEDS = {}\n```\n\n## What decide is given\n\nctx.\n\n"
            "### Options: the chain\n\nchain.\n\n#### Greeks\n\ngreeks.\n\n### Feeds: weather\n\nfeeds.\n\n## The open desks\n\nopen.\n\n"
            "## Your seat\n\nseat.\n\n## What decide returns\n\nreturns.\n")

    def test_sections_follow_the_headings_and_inherit_their_parents_topic(self):
        sections = contract_sections(self.TEXT)
        self.assertEqual([(s.id, s.topic) for s in sections], [
            ("the-contract", "core"), ("the-file", "core"), ("what-decide-is-given", "core"), ("options-the-chain", "options"),
            ("greeks", "options"), ("feeds-weather", "feeds"), ("the-open-desks", "open"), ("your-seat", "agent"),
            ("what-decide-returns", "core")])
        self.assertIn("# not a heading", sections[1].text, "a comment inside a code fence is not a heading")

    def test_a_job_is_sent_core_first_its_topics_after_and_the_rest_by_id(self):
        body, sent = contract_for(self.TEXT, {"feeds"})
        self.assertEqual(sent["sections"], ["the-contract", "the-file", "what-decide-is-given", "what-decide-returns", "feeds-weather"])
        self.assertLess(body.index("returns."), body.index("feeds."), "core first: calls of one role share a cached prefix")
        self.assertIn("- options-the-chain: Options: the chain", body)
        self.assertNotIn("chain.\n", body)
        everything, sent = contract_for(self.TEXT, (), extra=["all"])
        self.assertEqual(sent["left"], [])

    def test_the_topics_of_a_strategy(self):
        self.assertEqual(contract_topics({"asset_class": "option"}, "alpaca-options"), {"options"})
        self.assertEqual(contract_topics({"feeds": ["weather"]}, "kalshi-open"), {"feeds", "open"})
        self.assertEqual(contract_topics({"venue": "kalshi"}, "kalshi-sports"), set())

    def test_an_answer_that_asks_is_asked_again_once_with_the_sections(self):
        calls = []

        def ask(**kw):
            calls.append(kw)
            text = json.dumps({"contract_sections": ["options-the-chain"]}) if len(calls) == 1 else json.dumps({"answer": "a file", "code": "x"})
            return Answer(text, D("0.30"), {}, "gpt-6-astra")

        reply, sent = ask_with_contract(SimpleNamespace(ask=ask), head="HEAD", contract=self.TEXT, topics=(), user="{}", agent="a",
                                        max_output_tokens=100, effort="medium")
        self.assertEqual(len(calls), 2)
        self.assertIn("chain.", calls[1]["system"])
        self.assertNotIn("contract_sections", calls[1]["system"], "asked once: the second call cannot ask again")
        self.assertEqual((reply.cost_usd, sent["asked"]), (D("0.60"), ["options-the-chain"]))
        self.assertEqual(asked_sections(json.dumps({"contract_sections": ["x"], "files": [{"path": "p"}]})), [], "an answer with files is an answer")

    def test_a_failed_second_call_keeps_the_first_calls_cost(self):
        calls = []

        def ask(**kw):
            calls.append(kw)
            if len(calls) == 2:
                raise FrontierError("frontier call failed: TimeoutError")
            return Answer(json.dumps({"contract_sections": ["greeks"]}), D("0.30"), {}, "gpt-6-astra")

        with self.assertRaises(FrontierError) as caught:
            ask_with_contract(SimpleNamespace(ask=ask), head="H", contract=self.TEXT, topics=(), user="{}", agent="a",
                              max_output_tokens=100, effort="medium")
        self.assertEqual(caught.exception.spent_usd, D("0.30"))

    def test_the_real_contract_s_core_is_under_six_tenths_of_it(self):
        whole = CONTRACT.read_text(encoding="utf-8")
        body, sent = contract_for(whole, ())
        self.assertLess(sent["bytes"], 0.6 * sent["full_bytes"])
        self.assertTrue({"the-alpha-lab", "your-seat"} <= set(sent["left"]))
        self.assertIn("## How replay scores it", body)


if __name__ == "__main__":
    unittest.main()
