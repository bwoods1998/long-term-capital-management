"""RELEASE 1019f: THE SCREEN AFTER THE OPEN (the audit's "bands move a session late"). The judge (league/events/screen.py
`final_until`) makes a close X final once the session after X has had its open decision (A69's fast path; A66's three
sessions likewise move at an open), and the intents a look as of X covers were settled by X's own score; yet the lane
ran the screen only at 20:30 ET and the House's event book read the bands once a session, at its first decision. So a
look the open made final was written that evening, after the close decision, and a close-entry program reached Probe a
session late. Held here, with no rule moved:
- the House's lane runs the screen's looks of the seating versions after the open decision (from 09:40 ET) whenever the
  judge's final horizon of any of them moved since the last screen receipt, and never twice for the same horizons; the
  nightly screen (with the band review of the real fills) writes nothing a morning look already wrote;
- the House's event book reads the bands again at the close decision when the lane's band history moved since its
  morning sync, so a look written at 10:00 ET makes that day's close decision buy at the Probe band;
- the night is the SESSION's: a score that ran past midnight ET still gets that session's screen and report, once;
- the screen's receipt keeps why each look waits.
Synthetic data only: every event, return, receipt, price and fill here is invented."""

from __future__ import annotations

import datetime as dt
import json
import unittest
from decimal import Decimal as D
from unittest import mock

from league.events import bands as BA
from league.events import book as EB
from league.events import calendar as C
from league.events import house as H
from league.events import programs as P
from league.events import score as SC
from league.events import screen as SN
from league.events import store as S
from league.tests import test_events_house as TH
from league.tests.test_events_book import CIK, DAY, NEXT, PRIOR, EventTest, at, iso
from league.tests.test_events_screen import decided_summary, final_record

UTC = dt.timezone.utc
NY = C.NY
#: A record pass's receipt as the House writes it when every feed read whole (league/events/house.py `_record`).
CLEAN = {"8-K": {"new": 0, "fetched": 0, "failed": 0, "unlisted": 0}, "4": {"new": 0, "fetched": 0, "failed": 0,
                                                                          "unlisted": 0},
         "news": {"seen": 0, "stored": 0}, "cut": False, "verdicts": []}


def et(day: dt.date, hh: int, mm: int = 0, ss: int = 0) -> dt.datetime:
    return dt.datetime.combine(day, dt.time(hh, mm, ss), tzinfo=NY).astimezone(UTC)


def settle(st: S.Store, program: str, entries, per_day: int, a: float, *, start: int = 1000) -> int:
    """Settled invented events of `program` at its seating version: `per_day` a session on each entry session, each
    exiting at the program's own exit (the same session's close, or the next session's open), abnormal return `a`."""
    p = next(x for x in P.SEATING if x.id == program)
    n = start
    for d in entries:
        exit_day = d if p.exit_at == "close" else C.nth(st, d, 2).day
        for _ in range(per_day):
            ev = f"syn:{program}:{n}"
            st.db.execute("INSERT INTO intents(program, version, event, symbol, cik, decided_at, entry_day, entry_at, "
                          "exit_day, exit_at, rank_key, mode, status, why) VALUES(?, ?, ?, 'SYN', ?, 'z', ?, ?, ?, ?, "
                          "NULL, 'shadow', 'exited', NULL)", (p.id, p.version, ev, f"{n:010d}", d.isoformat(),
                                                             p.entry_at, exit_day.isoformat(), p.exit_at))
            st.db.execute("INSERT INTO outcomes(program, version, event, entry_px, exit_px, bench, bench_entry, bench_exit, "
                          "cost_entry_bp, cost_exit_bp, r, b, a, tradable, settled_at, status) VALUES(?, ?, ?, 10, 10, "
                          "'SPY', 1, 1, 5, 5, ?, 0, ?, 1, 'z', 'settled')", (p.id, p.version, ev, a, a))
            n += 1
    return n


def decisions(st: S.Store, first: dt.date, last: dt.date, *, kinds=("open", "close")) -> None:
    """Every decision of the sessions [first, last] made `ok`, each receipt naming its programs and stamped at its own
    time (never the wall clock), as the House's lane writes them."""
    for s in C.sessions(st, first, last):
        for kind in kinds:
            when = (s.open_decide if kind == "open" else s.close_decide) + dt.timedelta(seconds=30)
            rid = st.start_receipt(f"decide-{kind}:{s.day.isoformat()}", now=when)
            st.finish_receipt(rid, "ok", decided_summary(kind), now=when + dt.timedelta(seconds=20))


