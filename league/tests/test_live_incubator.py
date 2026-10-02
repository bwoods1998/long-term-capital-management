"""The incubator (release B, Oct 1, 2026; `league/live/incubator.py`): one lot of real money for a family whose practice
cohort passed its pre-registered first look, within the owner's caps (`options_money.incubator`), never evidence and
never a promotion. With the fakes of `live_fakes`: real money on, an active grant, the paper proof passed, and a
practice cohort written straight into `observe.sqlite` under the running evaluator."""

from __future__ import annotations

import copy
import datetime as dt
import json
import os
import random
import re
import sqlite3
import unittest
from decimal import Decimal as D
from pathlib import Path
from unittest import mock

from league.tests.test_live_step import HAVE, LiveCase

if HAVE:
    from league.constitution import CONSTITUTION
    from league.live import calibration as C
    from league.live import incubator as INC
    from league.live import money as M
    from league.live.decider import InlineDecider
    from league.live.families import MemoryFamilies, _entry_matches
    from league.live.observe import ObserveStore, cohort_rows, practice_record
    from league.live.real import RealBook, incubator_tally, is_incubator
    from league.live.state import LiveState
    from league.live.step import Instance, OptionsLive, _rank
    from league.tests.live_fakes import MONDAY, VERTICAL, Grant, at, family

REPO = Path(__file__).resolve().parents[2]
TUESDAY = dt.date(2026, 9, 29)

#: The practised program: a $1 SPY call vertical `atm` strikes out of the money, a day out, asking for `qty` (the
#: incubator sends one lot), closed after `hold` minutes.
PROGRAM = '''
NEEDS = {"roots": ["SPY"], "dte": [0, 3], "band": 0.03, "cadence": 1, "history": 0, "start": 571, "end": 958}
PARAMS = {"at": 571, "opens": 1, "hold": 3, "atm": 4, "width": 1.0, "dte": 1, "qty": 2, "right": "C", "type": "debit_vertical"}
STATE = {"opened": 0}

def decide(ctx):
    p = ctx.params
    out = []
    for pos in ctx.positions:
        if pos["held_minutes"] >= p["hold"]:
            out.append({"close": pos["id"], "limit": "natural", "note": "incubator test close"})
    if STATE["opened"] < p["opens"] and ctx.minute >= p["at"] and not ctx.orders and not ctx.positions:
        STATE["opened"] += 1
        if p["type"] == "long_call":
            out.append({"open": "long_call", "root": "SPY", "qty": p["qty"], "limit": "natural", "tag": "inc",
                        "legs": [{"side": "long", "right": "C", "dte": p["dte"], "atm": p["atm"]}]})
        else:
            out.append({"open": "debit_vertical", "root": "SPY", "qty": p["qty"], "limit": "natural", "tag": "inc",
                        "note": "incubator test open",
                        "legs": [{"side": "long", "right": p["right"], "dte": p["dte"], "atm": p["atm"]},
                                 {"side": "short", "right": p["right"], "rel": 0, "offset": p["width"]}]})
    return out
'''
PARAMS = {"at": 571, "opens": 1, "hold": 3, "atm": 4, "width": 1.0, "dte": 1, "qty": 2, "right": "C", "type": "debit_vertical"}
#: Three sessions before MONDAY (Sept 28, 2026): the default cohort's practice.
DAYS = ("2026-09-23", "2026-09-24", "2026-09-25")


def table(**incubator) -> "M.Table":
    c = copy.deepcopy(CONSTITUTION)
    c["options_money"]["incubator"].update(incubator)
    return M.Table.from_constitution(c)


def winning(n: int = 10, *, pnl: float = 5.0, max_loss: float = 30.0, days=DAYS, forced: bool = False) -> list:
    return [(days[i % len(days)], pnl, max_loss, forced) for i in range(n)]


class Base(LiveCase):
    """An `OptionsLive` with the fakes, and the helpers that write a practice cohort."""

    def setUp(self):
        super().setUp()
        self.switch(True)

    def switch(self, on, **more):
        (self.root / "swarm.json").write_text(json.dumps({"live": {"calibration": False, "observe": False,
                                                                    "house_test": False, "incubator": on, **more}}))

    def make(self, rows=(), *, incubated=(), observed=(), real_money=True, config=None, table=None):
        self.families = MemoryFamilies(rows, observed, incubated)
        self.live = OptionsLive(self.root, market=self.market, real=self.venue, paper=self.paper, families=self.families,
                                grant=self.grant, kill_switch=lambda: self.killed, decider=InlineDecider(), table=table,
                                config={"require_paper_proof": False, **(config or {})}, real_money=real_money,
                                performance={"start_at": "2026-09-26T06:25:30.000Z", "start_equity": "481.65"},
                                clock=self.clock, record=self.ledger, alert=lambda lvl, text: self.alerts.append((lvl, text)),
                                notify=self.notices.append)
        return self.live

    def restart(self):
        families = self.families
        self.live.close()
        self.live.state.close()
        self.live = OptionsLive(self.root, market=self.market, real=self.venue, paper=self.paper, families=families,
                                grant=self.grant, kill_switch=lambda: self.killed, decider=InlineDecider(),
                                table=self.live.table, config={"require_paper_proof": False}, real_money=True,
                                performance={"start_at": "2026-09-26T06:25:30.000Z", "start_equity": "481.65"},
                                clock=self.clock, record=self.ledger, alert=lambda lvl, text: self.alerts.append((lvl, text)),
                                notify=self.notices.append)
        return self.live

    def snapshot(self, fid="fam", n=1, *, code=PROGRAM, params=None, structure="debit_vertical", evaluator=None,
                 run_sha=None) -> dict:
        return {"family": fid, "version": n, "code": code, "params": dict(PARAMS if params is None else params),
                "run_sha": run_sha or f"sha-{fid}-{n}", "structure": structure, "roots": ["SPY"], "needs_roots": ["SPY"],
                "band": "gym", "observe": True, "tier": "train", "practice_frozen": True,
                "practice_evaluator": evaluator or self.live.observe_store.evaluator}

    def cohort(self, fid="fam", n=1, *, trades=None, first_day=DAYS[0], sessions=3, last_day=DAYS[-1], due=100, made=100,
               open_mark=0.0, status="active", reason=None, practice_first=None, trade_evaluator=None, qty=1,
               fees=1.3, incubate=True, facts_sha=None, facts_structure=None, **snap) -> dict:
        """A practice cohort of (fid, n) under the running evaluator: its snapshot, its practice row and its closed trades
        [(exit day, pnl, max loss, forced)], and (`incubate`) the swarm's facts row for it."""
        store = self.live.observe_store
        snapshot = self.snapshot(fid, n, **snap)
        db = store._connect()
        db.execute("INSERT INTO cohorts(family, version, admitted_at, first_day, snapshot, status, reason) VALUES(?,?,?,?,?,?,?)",
                   (fid, n, 1.0, first_day, json.dumps(snapshot, sort_keys=True), status, reason))
        db.execute("INSERT INTO practice(family, version, tier, lineage, structure, roots, capital, first_at, first_day, last_at, "
                   "last_day, sessions, minutes, decisions_due, decisions_made, account, open_mark_pnl, status) "
                   "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   (fid, n, "train", fid, snapshot["structure"], '["SPY"]', 10000.0, 1.0, practice_first or first_day, 2.0,
                    last_day, sessions, 390 * sessions, due, made, "a", open_mark, "live"))
        for i, (day, pnl, max_loss, forced) in enumerate(winning() if trades is None else trades):
            body = {"id": i, "qty": qty, "fees": fees, "max_loss": max_loss, "pnl": pnl, "exit_day": day, "type": "debit_vertical"}
            db.execute("INSERT INTO trades(instance, account, family, version, trade_id, day, pnl, max_loss, recorded_at, body, "
                       "exit_day, reason, forced, evaluator) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                       (f"{fid}@{n}:o", "a", fid, n, str(i), day, pnl, max_loss, 1.0, json.dumps(body), day, "program",
                        int(forced), trade_evaluator or store.evaluator))
        if incubate:
            self.families.incubated[(fid, n)] = {"family": fid, "version": n, "run_sha": facts_sha or snapshot["run_sha"],
                                                 "structure": facts_structure or snapshot["structure"], "roots": ["SPY"],
                                                 "band": "gym", "incubator": True, "observe": False,
                                                 "holdout_passed": False, "validation_passed": False}
        return snapshot

    def first(self, rows=(), **kw) -> "OptionsLive":
        """A House at 09:31 on MONDAY with one eligible cohort `fam@1`."""
        live = self.make(rows, **{k: kw.pop(k) for k in ("table", "config", "real_money") if k in kw})
        self.cohort(**kw)
        return live

    def mine(self):
        return [b for b in self.venue.sent if str(b.get("client_order_id") or "").endswith("-fam")
                and (b.get("legs") or [{}])[0].get("position_intent", b.get("position_intent")) in ("buy_to_open",)]

    def opens(self, family="fam"):
        return self.live.state.rows("SELECT * FROM orders WHERE action='open' AND family=? ORDER BY oid", (family,))

    def pins(self):
        return self.live.state.get(INC.PINS) or {}

    def verdicts(self):
        return self.live.state.get(INC.VERDICTS) or {}


# ============================================================================================ one test decides the route
@unittest.skipUnless(HAVE, "numpy not installed")
class TheRoute(Base):
    def test_the_key_alone_decides_the_route_coerced_never_raised(self):
        inst = Instance("fam@1:i", "fam", 1, "real", PROGRAM, {}, tuition=True, incubator=False)
        self.assertTrue(inst.incubator)
        self.assertFalse(inst.observe)
        for key, kind, tuition in (("fam@1:t", "real", True), ("fam@1:r", "real", False), ("house:rebound-live@0:h", "real", False),
                                   ("fam@1:o", "shadow", False), ("fam@1:s", "shadow", False)):
            self.assertFalse(Instance(key, "fam", 1, kind, PROGRAM, {}, tuition=tuition, incubator=True).incubator, key)
        self.assertTrue(Instance("fam@1:i", "fam", 1, "shadow", PROGRAM, {}, incubator="yes").incubator,
                        "the key's, whatever the kind: the order path's belt refuses a non-real one")

    def test_a_shadow_or_non_tuition_incubator_instance_is_refused_at_the_order_path_and_alerted(self):
        live = self.make()
        day = live._ensure_day(MONDAY, 570, 960)
        for inst in (Instance("fam@1:i", "fam", 1, "real", PROGRAM, {}, tuition=False),
                     Instance("fam@1:i", "fam", 1, "shadow", PROGRAM, {}, tuition=True)):
            before = len(self.alerts)
            why = live._real_intent(inst, day, 1, {"open": "debit_vertical", "root": "SPY"}, {})
            self.assertIn("not a real", why)
            self.assertEqual(len(self.alerts), before + 1)
            self.assertEqual(self.alerts[-1][0], "error")
        self.assertEqual(self.venue.sent, [])

    def test_an_incubator_open_is_sized_by_plan_incubator_only_and_a_family_open_by_plan_open_only(self):
        calls = {"open": 0, "incubator": 0}
        real_open, real_inc = M.plan_open, M.plan_incubator

        def spy_open(*a, **k):
            calls["open"] += 1
            return real_open(*a, **k)

        def spy_inc(*a, **k):
            calls["incubator"] += 1
            return real_inc(*a, **k)

        with mock.patch.object(M, "plan_open", spy_open), mock.patch.object(M, "plan_incubator", spy_inc):
            self.first()
            self.run_to(9, 31)
            self.assertEqual(len(self.opens()), 1)
            self.assertEqual(calls["open"], 0, "an incubator open never reaches plan_open")
            self.assertGreaterEqual(calls["incubator"], 1)
        # A Probe family alone: plan_open only.
        calls.update(open=0, incubator=0)
        self.live.state.close()
        self.setUp()
        with mock.patch.object(M, "plan_open", spy_open), mock.patch.object(M, "plan_incubator", spy_inc):
            self.make([family("vert", VERTICAL, band="probe")])
            self.run_to(9, 31)
            self.assertEqual((calls["open"] >= 1, calls["incubator"]), (True, 0))

    def test_restore_by_keyword_keeps_it_real_tuition_incubator_and_its_saved_mode(self):
        live = self.make()
        live.state.upsert("instances", {"id": "fam@1:i", "family": "fam", "version": 1, "run_sha": "x", "code": PROGRAM,
                                        "params": json.dumps(PARAMS), "band": "gym", "tuition": 0, "mode": "exit_only",
                                        "created_at": 1.0, "retired_at": None, "why": None}, "id")
        live = self.restart()
        inst = live.instances["fam@1:i"]
        self.assertEqual((inst.kind, inst.incubator, inst.tuition, inst.observe, inst.mode),
                         ("real", True, True, False, "exit_only"))

    def test_the_minutes_order_is_d2_then_the_incubator_then_the_house_test(self):
        insts = [Instance("house:rebound-live@0:h", "house:rebound-live", 0, "real", "", {}),
                 Instance("fam@1:i", "fam", 1, "real", "", {}, tuition=True),
                 Instance("pro@1:r", "pro", 1, "real", "", {}), Instance("pre@1:t", "pre", 1, "real", "", {}, tuition=True)]
        self.assertEqual([i.key for i in sorted(insts, key=_rank)], ["pro@1:r", "pre@1:t", "fam@1:i", "house:rebound-live@0:h"])


