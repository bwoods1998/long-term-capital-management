"""RELEASE 1019i'S REPORT LINES AND ALARMS (PREREG-EVL-7's harness change H4, PREREG-EVL-8's harness plan H1 and H2):
`evl_fill_rate` and `evl_attempts` (league/ops/evl_health.py, raised by the stall job, worded by the gateway), and,
from its review, `evl_score_parity` (the batched score's parity latch: a flag 0 fails closed) and `evl_px_store` (the
price lane's store at its 2 GB line or the disk under the PX floor), the lane report's settle-pace and fill-rate lines
(league/events/report.py), the mail's facts (league/ops/daily_report.py `settle_line`, `fill_lines`, `px_line`), and
the births' facts wall over the new tables (league/events/births.py `FACTS_DENY`). Every row here is invented; no
figure is a market's.
"""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from league.events import attempts as AT
from league.events import births as BI
from league.events import pxstore as PXS
from league.events import report as RP
from league.events import score as SCO
from league.events import store as S
from league.ops import daily_report as DR
from league.ops import evl_health as EV
from league.ops import stall as ST

UTC = dt.timezone.utc
CTX = {"config": {"events": {"enabled": True}}, "settings": {}}
PX_ON = {"config": {"events": {"enabled": True, "px_data": True}}, "settings": {}}
GB = 2 ** 30


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

    def check(self, cause, now, ctx=CTX):
        return EV.checks(ctx, self.root, now.timestamp())[cause]


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
        self.assertEqual(ST.CAUSES[-8:-4], ("evl_fill_rate", "evl_attempts", "evl_score_parity", "evl_px_store"))
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


class TheParityAlarm(LaneCase):
    """`evl_score_parity`: the batched score's parity latch stands (league/events/score.py `latched`)."""

    def test_the_latch_stands_until_the_captain_clears_it(self):
        now = at(dt.date(2026, 10, 30), 2, 0)
        quiet = self.check("evl_score_parity", now)
        self.assertEqual((quiet["stalled"], quiet["judged"]), (False, True), quiet["what"])
        night = dt.date(2026, 10, 29)
        with self.st.tx() as db:
            for i, equal in enumerate((1, 1, 0)):
                db.execute("INSERT INTO score_parity(program, version, event, night, equal, checked_at) VALUES("
                           "'EVL-ERN-READ-O1', 2, ?, ?, ?, ?)", (f"8k:{i}", night.isoformat(), equal, S.iso(now)))
        SCO.latch(self.st, night, {"program": "EVL-ERN-READ-O1", "version": 2, "event": "8k:2"}, at(night, 1, 0))
        check = self.check("evl_score_parity", now)
        self.assertTrue(check["stalled"], check["what"])
        self.assertIn("the batched score is OFF", check["what"])
        self.assertIn("score-unlatch", check["what"])
        self.assertIn("2 of 3 sampled intents equal", check["what"])
        self.assertEqual((check["numbers"]["checked"], check["numbers"]["equal"], check["numbers"]["night"]),
                         (3, 2, night.isoformat()))
        self.assertEqual(check["onset"], at(night, 1, 0).timestamp())
        self.assertIsNone(check["owner_step"], "the House's and the captain's, never the owner's")
        SCO.unlatch(self.st)
        self.assertFalse(self.check("evl_score_parity", now)["stalled"])


