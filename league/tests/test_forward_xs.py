"""Release E4, package J: the panel lane's half of the forward record (league/ops/forward_xs.py).

What is held here: a scored panel version is registered once, hash-chained, with its NEEDS, its route and its alpha in
the hashed row, and a structure the registry does not know is still refused; a forward run read as E3's series gives
E3's excess the run's own residual and its stress excess the run's stress residual; THE ROWS THAT ARE FINAL (a day's
row once the next session is in the store, a decision once two are: shown on the real engine over a panel whose
membership changes); the panel night (E3's own night on the panel store: rows through the session before the
store's last, the night named by that day under its own job, two nights the same rows, the checkpoint, the queue of
each night its own lane's); the engine label; the budget one night shares; E3's stop rules reading each lane's own
nights; the morning marks; the report's groups; SEAL X14 (`TheMarkerCarriesNoOutcome`); the three alarms, each by its
two switches, their texts ids, counts and dates only; and WITH EVERY MODE OFF NOTHING RUNS AND NOTHING IS WRITTEN.

The twin of a live instance is league/tests/test_forward_xs_twin.py. Every panel, program, verdict and book here is
invented (`league.xs.synth`: seeded pseudo-random paths, made-up tickers); no market data is read."""

from __future__ import annotations

import datetime as dt
import json
import math
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from league.equity import schedule
from league.equity.store import mint_equity_gate_capability
from league.live import decider as D
from league.ops import forward_db as F
from league.ops import forward_register as R
from league.ops import forward_report, forward_shadow
from league.ops import forward_xs as X
from league.ops.context import Context
from league.swarm import elane_xs
from league.swarm.gate import run_sha
from league.swarm.store import SwarmStore
from league.tests import elane_e2_fakes as e2
from league.tests import elane_xs_fakes as fx
from league.tests.test_forward_db import at, sessions_from, sha
from league.xs import book as xbook
from league.xs import config as xconfig
from league.xs import results as xresults
from league.xs import runner as xrunner
from league.xs import store as xstore
from league.xs import synth

#: An invented panel program: each week, the names that fell most over the last five sessions, equal weights, at the
#: open. It keeps no state.
CODE = '''
NEEDS = {"panel": "sp500", "history": 60, "max_names": 8, "rebalance": "weekly", "weekday": 0,
         "max_hold_sessions": 40}
PARAMS = {"k": 6}


def decide(ctx):
    ranked = []
    for i in range(ctx.n):
        week = 0.0
        for j in range(1, 6):
            value = float(ctx.ret[i][-j])
            if value == value:
                week += value
        ranked.append((week, int(ctx.ids[i])))
    ranked.sort()
    picks = [slot for _, slot in ranked[:PARAMS["k"]]]
    if len(picks) < 5:
        return {"hold": True}
    return {"target": {slot: 1.0 / len(picks) for slot in picks}, "at": "open"}
'''
NEEDS = {"panel": "sp500", "history": 60, "max_names": 8, "rebalance": "weekly", "weekday": 0, "max_hold_sessions": 40}
#: Invented Train verdicts as the panel lane's record keeps them (league/swarm/elane_xs.py `compact`).
FACTS = {"seen_years": 5, "years_positive": 4}
PASSED = {"passed": True, "verdict": "pass", "fails": [], "facts": FACTS}
FAILED = {"passed": False, "verdict": "fail", "fails": ["XT1"], "facts": FACTS}
STATE = {"passed": False, "verdict": "fail", "fails": ["STATE"], "facts": FACTS}
REVIEW = {"passed": False, "verdict": "fail", "bar_passed": True, "fails": ["REVIEW"], "facts": FACTS}
#: The synthetic panels end here; a night's store is the same history fetched `as_of` its day.
END = dt.date(2027, 3, 31)
RECORD = {"elane": {"mode": "gate", "universe": ["SPY", "XLK"], "panel": {"mode": "train"},
                    "forward": {"mode": "record", "controls_per_group": 0}}}


class Clock:
    def __init__(self, t: float):
        self.t = float(t)

    def __call__(self) -> float:
        return self.t


class House:
    """A House state root: the real swarm store, the forward store, and a synthetic panel written night by night (one
    history, no membership change, no dividend: nothing restates unless a test asks for it)."""

    def __init__(self, case: unittest.TestCase, **panel):
        tmp = tempfile.TemporaryDirectory()
        case.addCleanup(tmp.cleanup)
        self.case = case
        self.root = Path(tmp.name)
        self.store_root = self.root / "equity-daily"
        self.days = sessions_from(F.t0(), 60)
        self.clock = Clock(at(self.days[0], 12))
        self.panel = {"n_assets": 40, "seed": 11, "churn": 0.0, "gate": True, "end": END, **panel}
        self.swarm = SwarmStore(self.root, clock=self.clock)
        case.addCleanup(self.swarm.close)
        self.db = F.open_db(self.root)
        case.addCleanup(self.db.close)
        self.settings = json.loads(json.dumps(RECORD))
        self.deciders: list[D.InlineDecider] = []

    def store(self, through: dt.date, **over) -> None:
        """The night's stores: the same invented history, fetched as of `through`."""
        synth.synthetic_panel(self.store_root, as_of=through, **{**self.panel, **over})

    def family(self, slug: str, verdicts: dict | None = None, *, code: str = CODE, versions: int = 1, **record) -> str:
        held = {str(n): {"n": n, **v} for n, v in ({1: PASSED} if verdicts is None else verdicts).items()}
        fam = fx.panel_family(self.swarm, slug, code=code, names=8,
                              record={"status": "researching", "versions": held, **record})
        for n in range(2, versions + 1):
            self.swarm.add_version(fam["id"], code, {"k": 5 + n}, author="fake:author")
        return str(fam["id"])

    def scored(self, fid: str, n: int = 1, *, bar_passed: bool = True, when: float | None = None) -> int:
        """The swarm's scored event of a panel version (league/swarm/elane_xs.py `score`), at `when`."""
        if when is not None:
            self.clock.t = when
        return self.swarm.event("swarm.elane", fid, {
            "pass": "scored", "version": n, "sha": self.swarm.version(fid, n)["sha"], "bar_passed": bar_passed,
            "fails": [], "objective": elane_xs.OBJECTIVE, "judged": True, "structure": "panel"})

    def sync(self, when: float | None = None) -> dict:
        if when is not None:
            self.clock.t = when
        return R.sync(self.root, self.db, now=self.clock(), settings=self.settings)

    def row(self, key: str) -> dict | None:
        found = self.db.execute("SELECT * FROM fwd_registry WHERE key=?", (key,)).fetchone()
        return None if found is None else dict(found)

    def decider(self) -> D.InlineDecider:
        self.deciders.append(D.InlineDecider())
        return self.deciders[-1]

    def shadow(self, index: int, *, decider=None, write: bool = True):
        """The panel night's shadow on the evening after session `index` (the panel store through that session)."""
        if write:
            self.store(self.days[index])
        self.clock.t = max(self.clock.t, at(self.days[index], 22, 5))
        return X.panel_shadow(self.root, self.db, decider=decider or self.decider(), settings=self.settings,
                              clock=self.clock, fresh=self.decider)

    def night(self, index: int, **kw) -> dict:
        return self.shadow(index, **kw).night()

    def e3_shadow(self, index: int):
        """E3's own night's shadow on the same root (league/ops/forward_shadow.py)."""
        self.clock.t = max(self.clock.t, at(self.days[index], 18, 35))
        return forward_shadow.Shadow(self.root, self.db, decider=self.decider(), settings=self.settings,
                                     clock=self.clock, fresh=self.decider)

    def rows(self, pid: int) -> list[dict]:
        return [dict(r) for r in self.db.execute("SELECT * FROM fwd_days WHERE pid=? ORDER BY day, engine", (pid,))]

    def events(self, kind: str) -> list[dict]:
        return F.events(self.db, kind)


def registered(case: unittest.TestCase, **panel) -> tuple[House, str, int]:
    """A House with one panel version scored on the first forward day at noon and registered: (the House, its key, its
    pid). Its first decision is that day's close, its first day the session after."""
    h = House(case, **panel)
    h.store(h.days[0])
    fid = h.family("px")
    h.scored(fid, when=at(h.days[0], 12))
    h.sync()
    return h, f"{fid}@1", int(h.row(f"{fid}@1")["pid"])


