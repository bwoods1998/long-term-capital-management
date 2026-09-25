"""Every lane is measured (F4, Sept 25, 2026, the forward-first run).

In the 24 hours to T0 the consultant cost $28.72 for 51 answers and nothing said whether one made an
agent trade better; the teacher's "137 lessons" were 111 post-mortems and 6 lessons; the engineer had
verified 22 repairs for $26.59 in its life. These tests pin the `consult.outcome` rows, the doubling
of an unproductive consult's price, the consultant's pause, and the `lift` section of the hourly
yield row (league/yield_ledger.py), plus `scripts/gate_replay.py`'s arithmetic on a small ledger.
"""

from __future__ import annotations

import copy
import sys
import tempfile
import threading
import unittest
from decimal import Decimal as D
from pathlib import Path
from types import SimpleNamespace

from league.economy import check_bounds, load_game
from league.ledger import Ledger, now_iso
from league.merton import Merton, consult_verdict, consult_verdicts
from league.research_gate import lesson_arm
from league.tests.fakes import Clock
from league.tests.test_merton import FakeForge, FakeFrontier
from league.tests.test_researcher import ResearchCase
from league.yield_ledger import YieldLedger, engineer_lift, fold, teacher_lift

ROOT = Path(__file__).resolve().parents[2]


class LedgerCase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.clock = Clock()
        self.ledger = Ledger(Path(self.dir.name) / "l.sqlite", clock=self.clock)

    def tearDown(self):
        self.ledger.close()
        self.dir.cleanup()

    def consult(self, agent="haghani-63", cost="0.56", wrote_code=True):
        self.clock.advance(60)
        return self.ledger.append("merton.pass", {"role": "consultant", "agent": agent, "at_epoch": self.clock(), "cost_usd": cost,
                                                  "wrote_code": wrote_code, "answer": "a file", "confidence": "medium"})

    def session(self, agent="haghani-63", *, candidate=False, reason="finished"):
        self.clock.advance(600)
        return self.ledger.append("agent.research", {"tool": "summary", "session": f"s-{self.ledger.head()[0]}", "candidate": candidate,
                                                     "trials": int(candidate), "reason": reason, "cost_usd": "0.02"}, agent=agent)

    def block(self, agent, growth, *, active=True, step=3600):
        self.clock.advance(step)
        return self.ledger.append("eval.block", {"active": active, "log_growth": growth, "book": "alpaca-paper"}, agent=agent)

    def merton(self, **kw):
        return Merton(FakeFrontier({"files": []}), FakeForge(), self.ledger, evidence=lambda role: {}, clock=self.clock, **kw)


