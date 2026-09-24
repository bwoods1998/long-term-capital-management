"""No wasted wakes on desks that keep hours (the wake skip, Sept 24, 2026, the close-the-gaps run).

A stock or option agent's wake outside the regular US session sends nothing: its entries cannot
trade until the open, a market exit is refused by the book ("market orders outside regular hours
are not permitted"), and the strategy decides on a shut market's stale quotes. Measured on the T0
snapshot (ledger to 01:41Z Sept 24, the 48 hours before): 2,891 of 9,884 wakes (29%) were stock or
option agents outside the session, billed 9,424 box seconds, and sent 79 intents, of which 75 were
refused as market orders outside regular hours (scholes-h7dd043-2 51, scholes-25 21: their own exits,
"close the position before the session ends"; mcentee-h4054c4 2 and mcentee-30 1: entries). The
other 585 such refusals in those hours were the House's own wind-downs of dead accounts, held for
the open since A7 (Sept 23): a wind-down's held sells keep waiting for the open as before.
"""

import json
from decimal import Decimal
from pathlib import Path

from league.ledger import now_iso
from league.tapes import parse_time
from league.tests.test_house import HouseCase
from league.venues import instrument_for

D = Decimal

#: Buys the index ETF at market when flat and sells it at market when holding, every wake.
ETF = '''
NEEDS = {"venue": "alpaca", "horizon": "hour", "style": "test-etf", "symbols": ["SPY"],
         "bars": {"timeframe": "5Min", "limit": 10}, "wake_minutes": 15}
PARAMS = {}

def decide(ctx):
    held = [p for p in ctx["positions"] if p["symbol"] == "SPY"]
    if held:
        return {"intents": [{"symbol": "SPY", "side": "sell", "quantity": held[0]["quantity"], "type": "market",
                             "reason": "close the position before the session ends"}], "thought": "selling"}
    return {"intents": [{"symbol": "SPY", "side": "buy", "notional_usd": 20, "type": "market", "reason": "in"}],
            "thought": "buying"}
'''

#: An open-desk agent naming a coin and a stock: it buys both, a limit on the stock.
MIXED = '''
NEEDS = {"venue": "alpaca", "horizon": "hour", "style": "test-mixed", "symbols": ["BTC/USD", "SPY"],
         "bars": {"timeframe": "5Min", "limit": 10}, "wake_minutes": 15}
PARAMS = {}

def decide(ctx):
    if ctx["positions"]:
        return {"intents": [], "thought": "holding"}
    return {"intents": [{"symbol": "BTC/USD", "side": "buy", "notional_usd": 20, "type": "market", "reason": "coin"},
                        {"symbol": "SPY", "side": "buy", "quantity": 0.03, "type": "limit", "limit_price": 650, "reason": "stock"}],
            "thought": "buying both"}
'''

NIGHT = parse_time("2026-09-10T00:26:40Z")    # Thursday, 20:26 in New York: the session is shut
SESSION = parse_time("2026-09-10T14:00:00Z")  # 10:00 in New York
BELL = parse_time("2026-09-11T13:30:05Z")     # a few seconds after Friday's open


class SessionWakes(HouseCase):
    def setUp(self):
        super().setUp()
        self.spy = instrument_for("alpaca-paper", {"symbol": "SPY"})
        self.broker.set_quote(self.spy, "649.95", "650.05")
        self.decided: list[str] = []
        decide = self.house.sandbox.decide
        self.house.sandbox.decide = lambda agent, code, ctx: self.decided.append(agent) or decide(agent, code, ctx)

    def at(self, moment):
        self.clock.now = moment
        self.broker.clock_iso = now_iso(self.clock)

    def etf(self, name="scholes", code=ETF):
        agent = self.seated(name, code)
        self.house.seat(agent)
        return agent

    def refusals(self, agent):
        return ["; ".join(e.payload.get("reasons") or []) for e in self.house.ledger.iter(kinds="book.refused", agent=agent.id)]

    def test_a_stock_desk_is_not_woken_into_a_shut_session(self):
        agent = self.etf()
        self.assertEqual(agent.specialty, "alpaca-index-etfs")
        self.at(NIGHT)
        out = self.house.wake(agent)
        self.assertIn("the regular session is shut", out["skipped"])
        self.assertEqual(self.decided, [])  # no box run, no snapshot
        self.assertIsNone(self.house.ledger.last("agent.woke", agent=agent.id))
        self.clock.advance(15 * 60)
        self.assertEqual(self.house.tick()["woke"], [agent.id])
        self.assertEqual((self.decided, self.refusals(agent), self.broker.submitted), ([], [], []))
        self.assertEqual(self.house.idle_run(agent)["shut"], 2)  # the bench-time bookkeeping a shut wake always did
        self.assertEqual(self.house._state["next_wake"][agent.id], self.clock() + 15 * 60)  # its cadence, as before

    def test_in_the_session_it_is_woken_and_trades(self):
        agent = self.etf()
        self.at(SESSION)
        self.house.tick()
        self.assertEqual(self.decided, [agent.id])
        self.assertIn(self.spy.key, self.house.books["alpaca-paper"].account(agent.id).holdings)

    def test_a_position_held_overnight_is_sold_at_the_first_wake_after_the_bell(self):
        agent = self.etf()
        self.at(SESSION)
        self.house.tick()
        book = self.house.books["alpaca-paper"]
        self.assertIn(self.spy.key, book.account(agent.id).holdings)
        self.at(parse_time("2026-09-10T20:30:00Z"))  # the bell has rung: its exit would be a refused market order
        self.assertIn("the regular session is shut", self.house.wake(agent)["skipped"])
        self.house.tick()
        self.assertEqual(self.refusals(agent), [])
        self.assertIn(self.spy.key, book.account(agent.id).holdings)
        self.assertEqual(self.house.idle_run(agent)["shut"], 0)  # holding is acting: no bench-time pull
        self.at(BELL)
        self.house.tick()
        self.assertEqual(book.account(agent.id).holdings, {})
        self.assertEqual(self.decided, [agent.id, agent.id])

    def test_an_open_desk_naming_a_coin_still_wakes_and_only_its_stock_entry_waits(self):
        agent = self.etf("mixed", MIXED)
        self.assertEqual(agent.specialty, "alpaca-open")
        self.at(NIGHT)
        self.house.tick()
        self.assertEqual(self.decided, [agent.id])  # a coin trades all night
        book = self.house.books["alpaca-paper"]
        self.assertIn(self.btc.key, book.account(agent.id).holdings)
        self.assertNotIn(self.spy.key, book.account(agent.id).holdings)
        (reason,) = self.refusals(agent)
        self.assertIn("outside the regular session no stock or option entry is sent", reason)
        self.assertFalse([o for o in self.broker.submitted if "SPY" in json.dumps(o, default=str)])

    def test_the_skipped_wakes_are_counted_in_health(self):
        agent = self.etf()
        self.at(NIGHT)
        self.house.tick()
        self.clock.advance(15 * 60)
        self.house.tick()
        health = json.loads((Path(self.house.root) / "health.json").read_text())
        skipped = health["wakes_skipped"]
        self.assertEqual((skipped["count"], skipped["by_desk"]), (2, {"alpaca-index-etfs": 2}))
        self.assertEqual(skipped["last_at"], now_iso(self.clock))


if __name__ == "__main__":
    import unittest

    unittest.main()