class TheRegistry(unittest.TestCase):
    def test_a_scored_panel_version_is_registered_once_with_its_needs_in_the_hashed_row(self):
        h = House(self)
        fid = h.family("px")
        seq = h.scored(fid, when=at(h.days[0], 12))
        out = h.sync(at(h.days[1], 10))
        self.assertEqual((out["registered"], out["controls"], out["skipped"]), (1, 0, []))
        row, version = h.row(f"{fid}@1"), h.swarm.version(fid, 1)
        self.assertEqual({k: row[k] for k in ("pid", "family", "version", "lane", "reason", "ugroup", "author",
                                              "evidence", "route", "alpha_f")},
                         {"pid": 1, "family": fid, "version": 1, "lane": "equity", "reason": "train_pass",
                          "ugroup": "panel:sp500", "author": "architect:test", "evidence": f"event:{seq}",
                          "route": "XS1", "alpha_f": "0.03"})
        self.assertEqual((row["code"], row["program_sha"], row["run_sha"]), (CODE, sha(CODE), run_sha(version)))
        self.assertEqual(json.loads(row["needs"]), NEEDS, "the program's own NEEDS literal, parsed by the panel's reader")
        # ...in the hashed row: its route, its alpha and its NEEDS cannot be changed after a forward day exists.
        self.assertTrue({"needs", "route", "alpha_f", "program_sha", "params"} <= set(F.HASHED))
        self.assertTrue(out["chain"]["ok"])
        for column, value in (("needs", json.dumps({**NEEDS, "max_names": 12})), ("route", "S2"), ("alpha_f", "0.12")):
            tampered = dict(row)
            tampered[column] = value
            self.assertNotEqual(F.row_hash(row["prev_hash"], tampered), row["row_hash"], column)
        # D2: it first decides at the close after its scored event, and has no row before the session after.
        self.assertEqual((row["created_at"], row["first_close"], row["first_day"]),
                         (at(h.days[0], 12), h.days[0].isoformat(), h.days[1].isoformat()))
        # A second run adds nothing.
        again = h.sync(at(h.days[1], 11))
        self.assertEqual((again["registered"], again["chain"]["rows"]), (0, 1))
        self.assertEqual(X.scored(h.swarm)[0]["key"], f"{fid}@1")
        self.assertEqual((X.UGROUP, X.ROUTE, X.ALPHA_F), ("panel:sp500", "XS1", "0.03"))

    def test_passed_or_failed_and_never_a_version_judged_on_its_program_alone(self):
        h = House(self)
        unjudged = {code: elane_xs.program_fault(code, "an invented fault") for code in ("RUN", "DQ", "LOAD")}
        fid = h.family("px", {1: PASSED, 2: FAILED, 3: STATE, 4: REVIEW, 5: unjudged["RUN"], 6: unjudged["DQ"],
                              7: unjudged["LOAD"]}, versions=7)
        out = h.sync()
        self.assertEqual((out["registered"], out["skipped"]), (4, []), "unjudged is not refused: it has no figure")
        self.assertEqual({r["key"]: r["reason"] for r in map(dict, h.db.execute("SELECT key, reason FROM fwd_registry"))},
                         {f"{fid}@1": "train_pass", f"{fid}@2": "train_fail", f"{fid}@3": "train_fail",
                          f"{fid}@4": "train_pass"},
                         "a STATE failure was judged on the bar; one the review refused passed the bar")
        self.assertEqual(F.events(h.db, "register_skipped"), [])
        self.assertTrue(X.judged(PASSED) and X.judged(STATE))
        self.assertFalse(X.judged(unjudged["LOAD"]) or X.judged({"facts": {}}) or X.judged(None))

    def test_an_etf_program_beside_it_keeps_e3s_route_and_pids_follow_the_order_they_came_to_exist(self):
        h = House(self)
        etf = e2.e2_family(h.swarm, "ex", lane="equity", agenda="trend", symbols=("XLK",), code=e2.program("XLK"),
                           record={"status": "researching", "versions": {"1": {"passed": True, "fails": [],
                                                                               "pnl_10": 1.0, "pnl_15": 1.0}}})
        fid = h.family("px")
        h.scored(fid, when=at(h.days[0], 11))
        h.clock.t = at(h.days[0], 13)
        h.swarm.event("swarm.elane", etf["id"], {"pass": "scored", "version": 1, "sha": h.swarm.version("ex", 1)["sha"],
                                                 "bar_passed": True})
        out = h.sync(at(h.days[0], 15))
        self.assertEqual(out["registered"], 2)
        rows = [dict(r) for r in h.db.execute("SELECT pid, key, route, ugroup FROM fwd_registry ORDER BY pid")]
        self.assertEqual([(r["key"], r["route"]) for r in rows], [(f"{fid}@1", "XS1"), ("ex@1", "S2")])
        self.assertFalse(rows[1]["ugroup"].startswith("panel:"))
        self.assertEqual([X.is_panel(r) for r in rows], [True, False])
        self.assertTrue(X.is_panel(F.program(h.db, f"{fid}@1")) and not X.is_panel(F.program(h.db, "ex@1")))

    def test_what_the_registry_refuses_it_still_refuses(self):
        h = House(self)
        fid = h.family("px", code=CODE.replace('"panel": "sp500"', '"panel": "ftse"'))
        out = h.sync()
        self.assertEqual((out["registered"], [s["key"] for s in out["skipped"]]), (0, [f"{fid}@1"]))
        self.assertEqual([e["payload"]["cause"] for e in F.events(h.db, "register_skipped")], ["needs"])
        h.sync()
        self.assertEqual(len(F.events(h.db, "register_skipped")), 1, "once a key and cause")
        # E3's own reader takes no panel family, and its row function still refuses a structure it does not know.
        fam = h.swarm.family(fid)
        self.assertNotIn("panel", R.STRUCTURES)
        with self.assertRaises(R._Refused) as refused:
            R._row(h.swarm, fam, 1, reason=None)
        self.assertEqual(refused.exception.cause, "structure")
        self.assertEqual(R.scored_versions(h.swarm), [])
        # The chain takes the panel's route on a panel row only, and E3's on no panel row.
        good = fx.panel_family(h.swarm, "py", code=CODE, record={"status": "researching", "versions": {"1": PASSED}})
        row = X.scored(h.swarm)[-1]
        self.assertEqual(row["family"], good["id"])
        base = {"key": row["key"], "family": row["family"], "version": 1, "lane": "equity", "reason": "train_pass",
                "lineage": row["lineage"], "code": row["code"], "params": "{}", "needs": json.dumps(row["needs"]),
                "program_sha": row["sha"], "run_sha": row["run_sha"], "author": "", "created_at": h.clock(),
                "evidence": "registry", "first_close": F.first_close(h.clock()),
                "first_day": F.first_day(F.first_close(h.clock())), "registered_at": h.clock()}
        for ugroup, route, alpha in (("panel:sp500", "S2", "0.03"), ("index", "XS1", "0.03"),
                                     ("panel:sp500", "XS1", "0.12"), ("panel:sp500", "F-GS-XS", "0.12")):
            with self.assertRaises(ValueError, msg=(ugroup, route, alpha)):
                F.append_registry(h.db, {**base, "ugroup": ugroup, "route": route, "alpha_f": alpha})
        self.assertEqual(h.db.execute("SELECT COUNT(*) FROM fwd_registry").fetchone()[0], 0)

    def test_a_live_panel_instance_the_registry_does_not_hold_and_its_tags(self):
        h = House(self)
        fid = h.family("px", {})                # no version judged: nothing registered from the record
        version = h.swarm.version(fid, 1)
        live = sqlite3.connect(str(h.root / R.LIVE_DB))
        from league.equity import live as L

        live.executescript(L.SCHEMA + xbook.SCHEMA)
        live.execute(xbook.INSTANCE_KIND_DDL)
        live.execute("INSERT INTO eq_instances(id, family, version, lane, run_sha, code, params, band, max_hold, "
                     "created_at, kind) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                     (f"{fid}@1:r", fid, 1, "equity", run_sha(version), CODE, "{}", "probe", 40, h.clock(), "panel"))
        live.commit()
        live.close()
        h.swarm.set_state(fid, **{elane_xs.LOOK_KEY: {"version": 1, "at": "t", "passed": True,
                                                      "verdict": {"passed": True}, "seat": "candidate"}})
        out = h.sync()
        self.assertEqual((out["registered"], out["skipped"]), (1, []))
        row = h.row(f"{fid}@1")
        self.assertEqual((row["reason"], row["ugroup"], row["route"], row["evidence"]),
                         ("live", "panel:sp500", "XS1", "registry"))
        tags = F.tags(h.db, row["pid"])
        self.assertEqual(tags["live"][0]["value"], f"{fid}@1:r")
        self.assertIn("look_pass", tags, "a panel family's look is read under the panel's own key")
        self.assertEqual(X.look_key(h.swarm.family(fid)), elane_xs.LOOK_KEY)
        self.assertIsNone(X.look_key({"structure": "etf"}))


class TheSeries(unittest.TestCase):
    """E3's excess of a panel row IS the run's residual, and its stress excess the run's stress residual."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = synth.synthetic_panel(Path(cls.tmp.name) / "equity-daily", n_assets=40, seed=11, churn=0.3, gate=True,
                                     end=dt.date(2026, 12, 31))
        gate = mint_equity_gate_capability(root, "a test's forward run")
        cls.made = xrunner.Isolated(D.InlineDecider(), root, nice=None).forward(CODE, None, name="p", gate=gate,
                                                                                start=F.t0())

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_x_from_the_series_is_the_runs_x_and_the_stress_excess_its_x15(self):
        result = self.made.result
        found = X.series(result)
        days, x, x15 = (xresults.column(result, name) for name in ("day", "x", "x15"))
        self.assertEqual(list(found.iso), days)
        self.assertGreater(len(days), 50)
        self.assertGreater(sum(1 for v in x if v != 0.0), 40, "the invented program trades: the series is not empty")
        for i in range(len(days)):
            self.assertLessEqual(abs((found.r[i] - found.w[i] * found.b[i]) - x[i]), 1e-12, days[i])
            self.assertLessEqual(abs((found.r15[i] - found.w[i] * found.b[i]) - x15[i]), 1e-12, days[i])
        self.assertEqual(found.x, tuple(x))
        self.assertTrue(any(abs(a - b) > 1e-9 for a, b in zip(x, x15)), "the stress residual is its own series")
        self.assertEqual(found.exits, tuple(xresults.column(result, "exits")))
        self.assertEqual(found.w, tuple(xresults.column(result, "w")))
        self.assertTrue(all(b == 0.0 for w, b in zip(found.w, found.b) if w == 0.0))
        # The sum E3's checkpoint takes is the run's own.
        self.assertLessEqual(abs(math.fsum(r - w * b for r, w, b in zip(found.r, found.w, found.b))
                                 - result["summary"]["sum_x"]), 1e-10)

    def test_the_sessions_through_a_day_and_a_row_that_cannot_be_a_row(self):
        result = self.made.result
        days = xresults.column(result, "day")
        cut = X.series(result, through=days[9])
        self.assertEqual((len(cut.iso), cut.iso[-1], len(cut.days)), (10, days[9], 10))
        self.assertEqual(X.series(result, through="2000-01-01").iso, ())
        at_ = {name: xresults.DAILY.index(name) for name in xresults.DAILY}
        nan = [list(row) for row in result["daily"]]
        nan[3][at_["x"]] = float("nan")
        with self.assertRaises(ValueError):
            X.series({"daily": nan})
        bench = [list(row) for row in result["daily"]]
        bench[0][at_["w"]], bench[0][at_["bench"]] = 0.0, 0.01
        with self.assertRaises(ValueError):
            X.series({"daily": bench})


class TheRowsThatAreFinal(unittest.TestCase):
    """ROWS LAG ONE SESSION, TWINS TWO, on the real engine over a panel whose membership changes: what a run through
    P says of day P - 1 and before is what every later run says, and of day P it is not; what it decided at P - 2 and
    before is what every later run decided, and at P - 1 it is not always."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = synth.synthetic_panel(Path(cls.tmp.name) / "equity-daily", n_assets=40, seed=11, churn=0.6, gate=True,
                                     end=dt.date(2026, 12, 31))
        cls.panel = xstore.PanelStore(root, gate=mint_equity_gate_capability(root, "a test's forward runs"))
        cls.days = [d for d in cls.panel.sessions("forward") if d >= F.t0()]
        cls.runs = {}
        for day in cls.days[5:38]:
            piece = cls.panel.bars("forward", history=60, run_key="one key", start=F.t0(), end=day)
            cls.runs[day] = xrunner.run_bars(CODE, None, piece.bars, name="p")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def differing(self, read) -> dict[int, int]:
        """{lag: how many (P, a later store) pairs differ on what `read` gives for the session `lag` before P}."""
        out = {lag: 0 for lag in range(4)}
        for i in range(5, 36):
            first = self.runs[self.days[i]]
            for later in (self.runs[self.days[i + 1]], self.runs[self.days[i + 2]]):
                for lag in out:
                    day = self.days[i - lag].isoformat()
                    out[lag] += read(first, day) != read(later, day)
        return out

    def test_the_membership_does_change_inside_the_days_compared(self):
        universe = self.panel.universe()
        members = [frozenset(aid for aid, _ in universe.members(day)) for day in self.days[4:38]]
        self.assertGreaterEqual(sum(1 for a, b in zip(members, members[1:]) if a != b), 1)
        self.assertEqual((X.TWIN_LAG, X.ROW_LAG), (xconfig.MEMBER_AHEAD, xconfig.MEMBER_AHEAD - 1))

    def test_a_days_row_is_final_once_the_next_session_is_in_the_store(self):
        def row(result, day):
            return next((tuple(r[1:8]) for r in result["daily"] if r[0] == day), None)

        found = self.differing(row)
        self.assertEqual((found[1], found[2], found[3]), (0, 0, 0))
        self.assertGreater(found[0], 0, "the store's last day is NOT final: a buy filled there is not opened yet")

    def test_a_decision_is_final_once_two_later_sessions_are_in_the_store(self):
        def pick(result, day):
            return next(((p["buys"], p["sells"], p["ctx_sha"]) for p in result["picks"] if p["decided"] == day), None)

        found = self.differing(pick)
        self.assertEqual((found[2], found[3]), (0, 0))
        self.assertGreater(found[1], 0, "membership is read two sessions ahead: a decision a session old can still move")


