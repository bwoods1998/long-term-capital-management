"""RELEASE 1019i'S REPORT LINES AND ALARMS (PREREG-EVL-7's harness change H4, PREREG-EVL-8's harness plan H1):
`evl_fill_rate` and `evl_attempts` (league/ops/evl_health.py, raised by the stall job, worded by the gateway), the lane
report's settle-pace and fill-rate lines (league/events/report.py), the mail's facts (league/ops/daily_report.py
`settle_line`, `fill_lines`), and the births' facts wall over the new tables (league/events/births.py `FACTS_DENY`).
Every row here is invented; no figure is a market's.
"""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from league.events import attempts as AT
from league.events import births as BI
from league.events import report as RP
from league.events import store as S
from league.ops import daily_report as DR
from league.ops import evl_health as EV
from league.ops import stall as ST

UTC = dt.timezone.utc
CTX = {"config": {"events": {"enabled": True}}, "settings": {}}


def at(day: dt.date, hh: int, mm: int) -> dt.datetime:
    return dt.datetime.combine(day, dt.time(hh, mm), tzinfo=UTC)


class LaneCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.st = S.Store(self.root / "events")
        self.addCleanup(self.st.close)
        d = dt.date(2026, 9, 1)
        with self.st.tx() as db:
            while d <= dt.date(2026, 11, 30):
                if d.weekday() < 5:
                    db.execute("INSERT INTO sessions(day, open_at, close_at, early) VALUES(?, ?, ?, 0)",
                               (d.isoformat(), S.iso(at(d, 13, 30)), S.iso(at(d, 20, 0))))
                d += dt.timedelta(days=1)
        self.n = 0

    def days(self, last, n):
        out, d = [], last
        while len(out) < n:
            if d.weekday() < 5:
                out.append(d)
            d -= dt.timedelta(days=1)
        return sorted(out)

    def attempt(self, day, auction="open", *, filled=True, final=True, side="buy"):
        self.n += 1
        kind = {("buy", "open"): "loo", ("buy", "close"): "loc", ("sell", "open"): "moo", ("sell", "close"): "moc"}
        AT.record(self.st, [{"client_id": f"c{self.n}", "venue_id": "v", "program": "EVL-ERN-READ-O1", "version": 2,
                             "event": f"8k:{self.n}", "side": side, "kind": kind[(side, auction)], "day": day.isoformat(),
                             "at": auction, "band": "learning", "rung": 0, "resend": 0, "replaces": None, "sent": 1,
                             "accepted": 1, "state": ("filled" if filled else "canceled") if final else "working",
                             "final": int(final), "venue_status": None, "qty": 2.0, "filled_qty": 2.0 if filled else 0.0,
                             "avg_px": None, "limit_px": 20.0, "cancel_ms": None, "sent_at": None, "submitted_at": None,
                             "filled_at": None, "canceled_at": None, "expired_at": None, "binding": None,
                             "updated_at": S.iso(at(day, 14, 0))}])

    def check(self, cause, now):
        return EV.checks(CTX, self.root, now.timestamp())[cause]


