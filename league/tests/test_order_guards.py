"""The House's order guards (Sept 22, 2026): venue facts in front of the book, a 403 that is a
refusal, and resting entries nobody is managing.

Measured on the Alpaca paper book over the 48 hours to Sept 22, 2026: 55 orders refused under the
venue's $10 crypto minimum, 63 refused "insufficient balance", each booked `unknown` and then a
second time as "the venue has no such order"; and a crypto agent vetoed by the frontier auditor
partly for sizing that ignored the $10 minimum and resting buys with no stale guard. Every test
here runs on fake venues and fake transports; nothing reaches the network.
"""

from __future__ import annotations

import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from ltcm.adapters import AlpacaCredentials
from ltcm.adapters.alpaca import DATA_BASE, PAPER_BASE, AlpacaBroker
from ltcm.tests.fakes import FakeTransport

from league.auditor import order_outcomes
from league.book import Book, Intent, Limits
from league.fees import Fees
from league.ledger import Ledger, now_iso
from league.preaudit import HOUSE_REFUSALS, PreAudit
from league.tests.fakes import Clock
from league.tests.test_house import BUYER, HouseCase
from league.venues import CENT, SUB_PENNY, instrument_for, min_order_usd, price_increment, snap_limit

D = Decimal

#: Bids far under the market once, then leaves the bid to rest.
RESTER = '''
NEEDS = {"venue": "alpaca", "horizon": "hour", "style": "test-rester", "symbols": ["BTC/USD"],
         "bars": {"timeframe": "5Min", "limit": 10}, "wake_minutes": 5}
PARAMS = {}

def decide(ctx):
    if ctx["memory"].get("placed"):
        return {"intents": [], "thought": "resting", "memory": ctx["memory"]}
    return {"intents": [{"symbol": "BTC/USD", "side": "buy", "quantity": 0.0003, "type": "limit", "limit_price": 75000,
                         "reason": "a bid far under the market"}], "thought": "bidding", "memory": {"placed": True}}
'''

#: Buys, then offers what it holds far over the market, then leaves the offer to rest.
EXITER = '''
NEEDS = {"venue": "alpaca", "horizon": "hour", "style": "test-exiter", "symbols": ["BTC/USD"],
         "bars": {"timeframe": "5Min", "limit": 10}, "wake_minutes": 5}
PARAMS = {}

def decide(ctx):
    held = [p for p in ctx["positions"] if p["symbol"] == "BTC/USD"]
    if ctx["memory"].get("offered"):
        return {"intents": [], "thought": "offered", "memory": ctx["memory"]}
    if held:
        return {"intents": [{"symbol": "BTC/USD", "side": "sell", "quantity": held[0]["quantity"], "type": "limit", "limit_price": 85000,
                             "reason": "take profit far above"}], "thought": "offer", "memory": {"offered": True}}
    return {"intents": [{"symbol": "BTC/USD", "side": "buy", "notional_usd": 20, "type": "market", "reason": "entry"}], "thought": "buy"}
'''

#: A limit bid priced to the thousandth of a dollar.
SNAPPER = '''
NEEDS = {"venue": "alpaca", "horizon": "hour", "style": "test-snapper", "symbols": ["BTC/USD"],
         "bars": {"timeframe": "5Min", "limit": 10}, "wake_minutes": 5}
PARAMS = {}

def decide(ctx):
    return {"intents": [{"symbol": "BTC/USD", "side": "buy", "quantity": 0.0002, "type": "limit", "limit_price": 75000.567,
                         "reason": "a bid under the market"}], "thought": "bid"}
'''

#: Asks for $8 of bitcoin every wake: under Alpaca's minimum.
SMALL = BUYER.replace('"notional_usd": ctx["params"]["notional"]', '"notional_usd": 8').replace("test-buyer", "test-small")


def raising(*args, **kwargs):
    raise RuntimeError("the feed is down")


