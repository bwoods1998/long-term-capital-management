"""A84 (the captain's reading of 19:58Z Oct 21, 2026, recorded before any look; release 1019f): A69 (i)'s fast path
reads EACH FEED BY ITS OWN CLEAN READS. A record pass whose read of a feed errored, was cut, or had no tickers copy is a
MISSING read of that feed, not a broken span; the span is whole when, for each of 8-K, Form 4 and news separately, clean
reads of that feed are at most FAST_RECORD_GAP (15 minutes) apart from before the span's start through its end
(league/events/screen.py `_fast_passes`, `_feed_problems`); (ii) and (iii) are unchanged. The audit behind it (two
lenses, independently): SEC's getcurrent feed timed out in 9 record passes in 61 hours, each followed by a clean pass
within 2-4 minutes, so no span was ever whole under "every pass whole" and every look waited A66's three sessions.

And the stall job's `evl_final` (league/ops/evl_health.py): a seatable program's final record more than one session
behind what A69 allows, the program and the judge's why named.

Synthetic data only: every filing, article, receipt, decision and settled value here is invented; no market price is
read or computed."""

from __future__ import annotations

import copy
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from league.events import bands as BA
from league.events import calendar as C
from league.events import edgar as E
from league.events import programs as P
from league.events import screen as SC
from league.events import store as S
from league.ops import evl_health as EV
from league.ops import stall as ST
from league.tests import test_events_1019c as T19C
from league.tests import test_events_house as TH
from league.tests import test_events_review_1019b as R19B
from league.tests import test_evl_health as TE
from league.tests.test_events_screen import final_record

NY = C.NY
UTC = dt.timezone.utc
CLEAN = T19C.CLEAN
et = T19C.et
TWO = dt.timedelta(minutes=2)          # the House's RECORD_EVERY (league/events/house.py)
TIMEOUT = "TimeoutError: The read operation timed out"


