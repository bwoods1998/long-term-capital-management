"""The forward screen's job (league/ops/forward_screen.py, FWD1-R): the clock, the lineages, the checkpoints of record,
one verdict a lineage, the panel's placebo leg, the engine rule, the sides read from a program's own run, the permit
file and the sentence beside a trade.

Every store is made here from invented rows (FAKE: no market data, no real figure); the House's runs are a fake."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import tempfile
import types
import unittest
from unittest import mock
from collections import Counter
from pathlib import Path

import numpy as np

from league.equity import schedule
from league.live.decider import InlineDecider
from league.ops import forward_db, forward_screen as FS, fwd1_rule as R, registry
from league.tests import test_forward_shadow as TS

REPO = Path(__file__).resolve().parents[2]
RECEIPT = REPO / R.RECEIPT_PATH
PIN_AT = dt.datetime(2026, 10, 15, 14, 0, tzinfo=dt.timezone.utc).timestamp()      # inside Thursday's session
START = dt.date(2026, 10, 16)


def sessions(first: dt.date, n: int) -> list[str]:
    out, day = [], first
    while len(out) < n:
        if schedule.is_session(day):
            out.append(day.isoformat())
        day += dt.timedelta(days=1)
    return out


def fake_rule() -> R.Rule:
    figures = {key: {"budget": 0.15 if key.endswith("N") else 0.03, "fp_point": 0.02, "fp_ub": 0.025,
                     "zero_edge_by_checkpoint": [0.01, 0.015, 0.02, 0.022, 0.024, 0.026, 0.028], "edge": "+10%",
                     "power": 0.05, "fp_avg": 0.03} for key in ("ETF|N", "PANEL|N", "PANEL|XS1")}
    return R.Rule(receipt_sha256="c" * 64, figures=figures)


def floor_pools(seed: int, n_d: int = 1004, n_c: int = 751, *, panel: bool = False):
    """FAKE Train-era pools: (r, r15, w, b) for an ETF program, (x, x15, w) for a panel one."""
    out = []
    for span, n in ((0, n_d), (1, n_c)):
        rng = np.random.default_rng([seed, span, n])
        on = rng.random(n) < 0.6
        w = np.where(on, 0.5, 0.0)
        r = np.where(on, rng.normal(0.0002, 0.006, n), 0.0)
        r15 = r - np.where(on & (rng.random(n) < 0.15), 1e-4, 0.0)
        b = rng.normal(0.0003, 0.01, n)
        out.append((r, r15, w) if panel else (r, r15, w, b))
    return tuple(out)


class FakeRuns:
    """The House's runs, invented: the floors' pools and a placebo block."""

    def __init__(self, placebo_t=None, days=None, fail=False, refuse=False, forward=None):
        self.calls = Counter()
        self.placebo_t = placebo_t
        self.days = days
        self.fail = fail
        self.refuse = refuse
        self.forward = forward

    def forward_sides(self, program, typ, *, settings, fdb=None):
        self.calls["forward"] += 1
        if self.forward is None:
            raise RuntimeError("no forward run in this test")
        return self.forward

    def etf_pools(self, program):
        self.calls["etf"] += 1
        if self.fail:
            raise RuntimeError("the child died")
        if self.refuse:
            raise FS.OwnFloorRefused("a Train-era run ended ['disqualified', 'ok']: its series is partial")
        return floor_pools(1)

    def panel_pools(self, program):
        self.calls["panel"] += 1
        return floor_pools(2, panel=True)

    def panel_placebo(self, program, *, start, end, seed):
        self.calls["placebo"] += 1
        k = len([d for d in sessions(start, 80) if d <= end.isoformat()])
        return {"t": list(self.placebo_t if self.placebo_t is not None else [0.0] * 999),
                "days": self.days if self.days is not None else k, "n": 999, "seed": seed}

    def close(self):
        pass


class Fixture(unittest.TestCase):
    """A state root with a forward store holding invented registry rows and days."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.fdb = forward_db.open_db(self.root)
        self.engine, _ = forward_db.engine_id(self.fdb, "equity-engine-1+aaaaaaaaaaaa+fwd-1", at=1.0)
        self.pid = 0
        self.families: dict[str, dict] = {}
        self.settings = {"elane": {"fwd1": {"mode": "record", "seats": "off"}, "forward": {"mode": "record"}}}
        self.rule = fake_rule()

    def tearDown(self):
        self.fdb.close()
        self.tmp.cleanup()

    def family(self, fid: str, *, structure: str = "etf", state: dict | None = None, lineage: str | None = None):
        self.families[fid] = {"id": fid, "structure": structure, "spec": {"lane": "equity", "agenda": "trend"},
                              "state": dict(state or {}), "lineage": lineage, "band": "gym"}
        return self.families[fid]

    def row(self, fid: str, version: int, *, reason: str = "train_pass", first_day: str = "2026-10-13",
            lineage: str | None = None, panel: bool = False) -> int:
        self.pid += 1
        lin = lineage or f"equity:{fid}"
        self.fdb.execute(
            "INSERT INTO fwd_registry(pid, key, family, version, lane, reason, ugroup, lineage, code, params, needs, "
            "program_sha, run_sha, author, created_at, evidence, first_close, first_day, registered_at, route, "
            "alpha_f, prev_hash, row_hash) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (self.pid, f"{fid}@{version}", fid, version, "equity", reason, "panel:sp500" if panel else "index", lin,
             "PARAMS = {}\n", "{}", json.dumps({"symbols": ["SPY"], "history": 1}), "p" * 64, f"{self.pid:064d}", "",
             1.0, "registry", "2026-10-12", first_day, 1.0, "XS1" if panel else "S2", "0.03", "0" * 64,
             f"{self.pid:063d}h"))
        self.fdb.commit()
        return self.pid

    def days(self, pid: int, values, *, first: dt.date = dt.date(2026, 10, 13), engine: int | None = None,
             w: float = 0.5, b: float = 0.0, bars: str = "b" * 16, status: dict | None = None,
             r15: float = -1e-5):
        names = sessions(first, len(values))
        for day, r in zip(names, values):
            self.fdb.execute("INSERT INTO fwd_days(pid, day, engine, r, w, b, r15, r0, entries, exits, status, at, bars) "
                             "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                             (pid, day, engine or self.engine, float(r), w, b, float(r) + r15, None, 0, 0,
                              (status or {}).get(day, "ok"), 1.0, bars))
        self.fdb.commit()
        return names

    def restated(self, pid: int, first: str, last: str, *, engine: int | None = None, bars: str = "moved"):
        """E3's own `restated` event of a pid under an engine id (league/ops/forward_shadow.py, A RESTATED RECORD)."""
        payload = {"why": "a test's", "engine": engine or self.engine, "night": last, "days": 1, "first": first,
                   "last": last, "moved": 1 if bars == "moved" else 0, "same": 0 if bars == "moved" else 1, "bars": bars}
        self.fdb.execute("INSERT INTO fwd_events(at, kind, pid, day, payload) VALUES (1.0, 'restated', ?, ?, ?)",
                         (pid, first, json.dumps(payload)))
        self.fdb.commit()

    def advance(self, day: str):
        """A night of the record through `day` (its `fwd_runs` row): THE STALL RULE's night."""
        self.fdb.execute("INSERT INTO fwd_runs(job, through, engine, started, finished, seconds, programs, sessions, "
                         "errors, stale, budget_hit, head) VALUES ('forward_shadow', ?, ?, 1.0, 1.0, 0.0, 1, 1, 0, 0, 0, "
                         "NULL)", (day, self.engine))
        self.fdb.commit()

    def permits(self) -> dict:
        return json.loads((self.root / FS.PERMITS).read_text())["lineages"]

    def sides(self, pid: int, names, value: float = 0.0, engine: int | None = None):
        """Sides kept by an earlier night's forward run (the first day's lot entering at `value`)."""
        db = FS.open_store(self.root)
        with db:
            for i, day in enumerate(names):
                db.execute("INSERT OR IGNORE INTO fwd1_sides(pid, day, engine, sides, at) VALUES (?,?,?,?,?)",
                           (pid, day, engine or self.engine, value if i == 0 else 0.0, 2.0))
        db.close()

    def recorded(self, pid: int) -> dict:
        """The record's r of a pid's rows, as its own forward run would give them."""
        return {str(r[0]): float(r[1]) for r in self.fdb.execute("SELECT day, r FROM fwd_days WHERE pid=?", (pid,))}

    def night(self, runs=None, *, now: float = PIN_AT + 86400 * 20):
        return FS.night(self.root, rule=self.rule, settings=self.settings, now=now, base=None, release=None,
                        runs=runs or FakeRuns(), families=self.families, clock=lambda: now)

    def store(self):
        db = FS.open_store(self.root)
        return db

    def pin_first(self):
        """The pin first seen running at PIN_AT (the clock starts Friday Oct 16), nothing judged yet."""
        db = FS.open_store(self.root)
        FS.pinned(db, self.rule, base=None, release=None, now=PIN_AT)
        db.close()

    def first_night(self):
        """The pin is first seen running at PIN_AT."""
        return FS.night(self.root, rule=self.rule, settings=self.settings, now=PIN_AT, base=None, release=None,
                        runs=FakeRuns(), families=self.families, clock=lambda: PIN_AT)


class TheClock(Fixture):
    def test_the_clock_starts_at_the_first_session_after_the_pin(self):
        self.family("f1")
        pid = self.row("f1", 1)
        names = self.days(pid, [0.0] * 3 + [0.01 + 0.001 * (i % 3) for i in range(10)])   # 3 days before the pin
        self.assertEqual(names[3], START.isoformat())
        self.sides(pid, names)
        self.first_night()
        db = self.store()
        pin = dict(db.execute("SELECT * FROM fwd1_pins").fetchone())
        self.assertEqual(pin["start"], START.isoformat())
        self.assertEqual(pin["evidence"], "sighting")
        lin = dict(db.execute("SELECT * FROM fwd1_lineages").fetchone())
        self.assertEqual(lin["start"], START.isoformat())     # registered before the pin: it enters mid-run
        check = dict(db.execute("SELECT * FROM fwd1_checks WHERE k=5").fetchone())
        self.assertEqual(check["day"], names[3 + 4])          # the 5th counted day FROM the start: nothing before it
        self.assertGreater(check["t"], 2.61)
        db.close()

    def test_the_deploy_record_dates_the_pin(self):
        base = self.root / "base"
        base.mkdir()
        (base / "deploys.jsonl").write_text(json.dumps({"stage": "verdict", "verdict": "promoted", "release": "rel-1",
                                                        "at": "2026-10-15T14:00:00Z"}) + "\n")
        db = self.store()
        pin = FS.pinned(db, self.rule, base=base, release=Path("/x/rel-1"), now=PIN_AT + 86400 * 2)
        self.assertEqual((pin["evidence"], pin["start"], pin["release"]), ("deploys", START.isoformat(), "rel-1"))
        again = FS.pinned(db, self.rule, base=None, release=None, now=PIN_AT + 86400 * 9)
        self.assertEqual(again["pinned_at"], pin["pinned_at"])      # written once a sha
        db.close()


class ThePooledScreenWithholdsItsLineages(Fixture):
    """POOL1 (A55a: PREREG-POOL1 sections 8 and 11 P1 item 5): a lineage on the pooled screen's POOL-route or hold
    list has no pass sentence, no status count and no registry entry in FWD1's operator report until its unit's
    verdict is final (it is counted as `pool_route` only), and is shown after; FWD1-R's verdict and permit file are
    unchanged. The pool's file failing closed withholds every ETF lineage."""

    def pool(self, word: str = "pending", *, raw: str | None = None):
        from league.ops import pool_screen

        path = self.root / pool_screen.PERMITS
        if raw is not None:
            path.write_text(raw)
            return
        cell = "trend_momentum/sectors"
        path.write_text(json.dumps({"version": 1, "screen": "POOL1", "receipt": "d" * 64, "clock": "2026-10-26",
                                    "at": "x", "routes": {"equity:f1": {"cell": cell, "cluster": "trend_momentum"}},
                                    "holds": [], "units": {cell: {"cluster": "trend_momentum", "word": word}},
                                    "lineages": {}, "eligible": []}))

    def passed(self):
        self.family("f1")
        pid = self.row("f1", 1, first_day="2026-10-16")
        names = self.days(pid, [0.01 + 0.001 * (i % 3) for i in range(12)], first=START)
        self.sides(pid, names, 0.5)
        return pid

    def report(self) -> dict:
        return json.loads((self.root / FS.REPORT).read_text())

    def test_absent_until_final_and_present_after(self):
        self.passed()
        self.pool("pending")
        self.first_night()
        report = self.report()
        self.assertEqual(report["passes"], [])
        self.assertEqual(report["pool_route"], 1)
        self.assertEqual(report["registry"]["ETF|N"]["observed"], 0)
        self.assertNotIn("ETF|N", report["counts"])
        db = self.store()
        self.assertEqual(db.execute("SELECT verdict FROM fwd1_verdicts").fetchone()[0], "pass")   # FWD1-R unchanged
        db.close()
        self.assertEqual(json.loads((self.root / FS.PERMITS).read_text())["lineages"]["equity:f1"]["status"], "pass")
        for word in ("FAIL", "DEMOTED", "VOID", "REFUTED", "PASS"):
            self.pool(word)
            self.night()
            with self.subTest(word=word):
                report = self.report()
                self.assertEqual([p["lineage"] for p in report["passes"]], ["equity:f1"])
                self.assertEqual(report["pool_route"], 0)
                self.assertEqual(report["registry"]["ETF|N"]["observed"], 1)

    def test_fail_closed_withholds_every_etf_lineage(self):
        self.passed()
        self.pool(raw="{not json")
        self.first_night()
        self.assertEqual(self.report()["passes"], [])
        self.assertEqual(self.report()["pool_route"], 1)
        (self.root / "pool-screen-permits.json").unlink()
        self.settings = {**self.settings, "elane": {**self.settings["elane"], "pool": {"mode": "record"}}}
        self.night()
        self.assertEqual(self.report()["pool_route"], 1)          # missing while the pool's mode is on
        self.settings = {**self.settings, "elane": {**self.settings["elane"], "pool": {"mode": "off"}}}
        self.night()
        self.assertEqual(self.report()["pool_route"], 0)          # missing with the mode off: nothing withheld


