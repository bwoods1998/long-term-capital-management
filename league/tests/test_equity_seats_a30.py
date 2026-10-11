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
import sqlite3
import unittest
from decimal import Decimal as D
from pathlib import Path
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


# ================================================================================== A30 (2): the idle clock and the House
PAUSED = "the House is paused"


class TheIdleClock(TS.SeatCase):
    """A30 (2): THE IDLE CLOCK DOES NOT RUN WHILE THE HOUSE REFUSES EVERY OPEN. A session with an entry window in which
    the House looked and never once would have opened (`EquityBook._open_note`: what `_open_block` answers before it
    looks at the instance) is left out of every program's seated sessions and of its sessions since its last asked
    buy."""

    def work(self, f: TS.Floor, n: int, *, blocked: str | None = None) -> dict:
        """Session `n` with the House's answer to every open set to `blocked` for its whole day: the open window, a
        midday minute (the entry cut-off ends a refused buy as missed) and the decision."""
        f.h.blocked = blocked
        for hh, mm in ((9, 31), (9, 33), (12, 0)):
            f.h.tick(hh, mm, day=f.days[n])
        out = {}
        for hh, mm in ((16, 21), (16, 31), (16, 32)):
            out.update({k: v for k, v in f.h.tick(hh, mm, day=f.days[n]).items() if k not in out or k in ("seats", "decided")})
        return out

    def test_after_a_ten_session_pause_no_trader_yields(self):
        """THE CHECK'S SCENARIO. Three seats held by three daily traders, two slow programs waiting. Each trader buys
        a lot, sells it at session 3's open and from then on asks to buy every day. The House is paused from session
        3 to session 14: the sells go through, every buy ends missed with the House's own reason. Before A30 the
        clock ran through the pause and two traders lost their seats to the slow programs at sessions 11 and 12."""
        f = self.floor()
        traders = {"daily-1": "SPY", "daily-2": "QQQ", "daily-3": "IWM"}
        for i, (family, symbol) in enumerate(traders.items()):
            f.add(family, symbol, k=240 - 10 * i, passed=1.0 + i)
            f.plan(family, {"buy": symbol, **BUY})
        f.add("slow-1", "DIA", k=5, passed=4.0)
        f.add("slow-2", "XLK", k=4, passed=5.0)
        for n in range(0, 19):
            if n == 1:
                for family in traders:
                    f.plan(family)
            if n == 2:
                for family in traders:
                    [lot] = f.h.book._lots(instance=f.key(family))
                    f.plan(family, {"sell": lot.lid, "at": "open"})
            if n == 3:
                for family, symbol in traders.items():
                    f.plan(family, {"buy": symbol, **BUY})         # a buy asked every day from now on
            self.work(f, n, blocked=PAUSED if 3 <= n <= 14 else None)
            self.assertEqual(sorted(f.holders()), sorted(traders), f"session {n}: a trader lost its seat")
            self.assertEqual(f.waiting(), [("slow-1", 1, False), ("slow-2", 2, False)])
        self.assertEqual([e["action"] for e in f.events()], ["seated"] * 3, "no seat changed hands")
        self.assertEqual(len([b for b in f.h.venue.sent if b["side"] == "sell"]), 3, "their own sells went through the pause")
        during = [i for i in f.h.intents(kind="buy") if f.days[4].isoformat() <= i.exec_day <= f.days[14].isoformat()]
        self.assertEqual(len(during), 33)
        self.assertEqual({(i.status, i.why) for i in during}, {("missed", f"the entry cut-off passed (last: {PAUSED})")})
        after = [i for i in f.h.intents(kind="buy") if i.exec_day == f.days[15].isoformat()]
        self.assertEqual({i.status for i in after}, {"done"}, "the pause lifted: they buy again")
        plan = f.seats()
        self.assertEqual([x["day"] for x in plan["left_out"]], [f.days[n].isoformat() for n in range(3, 15)])
        self.assertEqual({x["why"] for x in plan["left_out"]}, {f"open window: {PAUSED}"})
        self.assertEqual({(h["left_out"], h["seated_sessions"], h["idle"]) for h in plan["holders"]}, {(12, 6, False)})
        self.assertIn("(12 more left out: the House refused every open)", self.work(f, 19)["seats"])
        self.assert_nothing_was_ever_forced(f, own_sells=3)

    def test_a_program_idle_of_its_own_choice_still_yields_once_it_has_ten_sessions_of_its_own(self):
        """The same ten paused sessions (3 to 12), a daily trader and a program that never asks. The pause is left
        out of both clocks; the idle program has two sessions of its own before it and yields at the decision of
        its tenth, session 20 (without the pause: session 10). The trader never does."""
        f = self.floor()
        f.add("daily", "SPY", k=240, passed=1.0)
        f.add("holds", "QQQ", k=230, passed=2.0)
        f.add("rare", "IWM", k=100, passed=3.0)
        f.add("slow", "DIA", k=5, passed=4.0)
        f.plan("daily", {"buy": "SPY", **BUY})
        f.plan("holds", {"buy": "QQQ", **BUY})
        for n in range(0, 21):
            if n == 1:
                f.plan("holds")
                f.plan("daily")
            if n == 2:
                [lot] = f.h.book._lots(instance=f.key("daily"))
                f.plan("daily", {"sell": lot.lid, "at": "open"})
            if n == 3:
                f.plan("daily", {"buy": "SPY", **BUY})
            if n == 14:
                f.plan("daily")                                    # one lot bought at session 14's open, then held
            self.work(f, n, blocked=PAUSED if 3 <= n <= 12 else None)
            rare = {h["family"]: h for h in f.seats()["holders"]}.get("rare")
            if n < 20:
                counted = n if n < 3 else 2 if n <= 12 else n - 10
                self.assertEqual((rare["seated_sessions"], rare["left_out"], rare["idle"]),
                                 (counted, max(0, min(n, 12) - 2), False), f"session {n}")
                self.assertEqual(f.band("rare"), "probe", f"session {n}")
        self.assertEqual((f.band("rare"), f.band("slow")), ("candidate", "probe"), "ten sessions of its own: it yields")
        self.assertEqual([(e["action"], e["family"]) for e in f.events()[3:]], [("yielded", "rare"), ("seated", "slow")])
        self.assertIn("seated 10", f.events()[3]["why"])
        self.assertEqual({f.band("daily"), f.band("holds")}, {"probe"})
        self.assert_nothing_was_ever_forced(f, own_sells=1)

    def test_each_house_wide_reason_is_what_open_block_answers_before_the_instance(self):
        """The reasons A30 names, each alone for a whole session: the pause and the grant (the House's own
        `real_block`), the kill switch, a stop, the reconciliation's freeze, a corporate action's freeze, the stock
        proof's BUY stage not passed, a failed SELL stage, the lane switched off. Each is what `_open_block` answers
        for ANY program, each leaves the session out, and none is the instance's own."""
        def freeze(h):
            h.state.put("eq_freeze", {"why": "an unexplained corporate action on a held symbol"})

        def unfreeze(h):
            h.state.execute("DELETE FROM kv WHERE key='eq_freeze'")

        def recon(h):
            # (As two mismatched readings in a row leave it; the share nobody owns keeps every later reading bad.)
            h.venue.held["XLF"] = D("1")
            h.state.put("eq_recon", {"frozen": "XLF: the account holds 1, the equity book expects 0", "bad": 2})

        def unrecon(h):
            h.venue.held.pop("XLF")
            h.state.execute("DELETE FROM kv WHERE key='eq_recon'")

        reasons = {
            "paused": (lambda h: setattr(h, "blocked", PAUSED), lambda h: setattr(h, "blocked", None), PAUSED),
            "the grant": (lambda h: setattr(h, "blocked", "the grant options-swarm-20260928 is not active on the money rules in force"),
                          lambda h: setattr(h, "blocked", None), "the grant"),
            "a stop": (lambda h: setattr(h, "blocked", "the daily stop: no new real entry today"),
                       lambda h: setattr(h, "blocked", None), "the daily stop"),
            "the kill switch": (lambda h: setattr(h, "kill", True), lambda h: setattr(h, "kill", False), "kill switch is engaged"),
            "a corporate action's freeze": (freeze, unfreeze, "equity reconciliation: an unexplained corporate action"),
            "the BUY stage": (lambda h: setattr(h.proof, "ok", False), lambda h: setattr(h.proof, "ok", True),
                              "BUY stage (paper_proof_stock_buy) has not passed"),
            "a failed SELL stage": (lambda h: setattr(h.proof, "failed", "the practice sale did not fill"),
                                    lambda h: setattr(h.proof, "failed", ""), "new real equity buys stop until it passes"),
            "the reconciliation's freeze": (recon, unrecon, "equity reconciliation: XLF"),
        }
        f = self.floor()
        f.add("rare", "IWM", k=100, passed=3.0)
        f.session(0)
        for n, (name, (on, off, words)) in enumerate(reasons.items(), 1):
            with self.subTest(name):
                on(f.h)
                answer = f.h.book._open_block(lambda opening=True: f.h.blocked, L.OPEN_PROBE, lambda: f.h.kill)
                self.assertIn(words, answer or "")
                self.assertNotIn("not at Probe or Sized", answer)
                for mm in (31, 33):
                    f.h.tick(9, mm, day=f.days[n])
                off(f.h)
                for hh, mm in ((16, 21), (16, 31), (16, 32)):
                    f.h.tick(hh, mm, day=f.days[n])
                note = f.h.state.get(L.OPEN_NOTE_KEY)[f.days[n].isoformat()]
                self.assertEqual(set(note), {"open"})
                self.assertFalse(note["open"]["clear"])
                self.assertIn(words, note["open"]["why"])
                self.assertIn(f.days[n].isoformat(), f.h.book._refused_days())
        held = f.seats()["holders"][0]
        self.assertEqual((held["seated_sessions"], held["left_out"]), (0, len(reasons)), "eight sessions on, none counted")
        # The answer the note is written from is the House's alone: with nothing refused it is None for the probe,
        # and for an instance that holds no seat it is the instance's own reason, which the note never sees.
        self.assertIsNone(f.h.book._open_block(lambda opening=True: None, L.OPEN_PROBE, lambda: False))
        self.assertTrue(L.OPEN_PROBE.live)
        self.assertEqual(f.h.book._open_block(lambda opening=True: None, None, lambda: False),
                         "the program is not at Probe or Sized")

    def test_what_is_a_refused_session_and_what_is_not(self):
        """A window the House looked in and never would have opened in, either one: left out. A window that cleared
        at any minute, a refusal that is a program's own (its sleeve, the instrument cap, cash), a session the House
        did not look at: counted. And nothing a program writes reaches the note."""
        f = self.floor()
        f.add("rare", "IWM", k=100, passed=3.0)
        f.add("busy", "SPY", k=200, passed=1.0)
        f.session(0)
        h = f.h

        def session(n: int, ticks: dict) -> dict:
            """`ticks`: {(hh, mm): what the House answers every open at that minute (None: it may go)}."""
            for (hh, mm), blocked in ticks.items():
                h.blocked = blocked
                h.tick(hh, mm, day=f.days[n])
            h.blocked = None
            for hh, mm in ((16, 21), (16, 31), (16, 32)):
                h.tick(hh, mm, day=f.days[n])
            return dict(h.book._refused_days())

        first = f.days[1].isoformat()
        # 1: refused at 09:31, clear at 09:33: the open window cleared, and an entry of that window had its chance.
        self.assertNotIn(first, session(1, {(9, 31): PAUSED, (9, 33): None}))
        # 2: clear at 09:31 and refused afterwards: clear is kept (a later refusal does not undo a minute that was open).
        self.assertNotIn(f.days[2].isoformat(), session(2, {(9, 31): None, (9, 33): PAUSED, (9, 40): PAUSED}))
        # 3: the open window clear, the close window refused at every minute the House looked (a stop tripped at noon).
        got = session(3, {(9, 31): None, (15, 55): "the daily stop: no new real entry today",
                          (15, 58): "the daily stop: no new real entry today"})
        self.assertEqual(got.get(f.days[3].isoformat()), "close window: the daily stop: no new real entry today")
        # 4: both refused: the session's own order, the open window's reason first.
        got = session(4, {(9, 31): PAUSED, (15, 56): "the gateway's kill switch is engaged"})
        self.assertEqual(got.get(f.days[4].isoformat()), f"open window: {PAUSED}")
        # 5: minutes outside the two entry windows say nothing (09:30 before the first send, 09:45 the cut-off itself,
        # midday, 15:59:30 on): refused at each, and the session counts.
        for (hh, mm, ss) in ((9, 30, 3), (9, 45, 3), (12, 0, 3), (15, 59, 31)):
            h.blocked = PAUSED
            h.tick(hh, mm, ss, day=f.days[5])
        self.assertNotIn(f.days[5].isoformat(), session(5, {}))
        self.assertNotIn(f.days[5].isoformat(), h.state.get(L.OPEN_NOTE_KEY), "no window was looked at")
        # 6: a program's own refusal (its buy asks for more than the account's cash) is no word of the House's.
        f.plan("busy", {"buy": "SPY", **BUY})
        f.session(6, windows=False)
        f.plan("busy")
        cash, h.venue.cash = h.venue.cash, D("30")
        got = session(7, {(9, 31): None, (9, 33): None})
        h.venue.cash = cash
        [intent] = h.intents(instance=f.key("busy"), kind="buy")
        self.assertIn("sizing (cash): refused", intent.why)
        self.assertNotIn(f.days[7].isoformat(), got)
        # 8: NOTHING A PROGRAM WRITES REACHES THE NOTE: a tag that says the House is paused, on a buy that goes.
        f.plan("busy", {"buy": "SPY", "share": 0.5, "at": "open", "tag": f"{PAUSED}: open window refused"})
        f.session(8, windows=False)
        f.plan("busy")
        got = session(9, {(9, 31): None, (9, 33): None})
        self.assertEqual(len(h.book._lots(instance=f.key("busy"))), 1)
        self.assertEqual(got, {f.days[3].isoformat(): "close window: the daily stop: no new real entry today",
                               f.days[4].isoformat(): f"open window: {PAUSED}"})
        # A session the House did not look at at all (it did not run in the windows) is not one: it counts.
        f.session(10, windows=False)
        rare = {x["family"]: x for x in f.seats()["holders"]}["rare"]
        self.assertEqual((rare["seated_sessions"], rare["left_out"]), (8, 2))
        # THE KV: today's note while it is today's, and the refused sessions; a clear day is gone the day after.
        self.assertEqual(sorted(h.state.get(L.OPEN_NOTE_KEY)), [f.days[3].isoformat(), f.days[4].isoformat(),
                                                                f.days[9].isoformat()])
        self.assertEqual(h.state.get(L.OPEN_NOTE_KEY)[f.days[9].isoformat()], {"open": {"clear": True}})

    def test_the_note_is_the_books_own_and_a_restart_keeps_it(self):
        f = self.floor()
        f.add("rare", "IWM", k=100, passed=3.0)
        f.add("late", "DIA", k=1, passed=9.0)
        f.h.families.roster = 1
        f.session(0)
        for n in range(1, 6):
            self.work(f, n, blocked=PAUSED)
        note = f.h.state.get(L.OPEN_NOTE_KEY)
        f.h.book = f.h.new_book()                                # the House starts again
        self.assertEqual(f.h.state.get(L.OPEN_NOTE_KEY), note)
        f.h.blocked = None
        f.run(6, 14)
        self.assertEqual(f.band("rare"), "probe", "nine sessions of its own (6 to 14): not yet")
        f.session(15)
        self.assertEqual((f.band("rare"), f.band("late")), ("candidate", "probe"))
        # A note that is no note (a kv someone damaged) is read as no refusal, never as an error of the seat rule.
        f.h.state.put(L.OPEN_NOTE_KEY, ["not", "a", "note"])
        self.assertEqual(f.h.book._refused_days(), {})
        f.h.state.put(L.OPEN_NOTE_KEY, {"not-a-day": {"open": {"clear": False, "why": "x"}}, "2026-10-13": "nor this"})
        self.assertEqual(f.h.book._refused_days(), {})
        self.assertNotIn("errors", f.session(16))

    def test_first_come_keeps_no_note_and_asks_the_house_nothing_more(self):
        with X.seat_rule("first-come"):
            f = self.floor()
            f.add("a-first", "SPY", k=1, passed=1.0)
            asked = []
            real = f.h.book._open_block
            f.h.book._open_block = lambda *a, **k: asked.append(a) or real(*a, **k)
            for n in range(0, 3):
                self.work(f, n, blocked=PAUSED)
            self.assertIsNone(f.h.state.get(L.OPEN_NOTE_KEY))
            self.assertEqual(asked, [], "with no entry to send, the rollback value asks `_open_block` nothing")


