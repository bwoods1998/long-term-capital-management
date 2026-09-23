"""Research runs when something changed, not when the clock says so (Sept 23, 2026).

Measured on the production ledger, 00:00Z Sept 22 to 16:28Z Sept 23: 90.3% of 7,532 research
sessions abstained, abstentions cost $112.80 of $147.44, and 41% of the gate's runs were `clock`
or `backoff_elapsed`. These tests pin the evidence-only rule (`clock_runs: winners_and_idle`), the
abstention lock (`abstain_lock_after: 3`) and the `trigger` / `record` columns on every row.
"""

from __future__ import annotations

import unittest

from league.research_gate import report
from league.tests.test_jev_sensor import GateCase, summary


class EvidenceOnlyGate(GateCase):
    def evidence_ready(self, **settings):
        return self.ready(legacy=False, settings={"clock_runs": "winners_and_idle", "abstain_lock_after": 3, **settings})

    def win(self, agent, n=3, growth=0.004):
        for i in range(n):
            self.house.ledger.append("eval.block", {"agent": agent.id, "log_growth": growth, "active": True,
                                                    "book": "alpaca-paper", "block": f"b{i}"}, agent=agent.id)

    def test_an_unproven_agent_waits_for_evidence_and_the_row_says_so(self):
        agent = self.evidence_ready()
        self.clock.advance(self.interval)
        self.assertFalse(self.house.research_due(agent), "no fill, settlement or verdict: the clock alone buys nothing")
        row = self.gates()[-1]
        self.assertEqual((row["decision"], row["reason"], row["record"], row["trigger"]), ("skip", "nothing_new:unproven", "unproven", "nothing_new"))
        self.house.ledger.append("book.settle", {"book": "kalshi-shadow", "pnl": "1.00"}, agent=agent.id)
        self.clock.advance(60)
        self.assertTrue(self.house.research_due(agent))
        row = self.gates()[-1]
        self.assertEqual((row["decision"], row["reason"], row["trigger"], row["record"]), ("run", "trigger", "book.settle", "unproven"))
        self.assertIn("book.settle:1", row["triggers"])

    def test_a_winner_keeps_its_clock_and_an_idle_agent_its_cadence(self):
        agent = self.evidence_ready()
        self.win(agent)  # before the gate's first look: not news, just the record it reads
        self.house.standings()
        self.clock.advance(self.interval)
        self.assertTrue(self.house.research_due(agent), "a positive earned record still researches on the clock")
        self.assertEqual((self.gates()[-1]["reason"], self.gates()[-1]["record"]), ("clock", "winner"))
        self.researched(agent)
        summary(self.house.ledger, agent.id)
        self.clock.advance(self.interval)
        self.assertTrue(self.house.research_due(agent), "one empty pass is below `after`: the clock still decides for a winner")
        self.assertEqual((self.gates()[-1]["reason"], self.gates()[-1]["record"]), ("clock", "winner"))
        idle = self.seated("idler")
        self.house._state["last_research"][idle.id] = self.clock()
        self.house._state["idle"][idle.id] = {"barren": 10, "shut": 0, "offered": 4}
        self.clock.advance(self.house.research_interval_hours(idle) * 3600)
        self.assertTrue(self.house.research_due(idle), "an idle agent's research is pulled forward as before")
        self.assertEqual((self.gates(idle.id)[-1]["reason"], self.gates(idle.id)[-1]["record"]), ("clock", "idle"))

    def test_the_heartbeat_still_wakes_an_agent_nothing_ever_happens_to(self):
        agent = self.evidence_ready(max_skip_hours=5)
        self.clock.advance(self.interval)
        self.assertFalse(self.house.research_due(agent))
        self.clock.advance(5 * 3600)
        self.assertTrue(self.house.research_due(agent))
        self.assertEqual(self.gates()[-1]["reason"], "heartbeat")

    def test_three_abstentions_lock_research_to_its_own_venue_outcomes(self):
        agent = self.evidence_ready()
        self.win(agent)
        self.house.standings()
        for _ in range(3):
            summary(self.house.ledger, agent.id)
        self.researched(agent)
        other = self.seated("neighbour")
        self.house.ledger.append("library.note", {"niche": agent.niche, "title": "t", "text": "a note for the desk"}, agent=other.id)
        self.clock.advance(self.interval)
        self.assertFalse(self.house.research_due(agent), "a winner, but three empty sessions: a neighbour's note does not wake it")
        row = self.gates()[-1]
        self.assertEqual((row["decision"], row["reason"], row["empty_streak"]), ("skip", "abstain_lock:3", 3))
        self.house.ledger.append("book.fill", {"book": "alpaca-paper", "source": "venue"}, agent=agent.id)
        self.clock.advance(60)
        self.assertTrue(self.house.research_due(agent), "a fill of its own still wakes it")
        self.assertEqual(self.gates()[-1]["trigger"], "book.fill")
        summary(self.house.ledger, agent.id, candidate=True, trials=1)  # the session produced a candidate: the lock lifts
        self.researched(agent)
        self.house.ledger.append("library.note", {"niche": agent.niche, "title": "t2", "text": "another note"}, agent=other.id)
        self.clock.advance(self.interval)
        self.assertTrue(self.house.research_due(agent))
        self.assertEqual(self.gates()[-1]["trigger"], "library.note")

    def test_a_lesson_for_its_desk_a_repair_verdict_and_an_audit_are_triggers(self):
        agent = self.evidence_ready()
        self.clock.advance(self.interval)
        self.assertFalse(self.house.research_due(agent))
        self.house.ledger.append("playbook.entry", {"title": "On the test family", "text": f"what {agent.family} keeps doing wrong", "source": "teacher"})
        self.clock.advance(60)
        self.assertTrue(self.house.research_due(agent))
        self.assertEqual(self.gates()[-1]["trigger"], "lesson")
        self.researched(agent)
        self.clock.advance(self.interval)
        self.house.ledger.append("repair.status", {"key": f"strategy_defect:{agent.id}:abcdef123456", "state": "verified", "note": "n"})
        self.assertTrue(self.house.research_due(agent))
        self.assertEqual(self.gates()[-1]["trigger"], "repair.status")
        self.researched(agent)
        self.clock.advance(self.interval)
        self.house.ledger.append("audit.verdict", {"approve": False, "reasons": ["x"]}, agent=agent.id)
        self.assertTrue(self.house.research_due(agent))
        self.assertEqual(self.gates()[-1]["trigger"], "audit.verdict")
        self.assertIn("audit.verdict:refuse:1", self.gates()[-1]["triggers"])

    def test_the_report_prices_each_kind_of_evidence(self):
        agent = self.evidence_ready()
        self.clock.advance(self.interval)
        self.assertFalse(self.house.research_due(agent))
        self.house.ledger.append("book.settle", {"book": "kalshi-shadow", "pnl": "1.00"}, agent=agent.id)
        self.clock.advance(60)
        self.assertTrue(self.house.research_due(agent))
        summary(self.house.ledger, agent.id, candidate=True, trials=1)
        out = report(self.house.ledger)
        self.assertEqual(out["by_trigger"]["book.settle"]["runs"], 1)
        self.assertEqual(out["by_trigger"]["book.settle"]["candidates"], 1)
        self.assertEqual(out["by_trigger"]["book.settle"]["usd_per_candidate"], "0.0160")


if __name__ == "__main__":
    unittest.main()
