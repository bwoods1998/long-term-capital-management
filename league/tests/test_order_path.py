"""The order path's defects from the Sept 23, 2026 study (workstream B), each with the test that
failed before its fix:

- an option asked for at market, and a post-only Kalshi order that would cross, are fitted by the
  House rather than refused or rejected (`House._fit_order_type`);
- an agent whose seat is gone between its decision and the submission has its intents dropped with
  one alert, not a `book.refused` row each (`House._submit_wakes`);
- a backlog of due agents (a resumed House) is drained one desk at a time (`House._every_desk_first`);
- the order path's own invariants: a refusal for an agent that is not alive, and a round-the-clock
  desk with no wake for half an hour (`House._order_path_invariants`);
- a venue answering "no such order" is believed on the second look a minute later, and an order it
  has after all is revived with its fill (`Book._venue_missed`, `Book._recheck_never_arrived`);
- the venue's reason rides on the order row it closes (`Book._route`);
- the market slices of a sliced exit wait for the open instead of being refused (`Book._advance_plan`).

Every test runs on the fake venues; nothing reaches the network.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

from ltcm.broker import Instrument, RejectedOrder, UnknownOutcome

from league import seeds
from league.book import EXIT_PLAN_TTL_SECONDS, NEVER_ARRIVED, NEVER_ARRIVED_RECHECK_SECONDS, Book, Intent, Limits
from league.fees import Fees
from league.tests.fakes import FakeBroker, iso
from league.tests.test_book import BTC, BookCase
from league.tests.test_exit_slices import SliceCase
from league.tests.test_house import HouseCase
from league.venues import instrument_for

D = Decimal
NO_LEG = {"market": "KXBTC15M-26SEP231145-45", "leg": "no"}


# ------------------------------------------------------------------ the House's fitting of an order
class OrderFitting(HouseCase):
    def sized(self, agent, book, *rows):
        adjusted: list[str] = []
        intents, dropped = self.house._intents(agent, book, [{"reason": "test", **row} for row in rows], adjusted=adjusted)
        return intents, dropped, adjusted

    def kalshi_book(self):
        broker = FakeBroker("kalshi-shadow", family="kalshi")
        book = Book("kalshi-shadow", broker, self.house.ledger, fees=Fees("kalshi"), real_money=False, clock=self.clock)
        self.house.books["kalshi-shadow"] = book
        return book, broker

    def test_an_option_asked_for_at_market_becomes_a_limit_at_the_touch_and_the_book_takes_it(self):
        agent = self.house.spawn("options-breakout", "options-breakout", seeds.load("options-breakout"), reason="test", specialty="alpaca-options")
        self.house.seat(agent)
        book = self.house.books["alpaca-paper"]
        self.assertEqual(book.limits[agent.id].asset_classes, ("option",))
        contract = instrument_for("alpaca-paper", {"occ": "F261009C00013000"})
        self.broker.set_quote(contract, "0.40", "0.44")
        (buy,), dropped, adjusted = self.sized(agent, book, {"occ": "F261009C00013000", "side": "buy", "quantity": 1, "type": "market"})
        self.assertEqual((buy.order_type, buy.limit_price, dropped), ("limit", D("0.44"), []))
        self.assertIn("a market buy became a limit at the ask of 0.44", adjusted[0])
        (outcome,) = book.submit([buy])  # the book, still the judge, takes it: no "must be a limit order" refusal
        self.assertEqual(outcome.status, "filled", outcome.detail)
        self.assertIsNone(self.house.ledger.last("book.refused", agent=agent.id))
        (sell,), _, adjusted = self.sized(agent, book, {"occ": "F261009C00013000", "side": "sell", "quantity": 1, "type": "market"})
        self.assertEqual((sell.order_type, sell.limit_price), ("limit", D("0.40")))
        self.assertIn("limit at the bid of 0.40", adjusted[0])
        (asked,), _, adjusted = self.sized(agent, book, {"occ": "F261009C00013000", "side": "buy", "quantity": 1, "type": "limit", "limit_price": 0.41})
        self.assertEqual((asked.order_type, asked.limit_price, adjusted), ("limit", D("0.41"), []))  # a limit as asked is left alone

    def test_a_post_only_kalshi_bid_that_would_cross_is_re_priced_one_tick_inside_the_ask(self):
        agent = self.seated()
        agent.specialty = self.house.registry.get(agent.id).specialty = None  # a test agent of no desk: no specialty check
        book, broker = self.kalshi_book()
        contract = instrument_for("kalshi-shadow", NO_LEG)
        broker.set_quote(contract, "0.94", "0.96")
        book.limits[agent.id] = Limits(D("100"), D("75"))
        book.stake(agent.id, "100")
        (bid,), dropped, adjusted = self.sized(agent, book, {**NO_LEG, "side": "buy", "quantity": 2, "type": "limit", "limit_price": 0.97, "post_only": True})
        self.assertEqual((bid.limit_price, bid.post_only, dropped), (D("0.95"), True, []))
        self.assertIn("post-only limit 0.97 re-priced to 0.95, one tick inside the ask of 0.96", adjusted[0])
        (outcome,) = book.submit([bid])  # the fake venue rejects a post-only order that crosses; this one rests
        self.assertEqual(outcome.status, "resting", outcome.detail)
        (at_touch,), _, adjusted = self.sized(agent, book, {**NO_LEG, "side": "buy", "quantity": 2, "type": "limit", "limit_price": 0.96, "post_only": True})
        self.assertEqual(at_touch.limit_price, D("0.95"))  # at the ask is a cross too
        (under,), _, adjusted = self.sized(agent, book, {**NO_LEG, "side": "buy", "quantity": 2, "type": "limit", "limit_price": 0.93, "post_only": True})
        self.assertEqual((under.limit_price, adjusted), (D("0.93"), []))  # a bid under the ask rests as asked
        (taker,), _, adjusted = self.sized(agent, book, {**NO_LEG, "side": "buy", "quantity": 2, "type": "limit", "limit_price": 0.97})
        self.assertEqual((taker.limit_price, adjusted), (D("0.97"), []))  # not post-only: a marketable limit is what it meant
        (offer,), _, adjusted = self.sized(agent, book, {**NO_LEG, "side": "sell", "quantity": 2, "type": "limit", "limit_price": 0.93, "post_only": True})
        self.assertEqual(offer.limit_price, D("0.95"))  # an offer at or under the bid rests one tick over it
        self.assertIn("one tick inside the bid of 0.94", adjusted[0])


# --------------------------------------------------------------------- the seat guard at submission
class SeatGuard(HouseCase):
    def test_intents_of_an_agent_whose_seat_is_gone_are_dropped_with_one_alert_not_refused(self):
        agent = self.seated()
        out = self.house.wake(agent)
        self.assertTrue(out["intents"])
        book = self.house.books["alpaca-paper"]
        del book.limits[agent.id]  # the seat went between the decision and its submission
        self.assertEqual(self.house._submit_wakes("alpaca-paper", [out]), [])
        self.assertEqual(self.broker.submitted, [])
        self.assertIsNone(self.house.ledger.last("book.refused", agent=agent.id))
        alerts = [e.payload["text"] for e in self.house.ledger.iter(kinds="ops.alert") if "no seat" in e.payload["text"]]
        self.assertEqual(len(alerts), 1)
        self.assertIn(f"{agent.id}: 1 intent(s) dropped before the alpaca-paper book", alerts[0])
        self.house._submit_wakes("alpaca-paper", [out])  # again the same day: told once
        self.assertEqual(sum(1 for e in self.house.ledger.iter(kinds="ops.alert") if "no seat" in e.payload["text"]), 1)
        book.limits[agent.id] = Limits(D("100"), D("75"))  # seated again: its intents go through
        self.assertEqual([o.status for o in self.house._submit_wakes("alpaca-paper", [out])], ["filled"])


# --------------------------------------------------------------------- draining a backlog of wakes
class DeskFairResume(HouseCase):
    def test_a_backlog_is_drained_one_desk_at_a_time_the_longest_waiting_desk_first(self):
        desks = {"a": "alpaca-crypto-alts", "b": "alpaca-crypto-majors", "c": "alpaca-index-etfs"}
        agents = {}
        for letter, desk in desks.items():
            for n in range(3):
                agent = self.seated(f"{letter}{n}")
                self.house.registry.get(agent.id).specialty = desk
                agents[f"{letter}{n}"] = agent.id
                self.house._state["next_wake"][agent.id] = 100 + n  # oldest deadline first within a desk
        self.house.settings.max_wakes_per_tick = self.house.settings.cold_wakes_per_tick = 2
        self.house._state["desk_woke"] = {desks["a"]: 50.0, desks["b"]: 10.0}  # b waited longer than a; c never woke

        def woken(names):
            for name in names:
                self.house._state["desk_woke"][self.house.registry.get(agents[name]).specialty] = self.clock()
                self.house._state["next_wake"][agents[name]] = self.clock() + 10 ** 9
            self.clock.advance(60)

        self.assertEqual([a.id for a in self.house.due()], [agents["c0"], agents["b0"]])  # one a desk, longest wait first
        woken(["c0", "b0"])
        self.assertEqual([a.id for a in self.house.due()], [agents["a0"], agents["b1"]])  # a's turn; b and c tie, deadline order
        woken(["a0", "b1"])
        self.assertEqual([a.id for a in self.house.due()], [agents["c1"], agents["a1"]])
        woken(["c1", "a1"])
        self.house.settings.max_wakes_per_tick = self.house.settings.cold_wakes_per_tick = 16
        self.assertEqual(len(self.house.due()), 3)  # no backlog: everyone due is woken, in deadline order

    def test_a_wake_stamps_its_desk(self):
        agent = self.seated()
        self.house.registry.get(agent.id).specialty = "alpaca-crypto-alts"
        self.house.wake(agent)
        self.assertEqual(self.house._state["desk_woke"], {"alpaca-crypto-alts": self.clock()})


# -------------------------------------------------------------------------- the path's invariants
class OrderPathInvariants(HouseCase):
    def alerts(self, text):
        return [e.payload["text"] for e in self.house.ledger.iter(kinds="ops.alert") if text in e.payload["text"]]

    def refused(self, agent_id, reason):
        self.house.ledger.append("book.refused", {"book": "alpaca-paper", "intent_id": "in-x", "reasons": [reason]}, agent=agent_id)

    def test_a_refusal_for_an_agent_that_is_not_alive_is_told_once_a_day(self):
        dead = self.seated("dead")
        alive = self.seated("alive")
        self.house.registry.died(dead.id, "credits", "a test death")
        self.refused(alive.id, "needs $30.00 with fees; free cash is $20.00")
        self.house._order_path_invariants()
        self.assertEqual(self.alerts("not alive"), [])
        self.refused(dead.id, f"{dead.id} has no seat on the alpaca-paper book")
        self.refused(dead.id, "market orders outside regular hours are not permitted")
        self.clock.advance(61)
        self.house._order_path_invariants()
        (told,) = self.alerts("not alive")
        self.assertIn(f"{dead.id}: 2 intent(s) refused on alpaca-paper for an agent that is not alive", told)
        self.assertIn("has no seat", told)
        self.refused(dead.id, "market orders outside regular hours are not permitted")
        self.clock.advance(61)
        self.house._order_path_invariants()
        self.assertEqual(len(self.alerts("not alive")), 1)  # the same day: told once

    def test_a_round_the_clock_desk_with_no_wake_for_half_an_hour_is_told_once_and_a_pause_resets_it(self):
        coin = self.seated("coin")
        self.house.registry.get(coin.id).specialty = "alpaca-crypto-alts"
        stock = self.seated("stock")
        self.house.registry.get(stock.id).specialty = "alpaca-index-etfs"
        self.clock.advance(1801)
        self.house._order_path_invariants()
        (told,) = self.alerts("round-the-clock")
        self.assertIn("alpaca-crypto-alts: no wake on a round-the-clock desk for 30 minutes with 1 living member(s)", told)
        self.assertEqual(self.alerts("alpaca-index-etfs"), [])  # a desk that keeps the session has quiet nights of its own
        self.clock.advance(61)
        self.house._order_path_invariants()
        self.assertEqual(len(self.alerts("round-the-clock")), 1)  # told once per half hour
        (self.house.root / "PAUSE").write_text("a test pause", encoding="utf-8")
        self.clock.advance(1801)
        self.house._order_path_invariants()
        self.assertEqual(len(self.alerts("round-the-clock")), 1)  # paused: not the scheduler's fault
        (self.house.root / "PAUSE").unlink()
        self.clock.advance(61)
        self.house._order_path_invariants()
        self.assertEqual(len(self.alerts("round-the-clock")), 1)  # a minute after the pause lifted
        self.clock.advance(1801)
        self.house._order_path_invariants()
        self.assertEqual(len(self.alerts("round-the-clock")), 2)
        self.house.wake(coin)
        self.clock.advance(1801)
        self.house._order_path_invariants()
        self.assertEqual(len(self.alerts("round-the-clock")), 3)  # the wake was half an hour ago again
        self.house.wake(coin)
        self.clock.advance(1700)
        self.house._order_path_invariants()
        self.assertEqual(len(self.alerts("round-the-clock")), 3)  # woken within the half hour: nothing to say


# ---------------------------------------------------------------- the venue's "no such order"
class NeverArrived(BookCase):
    def test_a_lost_answer_is_believed_on_the_second_look_a_minute_later(self):
        self.seat("a1")
        self.broker.set_quote(BTC, "80000", "80010")
        self.broker.lose_next_submit = True
        self.assertEqual(self.book.submit([self.intent("a1", BTC, "buy", "0.0005")])[0].status, "unknown")
        self.book.poll()
        self.book.poll()  # twice in the same minute is one look
        self.assertEqual([w.status for w in self.book.open_orders()], ["unknown"])
        self.assertEqual(self.book.ledger.last("book.order").payload["status"], "unknown")  # no verdict on the record yet
        self.clock.advance(61)
        self.book.poll()
        self.assertEqual(self.book.open_orders(), [])
        self.assertEqual(self.book.ledger.last("book.order").payload["reason"], NEVER_ARRIVED)
        self.assertTrue(self.book.reconcile().ok)

    def test_an_order_the_venue_has_after_all_is_revived_and_its_fill_booked(self):
        self.seat("a1")
        self.broker.set_quote(BTC, "80000", "80010")
        self.assertTrue(self.book.reconcile().ok)  # the baseline: what the venue held before the order
        original_submit, original_get = self.broker.submit, self.broker.get_order
        hidden = {"looks": 0}

        def accepted_and_filled_but_the_answer_was_lost(intent):
            original_submit(intent)  # the venue has it, and filled it
            raise UnknownOutcome("the answer was lost")

        def not_found_three_times_then_found(order_id):
            hidden["looks"] += 1
            if hidden["looks"] <= 3:
                raise RejectedOrder(f"no order {order_id}")  # a venue answering 404 while it catches up
            return original_get(order_id)

        with patch.object(self.broker, "submit", side_effect=accepted_and_filled_but_the_answer_was_lost), \
                patch.object(self.broker, "get_order", side_effect=not_found_three_times_then_found):
            (out,) = self.book.submit([self.intent("a1", BTC, "buy", "0.0005")])
            self.assertEqual(out.status, "unknown")
            self.book.poll()
            self.clock.advance(61)
            self.book.poll()  # closed as never arrived: the venue said so twice (and once more when asked again at once)
            self.assertEqual(self.book.open_orders(), [])
            self.assertEqual(self.book.account("a1").holdings, {})
            self.assertFalse(self.book.reconcile().ok)  # the venue holds what the book does not know
            self.clock.advance(61)
            self.book.poll()  # asked once more: the venue has it after all
        rows = [e.payload for e in self.ledger.iter(kinds="book.order")]
        self.assertEqual([r["status"] for r in rows][-4:], ["rejected", "accepted", "accepted", "filled"])
        self.assertIn("has this order after all", rows[-3]["reason"])
        self.assertEqual(self.book.account("a1").holdings[BTC.key].quantity, D("0.00049875"))  # the in-kind fee taken
        self.assertTrue(self.book.reconcile().ok)
        self.assertTrue(self.book.evidence_integrity("a1")["ok"])
        self.assertEqual(self.ledger.verify(), self.ledger.head()[0])

    def test_a_restart_keeps_asking_about_an_order_closed_as_never_arrived(self):
        self.seat("a1")
        self.broker.set_quote(BTC, "80000", "80010")
        self.assertTrue(self.book.reconcile().ok)
        original_submit = self.broker.submit

        def accepted_but_the_answer_was_lost(intent):
            original_submit(intent)
            raise UnknownOutcome("the answer was lost")

        with patch.object(self.broker, "submit", side_effect=accepted_but_the_answer_was_lost), \
                patch.object(self.broker, "get_order", side_effect=RejectedOrder("no order")):
            self.book.submit([self.intent("a1", BTC, "buy", "0.0005")])
            self.book.poll()
            self.clock.advance(61)
            self.book.poll()
        self.assertEqual(self.book.ledger.last("book.order").payload["reason"], NEVER_ARRIVED)
        self.assertFalse(self.book.reconcile().ok)
        again = self.new_book()  # a restart folds the verdict and keeps the venue's window open
        again.limits = dict(self.book.limits)
        again.poll()
        self.assertEqual(again.account("a1").holdings[BTC.key].quantity, D("0.00049875"))
        self.assertTrue(again.reconcile().ok)

    def lost_buy(self, quantity="0.0006"):
        """A limit buy the venue took and rests, whose answer was lost, closed as never arrived
        after two looks: ~$48 of the stake at 79990."""
        original_submit = self.broker.submit

        def accepted_but_the_answer_was_lost(intent):
            original_submit(intent)  # the venue has it, resting
            raise UnknownOutcome("the answer was lost")

        with patch.object(self.broker, "submit", side_effect=accepted_but_the_answer_was_lost), \
                patch.object(self.broker, "get_order", side_effect=RejectedOrder("no order")):
            (first,) = self.book.submit([self.intent("a1", BTC, "buy", quantity, order_type="limit", limit_price="79990")])
            self.assertEqual(first.status, "unknown")
            self.book.poll()
            self.clock.advance(61)
            self.book.poll()
        self.assertEqual(self.book.ledger.last("book.order").payload["reason"], NEVER_ARRIVED)
        return next(o for o in self.broker.orders.values() if o.limit_price == D("79990"))

    def test_a_buy_closed_as_never_arrived_keeps_its_cash_reserved_while_the_book_still_asks(self):
        """Found in review (Sept 23, 2026): the verdict freed the buy's cash on the spot, a second buy
        of the same size passed `check`, and when the venue had the first order after all the revival
        left the agent 96% invested against the 50% cap, paid from the venue's pooled cash."""
        self.seat("a1", usd="100")
        self.broker.set_quote(BTC, "80000", "80010")
        self.assertTrue(self.book.reconcile().ok)
        resting = self.lost_buy()
        self.assertEqual(self.book.open_orders(), [])
        self.assertGreater(self.book._reserved_cash("a1"), D("47"))  # the verdict did not free the ~$48
        (second,) = self.book.submit([self.intent("a1", BTC, "buy", "0.0006")])
        self.assertEqual(second.status, "refused", second.detail)
        self.assertIn("working buys", second.detail)  # the never-arrived buy still counts against the cap
        self.broker.fill_resting(resting.id, "0.0006")  # the venue had it, and fills it
        self.clock.advance(61)
        self.book.poll()  # the recheck finds it and books the fill
        account = self.book.account("a1")
        self.assertEqual(account.holdings[BTC.key].quantity, D("0.0005985"))
        self.assertEqual(self.book._reserved_cash("a1"), D("0"))  # found: nothing left to reserve
        held = account.holdings[BTC.key].quantity * self.book.marks[BTC.key]
        self.assertLessEqual(held, self.book.equity("a1") * D("0.5"))  # within the cap, as the book judged it
        self.assertGreater(account.cash, D("50"))
        self.assertTrue(self.book.reconcile().ok)
        self.assertTrue(self.book.evidence_integrity("a1")["ok"])

    def test_the_reservation_lapses_with_the_recheck_window(self):
        self.seat("a1", usd="100")
        self.broker.set_quote(BTC, "80000", "80010")
        self.assertTrue(self.book.reconcile().ok)
        self.lost_buy()
        self.assertGreater(self.book._reserved_cash("a1"), D("47"))
        self.clock.advance(NEVER_ARRIVED_RECHECK_SECONDS + 1)
        self.assertEqual(self.book._reserved_cash("a1"), D("0"))  # the book has stopped asking: the venue never had it
        with patch.object(self.broker, "get_order", side_effect=RejectedOrder("no order")):
            self.book.poll()
        self.broker.clock_iso = iso(self.clock)  # a fresh quote, a quarter of an hour on
        (buy,) = self.book.submit([self.intent("a1", BTC, "buy", "0.0006")])
        self.assertEqual(buy.status, "filled", buy.detail)


