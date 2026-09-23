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



# The ladder's integration runs through the legacy $50 tuition, which cannot seat a $60 stake; it
# exercises the mechanism with the micro rung as it stood before the Sept 21, 2026 learning surge.
# Production's persistent owner grant supersedes the tuition.
from unittest.mock import patch as _patch  # noqa: E402
from league.constitution import CONSTITUTION as _CONSTITUTION  # noqa: E402
_LEGACY_MICRO = _patch.dict(_CONSTITUTION["rungs"]["2"], {"stake_usd": "25", "max_position_usd": "10", "max_order_usd": "10", "option_max_position_usd": "20"})


def setUpModule():
    _LEGACY_MICRO.start()


def tearDownModule():
    _LEGACY_MICRO.stop()

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
        self.approve, self.seen, self.ledger = approve, [], None

    def audit(self, agent, verdict):
        self.seen.append(agent.id)
        if self.ledger is not None:  # the real auditor records every verdict; the cooldown reads that row
            self.ledger.append("audit.verdict", {"approve": self.approve, "summary": "test"}, agent=agent.id)
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
        game["economy"]["newcomer_seconds"] = 10 ** 9  # the ladder is what is under test, not the refill
        game["audit"]["cooldown_hours"] = 72  # the mechanism is what is tested here, not the expedition's dial (24)
        self.auditor = FakeAuditor()
        self.house = House(
            Path(self.dir.name) / "house", brokers={"alpaca-paper": self.paper, "alpaca": self.real}, sandbox=InProcessSandbox(),
            alpaca_data=self.data, clock=self.clock, settings=Settings(mark_every_seconds=0, research=False, real_money=True), game=game, auditor=self.auditor,
        )
        self.auditor.ledger = self.house.ledger
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

    def test_a_vetoed_agent_waits_out_a_cooldown_and_a_poor_one_is_not_audited(self):
        house = self.house
        self.auditor.approve = False
        agent = house.spawn("climber", "ladder-test", LADDER, reason="test", endowment="2.5")
        house.evaluator.seat(agent.id, 1, "test")
        house._state["tried"][agent.id] = agent.code_sha256
        self.run_hours(45, edge=0.78)  # eligible at several looks, vetoed at the first
        self.assertEqual(house.evaluator.rung(agent.id), 1)
        self.assertEqual(self.auditor.seen.count(agent.id), 1)  # audited once, not at every look (a child it forked may be audited too)
        self.assertFalse(house._audit_due(agent))
        self.clock.advance(73 * 3600)
        self.assertTrue(house._audit_due(agent))
        house.economy.charge(agent.id, house.economy.balance(agent.id) - D("0.10"), "test")
        self.assertTrue(house._audit_due(agent))  # the House pays for the audit (Sept 23, 2026)...
        house.game["audit"]["house_pays"] = False
        self.assertFalse(house._audit_due(agent))  # ...and an agent that pays must be able to

    def test_an_audit_that_never_ran_does_not_cost_the_agent_a_day(self):
        """A gate that fails shut is right. A gate that fails shut AND fines the agent a day at the
        top of the ladder for its own malfunction is not: the frontier was down, not the strategy."""
        house = self.house
        agent = house.spawn("climber", "ladder-test", LADDER, reason="test", endowment="2.5")
        house.evaluator.seat(agent.id, 1, "test")
        house.ledger.append("audit.verdict", {"approve": False, "error": "frontier call refused: HTTP 502",
                                              "summary": "the audit could not run; the agent stays on paper"}, agent=agent.id)
        self.assertFalse(house._audit_due(agent))
        self.clock.advance(31 * 60)
        self.assertTrue(house._audit_due(agent))
        house.ledger.append("audit.verdict", {"approve": False, "summary": "look-ahead in the entry"}, agent=agent.id)
        self.clock.advance(31 * 60)
        self.assertFalse(house._audit_due(agent))  # a real veto is still a day's wait

    def test_up_the_ladder_sized_and_back_down(self):
        house = self.house
        agent = house.spawn("climber", "ladder-test", LADDER, reason="test", endowment="2.5")
        house.evaluator.seat(agent.id, 1, "test: straight to paper")
        house._state["tried"][agent.id] = agent.code_sha256

        for _ in range(42 * 12):
            self.run_hours(1 / 12, edge=0.78)
            if house.evaluator.rung(agent.id) >= 2:
                break
        self.assertEqual(self.auditor.seen[:1], [agent.id])  # eligible on paper, so it was audited
        self.assertEqual(house.evaluator.rung(agent.id), 2)
        real, paper = house.books["alpaca"], house.books["alpaca-paper"]
        self.assertEqual(real.account(agent.id).staked, D("25"))
        self.assertEqual(paper.account(agent.id).holdings, {})  # it left the paper book flat
        self.assertTrue(paper.account(agent.id).swept)
        self.assertEqual(real.limits[agent.id].max_position_usd, D("10"))
        self.assertTrue(real.reconcile().ok)

        for _ in range(46 * 12):
            self.run_hours(1 / 12, edge=0.78)
            if house.evaluator.rung(agent.id) >= 3:
                break
        self.assertEqual(house.evaluator.rung(agent.id), 3)
        fills = [e for e in house.ledger.iter(kinds="book.fill", agent=agent.id) if e.payload["book"] == "alpaca" and e.payload["source"] == "venue"]
        self.assertTrue(all(D(e.payload["quantity"]) * D(e.payload["price"]) <= D("10.01") for e in fills[:50]))  # micro-real means micro

        self.clock.advance(86400)  # an epoch passes: payout, sizing, recommendation
        self.run_hours(1, edge=0.78)
        sized = [e.payload for e in house.ledger.iter(kinds="eval.verdict", agent=agent.id) if e.payload.get("decision") == "size"]
        self.assertTrue(sized)
        self.assertGreater(D(sized[-1]["stake_usd"]), D("25"))
        self.assertLessEqual(D(sized[-1]["stake_usd"]), D(sized[-1]["ceiling_usd"]))  # venue cash at the sizing decision
        # Regression: every wake re-seats the agent, and a seat once reset a scaled agent's limits to
        # the micro rung's, so its larger stake traded at $10 a position until the next day's sizing.
        self.run_hours(1, edge=0.78)
        self.assertEqual(real.limits[agent.id].max_position_usd, min(real.account(agent.id).staked / 2, D("60")).quantize(D("0.01")))
        self.assertGreater(real.limits[agent.id].max_position_usd, D("10"))
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
