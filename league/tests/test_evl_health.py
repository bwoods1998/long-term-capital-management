"""Release R1 WP2 (the owner's goal of Oct 19, 2026, item 7): the event lane's own stall causes (league/ops/evl_health.py:
`evl_record`, `evl_decide`, `evl_verdicts`, `evl_score`), the stall job's research switch (ops.json `stall.research`), the
cheap-day rule (budget rule 3: no `underspend`) and the daily one-screen report riding the stall notice. Synthetic stores
only: every event, verdict, intent and outcome here is invented, and no market price is read."""
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

from league.events import calendar as C
from league.events import programs as P
from league.events import store as ES
from league.ops import evl_health as EV
from league.ops import stall as ST
from league.ops.context import Context
from league.tests.test_ops_stall import Base as StallBase

NY = ZoneInfo("America/New_York")
UTC = dt.timezone.utc
MON, TUE, WED = dt.date(2026, 10, 19), dt.date(2026, 10, 20), dt.date(2026, 10, 21)
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "stall_report.json"


def et(day: dt.date, hhmm: str) -> float:
    h, m = (int(x) for x in hhmm.split(":"))
    return dt.datetime.combine(day, dt.time(h, m), tzinfo=NY).timestamp()


def iso(epoch: float) -> str:
    return ES.iso(dt.datetime.fromtimestamp(epoch, UTC))


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

    def intent(self, event: str, exit_day: dt.date, status: str = "planned") -> None:
        self.st.db.execute("INSERT INTO intents(program, version, event, symbol, cik, decided_at, entry_day, entry_at, "
                           "exit_day, exit_at, mode, status) VALUES('EVL-ERN-READ-O1', 1, ?, 'XYZ', '0000000009', ?, ?, "
                           "'open', ?, 'close', 'shadow', ?)",
                           (event, iso(et(exit_day, "09:15")), exit_day.isoformat(), exit_day.isoformat(), status))

    def ctx(self, *, enabled: bool = True, settings: dict | None = None) -> dict:
        return {"config": {"events": {"enabled": enabled}}, "settings": settings or {}}

    def check(self, cause: str, now: float, **kw) -> dict:
        errors: list[str] = []
        out = EV.checks(self.ctx(**kw), self.root, now, errors=errors)
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
        self.assertEqual(ST.CAUSES[-8:-4], EV.CAUSES, "the four, before the equity lanes' own four")

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
        self.assertEqual(errors, ["the event lane's store could not be read (DatabaseError): its four causes are not judged"])


class Record(Lane):
    def test_no_record_pass_in_thirty_minutes(self):
        now = et(TUE, "03:00")  # round the clock: the news recorder never sleeps
        self.assertTrue(self.check("evl_record", now)["stalled"], "none on record")
        self.receipt("record", now - 12 * 60)
        fresh = self.check("evl_record", now)
        self.assertFalse(fresh["stalled"])
        self.assertEqual(fresh["numbers"]["passes_30m"], 1)
        late = self.check("evl_record", now + 25 * 60)
        self.assertTrue(late["stalled"])
        self.assertEqual((late["numbers"]["minutes_since_record"], late["onset"]), (36.5, now - 12 * 60 + 30))
        self.assertIn("finished no record pass in the last 30 minutes", late["what"])
        self.assertIsNone(late["owner_step"])

    def test_failed_passes_and_news_errors_are_counted_and_only_an_ok_pass_counts(self):
        now = et(TUE, "10:00")
        self.receipt("record", now - 20 * 60, status="running", finished=None)
        self.receipt("record", now - 10 * 60, status="failed")
        self.assertTrue(self.check("evl_record", now)["stalled"], "a pass that failed or never finished is none")
        self.receipt("record", now - 8 * 60, status="error: TimeoutError")
        self.receipt("record", now - 5 * 60, summary={"8-K": {"new": 3}, "news": {"error": "GatewayError: HTTP 403"}})
        check = self.check("evl_record", now)
        self.assertFalse(check["stalled"])
        self.assertEqual((check["numbers"]["failed_passes_30m"], check["numbers"]["news_errors_30m"]), (2, 1))
        self.receipt("record", now + 60, status="partial")  # a bounded pass that stopped at its 90 s finished all the same
        self.assertEqual(self.check("evl_record", now + 26 * 60)["numbers"]["passes_30m"], 1)
        self.assertFalse(self.check("evl_record", now + 26 * 60)["stalled"])
        self.assertIn("1 of the last 30 minutes' passes could not read the news", check["what"])


