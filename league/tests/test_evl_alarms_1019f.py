"""Release 1019f (the audit of the live House, lens "stalls": ALARMS THAT DID NOT EXIST; the captain's A80 (2)): the event
lane's new stall causes (league/ops/evl_health.py) and the stall job's notice pace (league/ops/stall.py):
(a) `evl_entries`: an auction of the last 24 h whose planned real buys under 90% filled, or one never sent, from the book's
    own rows in live.sqlite: the venue's cancels at once (A80), the re-sends after one, the never-sent by reason and the
    constraint that bound; the daily report carries the same per auction, and the break-even edge of Done's compute
    clause once a Probe buy exists;
(b) `evl_backfill`: a weekday of the daily-index backfill's reach not done by 12:00 ET of the next weekday, a run of
    passes that are not ok over 6 h, a done day whose passes failed to fetch a filing;
(c) `evl_decide` stands for PREREG-EVL-4's rows of a close still to decide by themselves 2 h after the job first saw it;
    `evl_verdicts` reads their `decide-close-evl4` tallies;
(d) the notice: an INFO cause new while a told owner cause stands is mailed at once (the INFO causes alone, the owner
    causes named as still waiting); dlane's A4 is not judged under the research switch;
(e) `evl_handback`: a real event fill the book owes the lane's `real_fills` over 1 h and not there.
Synthetic stores only: every event, order, fill, quantity and price is invented; no market price is read."""
import datetime as dt
import json
import sqlite3
import unittest
from pathlib import Path

from league.events import calendar as C
from league.events import screen as SC
from league.events import store as ES
from league.ops import evl_health as EV
from league.ops import stall as ST
from league.tests.evl_book_fakes import Book, cancel_at_once, entry_why, ny
from league.tests.test_daily_report import Cal
from league.tests.test_evl_health import Lane, StallHarness, backfill_done, et, iso

MON, TUE, WED, THU, FRI = (dt.date(2026, 10, d) for d in (19, 20, 21, 22, 23))
HOUR = 3600.0


