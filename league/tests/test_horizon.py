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
from league.tapes import parse_time
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

    def test_the_houses_own_exit_stands_until_the_venue_reports_it(self):
        """The review of #297 (Sept 25, 2026): the rule cancelled every working order in the coin -- its own
        exit too -- and sent the exit again under the same nonce, which the book refused as a duplicate, so a
        market sell the venue had not reported yet left the position with no exit until the hour turned."""
        agent = self.house.spawn("holder", "test-family", HOLDER, reason="test")
        self.house.evaluator.seat(agent.id, 1, "test")
        self.house._state["tried"][agent.id] = agent.code_sha256
        self.house.tick()
        book = self.house.books["alpaca-paper"]
        self.assertIn(self.btc.key, book.account(agent.id).holdings)
        self.clock.advance(49 * 3600)
        self.broker.clock_iso = now_iso(self.clock)
        self.broker.asynchronous = True  # Alpaca's habit: a market order is accepted, and filled on a later read
        broker = self.broker

        def cancel_before_the_fill(order_id):  # the venue takes a cancel that reaches it before the fill
            for order in broker.orders.values():
                if order_id in (order.id, order.broker_order_id):
                    broker._pending.pop(order.id, None)
                    if not order.terminal:
                        order.status = "cancelled"
                        broker.cancelled.append(order.id)
                    return order
            raise AssertionError(order_id)

        broker.cancel = cancel_before_the_fill
        self.assertEqual(self.house._enforce_horizon(), 1)
        sent = book.open_orders(agent.id)
        self.assertEqual(len(sent), 1)  # sent, not yet reported
        self.house._enforce_horizon()  # the next tick, before the venue's minute pass has read it
        self.assertEqual(broker.cancelled, [])  # its own exit stands
        self.assertEqual([w.order_id for w in book.open_orders(agent.id)], [sent[0].order_id])
        sells = [e for e in self.house.ledger.iter(kinds="agent.intent", agent=agent.id) if e.payload.get("side") == "sell"]
        self.assertEqual(len(sells), 1)  # never a second sell beside it
        book.poll()
        self.assertEqual(book.account(agent.id).holdings, {})
        self.assertTrue(book.reconcile().ok)

    def test_an_exit_the_venue_cancelled_is_sent_again_at_once_under_a_new_nonce(self):
        agent = self.house.spawn("holder", "test-family", HOLDER, reason="test")
        self.house.evaluator.seat(agent.id, 1, "test")
        self.house._state["tried"][agent.id] = agent.code_sha256
        self.house.tick()
        book = self.house.books["alpaca-paper"]
        self.clock.advance(49 * 3600)
        self.broker.clock_iso = now_iso(self.clock)
        self.broker.asynchronous = True
        self.house._enforce_horizon()
        (sent,) = book.open_orders(agent.id)
        self.broker._pending.pop(sent.order_id, None)  # the venue cancels it unfilled (an Alpaca crypto order can expire)
        self.broker.orders[sent.order_id].status = "cancelled"
        book.poll()
        self.assertEqual(book.open_orders(agent.id), [])
        self.assertIn(self.btc.key, book.account(agent.id).holdings)
        self.assertEqual(self.house._enforce_horizon(), 1)  # the same hour: a new intent, not the cancelled one's duplicate
        book.poll()
        self.assertEqual(book.account(agent.id).holdings, {})
        self.assertTrue(book.reconcile().ok)

    def test_the_crypto_rule_can_be_switched_off_in_the_game_file(self):
        self.house.game["horizon"]["crypto_max_hold_hours"] = 0
        agent = self.house.spawn("holder", "test-family", HOLDER, reason="test")
        self.house.evaluator.seat(agent.id, 1, "test")
        self.house._state["tried"][agent.id] = agent.code_sha256
        self.house.tick()
        self.clock.advance(100 * 3600)
        self.broker.clock_iso = now_iso(self.clock)
        self.assertEqual(self.house._enforce_horizon(), 0)
        self.assertIn(self.btc.key, self.house.books["alpaca-paper"].account(agent.id).holdings)