class TheVerdicts(Fixture):
    def test_a_pass_its_floor_its_words_and_one_verdict_a_lineage(self):
        self.family("f1")
        pid = self.row("f1", 1, first_day="2026-10-16")
        self.row("f1", 2, first_day="2026-10-16", reason="train_fail")
        later = self.row("f1", 3, first_day="2026-10-19")            # a later version: never the representative
        names = self.days(pid, [0.01 + 0.001 * (i % 3) for i in range(12)], first=START)
        self.days(later, [0.02] * 5, first=dt.date(2026, 10, 19))
        self.sides(pid, names, 0.5)
        self.first_night()
        db = self.store()
        lin = dict(db.execute("SELECT * FROM fwd1_lineages").fetchone())
        self.assertEqual((lin["rep"], lin["case_"], lin["type"], lin["judged"], lin["versions"]), (pid, "N", "ETF", 1, 3))
        v = dict(db.execute("SELECT * FROM fwd1_verdicts").fetchone())
        self.assertEqual((v["verdict"], v["k"], v["pid"]), ("pass", 5, pid))
        self.assertIn("WEAK SCREEN", v["beside"])
        self.assertIn("t = ", v["beside"])
        self.assertIn("Registry: 1 forward passes of 1 ETF case N lineages judged so far", v["beside"])
        self.assertNotIn("t = ", v["words"])
        fl = dict(db.execute("SELECT * FROM fwd1_floors").fetchone())
        self.assertIsNotNone(fl["k_own"])
        self.assertIsNotNone(fl["drift"])
        check = dict(db.execute("SELECT * FROM fwd1_checks WHERE k=5").fetchone())
        self.assertEqual(check["g_bp"], 2.0)
        self.assertEqual(check["c_used"], R.c_used("ETF", "N", fl["k_own"]))
        with self.assertRaises(sqlite3.DatabaseError):           # the checkpoint of record is never rewritten
            db.execute("UPDATE fwd1_checks SET t=0")
        with self.assertRaises(sqlite3.DatabaseError):
            db.execute("DELETE FROM fwd1_verdicts")
        db.close()
        receipt = self.night()                                   # nothing judges it again
        self.assertEqual(receipt.get("checks", 0), 0)
        doc = json.loads((self.root / FS.PERMITS).read_text())
        row = doc["lineages"]["equity:f1"]
        self.assertEqual((row["status"], row["family"], row["version"], row["k"], row["weak"]), ("pass", "f1", 1, 5, True))
        self.assertEqual(row["start"], "2026-10-16")                # its FWD1_START (L5, A48): a date, no figure
        self.assertEqual(row["run_sha"], f"{pid:064d}")
        self.assertEqual(row["engine"], "equity-engine-1+aaaaaaaaaaaa+fwd-1")

        def numbers(value):
            if isinstance(value, dict):
                return [x for v in value.values() for x in numbers(v)]
            if isinstance(value, list):
                return [x for v in value for x in numbers(v)]
            return [value] if isinstance(value, float) else []
        self.assertEqual(numbers(doc), [])                       # ids and words only: no figure crosses
        report = json.loads((self.root / FS.REPORT).read_text())
        self.assertEqual(report["registry"]["ETF|N"]["observed"], 1)
        # the sentence stands beside every trade of the program once it is seated on the pass (the direction report)
        from league.ops import dlane_report

        seated = {"elane_forward": {"seated": True, "eligible": True, "version": 1, "lineage": "equity:f1"}}
        fake = types.SimpleNamespace(root=self.root, looks=lambda: [],
                                     family=lambda fid: {"id": fid, "structure": "etf", "state": seated})
        line = dlane_report.EquityScreens(fake).of("f1", 1)
        self.assertEqual(line["screen"], "FWD1-R")
        self.assertIn("t = ", line["beside"])
        self.assertIsNone(dlane_report.EquityScreens(fake).of("f1", 2)["beside"])   # another version: none stated

    def test_a_fail_at_sixty_and_a_global_bar_read_without_a_floor(self):
        self.family("f1")
        pid = self.row("f1", 1, first_day="2026-10-16")
        values = [0.004 if i % 2 else -0.004 for i in range(60)]
        names = self.days(pid, values, first=START)
        self.sides(pid, names)
        runs = FakeRuns()
        FS.night(self.root, rule=self.rule, settings=self.settings, now=PIN_AT, base=None, release=None, runs=runs,
                 families=self.families, clock=lambda: PIN_AT)
        db = self.store()
        self.assertEqual([int(r["k"]) for r in db.execute("SELECT k FROM fwd1_checks ORDER BY k")], list(R.PLAN))
        v = dict(db.execute("SELECT * FROM fwd1_verdicts").fetchone())
        self.assertEqual((v["verdict"], v["k"]), ("fail", 60))
        self.assertEqual(runs.calls["etf"], 0)                   # t never reached the global bar: no floor was run
        db.close()

    def test_an_etf_lineage_with_a_sealed_look_is_not_judged(self):
        self.family("f1", state={"elane_try": {"version": 1, "entered": True}})
        pid = self.row("f1", 1)
        self.days(pid, [0.01] * 6)
        self.family("f2")
        p2 = self.row("f2", 1)
        self.fdb.execute("INSERT INTO fwd_tags(pid, tag, value, at) VALUES (?, 'look_fail', '', 1.0)", (p2,))
        self.fdb.commit()
        self.first_night()
        db = self.store()
        rows = {r["lineage"]: dict(r) for r in db.execute("SELECT * FROM fwd1_lineages")}
        self.assertEqual(rows["equity:f1"]["judged"], 0)
        self.assertEqual(rows["equity:f1"]["why"], FS.NOT_JUDGED["sealed"])
        self.assertEqual(rows["equity:f2"]["judged"], 0)
        self.assertEqual(db.execute("SELECT COUNT(*) FROM fwd1_checks").fetchone()[0], 0)
        db.close()
        doc = json.loads((self.root / FS.PERMITS).read_text())
        self.assertEqual(doc["lineages"], {})                    # not judged: not listed, its sealed path stands

    def test_a_case_n_lineage_that_looks_later_is_void(self):
        fam = self.family("f1")
        pid = self.row("f1", 1, first_day="2026-10-16")
        self.days(pid, [0.0] * 3, first=START)
        self.first_night()
        fam["state"]["elane_try"] = {"version": 1}
        self.night()
        db = self.store()
        v = dict(db.execute("SELECT * FROM fwd1_verdicts").fetchone())
        self.assertEqual(v["verdict"], "void")
        db.close()

    def test_a_lineage_that_already_trades_is_not_judged(self):
        self.family("f9")
        self.row("f9", 1, reason="live")
        self.first_night()
        db = self.store()
        row = dict(db.execute("SELECT * FROM fwd1_lineages WHERE lineage='equity:f9'").fetchone())
        self.assertEqual((row["judged"], row["why"]), (0, FS.NOT_JUDGED["live"]))
        db.close()

    def test_the_house_failing_marks_nobody(self):
        self.family("f1")
        pid = self.row("f1", 1, first_day="2026-10-16")
        names = self.days(pid, [0.01 + 0.001 * (i % 3) for i in range(6)], first=START)
        self.sides(pid, names)
        receipt = FS.night(self.root, rule=self.rule, settings=self.settings, now=PIN_AT, base=None, release=None,
                           runs=FakeRuns(fail=True), families=self.families, clock=lambda: PIN_AT)
        self.assertEqual(receipt["house"], 1)
        db = self.store()
        self.assertEqual(db.execute("SELECT COUNT(*) FROM fwd1_checks").fetchone()[0], 0)    # asked again tomorrow
        self.assertEqual(db.execute("SELECT COUNT(*) FROM fwd1_floors").fetchone()[0], 0)
        db.close()
        self.night()
        db = self.store()
        self.assertEqual(dict(db.execute("SELECT verdict FROM fwd1_verdicts").fetchone())["verdict"], "pass")
        db.close()

    def test_no_own_floor_is_ineligible_with_no_verdict(self):
        self.family("f1")
        pid = self.row("f1", 1, first_day="2026-10-16")
        names = self.days(pid, [0.01 + 0.001 * (i % 3) for i in range(12)], first=START)
        self.sides(pid, names)
        FS.night(self.root, rule=self.rule, settings=self.settings, now=PIN_AT, base=None, release=None,
                 runs=FakeRuns(refuse=True), families=self.families, clock=lambda: PIN_AT)
        db = self.store()
        self.assertIsNone(db.execute("SELECT * FROM fwd1_verdicts").fetchone())
        self.assertEqual(db.execute("SELECT COUNT(*) FROM fwd1_checks").fetchone()[0], 0)
        fl = dict(db.execute("SELECT * FROM fwd1_floors").fetchone())
        self.assertIsNone(fl["k_own"])
        self.assertIn("partial", fl["why"])
        self.assertEqual([r["status"] for r in FS.status_rows(db)], ["ineligible"])
        db.close()
        doc = json.loads((self.root / FS.PERMITS).read_text())
        self.assertEqual(doc["lineages"]["equity:f1"]["status"], "ineligible")
        runs = FakeRuns()
        self.night(runs)                                          # never asked again
        self.assertEqual(runs.calls["etf"], 0)

    def test_a_passed_checkpoint_left_without_its_verdict_gets_it(self):
        """A store written by a build that wrote the checkpoint and the verdict apart: the verdict follows."""
        self.family("f1")
        pid = self.row("f1", 1, first_day="2026-10-16")
        names = self.days(pid, [0.01] * 6, first=START)
        self.first_night()                                   # registers it (no sides yet: no checkpoint)
        db = self.store()
        with db:
            db.execute("INSERT INTO fwd1_floors(pid, case_, k_own, cells, drift, why, seconds, at) VALUES "
                       "(?, 'N', 150, '{}', 0.1, NULL, 0, 1)", (pid,))
            db.execute("INSERT INTO fwd1_checks(lineage, k, pid, engine, day, t, s, s15, g_bp, ll, count, draws, c_used, "
                       "passed, why, at) VALUES ('equity:f1', 5, ?, ?, ?, 9.0, 0.05, 0.05, 2, 0, NULL, NULL, 2.61, 1, "
                       "NULL, 1)", (pid, self.engine, names[4]))
        db.close()
        self.night()
        db = self.store()
        v = dict(db.execute("SELECT * FROM fwd1_verdicts").fetchone())
        self.assertEqual((v["verdict"], v["k"]), ("pass", 5))
        self.assertIn("t = 9.00", v["beside"])
        db.close()

    def test_no_sides_no_checkpoint(self):
        self.family("f1")
        pid = self.row("f1", 1, first_day="2026-10-16")
        self.days(pid, [0.01] * 6, first=START)
        receipt = self.first_night()                              # the forward run failed: the House's
        self.assertEqual((receipt["no_sides"], receipt["house"]), (1, 1))

    def test_the_sides_come_from_the_programs_own_run_where_it_reproduces_the_record(self):
        self.family("f1")
        pid = self.row("f1", 1, first_day="2026-10-16")
        names = self.days(pid, [0.01 + 0.001 * (i % 3) for i in range(6)], first=START)
        ran = self.recorded(pid)
        moved = {**ran, names[2]: ran[names[2]] + 1e-3}          # one day the run does not reproduce
        runs = FakeRuns(forward={"r": moved, "sides": {names[0]: 0.5, names[3]: 0.25}})
        receipt = self.night(runs, now=PIN_AT)
        self.assertEqual(runs.calls["forward"], 1)
        self.assertEqual(receipt["no_sides"], 1)                  # the moved day has no sides: no checkpoint
        db = self.store()
        held = {r["day"]: r["sides"] for r in db.execute("SELECT day, sides FROM fwd1_sides")}
        self.assertNotIn(names[2], held)
        self.assertEqual((held[names[0]], held[names[3]], held[names[1]]), (0.5, 0.25, 0.0))
        self.assertEqual(db.execute("SELECT COUNT(*) FROM fwd1_checks").fetchone()[0], 0)
        db.close()
        runs = FakeRuns(forward={"r": ran, "sides": {names[0]: 0.5, names[2]: 0.5, names[3]: 0.25}})
        self.night(runs, now=PIN_AT)                              # the next night's run reproduces it
        db = self.store()
        check = dict(db.execute("SELECT * FROM fwd1_checks WHERE k=5").fetchone())
        x = [float(r) for r in [ran[d] for d in names[:5]]]
        sides = [0.5, 0.0, 0.5, 0.25, 0.0]
        self.assertAlmostEqual(check["s"], sum(v - 2e-4 * c for v, c in zip(x, sides)), delta=1e-12)
        self.assertEqual(held[names[0]], 0.5)                     # first write stands
        db.close()

    def test_the_haircut_reads_the_measured_gap(self):
        self.family("f1")
        pid = self.row("f1", 1, first_day="2026-10-16")
        names = self.days(pid, [0.01 + 0.001 * (i % 3) for i in range(6)], first=START)
        self.sides(pid, names, 0.5)
        for lid, gap in enumerate((3.0, 4.5), start=1):
            self.fdb.execute("INSERT INTO fwd_lotgap(lid, instance, pid, symbol, opened_day, exit_day, entry_at, exit_at, "
                             "model_bp, side_gap_bp, at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                             (lid, "i", pid, "SPY", "2026-10-13", "2026-10-14", "open", "open", 1.0, gap, 1.0))
        self.fdb.commit()
        self.first_night()
        db = self.store()
        self.assertEqual(dict(db.execute("SELECT g_bp FROM fwd1_checks WHERE k=5").fetchone())["g_bp"], 4.0)
        db.close()


class ThePanel(Fixture):
    def setUp(self):
        super().setUp()
        self.family("p1", structure="panel")
        self.pid1 = self.row("p1", 1, first_day="2026-10-16", panel=True)
        self.names = self.days(self.pid1, [0.012 + 0.001 * (i % 3) for i in range(6)], first=START, b=0.004)
        self.sides(self.pid1, self.names)

    def run_night(self, runs):
        return FS.night(self.root, rule=self.rule, settings=self.settings, now=PIN_AT, base=None, release=None,
                        runs=runs, families=self.families, clock=lambda: PIN_AT)

    def test_the_placebo_leg_holds_at_119(self):
        runs = FakeRuns(placebo_t=[99.0] * 119 + [0.0] * 880)
        self.run_night(runs)
        db = self.store()
        check = dict(db.execute("SELECT * FROM fwd1_checks WHERE k=5").fetchone())
        self.assertEqual((check["count"], check["draws"], check["passed"]), (119, 999, 1))
        self.assertEqual(check["g_bp"], 3.0)                     # the panel's 3 bp until 20 live panel lots
        lin = dict(db.execute("SELECT * FROM fwd1_lineages").fetchone())
        self.assertEqual((lin["type"], lin["case_"]), ("PANEL", "N"))
        v = dict(db.execute("SELECT * FROM fwd1_verdicts").fetchone())
        self.assertIn("WEAK at this checkpoint", v["beside"])
        db.close()

    def test_the_placebo_leg_fails_at_120(self):
        self.run_night(FakeRuns(placebo_t=[99.0] * 120 + [0.0] * 879))
        db = self.store()
        check = dict(db.execute("SELECT * FROM fwd1_checks WHERE k=5").fetchone())
        self.assertEqual((check["count"], check["passed"]), (120, 0))
        self.assertIsNone(db.execute("SELECT * FROM fwd1_verdicts").fetchone())
        db.close()

    def test_a_run_read_on_other_sessions_than_the_judged_ones_waits_on_the_house(self):
        """A placebo run whose span is not the k judged sessions with no session of the program's own to explain it
        is the House's (the review's fix: it no longer fails the checkpoint, which a FAIL at 60 would make for good)."""
        receipt = self.run_night(FakeRuns(days=4))
        db = self.store()
        self.assertIsNone(db.execute("SELECT * FROM fwd1_checks WHERE k=5").fetchone())
        self.assertGreaterEqual(receipt["house"], 1)
        db.close()

    def test_a_span_holding_a_session_the_house_left_out_waits(self):
        """THE PLACEBO SPAN: an audit-marked session inside the span is the House's: no checkpoint, no fail."""
        self.days(self.pid1, [0.013], first=dt.date.fromisoformat(sessions(START, 7)[6]), b=0.004)
        self.sides(self.pid1, sessions(START, 7))
        self.fdb.execute("INSERT INTO fwd_events(at, kind, pid, day, payload) VALUES (1.0, 'audit_mismatch', ?, ?, '{}')",
                         (self.pid1, self.names[2]))
        self.fdb.commit()
        runs = FakeRuns()
        self.run_night(runs)
        db = self.store()
        self.assertIsNone(db.execute("SELECT * FROM fwd1_checks WHERE k=5").fetchone())
        self.assertEqual(runs.calls["placebo"], 0)                # not run: its span cannot be the judged sessions
        self.assertIn("left out", db.execute("SELECT payload FROM fwd1_events WHERE kind='house'").fetchone()[0])
        db.close()

    def test_a_span_holding_a_session_the_program_disqualified_fails_closed(self):
        """A session of the span that is the program's own (a disqualified row) is its own doing: the leg fails
        closed, and no placebo run is spent on it."""
        p2 = self.row("p2", 1, first_day="2026-10-16", panel=True)
        self.family("p2", structure="panel")
        names = sessions(START, 7)
        self.days(p2, [0.012 + 0.001 * (i % 3) for i in range(7)], first=START, b=0.004,
                  status={names[2]: "disqualified"})
        self.sides(p2, names)
        runs = FakeRuns()
        self.run_night(runs)
        db = self.store()
        check = dict(db.execute("SELECT * FROM fwd1_checks WHERE lineage='equity:p2' AND k=5").fetchone())
        self.assertEqual((check["passed"], check["draws"]), (0, 0))
        self.assertIn("fails closed", check["why"])
        self.assertEqual(check["day"], names[5])                  # the 5th COUNTED day: the disqualified one is not
        db.close()
        self.assertEqual(runs.calls["placebo"], 1)                # p1's leg only

    def test_a_refusal_before_any_validation_read_is_no_sealed_precheck(self):
        """elane_xs writes its pre-check record with `reached` False when it refuses a version before any Validation
        read (a Train segment its own errors ended, the same lineage as a twin): no sealed data was read, so the
        lineage is case N at its first sighting and a pending case-N lineage is not voided by one."""
        self.family("p3", structure="panel", state={"elane_xs_precheck": {"version": 1, "reached": False,
                                                                          "why": "same lineage", "twin": "p9"}})
        self.row("p3", 1, panel=True)
        self.run_night(FakeRuns())
        self.families["p1"]["state"]["elane_xs_precheck"] = {"version": 2, "reached": False, "why": "train run"}
        self.run_night(FakeRuns())
        db = self.store()
        rows = {r["lineage"]: dict(r) for r in db.execute("SELECT * FROM fwd1_lineages")}
        self.assertEqual((rows["equity:p3"]["case_"], rows["equity:p3"]["judged"]), ("N", 1))
        verdicts = {r["lineage"]: r["verdict"] for r in db.execute("SELECT lineage, verdict FROM fwd1_verdicts")}
        self.assertNotEqual(verdicts.get("equity:p1"), "void")
        db.close()
        self.assertTrue(FS.family_sealed({"state": {"elane_xs_precheck": {"version": 1, "reached": True}}}))
        self.assertTrue(FS.family_sealed({"state": {"elane_xs_precheck": {"version": 1}}}))    # unsaid: sealed

    def test_a_panel_lineage_with_an_xs1_precheck_is_case_xs1(self):
        self.family("p2", structure="panel", state={"elane_xs_precheck": {"version": 1}})
        self.row("p2", 1, panel=True)
        self.run_night(FakeRuns())
        db = self.store()
        row = dict(db.execute("SELECT * FROM fwd1_lineages WHERE lineage='equity:p2'").fetchone())
        self.assertEqual((row["case_"], row["judged"]), ("XS1", 1))
        db.close()


class TheEngine(Fixture):
    def test_an_untouched_program_carries_on_a_touched_one_is_void(self):
        for fid in ("f1", "f2"):
            self.family(fid)
        p1 = self.row("f1", 1, first_day="2026-10-16")
        p2 = self.row("f2", 1, first_day="2026-10-16")
        flat = [0.004 if i % 2 else -0.004 for i in range(8)]
        n1 = self.days(p1, flat, first=START)
        n2 = self.days(p2, flat, first=START)
        self.sides(p1, n1)
        self.sides(p2, n2)
        self.first_night()                                         # checkpoint 5 read (and failed) under engine 1
        new, _ = forward_db.engine_id(self.fdb, "equity-engine-1+bbbbbbbbbbbb+fwd-1", at=3.0)
        self.days(p1, flat + [0.004] * 5, first=START, engine=new)                      # the same days: untouched
        self.days(p2, [0.0] + flat[1:] + [0.004] * 5, first=START, engine=new)          # a judged day moved
        self.sides(p1, sessions(START, 13), engine=new)
        self.sides(p2, sessions(START, 13), engine=new)
        self.night()
        db = self.store()
        verdicts = {r["lineage"]: r["verdict"] for r in db.execute("SELECT lineage, verdict FROM fwd1_verdicts")}
        self.assertEqual(verdicts.get("equity:f2"), "void")
        self.assertNotIn("equity:f1", verdicts)
        self.assertEqual(dict(db.execute("SELECT engine FROM fwd1_checks WHERE lineage='equity:f1' AND k=10")
                              .fetchone())["engine"], new)
        db.close()


class TheEngineChange(Fixture):
    """An engine change and a pending lineage (the reviews' majors): the rows under a new engine id come later than the
    id (the panel night hours after E3's, a program the budget left stale a night later), so a judged day missing
    under it is WAITED for, never a void; a day present under both ids is compared on r, w, b and r15; a day that
    moved only because the vendor restated the store's history is carried."""

    FLAT = [0.004 if i % 2 else -0.004 for i in range(8)]

    def lineage(self, fid="f1", *, panel=False, b=0.0):
        self.family(fid, structure="panel" if panel else "etf")
        pid = self.row(fid, 1, first_day="2026-10-16", panel=panel)
        names = self.days(pid, self.FLAT, first=START, b=b)
        self.sides(pid, names)
        self.first_night()                                         # checkpoint 5 read (and failed) under engine 1
        db = self.store()
        self.assertEqual(db.execute("SELECT engine FROM fwd1_checks WHERE k=5").fetchone()[0], self.engine)
        db.close()
        return pid

    def verdicts(self):
        db = self.store()
        try:
            return {r["lineage"]: dict(r) for r in db.execute("SELECT * FROM fwd1_verdicts")}
        finally:
            db.close()

    def test_a_program_not_yet_written_under_the_new_id_waits_then_carries_on(self):
        pid = self.lineage()
        new, _ = forward_db.engine_id(self.fdb, "equity-engine-1+bbbbbbbbbbbb+fwd-1", at=3.0)
        receipt = self.night()                                     # E3's night has not reached it (its budget)
        self.assertEqual(self.verdicts(), {})
        self.assertEqual(receipt.get("engine_wait"), 1)
        self.assertEqual(self.permits()["equity:f1"]["status"], "pending")
        self.days(pid, self.FLAT + [0.004] * 5, first=START, engine=new)       # the next night writes it whole
        self.sides(pid, sessions(START, 13), engine=new)
        self.night()
        self.assertEqual(self.verdicts(), {})
        db = self.store()
        self.assertEqual(db.execute("SELECT engine FROM fwd1_checks WHERE k=10").fetchone()[0], new)
        self.assertEqual(json.loads(db.execute("SELECT payload FROM fwd1_events WHERE kind='engine_switched'")
                                    .fetchone()[0])["touched"], False)
        db.close()

    def test_a_panel_lineage_between_the_two_nights_is_never_voided(self):
        pid = self.lineage("p1", panel=True, b=0.001)
        new, _ = forward_db.engine_id(self.fdb, "equity-engine-1+aaaaaaaaaaaa+fwd-1+xs.bbbbbbbbbbbb", at=3.0)
        self.night()                                               # after E3's night: no panel row under it yet
        self.assertEqual(self.verdicts(), {})
        self.days(pid, self.FLAT + [0.004] * 5, first=START, engine=new, b=0.001)   # the panel night writes them
        self.sides(pid, sessions(START, 13), engine=new)
        self.night()                                               # after the panel night
        self.assertEqual(self.verdicts(), {})
        db = self.store()
        self.assertEqual(db.execute("SELECT engine FROM fwd1_checks WHERE k=10").fetchone()[0], new)
        db.close()

    def test_a_benchmark_that_moved_is_a_touch(self):
        """b (so the panel's x = r - w b) and r15 count as r and w do: a panel day whose matched-cell benchmark moved
        under the new id is a touched judged day."""
        pid = self.lineage("p1", panel=True, b=0.001)
        new, _ = forward_db.engine_id(self.fdb, "equity-engine-1+aaaaaaaaaaaa+fwd-1+xs.cccccccccccc", at=3.0)
        self.days(pid, self.FLAT + [0.004] * 5, first=START, engine=new, b=0.002)
        self.sides(pid, sessions(START, 13), engine=new)
        self.night()
        self.assertEqual(self.verdicts()["equity:p1"]["verdict"], "void")

    def test_a_stress_return_that_moved_is_a_touch(self):
        pid = self.lineage()
        new, _ = forward_db.engine_id(self.fdb, "equity-engine-1+dddddddddddd+fwd-1", at=3.0)
        self.days(pid, self.FLAT + [0.004] * 5, first=START, engine=new, r15=-3e-5)    # every r15 moved, r and w not
        self.sides(pid, sessions(START, 13), engine=new)
        self.night()
        self.assertEqual(self.verdicts()["equity:f1"]["verdict"], "void")

    def test_a_restated_history_is_carried_and_an_unexplained_move_is_a_touch(self):
        p1 = self.lineage("f1")
        p2 = self.row("f2", 1, first_day="2026-10-16")
        self.family("f2")
        n2 = self.days(p2, self.FLAT, first=START)
        self.sides(p2, n2)
        p3 = self.row("f3", 1, first_day="2026-10-16")
        self.family("f3")
        n3 = self.days(p3, self.FLAT, first=START)
        self.sides(p3, n3)
        self.night(now=PIN_AT)                                     # checkpoint 5 of f2 and f3 under engine 1
        # The vendor restated the history (an ex-day): E3's night under the old id said so for f1 and f3, then the
        # new id was written whole on today's store, every judged day a little moved and its bars hash too.
        for pid in (p1, p3):
            self.restated(pid, START.isoformat(), sessions(START, 8)[-1])
        new, _ = forward_db.engine_id(self.fdb, "equity-engine-1+eeeeeeeeeeee+fwd-1", at=3.0)
        moved = [v + 1e-5 for v in self.FLAT] + [0.004] * 5
        self.days(p1, moved, first=START, engine=new, bars="c" * 16)    # restated, and the record said so: carried
        self.days(p2, moved, first=START, engine=new, bars="c" * 16)    # moved with no restatement on record: a touch
        self.days(p3, moved, first=START, engine=new)                   # moved with the same bars: the engine's touch
        for pid in (p1, p2, p3):
            self.sides(pid, sessions(START, 13), engine=new)
        self.night()
        verdicts = self.verdicts()
        self.assertNotIn("equity:f1", verdicts)
        self.assertEqual(verdicts["equity:f2"]["verdict"], "void")
        self.assertEqual(verdicts["equity:f3"]["verdict"], "void")
        db = self.store()
        payload = json.loads(db.execute("SELECT payload FROM fwd1_events WHERE kind='engine_switched' AND "
                                        "lineage='equity:f1'").fetchone()[0])
        self.assertEqual((payload["touched"], payload["restated"]), (False, 5))
        db.close()

    def test_the_wait_is_bounded_by_the_stall_rule_and_a_new_id_asks_again(self):
        pid = self.lineage()
        new, _ = forward_db.engine_id(self.fdb, "equity-engine-1+ffffffffffff+fwd-1", at=3.0)
        later = sessions(START, 30)[10:]
        for i in range(FS.STALL_NIGHTS):
            self.advance(later[i])
            receipt = self.night()
        self.assertEqual(receipt.get("stalled"), 1)
        self.assertEqual(self.permits()["equity:f1"]["status"], "stalled")
        self.assertEqual(self.verdicts(), {})                      # nothing marks it
        self.advance(later[FS.STALL_NIGHTS])
        receipt = self.night()
        self.assertEqual(receipt.get("stalled_skipped"), 1)
        newer, _ = forward_db.engine_id(self.fdb, "equity-engine-1+999999999999+fwd-1", at=4.0)
        self.days(pid, self.FLAT + [0.004] * 5, first=START, engine=newer)
        self.sides(pid, sessions(START, 13), engine=newer)
        self.night()                                               # a new id: asked again, and carried
        self.assertEqual(self.permits()["equity:f1"]["status"], "pending")
        db = self.store()
        self.assertEqual(db.execute("SELECT engine FROM fwd1_checks WHERE k=10").fetchone()[0], newer)
        db.close()


class TheRestatedSides(Fixture):
    """A RESTATED DAY'S SIDES (the review's major): after an ex-day the vendor rescales the whole adjusted history and
    E3 keeps the first-written r, so a program's own forward run never reproduces the stored r of the days before it
    again. Its sides are still that day's when the run made the same orders that session (its lots in and out as the
    record counts them) from inputs the restatement moved (the bars hash of the day's decision)."""

    def test_a_restated_day_keeps_its_sides_and_a_different_order_does_not(self):
        self.family("f1")
        pid = self.row("f1", 1, first_day="2026-10-16")
        names = self.days(pid, [0.01 + 0.001 * (i % 3) for i in range(6)], first=START)
        ran = {d: v * 1.001 for d, v in self.recorded(pid).items()}         # every day moved past TOL
        bars = {d: "c" * 16 for d in names}                                  # ... by a restated history
        bars[names[4]] = "b" * 16                                            # this one with the stored inputs
        entries = {d: 0 for d in names}
        entries[names[3]] = 1                                                # this one with another order
        runs = FakeRuns(forward={"r": ran, "sides": {names[0]: 0.5}, "entries": entries,
                                 "exits": {d: 0 for d in names}, "bars": bars})
        receipt = self.night(runs, now=PIN_AT)
        db = self.store()
        held = {r["day"]: r["sides"] for r in db.execute("SELECT day, sides FROM fwd1_sides")}
        db.close()
        self.assertEqual(set(held), {names[0], names[1], names[2], names[5]})
        self.assertEqual(held[names[0]], 0.5)
        self.assertEqual(receipt["sides_restated"], 4)
        self.assertEqual(receipt["no_sides"], 1)                             # days 4 and 5 are not that run's


class TheStallRule(Fixture):
    def test_sides_that_never_come_stall_the_lineage_and_cost_no_run(self):
        self.pin_first()
        self.family("f1")
        pid = self.row("f1", 1, first_day="2026-10-16")
        self.days(pid, [0.01] * 6, first=START)
        later = sessions(START, 30)[10:]
        runs = FakeRuns()                                          # its forward run never finishes
        for i in range(FS.STALL_NIGHTS - 1):
            self.advance(later[i])
            self.night(runs)
            self.night(runs)                                       # the night's second run counts no night
        self.assertEqual(runs.calls["forward"], 2 * (FS.STALL_NIGHTS - 1))
        self.assertEqual(self.permits()["equity:f1"]["status"], "pending")
        self.advance(later[FS.STALL_NIGHTS - 1])
        receipt = self.night(runs)
        self.assertEqual(receipt["stalled"], 1)
        self.assertEqual(self.permits()["equity:f1"]["status"], "stalled")
        report = json.loads((self.root / FS.REPORT).read_text())
        self.assertEqual(report["stalled"][0]["cause"], "sides")
        calls = runs.calls["forward"]
        self.night(runs)
        self.advance(later[FS.STALL_NIGHTS])
        self.night(runs)
        self.assertEqual(runs.calls["forward"], calls)            # stalled: no run
        db = self.store()
        self.assertIsNone(db.execute("SELECT * FROM fwd1_verdicts").fetchone())     # nothing marks it
        db.close()

    def test_a_lineage_that_waits_goes_after_one_that_does_not(self):
        self.pin_first()
        for fid in ("a1", "z9"):
            self.family(fid)
        pa = self.row("a1", 1, first_day="2026-10-16")
        pz = self.row("z9", 1, first_day="2026-10-16")
        self.days(pa, [0.01] * 6, first=START)
        values = [0.004 if i % 2 else -0.004 for i in range(10)]
        self.days(pz, values[:9], first=START)
        order, case = [], self

        class Watch(FakeRuns):
            def forward_sides(self, program, typ, *, settings, fdb=None):
                order.append(program.key)
                if program.key.startswith("a1"):
                    raise RuntimeError("its child never finishes")
                return {"r": case.recorded(program.pid), "sides": {}}

        self.advance(sessions(START, 12)[10])
        self.night(Watch())
        self.assertEqual(order, ["a1@1", "z9@1"])
        order.clear()
        self.days(pz, values[9:], first=dt.date.fromisoformat(sessions(START, 10)[9]))
        self.advance(sessions(START, 12)[11])
        self.night(Watch())
        self.assertEqual(order, ["z9@1", "a1@1"])                 # a1 waited a night: it goes after


class TheCheckpointsReading(Fixture):
    def test_a_deferred_checkpoint_is_judged_on_its_first_reading(self):
        """A would-be pass whose floor waits on the House keeps the reading of the night it reached k counted days:
        a live-like row that comes a night late never makes a second reading (the review's fix)."""
        self.family("f1")
        pid = self.row("f1", 1, first_day="2026-10-16")
        values = [0.01 + 0.001 * (i % 3) for i in range(6)]
        names = self.days(pid, values, first=START)
        self.sides(pid, names, 0.5)
        FS.night(self.root, rule=self.rule, settings=self.settings, now=PIN_AT, base=None, release=None,
                 runs=FakeRuns(fail=True), families=self.families, clock=lambda: PIN_AT)
        db = self.store()
        self.assertIsNone(db.execute("SELECT * FROM fwd1_checks").fetchone())           # the floor waited
        db.close()
        x = [v - 2e-4 * (0.5 if i == 0 else 0.0) for i, v in enumerate(values[:5])]
        first = R.checkpoint(x, [v - 1e-5 for v in x], 5)                               # that night's reading
        for day in names[:5]:                                      # a late live-like re-price, far lower
            self.fdb.execute("INSERT INTO fwd_ll(pid, day, engine, r_ll, at) VALUES (?,?,?,?,?)",
                             (pid, day, self.engine, -0.02, 5.0))
        self.fdb.commit()
        self.night()
        db = self.store()
        check = dict(db.execute("SELECT * FROM fwd1_checks WHERE k=5").fetchone())
        self.assertAlmostEqual(check["t"], first["t"], places=12)
        self.assertAlmostEqual(check["s"], first["S"], places=12)
        self.assertEqual((check["ll"], check["passed"]), (0, 1))
        self.assertEqual(dict(db.execute("SELECT verdict FROM fwd1_verdicts").fetchone())["verdict"], "pass")
        self.assertEqual(db.execute("SELECT COUNT(*) FROM fwd1_pending WHERE k=5").fetchone()[0], 1)
        db.close()


class TheLiveness(Fixture):
    def test_a_stopped_representative_is_stopped_not_pending_and_runs_nothing(self):
        self.pin_first()
        self.family("f1")
        pid = self.row("f1", 1, first_day="2026-10-16")
        self.days(pid, [0.01] * 6, first=START)
        self.fdb.execute("INSERT INTO fwd_tags(pid, tag, value, at) VALUES (?, 'stopped', 'disqualified:x', 2.0)", (pid,))
        self.fdb.commit()
        runs = FakeRuns()
        receipt = self.night(runs)
        self.assertEqual((receipt["stopped"], runs.calls["forward"]), (1, 0))
        self.assertEqual(self.permits()["equity:f1"]["status"], "stopped")
        self.fdb.execute("INSERT INTO fwd_tags(pid, tag, value, at) VALUES (?, 'resumed', 'x', 3.0)", (pid,))
        self.fdb.commit()
        self.night(runs)
        self.assertEqual(self.permits()["equity:f1"]["status"], "pending")
        self.assertEqual(runs.calls["forward"], 1)

    def test_a_lineage_of_another_receipt_is_superseded(self):
        self.family("f1")
        pid = self.row("f1", 1, first_day="2026-10-16")
        self.days(pid, [0.01] * 3, first=START)
        self.first_night()
        self.assertEqual(self.permits()["equity:f1"]["status"], "pending")
        self.rule = R.Rule(receipt_sha256="d" * 64, figures=self.rule.figures)
        self.night()
        self.assertEqual(self.permits()["equity:f1"]["status"], "superseded")


class TheBudgetAndTheDeadline(Fixture):
    def test_the_nights_two_runs_share_one_budget(self):
        self.pin_first()
        self.family("f1")
        self.family("f2")
        p1 = self.row("f1", 1, first_day="2026-10-16")
        p2 = self.row("f2", 1, first_day="2026-10-16")
        self.days(p1, [0.01] * 6, first=START)
        self.days(p2, [0.01] * 6, first=START)
        t = [PIN_AT + 86400 * 20]

        class Slow(FakeRuns):
            def forward_sides(self, program, typ, *, settings, fdb=None):
                t[0] += 400.0
                return super().forward_sides(program, typ, settings=settings, fdb=fdb)

        settings = {"elane": {"fwd1": {"mode": "record", "cpu_seconds_night": 900}, "forward": {"mode": "record"}}}
        first = FS.night(self.root, rule=self.rule, settings=settings, now=t[0], base=None, release=None, runs=Slow(),
                         families=self.families, clock=lambda: t[0])
        self.assertEqual((first["budget"], first["seconds"]), (900.0, 800.0))
        second = FS.night(self.root, rule=self.rule, settings=settings, now=t[0], base=None, release=None,
                          runs=Slow(), families=self.families, clock=lambda: t[0])
        self.assertEqual(second["budget"], 100.0)                  # what the night's first run left
        t[0] += FS.NIGHT_WINDOW_S + 1
        third = FS.night(self.root, rule=self.rule, settings=settings, now=t[0], base=None, release=None, runs=Slow(),
                         families=self.families, clock=lambda: t[0])
        self.assertEqual(third["budget"], 900.0)                   # the next night's own

    def test_no_run_starts_at_the_deadline(self):
        self.pin_first()
        self.family("f1")
        pid = self.row("f1", 1, first_day="2026-10-16")
        self.days(pid, [0.01] * 6, first=START)
        runs = FakeRuns()
        now = PIN_AT + 86400 * 20
        receipt = FS.night(self.root, rule=self.rule, settings=self.settings, now=now, base=None, release=None,
                           runs=runs, families=self.families, clock=lambda: now, deadline=now + FS.MIN_RUN_S)
        self.assertEqual((runs.calls["forward"], receipt["deferred"]), (0, 1))

    def test_the_deadline_is_the_pre_open_or_the_wall(self):
        thursday_night = dt.datetime(2026, 10, 15, 22, 40, tzinfo=dt.timezone.utc).timestamp()
        friday_open = schedule.moments(dt.date(2026, 10, 16)).open_at
        self.assertEqual(FS.preopen_deadline(thursday_night), friday_open - 3600 - FS.MARGIN_S)
        preopen = friday_open - 3600 + 60                           # inside Friday's pre-open
        self.assertLess(FS.preopen_deadline(preopen), preopen)
        job = registry.by_name()["forward_screen"]
        self.assertEqual(job.wall, FS.WALL_S)
        self.assertLessEqual(job.grace, 2 * 3600)                   # after forward_xs it is done before the pre-open
        ctx = types.SimpleNamespace(root=self.root, now=lambda: friday_open - 3600 - 200, alert=lambda *a: None,
                                    config={})
        import league.swarm.settings as ss

        real, real_rule = ss.load, R.rule
        try:
            ss.load = lambda root, config=None: self.settings
            R.rule = lambda policy=None: (self.rule, None)
            self.assertIn("pre-open", FS.run(ctx)["why"])
        finally:
            ss.load, R.rule = real, real_rule


class TheIndexLineageUntried(Fixture):
    """L5 (A48): every permit row carries its lineage's FWD1_START ("start"); the swarm keeps an index-only case-N
    lineage's S2 try, while the file lists it pending, for the representative's own family and a start after the
    pin's, until the close of that session (league/swarm/elane_forward.py `untried`); once its family records the
    sealed pre-check the judge's next night voids it (A33 (4): `judge`'s "a case-N lineage reached a sealed pre-check
    after FWD1_START"), the file lists it "void" (not `JUDGED`) and it keeps its sealed path. One look: the S2 one,
    never a forward verdict beside it. The swarm store is a stand-in (its root and its clock: all `try_refused` reads
    of it)."""

    ON = {"elane": {"fwd1": {"mode": "record", "seats": "on"}}}

    def index(self, fid: str) -> dict:
        fam = self.family(fid)
        fam["spec"]["symbols"] = ["SPY", "QQQ"]                    # index-only: R-SEC lets its try through
        return fam

    def test_every_permit_row_carries_its_start(self):
        for fid, first_day in (("f1", "2026-10-16"), ("f2", "2026-10-13"), ("f3", "2026-10-19")):
            self.index(fid)
            self.row(fid, 1, first_day=first_day)
        self.first_night()
        db = self.store()
        starts = {str(r["lineage"]): str(r["start"]) for r in db.execute("SELECT lineage, start FROM fwd1_lineages")}
        db.close()
        # FWD1_START = max(first_day, the pin's first judged session Oct 16)
        self.assertEqual(starts, {"equity:f1": "2026-10-16", "equity:f2": "2026-10-16", "equity:f3": "2026-10-19"})
        doc = json.loads((self.root / FS.PERMITS).read_text())
        self.assertEqual(doc["version"], FS.PERMITS_VERSION)
        self.assertEqual(FS.PERMITS_VERSION, 1)                     # an added key: the version stays
        self.assertEqual({k: v["start"] for k, v in doc["lineages"].items()}, starts)
        self.assertEqual({v["status"] for v in doc["lineages"].values()}, {"pending"})
        for row in doc["lineages"].values():
            self.assertEqual(dt.date.fromisoformat(row["start"]).isoformat(), row["start"])
            self.assertTrue(schedule.is_session(row["start"]))

    def test_the_whole_path_an_untried_index_lineage_takes_its_try_and_is_voided(self):
        from league.swarm import elane_forward as EF

        fam = self.index("f1")
        v1 = self.row("f1", 1, first_day="2026-10-19", reason="train_fail")   # its v1 failed Train, after the pin
        self.first_night()                                          # Thu Oct 15 14:00Z: sighted pending, start Mon
        row = self.permits()["equity:f1"]
        self.assertEqual((row["status"], row["case"], row["type"], row["start"], row["family"]),
                         ("pending", "N", "ETF", "2026-10-19", "f1"))
        self.assertEqual(json.loads((self.root / FS.PERMITS).read_text())["start"], START.isoformat())   # the pin's
        close = schedule.moments(dt.date(2026, 10, 19)).close_at
        swarm = types.SimpleNamespace(root=self.root, clock=lambda: PIN_AT + 3 * 3600.0)
        # its v2 passes Train hours later: the S2 try is open while Mon Oct 19's session has not closed ...
        self.assertTrue(EF.untried(swarm, fam, row, pin_start=START.isoformat()))
        self.assertIsNone(EF.try_refused(swarm, fam, self.ON))
        self.assertIsNone(EF.try_refused(swarm, fam, self.ON, now=close - 1.0))
        # ... and shut from that close (as A39 built it), until FWD1 has judged it; a sibling family never had it
        self.assertEqual(EF.try_refused(swarm, fam, self.ON, now=close), EF.REFUSED)
        sibling = self.index("f1b")
        sibling["lineage"] = "f1"
        self.assertEqual(EF.try_refused(swarm, sibling, self.ON), EF.REFUSED)
        # v2 registered (train_pass, the same first_day) and its S2 try taken before the close (elane.validate's record)
        self.row("f1", 2, first_day="2026-10-19")
        fam["state"]["elane_try"] = {"version": 2, "first": True, "precheck": True, "entered": True, "retry_sha": None}
        self.days(v1, [0.0], first=dt.date(2026, 10, 19))           # the record's night of Oct 19 runs after the close
        evening = close + 2.5 * 3600.0
        receipt = self.night(now=evening)
        db = self.store()
        verdict = dict(db.execute("SELECT * FROM fwd1_verdicts WHERE lineage='equity:f1'").fetchone())
        checks = db.execute("SELECT COUNT(*) FROM fwd1_checks").fetchone()[0]
        voids = [dict(r) for r in db.execute("SELECT * FROM fwd1_events WHERE kind='void'")]
        db.close()
        self.assertEqual(verdict["verdict"], "void")
        self.assertEqual(receipt.get("checks", 0), 0)
        self.assertEqual(checks, 0)                                 # judged no further: no checkpoint read
        self.assertEqual(len(voids), 1)
        self.assertIn("reached a sealed pre-check after FWD1_START", voids[0]["payload"])
        listed = self.permits()["equity:f1"]
        self.assertEqual((listed["status"], listed["start"]), ("void", "2026-10-19"))
        self.assertNotIn("void", EF.JUDGED)
        self.assertIsNone(EF.try_refused(swarm, fam, self.ON, now=evening))   # its sealed path stands
        self.assertIsNone(EF.try_refused(swarm, fam, self.ON, now=evening + 86400.0 * 30))
        self.night(now=evening + 86400.0)                           # nothing judges it again
        self.assertEqual(self.permits()["equity:f1"]["status"], "void")

    def test_the_motivating_timing_writes_a_kept_event_before_the_void(self):
        """v1 sighted, v2 passes Train with the same first_day and takes its exempt try before the next night: that
        night's `repick` reads v2 as better but sealed (another case), keeps v1 with a `kept` event and the job warns
        (`repick_kept`), then the judge voids the lineage. Expected, not a fault."""
        fam = self.index("f1")
        self.row("f1", 1, first_day="2026-10-19", reason="train_fail")
        self.first_night()
        self.row("f1", 2, first_day="2026-10-19")
        fam["state"]["elane_try"] = {"version": 2, "first": True, "precheck": True, "entered": True, "retry_sha": None}
        thu_night = schedule.moments(dt.date(2026, 10, 15)).close_at + 3 * 3600.0
        receipt = self.night(now=thu_night)
        db = self.store()
        kinds = [str(r["kind"]) for r in db.execute("SELECT kind FROM fwd1_events WHERE kind IN ('kept', 'void') "
                                                     "ORDER BY seq")]
        verdict = db.execute("SELECT verdict FROM fwd1_verdicts WHERE lineage='equity:f1'").fetchone()[0]
        db.close()
        self.assertEqual(kinds, ["kept", "void"])
        self.assertEqual(receipt.get("repick_kept"), 1)
        self.assertEqual(verdict, "void")

    def test_a_lineage_registered_before_the_pin_is_refused(self):
        """FWD1_START = the pin's start when the lineage's first_day is earlier: its forward days are in the record
        already, so no exemption (the file's top-level start is not before the row's)."""
        from league.swarm import elane_forward as EF

        fam = self.index("f2")
        pid = self.row("f2", 1, first_day="2026-10-13")
        self.days(pid, [0.001, -0.002], first=dt.date(2026, 10, 13))
        self.first_night()
        row = self.permits()["equity:f2"]
        self.assertEqual((row["status"], row["start"]), ("pending", "2026-10-16"))
        swarm = types.SimpleNamespace(root=self.root, clock=lambda: PIN_AT + 3600.0)
        self.assertEqual(EF.try_refused(swarm, fam, self.ON), EF.REFUSED)

    def test_a_pending_lineage_untried_by_the_close_stays_judged_and_refused(self):
        from league.swarm import elane_forward as EF

        fam = self.index("f1")
        pid = self.row("f1", 1, first_day="2026-10-19")
        self.first_night()
        close = schedule.moments(dt.date(2026, 10, 19)).close_at
        swarm = types.SimpleNamespace(root=self.root, clock=lambda: close - 3600.0)
        self.assertIsNone(EF.try_refused(swarm, fam, self.ON))       # open before the close ...
        names = self.days(pid, [0.0, 0.0], first=dt.date(2026, 10, 19))
        self.night(now=schedule.moments(dt.date.fromisoformat(names[-1])).close_at + 9000.0)
        self.assertEqual(self.permits()["equity:f1"]["status"], "pending")
        swarm = types.SimpleNamespace(root=self.root, clock=lambda: close + 9000.0)
        self.assertEqual(EF.try_refused(swarm, fam, self.ON), EF.REFUSED)    # ... FWD1 judges it: no S2 look now


class TheJob(Fixture):
    def test_switches_and_no_pin(self):
        ctx = types.SimpleNamespace(root=self.root, now=lambda: PIN_AT + 86400 * 5, alert=lambda *a: None, config={})
        import league.swarm.settings as ss

        real = ss.load
        try:
            ss.load = lambda root, config=None: {"elane": {"fwd1": {"mode": "off"}}}
            self.assertEqual(FS.run(ctx)["why"], "elane.fwd1.mode is off")
            ss.load = lambda root, config=None: {"elane": {"fwd1": {"mode": "record"}, "forward": {"mode": "off"}}}
            self.assertIn("elane.forward.mode is off", FS.run(ctx)["why"])
        finally:
            ss.load = real
        self.assertEqual(FS.cfg({})["mode"], "off")
        self.assertEqual(FS.cfg({})["seats"], "off")
        self.assertEqual(FS.cfg({"elane": {"fwd1": {"mode": "record", "seats": "on", "cpu_seconds_night": 99999}}}),
                         {"mode": "record", "seats": "on", "cpu_seconds_night": 2400, "run_budget_seconds": 300})

    def test_sides_from_lots_both_ways(self):
        lots = [{"lid": 1, "weight": 0.25, "entry_day": "2026-10-16", "exit_day": "2026-10-19"},
                {"lid": 2, "weight": 0.25, "entry_day": "2026-10-19", "exit_day": None}]
        self.assertEqual(FS.lot_sides({"lots": lots}), {"2026-10-16": 0.25, "2026-10-19": 0.5})
        with self.assertRaises(ValueError):
            FS.lot_sides({"lots": [{"lid": 3, "weight": "x", "entry_day": "2026-10-16"}]})

    def test_the_registry_runs_it_after_both_nights(self):
        job = registry.by_name()["forward_screen"]
        self.assertEqual(job.module, "league.ops.forward_screen")
        self.assertEqual({(t.kind, t.job) for t in job.triggers}, {("after", "forward_shadow"), ("after", "forward_xs")})
        self.assertTrue(job.in_pause)
        names = [j.name for j in registry.JOBS]
        self.assertGreater(names.index("forward_screen"), names.index("forward_xs"))

    def test_the_constants_the_swarm_holds(self):
        from league.swarm import elane, elane_forward, elane_seal, elane_xs

        self.assertEqual(elane_forward.PERMITS, FS.PERMITS)
        self.assertEqual(elane_forward.PERMITS_VERSION, FS.PERMITS_VERSION)
        self.assertIn(elane_forward.STATE_KEY, elane_seal.SEALED_KEYS)
        self.assertEqual(set(FS.SEALED_STATE), {elane.TRY_KEY, elane.VERDICTS_KEY, elane.LOOK_KEY,
                                                elane_xs.PRECHECK_KEY, elane_xs.LOOK_KEY})
        self.assertEqual(FS.ENGINE_TOUCH, forward_db.TOL)

    def test_the_seal_no_generator_side_module_imports_the_judge(self):
        import ast

        for top in ("swarm", "equity", "live", "gym", "xs"):
            for path in (REPO / "league" / top).rglob("*.py"):
                tree = ast.parse(path.read_text(encoding="utf-8"))
                for node in ast.walk(tree):
                    names = []
                    if isinstance(node, ast.Import):
                        names = [a.name for a in node.names]
                    elif isinstance(node, ast.ImportFrom):
                        names = [f"{node.module or ''}.{a.name}" for a in node.names] + [node.module or ""]
                    for name in names:
                        with self.subTest(path=str(path.relative_to(REPO)), name=name):
                            self.assertNotIn("forward_screen", name)
                            self.assertNotIn("fwd1_rule", name)
                text = path.read_text(encoding="utf-8")
                self.assertNotIn(FS.DB, text, str(path))
                self.assertNotIn(FS.REPORT, text, str(path))


#: Thursday Oct 15 22:30Z: after the record's night of Oct 15, before Friday Oct 16 (the first forward day) opens.
EVE = dt.datetime(2026, 10, 15, 22, 30, tzinfo=dt.timezone.utc).timestamp()
#: The four sector families the 08:06Z run of Oct 15 sighted on their Train-failed v1: the versions registered then,
#: and the version that passed Train (registered later with the same first_day).
FOUR = {"sector-sync-beta": (("train_fail", "train_fail", "train_pass"), 3),
        "sector-turn-month-beta": (("train_fail", "train_pass"), 2),
        "sector-monthly-rotation": (("train_fail", "train_pass"), 2),
        "defensive-low-vol-relative": (("train_fail", "train_fail", "train_fail", "train_pass"), 4)}


class TheRepresentativeBeforeAnyForwardDay(Fixture):
    """THE REPRESENTATIVE BEFORE ANY FORWARD DAY (`repick`): a lineage sighted on a failed version takes the version the
    rule prefers, of the same first_day, while no forward day and no judge row of it exists; then it is frozen."""

    def sighted_on_v1(self, fid: str = "f1") -> int:
        """A family whose Train-failed v1 (first_day Oct 16) is all the registry holds when the pin is first seen."""
        self.family(fid)
        pid = self.row(fid, 1, reason="train_fail", first_day="2026-10-16")
        return pid

    def lineage(self, fid: str = "f1") -> dict:
        db = self.store()
        try:
            return dict(db.execute("SELECT * FROM fwd1_lineages WHERE lineage=?", (f"equity:{fid}",)).fetchone())
        finally:
            db.close()

    def repicks(self, fid: str = "f1") -> list[dict]:
        db = self.store()
        try:
            return [dict(r) for r in db.execute("SELECT * FROM fwd1_events WHERE kind='repicked' AND lineage=? "
                                                "ORDER BY seq", (f"equity:{fid}",))]
        finally:
            db.close()

    def test_the_four_families_take_their_passing_versions_and_one_event_each(self):
        firsts = {fid: self.sighted_on_v1(fid) for fid in FOUR}
        self.family("steady")
        steady = self.row("steady", 1, first_day="2026-10-16")            # its v1 passed: already the rule's
        self.first_night()
        before = {fid: self.lineage(fid) for fid in (*FOUR, "steady")}
        self.assertEqual({fid: before[fid]["rep"] for fid in FOUR}, firsts)  # sighted on the failed v1
        passing = {}
        for fid, (reasons, passed) in FOUR.items():
            for n, reason in enumerate(reasons[1:], start=2):
                pid = self.row(fid, n, reason=reason, first_day="2026-10-16")
                if n == passed:
                    passing[fid] = pid
            self.row(fid, len(reasons) + 1, first_day="2026-10-19")           # a later first_day: never chosen
        self.row("steady", 2, first_day="2026-10-16")                         # a second pass: not the lowest pid
        receipt = self.night(now=EVE)
        self.assertEqual(receipt["repicked"], 4)
        self.assertNotIn("repick_frozen", receipt)
        permits = self.permits()
        for fid, (reasons, passed) in FOUR.items():
            with self.subTest(family=fid):
                lin, old = self.lineage(fid), before[fid]
                self.assertEqual((lin["rep"], lin["version"], lin["family"]), (passing[fid], passed, fid))
                self.assertEqual(lin["run_sha"], f"{passing[fid]:064d}")
                self.assertEqual(lin["row_hash"], f"{passing[fid]:063d}h")
                self.assertEqual(lin["versions"], len(reasons) + 1)
                self.assertEqual((lin["case_"], lin["judged"], lin["why"], lin["type"]), ("N", 1, None, "ETF"))
                # the lineage, its start, its receipt and its first sighting stand
                self.assertEqual({k: lin[k] for k in ("lineage", "start", "receipt", "at")},
                                 {k: old[k] for k in ("lineage", "start", "receipt", "at")})
                # THE PLACEBO SEED follows the new row hash (no day was read under the old one)
                self.assertNotEqual(R.placebo_seed(self.rule.receipt_sha256, lin["row_hash"]),
                                    R.placebo_seed(self.rule.receipt_sha256, old["row_hash"]))
                events = self.repicks(fid)
                self.assertEqual(len(events), 1)
                self.assertEqual((events[0]["pid"], events[0]["once"]), (passing[fid], f"{firsts[fid]}>{passing[fid]}"))
                payload = json.loads(events[0]["payload"])
                self.assertEqual((payload["from"], payload["to"], payload["from_version"], payload["to_version"]),
                                 (firsts[fid], passing[fid], 1, passed))
                self.assertEqual(payload["why"], FS.REPICK_WHY)
                self.assertEqual(payload["was"]["row_hash"], old["row_hash"])
                self.assertEqual((permits[f"equity:{fid}"]["status"], permits[f"equity:{fid}"]["version"]),
                                 ("pending", passed))
        self.assertEqual(self.lineage("steady"), before["steady"])           # already the rule's: untouched
        self.assertEqual(self.lineage("steady")["rep"], steady)
        self.assertEqual(self.repicks("steady"), [])
        again = self.night(now=EVE + 600)                                    # a second run that night: no change
        self.assertNotIn("repicked", again)
        self.assertEqual(sum(len(self.repicks(fid)) for fid in FOUR), 4)     # the event is written once a change

    def test_the_judge_reads_the_version_it_repicked(self):
        self.sighted_on_v1()
        self.first_night()
        passed = self.row("f1", 2, first_day="2026-10-16")
        self.assertEqual(self.night(now=EVE)["repicked"], 1)
        names = self.days(passed, [0.01 + 0.001 * (i % 3) for i in range(12)], first=START)
        self.sides(passed, names, 0.5)
        self.night()
        db = self.store()
        v = dict(db.execute("SELECT * FROM fwd1_verdicts").fetchone())
        db.close()
        self.assertEqual((v["verdict"], v["pid"]), ("pass", passed))
        self.assertEqual((self.permits()["equity:f1"]["version"], self.permits()["equity:f1"]["run_sha"]),
                         (2, f"{passed:064d}"))

    def test_no_repick_once_a_forward_day_exists_for_any_pid_of_the_lineage(self):
        for which in ("the failed v1", "the passing v2"):
            with self.subTest(day_of=which):
                self.tearDown()
                self.setUp()
                v1 = self.sighted_on_v1()
                self.first_night()
                v2 = self.row("f1", 2, first_day="2026-10-16")
                self.days(v1 if which == "the failed v1" else v2, [0.0], first=START)
                receipt = self.night(now=EVE)
                self.assertNotIn("repicked", receipt)
                self.assertEqual(receipt["repick_frozen"], 1)
                self.assertEqual(self.lineage()["rep"], v1)
                self.assertEqual(self.repicks(), [])

    def test_no_repick_once_the_record_ran_through_its_first_day_or_the_day_opened(self):
        v1 = self.sighted_on_v1()
        self.first_night()
        self.row("f1", 2, first_day="2026-10-16")
        opened = dt.datetime(2026, 10, 16, 13, 30, tzinfo=dt.timezone.utc).timestamp()   # 09:30 New York
        self.assertEqual(self.night(now=opened)["repick_frozen"], 1)        # the forward day has begun
        self.assertEqual(self.lineage()["rep"], v1)
        db = self.store()
        self.assertIsNone(FS.frozen(db, self.fdb, "equity:f1", [v1, v1 + 1], "2026-10-16", EVE))
        self.advance("2026-10-16")                                          # a night of the record through it
        self.assertEqual(FS.frozen(db, self.fdb, "equity:f1", [v1, v1 + 1], "2026-10-16", EVE), "counted")
        db.close()
        self.assertEqual(self.night(now=EVE)["repick_frozen"], 1)
        self.assertEqual(self.lineage()["rep"], v1)

    def test_no_repick_once_a_judge_row_exists(self):
        cases = {
            "a checkpoint": "INSERT INTO fwd1_checks(lineage, k, pid, engine, day, t, s, s15, g_bp, ll, count, draws, "
                            "c_used, passed, why, at) VALUES ('equity:f1', 5, {v1}, 1, '2026-10-22', 0.1, 0.0, 0.0, 2, "
                            "0, NULL, NULL, NULL, 0, 'x', 1)",
            "a pending reading": "INSERT INTO fwd1_pending(lineage, k, engine, pid, day, t, s, s15, g_bp, ll, at) "
                                 "VALUES ('equity:f1', 5, 1, {v1}, '2026-10-22', 3.0, 0.1, 0.1, 2, 0, 1)",
            "a verdict": "INSERT INTO fwd1_verdicts(lineage, pid, verdict, k, day, c_used, why, beside, words, at) "
                         "VALUES ('equity:f1', {v1}, 'void', NULL, NULL, NULL, 'x', NULL, NULL, 1)",
            "sides": "INSERT INTO fwd1_sides(pid, day, engine, sides, at) VALUES ({v1}, '2026-10-16', 1, 0.0, 1)",
            "a floor": "INSERT INTO fwd1_floors(pid, case_, k_own, cells, drift, why, seconds, at) VALUES "
                       "({v1}, 'N', 150, '{{}}', NULL, NULL, 0, 1)",
            "a wait": "INSERT INTO fwd1_events(at, kind, lineage, pid, once, payload) VALUES "
                      "(1, 'waited', 'equity:f1', {v1}, 'sides:1:2026-10-16', '{{}}')"}
        for name, sql in cases.items():
            with self.subTest(judge_row=name):
                self.tearDown()
                self.setUp()
                v1 = self.sighted_on_v1()
                self.first_night()
                v2 = self.row("f1", 2, first_day="2026-10-16")
                db = self.store()
                with db:
                    db.execute(sql.format(v1=v1))
                self.assertEqual(FS.frozen(db, self.fdb, "equity:f1", [v1, v2], "2026-10-16", EVE), "judged")
                db.close()
                receipt = self.night(now=EVE)
                self.assertNotIn("repicked", receipt)
                self.assertEqual(self.lineage()["rep"], v1)
                self.assertEqual(self.repicks(), [])

    def test_the_store_allows_the_repick_update_alone(self):
        v1 = self.sighted_on_v1()
        self.first_night()
        v2 = self.row("f1", 2, first_day="2026-10-16")
        db = self.store()
        with self.assertRaises(sqlite3.DatabaseError):                     # no event: refused
            db.execute("UPDATE fwd1_lineages SET rep=? WHERE lineage='equity:f1'", (v2,))
        db.rollback()
        with self.assertRaises(sqlite3.DatabaseError):                     # the same pid: no re-pick, refused
            db.execute("UPDATE fwd1_lineages SET why='x' WHERE lineage='equity:f1'")
        db.rollback()
        with self.assertRaises(sqlite3.DatabaseError):                     # its start moved: refused
            FS.event(db, "repicked", at=1.0, lineage="equity:f1", pid=v2, once=f"{v1}>{v2}")
            db.execute("UPDATE fwd1_lineages SET rep=?, start='2026-10-19' WHERE lineage='equity:f1'", (v2,))
        db.rollback()
        for column, value in (("type", "PANEL"), ("case_", "XS1"), ("judged", 0), ("why", "x")):
            with self.assertRaises(sqlite3.DatabaseError, msg=column):     # what it is judged as moved: refused
                FS.event(db, "repicked", at=1.0, lineage="equity:f1", pid=v2, once=f"{v1}>{v2}")
                db.execute(f"UPDATE fwd1_lineages SET rep=?, {column}=? WHERE lineage='equity:f1'", (v2, value))
            db.rollback()
        with self.assertRaises(sqlite3.DatabaseError):                     # a checkpoint exists: refused
            db.execute("INSERT INTO fwd1_checks(lineage, k, pid, engine, day, t, s, s15, g_bp, ll, count, draws, "
                       "c_used, passed, why, at) VALUES ('equity:f1', 5, ?, 1, '2026-10-22', 0.1, 0.0, 0.0, 2, 0, "
                       "NULL, NULL, NULL, 0, 'x', 1)", (v1,))
            FS.event(db, "repicked", at=1.0, lineage="equity:f1", pid=v2, once=f"{v1}>{v2}")
            db.execute("UPDATE fwd1_lineages SET rep=? WHERE lineage='equity:f1'", (v2,))
        db.rollback()
        with self.assertRaises(sqlite3.DatabaseError):
            db.execute("DELETE FROM fwd1_lineages")
        db.rollback()
        with db:                                                           # the event, then the row: allowed
            FS.event(db, "repicked", at=1.0, lineage="equity:f1", pid=v2, once=f"{v1}>{v2}")
            db.execute("UPDATE fwd1_lineages SET rep=? WHERE lineage='equity:f1'", (v2,))
        self.assertEqual(self.lineage()["rep"], v2)
        db.close()

    def test_an_unreadable_forward_record_repicks_nothing(self):
        v1 = self.sighted_on_v1()
        self.first_night()
        v2 = self.row("f1", 2, first_day="2026-10-16")

        class Unreadable:
            """The forward record, but its day rows cannot be read."""

            def __init__(self, db, table):
                self.db, self.table = db, table

            def execute(self, sql, *args):
                if self.table in sql:
                    raise sqlite3.OperationalError("database is locked")
                return self.db.execute(sql, *args)

        db = self.store()
        for table in (*FS.RECORD_DAY_TABLES, "fwd_runs"):
            with self.subTest(table=table):
                fdb = Unreadable(self.fdb, table)
                self.assertEqual(FS.frozen(db, fdb, "equity:f1", [v1, v2], "2026-10-16", EVE), "unreadable")
                got = FS.repick(db, fdb, self.families, rule=self.rule, pin_start=START, now=EVE)
                self.assertEqual(got, {"repicked": 0, "repick_frozen": 0, "repick_kept": 0, "repick_unread": 1})
        got = FS.repick(db, Unreadable(self.fdb, "fwd_registry"), self.families, rule=self.rule, pin_start=START,
                        now=EVE)
        self.assertEqual(got["repick_unread"], 1)
        db.close()
        self.assertEqual(self.lineage()["rep"], v1)
        self.assertEqual(self.repicks(), [])
        self.fdb.execute("DROP TABLE fwd_days")                            # the whole night: kept, said in the receipt
        self.fdb.commit()
        receipt = self.night(now=EVE)
        self.assertEqual(receipt["repick_unread"], 1)
        self.assertEqual(self.lineage()["rep"], v1)

    def kept(self, fid: str = "f1") -> list[dict]:
        db = self.store()
        try:
            return [dict(r) for r in db.execute("SELECT * FROM fwd1_events WHERE kind='kept' AND lineage=? "
                                                "ORDER BY seq", (f"equity:{fid}",))]
        finally:
            db.close()

    def test_every_per_pid_table_of_the_record_freezes(self):
        """A row of any per-pid table of the record (RECORD_DAY_TABLES) for a pid of the lineage is a forward day of it:
        a checkpoint, a live-like re-price, a twin, a closed live lot, a participation row."""
        rows = {
            "fwd_checks": ("INSERT INTO fwd_checks(pid, n, day, engine, t_r, sum_r, sum_r15, t_x, mean_w, p_x, t_x0, "
                           "p_x0, final, at) VALUES (?, 20, '2026-10-16', {engine}, 0, 0, 0, 0, 0, 0, NULL, NULL, 0, 1)"),
            "fwd_ll": "INSERT INTO fwd_ll(pid, day, engine, r_ll, at) VALUES (?, '2026-10-16', {engine}, 0, 1)",
            "fwd_twins": ("INSERT INTO fwd_twins(instance, day, pid, live_keys, shadow_keys, agree, why, at) VALUES "
                          "('f1@2:r', '2026-10-15', ?, '[]', '[]', 1, NULL, 1)"),
            "fwd_lotgap": ("INSERT INTO fwd_lotgap(lid, instance, pid, symbol, opened_day, exit_day, entry_at, exit_at, "
                           "model_bp, at) VALUES (1, 'f1@2:r', ?, 'SPY', '2026-10-13', '2026-10-14', 'a', 'b', 2.0, 1.0)"),
            "fwd_part": ("INSERT INTO fwd_part(instance, through, pid, matched, missed, extra, at) VALUES "
                         "('f1@2:r', '2026-10-14', ?, 1, 0, 0, 1.0)")}
        self.assertEqual(set(rows), set(FS.RECORD_DAY_TABLES) - {"fwd_days"})   # fwd_days: the test above
        for table, sql in rows.items():
            for which in ("v1", "v2"):
                with self.subTest(table=table, pid_of=which):
                    self.tearDown()
                    self.setUp()
                    v1 = self.sighted_on_v1()
                    self.first_night()
                    v2 = self.row("f1", 2, reason="seed", first_day="2026-10-16")
                    self.fdb.execute(sql.format(engine=self.engine), (v1 if which == "v1" else v2,))
                    self.fdb.commit()
                    db = self.store()
                    self.assertEqual(FS.frozen(db, self.fdb, "equity:f1", [v1, v2], "2026-10-16", EVE), "forward_day")
                    db.close()
                    receipt = self.night(now=EVE)
                    self.assertNotIn("repicked", receipt)
                    self.assertEqual((receipt["repick_frozen"], receipt["repick_kept"]), (1, 1))
                    self.assertEqual(self.lineage()["rep"], v1)
                    self.assertEqual(self.repicks(), [])
                    self.assertEqual(json.loads(self.kept()[0]["payload"])["because"],
                                     FS.KEPT_BECAUSE["forward_day"])

    def test_the_last_run_that_can_repick_is_before_the_first_days_open(self):
        """The window closes at the first_day's open (Fri Oct 16 13:30Z), not at the record's night of it; the job is
        quiet from 13:00Z and skips near the 12:28Z pre-open deadline, so Thursday's night run is the one."""
        v1 = self.sighted_on_v1()
        self.first_night()
        v2 = self.row("f1", 2, first_day="2026-10-16")
        self.advance("2026-10-15")                                          # Thursday's record night ran
        at = {hm: dt.datetime(2026, 10, 16, *hm, tzinfo=dt.timezone.utc).timestamp()
              for hm in ((12, 0), (12, 59), (13, 0), (13, 30), (21, 45))}
        db = self.store()
        self.assertIsNone(FS.frozen(db, self.fdb, "equity:f1", [v1, v2], "2026-10-16", EVE))
        self.assertIsNone(FS.frozen(db, self.fdb, "equity:f1", [v1, v2], "2026-10-16", at[(12, 59)]))
        for hm in ((13, 30), (21, 45)):                                     # Friday evening, before its record night
            self.assertEqual(FS.frozen(db, self.fdb, "equity:f1", [v1, v2], "2026-10-16", at[hm]), "begun")
        db.close()
        from league.ops import forward_shadow

        self.assertFalse(forward_shadow.quiet(EVE))
        self.assertFalse(forward_shadow.quiet(at[(12, 59)]))
        self.assertTrue(forward_shadow.quiet(at[(13, 0)]))                  # the job skips from 09:00 New York
        self.assertLess(FS.preopen_deadline(at[(12, 0)]) - at[(12, 0)], 3600)   # and before the 12:28Z deadline
        late = self.night(now=at[(21, 45)])
        self.assertNotIn("repicked", late)
        self.assertEqual((late["repick_frozen"], late["repick_kept"]), (1, 1))
        self.assertEqual(self.lineage()["rep"], v1)
        self.assertEqual(json.loads(self.kept()[0]["payload"])["because"], FS.KEPT_BECAUSE["begun"])

    def test_a_rebirth_in_the_same_lineage_takes_its_passing_family(self):
        """The fifth lineage of Oct 15: four failed versions of one family, then a passing family of the same lineage
        with the same first_day."""
        self.family("rev", lineage="rev")
        failed = [self.row("rev", n, reason="train_fail", first_day="2026-10-16") for n in (1, 2)]
        self.first_night()
        failed += [self.row("rev", n, reason="train_fail", first_day="2026-10-16") for n in (3, 4)]
        self.family("rev-exhaustion", lineage="rev")
        born = self.row("rev-exhaustion", 1, first_day="2026-10-16", lineage="equity:rev")
        before = self.lineage("rev")
        self.assertEqual(self.night(now=EVE)["repicked"], 1)
        lin = self.lineage("rev")
        self.assertEqual((lin["rep"], lin["family"], lin["version"], lin["versions"]), (born, "rev-exhaustion", 1, 5))
        self.assertEqual({k: lin[k] for k in FS.REPICK_KEEPS}, {k: before[k] for k in FS.REPICK_KEEPS})
        self.assertEqual([e["once"] for e in self.repicks("rev")], [f"{failed[0]}>{born}"])
        self.assertEqual(self.kept("rev"), [])

    def test_a_better_pid_that_would_change_what_is_judged_is_kept(self):
        """A re-pick changes which version is judged, never what it is judged as: a better pid that would move the
        row's type, case, judged flag or reason is kept off, once, and the lineage stays as sighted."""
        shapes = {"etf to panel": (dict(panel=True), ["type"]),
                  "its family gone from the swarm store": (dict(fid="ghost"), ["type", "case_", "judged", "why"]),
                  "a live row": (dict(reason="live"), ["case_", "judged", "why"])}
        for name, (kw, changes) in shapes.items():
            with self.subTest(shape=name):
                self.tearDown()
                self.setUp()
                v1 = self.sighted_on_v1()
                self.first_night()
                before = self.lineage()
                fid = kw.pop("fid", "f1")
                v2 = self.row(fid, 2, first_day="2026-10-16", lineage="equity:f1", **kw)
                receipt = self.night(now=EVE)
                self.assertNotIn("repicked", receipt)
                self.assertEqual((receipt["repick_frozen"], receipt["repick_kept"]), (1, 1))
                self.assertEqual(self.lineage(), before)
                self.assertEqual(self.repicks(), [])
                (kept,) = self.kept()
                payload = json.loads(kept["payload"])
                self.assertEqual((kept["pid"], kept["once"]), (v2, f"{v1}>{v2}"))
                self.assertEqual((payload["because"], payload["changes"], payload["why"]),
                                 (FS.KEPT_BECAUSE["keeps"], changes, FS.KEPT_WHY))
                again = self.night(now=EVE + 600)                           # the event is written once
                self.assertEqual((again["repick_frozen"], again.get("repick_kept")), (1, None))
                self.assertEqual(len(self.kept()), 1)

    def test_the_same_facts_give_the_same_record_whenever_the_better_version_came(self):
        """Two lineages with the same registry rows and the same sealed try of v2 (after the sighting, before
        FWD1_START): one sighted before v2 was registered, one after. Both are voided by the judge as case N."""
        for structure, panel in (("etf", False), ("panel", True)):
            with self.subTest(structure=structure):
                self.tearDown()
                self.setUp()
                for fid in ("a", "b"):
                    self.family(fid, structure=structure)
                self.row("a", 1, reason="train_fail", first_day="2026-10-16", panel=panel)
                self.row("b", 1, reason="train_fail", first_day="2026-10-16", panel=panel)
                b2 = self.row("b", 2, first_day="2026-10-16", panel=panel)   # before the sighting
                self.first_night()
                a2 = self.row("a", 2, first_day="2026-10-16", panel=panel)   # after it
                for pid in (a2, b2):
                    self.fdb.execute("INSERT INTO fwd_tags(pid, tag, value, at) VALUES (?, 'try', '', 1.0)", (pid,))
                self.fdb.commit()
                receipt = self.night(now=EVE)
                self.assertNotIn("repicked", receipt)
                self.assertEqual(receipt["repick_kept"], 1)
                db = self.store()
                got = {r["lineage"]: (r["case_"], r["judged"]) for r in db.execute("SELECT * FROM fwd1_lineages")}
                verdicts = {r["lineage"]: r["verdict"] for r in db.execute("SELECT * FROM fwd1_verdicts")}
                db.close()
                self.assertEqual(got, {"equity:a": ("N", 1), "equity:b": ("N", 1)})
                self.assertEqual(verdicts, {"equity:a": "void", "equity:b": "void"})
                self.assertEqual(json.loads(self.kept("a")[0]["payload"])["changes"],
                                 ["case_", "judged", "why"] if structure == "etf" else ["case_"])

    def test_the_job_warns_when_a_better_version_is_first_kept(self):
        ctx = types.SimpleNamespace(root=self.root, now=lambda: EVE, config={}, alerts=[])
        ctx.alert = lambda level, text: ctx.alerts.append((level, text))
        import league.swarm.settings as ss

        with mock.patch.object(ss, "load", lambda root, config=None: self.settings), \
                mock.patch.object(R, "rule", lambda policy=None: (self.rule, None)):
            for receipt, warned in (({"repick_frozen": 5}, False), ({"repick_frozen": 5, "repick_kept": 5}, True)):
                ctx.alerts.clear()
                with mock.patch.object(FS, "night", lambda *a, **k: dict(receipt)):
                    self.assertEqual(FS.run(ctx), receipt)
                self.assertEqual(any("keep a representative" in text for _, text in ctx.alerts), warned, ctx.alerts)

    def test_a_store_of_the_earlier_build_takes_the_repick_trigger(self):
        old_schema = "PRAGMA recursive_triggers=ON;\n" + FS._TABLES + "".join(
            f"CREATE TRIGGER IF NOT EXISTS {t}_no_{verb.lower()} BEFORE {verb} ON {t} BEGIN SELECT RAISE(ABORT, "
            f"'{FS.APPEND_ONLY_ERROR}'); END;\n" for t in FS.TABLES for verb in ("UPDATE", "DELETE"))
        path = self.root / FS.DB
        db = sqlite3.connect(str(path))
        db.executescript(old_schema)
        db.close()
        v1 = self.sighted_on_v1()
        self.first_night()
        v2 = self.row("f1", 2, first_day="2026-10-16")
        db = self.store()
        names = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND "
                                          "tbl_name='fwd1_lineages'")}
        self.assertEqual(names, {"fwd1_lineages_no_delete", "fwd1_lineages_repick_only"})
        db.close()
        self.assertEqual(self.night(now=EVE)["repicked"], 1)
        self.assertEqual(self.lineage()["rep"], v2)
        self.assertEqual(json.loads(self.repicks()[0]["payload"])["from"], v1)


