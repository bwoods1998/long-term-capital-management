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

    class LateVenue(Venue):
        """The real account as the venue answers it: a POST's answer carries NO fill (the fill lands after it). A stock
        limit order (the equity book's) rests until the test fills it (`fill_stock`); a market order fills at the next
        read of the account."""

        posting = False

        def submit(self, body, *, exit):
            self.posting = True
            try:
                return super().submit(body, exit=exit)
            finally:
                self.posting = False

        def _try_fill(self, order):
            if self.posting:
                return
            if order["legs"] or occ_parts(order["symbol"]) or order["type"] != "limit":
                return super()._try_fill(order)

        def fill_stock(self, symbol, share=D(1)):
            """`share` of what is left of the working stock orders on `symbol` fills at the quote."""
            quote = self.market.stocks([symbol])[symbol]["latestQuote"]
            for o in self.book:
                if o["symbol"] != symbol or o["legs"] or o["status"] not in WORKING:
                    continue
                buying = o["side"] == "buy"
                price, done = D(str(quote["ap"] if buying else quote["bp"])), D(o["filled_qty"])
                add = ((D(o["qty"]) - done) * D(share)).quantize(D("0.000000001"))
                if add <= 0:
                    continue
                old = D(str(o.get("filled_avg_price") or 0))
                o["filled_avg_price"] = str((old * done + price * add) / (done + add))
                o["filled_qty"] = str(done + add)
                o["status"] = "filled" if done + add >= D(o["qty"]) else "partially_filled"
                if o["status"] == "filled":
                    o["filled_at"] = iso(self.clock())
                self.held[symbol] = self.held.get(symbol, D(0)) + (add if buying else -add)

    class CountingPaper(PaperStocks):
        """The practice account, counting every read of its positions."""

        reads = 0

        def positions(self):
            self.reads += 1
            return super().positions()


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