# ------------------------------------------------------------------------------ venue facts
class VenueFactsTest(unittest.TestCase):
    spy = instrument_for("alpaca-paper", {"symbol": "SPY"})
    btc = instrument_for("alpaca-paper", {"symbol": "BTC/USD"})
    contract = instrument_for("kalshi-shadow", {"market": "KXBTCD-26SEP2017-T80999.99", "leg": "yes"})

    def test_buys_snap_down_and_sells_snap_up_to_the_cent_on_a_stock(self):
        tick = price_increment(self.spy, D("650.129"))
        self.assertEqual(tick, CENT)
        self.assertEqual(snap_limit(self.spy, "buy", D("650.129"), tick), D("650.12"))
        self.assertEqual(snap_limit(self.spy, "sell", D("650.121"), tick), D("650.13"))
        on_grid = D("650.10")
        self.assertIs(snap_limit(self.spy, "buy", on_grid, tick), on_grid)  # nothing to do: the price as asked

    def test_a_stock_under_a_dollar_is_quoted_to_a_hundredth_of_a_cent(self):
        self.assertEqual(price_increment(self.spy, D("0.51237")), SUB_PENNY)
        self.assertEqual(price_increment(self.spy, D("1")), CENT)
        self.assertEqual(snap_limit(self.spy, "buy", D("0.51237"), SUB_PENNY), D("0.5123"))
        self.assertIsNone(price_increment(self.spy, None))

    def test_a_coin_is_never_snapped_to_a_guessed_cent(self):
        self.assertIsNone(price_increment(self.btc, D("0.123456")))
        self.assertIsNone(price_increment(self.btc, D("0.123456"), asset={}))
        self.assertIsNone(price_increment(self.btc, D("0.123456"), asset={"price_increment": "0.01"}))  # not the venue's Decimal
        self.assertEqual(snap_limit(self.btc, "buy", D("0.123456"), None), D("0.123456"))
        tick = price_increment(self.btc, D("80000.567"), asset={"price_increment": D("1")})
        self.assertEqual((tick, snap_limit(self.btc, "buy", D("80000.567"), tick)), (D("1"), D("80000")))

    def test_kalshi_is_the_cent_unless_the_market_publishes_a_finer_band(self):
        self.assertEqual(price_increment(self.contract, D("0.955")), CENT)
        tapered = [{"start": D("0"), "end": D("0.10"), "step": D("0.001")}, {"start": D("0.10"), "end": D("0.90"), "step": D("0.01")},
                   {"start": D("0.90"), "end": D("1"), "step": D("0.001")}]
        self.assertEqual(price_increment(self.contract, D("0.955"), bands=tapered), D("0.001"))
        self.assertEqual(snap_limit(self.contract, "buy", D("0.955"), D("0.001")), D("0.955"))  # a favourite's bid in the tail stands
        self.assertEqual(price_increment(self.contract, D("0.555"), bands=tapered), CENT)
        self.assertEqual(snap_limit(self.contract, "buy", D("0.555"), CENT), D("0.55"))

    def test_a_snap_never_crosses_zero_or_an_event_contracts_dollar(self):
        self.assertEqual(snap_limit(self.spy, "buy", D("0.00005"), SUB_PENNY), D("0.00005"))
        self.assertEqual(snap_limit(self.contract, "sell", D("0.995"), CENT), D("0.995"))
        self.assertEqual(snap_limit(self.contract, "sell", D("0.985"), CENT), D("0.99"))

    def test_only_an_alpaca_coin_has_a_minimum(self):
        self.assertEqual(min_order_usd(self.btc), D("10"))
        self.assertEqual(min_order_usd(instrument_for("alpaca", {"symbol": "ETH/USD"})), D("10"))
        for instrument in (self.spy, self.contract, instrument_for("alpaca-paper", {"occ": "SPY261016C00650000"})):
            self.assertIsNone(min_order_usd(instrument), instrument.key)