class World:
    """A state root of INVENTED forward rows for the judge's whole-night tests (seeded draws, no market data): ETF and
    panel lineages, each with its representative's rows and its sides already kept (no forward run is needed), the
    House's runs the fake's (`FakeRuns`: invented floors, placebo draws that never bind)."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.fdb = forward_db.open_db(self.root)
        self.engine, _ = forward_db.engine_id(self.fdb, "equity-engine-1+aaaaaaaaaaaa+fwd-1", at=1.0)
        self.families: dict[str, dict] = {}
        self.rule = fake_rule()
        self.settings = {"elane": {"fwd1": {"mode": "record", "seats": "off", "cpu_seconds_night": 2400},
                                   "forward": {"mode": "record"}}}
        self.rows: dict[int, list[tuple[str, float, float, float, float, str]]] = {}
        db = FS.open_store(self.root)
        FS.pinned(db, self.rule, base=None, release=None, now=PIN_AT)       # the clock starts Friday Oct 16
        db.close()

    def close(self):
        self.fdb.close()

    def lineage(self, pid: int, typ: str, values, *, b=None, sides=None):
        """One lineage `L<pid>` of type `typ`: its representative's rows (r, w = 0.5, b, r15 = r - 1e-5, status ok)
        from START, and their sides kept."""
        fid = f"L{pid:03d}"
        panel = typ == "PANEL"
        self.families[fid] = {"id": fid, "structure": "panel" if panel else "etf",
                              "spec": {"lane": "equity", "agenda": "trend"}, "state": {}, "lineage": None, "band": "gym"}
        self.fdb.execute(
            "INSERT INTO fwd_registry(pid, key, family, version, lane, reason, ugroup, lineage, code, params, needs, "
            "program_sha, run_sha, author, created_at, evidence, first_close, first_day, registered_at, route, "
            "alpha_f, prev_hash, row_hash) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (pid, f"{fid}@1", fid, 1, "equity", "train_pass", "panel:sp500" if panel else "index", f"equity:{fid}",
             "PARAMS = {}\n", "{}", json.dumps({"symbols": ["SPY"], "history": 1}), "p" * 64, f"{pid:064d}", "", 1.0,
             "registry", "2026-10-15", START.isoformat(), 1.0, "XS1" if panel else "S2", "0.03", "0" * 64,
             f"{pid:063d}h"))
        names = sessions(START, len(values))
        b = [0.0] * len(values) if b is None else list(b)
        sides = [0.0] * len(values) if sides is None else list(sides)
        self.rows[pid] = [(day, float(r), 0.5, float(bb), float(r) - 1e-5, "ok") for day, r, bb in zip(names, values, b)]
        db = FS.open_store(self.root)
        with db:
            for day, side in zip(names, sides):
                db.execute("INSERT INTO fwd1_sides(pid, day, engine, sides, at) VALUES (?,?,?,?,?)",
                           (pid, day, self.engine, float(side), 2.0))
        db.close()
        self.fdb.commit()

    def reveal(self, through: str | None = None):
        """The record's rows through `through` (every row when None)."""
        for pid, rows in self.rows.items():
            for day, r, w, b, r15, status in rows:
                if through is None or day <= through:
                    self.fdb.execute("INSERT OR IGNORE INTO fwd_days(pid, day, engine, r, w, b, r15, r0, entries, exits, "
                                     "status, at, bars) VALUES (?,?,?,?,?,?,?,NULL,0,0,?,1.0,?)",
                                     (pid, day, self.engine, r, w, b, r15, status, "b" * 16))
        self.fdb.commit()

    def night(self, now: float):
        return FS.night(self.root, rule=self.rule, settings=self.settings, now=now, base=None, release=None,
                        runs=FakeRuns(), families=self.families, clock=lambda: now)

    def checks(self) -> dict[str, dict[int, tuple]]:
        db = FS.open_store(self.root)
        try:
            out: dict[str, dict[int, tuple]] = {}
            for r in db.execute("SELECT * FROM fwd1_checks ORDER BY lineage, k"):
                out.setdefault(r["lineage"], {})[int(r["k"])] = (r["day"], r["t"], r["s"], r["s15"], r["g_bp"],
                                                                 r["passed"], r["c_used"], r["count"])
            return out
        finally:
            db.close()

    def verdicts(self) -> dict[str, str]:
        db = FS.open_store(self.root)
        try:
            return {r["lineage"]: r["verdict"] for r in db.execute("SELECT lineage, verdict FROM fwd1_verdicts")}
        finally:
            db.close()