# ================================================================================================ the practice rule
@unittest.skipUnless(HAVE, "numpy not installed")
class ThePracticeRule(unittest.TestCase):
    """`money.practice_ok` at every boundary, and `observe.practice_record` read-only, evaluator-filtered."""

    def setUp(self):
        self.table = M.Table.from_constitution()
        self.good = {"sessions": 3, "closes_program": 10, "decisions_due": 100, "decisions_made": 80, "coverage": 0.8,
                     "pnl_program": 0.01, "pnl_all": 0.01, "open_mark": 0.0}

    def check(self, **change):
        return M.practice_ok(self.table, {**self.good, **change})

    def test_every_condition_at_its_boundary(self):
        self.assertEqual(self.check()[0], True)
        self.assertEqual(self.check(sessions=2)[0], False)
        self.assertTrue(self.check(sessions=2)[1].startswith("P1"))
        self.assertTrue(self.check(sessions=None)[1].startswith("P1"))
        self.assertEqual(self.check(closes_program=9)[0], False)
        self.assertTrue(self.check(closes_program=9)[1].startswith("P2"))
        self.assertEqual(self.check(decisions_made=79)[0], False, "0.79")
        self.assertTrue(self.check(decisions_made=79)[1].startswith("P3"))
        self.assertEqual(self.check(decisions_due=0, decisions_made=0, coverage=None)[0], False, "coverage unknown")
        self.assertEqual(self.check(decisions_due=None, decisions_made=None, coverage=0.79)[0], False)
        self.assertEqual(self.check(decisions_due=None, decisions_made=None, coverage=0.8)[0], True)
        self.assertEqual(self.check(pnl_program=0.0)[0], False)
        self.assertTrue(self.check(pnl_program=0.0)[1].startswith("P4"))
        self.assertEqual(self.check(pnl_all=0.0)[0], False)
        self.assertTrue(self.check(pnl_all=0.0)[1].startswith("P5"))
        self.assertEqual(self.check(pnl_all=5.0, open_mark=-5.0)[0], False, "a negative open mark can fail P6")
        self.assertTrue(self.check(pnl_all=5.0, open_mark=-5.0)[1].startswith("P6"))
        self.assertEqual(self.check(pnl_program=0.1 + 0.2 - 0.3)[0], False, "float noise is not a profit")

    def test_the_exit_check_is_p3_to_p6_only_and_can_only_refuse(self):
        self.assertEqual(M.practice_ok(self.table, {**self.good, "sessions": 1, "closes_program": 0}, exit_check=True)[0], True)
        self.assertEqual(M.practice_ok(self.table, {**self.good, "pnl_all": -1.0}, exit_check=True)[0], False)

    def test_the_record_is_read_only_evaluator_filtered_and_ignores_pnl_marked(self):
        import tempfile

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.assertIsNone(practice_record(root, "fam", 1, before="2026-09-28", evaluator="E"), "no file: no record")
        store = ObserveStore(root)
        store.evaluator = "E"
        db = store._connect()
        db.execute("INSERT INTO cohorts(family, version, admitted_at, first_day, snapshot) VALUES('fam', 1, 1, '2026-09-23', ?)",
                   (json.dumps({"practice_evaluator": "E", "run_sha": "s", "structure": "debit_vertical", "tier": "train"}),))
        db.execute("INSERT INTO practice(family, version, tier, capital, first_at, first_day, last_at, last_day, sessions, "
                   "decisions_due, decisions_made, pnl_marked, open_mark_pnl) VALUES('fam', 1, 'train', 1e4, 1, '2026-09-23', 2, "
                   "'2026-09-28', 4, 10, 9, 99999, -3.5)")
        rows = [("2026-09-24", 10.0, 40.0, 0, "E", 1, 1.0), ("2026-09-25", -4.0, 40.0, 1, "E", 1, 1.0),
                ("2026-09-25", 100.0, 40.0, 0, "OLD", 1, 1.0), ("2026-09-28", 50.0, 40.0, 0, "E", 1, 1.0),
                ("2026-09-25", 3.0, 120.0, 0, "E", 2, 2.0)]
        for i, (day, pnl, loss, forced, ev, qty, fees) in enumerate(rows):
            db.execute("INSERT INTO trades(instance, account, family, version, trade_id, day, pnl, max_loss, recorded_at, body, "
                       "exit_day, forced, evaluator) VALUES('fam@1:o', 'a', 'fam', 1, ?, ?, ?, ?, 1, ?, ?, ?, ?)",
                       (str(i), day, pnl, loss, json.dumps({"qty": qty, "fees": fees}), day, forced, ev))
        self.addCleanup(store.close)                        # the House's own connection stays open, as on the box
        before = os.stat(root / "observe.sqlite").st_mtime_ns
        record = practice_record(root, "fam", 1, before="2026-09-28", evaluator="E", unit_cap=50.0)
        self.assertEqual(os.stat(root / "observe.sqlite").st_mtime_ns, before, "read-only")
        self.assertEqual(record["sessions"], 3, "today's session left out")
        self.assertEqual((record["closes_program"], record["pnl_program"]), (2, 13.0),
                         "program closes under this evaluator before today; forced and other evaluators left out")
        self.assertEqual((record["closes_all"], record["pnl_all"]), (3, 9.0), "forced closes count in P5")
        self.assertEqual((record["open_mark"], record["coverage"], record["intraday"]), (-3.5, 0.9, True),
                         "stepped today with nothing kept from before it: today's values, said so")
        self.assertEqual(record["feasible"], 1, "40 + 2 x 1 fits $50; 120 / 2 + 2 x 2 / 2 does not")
        self.assertEqual(record["return_on_risk"], round(9.0 / 200.0, 6))
        self.assertEqual(practice_record(root, "fam", 1, before="2026-09-28", evaluator="OLD")["closes_program"], 1)
        # A practice row older than its cohort is ineligible; a broken file never raises.
        db = sqlite3.connect(root / "observe.sqlite")
        db.execute("UPDATE practice SET first_day='2026-09-22'")
        db.commit()
        db.close()
        self.assertIsNone(practice_record(root, "fam", 1, before="2026-09-28", evaluator="E")["sessions"])
        store.close()
        (root / "observe.sqlite").write_bytes(b"garbage" * 1000)
        for suffix in ("-wal", "-shm"):
            try:
                (root / f"observe.sqlite{suffix}").unlink()
            except FileNotFoundError:
                pass
        self.assertIsNone(practice_record(root, "fam", 1, before="2026-09-28", evaluator="E"))
        self.assertIsNone(cohort_rows(root))


    def test_the_record_before_today_never_reads_todays_coverage_or_mark(self):
        import tempfile

        from league.live import observe as O

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        # A file from before release B's columns gains them when the House opens it.
        old = sqlite3.connect(root / "observe.sqlite")
        old.executescript(O.SCHEMA.replace("    prior_day TEXT, prior_due INTEGER, prior_made INTEGER, prior_open_mark REAL,\n", ""))
        self.assertNotIn("prior_day", {r[1] for r in old.execute("PRAGMA table_info(practice)")})
        old.close()
        store = ObserveStore(root, clock=lambda: 200000.0)
        store.evaluator = "E"
        self.addCleanup(store.close)
        db = store._connect()
        self.assertTrue({"prior_day", "prior_due", "prior_made", "prior_open_mark"}
                        <= {r[1] for r in db.execute("PRAGMA table_info(practice)")})
        db.execute("INSERT INTO cohorts(family, version, admitted_at, first_day, snapshot) VALUES('fam', 1, 1, '2026-09-23', ?)",
                   (json.dumps({"practice_evaluator": "E"}),))

        def minute(day, t, *, made=True, mark=0.0):
            self.assertTrue(store.practice([{"family": "fam", "version": 1, "tier": "train", "capital": 1e4, "account": "a",
                                             "at": t, "day": day, "equity": 1e4, "open_positions": 1,
                                             "open_mark_pnl": mark, "due": True, "made": made, "status": "live"}]))

        def read(before):
            r = practice_record(root, "fam", 1, before=before, evaluator="E")
            return r["decisions_due"], r["decisions_made"], r["open_mark"], r["intraday"]

        minute("2026-09-23", 60.0, mark=1.0)
        self.assertEqual(read("2026-09-23"), (0, 0, 0.0, False), "first stepped today: nothing before it")
        minute("2026-09-23", 120.0, made=False, mark=2.0)
        self.assertEqual(read("2026-09-24"), (2, 1, 2.0, False), "not stepped since: all before today")
        minute("2026-09-24", 86460.0, made=False, mark=-50.0)
        minute("2026-09-24", 86520.0, made=False, mark=-60.0)
        self.assertEqual(read("2026-09-24"), (2, 1, 2.0, False), "today's two missed decisions and mark left out")
        self.assertEqual(practice_record(root, "fam", 1, before="2026-09-24", evaluator="E")["coverage"], 0.5)
        self.assertEqual(db.execute("SELECT decisions_due, open_mark_pnl, prior_day, prior_due, prior_made, prior_open_mark "
                                    "FROM practice").fetchone(), (4, -60.0, "2026-09-24", 2, 1, 2.0),
                         "the values 09-23 left, stamped with the roll's day (09-24), never the day they came from")
        self.assertEqual(read("2026-09-25"), (4, 1, -60.0, False))
        minute("2026-09-25", 172860.0, mark=7.0)
        self.assertEqual(read("2026-09-25"), (4, 1, -60.0, False), "the roll keeps the last session's values")
        self.assertEqual(db.execute("SELECT prior_day FROM practice").fetchone()[0], "2026-09-25")
        # A row stepped today before the columns existed: what it held before today is not known, and said so.
        db.execute("UPDATE practice SET prior_day=NULL, prior_due=NULL, prior_made=NULL, prior_open_mark=NULL")
        self.assertEqual(read("2026-09-25"), (5, 2, 7.0, True))
        # The verifiers' PROBE A, in the store: B rolls on 09-28, then release A (a rollback, which never rolls
        # `prior_*`) steps 09-29. The 09-28 roll holds what 09-25 left, an older session than the record before 09-29:
        # not known from it, said so (fail closed), never 09-25's values as if they were 09-28's.
        minute("2026-09-28", 432060.0, mark=3.0)
        self.assertEqual(db.execute("SELECT prior_day, prior_due, prior_made, prior_open_mark FROM practice").fetchone(),
                         ("2026-09-28", 5, 2, 7.0))
        self.assertEqual(read("2026-09-28"), (5, 2, 7.0, False))
        db.execute("UPDATE practice SET last_day='2026-09-29', sessions=sessions+1, decisions_due=decisions_due+5, "
                   "open_mark_pnl=-1000.0")                       # release A's minutes on 09-29
        self.assertEqual(read("2026-09-29"), (11, 3, -1000.0, True), "09-28's roll is not the record before 09-29")
        minute("2026-09-29", 518460.0, mark=1.0)                  # B back the same day: no roll, still not known
        self.assertEqual(read("2026-09-29"), (12, 4, 1.0, True))
        minute("2026-09-30", 604860.0, mark=2.0)                  # the next session day's roll: known again
        self.assertEqual(read("2026-09-30"), (12, 4, 1.0, False))