class ConsultVerdicts(LedgerCase):
    def test_a_consult_is_judged_on_what_the_agent_did_within_two_sessions(self):
        c1 = self.consult()
        self.assertIsNone(consult_verdicts(self.ledger, "haghani-63")[0][1], "no session has finished: not judged")
        self.session()
        self.assertIsNone(consult_verdicts(self.ledger, "haghani-63")[0][1], "one session is not two")
        self.session(reason="provider: provider_http_502")  # the vendor broke it: not a pass
        self.assertIsNone(consult_verdicts(self.ledger, "haghani-63")[0][1])
        self.session()
        self.assertEqual(consult_verdicts(self.ledger, "haghani-63")[0][1], {"productive": False, "by": None, "sessions": 2})
        c2 = self.consult()
        self.session(candidate=True)
        self.assertEqual(consult_verdicts(self.ledger, "haghani-63")[1][1]["by"], "candidate")
        c3 = self.consult()
        self.ledger.append("agent.strategy", {"control": "pause_entries", "code_sha256": "x"}, agent="haghani-63")
        self.session()
        self.ledger.append("agent.strategy", {"control": "edit_params", "code_sha256": "x"}, agent="haghani-63")
        verdicts = dict((c.seq, v) for c, v in consult_verdicts(self.ledger, "haghani-63"))
        self.assertEqual(verdicts[c3.seq]["by"], "edit", "a pause restates a strategy; an edit changes one")
        self.assertEqual(verdicts[c1.seq]["productive"], False)
        self.assertEqual(verdicts[c2.seq]["productive"], True)
        self.assertIsNone(consult_verdict(c1, [], sessions=2))

    def test_each_unproductive_consult_in_a_row_doubles_the_next_price_and_a_productive_one_resets_it(self):
        merton = self.merton(lift={"consult_max_multiple": 4})
        self.assertEqual(merton.consult_price_multiple("haghani-63"), (1, 0))
        for n in (1, 2, 3):
            self.consult()
            self.session()
            self.session()
            self.assertEqual(merton.consult_price_multiple("haghani-63"), (min(2 ** n, 4), n))
        self.consult()
        self.assertEqual(merton.consult_price_multiple("haghani-63"), (4, 3), "a consult not yet judged moves nothing")
        self.session(candidate=True)
        self.assertEqual(merton.consult_price_multiple("haghani-63"), (1, 0))
        self.consult(agent="someone-else")
        self.session(agent="someone-else")
        self.session(agent="someone-else")
        self.assertEqual(merton.consult_price_multiple("haghani-63"), (1, 0), "another agent's consults are its own")

    def test_the_consultant_can_be_paused_until_profit(self):
        self.ledger.append("ops.started", {"release": "test"})
        self.ledger.append("book.settle", {"book": "kalshi", "pnl": "-1.00", "real_money": True}, agent="x")
        self.assertTrue(self.merton(paused_until_profit=["consultant"]).consult_paused())
        self.assertFalse(self.merton(paused_until_profit=["teacher"]).consult_paused())
        rows = [e.payload for e in self.ledger.iter(kinds="ops.budget") if e.payload.get("what") == "merton pause"]
        self.assertEqual({r["role"] for r in rows}, {"consultant"})
        self.clock.advance(600)
        self.ledger.append("book.settle", {"book": "kalshi", "pnl": "3.00", "real_money": True}, agent="x")
        self.assertFalse(self.merton(paused_until_profit=["consultant"]).consult_paused())


class ThePriceAnAgentPays(ResearchCase):
    class Merton:
        def __init__(self, multiple=(1, 0), paused=False):
            self.multiple, self.paused, self.seen = multiple, paused, []

        def consult_paused(self):
            return self.paused

        def consult_price_multiple(self, agent_id):
            return self.multiple

        def consult(self, agent, question, evidence, *, contract, **settings):
            self.seen.append(agent.id)
            return {"answer": "Rewrite the entry.", "code": "", "confidence": "medium", "cost_usd": "0.40"}

    def hire(self, merton, credits_min="1.00"):
        r = self.researcher([[("ask_merton", {"question": "Is my idea structurally dead, or is it the parameters?"})]],
                            merton=merton, merton_settings={"min_credits_usd": credits_min, "cooldown_hours": 0},
                            house_budget=lambda: True, standing=lambda _: {"active_blocks": 4, "mean_growth": 0.001})
        before = self.economy.balance(self.parent.id)
        r.research(self.parent, {}, session="s1")
        return before

    def test_an_agent_whose_consults_went_nowhere_pays_double(self):
        before = self.hire(self.Merton(multiple=(2, 1)))
        charged = [D(e.payload["usd"]) for e in self.ledger.iter(kinds="credit.charge", agent=self.parent.id) if e.payload["what"] == "merton's time"]
        self.assertEqual(charged, [D("0.80")])
        row = [e.payload for e in self.ledger.iter(kinds="agent.research", agent=self.parent.id) if e.payload.get("tool") == "merton"][-1]
        self.assertEqual((row["cost_usd"], row["price_multiple"], row["charged_usd"]), ("0.40", 2, "0.80"), "the House's cost stays the cost")
        self.assertLess(self.economy.balance(self.parent.id), before - D("0.79"))

    def test_the_doubled_minimum_and_the_pause_refuse_before_anything_is_spent(self):
        merton = self.Merton(multiple=(8, 3))
        self.hire(merton, credits_min="1.00")  # it holds $5: $8 is out of reach
        self.assertEqual(merton.seen, [])
        self.assertIn("8x", self.tool_output(1)["error"])
        paused = self.Merton(paused=True)
        self.hire(paused)
        self.assertEqual(paused.seen, [])
        self.assertIn("paused", self.tool_output(1)["error"])


