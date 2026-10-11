"""The E1 review's fixes in league/live (the hooks in the options book):

- THE COVER (amend-1, money-1): a short share position is covered by EXACTLY the account's short, which is all the
  gateway admits on a symbol held short (`live_fakes.Venue.stock_refusal` holds its rule in every test); a refused
  share order is an alarm; the lot an assignment swallowed is closed in the equity book once the cover has filled.
- THE RACE (ops-2, amend-3, money-2): the options book's reconciliation leaves a symbol the equity book has in flux
  to the equity book's own, so a fill booked a minute later never freezes both lanes (a venue whose fills land AFTER
  the POST answers, `LateVenue`, and the real `EquityBook` under `OptionsLive.minute`).
- A LONG EXCESS on a symbol the equity book holds (ops-9, amend-10): only the part an assignment explains is sold.
- THE MINUTE (money-11, ops-15): an options pass that raises still gives the equity book its minute; a pass whose
  account reads failed late in the minute skips it; the stock proof reads nothing of the practice account when it has
  nothing to do.
- THE INVESTED CAP (money-10): an option open counts what the equity lane holds and is buying (A1).
- THE STOCK PROOF'S START (amend-11): stage BUY goes in the first open window, whatever the options route's proofs say.

No price here is a market's."""

import datetime as dt
import tempfile
import unittest
from decimal import Decimal as D
from pathlib import Path
from unittest import mock

try:
    import numpy  # noqa: F401
    HAVE = True
except ImportError:  # pragma: no cover
    HAVE = False

if HAVE:
    from league.equity import config
    from league.equity import live as L
    from league.equity import schedule as S
    from league.live import equity_hook as H
    from league.live import money as M
    from league.live.paper import STOCK_BUY_KEY, STOCK_BUY_WITNESSES, STOCK_SELL_KEY, STOCK_WITNESSES, StockPaperProof
    from league.live.real import RealBook
    from league.live.state import LiveState
    from league.live.venue import occ_parts
    from league.tests.live_fakes import MONDAY, VERTICAL, Clock, Market, Venue, at, family, iso
    from league.tests.test_equity_book import CODE, family_row
    from league.tests.test_equity_hooks import FakeBook
    from league.tests.test_equity_paper import PaperStocks
    from league.tests.test_live_money import fwd
    from league.tests.test_live_step import LiveCase

    FRIDAY = MONDAY - dt.timedelta(days=3)
    TUESDAY = MONDAY + dt.timedelta(days=1)
    WORKING = ("new", "accepted", "partially_filled")


def stock_proof_passed(state) -> None:
    """Both stages of the stock paper proof taken as passed (league/tests/test_equity_paper.py proves them)."""
    for key, witnesses in ((STOCK_BUY_KEY, STOCK_BUY_WITNESSES), (STOCK_SELL_KEY, STOCK_WITNESSES)):
        state.put(key, {"schema": 1, "status": "passed", **{k: True for k in witnesses}})


def seat(book, name="seed-overnight-spy", *, symbols=("SPY",)):
    """A Probe program seated in the real equity book (as its daily step leaves one)."""
    inst = L.Instance(L.instance_key(name, 1), name, 1, "beta", "r1", CODE, {}, "probe", True, 20, created_at=book.clock())
    book._save_instance(inst)
    book.families.rows.setdefault(name, family_row(name, symbols=symbols))
    return inst


def hold(book, venue, inst, symbol="SPY", qty="0.5", px="590"):
    """A lot the program bought at Friday's close, held on the account."""
    qty, px = D(qty), D(px)
    lot = L.Lot(book._next("eq_lots", "lid"), inst.id, inst.family, inst.version, inst.lane, symbol,
                config.UNIVERSE[symbol], qty, qty, px, qty * px, "close", opened_at=at(FRIDAY, 15, 56),
                opened_day=FRIDAY.isoformat(), cash=-(qty * px), probe=True)
    book._save_lot(lot)
    venue.held[symbol] = venue.held.get(symbol, D(0)) + qty
    return lot


