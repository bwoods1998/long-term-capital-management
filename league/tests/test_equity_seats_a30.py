"""THE SEAT RULE AS AMENDED BEFORE IT WENT LIVE (release E5-A; the captain's A24 with A30), and the findings of the
release's independent check, each as a test on the real `EquityBook`.

- `ALostBuy` (A30 (3), the check's blocker): a buy whose answer was lost and which the book gave up as lost keeps its
  program from being read flat for as long as the book may still take the order back (and a day past it), so the
  program does not yield, and the lot that shows up afterwards stays its own: the House sells nothing.
- `NoOrderThatMayStillFill` (the wider question): for EVERY status an order row can hold, on either side and at every
  age, whenever the book's own order path would still book a fill of that order, the seat rule reads its program as
  not flat. The yield is impossible while an order of the program could still show up.

Everything is invented (programs, prices, K): no figure here is a market's, an account's or a real program's."""

from __future__ import annotations

import datetime as dt
import unittest
from decimal import Decimal as D
from unittest import mock

from league.equity import live as L
from league.equity import schedule as S
from league.tests import equity_design as X
from league.tests import test_equity_book as T
from league.tests import test_equity_seats as TS

BUY = {"share": 0.5, "at": "open"}


def shown_filled(h: T.Harness, order: L.Order, px: str, *, venue_id: str = "late-venue-id") -> None:
    """The venue shows `order` after all, filled whole at `px` (its row by the order's client id, the shares in the
    account, the cash gone)."""
    h.venue.book.append({"id": venue_id, "client_order_id": order.client_id, "status": "filled", "symbol": order.symbol,
                         "side": order.side, "qty": str(order.qty), "limit_price": str(order.limit_px), "type": "limit",
                         "time_in_force": "day", "filled_qty": str(order.qty), "filled_avg_price": px,
                         "submitted_at": T.iso(order.placed_at), "filled_at": T.iso(order.placed_at + 5),
                         "order_class": "simple", "legs": None})
    sign = 1 if order.side == "buy" else -1
    h.venue.held[order.symbol] = h.venue.held.get(order.symbol, D(0)) + sign * order.qty
    h.venue.cash -= sign * order.qty * D(px)


