"""POOL1's job, THE RECORD HALF P1 (league/ops/pool_screen.py; the owner's A55, pre-registered in A55a): the clock and
the POOL-route list written once on the first night after the release, the refusal's permanence, the House-set cell
key and the later lineages' holds, merges and assignments, the cell sessions, the looks (a word and a sha at a
non-final look, the series with a final verdict, exactly D_1..k after a failed night), the engine and join rules
(lost, never gained), the demotion, the House's failures, the permit file of ids and words, the operator views, the
job and its seals.

Every store is made here from invented rows and the House's runs are a fake (FAKE: no market data, no real figure,
no POOL1 figure)."""

from __future__ import annotations

import ast
import datetime as dt
import hashlib
import json
import os
import sqlite3
import stat
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from league.equity import schedule
from league.ops import forward_db, forward_report as FR, forward_screen as FS, pool_rule as P, pool_screen as PS
from league.ops import fwd1_rule as F, registry
from league.tests.test_pool_rule import receipt, receipt_doc

REPO = Path(__file__).resolve().parents[2]
UTC = dt.timezone.utc
REL = "20261023T200505Z-pool1"
#: The release that carries the receipt starts Fri Oct 23 2026 at 20:05Z (after the close), before that night's run.
REL_AT = dt.datetime(2026, 10, 23, 20, 5, tzinfo=UTC).timestamp()
SETTINGS = {"elane": {"pool": {"mode": "record", "seats": "off"}, "forward": {"mode": "record"},
                      "fwd1": {"mode": "record", "seats": "off"}}}
SYMBOL = {"index": "SPY", "sectors": "XLK", "defensive": "TLT"}


def nyse(first: str, n: int) -> list[str]:
    out, day = [], dt.date.fromisoformat(first)
    while len(out) < n:
        if schedule.is_session(day):
            out.append(day.isoformat())
        day += dt.timedelta(days=1)
    return out


def at(day: str, hour: int = 23, minute: int = 0) -> float:
    return dt.datetime.fromisoformat(day).replace(hour=hour, minute=minute, tzinfo=UTC).timestamp()


def weekdays(first: str, n: int) -> list[str]:
    out, day = [], dt.date.fromisoformat(first)
    while len(out) < n:
        if day.weekday() < 5:
            out.append(day.isoformat())
        day += dt.timedelta(days=1)
    return out


TRAIN_DAYS = (weekdays("2016-01-06", 300), weekdays("2022-01-05", 260))


def unit_rng(*key) -> np.random.Generator:
    return np.random.default_rng([int(hashlib.sha256("|".join(map(str, key)).encode()).hexdigest()[:8], 16)])


def train_R(sym: str, era: int) -> np.ndarray:
    return unit_rng("R", sym, era).normal(0.0004, 0.01, len(TRAIN_DAYS[era]))


def fwd_R(sym: str, day: str) -> float:
    return float(unit_rng("fR", sym, day).normal(0.0004, 0.01))


class FakeRuns:
    """The House's runs, invented: Train eras whose noise has a common part a cell (`World.train_cell`), the member's
    forward run as the record's own rows (it reproduces every day), the Train market."""

    def __init__(self, world: "World"):
        self.w = world
        self.calls: dict[str, int] = {}

    def _count(self, name: str) -> None:
        self.calls[name] = self.calls.get(name, 0) + 1

    def train_series(self, program):
        self._count("train")
        if self.w.fail_train:
            raise RuntimeError("the child died")
        if program.pid in self.w.refuse_train:
            raise FS.OwnFloorRefused("a Train-era run ended ['error']: its series is partial")
        symbols = list(program.needs.get("symbols") or ["SPY"])
        sym = symbols[0]
        cell = self.w.train_cell.get(program.pid, f"own-{program.pid}")
        own = self.w.train_twin.get(program.pid, program.pid)          # a Train twin: the same idiosyncratic part
        out = []
        for era, days in enumerate(TRAIN_DAYS):
            R = train_R(sym, era)
            noise = 0.7 * unit_rng("c", cell, era).normal(0, 1, len(days)) + 0.7 * unit_rng("e", own, era).normal(
                0, 1, len(days))
            w = np.full(len(days), self.w.train_w.get(program.pid, 0.5))
            r = w * R + 0.002 * noise
            ws = [w.tolist()] + [[0.0] * len(days) for _ in symbols[1:]]   # every exposure in the first symbol
            Rs = [R.tolist()] + [train_R(x, era).tolist() for x in symbols[1:]]
            out.append({"days": list(days), "symbols": symbols, "r": r.tolist(), "r15": (r - 1e-5).tolist(),
                        "w": w.tolist(), "b": R.tolist(), "ws": ws, "R": Rs,
                        "sides": [0.0] * len(days), "k_close": 30 + program.pid % 7, "k_sessions": len(days)})
        return out

    def forward_series(self, program, *, settings=None, fdb=None):
        self._count("forward")
        if self.w.fail_forward:
            raise RuntimeError("the child died")
        engine = forward_db.engine_now(self.w.fdb)
        rows = [dict(r) for r in self.w.fdb.execute("SELECT * FROM fwd_days WHERE pid=? AND engine=? ORDER BY day",
                                                    (program.pid, engine))]
        sym = (program.needs.get("symbols") or ["SPY"])[0]
        return {"symbols": [sym], "r": {r["day"]: r["r"] + self.w.unreproduced.get((program.pid, r["day"]), 0.0)
                                        for r in rows},
                "ws": {r["day"]: [r["w"]] for r in rows}, "R": {r["day"]: [r["b"]] for r in rows},
                "sides": {r["day"]: 0.0 for r in rows}, "entries": {r["day"]: r["entries"] for r in rows},
                "exits": {r["day"]: r["exits"] for r in rows}, "bars": {r["day"]: r["bars"] for r in rows}}

    def market(self):
        self._count("market")
        out = []
        for era, days in enumerate(TRAIN_DAYS):
            out.append({"days": list(days), "spy": train_R("SPY", era).tolist(),
                        "sectors": [train_R(s, era).tolist() for s in P.SECTOR_ETFS],
                        "tlt": train_R("TLT", era).tolist(), "gld": train_R("GLD", era).tolist()})
        return out

    def control_train(self, spec):
        self._count("control_train")
        sym = spec["symbols"][0]
        out = []
        for era, days in enumerate(TRAIN_DAYS):
            R = train_R(sym, era)
            w = (unit_rng("cw", spec["n"], era).random(len(days)) < 0.5) * 0.25
            out.append({"days": list(days), "symbols": [sym], "r0": (w * R).tolist(), "ws": [w.tolist()],
                        "R": [R.tolist()]})
        return out

    def control_forward(self, program, *, settings=None, fdb=None):
        self._count("control_forward")
        spec = json.loads(program.code)
        sym = spec["symbols"][0]
        days = [str(r[0]) for r in self.w.fdb.execute("SELECT day FROM fwd_days WHERE pid=?", (program.pid,))]
        return {"symbols": [sym], "ws": {d: [0.25] for d in days}, "R": {d: [fwd_R(sym, d)] for d in days}}

    def close(self):
        pass


