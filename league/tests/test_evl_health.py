"""Release 1019c (the review of r1/alarms, its majors 2 and 3 and its STOP/PAUSE minor; the owner's goal of Oct 19, 2026,
item 5): the event lane's own stall causes (league/ops/evl_health.py) judge PROGRESS, never a receipt's status alone:
`evl_record` (a clean pass: its 8-K, Form 4 and news reads without error, the failing feed named), `evl_decide` (a
decision not made in its window: missing, failed, cut, unfinished), `evl_verdicts` (needed verdicts unanswered past their
decision, the close decision's reading programs included, through run.py's own tally) and `evl_score` (intents due by the
latest session still open after its passes), each quiet while the lane is idle by design (events/STOP, the House's
PAUSE, a weekend); the stall job's research switch and its cheap-day rule. Synthetic stores only: every event, verdict,
intent and receipt here is invented, and no market price is read."""
import datetime as dt
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

from league.events import calendar as C
from league.events import programs as P
from league.events import run as R
from league.events import store as ES
from league.ops import evl_health as EV
from league.ops import stall as ST
from league.ops.context import Context
from league.tests.test_ops_stall import Base as StallBase

NY = ZoneInfo("America/New_York")
UTC = dt.timezone.utc
MON, TUE, WED = dt.date(2026, 10, 19), dt.date(2026, 10, 20), dt.date(2026, 10, 21)

#: A record pass as the House's lane writes it (league/events/house.py `_record_steps`): one block per read, no error.
CLEAN = {"8-K": {"new": 2, "fetched": 2, "failed": 0, "unlisted": 0}, "4": {"new": 5, "fetched": 5, "failed": 0, "unlisted": 0},
         "news": {"seen": 3, "stored": 3}, "cut": False, "verdicts": []}


def et(day: dt.date, hhmm: str) -> float:
    h, m = (int(x) for x in hhmm.split(":"))
    return dt.datetime.combine(day, dt.time(h, m), tzinfo=NY).timestamp()


def iso(epoch: float) -> str:
    return ES.iso(dt.datetime.fromtimestamp(epoch, UTC))


#: The weekdays a test's daily-index backfill reaches (league/events/house.py `BACKFILL_WEEKDAYS` before Oct 19-23).
REACH = tuple(dt.date(2026, 10, d) for d in (14, 15, 16, 19, 20, 21, 22))


def backfill_done(st: ES.Store, days=REACH) -> None:
    """Every weekday of `days` backfilled from the daily index (the lane's meta `evl:backfill:<day>` "done", as
    league/events/house.py `_backfill` writes it; release 1019f's `evl_backfill` judges it)."""
    for day in days:
        st.set_meta(f"evl:backfill:{day.isoformat()}", "done")


def blocks(**over) -> dict:
    """CLEAN with some blocks replaced (a block given as None is left out)."""
    out = {k: dict(v) if isinstance(v, dict) else v for k, v in CLEAN.items()}
    for key, value in over.items():
        key = {"k8": "8-K", "f4": "4"}.get(key, key)
        if value is None:
            out.pop(key, None)
        else:
            out[key] = value
    return out