def backfilled(st: S.Store, first: dt.date, last: dt.date) -> None:
    d = first
    while d <= last:
        if d.weekday() < 5:
            st.set_meta(f"evl:backfill:{d.isoformat()}", "done")
        d += dt.timedelta(days=1)


def passes(st: S.Store, start: dt.datetime, end: dt.datetime, every=dt.timedelta(minutes=10)) -> None:
    """Record passes every `every` from `start` through `end`, each finished `ok` with its feeds read whole."""
    rows, t = [], start
    while t <= end:
        rows.append(("record", S.iso(t), S.iso(t + dt.timedelta(seconds=40)), "ok", json.dumps(CLEAN)))
        t += every
    st.db.executemany("INSERT INTO receipts(job, started_at, finished_at, status, summary) VALUES(?, ?, ?, ?, ?)", rows)


# --------------------------------------------------------------------------------------------- the House's lane
class ScreenAfterTheOpen(TH.LaneCase):
    """EVL-INS-BUY-O1 v2 (an open-entry program, one session held): 10 events a session at +1% on the eight sessions
    Oct 20-29, 2026, so its look 1 (80 events, 80 issuers, 8 blocks) falls due as of Oct 29's close. Every decision is
    made, every backfill run and every record pass read its feeds whole (A69's fast path): Oct 29's close is final once
    Oct 30's open decision is made."""

    PROG = "EVL-INS-BUY-O1"
    KEY = "EVL-INS-BUY-O1@v2"
    X = dt.date(2026, 10, 29)
    T = dt.date(2026, 10, 30)

    def setUp(self):
        super().setUp()
        self.lane = self.new_lane(screen_open=True)
        with self.store() as st:
            entries = [s.day for s in C.sessions(st, dt.date(2026, 10, 20), self.X)]
            self.assertEqual(len(entries), 8)
            settle(st, self.PROG, entries, 10, 0.01)
            decisions(st, dt.date(2026, 10, 20), self.X)
            backfilled(st, dt.date(2026, 10, 15), self.T)
            for d in [s.day for s in C.sessions(st, dt.date(2026, 10, 20), self.T)]:
                st.set_meta(SC.equity_key(d), repr(2000.0))
                st.set_meta(f"tickers@{S.iso(et(d, 7, 0, 5))}", st.meta("tickers@2026-10-20T11:00:05Z"))
            passes(st, et(dt.date(2026, 10, 23), 8, 40), et(self.X, 20, 30))

    def screens(self, job="screen"):
        """This release's screen receipts (the fixture's Monday night one has no `run`)."""
        rows = [json.loads(r["summary"]) | {"status": r["status"]} for r in self.receipts(job)]
        return [r for r in rows if "run" in r]

    def turned(self):
        """One turn; the task it ran, or None (the lane's health keeps the last task run, not this turn's)."""
        before = self.lane.health()["last"]
        last = self.turn()
        return last.get("task") if last and last != before else None

    def band_history(self):
        with self.store() as st:
            return [dict(r) for r in st.db.execute("SELECT * FROM band_history ORDER BY id")]

    def looks(self):
        with self.store() as st:
            return [dict(r) for r in st.db.execute("SELECT program, version, k, at FROM looks ORDER BY program, k")]

    def night_of_x(self):
        """Oct 29's night at 20:31 ET: the score, the screen, the report."""
        self.at(et(self.X, 20, 31))
        self.assertEqual([self.turned() for _ in range(3)], ["score", "screen", "report"])

    def open_of_t(self):
        """Oct 30's open decision made at 09:15:30 ET, the record passes through 09:10 ET."""
        with self.store() as st:
            passes(st, et(self.X, 20, 40), et(self.T, 9, 10))
            decisions(st, self.T, self.T, kinds=("open",))

    def test_a_look_the_open_makes_final_is_written_that_morning_and_never_twice(self):
        self.night_of_x()
        [night] = self.screens()
        self.assertEqual((night["run"], night["day"], night["written"]), ("night", "2026-10-29", 0))
        self.assertEqual(night["horizons"][self.KEY], "2026-10-28", "Oct 29 waits for Oct 30's open decision")
        self.assertEqual(self.looks(), [])
        self.open_of_t()
        self.at(et(self.T, 9, 35))
        self.mark_recorded()
        self.assertNotEqual(self.turned(), H.SCREEN_OPEN_JOB, "not before 09:40 ET")
        self.assertEqual(self.receipts(H.SCREEN_OPEN_JOB), [])
        self.at(et(self.T, 9, 41))
        self.mark_recorded()
        self.assertEqual(self.turned(), H.SCREEN_OPEN_JOB)
        [morning] = self.screens(H.SCREEN_OPEN_JOB)
        self.assertEqual((morning["status"], morning["run"], morning["day"], morning["written"]),
                         ("ok", "open", "2026-10-30", 1))
        self.assertEqual(morning["horizons"][self.KEY], "2026-10-29")
        self.assertEqual(morning["looks"], [{"program": self.PROG, "version": 2, "k": 1, "held": 1, "passed": 1,
                                             "band": "probe"}])
        self.assertEqual([(r["program"], r["version"], r["k"]) for r in self.looks()], [(self.PROG, 2, 1)])
        self.assertEqual(S.parse_iso(self.looks()[0]["at"]).astimezone(NY).date(), self.X, "as of Oct 29's close")
        [move] = self.band_history()
        self.assertEqual((move["program"], move["version"], move["band"], move["written_at"]),
                         (self.PROG, 2, "probe", S.iso(et(self.T, 9, 41))),
                         "Probe from 09:41 ET: the House's close decision of Oct 30 is the first decision after it")
        with self.store() as st:
            self.assertEqual(BA.bands(st)[(self.PROG, 2)], "probe")
        # NOTHING IS SCREENED TWICE FOR THE SAME HORIZONS: the morning's later reads find them unmoved
        for hh, mm in ((9, 52), (10, 3), (11, 30), (15, 30)):
            self.at(et(self.T, hh, mm))
            self.mark_recorded()
            self.turn()
        self.assertEqual(len(self.receipts(H.SCREEN_OPEN_JOB)), 1)
        # ... and the night's screen (the band review with it) writes nothing the morning wrote
        with self.store() as st:
            decisions(st, self.T, self.T, kinds=("close",))
        self.at(et(self.T, 20, 31))
        self.mark_recorded()
        self.assertEqual([self.turned() for _ in range(2)], ["score", "screen"])
        tonight = self.screens()[-1]
        self.assertEqual((tonight["run"], tonight["day"], tonight["written"], tonight["review"]),
                         ("night", "2026-10-30", 0, []))
        self.assertEqual(len(self.looks()), 1)
        self.assertEqual(len(self.band_history()), 1)

    def test_the_screen_receipt_keeps_why_each_look_waits(self):
        self.night_of_x()
        [night] = self.screens()
        waits = [w for w in night["waits"] if w["program"] == self.PROG]
        self.assertEqual(len(waits), 1)
        self.assertEqual((waits[0]["version"], waits[0]["k"]), (2, None))
        self.assertIn("look 1 falls due at 2026-10-29, not final yet", waits[0]["why"])
        self.assertIn("the session after it (2026-10-30) has not had its open decision", waits[0]["why"])
        self.assertEqual(night["waiting"], len(night["waits"]))
        self.assertLessEqual(max(len(w["why"]) for w in night["waits"]), H.WHY_CHARS)

    def test_the_screen_after_the_open_needs_the_open_decision_and_its_window(self):
        self.night_of_x()
        with self.store() as st:
            passes(st, et(self.X, 20, 40), et(self.T, 9, 10))
            session = C.session(st, self.T)
            self.lane._open_checked = None
            self.assertIsNone(self.lane._screen_open_due(st, et(self.T, 9, 45), self.T, session, []),
                              "no open decision of Oct 30 made: nothing to screen after")
            decisions(st, self.T, self.T, kinds=("open",))
            soon: list[dt.datetime] = []
            self.assertIsNone(self.lane._screen_open_due(st, et(self.T, 9, 39), self.T, session, soon))
            self.assertIn(et(self.T, 9, 40), soon)
            self.assertIsNone(self.lane._screen_open_due(st, session.close_decide - H.SCREEN_CLEAR, self.T, session, []),
                              "never within 5 minutes of the close decision")
            self.assertIsNotNone(self.lane._screen_open_due(st, et(self.T, 9, 45), self.T, session, []))
            # PLANNING CHANGES NO STATE WHEN IT RETURNS THE TASK (the branch's check: `run` plans again after every
            # task and drops what that plan returns): a plan whose task is not run leaves it due for the next plan.
            self.assertIsNone(self.lane._open_checked)
            self.at(et(self.T, 9, 46))
            task = self.lane._screen_open_due(st, et(self.T, 9, 46), self.T, session, [])
            self.assertIsNotNone(task, "the task a dropped plan returned is returned again")
            status, out = self.lane._do(st, task)                     # it runs at 09:46: the 10-minute clock starts
            self.assertEqual((status, out["written"]), ("ok", 1))
            self.assertEqual(self.lane._open_checked, et(self.T, 9, 46))
            soon = []
            self.assertIsNone(self.lane._screen_open_due(st, et(self.T, 9, 50), self.T, session, soon),
                              "after a run the horizons are read at most every 10 minutes")
            self.assertIn(et(self.T, 9, 56), soon)
            soon = []
            self.assertIsNone(self.lane._screen_open_due(st, et(self.T, 9, 57), self.T, session, soon),
                              "the horizons have not moved since the run")
            self.assertEqual(self.lane._open_checked, et(self.T, 9, 57), "a check that found no change starts it too")
            soon = []
            self.assertIsNone(self.lane._screen_open_due(st, et(self.T, 10, 0), self.T, session, soon))
            self.assertIn(et(self.T, 10, 7), soon)
            self.assertIsNone(self.lane._screen_open_due(st, et(self.T, 10, 0), self.T, None, []), "no session")

    def test_a_screen_due_in_the_plan_after_a_record_pass_runs_at_the_next_turn(self):
        """The branch's check (a major): the record pass is due every 2 minutes, so the screen after the open often falls
        due in the plan `run` makes AFTER a task, whose task is dropped. Planning must not start the 10-minute clock
        then: the next turn runs the screen."""
        self.night_of_x()
        self.open_of_t()
        self.at(et(self.T, 9, 41))                     # no mark_recorded: the record pass is due on this turn
        ran = [self.turned() for _ in range(2)]
        self.assertEqual(ran[0], "record", ran)
        self.assertEqual(ran[1], H.SCREEN_OPEN_JOB, "the screen the plan after the record pass returned runs next")
        self.assertEqual(len(self.receipts(H.SCREEN_OPEN_JOB)), 1)
        self.assertEqual([(r["program"], r["k"]) for r in self.looks()], [(self.PROG, 1)])

    def test_the_seating_versions_alone_are_screened_after_the_open(self):
        self.night_of_x()
        self.open_of_t()
        calls = []
        real = SN.run

        def run(store, today, **kw):
            calls.append((today, kw.get("programs")))
            return real(store, today, **kw)
        self.at(et(self.T, 9, 41))
        self.mark_recorded()
        with mock.patch.object(SN, "run", run):
            self.assertEqual(self.turned(), H.SCREEN_OPEN_JOB)
        [(today, programs)] = calls
        self.assertEqual(today, self.T)
        self.assertEqual(sorted(programs), sorted((p.id, p.version) for p in P.SEATING))
        self.assertTrue(all(BA.seating().get(k) is not None for k in programs))