# ======================================================================================================== the caps
@unittest.skipUnless(HAVE, "numpy not installed")
class TheCaps(unittest.TestCase):
    """`money.plan_incubator` and the tally (`real.incubator_tally`) over the live state's own rows."""

    def setUp(self):
        import tempfile

        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state = LiveState(Path(self.tmp.name) / "live.sqlite")
        self.addCleanup(self.state.close)
        self.table = M.Table.from_constitution()
        self.oid = self.pid = 0
        self.E = D("1465")

    # -------------------------------------------------------------- rows as the real book writes them
    def order(self, family="fam", *, unit=D("30"), status="working", day="2026-09-28", filled=0, fees=D("1"),
              instance=None, dispatched=True, tuition=1, qty=1):
        self.oid += 1
        max_loss = (unit - 2 * fees) * qty
        self.state.upsert("orders", {"oid": self.oid, "client_id": f"lv-{self.oid}", "instance": instance or f"{family}@1:i",
                                     "family": family, "action": "open", "type": "debit_vertical", "root": "SPY",
                                     "legs": json.dumps([{"symbol": f"A{self.oid}", "side": 1, "ratio": 1, "is_call": True,
                                                          "strike": 600.0, "expiry": "2026-10-02", "key": 1},
                                                         {"symbol": f"B{self.oid}", "side": -1, "ratio": 1, "is_call": True,
                                                          "strike": 601.0, "expiry": "2026-10-02", "key": 2}]),
                                     "qty": qty, "limit_value": 0.3,
                                     "limit_price": "0.30", "placed_at": 1.0, "day": day, "placed_minute": 1,
                                     "status": status, "filled_qty": filled, "max_loss": float(max_loss),
                                     "fees_est": float(fees), "tuition": tuition,
                                     "answer": json.dumps({"dispatched": dispatched}), "updated_at": 1.0}, "oid")
        if dispatched:
            self.state.execute("INSERT INTO dispatch_counts(oid, day, legs) VALUES(?,?,2)", (self.oid, day))
        return self.oid

    def position(self, family="fam", *, loss=D("30"), fees=D("1"), status="open", cash=None, closed_at=None,
                 instance=None, qty=1):
        self.pid += 1
        share = (loss - 2 * fees) / 100
        self.state.upsert("positions", {"pid": self.pid, "instance": instance or f"{family}@1:i", "family": family,
                                        "type": "debit_vertical", "root": "SPY", "legs": "[]", "qty": 0 if status == "closed" else qty,
                                        "opened_qty": qty, "entry": float(share), "max_loss_share": float(share),
                                        "collateral": 0.0, "fees": float(fees),
                                        "cash": float(cash if cash is not None else -(share * 100 + fees)), "opened_at": 1.0,
                                        "opened_day": "2026-09-21", "opened_minute": 1, "status": status,
                                        "closed_at": closed_at, "tuition": 1, "info": "{}"}, "pid")
        return self.pid

    def tally(self, family="fam", day="2026-09-28"):
        return incubator_tally(self.state.rows, day=day, week_start=INC.week_start_of(dt.date.fromisoformat(day)),
                               family=family)

    def plan(self, unit, family="fam", *, day="2026-09-28", exposure=None, room=D("300"), E=None):
        return M.plan_incubator(self.table, unit=D(unit), equity=E or self.E, tally=self.tally(family, day),
                                exposure=exposure or M.Exposure(), room=room)

    # -------------------------------------------------------------- direct cases
    def test_one_lot_under_fifty_dollars(self):
        self.assertEqual(self.plan("50").qty, 1)
        self.assertEqual(self.plan("50.01").qty, 0)
        self.assertIn("over its $50 cap", self.plan("50.01").reason)

    def test_a_fifth_open_is_refused(self):
        for fam in ("a", "b", "c"):
            self.position(fam, loss=D("10"))
        self.order("d", unit=D("10"))
        self.assertEqual(self.tally("e").open_n, 4)
        self.assertIn("the most it holds is 4", self.plan("10", "e").reason)

    def test_the_weekly_envelope_counts_realized_held_and_working_to_the_cent(self):
        monday = at(dt.date(2026, 9, 28), 10, 0)
        self.position("a", status="closed", cash=D("-100"), closed_at=monday)
        self.position("b", loss=D("40"))
        self.assertEqual(self.plan("10.01", "c").qty, 0)
        self.assertIn("envelope", self.plan("10.01", "c").reason)
        self.assertEqual(self.plan("10.00", "c").qty, 1)

    def test_a_family_holds_or_works_at_most_fifty_dollars(self):
        self.position("a", loss=D("30"))
        self.assertIn("the family already holds", self.plan("20.01", "a").reason)
        self.assertEqual(self.plan("20", "a").qty, 1)
        self.assertEqual(self.plan("50", "b").qty, 1, "another family's own $50")
        self.order("a", unit=D("20"))
        self.assertEqual(self.plan("0.01", "a").qty, 0, "held and working together")

    def test_a_position_carried_into_a_new_week_counts_as_held_and_last_weeks_loss_resets_on_monday(self):
        friday = at(dt.date(2026, 9, 25), 15, 0)
        self.position("a", status="closed", cash=D("-140"), closed_at=friday)
        self.position("b", loss=D("45"))
        self.assertEqual(self.tally("x", day="2026-09-25").realized_loss, D("140"))
        self.assertEqual(self.plan("20", "x", day="2026-09-25").qty, 0, "Friday: 140 + 45 + 20 > 150")
        monday = self.tally("x", day="2026-09-28")
        self.assertEqual((monday.realized_loss, monday.held), (D("0"), D("45")))
        self.assertEqual(self.plan("20", "x", day="2026-09-28").qty, 1, "Monday: a new week")

    def test_stopped_for_the_week_once_realized_loss_reaches_it(self):
        self.position("a", status="closed", cash=D("-150"), closed_at=at(dt.date(2026, 9, 28), 10, 0))
        plan = self.plan("1", "b")
        self.assertEqual(plan.qty, 0)
        self.assertIn("stopped for the week", plan.reason)

    def test_the_weekly_stop_latches_a_later_gain_in_the_same_week_never_reopens_it(self):
        """The review's case (Sept 30): Monday R $100 with A ($30) and B ($20) held; Wednesday A, a broken structure, closes
        leg by leg for -$56 (R $156: stopped); Thursday B closes +$15 (R $141). The route stays stopped for the rest of
        the ISO week, across a restart, and opens again the next Monday."""
        monday, wednesday = (at(dt.date(2026, 9, d), 11, 0) for d in (28, 30))
        thursday = at(dt.date(2026, 10, 1), 11, 0)
        self.position("z", status="closed", cash=D("-100"), closed_at=monday)
        a = self.position("a", loss=D("30"))
        b = self.position("b", loss=D("20"))
        self.assertIn("envelope", self.plan("0.01", "c", day="2026-09-28").reason, "Monday: the envelope is full")
        self.state.execute("UPDATE positions SET status='closed', qty=0, cash=-56, closed_at=? WHERE pid=?", (wednesday, a))
        self.assertIn("stopped for the week", self.plan("8.50", "c", day="2026-09-30").reason)
        self.state.execute("UPDATE positions SET status='closed', qty=0, cash=15, closed_at=? WHERE pid=?", (thursday, b))
        t = self.tally("c", day="2026-10-01")
        self.assertEqual((t.realized_loss, t.week_peak_loss, t.held), (D("141"), D("156"), D("0")))
        plan = self.plan("8.50", "c", day="2026-10-01")
        self.assertEqual(plan.qty, 0, "a gain later in the week never re-opens the route")
        self.assertIn("stopped for the week", plan.reason)
        self.state.close()
        self.state = LiveState(Path(self.tmp.name) / "live.sqlite")
        self.assertEqual(self.plan("8.50", "c", day="2026-10-02").qty, 0, "restart-safe: read from the live state's closes")
        self.assertEqual(self.plan("8.50", "c", day="2026-10-05").qty, 1, "the next ISO week opens again")

    def test_the_latch_reads_a_ties_losses_first(self):
        t = at(dt.date(2026, 9, 28), 10, 0)
        self.position("a", status="closed", cash=D("40"), closed_at=t)
        self.position("b", status="closed", cash=D("-160"), closed_at=t)
        tally = self.tally("c")
        self.assertEqual((tally.realized_loss, tally.week_peak_loss), (D("120"), D("160")))
        self.assertIn("stopped for the week", self.plan("1", "c").reason)

    def test_net_gains_offset_losses_within_the_week(self):
        t = at(dt.date(2026, 9, 28), 10, 0)
        self.position("a", status="closed", cash=D("-120"), closed_at=t)
        self.position("b", status="closed", cash=D("70"), closed_at=t)
        self.assertEqual(self.tally("c").realized_loss, D("50"))

    def test_a_broken_structures_cash_counts_when_it_lost_more_than_its_maximum(self):
        self.position("a", loss=D("30"), cash=D("-44"))
        self.assertEqual(self.tally("a").held, D("44"))

    def test_lost_opens_count_whole_for_their_iso_week_and_unpriced_closes_hold(self):
        """A lost open the venue later shows is taken back and its fills booked (`RealBook.ingest`): it counts whole until
        its ISO week ends (a tightening of the spec's "today's"), never last week's."""
        self.order("a", unit=D("30"), status="lost", day="2026-09-28")
        self.order("a", unit=D("30"), status="lost", day="2026-09-25")
        self.position("b", loss=D("20"), status="unpriced_close")
        t = self.tally("a", day="2026-09-30")
        self.assertEqual((t.working, t.held, t.open_n), (D("30"), D("20"), 2), "Wednesday: Monday's lost open counts")
        self.assertEqual(self.tally("a", day="2026-10-05").working, D("0"), "the next Monday: it no longer counts")

    def test_tuition_and_other_families_rows_never_count_and_the_suffix_is_exact(self):
        self.order("t", unit=D("30"), instance="t@1:t")
        self.position("r", loss=D("30"), instance="r@1:r")
        self.order("x", unit=D("30"), instance="x@1:I")
        self.assertEqual(self.tally("t"), M.IncubatorTally())

    def test_the_day_legs_and_dispatch_limits(self):
        for _ in range(20):
            oid = self.order("a", unit=D("5"), status="cancelled")
        self.assertEqual(self.tally("b").legs_today, 40)
        self.assertIn("order legs today", self.plan("5", "b").reason)
        self.state.execute("DELETE FROM dispatch_counts")
        self.state.execute("DELETE FROM orders")
        # 25% of the gateway's day cap at E = $1,465: $366.25 of opens a day.
        for _ in range(8):
            self.order("a", unit=D("45"), status="cancelled", fees=D("0"))
        self.state.execute("DELETE FROM dispatch_counts")
        self.assertEqual(self.tally("b").opened_today, D("360"))
        self.assertEqual(self.plan("6.25", "b").qty, 1)
        self.assertIn("of the day cap", self.plan("6.26", "b").reason)
        del oid

    def test_the_ten_refusals_in_their_order(self):
        E, t = self.E, self.table
        full = M.IncubatorTally
        cases = [
            (dict(unit="1", E=D("0")), "no sizing equity"),
            (dict(unit="0"), "not positive"),
            (dict(unit="50.01"), "over its $50 cap"),
            (dict(unit="30", tally=full(family_held=D("30"))), "the family already holds"),
            (dict(unit="1", tally=full(open_n=4)), "the most it holds is 4"),
            (dict(unit="1", tally=full(realized_loss=D("150"))), "stopped for the week"),
            (dict(unit="1", tally=full(held=D("149.01"))), "envelope"),
            (dict(unit="1", tally=full(legs_today=40)), "order legs today"),
            (dict(unit="1", tally=full(opened_today=D("366"))), "of the day cap"),
            (dict(unit="1", exposure=M.Exposure(book_loss=D("1018"))), "the book's cap"),
            # The per-order cap binds before the day share only where the gateway's order share is under a quarter of
            # its day share (today both are a quarter of E), so this case tightens the table's order share.
            (dict(unit="20", E=D("100"), room=D("0"), table=table(), order_share="0.10"), "per-order cap"),
            (dict(unit="1", exposure=M.Exposure(day_opened=D("1165")), E=E), "the gateway's day cap"),
        ]
        for kw, why in cases:
            tab = t
            if "order_share" in kw:
                c = copy.deepcopy(CONSTITUTION)
                c["options_money"]["gateway"]["order_equity_share"] = kw["order_share"]
                tab = M.Table.from_constitution(c)
            plan = M.plan_incubator(tab, unit=D(kw["unit"]), equity=kw.get("E", E), tally=kw.get("tally", full()),
                                    exposure=kw.get("exposure", M.Exposure()), room=kw.get("room", D("300")))
            self.assertEqual(plan.qty, 0, why)
            self.assertIn(why, plan.reason)
        self.assertEqual(M.plan_incubator(t, unit=D("50"), equity=E, tally=full(), exposure=M.Exposure(),
                                          room=D("300")).qty, 1)

    def test_room_is_kept_for_probe_floors_and_the_house_test(self):
        """At E = $1,465: the book cap $1,318.50 and the day cap $1,465 each keep $300 (two $100 Probe floors and the House
        test's $100 structure) after the incubator's open."""
        E = D("1465")
        book = self.table.book_share * E
        at_edge = M.Exposure(book_loss=book - D("300") - D("30"))
        self.assertEqual(self.plan("30", exposure=at_edge, E=E).qty, 1)
        self.assertEqual(self.plan("30.01", exposure=at_edge, E=E).qty, 0)
        after = at_edge.book_loss + D("30")
        self.assertGreaterEqual(book - after, D("300"), "a Probe floor and the House test's $100 still fit")
        day = M.Exposure(day_opened=E - D("300") - D("30"))
        self.assertEqual(self.plan("30", exposure=day, E=E).qty, 1)
        self.assertEqual(self.plan("30.01", exposure=day, E=E).qty, 0)

    # -------------------------------------------------------------- the property
    def test_the_invariants_hold_at_every_admitted_open_over_random_sequences(self):
        """Opens, fills and partial fills, cancels, lost opens, closes at random P&L, broken structures, restarts and ISO
        weeks, driven through the tally and the plan: at every admitted open one lot, unit <= $50, the family's held and
        working plus the unit <= $50, at most 4 held or working after it, R + H + W + unit <= $150; and every week's net
        realized loss is at most $150 plus the residuals injected (fees above the estimate, a broken close)."""
        rng = random.Random(20261001)
        start = dt.date(2026, 9, 28)
        for seq in range(60):
            self.state.execute("DELETE FROM orders")
            self.state.execute("DELETE FROM positions")
            self.state.execute("DELETE FROM dispatch_counts")
            day = start
            weekly: dict[str, D] = {}
            peak: dict[str, D] = {}
            residual: dict[str, D] = {}
            for step in range(80):
                today = day.isoformat()
                week = INC.week_start_of(day)
                action = rng.random()
                fam = rng.choice(("a", "b", "c", "d", "e"))
                if action < 0.35:
                    unit = D(rng.randrange(100, 6000)) / 100
                    t = self.tally(fam, today)
                    plan = self.plan(unit, fam, day=today)
                    if plan.qty:
                        self.assertEqual(plan.qty, 1)
                        self.assertLessEqual(unit, D("50"))
                        self.assertLessEqual(t.family_held + t.family_working + unit, D("50"))
                        self.assertLess(t.open_n, 4)
                        self.assertLessEqual(t.realized_loss + t.held + t.working + unit, D("150"))
                        self.assertLess(peak.get(week, D(0)), D("150"), "no open in a week after its net loss reached $150")
                        self.order(fam, unit=unit, day=today, fees=D("1"))
                elif action < 0.55:
                    # A working open fills (whole or one lot of it) at or under its admitted maximum loss.
                    rows = self.state.rows("SELECT * FROM orders WHERE status='working' AND action='open'")
                    if rows:
                        r = rng.choice(rows)
                        unit = D(str(r["max_loss"])) + 2 * D(str(r["fees_est"]))
                        self.state.execute("UPDATE orders SET status='filled', filled_qty=qty WHERE oid=?", (r["oid"],))
                        self.position(r["family"], loss=unit, fees=D(str(r["fees_est"])))
                elif action < 0.65:
                    rows = self.state.rows("SELECT oid FROM orders WHERE status='working'")
                    if rows:
                        self.state.execute("UPDATE orders SET status=? WHERE oid=?",
                                           (rng.choice(("cancelled", "lost", "expired")), rng.choice(rows)["oid"]))
                elif action < 0.85:
                    # A close at a random P&L within the structure's range; sometimes a residual (fees above the estimate,
                    # a broken structure's legs closed at forced prices).
                    rows = self.state.rows("SELECT * FROM positions WHERE status='open'")
                    if rows:
                        r = rng.choice(rows)
                        risk = D(str(r["max_loss_share"])) * 100 + 2 * D(str(r["fees"]))
                        cash = -risk + D(rng.randrange(0, int(risk * 200) + 1)) / 100
                        extra = D(rng.choice((0, 0, 0, 1, 7))) / 100 if rng.random() < 0.9 else D("3.50")
                        cash -= extra
                        residual[week] = residual.get(week, D(0)) + extra
                        self.state.execute("UPDATE positions SET status='closed', qty=0, cash=?, closed_at=? WHERE pid=?",
                                           (float(cash), at(day, 12, 0), r["pid"]))
                        weekly[week] = weekly.get(week, D(0)) + cash
                        peak[week] = max(peak.get(week, D(0)), -weekly[week])
                elif action < 0.9:
                    # A restart: a new book on the same file reads the same numbers.
                    before = self.tally(fam, today)
                    self.state.close()
                    self.state = LiveState(Path(self.tmp.name) / "live.sqlite")
                    self.assertEqual(self.tally(fam, today), before)
                else:
                    day += dt.timedelta(days=rng.choice((1, 1, 1, 3)))
            for week, cash in weekly.items():
                self.assertLessEqual(max(D(0), -cash), D("150") + residual.get(week, D(0)) + D("0.01"), (seq, week))
        self.addCleanup(self.state.close)

    def test_rollback_to_release_a_counts_incubator_rows_as_tuition_fail_closed(self):
        """Release A's exposure code summed every tuition-flagged open: the incubator's rows are tuition-flagged, so a
        rollback across B counts them against tuition's own caps (fail-closed), while B keeps the two apart."""
        self.order("fam", unit=D("30"))
        rows = self.state.rows("SELECT tuition, instance FROM orders")
        self.assertEqual([r["tuition"] for r in rows], [1])
        book = RealBook(self.state, None, self.table)
        exposure = book.exposure("fam", day="2026-09-28", week_start="2026-09-28")
        self.assertEqual((exposure.tuition_day, exposure.tuition_week), (D(0), D(0)), "B: the two routes' sums apart")

        def release_a_tuition(state, *, day, week_start):
            """Release A's tuition sums, copied from `RealBook.exposure` at a/live-guards 1df0e7fb (no `:i` skip)."""
            sent = state.rows("SELECT day, max_loss, qty, filled_qty, status, tuition, answer FROM orders WHERE "
                              "action='open' AND day>=?", (week_start,))
            tuition_day = tuition_week = D(0)
            for r in sent:
                if r["tuition"]:
                    live = r["status"] in ("pending", "working", "unknown")
                    units = int(r["qty"]) if live else int(r["filled_qty"])
                    loss = M.D(r["max_loss"]) * units / max(1, int(r["qty"]))
                    tuition_week += loss
                    if r["day"] == day:
                        tuition_day += loss
            return tuition_day, tuition_week

        self.assertEqual(release_a_tuition(self.state, day="2026-09-28", week_start="2026-09-28"), (D("28"), D("28")),
                         "A: the incubator's working $30 open ($28 of maximum loss before fees) counts as tuition")
        import inspect

        source = inspect.getsource(RealBook.exposure)
        self.assertIn('if r["tuition"] and not is_incubator(r["instance"]):', source, "B's only change to that loop")


# ======================================================================================================== first looks
@unittest.skipUnless(HAVE, "numpy not installed")
class FirstLooks(Base):
    def test_a_passing_cohort_is_pinned_and_sends_one_real_tuition_lot_never_evidence(self):
        live = self.first()
        self.run_to(9, 31)
        [verdict] = self.verdicts().values()
        self.assertTrue(verdict["passed"], verdict["why"])
        self.assertEqual((verdict["record"]["sessions"], verdict["record"]["closes_program"]), (3, 10))
        self.assertEqual(verdict["fill_model"], str(live.shadow.fill_model.version))
        self.assertEqual(self.pins()["order"], ["fam@1:i"])
        inst = live.instances["fam@1:i"]
        self.assertEqual((inst.kind, inst.tuition, inst.incubator, inst.observe, inst.band), ("real", True, True, False, "gym"))
        [row] = self.opens()
        self.assertEqual((row["qty"], row["tuition"], row["instance"]), (1, 1, "fam@1:i"), "one lot, whatever it asked")
        self.assertLessEqual(row["max_loss"] + 2 * row["fees_est"], 50.0)
        self.assertTrue([p for p, a in self.ledger.of("live.incubator") if p.get("first_look") == "fam@1"])
        self.run_to(9, 40)
        self.assertEqual(self.families.forward_rows("fam"), [], "never a forward row")
        self.assertEqual(self.families.moves, [], "never a band move")
        closed = live.state.rows("SELECT pid, tuition, instance FROM positions WHERE status='closed'")
        self.assertEqual([(r["tuition"], r["instance"]) for r in closed], [(1, "fam@1:i")])
        self.assertEqual({r["pid"] for r in live.state.rows("SELECT pid FROM forward_exports")}, {r["pid"] for r in closed})
        self.assertEqual(live.health()["incubator"]["pins"]["order"], ["fam@1:i"])
        self.assertEqual(live.site_inputs()["structures"], [])

    def test_the_owners_report_reads_the_state_without_writing_it(self):
        from league.live.__main__ import incubator_report

        self.first(params=dict(PARAMS, hold=600))
        self.run_to(9, 31)
        rows = self.live.state.rows("SELECT COUNT(*) AS n FROM events")[0]["n"]
        out = incubator_report(self.root, now=self.clock())
        self.assertEqual(out["switch"], {"live.incubator": True, "on": True})
        self.assertEqual(out["pins"]["order"], ["fam@1:i"])
        self.assertTrue(out["verdicts"]["fam@1"]["passed"])
        self.assertEqual(out["tally"]["open"], 1)
        self.assertEqual([r["id"] for r in out["instances"]], ["fam@1:i"])
        self.assertEqual(self.live.state.rows("SELECT COUNT(*) AS n FROM events")[0]["n"], rows, "read-only")

    def test_the_first_look_is_recorded_while_the_switch_is_off(self):
        self.switch(False)
        live = self.first()
        self.run_to(9, 31)
        self.assertTrue(self.verdicts()["fam@1"]["passed"])
        self.assertEqual(self.pins().get("order"), [])
        self.assertNotIn("fam@1:i", live.instances)
        self.assertEqual(self.opens(), [])

    def test_a_failed_first_look_is_final(self):
        self.first(trades=winning(10, pnl=-1.0))
        self.run_to(9, 31)
        verdict = self.verdicts()["fam@1"]
        self.assertFalse(verdict["passed"])
        self.assertTrue(verdict["why"].startswith("P4"))
        # Later positive practice never re-admits it.
        db = self.live.observe_store._connect()
        db.execute("UPDATE trades SET pnl=50")
        self.clock.set(at(TUESDAY, 9, 31))
        self.run_to(9, 31)
        self.assertFalse(self.verdicts()["fam@1"]["passed"])
        self.assertEqual(self.verdicts()["fam@1"]["day"], "2026-09-28", "the first look is never taken again")
        self.assertEqual(self.pins()["order"], [])

    def test_no_look_before_the_sample_and_today_is_left_out(self):
        self.first(trades=winning(9))
        self.run_to(9, 31)
        self.assertEqual(self.verdicts(), {}, "9 program closes: no look yet")
        self.live.state.close()
        self.setUp()
        # Three sessions only counting today's, and a tenth close today: neither counts before today.
        self.first(trades=winning(9) + [("2026-09-28", 5.0, 30.0, False)], last_day="2026-09-28")
        self.run_to(9, 31)
        self.assertEqual(self.verdicts(), {})

    def test_forced_closes_count_in_p5_never_in_p2_or_p4(self):
        self.first(trades=winning(9) + winning(3, pnl=30.0, forced=True))
        self.run_to(9, 31)
        self.assertEqual(self.verdicts(), {}, "a forced close is not a program close")
        self.live.state.close()
        self.setUp()
        self.first(trades=winning(10, pnl=1.0) + winning(1, pnl=-20.0, forced=True))
        self.run_to(9, 31)
        verdict = self.verdicts()["fam@1"]
        self.assertFalse(verdict["passed"])
        self.assertTrue(verdict["why"].startswith("P5"))

    def test_pins_stand_for_the_session_survive_a_restart_and_nothing_joins_mid_session(self):
        live = self.first()
        self.run_to(9, 31)
        self.cohort("late", 1)
        self.run_to(9, 45)
        self.assertEqual(self.pins()["order"], ["fam@1:i"], "no mid-session join")
        self.assertNotIn("late@1", self.verdicts(), "no first look mid-session either")
        live = self.restart()
        self.assertIn("fam@1:i", live.instances)
        self.run_to(9, 50)
        self.assertEqual(self.pins()["order"], ["fam@1:i"])
        self.assertEqual(live.instances["fam@1:i"].mode, "live")
        # The next session pins afresh: both.
        self.clock.set(at(TUESDAY, 9, 31))
        self.run_to(9, 31)
        self.assertEqual(sorted(self.pins()["order"]), ["fam@1:i", "late@1:i"])

    def test_the_next_session_ends_an_incubation_whose_extended_record_fails(self):
        live = self.first()
        self.run_to(9, 31)
        self.assertEqual(live.instances["fam@1:i"].mode, "live")
        db = live.observe_store._connect()
        db.execute("INSERT INTO trades(instance, account, family, version, trade_id, day, pnl, max_loss, recorded_at, body, "
                   "exit_day, reason, forced, evaluator) VALUES('fam@1:o', 'a', 'fam', 1, 'loss', '2026-09-28', -80, 30, 1, "
                   "'{}', '2026-09-28', 'program', 0, ?)", (live.observe_store.evaluator,))
        self.clock.set(at(TUESDAY, 9, 31))
        self.run_to(9, 31)
        verdict = self.verdicts()["fam@1"]
        self.assertTrue(verdict["passed"])
        self.assertTrue(verdict["ended"]["why"].startswith("P4"))
        self.assertEqual(self.pins()["order"], [])
        inst = live.instances.get("fam@1:i")
        self.assertTrue(inst is None or inst.mode == "exit_only")


