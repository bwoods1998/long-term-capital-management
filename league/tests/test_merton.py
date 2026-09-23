import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

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
    def test_the_retired_registry_becomes_descriptions_of_the_proposal_s_own_files_only(self):
        rows = [{'name': 'new-idea', 'family': 'f', 'why': 'w', 'file': name} for name in (
            'league/strategies/new_idea.py', 'old.py', 'league/strategies/../constitution.py', '/tmp/hidden.py')]
        proposal = parse_proposal('architect', {'files': [
            {'path': 'league/strategies/new_idea.py', 'content': GOOD},
            {'path': 'league/strategies/registry.json', 'content': json.dumps(rows)}]}, Decimal('1'))
        self.assertEqual([f['path'] for f in proposal.files], ['league/strategies/new_idea.py', 'league/strategies/new_idea.json'])
        self.assertEqual(json.loads(proposal.files[1]['content']), {'name': 'new-idea', 'family': 'f', 'why': 'w'})

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

    def test_a_paid_unreadable_pass_retains_its_cost(self):
        frontier = SimpleNamespace(ask=lambda **kw: Answer("not JSON", Decimal("0.85"), {}, "test-model"))
        row = self.merton(frontier, FakeForge()).run("architect")
        self.assertTrue(row["error"])
        self.assertEqual(row["cost_usd"], "0.85")
        self.assertEqual(self.ledger.last("merton.pass").payload["cost_usd"], "0.85")

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
        rows = [e.payload for e in self.ledger.iter(kinds="tool.blocked")]
        self.assertEqual([(r["request"], r["outcome"][:20]) for r in rows], [("req-1", "cannot be a pure too")])
        self.assertEqual(self.ledger.count(kinds='tool.fulfilled'), 0)

    def tool_proposal(self, forge):
        self.ledger.append("tool.request", {"name": "midpoint", "description": "price an existing two-sided quote"}, agent="a1", id="req-1")
        content = "def midpoint(bid, ask):\n    return (bid + ask) / 2\n"
        answer = {"summary": "quote helper", "files": [{"path": "league/tools/midpoint.py", "content": content}],
                  "answers": [{"request": "req-1", "outcome": "midpoint helper implemented"}]}
        return self.merton(FakeFrontier(answer), forge, evidence=lambda role: {"open_requests": [{"id": "req-1"}]}), content

    def test_a_tool_request_survives_a_failed_forge(self):
        merton, _ = self.tool_proposal(FakeForge(fail=True))
        self.assertIn("forge_error", merton.run("toolsmith"))
        self.assertEqual(self.ledger.count(kinds="tool.fulfilled"), 0)

    def test_a_tool_request_survives_failed_ci(self):
        forge = FakeForge()
        merton, _ = self.tool_proposal(forge)
        merton.run("toolsmith")
        self.assertEqual(self.ledger.count(kinds="tool.fulfilled"), 0)
        forge.statuses[7] = {"state": "open", "checks": {"conclusion": "failure"}}
        merton.follow()
        self.assertEqual(self.ledger.count(kinds="tool.fulfilled"), 0)

    def test_a_merged_tool_is_fulfilled_only_once_its_contents_are_running(self):
        forge = FakeForge()
        merton, content = self.tool_proposal(forge)
        merton.run("toolsmith")
        forge.statuses[7] = {"merged": True, "state": "closed", "checks": {"conclusion": "success"}}
        root = Path(self.dir.name)
        with patch("league.merton.__file__", str(root / "league/merton.py")):
            self.assertEqual([r["status"] for r in merton.follow()], ["merged"])
            self.assertEqual(self.ledger.count(kinds="tool.fulfilled"), 0)
            # A later process sees the durable pending change, not an in-memory proposal.
            restarted = self.merton(FakeFrontier(), forge)
            tool = root / "league/tools/midpoint.py"
            tool.parent.mkdir(parents=True)
            tool.write_text("def midpoint(bid, ask):\n    return bid\n")
            self.assertEqual(restarted.follow(), [])
            tool.write_text(content)
            self.assertEqual([r["status"] for r in restarted.follow()], ["deployed"])
            self.assertEqual(self.ledger.last("tool.fulfilled").payload["status"], "deployed")
            self.assertEqual(restarted.follow(), [])
            self.assertEqual(self.ledger.count(kinds="tool.fulfilled"), 1)

    def test_a_rejected_tool_file_does_not_close_its_request(self):
        self.ledger.append("tool.request", {"name": "x"}, id="req-1")
        answer = {"files": [{"path": "league/constitution.py", "content": "changed"}],
                  "answers": [{"request": "req-1", "outcome": "fixed"}]}
        self.merton(FakeFrontier(answer), FakeForge(), evidence=lambda role: {"open_requests": [{"id": "req-1"}]}).run("toolsmith")
        self.assertEqual(self.ledger.count(kinds="tool.fulfilled"), 0)

    def test_duplicate_and_invalid_tool_answers_do_not_lose_the_paid_pass(self):
        frontier = FakeFrontier({"files": [], "answers": [
            {"request": {}, "outcome": "bad id"},
            {"request": "req-1", "outcome": "first answer"},
            {"request": "req-1", "outcome": "final answer"},
        ]})
        merton = self.merton(frontier, FakeForge(), evidence=lambda role: {"open_requests": [{"id": "req-1"}]})
        row = merton.run("toolsmith")
        self.assertEqual(row["cost_usd"], "1.25")
        self.assertEqual(self.ledger.count(kinds="tool.blocked"), 1)
        self.assertEqual(self.ledger.last("tool.blocked").payload["outcome"], "final answer")

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

    def test_a_role_that_keeps_changing_nothing_sits_down_less_often(self):
        """Sept 21, 2026: fifteen operator passes in four hours, every one "leave the dials
        unchanged". One empty pass is normal; each further one doubles the wait, up to eight."""
        merton = self.merton(FakeFrontier({"files": []}), FakeForge())
        self.ledger.append("ops.started", {"release": "test"})
        self.assertEqual(merton.backoff("operator"), 1)
        for expected in (1, 2, 4, 8, 8):
            merton.run("operator")
            self.assertEqual(merton.backoff("operator"), expected)
        self.clock.advance(24 * 3600 * 7.9)
        self.assertNotIn("operator", merton.due())
        self.clock.advance(24 * 3600 * 0.2)
        self.assertIn("operator", merton.due())
        self.ledger.append("merton.pass", {"role": "operator", "at_epoch": self.clock(), "files": 1, "summary": "a change"})
        self.assertEqual(merton.backoff("operator"), 1)
        self.ledger.append("merton.pass", {"role": "operator", "at_epoch": self.clock(), "files": 0, "skipped": True})
        self.assertEqual(merton.backoff("operator"), 1)  # a skipped pass neither counts nor resets

    def test_the_architect_backs_off_at_most_twice(self):
        merton = self.merton(FakeFrontier({"files": []}), FakeForge())
        merton.backoff_max = {"architect": 2}
        self.ledger.append("ops.started", {"release": "test"})
        for _ in range(5):
            merton.run("architect")
            merton.run("operator")
        self.assertEqual((merton.backoff("architect"), merton.backoff("operator")), (2, 8))

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
        # Room to finish: at 12,000 tokens and "high" effort most consultations of Sept 22, 2026
        # spent the whole allowance reasoning and came back incomplete, paid for and empty.
        self.assertEqual((asked["agent"], asked["effort"], asked["max_output_tokens"]), ("consult-meriwether-3", "medium", 16000))
        self.assertIn("THE STRATEGY CONTRACT", asked["system"])
        prompt = json.loads(asked["user"])
        self.assertEqual(prompt["question"], "Why do my fills lose?")
        self.assertEqual(prompt["evidence"], {"strategy_file": "x"})

    def test_the_caller_may_set_the_room_and_effort_within_the_gateways_ceiling(self):
        merton = self.merton({"answer": "ok", "code": "", "confidence": "low"})
        merton.consult(self.agent, "Why do my fills lose?", {}, contract="C", max_output_tokens=90000, effort="high")
        merton.consult(self.agent, "Why do my fills lose?", {}, contract="C", max_output_tokens=10, effort="loud")
        self.assertEqual([(a["max_output_tokens"], a["effort"]) for a in self.frontier.asked], [(16000, "high"), (4000, "medium")])

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

    def test_an_unreadable_paid_consultation_is_still_billed(self):
        merton = self.merton()
        merton.frontier = SimpleNamespace(ask=lambda **kw: Answer("not JSON", Decimal("0.37"), {}, "test-model"))
        out = merton.consult(self.agent, "Help with fees?", {}, contract="C")
        self.assertTrue(out["error"])
        self.assertEqual(out["cost_usd"], "0.37")
        self.assertIn("unreadable", out["answer"])
        self.assertEqual(self.ledger.last("merton.pass").payload["cost_usd"], "0.37")

    def test_he_is_told_what_he_may_not_do(self):
        from league.merton import CONSULT

        self.assertIn("NOT given the power to trade, to promote it, or to change the rules", CONSULT)
        self.assertIn("keep the agent inside its specialty", CONSULT)

    def test_he_is_told_to_write_a_file_not_a_critique(self):
        """Ten agents hired him on the floor's first night and ten got advice alone, mostly "audit
        this before you spend another trial" -- counsel any of them could have written itself, at
        the price of the best mind in the firm."""
        from league.merton import CONSULT

        self.assertIn("WRITE IT A STRATEGY FILE", CONSULT)
        self.assertIn("Advice is the\nEXCEPTION here, not the default", CONSULT)
        self.assertLess(CONSULT.index("A WHOLE STRATEGY FILE"), CONSULT.index("ADVICE ALONE"))


