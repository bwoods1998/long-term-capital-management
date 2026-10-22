"""PREREG-EVL-3 (registered 2026-10-19T05:23:06Z): version 2 of the nine seatable programs, real money at learning size
from birth, bands moved by looks counted in settled events and by real fills. Synthetic data only."""

import datetime as dt
import tempfile
import unittest

from league.tests.evl6_fakes import on_1019h
from league.events import bands as BA
from league.events import calendar as C
from league.events import programs as P
from league.events import score as SCORE
from league.events import screen as SC
from league.events import store as S
from league.tests.test_events_run import FakeGateway
from league.tests.test_events_screen import final_record

UTC = dt.timezone.utc
NINE = ("EVL-ERN-READ-O1", "EVL-ERN-REACT-C1", "EVL-8K-READ-O1", "EVL-NEWS-READ-O1", "EVL-ERN-REACT-ON",
        "EVL-ERN-GUIDE-O1", "EVL-INS-BUY-O1", "EVL-NEWS-READ-ON", "EVL-NEWS-REACT-ON")


@on_1019h
class V2Test(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.st = S.Store(self.tmp.name)
        C.refresh(self.st, FakeGateway({}), dt.date(2026, 10, 1), dt.date(2027, 3, 31))
        self.days = [s.day for s in C.sessions(self.st, dt.date(2026, 10, 20), dt.date(2027, 3, 31))]

    def tearDown(self):
        self.st.close()
        self.tmp.cleanup()

    # -------------------------------------------------------------------------------------------- the rows
    def test_version_two_rows_seat_and_version_one_never_does(self):
        self.assertEqual(P.REGISTERED_AT_3, "2026-10-19T05:23:06Z")
        v2 = [p for p in P.PROGRAMS if p.version == 2]
        self.assertEqual(tuple(p.id for p in v2), NINE)
        for p in v2:
            v1 = P.BY_KEY[(p.id, 1)]
            self.assertEqual((p.family, p.entry_at, p.exit_at, p.hold, p.reads, p.rule),
                             (v1.family, v1.entry_at, v1.exit_at, v1.hold, v1.reads, v1.rule))
            self.assertTrue(p.can_seat and p.prereg == 3)
            self.assertFalse(v1.can_seat)
            self.assertEqual(p.registered_at, dt.datetime(2026, 10, 19, 5, 23, 6, tzinfo=UTC))
        # PREREG-EVL-4's three seat at their version 1 beside the nine (their ids are new: its section 2)
        self.assertEqual(sorted((p.id, p.version) for p in P.SEATING),
                         sorted([(i, 2) for i in NINE] + [(i, 1) for i in ("EVL-8K-REACT-ON", "EVL-8K-READ-ON",
                                                                           "EVL-NEWSPM-READ-ON", "EVL-ERN-DROP-ON",
                                                                           "EVL-ERN-UNDER-ON", "EVL-NEWS-NIGHT2-ON")]))
        self.assertTrue(all(p.version == 1 for p in P.BY_ID.values()))
        self.assertEqual(SC.expected_false_passes(self.st)["versions"], 15)
        self.assertEqual(SC.expected_false_passes(self.st)["expected"], 1.95)    # (release 1019i: PREREG-EVL-6 section 5 restates the count, 0.13 a version or run of 3.9)

    def test_registration_gates_version_two(self):
        row = {"accession": "0000000001-26-000009", "cik": "0000000001", "items": '["2.02"]',
               "knowable_at": "2026-10-19T05:20:00Z"}
        uni = {"symbol": "AAA"}
        v1, v2 = P.BY_KEY[("EVL-CTRL-ERN-ALL-O1", 1)], P.BY_KEY[("EVL-INS-BUY-O1", 2)]
        self.assertEqual(len(P.select(v1, [row], eligible=lambda c: uni, verdict=lambda r: None)), 1)
        buy = dict(row, knowable_at="2026-10-19T05:23:06Z", accession="0000000001-26-000010")
        self.assertEqual(P.select(v2, [buy], eligible=lambda c: uni, verdict=lambda r: None), [])  # at registration
        later = dict(buy, knowable_at="2026-10-19T05:23:07Z")
        self.assertEqual(len(P.select(v2, [later], eligible=lambda c: uni, verdict=lambda r: None)), 1)

    def test_the_limit_at_entry_binds_every_version_two(self):
        uni = {"prev_close": 10.0}
        self.assertTrue(SCORE._above_limit({"program": "EVL-ERN-REACT-C1", "version": 2}, uni, 12.6))
        self.assertFalse(SCORE._above_limit({"program": "EVL-ERN-REACT-C1", "version": 1}, uni, 12.6))
        self.assertTrue(SCORE._above_limit({"program": "EVL-ERN-READ-O1", "version": 2}, uni, 12.6))

    # -------------------------------------------------------------------------------------------- the looks
    def _settle(self, program, version, per_day, days, a_of, issuers=None, start=0):
        """Synthetic settled one-session events: per_day events on each of `days` sessions, abnormal return a_of(i)."""
        n = start
        for d in days:
            for _ in range(per_day):
                ev = f"syn:{program}:{version}:{n}"
                cik = f"{(n % (issuers or 10_000)):010d}"
                a = a_of(n)
                self.st.db.execute("INSERT INTO intents(program, version, event, symbol, cik, decided_at, entry_day, entry_at, "
                                   "exit_day, exit_at, rank_key, mode, status, why) VALUES(?, ?, ?, 'S', ?, 'z', ?, 'open', "
                                   "?, 'close', NULL, 'shadow', 'exited', NULL)", (program, version, ev, cik, d.isoformat(),
                                                                                   d.isoformat()))
                self.st.db.execute("INSERT INTO outcomes(program, version, event, entry_px, exit_px, bench, bench_entry, "
                                   "bench_exit, cost_entry_bp, cost_exit_bp, r, b, a, tradable, settled_at, status) "
                                   "VALUES(?, ?, ?, 10, 10, 'SPY', 1, 1, 5, 5, ?, 0, ?, 1, 'z', 'settled')",
                                   (program, version, ev, a, a))
                n += 1
        return n

    def test_looks_are_counted_in_events_with_issuer_and_block_minimums_and_merge(self):
        days = self.days[:20]
        self._settle("EVL-INS-BUY-O1", 2, 40, days, lambda i: 0.001)
        rows = SC.settled_rows(self.st, "EVL-INS-BUY-O1", 2)
        plan = SC.v2_schedule(self.st, rows, days[-1])
        # 40 a session: 60 events by session 2, but 8 blocks only at session 8 (320 events): looks 1-5 are one look
        self.assertEqual(plan["looks"][0], (1, days[7], [2, 3, 4, 5]))
        self.assertEqual(plan["looks"][1], (6, days[11], []))       # 450 by session 12 (480)
        self.assertEqual(plan["looks"][2], (7, days[16], []))       # 675 by session 17 (680)
        self.assertEqual(len(plan["looks"]), 3)

    def test_too_few_issuers_hold_no_look_and_an_unsettled_exit_stops_the_scan(self):
        days = self.days[:12]
        self._settle("EVL-INS-BUY-O1", 2, 20, days, lambda i: 0.001, issuers=30)
        rows = SC.settled_rows(self.st, "EVL-INS-BUY-O1", 2)
        self.assertEqual(SC.v2_schedule(self.st, rows, days[-1])["looks"], [])
        plan = SC.v2_schedule(self.st, rows, days[-1], pending=[(days[2], days[3])])
        self.assertEqual(plan["stopped"], days[3])

    def test_a_pass_promotes_to_probe_and_a_loser_is_retired(self):
        days = self.days[:8]
        self._settle("EVL-INS-BUY-O1", 2, 10, days, lambda i: 0.01)            # every block +1%: a pass at 80 events
        self._settle("EVL-ERN-REACT-ON", 2, 10, days, lambda i: -0.01)         # every block -1%: retired
        # (the look as of days[-1] is computed once that close is final: three later sessions decided, release 1019b)
        now = final_record(self.st, self.days[10])
        out = SC.run(self.st, self.days[10], draws=999, now=now)
        by = {(w["program"], w["k"]): w for w in out["written"]}
        win = by[("EVL-INS-BUY-O1", 1)]
        self.assertEqual((win["held"], win["passed"], win["alpha"], win["band"]), (1, 1, 0.018, "probe"))
        lose = by[("EVL-ERN-REACT-ON", 1)]
        self.assertEqual((lose["passed"], lose["band"]), (0, "retired"))
        bands = BA.bands(self.st)
        self.assertEqual(bands[("EVL-INS-BUY-O1", 2)], "probe")
        self.assertEqual(bands[("EVL-ERN-REACT-ON", 2)], "retired")
        self.assertEqual(bands[("EVL-ERN-READ-O1", 2)], "learning")
        detail = SC.look_detail(self.st, "EVL-INS-BUY-O1", 2, 1)
        self.assertEqual(detail["skew"]["session"]["seed"], "EVL-INS-BUY-O1|v2|look1")
        self.assertLessEqual(detail["skew"]["session"]["alpha"], 0.018)
        # a retired program never moves again; a version 1 program has no band
        self.assertFalse(BA.set_band(self.st, "EVL-ERN-REACT-ON", 2, "probe", since="x", why="y"))
        with self.assertRaises(ValueError):
            BA.set_band(self.st, "EVL-INS-BUY-O1", 1, "probe", since="x", why="y")
        self.assertEqual(SC.run(self.st, self.days[10], draws=999, now=now)["written"], [])   # written once

    # -------------------------------------------------------------------------------------------- real fills
    def _fills(self, program, n, pnl_each, band="probe", start=0):
        for i in range(start, start + n):
            d = self.days[i % len(self.days)]
            ev = f"real:{i}"
            self.st.db.execute("INSERT OR IGNORE INTO intents(program, version, event, symbol, cik, decided_at, entry_day, "
                               "entry_at, exit_day, exit_at, rank_key, mode, status, why) VALUES(?, 2, ?, 'S', ?, 'z', ?, "
                               "'open', ?, 'close', NULL, 'shadow', 'exited', NULL)",
                               (program, ev, f"{i:010d}", d.isoformat(), d.isoformat()))
            BA.record_fill(self.st, program=program, version=2, event=ev, side="buy", qty=10, price=10.0, fee=0.0,
                           filled_at=f"{d.isoformat()}T13:30:00Z", band=band)
            BA.record_fill(self.st, program=program, version=2, event=ev, side="sell", qty=10, price=10.0 + pnl_each / 10,
                           fee=0.0, filled_at=f"{d.isoformat()}T20:00:00Z", band=band)

    def test_real_fills_demote_and_size(self):
        BA.set_band(self.st, "EVL-ERN-READ-O1", 2, "probe", since="x", why="look 1 passed")
        self._fills("EVL-ERN-READ-O1", 50, -3.5)                                # -$175 over the last 50
        self.assertFalse(BA.record_fill(self.st, program="EVL-ERN-READ-O1", version=2, event="real:0", side="buy",
                                        qty=10, price=10.0, fee=0.0, filled_at="z", band="probe"))   # idempotent
        changes = BA.review(self.st)
        self.assertEqual([c["band"] for c in changes], ["learning"])
        self.assertEqual(BA.bands(self.st)[("EVL-ERN-READ-O1", 2)], "learning")
        BA.set_band(self.st, "EVL-8K-READ-O1", 2, "probe", since="x", why="look 1 passed")
        self._fills("EVL-8K-READ-O1", 160, 0.5)                                  # +5% each: the bound is above zero
        self.assertEqual([c["band"] for c in BA.review(self.st)], ["sized"])
        self.assertEqual(BA.bands(self.st)[("EVL-8K-READ-O1", 2)], "sized")
        events = BA.real_events(self.st, "EVL-8K-READ-O1", 2)
        self.assertEqual(len(events), 160)
        self.assertAlmostEqual(events[0]["r"], 0.005)


if __name__ == "__main__":
    unittest.main()