class Decide(Lane):
    def test_a_decision_not_done_ten_minutes_after_its_time(self):
        early = self.check("evl_decide", et(TUE, "09:24"))
        self.assertEqual(early["numbers"]["first_missed"], "close:2026-10-19", "the 09:15 is not due until 09:25")
        self.assertEqual(early["numbers"]["decisions_due"], 1)
        now = et(TUE, "09:26")
        check = self.check("evl_decide", now)
        self.assertTrue(check["stalled"])
        self.assertEqual((check["numbers"]["decisions_due"], check["numbers"]["missed"]), (2, 2))
        self.assertIn("close decision of 2026-10-19 (15:46 ET) is not done 10 minutes after its time", check["what"])
        self.receipt("decide-close:2026-10-19", et(MON, "15:46"))
        self.receipt("decide-open:2026-10-20", et(TUE, "09:15"), status="pending", summary={"pending": {"EVL-ERN-READ-O1": 2}})
        check = self.check("evl_decide", now)
        self.assertEqual((check["numbers"]["missed"], check["numbers"]["waiting_on_verdicts"]), (1, 1))
        self.assertIn("(it waits on verdicts)", check["what"])
        self.assertEqual(check["onset"], et(TUE, "09:15"))
        self.receipt("decide-open:2026-10-20", et(TUE, "09:22"))  # the verdicts came: a decision done late is done
        self.assertFalse(self.check("evl_decide", now)["stalled"])
        # A re-decision that waits on late events is no missed decision once one ran ok.
        self.receipt("decide-open:2026-10-20", et(TUE, "10:40"), status="pending")
        self.assertFalse(self.check("evl_decide", et(TUE, "11:00"))["stalled"])

    def test_an_early_close_moves_the_close_decision_and_the_weekend_has_none(self):
        friday = dt.date(2026, 11, 27)  # the day after Thanksgiving: a 13:00 close
        self.receipt("decide-close:2026-11-25", et(dt.date(2026, 11, 25), "15:46"))
        self.receipt("decide-open:2026-11-27", et(friday, "09:15"))
        check = self.check("evl_decide", et(friday, "12:57"))
        self.assertEqual((check["numbers"]["first_missed"], check["numbers"]["missed"]), ("close:2026-11-27", 1),
                         "12:46 + 10 minutes")
        self.assertFalse(self.check("evl_decide", et(friday, "12:55"))["stalled"], "not due before 12:56")
        self.receipt("decide-close:2026-11-27", et(friday, "12:46"))
        sunday = self.check("evl_decide", et(dt.date(2026, 11, 29), "12:00"))
        self.assertEqual((sunday["stalled"], sunday["numbers"]["decisions_due"]), (False, 0))

    def test_the_decisions_judged_are_the_programs_own_rows(self):
        """Programs are data rows (league/events/programs.py): the entry kinds come from them, so a wave of programs that
        needs a decision kind is judged with no code here."""
        opens = tuple(p for p in P.PROGRAMS if p.entry_at == "open")
        with mock.patch.object(P, "PROGRAMS", opens):
            self.assertEqual(EV.entry_kinds(), ("open",))
            self.assertEqual(self.check("evl_decide", et(TUE, "09:26"))["numbers"]["decisions_due"], 1)
        self.assertEqual(EV.entry_kinds(), ("open", "close"))