class SweepWithReservedCash(HouseCase):
    def test_a_dead_agents_sweep_takes_the_free_cash_and_leaves_what_a_never_arrived_buy_binds(self):
        """`_sweep` runs unguarded in the mark pass: it must never ask the book for cash a
        never-arrived buy still reserves (`Book.stake` refuses that), and it must still sweep the
        rest once the book has stopped asking the venue."""
        agent = self.seated()
        self.house.seat(agent)
        book = self.house.books["alpaca-paper"]
        staked = book.account(agent.id).cash
        self.assertGreater(staked, D("0"))
        self.broker.set_quote(self.btc, "80000", "80010")
        original_submit = self.broker.submit

        def accepted_but_the_answer_was_lost(intent):
            original_submit(intent)
            raise UnknownOutcome("the answer was lost")

        quantity = ((staked * D("0.3")) / D("80000")).quantize(D("0.000000001"))  # under the $75 order cap
        with patch.object(self.broker, "submit", side_effect=accepted_but_the_answer_was_lost), \
                patch.object(self.broker, "get_order", side_effect=RejectedOrder("no order")):
            (out,) = book.submit([Intent.new(agent=agent.id, instrument=self.btc, side="buy", quantity=quantity, order_type="limit",
                                             limit_price="79990", reason="test", created_at=iso(self.clock), nonce="lost")])
            self.assertEqual(out.status, "unknown", out.detail)
            book.poll()
            self.clock.advance(61)
            book.poll()
        self.assertEqual(book.ledger.last("book.order").payload["reason"], NEVER_ARRIVED)
        reserved = book._reserved_cash(agent.id)
        self.assertGreater(reserved, D("0"))
        self.house.registry.died(agent.id, "credits", "a test death")
        self.house._sweep(agent.id, book)  # no BookError: the free cash goes, the reserved cash stays
        self.assertEqual(book.account(agent.id).cash, reserved)
        self.assertFalse(book.account(agent.id).swept)
        self.clock.advance(NEVER_ARRIVED_RECHECK_SECONDS + 1)
        with patch.object(self.broker, "get_order", side_effect=RejectedOrder("no order")):
            book.poll()
        self.house._sweep(agent.id, book)
        self.assertEqual(book.account(agent.id).cash, D("0"))
        self.assertTrue(book.account(agent.id).swept)