class PacedByTheBudget(unittest.TestCase):
    """The frontier budget is the half that writes strategies, builds tools and reads the floor.
    Eleven hours into the expedition the gateway had billed $1.72 of it against $7.14 a day."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.clock = Clock()
        self.ledger = Ledger(Path(self.dir.name) / "l.sqlite", clock=self.clock)
        self.share = [1.0]
        self.merton = Merton(FakeFrontier({"files": []}), FakeForge(), self.ledger, evidence=lambda role: {},
                             clock=self.clock, schedule_hours={"operator": 8, "teacher": 12, "toolsmith": 8, "designer": 36, "architect": 8},
                             first_after_hours={"operator": 0, "teacher": 0, "toolsmith": 0, "designer": 0, "architect": 0},
                             pace=lambda: self.share[0])

    def tearDown(self):
        self.ledger.close()
        self.dir.cleanup()

    def test_an_underspent_day_brings_a_role_round_sooner(self):
        self.ledger.append("ops.started", {"release": "test"})
        self.merton.run("operator")
        self.clock.advance(5 * 3600)
        self.assertNotIn("operator", self.merton.due())  # eight hours, on the game file's clock
        self.share[0] = 0.5
        self.assertIn("operator", self.merton.due())  # four, while the day's frontier is unspent

    def test_the_schedule_is_never_stretched_and_never_gutted(self):
        self.ledger.append("ops.started", {"release": "test"})
        self.merton.run("architect")
        last = self.merton.last_pass("architect")
        for share, hours, expected in ((4.0, 7.9, False), (4.0, 8.1, True), (0.0, 1.9, False), (0.0, 2.1, True), (None, 8.1, True)):
            self.share[0] = share                 # stretched back to one, gutted up to a quarter
            self.clock.now = last + hours * 3600
            self.assertEqual("architect" in self.merton.due(), expected, (share, hours))

    def test_a_pacer_that_raises_leaves_the_schedule_alone(self):
        def broken():
            raise RuntimeError("no pacer")

        self.merton.pace = broken
        self.ledger.append("ops.started", {"release": "test"})
        self.merton.run("teacher")
        self.clock.advance(11 * 3600)
        self.assertNotIn("teacher", self.merton.due())
        self.clock.advance(2 * 3600)
        self.assertIn("teacher", self.merton.due())


class WhereANewStrategyIsWorthWriting(unittest.TestCase):
    """Twice on Sept 20, 2026 the architect declined with "every specialty is occupied" while
    twenty-six agents across the floor had never placed a single order. An occupied desk full of
    agents that cannot trade is the emptiest thing on the floor, and the brief never said so."""

    def test_the_brief_sends_him_at_the_worst_evidence_not_the_empty_corner(self):
        from league.merton import BRIEFS

        brief = BRIEFS["architect"]
        self.assertIn("barren_agents", brief)
        self.assertIn("losing_agents", brief)
        self.assertIn("having members is not a reason to leave it alone", brief)

    def test_a_desk_reports_how_its_members_are_really_faring(self):
        from types import SimpleNamespace

        from league.merton import _how_the_desk_is_doing

        record = {"idle": {"active_blocks": 0, "mean_growth": 0.0},
                  "loser": {"active_blocks": 9, "mean_growth": -0.004},
                  "winner": {"active_blocks": 6, "mean_growth": 0.003},
                  "elsewhere": {"active_blocks": 40, "mean_growth": 0.09}}
        house = SimpleNamespace(
            registry=SimpleNamespace(living=lambda: [SimpleNamespace(id=a, niche="d1" if a != "elsewhere" else "d2") for a in record]),
            standing_of=lambda agent_id: record[agent_id])
        self.assertEqual(_how_the_desk_is_doing(house, "d1"),
                         {"barren_agents": 1, "trading_agents": 2, "losing_agents": 1, "best_mean_growth": 0.003})
        self.assertEqual(_how_the_desk_is_doing(house, "nobody"),
                         {"barren_agents": 0, "trading_agents": 0, "losing_agents": 0, "best_mean_growth": None})


class TheOperatorReadsTheRealBounds(unittest.TestCase):
    """This brief named `inference_daily_cap_usd (0.5-10)` in its own text. When the checker's
    bound was raised to 25 and the cap set to 20, the operator went on reading its brief, proposed
    the same reduction three times, and one of them merged at 11:36 on Sept 20, 2026 -- throttling
    the floor's research below what the owner's budget funds. Two places held the same number and
    they disagreed."""

    def test_the_brief_carries_no_bound_of_its_own(self):
        from league.merton import BRIEFS

        brief = BRIEFS["operator"]
        self.assertIn("permitted_dials", brief)
        self.assertNotIn("(0.5-10)", brief)
        self.assertNotIn("(30-600)", brief)

    def test_the_operator_is_shown_the_checkers_bounds_and_the_live_config(self):
        from types import SimpleNamespace

        from league.ci import CONFIG_DIALS
        from league.merton import evidence_from

        house = SimpleNamespace(
            registry=SimpleNamespace(living=lambda: []),
            commons=SimpleNamespace(blocked_requests=lambda **kw: []),
            ledger=SimpleNamespace(read=lambda **kw: []),
            evaluator=SimpleNamespace(blocks=lambda _: [], rung=lambda _: 1),
            economy=SimpleNamespace(balance=lambda _: 0),
            books={}, budget=None, pacer=SimpleNamespace(report=lambda: {}, running=lambda: False),
            settings=SimpleNamespace(real_money=False), registry_path=None)
        shown = evidence_from(house)("operator")
        self.assertEqual(set(shown["permitted_dials"]), set(CONFIG_DIALS))
        for key, (low, high) in CONFIG_DIALS.items():
            self.assertEqual(shown["permitted_dials"][key], {"min": low, "max": high})
        self.assertIn("inference_daily_cap_usd", shown["config"])
        self.assertNotIn("real_money", shown["permitted_dials"])


class DesignerSourceAndRuntime(unittest.TestCase):
    def test_temporary_burst_settings_are_not_presented_as_the_repository_file(self):
        from types import SimpleNamespace
        from league.economy import load_game
        from league.merton import evidence_from

        game=load_game();game['economy']['fork_threshold_usd']='2.00'
        game['economy']['epoch_seconds']=3600
        house=SimpleNamespace(
            game=game, registry=SimpleNamespace(living=lambda: [],dead=lambda: []),
            commons=SimpleNamespace(blocked_requests=lambda **kw: []),
            ledger=SimpleNamespace(read=lambda **kw: []),
            evaluator=SimpleNamespace(blocks=lambda _: [],rung=lambda _: 1),
            economy=SimpleNamespace(balance=lambda _: 0), books={},budget=None,
            pacer=SimpleNamespace(report=lambda: {},running=lambda: False),
            settings=SimpleNamespace(real_money=False),registry_path=None)
        shown=evidence_from(house)('designer')
        self.assertEqual(shown['game'],load_game())
        self.assertEqual(shown['active_game']['economy']['epoch_seconds'],3600)
        self.assertNotEqual(shown['game']['economy']['epoch_seconds'],3600)
        house._burst = {'id': 'night', 'ends': 2000}
        house.clock = lambda: 1500
        shown = evidence_from(house)('designer')
        self.assertEqual(shown['learning_window']['remaining_seconds'], 500)
        from league.constitution import CONSTITUTION
        self.assertEqual(shown['qualification_policy']['micro']['min_active_blocks'],
                         CONSTITUTION['ladder']['micro']['min_active_blocks'])  # 3 since swing and bunt
        self.assertEqual(shown['qualification_policy']['completed_exposures']['min_episodes'], 10)
        self.assertIsNone(shown['live_pilot'])


class NoBriefMayCarryANumberTheCheckerOwns(unittest.TestCase):
    """Three times on Sept 20, 2026 one number lived in two places and they drifted apart in
    silence: the pacer's Sail allowance against the provider's fixed floor cap (research stopped
    mid-morning); the updater's judge against GitHub's (no commit could reach the box); and the
    operator's brief against the checker's bounds (a merged pull request put the cap back and
    throttled the floor). Each time the second copy was the one nobody thought to update.

    A brief is prose a model reasons from. Any threshold written into it is a copy of a number the
    code enforces, and the code will move first."""

    def test_no_brief_states_a_range_for_a_dial_the_checker_bounds(self):
        import re

        from league.ci import CONFIG_DIALS
        from league.merton import BRIEFS

        offences = []
        for role, brief in BRIEFS.items():
            for dial in CONFIG_DIALS:
                # "tick_seconds (30-600)", "inference_daily_cap_usd 0.5 to 10", and the like
                window = brief[brief.find(dial):brief.find(dial) + 60] if dial in brief else ""
                if window and re.search(r"[\d.]+\s*(?:-|to|–)\s*[\d.]+", window):
                    offences.append(f"{role}: {window.strip()[:60]}")
        self.assertEqual(offences, [], "a brief must read the checker's bounds, never restate them")

    def test_the_constitutions_money_thresholds_are_not_restated_either(self):
        from league.constitution import CONSTITUTION
        from league.merton import BRIEFS, CONSULT

        owned = {str(CONSTITUTION["tuition"]["max_loss_usd"]), str(CONSTITUTION["rungs"]["2"]["stake_usd"]),
                 str(CONSTITUTION["budgets"]["expedition"]["sail_usd"])}
        for name, text in list(BRIEFS.items()) + [("consult", CONSULT)]:
            for value in owned:
                self.assertNotIn(f"${value} ", text, f"{name} restates a constitutional amount the code owns")