class Lane(unittest.TestCase):
    """A House state root with the lane's store (`<root>/events/events.sqlite`), receipts written by hand."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "state"
        self.root.mkdir()
        self.st = ES.Store(self.root / "events")
        self.addCleanup(self.st.close)

    def receipt(self, job: str, started: float, *, finished: float | None = -1.0, status: str = "ok",
                summary: dict | None = None) -> None:
        end = started + 30 if finished == -1.0 else finished
        self.st.db.execute("INSERT INTO receipts(job, started_at, finished_at, status, summary) VALUES(?, ?, ?, ?, ?)",
                           (job, iso(started), None if end is None else iso(end), status, json.dumps(summary or {})))

    def record(self, at: float, summary: dict | None = None, status: str = "ok") -> None:
        self.receipt("record", at - 20, finished=at, status=status, summary=CLEAN if summary is None else summary)

    def intent(self, event: str, exit_day: dt.date, status: str = "planned", symbol: str = "XYZ") -> None:
        self.st.db.execute("INSERT INTO intents(program, version, event, symbol, cik, decided_at, entry_day, entry_at, "
                           "exit_day, exit_at, mode, status) VALUES('EVL-ERN-READ-O1', 2, ?, ?, '0000000009', ?, ?, "
                           "'open', ?, 'close', 'shadow', ?)",
                           (event, symbol, iso(et(exit_day, "09:15")), exit_day.isoformat(), exit_day.isoformat(), status))

    def ctx(self, *, enabled: bool = True, settings: dict | None = None) -> dict:
        return {"config": {"events": {"enabled": enabled}}, "settings": settings or {}}

    def check(self, cause: str, now: float, *, idle=None, line=None, **kw) -> dict:
        errors: list[str] = []
        out = EV.checks(self.ctx(**kw), self.root, now, errors=errors, idle=idle, line=line)
        self.errors = errors
        return out[cause]


class WhenJudged(Lane):
    def test_off_on_the_house_or_switched_off_is_not_judged(self):
        now = et(TUE, "12:00")
        for cause in EV.CAUSES:
            off = self.check(cause, now, enabled=False)
            self.assertEqual((off["stalled"], off["judged"]), (False, False), cause)
            self.assertIn("does not run on the House (league/config.json events.enabled)", off["what"])
            switched = self.check(cause, now, settings={"stall": {"evl": False}})
            self.assertIn("switched off (ops.json stall.evl is false)", switched["what"])
        self.assertEqual(EV.checks({}, self.root, now)["evl_record"]["judged"], False, "no config: the lane is off")
        self.assertEqual(ST.CAUSES[-15:-4], EV.CAUSES, "the eleven (release 1019f: A84's evl_final after evl_fills, then "
                         "evl_entries, evl_backfill and evl_handback; release 1019i: the attempts ledger's evl_fill_rate "
                         "and evl_attempts), before the equity lanes' own four")

    def test_a_lane_switched_on_with_no_store_has_recorded_nothing(self):
        empty = Path(self.tmp.name) / "bare"
        empty.mkdir()
        out = EV.checks(self.ctx(), empty, et(TUE, "12:00"))
        self.assertTrue(out["evl_record"]["stalled"])
        self.assertIn("finished no record pass on record", out["evl_record"]["what"])

    def test_an_unreadable_store_is_not_judged_and_said(self):
        self.st.close()
        (self.root / "events" / "events.sqlite").write_bytes(b"not a database at all" * 10)
        for name in ("events.sqlite-wal", "events.sqlite-shm"):
            (self.root / "events" / name).unlink(missing_ok=True)
        errors: list[str] = []
        out = EV.checks(self.ctx(), self.root, et(TUE, "12:00"), errors=errors)
        self.assertTrue(all(not c["stalled"] and c["judged"] is False for c in out.values()))
        self.assertEqual(errors, ["the event lane's store could not be read (DatabaseError): its causes are not judged"])

    def test_the_lanes_stop_file_idles_all_four_and_excuses_its_window(self):
        """events/STOP idles the lane by design (league/events/house.py): nothing is judged while it stands, nor for the
        lane's first half hour after it goes; a decision whose window fell inside it is excused for good."""
        now = et(TUE, "10:20")
        (self.root / "events" / "STOP").write_text("maintenance")
        os.utime(self.root / "events" / "STOP", (now - 3600, now - 3600))  # placed at 09:20 ET
        idle = EV.idle_windows(None, self.root, now)
        self.assertIsNone(idle["stop"][-1][1])
        for cause in EV.CAUSES:
            check = self.check(cause, now, idle=idle)
            self.assertEqual((check["stalled"], check["judged"]), (False, False), cause)
            self.assertIn("the lane is stopped by events/STOP", check["what"])
        (self.root / "events" / "STOP").unlink()
        idle = EV.idle_windows(idle, self.root, now + 600)
        self.assertEqual(idle["stop"][-1][1], now + 600, "a window open at the last run and gone now ends now")
        self.assertIn("came back from events/STOP", self.check("evl_record", now + 900, idle=idle)["what"])
        later = now + 3600
        self.record(later - 60)
        self.assertFalse(self.check("evl_record", later, idle=idle)["stalled"])
        decide = self.check("evl_decide", later, idle=idle)
        self.assertEqual(decide["numbers"]["excused_stop"], 1, "the 09:15 decision fell inside the STOP: excused")
        self.assertEqual(decide["numbers"]["missed"], 1, "Monday's close was before the STOP: missed all the same")
        self.receipt("decide-close:2026-10-19", et(MON, "15:47"))
        self.assertFalse(self.check("evl_decide", later, idle=idle)["stalled"])
        self.assertTrue(self.check("evl_decide", later)["stalled"], "with no STOP on record it is a missed decision")


class Record(Lane):
    def test_no_clean_record_pass_in_thirty_minutes(self):
        now = et(TUE, "03:00")  # round the clock: the news recorder never sleeps
        self.assertTrue(self.check("evl_record", now)["stalled"], "none on record")
        self.record(now - 12 * 60)
        fresh = self.check("evl_record", now)
        self.assertFalse(fresh["stalled"])
        self.assertEqual((fresh["numbers"]["passes_30m"], fresh["numbers"]["clean_30m"], fresh["numbers"]["failing"]),
                         (1, 1, "none"))
        late = self.check("evl_record", now + 25 * 60)
        self.assertTrue(late["stalled"])
        self.assertEqual((late["numbers"]["minutes_since_clean"], late["onset"]), (37.0, now - 12 * 60))
        self.assertIn("finished no clean record pass in the last 30 minutes", late["what"])
        self.assertIsNone(late["owner_step"])

    def test_an_ok_pass_whose_reads_all_failed_is_no_progress(self):
        """The review's probe: three hours of `ok` passes with EDGAR's two feeds at HTTP 403 and the news failing stood on
        no cause. Each such pass is no clean pass, and the cause names the feeds."""
        now = et(TUE, "13:00")
        self.record(now - 4 * 3600)  # the last clean pass, four hours ago
        broken = blocks(k8={"error": "GatewayError: HTTP 403"}, f4={"error": "GatewayError: HTTP 403"},
                        news={"error": "GatewayError: HTTP 403"})
        for minutes in range(180, 0, -2):
            self.record(now - minutes * 60, broken)
        check = self.check("evl_record", now)
        self.assertTrue(check["stalled"])
        self.assertEqual(check["numbers"]["failing"], "8k,form4,news")
        self.assertEqual((check["numbers"]["passes_30m"], check["numbers"]["clean_30m"]), (15, 0))
        self.assertIn("the 8-K feed and the Form 4 feed and the news could not be read", check["what"])
        self.assertIn("the last clean one ended", check["what"])

    def test_each_read_on_its_own_and_what_is_no_error(self):
        now = et(TUE, "13:00")
        cases = {
            "news": blocks(news={"error": "GatewayError: HTTP 401"}),
            "form4": blocks(f4={"error": "URLError"}),
            "8k": blocks(k8={"new": 3, "fetched": 0, "failed": 3, "unlisted": 0}),     # the feed reads, no document does
            "8k,news": blocks(k8=None, news={"error": "x"}),                            # a read missing from the pass
        }
        for name, summary in cases.items():
            self.st.db.execute("DELETE FROM receipts")
            self.record(now - 5 * 60, summary)
            check = self.check("evl_record", now)
            self.assertEqual((check["stalled"], check["numbers"]["failing"]), (True, name), name)
        self.st.db.execute("DELETE FROM receipts")
        self.record(now - 5 * 60, {**CLEAN, "tickers": {"error": "URLError: no tickers copy"}})
        self.assertEqual(self.check("evl_record", now)["numbers"]["failing"], "8k", "no tickers copy: no 8-K fetched")
        # A news read cut by its bound, a partial fetch and a pass with nothing new are all clean.
        for summary in (blocks(news={"cut": True}), blocks(k8={"new": 4, "fetched": 3, "failed": 1, "unlisted": 0}),
                        blocks(k8={"new": 0, "fetched": 0, "failed": 0, "unlisted": 0})):
            self.st.db.execute("DELETE FROM receipts")
            self.record(now - 5 * 60, summary)
            self.assertFalse(self.check("evl_record", now)["stalled"], summary)

    def test_failed_and_unfinished_passes_never_count(self):
        now = et(TUE, "10:00")
        self.receipt("record", now - 20 * 60, status="running", finished=None, summary=CLEAN)
        self.receipt("record", now - 10 * 60, status="failed", summary={"error": "LaneDeadline"})
        check = self.check("evl_record", now)
        self.assertTrue(check["stalled"])
        self.assertEqual(check["numbers"]["failed_30m"], 1)
        self.assertIn("its passes failed", check["what"])


