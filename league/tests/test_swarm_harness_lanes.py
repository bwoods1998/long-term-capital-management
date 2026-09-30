"""The harness loop's lanes: the protected boundary, read-only House observers, ranking, the canary gate, the offline
judges' decision, the arms comparison, and one full lane cycle through the persistent journal."""
from __future__ import annotations

import ast
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from league.swarm import canary as gate
from league.swarm import harness_lanes as lanes
from league.swarm import improvement as labmod
from league.swarm.store import SwarmStore
from league.tests.swarm_fakes import Clock

REPO = Path(__file__).resolve().parents[2]
try:
    import numpy  # noqa: F401
    HAVE_NUMPY = True
except ImportError:  # pragma: no cover
    HAVE_NUMPY = False


def commit(repo: Path, message: str) -> str:
    labmod.git(repo, "add", ".")
    labmod.git(repo, "-c", "user.name=Harness Test", "-c", "user.email=harness@example.invalid", "commit", "-qm", message)
    return labmod.git(repo, "rev-parse", "HEAD")


def run(fid: str, status: str, n: int) -> dict:
    return {"run_id": f"{fid[:8]}{status[:4]}{n:012d}"[:24], "status": status, "trials": 1, "summary": {"train_score": 9.9}}


class Boundary(unittest.TestCase):
    def test_fingerprint_files_match_the_gym_driver(self):
        tree = ast.parse((REPO / "league/gym/driver.py").read_text())
        value = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                     and any(getattr(t, "id", None) == "LEAGUE_FILES" for t in n.targets))
        self.assertEqual(tuple(value), lanes.LEAGUE_FILES)

    def test_objective_sealed_spend_capital_and_release_paths_are_protected_for_every_lane(self):
        for path, why in (("league/swarm/harness_lanes.py", "objective"), ("league/swarm/harness_judges/research.py", "objective"),
                          ("league/tests/test_swarm_store.py", "objective"), ("league/gym/fills.py", "sealed"),
                          ("league/swarm/gate.py", "sealed"), ("league/swarm/guard.py", "spend"), ("gateway/src/index.ts", "spend"),
                          ("league/live/money.py", "capital"), ("league/constitution.py", "capital"), (".github/workflows/ci.yml", "release")):
            self.assertEqual(lanes.protected_reason(path), why, path)
        self.assertIsNone(lanes.protected_reason("league/tests/test_harness_candidate_preflight.py"))
        for lane in lanes.LANES.values():
            for pattern in lane.surface:
                if "*" not in pattern:
                    self.assertIsNone(lanes.protected_reason(pattern), f"{lane.id} surface {pattern} is protected")
        with self.assertRaisesRegex(labmod.ImprovementError, "protected"):
            lanes.surface_check(lanes.LANES["research"], ["league/swarm/researcher.py", "league/swarm/guard.py"])
        with self.assertRaisesRegex(labmod.ImprovementError, "outside"):
            lanes.surface_check(lanes.LANES["research"], ["league/swarm/architect.py"])
        lanes.surface_check(lanes.LANES["memory"], ["league/swarm/architect.py", "league/tests/test_harness_candidate_x.py"])

    def test_content_guard_refuses_new_processes_network_reflection_and_protected_imports(self):
        before = "import json\n\ndef f(x):\n    return json.dumps(x).replace('a', 'b')\n"
        lanes.content_guard("league/swarm/researcher.py", before, before + "\ndef g(y):\n    return sorted(y)\n")
        for added, pattern in (("import subprocess\n", "subprocess"), ("from . import guard\n", "guard"),
                               ("from ..live import money\n", "money"), ("x = eval('1')\n", "eval"),
                               ("open('/tmp/x', 'w')\n", "open")):
            with self.assertRaisesRegex(labmod.ImprovementError, pattern):
                lanes.content_guard("league/swarm/researcher.py", before, before + added)
        lanes.content_guard("league/CONTRACT.md", None, "import subprocess")  # prose is not code

    def test_live_path_follows_live_imports_and_module_level_closures(self):
        modules = lanes.live_path_modules(REPO)
        for path in ("league/live/step.py", "league/gym/engine.py", "league/swarm/gate.py", "league/swarm/bands.py",
                     "league/constitution.py", "league/swarm/researcher.py"):
            self.assertIn(path, modules)
        self.assertNotIn("league/live/__main__.py", modules)
        self.assertNotIn("league/swarm/architect.py", modules)
        found = lanes.classify(["league/swarm/architect.py"], modules)
        self.assertEqual(found["release_class"], "research")
        self.assertEqual(lanes.classify(["league/swarm/researcher.py", "league/swarm/architect.py"], modules)["release_class"],
                         "money_path")
        self.assertEqual(lanes.classify(["league/live/shadow.py"], modules)["release_class"], "evidence_reset")