# -------------------------------------------------------------------------- sizing and prices
class OrderGuardsTest(HouseCase):
    def sized(self, agent, *rows):
        adjusted: list[str] = []
        intents, dropped = self.house._intents(agent, self.house.books["alpaca-paper"],
                                               [{"type": "market", "reason": "test", **row} for row in rows], adjusted=adjusted)
        return intents, dropped, adjusted

    def test_a_ten_dollar_buy_the_step_floored_under_the_minimum_is_raised_one_step(self):
        agent = self.seated()
        self.house.seat(agent)
        (intent,), dropped, adjusted = self.sized(agent, {"symbol": "BTC/USD", "side": "buy", "notional_usd": 10})
        # $10 at the $80,005 ask floors to 0.000124992 BTC, $9.99998: Alpaca would refuse it.
        self.assertEqual(intent.quantity, D("0.000124993"))
        self.assertGreaterEqual(intent.quantity * D("80005"), D("10"))
        self.assertEqual(dropped, [])
        self.assertIn("raised one step", adjusted[0])
        self.assertIsNone(self.house.ledger.last("book.refused", agent=agent.id))
        (outcome,) = self.house.books["alpaca-paper"].submit([intent])  # the book, still the judge, takes it
        self.assertEqual(outcome.status, "filled")

    def test_a_buy_asked_under_ten_dollars_is_a_house_refusal_the_strategy_sees(self):
        agent = self.seated()
        intents, dropped, _ = self.sized(agent, {"symbol": "BTC/USD", "side": "buy", "notional_usd": 8},
                                         {"symbol": "BTC/USD", "side": "buy", "quantity": 0.0001, "type": "limit", "limit_price": 79000})
        self.assertEqual((intents, dropped), ([], []))  # not a malformed intent
        refusals = [e.payload for e in self.house.ledger.iter(kinds="book.refused", agent=agent.id)]
        self.assertEqual(len(refusals), 2)
        for row, asked in zip(refusals, ("$8.00", "$7.90")):
            self.assertEqual(row["book"], "alpaca-paper")
            self.assertTrue(row["intent_id"].startswith("in-"))
            self.assertIn(f"a {asked} buy is below the venue minimum of $10", row["reasons"][0])
            self.assertTrue(any(pattern in row["reasons"][0] for pattern in HOUSE_REFUSALS))
            self.assertEqual(row["instrument"]["asset_class"], "crypto")
        seen = order_outcomes(self.house.ledger, agent.id, "alpaca-paper")
        self.assertEqual([(o["status"], o["submitted_to_venue"]) for o in seen], [("refused", False)] * 2)
        self.assertEqual(self.broker.submitted, [])

    def test_a_sell_is_not_held_to_the_minimum(self):
        agent = self.seated()
        (intent,), dropped, adjusted = self.sized(agent, {"symbol": "BTC/USD", "side": "sell", "quantity": "0.0001"})
        self.assertEqual((intent.side, intent.quantity, dropped, adjusted), ("sell", D("0.0001"), [], []))
        self.assertIsNone(self.house.ledger.last("book.refused", agent=agent.id))

    def test_a_given_quantity_is_floored_to_the_instruments_step(self):
        agent = self.seated()
        intents, dropped, adjusted = self.sized(agent, {"symbol": "BTC/USD", "side": "sell", "quantity": "0.00012345678912"},
                                                {"symbol": "SPY", "side": "sell", "quantity": "2.5", "type": "limit", "limit_price": 650})
        self.assertEqual([i.quantity for i in intents], [D("0.000123456"), D("2.5")])  # nine decimals; fractional shares at a limit too (A7, Sept 23, 2026)
        self.assertEqual(dropped, [])
        self.assertEqual(len(adjusted), 1)
        self.assertIn("floored to 0.000123456", adjusted[0])

    def test_a_limit_is_snapped_to_the_venues_increment_and_the_wake_says_so(self):
        self.broker.asset = lambda symbol: {"price_increment": D("0.01")}  # what the venue's asset record would state
        agent = self.seated("snapper", SNAPPER)
        out = self.house.wake(agent)
        (intent,) = out["intents"]
        self.assertEqual(intent.limit_price, D("75000.56"))  # a bid snaps DOWN
        woke = self.house.ledger.last("agent.woke", agent=agent.id).payload
        self.assertEqual(woke["adjusted"], ["BTC/USD buy: limit 75000.567 snapped down to 75000.56 (the venue's 0.01 grid)"])
        (sell,), _, _ = self.sized(agent, {"symbol": "BTC/USD", "side": "sell", "quantity": "0.0001", "type": "limit",
                                           "limit_price": "85000.561"})
        self.assertEqual(sell.limit_price, D("85000.57"))  # an offer snaps UP

    def test_a_coins_price_is_left_alone_when_the_venue_has_not_stated_its_increment(self):
        agent = self.seated("snapper", SNAPPER)  # the fake venue has no asset record
        out = self.house.wake(agent)
        self.assertEqual(out["intents"][0].limit_price, D("75000.567"))
        self.assertNotIn("adjusted", self.house.ledger.last("agent.woke", agent=agent.id).payload)

    def test_the_snapshot_states_the_venues_rules_where_they_are_known(self):
        agent = self.seated()
        book = self.house.books["alpaca-paper"]
        self.assertEqual(self.house.snapshot(agent, book)["venue_rules"], {"BTC/USD": {"min_order_usd": 10.0}})
        self.broker.asset = lambda symbol: {"price_increment": D("0.01"), "min_order_size": D("0.0001")}
        self.assertEqual(self.house.snapshot(agent, book)["venue_rules"], {"BTC/USD": {"min_order_usd": 10.0, "price_increment": 0.01}})
        etf = self.house.spawn("scholes", "etf", BUYER.replace('"symbols": ["BTC/USD"]', '"symbols": ["SPY"]').replace("test-buyer", "etf"),
                               reason="test")
        self.house.evaluator.seat(etf.id, 1, "test")
        self.house.seat(etf)
        self.assertEqual(self.house.snapshot(etf, book)["venue_rules"], {"SPY": {"price_increment": 0.01}})

    def test_the_pre_audit_does_not_count_the_houses_minimum_against_the_strategy(self):
        agent = self.seated("small", SMALL)
        for _ in range(6):
            self.house.wake(agent)
            self.clock.advance(301)
        self.assertEqual(self.house.ledger.count(kinds="book.refused", agent=agent.id), 6)
        (found,) = [r for r in PreAudit(self.house.ledger, clock=self.clock).run(self.house) if r["agent"] == agent.id]
        self.assertTrue(found["final"])
        self.assertNotIn("refusals", found["flags"])
        self.assertNotIn("dropped_intents", found["flags"])