class Entries(Lane):
    """(a) `evl_entries`: the book's own rows of each auction of the last 24 h."""

    def setUp(self):
        super().setUp()
        backfill_done(self.st)
        self.book = Book(self.root)
        self.addCleanup(self.book.close)

    def entries(self, now):
        return self.check("evl_entries", now)

    def test_the_venues_cancel_at_once_is_a60s_rule_on_its_own_stamps(self):
        order = {"side": "buy", "tif": "opg", "filled_qty": "0", **cancel_at_once(TUE, "open", 5.0)}
        self.assertEqual(EV.venue_cancel_ms(order), 5)
        self.assertEqual(EV.venue_cancel_ms({**order, **cancel_at_once(TUE, "open", 60_000.0)}), 60000, "60 s: inside")
        for changed in ({"answer": cancel_at_once(TUE, "open", 60_001.0)["answer"]},  # past 60 s: the auction's own end
                        {"side": "sell"}, {"tif": "day"}, {"filled_qty": "1"}, {"status": "expired"},
                        {"answer": {**order["answer"], "cancel_sent": 1.0}},              # the House cancelled it
                        {"answer": {**order["answer"], "final": "replaced"}},
                        {"answer": {"final": "canceled", "submitted_at": order["answer"]["submitted_at"]}},
                        {"answer": {**order["answer"], "canceled_at": "2026-10-20T13:16:01"}}):  # no zone: no time
            self.assertIsNone(EV.venue_cancel_ms({**order, **changed}), changed)

    def test_the_rule_is_the_books_own_once_release_1019e_is_merged(self):
        """league/equity/live.py `venue_cancel_ms` (release 1019e, A80's re-send) and this reader judge the same orders
        alike: read here from the rows, there from the book's `Order`. Skipped on a tree without the re-send."""
        from league.equity import live as L

        if not hasattr(L, "venue_cancel_ms"):
            self.skipTest("release 1019e's re-send is not in this tree")
        specs = [cancel_at_once(TUE, "open", ms) for ms in (0.0, 5.0, 59_999.0, 60_000.0, 60_001.0, 180_000.0)]
        specs += [{**cancel_at_once(TUE, "open"), "filled": "1"}, {"status": "filled", "filled": "3"}, {"status": "expired"},
                  {"status": "canceled", "answer": {**cancel_at_once(TUE, "open")["answer"], "cancel_sent": 1.0}},
                  {"status": "canceled", "answer": {**cancel_at_once(TUE, "open")["answer"], "final": "replaced"}},
                  {**cancel_at_once(TUE, "open"), "side": "sell"}]
        iid = self.book.buy(TUE, "open")
        for spec in specs:
            self.book.order(iid, TUE, "open", **spec)
        self.book.db.row_factory = sqlite3.Row
        rows = [dict(r) for r in self.book.db.execute("SELECT * FROM eq_orders ORDER BY eid")]
        self.assertEqual([EV.venue_cancel_ms(r) for r in rows], [L.venue_cancel_ms(L.Order.of(r)) for r in rows])
        self.assertEqual(sum(1 for r in rows if EV.venue_cancel_ms(r) is not None), 4)

    def test_why_a_buy_was_never_sent_is_named_by_the_books_own_words(self):
        said = {
            "not filled at the open auction (never sent: the event kind's day order count: 148 of 150 sent, 2 kept for "
            "exiting its lots and buys held and this one)": "order_line",
            "sizing: no whole share fits (cash): refused: the House-wide available cash is $0.00": "cash",
            "sizing: no whole share fits (budget): refused: the shared loss budget has $0.00 of room": "budget",
            "sizing: no whole share fits (instrument): refused: XYZ may hold $0.00 more on the account": "name_wall",
            "sizing: no whole share fits (invested): refused: the invested cap leaves $0.00": "invested",
            "sizing: no whole share fits: the learning target rounds to none and one share at $99 is above 0.05 x E": "price",
            "not filled at the open auction (never sent: the program holds and has on order more than its 8 positions)":
                "room",
            "not filled at the close auction (never sent: the day's eligible list is not at the gateway yet)": "gateway",
            "not filled at the open auction (never sent: the gateway's kill switch is engaged)": "blocked",
            "not filled at the open auction (never sent: one order a symbol: an equity order on XYZ is working)": "busy",
            "not filled at the open auction (never sent)": "other",
        }
        for why, reason in said.items():
            self.assertEqual(EV.unsent_reason(why), reason, why)
        self.assertEqual(EV.unsent_reason("the refused buy: over", {"cap": "buying_power"}), "cash")
        self.assertEqual(EV.unsent_reason("the refused buy: over", {"cap": "stock_event_buys"}), "gateway")
        self.assertTrue(set(said.values()) <= set(EV.UNSENT))
        self.assertEqual(EV.sent_binding(entry_why("open", "cash")), "cash")
        self.assertIsNone(EV.sent_binding(entry_why("open", "intent")), "the target bought whole")
        self.assertEqual(EV.sent_binding(entry_why("open", "instrument")), "name_wall")

    def test_an_auction_under_90_percent_filled_stands_with_its_cancels_resends_and_never_sent(self):
        """Ten buys planned at Tuesday's open: six fill at once; two the venue cancelled 5 ms after it accepted them, one
        of which A80 sent again and it filled; one stopped by the day order count and one sized out on cash: 7 of 10."""
        filled = {"status": "filled", "filled": "3"}
        for _ in range(6):
            self.book.buy(TUE, "open", orders=(filled,))
        self.book.buy(TUE, "open", status="missed", orders=(cancel_at_once(TUE, "open"),),
                      why="not filled at the open auction (canceled; the venue cancelled it 5 ms after its submission)")
        self.book.buy(TUE, "open", orders=(cancel_at_once(TUE, "open", 6.0),
                                           {**filled, "why": "A80's one re-send (the venue cancelled the first buy 6 ms "
                                                             "after its submission, nothing filled): " + entry_why("open")}))
        self.book.buy(TUE, "open", status="missed", why="not filled at the open auction (never sent: the event kind's day "
                                                        "order count: 148 of 150 sent, 2 kept)")
        self.book.buy(TUE, "open", status="refused", why="sizing: no whole share fits (cash): refused: no cash")
        self.book.decision(TUE, "open", {"EVL-ERN-READ-O1": {"picks": 12, "room": 10, "planned": 10, "skipped": {}}})
        early = self.entries(et(TUE, "09:44"))
        self.assertEqual(early["numbers"]["auctions"], 1, "the open is judged 15 minutes after its cross; Monday's close is")
        self.assertFalse(early["stalled"])
        check = self.entries(et(TUE, "09:46"))
        self.assertTrue(check["stalled"])
        n = check["numbers"]
        self.assertEqual((n["planned"], n["filled"], n["fill_pct"], n["venue_cancels"], n["resent"], n["resent_filled"],
                          n["never_sent"], n["never_order_line"], n["never_cash"], n["short_first"]),
                         (10, 7, 70, 2, 1, 1, 2, 1, 1, "open:2026-10-20"))
        self.assertEqual(n["bound"], "room", "the decision cut 2 picks for room; cash and the order line stopped 1 each")
        self.assertIn("Real event buys fell short at 1 of 2 auctions of the last 24 h: 7 of 10 planned filled (70%, the "
                      "bar 90%); the venue cancelled 2 at once (A80), 1 went again once (1 filled); 2 never sent (the day "
                      "order count 1, cash 1)", check["what"])
        self.assertIn("The open of 2026-10-20 bound most on the program's room", check["what"])
        self.assertIsNone(check["owner_step"])
        for banned in ("XYZ", "12.34", "12.00"):
            self.assertNotIn(banned, json.dumps(check), banned)
        # A day later the auction has left the 24 hours.
        self.assertEqual(self.entries(et(WED, "09:46"))["numbers"]["planned"], 0)

    def test_nine_of_ten_filled_is_no_stall_but_one_never_sent_is(self):
        for _ in range(9):
            self.book.buy(TUE, "open", orders=({"status": "filled", "filled": "3"},))
        self.book.buy(TUE, "open", status="missed", orders=({"status": "expired"},),
                      why="not filled at the open auction (expired)")
        quiet = self.entries(et(TUE, "10:00"))
        self.assertFalse(quiet["stalled"])
        self.assertEqual((quiet["numbers"]["fill_pct"], quiet["numbers"]["unfilled"]), (90, 1))
        self.assertIn("9 of 10 planned filled (90%, the bar 90%); none never sent; 1 sent and not filled", quiet["what"])
        self.book.buy(TUE, "close", status="refused", why="sizing: no whole share fits (budget): refused: no room")
        for _ in range(19):
            self.book.buy(TUE, "close", orders=({"status": "filled", "filled": "1",
                                                 "why": entry_why("close", "budget", 1)},))
        check = self.entries(et(TUE, "16:20"))
        self.assertTrue(check["stalled"], "19 of 20 filled, but one was never sent")
        self.assertEqual((check["numbers"]["short_first"], check["numbers"]["bound"], check["numbers"]["never_budget"]),
                         ("close:2026-10-20", "budget", 1))

    def test_not_judged_without_the_books_tables_and_an_unreadable_book_blinds_only_itself(self):
        self.book.close()
        (self.root / "live.sqlite").unlink()
        self.assertFalse(self.entries(et(TUE, "10:00"))["judged"])
        sqlite3.connect(self.root / "live.sqlite").close()
        self.assertIn("no event table in live.sqlite", self.entries(et(TUE, "10:00"))["what"])
        (self.root / "live.sqlite").write_bytes(b"not a database" * 50)
        errors: list[str] = []
        out = EV.checks(self.ctx(), self.root, et(TUE, "10:00"), errors=errors)
        self.assertFalse(out["evl_entries"]["judged"])
        self.assertFalse(out["evl_handback"]["judged"])
        self.assertTrue(out["evl_record"]["judged"], "the lane's store is read as before")
        self.assertEqual(errors, ["live.sqlite could not be read for evl_entries (DatabaseError): it is not judged",
                                  "live.sqlite could not be read for evl_handback (DatabaseError): it is not judged"])


