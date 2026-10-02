"""THE FORWARD LADDER (evidence v3, `league/live/ladder.py`): its lines, its receipts, its cohort lifecycle, the swarm's side
of a promotion and a demotion, and its public-safe counts."""

from __future__ import annotations

import copy
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from league.constitution import CONSTITUTION, options_money_problems
from league.live import ladder as L
from league.live.observe import ObserveStore

try:
    import numpy as np

    HAVE = True
except ImportError:  # pragma: no cover - the House and CI carry numpy
    HAVE = False

EVALUATOR = "bundle-1:fills-1:exec-1"
CODE = '''
NEEDS = {"roots": ["SPY"], "dte": [0, 3], "band": 0.03, "cadence": 1, "history": 0, "start": 571, "end": 958}
PARAMS = {"hold": 3}

def decide(ctx):
    return []
'''


def sessions(first: str, n: int) -> list[str]:
    return L.sessions_between(first, (dt.date.fromisoformat(first) + dt.timedelta(days=3 * n)).isoformat())[:n]


def body(pnl: float, *, delta: float = 0.0, spot: float = 500.0, move: float = 0.0, qty: int = 1, fees: float = 1.3,
         exit_spot: bool = True) -> dict:
    """An engine trade row's body: two legs whose context deltas differ by `delta` / 100 a lot."""
    out = {"qty": qty, "fees": fees, "type": "debit_vertical",
           "legs": [{"side": "long", "ratio": 1, "right": "C"}, {"side": "short", "ratio": 1, "right": "C"}],
           "context": {"spot": spot, "delta": [0.3 + delta / 100.0, 0.3]}}
    if exit_spot:
        out["exit_spot"] = spot + move
    return out


def record(days: list[str], returns: list[list[float]], *, loss: float = 100.0, delta: float = 0.0,
           moves: dict[str, float] | None = None) -> list[dict]:
    """Ledger rows: on each day, one close per return (pnl = return x loss, plus delta x that day's move)."""
    rows, seq = [], 0
    for day, rs in zip(days, returns):
        move = (moves or {}).get(day, 0.0)
        for r in rs:
            pnl = r * loss + delta * move
            rows.append({"seq": seq, "trade_id": str(seq), "pnl": pnl, "max_loss": loss, "exit_day": day,
                         "body": body(pnl, delta=delta, move=move)})
            seq += 1
    return rows


def rules(**changes) -> L.Rules:
    base = L.Rules.from_constitution()
    return L.Rules(**{**base.__dict__, **changes})


# ================================================================================================== the constitution
class TheTable(unittest.TestCase):
    def test_the_ladder_block_reads_as_the_plan_states_it(self):
        r = L.Rules.from_constitution()
        self.assertEqual((r.min_sessions, r.min_closes, r.confidence, r.windows, r.windows_positive, r.fdr_q, r.fdr_days,
                          r.max_sessions), (20, 30, 0.95, 4, 3, 0.10, 90, 60))
        self.assertIsInstance(r.binding, bool)
        self.assertEqual(options_money_problems(), [])

    def test_a_row_may_only_tighten(self):
        for key, value in (("min_sessions", 19), ("min_closes", 29), ("confidence", "0.94"), ("draws", 1999),
                           ("windows_positive", 2), ("fdr_q", "0.11"), ("fdr_days", 89), ("max_sessions", 61),
                           ("drift_known_share", "0.89"), ("demote_sessions", 21), ("demote_confidence", "0.79"),
                           ("windows", 5), ("min_closes", 30.0)):
            changed = copy.deepcopy(CONSTITUTION)
            changed["options_money"]["ladder"][key] = value
            self.assertTrue(any(f"ladder.{key}" in p for p in options_money_problems(changed)), (key, value))
            with self.assertRaises(ValueError):
                L.Rules.from_constitution(changed)
        for key, value in (("min_sessions", 40), ("min_closes", 60), ("confidence", "0.99"), ("fdr_q", "0.05"),
                           ("fdr_days", 180), ("max_sessions", 40), ("windows_positive", 4), ("demote_sessions", 10)):
            changed = copy.deepcopy(CONSTITUTION)
            changed["options_money"]["ladder"][key] = value
            self.assertEqual(options_money_problems(changed), [], (key, value))

    def test_binding_is_a_json_boolean_and_the_window_holds_the_record(self):
        for value in (1, "true", None):
            changed = copy.deepcopy(CONSTITUTION)
            changed["options_money"]["ladder"]["binding"] = value
            self.assertTrue(any("ladder.binding" in p for p in options_money_problems(changed)), value)
        changed = copy.deepcopy(CONSTITUTION)
        changed["options_money"]["ladder"].update(min_sessions=40, max_sessions=30)
        self.assertTrue(any("max_sessions" in p for p in options_money_problems(changed)))
        changed = copy.deepcopy(CONSTITUTION)
        del changed["options_money"]["ladder"]
        self.assertTrue(options_money_problems(changed))

    def test_sized_waits_for_twenty_real_trades_and_five_sessions(self):
        sized = CONSTITUTION["options_money"]["sized"]
        self.assertEqual((sized["min_probe_real_trades"], sized["min_probe_sessions"]), (20, 5))


# ================================================================================================== the lines
@unittest.skipUnless(HAVE, "numpy not installed")
class TheLines(unittest.TestCase):
    def closes(self, returns_by_day: list[list[float]], first="2026-10-05", r_adj=None) -> list[L.Close]:
        out = []
        for day, rs in zip(sessions(first, len(returns_by_day)), returns_by_day):
            out += [L.Close(day=day, r=r, r_adj=r if r_adj is None else r_adj, unit=50.0) for r in rs]
        return out

    def test_the_bootstrap_is_deterministic_and_bounds_a_positive_record(self):
        rng = np.random.default_rng(1)
        good = self.closes([[0.3 + 0.2 * float(rng.standard_normal()) for _ in range(2)] for _ in range(25)])
        a = L.bootstrap(good, confidence=0.95, draws=2000, seed="s")
        b = L.bootstrap(good, confidence=0.95, draws=2000, seed="s")
        self.assertEqual(a, b)
        self.assertGreater(a["lcb"], 0)
        self.assertLess(a["p"], 0.05)
        self.assertEqual(a["days"], 25)

    def test_a_mean_at_or_below_zero_or_one_day_is_p_one_and_no_bound(self):
        flat = self.closes([[0.1, -0.1]] * 25)
        self.assertEqual((L.bootstrap(flat, confidence=0.95, draws=2000, seed="s")["p"],
                          L.bootstrap(flat, confidence=0.95, draws=2000, seed="s")["lcb"]), (1.0, None))
        one_day = [L.Close(day="2026-10-05", r=0.5, r_adj=0.5, unit=1.0)] * 40
        out = L.bootstrap(one_day, confidence=0.95, draws=2000, seed="s")
        self.assertEqual((out["p"], out["lcb"]), (1.0, None), "one block has no spread: no bound")

    def test_a_noisy_null_rarely_bounds_above_zero(self):
        rng = np.random.default_rng(7)
        passed = 0
        for k in range(200):
            null = self.closes([[0.5 * float(rng.standard_normal()) for _ in range(2)] for _ in range(25)])
            passed += (L.bootstrap(null, confidence=0.95, draws=2000, seed=str(k))["lcb"] or -1) > 0
        self.assertLess(passed, 25, "about 5% of nulls, not more")

    def test_windows_split_the_sessions_equally(self):
        days = sessions("2026-10-05", 20)
        closes = [L.Close(day=d, r=1.0 if i < 15 else -5.0, r_adj=None, unit=None) for i, d in enumerate(days)]
        sums = L.windows(closes, days, 4)
        self.assertEqual(sums, [5.0, 5.0, 5.0, -25.0])
        self.assertEqual(L.windows([], days, 4), [0.0, 0.0, 0.0, 0.0])
        self.assertEqual(len(L.windows(closes, days[:6], 4)), 4)

    def test_benjamini_hochberg_steps_up(self):
        ps = [0.001, 0.008, 0.039, 0.041, 0.042, 0.06, 0.074, 0.205, 0.212, 0.216]
        self.assertEqual(L.benjamini_hochberg(ps, 0.05), (0.008, 10))
        self.assertEqual(L.benjamini_hochberg(ps, 0.10), (0.06, 10), "the step-up rejects past ranks that failed")
        self.assertEqual(L.benjamini_hochberg([0.2, 0.5], 0.10), (None, 2))
        cut, m = L.benjamini_hochberg([0.004] + [1.0] * 30, 0.10)
        self.assertEqual((cut, m), (None, 31), "entrants without a record (p = 1) raise the bar")

    def test_the_entry_delta_and_the_drift_charge(self):
        b = body(0.0, delta=20.0, spot=500.0, move=4.0)
        self.assertAlmostEqual(L.entry_delta(b), 20.0)
        self.assertAlmostEqual(L.drift_usd(b), 80.0)
        short = dict(b, legs=[{"side": "short", "ratio": 1}, {"side": "long", "ratio": 1}], qty=2)
        self.assertAlmostEqual(L.entry_delta(short), -40.0)
        for broken in (dict(b, exit_spot=None), dict(b, context={"spot": 500.0, "delta": [0.5]}),
                       dict(b, context={"spot": 500.0, "delta": [None, 0.3]}), dict(b, legs=[{"side": "?", "ratio": 1}] * 2),
                       dict(b, qty=0)):
            self.assertIsNone(L.drift_usd(broken))

    def test_the_drift_control_fails_drift_and_keeps_a_non_directional_edge(self):
        days = sessions("2026-10-05", 30)
        moves = {d: 3.0 if i % 2 else 1.0 for i, d in enumerate(days)}             # a market that only rises
        drift = [L.close_of(r) for r in record(days, [[-0.03]] * 30, delta=20.0, moves=moves)]
        self.assertGreater(sum(c.r for c in drift), 0, "raw P&L is positive: the market's drift")
        self.assertFalse(L.drift_line(drift, 0.9)["passed"])
        premium = [L.close_of(r) for r in record(days, [[0.05]] * 30, delta=0.0, moves=moves)]
        self.assertTrue(L.drift_line(premium, 0.9)["passed"])
        unknown = [L.Close(day=c.day, r=c.r, r_adj=None if i % 5 == 0 else c.r_adj, unit=None)
                   for i, c in enumerate(premium)]
        line = L.drift_line(unknown, 0.9)
        self.assertEqual((line["passed"], line["share"]), (False, 0.8), "figures known for under 90% of closes fail it")