class Feeds(unittest.TestCase):
    """TheFastPath's world (league/tests/test_events_1019c.py): look 1 of EVL-INS-BUY-O1 v2 due at days[7], the House's
    record final through days[8], the screen at 23:00 ET of days[8]; here the record passes run every 2 minutes, as the
    House runs them."""

    setUp, tearDown, settle = (R19B.LooksOnAFinalRecord.setUp, R19B.LooksOnAFinalRecord.tearDown,
                               R19B.LooksOnAFinalRecord.settle)
    passes, one_pass, spoil, due, written = (T19C.TheFastPath.passes, T19C.TheFastPath.one_pass,
                                             T19C.TheFastPath.spoil, T19C.TheFastPath.due, T19C.TheFastPath.written)
    P = "EVL-INS-BUY-O1"

    def every_two_minutes(self) -> dt.datetime:
        now = self.due()
        self.passes(et(self.days[0], 8), et(self.days[8], 12), every=TWO)
        return now

    def timeout(self, at: dt.datetime, feed: str) -> None:
        """SEC's getcurrent feed timing out in the pass of `at` (45 seconds, the audit's measure): that feed's read in
        error, the pass 2 minutes later gone (the House runs the next once the slow one ends) and a clean one 3 minutes
        after it."""
        body = copy.deepcopy(CLEAN) | {feed: {"error": TIMEOUT}}
        cur = self.st.db.execute("UPDATE receipts SET summary=?, finished_at=? WHERE job='record' AND started_at=?",
                                 (json.dumps(body), S.iso(at + dt.timedelta(seconds=46)), S.iso(at)))
        self.assertEqual(cur.rowcount, 1, at)
        self.st.db.execute("DELETE FROM receipts WHERE job='record' AND started_at=?", (S.iso(at + TWO),))
        self.one_pass(at + dt.timedelta(minutes=3))

    def final(self, now: dt.datetime) -> tuple[dt.date | None, str]:
        return SC.final_until(self.st, self.P, 2, self.days[8], now)

    # ------------------------------------------------------------------------------------------- the audit's replay
    def test_the_audits_replay_a_timeout_then_a_clean_pass_3_minutes_later_is_whole(self):
        """Four timeouts a night (22:24, 23:10, 23:54 and 00:50 ET, the 8-K and the Form 4 feed in turn) on every night
        of the record, each followed by a clean pass 3 minutes later: under A69's first reading every one broke its
        span; under A84 each is a missing read, the next clean one recovers it, and the look is written one session
        after its close."""
        now = self.every_two_minutes()
        for night in self.days[3:8]:
            for hh, mm, feed in ((22, 24, "8-K"), (23, 10, "4"), (23, 54, "8-K"), (0, 50, "4")):
                self.timeout(et(night + dt.timedelta(days=1) if hh == 0 else night, hh, mm), feed)
        missed = [r for r in self.st.db.execute("SELECT status, summary FROM receipts WHERE job='record'")
                  if SC._feed_problems(str(r["status"]), r["summary"])]
        self.assertEqual(len(missed), 20, "every one a missing read of one feed")
        self.assertTrue(all(len(SC._feed_problems(str(r["status"]), r["summary"])) == 1 for r in missed))
        self.assertEqual(self.final(now)[0], self.days[7], "final one session after it: the fast path fires")
        out = SC.run(self.st, self.days[8], draws=999, now=now)
        self.assertEqual(self.written(out), [(self.P, 1)])
        self.assertEqual(SC.look_rows(self.st, self.P, 2)[0]["at"][:10], self.days[7].isoformat(), "the as-of date")

    def test_a_feed_with_no_clean_read_for_20_minutes_is_not_whole(self):
        now = self.every_two_minutes()
        self.spoil(et(self.days[7], 22, 22), et(self.days[7], 22, 38), **{"8-K": {"error": TIMEOUT}})
        horizon, why = self.final(now)
        self.assertEqual(horizon, self.days[6], "days[7]'s windows hold the 20 minutes; days[6]'s end before them")
        self.assertIn(f"the fast path (A69) stops at {self.days[7].isoformat()}: no clean read of the 8-K feed from "
                      f"{S.iso(et(self.days[7], 22, 20))} to {S.iso(et(self.days[7], 22, 40))}, more than 15 minutes: "
                      f"the record pass of {S.iso(et(self.days[7], 22, 22))} had a 8-K feed error ({TIMEOUT})", why)
        self.assertIn("(9 passes missed it)", why)
        out = SC.run(self.st, self.days[8], draws=999, now=now)
        self.assertEqual(out["written"], [], "A66's rules hold the look")

    def test_the_gap_is_at_most_fifteen_minutes_between_clean_reads(self):
        now = self.every_two_minutes()
        self.spoil(et(self.days[7], 22, 22), et(self.days[7], 22, 36), news={"error": TIMEOUT})
        self.one_pass(et(self.days[7], 22, 35))             # clean news reads at 22:20 and 22:35: 15 minutes
        self.assertEqual(self.final(now)[0], self.days[7], "exactly FAST_RECORD_GAP apart is whole")
        self.st.db.execute("DELETE FROM receipts WHERE job='record' AND started_at=?", (S.iso(et(self.days[7], 22, 35)),))
        self.st.db.execute("DELETE FROM receipts WHERE job='record' AND started_at=?", (S.iso(et(self.days[7], 22, 36)),))
        horizon, why = self.final(now)                      # 22:20 to 22:38: 18 minutes
        self.assertEqual(horizon, self.days[6])
        self.assertIn(f"no clean read of the news feed from {S.iso(et(self.days[7], 22, 20))} to "
                      f"{S.iso(et(self.days[7], 22, 38))}", why)

    def test_each_feed_needs_clean_reads_across_a_spans_start(self):
        """Every close's span from 09:00 ET of the session before it: 21 minutes with no pass at days[6]'s 09:00 (inside
        days[6]'s span) hold days[6], and so days[7]; a pass at 08:50 that missed the Form 4 feed leaves that feed's
        gap; a clean pass at 08:55 closes it (15 minutes after the last clean read at 08:40)."""
        now = self.due()
        self.passes(et(self.days[0], 8), et(self.days[6], 8, 40), every=dt.timedelta(minutes=10))
        self.passes(et(self.days[6], 9, 1), et(self.days[8], 12), every=TWO)
        horizon, why = self.final(now)
        self.assertEqual(horizon, self.days[5])
        self.assertIn(f"stops at {self.days[6].isoformat()}: no record pass ran from {S.iso(et(self.days[6], 8, 40))} "
                      f"to {S.iso(et(self.days[6], 9, 1))}", why)
        self.one_pass(et(self.days[6], 8, 50), **{"4": {"error": TIMEOUT}})
        horizon, why = self.final(now)
        self.assertEqual(horizon, self.days[5])
        self.assertIn(f"stops at {self.days[6].isoformat()}: no clean read of the Form 4 feed from "
                      f"{S.iso(et(self.days[6], 8, 40))} to {S.iso(et(self.days[6], 9, 1))}", why)
        self.one_pass(et(self.days[6], 8, 55))
        self.assertEqual(self.final(now)[0], self.days[7])

    # ------------------------------------------------------------------------------------ each feed by its own reads
    def test_each_feed_is_judged_by_its_own_reads(self):
        """Two hours in which EVERY pass misses one feed, the 8-K, Form 4 and news feeds in turn: each feed is read
        cleanly at least every 6 minutes, so the span is whole (A69's first reading failed every one of them). Then the
        news alone missing for 30 minutes: the why names the news feed and no other."""
        now = self.every_two_minutes()
        at, i = et(self.days[7], 20), 0
        while at <= et(self.days[7], 22):
            feed = SC.RECORD_FEEDS[i % 3]
            part = {"cut": True} if feed == "news" and i % 2 else {"error": TIMEOUT}
            self.spoil(at, at, **{feed: part})
            at, i = at + TWO, i + 1
        self.assertEqual(self.final(now)[0], self.days[7], "each feed's clean reads at most 6 minutes apart")
        self.spoil(et(self.days[7], 23), et(self.days[7], 23, 30), news={"error": TIMEOUT})
        horizon, why = self.final(now)
        self.assertEqual(horizon, self.days[6])
        self.assertIn("no clean read of the news feed from", why)
        self.assertIn("had a news error", why)
        self.assertNotIn("8-K", why)
        self.assertNotIn("Form 4", why)

    def test_one_feeds_errors_never_judge_another(self):
        now = self.every_two_minutes()
        for feed, part, name, needle in (("4", {"error": TIMEOUT, "fetched": 2}, "Form 4", "had a 4 feed error"),
                                         ("news", {"cut": True}, "news", "cut its news read short"),
                                         ("8-K", {"error": TIMEOUT}, "8-K", "had a 8-K feed error")):
            with self.subTest(feed=feed):
                self.spoil(et(self.days[7], 22), et(self.days[7], 23, 58), **{feed: part})
                horizon, why = self.final(now)
                self.assertEqual(horizon, self.days[6])
                self.assertIn(f"no clean read of the {name} feed from", why)
                self.assertIn(needle, why)
                self.assertNotIn("record pass ran", why)
                self.spoil(et(self.days[7], 22), et(self.days[7], 23, 58))      # the clean passes again
                self.assertEqual(self.final(now)[0], self.days[7])

    def test_no_tickers_copy_is_a_missing_8k_read_only(self):
        """No tickers copy holds the 8-Ks (none is fetched without it), never the Form 4s or the news."""
        now = self.every_two_minutes()
        self.timeout(et(self.days[7], 22, 24), "8-K")
        self.spoil(et(self.days[7], 23), et(self.days[7], 23, 4), tickers={"error": "OSError: invented"})
        self.assertEqual(self.final(now)[0], self.days[7], "4 minutes without it, then a clean 8-K read")
        self.spoil(et(self.days[7], 23), et(self.days[7], 23, 30), tickers={"error": "OSError: invented"})
        horizon, why = self.final(now)
        self.assertEqual(horizon, self.days[6])
        self.assertIn("no clean read of the 8-K feed from", why)
        self.assertIn("could not read the tickers copy (its 8-Ks waited)", why)
        self.assertEqual(SC._feed_problems("ok", json.dumps(CLEAN | {"tickers": {"error": "x"}})),
                         {"8-K": "could not read the tickers copy (its 8-Ks waited)"})
        self.assertEqual(set(SC._feed_problems("failed", json.dumps({"error": "x"}))), set(SC.RECORD_FEEDS),
                         "a pass that raised read no feed")
        self.assertEqual(set(SC._feed_problems("ok", "not json")), set(SC.RECORD_FEEDS))
        self.assertEqual(SC._feed_problems("ok", json.dumps(CLEAN)), {})

    # --------------------------------------------------------------------------------- (ii), (iii) and A82 unchanged
    def test_ii_and_iii_and_the_a82_backfill_are_unchanged(self):
        """With (i) whole by A84 (a timeout, a clean pass 3 minutes later), a filing of X's windows still failed or
        listed holds X ((ii)), and so does a weekday whose daily-index backfill (A82's, filing by filing) has not run
        ((iii)): A84 moves no other condition."""
        now = self.every_two_minutes()
        self.timeout(et(self.days[7], 22, 24), "8-K")
        self.assertEqual(self.final(now)[0], self.days[7])
        accepted = et(self.days[7], 10)

        def filing(acc: str, form: str, status: str) -> None:
            self.st.db.execute("INSERT INTO filings(accession, form, cik, company, items, accepted_at, knowable_at, "
                               "received_at, source, status) VALUES(?, ?, '0000000777', 'Invented', '[]', ?, ?, ?, "
                               "'current', ?)", (acc, form, S.iso(accepted), S.iso(E.knowable(accepted)),
                                                 S.iso(accepted), status))
        for acc, form, status, needle in (("x-1", "4", "failed:OSError:invented", "filing x-1 (4) is failed"),
                                          ("x-2", "4", "listed", "filing x-2 (4) is still listed")):
            with self.subTest(acc=acc):
                filing(acc, form, status)
                horizon, why = self.final(now)
                self.assertEqual(horizon, self.days[6])
                self.assertIn(f"stops at {self.days[7].isoformat()}: {needle}", why)
                self.st.db.execute("DELETE FROM filings WHERE accession=?", (acc,))
        key = f"evl:backfill:{self.days[7].isoformat()}"
        self.st.db.execute("DELETE FROM meta WHERE key=?", (key,))
        horizon, why = self.final(now)
        self.assertEqual(horizon, self.days[6])
        self.assertIn(f"the daily-index backfill of {self.days[7].isoformat()} has not run", why)
        self.st.set_meta(key, "done")
        self.assertEqual(self.final(now)[0], self.days[7])

    def test_the_fast_path_still_waits_for_the_next_sessions_open_decision(self):
        now = self.every_two_minutes()
        self.timeout(et(self.days[7], 22, 24), "8-K")
        early = et(self.days[8], 9, 10)                     # days[8]'s open decision is at 09:15
        horizon, why = SC.final_until(self.st, self.P, 2, self.days[8], early)
        self.assertEqual(horizon, self.days[6])
        self.assertIn(f"the session after it ({self.days[8].isoformat()}) has not had its open decision", why)
        self.assertEqual(self.final(now)[0], self.days[7])