#: A daily prices-desk strategy that bids every favourite it is shown, and remembers the hours it saw.
DIESEL_BIDDER = '''
NEEDS = {"venue": "kalshi", "horizon": "day", "style": "test-diesel", "series": ["KXDIESELD"], "max_hours_to_close": 30,
         "wake_minutes": 60}
PARAMS = {}

def decide(ctx):
    return {"intents": [{"market": m["market"], "leg": "yes", "side": "buy", "quantity": 1, "type": "limit", "limit_price": 0.96,
                         "post_only": True, "reason": "a resting bid on a favourite"} for m in ctx["markets"]],
            "thought": "bidding", "memory": {"hours": {m["market"]: m["hours_to_resolve"] for m in ctx["markets"]}}}
'''


class HorizonBySchedule(unittest.TestCase):
    """X2 (Sept 24, 2026): the horizon rule judges a Kalshi market by its scheduled (expected)
    expiration when the venue gives one, by its close otherwise, and its refusal says which.

    Measured on the T0 snapshot (ledger to 01:41Z Sept 24): 138 horizon refusals, 71 of them on the
    daily diesel print (KXDIESELD-26SEP21 34, -26SEP22 36, -26SEP23 1; hawkins-3 27, hawkins-9 16,
    hawkins-8 14, hawkins-2 14), each "expected to resolve in 171-185 hours" while the market stopped
    trading a few hours later. The venue's "expected" expiration for that print is a deadline a week
    on (it equals its latest; review of #249), so P1 judges it by its close plus the diesel series'
    measured settle lag (`tapes.SettleLags`, fed by the settled markets the House's tapes read), and
    by the deadline while that cannot be measured. The close stands in only for a market the venue
    gives no expected expiration, of which none was seen."""

    def setUp(self):
        from league.tapes import KalshiData
        from league.tests.test_ladder import InProcessSandbox
        from league.tests.test_tapes import FakeMarketData, ScheduledExpirationTest
        from ltcm.data.kalshi import KalshiMarketData
        from league.house import House, Settings
        from league.tests.fakes import Clock, FakeBroker
        from pathlib import Path
        import tempfile
        from unittest.mock import patch

        strategies = patch('league.strategies.all_strategies', return_value=[])
        strategies.start()
        self.addCleanup(strategies.stop)
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.clock = Clock(ScheduledExpirationTest.NOW)  # 03:18:43Z Sept 22: hawkins-8's refusal
        rows = ScheduledExpirationTest()
        self.diesel = rows.diesel()                                                   # stops at 05:59Z, scheduled a week on
        self.scheduled = rows.venue_row("KXDIESELD-26SEP24-T6.500", "2026-09-24T06:00:00Z",
                                        expected_expiration_time="2026-09-24T15:18:43Z")  # 60 hours out by its schedule
        self.unscheduled = rows.venue_row("KXDIESELD-26SEP24-T6.505", "2026-09-24T15:18:43Z",
                                          expected_expiration_time=None, expiration_time="2026-10-01T07:30:00Z")  # no schedule (none seen): its close, 60 hours out
        parsed = {row["ticker"]: KalshiMarketData.parse_market(row) for row in (self.diesel, self.scheduled, self.unscheduled)}

        class Venue(FakeMarketData):
            def market(self, ticker):
                return parsed[ticker]  # a ticker the venue does not know raises

        self.data = KalshiData(Venue({"KXDIESELD": [[parsed[self.diesel["ticker"]]]]}), clock=self.clock)
        self.broker = FakeBroker("kalshi-shadow", family="kalshi")
        self.broker.clock_iso = now_iso(self.clock)  # the venue's quotes are as fresh as the House's clock
        for ticker in parsed:
            self.broker.set_quote(self.contract(ticker), "0.96", "0.98")
        game = load_game()
        game["economy"]["min_population"] = 0
        game["economy"]["newcomer_seconds"] = 10 ** 9
        self.house = House(Path(self.dir.name) / "house", brokers={"kalshi-shadow": self.broker}, sandbox=InProcessSandbox(),
                           kalshi_data=self.data, clock=self.clock, game=game, settings=Settings(mark_every_seconds=0, research=False))
        self.addCleanup(self.house.close, wait=None)
        self.agent = self.house.spawn("hawkins", "prices-favorites", DIESEL_BIDDER, reason="a test agent")
        self.assertEqual(self.agent.specialty, "kalshi-prices")
        self.house.evaluator.seat(self.agent.id, 1, "test")
        self.house._state["tried"][self.agent.id] = self.agent.code_sha256
        self.book = self.house.books["kalshi-shadow"]

    @staticmethod
    def contract(ticker):
        return instrument_for("kalshi-shadow", {"market": ticker, "leg": "yes"})

    def refusals(self):
        return ["; ".join(e.payload.get("reasons") or []) for e in self.house.ledger.iter(kinds="book.refused", agent=self.agent.id)]

    def bid(self, ticker):
        self.house.seat(self.agent)
        return self.house._intents(self.agent, self.book, [{"market": ticker, "leg": "yes", "side": "buy", "quantity": 1, "type": "limit",
                                                            "limit_price": 0.96, "post_only": True, "reason": "test"}])

    def diesel_orders(self):
        return [e.payload for e in self.house.ledger.iter(kinds="book.order") if e.payload.get("instrument", {}).get("market_id") == self.diesel["ticker"]]

    def test_while_no_settle_lag_is_measured_the_daily_diesel_print_is_refused_by_its_deadline_saying_so(self):
        """Fewer than 20 of the series' settled markets on record: the rule before P1, and the strategy
        is shown the hours the rule judges."""
        from league.tests.test_tapes import diesel_settled

        self.data.settle_lags.observe(diesel_settled(19, 5.86, last_close="2026-09-21T05:59:00Z"))
        self.house.tick()
        self.assertEqual(self.refusals(), ["this market is expected to resolve in 172 hours, by its expected expiration (2026-09-29T07:30:00Z), "
                                           "a deadline days after its close: its series has fewer than 20 settled markets on record to measure "
                                           "when it pays; entries must resolve within 48"])
        self.assertEqual(self.diesel_orders(), [])
        self.assertEqual(self.house._state["memory"][self.agent.id]["hours"], {self.diesel["ticker"]: 172.1881})  # what the strategy was shown

    def test_the_daily_diesel_print_is_entered_by_its_series_measured_settle_lag(self):
        """P1, review of #249: on the local history cache the last 40 diesel dailies paid within 5.86 hours
        of the close (p95). The book, the House and the strategy's view read the one answer."""
        from league.tests.test_tapes import diesel_settled

        self.data.settle_lags.observe(diesel_settled(40, 5.86, last_close="2026-09-21T05:59:00Z"))
        self.house.tick()
        self.assertEqual(self.refusals(), [])
        self.assertTrue(self.diesel_orders(), "the bid reached the book")
        due = parse_time("2026-09-22T05:59:00Z") + 5.86 * 3600
        self.assertAlmostEqual(self.house._resolves_at(self.contract(self.diesel["ticker"])), due, places=3)  # what the book judges
        self.assertEqual(self.house._state["memory"][self.agent.id]["hours"], {self.diesel["ticker"]: 8.5314})  # 2.67 h to the close + 5.86

    def test_a_series_that_pays_past_the_horizon_stays_refused_and_says_by_its_measured_lag(self):
        from league.tests.test_tapes import diesel_settled

        self.data.settle_lags.observe(diesel_settled(40, 60.0, last_close="2026-09-19T05:59:00Z"))
        self.house.tick()
        self.assertEqual(self.refusals(), ["this market is expected to resolve in 63 hours, by its close plus its series' measured settle lag "
                                           "(2026-09-24T17:59:00Z: 60 hours after the close, the 95th percentile of its last 40 settled markets; "
                                           "its expected expiration, 2026-09-29T07:30:00Z, is a deadline, not a schedule); entries must resolve "
                                           "within 48"])
        self.assertEqual(self.diesel_orders(), [])

    def test_the_house_keeps_the_settle_lags_beside_its_state(self):
        from league.house import SETTLE_LAGS_FILE

        self.assertEqual(self.data.settle_lags.path, self.house.root / SETTLE_LAGS_FILE)

    def test_a_market_scheduled_past_the_horizon_is_refused_and_the_refusal_says_by_its_schedule(self):
        intents, dropped = self.bid(self.scheduled["ticker"])
        self.assertEqual((intents, dropped), ([], []))
        (reason,) = self.refusals()
        self.assertEqual(reason, "this market is expected to resolve in 60 hours, by its scheduled expiration (2026-09-24T15:18:43Z); "
                                 "entries must resolve within 48")

    def test_a_market_the_venue_gives_no_schedule_is_refused_by_its_close_and_says_so(self):
        intents, dropped = self.bid(self.unscheduled["ticker"])
        self.assertEqual((intents, dropped), ([], []))
        (reason,) = self.refusals()
        self.assertEqual(reason, "this market is expected to resolve in 60 hours, by its close (2026-09-24T15:18:43Z): the venue lists "
                                 "no scheduled expiration for it; entries must resolve within 48")

    def test_a_market_that_cannot_be_looked_up_is_left_to_the_book(self):
        (intent,), dropped = self.bid("KXDIESELD-26SEP22-T9.999")
        self.assertEqual((dropped, self.refusals()), ([], []))
        self.broker.set_quote(intent.instrument, "0.96", "0.98")
        outcome = self.book.submit([intent])[0]
        self.assertIn("cannot tell when this market resolves", outcome.detail)  # the book is still the judge

    def test_an_exit_is_never_judged(self):
        (intent,), dropped = self.house._intents(self.agent, self.book, [{"market": self.unscheduled["ticker"], "leg": "yes", "side": "sell",
                                                                          "quantity": 1, "type": "limit", "limit_price": 0.98, "reason": "test"}])
        self.assertEqual((intent.side, dropped, self.refusals()), ("sell", [], []))


