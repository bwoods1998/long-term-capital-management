"""AN EXIT IS NEVER HELD ON THE PRACTICE ACCOUNT PAST THE ENTRY CUT-OFF (league/equity/live.py `_work_exit`,
`_sell_unproven`).

The stock paper proof's SELL stage gates every real equity sale (A10.1): the practice sale goes first in its window,
sent in the open window's first minute and normally witnessed in its second, and real exits wait for that pass. Found
in the rehearsal of the first real-money session (Oct 11, 2026): that wait had no end. A stage that could not pass (a
practice sale that rests, FILL activities the practice account does not list, a practice position off its baseline)
held every real lot for as long as it could not, the max-hold exit and the owner's flatten among them, while a failed
stage also stops every new buy. The wait now ends at the session's entry cut-off (09:45): from then on every exit goes
through the normal path whatever the stage says, and the owner is told once a session.

What must NOT change is held here too: inside the open window a real sale still waits for the stage; the min hold and
the gateway's kill switch still hold an exit; a failed stage still stops new real buys.

The book's harness and fakes are league/tests/test_equity_book.py's; the practice account of the last class is
league/tests/test_equity_paper.py's, under the REAL `StockPaperProof`. No price here is a market's."""

import datetime as dt
import unittest

from league.equity import live as L
from league.tests.test_equity_book import FRIDAY, MONDAY, TUESDAY, WEDNESDAY, BookTest, at

try:
    import numpy  # noqa: F401
    HAVE = True
except ImportError:  # pragma: no cover
    HAVE = False

WAITS = "SELL stage"
TOLD = "never held on the practice account"