class ALostBuy(TS.SeatCase):
    """THE CHECK'S BLOCKER. Three seats: `h1` and `h2` hold lots; `rare`, seated ten sessions and never asked, waits
    on its signal; `w` waits unflagged. Session 10: rare's one buy is posted, the answer is lost, the lookups by client
    id find nothing: the order is `lost` and its intent `missed`."""

    def lost(self) -> tuple[TS.Floor, L.Order]:
        f = self.floor()
        f.add("h1", "SPY", k=200, passed=1.0)
        f.add("h2", "QQQ", k=150, passed=2.0)
        f.add("rare", "IWM", k=40, passed=3.0)
        f.add("w", "DIA", k=10, passed=4.0)
        f.plan("h1", {"buy": "SPY", **BUY})
        f.plan("h2", {"buy": "QQQ", **BUY})
        f.session(0)
        f.plan("h1")
        f.plan("h2")
        f.run(1, 8)
        f.plan("rare", {"buy": "IWM", **BUY})                   # its one buy in ten sessions, for session 10's open
        f.session(9)
        f.plan("rare")
        h = f.h
        h.venue.submit_mode = "lost_absent"                      # the answer is lost; the venue does not show the order
        for mm in (31, 33):
            h.tick(9, mm, day=f.days[10])
        h.venue.submit_mode = "ok"
        for mm in (35, 37, 39, 41, 50):                          # the lookups by client id find nothing: given up
            h.tick(9, mm, day=f.days[10])
        [order] = [o for o in h.orders() if o.family == "rare"]
        self.assertEqual((order.status, order.side, order.venue_id), ("lost", "buy", None))
        [intent] = h.intents(instance=f.key("rare"), kind="buy")
        self.assertEqual(intent.status, "missed")
        self.assertIn("the lost buy", intent.why)
        return f, order

    def decide(self, f: TS.Floor, n: int) -> None:
        for hh, mm in ((16, 21), (16, 31), (16, 32)):
            f.h.tick(hh, mm, day=f.days[n])

    def test_a_lost_buy_keeps_its_program_seated_and_the_lot_that_shows_up_is_its_own(self):
        f, order = self.lost()
        h = f.h
        self.assertFalse(h.book._flat(f.key("rare")), "a buy the book may still take back: not flat")
        self.assertIsNone(h.book._last_ask(f.key("rare")), "a lost buy is no asked buy: only flatness holds the seat")
        self.decide(f, 10)
        held = {x["family"]: x for x in f.seats()["holders"]}["rare"]
        self.assertEqual((held["seated_sessions"], held["flat"], held["idle"]), (10, False, False))
        self.assertEqual((f.band("rare"), f.band("w")), ("probe", "candidate"), "it does not yield")
        self.assertIsNone(f.inst("rare").retired_at)
        # THE VENUE SHOWS THE ORDER AFTER ALL, filled, the next day: the book takes it back and books the lot.
        for mm in (31, 33):
            h.tick(9, mm, day=f.days[11])
        shown_filled(h, order, "220.05")
        h.tick(12, 0, day=f.days[11])
        [lot] = h.book._lots(instance=f.key("rare"))
        self.assertEqual((lot.symbol, lot.qty, lot.status), ("IWM", order.qty, "open"))
        self.assertTrue(any("is at the venue after all" in text for _, text in h.alerts))
        self.decide(f, 11)
        f.run(12, 16)
        self.assertEqual((f.band("rare"), f.inst("rare").retired_at), ("probe", None), "it holds its lot and its seat")
        [lot] = h.book._lots(instance=f.key("rare"))
        self.assertEqual(lot.status, "open", "the lot is the program's own: nobody sold it")
        self.assertEqual(f.band("w"), "candidate")
        self.assert_nothing_was_ever_forced(f)

    def test_under_first_come_the_same_script_keeps_the_seat_and_the_lot_too(self):
        with X.seat_rule("first-come"):
            f, order = self.lost()
            h = f.h
            self.decide(f, 10)
            for mm in (31, 33):
                h.tick(9, mm, day=f.days[11])
            shown_filled(h, order, "220.05")
            h.tick(12, 0, day=f.days[11])
            self.decide(f, 11)
            f.run(12, 14)
            self.assertEqual((f.band("rare"), f.inst("rare").retired_at), ("probe", None))
            self.assertEqual(len(h.book._lots(instance=f.key("rare"))), 1)
            self.assertEqual(h.intents(kind="house_exit"), [])
            self.assertEqual([b for b in h.venue.sent if b["side"] == "sell"], [])

    def test_an_order_never_found_lets_the_seat_go_once_the_take_back_is_over(self):
        """The order never shows. While the book may still take it back (three calendar days after its session's,
        `LOST_TAKE_BACK_DAYS`) and for one day more, the program is not flat and keeps its seat; after that it is
        flat again, with no asked buy in ten seated sessions, and its idle seat yields. Nothing is sold."""
        f, order = self.lost()
        h = f.h
        self.decide(f, 10)
        n, kept = 11, []
        while f.band("rare") == "probe":
            f.session(n)
            gap = (f.days[n] - f.days[10]).days
            kept.append((gap, f.band("rare")))
            self.assertEqual(f.band("rare") == "probe", gap <= L.LOST_TAKE_BACK_DAYS + 1, kept)
            n += 1
        self.assertGreater(len(kept), 2)
        self.assertEqual((f.band("rare"), f.band("w")), ("candidate", "probe"))
        self.assertEqual(h.book._lots(instance=f.key("rare")), [])
        # And from then on the book takes that order back no more, whatever the venue shows: the lot it would have
        # booked to a program without a seat cannot exist.
        shown_filled(h, order, "220.05")
        f.session(n)
        [again] = [o for o in h.orders() if o.eid == order.eid]
        self.assertEqual((again.status, again.filled_qty), ("lost", D(0)))
        self.assertEqual(h.book._lots(instance=f.key("rare")), [])
        self.assertEqual(h.intents(kind="house_exit"), [])