class Lift(LedgerCase):
    def born(self, agent, specialty="alpaca-crypto-alts", family="crypto-alts-reversion"):
        self.ledger.append("agent.born", {"specialty": specialty, "family": family, "founder": None, "reason": "test"}, agent=agent)

    def two_arms(self):
        lesson = [f"agent-{n}" for n in range(60) if lesson_arm(f"agent-{n}") == "lesson"][:3]
        control = [f"agent-{n}" for n in range(60) if lesson_arm(f"agent-{n}") == "control"][:3]
        return lesson, control

    def test_post_mortems_are_not_the_teachers_lessons(self):
        since = now_iso(self.clock)
        self.ledger.append("playbook.entry", {"title": "Post-mortem: x", "text": "died", "source": "graveyard"})
        self.ledger.append("playbook.entry", {"title": "Lesson: y", "text": "do z", "source": "teacher"})
        self.assertEqual(fold(self.ledger, since=since)["evidence"]["teacher"], {"lessons": 1})

    def test_the_teacher_is_measured_against_the_arm_its_lessons_did_not_wake(self):
        lesson, control = self.two_arms()
        for agent in lesson + control:
            self.born(agent)
        self.born("bystander", specialty="kalshi-weather", family="weather-no")
        since = now_iso(self.clock)
        self.clock.advance(60)
        self.ledger.append("playbook.entry", {"title": "Lesson: 2026-09-25-alts", "source": "teacher",
                                              "text": "Audit crypto-alts reversion before another fork."})
        for _ in range(12):
            for agent in lesson:
                self.block(agent, 0.004, step=600)
            for agent in control:
                self.block(agent, -0.001 if _ % 2 else 0.001, step=600)
            self.block("bystander", -0.05, step=600)
        out = teacher_lift(self.ledger, now=self.clock(), since=since, teacher_days=3, min_blocks=30)
        self.assertEqual((out["lessons"], out["lesson_arm"]["agents"], out["control_arm"]["agents"]), (1, 3, 3))
        self.assertEqual((out["lesson_arm"]["blocks"], out["control_arm"]["blocks"]), (36, 36), "the bystander is named by nothing")
        self.assertAlmostEqual(out["lift"], 0.004, places=6)
        self.assertEqual(out["verdict"], "lift")
        self.assertEqual(teacher_lift(self.ledger, now=self.clock(), since=None)["verdict"], "not_started")

    def test_the_engineer_is_repairs_verified_per_dollar(self):
        self.ledger.append("merton.pass", {"role": "engineer", "cost_usd": "1.20", "files": 2})
        self.ledger.append("merton.pass", {"role": "engineer", "cost_usd": "0.30", "files": 0})
        for state in ("admitted", "verified", "verified"):
            self.ledger.append("repair.status", {"key": "strategy_defect:a:1", "state": state})
        self.ledger.append("repair.status", {"key": "order_refusal:kalshi:x", "state": "verified"})
        out = engineer_lift(self.ledger, now=self.clock(), days=7)
        self.assertEqual((out["repairs_verified"], out["usd"], out["usd_per_repair"], out["verdict"]), (2, "1.5000", "0.7500", "lift"))
        self.clock.advance(8 * 86400)
        later = engineer_lift(self.ledger, now=self.clock(), days=7)
        self.assertEqual((later["repairs_verified"], later["lifetime"]["repairs_verified"], later["verdict"]), (0, 2, "insufficient"))


