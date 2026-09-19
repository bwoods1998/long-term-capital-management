"""The horizon rule: fast feedback is what the ladder runs on.

No entry in a Kalshi market expected to pay later than the agent's horizon allows; no crypto
position held longer than the game's limit. Equities (and options, when they are offered) are not
bounded: that is the owner's decision of Sept 19, 2026.
"""

import copy
import json
import unittest
from decimal import Decimal

from league.book import Limits
from league.economy import check_bounds, load_game
from league.ledger import now_iso
from league.tests.test_book import BookCase
from league.tests.test_house import BUYER, HouseCase
from league.venues import instrument_for

D = Decimal
HOLDER = BUYER.replace("test-buyer", "test-holder").replace('''    if held:
        return {"intents": [{"symbol": "BTC/USD", "side": "sell", "quantity": held[0]["quantity"], "type": "market", "reason": "take it off"}],
                "thought": "holding, so selling", "memory": {"sold": True}}''', '''    if held:
        return {"intents": [], "thought": "holding for ever"}''')


class KalshiEntries(BookCase):
    venue = "kalshi-shadow"
    family = "kalshi"
    cash = "1000"

    def setUp(self):
        super().setUp()
        self.market = instrument_for("kalshi", {"market": "KXNFLGAME-26SEP20AB-A", "leg": "yes"})
        self.market = type(self.market)(**{**self.market.__dict__, "venue": self.venue})
        self.broker.set_quote(self.market, "0.60", "0.62")
        self.due: float | None = self.clock() + 6 * 3600
        self.asked = []
        self.book.resolves_at = self.resolves_at

    def resolves_at(self, instrument):
        self.asked.append(instrument.market_id)
        return self.due

    def seat(self, agent, hours):
        self.book.limits[agent] = Limits(D("100"), D("75"), max_hours_to_resolve=hours)
        self.book.stake(agent, "200")

    def buy(self, agent="a"):
        return self.book.submit([self.intent(agent, self.market, "buy", "10", order_type="limit", limit_price="0.60")])[0]

    def test_a_market_that_pays_inside_the_horizon_may_be_entered(self):
        self.seat("a", 12)
        self.assertNotEqual(self.buy().status, "refused")

    def test_a_market_that_pays_next_year_is_refused_and_the_reason_says_when(self):
        self.seat("a", 12)
        self.due = self.clock() + 400 * 86400
        outcome = self.buy()
        self.assertEqual(outcome.status, "refused")
        self.assertIn("expected to resolve in 9600 hours; entries must resolve within 12", outcome.detail)

    def test_the_limit_is_the_agents_own(self):
        self.seat("hourly", 12)
        self.seat("daily", 48)
        self.due = self.clock() + 30 * 3600
        self.assertEqual(self.buy("hourly").status, "refused")
        self.assertNotEqual(self.buy("daily").status, "refused")

    def test_the_limit_is_inclusive(self):
        self.seat("a", 12)
        self.due = self.clock() + 12 * 3600
        self.assertNotEqual(self.buy().status, "refused")

    def test_not_knowing_when_it_pays_is_a_refusal(self):
        self.seat("a", 12)
        self.due = None
        self.assertIn("cannot tell when this market resolves", self.buy().detail)
        self.book.resolves_at = lambda instrument: 1 / 0
        self.assertIn("cannot tell when this market resolves", self.buy().detail)
        self.book.resolves_at = None
        self.assertIn("cannot tell when this market resolves", self.buy().detail)

    def test_an_exit_is_never_refused_by_the_horizon(self):
        self.seat("a", 12)
        self.assertNotEqual(self.buy().status, "refused")
        order = next(iter(self.broker.orders))
        self.broker.fill_resting(order, "10")
        self.book.poll()
        self.due = self.clock() + 400 * 86400  # the schedule slipped a year after it was bought
        outcome = self.book.submit([self.intent("a", self.market, "sell", "10", order_type="limit", limit_price="0.62")])[0]
        self.assertNotEqual(outcome.status, "refused", outcome.detail)

    def test_no_limit_means_no_rule_and_no_lookup(self):
        self.book.limits["a"] = Limits(D("100"), D("75"))
        self.book.stake("a", "200")
        self.due = self.clock() + 400 * 86400
        self.assertNotEqual(self.buy().status, "refused")
        self.assertEqual(self.asked, [])


