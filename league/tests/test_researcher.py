"""The research loop: what a specialist can look at, and what it remembers.

A scripted provider stands in for the Sail model: each turn it makes the tool calls the test
wrote down, so what is tested is the House's side: the tools, the charges, the journal.
"""

import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from league.agents import Registry
from league.commons import Commons
from league.economy import Economy
from league.ledger import Ledger
from league.researcher import Researcher, TOOLS, _trim
from league.tests.fakes import Clock

D = Decimal
CODE = 'NEEDS = {"venue": "kalshi", "horizon": "day", "style": "t", "series": ["KXNFLGAME"], "max_hours_to_close": 30, "wake_minutes": 60}\nPARAMS = {"notional_usd": 10.0}\n\ndef decide(ctx):\n    return {"intents": [], "thought": "x"}\n'


class Script:
    """`respond` plays back one list of (tool, arguments) per turn and records what it was shown."""

    def __init__(self, turns):
        self.turns, self.seen, self.kwargs = list(turns), [], []

    def respond(self, profile, conversation, **kwargs):
        self.seen.append(json.loads(json.dumps(conversation, default=str)))
        self.kwargs.append({"profile": profile, **kwargs})
        calls = self.turns.pop(0) if self.turns else [("finish", {"summary": "done"})]
        return SimpleNamespace(cost_usd="0.01", output_items=[{"role": "assistant", "content": "ok"}], output_text="thinking", status="completed", incomplete=False,
                               function_calls=[SimpleNamespace(name=n, arguments=a, call_id=f"c{i}", error=None) for i, (n, a) in enumerate(calls)])


class ResearchCase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.clock = Clock()
        self.ledger = Ledger(Path(self.dir.name) / "l.sqlite", clock=self.clock)
        self.registry = Registry(self.ledger)
        self.economy = Economy(self.ledger, clock=self.clock)
        self.parent = self.registry.born(name="football-favorites", family="sports-favorites", code=CODE, needs={"venue": "kalshi", "horizon": "day", "style": "t"}, specialty="kalshi-sports")
        self.child = self.registry.born(name="football-favorites", family="sports-favorites", code=CODE, needs={"venue": "kalshi", "horizon": "day", "style": "t"}, parent=self.parent.id, specialty="kalshi-sports")
        for agent in (self.parent, self.child):
            self.economy.grant(agent.id, "5", "test")
        self.replays = []

    def tearDown(self):
        self.ledger.close()
        self.dir.cleanup()

    def researcher(self, turns, **kw):
        self.script = Script(turns)
        return Researcher(
            ledger=self.ledger, provider=self.script, commons=Commons(self.ledger), economy=self.economy, rules="THE GAME", contract="THE CONTRACT",
            run_replay=lambda agent, code: self.replays.append(code) or {"passed": False, "numbers": {"reasons": ["lost"], "trades": 43}, "digest": {"all": {"trades": 43, "wins": 38, "losses": 7}}},
            settings={"max_turns": 6, "profile": "pro_flex", "reasoning_effort": "medium"}, clock=self.clock,
            specialty=lambda agent: "YOUR SPECIALTY: sports results", lineage=self.registry.lineage, **kw)

    def first_prompt(self):
        return self.script.seen[0][1]["content"]

    def tool_output(self, turn, index=0):
        outputs = [item for item in self.script.seen[turn] if isinstance(item, dict) and item.get("type") == "function_call_output"]
        return json.loads(outputs[index]["output"])


