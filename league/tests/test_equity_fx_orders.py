"""The equity book's ORDER PATH after the E1 review (`league/equity/live.py`; findings money-4, ops-5, money-9, amend-5,
money-7, ops-7, ops-10, ops-12, money-6), on the book tests' harness (league/tests/test_equity_book.py: an in-memory
venue with Alpaca's documented stock-order shapes and invented prices; money's and core's functions stubbed at their
interface).

- THE OWNER'S COMMANDS: `python3 -m league.live --flatten-equity "<why>"` and `--clear-equity-freeze "<why>"` write a
  key-value; the book's minute acts on it once, in the House's own thread, and records who and why.
- EXITS, THEN ENTRIES (A2, in both windows): the close window's entries wait a minute for its exits, and an entry sized
  to nothing is not final while an exit may still fill (the venue here fills AFTER the POST answers, as a venue does).
- ONE INTENT, ONE LOT: a fill the re-price cancel's own lookup finds never leaves the replacement to open a second lot.
- THE HOUSE'S MINUTE CLOCK: the book's sends go later than the minute's `now` by however long the options minute
  took; a re-price is due on the minute clock, nothing is POSTed at or after a cut-off by the wall clock, and an order
  still resting on a later day than its own is cancelled before the next open.
- THE GATEWAY'S UNREAD READINGS (424 positions, 424 orders, 503 equity, 409 stock_close): sent again next minute.

No price here is a market's."""

import contextlib
import datetime as dt
import io
import tempfile
import unittest
from decimal import Decimal as D
from pathlib import Path
from unittest import mock

from league.equity import live as L
from league.equity import schedule as S
from league.live import __main__ as owner
from league.live.venue import Submitted
from league.tests import test_equity_book as T

SUNDAY = dt.date(2026, 10, 11)
MONDAY, TUESDAY, FRIDAY = T.MONDAY, T.TUESDAY, T.FRIDAY


class LateVenue(T.Venue):
    """The POST answers `new`, unfilled; the fill shows at the venue's next reading (a venue answers before it fills)."""

    def submit(self, body, *, exit):
        mode, self.fill = self.fill, "none"
        try:
            return super().submit(body, exit=exit)
        finally:
            self.fill = mode


class UnreadVenue(T.Venue):
    """`submit_mode` one of `UNREAD`: the gateway could not make a reading, so nothing was sent (its documented
    answers: 424 `positions` and `orders`, 503 `equity`, 409 `stock_close`); `stock_order`: a cap's 403, a verdict."""

    UNREAD = {"positions": 424, "orders": 424, "equity": 503, "stock_close": 409}

    def submit(self, body, *, exit):
        status = {**self.UNREAD, "stock_order": 403}.get(self.submit_mode)
        if status is None:
            return super().submit(body, exit=exit)
        self.sent.append(dict(body))
        text = "Cannot read the real account: nothing was sent. Send it again."
        return Submitted(False, {"error": text, "cap": self.submit_mode}, f"HTTP {status} {text}", status=status)


def with_venue(h: T.Harness, kind: type, *, cash: str = "2000") -> T.Harness:
    """The harness on another venue (the book rebuilt on it)."""
    h.venue = kind(h.market, h.clock, cash=cash)
    h.book = h.new_book()
    return h


def lagged(h: T.Harness, seconds: float) -> T.Harness:
    """The book's WALL clock `seconds` past the minute's `now` at every read: the equity minute runs after the options
    minute (league/live/step.py `minute`), so its sends go that much later than the `now` it is handed."""
    h.book.clock = lambda: h.clock() + seconds
    return h


def command(root: Path, *args: str) -> dict:
    """The owner's command against the state at `root` (its report is printed to the owner's terminal: swallowed)."""
    with contextlib.redirect_stdout(io.StringIO()):
        return owner.main(["--root", str(root), *args])


