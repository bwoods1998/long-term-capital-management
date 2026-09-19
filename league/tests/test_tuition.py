"""The micro rung's tuition: what the paper screen may cost is a number in the constitution.

The screen from paper to real money lets through agents with no proven edge, on purpose. These
tests pin the dollar cap that makes that safe: how many agents may hold real money at once, that
the loss so far plus what the seated agents could still lose must fit under the line, and that at
the line the rung closes, everyone on it goes back to paper, and the loss is not forgotten.
"""

import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest import mock

from league.constitution import CONSTITUTION
from league.economy import load_game
from league.house import House, Settings
from league.ledger import now_iso
from league.tests.fakes import Clock, FakeBroker
from league.tests.test_house import FakeAlpacaData
from league.tests.test_ladder import LADDER, FakeAuditor, InProcessSandbox
from league.venues import instrument_for

D = Decimal
BTC = {"symbol": "BTC/USD"}


class TuitionTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.clock = Clock()
        self.paper, self.real = FakeBroker("alpaca-paper"), FakeBroker("alpaca", cash="800")
        game = load_game()
        game["economy"]["min_population"] = 0
        self.auditor = FakeAuditor()
        self.house = House(
            Path(self.dir.name) / "house", brokers={"alpaca-paper": self.paper, "alpaca": self.real}, sandbox=InProcessSandbox(),
            alpaca_data=FakeAlpacaData(), clock=self.clock, settings=Settings(mark_every_seconds=0, research=False, real_money=True), game=game, auditor=self.auditor,
        )
        self.auditor.ledger = self.house.ledger
        self.quote(80000)
        self.house.books["alpaca"].reconcile()

    def tearDown(self):
        self.house.close(wait=None)
        self.dir.cleanup()

    def quote(self, price):
        for broker in (self.paper, self.real):
            broker.clock_iso = now_iso(self.clock)
            broker.set_quote(instrument_for(broker.venue, BTC), f"{price - 2:.2f}", f"{price + 2:.2f}")

    def on_micro(self, name, rung=2):
        agent = self.house.spawn(name, "tuition-test", LADDER, reason="test", endowment="2.5")
        self.house._state["tried"][agent.id] = agent.code_sha256
        self.house._state["next_wake"][agent.id] = self.clock() + 10**9  # it trades only when the test says so
        self.house.evaluator.seat(agent.id, rung, "test")
        self.house.seat(agent)
        return agent

    def lose_about_five_dollars(self, agent):
        """Buy $10 of bitcoin with real money and halve the price."""
        from league.book import Intent

        book = self.house.books["alpaca"]
        outcome = book.submit([Intent.new(agent=agent.id, instrument=instrument_for("alpaca", BTC), side="buy", quantity="0.000124",
                                          reason="test", created_at=now_iso(self.clock), nonce=agent.id)])[0]
        self.assertIn(outcome.status, ("filled", "sent"), outcome.detail)
        book.poll()
        self.quote(40000)
        book.mark()

    def limit(self, usd):
        return mock.patch.dict(CONSTITUTION["tuition"], {"max_loss_usd": str(usd)})

    # ------------------------------------------------------------------ room
    def test_an_untouched_rung_has_room_and_has_cost_nothing(self):
        state = self.house.tuition()
        self.assertEqual((state["spent_usd"], state["seated"], state["room"], state["closed"]), (D(0), 0, True, False))
        self.assertEqual((state["limit_usd"], state["max_agents"]), (D("50"), 4))

    def test_the_fifth_agent_waits_on_paper(self):
        for i in range(4):
            self.assertTrue(self.house.tuition()["room"], i)
            self.on_micro(f"m{i}")
        state = self.house.tuition()
        self.assertEqual((state["seated"], state["room"]), (4, False))

    def test_what_the_seated_could_still_lose_is_budgeted_before_it_is_lost(self):
        # Four agents fit under $50 only while nothing has been lost: 4 x $7.50 = $30. After a $5
        # loss a second agent still fits under $20.50 (5 + 2 x 7.50 = 20) but not under $19.
        a = self.on_micro("aa")
        self.lose_about_five_dollars(a)
        spent = self.house.tuition()["spent_usd"]
        self.assertTrue(D("4.9") < spent < D("5.2"), spent)
        with self.limit("20.50"):
            self.assertTrue(self.house.tuition()["room"])
        with self.limit("19"):
            state = self.house.tuition()
            self.assertEqual((state["room"], state["closed"]), (False, False))

    def test_an_eligible_agent_is_not_even_audited_when_there_is_no_room(self):
        from league.evaluator import Verdict

        for i in range(4):
            self.on_micro(f"m{i}")
        waiting = self.on_micro("waiting", rung=1)
        self.house._promote(waiting, Verdict(waiting.id, 1, "eligible", "it cleared the screen", {}))
        self.assertEqual((self.house.evaluator.rung(waiting.id), self.auditor.seen), (1, []))

    # ------------------------------------------------------------- at the line
    def test_at_the_line_everyone_on_the_rung_goes_back_to_paper_and_the_owner_is_told_once(self):
        a, b = self.on_micro("aa"), self.on_micro("bb")
        self.lose_about_five_dollars(a)
        with self.limit("4"):
            self.assertTrue(self.house.tuition()["closed"])
            self.house._enforce_tuition()
            self.house._enforce_tuition()
            self.assertEqual([self.house.evaluator.rung(x.id) for x in (a, b)], [1, 1])
            real = self.house.books["alpaca"]
            self.assertEqual(real.account(a.id).holdings, {})  # what it held was sold
            self.assertTrue(real.account(a.id).swept and real.account(b.id).swept)
            # The loss outlives the account: equity is zero and what did not come back is still staked.
            state = self.house.tuition()
            self.assertTrue(D("4.9") < state["spent_usd"] < D("5.3"), state["spent_usd"])
            self.assertEqual((state["seated"], state["room"], state["closed"]), (0, False, True))
            alerts = [e.payload for e in self.house.ledger.iter(kinds="ops.alert") if "tuition" in str(e.payload)]
            self.assertEqual(len(alerts), 1)
            self.assertTrue(real.reconcile().ok)

    def test_raising_the_line_reopens_the_rung(self):
        a = self.on_micro("aa")
        self.lose_about_five_dollars(a)
        with self.limit("4"):
            self.house._enforce_tuition()
            self.assertFalse(self.house.tuition()["room"])
        self.assertTrue(self.house.tuition()["room"])  # the owner's $50 line: $5 spent, nobody seated

    def test_an_agent_that_earned_the_scaled_rung_is_no_longer_tuition(self):
        a = self.on_micro("aa")
        self.lose_about_five_dollars(a)
        self.assertGreater(self.house.tuition()["spent_usd"], 0)
        self.house.evaluator.promote(a.id, 3, "test")
        state = self.house.tuition()
        self.assertEqual((state["spent_usd"], state["seated"]), (D(0), 0))

    def test_profits_on_the_rung_do_not_raise_the_line(self):
        a = self.on_micro("aa")
        from league.book import Intent

        book = self.house.books["alpaca"]
        book.submit([Intent.new(agent=a.id, instrument=instrument_for("alpaca", BTC), side="buy", quantity="0.000124", reason="test", created_at=now_iso(self.clock), nonce="up")])
        book.poll()
        self.quote(120000)
        book.mark()
        state = self.house.tuition()
        self.assertGreater(state["pnl_usd"], 0)
        self.assertEqual(state["spent_usd"], D(0))

    def test_practice_money_is_never_tuition(self):
        paper_only = self.on_micro("pp", rung=1)
        self.assertIn(paper_only.id, self.house.books["alpaca-paper"].accounts)
        self.assertEqual(self.house.tuition()["spent_usd"], D(0))


if __name__ == "__main__":
    unittest.main()
