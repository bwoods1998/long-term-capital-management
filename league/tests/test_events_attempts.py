"""THE ATTEMPTS LEDGER (release 1019i; PREREG-EVL-7's harness changes H3 and H4, league/events/attempts.py).

Through the REAL book (league/equity/live.py `_event_attempts`), the real `size_entry`, the money table in force and
test_events_venue_cancel's auction venue that cancels an accepted buy by itself (A80): every event order the book sends
is in the lane's `real_attempts` with the venue's own states (the cancelled buy with A80's cancel time, its re-send
marked, the fill, the closing sale), a pick that ended unsent has its row, the ORDER BODIES SENT ARE BYTE-IDENTICAL with
the ledger on and off, and a lane store without the table makes the rows wait. Then the fill-rate lines over 3 and 20
sessions and the two alarms' findings on an invented ledger. No figure here is a market's.
"""

from __future__ import annotations

import datetime as dt
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from league.events import attempts as AT
from league.events import book as BK
from league.events import store as S
from league.tests import test_events_venue_cancel as VC
from league.tests.test_events_book import DAY, NEXT
from league.tests.evl6_fakes import on_1019h


def ledger(h) -> list[dict]:
    return [dict(r) for r in h.lane.st.db.execute("SELECT * FROM real_attempts ORDER BY sent_at, client_id")]


# (release 1019j's assembly: a mechanism test written on release 1019h's seats; PREREG-EVL-6 moved every seat to a new
# version, so it runs on that table, as league/tests/test_events_book.py's do)
@on_1019h
class TheLedgerThroughTheBook(VC.VenueCancelTest):
    def session(self, h, *, day=DAY):
        for hh, mm in ((9, 15), (9, 16), (9, 17), (9, 18), (9, 31), (9, 33), (15, 46), (15, 47), (15, 48), (16, 1),
                       (16, 3), (16, 4), (16, 30)):
            h.tick(hh, mm, day=day)

    def test_every_order_with_the_venues_states_and_a80s_resend(self):
        h = self.harness()
        self.one_buy(h, 0.005)
        self.session(h)
        rows = ledger(h)
        buys = [r for r in rows if r["side"] == "buy"]
        sales = [r for r in rows if r["side"] == "sell"]
        self.assertEqual(len(buys), 2, rows)
        first, again = buys
        self.assertEqual((first["kind"], first["state"], first["final"], first["sent"], first["accepted"]),
                         ("loo", "canceled", 1, 1, 1))
        self.assertEqual((first["cancel_ms"], first["resend"], first["filled_qty"], first["venue_status"]),
                         (5, 0, 0.0, "canceled"))
        self.assertEqual((again["kind"], again["state"], again["resend"], again["filled_qty"], again["replaces"]),
                         ("loo", "filled", 1, 2.0, first["client_id"]))
        self.assertEqual(again["avg_px"], 17.0)
        self.assertEqual(again["limit_px"], 20.0)
        self.assertEqual((first["program"], first["version"], first["event"], first["day"], first["at"]),
                         (VC.PROGRAM, 2, "8k:a-1", DAY.isoformat(), "open"))
        [sale] = sales
        self.assertEqual((sale["kind"], sale["state"], sale["final"], sale["filled_qty"], sale["limit_px"]),
                         ("moc", "filled", 1, 2.0, None))
        self.assertEqual({r["client_id"] for r in rows}, {o.client_id for o in h.orders()}, "every order, once")
        self.assertIsNotNone(h.state.get(BK.ATTEMPTS_MARK))

    def test_the_order_bodies_sent_are_byte_identical_with_the_ledger_on_and_off(self):
        on = self.harness()
        self.one_buy(on, 0.005)
        self.session(on)
        with tempfile.TemporaryDirectory() as other:
            self.root = Path(other)
            with mock.patch.object(BK, "write_attempts", None):
                off = self.harness()
                self.one_buy(off, 0.005)
                self.session(off)
                # (a client id carries a hash of its state root, `lq-<root>-<n>-<program>`: every other field is the same)
                self.assertEqual([self.shape(b) for b in off.bodies()], [self.shape(b) for b in on.bodies()])
                self.assertEqual([b["client_order_id"].split("-", 2)[2] for b in off.bodies()],
                                 [b["client_order_id"].split("-", 2)[2] for b in on.bodies()])
                self.assertEqual([(o.status, str(o.filled_qty), o.tif, o.otype, str(o.limit_px)) for o in off.orders()],
                                 [(o.status, str(o.filled_qty), o.tif, o.otype, str(o.limit_px)) for o in on.orders()])
                self.assertEqual(ledger(off), [], "no ledger without the adapter's writer")
        self.assertEqual(len(on.bodies()), 3)
        self.assertEqual(len(ledger(on)), 3)

    def test_a_pick_that_ended_unsent_has_its_row(self):
        h = self.harness()
        self.one_buy(h)
        h.kill = True
        self.session(h)
        self.assertEqual(h.bodies(), [])
        [row] = ledger(h)
        self.assertEqual((row["state"], row["sent"], row["final"], row["kind"], row["side"]), ("unsent", 0, 1, "loo", "buy"))
        self.assertTrue(row["client_id"].startswith("unsent:"))

    def test_a_store_without_the_table_makes_the_rows_wait(self):
        h = self.harness()
        h.lane.st.db.execute("DROP TABLE real_attempts")
        self.one_buy(h, 0.005)
        out = {}
        for hh, mm in ((9, 15), (9, 16), (9, 17)):
            out = h.tick(hh, mm)
        self.assertIn("wait", out.get("event_attempts", ""))
        self.assertIsNone(h.state.get(BK.ATTEMPTS_MARK), "the mark moves only once the lane took them")
        h.lane.st.db.executescript(S.SCHEMA_1019I)
        h.tick(9, 18)
        self.assertEqual(len(ledger(h)), 2)