class Decide(Lane):
    def test_a_decision_not_made_in_its_window(self):
        early = self.check("evl_decide", et(TUE, "09:24"))
        self.assertEqual(early["numbers"]["first_missed"], "close:2026-10-19", "the 09:15 is not due until 09:25")
        self.assertEqual(early["numbers"]["decisions_due"], 1)
        now = et(TUE, "09:26")
        check = self.check("evl_decide", now)
        self.assertTrue(check["stalled"])
        self.assertEqual((check["numbers"]["decisions_due"], check["numbers"]["missed"]), (2, 2))
        self.assertIn("close decision of 2026-10-19 (15:46 ET) was not made in its 10-minute window: it was never started",
                      check["what"])
        self.receipt("decide-close:2026-10-19", et(MON, "15:47"))
        self.receipt("decide-open:2026-10-20", et(TUE, "09:15"), status="pending", summary={"pending": {"EVL-ERN-READ-O1": 2}})
        self.assertFalse(self.check("evl_decide", now)["stalled"], "pending is made: its verdicts are evl_verdicts'")

    def test_failed_or_cut_in_the_window_and_decided_later_still_stands(self):
        """A live decision cut by the lane's bound and never finished in its window missed its auction: decided later it
        is in the shadow record only, and the cause says so."""
        self.receipt("decide-close:2026-10-19", et(MON, "15:47"))
        self.receipt("decide-open:2026-10-20", et(TUE, "09:15"), status="failed", summary={"why": "GatewayError: 429"})
        self.receipt("decide-open:2026-10-20", et(TUE, "09:16"), status="ok")  # failed, then a minute later: made
        self.assertFalse(self.check("evl_decide", et(TUE, "09:40"))["stalled"])
        self.st.db.execute("DELETE FROM receipts WHERE job='decide-open:2026-10-20'")
        self.receipt("decide-open:2026-10-20", et(TUE, "09:15"), status="cut", summary={"why": "the lane's time bound"})
        self.receipt("decide-open:2026-10-20", et(TUE, "09:31"), status="ok")  # a backfill
        check = self.check("evl_decide", et(TUE, "09:40"))
        self.assertTrue(check["stalled"])
        self.assertEqual((check["numbers"]["first_state"], check["numbers"]["decided_later"]), ("cut", 1))
        self.assertIn("it was cut by the lane's time bound; it was decided later, for the shadow record only", check["what"])
        self.assertEqual(check["onset"], et(TUE, "09:25"))
        self.st.db.execute("DELETE FROM receipts WHERE job='decide-open:2026-10-20'")
        self.receipt("decide-open:2026-10-20", et(TUE, "09:15"), status="running", finished=None)
        self.assertEqual(self.check("evl_decide", et(TUE, "09:40"))["numbers"]["first_state"], "unfinished")
        # Started in its window and finished after it (09:27): the real-money decision had already gone without it.
        self.st.db.execute("DELETE FROM receipts WHERE job='decide-open:2026-10-20'")
        self.receipt("decide-open:2026-10-20", et(TUE, "09:24"), finished=et(TUE, "09:27"))
        late = self.check("evl_decide", et(TUE, "09:40"))
        self.assertEqual((late["stalled"], late["numbers"]["first_state"]), (True, "late"))
        self.assertIn("it finished after its window", late["what"])
        # A day later the missed decision has left the look-back.
        self.receipt("decide-close:2026-10-20", et(TUE, "15:47"))
        self.receipt("decide-open:2026-10-21", et(WED, "09:15"))
        self.assertFalse(self.check("evl_decide", et(WED, "09:40"))["stalled"])

    def test_an_early_close_moves_the_close_decision_and_the_weekend_has_none(self):
        friday = dt.date(2026, 11, 27)  # the day after Thanksgiving: a 13:00 close
        self.receipt("decide-close:2026-11-25", et(dt.date(2026, 11, 25), "15:47"))
        self.receipt("decide-open:2026-11-27", et(friday, "09:15"))
        check = self.check("evl_decide", et(friday, "12:57"))
        self.assertEqual((check["numbers"]["first_missed"], check["numbers"]["missed"]), ("close:2026-11-27", 1),
                         "12:46 + 10 minutes")
        self.assertFalse(self.check("evl_decide", et(friday, "12:55"))["stalled"], "not due before 12:56")
        self.receipt("decide-close:2026-11-27", et(friday, "12:47"))
        sunday = self.check("evl_decide", et(dt.date(2026, 11, 29), "12:00"))
        self.assertEqual((sunday["stalled"], sunday["numbers"]["decisions_due"]), (False, 0))

    def test_the_decisions_judged_are_the_programs_own_rows(self):
        opens = tuple(p for p in P.PROGRAMS if p.entry_at == "open")
        with mock.patch.object(P, "PROGRAMS", opens):
            self.assertEqual(EV.entry_kinds(), ("open",))
            self.assertEqual(self.check("evl_decide", et(TUE, "09:26"))["numbers"]["decisions_due"], 1)
        self.assertEqual(EV.entry_kinds(), ("open", "close"))


