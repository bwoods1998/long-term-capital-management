"""POOL1's job, THE RECORD HALF P1 (league/ops/pool_screen.py; the owner's A55, pre-registered in A55a; the receipt
contract POOL1-RECEIPT-1): the first sighting, the clock-start conformance and the POOL-route list written once, the
refusal's permanence (a lost store, an unreadable file, a shorter list), the House's Train series as the vendored House
job's records, the founders and later lineages (holds, waits on FWD1's row and on earlier members, merges and
assignments), the cell sessions, the looks (a word and a sha at a non-final look, the series with a final verdict,
exactly D_1..k after a failed night), the floors through the vendored pipeline, the engine and join rules (lost, never
gained), the demotion, the House's failures, the permit file of ids and fixed words, the operator views, the job and
its seals.

Every store is made here from invented rows; the House's Train series are the vendored p1conform's invented House
export (league/tests/pool_world.py) and its forward runs a fake. No market data, no real figure, no POOL1 figure."""

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
from league.ops import registry
from league.tests import pool_world as W

REPO = Path(__file__).resolve().parents[2]
UTC = dt.timezone.utc
REL = "20261023T200505Z-pool1"
#: The release that carries the receipt starts Fri Oct 23 2026 at 20:05Z (after the close), before that night's run.
REL_AT = dt.datetime(2026, 10, 23, 20, 5, tzinfo=UTC).timestamp()
SETTINGS = {"elane": {"pool": {"mode": "record", "seats": "off"}, "forward": {"mode": "record"},
                      "fwd1": {"mode": "record", "seats": "off"}}}
SECTORS, INDEX, REVERSAL = W.TM_S, W.TM_I, W.RL_I
CLOCK = "2026-10-26"
BAR = 170                                         # c_G_k: the bar when no floor holds above it (no_floor)


def nyse(first: str, n: int) -> list[str]:
    out, day = [], dt.date.fromisoformat(first)
    while len(out) < n:
        if schedule.is_session(day):
            out.append(day.isoformat())
        day += dt.timedelta(days=1)
    return out


def at(day: str, hour: int = 23, minute: int = 0) -> float:
    return dt.datetime.fromisoformat(day).replace(hour=hour, minute=minute, tzinfo=UTC).timestamp()


def unit_rng(*key) -> np.random.Generator:
    return np.random.default_rng([int(hashlib.sha256("|".join(map(str, key)).encode()).hexdigest()[:8], 16)])


def fwd_R(sym: str, day: str) -> float:
    return float(unit_rng("fR", sym, day).normal(0.0004, 0.01))


def symbol_of(pid: int, extra: dict | None = None) -> str:
    recs = (extra or {}).get(pid) or W.records(pid)
    return str(recs["e0k10"]["universe"][0])


class FakeRuns:
    """The House's runs: the invented export's own `one_run` records for the Train parts (K's counts invented), the
    invented market record, and the member's forward run as the record's own rows (it reproduces every day)."""

    def __init__(self, world: "World"):
        self.w = world
        self.calls: dict[str, int] = {}

    def _count(self, name: str) -> None:
        self.calls[name] = self.calls.get(name, 0) + 1

    def train_part(self, cal, pid, part):
        self._count("train")
        if self.w.fail_train or pid in self.w.fail_pids:
            raise RuntimeError("the child died")
        recs = self.w.extra_records.get(int(pid)) or W.records(int(pid))
        rec = recs[part]
        k = {"close_days": 30 + int(pid) % 7, "sessions": 400} if part.endswith("k10") and rec.get("status") == "ok" \
            else None
        return dict(rec), k

    def market(self, cal):
        self._count("market")
        if self.w.fail_market:
            raise RuntimeError("the store is locked")
        return dict(W.house()["prices"])

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

    def control_train(self, spec):
        self._count("control_train")
        sym = spec["symbols"][0]
        out = []
        for era in (0, 1):
            days = W.house()["prices"][f"e{era}"]["days"][2:]
            R = unit_rng("cR", sym, era).normal(0.0004, 0.01, len(days))
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
    """A state root: a forward record holding the invented export's founders as registry rows, FWD1-R's store, a
    deploys record that names the release carrying the receipt, and invented forward days."""

    RECEIPT: dict = {}
    #: Founders FWD1 has no row for (by default it sighted every one: the export's own tm_s3 is the test of a wait).
    NO_ROW: tuple = ()

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
        self.fdb.row_factory = sqlite3.Row
        self.engine, _ = forward_db.engine_id(self.fdb, "equity-engine-1+aaaaaaaaaaaa+fwd-1", at=1.0)
        self.fdb.commit()
        self.rec = W.receipt(**self.RECEIPT)
        self.cal = W.calib()
        self.families: dict[str, dict] = {}
        self.extra_records: dict[int, dict] = {}
        self.fail_pids: set[int] = set()
        self.unreproduced: dict[tuple[int, str], float] = {}
        self.fail_forward = self.fail_train = self.fail_market = False
        self.alpha: dict[int, float] = {}
        #: The families' immutable birth cards (`cards.card_of`'s): a later lineage's declared class and inputs.
        self.cards: dict[str, dict] = {}
        patch = mock.patch.object(PS, "_card", lambda swarm, fid: self.cards.get(str(fid)))
        patch.start()
        self.addCleanup(patch.stop)
        for m in W.metas():
            self.register(m["lineage"], m["pid"], symbols=list(m["needs_symbols"]), sha=m["program_sha"])
        self.sdb = FS.open_store(self.root)
        for m in W.metas():
            if m["lineage"] in self.NO_ROW:
                continue
            if m["ugroup"] == "sectors":
                self.fwd1_row(m["lineage"], m["pid"])
            else:
                self.fwd1_row(m["lineage"], m["pid"], judged=0, case=None, why=FS.NOT_JUDGED["sealed"])
        self.runs = FakeRuns(self)

    def tearDown(self):
        self.fdb.close()
        self.sdb.close()
        self.tmp.cleanup()

    # ------------------------------------------------------------------------------------------------ the record
    def register(self, lineage: str, pid: int, *, reason: str = "train_pass", first_day: str = "2026-10-13",
                 created_at: float | None = None, ugroup: str | None = None, code: str | None = None,
                 sha: str | None = None, symbols: list[str] | None = None) -> int:
        fid = lineage.split(":", 1)[1]
        sym = symbols or ["SPY"]
        code = code if code is not None else f"PARAMS = {{}}\n# {pid}\n"
        group = "sectors" if sym[0].startswith("XL") else "index"
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
        self.cards.setdefault(fid, {"mechanism_class": "trend_momentum", "inputs": ["underlying_price"]})
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
        sym = symbol_of(pid, self.extra_records)
        for day in names:
            noise = float(rng.normal(0, 0.002))
            if day in skip:
                continue
            b = fwd_R(sym, day)
            r = 0.5 * b + a + noise
            self.fdb.execute("INSERT OR IGNORE INTO fwd_days(pid, day, engine, r, w, b, r15, r0, entries, exits, status, "
                             "at, bars) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                             (pid, day, engine or self.engine, r, 0.5, b, r - 1e-5, None, 0, 0,
                              (status or {}).get(day, "ok"), 1.0, "b" * 16))
        self.fdb.commit()

    def advance(self, day: str, *, finished: float | None = None):
        self.fdb.execute("INSERT INTO fwd_runs(job, through, engine, started, finished, seconds, programs, sessions, "
                         "errors, stale, budget_hit, head) VALUES ('forward_shadow', ?, ?, ?, ?, 0.0, 1, 1, 0, 0, 0, NULL)",
                         (day, self.engine, finished or at(day), finished or at(day)))
        self.fdb.commit()

    # ------------------------------------------------------------------------------------------------ the pool
    def store(self) -> sqlite3.Connection:
        return PS.open_store(self.root)

    def judge(self, now: float, *, receipt_=None, budget: float = 1e9, base: Path | None | str = "default"):
        """One night of the pool as `pool_screen.night` runs it (the routes, the permit file, the looks, the permit file
        and the report), without its once-a-record-night guard (a test reads several nights of one record)."""
        store = self.store()
        try:
            j = PS.Night(self.root, store, self.fdb, receipt=receipt_ or self.rec, runs=self.runs, families=self.families,
                         swarm=None, settings=SETTINGS, budget=budget, clock=lambda: now,
                         base=self.base if base == "default" else base, release=REL, cal=self.cal)
            try:
                pin = j.run_routes(now)
            finally:
                PS.write_permits(self.root, store, receipt=receipt_ or self.rec, at=now, fdb=self.fdb)
            if pin is not None:
                try:
                    j.run_looks()
                finally:
                    PS.write_permits(self.root, store, receipt=receipt_ or self.rec, at=now, fdb=self.fdb)
            (self.root / PS.REPORT).write_text(json.dumps(PS.report(store, receipt=receipt_ or self.rec, notes=j.notes)))
            return dict(j.tally), j
        finally:
            store.close()

    def night_of(self, now: float, **kw) -> PS.Night:
        return PS.Night(self.root, self.store(), self.fdb, receipt=self.rec, runs=self.runs, families=self.families,
                        settings=SETTINGS, clock=lambda: now, cal=self.cal, **kw)

    def rows(self, table: str, where: str = "", args=()) -> list[dict]:
        db = self.store()
        try:
            return [dict(r) for r in db.execute(f"SELECT * FROM {table} {where}", args)]
        finally:
            db.close()

    def founders(self, cell: str) -> list[tuple[str, int]]:
        return [(lin, self.rec.founders[lin].pid) for lin in self.rec.units[cell].members]

    def first_night(self):
        """The record's nights before the release (through Thu Oct 22) and its first night after it (Fri Oct 23)."""
        self.advance("2026-10-22")
        self.advance("2026-10-23", finished=at("2026-10-23", 23))
        return self.judge(at("2026-10-23", 23, 30))

    def permits(self) -> dict:
        return json.loads((self.root / PS.PERMITS).read_text())

    def members(self) -> dict[str, dict]:
        return {m["lineage"]: m for m in self.rows("pool_members")}


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
            for sql in ("UPDATE pool_routes SET why='x'", "DELETE FROM pool_routes",
                        "INSERT OR REPLACE INTO pool_routes(lineage, cell, cluster, night, why, at) VALUES "
                        "('L', 'c2', 'k', 'n', 'w', 2.0)"):
                with self.subTest(sql=sql), self.assertRaises(sqlite3.DatabaseError):
                    with db:
                        db.execute(sql)
            for table in PS.TABLES:
                names = {str(r[0]) for r in db.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND "
                                                       "tbl_name=?", (table,))}
                self.assertEqual(names, {f"{table}_no_update", f"{table}_no_delete"}, table)
            with self.assertRaises(ValueError):
                PS.event(db, "not_a_kind", at=1.0)
        finally:
            db.close()