class VenueReason(BookCase):
    venue = "kalshi-shadow"
    family = "kalshi"

    def test_the_venues_reason_rides_on_the_order_row_it_closes(self):
        self.seat("a1")
        contract = Instrument("event", "KXBTCD-26SEP2317-T80999", "kalshi-shadow", market_id="KXBTCD-26SEP2317-T80999", right="yes")
        self.broker.set_quote(contract, "0.90", "0.92")
        (out,) = self.book.submit([self.intent("a1", contract, "buy", "2", order_type="limit", limit_price="0.95", post_only=True)])
        self.assertEqual((out.status, out.detail), ("rejected", "post-only order would cross"))
        row = self.book.ledger.last("book.order").payload
        self.assertEqual((row["status"], row["reason"]), ("rejected", "post-only order would cross"))
        (out,) = self.book.submit([self.intent("a1", contract, "buy", "2", order_type="limit", limit_price="0.91", post_only=True)])
        self.assertEqual(out.status, "resting")
        self.assertEqual(self.book.ledger.last("book.order").payload["reason"], "")  # a resting order has nothing to explain


# --------------------------------------------------------- sliced exits over a close
class HeldSlices(SliceCase):
    instrument = Instrument("equity", "SPY", "alpaca-paper")

    def new_book(self):
        book = super().new_book()
        self.session_open = getattr(self, "session_open", True)
        book.market_open = lambda instrument, now: self.session_open if instrument.asset_class == "equity" else None
        return book

    def test_the_market_slices_of_a_sliced_exit_wait_for_the_open_instead_of_being_refused(self):
        self.seat()
        self.broker.set_quote(self.instrument, "500.00", "500.05")
        self.buy(self.instrument, "0.13", "0.13", "0.13", "0.03")
        held = self.held(self.instrument)
        self.broker.fractions = ["0.5"]  # the first slice fills by half; the rest is for the next passes
        sell = self.intent("a1", self.instrument, "sell", held)
        (out,) = self.book.submit([sell])
        self.assertEqual(out.status, "partial", out.detail)
        (plan_id,) = list(self.book.exit_plans)
        sent = len(self.sells())
        self.session_open = False  # the bell, before the next pass
        self.book.poll()
        self.clock.advance(EXIT_PLAN_TTL_SECONDS + 1)  # the whole night
        self.book.poll()
        self.assertEqual(len(self.sells()), sent)  # nothing sent into a shut session
        self.assertIn(plan_id, self.book.exit_plans)  # and the plan neither refused nor timed out
        self.assertEqual(self.ledger.count(kinds="book.refused"), 0)
        self.session_open = True
        self.book.poll()
        self.assertEqual(self.held(self.instrument), 0)
        self.assertNotIn(plan_id, self.book.exit_plans)
        self.assert_sound([sell.id])

    def test_a_plan_resumed_at_the_open_still_times_out_from_there(self):
        self.seat()
        self.broker.set_quote(self.instrument, "500.00", "500.05")
        self.buy(self.instrument, "0.13", "0.13", "0.13", "0.03")
        self.broker.fractions = ["0.5"]
        self.book.submit([self.intent("a1", self.instrument, "sell", self.held(self.instrument))])
        (plan_id,) = list(self.book.exit_plans)
        self.session_open = False
        self.book.poll()
        self.session_open = True
        self.broker.reject_all = True  # the venue refuses every slice after the open
        self.book.poll()
        self.assertIn(plan_id, self.book.exit_plans)
        self.clock.advance(EXIT_PLAN_TTL_SECONDS + 1)
        self.book.poll()
        self.assertNotIn(plan_id, self.book.exit_plans)  # not finished within the hour after the open
        self.assertTrue(self.book.reconcile().ok)


import unittest


class ReviewFollowUps(unittest.TestCase):
    """The #203 review's follow-ups (Sept 23, 2026): the reconcile alert level for an order whose
    outcome is still unknown, checked on the House's rule text."""

    def test_an_unknown_outcome_alone_is_a_warning_and_a_cash_or_position_problem_stays_an_error(self):
        import inspect
        from league import house as house_module
        source = inspect.getsource(house_module.House)
        self.assertIn('pending_only = (not result.position_diffs and "outcome is unknown" in result.detail', source)
        self.assertIn('and "cash differs" not in result.detail)', source)
        self.assertIn("minor = minor or pending_only", source)

    def test_the_wake_stamps_are_written_under_the_state_lock(self):
        import inspect
        from league import house as house_module
        source = inspect.getsource(house_module.House.wake)
        lock = source.index("with self._state_lock:")
        self.assertLess(lock, source.index('self._state.setdefault("desk_woke", {})'))
        self.assertLess(lock, source.index('self._state["next_wake"][agent.id] = next_wake'))