# --------------------------------------------------------------------------------- the race (ops-2, amend-3, money-2)
@unittest.skipUnless(HAVE, "numpy not installed")
class TheRace(LiveCase):
    """The options path reads the account, reconciles, and only then the equity book's minute books its fills."""

    def setUp(self):
        super().setUp()
        rows = self.venue.activity_rows
        self.venue = LateVenue(self.market, equity="5481.65", last_equity="481.65")
        self.venue.activity_rows = rows

    def house(self):
        live = self.make([])
        stock_proof_passed(live.state)
        live.state.put("eq_decide", {"day": FRIDAY.isoformat(), "status": "done"})
        self.assertIsInstance(live.equity, L.EquityBook)
        return live

    def frozen_alerts(self):
        return [text for _, text in self.alerts if "real entries frozen" in text or "frozen by reconciliation" in text]

    def minute(self, hh, mm):
        """ONE pass at hh:mm, as the loop makes it: the options path, then the equity book's minute (`run_to` passes
        the minute it starts in a second time, and that second pass would book the fill before the next reading)."""
        self.clock.set(at(MONDAY, hh, mm))
        return self.live.minute()

    def test_a_sale_filled_over_two_minutes_never_freezes_the_options_book(self):
        live = self.house()
        book = live.equity
        inst = seat(book)
        lot = hold(book, self.venue, inst, "SPY", "0.5", "590")
        plan_sale(book, inst, lot)
        self.minute(9, 31)
        [sale] = [b for b in self.venue.sent if b.get("symbol") == "SPY"]
        self.assertEqual((sale["side"], sale["type"], sale["qty"]), ("sell", "limit", "0.5"))
        self.assertTrue(sale["client_order_id"].startswith("lq-"))
        self.assertEqual(self.venue.held["SPY"], D("0.5"), "the POST's answer carried no fill")
        self.venue.fill_stock("SPY", D("0.6"))                         # 0.3 fills between the minutes
        self.minute(9, 32)
        self.assertEqual(live.book.mismatch, [], "the equity order is working: the equity book judges the symbol")
        self.assertEqual(book._lot(lot.lid).qty, D("0.2"), "booked by the equity book's minute, after the options reads")
        self.venue.fill_stock("SPY")                                   # the rest, a minute later
        out = self.minute(9, 33)
        self.assertEqual(live.book.mismatch, [])
        self.assertEqual(live.book.frozen, "", "two fills in consecutive minutes froze real entries in both lanes")
        self.assertIsNone(out["blocked"])
        self.assertEqual(book._lot(lot.lid).status, "closed")
        for mm in (34, 35, 36):
            self.minute(9, mm)
        self.assertEqual((live.book.frozen, book.frozen), ("", ""))
        self.assertEqual(self.frozen_alerts(), [])
        self.assertEqual(self.notices, [], "the owner was paged for a reconciliation stop that was a race")

    def test_an_exit_and_then_an_entry_at_the_open_never_freeze_it_either(self):
        """The review's own morning: an overnight seed sells at the open while another program buys (entries wait for
        the exits), each filled after its POST and booked a minute later."""
        live = self.house()
        book = live.equity
        seller, buyer = seat(book), seat(book, "seed-reversal-index", symbols=("IWM",))
        lot = hold(book, self.venue, seller, "SPY", "0.5", "590")
        plan_sale(book, seller, lot)
        now = book.clock()
        book._save_intent(L.Intent(book._next("eq_intents", "iid"), buyer.id, buyer.family, buyer.version,
                                   FRIDAY.isoformat(), MONDAY.isoformat(), "open", "buy", "planned", symbol="IWM",
                                   share=D("0.5"), created_at=now, updated_at=now))
        self.minute(9, 31)
        self.venue.fill_stock("SPY")
        self.minute(9, 32)                                             # the sale is booked, the entry sent
        [entry] = [b for b in self.venue.sent if b.get("symbol") == "IWM"]
        self.assertEqual((entry["side"], entry["type"]), ("buy", "limit"))
        self.venue.fill_stock("IWM")
        out = self.minute(9, 33)
        self.assertGreater(self.venue.held["IWM"], 0)
        self.assertEqual((live.book.mismatch, live.book.frozen), ([], ""))
        self.assertIsNone(out["blocked"])
        self.assertEqual(H.expected_shares(book), {"IWM": self.venue.held["IWM"]}, "booked by the equity book's minute")
        self.assertEqual(self.frozen_alerts() + self.notices, [])

    def test_a_settled_symbol_is_judged_again_and_a_real_mismatch_still_freezes(self):
        live = self.house()
        book = live.equity
        inst = seat(book)
        lot = hold(book, self.venue, inst, "SPY", "0.5", "590")
        plan_sale(book, inst, lot)
        self.minute(9, 31)
        self.venue.fill_stock("SPY")
        self.minute(9, 32)
        self.assertEqual(book._lot(lot.lid).status, "closed")
        self.assertEqual(H.flux(book, live.state.rows, self.clock()), {"SPY"}, "it ended this minute")
        self.venue.held["SPY"] = D("0.1")                              # shares nothing explains, while in flux
        self.minute(9, 33)
        self.assertEqual(live.book.mismatch, [], "not judged within two minutes of the order's end")
        for mm in (34, 35, 36):
            self.minute(9, mm)
        self.assertEqual(H.flux(book, live.state.rows, self.clock()), set())
        self.assertIn("SPY: 0.1 shares held, 0 expected", live.book.frozen, "settled: judged, and frozen on two readings")
        self.assertIn("equity lots 0, assignment shares 0", live.book.frozen)

    def test_reconcile_skips_only_the_symbols_in_flux(self):
        dir_ = tempfile.TemporaryDirectory()
        self.addCleanup(dir_.cleanup)
        clock = Clock(at(MONDAY, 10, 0))
        state = LiveState(Path(dir_.name) / "live.sqlite", clock=clock)
        self.addCleanup(state.close)
        venue = Venue(Market(clock))
        book = RealBook(state, venue, M.Table.from_constitution(), clock=clock)

        def recon(**kw):
            return book.reconcile(venue.positions(), [], day=MONDAY, after_close=False, **kw)

        venue.held["SPY"], venue.held["QQQ"] = D("0.2"), D("1")
        owned = {"SPY": D("0.5"), "IWM": D("2")}
        self.assertEqual(len(recon(equity_shares=owned)), 3, "SPY short of its lots, QQQ unexplained, IWM not held")
        problems = recon(equity_shares=owned, equity_flux={"spy", "IWM"})
        self.assertEqual(len(problems), 1)
        self.assertIn("QQQ: 1 shares held, 0 expected", problems[0])
        self.assertEqual(recon(equity_shares=owned, equity_flux={"SPY", "IWM", "QQQ"}), [])

    def test_flux_is_a_working_order_or_one_that_changed_in_the_last_two_minutes(self):
        live = self.house()
        book = live.equity
        inst = seat(book)
        now = self.clock()

        def order(eid, symbol, status, updated):
            row = L.Order(eid, f"lq-{eid}", inst.id, inst.family, "buy", symbol, "etf", "open", D("1"), D("100"), 10,
                          status, now - 600, MONDAY.isoformat()).row()
            live.state.upsert("eq_orders", {**row, "updated_at": updated}, "eid")

        order(1, "SPY", "working", now - 900)                         # resting since long ago: still in flux
        order(2, "QQQ", "filled", now - 60)                           # ended a minute ago
        order(3, "IWM", "canceled", now - L.FLUX_S - 1)               # settled
        self.assertEqual(H.flux(book, live.state.rows, now), {"SPY", "QQQ"})
        self.assertEqual(live._equity_flux(now), {"SPY", "QQQ"})
        self.assertEqual(H.flux(None, live.state.rows, now), set(), "no book: nothing in flux")
        live.equity = H.Unreadable("the equity book cannot be read")
        with self.assertRaises(RuntimeError):
            H.flux(live.equity, live.state.rows, now)
        self.assertEqual(live._equity_flux(now), set(), "unreadable: every symbol is judged (fail closed)")