class Backfill(Lane):
    """(b) `evl_backfill`: the daily-index backfill's reach, from the lane's receipts and meta."""

    def backfill(self, day, at, status, **counts):
        summary = {"day": day.isoformat(), **({"why": "GatewayError: 404"} if status == "waiting" else
                                              {"complete": status == "ok", "rows": 9, "filings": 8, "known": 0,
                                               "fetched": 0, "failed": 0, "unlisted": 0, "redecide": 0, **counts})}
        self.receipt("backfill", at, status=status, summary=summary)

    def test_a_weekday_not_done_by_noon_of_the_next_weekday_stands(self):
        """Monday Oct 19 is the reach's first weekday (the lane registered that morning): its index is read from 05:00 ET
        Tuesday and due done by 12:00 ET Tuesday."""
        self.assertEqual(EV.backfill_reach(et(TUE, "11:00")), [MON], "nothing before the lane's registration")
        self.assertEqual(EV.backfill_reach(et(FRI, "11:00")), [MON, TUE, WED, THU][-3:])
        self.backfill(MON, et(TUE, "07:01"), "partial", known=500, fetched=7, failed=0)
        self.assertFalse(self.check("evl_backfill", et(TUE, "11:59"))["stalled"])
        check = self.check("evl_backfill", et(TUE, "13:30"))
        self.assertTrue(check["stalled"])
        self.assertEqual((check["numbers"]["first_day"], check["numbers"]["state"], check["numbers"]["hours"],
                          check["numbers"]["known"], check["numbers"]["fetched"]), ("2026-10-19", "late", 1.5, 500, 7))
        self.assertIn("The daily-index backfill of 2026-10-19 is not done 1.5 h after it was due (12:00 ET of the next "
                      "weekday): its last pass read 'partial' at 07:01 ET; 1 passes; 8 filings, 500 known", check["what"])
        self.st.set_meta("evl:backfill:2026-10-19", "done")
        self.assertFalse(self.check("evl_backfill", et(TUE, "13:30"))["stalled"])
        # Friday's index is due by Monday noon (the next weekday), not Saturday's.
        self.assertEqual(EV.backfill_due(dt.date(2026, 10, 23)), et(dt.date(2026, 10, 26), "12:00"))

    def test_a_waiting_or_partial_streak_over_six_hours_stands_before_its_day_is_due(self):
        backfill_done(self.st, [MON])
        for hhmm in ("05:01", "06:01", "07:01", "08:01", "09:01", "10:01", "11:01"):
            self.backfill(TUE, et(WED, hhmm), "waiting")
        self.assertFalse(self.check("evl_backfill", et(WED, "11:00"))["stalled"], "5.98 h: not yet")
        check = self.check("evl_backfill", et(WED, "11:05"))
        self.assertTrue(check["stalled"])
        self.assertEqual((check["numbers"]["state"], check["numbers"]["passes"], check["numbers"]["last_status"]),
                         ("streak", 7, "waiting"))
        self.assertIn("The daily-index backfill of 2026-10-20 has read waiting or partial for 6.1 h", check["what"])

    def test_a_done_day_whose_passes_failed_to_fetch_a_filing_stands(self):
        backfill_done(self.st, [MON, TUE])
        self.backfill(TUE, et(WED, "05:01"), "partial", fetched=3, failed=2)
        self.backfill(TUE, et(WED, "06:01"), "ok", known=5, fetched=1)
        check = self.check("evl_backfill", et(WED, "07:00"))
        self.assertTrue(check["stalled"])
        self.assertEqual((check["numbers"]["state"], check["numbers"]["failed"], check["numbers"]["fetched"]),
                         ("failed", 2, 4))
        self.assertIn("is done, but 2 filings failed to fetch in its passes", check["what"])
        self.assertIsNone(check["onset"])

    def test_release_1019fs_backfill_retries_count_the_days_last_figure_not_each_pass(self):
        """Release 1019f's backfill (fix/backfill-robust) tries a failed fetch again and its receipts carry `retrying`:
        their `failed` is the DAY's count so far. A filing that failed once and fetched on its retry leaves the done day
        clear (summed, the old way, it would stand for a filing that is in the store); one past its last try stands,
        named by the last receipt (`done-failed`, its `unfetched`)."""
        backfill_done(self.st, [MON, TUE])
        self.backfill(TUE, et(WED, "05:01"), "partial", fetched=3, failed=1, retrying=1, retried=0)
        self.backfill(TUE, et(WED, "05:04"), "ok", fetched=1, failed=0, retrying=0, retried=1)
        clear = self.check("evl_backfill", et(WED, "07:00"))
        self.assertFalse(clear["stalled"], clear["what"])
        self.backfill(MON, et(TUE, "05:01"), "partial", fetched=2, failed=1, retrying=1, retried=0)
        self.backfill(MON, et(TUE, "06:05"), "done-failed", failed=1, retrying=0, retried=1,
                      unfetched=[{"accession": "0000000003-26-000702", "form": "8-K", "tries": 6, "error": "x"}])
        check = self.check("evl_backfill", et(WED, "07:00"))
        self.assertTrue(check["stalled"])
        self.assertEqual((check["numbers"]["first_day"], check["numbers"]["state"], check["numbers"]["failed"]),
                         ("2026-10-19", "failed", 1))
        self.assertIn("is done, but 1 filings failed to fetch after their last try (named in its last receipt's "
                      "`unfetched`)", check["what"])