class Verdicts(Lane):
    def tally(self, at: float, needed: int, answered: int, status: str = "ok", job: str = "decide-open:2026-10-20"):
        self.receipt(job, at, status=status, summary={"verdicts": {"needed": needed, "answered": answered}})

    def test_needed_verdicts_unanswered_past_the_decision(self):
        self.tally(et(MON, "15:47"), 0, 0, job="decide-close:2026-10-19")
        self.assertIn("No verdict a decision of the last 24 h needed is unanswered", self.check("evl_verdicts", et(TUE, "09:26"))["what"])
        for minute in ("09:15", "09:20", "09:25"):
            self.tally(et(TUE, minute), 10, 7, status="pending")
        early = self.check("evl_verdicts", et(TUE, "09:26"))
        self.assertFalse(early["stalled"], "11 minutes past: the lane is still asking")
        check = self.check("evl_verdicts", et(TUE, "09:31"))
        self.assertTrue(check["stalled"])
        self.assertEqual((check["numbers"]["unanswered"], check["numbers"]["needed"], check["numbers"]["first_held"]),
                         (3, 10, "open:2026-10-20"))
        self.assertIn("3 verdicts the event lane's open decision of 2026-10-20 needs have no answer 16 minutes past it",
                      check["what"])
        self.tally(et(TUE, "09:32"), 10, 10)  # every verdict stored: decided, and the latest receipt is the one read
        self.assertFalse(self.check("evl_verdicts", et(TUE, "09:40"))["stalled"])

    def test_a_redecision_that_finds_new_verdicts_is_judged_from_its_own_start(self):
        self.tally(et(TUE, "09:15"), 8, 8)
        self.tally(et(TUE, "11:40"), 9, 8, status="pending")  # the hourly re-decision found a late event's verdict
        self.assertFalse(self.check("evl_verdicts", et(TUE, "11:50"))["stalled"], "10 minutes into its own run")
        self.assertTrue(self.check("evl_verdicts", et(TUE, "11:56"))["stalled"])

    def test_a_receipt_from_before_the_tally_is_read_by_its_pending_counts(self):
        """Release 1019b's receipts carry `pending` (each program's waiting events) and no tally: they are judged too."""
        self.receipt("decide-open:2026-10-20", et(TUE, "09:15"), status="pending",
                     summary={"pending": {"EVL-ERN-READ-O1": 2, "EVL-ERN-READ-O1@v2": 2}})
        check = self.check("evl_verdicts", et(TUE, "09:40"))
        self.assertTrue(check["stalled"])
        self.assertEqual((check["numbers"]["unanswered"], check["numbers"]["needed"]), (4, 0))

    def test_the_houses_pause_holds_verdicts_by_design(self):
        self.tally(et(TUE, "09:15"), 10, 2, status="pending")
        (self.root / "PAUSE").write_text("maintenance")
        os.utime(self.root / "PAUSE", (et(TUE, "09:00"), et(TUE, "09:00")))
        idle = EV.idle_windows(None, self.root, et(TUE, "09:50"))
        held = self.check("evl_verdicts", et(TUE, "09:50"), idle=idle)
        self.assertEqual((held["stalled"], held["judged"]), (False, False))
        self.assertIn("the House is paused (PAUSE)", held["what"])
        self.assertFalse(self.check("evl_record", et(TUE, "09:50"), idle=idle)["judged"] is False, "the rest is judged")
        (self.root / "PAUSE").unlink()
        idle = EV.idle_windows(idle, self.root, et(TUE, "10:20"))
        self.assertIn("PAUSE ended under 30 minutes ago", self.check("evl_verdicts", et(TUE, "10:30"), idle=idle)["what"])
        self.tally(et(TUE, "10:40"), 10, 2, status="pending")
        check = self.check("evl_verdicts", et(TUE, "10:51"), idle=idle)
        self.assertTrue(check["stalled"])
        self.assertEqual(check["numbers"]["unanswered_since"], iso(et(TUE, "10:20")),
                         "counted from the pause's end, not from 09:15")
        self.tally(et(TUE, "10:52"), 10, 10)
        self.assertFalse(self.check("evl_verdicts", et(TUE, "10:55"), idle=idle)["stalled"])

    def test_the_lanes_line_reached_is_said(self):
        self.tally(et(TUE, "09:15"), 40, 25, status="pending")
        check = self.check("evl_verdicts", et(TUE, "09:45"), line={"line_usd": 3.0, "spent_usd": 3.004})
        self.assertTrue(check["stalled"])
        self.assertEqual((check["numbers"]["verdict_line_usd"], check["numbers"]["at_line"]), (3.0, True))
        self.assertIn("the lane's verdict line for the day is reached", check["what"])