class ThePanelNight(unittest.TestCase):
    def test_the_rows_end_a_session_before_the_stores_last_and_the_night_is_named_by_that_day(self):
        h, key, pid = registered(self)
        receipt = h.night(8)
        days = [d.isoformat() for d in h.days]
        self.assertEqual((receipt["through"], receipt["panel_through"]), (days[7], days[8]))
        self.assertEqual((receipt["programs"], receipt["new_days"], receipt["errors"], receipt["stale"],
                          receipt["data_failed"], receipt["house"]), (1, 7, 0, 0, 0, 0))
        rows = h.rows(pid)
        self.assertEqual([r["day"] for r in rows], days[1:8], "from its first day through the session before the last")
        self.assertTrue(all(r["status"] == "ok" and isinstance(r["bars"], str) and len(r["bars"]) == F.BARS_HEX
                            and r["r0"] is None for r in rows))
        self.assertEqual(len({r["bars"] for r in rows}), len(rows), "one bars hash a decision session")
        self.assertTrue(any(r["w"] > 0 for r in rows) and any(r["entries"] > 0 for r in rows), "it trades")
        night = [dict(r) for r in h.db.execute("SELECT job, through, programs, sessions, stale FROM fwd_runs")]
        self.assertEqual(night, [{"job": "forward_xs", "through": days[7], "programs": 1, "sessions": 7, "stale": 0}])
        self.assertEqual((X.JOB, X.E3_JOB), ("forward_xs", forward_shadow.JOB))
        self.assertEqual(forward_shadow.Shadow.JOB, forward_shadow.JOB)
        # A panel run has no live-like row (no minute bars exist for 500 names) and no control stands beside it.
        self.assertEqual(h.db.execute("SELECT COUNT(*) FROM fwd_ll").fetchone()[0], 0)
        self.assertEqual(h.events("no_minute"), [])
        self.assertEqual(receipt["controls"]["rows"], 0)

    def test_two_nights_give_the_same_rows_and_a_night_run_again_adds_nothing(self):
        h, key, pid = registered(self)
        h.night(8)
        first = h.rows(pid)
        again = h.night(8, write=False)
        self.assertEqual((again["programs"], again["new_days"], again["restated"], again["stale"]), (0, 0, 0, 0),
                         "written through the night's day: not due")
        self.assertEqual(h.rows(pid), first)
        second = h.night(9)
        self.assertEqual((second["new_days"], second["restated"], second["through"]), (1, 0, h.days[8].isoformat()))
        rows = h.rows(pid)
        self.assertEqual(rows[:len(first)], first, "first write stands, and the whole recompute says the same")
        self.assertEqual(rows[-1]["day"], h.days[8].isoformat())
        self.assertEqual(h.events("restated"), [])
        # The same days computed in one night on another root are the same numbers.
        other, _, other_pid = registered(self)
        other.night(9)
        self.assertEqual([(r["day"], r["r"], r["w"], r["b"], r["r15"], r["entries"], r["exits"], r["bars"]) for r in rows],
                         [(r["day"], r["r"], r["w"], r["b"], r["r15"], r["entries"], r["exits"], r["bars"])
                          for r in other.rows(other_pid)])

    def test_the_rows_are_the_engines_own_series_and_the_checkpoint_reads_the_residual(self):
        h, key, pid = registered(self)
        h.night(24)
        rows = h.rows(pid)
        self.assertEqual(len(rows), 23)
        gate = mint_equity_gate_capability(h.store_root, "the test's own run")
        run = xrunner.Isolated(D.InlineDecider(), h.store_root, nice=None).forward(CODE, {"k": 6}, name=key, gate=gate,
                                                                                   start=h.days[1])
        x = dict(zip(xresults.column(run.result, "day"), xresults.column(run.result, "x")))
        x15 = dict(zip(xresults.column(run.result, "day"), xresults.column(run.result, "x15")))
        for row in rows:
            self.assertLessEqual(abs((row["r"] - row["w"] * row["b"]) - x[row["day"]]), 1e-12, row["day"])
            self.assertLessEqual(abs((row["r15"] - row["w"] * row["b"]) - x15[row["day"]]), 1e-12, row["day"])
        (check,) = [dict(r) for r in h.db.execute("SELECT * FROM fwd_checks WHERE pid=?", (pid,))]
        first20 = [x[r["day"]] for r in rows[:20]]
        self.assertEqual((check["n"], check["day"], check["final"]), (20, rows[19]["day"], 0))
        self.assertAlmostEqual(check["t_x"], xresults.t_stat(first20), places=9)
        self.assertLessEqual(abs(check["sum_r15"] - math.fsum(r["r15"] for r in rows[:20])), 1e-12)
        self.assertIsNotNone(check["p_x"])

    def test_each_night_runs_its_own_lane(self):
        h = House(self)
        h.store(h.days[0])
        etf = e2.e2_family(h.swarm, "ex", lane="equity", agenda="trend", symbols=("XLK",), code=e2.program("XLK"),
                           record={"status": "researching", "versions": {"1": {"passed": True, "fails": [],
                                                                               "pnl_10": 1.0, "pnl_15": 1.0}}})
        fid = h.family("px")
        h.scored(fid, when=at(h.days[0], 12))
        h.sync()
        h.store(h.days[6])
        own, panel = h.e3_shadow(6), h.shadow(6, write=False)
        self.assertEqual([p.key for p in own.due()], [f"{etf['id']}@1"], "E3's night never lists a panel program")
        self.assertEqual([p.key for p in panel.due()], [f"{fid}@1"], "and the panel night never an ETF program")
        self.assertEqual((own.night_day, panel.night_day), (h.days[6].isoformat(), h.days[5].isoformat()))
        self.assertFalse(X.is_panel_night(own))
        self.assertTrue(X.is_panel_night(panel))
        receipt = own.night()
        self.assertEqual((receipt["programs"], receipt["data_failed"], receipt["errors"]), (1, 0, 0))
        self.assertEqual(h.events("data_failed"), [], "E3's engine was never handed the panel program")
        receipt = panel.night()
        self.assertEqual((receipt["programs"], receipt["errors"]), (1, 0))
        jobs = [r[0] for r in h.db.execute("SELECT job FROM fwd_runs ORDER BY run")]
        self.assertEqual(jobs, ["forward_shadow", "forward_xs"])
        # One engine id for both lanes' rows that night, and each pid has its own rows.
        self.assertEqual({r[0] for r in h.db.execute("SELECT DISTINCT engine FROM fwd_days")}, {own.engine})
        self.assertEqual(own.engine, panel.engine)

    def test_the_engine_label_names_the_xs_evidence_once_a_panel_row_exists(self):
        from league.xs import identity

        h = House(self)
        h.store(h.days[0])
        base = F.fwd_engine()
        self.assertEqual(X.engine_label(h.db, base), base, "no panel row: E3's label, unmoved")
        self.assertEqual(h.e3_shadow(0)._label(), base)
        fid = h.family("px")
        h.sync()
        label = f"{base}+xs.{identity.xs_fingerprint()[:12]}"
        self.assertEqual(X.engine_label(h.db, base), label)
        self.assertEqual(h.e3_shadow(0)._label(), label)
        self.assertEqual(h.shadow(1)._label(), label, "both nights write under one label")
        with mock.patch.object(identity, "xs_fingerprint", return_value="f" * 64):
            self.assertEqual(X.engine_label(h.db, base), f"{base}+xs.ffffffffffff", "an xs evidence change: a new series")

    def test_one_budget_a_night(self):
        h, key, pid = registered(self)
        h.store(h.days[6])
        when = at(h.days[6], 22, 5)
        self.assertEqual(X.night_budget(h.db, F.cfg(h.settings), when), 1800.0)
        h.db.execute("INSERT INTO fwd_runs(job, through, engine, started, finished, seconds) VALUES('forward_shadow', ?, 1, "
                     "?, ?, 1700.0)", (h.days[6].isoformat(), when - 4 * 3600, when - 3.5 * 3600))
        h.db.execute("INSERT INTO fwd_runs(job, through, engine, started, finished, seconds) VALUES('forward_shadow', ?, 1, "
                     "?, ?, 900.0)", (h.days[5].isoformat(), when - 28 * 3600, when - 27 * 3600))
        h.db.commit()
        self.assertEqual(X.night_budget(h.db, F.cfg(h.settings), when), 100.0, "what E3's night of that evening left")
        h.db.execute("INSERT INTO fwd_runs(job, through, engine, started, finished, seconds) VALUES('forward_xs', ?, 1, ?, "
                     "?, 400.0)", (h.days[5].isoformat(), when - 600, when - 300))
        h.db.commit()
        self.assertEqual(X.night_budget(h.db, F.cfg(h.settings), when), 0.0, "never under zero")
        # With nothing left every panel program waits (it goes first the next night) and the marker is still written.
        receipt = h.night(6, write=False)
        self.assertEqual((receipt["programs"], receipt["stale"], receipt["budget_hit"]), (0, 1, 1))
        self.assertEqual(h.rows(pid), [])
        self.assertEqual(receipt["marker"], {"instances": 0, "behind": 0})
        self.assertTrue((h.store_root / xbook.TWINS_FILE).is_file())

    def test_the_preflight_runs_the_panel_kind_and_a_failure_marks_nobody(self):
        h, key, pid = registered(self)
        asked = []

        class Recording(D.InlineDecider):
            def kind(self, kind, op, payload, **kw):
                asked.append((kind, op, payload.get("name")))
                return super().kind(kind, op, payload, **kw)

        receipt = h.night(5, decider=Recording())
        self.assertEqual(receipt["programs"], 1)
        self.assertEqual([a for a in asked if a[2] in ("forward-canary", "forward-xs-canary")],
                         [("equity", "run", "forward-canary"), ("panel", "needs", "forward-xs-canary"),
                          ("panel", "run", "forward-xs-canary")])
        self.assertIn(("panel", "run", key), asked)

        class NoPanel(D.InlineDecider):
            def kind(self, kind, op, payload, **kw):
                if kind == "panel":
                    raise D.DeciderError("the child knows no panel kind")
                return super().kind(kind, op, payload, **kw)

        before = h.db.execute("SELECT COUNT(*) FROM fwd_runs").fetchone()[0]
        with self.assertRaises(forward_shadow.NightFailed):
            h.night(6, decider=NoPanel())
        self.assertEqual(h.db.execute("SELECT COUNT(*) FROM fwd_runs").fetchone()[0], before, "no night row")
        self.assertEqual([e["day"] for e in h.events("night_failed")], [h.days[5].isoformat()])
        self.assertEqual(h.events("run_failed") + h.events("data_failed") + h.events("suspect"), [])
        self.assertEqual(len(h.rows(pid)), 4, "nobody was run")

    def test_every_run_of_a_night_reads_the_nights_one_store(self):
        # The ops child's address space is capped 500 MB above its start, and every open of the panel store maps its
        # two bar arrays again (about 120 MB at the real panel's size, held until a full collection). Opened once a
        # run, as `league.xs.runner.Isolated` opens it, the third run of a night found no room: measured at the real
        # panel's size, every program after the first two was a `data_failed`. One store a night.
        h = House(self)
        h.store(h.days[0])
        for slug in ("pa", "pb", "pc"):
            h.scored(h.family(slug, code=CODE + f"\n# {slug}\n"), when=at(h.days[0], 12))
        h.sync()
        opened = []
        real = xstore.PanelStore.__init__

        def counted(self, *args, **kwargs):
            opened.append(1)
            return real(self, *args, **kwargs)

        with mock.patch.object(xstore.PanelStore, "__init__", counted):
            receipt = h.night(6)
        self.assertEqual((receipt["programs"], receipt["data_failed"], receipt["errors"]), (3, 0, 0))
        self.assertEqual(len(opened), 1, "the canary, three programs and the bars hash: one open of the panel store")

    def test_a_program_the_child_cannot_run_is_the_retrys_and_marked_only_beside_one_that_ran(self):
        h = House(self)
        h.store(h.days[0])
        good = h.family("px")
        bad = h.family("py", code=CODE.replace("ranked.sort()", "raise RuntimeError('an invented failure')"))
        for fid in (good, bad):
            h.scored(fid, when=at(h.days[0], 12))
        h.sync()

        class Failing(D.InlineDecider):
            def kind(self, kind, op, payload, **kw):
                if kind == "panel" and op == "run" and payload.get("name") == f"{bad}@1":
                    raise D.DeciderError("the child died on this program")
                return super().kind(kind, op, payload, **kw)

        shadow = h.shadow(6, decider=Failing())
        shadow.fresh = Failing
        receipt = shadow.night()
        self.assertEqual((receipt["programs"], receipt["retried"], receipt["errors"], receipt["house"]), (1, 1, 1, 0))
        (event,) = h.events("run_failed")
        self.assertEqual((event["pid"], event["day"], event["payload"]["completed"]),
                         (int(h.row(f"{bad}@1")["pid"]), h.days[5].isoformat(), 1))
        self.assertEqual(h.rows(int(h.row(f"{bad}@1")["pid"])), [])