class TheSellStagesWaitHasAnEnd(BookTest):
    def held(self, h, symbol="SPY", family="seed-overnight-spy", **kw):
        inst = h.instance(family)
        return inst, h.lot(inst, symbol, "0.5", "590", **kw)

    def test_a_real_sale_waits_through_the_open_window_then_goes(self):
        h = self.harness()
        inst, lot = self.held(h)
        sale = h.intent(inst, "sell", symbol="SPY", lid=lot.lid)
        h.proof.sell = False
        for mm in range(31, 45):
            h.tick(9, mm)
        self.assertEqual(h.venue.sent, [], "the practice sale has the open window's fifteen minutes to go first")
        self.assertIn(WAITS, h.get_intent(sale.iid).why)
        self.assertEqual(h.book._lot(lot.lid).status, "open")
        self.assertEqual(h.alerts, [], "nothing is said while the stage may still pass first")
        h.tick(9, 45)
        self.assertEqual([(b["side"], b["symbol"], b["type"]) for b in h.venue.sent], [("sell", "SPY", "limit")])
        h.tick(9, 46)
        closed = h.book._lot(lot.lid)
        self.assertEqual((closed.status, closed.exit_at, closed.exit_day, closed.reason),
                         ("closed", "open", MONDAY.isoformat(), "program"))
        self.assertEqual(h.get_intent(sale.iid).status, "done")
        [(level, text)] = h.alerts
        self.assertEqual(level, "error")
        self.assertIn(TOLD, text)
        self.assertIn("Owner step", text)
        self.assertEqual(h.state.get("eq_sell_unproven")["day"], MONDAY.isoformat())
        self.assertEqual(sum(1 for kind, payload in h.events if kind == "equity.alert" and TOLD in payload["what"]), 1)

    def test_a_stage_that_passes_inside_the_window_releases_the_sale_at_once_and_nothing_is_said(self):
        h = self.harness()
        inst, lot = self.held(h)
        h.intent(inst, "sell", symbol="SPY", lid=lot.lid)
        h.proof.sell = False
        h.tick(9, 31)
        self.assertEqual(h.venue.sent, [])
        h.proof.sell = True                                     # the practice sale witnessed in the second minute
        h.tick(9, 32)
        self.assertEqual([b["side"] for b in h.venue.sent], ["sell"])
        for mm in range(33, 47):
            h.tick(9, mm)
        self.assertEqual(h.alerts, [])
        self.assertIsNone(h.state.get("eq_sell_unproven"))

    def test_the_owner_is_told_once_a_session_however_many_exits_go(self):
        h = self.harness()
        a, spy = self.held(h, "SPY", "fam-a")
        b, qqq = self.held(h, "QQQ", "fam-b")
        c, iwm = self.held(h, "IWM", "fam-c")
        h.intent(a, "sell", symbol="SPY", lid=spy.lid)
        h.intent(b, "sell", symbol="QQQ", lid=qqq.lid)
        h.intent(c, "sell", symbol="IWM", lid=iwm.lid, exec_day=TUESDAY, decided=MONDAY)
        h.proof.sell = False
        h.tick(9, 44)
        self.assertEqual(h.venue.sent, [])
        h.tick(9, 45)
        self.assertEqual(sorted(b["symbol"] for b in h.venue.sent), ["QQQ", "SPY"])
        self.assertEqual(len([1 for _, text in h.alerts if TOLD in text]), 1)
        h.tick(9, 44, day=TUESDAY)
        self.assertEqual(len(h.venue.sent), 2, "the next session waits through its own open window again")
        h.tick(9, 45, day=TUESDAY)
        self.assertEqual(sorted(b["symbol"] for b in h.venue.sent), ["IWM", "QQQ", "SPY"])
        self.assertEqual(len([1 for _, text in h.alerts if TOLD in text]), 2, "once a session")

    def test_the_max_hold_exit_and_the_owners_flatten_go_too(self):
        h = self.harness()
        inst, lot = self.held(h)
        other, held = self.held(h, "QQQ", "fam-b")
        h.book._plan_exit(lot, exec_day=MONDAY.isoformat(), at="open", reason="max_hold",
                          why="held 3 sessions by the next open (its maximum 3)", decided_day=FRIDAY.isoformat())
        h.proof.sell = False
        h.tick(9, 44)
        self.assertEqual(h.venue.sent, [])
        h.tick(9, 45)
        self.assertEqual([(b["side"], b["symbol"]) for b in h.venue.sent], [("sell", "SPY")])
        self.assertEqual(h.book._lot(lot.lid).reason, "max_hold")
        # The rollback's first step in mid session (docs/operations.md): queued, and sent the same minute.
        h.clock.set(at(MONDAY, 11, 0))
        h.state.put(L.OWNER_FLATTEN, {"why": "a rollback", "by": "the owner", "at": h.clock()})
        h.tick(11, 0)
        self.assertEqual([(b["side"], b["symbol"]) for b in h.venue.sent], [("sell", "SPY"), ("sell", "QQQ")])
        self.assertEqual(h.book._lot(held.lid).reason, "flatten")

    def test_the_min_hold_and_the_kill_switch_still_hold_an_exit(self):
        h = self.harness()
        inst, bought_today = self.held(h, opened=MONDAY, entry_at="open")
        other, lot = self.held(h, "QQQ", "fam-b")
        h.book._plan_exit(bought_today, exec_day=MONDAY.isoformat(), at="open", reason="flatten", why="a rollback",
                          decided_day=MONDAY.isoformat())
        kept = h.intent(other, "sell", symbol="QQQ", lid=lot.lid)
        h.proof.sell = False
        h.kill = True
        h.tick(9, 45)
        h.tick(9, 46)
        self.assertEqual(h.venue.sent, [], "never in the session it was bought; never through the gateway's kill")
        self.assertIn("kill switch", h.get_intent(kept.iid).why)
        h.kill = False
        h.tick(9, 47)
        self.assertEqual([(b["side"], b["symbol"]) for b in h.venue.sent], [("sell", "QQQ")])
        self.assertEqual(h.book._lot(bought_today.lid).status, "open")

    def test_a_failed_stage_still_stops_new_buys_while_exits_go(self):
        h = self.harness()
        inst, lot = self.held(h)
        other = h.instance("fam-b")
        h.intent(inst, "sell", symbol="SPY", lid=lot.lid)
        buy = h.intent(other, "buy", symbol="QQQ", share="0.2", at_="close")
        h.proof.sell = False
        h.proof.failed = "the stock paper proof's SELL stage failed on 2026-10-09: the round trip ended without " \
                         "activity_witness"
        h.tick(9, 45)
        self.assertEqual([(b["side"], b["symbol"]) for b in h.venue.sent], [("sell", "SPY")])
        for mm in (55, 56, 57, 58, 59):
            h.tick(15, mm)
        h.tick(16, 0)
        self.assertEqual([(b["side"], b["symbol"]) for b in h.venue.sent], [("sell", "SPY")], "no real buy")
        self.assertEqual(h.get_intent(buy.iid).status, "missed")
        self.assertIn("new real equity buys stop", h.get_intent(buy.iid).why)

    def test_a_proof_that_cannot_be_read_holds_an_exit_no_longer_either(self):
        h = self.harness()
        inst, lot = self.held(h)
        sale = h.intent(inst, "sell", symbol="SPY", lid=lot.lid)

        def unreadable():
            raise RuntimeError("the state cannot be read")

        h.proof.sell_passed = unreadable
        h.tick(9, 44)
        self.assertEqual(h.venue.sent, [])
        self.assertIn("could not be read", h.get_intent(sale.iid).why)
        h.tick(9, 45)
        self.assertEqual([b["side"] for b in h.venue.sent], ["sell"])

    def test_a_close_exit_of_the_day_goes_in_the_close_window(self):
        h = self.harness()
        inst, lot = self.held(h)
        h.intent(inst, "sell", symbol="SPY", lid=lot.lid, at_="close")
        h.proof.sell = False
        h.tick(9, 45)
        h.tick(15, 54)
        self.assertEqual(h.venue.sent, [], "a close exit waits for the close, as before")
        h.tick(15, 55)
        self.assertEqual([b["side"] for b in h.venue.sent], ["sell"])
        self.assertEqual(h.book._lot(lot.lid).exit_at, "close")