class TheOwnersCommands(T.BookTest):
    """money-4, ops-5, money-9: the rollback's step 3 and the corporate-action freeze each had no way to be run."""

    def test_the_key_names_are_the_books(self):
        self.assertEqual((owner.EQUITY_FLATTEN, owner.EQUITY_CLEAR_FREEZE), (L.OWNER_FLATTEN, L.OWNER_CLEAR_FREEZE))

    def test_flatten_is_run_by_the_books_own_minute(self):
        h = self.harness()
        inst = h.instance()
        old, young = h.lot(inst, "SPY", "0.5", "590"), h.lot(inst, "QQQ", "0.5", "490", opened=MONDAY)
        h.clock.set(T.at(MONDAY, 12, 0))
        shown = command(self.root, "--flatten-equity", "the  rollback of E1")
        ask = shown["equity"]["pending_owner_actions"][L.OWNER_FLATTEN]
        self.assertEqual((ask["why"], ask["by"]), ("the rollback of E1", "the owner (python -m league.live)"))
        self.assertEqual(h.venue.sent, [], "the command itself sends nothing: it writes a key-value")
        self.assertEqual(h.intents(kind="house_exit"), [])
        out = h.tick(12, 1)
        self.assertEqual(out["flatten"], 2)
        self.assertIsNone(h.state.get(L.OWNER_FLATTEN), "done once, its key deleted")
        self.assertEqual(h.book._lot(old.lid).reason, "flatten")           # sold this minute, through the normal path
        self.assertEqual(h.book._lot(young.lid).status, "open")            # min hold: tomorrow's open
        self.assertTrue(all(b["type"] == "limit" for b in h.venue.sent))    # never a market order
        [(_, said)] = [e for e in h.events if e[0] == "equity.flatten"]
        self.assertEqual(said["lots"], 2)
        self.assertIn("the owner (python -m league.live): the rollback of E1", said["why"])
        self.assertTrue(any("flatten" in text and "2 lots" in text for _, text in h.alerts))
        self.assertNotIn("flatten", h.tick(12, 2))
        self.assertEqual(len(h.intents(kind="house_exit")), 2, "each lot queued once")
        self.assertEqual(command(self.root, "--status")["equity"]["pending_owner_actions"], {})
        h.tick(16, 0)
        h.tick(9, 31, day=TUESDAY)
        self.assertEqual(h.book._lot(young.lid).reason, "flatten")

    def test_flatten_on_a_closed_day_queues_the_next_open(self):
        h = self.harness()
        inst = h.instance()
        lot = h.lot(inst, "SPY", "0.5", "590")
        h.clock.set(T.at(SUNDAY, 15, 0))
        command(self.root, "--flatten-equity", "before Monday")
        self.assertEqual(h.tick(15, 1, day=SUNDAY)["flatten"], 1)
        [exit_] = h.intents(kind="house_exit")
        self.assertEqual((exit_.exec_day, exit_.at, exit_.tag, exit_.lid), ("2026-10-12", "open", "flatten", lot.lid))
        self.assertEqual(h.venue.sent, [])
        h.tick(9, 31)
        self.assertEqual(h.book._lot(lot.lid).status, "closed")

    def test_the_corporate_action_freeze_is_cleared_and_recorded(self):
        h = self.harness()
        h.lot(h.instance("fam-a"), "SPY", "1", "590")
        buy = h.intent(h.instance("fam-b"), "buy", symbol="QQQ", share="0.2")
        h.venue.held["SPY"] = D("0.4")                                      # and a mismatch of the book's own
        h.state.put("eq_freeze", {"why": "DIVFEE on SPY: a type the book does not book", "at": 1.0, "activity": "a-1"})
        h.tick(9, 31)
        h.tick(9, 32)
        self.assertEqual(h.venue.sent, [])
        self.assertIn("DIVFEE on SPY", h.get_intent(buy.iid).why)
        command(self.root, "--clear-equity-freeze", "booked by hand: a fee of the ADR")
        out = h.tick(9, 33)
        self.assertTrue(out["freeze_cleared"])
        self.assertIsNone(h.state.get("eq_freeze"))
        self.assertIsNone(h.state.get(L.OWNER_CLEAR_FREEZE))
        self.assertIn("SPY: the account holds 0.4", h.book.frozen, "the reconciliation's own freeze is not the owner's")
        self.assertNotIn("DIVFEE", h.book.frozen)
        said = [p for kind, p in h.events if kind == "equity.freeze" and p.get("cleared") == "eq_freeze"]
        self.assertEqual(len(said), 1)
        self.assertIn("the owner (python -m league.live): booked by hand: a fee of the ADR", said[0]["by"])
        self.assertIn("DIVFEE on SPY", said[0]["why"])
        self.assertEqual((said[0]["frozen"], said[0]["activity"]), (True, "a-1"))
        self.assertEqual(h.venue.sent, [])
        h.venue.held["SPY"] = D("1")
        h.tick(9, 34)
        h.tick(9, 35)                                                       # two clean readings lift the other one
        self.assertEqual([b["side"] for b in h.venue.sent], ["buy"], "the opens go again once nothing freezes them")

    def test_clearing_lifts_the_block_in_the_same_minute(self):
        h = self.harness()
        h.intent(h.instance(), "buy", symbol="QQQ", share="0.2")
        h.state.put("eq_freeze", {"why": "a rename of SPY", "at": 1.0})
        h.tick(9, 31)
        command(self.root, "--clear-equity-freeze", "reviewed")
        h.tick(9, 32)
        self.assertEqual([b["side"] for b in h.venue.sent], ["buy"])

    def test_a_clear_with_nothing_frozen_only_spends_its_key(self):
        h = self.harness()
        command(self.root, "--clear-equity-freeze", "nothing to clear")
        self.assertIs(h.tick(9, 31)["freeze_cleared"], False)
        self.assertIsNone(h.state.get(L.OWNER_CLEAR_FREEZE))
        self.assertEqual([e for e in h.events if e[0] == "equity.freeze"], [])

    def test_a_reason_is_required(self):
        h = self.harness()
        for flag in ("--flatten-equity", "--clear-equity-freeze"):
            with self.subTest(flag=flag), self.assertRaises(SystemExit):
                command(self.root, flag, "   ")
        self.assertIsNone(h.state.get(L.OWNER_FLATTEN))
        self.assertIsNone(h.state.get(L.OWNER_CLEAR_FREEZE))

    def test_a_flatten_that_fails_is_tried_again_and_never_stops_the_clear(self):
        h = self.harness()
        inst = h.instance()
        lot = h.lot(inst, "SPY", "0.5", "590")
        h.state.put("eq_freeze", {"why": "a rename of SPY", "at": 1.0})
        h.state.put(L.OWNER_FLATTEN, {"why": "the rollback", "at": 1.0, "by": "the owner"})
        h.state.put(L.OWNER_CLEAR_FREEZE, {"why": "reviewed", "at": 1.0, "by": "the owner"})
        with mock.patch.object(L.EquityBook, "flatten", side_effect=RuntimeError("boom")):
            out = h.tick(9, 31)
        self.assertTrue(any(L.OWNER_FLATTEN in e for e in out["errors"]))
        self.assertIsNotNone(h.state.get(L.OWNER_FLATTEN), "kept: tried again next minute")
        self.assertIsNone(h.state.get("eq_freeze"))
        self.assertEqual(h.tick(9, 32)["flatten"], 1)
        self.assertEqual(h.book._lot(lot.lid).reason, "flatten")