# ------------------------------------------------------------------------------------- the clock and the conformance
class TheClock(World):
    def test_no_clock_before_a_record_night_after_the_release(self):
        self.advance("2026-10-22")
        tally, _ = self.judge(at("2026-10-23", 21))           # the release ran, no record night yet
        self.assertEqual(tally.get("clock_wait"), 1)
        for table in ("pool_pins", "pool_units", "pool_routes", "pool_members", "pool_train"):
            self.assertEqual(self.rows(table), [], table)
        self.assertEqual(len(self.rows("pool_sighting")), 1)     # the first sighting, stored once
        self.assertEqual(self.permits()["routes"], {})

    def test_the_first_night_checks_conformance_then_writes_the_route_list_once(self):
        self.first_night()
        pins = self.rows("pool_pins")
        self.assertEqual((pins[0]["night"], pins[0]["clock"], pins[0]["evidence"]), ("2026-10-23", CLOCK, "deploys"))
        checks = {c["cluster"]: c for c in self.rows("pool_clockcheck")}
        self.assertEqual({c: bool(r["conforming"]) for c, r in checks.items()},
                         {"trend_momentum": True, "reversal_liquidity": True})
        floors = json.loads(checks["trend_momentum"]["row"])["floors"]
        self.assertEqual(floors, {fd: dict(self.rec.clusters["trend_momentum"].c_own_at_pin[fd]) for fd in P.FLOORS})
        units = {u["cell"]: u for u in self.rows("pool_units")}
        self.assertEqual(set(units), set(self.rec.units))
        self.assertTrue(all(u["clocked"] == 1 and u["conforming"] == 1 for u in units.values()))
        routes = {r["lineage"]: r for r in self.rows("pool_routes")}
        self.assertEqual(set(routes), {lin for lin, _ in self.founders(SECTORS)})       # FWD1's case N sector lineages
        self.assertTrue(all(r["cell"] == SECTORS and r["cluster"] == "trend_momentum" for r in routes.values()))
        members = self.members()
        self.assertEqual({members[lin]["route"] for lin, _ in self.founders(INDEX)}, {"sealed"})
        self.assertEqual(members["equity:eq1"]["route"], "out")
        self.assertEqual((members["equity:rl_copy"]["route"], members["equity:rl_copy"]["merged_into"]),
                         ("merged", "equity:rl_i1"))
        self.judge(at("2026-10-26", 23, 30))
        self.assertEqual(len(self.rows("pool_pins")), 1)
        self.assertEqual(set(r["lineage"] for r in self.rows("pool_routes")), set(routes))

    def test_the_train_series_are_the_house_jobs_records(self):
        self.first_night()
        for m in W.metas():
            rows = {r["part"]: r for r in self.rows("pool_train", "WHERE pid=?", (m["pid"],))}
            f = self.rec.founders[m["lineage"]]
            if f.status != "member":
                self.assertEqual(rows, {})                          # an out or merged founder owes no series
                continue
            self.assertEqual(set(rows), set(P.PARTS))
            for part, row in rows.items():
                self.assertEqual(json.loads(row["record"]), W.records(m["pid"])[part])
                self.assertEqual(PS.record_sha(json.loads(row["record"])), f.train_sha256[part])
        prm = {r["pid"]: r for r in self.rows("pool_params")}
        cal = self.cal
        hc = cal.cluster.house_context(W.house()["prices"], np.array(W.house()["cuts"]))
        _, mm = P.house_member(cal, W.metas()[0], W.records(W.metas()[0]["pid"]), hc)
        self.assertEqual(json.loads(prm[mm.meta["pid"]]["mu"]), [float(x) for x in mm.mu])
        self.assertEqual(prm[mm.meta["pid"]]["sigma"], float(mm.sigma))
        self.assertEqual(len(self.rows("pool_market")), 2)

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

    def test_with_no_deploys_record_the_sighting_is_stored_once_and_the_clock_follows(self):
        """The P1 review's F7: with no deploys record the first sighting's time is stored once and read on every later
        night, so the next record night written after it starts the clock (it no longer waits for ever)."""
        self.advance("2026-10-22")
        self.advance("2026-10-23", finished=at("2026-10-23", 23))
        self.judge(at("2026-10-23", 23, 30), base=None)
        self.assertEqual(self.rows("pool_pins"), [])                       # tonight's run finished before the sighting
        sight = self.rows("pool_sighting")
        self.assertEqual((sight[0]["evidence"], sight[0]["release_start"]), ("sighting", at("2026-10-23", 23, 30)))
        self.advance("2026-10-26")
        self.judge(at("2026-10-26", 23, 30), base=None)
        self.assertEqual(len(self.rows("pool_sighting")), 1)
        self.assertEqual(self.rows("pool_pins")[0]["clock"], "2026-10-27")

    def test_an_alarm_after_five_nights_of_waiting(self):
        self.advance("2026-10-22")
        self.fail_market = True
        tallies = []
        for day in nyse("2026-10-23", 7):
            self.advance(day)
            tallies.append(self.judge(at(day, 23, 30))[0])
        self.assertEqual(self.rows("pool_pins"), [])
        self.assertEqual([bool(t.get("clock_alarm")) for t in tallies], [False] * 4 + [True] * 3)
        report = json.loads((self.root / PS.REPORT).read_text())
        self.assertTrue(any("clock waits" in n for n in report["notes"]))
        self.assertNotIn("why", self.permits())                            # the detail is the report's, never the file's

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

    def test_the_conformance_spans_nights_within_the_budget(self):
        self.advance("2026-10-22")
        self.advance("2026-10-23", finished=at("2026-10-23", 23))
        calls = {"n": 0}
        real = PS.Night._over

        def over(self):
            calls["n"] += 1
            return calls["n"] > 30 or real(self)

        with mock.patch.object(PS.Night, "_over", over):
            self.judge(at("2026-10-23", 23, 30))
        self.assertEqual(self.rows("pool_pins"), [])                      # the House's work waits a night
        self.assertTrue(self.rows("pool_train"))
        self.advance("2026-10-26")
        self.judge(at("2026-10-26", 23, 30))
        self.assertEqual(self.rows("pool_pins")[0]["clock"], "2026-10-27")
        self.assertTrue(all(c["conforming"] for c in self.rows("pool_clockcheck")))

    def test_the_route_rule_at_the_clock(self):
        (pass_lin, pass_pid), (fail_lin, fail_pid) = self.founders(SECTORS)[:2]
        self.fwd1_check(pass_lin, pass_pid, 5, passed=1)
        self.fwd1_verdict(pass_lin, pass_pid, "pass")
        self.fwd1_verdict(fail_lin, fail_pid, "fail")
        self.first_night()
        routes = {r["lineage"] for r in self.rows("pool_routes")}
        self.assertNotIn(pass_lin, routes)                         # an FWD1-R pass before the clock: not on the route
        self.assertIn(fail_lin, routes)                            # an FWD1 fail does not bar the POOL route (A33(5))
        self.assertEqual(self.members()[pass_lin]["route"], "fwd1")

    def test_u_at_the_clock_reads_the_checkpoints_read_before_it(self):
        self.rec = W.receipt(u={"trend_momentum": {"*": [0.02, 0.03], "10": [0.04, 0.06], "15": [0.05, 0.07]}})
        lin, pid = self.founders(SECTORS)[0]
        self.fwd1_check(lin, pid, 5)
        self.fwd1_check(lin, pid, 10)
        self.first_night()
        unit = {u["cell"]: u for u in self.rows("pool_units")}[SECTORS]
        self.assertEqual(unit["fwd1_count"], 10)
        self.assertAlmostEqual(unit["u_point"], 0.04)
        self.assertAlmostEqual(unit["cap"], 0.08)
        self.assertAlmostEqual(unit["wall"], 0.09)