# ----------------------------------------------------------------------- resting entries
class StaleRestingTest(HouseCase):
    def orders(self, agent):
        return self.house.books["alpaca-paper"].open_orders(agent.id)

    def ticks(self, minutes):
        for _ in range(minutes // 5):
            self.clock.advance(300)
            self.house.tick()

    def test_an_entry_left_resting_by_failing_wakes_is_cancelled_once_the_allowance_is_up(self):
        agent = self.seated("rester", RESTER)
        self.house.tick()
        (order,) = self.orders(agent)
        self.assertEqual((order.side, order.status), ("buy", "accepted"))
        placed = self.house.ledger.last("agent.woke", agent=agent.id)
        self.data.bars = raising  # every wake from here on is skipped: no market data
        self.ticks(30)  # thirty minutes is the floor of the allowance (three wakes of five would be fifteen)
        self.assertEqual(len(self.orders(agent)), 1)
        self.assertEqual(self.broker.cancelled, [])
        self.ticks(5)
        self.assertEqual(self.orders(agent), [])
        self.assertEqual(len(self.broker.cancelled), 1)
        self.assertEqual(self.house.ledger.last("book.cancel", agent=agent.id).payload["order_id"], order.order_id)
        note = self.house.ledger.last("agent.inactive", agent=agent.id).payload
        self.assertEqual((note["reason"], note["order_id"], note["last_completed_wake"], note["book"]),
                         ("wakes_failing", order.order_id, placed.at, "alpaca-paper"))
        self.ticks(10)  # nothing is cancelled or noted twice
        self.assertEqual(len(self.broker.cancelled), 1)
        self.assertEqual(self.house.ledger.count(kinds="agent.inactive", agent=agent.id), 1)

    def test_a_resting_exit_is_never_cancelled(self):
        agent = self.seated("exiter", EXITER)
        self.house.tick()  # buys
        self.clock.advance(301)
        self.house.tick()  # offers what it holds
        (order,) = self.orders(agent)
        self.assertEqual(order.side, "sell")
        self.data.bars = raising
        self.ticks(60)
        self.assertEqual([o.order_id for o in self.orders(agent)], [order.order_id])
        self.assertEqual(self.broker.cancelled, [])
        self.assertIsNone(self.house.ledger.last("agent.inactive", agent=agent.id))

    def test_an_agent_whose_wakes_complete_keeps_its_resting_entries(self):
        agent = self.seated("rester", RESTER)
        self.house.tick()
        self.ticks(60)
        self.assertEqual(len(self.orders(agent)), 1)
        self.assertEqual(self.broker.cancelled, [])

    def test_a_restart_gives_the_strategy_the_whole_allowance_again(self):
        agent = self.seated("rester", RESTER)
        self.house.tick()
        self.house.close()
        self.clock.advance(2 * 3600)  # the floor was down for two hours
        self.house = self.new_house()
        self.data.bars = raising
        self.house.tick()  # a wake the House never attempted is not the strategy failing
        self.assertEqual(len(self.orders(agent)), 1)
        self.ticks(35)
        self.assertEqual(self.orders(agent), [])


# ------------------------------------------------------------------------- a 403 is a refusal
class ForbiddenOrderTest(unittest.TestCase):
    def test_a_403_to_the_order_post_is_booked_rejected_once_with_the_venues_reason(self):
        with tempfile.TemporaryDirectory() as root:
            clock = Clock()
            quote = {"quotes": {"AVAX/USD": {"bp": 24.99, "ap": 25.01, "t": now_iso(clock)}}}
            transport = FakeTransport({
                ("POST", PAPER_BASE + "/v2/orders"): (403, {}, b'{"code": 40310000, "message": "insufficient balance for AVAX"}'),
                DATA_BASE + "/v1beta3/crypto/us/latest/quotes*": quote,
                PAPER_BASE + "/v2/orders:by_client_order_id*": (404, {}, b'{"message": "order not found"}'),
            })
            broker = AlpacaBroker(AlpacaCredentials("key", "secret", paper=True), transport=transport, venue="alpaca-paper")
            ledger = Ledger(Path(root) / "ledger.sqlite", clock=clock)
            book = Book("alpaca-paper", broker, ledger, fees=Fees("alpaca"), real_money=False, clock=clock)
            book.limits["trader"] = Limits(D("100"), D("75"))
            book.stake("trader", "200")
            intent = Intent.new(agent="trader", instrument=instrument_for("alpaca-paper", {"symbol": "AVAX/USD"}), side="buy",
                                quantity="0.8", reason="test", created_at=now_iso(clock), nonce="1")
            (outcome,) = book.submit([intent])
            self.assertEqual(outcome.status, "rejected")
            self.assertIn("insufficient balance for AVAX", outcome.detail)
            book.poll()
            rows = [e.payload for e in ledger.iter(kinds="book.order")]
            self.assertEqual([r["status"] for r in rows], ["new", "rejected"])  # no `unknown`, no "never arrived" twin
            self.assertIn("HTTP 403 insufficient balance for AVAX", rows[-1]["reason"])
            self.assertEqual([c["method"] for c in transport.calls if "/v2/orders" in c["path"]], ["POST"])
            self.assertEqual(book.open_orders(), [])
            ledger.close()


if __name__ == "__main__":
    unittest.main()