class FourKind(Lane):
    """(c) PREREG-EVL-4's rows of a close a release without them decided: `evl_decide` and `evl_verdicts`."""

    def setUp(self):
        super().setUp()
        backfill_done(self.st)
        C.refresh(self.st, Cal(), dt.date(2026, 10, 1), dt.date(2026, 12, 31))
        # Tuesday's close decided by a release without PREREG-EVL-4's rows (its receipt names none of them); the opens
        # decided in their windows.
        self.receipt("decide-open:2026-10-20", et(TUE, "09:15"))
        self.receipt("decide-close:2026-10-20", et(TUE, "15:47"), summary={"verdicts": {"needed": 0, "answered": 0}})
        self.receipt("decide-open:2026-10-21", et(WED, "09:15"))
        self.kept: dict = {}

    def decide(self, now, **kw):
        errors: list[str] = []
        out = EV.checks(self.ctx(), self.root, now, errors=errors, kept=self.kept, **kw)
        return out["evl_decide"]

    def test_the_judges_own_reading_names_the_close(self):
        self.assertIn(TUE, SC.made_without(self.st, WED))

    def test_a_close_still_to_decide_two_hours_after_first_sight_stands_and_clears_once_decided(self):
        first = self.decide(et(WED, "08:00"))
        self.assertEqual(first["numbers"]["four_waiting"], 0, "first seen now")
        self.assertEqual(sorted(self.kept["four"]), ["2026-10-20"])
        self.assertFalse(self.decide(et(WED, "09:59"))["stalled"])
        check = self.decide(et(WED, "10:01"))
        self.assertTrue(check["stalled"])
        self.assertEqual((check["numbers"]["four_first"], check["numbers"]["four_state"], check["numbers"]["four_hours"]),
                         ("2026-10-20", "never", 2.0))
        self.assertIn("PREREG-EVL-4's rows of the close of 2026-10-20 are still to decide by themselves 2.0 h after a "
                      "release decided it without them: its decide-close-evl4 was never run", check["what"])
        self.receipt(f"decide-{SC.FOUR_KIND}:2026-10-20", et(WED, "10:02"), status="failed", summary={"why": "x"})
        self.assertEqual(self.decide(et(WED, "10:10"))["numbers"]["four_state"], "failed")
        self.receipt(f"decide-{SC.FOUR_KIND}:2026-10-20", et(WED, "10:12"), status="pending",
                     summary={"verdicts": {"needed": 2, "answered": 1}})
        self.assertEqual(self.decide(et(WED, "10:20"))["numbers"]["four_state"], "pending")
        verdicts = EV.checks(self.ctx(), self.root, et(WED, "10:40"), kept=self.kept)["evl_verdicts"]
        self.assertTrue(verdicts["stalled"], "its tally is read: 1 verdict unanswered 28 minutes past its run")
        self.assertEqual(verdicts["numbers"]["first_held"], "close-evl4:2026-10-20")
        self.assertIn("1 verdicts the event lane's close decision of PREREG-EVL-4's rows of 2026-10-20 needs",
                      verdicts["what"])
        self.receipt(f"decide-{SC.FOUR_KIND}:2026-10-20", et(WED, "10:41"), summary={"verdicts": {"needed": 2,
                                                                                                  "answered": 2}})
        done = self.decide(et(WED, "10:50"))
        self.assertFalse(done["stalled"])
        self.assertEqual(self.kept["four"], {}, "a close no longer waiting is dropped")

    def test_a_close_decided_again_by_a_release_without_the_rows_is_stale_and_stands(self):
        self.receipt(f"decide-{SC.FOUR_KIND}:2026-10-20", et(WED, "08:00"))
        self.receipt("decide-close:2026-10-20", et(WED, "08:30"), summary={})   # decided again without the rows
        self.assertEqual(SC.made_without(self.st, WED), {TUE: True})
        self.decide(et(WED, "08:40"))
        self.assertFalse(self.decide(et(WED, "10:30"))["stalled"], "2 h from the job's first sight")
        self.assertEqual(self.decide(et(WED, "10:45"))["numbers"]["four_state"], "stale")

    def test_the_houses_pause_holds_it_and_its_end_starts_the_clock(self):
        self.decide(et(WED, "06:00"))
        pause = {"stop": [], "pause": [[et(WED, "07:00"), None]]}
        self.assertFalse(self.decide(et(WED, "09:00"), idle=pause)["stalled"])
        ended = {"stop": [], "pause": [[et(WED, "07:00"), et(WED, "09:00")]]}
        self.assertFalse(self.decide(et(WED, "10:59"), idle=ended)["stalled"])
        self.assertTrue(self.decide(et(WED, "11:01"), idle=ended)["stalled"])