class ExitsThenEntries(T.BookTest):
    """amend-5, money-7: the Gym fills a session's close exits before it sizes its close entries (A2); the book sized
    the entries in the minute it sent the exits, the lot being sold still in the sleeve, and a zero size was final."""

    def rotation(self, **kw) -> tuple[T.Harness, L.Lot, L.Lot, L.Intent, L.Intent]:
        """A program whose Probe sleeve (0.25 x $2,000) is full of SPY and IWM decides: sell IWM at the close, buy QQQ
        at the same close."""
        h = with_venue(self.harness(**kw), LateVenue)
        a = h.instance("rotator")
        spy, iwm = h.lot(a, "SPY", "0.416", "600"), h.lot(a, "IWM", "1.136", "220")
        sale = h.intent(a, "sell", symbol="IWM", lid=iwm.lid, at_="close")
        buy = h.intent(a, "buy", symbol="QQQ", share="0.5", at_="close")
        return h, spy, iwm, sale, buy

    def test_a_close_rotation_buys_on_the_cash_after_its_sale(self):
        h, spy, iwm, sale, buy = self.rotation()
        h.tick(15, 55)
        self.assertEqual([(b["side"], b["symbol"]) for b in h.venue.sent], [("sell", "IWM")])
        self.assertEqual(h.get_intent(buy.iid).status, "planned", "the entry waits for the window's exits")
        self.assertEqual(T.SIZED, [], "and is not sized while the lot being sold still fills its sleeve")
        h.tick(15, 56)
        self.assertEqual(h.book._lot(iwm.lid).status, "closed")
        self.assertEqual([(b["side"], b["symbol"]) for b in h.venue.sent], [("sell", "IWM"), ("buy", "QQQ")])
        sized = T.SIZED[-1]
        self.assertEqual(sized.sleeve_free_cash, D("500") - D("0.416") * D("600"))      # the sleeve less SPY alone
        self.assertEqual(D(h.venue.sent[1]["qty"]), (D("250") / D("500.61")).quantize(D("1e-6"), rounding=T.ROUND_DOWN))
        h.tick(15, 57)
        self.assertEqual(h.get_intent(buy.iid).status, "done")
        self.assertEqual(sorted(lot.symbol for lot in h.lots(open_only=True)), ["QQQ", "SPY"], "as the Gym's session")

    def test_the_whole_sleeve_rotates(self):
        h = with_venue(self.harness(cash="1500"), LateVenue)
        a = h.instance("rot")
        lot = h.lot(a, "QQQ", "1.0", "500")                                 # the whole 0.25 x E sleeve
        h.intent(a, "sell", symbol="QQQ", lid=lot.lid, at_="close")
        buy = h.intent(a, "buy", symbol="SPY", share="0.5", at_="close")
        for mm in (55, 56, 57):
            h.tick(15, mm)
        self.assertEqual(h.get_intent(buy.iid).status, "done")
        self.assertEqual([(x.symbol, x.entry_at) for x in h.lots(open_only=True)], [("SPY", "close")])

    def test_an_entry_sized_to_nothing_waits_while_its_sale_is_working(self):
        h, spy, iwm, sale, buy = self.rotation()
        h.venue.fill = "none"                                               # the sale rests through its first limit
        h.tick(15, 55)
        h.tick(15, 56)                                                      # the wait is over; the sale is re-priced
        waiting = h.get_intent(buy.iid)
        self.assertEqual(waiting.status, "planned", "not final while its own program's exit may still fill")
        self.assertIn("sized again when the exits still working fill (1 of its own program, 1 in all)", waiting.why)
        self.assertNotIn("buy", [b["side"] for b in h.venue.sent])
        h.venue.fill = "cross"
        h.tick(15, 57)                                                      # the sale filled: sized on its cash
        self.assertEqual(h.book._lot(iwm.lid).status, "closed")
        self.assertEqual([(b["side"], b["symbol"]) for b in h.venue.sent][-1], ("buy", "QQQ"))
        h.tick(15, 58)
        self.assertEqual(h.get_intent(buy.iid).status, "done")
        self.assertEqual(sorted(lot.symbol for lot in h.lots(open_only=True)), ["QQQ", "SPY"])

    def test_a_sale_that_never_fills_leaves_the_entry_missed_at_the_cut_off(self):
        h, spy, iwm, sale, buy = self.rotation()
        h.venue.fill = "none"
        for hh, mm in ((15, 55), (15, 56), (15, 57), (15, 58), (15, 59), (16, 0)):
            h.tick(hh, mm)
        missed = h.get_intent(buy.iid)
        self.assertEqual(missed.status, "missed")
        self.assertIn("the entry cut-off passed", missed.why)
        self.assertIn("sizing (", missed.why, "the reason it could not be sized is kept")
        self.assertEqual(h.get_intent(sale.iid).status, "missed")
        self.assertEqual([(c.exec_day, c.at, c.lid) for c in h.intents(kind="house_exit")],
                         [("2026-10-13", "open", iwm.lid)])
        self.assertNotIn("buy", [b["side"] for b in h.venue.sent])

    def test_the_close_entries_wait_one_minute_whatever_the_exits(self):
        """As the open window's `exit_wait_s`: after `CLOSE_EXIT_WAIT_S` the entries go on the cash there is, and an
        unfilled sale adds nothing to it."""
        h = with_venue(self.harness(cash="300"), LateVenue, cash="300")
        a, b = h.instance("fam-a"), h.instance("fam-b")
        lot = h.lot(a, "SPY", "0.5", "590")
        h.intent(a, "sell", symbol="SPY", lid=lot.lid, at_="close")
        buy = h.intent(b, "buy", symbol="QQQ", share="1", at_="close")
        h.venue.fill = "none"
        h.tick(15, 55)
        self.assertEqual([x["side"] for x in h.venue.sent], ["sell"])
        self.assertEqual(h.get_intent(buy.iid).status, "planned")
        h.tick(15, 56)                                                      # 15:56:00 has passed
        self.assertIn("buy", [x["side"] for x in h.venue.sent])
        self.assertEqual(T.SIZED[-1].available_cash, D("250"))             # nothing from the unfilled sale
        self.assertEqual(L.CLOSE_EXIT_WAIT_S, 60.0)

    def test_with_no_exit_in_the_window_the_entries_go_at_once(self):
        h = with_venue(self.harness(), LateVenue)
        h.intent(h.instance(), "buy", symbol="SPY", share="0.5", at_="close")
        h.tick(15, 55)
        self.assertEqual([b["side"] for b in h.venue.sent], ["buy"], "E1's seeds: nothing to wait for")

    def test_a_lot_bought_today_holds_nobody(self):
        """A close exit of a lot bought this session cannot go (the min hold): the entries do not wait for it."""
        h = with_venue(self.harness(), LateVenue)
        a = h.instance()
        young = h.lot(a, "IWM", "0.5", "220", opened=MONDAY, entry_at="open")
        h.intent(a, "sell", symbol="IWM", lid=young.lid, at_="close")
        h.intent(a, "buy", symbol="QQQ", share="0.2", at_="close")
        h.tick(15, 55)
        self.assertEqual([(b["side"], b["symbol"]) for b in h.venue.sent], [("buy", "QQQ")])

    def test_a_zero_size_is_final_when_no_exit_can_fund_it(self):
        h = self.harness()
        a = h.instance()
        h.lot(a, "SPY", "0.83", "600")                                      # the sleeve is full and nothing is sold
        buy = h.intent(a, "buy", symbol="QQQ", share="0.5", at_="close")
        h.tick(15, 55)
        refused = h.get_intent(buy.iid)
        self.assertEqual(refused.status, "refused")
        self.assertTrue(refused.why.startswith("sizing ("))

    def test_todays_close_exit_funds_no_open_entry(self):
        """Before the close window a close exit is not due: an open entry it would fund is refused at once, as the Gym
        refuses it (open entries come before close exits)."""
        h = self.harness()
        a = h.instance()
        lot = h.lot(a, "SPY", "0.83", "600")
        h.intent(a, "sell", symbol="SPY", lid=lot.lid, at_="close")
        buy = h.intent(a, "buy", symbol="QQQ", share="0.5")
        h.tick(9, 31)
        self.assertEqual(h.get_intent(buy.iid).status, "refused")

    def test_the_open_window_too(self):
        """The same root at the open: after `exit_wait_s` an entry its own exit will fund is sized to nothing; it waits
        for the exit instead of ending refused with twelve minutes of its window left."""
        h = self.harness()
        a = h.instance()
        lot = h.lot(a, "SPY", "0.83", "600")
        h.intent(a, "sell", symbol="SPY", lid=lot.lid)
        buy = h.intent(a, "buy", symbol="QQQ", share="0.5")
        h.venue.fill = "none"
        for mm in (31, 32, 33):
            h.tick(9, mm)
        self.assertEqual(h.get_intent(buy.iid).status, "planned")
        self.assertIn("sized again when the exits still working fill", h.get_intent(buy.iid).why)
        h.venue.fill = "cross"
        h.tick(9, 34)
        self.assertEqual(h.book._lot(lot.lid).status, "closed")
        self.assertEqual([(x.symbol, x.entry_at) for x in h.lots(open_only=True)], [("QQQ", "open")])