def invented(world: World, n: int, *, seed: int, edge: float = 0.0, days: int = 70):
    """`n` lineages, every other one a panel, each a seeded normal series with a daily edge `edge` (a panel's in its
    residual x = r - w b: its r carries w b beside it), random sides."""
    for i in range(n):
        rng = np.random.default_rng([seed, i])
        typ = "PANEL" if i % 2 == 0 else "ETF"
        x = rng.normal(edge, 0.006, days)
        b = rng.normal(0.0003, 0.01, days) if typ == "PANEL" else np.zeros(days)
        world.lineage(i + 1, typ, (x + 0.5 * b).tolist(), b=b.tolist(),
                      sides=rng.choice([0.0, 0.25, 0.5], size=days).tolist())


def evening(day: str) -> float:
    return dt.datetime.fromisoformat(day + "T23:30:00+00:00").timestamp()


class TheLookAhead(unittest.TestCase):
    """No checkpoint of record reads a day after its k-th counted day (THE LOOK-AHEAD CANARY), a night reads the same
    as the nights it stands for (one session a night gives what one night over every row gives), and the judge has
    power: a planted strong edge reaches a pass, a zero edge mostly fails. Through the job's own `night` on invented
    rows (the judge is protected: nothing else would catch a later edit that reads `days` for `days[:k]`, or a sign
    that kills the power)."""

    N = 24

    def world(self) -> World:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        world = World(Path(tmp.name))
        self.addCleanup(world.close)
        return world

    def test_the_canary_future_days_never_move_a_checkpoint_of_record(self):
        base = self.world()
        invented(base, self.N, seed=5)
        base.reveal()
        base.night(evening(sessions(START, 80)[-1]))
        perturbed = self.world()
        invented(perturbed, self.N, seed=5)
        rng = np.random.default_rng(17)
        cuts = {}
        for pid, rows in perturbed.rows.items():                 # every day after a cut: +5% a day
            cut = int(rng.integers(0, len(rows)))
            cuts[f"equity:L{pid:03d}"] = rows[cut][0]
            perturbed.rows[pid] = rows[:cut] + [(d, 0.05, 1.0, b, 0.0499, s) for d, _, _, b, _, s in rows[cut:]]
        perturbed.reveal()
        perturbed.night(evening(sessions(START, 80)[-1]))
        a, b = base.checks(), perturbed.checks()
        compared = 0
        for lineage, cut in cuts.items():
            before = {k: v for k, v in a.get(lineage, {}).items() if v[0] < cut}
            after = {k: v for k, v in b.get(lineage, {}).items() if v[0] < cut}
            self.assertEqual(before, after, lineage)
            compared += len(before)
        self.assertGreater(compared, 10)
        self.assertGreater(sum(1 for v in perturbed.verdicts().values() if v == "pass"),
                           sum(1 for v in base.verdicts().values() if v == "pass"),
                           "and the perturbed days are read after the cut")

    def test_one_session_a_night_reads_what_one_night_over_every_row_reads(self):
        whole = self.world()
        invented(whole, self.N, seed=9)
        whole.reveal()
        whole.night(evening(sessions(START, 80)[-1]))
        nightly = self.world()
        invented(nightly, self.N, seed=9)
        for day in sessions(START, 72):
            nightly.reveal(day)
            nightly.night(evening(day))
        self.assertEqual(nightly.checks(), whole.checks())
        self.assertEqual(nightly.verdicts(), whole.verdicts())
        self.assertTrue(whole.verdicts())

    def test_a_planted_edge_passes_and_a_zero_edge_mostly_fails(self):
        counts = {}
        for edge in (0.0, 0.004):                                  # zero, and 40 bp a day
            world = self.world()
            invented(world, 30, seed=23, edge=edge)
            world.reveal()
            world.night(evening(sessions(START, 80)[-1]))
            counts[edge] = sum(1 for v in world.verdicts().values() if v == "pass")
        self.assertLessEqual(counts[0.0], 4, counts)               # the bars hold a zero edge to a few passes
        self.assertGreaterEqual(counts[0.004], 15, counts)         # a strong edge passes


