"""PREREG-EVL-5 (frozen; tag `prereg-evl-5`, commit b73f205f, registered 2026-10-21T21:26:21Z, A92): three new seatable
programs at PREREG-EVL-3's learning band from birth, their version 1 the seating version, and one control. Held here,
on invented rows only (league/tests/evl5_world.py), ONE TEST A CLAUSE of the frozen text:

- the rows as frozen (section 1.2's ids, families, entry at D's close and exit at the next open, hold 1, PREREG-EVL-2's
  limit at entry), their own registration time, the seating gate, SEATING (1.5 of the lane's stated 3.0 expected false
  passes, section 3), the judge's registries, PREREG-EVL-3's screen at version 1 (seed strings `{id}|v1|look{k}`);
- section 1.1's terms: D's close window (ERN(D), item 2.02, 8-K/A out), the reaction, DAY(D), TAKEN AT D'S CLOSE BY AN
  EARLIER ROW (a), (b), (c) and the wait, the attention articles of P, NO NEW INFORMATION (i) (any source, any symbols,
  PREREG-EVL-1 section 3's non-live exclusion), (ii) (any 8-K from P''s close decision) and (iii) (an insider buy from
  09:00 ET of P), the gap (D's 09:30 minute's open over P's close), each window's knowable-time boundaries, and the sets
  that skip carrying no registration floor;
- section 1.2's rules and rankings: EVL-ERN-DROP-ON (<= 0.96, the fall), EVL-ERN-UNDER-ON (above 0.96 and below 1.04
  with an `ok` score >= 2, the score plus 0.5 raised, one an issuer, the highest score then the earliest), its control
  (every muted filing, scored first, waiting for the scores, never for a TEXT with none), EVL-NEWS-NIGHT2-ON (the gap
  >= 1.02, the issuer's earliest attention article), NO NEW PROMPT AND NO SECOND VERDICT, and the three sharing no
  (issuer, D) with one another and no (issuer, entry, exit) with the twelve earlier seatable programs;
- section 1.3: real money over the rows stored and the verdicts answered before D's close decision (TAKEN, the
  skips and NO NEW INFORMATION read from them; an unanswered DAY(D) article skips its issuer), the gap from the lane's
  stored minute or the book's own read, the extended next-open guard (score >= 2, or >= 1 with guidance raised, or
  unanswered; PREREG-EVL-4's guard unchanged), ROOM after PREREG-EVL-4's rows and before the births; THE EARLIER ROWS'
  DECISION COMES FIRST: the part runs last under its own bound, its failure or expiry finishes the receipt with the
  earlier rows whole and names none of its rows, `decide-close-evl5` decides them later and real money never trades
  that close; the heavy reads of EVL-NEWS-NIGHT2-ON in the session's pre-passes from 09:47 ET, which give what one
  computation at the close gives;
- section 2's final record for these rows (A69's span from P''s close decision, A74 (3)'s backfill from P' through X;
  A84's per-feed reading when merged, A69's otherwise; A66 otherwise) and section 3's record before the release
  (`decide-close-evl5` of every close since the registration a release without them decided, oldest first, once);
- THE PROOF: on the invented week, every earlier program's (PREREG-EVL-1 to -4 and two registered births) shadow intents
  and real-money picks are the same with and without PREREG-EVL-5's rows (the same week decided by release 1019e's own
  code gives them too: `python league/tests/evl5_world.py OUT.json` with that tree on PYTHONPATH)."""

from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
import json
import re
import sqlite3
import tempfile
import unittest
from decimal import Decimal
from decimal import Decimal as D_
from pathlib import Path
from typing import Callable
from unittest import mock

from league import ci
from league.equity import live as L
from league.events import book as EB
from league.events import calendar as C
from league.events import house as H
from league.events import programs as P
from league.events import report as RP
from league.events import run as R
from league.events import score as SCORE
from league.events import screen as SC
from league.events import store as S
from league.events import verdicts as V
from league.tests import evl5_world as W
from league.tests import test_events_book as TB
from league.tests import test_events_house as TH
from league.tests.test_events_house import Clock, FakeHouse, Mono

UTC = dt.timezone.utc
REPO = Path(__file__).resolve().parents[2]
FIVE = ("EVL-ERN-DROP-ON", "EVL-ERN-UNDER-ON", "EVL-NEWS-NIGHT2-ON")
CONTROL5 = "EVL-CTRL-ERN-UNDER-ON"
ALL5 = FIVE + (CONTROL5,)
NINE = ("EVL-ERN-READ-O1", "EVL-ERN-REACT-C1", "EVL-8K-READ-O1", "EVL-NEWS-READ-O1", "EVL-ERN-REACT-ON",
        "EVL-ERN-GUIDE-O1", "EVL-INS-BUY-O1", "EVL-NEWS-READ-ON", "EVL-NEWS-REACT-ON")
FOUR = ("EVL-8K-REACT-ON", "EVL-8K-READ-ON", "EVL-NEWSPM-READ-ON")
REGISTERED_5 = dt.datetime(2026, 10, 21, 21, 26, 21, tzinfo=UTC)
D, PRIOR, NEXT, FRI = W.D_DAY, W.P_DAY, W.N_DAY, W.F_DAY
et = W.et
CIK = W.CIK


def earlier(program: str, version: int) -> bool:
    """Every program but PREREG-EVL-5's (PREREG-EVL-1 to -4 and the births)."""
    return program not in ALL5


def without_evl5():
    """THE CODE WITHOUT PREREG-EVL-5's ROWS: the program table without them (the close decision's last part then
    decides nothing), as release 1019e decided."""
    return mock.patch.object(P, "PROGRAMS", tuple(p for p in P.PROGRAMS if p.prereg != 5))


class WorldCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.w = W.World(Path(self.tmp.name) / "lane")
        self.addCleanup(self.w.close)
        self.addCleanup(P.load_births, None)
        self.st = self.w.st

    def intents(self, program: str, day: dt.date | None = None) -> list[dict]:
        sql, args = "SELECT * FROM intents WHERE program=?", [program]
        if day is not None:
            sql += " AND entry_day=?"
            args.append(day.isoformat())
        return [dict(r) for r in self.st.db.execute(sql + " ORDER BY event", args)]

    def taken(self, program: str, day: dt.date | None = None) -> list[str]:
        return sorted(r["symbol"] for r in self.intents(program, day) if not str(r["status"]).startswith("skipped"))

    def verdict(self, event: str, score: int | None, answered: dt.datetime, *, news: bool = False,
                status: str = "ok", guidance: str = "none") -> None:
        prompt = V.PROMPTS["news" if news else "doc"]
        self.st.db.execute("INSERT INTO verdicts(event, prompt_sha, model, request_id, asked_at, answered_at, status, "
                           "score, guidance, answer, usd) VALUES(?, ?, ?, 'r', ?, ?, ?, ?, ?, '{}', 0.001)",
                           (event, prompt.sha, V.MODEL, S.iso(answered), S.iso(answered), status, score, guidance))

    def close(self, day: dt.date = D, *, pre: bool = True) -> dict:
        """The House's day for the close: the open decision (its verdicts asked ahead), the close's verdict pre-pass at
        12:30 ET (PREREG-EVL-5's heavy reads), then the live close decision at 15:47 ET."""
        self.w.at(et(day, 7, 31)).decide("open", day, ask_only=True)
        self.w.at(et(day, 9, 15, 30)).decide("open", day)
        if pre:
            self.w.at(et(day, 12, 30)).decide("close", day, ask_only=True)
        return self.w.at(et(day, 15, 47)).decide("close", day)

    def receipt(self, job: str) -> dict:
        row = self.st.db.execute("SELECT status, summary FROM receipts WHERE job=? ORDER BY id DESC LIMIT 1",
                                 (job,)).fetchone()
        return {"status": row["status"], **json.loads(row["summary"] or "{}")}


# ----------------------------------------------------------------------------------------------------------- the rows
class TheRows(unittest.TestCase):
    def test_the_four_rows_as_frozen(self):
        """Section 1.2's three seatable programs in its order, then section 4's control; each enters at the CLOSE of D
        and exits at the OPEN of the next session (hold 1); version 1 their seating version (section 2); after every
        PREREG-EVL-4 row (ROOM's order within a band), before any birth."""
        self.assertEqual(P.REGISTERED_AT_5, "2026-10-21T21:26:21Z")
        rows = [p for p in P.PROGRAMS if p.prereg == 5]
        self.assertEqual(tuple(p.id for p in rows), ALL5)
        self.assertEqual(P.PREREG_PROGRAMS[-4:], tuple(rows), "after every earlier file's rows")
        self.assertEqual({p.id: (p.version, p.seatable, p.family, p.entry_at, p.hold, p.reads, p.exit_at, p.rule)
                          for p in rows},
                         {"EVL-ERN-DROP-ON": (1, True, "ern-drop", "close", 1, False, "open", "none"),
                          "EVL-ERN-UNDER-ON": (1, True, "ern-under", "close", 1, True, "open", "min2"),
                          "EVL-NEWS-NIGHT2-ON": (1, True, "news-night2", "close", 1, False, "open", "none"),
                          "EVL-CTRL-ERN-UNDER-ON": (1, False, "ern-under", "close", 1, False, "open", "none")})
        self.assertEqual([p for p in P.PROGRAMS if p.id in ALL5 and p.version != 1], [], "no version 2 of a new id")
        for p in rows:
            self.assertEqual(p.can_seat, p.id in FIVE, p.id)
            self.assertEqual(p.registered_at, REGISTERED_5, p.id)
            self.assertIs(P.BY_ID[p.id], p)
        self.assertEqual([(p.id, p.version) for p in P.PREREG_SEATING],
                         [(i, 2) for i in NINE] + [(i, 1) for i in FOUR] + [(i, 1) for i in FIVE])
        self.assertEqual(P.SEATING_PREREGS, (3, 4, 5))
        self.assertEqual(P.CLOSE_FAMILIES_5, ("ern-drop", "ern-under", "news-night2"))
        self.assertFalse(set(P.CLOSE_FAMILIES_5) & set(P.REACT_FAMILIES), "the >= 1.04 rule never applies to them")

    def test_each_file_counts_from_its_own_registration_time(self):
        five = P.BY_ID["EVL-ERN-DROP-ON"]
        with mock.patch.object(P, "REGISTERED_AT_4", "2026-12-01T00:00:00Z"), \
                mock.patch.object(P, "REGISTERED_AT_3", "2026-12-01T00:00:00Z"):
            self.assertEqual(five.registered_at, REGISTERED_5, "PREREG-EVL-5 never reads PREREG-EVL-4's or -3's time")
        with mock.patch.object(P, "REGISTERED_AT_5", None), self.assertRaises(RuntimeError):
            five.registered_at
        with self.assertRaises(ValueError):
            dataclasses.replace(five, prereg=6).registered_at
        self.assertEqual(P.BY_ID["EVL-8K-READ-ON"].registered_at, S.parse_iso(P.REGISTERED_AT_4))

    def test_the_constants_are_the_frozen_texts(self):
        """Every number the rules read, from the frozen file's own words."""
        text = (REPO / "docs" / "prereg" / "PREREG-EVL-5.md").read_text()
        self.assertIn("the reaction <= 0.96 (no model)", text)
        self.assertIn("a reaction above 0.96 and below 1.04", text)
        self.assertIn("the gap >= 1.02 (no model)", text)
        self.assertIn('the score, plus 0.5 when that verdict\'s guidance is "raised"', text)
        self.assertIn("`ok` with score >= 2, or `ok` with score >= 1 and guidance \"raised\"", text)
        self.assertIn("its `updated_at` is at most 10 minutes after its `created_at`", text)
        self.assertIn("T29 of a session is PREREG-EVL-2 section\n  2's (15:29:00 ET", text)
        self.assertEqual((P.DROP_RATIO, P.REACT_RATIO, P.GAP_RATIO, P.GUIDE_BONUS), (0.96, 1.04, 1.02, 0.5))
        self.assertEqual((P.READ_MIN_SCORE, P.GUIDE_MIN_SCORE, P.NEWS_UPDATE_LIMIT), (2, 1, dt.timedelta(minutes=10)))
        self.assertEqual(P.T29_BEFORE_CLOSE, dt.timedelta(minutes=31))

    def test_the_entry_at_the_close_the_exit_at_the_next_open_and_the_limit_at_entry(self):
        """ENTRY, EXIT AND HOLD: the CLOSE auction of D, out at the OPEN auction of the next session, one session in
        the screen's sense; THE LIMIT AT ENTRY, shadow and real alike: an entry auction above 1.25 x the raw SIP close
        of P is not filled (score.py, prereg >= 2), and the book's limit is 1.25 x it."""
        for pid in ALL5:
            p = P.BY_ID[pid]
            self.assertEqual(EB.exit_plan(p, D), (NEXT.isoformat(), "open"))
            intent = {"program": pid, "version": 1}
            self.assertTrue(SCORE._above_limit(intent, {"prev_close": 10.0}, 12.51), pid)
            self.assertFalse(SCORE._above_limit(intent, {"prev_close": 10.0}, 12.50), pid)
            self.assertEqual(SC.HOLDS[pid], 1)
        self.assertEqual(EB.limit_price(Decimal("10.00"), EB.settings().limit_ratio), Decimal("12.50"))