class ExitsThenEntriesWithTheRealSizing(unittest.TestCase):
    """The same rotation with nothing stubbed but the venue: money's `size_entry` and `available_cash`, core's fees and
    the shared budget's room as they are (the book tests stub them at their interface)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.h = with_venue(T.Harness(Path(self.tmp.name)), LateVenue)
        self.addCleanup(self.h.state.close)

    def rotate(self) -> tuple[L.Lot, L.Intent]:
        h = self.h
        a = h.instance("rotator")
        h.lot(a, "SPY", "0.416", "600")
        iwm = h.lot(a, "IWM", "1.136", "220")
        h.intent(a, "sell", symbol="IWM", lid=iwm.lid, at_="close")
        return iwm, h.intent(a, "buy", symbol="QQQ", share="0.5", at_="close")

    def test_the_rotation_ends_as_the_gyms_session(self):
        h = self.h
        iwm, buy = self.rotate()
        for mm in (55, 56, 57):
            h.tick(15, mm)
        self.assertEqual(h.book._lot(iwm.lid).status, "closed")
        self.assertEqual(h.get_intent(buy.iid).status, "done", h.get_intent(buy.iid).why)
        held = {lot.symbol: lot for lot in h.lots(open_only=True)}
        self.assertEqual(sorted(held), ["QQQ", "SPY"])
        self.assertLessEqual(held["QQQ"].entry_notional, D("250"))          # half the $500 sleeve, as it asked
        self.assertGreater(held["QQQ"].entry_notional, D("249"))

    def test_a_resting_sale_leaves_the_entry_waiting_not_refused(self):
        h = self.h
        iwm, buy = self.rotate()
        h.venue.fill = "none"
        h.tick(15, 55)
        h.tick(15, 56)
        waiting = h.get_intent(buy.iid)
        self.assertEqual(waiting.status, "planned")
        self.assertIn("the sleeve has $0.48 of free cash", waiting.why)     # the review's own figure: the sleeve is full
        self.assertIn("sized again when the exits still working fill", waiting.why)
        h.venue.fill = "cross"
        h.tick(15, 57)
        h.tick(15, 58)
        self.assertEqual(h.get_intent(buy.iid).status, "done")


class OneIntentOneLot(T.BookTest):
    """ops-7: the re-price cancel's own lookup found a fill and the terminal state together; the lot's id was saved on
    a fresh row, and the entry went on from its stale one (no lot): the replacement's fill opened a second lot."""

    def partly_filled_in_the_cancel(self, h: T.Harness, *, then=None) -> None:
        """The venue: 40% of the resting order fills in the moment before its cancel lands."""
        real = h.venue.cancel

        def cancel(venue_id):
            for o in h.venue.book:
                if o["id"] == venue_id and o["status"] == "new":
                    h.venue._fill(o, (D(o["qty"]) * D("0.4")).quantize(D("1e-9")))
                    o["status"], o["canceled_at"] = "canceled", T.iso(h.clock())
            h.venue.cancel = real
            if then is not None:
                then()
            return True, ""

        h.venue.cancel = cancel

    def assert_one_lot(self, h: T.Harness, it: L.Intent) -> None:
        orders, lots = h.orders(), h.lots()
        self.assertEqual(len(lots), 1, [(x.lid, str(x.qty)) for x in lots])
        self.assertEqual(lots[0].qty, sum((o.filled_qty for o in orders), D(0)))
        self.assertEqual({o.lid for o in orders if o.filled_qty > 0}, {lots[0].lid})
        self.assertEqual((h.get_intent(it.iid).status, h.get_intent(it.iid).lid), ("done", lots[0].lid))
        self.assertEqual(h.venue.held["SPY"], lots[0].qty)

    def test_a_fill_found_by_the_cancels_lookup_joins_the_replacements(self):
        h = self.harness()
        it = h.intent(h.instance(), "buy", symbol="SPY", share="0.5")
        h.venue.fill = "none"
        h.tick(9, 31)
        self.partly_filled_in_the_cancel(h)
        h.tick(9, 32)                                           # re-price: cancel, lookup (fill and canceled), resend
        self.assertEqual([o.status for o in h.orders()], ["canceled", "working"])
        self.assertEqual(h.orders()[1].lid, h.lots()[0].lid, "the replacement is sent for the lot the fill opened")
        h.venue.fill = "cross"
        h.tick(9, 33)
        h.tick(9, 34)
        self.assert_one_lot(h, it)

    def test_a_minute_without_a_quote_between_them_changes_nothing(self):
        """The same fill, then a minute in which the entry only records why it waits: the row it saves is the fresh
        one, with its lot."""
        h = self.harness()
        it = h.intent(h.instance(), "buy", symbol="SPY", share="0.5")
        h.venue.fill = "none"
        h.tick(9, 31)
        good = h.market.quotes["SPY"]
        self.partly_filled_in_the_cancel(h, then=lambda: h.market.quotes.update(SPY=(D("0"), D("0"))))
        h.tick(9, 32)
        waiting = h.get_intent(it.iid)
        self.assertIn("no usable quote", waiting.why)
        self.assertEqual(waiting.lid, h.lots()[0].lid, "the wait is saved on the row as the fill left it")
        h.market.quotes["SPY"] = good
        h.venue.fill = "cross"
        h.tick(9, 33)
        h.tick(9, 34)
        self.assert_one_lot(h, it)

    def test_a_buy_fill_joins_its_intents_lot_whatever_a_row_lost(self):
        h = self.harness()
        it = h.intent(h.instance(), "buy", symbol="SPY", share="0.5")
        h.venue.fill = "none"
        h.tick(9, 31)
        self.partly_filled_in_the_cancel(h, then=lambda: h.market.quotes.update(SPY=(D("0"), D("0"))))
        h.tick(9, 32)
        row = h.get_intent(it.iid)
        row.lid = None                                          # a row saved from before the fill
        h.book._save_intent(row)
        h.market.quotes["SPY"] = (D("599.90"), D("600.10"))
        h.venue.fill = "cross"
        h.tick(9, 33)
        h.tick(9, 34)
        self.assert_one_lot(h, it)


