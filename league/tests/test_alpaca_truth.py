"""Alpaca stocks and options, Sept 23, 2026: what agents are shown is what the book takes, and a
session desk is awake for the open.

Measured that day, read-only, on the live ledger:

- haghani-37, a $25 crypto bunt shown $12.50 a position and an order, had 10 real refusals: 3 once
  its equity fell to $24.89-24.96 (the book holds a position and an order to half the CURRENT
  equity), and 7 at equity at or above its stake, from limit bids sized to $12.50 at their own
  price that the book's position rule values at the ask.
- An options bunt is staked $40 and was shown $40 and a chain filtered at $0.40 a share, while half
  its equity lets it buy $20 a contract.
- The options desk woke at 13:29:55Z on a clock 4.3-4.6 s slow, saw a shut market, and 5 of its 8
  agents did not wake again until 14:01Z or later.
- 170-280 of about 300 option quotes a snapshot carried were stamped later than the snapshot's
  `now`, which was read before the chain was fetched.

Nothing here changes a rule the book enforces, a stake or a cap. Every test runs on fake venues.
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from decimal import ROUND_DOWN, Decimal
from pathlib import Path
from unittest.mock import patch

from ltcm.data import market_open_at, to_datetime

from league import seeds
from league.book import Intent
from league.constitution import CONSTITUTION
from league.economy import load_game
from league.house import OPEN_WAKE_SECONDS, House, Settings
from league.ledger import now_iso
from league.sandbox import LocalSandbox
from league.tests.fakes import Clock, FakeBroker
from league.tests.test_house import BUYER
from league.tests.test_ladder import InProcessSandbox
from league.venues import instrument_for

D = Decimal
CENT = D("0.01")
MONDAY_1100_NY = 1790002800.0  # 2026-09-21T15:00:00Z: the session is open


def at(stamp: str) -> float:
    return datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone(timezone.utc).timestamp()


#: Bids 1% under the ask, sized to exactly the order limit it is shown, at its own price.
BIDDER = '''
NEEDS = {"venue": "alpaca", "horizon": "hour", "style": "test-bidder", "symbols": ["BTC/USD"],
         "bars": {"timeframe": "5Min", "limit": 10}, "wake_minutes": 5}
PARAMS = {}

def decide(ctx):
    if ctx["positions"] or ctx["open_orders"]:
        return {"intents": [], "thought": "working"}
    ask = ctx["quotes"]["BTC/USD"]["ask"]
    return {"intents": [{"symbol": "BTC/USD", "side": "buy", "notional_usd": ctx["limits"]["max_order_usd"], "type": "limit",
                         "limit_price": round(ask * 0.99, 2), "reason": "a bid under the ask, sized to the limit"}],
            "thought": "bid"}
'''

#: Each wake: cancels any resting bid and bids again 1% under the ask, sized to the order limit it
#: is shown -- a strategy that reprices its bid every wake (review of PR #189, Sept 23, 2026).
REPRICER = '''
NEEDS = {"venue": "alpaca", "horizon": "hour", "style": "test-repricer", "symbols": ["BTC/USD"],
         "bars": {"timeframe": "5Min", "limit": 10}, "wake_minutes": 5}
PARAMS = {}

def decide(ctx):
    if ctx["positions"]:
        return {"intents": [], "thought": "holding"}
    ask = ctx["quotes"]["BTC/USD"]["ask"]
    return {"cancels": [o["order_id"] for o in ctx["open_orders"]],
            "intents": [{"symbol": "BTC/USD", "side": "buy", "notional_usd": ctx["limits"]["max_order_usd"], "type": "limit",
                         "limit_price": round(ask * 0.99, 2), "reason": "reprice"}],
            "thought": "reprice"}
'''

#: An index-ETF desk strategy (it keeps the session) that only watches.
ETF_WATCHER = '''
NEEDS = {"venue": "alpaca", "horizon": "day", "style": "test-etf-watcher", "symbols": ["SPY"],
         "bars": {"timeframe": "5Min", "limit": 10}, "wake_minutes": 30}
PARAMS = {}

def decide(ctx):
    return {"intents": [], "thought": "watching"}
'''

#: A crypto desk strategy (no session) that only watches.
COIN_WATCHER = (ETF_WATCHER.replace('"SPY"', '"BTC/USD"').replace("test-etf-watcher", "test-coin-watcher")
                .replace('"horizon": "day"', '"horizon": "hour"'))


class Touches:
    """Bars and the touch by symbol. Each symbol's quote read takes `lag` seconds on the House's
    clock and is stamped with the moment it was read, as a live feed's are."""

    def __init__(self, clock: Clock, prices: dict[str, float], lag: float = 0.0):
        self.clock, self.prices, self.lag = clock, prices, lag
        self.served: dict[str, dict] = {}

    def bars(self, symbols, timeframe, *, start=None, end=None, limit=120):
        return {s: [{"t": "2026-09-21T14:00:00Z", "o": self.prices.get(s, 100.0), "h": self.prices.get(s, 100.0),
                     "l": self.prices.get(s, 100.0), "c": self.prices.get(s, 100.0), "v": 1.0}] for s in symbols}

    def quotes(self, symbols):
        out = {}
        for symbol in symbols:
            self.clock.advance(self.lag)
            price = self.prices.get(symbol, 100.0)
            out[symbol] = {"bid": price - 0.01, "ask": price + 0.01, "t": now_iso(self.clock)}
        self.served.update({k: dict(v) for k, v in out.items()})
        return out


