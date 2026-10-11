"""THE FORWARD REPORT (release E3; league/ops/forward_report.py): the day's meters, the report file, the funnel counts
and the alarms, and seal T8, `TheReportShowsOnlyWhatItMay`.

- D6: one representative a lineage, the cut by hash, a member's unbroken run of counted days ending today; CEY accrues
  only from the 10th session and is provisional to the 20th; the 20-day median.
- D7: the simulated program-years from the swarm's equity runs and the forward rows; the history's independent years on
  a synthetic store; the multiple; a store that cannot be read leaves both None that day.
- D8: one p a lineage, its representative's latest checkpoint under the newest engine it has; the controls on their
  cost-free p; D9: the groups' daily rows, a tag counted from its own time, the pooled controls, a read taken on
  exactly a pair's first 60 usable sessions and nothing shown before it.
- `meters` twice writes once (first write stands); each alarm of the spec's 12.3 from a fixture; FW1's silences; when a
  report is stale (never for want of a run nobody owed: a weekend); `funnel_rows`' zeros and integers.

THE FORWARD STORE'S FUNCTIONS ARE FAKES HERE (`FakeA`): package A's `forward_db` is a stub on this package's branch,
so `cfg`, `mode`, `t0`, `open_db`, `engine_now`, `engine_label`, `verify_chain`, `active` and `suspect` are patched
with small functions written to the semantics its docstrings state, over a store made from its real `SCHEMA`. The
memory tables' `counts` (package E's) is a fake too. The integrator's end-to-end test runs the real ones together.
Every program, series and count is invented; the one price store is `league.equity.synth`'s."""

from __future__ import annotations

import ast
import datetime as dt
import hashlib
import json
import math
import os
import sqlite3
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from league.equity import config
from league.equity import schedule as ES
from league.ops import forward_db
from league.ops import forward_report as R
from league.ops import forward_stats as FS
from league.ops import guard
from league.ops import release_receipts as RR
from league.ops import schedule as S
from league.ops.context import Context, read_json, write_json
from league.swarm import elane_memory

RECORD = {"elane": {"forward": {"mode": "record"}}}
OFF = {"elane": {"forward": {"mode": "off"}}}
T0 = ES.next_session(config.LOOK_CAP)
#: The first 300 forward days (D1: the sessions after the look cap).
DAYS = R.forward_days(T0, T0 + dt.timedelta(days=440))[:300]
E3_OPS = ("forward_db", "forward_register", "forward_controls", "forward_shadow", "forward_audit", "forward_stats",
          "forward_report", "forward_twins", "fill_minutes", "contam_probe", "release_receipts")
REPO = Path(__file__).resolve().parents[2]


def ny(day: str, hh: int, mm: int = 0) -> float:
    d = dt.date.fromisoformat(day)
    return dt.datetime(d.year, d.month, d.day, hh, mm, tzinfo=ES.NY).timestamp()


def close(day: str) -> float:
    return float(ES.moments(day).close_at)


class FakeA:
    """Package A's forward store functions, as their docstrings state them (the module docstring)."""

    chain: dict = {"ok": True, "rows": 0, "first_bad": None}

    @staticmethod
    def cfg(settings):
        out = dict(forward_db.DEFAULTS)
        raw = ((settings or {}).get("elane") or {}).get("forward") if isinstance(settings, dict) else None
        if isinstance(raw, dict):
            if raw.get("mode") in forward_db.MODES:
                out["mode"] = raw["mode"]
            for key, (low, high) in forward_db.BOUNDS.items():
                if isinstance(raw.get(key), int) and not isinstance(raw.get(key), bool) and low <= raw[key] <= high:
                    out[key] = raw[key]
        return out

    @classmethod
    def mode(cls, settings):
        return cls.cfg(settings)["mode"]

    @staticmethod
    def t0():
        return T0

    @staticmethod
    def open_db(root, *, readonly=False):
        path = Path(root) / forward_db.DB
        if readonly:
            return guard.connect_ro(path)
        db = sqlite3.connect(str(path))
        db.row_factory = sqlite3.Row
        db.executescript(forward_db.SCHEMA)
        return db

    @staticmethod
    def engine_now(db):
        row = db.execute("SELECT max(id) FROM fwd_engines").fetchone()
        return None if row[0] is None else int(row[0])

    @staticmethod
    def engine_label(db, id):  # noqa: A002 - the contract's name
        row = db.execute("SELECT label FROM fwd_engines WHERE id=?", (id,)).fetchone()
        return None if row is None else row[0]

    @classmethod
    def verify_chain(cls, db):
        return dict(cls.chain)

    @staticmethod
    def active(db, pid):
        stopped = db.execute("SELECT max(at) FROM fwd_tags WHERE pid=? AND tag='stopped'", (pid,)).fetchone()[0]
        resumed = db.execute("SELECT max(at) FROM fwd_tags WHERE pid=? AND tag='resumed'", (pid,)).fetchone()[0]
        return stopped is None or (resumed is not None and resumed >= stopped)

    @staticmethod
    def suspect(db, pid):
        night = db.execute("SELECT max(value) FROM fwd_tags WHERE pid=? AND tag='suspect'", (pid,)).fetchone()[0]
        last = db.execute("SELECT max(day) FROM fwd_days WHERE pid=?", (pid,)).fetchone()[0]
        return night is not None and (last is None or night >= last)


def fake_counts(db):
    """Package E's `elane_memory.counts`, as its docstring states it: row counts only."""
    tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'mem_%'")}
    if "mem_seen" not in tables:
        return {"seen": 0, "contrib": 0, "families": 0, "by_year": {}}
    return {"seen": db.execute("SELECT count(*) FROM mem_seen").fetchone()[0],
            "contrib": db.execute("SELECT count(*) FROM mem_contrib").fetchone()[0],
            "families": db.execute("SELECT count(DISTINCT family) FROM mem_contrib").fetchone()[0],
            "by_year": {str(r[0]): r[1] for r in db.execute("SELECT year, count(*) FROM mem_contrib GROUP BY year")}}