# ================================================================================================= the check's minors
class TheMinors(TS.SeatCase):
    def rare(self, **floor) -> TS.Floor:
        f = self.floor(**floor)
        f.add("busy-1", "SPY", k=200, passed=1.0)
        f.add("busy-2", "SPY", k=150, passed=2.0)
        f.add("rare", "QQQ", k=100, passed=3.0)
        f.add("late", "IWM", k=1, passed=9.0)
        for family in ("busy-1", "busy-2"):
            f.plan(family, {"buy": "SPY", **BUY})
        f.session(0)
        for family in ("busy-1", "busy-2"):
            f.plan(family)
        return f

    def record(self, f: TS.Floor, family: str, n: int) -> None:
        """A real record at the program loss line, by hand: EDM1 names the program at its next reading."""
        inst = f.inst(family) or L.Instance(f.key(family), family, 1, "beta", "r1", T.CODE, {}, "candidate", False, 20,
                                            created_at=1.0, retired_at=2.0, why="demoted: long ago")
        lot = f.h.lot(inst, "DIA", "1", "450", opened=TS.FRIDAY)
        f.h.venue.held["DIA"] -= D("1")
        lot.status, lot.qty, lot.cash, lot.exit_day, lot.closed_at = "closed", D(0), D("-300"), f.days[n].isoformat(), 5.0
        f.h.book._save_lot(lot)

    # ------------------------------------------------------------------------------------------ EDM1 at the seating
    def test_edm1_at_the_seating_writes_the_demotion_and_leaves_the_plan_true(self):
        """A program that yielded waits flagged idle. A seat frees between two decisions, and at its seating in the
        seating pass EDM1 names it (its record moved since the day's sync). The same `waiting_demoted` record and the
        same alert as the day's own pass; its idle flag is dropped; the plan no longer lists it as waiting; the
        seat falls through to the next program in the same sync."""
        f = self.rare(seats=4, roster=3)
        f.run(1, 10)
        self.assertEqual((f.waiting(), sorted(f.seats()["idle"])), ([("rare", 1, True)], ["rare"]))
        f.add("next", "DIA", k=0, passed=20.0)
        f.h.tick(16, 33, day=f.days[10])
        self.assertEqual(f.waiting(), [("next", 1, False), ("rare", 2, True)])
        self.record(f, "next", 10)
        f.add("after", "XLK", k=0, passed=21.0)
        alerts = len(f.h.alerts)
        f.h.families.roster = 4                                    # a fourth seat, mid-evening
        f.h.tick(16, 40, day=f.days[10])
        self.assertEqual(sorted(f.holders()), ["after", "busy-1", "busy-2", "late"], "it fell through to the next")
        plan = f.seats()
        self.assertEqual(f.waiting(), [("rare", 1, True)], "the demoted program is not in the plan's waiting list")
        self.assertEqual(plan["sticky"], ["next"])
        self.assertEqual([(e["action"], e["family"], e.get("rank")) for e in f.events()[-2:]],
                         [("waiting_demoted", "next", 1), ("seated", "after", 2)])
        self.assertTrue(f.events()[-2]["why"].startswith("EDM1:"))
        told = [text for _, text in f.h.alerts[alerts:] if "waited for a seat and is demoted" in text]
        self.assertEqual(len(told), 1, f.h.alerts[alerts:])
        self.assertIn(f.key("next"), told[0])
        self.assertFalse([e for e in f.events() if e["action"] == "passed_over"], "a demotion is not a seating to try again")
        for mm in (41, 42, 43):                                    # the pass runs every minute: said once
            f.h.tick(16, mm, day=f.days[10])
        self.assertEqual(len([e for e in f.events() if e["action"] == "waiting_demoted"]), 1)
        self.assertEqual(len([t for _, t in f.h.alerts if "waited for a seat and is demoted" in t]), 1)
        # A FLAGGED program named at its seating loses its flag with its place: `rare`, its record at the line too.
        self.record(f, "rare", 10)
        f.h.families.rows["late"]["band"] = "retired"
        f.h.tick(16, 50, day=f.days[10])
        plan = f.seats()
        self.assertEqual((f.waiting(), plan["idle"], plan["sticky"]), ([], {}, ["next", "rare"]))
        self.assertEqual((f.events()[-1]["action"], f.events()[-1]["family"]), ("waiting_demoted", "rare"))
        f.run(11, 13)
        self.assertEqual({f.band("next"), f.band("rare")}, {"candidate"}, "a seat is free and neither returns")

    # ------------------------------------------------------------------------------------- the yield's two writes
    def test_a_live_write_that_fails_inside_the_yield_leaves_the_band_where_it_was(self):
        """THE CHECK'S P3: the live state's write fails inside the yield, on the day the rare program's signal fires,
        with a better-ranked program waiting. Before: the swarm's store had the band (written first), the book still
        ran the instance, it bought the next session and that lot was sold as `demoted`. Now the swarm's write is the
        last statement of the transaction: nothing moved at all, the program keeps its seat, buys its lot and
        holds it; the day after its failed yield it is no longer flat, and nobody sells anything."""
        f = self.rare()
        f.h.families.rows["late"]["seat_activity"] = TS.counts(180)        # the waiting program ranks above `rare`
        f.run(1, 9)
        real = f.h.book._save_instance
        fired = []

        def save(inst):
            if inst.family == "rare" and str(inst.why).startswith(L.YIELDED) and not fired:
                fired.append(inst.id)
                raise RuntimeError("the live state's write failed (injected)")
            return real(inst)

        f.h.book._save_instance = save
        moves = len(f.h.families.moves)
        f.plan("rare", {"buy": "QQQ", **BUY})                      # its rare signal fires at this very decision
        out = f.session(10)
        f.plan("rare")
        self.assertEqual(fired, [f.key("rare")])
        self.assertTrue(any(e.startswith("seats: RuntimeError") for e in f.h.book._last.get("errors", []) + out.get("errors", [])))
        self.assertEqual(len(f.h.families.moves), moves, "the swarm's store was never written")
        self.assertEqual((f.band("rare"), f.band("late")), ("probe", "candidate"))
        inst = f.inst("rare")
        self.assertEqual((inst.retired_at, inst.band, inst.why), (None, "probe", ""))
        self.assertEqual(f.h.state.get(L.SEAT_KEY).get("idle"), {}, "no flag")
        self.assertIsNone(f.h.state.get(L.SEAT_KEY).get("yield_day"))
        self.assertEqual(f.h.state.get("eq_band_since")[f.key("rare")]["band"], "probe")
        self.assertEqual(inst.last_decided_day, f.days[10].isoformat(), "the day's decision ran all the same")
        f.run(11, 14)
        [lot] = f.h.book._lots(instance=f.key("rare"))
        self.assertEqual((lot.symbol, lot.status, f.band("rare")), ("QQQ", "open", "probe"), "it bought its lot and holds it")
        self.assertEqual(f.band("late"), "candidate")
        self.assert_nothing_was_ever_forced(f)

    def test_a_row_that_changed_rolls_the_whole_yield_back(self):
        f = self.rare()
        f.run(1, 9)
        before = {k: f.h.state.get(k) for k in (L.SEAT_KEY, "eq_band_since")}
        instance = dict(f.h.state.rows("SELECT * FROM eq_instances WHERE id=?", (f.key("rare"),))[0])
        with mock.patch.object(f.h.families, "confirm_band", return_value=False):
            out = f.session(10)
        self.assertIn("rare: the row changed; no yield", out.get("bands", []) + f.h.book._last.get("bands", []))
        self.assertEqual(dict(f.h.state.rows("SELECT * FROM eq_instances WHERE id=?", (f.key("rare"),))[0]),
                         {**instance, "last_decided_day": f.days[10].isoformat()}, "the retirement was rolled back")
        after = {k: f.h.state.get(k) for k in (L.SEAT_KEY, "eq_band_since")}
        self.assertEqual(after["eq_band_since"], before["eq_band_since"])
        self.assertEqual((after[L.SEAT_KEY].get("idle"), after[L.SEAT_KEY].get("yield_day")), ({}, None))
        self.assertEqual(f.inst("rare").retired_at, None)
        f.session(11)
        self.assertEqual((f.band("rare"), f.band("late")), ("candidate", "probe"))

    def test_a_commit_that_fails_after_the_swarms_write_moves_the_band_back(self):
        """The one window left: the live state's COMMIT itself fails after the swarm's store took the band. The band
        is moved back to the seat's own before the error goes on; the store and the book say the same."""
        f = self.rare()
        f.run(1, 9)
        h = f.h
        proxy = CommitFails(h.state.db)
        h.state.db = proxy
        self.addCleanup(lambda: setattr(h.state, "db", proxy.db))
        real = h.families.confirm_band

        def confirm(expected, band, reason):
            done = real(expected, band, reason)
            if done and band == "candidate" and expected["family"] == "rare":
                proxy.armed = True                                 # the swarm has the band: now the commit fails
            return done

        with mock.patch.object(h.families, "confirm_band", confirm):
            out = f.session(10)
        self.assertEqual(proxy.failed, 1)
        self.assertTrue(any(e.startswith("seats: OperationalError") for e in h.book._last.get("errors", []) + out.get("errors", [])))
        self.assertEqual([(m[0], m[1]) for m in h.families.moves[-2:]], [("rare", "candidate"), ("rare", "probe")])
        self.assertIn("its yield could not be written", h.families.moves[-1][2])
        self.assertEqual((f.band("rare"), f.band("late")), ("probe", "candidate"))
        self.assertEqual((f.inst("rare").retired_at, f.inst("rare").band), (None, "probe"))
        self.assertFalse([t for level, t in h.alerts if level == "error"], "moved back: nothing to tell")
        f.session(11)
        self.assertEqual((f.band("rare"), f.band("late")), ("candidate", "probe"), "and the next day it yields")
        # When the band cannot be moved back either, the owner is told; the next sync settles it with nothing sold.
        g = self.rare()
        g.run(1, 9)
        proxy2 = CommitFails(g.h.state.db)
        g.h.state.db = proxy2
        self.addCleanup(lambda: setattr(g.h.state, "db", proxy2.db))
        real2 = g.h.families.confirm_band

        def confirm2(expected, band, reason):
            if band == "probe" and expected["family"] == "rare" and proxy2.failed:
                return False                                       # the way back is refused too
            done = real2(expected, band, reason)
            if done and band == "candidate" and expected["family"] == "rare":
                proxy2.armed = True
            return done

        with mock.patch.object(g.h.families, "confirm_band", confirm2):
            g.session(10)
            self.assertTrue([t for level, t in g.h.alerts if level == "error" and "could not be moved back" in t])
            self.assertEqual((g.band("rare"), g.inst("rare").retired_at), ("candidate", None), "the split, as it would stand")
            g.run(11, 13)
        self.assertEqual(g.band("late"), "probe")
        self.assertEqual(g.h.intents(kind="house_exit"), [])
        self.assertEqual([b for b in g.h.venue.sent if b["side"] == "sell"], [])

    def test_the_yield_refuses_to_run_inside_another_transaction(self):
        f = self.rare()
        f.run(1, 9)
        real = L.EquityBook._seat_bands

        def inside(book, *a, **k):
            with book.state.transaction():
                return real(book, *a, **k)

        with mock.patch.object(L.EquityBook, "_seat_bands", inside):
            out = f.session(10)
        self.assertIn("rare: no yield inside another transaction", out.get("bands", []) + f.h.book._last.get("bands", []))
        self.assertEqual((f.band("rare"), f.inst("rare").retired_at), ("probe", None))

    # ------------------------------------------------------------------------- the stale flag; first come's return
    def test_a_stale_idle_flag_is_dropped_when_its_family_holds_a_seat(self):
        """A rollback and a roll forward: `rare` yields under the rule, the rule goes to "first-come" and a seat frees:
        it is seated again by pass time. Its flag is dropped at that sync (the report's `idle_flagged` never names a
        seated program), and when the rule comes back the plan is clean."""
        from league.ops import dlane_report as R

        f = self.rare()
        f.run(1, 10)
        self.assertEqual(sorted(f.seats()["idle"]), ["rare"])
        with X.seat_rule("first-come"):
            f.h.book = f.h.new_book()
            f.session(11)
            self.assertEqual(sorted(f.seats()["idle"]), ["rare"], "it waits: the flag is kept, simply not read")
            f.h.families.rows["late"]["band"] = "retired"
            f.session(12, windows=False)
            self.assertEqual(sorted(f.holders()), ["busy-1", "busy-2", "rare"])
            self.assertEqual(f.seats()["idle"], {}, "seated again: the flag is gone under first come too")
            seats = R.equity_seats(None, R.read_book(Path(f.h.state.path)), set())
            self.assertEqual(seats["idle_flagged"], [])
        f.h.book = f.h.new_book()                                  # the rule is back
        f.session(13)
        plan = f.seats()
        self.assertEqual((plan["rule"], plan["idle"], f.waiting()), ("activity-1-free", {}, []))
        self.assertFalse(any(h["family"] in plan["idle"] for h in plan["holders"]))
        # The same guard under the rule itself: a flag written for a family whose band is live is dropped at the sync.
        memory = f.h.state.get(L.SEAT_KEY)
        f.h.state.put(L.SEAT_KEY, {**memory, "idle": {"busy-1": {"day": "2026-10-12", "why": "stale"}}})
        f.h.tick(16, 40, day=f.days[13])                           # the seating pass
        self.assertEqual(f.seats()["idle"], {})

    def test_under_first_come_a_yielded_programs_return_is_not_a_decision_late(self):
        """The rollback with a yielded program waiting: a seat frees between two decisions, and the seating pass moves
        its band AND brings its instance back in the same pass, so it is asked for the same close. (Before, its band
        moved there and its instance came back only at the next decision: its first order a session later.)"""
        f = self.rare()
        f.run(1, 10)
        self.assertEqual(f.waiting(), [("rare", 1, True)])
        with X.seat_rule("first-come"):
            f.h.book = f.h.new_book()
            f.session(11)
            self.assertEqual((f.band("rare"), f.inst("rare").retired_at is None), ("candidate", False), "every seat is held")
            f.h.families.rows["late"]["band"] = "retired"          # a seat frees after the day's decision
            f.h.tick(16, 40, day=f.days[11])                       # the seating pass
            inst = f.inst("rare")
            self.assertEqual((f.band("rare"), inst.retired_at, inst.band, inst.why), ("probe", None, "probe", ""),
                             "its band and its instance in the same pass")
            self.assertEqual(inst.last_decided_day, f.days[11].isoformat(), "asked for the same close")
            self.assertEqual(f.seats()["idle"], {})
            self.assertEqual(f.h.state.get("eq_decide")["instances"].count(f.key("rare")), 1)
        self.assertEqual([b for b in f.h.venue.sent if b["side"] == "sell"], [])

    # --------------------------------------------------------------------------------------------- the seat's date
    def test_a_seat_taken_after_its_sessions_open_counts_from_the_next_session(self):
        """THE CHOICE (the check's last minor): a seat taken in the seating pass before the next session's open is
        dated the decision day, and that session is its first; one taken once the open has begun (09:30:30) is
        counted from the session after, so the idle test names it only after ten sessions it sat through whole.
        The mark's own `day` stays the decision day every other reader of `eq_band_since` knows."""
        for at, whole in (((16, 40, 0), True), ((9, 30, 1), True), ((9, 31, 1), False), ((15, 50, 1), False)):
            with self.subTest(at=at):
                f = self.floor(seats=4, roster=3)
                f.add("busy-1", "SPY", k=200, passed=1.0)
                f.add("busy-2", "QQQ", k=150, passed=2.0)
                f.add("busy-3", "DIA", k=120, passed=3.0)
                for family, symbol in (("busy-1", "SPY"), ("busy-2", "QQQ"), ("busy-3", "DIA")):
                    f.plan(family, {"buy": symbol, **BUY})
                f.session(0)
                for family in ("busy-1", "busy-2", "busy-3"):
                    f.plan(family)
                f.run(1, 3)
                f.add("new", "IWM", k=50, passed=30.0)             # it passes its look, and a fourth seat opens
                f.h.families.roster = 4
                hh, mm, plus = at
                f.h.tick(hh, mm, day=f.days[3 + plus])
                mark = f.h.state.get("eq_band_since")[f.key("new")]
                first = f.days[3] if whole else f.days[4]
                self.assertEqual(mark, {"band": "probe", "day": f.days[3].isoformat(),
                                        **({} if whole else {"seat": f.days[4].isoformat()})})
                held = {x["family"]: x for x in f.seats()["holders"]}["new"]
                self.assertEqual((held["since"], held["seated_sessions"]), (first.isoformat(), 0))
                self.assertEqual(f.inst("new").last_decided_day, f.days[3].isoformat(), "asked for the same close")
                f.add("late", "XLK", k=1, passed=40.0)
                last = 13 if whole else 14
                for n in range(4, last):
                    f.session(n)
                    self.assertEqual(f.band("new"), "probe", f"session {n}")
                held = {x["family"]: x for x in f.seats()["holders"]}["new"]
                self.assertEqual((held["seated_sessions"], held["idle"]), (9, False))
                f.session(last)
                self.assertEqual((f.band("new"), f.band("late")), ("candidate", "probe"),
                                 "ten whole sessions seated, and then it yields")

    def test_a_returned_programs_late_seat_keeps_its_own_session_through_the_revival(self):
        f = self.rare(seats=4, roster=3)
        f.run(1, 10)
        self.assertEqual(f.waiting(), [("rare", 1, True)])
        f.h.families.roster = 4
        f.h.tick(10, 0, day=f.days[11])                            # a seat opens in the middle of session 11
        inst = f.inst("rare")
        self.assertEqual((inst.retired_at, inst.band), (None, "probe"))
        self.assertEqual(f.h.state.get("eq_band_since")[f.key("rare")],
                         {"band": "probe", "day": f.days[10].isoformat(), "seat": f.days[11].isoformat()})
        f.h.tick(10, 1, day=f.days[11])
        self.assertEqual(f.h.state.get("eq_band_since")[f.key("rare")]["seat"], f.days[11].isoformat())
        f.session(11, windows=False)
        held = {x["family"]: x for x in f.seats()["holders"]}["rare"]
        self.assertEqual((held["since"], held["seated_sessions"]), (f.days[11].isoformat(), 0))

    # ------------------------------------------------------------------------------------------------ the tripwire
    def test_a_lot_of_a_program_that_yielded_is_never_silent(self):
        """What must never happen, if it ever did: a lot booked to a program after it yielded. The House's own rule
        for a program that no longer runs takes the lot out at the next open (no stuck lot), and the owner is told
        at error level that the seat rule's promise was broken by the order path."""
        f = self.rare()
        f.run(1, 10)
        inst = f.inst("rare")
        self.assertTrue(inst.why.startswith(L.YIELDED))
        f.h.lot(inst, "QQQ", "0.5", "500", opened=f.days[10])
        f.session(11)
        [exit_] = f.h.intents(kind="house_exit")
        self.assertEqual((exit_.instance, exit_.tag), (f.key("rare"), "retired"))
        [told] = [t for level, t in f.h.alerts if level == "error" and "YIELDED" in t]
        self.assertIn("The seat rule must never end in a sale", told)
        self.assertIn(f.key("rare"), told)
        self.assertTrue([p for kind, p in f.h.events if kind == "equity.alert" and "yielded" in str(p.get("what"))])


class CommitFails:
    """The live state's connection with one COMMIT that fails (as a full disk would make it): the transaction is
    rolled back and the error raised, once, when `armed`."""

    def __init__(self, db):
        self.db, self.armed, self.failed = db, False, 0

    def execute(self, sql, *args):
        if self.armed and sql == "COMMIT":
            self.armed = False
            self.failed += 1
            self.db.execute("ROLLBACK")
            raise sqlite3.OperationalError("disk I/O error (injected)")
        return self.db.execute(sql, *args)

    def __getattr__(self, name):
        return getattr(self.db, name)


if __name__ == "__main__":
    unittest.main()
