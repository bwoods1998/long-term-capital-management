"""RELEASE 1019c: A69's fast path to a final record, A66's owed re-decision rule, and the event kind's own day order
count. Synthetic data only: every price, filing, article, verdict, receipt and fill here is invented."""

from __future__ import annotations

import copy
import datetime as dt
import json
import tempfile
import unittest
from decimal import Decimal as D
from zoneinfo import ZoneInfo

from league.constitution import (CONSTITUTION, EQUITY_MONEY_BOUNDS, PINNED_DIGEST, digest, equity_money_problems,
                                 money_digest)
from league.equity import schedule as ES
from league.events import book as EB
from league.events import calendar as C
from league.events import edgar as E
from league.events import programs as P
from league.events import run as R
from league.events import screen as SC
from league.events import store as S
from league.tests import equity_design as X
from league.tests import test_events_house as TH
from league.tests.test_events_book import DAY, PRIOR, EventTest, iso
from league.tests.test_events_review_1019b import LooksOnAFinalRecord, c1_event
from league.tests.test_events_run import FakeGateway, sec_pages
from league.tests.test_events_screen import final_record

NY = ZoneInfo("America/New_York")
UTC = dt.timezone.utc
#: A record pass's receipt as the House writes it when every feed read whole (league/events/house.py `_record`).
CLEAN = {"8-K": {"new": 0, "fetched": 0, "failed": 0, "unlisted": 0}, "4": {"new": 0, "fetched": 0, "failed": 0,
                                                                          "unlisted": 0},
         "news": {"seen": 0, "stored": 0}, "cut": False, "verdicts": []}


def et(day: dt.date, hh: int, mm: int = 0) -> dt.datetime:
    return dt.datetime.combine(day, dt.time(hh, mm), tzinfo=NY).astimezone(UTC)