class Fixture(unittest.TestCase):
    """A state root with a forward store (its real DDL), the fakes in place, and writers of the rows the other
    packages write. The clock is `self.now`; a row's `at` is the clock's unless given."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = self.base / "state"
        self.root.mkdir()
        FakeA.chain = {"ok": True, "rows": 0, "first_bad": None}
        fakes = {name: getattr(FakeA, name) for name in ("cfg", "mode", "t0", "open_db", "engine_now", "engine_label",
                                                         "verify_chain", "active", "suspect")}
        for patcher in (mock.patch.multiple(forward_db, **fakes), mock.patch.object(elane_memory, "counts", fake_counts)):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.db = forward_db.open_db(self.root)
        self.addCleanup(self.db.close)
        self.now = ny(DAYS[0], 20)
        self.pid = 0
        self.engine = self.label("eq-1+aaaaaaaaaaaa+fwd-1")

    # ------------------------------------------------------------------ the rows of packages A, B and D
    def label(self, text: str) -> int:
        with self.db:
            return int(self.db.execute("INSERT INTO fwd_engines(label, at) VALUES(?, ?)", (text, self.now)).lastrowid)

    def register(self, key: str | None = None, *, reason: str = "train_pass", lineage: str | None = None,
                 ugroup: str = "index", first_day: str = DAYS[0], symbols: tuple = ("SPY",),
                 registered_at: float | None = None, lane: str = "equity") -> int:
        self.pid += 1
        key = key or f"fam-{self.pid}@1"
        family, version = (None, None) if lane == "control" else (key.split("@")[0], 1)
        with self.db:
            self.db.execute(
                "INSERT INTO fwd_registry(pid, key, family, version, lane, reason, ugroup, lineage, code, params, needs, "
                "program_sha, run_sha, author, created_at, evidence, first_close, first_day, registered_at, route, "
                "alpha_f, prev_hash, row_hash) VALUES(?, ?, ?, ?, ?, ?, ?, ?, 'fake', '{}', ?, 'sha', 'run', 'fake', ?, "
                "'registry', ?, ?, ?, ?, ?, 'p', ?)",
                (self.pid, key, family, version, lane, reason, ugroup, lineage or f"{lane}:{key.split('@')[0]}",
                 json.dumps({"symbols": list(symbols), "history": 1, "max_hold_sessions": 20}), self.now,
                 ES.previous_session(first_day).isoformat(), first_day,
                 self.now if registered_at is None else registered_at, "none" if lane == "control" else "S2",
                 "0" if lane == "control" else "0.03", f"h{self.pid}"))
        return self.pid

    def control(self, group: str = "index", n: int = 0, *, first_day: str = DAYS[0]) -> int:
        return self.register(f"control:{group}:{n}", reason="control", lane="control", ugroup=group,
                             lineage=f"control:{group}:{n}", first_day=first_day)

    def day(self, pid: int, day: str, r: float = 0.0, *, w: float = 1.0, b: float = 0.0, r0: float | None = None,
            status: str = "ok", engine: int | None = None, at: float | None = None) -> None:
        with self.db:
            self.db.execute("INSERT INTO fwd_days(pid, day, engine, r, w, b, r15, r0, entries, exits, status, at) "
                            "VALUES(?, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?, ?)",
                            (pid, day, engine or self.engine, r, w, b, r, r0, status, self.now if at is None else at))

    def series(self, pid: int, days, values, **kw) -> None:
        for day, value in zip(days, values):
            self.day(pid, day, float(value), **kw)

    def check(self, pid: int, n: int, day: str, p_x: float | None, *, p_x0: float | None = None, final: int = 0,
              engine: int | None = None, at: float | None = None) -> None:
        with self.db:
            self.db.execute("INSERT INTO fwd_checks(pid, n, day, engine, t_r, sum_r, sum_r15, t_x, mean_w, p_x, t_x0, "
                            "p_x0, final, at) VALUES(?, ?, ?, ?, 0.0, 0.0, 0.0, 0.0, 1.0, ?, 0.0, ?, ?, ?)",
                            (pid, n, day, engine or self.engine, p_x, p_x0, final, self.now if at is None else at))

    def tag(self, pid: int, tag: str, value: str = "", *, at: float | None = None) -> None:
        with self.db:
            self.db.execute("INSERT INTO fwd_tags(pid, tag, value, at) VALUES(?, ?, ?, ?)",
                            (pid, tag, value, self.now if at is None else at))

    def event(self, kind: str, *, pid: int | None = None, day: str | None = None, at: float | None = None) -> None:
        with self.db:
            self.db.execute("INSERT INTO fwd_events(at, kind, pid, day, payload) VALUES(?, ?, ?, ?, '{}')",
                            (self.now if at is None else at, kind, pid, day))

    def night(self, through: str, *, programs: int = 1, sessions: int = 1, stale: int = 0, errors: int = 0,
              started: float | None = None) -> None:
        started = ny(through, 18, 35) if started is None else started
        with self.db:
            self.db.execute("INSERT INTO fwd_runs(job, through, engine, started, finished, seconds, programs, sessions, "
                            "errors, stale, budget_hit, head) VALUES('forward_shadow', ?, ?, ?, ?, 12.5, ?, ?, ?, ?, ?, 'h')",
                            (through, self.engine, started, started + 60.0, programs, sessions, errors, stale,
                             1 if stale else 0))

    def meters(self, settings=RECORD) -> dict:
        return R.meters(self.root, self.db, now=self.now, settings=settings)

    def section(self, settings=RECORD) -> dict:
        return R.section(self.root, now=self.now, settings=settings)

    def ids(self, settings=RECORD) -> list[str]:
        return [a["id"] for a in self.section(settings)["alarms"]]

    def table(self, name: str) -> list[dict]:
        return [dict(r) for r in self.db.execute(f"SELECT * FROM {name} ORDER BY 1, 2")]

    # ------------------------------------------------------------------ the swarm store and the live book
    def swarm(self):
        from league.swarm.store import SwarmStore

        store = SwarmStore(self.root, clock=lambda: self.now)
        self.addCleanup(store.close)
        return store

    def equity_family(self, store, fid: str, structure: str = "etf") -> None:
        spec = {"id": fid, "mechanism": "a published overnight prior long enough for the store", "structure": structure,
                "roots": ["SPY"]}
        if structure in ("etf", "stock"):
            spec["lane"] = "beta"
        store.add_family(spec, origin="architect")


# ============================================================================================== D6: N_eff and CEY
class TheRepresentatives(Fixture):
    def test_one_a_lineage_a_passer_seed_or_live_row_first_then_the_lowest_pid(self):
        a_fail = self.register("a@1", reason="train_fail", lineage="equity:a")
        a_pass = self.register("a@2", reason="train_pass", lineage="equity:a")
        self.register("a@3", reason="train_pass", lineage="equity:a")
        b_fail = self.register("b@1", reason="train_fail", lineage="equity:b")
        self.register("b@2", reason="train_fail", lineage="equity:b")
        seed = self.register("s@1", reason="seed", lineage="beta:s")
        live = self.register("l@1", reason="live", lineage="equity:l")
        self.control("index", 0)
        self.assertEqual(R.representatives(self.db, DAYS[5]), [a_pass, b_fail, seed, live])
        self.assertNotIn(a_fail, R.representatives(self.db, DAYS[5]))

    def test_a_row_counts_from_its_first_day(self):
        early = self.register("a@1", reason="train_fail", lineage="equity:a", first_day=DAYS[0])
        later = self.register("a@2", reason="train_pass", lineage="equity:a", first_day=DAYS[3])
        self.assertEqual(R.representatives(self.db, DAYS[2]), [early], "the passer has no forward day yet")
        self.assertEqual(R.representatives(self.db, DAYS[3]), [later])

    def test_above_the_cap_the_smallest_hashes_are_kept(self):
        pids = {self.register(f"fam-{i}@1"): f"fam-{i}@1" for i in range(60)}
        with mock.patch.dict(forward_db.DEFAULTS, {"neff_max_members": 50}):
            kept = R.representatives(self.db, DAYS[0])
        want = sorted(pids, key=lambda p: hashlib.sha256(("neff-1|" + pids[p]).encode()).hexdigest())[:50]
        self.assertEqual(kept, sorted(want))
        self.assertEqual(len(R.representatives(self.db, DAYS[0])), 60, "under the code default nothing is cut")


class ThePopulation(Fixture):
    def test_the_window_is_the_last_sixty_forward_days_and_x_is_the_daily_excess(self):
        pid = self.register("a@1")
        for i, day in enumerate(DAYS[:70]):
            self.day(pid, day, 0.001 * i, w=0.5, b=0.002)
        keys, X = R.population(self.db, DAYS[69])
        self.assertEqual((keys, X.shape), (["a@1"], (1, 60)))
        self.assertAlmostEqual(X[0, 0], 0.001 * 10 - 0.5 * 0.002, places=15)     # the 11th forward day opens the window
        self.assertAlmostEqual(X[0, -1], 0.001 * 69 - 0.5 * 0.002, places=15)
        self.assertEqual(R.population(self.db, DAYS[4])[1].shape, (1, 5), "no day before the first forward day")
        self.assertEqual(R.population(self.db, (T0 - dt.timedelta(days=1)).isoformat())[1].shape, (0, 0),
                         "before the first forward day there is no window and nobody is registered")

    def test_only_the_unbroken_run_ending_today_is_read(self):
        whole, gap, dq, marked, old, late = (self.register(f"{name}@1") for name in ("w", "g", "d", "m", "o", "l"))
        for pid in (whole, gap, dq, marked, old):
            for day in DAYS[:30]:
                if (pid, day) == (gap, DAYS[19]):
                    continue                                                # the data's: no row that night
                self.day(pid, day, 0.01, status="disqualified" if (pid, day) == (dq, DAYS[24]) else "ok",
                         engine=1)
        self.event("audit_mismatch", pid=marked, day=DAYS[27])
        for day in DAYS[25:30]:
            self.day(late, day, 0.01)
        keys, X = R.population(self.db, DAYS[29])
        runs = {key: int(np.isfinite(row).sum()) for key, row in zip(keys, X)}
        self.assertEqual(runs, {"w@1": 30, "g@1": 10, "d@1": 5, "m@1": 2, "o@1": 30, "l@1": 5})
        self.assertTrue(np.isnan(X[keys.index("g@1"), :20]).all(), "what lies before a gap is not read")
        # A member that stopped having rows has no run ending today.
        self.assertEqual(int(np.isfinite(R.population(self.db, DAYS[31])[1]).sum()), 0)

    def test_the_newest_engines_rows_are_the_series(self):
        pid = self.register("a@1")
        self.series(pid, DAYS[:12], [0.01] * 12)
        newer = self.label("eq-1+bbbbbbbbbbbb+fwd-1")
        self.series(pid, DAYS[:12], [0.02] * 12, engine=newer)
        _, X = R.population(self.db, DAYS[11])
        self.assertEqual(X[0].tolist(), [0.02] * 12)


class CleanEvidenceYears(Fixture):
    def members(self, n: int, days: int, seed: int = 5) -> np.ndarray:
        rng = np.random.default_rng(seed)
        values = rng.normal(0.0, 0.01, (n, days))
        for i in range(n):
            self.series(self.register(f"fam-{i}@1"), DAYS[:days], values[i])
        return values

    def test_it_accrues_only_from_the_tenth_session(self):
        values = self.members(6, 25)
        self.night(DAYS[24])
        self.assertEqual(self.meters(), {"days": 25, "cey": 25, "meter": 25, "groups": 25 * 5})
        rows = self.table("fwd_cey")
        self.assertEqual([r["day"] for r in rows], DAYS[:25])
        self.assertEqual([r["n_w"] for r in rows], list(range(1, 26)))
        self.assertTrue(all(r["cey_day"] == 0.0 and r["members"] == 0 and r["neff"] == 0.0 for r in rows[:9]))
        self.assertTrue(all(r["members"] == 6 and r["cey_day"] > 0.0 for r in rows[9:]))
        total = 0.0
        for k, row in enumerate(rows):
            want = FS.neff(values[:, :k + 1])
            self.assertAlmostEqual(row["neff"], want["neff"], places=9)
            self.assertEqual(row["cey_day"], row["neff"] / 252.0)
            total += row["cey_day"]
            self.assertAlmostEqual(row["cey_total"], total, places=12)
        self.assertAlmostEqual(rows[-1]["neff_raw"], FS.neff(values)["neff_raw"], places=9)

    def test_it_is_provisional_to_the_twentieth_session(self):
        self.members(4, 22)
        self.night(DAYS[18])
        self.meters()
        self.assertTrue(self.section()["cey"]["provisional"])
        self.assertEqual(self.section()["cey"]["n_w"], 19)
        self.night(DAYS[19])
        self.meters()
        cey = self.section()["cey"]
        self.assertEqual((cey["n_w"], cey["provisional"], cey["day"]), (20, False, DAYS[19]))
        self.assertEqual(forward_db.NEFF_PROVISIONAL, 20)

    def test_the_window_stops_at_sixty_sessions_and_the_median_reads_the_last_twenty_days(self):
        self.members(3, 70)
        self.night(DAYS[69])
        self.meters()
        rows = self.table("fwd_cey")
        self.assertEqual(rows[-1]["n_w"], forward_db.NEFF_WINDOW)
        cey = self.section()["cey"]
        ordered = sorted(r["cey_day"] for r in rows[-20:])
        self.assertEqual(cey["median20"], (ordered[9] + ordered[10]) / 2.0)
        self.assertEqual(cey["cey_total"], rows[-1]["cey_total"])
        self.assertIn("neff_raw", cey)

    def test_the_setting_caps_the_members(self):
        self.members(60, 12)
        self.night(DAYS[11])
        self.meters({"elane": {"forward": {"mode": "record", "neff_max_members": 50}}})
        self.assertEqual(self.table("fwd_cey")[-1]["members"], 50)


class MetersTwiceWriteOnce(Fixture):
    def test_the_first_write_stands(self):
        rng = np.random.default_rng(3)
        for i in range(4):
            self.series(self.register(f"fam-{i}@1"), DAYS[:12], rng.normal(0, 0.01, 12))
        self.night(DAYS[11])
        first = self.meters()
        before = {name: self.table(name) for name in ("fwd_cey", "fwd_meter", "fwd_groups")}
        self.assertEqual(first["days"], 12)
        self.assertEqual(self.meters(), {"days": 0, "cey": 0, "meter": 0, "groups": 0})
        # A program registered later with rows for old days does not rewrite them: the day's row was written once.
        self.now += 86400.0
        self.series(self.register("late@1"), DAYS[:13], rng.normal(0, 0.01, 13))
        for pid in range(1, 5):
            self.day(pid, DAYS[12], 0.001 * pid)
        self.night(DAYS[12])
        self.assertEqual(self.meters()["days"], 1)
        for name, rows in before.items():
            self.assertEqual([r for r in self.table(name) if r["day"] <= DAYS[11]], rows, name)
        self.assertEqual(self.table("fwd_cey")[-1]["members"], 5)

    def test_no_night_no_row_and_no_day_past_the_last_night(self):
        self.series(self.register(), DAYS[:5], [0.01] * 5)
        self.assertEqual(self.meters(), {"days": 0, "cey": 0, "meter": 0, "groups": 0})
        self.night(DAYS[2])
        self.assertEqual(self.meters()["days"], 3)
        self.assertEqual([r["day"] for r in self.table("fwd_cey")], DAYS[:3])


# ============================================================================================== D7: the replay multiple
class TheReplayMultiple(Fixture):
    def test_simulated_program_years_are_the_equity_runs_days_and_the_forward_rows(self):
        store = self.swarm()
        self.equity_family(store, "eq-a")
        self.equity_family(store, "eq-b", "stock")
        self.equity_family(store, "opt-a", "long_single")

        def run(fid, rid, days, *, status="ok", trials=1):
            store.add_run(fid, 1, {"run_id": rid, "status": status, "trials": trials, "summary": {"days": days}},
                          window="train", stress=1.0, purpose="train", prune=False)

        run("eq-a", "r1", 1000)
        run("eq-a", "r2", 750, trials=2)
        run("eq-b", "r3", 500)
        run("eq-a", "r4", 9000, status="refused")       # not a Gym evaluation
        run("eq-a", "r5", 9000, status="error")
        run("eq-a", "r6", 9000, trials=0)               # nothing evaluated
        run("opt-a", "r7", 9000)                        # an options family
        store.close()
        pid, control = self.register(), self.control()
        self.series(pid, DAYS[:4], [0.0] * 4)
        newer = self.label("eq-1+bbbbbbbbbbbb+fwd-1")
        self.series(pid, DAYS[:4], [0.0] * 4, engine=newer)        # any engine: a row is a simulated session
        self.series(control, DAYS[:4], [0.0] * 4, r0=0.0)          # a control is not a program
        self.assertEqual(R.sim_program_years(self.root, self.db, DAYS[3]), (1000 + 1500 + 500 + 8) / 252.0)
        self.assertEqual(R.sim_program_years(self.root, self.db, DAYS[1]), (1000 + 1500 + 500 + 4) / 252.0)

    def test_without_a_swarm_store_only_the_forward_rows_count(self):
        self.series(self.register(), DAYS[:3], [0.0] * 3)
        self.assertEqual(R.sim_program_years(self.root, self.db, DAYS[2]), 3 / 252.0)

    def test_the_historys_independent_years_on_a_synthetic_store(self):
        from league.equity import store as ST
        from league.equity import synth

        symbols = ("SPY", "QQQ", "IWM")
        path = synth.synthetic_store(self.root / ST.STORE_DIR, symbols=symbols, start=dt.date(2024, 1, 2),
                                     end=dt.date(2026, 10, 30), gate=True)
        got = R.hist_independent_years(self.root, [*symbols, "NOPE"])
        # By hand from the store's own files: each year's adjusted closes through the look cap, with the session
        # before the year (the first return's base).
        files = {sym: np.load(path / "bars" / f"{sym}.npz") for sym in symbols}
        days = [ST.from_ordinal(int(o)) for o in files["SPY"]["days"] if ST.from_ordinal(int(o)) <= config.LOOK_CAP]
        closes = np.vstack([files[sym]["all_c"][:len(days)] for sym in symbols])
        by_year = {}
        for year in (2024, 2025, 2026):
            index = [i for i, d in enumerate(days) if d.year == year]
            block = closes[:, max(index[0] - 1, 0):index[-1] + 1]
            by_year[year] = block[:, 1:] / block[:, :-1] - 1.0
        self.assertEqual(sum(v.shape[1] for v in by_year.values()), len(days) - 1, "every session but the store's first")
        self.assertAlmostEqual(got, FS.independent_years(by_year), places=9)
        # Three synthetic symbols drawn apart over about 2.8 years of sessions: near three independent series.
        self.assertTrue(2.2 * len(days) / 252.0 < got <= 3.0 * len(days) / 252.0, got)
        self.assertEqual(R.GATE_REASON, "forward-report")

    def test_a_symbol_counts_only_in_the_years_it_has_a_bar_on_every_session(self):
        from league.equity import store as ST
        from league.equity import synth

        symbols = ("SPY", "QQQ", "IWM")
        span = dict(symbols=symbols, start=dt.date(2024, 1, 2), end=dt.date(2026, 10, 30), gate=True)
        whole = synth.synthetic_store(self.base / "whole" / ST.STORE_DIR, **span)
        synth.synthetic_store(self.root / ST.STORE_DIR, gaps={"IWM": [dt.date(2025, 3, 3)]}, **span)
        files = {sym: np.load(whole / "bars" / f"{sym}.npz") for sym in symbols}
        days = [ST.from_ordinal(int(o)) for o in files["SPY"]["days"] if ST.from_ordinal(int(o)) <= config.LOOK_CAP]
        closes = np.vstack([files[sym]["all_c"][:len(days)] for sym in symbols])
        by_year = {}
        for year in (2024, 2025, 2026):
            index = [i for i, d in enumerate(days) if d.year == year]
            block = closes[:2 if year == 2025 else 3, max(index[0] - 1, 0):index[-1] + 1]   # IWM is out of 2025 alone
            by_year[year] = block[:, 1:] / block[:, :-1] - 1.0
        self.assertAlmostEqual(R.hist_independent_years(self.root, symbols), FS.independent_years(by_year), places=9)
        self.assertLess(R.hist_independent_years(self.root, symbols), R.hist_independent_years(self.base / "whole", symbols))

    def test_a_store_that_cannot_be_read_gives_none_and_the_day_is_written_without_the_multiple(self):
        self.assertIsNone(R.hist_independent_years(self.root, ["SPY"]))
        self.series(self.register(), DAYS[:2], [0.0, 0.01])
        self.night(DAYS[1])
        self.meters()
        row = self.table("fwd_cey")[-1]
        self.assertEqual((row["hist_iy"], row["replay_multiple"]), (None, None))
        self.assertEqual(row["sim_py"], 2 / 252.0)

    def test_the_multiple_is_written_from_the_days_three_figures(self):
        from league.equity import store as ST
        from league.equity import synth

        synth.synthetic_store(self.root / ST.STORE_DIR, symbols=("SPY", "QQQ"), start=dt.date(2025, 6, 2),
                              end=dt.date(2026, 10, 30), gate=True)
        rng = np.random.default_rng(8)
        for i in range(3):
            self.series(self.register(symbols=("SPY", "QQQ")), DAYS[:11], rng.normal(0, 0.01, 11))
        self.night(DAYS[10])
        self.meters()
        row = self.table("fwd_cey")[-1]
        self.assertAlmostEqual(row["hist_iy"], R.hist_independent_years(self.root, ["QQQ", "SPY"]), places=12)
        self.assertEqual(row["sim_py"], 33 / 252.0)
        self.assertEqual(row["replay_multiple"], row["sim_py"] / (row["hist_iy"] + row["cey_total"]))

    def test_with_no_registered_symbol_the_settings_universe_is_read(self):
        from league.equity import store as ST
        from league.equity import synth

        synth.synthetic_store(self.root / ST.STORE_DIR, symbols=("SPY", "QQQ"), start=dt.date(2025, 6, 2),
                              end=dt.date(2026, 10, 30), gate=True)
        self.series(self.register(first_day=DAYS[1], symbols=("SPY",)), DAYS[1:3], [0.0, 0.01])
        self.night(DAYS[2])
        with mock.patch.object(R, "_universe", wraps=R._universe) as universe:
            self.meters()
        self.assertEqual(universe.call_count, 1, "the first forward day: no program registered by then")
        rows = self.table("fwd_cey")
        # The default universe's symbols the store holds (SPY and QQQ) against the one registered symbol.
        self.assertAlmostEqual(rows[0]["hist_iy"], R.hist_independent_years(self.root, ["SPY", "QQQ", "IWM", "DIA"]), places=12)
        self.assertAlmostEqual(rows[1]["hist_iy"], R.hist_independent_years(self.root, ["SPY"]), places=12)
        self.assertNotEqual(rows[0]["hist_iy"], rows[1]["hist_iy"])


# ============================================================================================== D8: any edge anywhere
class TheMeter(Fixture):
    def test_one_p_a_lineage_its_representatives_latest_checkpoint_under_its_newest_engine(self):
        a_fail = self.register("a@1", reason="train_fail", lineage="equity:a")
        a_pass = self.register("a@2", reason="train_pass", lineage="equity:a")
        b = self.register("b@1", reason="train_fail", lineage="equity:b")
        self.register("c@1", reason="seed", lineage="beta:c")                    # no checkpoint: outside the family
        d = self.register("d@1", reason="train_pass", lineage="equity:d")
        newer = self.label("eq-1+bbbbbbbbbbbb+fwd-1")
        self.check(a_fail, 20, DAYS[20], 1e-9)                                  # not its lineage's representative
        self.check(a_pass, 20, DAYS[20], 0.5)
        self.check(a_pass, 60, DAYS[60], 0.0004)
        self.check(a_pass, 20, DAYS[20], 0.3, engine=newer)                     # the newest engine it has: n 20 there
        self.check(b, 20, DAYS[20], None)                                       # never traded: tested, p 1
        self.check(d, 20, DAYS[20], 0.04)
        self.check(d, 37, DAYS[37], 0.2, final=1)                               # a final checkpoint is its latest
        self.check(d, 60, DAYS[70], 0.0001)                                     # written after the day read
        self.night(DAYS[62])
        self.meters()
        rows = {r["day"]: r for r in self.table("fwd_meter")}
        self.assertEqual((rows[DAYS[19]]["m"], rows[DAYS[19]]["min_p"]), (0, None))
        at_20 = rows[DAYS[20]]
        self.assertEqual((at_20["m"], at_20["min_p"]), (3, 0.04))
        last = rows[DAYS[62]]
        self.assertEqual((last["m"], last["bh"], last["by_"], last["min_p"]), (3, 0, 0, 0.2))

    def test_the_counts_are_bh_and_by_over_the_family(self):
        ps = [0.005, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 1.0]
        for i, p in enumerate(ps):
            self.check(self.register(f"fam-{i}@1"), 20, DAYS[20], p)
        self.night(DAYS[21])
        self.meters()
        row = self.table("fwd_meter")[-1]
        self.assertEqual((row["m"], row["bh"], row["by_"], row["min_p"]), (10, FS.bh(ps), FS.by(ps), 0.005))
        self.assertEqual((row["bh"], row["by_"]), (1, 0))
        meter = self.section()["meter"]
        self.assertEqual((meter["reading"], meter["unreliable"], meter["q"]), ("none yet", False, 0.10))
        self.assertNotIn("min_p", meter, "one program's figure: stored, never reported")

    def test_the_controls_are_read_on_their_cost_free_p(self):
        self.check(self.register(), 20, DAYS[20], 0.5)
        for n in range(20):
            # A control's net p is low by its costs; its cost-free p is what the calibration check reads.
            self.check(self.control("index", n), 20, DAYS[20], 0.0001, p_x0=0.05 if n < 3 else 0.2 + 0.04 * n)
        self.check(self.control("sectors", 0), 20, DAYS[20], 0.0001, p_x0=None)
        self.night(DAYS[21])
        self.meters()
        row = self.table("fwd_meter")[-1]
        self.assertEqual((row["controls_m"], row["controls_bh"], row["controls_by"]), (21, 0, 0))
        self.assertAlmostEqual(row["controls_p10"], 3 / 21.0, places=15)
        self.assertEqual((row["m"], row["bh"]), (1, 0))

    def test_a_calibration_failure_reads_unreliable(self):
        self.check(self.register(), 20, DAYS[20], 0.5)
        for n in range(5):
            self.check(self.control("index", n), 20, DAYS[20], 0.5, p_x0=0.0001)
        self.night(DAYS[21])
        self.meters()
        meter = self.section()["meter"]
        self.assertEqual((meter["controls_by"], meter["unreliable"], meter["controls_p10"]), (5, True, 1.0))
        self.assertEqual(meter["engines"], [])


# ============================================================================================== D9: RC
class TheGroups(Fixture):
    def test_each_groups_row_by_hand(self):
        day = DAYS[3]
        passers = [self.register(reason="train_pass", ugroup="index" if i < 4 else "index+sectors") for i in range(6)]
        failers = [self.register(reason="train_fail", ugroup="stocks") for _ in range(5)]
        seed = self.register(reason="seed", ugroup="index")
        live = self.register(reason="live", ugroup="index")                      # a reason that is no RC group
        controls = [self.control("index", n) for n in range(5)]
        late_control = self.control("sectors", 0, first_day=DAYS[9])             # not registered by the day
        for i, pid in enumerate(passers):
            self.day(pid, day, 0.010 + 0.001 * i, w=0.5, b=0.004)
        for i, pid in enumerate(failers):
            self.day(pid, day, -0.002 * i, w=1.0, b=0.004, status="disqualified" if i == 4 else "ok")
        self.day(seed, day, 0.02, w=0.25, b=0.004)
        self.day(live, day, 0.5)
        for n, pid in enumerate(controls):
            self.day(pid, day, -0.001, w=0.4, b=0.004, r0=0.0005 * n)
        self.tag(passers[0], "look_pass", at=close(day) - 1.0)
        self.tag(passers[1], "look_pass", at=close(day) + 1.0)                   # learned after that day's close
        self.tag(passers[2], "look_fail", at=close(DAYS[0]))
        self.tag(seed, "look_pass", at=close(DAYS[1]))
        self.night(day)
        self.meters()
        rows = {r["grp"]: r for r in self.table("fwd_groups") if r["day"] == day}
        self.assertEqual(sorted(rows), ["control:index", "look_fail", "look_pass", "seed", "train_fail", "train_pass"])
        tp = rows["train_pass"]
        self.assertEqual((tp["n"], tp["ugroups"], tp["mean_x0"]), (6, "index+sectors", None))
        self.assertAlmostEqual(tp["mean_r"], 0.0125, places=15)
        self.assertAlmostEqual(tp["mean_x"], 0.0125 - 0.5 * 0.004, places=15)
        self.assertEqual(tp["mean_w"], 0.5)
        tf = rows["train_fail"]
        self.assertEqual((tf["n"], tf["ugroups"]), (4, "stocks"))                # the disqualified day is not counted
        self.assertAlmostEqual(tf["mean_x"], -0.003 - 0.004, places=15)
        self.assertEqual((rows["look_pass"]["n"], rows["look_fail"]["n"], rows["seed"]["n"]), (2, 1, 1))
        self.assertAlmostEqual(rows["look_pass"]["mean_x"], ((0.010 - 0.002) + (0.02 - 0.001)) / 2, places=15)
        control = rows["control:index"]
        self.assertEqual((control["n"], control["ugroups"]), (5, "index"))
        self.assertAlmostEqual(control["mean_x0"], 0.001 - 0.4 * 0.004, places=15)   # cost-free: r0 - w * b
        self.assertAlmostEqual(control["mean_x"], -0.001 - 0.4 * 0.004, places=15)
        self.assertNotIn("control:sectors", rows)
        self.assertEqual(late_control, 19)

    def test_the_cost_free_mean_is_the_controls_alone_and_whole_or_absent(self):
        day = DAYS[0]
        self.day(self.register(reason="train_pass"), day, 0.01, r0=0.02)        # a program's row carries no cost-free series
        for n in range(3):
            self.day(self.control("index", n), day, -0.001, w=0.5, b=0.002, r0=None if n == 2 else 0.001)
        for n in range(2):
            self.day(self.control("sectors", n), day, -0.001, w=0.5, b=0.002, r0=0.001)
        self.night(day)
        self.meters()
        rows = {r["grp"]: r for r in self.table("fwd_groups")}
        self.assertIsNone(rows["train_pass"]["mean_x0"])
        self.assertEqual((rows["control:index"]["n"], rows["control:index"]["mean_x0"]), (3, None),
                         "a control without its cost-free row: no mean is made of the rest")
        self.assertEqual(rows["control:sectors"]["mean_x0"], 0.001 - 0.5 * 0.002)

    def test_a_group_with_no_counted_row_is_written_empty(self):
        self.register()
        self.night(DAYS[0])
        self.meters()
        rows = self.table("fwd_groups")
        self.assertEqual([(r["grp"], r["n"], r["mean_x"], r["ugroups"]) for r in rows],
                         [(g, 0, None, "") for g in ("look_fail", "look_pass", "seed", "train_fail", "train_pass")])


class TheReads(Fixture):
    def groups(self, day: str, **rows) -> None:
        with self.db:
            for grp, (n, x, x0, ugroups) in rows.items():
                self.db.execute("INSERT INTO fwd_groups(day, grp, n, mean_x, mean_r, mean_w, mean_x0, ugroups) "
                                "VALUES(?, ?, ?, ?, 0.0, 1.0, ?, ?)", (day, grp.replace("__", ":"), n, x, x0, ugroups))

    def pair(self, a: str, b: str, day: str) -> dict:
        return next(p for p in R.rc_pairs(self.db, day) if (p["a"], p["b"]) == (a, b))

    def test_no_figure_before_a_pairs_read_and_a_read_on_exactly_its_usable_sessions(self):
        rng = np.random.default_rng(21)
        a, b = rng.normal(0.0004, 0.003, 80), rng.normal(0.0, 0.003, 80)
        usable = 0
        took: list[str] = []
        for i, day in enumerate(DAYS[:75]):
            thin = i in (7, 30)                                   # one side under five programs: not a usable session
            self.groups(day, train_pass=(4 if i == 7 else 9, float(a[i]), None, "index"),
                        train_fail=(4 if i == 30 else 12, float(b[i]), None, "index"))
            usable += 0 if thin else 1
            took += [] if thin else [day]
            pair = self.pair("train_pass", "train_fail", day)
            self.assertEqual(pair["usable"], usable)
            if usable < 60:
                self.assertEqual((pair["reads"], pair["next_read"]), ([], 60))
                self.assertNotIn("mean_bp", json.dumps(R.rc_pairs(self.db, day)), "nothing is shown before the read")
        keep = [i for i in range(75) if i not in (7, 30)][:60]
        want = FS.rc_read(a[keep], b[keep])
        pair = self.pair("train_pass", "train_fail", DAYS[74])
        self.assertEqual((pair["usable"], pair["next_read"]), (73, 120))
        (read,) = pair["reads"]
        self.assertEqual((read["n"], read["day"]), (60, took[59]))
        self.assertEqual((read["mean_bp"], read["t"]), (want["mean_bp"], want["t"]))
        # The sessions after the 60th do not move the read taken on it.
        self.assertEqual(self.pair("train_pass", "train_fail", took[59])["reads"], [read])
        self.assertEqual(forward_db.RC_READS, (60, 120, 250))

    def test_the_second_and_third_reads_and_then_none(self):
        for i, day in enumerate(DAYS[:255]):
            self.groups(day, look_pass=(5, 0.001 * (i % 3), None, "index"), look_fail=(5, 0.0005, None, "index"))
        pair = self.pair("look_pass", "look_fail", DAYS[254])
        self.assertEqual(([r["n"] for r in pair["reads"]], pair["next_read"]), ([60, 120, 250], None))
        self.assertEqual([r["day"] for r in pair["reads"]], [DAYS[59], DAYS[119], DAYS[249]])
        self.assertEqual(self.pair("look_pass", "look_fail", DAYS[119])["next_read"], 250)

    def test_a_program_group_is_read_against_the_pooled_controls_it_names(self):
        for i, day in enumerate(DAYS[:62]):
            sectors = (50, None, 0.0002, "sectors") if i != 5 else (4, None, 0.0002, "sectors")
            rows = {"train_pass": (8, 0.0010, None, "index+sectors"), "control__index": (50, -0.0030, 0.0004, "index"),
                    "control__sectors": sectors, "train_fail": (8, 0.0, None, "index+stocks")}
            if i == 9:
                rows["train_pass"] = (8, 0.0010, None, "defensive+index")     # a group it names has no control row
            self.groups(day, **rows)
        pair = self.pair("train_pass", R.RC_CONTROLS, DAYS[61])
        self.assertEqual(pair["usable"], 60, "the day a named control group is thin, and the day one is absent, are out")
        (read,) = pair["reads"]
        # The controls' cost-free x0, pooled unweighted over the groups named: (0.0004 + 0.0002) / 2.
        self.assertAlmostEqual(read["mean_bp"], (0.0010 - 0.0003) * 1e4, places=9)
        self.assertIsNone(read["t"], "a constant difference has no t")
        self.assertEqual(self.pair("train_fail", R.RC_CONTROLS, DAYS[61])["usable"], 0, "no control:stocks row")
        self.assertEqual([(p["a"], p["b"]) for p in R.rc_pairs(self.db, DAYS[61])],
                         [("look_pass", "look_fail"), ("train_pass", "train_fail"), ("look_pass", "controls"),
                          ("look_fail", "controls"), ("train_pass", "controls"), ("train_fail", "controls")])


# ============================================================================================== the report file
class TheSection(Fixture):
    def test_its_keys_and_its_counts(self):
        a = self.register("a@1", reason="train_pass", lineage="equity:a")
        b = self.register("b@1", reason="train_fail", lineage="equity:b")
        self.register("b@2", reason="train_fail", lineage="equity:b", registered_at=self.now - 3 * 86400)
        c = self.register("c@1", reason="seed", lineage="beta:c")
        d = self.register("d@1", reason="live", lineage="equity:d")
        for n in range(3):
            self.control("index", n)
        for pid in (a, b, c):
            self.series(pid, DAYS[:2], [0.01, -0.01])
        self.day(d, DAYS[0], 0.0, status="disqualified")
        self.tag(b, "stopped", f"cap:{DAYS[1]}")
        self.tag(c, "stopped", f"disqualified:{DAYS[0]}", at=self.now - 10)
        self.tag(c, "resumed", "why", at=self.now)                              # the operator's undo: active again
        self.tag(d, "suspect", DAYS[1])
        self.tag(a, "suspect", DAYS[0])                                         # it has completed a run since
        self.check(a, 20, DAYS[1], 0.4)
        self.check(b, 37, DAYS[1], 0.4, final=1)
        self.check(6, 20, DAYS[1], 0.4, p_x0=0.5)
        self.event("run_failed", pid=d, day=DAYS[1])
        self.event("data_failed", pid=a, day=DAYS[1])
        self.event("data_failed", pid=b, day=DAYS[0])
        self.event("night_failed", day=DAYS[0], at=ny(DAYS[0], 19))
        self.night(DAYS[0], programs=3, sessions=3)
        self.night(DAYS[1], programs=4, sessions=7, stale=2, errors=1)
        self.now = ny(DAYS[1], 20)
        self.meters()
        # The engine label moves after the night: the checkpoint of record is counted once, whatever engine recomputes it.
        self.check(a, 20, DAYS[1], 0.4, engine=self.label("eq-1+bbbbbbbbbbbb+fwd-1"))
        out = self.section()
        self.assertEqual(tuple(out), R.SECTION_KEYS)
        self.assertEqual((out["at"], out["mode"], out["t0"], out["through"]), (S.iso(self.now), "record", DAYS[0], DAYS[1]))
        self.assertEqual(out["engine"], {"id": 2, "label": "eq-1+bbbbbbbbbbbb+fwd-1"})
        registry = out["registry"]
        self.assertEqual((registry["total"], registry["programs"], registry["controls"], registry["lineages"]), (8, 5, 3, 4))
        self.assertEqual(registry["by_reason"], {"train_pass": 1, "train_fail": 2, "seed": 1, "live": 1, "control": 3})
        self.assertEqual(registry["today"]["train_fail"], 1, "the row registered three days ago is not today's")
        self.assertEqual((registry["stopped"], registry["suspects"]), ({"cap": 1, "disqualified": 0}, 1))
        self.assertEqual(registry["chain"], {"ok": True, "rows": 0, "first_bad": None})
        shadow = out["shadow"]
        self.assertEqual((shadow["through"], shadow["nights"], shadow["programs"], shadow["sessions"], shadow["stale"],
                          shadow["errors"], shadow["budget_hit"]), (DAYS[1], 2, 4, 7, 2, 1, True))
        self.assertEqual((shadow["run_failed"], shadow["data_failed"], shadow["run_disqualified"]), (1, 1, 0))
        self.assertEqual(shadow["night_failed"], {"day": DAYS[0], "at": S.iso(ny(DAYS[0], 19))})
        self.assertEqual(out["checkpoints"], {"20": 1, "60": 0, "120": 0, "250": 0, "later": 0, "final": 1, "controls": 1})
        self.assertEqual(out["meter"]["engines"], [1])
        self.assertEqual(out["rc"]["groups"]["train_pass"], 1)
        self.assertEqual(len(out["rc"]["pairs"]), 6)
        self.assertEqual((out["memory"], out["contamination"], out["receipts"]), (None, None, []))

    def test_without_a_forward_store_the_report_is_still_whole(self):
        self.db.close()
        (self.root / forward_db.DB).unlink()
        out = self.section()
        self.assertEqual(tuple(out), R.SECTION_KEYS)
        self.assertEqual((out["registry"], out["shadow"], out["cey"], out["through"], out["alarms"]),
                         (None, None, None, None, []))

    def test_a_part_that_cannot_be_read_is_named_and_the_rest_is_written(self):
        self.register()
        with mock.patch.object(R, "_fills", side_effect=sqlite3.OperationalError("database is locked")):
            out = self.section()
        self.assertEqual(out["fills"], {"error": "OperationalError"})
        self.assertEqual(out["registry"]["programs"], 1)
        with mock.patch.object(forward_db, "verify_chain", side_effect=RuntimeError("no chain")):
            out = self.section()
        self.assertEqual(out["registry"]["chain"], {"ok": None, "error": "RuntimeError"})
        # Unread is not broken: no warning says the chain does not hold; an info row says the alarm was not read.
        self.assertEqual(out["alarms"], [{"id": "FW4", "level": "info", "new": True,
                                          "text": "FW4 unread: this alarm could not be read (RuntimeError)"}])

    def test_an_alarm_that_cannot_be_read_does_not_lose_the_others(self):
        self.register(first_day=DAYS[0])
        self.now = ny(DAYS[2], 12)
        self.event("identity_moved", at=self.now - 60)
        with mock.patch.object(R, "_nights", side_effect=sqlite3.OperationalError("database is locked")):
            out = self.section()
        self.assertEqual([(a["id"], a["level"]) for a in out["alarms"]],
                         [("FW1", "warning"), ("FW2", "info"), ("FW3", "info"), ("FW8", "warning")])
        self.assertTrue(all(R.text_ok(a["text"]) for a in out["alarms"]))
        self.assertEqual(out["shadow"], {"error": "OperationalError"})

    def test_the_fills_and_twins_as_recorded(self):
        live = self.register("live-a@3", reason="live")
        plain = self.register("plain-b@1", reason="train_pass")
        self.tag(live, "live", "live-a@3:r")
        with self.db:
            for i, (at, drift) in enumerate((("open", 4.0), ("open", 8.0), ("open", 6.0), ("close", -2.0))):
                self.db.execute("INSERT INTO fwd_fillgap VALUES(?, ?, ?, 100.0, 100.04, ?, '09:31', 'vw')",
                                (DAYS[0], f"S{i}", at, drift))
            for lid, (inst, pid, gap) in enumerate((("live-a@3:r", live, -3.0), ("live-a@3:r", live, -5.0),
                                                    ("live-a@3:r", live, None), ("plain-b@1:r", plain, 9.0)), 1):
                self.db.execute("INSERT INTO fwd_lotgap(lid, instance, pid, symbol, opened_day, exit_day, entry_at, "
                                "exit_at, model_bp, entry_slip_bp, exit_slip_bp, side_gap_bp, twin_gap_bp, at) "
                                "VALUES(?, ?, ?, 'SPY', ?, ?, 'open', 'open', 1.0, 3.0, 5.0, 3.0, ?, 1.0)",
                                (lid, inst, pid, DAYS[0], DAYS[1], gap))
            twins = (("live-a@3:r", live, DAYS[0], 1, None, None), ("live-a@3:r", live, DAYS[1], 0, None, "bars"),
                     ("live-a@3:r", live, DAYS[2], 0, None, "program"), ("live-a@3:r", live, DAYS[3], None, "split", None),
                     ("plain-b@1:r", plain, DAYS[0], 1, None, None))
            for inst, pid, day, agree, why, cause in twins:
                self.db.execute("INSERT INTO fwd_twins(instance, day, pid, live_keys, shadow_keys, agree, why, at, cause) "
                                "VALUES(?, ?, ?, '[]', '[]', ?, ?, 1.0, ?)", (inst, day, pid, agree, why, cause))
            self.db.execute("INSERT INTO fwd_part VALUES('live-a@3:r', ?, ?, 1, 9, 9, 1.0)", (DAYS[0], live))
            self.db.execute("INSERT INTO fwd_part VALUES('live-a@3:r', ?, ?, 6, 1, 1, 1.0)", (DAYS[2], live))
            self.db.execute("INSERT INTO fwd_ll VALUES(?, ?, 1, 0.001, 1.0)", (live, DAYS[0]))
        self.event("no_minute", pid=live, day=DAYS[1])
        fills = self.section()["fills"]
        self.assertEqual(fills["timing"]["open"], {"n": 3, "mean_bp": 6.0, "se_bp": 2.0 / math.sqrt(3.0)})
        self.assertEqual(fills["timing"]["close"], {"n": 1, "mean_bp": -2.0, "se_bp": None})
        self.assertEqual(fills["livelike"], {"rows": 1, "no_minute": 1})
        self.assertEqual((fills["lots"]["n"], fills["lots"]["priced"], fills["lots"]["bound_bp"]), (4, 3, 15.0))
        self.assertAlmostEqual(fills["lots"]["mean"]["twin_gap_bp"], 1.0 / 3.0, places=12)
        self.assertEqual((fills["lots"]["mean"]["side_gap_bp"], fills["lots"]["mean"]["timing_entry_bp"]), (3.0, None))
        self.assertEqual(fills["participation"], {"instances": 1, "matched": 6, "missed": 1, "extra": 1, "rate": 0.75})
        intents = fills["intents"]
        self.assertEqual((intents["sessions"], intents["agreed"], intents["disagreed"], intents["unreadable"]), (4, 2, 2, 1))
        self.assertEqual((intents["causes"], intents["share"], intents["bound"]),
                         ({"bars": 1, "program": 1, "unknown": 0}, 0.5, 0.95))
        # One row a LIVE instance (its registry row carries the "live" tag); the other is in the aggregates only.
        self.assertEqual(fills["by_instance"], [{"instance": "live-a@3:r", "pid": live, "lots": 3, "priced": 2,
                                                 "mean_twin_gap_bp": -4.0, "sessions": 3, "agreed": 1, "disagreed": 2,
                                                 "causes": {"bars": 1, "program": 1, "unknown": 0}, "unreadable": 1}])


class ReadingTheSection(Fixture):
    def write(self, at: float, **doc) -> None:
        write_json(self.root / R.FILE, {"at": S.iso(at), "mode": "record", "alarms": [], **doc})

    def read_at(self, now: float):
        with mock.patch.object(R.time, "time", lambda: now):
            return R.read_section(self.root)

    def test_absent_unreadable_and_fresh(self):
        self.assertIsNone(self.read_at(self.now))
        (self.root / R.FILE).write_text("{torn")
        self.assertIsNone(self.read_at(self.now))
        (self.root / R.FILE).write_text("[1, 2]")
        self.assertIsNone(self.read_at(self.now))
        self.write(self.now, through=DAYS[0])
        self.assertEqual(self.read_at(self.now + 35 * 3600)["through"], DAYS[0])
        write_json(self.root / R.FILE, {"mode": "record"})
        self.assertIsNone(self.read_at(self.now), "a report that does not say when it was written")

    def test_stale_once_a_run_was_missed_and_thirty_six_hours_passed(self):
        tuesday, wednesday, thursday = DAYS[1], DAYS[2], DAYS[3]
        written = ny(tuesday, 18, 40)                                # after Tuesday night's shadow
        self.write(written)
        self.assertIsNotNone(self.read_at(ny(wednesday, 12)), "the 08:55 run is overdue, the report 17 hours old")
        self.assertIsNotNone(self.read_at(written + 36 * 3600 - 1))
        self.assertIsNone(self.read_at(written + 36 * 3600 + 1), "36 hours, and Wednesday's 08:55 run never wrote")
        self.assertIsNone(self.read_at(ny(thursday, 12)))
        self.assertEqual(R.STALE_HOURS, 36.0)

    def test_a_weekend_makes_no_report_stale(self):
        friday = next(d for d in DAYS if dt.date.fromisoformat(d).weekday() == 4)
        monday = DAYS[DAYS.index(friday) + 1]
        written = ny(friday, 18, 40)
        self.write(written)
        sunday = ny(friday, 21, 30) + 2 * 86400                      # the dlane job's Sunday run: 51 hours old
        self.assertGreater(sunday - written, 36 * 3600)
        self.assertIsNotNone(self.read_at(sunday), "no run of the job fell due since Friday night")
        self.assertIsNotNone(self.read_at(ny(monday, 9, 0)), "Monday's 08:55 run is inside its grace")
        self.assertIsNotNone(self.read_at(ny(monday, 11, 54)))
        self.assertIsNone(self.read_at(ny(monday, 11, 56)), "three hours past Monday's 08:55 run")


# ============================================================================================== the funnel's counts
class TheFunnelRows(Fixture):
    def test_zeros_and_integers_without_any_store(self):
        self.db.close()
        (self.root / forward_db.DB).unlink()
        out = R.funnel_rows(self.root, 0.0, self.now)
        self.assertEqual(out, {key: 0 for key in R.FUNNEL_KEYS})
        self.assertTrue(all(type(v) is int for v in out.values()))
        self.assertEqual(tuple(out), R.FUNNEL_KEYS)

    def test_the_counts_of_a_window(self):
        start = self.now
        early = self.register("a@1", lineage="equity:a", registered_at=start - 5 * 86400)
        self.register("a@2", lineage="equity:a", registered_at=start + 100)
        late = self.register("b@1", lineage="equity:b", registered_at=start + 200)
        self.control("index", 0)
        self.day(early, DAYS[0], 0.01, at=start - 86400)
        self.day(early, DAYS[1], 0.01, at=start + 300)
        self.day(late, DAYS[1], 0.01, at=start + 300)
        self.day(4, DAYS[1], 0.01, r0=0.0, at=start + 300)                       # a control's row is no program-session
        newer = self.label("eq-1+bbbbbbbbbbbb+fwd-1")
        for day in DAYS[:2]:
            self.day(early, day, 0.01, engine=newer, at=start + 400)             # an engine move counts nothing twice
        self.check(early, 20, DAYS[1], 0.4, at=start + 300)
        self.check(early, 20, DAYS[1], 0.4, engine=newer, at=start + 400)
        self.check(4, 20, DAYS[1], 0.4, p_x0=0.5, at=start + 300)
        self.night(DAYS[0], stale=7, errors=1, started=start - 86400)
        self.night(DAYS[1], stale=3, errors=2, started=start + 250)
        self.event("night_failed", day=DAYS[1], at=start + 100)
        with self.db:
            self.db.execute("INSERT INTO fwd_meter VALUES(?, 5, 2, 1, 0.001, 0, 0, 0, NULL, ?)", (DAYS[1], start + 500))
        out = R.funnel_rows(self.root, start, start + 3600)
        self.assertEqual(out, {"registered": 2, "registered_total": 3, "lineages": 2, "controls": 1, "program_sessions": 2,
                               "program_sessions_total": 3, "stale": 3, "errors": 3, "checkpoints": 1, "bh": 2, "by": 1,
                               "oof_seen": 0, "oof_rows": 0})
        self.assertTrue(all(type(v) is int for v in out.values()))
        before = R.funnel_rows(self.root, start - 2 * 86400, start)
        self.assertEqual((before["registered"], before["program_sessions"], before["stale"], before["errors"], before["bh"]),
                         (0, 1, 7, 1, 0))

    def test_the_memory_rows_of_the_window_from_the_swarm_store(self):
        store = self.swarm()
        store.close()
        db = sqlite3.connect(str(self.root / "swarm.sqlite"))
        self.addCleanup(db.close)
        self.assertEqual(R.funnel_rows(self.root, 0.0, self.now + 1)["oof_rows"], 0, "no memory table: nothing recorded")
        db.executescript(elane_memory.SCHEMA)
        inside, outside = S.iso(self.now), S.iso(self.now - 5 * 86400)
        for n, at in enumerate((inside, inside, outside)):
            db.execute("INSERT INTO mem_seen(family, version, cell, gid, bar_passed, fails, seen_sha, at) "
                       "VALUES('fake', ?, 'c', 'g0', 0, '[]', 's', ?)", (n, at))
        for n, at in enumerate((inside, outside)):
            db.execute("INSERT INTO mem_contrib(family, version, cell, kind, year, symset, k, status, n_days, n_lots, "
                       "exp_mean, e_ann, series_sha, run_sha, at) VALUES('fake', ?, 'c', 'own', 2017, 'own', 1.0, 'ok', "
                       "250, 9, 0.5, 0.777777, 's', 'r', ?)", (n, at))
        db.commit()
        out = R.funnel_rows(self.root, self.now - 3600, self.now + 3600)
        self.assertEqual((out["oof_seen"], out["oof_rows"]), (2, 1))
        self.assertEqual(self.section()["memory"], {"seen": 3, "contrib": 2, "families": 1, "by_year": {"2017": 2}})

    def test_an_unreadable_store_raises(self):
        self.db.close()
        (self.root / forward_db.DB).write_bytes(b"this is not a database at all, not one page of it")
        with self.assertRaises(sqlite3.DatabaseError):
            R.funnel_rows(self.root, 0.0, self.now)


# ============================================================================================== the alarms
class FW1TheStalledJob(Fixture):
    def test_no_row_by_nine_the_next_session_for_a_day_a_program_was_owed(self):
        self.register(first_day=DAYS[0])
        self.now = ny(DAYS[1], 8, 59)
        self.assertNotIn("FW1", self.ids())
        self.now = ny(DAYS[1], 9, 0)
        (alarm,) = [a for a in self.section()["alarms"] if a["id"] == "FW1"]
        self.assertEqual(alarm["level"], "warning")
        self.assertIn(f"no forward row for {DAYS[0]} by 09:00 New York on {DAYS[1]} though 1 registered rows", alarm["text"])
        self.day(1, DAYS[0], 0.01)
        self.assertNotIn("FW1", self.ids())

    def test_silent_on_an_empty_registry(self):
        self.now = ny(DAYS[5], 12)
        self.assertEqual(self.ids(), [])
        self.assertEqual(R.alarms(self.root, now=self.now, settings=RECORD), [])

    def test_silent_on_the_two_sessions_after_a_first_registration(self):
        # Registered during the first forward session: it first decides at that close, its first day is the next.
        self.register(first_day=DAYS[1])
        for now in (ny(DAYS[0], 11), ny(DAYS[0], 20), ny(DAYS[1], 9, 30), ny(DAYS[1], 23), ny(DAYS[2], 8, 59)):
            self.now = now
            self.assertNotIn("FW1", self.ids(), S.iso(now))
            self.assertEqual(R.alarms(self.root, now=now, settings=RECORD), [], "no report yet, and nothing owed")
        self.now = ny(DAYS[2], 9, 0)
        self.assertIn("FW1", self.ids())

    def test_silent_when_every_owed_program_is_stopped_and_loud_again_once_one_is_resumed(self):
        pid = self.register(first_day=DAYS[0])
        self.tag(pid, "stopped", f"cap:{DAYS[0]}", at=self.now)
        self.now = ny(DAYS[1], 10)
        self.assertNotIn("FW1", self.ids())
        self.tag(pid, "resumed", "why", at=self.now)
        self.assertIn("FW1", self.ids())

    def test_silent_with_the_mode_off_whatever_the_files_age(self):
        self.register(first_day=DAYS[0])
        self.now = ny(DAYS[6], 12)
        self.assertNotIn("FW1", self.ids(OFF))
        write_json(self.root / R.FILE, {"at": S.iso(self.now - 5 * 86400), "mode": "record",
                                        "alarms": [{"id": "FW3", "level": "warning", "text": "FW3: old", "new": True}]})
        self.assertEqual(R.alarms(self.root, now=self.now, settings=OFF), [], "the mode is off: a file 5 days old")
        write_json(self.root / R.FILE, {"at": S.iso(self.now - 5 * 86400), "mode": "off", "alarms": []})
        self.assertEqual(R.alarms(self.root, now=self.now, settings=RECORD), [], "the file says the mode was off")


class TheReadersAlarms(Fixture):
    """`alarms`, as the dlane report reads them."""

    ROW = {"id": "FW3", "level": "warning", "text": "FW3: 2 stored days of 1 programs were restated", "new": True}

    def test_the_files_alarms_while_it_is_fresh(self):
        write_json(self.root / R.FILE, {"at": S.iso(self.now), "mode": "record",
                                        "alarms": [self.ROW, {"id": "FW2", "text": "no level"}, "junk",
                                                   {"id": 7, "level": "warning", "text": "t"},
                                                   {"id": "CP1", "level": "info", "text": "CP1 route x: t"}]})
        got = R.alarms(self.root, now=self.now + 3600, settings=RECORD)
        self.assertEqual(got, [self.ROW, {"id": "CP1", "level": "info", "text": "CP1 route x: t", "new": False}])
        self.assertTrue(all(set(a) == {"id", "level", "text", "new"} for a in got))

    def test_a_stale_report_is_one_fw1_row_when_a_program_is_owed(self):
        self.register(first_day=DAYS[0])
        written = ny(DAYS[1], 18, 40)
        write_json(self.root / R.FILE, {"at": S.iso(written), "mode": "record", "alarms": [self.ROW]})
        self.assertEqual(R.alarms(self.root, now=written + 30 * 3600, settings=RECORD), [self.ROW])
        (alarm,) = R.alarms(self.root, now=ny(DAYS[3], 12), settings=RECORD)
        self.assertEqual((alarm["id"], alarm["level"], alarm["new"]), ("FW1", "warning", True))
        self.assertIn(f"last written on {DAYS[1]}", alarm["text"])
        self.assertTrue(R.text_ok(alarm["text"]))
        (self.root / R.FILE).unlink()
        (alarm,) = R.alarms(self.root, now=ny(DAYS[3], 12), settings=RECORD)
        self.assertIn("there is no forward report", alarm["text"])

    def test_a_weekend_old_report_still_gives_its_own_alarms(self):
        self.register(first_day=DAYS[0])
        friday = next(d for d in DAYS if dt.date.fromisoformat(d).weekday() == 4)
        write_json(self.root / R.FILE, {"at": S.iso(ny(friday, 18, 40)), "mode": "record", "alarms": [self.ROW]})
        self.assertEqual(R.alarms(self.root, now=ny(friday, 21, 30) + 2 * 86400, settings=RECORD), [self.ROW])

    def test_it_never_raises(self):
        (self.root / R.FILE).write_text("{torn")
        self.assertEqual(R.alarms(self.root, now=self.now, settings=RECORD), [], "nothing registered: nothing owed")
        self.assertEqual(R.alarms(self.base / "nowhere", now=self.now, settings=RECORD), [])
        self.assertEqual(R.alarms(self.root, now=self.now, settings={"elane": "torn"}), [])
        self.register(first_day=DAYS[0])
        with mock.patch.object(forward_db, "open_db", side_effect=sqlite3.OperationalError("locked")):
            (alarm,) = R.alarms(self.root, now=ny(DAYS[3], 12), settings=RECORD)
        self.assertIn("the forward store could not be read", alarm["text"])

    def test_no_settings_handed_in_reads_the_swarms_own(self):
        (self.root / "swarm.json").write_text(json.dumps(RECORD))
        write_json(self.root / R.FILE, {"at": S.iso(self.now), "mode": "record", "alarms": [self.ROW]})
        self.assertEqual(R.alarms(self.root, now=self.now), [self.ROW])
        (self.root / "swarm.json").write_text(json.dumps(OFF))
        self.assertEqual(R.alarms(self.root, now=self.now), [])


class EachForwardAlarm(Fixture):
    def setUp(self):
        super().setUp()
        self.pid_a = self.register("a@1", first_day=DAYS[0])
        for day in DAYS[:12]:
            self.day(self.pid_a, day, 0.001)
        self.now = ny(DAYS[11], 20)

    def test_nothing_holds_on_a_quiet_night(self):
        self.night(DAYS[10])
        self.night(DAYS[11])
        self.assertEqual(self.ids(), [])

    def test_fw2_programs_left_stale_two_nights_running(self):
        self.night(DAYS[9], stale=0)
        self.night(DAYS[10], stale=4)
        self.assertNotIn("FW2", self.ids(), "one night: the backlog is under a day old")
        self.night(DAYS[11], stale=0)
        self.assertNotIn("FW2", self.ids(), "the night after caught up")
        self.night(DAYS[11], stale=6)                              # the night's later run (a restart) is the night's
        (alarm,) = [a for a in self.section()["alarms"] if a["id"] == "FW2"]
        self.assertIn(f"({DAYS[10]}: 4, {DAYS[11]}: 6)", alarm["text"])

    def test_fw2_a_program_that_failed_on_two_nights_running(self):
        b, c = self.register("b@1"), self.register("c@1")
        self.night(DAYS[10])
        self.night(DAYS[11])
        self.event("data_failed", pid=self.pid_a, day=DAYS[10])
        self.event("run_failed", pid=b, day=DAYS[11])
        self.event("data_failed", pid=c, day=DAYS[9])              # not the night before
        self.event("data_failed", pid=c, day=DAYS[11])
        self.assertNotIn("FW2", self.ids(), "no program failed on both nights")
        self.event("run_failed", pid=self.pid_a, day=DAYS[11])
        self.event("data_failed", pid=b, day=DAYS[10])
        (alarm,) = [a for a in self.section()["alarms"] if a["id"] == "FW2"]
        self.assertIn(f"2 programs failed on both {DAYS[10]} and {DAYS[11]} (0 without data, 2 whose run failed alone)",
                      alarm["text"])

    def test_fw3_a_day_restated_last_night(self):
        self.night(DAYS[10])
        self.event("restated", pid=self.pid_a, day=DAYS[3], at=ny(DAYS[10], 18, 36))
        self.night(DAYS[11])
        self.assertNotIn("FW3", self.ids(), "written the night before last")
        self.event("restated", pid=self.pid_a, day=DAYS[4], at=ny(DAYS[11], 18, 36))
        self.event("restated", pid=self.pid_a, day=DAYS[5], at=ny(DAYS[11], 18, 36))
        (alarm,) = [a for a in self.section()["alarms"] if a["id"] == "FW3"]
        self.assertIn(f"2 stored days of 1 programs were restated on the night of {DAYS[11]}", alarm["text"])

    def test_fw4_the_chain_does_not_hold(self):
        FakeA.chain = {"ok": False, "rows": 9, "first_bad": 4}
        (alarm,) = [a for a in self.section()["alarms"] if a["id"] == "FW4"]
        self.assertIn("does not hold from pid 4 (9 rows): stop the forward jobs and compare with the backup", alarm["text"])
        self.assertEqual(self.section()["registry"]["chain"], {"ok": False, "rows": 9, "first_bad": 4})

    def cey(self, values) -> None:
        with self.db:
            for day, value in zip(DAYS, values):
                self.db.execute("INSERT INTO fwd_cey(day, n_w, members, neff, neff_raw, cey_day, cey_total, at) "
                                "VALUES(?, 60, 5, ?, 1.0, ?, 0.0, 1.0)", (day, value * 252.0, value))

    def test_fw5_the_increment_under_its_median_ten_days_running_while_births_go_on(self):
        store = self.swarm()
        self.equity_family(store, "eq-a")
        self.now = ny(DAYS[25], 12)
        store.event("swarm.born", "eq-a", {"lane": "beta"})
        falling = [0.10] * 20 + [0.09 - 0.001 * i for i in range(10)]
        self.cey(falling[:29])
        self.now = ny(DAYS[28], 20)
        self.assertNotIn("FW5", self.ids(), "nine days running")
        with self.db:
            self.db.execute("INSERT INTO fwd_cey(day, n_w, members, neff, neff_raw, cey_day, cey_total, at) "
                            "VALUES(?, 60, 5, 1.0, 1.0, ?, 0.0, 1.0)", (DAYS[29], falling[29]))
        self.now = ny(DAYS[29], 20)
        (alarm,) = [a for a in self.section()["alarms"] if a["id"] == "FW5"]
        self.assertIn(f"for 10 forward days running (since {DAYS[20]}) while 1 equity births went on", alarm["text"])

    def test_fw5_needs_equity_births_in_those_days(self):
        store = self.swarm()
        self.equity_family(store, "eq-a")
        self.now = ny(DAYS[15], 12)                                 # before the ten days: the generators have stopped
        store.event("swarm.born", "eq-a", {"lane": "beta"})
        self.cey([0.10] * 20 + [0.09 - 0.001 * i for i in range(10)])
        self.now = ny(DAYS[29], 20)
        self.assertNotIn("FW5", self.ids())

    def test_fw5_is_silent_while_the_increment_holds_its_median(self):
        store = self.swarm()
        self.equity_family(store, "eq-a")
        store.event("swarm.born", "eq-a", {"lane": "beta"})
        self.cey([0.0] * 9 + [0.05] * 30)                          # the first nine sessions accrue nothing, by rule
        self.now = ny(DAYS[38], 20)
        self.assertNotIn("FW5", self.ids())

    def lots(self, instance: str, pid: int, gaps) -> None:
        start = self.db.execute("SELECT coalesce(max(lid), 0) FROM fwd_lotgap").fetchone()[0]
        with self.db:
            for i, gap in enumerate(gaps, 1):
                self.db.execute("INSERT INTO fwd_lotgap(lid, instance, pid, symbol, opened_day, exit_day, entry_at, "
                                "exit_at, model_bp, twin_gap_bp, at) VALUES(?, ?, ?, 'SPY', ?, ?, 'open', 'open', 1.0, ?, "
                                "1.0)", (start + i, instance, pid, DAYS[0], DAYS[1], gap))

    def twins(self, instance: str, pid: int, agreed: int, sessions: int, unreadable: int = 0, bars: int = 0) -> None:
        with self.db:
            for i in range(sessions + unreadable):
                agree = None if i >= sessions else 1 if i < agreed else 0
                cause = None if agree != 0 else "bars" if i < agreed + bars else "program"
                self.db.execute("INSERT INTO fwd_twins(instance, day, pid, live_keys, shadow_keys, agree, at, cause) "
                                "VALUES(?, ?, ?, '[]', '[]', ?, 1.0, ?)", (instance, DAYS[i], pid, agree, cause))

    def test_fw6_a_mean_twin_gap_beyond_the_bound_either_way(self):
        self.lots("a@1:r", self.pid_a, [-16.0] * 5)
        self.lots("b@1:r", 2, [16.5] * 4 + [None])                 # four priced closes: not read yet
        self.lots("c@1:r", 3, [-14.0, -16.0, -15.0, -15.0, -15.0])  # a mean of exactly 15: inside
        self.lots("d@1:r", 4, [17.0] * 6)
        rows = [a for a in self.section()["alarms"] if a["id"] == "FW6"]
        self.assertEqual(len(rows), 2)
        self.assertIn("FW6 instance a@1:r gap: its mean twin gap over 5 priced closes is beyond the A14 bound (worse",
                      rows[0]["text"])
        self.assertIn("FW6 instance d@1:r gap: its mean twin gap over 6 priced closes is beyond the A14 bound (better",
                      rows[1]["text"])
        self.assertTrue(all(R.text_ok(a["text"]) for a in rows), "the instance and the counts, no figure")

    def test_fw6_twenty_sessions_under_the_agreement_bound(self):
        self.twins("a@1:r", self.pid_a, 18, 20, bars=1)
        self.twins("b@1:r", 2, 19, 20)                              # 95 of 100: holds
        self.twins("c@1:r", 3, 10, 19, unreadable=5)                # nineteen readable sessions: not read yet
        (alarm,) = [a for a in self.section()["alarms"] if a["id"] == "FW6"]
        # A disagreement is data, counted with its cause: it still counts against the bound (A14's rule is unchanged).
        self.assertEqual(alarm["text"], "FW6 instance a@1:r intents: 18 of 20 sessions agree with its twin, under the A14 "
                                        "bound (1 of the 2 that differ read other bars than the store now holds)")

    def test_fw6_a_disagreement_counts_whatever_its_cause(self):
        self.twins("a@1:r", self.pid_a, 18, 20, bars=2)             # both for the bars alone: still 18 of 20
        (alarm,) = [a for a in self.section()["alarms"] if a["id"] == "FW6"]
        self.assertIn("18 of 20 sessions agree", alarm["text"])
        self.assertIn("(2 of the 2 that differ read other bars", alarm["text"])
        self.assertTrue(R.text_ok(alarm["text"]))

    def test_fw6_is_about_living_instances(self):
        from league.live.state import LiveState
        from league.tests.test_equity_twins import add_tables

        self.lots("a@1:r", self.pid_a, [-20.0] * 5)
        live = LiveState(self.root / "live.sqlite")
        self.addCleanup(live.close)
        add_tables(live)
        live.db.execute("INSERT INTO eq_instances(id, family, version, lane, run_sha, code, params, band, max_hold, "
                        "created_at, retired_at) VALUES('a@1:r', 'a', 1, 'beta', 'r', 'c', '{}', 'probe', 20, 1.0, 2.0)")
        live.db.commit()
        self.assertNotIn("FW6", self.ids())

    def book(self, decide: dict | None, *, retired: bool = False):
        from league.live.state import LiveState
        from league.tests.test_equity_twins import add_tables

        live = LiveState(self.root / "live.sqlite")
        self.addCleanup(live.close)
        add_tables(live)
        live.db.execute("INSERT OR REPLACE INTO eq_instances(id, family, version, lane, run_sha, code, params, band, "
                        "max_hold, created_at, retired_at) VALUES('a@1:r', 'a', 1, 'beta', 'r', 'c', '{}', 'probe', 20, "
                        "1.0, ?)", (2.0 if retired else None,))
        live.db.commit()
        if decide is not None:
            live.put("eq_decide", decide)
        return live

    def test_fw7_a_failed_decide(self):
        live = self.book({"day": DAYS[11], "status": "failed", "at": close(DAYS[11]) + 1800, "why": "the bars"})
        (alarm,) = [a for a in self.section()["alarms"] if a["id"] == "FW7"]
        self.assertIn(f"the equity decide of {DAYS[11]} failed", alarm["text"])
        live.put("eq_decide", {"day": DAYS[11], "status": "done", "at": close(DAYS[11]) + 1800})
        self.assertNotIn("FW7", self.ids())

    def test_fw7_a_decide_later_than_forty_minutes_after_the_close(self):
        live = self.book({"day": DAYS[11], "status": "done", "at": close(DAYS[11]) + 2400})
        self.assertNotIn("FW7", self.ids(), "16:40 itself is on time")
        live.put("eq_decide", {"day": DAYS[11], "status": "done", "at": close(DAYS[11]) + 2401})
        (alarm,) = [a for a in self.section()["alarms"] if a["id"] == "FW7"]
        self.assertIn(f"the equity decide of {DAYS[11]} ran late", alarm["text"])
        # With no live program the book writes a `why` at about 16:20, late or not: ignored.
        live.put("eq_decide", {"day": DAYS[11], "status": "done", "at": close(DAYS[11]) + 9000, "why": "no live program"})
        self.assertNotIn("FW7", self.ids())

    def test_fw7_only_while_an_instance_lives(self):
        self.book({"day": DAYS[11], "status": "failed", "at": 1.0}, retired=True)
        self.assertNotIn("FW7", self.ids())

    def test_fw8_the_identity_moved_while_a_lineage_is_live(self):
        self.event("identity_moved", at=self.now - 30 * 3600)
        self.assertNotIn("FW8", self.ids(), "more than a day ago")
        self.event("identity_moved", at=self.now - 3600)
        (alarm,) = [a for a in self.section()["alarms"] if a["id"] == "FW8"]
        self.assertIn("the equity fingerprint moved while a lineage is live (1 identity_moved events", alarm["text"])

    def test_fw8_reads_back_to_the_last_report_over_a_weekend(self):
        friday = next(d for d in DAYS[5:] if dt.date.fromisoformat(d).weekday() == 4)
        monday = DAYS[DAYS.index(friday) + 1]
        write_json(self.root / R.FILE, {"at": S.iso(ny(friday, 18, 40)), "mode": "record", "alarms": []})
        self.event("identity_moved", at=ny(friday, 23))             # a Friday night deploy
        self.now = ny(monday, 8, 55)
        self.assertIn("FW8", self.ids(), "sixty hours ago, and not yet told")

    def test_with_the_mode_off_no_forward_alarm_is_raised(self):
        FakeA.chain = {"ok": False, "rows": 9, "first_bad": 4}
        self.night(DAYS[10], stale=4)
        self.night(DAYS[11], stale=4)
        self.event("restated", pid=self.pid_a, day=DAYS[4], at=ny(DAYS[11], 18, 36))
        self.book({"day": DAYS[11], "status": "failed", "at": 1.0})
        self.now = ny(DAYS[13], 12)
        self.event("identity_moved", at=self.now - 60)
        self.assertEqual(self.ids(OFF), [])
        self.assertEqual(sorted(set(self.ids())), ["FW1", "FW2", "FW3", "FW4", "FW7", "FW8"])


class TheOtherAlarms(Fixture):
    def receipts(self, *rows) -> None:
        db = sqlite3.connect(str(self.root / RR.DB))
        self.addCleanup(db.close)
        db.executescript(RR.SCHEMA)
        for rid, kind, deployed, verdict, at in rows:
            db.execute("INSERT INTO l3_receipts(id, kind, release, metric, direction, min_delta, window_hours, "
                       "deployed_at, value, verdict, at) VALUES(?, ?, 'E3', 'forward_record.program_sessions', 'up', 1, "
                       "72, ?, 3, ?, ?)", (rid, kind, deployed, verdict, at))
        db.commit()

    def test_rr1_a_receipt_unread_a_day_after_its_window_closed(self):
        deployed = self.now - 96 * 3600
        self.receipts(("fake-a", "declared", deployed, None, deployed), ("fake-b", "declared", deployed + 60, None, deployed))
        out = self.section()
        (alarm,) = out["alarms"]
        self.assertEqual((alarm["id"], alarm["level"]), ("RR1", "warning"))
        self.assertIn(f"RR1 receipt fake-a: unread though its window closed on {S.iso(deployed + 72 * 3600)[:10]}",
                      alarm["text"])
        self.assertEqual([(r["id"], r["unread"]) for r in out["receipts"]], [("fake-a", True), ("fake-b", False)])

    def test_rr2_a_receipt_read_flat_or_the_wrong_way_is_listed_for_a_week(self):
        deployed = self.now - 80 * 3600
        self.receipts(("fake-a", "declared", deployed, None, deployed), ("fake-a", "read", deployed, "flat", self.now - 3600),
                      ("fake-b", "declared", deployed, None, deployed), ("fake-b", "read", deployed, "wrong_way", self.now),
                      ("fake-c", "declared", deployed, None, deployed), ("fake-c", "read", deployed, "moved", self.now),
                      ("fake-d", "declared", deployed, None, deployed),
                      ("fake-d", "read", deployed, "unreadable", self.now))
        rows = self.section()["alarms"]
        self.assertEqual([(a["id"], a["level"]) for a in rows], [("RR2", "info"), ("RR2", "info")])
        self.assertIn("RR2 receipt fake-a: read flat on", rows[0]["text"])
        self.assertIn("RR2 receipt fake-b: read wrong_way on", rows[1]["text"])
        self.assertIn("(listed, never reverted)", rows[1]["text"])
        self.now += 8 * 86400
        self.assertEqual(self.ids(), [])

    def contamination(self, **routes) -> None:
        write_json(self.root / "contamination.json", {"version": "contam-1", "routes": routes, "history": self.history})

    history: list = []

    def cells(self, **named) -> dict:
        out: dict = {}
        for name, (readable, recalled) in named.items():
            stratum, era = name.split("__")
            out.setdefault(stratum, {})[era.replace("_", "-")] = {"n": 96, "acc": 0.61, "p_perm": 0.004,
                                                                 "readable": readable, "recalled": recalled}
        return out

    def test_cp1_a_route_unprobed_for_forty_five_days(self):
        self.history = []
        self.contamination(**{"sail:fake_a": {"at": S.iso(self.now - 46 * 86400), "probes": 2, "idle": 0, "cells": {}},
                              "sail:fake_b": {"at": S.iso(self.now - 44 * 86400), "probes": 2, "idle": 0, "cells": {}},
                              "sail:fake_c": {"attempted_at": S.iso(self.now - 50 * 86400), "idle": 1}})
        rows = self.section()["alarms"]
        self.assertEqual([(a["id"], a["level"]) for a in rows], [("CP1", "info"), ("CP1", "info")])
        self.assertIn(f"CP1 route sail:fake_a unprobed: no completed probe since {S.iso(self.now - 46 * 86400)[:10]}",
                      rows[0]["text"])
        self.assertIn("CP1 route sail:fake_c unprobed", rows[1]["text"])

    def test_cp1_a_readable_recent_cell_newly_recalled(self):
        at = S.iso(self.now - 86400)
        cells = self.cells(S1__2025=(True, True), S2__2026H1=(True, True), S1__2016_24=(True, True), S3__2025=(True, False))
        before = self.cells(S1__2025=(True, False), S2__2026H1=(True, True))
        self.history = [{"route": "sail:fake_a", "at": S.iso(self.now - 30 * 86400), "cells": before},
                        {"route": "sail:fake_a", "at": at, "cells": cells}]
        self.contamination(**{"sail:fake_a": {"at": at, "probes": 2, "idle": 0, "cells": cells}})
        out = self.section()
        (alarm,) = out["alarms"]
        self.assertIn("CP1 route sail:fake_a recall: 1 readable cells newly recalled (S1/2025)", alarm["text"])
        route = out["contamination"]["routes"]["sail:fake_a"]
        self.assertEqual((route["cells"], route["readable"], route["recalled"], route["probes"]),
                         (4, 4, ["S1/2016-24", "S1/2025", "S2/2026H1"], 2))
        # A first probe has nothing before it: what it recalls in the recent eras is new.
        self.history = []
        self.contamination(**{"sail:fake_a": {"at": at, "probes": 1, "idle": 0, "cells": cells}})
        self.assertIn("2 readable cells newly recalled (S1/2025, S2/2026H1)", self.section()["alarms"][0]["text"])

    def test_cp2_a_route_whose_last_three_attempts_added_no_cell(self):
        self.history = []
        self.contamination(**{"sail:fake_a": {"attempted_at": S.iso(self.now), "idle": 3, "partial": {"probe_n": 1}},
                              "sail:fake_b": {"attempted_at": S.iso(self.now), "idle": 2}})
        out = self.section()
        (alarm,) = out["alarms"]
        self.assertEqual((alarm["id"], alarm["level"]), ("CP2", "warning"))
        self.assertIn("CP2 route sail:fake_a: its last 3 probe attempts added no cell", alarm["text"])
        self.assertTrue(out["contamination"]["routes"]["sail:fake_a"]["partial"])

    def test_mm1_a_memory_alert_in_the_last_day(self):
        store = self.swarm()
        self.equity_family(store, "eq-a")
        self.now -= 30 * 3600
        store.event("swarm.status", "eq-a", {"action": "elane_memory", "alert": True, "text": "old"})
        self.now += 30 * 3600
        store.event("swarm.status", "eq-a", {"action": "elane_memory", "alert": False, "text": "not an alert"})
        store.event("swarm.status", "eq-a", {"action": "other", "alert": True, "text": "names elane_memory in passing"})
        write_json(self.root / R.FILE, {"at": S.iso(self.now - 3600), "mode": "record", "alarms": []})
        self.assertEqual(self.ids(), [])
        store.event("swarm.status", "eq-a", {"action": "elane_memory", "alert": True, "version": 2,
                                             "text": "the memory ingest failed (RunFailed): nothing recorded for v2"})
        (alarm,) = self.section()["alarms"]
        self.assertEqual((alarm["id"], alarm["level"]), ("MM1", "warning"))
        self.assertIn("MM1: 1 memory alerts (swarm.status elane_memory) since", alarm["text"])

    def test_new_is_told_by_the_alarm_and_its_subject(self):
        self.history = []
        self.contamination(**{"sail:fake_a": {"attempted_at": S.iso(self.now), "idle": 3}})
        first = self.section()
        self.assertEqual([a["new"] for a in first["alarms"]], [True])
        write_json(self.root / R.FILE, first)
        self.contamination(**{"sail:fake_a": {"attempted_at": S.iso(self.now), "idle": 4},
                              "sail:fake_b": {"attempted_at": S.iso(self.now), "idle": 3}})
        again = self.section()
        self.assertEqual([(a["text"].split(":")[1], a["new"]) for a in again["alarms"]],
                         [("fake_a", False), ("fake_b", True)], "the count moved; the alarm is the same one")


# ============================================================================================== the job
class TheJob(Fixture):
    def ctx(self, settings: dict) -> Context:
        (self.root / "swarm.json").write_text(json.dumps(settings))
        release = self.base / "release"
        release.mkdir(exist_ok=True)
        return Context("forward_report", root=self.root, due_at=self.now, base=self.base, release=release, config={},
                       clock=lambda: self.now)

    def test_with_the_mode_off_it_writes_the_off_file_and_is_skipped(self):
        self.register(first_day=DAYS[0])
        self.now = ny(DAYS[4], 12)
        ctx = self.ctx(OFF)
        out = R.run(ctx)
        self.assertEqual(out["status"], "skipped")
        self.assertEqual(read_json(self.root / R.FILE), {"at": S.iso(self.now), "mode": "off", "alarms": []})
        self.assertEqual((ctx.alerts, self.table("fwd_cey")), ([], []))

    def test_it_writes_the_meters_then_the_report_and_alerts_each_warning(self):
        rng = np.random.default_rng(2)
        for i in range(3):
            self.series(self.register(f"fam-{i}@1"), DAYS[:11], rng.normal(0, 0.01, 11))
        self.night(DAYS[9], stale=2)
        self.night(DAYS[10], stale=2)
        write_json(self.root / "contamination.json", {"version": "contam-1", "history": [], "routes": {
            "sail:fake_a": {"at": S.iso(ny(DAYS[10], 12) - 50 * 86400), "probes": 1, "idle": 0, "cells": {}}}})
        self.now = ny(DAYS[10], 19)
        ctx = self.ctx(RECORD)
        out = R.run(ctx)
        self.assertEqual((out["ok"], out["through"], out["days"], out["cey"], out["alarms"]),
                         (True, DAYS[10], 11, 11, ["FW2", "CP1"]))
        doc = read_json(self.root / R.FILE)
        self.assertEqual(tuple(sorted(doc)), tuple(sorted(R.SECTION_KEYS)))
        self.assertEqual((doc["mode"], doc["through"], doc["cey"]["day"], doc["cey"]["members"]),
                         ("record", DAYS[10], DAYS[10], 3))
        self.assertEqual(stat.S_IMODE(os.stat(self.root / R.FILE).st_mode), 0o600)
        # A warning is a House alert of the job; an info row rides the report only.
        self.assertEqual([a["level"] for a in ctx.alerts], ["warning"])
        self.assertTrue(ctx.alerts[0]["text"].startswith("forward: FW2 stale: programs were left stale two nights"))
        # A second run the same night writes no meter again and tells the same alarm as no longer new.
        again = R.run(ctx)
        self.assertEqual((again["days"], again["cey"]), (0, 0))
        self.assertEqual([a["new"] for a in read_json(self.root / R.FILE)["alarms"]], [False, False])

    def test_the_report_is_written_whatever_the_meters_did(self):
        self.series(self.register(), DAYS[:3], [0.01, -0.01, 0.02])
        self.night(DAYS[1])
        self.night(DAYS[2])
        self.now = ny(DAYS[2], 19)
        ctx = self.ctx(RECORD)
        calls = []

        def torn(db, day):
            calls.append(day)
            if day == DAYS[1]:
                raise ValueError("a p-value is a number in [0, 1]; got 1.0000002")
            return real(db, day)

        real = R._meter_row
        with mock.patch.object(R, "_meter_row", torn):
            out = R.run(ctx)
        self.assertEqual((out["status"], out["days"], out["through"]), ("failed", 1, DAYS[2]))
        self.assertEqual(out["error"], f"the meters of {DAYS[1]} could not be written (ValueError); the report was written "
                                       "without them")
        self.assertEqual(calls, DAYS[:2], "the pass stops at the day that failed")
        self.assertEqual((self.table("fwd_meter")[-1]["day"], self.table("fwd_groups")[-1]["day"]), (DAYS[0], DAYS[0]),
                         "nothing of the failed day is written")
        self.assertEqual([r["day"] for r in self.table("fwd_cey")], DAYS[:1], "no later day is written past the one that failed")
        self.assertEqual(read_json(self.root / R.FILE)["at"], S.iso(self.now))
        # The next run writes the days the failed one did not reach, in order.
        again = R.run(ctx)
        self.assertEqual((again["ok"], again["days"]), (True, 2))
        self.assertEqual([r["day"] for r in self.table("fwd_cey")], DAYS[:3])

    def test_a_forward_store_that_cannot_be_opened_is_a_failed_receipt_and_a_report(self):
        self.now = ny(DAYS[2], 19)
        ctx = self.ctx(RECORD)
        real = forward_db.open_db

        def locked(root, *, readonly=False):
            if not readonly:
                raise sqlite3.OperationalError("database is locked")
            return real(root, readonly=True)

        with mock.patch.object(forward_db, "open_db", locked):
            out = R.run(ctx)
        self.assertEqual((out["status"], out["days"]), ("failed", 0))
        self.assertIn("the meters of the night could not be written (OperationalError)", out["error"])
        self.assertEqual(read_json(self.root / R.FILE)["mode"], "record")

    def test_the_receipt_holds_counts_never_a_figure(self):
        self.series(self.register(), DAYS[:3], [0.0123456, -0.0234567, 0.0345678])
        self.night(DAYS[2])
        self.now = ny(DAYS[2], 19)
        out = R.run(self.ctx(RECORD))
        self.assertEqual(set(out), {"ok", "path", "through", "days", "cey", "meter", "groups", "alarms"})
        self.assertTrue(all(isinstance(out[k], int) for k in ("days", "cey", "meter", "groups")))


# ============================================================================================== T8
class TheReportShowsOnlyWhatItMay(Fixture):
    """SEAL T8. Forward rows reach only forward-report.json (and through it the dlane report's section) and
    `a14_reading`; no per-program forward figure for a pid without a "live" tag; no RC difference before a pair's
    read; no figure of the sealed memory tables (counts only); integers only in `funnel_rows`; nothing E3 writes
    lies under the release directory; every alarm text and every alert of an E3 job holds ids, counts and dates only."""

    #: Figures no report may show: a program's daily return, its checkpoint's p, a hidden year's contribution.
    SECRET_R, SECRET_P, SECRET_E = 0.012345678, 0.000424242, 0.777777

    def everything(self) -> Context:
        """A fixture that fires all thirteen alarms and holds a secret figure in every sealed place."""
        from league.live.state import LiveState
        from league.tests.test_equity_twins import add_tables

        rng = np.random.default_rng(31)
        secret = self.register("secret-program@1", reason="train_pass", lineage="equity:secret-lineage")
        self.series(secret, DAYS[:62], [self.SECRET_R] * 31 + [-self.SECRET_R] * 31)
        self.check(secret, 20, DAYS[20], self.SECRET_P)
        self.check(secret, 60, DAYS[60], self.SECRET_P)
        live = self.register("seated-program@2", reason="live", lineage="equity:seated")
        self.tag(live, "live", "seated-program@2:r")
        peers = [self.register(f"peer-{i}@1", reason="train_pass" if i < 6 else "train_fail") for i in range(12)]
        for pid in (live, *peers):
            self.series(pid, DAYS[:62], rng.normal(0, 0.01, 62))
        for n in range(5):
            self.series(self.control("index", n), DAYS[:62], rng.normal(0, 0.01, 62), r0=0.0001)
        for day in DAYS[:62]:
            self.night(day, stale=3, programs=14, sessions=14)
        last = DAYS[61]
        self.event("data_failed", pid=secret, day=DAYS[60])
        self.event("data_failed", pid=secret, day=last)
        self.event("restated", pid=secret, day=DAYS[7], at=ny(last, 18, 36))
        self.event("identity_moved", at=ny(last, 18, 37))
        FakeA.chain = {"ok": False, "rows": 19, "first_bad": 3}
        with self.db:
            for lid in range(1, 7):
                self.db.execute("INSERT INTO fwd_lotgap(lid, instance, pid, symbol, opened_day, exit_day, entry_at, exit_at, "
                                "model_bp, twin_gap_bp, at) VALUES(?, 'seated-program@2:r', ?, 'SPY', ?, ?, 'open', 'open', "
                                "1.0, -21.5, 1.0)", (lid, live, DAYS[0], DAYS[1]))
            for i in range(22):
                self.db.execute("INSERT INTO fwd_twins(instance, day, pid, live_keys, shadow_keys, agree, at, cause) VALUES("
                                "'seated-program@2:r', ?, ?, '[]', '[]', ?, 1.0, ?)",
                                (DAYS[i], live, 1 if i < 15 else 0, None if i < 15 else "bars"))
        self.now = ny(DAYS[62], 9, 5)                                 # the next morning: no row for DAYS[62] is owed yet
        # The swarm store: equity births (FW5), a memory alert (MM1) and the sealed tables with a secret in them.
        store = self.swarm()
        self.equity_family(store, "eq-a")
        store.event("swarm.born", "eq-a", {"lane": "beta"})
        store.event("swarm.status", "eq-a", {"action": "elane_memory", "alert": True, "text": "a birth got no hidden year"})
        store.close()
        db = sqlite3.connect(str(self.root / "swarm.sqlite"))
        db.executescript(elane_memory.SCHEMA)
        db.execute("INSERT INTO mem_seen(family, version, cell, gid, bar_passed, fails, drift_share, seen_sha, at) "
                   "VALUES('secret-program', 1, 'c', 'g0', 1, '[]', ?, 's', ?)", (self.SECRET_E, S.iso(self.now)))
        db.execute("INSERT INTO mem_contrib(family, version, cell, kind, year, symset, k, status, n_days, n_lots, exp_mean, "
                   "e_ann, se_ann, t_x, series_sha, run_sha, at) VALUES('secret-program', 1, 'c', 'own', 2018, 'own', 1.0, "
                   "'ok', 250, 9, 0.5, ?, ?, ?, 's', 'r', ?)", (self.SECRET_E, self.SECRET_E, self.SECRET_E, S.iso(self.now)))
        db.commit()
        db.close()
        # The live book (FW7), the receipts (RR1, RR2) and the probe's file (CP1, CP2).
        book = LiveState(self.root / "live.sqlite")
        self.addCleanup(book.close)
        add_tables(book)
        book.db.execute("INSERT INTO eq_instances(id, family, version, lane, run_sha, code, params, band, max_hold, "
                        "created_at) VALUES('seated-program@2:r', 'seated-program', 2, 'beta', 'r', 'c', '{}', 'probe', 20, "
                        "1.0)")
        book.db.commit()
        book.put("eq_decide", {"day": last, "status": "failed", "at": close(last) + 1800, "why": "the bars"})
        receipts = sqlite3.connect(str(self.root / RR.DB))
        receipts.executescript(RR.SCHEMA)
        for rid, kind, deployed, verdict, at in (("fake-unread", "declared", self.now - 100 * 3600, None, 1.0),
                                                 ("fake-flat", "declared", self.now - 80 * 3600, None, 1.0),
                                                 ("fake-flat", "read", self.now - 80 * 3600, "flat", self.now - 60)):
            receipts.execute("INSERT INTO l3_receipts(id, kind, release, metric, direction, min_delta, window_hours, "
                             "deployed_at, value, verdict, at) VALUES(?, ?, 'E3', 'forward_record.program_sessions', 'up', "
                             "1, 72, ?, 3, ?, ?)", (rid, kind, deployed, verdict, at))
        receipts.commit()
        receipts.close()
        write_json(self.root / "contamination.json", {"version": "contam-1", "history": [], "routes": {
            "sail:fake_a": {"at": S.iso(self.now - 50 * 86400), "probes": 1, "idle": 3, "cells": {}}}})
        (self.root / "swarm.json").write_text(json.dumps(RECORD))
        self.release = self.base / "release"
        (self.release / "docs" / "benchmarks").mkdir(parents=True)
        (self.release / "docs" / "benchmarks" / "release_receipts.json").write_text(json.dumps({"schema": 1, "receipts": []}))
        return Context("forward_report", root=self.root, due_at=self.now, base=self.base, release=self.release, config={},
                       clock=lambda: self.now)

    def cey_under_its_median(self) -> None:
        """FW5's ten days: the last ten `fwd_cey` rows under their 20-day median (rows of this package's own table)."""
        with self.db:
            for i, day in enumerate(DAYS[:62]):
                value = 0.10 if i < 52 else 0.09 - 0.001 * (i - 52)
                self.db.execute("INSERT INTO fwd_cey(day, n_w, members, neff, neff_raw, cey_day, cey_total, at) "
                                "VALUES(?, 60, 14, ?, 30.0, ?, 0.0, 1.0)", (day, value * 252, value))

    def test_every_alarm_of_the_spec_and_every_alert_of_the_job_holds_ids_counts_and_dates_only(self):
        ctx = self.everything()
        self.cey_under_its_median()
        # One more session passes with no forward row at all (FW1); the fingerprint moves and a memory alert is raised
        # inside the last day (FW8, MM1).
        self.now = ny(DAYS[63], 8)
        self.event("identity_moved")
        store = self.swarm()
        store.event("swarm.status", "eq-a", {"action": "elane_memory", "alert": True, "text": "the memory ingest failed"})
        self.now = ny(DAYS[63], 9, 5)
        out = R.run(ctx)
        doc = read_json(self.root / R.FILE)
        fired = sorted({a["id"] for a in doc["alarms"]})
        self.assertEqual(fired, sorted(R.ALARMS), "the fixture fires every alarm of the spec's 12.3")
        self.assertEqual(out["alarms"], [a["id"] for a in doc["alarms"]])
        for alarm in doc["alarms"]:
            self.assertEqual(set(alarm), {"id", "level", "text", "new"})
            self.assertEqual(alarm["level"], R.ALARMS[alarm["id"]])
            self.assertTrue(alarm["text"].startswith(alarm["id"]))
            self.assertTrue(R.text_ok(alarm["text"]), alarm["text"])
            self.assertNotIn("secret", alarm["text"])
        warnings = [a for a in doc["alarms"] if a["level"] == "warning"]
        self.assertEqual([a["text"] for a in ctx.alerts], [f"forward: {a['text']}" for a in warnings])
        self.assertTrue(all(a["level"] == "warning" and R.text_ok(a["text"]) for a in ctx.alerts))
        self.assertTrue(len(ctx.alerts) >= 11)

    def test_the_oracle_itself(self):
        for bad in ("a return of 0.0123", "12.5 bp a side", "up 3%", "lost $40", "a gap of 16 BP", "1,234 rows", ""):
            self.assertFalse(R.text_ok(bad), bad)
        for good in ("FW1: no forward row for 2026-10-12 by 09:00 New York on 2026-10-13 though 3 registered rows",
                     "FW6 instance fam-a@3:r gap: its mean twin gap over 5 priced closes is beyond the A14 bound",
                     "CP1 route sail:glm_asap recall: 2 readable cells newly recalled (S1/2025, S2/2026H1)"):
            self.assertTrue(R.text_ok(good), good)
        self.assertFalse(R.text_ok(None))

    def test_no_alert_an_e3_job_writes_formats_a_figure(self):
        # Every `.alert(...)` call in an E3 ops module, read from its source: no float format, no "bp", no percent
        # or dollar sign in what it writes (a job that is still a stub alerts nothing yet and holds trivially).
        def texts(node: ast.AST) -> list[str]:
            found = []
            for part in ast.walk(node):
                if isinstance(part, ast.Constant) and isinstance(part.value, str):
                    found.append(part.value)
            return found

        seen = 0
        for name in E3_OPS:
            tree = ast.parse((REPO / "league" / "ops" / f"{name}.py").read_text())
            for call in ast.walk(tree):
                if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute) and call.func.attr == "alert"):
                    continue
                seen += 1
                for arg in (*call.args, *(k.value for k in call.keywords)):
                    for spec in (n.format_spec for n in ast.walk(arg) if isinstance(n, ast.FormattedValue) and n.format_spec):
                        self.assertNotRegex("".join(texts(spec)), r"[feEgG%]", f"{name}: an alert formats a figure")
                    for text in texts(arg):
                        self.assertNotRegex(text, r"\bbp\b|%|\$", f"{name}: {text!r}")
        self.assertGreaterEqual(seen, 1, "forward_report alerts its warnings")

    def test_no_figure_of_a_program_without_a_live_tag_and_no_sealed_figure(self):
        ctx = self.everything()
        R.run(ctx)
        doc = read_json(self.root / R.FILE)
        text = json.dumps(doc)
        for secret in ("secret-program", "secret-lineage", "peer-3", str(self.SECRET_R)[:9], str(self.SECRET_P)[:9],
                       str(self.SECRET_E)):
            self.assertNotIn(secret, text)
        self.assertNotIn("min_p", text)
        self.assertNotIn("p_x", text)
        # The one program named is the seated one, with its twins (the Done meter's A14 reads them).
        self.assertEqual([row["instance"] for row in doc["fills"]["by_instance"]], ["seated-program@2:r"])
        self.assertEqual(text.count("seated-program"), text.count("seated-program@2:r"))
        # The memory tables: row counts only.
        self.assertEqual(doc["memory"], {"seen": 1, "contrib": 1, "families": 1, "by_year": {"2018": 1}})

        def numbers(value, path=""):
            if isinstance(value, dict):
                for k, v in value.items():
                    yield from numbers(v, f"{path}.{k}")
            elif isinstance(value, list):
                for v in value:
                    yield from numbers(v, path)
            elif isinstance(value, float):
                yield path, value

        allowed = (".cey.", ".meter.controls_p10", ".meter.q", ".fills.", ".rc.pairs", ".receipts")
        for path, value in numbers(doc):
            self.assertTrue(path.startswith(allowed), f"{path} = {value}: a figure outside the aggregates")

    def test_no_rc_difference_before_a_pairs_read(self):
        self.everything()
        self.meters()
        through = {r["day"] for r in self.table("fwd_groups")}
        self.assertEqual(len(through), 62)
        # 62 forward days, but the seated program is no RC group and one group side is thin on no day: the pair
        # (train_pass, train_fail) has 62 usable sessions and has been read once; the look pairs have none.
        pairs = {(p["a"], p["b"]): p for p in R.rc_pairs(self.db, DAYS[61])}
        self.assertEqual(pairs[("train_pass", "train_fail")]["usable"], 62)
        self.assertEqual([r["n"] for r in pairs[("train_pass", "train_fail")]["reads"]], [60])
        for day in (DAYS[10], DAYS[58]):
            for pair in R.rc_pairs(self.db, day):
                self.assertEqual(pair["reads"], [], f"{pair['a']} against {pair['b']} on {day}")
                self.assertEqual(set(pair), {"a", "b", "usable", "next_read", "reads"})
        self.assertEqual(pairs[("look_pass", "look_fail")], {"a": "look_pass", "b": "look_fail", "usable": 0,
                                                             "next_read": 60, "reads": []})
        # The groups' daily means stay in the store: the report prints their counts.
        section = self.section()
        self.assertTrue(all(type(n) is int for n in section["rc"]["groups"].values()))
        self.assertNotIn("mean_x", json.dumps(section["rc"]))

    def test_integers_only_in_the_funnel(self):
        self.everything()
        out = R.funnel_rows(self.root, self.now - 30 * 86400, self.now + 3600)
        self.assertEqual(tuple(out), R.FUNNEL_KEYS)
        self.assertTrue(all(type(v) is int for v in out.values()), out)
        self.assertEqual((out["oof_seen"], out["oof_rows"], out["controls"]), (1, 1, 5))
        self.assertGreater(out["program_sessions_total"], 0)

    def test_nothing_is_written_under_the_release_directory_and_the_report_is_owner_only(self):
        ctx = self.everything()
        before = sorted((str(p.relative_to(self.release)), p.stat().st_mtime_ns) for p in self.release.rglob("*"))
        R.run(ctx)
        self.assertEqual(sorted((str(p.relative_to(self.release)), p.stat().st_mtime_ns) for p in self.release.rglob("*")),
                         before)
        self.assertEqual(stat.S_IMODE(os.stat(self.root / R.FILE).st_mode), 0o600)
        written = {p.name for p in self.root.iterdir()}
        self.assertTrue({R.FILE, forward_db.DB} <= written)
        self.assertFalse((self.base / R.FILE).exists())

    def test_the_forward_rows_reach_only_the_report_file_and_the_done_meters_reading(self):
        # By source: outside the E3 ops modules, only the dlane report (its `forward_record` section and A14), the
        # funnel (integers) and the stall job (the receipts) may name a module of the forward record.
        allowed = {"dlane_report.py", "funnel.py", "stall.py", *(f"{name}.py" for name in E3_OPS)}
        names = ("forward_report", "forward_twins", "forward_db", "forward_shadow", "forward_register", "forward_audit",
                 "forward_controls", "fill_minutes", "release_receipts", "contam_probe")
        for path in sorted((REPO / "league" / "ops").glob("*.py")):
            if path.name in allowed:
                continue
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    imported = {alias.name for alias in node.names} | {(node.module or "").split(".")[-1]}
                elif isinstance(node, ast.Import):
                    imported = {alias.name.split(".")[-1] for alias in node.names}
                else:
                    continue
                self.assertFalse(imported & set(names), f"{path.name} imports {sorted(imported & set(names))}")


if __name__ == "__main__":
    unittest.main()