class TheStallJobsLine(Lane):
    """The verdict line the stall job states (`verdict_line`) is the House's own (league/events/house.py `verdict_line`
    and `_spend_today`): the lower of `events.verdict_usd_day` (the House's own default when the key is unset) and the
    budget's allowance, and the UTC day's verdict dollars (the day every line is held on), a verdict with no stated cost
    at the House's figure."""

    def test_the_line_and_the_days_dollars_are_the_houses(self):
        from league.events import house as H
        from league.ops import budget as B

        now = et(TUE, "12:00")
        bare = {"config": {"events": {"enabled": True}}}
        line = EV.verdict_line(bare, self.root, now)
        self.assertEqual(line["line_usd"], min(H.VERDICT_USD_DAY, B.floor_lane_usd_day()), "no budget.json: the floor")
        self.assertEqual(line["spent_usd"], 0.0)
        low = EV.verdict_line({"config": {"events": {"enabled": True, "verdict_usd_day": 0.5}}}, self.root, now)
        self.assertEqual(low["line_usd"], 0.5, "a config below the allowance holds")
        for event, at, usd in (("e0", et(MON, "19:59"), 4.0),     # Monday in UTC (23:59Z): not Tuesday's
                               ("e1", et(MON, "23:59"), 0.25),    # Tuesday in UTC (03:59Z), Monday in New York: Tuesday's
                               ("e2", et(TUE, "00:01"), 0.002),
                               ("e3", et(TUE, "11:00"), None),     # no stated cost: the House's figure
                               ("e4", et(TUE, "20:00"), 0.5)):     # 00:00Z Wednesday: Wednesday's
            self.st.db.execute("INSERT INTO verdicts(event, prompt_sha, model, asked_at, answered_at, status, usd) "
                               "VALUES(?, 'p', 'm', ?, ?, 'ok', ?)", (event, iso(at), iso(at), usd))
        self.assertAlmostEqual(EV.verdict_line(bare, self.root, now)["spent_usd"], 0.25 + 0.002 + H.VERDICT_USD_UNKNOWN,
                               places=9)
        # The House's lane counts the same day (league/events/house.py `verdict_day`).
        day, (lo, hi) = H.verdict_day(dt.datetime.fromtimestamp(now, UTC))
        self.assertEqual((day, lo, hi), (TUE, "2026-10-20T00:00:00Z", "2026-10-21T00:00:00Z"))


class CloseDecisionTally(unittest.TestCase):
    """The review of r1/alarms, its major 3, end to end: the close decision's needed and unanswered verdict sets, of
    PREREG-EVL-2's close-entry reading program (NEWS-READ-ON, versions 1 and 2), written by league/events/run.py's own
    `decide_close` into its receipt, reach `evl_verdicts`."""

    def setUp(self):
        from league.tests.test_events_run import sec_pages
        from league.tests.test_events_wave2 import DayGateway

        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "state"
        self.st = ES.Store(self.root / "events")
        self.addCleanup(self.st.close)
        self.now = dt.datetime(2026, 10, 19, 19, 46, tzinfo=UTC)
        self.gw = DayGateway({"AAA": 3, "BBB": 1}, {"AAA": 21.0, "BBB": 20.5})
        self.ctx = R.Context(self.st, self.gw, sec_pages, now=lambda: self.now)
        C.refresh(self.st, self.gw, dt.date(2026, 8, 1), dt.date(2026, 12, 31))
        self.st.set_meta("tickers@2026-10-19T01:05:00Z", self.st.put_document(sec_pages("x/company_tickers.json"), "t"))
        pinned = P.REGISTERED_AT
        P.REGISTERED_AT = "2026-10-19T01:00:00Z"
        self.addCleanup(setattr, P, "REGISTERED_AT", pinned)
        for nid, symbol, hour in (("n1", "AAA", 14), ("n3", "BBB", 16)):
            knowable = dt.datetime(2026, 10, 19, hour, 0, tzinfo=UTC)
            created = knowable - dt.timedelta(minutes=2)
            self.st.db.execute("INSERT INTO news(id, created_at, updated_at, received_at, knowable_at, source, headline, "
                               "summary, symbols, live) VALUES(?, ?, ?, ?, ?, 'benzinga', 'h', 's', ?, 1)",
                               (nid, ES.iso(created), ES.iso(created), ES.iso(created), ES.iso(knowable), json.dumps([symbol])))
        self.answer = self.gw.post_json

    def test_a_close_entry_reading_program_waiting_stands_on_evl_verdicts(self):
        self.gw.post_json = lambda path, body, headers=None: (503, {"error": "upstream"})
        out = R.decide_close(self.ctx, dt.date(2026, 10, 19))
        self.assertIn("EVL-NEWS-READ-ON@v2", out["pending"])
        self.assertEqual(out["verdicts"], {"needed": 2, "answered": 0})
        ctx = {"config": {"events": {"enabled": True}}, "settings": {}}
        at = self.now.timestamp()
        quiet = EV.checks(ctx, self.root, at + 10 * 60)["evl_verdicts"]
        self.assertFalse(quiet["stalled"], "the close decision's window has not ended (15:56 ET)")
        check = EV.checks(ctx, self.root, at + 16 * 60)["evl_verdicts"]
        self.assertTrue(check["stalled"], check["what"])
        self.assertEqual((check["numbers"]["first_held"], check["numbers"]["unanswered"], check["numbers"]["needed"]),
                         ("close:2026-10-19", 2, 2))
        self.gw.post_json = self.answer
        self.now = self.now + dt.timedelta(minutes=17)
        R.decide_close(self.ctx, dt.date(2026, 10, 19))
        self.assertFalse(EV.checks(ctx, self.root, at + 20 * 60)["evl_verdicts"]["stalled"], "answered: decided")