class TheHouseRuns(TS.Case):
    """`HouseRuns` on E1's real engine in an `InlineDecider` over a synthetic store (THE FAKES of E3's shadow tests for
    its other packages): the sides of a program's own forward run against the record's own night, and its Train-era
    pools for the own floor."""

    def test_the_sides_of_its_own_run_reproduce_the_record(self):
        pid = TS.register(self.db, "always@1", TS.ALWAYS, first_close=TS.FWD[2])
        self.night(TS.FWD[8])                                     # E3's own night writes the record
        rows = self.rows(pid)
        self.assertTrue(rows)
        runs = FS.HouseRuns(self.root, budget_seconds=120, decider=InlineDecider(), clock=self.clock)
        found = runs.forward_sides(self.program(pid), "ETF", settings=TS.RECORD, fdb=self.db)
        for row in rows:
            self.assertAlmostEqual(found["r"][row["day"]], row["r"], delta=forward_db.TOL)
        entry = rows[0]["day"]                                    # it buys at the open of its first day and holds
        self.assertGreater(found["sides"][entry], 0.4)
        self.assertEqual({d for d, v in found["sides"].items() if v}, {entry})

    def test_its_train_era_pools_give_an_own_floor(self):
        TS.synth.synthetic_store(self.root / TS.STORE_DIR, symbols=TS.SYMBOLS, start=dt.date(2016, 1, 4),
                                 end=TS.END, seed=7, gate=True, as_of=TS.FWD[8])
        pid = TS.register(self.db, "always@1", TS.ALWAYS, first_close=TS.FWD[2])
        runs = FS.HouseRuns(self.root, budget_seconds=300, decider=InlineDecider(), clock=self.clock)
        pool_d, pool_c = runs.etf_pools(self.program(pid))
        self.assertGreater(len(pool_d[0]), 900)                  # 2016-19 from its third session
        self.assertGreater(len(pool_c[0]), 700)                  # 2022-24
        self.assertTrue(all(len(a) == len(pool_d[0]) for a in pool_d))
        cells = R.floor_cells("ETF", pool_d, pool_c)
        self.assertEqual(len(cells), 2)
        found = R.own_floor_k([[p[:3] for p in c] for c in cells], R.OWN_CAP["N"])
        self.assertIsNotNone(found["k_own"], found["why"])
        self.assertIsNotNone(R.drift_kept(cells, R.k_used("ETF", "N", found["k_own"]) or 500))


    def test_a_train_era_series_its_own_runs_do_not_give_is_the_programs_own(self):
        """A ValueError of `screen.series` over the program's own Train-era runs is as deterministic as the runs: the
        program's own (OwnFloorRefused, ineligible, stated), never the House's asked again each night."""
        TS.synth.synthetic_store(self.root / TS.STORE_DIR, symbols=TS.SYMBOLS, start=dt.date(2016, 1, 4),
                                 end=TS.END, seed=7, gate=True, as_of=TS.FWD[8])
        pid = TS.register(self.db, "always@1", TS.ALWAYS, first_close=TS.FWD[2])
        runs = FS.HouseRuns(self.root, budget_seconds=300, decider=InlineDecider(), clock=self.clock)
        from league.equity import screen

        def unreadable(*args, **kwargs):
            raise ValueError("a held symbol with no price that session")

        with mock.patch.object(screen, "series", unreadable):
            with self.assertRaises(FS.OwnFloorRefused):
                runs.etf_pools(self.program(pid))