class HourlyLift(LedgerCase):
    def house(self):
        return SimpleNamespace(ledger=self.ledger, clock=self.clock, _state={}, _state_lock=threading.RLock(),
                               game={"merton": {"lift": {"consult_blocks": 2}}}, jev_floor=None, alerts=[],
                               alert=lambda level, text: self.alerts.append(text))

    def test_the_yield_row_carries_the_lift_and_the_consults_get_their_outcome_rows(self):
        self.alerts = []
        for growth in (-0.01, -0.02):
            self.block("haghani-63", growth)
        self.consult(cost="0.60")
        self.session()
        self.session()
        for growth in (0.01, 0.03):
            self.block("haghani-63", growth)
        house = self.house()
        YieldLedger(house).tick()
        self.assertEqual(self.alerts, [])
        outcomes = {e.payload["stage"]: e.payload for e in self.ledger.iter(kinds="consult.outcome")}
        self.assertEqual((outcomes["sessions"]["productive"], outcomes["sessions"]["doubles_next_price"]), (False, True))
        self.assertAlmostEqual(outcomes["blocks"]["lift"], 0.035, places=6)
        self.assertEqual((outcomes["blocks"]["after"]["positive"], outcomes["blocks"]["partial"]), (2, False))
        row = [e.payload for e in self.ledger.iter(kinds="ops.budget") if e.payload.get("what") == "yield"][-1]
        lift = row["lift"]
        self.assertEqual((lift["consultant"]["judged"], lift["consultant"]["judged_blocks"]), (1, 1))
        self.assertEqual((lift["consultant"]["usd"], lift["consultant"]["usd_per_positive_block"]), ("0.6000", "0.3000"))
        self.assertEqual(lift["consultant"]["verdict"], "insufficient", "one consult is not ten")
        self.assertEqual(lift["teacher"]["verdict"], "not_started")
        self.clock.advance(3600)
        YieldLedger(house).tick()
        self.assertEqual(len(list(self.ledger.iter(kinds="consult.outcome"))), 2, "each stage is written once")


class Bounds(unittest.TestCase):
    def test_the_new_dials_have_bounds_the_checker_holds(self):
        game = load_game()
        self.assertEqual(game["research"]["gate"]["clock_runs"], "real_positions")
        self.assertIn("consultant", game["merton_bounds"]["paused_until_profit"])
        for path, value in ((("research", "gate", "clock_runs"), "sometimes"), (("research", "gate", "practice_max_skip_hours"), 500),
                            (("research", "gate", "idle_runs"), "always"), (("merton", "lift", "consult_max_multiple"), 64)):
            bad = copy.deepcopy(game)
            node = bad
            for key in path[:-1]:
                node = node[key]
            node[path[-1]] = value
            with self.assertRaises(ValueError, msg=path):
                check_bounds(bad)


class GateReplay(LedgerCase):
    """`scripts/gate_replay.py` on a ledger small enough to count by hand."""

    def test_the_replay_counts_what_the_new_rules_would_have_run(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        try:
            import gate_replay
        finally:
            sys.path.remove(str(ROOT / "scripts"))
        L = self.ledger
        for agent, book in (("practice-1", "alpaca-paper"), ("real-1", "alpaca"), ("refused-1", "alpaca-paper")):
            L.append("agent.born", {"specialty": "alpaca-crypto-alts", "family": "f"}, agent=agent)
            L.append("agent.woke", {"ok": True, "book": book, "offered": 3}, agent=agent)  # acted: no barren count
        self.clock.advance(2 * 86400)  # born two days ago: inside a practice agent's 72-hour heartbeat
        for agent in ("practice-1", "real-1"):
            L.append("research.gate", {"decision": "run", "reason": "clock", "trigger": "clock", "triggers": [], "record": "winner"}, agent=agent)
            self.session(agent)
        for amount in ("3.80", "4.10"):
            L.append("book.refused", {"book": "alpaca-paper", "reasons": [f"insufficient desk cash: need {amount} have 1.00"]}, agent="refused-1")
            self.session("refused-1")
        out = gate_replay.replay(str(Path(self.dir.name) / "l.sqlite"), hours=24)
        self.assertEqual(out["by_reason"]["run:clock"]["did"], 2)
        self.assertEqual(out["by_reason"]["run:clock"]["would"], 1, "the real agent keeps its clock; the practice winner waits")
        self.assertEqual((out["by_reason"]["refusal_prompt"]["did"], out["by_reason"]["refusal_prompt"]["would"]), (2, 1))
        self.assertEqual(out["would_run_as"], {"clock:real": 1, "trigger:book.refused": 1})


if __name__ == "__main__":
    unittest.main()