def chain_of_f(clock: Clock, lag: float = 0.0):
    """An option chain on F only: three calls near the money, their asks 19, 25 and 40 cents."""

    def option_chain(symbol, *, expiry_from, expiry_to):
        clock.advance(lag)
        if symbol != "F":
            return []
        row = lambda occ, strike, bid, ask: {"symbol": occ, "underlying": "F", "expiry": "2026-10-09", "strike": strike, "right": "call",
                                             "bid": bid, "ask": ask, "as_of": now_iso(clock), "iv": 0.3, "delta": 0.5, "volume": 1.0}
        return [row("F261009C00013000", 13.0, 0.17, 0.19), row("F261009C00013500", 13.5, 0.23, 0.25),
                row("F261009C00012500", 12.5, 0.38, 0.40)]

    return option_chain


class RealAlpaca(unittest.TestCase):
    """A House with a real (fake) Alpaca venue of $500, during a regular session."""

    def setUp(self):
        strategies = patch("league.strategies.all_strategies", return_value=[])
        strategies.start()
        self.addCleanup(strategies.stop)
        envelope = patch.dict(CONSTITUTION["tuition"], {"max_loss_usd": "500"})  # room for a bunt and an options bunt
        envelope.start()
        self.addCleanup(envelope.stop)
        self.dir = tempfile.TemporaryDirectory()
        self.clock = Clock(MONDAY_1100_NY)
        self.paper, self.real = FakeBroker("alpaca-paper"), FakeBroker("alpaca", cash="500")
        self.data = Touches(self.clock, {"BTC/USD": 80000.0, "F": 13.0})
        self.btc = instrument_for("alpaca", {"symbol": "BTC/USD"})
        self.eth = instrument_for("alpaca", {"symbol": "ETH/USD"})
        for broker in (self.paper, self.real):
            broker.clock_iso = now_iso(self.clock)
            broker.set_quote(instrument_for(broker.venue, {"symbol": "BTC/USD"}), "79999.99", "80000.01")
        self.real.set_quote(self.eth, "2000", "2010")
        game = load_game()
        game["economy"]["min_population"] = 0
        game["economy"]["newcomer_seconds"] = 10 ** 9
        self.house = House(
            Path(self.dir.name) / "house", brokers={"alpaca-paper": self.paper, "alpaca": self.real}, sandbox=InProcessSandbox(),
            alpaca_data=self.data, clock=self.clock, settings=Settings(mark_every_seconds=0, research=False, real_money=True), game=game)
        self.book = self.house.books["alpaca"]

    def tearDown(self):
        self.house.close(wait=None)
        self.dir.cleanup()

    def bunt(self, name, code, **kw):
        agent = self.house.spawn(name, name, code, reason="test", **kw)
        self.house.evaluator.seat(agent.id, 2, "test: a bunt")
        self.house._state["tried"][agent.id] = agent.code_sha256
        self.house.seat(agent)
        return agent

    def half_equity_less_a_cent(self, agent) -> Decimal:
        return (self.book.equity(agent.id) * D("0.5") - CENT).quantize(CENT, rounding=ROUND_DOWN)


