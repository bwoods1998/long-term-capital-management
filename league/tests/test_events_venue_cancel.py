"""A80 (the captain's amendment of 16:10Z Oct 21, 2026): THE VENUE CANCELS AN EVENT BUY AT ONCE. The venue accepted
about a quarter of the event lane's auction buys and cancelled them milliseconds later, with no reason and nothing
filled; the House then finished each such intent missed at the auction's end. Now (league/equity/live.py
`_event_last`, `venue_cancel_ms`) an event ENTRY whose last order the venue cancelled within `VENUE_CANCEL_RETRY_S`
(60 s) of the order's own submission, nothing filled, is sent again ONCE through the normal path (every gate again,
`_size_event`, `_send` with its wall-clock cut-off; the gateway judges every cap again), while its auction's window is
open; a second cancel at once ends it missed at the auction's end, its why naming both; exits are unchanged.

Through the REAL book, the REAL `size_entry` and the money table in force, against test_events_book's in-memory auction
venue taught to cancel an accepted order by itself, and a lane store of invented events. No figure here is a market's."""

from __future__ import annotations

import datetime as dt
import unittest
from decimal import Decimal as D

from league.equity import live as L
from league.live.venue import Submitted
from league.tests import test_events_book as EB
from league.tests.test_events_book import CIK, DAY, NEXT, UTC, V2, at, earnings

PROGRAM = "EVL-ERN-READ-O1"     # learning: two whole shares at the $20.00 limit (E $2,000), sold at the same close


def ns(t: float) -> str:
    """An RFC 3339 stamp to the nanosecond, as the venue writes an order's `submitted_at` (invented digits)."""
    return dt.datetime.fromtimestamp(t, UTC).strftime("%Y-%m-%dT%H:%M:%S.%f") + "012Z"