# ====================================================================================== the House's own receipts
class TheHousesOwnReceipts(TH.LaneCase):
    """A84's soundness on the House's own record pass (league/events/house.py `_record`): a getcurrent timeout writes
    the 8-K read's `error` and nothing else, the next pass pages back to the newest known accession and fetches the
    filing accepted meanwhile, and the screen reads the receipts the House wrote as whole; 20 minutes of timeouts do
    not."""

    def setUp(self):
        super().setUp()
        with self.store() as st:     # the backfill and the nightly jobs are not this test's
            for day in ("2026-10-15", "2026-10-16", "2026-10-19"):
                st.set_meta(f"evl:backfill:{day}", "done")
        self.down = False
        real = self.sec.__call__

        def sec(url: str) -> bytes:
            if self.down and "action=getcurrent" in url and "type=8-K" in url:
                raise TimeoutError("The read operation timed out")
            return real(url)
        self.lane._sec_base = sec

    def record_at(self, wall: str) -> dict:
        self.at(TH.et("2026-10-20", wall))
        last = self.turn()
        self.assertEqual((last["task"], last["status"]), ("record", "ok"), wall)
        return json.loads(self.receipts("record")[-1]["summary"])

    def whole(self, start: str, end: str) -> str | None:
        with self.store() as st:
            return SC._fast_passes(st, TH.et("2026-10-20", start), TH.et("2026-10-20", end), {})

    def test_a_timeout_then_a_clean_pass_recovers_the_filing_and_reads_whole(self):
        self.assertEqual(SC._feed_problems("ok", json.dumps(self.record_at("07:01"))), {})
        self.sec.add("0000000001-26-000301", "0000000001", "2026-10-20 07:02:00")      # accepted between the passes
        self.down = True
        missed = self.record_at("07:03")
        self.assertEqual(SC._feed_problems("ok", json.dumps(missed)),
                         {"8-K": "had a 8-K feed error (TimeoutError: The read operation timed out)"})
        with self.store() as st:
            self.assertIsNone(st.db.execute("SELECT 1 FROM filings").fetchone(), "the failed read stored nothing")
        self.down = False
        self.assertEqual(SC._feed_problems("ok", json.dumps(self.record_at("07:06"))), {})
        with self.store() as st:
            self.assertEqual(st.db.execute("SELECT status FROM filings WHERE accession='0000000001-26-000301'")
                             .fetchone()[0], "fetched", "the clean read after the failed one recovered it")
        self.assertIsNone(self.whole("07:01", "07:06"), "A84: one missing read, the next clean 3 minutes later")
        self.down = True
        for minute in range(8, 26, 2):                      # 07:08 to 07:24: nine passes, every 8-K read timed out
            self.record_at(f"07:{minute:02d}")
        self.down = False
        self.record_at("07:26")
        why = self.whole("07:01", "07:26")
        self.assertIn("no clean read of the 8-K feed from 2026-10-20T11:06:00Z to 2026-10-20T11:26:00Z", why)
        self.assertIn("(9 passes missed it)", why)
        self.assertIsNone(self.whole("07:01", "07:07"))