class ThePxStoreAlarm(LaneCase):
    """`evl_px_store`: px.sqlite at or over its 2 GB line, or (the recorders on) the state disk under the PX floor."""

    def room(self, free):
        patch = mock.patch.object(PXS, "disk_free", return_value=free)
        patch.start()
        self.addCleanup(patch.stop)

    def test_not_judged_while_off_with_no_store(self):
        self.room(100 * GB)
        got = self.check("evl_px_store", at(dt.date(2026, 10, 30), 2, 0))
        self.assertFalse(got["judged"])
        self.assertIn("events.px_data", got["what"])

    def test_room_on_the_floor_and_over_the_line(self):
        now = at(dt.date(2026, 10, 30), 2, 0)
        self.room(100 * GB)
        quiet = self.check("evl_px_store", now, PX_ON)
        self.assertEqual((quiet["stalled"], quiet["judged"]), (False, True), quiet["what"])
        self.assertEqual(quiet["numbers"]["floor_gb"], 5.0, "the swarm guard's 3 GB and 2 GB more")
        self.room(int(4.5 * GB))
        low = self.check("evl_px_store", now, PX_ON)
        self.assertTrue(low["stalled"])
        self.assertIn("the state disk has 4.5 GB free, under the PX floor of 5.0 GB", low["what"])
        self.assertFalse(self.check("evl_px_store", now)["judged"], "the recorders off and no px.sqlite: nothing writes")
        self.room(None)
        self.assertIn("could not be read", self.check("evl_px_store", now, PX_ON)["what"])
        self.room(100 * GB)
        with PXS.PxStore(self.root / "events") as px:
            px.set_meta("x", "y")
        size = PXS.stored_bytes(self.root / "events")
        with mock.patch.object(PXS, "MAX_BYTES", size):
            over = self.check("evl_px_store", now)
            self.assertTrue(over["stalled"], "over its line, recorders on or off")
            self.assertIn("at or over its", over["what"])
        self.assertFalse(self.check("evl_px_store", now)["stalled"])

    def test_the_stall_job_names_both_new_causes_and_the_gateway_words_them(self):
        source = (Path(__file__).resolve().parents[2] / "gateway" / "lib" / "email.mjs").read_text()
        for cause in ("evl_score_parity", "evl_px_store"):
            self.assertIn(cause, ST.CAUSES)
            self.assertIn(cause, EV.CAUSES)
            self.assertIn(f"\n  {cause}: '", source)
            self.assertIn(cause, EV.DOING)


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
        self.assertFalse(line["latched"])
        SCO.latch(self.st, night, {"program": "EVL-ERN-READ-O1", "version": 2, "event": "8k:x"}, at(night, 1, 0))
        self.assertTrue(DR.settle_line(RP.settle_pace(self.st, night))["latched"], "the latch in the mail's facts")
        self.assertIn("THE BATCHED SCORE IS OFF: a parity flag 0 latched it", RP.render(RP.build(
            self.st, night, now=at(night, 23, 0) + dt.timedelta(days=1))))
        SCO.unlatch(self.st)
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


class ThePxLine(LaneCase):
    def test_the_px_line_sizes_free_space_and_the_days_runs(self):
        day = dt.date(2026, 10, 30)
        with mock.patch.object(PXS, "disk_free", return_value=int(41.2 * GB)):
            off = DR.px_line(CTX, self.root, day)
            self.assertEqual(off, {"on": False, "size_mb": None, "line_mb": None, "free_gb": None, "floor_gb": None,
                                   "ok": None, "runs": {k: None for k in DR.PX_STATUSES}},
                             "off and no px.sqlite: nothing, in the one shape")
            with PXS.PxStore(self.root / "events") as px:
                for status in ("ok", "ok", "partial", "disk"):
                    run = px.start_run("daily", now=at(day, 14, 0), free_bytes=int(41.2 * GB))
                    px.finish_run(run, status, now=at(day, 14, 1))
                run = px.start_run("daily", now=at(day, 2, 0))     # 22:00 ET of the day before: another New York day
                px.finish_run(run, "failed", now=at(day, 2, 1))
            line = DR.px_line(PX_ON, self.root, day)
        self.assertTrue(line["on"])
        self.assertEqual((line["line_mb"], line["free_gb"], line["floor_gb"], line["ok"]), (2048.0, 41.2, 5.0, True))
        self.assertGreater(line["size_mb"], 0)
        self.assertEqual(line["runs"], {"ok": 2, "partial": 1, "waiting": 0, "cut": 0, "failed": 0, "disk": 1})
        with PXS.PxStore(self.root / "events") as px:
            row = dict(px.db.execute("SELECT * FROM px_runs WHERE status='disk'").fetchone())
        self.assertEqual(row["free_bytes"], int(41.2 * GB), "px_runs carries the free space at the run's start")
        self.assertGreater(row["size_bytes"], 0, "... and px.sqlite's size at its end")
        fixture = json.loads((Path(__file__).resolve().parent / "fixtures" / "daily_report.json").read_text())
        self.assertEqual(set(fixture["px_store"]), set(line), "the gateway's fixture is the House's shape")
        self.assertEqual(set(fixture["px_store"]["runs"]), set(DR.PX_STATUSES))


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