# ======================================================================================== A69: the fast path
class TheFastPath(unittest.TestCase):
    """A69: a close X is final once the session after X has had its open decision when (i) each feed was read whole
    from the start of X's earliest window through that decision (A84: clean reads of each of 8-K, Form 4 and news at
    most 15 minutes apart; a pass that missed a feed is a missing read of it, so a single bad pass among clean ones
    breaks nothing, a run of them 15 minutes long does), (ii) no filing of those windows the lane would fetch is still
    listed or failed, (iii) the daily-index backfills of the days of X's windows have run and (iv) every decision of
    the program's entry kind through X is made; otherwise A66's three sessions."""

    setUp, tearDown, settle = LooksOnAFinalRecord.setUp, LooksOnAFinalRecord.tearDown, LooksOnAFinalRecord.settle
    P = "EVL-INS-BUY-O1"

    def passes(self, start: dt.datetime, end: dt.datetime, *, every: dt.timedelta = dt.timedelta(minutes=10),
               summary: dict | None = None) -> None:
        """Record receipts every `every` from `start` through `end`, each finished `ok` with `summary` (CLEAN)."""
        rows, t = [], start
        while t <= end:
            rows.append(("record", S.iso(t), S.iso(t + dt.timedelta(seconds=40)), "ok", json.dumps(summary or CLEAN)))
            t += every
        self.st.db.executemany("INSERT INTO receipts(job, started_at, finished_at, status, summary) VALUES(?, ?, ?, ?, ?)",
                               rows)

    def one_pass(self, at: dt.datetime, *, status: str = "ok", **parts) -> None:
        body = copy.deepcopy(CLEAN) | parts
        self.st.db.execute("INSERT INTO receipts(job, started_at, finished_at, status, summary) VALUES('record', ?, ?, ?, ?)",
                           (S.iso(at), S.iso(at + dt.timedelta(seconds=40)), status, json.dumps(body)))

    def spoil(self, start: dt.datetime, end: dt.datetime, *, status: str = "ok", **parts) -> None:
        """A84: every record pass from `start` through `end` misses what `parts` (or `status`) say, so the feed has no
        clean read from the pass before `start` to the one after `end`."""
        self.st.db.execute("UPDATE receipts SET status=?, summary=? WHERE job='record' AND started_at>=? AND started_at<=?",
                           (status, json.dumps(copy.deepcopy(CLEAN) | parts), S.iso(start), S.iso(end)))

    def due(self) -> dt.datetime:
        """Look 1 of INS-BUY-O1 v2 due at days[7] (80 events, 8 blocks); the House's record final through days[8]
        (decisions and backfills), the screen at 23:00 ET of days[8], one session after days[7]."""
        self.settle(self.P, 2, 10, self.days[:8], lambda i: 0.01)
        return final_record(self.st, self.days[8])

    def written(self, out):
        return [(w["program"], w["k"]) for w in out["written"]]

    def test_a_clean_record_is_final_after_one_session(self):
        now = self.due()
        out = SC.run(self.st, self.days[8], draws=999, now=now)
        self.assertEqual(out["written"], [], "no record pass on record: nothing is proven, A66's window holds it")
        self.assertIn("re-decision window", out["waiting"][0]["why"])
        self.assertIn("the fast path (A69) stops at", out["waiting"][0]["why"])
        self.passes(et(self.days[0], 8), et(self.days[8], 12))
        self.assertEqual(SC.final_until(self.st, self.P, 2, self.days[8], now)[0], self.days[7],
                         "final one session after it: days[8]'s open decision is made")
        out = SC.run(self.st, self.days[8], draws=999, now=now)
        self.assertEqual(self.written(out), [(self.P, 1)])
        self.assertEqual(SC.look_rows(self.st, self.P, 2)[0]["at"][:10], self.days[7].isoformat(), "the as-of date")
        # The session after X has not had its open decision: X waits (days[8] at days[8]'s own evening).
        horizon, why = SC.final_until(self.st, self.P, 2, self.days[8], now)
        self.assertEqual(horizon, self.days[7])
        self.assertIn(f"the session after it ({self.days[9].isoformat()}) has not had its open decision", why)

    def keeps_a66(self, now: dt.datetime, needle: str, *, again=None) -> None:
        out = SC.run(self.st, self.days[8], draws=999, now=now)
        self.assertEqual(out["written"], [])
        why = out["waiting"][0]["why"]
        self.assertIn("the re-decision window reaches", why)
        self.assertIn(needle, why)
        later = final_record(self.st, self.days[10])     # three sessions after days[7]: A66 makes it final
        if again is not None:
            again()
        out = SC.run(self.st, self.days[10], draws=999, now=later)
        self.assertEqual(self.written(out), [(self.P, 1)], "A66 unchanged: final once out of the re-decision window")
        self.assertEqual(SC.look_rows(self.st, self.P, 2)[0]["at"][:10], self.days[7].isoformat())

    def test_a_record_pass_with_a_news_error_keeps_a66(self):
        """A84: one pass with a news error, the next clean 9 minutes later, is whole; news errors from 12:10 to 12:30
        (no clean news read from 12:00 to 12:40) keep A66."""
        now = self.due()
        self.passes(et(self.days[0], 8), et(self.days[8], 12))
        self.one_pass(et(self.days[6], 12, 1), news={"error": "OSError: invented"})
        self.assertEqual(SC.final_until(self.st, self.P, 2, self.days[8], now)[0], self.days[7], "A84: a missing read")
        self.spoil(et(self.days[6], 12, 10), et(self.days[6], 12, 30), news={"error": "OSError: invented"})
        self.keeps_a66(now, f"stops at {self.days[6].isoformat()}: no clean read of the news feed from")
        why = SC.final_until(self.st, self.P, 2, self.days[8], now)[1]
        self.assertIn("the record pass of", why)
        self.assertIn("had a news error (OSError: invented)", why)

    def bad_pass(self, needle: str, feed: str = "8-K", *, status: str = "ok", **parts) -> None:
        """A84: one bad pass at 11:01 among clean ones every 10 minutes is a missing read (whole); the passes from 11:10
        to 11:30 bad too leave `feed` no clean read from 11:00 to 11:40, and days[7] waits."""
        now = self.due()
        self.passes(et(self.days[0], 8), et(self.days[8], 12))
        self.one_pass(et(self.days[7], 11, 1), status=status, **parts)
        self.assertEqual(SC.final_until(self.st, self.P, 2, self.days[8], now)[0], self.days[7],
                         "A84: the clean passes 9 minutes later recover what the bad one missed")
        self.spoil(et(self.days[7], 11, 10), et(self.days[7], 11, 30), status=status, **parts)
        horizon, why = SC.final_until(self.st, self.P, 2, self.days[8], now)
        self.assertEqual(horizon, self.days[6], "days[6]'s windows end before the bad passes; days[7]'s do not")
        self.assertIn(f"no clean read of the {feed} feed from {S.iso(et(self.days[7], 11))} to "
                      f"{S.iso(et(self.days[7], 11, 40))}, more than 15 minutes: the record pass of "
                      f"{S.iso(et(self.days[7], 11, 1))}", why)
        self.assertIn(needle, why)
        self.assertIn("(4 passes missed it)", why)

    def test_a_cut_news_read_keeps_a66(self):
        self.bad_pass("cut its news read short", "news", news={"cut": True})

    def test_an_8k_feed_error_keeps_a66(self):
        self.bad_pass("had a 8-K feed error (GatewayError: 503)", **{"8-K": {"error": "GatewayError: 503"}})

    def test_a_form_4_feed_error_keeps_a66(self):
        self.bad_pass("had a 4 feed error", "Form 4", **{"4": {"error": "GatewayError: 503", "fetched": 2}})

    def test_an_unread_tickers_copy_keeps_a66(self):
        self.bad_pass("could not read the tickers copy", tickers={"error": "KeyError: x"})

    def test_a_failed_or_unfinished_pass_keeps_a66(self):
        self.bad_pass("is failed", status="failed")

    def test_an_unfinished_pass_keeps_a66(self):
        self.bad_pass("is running", status="running")

    def test_a_failed_filing_keeps_a66(self):
        now = self.due()
        self.passes(et(self.days[0], 8), et(self.days[8], 12))
        accepted = et(self.days[6], 10)
        self.st.db.execute("INSERT INTO filings(accession, form, cik, company, items, accepted_at, knowable_at, "
                           "received_at, source, status) VALUES('x-1', '4', '0000000777', 'Invented', '[]', ?, ?, ?, "
                           "'current', 'failed:OSError:invented')",
                           (S.iso(accepted), S.iso(E.knowable(accepted)), S.iso(accepted)))
        self.keeps_a66(now, "filing x-1 (4) is failed:OSError:invented")

    def test_a_missing_backfill_keeps_a66(self):
        now = self.due()
        self.passes(et(self.days[0], 8), et(self.days[8], 12))
        drop = lambda: self.st.db.execute("DELETE FROM meta WHERE key=?", (f"evl:backfill:{self.days[6].isoformat()}",))  # noqa: E731
        drop()
        self.keeps_a66(now, f"the daily-index backfill of {self.days[6].isoformat()} has not run", again=drop)

    def test_a_gap_in_the_record_passes_keeps_a66(self):
        now = self.due()
        self.passes(et(self.days[0], 8), et(self.days[6], 13))
        self.passes(et(self.days[6], 15), et(self.days[8], 12))          # two hours with no pass on days[6]
        horizon, why = SC.final_until(self.st, self.P, 2, self.days[8], now)
        self.assertEqual(horizon, self.days[5])
        self.assertIn("no record pass ran from", why)

    def test_finality_stays_contiguous(self):
        """News errors in days[6]'s windows only (days[5] 12:00 to 12:30, no clean news read for 40 minutes): days[7]'s
        own passes are clean, but days[6] is not final, so neither is days[7]."""
        now = self.due()
        self.passes(et(self.days[0], 8), et(self.days[8], 12))
        self.spoil(et(self.days[5], 12, 10), et(self.days[5], 12, 30), news={"error": "OSError: invented"})
        horizon, why = SC.final_until(self.st, self.P, 2, self.days[8], now)
        self.assertEqual(horizon, self.days[5])
        self.assertIn(f"stops at {self.days[6].isoformat()}", why)

    def test_a_listed_8k_waits_only_when_its_filer_is_in_the_tickers_copy(self):
        now = self.due()
        self.passes(et(self.days[0], 8), et(self.days[8], 12))
        copy_ = json.dumps({"0": {"cik_str": 777, "ticker": "LSTD", "title": "Listed Co"}}).encode()
        self.st.set_meta(f"tickers@{S.iso(et(self.days[0], 7))}", self.st.put_document(copy_, "company_tickers"))
        accepted = et(self.days[7], 10)

        def listed(acc, cik):
            self.st.db.execute("INSERT INTO filings(accession, form, cik, company, items, accepted_at, knowable_at, "
                               "received_at, source, status) VALUES(?, '8-K', ?, 'Invented', '[]', ?, ?, ?, 'current', "
                               "'listed')", (acc, cik, S.iso(accepted), S.iso(E.knowable(accepted)), S.iso(accepted)))
        listed("u-1", "0000000888")          # not in the copy: never fetched, never an event of days[7]
        self.assertEqual(SC.final_until(self.st, self.P, 2, self.days[8], now)[0], self.days[7])
        listed("l-1", "0000000777")          # in the copy: it will be fetched; days[7] waits for it
        horizon, why = SC.final_until(self.st, self.P, 2, self.days[8], now)
        self.assertEqual(horizon, self.days[6])
        self.assertIn("filing l-1 (8-K) of a listed filer is still listed", why)

    def test_the_session_after_must_have_made_its_open_decision(self):
        now = self.due()
        self.passes(et(self.days[0], 8), et(self.days[8], 12))
        self.st.db.execute("DELETE FROM receipts WHERE job=?", (f"decide-open:{self.days[8].isoformat()}",))
        horizon, why = SC.final_until(self.st, self.P, 2, self.days[8], now)
        self.assertEqual(horizon, self.days[6])
        self.assertIn(f"the open decision of {self.days[8].isoformat()} is not made", why)

    def test_a_decision_pending_on_the_programs_own_verdicts_keeps_a66(self):
        now = self.due()
        self.passes(et(self.days[0], 8), et(self.days[8], 12))
        rid = self.st.start_receipt(f"decide-open:{self.days[7].isoformat()}")
        self.st.finish_receipt(rid, "pending", {"pending": {f"{self.P}@v2": 1}})
        horizon, why = SC.final_until(self.st, self.P, 2, self.days[8], now)
        self.assertEqual(horizon, self.days[6])
        self.assertIn(f"the open decision of {self.days[7].isoformat()} is pending", why)
        rid = self.st.start_receipt(f"decide-open:{self.days[7].isoformat()}")
        self.st.finish_receipt(rid, "pending", {"pending": {"EVL-8K-READ-O1@v2": 1}})
        self.assertEqual(SC.final_until(self.st, self.P, 2, self.days[8], now)[0], self.days[7],
                         "pending only on another program's verdicts: made for this one")


def opens_after(st: S.Store, day: dt.date, now: dt.datetime) -> int:
    """How many sessions after `day` have had their open decision at `now`: from SC.FINAL_SESSIONS (three) on, the
    House's hourly re-decision reaches `day` no more (A66's first rule)."""
    after = C.sessions(st, day + dt.timedelta(days=1), now.astimezone(NY).date())
    return len([s for s in after if s.open_decide <= now])


