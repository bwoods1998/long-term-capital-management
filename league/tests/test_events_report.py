"""The event lane's daily report (league.events.report) on a synthetic store: counts and summary statistics only."""

import datetime as dt
import json
import tempfile
import unittest

from league.tests.evl6_fakes import on_1019h
from league.events import calendar as C
from league.events import report as R
from league.events import screen as SC
from league.events import store as S

UTC = dt.timezone.utc
DAY = dt.date(2026, 10, 20)  # a Tuesday


class Calendar:
    def get_json(self, path, params=None):
        start, end = dt.date.fromisoformat(params["start"]), dt.date.fromisoformat(params["end"])
        out, d = [], start
        while d <= end:
            if d.weekday() < 5:
                out.append({"date": d.isoformat(), "open": "09:30", "close": "16:00"})
            d += dt.timedelta(days=1)
        return out


def et(day, hhmm):
    h, m = (int(x) for x in hhmm.split(":"))
    return S.iso(dt.datetime.combine(day, dt.time(h, m), tzinfo=C.NY))


@on_1019h
class ReportTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.st = S.Store(self.tmp.name)
        C.refresh(self.st, Calendar(), dt.date(2026, 10, 1), dt.date(2026, 12, 31))
        db = self.st.db
        with self.st.tx():
            filings = [("0001-26-000001", "8-K", '["2.02", "9.01"]', "fetched", DAY),
                       ("0001-26-000002", "8-K", '["2.02"]', "failed:EdgarError:no Accepted time", DAY),
                       ("0001-26-000003", "8-K", '["8.01"]', "fetched", DAY),
                       ("0001-26-000004", "8-K", '["1.01"]', "listed", DAY),
                       ("0001-26-000005", "4", "[]", "fetched", DAY),
                       ("0001-26-000006", "4", "[]", "fetched", DAY),
                       ("0001-26-000007", "8-K", '["2.02"]', "fetched", DAY - dt.timedelta(days=1))]
            for acc, form, items, status, day in filings:
                db.execute("INSERT INTO filings(accession, form, cik, items, accepted_at, knowable_at, received_at, source, "
                           "status) VALUES(?, ?, '0000000001', ?, ?, ?, ?, 'current', ?)",
                           (acc, form, items, et(day, "08:01"), et(day, "08:11"), et(day, "08:03"), status))
            news = [("1", "ACME SURGES ON MIRACLE CURE", 1, DAY), ("2", "Other headline", 1, DAY),
                    ("3", "Backfilled headline", 0, DAY), ("4", "Yesterday", 1, DAY - dt.timedelta(days=1))]
            for nid, headline, live, day in news:
                db.execute("INSERT INTO news(id, created_at, received_at, knowable_at, source, headline, summary, symbols, "
                           "live) VALUES(?, ?, ?, ?, 'benzinga', ?, 'secret summary', '[\"ACME\"]', ?)",
                           (nid, et(day, "07:00"), et(day, "07:01"), et(day, "07:02"), headline, live))
            for event, status, usd in (("8k:a", "ok", 0.004), ("8k:b", "ok", 0.006), ("8k:c", "unparsed", 0.003),
                                       ("8k:d", "failed:timeout", 0.0)):
                db.execute("INSERT INTO verdicts(event, prompt_sha, model, asked_at, answered_at, status, usd) VALUES(?, "
                           "'p', 'claude-haiku-4-5-20251001', ?, ?, ?, ?)", (event, et(DAY, "08:20"), et(DAY, "08:21"),
                                                                             status, usd))
            intents = [("EVL-ERN-READ-O1", "8k:a", "ACME", "exited", 0.012, 0.010, 1),
                       ("EVL-ERN-READ-O1", "8k:b", "BETA", "exited", -0.004, -0.006, 1),
                       ("EVL-ERN-READ-O1", "8k:c", "GAMA", "exited", 0.002, 0.001, None),
                       ("EVL-ERN-READ-O1", "8k:d", "DELT", "skipped:issuer-held", None, None, None),
                       ("EVL-ERN-READ-O1", "8k:e", "EPSI", "planned", None, None, None),
                       ("EVL-ERN-READ-O3", "8k:a", "ACME", "planned", None, None, None)]
            for i, (prog, ev, sym, status, r, a, trad) in enumerate(intents):
                exit_day = DAY if prog.endswith("O1") else dt.date(2026, 10, 22)
                db.execute("INSERT INTO intents(program, version, event, symbol, cik, decided_at, entry_day, entry_at, "
                           "exit_day, exit_at, mode, status) VALUES(?, 1, ?, ?, ?, ?, ?, 'open', ?, 'close', 'shadow', ?)",
                           (prog, ev, sym, f"{i:010d}", et(DAY, "09:15"), DAY.isoformat(), exit_day.isoformat(), status))
                if r is not None:
                    db.execute("INSERT INTO outcomes(program, version, event, entry_px, exit_px, bench, r, b, a, tradable, "
                               "settled_at, status) VALUES(?, 1, ?, 123.45, 124.56, 'SPY', ?, ?, ?, ?, ?, 'settled')",
                               (prog, ev, r, r - a, a, trad, et(DAY, "20:31")))
            db.execute("INSERT INTO marks(symbol, day, label, px, t, source, fetched_at) VALUES('ACME', ?, 'open', 123.45, "
                       "'x', 'sip:N:O', 'x')", (DAY.isoformat(),))
            db.execute("INSERT INTO bars(symbol, day, adj, o, c, fetched_at) VALUES('ACME', ?, 'raw', 123.40, 124.50, 'x')",
                       (DAY.isoformat(),))
            receipts = [("record", "06:00", "ok"), ("record", "06:02", "ok"), ("universe", "07:30", "ok"),
                        ("decide-open:2026-10-20", "09:15", "failed"), ("verdicts", "06:10", "running"),
                        ("score", "20:30", "running")]
            for job, hhmm, status in receipts:
                db.execute("INSERT INTO receipts(job, started_at, finished_at, status, summary) VALUES(?, ?, ?, ?, "
                           "'{\"symbols\": [\"ACME\"]}')", (job, et(DAY, hhmm),
                                                           None if status == "running" else et(DAY, hhmm), status))
        self.now = dt.datetime.combine(DAY, dt.time(21, 40), tzinfo=C.NY)

    def tearDown(self):
        self.st.close()
        self.tmp.cleanup()

    def test_the_report_counts_the_day(self):
        rep = R.build(self.st, DAY, now=self.now)
        ev = rep["events"]
        self.assertEqual(ev["8-K 2.02"], {"total": 2, "fetched": 1, "failed": 1, "pending": 0})
        self.assertEqual(ev["8-K other"], {"total": 2, "fetched": 1, "failed": 0, "pending": 1})
        self.assertEqual(ev["Form 4"]["fetched"], 2)
        self.assertEqual(ev["news"], {"total": 3, "live": 2, "backfilled": 1})
        self.assertEqual(ev["recorded_today"], 9)
        vd = rep["verdicts"]
        self.assertEqual((vd["ok"]["n"], vd["ok"]["usd"], vd["unparsed"]["n"], vd["refused"]["n"], vd["failed"]["n"]),
                         (2, 0.01, 1, 0, 1))
        progs = {p["program"]: p for p in rep["programs"]}
        o1 = progs["EVL-ERN-READ-O1"]
        self.assertEqual(o1["intents_today"], {"planned": 1, "entered": 0, "skipped": 1, "exited": 3})
        st = o1["settled"]
        self.assertEqual((st["n"], st["n_tradable"], st["issuers"], st["sessions"]), (3, 2, 3, 1))
        self.assertAlmostEqual(st["mean_a"], (0.010 - 0.006 + 0.001) / 3, places=15)
        self.assertAlmostEqual(st["mean_a_tradable"], 0.002, places=15)
        self.assertEqual(o1["next_look"]["status"], "upcoming")
        self.assertEqual((o1["next_look"]["k"], o1["next_look"]["at_sessions"]), (1, 10))
        self.assertFalse(progs["EVL-ERN-READ-O3"]["seatable"])
        self.assertEqual(progs["EVL-ERN-READ-O3"]["next_look"]["status"], "a record: never screened")
        self.assertIn("EVL-NEWS-READ-O1", rep["registered_without_intents"])
        self.assertEqual(rep["gaps"]["entry"]["n"], 1)
        self.assertAlmostEqual(rep["gaps"]["entry"]["mean_bp"], (123.45 / 123.40 - 1) * 1e4, places=9)
        # (release 1019i: PREREG-EVL-6 section 5 restates the count, 0.13 a version or run of 3.9, three ways)
        self.assertEqual(rep["expected_false_passes"],
                         {"versions": 15, "runs": 0, "waiting": 0, "charge": 0.13, "expected": 1.95, "budget": 3.9,
                          "left": 1.95, "left_after_waiting": 1.95, "base": 0.45, "stress": 2.55, "per_version": 0.24,
                          "rule": "PREREG-EVL-6 section 5"},
                         "fifteen seatable versions at 0.13, of the lane's restated 3.9")
        jb = rep["jobs"]
        self.assertEqual(jb["missed"], ["decide-close", "screen"])  # decide-open ran (and failed); score still runs
        self.assertEqual(sorted((f["job"], f["status"]) for f in jb["failed"]),
                         [("decide-open:2026-10-20", "failed"), ("verdicts", "unfinished")])
        self.assertEqual(jb["by_job"]["record"], {"n": 2, "ok": 2, "failed": 0})

    def test_neither_form_carries_a_price_a_headline_or_a_symbol(self):
        rep = R.build(self.st, DAY, now=self.now)
        text = R.render(rep)
        data = json.dumps(rep, sort_keys=True)
        for banned in ("ACME", "MIRACLE", "headline", "secret summary", "123.45", "124.56", "123.4", "124.5"):
            self.assertNotIn(banned, text)
            self.assertNotIn(banned, data)
        self.assertLessEqual(len(text.splitlines()), 14)
        self.assertIn("Expected false passes: 1.95 (0.13 x 15 versions and 0 fresh runs; base 0.45, stresses' worst "
                      "2.55) of the lane's restated 3.9 (PREREG-EVL-6 section 5; 1.95 left, 0 runs waiting); per version "
                      "0.24 within 120 sessions", text)
        self.assertIn("missed: decide-close, screen", text)
        self.assertIn("EVL-ERN-READ-O3 v1 (record)", text)

    def test_a_look_on_record_shows_in_the_report(self):
        look = {c: None for c in SC.LOOK_COLUMNS} | {
            "program": "EVL-ERN-READ-O1", "version": 1, "k": 1, "at": "2026-11-02T21:00:00Z", "sessions": 10, "n": 61,
            "issuers": 50, "blocks": 10, "p": 0.0123, "alpha": 0.022, "fp_check": 0.02, "held": 1, "passed": 0,
            "why": "fail: session p 0.01230 > alpha 0.022",
            "issuer": {"p": 0.2, "alpha": 0.024, "f": 0.01, "values": 50}}
        SC.write_look(self.st, look)
        rep = R.build(self.st, DAY, now=self.now)
        o1 = next(p for p in rep["programs"] if p["program"] == "EVL-ERN-READ-O1")
        self.assertEqual((o1["last_look"]["k"], o1["last_look"]["issuer"]["p"], o1["held_looks"]), (1, 0.2, 1))
        self.assertEqual(o1["next_look"]["k"], 2)
        self.assertIn("last look 1 fail p 0.0123/0.022, issuer p 0.2000/0.024", R.render(rep))

    def test_a_quiet_day_reports_zeros(self):
        empty = S.Store(self.tmp.name + "-empty")
        try:
            rep = R.build(empty, dt.date(2026, 10, 24), now=dt.datetime(2026, 10, 24, 22, 0, tzinfo=UTC))
            self.assertEqual((rep["session"], rep["programs"], rep["jobs"]["missed"]), (False, [], []))
            self.assertIn("no session", R.render(rep))
        finally:
            empty.close()