class TheStopRulesReadEachLanesOwnNights(unittest.TestCase):
    """E3's rules, unchanged, on the nights of the job that runs the program (rows and events invented, as E3's own
    tests write them)."""

    def setUp(self):
        self.h, self.key, self.pid = registered(self)
        etf = e2.e2_family(self.h.swarm, "ex", lane="equity", agenda="trend", symbols=("XLK",), code=e2.program("XLK"),
                           record={"status": "researching", "versions": {"1": {"passed": True, "fails": [],
                                                                               "pnl_10": 1.0, "pnl_15": 1.0}}})
        self.h.sync()
        self.etf = int(self.h.row(f"{etf['id']}@1")["pid"])
        self.engine = F.engine_id(self.h.db, "an-invented-engine", at=self.h.clock())[0]

    def night(self, job: str, index: int, marks: dict[int, str]) -> None:
        h = self.h
        through = h.days[index].isoformat()
        h.clock.t = at(h.days[index], 23)
        h.db.execute("INSERT INTO fwd_runs(job, through, engine, started, finished, seconds, programs) VALUES(?, ?, ?, ?, "
                     "?, 1.0, 1)", (job, through, self.engine, h.clock() - 60, h.clock()))
        h.db.commit()
        for pid, kind in marks.items():
            F.event(h.db, kind, pid=pid, day=through, payload={"why": "an invented night"}, at=h.clock(), once="night")

    def stopped(self) -> set[int]:
        return {int(r[0]) for r in self.h.db.execute("SELECT pid FROM fwd_tags WHERE tag='stopped'")}

    def test_three_disqualified_panel_nights_stop_the_panel_program_and_e3s_nights_say_nothing_of_it(self):
        for i in (1, 2, 3):
            self.night("forward_shadow", i, {})
        for i in (1, 2):
            self.night("forward_xs", i, {self.pid: "run_disqualified"})
        self.h.sync()
        self.assertEqual(self.stopped(), set())
        self.night("forward_xs", 3, {self.pid: "run_disqualified"})
        out = self.h.sync()
        self.assertEqual((out["stopped"], self.stopped()), (1, {self.pid}))

    def test_a_panel_night_it_completed_breaks_the_run_of_nights(self):
        h = self.h
        self.night("forward_xs", 1, {self.pid: "run_disqualified"})
        self.night("forward_xs", 2, {})
        # ...its run completed on the second panel night: its row for that night's day, written by that night.
        h.db.execute("INSERT INTO fwd_days(pid, day, engine, r, w, b, entries, exits, status, at, bars) VALUES(?, ?, ?, 0, "
                     "0, 0, 0, 0, 'ok', ?, 'x')", (self.pid, h.days[2].isoformat(), self.engine, h.clock() - 30))
        h.db.commit()
        for i in (3, 4):
            self.night("forward_xs", i, {self.pid: "run_disqualified"})
        h.sync()
        self.assertEqual(self.stopped(), set(), "disqualified, ran, disqualified, disqualified: not three running")
        self.night("forward_xs", 5, {self.pid: "run_disqualified"})
        h.sync()
        self.assertEqual(self.stopped(), {self.pid})

    def test_a_panel_nights_end_is_no_end_of_e3s_night(self):
        # An ETF program left stale on E3's night gets that day's row the NEXT evening. Were the two jobs' nights
        # read as one, the panel night's later end would make that row a run completed on the first night.
        h = self.h
        self.night("forward_shadow", 1, {self.etf: "run_disqualified"})
        self.night("forward_shadow", 2, {})                                       # stale that night: no row, no mark
        self.night("forward_xs", 2, {})
        h.clock.t = at(h.days[3], 19)
        h.db.execute("INSERT INTO fwd_days(pid, day, engine, r, w, b, entries, exits, status, at, bars) VALUES(?, ?, ?, 0, "
                     "0, 0, 0, 0, 'disqualified', ?, 'x')", (self.etf, h.days[2].isoformat(), self.engine, h.clock() - 30))
        h.db.commit()
        self.night("forward_shadow", 3, {self.etf: "run_disqualified"})
        self.night("forward_xs", 3, {})
        self.night("forward_shadow", 4, {self.etf: "run_disqualified"})
        h.sync()
        self.assertEqual(self.stopped(), {self.etf}, "its own last three attempted nights were all disqualified")