class TruthfulLimits(RealAlpaca):
    def test_a_bunt_whose_equity_fell_is_shown_half_of_it_less_a_cent_and_the_book_takes_that(self):
        agent = self.bunt("buyer", BUYER)
        self.assertEqual((self.book.account(agent.id).staked, self.book.limits[agent.id].max_order_usd), (D("25"), D("12.50")))
        # It bought $5 of ether at the ask; marked at the bid, with the fee, its equity is under $25.
        bought = self.book.submit([Intent.new(agent=agent.id, instrument=self.eth, side="buy", quantity="0.0025", reason="t",
                                              created_at=now_iso(self.clock), nonce="eth")])[0]
        self.assertEqual(bought.status, "filled", bought.detail)
        self.assertLess(self.book.equity(agent.id), D("25"))
        line = self.half_equity_less_a_cent(agent)
        self.assertLess(line, D("12.50"))

        ctx = self.house.snapshot(agent, self.book)
        self.assertEqual(ctx["limits"], {"max_position_usd": float(line), "max_order_usd": float(line)})
        self.assertEqual(self.book.limits[agent.id].max_order_usd, D("12.50"))  # the seat's cap, enforced as before

        now, quote = now_iso(self.clock), self.real.quote(self.btc)
        # The seat's $12.50, the number it used to be shown: the book refuses it as over half the equity.
        seat = Intent.new(agent=agent.id, instrument=self.btc, side="buy", quantity=(D("12.50") / quote.ask).quantize(D("1e-9"), rounding=ROUND_DOWN),
                          reason="t", created_at=now, nonce="seat")
        self.assertTrue(any("50% of desk equity" in r for r in self.book.check(seat, quote, now)))
        # What it is shown now, asked for as a strategy asks for it: the book takes it.
        intents, dropped = self.house._intents(agent, self.book, [{"symbol": "BTC/USD", "side": "buy", "type": "market",
                                                                   "notional_usd": ctx["limits"]["max_order_usd"], "reason": "t"}])
        self.assertEqual(dropped, [])
        self.assertEqual(self.book.check(intents[0], quote, now), [])

    def test_a_bid_under_the_ask_sized_to_its_limit_is_trimmed_to_what_the_ask_values_and_is_not_refused(self):
        agent = self.bunt("bidder", BIDDER)
        self.assertEqual(self.book.equity(agent.id), D("25"))
        self.house._state["next_wake"][agent.id] = 0
        outcome = self.house.wake(agent)
        self.assertEqual(len(outcome["intents"]), 1, outcome)
        intent = outcome["intents"][0]
        ask = self.real.quote(self.btc).ask
        self.assertLessEqual(intent.quantity * ask, self.half_equity_less_a_cent(agent))  # valued at the ask, as the book does
        self.assertLess(intent.limit_price, ask)
        woke = self.house.ledger.last("agent.woke", agent=agent.id).payload
        self.assertTrue(any("trimmed" in note and "at the ask" in note for note in woke.get("adjusted") or []), woke)
        sent = self.house._submit_wakes("alpaca", [outcome])
        self.assertEqual(len(sent), 1)
        self.assertNotEqual(sent[0].status, "refused", sent[0].detail)
        self.assertEqual(list(self.house.ledger.iter(kinds="book.refused", agent=agent.id)), [])

    def test_a_trim_only_ever_shrinks_a_real_buy_and_never_touches_one_that_fits_or_a_practice_one(self):
        agent = self.bunt("bidder", BIDDER)
        quote = self.real.quote(self.btc)
        small = [{"symbol": "BTC/USD", "side": "buy", "type": "limit", "limit_price": str(quote.bid), "notional_usd": 11, "reason": "t"}]
        adjusted: list[str] = []
        intents, _ = self.house._intents(agent, self.book, small, adjusted=adjusted)
        self.assertEqual(adjusted, [])
        self.assertEqual(intents[0].quantity, (D(11) / quote.bid).quantize(D("1e-9"), rounding=ROUND_DOWN))
        # Trimmed under Alpaca's $10 crypto minimum it would be refused at the venue: left as asked for the book to judge.
        self.assertIsNone(self.house._fit_real_entry(agent, self.book, self.btc, D("0.001"), None, D("1e-9"), D("30")))
        paper_agent = self.house.spawn("paper-bidder", "paper-bidder", BIDDER.replace("test-bidder", "test-paper-bidder"), reason="t")
        self.house.evaluator.seat(paper_agent.id, 1, "test")
        self.house.seat(paper_agent)
        paper = self.house.books["alpaca-paper"]
        big = [{"symbol": "BTC/USD", "side": "buy", "type": "limit", "limit_price": "79000", "notional_usd": 75, "reason": "t"}]
        adjusted = []
        intents, _ = self.house._intents(paper_agent, paper, big, adjusted=adjusted)
        self.assertEqual(adjusted, [])  # practice is judged by its own book as before
        self.assertEqual(self.house.snapshot(paper_agent, paper)["limits"], {"max_position_usd": 100.0, "max_order_usd": 75.0})

    def test_a_bid_cancelled_and_replaced_in_one_decision_is_trimmed_and_not_refused(self):
        # `wake` sizes a decision's orders before it applies the decision's cancels, and the book
        # judges them after. Counting the bid being cancelled left a room under the $10 minimum, so
        # the replacement went untrimmed and was refused at the ask: the agent had no order at all.
        agent = self.bunt("repricer", REPRICER)
        ask = self.real.quote(self.btc).ask
        resting = None
        for n in range(2):
            self.house._state["next_wake"][agent.id] = 0
            outcome = self.house.wake(agent)
            self.assertEqual(len(outcome["intents"]), 1, (n, outcome))
            intent = outcome["intents"][0]
            self.assertLessEqual(intent.quantity * ask, self.half_equity_less_a_cent(agent), n)
            woke = self.house.ledger.last("agent.woke", agent=agent.id).payload
            self.assertTrue(any("trimmed" in note for note in woke.get("adjusted") or []), (n, woke))
            self.assertEqual(woke["cancels"], n)  # the second wake cancelled the first wake's bid
            sent = self.house._submit_wakes("alpaca", [outcome])
            self.assertEqual([o.status for o in sent], ["resting"], (n, [o.detail for o in sent]))
            working = self.book.open_orders(agent.id)
            self.assertEqual(len(working), 1, n)  # the replacement, and not the bid it replaced
            self.assertNotEqual(working[0].order_id, resting, n)
            resting = working[0].order_id
            self.clock.advance(300)
        self.assertEqual(list(self.house.ledger.iter(kinds="book.refused", agent=agent.id)), [])

    def test_a_resting_bid_is_counted_against_a_new_one_unless_the_decision_cancels_it(self):
        agent = self.bunt("bidder", BIDDER)
        self.house._state["next_wake"][agent.id] = 0
        sent = self.house._submit_wakes("alpaca", [self.house.wake(agent)])
        self.assertEqual([o.status for o in sent], ["resting"], [o.detail for o in sent])
        (working,) = self.book.open_orders(agent.id)
        limit = working.limit_price
        asked = (D("12.49") / limit).quantize(D("1e-9"), rounding=ROUND_DOWN)
        # Kept, the resting bid leaves a room under the $10 minimum: left as asked for the book to judge.
        self.assertIsNone(self.house._fit_real_entry(agent, self.book, self.btc, asked, limit, D("1e-9"), D("10")))
        self.assertIsNone(self.house._fit_real_entry(agent, self.book, self.btc, asked, limit, D("1e-9"), D("10"),
                                                     cancelling={"someone-else"}))
        # Cancelled by the same decision, it is not counted: the new bid is trimmed to fit at the ask.
        fitted = self.house._fit_real_entry(agent, self.book, self.btc, asked, limit, D("1e-9"), D("10"),
                                            cancelling={working.order_id})
        self.assertIsNotNone(fitted)
        ask = self.real.quote(self.btc).ask
        self.assertLess(fitted[0], asked)
        self.assertLessEqual(fitted[0] * ask, self.half_equity_less_a_cent(agent))
        self.assertGreaterEqual(fitted[0] * limit, D("10"))

    def test_an_options_bunt_is_shown_forty_dollars_and_only_contracts_the_book_takes(self):
        """A2a (Sept 23, 2026): staked `allocator.option_bunt_usd` $80, so one $40 contract fits under half its
        equity (at $40 it was shown $19.99 and a chain of contracts up to 19 cents). The chain is filtered a
        cent under the line (`_real_limits`), so it shows contracts up to 39 cents while the book takes $40."""
        self.real.option_chain = chain_of_f(self.clock)
        agent = self.bunt("options-breakout", seeds.load("options-breakout"), specialty="alpaca-options")
        self.assertEqual(self.book.account(agent.id).staked, D("80"))
        self.assertEqual(self.book.limits[agent.id].max_order_usd, D("40"))  # the seat's cap: half the stake

        ctx = self.house.snapshot(agent, self.book)
        self.assertEqual(ctx["limits"], {"max_position_usd": 39.99, "max_order_usd": 39.99})
        self.assertEqual([row["occ"] for row in ctx["chain"]], ["F261009C00013000", "F261009C00013500"])  # the $19 and $25 contracts

        now = now_iso(self.clock)
        for occ, bid, ask, takes in (("F261009C00013000", "0.17", "0.19", True), ("F261009C00013500", "0.23", "0.25", True),
                                     ("F261009C00012500", "0.38", "0.40", True)):
            contract = instrument_for("alpaca", {"occ": occ})
            self.real.set_quote(contract, bid, ask)
            one = Intent.new(agent=agent.id, instrument=contract, side="buy", quantity="1", order_type="limit", limit_price=ask,
                             reason="t", created_at=now, nonce=occ)
            reasons = self.book.check(one, self.real.quote(contract), now)
            self.assertEqual(reasons == [], takes, (occ, reasons))