# ================================================================================================== judge
@unittest.skipUnless(HAVE, "numpy not installed")
class TheJudgement(unittest.TestCase):
    def cohort(self, first="2026-10-05"):
        return {"family": "fam", "version": 1, "first_day": first,
                "snapshot": {"run_sha": "sha-1", "practice_evaluator": EVALUATOR}}

    def test_a_short_record_has_p_one_and_says_why(self):
        days = sessions("2026-10-05", 19)
        out = L.judge(self.cohort(), {"first_day": days[0], "sessions": 19}, record(days, [[0.4, 0.4]] * 19),
                      through=days[-1], rules=rules())
        self.assertEqual((out["full"], out["p"], out["lines"]["record"]), (False, 1.0, False))
        self.assertEqual(out["closes"], 38)
        self.assertEqual(out["per_session"][days[0]], 2)

    def test_a_strong_record_meets_every_line_but_the_desks(self):
        rng = np.random.default_rng(3)
        days = sessions("2026-10-05", 24)
        rows = record(days, [[0.25 + 0.3 * float(rng.standard_normal()) for _ in range(2)] for _ in days])
        out = L.judge(self.cohort(), {"first_day": days[0], "sessions": 24}, rows, through=days[-1], rules=rules())
        self.assertTrue(all(out["lines"].values()), out["lines"])
        self.assertLess(out["p"], 0.05)
        self.assertEqual(out["typical"], round(100.0 + 2.6, 2), "the median lot's maximum loss with both fees")

    def test_a_practice_row_older_than_its_cohort_is_ineligible(self):
        days = sessions("2026-10-05", 24)
        out = L.judge(self.cohort(days[1]), {"first_day": days[0], "sessions": 24}, record(days, [[0.3]] * 24),
                      through=days[-1], rules=rules())
        self.assertEqual((out["eligible"], out["sessions"], out["p"]), (False, None, 1.0))

    def test_the_inputs_hash_moves_with_any_close(self):
        days = sessions("2026-10-05", 22)
        rows = record(days, [[0.3, 0.1]] * 22)
        a = L.judge(self.cohort(), {"first_day": days[0], "sessions": 22}, rows, through=days[-1], rules=rules())
        rows[3] = dict(rows[3], pnl=rows[3]["pnl"] + 0.01)
        b = L.judge(self.cohort(), {"first_day": days[0], "sessions": 22}, rows, through=days[-1], rules=rules())
        self.assertNotEqual(a["inputs"], b["inputs"])


# ================================================================================================== the store
class StoreCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.now = [1_790_000_000.0]
        self.store = ObserveStore(self.root, clock=lambda: self.now[0])
        self.store.evaluator = EVALUATOR
        self.addCleanup(self.store.close)

    def program(self, fid="fam", n=1, tier="validated") -> dict:
        return {"family": fid, "version": n, "band": "gym", "observe": True, "tier": tier, "lineage": fid,
                "code": CODE, "params": {"hold": 3}, "run_sha": f"sha-{fid}-{n}", "structure": "debit_vertical"}

    def add_record(self, fid: str, n: int, days: list[str], returns: list[list[float]], **kw) -> None:
        db = self.store._connect()
        for r in record(days, returns, **kw):
            db.execute("INSERT INTO trades(instance, account, family, version, trade_id, day, pnl, max_loss, recorded_at, "
                       "body, exit_day, reason, forced, evaluator) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                       (f"{fid}@{n}:o", "a", fid, n, f"{fid}-{r['trade_id']}", r["exit_day"], r["pnl"], r["max_loss"], 1.0,
                        json.dumps(r["body"]), r["exit_day"], "program", 0, EVALUATOR))
        db.execute("INSERT OR REPLACE INTO practice(family, version, tier, capital, first_at, first_day, last_at, last_day, "
                   "sessions) VALUES(?,?,?,?,?,?,?,?,?)", (fid, n, "validated", 10000.0, 1.0, days[0], 2.0, days[-1],
                                                           len(days)))


