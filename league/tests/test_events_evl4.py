"""PREREG-EVL-4 (frozen; tag `prereg-evl-4`, registered 2026-10-19T16:01:05Z): three new seatable programs at
PREREG-EVL-3's learning band from birth, their version 1 the seating version, and two controls. Held here, on invented
rows only (league/tests/evl4_world.py):

- the rows as frozen, their own registration time (never PREREG-EVL-3's), the seating gate, the judge's registries, the
  expected false passes (1.2 of the lane's stated 3.0), PREREG-EVL-3's screen run on them (event-counted looks, alpha
  0.018, the control read at version 1, the seed strings `{id}|v1|look{k}`, promotion and retirement);
- the windows (the close window [P's close decision, D's close decision), PM(D) after P's close and by 09:00 ET of D,
  DAY(D) after 09:00 ET and by T29), the knowable times and the registration gate;
- EXCLUDED (ERN(D) or DAY(D)) skipping an issuer in all five rows even when the row that excludes it predates every
  registration time, and EVL-NEWSPM-READ-ON's F8K(D) skip;
- each rule: EVL-8K-REACT-ON's 1.04 (1.0399 not, a missing price not), EVL-8K-READ-ON's score 2 (1 not, a TEXT under 200
  characters has no verdict), the one verdict it shares with EVL-8K-READ-O1, EVL-NEWSPM-READ-ON's highest score then the
  earliest, which asks no verdict of its own and waits for EVL-NEWS-READ-O1's;
- a re-decision marking an unsettled intent `skipped:excluded` when a row stored later excludes its issuer;
- real money: the three seat at learning after the nine, the controls never; the rows stored before the decision
  time alone (EXCLUDED read from them too); section 1.3's guard (no buy for a filing knowable from 09:00 ET of D whose
  verdict is `ok` with score >= 2, or not yet answered);
- the House asking EVL-NEWS-READ-O1's verdicts when only they are missing, and a wait nothing can ask backing off;
- THE PROOF: every PREREG-EVL-1/2/3 program's intents and real-money picks on a synthetic week are the same with and
  without PREREG-EVL-4's rows (the same week decided by release 1019b's own code gives them too: evl4_world.py)."""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest import mock

from league.equity import schedule as ES
from league.events import bands as BA
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
from league.tests import evl4_world as W
from league.tests import test_events_book as TB
from league.tests.test_events_house import LaneCase, et as house_et
from league.tests.test_events_screen import final_record

UTC = dt.timezone.utc
NEW = ("EVL-8K-REACT-ON", "EVL-8K-READ-ON", "EVL-NEWSPM-READ-ON")
CONTROLS4 = ("EVL-CTRL-8K-ON", "EVL-CTRL-NEWSPM-ON")
FOUR = NEW + CONTROLS4
NINE = ("EVL-ERN-READ-O1", "EVL-ERN-REACT-C1", "EVL-8K-READ-O1", "EVL-NEWS-READ-O1", "EVL-ERN-REACT-ON",
        "EVL-ERN-GUIDE-O1", "EVL-INS-BUY-O1", "EVL-NEWS-READ-ON", "EVL-NEWS-REACT-ON")
REGISTERED_4 = dt.datetime(2026, 10, 19, 16, 1, 5, tzinfo=UTC)
D, PRIOR, NEXT = W.D_DAY, W.P_DAY, W.N_DAY
et = W.et


def earlier(program: str, version: int) -> bool:
    return program not in FOUR


def without_evl4():
    """THE CODE WITHOUT PREREG-EVL-4's rows: the program table without them, and the close decision without their own
    reads (`run._rows_4`: the earlier rows' eligibility and nothing more), as release 1019b decided."""
    rows = tuple(p for p in P.PROGRAMS if p.prereg != 4)

    def no_rows(ctx, day, window, by_ticker, elig, *, live):
        return {"rows": {f: [] for f in P.CLOSE_FAMILIES_4}, "elig": dict(elig), "excluded": set(), "filed": set(),
                "counts": {}}
    return mock.patch.object(P, "PROGRAMS", rows), mock.patch.object(R, "_rows_4", no_rows)


class WorldCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.w = W.World(Path(self.tmp.name) / "lane")
        self.addCleanup(self.w.close)
        self.st = self.w.st

    def intents(self, program: str, day: dt.date | None = None, version: int | None = None) -> list[dict]:
        sql, args = "SELECT * FROM intents WHERE program=?", [program]
        if day is not None:
            sql += " AND entry_day=?"
            args.append(day.isoformat())
        if version is not None:
            sql += " AND version=?"
            args.append(version)
        return [dict(r) for r in self.st.db.execute(sql + " ORDER BY event", args)]

    def taken(self, program: str, day: dt.date | None = None, version: int = 1) -> list[str]:
        """The symbols version `version` of `program` took (intents not skipped), sorted."""
        return sorted(r["symbol"] for r in self.intents(program, day, version)
                      if not str(r["status"]).startswith("skipped"))

    def verdict(self, event: str, score: int | None, answered: dt.datetime, *, news: bool = False,
                status: str = "ok") -> None:
        prompt = V.PROMPTS["news" if news else "doc"]
        self.st.db.execute("INSERT INTO verdicts(event, prompt_sha, model, request_id, asked_at, answered_at, status, "
                           "score, guidance, answer, usd) VALUES(?, ?, ?, 'r', ?, ?, ?, ?, 'none', '{}', 0.001)",
                           (event, prompt.sha, V.MODEL, S.iso(answered), S.iso(answered), status, score))

    def open_then_close(self, day: dt.date) -> dict:
        """The House's day: the open decision (its verdicts asked ahead), then the live close decision."""
        self.w.at(et(day, 7, 31)).decide("open", day, ask_only=True)
        self.w.at(et(day, 9, 15, 30)).decide("open", day)
        self.w.at(et(day, 15, 17)).decide("close", day, ask_only=True)
        return self.w.at(et(day, 15, 47)).decide("close", day)