# ----------------------------------------------------------------------------------------------------------- the judge
class TheJudge(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(P.load_births, None)
        self.w = W.World(Path(self.tmp.name) / "lane")
        self.addCleanup(self.w.close)
        self.st = self.w.st

    def test_the_registries_and_the_expected_false_passes(self):
        """Section 3: 0.10 x every version that can seat: 0.9 + 0.3 + 0.3 = 1.5 of the lane's stated 3.0 with no birth
        registered before it (SEATING sums them); each seatable birth adds 0.10; the control costs nothing."""
        self.assertEqual(SC.SEATABLE[-3:], FIVE)
        self.assertEqual(SC.RECORDS[-1], CONTROL5)
        self.assertEqual(SC.CONTROLS["EVL-ERN-UNDER-ON"], CONTROL5)
        self.assertNotIn("EVL-ERN-DROP-ON", SC.CONTROLS)
        self.assertNotIn("EVL-NEWS-NIGHT2-ON", SC.CONTROLS, "no control condition for the two rows that read no model")
        self.assertEqual([SC._seating(p, 1) for p in ALL5], [True, True, True, False])
        self.assertEqual(SC.expected_false_passes(self.st), {"versions": 15, "expected": 1.5, "budget": 3.0, "left": 1.5})
        self.w.births()
        self.assertEqual(SC.expected_false_passes(self.st)["expected"], 1.7, "two seatable births: 0.10 each")
        self.assertEqual(R._group("EVL-ERN-UNDER-ON"), frozenset({"EVL-ERN-UNDER-ON", CONTROL5}))
        self.assertEqual(R._group("EVL-NEWS-NIGHT2-ON"), frozenset({"EVL-NEWS-NIGHT2-ON"}))

    def _settle(self, program: str, per_day: int, days: list[dt.date], a: float, start: int = 0) -> int:
        n = start
        for d in days:
            nxt = C.nth(self.st, d, 2).day
            for _ in range(per_day):
                ev = f"syn:{program}:{n}"
                self.st.db.execute("INSERT INTO intents(program, version, event, symbol, cik, decided_at, entry_day, "
                                   "entry_at, exit_day, exit_at, rank_key, mode, status, why) VALUES(?, 1, ?, 'S', ?, "
                                   "'z', ?, 'close', ?, 'open', NULL, 'shadow', 'exited', NULL)",
                                   (program, ev, f"{n:010d}", d.isoformat(), nxt.isoformat()))
                self.st.db.execute("INSERT INTO outcomes(program, version, event, entry_px, exit_px, bench, bench_entry, "
                                   "bench_exit, cost_entry_bp, cost_exit_bp, r, b, a, tradable, settled_at, status) "
                                   "VALUES(?, 1, ?, 10, 10, 'SPY', 1, 1, 5, 5, ?, 0, ?, 1, 'z', 'settled')",
                                   (program, ev, a, a))
                n += 1
        return n

    def test_preregevl3s_screen_runs_them_at_version_1(self):
        """Section 2: PREREG-EVL-3's screen unchanged, at version 1 (seed strings `{id}|v1|look{k}`), EVL-ERN-UNDER-ON's
        mean block value against its control's over the same sessions."""
        days = [s.day for s in C.sessions(self.st, dt.date(2026, 10, 22), dt.date(2026, 11, 30))][:8]
        n = self._settle("EVL-ERN-UNDER-ON", 8, days, 0.01)
        self._settle(CONTROL5, 8, days, 0.02, start=n)
        today = C.nth(self.st, days[-1], 3).day
        now = et(today, 21, 0)
        with mock.patch.object(SC, "final_until", lambda *a, **k: (today, "final")):
            out = SC.run(self.st, today, programs=[("EVL-ERN-UNDER-ON", 1)], now=now, draws=999)
        [look] = out["written"]
        self.assertEqual((look["program"], look["version"], look["k"]), ("EVL-ERN-UNDER-ON", 1, 1))
        detail = SC.look_detail(self.st, "EVL-ERN-UNDER-ON", 1, 1)
        self.assertEqual(detail["control"]["program"], CONTROL5)
        self.assertIn("mean block", detail["why"], "its block value is below its control's: no pass")
        self.assertEqual(SC.seed_string("EVL-ERN-UNDER-ON", 1, 1), "EVL-ERN-UNDER-ON|v1|look1")
        self.assertEqual(detail["alpha"] <= SC.V2_ALPHA, True)

    def test_a_close_made_without_their_rows_or_with_their_part_failed_is_not_made_for_them(self):
        """Section 3 (THE RECORD BEFORE THE RELEASE) and 1.3: a close decided by a release without these rows, or whose
        part for them failed, is not made for them until `decide-close-evl5` names them; PREREG-EVL-4's rows read
        `decide-close-evl4` alone, as before; a close decided before the registration time is made for them."""
        def receipt(job: str, summary: dict, at: dt.datetime) -> None:
            rid = self.st.start_receipt(job, now=at)
            self.st.finish_receipt(rid, "ok", summary, now=at)
        thu = dt.date(2026, 10, 22)
        for day in (dt.date(2026, 10, 21), thu):
            receipt(f"decide-open:{day}", {}, et(day, 9, 15))
            receipt(f"decide-close:{day}", {k: {"planned": 0} for k in FOUR + ("EVL-CTRL-8K-ON", "EVL-CTRL-NEWSPM-ON")},
                    et(day, 15, 47))
        self.assertEqual(SC.made_without(self.st, thu, prereg=5), {thu: False}, "Oct 21's close predates the registration")
        self.assertEqual(SC.made_without(self.st, thu), {}, "PREREG-EVL-4's are named: its reading unchanged")
        now = et(dt.date(2026, 10, 27), 17, 0)
        got = SC.final_until(self.st, "EVL-ERN-DROP-ON", 1, dt.date(2026, 10, 27), now)
        self.assertIn("the close decision of 2026-10-22 is made without its rows", got[1])
        receipt(f"decide-{SC.FOUR_KIND}:{thu}", {key: {"planned": 0} for key in ALL5}, et(dt.date(2026, 10, 23), 1, 0))
        self.assertEqual(SC.made_without(self.st, thu, prereg=5), {thu: False}, "named by its own file's kind alone")
        receipt(f"decide-{SC.FIVE_KIND}:{thu}", {key: {"planned": 0} for key in ALL5}, et(dt.date(2026, 10, 23), 1, 1))
        self.assertEqual(SC.made_without(self.st, thu, prereg=5), {})
        got = SC.final_until(self.st, "EVL-ERN-DROP-ON", 1, dt.date(2026, 10, 27), now)
        self.assertNotIn("made without its rows", got[1], "its rows' own decision is its decision")
        receipt(f"decide-close:{thu}", {"evl5_error": "PartDeadline: past its own time bound"}, et(thu, 17, 0))
        self.assertEqual(SC.made_without(self.st, thu, prereg=5), {thu: True}, "decided again without them: stale")

    def test_the_final_records_span_starts_at_the_close_decision_of_p_prime(self):
        """Section 2: FOR THIS FILE'S ROWS A69's span begins at the close decision time of P' (two sessions before X),
        A74 (3)'s daily-index backfill must have run for every weekday from P' through X, and the passes are judged by
        `_fast_passes` from that start, A84's per-feed rule when merged and A69's otherwise; PREREG-EVL-4's span still
        begins at 09:00 ET of the session before X."""
        x = C.session(self.st, D)
        after = C.nth(self.st, D, 2)
        rid = self.st.start_receipt(f"decide-open:{after.day}", now=after.open_decide)
        self.st.finish_receipt(rid, "ok", {}, now=after.open_decide)
        seen: list[tuple[str, dt.datetime]] = []

        def passes(store, start, end, cache):
            seen.append(("passes", start))
            return None

        def filings(store, x_, start, end, now, cache):
            seen.append(("filings", start))
            return None
        now = et(NEXT, 12, 0)
        for day in W4_weekdays(FRI, D):
            self.st.set_meta(f"evl:backfill:{day.isoformat()}", "done")
        with mock.patch.object(SC, "_fast_passes", passes), mock.patch.object(SC, "_fast_filings", filings):
            self.assertIsNone(SC._fast_block(self.st, P.BY_ID["EVL-NEWS-NIGHT2-ON"], REGISTERED_5.date(), x, None, now,
                                             {}))
            self.assertEqual(seen, [("filings", C.session(self.st, FRI).close_decide),
                                    ("passes", C.session(self.st, FRI).close_decide)])
            seen.clear()
            self.assertIsNone(SC._fast_block(self.st, P.BY_ID["EVL-8K-READ-ON"], dt.date(2026, 10, 19), x, None, now, {}))
            self.assertEqual(seen, [("filings", C.session(self.st, PRIOR).open_cutoff),
                                    ("passes", C.session(self.st, PRIOR).open_cutoff)], "PREREG-EVL-4's span unchanged")
            self.st.set_meta(f"evl:backfill:{FRI.isoformat()}", "partial")
            self.assertEqual(SC._fast_block(self.st, P.BY_ID["EVL-ERN-DROP-ON"], REGISTERED_5.date(), x, None, now, {}),
                             "the daily-index backfill of 2026-10-23 has not run")
            self.assertIsNone(SC._fast_block(self.st, P.BY_ID["EVL-8K-READ-ON"], dt.date(2026, 10, 19), x, None, now, {}),
                              "PREREG-EVL-4's rows read the backfill from P alone")

    def test_an_8k_feed_gap_after_p_primes_close_decision_holds_their_looks_alone(self):
        """The record passes: no clean 8-K read from Friday 17:00 to 17:30 ET (inside this file's span, before Monday's
        09:00 ET: a gap of more than 15 minutes in that feed's clean reads, whether A69 (i) is read pass by pass or, A84,
        feed by feed) breaks EVL-NEWS-NIGHT2-ON's fast path for Tuesday's close; PREREG-EVL-4's span starts after it."""
        x = C.session(self.st, D)
        after = C.nth(self.st, D, 2)
        rid = self.st.start_receipt(f"decide-open:{after.day}", now=after.open_decide)
        self.st.finish_receipt(rid, "ok", {}, now=after.open_decide)
        for day in W4_weekdays(FRI, D):
            self.st.set_meta(f"evl:backfill:{day.isoformat()}", "done")
        whole = {"8-K": {"new": 0}, "4": {"new": 0}, "news": {"stored": 0}}
        t = C.session(self.st, FRI).close_decide - dt.timedelta(minutes=10)
        while t <= after.open_decide + dt.timedelta(minutes=5):
            body = {"8-K": {"error": "timeout"}, "4": {"new": 0}, "news": {"stored": 0}} \
                if et(FRI, 17, 0) <= t < et(FRI, 17, 30) else whole
            rid = self.st.start_receipt("record", now=t)
            self.st.finish_receipt(rid, "ok", body, now=t)
            t += dt.timedelta(minutes=5)
        now = et(NEXT, 12, 0)
        got = SC._fast_block(self.st, P.BY_ID["EVL-NEWS-NIGHT2-ON"], REGISTERED_5.date(), x, None, now, {})
        self.assertIsNotNone(got)
        self.assertIn("8-K", got)
        self.assertIsNone(SC._fast_block(self.st, P.BY_ID["EVL-8K-READ-ON"], dt.date(2026, 10, 19), x, None, now, {}))


def W4_weekdays(first: dt.date, last: dt.date) -> list[dt.date]:
    return list(W.W4.weekdays(first, last))


# ---------------------------------------------------------------------------------------------- the earnings rows
class TheEarningsRows(WorldCase):
    def ern(self, accession: str, ticker: str, accepted: dt.datetime, *, items=("2.02",), text_len: int = 5000,
            stored: dt.datetime | None = None, form: str = "8-K") -> str:
        self.w.filing(accession, ticker, accepted=accepted, items=items, text_len=text_len, stored=stored, form=form)
        return f"8k:{accession}"

    def test_ern_d_is_the_close_window_of_d_and_8ka_is_not_in_it(self):
        """ERN(D): item 2.02 8-Ks (form exactly 8-K) knowable at or after P's close decision time and before D's."""
        g = self.w.gw
        g.minute.update({"KKK": 19.0, "NNN": 19.0, "OOO": 19.0, "MMM": 19.0})
        p, d = C.session(self.st, PRIOR), C.session(self.st, D)
        self.ern("0000000011-26-000101", "KKK", p.close_decide - dt.timedelta(minutes=10))     # knowable at P's 15:46
        self.ern("0000000014-26-000101", "NNN", d.close_decide - dt.timedelta(minutes=10))     # knowable at D's 15:46
        self.ern("0000000015-26-000101", "OOO", et(D, 10, 0), form="8-K/A")
        self.ern("0000000013-26-000101", "MMM", et(D, 10, 0), items=("7.01",))
        self.close()
        self.assertEqual(self.taken("EVL-ERN-DROP-ON", D), ["KKK"])
        self.assertEqual(self.taken("EVL-ERN-DROP-ON", NEXT), [], "NNN's day 0 is Wednesday")

    def test_drop_takes_a_fall_to_096_ranked_by_it_and_a_missing_price_takes_nothing(self):
        g = self.w.gw
        g.minute.update({"KKK": 19.2, "LLL": 19.2002, "MMM": 18.0})      # 0.96, 0.96001, 0.90; NNN has no T29 bar
        g.minute.pop("NNN")
        for t, acc in (("KKK", "0000000011-26-000102"), ("LLL", "0000000012-26-000102"), ("MMM", "0000000013-26-000102"),
                       ("NNN", "0000000014-26-000102")):
            self.ern(acc, t, et(PRIOR, 17, 0))
        g.doc.update({"LLL": 2, "KKK": 0, "MMM": 0, "NNN": 0})
        self.close()
        rows = {r["symbol"]: r for r in self.intents("EVL-ERN-DROP-ON", D)}
        self.assertEqual(sorted(rows), ["KKK", "MMM"], "exactly 0.96 falls; above it does not; no price, no event")
        self.assertAlmostEqual(rows["KKK"]["rank_key"], 0.04)
        self.assertAlmostEqual(rows["MMM"]["rank_key"], 0.10)
        self.assertEqual((rows["KKK"]["entry_at"], rows["KKK"]["exit_at"], rows["KKK"]["exit_day"]),
                         ("close", "open", NEXT.isoformat()))
        self.assertEqual(self.taken("EVL-ERN-UNDER-ON", D), ["LLL"], "0.96001 is above 0.96: the muted band")

    def test_under_takes_a_muted_reaction_with_score_2_ranked_with_the_raised_bonus(self):
        g = self.w.gw
        g.minute.update({"KKK": 20.0, "LLL": 20.0, "MMM": 20.8, "NNN": 20.0, "OOO": 20.0})
        g.doc.update({"KKK": 1, "LLL": 3, "MMM": 3, "NNN": 3, "OOO": 2})
        g.guide.update({"LLL": "raised", "NNN": "maintained", "OOO": "raised"})
        self.ern("0000000011-26-000103", "KKK", et(PRIOR, 17, 0))                       # score 1: not taken
        self.ern("0000000012-26-000103", "LLL", et(PRIOR, 17, 0))                       # 3 raised: 3.5
        self.ern("0000000013-26-000103", "MMM", et(PRIOR, 17, 0))                       # 1.04 exactly: neither row
        self.ern("0000000014-26-000103", "NNN", et(PRIOR, 17, 0), text_len=150)         # no verdict: not taken
        self.ern("0000000015-26-000103", "OOO", et(PRIOR, 17, 0))                       # 2 raised: 2.5
        self.ern("0000000015-26-000104", "OOO", et(PRIOR, 18, 0))                       # the same issuer, score 2 again
        self.close()
        got = {r["symbol"]: (r["event"], r["rank_key"]) for r in self.intents("EVL-ERN-UNDER-ON", D)}
        self.assertEqual(got, {"LLL": ("8k:0000000012-26-000103", 3.5), "OOO": ("8k:0000000015-26-000103", 2.5)},
                         "one an issuer: the highest score, then the earliest; the score plus 0.5 when raised")
        self.assertEqual(self.taken("EVL-ERN-DROP-ON", D), [])
        self.assertNotIn("8k:0000000014-26-000103", {q[0] for q in self.w.gw.asked()}, "a TEXT under 200 is never asked")
        self.assertNotIn("MMM", self.taken(CONTROL5, D), "1.04 is the REACT rows' (TAKEN (a))")

    def test_the_control_takes_every_muted_filing_and_ranks_the_scored_first(self):
        g = self.w.gw
        g.minute.update({"KKK": 20.0, "LLL": 20.0, "MMM": 19.6})
        g.doc.update({"KKK": 1, "LLL": 3, "MMM": 0})
        self.ern("0000000011-26-000104", "KKK", et(PRIOR, 17, 0))
        self.ern("0000000012-26-000104", "LLL", et(PRIOR, 17, 0))
        self.ern("0000000013-26-000104", "MMM", et(PRIOR, 17, 0), text_len=150)
        self.ern("0000000013-26-000105", "MMM", et(PRIOR, 18, 0))                       # an `ok` score of 0
        out = self.close()
        self.assertNotIn(CONTROL5, out["pending"], "never waits for a TEXT that gets no verdict")
        got = {r["symbol"]: (r["event"], r["rank_key"]) for r in self.intents(CONTROL5, D)}
        self.assertEqual(got, {"KKK": ("8k:0000000011-26-000104", 1.0), "LLL": ("8k:0000000012-26-000104", 3.0),
                               "MMM": ("8k:0000000013-26-000105", 0.0)},
                         "with or without a verdict; a filing with a stored score ranks before one without")
        self.assertEqual(self.taken("EVL-ERN-UNDER-ON", D), ["LLL"])

    def test_taken_by_an_earlier_row_a_b_c_and_the_wait(self):
        """TAKEN AT D'S CLOSE BY AN EARLIER ROW: (a) an ERN(D) reaction >= 1.04, (b) a DAY(D) article scored `ok` >= 2,
        (c) a day-news reaction >= 1.04; an answer unparsed, refused or under 2 is no (b); an unanswered DAY(D) article
        makes the issuer's events WAIT in the shadow."""
        g = self.w.gw
        g.minute.update({"KKK": 19.0, "LLL": 19.0, "MMM": 21.0, "NNN": 19.0, "OOO": 19.0, "PPP": 19.0, "QQQ": 19.0})
        g.closes[("MMM", FRI)] = 22.0             # MMM's release before Monday's close: 21/22, a fall; the day: 21/20
        g.news.update({"KKK": 2, "LLL": 1, "NNN": 3, "OOO": 0})
        self.ern("0000000011-26-000106", "KKK", et(PRIOR, 17, 0))
        self.w.article("n-kkk", "KKK", knowable=et(D, 10, 0))                             # (b): score 2
        self.ern("0000000012-26-000106", "LLL", et(PRIOR, 17, 0))
        self.w.article("n-lll", "LLL", knowable=et(D, 10, 0))                             # score 1: not (b)
        self.ern("0000000013-26-000106", "MMM", et(PRIOR, 15, 50))
        self.w.article("n-mmm", "MMM", knowable=et(D, 10, 0))                             # (c): the day's 1.05
        self.ern("0000000014-26-000106", "NNN", et(PRIOR, 17, 0))
        self.ern("0000000014-26-000107", "NNN", et(PRIOR, 18, 0))
        g.minute["NNN"] = 19.0
        self.ern("0000000015-26-000106", "OOO", et(PRIOR, 17, 0))
        self.w.article("n-ooo", "OOO", knowable=et(D, 10, 0))                             # score 0 then refused below
        self.ern("0000000016-26-000106", "PPP", et(PRIOR, 17, 0))
        self.w.article("n-ppp", "PPP", knowable=et(D, 10, 0))                             # no answer: waits
        g.refuse.add("PPP")
        self.ern("0000000017-26-000106", "QQQ", et(PRIOR, 17, 0))
        self.ern("0000000017-26-000107", "QQQ", et(PRIOR, 18, 0))
        g.minute["QQQ"] = 21.0                                                            # (a): its 1.05
        out = self.close()
        self.assertEqual(out["pending"].get("EVL-ERN-DROP-ON"), 1, "PPP waits for its DAY(D) answer")
        self.assertEqual(self.intents("EVL-ERN-DROP-ON", D), [], "a program waiting decides nothing")
        g.refuse.clear()
        out = self.w.at(et(D, 15, 52)).decide("close", D)
        self.assertNotIn("EVL-ERN-DROP-ON", out["pending"])
        self.assertEqual(self.taken("EVL-ERN-DROP-ON", D), ["LLL", "NNN", "OOO", "PPP"],
                         "KKK by (b), MMM by (c), QQQ by (a); LLL's 1 and OOO's 0 take nothing")
        self.st.db.execute("DELETE FROM intents WHERE program='EVL-ERN-DROP-ON'")
        self.st.db.execute("UPDATE verdicts SET status='unparsed', score=NULL WHERE event='news:n-ooo'")
        self.st.db.execute("UPDATE verdicts SET status='refused', score=NULL WHERE event='news:n-lll'")
        self.w.at(et(D, 16, 0)).decide("close", D, live=False)
        self.assertEqual(self.taken("EVL-ERN-DROP-ON", D), ["LLL", "NNN", "OOO", "PPP"], "unparsed or refused: no (b)")

    def test_the_sets_that_skip_carry_no_registration_floor(self):
        """Thu Oct 22, the first close after the registration: an ERN(D) filing knowable before 21:26:21Z Oct 21 is no
        event of these rows, but its reaction of 1.05 makes its issuer TAKEN (a), and the issuer's later release is
        skipped; a later release alone is an event."""
        thu, wed = dt.date(2026, 10, 22), dt.date(2026, 10, 21)
        g = self.w.gw
        g.minute.update({"KKK": 19.0, "LLL": 19.0})
        self.ern("0000000011-26-000108", "KKK", et(wed, 16, 50))                # knowable 17:00 ET = 21:00Z: before it
        self.ern("0000000011-26-000109", "KKK", et(thu, 8, 0))
        self.ern("0000000012-26-000108", "LLL", et(wed, 16, 50))
        g.minute["KKK"] = 21.0
        self.close(thu)
        self.assertEqual(self.taken("EVL-ERN-DROP-ON", thu), [], "KKK TAKEN (a) by its pre-registration release; LLL's "
                                                                  "only release predates the registration")
        g.minute["KKK"] = 19.0
        self.st.db.execute("DELETE FROM marks")
        self.st.db.execute("DELETE FROM intents")
        self.w.at(et(thu, 16, 0)).decide("close", thu, live=False)
        self.assertEqual(self.taken("EVL-ERN-DROP-ON", thu), ["KKK"], "its Thursday release, the event")
        self.assertEqual(self.intents("EVL-ERN-DROP-ON", thu)[0]["event"], "8k:0000000011-26-000109")

    def test_under_and_its_control_skip_an_issuer_with_a_fall(self):
        g = self.w.gw
        g.doc.update({"KKK": 3})
        g.closes[("KKK", FRI)] = 20.6
        self.ern("0000000011-26-000110", "KKK", et(PRIOR, 15, 50))             # 19.6 / 20.6: 0.951, a fall
        self.ern("0000000011-26-000111", "KKK", et(PRIOR, 17, 0))              # 19.6 / 20: 0.98, muted, scored 3
        g.minute["KKK"] = 19.6
        self.close()
        self.assertEqual(self.taken("EVL-ERN-UNDER-ON", D), [])
        self.assertEqual(self.taken(CONTROL5, D), [])
        self.assertEqual([r["event"] for r in self.intents("EVL-ERN-DROP-ON", D) if r["status"] == "planned"],
                         ["8k:0000000011-26-000110"], "the earliest knowable filing the rule takes")



# ---------------------------------------------------------------------------------------------- the second night
class TheSecondNight(WorldCase):
    def setUp(self):
        super().setUp()
        self.w.gw.opens = {}
        self.w.gw.default_open = 21.0              # a gap of 1.05 unless a test says otherwise

    def test_the_attention_window_of_p(self):
        """THE ATTENTION ARTICLES OF P: single-symbol articles, that symbol the issuer's eligible ticker for D, knowable
        after the close of P' and at or before T29 of P (PREREG-EVL-1 section 3's non-live exclusion applied)."""
        f, p = C.session(self.st, FRI), C.session(self.st, PRIOR)
        w = self.w
        w.article("n-kkk", "KKK", knowable=f.close_at)                                   # at P''s close: not after it
        w.article("n-lll", "LLL", knowable=f.close_at + dt.timedelta(seconds=1))
        w.article("n-mmm", "MMM", knowable=p.close_at - P.T29_BEFORE_CLOSE)              # at T29 of P: in
        w.article("n-nnn", "NNN", knowable=p.close_at - P.T29_BEFORE_CLOSE + dt.timedelta(seconds=1))   # after T29
        w.article("n-ooo", "OOO", knowable=et(PRIOR, 10, 0), symbols=["OOO", "PPP"])     # two symbols: none's
        w.article("n-qqq", "QQQ", knowable=et(PRIOR, 10, 0), live=False, edited=dt.timedelta(minutes=11))   # excluded
        self.close()
        self.assertEqual(self.taken("EVL-NEWS-NIGHT2-ON", D), ["LLL", "MMM"])
        self.assertEqual([r["event"] for r in self.intents("EVL-NEWS-NIGHT2-ON", D)], ["news:n-lll", "news:n-mmm"])
        self.assertEqual(self.taken("EVL-NEWS-NIGHT2-ON", NEXT), [], "after T29 of Monday and before its close: in no "
                                                                      "session's attention window")

    def test_no_new_information_i_any_source_any_symbols_and_the_non_live_exclusion(self):
        """(i): no article of any source, with any number of symbols, naming a ticker SEC's copy maps to the issuer,
        knowable after T29 of P and at or before D's close decision; a live article counts whatever its `updated_at`,
        a backfilled one only when edited at most 10 minutes after its creation."""
        p, d = C.session(self.st, PRIOR), C.session(self.st, D)
        w = self.w
        for t in ("KKK", "LLL", "MMM", "NNN", "OOO", "PPP", "QQQ"):
            w.article(f"n-{t.lower()}", t, knowable=et(PRIOR, 10, 0))
        w.article("x-kkk", "KKK", knowable=et(D, 9, 0), symbols=["AAA", "KKK", "BBB"])     # many symbols: named
        w.article("x-lll", "LLL", knowable=et(D, 9, 0), live=False, edited=dt.timedelta(minutes=10))   # counts
        w.article("x-mmm", "MMM", knowable=et(D, 9, 0), live=False, edited=dt.timedelta(minutes=11))   # excluded
        w.article("x-nnn", "NNN", knowable=et(D, 9, 0), live=True, edited=dt.timedelta(hours=3))       # live: counts
        w.article("x-ooo", "OOO", knowable=p.close_at - P.T29_BEFORE_CLOSE + dt.timedelta(seconds=1),
                  symbols=["OOO", "AAA"])                                                 # just after T29 of P: named
        w.article("x-ppp", "PPP", knowable=d.close_decide + dt.timedelta(seconds=1), symbols=["PPP", "AAA"])  # after
        w.article("x-qqq", "QQQ", knowable=d.close_decide, symbols=["QQQ", "AAA"])        # at D's close decision: named
        self.close()
        self.assertEqual(self.taken("EVL-NEWS-NIGHT2-ON", D), ["MMM", "PPP"])

    def test_no_new_information_ii_any_8k_from_p_primes_close_decision(self):
        """(ii): no 8-K of the issuer (form exactly 8-K, any items) knowable at or after P''s close decision and before
        D's (the close windows of P and of D)."""
        f, d = C.session(self.st, FRI), C.session(self.st, D)
        w = self.w
        for t in ("KKK", "LLL", "MMM", "NNN", "OOO"):
            w.article(f"n-{t.lower()}", t, knowable=et(PRIOR, 10, 0))
        w.filing("0000000011-26-000201", "KKK", knowable=f.close_decide, items=("5.07",))              # at it: in
        w.filing("0000000012-26-000201", "LLL", knowable=f.close_decide - dt.timedelta(seconds=1), items=("5.07",))
        w.filing("0000000013-26-000201", "MMM", knowable=d.close_decide - dt.timedelta(seconds=1), items=("9.01",))
        w.filing("0000000014-26-000201", "NNN", knowable=d.close_decide, items=("8.01",))             # at D's: out
        w.filing("0000000015-26-000201", "OOO", knowable=et(PRIOR, 12, 0), items=("2.02",), form="8-K/A")  # not 8-K
        self.close()
        self.assertEqual(self.taken("EVL-NEWS-NIGHT2-ON", D), ["LLL", "NNN", "OOO"])

    def test_no_new_information_iii_an_insider_buy_from_0900_of_p(self):
        """(iii): no Form 4 of the issuer with PREREG-EVL-2's INSIDER BUY knowable at or after 09:00 ET of P and before
        D's close decision; a buy under $50,000 is none."""
        w = self.w
        for t in ("KKK", "LLL", "MMM"):
            w.article(f"n-{t.lower()}", t, knowable=et(PRIOR, 10, 0))
        w.insider_buy("0000000011-26-000301", "KKK", accepted=et(PRIOR, 8, 50), usd=60_000.0)   # knowable 09:00: in
        w.insider_buy("0000000012-26-000301", "LLL", accepted=et(PRIOR, 8, 49), usd=60_000.0)   # 08:59: out
        w.insider_buy("0000000013-26-000301", "MMM", accepted=et(D, 11, 0), usd=40_000.0)       # under $50,000
        self.close()
        self.assertEqual(self.taken("EVL-NEWS-NIGHT2-ON", D), ["LLL", "MMM"])

    def test_the_gap_its_minute_its_boundary_and_one_event_an_issuer(self):
        """THE GAP: the open of D's 09:30:00 minute bar over P's close (the universe row's previous close); >= 1.02
        taken, ranked by it; no trade in that minute, no gap; the issuer's one event its earliest attention article
        knowable after the registration time."""
        g, w = self.w.gw, self.w
        g.opens = {"KKK": 20.4, "LLL": 20.39, "MMM": 21.0, "NNN": 20.6}
        g.no_open = {"OOO"}
        for t, hh in (("KKK", 10), ("LLL", 11), ("MMM", 12), ("OOO", 13)):
            w.article(f"n-{t.lower()}", t, knowable=et(PRIOR, hh, 0))
        w.article("n-nnn-2", "NNN", knowable=et(PRIOR, 14, 0))
        w.article("n-nnn-1", "NNN", knowable=et(dt.date(2026, 10, 24), 9, 0))
        self.close()
        got = {r["symbol"]: (r["event"], round(r["rank_key"], 4)) for r in self.intents("EVL-NEWS-NIGHT2-ON", D)}
        self.assertEqual(got, {"KKK": ("news:n-kkk", 1.02), "MMM": ("news:n-mmm", 1.05),
                               "NNN": ("news:n-nnn-1", 1.03)}, "1.0195 is under 1.02; OOO had no 09:30 trade")
        marks = {r[0]: r[1] for r in self.st.db.execute("SELECT symbol, px FROM marks WHERE label='0930'")}
        self.assertEqual(marks["OOO"], None, "a minute with no trade is stored as such")
        self.assertEqual(marks["KKK"], 20.4)

    def test_only_an_eligible_issuers_events_and_its_eligible_ticker(self):
        """An issuer is ELIGIBLE when PREREG-EVL-1 section 2 makes its stock eligible for D; an article's one symbol
        must be that eligible ticker. An issuer Alpaca lists as inactive is no event of any of the three."""
        g, w = self.w.gw, self.w
        g.inactive = {"LLL", "MMM"}
        g.minute.update({"LLL": 19.0, "KKK": 19.0})
        w.article("n-kkk", "KKK", knowable=et(PRIOR, 10, 0))
        w.article("n-lll", "LLL", knowable=et(PRIOR, 10, 0))
        w.filing("0000000012-26-000901", "LLL", accepted=et(PRIOR, 17, 30), items=("2.02",))
        w.filing("0000000011-26-000901", "KKK", accepted=et(PRIOR, 17, 0), items=("2.02",))
        self.close()
        self.assertEqual(self.taken("EVL-ERN-DROP-ON", D), ["KKK"])
        self.assertEqual(self.taken("EVL-NEWS-NIGHT2-ON", D), [], "KKK's own release is (ii): an 8-K in D's window")
        self.assertIsNone(R.eligibility(w.ctx, D, [CIK["LLL"]], live=True, kind="close")[CIK["LLL"]])

    def test_no_new_information_i_reads_every_ticker_secs_copy_maps_to_the_issuer(self):
        """(i) reads a ticker that SEC's company_tickers.json (the copy D's decision reads) maps to the issuer's CIK:
        every ticker of a CIK with two, upper case, from an article with any number of symbols."""
        tickers = {"0000000001": [("AAA", "A Inc."), ("AAA.B", "A Inc.")], "0000000002": [("BBB", "B Inc.")]}
        ciks_of = P.ciks_by_ticker(tickers)
        self.assertEqual(ciks_of["AAA.B"], {"0000000001"})
        named = P.named_ciks([{"named": ["aaa.b", "ZZZ"]}, {"named": []}], ciks_of)
        self.assertEqual(named, {"0000000001"})
        self.assertEqual(P.news_named(self.st, et(D, 9, 0), et(D, 10, 0)), [])

    def test_the_three_share_no_issuer_day_and_none_shares_an_auction_pair_with_the_twelve(self):
        """Section 1.2: the three programs share no (issuer, D) with one another and no (issuer, entry auction, exit
        auction) with any seatable program of PREREG-EVL-1 to -4, on the invented week of every family."""
        W.evl4_rows(self.w)
        W.evl5_rows(self.w)
        W.decide_week(self.w)
        mine: dict[tuple[str, str], set[str]] = {}
        pairs: dict[tuple[str, str, str, str], set[str]] = {}
        for r in self.st.db.execute("SELECT program, version, cik, entry_day, entry_at, exit_day, exit_at FROM intents "
                                    "WHERE status NOT LIKE 'skipped%'"):
            prog = P.BY_KEY.get((r["program"], r["version"]))
            if prog is None or not (prog.can_seat or prog.id in FIVE):
                continue
            pairs.setdefault((r["cik"], f"{r['entry_day']}:{r['entry_at']}", f"{r['exit_day']}:{r['exit_at']}", ""),
                             set()).add(prog.id)
            if prog.id in FIVE:
                mine.setdefault((r["cik"], r["entry_day"]), set()).add(prog.id)
        self.assertTrue(mine)
        self.assertEqual({k: v for k, v in mine.items() if len(v) > 1}, {})
        clash = {k: v for k, v in pairs.items() if v & set(FIVE) and v - set(FIVE)}
        self.assertEqual(clash, {})


# ----------------------------------------------------------------------------------------------------- the verdicts
class TheVerdicts(WorldCase):
    def test_no_new_prompt_and_no_second_verdict(self):
        """Section 1.2: a PROMPT-DOC verdict of an eligible ERN(D) filing, or a PROMPT-NEWS verdict of a DAY(D) article,
        that these rows read and no row has stored by their decision is asked by it, with the same event id, prompt and
        rendering as the earlier row's; stored once, never asked again."""
        g, w = self.w.gw, self.w
        g.minute.update({"KKK": 20.0, "LLL": 19.0})
        g.doc.update({"KKK": 3, "LLL": 1})
        g.news.update({"LLL": 1})
        w.filing("0000000011-26-000401", "KKK", accepted=et(D, 10, 0), items=("2.02",))     # (no open row asks it)
        w.filing("0000000012-26-000401", "LLL", accepted=et(D, 10, 0), items=("2.02",))
        w.article("n-lll", "LLL", knowable=et(D, 10, 0))
        w.at(et(D, 9, 15, 30)).decide("open", D)              # (the universe rows of D)
        g.claude_calls.clear()
        out = R.decide_close(w.at(et(D, 15, 47)).ctx, D, backfill_run=True, evl5_only=True)
        self.assertEqual(sorted(g.asked()), ["doc:KKK", "news:LLL"], "KKK is muted (UNDER reads it); LLL fell (DROP "
                                                                     "reads its day news)")
        self.assertEqual({r["event"] for r in self.st.db.execute("SELECT event FROM verdicts")},
                         {"8k:0000000011-26-000401", "news:n-lll"})
        self.assertEqual(out["verdicts"], {"needed": 2, "answered": 2})
        self.assertEqual(self.taken("EVL-ERN-UNDER-ON", D), ["KKK"])
        self.assertEqual(self.taken("EVL-ERN-DROP-ON", D), ["LLL"])
        g.claude_calls.clear()
        R.decide_close(w.ctx, D, backfill_run=True)
        self.assertNotIn("doc:KKK", g.asked())
        self.assertNotIn("news:LLL", g.asked(), "the first stored answer is final: never asked again")
        self.assertEqual(self.receipt(f"decide-{SC.FIVE_KIND}:{D}")["status"], "ok")

    def test_the_prompts_are_unchanged(self):
        self.assertEqual(V.PROMPTS["doc"].sha, "b735c36ee7127d04afd1f6277b1441639680ad04b4c688118b465323dd5ad3f3")
        self.assertEqual(V.PROMPTS["news"].sha, "4b5245a95835a32f37eaf79ebbd54cc9aa72e1c4608e3ad96e00d302463bcacf")


# ----------------------------------------------------------------------------------------------------- the pre-pass
class ThePrePass(WorldCase):
    def test_the_pre_pass_reads_from_0947_and_stores_its_reads(self):
        """Section 1.3: EVL-NEWS-NIGHT2-ON's heavy reads (its attention articles of P, (ii) and (iii) so far, the
        eligibility of the issuers that survive them, the 09:30 bars of the gap) are made and stored by the session's
        verdict pre-passes from about 09:47 ET of D, once the 09:30 bar is on the Basic plan's tape."""
        W.evl5_rows(self.w)
        session = C.session(self.st, D)
        self.assertEqual(R.pre_from(session), et(D, 9, 47))
        self.w.at(et(D, 9, 15, 30)).decide("open", D)
        out = self.w.at(et(D, 9, 46, 59)).decide("close", D, ask_only=True)
        self.assertNotIn("evl5_pre", out)
        self.assertIsNone(self.st.meta(f"{R.PRE_KEY}{D}"))
        self.assertEqual(self.st.db.execute("SELECT COUNT(*) FROM marks WHERE label='0930'").fetchone()[0], 0)
        out = self.w.at(et(D, 9, 47)).decide("close", D, ask_only=True)
        self.assertEqual(out["evl5_pre"]["status"], "stored")
        pre = json.loads(self.st.meta(f"{R.PRE_KEY}{D}"))
        survivors = {CIK[t] for t in ("SSS", "TTT", "UUU", "YYY", "AAB", "AAC")}
        self.assertEqual(set(pre["survivors"]), survivors, "VVV (i), WWW (ii), XXX (iii), ZZZ (i, its edit counts)")
        self.assertEqual(pre["cut"], S.iso(et(D, 9, 47)))
        kept = {r[0] for r in self.st.db.execute("SELECT cik FROM eligibility WHERE day=? AND rule='live'", (D.isoformat(),))}
        self.assertTrue(survivors <= kept, "each survivor's eligibility kept as read (the live rule)")
        marks = {r[0]: r[1] for r in self.st.db.execute("SELECT symbol, px FROM marks WHERE label='0930' AND day=?",
                                                         (D.isoformat(),))}
        self.assertEqual(set(marks), {"SSS", "TTT", "UUU", "YYY", "AAC"},
                         "a batch stores only a price: AAB's 09:30 minute had no trade, so the pre-pass stores nothing")
        self.assertTrue(all(px is not None for px in marks.values()))
        self.assertEqual(self.intents("EVL-NEWS-NIGHT2-ON"), [], "no intent, no receipt")
        self.assertIsNone(self.st.db.execute("SELECT 1 FROM receipts WHERE job=?", (f"decide-close:{D}",)).fetchone())
        # the close decision reads AAB alone (09:30-09:35 ET): later minutes traded and 09:30 did not, so no trade there
        self.w.at(et(D, 15, 47)).decide("close", D)
        row = self.st.db.execute("SELECT px, source FROM marks WHERE label='0930' AND day=? AND symbol='AAB'",
                                 (D.isoformat(),)).fetchone()
        self.assertEqual((row["px"], row["source"]), (None, "sip-1min:none"))
        self.assertNotIn("AAB", self.taken("EVL-NEWS-NIGHT2-ON"))

    def test_the_pre_pass_and_the_close_give_what_one_computation_at_the_close_gives(self):
        """Every rule is unchanged by where it is read: the pre-pass at 09:47 ET and the close decision (which adds
        what came after the cut: an attention article stored late, an 8-K stored late, an article naming a survivor)
        decide EVL-NEWS-NIGHT2-ON's events exactly as one computation at the close does."""
        def day(world: W.World, pre: bool) -> list[tuple]:
            W.evl5_rows(world)
            world.at(et(D, 9, 15, 30)).decide("open", D)
            if pre:
                world.at(et(D, 9, 47)).decide("close", D, ask_only=True)
            # after the cut: SSS named by a new article, an attention article of AAD stored late (knowable Monday),
            # a late-stored 8-K of TTT knowable Monday afternoon, AAE's attention article stored at noon
            world.article("x-sss", "SSS", knowable=et(D, 11, 0))
            world.article("n-aad", "AAD", knowable=et(PRIOR, 13, 0), stored=et(D, 12, 0))
            world.filing("0000000020-26-000501", "TTT", knowable=et(PRIOR, 15, 0), stored=et(D, 13, 0), items=("8.01",))
            world.article("n-aae", "AAE", knowable=et(PRIOR, 14, 0), stored=et(D, 12, 30))
            world.gw.opens.update({"AAD": 21.0, "AAE": 20.2})
            if pre:
                world.at(et(D, 15, 17)).decide("close", D, ask_only=True)
            world.at(et(D, 15, 47)).decide("close", D)
            return [r for r in world.intents(lambda p, v: p == "EVL-NEWS-NIGHT2-ON")]
        other = W.World(Path(self.tmp.name) / "other")
        self.addCleanup(other.close)
        with_pre, without = day(self.w, True), day(other, False)
        self.assertEqual(with_pre, without)
        self.assertEqual(sorted(r[3] for r in with_pre), ["AAC", "AAD", "YYY"])
        summary = self.receipt(f"decide-close:{D}")["evl5"]
        self.assertEqual(summary["pre"]["cut"], S.iso(et(D, 15, 17)))
        self.assertEqual((summary["pre"]["added"], summary["pre"]["removed"]), (0, 0), "the 15:17 pass moved the cut")
        self.assertEqual(json.loads(other.st.meta(f"{R.PRE_KEY}{D}") or "null"), None, "no pre-pass in the other")


    def night2(self, world: W.World, *, pre: Callable[[W.Gateway], None] | None, close: Callable[[W.Gateway], None]
               = lambda gw: None) -> tuple[list[tuple], dict]:
        """D decided as the House decides it: the open, a pre-pass at 09:47 ET under `pre`'s feed (None: no pre-pass),
        the live close decision under `close`'s feed; EVL-NEWS-NIGHT2-ON's shadow intents and the real-money picks of
        D's close, read by the book after the lane's close decision (the lane's marks first, the book's own read
        else)."""
        W.evl5_rows(world)
        world.at(et(D, 9, 15, 30)).decide("open", D)
        if pre is not None:
            pre(world.gw)
            world.at(et(D, 9, 47)).decide("close", D, ask_only=True)
        world.gw.minutes_down, world.gw.minutes_partial = False, set()
        close(world.gw)
        world.at(et(D, 15, 47)).decide("close", D)
        world.gw.minutes_down, world.gw.minutes_partial = False, set()
        lane = EB.Lane(world.root / S.DB_NAME)
        try:
            session = C.session(lane, D)
            gap = EB.gap_reader(lane, D, opens=W.opening)
            reaction = EB.reaction_reader(lane, D, daily=lambda symbol, d: W.CLOSES.get((symbol, d), 20.0),
                                          minutes=lambda symbol, session: W.MINUTE.get(symbol))
            prog = EB.program_of("EVL-NEWS-NIGHT2-ON", 1)
            picks = [x.symbol for x in EB.picks(lane, prog, D, decided_at=session.close_decide, reaction=reaction,
                                                gap=gap)]
        finally:
            lane.close()
        return world.intents(lambda p, v: p == "EVL-NEWS-NIGHT2-ON"), {"picks": picks}

    def test_an_empty_or_partial_pre_pass_answer_removes_nothing(self):
        """The judges' review of this release (major): a 200 answer with no bar, or one that leaves names out, at the
        09:47 ET pre-pass stores NO row for the names it lacks (a batch stores only a price), so the close decision
        reads them and decides EVL-NEWS-NIGHT2-ON exactly as one computation at the close does, in the shadow and in
        real money (PREREG-EVL-1 section 3: an outage removes nothing; section 1.3: unchanged by where it is read)."""
        def down(gw: W.Gateway) -> None:
            gw.minutes_down = True

        def partial(gw: W.Gateway) -> None:
            gw.minutes_partial = {"SSS", "TTT", "AAC"}
        worlds = {}
        for name, pre in (("once", None), ("down", down), ("partial", partial), ("whole", lambda gw: None)):
            world = W.World(Path(self.tmp.name) / name)
            self.addCleanup(world.close)
            worlds[name] = (world, *self.night2(world, pre=pre))
        once = worlds["once"]
        self.assertEqual(sorted(r[3] for r in once[1]), ["AAC", "SSS", "TTT", "YYY"])
        self.assertEqual(sorted(once[2]["picks"]), ["AAC", "SSS", "TTT", "YYY"])
        for name in ("down", "partial", "whole"):
            world, intents, real = worlds[name]
            self.assertEqual(intents, once[1], name)
            self.assertEqual(real, once[2], name)
        down_world = worlds["down"][0]
        self.assertEqual(down_world.st.db.execute("SELECT COUNT(*) FROM marks WHERE label='0930' AND px IS NULL "
                                                  "AND symbol!='AAB'").fetchone()[0], 0, "no row of no trade but AAB's")

    def test_a_close_read_with_no_bar_stores_nothing_and_the_next_decision_reads_it(self):
        """A decision's read of a name alone: an answer with no bar at all is no answer (nothing stored: no gap at this
        decision, the shadow's next decision reads it again); a later minute's bar with none at 09:30 is the tape's
        word that the minute had no trade (a row with no price, never read again)."""
        world = self.w
        W.evl5_rows(world)
        world.at(et(D, 9, 15, 30)).decide("open", D)
        world.gw.minutes_down = True
        world.at(et(D, 15, 47)).decide("close", D)
        self.assertEqual(world.st.db.execute("SELECT COUNT(*) FROM marks WHERE label='0930'").fetchone()[0], 0)
        self.assertEqual(self.taken("EVL-NEWS-NIGHT2-ON"), [], "no gap read: nothing taken at this decision")
        world.gw.minutes_down = False
        world.at(et(D, 16, 41)).decide("close", D, live=False)
        self.assertEqual(self.taken("EVL-NEWS-NIGHT2-ON"), ["AAC", "SSS", "TTT", "YYY"], "the shadow's re-decision")
        none = world.st.db.execute("SELECT symbol FROM marks WHERE label='0930' AND px IS NULL").fetchall()
        self.assertEqual([r[0] for r in none], ["AAB"])
        before = len(world.gw.gets)
        world.at(et(D, 17, 41)).decide("close", D, live=False)
        reads = [g for g in world.gw.gets[before:] if g[0].endswith("/v2/stocks/bars") and g[1].get("timeframe") == "1Min"
                 and S.parse_iso(g[1]["end"]) - S.parse_iso(g[1]["start"]) <= dt.timedelta(minutes=5)]
        self.assertEqual(reads, [], "every survivor's minute is stored: none is read again")


class ThePrePassSchedule(WorldCase):
    def lane(self) -> H.EventLane:
        self.clock = Clock(S.iso(et(D, 9, 0)))
        house = FakeHouse(self.clock)
        return H.EventLane(house, self.w.root, gateway=self.w.gw, sec=W.sec, monotonic=Mono())

    def test_the_houses_schedule_of_the_pre_pass(self):
        """The House (league/events/house.py `_pre_due`): today's close verdict pass is due from 09:47 ET while meta
        `evl5:pre:<day>` is not stored, whatever the verdicts; inside the last 30 minutes once more, once the earlier
        rows' verdicts are all stored; a failed pre-read waits VERDICT_BACKOFF; never before the registration."""
        lane = self.lane()
        session = C.session(self.st, D)
        soon: list[dt.datetime] = []
        self.assertFalse(lane._pre_due(self.st, session, et(D, 9, 46), soon))
        self.assertIn(et(D, 9, 47), soon)
        self.assertTrue(lane._pre_due(self.st, session, et(D, 9, 47), []))
        self.st.set_meta(f"{R.PRE_KEY}{D}", json.dumps({"cut": S.iso(et(D, 9, 48)), "survivors": []}))
        soon = []
        self.assertFalse(lane._pre_due(self.st, session, et(D, 12, 0), soon))
        self.assertIn(session.close_decide - H.URGENT_BEFORE, soon)
        lane._looks[("close", D)] = H.VerdictLook(et(D, 15, 16), 2, False)
        self.assertFalse(lane._pre_due(self.st, session, et(D, 15, 17), []), "the earlier rows' asks first")
        lane._looks[("close", D)] = H.VerdictLook(et(D, 15, 16), 0, False)
        self.assertTrue(lane._pre_due(self.st, session, et(D, 15, 17), []))
        self.st.set_meta(f"{R.PRE_KEY}{D}", json.dumps({"cut": S.iso(et(D, 15, 17)), "survivors": []}))
        self.assertFalse(lane._pre_due(self.st, session, et(D, 15, 20), []), "the cut moved: done")
        self.st.db.execute("DELETE FROM meta WHERE key=?", (f"{R.PRE_KEY}{D}",))
        lane._pre_failed[D] = et(D, 10, 0)
        self.assertFalse(lane._pre_due(self.st, session, et(D, 10, 5), []))
        self.assertTrue(lane._pre_due(self.st, session, et(D, 10, 10), []))
        wed = C.session(self.st, dt.date(2026, 10, 21))
        self.assertFalse(lane._pre_due(self.st, wed, et(wed.day, 10, 0), []), "no attention article can be an event")
        latest = {f"decide-open:{D}": ("ok", et(D, 9, 15))}
        lane._events_at = et(D, 10, 0)
        lane._looks[("close", D)] = H.VerdictLook(et(D, 10, 29), 0, False)      # (no verdict is missing)
        urgent, early = lane._verdict_targets(self.st, et(D, 10, 30), D, session, latest, [])
        self.assertEqual((urgent, early), (None, ("close", D, True)), "the close's early verdict pass, for it alone")
        self.st.set_meta(f"{R.PRE_KEY}{D}", json.dumps({"cut": S.iso(et(D, 10, 30)), "survivors": []}))
        self.assertEqual(lane._verdict_targets(self.st, et(D, 10, 31), D, session, latest, []), (None, None))

    def test_a_failed_pre_read_backs_off_and_a_cut_one_goes_on(self):
        W.evl5_rows(self.w)
        lane = self.lane()
        self.w.at(et(D, 9, 15, 30)).decide("open", D)
        ctx = H.LaneContext(lane, self.st, H.LaneGateway(self.w.gw, lane, None, cut=False), W.sec,
                            lambda: et(D, 10, 0))
        self.clock.set(S.iso(et(D, 10, 0)))
        with mock.patch.object(R, "_marks_0930", side_effect=RuntimeError("the bars feed is down")):
            out = lane._verdicts(ctx, "close", D, True)
        self.assertIn(D, lane._pre_failed)
        self.assertIsNone(self.st.meta(f"{R.PRE_KEY}{D}"))
        self.assertEqual(out["decision"], "close")
        lane._pre_failed.clear()
        with mock.patch.object(R, "EVL5_PRE_BUDGET", -1.0):
            out = R.decide_close(ctx, D, ask_only=True)
        self.assertEqual(out["evl5_pre"]["status"], "cut")
        self.assertNotIn(D, lane._pre_failed)


# ----------------------------------------------------------------------------------------------------- the isolation
class TheIsolation(WorldCase):
    def week(self, world: W.World) -> None:
        W.evl4_rows(world)
        W.evl5_rows(world)
        world.at(et(D, 7, 31)).decide("open", D, ask_only=True)
        world.at(et(D, 9, 15, 30)).decide("open", D)
        world.at(et(D, 12, 30)).decide("close", D, ask_only=True)

    def test_a_failing_part_leaves_the_earlier_rows_whole_and_its_rows_unnamed(self):
        """Section 1.3: any failure in the part is the part's alone: the decision finishes with the earlier rows'
        results and names none of this file's rows, which `decide-close-evl5` then decides by themselves; that close is
        never traded for them."""
        other = W.World(Path(self.tmp.name) / "other")
        self.addCleanup(other.close)
        self.week(self.w)
        self.week(other)
        with mock.patch.object(R, "_rows_5", side_effect=RuntimeError("an invented failure")):
            out = self.w.at(et(D, 15, 47)).decide("close", D)
        with without_evl5():
            other.at(et(D, 15, 47)).decide("close", D)
        self.assertEqual(out["evl5_error"], "RuntimeError: an invented failure")
        receipt = self.receipt(f"decide-close:{D}")
        self.assertEqual(receipt["status"], "ok")
        for key in ALL5:
            self.assertFalse(SC.names(receipt, key), key)
        for key in ("EVL-ERN-REACT-C1@v2", "EVL-NEWS-READ-ON@v2", "EVL-8K-READ-ON"):
            self.assertTrue(SC.names(receipt, key), key)
        self.assertEqual(self.w.intents(earlier), other.intents(earlier), "the earlier rows' decision, whole")
        self.assertEqual(self.w.intents(lambda p, v: p in ALL5), [])
        self.assertEqual(SC.made_without(self.st, D, prereg=5), {D: False})
        lane = EB.Lane(self.w.root / S.DB_NAME)
        self.addCleanup(lane.close)
        self.assertEqual(EB.part_hold(lane, "EVL-ERN-DROP-ON", 1, D)[0], "never")
        self.assertIsNone(EB.part_hold(lane, "EVL-8K-READ-ON", 1, D), "PREREG-EVL-4's rows are not held")
        from league.events import __main__ as CLI

        self.w.at(et(D, 16, 30))
        got = CLI.decide_evl5(self.w.ctx, D)
        self.assertEqual(sorted(k for k in got if k in ALL5), sorted(ALL5))
        self.assertEqual(SC.made_without(self.st, D, prereg=5), {})
        self.assertEqual(EB.part_hold(lane, "EVL-ERN-DROP-ON", 1, D)[0], "never", "decided later: still never traded")
        self.assertEqual(self.taken("EVL-ERN-DROP-ON", D), ["KKK", "NNN"])

    def test_a_part_past_its_own_bound_finishes_the_receipt_in_time(self):
        """Section 1.3's own time bound: a part whose reads run past EVL5_BUDGET (here a gateway each of whose bars
        reads takes 20 invented seconds) stops with `PartDeadline`, inside the task's own bound less EVL5_FINISH: the
        receipt finishes ok with the earlier rows' results and none of this file's rows."""
        clock, inside = [1000.0], [False]
        inner, rows_5 = self.w.gw.get_json, R._rows_5

        def slow(path, params=None):
            if inside[0] and "bars" in path:
                clock[0] += 20.0
            return inner(path, params)

        def part(*a, **k):
            inside[0] = True
            try:
                return rows_5(*a, **k)
            finally:
                inside[0] = False
        W.evl4_rows(self.w)
        W.evl5_rows(self.w)
        self.w.at(et(D, 9, 15, 30)).decide("open", D)         # (no pre-pass: the part reads its 09:30 minutes itself)
        self.w.gw.get_json = slow
        self.w.ctx.mono = lambda: clock[0]
        self.w.ctx.deadline = clock[0] + 150.0
        with mock.patch.object(R, "EVL5_BUDGET", 30.0), mock.patch.object(R, "_rows_5", part):
            out = self.w.at(et(D, 15, 47)).decide("close", D)
        self.assertTrue(out["evl5_error"].startswith("PartDeadline: PREREG-EVL-5's part ran past its own time bound"),
                        out["evl5_error"])
        self.assertLess(clock[0], self.w.ctx.deadline - R.EVL5_FINISH)
        receipt = self.receipt(f"decide-close:{D}")
        self.assertEqual(receipt["status"], "ok")
        self.assertFalse(any(SC.names(receipt, k) for k in ALL5))
        self.assertTrue(SC.names(receipt, "EVL-NEWS-REACT-ON@v2"))
        self.assertTrue(issubclass(R.PartDeadline, Exception) and not issubclass(R.PartDeadline, R.Deadline))

    def test_the_tasks_own_bound_inside_the_part_stops_the_task(self):
        """A `Deadline` (the task's bound, the House's `LaneDeadline`) inside the part is never the part's failure: the
        task stops and its next turn decides the close again, whole."""
        self.week(self.w)
        with mock.patch.object(R, "_rows_5", side_effect=H.LaneDeadline("the task's bound")):
            with self.assertRaises(H.LaneDeadline):
                self.w.at(et(D, 15, 47)).decide("close", D)

    def test_a_failing_pre_read_leaves_the_earlier_asks_stored(self):
        W.evl4_rows(self.w)
        W.evl5_rows(self.w)
        self.w.at(et(D, 9, 15, 30)).decide("open", D)
        with mock.patch.object(R, "_rows_5", side_effect=RuntimeError("down")):
            out = self.w.at(et(D, 12, 30)).decide("close", D, ask_only=True)
        self.assertEqual(out["evl5_pre"], {"status": "error", "why": "RuntimeError: down"})
        asked = set(self.w.gw.asked())
        self.assertIn("news:DDD", asked, "EVL-NEWS-READ-ON's ask, made before the part")
        self.assertIn("doc:CCC", asked, "EVL-8K-READ-ON's ask (PREREG-EVL-4's part)")
        self.assertFalse(any(k in out["pending"] for k in ALL5))



# ----------------------------------------------------------------------------------------------------------- the book
class TheBook(WorldCase):
    def lane(self) -> EB.Lane:
        lane = EB.Lane(self.w.root / S.DB_NAME)
        self.addCleanup(lane.close)
        return lane

    def test_the_three_seat_at_learning_after_preregevl4s_rows_and_before_the_births(self):
        """ROOM: Sized, then Probe, then learning; within a band the tables' order: PREREG-EVL-1's rows, -2's, -4's,
        then this file's in section 1.2's order; R3's births after every file's rows; the control never seats."""
        self.w.births()
        lane = self.lane()
        ids = [p.id for p in EB.seatable()]
        self.assertEqual(ids[:15], list(NINE + FOUR + FIVE))
        self.assertEqual(ids[15:], ["EVL-B-ERNREACT-DIP", "EVL-B-8K-502"])
        bands = {b.program: b.band for b in EB.bands(lane)}
        self.assertEqual({pid: bands[pid] for pid in FIVE}, dict.fromkeys(FIVE, "learning"))
        self.assertIsNone(EB.program_of(CONTROL5, 1))
        self.assertIsNone(EB.program_of("EVL-ERN-DROP-ON", 2))
        order = ["EVL-NEWSPM-READ-ON", *FIVE, "EVL-B-ERNREACT-DIP"]
        keys = [EB.room_key(pid, "learning") for pid in order]
        self.assertEqual(keys, sorted(keys))
        self.assertLess(EB.room_key("EVL-NEWS-NIGHT2-ON", "probe"), EB.room_key("EVL-ERN-READ-O1", "learning"))

        def pick(program: str) -> EB.Pick:
            return EB.Pick(program, 1, f"e:{program}", "SAME", "1", 2.0, 1e6, Decimal(10), "z")
        given = EB.one_name_an_auction({pid: [pick(pid)] for pid in ("EVL-ERN-UNDER-ON", "EVL-8K-READ-ON",
                                                                     "EVL-B-ERNREACT-DIP")})
        self.assertEqual({k: [p.symbol for p in v] for k, v in given.items()},
                         {"EVL-8K-READ-ON": ["SAME"], "EVL-ERN-UNDER-ON": [], "EVL-B-ERNREACT-DIP": []})

    def test_real_money_reads_rows_stored_and_answered_before_its_decision(self):
        """Section 1.3: the shadow rule over the events STORED, and the verdicts ANSWERED, before D's close decision
        time, TAKEN and NO NEW INFORMATION applied to those rows; a DAY(D) article unanswered by then skips its issuer
        (the shadow waits); a row stored later counts in the shadow only."""
        W.evl5_rows(self.w)
        g = self.w.gw
        self.w.filing("0000000029-26-000601", "AAD", accepted=et(PRIOR, 17, 0), items=("2.02",))
        self.w.article("n-aad-day", "AAD", knowable=et(D, 13, 0))
        g.minute["AAD"] = 19.0
        g.refuse.add("AAD")                                          # its day-news verdict: no answer by 15:46
        self.close()
        self.assertEqual(self.close_pending(), {"EVL-ERN-DROP-ON": 1}, "the shadow waits for AAD's answer")
        lane = self.lane()
        got = W.picks(self.w, lambda p: p.prereg == 5)
        self.assertEqual([x[1] for x in got[f"EVL-ERN-DROP-ON@v1@{D}"]], ["KKK"],
                         "NNN barred by the guard (score 1, raised); AAD skipped: its DAY(D) article unanswered")
        self.assertEqual([x[1] for x in got[f"EVL-ERN-UNDER-ON@v1@{D}"]], ["MMM"],
                         "LLL barred by the guard: UNDER buys only a release knowable before 09:00 ET of D")
        self.assertEqual([(x[1], x[3]) for x in got[f"EVL-NEWS-NIGHT2-ON@v1@{D}"]],
                         [("YYY", 1.05), ("AAC", 1.04), ("SSS", 1.03), ("TTT", 1.02)], "ranked by the gap, then ADV")
        lane.close()
        g.refuse.clear()
        self.w.at(et(D, 16, 0)).decide("close", D, live=False)
        self.assertIn("AAD", self.taken("EVL-ERN-DROP-ON", D), "the shadow keeps its event once answered")
        self.w.article("n-aac-2", "AAC", knowable=et(D, 14, 0), stored=et(D, 16, 30))
        self.w.at(et(D, 16, 41)).decide("close", D, live=False)
        rows = {r["symbol"]: r["status"] for r in self.intents("EVL-NEWS-NIGHT2-ON", D)}
        self.assertEqual(rows["AAC"], "skipped:taken", "an article stored later: the shadow skips the issuer")
        got = W.picks(self.w, lambda p: p.id == "EVL-NEWS-NIGHT2-ON")
        self.assertIn("AAC", [x[1] for x in got[f"EVL-NEWS-NIGHT2-ON@v1@{D}"]], "real money read the rows stored before")

    def close_pending(self) -> dict:
        return {k: v for k, v in self.receipt(f"decide-close:{D}")["pending"].items() if k in ALL5}

    def test_the_guard_bars_raised_for_these_rows_and_preregevl4s_is_unchanged(self):
        """NO REAL-MONEY TAKING FROM AN EARLIER ROW: in real money only, EVL-ERN-DROP-ON and EVL-ERN-UNDER-ON do not buy
        for a filing knowable at or after 09:00 ET of D whose stored PROMPT-DOC verdict is `ok` with score >= 2, or `ok`
        with score >= 1 and guidance raised, or not yet answered, at D's close decision time; PREREG-EVL-4's rows keep
        their guard (score >= 2, or not answered)."""
        w = self.w
        cases = {"0000000011-26-000701": (et(D, 10, 0), 1, "raised", et(D, 12, 0)),        # raised: barred
                 "0000000012-26-000701": (et(D, 10, 0), 1, "maintained", et(D, 12, 0)),    # bought
                 "0000000013-26-000701": (et(D, 10, 0), 2, "none", et(D, 12, 0)),          # barred
                 "0000000014-26-000701": (et(D, 10, 0), 3, "none", et(D, 15, 46, 30)),     # answered after: barred
                 "0000000015-26-000701": (et(D, 10, 0), None, None, None),                 # unanswered: barred
                 "0000000016-26-000701": (et(PRIOR, 17, 0), 3, "raised", et(PRIOR, 18, 0)),  # before 09:00 of D
                 "0000000017-26-000701": (et(D, 10, 0), 1, "raised", et(D, 12, 0))}        # unparsed: bought
        for i, (acc, (accepted, score, guidance, answered)) in enumerate(cases.items()):
            w.filing(acc, NEW_TICKERS[i], accepted=accepted, items=("2.02",))
            if answered is not None:
                self.verdict(f"8k:{acc}", score, answered, guidance=guidance,
                             status="unparsed" if acc.startswith("0000000017") else "ok")
        lane = self.lane()
        session = C.session(lane, D)
        moment = session.close_decide
        rows = {r["accession"]: dict(r) for r in lane.db.execute("SELECT * FROM filings")}
        barred = {acc: EB.next_open_event(lane, rows[acc], session, moment, raised=True) for acc in cases}
        self.assertEqual([acc for acc, b in barred.items() if not b],
                         ["0000000012-26-000701", "0000000016-26-000701", "0000000017-26-000701"])
        four = {acc: EB.next_open_event(lane, rows[acc], session, moment) for acc in cases}
        self.assertFalse(four["0000000011-26-000701"], "PREREG-EVL-4's guard: score 1 raised is bought, as before")
        self.assertEqual(EB.RAISED_GUARD, ("EVL-ERN-DROP-ON", "EVL-ERN-UNDER-ON"))
        self.assertEqual(set(EB.NEXT_OPEN_GUARD), {"EVL-8K-REACT-ON", "EVL-8K-READ-ON", *EB.RAISED_GUARD})
        self.assertNotIn("EVL-NEWS-NIGHT2-ON", EB.NEXT_OPEN_GUARD)

    def test_the_gap_reader(self):
        """The gap is read from SIP minute bars as the book reads the reactions: the lane's stored 09:30 mark first
        (one with no price: no trade, not bought), else the book's own reading, all the day's live names together."""
        lane_rows = self.st
        for t in ("KKK", "LLL", "MMM", "NNN"):
            lane_rows.db.execute("INSERT INTO universe(day, symbol, cik, name, exchange, prev_close, adv20, bench, sigma60) "
                                 "VALUES(?, ?, ?, 'x', 'NASDAQ', 20.0, 1e7, 'IWM', NULL)", (D.isoformat(), t, CIK[t]))
            lane_rows.db.execute("INSERT INTO eligibility(day, cik, rule, eligible, symbol, decided_at) VALUES(?, ?, 'live', "
                                 "1, ?, 'x')", (D.isoformat(), CIK[t], t))
        lane_rows.db.execute("INSERT INTO marks(symbol, day, label, px, t, source, fetched_at) VALUES('KKK', ?, '0930', 20.6, "
                             "'t', 'sip-1min', 'x')", (D.isoformat(),))
        lane_rows.db.execute("INSERT INTO marks(symbol, day, label, px, t, source, fetched_at) VALUES('LLL', ?, '0930', NULL, "
                             "'t', 'sip-1min:none', 'x')", (D.isoformat(),))
        asked: list[tuple] = []
        lane = self.lane()

        def many(names, session):
            asked.append(tuple(names))
            return {"MMM": 21.0, "NNN": None}

        def one(symbol, session):
            asked.append(("one", symbol))
            return 20.2
        gap = EB.gap_reader(lane, D, opens=one, opens_many=many)
        uni = lambda t: {"symbol": t, "prev_close": 20.0}  # noqa: E731
        self.assertAlmostEqual(gap({}, uni("KKK")), 1.03)
        self.assertIsNone(gap({}, uni("LLL")), "a stored minute with no trade: no gap")
        self.assertAlmostEqual(gap({}, uni("MMM")), 1.05)
        self.assertIsNone(gap({}, uni("NNN")))
        self.assertAlmostEqual(gap({}, uni("OUT")), 1.01)
        self.assertEqual(asked, [("MMM", "NNN"), ("one", "OUT")], "one batch for the live names with no mark")
        bars = [{"t": S.iso(C.session(lane, D).open_at), "o": 20.5}, {"t": S.iso(et(D, 9, 31)), "o": 30.0}]
        self.assertEqual(EB.opening_minute(bars, C.session(lane, D)), 20.5)
        self.assertIsNone(EB.opening_minute(bars[1:], C.session(lane, D)))

    def test_part_hold(self):
        """The earlier rows' decision comes first: a buy of this file's rows at D's close goes once the lane's first
        finished close decision of D names its program; waits while there is none; never when it does not name it."""
        lane = self.lane()
        self.assertEqual(EB.part_hold(lane, "EVL-ERN-DROP-ON", 1, D)[0], "wait")
        self.assertIsNone(EB.part_hold(lane, "EVL-NEWSPM-READ-ON", 1, D))
        lane.close()
        rid = self.st.start_receipt(f"decide-close:{D}", now=et(D, 15, 47))
        self.assertEqual(EB.part_hold(self.lane(), "EVL-ERN-DROP-ON", 1, D)[0], "wait", "running: not finished")
        self.st.finish_receipt(rid, "ok", {"EVL-ERN-DROP-ON": {"planned": 1}, "kept": {"EVL-NEWS-NIGHT2-ON": {}}},
                               now=et(D, 15, 48))
        lane = self.lane()
        self.assertIsNone(EB.part_hold(lane, "EVL-ERN-DROP-ON", 1, D))
        self.assertIsNone(EB.part_hold(lane, "EVL-NEWS-NIGHT2-ON", 1, D), "kept is named")
        self.assertEqual(EB.part_hold(lane, "EVL-ERN-UNDER-ON", 1, D)[0], "never")
        rid = self.st.start_receipt(f"decide-close:{D}", now=et(D, 15, 50))
        self.st.finish_receipt(rid, "ok", {"EVL-ERN-UNDER-ON": {"planned": 1}}, now=et(D, 15, 51))
        self.assertEqual(EB.part_hold(self.lane(), "EVL-ERN-UNDER-ON", 1, D)[0], "never", "the first finished one counts")


NEW_TICKERS = ("KKK", "LLL", "MMM", "NNN", "OOO", "PPP", "QQQ", "RRR")


class TheBookLive(TB.EventTest):
    """Through the REAL book (league/equity/live.py's event kind): a PREREG-EVL-5 buy is planned at the close decision
    in ROOM's order, at learning size, and goes only once the lane's own close decision names its program; a close
    whose part failed is never traded."""

    def drop(self, h: TB.Harness) -> None:
        h.lane.universe(TB.DAY, "ACME", TB.CIK, 16.0)
        h.lane.filing("e-1", TB.CIK, accepted=TB.iso(TB.PRIOR, 16, 30), items=("2.02",))
        h.lane.verdict("e-1", 1, answered=TB.iso(TB.PRIOR, 16, 40))
        h.lane.st.db.execute("INSERT INTO marks(symbol, day, label, px, t, source, fetched_at) VALUES('ACME', ?, '1530', "
                             "15.2, 't', 'sip-1min', 'x')", (TB.DAY.isoformat(),))
        h.lane.st.db.execute("INSERT INTO bars(symbol, day, adj, o, h, l, c, v, fetched_at) VALUES('ACME', ?, 'raw', 16, 16, "
                             "16, 16.0, 1e6, 'x')", (TB.PRIOR.isoformat(),))
        h.lane.decided(TB.DAY, "open")
        h.symbol("ACME", last=15.2)
        h.venue.prints[("ACME", TB.DAY.isoformat(), "close")] = Decimal("15.30")

    def close_receipt(self, h: TB.Harness, summary: dict) -> None:
        rid = h.lane.st.start_receipt(f"decide-close:{TB.DAY.isoformat()}")
        h.lane.st.finish_receipt(rid, "ok", summary)

    def test_a_buy_waits_for_the_lanes_close_decision_to_name_its_program(self):
        h = self.harness()
        self.drop(h)
        for hh, mm in ((9, 15), (9, 16), (15, 46), (15, 47)):
            h.tick(hh, mm, day=TB.DAY)
        [buy] = h.event_intents("buy")
        self.assertEqual((buy["program"], buy["version"], buy["band"], buy["tif"], buy["limit_px"], buy["exit_day"],
                          buy["exit_at"]), ("EVL-ERN-DROP-ON", 1, "learning", "cls", "20.00", TB.NEXT.isoformat(), "open"))
        self.assertEqual(h.bodies(), [], "no buy before the lane's own close decision names the program")
        self.assertIn("waits for the lane's own close decision", buy["why"])
        self.close_receipt(h, {"EVL-ERN-DROP-ON": {"planned": 1}})
        h.tick(15, 48, day=TB.DAY)
        [body] = h.bodies()
        self.assertEqual((body["symbol"], body["qty"], body["side"], body["type"], body["time_in_force"],
                          body["limit_price"]), ("ACME", "2", "buy", "limit", "cls", "20.00"),
                         "2% of E=$2,000 at the $20.00 limit, limit-on-close")
        h.tick(16, 1, day=TB.DAY)
        h.tick(16, 3, day=TB.DAY)
        [lot] = h.lots()
        self.assertEqual((lot.family, lot.version, lot.info["evl_exit"]["day"], lot.info["evl_exit"]["at"]),
                         ("EVL-ERN-DROP-ON", 1, TB.NEXT.isoformat(), "open"))

    def test_a_close_whose_part_failed_is_never_traded(self):
        h = self.harness()
        self.drop(h)
        self.close_receipt(h, {"EVL-ERN-REACT-C1@v2": {"planned": 0}, "evl5_error": "PartDeadline: past its own bound"})
        for hh, mm in ((9, 15), (9, 16), (15, 46), (15, 47), (15, 48)):
            h.tick(hh, mm, day=TB.DAY)
        [buy] = h.event_intents("buy")
        self.assertEqual(buy["status"], "refused")
        self.assertIn("never traded", buy["why"])
        self.assertEqual(h.bodies(), [])


class TheRoomWhileItWaits(TB.EventTest):
    """The money review of release 1019g (major): while a PREREG-EVL-5 buy waits for the lane's close decision
    (`book.part_hold`), ROOM's order holds at the close auction: every buy AFTER it in ROOM's order is sized and counted
    as if the waiting buy were already working (its worst case out of their cash, invested room, loss budget and name
    wall; its send and its exit out of the event line and the House-wide line), and a later buy that fits only without
    that room waits too instead of being refused; the waiting buy is never held behind them. Invented figures: E is
    $2,000 and the options book reserves $1,905, so $45 of cash is free (the $50 reserve kept): one learning buy of two
    shares at its $20.00 limit fits, two do not."""

    def setUp(self):
        super().setUp()
        self.addCleanup(P.load_births, None)

    def fall(self, h: TB.Harness, symbol: str, cik: str, acc: str, mark: float, *, score: int = 1,
             day: dt.date = TB.DAY, prior: dt.date = TB.PRIOR) -> None:
        """An earnings 8-K of `symbol` accepted at 16:30 ET of `prior`, its verdict, its universe row of `day` ($16.00:
        the $20.00 limit), the raw close of `prior` ($16.00) and the T29 mark of `day` (`mark`)."""
        h.lane.universe(day, symbol, cik, 16.0)
        h.lane.filing(acc, cik, accepted=TB.iso(prior, 16, 30), items=("2.02",))
        h.lane.verdict(acc, score, answered=TB.iso(prior, 16, 40))
        h.lane.st.db.execute("INSERT INTO marks(symbol, day, label, px, t, source, fetched_at) VALUES(?, ?, '1530', ?, 't', "
                             "'sip-1min', 'x')", (symbol, day.isoformat(), mark))
        h.lane.st.db.execute("INSERT OR REPLACE INTO bars(symbol, day, adj, o, h, l, c, v, fetched_at) VALUES(?, ?, 'raw', "
                             "16, 16, 16, 16.0, 1e6, 'x')", (symbol, prior.isoformat()))
        h.symbol(symbol, last=mark)
        h.venue.prints[(symbol, day.isoformat(), "close")] = D_("15.30")

    def birth(self, h: TB.Harness) -> P.Program:
        """A registered close-entry birth of R3 (a fall to 0.97 or less with a PROMPT-DOC score >= 1, by the reaction,
        out at the next open), seatable: ROOM puts it after every PREREG program (`book.BIRTH_ROOM`)."""
        from league.events import births as BI

        sp = {"id": "EVL-B-ERNREACT-DIP", "version": 1, "family": "ern-react",
              "rule": {"react_max": 0.97, "score_min": 1}, "entry": BI.ENTRY["ern-react"], "exit": "open", "hold": 1,
              "rank": "reaction", "seatable": True}
        at = "2026-11-03T01:00:00Z"
        h.lane.st.db.execute("INSERT INTO births(id, version, sha, spec, seatable, registered_at, committed_at, "
                             "received_at, path, commit_sha, seq, line, why, by, night) VALUES(?, 1, ?, ?, 1, ?, ?, ?, "
                             "'docs/births/2026-11-02.jsonl', ?, 0, '{}', 'x', 'captain', '2026-11-02')",
                             (sp["id"], BI.sha(sp), BI.canonical(sp), at, at, at, "c" * 40))
        [born] = [b for b in P.load_births(h.lane.st) if b.id == sp["id"]]
        return born

    def receipt(self, h: TB.Harness, *names: str, day: dt.date = TB.DAY) -> None:
        rid = h.lane.st.start_receipt(f"decide-close:{day.isoformat()}")
        h.lane.st.finish_receipt(rid, "ok", {name: {"planned": 1} for name in names})

    def sent(self, h: TB.Harness) -> list[tuple[str, str]]:
        return [(b["symbol"], b["qty"]) for b in h.bodies() if b["side"] == "buy"]

    def buy(self, h: TB.Harness, symbol: str) -> dict:
        [row] = [r for r in h.event_intents("buy") if r["symbol"] == symbol]
        return row

    def test_a_birth_after_a_waiting_learning_row_leaves_it_the_cash(self):
        h = self.harness()
        h.options.reserved_usd = 1905.0
        self.fall(h, "ACME", TB.CIK, "e-1", 15.2)                # 0.95: EVL-ERN-DROP-ON (learning, its row first)
        self.fall(h, "BETA", TB.CIK2, "e-2", 15.44)              # 0.965: the birth's alone (DROP needs <= 0.96)
        born = self.birth(h)
        self.assertGreater(EB.room_key(born.id, "learning"), EB.room_key("EVL-ERN-DROP-ON", "learning"))
        h.lane.decided(TB.DAY, "open")
        for hh, mm in ((9, 15), (9, 16), (15, 46), (15, 47)):
            h.tick(hh, mm)
        self.assertEqual(sorted((r["program"], r["symbol"]) for r in h.event_intents("buy")),
                         [(born.id, "BETA"), ("EVL-ERN-DROP-ON", "ACME")])
        self.assertEqual(self.sent(h), [], "the birth does not take the $40 ROOM keeps for the waiting buy")
        self.assertIn(EB.PART_WAIT, self.buy(h, "ACME")["why"])
        self.assertIn(L.HELD_ROOM, self.buy(h, "BETA")["why"], "it waits too: refused only once the room is spent")
        self.assertEqual(self.buy(h, "BETA")["status"], "planned")
        self.receipt(h, "EVL-ERN-DROP-ON")
        h.tick(15, 48)
        self.assertEqual(self.sent(h), [("ACME", "2")], "the waiting buy gets its two shares: ROOM's order")
        self.assertEqual(self.buy(h, "BETA")["status"], "refused")
        self.assertIn("no whole share fits", self.buy(h, "BETA")["why"])

    def test_a_close_that_never_names_the_row_frees_its_room_for_the_buy_after_it(self):
        h = self.harness()
        h.options.reserved_usd = 1905.0
        self.fall(h, "ACME", TB.CIK, "e-1", 15.2)
        self.fall(h, "BETA", TB.CIK2, "e-2", 15.44)
        born = self.birth(h)
        h.lane.decided(TB.DAY, "open")
        for hh, mm in ((9, 15), (9, 16), (15, 46), (15, 47)):
            h.tick(hh, mm)
        rid = h.lane.st.start_receipt(f"decide-close:{TB.DAY.isoformat()}")
        h.lane.st.finish_receipt(rid, "ok", {f"{born.id}@v1": {"planned": 1}, "evl5_error": "PartDeadline: past its bound"})
        h.tick(15, 48)
        self.assertEqual(self.buy(h, "ACME")["status"], "refused", "never traded")
        self.assertEqual(self.sent(h), [("BETA", "2")], "nothing is kept for a buy that will never go")

    def test_a_waiting_probe_row_leaves_a_learning_row_of_preregevl1_after_it_the_cash(self):
        h = self.harness()
        h.options.reserved_usd = 1905.0
        self.fall(h, "ACME", TB.CIK, "e-1", 15.2)                # EVL-ERN-DROP-ON at Probe: (1, 12)
        self.fall(h, "GAMA", TB.CIK3, "e-3", 16.8, score=0)      # 1.05: EVL-ERN-REACT-C1 at learning: (2, 1)
        h.lane.band("EVL-ERN-DROP-ON", "probe", version=1)
        self.assertLess(EB.room_key("EVL-ERN-DROP-ON", "probe"), EB.room_key("EVL-ERN-REACT-C1", "learning"))
        h.lane.decided(TB.DAY, "open")
        for hh, mm in ((9, 15), (9, 16), (15, 46), (15, 47)):
            h.tick(hh, mm)
        programs = {r["symbol"]: (r["program"], r["band"]) for r in h.event_intents("buy")}
        self.assertEqual(programs, {"ACME": ("EVL-ERN-DROP-ON", "probe"), "GAMA": ("EVL-ERN-REACT-C1", "learning")})
        self.assertEqual(self.sent(h), [], "the learning row does not take the Probe row's cash while it waits")
        self.receipt(h, "EVL-ERN-DROP-ON")
        h.tick(15, 48)
        self.assertEqual(self.sent(h), [("ACME", "2")], "Probe first: two shares, all the $45 holds")
        self.assertEqual(self.buy(h, "GAMA")["status"], "refused")

    def test_a_waiting_row_keeps_its_send_and_its_exit_on_the_event_line(self):
        h = self.harness()
        self.fall(h, "ACME", TB.CIK, "e-1", 15.2)
        self.fall(h, "BETA", TB.CIK2, "e-2", 15.44)
        born = self.birth(h)
        h.lane.decided(TB.DAY, "open")
        tight = dataclasses.replace(EB.settings(), max_orders_day=2)    # (the line: one entry and its exit)
        with mock.patch.object(EB, "settings", lambda constitution=None: tight):
            for hh, mm in ((9, 15), (9, 16), (15, 46), (15, 47)):
                h.tick(hh, mm)
            self.assertEqual(self.sent(h), [], "the birth leaves the line's two orders to the waiting buy")
            self.assertIn("the event kind's day order count", self.buy(h, "BETA")["why"])
            self.assertIn(L.HELD_AHEAD, self.buy(h, "BETA")["why"])
            self.receipt(h, "EVL-ERN-DROP-ON", f"{born.id}@v1")
            h.tick(15, 48)
        self.assertEqual(self.sent(h), [("ACME", "2")])

    def test_a_waiting_probe_row_keeps_its_line_slots_from_a_learning_row_of_preregevl1_after_it(self):
        h = self.harness()
        self.fall(h, "ACME", TB.CIK, "e-1", 15.2)
        self.fall(h, "GAMA", TB.CIK3, "e-3", 16.8, score=0)
        h.lane.band("EVL-ERN-DROP-ON", "probe", version=1)
        h.lane.decided(TB.DAY, "open")
        tight = dataclasses.replace(EB.settings(), max_orders_day=2)
        with mock.patch.object(EB, "settings", lambda constitution=None: tight):
            for hh, mm in ((9, 15), (9, 16), (15, 46), (15, 47)):
                h.tick(hh, mm)
            self.assertEqual(self.sent(h), [], "the learning row leaves the line's two orders to the waiting Probe row")
            self.assertIn("the event kind's day order count", self.buy(h, "GAMA")["why"])
            self.receipt(h, "EVL-ERN-DROP-ON")
            h.tick(15, 48)
        probe = str(int(tight.share("probe") * 2000 // 20))
        self.assertEqual(self.sent(h), [("ACME", probe)], "Probe's share of E at the $20.00 limit")

    def test_a_decision_started_at_its_time_gives_the_book_a_minute_to_send(self):
        """The same book minutes (at :40 seconds), the lane's close decision started at 15:47:00 ET (the lane's hold,
        `house.HOLD_LEAD`) and finished at 15:47:05: the 15:47:40 minute sends the buy, well before the cut-off."""
        h = self.harness()
        self.fall(h, "ACME", TB.CIK, "e-1", 15.2)
        h.lane.decided(TB.DAY, "open")
        for hh, mm in ((9, 15), (9, 16)):
            h.tick(hh, mm)
        h.tick(15, 46, 40)
        self.receipt(h, "EVL-ERN-DROP-ON")                       # (15:47:05 ET)
        h.tick(15, 47, 40)
        self.assertEqual(self.sent(h), [("ACME", "2")])

    def test_buys_left_unsent_waiting_for_the_lanes_decision_are_counted_and_a_recurrence_alarmed(self):
        """The money review's third finding: at realistic tick spacing (a book minute at :40 seconds) a lane decision
        that finishes at 15:48:50 ET leaves its rows' buy unsent at the window's cut-off (the close - 11 minutes); the
        book says it after the close (an `equity.alert`, info), the lane's report counts it per close
        (`room_effects`), and a second such close within five sessions makes the alarm a warning."""
        h = self.harness()
        self.fall(h, "ACME", TB.CIK, "e-1", 15.2)
        h.lane.decided(TB.DAY, "open")
        for hh, mm in ((9, 15), (9, 16)):
            h.tick(hh, mm)
        for mm in (46, 47, 48):
            h.tick(15, mm, 40)
        self.receipt(h, "EVL-ERN-DROP-ON")                       # (15:48:50 ET)
        h.tick(15, 49, 40)
        h.tick(16, 2, 10)
        buy = self.buy(h, "ACME")
        self.assertEqual(buy["status"], "missed")
        self.assertIn("never sent", buy["why"])
        self.assertIn(EB.PART_WAIT, buy["why"])
        self.assertEqual(self.sent(h), [])
        [said] = [p for k, p in h.events if k == "equity.alert" and "evl5_held_unsent" in p]
        self.assertEqual((said["day"], said["evl5_held_unsent"], said["recent"]), (TB.DAY.isoformat(), 1, []))
        self.assertEqual([lv for lv, text in h.alerts if "PREREG-EVL-5" in text], ["info"])
        room = RP.room_effects(h.lane.st, TB.DAY)
        self.assertEqual((room["held_unsent"], room["room_waited"]), (1, 0))
        self.assertEqual(RP.HELD_UNSENT, EB.PART_WAIT)
        self.assertEqual(RP.ROOM_WAIT, L.HELD_AHEAD)
        self.assertNotIn(RP.ROOM_WAIT, EB.PART_WAIT, "a waiting buy of these rows is never counted as a later one")
        h.tick(16, 5)
        self.assertEqual(len([p for k, p in h.events if k == "equity.alert" and "evl5_held_unsent" in p]), 1, "once")
        # the next session, the same late decision: it recurs
        self.fall(h, "OMEG", "0000000009", "e-9", 15.0, day=TB.NEXT, prior=TB.DAY)
        h.lane.decided(TB.NEXT, "open")
        for hh, mm in ((9, 15), (9, 16)):
            h.tick(hh, mm, day=TB.NEXT)
        for mm in (46, 47, 48):
            h.tick(15, mm, 40, day=TB.NEXT)
        self.receipt(h, "EVL-ERN-DROP-ON", day=TB.NEXT)
        h.tick(15, 49, 40, day=TB.NEXT)
        h.tick(16, 2, 10, day=TB.NEXT)
        said = [p for k, p in h.events if k == "equity.alert" and "evl5_held_unsent" in p]
        self.assertEqual((said[-1]["day"], said[-1]["recent"]), (TB.NEXT.isoformat(), [TB.DAY.isoformat()]))
        self.assertEqual([lv for lv, text in h.alerts if "PREREG-EVL-5" in text], ["info", "warning"])


class TheLanesTurnForItsCloseDecision(TH.LaneCase):
    """The money review of release 1019g (third finding): real money buys this file's rows only once the lane's close
    decision has finished and only until the close - 11 minutes, while the lane's turns start only on the House's
    publishes. From `HOLD_LEAD` before its live close decision (the close decision + CLOSE_GRACE, 15:47:00 ET) a turn
    keeps going: it runs what falls due meanwhile and starts the decision AT its time, not at the next publish; `due()`
    looks again no later than the lead's start. Here the lane's sleep moves the House's clock."""

    def new_lane(self, redecide=False, **settings):
        lane = super().new_lane(redecide, **settings)

        def sleep(seconds: float) -> None:
            self.mono.advance(seconds)
            self.clock.advance(seconds)
        lane._sleep = sleep
        self.ran: list[tuple[str, str]] = []
        note = lane._note

        def noted(name, status, summary, began):
            self.ran.append((name, S.iso(lane.now())))
            return note(name, status, summary, began)
        lane._note = noted
        return lane

    def opened(self, day: str = "2026-10-20") -> None:
        with self.store() as st:
            rid = st.start_receipt(f"decide-open:{day}", now=TH.et(day, "09:15"))
            st.finish_receipt(rid, "ok", {}, now=TH.et(day, "09:16"))

    def test_a_turn_inside_the_lead_starts_the_live_close_decision_at_its_time(self):
        self.opened()
        self.at(TH.et("2026-10-20", "15:44") + dt.timedelta(seconds=40))
        self.mark_recorded()
        self.lane.run()
        [close] = self.receipts("decide-close:2026-10-20")
        self.assertEqual(close["started_at"], "2026-10-20T19:47:00Z", "at 15:47:00 ET, not at the next publish")
        self.assertEqual(close["status"], "ok")
        names = [n for n, _ in self.ran]
        self.assertEqual(names[-1], "decide-close")
        self.assertIn("record", names, "what fell due in the lead ran in it (the record pass at 15:46:40)")
        self.assertTrue(all(at < "2026-10-20T19:47:00Z" for n, at in self.ran if n != "decide-close"))
        self.assertIsNone(self.lane.health()["running"])

    def test_due_looks_again_at_the_leads_start_and_no_rows_no_hold(self):
        self.opened()
        self.at(TH.et("2026-10-20", "15:42"))
        self.mark_recorded(TH.et("2026-10-20", "15:42") + dt.timedelta(seconds=50))   # (the next record pass: 15:44:50)
        self.lane._looks[("close", dt.date(2026, 10, 20))] = H.VerdictLook(TH.et("2026-10-20", "15:42"), 0, False)
        for _ in range(6):                                    # (the turns of what is due at 15:42, until none is)
            self.lane.run()
            if self.lane._next_look > self.clock():
                break
        self.assertGreater(self.lane._next_look, self.clock(), "nothing more is due at 15:42")
        self.assertEqual(self.lane._next_look, (TH.et("2026-10-20", "15:47") - H.HOLD_LEAD).timestamp(),
                         "the next look is the lead's start (15:44:30 ET), before the record pass due at 15:44:50")
        self.assertEqual(self.receipts("decide-close:2026-10-20"), [])
        with mock.patch.object(R, "five_programs", return_value=[]):
            self.at(TH.et("2026-10-20", "15:45"))
            self.lane._next_look = float("-inf")
            self.lane.run()
        self.assertEqual(self.receipts("decide-close:2026-10-20"), [], "no PREREG-EVL-5 rows: the turn ends as before")

    def test_a_clock_that_does_not_move_ends_the_held_turn(self):
        self.opened()
        self.at(TH.et("2026-10-20", "15:46"))
        self.mark_recorded()
        self.lane._sleep = self.mono.advance                  # (the House's clock stays where it is)
        self.lane.run()
        self.assertEqual(self.receipts("decide-close:2026-10-20"), [])
        self.assertIsNone(self.lane.health()["running"])

    # -- the money re-review (wf_03d60ddf-1c3): a lead task that returns late, and no other decision in the lead -------
    def overrun(self, returns_at: dt.datetime) -> list[str]:
        """The record pass's last network read returns at `returns_at`, after its bound (the gateway's timeout is 45 s;
        a bounded task checks its bound only before each read): the lane's clock moves there inside the task."""
        started: list[str] = []

        def record(ctx, deadline):
            started.append(S.iso(self.lane.now()))
            self.assertLess(deadline, self.mono() + 20.0, "the record pass is bounded to end before the decision")
            self.clock.set(returns_at)
            return {}
        self.lane._record = record
        return started

    def decisions(self) -> list[tuple[str, str, str]]:
        """(kind, day, started at) of every decision the lane started, in order."""
        out: list[tuple[str, str, str]] = []
        decide = self.lane._decide

        def wrapped(ctx, kind, day, live):
            out.append((kind, day.isoformat(), S.iso(self.lane.now())))
            return decide(ctx, kind, day, live)
        self.lane._decide = wrapped
        return out

    def test_a_lead_task_that_returns_after_the_decisions_time_still_starts_it_in_the_same_turn(self):
        """The re-review's case (a): a record pass due at 15:46:40 whose last read returns at 15:47:05 ET. Before the
        fix the turn ended there (`_close_hold` is None once the time has come) and the decision waited for the next
        publish; now it starts at 15:47:05, in the same turn."""
        self.opened()
        self.at(TH.et("2026-10-20", "15:44") + dt.timedelta(seconds=40))
        self.mark_recorded()                                   # (the record pass is due again at 15:46:40)
        started = self.overrun(TH.et("2026-10-20", "15:47") + dt.timedelta(seconds=5))
        made = self.decisions()
        self.lane.run()
        self.assertEqual(started, ["2026-10-20T19:46:40Z"])
        [close] = self.receipts("decide-close:2026-10-20")
        self.assertEqual(close["started_at"], "2026-10-20T19:47:05Z", "at once, never at the next publish")
        self.assertEqual(close["status"], "ok")
        self.assertEqual(made, [("close", "2026-10-20", "2026-10-20T19:47:05Z")])
        self.assertEqual([n for n, _ in self.ran][-2:], ["record", "decide-close"])
        self.assertIsNone(self.lane.health()["running"])
        self.assertFalse(self.lane._close_owed(self.lane_store(), self.clock_dt()), "made: owed no more")

    def lane_store(self) -> S.Store:
        st = self.store()
        self.addCleanup(st.close)
        return st

    def test_a_turn_that_begins_after_the_time_with_a_task_that_ends_late_runs_the_decision(self):
        """A task started BEFORE the lead (a re-decision with the whole DECIDE_BUDGET, at 15:44:29 ET) that returns at
        15:47:10 ET: the turn does not end while the live decision is owed."""
        self.opened()
        self.at(TH.et("2026-10-20", "15:44") + dt.timedelta(seconds=29))
        self.mark_recorded()
        self.lane._looks[("close", dt.date(2026, 10, 20))] = H.VerdictLook(self.clock_dt(), 0, False)
        self.lane._redecide.add(("close", dt.date(2026, 10, 19)))
        made = self.decisions()
        decide = self.lane._decide

        def slow(ctx, kind, day, live):
            out = decide(ctx, kind, day, live)
            if day == dt.date(2026, 10, 19):
                self.clock.set(TH.et("2026-10-20", "15:47") + dt.timedelta(seconds=10))
            return out
        self.lane._decide = slow
        self.lane.run()
        self.assertEqual(made, [("close", "2026-10-19", "2026-10-20T19:44:29Z"),
                                ("close", "2026-10-20", "2026-10-20T19:47:10Z")])
        [close] = self.receipts("decide-close:2026-10-20")
        self.assertEqual(close["status"], "ok")

    def test_a_redecision_queued_inside_the_lead_waits_for_the_live_decision(self):
        """The re-review's case (b): the hourly re-decision of Monday's close queued at 15:46:30 ET would run with the
        whole DECIDE_BUDGET (150 s, `_deadline` bounds no decision) and end at 15:47:11. Inside the lead no decision
        but the live one starts: the live close decision starts at 15:47:00 ET, then the re-decision."""
        self.opened()
        self.at(TH.et("2026-10-20", "15:46") + dt.timedelta(seconds=30))
        self.mark_recorded()
        self.lane._looks[("close", dt.date(2026, 10, 20))] = H.VerdictLook(self.clock_dt(), 0, False)
        self.lane._redecide.add(("close", dt.date(2026, 10, 19)))
        made = self.decisions()
        decide = self.lane._decide

        def slow(ctx, kind, day, live):
            out = decide(ctx, kind, day, live)
            if day == dt.date(2026, 10, 19):
                self.clock.advance(41)
            return out
        self.lane._decide = slow
        self.lane.run()
        self.assertEqual(made[0], ("close", "2026-10-20", "2026-10-20T19:47:00Z"), "the live decision first")
        [close] = self.receipts("decide-close:2026-10-20")
        self.assertEqual(close["started_at"], "2026-10-20T19:47:00Z")
        if len(made) == 1:                                     # (the re-decision is the next turn's)
            self.assertEqual(self.lane._next_look, self.clock(), "due at once after the live decision")
            self.lane.run()
        self.assertEqual(made[1][:2], ("close", "2026-10-19"), "the re-decision after it, whole")
        self.assertGreaterEqual(made[1][2], "2026-10-20T19:47:00Z")
        self.assertNotIn(("close", dt.date(2026, 10, 19)), self.lane._redecide)

    def test_inside_the_lead_no_other_decision_is_due_whatever_its_rank(self):
        """A missed decision (rank 1), a cut one (rank 2), the hourly re-decision and the backfill kinds (rank 3) wait
        from HOLD_LEAD before the live close decision until a run of it has finished `ok` or `pending` (release 1019h:
        a run that has only started, or that failed, keeps them waiting); before the lead, once it is made, or with no
        PREREG-EVL-5 programs, they are due as before."""
        self.opened()
        monday = dt.date(2026, 10, 19)
        with self.store() as st:
            st.db.execute("DELETE FROM receipts WHERE job='decide-close:2026-10-19'")     # (missed: rank 1)
        lead_at = TH.et("2026-10-20", "15:47") - H.HOLD_LEAD
        cases = {
            "missed": lambda: None,
            "cut": lambda: self.lane._cut.add(("close", monday)),
            "five": lambda: self.lane._five.add(monday),
        }
        for name, setup in cases.items():
            with self.subTest(name), self.store() as st:
                self.lane._cut.clear()
                self.lane._five.clear()
                setup()
                if name != "missed":
                    rid = st.start_receipt("decide-close:2026-10-19", now=TH.et("2026-10-19", "15:47"))
                    st.finish_receipt(rid, "cut" if name == "cut" else "ok", {}, now=TH.et("2026-10-19", "15:48"))
                if name == "five":
                    self.lane._redecide.add((H.FIVE_KIND, monday))
                for when, due in ((lead_at - dt.timedelta(seconds=1), True), (lead_at, False),
                                  (TH.et("2026-10-20", "15:46") + dt.timedelta(seconds=59), False)):
                    got = self.lane._due_decision(st, when, self.lane._decide_receipts(st, when), [])
                    self.assertEqual(got is not None, due, (name, when))
                with mock.patch.object(R, "five_programs", return_value=[]):
                    self.assertIsNotNone(self.lane._due_decision(st, lead_at, self.lane._decide_receipts(st, lead_at),
                                                                 []), "no PREREG-EVL-5 rows: no lead")
                at = TH.et("2026-10-20", "15:47")
                got = self.lane._due_decision(st, at, self.lane._decide_receipts(st, at), [])
                self.assertEqual(got[2:4], ("close", dt.date(2026, 10, 20)), "at its time: the live one, rank 0")
                # (release 1019h, the review of release 1019g: the lead ends when a run of the live one has FINISHED
                # `ok` or `pending`, never at a run that has only started or that failed: the others wait through the
                # failed run's retry, which is the live one's, rank 0)
                tue = ("close", dt.date(2026, 10, 20))
                rid = st.start_receipt("decide-close:2026-10-20", now=at)
                got = self.lane._due_decision(st, at, self.lane._decide_receipts(st, at), [])
                self.assertTrue(got is None or got[2:4] == tue, "running: the others still wait")
                st.finish_receipt(rid, "failed", {"why": "OSError: invented"}, now=at + dt.timedelta(seconds=5))
                for after, live in ((30, False), (60, True)):
                    when = at + dt.timedelta(seconds=after)
                    got = self.lane._due_decision(st, when, self.lane._decide_receipts(st, when), [])
                    self.assertEqual(None if got is None else got[2:4], tue if live else None, (name, after))
                rid = st.start_receipt("decide-close:2026-10-20", now=at + dt.timedelta(seconds=60))
                st.finish_receipt(rid, "ok", {}, now=at + dt.timedelta(seconds=65))
                when = at + dt.timedelta(seconds=70)
                got = self.lane._due_decision(st, when, self.lane._decide_receipts(st, when), [])
                self.assertIsNotNone(got, "the live one is made: the others are due again")
                self.assertEqual(got[3], monday)
                st.db.execute("DELETE FROM receipts WHERE job='decide-close:2026-10-20'")
                st.db.execute("DELETE FROM receipts WHERE job IN ('decide-close:2026-10-19', ?)",
                              (f"{H.FIVE_KIND}:2026-10-19",))

    def test_a_decision_started_before_the_lead_is_due_to_end_by_the_decisions_time(self):
        self.assertGreaterEqual(H.HOLD_LEAD.total_seconds(), H.DECIDE_BUDGET)
        self.assertLess(H.HOLD_LEAD, H.LIVE_WITHIN)


class TheHeldTurnInTheWeek(unittest.TestCase):
    """The money re-review's fix in the invented week (league/tests/evl5_world.py): Tuesday's and Wednesday's live close
    decisions made by the House's lane in a held turn that begins at 15:44:40 ET with the hourly re-decision of
    Monday's close queued (it waits for the live one) and a record pass whose last read returns at 15:47:05 ET (the
    decision starts then, in the same turn), against the same decisions made directly at 15:47:00 ET with Monday's
    re-decision after them: every program's intents (PREREG-EVL-1 to -4, the births and PREREG-EVL-5's), the earlier
    programs' real-money picks and PREREG-EVL-5's real-money gate (`book.part_hold`) are the same."""

    def world(self) -> W.World:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.addCleanup(P.load_births, None)
        world = W.World(Path(tmp.name) / "lane")
        self.addCleanup(world.close)
        world.births()
        W.evl4_rows(world)
        W.evl5_rows(world)
        for day in W.W4.weekdays(dt.date(2026, 10, 19), PRIOR - dt.timedelta(days=1)):   # (decided before the week)
            for kind, hh, mm in (("open", 9, 15), ("close", 15, 47)):
                rid = world.st.start_receipt(f"decide-{kind}:{day.isoformat()}", now=et(day, hh, mm))
                world.st.finish_receipt(rid, "ok", {}, now=et(day, hh, mm))
        world.at(et(PRIOR, 7, 31)).decide("open", PRIOR, ask_only=True)       # (and Monday's open, as the House does)
        world.at(et(PRIOR, 9, 15, 30)).decide("open", PRIOR)
        return world

    @staticmethod
    def direct(w: W.World, day: dt.date) -> None:
        w.at(et(day, 15, 47)).decide("close", day)
        w.at(et(day, 15, 47, 10)).decide("close", PRIOR, live=False)    # (the hourly re-decision, after it)

    def by_the_lane(self, w: W.World, day: dt.date) -> None:
        from ltcm.tests.fakes import Clock

        start = et(day, 15, 44, 40)
        clock, mono = Clock(S.iso(start)), Mono()

        def sleep(seconds: float) -> None:
            mono.advance(seconds)
            clock.advance(seconds)
        lane = H.EventLane(FakeHouse(clock), w.root, gateway=w.gw, sec=W.sec, monotonic=mono, sleep=sleep)
        lane._redecide_next = dt.datetime(2100, 1, 1, tzinfo=UTC)
        lane._open_checked = dt.datetime(2100, 1, 1, tzinfo=UTC)
        w.st.set_meta("evl:lane:sessions_at", S.iso(start))
        rid = w.st.start_receipt("record", now=start)
        w.st.finish_receipt(rid, "ok", {}, now=start)
        lane._redecide.add(("close", PRIOR))                  # (queued inside the lead)

        def record(ctx, deadline):
            rid = ctx.store.start_receipt("record", now=ctx.now())
            if ctx.now() < et(day, 15, 47):
                clock.set(et(day, 15, 47, 5))                  # (its last read returns after its bound)
            ctx.store.finish_receipt(rid, "ok", {}, now=ctx.now())
            return {}
        lane._record = record
        made: list[tuple[str, str, str]] = []
        decide = lane._decide

        def noted(ctx, kind, d, live):
            made.append((kind, d.isoformat(), S.iso(lane.now())))
            return decide(ctx, kind, d, live)
        lane._decide = noted
        with mock.patch.object(lane, "_nightly", return_value=None), \
                mock.patch.object(lane, "_backfill_due", return_value=None), \
                mock.patch.object(lane, "_tickers_due", return_value=False):
            for _ in range(4):
                lane.run()
                if ("close", PRIOR.isoformat()) in [m[:2] for m in made]:
                    break
                clock.advance(60)                              # (the next publish)
        self.assertEqual(made[0], ("close", day.isoformat(), S.iso(et(day, 15, 47, 5))), made)
        self.assertEqual(made[1][:2], ("close", PRIOR.isoformat()), "the re-decision after the live one")
        [live] = [r for r in w.st.db.execute("SELECT * FROM receipts WHERE job=? ORDER BY id",
                                              (f"decide-close:{day.isoformat()}",))]
        self.assertEqual((live["started_at"], live["status"]), (S.iso(et(day, 15, 47, 5)), "ok"))
        self.assertLess(live["finished_at"], S.iso(et(day, 15, 49)), "finished before the book's cut-off")
        w.at(lane.now())

    def test_every_programs_close_decisions_and_the_real_money_are_the_same(self):
        a, b = self.world(), self.world()
        W.decide_week(a, close=self.direct)
        W.decide_week(b, close=self.by_the_lane)
        rows = a.intents(earlier)
        self.assertGreater(len(rows), 60)
        self.assertEqual(b.intents(earlier), rows, "PREREG-EVL-1 to -4 and the births")
        self.assertEqual(b.intents(lambda p, v: p in ALL5), a.intents(lambda p, v: p in ALL5))
        self.assertTrue(b.intents(lambda p, v: p in ALL5))
        picks = W.picks(a, lambda p: p.prereg != 5)
        self.assertTrue(any(picks.values()))
        self.assertEqual(W.picks(b, lambda p: p.prereg != 5), picks)
        self.assertEqual(W.picks(b, lambda p: p.prereg == 5), W.picks(a, lambda p: p.prereg == 5))
        held = [EB.Lane(w.root / S.DB_NAME) for w in (a, b)]
        try:
            for day in (D, NEXT):
                for prog in R.five_programs():
                    if prog.seatable:
                        self.assertIsNone(EB.part_hold(held[1], prog.id, prog.version, day), (prog.id, day))
                        self.assertEqual(EB.part_hold(held[1], prog.id, prog.version, day),
                                         EB.part_hold(held[0], prog.id, prog.version, day))
        finally:
            for lane in held:
                lane.close()


# ----------------------------------------------------------------------------------------------- the record before
class TheRecordBeforeTheRelease(unittest.TestCase):
    """Section 3: every close decision from the registration time to the first one the House release carrying this
    file's code makes is decided for this file's programs BY THEMSELVES (`decide-close-evl5:<day>`), once each, oldest
    first, as a backfill; no earlier row is decided again and no intent of an earlier row is written. Release 1019e
    decides every session from Oct 19 through Mon Nov 2's close; this release then first runs at 17:00 ET Nov 2."""

    LATE = dt.date(2026, 11, 2)

    def world(self) -> W.World:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.addCleanup(P.load_births, None)
        world = W.World(Path(tmp.name) / "lane")
        self.addCleanup(world.close)
        return world

    def by_1019e(self, world: W.World) -> None:
        from league.events import __main__ as CLI

        world.births()
        W.evl4_rows(world)
        W.evl5_rows(world)
        with without_evl5():
            world.at(et(dt.date(2026, 10, 22), 7, 0))
            CLI.catchup(world.ctx)
            W.decide_week(world)
            world.at(et(self.LATE, 17, 0))
            CLI.catchup(world.ctx)
        for day in W.W4.weekdays(dt.date(2026, 10, 19), self.LATE):
            world.st.set_meta(f"evl:backfill:{day.isoformat()}", "done")

    def test_the_closes_before_the_release_are_decided_by_themselves_once_oldest_first(self):
        from league.events import __main__ as CLI

        a, b = self.world(), self.world()
        self.by_1019e(a)
        self.by_1019e(b)
        gap = [dt.date(2026, 10, d) for d in (22, 23, 26, 27, 28)]
        self.assertEqual(SC.made_without(b.st, self.LATE, prereg=5), dict.fromkeys(gap + [dt.date(2026, 10, 29),
                                                                                          dt.date(2026, 10, 30),
                                                                                          self.LATE], False))
        # THE HOUSE: the closes the hourly re-decision no longer reaches get their rows' own decision, oldest first
        lane = H.EventLane(FakeHouse(Clock(S.iso(et(self.LATE, 17, 0)))), b.root, gateway=b.gw, sec=W.sec,
                           monotonic=Mono())
        now = et(self.LATE, 17, 0)
        lane._refill_redecide(b.st, now, self.LATE)
        self.assertEqual(sorted(lane._five), gap)
        best = lane._due_decision(b.st, now, lane._decide_receipts(b.st, now), [])
        self.assertEqual(best[2:], (H.FIVE_KIND, gap[0], False), "oldest first, a backfill")
        jobs = ("SELECT job, status, summary FROM receipts WHERE job LIKE 'decide-open:%' OR job LIKE 'decide-close:%' "
                "ORDER BY id")
        before = [tuple(r) for r in b.st.db.execute(jobs)]
        out = CLI.catchup(b.ctx)                                          # (the CLI's catchup does the same)
        self.assertEqual([k for k in out if k.startswith(SC.FIVE_KIND)][:5], [f"{SC.FIVE_KIND}:{d}" for d in gap])
        after = [tuple(r) for r in b.st.db.execute(jobs)]
        self.assertEqual(after[:len(before)], before, "no earlier row's receipt is touched")
        with without_evl5():
            CLI.catchup(a.ctx)
        self.assertEqual(a.intents(earlier), b.intents(earlier), "no earlier program changes")
        self.assertEqual(SC.made_without(b.st, self.LATE, prereg=5), {})
        self.assertEqual([k for k in CLI.catchup(b.ctx) if k.startswith(SC.FIVE_KIND)], [], "once")
        c = self.world()
        W.the_week(c)
        taken = lambda w: {(r[0], r[3], r[6]) for r in w.intents(lambda p, v: p in ALL5)   # noqa: E731
                           if not str(r[12]).startswith("skipped")}
        self.assertEqual(taken(b), taken(c), "the same events as deciding them live")


# ----------------------------------------------------------------------------------------------------------- the proof
class TheProof(unittest.TestCase):
    """NO EARLIER PROGRAM CHANGES: the synthetic week (league/tests/evl5_world.py: every family of PREREG-EVL-1, -2 and
    -4, two registered births and PREREG-EVL-5's events on one store, decided as the House decides, with its pre-passes,
    late-stored rows and the re-decisions) gives every earlier program the same shadow intents and the same real-money
    picks with PREREG-EVL-5's rows and without them (the same week decided by release 1019e's own code gives them too:
    evl5_world.py's script)."""

    def week(self, *, evl5: bool) -> tuple[list[tuple], dict, W.World]:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.addCleanup(P.load_births, None)
        world = W.World(Path(tmp.name) / "lane")
        self.addCleanup(world.close)
        world.births()
        W.evl4_rows(world)
        W.evl5_rows(world)
        if evl5:
            W.decide_week(world)
        else:
            with without_evl5():
                W.decide_week(world)
            self.assertEqual(world.intents(lambda p, v: p in ALL5), [], "no row of PREREG-EVL-5 decided")
        return world.intents(earlier), W.picks(world, lambda p: p.prereg != 5), world

    def test_every_earlier_programs_intents_and_picks_are_the_same(self):
        with_rows, with_picks, world = self.week(evl5=True)
        without_rows, without_picks, _ = self.week(evl5=False)
        self.assertGreater(len(without_rows), 60)
        programs = {r[0] for r in without_rows}
        self.assertTrue(set(NINE) | set(FOUR) <= programs | {"EVL-INS-BUY-O1"}, programs)
        self.assertTrue({"EVL-B-ERNREACT-DIP", "EVL-B-8K-502"} <= programs, "the births decide in the week")
        self.assertEqual(with_rows, without_rows)
        self.assertEqual(with_picks, without_picks)
        self.assertTrue(any(with_picks.values()))
        mine = {(r[0], r[3], r[6], r[12]) for r in world.intents(lambda p, v: p in ALL5)}
        self.assertEqual(mine, {
            ("EVL-ERN-DROP-ON", "KKK", D.isoformat(), "planned"), ("EVL-ERN-DROP-ON", "NNN", D.isoformat(), "planned"),
            ("EVL-ERN-UNDER-ON", "LLL", D.isoformat(), "planned"), ("EVL-ERN-UNDER-ON", "MMM", D.isoformat(), "planned"),
            (CONTROL5, "LLL", D.isoformat(), "planned"), (CONTROL5, "MMM", D.isoformat(), "planned"),
            (CONTROL5, "QQQ", D.isoformat(), "planned"),
            ("EVL-NEWS-NIGHT2-ON", "SSS", D.isoformat(), "planned"), ("EVL-NEWS-NIGHT2-ON", "TTT", D.isoformat(), "planned"),
            ("EVL-NEWS-NIGHT2-ON", "YYY", D.isoformat(), "planned"),
            ("EVL-NEWS-NIGHT2-ON", "AAC", D.isoformat(), "skipped:taken"),
            ("EVL-NEWS-NIGHT2-ON", "AAC", NEXT.isoformat(), "planned"),
            ("EVL-NEWS-NIGHT2-ON", "ZZZ", NEXT.isoformat(), "planned")},
            "OOO (b), PPP (a), RRR (c) taken by earlier rows; QQQ's TEXT has no verdict; UUU under 1.02, AAB no trade; "
            "VVV (i), WWW (ii), XXX (iii), ZZZ (i, its edit within 10 minutes) on Tuesday; AAC by a late article")


# ----------------------------------------------------------------------------------------------------------- the docs
class TheDocs(unittest.TestCase):
    def test_the_frozen_file_is_the_tags_byte_for_byte(self):
        """docs/prereg/PREREG-EVL-5.md and docs/prereg/evl-5/ are the tag's (A92: sha256 48b19fde...)."""
        shas = {"docs/prereg/PREREG-EVL-5.md": "48b19fdeb0059cb9ee4c48784cce1de2d543e692fd2df47882c3fef764aabdf4",
                "docs/prereg/evl-5/calib_evl5.py": "b33b2738d09821b3d883271e180c72f61b13f22a8d30239bb519dfdd9d7f73ce",
                "docs/prereg/evl-5/calib_evl5.out": "6efa3e2691dad2a7f3a454c1db12f451be2a331296a8d3ad1532c04c5eee07c6"}
        for path, sha in shas.items():
            self.assertEqual(hashlib.sha256((REPO / path).read_bytes()).hexdigest(), sha, path)
        text = (REPO / "docs" / "prereg" / "PREREG-EVL-5.md").read_text()
        for pid in ALL5:
            self.assertIn(pid, text)

    def test_the_wall_holds_the_frozen_files_and_the_lanes_modules(self):
        for path in ("docs/prereg/PREREG-EVL-5.md", "docs/prereg/evl-5/calib_evl5.py", "league/events/programs.py",
                     "league/events/run.py", "league/events/screen.py", "league/events/book.py",
                     "league/events/house.py"):
            self.assertTrue(ci.guard([path], None), path)
            for role in ci.ROLE_PATHS:
                self.assertTrue(ci.guard([path], role), (path, role))


# ----------------------------------------------------------------------------------------------------------- the report
class TheReport(WorldCase):
    def test_the_report_counts_the_funnels_the_failed_parts_and_the_room_effects(self):
        """Section 6: the report counts each row's funnel; section 1.3: the shadow's difference from real money, the
        closes whose part failed, and the two room effects (counted, never prevented)."""
        W.evl5_rows(self.w)
        self.close()
        self.w.article("n-aac-2", "AAC", knowable=et(D, 14, 0), stored=et(D, 16, 30))
        self.w.at(et(D, 16, 41)).decide("close", D, live=False)
        live = self.w.root.parent / RP.LIVE_DB
        db = sqlite3.connect(live)
        db.execute("CREATE TABLE eq_intents(iid INTEGER PRIMARY KEY, status TEXT, why TEXT)")
        db.execute("CREATE TABLE eq_event_intents(iid INTEGER PRIMARY KEY, program TEXT, side TEXT, band TEXT, day TEXT, "
                   "at TEXT)")
        rows = [(1, "EVL-ERN-DROP-ON", "buy", "learning", D, "close", "missed",
                 "not filled at the close auction (never sent: the event kind's day order count: 147 of 150 sent)"),
                (2, "EVL-NEWS-NIGHT2-ON", "sell", "learning", NEXT, "open", "done", "the lot is sold"),
                (3, "EVL-ERN-READ-O1", "buy", "learning", NEXT, "open", "refused",
                 "sizing: no whole share fits (cash): refused: the cash"),
                (4, "EVL-ERN-READ-O1", "buy", "probe", NEXT, "open", "refused",
                 "sizing: no whole share fits (cash): refused: the cash"),
                (5, "EVL-ERN-UNDER-ON", "buy", "learning", D, "close", "missed",
                 f"not filled at the close auction (never sent: {EB.PART_WAIT} of {D} to decide PREREG-EVL-5's rows)"),
                (6, "EVL-B-ERNREACT-DIP", "buy", "learning", D, "close", "missed",
                 f"not filled at the close auction (never sent: {L.HELD_ROOM} (1 {L.HELD_AHEAD}): skipped)"),
                (7, "EVL-ERN-REACT-C1", "buy", "learning", D, "close", "done", f"filled 2 shares at the close")]
        for iid, program, side, band, day, at_, status, why in rows:
            db.execute("INSERT INTO eq_intents VALUES(?, ?, ?)", (iid, status, why))
            db.execute("INSERT INTO eq_event_intents VALUES(?, ?, ?, ?, ?, ?)", (iid, program, side, band, day.isoformat(),
                                                                                 at_))
        db.commit()
        db.close()
        self.assertEqual(RP.room_effects(self.st, D), {"line_refused": 1, "exits_held": 0, "open_lost": 0,
                                                       "held_unsent": 1, "room_waited": 1})
        self.assertEqual(RP.room_effects(self.st, NEXT), {"line_refused": 0, "exits_held": 1, "open_lost": 1,
                                                          "held_unsent": 0, "room_waited": 0})
        rep = RP.build(self.st, D, now=et(D, 21, 5))
        self.assertEqual(rep["evl5"]["funnel"]["survivors"], 5)
        self.assertEqual(rep["evl5"]["funnel"]["gap_pass"], 3)
        self.assertEqual(rep["evl5"]["failed"], [])
        night2 = [p for p in rep["programs"] if p["program"] == "EVL-NEWS-NIGHT2-ON"][0]
        self.assertEqual(night2["late_rows"]["excluded_late"], 1, "AAC: a row stored later put it in NO NEW INFORMATION")
        self.assertEqual(night2["late_rows"]["stored_late"], 0)
        text = RP.render(rep)
        self.assertIn("PREREG-EVL-5: ERN(D)", text)
        self.assertIn("room: line refused 1", text)
        self.assertIn("unsent waiting for the close decision 1 (later buys 1)", text)
        rid = self.st.start_receipt(f"decide-close:{D}", now=et(D, 17, 0))
        self.st.finish_receipt(rid, "ok", {"evl5_error": "RuntimeError: invented"}, now=et(D, 17, 0))
        self.assertEqual(RP.evl5(self.st, D)["failed"], [{"day": D.isoformat(), "error": "RuntimeError: invented",
                                                         "decided_since": False}])
        kept = RP.kept_out(self.st, D)
        self.assertIsInstance(kept, dict)


# ----------------------------------------------------------------------------------------------------------- the births
class TheBirths(WorldCase):
    def test_a_births_night_runs_with_these_rows_and_reads_the_lanes_sum(self):
        """R3's validator reads the lane's own SEATING sum: 1.5 used with these rows and no birth (section 3; A92), 1.7
        with the two invented births; their facts list these rows (counted, never their prices)."""
        from league.events import births as BI

        self.assertEqual(BI.budget_used_tenths(self.st), 15)
        self.assertEqual(BI.budget(self.st)["left"], 1.5)
        self.w.births()
        self.assertEqual(BI.budget_used_tenths(self.st), 17)
        facts = BI.Facts(self.st, D).facts()
        listed = {p["id"]: p for p in facts["programs"]}
        for pid in ALL5:
            self.assertIn(pid, listed)
        out = BI.night(self.st, None, today=D, now=lambda: et(D, 21, 15), dry_run=True,
                       proposals=[{"spec": {"id": "EVL-B-NEWSDAY-X", "version": 1, "family": "news-day",
                                            "rule": {"score_min": 3}, "entry": "close", "exit": "open", "hold": 1,
                                            "rank": "score", "seatable": True}, "why": "invented"}])
        self.assertIn("counts", out)


# PREREG-EVL-7 (A125 pinned REGISTERED_AT_7): this module's tests are of mechanisms written before the learners
# registered and run on the registries without them (league/tests/evl7_fakes.py); the learners' own effects on these
# paths are league/tests/test_events_evl7.py's and test_events_evl7_fix.py's.
from league.tests.evl7_fakes import setUpModule, tearDownModule  # noqa: E402,F401

if __name__ == "__main__":
    unittest.main()
