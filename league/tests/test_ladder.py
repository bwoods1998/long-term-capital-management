"""The whole ladder in one run: paper, the audit, micro-real, scaled, sizing, and decay back down.

Slow for a unit test (a few hundred simulated hours of five-minute wakes, each a real subprocess),
and the only place every rule is seen working together.
"""

import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from league.economy import load_game
from league.house import House, Settings
from league.ledger import now_iso
from league import runner
from league.replay import run_replay
from league.sandbox import Run
from league.tests.fakes import Clock, FakeBroker
from league.tests.test_house import FakeAlpacaData
from league.venues import instrument_for

D = Decimal

LADDER = '''
NEEDS = {"venue": "alpaca", "horizon": "hour", "style": "ladder-test", "symbols": ["BTC/USD"],
         "bars": {"timeframe": "5Min", "limit": 5}, "wake_minutes": 5}
PARAMS = {}

def decide(ctx):
    held = [p for p in ctx["positions"] if p["symbol"] == "BTC/USD"]
    if held:
        return {"intents": [{"symbol": "BTC/USD", "side": "sell", "quantity": held[0]["quantity"], "type": "market", "reason": "sell the step up"}], "thought": "sell"}
    size = min(40.0, ctx["limits"]["max_order_usd"] * 0.9, ctx["cash"] * 0.9)
    return {"intents": [{"symbol": "BTC/USD", "side": "buy", "notional_usd": size, "type": "market", "reason": "buy the step"}], "thought": "buy"}
'''


class InProcessSandbox:
    """Test-only: runs `decide` in this process (a thousand wakes as subprocesses takes minutes).
    It claims to be sealed so the House will open real-money books against the fake venues."""

    secure = True

    def __init__(self):
        self.retired, self.forks = [], []

    def decide(self, agent, code, ctx):
        return Run(runner.decide(code, json.loads(json.dumps(ctx))), 0.01)

    def needs(self, agent, code):
        return Run(runner.needs_of(code), 0.01)

    def replay(self, agent, code, params, tape, *, stake, limits, timeout=600):
        return Run(run_replay(code, params, tape, stake=stake, limits=limits), 0.01)

    def fork(self, parent, child):
        self.forks.append((parent, child))
        return True

    def retire(self, agent):
        self.retired.append(agent)

    def sleep_all(self):
        return 0


class FakeAuditor:
    def __init__(self, approve=True):
        self.approve, self.seen = approve, []

    def audit(self, agent, verdict):
        self.seen.append(agent.id)
        return {"approve": self.approve, "summary": "test"}

    def score(self):
        return {}


class LadderTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.clock = Clock()
        self.paper, self.real = FakeBroker("alpaca-paper"), FakeBroker("alpaca", cash="800")
        self.data = FakeAlpacaData()
        game = load_game()
        game["economy"]["min_population"] = 0
        self.auditor = FakeAuditor()
        self.house = House(
            Path(self.dir.name) / "house", brokers={"alpaca-paper": self.paper, "alpaca": self.real}, sandbox=InProcessSandbox(),
            alpaca_data=self.data, clock=self.clock, settings=Settings(mark_every_seconds=0, research=False, real_money=True), game=game, auditor=self.auditor,
        )
        self.price = 80000.0
        self.step = 0

    def tearDown(self):
        self.house.close(wait=None)
        self.dir.cleanup()

    def run_hours(self, hours, edge):
        """Five-minute ticks. The strategy buys when flat and sells on its next wake, so the tape is
        written against its state: while it holds, the price rises on `edge` of the steps and falls
        on the rest; while it is flat the price drifts back. A third of its round trips lose, which
        keeps the record honest (one that wins every trade is, rightly, held back by the loss-rate gate)."""
        for _ in range(int(hours * 12)):
            self.step += 1
            holds = any(book.account("climber").holdings for book in self.house.books.values() if "climber" in book.accounts)
            favourable = (self.step * 7) % 100 < edge * 100
            if holds:
                self.price *= 1.022 if favourable else 0.978
            else:
                self.price *= 1 + (80000.0 / self.price - 1) * 0.5  # back toward where it started
            self.data.price = self.price
            for broker in (self.paper, self.real):
                broker.clock_iso = now_iso(self.clock)
                broker.set_quote(instrument_for(broker.venue, {"symbol": "BTC/USD"}), f"{self.price - 2:.2f}", f"{self.price + 2:.2f}")
            self.clock.advance(300)
            self.house.tick()

    def test_up_the_ladder_sized_and_back_down(self):
        house = self.house
        agent = house.spawn("climber", "ladder-test", LADDER, reason="test", endowment="2.5")
        house.evaluator.seat(agent.id, 1, "test: straight to paper")
        house._state["tried"][agent.id] = agent.code_sha256

        self.run_hours(32, edge=0.78)  # 2.2% moves, right 78% of the time, against a 0.5% round-trip fee
        self.assertEqual(self.auditor.seen[:1], [agent.id])  # eligible on paper, so it was audited
        self.assertEqual(house.evaluator.rung(agent.id), 2)
        real, paper = house.books["alpaca"], house.books["alpaca-paper"]
        self.assertEqual(real.account(agent.id).staked, D("25"))
        self.assertEqual(paper.account(agent.id).holdings, {})  # it left the paper book flat
        self.assertTrue(paper.account(agent.id).swept)
        self.assertEqual(real.limits[agent.id].max_position_usd, D("10"))
        self.assertTrue(real.reconcile().ok)

        self.run_hours(34, edge=0.78)
        self.assertEqual(house.evaluator.rung(agent.id), 3)
        fills = [e for e in house.ledger.iter(kinds="book.fill", agent=agent.id) if e.payload["book"] == "alpaca" and e.payload["source"] == "venue"]
        self.assertTrue(all(D(e.payload["quantity"]) * D(e.payload["price"]) <= D("10.01") for e in fills[:50]))  # micro-real means micro

        self.clock.advance(86400)  # an epoch passes: payout, sizing, recommendation
        self.run_hours(1, edge=0.78)
        sized = [e.payload for e in house.ledger.iter(kinds="eval.verdict", agent=agent.id) if e.payload.get("decision") == "size"]
        self.assertTrue(sized)
        self.assertGreater(D(sized[-1]["stake_usd"]), D("25"))
        self.assertLessEqual(D(sized[-1]["stake_usd"]), real.venue_cash * D("0.25") + 1)  # never more than a quarter of the venue's cash
        recommendation = house.ledger.last("ops.recommendation").payload
        self.assertEqual(recommendation["ranked"][0]["agent"], agent.id)

        self.run_hours(30, edge=0.3)  # the edge is gone: most round trips now lose
        verdicts = [e.payload["decision"] for e in house.ledger.iter(kinds="eval.verdict", agent=agent.id)]
        self.assertTrue("demote" in verdicts or "die" in verdicts, verdicts[-6:])
        self.assertTrue(real.reconcile().ok)
        self.assertTrue(paper.reconcile().ok)
        self.assertEqual(house.ledger.verify(), house.ledger.head()[0])


if __name__ == "__main__":
    unittest.main()