class TheMorningMarks(unittest.TestCase):
    def book(self, h: House, fid: str, audits: dict[str, str | None]) -> None:
        from league.equity import live as L

        db = sqlite3.connect(str(h.root / R.LIVE_DB))
        db.executescript(L.SCHEMA + xbook.SCHEMA)
        db.execute(xbook.INSTANCE_KIND_DDL)
        db.execute("INSERT INTO eq_instances(id, family, version, lane, run_sha, code, params, band, max_hold, created_at, "
                   "kind) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                   (f"{fid}@1:r", fid, 1, "equity", run_sha(h.swarm.version(fid, 1)), CODE, "{}", "probe", 40,
                    at(h.days[2], 16, 30), "panel"))
        for day, audit in audits.items():
            db.execute("INSERT INTO eq_rebalances(instance, family, version, decided_day, exec_day, at, called, targets, "
                       "n_names, n_sells, n_buys, n_skipped, audit, status, created_at) VALUES(?,?,1,?,?,'open',1,'[]',0,0,"
                       "0,0,?,'planned',1.0)", (f"{fid}@1:r", fid, day, day, audit))
        db.commit()
        db.close()

    def test_a_mismatched_panel_decision_marks_that_day_of_its_program_once(self):
        h, key, pid = registered(self)
        days = [d.isoformat() for d in h.days]
        self.book(h, key.split("@")[0], {days[3]: "ok", days[4]: "mismatch", days[0]: "mismatch", days[5]: None})
        self.assertEqual(X.audit_marks(h.db, h.root / R.LIVE_DB, now=h.clock()), 1,
                         "the day before its first day is no forward day of it")
        (event,) = h.events("audit_mismatch")
        self.assertEqual((event["pid"], event["day"], event["payload"]["instance"]), (pid, days[4], f"{key}:r"))
        self.assertEqual(X.audit_marks(h.db, h.root / R.LIVE_DB, now=h.clock()), 0, "once a (pid, day)")
        # The day leaves the counted days; its row stays. The panel night makes the mark up before any checkpoint.
        receipt = h.night(8)
        self.assertEqual(receipt["marks"], 0)
        counted = [r["day"] for r in F.counted_days(h.db, pid)]
        self.assertEqual(counted, [d for d in days[1:8] if d != days[4]])
        self.assertEqual(len(h.rows(pid)), 7)

    def test_the_morning_job_writes_them_and_an_etf_instance_is_none_of_theirs(self):
        from league.ops import forward_audit

        h, key, pid = registered(self)
        self.book(h, key.split("@")[0], {h.days[3].isoformat(): "mismatch"})
        (h.root / "swarm.json").write_text(json.dumps(h.settings))
        ctx = Context("forward_audit", root=h.root, due_at=h.clock(), clock=h.clock, config={})
        out = forward_audit.run(ctx)
        self.assertEqual((out["marked"], out["marks"], out["chain_ok"]), (1, "ok", True))
        self.assertEqual(ctx.alerts, [])
        self.assertEqual(X.audit_marks(h.db, h.root / "absent.sqlite", now=h.clock()), 0)


