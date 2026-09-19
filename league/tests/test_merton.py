import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from league.merton import Merton, ForgeError, parse_proposal
from league.frontier import Answer, FrontierError
from league.ledger import Ledger
from league.tests.fakes import Clock

GOOD = '''
NEEDS = {"venue": "alpaca", "horizon": "hour", "style": "test", "symbols": ["BTC/USD"], "wake_minutes": 15}
PARAMS = {}

def decide(ctx):
    return {"intents": [], "thought": "nothing"}
'''


class FakeFrontier:
    def __init__(self, answer=None, error=None):
        self.answer, self.error, self.asked = answer, error, []

    def ask(self, **kw):
        self.asked.append(kw)
        if self.error:
            raise self.error
        return Answer(json.dumps(self.answer), Decimal("1.25"), {}, "gpt-6-astra")


class FakeForge:
    def __init__(self, fail=False):
        self.proposed, self.fail, self.statuses = [], fail, {}

    def propose(self, **kw):
        if self.fail:
            raise ForgeError("HTTP 503: GitHub is not configured.")
        self.proposed.append(kw)
        return {"ok": True, "branch": f"merton/{kw['role']}/{kw['slug']}-abcd1234", "number": 7, "url": "https://github.com/x/y/pull/7"}

    def status(self, number):
        return self.statuses[number]


class ProposalTest(unittest.TestCase):
    def test_only_the_roles_own_paths_survive(self):
        answer = {"summary": "s", "slug": "New Idea!", "title": "t", "body": "b", "files": [
            {"path": "league/strategies/new_idea.py", "content": GOOD},
            {"path": "league/constitution.py", "content": "x = 1"},
            {"path": "league/game.json", "content": "{}"},
            {"path": "../etc/passwd", "content": "x"},
            {"path": "league/strategies/bad.py", "content": "import os\ndef decide(ctx):\n    return {}\n"},
            {"path": "league/strategies/registry.json", "content": "not json"},
        ]}
        proposal = parse_proposal("architect", answer, Decimal("1"))
        self.assertEqual([f["path"] for f in proposal.files], ["league/strategies/new_idea.py"])
        self.assertEqual(len(proposal.dropped), 5)
        self.assertEqual(proposal.slug, "new-idea")

    def test_a_designer_may_touch_only_the_game(self):
        answer = {"files": [{"path": "league/game.json", "content": "{}"}, {"path": "league/strategies/x.py", "content": GOOD}]}
        self.assertEqual([f["path"] for f in parse_proposal("designer", answer, Decimal(0)).files], ["league/game.json"])

    def test_garbage_is_no_files(self):
        self.assertEqual(parse_proposal("teacher", {"files": "everything"}, Decimal(0)).files, [])
        self.assertEqual(parse_proposal("teacher", {"files": [1, {"path": 3}]}, Decimal(0)).files, [])


class MertonTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.clock = Clock()
        self.ledger = Ledger(Path(self.dir.name) / "l.sqlite", clock=self.clock)

    def tearDown(self):
        self.ledger.close()
        self.dir.cleanup()

    def merton(self, frontier, forge, evidence=None):
        return Merton(frontier, forge, self.ledger, evidence=evidence or (lambda role: {"league_table": [], "open_requests": [{"name": "x"}]}), clock=self.clock)

    def test_a_pass_with_a_change_becomes_a_pull_request_and_two_ledger_rows(self):
        answer = {"summary": "an empty niche", "slug": "idea", "title": "A new strategy", "body": "why", "files": [{"path": "league/strategies/idea.py", "content": GOOD}]}
        frontier, forge = FakeFrontier(answer), FakeForge()
        row = self.merton(frontier, forge).run("architect")
        self.assertEqual(forge.proposed[0]["role"], "architect")
        self.assertEqual(row["number"], 7)
        self.assertEqual(row["cost_usd"], "1.25")
        self.assertEqual(frontier.asked[0]["agent"], "merton-architect")
        self.assertIn("THE STRATEGY CONTRACT", frontier.asked[0]["system"])
        change = self.ledger.last("merton.change").payload
        self.assertEqual((change["status"], change["paths"]), ("opened", ["league/strategies/idea.py"]))

    def test_doing_nothing_is_recorded_and_opens_nothing(self):
        forge = FakeForge()
        row = self.merton(FakeFrontier({"summary": "nothing new", "files": []}), forge).run("teacher")
        self.assertEqual(forge.proposed, [])
        self.assertEqual(row["files"], 0)
        self.assertEqual(self.ledger.count(kinds="merton.change"), 0)

    def test_a_failed_call_or_an_unconfigured_forge_is_a_row_not_a_crash(self):
        row = self.merton(FakeFrontier(error=FrontierError("HTTP 402", status=402)), FakeForge()).run("designer")
        self.assertTrue(row["error"])
        answer = {"summary": "s", "slug": "x", "title": "t", "body": "b", "files": [{"path": "league/playbook/2026-09-20-x.md", "content": "a lesson"}]}
        row = self.merton(FakeFrontier(answer), FakeForge(fail=True)).run("teacher")
        self.assertIn("not configured", row["forge_error"])

    def test_the_toolsmith_does_not_spend_money_on_an_empty_queue(self):
        frontier = FakeFrontier({"files": []})
        row = self.merton(frontier, FakeForge(), evidence=lambda role: {"open_requests": []}).run("toolsmith")
        self.assertTrue(row["skipped"])
        self.assertEqual(frontier.asked, [])

    def test_the_toolsmith_answers_the_queue_even_when_it_builds_nothing(self):
        self.ledger.append("tool.request", {"name": "longer_tape", "description": "a longer replay tape for hourly markets"}, agent="a1", id="req-1")
        answer = {"summary": "needs data, not a tool", "files": [], "answers": [{"request": "req-1", "outcome": "cannot be a pure tool: it needs more recorded history"}, {"request": "made-up", "outcome": "x"}]}
        merton = self.merton(FakeFrontier(answer), FakeForge(), evidence=lambda role: {"open_requests": [{"id": "req-1", "name": "longer_tape"}]})
        merton.run("toolsmith")
        rows = [e.payload for e in self.ledger.iter(kinds="tool.fulfilled")]
        self.assertEqual([(r["request"], r["outcome"][:20]) for r in rows], [("req-1", "cannot be a pure too")])

    def test_each_role_is_due_on_its_own_clock(self):
        merton = self.merton(FakeFrontier({"files": []}), FakeForge())
        self.ledger.append("ops.started", {"release": "test"})
        self.assertEqual(merton.due(), [])  # nobody sits down on the first morning: there is nothing to read yet
        self.clock.advance(7 * 3600)
        self.assertEqual(merton.due(), ["operator"])
        self.clock.advance(66 * 3600)
        self.assertEqual(set(merton.due()), {"architect", "toolsmith", "operator", "designer", "teacher"})
        merton.run("operator")
        merton.run("architect")
        self.assertNotIn("operator", merton.due())
        self.clock.advance(25 * 3600)
        self.assertIn("operator", merton.due())
        self.assertNotIn("architect", merton.due())

    def test_following_records_what_ci_decided(self):
        answer = {"summary": "s", "slug": "idea", "title": "t", "body": "b", "files": [{"path": "league/strategies/idea.py", "content": GOOD}]}
        forge = FakeForge()
        merton = self.merton(FakeFrontier(answer), forge)
        merton.run("architect")
        forge.statuses[7] = {"merged": False, "state": "open", "checks": {"conclusion": "pending"}}
        self.assertEqual(merton.follow(), [])
        forge.statuses[7] = {"merged": False, "state": "open", "checks": {"conclusion": "failure"}}
        self.assertEqual(merton.follow()[0]["status"], "refused by CI")
        self.assertEqual(merton.follow(), [])  # recorded once