class Journal(ResearchCase):
    def test_a_first_pass_is_told_its_journal_is_empty_and_to_write_in_it(self):
        self.researcher([]).research(self.parent, {}, session="s1")
        self.assertIn("YOUR JOURNAL is empty", self.first_prompt())
        self.assertIn("YOUR SPECIALTY: sports results", self.first_prompt())

    def test_what_it_writes_to_itself_comes_back_at_the_start_of_every_pass(self):
        r = self.researcher([[("journal_write", {"text": "Resting bids during a match get picked off on goals: enter before kickoff only."})], [("finish", {"summary": "Pre-game entries only from now on."})]])
        r.research(self.parent, {}, session="s1")
        self.researcher([]).research(self.parent, {}, session="s2")
        prompt = self.first_prompt()
        self.assertIn("picked off on goals", prompt)
        self.assertIn("Pre-game entries only", prompt)  # the conclusion of a pass is remembered too
        self.assertLess(prompt.index("picked off"), prompt.index("Pre-game entries"))  # oldest first

    def test_a_child_inherits_its_parents_journal_and_a_stranger_does_not(self):
        self.researcher([[("journal_write", {"text": "College favourites under 5,000 contracts of volume never fill before kickoff."})]]).research(self.parent, {}, session="s1")
        self.researcher([]).research(self.child, {}, session="s2")
        self.assertIn(f"{self.parent.id}] College favourites", self.first_prompt())
        stranger = self.registry.born(name="weather-no", family="kalshi-favorites", code=CODE, needs={"venue": "kalshi", "horizon": "day", "style": "t"}, specialty="kalshi-weather")
        self.economy.grant(stranger.id, "5", "test")
        self.researcher([]).research(stranger, {}, session="s3")
        self.assertNotIn("College favourites", self.first_prompt())

    def test_the_journal_is_on_the_ledger_so_it_survives_a_restart_and_its_authors_death(self):
        self.researcher([[("journal_write", {"text": "Totals over 5.5 lost 3 of 25 pre-game: the edge is thinner than the 93-cent price."})]]).research(self.parent, {}, session="s1")
        self.registry.died(self.parent.id, "credits")
        fresh = Researcher(ledger=self.ledger, provider=None, commons=Commons(self.ledger), economy=self.economy, rules="", contract="",
                           run_replay=lambda a, c: {}, settings={}, lineage=Registry(self.ledger).lineage)
        self.assertEqual([row["text"][:20] for row in fresh.journal(self.child.id)], ["Totals over 5.5 lost"])

    def test_the_journal_keeps_the_newest_entries_and_refuses_a_stub(self):
        r = self.researcher([[("journal_write", {"text": "ok"})]] + [[("journal_write", {"text": f"note number {i:02d} with enough words to keep"})] for i in range(5)])
        r.research(self.parent, {}, session="s1")
        self.assertIn("at least a sentence", self.tool_output(1)["error"])
        rows = r.journal(self.parent.id, entries=3)
        self.assertEqual([row["text"][:14] for row in rows], ["note number 02", "note number 03", "note number 04"])  # six turns: a stub and five notes


class Looking(ResearchCase):
    def test_it_can_see_what_its_strategy_sees(self):
        view = {"now": "x", "cash": 200.0, "params": {"secret": 1}, "markets": [{"market": f"M{i}", "volume_24h": i} for i in range(60)], "positions": []}
        r = self.researcher([[("markets_now", {})]], look=lambda agent: view)
        r.research(self.parent, {}, session="s1")
        shown = self.tool_output(1)
        self.assertEqual((len(shown["markets"]), shown["markets"][0]["market"], shown["markets_shown"]), (40, "M59", "40 busiest of 60"))
        self.assertEqual(shown["cash"], 200.0)
        self.assertNotIn("params", shown)

    def test_a_venue_that_is_down_is_an_answer_not_a_crash(self):
        r = self.researcher([[("markets_now", {})]], look=lambda agent: 1 / 0)
        out = r.research(self.parent, {}, session="s1")
        self.assertIn("could not be read", self.tool_output(1)["error"])
        self.assertEqual(out.reason, "finished")

    def test_trim_keeps_the_nearest_contracts_and_the_latest_bars(self):
        out = _trim({"chain": [{"occ": str(i)} for i in range(90)], "bars": {"F": [{"c": i} for i in range(200)]}, "memory": {"x": 1}})
        self.assertEqual((len(out["chain"]), len(out["bars"]["F"]), out["bars"]["F"][-1]), (40, 30, {"c": 199}))
        self.assertNotIn("memory", out)

    def test_a_replay_answers_with_where_it_won_and_lost(self):
        r = self.researcher([[("replay", {"code": CODE, "purpose": "pre-game only"})]])
        out = r.research(self.parent, {}, session="s1")
        answer = self.tool_output(1)
        self.assertEqual((answer["passed"], answer["digest"]["all"]["losses"], out.trials), (False, 7, 1))

    def test_every_tool_the_model_is_offered_is_one_the_house_runs(self):
        r = self.researcher([[(tool["name"], {}) for tool in TOOLS if tool["name"] not in ("finish", "web_search")]], look=lambda agent: {})
        r.research(self.parent, {}, session="s1")
        outputs = [json.loads(item["output"]) for item in self.script.seen[1] if isinstance(item, dict) and item.get("type") == "function_call_output"]
        self.assertFalse([o for o in outputs if "no such tool" in str(o.get("error"))])

    def test_the_pass_runs_on_the_games_profile_and_is_charged_to_the_agent(self):
        before = self.economy.balance(self.parent.id)
        self.researcher([]).research(self.parent, {}, session="s1")
        self.assertEqual((self.script.kwargs[0]["profile"], self.script.kwargs[0]["reasoning_effort"]), ("pro_flex", "medium"))
        self.assertEqual(before - self.economy.balance(self.parent.id), D("0.01"))


if __name__ == "__main__":
    unittest.main()