class World(unittest.TestCase):
    """A state root: a forward record holding the receipt's founders as registry rows, FWD1-R's store, a deploys
    record that names the release carrying the receipt, and invented forward days."""

    RECEIPT: dict = {}

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "state"
        self.base = Path(self.tmp.name) / "base"
        self.root.mkdir()
        self.base.mkdir()
        (self.base / "deploys.jsonl").write_text(json.dumps(
            {"stage": "verdict", "verdict": "promoted", "release": REL,
             "at": dt.datetime.fromtimestamp(REL_AT, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")}) + "\n")
        self.fdb = forward_db.open_db(self.root)
        self.engine, _ = forward_db.engine_id(self.fdb, "equity-engine-1+aaaaaaaaaaaa+fwd-1", at=1.0)
        self.fdb.commit()
        self.rec = receipt(**self.RECEIPT)
        self.families: dict[str, dict] = {}
        self.train_cell: dict[int, str] = {}
        self.train_w: dict[int, float] = {}
        self.train_twin: dict[int, int] = {}
        self.refuse_train: set[int] = set()
        self.unreproduced: dict[tuple[int, str], float] = {}
        self.fail_forward = False
        self.fail_train = False
        self.alpha: dict[int, float] = {}
        for lineage, f in sorted(self.rec.founders.items()):
            self.register(lineage, f.pid, group=f.group or "index", reason="train_pass", cell=f.cell)
        self.sdb = FS.open_store(self.root)
        for lineage, f in sorted(self.rec.founders.items()):
            if f.cell and f.cell.endswith("/sectors"):
                self.fwd1_row(lineage, f.pid)
            else:
                self.fwd1_row(lineage, f.pid, judged=0, case=None,
                              why=FS.NOT_JUDGED["sealed"])
        self.runs = FakeRuns(self)

    def tearDown(self):
        self.fdb.close()
        self.sdb.close()
        self.tmp.cleanup()

    # ------------------------------------------------------------------------------------------------ the record
    def register(self, lineage: str, pid: int, *, group: str = "index", reason: str = "train_pass",
                 first_day: str = "2026-10-13", created_at: float | None = None, cell: str | None = None,
                 ugroup: str | None = None, code: str | None = None, sha: str | None = None,
                 symbols: list[str] | None = None) -> int:
        fid = lineage.split(":", 1)[1]
        sym = symbols or [SYMBOL[group]]
        code = code if code is not None else f"PARAMS = {{}}\n# {pid}\n"
        self.fdb.execute(
            "INSERT INTO fwd_registry(pid, key, family, version, lane, reason, ugroup, lineage, code, params, needs, "
            "program_sha, run_sha, author, created_at, evidence, first_close, first_day, registered_at, route, alpha_f, "
            "prev_hash, row_hash) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (pid, f"{fid}@{pid}", fid, 1, "equity", reason, ugroup or group, lineage, code, "{}",
             json.dumps({"symbols": sym, "history": 1}), sha or hashlib.sha256(code.encode()).hexdigest(),
             f"{pid:064d}", "", created_at if created_at is not None else at("2026-10-09", 15), "registry",
             "2026-10-12", first_day, 1.0, "S2", "0.03", "0" * 64, f"{pid:063d}h"))
        self.fdb.commit()
        self.families[fid] = {"id": fid, "structure": "etf", "spec": {"lane": "equity", "agenda": "trend",
                                                                        "symbols": sym}, "state": {}, "band": "gym"}
        if cell is not None:
            self.train_cell[pid] = cell
        return pid

    def fwd1_row(self, lineage: str, pid: int, *, typ: str = "ETF", case: str | None = "N", judged: int = 1,
                 why: str | None = None, cell: str = "equity / trend / sectors"):
        with self.sdb:
            self.sdb.execute("INSERT INTO fwd1_lineages(lineage, type, rep, family, version, run_sha, row_hash, case_, "
                             "judged, why, start, cell, receipt, versions, at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                             (lineage, typ, pid, lineage.split(":", 1)[1], 1, f"{pid:064d}", f"{pid:063d}h", case,
                              judged, why, "2026-10-16", cell, "c" * 64, 1, 1.0))

    def fwd1_check(self, lineage: str, pid: int, k: int, *, when: float = 2.0, passed: int = 0):
        with self.sdb:
            self.sdb.execute("INSERT INTO fwd1_checks(lineage, k, pid, engine, day, t, s, s15, g_bp, ll, count, draws, "
                             "c_used, passed, why, at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                             (lineage, k, pid, self.engine, "2026-10-20", 0.1, 0.0, 0.0, 2.0, 0, None, None, None, passed,
                              None, when))

    def fwd1_verdict(self, lineage: str, pid: int, verdict: str):
        with self.sdb:
            self.sdb.execute("INSERT INTO fwd1_verdicts(lineage, pid, verdict, k, day, c_used, why, beside, words, at) "
                             "VALUES (?,?,?,?,?,?,?,?,?,?)", (lineage, pid, verdict, 5, "2026-10-20", 2.61, "x", None,
                                                              None, 3.0))

    def days(self, pid: int, names, *, alpha: float | None = None, skip=(), status=None, engine=None):
        a = self.alpha.get(pid, 0.0) if alpha is None else alpha
        rng = unit_rng("noise", pid)
        for day in names:
            noise = float(rng.normal(0, 0.002))
            if day in skip:
                continue
            b = fwd_R(SYMBOL["sectors"] if self.is_sector(pid) else "SPY", day)
            r = 0.5 * b + a + noise
            self.fdb.execute("INSERT OR IGNORE INTO fwd_days(pid, day, engine, r, w, b, r15, r0, entries, exits, status, "
                             "at, bars) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                             (pid, day, engine or self.engine, r, 0.5, b, r - 1e-5, None, 0, 0,
                              (status or {}).get(day, "ok"), 1.0, "b" * 16))
        self.fdb.commit()

    def is_sector(self, pid: int) -> bool:
        row = self.fdb.execute("SELECT needs FROM fwd_registry WHERE pid=?", (pid,)).fetchone()
        return "XL" in str(row[0])

    def advance(self, day: str, *, finished: float | None = None):
        self.fdb.execute("INSERT INTO fwd_runs(job, through, engine, started, finished, seconds, programs, sessions, "
                         "errors, stale, budget_hit, head) VALUES ('forward_shadow', ?, ?, ?, ?, 0.0, 1, 1, 0, 0, 0, NULL)",
                         (day, self.engine, finished or at(day), finished or at(day)))
        self.fdb.commit()

    def nights(self, names):
        for day in names:
            self.advance(day)

    # ------------------------------------------------------------------------------------------------ the pool
    def store(self) -> sqlite3.Connection:
        return PS.open_store(self.root)

    def judge(self, now: float, *, receipt_=None, budget: float = 1e9):
        """One night of the pool as `pool_screen.night` runs it (the night, the permit file, the report), without its
        once-a-record-night guard (a test reads several nights of one record)."""
        store = self.store()
        try:
            j = PS.Night(self.root, store, self.fdb, receipt=receipt_ or self.rec, runs=self.runs, families=self.families,
                         swarm=None, settings=SETTINGS, budget=budget, clock=lambda: now, base=self.base, release=REL)
            tally = j.run(now)
            PS.write_permits(self.root, store, receipt=receipt_ or self.rec, at=now, fdb=self.fdb)
            (self.root / PS.REPORT).write_text(json.dumps(PS.report(store, receipt=receipt_ or self.rec)))
            return tally, j
        finally:
            store.close()

    def rows(self, table: str, where: str = "", args=()) -> list[dict]:
        db = self.store()
        try:
            return [dict(r) for r in db.execute(f"SELECT * FROM {table} {where}", args)]
        finally:
            db.close()

    def founders(self, cell: str) -> list[tuple[str, int]]:
        return [(lin, self.rec.founders[lin].pid) for lin in self.rec.units[cell].founders]

    def first_night(self):
        """The record's nights before the release (through Thu Oct 22) and its first night after it (Fri Oct 23)."""
        self.advance("2026-10-22")
        self.advance("2026-10-23", finished=at("2026-10-23", 23))
        return self.judge(at("2026-10-23", 23, 30))

    def permits(self) -> dict:
        return json.loads((self.root / PS.PERMITS).read_text())


SECTORS = "trend_momentum/sectors"
INDEX = "trend_momentum/index"
REVERSAL = "reversal_liquidity/index"
CLOCK = "2026-10-26"


# ----------------------------------------------------------------------------------------------- store and settings
class TheStoreAndSettings(World):
    def test_settings(self):
        self.assertEqual(PS.cfg({}), {"mode": "off", "seats": "off", "cpu_seconds_night": 600})
        self.assertEqual(PS.cfg({"elane": {"pool": {"mode": "record", "seats": "on", "cpu_seconds_night": 5000}}}),
                         {"mode": "record", "seats": "on", "cpu_seconds_night": 1200})
        self.assertEqual(PS.cfg({"elane": {"pool": {"mode": "live", "cpu_seconds_night": 1.5}}})["mode"], "off")
        policy = json.loads((REPO / "league" / "swarm" / "policy.json").read_text())
        self.assertEqual(PS.cfg(policy)["mode"], "record")
        self.assertEqual(PS.cfg(policy)["seats"], "off")

    def test_the_store_is_0600_and_append_only_by_trigger(self):
        db = self.store()
        try:
            self.assertEqual(stat.S_IMODE(os.stat(self.root / PS.DB).st_mode), 0o600)
            with db:
                db.execute("INSERT INTO pool_routes(lineage, cell, cluster, night, why, at) VALUES ('L', 'c', 'k', 'n', "
                           "'w', 1.0)")
                db.execute("INSERT INTO pool_holds(lineage, night, why, at) VALUES ('H', 'n', 'w', 1.0)")
            for sql in ("UPDATE pool_routes SET why='x'", "DELETE FROM pool_routes",
                        "INSERT OR REPLACE INTO pool_routes(lineage, cell, cluster, night, why, at) VALUES "
                        "('L', 'c2', 'k', 'n', 'w', 2.0)", "DELETE FROM pool_holds", "UPDATE pool_holds SET why='y'"):
                with self.subTest(sql=sql), self.assertRaises(sqlite3.DatabaseError):
                    with db:
                        db.execute(sql)
            self.assertEqual([dict(r)["cell"] for r in db.execute("SELECT cell FROM pool_routes")], ["c"])
            for table in PS.TABLES:
                names = {str(r[0]) for r in db.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND "
                                                       "tbl_name=?", (table,))}
                self.assertEqual(names, {f"{table}_no_update", f"{table}_no_delete"}, table)
            with db:
                self.assertTrue(PS.event(db, "held", at=1.0, lineage="L", once="held"))
                self.assertFalse(PS.event(db, "held", at=2.0, lineage="L", once="held"))
            with self.assertRaises(ValueError):
                PS.event(db, "not_a_kind", at=1.0)
        finally:
            db.close()