if __name__ == "__main__":
    unittest.main()


class Consulting(unittest.TestCase):
    """Merton for hire: one agent pays him, out of credits it earned, to think about its problem."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.clock = Clock()
        self.ledger = Ledger(Path(self.dir.name) / "l.sqlite", clock=self.clock)
        self.agent = SimpleNamespace(id="meriwether-3", family="sports-favorites", niche="kalshi-sports", generation=1)

    def tearDown(self):
        self.ledger.close()
        self.dir.cleanup()

    def merton(self, answer=None, error=None):
        self.frontier = FakeFrontier(answer, error)
        return Merton(self.frontier, None, self.ledger, evidence=lambda role: {}, clock=self.clock)

    def test_advice_is_recorded_with_its_price_and_no_code(self):
        merton = self.merton({"answer": "Enter before kickoff; a resting bid is picked off on a goal.", "code": "", "confidence": "high"})
        out = merton.consult(self.agent, "Why do my fills lose?", {"strategy_file": "x"}, contract="C")
        self.assertEqual((out["answer"][:20], out["code"], out["confidence"], out["cost_usd"]), ("Enter before kickoff", "", "high", "1.25"))
        row = self.ledger.last("merton.pass").payload
        self.assertEqual((row["role"], row["agent"], row["wrote_code"]), ("consultant", "meriwether-3", False))
        self.assertEqual(row["question"], "Why do my fills lose?")
        self.assertNotIn("code", row)  # the file is the agent's to run, not a line on the public record
        asked = self.frontier.asked[0]
        self.assertEqual((asked["agent"], asked["effort"]), ("consult-meriwether-3", "high"))
        self.assertIn("THE STRATEGY CONTRACT", asked["system"])

    def test_a_whole_file_comes_back_whole(self):
        code = "NEEDS = {}\nPARAMS = {}\n\ndef decide(ctx):\n    return {}\n"
        merton = self.merton({"answer": "Here.", "code": code, "confidence": "medium"})
        out = merton.consult(self.agent, "Write me one that only enters before the start.", {}, contract="C")
        self.assertEqual(out["code"], code)
        self.assertTrue(self.ledger.last("merton.pass").payload["wrote_code"])

    def test_a_frontier_failure_costs_the_agent_nothing_and_says_so(self):
        merton = self.merton(error=FrontierError("the gateway refused it"))
        out = merton.consult(self.agent, "Anything?", {}, contract="C")
        self.assertEqual((out["cost_usd"], out["code"], out["error"]), ("0", "", True))
        self.assertIn("could not be reached", out["answer"])
        self.assertTrue(self.ledger.last("merton.pass").payload["error"])

    def test_he_is_told_what_he_may_not_do(self):
        from league.merton import CONSULT

        self.assertIn("NOT given the power to trade, to promote it, or to change the rules", CONSULT)
        self.assertIn("keep the agent inside its specialty", CONSULT)