class TheCohortLifecycle(StoreCase):
    # ------------------------------------------------------------------ practice restarts on a new evaluator (the review)
    def test_a_program_completed_under_another_evaluator_practises_again_as_a_new_cohort(self):
        self.store.freeze(self.program(), day="2026-10-05")
        old = sessions("2026-10-05", 4)
        self.add_record("fam", 1, old, [[0.2]] * 4)
        self.store.evaluator = "bundle-2:fills-1:exec-2"         # a release moved the practice evaluator
        out = self.store.cohort_candidates([self.program()], day="2026-10-12", in_session=True)
        self.assertEqual([(r["family"], r.get("practice_frozen")) for r in out], [("fam", None)],
                         "offered again, not as the old snapshot")
        snap = self.store.freeze(out[0], day="2026-10-12")
        self.assertEqual(snap["practice_evaluator"], "bundle-2:fills-1:exec-2")
        db = self.store._connect()
        self.assertEqual(db.execute("SELECT status, first_day, evaluator FROM cohorts").fetchall(),
                         [("active", "2026-10-12", "bundle-2:fills-1:exec-2")])
        [(status, reason, evaluator, practice)] = db.execute(
            "SELECT status, reason, evaluator, practice FROM cohort_archive").fetchall()
        self.assertEqual((status, evaluator), ("complete", EVALUATOR))
        self.assertIn("evaluator changed", reason)
        self.assertEqual(json.loads(practice)["sessions"], 4, "its old practice row is kept in the archive")
        self.assertIsNone(db.execute("SELECT 1 FROM practice").fetchone(), "its practice row starts again")
        self.assertEqual(sorted((e["evaluator"], e["entered_day"]) for e in self.store.entrants(since="2026-01-01")),
                         [(EVALUATOR, "2026-10-05"), ("bundle-2:fills-1:exec-2", "2026-10-12")], "two trials")
        new = sessions("2026-10-12", 3)
        self.store.practice([{"family": "fam", "version": 1, "tier": "validated", "capital": 10000.0, "account": "b",
                              "at": self.now[0] + 86_400.0 * i, "day": d, "equity": 10000.0} for i, d in enumerate(new)])
        practice, _ = self.store.ladder_rows("fam", 1, evaluator=self.store.evaluator, first_day="2026-10-12",
                                             through=new[-1])
        cohort = self.store.ladder_cohorts()[0]
        figures = L.judge(cohort, practice, [], through=new[-1], rules=L.Rules.from_constitution())
        self.assertEqual((figures["eligible"], figures["sessions"]), (True, 3), "judged on its own sessions")
        self.store.set_entrant_p("fam", 1, 0.5, day=new[-1])
        self.assertEqual({e["evaluator"]: e["p_value"] for e in self.store.entrants(since="2026-01-01")},
                         {"bundle-2:fills-1:exec-2": 0.5, EVALUATOR: None})

    def test_a_cohort_completed_under_this_evaluator_or_ended_by_the_ladder_never_reenters(self):
        for i, status in enumerate(("complete", "failed", "promoted", "demoted")):
            fid = f"f{i}"
            self.store.freeze(self.program(fid), day="2026-10-05")
            self.store._connect().execute("UPDATE cohorts SET status=? WHERE family=?", (status, fid))
        current = [self.program(f"f{i}") for i in range(4)]
        self.assertEqual(self.store.cohort_candidates(current, day="2026-10-12", in_session=True), [])
        self.store.evaluator = "another"
        out = self.store.cohort_candidates(current, day="2026-10-12", in_session=True)
        self.assertEqual([r["family"] for r in out], ["f0"], "only the one that completed under another evaluator")
        for i in (1, 2, 3):
            with self.assertRaises(ValueError):
                self.store.freeze(self.program(f"f{i}"), day="2026-10-12")

    def test_the_trade_cap_spares_an_active_or_promoted_ladder_record(self):
        store = ObserveStore(self.root / "capped", clock=lambda: 1.0, max_rows=10)
        store.evaluator = EVALUATOR
        self.addCleanup(store.close)
        store.freeze(self.program("kept"), day="2026-10-05")
        store.freeze(self.program("up"), day="2026-10-05")
        store.close_cohort("up", 1, status="promoted", day="2026-11-02", reason="r")
        for fid in ("kept", "up", "other"):
            store.add(f"{fid}@1:o", fid, 1, [{"id": i, "pnl": 1.0, "max_loss": 10.0, "exit_day": "2026-10-06",
                                              "evaluator": EVALUATOR} for i in range(8)], account="a")
        counts = dict(store._connect().execute("SELECT family, COUNT(*) FROM trades GROUP BY family").fetchall())
        self.assertEqual((counts.get("kept"), counts.get("up"), counts.get("other")), (8, 8, None),
                         "the oldest unprotected rows go; the ladder's records stay whole")

    def test_an_older_file_gains_the_cohorts_evaluator(self):
        import sqlite3

        path = self.root / "old"
        path.mkdir()
        db = sqlite3.connect(str(path / "observe.sqlite"))
        db.execute("CREATE TABLE cohorts (family TEXT NOT NULL, version INTEGER NOT NULL, admitted_at REAL NOT NULL, "
                   "first_day TEXT NOT NULL, snapshot TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'active', "
                   "completed_day TEXT, reason TEXT, PRIMARY KEY (family, version))")
        db.execute("INSERT INTO cohorts(family, version, admitted_at, first_day, snapshot) VALUES('a', 1, 1, '2026-10-01', ?)",
                   (json.dumps({"practice_evaluator": "e-old"}),))
        db.commit()
        db.close()
        store = ObserveStore(path, clock=lambda: 1.0)
        self.addCleanup(store.close)
        self.assertEqual(store._connect().execute("SELECT evaluator FROM cohorts").fetchone(), ("e-old",))

    def test_a_frozen_cohort_is_a_ladder_entrant_once(self):
        snap = self.store.freeze(self.program(), day="2026-10-05")
        self.assertEqual(snap["ladder"], L.LADDER_VERSION)
        self.assertEqual(snap["practice_max_sessions"], L.Rules.from_constitution().max_sessions)
        self.store.freeze(self.program(), day="2026-10-06")
        [entrant] = self.store.entrants(since="2026-01-01")
        self.assertEqual((entrant["family"], entrant["version"], entrant["run_sha"], entrant["tier"], entrant["evaluator"],
                          entrant["entered_day"], entrant["p_value"]),
                         ("fam", 1, "sha-fam-1", "validated", EVALUATOR, "2026-10-05", None))

    def test_a_ladder_cohort_never_completes_at_the_old_target_but_at_its_window(self):
        self.store.freeze(self.program(), day="2026-10-05")
        days = sessions("2026-10-05", 5)
        self.add_record("fam", 1, days, [[0.2, 0.2, 0.2]] * 5)
        out = self.store.cohort_candidates([], day=sessions("2026-10-05", 6)[-1], in_session=True)
        self.assertEqual([r["family"] for r in out], ["fam"], "3 sessions and 10 closes no longer end it")
        late = sessions("2026-10-05", 61)[-1]
        self.assertEqual(self.store.cohort_candidates([], day=late, in_session=True), [])
        status = self.store._connect().execute("SELECT status, reason FROM cohorts").fetchone()
        self.assertEqual(status, ("complete", "ladder: its practice window ended"))

    def test_a_pre_ladder_cohort_keeps_the_old_rule(self):
        snapshot = dict(self.program(), practice_frozen=True, practice_evaluator=EVALUATOR)
        self.store._connect().execute("INSERT INTO cohorts(family, version, admitted_at, first_day, snapshot) VALUES(?,?,?,?,?)",
                                      ("old", 1, 1.0, "2026-10-05", json.dumps(snapshot)))
        days = sessions("2026-10-05", 4)
        self.add_record("old", 1, days, [[0.2, 0.2, 0.2]] * 4)
        self.store.cohort_candidates([], day=sessions("2026-10-05", 5)[-1], in_session=True)
        status = self.store._connect().execute("SELECT status, reason FROM cohorts WHERE family='old'").fetchone()
        self.assertEqual(status, ("complete", "observation target reached"))

    def test_close_cohort_moves_only_from_the_states_named(self):
        self.store.freeze(self.program(), day="2026-10-05")
        self.assertTrue(self.store.close_cohort("fam", 1, status="promoted", day="2026-11-02", reason="r"))
        self.assertFalse(self.store.close_cohort("fam", 1, status="failed", day="2026-11-02", reason="r"))
        self.assertTrue(self.store.close_cohort("fam", 1, status="demoted", day="2026-12-02", reason="r",
                                                was=("promoted",)))
        with self.assertRaises(ValueError):
            self.store.close_cohort("fam", 1, status="active", day="x", reason="r")
        self.assertEqual(self.store.ladder_cohorts(), [])
        self.assertEqual([c["status"] for c in self.store.ladder_cohorts(statuses=("demoted",))], ["demoted"])

    def test_the_record_is_the_cohorts_own_program_closes_under_its_evaluator(self):
        self.store.freeze(self.program(), day="2026-10-05")
        days = sessions("2026-10-05", 3)
        self.add_record("fam", 1, days, [[0.1]] * 3)
        db = self.store._connect()
        db.execute("UPDATE trades SET forced=1 WHERE trade_id='fam-0'")
        db.execute("UPDATE trades SET evaluator='other' WHERE trade_id='fam-1'")
        practice, rows = self.store.ladder_rows("fam", 1, evaluator=EVALUATOR, first_day=days[0], through=days[-1])
        self.assertEqual([r["trade_id"] for r in rows], ["fam-2"])
        self.assertEqual(practice["sessions"], 3)
        _, none = self.store.ladder_rows("fam", 1, evaluator=EVALUATOR, first_day=days[0], through=days[1])
        self.assertEqual(none, [], "nothing after the day judged")