class Score(Lane):
    def test_intents_still_open_after_the_nights_passes(self):
        """The review's probe: Monday's score `ok` with every settlement raising left 12 intents entered at 12:20 ET the
        next day, and nothing stood. Now the intents themselves are judged."""
        before = self.check("evl_score", et(TUE, "22:59"))
        self.assertEqual(before["numbers"]["day"], "2026-10-19", "Tuesday's 23:00 has not come")
        for i in range(12):
            self.intent(f"8k:{i}", TUE, status="entered" if i % 2 else "planned")
        self.receipt("score", et(TUE, "20:30"), status="ok", summary={"day": "2026-10-20", "complete": True, "due": 12,
                                                                      "settled": 0, "errors": 12})
        now = et(TUE, "23:20")
        check = self.check("evl_score", now)
        self.assertTrue(check["stalled"])
        self.assertEqual((check["numbers"]["open_due"], check["numbers"]["last_pass_errors"], check["onset"]),
                         (12, 12, et(TUE, "23:00")))
        self.assertIn("12 intents due by the session of 2026-10-20 are still open after the night's score passes", check["what"])
        self.st.db.execute("UPDATE intents SET status='exited'")
        self.assertFalse(self.check("evl_score", now)["stalled"])

    def test_no_pass_at_all_and_an_exit_the_tape_showed_absent(self):
        self.intent("8k:a", TUE, symbol="AAA")
        self.intent("8k:b", TUE, symbol="BBB")
        now = et(TUE, "23:30")
        check = self.check("evl_score", now)
        self.assertTrue(check["stalled"])
        self.assertIn("no score pass ran after its close", check["what"])
        # BBB's closing print was absent on its exit day (PREREG-EVL-1 section 5: the next session's close): by design.
        self.st.db.execute("INSERT INTO marks(symbol, day, label, px, t, source, fetched_at) VALUES('BBB', ?, 'close', NULL, "
                           "NULL, 'none', ?)", (TUE.isoformat(), iso(now)))
        check = self.check("evl_score", now)
        self.assertEqual((check["numbers"]["open_due"], check["numbers"]["waiting_on_tape"]), (1, 1))
        self.st.db.execute("UPDATE intents SET status='exited' WHERE event='8k:a'")
        check = self.check("evl_score", now)
        self.assertFalse(check["stalled"])
        self.assertIn("1 the tape keeps waiting", check["what"])

    def test_an_intent_a_catch_up_decision_wrote_after_the_nights_pass_waits_for_the_next_pass(self):
        """Release 1019f's integration (Oct 21, 2026's false alarm): PREREG-EVL-4's rows decided by themselves for an
        older close once release 1019d went live wrote an intent due by Tuesday after Tuesday night's score pass had
        run. The next pass settles it; until then it is no stall (counted apart). An intent of a decision made before the
        pass still stands, and with no pass after the close nothing is excused."""
        self.intent("8k:new", TUE)
        self.intent("8k:old", TUE)
        self.st.db.execute("UPDATE intents SET program='EVL-CTRL-8K-ON', version=1, entry_at='close', "
                           "entry_day='2026-10-19' WHERE event='8k:new'")
        now = et(TUE, "23:30")
        self.assertTrue(self.check("evl_score", now)["stalled"], "no score pass after the close: nothing excused")
        self.receipt("score", et(TUE, "20:30"), status="ok", summary={"day": "2026-10-20", "complete": True})
        self.receipt("decide-close-evl4:2026-10-19", et(TUE, "21:10"),
                     summary={"EVL-CTRL-8K-ON": {"planned": 1, "skipped": 0, "known": 0}})
        check = self.check("evl_score", now)
        self.assertTrue(check["stalled"], "8k:old stands: its decision was made before the pass")
        self.assertEqual((check["numbers"]["open_due"], check["numbers"]["after_last_pass"]), (1, 1))
        self.st.db.execute("UPDATE intents SET status='exited' WHERE event='8k:old'")
        check = self.check("evl_score", now)
        self.assertFalse(check["stalled"])
        self.assertIn("1 a decision wrote after the night's last score pass (the next pass settles them)", check["what"])
        # the next night's pass that leaves it open: it stands then
        self.receipt("score", et(WED, "20:30"), status="ok", summary={"day": "2026-10-21", "complete": True})
        self.assertTrue(self.check("evl_score", et(WED, "23:30"))["stalled"])
        # a decision receipt that wrote nothing new for the key excuses nothing
        self.assertEqual(EV.written_after({"decide": {"decide-close-evl4:2026-10-19": [
            {"started_at": iso(et(TUE, "21:10")), "summary": json.dumps({"EVL-CTRL-8K-ON": {"planned": 0, "known": 1}})}]}},
            et(TUE, "20:30")), set())

    def test_a_night_with_nothing_due_is_no_stall(self):
        self.intent("8k:b", WED)  # due tomorrow
        self.intent("8k:c", TUE, status="exited")
        check = self.check("evl_score", et(TUE, "23:30"))
        self.assertEqual((check["stalled"], check["numbers"]["open_due"]), (False, 0))