class ProgramTableTest(unittest.TestCase):
    def test_the_judge_and_the_program_table_agree(self):
        from league.events import programs as P
        self.assertEqual(set(SC.SEATABLE), {p.id for p in P.PROGRAMS if p.seatable})
        self.assertEqual(set(SC.SEATABLE) | set(SC.RECORDS), {p.id for p in P.PROGRAMS})
        self.assertEqual(SC.HOLDS, {p.id: p.hold for p in P.PROGRAMS})
        # (PREREG-EVL-8 section 3.2: its three PX seats read no verdict and have a control condition, screen.CONTROLS'
        # rows of that file, judged by league/events/screen8.py: league/tests/test_events_evl8.py holds them)
        self.assertEqual({k for k in SC.CONTROLS if not P.is_8(k)}, {p.id for p in P.PROGRAMS if p.seatable and p.reads})
        for prog, ctl in SC.CONTROLS.items():
            if P.is_8(prog):
                continue        # (a PX seat's family is its own and its control's another: test_events_evl8.py)
            self.assertEqual(P.BY_ID[ctl].family, P.BY_ID[prog].family)
            self.assertFalse(P.BY_ID[ctl].reads or P.BY_ID[ctl].seatable)


# PREREG-EVL-7 (A125 pinned REGISTERED_AT_7): this module's tests are of mechanisms written before the learners
# registered and run on the registries without them (league/tests/evl7_fakes.py); the learners' own effects on these
# paths are league/tests/test_events_evl7.py's and test_events_evl7_fix.py's.
from league.tests.evl7_fakes import setUpModule, tearDownModule  # noqa: E402,F401

if __name__ == "__main__":
    unittest.main()