class TheNightIsTheSessions(TH.LaneCase):
    """The nightly score and screen are keyed on the SESSION (Tue Oct 20, 2026 here), not the calendar day."""

    D = dt.date(2026, 10, 20)

    def setUp(self):
        super().setUp()
        with self.store() as st:
            decisions(st, self.D, self.D)
            st.set_meta(SC.equity_key(self.D), repr(2000.0))
            st.set_meta("tickers@2026-10-21T11:00:05Z", st.meta("tickers@2026-10-20T11:00:05Z"))
            st.set_meta("evl:backfill:2026-10-19", "done")
            st.set_meta("evl:backfill:2026-10-20", "done")

    turned = ScreenAfterTheOpen.turned

    def nightly(self, job):
        """This test's `job` receipts (the fixture's Monday night ones left out): their summaries."""
        return [json.loads(r["summary"]) for r in self.receipts(job) if r["started_at"] >= S.iso(et(self.D, 0))]

    def test_a_score_that_overran_midnight_still_gets_its_screen_and_report(self):
        intents = [{"program": "EVL-ERN-READ-O1", "version": 2, "event": f"8k:invented-{n}"} for n in range(5)]
        settled = []

        def settle_one(st, gw, intent, *, now):
            settled.append(intent["event"])
            self.mono.advance(50)
            return "settled"
        nxt = self.D + dt.timedelta(days=1)
        with mock.patch.object(SC, "due", return_value=intents), mock.patch.object(SC, "settle_one", settle_one):
            self.at(et(self.D, 23, 58))          # the House came back late that evening
            self.mark_recorded()
            self.assertEqual(self.turned(), "score")
            self.assertEqual(len(settled), 3, "the score's bound: 3 of the 5 before midnight")
            self.at(et(nxt, 0, 3))               # Wed Oct 21, before its own 20:30 ET
            self.mark_recorded()
            self.assertEqual(self.turned(), "score", "the same night goes on")
            self.assertEqual(settled, [f"8k:invented-{n}" for n in range(5)], "each intent tried once a night")
            self.assertEqual([self.turned() for _ in range(2)], ["screen", "report"])
            for hh in (0, 7, 9, 13):
                self.at(et(nxt, hh, 30))
                self.mark_recorded()
                self.assertNotIn(self.turned(), ("score", "screen", "report"))
        self.assertEqual([(s["day"], s["complete"]) for s in self.nightly("score")],
                         [("2026-10-20", False), ("2026-10-20", True)])
        self.assertEqual([(s["day"], s["run"]) for s in self.nightly("screen")], [("2026-10-20", "night")],
                         "Tuesday's screen, once, after midnight")
        self.assertEqual([s["day"] for s in self.nightly("report")], ["2026-10-20"])
        self.assertTrue((self.root / "reports" / "2026-10-20.txt").exists())
        self.assertFalse((self.root / "reports" / "2026-10-21.txt").exists(), "Wednesday's report waits for its night")

    def test_a_night_the_house_missed_is_made_the_next_morning_clear_of_the_open_decision(self):
        nxt = self.D + dt.timedelta(days=1)
        self.at(et(nxt, 9, 11))                  # no score, screen or report of Tuesday's night at all
        self.mark_recorded()
        tasks = [self.turned() for _ in range(4)]
        self.assertIn("score", tasks)
        self.assertNotIn("screen", tasks, "no screen within 5 minutes of a decision")
        self.assertEqual([s["day"] for s in self.nightly("score")], ["2026-10-20"])
        self.assertEqual(self.nightly("screen"), [])
        with self.store() as st:
            decisions(st, nxt, nxt, kinds=("open",))
        self.at(et(nxt, 9, 17))
        self.mark_recorded()
        tasks = [self.turned() for _ in range(3)]
        self.assertEqual(tasks[:2], ["screen", "report"])
        self.assertEqual([s["day"] for s in self.nightly("screen")], ["2026-10-20"])

    def test_the_night_is_todays_session_from_2030_and_the_one_before_until_then(self):
        with self.store() as st:
            self.assertEqual(self.lane._night(st, et(self.D, 20, 29), self.D, C.session(st, self.D), []),
                             dt.date(2026, 10, 19))
            self.assertEqual(self.lane._night(st, et(self.D, 20, 30), self.D, C.session(st, self.D), []), self.D)
            sat = dt.date(2026, 10, 24)
            self.assertEqual(self.lane._night(st, et(sat, 21, 0), sat, None, []), dt.date(2026, 10, 23))