class Fills(Lane):
    """The goal's "fill gaps": the lane's real fills beside the shadow's own auction prices (the House's event twins in the
    swarm store's kv `equity_twins`; league/ops/twins.py `event_twin`), the signed mean of a side over the last 20."""

    def twins(self, gaps):
        from league.swarm.store import SwarmStore

        store = SwarmStore(self.root)
        records = {f"eq:{i}": {"key": f"eq:{i}", "kind": "event", "status": "priced", "final": True,
                               "exit_day": f"2026-10-{10 + i // 5:02d}", "judged_at": f"2026-10-21T01:{i:02d}:00Z",
                               "entry_gap_bp": entry, "exit_gap_bp": exit_}
                   for i, (entry, exit_) in enumerate(gaps)}
        records["eq:999"] = {"key": "eq:999", "kind": "equity", "status": "priced", "entry_gap_bp": 900.0}  # not the lane's
        store.put("equity_twins", records)
        store.close()

    def test_not_judged_before_the_first_real_fill_is_priced(self):
        check = self.check("evl_fills", et(TUE, "12:00"))
        self.assertEqual((check["stalled"], check["judged"]), (False, False))
        self.assertIn("no real fill of the event lane is priced", check["what"])

    def test_a_side_worse_than_15_bp_over_the_last_20_stands(self):
        self.twins([(40.0, 0.0)] * 10 + [(18.0, 1.0)] * 20)   # the last 20 entries average 18 bp worse than the print
        check = self.check("evl_fills", et(TUE, "12:00"))
        self.assertTrue(check["stalled"])
        self.assertEqual((check["numbers"]["entry_n"], check["numbers"]["entry_mean_bp"], check["numbers"]["worse"],
                          check["numbers"]["off"], check["numbers"]["better"]), (20, 18.0, "entry", "entry", "none"))
        self.assertIn("the signed mean gap entry +18.0 bp over 20 (worse than the prints by more than 15 bp)", check["what"])
        self.assertIn("exit +1.0 bp over 20 (within 15 bp)", check["what"])
        self.twins([(14.0, -3.0)] * 20 + [(None, 2.0)] * 4)
        quiet = self.check("evl_fills", et(TUE, "12:00"))
        self.assertFalse(quiet["stalled"])
        self.assertEqual((quiet["numbers"]["entry_n"], quiet["numbers"]["exit_n"]), (20, 20))
        self.assertIn("entry +14.0 bp over 20 (within 15 bp); exit -2.0 bp over 20 (within 15 bp)", quiet["what"])
        self.twins([(90.0, 90.0)] * 4)                        # too few to judge
        few = self.check("evl_fills", et(TUE, "12:00"))
        self.assertFalse(few["stalled"])
        self.assertIn("entry +90.0 bp over 4 (too few to judge: 5 at least)", few["what"])
        self.assertNotIn("within", few["what"], "never 'within 15 bp' of a gap it could not judge")
        self.assertEqual(EV.fill_gaps([]), {"entry_n": 0, "entry_mean_bp": None, "exit_n": 0, "exit_mean_bp": None})

    def test_a_side_better_than_15_bp_stands_too_and_says_so(self):
        """The review of r2/alarms, its major 3: the Done item and PREREG-EVL-3 section 5 ask fills WITHIN 15 bp of the
        auction prints, the signed mean per side, either way (A50: the size of the mean gap). Fills 40 bp better than the
        shadow's prints say the fills or the shadow's prices are mis-measured: the cause stands and names the direction."""
        self.twins([(-40.0, -40.0)] * 20)
        check = self.check("evl_fills", et(TUE, "12:00"))
        self.assertTrue(check["stalled"])
        self.assertEqual((check["numbers"]["off"], check["numbers"]["better"], check["numbers"]["worse"]),
                         ("entry,exit", "entry,exit", "none"))
        self.assertIn("strayed from the shadow's auction prices", check["what"])
        self.assertIn("entry -40.0 bp over 20 (better than the prints by more than 15 bp)", check["what"])
        self.assertIn("exit -40.0 bp over 20 (better than the prints by more than 15 bp)", check["what"])
        self.assertNotIn("within", check["what"].replace("asks within 15 bp", ""))
        self.twins([(-16.0, 30.0)] * 20)                      # one side each way
        both = self.check("evl_fills", et(TUE, "12:00"))
        self.assertEqual((both["numbers"]["better"], both["numbers"]["worse"]), ("entry", "exit"))
        self.twins([(-15.0, 15.0)] * 20)                      # at the bound: within
        self.assertFalse(self.check("evl_fills", et(TUE, "12:00"))["stalled"])