class OpenWake(unittest.TestCase):
    """Session desks are woken a few seconds after the regular open when they would sleep through it."""

    OPEN = at("2026-09-23T13:30:00Z")  # a Wednesday, 09:30 in New York

    def setUp(self):
        strategies = patch("league.strategies.all_strategies", return_value=[])
        strategies.start()
        self.addCleanup(strategies.stop)
        self.dir = tempfile.TemporaryDirectory()
        self.clock = Clock(self.OPEN - 5)
        self.broker = FakeBroker("alpaca-paper")
        self.data = Touches(self.clock, {"SPY": 660.0, "BTC/USD": 80000.0})
        game = load_game()
        game["economy"]["min_population"] = 0
        game["economy"]["newcomer_seconds"] = 10 ** 9
        self.house = House(Path(self.dir.name) / "house", brokers={"alpaca-paper": self.broker}, game=game,
                           sandbox=LocalSandbox(Path(self.dir.name) / "boxes"), alpaca_data=self.data, clock=self.clock,
                           settings=Settings(mark_every_seconds=0, research=False))

    def tearDown(self):
        self.house.close(wait=None)
        self.dir.cleanup()

    def seated(self, name, code):
        agent = self.house.spawn(name, name, code, reason="test")
        self.house.evaluator.seat(agent.id, 1, "test")
        self.house._state["tried"][agent.id] = agent.code_sha256
        return agent

    def woken_at(self, agent, moment: float) -> float:
        self.clock.now = moment
        self.broker.clock_iso = now_iso(self.clock)
        self.house.wake(agent)
        return self.house._state["next_wake"][agent.id]

    def test_an_etf_desk_woken_just_before_the_open_is_due_again_a_few_seconds_after_it(self):
        agent = self.seated("etf", ETF_WATCHER)
        self.assertTrue(self.house.niche_of(agent).keeps_hours(agent.needs))
        due = self.woken_at(agent, self.OPEN - 5)  # 13:29:55Z, as the options desk woke on Sept 23
        self.assertEqual(due, self.OPEN + OPEN_WAKE_SECONDS)  # not 13:59:55Z
        self.assertTrue(market_open_at(now_iso(lambda: due)))
        self.clock.now = due - 1
        self.assertNotIn(agent.id, [a.id for a in self.house.due()])
        self.clock.now = due
        self.assertIn(agent.id, [a.id for a in self.house.due()])
        # From that wake its own cadence runs on.
        self.assertEqual(self.woken_at(agent, due), due + 30 * 60)

    def test_no_other_wake_moves(self):
        etf, coin = self.seated("etf", ETF_WATCHER), self.seated("coin", COIN_WATCHER)
        self.assertFalse(self.house.niche_of(coin).keeps_hours(coin.needs))
        self.assertEqual(self.woken_at(coin, self.OPEN - 5), self.OPEN - 5 + 30 * 60)  # coins keep no session
        self.assertEqual(self.woken_at(etf, self.OPEN - 3600), self.OPEN - 1800)  # the next wake is still before the open
        self.assertEqual(self.woken_at(etf, self.OPEN), self.OPEN + 1800)  # woken in the session
        self.assertEqual(self.woken_at(etf, self.OPEN + 7200), self.OPEN + 9000)
        saturday = at("2026-09-26T15:00:00Z")
        self.assertEqual(self.woken_at(etf, saturday), saturday + 1800)  # no session within its wake

    def test_market_data_read_before_the_open_is_not_served_after_it(self):
        reads = []

        def build():
            reads.append(self.clock())
            return {"SPY": {"bid": 1.0, "ask": 1.02}}

        self.clock.now = self.OPEN - 2
        self.house._cached("quotes:SPY", 120, build)
        self.clock.now = self.OPEN - 1
        self.house._cached("quotes:SPY", 120, build)
        self.assertEqual(len(reads), 1)  # before the open, the cache serves as it always did
        self.clock.now = self.OPEN + OPEN_WAKE_SECONDS
        self.house._cached("quotes:SPY", 120, build)
        self.assertEqual(len(reads), 2)  # read again: the session has opened since
        self.clock.now += 10
        self.house._cached("quotes:SPY", 120, build)
        self.assertEqual(len(reads), 2)  # and served from the cache again after that

    def test_a_fetch_that_began_before_the_open_and_ended_after_it_is_read_again(self):
        reads = []

        def slow():
            reads.append(self.clock())
            self.clock.advance(4)  # an options chain of eight underlyings takes seconds
            return []

        self.clock.now = self.OPEN - 2
        self.house._cached("chain:F", 120, slow)
        self.clock.now = self.OPEN + OPEN_WAKE_SECONDS
        self.house._cached("chain:F", 120, slow)
        self.assertEqual(len(reads), 2)


