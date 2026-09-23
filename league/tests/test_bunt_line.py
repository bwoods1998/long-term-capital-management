"""An agent can see how far its own evidence is from real money (Sept 23, 2026).

The best stock agent, scholes-21, stood at E 0.9987 on 4 closed trades, $4.53 short of the bunt line,
and nothing it was shown said so. The line is the constitution's and the numbers are the allocator's;
the House only reads them back to the agent."""
from decimal import Decimal

from league import allocator
from league.constitution import CONSTITUTION
from league.tests.test_house import BUYER, HouseCase

D = Decimal
LINE = CONSTITUTION["allocator"]


class BuntLine(HouseCase):
    def board(self, agent, **evidence):
        row = {"E": 1.0, "W_paper": 1.0, "W_real": 1.0, "trades": 0, "settled": 0, **evidence}
        self.house.allocator._board = {"enabled": True, "at": "2026-09-23T14:00:00.000Z",
                                       "agents": {agent.id: {"band": "paper", "evidence": row}}}

    def test_the_standing_says_how_far_the_agent_is_from_the_bunt_line(self):
        agent = self.seated()
        self.house.books["alpaca-paper"].stake(agent.id, D("200"), note="test purse")
        self.board(agent, E=0.9987, W_paper=0.99740169, trades=4)
        line = self.house.standing_of(agent.id)["bunt_line"]
        self.assertTrue(line["measured"])
        self.assertEqual((line["bunt_at"], line["bunt_min_trades"]), (LINE["bunt_at"], LINE["bunt_min_trades"]))
        self.assertEqual((line["E"], line["W_paper"], line["W_real"], line["closed_trades"]), (0.9987, 0.99740169, 1.0, 4))
        self.assertAlmostEqual(line["e_short"], LINE["bunt_at"] - 0.9987, places=6)
        self.assertEqual(line["trades_short"], LINE["bunt_min_trades"] - 4)
        # E = W_paper ** 0.5 x W_real: with no real record the line is W_paper = 1.01 ** 2.
        weight = LINE["evidence"]["paper_weight"]
        self.assertAlmostEqual(line["w_paper_needed"], LINE["bunt_at"] ** (1 / weight), places=6)
        gain = LINE["bunt_at"] ** (1 / weight) / 0.99740169 - 1
        self.assertAlmostEqual(line["paper_gain_needed_pct"], 100 * gain, places=3)
        self.assertAlmostEqual(line["paper_gain_needed_usd"], 200 * gain, places=2)
        self.assertFalse(line["at_the_line"])

    def test_the_research_standing_carries_it_too(self):
        agent = self.seated()
        self.board(agent, E=1.02, W_paper=1.0404, trades=6)
        line = self.house._research_standing(agent)["bunt_line"]
        self.assertEqual((line["e_short"], line["trades_short"], line["at_the_line"]), (0.0, 0, True))
        self.assertEqual(line["paper_gain_needed_pct"], 0.0)

    def test_an_agent_on_real_money_is_told_the_line_it_must_hold(self):
        agent = self.seated()
        self.board(agent, E=1.02, W_paper=1.0404, trades=6)
        self.house.allocator._board["agents"][agent.id]["band"] = "bunt"
        line = self.house.standing_of(agent.id)["bunt_line"]
        self.assertTrue(line["on_real_money"])
        self.assertAlmostEqual(line["holds_real_money_down_to_E"], LINE["bunt_at"] * LINE["hysteresis"], places=6)
        self.board(agent, E=1.0, trades=2)
        self.assertNotIn("on_real_money", self.house.standing_of(agent.id)["bunt_line"])

    def test_an_agent_the_allocator_has_not_measured_is_told_so(self):
        agent = self.house.spawn("young", "test-family", BUYER, reason="test")  # rung 0: judged by replay first
        self.assertEqual(self.house.evaluator.rung(agent.id), 0)
        line = self.house.standing_of(agent.id)["bunt_line"]
        self.assertFalse(line["measured"])
        self.assertEqual(line["bunt_min_trades"], LINE["bunt_min_trades"])

    def test_it_is_the_allocators_own_measure_after_a_pass(self):
        agent = self.seated()
        self.house.tick()                 # buys
        self.clock.advance(301)
        self.house.tick()                 # sells: one closed trade
        self.house.allocator.rebalance()
        ev = allocator.evidence(self.house, agent)
        line = self.house.standing_of(agent.id)["bunt_line"]
        self.assertTrue(line["measured"])
        self.assertEqual(line["closed_trades"], ev.paper_trades)
        self.assertGreaterEqual(ev.paper_trades, 1)
        self.assertAlmostEqual(line["E"], ev.e, places=6)
        self.assertAlmostEqual(line["W_paper"], ev.w_paper, places=6)
        self.assertEqual(line["trades_short"], max(0, LINE["bunt_min_trades"] - ev.paper_trades))

    def test_reading_it_changes_nothing(self):
        agent = self.seated()
        self.board(agent, E=1.5, W_paper=2.25, trades=9)
        from league.constitution import money_digest

        head, rung, money = self.house.ledger.head(), self.house.evaluator.rung(agent.id), money_digest()
        board = dict(self.house.allocator.board())
        for _ in range(3):
            self.house.standing_of(agent.id)
            self.house.bunt_line(agent)
        self.assertEqual(self.house.ledger.head(), head)
        self.assertEqual(self.house.evaluator.rung(agent.id), rung)
        self.assertEqual(self.house.allocator.board(), board)
        self.assertEqual(money_digest(), money)

    def test_nothing_is_shown_while_the_allocator_is_off(self):
        from unittest.mock import patch

        agent = self.seated()
        with patch.object(allocator, "enabled", return_value=False):
            self.assertIsNone(self.house.standing_of(agent.id)["bunt_line"])


class OneLossTrialText(HouseCase):
    """The rules tell a bunt what the study measured on Sept 23, 2026: one lost position over about
    15% of a fresh stake (1 - hysteresis) sends it back to paper."""

    def test_the_rules_name_the_one_loss_trial_and_its_share(self):
        import json
        from league.constitution import CONSTITUTION
        from league.rules import rules_text
        text = rules_text(json.load(open("league/game.json")))
        share = 1 - float(CONSTITUTION["allocator"]["hysteresis"])
        self.assertIn("ONE-LOSS TRIAL", text)
        self.assertIn(f"about {share:.0%} of your stake", text)
