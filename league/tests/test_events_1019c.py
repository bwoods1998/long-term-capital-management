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
from league.events import book as EB
from league.events import calendar as C
from league.events import edgar as E
from league.events import programs as P
from league.events import run as R
from league.events import screen as SC
from league.events import store as S
from league.tests import equity_design as X
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
    """A69: a close X is final once the session after X has had its open decision when (i) every record pass from the
    start of X's earliest window through that decision read its feeds whole, (ii) no filing of those windows the lane
    would fetch is still listed or failed, (iii) the daily-index backfills of the days of X's windows have run and
    (iv) every decision of the program's entry kind through X is made; otherwise A66's three sessions."""

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
        now = self.due()
        self.passes(et(self.days[0], 8), et(self.days[8], 12))
        self.one_pass(et(self.days[6], 12, 1), news={"error": "OSError: invented"})
        self.keeps_a66(now, f"stops at {self.days[6].isoformat()}: the record pass of")
        why = SC.final_until(self.st, self.P, 2, self.days[8], now)[1]
        self.assertIn("had a news error (OSError: invented)", why)

    def bad_pass(self, needle: str, *, status: str = "ok", **parts) -> None:
        now = self.due()
        self.passes(et(self.days[0], 8), et(self.days[8], 12))
        self.one_pass(et(self.days[7], 11, 1), status=status, **parts)
        horizon, why = SC.final_until(self.st, self.P, 2, self.days[8], now)
        self.assertEqual(horizon, self.days[6], "days[6]'s windows end before the bad pass; days[7]'s do not")
        self.assertIn(needle, why)

    def test_a_cut_news_read_keeps_a66(self):
        self.bad_pass("cut its news read short", news={"cut": True})

    def test_an_8k_feed_error_keeps_a66(self):
        self.bad_pass("had a 8-K feed error (GatewayError: 503)", **{"8-K": {"error": "GatewayError: 503"}})

    def test_a_form_4_feed_error_keeps_a66(self):
        self.bad_pass("had a 4 feed error", **{"4": {"error": "GatewayError: 503", "fetched": 2}})

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
        """A news error in days[6]'s windows only (days[5] 12:00): days[7]'s own passes are clean, but days[6] is not
        final, so neither is days[7]."""
        now = self.due()
        self.passes(et(self.days[0], 8), et(self.days[8], 12))
        self.one_pass(et(self.days[5], 12, 1), news={"error": "OSError: invented"})
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