# --------------------------------------------------------------------------------------------- the House's event book
class TheCloseDecisionReadsTheBandsAgain(EventTest):
    """EVL-ERN-REACT-ON v2 (close entry, exit at the next open): its look 1 falls due as of Fri Oct 30's close (80
    invented events entered Oct 20-29) and A66 makes that close final once Wed Nov 4's open decision is made. On Nov 4
    an earnings 8-K at 11:00 ET with a +5% 15:29 ET reaction is wanted at the close by EVL-ERN-REACT-C1 (the earlier
    row) and EVL-ERN-REACT-ON: at learning the earlier row is given it, at Probe REACT-ON is (ROOM)."""

    REACT = "EVL-ERN-REACT-ON"

    def setUp(self):
        super().setUp()
        self.h = h = self.harness()
        st = h.lane.st
        entries = [s.day for s in C.sessions(st, dt.date(2026, 10, 20), dt.date(2026, 10, 29))]
        settle(st, self.REACT, entries, 10, 0.01)
        decisions(st, dt.date(2026, 10, 19), PRIOR)
        backfilled(st, dt.date(2026, 10, 15), PRIOR)
        h.lane.filing("r-1", CIK, accepted=iso(DAY, 11, 0), received=iso(DAY, 11, 1))
        h.lane.universe(DAY, "ACME", CIK, 16.0)
        st.db.execute("INSERT INTO bars(symbol, day, adj, o, h, l, c, v, fetched_at) VALUES('ACME', ?, 'raw', 16, 16, 16, "
                      "16.0, 1e6, 'x')", (PRIOR.isoformat(),))
        st.db.execute("INSERT INTO marks(symbol, day, label, px, t, source, fetched_at) VALUES('ACME', ?, '1530', 16.8, "
                      "'x', 'sip-1min', 'x')", (DAY.isoformat(),))
        self.ready(h)
        h.symbol("ACME", last=16.8)
        h.venue.prints[("ACME", DAY.isoformat(), "close")] = D("17.00")

    def lanes_screen_at_ten(self):
        """The House's lane at 10:00 ET of DAY: its screen after the open (house.py `_screen_open_due`, then the task)."""
        h = self.h
        h.clock.set(at(DAY, 10, 0, 0))
        lane = H.EventLane(TH.FakeHouse(h.clock), self.root / "events", gateway=TH.FakeGateway(), sec=TH.FakeSEC())
        st = h.lane.st
        task = lane._screen_open_due(st, lane.now(), DAY, C.session(st, DAY), [])
        self.assertIsNotNone(task, "Nov 4's open made Oct 30's close final: the horizon moved")
        status, out = lane._do(st, task)
        self.assertEqual((status, out["written"]), ("ok", 1))
        return out

    def close_buy(self):
        h = self.h
        for hh, mm in ((15, 46), (15, 47)):
            h.tick(hh, mm)
        [buy] = [r for r in h.event_intents("buy") if r["status"] != "refused"]
        decision = json.loads(h.state.rows("SELECT summary FROM eq_event_decisions WHERE at='close'")[0]["summary"])
        return buy, h.bodies()[-1], decision

    def test_a_look_written_at_ten_makes_that_days_close_decision_use_the_probe_band(self):
        h = self.h
        h.tick(9, 15)                                     # the open decision: the session's first band sync
        self.assertEqual(h.state.rows("SELECT band FROM eq_event_programs WHERE program=? AND version=2",
                                      (self.REACT,))[0]["band"], "learning")
        out = self.lanes_screen_at_ten()
        self.assertEqual(out["looks"], [{"program": self.REACT, "version": 2, "k": 1, "held": 1, "passed": 1,
                                         "band": "probe"}])
        buy, body, decision = self.close_buy()
        self.assertEqual((buy["program"], buy["band"], buy["tif"]), (self.REACT, "probe", "cls"))
        whole = (EB.settings().share("probe") * D("2000") / D("20.00")).to_integral_value(rounding="ROUND_DOWN")
        self.assertEqual((body["symbol"], body["qty"], body["time_in_force"]), ("ACME", str(whole), "cls"),
                         "Probe's share of E (3.5%: A86 REVISED) at the close of the day its look was written")
        self.assertEqual(decision["band_sync"], "moved")
        self.assertEqual(h.state.rows("SELECT band FROM eq_event_programs WHERE program=? AND version=2",
                                      (self.REACT,))[0]["band"], "probe")
        self.assertEqual(h.state.get("eq_event_band_mark"), 1, "the mark the close's sync read (0 at the open's)")
        self.assertTrue(any(f"{self.REACT} v2 is now probe" in text for _, text in h.alerts))
        self.assertTrue(any(k == "equity.band" and p.get("to") == "probe" for k, p in h.events))

    def test_with_no_move_the_close_decision_keeps_the_mornings_bands(self):
        h = self.h
        calls = []
        real = h.book._event_sync

        def sync(*a, **kw):
            calls.append(a[-1] is not None)
            return real(*a, **kw)
        with mock.patch.object(h.book, "_event_sync", sync):
            h.tick(9, 15)
            buy, body, decision = self.close_buy()
        self.assertEqual(len(calls), 1, "once a session, at its first decision")
        self.assertEqual((buy["program"], buy["band"]), ("EVL-ERN-REACT-C1", "learning"), "the earlier row at learning")
        self.assertEqual((body["symbol"], body["qty"]), ("ACME", "2"))
        self.assertNotIn("band_sync", decision)
        open_decision = json.loads(h.state.rows("SELECT summary FROM eq_event_decisions WHERE at='open'")[0]["summary"])
        self.assertEqual(open_decision["band_sync"], "first")

    def test_a_mark_that_cannot_be_read_reads_the_bands_again(self):
        h = self.h
        h.tick(9, 15)
        with mock.patch.object(EB, "band_mark", return_value=None):
            _, _, decision = self.close_buy()
        self.assertEqual((decision["band_sync"], decision["bands"]), ("moved", True))

    def test_the_next_sessions_open_reads_the_bands_as_its_first_decision(self):
        h = self.h
        h.tick(9, 15)
        h.tick(15, 46)
        self.assertEqual(h.book._event_bands_due(DAY.isoformat(), "close", EB, h.book._event_lane_store()), None)
        self.assertEqual(h.book._event_bands_due(NEXT.isoformat(), "open", EB, h.book._event_lane_store()), "first")