# ================================================================================================== the session's end
class MemoryBridge:
    """The swarm's side, in memory."""

    def __init__(self):
        self.prefilters: dict[str, dict] = {}
        self.requests: dict[str, dict] = {}
        self.refused: str | None = None
        self.promote_fails: str | None = None
        self.promoted: list[dict] = []
        self.families: list[dict] = []
        self.forward: dict[str, list[dict]] = {}
        self.demoted: list[tuple[str, str]] = []
        #: L0: each family's validation verdict (True unless named); the families as the swarm's store holds them.
        self.validated: dict[str, bool | None] = {}
        self.status: dict[str, dict | None] = {}
        self.swept: list[set] = []

    def prefilter(self, run_sha):
        return self.prefilters.get(run_sha)

    def request_prefilter(self, run_sha, *, family, version, bundle, day):
        self.requests[run_sha] = {"family": family, "version": version, "bundle": bundle, "day": day}

    def settle_prefilter(self, run_sha):
        self.requests.pop(run_sha, None)

    def sweep_prefilter(self, active):
        keep = set(active)
        self.swept.append(keep)
        gone = [sha for sha in self.requests if sha not in keep]
        for sha in gone:
            self.requests.pop(sha)
        return len(gone)

    def family_status(self, family):
        if family in self.status:
            return self.status[family]
        return {"retired": False, "band": "gym", "version": None, "proof": {}}

    def validation(self, family, version):
        return self.validated.get(family, True)

    def refusal(self, family, version, run_sha):
        return self.refused

    def promote(self, **kw):
        if self.promote_fails:
            return self.promote_fails
        self.promoted.append(kw)
        return None

    def ladder_families(self):
        return self.families

    def forward_rows(self, family):
        return self.forward.get(family, [])

    def demote(self, family, *, why, receipt, at):
        self.demoted.append((family, why))
        return True