class NoOrderThatMayStillFill(T.BookTest):
    """THE WIDER QUESTION: can any lot be booked to an instance after it yielded? A lot is booked by a buy's fill and
    by nothing else, and a fill is booked only when the order path absorbs the venue's row of an order
    (`EquityBook._absorb`). So the yield must be impossible whenever the order path could still absorb an order of
    the program. This asks the book's own code, never a copy of its lists: for every status of `WORKING` and
    `TERMINAL`, each side, each age in days, an order row is written, `_flat` is asked, the venue is made to show
    the order filled, and the House's next minute runs."""

    AGES = range(0, 9)

    def setUp(self):
        super().setUp()
        self.h = self.harness()
        self.inst = self.h.instance("rare", band="probe")
        self.today = TS.sessions(dt.date(2026, 10, 12), 12)[-1]

    def one(self, status: str, side: str, age: int, *, n: int) -> tuple[bool, bool]:
        """(whether `_flat` read the program flat with that order, whether the book then booked a fill of it)."""
        h, key = self.h, self.inst.id
        for table in ("eq_orders", "eq_lots", "eq_fills", "eq_intents"):
            h.state.execute(f"DELETE FROM {table}")
        h.venue.book.clear()
        h.venue.held.clear()
        day = self.today - dt.timedelta(days=age)
        h.clock.set(T.at(self.today, 16, 21))
        lid = None
        if side == "sell":                                       # a sale has a lot of its own, sold since by another order
            lot = h.lot(self.inst, "IWM", "1", "220", opened=day - dt.timedelta(days=3))
            lot.status, lot.qty, lot.exit_day, lot.closed_at = "closed", D(0), day.isoformat(), T.at(day, 9, 40)
            h.book._save_lot(lot)
            h.venue.held.clear()
            lid = lot.lid
        order = L.Order(n, f"{L.CLIENT_PREFIX}test-{n}-rare", key, "rare", side, "IWM", "etf", "open", D("1"), D("220"),
                        10, status, T.at(day, 9, 31), day.isoformat(), lid=lid,
                        venue_id=None if status in ("pending", "unknown", "lost", "refused", "missed") else f"v-{n}")
        h.book._save_order(order)
        flat = h.book._flat(key)
        shown_filled(h, order, "220.05", venue_id=order.venue_id or f"late-{n}")
        h.tick(16, 22, day=self.today)
        [after] = [o for o in h.orders() if o.eid == n]
        booked = after.filled_qty > 0 or bool(h.state.rows("SELECT 1 AS x FROM eq_fills WHERE eid=?", (n,)))
        return flat, booked

    def test_whenever_the_order_path_would_still_book_a_fill_the_program_is_not_flat(self):
        self.assertTrue(self.h.book._flat(self.inst.id), "with no order, no lot and no intent it is flat")
        statuses = tuple(L.WORKING) + tuple(L.TERMINAL)
        self.assertEqual(len(set(statuses)), len(statuses))
        seen, n = {}, 100
        for status in statuses:
            for side in ("buy", "sell"):
                for age in self.AGES:
                    n += 1
                    flat, booked = self.one(status, side, age, n=n)
                    seen[status, side, age] = (flat, booked)
                    self.assertFalse(flat and booked, f"a {status} {side} of {age} days ago: read flat, and its fill "
                                                      "was booked afterwards")
        # What the book's order path takes back, as observed: every order still working, at any age, and one given
        # up as lost while its session's day is within `LOST_TAKE_BACK_DAYS` of today. Nothing else, ever.
        booked = {k for k, (_, b) in seen.items() if b}
        self.assertEqual(booked, {(s, side, age) for s in L.WORKING for side in ("buy", "sell") for age in self.AGES}
                         | {("lost", side, age) for side in ("buy", "sell") for age in range(0, L.LOST_TAKE_BACK_DAYS + 1)})
        # And what holds a seat: all of those, and a lost order for one day more (the margin, below).
        held = {k for k, (flat, _) in seen.items() if not flat}
        self.assertEqual(held - booked, {("lost", side, L.LOST_TAKE_BACK_DAYS + 1) for side in ("buy", "sell")})
        self.assertTrue(booked <= held)

    def test_the_margin_covers_a_minute_that_straddles_midnight(self):
        """`_sync_orders` reads the day off the minute's `now`; `_flat` off the wall clock, which may already be the
        next New York day when the equity minute runs late. A lost order on the last day of its take-back by the
        minute's clock is not flat by the wall clock either: the seat rule reads a day further than the order path."""
        h, key = self.h, self.inst.id
        day = self.today - dt.timedelta(days=L.LOST_TAKE_BACK_DAYS)
        order = L.Order(7, f"{L.CLIENT_PREFIX}test-7-rare", key, "rare", "buy", "IWM", "etf", "open", D("1"), D("220"),
                        10, "lost", T.at(day, 9, 31), day.isoformat())
        h.book._save_order(order)
        late = dt.datetime.combine(self.today + dt.timedelta(days=1), dt.time(0, 0, 20), tzinfo=T.NY).timestamp()
        h.clock.set(late)                                         # the wall clock: twenty seconds into the next day
        self.assertFalse(h.book._flat(key))
        shown_filled(h, order, "220.05")
        before = dt.datetime.combine(self.today, dt.time(23, 59, 3), tzinfo=T.NY).timestamp()
        out: dict = {}
        h.book._sync_orders(before, out)                          # the minute's own `now`: still the day before
        [after] = h.orders()
        self.assertEqual(after.status, "filled", "the order path took it back")
        self.assertEqual(len(h.book._lots(instance=key)), 1)

    def test_the_two_windows_are_one_constant(self):
        self.assertEqual(L.LOST_TAKE_BACK_DAYS, 3)
        self.assertEqual(L.LOST_HOLDS_SEAT_DAYS, L.LOST_TAKE_BACK_DAYS + 1)
        self.assertEqual(S.ny_day(T.at(self.today, 16, 21)), self.today)