class TheBandMark(EventTest):
    def test_the_newest_band_history_id_or_zero_or_none(self):
        h = self.harness()
        self.assertEqual(EB.band_mark(None), 0, "no lane")
        lane = EB.open_lane(self.root)
        self.addCleanup(lane.close)
        self.assertEqual(EB.band_mark(lane), 0, "no row")
        BA.set_band(h.lane.st, "EVL-8K-READ-O1", 2, "probe", since="2026-11-03T21:00:00Z", why="look 1 passed",
                    now=dt.datetime(2026, 11, 4, 15, tzinfo=UTC))
        BA.set_band(h.lane.st, "EVL-8K-READ-O1", 2, "learning", since="2026-11-04T21:00:00Z", why="demoted",
                    now=dt.datetime(2026, 11, 5, 2, tzinfo=UTC))
        self.assertEqual(EB.band_mark(lane), 2)
        h.lane.st.db.execute("DROP TABLE band_history")
        self.assertEqual(EB.band_mark(lane), 0, "a store from before PREREG-EVL-3")

    def test_an_unreadable_table_is_none(self):
        class Broken:
            class db:  # noqa: N801 - the Lane's shape
                @staticmethod
                def execute(sql, *args):
                    import sqlite3

                    if "sqlite_master" in sql:
                        return [("band_history",)]
                    raise sqlite3.DatabaseError("malformed")
        self.assertIsNone(EB.band_mark(Broken()))