class TheMinuteClock(T.BookTest):
    """ops-10, ops-12: the minute's `now` is its start; the book's sends go after the options minute, up to most of a
    minute later by the wall clock."""

    def test_the_open_window_re_prices_every_minute(self):
        for lag in (2.0, 40.0):
            with self.subTest(lag=lag):
                tmp = tempfile.TemporaryDirectory()
                self.addCleanup(tmp.cleanup)
                h = lagged(T.Harness(Path(tmp.name)), lag)
                self.addCleanup(h.state.close)
                h.intent(h.instance(), "buy", symbol="SPY", share="0.5")
                h.venue.fill = "none"
                sent = []
                for mm in range(31, 36):
                    h.tick(9, mm)
                    sent.append(len(h.orders()))
                self.assertEqual(sent, [1, 2, 3, 4, 5], "one a minute, not one every second minute")
                orders = h.orders()
                self.assertEqual([o.collar_bp for o in orders], [10, 20, 30, 40, 50])
                self.assertEqual([o.answer["tick"] for o in orders], [T.at(MONDAY, 9, mm) for mm in range(31, 36)])
                self.assertEqual([o.placed_at for o in orders], [T.at(MONDAY, 9, mm) + lag for mm in range(31, 36)],
                                 "placed_at stays the wall clock at the POST")

    def test_the_close_window_re_prices_every_minute_and_never_after_its_cut_off(self):
        h = lagged(self.harness(), 40.0)                                    # the options minute took forty seconds
        it = h.intent(h.instance(), "buy", symbol="SPY", share="0.5", at_="close")
        h.venue.fill = "none"
        until = S.moments(MONDAY, h.book._offsets()).close_until
        for mm in (55, 56, 57, 58, 59):
            h.tick(15, mm)
        orders = h.orders()
        self.assertEqual([o.collar_bp for o in orders], [10, 20, 30, 40], "15:55 to 15:58, each minute")
        self.assertTrue(all(o.placed_at < until for o in orders), "nothing POSTed at or after 15:59:30 by the wall clock")
        self.assertEqual(orders[-1].status, "working", "and not cancelled for a re-price that could not follow")
        self.assertEqual(len(h.venue.cancels), 3)
        h.tick(16, 0)
        self.assertEqual([o.status for o in h.orders()], ["canceled"] * 4)
        self.assertEqual(h.get_intent(it.iid).status, "missed")

    def test_no_entry_is_posted_after_its_cut_off_by_the_wall_clock(self):
        for hh, mm, at_, lag in ((15, 59, "close", 30.0), (9, 44, "open", 58.0)):
            with self.subTest(window=at_):
                tmp = tempfile.TemporaryDirectory()
                self.addCleanup(tmp.cleanup)
                h = lagged(T.Harness(Path(tmp.name)), lag)
                self.addCleanup(h.state.close)
                it = h.intent(h.instance(), "buy", symbol="SPY", share="0.5", at_=at_)
                h.tick(hh, mm)                              # `now` is inside the window; the wall clock is past it
                self.assertEqual(h.venue.sent, [])
                self.assertEqual(h.orders(), [], "nothing written either")
                self.assertIn("cut-off passed on the wall clock", h.get_intent(it.iid).why)
                h.tick(hh, mm + 1) if mm < 59 else h.tick(16, 0)
                self.assertEqual(h.get_intent(it.iid).status, "missed")
                self.assertEqual(h.venue.sent, [])

    def test_no_exit_is_posted_after_the_close_window_by_the_wall_clock(self):
        h = lagged(self.harness(), 40.0)
        inst = h.instance()
        lot = h.lot(inst, "SPY", "0.5", "590")
        it = h.intent(inst, "sell", symbol="SPY", lid=lot.lid, at_="close")
        h.tick(15, 59)                                                      # 15:59:43 by the wall clock
        self.assertEqual(h.venue.sent, [])
        self.assertEqual(h.book._lot(lot.lid).status, "open", "the lot is not marked closing for an order never sent")
        h.tick(16, 0)
        self.assertEqual(h.get_intent(it.iid).status, "missed")
        self.assertEqual([(c.exec_day, c.at) for c in h.intents(kind="house_exit")], [("2026-10-13", "open")])
        h.book.clock = h.clock
        h.tick(9, 31, day=TUESDAY)
        self.assertEqual(h.book._lot(lot.lid).status, "closed")

    def test_an_order_resting_past_its_session_is_cancelled_before_the_next_open(self):
        """The rest of ops-12's scenario: an order that reached the venue after its close rests for the next session,
        and the House was down at its cut-off's own cancel. It never fills as a lot of the session it missed."""
        h = self.harness()
        a, b = h.instance("fam-a"), h.instance("fam-b")
        lot = h.lot(a, "SPY", "0.5", "590")
        sale = h.intent(a, "sell", symbol="SPY", lid=lot.lid, at_="close")
        buy = h.intent(b, "buy", symbol="QQQ", share="0.2", at_="close")
        h.venue.fill = "none"
        h.tick(15, 58)                                                      # both rest; the House then stops
        self.assertEqual([o.status for o in h.orders()], ["working", "working"])
        h.book = h.new_book()                                               # back on Tuesday, before the open
        h.tick(8, 0, day=TUESDAY)                                           # (the venue fills nothing before its open)
        self.assertEqual([o.status for o in h.orders()], ["canceled", "canceled"])
        self.assertEqual(len(h.venue.cancels), 2)
        self.assertEqual(len([text for _, text in h.alerts if "still working at the venue" in text]), 2)
        h.venue.fill = "cross"
        h.tick(9, 31, day=TUESDAY)
        self.assertEqual(h.get_intent(buy.iid).status, "missed", "the buy is not chased in another session")
        self.assertEqual([x.symbol for x in h.lots(open_only=True)], [], "and never became a lot of Monday's close")
        sold = h.book._lot(lot.lid)
        self.assertEqual((sold.status, sold.exit_day, sold.exit_at), ("closed", "2026-10-13", "open"),
                         "the sale went again as Tuesday's own order")
        self.assertEqual(h.get_intent(sale.iid).status, "done")

    def test_inside_the_window_by_the_wall_clock_the_send_goes(self):
        h = lagged(self.harness(), 20.0)                                    # 15:59:23: seven seconds to spare
        h.intent(h.instance(), "buy", symbol="SPY", share="0.5", at_="close")
        h.tick(15, 59)
        self.assertEqual(len(h.venue.sent), 1)

    def test_an_order_without_the_stamp_is_aged_from_its_post(self):
        h = self.harness()
        h.intent(h.instance(), "buy", symbol="SPY", share="0.5")
        h.venue.fill = "none"
        h.tick(9, 31)
        order = h.orders()[0]
        order.answer.pop("tick")
        h.book._save_order(order)
        h.tick(9, 32)
        self.assertEqual(len(h.orders()), 2)