# ------------------------------------------------------------------------------------------------------- the clock
class TheClock(World):
    def test_no_clock_before_a_record_night_after_the_release(self):
        self.advance("2026-10-22")
        tally, _ = self.judge(at("2026-10-23", 21))           # the release ran, no record night yet
        self.assertEqual(tally.get("clock_wait"), 1)
        for table in ("pool_pins", "pool_units", "pool_routes", "pool_members"):
            self.assertEqual(self.rows(table), [], table)

    def test_the_first_night_writes_the_units_the_founders_and_the_route_list_once(self):
        self.first_night()
        pins = self.rows("pool_pins")
        self.assertEqual(len(pins), 1)
        self.assertEqual((pins[0]["night"], pins[0]["clock"], pins[0]["evidence"]), ("2026-10-23", CLOCK, "deploys"))
        self.assertEqual({u["cell"] for u in self.rows("pool_units")}, set(self.rec.units))
        self.assertEqual({u["cell"]: json.loads(u["stage1"]) for u in self.rows("pool_units")}[SECTORS],
                         {"refuted": False, "z": [0.5, 0.2]})
        routes = {r["lineage"]: r for r in self.rows("pool_routes")}
        self.assertEqual(set(routes), {lin for lin, _ in self.founders(SECTORS)})       # FWD1's case N sector lineages
        self.assertTrue(all(r["cell"] == SECTORS and r["cluster"] == "trend_momentum" for r in routes.values()))
        members = {m["lineage"]: m for m in self.rows("pool_members")}
        self.assertEqual({m["route"] for lin, m in members.items() if INDEX in str(m["cell"])}, {"sealed"})
        self.assertEqual(members["equity:out-0"]["route"], "out")
        again = self.judge(at("2026-10-26", 23, 30))
        self.assertEqual(len(self.rows("pool_pins")), 1)
        self.assertEqual(set(r["lineage"] for r in self.rows("pool_routes")), set(routes))
        del again

    def test_a_weekend_release_starts_the_clock_a_session_later(self):
        (self.base / "deploys.jsonl").write_text(json.dumps(
            {"stage": "verdict", "verdict": "promoted", "release": REL, "at": "2026-10-24T15:00:00Z"}) + "\n")
        self.advance("2026-10-22")
        self.advance("2026-10-23", finished=at("2026-10-23", 23))
        self.advance("2026-10-23", finished=at("2026-10-24", 23))        # Saturday's night: the same session
        self.judge(at("2026-10-24", 23, 30))
        self.assertEqual(self.rows("pool_pins"), [])
        self.advance("2026-10-26")
        self.judge(at("2026-10-26", 23, 30))
        self.assertEqual(self.rows("pool_pins")[0]["clock"], "2026-10-27")

    def test_an_unreadable_fwd1_store_writes_nothing_and_the_next_night_is_the_first(self):
        self.advance("2026-10-22")
        self.advance("2026-10-23", finished=at("2026-10-23", 23))
        with mock.patch.object(PS, "fwd1_facts", lambda root, fdb: None):
            tally, _ = self.judge(at("2026-10-23", 23, 30))
        self.assertEqual(tally.get("house"), 1)
        self.assertEqual(self.rows("pool_pins"), [])
        self.advance("2026-10-26")
        self.judge(at("2026-10-26", 23, 30))
        self.assertEqual(self.rows("pool_pins")[0]["clock"], "2026-10-27")

    def test_a_founder_of_a_cell_below_m_min_stays_on_its_route(self):
        doc = receipt_doc()
        for i in range(2):
            doc["founders"][f"equity:rv-sec-{i}"] = {"pid": 950 + i, "class": "relative_value", "group": "sectors",
                                                     "cell": "relative_value/sectors", "why": None, "merged_into": None}
        self.rec = P.parse_receipt(doc, "d" * 64)[0]
        for i in range(2):
            self.register(f"equity:rv-sec-{i}", 950 + i, group="sectors")
            self.fwd1_row(f"equity:rv-sec-{i}", 950 + i)
        self.first_night()
        self.assertNotIn("relative_value/sectors", {u["cell"] for u in self.rows("pool_units")})
        members = {m["lineage"]: m for m in self.rows("pool_members")}
        self.assertEqual((members["equity:rv-sec-0"]["route"], members["equity:rv-sec-0"]["cell"]), ("fwd1", None))
        self.assertNotIn("equity:rv-sec-0", self.permits()["routes"])

    def test_the_route_rule_at_the_clock(self):
        (pass_lin, pass_pid), (fail_lin, fail_pid) = self.founders(SECTORS)[:2]
        self.fwd1_check(pass_lin, pass_pid, 5, passed=1)
        self.fwd1_verdict(pass_lin, pass_pid, "pass")
        self.fwd1_verdict(fail_lin, fail_pid, "fail")
        self.first_night()
        routes = {r["lineage"] for r in self.rows("pool_routes")}
        self.assertNotIn(pass_lin, routes)                         # an FWD1-R pass before the clock: not on the route
        self.assertIn(fail_lin, routes)                            # an FWD1 fail does not bar the POOL route (A33(5))
        member = {m["lineage"]: m for m in self.rows("pool_members")}[pass_lin]
        self.assertEqual(member["route"], "fwd1")

    def test_u_at_the_clock_reads_the_checkpoints_read_before_it(self):
        doc = receipt_doc()
        doc["clusters"]["trend_momentum"]["u"] = {str(k): [0.001 * k, 0.001 * k + 0.01] for k in P.U_COUNTS}
        self.rec = P.parse_receipt(doc, "d" * 64)[0]
        lin, pid = self.founders(SECTORS)[0]
        self.fwd1_check(lin, pid, 5)
        self.fwd1_check(lin, pid, 10)
        self.first_night()
        unit = {u["cell"]: u for u in self.rows("pool_units")}[SECTORS]
        self.assertEqual(unit["fwd1_count"], 10)
        self.assertAlmostEqual(unit["u_point"], 0.010)
        self.assertAlmostEqual(unit["cap"], 0.11)
        self.assertAlmostEqual(unit["wall"], 0.13)


class AReportOnlyCluster(World):
    RECEIPT = {"u": {"trend_momentum": (0.12, 0.2)}}

    def test_its_members_stay_on_fwd1_and_it_seats_nothing(self):
        self.first_night()
        self.assertEqual(self.rows("pool_routes"), [])
        units = {u["cell"]: u for u in self.rows("pool_units")}
        self.assertTrue(units[SECTORS]["report_only"])
        self.assertEqual((units[SECTORS]["cap"], units[SECTORS]["wall"]), (0.12, 0.15))
        self.assertEqual(self.permits()["units"][SECTORS]["word"], P.REPORT_ONLY)
        self.assertEqual({m["route"] for m in self.rows("pool_members") if m["cell"] == SECTORS}, {"fwd1"})


class ARefutedUnitAndAMergedFounder(World):
    def setUp(self):
        doc = receipt_doc()
        doc["units"][SECTORS]["stage1"] = {"refuted": True, "z": [-1.2, 0.1]}
        doc["founders"]["equity:copy-0"] = {"pid": 900, "class": "trend_momentum", "group": "sectors", "cell": SECTORS,
                                            "why": None, "merged_into": "equity:trend_momentum-sectors-0"}
        type(self).RECEIPT = {}
        super().setUp()
        self.rec = P.parse_receipt(doc, "d" * 64)[0]
        self.register("equity:copy-0", 900, group="sectors")
        self.fwd1_row("equity:copy-0", 900)

    def test_a_refuted_unit_is_final_and_its_founders_stay_on_fwd1(self):
        self.first_night()
        self.assertEqual({v["cell"]: v["word"] for v in self.rows("pool_verdicts")}, {SECTORS: "REFUTED"})
        self.assertEqual(self.rows("pool_routes"), [])
        self.assertEqual(self.permits()["units"][SECTORS]["word"], "REFUTED")


class AMergedFounder(World):
    def setUp(self):
        super().setUp()
        doc = receipt_doc()
        doc["founders"]["equity:copy-0"] = {"pid": 900, "class": "trend_momentum", "group": "sectors", "cell": SECTORS,
                                            "why": None, "merged_into": "equity:trend_momentum-sectors-0"}
        self.rec = P.parse_receipt(doc, "d" * 64)[0]
        self.register("equity:copy-0", 900, group="sectors")
        self.fwd1_row("equity:copy-0", 900)

    def test_a_merged_copy_follows_its_members_route_and_is_no_member(self):
        self.first_night()
        routes = {r["lineage"]: r for r in self.rows("pool_routes")}
        self.assertIn("equity:copy-0", routes)
        member = {m["lineage"]: m for m in self.rows("pool_members")}["equity:copy-0"]
        self.assertEqual((member["route"], member["merged_into"]), ("merged", "equity:trend_momentum-sectors-0"))
        store = self.store()
        try:
            cell = PS.Night(self.root, store, self.fdb, receipt=self.rec, runs=self.runs,
                            families=self.families).cell_members(SECTORS)
        finally:
            store.close()
        self.assertNotIn(900, [m["pid"] for m in cell])