class Truncated(ResearchCase):
    """An answer cut short by the output budget (reasoning tokens included) still holds work."""

    def script(self, turns, *, cut=2, **kw):
        """A provider whose first `cut` answers are cut short by the output budget."""
        r = self.researcher(turns, **kw)
        original = self.script.respond

        def respond(profile, conversation, **kwargs):
            reply = original(profile, conversation, **kwargs)
            reply.incomplete = len(self.script.seen) <= cut
            reply.incomplete_reason = "max_output_tokens"
            return reply

        self.script.respond = respond
        return r

    def test_the_tool_calls_a_cut_short_answer_made_are_still_run(self):
        r = self.script([[("journal_write", {"text": "The chain's spreads are widest in the first ten minutes."})],
                         [("library_search", {"query": "spreads"})],
                         [("finish", {"summary": "Wrote what I found about spreads at the open."})]], cut=2)
        out = r.research(self.parent, {}, session="s1")
        self.assertEqual((out.reason, out.turns), ("finished", 3))
        self.assertIn("widest in the first ten minutes", self.researcher([]).journal(self.parent.id)[0]["text"])
        cut = [e.payload for e in self.ledger.iter(kinds="agent.research") if e.payload.get("tool") == "truncated"]
        self.assertEqual([(row["reason"], row["calls"]) for row in cut], [("max_output_tokens", ["journal_write"]), ("max_output_tokens", ["library_search"])])

    def test_an_answer_cut_short_with_nothing_in_it_ends_the_pass_and_says_why(self):
        r = self.script([[]], cut=9)
        out = r.research(self.parent, {}, session="s1")
        self.assertEqual((out.reason, out.turns), ("provider: max_output_tokens", 1))

    def test_three_cut_answers_end_the_pass_however_much_they_carried(self):
        r = self.script([[("library_search", {"query": "x"})]] * 6, cut=9)
        out = r.research(self.parent, {}, session="s1")
        self.assertEqual((out.reason, out.turns), ("provider: max_output_tokens", 3))