def plan_sale(book, inst, lot, day=None):
    """The program's own sale of the lot at Monday's open (Friday's decision)."""
    now = book.clock()
    intent = L.Intent(book._next("eq_intents", "iid"), inst.id, inst.family, inst.version, FRIDAY.isoformat(),
                      (day or MONDAY).isoformat(), "open", "sell", "planned", symbol=lot.symbol, lid=lot.lid,
                      created_at=now, updated_at=now)
    book._save_intent(intent)
    return intent


# ----------------------------------------------------------------------------------------- the cover (amend-1, money-1)
@unittest.skipUnless(HAVE, "numpy not installed")
class TheCover(LiveCase):
    """A8.2 as the gateway allows it: the cover is the account's short and never more."""

    def start(self, owned=None, **kw):
        live = self.make([])
        live.equity = FakeBook(owned, **kw)
        self.run_to(9, 31)
        return live

    def stock(self, symbol="SPY"):
        return [b for b in self.venue.sent if b.get("symbol") == symbol]

    def reading(self, live):
        """The next reading of the account's shares (`ACTIVITIES_EVERY` later)."""
        self.clock.set(self.clock() + 300)
        live._close_shares()

    def refusals(self):
        return [text for level, text in self.alerts if level == "error" and "REFUSED" in text]

    def test_the_fake_venue_holds_the_gateways_rule(self):
        self.venue.held["SPY"] = D("-99.6")
        self.assertIn("100 needed, 99.6 short held", self.venue.stock_refusal({"symbol": "SPY", "qty": "100", "side": "buy",
                                                                               "type": "market"}))
        self.assertIsNone(self.venue.stock_refusal({"symbol": "SPY", "qty": "99.6", "side": "buy", "type": "market"}))
        self.venue.held["SPY"] = D("2")
        self.assertIn("3 needed, 2 long held", self.venue.stock_refusal({"symbol": "SPY", "qty": "3", "side": "sell"}))
        self.assertIsNone(self.venue.stock_refusal({"symbol": "SPY", "qty": "2", "side": "sell", "type": "market"}))
        self.assertIn("limit order", self.venue.stock_refusal({"symbol": "QQQ", "qty": "1", "side": "buy", "type": "market"}))
        self.assertIsNone(self.venue.stock_refusal({"symbol": "QQQ", "qty": "1", "side": "buy", "type": "limit"}))
        self.assertIsNone(self.paper.stock_refusal({"symbol": "SPY", "qty": "9", "side": "sell"}), "the practice account")

    def test_an_assignment_netted_against_a_fractional_lot_is_covered_and_the_account_ends_flat(self):
        """The blocker's scenario: a lot of 0.4 SPY, 100 shares delivered, the account shows 99.6 short. A buy of 100
        (the lot's 0.4 with the short) is refused by the gateway on every pass and the short stays."""
        live = self.start({"SPY": "0.4"})
        live._book_shares("OPASN", "SPY261016C00600000", 1)
        self.venue.held["SPY"] = D("-99.6")
        live._close_shares()
        self.assertEqual([(b["side"], b["type"], b["qty"]) for b in self.stock()], [("buy", "market", "99")],
                         "whole shares first: the order the House sent before E1")
        self.assertEqual(self.venue.held["SPY"], D("-0.6"))
        self.reading(live)
        self.assertEqual([b["qty"] for b in self.stock()], ["99", "0.6"], "the fraction at the next reading")
        self.assertEqual(self.venue.held["SPY"], D("0"), "the account is flat: nothing short, nothing bought beyond it")
        self.reading(live)
        self.assertEqual(len(self.stock()), 2)
        self.assertEqual(self.refusals(), [], "the gateway admitted both")
        self.assertEqual(live.equity.taken, [("SPY", D("0.4"), D("600.0"))], "the lot went with the assignment")
        self.assertEqual(live.state.get("shares"), {}, "the ledger is back at zero: 99 + 0.6 covered, 0.4 the lot's")
        self.assertEqual(live.state.get("shares_orders"), {})
        self.assertFalse(live._stock_held)

    def test_a_whole_short_is_one_order_and_a_fraction_alone_goes_as_it_is(self):
        live = self.start()
        self.venue.held["SPY"] = D("-100")
        self.venue.held["QQQ"] = D("-0.25")
        live._close_shares()
        self.assertEqual([b["qty"] for b in self.stock()], ["100"])
        self.assertEqual([b["qty"] for b in self.stock("QQQ")], ["0.25"])
        self.assertEqual((self.venue.held["SPY"], self.venue.held["QQQ"]), (D("0"), D("0")))

    def test_a_refused_share_order_is_an_alarm_and_the_owner_is_told_once(self):
        live = self.start()
        self.venue.held["SPY"] = D("-5")
        self.venue.submit_mode = "reject"
        live._close_shares()
        [first] = self.refusals()
        self.assertIn("SPY: the cover of a short share position (buy 5 at market) was REFUSED", first)
        self.assertIn("refused 1 time(s)", first)
        self.assertEqual([n["stop"] for n in self.notices], ["assignment"], "a short the House cannot cover: the owner")
        self.reading(live)
        self.reading(live)
        self.assertEqual(len(self.stock()), 3, "sent again at each reading")
        self.assertEqual(len(self.refusals()), 1, "not an alarm a reading")
        self.clock.set(self.clock() + 3600)
        live._close_shares()
        self.assertEqual(len(self.refusals()), 2, "said again after an hour while it is still refused")
        self.assertIn("refused 4 time(s)", self.refusals()[-1])
        self.assertEqual(len(self.notices), 1)
        self.assertEqual(live.state.get("shares_orders"), {}, "a refused order is not remembered")
        self.venue.submit_mode = "ok"
        self.reading(live)
        self.assertEqual(self.venue.held["SPY"], D("0"))
        self.assertEqual(live.state.get("shares_refused"), {}, "it went: cleared")

    def test_a_refused_sale_is_an_alarm_too_and_a_gone_position_clears_it(self):
        live = self.start()
        self.venue.held["QQQ"] = D("3")
        live._close_shares()
        self.venue.submit_mode = "gateway"
        self.reading(live)
        [refused] = self.refusals()
        self.assertIn("QQQ: the sale of shares no program owns (sell 3 at market) was REFUSED", refused)
        self.assertEqual(self.notices, [], "only a cover's refusal is the owner's page")
        del self.venue.held["QQQ"]
        self.reading(live)
        self.assertEqual(live.state.get("shares_refused"), {})

    def test_the_lot_is_closed_only_once_the_cover_has_filled_and_the_book_is_asked_again_when_it_cannot_say(self):
        live = self.start({"SPY": "2"})
        live._book_shares("OPASN", "SPY261016C00600000", 1)
        self.venue.held["SPY"] = D("-98")
        self.venue.submit_mode = "reject"
        live._close_shares()
        self.reading(live)
        self.assertEqual(live.equity.taken, [], "no cover has filled: nothing proves the lot is gone")
        self.assertEqual(live.equity.owned, {"SPY": D("2")})
        self.venue.submit_mode = "ok"
        self.reading(live)
        self.assertEqual(self.venue.held["SPY"], D("0"))
        with mock.patch.object(FakeBook, "shares_taken", side_effect=RuntimeError("the book's rows are locked")):
            self.reading(live)
            self.reading(live)
        self.assertEqual(sum(1 for _, text in self.alerts if "could not close them" in text), 1, "alerted once")
        self.assertEqual(len(live.state.get("shares_orders")), 1, "the filled cover is kept until the book has closed it")
        self.assertEqual(live.state.get("shares"), {"SPY": "-2"})
        self.reading(live)
        self.assertEqual(live.equity.taken, [("SPY", D("2"), D("600.0"))])
        self.assertEqual(live.state.get("shares"), {})
        self.assertEqual(live.state.get("shares_orders"), {})
        self.assertEqual(sum(1 for _, text in self.alerts if "the lots are closed in the equity book" in text), 1)

    def test_an_unreadable_book_still_covers_to_flat_and_closes_no_lot(self):
        live = self.start({"SPY": "1"})
        live.equity.fail = "the book's rows are locked"
        self.venue.held["SPY"] = D("-3.5")
        live._close_shares()
        self.reading(live)
        self.assertEqual([b["qty"] for b in self.stock()], ["3", "0.5"])
        self.assertEqual(self.venue.held["SPY"], D("0"))
        self.reading(live)
        self.assertEqual(live.equity.taken, [], "what the book owned could not be told")

    def test_the_real_books_lot_is_closed_as_forced_at_the_covers_price_and_both_reconciliations_are_clean(self):
        live = self.make([])
        stock_proof_passed(live.state)
        live.state.put("eq_decide", {"day": FRIDAY.isoformat(), "status": "done"})
        book = live.equity
        self.assertIsInstance(book, L.EquityBook, "the House's own equity book (the constitution's equity block)")
        self.run_to(9, 31)
        inst = seat(book)
        lot = hold(book, self.venue, inst, "SPY", "0.4", "590")
        sale = plan_sale(book, inst, lot, TUESDAY)
        live._book_shares("OPASN", "SPY261016C00600000", 1)          # a short call assigned: 100 shares delivered
        self.venue.held["SPY"] -= 100
        live._close_shares()
        self.reading(live)
        self.reading(live)
        self.assertEqual([(b["side"], b["qty"]) for b in self.venue.sent if b.get("symbol") == "SPY"],
                         [("buy", "99"), ("buy", "0.6")])
        self.assertEqual(self.venue.held["SPY"], D("0"))
        closed = book._lot(lot.lid)
        self.assertEqual((closed.status, closed.reason, closed.qty, closed.exit_px, closed.exit_day),
                         ("closed", "forced", D(0), D("600.0"), MONDAY.isoformat()))
        self.assertEqual(closed.cash, D("0.4") * (D("600.0") - D("590")), "the cover's price less its entry, no fee")
        self.assertEqual(closed.info["taken"][0]["priced"], "cover")
        self.assertEqual(H.expected_shares(book), {})
        self.assertEqual(live.state.get("shares"), {})
        positions = self.venue.positions()
        self.assertEqual(live.book.reconcile(positions, [], day=MONDAY, after_close=False, shares={},
                                             equity_shares=live._owned_shares()), [])
        self.assertEqual(book.reconcile(positions), [])
        self.assertEqual(sum(1 for lvl, text in self.alerts if lvl == "error" and "took 0.4 shares" in text), 1)
        self.assertEqual([p["reason"] for p, _ in self.ledger.of("equity.close")], ["forced"])
        # The program's own sale of the lot finds it closed at Tuesday's open: nothing is sent for it.
        self.clock.set(at(TUESDAY, 9, 31))
        live.minute()
        self.assertEqual(book._intent(sale.iid).status, "done")
        self.assertEqual([b for b in self.venue.sent if b.get("side") == "sell"], [])

    def test_shares_taken_closes_oldest_first_and_prices_at_the_mark_without_a_cover_price(self):
        live = self.make([])
        book = live.equity
        a, b = seat(book, "seed-overnight-spy"), seat(book, "seed-reversal-index")
        first = hold(book, self.venue, a, "SPY", "0.5", "590")
        second = hold(book, self.venue, b, "SPY", "0.3", "595")
        self.assertEqual(book.shares_taken("SPY", D("0.6"), None, why="a test"), D("0.6"))
        one, two = book._lot(first.lid), book._lot(second.lid)
        self.assertEqual((one.status, one.reason, one.exit_px), ("closed", "forced", D("590")))
        self.assertEqual(one.info["taken"][0]["priced"], "mark")
        self.assertEqual((two.status, two.qty), ("closing", D("0.2")), "the rest of the newer lot is still the program's")
        self.assertEqual(H.expected_shares(book), {"SPY": D("0.2")})
        self.assertEqual(book.shares_taken("SPY", D("5"), D("601"), why="a test"), D("0.2"), "never more than it holds")
        self.assertEqual(book.shares_taken("QQQ", D("1"), D("500"), why="a test"), D("0"))
        self.assertEqual(H.shares_taken(None, "SPY", D("1"), None, why="no book"), D("0"))
        with self.assertRaises(RuntimeError):
            H.shares_taken(H.Unreadable("the equity book cannot be read"), "SPY", D("1"), None, why="unreadable")