class Verdicts(Lane):
    def tally(self, at: float, needed: int, answered: int, status: str = "ok", job: str = "decide-open:2026-10-20"):
        self.receipt(job, at, status=status, summary={"verdicts": {"needed": needed, "answered": answered}})

    def test_over_a_fifth_of_the_days_verdicts_unanswered(self):
        now = et(TUE, "09:30")
        self.assertIn("carries a verdict tally yet", self.check("evl_verdicts", now)["what"])
        self.tally(et(TUE, "09:15"), 10, 7, status="pending")
        check = self.check("evl_verdicts", now)
        self.assertTrue(check["stalled"])
        self.assertEqual((check["numbers"]["needed"], check["numbers"]["unanswered"], check["numbers"]["unanswered_share"]),
                         (10, 3, 0.3))
        self.assertIn("3 of the 10 verdicts the event lane's decisions of 2026-10-20 needed have no answer (30%, over 20%)",
                      check["what"])
        self.tally(et(TUE, "09:20"), 10, 8)  # the latest receipt of the decision is the one read
        self.assertFalse(self.check("evl_verdicts", now)["stalled"], "20% is not over 20%")
        self.tally(et(TUE, "09:22"), 0, 0)
        self.assertIn("needed no verdict", self.check("evl_verdicts", now)["what"])

    def test_the_latest_sessions_decisions_are_summed_and_a_bad_tally_is_skipped(self):
        self.tally(et(MON, "15:46"), 50, 0, job="decide-close:2026-10-19")  # Monday's: not the day judged at 15:57 Tue
        self.tally(et(TUE, "09:15"), 8, 8)
        self.tally(et(TUE, "15:46"), 12, 8, job="decide-close:2026-10-20")
        check = self.check("evl_verdicts", et(TUE, "15:57"))
        self.assertEqual((check["numbers"]["day"], check["numbers"]["needed"], check["numbers"]["answered"]),
                         ("2026-10-20", 20, 16))
        self.assertFalse(check["stalled"], "4 of 20")
        for bad in ({"needed": 5, "answered": 9}, {"needed": "lots", "answered": 1}, {"needed": -1, "answered": 0}, "x"):
            self.receipt("decide-close:2026-10-20", et(TUE, "15:50"), summary={"verdicts": bad})
            self.assertEqual(self.check("evl_verdicts", et(TUE, "15:57"))["numbers"]["decisions_read"], "open", bad)


class Score(Lane):
    def test_a_session_not_scored_by_23_00(self):
        before = self.check("evl_score", et(TUE, "22:59"))
        self.assertEqual(before["numbers"]["day"], "2026-10-19", "Tuesday's 23:00 has not come")
        self.intent("8k:a", TUE)
        now = et(TUE, "23:30")
        check = self.check("evl_score", now)
        self.assertTrue(check["stalled"])
        self.assertEqual((check["numbers"]["unsettled_due"], check["onset"]), (1, et(TUE, "23:00")))
        self.receipt("score", et(TUE, "16:05"))  # before the tape is 16 minutes old: not this session's scoring
        self.assertTrue(self.check("evl_score", now)["stalled"])
        self.receipt("score", et(TUE, "20:30"), status="failed")
        self.assertTrue(self.check("evl_score", now)["stalled"], "a pass where every due intent failed scores nothing")
        self.receipt("score", et(TUE, "20:45"))
        self.assertFalse(self.check("evl_score", now)["stalled"])

    def test_a_night_with_nothing_due_is_no_stall(self):
        self.intent("8k:b", WED)  # due tomorrow
        self.intent("8k:c", TUE, status="exited")
        check = self.check("evl_score", et(TUE, "23:30"))
        self.assertEqual((check["stalled"], check["numbers"]["unsettled_due"]), (False, 0))