class NoYieldWhileAnOrderMayStillFill(TS.SeatCase):
    """The same on the whole rule: `rare`, idle for twelve seated sessions with an unflagged program waiting, and one
    order of its own in each state the order path may still fill. It never yields; with the order gone it does."""

    def test_each_state_alone_holds_the_seat(self):
        cases = [(status, 0) for status in L.WORKING] + [("lost", age) for age in range(0, L.LOST_HOLDS_SEAT_DAYS + 1)]
        for status, age in cases:
            with self.subTest(status=status, age=age):
                f = self.floor()
                f.add("h1", "SPY", k=200, passed=1.0)
                f.add("h2", "QQQ", k=150, passed=2.0)
                f.add("rare", "IWM", k=40, passed=3.0)
                f.plan("h1", {"buy": "SPY", **BUY})
                f.plan("h2", {"buy": "QQQ", **BUY})
                f.session(0)
                f.plan("h1")
                f.plan("h2")
                f.run(1, 11)
                h = f.h
                day = f.days[12] - dt.timedelta(days=age)
                order = L.Order(900, f"{L.CLIENT_PREFIX}test-900-rare", f.key("rare"), "rare", "buy", "IWM", "etf", "open",
                                D("1"), D("220"), 10, status, T.at(day, 9, 31), day.isoformat())
                h.book._save_order(order)
                f.add("w", "DIA", k=10, passed=4.0)              # an unflagged program passes its look, and waits
                # The venue does not show the order, and no minute of the order path runs before the decision: the
                # row is what the decision finds.
                h.clock.set(T.at(f.days[12], 16, 20, 50))
                with mock.patch.object(L.EquityBook, "_sync_orders", lambda *a, **k: None):
                    for hh, mm in ((16, 21), (16, 31), (16, 32)):
                        h.tick(hh, mm, day=f.days[12])
                held = {x["family"]: x for x in f.seats()["holders"]}["rare"]
                self.assertEqual((held["flat"], held["idle"], held["seated_sessions"]), (False, False, 12))
                self.assertEqual((f.band("rare"), f.band("w")), ("probe", "candidate"))
                # The order gone (as if it had never been written): flat, idle, and the seat yields at the next decision.
                h.state.execute("DELETE FROM eq_orders WHERE eid=900")
                f.session(13)
                self.assertEqual((f.band("rare"), f.band("w")), ("candidate", "probe"))
                self.assert_nothing_was_ever_forced(f)


if __name__ == "__main__":
    unittest.main()