# ------------------------------------------------------------------------ a long excess on a held symbol (ops-9, amend-10)
@unittest.skipUnless(HAVE, "numpy not installed")
class TheLongExcess(LiveCase):
    """A8.2's "lots the equity book owns are never touched": shares beyond the lots on a symbol the book HOLDS are sold
    only for the part an assignment or an exercise explains (the share-event ledger)."""

    def start(self, owned=None):
        live = self.make([])
        live.equity = FakeBook(owned)
        self.run_to(9, 31)
        return live

    def stock(self, symbol="SPY"):
        return [b for b in self.venue.sent if b.get("symbol") == symbol]

    def readings(self, live, n=3):
        for _ in range(n):
            self.clock.set(self.clock() + 300)
            live._close_shares()

    def test_a_splits_new_shares_are_never_sold(self):
        """A held ETF splits 2:1 and the account shows it before the book has booked the split: the extra shares are
        the lots' own. They were sold at market on the second reading."""
        live = self.start({"SPY": "2.5"})
        self.venue.held["SPY"] = D("5")
        self.readings(live, 4)
        self.assertEqual(self.stock(), [], "never an order")
        self.assertEqual(self.venue.held["SPY"], D("5"))
        self.assertEqual({k: D(v) for k, v in live.state.get("unexplained_shares").items()}, {"SPY": D("2.5")})
        told = [text for level, text in self.alerts if level == "error" and "no assignment or exercise explains" in text]
        self.assertEqual(len(told), 1, "alarmed once while the quantity stands")
        self.assertTrue(live._stock_held, "unexplained shares keep an assignment's latch")
        problems = live.book.reconcile(self.venue.positions(), [], day=MONDAY, after_close=False,
                                       equity_shares=live._owned_shares())
        self.assertIn("SPY: 5 shares held, 2.5 expected", " ".join(problems), "reconciliation's freeze has it")
        live.equity.owned["SPY"] = D("5")                              # the split booked
        self.readings(live, 1)
        self.assertEqual(live.state.get("unexplained_shares"), {})
        self.assertFalse(live._stock_held)

    def test_an_exercises_shares_on_a_held_symbol_are_sold_and_what_they_do_not_explain_is_not(self):
        live = self.start({"SPY": "0.25"})
        live._book_shares("OPEXC", "SPY261016C00600000", 1)          # 100 shares received
        self.venue.held["SPY"] = D("100.75")                           # ... and half a share nothing explains
        self.readings(live, 2)
        self.assertEqual([(b["side"], D(b["qty"])) for b in self.stock()], [("sell", D("100"))])
        self.assertEqual(self.venue.held["SPY"], D("0.75"))
        self.readings(live, 3)
        self.assertEqual(len(self.stock()), 1, "the unexplained half share is never sold")
        self.assertEqual({k: D(v) for k, v in live.state.get("unexplained_shares").items()}, {"SPY": D("0.5")})

    def test_shares_of_a_symbol_the_book_holds_no_lot_of_are_sold_as_before(self):
        live = self.start({"SPY": "1"})
        self.venue.held["SPY"] = D("1")
        self.venue.held["QQQ"] = D("3")                                # a spin-off's shares, a stray: no lot of it
        self.readings(live, 2)
        self.assertEqual([(b["side"], b["qty"]) for b in self.stock("QQQ")], [("sell", "3")])
        self.assertEqual(self.stock(), [])
        self.assertIsNone(live.state.get("unexplained_shares") or None)


if __name__ == "__main__":
    unittest.main()