class TheFillRateAlarm(LaneCase):
    def test_a_three_session_rate_under_85_percent_stands_and_a_healthy_one_does_not(self):
        last = dt.date(2026, 10, 30)
        for day in self.days(last, 20):
            for i in range(5):
                self.attempt(day, "open", filled=day < dt.date(2026, 10, 28) or i < 4)
                self.attempt(day, "close")
        check = self.check("evl_fill_rate", at(last, 22, 0))
        self.assertTrue(check["stalled"], check["what"])
        self.assertIn("the open's 80% of 15 sent over 3 sessions is under 85%", check["what"])
        self.assertEqual((check["numbers"]["open_sent_3"], check["numbers"]["open_filled_3"]), (15, 12))
        self.assertEqual(check["numbers"]["dropped"], "open")
        for day in self.days(last, 3):
            for _ in range(10):
                self.attempt(day, "open")
        quiet = self.check("evl_fill_rate", at(last, 22, 0))
        self.assertFalse(quiet["stalled"], quiet["what"])
        self.assertTrue(quiet["judged"])

    def test_not_judged_without_the_ledger(self):
        self.st.db.execute("DROP TABLE real_attempts")
        for cause in ("evl_fill_rate", "evl_attempts"):
            got = self.check(cause, at(dt.date(2026, 10, 30), 22, 0))
            self.assertFalse(got["judged"], cause)
            self.assertIn("no attempts ledger yet", got["what"])

    def test_the_stall_job_names_both_and_the_gateway_words_them(self):
        self.assertIn("evl_fill_rate", ST.CAUSES)
        self.assertIn("evl_attempts", ST.CAUSES)
        self.assertEqual(ST.CAUSES[-7:-5], ("evl_fill_rate", "evl_attempts"))
        source = (Path(__file__).resolve().parents[2] / "gateway" / "lib" / "email.mjs").read_text()
        for cause in ("evl_fill_rate", "evl_attempts"):
            self.assertIn(f"\n  {cause}: '", source)
            self.assertIn(cause, EV.DOING)


class TheAttemptsAlarm(LaneCase):
    def test_an_order_with_no_final_state_an_hour_after_its_auction(self):
        day = dt.date(2026, 10, 29)
        self.attempt(day, "open", final=False)
        self.assertFalse(self.check("evl_attempts", at(day, 14, 29))["stalled"], "59 minutes after the open")
        check = self.check("evl_attempts", at(day, 14, 31))
        self.assertTrue(check["stalled"])
        self.assertIn("1 order sent with no final state an hour after the auction", check["what"])
        self.assertEqual(check["numbers"]["open"], 1)
        self.assertEqual(check["onset"], at(day, 14, 30).timestamp())
        self.attempt(day, "close")
        self.st.db.execute("UPDATE real_attempts SET state='filled', final=1")
        self.assertFalse(self.check("evl_attempts", at(day, 22, 0))["stalled"])

    def test_an_order_of_the_book_the_ledger_lacks(self):
        from league.tests.evl_book_fakes import Book, ny

        day = dt.date(2026, 10, 29)
        book = Book(self.root)
        book.buy(day, "open", orders=({"status": "filled", "filled": "2"},))
        # the book's instance row (a real event instance), so its orders are the ledger's
        book.db.execute("INSERT INTO eq_instances(id, family, version, lane, run_sha, code, params, band, max_hold, "
                        "created_at) VALUES('EVL-ERN-READ-O1:2:r', 'EVL-ERN-READ-O1', 2, 'event', 'x', 'x', '{}', "
                        "'learning', 1, 0)")
        book.db.execute("UPDATE eq_orders SET updated_at=?", (ny(day, "09:35"),))
        book.close()
        late = dt.datetime.fromtimestamp(ny(day, "11:00"), UTC)
        check = self.check("evl_attempts", late)
        self.assertTrue(check["stalled"], check["what"])
        self.assertEqual(check["numbers"]["missing"], 1)
        self.assertIn("1 of the book's orders are not in the ledger", check["what"])
        rows, _ = AT.book_rows(lambda sql, params=(): _rows(self.root / "live.sqlite", sql, params))
        AT.record(self.st, rows)
        self.assertFalse(self.check("evl_attempts", late)["stalled"], "the hand-back caught up")


def _rows(path, sql, params):
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in db.execute(sql, tuple(params)).fetchall()]
    finally:
        db.close()


