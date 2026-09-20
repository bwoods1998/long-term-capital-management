"""The research loop: what a specialist can look at, and what it remembers.

A scripted provider stands in for the Sail model: each turn it makes the tool calls the test
wrote down, so what is tested is the House's side: the tools, the charges, the journal.
"""

import json
import asyncio
import concurrent.futures
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
from league.sandbox import SandboxError
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
            ledger=self.ledger, provider=self.script, commons=Commons(self.ledger, clock=self.clock), economy=self.economy, rules="THE GAME", contract="THE CONTRACT",
            run_replay=lambda agent, code: self.replays.append(code) or {"passed": False, "numbers": {"reasons": ["lost"], "trades": 43}, "digest": {"all": {"trades": 43, "wins": 38, "losses": 7}}},
            clock=self.clock, specialty=lambda agent: "YOUR SPECIALTY: sports results", lineage=self.registry.lineage,
            **{"settings": {"max_turns": 6, "profile": "pro_flex", "reasoning_effort": "medium"}, **kw})

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
        fresh = Researcher(ledger=self.ledger, provider=None, commons=Commons(self.ledger, clock=self.clock), economy=self.economy, rules="", contract="",
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


class CandidateRetention(ResearchCase):
    """Trying another idea must not discard code the House can already put to work."""

    def run_candidates(self, outcomes):
        codes = [CODE + f"\n# candidate {index}\n" for index in range(len(outcomes))]
        researcher = self.researcher(
            [[("replay", {"code": code, "purpose": f"idea {index}"})] for index, code in enumerate(codes)]
            + [[("finish", {"summary": "Keep the improvement that can be used."})]]
        )
        results = iter(outcomes)
        researcher.run_replay = lambda agent, code: next(results)
        return researcher.research(self.parent, {}, session="candidates"), codes

    def test_a_later_failed_replay_keeps_the_passing_candidate(self):
        out, codes = self.run_candidates([
            {"passed": True, "numbers": {"trades": 24}},
            {"passed": False, "numbers": {"trades": 40, "reasons": ["lost"]}},
        ])
        self.assertEqual(out.candidate["code"], codes[0])
        self.assertTrue(out.candidate["passed"])
        self.assertEqual(out.trials, 2)
        self.assertFalse(self.tool_output(2, 1)["passed"])  # the model still sees the failed result
        retained = [row.payload for row in self.ledger.iter(kinds="agent.research") if row.payload.get("status") == "retained"]
        self.assertEqual(len(retained), 1)
        self.assertEqual(retained[0]["_candidate"], out.candidate)
        self.assertEqual(retained[0]["session"], "candidates")

    def test_a_selected_candidate_survives_process_exit_before_the_summary(self):
        researcher = self.researcher([
            [("replay", {"code": CODE, "purpose": "passing idea"})],
            [("replay", {"code": CODE + "\n# next idea", "purpose": "another idea"})],
        ])

        def replay(agent, code):
            if code != CODE:
                raise SystemExit("a worker restarted")
            return {"passed": True, "needs": agent.needs, "params": agent.params, "numbers": {"trades": 24}}

        researcher.run_replay = replay
        with self.assertRaises(SystemExit):
            researcher.research(self.parent, {}, session="interrupted")
        saved = [row.payload for row in self.ledger.iter(kinds="agent.research") if row.payload.get("status") == "retained"]
        self.assertEqual(saved[0]["_candidate"]["code"], CODE)
        self.assertTrue(saved[0]["_candidate"]["passed"])
        self.assertFalse([row for row in self.ledger.iter(kinds="agent.research") if row.payload.get("tool") == "summary"])

    def test_a_failed_candidate_that_trades_survives_a_later_idle_candidate(self):
        out, codes = self.run_candidates([
            {"passed": False, "numbers": {"trades": 3}},
            {"passed": False, "numbers": {"trades": 0}},
        ])
        self.assertEqual(out.candidate["code"], codes[0])
        self.assertFalse(out.candidate["passed"])
        self.assertEqual(out.candidate["numbers"]["trades"], 3)

    def test_a_later_passing_candidate_replaces_a_failure(self):
        out, codes = self.run_candidates([
            {"passed": False, "numbers": {"trades": 3}},
            {"passed": True, "numbers": {"trades": 24}},
        ])
        self.assertEqual(out.candidate["code"], codes[1])
        self.assertTrue(out.candidate["passed"])

    def test_the_latest_refinement_wins_within_the_same_eligibility_class(self):
        for passed, trades in ((True, 24), (False, 3), (False, 0)):
            with self.subTest(passed=passed, trades=trades):
                # Each research session's token charges have durable, distinct identities.
                self.clock.advance(1)
                outcomes = [{"passed": passed, "numbers": {"trades": trades}}] * 2
                codes = [CODE + "\n# before\n", CODE + "\n# after\n"]
                researcher = self.researcher([
                    [("replay", {"code": code, "purpose": "refinement"})] for code in codes
                ])
                results = iter(outcomes)
                researcher.run_replay = lambda agent, code: next(results)
                out = researcher.research(self.parent, {}, session=f"refinement-{passed}-{trades}")
                self.assertEqual(out.candidate["code"], codes[1])

    def test_a_later_replay_error_does_not_erase_a_usable_candidate(self):
        out, codes = self.run_candidates([
            {"passed": True, "numbers": {"trades": 24}},
            {"passed": False, "error": "replay unavailable", "numbers": {}},
        ])
        self.assertEqual(out.candidate["code"], codes[0])
        self.assertEqual(out.reason, "finished")

    def test_a_later_unavailable_box_keeps_the_candidate_and_the_paid_cost(self):
        r = self.researcher([
            [("replay", {"code": CODE, "purpose": "passing idea"})],
            [("replay", {"code": CODE + "\n# next idea", "purpose": "another idea"})],
            [("finish", {"summary": "Keep the earlier passing idea."})],
        ])

        def replay(agent, code):
            if code != CODE:
                raise SandboxError("probe box unavailable")
            return {"passed": True, "needs": agent.needs, "params": agent.params, "numbers": {"trades": 24}}

        r.run_replay = replay
        before = self.economy.balance(self.parent.id)
        out = r.research(self.parent, {}, session="box-failed")
        self.assertEqual(out.candidate["code"], CODE)
        self.assertEqual((out.reason, out.trials), ("finished", 1))
        self.assertEqual(out.cost_usd, D("0.03"))
        self.assertEqual(before - self.economy.balance(self.parent.id), out.cost_usd)
        self.assertIn("probe box unavailable", self.tool_output(2, 1)["error"])
        errors = [row.payload for row in self.ledger.iter(kinds="agent.research") if row.payload.get("tool") == "replay_error"]
        self.assertEqual(len(errors), 1)
        self.assertFalse(errors[0]["counted_as_trial"])
        self.assertTrue(self.ledger.last("agent.research").payload["candidate"])

    def test_replay_cancellation_and_process_exit_still_propagate(self):
        for exception in (asyncio.CancelledError, concurrent.futures.CancelledError, SystemExit):
            with self.subTest(exception=exception.__name__):
                r = self.researcher([[("replay", {"code": CODE, "purpose": "an idea"})]])

                def cancelled(agent, code):
                    raise exception("stop")

                r.run_replay = cancelled
                with self.assertRaises(exception):
                    r.research(self.parent, {}, session=f"cancel-{exception.__module__}-{exception.__name__}")


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

    def test_an_answer_that_thought_until_it_ran_out_is_asked_again_for_the_call_alone(self):
        """Twelve of the floor's first twenty-eight passes died on exactly this, having bought
        nothing: the model filled its whole output budget with reasoning and never reached a tool.
        A bigger budget only buys more reasoning, so the next turn is asked to think less."""
        r = self.script([[], [("finish", {"summary": "got there in the end"})]], cut=1)
        out = r.research(self.parent, {}, session="s1")
        self.assertEqual((out.reason, out.turns), ("finished", 2))
        self.assertEqual([k["reasoning_effort"] for k in self.script.kwargs], ["medium", "low"])
        self.assertIn("ran out of room", json.dumps(self.script.seen[-1], default=str))

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

    def hire(self, question="Is my idea structurally dead, or is it the parameters?", merton=None, settings=None, budget=True,
             turns=None, record=None):
        self.merton = merton or self.FakeMerton()
        self.record = {"active_blocks": 4, "mean_growth": 0.0} if record is None else record
        r = self.researcher(turns if turns is not None else [[("ask_merton", {"question": question})]],
                            merton=self.merton, merton_settings=settings or {"min_credits_usd": "1.00", "cooldown_hours": 24},
                            house_budget=lambda: budget, standing=lambda _: self.record)
        return r, r.research(self.parent, {}, session="s1")

    def test_merton_is_hired_by_traders_and_nobody_else(self):
        """Frontier intelligence is the prize for trading well, never a rebate for existing. An
        agent that has not traded is served by Merton's own roles, which cost it nothing."""
        r, out = self.hire(record={"active_blocks": 0, "mean_growth": 0.0})
        self.assertIn("Merton is hired by traders", self.tool_output(1)["error"])
        self.assertEqual(self.merton.seen, [])

    def test_profit_buys_more_of_him_than_a_rung_does(self):
        settings = {"min_credits_usd": "1.00", "cooldown_hours": 8, "cooldown_hours_by_rung": {"1": 8},
                    "profitable_cooldown_hours_by_rung": {"1": 3}}
        r, out = self.hire(settings=settings, record={"active_blocks": 6, "mean_growth": 0.004})
        self.assertIn("answer", self.tool_output(1))
        self.clock.advance(4 * 3600)
        r, out = self.hire(settings=settings, record={"active_blocks": 6, "mean_growth": 0.004})
        self.assertIn("answer", self.tool_output(1))  # profitable: every three hours
        self.clock.advance(4 * 3600)
        r, out = self.hire(settings=settings, record={"active_blocks": 6, "mean_growth": -0.004})
        self.assertIn("not yet profitable", self.tool_output(1)["error"])  # losing: it waits the eight
        self.clock.advance(5 * 3600)
        r, out = self.hire(settings=settings, record={"active_blocks": 6, "mean_growth": -0.004})
        self.assertIn("answer", self.tool_output(1))

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
        self.assertIn("every 24h", self.tool_output(1)["error"])
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
                            merton=self.merton, merton_settings=settings, house_budget=lambda: True, rung=lambda a: rungs[a],
                            standing=lambda _: {"active_blocks": 4, "mean_growth": 0.0})
        r.research(self.parent, {}, session="s1")
        self.clock.advance(9 * 3600)
        r2 = self.researcher([[("ask_merton", {"question": "Is my idea structurally dead or is it the band?"})]],
                             merton=self.merton, merton_settings=settings, house_budget=lambda: True, rung=lambda a: rungs[a],
                             standing=lambda _: {"active_blocks": 4, "mean_growth": 0.0})
        r2.research(self.parent, {}, session="s2")
        self.assertIn("every 24h", self.tool_output(1)["error"])
        rungs[self.parent.id] = 2  # it reached real money
        r3 = self.researcher([[("ask_merton", {"question": "Is my idea structurally dead or is it the band?"})]],
                             merton=self.merton, merton_settings=settings, house_budget=lambda: True, rung=lambda a: rungs[a],
                             standing=lambda _: {"active_blocks": 4, "mean_growth": 0.0})
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