# ----------------------------------------------------------------------------------------------------- the rows
class TheRows(unittest.TestCase):
    def test_the_five_rows_as_frozen(self):
        self.assertEqual(P.REGISTERED_AT_4, "2026-10-19T16:01:05Z")
        rows = [p for p in P.PROGRAMS if p.prereg == 4]
        self.assertEqual(tuple(p.id for p in rows), FOUR, "section 1.2's order, then section 4's controls")
        self.assertEqual(P.PROGRAMS[-5:], tuple(rows), "after every earlier row and PREREG-EVL-3's version 2 copies")
        self.assertEqual({p.id: (p.version, p.seatable, p.family, p.entry_at, p.hold, p.reads, p.exit_at, p.rule)
                          for p in rows},
                         {"EVL-8K-REACT-ON": (1, True, "8k-react", "close", 1, False, "open", "none"),
                          "EVL-8K-READ-ON": (1, True, "8k-day", "close", 1, True, "open", "min2"),
                          "EVL-NEWSPM-READ-ON": (1, True, "news-pm", "close", 1, True, "open", "min2"),
                          "EVL-CTRL-8K-ON": (1, False, "8k-day", "close", 1, False, "open", "none"),
                          "EVL-CTRL-NEWSPM-ON": (1, False, "news-pm", "close", 1, False, "open", "none")})
        self.assertEqual([p for p in P.PROGRAMS if p.id in FOUR and p.version != 1], [], "no version 2 of a new id")
        for p in rows:
            self.assertEqual(p.can_seat, p.id in NEW, p.id)
            self.assertEqual(p.registered_at, REGISTERED_4, p.id)
            self.assertIs(P.BY_ID[p.id], p)
        self.assertEqual([(p.id, p.version) for p in P.SEATING],
                         [(i, 2) for i in NINE] + [(i, 1) for i in NEW], "the nine version 2 rows, then the three")
        self.assertFalse([p for p in P.PROGRAMS if p.prereg in (1, 2) and p.can_seat],
                         "version 1 of PREREG-EVL-1's and -2's programs never seats")

    def test_each_file_counts_from_its_own_registration_time(self):
        four = P.BY_KEY[("EVL-8K-READ-ON", 1)]
        with mock.patch.object(P, "REGISTERED_AT_3", "2026-12-01T00:00:00Z"), \
                mock.patch.object(P, "REGISTERED_AT_2", "2026-12-01T00:00:00Z"):
            self.assertEqual(four.registered_at, REGISTERED_4, "PREREG-EVL-4 never reads PREREG-EVL-3's time")
            self.assertEqual(P.BY_KEY[("EVL-ERN-READ-O1", 2)].registered_at,
                             dt.datetime(2026, 12, 1, tzinfo=UTC), "PREREG-EVL-3's rows still read theirs")
        with mock.patch.object(P, "REGISTERED_AT_4", None), self.assertRaises(RuntimeError):
            four.registered_at
        with self.assertRaises(ValueError):
            dataclasses.replace(four, prereg=5).registered_at
        self.assertEqual(P.BY_KEY[("EVL-NEWS-READ-ON", 1)].registered_at, S.parse_iso(P.REGISTERED_AT_2))
        self.assertEqual(P.BY_KEY[("EVL-NEWS-READ-ON", 2)].registered_at, S.parse_iso(P.REGISTERED_AT_3))
        self.assertEqual(P.BY_KEY[("EVL-ERN-READ-O1", 1)].registered_at, P.registered())

    def test_the_limit_at_entry_and_the_exit_at_the_next_open(self):
        uni = {"prev_close": 10.0}
        for pid in FOUR:
            self.assertTrue(SCORE._above_limit({"program": pid, "version": 1}, uni, 12.51), pid)
            self.assertFalse(SCORE._above_limit({"program": pid, "version": 1}, uni, 12.50), pid)
        with tempfile.TemporaryDirectory() as tmp:
            w = W.World(Path(tmp) / "lane")
            try:
                cand = P.Candidate("8k:x", W.CIK["CCC"], "CCC", et(D, 11, 10), 1.05, None, {})
                for pid in FOUR:
                    P.write_intents(w.st, P.BY_ID[pid], D, [cand], decided_at=et(D, 15, 46))
                rows = {(r["program"], r["entry_at"], r["exit_day"], r["exit_at"]) for r in w.st.db.execute(
                    "SELECT * FROM intents")}
                self.assertEqual(rows, {(pid, "close", NEXT.isoformat(), "open") for pid in FOUR})
                self.assertEqual(EB.exit_plan(P.BY_ID["EVL-8K-REACT-ON"], D), (NEXT.isoformat(), "open"))
            finally:
                w.close()