# ----------------------------------------------------------------------------------------------- the refusal stays
class TheRefusalIsNeverLifted(World):
    def test_the_route_list_survives_every_final_word_mode_off_and_a_rollback(self):
        self.first_night()
        routed = set(self.permits()["routes"])
        self.assertTrue(routed)
        db = self.store()
        with db:                                                   # a pooled FAIL (and a DEMOTED, a VOID) is final
            db.execute("INSERT INTO pool_verdicts(cell, word, why, at) VALUES (?,?,?,?)", (SECTORS, "FAIL", "x", 9.0))
        db.close()
        self.judge(at("2026-10-26", 23, 30))
        store = self.store()
        try:
            PS.write_permits(self.root, store, receipt=self.rec, at=9.0, fdb=self.fdb)
        finally:
            store.close()
        self.assertEqual(set(self.permits()["routes"]), routed)
        self.assertEqual(self.permits()["units"][SECTORS]["word"], "FAIL")
        # mode off: the job stops, the file stays
        ctx = types.SimpleNamespace(root=self.root, config={}, now=lambda: at("2026-10-27", 23, 30), alert=lambda *a: None)
        with mock.patch("league.swarm.settings.load", lambda root, config=None: {"elane": {"pool": {"mode": "off"}}}):
            self.assertEqual(PS.run(ctx)["status"], "skipped")
        self.assertEqual(set(self.permits()["routes"]), routed)
        # a rollback of the pin (no receipt): the file is written again from the store, every entry kept
        PS.keep_permits(self.root, None, "no POOL1 receipt is pinned", at("2026-10-28", 23))
        doc = self.permits()
        self.assertEqual(set(doc["routes"]), routed)
        self.assertEqual(doc["receipt"], self.rec.sha256)

    def test_no_code_deletes_the_permit_file(self):
        tree = ast.parse((REPO / "league" / "ops" / "pool_screen.py").read_text())
        calls = {n.func.attr for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
        self.assertFalse(calls & {"unlink", "remove", "rmtree", "rename", "replace"})


# ------------------------------------------------------------------------------------------- the later lineages
class TheLaterLineages(World):
    def later(self, lineage: str, pid: int, *, group: str = "sectors", cell: str | None = SECTORS, fwd1: bool = True,
              created: str = "2026-10-21", **kw):
        self.register(lineage, pid, group=group, created_at=at(created, 15), first_day="2026-10-22", cell=cell, **kw)
        if fwd1:
            self.fwd1_row(lineage, pid)

    def test_a_lineage_fwd1_judges_as_case_n_is_held_until_the_house_assigns_it(self):
        self.later("equity:late-1", 501)
        self.later("equity:late-2", 502, cell="independent")
        self.fail_train = True                                        # tonight the House cannot read Train series
        self.first_night()
        self.assertEqual(set(self.permits()["holds"]), {"equity:late-1", "equity:late-2"})
        self.fail_train = False
        self.advance("2026-10-26")
        self.judge(at("2026-10-26", 23, 30))
        doc = self.permits()
        self.assertEqual(doc["holds"], [])
        self.assertIn("equity:late-1", doc["routes"])                 # assigned to the pending sector cell
        self.assertNotIn("equity:late-2", doc["routes"])              # under rho_assign: a new cell, released
        members = {m["lineage"]: m for m in self.rows("pool_members")}
        self.assertEqual((members["equity:late-1"]["cell"], members["equity:late-1"]["assigned"]), (SECTORS, 1))
        self.assertEqual(members["equity:late-2"]["route"], "new_cell")
        self.assertGreater(json.loads(members["equity:late-1"]["corr"])[SECTORS], self.rec.rho_assign)

    def test_an_fwd1_pass_while_held_never_seats_it_and_it_joins_the_pool_route(self):
        """A held lineage takes no FWD1-R seat; a pass FWD1 reads while it is held was never a seatable ticket, so on
        its assignment into a pending unit it is on the POOL route like any other (section 7.2), never released."""
        self.later("equity:late-7", 507)
        self.fail_train = True
        self.first_night()
        self.assertEqual(self.permits()["holds"], ["equity:late-7"])
        self.fwd1_check("equity:late-7", 507, 5, when=at("2026-10-26", 22), passed=1)
        self.fwd1_verdict("equity:late-7", 507, "pass")
        self.fail_train = False
        self.advance("2026-10-26")
        self.judge(at("2026-10-26", 23, 30))
        members = {m["lineage"]: m for m in self.rows("pool_members")}
        self.assertEqual(members["equity:late-7"]["route"], "pool")
        self.assertIn("equity:late-7", self.permits()["routes"])
        self.assertEqual(self.rows("pool_releases", "WHERE lineage='equity:late-7'"), [])

    def test_what_is_out_is_decided_at_the_first_reading_and_never_held(self):
        self.later("equity:panel-1", 601, ugroup="panel:sp500")
        self.later("equity:stock-1", 602, symbols=["XLK", "AAPL"])
        self.later("equity:event-1", 603, code="def decide(ctx):\n    return ctx.events_next\n")
        self.register("equity:failonly-1", 604, group="sectors", reason="train_fail", created_at=at("2026-10-21", 15))
        self.fwd1_row("equity:failonly-1", 604)
        self.first_night()
        members = {m["lineage"]: m for m in self.rows("pool_members")}
        self.assertIn("panel", members["equity:panel-1"]["why"])
        self.assertIn("stocks", members["equity:stock-1"]["why"])
        self.assertIn("event reader", members["equity:event-1"]["why"])
        self.assertNotIn("equity:failonly-1", members)                 # Train-fail only: no member, no reading
        self.assertEqual(self.permits()["holds"], [])

    def test_a_copy_by_program_sha_follows_its_members_route(self):
        lin, pid = self.founders(SECTORS)[0]
        sha = self.fdb.execute("SELECT program_sha FROM fwd_registry WHERE pid=?", (pid,)).fetchone()[0]
        self.later("equity:copy-9", 701, sha=sha, cell="unrelated")
        self.first_night()
        members = {m["lineage"]: m for m in self.rows("pool_members")}
        self.assertEqual((members["equity:copy-9"]["route"], members["equity:copy-9"]["merged_into"]), ("merged", lin))
        self.assertIn("equity:copy-9", self.permits()["routes"])

    def test_one_assigned_to_a_pending_unit_is_on_the_route_at_its_first_passing_pid(self):
        self.register("equity:late-3", 509, group="sectors", reason="train_fail", created_at=at("2026-10-21", 14),
                      first_day="2026-10-22", cell=SECTORS)
        self.register("equity:late-3", 511, group="sectors", reason="train_pass", created_at=at("2026-10-21", 15),
                      first_day="2026-10-22", cell=SECTORS)
        self.register("equity:late-3", 512, group="sectors", reason="seed", created_at=at("2026-10-21", 16),
                      first_day="2026-10-22", cell=SECTORS)
        self.fwd1_row("equity:late-3", 511)
        self.first_night()
        members = {m["lineage"]: m for m in self.rows("pool_members")}
        self.assertEqual(members["equity:late-3"]["pid"], 511)            # the lowest passing pid, never the failed v1
        self.assertIn("equity:late-3", self.permits()["routes"])

    def test_a_copy_by_train_correlation_is_merged_into_the_earlier_member(self):
        lin, pid = self.founders(SECTORS)[1]
        self.later("equity:twin-1", 702)
        self.train_twin[702] = pid
        self.first_night()
        members = {m["lineage"]: m for m in self.rows("pool_members")}
        self.assertEqual((members["equity:twin-1"]["route"], members["equity:twin-1"]["merged_into"]), ("merged", lin))
        self.assertIn("equity:twin-1", self.permits()["routes"])          # its member is on the POOL route

    def test_the_house_group_and_the_declared_card(self):
        """The House reads the group from Train exposure (a mixed NEEDS label "index+sectors" held in SPY is an index
        lineage) and the class from the family's card, its own or its fork parent's (`cards.card_of`)."""
        self.later("equity:mixed-1", 801, group="index", symbols=["SPY", "XLK"], ugroup="index+sectors", cell=INDEX)
        self.later("equity:beta-1", 802, cell=None)
        self.later("equity:cal-1", 803, cell=None)
        cards = {"mixed-1": {"card": {"mechanism_class": "trend_momentum", "inputs": ["underlying_price"]}, "own": True},
                 "beta-1": {"card": {"mechanism_class": "equity_premium", "inputs": []}, "own": False},
                 "cal-1": {"card": {"mechanism_class": "calendar_flow", "inputs": ["event_calendar"]}, "own": False}}
        from league.swarm import cards as cards_mod

        with mock.patch.object(cards_mod, "card_of", lambda store, fid: cards.get(fid)):
            store = self.store()
            try:
                j = PS.Night(self.root, store, self.fdb, receipt=self.rec, runs=self.runs, families=self.families,
                             swarm=object(), settings=SETTINGS, clock=lambda: at("2026-10-23", 23, 30), base=self.base,
                             release=REL)
                self.advance("2026-10-22")
                self.advance("2026-10-23", finished=at("2026-10-23", 23))
                j.night = PS.record_night(self.fdb)
                j.run(at("2026-10-23", 23, 30))
            finally:
                store.close()
        members = {m["lineage"]: m for m in self.rows("pool_members")}
        params = {r["pid"]: r for r in self.rows("pool_params")}
        self.assertEqual(params[801]["grp"], "index")
        self.assertIn(members["equity:mixed-1"]["cell"], (INDEX, REVERSAL))     # assigned among the index cells
        self.assertEqual(members["equity:mixed-1"]["declared"], "trend_momentum")
        self.assertIn("equity_premium", members["equity:beta-1"]["why"])         # a fork's card: its parent's
        self.assertIn("event reader", members["equity:cal-1"]["why"])

    def test_fwd1_spend_before_its_hold_releases_it_in_p1(self):
        self.later("equity:late-4", 504)
        self.fwd1_check("equity:late-4", 504, 5, when=1.0)            # read before the pool ever held it
        self.first_night()
        members = {m["lineage"]: m for m in self.rows("pool_members")}
        self.assertEqual(members["equity:late-4"]["route"], "fwd1")
        self.assertNotIn("equity:late-4", self.permits()["routes"])
        self.assertEqual(self.permits()["holds"], [])

    def test_own_runs_that_give_no_train_series_are_out(self):
        self.later("equity:late-5", 505)
        self.refuse_train.add(505)
        self.first_night()
        members = {m["lineage"]: m for m in self.rows("pool_members")}
        self.assertIn("no Train series", members["equity:late-5"]["why"])
        self.assertEqual(self.permits()["holds"], [])


class ALaterLineageAssignedToAFinalUnit(World):
    def test_stays_on_fwd1(self):
        self.first_night()
        db = self.store()
        with db:
            db.execute("INSERT INTO pool_verdicts(cell, word, why, at) VALUES (?,?,?,?)", (SECTORS, "FAIL", "x", 9.0))
        db.close()
        self.register("equity:late-6", 506, group="sectors", created_at=at("2026-10-26", 15), first_day="2026-10-27",
                      cell=SECTORS)
        self.fwd1_row("equity:late-6", 506)
        self.advance("2026-10-26")
        self.judge(at("2026-10-26", 23, 30))
        members = {m["lineage"]: m for m in self.rows("pool_members")}
        self.assertEqual(members["equity:late-6"]["route"], "final_unit")
        self.assertNotIn("equity:late-6", self.permits()["routes"])
        self.assertEqual(self.permits()["holds"], [])


# --------------------------------------------------------------------------------------------- sessions and looks
def no_floor(self, *args, **kwargs):
    return 0                                                         # c_used = c_G (1.70 + 0.03 margin: 1.70)


def holds(self, *args, **kwargs):
    return 0, 999


def fails(self, *args, **kwargs):
    return 999, 999


class Looks(World):
    """The sector cell's four founders with forward days from Oct 13 to the session after its k-th cell session."""

    def run_through(self, n_sessions: int, *, alpha: float = 0.0, skip: dict | None = None, extra=0, placebo=holds,
                    floor=no_floor):
        names = nyse("2026-10-13", 10 + n_sessions + extra + 1)
        for _, pid in self.founders(SECTORS):
            self.days(pid, names, alpha=alpha, skip=(skip or {}).get(pid, ()))
        for _, pid in self.founders(INDEX) + self.founders(REVERSAL):
            self.days(pid, names)
        self.first_night()
        with mock.patch.object(PS.Night, "c_own", floor), mock.patch.object(PS.Night, "placebo", placebo):
            out = []
            for i, day in enumerate([d for d in names if d > "2026-10-23"]):
                self.advance(day)
                out.append(self.judge(at(day, 23, 30)))
            return out, names


class TheSessions(Looks):
    def test_a_session_with_fewer_than_m_min_counted_rows_is_no_cell_session(self):
        names = nyse(CLOCK, 6)
        pids = [pid for _, pid in self.founders(SECTORS)]
        skip = {pids[0]: {names[1]}, pids[1]: {names[1]}}
        status = {names[2]: "disqualified"}
        self.days(pids[0], nyse("2026-10-13", 20), skip=skip[pids[0]])
        self.days(pids[1], nyse("2026-10-13", 20), skip=skip[pids[1]], status=status)
        self.days(pids[2], nyse("2026-10-13", 20), status=status)
        self.days(pids[3], nyse("2026-10-13", 20))
        self.first_night()
        for day in names:
            self.advance(day)
        for i in range(STALL := PS.STALL_NIGHTS):
            self.advance(nyse(names[-1], 2 + i)[-1])
        self.judge(at(nyse(names[-1], 2 + STALL)[-1], 23, 30))
        sess = {r["day"]: r for r in self.rows("pool_sessions", "WHERE cell=?", (SECTORS,))}
        self.assertEqual(sess[names[0]]["session"], 1)
        self.assertEqual((sess[names[1]]["counted"], sess[names[1]]["session"]), (2, 0))   # two rows absent
        self.assertEqual((sess[names[2]]["counted"], sess[names[2]]["session"]), (2, 0))   # two disqualified
        self.assertEqual(sess[names[3]]["session"], 1)

    def test_a_session_waits_for_its_rows_and_its_settling_night(self):
        names = nyse(CLOCK, 4)
        pids = [pid for _, pid in self.founders(SECTORS)]
        for pid in pids[:3]:
            self.days(pid, nyse("2026-10-13", 15))
        self.days(pids[3], nyse("2026-10-13", 15), skip={names[1]})   # one row has not come
        self.first_night()
        self.advance(names[0])
        self.judge(at(names[0], 23, 30))
        self.assertEqual(self.rows("pool_sessions", "WHERE cell=?", (SECTORS,)), [])   # not settled: no later night
        self.advance(names[1])
        self.advance(names[2])
        self.judge(at(names[2], 23, 30))
        days = [r["day"] for r in self.rows("pool_sessions", "WHERE cell=? ORDER BY day", (SECTORS,))]
        self.assertEqual(days, [names[0]])                             # names[1] waits for its fourth row
        self.days(pids[3], [names[1]])
        self.advance(names[3])
        self.judge(at(names[3], 23, 30))
        days = [r["day"] for r in self.rows("pool_sessions", "WHERE cell=? ORDER BY day", (SECTORS,))]
        self.assertEqual(days, names[:3])

    def test_absent_days_count_zero_and_a_later_member_joins_at_its_first_counted_day(self):
        names = nyse("2026-10-13", 25)
        pids = [pid for _, pid in self.founders(SECTORS)]
        late = names.index(CLOCK) + 3
        for pid in pids[:3]:
            self.days(pid, names, alpha=0.001)
        self.days(pids[3], names[late:], alpha=0.001)                 # its first counted day is three sessions in
        self.first_night()
        for day in [d for d in names if d > "2026-10-23"]:
            self.advance(day)
        store = self.store()
        try:
            j = PS.Night(self.root, store, self.fdb, receipt=self.rec, runs=self.runs, families=self.families,
                         settings=SETTINGS, clock=lambda: at(names[-1], 23, 30))
            j.train_step()
            j.classify(SECTORS)
            sess = j.sessions(SECTORS, self.engine)
            out = j.series(SECTORS, self.engine, sess[:6])
        finally:
            store.close()
        self.assertEqual(out["active"], [3, 3, 3, 4, 4, 4])
        self.assertEqual(len(out["D"]), 6)

    def test_an_absent_row_enters_d_as_zero_by_hand(self):
        names = nyse("2026-10-13", 25)
        members = self.founders(SECTORS)
        gone = names[names.index(CLOCK) + 2]
        for i, (_, pid) in enumerate(members):
            self.days(pid, names, alpha=0.001, skip={gone} if i == 0 else ())
        self.first_night()
        for day in [d for d in names if d > "2026-10-23"]:
            self.advance(day)
        for _ in range(PS.STALL_NIGHTS):                               # the absent row will not come
            self.advance(names[-1])
        store = self.store()
        try:
            j = PS.Night(self.root, store, self.fdb, receipt=self.rec, runs=self.runs, families=self.families,
                         settings=SETTINGS, clock=lambda: at(names[-1], 23, 30))
            j.train_step()
            j.classify(SECTORS)
            sess = j.sessions(SECTORS, self.engine)[:6]
            self.assertIn(gone, sess)                                   # three counted rows: still a cell session
            cell = j.cell_members(SECTORS)
            whole = j.series(SECTORS, self.engine, sess, members=cell)
            each = [j.series(SECTORS, self.engine, sess, members=[m])["D"] for m in cell]
        finally:
            store.close()
        for t, day in enumerate(sess):
            want = sum(z[t] for z in each) / 4                         # each member's own z; the absent one's is 0
            self.assertAlmostEqual(whole["D"][t], want, places=14)
        self.assertEqual(each[0][sess.index(gone)], 0.0)
        self.assertEqual(whole["mar"][sess.index(gone)][1:], (1, 4))   # one zeroed member-day of four slots


class TheLooksWriteAWordAndAShaUntilFinal(Looks):
    def test_a_non_final_look_writes_only_the_word_and_the_sha(self):
        self.run_through(41, alpha=0.0, placebo=fails)
        checks = self.rows("pool_checks", "WHERE cell=?", (SECTORS,))
        self.assertEqual(len(checks), 1)
        self.assertEqual((checks[0]["k"], checks[0]["word"]), (40, "not_passed"))
        self.assertEqual(self.rows("pool_verdicts", "WHERE cell=?", (SECTORS,)), [])
        self.assertEqual(set(checks[0]), {"cell", "k", "engine", "word", "sha", "look", "at"})   # no T, no series
        self.assertEqual(self.permits()["units"][SECTORS]["word"], "pending")
        report = json.loads((self.root / PS.REPORT).read_text()) if (self.root / PS.REPORT).exists() else None
        if report is not None:
            self.assertEqual(report["units"][SECTORS]["word"], "pending")
        # the stored sha is D_1..40's, read again from the store
        store = self.store()
        try:
            j = PS.Night(self.root, store, self.fdb, receipt=self.rec, runs=self.runs, families=self.families)
            sess = j.sessions(SECTORS, self.engine)[:40]
            out = j.series(SECTORS, self.engine, sess)
            self.assertEqual(P.series_sha(sess, out["D"], out["D15"]), checks[0]["sha"])
        finally:
            store.close()

    def test_a_pass_writes_the_verdict_with_its_series_once(self):
        self.run_through(42, alpha=0.002)
        verdict = self.rows("pool_verdicts", "WHERE cell=?", (SECTORS,))
        self.assertEqual(len(verdict), 1)
        self.assertEqual((verdict[0]["word"], verdict[0]["k"]), ("PASS", 40))
        self.assertEqual(len(json.loads(verdict[0]["series"])["D"]), 40)
        self.assertGreaterEqual(verdict[0]["t"], verdict[0]["c_used"])
        doc = self.permits()
        self.assertEqual(doc["units"][SECTORS]["word"], "PASS")
        self.assertEqual(P.figure_free(doc), [])

    def test_a_pass_without_its_placebo_leg_is_no_pass(self):
        self.run_through(41, alpha=0.002, placebo=fails)
        self.assertEqual(self.rows("pool_verdicts", "WHERE cell=?", (SECTORS,)), [])
        self.assertEqual(self.rows("pool_checks", "WHERE cell=?", (SECTORS,))[0]["word"], "not_passed")

    def test_an_ineligible_look_writes_no_verdict(self):
        self.run_through(41, alpha=0.002, floor=lambda *a, **k: None)
        self.assertEqual(self.rows("pool_checks", "WHERE cell=?", (SECTORS,))[0]["word"], "ineligible")
        self.assertEqual(self.rows("pool_verdicts", "WHERE cell=?", (SECTORS,)), [])

    def test_a_moved_series_is_void(self):
        """A later look reads D_1..k of every earlier look again from the store: a series that is not the stored
        sha's is a moved series (the judged days moved): VOID, written once."""
        out, names = self.run_through(41, alpha=0.0, placebo=fails)
        self.assertEqual(self.rows("pool_checks", "WHERE cell=?", (SECTORS,))[0]["k"], 40)
        more = nyse(names[-1], 25)[1:]
        for _, pid in self.founders(SECTORS):
            self.days(pid, more)
        real = P.series_sha
        with mock.patch.object(PS.Night, "c_own", no_floor), mock.patch.object(PS.Night, "placebo", fails), \
                mock.patch.object(P, "series_sha", lambda days, D, D15: "0" * 64 if len(days) == 40 else real(days, D, D15)):
            for day in more:
                self.advance(day)
                self.judge(at(day, 23, 30))
        verdict = self.rows("pool_verdicts", "WHERE cell=?", (SECTORS,))[0]
        self.assertEqual(verdict["word"], "VOID")
        self.assertIn("moved", verdict["why"])
        self.assertEqual([c["k"] for c in self.rows("pool_checks", "WHERE cell=?", (SECTORS,))], [40])


class ALookAfterAFailedNight(Looks):
    def test_reads_exactly_d1_k(self):
        names = nyse("2026-10-13", 70)
        for _, pid in self.founders(SECTORS):
            self.days(pid, names)
        self.first_night()
        after = [d for d in names if d > "2026-10-23"]
        with mock.patch.object(PS.Night, "c_own", no_floor), mock.patch.object(PS.Night, "placebo", fails):
            for day in after[:41]:
                self.advance(day)
            self.fail_forward = True
            tally, _ = self.judge(at(after[40], 23, 30))
            self.assertEqual(self.rows("pool_checks"), [])            # the House failed: nothing written, nobody marked
            self.assertGreaterEqual(tally.get("house", 0), 1)
            self.assertTrue(self.rows("pool_events", "WHERE kind='waited'"))
            self.fail_forward = False
            for day in after[41:50]:
                self.advance(day)
            self.judge(at(after[49], 23, 30))
        check = self.rows("pool_checks", "WHERE cell=?", (SECTORS,))[0]
        store = self.store()
        try:
            j = PS.Night(self.root, store, self.fdb, receipt=self.rec, runs=self.runs, families=self.families)
            sess = j.sessions(SECTORS, self.engine)
            self.assertGreater(len(sess), 40)
            out = j.series(SECTORS, self.engine, sess[:40])
            self.assertEqual(check["sha"], P.series_sha(sess[:40], out["D"], out["D15"]))   # exactly D_1..40
        finally:
            store.close()


class TheStallRule(Looks):
    def test_a_house_failure_marks_nobody_and_stalls_after_five_nights(self):
        names = nyse("2026-10-13", 70)
        for _, pid in self.founders(SECTORS):
            self.days(pid, names)
        self.first_night()
        after = [d for d in names if d > "2026-10-23"]
        self.fail_forward = True
        with mock.patch.object(PS.Night, "c_own", no_floor), mock.patch.object(PS.Night, "placebo", fails):
            for day in after[:40]:
                self.advance(day)
            tallies = []
            for day in after[40:47]:
                self.advance(day)
                tallies.append(self.judge(at(day, 23, 30))[0])
        self.assertEqual(self.rows("pool_checks"), [])
        self.assertEqual(self.rows("pool_verdicts"), [])
        self.assertEqual(len(self.rows("pool_events", "WHERE kind='stalled'")), 1)
        self.assertGreaterEqual(sum(t.get("stalled_now", 0) for t in tallies), 1)


class TheFinalLook(Looks):
    def test_fail_at_120(self):
        with mock.patch.object(P, "PLAN", (40, 60, 120)):
            self.run_through(121, alpha=0.0, placebo=fails)
        verdict = self.rows("pool_verdicts", "WHERE cell=?", (SECTORS,))[0]
        self.assertEqual((verdict["word"], verdict["k"]), ("FAIL", 120))
        self.assertEqual([c["k"] for c in self.rows("pool_checks", "WHERE cell=? ORDER BY k", (SECTORS,))], [40, 60, 120])
        self.assertEqual(len(json.loads(verdict["series"])["D"]), 120)
        self.assertEqual(self.permits()["units"][SECTORS]["word"], "FAIL")


class AMemberWhoseRunDoesNotReproduce(Looks):
    def test_over_ten_percent_enters_as_zero_throughout_with_a_warning(self):
        names = nyse("2026-10-13", 60)
        lin, pid = self.founders(SECTORS)[0]
        for day in names[10:20]:                                     # ten of its ~50 days: over 10%
            self.unreproduced[(pid, day)] = 0.01
        out, _ = self.run_through(41, alpha=0.0, placebo=fails)
        self.assertGreaterEqual(sum(t[0].get("unreproduced", 0) for t in out), 1)
        events = self.rows("pool_events", "WHERE kind='unreproduced'")
        self.assertEqual([e["lineage"] for e in events], [lin])
        store = self.store()
        try:
            j = PS.Night(self.root, store, self.fdb, receipt=self.rec, runs=self.runs, families=self.families)
            sess = j.sessions(SECTORS, self.engine)[:40]
            member = [m for m in j.cell_members(SECTORS) if m["lineage"] == lin]
            self.assertEqual(set(j.series(SECTORS, self.engine, sess, members=member)["D"]), {0.0})
        finally:
            store.close()


class TheOwnFloorAtALook(Looks):
    def test_c_own_on_the_clusters_members_and_its_resamples_kept_across_nights(self):
        """The own floor at a look, on the real code (2,000 resamples cut to 60 here): the night's budget runs out after
        one chunk of resamples, they are kept, the look waits (nothing is written for it), and the next night resumes
        from them; each cell's look reads its cluster's floor with the membership through that look."""
        real_floor, real_boot = PS.Night.c_own, P.bootstrap_histograms
        state = {"chunks": 0, "limit": 1}

        def counted(*args, **kwargs):
            state["chunks"] += 1
            return real_boot(*args, **kwargs)

        def over(self):
            return state["chunks"] >= state["limit"]

        with mock.patch.object(P, "BOOT_RESAMPLES", 60), mock.patch.object(P, "bootstrap_histograms", counted), \
                mock.patch.object(PS.Night, "_over", over):
            self.run_through(41, alpha=0.0, placebo=fails, floor=real_floor)
            self.assertEqual(self.rows("pool_floors"), [])                 # the budget ran out mid-bootstrap
            self.assertEqual(len(self.rows("pool_boot")), 50)               # its one chunk kept
            self.assertEqual(self.rows("pool_checks"), [])
            self.assertTrue(self.rows("pool_events", "WHERE kind='waited'"))
            state["limit"] = 10 ** 9
            day = nyse("2026-10-13", 60)[53]
            self.advance(day)
            with mock.patch.object(PS.Night, "c_own", real_floor), mock.patch.object(PS.Night, "placebo", fails):
                self.judge(at(day, 23, 30))
        floors = self.rows("pool_floors")
        self.assertEqual({f["cluster"] for f in floors}, {"reversal_liquidity", "trend_momentum"})
        self.assertEqual(len(self.rows("pool_boot")), 60 * len(P.NULLS) * len(floors))
        for f in floors:
            row = json.loads(f["row"])
            self.assertEqual(set(row["nulls"]), set(P.NULLS))
            if row["k_own"] is not None:
                self.assertGreaterEqual(row["k_own"], row["matched"])
        self.assertEqual({c["cell"] for c in self.rows("pool_checks")}, set(self.rec.units))
        self.assertTrue(all(c["word"] in ("not_passed", "ineligible") for c in self.rows("pool_checks")))


class TheZeroedDaysVoid(Looks):
    def test_absent_rows_on_the_largest_moves_void_the_cell(self):
        """One member's rows absent on exactly the four sessions of the largest benchmark moves (each session still a
        cell session: three counted rows): its zeroed days are all in the top decile, p = 0.1^4: VOID."""
        names = nyse("2026-10-13", 70)
        after = [d for d in names if d >= CLOCK]
        moves = sorted(after[:40], key=lambda d: -abs(fwd_R("XLK", d)))[:4]
        pids = [pid for _, pid in self.founders(SECTORS)]
        self.run_through(41, alpha=0.0, skip={pids[0]: set(moves)}, placebo=fails, extra=PS.STALL_NIGHTS + 1)
        verdict = self.rows("pool_verdicts", "WHERE cell=?", (SECTORS,))
        self.assertEqual(verdict[0]["word"], "VOID")
        mar = json.loads(verdict[0]["mar"])
        self.assertTrue(mar["void"])
        self.assertEqual((mar["top"], mar["zeroed"]), (4, 4))

    def test_absent_rows_spread_evenly_do_not(self):
        names = nyse("2026-10-13", 70)
        after = [d for d in names if d >= CLOCK]
        pids = [pid for _, pid in self.founders(SECTORS)]
        self.run_through(41, alpha=0.0, skip={pids[0]: set(after[1:40:8])}, placebo=fails, extra=PS.STALL_NIGHTS + 1)
        self.assertEqual(self.rows("pool_verdicts", "WHERE cell=?", (SECTORS,)), [])
        self.assertEqual(self.rows("pool_checks", "WHERE cell=?", (SECTORS,))[0]["word"], "not_passed")


# ------------------------------------------------------------------------------------------- engine, join, demotion
class TheEngineRule(Looks):
    def test_an_engine_move_that_touches_a_judged_day_voids_a_pending_cell(self):
        self.run_through(41, alpha=0.0, placebo=fails)
        new, _ = forward_db.engine_id(self.fdb, "equity-engine-1+bbbbbbbbbbbb+fwd-1", at=2.0)
        self.fdb.commit()
        names = nyse("2026-10-13", 53)
        for _, pid in self.founders(SECTORS):
            self.days(pid, names, alpha=0.01, engine=new)                # every judged day moved
        self.advance(names[-1])
        with mock.patch.object(PS.Night, "c_own", no_floor), mock.patch.object(PS.Night, "placebo", fails):
            self.judge(at(names[-1], 23, 30))
        self.assertEqual(self.rows("pool_verdicts", "WHERE cell=?", (SECTORS,))[0]["word"], "VOID")

    def test_an_engine_move_that_leaves_them_carries_the_cell(self):
        self.run_through(41, alpha=0.0, placebo=fails)
        new, _ = forward_db.engine_id(self.fdb, "equity-engine-1+bbbbbbbbbbbb+fwd-1", at=2.0)
        self.fdb.commit()
        names = nyse("2026-10-13", 53)
        for _, pid in self.founders(SECTORS):
            self.days(pid, names, alpha=0.0, engine=new)
        self.advance(names[-1])
        with mock.patch.object(PS.Night, "c_own", no_floor), mock.patch.object(PS.Night, "placebo", fails):
            self.judge(at(names[-1], 23, 30))
        self.assertEqual(self.rows("pool_verdicts", "WHERE cell=?", (SECTORS,)), [])
        switched = self.rows("pool_events", "WHERE kind='engine_switched' AND cell=?", (SECTORS,))
        self.assertEqual(json.loads(switched[0]["payload"])["to"], new)

    def test_a_pass_touched_by_an_engine_move_is_lost_never_gained(self):
        self.run_through(42, alpha=0.002)
        self.assertEqual(self.rows("pool_verdicts", "WHERE cell=?", (SECTORS,))[0]["word"], "PASS")
        new, _ = forward_db.engine_id(self.fdb, "equity-engine-1+bbbbbbbbbbbb+fwd-1", at=2.0)
        self.fdb.commit()
        names = nyse("2026-10-13", 54)
        for _, pid in self.founders(SECTORS):
            self.days(pid, names, alpha=-0.01, engine=new)
        self.advance(names[-1])
        self.judge(at(names[-1], 23, 30))
        self.assertEqual(self.permits()["units"][SECTORS]["word"], "DEMOTED")
        self.assertIn("lost", self.rows("pool_demotions", "WHERE cell=?", (SECTORS,))[0]["why"])


class AJoinLosesAPass(Looks):
    def test_a_recorded_pass_is_re_derived_at_the_joint_bar(self):
        self.run_through(42, alpha=0.002)
        verdict = self.rows("pool_verdicts", "WHERE cell=?", (SECTORS,))[0]
        db = self.store()
        with db:
            db.execute("INSERT INTO pool_clusters(look, cluster, cells, u_point, u_bound, at) VALUES (?,?,?,?,?,?)",
                       (f"{REVERSAL}:40", "reversal_liquidity+trend_momentum", json.dumps(sorted([SECTORS, INDEX, REVERSAL])),
                        0.04, 0.06, 99.0))
            db.execute("INSERT INTO pool_floors(cluster, look, row, at) VALUES (?,?,?,?)",
                       ("reversal_liquidity+trend_momentum", f"{REVERSAL}:40",
                        json.dumps({"k_own": int(verdict["t"] * 100) + 50, "why": None}), 99.0))
        db.close()
        self.advance(nyse("2026-10-13", 60)[-1])
        self.judge(at(nyse("2026-10-13", 60)[-1], 23, 30))
        self.assertEqual(self.permits()["units"][SECTORS]["word"], "DEMOTED")
        self.assertIn("joint bar", self.rows("pool_demotions", "WHERE cell=?", (SECTORS,))[0]["why"])

    def test_the_effective_cluster_joins_only_tighten(self):
        self.first_night()
        db = self.store()
        with db:
            db.execute("INSERT INTO pool_clusters(look, cluster, cells, u_point, u_bound, at) VALUES (?,?,?,?,?,?)",
                       ("x:40", "reversal_liquidity+trend_momentum", json.dumps([SECTORS, INDEX, REVERSAL]), 0.04, 0.06,
                        5.0))
        j = PS.Night(self.root, db, self.fdb, receipt=self.rec, runs=self.runs, families=self.families)
        cid, cells, u = j.effective_cluster(SECTORS)
        self.assertEqual((cid, cells), ("reversal_liquidity+trend_momentum", sorted([SECTORS, INDEX, REVERSAL])))
        self.assertEqual(u, P.joined_u([(0.02, 0.03), (0.02, 0.03)]))
        db.close()


class TheDemotion(Looks):
    def test_a_pass_whose_post_pass_sessions_fail_is_demoted_sticky(self):
        out, names = self.run_through(42, alpha=0.002)
        self.assertEqual(self.rows("pool_verdicts", "WHERE cell=?", (SECTORS,))[0]["word"], "PASS")
        more = nyse(names[-1], 30)[1:]
        for _, pid in self.founders(SECTORS):
            self.days(pid, more, alpha=-0.004)
        for day in more:
            self.advance(day)
            self.judge(at(day, 23, 30))
        self.assertEqual(self.permits()["units"][SECTORS]["word"], "DEMOTED")
        post = self.rows("pool_post", "WHERE cell=?", (SECTORS,))
        self.assertEqual([p["n"] for p in post], [20])
        self.assertEqual(post[0]["word"], "DEMOTED")


# ---------------------------------------------------------------------------------------- permits and operator views
class ThePermitFile(Looks):
    def test_ids_and_words_only_and_every_registry_lineage(self):
        self.register("equity:other-1", 801, group="index", created_at=at("2026-10-21", 15), first_day="2026-10-22",
                      reason="train_fail")
        self.run_through(42, alpha=0.002)
        doc = self.permits()
        self.assertEqual(P.figure_free(doc), [])
        self.assertEqual(doc["version"], PS.PERMITS_VERSION)
        self.assertEqual(set(doc), {"version", "screen", "receipt", "clock", "at", "routes", "holds", "units", "lineages",
                                    "eligible"})
        registry_lineages = {str(r[0]) for r in self.fdb.execute("SELECT DISTINCT lineage FROM fwd_registry")}
        self.assertLessEqual(registry_lineages, set(doc["lineages"]))
        self.assertIsNone(doc["lineages"]["equity:other-1"]["cell"])
        self.assertEqual(stat.S_IMODE(os.stat(self.root / PS.PERMITS).st_mode), 0o600)
        # the eligible lineages of the pass: in Train K order, ids only
        eligible = doc["eligible"]
        self.assertEqual({e["lineage"] for e in eligible}, {lin for lin, _ in self.founders(SECTORS)})
        pids = [self.rec.founders[e["lineage"]].pid for e in eligible]
        ks = [(30 + pid % 7) for pid in pids]
        self.assertEqual(ks, sorted(ks, reverse=True))
        self.assertTrue(all(set(e) == {"lineage", "cell", "cluster", "family", "version", "run_sha", "fwd1_cell"}
                            for e in eligible))

    def test_the_names_are_the_swarms(self):
        from league.swarm import elane_forward, elane_seal

        self.assertEqual(PS.PERMITS, elane_forward.POOL_PERMITS)
        self.assertEqual(PS.PERMITS, FR.POOL_PERMITS)
        self.assertEqual(PS.PERMITS_VERSION, elane_forward.POOL_PERMITS_VERSION)
        self.assertEqual(PS.MODES, elane_forward.POOL_MODES)
        self.assertIn(elane_forward.POOL_KEY, elane_seal.SEALED_KEYS)
        self.assertEqual(set(FR.POOL_OVER), set(PS.OVER))
        for settings in ({}, {"elane": {}}, {"elane": {"pool": {}}}, {"elane": {"pool": {"mode": "off"}}},
                         {"elane": {"pool": {"mode": "record"}}}, {"elane": {"pool": {"mode": "bogus"}}}):
            self.assertEqual(PS.pool_on(settings), elane_forward.pool_on(settings), settings)

    def test_the_report_shows_no_interim_word(self):
        self.run_through(41, alpha=0.0, placebo=fails)
        store = self.store()
        try:
            rep = PS.report(store, receipt=self.rec)
        finally:
            store.close()
        self.assertEqual(rep["units"][SECTORS]["word"], "pending")
        self.assertNotIn("not_passed", json.dumps(rep))
        self.assertIn("0 passes of 3 units", rep["beside"])


class TheOperatorViewsWithhold(World):
    def write(self, doc):
        (self.root / PS.PERMITS).write_text(json.dumps(doc))

    def doc(self, word="pending"):
        return {"version": 1, "screen": "POOL1", "receipt": "d" * 64, "clock": CLOCK, "at": "x",
                "routes": {"equity:a": {"cell": SECTORS, "cluster": "trend_momentum"}}, "holds": ["equity:h"],
                "units": {SECTORS: {"cluster": "trend_momentum", "word": word}}, "lineages": {}, "eligible": []}

    def test_both_readers_agree(self):
        cases = [(None, {}), (None, SETTINGS), ("{not json", SETTINGS), (self.doc(), SETTINGS), (self.doc("PASS"), {}),
                 (self.doc("VOID"), SETTINGS), ({**self.doc(), "version": 2}, {}), (self.doc("ineligible"), SETTINGS)]
        for doc, settings in cases:
            path = self.root / PS.PERMITS
            if path.exists():
                path.unlink()
            if doc is not None:
                path.write_text(doc if isinstance(doc, str) else json.dumps(doc))
            with self.subTest(doc=str(doc)[:40], settings=settings):
                self.assertEqual(PS.withheld(self.root, settings), FR._pool_withheld(self.root, settings))
        self.write(self.doc())
        self.assertEqual(PS.withheld(self.root, SETTINGS), (frozenset({"equity:a", "equity:h"}), False))
        self.write(self.doc("FAIL"))
        self.assertEqual(PS.withheld(self.root, SETTINGS), (frozenset({"equity:h"}), False))
        (self.root / PS.PERMITS).unlink()
        self.assertEqual(PS.withheld(self.root, SETTINGS), (frozenset(), True))          # missing while on: fail closed
        self.assertEqual(PS.withheld(self.root, {}), (frozenset(), False))

    def test_fwd1s_report_leaves_a_pool_lineage_out_until_final(self):
        rule = F.Rule(receipt_sha256="c" * 64, figures={k: {"budget": 0.15, "fp_point": 0.02, "fp_ub": 0.025,
                                                            "zero_edge_by_checkpoint": [0.01] * 7, "edge": "+10%",
                                                            "power": 0.05, "fp_avg": 0.03}
                                                        for k in ("ETF|N", "PANEL|N", "PANEL|XS1")})
        lin, pid = sorted(self.rec.units[SECTORS].founders)[0], None
        pid = self.rec.founders[lin].pid
        with self.sdb:
            self.sdb.execute("INSERT INTO fwd1_verdicts(lineage, pid, verdict, k, day, c_used, why, beside, words, at) "
                             "VALUES (?,?,?,?,?,?,?,?,?,?)", (lin, pid, "pass", 5, "2026-10-20", 2.61, "passed",
                                                              "t = 3.10 shadow P&L", "w", 3.0))
        pin = {"start": "2026-10-16", "release": ""}
        full = FS.report(self.sdb, rule=rule, pin=pin, fdb=self.fdb)
        self.assertIn(lin, [p["lineage"] for p in full["passes"]])
        held = FS.report(self.sdb, rule=rule, pin=pin, fdb=self.fdb, withheld={lin})
        self.assertNotIn(lin, [p["lineage"] for p in held["passes"]])
        self.assertEqual(held["pool_route"], 1)
        self.assertEqual(sum(c.get("pass", 0) for c in held["counts"].values()), 0)
        self.assertEqual(held["registry"]["ETF|N"]["observed"], 0)
        everything = FS.report(self.sdb, rule=rule, pin=pin, fdb=self.fdb, withhold_etf=True)
        self.assertEqual(everything["passes"], [])
        self.assertEqual(everything["pool_route"], len(self.rec.units[SECTORS].founders))

    def test_the_bh_by_meter_leaves_them_out_until_final(self):
        lin = sorted(self.rec.units[SECTORS].founders)[0]
        pid = self.rec.founders[lin].pid
        for p in [self.rec.founders[x].pid for x in self.rec.units[SECTORS].founders]:
            self.fdb.execute("INSERT INTO fwd_checks(pid, n, day, engine, t_r, sum_r, sum_r15, t_x, mean_w, p_x, at) "
                             "VALUES (?,?,?,?,?,?,?,?,?,?,?)", (p, 20, "2026-11-10", self.engine, 1.0, 0.1, 0.1, 1.0,
                                                                0.5, 0.01, 1.0))
        self.fdb.commit()
        full = FR._meter_row(self.fdb, "2026-11-10")
        held = FR._meter_row(self.fdb, "2026-11-10", withheld={lin})
        self.assertEqual(held["m"], full["m"] - 1)
        none = FR._meter_row(self.fdb, "2026-11-10", withhold_etf=True)
        self.assertEqual(none["m"], 0)
        del pid


# ----------------------------------------------------------------------------------------------------- the job
class TheJob(World):
    def ctx(self, now, settings=SETTINGS):
        alerts = []
        return types.SimpleNamespace(root=self.root, config={}, now=lambda: now, base=self.base, release=REL,
                                     alert=lambda level, text: alerts.append((level, text)), alerts=alerts), settings

    def test_its_registry_row(self):
        jobs = registry.by_name()
        job = jobs["pool_screen"]
        names = [j.name for j in registry.JOBS]
        self.assertEqual(names.index("pool_screen"), names.index("forward_screen") + 1)
        self.assertEqual([(t.kind, t.job) for t in job.triggers], [("after", "forward_shadow")])
        self.assertEqual((job.wall, job.cpu, job.grace, job.in_pause, job.paid), (PS.WALL_S, 900, 2 * 3600, True, False))
        self.assertEqual(job.module, "league.ops.pool_screen")
        self.assertGreaterEqual(jobs["grant"].grace, max(j.wall for j in registry.JOBS) + 5 * 60)

    def test_mode_off_quiet_and_no_pin(self):
        ctx, _ = self.ctx(at("2026-10-23", 23, 30))
        with mock.patch("league.swarm.settings.load", lambda root, config=None: {"elane": {"pool": {"mode": "off"}}}):
            self.assertIn("off", PS.run(ctx)["why"])
        self.assertFalse((self.root / PS.PERMITS).exists())
        quiet, _ = self.ctx(at("2026-10-26", 15))                     # 11:00 New York on a session
        with mock.patch("league.swarm.settings.load", lambda root, config=None: SETTINGS):
            self.assertIn("09:00-17:30", PS.run(quiet)["why"])
            out = PS.run(ctx)
        self.assertEqual(out["status"], "skipped")
        self.assertIn("nothing is judged", out["why"])
        doc = self.permits()                                           # written from the store: the swarm reads a file
        self.assertEqual((doc["routes"], doc["holds"], doc["receipt"]), ({}, [], None))
        self.assertIn("no POOL1 receipt", doc["why"])

    def test_a_pinned_night_runs_the_job_and_alerts_its_stalls(self):
        self.advance("2026-10-22")
        self.advance("2026-10-23", finished=at("2026-10-23", 23))
        ctx, _ = self.ctx(at("2026-10-23", 23, 30))
        world = self

        class Swarm:
            def __init__(self, root, readonly=False):
                self.closed = False

            def families(self, alive=None, lanes=None):
                return [dict(f, spec={"lane": "equity", **f["spec"]}) for f in world.families.values()]

            def close(self):
                self.closed = True

        with mock.patch("league.swarm.settings.load", lambda root, config=None: SETTINGS), \
                mock.patch.object(P, "rule", lambda *a, **k: (self.rec, None)), \
                mock.patch.object(PS, "PoolRuns", lambda *a, **k: FakeRuns(world)), \
                mock.patch("league.swarm.store.SwarmStore", Swarm):
            out = PS.run(ctx)
            self.assertNotIn("status", out)
            self.assertEqual(out.get("routes_written"), len(self.rec.units[SECTORS].founders))
            self.assertEqual(self.permits()["clock"], CLOCK)
            self.assertEqual(json.loads((self.root / PS.REPORT).read_text())["routes"], out["routes_written"])
            self.assertEqual(PS.run(ctx)["status"], "skipped")             # the same record night: nothing written

    def test_once_a_record_night(self):
        self.advance("2026-10-22")
        self.advance("2026-10-23", finished=at("2026-10-23", 23))
        now = at("2026-10-23", 23, 30)
        kw = dict(receipt=self.rec, settings=SETTINGS, now=now, base=self.base, release=REL, runs=self.runs,
                  families=self.families, swarm=types.SimpleNamespace(), clock=lambda: now)
        first = PS.night(self.root, **kw)
        self.assertNotIn("status", first)
        second = PS.night(self.root, **kw)
        self.assertEqual(second["status"], "skipped")
        self.assertEqual(len(self.rows("pool_runs")), 1)


# --------------------------------------------------------------------------------------------------- the seals
class TheSeals(unittest.TestCase):
    def test_no_stall_cause_is_the_pools(self):
        from league.ops import elane_health, stall

        for causes in (stall.CAUSES, elane_health.CAUSES, stall.RESEARCH_CAUSES):
            self.assertFalse([c for c in causes if "pool" in c], causes)
        self.assertNotIn("pool_screen", (REPO / "league" / "ops" / "stall.py").read_text())

    def test_no_identity_holds_a_pool_module(self):
        from league.gym.driver import LEAGUE_FILES
        from league.swarm import evaluator

        files = set(LEAGUE_FILES) | set(evaluator.EQUITY_GYM_FILES) | set(evaluator.EQUITY_CALENDAR_FILES) | {
            f"league/equity/{n}.py" for n in evaluator.EQUITY_EVIDENCE}
        self.assertFalse({f for f in files if "pool" in f})
        for tree in ("gym", "live", "equity"):
            self.assertFalse(list((REPO / "league" / tree).rglob("pool_*.py")))

    def test_the_rule_reads_no_store(self):
        tree = ast.parse((REPO / "league" / "ops" / "pool_rule.py").read_text())
        imported = {(n.module or "") for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)} | {
            a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        self.assertFalse(imported & {"sqlite3", "forward_db", "pool_screen"})


# ---------------------------------------------------------------------------------- the pool's runs, the real engine
from league.live.decider import InlineDecider  # noqa: E402
from league.tests import test_forward_shadow as TS  # noqa: E402


class ThePoolRunsOnTheRealEngine(TS.Case):
    """`PoolRuns` on E1's real engine in an `InlineDecider` over a synthetic store (E3's shadow test world)."""

    def test_the_train_series_and_the_forward_run_per_symbol(self):
        TS.synth.synthetic_store(self.root / TS.STORE_DIR, symbols=TS.SYMBOLS, start=dt.date(2016, 1, 4),
                                 end=TS.END, seed=7, gate=True, as_of=TS.FWD[8])
        pid = TS.register(self.db, "always@1", TS.ALWAYS, first_close=TS.FWD[2])
        runs = PS.PoolRuns(self.root, budget_seconds=300, decider=InlineDecider(), clock=self.clock)
        eras = runs.train_series(self.program(pid))
        self.assertEqual(len(eras), 2)
        for era in eras:
            ws, w = np.asarray(era["ws"]), np.asarray(era["w"])
            np.testing.assert_allclose(ws.sum(axis=0), w)               # per symbol, summing to screen.series' w
            self.assertEqual(ws.shape, (len(era["symbols"]), len(era["days"])))
            self.assertGreater(era["k_sessions"], 0)
        self.night(TS.FWD[8])
        rows = self.rows(pid)
        found = runs.forward_series(self.program(pid), settings=TS.RECORD, fdb=self.db)
        for row in rows:
            self.assertAlmostEqual(found["r"][row["day"]], row["r"], delta=forward_db.TOL)
            self.assertAlmostEqual(sum(found["ws"][row["day"]]), row["w"], delta=1e-12)
        market = runs.market()
        self.assertEqual(len(market), 2)
        self.assertEqual(len(market[0]["sectors"]), len(P.SECTOR_ETFS))
        self.assertTrue(all(np.isnan(v) for v in market[0]["sectors"][0]))   # a symbol the store lacks: NaN

    def test_the_controls_replay_their_hash_law(self):
        TS.synth.synthetic_store(self.root / TS.STORE_DIR, symbols=TS.SYMBOLS, start=dt.date(2016, 1, 4),
                                 end=TS.END, seed=7, gate=True, as_of=TS.FWD[8])
        pid = TS.register_control(self.db, "index", 0, list(TS.SYMBOLS), first_close=TS.FWD[2])
        program = self.program(pid)
        runs = PS.PoolRuns(self.root, budget_seconds=300, decider=InlineDecider(), clock=self.clock)
        spec = json.loads(program.code)
        eras = runs.control_train(spec)
        self.assertEqual(len(eras), 2)
        for era in eras:
            ws = np.asarray(era["ws"])
            self.assertEqual(ws.shape, (len(spec["symbols"]), len(era["days"])))
            self.assertGreater(float(ws.sum()), 0.0)
            self.assertEqual(len(era["r0"]), len(era["days"]))
        self.night(TS.FWD[8])
        found = runs.control_forward(program, settings=TS.RECORD, fdb=self.db)
        rows = self.rows(pid)
        self.assertTrue(rows)
        for row in rows:
            self.assertAlmostEqual(sum(found["ws"][row["day"]]), row["w"], delta=1e-12)   # the record's own exposure


if __name__ == "__main__":
    unittest.main()