# ================================================================================ A66 owed: what a re-decision writes
class ARedecisionWritesOnlyWhatIsOpen(unittest.TestCase):
    """A66 (owed), as release 1019c's fix round keeps it: a re-decision never writes an intent for a program of a GROUP
    (every version of an id, its control, and every READ program of that control) a look of which stands over the
    session, so a late-stored event can never land under a look already written, and the group's records stay even
    (release 1019c's judges review; A74 (5)). Every other program is decided whole, inside the re-decision window and
    outside it: A74 (6), which wrote again outside the window only the programs the last receipt was pending on, is
    withdrawn (the judges review of release 1019c, its major: it dropped a backfilled event from every record, and
    split a READ program from its control). Each kept program's entry lists the events left out of its record, and the
    daily report counts them."""

    MONDAY = dt.date(2026, 10, 19)
    AAA = ("0000000001-26-000001", "0000000001")       # accepted 07:05 ET Monday (sec_pages); verdict score 3
    BBB = ("0000000002-26-000002", "0000000002")       # accepted 07:10 ET Monday; verdict score 1

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.st = S.Store(self.tmp.name)
        self.now = dt.datetime(2026, 10, 19, 13, 15, tzinfo=UTC)
        self.gw = FakeGateway({"AAA": 3, "BBB": 1})
        C.refresh(self.st, self.gw, dt.date(2026, 8, 1), dt.date(2026, 12, 31))
        self.st.set_meta("tickers@2026-10-19T01:05:00Z", self.st.put_document(sec_pages("x/company_tickers.json"), "t"))
        self._pinned = P.REGISTERED_AT
        P.REGISTERED_AT = "2026-10-19T01:00:00Z"

    def tearDown(self):
        P.REGISTERED_AT = self._pinned
        self.st.close()
        self.tmp.cleanup()

    def store(self, filing) -> None:
        acc, cik = filing
        entry = {"form": "8-K", "cik": cik, "accession": acc, "company": "Co", "items": ["2.02"], "accepted_at": None,
                 "index_url": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-', '')}/{acc}-index.htm"}
        self.assertEqual(E.record_filing(self.st, sec_pages, entry, source="current", now=self.now), "fetched")

    def decide(self, at: dt.datetime, gw=None) -> dict:
        ctx = R.Context(self.st, gw or self.gw, sec_pages, now=lambda: at)
        return R.decide_open(ctx, self.MONDAY)

    def symbols(self, program: str, version: int = 1) -> list[str]:
        return [r[0] for r in self.st.db.execute("SELECT symbol FROM intents WHERE program=? AND version=? AND "
                                                 "status='planned' ORDER BY symbol", (program, version))]

    def pending_monday(self) -> dict:
        """Monday's open decided while Claude refuses: the READ programs pending, the controls decided (AAA only)."""
        self.store(self.AAA)
        refusing = FakeGateway({"AAA": 3})
        refusing.post_json = lambda path, body, headers=None: (400, {"error": "invented refusal"})
        first = self.decide(self.now, refusing)
        self.assertIn("EVL-ERN-READ-O1", first["pending"])
        self.assertNotIn("EVL-CTRL-ERN-ALL-O1", first["pending"])
        self.assertEqual(self.symbols("EVL-CTRL-ERN-ALL-O1"), ["AAA"])
        self.store(self.BBB)                 # stored late: after Monday's decision ran
        return first

    def test_outside_the_window_every_program_is_decided_whole(self):
        """Release 1019c's judges review, its major (A74 (6) withdrawn): the late BBB lands for every program its rule
        takes, the control too, so each READ program's comparison with its control stays even (under A74 (6) GUIDE-O1,
        which was pending, took BBB and its control did not)."""
        first = self.pending_monday()
        friday = dt.datetime(2026, 10, 23, 14, 0, tzinfo=UTC)     # Tue, Wed, Thu and Fri have had their opens
        self.assertGreaterEqual(opens_after(self.st, self.MONDAY, friday), SC.FINAL_SESSIONS)
        out = self.decide(friday)
        self.assertEqual(out["pending"], {})
        self.assertNotIn("kept", out, "no look stands over Monday: nothing is kept")
        self.assertEqual(self.symbols("EVL-ERN-READ-O1"), ["AAA"], "BBB's score 1 is under READ-O1's 2")
        self.assertEqual(self.symbols("EVL-ERN-READ-O1", 2), ["AAA"])
        self.assertEqual(self.symbols("EVL-ERN-GUIDE-O1", 2), ["AAA", "BBB"])
        self.assertEqual(self.symbols("EVL-CTRL-ERN-ALL-O1"), ["AAA", "BBB"],
                         "the control takes the late event as its READ programs do: the comparison stays even")
        self.assertNotIn("EVL-CTRL-ERN-ALL-O1", first["pending"], "it was not pending: A74 (6) kept it")
        receipt = self.st.db.execute("SELECT status FROM receipts WHERE job='decide-open:2026-10-19' ORDER BY id DESC "
                                     "LIMIT 1").fetchone()[0]
        self.assertEqual(receipt, "ok")
        again = self.decide(friday + dt.timedelta(hours=1))
        self.assertNotIn("kept", again)
        self.assertEqual(self.symbols("EVL-CTRL-ERN-ALL-O1"), ["AAA", "BBB"], "decided again: the same record")
        self.assertEqual(self.symbols("EVL-ERN-GUIDE-O1", 2), ["AAA", "BBB"])

    def test_inside_the_window_every_program_is_decided_again(self):
        self.pending_monday()
        tuesday = dt.datetime(2026, 10, 20, 14, 0, tzinfo=UTC)
        self.assertLess(opens_after(self.st, self.MONDAY, tuesday), SC.FINAL_SESSIONS)
        out = self.decide(tuesday)
        self.assertNotIn("kept", out)
        self.assertEqual(self.symbols("EVL-CTRL-ERN-ALL-O1"), ["AAA", "BBB"], "inside the window the late event lands")

    def test_a_look_freezes_its_group_outside_the_window_too(self):
        """The one rule that keeps A66's purpose holds outside the window as inside it: a look of READ-O1 version 2 over
        Monday keeps its whole group, and a record outside the group takes the late AAA (under A74 (6) Monday's `ok`
        receipt kept every program, that record too)."""
        self.store(self.BBB)
        self.assertEqual(self.decide(self.now)["pending"], {})
        self.store(self.AAA)                 # stored late
        self.look("EVL-ERN-READ-O1", 2)
        friday = dt.datetime(2026, 10, 23, 14, 0, tzinfo=UTC)
        self.assertGreaterEqual(opens_after(self.st, self.MONDAY, friday), SC.FINAL_SESSIONS)
        out = self.decide(friday)
        self.assertEqual(sorted(out["kept"]), sorted(p if v == 1 else f"{p}@v{v}" for p, v in self.GROUP))
        self.assertEqual(self.symbols("EVL-CTRL-ERN-ALL-O1"), ["BBB"], "nothing lands under the group's look")
        self.assertEqual(out["kept"]["EVL-CTRL-ERN-ALL-O1"]["events"], [f"8k:{self.AAA[0]}"], "named and counted")
        self.assertEqual(self.symbols("EVL-ERN-READ-O3"), ["AAA"], "a record outside the group: decided whole")
        self.assertNotIn("EVL-ERN-READ-O3", out["kept"])

    GROUP = (("EVL-ERN-READ-O1", 1), ("EVL-ERN-READ-O1", 2), ("EVL-ERN-GUIDE-O1", 1), ("EVL-ERN-GUIDE-O1", 2),
             ("EVL-CTRL-ERN-ALL-O1", 1))

    def look(self, program: str, version: int, day: dt.date | None = None) -> None:
        self.st.db.execute("INSERT INTO looks(program, version, k, at, held, passed) VALUES(?, ?, 1, ?, 1, 0)",
                           (program, version, S.iso(C.session(self.st, day or self.MONDAY).close_at)))

    def test_a_look_freezes_its_whole_group_inside_the_window(self):
        """The judges review's case: a look of READ-O1 version 2 over Monday freezes BOTH versions of READ-O1 (version
        2 takes version 1's events word for word), its control, and both versions of GUIDE-O1 (which reads the same
        control): the late AAA lands in none of them, and each receipt names it. The records outside the group
        (READ-O3, READ3-O1) take it."""
        self.store(self.BBB)
        first = self.decide(self.now)
        self.assertEqual(first["pending"], {})
        before = {k: self.symbols(*k) for k in self.GROUP}
        self.assertEqual(before[("EVL-CTRL-ERN-ALL-O1", 1)], ["BBB"])
        self.assertEqual(before[("EVL-ERN-GUIDE-O1", 2)], ["BBB"])
        self.store(self.AAA)                 # stored late
        self.look("EVL-ERN-READ-O1", 2)
        out = self.decide(dt.datetime(2026, 10, 20, 14, 0, tzinfo=UTC))
        for program, version in self.GROUP:
            key = program if version == 1 else f"{program}@v{version}"
            entry = out["kept"][key]
            self.assertIn("a look of its group is written over this session (EVL-ERN-READ-O1@v2 look 1 as of "
                          "2026-10-19)", entry["why"], key)
            self.assertEqual(self.symbols(program, version), before[(program, version)], f"{key}: nothing lands")
            self.assertEqual(entry["events"] + entry["unjudged"], [f"8k:{self.AAA[0]}"],
                             f"{key}: the late AAA its rule takes is named as left out")
        self.assertEqual(out["kept"]["EVL-ERN-READ-O1"]["events"], [f"8k:{self.AAA[0]}"],
                         "the verdict the records outside the group asked in this run is read: AAA is taken (score 3)")
        self.assertEqual(self.symbols("EVL-ERN-READ-O1"), self.symbols("EVL-ERN-READ-O1", 2), "v1 and v2 stay even")
        self.assertEqual(self.symbols("EVL-ERN-READ-O3"), ["AAA"], "a record outside the group is decided as before")
        self.assertNotIn("EVL-ERN-READ-O3", out["kept"])
        self.assertNotIn("EVL-8K-READ-O1", out.get("kept", {}), "another group is not frozen")

    def test_a_control_look_side_freezes_the_same_group(self):
        """A look of GUIDE-O1 version 1 freezes the same group (GUIDE, READ-O1 and their control) from the other side."""
        self.store(self.BBB)
        self.decide(self.now)
        self.store(self.AAA)
        self.look("EVL-ERN-GUIDE-O1", 1)
        out = self.decide(dt.datetime(2026, 10, 20, 14, 0, tzinfo=UTC))
        self.assertEqual(sorted(out["kept"]), sorted(p if v == 1 else f"{p}@v{v}" for p, v in self.GROUP))
        self.assertEqual(self.symbols("EVL-CTRL-ERN-ALL-O1"), ["BBB"])

    def test_a_look_that_does_not_cover_the_session_freezes_nothing(self):
        self.store(self.BBB)
        self.decide(self.now)
        self.store(self.AAA)
        self.look("EVL-ERN-READ-O1", 2, dt.date(2026, 10, 16))     # as of the Friday before
        out = self.decide(dt.datetime(2026, 10, 20, 14, 0, tzinfo=UTC))
        self.assertNotIn("kept", out)
        self.assertEqual(self.symbols("EVL-CTRL-ERN-ALL-O1"), ["AAA", "BBB"], "inside the window the late event lands")

    def test_a_pending_program_under_its_groups_look_is_kept_and_its_session_made(self):
        """A program pending on its own verdicts when a look of its group stands over the session is kept too (the
        group stays even); the kept run's receipt no longer waits on it, so its session is made (A66's second rule)
        and its next look is not held back by it."""
        self.pending_monday()
        self.look("EVL-ERN-READ-O1", 2)
        out = self.decide(dt.datetime(2026, 10, 20, 14, 0, tzinfo=UTC))
        self.assertEqual(out["pending"], {})
        self.assertIn("a look of its group", out["kept"]["EVL-ERN-GUIDE-O1@v2"]["why"])
        self.assertEqual(self.symbols("EVL-ERN-GUIDE-O1", 2), [], "nothing lands under its group's look")
        self.assertIn(f"8k:{self.AAA[0]}", out["kept"]["EVL-ERN-GUIDE-O1@v2"]["events"] +
                      out["kept"]["EVL-ERN-GUIDE-O1@v2"]["unjudged"])
        status, summary = self.st.db.execute("SELECT status, summary FROM receipts WHERE job='decide-open:2026-10-19' "
                                             "ORDER BY id DESC LIMIT 1").fetchone()
        self.assertEqual(status, "ok")
        self.assertFalse(SC._waits_on(status, summary, "EVL-ERN-GUIDE-O1@v2"), "its Monday decision is made")

    def test_the_report_counts_what_each_decision_kept_out(self):
        from league.events import report as RP

        self.store(self.BBB)
        self.decide(self.now)
        self.store(self.AAA)
        self.look("EVL-ERN-READ-O1", 2)
        self.decide(dt.datetime(2026, 10, 20, 14, 0, tzinfo=UTC))
        self.decide(dt.datetime(2026, 10, 20, 15, 0, tzinfo=UTC))     # the next hour's re-decision: the same event
        status = RP.program_status(self.st, "EVL-CTRL-ERN-ALL-O1", 1, self.MONDAY)
        self.assertEqual(status["kept_out"], {"events": 1, "unjudged": 0}, "each event once")
        self.assertEqual(RP.program_status(self.st, "EVL-ERN-READ-O3", 1, self.MONDAY)["kept_out"],
                         {"events": 0, "unjudged": 0})
        text = RP.render(RP.build(self.st, self.MONDAY, now=dt.datetime(2026, 10, 20, 16, 0, tzinfo=UTC)))
        self.assertIn("EVL-CTRL-ERN-ALL-O1 v1 (record): today p/e/s/x", text)
        self.assertIn("; kept out 1", text)

    def test_a_look_records_when_it_was_written(self):
        """From its written time on a look freezes its group (`_scope`): the time is in its detail (`written_at`)."""
        at = dt.datetime(2026, 10, 20, 1, 0, tzinfo=UTC)
        look = {c: None for c in SC.LOOK_COLUMNS} | {"program": "EVL-ERN-READ-O1", "version": 2, "k": 1,
                                                     "at": S.iso(C.session(self.st, self.MONDAY).close_at),
                                                     "held": 0, "passed": 0, "why": "skipped: invented"}
        self.assertTrue(SC.write_look(self.st, look, now=at))
        self.assertEqual(SC.look_detail(self.st, "EVL-ERN-READ-O1", 2, 1)["written_at"], S.iso(at))
        self.assertFalse(SC.write_look(self.st, look, now=at + dt.timedelta(hours=1)), "never rewritten")
        self.assertEqual(SC.look_detail(self.st, "EVL-ERN-READ-O1", 2, 1)["written_at"], S.iso(at))

    def test_a_kept_program_is_asked_no_verdict_and_fetched_no_price(self):
        """`_left_out` reads only what is stored: a REACT row with no stored price, or a READ row with no stored verdict,
        is `unjudged`; a stored reaction below 1.04 is not taken; the prices are read without the gateway."""
        class NoGateway:
            def get_json(self, *a, **k):
                raise AssertionError("a kept program fetched a price")

            def post_json(self, *a, **k):
                raise AssertionError("a kept program asked a verdict")

        ctx = R.Context(self.st, NoGateway(), sec_pages, now=lambda: dt.datetime(2026, 10, 20, 21, 0, tzinfo=UTC))
        at = dt.datetime(2026, 10, 19, 11, 5, tzinfo=UTC)
        self.assertIsNone(R._mark_1530(ctx, "AAA", self.MONDAY, fetch=False))
        self.assertIsNone(R._last_close_before(ctx, "AAA", at, fetch=False))
        self.store(self.AAA)
        row = dict(self.st.db.execute("SELECT * FROM filings WHERE accession=?", (self.AAA[0],)).fetchone())
        uni = {"symbol": "AAA", "cik": self.AAA[1]}
        c1 = EB.program_of("EVL-ERN-REACT-C1", 2)
        for ratio, want in ((None, {"events": [], "unjudged": [f"8k:{self.AAA[0]}"]}),
                            (1.01, {"events": [], "unjudged": []}),
                            (1.05, {"events": [f"8k:{self.AAA[0]}"], "unjudged": []})):
            got = R._left_out(self.st, c1, [row], eligible=lambda c: uni, reaction=lambda r, u, x=ratio: x)
            self.assertEqual(got, want, ratio)
        read = EB.program_of("EVL-ERN-READ-O1", 2)
        self.assertEqual(R._left_out(self.st, read, [row], eligible=lambda c: uni),
                         {"events": [], "unjudged": [f"8k:{self.AAA[0]}"]}, "no verdict stored: unjudged, never asked")

    def test_a_close_entry_look_freezes_only_the_sessions_it_covers(self):
        c1 = EB.program_of("EVL-ERN-REACT-C1", 2)
        self.st.db.execute("INSERT INTO looks(program, version, k, at, held, passed) VALUES(?, 2, 1, ?, 1, 0)",
                           (c1.id, S.iso(C.session(self.st, self.MONDAY).close_at)))
        tuesday = dt.datetime(2026, 10, 20, 21, 0, tzinfo=UTC)
        self.assertIsNone(R._scope(self.st, "close", self.MONDAY, tuesday)(c1),
                          "Monday's C1 entries exit Tuesday's close: a look as of Monday does not cover them")
        friday = dt.date(2026, 10, 16)
        self.assertIn("a look of its group is written over this session", R._scope(self.st, "close", friday,
                                                                                    tuesday)(c1)["why"])
        self.assertIn("a look of its group", R._scope(self.st, "close", friday, tuesday)(P.BY_KEY[
            ("EVL-ERN-REACT-C1", 1)])["why"], "version 1 of the id too")
        self.assertIsNone(R._scope(self.st, "close", friday, tuesday)(EB.program_of("EVL-ERN-REACT-ON", 2)),
                          "another id with no control is its own group")


# ============================================================== an outage removes nothing (A74 (6) withdrawn)
class BackfillGateway(FakeGateway):
    """FakeGateway with a NASDAQ closing print, which the backfill rule reads for the listing exchange (invented)."""

    def get_json(self, path, params=None):
        if path.endswith("/trades"):
            return {"trades": [{"t": params["start"], "x": "Q", "p": 20.0, "s": 100, "c": ["@", "6"]}]}
        return super().get_json(path, params)


class AnOutageRemovesNothing(unittest.TestCase):
    """Release 1019c's judges review, its major: PREREG-EVL-1 section 3, "an outage removes nothing", and its BACKFILL,
    events "are read afterwards and count". The House is down from Monday 10:00 ET to Thursday 10:00 ET. Back, its
    daily-index backfill of Monday (still in its three weekdays' reach; a look of Monday waits for it, A66's third rule)
    stores BBB, an 8-K of Monday's open window the current feed missed, and decides Monday's open again
    (league/events/house.py `_backfill`). Monday is outside the re-decision window by then: under A74 (6), now
    withdrawn, Monday's `ok` receipt kept every program, BBB was in no record, and real money's one position per issuer
    no longer saw the shadow's holding."""

    MONDAY = dt.date(2026, 10, 19)
    AAA = ("0000000001-26-000001", "0000000001")       # accepted 07:05 ET Monday (sec_pages): stored live, score 3
    BBB = ("0000000002-26-000002", "0000000002")       # accepted 07:10 ET Monday: missed live, the backfill's, score 3
    BACK = dt.datetime(2026, 10, 22, 14, 0, tzinfo=UTC)     # Thursday 10:00 ET: the House is back

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.st = S.Store(self.tmp.name)
        self.gw = BackfillGateway({"AAA": 3, "BBB": 3})
        C.refresh(self.st, self.gw, dt.date(2026, 8, 1), dt.date(2026, 12, 31))
        self.st.set_meta("tickers@2026-10-19T01:05:00Z", self.st.put_document(sec_pages("x/company_tickers.json"), "t"))
        self._pinned = P.REGISTERED_AT
        P.REGISTERED_AT = "2026-10-19T01:00:00Z"

    def tearDown(self):
        P.REGISTERED_AT = self._pinned
        self.st.close()
        self.tmp.cleanup()

    def store(self, filing, *, source: str, now: dt.datetime) -> None:
        acc, cik = filing
        entry = {"form": "8-K", "cik": cik, "accession": acc, "company": "Co", "items": ["2.02"], "accepted_at": None,
                 "index_url": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-', '')}/{acc}-index.htm"}
        self.assertEqual(E.record_filing(self.st, sec_pages, entry, source=source, now=now), "fetched")

    def symbols(self, program: str, version: int = 1) -> list[str]:
        return [r[0] for r in self.st.db.execute("SELECT symbol FROM intents WHERE program=? AND version=? AND "
                                                 "status='planned' ORDER BY symbol", (program, version))]

    def outage(self) -> dict:
        """Monday's live open decision (AAA), the outage, and the backfill's re-decision of Monday on Thursday."""
        live = dt.datetime(2026, 10, 19, 13, 15, tzinfo=UTC)              # 09:15 ET Monday
        self.store(self.AAA, source="current", now=live)
        first = R.decide_open(R.Context(self.st, self.gw, sec_pages, now=lambda: live), self.MONDAY)
        self.assertEqual(first["pending"], {})
        self.assertEqual(self.symbols("EVL-CTRL-ERN-ALL-O1"), ["AAA"])
        self.assertGreaterEqual(opens_after(self.st, self.MONDAY, self.BACK), SC.FINAL_SESSIONS, "outside the window")
        horizon, why = SC.final_until(self.st, "EVL-ERN-READ-O1", 2, self.BACK.astimezone(NY).date(), self.BACK)
        self.assertIsNone(horizon)
        self.assertIn("the daily-index backfill of 2026-10-19 has not run", why, "A66's third rule: Monday waits")
        self.store(self.BBB, source="daily-index", now=self.BACK)
        self.st.set_meta("evl:backfill:2026-10-19", "done")
        at = self.BACK + dt.timedelta(minutes=5)
        return R.decide_open(R.Context(self.st, self.gw, sec_pages, now=lambda: at), self.MONDAY, backfill_run=True)

    def test_a_backfill_after_an_outage_of_three_sessions_lands_in_every_record(self):
        again = self.outage()
        self.assertNotIn("kept", again, "no look stands over Monday: nothing is kept")
        self.assertEqual(again["pending"], {})
        for program, version in (("EVL-ERN-READ-O1", 1), ("EVL-ERN-READ-O1", 2), ("EVL-ERN-GUIDE-O1", 1),
                                 ("EVL-ERN-GUIDE-O1", 2), ("EVL-CTRL-ERN-ALL-O1", 1)):
            self.assertEqual(self.symbols(program, version), ["AAA", "BBB"], f"{program} v{version}: the event counts")
        horizon, _ = SC.final_until(self.st, "EVL-ERN-READ-O1", 2, self.BACK.astimezone(NY).date(),
                                    self.BACK + dt.timedelta(minutes=10))
        self.assertEqual(horizon, self.MONDAY, "Monday is final once its backfill ran, with BBB in its record")

    def test_real_moneys_one_position_per_issuer_sees_the_backfilled_event(self):
        """PREREG-EVL-1 section 5 and A70 (14): READ-O1 version 2 held BBB's issuer from Monday's backfilled event, so
        real money's decision of Friday Oct 23 (within 5 sessions) skips the issuer for that program."""
        self.outage()
        self.assertTrue(EB.held_recently(self.st, EB.program_of("EVL-ERN-READ-O1", 2), self.BBB[1],
                                         dt.date(2026, 10, 23)))


class TheHouseAfterAnOutage(TH.LaneCase):
    """The House's own scheduler (league/events/house.py), down Monday 10:00 ET to Thursday 11:00 ET: Monday's decisions
    were made before it went down (LaneCase.setUp), the missed decisions of Tuesday to Thursday on its return. Monday's
    daily index (still in the backfill's reach on Thursday) holds an earnings 8-K accepted 07:10 ET Monday that the live
    pass missed: the backfill fetches it and the House decides Monday's open again, for every program."""

    start = "2026-10-22T15:00:00Z"   # Thu Oct 22, 11:00 ET

    def test_the_backfilled_event_reaches_every_record(self):
        acc = "0000000002-26-000777"
        self.gw.scores["BBB"] = 3                       # its verdict: READ-O1's rule takes it too
        self.sec.add(acc, "0000000002", "2026-10-19 07:10:00", current=False)
        self.sec.daily["20261019"] = [acc]
        self.mark_recorded()
        with self.store() as st:
            for day, kinds in (("2026-10-20", ("open", "close")), ("2026-10-21", ("open", "close")),
                               ("2026-10-22", ("open",))):
                for kind in kinds:
                    rid = st.start_receipt(f"decide-{kind}:{day}", now=TH.et("2026-10-22", "10:30"))
                    st.finish_receipt(rid, "ok", {}, now=TH.et("2026-10-22", "10:31"))
            for day in ("2026-10-20", "2026-10-21"):
                st.set_meta(f"evl:backfill:{day}", "done")
            st.set_meta("tickers@2026-10-22T11:00:05Z", st.put_document(json.dumps(TH.TICKERS).encode(), "t"))
        for kind in ("open", "close"):
            self.lane._looks[(kind, dt.date(2026, 10, 22))] = TH.H.VerdictLook(self.clock_dt(), 0, False)
        self.lane._events_at = TH.et("2026-10-22", "00:00")
        tasks = []
        for _ in range(12):
            last = self.turn()
            tasks.append((last.get("task"), last.get("status")))
            if last.get("task") == "decide-open":
                break
            self.clock.advance(30)
        self.assertIn(("backfill", "ok"), tasks, tasks)
        self.assertEqual(tasks[-1][0], "decide-open", tasks)
        with self.store() as st:
            got = {(r[0], r[1]) for r in st.db.execute("SELECT program, version FROM intents WHERE event=?",
                                                        (f"8k:{acc}",))}
            summary = json.loads(st.db.execute("SELECT summary FROM receipts WHERE job='decide-open:2026-10-19' "
                                               "ORDER BY id DESC LIMIT 1").fetchone()[0])
        self.assertNotIn("kept", summary)
        for key in (("EVL-CTRL-ERN-ALL-O1", 1), ("EVL-ERN-READ-O1", 1), ("EVL-ERN-READ-O1", 2),
                    ("EVL-ERN-GUIDE-O1", 2)):
            self.assertIn(key, got, f"the backfilled 8-K is in {key}'s record")


# ======================================================================== the event kind's own day order count
class TheEventKindsOwnDayCount(EventTest):
    """The event kind's auction orders count against `equity_money.event.max_orders_day` (150), the old lanes keep the
    equity book's 60; both stay under the House-wide line and the gateway's."""

    def test_the_row_its_bounds_and_its_reader(self):
        event = CONSTITUTION["equity_money"]["event"]
        self.assertEqual(event["max_orders_day"], 150)
        self.assertEqual(CONSTITUTION["equity_money"]["order_path"]["max_orders_day"], 60, "the old lanes keep 60")
        live = sum(event["max_open"][band] for band in EB.LIVE_BANDS)
        self.assertEqual(event["max_orders_day"], max(2 * live, 150), "2 x the max_open of the live bands, at least 150")
        # A78 (release 1019d, the reading that trades less): with PREREG-EVL-4's three, the twelve seatable programs' full
        # learning rooms bought and sold in one day (2 x 12 x 8 = 192) are above the line, and the line STAYS 150 (the
        # House-wide line leaves it at most 190: the bound below); on a day that would need more, entries stop in ROOM's
        # order, so PREREG-EVL-4's rows are refused first, and exits never (`test_twelve_programs_on_a_heavy_day_...`).
        # (PREREG-EVL-5, release 1019g: fifteen seatable programs, 2 x 15 x 8 = 240, further above the line: it stays 150)
        self.assertEqual(len(EB.seatable()), 15)
        self.assertLess(event["max_orders_day"], 2 * len(EB.seatable()) * event["max_open"]["learning"],
                        "A78: twelve programs' full learning rooms are above the line; it is not raised for them")
        self.assertEqual(2 * 9 * event["max_open"]["learning"], 144, "the nine's fit under it, as release 1019c read it")
        self.assertLessEqual(event["max_orders_day"], CONSTITUTION["options_money"]["gateway"]["max_day_orders"])
        self.assertEqual(EQUITY_MONEY_BOUNDS["event.max_orders_day"], ("0", "300"))
        self.assertEqual((EB.settings().max_orders_day, EB.FALLBACK.max_orders_day), (150, 0))
        for value, why in ((301, "event.max_orders_day = 301 is outside [0, 300]"),
                           (150.0, "event.max_orders_day = 150.0 is not a whole count"),
                           (191, "are above the House-wide line together")):
            bad = copy.deepcopy(CONSTITUTION)
            bad["equity_money"]["event"]["max_orders_day"] = value
            self.assertIn(why, " ".join(equity_money_problems(bad)), value)
            self.assertEqual(EB.settings(bad), EB.FALLBACK, value)
        bad = copy.deepcopy(CONSTITUTION)
        bad["options_money"]["gateway"]["max_day_orders"] = 140
        self.assertIn("is above the gateway's day line", " ".join(equity_money_problems(bad)))
        missing = copy.deepcopy(CONSTITUTION)
        del missing["equity_money"]["event"]["max_orders_day"]
        self.assertIn("equity_money.event.max_orders_day is missing", " ".join(equity_money_problems(missing)))
        self.assertEqual(equity_money_problems(X.before_r2()), [], "R2's rollback (no event block) stays valid")

    def test_the_digests_moved_once_with_the_row_and_nothing_else(self):
        pair = X.in_force()
        self.assertEqual((money_digest(), digest()), X.DIGESTS[pair])
        self.assertEqual(digest(), PINNED_DIGEST)
        # (The captain's A86 moved them once more, the Probe band's three rows: release 1019c's pins are the table's
        # with those rows set back, `before_a86`; league/tests/test_events_a86.py holds the move.)
        at_1019c = X.before_a86()
        self.assertEqual((money_digest(at_1019c), digest(at_1019c)), X.DIGESTS_1019C[pair], "release 1019c's pair")
        self.assertEqual((money_digest(at_1019c)[:8], digest(at_1019c)[:8]), ("055e5313", "a8d4cbd9"))
        before = X.before_1019c()
        self.assertEqual((money_digest(before), digest(before)), X.DIGESTS_R2[pair], "release 1019b's pair, exactly")
        self.assertEqual((money_digest(before)[:8], digest(before)[:8]), ("285fa7af", "fd38e4e1"))
        for candidate in X.CANDIDATES:
            at = X.before_a86(X.constitution_at(*candidate))
            self.assertEqual((money_digest(at), digest(at)), X.DIGESTS_1019C[candidate], candidate)
            back = X.before_1019c(at)
            self.assertEqual((money_digest(back), digest(back)), X.DIGESTS_R2[candidate], candidate)
        self.assertEqual(set(X.DIGESTS_1019C.values()) & set(X.DIGESTS_R2.values()), set())
        off = X.before_a86()
        off["equity_money"]["event"]["enabled"] = False
        self.assertEqual((money_digest(off)[:8], digest(off)[:8]), ("1b7a5c22", "50e951c9"),
                         "the rollback: every event buy stopped, the row kept")

    def test_forty_open_entry_learning_lots_and_a_probe_close_entry_on_one_day_all_send(self):
        h = self.harness()
        n = 0

        def name(prefix: str, i: int) -> tuple[str, str]:
            nonlocal n
            n += 1
            sym = f"{prefix}{i:03d}"
            h.symbol(sym, last=1.0)
            h.venue.prints[(sym, DAY.isoformat(), "open")] = D("1.00")
            h.venue.prints[(sym, DAY.isoformat(), "close")] = D("1.01")
            return f"{n + 100:010d}", sym

        for i in range(16):        # READ-O1 takes eight; GUIDE-O1 the eight READ-O1 has no room for
            cik, sym = name("E", i)
            h.lane.filing(f"e-{i}", cik, accepted=iso(PRIOR, 16, 30), received=iso(PRIOR, 16, 31))
            h.lane.verdict(f"e-{i}", 3, answered=iso(PRIOR, 16, 35), guidance="raised")
            h.lane.universe(DAY, sym, cik, 1.0)
        for i in range(8):         # 8K-READ-O1
            cik, sym = name("K", i)
            h.lane.filing(f"k-{i}", cik, accepted=iso(PRIOR, 17, 0), received=iso(PRIOR, 17, 1), items=("8.01",))
            h.lane.verdict(f"k-{i}", 3, answered=iso(PRIOR, 17, 5))
            h.lane.universe(DAY, sym, cik, 1.0)
        for i in range(8):         # NEWS-READ-O1
            cik, sym = name("N", i)
            h.lane.article(f"n-{i}", sym, knowable=iso(DAY, 7, 30))
            h.lane.verdict(f"n-{i}", 3, answered=iso(DAY, 7, 35), news=True)
            h.lane.universe(DAY, sym, cik, 1.0)
        for i in range(8):         # INS-BUY-O1
            cik, sym = name("I", i)
            h.lane.insider_buy(f"f-{i}", cik, accepted=iso(PRIOR, 17, 0), usd=60000)
            h.lane.st.db.execute("UPDATE filings SET received_at=? WHERE accession=?", (iso(PRIOR, 17, 1), f"f-{i}"))
            h.lane.universe(DAY, sym, cik, 1.0)
        c1_event(h, 0)             # the close's entry: EVL-ERN-REACT-C1 at Probe (5% of E)
        h.lane.band("EVL-ERN-REACT-C1", "probe")
        # (The captain's A85: a learning OPEN buy leaves the close's Probe program its room. C1's last five close
        # decisions read one pick each, so $100 is held for it, and the forty $40 learning buys still fit the $1,950
        # above the reserve. With no decision on record its whole room, six $100 buys, would be held: 34 would go.)
        d = DAY
        for _ in range(5):
            d = ES.previous_session(d)
            h.state.upsert("eq_event_decisions", {
                "day": d.isoformat(), "at": "close", "decided_at": "x", "status": "done", "created_at": 0.0,
                "summary": json.dumps({"programs": {"EVL-ERN-REACT-C1": {"picks": 1, "room": 8}}})}, "day, at")
        self.ready(h)
        h.day()
        opens = [b for b in h.bodies() if b["side"] == "buy" and b["time_in_force"] == "opg"]
        sells = [b for b in h.bodies() if b["side"] == "sell"]
        closes = [b for b in h.bodies() if b["side"] == "buy" and b["time_in_force"] == "cls"]
        self.assertEqual((len(opens), len(sells), len(closes)), (40, 40, 1))
        by = {}
        for r in h.event_intents("buy"):
            by.setdefault(r["program"], []).append(r["status"])
        self.assertEqual({p: len(v) for p, v in by.items() if p != "EVL-ERN-REACT-C1"},
                         {"EVL-ERN-READ-O1": 8, "EVL-ERN-GUIDE-O1": 8, "EVL-8K-READ-O1": 8, "EVL-NEWS-READ-O1": 8,
                          "EVL-INS-BUY-O1": 8})
        self.assertEqual(by["EVL-ERN-REACT-C1"], ["done"], "the Probe close entry sent and filled")
        [c1] = closes
        self.assertEqual(c1["qty"], "56", "Probe: 3.5% of $2,000 at the $1.25 limit (A86; 80 at the old 5%)")
        day = DAY.isoformat()
        from league.equity import live as L

        self.assertEqual((L.event_orders_today(h.state.rows, day), L.orders_today(h.state.rows, day)), (81, 81),
                         "every order of the day is the event kind's: 81 of its 150, none of the old lanes' 60")

    def test_twelve_programs_on_a_heavy_day_refuse_preregevl4s_rows_first_and_never_an_exit(self):
        """A78 (the reading that trades less): the event kind's line stays 150 with twelve seatable programs, so on a day
        that needs more, ENTRIES stop in ROOM's order (Sized, Probe, learning; within a band PREREG-EVL-1's rows, then
        PREREG-EVL-2's, then PREREG-EVL-4's), PREREG-EVL-4's refused first, and an EXIT is never stopped by it. The day:
        the five open-entry programs' forty learning lots (bought at the open, sold at the close), the day's other event
        orders (67: the morning's sales of the overnight lots and the rest of a heavy day), then the close's sales (all
        forty go, past the line's entries) and its buys: EVL-ERN-REACT-C1 (PREREG-EVL-1) and EVL-NEWS-READ-ON
        (PREREG-EVL-2) take the last two orders the line allows (147 + 1 + its own exit, then 148 + 1 + 1), and
        EVL-8K-REACT-ON and EVL-8K-READ-ON (PREREG-EVL-4) are refused by the event kind's day order count."""
        from league.equity import live as L

        h = self.harness()
        n = 0

        def name(prefix: str, i: int) -> tuple[str, str]:
            nonlocal n
            n += 1
            sym = f"{prefix}{i:03d}"
            h.symbol(sym, last=1.0)
            h.venue.prints[(sym, DAY.isoformat(), "open")] = D("1.00")
            h.venue.prints[(sym, DAY.isoformat(), "close")] = D("1.01")
            return f"{n + 100:010d}", sym

        for i in range(16):        # the open: READ-O1 takes eight, GUIDE-O1 the eight READ-O1 has no room for
            cik, sym = name("E", i)
            h.lane.filing(f"e-{i}", cik, accepted=iso(PRIOR, 16, 30), received=iso(PRIOR, 16, 31))
            h.lane.verdict(f"e-{i}", 3, answered=iso(PRIOR, 16, 35), guidance="raised")
            h.lane.universe(DAY, sym, cik, 1.0)
        for i in range(8):         # 8K-READ-O1
            cik, sym = name("K", i)
            h.lane.filing(f"k-{i}", cik, accepted=iso(PRIOR, 17, 0), received=iso(PRIOR, 17, 1), items=("8.01",))
            h.lane.verdict(f"k-{i}", 3, answered=iso(PRIOR, 17, 5))
            h.lane.universe(DAY, sym, cik, 1.0)
        for i in range(8):         # NEWS-READ-O1
            cik, sym = name("N", i)
            h.lane.article(f"n-{i}", sym, knowable=iso(DAY, 7, 30))
            h.lane.verdict(f"n-{i}", 3, answered=iso(DAY, 7, 35), news=True)
            h.lane.universe(DAY, sym, cik, 1.0)
        for i in range(8):         # INS-BUY-O1
            cik, sym = name("I", i)
            h.lane.insider_buy(f"f-{i}", cik, accepted=iso(PRIOR, 17, 0), usd=60000)
            h.lane.st.db.execute("UPDATE filings SET received_at=? WHERE accession=?", (iso(PRIOR, 17, 1), f"f-{i}"))
            h.lane.universe(DAY, sym, cik, 1.0)
        c1 = c1_event(h, 0)        # the close: EVL-ERN-REACT-C1's (PREREG-EVL-1) mid-session earnings 8-K, +5%
        cik, news = name("D", 0)   # EVL-NEWS-READ-ON's (PREREG-EVL-2) day article, score 3
        h.lane.article("d-0", news, knowable=iso(DAY, 10, 30))
        h.lane.verdict("d-0", 3, answered=iso(DAY, 10, 35), news=True)
        h.lane.universe(DAY, news, cik, 1.0)
        # PREREG-EVL-4's two 8-K rows: two material 8.01 8-Ks knowable after PRIOR's close decision and before 09:00 ET
        # of DAY (F8K(DAY); no next-open guard), with no verdict by DAY's open (EVL-8K-READ-O1 buys neither there)
        cik, react = name("R", 0)  # EVL-8K-REACT-ON: its T29 minute at 1.05 x PRIOR's close
        h.lane.filing("r4-0", cik, accepted=iso(PRIOR, 17, 30), received=iso(PRIOR, 17, 31), items=("8.01",))
        h.lane.universe(DAY, react, cik, 1.0)
        h.lane.st.db.execute("INSERT INTO bars(symbol, day, adj, o, h, l, c, v, fetched_at) VALUES(?, ?, 'raw', 1, 1, 1, "
                             "1.0, 1e6, 'x')", (react, PRIOR.isoformat()))
        h.lane.st.db.execute("INSERT INTO marks(symbol, day, label, px, t, source, fetched_at) VALUES(?, ?, '1530', 1.05, "
                             "'x', 'sip-1min', 'x')", (react, DAY.isoformat()))
        cik, read = name("Q", 0)   # EVL-8K-READ-ON: its PROMPT-DOC score 2, answered at 10:00 ET of DAY
        h.lane.filing("q4-0", cik, accepted=iso(PRIOR, 18, 0), received=iso(PRIOR, 18, 1), items=("8.01",))
        h.lane.verdict("q4-0", 2, answered=iso(DAY, 10, 0))
        h.lane.universe(DAY, read, cik, 1.0)
        self.ready(h)
        day = DAY.isoformat()
        for hh, mm in ((9, 15), (9, 16), (9, 17), (9, 31), (9, 33)):
            h.tick(hh, mm)
        self.assertEqual(sum(1 for b in h.bodies() if b["side"] == "buy" and b["time_in_force"] == "opg"), 40)
        self.assertEqual(L.event_orders_today(h.state.rows, day), 40)
        [inst] = [r["id"] for r in h.state.rows("SELECT id FROM eq_instances WHERE lane=? AND family='EVL-INS-BUY-O1'",
                                                (L.EVENT_LANE,))]
        with h.state.transaction():  # the day's 67 other event orders (expired: no lot, no working order)
            for i in range(67):
                h.state.execute("INSERT INTO eq_orders(eid, client_id, instance, family, side, symbol, class, at, qty, "
                                "limit_px, collar_bp, status, placed_at, day, updated_at) VALUES(?, ?, ?, 'f', 'sell', "
                                "'ZZZ', 'stock', 'open', '1', '1', 0, 'expired', 0, ?, 0)",
                                (900000 + i, f"heavy-{i}", inst, day))
        self.assertEqual(L.event_orders_today(h.state.rows, day), 107)
        for hh, mm in ((15, 46), (15, 47), (15, 48), (16, 1), (16, 3)):
            h.tick(hh, mm)
        sells = [b for b in h.bodies() if b["side"] == "sell"]
        closes = {b["symbol"] for b in h.bodies() if b["side"] == "buy" and b["time_in_force"] == "cls"}
        self.assertEqual(len(sells), 40, "every exit of the day goes: none is stopped by the line")
        self.assertEqual(closes, {c1, news}, "PREREG-EVL-1's and PREREG-EVL-2's close entries take the line's last room")
        refused = {r["program"]: r["why"] for r in h.event_intents("buy") if r["day"] == day and r["at"] == "close"
                   and r["symbol"] in (react, read)}
        self.assertEqual(sorted(refused), ["EVL-8K-REACT-ON", "EVL-8K-READ-ON"], "PREREG-EVL-4's rows planned their buys")
        for program, why in refused.items():
            self.assertIn("the event kind's day order count: 149 of 150 sent", why or "", program)
        self.assertEqual(L.event_orders_today(h.state.rows, day), 149, "40 + 40 + 67 + 2, under the line")
        self.assertIsNone(h.book._count_refusal(day, exit_=True), "an exit still goes at the line")

    def test_each_lane_meets_its_own_line_and_both_the_house_wide_one(self):
        h = self.harness()
        book, day = h.book, DAY.isoformat()
        old = h.instance("seed-overnight-spy")
        event = h.instance("EVL-INS-BUY-O1", 2, lane="event")

        def orders(instance: str, count: int, start: int) -> None:
            with h.state.transaction():
                for i in range(start, start + count):
                    h.state.execute("INSERT INTO eq_orders(eid, client_id, instance, family, side, symbol, class, at, qty, "
                                    "limit_px, collar_bp, status, placed_at, day, updated_at) VALUES(?, ?, ?, 'f', 'buy', "
                                    "'S', 'stock', 'open', '1', '1', 0, 'filled', 0, ?, 0)",
                                    (i, f"c{i}", instance, day))
        orders(event.id, 100, 1)
        self.assertIsNone(book._count_refusal(day, exit_=False, event_line=150), "100 + 1 of the event kind's 150")
        self.assertIsNone(book._count_refusal(day, exit_=False), "none of them is the old lanes': 0 of 60")
        orders(old.id, 59, 1000)
        self.assertIsNone(book._count_refusal(day, exit_=False))
        orders(old.id, 1, 2000)
        self.assertIn("the equity day's order count: 60 of 60 sent", book._count_refusal(day, exit_=False) or "")
        self.assertIsNone(book._count_refusal(day, exit_=False, event_line=150), "the event kind's own line is apart")
        orders(event.id, 48, 3000)
        self.assertIsNone(book._count_refusal(day, exit_=False, event_line=150), "148 + 1 and its own exit of 150")
        orders(event.id, 1, 4000)
        self.assertIn("the event kind's day order count: 149 of 150 sent, 1 kept",
                      book._count_refusal(day, exit_=False, event_line=150) or "",
                      "the entry's own exit (the money review): 149 + 1 + 1 is above the line")
        orders(event.id, 1, 5000)
        self.assertIn("the event kind's day order count: 150 of 150 sent",
                      book._count_refusal(day, exit_=False, event_line=150) or "")
        self.assertIsNone(book._count_refusal(day, exit_=True), "an exit is never stopped by a lane's line")
        h.options.count = 40                   # 40 + 210 = 250: the House-wide line is full
        self.assertIn("the House's day order count: 250 sent of 250",
                      book._count_refusal(day, exit_=True) or "", "the House-wide line binds every order")

    # ---------------------------------------------------------------- release 1019c's money review: the exits' room
    def _open_window_then_close(self, h, options: int = 0) -> tuple[int, str, int, int, int]:
        """The open window's event buys of an open-entry program (each sold at that day's close) sent one by one while
        the count lets them, then the cross (each becomes an event lot) and the close's sales of every lot (EXITS: no
        lane's line may stop them). (buys sent, why the next was refused, sales sent, sales refused, the day's
        equity orders)."""
        from league.equity import live as L

        book, day = h.book, DAY.isoformat()
        event = h.instance("EVL-INS-BUY-O1", 2, lane="event")
        h.options.count = options

        def order(eid: int, side: str, status: str, iid: int | None = None, lid: int | None = None) -> None:
            h.state.execute("INSERT INTO eq_orders(eid, client_id, instance, family, side, symbol, class, at, qty, "
                            "limit_px, collar_bp, status, placed_at, day, updated_at, lid, iid) VALUES(?, ?, ?, 'f', ?, "
                            "?, 'stock', 'open', '1', '1', 0, ?, 0, ?, 0, ?, ?)",
                            (eid, f"c{eid}", event.id, side, f"S{eid % 100000}", status, day, lid, iid))

        buys, why = 0, None
        while buys < 400:
            why = book._count_refusal(day, exit_=False, event_line=150)
            if why is not None:
                break
            buys += 1
            with h.state.transaction():
                order(buys, "buy", "working", iid=buys)
                h.state.execute("INSERT INTO eq_event_intents(iid, program, version, event, side, tif, otype, symbol, day, "
                                "at, weight, exit_day, exit_at, decided_at, created_at) VALUES(?, 'EVL-INS-BUY-O1', 2, ?, "
                                "'buy', 'opg', 'limit', ?, ?, 'open', '0.10', ?, 'close', ?, 0)",
                                (buys, f"f4:e{buys}", f"S{buys}", day, day, day))
        with h.state.transaction():
            h.state.execute("UPDATE eq_orders SET status='filled' WHERE side='buy'")
        lids = []
        for i in range(buys):
            lot = L.Lot(book._next("eq_lots", "lid"), event.id, event.family, event.version, L.EVENT_LANE, f"S{i + 1}",
                        "stock", D("1"), D("1"), D("1"), D("1"), "open", opened_at=0, opened_day=day, cash=-D("1"),
                        probe=True)
            book._save_lot(lot)
            lids.append(lot.lid)
        sold = refused = 0
        for lid in lids:
            if book._count_refusal(day, exit_=True) is not None:
                refused += 1
                continue
            with h.state.transaction():
                order(200000 + lid, "sell", "working", lid=lid)
            sold += 1
        return buys, why or "", sold, refused, L.orders_today(h.state.rows, day)

    def test_the_open_windows_buys_keep_their_close_sales_room(self):
        """An auction buy is no lot until its cross: each open-window buy of an open-entry program keeps the exit it
        will need at that day's close (`_exit_reserve`), so the event line bounds the kind's whole day (75 buys and
        75 sales, 150) and no sale is refused (before the review: 150 buys, then 100 sales sent and 50 REFUSED at the
        House-wide line)."""
        buys, why, sold, refused, total = self._open_window_then_close(self.harness())
        self.assertEqual(buys, 75)
        self.assertIn("the event kind's day order count: 75 of 150 sent, 76 kept", why)
        self.assertEqual((sold, refused, total), (75, 0, 150), "every lot's exit goes")

    def test_an_entry_keeps_every_equity_exit_its_room_at_the_house_wide_line(self):
        """With the House-wide line filling (120 options orders), an event entry leaves the House-wide room for every
        equity exit and its own: 65 buys, and all 65 sales go, the day's line exactly full (before the review: 130
        buys and every one of their 130 sales REFUSED at the House-wide line)."""
        buys, why, sold, refused, total = self._open_window_then_close(self.harness(), options=120)
        self.assertEqual(buys, 65)
        self.assertIn("the House's day order count: 185 sent of 250", why)
        self.assertIn("66 kept for the equity book's exits, this entry's own included", why)
        self.assertEqual((sold, refused, total), (65, 0, 130), "every lot's exit goes")
        self.assertEqual(120 + total, 250, "the House-wide line exactly full, never over")


if __name__ == "__main__":
    unittest.main()
