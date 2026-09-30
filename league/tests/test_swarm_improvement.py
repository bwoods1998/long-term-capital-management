"""The harness lab's protected comparison, persistent decisions, and exact-tree deployment evidence."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

from league.swarm import improvement as labmod
from league.swarm.store import SwarmStore
from league.tests.swarm_fakes import Clock


SOURCE = "import time\n\nclass Scheduler:\n    def work(self):\n        return 2\n\nclass Swarm:\n    pass\n"


def commit(repo: Path, message: str) -> str:
    labmod.git(repo, "add", ".")
    labmod.git(repo, "-c", "user.name=Harness Test", "-c", "user.email=harness@example.invalid", "commit", "-qm", message)
    return labmod.git(repo, "rev-parse", "HEAD")


class HarnessCase(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.temp = Path(temp.name)
        self.repo = self.temp / "repo"
        self.repo.mkdir()
        labmod.git(self.repo, "init", "-q")
        self.source = self.repo / labmod.SCHEDULER_PATH
        self.source.parent.mkdir(parents=True)
        self.source.write_text(SOURCE)
        self.base = commit(self.repo, "baseline")
        self.release = self.temp / "releases" / "base-release"
        shutil.copytree(self.repo / "league", self.release / "league")
        self.clock = Clock()
        self.clock.t = 1_790_000_000
        self.swarm = self.temp / "swarm"
        self.store = SwarmStore(self.swarm, clock=self.clock)
        self.addCleanup(self.store.close)
        self.root = self.temp / "journal"
        self.lab = labmod.HarnessImprovement(self.root, repo=self.repo, clock=self.clock)
        self.addCleanup(lambda: self.lab.close())
        self.cycles(self.clock() - 600, held=20, trials=10)
        self.heartbeat(self.release, self.clock() - 4000)

    def cycles(self, begin, *, held, trials, errors=0, usd=0.01):
        now = self.clock.t
        for index in range(held + trials + errors):
            self.clock.t = begin + index
            self.store.event("swarm.cycle", "one", {"model_calls": 1, "hold": index < held,
                             "trials": int(held <= index < held + trials), "cost_usd": usd,
                             "error": "failed" if index >= held + trials else None})
        self.clock.t = now

    def heartbeat(self, release, started):
        (self.swarm / "swarm.heartbeat").write_text(json.dumps({"at": self.clock(), "release": str(release), "started_at": started}))

    def capture(self):
        return self.lab.capture(self.swarm, base=self.base)[0]

    def candidate(self):
        self.source.write_text(SOURCE.replace("return 2", "return 1"))
        return commit(self.repo, "candidate")

    def evaluated(self, *, quality=5, improved=True, test_exit=0, expected=True):
        key = self.capture()
        self.lab.stage(key, self.candidate())
        def judge(tree, *_args, **_kwargs):
            data = {"protocol": "scheduler-work-v1", "quality": 5 if tree.name == "base" else quality,
                    "required": 5, "provider_calls": 0, "idle_model_turns": 3 if tree.name == "base" or not improved else 0,
                    "sqlite_statements": 200, "cpu_seconds": 0.01}
            return {"exit": test_exit if tree.name == "head" and _args[1][0] == "-m" else 0,
                    "seconds": 0.01, "cpu_seconds": 0.01, "stdout": json.dumps(data), "stderr": ""}
        with patch.object(labmod, "sandbox", side_effect=judge):
            result = self.lab.evaluate(key, python=Path(sys.executable))
        self.assertEqual(result["passed"], expected)
        return key

    def deployment(self, key, *, complete=True):
        proposal = self.lab.worklist.get(key).carry["_proposal"]
        release = self.temp / "releases" / "candidate-release"
        shutil.copytree(self.repo / "league", release / "league")
        at = self.clock() + 60
        self.promoted = at
        self.clock.t = at + 100
        self.heartbeat(release, at - 600)
        common = {"deploy": "candidate-release@1", "release": release.name}
        rows = [{**common, "stage": "start", "watch_seconds": 600, "at": labmod.iso(at - 620)},
                {**common, "stage": "stage", "ok": True, "digest": proposal["release_digest"], "at": labmod.iso(at - 610)},
                {**common, "stage": "canary", "ok": True, "ticks": 3, "at": labmod.iso(at - 600)}]
        if complete:
            rows += [{**common, "stage": "watch", "grace": False, "ok": True, "at": labmod.iso(at - 1)},
                     {**common, "stage": "verdict", "verdict": "promoted", "at": labmod.iso(at)}]
        self.deploy_log = self.temp / "deploys.jsonl"
        self.deploy_log.write_text("".join(json.dumps(row) + "\n" for row in rows))
        self.current = release

    def reconcile(self, key):
        return self.lab.reconcile(key, deploy_log=self.deploy_log, current_release=self.current.name, swarm=self.swarm)


class PersistentDecisions(HarnessCase):
    def test_snapshot_excludes_pending_work_and_does_not_export_cycle_text(self):
        self.clock.advance(-1)
        self.store.event("swarm.cycle", "one", {"hold": True, "pending_run": True, "model_calls": 1,
                         "cost_usd": 0.01, "error": "private execution details", "note": "private mechanism", "score": 9.9})
        self.clock.advance(1)
        result = labmod.snapshot(self.swarm, since=self.clock() - 900, until=self.clock())
        self.assertEqual(result["hold_calls"], 20)
        self.assertEqual(result["errors"], 1)
        self.assertEqual(result["model_usd"], .31)
        self.assertNotIn("private", json.dumps(result))
        self.assertNotIn("score", json.dumps(result))

    def test_capture_deduplicates_across_restart_and_never_changes_swarm(self):
        count = self.store._one("SELECT COUNT(*) AS n FROM events")["n"]
        key = self.capture()
        first = self.lab.ledger.head()
        self.lab.close()
        self.lab = labmod.HarnessImprovement(self.root, repo=self.repo, clock=self.clock)
        self.clock.advance(30)
        self.heartbeat(self.release, self.clock() - 4000)
        self.assertEqual(self.capture(), key)
        self.assertEqual(self.lab.ledger.head(), first)
        self.assertEqual(self.lab.ledger.verify(), 1)
        self.assertEqual(self.store._one("SELECT COUNT(*) AS n FROM events")["n"], count)
        self.assertEqual(self.lab.worklist.get(key).details["baseline"]["model_usd"], 0.3)

    def test_stale_or_different_running_release_cannot_supply_baseline(self):
        self.clock.advance(181)
        with self.assertRaisesRegex(labmod.ImprovementError, "fresh"):
            self.capture()
        self.heartbeat(self.release, self.clock() - 4000)
        wrong = self.temp / "another-release"
        wrong.mkdir()
        with self.assertRaisesRegex(labmod.ImprovementError, "match"):
            self.lab.capture(self.swarm, base=self.base, release=wrong)

    def test_protected_evaluator_and_global_changes_are_refused(self):
        key = self.capture()
        protected = self.repo / "league" / "evaluator.py"
        protected.write_text("ALLOW_EVERYTHING = True\n")
        with self.assertRaisesRegex(labmod.ImprovementError, "every other path"):
            self.lab.stage(key, commit(self.repo, "attempt to change evaluator"))
        with self.assertRaisesRegex(labmod.ImprovementError, "protected"):
            labmod.patch_guard(SOURCE, SOURCE.replace("import time", "import os"))
        with self.assertRaisesRegex(labmod.ImprovementError, "reflective"):
            labmod.patch_guard(SOURCE, SOURCE.replace("return 2", "return open('/host-secret').read()"))
        with self.assertRaisesRegex(labmod.ImprovementError, "persistent-store"):
            labmod.patch_guard(SOURCE, SOURCE.replace("return 2", "return self.store._db.execute('DROP TABLE events')"))
        original = SOURCE.replace("return 2", "return self.store.set_state('one', research_wait=None)")
        with self.assertRaisesRegex(labmod.ImprovementError, "state fields"):
            labmod.patch_guard(original, original.replace("research_wait=None", "gate_ready=True"))

    def test_baseline_bytes_and_judge_are_pinned(self):
        key = self.capture()
        proposal = self.lab.worklist.get(key)
        self.lab.worklist.report(key=key, kind=proposal.kind, summary=proposal.summary, evidence=[], agents=[], source="operator", severity="high",
                                 details={"source": {"digest": "not-the-running-tree"}})
        with self.assertRaisesRegex(labmod.ImprovementError, "baseline commit"):
            self.lab.stage(key, self.candidate())
        self.lab.worklist.report(key=key, kind=proposal.kind, summary=proposal.summary, evidence=[], agents=[], source="operator", severity="high",
                                 details={"source": {"digest": labmod.tree_digest(self.release)[0]}})
        self.lab.stage(key, "HEAD")
        changed = self.temp / "modified-judge.py"
        changed.write_text("print('always good')\n")
        with patch.object(labmod, "BENCHMARK", changed), self.assertRaisesRegex(labmod.ImprovementError, "frozen judge"):
            self.lab.evaluate(key, python=Path(sys.executable))

    def test_prepare_creates_isolated_worktree(self):
        key = self.capture()
        target = self.temp / "isolated"
        receipt = self.lab.prepare(key, target)
        self.assertEqual(labmod.git(target, "rev-parse", "HEAD"), self.base)
        self.assertEqual(receipt["worktree"], str(target))
        (target / labmod.SCHEDULER_PATH).write_text(SOURCE.replace("return 2", "return 1"))
        head = commit(target, "isolated candidate")
        self.lab.stage(key, head)
        self.assertEqual(self.source.read_text(), SOURCE)

    def test_canary_requires_exact_tree_complete_watch_and_subsequent_window(self):
        key = self.evaluated()
        self.deployment(key, complete=False)
        self.assertIn("complete successful", self.reconcile(key)["waiting"])
        self.deploy_log.write_text(self.deploy_log.read_text().replace(self.lab.worklist.get(key).carry["_proposal"]["release_digest"], "other-tree"))
        self.assertIn("exact evaluated tree", self.reconcile(key)["waiting"])

    def test_reduced_cost_cannot_buy_a_quality_regression(self):
        key = self.evaluated(quality=4, expected=False)
        self.assertEqual(self.lab.worklist.get(key).state, "rejected")

    def test_fixed_regression_failure_refuses_an_optimistic_benchmark(self):
        key = self.evaluated(test_exit=1, expected=False)
        self.assertEqual(self.lab.worklist.get(key).state, "rejected")

    def test_no_improvement_is_rejected_and_not_reproposed_on_timer(self):
        key = self.evaluated(improved=False, expected=False)
        self.assertEqual(self.lab.worklist.get(key).state, "rejected")
        rows = self.lab.ledger.head()
        self.clock.advance(60)
        self.heartbeat(self.release, self.clock() - 4000)
        self.assertEqual(self.capture(), key)
        self.assertEqual(self.lab.ledger.head(), rows)

    def test_retains_only_after_fixed_window_and_remembers_later_rollback(self):
        key = self.evaluated()
        self.deployment(key)
        self.assertEqual(self.reconcile(key)["waiting"], "subsequent observation window")
        self.assertEqual(self.lab.worklist.get(key).state, "observing")
        self.cycles(self.promoted + 100, held=0, trials=30)
        self.clock.t = self.promoted + 900
        self.heartbeat(self.current, self.promoted - 600)
        result = self.reconcile(key)
        self.assertEqual(result["decision"], "retained")
        self.assertEqual(self.lab.worklist.get(key).state, "verified")
        rows = self.lab.ledger.head()
        self.assertEqual(self.reconcile(key), result)
        self.assertEqual(self.lab.ledger.head(), rows)
        with self.deploy_log.open("a") as log:
            log.write(json.dumps({"stage": "rollback", "ok": True, "from": self.current.name, "to": "base-release"}) + "\n")
        self.assertEqual(self.reconcile(key)["decision"], "reverted")
        self.assertEqual(self.lab.worklist.get(key).state, "rejected")
        self.assertGreater(self.lab.ledger.verify(), 4)
        self.assertEqual(self.lab.worklist.get(key).carry["_proposal"]["baseline"]["model_usd"], 0.3)

    def test_failed_forward_comparison_cannot_be_rescued_by_later_peeking(self):
        key = self.evaluated()
        self.deployment(key)
        self.cycles(self.promoted + 100, held=20, trials=10)
        self.clock.t = self.promoted + 900
        self.heartbeat(self.current, self.promoted - 600)
        result = self.reconcile(key)
        self.assertEqual(result["decision"], "revert_recommended")
        self.cycles(self.promoted + 1000, held=0, trials=1000)
        self.clock.t = self.promoted + 5000
        self.heartbeat(self.current, self.promoted - 600)
        self.assertEqual(self.reconcile(key), result)
        self.assertEqual(self.lab.worklist.get(key).state, "observing", "a recommendation is not an executed rollback")

    def test_insufficient_activity_and_missing_metering_do_not_earn_retention(self):
        key = self.evaluated()
        self.deployment(key)
        self.cycles(self.promoted + 100, held=0, trials=2, usd=0)
        self.clock.t = self.promoted + 900
        self.heartbeat(self.current, self.promoted - 600)
        result = self.reconcile(key)
        self.assertEqual(result["decision"], "insufficient_activity")
        self.assertFalse(result["cost_efficiency_preserved"])
        self.assertEqual(self.lab.worklist.get(key).state, "observing")

    def test_retained_tree_becomes_the_next_generation_baseline(self):
        key = self.evaluated()
        self.deployment(key)
        self.cycles(self.promoted + 100, held=0, trials=30)
        self.clock.t = self.promoted + 900
        self.heartbeat(self.current, self.promoted - 600)
        self.assertEqual(self.reconcile(key)["decision"], "retained")
        self.cycles(self.promoted + 1000, held=40, trials=10)
        self.clock.t = self.promoted + 1200
        self.heartbeat(self.current, self.promoted - 600)
        next_key = self.capture()
        self.assertNotEqual(key, next_key)
        self.assertEqual(self.lab.worklist.get(next_key).details["base"], self.lab.worklist.get(key).commit)


@unittest.skipUnless(shutil.which("bwrap"), "credential-free network namespace requires bwrap")
class IsolatedEvaluation(unittest.TestCase):
    def test_sandbox_cannot_see_host_home_or_network_or_write_candidate(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            tree, judge = root / "tree", root / "judge"
            tree.mkdir()
            judge.mkdir()
            (tree / "pin").write_text("immutable")
            code = ("import os,socket; from pathlib import Path; "
                    "assert 'HOME' not in os.environ; assert not Path('/home').exists(); "
                    "assert not Path('/workspace').exists(); "
                    "s=socket.socket(); s.settimeout(.1); assert s.connect_ex(('1.1.1.1',443)) != 0; "
                    "assert Path('/work/pin').read_text() == 'immutable'\n"
                    "try: Path('/work/pin').write_text('changed')\n"
                    "except OSError: pass\n"
                    "else: raise AssertionError('writable candidate')\n")
            result = labmod.sandbox(tree, judge, ["-c", code], python=Path(sys.executable))
            self.assertEqual(result["exit"], 0, result)

    def test_real_fixed_benchmark_and_regressions_compare_two_commits(self):
        with tempfile.TemporaryDirectory() as td:
            root, repo = Path(td), Path(td) / "repo"
            repo.mkdir()
            for name in ("league", "ltcm", "scripts", "playbooks", "deploy"):
                if (labmod.REPO / name).is_dir():
                    shutil.copytree(labmod.REPO / name, repo / name,
                                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache", ".data"))
            source = repo / labmod.SCHEDULER_PATH
            good = source.read_text()
            marker = "        fams = self.store.families(alive=True)\n        with self._lock:\n"
            self.assertEqual(good.count(marker), 1)
            # A synthetic inefficient baseline with identical scheduling behavior. The candidate removes redundant
            # reads; this tests the real comparison path, not a claim that production exhibits this injected defect.
            source.write_text(good.replace(marker, "        for _ in range(12):\n            self.store.get('unused-query')\n" + marker))
            labmod.git(repo, "init", "-q")
            base = commit(repo, "synthetic redundant-read baseline")
            release = root / "base-release"
            shutil.copytree(repo, release, ignore=shutil.ignore_patterns(".git"))
            # Normalize exactly like the owner upload; repository executable bits are not the deployed modes.
            for file in release.rglob("*"):
                if file.is_file():
                    file.chmod(0o755 if file.suffix == ".sh" else 0o644)
            source.write_text(good)
            head = commit(repo, "remove synthetic redundant reads")
            clock = Clock()
            swarm = root / "swarm"
            store = SwarmStore(swarm, clock=clock)
            lab = labmod.HarnessImprovement(root / "journal", repo=repo, clock=clock)
            try:
                for _ in range(30):
                    store.event("swarm.cycle", "one", {"model_calls": 1, "hold": True, "cost_usd": .01})
                    clock.advance(1)
                (swarm / "swarm.heartbeat").write_text(json.dumps({"at": clock(), "release": str(release), "started_at": clock() - 4000}))
                key = lab.capture(swarm, base=base)[0]
                lab.stage(key, head)
                receipt = lab.evaluate(key, python=Path(sys.executable))
                self.assertTrue(receipt["passed"], json.dumps(receipt, indent=2))
                self.assertEqual(receipt["trees"]["head"]["metrics"]["quality"], 5)
                self.assertLess(receipt["trees"]["head"]["metrics"]["sqlite_statements"],
                                receipt["trees"]["base"]["metrics"]["sqlite_statements"] * .8)
                self.assertEqual(lab.worklist.get(key).state, "canary", "offline success never certifies production retention")
            finally:
                lab.close()
                store.close()


if __name__ == "__main__":
    unittest.main()