# ======================================================================================================== eligibility
@unittest.skipUnless(HAVE, "numpy not installed")
class Eligibility(Base):
    """Each condition removed alone: no pin."""

    def pinned(self, rows=(), *, before=None, **kw) -> list:
        live = self.first(rows, **kw)
        if before is not None:
            before(live)
        self.run_to(9, 31)
        return self.pins().get("order") or []

    def test_the_eligible_baseline_is_pinned(self):
        self.assertEqual(self.pinned(), ["fam@1:i"])

    def test_no_facts_row_retired_or_out_of_the_gym(self):
        self.assertEqual(self.pinned(incubate=False), [])

    def test_a_d2_row_for_the_family(self):
        for band, holdout in (("gym", False), ("candidate", True), ("probe", True)):
            with self.subTest(band=band):
                self.assertEqual(self.pinned([family("fam", VERTICAL, band=band, holdout=holdout, validation=True)]), [])
                self.live.state.close()
                self.setUp()

    def test_a_failed_cohort_an_evaluator_change_or_stale_trades(self):
        self.assertEqual(self.pinned(status="failed", reason="disqualified"), [])
        self.live.state.close()
        self.setUp()
        self.assertEqual(self.pinned(evaluator="an-old-evaluator"), [])
        self.live.state.close()
        self.setUp()
        self.assertEqual(self.pinned(trade_evaluator="an-old-evaluator"), [])
        self.assertEqual(self.verdicts(), {}, "stale trades are not this cohort's sample")
        self.live.state.close()
        self.setUp()
        self.assertEqual(self.pinned(practice_first="2026-09-22"), [], "a practice row older than its cohort")

    def test_structures_real_money_does_not_trade(self):
        # Money rules v3 (D3): a credit type is a real type, from $2,000 of sizing equity (the fixture's grant and account
        # are over it); under it, shadow only.
        self.assertEqual(self.pinned(structure="credit_vertical"), ["fam@1:i"], "credit at $2,000 or more")
        self.live.state.close()
        self.setUp()
        self.grant.capital = "1999.99"
        self.assertEqual(self.pinned(structure="credit_vertical"), [], "credit under $2,000")
        self.assertIn("credit structure", self.pins()["refused"]["fam@1"])
        self.live.state.close()
        self.setUp()
        self.assertEqual(self.pinned(structure="long_strangle"), [])
        self.live.state.close()
        self.setUp()
        c = copy.deepcopy(CONSTITUTION)
        c["options_money"]["real_types"] = ["debit_vertical", "long_butterfly", "long_call"]
        self.assertEqual(self.pinned(structure="long_single", table=M.Table.from_constitution(c)), [],
                         "a long_single with one single not real")

    def test_the_facts_run_sha_differs_from_the_snapshots(self):
        self.assertEqual(self.pinned(facts_sha="another-sha"), [])

    def test_no_close_that_one_lot_could_open(self):
        self.assertEqual(self.pinned(trades=winning(10, max_loss=60.0)), [])
        self.assertTrue(self.verdicts()["fam@1"]["passed"], "its first look passed; it could never open")
        self.assertIn("could never open", self.pins()["refused"]["fam@1"])

    def test_unreadable_stores_fail_closed(self):
        def broken_facts(live):
            self.families.incubator_error = sqlite3.OperationalError("database is locked")

        self.assertEqual(self.pinned(before=broken_facts), [])
        self.assertTrue(any("facts could not be read" in text for _, text in self.alerts))
        self.live.state.close()
        self.setUp()

        def broken_practice(live):
            live.observe_store.close()
            (self.root / "observe.sqlite").write_bytes(b"garbage" * 1000)
            for suffix in ("-wal", "-shm"):
                try:
                    (self.root / f"observe.sqlite{suffix}").unlink()
                except FileNotFoundError:
                    pass

        self.assertEqual(self.pinned(before=broken_practice), [])

    def test_real_money_off_or_a_table_at_zero(self):
        self.assertEqual(self.pinned(real_money=False), [])
        for row in ({"max_open": 0}, {"week_loss_usd": "0"}, {"max_loss_usd": "0"}):
            self.live.state.close()
            self.setUp()
            self.assertEqual(self.pinned(table=table(**row)), [], row)

    def test_at_most_eight_by_return_on_risk_one_per_family(self):
        live = self.make()
        for i in range(10):
            self.cohort(f"f{i}", 1, trades=winning(10, pnl=1.0 + i))
        self.run_to(9, 31)
        self.assertEqual(self.pins()["order"], [f"f{i}@1:i" for i in range(9, 1, -1)])
        del live

    def test_pins_come_only_from_todays_kept_cohorts(self):
        """The review's case (Sept 30): the best-ranked cohort has a D2 row, so it is kept (L2') but never pinned, and the
        ninth-ranked is not pinned in its place: it is not kept, so the practice league could complete it mid-session."""
        live = self.make([family("f9", VERTICAL, band="gym", holdout=False, validation=True)])
        for i in range(10):
            self.cohort(f"f{i}", 1, trades=winning(10, pnl=1.0 + i))
        self.run_to(9, 31)
        kept = {tuple(c) for c in live.state.get(INC.KEEP)["cohorts"]}
        self.assertEqual(kept, {(f"f{i}", 1) for i in range(2, 10)})
        self.assertEqual(self.pins()["order"], [f"f{i}@1:i" for i in range(8, 1, -1)])
        self.assertTrue({(k[: -len(INC.SUFFIX)].rsplit("@", 1)[0], 1) for k in self.pins()["order"]} <= kept)
        self.assertIn("D2", self.pins()["refused"]["f9@1"])
        self.assertIn("kept cohorts", self.pins()["refused"]["f1@1"])


# ================================================================================================ the weekly stop
@unittest.skipUnless(HAVE, "numpy not installed")
class TheWeeklyStop(Base):
    def test_the_minute_records_the_stop_when_a_close_reaches_it_and_health_shows_it_before(self):
        """The stop is the plan's (from the live state's closes, at every open); the record and the alert come at the
        minute an incubator structure leaves the book, not only at the next open, and health derives it until then."""
        live = self.first()
        self.run_to(9, 31)
        self.assertEqual(len(self.opens()), 1)
        live.state.upsert("positions", {"pid": 9000, "instance": "old@1:i", "family": "old", "type": "debit_vertical",
                                        "root": "SPY", "legs": "[]", "qty": 0, "opened_qty": 1, "entry": 0.4,
                                        "max_loss_share": 0.4, "collateral": 0.0, "fees": 1.0, "cash": -150.0,
                                        "opened_at": 1.0, "opened_day": "2026-09-28", "opened_minute": 1,
                                        "status": "closed", "closed_at": at(MONDAY, 9, 0), "tuition": 1, "info": "{}"},
                          "pid")
        self.assertIsNone(live.state.get(INC.WEEK))
        shown = live.health()["incubator"]["week_stopped"]
        self.assertEqual(shown["week"], "2026-09-28")
        self.assertIn("not yet recorded", shown["why"])
        self.run_to(9, 45)
        self.assertEqual(live.state.get(INC.WEEK)["week"], "2026-09-28")
        said = [t for _, t in self.alerts if "stopped for the rest of the week" in t]
        self.assertEqual(len(said), 1, "once a week")
        self.assertEqual(len(self.opens()), 1, "no open after it")


# ======================================================================================================== the switch
@unittest.skipUnless(HAVE, "numpy not installed")
class TheSwitch(Base):
    def test_off_sends_its_instances_to_exits_within_a_minute_and_cancels_their_opens(self):
        self.venue.fill = "none"
        live = self.first()
        self.run_to(9, 31)
        [row] = self.opens()
        self.assertEqual(row["status"], "working")
        self.switch(False)
        self.run_to(9, 32)
        self.assertEqual(live.instances["fam@1:i"].mode, "exit_only")
        self.assertIsNotNone(self.opens()[0]["cancel_sent"], "cancelled within the minute")
        self.run_to(9, 33)
        self.assertEqual(self.opens()[0]["status"], "cancelled")

    def test_a_malformed_value_reads_off_and_is_said_once(self):
        self.switch("true")
        live = self.first()
        self.run_to(9, 33)
        self.assertFalse(live.switches()["incubator"])
        said = [t for _, t in self.alerts if "live.incubator" in t]
        self.assertEqual(len(said), 1)
        self.assertEqual(self.opens(), [])

    def test_the_default_is_off(self):
        from league.swarm.settings import DEFAULTS

        self.assertIs(DEFAULTS["live"]["incubator"], False)
        (self.root / "swarm.json").write_text(json.dumps({"live": {"calibration": False, "observe": False}}))
        live = self.first()
        self.run_to(9, 31)
        self.assertEqual(self.opens(), [])
        self.assertEqual(live.health()["incubator"]["pins"]["closed"], "incubator: live.incubator is off")
        self.assertTrue(self.verdicts()["fam@1"]["passed"], "the first look is taken all the same")


# ================================================================================================= stops and blocks
@unittest.skipUnless(HAVE, "numpy not installed")
class StopsAndBlocks(Base):
    def blocked(self, setup, **kw) -> list:
        live = self.first(**kw)
        setup(live)
        self.run_to(9, 32)
        return self.opens()

    def test_every_real_entry_block_stops_an_incubator_open(self):
        def kill(live):
            self.killed = True

        def daily(live):
            live.stops.daily_tripped, live.stops.daily_why = True, "test"
            live.stops.day = "2026-09-28"
            live.state.put("stops", live.stops.as_state())

        def drawdown(live):
            live.stops.drawdown_tripped, live.stops.drawdown_why = True, "test"
            live.state.put("stops", live.stops.as_state())

        def frozen(live):
            live.state.put("recon", {"frozen": "a mismatch", "bad": 5, "good": 0})
            live.book.load()
            self.venue.extra_positions.append({"symbol": "QQQ261002C00400000", "asset_class": "us_option", "qty": "1",
                                               "side": "long"})

        def unpriced(live):
            live.state.upsert("positions", {"pid": 99, "instance": "x@1:t", "family": "x", "type": "debit_vertical",
                                            "root": "SPY", "legs": "[]", "qty": 0, "opened_qty": 1, "entry": 0.1,
                                            "max_loss_share": 0.1, "collateral": 0, "fees": 0, "cash": -10, "opened_at": 1,
                                            "opened_day": "2026-09-25", "opened_minute": 1, "status": "unpriced_close",
                                            "info": "{}"}, "pid")

        def latch(live):
            live.state.put("assignment_latch", {"why": "an assignment", "at": 1})
            live.state.put("shares", {"SPY": 100})           # unresolved: the latch holds

        def grant(live):
            self.grant.active = False

        for name, setup in (("kill", kill), ("daily", daily), ("drawdown", drawdown), ("frozen", frozen),
                            ("unpriced", unpriced), ("latch", latch), ("grant", grant)):
            with self.subTest(name):
                self.assertEqual(self.blocked(setup), [], name)
                self.live.state.close()
                self.killed = False
                self.grant = Grant()
                self.setUp()

    def test_no_paper_proof_and_no_single_leg_proof_for_a_long_call(self):
        live = self.first(config={"require_paper_proof": True})
        self.run_to(9, 32)
        self.assertEqual(self.opens(), [], "no paper proof")
        self.live.state.close()
        self.setUp()
        params = dict(PARAMS, type="long_call", atm=6)
        live = self.first(config={"require_paper_proof": True}, params=params, structure="long_call")
        live.state.put("paper_proof", {"schema": 2, "status": "passed", "open_witness": True, "close_witness": True})
        live.proof_single.passed = lambda: False
        self.run_to(9, 32)
        self.assertEqual(self.opens(), [], "no single-leg proof")
        refusals = [p["why"] for p, a in self.ledger.of("live.refusal") if a == "fam"]
        self.assertTrue(any("single-leg route" in why for why in refusals), refusals)

    def test_the_house_paused_blocks_it(self):
        live = self.first()
        live.house_open = False                             # as `tick(open_for_business=False)` sets it
        self.run_to(9, 32)
        self.assertEqual(self.opens(), [])

    def test_exits_still_go_under_the_daily_stop(self):
        live = self.first()
        self.run_to(9, 31)
        self.assertEqual(len(self.opens()), 1)
        live.stops.daily_tripped, live.stops.daily_why, live.stops.day = True, "test", "2026-09-28"
        live.state.put("stops", live.stops.as_state())
        self.run_to(9, 40)
        closes = live.state.rows("SELECT * FROM orders WHERE action='close' AND family='fam'")
        self.assertTrue(closes, "its own close went")