class TheIndexAfterAnSecHoliday(unittest.TestCase):
    """Release 1019f's review (lens judges, a major): EDGAR dates an 8-K accepted after 17:30 ET as filed on the next
    day it is open, so on an SEC holiday NYSE trades (Wed Nov 11, 2026, Veterans Day) the 8-Ks accepted after 17:30 ET
    of Tue Nov 10, events of Nov 11's open decision, are in Thu Nov 12's daily index; Nov 10's does not list them and
    Nov 11 has none. The holiday's backfill is done (fix/backfill-robust), so a close on the holiday is final, by A69's
    fast path or by A66's three sessions, only once Nov 12's backfill has run too (league/events/screen.py
    `index_through`); an ordinary close still waits for its own index alone."""

    from league.tests import test_events_1019c as _T19C   # (the module, so its own tests are not collected again here)
    from league.tests import test_events_review_1019b as _R19B

    setUp, tearDown, settle = _R19B.LooksOnAFinalRecord.setUp, _R19B.LooksOnAFinalRecord.tearDown, \
        _R19B.LooksOnAFinalRecord.settle
    passes, written = _T19C.TheFastPath.passes, _T19C.TheFastPath.written
    P = "EVL-INS-BUY-O1"
    HOLIDAY, AFTER = dt.date(2026, 11, 11), dt.date(2026, 11, 12)

    def due_at_the_holiday(self) -> None:
        """Look 1 of INS-BUY-O1 v2 falls due at the holiday's close (80 events over the 8 sessions through it)."""
        i = self.days.index(self.HOLIDAY)
        self.settle(self.P, 2, 10, self.days[i - 7:i + 1], lambda n: 0.01)

    def test_the_index_through_a_session(self):
        cases = {dt.date(2026, 11, 10): dt.date(2026, 11, 10), dt.date(2026, 11, 11): dt.date(2026, 11, 12),
                 dt.date(2026, 10, 12): dt.date(2026, 10, 13), dt.date(2027, 10, 11): dt.date(2027, 10, 12),
                 dt.date(2027, 11, 11): dt.date(2027, 11, 12), dt.date(2026, 7, 3): dt.date(2026, 7, 6),
                 dt.date(2027, 12, 31): dt.date(2028, 1, 3), dt.date(2026, 11, 27): dt.date(2026, 11, 27),
                 dt.date(2026, 4, 3): dt.date(2026, 4, 3)}        # (Good Friday: NYSE shut, EDGAR open)
        for day, last in cases.items():
            self.assertEqual(SN.index_through(day), last, day)

    def test_the_house_takes_the_judges_table_and_the_judge_reads_a_day_only_the_house_lists(self):
        self.assertIs(H.SEC_HOLIDAYS, SN.SEC_HOLIDAYS)
        eve = dt.date(2026, 12, 24)
        self.assertEqual(SN.index_through(eve), eve)
        with mock.patch.object(H, "SEC_HOLIDAYS", {**SN.SEC_HOLIDAYS, eve: "Christmas Eve, by executive order"}):
            self.assertEqual(SN.index_through(eve), dt.date(2026, 12, 28), "Dec 25 a holiday, then the weekend")

    def test_the_fast_path_makes_the_holiday_final_only_after_the_index_that_holds_its_eve(self):
        self.due_at_the_holiday()
        now = final_record(self.st, self.AFTER, wall=dt.time(9, 40))
        self.st.db.execute("DELETE FROM meta WHERE key=?", (f"evl:backfill:{self.AFTER.isoformat()}",))  # (05:00 Nov 13)
        self.st.db.execute("DELETE FROM receipts WHERE job=?", (f"decide-close:{self.AFTER.isoformat()}",))
        self.assertEqual(self.st.meta(f"evl:backfill:{self.HOLIDAY.isoformat()}"), "done", "the holiday's own")
        self.passes(et(self.days[0], 8), et(self.AFTER, 9, 30))
        horizon, why = SN.final_until(self.st, self.P, 2, self.AFTER, now)
        self.assertEqual(horizon, dt.date(2026, 11, 10), why)
        self.assertIn("the fast path (A69) stops at 2026-11-11: the daily-index backfill of 2026-11-12 has not run "
                      "(its index holds the 8-Ks of 2026-11-10's evening: 2026-11-11 is an SEC holiday)", why)
        out = SN.run(self.st, self.AFTER, draws=999, now=now)
        self.assertEqual(out["written"], [], "no look as of the holiday before its eve's index is backfilled")
        self.st.set_meta(f"evl:backfill:{self.AFTER.isoformat()}", "done")
        later = et(dt.date(2026, 11, 13), 5, 10)
        self.assertEqual(SN.final_until(self.st, self.P, 2, dt.date(2026, 11, 13), later)[0], self.HOLIDAY)
        out = SN.run(self.st, dt.date(2026, 11, 13), draws=999, now=later)
        self.assertEqual(self.written(out), [(self.P, 1)])
        self.assertEqual(SN.look_rows(self.st, self.P, 2)[0]["at"][:10], self.HOLIDAY.isoformat(), "the as-of date")

    def test_on_an_ordinary_day_the_close_waits_for_its_own_index_alone(self):
        x, y = dt.date(2026, 11, 9), dt.date(2026, 11, 10)
        i = self.days.index(x)
        self.settle(self.P, 2, 10, self.days[i - 7:i + 1], lambda n: 0.01)
        now = final_record(self.st, y, wall=dt.time(9, 40))
        self.st.db.execute("DELETE FROM meta WHERE key=?", (f"evl:backfill:{y.isoformat()}",))
        self.st.db.execute("DELETE FROM receipts WHERE job=?", (f"decide-close:{y.isoformat()}",))
        self.passes(et(self.days[0], 8), et(y, 9, 30))
        horizon, why = SN.final_until(self.st, self.P, 2, y, now)
        self.assertEqual(horizon, x, "Nov 10's index (not yet read) holds none of Nov 9's windows")
        self.assertEqual(self.written(SN.run(self.st, y, draws=999, now=now)), [(self.P, 1)])

    def test_a66_holds_the_holiday_until_the_index_that_holds_its_eve(self):
        self.due_at_the_holiday()
        monday = dt.date(2026, 11, 16)
        now = final_record(self.st, monday, wall=dt.time(9, 40))   # (no record pass on record: A66 alone)
        self.st.db.execute("DELETE FROM meta WHERE key=?", (f"evl:backfill:{self.AFTER.isoformat()}",))
        horizon, why = SN.final_until(self.st, self.P, 2, monday, now)
        self.assertEqual(horizon, dt.date(2026, 11, 10), why)
        self.assertIn("the daily-index backfill of 2026-11-12 has not run", why)
        self.assertEqual(SN.run(self.st, monday, draws=999, now=now)["written"], [])
        self.st.set_meta(f"evl:backfill:{self.AFTER.isoformat()}", "done")
        self.assertEqual(SN.final_until(self.st, self.P, 2, monday, now)[0], self.HOLIDAY, "A66's three sessions")
        self.assertEqual(self.written(SN.run(self.st, monday, draws=999, now=now)), [(self.P, 1)])

    def test_a66_on_the_day_after_the_holiday_holds_both(self):
        """Nov 12's index holds the windows of the holiday and of Nov 12: with it not backfilled, A66 at Nov 17's open
        (its horizon Nov 12) falls back to Nov 10, before the holiday, as the fast path does."""
        self.due_at_the_holiday()
        tuesday = dt.date(2026, 11, 17)
        now = final_record(self.st, tuesday, wall=dt.time(9, 40))
        self.st.db.execute("DELETE FROM meta WHERE key=?", (f"evl:backfill:{self.AFTER.isoformat()}",))
        horizon, why = SN.final_until(self.st, self.P, 2, tuesday, now)
        self.assertEqual(horizon, dt.date(2026, 11, 10), why)


# PREREG-EVL-7 (A125 pinned REGISTERED_AT_7): this module's tests are of mechanisms written before the learners
# registered and run on the registries without them (league/tests/evl7_fakes.py); the learners' own effects on these
# paths are league/tests/test_events_evl7.py's and test_events_evl7_fix.py's.
from league.tests.evl7_fakes import setUpModule, tearDownModule  # noqa: E402,F401

if __name__ == "__main__":
    unittest.main()