class StampedAfterTheData(unittest.TestCase):
    """`now` is read after the market data, so no quote in a snapshot is later than it."""

    def setUp(self):
        strategies = patch("league.strategies.all_strategies", return_value=[])
        strategies.start()
        self.addCleanup(strategies.stop)
        self.dir = tempfile.TemporaryDirectory()
        self.clock = Clock(MONDAY_1100_NY)
        self.broker = FakeBroker("alpaca-paper")
        self.broker.clock_iso = now_iso(self.clock)
        self.data = Touches(self.clock, {"SPY": 660.0, "F": 13.0}, lag=1.5)
        game = load_game()
        game["economy"]["min_population"] = 0
        game["economy"]["newcomer_seconds"] = 10 ** 9
        self.house = House(Path(self.dir.name) / "house", brokers={"alpaca-paper": self.broker}, game=game,
                           sandbox=LocalSandbox(Path(self.dir.name) / "boxes"), alpaca_data=self.data, clock=self.clock,
                           settings=Settings(mark_every_seconds=0, research=False))
        self.book = self.house.books["alpaca-paper"]

    def tearDown(self):
        self.house.close(wait=None)
        self.dir.cleanup()

    def test_a_stock_snapshot_is_stamped_after_its_quotes_and_leaves_their_stamps_alone(self):
        agent = self.house.spawn("etf", "etf", ETF_WATCHER, reason="test")
        self.house.evaluator.seat(agent.id, 1, "test")
        self.house.seat(agent)
        ctx = self.house.snapshot(agent, self.book)
        now = to_datetime(ctx["now"])
        self.assertEqual(ctx["quotes"], self.data.served)  # every quote's own stamp, as the feed gave it
        for symbol, quote in ctx["quotes"].items():
            self.assertLessEqual(to_datetime(quote["t"]), now, symbol)
        self.assertEqual(next(iter(ctx)), "now")

    def test_an_options_snapshot_is_stamped_after_its_chain(self):
        self.broker.option_chain = chain_of_f(self.clock, lag=1.0)
        agent = self.house.spawn("options-breakout", "options-breakout", seeds.load("options-breakout"), reason="test",
                                 specialty="alpaca-options")
        self.house.seat(agent)
        ctx = self.house.snapshot(agent, self.book)
        self.assertTrue(ctx["chain"])
        now = to_datetime(ctx["now"])
        for row in ctx["chain"]:
            self.assertLessEqual(to_datetime(row["as_of"]), now, row["occ"])


if __name__ == "__main__":
    unittest.main()