@unittest.skipUnless(HAVE, "numpy not installed")
class TheRealProofThatCannotPass(BookTest):
    """The REAL `StockPaperProof` beside the book, on a practice account that lists no FILL activity: its SELL stage
    cannot pass. The lot bought on the BUY stage's day leaves on the SELL stage's day at the entry cut-off; the stage
    fails at its window's end with its own alarm, and new real buys stay stopped."""

    def test_the_lot_leaves_at_the_cut_off_and_the_failed_stage_stops_buys(self):
        from league.live.paper import StockPaperProof
        from league.tests.live_fakes import Market as PaperMarket
        from league.tests.test_equity_paper import PaperStocks

        h = self.harness()
        paper = PaperStocks(PaperMarket(h.clock))
        paper.activity_lag = True
        h.proof = StockPaperProof(h.state, paper, clock=h.clock,
                                  alert=lambda level, text: h.alerts.append((level, text)))
        h.book = h.new_book()
        inst = h.instance()
        h.intent(inst, "buy", symbol="SPY", share="0.5")
        h.tick(9, 31)
        self.assertEqual(h.venue.sent, [], "stage BUY first")
        self.assertEqual([b["side"] for b in paper.sent], ["buy"])
        h.tick(9, 32)
        self.assertTrue(h.proof.buy_passed())
        self.assertEqual([b["side"] for b in h.venue.sent], ["buy"])
        h.tick(9, 33)
        [lot] = h.lots()
        self.assertEqual((lot.status, lot.opened_day), ("open", MONDAY.isoformat()))

        sale = h.intent(inst, "sell", symbol="SPY", lid=lot.lid, exec_day=TUESDAY, decided=MONDAY)
        for mm in range(31, 45):
            h.tick(9, mm, day=TUESDAY)
        self.assertEqual([b["side"] for b in paper.sent], ["buy", "sell"], "the practice sale went first")
        self.assertEqual(h.proof.status()["status"], "sold")
        self.assertFalse(h.proof.sell_passed())
        self.assertEqual([b["side"] for b in h.venue.sent], ["buy"], "the real sale waits inside the open window")
        self.assertIn(WAITS, h.get_intent(sale.iid).why)
        h.tick(9, 45, day=TUESDAY)
        self.assertEqual([b["side"] for b in h.venue.sent], ["buy", "sell"])
        h.tick(9, 46, day=TUESDAY)
        self.assertEqual(h.book._lot(lot.lid).status, "closed")
        self.assertEqual(len([1 for _, text in h.alerts if TOLD in text]), 1)

        h.tick(15, 55, day=TUESDAY)
        self.assertIn("SELL stage failed", h.proof.sell_failed())
        self.assertEqual(len([1 for _, text in h.alerts if "SELL stage failed" in text]), 1)
        again = h.intent(inst, "buy", symbol="SPY", share="0.5", exec_day=WEDNESDAY, decided=TUESDAY)
        for mm in range(31, 47):
            h.tick(9, mm, day=WEDNESDAY)
        self.assertEqual([b["side"] for b in h.venue.sent], ["buy", "sell"], "no new real buy: the stage is failed")
        self.assertEqual(h.get_intent(again.iid).status, "missed")
        self.assertIn("new real equity buys stop", h.get_intent(again.iid).why)


if __name__ == "__main__":
    unittest.main()