class TheReportLines(LaneCase):
    def score(self, night, status, **summary):
        rid = self.st.start_receipt("score", now=at(night, 1, 0) + dt.timedelta(days=1))
        self.st.finish_receipt(rid, status, {"day": night.isoformat(), **summary})

    def test_the_settle_pace_of_a_night(self):
        night = dt.date(2026, 10, 29)
        self.assertIsNone(RP.settle_pace(self.st, night))
        self.score(night, "partial", due=300, settled=280, skipped=10, waiting=10, errors=0, batched=True, seconds=120.0,
                   requests={"bars": 4, "trades": 590, "other": 0}, parity={"checked": 14, "equal": 14})
        self.score(night, "ok", due=40, settled=40, skipped=0, waiting=0, errors=0, batched=True, seconds=30.0,
                   requests={"bars": 2, "trades": 80, "other": 0})
        self.score(dt.date(2026, 10, 28), "ok", due=999, settled=999)        # another night's pass is not counted
        pace = RP.settle_pace(self.st, night)
        self.assertEqual((pace["passes"], pace["complete"], pace["settled"], pace["due"], pace["batched"]),
                         (2, True, 320, 340, 2))
        self.assertEqual(pace["seconds"], 150.0)
        self.assertEqual(pace["pace"], 128.0)
        self.assertEqual(pace["requests"], {"bars": 6, "trades": 670, "other": 0})
        self.assertEqual(pace["parity"], {"checked": 14, "equal": 14})
        line = DR.settle_line(pace)
        self.assertEqual(set(line), set(DR.SETTLE_FIELDS) | {"requests", "parity"})
        self.assertEqual(DR.settle_line(None)["passes"], 0)
        rep = RP.build(self.st, night, now=at(night, 23, 0) + dt.timedelta(days=1))
        text = RP.render(rep)
        self.assertIn("Score: 320 settled, 10 skipped, 10 waiting of 340 tried in 2 passes (2 batched), 150 s, 128.0 a "
                      "minute; requests: bars 6, trades 670; parity 14 of 14 equal", text)

    def test_the_fill_rate_lines(self):
        last = dt.date(2026, 10, 30)
        for day in self.days(last, 20):
            self.attempt(day, "open")
            self.attempt(day, "close", filled=day != last)
        lines = DR.fill_lines(AT.fill_rates(self.st, last))
        self.assertEqual(lines["close"]["last3"]["buys_sent"], 3)
        self.assertEqual(lines["close"]["last3"]["buys_filled"], 2)
        self.assertEqual(lines["open"]["last20"]["fill_rate"], 1.0)
        self.assertEqual(set(lines["open"]["last3"]), set(DR.FILL_FIELDS))
        empty = DR.fill_lines(None)
        self.assertEqual(set(empty), {"open", "close"})
        self.assertTrue(all(v is None for a in empty.values() for n in a.values() for v in n.values()))
        text = RP.render(RP.build(self.st, last, now=at(last, 23, 0)))
        self.assertIn("Fills (attempts ledger): open 3/3 100% (3) / 20/20 100% (20)", text)
        self.assertIn("close 2/3 67% (3) / 19/20 95% (20)", text)


class TheFactsWall(unittest.TestCase):
    def test_the_births_facts_never_read_the_ledger_or_the_parity_flags(self):
        self.assertTrue({"real_attempts", "score_parity"} <= BI.FACTS_DENY)
        with tempfile.TemporaryDirectory() as tmp:
            st = S.Store(Path(tmp) / "events")
            try:
                with BI.outcome_free(st.db):
                    for table in ("real_attempts", "score_parity"):
                        with self.assertRaises(sqlite3.DatabaseError, msg=table):
                            st.db.execute(f"SELECT * FROM {table}").fetchall()
                self.assertEqual(st.db.execute("SELECT COUNT(*) FROM real_attempts").fetchone()[0], 0)
            finally:
                st.close()

    def test_every_table_of_the_lane_that_carries_a_price_or_an_outcome_is_walled(self):
        with tempfile.TemporaryDirectory() as tmp:
            st = S.Store(Path(tmp) / "events")
            try:
                tables = {r[0] for r in st.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            finally:
                st.close()
        priced = {"bars", "marks", "outcomes", "looks", "bands", "band_history", "real_fills", "universe", "meta",
                  "real_attempts", "score_parity"}
        self.assertTrue(priced <= tables)
        self.assertTrue(priced <= BI.FACTS_DENY)


if __name__ == "__main__":
    unittest.main()