class ProtectedAnswer(HorizonBySchedule):
    """Review of #249 (the main session, 09:10Z): the horizon rule's answer is a money judge. It lives in
    `league/resolution.py`, in `ci.FORBIDDEN`, so an updater release cannot change what the book admits;
    the settle lags the House keeps (`settle_lags.json`) are data, read through it as untrusted: an entry
    that is not three finite times with the settlement at or after the close and a real deadline is
    ignored, each lag is clamped to [0, its deadline], and a series needs 20 good settlements. A
    malformed or hostile file admits nothing the rule refuses without it."""

    def test_the_answer_is_a_protected_money_judge(self):
        import tempfile
        from pathlib import Path

        from league import resolution, tapes
        from league.ci import FORBIDDEN
        from league.updater import protected_changes

        self.assertIn("league/resolution.py", FORBIDDEN)
        for name in ("resolution", "resolve_time", "SettleLags", "Resolution", "is_deadline"):
            self.assertIs(getattr(tapes, name), getattr(resolution, name), name)  # the tape, the live view and the House read it
        self.assertIsInstance(self.data.settle_lags, resolution.SettleLags)
        with tempfile.TemporaryDirectory() as folder:
            running, incoming = Path(folder) / "running", Path(folder) / "incoming"
            for tree, text in ((running, "LAG = 1\n"), (incoming, "LAG = 0\n")):
                (tree / "league").mkdir(parents=True)
                (tree / "league" / "resolution.py").write_text(text)
            refused = protected_changes(incoming, running)  # the updater refuses such a release
            self.assertTrue(any(line.startswith("league/resolution.py:") for line in refused), refused)

    def hostile(self, markets):
        """Load a `settle_lags.json` of this content through the protected reader, as the House does."""
        import json

        from league.resolution import SettleLags

        path = self.house.root / "hostile_settle_lags.json"
        path.write_text(markets if isinstance(markets, str) else json.dumps(markets))
        self.data.settle_lags = SettleLags(path)

    def entries(self, n, lag_hours, *, gap_hours=169.5, first=0):
        """`n` kept diesel entries [close, settled, deadline], one a day before Sept 22."""
        base = parse_time("2026-09-21T05:59:00Z")
        return {f"KXDIESELD-{i:03d}-T6.500": [base - i * 86400, base - i * 86400 + lag_hours * 3600, base - i * 86400 + gap_hours * 3600]
                for i in range(first, first + n)}

    def book_says(self):
        """The book's own verdict on a bid the House's check does not see (the book reads the same answer).
        A second later than any House refusal of the same bid, so it is another intent."""
        from unittest.mock import patch

        self.clock.advance(1)
        with patch.object(self.house, "_horizon_refusal", return_value=""):
            (intent,), dropped = self.bid(self.diesel["ticker"])
        return self.book.submit([intent])[0]

    def assert_refused_as_without_a_file(self):
        (reason,) = self.refusals()
        self.assertIn("this market is expected to resolve in 172 hours", reason)
        outcome = self.book_says()
        self.assertEqual(outcome.status, "refused")
        self.assertIn("this market is expected to resolve in 172 hours", outcome.detail)

    def test_an_honest_file_admits_the_diesel_print(self):
        """The control: 40 good settlements paid 5.86 hours after the close."""
        self.hostile({"version": 1, "series": {"KXDIESELD": self.entries(40, 5.86)}})
        self.assertEqual(self.bid(self.diesel["ticker"])[1], [])
        self.assertEqual(self.refusals(), [])
        self.assertNotEqual(self.book_says().status, "refused")

    def test_settlements_before_the_close_are_no_settlements(self):
        self.hostile({"version": 1, "series": {"KXDIESELD": self.entries(40, -100.0)}})
        self.bid(self.diesel["ticker"])
        self.assert_refused_as_without_a_file()
        self.assertIn("fewer than 20 settled markets", self.refusals()[0])

    def test_huge_lags_count_as_the_deadline(self):
        self.hostile({"version": 1, "series": {"KXDIESELD": self.entries(40, 10_000.0)}})
        self.bid(self.diesel["ticker"])
        self.assert_refused_as_without_a_file()

    def test_too_few_settlements_keep_the_deadline(self):
        self.hostile({"version": 1, "series": {"KXDIESELD": self.entries(19, 0.0)}})
        self.bid(self.diesel["ticker"])
        self.assert_refused_as_without_a_file()

    def test_malformed_entries_are_ignored(self):
        junk = {f"J{i}": value for i, value in enumerate((
            "garbage", None, 7, [1, 2], [1, 2, 3, 4], ["2026-09-01T05:59:00Z", 0, 0], [None, None, None],
            [float("nan"), 1.0, 2.0], [1.0, float("inf"), 2.0], [-5.0, 1.0, 1e12], [0, 0, 0],
            [1789000000.0, 1789000000.0, 1789000000.0 + 3600],  # an "expected" expiration an hour on is no deadline
        ))}
        self.hostile({"version": 1, "series": {"KXDIESELD": {**self.entries(19, 0.0), **junk}, "KXOTHER": "x", "": []}})
        self.bid(self.diesel["ticker"])
        self.assert_refused_as_without_a_file()

    def test_a_file_that_is_no_table_is_ignored(self):
        for text in ('{"version": 1, "series": {"KXDIESELD": {"KXDIESELD-0', "[1, 2, 3]", '"a string"', '{"series": [1, 2]}', "NaN"):
            with self.subTest(text=text):
                self.house.ledger.append("ops.alert", {"level": "info", "text": "reset"})  # a row between the subtests
                self.hostile(text)
                self.assertIsNone(self.data.settle_lags.lag("KXDIESELD", self.clock()))
                found = self.data.resolution_of(self.diesel["ticker"])
                self.assertEqual((found.basis, round((found.due - self.clock()) / 3600)), ("deadline", 172))


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