class AFounderWithNoFwd1Row(World):
    NO_ROW = ("equity:tm_s3",)

    def test_waits_and_is_routed_once_fwd1_sights_it(self):
        """The P1 review's F5: a founder FWD1 has no row for at the clock is decided by nothing (no 'sealed' route, no
        member row); once FWD1 sights it as case N it is appended to the POOL-route list."""
        self.first_night()
        self.assertNotIn("equity:tm_s3", self.members())
        self.assertNotIn("equity:tm_s3", self.permits()["routes"])
        self.fwd1_row("equity:tm_s3", self.rec.founders["equity:tm_s3"].pid)
        self.advance("2026-10-26")
        self.judge(at("2026-10-26", 23, 30))
        self.assertEqual(self.members()["equity:tm_s3"]["route"], "pool")
        self.assertIn("equity:tm_s3", self.permits()["routes"])


class ANonconformingCluster(World):
    def setUp(self):
        super().setUp()
        doc = W.doc()
        row = doc["clusters"]["trend_momentum"]["c_own_at_pin"]["R-REG"]
        row["N0"] = row["N0"] + 1                                   # the receipt's pin floor is not this House's
        row["c_own"] = max(row[n] for n in P.NULLS)
        row["k_used"] = P.k_used(170, 3, row["c_own"], row["minimum"])
        self.rec, why = P.read_receipt(W.strict(doc), expect_constants=W.constants())
        assert self.rec is not None, why

    def test_is_not_clocked_and_its_members_stay_per_program(self):
        tally, _ = self.first_night()
        self.assertEqual(tally.get("nonconforming"), 1)
        units = {u["cell"]: u for u in self.rows("pool_units")}
        self.assertEqual((units[SECTORS]["conforming"], units[SECTORS]["clocked"]), (0, 0))
        self.assertEqual((units[REVERSAL]["conforming"], units[REVERSAL]["clocked"]), (1, 1))
        self.assertEqual(self.rows("pool_routes"), [])
        self.assertEqual({self.members()[lin]["route"] for lin, _ in self.founders(SECTORS)}, {"per_program"})
        doc = self.permits()
        self.assertEqual(doc["units"][SECTORS]["word"], P.NONCONFORMING)
        self.assertEqual(P.figure_free(doc), [])
        report = json.loads((self.root / PS.REPORT).read_text())
        self.assertFalse(report["clock_check"]["trend_momentum"]["conforming"])
        self.assertTrue(any("NONCONFORMING" in n for n in report["notes"]))


class AFounderWhoseTrainRunFailsTwice(World):
    def test_is_out_and_its_cluster_nonconforming(self):
        pid = self.rec.founders["equity:tm_s2"].pid
        self.fail_pids.add(pid)
        self.advance("2026-10-22")
        self.advance("2026-10-23", finished=at("2026-10-23", 23))
        self.judge(at("2026-10-23", 23, 30))
        self.assertEqual(self.rows("pool_pins"), [])                      # one failure: a House wait
        self.advance("2026-10-26")
        self.judge(at("2026-10-26", 23, 30))
        prm = {r["pid"]: r for r in self.rows("pool_params")}
        self.assertEqual(prm[pid]["status"], "out")
        self.assertIn("failed twice", prm[pid]["why"])
        units = {u["cell"]: u for u in self.rows("pool_units")}
        self.assertEqual(units[SECTORS]["conforming"], 0)
        self.assertEqual(self.rows("pool_routes"), [])


class AReportOnlyCluster(World):
    RECEIPT = {"u": {"trend_momentum": {"*": [0.12, 0.2]}}}

    def test_its_members_stay_on_their_routes_and_it_seats_nothing(self):
        self.first_night()
        self.assertEqual(self.rows("pool_routes"), [])
        units = {u["cell"]: u for u in self.rows("pool_units")}
        self.assertTrue(units[SECTORS]["report_only"])
        self.assertEqual((units[SECTORS]["cap"], units[SECTORS]["wall"]), (0.12, 0.15))
        self.assertEqual(self.permits()["units"][SECTORS]["word"], P.REPORT_ONLY)
        self.assertNotIn("trend_momentum", {c["cluster"] for c in self.rows("pool_clockcheck")})


class AWallBelowZero(World):
    RECEIPT = {"u": {"trend_momentum": {"*": [0.05, 0.15]}}}

    def test_is_report_only(self):
        self.assertTrue(self.rec.clusters["trend_momentum"].report_only)
        self.first_night()
        self.assertEqual(self.rows("pool_routes"), [])
        self.assertEqual({u["cell"]: u["report_why"] for u in self.rows("pool_units")}[SECTORS], "u_bound")


class ADroppedTicket(World):
    RECEIPT = {"dropped": ("trend_momentum",)}

    def test_is_report_only(self):
        self.first_night()
        self.assertEqual(self.rows("pool_routes"), [])
        self.assertEqual({u["cell"]: u["report_why"] for u in self.rows("pool_units")}[SECTORS], "tickets_dropped")


class ARefutedAndAnIneligibleCluster(World):
    RECEIPT = {"refuted": ("trend_momentum",), "matched": 501}

    def test_are_final_and_never_clocked(self):
        self.first_night()
        verdicts = {v["cell"]: v["word"] for v in self.rows("pool_verdicts")}
        self.assertEqual(verdicts[SECTORS], "REFUTED")
        self.assertEqual(verdicts[REVERSAL], "INELIGIBLE")                # no bar on the grid at the pin
        self.assertEqual(self.rows("pool_routes"), [])
        self.assertEqual(self.permits()["units"][SECTORS]["word"], "REFUTED")
        self.assertEqual(self.permits()["units"][REVERSAL]["word"], P.INELIGIBLE)