@unittest.skipUnless(HAVE, "numpy not installed")
class TheSessionEnd(StoreCase):
    def setUp(self):
        super().setUp()
        self.bridge = MemoryBridge()
        self.events = []
        self.live = SimpleNamespace(observe_store=self.store, clock=lambda: self.now[0],
                                    record=lambda kind, payload, agent=None: self.events.append((kind, payload)))
        self.ladder = L.Ladder(self.live, bridge=self.bridge)
        self.days = sessions("2026-10-05", 25)
        self.bundle = patch.object(L.Ladder, "_bundle", return_value="bundle-1")
        self.bundle.start()
        self.addCleanup(self.bundle.stop)

    def strong(self, fid="fam", n=1, **kw):
        self.store.freeze(self.program(fid, n), day=self.days[0])
        rng = np.random.default_rng(abs(hash(fid)) % 1000)
        self.add_record(fid, n, self.days, [[0.3 + 0.2 * float(rng.standard_normal()) for _ in range(2)]
                                            for _ in self.days], **kw)

    def receipts(self):
        db = self.store._connect()
        return [dict(zip(("id", "family", "verdict", "reasons", "bh_size", "binding", "p_value"), r)) for r in
                db.execute("SELECT id, family, verdict, reasons, bh_size, binding, p_value FROM ladder_decisions ORDER BY id")]

    def run_day(self, binding=False, **changes):
        with patch.object(L.Rules, "from_constitution", return_value=rules(binding=binding, **changes)):
            return self.ladder.end_of_day(self.days[-1])

    def status(self, fid="fam"):
        return self.store._connect().execute("SELECT status, reason FROM cohorts WHERE family=?", (fid,)).fetchone()

    def test_a_short_record_is_judged_short(self):
        self.store.freeze(self.program(), day=self.days[0])
        self.add_record("fam", 1, self.days[:5], [[0.3]] * 5)
        out = self.run_day()
        self.assertEqual(out["verdicts"], {"short": 1})
        [r] = self.receipts()
        self.assertEqual((r["verdict"], r["p_value"], r["bh_size"]), ("short", 1.0, 1))
        self.assertEqual(self.store.entrants(since="2026-01-01")[0]["p_value"], 1.0)

    def test_every_line_met_asks_for_the_prefilter_first(self):
        self.strong()
        self.assertEqual(self.run_day(binding=True)["verdicts"], {"await_prefilter": 1})
        self.assertEqual(self.bridge.requests["sha-fam-1"], {"family": "fam", "version": 1, "bundle": "bundle-1",
                                                             "day": self.days[-1]})
        self.assertEqual(self.bridge.promoted, [])
        self.assertEqual(self.status(), ("active", None))

    def test_a_prefilter_on_another_bundle_is_asked_again(self):
        self.strong()
        self.bridge.prefilters["sha-fam-1"] = {"status": "done", "passed": True, "bundle": "bundle-0",
                                               "ran_bundle": "bundle-0"}
        self.assertEqual(self.run_day(binding=True)["verdicts"], {"await_prefilter": 1})
        self.assertEqual(self.bridge.requests["sha-fam-1"]["bundle"], "bundle-1")

    def test_not_binding_it_would_promote_and_promotes_nothing(self):
        self.strong()
        self.bridge.prefilters["sha-fam-1"] = {"status": "done", "passed": True, "bundle": "bundle-1",
                                               "ran_bundle": "bundle-1"}
        self.assertEqual(self.run_day(binding=False)["verdicts"], {"would_promote": 1})
        self.assertEqual(self.bridge.promoted, [])
        self.assertEqual(self.status(), ("active", None), "it keeps practising")
        self.assertEqual(self.receipts()[-1]["binding"], 0)

    def test_binding_it_promotes_the_practised_program_with_its_receipt(self):
        self.strong()
        self.bridge.prefilters["sha-fam-1"] = {"status": "done", "passed": True, "bundle": "bundle-1",
                                               "ran_bundle": "bundle-1"}
        self.assertEqual(self.run_day(binding=True)["verdicts"], {"promoted": 1})
        [promotion] = self.bridge.promoted
        [receipt] = self.receipts()
        self.assertEqual(promotion["receipt"], receipt["id"])
        self.assertEqual((promotion["family"], promotion["version"], promotion["snapshot"]["code"]), ("fam", 1, CODE))
        self.assertEqual(receipt["verdict"], "promote")
        self.assertEqual(self.status()[0], "promoted")
        self.assertNotIn("sha-fam-1", self.bridge.requests)
        self.assertEqual(self.events[-1], ("live.band", {"family": "fam", "from": "gym", "to": "probe", "version": 1,
                                                         "receipt": receipt["id"], "why": "the forward ladder promoted it"}))

    def test_a_negative_prefilter_fails_the_cohort(self):
        self.strong()
        self.bridge.prefilters["sha-fam-1"] = {"status": "done", "passed": False, "bundle": "bundle-1",
                                               "ran_bundle": "bundle-1"}
        self.assertEqual(self.run_day(binding=True)["verdicts"], {"prefilter_negative": 1})
        self.assertEqual(self.status(), ("failed", "ladder: the pre-filter read was negative"))

    def test_the_belt_and_a_refused_promotion_fail_the_cohort(self):
        self.strong()
        self.bridge.prefilters["sha-fam-1"] = {"status": "done", "passed": True, "bundle": "bundle-1",
                                               "ran_bundle": "bundle-1"}
        self.bridge.refused = "the family retired"
        self.assertEqual(self.run_day(binding=True)["verdicts"], {"blocked": 1})
        self.assertEqual(self.status(), ("failed", "ladder: the family retired"))
        self.strong("two")
        self.bridge.prefilters["sha-two-1"] = dict(self.bridge.prefilters["sha-fam-1"])
        self.bridge.refused, self.bridge.promote_fails = None, "the family is at probe, not in the Gym band"
        self.assertEqual(self.run_day(binding=True)["verdicts"], {"blocked": 1})
        self.assertEqual(self.receipts()[-1]["verdict"], "blocked", "the promote receipt ends blocked")
        self.assertEqual(self.status("two")[0], "failed")

    def test_the_desk_wide_fdr_counts_every_entrant_of_its_window(self):
        self.strong()
        for i in range(3):                                   # entrants with no record yet: p = 1 each
            self.store.freeze(self.program(f"new{i}"), day=self.days[-1])
        db = self.store._connect()
        for i in range(250):                                 # and entrants whose cohorts ended without a full record
            db.execute("INSERT INTO entrants(family, version, evaluator, entered_at, entered_day) VALUES(?,?,?,?,?)",
                       (f"gone{i}", 1, EVALUATOR, 1.0, self.days[0]))
        out = self.run_day(binding=True)
        self.assertEqual(out["bh_size"], 254)
        fam = [r for r in self.receipts() if r["family"] == "fam"][0]
        self.assertEqual(fam["verdict"], "fail")
        self.assertIn("the fdr line", json.loads(fam["reasons"]))
        self.assertEqual(self.bridge.requests, {})

    def test_an_old_entrant_leaves_the_window(self):
        self.strong()
        db = self.store._connect()
        for i in range(40):
            self.store.freeze(self.program(f"old{i}"), day="2026-05-01")
            db.execute("UPDATE entrants SET entered_day='2026-05-01' WHERE family=?", (f"old{i}",))
            self.store.close_cohort(f"old{i}", 1, status="failed", day="2026-07-01", reason="r")
        out = self.run_day(binding=True)
        self.assertEqual(out["bh_size"], 1)

    def test_drift_alone_fails_the_drift_line(self):
        self.store.freeze(self.program(), day=self.days[0])
        moves = {d: 4.0 for d in self.days}
        self.add_record("fam", 1, self.days, [[-0.03, -0.03]] * len(self.days), delta=20.0, moves=moves)
        self.run_day(binding=True)
        [r] = self.receipts()
        self.assertEqual(r["verdict"], "fail")
        self.assertEqual(json.loads(r["reasons"]), ["the drift line"])

    def test_one_cohorts_error_stops_no_others_judgement(self):
        self.strong()
        self.strong("two")
        alerts = []
        self.live.alert = lambda level, text: alerts.append(text)
        calls = []

        def prefilter(sha):
            calls.append(sha)
            if sha == "sha-fam-1":
                raise RuntimeError("the store is locked")
            return None

        self.bridge.prefilter = prefilter
        out = self.run_day(binding=True)
        self.assertEqual(out["verdicts"], {"error": 1, "await_prefilter": 1})
        self.assertIn("fam@1", alerts[0])
        self.assertEqual(self.bridge.promoted, [])

    def test_a_cohort_under_another_evaluator_is_not_judged(self):
        self.strong()
        self.store.evaluator = "another"
        self.assertEqual(self.run_day()["judged"], 0)

    def test_no_swarm_store_promotes_nothing(self):
        self.strong()
        self.ladder.bridge = None
        self.assertEqual(self.run_day(binding=True)["verdicts"], {"await_validation": 1})
        self.assertIn("no swarm store", self.receipts()[-1]["reasons"])

    # ------------------------------------------------------------------ L0: the Validation line (the WP6 review)
    def test_a_version_that_did_not_meet_the_validation_line_fails_and_asks_the_gate_nothing(self):
        self.strong()
        self.bridge.validated["fam"] = False
        self.bridge.prefilters["sha-fam-1"] = {"status": "done", "passed": True, "bundle": "bundle-1",
                                               "ran_bundle": "bundle-1"}
        self.assertEqual(self.run_day(binding=True)["verdicts"], {"validation_failed": 1})
        self.assertEqual(self.bridge.promoted, [])
        self.assertEqual(self.bridge.requests, {}, "no pre-filter read is asked for")
        self.assertEqual(self.status(), ("failed", "ladder: its version did not meet the Validation line"))
        self.assertEqual(self.receipts()[-1]["verdict"], "validation_failed")

    def test_a_train_entrant_never_validated_waits_and_is_still_a_trial(self):
        self.strong()
        self.store.freeze(self.program("other", tier="train"), day=self.days[0])
        self.bridge.validated["fam"] = None
        out = self.run_day(binding=True)
        self.assertEqual(out["verdicts"], {"await_validation": 1, "short": 1})
        self.assertEqual(out["bh_size"], 2)
        self.assertEqual(self.status(), ("active", None), "it keeps practising")
        self.assertEqual((self.bridge.requests, self.bridge.promoted), ({}, []))
        self.bridge.validated["fam"] = True              # the tournament validated it since: the next rung
        self.assertEqual(self.run_day(binding=True)["verdicts"], {"await_prefilter": 1, "short": 1})

    # ------------------------------------------------------------------ the family's state first (the WP6 review)
    def test_a_retired_familys_cohort_ends_and_its_request_goes(self):
        self.strong()
        self.bridge.requests["sha-fam-1"] = {"family": "fam", "version": 1, "bundle": "bundle-1", "day": self.days[0]}
        self.bridge.status["fam"] = {"retired": True, "band": "retired", "version": None, "proof": {}}
        out = self.run_day(binding=True)
        self.assertEqual((out["ended"], out["verdicts"], out["judged"]), ({"family_retired": 1}, {}, 0))
        self.assertEqual(self.status(), ("failed", "ladder: its family retired"))
        self.assertEqual(self.bridge.requests, {})
        self.assertEqual(self.receipts(), [], "nothing judged")
        self.bridge.status["fam"] = None
        self.strong("gone")
        self.bridge.status["gone"] = None
        self.assertEqual(self.run_day()["ended"], {"family_retired": 1})
        self.assertEqual(self.status("gone"), ("failed", "ladder: its family is not in the swarm's store"))

    def test_a_promotion_whose_house_writes_failed_is_made_good_at_the_next_session_end(self):
        self.strong()
        self.bridge.prefilters["sha-fam-1"] = {"status": "done", "passed": True, "bundle": "bundle-1",
                                               "ran_bundle": "bundle-1"}
        alerts = []
        self.live.alert = lambda level, text: alerts.append(text)
        close = self.store.close_cohort

        def locked(family, version, **kw):
            if kw.get("status") == "promoted":
                raise __import__("sqlite3").OperationalError("database is locked")
            return close(family, version, **kw)

        with patch.object(self.store, "close_cohort", side_effect=locked):
            self.assertEqual(self.run_day(binding=True)["verdicts"], {"error": 1})
        [promotion] = self.bridge.promoted                   # the swarm's band was written
        self.assertEqual(self.status(), ("active", None))
        self.assertEqual([e for e in self.events if e[0] == "live.band"], [])
        self.assertTrue(alerts)
        # The swarm's store now holds the band the ladder gave this program by its receipt: a restart (a new ladder on
        # the same stores) makes the House's records good instead of failing the cohort.
        self.bridge.status["fam"] = {"retired": False, "band": "probe", "version": 1,
                                                  "proof": {"route": "ladder", "run_sha": "sha-fam-1",
                                               "receipt": promotion["receipt"]}}
        self.ladder = L.Ladder(self.live, bridge=self.bridge)
        out = self.run_day(binding=True)
        self.assertEqual((out["ended"], out["verdicts"]), ({"promoted": 1}, {}))
        self.assertEqual(self.status()[0], "promoted")
        self.assertEqual(self.events[-1], ("live.band", {"family": "fam", "from": "gym", "to": "probe", "version": 1,
                                                         "receipt": promotion["receipt"],
                                                         "why": "the forward ladder promoted it"}))
        self.assertNotIn("sha-fam-1", self.bridge.requests)
        self.bridge.families = [{"family": "fam", "band": "probe", "version": 1, "promoted_at": self.now[0]}]
        self.bridge.forward["fam"] = [{"day": "2027-01-04", "source": "real", "pnl": -5.0, "max_loss": 100.0,
                                       "version": 1}] * 21
        self.run_day()
        self.assertEqual(self.status()[0], "demoted", "its later demotion finds it promoted")

    def test_a_band_another_receipt_or_program_gave_is_not_taken_for_this_promotion(self):
        self.strong()
        receipt = self.store.add_decision({"day": self.days[0], "family": "fam", "version": 1, "run_sha": "sha-fam-1",
                                           "inputs": "x", "stats": {}, "verdict": "would_promote", "binding": False})
        for proof in ({"route": "ladder", "run_sha": "sha-fam-1", "receipt": receipt},       # not a promote receipt
                      {"route": "ladder", "run_sha": "sha-other", "receipt": receipt},
                      {"route": "holdout", "run_sha": "sha-fam-1", "receipt": receipt}):
            self.bridge.status["fam"] = {"retired": False, "band": "probe", "version": 1, "proof": proof}
            self.assertEqual(self.run_day()["ended"], {}, proof)
        self.assertEqual(self.status(), ("active", None))

    # ------------------------------------------------------------------ one error stops nothing else (the WP6 review)
    def test_one_cohorts_read_error_stops_neither_another_nor_the_demotions(self):
        self.strong()
        self.strong("two")
        alerts = []
        self.live.alert = lambda level, text: alerts.append(text)
        rows = self.store.ladder_rows

        def broken(family, version, **kw):
            if family == "fam":
                raise __import__("sqlite3").OperationalError("database is locked")
            return rows(family, version, **kw)

        self.bridge.families = [{"family": "old", "band": "probe", "version": 1, "promoted_at": None}]
        self.bridge.forward["old"] = [{"day": d, "source": "real", "pnl": -5.0, "max_loss": 100.0, "version": 1}
                                      for d in self.days[:21]]
        with patch.object(self.store, "ladder_rows", side_effect=broken):
            out = self.run_day(binding=True)
        self.assertEqual(out["verdicts"], {"error": 1, "await_prefilter": 1})
        self.assertEqual([d["family"] for d in out["demoted"]], ["old"])
        self.assertIn("fam@1", alerts[0])

    def test_one_familys_demotion_error_stops_no_other(self):
        alerts = []
        self.live.alert = lambda level, text: alerts.append(text)
        self.bridge.families = [{"family": "bad", "band": "probe", "version": 1, "promoted_at": None},
                                {"family": "old", "band": "probe", "version": 1, "promoted_at": None}]
        self.bridge.forward["old"] = [{"day": d, "source": "real", "pnl": -5.0, "max_loss": 100.0, "version": 1}
                                      for d in self.days[:21]]
        forward = self.bridge.forward_rows

        def rows(family):
            if family == "bad":
                raise RuntimeError("unreadable")
            return forward(family)

        self.bridge.forward_rows = rows
        self.assertEqual([d["family"] for d in self.run_day()["demoted"]], ["old"])
        self.assertIn("bad", alerts[0])
        self.bridge.ladder_families = lambda: (_ for _ in ()).throw(RuntimeError("the store is locked"))
        self.assertEqual(self.run_day()["demoted"], [], "the session's end still ends")

    def test_requests_of_cohorts_no_longer_active_are_swept(self):
        self.strong()
        self.bridge.requests["sha-ended"] = {"family": "ended", "version": 1, "bundle": "bundle-1", "day": self.days[0]}
        out = self.run_day(binding=False)                    # its own request stays: its cohort is active
        self.assertEqual(out["swept"], 1)
        self.assertEqual(set(self.bridge.requests), {"sha-fam-1"})
        self.store.close_cohort("fam", 1, status="failed", day=self.days[-1], reason="r")
        self.run_day()
        self.assertEqual(self.bridge.requests, {}, "its cohort ended: its request goes too")

    def test_a_ladder_probe_is_demoted_on_a_negative_record_or_a_low_session_bound(self):
        self.strong()
        self.store.close_cohort("fam", 1, status="promoted", day=self.days[0], reason="r")
        promoted_at = dt.datetime(2026, 10, 1, 21, tzinfo=dt.timezone.utc).timestamp()
        self.bridge.families = [{"family": "fam", "band": "probe", "version": 1, "promoted_at": promoted_at}]
        self.bridge.forward["fam"] = [{"day": d, "source": "real", "pnl": -5.0, "max_loss": 100.0, "version": 1}
                                      for d in self.days[:21]]
        out = self.run_day()
        self.assertEqual([d["family"] for d in out["demoted"]], ["fam"])
        self.assertIn("negative over 21 trades", self.bridge.demoted[0][1])
        self.assertEqual(self.status()[0], "demoted")
        self.bridge.demoted.clear()
        rng = np.random.default_rng(5)
        self.bridge.forward["fam"] = [{"day": d, "source": "real", "pnl": float(1.0 + 40 * rng.standard_normal()),
                                       "max_loss": 100.0, "version": 1} for d in self.days[:20]]
        self.bridge.forward["fam"][0]["pnl"] = 60.0          # a mean above zero: not negative
        self.run_day()
        self.assertEqual(len(self.bridge.demoted), 1, "the 20-session bound below zero demotes it")
        self.bridge.demoted.clear()
        self.bridge.forward["fam"] = [{"day": d, "source": "real", "pnl": 20.0 + i % 3, "max_loss": 100.0, "version": 1}
                                      for i, d in enumerate(self.days[:20])]
        self.run_day()
        self.assertEqual(self.bridge.demoted, [])

    def test_the_rows_before_its_promotion_never_save_or_sink_it(self):
        self.bridge.families = [{"family": "fam", "band": "probe", "version": 1,
                                 "promoted_at": dt.datetime(2026, 11, 20, 21, tzinfo=dt.timezone.utc).timestamp()}]
        self.bridge.forward["fam"] = [{"day": d, "source": "nightly", "pnl": -5.0, "max_loss": 100.0, "version": 1}
                                      for d in self.days[:24]]
        self.assertEqual(self.run_day()["demoted"], [])