class StallHarness(StallBase):
    """The stall job over a swarm store (league/tests/test_ops_stall.py's) and a lane store, the lane on the House."""

    def setUp(self):
        super().setUp()
        self.now_ = et(TUE, "12:20")
        self.health = {"kill_switch": False}

    def lane(self, *, record_ago_minutes=None):
        st = ES.Store(self.root / "events")
        try:
            backfill_done(st)   # (release 1019f: the daily-index backfill of the reach is done, so evl_backfill is quiet)
            if record_ago_minutes is not None:
                at = self.now_ - record_ago_minutes * 60
                st.db.execute("INSERT INTO receipts(job, started_at, finished_at, status, summary) VALUES('record', ?, ?, "
                              "'ok', ?)", (iso(at - 20), iso(at), json.dumps(CLEAN)))
        finally:
            st.close()

    def ctx(self, *, now=None, ceiling=20, binds=(), events=True, settings=None):
        now = self.now_ if now is None else now
        ctx = Context("stall", root=self.root, base=self.base, due_at=now,
                      config={"events": {"enabled": True}} if events else {}, clock=lambda: now,
                      settings_value=settings if settings is not None else {"stall": {"research": False}})
        ctx.notify = self.notify
        ctx.population_ceiling = ceiling
        ctx.binds = list(binds)
        ctx.lane_on = True  # the direction lane on (its report read), as the swarm's own settings say on the House
        ctx.health = lambda: self.health
        return ctx

    def record(self, at: float) -> None:
        st = ES.Store(self.root / "events")
        st.db.execute("INSERT INTO receipts(job, started_at, finished_at, status, summary) VALUES('record', ?, ?, 'ok', ?)",
                      (iso(at - 20), iso(at), json.dumps(CLEAN)))
        st.close()


class StallJob(StallHarness):
    """The four through the stall job: standing in its checks, mailed at its INFO pace, a House warning each."""

    def test_a_lane_that_records_nothing_is_mailed_at_once_as_info(self):
        self.lane()
        out = ST.run(self.ctx())
        self.assertIn("evl_record", out["stalled"])
        self.assertTrue(out["notice"]["sent"])
        entry = self.notify.entry("evl_record")
        self.assertIsNone(entry["owner_step"])
        self.assertEqual(self.notify.calls[-1]["notice_id"], "stall:info:" + "+".join(sorted(out["stalled"])))
        self.assertIn("evl_record", out["warned"])
        self.record(self.now_ + 1790)
        again = ST.run(self.ctx(now=self.now_ + 1800))
        self.assertIn("evl_record", again["cleared"])

    def test_the_stop_file_quiets_the_four_through_the_job_and_its_window_is_kept(self):
        self.lane()
        (self.root / "events" / "STOP").write_text("x")
        out = ST.run(self.ctx())
        self.assertFalse(set(EV.CAUSES) & set(out["stalled"]), out["stalled"])
        kept = json.loads((self.root / ST.STATE_FILE).read_text())["evl_idle"]
        self.assertIsNone(kept["stop"][-1][1])

    def test_the_research_switch_judges_no_research_cause_and_no_research_alarm(self):
        self.lane(record_ago_minutes=2)
        st = ES.Store(self.root / "events")
        for job, start in (("decide-open:2026-10-20", et(TUE, "09:15")), ("decide-close:2026-10-19", et(MON, "15:47"))):
            st.db.execute("INSERT INTO receipts(job, started_at, finished_at, status, summary) VALUES(?, ?, ?, 'ok', '{}')",
                          (job, iso(start), iso(start + 60)))
        st.close()
        on = ST.run(self.ctx(settings={}))
        self.assertTrue({"births", "gym_runs"} <= set(on["stalled"]), on["stalled"])
        self.notify.calls.clear()
        (self.root / ST.STATE_FILE).unlink()
        off = ST.run(self.ctx())
        self.assertEqual(off["stalled"], [], "research off: nothing stands, nothing is mailed")
        self.assertEqual(self.notify.calls, [])
        for cause in ST.RESEARCH_CAUSES:
            check = off["checks"][cause]
            self.assertTrue(check["what"].startswith("Not judged: "), cause)
            self.assertIn("research is switched off (ops.json stall.research is false)" if cause != "underspend"
                          else "a cheap day is never a failed day", check["what"], cause)
            self.assertEqual((check["stalled"], check["owner_step"], check["numbers"]["judged"]), (False, None, False))
        report = {"at": self.now_ - 600, "lane": {"mode": "gate"},
                  "alarms": [{"id": "A1", "level": "warning", "text": "A1: no direction birth"},
                             {"id": "A3", "level": "warning", "text": "A3: a cleared best waits"}], "k5": {}}
        (self.root / ST.DLANE_REPORT).write_text(json.dumps(report))
        quiet = ST.run(self.ctx(now=self.now_ + 60))
        self.assertNotIn("dlane", quiet["stalled"])
        self.assertEqual(quiet["checks"]["dlane"]["numbers"]["not_judged"], "a1,a3")
        report["alarms"].append({"id": "PL1", "level": "warning", "text": "PL1: a program's loss line"})
        (self.root / ST.DLANE_REPORT).write_text(json.dumps(report))
        loud = ST.run(self.ctx(now=self.now_ + 120))
        self.assertIn("dlane", loud["stalled"])
        self.assertEqual(loud["checks"]["dlane"]["numbers"]["alarms"], "pl1")

    def test_a_cheap_day_is_never_a_failed_day(self):
        self.lane(record_ago_minutes=2)
        out = ST.run(self.ctx(settings={}))
        self.assertFalse(out["checks"]["underspend"]["stalled"])
        self.assertIn("a cheap day is never a failed day", out["checks"]["underspend"]["what"])
        self.assertEqual(ST.CHEAP_DAY_RULE, 3)


if __name__ == "__main__":
    unittest.main()