# ----------------------------------------------------------------------------------------------- the refusal stays
class TheRefusalIsNeverLifted(World):
    def test_the_route_list_survives_every_final_word_mode_off_and_a_rollback_of_the_pin(self):
        self.first_night()
        routed = set(self.permits()["routes"])
        self.assertTrue(routed)
        db = self.store()
        with db:
            db.execute("INSERT INTO pool_verdicts(cell, word, why, at) VALUES (?,?,?,?)", (SECTORS, "FAIL", "x", 9.0))
        db.close()
        self.judge(at("2026-10-26", 23, 30))
        self.assertEqual(set(self.permits()["routes"]), routed)
        self.assertEqual(self.permits()["units"][SECTORS]["word"], "FAIL")
        ctx = types.SimpleNamespace(root=self.root, config={}, now=lambda: at("2026-10-27", 23, 30), alert=lambda *a: None)
        with mock.patch("league.swarm.settings.load", lambda root, config=None: {"elane": {"pool": {"mode": "off"}}}):
            self.assertEqual(PS.run(ctx)["status"], "skipped")
        self.assertEqual(set(self.permits()["routes"]), routed)
        self.assertTrue(PS.keep_permits(self.root, None, "no_receipt", at("2026-10-28", 23)))
        doc = self.permits()
        self.assertEqual(set(doc["routes"]), routed)
        self.assertEqual((doc["receipt"], doc["why"]), (self.rec.sha256, "no_receipt"))

    def test_a_lost_store_lifts_nothing_and_starts_no_new_clock(self):
        """The P1 review's F4: the store deleted (its WAL too) after the clock: the file's routes and holds are carried
        whole, and a permit file naming this receipt's clock refuses a new clock (no judging, an alarm)."""
        self.register("equity:held-1", 520, created_at=at("2026-10-21", 15), first_day="2026-10-22", symbols=["XLK"])
        self.fwd1_row("equity:held-1", 520)
        self.fail_pids.add(520)
        self.first_night()
        before = self.permits()
        self.assertTrue(before["routes"] and before["holds"] == ["equity:held-1"] and before["clock"] == CLOCK)
        for name in (PS.DB, PS.DB + "-wal", PS.DB + "-shm"):
            path = self.root / name
            if path.exists():
                path.unlink()
        self.advance("2026-10-26")
        tally, _ = self.judge(at("2026-10-26", 23, 30))
        self.assertEqual(tally.get("store_lost"), 1)
        self.assertEqual(self.rows("pool_pins"), [])
        after = self.permits()
        self.assertEqual(set(after["routes"]), set(before["routes"]))
        self.assertEqual(after["holds"], before["holds"])
        self.assertEqual((after["receipt"], after["clock"]), (before["receipt"], before["clock"]))
        self.assertEqual(after["units"][SECTORS]["word"], "pending")
        self.assertTrue(json.loads((self.root / PS.REPORT).read_text())["store_lost"])

    def test_a_lost_store_under_no_receipt_keeps_the_route_list(self):
        """The review's probe: with the store lost and no receipt pinned (a pin rolled back), `keep_permits` used to
        write routes {}: it carries the file's lists whole."""
        self.first_night()
        routed = set(self.permits()["routes"])
        for name in (PS.DB, PS.DB + "-wal", PS.DB + "-shm"):
            if (self.root / name).exists():
                (self.root / name).unlink()
        self.assertTrue(PS.keep_permits(self.root, None, "no_receipt", at("2026-10-27", 23)))
        self.assertEqual(set(self.permits()["routes"]), routed)
        self.assertEqual(self.permits()["clock"], CLOCK)

    def test_a_list_is_never_written_shorter(self):
        self.first_night()
        doc = self.permits()
        doc["routes"]["equity:elsewhere"] = {"cell": SECTORS, "cluster": "trend_momentum"}
        doc["holds"] = ["equity:held-x"]
        (self.root / PS.PERMITS).write_text(json.dumps(doc))
        self.judge(at("2026-10-26", 23, 30))
        after = self.permits()
        self.assertIn("equity:elsewhere", after["routes"])
        self.assertEqual(after["holds"], ["equity:held-x"])

    def test_an_unreadable_file_is_never_overwritten(self):
        self.first_night()
        (self.root / PS.PERMITS).write_text("{torn")
        self.advance("2026-10-26")
        self.judge(at("2026-10-26", 23, 30))
        self.assertEqual((self.root / PS.PERMITS).read_text(), "{torn")
        self.assertTrue(self.rows("pool_events", "WHERE kind='permits_kept'"))

    def test_no_code_deletes_or_replaces_the_permit_file(self):
        tree = ast.parse((REPO / "league" / "ops" / "pool_screen.py").read_text())
        calls = {n.func.attr for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
        self.assertFalse(calls & {"unlink", "remove", "rmtree", "rename", "replace"})

    def test_the_file_is_written_before_the_looks_and_when_they_fail(self):
        """The P1 review's F9: the routes and holds of the night are published right after they are written, whatever
        a later step does; a cell whose look raises is an alarm and the others go on."""
        self.register("equity:held-2", 521, created_at=at("2026-10-21", 15), first_day="2026-10-22", symbols=["XLK"])
        self.fwd1_row("equity:held-2", 521)
        self.fail_pids.add(521)
        with mock.patch.object(PS.Night, "look", side_effect=RuntimeError("a bug in a look")):
            tally, _ = self.first_night()
        self.assertEqual(tally.get("look_failed"), len(self.rec.units))
        doc = self.permits()
        self.assertTrue(doc["routes"])
        self.assertEqual(doc["holds"], ["equity:held-2"])
        self.assertTrue(self.rows("pool_events", "WHERE kind='look_failed'"))


# ------------------------------------------------------------------------------------------- the later lineages
def far(src: int, pid: int, seed: int) -> dict:
    """Records of an independent program on a founder's symbol: its weights flipped on random sessions (invented)."""
    out = {}
    rng = np.random.default_rng(seed)
    flips: dict = {}
    for part, r in W.records(src).items():
        r = json.loads(json.dumps(r))
        era = part[:2]
        if era not in flips:
            flips[era] = rng.random(len(r["days"])) < 0.5
        f = flips[era]
        if "ws" in r:
            sym = r["universe"][0]
            w = np.array(r["ws"].get(sym, [0.0] * len(r["days"])))
            w = np.where(f, 0.5 - w, w)
            r["ws"] = {sym: w.tolist()}
            r["w"] = w.tolist()
        r["r"] = (np.array(r["r"]) * np.where(f, -1.0, 1.0)).tolist()
        r["pid"] = pid
        out[part] = r
    return out


class TheLaterLineages(World):
    def later(self, lineage: str, pid: int, *, like: str = "equity:tm_s1", fwd1: bool = True, created: str = "2026-10-21",
              records: dict | None = None, **kw):
        """A later lineage whose Train series are a copy of a founder's (`like`, perturbed: a near-copy merges, a far
        one does not) or the given records."""
        src = self.rec.founders[like].pid
        recs = records or {part: {**r, "pid": pid} for part, r in W.records(src).items()}
        self.extra_records[pid] = recs
        self.register(lineage, pid, created_at=at(created, 15), first_day="2026-10-22",
                      symbols=[recs["e0k10"]["universe"][0]], **kw)
        if fwd1:
            self.fwd1_row(lineage, pid)

    def test_a_lineage_fwd1_judges_as_case_n_is_held_until_the_house_decides_it(self):
        self.later("equity:late-1", 501)
        self.fail_pids.add(501)                                       # tonight the House cannot read its Train series
        self.first_night()
        self.assertEqual(self.permits()["holds"], ["equity:late-1"])
        self.assertNotIn("equity:late-1", self.members())
        self.fail_pids.discard(501)
        self.advance("2026-10-26")
        self.judge(at("2026-10-26", 23, 30))
        doc = self.permits()
        self.assertEqual(doc["holds"], [])
        members = self.members()
        self.assertEqual(members["equity:late-1"]["route"], "merged")           # a copy of tm_s1: its route
        self.assertIn("equity:late-1", doc["routes"])

    def test_a_held_lineage_with_no_train_series_stays_held(self):
        self.later("equity:late-2", 502)
        self.fail_pids.add(502)
        self.first_night()
        self.assertEqual(self.permits()["holds"], ["equity:late-2"])
        self.assertNotIn("equity:late-2", self.members())

    def test_no_fwd1_row_is_a_wait_never_a_sealed_route(self):
        """The P1 review's F5: a later lineage the House decided before FWD1 sighted it is no longer routed 'sealed'
        and released: it waits; once FWD1 judges it as case N it is held, then decided."""
        self.later("equity:late-3", 503, fwd1=False, records=far(self.rec.founders["equity:tm_s1"].pid, 503, 1))
        self.first_night()
        self.assertNotIn("equity:late-3", self.members())
        self.assertEqual(self.permits()["holds"], [])
        self.fwd1_row("equity:late-3", 503)
        self.advance("2026-10-26")
        self.judge(at("2026-10-26", 23, 30))
        self.assertIn("equity:late-3", self.members())
        self.assertNotEqual(self.members()["equity:late-3"]["route"], "sealed")

    def test_the_copy_merge_waits_for_every_earlier_members_train_series(self):
        """The P1 review's F13: a later lineage is decided only once every earlier member (by pid) has its Train series
        or is out: its copy is never assigned or routed past an earlier member whose series is missing."""
        self.later("equity:first-1", 510, records=far(self.rec.founders["equity:tm_s1"].pid, 510, 2))
        self.later("equity:copy-1", 511, like="equity:tm_s1",
                   records={p: {**r, "pid": 511} for p, r in far(self.rec.founders["equity:tm_s1"].pid, 510, 2).items()})
        self.fail_pids.add(510)
        self.first_night()
        members = self.members()
        self.assertNotIn("equity:copy-1", members)                   # its earlier member has no Train series yet
        self.fail_pids.discard(510)
        self.advance("2026-10-26")
        self.judge(at("2026-10-26", 23, 30))
        members = self.members()
        self.assertEqual((members["equity:copy-1"]["route"], members["equity:copy-1"]["merged_into"]),
                         ("merged", "equity:first-1"))

    def test_what_is_out_is_decided_at_the_first_reading_and_never_held(self):
        self.later("equity:panel-1", 601, ugroup="panel:sp500")
        self.register("equity:stock-1", 602, created_at=at("2026-10-21", 15), symbols=["XLK", "AAPL"])
        self.fwd1_row("equity:stock-1", 602)
        self.later("equity:event-1", 603, code="def decide(ctx):\n    return ctx.events_next\n")
        self.register("equity:failonly-1", 604, reason="train_fail", created_at=at("2026-10-21", 15), symbols=["XLK"])
        self.fwd1_row("equity:failonly-1", 604)
        self.first_night()
        members = self.members()
        self.assertIn("panel", members["equity:panel-1"]["why"])
        self.assertIn("stocks", members["equity:stock-1"]["why"])
        self.assertIn("event reader", members["equity:event-1"]["why"])
        self.assertNotIn("equity:failonly-1", members)                 # Train-fail only: no member, no reading
        self.assertEqual(self.permits()["holds"], [])

    def test_a_copy_by_program_sha_follows_its_members_route(self):
        lin = "equity:tm_s2"
        self.later("equity:copy-9", 701, like="equity:tm_s1", sha=self.rec.founders[lin].program_sha)
        self.first_night()
        members = self.members()
        self.assertEqual(members["equity:copy-9"]["route"], "merged")
        self.assertIn(members["equity:copy-9"]["merged_into"], {"equity:tm_s1", "equity:tm_s2"})
        self.assertIn("equity:copy-9", self.permits()["routes"])

    def test_an_independent_one_is_assigned_or_counts_toward_a_new_cell(self):
        later = W.later_meta()
        self.later(later["lineage"], later["pid"], records=W.records(later["pid"]))
        self.first_night()
        member = self.members()[later["lineage"]]
        cal = self.cal
        hc = cal.cluster.house_context(W.house()["prices"], np.array(W.house()["cuts"]))
        _, mm = P.house_member(cal, later, W.records(later["pid"]), hc)
        cand = {}
        for cell, unit in self.rec.units.items():
            if unit.group == mm.group:
                zs = []
                for x in unit.members:
                    _, f = P.house_member(cal, P.founder_meta(self.rec.founders[x]), W.records(self.rec.founders[x].pid), hc)
                    zs.append(P.train_z(cal, f, hc))
                cand[cell] = zs
        target, _ = P.assign(cal, P.train_z(cal, mm, hc), cand, self.rec.rho_assign)
        if target is None:
            self.assertEqual(member["route"], "new_cell")
        else:
            self.assertEqual((member["route"], member["cell"]), ("pool", target))
            self.assertIn(later["lineage"], self.permits()["routes"])

    def test_fwd1_spend_before_its_hold_releases_it_in_p1(self):
        self.later("equity:late-4", 504, records=far(self.rec.founders["equity:tm_s1"].pid, 504, 3))
        self.fwd1_check("equity:late-4", 504, 5, when=1.0)            # read before the pool ever held it
        with mock.patch.object(P, "assign", lambda cal, z, cells, rho: (SECTORS, {SECTORS: 0.9})):
            self.first_night()
        members = self.members()
        self.assertEqual(members["equity:late-4"]["route"], "fwd1")
        self.assertNotIn("equity:late-4", self.permits()["routes"])
        self.assertEqual(self.permits()["holds"], [])

    def test_assigned_to_a_pending_unit_it_is_on_the_route(self):
        self.later("equity:late-5", 505, records=far(self.rec.founders["equity:tm_s1"].pid, 505, 4))
        with mock.patch.object(P, "assign", lambda cal, z, cells, rho: (SECTORS, {SECTORS: 0.9})):
            self.first_night()
        members = self.members()
        self.assertEqual((members["equity:late-5"]["route"], members["equity:late-5"]["cell"],
                          members["equity:late-5"]["assigned"]), ("pool", SECTORS, 1))
        self.assertIn("equity:late-5", self.permits()["routes"])
        self.assertEqual(self.permits()["holds"], [])


class ALaterLineageAssignedToAFinalUnit(World):
    def test_stays_per_program(self):
        self.first_night()
        db = self.store()
        with db:
            db.execute("INSERT INTO pool_verdicts(cell, word, why, at) VALUES (?,?,?,?)", (SECTORS, "FAIL", "x", 9.0))
        db.close()
        src = self.rec.founders["equity:tm_s1"].pid
        self.extra_records[506] = far(src, 506, 5)
        self.register("equity:late-6", 506, created_at=at("2026-10-26", 15), first_day="2026-10-27", symbols=["XLK"])
        self.fwd1_row("equity:late-6", 506)
        self.advance("2026-10-26")
        with mock.patch.object(P, "assign", lambda cal, z, cells, rho: (SECTORS, {SECTORS: 0.9})):
            self.judge(at("2026-10-26", 23, 30))
        members = self.members()
        self.assertEqual(members["equity:late-6"]["route"], "final_unit")
        self.assertNotIn("equity:late-6", self.permits()["routes"])
        self.assertEqual(self.permits()["holds"], [])


# --------------------------------------------------------------------------------------------- sessions and looks
def no_floor(self, *args, **kwargs):
    return BAR                                                       # c_used = c_G (1.70)


def holds(self, *args, **kwargs):
    return 0, 999


def fails(self, *args, **kwargs):
    return 999, 999


class Looks(World):
    """The sector cell's three founders with forward days from Oct 13 to the session after its k-th cell session."""

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
            for day in [d for d in names if d > "2026-10-23"]:
                self.advance(day)
                out.append(self.judge(at(day, 23, 30)))
            return out, names


class TheSessions(Looks):
    def test_a_session_with_fewer_than_m_min_counted_rows_is_no_cell_session(self):
        names = nyse(CLOCK, 6)
        pids = [pid for _, pid in self.founders(SECTORS)]
        self.days(pids[0], nyse("2026-10-13", 20), skip={names[1]})
        self.days(pids[1], nyse("2026-10-13", 20), status={names[2]: "disqualified"})
        self.days(pids[2], nyse("2026-10-13", 20))
        self.first_night()
        for day in names:
            self.advance(day)
        for i in range(PS.STALL_NIGHTS):
            self.advance(nyse(names[-1], 2 + i)[-1])
        self.judge(at(nyse(names[-1], 2 + PS.STALL_NIGHTS)[-1], 23, 30))
        sess = {r["day"]: r for r in self.rows("pool_sessions", "WHERE cell=?", (SECTORS,))}
        self.assertEqual(sess[names[0]]["session"], 1)
        self.assertEqual((sess[names[1]]["counted"], sess[names[1]]["session"]), (2, 0))   # one row absent
        self.assertEqual((sess[names[2]]["counted"], sess[names[2]]["session"]), (2, 0))   # one disqualified
        self.assertEqual(sess[names[3]]["session"], 1)

    def test_a_session_waits_for_its_rows_and_its_settling_night(self):
        names = nyse(CLOCK, 4)
        pids = [pid for _, pid in self.founders(SECTORS)]
        for pid in pids[:2]:
            self.days(pid, nyse("2026-10-13", 15))
        self.days(pids[2], nyse("2026-10-13", 15), skip={names[1]})     # one row has not come
        self.first_night()
        self.advance(names[0])
        self.judge(at(names[0], 23, 30))
        self.assertEqual(self.rows("pool_sessions", "WHERE cell=?", (SECTORS,)), [])
        self.advance(names[1])
        self.advance(names[2])
        self.judge(at(names[2], 23, 30))
        days = [r["day"] for r in self.rows("pool_sessions", "WHERE cell=? ORDER BY day", (SECTORS,))]
        self.assertEqual(days, [names[0]])
        self.days(pids[2], [names[1]])
        self.advance(names[3])
        self.judge(at(names[3], 23, 30))
        days = [r["day"] for r in self.rows("pool_sessions", "WHERE cell=? ORDER BY day", (SECTORS,))]
        self.assertEqual(days, names[:3])

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
        j = self.night_of(at(names[-1], 23, 30))
        try:
            with mock.patch.object(P, "M_MIN", 2):                     # two counted rows: still a cell session here
                j.classify(SECTORS)
            sess = j.sessions(SECTORS, self.engine)[:6]
            self.assertIn(gone, sess)
            cell = j.cell_members(SECTORS)
            whole = j.series(SECTORS, self.engine, sess, members=cell)
            each = [j.series(SECTORS, self.engine, sess, members=[m])["D"] for m in cell]
        finally:
            j.store.close()
        for t in range(len(sess)):
            self.assertAlmostEqual(whole["D"][t], sum(z[t] for z in each) / len(each), places=14)
        self.assertEqual(each[0][sess.index(gone)], 0.0)
        self.assertEqual(whole["mar"][sess.index(gone)][1:], (1, 3))   # one zeroed member-day of three slots


class TheLooksWriteAWordAndAShaUntilFinal(Looks):
    def test_a_non_final_look_writes_only_the_word_and_the_sha(self):
        self.run_through(41, alpha=0.0, placebo=fails)
        checks = self.rows("pool_checks", "WHERE cell=?", (SECTORS,))
        self.assertEqual(len(checks), 1)
        self.assertEqual((checks[0]["k"], checks[0]["word"]), (40, "not_passed"))
        self.assertEqual(self.rows("pool_verdicts", "WHERE cell=?", (SECTORS,)), [])
        self.assertEqual(set(checks[0]), {"cell", "k", "engine", "word", "sha", "look", "at"})   # no T, no series
        self.assertEqual(self.permits()["units"][SECTORS]["word"], "pending")
        j = self.night_of(at("2026-12-30", 23, 30))
        try:
            sess = j.sessions(SECTORS, self.engine)[:40]
            out = j.series(SECTORS, self.engine, sess)
            self.assertEqual(P.series_sha(sess, out["D"], out["D15"]), checks[0]["sha"])
        finally:
            j.store.close()

    def test_a_pass_writes_the_verdict_with_its_series_once(self):
        self.run_through(42, alpha=0.004)
        verdict = self.rows("pool_verdicts", "WHERE cell=?", (SECTORS,))
        self.assertEqual(len(verdict), 1)
        self.assertEqual((verdict[0]["word"], verdict[0]["k"]), ("PASS", 40))
        self.assertEqual(len(json.loads(verdict[0]["series"])["D"]), 40)
        self.assertGreaterEqual(verdict[0]["t"], verdict[0]["c_used"])
        doc = self.permits()
        self.assertEqual(doc["units"][SECTORS]["word"], "PASS")
        self.assertEqual(P.figure_free(doc), [])
        self.assertEqual({e["lineage"] for e in doc["eligible"]}, {lin for lin, _ in self.founders(SECTORS)})

    def test_a_pass_without_its_placebo_leg_is_no_pass(self):
        self.run_through(41, alpha=0.004, placebo=fails)
        self.assertEqual(self.rows("pool_verdicts", "WHERE cell=?", (SECTORS,)), [])
        self.assertEqual(self.rows("pool_checks", "WHERE cell=?", (SECTORS,))[0]["word"], "not_passed")

    def test_an_ineligible_look_writes_no_verdict(self):
        self.run_through(41, alpha=0.004, floor=lambda *a, **k: None)
        self.assertEqual(self.rows("pool_checks", "WHERE cell=?", (SECTORS,))[0]["word"], "ineligible")
        self.assertEqual(self.rows("pool_verdicts", "WHERE cell=?", (SECTORS,)), [])

    def test_a_moved_series_is_void(self):
        out, names = self.run_through(41, alpha=0.0, placebo=fails)
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
            self.assertEqual(self.rows("pool_checks"), [])
            self.assertGreaterEqual(tally.get("house", 0), 1)
            self.fail_forward = False
            for day in after[41:50]:
                self.advance(day)
            self.judge(at(after[49], 23, 30))
        check = self.rows("pool_checks", "WHERE cell=?", (SECTORS,))[0]
        j = self.night_of(at(after[49], 23, 30))
        try:
            sess = j.sessions(SECTORS, self.engine)
            self.assertGreater(len(sess), 40)
            out = j.series(SECTORS, self.engine, sess[:40])
            self.assertEqual(check["sha"], P.series_sha(sess[:40], out["D"], out["D15"]))
        finally:
            j.store.close()


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
        self.assertEqual(len(self.rows("pool_events", "WHERE kind='stalled' AND cell=?", (SECTORS,))), 1)
        self.assertGreaterEqual(sum(t.get("stalled_now", 0) for t in tallies), 1)


class TheOwnFloorAtALook(Looks):
    def test_the_vendored_floor_on_the_members_through_the_look_kept_across_nights(self):
        """The bar at a look on the real code (the vendored pipeline at the receipt's B): the night's budget runs out
        mid-floor, the resamples computed so far are kept, the look waits (nothing is written for it), and the next
        night resumes from them; each cell's look reads its cluster's floor with the membership through that look."""
        names = nyse("2026-10-13", 60)
        for _, pid in self.founders(SECTORS) + self.founders(INDEX) + self.founders(REVERSAL):
            self.days(pid, names)
        self.first_night()                                              # the clock-start floors: not budgeted here
        state = {"armed": True, "computed": 0, "limit": 4}
        real_hook, real_over = PS.Night.boot_hook, PS.Night._over

        def hook_factory(night, cid, look_key):
            inner = real_hook(night, cid, look_key)

            def hook(null, e, key, compute):
                def counted():
                    state["computed"] += 1
                    return compute()
                return inner(null, e, key, counted)
            return hook

        def over(night):
            return (state["armed"] and state["computed"] >= state["limit"]) or real_over(night)

        after = [d for d in names if d > "2026-10-23"]
        with mock.patch.object(PS.Night, "boot_hook", hook_factory), mock.patch.object(PS.Night, "_over", over), \
                mock.patch.object(PS.Night, "placebo", fails):
            for day in after[:41]:
                self.advance(day)
            self.judge(at(after[40], 23, 30))
            self.assertEqual(self.rows("pool_floors"), [])                 # the budget ran out mid-floor
            kept = len(self.rows("pool_boot"))
            self.assertEqual(kept, state["limit"])
            self.assertEqual(self.rows("pool_checks"), [])
            self.assertTrue(self.rows("pool_events", "WHERE kind='waited'"))
            state["armed"] = False
            self.advance(after[41])
            self.judge(at(after[41], 23, 30))
        floors = {f["cluster"]: json.loads(f["row"]) for f in self.rows("pool_floors")}
        self.assertEqual(set(floors), {"trend_momentum", "reversal_liquidity"})
        for row in floors.values():
            fl = row["floors"][self.rec.rule.floor_def]
            self.assertEqual(row["k_used"], fl["k_used"])
            self.assertEqual(fl["minimum"], 150)
            if fl["c_own"] is not None:
                self.assertEqual(fl["k_used"], P.k_used(170, 3, fl["c_own"], 150))
        self.assertEqual(len(self.rows("pool_boot")), kept)                 # a floor finished in its night keeps none
        self.assertEqual({c["cell"] for c in self.rows("pool_checks")}, set(self.rec.units))


class TheZeroedDaysVoid(Looks):
    def test_absent_rows_on_the_largest_moves_void_the_cell(self):
        """One member's rows absent on exactly the four sessions of the largest benchmark moves: its zeroed days are
        all in the top decile, p = 0.1^4: VOID (the sessions with two rows wait the stall rule, then are not cell
        sessions; another founder joins to keep three counted rows)."""
        names = nyse("2026-10-13", 70)
        after = [d for d in names if d >= CLOCK]
        pids = [pid for _, pid in self.founders(SECTORS)]
        others = [symbol_of(p) for p in pids[1:]]
        # the sessions' benchmark |b| is the mean b of their counted rows: the two others' on the absent days
        moves = sorted(after[:40], key=lambda d: -abs(sum(fwd_R(s, d) for s in others) / len(others)))[:4]
        with mock.patch.object(P, "M_MIN", 2):
            self.run_through(41, alpha=0.0, skip={pids[0]: set(moves)}, placebo=fails, extra=PS.STALL_NIGHTS + 1)
        verdict = self.rows("pool_verdicts", "WHERE cell=?", (SECTORS,))
        self.assertEqual(verdict[0]["word"], "VOID")
        mar = json.loads(verdict[0]["mar"])
        self.assertTrue(mar["void"])
        self.assertEqual((mar["top"], mar["zeroed"]), (4, 4))


# ------------------------------------------------------------------------------------------- engine, join, demotion
class TheEngineRule(Looks):
    def test_an_engine_move_that_touches_a_judged_day_voids_a_pending_cell(self):
        self.run_through(41, alpha=0.0, placebo=fails)
        new, _ = forward_db.engine_id(self.fdb, "equity-engine-1+bbbbbbbbbbbb+fwd-1", at=2.0)
        self.fdb.commit()
        names = nyse("2026-10-13", 53)
        for _, pid in self.founders(SECTORS):
            self.days(pid, names, alpha=0.01, engine=new)
        self.advance(names[-1])
        with mock.patch.object(PS.Night, "c_own", no_floor), mock.patch.object(PS.Night, "placebo", fails):
            self.judge(at(names[-1], 23, 30))
        self.assertEqual(self.rows("pool_verdicts", "WHERE cell=?", (SECTORS,))[0]["word"], "VOID")

    def test_a_pass_touched_by_an_engine_move_is_lost_never_gained(self):
        self.run_through(42, alpha=0.004)
        self.assertEqual(self.rows("pool_verdicts", "WHERE cell=?", (SECTORS,))[0]["word"], "PASS")
        new, _ = forward_db.engine_id(self.fdb, "equity-engine-1+bbbbbbbbbbbb+fwd-1", at=2.0)
        self.fdb.commit()
        names = nyse("2026-10-13", 54)
        for _, pid in self.founders(SECTORS):
            self.days(pid, names, alpha=-0.01, engine=new)
        self.advance(names[-1])
        self.judge(at(names[-1], 23, 30))
        self.assertEqual(self.permits()["units"][SECTORS]["word"], "DEMOTED")


class AJoinLosesAPass(Looks):
    def test_a_recorded_pass_is_re_derived_at_the_joint_bar(self):
        self.run_through(42, alpha=0.004)
        verdict = self.rows("pool_verdicts", "WHERE cell=?", (SECTORS,))[0]
        joint = "reversal_liquidity+trend_momentum"
        db = self.store()
        with db:
            db.execute("INSERT INTO pool_clusters(look, cluster, cells, u_point, u_bound, report_only, at) VALUES "
                       "(?,?,?,?,?,?,?)", (f"{REVERSAL}:40", joint, json.dumps(sorted([SECTORS, INDEX, REVERSAL])), 0.0,
                                           0.0, 0, 99.0))
            db.execute("INSERT INTO pool_floors(cluster, look, row, at) VALUES (?,?,?,?)",
                       (joint, f"{REVERSAL}:40", json.dumps({"k_used": int(verdict["t"] * 100) + 50}), 99.0))
        db.close()
        self.advance(nyse("2026-10-13", 60)[-1])
        self.judge(at(nyse("2026-10-13", 60)[-1], 23, 30))
        self.assertEqual(self.permits()["units"][SECTORS]["word"], "DEMOTED")
        self.assertIn("joint bar", self.rows("pool_demotions", "WHERE cell=?", (SECTORS,))[0]["why"])

    def test_a_join_only_tightens_and_a_report_only_join_is_sticky(self):
        self.first_night()
        db = self.store()
        with db:
            db.execute("INSERT INTO pool_clusters(look, cluster, cells, u_point, u_bound, report_only, at) VALUES "
                       "(?,?,?,?,?,?,?)", ("x:40", "reversal_liquidity+trend_momentum",
                                           json.dumps([SECTORS, INDEX, REVERSAL]), 0.12, 0.15, 1, 5.0))
        j = PS.Night(self.root, db, self.fdb, receipt=self.rec, runs=self.runs, families=self.families, cal=self.cal)
        cid, cells, caps_ = j.effective_cluster(SECTORS)
        self.assertEqual((cid, cells), ("reversal_liquidity+trend_momentum", sorted([SECTORS, INDEX, REVERSAL])))
        self.assertFalse(caps_.report_only)                       # both parts' U 0: the union 0
        self.assertEqual(PS.unit_words(db)[SECTORS]["word"], P.REPORT_ONLY)
        db.close()


class TheDemotion(Looks):
    def test_a_pass_whose_post_pass_sessions_fail_is_demoted_sticky(self):
        out, names = self.run_through(42, alpha=0.004)
        self.assertEqual(self.rows("pool_verdicts", "WHERE cell=?", (SECTORS,))[0]["word"], "PASS")
        more = nyse(names[-1], 30)[1:]
        for _, pid in self.founders(SECTORS):
            self.days(pid, more, alpha=-0.006)
        for day in more:
            self.advance(day)
            self.judge(at(day, 23, 30))
        self.assertEqual(self.permits()["units"][SECTORS]["word"], "DEMOTED")
        post = self.rows("pool_post", "WHERE cell=?", (SECTORS,))
        self.assertEqual([p["n"] for p in post], [20])


# ---------------------------------------------------------------------------------------- permits and operator views
class ThePermitFile(Looks):
    def test_ids_and_fixed_words_only_and_every_registry_lineage(self):
        self.register("equity:other-1", 801, created_at=at("2026-10-21", 15), first_day="2026-10-22", reason="train_fail")
        self.run_through(42, alpha=0.004)
        doc = self.permits()
        self.assertEqual(P.figure_free(doc), [])
        self.assertEqual(set(doc), {"version", "screen", "receipt", "clock", "at", "routes", "holds", "units", "lineages",
                                    "eligible"})
        registry_lineages = {str(r[0]) for r in self.fdb.execute("SELECT DISTINCT lineage FROM fwd_registry")}
        self.assertLessEqual(registry_lineages, set(doc["lineages"]))
        self.assertEqual(stat.S_IMODE(os.stat(self.root / PS.PERMITS).st_mode), 0o600)

    def test_a_why_is_a_fixed_word_and_its_detail_the_reports(self):
        """The P1 review's F8: a reason with a figure in it ("outside 1.40-2.50") never reaches the file (whose figure check
        would refuse it and leave the swarm failing closed): the file carries a word, the report the words."""
        self.assertTrue(PS.keep_permits(self.root, None, "no_receipt", at("2026-10-23", 23),
                                        detail="the receipt's c_G is off the grid or outside 1.40-2.50"))
        self.assertEqual(self.permits()["why"], "no_receipt")
        self.assertEqual(P.figure_free(self.permits()), [])
        self.assertIn("1.40-2.50", json.loads((self.root / PS.REPORT).read_text())["notes"][0])
        PS.keep_permits(self.root, None, "the cap is 0.12", at("2026-10-23", 23))
        self.assertEqual(self.permits()["why"], "unreadable_reason")

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

    def test_the_report_shows_no_interim_word_and_counts_a_cluster_once(self):
        self.run_through(41, alpha=0.0, placebo=fails)
        store = self.store()
        try:
            rep = PS.report(store, receipt=self.rec)
        finally:
            store.close()
        self.assertEqual(rep["units"][SECTORS]["word"], "pending")
        self.assertNotIn("not_passed", json.dumps(rep))
        # three cells read at 40, two of them one cluster's: 0.02 (trend_momentum) + 0.02 (reversal_liquidity)
        self.assertIn("0 passes of 3 units; 0.04 expected at zero edge", rep["beside"])


class TheOperatorViewsWithhold(World):
    def doc(self, word="pending"):
        return {"version": 1, "screen": "POOL1", "receipt": "d" * 64, "clock": CLOCK, "at": "x",
                "routes": {"equity:a": {"cell": SECTORS, "cluster": "trend_momentum"}}, "holds": ["equity:h"],
                "units": {SECTORS: {"cluster": "trend_momentum", "word": word}}, "lineages": {}, "eligible": []}

    def test_both_readers_agree(self):
        cases = [(None, {}), (None, SETTINGS), ("{not json", SETTINGS), (self.doc(), SETTINGS), (self.doc("PASS"), {}),
                 (self.doc("VOID"), SETTINGS), ({**self.doc(), "version": 2}, {}), (self.doc("ineligible"), SETTINGS),
                 (self.doc("nonconforming"), SETTINGS)]
        for doc, settings in cases:
            path = self.root / PS.PERMITS
            if path.exists():
                path.unlink()
            if doc is not None:
                path.write_text(doc if isinstance(doc, str) else json.dumps(doc))
            with self.subTest(doc=str(doc)[:40], settings=settings):
                self.assertEqual(PS.withheld(self.root, settings), FR._pool_withheld(self.root, settings))

    def test_the_bh_by_meter_waits_while_the_file_fails_closed(self):
        """The P1 review's F11: while the pool's permit file fails closed the meter writes no row with every ETF lineage
        left out for good: it waits for the day, and writes it once the file reads."""
        day = forward_db.t0().isoformat()
        for p in [self.rec.founders[x].pid for x in self.rec.units[SECTORS].members]:
            self.fdb.execute("INSERT INTO fwd_checks(pid, n, day, engine, t_r, sum_r, sum_r15, t_x, mean_w, p_x, at) "
                             "VALUES (?,?,?,?,?,?,?,?,?,?,?)", (p, 20, day, self.engine, 1.0, 0.1, 0.1, 1.0, 0.5, 0.01, 1.0))
        self.advance(day)
        out = FR.meters(self.root, self.fdb, now=at(day, 23, 30), settings=SETTINGS)
        self.assertEqual(out.get("waiting", {}).get("pool"), FR.POOL_WAIT)
        self.assertEqual(self.fdb.execute("SELECT COUNT(*) FROM fwd_meter").fetchone()[0], 0)
        (self.root / PS.PERMITS).write_text(json.dumps({**self.doc(), "routes": {}, "holds": []}))
        out = FR.meters(self.root, self.fdb, now=at(day, 23, 40), settings=SETTINGS)
        self.assertNotIn("pool", out.get("waiting") or {})
        self.assertEqual(self.fdb.execute("SELECT COUNT(*) FROM fwd_meter").fetchone()[0], 1)


# ----------------------------------------------------------------------------------------------------- the job
class TheJob(World):
    def ctx(self, now):
        alerts = []
        return types.SimpleNamespace(root=self.root, config={}, now=lambda: now, base=self.base, release=REL,
                                     alert=lambda level, text: alerts.append((level, text)), alerts=alerts)

    def test_its_registry_row(self):
        jobs = registry.by_name()
        job = jobs["pool_screen"]
        names = [j.name for j in registry.JOBS]
        self.assertEqual(names.index("pool_screen"), names.index("forward_screen") + 1)
        self.assertEqual([(t.kind, t.job) for t in job.triggers], [("after", "forward_shadow")])
        self.assertEqual((job.wall, job.cpu, job.grace, job.in_pause, job.paid), (PS.WALL_S, 900, 2 * 3600, True, False))

    def test_mode_off_quiet_and_no_pin(self):
        ctx = self.ctx(at("2026-10-23", 23, 30))
        with mock.patch("league.swarm.settings.load", lambda root, config=None: {"elane": {"pool": {"mode": "off"}}}):
            self.assertIn("off", PS.run(ctx)["why"])
        self.assertFalse((self.root / PS.PERMITS).exists())
        quiet = self.ctx(at("2026-10-26", 15))
        with mock.patch("league.swarm.settings.load", lambda root, config=None: SETTINGS):
            self.assertIn("09:00-17:30", PS.run(quiet)["why"])
            out = PS.run(ctx)
        self.assertIn("nothing is judged", out["why"])
        doc = self.permits()
        self.assertEqual((doc["routes"], doc["holds"], doc["receipt"], doc["why"]), ({}, [], None, "no_receipt"))
        self.assertEqual(ctx.alerts, [])                                   # no pin set: no alarm

    def test_a_refused_receipt_under_a_pin_is_an_alarm(self):
        ctx = self.ctx(at("2026-10-23", 23, 30))
        with mock.patch("league.swarm.settings.load", lambda root, config=None: SETTINGS), \
                mock.patch.object(P, "pin", lambda *a, **k: {"name": "POOL1"}), \
                mock.patch.object(P, "rule", lambda *a, **k: (None, "the receipt's conformance vectors fail on this box: "
                                                                   "CV9: x")):
            out = PS.run(ctx)
        self.assertIn("nothing is judged", out["why"])
        self.assertEqual(self.permits()["why"], "nonconforming_receipt")
        self.assertEqual(len(ctx.alerts), 1)

    def test_the_conformance_is_run_once_and_kept(self):
        calls = {"n": 0}
        real = P.conform

        def counted(rec, cal):
            calls["n"] += 1
            return real(rec, cal)

        with mock.patch.object(P, "conform", counted):
            check = PS.conformed(self.root, 1.0)
            self.assertEqual(check(self.rec, self.cal), (True, None))
            self.assertEqual(check(self.rec, self.cal), (True, None))
        self.assertEqual(calls["n"], 1)
        self.assertEqual(len(self.rows("pool_conform")), 1)

    def test_a_pinned_night_runs_the_job_and_alerts_its_stalls(self):
        self.advance("2026-10-22")
        self.advance("2026-10-23", finished=at("2026-10-23", 23))
        ctx = self.ctx(at("2026-10-23", 23, 30))
        world = self

        class Swarm:
            def __init__(self, root, readonly=False):
                pass

            def families(self, alive=None, lanes=None):
                return [dict(f, spec={"lane": "equity", **f["spec"]}) for f in world.families.values()]

            def close(self):
                pass

        with mock.patch("league.swarm.settings.load", lambda root, config=None: SETTINGS), \
                mock.patch.object(P, "rule", lambda *a, **k: (self.rec, None)), \
                mock.patch.object(PS, "PoolRuns", lambda *a, **k: FakeRuns(world)), \
                mock.patch("league.swarm.store.SwarmStore", Swarm):
            out = PS.run(ctx)
            self.assertNotIn("status", out)
            self.assertEqual(out.get("routes_written"), len(self.rec.units[SECTORS].members))
            self.assertEqual(self.permits()["clock"], CLOCK)
            self.assertEqual(json.loads((self.root / PS.REPORT).read_text())["routes"], out["routes_written"])
            self.assertEqual(PS.run(ctx)["status"], "skipped")             # the same record night: nothing written


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

    def setUp(self):
        super().setUp()
        TS.synth.synthetic_store(self.root / TS.STORE_DIR, symbols=TS.SYMBOLS, start=dt.date(2016, 1, 4),
                                 end=TS.END, seed=7, gate=True, as_of=TS.FWD[8])

    def test_a_train_part_is_the_house_jobs_own_record_and_k_its_runs(self):
        cal = W.calib()
        pid = TS.register(self.db, "always@1", TS.ALWAYS, first_close=TS.FWD[2])
        self.db.row_factory = sqlite3.Row
        runs = PS.PoolRuns(self.root, budget_seconds=300, decider=InlineDecider(), clock=self.clock, fdb=self.db)
        for part in P.PARTS:
            rec, k = runs.train_part(cal, pid, part)
            want = cal.house_job.one_run(self.root, InlineDecider(), self.db, pid, part, [], 300.0)
            self.assertEqual(rec, want)
            if part.endswith("k10") and rec["status"] == "ok":
                self.assertGreater(k["sessions"], 0)
                ws = np.sum([np.asarray(v, dtype=float) for v in rec["ws"].values()], axis=0)
                np.testing.assert_allclose(ws, np.asarray(rec["w"], dtype=float), atol=1e-9)
            else:
                self.assertIsNone(k)
        prices = runs.market(cal)
        self.assertEqual(set(prices) >= {"e0", "e1"}, True)
        self.assertEqual(prices["e0"], cal.house_job.prices(self.root)["e0"])

    def test_the_forward_run_per_symbol_is_the_house_jobs_accounting(self):
        from league.equity import screen

        pid = TS.register(self.db, "always@1", TS.ALWAYS, first_close=TS.FWD[2])
        runs = PS.PoolRuns(self.root, budget_seconds=300, decider=InlineDecider(), clock=self.clock)
        self.night(TS.FWD[8])
        rows = self.rows(pid)
        found = runs.forward_series(self.program(pid), settings=TS.RECORD, fdb=self.db)
        for row in rows:
            self.assertAlmostEqual(found["r"][row["day"]], row["r"], delta=forward_db.TOL)
            self.assertAlmostEqual(sum(found["ws"][row["day"]]), row["w"], delta=1e-12)
        self.assertTrue(callable(screen.series))

    def test_the_controls_replay_their_hash_law(self):
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
        self.night(TS.FWD[8])
        found = runs.control_forward(program, settings=TS.RECORD, fdb=self.db)
        for row in self.rows(pid):
            self.assertAlmostEqual(sum(found["ws"][row["day"]]), row["w"], delta=1e-12)


if __name__ == "__main__":
    unittest.main()