class Gate(unittest.TestCase):
    def test_arm_split_is_deterministic_and_near_its_fraction(self):
        units = [f"family-{n}" for n in range(4000)]
        chosen = [u for u in units if gate.in_arm("salt", "key", u, 0.25)]
        self.assertEqual(chosen, [u for u in units if gate.in_arm("salt", "key", u, 0.25)])
        self.assertLess(abs(len(chosen) / len(units) - 0.25), 0.03)
        self.assertNotEqual(chosen, [u for u in units if gate.in_arm("other", "key", u, 0.25)])
        self.assertFalse(gate.in_arm("salt", "key", "x", 0))
        self.assertFalse(gate.in_arm("salt", "key", "x", "nan"))

    def test_gate_fails_closed_and_follows_state(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.assertFalse(gate.enabled("k", "u", root=root))
            (root / "harness").mkdir()
            (root / gate.FILE).write_text("{not json")
            gate._CACHE.entries.clear()
            self.assertFalse(gate.enabled("k", "u", root=root))
            for state, expected in (("retained", True), ("reverted", False), ("bogus", False)):
                (root / gate.FILE).write_text(json.dumps({"schema": 1, "arms": {"k": {"state": state, "salt": "s", "fraction": 1.0}}}))
                gate._CACHE.entries.clear()
                self.assertEqual(gate.enabled("k", "u", root=root), expected, state)
            (root / gate.FILE).write_text(json.dumps({"schema": 1, "arms": {"k": {"state": "canary", "salt": "s", "fraction": 1.0}}}))
            gate._CACHE.entries.clear()
            self.assertTrue(gate.enabled("k", "u", root=root))
            self.assertFalse(gate.enabled("other", "u", root=root))
        self.assertEqual(gate.mechanism_unit("A  claim.\nMore"), gate.mechanism_unit("a claim. more"))


class House(unittest.TestCase):
    """A synthetic House state: the observers read only operational counts and never write."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / "state"
        self.clock = Clock(1_790_000_000.0)
        self.store = SwarmStore(self.root, clock=self.clock)
        self.addCleanup(self.store.close)

    def family(self, fid, mechanism, structure="debit_vertical", roots=("SPY",)):
        return self.store.add_family({"id": fid, "mechanism": mechanism, "structure": structure, "roots": list(roots)},
                                     origin="architect")["id"]

    def research(self):
        for n in range(3):
            fid = self.family(f"fam-{n}", f"A distinct mechanism number {n} about opening drives and fades.")
            for k in range(10):
                status = "disqualified" if k < 3 + n else "ok"
                result = run(fid, status, k)
                if status == "disqualified":
                    result = {**result, "runtime": {"disqualified": "25 errors (first: line 7: AttributeError: 'list' object "
                                                                    "has no attribute 'items')", "messages": []}}
                row = self.store.add_run(fid, 1, result, window="train", stress=1.0, purpose="train")
                # the store may suffix a worker id; the observer still joins the cycle to its run
                self.store.event("swarm.cycle", fid, {"run_id": result["run_id"], "gym_seconds": 100.0, "cost_usd": 0.01,
                                                      "trials": 1, "model_calls": 1, "score": 7.7, "note": "private words"})
                self.assertTrue(row["run_id"])
                self.clock.advance(5)
            self.store.add_spend("sail_model", 1.0, family=fid)
        self.store.add_spend("gym_box", 0.5, detail={"box": "sb_1", "seconds": 600.0, "jobs": 8})
        self.store.event("swarm.pool", None, {"action": "batch_failed", "box": "sb_1", "jobs": 8,
                                              "error": "GymError: download failed on sb_1: sailbox transport failed: TimeoutError"})

    def test_research_and_data_counts_join_cycles_to_runs_and_hide_scores(self):
        self.research()
        self.clock.advance(60)
        doc = lanes.measure(self.root, now=self.clock(), seconds=3600)
        metrics = doc["lanes"]["research"]["metrics"]
        self.assertEqual(metrics["tallies"]["train_runs"], 30)
        self.assertEqual(metrics["tallies"]["dq_runs"], 12)
        self.assertAlmostEqual(metrics["train_dq_rate"], 0.4)
        self.assertEqual(metrics["tallies"]["wasted_gym_seconds"], 1200.0)
        self.assertEqual(doc["lanes"]["research"]["join"]["unmatched"], 0)
        self.assertIn("'list' object has no attribute 'items'", doc["lanes"]["research"]["examples"][0]["signature"])
        data = doc["lanes"]["data"]["metrics"]
        self.assertEqual((data["tallies"]["slots"], data["tallies"]["slots_failed"]), (8.0, 8.0))
        text = json.dumps(doc)
        for secret in ("7.7", "9.9", "private words", "train_score"):
            self.assertNotIn(secret, text)

    def test_measure_opens_every_database_read_only(self):
        self.research()
        self.store.close()
        before = {p.name: p.stat().st_mtime_ns for p in self.root.iterdir()}
        real = sqlite3.connect
        opened = []

        def guarded(database, *args, **kwargs):
            opened.append(str(database))
            if not (kwargs.get("uri") and "mode=ro" in str(database)):
                raise PermissionError(f"writable open of {database}")
            return real(database, *args, **kwargs)

        with patch.object(lanes.sqlite3, "connect", side_effect=guarded):
            lanes.measure(self.root, now=self.clock() + 60, seconds=3600)
        self.assertTrue(opened)
        self.assertEqual(before, {p.name: p.stat().st_mtime_ns for p in self.root.iterdir()}, "no file written or created")

    def test_rebirths_follow_the_frozen_first_sentence_detector_on_the_same_slice(self):
        dead = self.family("dead-one", "SMH implied vol is bid through the weeks when the leaders report. Sell the premium after.")
        self.store.retire(dead, "refuted")
        self.store.bury(dead, "refuted")
        self.clock.advance(7200)
        self.family("reborn", "SMH implied vol is bid through the weeks when leaders report. Buy the wings instead now.")
        self.family("other-slice", "SMH implied vol is bid through the weeks when leaders report. Buy the wings.",
                    roots=("QQQ",))
        self.family("new-idea", "Treasury auctions with weak demand push long yields up into the close of the day.")
        doc = lanes.measure(self.root, now=self.clock() + 60, seconds=3600, lanes=["memory"])
        tallies = doc["lanes"]["memory"]["metrics"]["tallies"]
        self.assertEqual((tallies["births"], tallies["rebirths"]), (3.0, 1.0))
        self.assertEqual(doc["lanes"]["memory"]["examples"][0]["family"], "reborn")
        self.assertGreaterEqual(lanes.same_idea("A claim about vol. X.", "A claim about vol. Y."), 1.0)

    def test_execution_counts_practice_rejects_by_cause_and_restart_recovery(self):
        now = self.clock()
        obs = sqlite3.connect(self.root / "observe.sqlite")
        obs.execute("CREATE TABLE events (instance TEXT, account TEXT, event_id INTEGER, family TEXT, version INTEGER, day TEXT,"
                    " minute INTEGER, kind TEXT, body TEXT, recorded_at REAL)")
        rows = [("f1", "intent", "{}")] * 10 + [("f1", "rejected", json.dumps({"reason": "no quote for the leg now"})),
                                               ("f1", "rejected", json.dumps({"reason": "max_loss 150 buys none"}))]
        obs.executemany("INSERT INTO events VALUES ('i','a',?,?,1,'d',0,?,?,?)",
                        [(n, fam, kind, body, now + n) for n, (fam, kind, body) in enumerate(rows)])
        obs.commit()
        obs.close()
        live = sqlite3.connect(self.root / "live.sqlite")
        live.execute("CREATE TABLE orders (status TEXT, placed_at REAL)")
        live.execute("CREATE TABLE events (seq INTEGER PRIMARY KEY, at REAL, kind TEXT, payload TEXT)")
        live.execute("INSERT INTO events(at, kind, payload) VALUES (?, 'live.instance', ?)", (now + 30, json.dumps({"state": "live"})))
        live.execute("INSERT INTO events(at, kind, payload) VALUES (?, 'live.error', '{}')", (now + 4000,))
        live.commit()
        live.close()
        ledger = sqlite3.connect(self.root / "ledger.sqlite")
        ledger.execute("CREATE TABLE ledger (seq INTEGER PRIMARY KEY, kind TEXT, at TEXT, payload TEXT)")
        for at in (now, now + 3900):
            ledger.execute("INSERT INTO ledger(kind, at, payload) VALUES ('ops.started', ?, ?)", (lanes.iso(at), json.dumps({"release": "r"})))
        ledger.commit()
        ledger.close()
        doc = lanes.measure(self.root, now=now + 7200, seconds=7200 + 1, lanes=["execution"])
        tallies = doc["lanes"]["execution"]["metrics"]["tallies"]
        self.assertEqual((tallies["intents"], tallies["rejects"], tallies["harness_rejects"], tallies["feasibility_rejects"]),
                         (10.0, 2.0, 1.0, 1.0))
        self.assertEqual((tallies["restarts"], tallies["restart_failures"]), (2.0, 1.0))
        self.assertEqual(lanes.reject_class("a malformed intent: TypeError"), "program")


class Ranking(unittest.TestCase):
    def measurement(self, **research):
        units = {"a": {"train_runs": 400.0, "dq_runs": 60.0, "ok_runs": 340.0, "gym_seconds": 4000.0,
                       "wasted_gym_seconds": 900.0, "births": 2.0, **research}}
        return {"schema": 1, "policy": lanes.POLICY, "since": 0.0, "until": 86400.0,
                "window": {"since": "x", "until": "y", "seconds": 86400}, "source": {"digest": "d" * 64},
                "lanes": {"research": {"units": units, "spend": {"sail_model": 10.0}, "examples": []},
                          "data": {"units": {"sb": {"gym_usd": 4.0, "gym_seconds": 1000.0, "slots": 1000.0, "slots_failed": 1.0,
                                                    "ok_slots": 999.0}}, "run_totals": {"runs": 10.0, "error_runs": 0.0},
                                   "examples": []}}}

    def test_thresholds_rank_and_explain(self):
        ranked = lanes.rank(self.measurement())
        self.assertEqual(ranked[0]["lane"], "research")
        self.assertTrue(ranked[0]["captured"])
        self.assertAlmostEqual(ranked[0]["value"], 0.15)
        self.assertEqual(ranked[0]["stake"]["usd_per_day"], round(4.0 * 900 / 4000, 2))
        data = next(r for r in ranked if r["lane"] == "data")
        self.assertFalse(data["captured"])
        self.assertIn("not past", data["why_not"])
        few = lanes.rank(self.measurement(train_runs=100.0, dq_runs=50.0))
        self.assertFalse(next(r for r in few if r["lane"] == "research")["captured"], "under the minimum denominator")


class Decisions(unittest.TestCase):
    lane = lanes.LANES["research"]
    bottleneck = lane.bottlenecks[0]

    def units(self, n, dq, *, prefix, runs=20, usd=1.0, cycles=50, errors=0):
        return {f"{prefix}{k}": {"train_runs": runs, "dq_runs": dq, "ok_runs": runs - dq, "research_usd": usd, "births": 1,
                                 "wasted_gym_seconds": dq * 100.0, "cycles": cycles, "cycle_errors": errors} for k in range(n)}

    def test_a_clear_canary_improvement_is_retained(self):
        out = lanes.retention(self.lane, self.bottleneck, self.units(20, 1, prefix="t"), self.units(20, 4, prefix="c"), seed="s")
        self.assertEqual(out["decision"], "retained", out)
        self.assertLess(out["primary"]["p_value"], 0.05)

    def test_no_effect_guard_breach_and_thin_arms(self):
        same = lanes.retention(self.lane, self.bottleneck, self.units(20, 3, prefix="t"), self.units(20, 3, prefix="c"), seed="s")
        self.assertEqual(same["decision"], "revert_recommended")
        costly = lanes.retention(self.lane, self.bottleneck, self.units(20, 1, prefix="t", usd=5.0),
                                 self.units(20, 4, prefix="c"), seed="s")
        self.assertEqual(costly["decision"], "revert_recommended")
        self.assertFalse(next(c for c in costly["checks"] if c["metric"] == "ok_runs_per_usd")["ok"])
        noisy = lanes.retention(self.lane, self.bottleneck, self.units(20, 1, prefix="t", errors=5), self.units(20, 4, prefix="c"),
                                seed="s")
        self.assertEqual(noisy["decision"], "revert_recommended", "a guard rising from zero is a breach")
        thin = lanes.retention(self.lane, self.bottleneck, self.units(2, 0, prefix="t", runs=2), self.units(2, 1, prefix="c", runs=2),
                               seed="s")
        self.assertEqual(thin["decision"], "insufficient_activity")

    def test_group_counts_use_an_exact_test(self):
        restart = lanes.LANES["execution"].bottleneck("restart_failure_rate")
        good = lanes.compare(restart.metric, {}, {}, seed="s", extra_treated={"restart_failures": 0, "restarts": 12},
                             extra_control={"restart_failures": 6, "restarts": 12})
        self.assertEqual(good["test"], "fisher_exact_one_sided")
        self.assertLess(good["p_value"], 0.05)
        self.assertAlmostEqual(lanes.fisher_less(0, 3, 1, 3), 0.5)

    def trees(self, base, head, *, base_exit=0, head_exit=0):
        return {"base": {"regressions": {"exit": base_exit}, "splits": {s: {"metrics": dict(base)} for s in ("dev", "heldout")}},
                "head": {"regressions": {"exit": head_exit}, "splits": {s: {"metrics": dict(head)} for s in ("dev", "heldout")}}}

    def test_offline_verdict_needs_heldout_improvement_safety_and_cost(self):
        base = {"gym_seconds_wasted": 2600.0, "false_refusals": 0, "screen_seconds": 0.05}
        ok = lanes.judge_verdict(self.lane, self.bottleneck, self.trees(base, {**base, "gym_seconds_wasted": 1170.0, "screen_seconds": 3.5}))
        self.assertTrue(ok["passed"], ok)
        slow = lanes.judge_verdict(self.lane, self.bottleneck,
                                   self.trees(base, {**base, "gym_seconds_wasted": 2400.0, "screen_seconds": 400.0}))
        self.assertFalse(slow["passed"])
        unsafe = lanes.judge_verdict(self.lane, self.bottleneck, self.trees(base, {**base, "gym_seconds_wasted": 0.0, "false_refusals": 1}))
        self.assertIn("false_refusals", " ".join(unsafe["reasons"]))
        broken = lanes.judge_verdict(self.lane, self.bottleneck, self.trees(base, {**base, "gym_seconds_wasted": 0.0}, head_exit=1))
        self.assertFalse(broken["passed"])
        memory = lanes.LANES["memory"]
        hold = memory.bottleneck("validation_attempts_per_usd")
        base = {"rebirths_admitted": 8, "novel_refused": 0, "sqlite_statements": 240}
        self.assertTrue(lanes.judge_verdict(memory, hold, self.trees(base, base))["passed"])
        self.assertFalse(lanes.judge_verdict(memory, memory.bottleneck("graveyard_rebirth_rate"), self.trees(base, base))["passed"])


SOURCE = "import json\n\n\ndef preflight(code):\n    return {'status': 'passed'}\n"


class LaneCycle(unittest.TestCase):
    """One research-lane candidate through the journal: capture, brief, stage, evaluate, canary, reconcile."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.temp = Path(temp.name)
        self.repo = self.temp / "repo"
        (self.repo / "league" / "swarm").mkdir(parents=True)
        (self.repo / "league" / "live").mkdir(parents=True)
        (self.repo / "league" / "swarm" / "preflight.py").write_text(SOURCE)
        (self.repo / "league" / "swarm" / "guard.py").write_text("CAP = 1\n")
        labmod.git(self.repo, "init", "-q")
        self.base = commit(self.repo, "baseline")
        self.clock = Clock(1_790_000_000.0)
        self.lab = labmod.HarnessImprovement(self.temp / "journal", repo=self.repo, clock=self.clock)
        self.addCleanup(lambda: self.lab.close())
        with tempfile.TemporaryDirectory() as t:
            tree = Path(t) / "base"
            labmod.archive(self.repo, self.base, tree)
            self.digest = labmod.release_digest(tree)
        self.key = f"harness:research:train_dq_rate:{self.base[:16]}"

    def measurement(self, units, *, since=0.0, until=86400.0, digest=None, deploys=(), current=None):
        return {"schema": 1, "policy": lanes.POLICY, "since": since, "until": until,
                "window": {"since": lanes.iso(since), "until": lanes.iso(until), "seconds": until - since},
                "source": {"digest": digest or self.digest, "release": "/r/base", "started_at": since - 10},
                "current": current, "deploys": list(deploys),
                "lanes": {"research": {"units": units, "spend": {"sail_model": 5.0},
                                       "examples": [{"signature": "AttributeError", "n": 3, "families": ["motive-1"],
                                                     "first_at": "2026-09-30T00:00:00Z"}]}}}

    def units(self, n, dq, prefix, runs=20):
        return {f"{prefix}{k}": {"train_runs": runs, "dq_runs": dq, "ok_runs": runs - dq, "research_usd": 1.0, "births": 1,
                                 "wasted_gym_seconds": dq * 100.0, "cycles": 40, "cycle_errors": 0} for k in range(n)}

    def gated(self):
        return SOURCE.replace("    return {'status': 'passed'}\n",
                              "    from league.swarm import canary\n"
                              f"    if canary.enabled('{self.key}', code, root='.'):\n"
                              "        return {'status': 'refused'}\n    return {'status': 'passed'}\n")

    def test_capture_is_ranked_durable_and_deduplicated(self):
        ranked = self.lab.capture_lanes(self.measurement(self.units(30, 3, "f")), base=self.base)
        self.assertEqual(ranked[0]["key"], self.key)
        head = self.lab.ledger.head()
        self.lab.close()
        self.lab = labmod.HarnessImprovement(self.temp / "journal", repo=self.repo, clock=self.clock)
        self.lab.capture_lanes(self.measurement(self.units(30, 3, "f")), base=self.base)
        self.assertEqual(self.lab.ledger.head(), head, "the same evidence buys no second report")
        job = self.lab.worklist.get(self.key)
        self.assertEqual(job.details["motivating"], ["motive-1"])
        with self.assertRaisesRegex(labmod.ImprovementError, "digest"):
            self.lab.capture_lanes({**self.measurement({}), "source": {}}, base=self.base)

    def test_brief_hides_the_heldout_split_and_stage_enforces_the_boundary(self):
        self.lab.capture_lanes(self.measurement(self.units(30, 3, "f")), base=self.base)
        proposal = self.lab.prepare(self.key, self.temp / "wt")
        brief = proposal["brief"]
        self.assertIn("never shown", brief["heldout"])
        self.assertNotIn(self.lab.secret(), json.dumps(brief))
        self.assertIn("canary.enabled", brief["canary"]["gate"])
        worktree = Path(proposal["worktree"])
        (worktree / "league" / "swarm" / "guard.py").write_text("CAP = 100\n")
        with self.assertRaisesRegex(labmod.ImprovementError, "protected"):
            self.lab.stage(self.key, commit(worktree, "raise a spend cap"))
        labmod.git(worktree, "checkout", "-q", "HEAD~1", "--", "league/swarm/guard.py")
        (worktree / "league" / "swarm" / "preflight.py").write_text(SOURCE.replace("'passed'", "'refused'"))
        with self.assertRaisesRegex(labmod.ImprovementError, "canary"):
            self.lab.stage(self.key, commit(worktree, "ungated"))
        self.assertEqual(self.lab.worklist.get(self.key).state, "revising")
        (worktree / "league" / "swarm" / "preflight.py").write_text(self.gated())
        staged = self.lab.stage(self.key, commit(worktree, "gated"))
        self.assertEqual(staged["classification"]["release_class"], "research")
        self.assertEqual(staged["canary_mode"], "arms")
        self.assertEqual(self.lab.worklist.get(self.key).attempt, 3)
        steps = self.lab.next_steps(root="J", repo="R")
        self.assertIn("evaluate", steps[0]["next"])

    def evaluated(self, head_wasted=1000.0):
        self.lab.capture_lanes(self.measurement(self.units(30, 3, "f")), base=self.base)
        worktree = Path(self.lab.prepare(self.key, self.temp / "wt")["worktree"])
        (worktree / "league" / "swarm" / "preflight.py").write_text(self.gated())
        self.lab.stage(self.key, commit(worktree, "gated"))
        calls = []

        def judge(tree, _judge, command, **_kwargs):
            calls.append((tree.name, command))
            if command[0] == "-m":
                return {"exit": 0, "stdout": "", "stderr": "", "seconds": 0.1, "cpu_seconds": 0.1, "error": None}
            split = command[command.index("--split") + 1]
            wasted = 2600.0 if tree.name == "base" else head_wasted
            body = {"protocol": "research-workflow-v1", "split": split, "provider_calls": 0, "gym_seconds_wasted": wasted,
                    "false_refusals": 0, "screen_seconds": 0.1 if tree.name == "base" else 3.0}
            return {"exit": 0, "stdout": json.dumps(body), "stderr": "", "seconds": 0.1, "cpu_seconds": 0.1, "error": None}

        with patch.object(labmod, "sandbox", side_effect=judge):
            receipt = self.lab.evaluate(self.key, python=Path(sys.executable))
        seeds = {c[1][c[1].index("--seed") + 1] for c in calls if "--seed" in c[1]}
        self.assertEqual(len(seeds), 1, "both trees and both splits share one held-out seed")
        self.assertEqual(receipt["heldout_seed"], seeds.pop())
        return receipt

    def test_offline_failure_leaves_attempts_then_rejects(self):
        receipt = self.evaluated(head_wasted=2500.0)
        self.assertFalse(receipt["passed"])
        self.assertEqual(self.lab.worklist.get(self.key).state, "revising")

    def deploy_rows(self, release="cand-release", promoted_at=90000.0):
        digest = self.lab.worklist.get(self.key).carry["_proposal"]["release_digest"]
        common = {"deploy": f"{release}@1", "release": release}
        return [{**common, "stage": "start", "watch_seconds": 600}, {**common, "stage": "stage", "ok": True, "digest": digest},
                {**common, "stage": "canary", "ok": True, "ticks": 3}, {**common, "stage": "watch", "ok": True, "grace": False},
                {**common, "stage": "verdict", "verdict": "promoted", "at": lanes.iso(promoted_at)}]

    def started(self):
        self.assertTrue(self.evaluated()["passed"])
        self.assertEqual(self.lab.worklist.get(self.key).state, "canary")
        digest = self.lab.worklist.get(self.key).carry["_proposal"]["release_digest"]
        waiting = self.lab.canary_start(self.key, measurement=self.measurement({}, since=89000, until=90100, digest=digest))
        self.assertIn("waiting", waiting)
        started = self.lab.canary_start(self.key, measurement=self.measurement(
            {}, since=89000, until=90100, digest=digest, deploys=self.deploy_rows(), current="cand-release"))
        arm = started["started"]
        self.assertEqual(gate.read(self.temp / "journal" / "canary.json")[self.key]["state"], "canary")
        return arm, digest

    def arms(self, arm, treated_dq, control_dq):
        units = {}
        for n in range(400):
            fid = f"u{n}"
            dq = treated_dq if gate.in_arm(arm["salt"], self.key, fid, arm["fraction"]) else control_dq
            units[fid] = {"train_runs": 20, "dq_runs": dq, "ok_runs": 20 - dq, "research_usd": 1.0, "births": 1,
                          "wasted_gym_seconds": dq * 100.0, "cycles": 40, "cycle_errors": 0}
        units["motive-1"] = {"train_runs": 20, "dq_runs": 20, "ok_runs": 0, "research_usd": 1.0, "births": 1,
                             "wasted_gym_seconds": 2000.0, "cycles": 40, "cycle_errors": 0}
        return units

    def test_canary_beats_the_control_and_is_retained_once(self):
        arm, digest = self.started()
        since, until = arm["since"], arm["since"] + 6 * 3600
        early = self.lab.reconcile_lane(self.key, measurement=self.measurement(
            self.arms(arm, 1, 4), since=since, until=since + 600, digest=digest, deploys=self.deploy_rows(), current="cand-release"))
        self.assertIn("waiting", early)
        final = self.measurement(self.arms(arm, 1, 4), since=since, until=until, digest=digest, deploys=self.deploy_rows(),
                                 current="cand-release")
        result = self.lab.reconcile_lane(self.key, measurement=final)
        self.assertEqual(result["decision"], "retained", result)
        self.assertEqual(result["motivating_excluded"], 1)
        self.assertEqual(self.lab.worklist.get(self.key).state, "verified")
        self.assertEqual(gate.read(self.temp / "journal" / "canary.json")[self.key]["state"], "retained")
        rows = self.lab.ledger.head()
        worse = self.measurement(self.arms(arm, 4, 1), since=since, until=until, digest=digest, deploys=self.deploy_rows(),
                                 current="cand-release")
        self.assertEqual(self.lab.reconcile_lane(self.key, measurement=worse), result, "no second look")
        self.assertEqual(self.lab.ledger.head(), rows)
        self.assertGreater(self.lab.ledger.verify(), 5)

    def test_a_canary_that_does_not_beat_the_control_is_flipped_back(self):
        arm, digest = self.started()
        since = arm["since"]
        result = self.lab.reconcile_lane(self.key, measurement=self.measurement(
            self.arms(arm, 3, 3), since=since, until=since + 6 * 3600, digest=digest, deploys=self.deploy_rows(),
            current="cand-release"))
        self.assertEqual(result["decision"], "reverted")
        self.assertEqual(self.lab.worklist.get(self.key).state, "rejected")
        self.assertEqual(gate.read(self.temp / "journal" / "canary.json")[self.key]["state"], "reverted")


class Judges(unittest.TestCase):
    """The fixed judges run as the sandbox runs them: a script importing the tree from PYTHONPATH."""

    def judge(self, name, split="dev", seed="dev"):
        env = {**os.environ, "PYTHONPATH": str(REPO), "PYTHONDONTWRITEBYTECODE": "1"}
        out = subprocess.run([sys.executable, str(REPO / "league/swarm/harness_judges" / f"{name}.py"), "--split", split,
                              "--seed", seed], capture_output=True, text=True, env=env, cwd=str(REPO), timeout=300)
        self.assertEqual(out.returncode, 0, out.stderr[-2000:])
        return json.loads(out.stdout.strip().splitlines()[-1])

    def test_memory_judge_labels_by_construction(self):
        dev = self.judge("memory")
        self.assertEqual((dev["rebirths_proposed"], dev["novel_proposed"], dev["provider_calls"]), (8, 8, 0))
        self.assertEqual(dev["novel_refused"], 0)
        held = self.judge("memory", "heldout", "00aa11bb22cc33dd")
        self.assertEqual(held, {**held, "rebirths_proposed": 12, "novel_proposed": 12})
        self.assertEqual(held["seed"], "00aa11bb22cc33dd")

    def test_heldout_cases_follow_the_seed_and_differ_from_dev(self):
        sys.path.insert(0, str(REPO / "league/swarm/harness_judges"))
        self.addCleanup(sys.path.remove, str(REPO / "league/swarm/harness_judges"))
        import data as data_judge
        import research as research_judge

        a, b = research_judge.cases("heldout", "s1"), research_judge.cases("heldout", "s2")
        self.assertEqual(a, research_judge.cases("heldout", "s1"))
        self.assertNotEqual([c["code"] for c in a], [c["code"] for c in b])
        dev = {c["code"] for c in research_judge.cases("dev", "dev")}
        self.assertFalse(dev & {c["code"] for c in a})
        self.assertNotEqual(data_judge.cases("heldout", "s1"), data_judge.cases("heldout", "s2"))

    def test_data_judge_never_retries_a_permanent_fault(self):
        dev = self.judge("data")
        self.assertEqual((dev["retried_permanent"], dev["failed_transient"]), (0, 0))

    @unittest.skipUnless(HAVE_NUMPY, "the research and execution judges need numpy")
    def test_research_and_execution_judges_keep_their_safety_counts(self):
        research = self.judge("research")
        self.assertEqual(research["false_refusals"], 0)
        self.assertGreater(research["cases"], 20)
        execution = self.judge("execution")
        self.assertEqual(execution["invalid_accepted"], 0)


@unittest.skipUnless(shutil.which("git"), "git is required")
class Cli(unittest.TestCase):
    def test_measure_and_lanes_need_no_journal_and_rank_writes_candidates(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            store = SwarmStore(root / "state", clock=Clock(1_790_000_000.0))
            store.close()
            script = REPO / "scripts" / "harness_improve.py"
            lanes_out = subprocess.run([sys.executable, str(script), "lanes"], capture_output=True, text=True, timeout=120)
            self.assertEqual(sorted(json.loads(lanes_out.stdout)["lanes"]), ["data", "execution", "memory", "research"])
            measured = subprocess.run([sys.executable, str(script), "measure", "--swarm", str(root / "state"), "--seconds", "3600",
                                       "--until", "1790000100", "--out", str(root / "m.json")], capture_output=True, text=True,
                                      timeout=120)
            self.assertEqual(measured.returncode, 0, measured.stdout + measured.stderr)
            self.assertEqual(oct((root / "m.json").stat().st_mode & 0o777), "0o600")
            doc = json.loads((root / "m.json").read_text())
            self.assertEqual(sorted(doc["lanes"]), ["data", "execution", "memory", "research"])
            base = "a" * 40
            refused = subprocess.run([sys.executable, str(script), "--root", str(root / "j"), "rank", "--measurement",
                                      str(root / "m.json"), "--base", base], capture_output=True, text=True, timeout=120)
            self.assertIn("digest", json.loads(refused.stdout)["error"])
            doc["source"]["digest"] = "d" * 64
            (root / "m.json").write_text(json.dumps(doc))
            ranked = subprocess.run([sys.executable, str(script), "--root", str(root / "j"), "rank", "--measurement",
                                     str(root / "m.json"), "--base", base, "--out", str(root / "c.json")],
                                    capture_output=True, text=True, timeout=120)
            self.assertEqual(ranked.returncode, 0, ranked.stdout + ranked.stderr)
            self.assertFalse(any(c["captured"] for c in json.loads((root / "c.json").read_text())["candidates"]))
            self.assertEqual(len(list((root / "j" / "measurements").iterdir())), 1)
            steps = subprocess.run([sys.executable, str(script), "--root", str(root / "j"), "next"], capture_output=True,
                                   text=True, timeout=120)
            self.assertEqual(json.loads(steps.stdout), {"next": []})

    def test_the_observer_writes_its_ranked_lanes_to_its_own_directory_only(self):
        from scripts import harness_improve as cli

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            store = SwarmStore(root / "state", clock=Clock(1_790_000_000.0))
            store.close()
            before = sorted(p.name for p in (root / "state").iterdir())
            (root / "harness").mkdir()
            state = cli.lanes_snapshot(root / "harness", root / "state", now=1_790_000_100.0)
            self.assertEqual(state["lanes_captured"], 0)
            ranked = json.loads((root / "harness" / "lanes-ranked.json").read_text())
            self.assertEqual(ranked["policy"], lanes.POLICY)
            self.assertTrue(all(not c["captured"] for c in ranked["candidates"]))
            self.assertEqual(oct((root / "harness" / "lanes-measurement.json").stat().st_mode & 0o777), "0o600")
            self.assertEqual(before, sorted(p.name for p in (root / "state").iterdir()))


if __name__ == "__main__":
    unittest.main()