class StallHarness(StallBase):
    """The stall job over a swarm store (league/tests/test_ops_stall.py's) and a lane store, the lane on the House."""

    def lane(self, *, record_ago_minutes=None):
        st = ES.Store(self.root / "events")
        try:
            if record_ago_minutes is not None:
                at = self.now_ - record_ago_minutes * 60
                st.db.execute("INSERT INTO receipts(job, started_at, finished_at, status, summary) VALUES('record', ?, ?, "
                              "'ok', '{}')", (iso(at - 20), iso(at)))
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
        return ctx

    def setUp(self):
        super().setUp()
        self.now_ = et(TUE, "12:20")

    def record(self, at: float) -> None:
        st = ES.Store(self.root / "events")
        st.db.execute("INSERT INTO receipts(job, started_at, finished_at, status, summary) VALUES('record', ?, ?, 'ok', '{}')",
                      (iso(at - 20), iso(at)))
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
        # Recording again: the cause clears at the next run.
        self.record(self.now_ + 1790)
        again = ST.run(self.ctx(now=self.now_ + 1800))
        self.assertIn("evl_record", again["cleared"])

    def test_the_research_switch_judges_no_research_cause_and_no_research_alarm(self):
        """A60 turned the old lanes' research off by settings: with ops.json stall.research false no cause and no notice
        comes of it, and the money alarms of the direction lane stand as before."""
        self.lane(record_ago_minutes=2)
        st = ES.Store(self.root / "events")
        for job, start in (("decide-open:2026-10-20", et(TUE, "09:15")), ("decide-close:2026-10-19", et(MON, "15:46"))):
            st.db.execute("INSERT INTO receipts(job, started_at, finished_at, status, summary) VALUES(?, ?, ?, 'ok', '{}')",
                          (job, iso(start), iso(start + 60)))
        st.close()
        on = ST.run(self.ctx(settings={}))  # research judged: a store last busy on Oct 7 stands on every research cause
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
        # The direction lane's report: its research alarms are not judged; a money alarm stands.
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
        """Budget rule 3: `underspend` is not judged, whatever research booked (the cap is what may be spent)."""
        self.lane(record_ago_minutes=2)
        out = ST.run(self.ctx(settings={}))
        self.assertFalse(out["checks"]["underspend"]["stalled"])
        self.assertIn("a cheap day is never a failed day", out["checks"]["underspend"]["what"])
        self.assertEqual(ST.CHEAP_DAY_RULE, 3)


def synthetic_lane(root: Path, day: dt.date = TUE) -> None:
    """A lane store holding one invented session's figures (league/tests/test_events_report.py's shape): filings, news,
    verdicts, settled and planned intents with invented returns, and the day's receipts (record, decisions, score), so
    no cause of the four stands at 22:20 ET."""
    st = ES.Store(root / "events")
    try:
        class Cal:
            def get_json(self, path, params=None):
                start, end = dt.date.fromisoformat(params["start"]), dt.date.fromisoformat(params["end"])
                out, d = [], start
                while d <= end:
                    if d.weekday() < 5:
                        out.append({"date": d.isoformat(), "open": "09:30", "close": "16:00"})
                    d += dt.timedelta(days=1)
                return out
        C.refresh(st, Cal(), dt.date(2026, 10, 1), dt.date(2026, 12, 31))
        db = st.db

        def t(hhmm):
            return iso(et(day, hhmm))
        with st.tx():
            for acc, form, items in (("0001-26-000001", "8-K", '["2.02"]'), ("0001-26-000003", "8-K", '["8.01"]'),
                                     ("0001-26-000005", "4", "[]")):
                db.execute("INSERT INTO filings(accession, form, cik, items, accepted_at, knowable_at, received_at, source, "
                           "status) VALUES(?, ?, '0000000001', ?, ?, ?, ?, 'current', 'fetched')",
                           (acc, form, items, t("08:01"), t("08:11"), t("08:03")))
            db.execute("INSERT INTO news(id, created_at, received_at, knowable_at, source, headline, summary, symbols, live) "
                       "VALUES('1', ?, ?, ?, 'benzinga', 'ACME SURGES ON MIRACLE CURE', 'secret summary', '[\"ACME\"]', 1)",
                       (t("07:00"), t("07:01"), t("07:02")))
            for event, status, usd in (("8k:a", "ok", 0.004), ("8k:b", "ok", 0.006), ("8k:c", "unparsed", 0.003)):
                db.execute("INSERT INTO verdicts(event, prompt_sha, model, asked_at, answered_at, status, usd) VALUES(?, 'p', "
                           "'claude-haiku-4-5-20251001', ?, ?, ?, ?)", (event, t("08:20"), t("08:21"), status, usd))
            for i, (event, sym, status, r, a) in enumerate((("8k:a", "ACME", "exited", 0.012, 0.010),
                                                            ("8k:b", "BETA", "exited", -0.004, -0.006),
                                                            ("8k:c", "GAMA", "exited", 0.002, 0.001))):
                db.execute("INSERT INTO intents(program, version, event, symbol, cik, decided_at, entry_day, entry_at, "
                           "exit_day, exit_at, mode, status) VALUES('EVL-ERN-READ-O1', 1, ?, ?, ?, ?, ?, 'open', ?, 'close', "
                           "'shadow', ?)", (event, sym, f"{i:010d}", t("09:15"), day.isoformat(), day.isoformat(), status))
                db.execute("INSERT INTO outcomes(program, version, event, entry_px, exit_px, bench, r, b, a, tradable, "
                           "settled_at, status) VALUES('EVL-ERN-READ-O1', 1, ?, 123.45, 124.56, 'SPY', ?, ?, ?, 1, ?, "
                           "'settled')", (event, r, r - a, a, t("20:31")))
            for job, hhmm, summary in (("record", "22:15", {}), ("decide-open:" + day.isoformat(), "09:15",
                                                                 {"verdicts": {"needed": 3, "answered": 3}}),
                                       ("decide-close:" + day.isoformat(), "15:46", {"verdicts": {"needed": 0, "answered": 0}}),
                                       ("score", "20:30", {"due": 3, "settled": 3})):
                db.execute("INSERT INTO receipts(job, started_at, finished_at, status, summary) VALUES(?, ?, ?, 'ok', ?)",
                           (job, t(hhmm), t(hhmm), json.dumps(summary)))
    finally:
        st.close()