class TheFlexQueue(ResearchCase):
    """`pro_flex` is cheap because it waits in a queue. When the queue will not serve a turn inside
    the deadline, the whole pass used to be thrown away with everything it had read still in hand."""

    class Timeout(RuntimeError):
        code = "provider_poll_timeout"

    def script(self, fail_turns):
        r = self.researcher([[("library_search", {"query": "x"})], [("finish", {"summary": "done"})]],
                            settings={"max_turns": 6, "profile": "pro_flex", "fast_profile": "pro_asap", "reasoning_effort": "medium"})
        original = self.script.respond
        seen = []

        def respond(profile, conversation, **kwargs):
            seen.append(profile)
            if len(seen) in fail_turns:
                raise TheFlexQueue.Timeout("provider_poll_timeout")
            return original(profile, conversation, **kwargs)

        self.script.respond = respond
        return r, seen

    def test_a_queue_that_will_not_serve_buys_the_priority_tier_for_that_turn(self):
        r, seen = self.script({1})
        out = r.research(self.parent, {}, session="s1")
        self.assertEqual((out.reason, seen), ("finished", ["pro_flex", "pro_asap", "pro_asap"]))
        row = [e.payload for e in self.ledger.iter(kinds="agent.research") if e.payload.get("tool") == "queued"]
        self.assertEqual([(r["was"], r["now"]) for r in row], [("pro_flex", "pro_asap")])

    def test_the_priority_tier_timing_out_too_ends_the_pass(self):
        r, seen = self.script({1, 2})
        out = r.research(self.parent, {}, session="s1")
        self.assertEqual((out.reason, seen), ("provider: provider_poll_timeout", ["pro_flex", "pro_asap"]))