class TheReportReadsAPanelProgramInItsOwnGroups(unittest.TestCase):
    def test_the_panels_groups_and_the_replay_multiples_numerator(self):
        h = House(self)
        h.store(h.days[0])
        etf = e2.e2_family(h.swarm, "ex", lane="equity", agenda="trend", symbols=("XLK",), code=e2.program("XLK"),
                           record={"status": "researching", "versions": {"1": {"passed": True, "fails": [],
                                                                               "pnl_10": 1.0, "pnl_15": 1.0}}})
        fid = h.family("px")
        h.scored(fid, when=at(h.days[0], 12))
        h.swarm.event("swarm.elane", etf["id"], {"pass": "scored", "version": 1, "sha": h.swarm.version("ex", 1)["sha"],
                                                 "bar_passed": True})
        h.sync()
        self.assertEqual([r["grp"] for r in forward_report._group_rows(h.db, h.days[0].isoformat())],
                         ["look_fail", "look_pass", "seed", "train_fail", "train_pass"],
                         "no panel row had a forward day yet: E3's groups, as they were")
        h.store(h.days[6])
        h.e3_shadow(6).night()
        h.night(6, write=False)
        day = h.days[4].isoformat()
        groups = {r["grp"]: r for r in forward_report._group_rows(h.db, day)}
        self.assertEqual(sorted(groups), sorted(["look_fail", "look_pass", "seed", "train_fail", "train_pass", *X.GROUPS]))
        self.assertEqual((groups["train_pass"]["n"], groups["train_pass"]["ugroups"]), (1, "sectors"))
        self.assertEqual((groups["xs:train_pass"]["n"], groups["xs:train_pass"]["ugroups"]), (1, "panel:sp500"))
        self.assertEqual([groups[name]["n"] for name in ("xs:train_fail", "xs:look_pass", "xs:look_fail")], [0, 0, 0])
        # No pair of the RC reads a panel group (no panel control exists), and E3's pairs do not see the panel's pid.
        self.assertFalse([p for p in forward_report.rc_pairs(h.db, day) if "xs:" in p["a"] or "xs:" in p["b"]])
        self.assertEqual((X.group({"ugroup": "panel:sp500"}, "look_pass"), X.group({"ugroup": "sectors"}, "look_pass")),
                         ("xs:look_pass", "look_pass"))
        # A panel family's Train runs are replays of the same years: the multiple's numerator counts them.
        before = forward_report.sim_program_years(h.root, h.db, day)
        h.swarm.add_run(fid, 1, {"status": "ok", "summary": {"days": 252}, "trials": 1, "run_id": "r1"}, window="train",
                        stress=1.0, purpose="elane_xs_train")
        self.assertAlmostEqual(forward_report.sim_program_years(h.root, h.db, day) - before, 1.0, places=6)