class DailyReport(StallHarness):
    """THE DAILY ONE-SCREEN REPORT: the day's figures ride the stall notice once a day from 22:00 ET of a session day,
    alone when nothing stands; the receipt and stall.json carry its day, never a figure."""

    def setUp(self):
        super().setUp()
        synthetic_lane(self.root)
        self.now_ = et(TUE, "22:20")

    def test_the_days_report_rides_a_notice_even_when_nothing_stands_and_once_a_day(self):
        out = ST.run(self.ctx())
        self.assertEqual(out["stalled"], [])
        self.assertTrue(out["notice"]["sent"])
        self.assertEqual(out["notice"]["report"], "2026-10-20")
        facts = self.notify.calls[-1]
        self.assertEqual((facts["causes"], facts["notice_id"]), ([], "stall:info:report:2026-10-20"))
        report = facts["report"]
        self.assertEqual(report["day"], "2026-10-20")
        self.assertEqual(report["events"], {"8k_202": 1, "8k_other": 1, "form4": 1, "news": 1, "failed": 0})
        self.assertEqual(report["verdicts"], {"ok": 2, "unparsed": 1, "refused": 0, "usd": 0.01})
        o1 = next(p for p in report["programs"] if p["id"] == "EVL-ERN-READ-O1")
        self.assertEqual((o1["settled"], o1["settled_today"], o1["tradable"], o1["real_n"]), (3, 3, 3, None))
        self.assertEqual(o1["shadow_pnl_usd"], round(100 * (0.012 - 0.004 + 0.002), 2), "at $100 an event")
        self.assertEqual((o1["mean_r_bp"], o1["mean_a_bp"]), (33.3, 16.7))
        self.assertEqual((o1["next_look"], o1["next_look_session"], o1["last_look"]), (1, 10, "none"))
        # No price, headline, symbol or text in the facts; no figure of the report in the receipt or stall.json.
        sent = json.dumps(facts)
        for banned in ("ACME", "MIRACLE", "secret summary", "123.45", "124.56", "BETA"):
            self.assertNotIn(banned, sent)
        kept = json.dumps(out) + (self.root / ST.STATE_FILE).read_text()
        for figure in ("shadow_pnl_usd", "mean_r_bp", "8k_202"):
            self.assertNotIn(figure, kept)
        self.assertEqual(json.loads((self.root / ST.STATE_FILE).read_text())["report"]["day"], "2026-10-20")
        # Told: the runs after it the same evening carry none, and mail nothing.
        self.record(self.now_ + 1700)
        later = ST.run(self.ctx(now=self.now_ + 1800))
        self.assertEqual((later["notice"]["sent"], later["notice"]["report"]), (False, None))
        self.assertEqual(len(self.notify.calls), 1)

    def test_it_rides_with_the_causes_standing_and_not_before_22_00_or_on_a_weekend(self):
        self.assertIsNone(ST.run(self.ctx(now=et(TUE, "21:50")))["notice"]["report"], "before 22:00 ET")
        self.assertEqual(self.notify.calls, [])
        st = ES.Store(self.root / "events")
        st.db.execute("DELETE FROM receipts WHERE job='record'")  # no record pass: evl_record stands
        st.close()
        out = ST.run(self.ctx())
        self.assertIn("evl_record", out["stalled"])
        facts = self.notify.calls[-1]
        self.assertEqual([c["cause"] for c in facts["causes"]], ["evl_record"])
        self.assertEqual((facts["report"]["day"], facts["notice_id"]), ("2026-10-20", "stall:info:evl_record:report:2026-10-20"))
        self.assertEqual(EV.report_day(et(dt.date(2026, 10, 24), "22:30")), None, "Saturday: Friday's is too old by then")
        self.assertEqual(EV.report_day(et(dt.date(2026, 10, 23), "23:59")), "2026-10-23")
        self.assertIsNone(EV.report_due(self.ctx(events=False), self.root, self.now_), "no lane on the House: no report")

    def test_a_duplicate_answer_tells_it_and_a_failed_send_tries_again(self):
        self.notify.answer = {"sent": False, "reason": "mail down"}
        first = ST.run(self.ctx())
        self.assertFalse(first["notice"]["sent"])
        self.assertEqual(json.loads((self.root / ST.STATE_FILE).read_text())["report"], {}, "not told: tried again")
        self.notify.answer = {"sent": True, "duplicate": True}
        self.record(self.now_ + 1700)
        ST.run(self.ctx(now=self.now_ + 1800))
        self.assertEqual(json.loads((self.root / ST.STATE_FILE).read_text())["report"]["day"], "2026-10-20",
                         "the gateway mailed this very notice already: its key names the day")
        calls = len(self.notify.calls)
        self.record(self.now_ + 3500)
        ST.run(self.ctx(now=self.now_ + 3600))
        self.assertEqual(len(self.notify.calls), calls)

    def test_a_report_that_does_not_fit_goes_without_and_says_so(self):
        with mock.patch.object(ST, "NOTICE_BYTES", 600):
            out = ST.run(self.ctx())
        self.assertIn("does not fit the notice: sent without it", " ".join(out["errors"]))
        self.assertEqual(self.notify.calls, [], "nothing stood: no notice without the report")