class TheExDay(TS.Case):
    """THE EX-DAY (the House review's major), in E3's own test world: the real E1 engine in an `InlineDecider` over a
    synthetic store rounded to cents as the vendor's is, E3's own night writing the record each evening, the job's
    night after it. A SPY dividend inside a checkpoint window rescales the whole adjusted history, E3 keeps the
    first-written r of every day, and the representative's own run never reproduces those r again: its sides are
    still read (the days were restated), and every checkpoint of record is written. The global bar is out of reach
    (no floor run): only whether each checkpoint is written is read."""

    def nights(self, dividends, count):
        TS.register(self.db, "always@1", TS.ALWAYS, first_close=TS.BEFORE)
        families = {"always": {"id": "always", "structure": "etf", "spec": {"lane": "equity", "agenda": "trend"},
                               "state": {}, "lineage": None, "band": "gym"}}
        store = FS.open_store(self.root)
        self.addCleanup(store.close)
        rule = fake_rule()
        pin = {"start": TS.FWD[0].isoformat(), "release": "", "pinned_at": 0.0}
        tallies = []
        with mock.patch.dict(R.C_G, {"ETF": {"N": 99.0}, "PANEL": {"N": 99.0, "XS1": 99.0}}):
            for through in TS.FWD[:count]:
                TS.write_night(self.root, through, dividends=dividends)
                TS.cents(self.root)
                self.shadow(through, write=False).night()
                FS.register(store, self.db, families, rule=rule, pin_start=TS.FWD[0], now=self.clock())
                runs = FS.HouseRuns(self.root, budget_seconds=120, decider=InlineDecider(), clock=self.clock)
                tallies.append(FS.Night(store, self.db, families, runs=runs, rule=rule, pin=pin, budget=900,
                                        clock=self.clock, settings=TS.RECORD).run())
        return [int(r[0]) for r in store.execute("SELECT k FROM fwd1_checks ORDER BY k")], tallies

    def test_every_checkpoint_is_written_across_an_ex_day(self):
        ks, tallies = self.nights({"SPY": [(TS.FWD[7], 1.5)]}, 16)
        self.assertEqual(ks, [5, 10, 15])
        self.assertGreater(sum(t.get("sides_restated", 0) for t in tallies), 0)   # the restated days kept their sides
        self.assertEqual(sum(t.get("no_sides", 0) for t in tallies), 0)
        self.assertEqual(self.events("restated")[0]["payload"]["bars"], "moved")    # E3 said so too