class TheRates(unittest.TestCase):
    """The fill-rate lines and the alarms' findings on an invented ledger (league/events/attempts.py)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.st = S.Store(Path(self.tmp.name) / "events")
        self.addCleanup(self.st.close)
        d = dt.date(2026, 9, 1)
        with self.st.tx() as db:
            while d <= dt.date(2026, 11, 30):
                if d.weekday() < 5:
                    o = dt.datetime.combine(d, dt.time(13, 30), tzinfo=dt.timezone.utc)
                    db.execute("INSERT INTO sessions(day, open_at, close_at, early) VALUES(?, ?, ?, 0)",
                               (d.isoformat(), S.iso(o), S.iso(o + dt.timedelta(hours=6, minutes=30))))
                d += dt.timedelta(days=1)
        self.n = 0

    def days(self, last, n):
        out, d = [], last
        while len(out) < n:
            if d.weekday() < 5:
                out.append(d)
            d -= dt.timedelta(days=1)
        return sorted(out)

    def buy(self, day, at="open", *, filled=True, cancel=None, resend=False, sent=True, final=True):
        self.n += 1
        kind = "loo" if at == "open" else "loc"
        row = {"client_id": f"c{self.n}", "venue_id": "v", "program": "EVL-ERN-READ-O1", "version": 2,
               "event": f"8k:{self.n}", "side": "buy", "kind": kind, "day": day.isoformat(), "at": at, "band": "learning",
               "rung": 0, "resend": 0, "replaces": None, "sent": int(sent), "accepted": int(sent),
               "state": ("filled" if filled else "canceled") if final else "working", "final": int(final),
               "venue_status": None, "qty": 2.0, "filled_qty": 2.0 if filled else 0.0, "avg_px": None, "limit_px": 20.0,
               "cancel_ms": cancel, "sent_at": None, "submitted_at": None, "filled_at": None, "canceled_at": None,
               "expired_at": None, "binding": None, "updated_at": "2026-10-01T00:00:00Z"}
        rows = [row]
        if resend:
            again = dict(row, client_id=f"c{self.n}-r", resend=1, cancel_ms=None, state="filled", filled_qty=2.0)
            rows = [dict(row, state="canceled", filled_qty=0.0, cancel_ms=5), again]
        AT.record(self.st, rows)

    def test_three_and_twenty_sessions_by_auction(self):
        last = dt.date(2026, 10, 30)
        for day in self.days(last, 20):
            for _ in range(4):
                self.buy(day, "open")
            self.buy(day, "close", filled=day < dt.date(2026, 10, 28))
        self.buy(last, "open", cancel=7, filled=False)
        self.buy(last, "open", resend=True)
        rates = AT.fill_rates(self.st, last)
        o3, o20 = rates["auctions"]["open"]["3"], rates["auctions"]["open"]["20"]
        self.assertEqual((o3["buys_sent"], o3["buys_filled"]), (14, 13))
        self.assertEqual((o20["buys_sent"], o20["buys_filled"]), (82, 81))
        self.assertEqual((o3["venue_cancels"], o3["buy_orders"], o3["resent"]), (2, 15, 1))
        c3, c20 = rates["auctions"]["close"]["3"], rates["auctions"]["close"]["20"]
        self.assertEqual((c3["buys_sent"], c3["buys_filled"], c3["fill_rate"]), (3, 0, 0.0))
        self.assertEqual((c20["buys_sent"], c20["buys_filled"]), (20, 17))
        self.assertEqual(rates["sessions"]["3"]["n"], 3)
        self.assertEqual(rates["sessions"]["20"]["first"], self.days(last, 20)[0].isoformat())
        self.assertEqual(AT.fill_drop(rates), [], "the close's 3 sessions hold 3 buys, under FILL_MIN")

    def test_a_low_rate_and_a_fall(self):
        last = dt.date(2026, 10, 30)
        for day in self.days(last, 20):
            for i in range(5):
                self.buy(day, "open", filled=day < dt.date(2026, 10, 28) or i < 4)    # 80% in the last 3
                self.buy(day, "close", filled=day < dt.date(2026, 10, 28) or i < 5)   # 100%
        found = AT.fill_drop(AT.fill_rates(self.st, last))
        self.assertEqual([(f["auction"], f["why"]) for f in found], [("open", "low")])
        st2 = AT.fill_drop({"auctions": {"close": {"3": {"fill_rate": 0.86, "buys_sent": 10},
                                                   "20": {"fill_rate": 0.99, "buys_sent": 60}}}})
        self.assertEqual([(f["auction"], f["why"]) for f in st2], [("close", "fall")])
        quiet = AT.fill_drop({"auctions": {"close": {"3": {"fill_rate": 0.90, "buys_sent": 10},
                                                     "20": {"fill_rate": 0.99, "buys_sent": 60}}}})
        self.assertEqual(quiet, [])

    def test_attempts_with_no_final_state(self):
        day = dt.date(2026, 10, 29)
        self.buy(day, "open", final=False)
        self.buy(day, "close", final=False)
        open_end = dt.datetime.combine(day, dt.time(13, 30), tzinfo=dt.timezone.utc)
        self.assertEqual(AT.open_attempts(self.st, open_end + dt.timedelta(minutes=59)), [])
        got = AT.open_attempts(self.st, open_end + dt.timedelta(minutes=61))
        self.assertEqual([r["kind"] for r in got], ["loo"])
        later = AT.open_attempts(self.st, open_end + dt.timedelta(hours=8))
        self.assertEqual(sorted(r["kind"] for r in later), ["loc", "loo"])
        self.assertNotIn("avg_px", later[0])

    def test_the_ledger_incomplete(self):
        book = [{"client_id": "a", "program": "P", "state": "filled", "updated_at": "2026-10-29T14:00:00Z"},
                {"client_id": "b", "program": "P", "state": "working", "updated_at": "2026-10-29T14:00:00Z"},
                {"client_id": "c", "program": "P", "state": "filled", "updated_at": "2026-10-29T15:30:00Z"}]
        held = {"a": {"state": "filled"}, "b": {"state": "pending"}}
        now = S.parse_iso("2026-10-29T16:00:00Z").timestamp()
        self.assertEqual([m["client_id"] for m in AT.missing(book, held, now)], ["b"])

    def test_record_is_idempotent_and_keeps_first_seen(self):
        self.buy(dt.date(2026, 10, 29))
        first = dict(self.st.db.execute("SELECT * FROM real_attempts").fetchone())
        self.assertEqual(AT.record(self.st, [{k: first[k] for k in AT.COLUMNS}]), 0)
        moved = {k: first[k] for k in AT.COLUMNS} | {"state": "expired", "final": 1}
        self.assertEqual(AT.record(self.st, [moved]), 1)
        again = dict(self.st.db.execute("SELECT * FROM real_attempts").fetchone())
        self.assertEqual((again["state"], again["first_seen"]), ("expired", first["first_seen"]))

    def test_the_kinds(self):
        self.assertEqual(AT.KINDS, {("buy", "opg"): "loo", ("buy", "cls"): "loc", ("sell", "opg"): "moo",
                                    ("sell", "cls"): "moc"})


if __name__ == "__main__":
    unittest.main()