# ================================================================================================== the swarm's side
class TheSwarmSide(unittest.TestCase):
    def setUp(self):
        from league.swarm.store import SwarmStore
        from league.tests.swarm_fakes import Clock

        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.store = SwarmStore(self.root, clock=Clock())
        self.addCleanup(self.store.close)
        self.store.add_family({"id": "fam", "mechanism": "An invented mechanism.", "structure": "debit_vertical",
                               "roots": ["SPY"], "dte": [0, 5]}, origin="test")
        self.store.add_version("fam", CODE, {"hold": 3}, author="test")
        from league.swarm.gate import run_sha

        self.sha = run_sha(self.store.version("fam", 1))
        self.store.set_state("fam", validation_version=1, validation_line={"passed": True})
        self.families = SimpleNamespace(root=self.root, lock=__import__("threading").Lock(), _db=lambda: self.store)
        self.bridge = L.SwarmBridge(self.families)
        self.snapshot = {"code": CODE, "params": {"hold": 3}, "run_sha": self.sha, "practice_evaluator": EVALUATOR}
        self.observed = ObserveStore(self.root, clock=lambda: 1.0)
        self.addCleanup(self.observed.close)

    def receipt(self, verdict="promote", **changes) -> int:
        """A receipt of the House's practice record (`ladder_decisions`)."""
        row = {"day": "2026-11-02", "family": "fam", "version": 1, "run_sha": self.sha, "inputs": "x", "stats": {},
               "verdict": verdict, "binding": True, **changes}
        return self.observed.add_decision(row)

    def test_a_promotion_bands_exactly_the_practised_program(self):
        from league.swarm import bands

        self.assertIsNone(self.bridge.refusal("fam", 1, self.sha))
        receipt = self.receipt()
        self.assertIsNone(self.bridge.promote(family="fam", version=1, snapshot=self.snapshot, receipt=receipt,
                                              typical=52.6, at=1_790_000_000.0))
        fam = self.store.family("fam")
        self.assertEqual(fam["band"], "probe")
        state = fam["state"]
        self.assertEqual((state["banded_version"], state["banded_evaluator"]["route"], state["banded_evaluator"]["receipt"],
                          state["typical_by_version"]["1"], state["live_promoted_at"]),
                         (1, "ladder", receipt, 52.6, 1_790_000_000.0))
        self.assertTrue(bands.current_banded_evaluator(state, self.sha))
        [row] = bands.read(self.root)
        self.assertEqual((row["band"], row["version"], row["code"], row["params"], row["run_sha"], row["holdout_passed"],
                          row["typical_max_loss_usd"]), ("probe", 1, CODE, {"hold": 3}, self.sha, True, 52.6))
        events = [e for e in self.store.events_after(0) if e["kind"] == "swarm.band"]
        self.assertIn(f"practice receipt {receipt}", events[-1]["payload"]["reason"])
        self.assertEqual(self.bridge.ladder_families(), [{"family": "fam", "band": "probe", "version": 1,
                                                          "promoted_at": 1_790_000_000.0}])

    def test_a_proof_without_its_receipt_or_under_another_fingerprint_is_not_current(self):
        from league.swarm import bands

        self.bridge.promote(family="fam", version=1, snapshot=self.snapshot, receipt=self.receipt(), typical=None, at=1.0)
        state = self.store.family("fam")["state"]
        for change in ({"receipt": None}, {"receipt": True}, {"execution_sha256": "another"}, {"run_sha": "x"}):
            broken = dict(state, banded_evaluator={**state["banded_evaluator"], **change})
            self.assertFalse(bands.current_banded_evaluator(broken, self.sha), change)

    def test_another_program_a_retired_family_or_another_band_refuses_the_promotion(self):
        self.assertIn("not the practised program",
                      self.bridge.promote(family="fam", version=1, snapshot={**self.snapshot, "params": {"hold": 4}},
                                          receipt=1, typical=None, at=1.0))
        self.assertIn("not the practised program", self.bridge.refusal("fam", 1, "another-sha"))
        self.assertEqual(self.store.family("fam")["band"], "gym", "nothing written")
        self.store.set_band("fam", "candidate", reason="test")
        self.assertIn("candidate", self.bridge.refusal("fam", 1, self.sha))
        self.assertIn("candidate", self.bridge.promote(family="fam", version=1, snapshot=self.snapshot, receipt=1,
                                                       typical=None, at=1.0))
        self.store.retire("fam", "test")
        self.assertEqual(self.bridge.refusal("fam", 1, self.sha), "the family retired")

    def test_a_ladder_proof_trades_only_with_its_practice_receipt(self):
        from league.live.families import SwarmFamilies
        from league.swarm import bands

        self.bridge.promote(family="fam", version=1, snapshot=self.snapshot, receipt=41, typical=52.6, at=1.0)
        self.assertEqual(bands.read(self.root), [], "no receipt 41 in the House's record: no row")
        for changes in ({"verdict": "would_promote"}, {"family": "other"}, {"version": 2}, {"run_sha": "another"}):
            receipt = self.receipt(**changes)
            self.store.set_state("fam", banded_evaluator={**self.store.family("fam")["state"]["banded_evaluator"],
                                                          "receipt": receipt})
            self.assertEqual(bands.read(self.root), [], changes)
            self.assertFalse(bands.ladder_receipt(self.root, family="fam", version=1, run_sha=self.sha, receipt=receipt))
        receipt = self.receipt()
        self.store.set_state("fam", banded_evaluator={**self.store.family("fam")["state"]["banded_evaluator"],
                                                      "receipt": receipt})
        [row] = bands.read(self.root)
        families = SwarmFamilies(self.root)
        self.addCleanup(lambda: families._store.close() if families._store is not None else None)
        forward = families.forward_rows("fam")
        self.assertTrue(families.confirm_band(row, "probe", "unchanged", forward))
        self.store.set_state("fam", banded_evaluator={**self.store.family("fam")["state"]["banded_evaluator"],
                                                      "receipt": receipt + 1000})
        self.assertFalse(families.confirm_band(row, "probe", "unchanged", forward), "a copied proof never confirms")
        self.assertFalse(bands.ladder_receipt(self.root / "nowhere", family="fam", version=1, run_sha=self.sha,
                                              receipt=receipt), "an unread record admits nothing")

    def test_the_belt_needs_the_validation_line_under_the_current_research_evaluator(self):
        from league.swarm import bands

        self.store.set_state("fam", validation_version=None, validation_line=None)
        self.assertIn("Validation line", self.bridge.refusal("fam", 1, self.sha), "a Train-tier entrant never validated")
        self.assertIsNone(self.bridge.validation("fam", 1))
        self.store.set_state("fam", validation_version=1, validation_line={"passed": False})
        self.assertIn("Validation line", self.bridge.refusal("fam", 1, self.sha))
        self.assertIs(self.bridge.validation("fam", 1), False)
        self.store.put("research_evaluator", "E2")
        self.store.set_state("fam", validation_version=2, validation_line={"passed": True},
                             validation_verdicts={"1": {"passed": True, "at": "x", "evaluator": "E1"}})
        self.assertIn("Validation line", self.bridge.refusal("fam", 1, self.sha), "a pass under another evaluator")
        self.store.set_state("fam", validation_verdicts={"1": {"passed": True, "at": "x", "evaluator": "E2"}})
        self.assertIsNone(self.bridge.refusal("fam", 1, self.sha), "its latest verdict under this one passed")
        self.assertIs(self.bridge.validation("fam", 1), True)
        self.assertIs(bands.validation_passed({"validation_version": 1, "validation_line": {"passed": True}}, 1, None), True)
        self.assertIsNone(bands.validation_passed({"validation_version": 2, "validation_line": {"passed": True}}, 1, None))

    def test_a_version_the_ladder_demoted_is_refused_again(self):
        self.store.set_state("fam", ladder_demoted={"receipt": 4, "why": "w", "at": 2.0, "version": 1})
        self.assertIn("ladder demoted", self.bridge.refusal("fam", 1, self.sha))
        self.store.set_state("fam", ladder_demoted={"receipt": 4, "why": "w", "at": 2.0, "version": 3})
        self.assertIsNone(self.bridge.refusal("fam", 1, self.sha))

    def test_the_family_as_the_store_holds_it_and_the_requests_sweep(self):
        self.assertEqual(self.bridge.family_status("fam"), {"retired": False, "band": "gym", "version": None, "proof": {}})
        self.assertIsNone(self.bridge.family_status("nobody"))
        for sha in ("a", "b", "c"):
            self.bridge.request_prefilter(sha, family="fam", version=1, bundle="b1", day="2026-11-02")
        self.assertEqual(self.bridge.sweep_prefilter(["b"]), 2)
        self.assertEqual(set(self.store.get(L.PREFILTER_REQUESTS)), {"b"})
        self.store.retire("fam", "test")
        self.assertTrue(self.bridge.family_status("fam")["retired"])

    def test_the_belt_reads_the_programs_verdicts_and_demotions(self):
        self.store.set_state("fam", incubator_barred={self.sha: {"why": "test"}})
        self.assertIn("barred", self.bridge.refusal("fam", 1, self.sha))
        self.store.set_state("fam", incubator_barred={}, robust_failed=[1])
        self.assertIn("demoted", self.bridge.refusal("fam", 1, self.sha))
        self.store.set_state("fam", robust_failed=[], review={"sha": self.sha, "verdict": "fail"})
        self.assertIn("review", self.bridge.refusal("fam", 1, self.sha))
        self.store.set_state("fam", review=None)
        self.store.refuse("fam", 1, "experiment contract", "test")
        self.assertIn("refused", self.bridge.refusal("fam", 1, self.sha))

    def test_the_prefilter_request_is_the_houses_and_the_demotion_goes_back_to_the_gym(self):
        self.bridge.request_prefilter(self.sha, family="fam", version=1, bundle="b1", day="2026-11-02")
        self.assertEqual(self.store.get(L.PREFILTER_REQUESTS)[self.sha]["bundle"], "b1")
        self.assertIsNone(self.bridge.prefilter(self.sha))
        self.store.put(L.PREFILTER_KEY + self.sha, {"status": "done", "passed": True})
        self.assertEqual(self.bridge.prefilter(self.sha)["passed"], True)
        self.bridge.settle_prefilter(self.sha)
        self.assertEqual(self.store.get(L.PREFILTER_REQUESTS), {})
        self.bridge.promote(family="fam", version=1, snapshot=self.snapshot, receipt=3, typical=None, at=1.0)
        self.assertTrue(self.bridge.demote("fam", why="w", receipt=4, at=2.0))
        fam = self.store.family("fam")
        self.assertEqual((fam["band"], fam["state"]["ladder_demoted"]["receipt"]), ("gym", 4))
        self.assertFalse(self.bridge.demote("fam", why="w", receipt=5, at=3.0), "a Gym family has nothing to lose")

    def test_the_sealed_routes_are_retired(self):
        from league.swarm import bands, gate

        self.assertIs(bands.TUITION_ROWS, False)
        self.assertIs(gate.SEALED_LOOKS, False)

    def test_the_default_bridge_is_the_swarms_store_only(self):
        self.assertIsInstance(L.default_bridge(SimpleNamespace(families=self.families)), L.SwarmBridge)
        from league.live.families import MemoryFamilies

        self.assertIsNone(L.default_bridge(SimpleNamespace(families=MemoryFamilies())))