# ----------------------------------------------------------------------------------------------------- the judge
class TheJudge(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.st = S.Store(self.tmp.name)
        self.addCleanup(self.st.close)
        C.refresh(self.st, W.Gateway(), dt.date(2026, 10, 1), dt.date(2027, 3, 31))
        self.days = [s.day for s in C.sessions(self.st, dt.date(2026, 10, 20), dt.date(2027, 3, 31))]

    def test_the_registries_and_the_expected_false_passes(self):
        self.assertEqual(SC.SEATABLE[-3:], NEW)
        self.assertEqual(SC.RECORDS[-2:], CONTROLS4)
        self.assertEqual((SC.CONTROLS["EVL-8K-READ-ON"], SC.CONTROLS["EVL-NEWSPM-READ-ON"]), CONTROLS4)
        self.assertNotIn("EVL-8K-REACT-ON", SC.CONTROLS, "no control condition for the REACT row (section 4)")
        self.assertEqual({SC.HOLDS[p] for p in FOUR}, {1})
        self.assertEqual([SC._seating(p, 1) for p in FOUR], [True, True, True, False, False])
        self.assertEqual(SC.expected_false_passes(self.st), {"versions": 12, "expected": 1.2, "budget": 3.0, "left": 1.8})

    def _settle(self, program: str, per_day: int, days: list[dt.date], a: float, start: int = 0) -> int:
        """Synthetic settled close-to-next-open events of (program, version 1): `per_day` a session, each its own
        issuer, abnormal return and after-cost return `a`."""
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
        days = self.days[:8]
        self._settle("EVL-8K-READ-ON", 10, days, 0.01)                 # every block +1%: a pass at 80 events
        self._settle("EVL-CTRL-8K-ON", 10, days, 0.0, start=10_000)    # its control, at version 1
        self._settle("EVL-8K-REACT-ON", 10, days, -0.01)               # every block -1%: retired
        self._settle("EVL-CTRL-NEWSPM-ON", 10, days, 0.05)             # a control: never screened, never seated
        # (a close-to-next-open block of the 8th session settles at the 9th: 8 blocks are covered at days[8], a close
        # final once three later sessions have had their open decision)
        now = final_record(self.st, self.days[12])
        out = SC.run(self.st, self.days[12], draws=999, now=now)
        by = {(w["program"], w["version"], w["k"]): w for w in out["written"]}
        self.assertEqual(sorted(by), [("EVL-8K-REACT-ON", 1, 1), ("EVL-8K-READ-ON", 1, 1)])
        win = by[("EVL-8K-READ-ON", 1, 1)]
        self.assertEqual((win["held"], win["passed"], win["alpha"], win["band"], win["merged"]),
                         (1, 1, 0.018, "probe", []), "60 events, 80 issuers, 8 blocks at the 9th session's close")
        self.assertEqual(SC.look_rows(self.st, "EVL-8K-READ-ON", 1)[0]["at"],
                         S.iso(C.session(self.st, self.days[8]).close_at))
        self.assertEqual(by[("EVL-8K-REACT-ON", 1, 1)]["band"], "retired")
        detail = SC.look_detail(self.st, "EVL-8K-READ-ON", 1, 1)
        self.assertEqual(detail["skew"]["session"]["seed"], "EVL-8K-READ-ON|v1|look1")
        self.assertEqual(detail["control"]["program"], "EVL-CTRL-8K-ON")
        self.assertEqual(detail["control"]["mean_block"], 0.0, "the control read at version 1")
        self.assertLessEqual(detail["skew"]["session"]["alpha"], 0.018)
        self.assertEqual((detail["n"], detail["issuers"], detail["blocks"]), (80, 80, 8))
        bands = BA.bands(self.st)
        self.assertEqual((bands[("EVL-8K-READ-ON", 1)], bands[("EVL-8K-REACT-ON", 1)], bands[("EVL-NEWSPM-READ-ON", 1)]),
                         ("probe", "retired", "learning"))
        self.assertNotIn(("EVL-CTRL-NEWSPM-ON", 1), bands)
        with self.assertRaises(ValueError):
            BA.set_band(self.st, "EVL-CTRL-8K-ON", 1, "probe", since="x", why="a control never seats")
        nxt = SC.next_look_v2(self.st, "EVL-8K-READ-ON", 1, self.days[12])
        self.assertEqual((nxt["k"], nxt["events_needed"]), (2, 90))
        self.assertEqual(SC.run(self.st, self.days[12], draws=999, now=now)["written"], [], "each look written once")

    def test_final_until_reads_its_own_registration_and_the_close_receipts(self):
        prog = P.BY_KEY[("EVL-8K-READ-ON", 1)]
        now = final_record(self.st, self.days[10])
        final, _ = SC.final_until(self.st, prog.id, 1, self.days[10], now)
        self.assertEqual(final, self.days[7], "three later sessions decided: the re-decision window has passed it")
        rid = self.st.start_receipt(f"decide-close:{self.days[5].isoformat()}")
        self.st.finish_receipt(rid, "pending", {"pending": {"EVL-8K-READ-ON": 2}})
        self.assertEqual(SC.final_until(self.st, prog.id, 1, self.days[10], now)[0], self.days[4],
                         "a close decision pending on its own verdicts holds its looks")
        self.assertEqual(SC.final_until(self.st, "EVL-NEWS-READ-ON", 2, self.days[10], now)[0], self.days[7],
                         "an earlier row is not held by PREREG-EVL-4's wait")


# ----------------------------------------------------------------------------------------------------- the windows
class TheWindows(WorldCase):
    def test_the_close_window_pm_and_day(self):
        """F8K(D): knowable at P's close decision time is D's, at D's close decision time is the next session's. PM(D):
        after P's close and by 09:00 ET of D. DAY(D): after 09:00 ET of D and by T29 of D."""
        w = self.w
        w.filing("0000000002-26-000101", "BBB", knowable=et(PRIOR, 15, 46))               # F8K(D), its first instant
        w.filing("0000000003-26-000101", "CCC", knowable=et(D, 15, 46))                   # F8K(next): D's decision time
        w.article("pm-at-close", "HHH", knowable=et(PRIOR, 16, 0))                        # P's close: no PM(D)
        w.article("pm-first", "JJJ", knowable=et(PRIOR, 16, 0, 1))
        w.article("pm-last", "DDD", knowable=et(D, 9, 0))                                 # 09:00 ET: PM(D)
        w.article("day-first", "EEE", knowable=et(D, 9, 0, 1))                            # DAY(D): EEE excluded
        w.filing("0000000005-26-000101", "EEE", knowable=et(D, 10, 0))
        w.article("day-last", "FFF", knowable=et(D, 15, 29))                              # T29: DAY(D), excluded
        w.filing("0000000006-26-000101", "FFF", knowable=et(D, 10, 0))
        w.article("after-t29", "GGG", knowable=et(D, 15, 29, 1))                          # after T29: no window
        w.filing("0000000007-26-000101", "GGG", knowable=et(D, 10, 0))
        self.assertEqual(P.close_window(self.st, D), (et(PRIOR, 15, 46), et(D, 15, 46)))
        self.assertEqual(P.news_window(self.st, D), (et(PRIOR, 16, 0), et(D, 9, 0)))
        self.assertEqual(P.day_news_window(self.st, D), (et(D, 9, 0), et(D, 15, 29)))
        out = self.open_then_close(D)
        self.assertEqual(out["pending"], {})
        self.assertEqual(self.taken("EVL-CTRL-8K-ON", D), ["BBB", "GGG"], "EEE and FFF are in DAY(D)")
        self.assertEqual(self.taken("EVL-CTRL-NEWSPM-ON", D), ["DDD", "JJJ"], "HHH's article at P's close is no PM(D)")
        later = self.w.at(et(NEXT, 15, 47)).decide("close", NEXT, live=False)
        self.assertEqual(later["pending"], {})
        self.assertEqual(self.taken("EVL-CTRL-8K-ON", NEXT), ["CCC"], "knowable at D's decision time: the next session's")

    def test_the_registration_gate_and_excluding_rows_before_any_registration(self):
        """Mon Oct 19 (D), the registration day: its close window opens Fri Oct 16 15:46 ET. An item 2.02 8-K of AAA
        knowable Fri 17:00 ET (before even PREREG-EVL-1's registration) and an article of BBB knowable 10:00 ET (before
        PREREG-EVL-4's) EXCLUDE both issuers; an event knowable AT 16:01:05Z is not taken, one a second later is."""
        day, fri = dt.date(2026, 10, 19), dt.date(2026, 10, 16)
        w = self.w
        w.gw.doc.update({"BBB": 3, "CCC": 2, "DDD": 2, "EEE": 2})
        w.filing("0000000001-26-000201", "AAA", knowable=et(fri, 17, 0), items=("2.02",))
        w.filing("0000000001-26-000202", "AAA", knowable=et(day, 13, 0))
        w.article("bbb-day", "BBB", knowable=et(day, 10, 0))
        w.filing("0000000002-26-000201", "BBB", knowable=et(day, 13, 30))
        w.filing("0000000003-26-000201", "CCC", knowable=et(day, 13, 0))
        w.filing("0000000004-26-000201", "DDD", knowable=REGISTERED_4)
        w.filing("0000000005-26-000201", "EEE", knowable=REGISTERED_4 + dt.timedelta(seconds=1))
        self.assertNotIn("0000000001-26-000201", [r["accession"] for r in P.filings_in(self.st, "8-K", *P.close_window(
            self.st, day))], "the earlier files' reader is floored at PREREG-EVL-1's registration")
        self.assertIn("0000000001-26-000201", [r["accession"] for r in P.filings_window(self.st, "8-K", *P.close_window(
            self.st, day))], "the sets that skip are not")
        self.w.at(et(day, 15, 17)).decide("close", day, ask_only=True)
        out = self.w.at(et(day, 15, 47)).decide("close", day)
        self.assertEqual(out["pending"], {})
        for pid in ("EVL-CTRL-8K-ON", "EVL-8K-READ-ON"):
            self.assertEqual(self.taken(pid, day), ["CCC", "EEE"], pid)
        self.assertEqual({r["event"] for r in self.st.db.execute("SELECT event FROM intents WHERE program IN (?, ?)",
                                                                    ("EVL-CTRL-8K-ON", "EVL-8K-READ-ON"))},
                         {"8k:0000000003-26-000201", "8k:0000000005-26-000201"}, "nothing of AAA, BBB or DDD")
        self.assertEqual(out["events"]["excluded"], 2)


# ----------------------------------------------------------------------------------------------------- the rules
class TheRules(WorldCase):
    def test_8k_react_takes_a_rise_of_4_percent_and_ranks_by_it(self):
        g = self.w.gw
        g.minute.update({"AAA": 20.8, "BBB": 20.798, "CCC": 21.6, "EEE": 25.0})
        g.minute.pop("DDD", None)                                                         # DDD: no T29 bar
        w = self.w
        w.filing("0000000001-26-000301", "AAA", knowable=et(PRIOR, 17, 0))                # 1.04: taken
        w.filing("0000000002-26-000301", "BBB", knowable=et(PRIOR, 17, 0))                # 1.0399: not
        w.filing("0000000003-26-000301", "CCC", knowable=et(PRIOR, 18, 0), items=("2.01",))   # 1.08: CCC's later one
        w.filing("0000000003-26-000302", "CCC", knowable=et(PRIOR, 17, 30), items=("7.01",))  # the earliest: the event
        w.filing("0000000004-26-000301", "DDD", knowable=et(PRIOR, 17, 0))                # no price: not
        w.filing("0000000005-26-000301", "EEE", knowable=et(PRIOR, 17, 0), items=("5.02",))   # not the family
        out = self.open_then_close(D)
        self.assertEqual(out["pending"], {})
        self.assertEqual([(r["symbol"], r["event"], r["status"]) for r in self.intents("EVL-8K-REACT-ON", D)],
                         [("AAA", "8k:0000000001-26-000301", "planned"),
                          ("CCC", "8k:0000000003-26-000301", "skipped:issuer-held"),
                          ("CCC", "8k:0000000003-26-000302", "planned")])
        react = {r["symbol"]: r for r in self.intents("EVL-8K-REACT-ON", D) if r["status"] == "planned"}
        self.assertAlmostEqual(react["AAA"]["rank_key"], 1.04)
        self.assertAlmostEqual(react["CCC"]["rank_key"], 1.08)
        marks = {r["symbol"]: r["px"] for r in self.st.db.execute("SELECT symbol, px FROM marks WHERE label='1530'")}
        self.assertEqual(marks, {"AAA": 20.8, "BBB": 20.798, "CCC": 21.6}, "read in one batch; DDD has no bar")
        batched = [p for path, p in g.gets if path.endswith("/stocks/bars") and p.get("timeframe") == "1Min"]
        self.assertEqual(batched[0]["symbols"], "AAA,BBB,CCC,DDD")
        lane = EB.Lane(self.w.root / S.DB_NAME)
        self.addCleanup(lane.close)
        picks = EB.picks(lane, P.BY_ID["EVL-8K-REACT-ON"], D, decided_at=et(D, 15, 46),
                         reaction=lambda row, uni: g.minute.get(uni["symbol"]) and g.minute[uni["symbol"]] / 20.0)
        self.assertEqual([(p.symbol, p.event, p.rank) for p in picks],
                         [("CCC", "8k:0000000003-26-000302", 21.6 / 20), ("AAA", "8k:0000000001-26-000301", 20.8 / 20)],
                         "ranked by the reaction, higher first; one event an issuer, its earliest")

    def test_8k_read_takes_score_2_waits_for_its_verdict_and_shares_8k_read_o1s(self):
        g = self.w.gw
        g.doc.update({"AAA": 2, "BBB": 1, "CCC": 3})
        w = self.w
        w.filing("0000000001-26-000401", "AAA", knowable=et(D, 10, 0))                    # score 2: taken
        w.filing("0000000002-26-000401", "BBB", knowable=et(D, 10, 0))                    # score 1: not
        w.filing("0000000003-26-000401", "CCC", knowable=et(D, 10, 0), text_len=150)      # TEXT < 200: no verdict
        refusing = W.Gateway(doc=g.doc)
        refusing.post_json = lambda path, body, headers=None: (400, {"error": "no"})
        refused = R.Context(self.st, refusing, W.sec, now=lambda: et(D, 15, 47))
        self.w.at(et(D, 9, 15, 30)).decide("open", D)
        out = R.decide_close(refused, D)
        self.assertEqual(out["pending"], {"EVL-8K-READ-ON": 2}, "READ events wait for their verdicts (the shadow rule)")
        self.assertEqual(self.intents("EVL-8K-READ-ON", D), [])
        self.assertEqual(self.taken("EVL-CTRL-8K-ON", D), ["AAA", "BBB", "CCC"], "the control needs no verdict")
        out = self.w.at(et(D, 15, 55)).decide("close", D)
        self.assertEqual(out["pending"], {})
        self.assertEqual(self.taken("EVL-8K-READ-ON", D), ["AAA"])
        self.assertEqual(sorted(g.asked()), ["doc:AAA", "doc:BBB"], "asked once each; a TEXT under 200 never")
        # the next open: EVL-8K-READ-O1 reads the one stored verdict of each filing (no second ask)
        self.w.at(et(NEXT, 9, 15, 30)).decide("open", NEXT)
        self.assertEqual(sorted(g.asked()), ["doc:AAA", "doc:BBB"])
        self.assertEqual((self.taken("EVL-8K-READ-O1", NEXT), self.taken("EVL-8K-READ-O1", NEXT, 2)), (["AAA"], ["AAA"]))
        stored = V.stored(self.st, "8k:0000000001-26-000401", V.PROMPTS["doc"])
        self.assertEqual((stored["score"], stored["prompt_sha"]), (2, V.PROMPTS["doc"].sha))

    def test_newspm_takes_the_highest_score_then_the_earliest_and_asks_nothing(self):
        w = self.w
        w.article("e-1", "EEE", knowable=et(D, 6, 0))
        w.article("e-2", "EEE", knowable=et(D, 7, 0))                                     # EEE's best: 3
        w.article("j-1", "JJJ", knowable=et(D, 6, 30))
        w.article("j-2", "JJJ", knowable=et(D, 8, 30))                                    # a tie: the earliest
        w.article("g-1", "GGG", knowable=et(D, 7, 0))                                     # score 1: the control's only
        out = self.w.at(et(D, 15, 47)).decide("close", D)
        self.assertEqual(out["pending"], {"EVL-NEWSPM-READ-ON": 5, "EVL-CTRL-NEWSPM-ON": 5},
                         "both wait for EVL-NEWS-READ-O1's verdicts")
        self.assertTrue(R.waits_on_open(out))
        self.assertEqual(self.w.gw.asked(), [], "these rows ask no verdict of their own")
        for ident, score, at in (("e-1", 2, 6), ("e-2", 3, 7), ("j-1", 3, 7), ("j-2", 3, 9), ("g-1", 1, 8)):
            self.verdict(f"news:{ident}", score, et(D, at, 5), news=True)
        out = self.w.at(et(D, 15, 50)).decide("close", D)
        self.assertEqual(out["pending"], {})
        self.assertFalse(R.waits_on_open(out))
        self.assertEqual({r["symbol"]: r["event"] for r in self.intents("EVL-NEWSPM-READ-ON", D)},
                         {"EEE": "news:e-2", "JJJ": "news:j-1"})
        self.assertEqual({r["symbol"]: (r["event"], r["rank_key"]) for r in self.intents("EVL-CTRL-NEWSPM-ON", D)},
                         {"EEE": ("news:e-2", 3.0), "JJJ": ("news:j-1", 3.0), "GGG": ("news:g-1", 1.0)})
        self.assertEqual(self.w.gw.asked(), [])

    def test_newspm_skips_an_issuer_with_any_f8k_filing_and_the_excluded(self):
        w = self.w
        w.article("f-1", "FFF", knowable=et(D, 7, 0))
        w.filing("0000000006-26-000501", "FFF", knowable=et(D, 14, 0))                   # any F8K(D) filing
        w.article("a-1", "AAA", knowable=et(D, 7, 0))
        w.filing("0000000001-26-000501", "AAA", knowable=et(D, 14, 0), items=("2.02",))  # ERN(D)
        w.article("d-1", "DDD", knowable=et(D, 7, 0))
        w.article("d-2", "DDD", knowable=et(D, 12, 0))                                    # DAY(D)
        w.article("e-1", "EEE", knowable=et(D, 7, 0))
        w.filing("0000000005-26-000501", "EEE", knowable=et(D, 14, 0), items=("5.02",))  # not the family
        out = self.open_then_close(D)
        self.assertEqual(out["pending"], {})
        self.assertEqual(self.taken("EVL-CTRL-NEWSPM-ON", D), ["EEE"])
        self.assertEqual(self.taken("EVL-NEWSPM-READ-ON", D), ["EEE"])
        self.assertEqual(self.taken("EVL-CTRL-8K-ON", D), ["FFF"], "the filing is the 8-K rows' issuer-day")
        self.assertEqual(self.taken("EVL-NEWS-READ-O1", D), ["DDD", "EEE", "FFF"],
                         "EVL-NEWS-READ-O1 is untouched (AAA's article scored 0)")


# ----------------------------------------------------------------------------------------------------- late rows
class TheLateRows(WorldCase):
    def test_a_redecision_marks_an_unsettled_intent_excluded_by_a_row_stored_later(self):
        w = self.w
        w.filing("0000000003-26-000601", "CCC", knowable=et(D, 10, 0))
        w.filing("0000000008-26-000601", "HHH", knowable=et(D, 10, 0))
        w.article("f-1", "FFF", knowable=et(D, 7, 0))
        self.open_then_close(D)
        self.assertEqual(self.taken("EVL-8K-READ-ON", D), ["CCC", "HHH"])
        self.assertEqual(self.taken("EVL-NEWSPM-READ-ON", D), ["FFF"])
        # stored after the decision, all knowable before it: an earnings 8-K of CCC (ERN(D)), an article of HHH during
        # D (DAY(D)), a family 8-K of FFF (the F8K(D) skip)
        w.filing("0000000003-26-000602", "CCC", knowable=et(D, 14, 0), items=("2.02",), stored=et(D, 16, 30))
        w.article("h-1", "HHH", knowable=et(D, 13, 0), stored=et(D, 16, 30))
        w.filing("0000000006-26-000601", "FFF", knowable=et(D, 12, 0), stored=et(D, 16, 30))
        # the settled one stays as it is (its record is final)
        self.st.db.execute("UPDATE intents SET status='exited' WHERE program='EVL-CTRL-8K-ON' AND symbol='CCC'")
        out = self.w.at(et(D, 16, 41)).decide("close", D, live=False)
        status = {(r["program"], r["symbol"]): r["status"] for r in self.st.db.execute("SELECT * FROM intents")}
        for pid in ("EVL-8K-READ-ON", "EVL-8K-REACT-ON"):
            self.assertEqual(status[(pid, "CCC")], "skipped:excluded", pid)
            self.assertEqual(status[(pid, "HHH")], "skipped:excluded", pid)
        self.assertEqual(status[("EVL-CTRL-8K-ON", "CCC")], "exited")
        self.assertEqual(status[("EVL-CTRL-8K-ON", "HHH")], "skipped:excluded")
        self.assertEqual(status[("EVL-NEWSPM-READ-ON", "FFF")], "skipped:excluded")
        self.assertEqual(status[("EVL-CTRL-NEWSPM-ON", "FFF")], "skipped:excluded")
        self.assertEqual(status[("EVL-CTRL-8K-ON", "FFF")], "planned", "FFF's filing is now the 8-K rows' event")
        self.assertEqual(out["skipped_excluded"], 7)
        self.assertEqual(status[("EVL-ERN-REACT-C1", "CCC")], "planned", "the earlier rows decide the late 8-K as ever")
        again = self.w.at(et(D, 17, 41)).decide("close", D, live=False)
        self.assertNotIn("skipped_excluded", again)
        # the report counts the difference from real money (section 1.3): rows stored after the decision, intents a
        # later row excluded
        self.assertEqual(RP.late_rows(self.st, "EVL-8K-READ-ON", 1, D),
                         {"stored_late_today": 0, "stored_late": 0, "excluded_late": 2})
        self.assertEqual(RP.late_rows(self.st, "EVL-CTRL-8K-ON", 1, D),
                         {"stored_late_today": 1, "stored_late": 1, "excluded_late": 1}, "FFF's filing, stored 16:30")
        self.assertEqual(RP.late_rows(self.st, "EVL-ERN-REACT-C1", 2, D)["stored_late"], 1, "CCC's earnings 8-K")
        text = RP.render(RP.build(self.st, D, now=et(D, 21, 5)))
        self.assertIn("EVL-CTRL-8K-ON v1 (record): today p/e/s/x", text)
        self.assertIn("stored after its decision 1 (today 1), excluded by a later row 1", text)


# ----------------------------------------------------------------------------------------------------- real money
class TheBook(WorldCase):
    def lane(self) -> EB.Lane:
        lane = EB.Lane(self.w.root / S.DB_NAME)
        self.addCleanup(lane.close)
        return lane

    def test_the_three_seat_at_learning_after_the_nine_and_the_controls_never(self):
        lane = self.lane()
        self.assertEqual([p.id for p in EB.seatable()], list(NINE + NEW))
        self.assertEqual([(b.program, b.version, b.band) for b in EB.bands(lane)][-3:], [(i, 1, "learning") for i in NEW])
        for pid in CONTROLS4:
            self.assertIsNone(EB.program_of(pid, 1), pid)
        self.assertIsNone(EB.program_of("EVL-8K-REACT-ON", 2))
        self.assertLess(EB.room_key("EVL-NEWS-REACT-ON", "learning"), EB.room_key("EVL-8K-REACT-ON", "learning"))
        self.assertLess(EB.room_key("EVL-8K-REACT-ON", "learning"), EB.room_key("EVL-8K-READ-ON", "learning"))
        self.assertLess(EB.room_key("EVL-8K-READ-ON", "learning"), EB.room_key("EVL-NEWSPM-READ-ON", "learning"))
        self.assertLess(EB.room_key("EVL-NEWSPM-READ-ON", "probe"), EB.room_key("EVL-ERN-READ-O1", "learning"))
        def pick(program: str, symbol: str) -> EB.Pick:
            return EB.Pick(program, 1, f"e:{program}", symbol, "1", 2.0, 1e6, Decimal(10), "z")
        given = EB.one_name_an_auction({"EVL-8K-READ-ON": [pick("EVL-8K-READ-ON", "CCC")],
                                        "EVL-NEWS-READ-ON": [pick("EVL-NEWS-READ-ON", "CCC")]})
        self.assertEqual({k: [p.symbol for p in v] for k, v in given.items()},
                         {"EVL-NEWS-READ-ON": ["CCC"], "EVL-8K-READ-ON": []}, "the earlier row takes the name")

    def test_real_money_reads_the_rows_stored_before_its_decision_and_the_next_open_guard(self):
        """Section 1.3: the real-money decision is the shadow rule over the rows STORED before D's close decision time,
        EXCLUDED read from them too; and the 8-K rows never buy for a filing knowable from 09:00 ET of D whose verdict is
        `ok` with score >= 2, or not answered, by then (EVL-8K-READ-O1's event at the next open)."""
        w, g = self.w, self.w.gw
        g.doc.update({"AAA": 1, "BBB": 2, "CCC": 3, "FFF": 2, "HHH": 1, "III": 3})
        w.filing("0000000002-26-000701", "BBB", knowable=et(PRIOR, 18, 0))                # before 09:00 ET of D: bought
        w.filing("0000000001-26-000701", "AAA", knowable=et(D, 10, 0))                    # answered 1: bought
        w.filing("0000000003-26-000701", "CCC", knowable=et(D, 10, 0))                    # answered 3: O1's next open
        w.filing("0000000008-26-000701", "HHH", knowable=et(D, 11, 0))                    # answered 1
        self.w.at(et(D, 9, 15, 30)).decide("open", D)
        self.w.at(et(D, 15, 0)).decide("close", D, ask_only=True)                        # the verdicts asked during D
        w.filing("0000000006-26-000701", "FFF", knowable=et(D, 15, 20))                   # not answered by 15:46
        # stored after 15:46, knowable before: HHH's earnings 8-K (EXCLUDED in the shadow only), III's family 8-K
        w.filing("0000000008-26-000702", "HHH", knowable=et(D, 13, 0), items=("2.02",), stored=et(D, 15, 50))
        w.filing("0000000009-26-000701", "III", knowable=et(D, 12, 0), stored=et(D, 15, 50))
        lane = self.lane()
        moment = et(D, 15, 46)
        react = lambda row, uni: 1.05  # noqa: E731
        got = {pid: [p.symbol for p in EB.picks(lane, P.BY_ID[pid], D, decided_at=moment, reaction=react)]
               for pid in NEW[:2]}
        self.assertEqual(got, {"EVL-8K-REACT-ON": ["AAA", "BBB", "HHH"], "EVL-8K-READ-ON": ["BBB"]},
                         "CCC (score 3) and FFF (unanswered) are EVL-8K-READ-O1's at the next open; III not stored")
        rows = EB.rows_for(lane, P.BY_ID["EVL-8K-REACT-ON"], D, moment)
        self.assertEqual(sorted(r["accession"] for r in rows),
                         ["0000000001-26-000701", "0000000002-26-000701", "0000000003-26-000701", "0000000006-26-000701",
                          "0000000008-26-000701"], "the rows stored by 15:46 alone, HHH not excluded by a later row")
        session = C.session(lane, D)
        self.assertEqual({r["accession"]: EB.next_open_event(lane, r, session, moment) for r in rows},
                         {"0000000001-26-000701": False, "0000000002-26-000701": False, "0000000003-26-000701": True,
                          "0000000006-26-000701": True, "0000000008-26-000701": False})
        lane.close()
        self.w.at(et(D, 15, 47)).decide("close", D)
        self.w.at(et(D, 16, 41)).decide("close", D, live=False)
        self.assertEqual(self.taken("EVL-8K-REACT-ON", D), ["AAA", "CCC", "III"],
                         "the shadow keeps every event (its own T29 reads: BBB and FFF rose 2.5%); HHH is EXCLUDED there "
                         "by its earnings 8-K")
        self.assertEqual(self.taken("EVL-8K-READ-ON", D), ["BBB", "CCC", "FFF", "III"])

    def test_the_guard_reads_only_the_8k_rows_and_answers_after_the_decision_as_unanswered(self):
        w = self.w
        w.filing("0000000003-26-000801", "CCC", knowable=et(D, 10, 0))
        self.verdict("8k:0000000003-26-000801", 3, et(D, 15, 46, 30))                     # answered after 15:46
        lane = self.lane()
        session = C.session(lane, D)
        row = dict(lane.db.execute("SELECT * FROM filings").fetchone())
        self.assertTrue(EB.next_open_event(lane, row, session, et(D, 15, 46)))
        self.assertTrue(EB.next_open_event(lane, row, None, et(D, 15, 46)), "no session: fail closed")
        self.assertEqual(EB.NEXT_OPEN_GUARD, ("EVL-8K-REACT-ON", "EVL-8K-READ-ON"))
        lane.close()
        self.st.db.execute("UPDATE verdicts SET answered_at=?, status='unparsed', score=NULL", (S.iso(et(D, 12, 0)),))
        lane = self.lane()
        self.assertFalse(EB.next_open_event(lane, row, C.session(lane, D), et(D, 15, 46)),
                         "an answer that is not ok leaves the buy")

    def test_the_prompts_are_unchanged(self):
        self.assertEqual(V.PROMPTS["doc"].sha, "b735c36ee7127d04afd1f6277b1441639680ad04b4c688118b465323dd5ad3f3")
        self.assertEqual(V.PROMPTS["news"].sha, "4b5245a95835a32f37eaf79ebbd54cc9aa72e1c4608e3ad96e00d302463bcacf")


class TheSaleGateCount(TB.EventTest):
    """Section 1.3's stated case, counted and never prevented: an earlier row's real-money buy at the next open lost to
    the sale gate because this file's overnight lot of the same name sells at that open."""

    def test_an_earlier_rows_buy_lost_to_a_later_rows_sale_is_counted(self):
        h = self.harness()
        prev2 = ES.previous_session(TB.PRIOR)
        h.lane.universe(TB.PRIOR, "ACME", TB.CIK, 16.0)
        # F8K(PRIOR): knowable before 09:00 ET of PRIOR; its verdict answered after PRIOR's open decision, so
        # EVL-8K-READ-O1 bought nothing at PRIOR's open and EVL-8K-READ-ON buys ACME at PRIOR's close
        h.lane.filing("f-1", TB.CIK, accepted=TB.iso(prev2, 16, 30), received=TB.iso(prev2, 16, 31), items=("8.01",))
        h.lane.verdict("f-1", 2, answered=TB.iso(TB.PRIOR, 10, 0))
        TB.earnings(h.lane, "f-2", TB.CIK, "ACME", score=3, items=("8.01",), prev_close=16.8)  # O1's at DAY's open
        self.ready(h, TB.PRIOR)
        self.ready(h, TB.DAY)
        h.symbol("ACME", last=16.8)
        h.venue.prints[("ACME", TB.PRIOR.isoformat(), "close")] = Decimal("16.90")
        h.venue.prints[("ACME", TB.DAY.isoformat(), "open")] = Decimal("17.00")
        for hh, mm in ((15, 46), (15, 47), (16, 1), (16, 3)):
            h.tick(hh, mm, day=TB.PRIOR)
        [lot] = h.lots()
        self.assertEqual((lot.family, lot.version, lot.info["evl_exit"]["day"], lot.info["evl_exit"]["at"]),
                         ("EVL-8K-READ-ON", 1, TB.DAY.isoformat(), "open"), "version 1 trades: its seating version")
        for hh, mm in ((9, 15), (9, 16), (9, 17)):
            h.tick(hh, mm, day=TB.DAY)
        summary = json.loads(h.state.rows("SELECT summary FROM eq_event_decisions WHERE day=? AND at='open'",
                                          (TB.DAY.isoformat(),))[0]["summary"])
        self.assertEqual(summary["programs"]["EVL-8K-READ-O1"]["skipped"], {"sale": 1})
        self.assertEqual(summary["sale_to_later"], {"EVL-8K-READ-O1": {"EVL-8K-READ-ON": 1}})
        [record] = [p for kind, p in h.events if kind == "equity.event_decide" and p["day"] == TB.DAY.isoformat()]
        self.assertEqual(record["sale_to_later"], {"EVL-8K-READ-O1": {"EVL-8K-READ-ON": 1}})


# ----------------------------------------------------------------------------------------------------- the House
class TheHouse(LaneCase):
    def test_a_close_waiting_on_pm_verdicts_has_the_open_decisions_asked(self):
        """CCC's pre-market article (knowable 08:00 ET) is stored at 09:30 ET, after Tuesday's open decision: the close's
        verdict task finds EVL-NEWSPM-READ-ON waiting on a PROMPT-NEWS verdict only EVL-NEWS-READ-O1's open decision
        asks, and has that decision's own asks made (`decide_open` with `ask_only`)."""
        self.at(house_et("2026-10-20", "09:16"))
        self.mark_recorded()
        self.assertEqual(self.turn()["task"], "decide-open")
        with self.store() as st:
            st.db.execute("INSERT INTO news(id, created_at, updated_at, received_at, knowable_at, source, headline, "
                          "summary, symbols, live) VALUES('ccc-pm', ?, ?, ?, ?, 'invented', 'h', 's', '[\"CCC\"]', 1)",
                          (S.iso(house_et("2026-10-20", "07:58")), S.iso(house_et("2026-10-20", "07:58")),
                           S.iso(house_et("2026-10-20", "09:30")), S.iso(house_et("2026-10-20", "08:00"))))
        self.at(house_et("2026-10-20", "15:20"))
        self.mark_recorded()
        self.lane._events_at = self.lane.now()
        last = self.turn()
        self.assertEqual(last["task"], "verdicts")
        self.assertTrue(any(c["messages"][0]["content"].startswith("Stock: CCC.") for c in self.gw.claude_calls),
                        "EVL-NEWS-READ-O1's own ask of the article")
        with self.store() as st:
            self.assertIsNotNone(V.stored(st, "news:ccc-pm", V.PROMPTS["news"]))
            ctx = R.Context(st, self.gw, self.sec, now=lambda: house_et("2026-10-20", "15:21"))
            self.assertEqual(R.decide_close(ctx, dt.date(2026, 10, 20), ask_only=True)["pending"], {})

    def test_a_wait_no_call_can_answer_backs_off(self):
        gw = H.LaneGateway(self.gw, self.lane, None, cut=False)
        key = ("close", dt.date(2026, 10, 20))
        self.assertTrue(self.lane._look(key, 2, 0, gw), "nothing asked, nothing stored: stalled")
        gw.counts.update({"asked": 1, "answered": 1})
        self.assertFalse(self.lane._look(key, 2, 1, gw), "an answer stored: not stalled")
        gw.counts.clear()
        gw.counts.update({"cut_deadline": 1})
        self.assertFalse(self.lane._look(key, 2, 0, gw), "out of time: tried again")
        gw.counts.clear()
        gw.counts.update({"asked": 1, "refused": 1})
        self.assertTrue(self.lane._look(key, 2, 0, gw), "refused: stalled, as before")


# ----------------------------------------------------------------------------------------------------- the proof
class TheProof(unittest.TestCase):
    """NO PREREG-EVL-1/2/3 PROGRAM CHANGES: the synthetic week (league/tests/evl4_world.py: every family of the three
    earlier files and of PREREG-EVL-4 on one store, decided as the House decides, with a late-stored filing and the
    re-decisions) gives every earlier program the same intents and the same real-money picks with PREREG-EVL-4's rows
    and without them (the code of release 1019b decides the same week to the same rows: evl4_world.py's script)."""

    def week(self, *, evl4: bool) -> tuple[list[tuple], dict, W.World, tempfile.TemporaryDirectory]:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        world = W.World(Path(tmp.name) / "lane")
        self.addCleanup(world.close)
        if evl4:
            W.the_week(world)
        else:
            rows, reads = without_evl4()
            with rows, reads:
                W.the_week(world)
            self.assertEqual(world.intents(lambda p, v: p in FOUR), [], "no row of PREREG-EVL-4 decided")
        return world.intents(earlier), W.nine_picks(world), world, tmp

    def test_every_earlier_programs_intents_and_picks_are_the_same(self):
        with_rows, with_picks, world, _ = self.week(evl4=True)
        without_rows, without_picks, _, _ = self.week(evl4=False)
        self.assertGreater(len(without_rows), 50)
        self.assertTrue(set(NINE) <= {r[0] for r in without_rows}, "every seatable family of the earlier files is in it")
        self.assertEqual(with_rows, without_rows)
        self.assertEqual(with_picks, without_picks)
        mine = {(r[0], r[3], r[12]) for r in world.intents(lambda p, v: p in FOUR)}
        self.assertEqual(mine, {
            ("EVL-8K-REACT-ON", "CCC", "planned"), ("EVL-8K-REACT-ON", "HHH", "skipped:excluded"),
            ("EVL-8K-REACT-ON", "III", "planned"),
            ("EVL-8K-READ-ON", "BBB", "planned"), ("EVL-8K-READ-ON", "CCC", "planned"),
            ("EVL-8K-READ-ON", "HHH", "skipped:excluded"), ("EVL-8K-READ-ON", "III", "planned"),
            ("EVL-CTRL-8K-ON", "BBB", "planned"), ("EVL-CTRL-8K-ON", "CCC", "planned"), ("EVL-CTRL-8K-ON", "FFF", "planned"),
            ("EVL-CTRL-8K-ON", "HHH", "skipped:excluded"), ("EVL-CTRL-8K-ON", "III", "planned"),
            ("EVL-NEWSPM-READ-ON", "EEE", "planned"), ("EVL-NEWSPM-READ-ON", "JJJ", "planned"),
            ("EVL-CTRL-NEWSPM-ON", "EEE", "planned"), ("EVL-CTRL-NEWSPM-ON", "JJJ", "planned")},
            "AAA (ERN), DDD (DAY) excluded; FFF's news skipped for its 8-K; HHH excluded by its late earnings 8-K")


if __name__ == "__main__":
    unittest.main()