class Handback(Lane):
    """(e) `evl_handback`: the book's real event fills beside the lane's `real_fills`."""

    def setUp(self):
        super().setUp()
        backfill_done(self.st)
        self.book = Book(self.root)
        self.addCleanup(self.book.close)

    def fill_row(self, side, event="ev1"):
        self.st.db.execute("INSERT INTO real_fills(program, version, event, side, qty, price, fee, filled_at, band) VALUES("
                           "'EVL-ERN-READ-O1', 2, ?, ?, 3, 12.0, 0, '2026-10-20T13:30:00Z', 'learning')", (event, side))

    def test_a_fill_owed_over_an_hour_and_not_in_real_fills_stands(self):
        cross = ny(TUE, "09:30")
        iid = self.book.buy(TUE, "open", event="ev1", ended=cross + 150)
        lid = self.book.lot(iid, event="ev1", opened_at=cross + 5)
        self.book.order(iid, TUE, "open", status="filled", filled="3", lid=lid, fill_at=cross + 5)
        self.assertFalse(self.check("evl_handback", cross + 150 + HOUR - 60)["stalled"], "under an hour")
        check = self.check("evl_handback", cross + 150 + HOUR + 60)
        self.assertTrue(check["stalled"])
        n = check["numbers"]
        self.assertEqual((n["fills_due"], n["missing_late"], n["missing_buys"], n["oldest_program"], n["oldest_side"]),
                         (1, 1, 1, "evl-ern-read-o1", "buy"))
        self.assertIn("1 real event fills are not in the lane's real_fills more than 1 h after the book owed them (1 buys, "
                      "0 sales); the oldest, a buy of EVL-ERN-READ-O1 version 2, owed since 09:32 ET 2026-10-20",
                      check["what"])
        self.fill_row("buy")
        quiet = self.check("evl_handback", cross + 3 * HOUR)
        self.assertFalse(quiet["stalled"])
        self.assertEqual((quiet["numbers"]["handed"], quiet["numbers"]["missing"]), (1, 0))

    def test_a_buy_still_at_its_auction_and_a_lot_not_closed_owe_nothing_yet(self):
        cross = ny(TUE, "16:00")
        live = self.book.buy(TUE, "close", status="sent", event="ev2")
        lid = self.book.lot(live, event="ev2", opened_at=cross)
        self.book.order(live, TUE, "close", status="filled", filled="3", lid=lid, fill_at=cross)
        self.assertEqual(self.check("evl_handback", cross + 5 * HOUR)["numbers"]["fills_due"], 0,
                         "its intent has not ended: the book hands the buy back once it has")
        done = self.book.buy(TUE, "open", event="ev3")
        held = self.book.lot(done, event="ev3", opened_at=ny(TUE, "09:30"))
        self.book.order(done, TUE, "open", status="filled", filled="3", lid=held, fill_at=ny(TUE, "09:30"))
        self.book.order(done, TUE, "close", status="filled", filled="1", side="sell", lid=held, fill_at=cross)
        self.fill_row("buy", "ev3")
        check = self.check("evl_handback", cross + 5 * HOUR)
        self.assertFalse(check["stalled"], "a part sold of a lot still open: its sale is handed back once it closes")
        self.book.db.execute("UPDATE eq_lots SET status='closed', closed_at=? WHERE lid=?", (cross + 60, held))
        sale = self.check("evl_handback", cross + 5 * HOUR)
        self.assertTrue(sale["stalled"])
        self.assertEqual((sale["numbers"]["missing_sales"], sale["numbers"]["oldest_side"]), (1, "sell"))