class Unbounded(BookCase):
    def test_an_equity_entry_is_never_asked_when_it_resolves(self):
        spy = instrument_for(self.venue, {"symbol": "SPY"})
        self.broker.set_quote(spy, "649.90", "650.10")
        self.book.resolves_at = lambda instrument: 1 / 0
        self.book.limits["a"] = Limits(D("100"), D("75"), max_hours_to_resolve=12)
        self.book.stake("a", "200")
        outcome = self.book.submit([self.intent("a", spy, "buy", "0.1")])[0]
        self.assertNotIn("resolve", outcome.detail)


class HouseHorizon(HouseCase):
    def test_kalshi_agents_get_the_limit_of_their_block_length_and_alpaca_agents_none(self):
        agent = self.seated()
        self.assertIsNone(self.house.horizon_hours(agent))
        self.assertIsNone(self.house._limits(1, agent).max_hours_to_resolve)
        hourly = type(agent)(**{**agent.__dict__, "venue": "kalshi", "horizon": "hour"})
        daily = type(agent)(**{**agent.__dict__, "venue": "kalshi", "horizon": "day"})
        self.assertEqual((self.house.horizon_hours(hourly), self.house.horizon_hours(daily)), (12.0, 48.0))

    def test_a_crypto_position_is_closed_by_the_house_after_forty_eight_hours(self):
        agent = self.house.spawn("holder", "test-family", HOLDER, reason="test")
        self.house.evaluator.seat(agent.id, 1, "test")
        self.house._state["tried"][agent.id] = agent.code_sha256
        self.house.tick()
        book = self.house.books["alpaca-paper"]
        self.assertIn(self.btc.key, book.account(agent.id).holdings)
        self.clock.advance(47 * 3600)
        self.broker.clock_iso = now_iso(self.clock)
        self.house.tick()
        self.assertIn(self.btc.key, book.account(agent.id).holdings)  # 47 hours: still its own
        self.clock.advance(2 * 3600)
        self.broker.clock_iso = now_iso(self.clock)
        self.house.tick()
        self.assertEqual(book.account(agent.id).holdings, {})
        sold = [e.payload for e in self.house.ledger.iter(kinds="agent.intent", agent=agent.id) if e.payload.get("side") == "sell"]
        self.assertEqual(len(sold), 1)
        self.assertIn("horizon rule: held 49 hours", sold[0]["reason"])
        self.assertTrue(book.reconcile().ok)

    def test_its_own_resting_sell_does_not_shield_a_position_from_the_rule(self):
        agent = self.house.spawn("holder", "test-family", HOLDER, reason="test")
        self.house.evaluator.seat(agent.id, 1, "test")
        self.house._state["tried"][agent.id] = agent.code_sha256
        self.house.tick()
        book = self.house.books["alpaca-paper"]
        quantity = book.account(agent.id).holdings[self.btc.key].quantity
        from league.book import Intent

        rest = book.submit([Intent.new(agent=agent.id, instrument=self.btc, side="sell", quantity=quantity, order_type="limit", limit_price="83000",
                                       reason="a sell that will never fill", created_at=now_iso(self.clock), nonce="far")])[0]
        self.assertEqual(rest.status, "resting", rest.detail)
        self.clock.advance(49 * 3600)
        self.broker.clock_iso = now_iso(self.clock)
        self.house.tick()
        self.assertEqual(book.account(agent.id).holdings, {})
        self.assertEqual(book.open_orders(agent.id), [])

    def test_the_rule_can_be_switched_off_in_the_game_file(self):
        game = load_game()
        game["horizon"]["crypto_max_hold_hours"] = 0
        self.assertEqual(type(self.house)._enforce_horizon(type("H", (), {"game": game})()), 0)


class GameFile(unittest.TestCase):
    def test_the_shipped_horizon_is_inside_its_bounds(self):
        game = load_game()
        self.assertEqual({k: v for k, v in game["horizon"].items() if not k.startswith("_")},
                         {"kalshi_hour_max_hours": 12, "kalshi_day_max_hours": 48, "crypto_max_hold_hours": 48})

    def test_a_designer_cannot_move_the_horizon_out_of_bounds(self):
        game = copy.deepcopy(load_game())
        game["horizon"]["kalshi_day_max_hours"] = 24 * 365
        with self.assertRaisesRegex(ValueError, "horizon.kalshi_day_max_hours"):
            check_bounds(json.loads(json.dumps(game)))


if __name__ == "__main__":
    unittest.main()
