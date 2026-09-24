"""The tick's costs (R6-perf, Sept 24, 2026, the close-the-gaps run): the same answers, read once.

Profiled on a copy of the House's snapshot of Sept 24, 2026 17:27Z (547,400 ledger rows): the seat market
asked every resident's program opportunity on every question (2,256 reads of each agent's every verdict in
six ticks of a full league, 81,096 rows parsed) and read pages of 5,000 rows to answer questions their first
rows answer. Each test pins the answer the old reading gave.
"""

from __future__ import annotations

from unittest.mock import patch

from league.house import _epoch
from league.tests.test_house import BUYER, HouseCase


def opportunity_as_read_before(house, agent, keeps_hours=False):
    """`House._program_opportunity` as it read before R6-perf, row for row: the answer to match."""
    opportunity, opportunity_seq = _epoch(agent.born_at), 0
    first_fill = None
    if keeps_hours:
        found = next(iter(house.ledger.iter(kinds="book.fill", agent=agent.id)), None)
        first_fill = None if found is None else found.seq
    signature = None
    for entry in house.ledger.iter(kinds=("agent.born", "agent.strategy", "eval.verdict"), agent=agent.id):
        p = entry.payload
        if entry.kind == "agent.strategy" and p.get("control"):
            continue
        if entry.kind in ("agent.born", "agent.strategy"):
            current = (p.get("code_sha256"), p.get("params"), p.get("needs"))
            if current != signature:
                if signature is None or not keeps_hours or (first_fill is not None and first_fill < entry.seq):
                    opportunity, opportunity_seq = _epoch(entry.at), entry.seq
                signature = current
        elif p.get("decision") in ("seat", "promote", "demote") and p.get("to_rung") == 1:
            opportunity, opportunity_seq = _epoch(entry.at), entry.seq
    return opportunity, opportunity_seq


class ProgramOpportunity(HouseCase):
    def ask(self, agent):
        return {keeps: self.house._program_opportunity(agent, keeps_hours=keeps) for keeps in (False, True)}

    def expected(self, agent):
        return {keeps: opportunity_as_read_before(self.house, agent, keeps) for keeps in (False, True)}

    def pause(self, agent):
        self.house.ledger.append("agent.research", {"tool": "control", "status": "requested", "control": "pause_entries",
                                                    "session": "s1", "note": "a pause restates the program"},
                                 agent=agent.id, id="control-request:s1:0")
        self.assertEqual(self.house._apply_controls(agent.id, "s1"), ["pause_entries"])

    def test_the_opportunity_is_read_once_a_change_and_answers_as_the_whole_record_does(self):
        agent = self.seated()
        other = self.seated("other", code=BUYER.replace("test-buyer", "test-other"))
        steps = [
            lambda: self.clock.advance(600),
            lambda: self.house.ledger.append("eval.verdict", {"decision": "look", "rung": 1}, agent=agent.id),
            lambda: self.house.registry.adopt(agent.id, code=BUYER + "\n# a new program\n", needs=agent.needs,
                                              params=agent.params, reason="research"),
            lambda: self.house.ledger.append("book.fill", {"book": "alpaca-paper", "source": "venue", "side": "buy"}, agent=agent.id),
            lambda: self.house.registry.adopt(agent.id, code=BUYER + "\n# after its first fill\n", needs=agent.needs,
                                              params=agent.params, reason="research"),
            lambda: self.house.evaluator.promote(agent.id, 2, "passed"),
            lambda: self.house.evaluator.demote(agent.id, "drift"),
            lambda: self.pause(agent),
            lambda: self.house.ledger.append("eval.verdict", {"decision": "look", "rung": 1}, agent=other.id),
        ]
        self.assertEqual(self.ask(agent), self.expected(agent))
        for step in steps:
            step()
            self.assertEqual((self.ask(agent), self.ask(other)), (self.expected(agent), self.expected(other)))
            with patch.object(self.house.ledger, "read", wraps=self.house.ledger.read) as read:
                again = self.ask(agent)
            self.assertEqual(again, self.expected(agent))
            whole = [c.kwargs for c in read.call_args_list if c.kwargs.get("limit") != 1]
            self.assertEqual(whole, [], "nothing new: only its newest row and its first fill are read, one row each")


class FirstRow(HouseCase):
    def test_the_first_matching_row_is_the_one_a_whole_page_gave(self):
        agent = self.seated()
        for i in range(150):
            self.house.ledger.append("agent.woke", {"ok": True, "offered": 1 if i in (70, 149) else 0}, agent=agent.id)
            if i == 120:
                self.house.ledger.append("book.fill", {"book": "alpaca-paper", "source": "venue"}, agent=agent.id)

        def match(e):
            return e.kind == "book.fill" or (e.payload.get("ok") and int(e.payload.get("offered") or 0) > 0)

        kinds = ("agent.woke", "book.fill")
        seqs = [e.seq for e in self.house.ledger.iter(kinds=kinds, agent=agent.id)]
        for after in (0, seqs[69], seqs[70], seqs[121], seqs[-2], seqs[-1]):
            whole = next((e for e in self.house.ledger.iter(kinds=kinds, agent=agent.id, after=after) if match(e)), None)
            paged = self.house._first_row(kinds, agent.id, after, match)
            self.assertEqual(None if paged is None else paged.seq, None if whole is None else whole.seq, after)
        with patch.object(self.house.ledger, "read", wraps=self.house.ledger.read) as read:
            self.assertIsNotNone(self.house._first_row(kinds, agent.id, 0, match))
        self.assertEqual([c.kwargs["limit"] for c in read.call_args_list], [64, 64], "the first match is in the second page of 64")
