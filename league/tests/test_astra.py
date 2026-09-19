import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from league.astra import Astra, ForgeError, parse_proposal
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
        return {"ok": True, "branch": f"astra/{kw['role']}/{kw['slug']}-abcd1234", "number": 7, "url": "https://github.com/x/y/pull/7"}

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


class AstraTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.clock = Clock()
        self.ledger = Ledger(Path(self.dir.name) / "l.sqlite", clock=self.clock)

    def tearDown(self):
        self.ledger.close()
        self.dir.cleanup()

    def astra(self, frontier, forge, evidence=None):
        return Astra(frontier, forge, self.ledger, evidence=evidence or (lambda role: {"league_table": [], "open_requests": [{"name": "x"}]}), clock=self.clock)

    def test_a_pass_with_a_change_becomes_a_pull_request_and_two_ledger_rows(self):
        answer = {"summary": "an empty niche", "slug": "idea", "title": "A new strategy", "body": "why", "files": [{"path": "league/strategies/idea.py", "content": GOOD}]}
        frontier, forge = FakeFrontier(answer), FakeForge()
        row = self.astra(frontier, forge).run("architect")
        self.assertEqual(forge.proposed[0]["role"], "architect")
        self.assertEqual(row["number"], 7)
        self.assertEqual(row["cost_usd"], "1.25")
        self.assertEqual(frontier.asked[0]["agent"], "astra:architect")
        self.assertIn("THE STRATEGY CONTRACT", frontier.asked[0]["system"])
        change = self.ledger.last("astra.change").payload
        self.assertEqual((change["status"], change["paths"]), ("opened", ["league/strategies/idea.py"]))

    def test_doing_nothing_is_recorded_and_opens_nothing(self):
        forge = FakeForge()
        row = self.astra(FakeFrontier({"summary": "nothing new", "files": []}), forge).run("teacher")
        self.assertEqual(forge.proposed, [])
        self.assertEqual(row["files"], 0)
        self.assertEqual(self.ledger.count(kinds="astra.change"), 0)

    def test_a_failed_call_or_an_unconfigured_forge_is_a_row_not_a_crash(self):
        row = self.astra(FakeFrontier(error=FrontierError("HTTP 402", status=402)), FakeForge()).run("designer")
        self.assertTrue(row["error"])
        answer = {"summary": "s", "slug": "x", "title": "t", "body": "b", "files": [{"path": "league/playbook/2026-09-20-x.md", "content": "a lesson"}]}
        row = self.astra(FakeFrontier(answer), FakeForge(fail=True)).run("teacher")
        self.assertIn("not configured", row["forge_error"])

    def test_the_toolsmith_does_not_spend_money_on_an_empty_queue(self):
        frontier = FakeFrontier({"files": []})
        row = self.astra(frontier, FakeForge(), evidence=lambda role: {"open_requests": []}).run("toolsmith")
        self.assertTrue(row["skipped"])
        self.assertEqual(frontier.asked, [])

    def test_each_role_is_due_on_its_own_clock(self):
        astra = self.astra(FakeFrontier({"files": []}), FakeForge())
        self.assertEqual(set(astra.due()), {"architect", "toolsmith", "operator", "designer", "teacher"})
        astra.run("operator")
        astra.run("architect")
        self.assertNotIn("operator", astra.due())
        self.clock.advance(25 * 3600)
        self.assertIn("operator", astra.due())
        self.assertNotIn("architect", astra.due())

    def test_following_records_what_ci_decided(self):
        answer = {"summary": "s", "slug": "idea", "title": "t", "body": "b", "files": [{"path": "league/strategies/idea.py", "content": GOOD}]}
        forge = FakeForge()
        astra = self.astra(FakeFrontier(answer), forge)
        astra.run("architect")
        forge.statuses[7] = {"merged": False, "state": "open", "checks": {"conclusion": "pending"}}
        self.assertEqual(astra.follow(), [])
        forge.statuses[7] = {"merged": False, "state": "open", "checks": {"conclusion": "failure"}}
        self.assertEqual(astra.follow()[0]["status"], "refused by CI")
        self.assertEqual(astra.follow(), [])  # recorded once


if __name__ == "__main__":
    unittest.main()