# ================================================================================================ never evidence
@unittest.skipUnless(HAVE, "numpy not installed")
class NeverEvidence(Base):
    def test_thirty_winning_incubator_trades_move_nothing(self):
        """No band move, no set_band or confirm_band, `bands.read` unchanged, no `:r` and no forward row."""
        live = self.first()
        read_before = self.families.read()
        for i in range(30):
            live.state.upsert("positions", {"pid": 100 + i, "instance": "fam@1:i", "family": "fam", "type": "debit_vertical",
                                            "root": "SPY", "legs": "[]", "qty": 0, "opened_qty": 1, "entry": 0.3,
                                            "max_loss_share": 0.3, "collateral": 0, "fees": 1, "cash": 25.0, "opened_at": 1,
                                            "opened_day": "2026-09-25", "opened_minute": 1, "status": "closed",
                                            "closed_at": 2.0, "tuition": 1, "info": "{}"}, "pid")
        spied = {"forward_rows": 0, "set_band": 0, "confirm_band": 0, "add_forward": 0}
        for name in spied:
            original = getattr(self.families, name)

            def spy(*a, _name=name, _original=original, **k):
                spied[_name] += 1
                return _original(*a, **k)

            setattr(self.families, name, spy)
        self.run_to(9, 40)
        self.assertEqual(spied, {"forward_rows": 0, "set_band": 0, "confirm_band": 0, "add_forward": 0})
        self.assertEqual(self.families.moves, [])
        self.assertEqual(self.families.read(), read_before)
        self.assertEqual(self.families.forward, {})
        self.assertFalse([k for k in live.instances if k.endswith(":r")])
        exported = {r["pid"] for r in live.state.rows("SELECT pid FROM forward_exports")}
        self.assertTrue(set(range(100, 130)) <= exported, "marked exported, never sent")

    def test_the_export_belt_skips_an_incubator_row_even_without_its_tuition_flag(self):
        live = self.make()
        live.state.upsert("positions", {"pid": 7, "instance": "fam@1:i", "family": "fam", "type": "debit_vertical",
                                        "root": "SPY", "legs": "[]", "qty": 0, "opened_qty": 1, "entry": 0.3,
                                        "max_loss_share": 0.3, "collateral": 0, "fees": 1, "cash": 25.0, "opened_at": 1,
                                        "opened_day": "2026-09-25", "opened_minute": 1, "status": "closed", "closed_at": 2.0,
                                        "tuition": 0, "info": "{}"}, "pid")
        live._export_real()
        self.assertEqual(self.families.forward, {})
        self.assertEqual([r["pid"] for r in live.state.rows("SELECT pid FROM forward_exports")], [7])

    def test_an_incubator_row_admits_only_an_incubator_identity(self):
        inc = {"family": "fam", "version": 1, "band": "gym", "incubator": True, "run_sha": "s"}
        ident = {"family": "fam", "version": 1, "band": "gym", "tuition": True, "observe": False, "incubator": True,
                 "run_sha": "s", "code": PROGRAM, "params": {}}
        self.assertTrue(_entry_matches(inc, ident, True))
        self.assertFalse(_entry_matches(inc, ident, False), "never a shadow open")
        self.assertFalse(_entry_matches(inc, dict(ident, tuition=False), True))
        self.assertFalse(_entry_matches(inc, dict(ident, run_sha="t"), True))
        self.assertFalse(_entry_matches(inc, dict(ident, incubator=False, band="gym", tuition=True), True),
                         "an incubator row never admits a tuition identity")
        tuition_row = {"family": "fam", "version": 1, "band": "gym", "validation_passed": True, "holdout_passed": False,
                       "code": PROGRAM, "params": {}}
        self.assertFalse(_entry_matches(tuition_row, ident, True), "a tuition row never admits an incubator identity")

    def test_the_swarm_never_reads_the_incubators_real_rows(self):
        """A static guard (SPEC-B §3.4): the swarm's evidence, gate, research and band readers never name the live
        state, the real book, the incubator's tally or its instances."""
        banned = re.compile(r"live\.sqlite|RealBook|incubator_tally|[\"']:i[\"']")
        swarm = REPO / "league" / "swarm"
        for name in ("evidence.py", "researcher.py", "strategist.py", "architect.py", "diagnostician.py",
                     "claude_research.py", "models.py", "gate.py", "tournament.py"):
            path = swarm / name
            if path.exists():
                self.assertIsNone(banned.search(path.read_text(encoding="utf-8")), name)
        import inspect

        from league.swarm import bands

        self.assertIsNone(banned.search(inspect.getsource(bands.read)))
        self.assertIsNone(re.compile(r"\bweight\b").search((REPO / "league" / "live" / "incubator.py").read_text()))

    def test_the_site_labels_its_positions_and_structures(self):
        from league import publish
        from league.trading_profit import INCUBATOR_SUFFIX, source_of

        from league.live.real import INCUBATOR_SUFFIX as LIVE_SUFFIX

        self.assertEqual(INCUBATOR_SUFFIX, LIVE_SUFFIX)
        self.assertEqual(source_of("fam", "fam@1:i"), "incubator")
        self.assertEqual(source_of("fam", "fam@1:t"), "agent")
        self.assertEqual(source_of("house:calibration", "house:calibration@0:i"), "calibration")
        row = {"pid": 3, "source": "incubator", "family": "fam", "underlying": "SPY", "structure": "debit_vertical",
               "right": "call", "legs": 2, "quantity": 1, "open_quantity": 1, "status": "open", "expiry": "2026-09-29",
               "opened_at": "2026-09-28T13:31:00Z", "pnl_usd": "1.00"}
        shown = publish.site_position(row, "2026-09-28T14:00:00.000Z")
        self.assertEqual((shown["source"], shown["agent"]), ("incubator", "fam"))
        self.assertIsNone(publish.site_position(dict(row, family="Not A Slug!"), "2026-09-28T14:00:00.000Z"))
        structure = {"agent": "fam", "underlying": "SPY", "structure": "debit_vertical", "legs": 2, "expiry": "2026-09-29",
                     "quantity": 1, "real": True, "opened_at": "2026-09-28T13:31:00Z", "max_loss_usd": 30.0,
                     "pnl_usd": 1.0, "route": "incubator"}
        self.assertEqual(publish.site_structure(structure, "2026-09-28T14:00:00.000Z")["route"], "incubator")
        self.assertNotIn("route", publish.site_structure(dict(structure, real=False), "2026-09-28T14:00:00.000Z"))
        self.assertNotIn("route", publish.site_structure(dict(structure, route="other"), "2026-09-28T14:00:00.000Z"))
        self.assertNotIn("route", publish.site_structure({k: v for k, v in structure.items() if k != "route"},
                                                         "2026-09-28T14:00:00.000Z"))

    def test_the_live_structures_carry_the_route(self):
        self.venue.fill = "natural"
        live = self.first(params=dict(PARAMS, hold=600))
        self.run_to(9, 32)
        rows = [r for r in live.site_inputs()["structures"] if r["real"]]
        self.assertEqual([r.get("route") for r in rows], ["incubator"])
        self.assertEqual(rows[0]["agent"], "fam")


# ================================================================================================ D2, tuition, ordering
@unittest.skipUnless(HAVE, "numpy not installed")
class D2AndOrdering(Base):
    def test_a_family_that_validates_mid_session_moves_from_its_incubator_to_tuition(self):
        live = self.first(params=dict(PARAMS, hold=600))
        self.run_to(9, 31)
        self.assertEqual(live.instances["fam@1:i"].mode, "live")
        self.families.rows["fam"] = family("fam", VERTICAL, band="gym", holdout=False, validation=True)
        self.clock.set(self.clock() + 300)
        self.run_to(9, 37)
        self.assertEqual(live.instances["fam@1:i"].mode, "exit_only")
        self.assertIn("fam@1:t", live.instances)

    def test_the_incubators_tuition_is_never_tuitions_and_a_tuition_family_is_never_incubated(self):
        live = self.first(params=dict(PARAMS, hold=600))
        self.run_to(9, 31)
        exposure = live.book.exposure("fam", day="2026-09-28", week_start="2026-09-28")
        self.assertEqual((exposure.tuition_day, exposure.tuition_week), (D(0), D(0)))
        self.assertGreater(exposure.family_loss, 0, "its held structure still counts in the family's and the book's")

    def test_a_d2_family_decides_before_the_incubator_within_the_minute(self):
        self.first([family("pro", VERTICAL, band="probe")])
        self.run_to(9, 31)
        opens = [str(b.get("client_order_id") or "") for b in self.venue.sent]
        self.assertEqual(len(opens), 2)
        self.assertTrue(opens[0].endswith("-pro") and opens[1].endswith("-fam"), opens)

    def test_three_families_in_one_minute_read_the_tally_afresh(self):
        live = self.make(table=table(max_open=2))
        self.venue.fill = "none"
        for fid, atm in (("fa", 2), ("fb", 4), ("fc", 6)):            # contracts apart: one stream per contract
            self.cohort(fid, 1, params=dict(PARAMS, atm=atm))
        self.run_to(9, 31)
        sent = [str(b.get("client_order_id") or "") for b in self.venue.sent]
        self.assertEqual(len(sent), 2, sent)
        refusals = [p["why"] for p, a in self.ledger.of("live.refusal")]
        self.assertTrue(any("the most it holds is 2" in why for why in refusals), refusals)
        del live

    def test_the_incubator_yields_its_working_open_to_a_later_d2_refusal_on_its_contracts(self):
        live = self.first()
        self.venue.fill = "none"
        self.run_to(9, 31)
        [row] = self.opens()
        symbol = json.loads(row["legs"])[0]["symbol"]
        self.clock.set(self.clock() + 60)
        live.book._reject("pro@1:r", f"one order stream per contract: {symbol} already has a working order (x)")
        live.incubator.step(live.day, 2, {})
        self.assertEqual(json.loads(self.opens()[0]["answer"]).get("cancel"), INC.YIELDED)
        self.assertTrue([p for p, a in self.ledger.of("live.incubator") if p.get("yielded") == row["oid"]])

    def test_an_older_refusal_or_a_non_d2_one_never_yields(self):
        live = self.first()
        self.venue.fill = "none"
        live.book._reject("pro@1:r", "one order stream per contract: SPY260929C00604000 already has a working order")
        self.run_to(9, 31)
        [row] = self.opens()
        symbol = json.loads(row["legs"])[0]["symbol"]
        live.book._reject("house:rebound-live@0:h", f"one order stream per contract: {symbol} already has a working order")
        live.book._reject("other@1:o", f"one order stream per contract: {symbol} already has a working order")
        live.incubator.step(live.day, 2, {})
        self.assertEqual(self.opens()[0]["status"], "working")
        self.assertIsNone(self.opens()[0]["cancel_sent"])

    def test_calibration_and_the_house_test_yield_to_an_incubator_refusal_on_their_contracts(self):
        """Their pre-registered `_yield`s read every other instance's refusals: an incubator's now counts as a family's."""
        import inspect

        from league.live import house_test as HT

        source = inspect.getsource(HT.HouseTest._yield)
        self.assertIn("if instance in (INSTANCE, C.INSTANCE)", source, "the test skips only its own and the calibration's")
        source = inspect.getsource(C.Calibration._yield)
        self.assertIn("if instance != INSTANCE", source, "the calibration skips only its own")
        self.assertTrue(is_incubator("fam@1:i"))


# ======================================================================================================== L2'
@unittest.skipUnless(HAVE, "numpy not installed")
class L2Prime(Base):
    def setUp(self):
        super().setUp()
        self.switch(True, observe=True)

    def status(self, fid="fam", n=1):
        return self.live.observe_store._connect().execute(
            "SELECT status, reason FROM cohorts WHERE family=? AND version=?", (fid, n)).fetchone()

    def test_a_passed_cohort_keeps_practising_past_its_target_while_the_switch_is_on(self):
        self.first()
        self.run_to(9, 31)
        self.assertEqual(self.live.state.get(INC.KEEP)["cohorts"], [["fam", 1]])
        self.assertEqual(self.status(), ("active", None))

    def test_with_the_switch_off_the_leagues_own_rule_completes_it(self):
        self.switch(False, observe=True)
        self.first()
        self.run_to(9, 31)
        self.assertEqual(self.status(), ("complete", "observation target reached"))

    def test_the_window_still_ends_a_kept_cohort(self):
        self.first(first_day="2026-09-10", practice_first="2026-09-10")
        self.run_to(9, 31)
        self.assertEqual(self.status(), ("complete", "maximum session window reached"))

    def test_at_most_eight_are_kept(self):
        self.make()
        for i in range(10):
            self.cohort(f"f{i}", 1, trades=winning(10, pnl=1.0 + i))
        self.run_to(9, 31)
        kept = self.live.state.get(INC.KEEP)["cohorts"]
        self.assertEqual(kept, [[f"f{i}", 1] for i in range(9, 1, -1)])
        statuses = {f"f{i}": self.status(f"f{i}")[1] for i in range(10)}
        self.assertEqual(statuses["f0"], "observation target reached")
        self.assertIsNone(statuses["f9"])


@unittest.skipUnless(HAVE, "numpy not installed")
class L2PrimeReadFailures(Base):
    """The review's case (Sept 30): one unreadable read at a session's first families pass must never end a passed
    incubation. The keep carries the last keep's cohorts (practising, never pinned), is not settled, and the next
    families pass (`FAMILIES_EVERY` later) takes the checks again."""

    def setUp(self):
        super().setUp()
        self.switch(True, observe=True)

    status = L2Prime.status

    def monday(self):
        self.first()
        self.run_to(9, 31)
        self.assertEqual(self.pins()["order"], ["fam@1:i"])
        self.assertEqual(self.live.state.get(INC.KEEP)["cohorts"], [["fam", 1]])
        self.clock.set(at(TUESDAY, 9, 31))

    def carried(self, why):
        """Tuesday's first pass could not take the check: still active, kept, carried, not pinned, never ended."""
        self.assertEqual(self.status(), ("active", None), why)
        keep = self.live.state.get(INC.KEEP)
        self.assertEqual((keep["day"], keep["cohorts"], keep["carried"], keep["unread"]),
                         ("2026-09-29", [["fam", 1]], [["fam", 1]], True))
        self.assertFalse(self.live.incubator.checked("2026-09-29"))
        self.assertEqual(self.pins()["order"], [], "never pinned on an untaken check")
        self.assertIn("could not be taken", self.pins()["refused"]["fam@1"])
        self.assertNotIn("ended", self.verdicts()["fam@1"])
        self.assertEqual(self.live.instances["fam@1:o"].mode, "live", "it goes on practising")
        self.assertNotIn("fam@1:i", self.live.instances)
        self.assertTrue([p for p, _ in self.ledger.of("live.incubator") if p.get("keep_carried") == ["fam@1"]])

    def recovered(self):
        """The next families pass reads again: today's check taken and passed, the keep settled, the pins of the day
        unchanged (no mid-session join), and the next session pins it again."""
        self.run_to(9, 35)
        self.assertFalse(self.live.incubator.checked("2026-09-29"), "no retry before FAMILIES_EVERY")
        self.run_to(9, 36)
        verdict = self.verdicts()["fam@1"]
        self.assertEqual((verdict["latest"]["day"], verdict["latest"]["ok"]), ("2026-09-29", True), verdict["latest"])
        keep = self.live.state.get(INC.KEEP)
        self.assertEqual(keep, {"day": "2026-09-29", "cohorts": [["fam", 1]]})
        self.assertTrue(self.live.incubator.checked("2026-09-29"))
        self.assertEqual(self.pins()["order"], [], "no mid-session join")
        self.assertEqual(self.status(), ("active", None))
        self.clock.set(at(TUESDAY, 9, 31) + 86400)
        self.run_to(9, 31)
        self.assertEqual(self.pins()["order"], ["fam@1:i"])
        self.assertEqual(self.status(), ("active", None))
        self.assertNotIn("ended", self.verdicts()["fam@1"])

    def test_unreadable_cohorts_at_the_first_pass_keep_it_and_the_next_pass_recovers(self):
        self.monday()
        with mock.patch.object(INC, "cohort_rows", return_value=None):
            self.run_to(9, 31)
        self.carried("the cohorts could not be read")
        self.assertTrue([p for p, _ in self.ledger.of("live.incubator") if p.get("unread") == "cohorts"])
        self.assertEqual(len([t for _, t in self.alerts if "could not read the practice cohorts" in t]), 1)
        self.recovered()

    def test_an_unreadable_recheck_record_keeps_it_never_ends_it_and_the_next_pass_recovers(self):
        self.monday()
        with mock.patch.object(INC, "practice_record", return_value=None):
            self.run_to(9, 31)
        self.carried("the re-check's record could not be read")
        latest = self.verdicts()["fam@1"]["latest"]
        self.assertEqual((latest["day"], latest["ok"], latest["unread"]), ("2026-09-29", False, True))
        self.assertEqual(len([p for p, _ in self.ledger.of("live.incubator") if p.get("unread") == "fam@1"]), 1)
        self.assertEqual(len([t for _, t in self.alerts if "could not read fam@1's practice record" in t]), 1)
        self.recovered()

    def test_first_looks_that_raise_keep_it_and_the_next_pass_recovers(self):
        self.monday()
        with mock.patch.object(INC.M, "practice_ok", side_effect=RuntimeError("boom")):
            self.run_to(9, 31)
        self.carried("the first looks raised")
        self.assertEqual(len([t for _, t in self.alerts if "first looks failed (RuntimeError" in t]), 1)
        self.recovered()

    def test_a_record_that_fails_at_the_retry_still_ends_it(self):
        self.monday()
        with mock.patch.object(INC, "practice_record", return_value=None):
            self.run_to(9, 31)
        self.carried("unread")
        db = self.live.observe_store._connect()
        db.execute("INSERT INTO trades(instance, account, family, version, trade_id, day, pnl, max_loss, recorded_at, body, "
                   "exit_day, reason, forced, evaluator) VALUES('fam@1:o', 'a', 'fam', 1, 'loss', '2026-09-28', -80, 30, 1, "
                   "'{}', '2026-09-28', 'program', 0, ?)", (self.live.observe_store.evaluator,))
        self.run_to(9, 36)
        verdict = self.verdicts()["fam@1"]
        self.assertTrue(verdict["ended"]["why"].startswith("P4"))
        self.assertEqual(self.live.state.get(INC.KEEP), {"day": "2026-09-29", "cohorts": []}, "the league's own rule again")
        self.assertTrue(self.live.incubator.checked("2026-09-29"))

    def test_an_unread_cohort_that_completes_meanwhile_settles_the_keep(self):
        self.monday()
        with mock.patch.object(INC, "practice_record", return_value=None):
            self.run_to(9, 31)
        self.live.observe_store._connect().execute(
            "UPDATE cohorts SET status='complete', completed_day='2026-09-29', reason='maximum session window reached'")
        self.run_to(9, 36)
        self.assertTrue(self.live.incubator.checked("2026-09-29"), "no read again every pass for the rest of the day")
        self.assertEqual(self.live.state.get(INC.KEEP), {"day": "2026-09-29", "cohorts": []})
        self.assertFalse(self.verdicts()["fam@1"]["latest"]["unread"])
        self.assertNotIn("ended", self.verdicts()["fam@1"])

    def test_a_first_look_that_cannot_read_its_record_is_kept_until_it_is_read(self):
        self.first()
        with mock.patch.object(INC, "practice_record", return_value=None):
            self.run_to(9, 31)
        self.assertEqual(self.verdicts(), {})
        self.assertEqual(self.status(), ("active", None), "not completed at its target before its first look")
        self.assertTrue([p for p, _ in self.ledger.of("live.incubator") if p.get("unread") == "fam@1"])
        keep = self.live.state.get(INC.KEEP)
        self.assertEqual((keep["cohorts"], keep["carried"], keep["unread"]), ([["fam", 1]], [["fam", 1]], True))
        self.assertEqual(self.pins()["order"], [])
        self.run_to(9, 36)
        self.assertTrue(self.verdicts()["fam@1"]["passed"])
        self.assertEqual(self.live.state.get(INC.KEEP), {"day": "2026-09-28", "cohorts": [["fam", 1]]})
        self.assertEqual(self.pins()["order"], [], "no mid-session join")
        self.clock.set(at(TUESDAY, 9, 31))
        self.run_to(9, 31)
        self.assertEqual(self.pins()["order"], ["fam@1:i"])

    def test_with_the_switch_off_a_read_failure_changes_nothing(self):
        self.switch(False, observe=True)
        self.first()
        with mock.patch.object(INC, "cohort_rows", return_value=None):
            self.run_to(9, 31)
        self.assertIsNone(self.live.state.get(INC.KEEP))
        self.assertTrue(self.live.incubator.checked("2026-09-28"))
        self.assertEqual(self.status(), ("complete", "observation target reached"))