class TheDeskCapDoesNotRatchet(ResearchCase):
    """The provider counts a desk's CUMULATIVE spend for the day against the cap it is handed.
    Handing it the balance alone was a ratchet: every charge lowered the cap and raised the total,
    and once the total passed the balance the agent was locked out until midnight UTC however many
    credits it was later granted. Sept 20, 2026: research on the floor fell to nothing."""

    def test_the_cap_is_what_it_has_spent_today_plus_what_it_still_holds(self):
        self.economy.charge(self.parent.id, "3.00", "an earlier pass today")
        held = self.economy.balance(self.parent.id)
        self.researcher([[("finish", {"summary": "done"})]]).research(self.parent, {}, session="s1")
        cap = Decimal(str(self.script.kwargs[0]["desk_cap_usd_per_day"]))
        self.assertEqual(cap, held + D("3.00"))
        self.assertGreater(cap, D("3.00"))  # strictly above what it has already spent, or it is locked out

    def test_yesterdays_spending_is_not_counted_against_today(self):
        before = self.economy.balance(self.parent.id)
        self.clock.advance(3 * 86400)
        self.economy.charge(self.parent.id, "1.00", "today")
        self.researcher([[("finish", {"summary": "done"})]]).research(self.parent, {}, session="s2")
        self.assertEqual(Decimal(str(self.script.kwargs[0]["desk_cap_usd_per_day"])), before - D("1.00") + D("1.00"))