class ReportShape(unittest.TestCase):
    def test_the_houses_report_facts_are_the_gateways_fixture(self):
        """league/tests/fixtures/stall_report.json is what the gateway's test composes (gateway/test/
        stall-notice.test.mjs): the House writes exactly its keys, a program's too."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        synthetic_lane(root)
        ctx = {"config": {"events": {"enabled": True}}, "settings": {}}
        budget = {"cap": {"cap_usd_day": 5.0, "fixed_usd_day": 1.6644, "lane_usd_day": 3.0}, "research_usd_day": 0.3356,
                  "meters": {"sail": {"burn_usd_day": 1.2}, "claude": {"burn_usd_day": 2.9}}}
        facts = EV.report_due(ctx, root, et(TUE, "22:20"), budget=budget)
        fixture = json.loads(FIXTURE.read_text())
        fixture.pop("_note")

        def shape(value):
            if isinstance(value, dict):
                return {k: shape(v) for k, v in value.items()}
            if isinstance(value, list):
                return [shape(value[0])] if value else []
            return None
        self.assertEqual(shape({**facts, "programs": facts["programs"][:1]}), shape(fixture))
        self.assertEqual(facts["costs"], {"cap_usd_day": 5.0, "fixed_usd_day": 1.66, "lane_usd_day": 3.0,
                                          "research_usd_day": 0.34, "metered_usd_day": 4.1})


if __name__ == "__main__":
    unittest.main()
