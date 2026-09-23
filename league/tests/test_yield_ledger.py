"""The hourly yield ledger (Sept 23, 2026): dollars per unit of evidence, by paid line, from the
rows that already exist."""

from __future__ import annotations

import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from league.ledger import Ledger, now_iso
from league.tests.fakes import Clock
from league.tests.test_hypotheses import FoundryCase
from league.yield_ledger import fold, line_of


class Fold(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.clock = Clock()
        self.ledger = Ledger(Path(self.dir.name) / "l.sqlite", clock=self.clock)

    def tearDown(self):
        self.ledger.close()
        self.dir.cleanup()

    def test_lines_are_credited_by_how_the_code_was_born(self):
        self.assertEqual(line_of("card:abc"), "foundry")
        self.assertEqual(line_of("lab:x-1"), "lab")
        self.assertEqual(line_of("repair-x", repair=True), "engineer")
        self.assertEqual(line_of("design-x", "Merton, as architect: why"), "architect")
        self.assertEqual(line_of(None, "a parameter mutation"), "research")

    def test_spend_and_evidence_by_line_and_dollars_per_unit(self):
        since = now_iso(self.clock)
        L = self.ledger
        L.append("agent.born", {"founder": "card:c1", "reason": "hypothesis card"}, agent="huang-h1")
        L.append("agent.born", {"founder": None, "reason": "a parameter mutation"}, agent="mullins-2")
        L.append("credit.charge", {"usd": "0.016", "what": "research tokens"}, agent="mullins-2")
        L.append("credit.charge", {"usd": "0.016", "what": "research tokens"}, agent="mullins-2")
        L.append("credit.charge", {"usd": "0.010", "what": "web search"}, agent="mullins-2")
        L.append("agent.research", {"tool": "summary", "candidate": True, "trials": 1, "reason": "finished"}, agent="mullins-2")
        L.append("agent.research", {"tool": "summary", "candidate": False, "trials": 0, "reason": "finished"}, agent="mullins-2")
        L.append("agent.research", {"tool": "merton", "session": "s", "error": True}, agent="mullins-2")
        L.append("merton.pass", {"role": "foundry", "cost_usd": "0.26", "cards": ["c1"]})
        L.append("merton.pass", {"role": "consultant", "cost_usd": "0.40", "error": True, "agent": "mullins-2"})
        L.append("merton.pass", {"role": "architect", "cost_usd": "5.06", "files": 2})
        L.append("hypothesis.card", {"id": "c1", "niche": "kalshi-crypto-15m"})
        L.append("eval.trial", {"passed": True, "family": "f"}, agent="huang-h1")
        L.append("eval.trial", {"passed": True, "family": "g"}, agent="mullins-2")
        L.append("eval.block", {"active": True, "log_growth": 0.01}, agent="huang-h1")
        L.append("eval.block", {"active": True, "log_growth": -0.02}, agent="huang-h1")
        L.append("eval.block", {"active": False, "log_growth": 0.0}, agent="huang-h1")
        L.append("audit.verdict", {"approve": True, "cost_usd": "0.31"}, agent="mullins-2")
        L.append("playbook.entry", {"title": "t", "text": "x", "source": "teacher"})
        out = fold(L, since=since)
        self.assertEqual(out["spend_usd"], {"architect": "5.0600", "audits": "0.3100", "consultant": "0.4000", "foundry": "0.2600", "research": "0.0320"})
        self.assertEqual(out["evidence"]["research"], {"abstentions": 1, "candidates": 1, "replay_passes": 1, "sessions": 2})
        self.assertEqual(out["evidence"]["foundry"], {"active_blocks": 2, "cards": 1, "positive_blocks": 1, "replay_passes": 1})
        self.assertEqual(out["evidence"]["consultant"], {"errors": 1, "failed": 1})
        self.assertEqual(out["evidence"]["audits"], {"approvals": 1, "verdicts": 1})
        self.assertEqual(out["evidence"]["teacher"], {"lessons": 1})
        self.assertEqual(out["usd_per"]["foundry"], {"cards": "0.2600", "positive_blocks": "0.2600", "replay_passes": "0.2600"})
        self.assertEqual(out["usd_per"]["research"], {"candidates": "0.0320", "replay_passes": "0.0320"})
        self.assertEqual(out["usd_per"]["architect"], {"proposals": "5.0600"}, "one pass that proposed files, whatever their number")
        self.assertEqual(Decimal(out["total_usd"]), Decimal("6.0620"))
        self.clock.advance(7200)
        later = fold(L, since=now_iso(self.clock))
        self.assertEqual((later["spend_usd"], later["evidence"]), ({}, {}), "the window is the window")


class HourlyRow(FoundryCase):
    def test_the_foundry_tick_writes_one_yield_row_an_hour(self):
        self.frontier.candidates = []
        rows = lambda: [e.payload for e in self.house.ledger.iter(kinds="ops.budget") if e.payload.get("what") == "yield"]  # noqa: E731
        self.house.tick()
        self.house.wait()
        self.assertEqual(len(rows()), 1)
        self.assertEqual(rows()[0]["hours"], 1.0)
        self.house.tick()
        self.house.wait()
        self.assertEqual(len(rows()), 1, "not one per tick")
        self.clock.advance(3600)
        self.house.tick()
        self.house.wait()
        self.assertEqual(len(rows()), 2)
        self.assertIn("foundry", rows()[1]["spend_usd"], "the foundry call of the first tick is in the hour's row")


if __name__ == "__main__":
    unittest.main()