class ThePanelHouseRuns(unittest.TestCase):
    """`HouseRuns`' panel paths in package J's own world (league/tests/test_forward_xs.py `House`: the real panel
    runner and engine in an `InlineDecider` over a synthetic panel of 40 invented names; E4's panel night writes the
    record): ONE OPEN OF THE PANEL STORE A JOB RUN, the sides of the representative's own run against the record, and
    THE CLOCK RULE on its Train segments and its placebo leg."""

    def setUp(self):
        from league.tests import test_forward_xs as TX

        self.TX = TX
        self.h, self.key, self.pid = TX.registered(self)
        self.h.night(10)                               # the panel night writes the record
        self.program = forward_db.program(self.h.db, self.key)

    def runs(self, decider=None):
        return FS.HouseRuns(self.h.root, budget_seconds=300, decider=decider or InlineDecider(), clock=self.h.clock,
                            fdb=self.h.db, settings=self.h.settings)

    def test_one_panel_store_a_job_run_and_the_sides_are_the_records(self):
        from league.xs import store as xstore

        rows = self.h.rows(self.pid)
        self.assertGreaterEqual(len(rows), 5)
        opened = []
        real = xstore.PanelStore.__init__

        def counting(store, *args, **kwargs):
            opened.append(1)
            return real(store, *args, **kwargs)

        runs = self.runs()
        with mock.patch.object(xstore.PanelStore, "__init__", counting):
            for _ in range(3):
                found = runs.forward_sides(self.program, "PANEL", settings=self.h.settings, fdb=self.h.db)
            block = runs.panel_placebo(self.program, start=dt.date.fromisoformat(rows[0]["day"]),
                                       end=dt.date.fromisoformat(rows[-1]["day"]), seed=7)
        self.assertEqual(len(opened), 1, "every panel run of the job read the one store")
        for row in rows:
            day = row["day"]
            self.assertAlmostEqual(found["r"][day], row["r"], delta=forward_db.TOL)
            self.assertEqual((found["bars"][day], found["entries"][day], found["exits"][day]),
                             (row["bars"], row["entries"], row["exits"]))
        self.assertEqual((block["days"], block["n"]), (len(rows), R.PLACEBO_DRAWS))
        runs.close()
        self.assertIsNone(runs._night)

    def test_the_train_segments_one_at_a_time_through_the_clock_rule(self):
        from league.swarm import elane_xs

        plain = self.runs().panel_pools(self.program)
        clocked = self.TX.TheHousesClockAtNight.clocked(self.key, [2, 0, 0])
        pools = self.runs(clocked()).panel_pools(self.program)
        self.assertEqual(clocked.made, [2, 0, 0], "the first segment's run lost decides to the clock: made again")
        for a, b in zip(plain, pools):
            self.assertEqual(a is None, b is None)
            if a is not None:
                for x, y in zip(a, b):
                    self.assertEqual(list(x), list(y))
        slow = self.TX.TheHousesClockAtNight.clocked(self.key, [3, 3, 3])
        with self.assertRaises(FS.OwnFloorRefused):                        # the same each run: the program's
            self.runs(slow()).panel_pools(self.program)
        unsteady = self.TX.TheHousesClockAtNight.clocked(self.key, [1, 2, 1])
        with self.assertRaises(elane_xs.ClockUnsteady):                    # not the same twice: the House's
            self.runs(unsteady()).panel_pools(self.program)

    def test_the_placebo_leg_through_the_clock_rule(self):
        rows = self.h.rows(self.pid)
        clocked = self.TX.TheHousesClockAtNight.clocked(self.key, [2, 0])
        block = self.runs(clocked()).panel_placebo(self.program, start=dt.date.fromisoformat(rows[0]["day"]),
                                                   end=dt.date.fromisoformat(rows[-1]["day"]), seed=7)
        self.assertEqual(clocked.made, [2, 0])
        self.assertEqual(block["days"], len(rows))