# ------------------------------------------------------------------------------------------ the minute (money-11, ops-15)
@unittest.skipUnless(HAVE, "numpy not installed")
class TheMinute(LiveCase):
    def test_an_options_pass_that_raises_still_gives_the_equity_book_its_minute(self):
        live = self.make([])
        live.equity = book = FakeBook()
        with mock.patch.object(live, "_options_minute", side_effect=RuntimeError("an options bug")):
            with self.assertRaisesRegex(RuntimeError, "an options bug"):
                live.minute()
        self.assertEqual([now for now, _ in book.ticks], [self.clock()], "its fills are booked and its exits sent")
        self.assertIsNone(book.ticks[0][1]["positions"], "nothing read this pass: the book reads what it needs")
        self.clock.set(self.clock() + 60)
        out = live.minute()                                            # the next pass is whole again
        self.assertEqual((out["state"], len(book.ticks)), ("session", 2))

    def test_the_equity_minute_is_skipped_only_when_the_account_reads_failed_late_in_the_minute(self):
        live = self.make([])
        live.equity = book = FakeBook()
        self.run_to(9, 31)
        self.assertEqual(len(book.ticks), 1)

        def hang(seconds):
            def positions():
                self.clock.set(self.clock() + seconds)                # the venue's timeout
                raise TimeoutError("timed out")
            return positions

        self.clock.set(at(MONDAY, 9, 32))
        with mock.patch.object(self.venue, "positions", side_effect=hang(50)):
            out = live.minute()
        self.assertIn("positions: TimeoutError", " ".join(out["venue_errors"]))
        self.assertIn("reads of the real account failed", out["equity"]["skipped"])
        self.assertEqual(len(book.ticks), 1, "the next options pass must start on time")
        self.clock.set(at(MONDAY, 9, 33))
        with mock.patch.object(self.venue, "positions", side_effect=hang(50)):
            live.minute()
        self.assertEqual(sum(1 for _, text in self.alerts if "equity book's minute is skipped" in text), 1,
                         "said once a run of skipped minutes")
        self.clock.set(at(MONDAY, 9, 34))
        with mock.patch.object(self.venue, "positions", side_effect=hang(1)):
            out = live.minute()                                        # it failed at once: the minute is not spent
        self.assertEqual((len(book.ticks), out["equity"]), (2, {"ticked": at(MONDAY, 9, 34)}))
        self.clock.set(at(MONDAY, 9, 35))
        real = self.venue.positions

        def slow():
            self.clock.set(self.clock() + 50)
            return real()

        with mock.patch.object(self.venue, "positions", side_effect=slow):
            out = live.minute()                                        # slow, but it answered: never skipped
        self.assertEqual(len(book.ticks), 3)
        self.assertNotIn("venue_errors", out)