def ms(t: float) -> str:
    """An RFC 3339 stamp to the millisecond, as the venue writes an order's `canceled_at`."""
    return dt.datetime.fromtimestamp(t, UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


class CancellingVenue(EB.AuctionVenue):
    """test_events_book's auction venue that also CANCELS AN ORDER IT ACCEPTED, BY ITSELF, as the venue did (A80): each
    of the next sends of `side` takes the next delay of `venue_cancels` (seconds after its own submission, in send
    order); the order is taken (a venue id, status "new", `submitted_at`) and shown `canceled` from that moment, with
    `canceled_at`, no reason and nothing filled (`fill_first` shares at `fill_px` first, when set). Every other order
    is the auction venue's."""

    def __init__(self, market, clock, *, cash="2000"):
        super().__init__(market, clock, cash=cash)
        self.venue_cancels: list[float] = []
        self.side = "buy"
        self.fill_first: D | None = None
        self.fill_px = D("17.00")

    def submit(self, body, *, exit: bool) -> Submitted:
        answer = super().submit(body, exit=exit)
        if not answer.ok:
            return answer
        o = self.book[-1]
        o["submitted_at"] = ns(self.clock())
        if body["side"] == self.side and self.venue_cancels:
            o["_venue_cancel_at"] = self.clock() + self.venue_cancels.pop(0)
        return Submitted(True, self._public(o), "", status=200)

    def _advance(self) -> None:
        for o in self.book:
            when = o.get("_venue_cancel_at")
            if when is None or o["status"] not in ("new", "accepted") or self.clock() < when:
                continue
            if self.fill_first:
                qty = self.fill_first
                o["filled_qty"], o["filled_avg_price"] = str(qty), str(self.fill_px)
                self.held[o["symbol"]] = self.held.get(o["symbol"], D(0)) + qty
                self.cash -= self.fill_px * qty
            o["status"], o["canceled_at"] = "canceled", ms(when)
        super()._advance()


class Harness(EB.Harness):
    """test_events_book's harness on the cancelling venue."""

    def __init__(self, root, **kw):
        super().__init__(root, **kw)
        self.venue = CancellingVenue(self.market, self.clock, cash=kw.get("cash", "2000"))
        self.book = self.new_book()


class VenueCancelTest(EB.EventTest):
    def harness(self, **kw) -> Harness:
        h = Harness(self.root, **kw)
        self.addCleanup(h.state.close)
        self.addCleanup(h.lane.st.close)
        self.addCleanup(lambda: h.book._event_lane is not None and h.book._event_lane.close())
        return h

    def one_buy(self, h: Harness, *cancels: float) -> None:
        """One READ-O1 pick (ACME, the lane's own decision first), its prints at the open and the close, and the venue's
        own cancels of the next buys."""
        earnings(h.lane, "a-1", CIK, "ACME")
        h.lane.intent(V2(PROGRAM), "8k:a-1", "ACME", CIK, DAY, DAY)
        self.ready(h)
        h.symbol("ACME", last=17.0, sd=0.02)
        h.venue.prints[("ACME", DAY.isoformat(), "open")] = D("17.00")
        h.venue.prints[("ACME", DAY.isoformat(), "close")] = D("17.50")
        h.venue.venue_cancels = list(cancels)

    def shape(self, body: dict) -> dict:
        return {k: v for k, v in body.items() if k != "client_order_id"}

    def buy(self, h: Harness) -> dict:
        [buy] = h.event_intents("buy")
        return buy

    def said(self, h: Harness) -> list[tuple[str, str]]:
        return [(level, text) for level, text in h.alerts if "A80" in text]


# ------------------------------------------------------------------------------------------------------- the rule
class TheRule(unittest.TestCase):
    """`venue_cancel_ms`: the venue's own cancel of an auction BUY, read off the order's own stamps."""

    def order(self, *, side="buy", tif="opg", status="canceled", final="canceled", filled="0", submitted=None,
              canceled=None, **answer) -> L.Order:
        t0 = at(DAY, 9, 16)
        stamps = {"submitted_at": ns(t0) if submitted is None else submitted,
                  "canceled_at": ms(t0 + 0.005) if canceled is None else canceled}
        return L.Order(1, "lq-x-1-f", "f@2:r", "f", side, "ACME", "stock", "open", D(2), D("20.00"), 0, status, t0,
                       DAY.isoformat(), venue_id="v", filled_qty=D(filled),
                       answer={"tick": t0, "final": final, **stamps, **answer}, tif=tif, otype="limit")

    def test_the_venue_cancel_of_an_auction_buy_within_60_s_of_its_submission_nothing_filled(self):
        t0 = at(DAY, 9, 16)
        self.assertEqual(L.VENUE_CANCEL_RETRY_S, 60)
        self.assertEqual(L.venue_cancel_ms(self.order()), 5)
        self.assertEqual(L.venue_cancel_ms(self.order(tif="cls")), 5, "a close entry alike")
        self.assertEqual(L.venue_cancel_ms(self.order(canceled=ms(t0 + 60))), 60000, "60 s is inside")
        self.assertIsNone(L.venue_cancel_ms(self.order(canceled=ms(t0 + 60.001))), "after 60 s: the auction's own end")
        self.assertIsNone(L.venue_cancel_ms(self.order(canceled=ms(t0 + 180))))
        self.assertEqual(L.venue_cancel_ms(self.order(submitted="2026-11-04T14:16:03.957047012Z",
                                                      canceled="2026-11-04T14:16:03.957Z")), 0,
                         "inside its own millisecond: the cancel's stamp is cut to the millisecond")
        self.assertIsNone(L.venue_cancel_ms(self.order(submitted="2026-11-04T14:16:03.959Z",
                                                       canceled="2026-11-04T14:16:03.957Z")), "before its submission")
        for why, kw in (("a sale", {"side": "sell"}), ("a day order", {"tif": "day"}), ("a fill", {"filled": "1"}),
                        ("not canceled", {"status": "expired", "final": "expired"}),
                        ("replaced, not cancelled", {"final": "replaced"}),
                        ("the House's own cancel", {"cancel_sent": t0 + 1}),
                        ("no submission stamp", {"submitted": ""}), ("an unreadable cancel stamp", {"canceled": "x"}),
                        ("a stamp with no zone", {"canceled": "2026-11-04T14:16:03.962"})):
            with self.subTest(why):
                self.assertIsNone(L.venue_cancel_ms(self.order(**kw)))


# ------------------------------------------------------------------------------------------------------- the day
class TheResend(VenueCancelTest):
    def test_a_buy_the_venue_cancelled_5_ms_after_its_submission_goes_again_once_and_fills(self):
        """(a) The venue cancels the first buy 5 ms after it accepted it; the next minute reads the cancel and the buy
        goes again: the same symbol, side, shares, limit, time in force and type, a new client id, the cancelled one
        its `replaces`. The re-send fills at the cross: the intent is done, one lot, the real fill written back once,
        two orders; the minute counts it; one alert of the session, after the close's end, names the count."""
        h = self.harness()
        self.one_buy(h, 0.005)
        h.tick(9, 15)
        out = h.tick(9, 16)
        self.assertNotIn("venue_cancel_resends", out)
        [first] = h.bodies()
        out = h.tick(9, 17)
        self.assertEqual(out.get("venue_cancel_resends"), 1)
        again, resent = h.bodies()
        self.assertEqual(self.shape(resent), self.shape(first), "the same shape and limit")
        self.assertEqual(self.shape(first), {"symbol": "ACME", "qty": "2", "side": "buy", "type": "limit",
                                             "limit_price": "20.00", "time_in_force": "opg"})
        self.assertNotEqual(resent["client_order_id"], first["client_order_id"], "a new client id")
        one, two = h.orders()
        self.assertEqual((one.status, one.filled_qty, one.answer["final"]), ("canceled", D(0), "canceled"))
        self.assertEqual((two.status, two.replaces, two.tif, two.otype), ("working", one.eid, "opg", "limit"))
        self.assertTrue(two.why.startswith("A80's one re-send (the venue cancelled the first buy 5 ms after its "
                                           "submission, nothing filled): event entry at the open ("), two.why)
        self.assertEqual([e["why"][:40] for k, e in h.events if k == "equity.order" and e.get("eid") == two.eid][0],
                         two.why[:40], "the order's record says it")
        out = h.tick(9, 18)
        self.assertNotIn("venue_cancel_resends", out)
        self.assertEqual(len(h.bodies()), 2, "once")
        h.tick(9, 31)
        h.tick(9, 33)
        buy = self.buy(h)
        self.assertEqual(buy["status"], "done")
        self.assertEqual(buy["why"], "filled 2 shares at the open (A80's one re-send of the buy the venue cancelled 5 ms "
                                     "after its submission)")
        [lot] = h.lots()
        self.assertEqual((lot.qty, lot.entry_px, lot.iid, lot.lane), (D(2), D("17.000000"), buy["iid"], "event"))
        self.assertEqual([(f["side"], f["qty"], f["price"]) for f in h.lane.fills()], [("buy", 2.0, 17.0)])
        self.assertEqual(self.said(h), [], "said once, after the session's last auction")
        for hh, mm in ((15, 46), (15, 47), (16, 1), (16, 3), (16, 4), (16, 30)):
            h.tick(hh, mm)
        self.assertEqual([f["side"] for f in h.lane.fills()], ["buy", "sell"], "the buy written back once")
        self.assertEqual(h.lots()[0].status, "closed")
        self.assertEqual(self.said(h), [("info", f"equity: A80: the venue cancelled 1 event buy of {DAY.isoformat()} at "
                                                 "once (within 60 s of its submission, nothing filled); 1 went again "
                                                 "once (1 filled), 0 did not (the window's cut-off or a gate)")])
        self.assertEqual(h.state.get(L.VENUE_CANCEL_SAID), DAY.isoformat())
        h.tick(9, 15, day=NEXT)
        h.tick(16, 5, day=NEXT)
        self.assertEqual(len(self.said(h)), 1, "a session with no venue cancel says nothing")

    def test_a_second_cancel_at_once_ends_it_missed_naming_both_and_no_third_order_goes(self):
        """(b) The re-send is cancelled at once too: no third order, the intent missed at the auction's end, its why
        naming both cancels."""
        h = self.harness()
        self.one_buy(h, 0.005, 0.006)
        h.tick(9, 15)
        h.tick(9, 16)
        self.assertEqual(h.tick(9, 17).get("venue_cancel_resends"), 1)
        for mm in (18, 19, 26):
            self.assertNotIn("venue_cancel_resends", h.tick(9, mm))
        self.assertEqual(len(h.bodies()), 2, "at most two orders from venue cancels")
        self.assertEqual([o.status for o in h.orders()], ["canceled", "canceled"])
        self.assertEqual(self.buy(h)["status"], "sent", "not ended before the auction's end")
        h.tick(9, 31)
        h.tick(9, 33)
        buy = self.buy(h)
        self.assertEqual((buy["status"], buy["why"]),
                         ("missed", "not filled at the open auction (canceled; the venue cancelled the first buy 5 ms "
                                    "after its submission and A80's one re-send 6 ms after its own, nothing filled)"))
        self.assertEqual((h.lots(), len(h.bodies())), ([], 2))
        h.tick(16, 3)
        self.assertEqual([text for _, text in self.said(h)],
                         [f"equity: A80: the venue cancelled 1 event buy of {DAY.isoformat()} at once (within 60 s of its "
                          "submission, nothing filled); 1 went again once (0 filled), 0 did not (the window's cut-off "
                          "or a gate)"])

    def test_the_auctions_own_cancel_minutes_after_submission_is_never_sent_again(self):
        """(c) Cancelled three minutes after its submission (as the venue ends every unfilled auction order at its cross,
        minutes after it was sent): no re-send, missed at the auction's end as before; nothing said."""
        h = self.harness()
        self.one_buy(h, 180.0)
        h.tick(9, 15)
        for mm in (16, 17, 18, 19, 20, 26):
            self.assertNotIn("venue_cancel_resends", h.tick(9, mm))
        self.assertEqual(h.orders()[0].status, "canceled")
        h.tick(9, 31)
        h.tick(9, 33)
        self.assertEqual(len(h.bodies()), 1)
        buy = self.buy(h)
        self.assertEqual((buy["status"], buy["why"]), ("missed", "not filled at the open auction (canceled)"))
        h.tick(16, 3)
        self.assertEqual(self.said(h), [])
        self.assertIsNone(h.state.get(L.VENUE_CANCEL_SAID))

    def test_no_resend_once_the_windows_cut_off_has_passed(self):
        """(d) The cancel is read when the window's cut-off (09:27 ET) has passed: by the minute (the next minute is past
        it, so the window sends nothing), or by the wall clock at the send (the minute started inside the window, the
        equity minute ran after it: `_send` writes and POSTs nothing). Missed at the auction's end, its why saying the
        one re-send did not go."""
        for case in ("minute", "wall clock"):
            with self.subTest(case):
                self.setUp()
                h = self.harness()
                self.one_buy(h, 0.005)
                h.tick(9, 15)
                if case == "minute":
                    h.tick(9, 26)
                    out = h.tick(9, 27)
                    held = "A80's one re-send did not go before the window's cut-off"
                else:
                    h.tick(9, 25)
                    h.clock.set(at(DAY, 9, 27, 0) + 0.25)
                    out = h.book.tick(at(DAY, 9, 26), account_row=h.venue.account(), positions=None, open_orders=None,
                                      real_block=lambda opening=True: None, killed=lambda: False)
                    held = ("A80's one re-send held: not sent: the window's cut-off passed on the wall clock before the "
                            "order could go")
                self.assertNotIn("venue_cancel_resends", out)
                self.assertEqual([o.status for o in h.orders()], ["canceled"], "nothing written")
                h.tick(9, 31)
                h.tick(9, 33)
                self.assertEqual(len(h.bodies()), 1)
                buy = self.buy(h)
                self.assertEqual((buy["status"], buy["why"]),
                                 ("missed", "not filled at the open auction (canceled; the venue cancelled it 5 ms after "
                                            f"its submission, nothing filled; {held})"))
                h.tick(16, 3)
                self.assertIn("0 went again once (0 filled), 1 did not", self.said(h)[0][1])

    def test_the_kill_switch_holds_the_resend(self):
        """(e) The kill switch engaged when the cancel is read: the re-send meets every gate again and is held; missed at
        the auction's end, its why naming the hold."""
        h = self.harness()
        self.one_buy(h, 0.005)
        h.tick(9, 15)
        h.tick(9, 16)
        h.kill = True
        out = h.tick(9, 17)
        self.assertNotIn("venue_cancel_resends", out)
        self.assertEqual(self.buy(h)["why"], "A80's one re-send held: the gateway's kill switch is engaged")
        h.tick(9, 26)
        h.tick(9, 31)
        h.tick(9, 33)
        self.assertEqual(len(h.bodies()), 1)
        buy = self.buy(h)
        self.assertEqual((buy["status"], buy["why"]),
                         ("missed", "not filled at the open auction (canceled; the venue cancelled it 5 ms after its "
                                    "submission, nothing filled; A80's one re-send held: the gateway's kill switch is "
                                    "engaged)"))
        self.assertEqual(h.lots(), [])

    def test_a_resend_the_gateway_refuses_follows_the_refusal_path(self):
        """(f) The gateway refuses the re-send: for a cap (the name's position cap), the intent ends refused at once in the
        gateway's words, as any refused buy; for a reading it could not make (its bars), nothing was sent and the re-send
        goes again the next minute, still the one re-send of the venue's cancel: two orders reach the venue."""
        for cap in ("stock_position", "bars"):
            with self.subTest(cap):
                self.setUp()
                h = self.harness()
                self.one_buy(h, 0.005)
                h.tick(9, 15)
                h.tick(9, 16)
                h.venue.gateway_refuses = cap
                self.assertEqual(h.tick(9, 17).get("venue_cancel_resends"), 1)
                one, two = h.orders()
                self.assertEqual((two.status, two.answer.get("cap"), two.replaces), ("refused", cap, one.eid))
                self.assertIn("A80's one re-send", two.why)
                h.venue.gateway_refuses = None
                out = h.tick(9, 18)
                if cap == "stock_position":
                    buy = self.buy(h)
                    self.assertEqual((buy["status"], buy["why"]),
                                     ("refused", "the refused buy: HTTP 403 refused (A80's one re-send of the buy the "
                                                 "venue cancelled 5 ms after its submission)"))
                    self.assertNotIn("venue_cancel_resends", out)
                    self.assertEqual(len(h.orders()), 2)
                    h.tick(9, 31)
                    h.tick(9, 33)
                    self.assertEqual((h.lots(), self.buy(h)["status"]), ([], "refused"))
                else:
                    self.assertEqual(out.get("venue_cancel_resends"), 1)
                    self.assertEqual([o.status for o in h.orders()], ["canceled", "refused", "working"])
                    self.assertTrue(h.orders()[2].why.startswith("A80's one re-send"))
                    h.tick(9, 31)
                    h.tick(9, 33)
                    self.assertEqual(len(h.venue.book), 2, "two orders reached the venue")
                    self.assertEqual(self.buy(h)["status"], "done")
                    self.assertEqual(h.lots()[0].qty, D(2))

    def test_an_exit_the_venue_cancelled_at_once_is_unchanged(self):
        """(g) An event lot's sale cancelled 5 ms after its submission is not sent again by A80: the sale is missed at
        the auction's end and the lot climbs the fallback ladder, as before."""
        h = self.harness()
        self.one_buy(h)
        for hh, mm in ((9, 15), (9, 16), (9, 31), (9, 33)):
            h.tick(hh, mm)
        [lot] = h.lots()
        h.venue.side, h.venue.venue_cancels = "sell", [0.005]
        h.tick(15, 46)
        h.tick(15, 47)
        self.assertEqual(h.bodies()[-1]["side"], "sell")
        for mm in (48, 49):
            self.assertNotIn("venue_cancel_resends", h.tick(15, mm))
        h.tick(16, 1)
        h.tick(16, 3)
        self.assertEqual([b["side"] for b in h.bodies()], ["buy", "sell"], "the sale went once")
        [sale] = h.event_intents("sell")
        self.assertEqual(sale["status"], "missed")
        lot = h.lots()[0]
        self.assertIn(lot.status, ("open", "closing"), "unsold: still held (closing marks the sale it sent)")
        self.assertEqual(lot.qty, D(2))
        self.assertEqual((lot.info["evl_exit"]["day"], lot.info["evl_exit"]["at"], lot.info["evl_exit"]["rung"]),
                         (NEXT.isoformat(), "close", 1), "the ladder's first rung")
        self.assertEqual(self.said(h), [], "a sale is no A80 count")

    def test_a_buy_that_filled_before_the_venue_cancelled_it_is_not_sent_again(self):
        """(h) The venue filled part of the buy before it cancelled the rest at once: no re-send; the intent is done
        with what filled, one lot."""
        h = self.harness()
        self.one_buy(h, 0.005)
        h.venue.fill_first = D(1)
        h.tick(9, 15)
        h.tick(9, 16)
        for mm in (17, 18):
            self.assertNotIn("venue_cancel_resends", h.tick(9, mm))
        [order] = h.orders()
        self.assertEqual((order.status, order.filled_qty), ("canceled", D(1)))
        h.tick(9, 31)
        h.tick(9, 33)
        self.assertEqual(len(h.bodies()), 1)
        buy = self.buy(h)
        self.assertEqual((buy["status"], buy["why"]), ("done", "filled 1 shares at the open"))
        self.assertEqual(h.lots()[0].qty, D(1))
        h.tick(16, 3)
        self.assertEqual(self.said(h), [])


if __name__ == "__main__":
    unittest.main()
