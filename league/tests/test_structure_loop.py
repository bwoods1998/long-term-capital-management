"""The learning loop for structures (G-LOOP of the options-desk run's Wave 2, Sept 25, 2026).

Evidence (the run record, docs/runs/2026-09-25-options-desk.md). An in-place edit was replayed at half
notional ($37.50 order cap), where a $1-wide condor cannot be opened (row S3). At 15:34:48Z krasker-22
"rewrote itself: its own rules had not fired in 11 wakes ... this file at least trades", adopting a
program whose replay had FAILED at 15:34:26Z, and at 15:42:56Z opened a CCL condor whose stop then tried
to buy it back at 1.46 on $0.50 wings (watch 16:31Z). `Lab._desk` returned None for the options desk, so
the lab never bred a structure program (row S3's note for after 20:05Z).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

from league.tests.test_options import STRUCTURE_AGENT, StructureHouseCase

#: A structure program whose width and deltas are bounded knobs (as the founders declare them).
BOUNDED = STRUCTURE_AGENT.replace(
    '"style": "test-structures"}',
    '"style": "test-structures", "parameter_rules": {"bounds": {"width": [1, 5], "entry_delta": [0.05, 0.35]}}}').replace(
    'PARAMS = {"structure": "iron_condor", "width": 1.0}', 'PARAMS = {"structure": "iron_condor", "width": 1.0, "entry_delta": 0.15}')
#: What a replay that opened nothing returns (the edit's replay is judged by the gate as any other).
NOTHING = {"ok": True, "trades": 0, "blocks": [], "return_pct": 0.0, "max_drawdown": 0.0, "fees_usd": 0.0}


class TheEditReplay(StructureHouseCase):
    """X1's `edit_params` replays a structure agent's edit at the full practice caps: the program as it trades."""

    def setUp(self):
        super().setUp()
        self.replays = []

        def replay(agent, code, params, tape, *, stake, limits, timeout=600):
            self.replays.append({"params": dict(params), "stake": stake, "limits": dict(limits)})
            return SimpleNamespace(result=dict(NOTHING), seconds=0.5, created=False)

        for patcher in (mock.patch.object(self.house.sandbox, "replay", side_effect=replay),
                        mock.patch.object(self.house, "tape_for", return_value=("options:test", {"venue": "alpaca", "asset_class": "option", "steps": []})),
                        mock.patch.object(self.house, "_replayable", return_value=True)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_a_structure_agents_edit_is_replayed_at_the_full_practice_caps(self):
        agent = self.house.spawn("krasker", "options-structures-test", BOUNDED, reason="test", specialty="alpaca-options")
        self.house.evaluator.seat(agent.id, 1, "practising on the structure book")  # as a founder is seated
        self.assertTrue(self.house.is_structure_agent(agent))
        result = self.house._edit_replay(self.house.registry.get(agent.id), {"width": 2.0})
        self.assertNotIn("error", result)
        (replay,) = self.replays
        # $200 stake, $100 a position, $75 an order: a $1 condor held at 0.62 ($62) fits, as it does on its book.
        self.assertEqual((replay["params"]["width"], replay["stake"], replay["limits"]),
                         (2.0, 200.0, {"max_position_usd": 100.0, "max_order_usd": 75.0}))
        self.assertEqual((result["numbers"]["stake_usd"], result["numbers"]["max_order_usd"]), (200.0, 75.0))
        look = self.house.ledger.last("agent.research", agent=agent.id).payload
        self.assertEqual((look["tool"], look["stake_usd"], look["max_order_usd"]), ("edit_replay", 200.0, 75.0))
        self.assertIn("the full practice caps", self.house._entries_standing(agent)["tools"])

    def test_any_other_agent_is_still_replayed_at_half_notional(self):
        from league.tests.test_entry_controls import SIZED

        agent = self.seated("sized", SIZED)
        self.assertFalse(self.house.is_structure_agent(agent))
        result = self.house._edit_replay(self.house.registry.get(agent.id), {"notional_usd": 20})
        self.assertNotIn("error", result)
        (replay,) = self.replays
        self.assertEqual((replay["stake"], replay["limits"]), (100.0, {"max_position_usd": 50.0, "max_order_usd": 37.5}))
        self.assertEqual((result["numbers"]["stake_usd"], result["numbers"]["max_order_usd"]), (100.0, 37.5))
        self.assertIn("half notional", self.house._entries_standing(agent)["tools"])


#: What krasker-22 took at 15:34:48Z: another structure program, whose replay traded (17 trades) and failed.
REWRITE = STRUCTURE_AGENT.replace("test-structures", "test-credit-spread").replace('"iron_condor"', '"credit_vertical"')


class TheStuckRewrite(StructureHouseCase):
    """The stuck-agent rule (`House._commit_research`) never puts a structure program that failed its replay to work."""

    def commit(self, agent, code, *, passed, barren=11, trades=17):
        needs = dict(agent.needs, style="test-credit-spread", structures=True)
        candidate = {"code": code, "needs": needs, "params": {"structure": "credit_vertical", "width": 1.0}, "passed": passed,
                     "purpose": "a short-dated defined-risk credit spread: this file at least trades", "numbers": {"trades": trades}}
        with mock.patch.object(self.house, "idle_run", return_value={"barren": barren}):
            return self.house._commit_research(agent.id, self.house._generation(agent.id), SimpleNamespace(candidate=candidate, consulted=""))

    def test_a_stuck_structure_agent_keeps_its_rules_when_the_new_programs_replay_failed(self):
        agent = self.structure_agent()
        was = agent.code_sha256
        self.assertIsNone(self.commit(agent, REWRITE, passed=False))
        self.assertEqual(self.house.registry.get(agent.id).code_sha256, was)
        self.assertEqual(self.house.ledger.count(kinds="agent.strategy", agent=agent.id), 0)
        row = self.house.ledger.last("agent.research", agent=agent.id).payload
        self.assertEqual((row["tool"], row["status"]), ("candidate", "not_adopted"))
        self.assertIn("had not fired in 11 wakes, but a structure program trades only once its replay passes", row["reason"])

    def test_a_single_leg_agent_is_not_rewritten_into_a_failed_structure_program_either(self):
        from league.tests.test_options_desk import SINGLE_LEG

        agent = self.house.spawn("krasker", "options-single-test", SINGLE_LEG, reason="test", specialty="alpaca-options")
        self.assertFalse(self.house.is_structure_agent(agent))
        was = agent.code_sha256
        self.assertIsNone(self.commit(agent, REWRITE, passed=False))
        self.assertEqual(self.house.registry.get(agent.id).code_sha256, was)
        self.assertEqual(self.house.ledger.last("agent.research", agent=agent.id).payload["status"], "not_adopted")

    def test_a_structure_program_that_passed_its_replay_is_adopted_as_before(self):
        agent = self.structure_agent()
        self.assertIsNone(self.commit(agent, REWRITE, passed=True))
        current = self.house.registry.get(agent.id)
        self.assertEqual(current.code, REWRITE)
        row = self.house.ledger.last("agent.strategy", agent=agent.id).payload
        self.assertIs(row["passed_replay"], True)

    def test_a_failed_structure_program_that_is_not_stuck_is_dropped_silently_as_any_other(self):
        agent = self.structure_agent()
        was = agent.code_sha256
        self.assertIsNone(self.commit(agent, REWRITE, passed=False, barren=3))
        self.assertEqual(self.house.registry.get(agent.id).code_sha256, was)
        self.assertEqual([e.payload.get("status") for e in self.house.ledger.iter(kinds="agent.research", agent=agent.id)], [])


if __name__ == "__main__":
    import unittest

    unittest.main()