@unittest.skipUnless(HAVE, "numpy not installed")
class TheFirstPassRetry(Base):
    """The review's nit (Sept 30): the incubator asks for the session's first families pass at once, once a session day;
    a pass that could not pin (the bands unreadable, its pins raised) is taken again `FAMILIES_EVERY` later, not every
    minute, with both switches off."""

    def setUp(self):
        super().setUp()
        self.switch(False)

    def test_unreadable_bands_are_read_again_every_five_minutes_not_every_minute(self):
        self.first()
        with mock.patch.object(self.families, "read", side_effect=sqlite3.OperationalError("database is locked")):
            self.run_to(9, 35)
        self.assertEqual(len([t for _, t in self.alerts if "bands could not be read" in t]), 1)
        self.assertTrue(self.live.incubator.due("2026-09-28"))
        self.run_to(9, 36)
        self.assertEqual(self.pins()["day"], "2026-09-28")
        self.assertEqual(self.pins()["closed"], "incubator: live.incubator is off")
        self.assertTrue(self.verdicts()["fam@1"]["passed"], "the first look is taken off too")

    def test_pins_that_raise_are_taken_again_every_five_minutes_not_every_minute(self):
        self.first()
        judged = mock.patch.object(INC.Incubator, "judge", wraps=self.live.incubator.judge)
        with mock.patch.object(INC.Incubator, "_pin", side_effect=RuntimeError("boom")), judged as judge:
            self.run_to(9, 35)
        self.assertEqual(len([t for _, t in self.alerts if "the incubator's pins failed" in t]), 1)
        self.assertEqual(judge.call_count, 1, "the first looks are not read again every minute")
        self.run_to(9, 36)
        self.assertEqual(self.pins()["day"], "2026-09-28")


@unittest.skipUnless(HAVE, "numpy not installed")
class L2PrimeSecondReview(Base):
    """The second review of the keep (Sept 30): two read faults in a row, a keep recomputed within the day, a keep that
    raises or a ledger that fails, a retried check on the practice row's live values, and a read that never recovers."""

    def setUp(self):
        super().setUp()
        self.switch(True, observe=True)

    status = L2Prime.status

    def new_cohort(self, fid="z", pnl=20.0, **kw):
        """A cohort that reaches its sample on the current day (its first look is due at this session's first pass)."""
        self.cohort(fid, 1, trades=winning(10, pnl=pnl), params=dict(PARAMS, opens=0), **kw)
        self.live.observe_store._connect().execute("UPDATE practice SET last_at=? WHERE family=?",
                                                   (self.clock() - 3600, fid))

    @staticmethod
    def unread_for(*families):
        real = INC.practice_record

        def flaky(root, f, n, **kw):
            return None if f in families else real(root, f, n, **kw)
        return mock.patch.object(INC, "practice_record", side_effect=flaky)

    @staticmethod
    def marked(mark=-1000.0):
        """The practice row's open mark at a retried pass: a P6 failure on the live value alone."""
        real = INC.practice_record

        def marked(root, f, n, **kw):
            record = real(root, f, n, **kw)
            return None if record is None else dict(record, open_mark=mark)
        return mock.patch.object(INC, "practice_record", side_effect=marked)

    def kept(self):
        return [tuple(c) for c in self.live.state.get(INC.KEEP)["cohorts"]]

    def monday(self):
        self.first()
        self.run_to(9, 31)
        self.assertEqual(self.pins()["order"], ["fam@1:i"])
        self.clock.set(at(TUESDAY, 9, 31))

    def test_a_first_look_unread_then_the_cohorts_unread_still_keeps_it(self):
        self.monday()
        self.new_cohort()
        with self.unread_for("z"):
            self.run_to(9, 31)
        self.assertIn(("z", 1), self.kept())
        with mock.patch.object(INC, "cohort_rows", return_value=None):
            self.run_to(9, 36)
        self.assertEqual(self.status("z"), ("active", None), "held: not completed at its target before its first look")
        self.assertIn(("z", 1), self.kept())
        self.assertEqual(self.status(), ("active", None))
        self.run_to(9, 41)
        self.assertTrue(self.verdicts()["z@1"]["passed"])
        self.assertEqual(self.status("z"), ("active", None))
        self.assertTrue(self.live.incubator.checked("2026-09-29"))
        self.assertEqual(self.pins()["order"], ["fam@1:i"], "no mid-session join")
        self.clock.set(at(TUESDAY, 9, 31) + 86400)
        self.run_to(9, 31)
        self.assertEqual(sorted(self.pins()["order"]), ["fam@1:i", "z@1:i"])

    def test_a_first_look_unread_then_a_restart_then_the_cohorts_unread_still_keeps_it(self):
        self.first()
        with mock.patch.object(INC, "practice_record", return_value=None):
            self.run_to(9, 31)
        self.assertEqual(self.kept(), [("fam", 1)])
        self.restart()
        with mock.patch.object(INC, "cohort_rows", return_value=None):
            self.run_to(9, 36)
        self.assertEqual(self.status(), ("active", None))
        self.assertEqual(self.kept(), [("fam", 1)])
        self.clock.set(at(TUESDAY, 9, 31))
        with mock.patch.object(INC, "cohort_rows", return_value=None):
            self.run_to(9, 31)
        self.assertEqual(self.status(), ("active", None), "the next day too")
        self.assertEqual(self.pins()["order"], [])

    def test_the_cohorts_unread_hold_a_cohort_that_reaches_its_sample_that_day(self):
        self.monday()
        self.new_cohort()
        with mock.patch.object(INC, "cohort_rows", return_value=None):
            self.run_to(9, 31)
        self.assertTrue(self.live.incubator.holding("2026-09-29"))
        self.assertEqual(self.status("z"), ("active", None), "no cohort is completed at its target on an unread pass")
        self.assertEqual(self.pins()["order"], [])
        self.run_to(9, 36)
        self.assertFalse(self.live.incubator.holding("2026-09-29"))
        self.assertTrue(self.verdicts()["z@1"]["passed"])
        self.assertEqual(sorted(self.kept()), [("fam", 1), ("z", 1)])
        self.assertEqual(self.status("z"), ("active", None))
        self.assertEqual(self.status(), ("active", None))

    def test_a_late_first_look_never_displaces_a_cohort_kept_and_pinned_earlier_that_day(self):
        self.make()
        for i in range(8):
            self.cohort(f"f{i}", 1, trades=winning(10, pnl=1.0 + i))
        self.run_to(9, 31)
        self.assertEqual(len(self.pins()["order"]), 8)
        self.clock.set(at(TUESDAY, 9, 31))
        self.new_cohort()
        with self.unread_for("z"):
            self.run_to(9, 31)
        self.assertEqual(len(self.pins()["order"]), 8)
        self.assertEqual(self.status("z"), ("active", None), "held beyond the cap while its first look is unread")
        self.run_to(9, 41)
        self.assertTrue(self.verdicts()["z@1"]["passed"])
        kept = self.kept()
        self.assertEqual(len(kept), 9)
        for i in range(8):
            self.assertIn((f"f{i}", 1), kept)
            self.assertEqual(self.status(f"f{i}"), ("active", None), f"f{i}")
            self.assertEqual(self.live.instances[f"f{i}@1:i"].mode, "live", f"f{i}")
        self.assertEqual(self.status("z"), ("active", None))
        self.assertFalse([p for p, _ in self.ledger.of("live.incubator") if "exits_only" in p])

    def test_a_carried_cohort_never_pushes_out_one_checked_that_day(self):
        with mock.patch.object(INC, "MAX_PINS", 2):
            self.make()
            self.cohort("hi", 1, trades=winning(10, pnl=3.0))
            self.cohort("lo", 1, trades=winning(10, pnl=1.0))
            self.run_to(9, 31)
            self.assertEqual(self.kept(), [("hi", 1), ("lo", 1)])
            self.clock.set(at(TUESDAY, 9, 31))
            self.new_cohort("mid", pnl=2.0)
            with self.unread_for("hi"):
                self.run_to(9, 31)
            self.assertEqual(self.kept(), [("mid", 1), ("lo", 1), ("hi", 1)], "the checked ones, then the carried")
            self.assertEqual(self.live.state.get(INC.KEEP)["carried"], [["hi", 1]])
            self.assertEqual(sorted(self.pins()["order"]), ["lo@1:i", "mid@1:i"])
            db = self.live.observe_store._connect()
            db.execute("INSERT INTO trades(instance, account, family, version, trade_id, day, pnl, max_loss, recorded_at, "
                       "body, exit_day, reason, forced, evaluator) VALUES('hi@1:o', 'a', 'hi', 1, 'loss', '2026-09-28', -80, "
                       "30, 1, '{}', '2026-09-28', 'program', 0, ?)", (self.live.observe_store.evaluator,))
            self.run_to(9, 41)
            self.assertIn("ended", self.verdicts()["hi@1"])
            self.assertEqual(self.kept(), [("mid", 1), ("lo", 1)])
            for fid in ("lo", "mid"):
                self.assertEqual(self.status(fid), ("active", None), fid)
                self.assertEqual(self.live.instances[f"{fid}@1:i"].mode, "live", fid)

    def test_a_keep_that_raises_completes_no_cohort_at_its_target(self):
        self.monday()
        with mock.patch.object(INC.Incubator, "keep", side_effect=RuntimeError("boom")):
            self.run_to(9, 33)
        self.assertEqual(self.status(), ("active", None), "held: never completed on a keep that raised")
        self.assertNotEqual(self.pins().get("day"), "2026-09-29", "its pins need the keep too: taken again later")
        self.assertNotIn("fam@1:i", [k for k, i in self.live.instances.items() if i.mode == "live"])
        self.assertEqual(len([t for _, t in self.alerts if "the incubator's keep failed (RuntimeError" in t]), 1)
        self.run_to(9, 38)
        self.assertEqual(self.status(), ("active", None))
        self.assertEqual(self.kept(), [("fam", 1)])
        self.assertEqual(self.pins()["order"], ["fam@1:i"])

    def test_a_ledger_that_fails_on_the_carried_event_never_changes_the_keep(self):
        self.monday()
        real = self.live.record

        def flaky(kind, payload, agent=None):
            if isinstance(payload, dict) and "keep_carried" in payload:
                raise sqlite3.OperationalError("disk I/O error")
            return real(kind, payload, agent)
        with mock.patch.object(self.live, "record", side_effect=flaky), \
                mock.patch.object(INC, "cohort_rows", return_value=None):
            self.run_to(9, 31)
        self.assertEqual(self.status(), ("active", None))
        keep = self.live.state.get(INC.KEEP)
        self.assertEqual((keep["cohorts"], keep["carried"], keep["unread"]), ([["fam", 1]], [["fam", 1]], True))

    def test_a_retried_recheck_reads_the_mark_before_today_never_todays(self):
        self.monday()
        with mock.patch.object(INC, "practice_record", return_value=None):
            self.run_to(9, 31)
        with L2PrimeRecordBeforeToday.today_mark(self.live, -1000.0):
            self.run_to(9, 36)
        self.assertEqual(L2PrimeRecordBeforeToday.row(self.live)["open_mark_pnl"], -1000.0, "today's mark")
        verdict = self.verdicts()["fam@1"]
        self.assertNotIn("ended", verdict)
        self.assertEqual((verdict["latest"]["ok"], verdict["latest"]["record"]["open_mark"]), (True, 0.0),
                         "the retry decides on the mark before today, as the first pass would have")
        self.assertEqual(self.live.state.get(INC.KEEP), {"day": "2026-09-29", "cohorts": [["fam", 1]]})
        self.assertTrue(self.live.incubator.checked("2026-09-29"))
        self.assertEqual(self.status(), ("active", None))
        self.assertEqual(self.pins()["order"], [], "no mid-session join")
        self.run_to(9, 37)                                # the session ends with the engine's own mark
        self.clock.set(at(TUESDAY, 9, 31) + 86400)
        self.run_to(9, 31)
        self.assertEqual(self.pins()["order"], ["fam@1:i"])
        self.assertTrue(self.verdicts()["fam@1"]["latest"]["ok"])

    def test_the_first_pass_recheck_failing_on_the_mark_still_ends_it(self):
        self.monday()
        with self.marked():
            self.run_to(9, 31)
        self.assertTrue(self.verdicts()["fam@1"]["ended"]["why"].startswith("P6"))

    def test_a_retried_first_look_reads_the_mark_before_today_never_todays(self):
        self.first()
        with mock.patch.object(INC, "practice_record", return_value=None):
            self.run_to(9, 31)
        with L2PrimeRecordBeforeToday.today_mark(self.live, -1000.0):
            self.run_to(9, 36)
        verdict = self.verdicts()["fam@1"]
        self.assertEqual((verdict["passed"], verdict["day"], verdict["record"]["open_mark"]), (True, "2026-09-28", 0.0),
                         "taken once, on the record before today (the mark its last session left), never today's")
        self.assertEqual(self.live.state.get(INC.KEEP), {"day": "2026-09-28", "cohorts": [["fam", 1]]})
        self.assertTrue(self.live.incubator.checked("2026-09-28"))
        self.assertEqual(self.status(), ("active", None))
        self.assertEqual(self.pins()["order"], [], "no mid-session join")
        self.run_to(9, 37)                                # the session ends with the engine's own mark
        self.clock.set(at(TUESDAY, 9, 31))
        self.run_to(9, 31)
        self.assertEqual(self.pins()["order"], ["fam@1:i"])

    def test_a_read_that_never_recovers_is_retried_at_most_retries_times(self):
        self.monday()
        judged = mock.patch.object(INC.Incubator, "judge", wraps=self.live.incubator.judge)
        with mock.patch.object(INC, "RETRIES", 2), mock.patch.object(INC, "practice_record", return_value=None), \
                judged as judge:
            self.run_to(9, 51)
            self.assertTrue(self.live.incubator.checked("2026-09-29"))
        self.assertEqual(judge.call_count, 3, "the first pass and two retries")
        self.assertEqual(self.status(), ("active", None), "the day's keep stands")
        self.assertEqual(self.kept(), [("fam", 1)])
        self.assertEqual(len([t for _, t in self.alerts if "after 2 retries" in t]), 1)
        self.assertNotIn("ended", self.verdicts()["fam@1"])