class TheMarkerCarriesNoOutcome(unittest.TestCase):
    """SEAL X14, the forward record's half: `xs-twins.json` holds instance ids and days only, and two forward stores
    that differ in every agreement bit and every figure give the same marker."""

    def book(self, h: House, *instances: tuple[str, float, float | None]) -> None:
        from league.equity import live as L

        db = sqlite3.connect(str(h.root / R.LIVE_DB))
        db.executescript(L.SCHEMA + xbook.SCHEMA)
        db.execute(xbook.INSTANCE_KIND_DDL)
        for iid, created, retired in instances:
            fid = iid.split("@")[0]
            db.execute("INSERT INTO eq_instances(id, family, version, lane, run_sha, code, params, band, max_hold, "
                       "created_at, retired_at, kind) VALUES(?,?,1,'equity','sha',?,'{}','probe',40,?,?,?)",
                       (iid, fid, CODE, created, retired, "equity" if fid == "etf" else "panel"))
        db.commit()
        db.close()

    def world(self, agree: int, cause: str | None, keys: str, figure: float) -> tuple[House, bytes]:
        h = House(self)
        h.store(h.days[10])
        h.clock.t = at(h.days[10], 22, 5)
        self.book(h, ("px@1:r", at(h.days[2], 16, 30), None), ("py@1:r", at(h.days[9], 16, 30), None),
                  ("pz@1:r", at(h.days[2], 16, 30), at(h.days[5], 16, 30)), ("etf@1:r", at(h.days[2], 16, 30), None))
        for day in h.days[2:7]:
            h.db.execute("INSERT INTO fwd_twins(instance, day, pid, live_keys, shadow_keys, agree, why, at, live_bars, "
                         "shadow_bars, cause) VALUES('px@1:r', ?, 1, ?, ?, ?, NULL, 1.0, 'aa', 'bb', ?)",
                         (day.isoformat(), keys, keys[::-1], agree, cause))
            h.db.execute("INSERT INTO fwd_days(pid, day, engine, r, w, b, r15, entries, exits, status, at, bars) VALUES(1, "
                         "?, 1, ?, ?, ?, ?, 1, 1, 'ok', 1.0, 'h')", (day.isoformat(), figure, figure, figure, figure))
        F.kv_put(h.db, X.BESIDE_KEY, {"px@1:r": {"sum_x": figure, "t_x": figure}})
        h.db.commit()
        shadow = X.panel_shadow(h.root, h.db, decider=h.decider(), settings=h.settings, clock=h.clock)
        self.assertEqual(shadow.mark(), {"instances": 2, "behind": 1})
        return h, (h.store_root / xbook.TWINS_FILE).read_bytes()

    def test_two_forward_stores_that_differ_in_every_agreement_bit_and_figure_give_the_same_marker(self):
        h, one = self.world(1, None, '["B|ZQAA|open|0.2000"]', 0.0123)
        _, two = self.world(0, "program", '["S|ZQZZ|close|2026-10-13", "B|ZQAB|open|0.1000"]', -0.0456)
        self.assertEqual(one, two)
        doc = json.loads(one)
        days = [d.isoformat() for d in h.days]
        self.assertEqual(doc, {"version": xbook.TWINS_VERSION, "through": days[10], "at": doc["at"], "instances": {
            "px@1:r": {"due": days[8], "last": days[6]},      # behind: its last row is two sessions short of its due day
            "py@1:r": {"due": None, "last": None}}},          # too young for a row yet
            "the alive panel instances alone: no retired one, no ETF instance")
        self.assertEqual(tuple(doc), ("at", "instances", "through", "version"))
        self.assertEqual(set(doc), set(X.MARKER_KEYS))

    def test_the_file_holds_instance_ids_and_days_and_nothing_else(self):
        h, raw = self.world(0, "bars", '["B|ZQAA|open|0.2000"]', 0.5)
        doc = json.loads(raw)
        text = raw.decode()
        for word in ("ZQ", "agree", "cause", "bars", "keys", "0.5", "sum_x", "t_x", "B|", "S|", "pid"):
            self.assertNotIn(word, text, word)
        for key, row in doc["instances"].items():
            self.assertRegex(key, r"^p[xy]@1:r$")
            self.assertEqual(tuple(row), X.MARKER_ROW)
            for value in row.values():
                self.assertTrue(value is None or dt.date.fromisoformat(value))
        self.assertEqual((h.store_root / xbook.TWINS_FILE).stat().st_mode & 0o777, 0o600)

    def test_the_writer_cuts_a_row_to_its_two_days_and_refuses_what_is_no_day(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = X.write_marker(tmp, {"a@1:r": {"due": "2026-10-13", "last": None, "agree": 0, "gap_bp": 9.5,
                                                  "symbols": ["ZQAA"]}}, through="2026-10-14", at="2026-10-15T02:00:00Z")
            self.assertEqual(json.loads(path.read_text()), {
                "version": "xs-twins-1", "through": "2026-10-14", "at": "2026-10-15T02:00:00Z",
                "instances": {"a@1:r": {"due": "2026-10-13", "last": None}}})
            for bad in ({"a": {"due": "0.25", "last": None}}, {"a": {"due": None, "last": "ZQAA"}},
                        {"a": {"due": 1, "last": None}}):
                with self.assertRaises(ValueError):
                    X.write_marker(tmp, bad, through="2026-10-14", at="t")
            with self.assertRaises(ValueError):
                X.write_marker(tmp, {}, through=None, at="t")

    def test_the_lane_reads_it_and_no_module_of_the_swarm_names_the_forward_store(self):
        h, _ = self.world(1, None, "[]", 0.0)
        through = h.days[10]
        self.assertEqual(elane_xs._twins_ready(h.root, through, h.days[9]),
                         "the shadow twin of px@1:r is more than one session behind")
        h.db.execute("INSERT INTO fwd_twins(instance, day, pid, live_keys, shadow_keys, agree, at) VALUES('px@1:r', ?, 1, "
                     "'[]', '[]', 1, 1.0)", (h.days[8].isoformat(),))
        h.db.commit()
        X.panel_shadow(h.root, h.db, decider=h.decider(), settings=h.settings, clock=h.clock).mark()
        self.assertIsNone(elane_xs._twins_ready(h.root, through, h.days[9]))
        source = (Path(elane_xs.__file__)).read_text()
        self.assertNotIn("forward_xs", source)
        self.assertNotIn(F.DB, source)


class TheAlarms(unittest.TestCase):
    def setUp(self):
        self.h = House(self)
        self.h.store(self.h.days[10])
        self.h.settings["elane"]["panel"]["mode"] = "live"
        self.now = at(self.h.days[11], 8, 55)

    def alarms(self, since: float = 0.0, settings=None) -> list[dict]:
        return X.alarms(self.h.db, self.h.root, now=self.now, since=since,
                        settings=self.h.settings if settings is None else settings)

    def marker(self, through: dt.date, **instances) -> None:
        X.write_marker(self.h.store_root, instances, through=through.isoformat(), at="2026-10-27T02:00:00Z")

    def test_the_twin_marker_behind(self):
        h = self.h
        (missing,) = self.alarms()
        self.assertEqual((missing["id"], missing["level"], missing["new"]), ("FX1", "warning", True))
        self.assertIn("no twin marker", missing["text"])
        self.marker(h.days[10])
        self.assertEqual(self.alarms(), [])
        self.marker(h.days[9])
        (one,) = self.alarms()
        self.assertTrue(one["text"].startswith("FX1 marker: "))
        self.assertIn(f"through {h.days[9].isoformat()} and the panel store through {h.days[10].isoformat()} (1 sessions "
                      "behind)", one["text"])
        self.marker(h.days[7])
        self.assertIn("(3 sessions behind)", self.alarms()[0]["text"])
        self.marker(h.days[10], **{"px@1:r": {"due": h.days[8].isoformat(), "last": h.days[7].isoformat()},
                                   "py@1:r": {"due": h.days[8].isoformat(), "last": h.days[8].isoformat()},
                                   "pz@1:r": {"due": None, "last": None}})
        (behind,) = self.alarms()
        self.assertTrue(behind["text"].startswith("FX1 instance px@1:r: its shadow twin is behind"))

    def twin_row(self, instance: str, day: dt.date, agree: int | None, cause: str | None, written: float) -> None:
        self.h.db.execute("INSERT INTO fwd_twins(instance, day, pid, live_keys, shadow_keys, agree, why, at, cause) "
                          "VALUES(?, ?, ?, '[]', '[]', ?, NULL, ?, ?)",
                          (instance, day.isoformat(), self.pid, agree, written, cause))
        self.h.db.commit()

    def test_a_rebalance_session_that_disagrees_is_told_and_a_hold_day_is_not(self):
        h = self.h
        fid = h.family("px")
        h.sync()
        self.pid = int(h.row(f"{fid}@1")["pid"])
        self.marker(h.days[10])
        called = [d for d in h.days[:12] if xconfig.decision_due(d, "weekly", 0)]
        hold = [d for d in h.days[:12] if not xconfig.decision_due(d, "weekly", 0)]
        self.twin_row("px@1:r", called[0], 0, "bars", self.now - 3600)
        self.twin_row("px@1:r", called[1], 1, None, self.now - 3600)
        self.twin_row("px@1:r", hold[0], 0, "unknown", self.now - 3600)
        self.twin_row("px@1:r", hold[1], None, None, self.now - 3600)
        (told,) = self.alarms(since=self.now - 86400)
        self.assertEqual((told["id"], told["level"]), ("FX2", "warning"))
        self.assertTrue(told["text"].startswith(f"FX2 instance px@1:r {called[0].isoformat()}: "))
        self.assertIn("(cause: bars)", told["text"])
        self.assertEqual(self.alarms(since=self.now - 60), [], "told when its row is written, not night after night")
        self.assertEqual(X.rebalance_agreement([{"day": d.isoformat(), "agree": a} for d, a in
                                                ((called[0], 0), (called[1], 1), (hold[0], 0), (hold[1], None))], NEEDS),
                         {"sessions": 2, "agreed": 1, "disagreed": [called[0].isoformat()], "unreadable": 0})
        self.assertEqual(X.rebalance_agreement([], None)["sessions"], None)

    def test_panel_programs_left_stale_two_panel_nights_running(self):
        h = self.h
        self.marker(h.days[10])
        for job, index, stale in (("forward_xs", 7, 3), ("forward_shadow", 8, 9), ("forward_shadow", 9, 9)):
            h.db.execute("INSERT INTO fwd_runs(job, through, engine, started, finished, seconds, stale) VALUES(?, ?, 1, 1.0, "
                         "2.0, 1.0, ?)", (job, h.days[index].isoformat(), stale))
        h.db.commit()
        self.assertEqual(self.alarms(), [], "one stale panel night; E3's own nights are FW2's")
        h.db.execute("INSERT INTO fwd_runs(job, through, engine, started, finished, seconds, stale) VALUES('forward_xs', ?, "
                     "1, 3.0, 4.0, 1.0, 5)", (h.days[8].isoformat(),))
        h.db.commit()
        (stale,) = self.alarms()
        self.assertEqual(stale["id"], "FX3")
        self.assertIn(f"({h.days[7].isoformat()}: 3, {h.days[8].isoformat()}: 5)", stale["text"])
        # ...and E3's FW2 reads E3's own two nights, never the panel's.
        (fw2,) = forward_report._backlog(h.db)
        self.assertIn(f"({h.days[8].isoformat()}: 9, {h.days[9].isoformat()}: 9)", fw2["text"])

    def test_each_follows_its_two_switches_and_every_text_holds_ids_counts_and_dates_only(self):
        h = self.h
        fid = h.family("px")
        h.sync()
        self.pid = int(h.row(f"{fid}@1")["pid"])
        self.marker(h.days[8], **{"px@1:r": {"due": h.days[8].isoformat(), "last": None}})
        called = [d for d in h.days[:12] if xconfig.decision_due(d, "weekly", 0)]
        self.twin_row("px@1:r", called[0], 0, "program", self.now - 60)
        for index, stale in ((7, 3), (8, 5)):
            h.db.execute("INSERT INTO fwd_runs(job, through, engine, started, finished, seconds, stale) VALUES('forward_xs', "
                         "?, 1, 1.0, 2.0, 1.0, ?)", (h.days[index].isoformat(), stale))
        h.db.commit()
        found = self.alarms()
        self.assertEqual(sorted({a["id"] for a in found}), sorted(X.ALARMS))
        for alarm in found:
            self.assertEqual(set(alarm), {"id", "level", "text", "new"})
            self.assertEqual(alarm["level"], X.ALARMS[alarm["id"]])
            self.assertTrue(alarm["text"].startswith(alarm["id"]))
            self.assertTrue(forward_report.text_ok(alarm["text"]), alarm["text"])
            self.assertNotIn("ZQ", alarm["text"])
        off_panel = {"elane": {**h.settings["elane"], "panel": {"mode": "off"}}}
        off_forward = {"elane": {**h.settings["elane"], "forward": {"mode": "off"}}}
        for alarm in X.ALARMS:
            self.assertTrue(X.raised(alarm, h.settings) and forward_report.raised(alarm, h.settings))
            self.assertFalse(X.raised(alarm, off_panel) or forward_report.raised(alarm, off_panel))
            self.assertFalse(X.raised(alarm, off_forward) or forward_report.raised(alarm, off_forward))
        self.assertFalse(forward_report.raised("FX9", h.settings))
        self.assertEqual(self.alarms(settings=off_panel) + self.alarms(settings=off_forward), [])
        # The forward report carries them, and hands them to the dlane report by their own switches.
        doc = forward_report.section(h.root, now=self.now, settings=h.settings)
        self.assertEqual(sorted({a["id"] for a in doc["alarms"] if a["id"] in X.ALARMS}), sorted(X.ALARMS))
        from league.ops.context import write_json

        write_json(h.root / forward_report.FILE, doc)
        read = forward_report.alarms(h.root, now=self.now, settings=h.settings)
        self.assertEqual(sorted({a["id"] for a in read if a["id"][:2] == "FX"}), sorted(X.ALARMS))
        self.assertEqual([a for a in forward_report.alarms(h.root, now=self.now, settings=off_panel) if a["id"][:2] == "FX"],
                         [])
        self.assertEqual([a["id"] for a in forward_report.section(h.root, now=self.now, settings=off_panel)["alarms"]
                          if a["id"][:2] == "FX"], [])

    def test_an_alarm_that_cannot_be_read_says_so_and_costs_no_other(self):
        self.marker(self.h.days[9])
        with mock.patch.object(X, "_stale_rows", side_effect=sqlite3.OperationalError("locked")):
            found = self.alarms()
        self.assertEqual([(a["id"], a["level"]) for a in found], [("FX1", "warning"), ("FX3", "info")])
        self.assertIn("could not be read (OperationalError)", found[1]["text"])


class WithEveryModeOff(unittest.TestCase):
    """Nothing runs, nothing is written."""

    def ctx(self, root: Path, settings: dict, when: float) -> Context:
        (root / "swarm.json").write_text(json.dumps(settings))
        return Context("forward_xs", root=root, due_at=when, clock=lambda: when, config={})

    def tree(self, root: Path) -> list[str]:
        return sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file())

    def test_the_job_is_skipped_before_a_store_a_child_or_a_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            days = sessions_from(F.t0(), 12)
            synth.synthetic_panel(root / "equity-daily", n_assets=20, seed=3, churn=0.0, gate=True, end=END, as_of=days[8])
            before = self.tree(root)
            evening = at(days[8], 22, 5)
            off = {"elane": {"mode": "gate", "panel": {"mode": "off"}, "forward": {"mode": "record"}}}
            no_record = {"elane": {"mode": "gate", "panel": {"mode": "live"}, "forward": {"mode": "off"}}}
            on = {"elane": {"mode": "gate", "universe": ["SPY"], "panel": {"mode": "train"}, "forward": {"mode": "record"}}}
            with mock.patch.object(forward_shadow, "_decider", side_effect=AssertionError("a child with a switch off")), \
                    mock.patch.object(F, "open_db", side_effect=AssertionError("the forward store was opened")), \
                    mock.patch.object(X, "panel_shadow", side_effect=AssertionError("a night with a switch off")):
                self.assertEqual(X.run(self.ctx(root, off, evening)),
                                 {"status": "skipped", "why": "the panel lane is off (elane.panel.mode)"})
                self.assertEqual(X.run(self.ctx(root, no_record, evening)),
                                 {"status": "skipped", "why": "elane.forward.mode is off"})
                self.assertEqual(X.run(self.ctx(root, {}, evening))["status"], "skipped", "the code defaults: off")
                self.assertEqual(X.run(self.ctx(root, on, at(days[9], 11)))["status"], "skipped",
                                 "inside a session nothing of the panel runs on the one core")
                empty = root / "empty"
                empty.mkdir()
                self.assertEqual(X.run(self.ctx(empty, on, evening)),
                                 {"status": "skipped", "why": "no panel store yet: no panel forward day"})
            self.assertEqual([p for p in self.tree(root) if p not in ("swarm.json", "empty/swarm.json")], before)
            self.assertFalse((root / F.DB).exists() or (root / "equity-daily" / xbook.TWINS_FILE).exists())

    def test_with_no_panel_row_e3s_night_is_what_it_was(self):
        h = House(self)
        h.store(h.days[0])
        etf = e2.e2_family(h.swarm, "ex", lane="equity", agenda="trend", symbols=("XLK",), code=e2.program("XLK"),
                           record={"status": "researching", "versions": {"1": {"passed": True, "fails": [],
                                                                               "pnl_10": 1.0, "pnl_15": 1.0}}})
        h.swarm.event("swarm.elane", etf["id"], {"pass": "scored", "version": 1, "sha": h.swarm.version("ex", 1)["sha"],
                                                 "bar_passed": True})
        h.settings["elane"]["panel"]["mode"] = "off"
        h.sync(at(h.days[0], 15))
        h.store(h.days[4])
        shadow = h.e3_shadow(4)
        with mock.patch.object(X, "twin", side_effect=AssertionError("a panel twin with no panel instance")), \
                mock.patch.object(X, "scored_rows", wraps=X.scored_rows) as asked:
            receipt = shadow.night()
        self.assertEqual(asked.call_count, 1, "the sync asks the panel's reader, which finds no panel family")
        self.assertEqual((receipt["programs"], receipt["errors"], receipt["new_days"]), (1, 0, 4))
        self.assertEqual([r[0] for r in h.db.execute("SELECT label FROM fwd_engines")], [F.fwd_engine()])
        self.assertEqual([r[0] for r in h.db.execute("SELECT DISTINCT job FROM fwd_runs")], ["forward_shadow"])
        self.assertFalse((h.store_root / xbook.TWINS_FILE).exists(), "E3's night writes no marker")
        groups = [r["grp"] for r in forward_report._group_rows(h.db, h.days[3].isoformat())]
        self.assertFalse([g for g in groups if g.startswith("xs:")])
        self.assertFalse(X.registered(h.db))