class NoticePace(StallHarness):
    """(d) THE NOTICE: a told owner cause no longer holds a new INFO cause back."""

    def test_pure(self):
        mail = {"owner_at": ST.S.iso(0.0), "owner_causes": ["kill_on"], "info_at": None,
                "told": {"kill_on": ST.S.iso(0.0), "dlane": ST.S.iso(0.0)}}
        self.assertIsNone(ST.due_notice(["kill_on"], ["kill_on"], mail, HOUR))
        self.assertIsNone(ST.due_notice(["kill_on", "dlane"], ["kill_on"], mail, HOUR), "dlane was told an hour ago")
        self.assertEqual(ST.due_notice(["kill_on", "evl_record"], ["kill_on"], mail, HOUR), "info")
        self.assertEqual(ST.due_notice(["kill_on", "evl_record"], ["kill_on", "evl_record"], mail, HOUR), "owner")
        self.assertIsNone(ST.due_notice(["kill_on", "evl_record"], ["kill_on"], {k: v for k, v in mail.items()
                                                                               if k != "told"}, HOUR),
                          "a state file from before the told record: the owner pace alone")
        self.assertEqual(ST.due_notice(["kill_on", "dlane"], ["kill_on"], mail, 25 * HOUR), "owner", "12 h on: owner")
        entries = [{"cause": "kill_on", "owner_step": "lift"}, {"cause": "evl_record", "owner_step": None}]
        self.assertEqual([e["cause"] for e in ST.notice_causes(entries, "info", ["kill_on"])], ["evl_record"])
        self.assertEqual(len(ST.notice_causes(entries, "owner", ["kill_on"])), 2)

    def test_a_new_event_lane_cause_is_mailed_at_once_while_a_told_owner_cause_stands(self):
        self.lane(record_ago_minutes=2)
        st = ES.Store(self.root / "events")
        for job, start in (("decide-open:2026-10-20", et(TUE, "09:15")), ("decide-close:2026-10-19", et(MON, "15:47"))):
            st.db.execute("INSERT INTO receipts(job, started_at, finished_at, status, summary) VALUES(?, ?, ?, 'ok', '{}')",
                          (job, iso(start), iso(start + 60)))
        st.close()
        self.health = {"kill_switch": True}
        first = ST.run(self.ctx())
        self.assertEqual((first["stalled"], first["notice"]["notice_id"]), (["kill_on"], "stall:owner:kill_on"))
        # 40 minutes on, the record passes stop: evl_record stands, and is mailed now, not 12 hours later.
        later = ST.run(self.ctx(now=self.now_ + 40 * 60))
        self.assertEqual(later["stalled"], ["kill_on", "evl_record"])
        self.assertTrue(later["notice"]["sent"])
        self.assertEqual((later["notice"]["notice_id"], later["notice"]["causes"]), ("stall:info:evl_record",
                                                                                     ["evl_record"]))
        facts = self.notify.calls[-1]
        self.assertEqual(([c["cause"] for c in facts["causes"]], facts["waiting_owner"]), (["evl_record"], ["kill_on"]))
        mail = json.loads((self.root / ST.STATE_FILE).read_text())["mail"]
        self.assertEqual((mail["owner_causes"], sorted(mail["told"])), (["kill_on"], ["evl_record", "kill_on"]))
        stalls = lambda: [c for c in self.notify.calls if c.get("kind") == "stall"]  # noqa: E731
        self.assertEqual(len(stalls()), 2)
        ST.run(self.ctx(now=self.now_ + 70 * 60))
        self.assertEqual(len(stalls()), 2, "both told: nothing until the owner pace")
        ST.run(self.ctx(now=self.now_ + 12 * HOUR + 60))
        [*_, last] = [c for c in self.notify.calls if c.get("kind") == "stall"]
        self.assertEqual(last["notice_id"], "stall:owner:kill_on", "12 h on, the owner notice again")
        told = [c["cause"] for c in last["causes"]]
        self.assertEqual((told[0], "evl_record" in told, "waiting_owner" in last), ("kill_on", True, False),
                         "an owner notice tells every cause standing")

    def test_an_info_notice_tells_no_done_checkpoint_it_does_not_list(self):
        """A Done checkpoint is told only by a notice that lists `done` (an owner cause): an INFO notice sent while it
        stands, told as a cause inside the 12 hours, leaves its key untold (`stall.json` `done_told`)."""
        self.lane(record_ago_minutes=45)   # evl_record stands, needing nothing
        st = ES.Store(self.root / "events")
        for job, start in (("decide-open:2026-10-20", et(TUE, "09:15")), ("decide-close:2026-10-19", et(MON, "15:47"))):
            st.db.execute("INSERT INTO receipts(job, started_at, finished_at, status, summary) VALUES(?, ?, ?, 'ok', '{}')",
                          (job, iso(start), iso(start + 60)))
        st.close()
        held = {"checkpoints": [{"at_close": 20, "holds": True, "final": True}]}
        (self.root / ST.DLANE_REPORT).write_text(json.dumps({"at": self.now_ - 600, "lane": {"mode": "gate"}, "k5": {},
                                                             "alarms": [], "done": {"all": held}}))
        an_hour_ago = ST.S.iso(self.now_ - HOUR)
        (self.root / ST.STATE_FILE).write_text(json.dumps({"schema": 2, "done_told": [], "mail": {
            "owner_at": an_hour_ago, "owner_causes": ["done"], "told": {"done": an_hour_ago}}}))
        out = ST.run(self.ctx())
        self.assertEqual((out["stalled"], out["notice"]["notice_id"]), (["done", "evl_record"], "stall:info:evl_record"))
        self.assertEqual(self.notify.calls[-1]["waiting_owner"], ["done"])
        self.assertEqual(json.loads((self.root / ST.STATE_FILE).read_text())["done_told"], [], "not listed: not told")

    def test_dlanes_a4_is_not_judged_under_the_research_switch(self):
        self.lane(record_ago_minutes=2)
        report = {"at": self.now_ - 600, "lane": {"mode": "gate"}, "k5": {},
                  "alarms": [{"id": "A4", "level": "warning", "text": "A4: the Probe loss budget has under one unit"}]}
        (self.root / ST.DLANE_REPORT).write_text(json.dumps(report))
        off = ST.run(self.ctx())
        self.assertNotIn("dlane", off["stalled"])
        self.assertEqual(off["checks"]["dlane"]["numbers"]["not_judged"], "a4")
        on = ST.run(self.ctx(now=self.now_ + 60, settings={}))
        self.assertIn("dlane", on["stalled"], "with research on it stands as before")
        self.assertEqual(ST.CLOSED_LANE_ALARMS, ("A4",))


class StallJobWiring(StallHarness):
    """The three new causes stand through the stall job, are kept in its state, and are worded by the gateway."""

    def test_through_the_job(self):
        self.lane(record_ago_minutes=2)
        book = Book(self.root)
        book.buy(TUE, "open", status="missed", why="not filled at the open auction (never sent: the event kind's day "
                                                    "order count: 150 of 150 sent)")
        book.close()
        out = ST.run(self.ctx())
        self.assertIn("evl_entries", out["stalled"])
        self.assertEqual(out["checks"]["evl_entries"]["numbers"]["never_order_line"], 1)
        self.assertIn("evl_entries", out["warned"])
        state = json.loads((self.root / ST.STATE_FILE).read_text())
        self.assertIn("four", state["evl_kept"])
        gateway = (Path(__file__).resolve().parents[2] / "gateway" / "lib" / "email.mjs").read_text()
        for cause in ("evl_entries", "evl_backfill", "evl_handback"):
            self.assertIn(cause, ST.CAUSES)
            self.assertIn(f"  {cause}: '", gateway, cause)


if __name__ == "__main__":
    unittest.main()