@unittest.skipUnless(HAVE, "numpy not installed")
class L2PrimeRecordBeforeToday(Base):
    """The verification of the second review (Sept 30 - Oct 1): every first look and re-check reads the record BEFORE
    TODAY (`observe.practice_record`: the practice row's coverage and open mark as its last session before today left
    them, `prior_*`), at the session's first pass or a retry alike, so a first pass that read nothing (the bands
    unreadable, `keep` raised) never lets a later pass decide on today's values, either way. A record that cannot say
    what it held before today decides nothing on P3 or P6, and never masks P4 or P5; a first look waiting for the next
    session's record is never taken again that day; the day's passes are counted durably from the START of each pass;
    and the HOLD is bounded by the day's retries."""

    def setUp(self):
        super().setUp()
        self.switch(True, observe=True)

    status = L2Prime.status
    kept = L2PrimeSecondReview.kept
    new_cohort = L2PrimeSecondReview.new_cohort
    unread_for = staticmethod(L2PrimeSecondReview.unread_for)

    @staticmethod
    def today_mark(live, mark, fid="fam"):
        """The practice row's open mark TODAY, through the engine's own minute upserts: `mark`."""
        store = live.observe_store
        real = store.practice

        def practice(rows):
            return real([dict(r, open_mark_pnl=mark) if r.get("family") == fid else r for r in rows])
        return mock.patch.object(store, "practice", side_effect=practice)

    @staticmethod
    def row(live, fid="fam"):
        names = ("last_day", "decisions_due", "decisions_made", "open_mark_pnl", "prior_day", "prior_due", "prior_made",
                 "prior_open_mark")
        values = live.observe_store._connect().execute(f"SELECT {', '.join(names)} FROM practice WHERE family=?",
                                                       (fid,)).fetchone()
        return dict(zip(names, values))

    def bands_fail(self):
        return mock.patch.object(self.families, "read", side_effect=sqlite3.OperationalError("database is locked"))

    def unknown_before(self, fid="fam"):
        """A row stepped today before release B's `prior_*` columns: what it held before today is not known."""
        self.live.observe_store._connect().execute(
            "UPDATE practice SET prior_day=NULL, prior_due=NULL, prior_made=NULL, prior_open_mark=NULL WHERE family=?",
            (fid,))

    def todays_coverage_collapses(self, fid="fam"):
        self.live.observe_store._connect().execute(
            "UPDATE practice SET decisions_due=decisions_due+1000 WHERE family=?", (fid,))

    def losing_close(self, fid="fam", day="2026-09-28"):
        """A program close before today that leaves its program P&L below $0 (P4, P5)."""
        self.live.observe_store._connect().execute(
            "INSERT INTO trades(instance, account, family, version, trade_id, day, pnl, max_loss, recorded_at, body, "
            "exit_day, reason, forced, evaluator) VALUES(?, 'a', ?, 1, 'loss', ?, -80, 30, 1, '{}', ?, 'program', 0, ?)",
            (f"{fid}@1:o", fid, day, day, self.live.observe_store.evaluator))

    def monday(self, mark=None):
        """Monday: fam@1's first look passes and it is pinned; its session ends with the open mark `mark`."""
        self.first()
        self.run_to(9, 31)
        self.assertEqual(self.pins()["order"], ["fam@1:i"])
        if mark is not None:
            self.live.observe_store._connect().execute("UPDATE practice SET open_mark_pnl=? WHERE family='fam'", (mark,))
        self.clock.set(at(TUESDAY, 9, 31))

    def wednesday(self):
        self.clock.set(at(TUESDAY, 9, 31) + 86400)
        self.run_to(9, 31)

    # ------------------------------------------------------------------ the record before today, at any pass
    def test_bands_unread_at_the_first_pass_then_todays_mark_never_ends_it(self):
        self.monday()
        with self.today_mark(self.live, -1000.0):
            with self.bands_fail():
                self.run_to(9, 31)
            session = self.live.state.get(INC.SESSION)
            self.assertEqual((session["day"], session["passes"]), ("2026-09-29", 1), "counted before the bands were read")
            self.run_to(9, 36)
        row = self.row(self.live)
        self.assertEqual((row["last_day"], row["open_mark_pnl"]), ("2026-09-29", -1000.0), "today's mark fails P6")
        self.assertEqual(row["prior_day"], "2026-09-29", "rolled at today's first minute: stamped today")
        verdict = self.verdicts()["fam@1"]
        self.assertNotIn("ended", verdict)
        self.assertEqual((verdict["latest"]["day"], verdict["latest"]["ok"]), ("2026-09-29", True), verdict["latest"])
        self.assertEqual(verdict["latest"]["record"]["open_mark"], row["prior_open_mark"])
        self.assertEqual(self.pins()["order"], ["fam@1:i"], "pinned on the record before today, as at the first pass")
        self.assertEqual(self.status(), ("active", None))

    def test_bands_unread_at_the_first_pass_then_todays_mark_never_pins_it(self):
        self.monday(mark=-1000.0)
        with self.today_mark(self.live, 0.0):
            with self.bands_fail():
                self.run_to(9, 31)
            self.run_to(9, 36)
        self.assertEqual(self.row(self.live)["prior_open_mark"], -1000.0)
        verdict = self.verdicts()["fam@1"]
        self.assertTrue(verdict["ended"]["why"].startswith("P6"), verdict)
        self.assertIn("-950.0", verdict["ended"]["why"], "the mark its last session left, never today's 0")
        self.assertEqual(self.pins()["order"], [])
        inst = self.live.instances.get("fam@1:i")
        self.assertTrue(inst is None or inst.mode != "live", "no real money on today's mark")

    def test_the_first_pass_decides_the_same_on_the_mark_before_today(self):
        self.monday(mark=-1000.0)
        with self.today_mark(self.live, 0.0):
            self.run_to(9, 31)
        self.assertTrue(self.verdicts()["fam@1"]["ended"]["why"].startswith("P6"))
        self.assertEqual(self.pins()["order"], [])

    def test_a_keep_that_raised_at_the_first_pass_then_todays_mark_never_ends_it(self):
        self.monday()
        with self.today_mark(self.live, -1000.0):
            with mock.patch.object(INC.Incubator, "keep", side_effect=RuntimeError("boom")), \
                    mock.patch.object(INC, "practice_record", return_value=None):
                self.run_to(9, 31)
            self.assertEqual(self.status(), ("active", None))
            self.run_to(9, 36)
        verdict = self.verdicts()["fam@1"]
        self.assertNotIn("ended", verdict)
        self.assertEqual((verdict["latest"]["ok"], verdict["latest"]["record"]["open_mark"]),
                         (True, self.row(self.live)["prior_open_mark"]))
        self.assertEqual(self.pins()["order"], ["fam@1:i"])

    def test_todays_coverage_is_never_read_at_a_retry(self):
        self.monday()
        with mock.patch.object(INC, "practice_record", return_value=None):
            self.run_to(9, 31)
        self.todays_coverage_collapses()
        self.run_to(9, 36)
        verdict = self.verdicts()["fam@1"]
        self.assertNotIn("ended", verdict)
        self.assertTrue(verdict["latest"]["ok"], verdict["latest"])
        row = self.row(self.live)
        self.assertEqual((verdict["latest"]["record"]["decisions_due"], verdict["latest"]["record"]["decisions_made"]),
                         (row["prior_due"], row["prior_made"]))
        self.assertGreater(row["decisions_due"], 1000)

    # ------------------------------------------------------------------ a record that cannot say what it held before today
    def test_without_its_values_before_today_a_recheck_failing_p6_is_deferred_never_ended(self):
        self.monday()
        with self.today_mark(self.live, -1000.0):
            with self.bands_fail():
                self.run_to(9, 31)
            self.run_to(9, 35)
            self.unknown_before()
            self.run_to(9, 36)
        verdict = self.verdicts()["fam@1"]
        self.assertNotIn("ended", verdict)
        latest = verdict["latest"]
        self.assertEqual((latest["ok"], latest["deferred"], latest["intraday"]), (False, True, True))
        self.assertIn("P6", latest["why"])
        self.assertEqual(self.pins()["order"], [], "never pinned on today's values")
        self.assertIn("today's", self.pins()["refused"]["fam@1"])
        keep = self.live.state.get(INC.KEEP)
        self.assertEqual(keep, {"day": "2026-09-29", "cohorts": [["fam", 1]], "carried": [["fam", 1]]})
        self.assertTrue(self.live.incubator.checked("2026-09-29"))
        self.run_to(9, 41)
        self.assertEqual(self.status(), ("active", None))
        self.assertTrue(self.verdicts()["fam@1"]["latest"]["deferred"], "re-checked at the next session only")
        self.wednesday()
        self.assertEqual(self.pins()["order"], ["fam@1:i"])
        self.assertTrue(self.verdicts()["fam@1"]["latest"]["ok"])

    def test_without_its_values_before_today_a_recheck_that_passes_is_not_pinned(self):
        self.monday()
        with self.bands_fail():
            self.run_to(9, 31)
        self.run_to(9, 35)
        self.unknown_before()
        self.run_to(9, 36)
        latest = self.verdicts()["fam@1"]["latest"]
        self.assertEqual((latest["ok"], latest["deferred"]), (False, True))
        self.assertEqual(self.pins()["order"], [])
        self.assertNotIn("fam@1:i", [k for k, i in self.live.instances.items() if i.mode == "live"])
        self.assertEqual(self.status(), ("active", None))

    def test_without_its_values_before_today_p4_still_ends_it_whatever_p3_says(self):
        self.monday()
        with self.bands_fail():
            self.run_to(9, 31)
        self.run_to(9, 35)
        self.unknown_before()
        self.todays_coverage_collapses()
        self.losing_close()
        self.run_to(9, 36)
        verdict = self.verdicts()["fam@1"]
        self.assertTrue(verdict["ended"]["why"].startswith("P4"), verdict.get("ended"))
        self.assertFalse(verdict["latest"].get("deferred"))
        self.assertEqual(self.live.state.get(INC.KEEP), {"day": "2026-09-29", "cohorts": []})

    def test_without_its_values_before_today_a_first_look_waits_for_the_next_session(self):
        self.first()
        with mock.patch.object(INC, "practice_record", return_value=None):
            self.run_to(9, 31)
        with self.today_mark(self.live, -1000.0):
            self.run_to(9, 35)
            self.unknown_before()
            self.run_to(9, 36)
        self.assertEqual(self.verdicts(), {}, "no look on today's mark")
        self.assertEqual(self.live.state.get(INC.SESSION)["deferred"], [["fam", 1]])
        self.assertEqual(self.kept(), [("fam", 1)])
        self.assertTrue([p for p, _ in self.ledger.of("live.incubator") if p.get("deferred") == "fam@1"])
        # Never taken again that day, even on a record that would pass.
        real = INC.practice_record
        good = mock.patch.object(INC, "practice_record",
                                 side_effect=lambda *a, **kw: dict(real(*a, **kw), intraday=False, open_mark=5.0))
        with mock.patch.object(self.live.incubator, "checked", return_value=False), good as read:
            self.run_to(9, 41)
        self.assertEqual(self.verdicts(), {})
        self.assertFalse([c for c in read.call_args_list if c.args[1] == "fam"], "not even read again today")
        self.assertEqual(self.status(), ("active", None))
        self.clock.set(at(TUESDAY, 9, 31))
        self.run_to(9, 31)
        verdict = self.verdicts()["fam@1"]
        self.assertEqual((verdict["passed"], verdict["day"]), (True, "2026-09-29"), "the next session's record")
        self.assertEqual(self.pins()["order"], ["fam@1:i"])

    def test_without_its_values_before_today_a_first_look_fails_on_p4_whatever_p3_says(self):
        self.first(trades=winning(10, pnl=-1.0))
        with mock.patch.object(INC, "practice_record", return_value=None):
            self.run_to(9, 31)
        self.run_to(9, 35)
        self.unknown_before()
        self.todays_coverage_collapses()
        self.run_to(9, 36)
        verdict = self.verdicts()["fam@1"]
        self.assertFalse(verdict["passed"])
        self.assertTrue(verdict["why"].startswith("P4"), verdict["why"])

    def test_a_deferred_first_look_is_never_taken_on_a_later_pass_that_day(self):
        self.monday()
        self.new_cohort("z")
        self.new_cohort("y")
        with self.unread_for("z", "y"):
            self.run_to(9, 31)
        with self.today_mark(self.live, -1000.0, "z"), self.unread_for("y"):
            self.run_to(9, 35)
            self.unknown_before("z")
            self.run_to(9, 36)
        self.assertNotIn("z@1", self.verdicts())
        self.assertFalse(self.live.incubator.checked("2026-09-29"), "y still unread: judged again")
        with self.unread_for("y"):
            self.run_to(9, 41)
        self.assertNotIn("z@1", self.verdicts(), "never taken on a later pass that day")
        self.assertIn(("z", 1), self.kept())
        self.assertEqual(self.status("z"), ("active", None))
        self.run_to(9, 46)
        self.assertTrue(self.verdicts()["y@1"]["passed"])
        self.assertNotIn("z@1", self.verdicts())
        self.wednesday()
        self.assertTrue(self.verdicts()["z@1"]["passed"])
        self.assertEqual(self.verdicts()["z@1"]["day"], "2026-09-30")

    # ------------------------------------------------------------------ the day's passes, durable, and the bounded HOLD
    def test_the_days_passes_are_counted_at_the_start_of_each_pass_and_a_restart_keeps_them(self):
        self.monday()
        with self.bands_fail():
            self.run_to(9, 31)
        self.assertEqual(self.live.incubator.passes("2026-09-29"), 1)
        live = self.restart()
        with mock.patch.object(self.families, "read", side_effect=sqlite3.OperationalError("database is locked")):
            self.run_to(9, 35)
            self.assertEqual(live.incubator.passes("2026-09-29"), 1,
                             "the restart's first pass, sooner than FAMILIES_EVERY after the last counted one, spends "
                             "no retry")
            self.run_to(9, 36)
        self.assertEqual(live.incubator.passes("2026-09-29"), 2, "FAMILIES_EVERY after it: counted on the saved count")
        session = self.live.state.get(INC.SESSION)
        self.assertEqual((session["passes"], session["last_at"]), (2, at(TUESDAY, 9, 36)))

    def test_unreadable_cohorts_hold_the_league_for_the_days_retries_only(self):
        with mock.patch.object(INC, "RETRIES", 2):
            self.monday()
            self.new_cohort("z")
            with mock.patch.object(INC, "cohort_rows", return_value=None):
                self.run_to(9, 41)
                self.assertTrue(self.live.incubator.holding("2026-09-29"), "the first pass and two retries")
                self.assertEqual(self.status("z"), ("active", None))
                self.run_to(9, 46)
                self.assertFalse(self.live.incubator.holding("2026-09-29"))
            self.assertEqual(self.status("z"), ("complete", "observation target reached"),
                             "the league's own rule again once the retries are spent")
            self.assertEqual(self.status(), ("active", None), "the carried keep stays kept")
            self.assertEqual(self.kept(), [("fam", 1)])
            errors = [t for lvl, t in self.alerts if lvl == "error" and "after 2 retries" in t]
            self.assertEqual(len(errors), 1)

    def test_a_keep_that_keeps_raising_holds_the_league_for_the_days_retries_only(self):
        with mock.patch.object(INC, "RETRIES", 2):
            self.monday()
            self.new_cohort("z", pnl=-1.0)
            with mock.patch.object(INC.Incubator, "keep", side_effect=RuntimeError("boom")):
                self.run_to(9, 41)
                self.assertEqual(self.status("z"), ("active", None), "HOLD while the retries remain")
                self.run_to(9, 46)
            self.assertEqual(self.status("z"), ("complete", "observation target reached"))
            self.assertEqual(self.status(), ("active", None), "the last saved keep stays kept")
            self.assertEqual(len([t for lvl, t in self.alerts if lvl == "error" and "keep still fails" in t]), 1)