# ================================================================================================== the exit's spot
@unittest.skipUnless(HAVE, "numpy not installed")
class TheExitSpot(unittest.TestCase):
    def day(self, prices):
        under = SimpleNamespace(price=np.array(prices, dtype=float), settle=None, close=None)
        return SimpleNamespace(day=dt.date(2026, 10, 5), open_min=570, chains={"SPY": SimpleNamespace(underlying=under)})

    def test_the_exit_minutes_price_or_the_last_within_five_minutes(self):
        day = self.day([500.0, 501.0, float("nan"), float("nan"), 503.0] + [float("nan")] * 10)
        trade = {"root": "spy", "exit_day": "2026-10-05", "exit_minute": 571}
        self.assertEqual(L.exit_spot(trade, day), 501.0)
        self.assertEqual(L.exit_spot(dict(trade, exit_minute=573), day), 501.0)
        self.assertEqual(L.exit_spot(dict(trade, exit_minute=574), day), 503.0)
        self.assertIsNone(L.exit_spot(dict(trade, exit_minute=584), day), "stale past five minutes")
        self.assertIsNone(L.exit_spot(dict(trade, exit_day="2026-10-06"), day), "another session")
        self.assertIsNone(L.exit_spot(dict(trade, root="QQQ"), day))
        self.assertIsNone(L.exit_spot(trade, None))

    def test_an_expiry_takes_the_settlement_level(self):
        day = self.day([500.0, 502.0])
        self.assertEqual(L.exit_spot({"root": "SPY", "exit_day": "2026-10-05", "exit_minute": None}, day), 502.0)