class TheGatewaysUnreadReadings(T.BookTest):
    """money-6: the gateway's "nothing was sent, send it again" answers were booked as final refusals: one ended an
    entry for good, three in a session carried an exit to the next one."""

    def test_the_caps_are_the_gateways(self):
        self.assertEqual(set(L.RETRY_CAPS), {"positions", "orders", "equity", "stock_close"})
        self.assertEqual(set(L.RETRY_CAPS), set(UnreadVenue.UNREAD))

    def test_an_exit_is_sent_again_and_never_carried_for_them(self):
        h = with_venue(self.harness(), UnreadVenue)
        inst = h.instance()
        lot = h.lot(inst, "SPY", "0.5", "590")
        it = h.intent(inst, "sell", symbol="SPY", lid=lot.lid)
        h.venue.submit_mode = "positions"                                   # the positions endpoint fails for 3 minutes
        for mm in (31, 32, 33):
            h.tick(9, mm)
        self.assertEqual([(o.status, o.answer.get("cap"), o.answer.get("retry")) for o in h.orders()],
                         [("refused", "positions", True)] * 3)
        h.venue.submit_mode = "ok"
        h.tick(9, 34)
        self.assertEqual(h.intents(kind="house_exit"), [], "not carried to the next session")
        self.assertEqual(h.book._lot(lot.lid).status, "closed", "sold the same morning")
        sold = h.orders()[-1]
        self.assertEqual((sold.status, sold.collar_bp), ("filled", 10), "an order never sent widened no collar")
        self.assertEqual(sold.limit_px, L.limit_for("sell", D("599.90"), 10))
        self.assertEqual(L.orders_today(h.state.rows, "2026-10-12"), 1)
        told = [text for _, text in h.alerts if "could not check the exit" in text]
        self.assertEqual(len(told), 1, "the owner is told once")
        self.assertIn("positions", told[0])
        h.tick(9, 35)
        self.assertEqual(h.get_intent(it.iid).status, "done")

    def test_an_exit_they_stop_all_day_is_carried_by_its_windows_end_alone(self):
        h = with_venue(self.harness(), UnreadVenue)
        inst = h.instance()
        lot = h.lot(inst, "SPY", "0.5", "590")
        it = h.intent(inst, "sell", symbol="SPY", lid=lot.lid)
        h.venue.submit_mode = "stock_close"
        for hh, mm in ((9, 31), (9, 32), (9, 33), (9, 34), (12, 0), (15, 55), (15, 59)):
            h.tick(hh, mm)
        self.assertEqual(h.get_intent(it.iid).status, "sent", "still trying")
        self.assertEqual(len(h.venue.sent), 7)
        self.assertEqual(len([text for _, text in h.alerts if "could not check the exit" in text]), 1)
        h.tick(16, 0)
        self.assertEqual(h.get_intent(it.iid).status, "missed")
        self.assertIn("the session's windows ended", h.get_intent(it.iid).why)
        self.assertEqual([(c.exec_day, c.at, c.lid) for c in h.intents(kind="house_exit")],
                         [("2026-10-13", "open", lot.lid)])

    def test_an_entry_is_sent_again_until_its_cut_off(self):
        for cap in UnreadVenue.UNREAD:
            with self.subTest(cap=cap):
                tmp = tempfile.TemporaryDirectory()
                self.addCleanup(tmp.cleanup)
                h = with_venue(T.Harness(Path(tmp.name)), UnreadVenue)
                self.addCleanup(h.state.close)
                it = h.intent(h.instance(), "buy", symbol="SPY", share="0.5", at_="close")
                h.venue.submit_mode = cap
                h.tick(15, 55)                                              # one unread reading at 15:55:03
                self.assertEqual((h.orders()[0].status, h.get_intent(it.iid).status), ("refused", "sent"))
                h.venue.submit_mode = "ok"
                h.tick(15, 56)
                second = h.orders()[1]
                self.assertEqual((second.status, second.collar_bp, second.replaces), ("filled", 10, h.orders()[0].eid))
                self.assertEqual(second.qty, h.orders()[0].qty)
                h.tick(15, 57)
                self.assertEqual(h.get_intent(it.iid).status, "done")
                self.assertEqual(len(h.lots()), 1)

    def test_an_entry_they_stop_to_its_cut_off_is_missed(self):
        h = with_venue(self.harness(), UnreadVenue)
        it = h.intent(h.instance(), "buy", symbol="SPY", share="0.5", at_="close")
        h.venue.submit_mode = "equity"
        for hh, mm in ((15, 55), (15, 56), (15, 57), (15, 58), (15, 59), (16, 0)):
            h.tick(hh, mm)
        self.assertEqual(h.get_intent(it.iid).status, "missed")
        self.assertEqual(len(h.venue.sent), 5)

    def test_the_houses_own_rate_refusal_widens_no_collar_either(self):
        h = self.harness()
        it = h.intent(h.instance(), "buy", symbol="SPY", share="0.5")
        h.venue.submit_mode = "ratelimited"
        h.tick(9, 31)
        h.tick(9, 32)
        h.venue.submit_mode = "ok"
        h.tick(9, 33)
        self.assertEqual([(o.status, o.collar_bp) for o in h.orders()], [("refused", 10), ("refused", 10), ("filled", 10)])
        h.tick(9, 34)
        self.assertEqual(h.get_intent(it.iid).status, "done")

    def test_a_caps_verdict_is_still_final(self):
        """A 403 the gateway's caps gave is a verdict on the order: an entry ends refused, an exit is carried after
        three (unchanged)."""
        h = with_venue(self.harness(), UnreadVenue)
        a, b = h.instance("fam-a"), h.instance("fam-b")
        lot = h.lot(a, "SPY", "0.5", "590")
        sale = h.intent(a, "sell", symbol="SPY", lid=lot.lid)
        buy = h.intent(b, "buy", symbol="QQQ", share="0.2")
        h.venue.submit_mode = "stock_order"
        for mm in (31, 32, 33, 34):
            h.tick(9, mm)
        self.assertEqual(h.get_intent(buy.iid).status, "refused")
        self.assertEqual(h.get_intent(sale.iid).status, "missed")
        self.assertIn("refused 3 times", h.get_intent(sale.iid).why)
        self.assertEqual([c.exec_day for c in h.intents(kind="house_exit")], ["2026-10-13"])
        self.assertTrue(any("carried to the next session" in text for _, text in h.alerts))


if __name__ == "__main__":
    unittest.main()