class Hiring(ResearchCase):
    """An agent hires Merton with its own credits: what a good record buys is better thinking."""

    class FakeMerton:
        def __init__(self, reply=None, cost="0.42"):
            self.reply = reply or {"answer": "Your idea is structurally dead: the average move is under the round trip.", "code": "", "confidence": "high"}
            self.cost, self.seen = cost, []

        def consult(self, agent, question, evidence, *, contract):
            self.seen.append((agent.id, question, evidence, contract))
            return {**self.reply, "cost_usd": self.cost}

    def hire(self, question="Is my idea structurally dead, or is it the parameters?", merton=None, settings=None, budget=True, turns=None):
        self.merton = merton or self.FakeMerton()
        r = self.researcher(turns if turns is not None else [[("ask_merton", {"question": question})]],
                            merton=self.merton, merton_settings=settings or {"min_credits_usd": "1.00", "cooldown_hours": 24},
                            house_budget=lambda: budget)
        return r, r.research(self.parent, {}, session="s1")

    def test_it_pays_from_its_own_credits_and_is_given_everything_it_knows(self):
        before = self.economy.balance(self.parent.id)
        r, out = self.hire()
        answer = self.tool_output(1)
        self.assertIn("structurally dead", answer["answer"])
        self.assertEqual((answer["code"], answer["cost_usd"]), (None, "0.42"))
        self.assertEqual(before - self.economy.balance(self.parent.id), D("0.42") + D("0.02"))  # his fee, and the two turns of the pass itself
        _, question, evidence, contract = self.merton.seen[0]
        self.assertIn("structurally dead", question)
        self.assertEqual((evidence["strategy_file"], evidence["agent"]["id"]), (self.parent.code, self.parent.id))
        self.assertEqual(evidence["specialty"], "YOUR SPECIALTY: sports results")
        self.assertEqual(contract, "THE CONTRACT")
        row = [e.payload for e in self.ledger.iter(kinds="credit.charge", agent=self.parent.id) if e.payload["what"] == "merton's time"]
        self.assertEqual(row[0]["usd"], "0.42000000")

    def test_a_poor_agent_cannot_afford_him(self):
        self.economy.charge(self.parent.id, "4.20", "test")  # $0.80 left
        r, out = self.hire()
        self.assertIn("not hired below 1.00", self.tool_output(1)["error"])
        self.assertEqual(self.merton.seen, [])

    def test_once_a_day(self):
        r, out = self.hire()
        self.assertIn("answer", self.tool_output(1))
        r2, out2 = self.hire()
        self.assertIn("once every 24h", self.tool_output(1)["error"])
        self.clock.advance(24 * 3600 + 1)
        r3, out3 = self.hire()
        self.assertIn("answer", self.tool_output(1))

    def test_the_firms_own_budget_still_binds(self):
        r, out = self.hire(budget=False)
        self.assertIn("frontier budget for today is spent", self.tool_output(1)["error"])
        self.assertEqual(self.merton.seen, [])

    def test_a_strategy_file_he_writes_is_the_agents_to_replay(self):
        merton = self.FakeMerton({"answer": "Here is a better file.", "code": CODE, "confidence": "medium"})
        r, out = self.hire(merton=merton, turns=[[("ask_merton", {"question": "Write me something that trades before kickoff only."})],
                                                 [("replay", {"code": CODE, "purpose": "Merton's file"})]])
        self.assertEqual(self.tool_output(1)["code"], CODE)
        self.assertIn("a trial in your line", self.tool_output(1)["note"])
        self.assertEqual((out.consulted, out.trials), (CODE, 1))

    def test_a_file_that_fails_the_safety_check_is_not_his_to_hand_over(self):
        merton = self.FakeMerton({"answer": "Try this.", "code": "import os\ndef decide(ctx):\n    return {}\n", "confidence": "low"})
        r, out = self.hire(merton=merton)
        answer = self.tool_output(1)
        self.assertIsNone(answer["code"])
        self.assertIn("refused by the safety check", answer["note"])
        self.assertEqual(out.consulted, "")

    def test_a_question_that_is_not_one_costs_nothing(self):
        r, out = self.hire(question="help")
        self.assertIn("something specific", self.tool_output(1)["error"])
        self.assertEqual(self.merton.seen, [])

    def test_what_merton_says_the_agent_cannot_work_without_goes_to_the_toolsmiths_queue(self):
        merton = self.FakeMerton({"answer": "You cannot price this without the score.", "code": "",
                                  "tool": {"name": "live_score", "description": "the running score of a game in play"}, "confidence": "high"})
        r, out = self.hire(merton=merton)
        self.assertEqual(self.tool_output(1)["tool_requested"], "live_score")
        queued = r.commons.open_requests()
        self.assertEqual(queued[0]["name"], "live_score")
        self.assertIn("Merton, for " + self.parent.id, queued[0]["description"])

    def test_a_rung_that_has_climbed_may_have_him_oftener(self):
        settings = {"min_credits_usd": "1.00", "cooldown_hours": 24, "cooldown_hours_by_rung": {"1": 24, "2": 8}}
        rungs = {self.parent.id: 1}
        self.merton = self.FakeMerton()
        r = self.researcher([[("ask_merton", {"question": "Is my idea structurally dead or is it the band?"})]],
                            merton=self.merton, merton_settings=settings, house_budget=lambda: True, rung=lambda a: rungs[a])
        r.research(self.parent, {}, session="s1")
        self.clock.advance(9 * 3600)
        r2 = self.researcher([[("ask_merton", {"question": "Is my idea structurally dead or is it the band?"})]],
                             merton=self.merton, merton_settings=settings, house_budget=lambda: True, rung=lambda a: rungs[a])
        r2.research(self.parent, {}, session="s2")
        self.assertIn("once every 24h", self.tool_output(1)["error"])
        rungs[self.parent.id] = 2  # it reached real money
        r3 = self.researcher([[("ask_merton", {"question": "Is my idea structurally dead or is it the band?"})]],
                             merton=self.merton, merton_settings=settings, house_budget=lambda: True, rung=lambda a: rungs[a])
        r3.research(self.parent, {}, session="s3")
        self.assertIn("answer", self.tool_output(1))


class Acting(ResearchCase):
    """A pass that reasons until its budget is gone and calls no tool has bought nothing.

    Measured Sept 19, 2026: nine of fifteen passes ended as `max_output_tokens` at turn one or two
    with no tool call at all, each costing about three cents.
    """

    def test_the_research_loop_requires_a_tool_call_when_the_game_file_says_so(self):
        r = self.researcher([])
        r.settings.update(tool_choice="required", max_output_tokens=32000)
        r.research(self.parent, {}, session="s1")
        self.assertEqual((self.script.kwargs[0]["tool_choice"], self.script.kwargs[0]["max_output_tokens"]), ("required", 32000))

    def test_it_asks_for_nothing_special_by_default(self):
        r = self.researcher([])
        r.settings.pop("tool_choice", None)
        r.research(self.parent, {}, session="s1")
        self.assertEqual(self.script.kwargs[0]["tool_choice"], "auto")

    def test_the_shipped_game_file_requires_one(self):
        from league.economy import load_game

        research = load_game()["research"]
        self.assertEqual((research["tool_choice"], research["max_output_tokens"]), ("required", 32000))