class TheJobFitsItsMemory(unittest.TestCase):
    """The House review's major, AT THE REAL PANEL'S SIZE (2,501 sessions by 767 columns, through mid-December 2026)
    UNDER THE OPS CHILD'S OWN LIMIT (`league.ops.__main__.limit`: the address space is capped 500 MB above the child's
    start, before the job's first import). As it was, every panel call of the job opened its own copy of the panel
    store (two bar arrays mapped again, freed only by a full collection): the third open found no room. Now one
    `HouseRuns` (one a job run) reads ONE panel store for every forward run, placebo leg and Train segment. The world
    is league/tests/fwd1_panel_budget.py's: the real store, panel night, runner and decider (the House's side and its
    child's loop), the engine canned; the calls run in a child of this test."""

    EXTRA_MB = 500          # the registry row's default: `league.ops.runner` starts the child with it
    CALLS = 6               # six forward runs and six placebo legs of one night's panel lineages, and one own floor
    #: Of the cap, the job's calls leave at least this much unused (measured on the desk: about 118 MB on 3.11 with
    #: the engine canned); the bound has room for another machine's libraries. What it holds is that a call no longer
    #: adds to the peak, which is the store's two maps, one Train slice, its pickle and its frame.
    HEADROOM_MB = 30

    def measure(self, mode):
        import os
        import subprocess
        import sys

        from league.ops import runner
        from league.tests import fwd1_panel_budget as B

        self.assertEqual(runner.EXTRA_MB, self.EXTRA_MB, "the address space the runner gives every job's child")
        if not hasattr(self, "state"):
            tmp = tempfile.TemporaryDirectory()
            self.addCleanup(tmp.cleanup)
            self.state = Path(tmp.name) / "state"
            built = B.build(self.state)
            self.assertGreaterEqual(built["sessions"], 2455, "the production panel's sessions")
            self.assertGreaterEqual(built["columns"], 700, "and its columns")
        env = {**os.environ, "PYTHONPATH": str(REPO), "PYTHONDONTWRITEBYTECODE": "1", "OPENBLAS_NUM_THREADS": "1",
               "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"}    # (as `league.ops.runner` starts its child)
        done = subprocess.run([sys.executable, "-c", B.BOOT, str(self.state), str(self.EXTRA_MB), mode,
                               str(self.CALLS)], cwd=REPO, env=env, capture_output=True, text=True,
                              timeout=registry.by_name()["forward_screen"].wall)
        self.assertEqual(done.returncode, 0, done.stderr[-2000:])
        return json.loads(done.stdout.strip().splitlines()[-1])

    def test_the_panel_calls_fit_with_room_to_spare_and_the_job_as_it_was_does_not(self):
        import os

        if os.geteuid() == 0:  # pragma: no cover
            self.skipTest("as root the decider starts its child from its own runtime copy: the canned child is not in it")
        out = self.measure("job")
        self.assertIsNone(out["error"], out)
        self.assertEqual(out["opens"], 1, "one panel store for every call of the job run")
        kinds = [a[0] for a in out["answers"]]
        self.assertEqual(kinds, ["sides", "placebo"] * self.CALLS + ["pools"], out["answers"])
        self.assertTrue(all(n > 700 for n in out["answers"][-1][1]), "both Train segments' pools")
        self.assertGreater(out["cap_mb"], 0, "the limit was set before the job's imports")
        self.assertLessEqual(out["vm_peak_mb"], out["cap_mb"] - self.HEADROOM_MB,
                             f"the peak of the job's panel calls leaves {self.HEADROOM_MB} MB of the cap: {out}")
        was = self.measure("as_it_was")
        self.assertTrue(was["error"] is not None or any(a[0] == "error" for a in was["answers"]),
                        f"a store a call does not fit: the measurement sees what it is for ({was})")


if __name__ == "__main__":
    unittest.main()