@unittest.skipUnless(HAVE, "numpy not installed")
class TheIdleProof(unittest.TestCase):
    """ops-15: the book steps the stock proof every minute, around the clock, until both stages pass; a minute with
    nothing for it to do reads nothing of the practice account."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.clock = Clock(at(MONDAY, 9, 0))
        self.market = Market(self.clock)
        self.paper = CountingPaper(self.market)
        self.state = LiveState(Path(self.dir.name) / "live.sqlite", clock=self.clock)
        self.alerts = []
        self.proof = StockPaperProof(self.state, self.paper, clock=self.clock,
                                     alert=lambda level, text: self.alerts.append((level, text)))

    def tearDown(self):
        self.state.close()
        self.dir.cleanup()

    def step(self, day, hh, mm, ss=3):
        self.clock.set(at(day, hh, mm, ss))
        return self.proof.step(self.clock(), market=self.market, window=S.moments(day))

    def test_waiting_outside_its_window_reads_nothing(self):
        sunday = MONDAY - dt.timedelta(days=1)
        self.clock.set(at(sunday, 22, 0))
        row = self.proof.step(self.clock(), market=self.market, window=S.moments(sunday))
        self.assertEqual((row["status"], self.state.get("paper_proof_stock")["status"]), ("waiting", "waiting"))
        for hh, mm in ((4, 0), (9, 25), (9, 30)):
            self.step(MONDAY, hh, mm)
        self.assertEqual(self.paper.reads, 0, "the night, the pre-open, the minute before the first send")
        self.step(MONDAY, 9, 31)
        self.assertEqual((self.paper.reads, len(self.paper.sent)), (1, 1), "the BUY window: it reads, and buys")

    def test_holding_its_lot_reads_nothing_until_the_sell_window(self):
        self.step(MONDAY, 9, 31)
        self.step(MONDAY, 9, 32)
        self.assertTrue(self.proof.buy_passed())
        reads = self.paper.reads
        for hh, mm in ((9, 33), (12, 0), (15, 20), (15, 56), (20, 0)):
            self.step(MONDAY, hh, mm)
        self.step(TUESDAY, 9, 30)
        self.assertEqual(self.paper.reads, reads, "the buy's own session and the night: nothing to do, nothing read")
        self.step(TUESDAY, 9, 31)
        self.assertEqual([b["side"] for b in self.paper.sent], ["buy", "sell"])
        self.step(TUESDAY, 9, 32)
        self.assertTrue(self.proof.passed(), self.proof.status())

    def test_a_missed_buy_window_and_a_failed_sell_stage_go_idle_too(self):
        self.paper.stock_fill = "none"
        self.step(MONDAY, 9, 31)
        self.step(MONDAY, 9, 46)                                       # the entry cut-off: cancelled, tried again tomorrow
        self.step(MONDAY, 9, 47)
        reads = self.paper.reads
        for hh, mm in ((9, 48), (13, 0), (16, 30)):
            self.step(MONDAY, hh, mm)
        self.assertEqual(self.paper.reads, reads, "tried today: idle until the next open window")
        self.paper.stock_fill = "natural"
        self.step(TUESDAY, 9, 31)
        self.step(TUESDAY, 9, 32)
        self.assertTrue(self.proof.buy_passed())
        wednesday = TUESDAY + dt.timedelta(days=1)
        self.paper.stock_fill = "none"
        self.step(wednesday, 9, 31)
        for hh, mm in ((12, 0), (15, 55), (15, 56), (15, 57)):
            self.step(wednesday, hh, mm)
        self.assertTrue(self.proof.sell_failed())
        self.assertEqual(sum(1 for _, text in self.alerts if "SELL stage failed" in text), 1)
        reads = self.paper.reads
        for hh, mm in ((15, 58), (16, 30), (23, 0)):
            self.step(wednesday, hh, mm)
        self.assertEqual(self.paper.reads, reads, "failed for the day and flat of orders: idle until the next window")


# --------------------------------------------------------------------------------- the stock proof's start (amend-11)
@unittest.skipUnless(HAVE, "numpy not installed")
class TheFirstOpenWindow(LiveCase):
    """A10.1: stage BUY goes in the FIRST open window after the deploy. It waited for both of the options route's paper
    proofs to read passed, so a House whose options proofs had not passed lost the window (and a day)."""

    def setUp(self):
        super().setUp()
        self.paper = PaperStocks(self.market)

    def test_stage_buy_does_not_wait_for_the_options_routes_proofs(self):
        live = self.make([], config={"require_paper_proof": True})
        self.assertIsInstance(live.equity, L.EquityBook)
        self.assertFalse(live.proof.passed() or live.proof_single.passed())
        self.run_to(9, 31)
        [buy] = [b for b in self.paper.sent if b.get("symbol") == "SPY" and not b.get("legs")]
        self.assertEqual((buy["side"], buy["type"]), ("buy", "limit"))
        self.assertTrue(buy["client_order_id"].startswith("lq-pp-"))
        self.run_to(9, 32)
        self.assertTrue(live.equity.stock_proof.buy_passed(), live.equity.stock_proof.status())
        self.assertFalse(live.proof.passed(), "the options route's own proof has not even begun (09:35)")
        self.assertEqual(self.venue.sent, [], "nothing real went for it")
        self.run_to(9, 45)
        self.assertTrue(live.proof.passed(), "and the options proof ran beside it, on its own contracts")


@unittest.skipUnless(HAVE, "numpy not installed")
class TheOptionsExitsStand(LiveCase):
    """Nothing here delays an options exit: a Probe family's vertical still opens and closes with the equity book
    ticking, in flux, beside it."""

    def test_a_vertical_round_trip_beside_a_working_equity_order(self):
        live = self.make([family("vert", VERTICAL, band="probe")])
        stock_proof_passed(live.state)
        live.state.put("eq_decide", {"day": FRIDAY.isoformat(), "status": "done"})
        book = live.equity
        inst = seat(book)
        lot = hold(book, self.venue, inst, "SPY", "0.5", "590")
        plan_sale(book, inst, lot)
        self.run_to(9, 31)
        self.assertEqual(len(live.book.positions), 1, "the options open went")
        self.run_to(9, 40)
        self.assertEqual([p.status for p in live.book.positions.values()], [], "and its close, three minutes on")
        self.assertEqual(live.book.frozen, "")


if __name__ == "__main__":
    unittest.main()
