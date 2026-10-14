"""The forward screen's job (league/ops/forward_screen.py, FWD1-R): the clock, the lineages, the checkpoints of record,
one verdict a lineage, the panel's placebo leg, the engine rule, the permit file and the nights' sides hook.

Every store is made here from invented rows (FAKE: no market data, no real figure); the House's runs are a fake."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import tempfile
import types
import unittest
from collections import Counter
from pathlib import Path

import numpy as np

from league.ops import forward_db, forward_screen as FS, fwd1_rule as R, registry
from league.equity import schedule

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

    def __init__(self, placebo_t=None, days=None, fail=False):
        self.calls = Counter()
        self.placebo_t = placebo_t
        self.days = days
        self.fail = fail

    def etf_pools(self, program):
        self.calls["etf"] += 1
        if self.fail:
            raise RuntimeError("the child died")
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
             w: float = 0.5, b: float = 0.0):
        names = sessions(first, len(values))
        for day, r in zip(names, values):
            self.fdb.execute("INSERT INTO fwd_days(pid, day, engine, r, w, b, r15, r0, entries, exits, status, at, bars) "
                             "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                             (pid, day, engine or self.engine, float(r), w, b, float(r) - 1e-5, None, 0, 0, "ok", 1.0,
                              "b" * 16))
        self.fdb.commit()
        return names

    def sides(self, pid: int, names, value: float = 0.0, engine: int | None = None):
        run = types.SimpleNamespace(program=types.SimpleNamespace(pid=pid), series=types.SimpleNamespace(iso=list(names)),
                                    result={"lots": [{"lid": 1, "weight": value, "entry_day": names[0], "exit_day": None}]
                                            if value else []})
        return FS.on_run(self.root, run, engine=engine or self.engine, now=2.0, settings=self.settings, rule=self.rule)

    def night(self, runs=None, *, now: float = PIN_AT + 86400 * 20):
        return FS.night(self.root, rule=self.rule, settings=self.settings, now=now, base=None, release=None,
                        runs=runs or FakeRuns(), families=self.families, clock=lambda: now)

    def store(self):
        db = FS.open_store(self.root)
        return db

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

    def test_no_sides_no_checkpoint(self):
        self.family("f1")
        pid = self.row("f1", 1, first_day="2026-10-16")
        self.days(pid, [0.01] * 6, first=START)
        receipt = self.first_night()
        self.assertEqual(receipt["no_sides"], 1)

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

    def test_a_span_that_is_not_the_judged_sessions_fails_closed(self):
        self.run_night(FakeRuns(days=4))
        db = self.store()
        check = dict(db.execute("SELECT * FROM fwd1_checks WHERE k=5").fetchone())
        self.assertEqual(check["passed"], 0)
        self.assertIn("fails closed", check["why"])
        db.close()

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

    def test_the_hook_writes_nothing_without_a_pin_or_with_the_switch_off(self):
        run = types.SimpleNamespace(program=types.SimpleNamespace(pid=1), series=types.SimpleNamespace(iso=["2026-10-16"]),
                                    result={"lots": []})
        self.assertEqual(FS.on_run(self.root, run, engine=1, now=1.0, settings={}, rule=self.rule), 0)
        self.assertFalse((self.root / FS.DB).exists())

    def test_sides_from_lots_both_ways(self):
        lots = [{"lid": 1, "weight": 0.25, "entry_day": "2026-10-16", "exit_day": "2026-10-19"},
                {"lid": 2, "weight": 0.25, "entry_day": "2026-10-19", "exit_day": None}]
        self.assertEqual(FS.lot_sides({"lots": lots}), {"2026-10-16": 0.25, "2026-10-19": 0.5})
        ordinals = [(dt.date(2026, 10, d) - dt.date(1970, 1, 1)).days for d in (16, 19)]   # E3's int ordinals
        run = types.SimpleNamespace(program=types.SimpleNamespace(pid=7),
                                    series=types.SimpleNamespace(iso=None, days=ordinals), result={"lots": lots})
        self.assertEqual(FS._run_days(run), ["2026-10-16", "2026-10-19"])

    def test_the_shadow_night_calls_the_hook(self):
        from league.ops import forward_shadow

        program = types.SimpleNamespace(pid=3, key="f@1")
        run = types.SimpleNamespace(program=program, series=types.SimpleNamespace(days=[], iso=["2026-10-16"]),
                                    result={"lots": [{"lid": 1, "weight": 0.5, "entry_day": "2026-10-16"}]})
        fake = types.SimpleNamespace(run_program=lambda p: (run, {}), write=lambda r, s: {"new_days": 1, "restated": 0,
                                                                                            "checks": 0},
                                     _commit=lambda: None, _rollback=lambda: None, db=None, clock=lambda: 5.0,
                                     settings=self.settings, root=self.root, engine=self.engine, _data_failed=None)
        import league.ops.forward_twins as twins
        real_twins, real_rule = twins.on_run, FS._pinned_rule
        try:
            twins.on_run = lambda *a, **k: 0
            FS._pinned_rule = lambda: self.rule
            tally = Counter()
            forward_shadow.Shadow._attempt(fake, program, tally)
        finally:
            twins.on_run, FS._pinned_rule = real_twins, real_rule
        self.assertEqual(tally["fwd1_sides"], 1)
        db = self.store()
        self.assertEqual(dict(db.execute("SELECT * FROM fwd1_sides").fetchone())["sides"], 0.5)
        db.close()

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


if __name__ == "__main__":
    unittest.main()