# ================================================================================ A66 owed: what a re-decision writes
class ARedecisionWritesOnlyWhatIsOpen(unittest.TestCase):
    """A66 (owed): a re-decision of a session OUTSIDE the re-decision window writes intents only for the programs its
    own receipt was pending on; and (A69) never for a program whose own look already stands over the session, so a
    late-stored event can never land under a look already written."""

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

    def test_outside_the_window_only_the_programs_it_was_pending_on_are_decided(self):
        first = self.pending_monday()
        friday = dt.datetime(2026, 10, 23, 14, 0, tzinfo=UTC)     # Tue, Wed, Thu and Fri have had their opens
        self.assertTrue(SC.outside_window(self.st, self.MONDAY, friday))
        out = self.decide(friday)
        self.assertEqual(out["pending"], {})
        self.assertEqual(self.symbols("EVL-ERN-READ-O1"), ["AAA"], "a program it was pending on is decided")
        self.assertEqual(self.symbols("EVL-ERN-READ-O1", 2), ["AAA"])
        self.assertEqual(self.symbols("EVL-ERN-GUIDE-O1", 2), ["AAA", "BBB"], "the late event too, for that program")
        self.assertEqual(self.symbols("EVL-CTRL-ERN-ALL-O1"), ["AAA"],
                         "the control was not pending: its session is final, the late event never lands in it")
        self.assertIn("outside the re-decision window", out["kept"]["EVL-CTRL-ERN-ALL-O1"])
        self.assertEqual(set(out["kept"]) & set(first["pending"]), set())
        receipt = self.st.db.execute("SELECT status FROM receipts WHERE job='decide-open:2026-10-19' ORDER BY id DESC "
                                     "LIMIT 1").fetchone()[0]
        self.assertEqual(receipt, "ok")
        again = self.decide(friday + dt.timedelta(hours=1))
        self.assertIn("EVL-ERN-READ-O1", again["kept"], "an ok receipt was pending on none: nothing is decided again")
        self.assertEqual(self.symbols("EVL-CTRL-ERN-ALL-O1"), ["AAA"])

    def test_inside_the_window_every_program_is_decided_again(self):
        self.pending_monday()
        tuesday = dt.datetime(2026, 10, 20, 14, 0, tzinfo=UTC)
        self.assertFalse(SC.outside_window(self.st, self.MONDAY, tuesday))
        out = self.decide(tuesday)
        self.assertNotIn("kept", out)
        self.assertEqual(self.symbols("EVL-CTRL-ERN-ALL-O1"), ["AAA", "BBB"], "inside the window the late event lands")

    def test_a_failed_run_after_a_pending_one_keeps_the_pending_ones_scope(self):
        self.pending_monday()
        rid = self.st.start_receipt("decide-open:2026-10-19")
        self.st.finish_receipt(rid, "failed", {"why": "GatewayError: invented"})
        out = self.decide(dt.datetime(2026, 10, 23, 14, 0, tzinfo=UTC))
        self.assertIn("EVL-CTRL-ERN-ALL-O1", out["kept"])
        self.assertEqual(self.symbols("EVL-CTRL-ERN-ALL-O1"), ["AAA"])

    def test_a_program_whose_look_stands_over_the_session_gets_no_late_event_inside_the_window(self):
        self.store(self.BBB)
        first = self.decide(self.now)
        self.assertEqual(first["pending"], {})
        self.store(self.AAA)                 # stored late
        self.st.db.execute("INSERT INTO looks(program, version, k, at, held, passed) VALUES('EVL-ERN-READ-O1', 2, 1, ?, "
                           "1, 0)", (S.iso(C.session(self.st, self.MONDAY).close_at),))
        out = self.decide(dt.datetime(2026, 10, 20, 14, 0, tzinfo=UTC))
        self.assertIn("is written over this session", out["kept"]["EVL-ERN-READ-O1@v2"])
        self.assertEqual(self.symbols("EVL-ERN-READ-O1", 2), [], "under its written look: nothing lands")
        self.assertEqual(self.symbols("EVL-ERN-READ-O1"), ["AAA"], "version 1 has no look: it takes the late event")
        self.assertEqual(self.symbols("EVL-CTRL-ERN-ALL-O1"), ["BBB"],
                         "READ-O1's control: the written look read its record, so it is frozen with it")
        self.assertIn("is written over this session", out["kept"]["EVL-CTRL-ERN-ALL-O1"])
        self.assertEqual(self.symbols("EVL-ERN-GUIDE-O1", 2), ["AAA", "BBB"], "no look of its own: the late event lands")

    def test_a_close_entry_look_freezes_only_the_sessions_it_covers(self):
        c1 = EB.program_of("EVL-ERN-REACT-C1", 2)
        self.st.db.execute("INSERT INTO looks(program, version, k, at, held, passed) VALUES(?, 2, 1, ?, 1, 0)",
                           (c1.id, S.iso(C.session(self.st, self.MONDAY).close_at)))
        tuesday = dt.datetime(2026, 10, 20, 21, 0, tzinfo=UTC)
        self.assertIsNone(R._scope(self.st, "close", self.MONDAY, tuesday)(c1),
                          "Monday's C1 entries exit Tuesday's close: a look as of Monday does not cover them")
        friday = dt.date(2026, 10, 16)
        self.assertIn("is written over this session", R._scope(self.st, "close", friday, tuesday)(c1))


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
        self.assertGreaterEqual(event["max_orders_day"], 2 * len(EB.seatable()) * event["max_open"]["learning"],
                                "every program's full learning room bought and sold in one day")
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
        self.assertEqual((money_digest()[:8], digest()[:8]), ("055e5313", "a8d4cbd9"))
        before = X.before_1019c()
        self.assertEqual((money_digest(before), digest(before)), X.DIGESTS_R2[pair], "release 1019b's pair, exactly")
        self.assertEqual((money_digest(before)[:8], digest(before)[:8]), ("285fa7af", "fd38e4e1"))
        for candidate in X.CANDIDATES:
            at = X.constitution_at(*candidate)
            self.assertEqual((money_digest(at), digest(at)), X.DIGESTS[candidate], candidate)
            back = X.before_1019c(at)
            self.assertEqual((money_digest(back), digest(back)), X.DIGESTS_R2[candidate], candidate)
        self.assertEqual(set(X.DIGESTS.values()) & set(X.DIGESTS_R2.values()), set())
        off = copy.deepcopy(CONSTITUTION)
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
        self.assertEqual(c1["qty"], "80", "Probe: 5% of $2,000 at the $1.25 limit")
        day = DAY.isoformat()
        from league.equity import live as L

        self.assertEqual((L.event_orders_today(h.state.rows, day), L.orders_today(h.state.rows, day)), (81, 81),
                         "every order of the day is the event kind's: 81 of its 150, none of the old lanes' 60")

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
        orders(event.id, 49, 3000)
        self.assertIsNone(book._count_refusal(day, exit_=False, event_line=150), "149 + 1 of 150")
        orders(event.id, 1, 4000)
        self.assertIn("the event kind's day order count: 150 of 150 sent",
                      book._count_refusal(day, exit_=False, event_line=150) or "")
        self.assertIsNone(book._count_refusal(day, exit_=True), "an exit is never stopped by a lane's line")
        h.options.count = 40                   # 40 + 210 = 250: the House-wide line is full
        self.assertIn("the House's day order count: 250 sent of 250",
                      book._count_refusal(day, exit_=True) or "", "the House-wide line binds every order")


if __name__ == "__main__":
    unittest.main()