@unittest.skipUnless(HAVE, "numpy not installed")
class L2PrimeThirdVerification(Base):
    """The third verification (Oct 1): the record before today is taken from `prior_*` only when they were rolled TODAY
    (a release that never rolls them, release A after a rollback, leaves an older roll: fail closed); a cohort kept
    without a verdict stays kept for the rest of the day, a restart past the retries included; the fallback never keeps
    nothing; a first look's event follows its saved verdict and a recorded first look is final; and only passes
    `FAMILIES_EVERY` apart spend the day's retries."""

    def setUp(self):
        super().setUp()
        self.switch(True, observe=True)

    status = L2Prime.status
    kept = L2PrimeSecondReview.kept
    new_cohort = L2PrimeSecondReview.new_cohort
    unread_for = staticmethod(L2PrimeSecondReview.unread_for)
    row = staticmethod(L2PrimeRecordBeforeToday.row)
    monday = L2PrimeRecordBeforeToday.monday
    wednesday = L2PrimeRecordBeforeToday.wednesday
    unknown_before = L2PrimeRecordBeforeToday.unknown_before

    def release_a_steps(self, day, mark=-1000.0, fid="fam"):
        """Release A (a rollback: no `prior_*`) steps the practice row on `day`: its session, coverage and mark move on,
        its `prior_*` never."""
        self.live.observe_store._connect().execute(
            "UPDATE practice SET last_day=?, sessions=sessions+1, decisions_due=decisions_due+10, "
            "decisions_made=decisions_made+10, open_mark_pnl=? WHERE family=?", (day, mark, fid))

    def first_looks(self, vk="fam@1"):
        """The `first_look` events of `vk`: the ledger's, and the live state's own (which `_recorded` reads)."""
        ledger = [p for p, _ in self.ledger.of("live.incubator") if p.get("first_look") == vk]
        state = [e["payload"] for e in self.live.state.events(kinds=["live.incubator"], limit=10000)
                 if e["payload"].get("first_look") == vk]
        self.assertEqual(len(ledger), len(state))
        return ledger

    # ------------------------------------------------------------------ 1. a stale `prior_*` after a release-A day
    def test_a_release_a_day_then_b_back_the_same_day_never_pins_on_an_older_session(self):
        # PROBE A: Monday under B ends at a mark of -1000 (P6 ends it at Tuesday's first pass, the control in
        # `test_the_first_pass_decides_the_same_on_the_mark_before_today`). Release A steps Tuesday, B is back that day.
        self.monday(mark=-1000.0)
        self.release_a_steps("2026-09-29", mark=-5.0)
        self.restart()
        self.run_to(9, 31)
        record = practice_record(self.live.root, "fam", 1, before="2026-09-29", evaluator=self.live.observe_store.evaluator)
        self.assertEqual((self.row(self.live)["prior_day"], record["intraday"]), ("2026-09-28", True),
                         "rolled Monday: not the record before Tuesday, and said so")
        verdict = self.verdicts()["fam@1"]
        self.assertNotIn("ended", verdict, "nothing decided on P3 or P6, and P4 and P5 hold")
        self.assertEqual((verdict["latest"]["ok"], verdict["latest"]["deferred"]), (False, True))
        self.assertEqual(self.pins()["order"], [], "never pinned on an older session's mark")
        self.assertNotIn("fam@1:i", [k for k, i in self.live.instances.items() if i.mode == "live"])
        self.assertEqual(self.status(), ("active", None), "kept practising, re-checked at the next session")

    def test_a_rollback_across_a_session_day_then_b_mid_session_decides_nothing_on_an_older_mark(self):
        # The second verifier's PROBE I: B's last roll is Monday's; release A steps Tuesday (ending at -1000) and
        # Wednesday morning; B is redeployed at 10:00 on Wednesday.
        self.monday()
        self.release_a_steps("2026-09-29")
        self.release_a_steps("2026-09-30")
        self.clock.set(at(TUESDAY, 10, 0) + 86400)
        self.restart()
        self.run_to(10, 0)
        verdict = self.verdicts()["fam@1"]
        latest = verdict["latest"]
        self.assertEqual((latest["day"], latest["ok"], latest.get("deferred"), latest.get("intraday")),
                         ("2026-09-30", False, True, True), "Monday's roll is not the record before Wednesday")
        self.assertNotIn("ended", verdict)
        self.assertEqual(self.pins()["order"], [])
        self.assertIn("today's", self.pins()["refused"]["fam@1"])

    # ------------------------------------------------------------------ 2. a restart past the retries keeps a cohort with no verdict
    def test_a_first_look_unread_through_the_retries_then_a_restart_stays_kept_and_is_looked_at_next_session(self):
        with mock.patch.object(INC, "RETRIES", 2):
            self.monday()
            self.new_cohort("z")
            with self.unread_for("z"):
                self.run_to(9, 47)
                self.assertTrue(self.live.incubator._retried_out("2026-09-29"))
                self.assertIn(("z", 1), self.kept())
                self.restart()
                self.run_to(9, 56)
            self.assertIn(("z", 1), self.kept(), "kept for the rest of the day across the restart")
            self.assertEqual(self.status("z"), ("active", None), "never completed at its target before its look")
            self.assertNotIn("z@1", self.verdicts())
            self.assertNotIn("z@1:i", self.pins()["order"], "never a pin candidate")
            self.run_to(10, 30)
            self.assertEqual(self.status("z"), ("active", None))
            self.wednesday()
        verdict = self.verdicts()["z@1"]
        self.assertEqual((verdict["passed"], verdict["day"]), (True, "2026-09-30"), "its look at the next session")
        self.assertIn("z@1:i", self.pins()["order"])

    def test_a_deferred_first_look_through_the_retries_then_a_restart_stays_kept_and_is_looked_at_next_session(self):
        with mock.patch.object(INC, "RETRIES", 2):
            self.monday()
            self.new_cohort("z")
            with self.unread_for("z", "fam"):
                self.run_to(9, 35)
            self.unknown_before("z")
            with self.unread_for("fam"):
                self.run_to(9, 47)
                self.assertEqual(self.live.state.get(INC.SESSION)["deferred"], [["z", 1]])
                self.assertTrue(self.live.incubator._retried_out("2026-09-29"))
                self.restart()
                self.run_to(9, 56)
            self.assertIn(("z", 1), self.kept())
            self.assertEqual(self.status("z"), ("active", None))
            self.assertNotIn("z@1", self.verdicts())
            self.wednesday()
        verdict = self.verdicts()["z@1"]
        self.assertEqual((verdict["passed"], verdict["day"]), (True, "2026-09-30"))
        self.assertEqual(self.status("z"), ("active", None))

    # ------------------------------------------------------------------ 3. the fallback never keeps nothing
    def keep_and_saved_keep_fail(self):
        real_get = INC.Incubator._get

        def get(inc, key):
            if key == INC.KEEP:
                raise sqlite3.OperationalError("disk I/O error")
            return real_get(inc, key)
        return (mock.patch.object(INC.Incubator, "keep", side_effect=RuntimeError("boom")),
                mock.patch.object(INC.Incubator, "_get", get))

    def test_fallback_unreadable_keeps_the_last_keep_this_process_took(self):
        # The second verifier's PROBE J: `keep` raises and the saved keep cannot be read, past the day's retries.
        with mock.patch.object(INC, "RETRIES", 2):
            self.monday()
            self.new_cohort("z", pnl=-1.0)
            raising, unreadable = self.keep_and_saved_keep_fail()
            with raising, unreadable:
                self.run_to(9, 47)
            self.assertEqual(self.status(), ("active", None), "kept and pinned on Monday: never completed on it")
            self.assertEqual(self.status("z"), ("complete", "observation target reached"),
                             "the rest of the league by its own rule")
            errors = [t for lvl, t in self.alerts if lvl == "error" and "keep still fails" in t]
            self.assertEqual(len(errors), 1)
            self.assertIn("the last keep this process took", errors[0])

    def test_fallback_unreadable_with_no_keep_taken_holds_every_cohort(self):
        with mock.patch.object(INC, "RETRIES", 2):
            self.monday()
            self.restart()                              # this process has taken no keep
            self.new_cohort("z", pnl=-1.0)
            raising, unreadable = self.keep_and_saved_keep_fail()
            with raising, unreadable:
                self.run_to(9, 47)
                self.assertIs(self.live.incubator.fallback("2026-09-29"), INC.HOLD)
            self.assertEqual(self.status(), ("active", None))
            self.assertEqual(self.status("z"), ("active", None), "HOLD: never nothing")

    # ------------------------------------------------------------------ 4. a first look's event follows its saved verdict
    def test_a_first_look_whose_verdict_cannot_be_saved_records_no_event_and_is_taken_once(self):
        self.first()
        real = self.live.state.put

        def put(key, value):
            if key == INC.VERDICTS:
                raise sqlite3.OperationalError("disk I/O error")
            return real(key, value)
        with mock.patch.object(self.live.state, "put", side_effect=put):
            self.run_to(9, 31)
        self.assertEqual(self.verdicts(), {})
        self.assertEqual(self.first_looks(), [], "no first_look event behind a verdict that was not saved")
        self.assertEqual(self.status(), ("active", None))
        self.run_to(9, 36)
        self.assertTrue(self.verdicts()["fam@1"]["passed"])
        looks = self.first_looks()
        self.assertEqual(len(looks), 1)
        self.assertEqual((looks[0]["evaluator"], looks[0]["program"], looks[0]["run_sha"]),
                         (self.live.observe_store.evaluator, self.verdicts()["fam@1"]["program"], "sha-fam-1"))

    def test_a_recorded_first_look_that_failed_is_final_and_never_retaken_and_passed(self):
        self.first(trades=winning(10, pnl=-1.0))
        self.run_to(9, 31)
        self.assertFalse(self.verdicts()["fam@1"]["passed"])
        self.assertEqual(len(self.first_looks()), 1)
        self.live.state.put(INC.VERDICTS, {})           # its verdict lost, its event kept (the old order's gap)
        db = self.live.observe_store._connect()
        for i in range(10):
            db.execute("INSERT INTO trades(instance, account, family, version, trade_id, day, pnl, max_loss, recorded_at, "
                       "body, exit_day, reason, forced, evaluator) VALUES('fam@1:o', 'a', 'fam', 1, ?, '2026-09-28', 100, "
                       "30, 1, ?, '2026-09-28', 'program', 0, ?)",
                       (f"win{i}", json.dumps({"qty": 1, "fees": 1.3}), self.live.observe_store.evaluator))
        record = practice_record(self.live.root, "fam", 1, before="2026-09-29", evaluator=self.live.observe_store.evaluator)
        self.assertTrue(M.practice_ok(self.live.table, record)[0], "a look taken again now would pass")
        self.clock.set(at(TUESDAY, 9, 31))
        self.run_to(9, 31)
        verdict = self.verdicts()["fam@1"]
        self.assertEqual((verdict["passed"], verdict["day"], verdict.get("restored")), (False, "2026-09-28", True))
        self.assertTrue(verdict["why"].startswith("P4"), verdict["why"])
        self.assertEqual(len(self.first_looks()), 1, "never taken again")
        self.assertEqual(self.pins()["order"], [])
        self.assertNotIn(("fam", 1), self.kept())

    def test_a_recorded_first_look_that_passed_is_restored_and_rechecked_that_pass(self):
        self.first()
        self.run_to(9, 31)
        self.assertEqual(self.pins()["order"], ["fam@1:i"])
        self.live.state.put(INC.VERDICTS, {})
        self.clock.set(at(TUESDAY, 9, 31))
        self.run_to(9, 31)
        verdict = self.verdicts()["fam@1"]
        self.assertEqual((verdict["passed"], verdict["day"], verdict.get("restored")), (True, "2026-09-28", True))
        self.assertEqual((verdict["latest"]["day"], verdict["latest"]["ok"]), ("2026-09-29", True), verdict["latest"])
        self.assertEqual(len(self.first_looks()), 1, "never taken again")
        self.assertEqual(self.pins()["order"], ["fam@1:i"], "its program and run sha, as recorded")
        self.assertTrue([p for p, _ in self.ledger.of("live.incubator") if p.get("restored") == "fam@1"])

    def test_a_restored_first_look_never_revives_an_ended_incubation(self):
        self.first()
        self.run_to(9, 31)
        self.clock.set(at(TUESDAY, 9, 31))
        db = self.live.observe_store._connect()
        db.execute("INSERT INTO trades(instance, account, family, version, trade_id, day, pnl, max_loss, recorded_at, body, "
                   "exit_day, reason, forced, evaluator) VALUES('fam@1:o', 'a', 'fam', 1, 'loss', '2026-09-28', -80, 30, 1, "
                   "'{}', '2026-09-28', 'program', 0, ?)", (self.live.observe_store.evaluator,))
        self.run_to(9, 31)
        self.assertTrue(self.verdicts()["fam@1"]["ended"]["why"].startswith("P4"))
        self.live.state.put(INC.VERDICTS, {})
        db.execute("DELETE FROM trades WHERE trade_id='loss'")       # a record that would pass again
        self.clock.set(at(TUESDAY, 9, 31) + 86400)
        self.run_to(9, 31)
        verdict = self.verdicts()["fam@1"]
        self.assertEqual((verdict["passed"], verdict.get("restored")), (True, True))
        self.assertTrue(verdict["ended"]["why"].startswith("P4"), "its recorded end stands")
        self.assertEqual(self.pins()["order"], [])
        self.assertEqual(len(self.first_looks()), 1)

    # ------------------------------------------------------------------ 5. only passes FAMILIES_EVERY apart spend a retry
    def test_a_pass_counts_only_families_every_after_the_last_counted_one(self):
        from league.live.step import FAMILIES_EVERY

        self.make()
        t0, day = at(TUESDAY, 9, 31), "2026-09-29"
        inc = self.live.incubator
        for dt_, n in ((0, 1), (60, 1), (FAMILIES_EVERY - 1, 1), (FAMILIES_EVERY, 2), (FAMILIES_EVERY + 60, 2)):
            inc.begin(day, t0 + dt_)
            self.assertEqual(inc.passes(day), n, dt_)
        self.assertEqual(self.live.state.get(INC.SESSION)["last_at"], t0 + FAMILIES_EVERY)
        inc = self.restart().incubator
        inc.begin(day, t0 + FAMILIES_EVERY + 120)
        self.assertEqual(inc.passes(day), 2, "a restart's pass sooner than FAMILIES_EVERY spends no retry")
        inc.begin(day, t0 + 2 * FAMILIES_EVERY)
        self.assertEqual(inc.passes(day), 3)
        inc.begin("2026-09-30", t0 + 86400)
        self.assertEqual(inc.passes("2026-09-30"), 1, "a new day counts afresh")

    def test_forced_passes_never_spend_the_days_retries(self):
        # The second verifier's PROBE D, at the production RETRIES: a forward read that fails forces a families pass
        # every minute.
        self.first([family("vert", VERTICAL, band="candidate")])
        self.run_to(9, 31)
        self.clock.set(at(TUESDAY, 9, 31))
        self.new_cohort("z")
        judged = mock.patch.object(INC.Incubator, "judge", wraps=self.live.incubator.judge)
        forward = mock.patch.object(self.families, "forward_rows", side_effect=sqlite3.OperationalError("locked"))
        with forward, mock.patch.object(INC, "cohort_rows", return_value=None), judged as judge:
            self.run_to(9, 44)
            self.assertEqual(self.live.incubator.passes("2026-09-29"), 3, "09:31, 09:36 and 09:41 only")
            self.assertGreater(judge.call_count, 3, "the forced passes ran (and read again)")
            self.assertTrue(self.live.incubator.holding("2026-09-29"))
        self.assertEqual(self.status("z"), ("active", None), "not completed while the retries remain")
        self.assertEqual(self.status(), ("active", None))


@unittest.skipUnless(HAVE, "numpy not installed")
class TheObserveRetry(Base):
    """With the observe band on (production), unreadable bands at the session's first pass are read again
    `FAMILIES_EVERY` later, not every minute."""

    def test_unreadable_bands_are_read_again_every_five_minutes(self):
        self.switch(False, observe=True)
        self.first()
        with mock.patch.object(self.families, "read", side_effect=sqlite3.OperationalError("database is locked")):
            self.run_to(9, 35)
        self.assertEqual(len([t for _, t in self.alerts if "bands could not be read" in t]), 1)
        self.run_to(9, 36)
        self.assertEqual((self.live.state.get("observe_pins") or {}).get("day"), "2026-09-28")


if __name__ == "__main__":
    unittest.main()