# ================================================================================================== the live path
from league.tests.live_fakes import MONDAY, at  # noqa: E402
from league.tests.test_live_practice import PracticeCase, trained  # noqa: E402


class TheLivePath(PracticeCase):
    def test_practice_closes_carry_their_exit_spot_and_the_close_judges_the_ladder(self):
        self.clock.set(at(MONDAY, 15, 30))
        self.build(observed=[trained("f", params={"hold": 3, "opens": 3})])
        self.run_to(15, 50)
        db = self.live.observe_store._connect()
        bodies = [json.loads(b) for (b,) in db.execute("SELECT body FROM trades WHERE forced=0")]
        self.assertTrue(bodies, "the program closed trades")
        for b in bodies:
            self.assertIsInstance(b.get("exit_spot"), float)
            self.assertGreater(b["exit_spot"], 0)
            self.assertIsNotNone(L.drift_usd(b), "the drift control's figures are all there")
        [entrant] = self.live.observe_store.entrants(since="2026-01-01")
        self.assertEqual((entrant["family"], entrant["entered_day"]), ("f", MONDAY.isoformat()))
        out = self.run_to(16, 0)
        self.assertEqual(out["ended"], MONDAY.isoformat())
        self.assertEqual(out["ladder"]["verdicts"], {"short": 1})
        [(verdict,)] = db.execute("SELECT verdict FROM ladder_decisions").fetchall()
        self.assertEqual(verdict, "short")
        self.assertEqual([a for a in self.alerts if "ladder" in a[1]], [])


from league.tests.test_live_step import HAVE as HAVE_LIVE, LiveCase  # noqa: E402
from league.tests.live_fakes import VERTICAL  # noqa: E402


@unittest.skipUnless(HAVE_LIVE, "numpy not installed")
class TheLadderProbeLive(LiveCase):
    """A ladder promotion read by the House's own path (`SwarmFamilies`, `OptionsLive`): real money only from the session
    after it, the money table's type and fit checks, and the practice receipt the live path reads (the WP6 review)."""

    def ladder_live(self, *, structure="debit_vertical", typical=50.0, promoted_at=None):
        from league.live.families import SwarmFamilies
        from league.swarm.gate import run_sha
        from league.swarm.store import SwarmStore

        live = self.make([])
        self.addCleanup(live.observe_store.close)
        store = SwarmStore(self.root)
        self.addCleanup(store.close)
        store.add_family({"id": "vert", "mechanism": "An invented mechanism for the ladder's live test.",
                          "structure": structure, "roots": ["SPY"], "dte": [0, 2]}, origin="test")
        version = store.add_version("vert", VERTICAL, {"hold": 600}, author="test")
        sha = run_sha(version)
        store.set_state("vert", validation_version=1, validation_line={"passed": True})
        live.families = SwarmFamilies(self.root)
        self.addCleanup(lambda: live.families._store.close() if live.families._store is not None else None)
        live.account_row = self.venue.account()
        receipt = live.observe_store.add_decision({"day": MONDAY.isoformat(), "family": "vert", "version": 1,
                                                   "run_sha": sha, "inputs": "x", "stats": {}, "verdict": "promote",
                                                   "binding": True})
        snapshot = {"code": VERTICAL, "params": {"hold": 600}, "run_sha": sha,
                    "practice_evaluator": live.observe_store.evaluator}
        self.assertIsNone(L.SwarmBridge(live.families).promote(
            family="vert", version=1, snapshot=snapshot, receipt=receipt, typical=typical,
            at=self.clock() if promoted_at is None else promoted_at))
        return live, store, receipt

    def test_a_ladder_probe_trades_real_money_only_from_the_session_after_its_promotion(self):
        live, store, _ = self.ladder_live()                  # promoted in the session (a late session end's judgement)
        self.run_to(9, 40)
        self.assertEqual(store.family("vert")["band"], "probe")
        self.assertIn("vert@1:s", live.instances)
        self.assertNotIn("vert@1:r", live.instances, "no real instance the session it was promoted")
        self.assertEqual(self.venue.sent, [])
        self.clock.set(at(MONDAY + dt.timedelta(days=1), 9, 31))
        live.minute()
        real = live.instances["vert@1:r"]
        self.assertEqual((real.code, real.params, real.version), (VERTICAL, {"hold": 600}, 1),
                         "exactly the practised program")
        self.assertEqual(len(self.venue.sent), 1)

    def test_a_ladder_probe_whose_type_is_not_real_is_held_at_candidate(self):
        live, store, _ = self.ladder_live(structure="long_straddle", promoted_at=at(MONDAY - dt.timedelta(days=3), 16, 5))
        self.run_to(9, 35)
        self.assertEqual(store.family("vert")["band"], "candidate")
        self.assertNotIn("vert@1:r", live.instances)
        self.assertEqual(self.venue.sent, [])

    def test_a_ladder_probe_whose_typical_unit_does_not_fit_is_held_at_candidate(self):
        live, store, _ = self.ladder_live(typical=5000.0, promoted_at=at(MONDAY - dt.timedelta(days=3), 16, 5))
        self.run_to(9, 35)
        self.assertEqual(store.family("vert")["band"], "candidate")
        self.assertNotIn("vert@1:r", live.instances)
        self.assertEqual(self.venue.sent, [])
        held = [p for p, _ in self.ledger.of("live.band") if p.get("to") == "candidate"]
        self.assertIn("over the Probe's cap", held[0]["why"])

    def test_a_ladder_band_without_its_receipt_never_trades(self):
        live, store, receipt = self.ladder_live(promoted_at=at(MONDAY - dt.timedelta(days=3), 16, 5))
        live.observe_store._connect().execute("UPDATE ladder_decisions SET verdict='blocked' WHERE id=?", (receipt,))
        self.run_to(9, 35)
        self.assertEqual(live.families.read(), [])
        self.assertNotIn("vert@1:r", live.instances)
        self.assertNotIn("vert@1:s", live.instances)
        self.assertEqual(self.venue.sent, [])


# ================================================================================================== the scoreboard
class TheCounts(StoreCase):
    def test_counts_only_never_a_figure_or_a_name(self):
        self.assertEqual(L.counts(self.root / "nowhere")["entrants"], 0)
        for i in range(3):
            self.store.freeze(self.program(f"f{i}"), day="2026-10-05")
        self.store.close_cohort("f0", 1, status="promoted", day="2026-11-02", reason="r")
        self.store.close_cohort("f1", 1, status="failed", day="2026-11-02", reason="r")
        self.store.add_decision({"day": "2026-11-02", "family": "f2", "version": 1, "inputs": "x", "stats": {},
                                 "verdict": "would_promote", "binding": False})
        out = L.counts(self.root, day="2026-11-02")
        self.assertEqual({k: out[k] for k in ("entrants", "in_practice", "promoted", "failed", "demoted", "would_promote")},
                         {"entrants": 3, "in_practice": 1, "promoted": 1, "failed": 1, "demoted": 0, "would_promote": 1})
        self.assertNotIn("f2", json.dumps(out))
        self.assertTrue(all(isinstance(v, (int, bool)) for v in out.values()))


if __name__ == "__main__":
    unittest.main()
