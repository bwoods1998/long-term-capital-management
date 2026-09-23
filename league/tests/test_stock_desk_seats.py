"""Displacement on desks that keep an exchange's hours is counted in the market's own time (Sept 23, 2026).

Nine stock and option agents were displaced Sept 21-23 after a median 6.5 session hours, every one
with fills and none with more than four closed trades; three held contracts the House then sold at
the open, and research rewrites kept restarting the clocks of the agents that had never traded."""
from datetime import datetime, timezone
from decimal import Decimal

from league.book import Holding
from league.constitution import CONSTITUTION
from league.tests.test_house import BUYER, HouseCase
from league.venues import instrument_for

D = Decimal
SPY_HOURLY = BUYER.replace('"BTC/USD"', '"SPY"')
#: Wednesday Sept 23, 2026: the first wake with the market open, five seconds after the open.
FIRST_WAKE = "2026-09-23T13:30:05Z"
#: Twelve regular-session hours after FIRST_WAKE: 6.5 on Wednesday, 5.5 on Thursday.
GRACE_ENDS = "2026-09-24T19:00:05Z"


def ts(stamp: str) -> float:
    return datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone(timezone.utc).timestamp()


class StockDeskSeats(HouseCase):
    def setUp(self):
        super().setUp()
        self.rules = self.house.game["economy"]
        self.book = self.house.books["alpaca-paper"]
        self.spy = instrument_for("alpaca-paper", {"symbol": "SPY"})

    def at(self, stamp: str) -> None:
        self.clock.now = ts(stamp)

    def seat(self, name: str = "stocks", code: str = SPY_HOURLY):
        """Seated on the Tuesday evening before, with its first open-market wake on Wednesday."""
        self.at("2026-09-22T22:00:00Z")
        agent = self.seated(name, code)
        self.assertTrue(self.house.niche_of(agent).keeps_hours(agent.needs))
        self.at(FIRST_WAKE)
        self.house.ledger.append("agent.woke", {"ok": True, "offered": 1}, agent=agent.id)
        return agent

    def fill(self, agent, stamp: str, *, closed: bool = False) -> None:
        """A practice fill; `closed` makes it a sale that left the position flat (a closed trade)."""
        self.at(stamp)
        payload = {"book": "alpaca-paper", "symbol": "SPY", "side": "sell" if closed else "buy",
                   "quantity": "0.05", "price": "500", "source": "venue"}
        if closed:
            payload.update(realized="-0.02", flat=True)
        self.house.ledger.append("book.fill", payload, agent=agent.id)

    def trades(self, agent, count: int) -> None:
        """`count` losing round trips inside Wednesday's session."""
        for n in range(count):
            self.fill(agent, f"2026-09-23T14:{10 + 2 * n:02d}:00Z")
            self.fill(agent, f"2026-09-23T14:{11 + 2 * n:02d}:00Z", closed=True)

    def weakest(self):
        found = self.house._weakest(self.rules)
        return None if found is None else found.id

    def test_the_grace_is_regular_session_hours_not_the_night(self):
        """At 01:31Z, twelve wall-clock hours after its first wake, an ETF agent had seen 6.5 hours of market."""
        agent = self.seat()
        self.at("2026-09-24T01:31:00Z")
        self.assertIsNone(self.weakest())
        self.at("2026-09-24T19:00:04Z")
        self.assertIsNone(self.weakest())
        self.at(GRACE_ENDS)
        self.assertEqual(self.weakest(), agent.id)

    def test_a_trading_hourly_agent_keeps_its_seat_until_it_has_closed_the_bunt_lines_trades(self):
        needed = int(CONSTITUTION["allocator"]["bunt_min_trades"])
        agent = self.seat()
        self.assertEqual(agent.horizon, "hour")
        self.trades(agent, needed - 1)
        self.at("2026-09-24T19:01:00Z")  # past the session grace, one session closed
        self.assertIsNone(self.weakest())
        self.fill(agent, "2026-09-24T19:02:00Z")
        self.fill(agent, "2026-09-24T19:03:00Z", closed=True)
        self.assertEqual(self.weakest(), agent.id)

    def test_the_protection_ends_after_the_games_sessions(self):
        agent = self.seat()
        self.trades(agent, 1)
        self.at("2026-09-25T19:59:00Z")  # Friday, before the third session closes
        self.assertIsNone(self.weakest())
        self.assertEqual(self.rules["displace_trading_after_sessions"], 3)
        self.at("2026-09-25T20:00:01Z")
        self.assertEqual(self.weakest(), agent.id)
        self.rules["displace_trading_after_sessions"] = 2  # the dial is the game designer's
        self.at("2026-09-24T20:00:01Z")
        self.assertEqual(self.weakest(), agent.id)

    def test_an_agent_holding_a_position_is_not_displaced_while_its_market_is_shut(self):
        """scholes-23 was removed at 07:11Z mid-basket; the House sold what its own exit sells at the open."""
        agent = self.seat()
        self.trades(agent, int(CONSTITUTION["allocator"]["bunt_min_trades"]))
        self.fill(agent, "2026-09-25T19:30:00Z")  # tonight's basket, sold at Monday's open
        self.book.account(agent.id).holdings[self.spy.key] = Holding(self.spy, D("0.05"), D("25"))
        self.at("2026-09-26T07:11:00Z")
        self.assertIsNone(self.weakest())
        self.at("2026-09-28T13:31:00Z")  # the market is open: the House can close it at market
        self.assertEqual(self.weakest(), agent.id)
        self.book.account(agent.id).holdings.clear()
        self.at("2026-09-26T07:11:00Z")
        self.assertEqual(self.weakest(), agent.id)  # flat overnight: nothing to protect

    def test_an_options_agent_holding_a_contract_is_not_displaced_while_the_market_is_shut(self):
        from league import seeds

        self.at("2026-09-22T22:00:00Z")
        agent = self.house.spawn("options-breakout", "options-breakout", seeds.load("options-breakout"),
                                 reason="test", specialty="alpaca-options")
        self.assertEqual(self.house.evaluator.rung(agent.id), 1)
        self.at(FIRST_WAKE)
        self.house.ledger.append("agent.woke", {"ok": True, "offered": 1}, agent=agent.id)
        contract = instrument_for("alpaca-paper", {"occ": "RIVN261002P00014000"})
        self.assertEqual(contract.asset_class, "option")
        self.book.account(agent.id).holdings[contract.key] = Holding(contract, D("1"), D("14"))
        self.at("2026-09-26T03:00:00Z")  # three sessions and the session grace long gone
        self.assertIsNone(self.weakest())
        self.at("2026-09-28T13:31:00Z")
        self.assertEqual(self.weakest(), agent.id)

    def test_a_rewrite_of_an_agent_that_never_traded_does_not_restart_its_clock(self):
        agent = self.seat()
        self.at("2026-09-24T15:00:00Z")
        self.house.registry.adopt(agent.id, code=agent.code + "\n# a research rewrite\n", needs=agent.needs,
                                  params=agent.params, reason="empty-record replacement")
        self.at("2026-09-24T19:00:10Z")
        self.assertEqual(self.weakest(), agent.id)

    def test_a_rewrite_after_trading_is_still_a_new_opportunity(self):
        agent = self.seat()
        self.fill(agent, "2026-09-23T14:00:00Z")
        self.at("2026-09-24T15:00:00Z")
        self.house.registry.adopt(agent.id, code=agent.code + "\n# a research rewrite\n", needs=agent.needs,
                                  params=agent.params, reason="a new program")
        self.at("2026-09-25T19:00:10Z")
        self.assertIsNone(self.weakest())  # the new program has not had an open-market wake yet

    def test_an_agent_that_never_traded_is_displaced_before_one_that_trades(self):
        idle = self.seat("idle")
        trader = self.seat("trader")
        self.trades(trader, int(CONSTITUTION["allocator"]["bunt_min_trades"]))
        # The trader has spent more of its credits: ranked by purse alone it would go first.
        self.house.economy.grant(idle.id, D("5"), "test: a fuller purse")
        self.at("2026-09-24T19:00:10Z")
        self.assertEqual(self.weakest(), idle.id)

    def test_a_profitable_trader_is_never_displaced(self):
        agent = self.seat()
        self.trades(agent, int(CONSTITUTION["allocator"]["bunt_min_trades"]))
        self.house.ledger.append("eval.block", {"book": "alpaca-paper", "key": "2026-09-23T14", "horizon": "hour",
                                                "start_equity": 200.0, "end_equity": 201.0, "flow": 0.0,
                                                "log_growth": 0.005, "active": True}, agent=agent.id)
        self.assertGreater(self.house.standing_of(agent.id)["mean_growth"], 0)
        self.at("2026-10-05T19:00:00Z")
        self.assertIsNone(self.weakest())

    def test_a_crypto_desk_keeps_its_wall_clock_grace(self):
        self.at("2026-09-22T22:00:00Z")
        agent = self.seated()
        self.assertFalse(self.house.niche_of(agent).keeps_hours(agent.needs))
        self.clock.advance(float(self.rules["epoch_seconds"]) * float(self.rules["displace_after_epochs"]) + 1)
        self.assertEqual(self.weakest(), agent.id)