# ========================================================================================= the stall job's evl_final
class FinalRecordAlarm(unittest.TestCase):
    """`evl_final` (league/ops/evl_health.py): a seatable program's final record (screen.final_until) more than one
    session behind what A69 allows, judged from the lane's store read-only, the program and the judge's why named."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "state"
        self.st = S.Store(self.root / "events")
        self.addCleanup(self.st.close)
        C.refresh(self.st, R19B.CalendarGateway({}), dt.date(2026, 10, 1), dt.date(2027, 3, 31))
        self.days = [s.day for s in C.sessions(self.st, dt.date(2026, 10, 20), dt.date(2027, 3, 31))]
        self.now = final_record(self.st, self.days[8])         # 23:00 ET of days[8]
        self.errors: list[str] = []

    def passes(self, start: dt.datetime, end: dt.datetime, every: dt.timedelta = dt.timedelta(minutes=10)) -> None:
        T19C.TheFastPath.passes(self, start, end, every=every)

    def check(self, now: dt.datetime | None = None) -> dict:
        self.errors = []
        out = EV.checks({"config": {"events": {"enabled": True}}, "settings": {}}, self.root,
                        (now or self.now).timestamp(), errors=self.errors)
        return out["evl_final"]

    def test_a_fast_path_that_never_fires_stands_naming_the_program_and_the_why(self):
        """No record pass on record (A69 (i) never met, the audit's finding in effect): every seatable program waits
        A66's three sessions, two behind what A69 allows."""
        check = self.check()
        first = P.SEATING[0]
        self.assertTrue(check["stalled"], check["what"])
        self.assertIn(f"The event lane's final record of {first.id} v{first.version} reaches "
                      f"{self.days[5].isoformat()} while A69's fast path allows {self.days[7].isoformat()}: 2 sessions "
                      f"behind, so its looks wait ({len(P.SEATING)} programs lag more than 1 session).", check["what"])
        self.assertIn("The judge: the re-decision window reaches", check["what"])
        self.assertIn("no record pass ran from", check["what"])
        self.assertLessEqual(len(check["what"]), 400, "the gateway's sentence")
        n = check["numbers"]
        self.assertEqual((n["programs"], n["lagging"], n["program"], n["version"], n["final_through"], n["a69_allows"],
                          n["lag_sessions"], n["max_lag_sessions"]),
                         (len(P.SEATING), len(P.SEATING), first.id.lower(), first.version, self.days[5].isoformat(),
                          self.days[7].isoformat(), 2, 2))
        self.assertEqual(check["onset"], et(self.days[8], 9, 15).timestamp(), "since A69 first allowed days[7]")
        self.assertIsNone(check["owner_step"])
        self.assertEqual(self.errors, [])

    def test_a_whole_record_clears_it_and_the_a84_replay_keeps_it_clear(self):
        """Passes every 2 minutes, as the House runs them, one 8-K read timed out in days[6]'s and days[7]'s windows:
        each feed's clean reads stay at most 4 minutes apart, and every program is final through days[7]."""
        self.passes(et(self.days[0], 8), et(self.days[8], 12), every=TWO)
        cur = self.st.db.execute("UPDATE receipts SET summary=? WHERE job='record' AND started_at=?",
                                 (json.dumps(copy.deepcopy(CLEAN) | {"8-K": {"error": TIMEOUT}}),
                                  S.iso(et(self.days[6], 22))))
        self.assertEqual(cur.rowcount, 1)
        check = self.check()
        self.assertFalse(check["stalled"], check["what"])
        self.assertEqual(check["what"], f"Every seatable program's final record is within 1 session of what A69's fast "
                                        f"path allows ({self.days[7].isoformat()}; {len(P.SEATING)} programs).")
        self.assertEqual((check["numbers"]["lagging"], check["numbers"]["max_lag_sessions"]), (0, 0))

    def test_one_session_behind_is_tolerated(self):
        self.passes(et(self.days[0], 8), et(self.days[8], 12))
        self.st.db.execute("DELETE FROM meta WHERE key=?", (f"evl:backfill:{self.days[7].isoformat()}",))
        check = self.check()
        self.assertFalse(check["stalled"], check["what"])
        self.assertEqual(check["numbers"]["max_lag_sessions"], 1)

    def test_a_feed_missing_for_20_minutes_two_sessions_back_stands_with_the_feed_named(self):
        self.passes(et(self.days[0], 8), et(self.days[8], 12))
        self.st.db.execute("UPDATE receipts SET summary=? WHERE job='record' AND started_at>=? AND started_at<=?",
                           (json.dumps(copy.deepcopy(CLEAN) | {"4": {"error": TIMEOUT}}), S.iso(et(self.days[6], 12)),
                            S.iso(et(self.days[6], 12, 10))))
        check = self.check()
        self.assertTrue(check["stalled"])
        self.assertIn("no clean read of the Form 4 feed from", check["what"])
        self.assertEqual(check["numbers"]["final_through"], self.days[5].isoformat())

    def test_a_retired_program_or_one_not_yet_registered_is_not_judged(self):
        first = P.SEATING[0]
        BA.set_band(self.st, first.id, first.version, "retired", since=S.iso(self.now), why="invented")
        check = self.check()
        self.assertEqual(check["numbers"]["programs"], len(P.SEATING) - 1)
        self.assertNotEqual(check["numbers"]["program"], first.id.lower())
        before = min(p.registered_at for p in P.SEATING) - dt.timedelta(minutes=1)
        self.assertFalse(self.check(before)["judged"], "no program registered yet: not judged")

    def test_a_registered_seatable_birth_is_judged_too_and_the_table_is_left_as_it_was(self):
        """Release 1019f's integration with release 1019e's births: the stall job's process holds no birth until
        `final_lags` loads them from the same read-only store; a seatable birth is a seating program like any other."""
        from league.events import births as BI
        from league.tests.test_events_births import spec

        sp = spec("EVL-B-8K-502", "8k", {"items": ["5.02"]})
        self.st.db.execute("INSERT INTO births(id, version, sha, spec, seatable, registered_at, committed_at, "
                           "received_at, path, commit_sha, seq, line, why, by, night) VALUES(?, 1, ?, ?, 1, ?, ?, ?, "
                           "'docs/births/2026-10-20.jsonl', ?, 0, '{}', 'x', 'captain', '2026-10-20')",
                           (sp["id"], BI.sha(sp), BI.canonical(sp), "2026-10-21T01:00:00Z", "2026-10-21T01:00:00Z",
                            "2026-10-21T01:00:00Z", "c" * 40))
        self.assertEqual(P.BIRTHS, (), "no birth loaded in this process")
        lags = EV.final_lags(self.root, self.now.timestamp())
        self.assertIn(("EVL-B-8K-502", 1), {(r["program"], r["version"]) for r in lags})
        self.assertEqual(len(lags), len(P.PREREG_SEATING) + 1)
        self.assertEqual((P.BIRTHS, len(P.SEATING)), ((), len(P.PREREG_SEATING)), "the table left as it was")
        self.assertEqual(self.check()["numbers"]["programs"], len(P.PREREG_SEATING) + 1)

    def test_its_own_failure_blinds_no_other_cause(self):
        with mock.patch.object(EV, "final_lags", side_effect=RuntimeError("invented")):
            out = EV.checks({"config": {"events": {"enabled": True}}, "settings": {}}, self.root,
                            self.now.timestamp(), errors=self.errors)
        self.assertEqual((out["evl_final"]["stalled"], out["evl_final"]["judged"]), (False, False))
        self.assertEqual(self.errors, ["the event lane's final records could not be read (RuntimeError): evl_final is "
                                       "not judged"])
        self.assertTrue(out["evl_record"]["judged"])

    def test_it_reads_the_store_and_writes_nothing(self):
        """Inside `guard.readonly()` every connection is `mode=ro`: the judge's horizon is read, nothing is written."""
        counts = lambda: [self.st.db.execute(f"SELECT count(*) FROM {t}").fetchone()[0]  # noqa: E731
                          for t in ("receipts", "meta", "looks", "bands", "band_history")]
        before = counts()
        check = self.check()
        self.assertTrue(check["judged"])
        self.assertEqual(self.errors, [])
        self.assertEqual(counts(), before)


class FinalThroughTheStallJob(TE.StallHarness):
    """`evl_final` through the stall job: among its CAUSES, standing in its checks and mailed (INFO, no owner step)."""

    def test_the_stall_job_raises_and_mails_it(self):
        st = S.Store(self.root / "events")
        try:
            C.refresh(st, R19B.CalendarGateway({}), dt.date(2026, 10, 1), dt.date(2027, 3, 31))
            days = [s.day for s in C.sessions(st, dt.date(2026, 10, 20), dt.date(2027, 3, 31))]
            now = final_record(st, days[8]).timestamp()
        finally:
            st.close()
        self.assertIn("evl_final", ST.CAUSES)
        out = ST.run(self.ctx(now=now))
        self.assertIn("evl_final", out["stalled"])
        self.assertTrue(out["notice"]["sent"])
        entry = self.notify.entry("evl_final")
        self.assertIsNone(entry["owner_step"])
        self.assertEqual(entry["numbers"]["lag_sessions"], 2)
        self.assertIn("A69's fast path allows", entry["what"])


if __name__ == "__main__":
    unittest.main()
