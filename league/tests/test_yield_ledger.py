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


class ByProfile(unittest.TestCase):
    """L2 (Sept 24, 2026): the hourly yield row reports candidates per dollar per profile. The gap
    review priced a Sail pro_asap session at about $0.055 against Luna's $0.017 by hand; the row
    now says it every hour, from each session's own research-token charges."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.clock = Clock()
        self.ledger = Ledger(Path(self.dir.name) / "l.sqlite", clock=self.clock)

    def tearDown(self):
        self.ledger.close()
        self.dir.cleanup()

    def session(self, name, profile, charges, *, candidate=False, reason="finished"):
        for turn, usd in enumerate(charges):
            self.ledger.append("credit.charge", {"usd": usd, "what": "research tokens", "detail": {"session": name, "turn": turn}},
                               agent="mullins-2", id=f"tokens:{name}:{turn}")
        self.ledger.append("agent.research", {"tool": "summary", "session": name, "profile": profile, "candidate": candidate, "trials": 0,
                                              "reason": reason, "cost_usd": str(sum(Decimal(c) for c in charges))}, agent="mullins-2")

    def test_candidates_per_dollar_by_profile(self):
        self.ledger.append("credit.charge", {"usd": "0.020", "what": "research tokens", "detail": {"session": "before", "turn": 0}},
                           agent="mullins-2", id="tokens:before:0")  # charged before the window...
        self.clock.advance(1)
        since = now_iso(self.clock)
        self.clock.advance(60)
        self.ledger.append("agent.research", {"tool": "summary", "session": "before", "profile": "pro_asap", "candidate": False,
                                              "trials": 0, "reason": "finished", "cost_usd": "0.020"}, agent="mullins-2")  # ...its summary inside
        self.session("a1", "pro_asap", ["0.030", "0.025"], candidate=True)
        self.session("a2", "pro_asap", ["0.055"])
        self.session("l1", "openai_luna", ["0.008", "0.009"], candidate=True)
        self.session("l2", "openai_luna", ["0.004"], reason="provider: provider_http_502")
        out = fold(self.ledger, since=since)
        asap, luna = out["by_profile"]["pro_asap"], out["by_profile"]["openai_luna"]
        self.assertEqual((asap["sessions"], asap["candidates"], asap["usd"]), (3, 1, "0.1300"))
        self.assertEqual(asap["candidates_per_usd"], 7.69)
        self.assertEqual((luna["sessions"], luna["candidates"], luna["provider_failures"], luna["usd"]), (2, 1, 1, "0.0210"))
        self.assertEqual(luna["candidates_per_usd"], 47.62)
        self.assertEqual(out["usd_per"]["research"]["candidates"], "0.0655", "the research line's own arithmetic is unchanged")


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