class TheJob(unittest.TestCase):
    def test_a_night_of_the_job_and_its_receipt(self):
        h, key, pid = registered(self)
        h.store(h.days[7])
        (h.root / "swarm.json").write_text(json.dumps(h.settings))
        when = at(h.days[7], 22, 5)
        ctx = Context("forward_xs", root=h.root, due_at=when, clock=lambda: when, config={})
        made = []

        def child(root):
            made.append(D.InlineDecider())
            return made[-1]

        with mock.patch.object(forward_shadow, "_decider", child):
            receipt = X.run(ctx)
        self.assertEqual((receipt["through"], receipt["panel_through"], receipt["programs"], receipt["new_days"],
                          receipt["marker"]), (h.days[6].isoformat(), h.days[7].isoformat(), 1, 6,
                                               {"instances": 0, "behind": 0}))
        self.assertEqual(ctx.alerts, [])
        self.assertEqual(len(made), 1, "one child, the forward job's own kind")
        doc = json.loads((h.store_root / xbook.TWINS_FILE).read_text())
        self.assertEqual((doc["version"], doc["through"], doc["instances"]),
                         (xbook.TWINS_VERSION, h.days[7].isoformat(), {}))
        self.assertEqual(doc["at"], dt.datetime.fromtimestamp(when, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
        # A preflight that fails is a failed receipt: nobody run, nobody marked, no marker moved.
        class Dead(D.InlineDecider):
            def ping(self):
                return {"ok": False}

        h.store(h.days[8])
        later = at(h.days[8], 22, 5)
        ctx = Context("forward_xs", root=h.root, due_at=later, clock=lambda: later, config={})
        with mock.patch.object(forward_shadow, "_decider", lambda root: Dead()):
            out = X.run(ctx)
        self.assertEqual(out["status"], "failed")
        self.assertIn("the preflight failed", out["error"])
        self.assertEqual(json.loads((h.store_root / xbook.TWINS_FILE).read_text())["through"], h.days[7].isoformat(),
                         "the marker stays where the last whole night left it: the lane reads it as behind")

    def test_the_registry_row_of_the_job(self):
        from league.ops import registry
        from league.ops import schedule as S

        jobs = registry.by_name()
        job = jobs["forward_xs"]
        self.assertEqual((job.module, job.triggers, job.in_pause, job.paid, job.retry),
                         ("league.ops.forward_xs", (S.after("equity_panel"),), True, False, True))
        shadow = jobs["forward_shadow"]
        self.assertEqual((job.cpu, job.wall, job.grace), (shadow.cpu, shadow.wall, shadow.grace))
        self.assertGreaterEqual(jobs["grant"].grace, job.wall + 300)
        self.assertTrue(callable(X.run))
        self.assertEqual((X.TAG, X.KIND, X.STORE_DIR), (xbook.TAG, xbook.KIND, elane_xs.STORE_DIR))
        self.assertEqual(X.PANEL_MANIFEST, elane_xs.PANEL_MANIFEST)


if __name__ == "__main__":
    unittest.main()
