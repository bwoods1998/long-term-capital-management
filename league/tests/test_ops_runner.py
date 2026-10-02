"""The House's job runner: one child at a time, receipts for every occurrence, missed and skipped said, restarts healed."""
import json
import os
import signal
import subprocess
import sys
import tempfile
import textwrap
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from league.ops import schedule as S
from league.ops.registry import Job
from league.ops.runner import Ops
from league.ops.store import OpsStore, read_runs

REPO = Path(__file__).resolve().parents[2]


def at(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()


class FakeHouse:
    def __init__(self):
        self.alerts = []

    def alert(self, level, text, **payload):
        self.alerts.append((level, text))


class Runner(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = self.base / "state"
        self.root.mkdir()
        self.now = at("2026-10-05T01:00:00Z")
        self.children, self.killed, self.procs = [], [], {}
        self.present = {"league.ops.a", "league.ops.b", "league.ops.after"}
        self.jobs = (
            Job("a", "league.ops.a", (S.daily(2, 0),), grace=3600, cpu=60, wall=600),
            Job("b", "league.ops.b", (S.daily(2, 0),), grace=7200, cpu=60, wall=600),
            Job("absent", "league.ops.nowhere", (S.daily(3, 0),), grace=3600, owner="WP9"),
            Job("after", "league.ops.after", (S.after("a"),), grace=3600),
        )
        self.house = FakeHouse()

    def spawn(self, argv, job):
        pid = 700001 + len(self.children)
        child = SimpleNamespace(pid=pid, returncode=None, argv=argv, job=job.name)
        child.poll = lambda: child.returncode
        self.children.append(child)
        self.procs[pid] = (argv, "1")
        return child

    def ops(self, **kw):
        kw.setdefault("jobs", self.jobs)
        ops = Ops(self.root, base=self.base, release=REPO, clock=lambda: self.now, spawn=self.spawn,
                  kill=lambda pid, sig: self.killed.append((pid, sig)), proc=self.procs.get,
                  present=lambda name: name in self.present, **kw)
        self.addCleanup(ops.close)
        return ops

    def finish(self, child, status="ok", summary=None, alerts=(), code=0, write=True):
        result = Path(child.argv[child.argv.index("--result") + 1])
        if write:
            result.parent.mkdir(parents=True, exist_ok=True)
            result.write_text(json.dumps({"status": status, "summary": summary or {"n": 1}, "alerts": list(alerts),
                                          "error": None if status != "failed" else "boom"}))
        child.returncode = code

    def rows(self):
        return read_runs(self.root, "2000", "2100")

    def test_a_due_job_runs_as_one_niced_child_and_its_receipt_is_written(self):
        ops = self.ops()
        self.now = at("2026-10-05T02:00:30Z")
        out = ops.tick(self.house)
        self.assertEqual(out["started"], "a")
        self.assertEqual(len(self.children), 1, "one child at a time: b waits")
        argv = self.children[0].argv
        self.assertEqual(argv[1:5], ["-m", "league.ops", "run", "a"])
        self.assertIn("--extra-mb", argv)
        self.assertEqual(argv[argv.index("--due") + 1], "2026-10-05T02:00:00Z")
        self.assertEqual(ops.tick(self.house), {"running": "a"})
        self.finish(self.children[0], summary={"checked": 9}, alerts=[{"level": "error", "text": "a check failed"}])
        self.now += 60
        ops.tick(self.house)
        self.assertEqual([c.job for c in self.children], ["a", "b"])
        a = [r for r in self.rows() if r["job"] == "a"][0]
        self.assertEqual((a["status"], json.loads(a["summary_json"])), ("ok", {"checked": 9}))
        # A job's alert reaches the House, never above warning.
        self.assertIn(("warning", "ops a: a check failed"), self.house.alerts)
        absent = [r for r in self.rows() if r["job"] == "absent"]
        self.assertEqual(absent, [])  # not due yet

    def test_a_job_whose_module_is_absent_is_skipped_with_its_reason(self):
        ops = self.ops()
        self.now = at("2026-10-05T03:00:10Z")
        ops.tick(self.house)
        row = [r for r in self.rows() if r["job"] == "absent"][0]
        self.assertEqual(row["status"], "skipped")
        self.assertIn("league.ops.nowhere is not in this release (WP9)", row["summary_json"])

    def test_a_job_switched_off_in_ops_json_is_skipped(self):
        (self.root / "ops.json").write_text(json.dumps({"jobs": {"a": {"enabled": False}}}))
        ops = self.ops()
        self.now = at("2026-10-05T02:00:30Z")
        ops.tick(self.house)
        self.assertEqual([c.job for c in self.children], ["b"])
        self.assertIn("switched off", [r for r in self.rows() if r["job"] == "a"][0]["summary_json"])

    def test_everything_off_starts_nothing(self):
        (self.root / "ops.json").write_text(json.dumps({"enabled": False}))
        ops = self.ops()
        self.now = at("2026-10-05T02:00:30Z")
        self.assertEqual(ops.tick(self.house), {"enabled": False})
        self.assertEqual(self.children, [])

    def test_a_job_past_its_grace_is_missed_and_said_once(self):
        ops = self.ops()
        self.now = at("2026-10-05T04:30:00Z")  # a's grace ended 03:00, b's 04:00: both missed
        out = ops.tick(self.house)
        self.assertEqual(sorted(out["missed"]), ["a due 2026-10-05T02:00:00Z", "b due 2026-10-05T02:00:00Z"])
        self.assertEqual({r["job"]: r["status"] for r in self.rows()}, {"a": "missed", "b": "missed", "absent": "skipped"})
        warnings = [t for level, t in self.house.alerts if level == "warning"]
        self.assertEqual(len(warnings), 1)
        self.assertIn("2 job occurrence(s) missed", warnings[0])
        ops.tick(self.house)
        self.assertEqual(len([t for level, t in self.house.alerts if "missed" in t]), 1)

    def test_occurrences_before_the_runner_was_installed_are_never_reported(self):
        self.now = at("2026-10-05T05:00:00Z")
        ops = self.ops()
        ops.tick(self.house)
        self.assertEqual(self.rows(), [])
        self.assertEqual(self.house.alerts, [])

    def test_a_child_that_dies_without_a_result_or_outlives_its_wall_time_fails(self):
        ops = self.ops()
        self.now = at("2026-10-05T02:00:30Z")
        ops.tick(self.house)
        self.finish(self.children[0], code=-9, write=False)
        ops.tick(self.house)
        a = [r for r in self.rows() if r["job"] == "a"][0]
        self.assertEqual(a["status"], "failed")
        self.assertIn("killed by a signal", a["error"])
        self.assertTrue(any("the a job failed" in t for _, t in self.house.alerts))
        # b started on that tick; let it run past its wall time.
        self.now += 601
        out = ops.tick(self.house)
        self.assertEqual(out["killed"], "b")
        self.assertEqual(self.killed[-1], (self.children[1].pid, signal.SIGKILL))
        self.assertIn("wall time", [r for r in self.rows() if r["job"] == "b"][0]["error"])

    def test_after_triggers_follow_the_named_job_and_start_triggers_follow_each_house_start(self):
        jobs = self.jobs + (Job("start", "league.ops.a", (S.at_start(),), grace=600),)
        ops = self.ops(jobs=jobs)
        self.assertEqual(ops.tick(self.house)["started"], "start")
        self.finish(self.children[0])
        self.now = at("2026-10-05T02:00:30Z")
        ops.tick(self.house)
        self.assertEqual(self.children[-1].job, "a")
        self.finish(self.children[-1])
        self.now += 30
        ops.tick(self.house)  # settles a; b starts (due at 02:00, earlier than a's follower)
        self.finish(self.children[-1])
        self.now += 30
        ops.tick(self.house)
        self.assertEqual([c.job for c in self.children], ["start", "a", "b", "after"])
        follower = [r for r in self.rows() if r["job"] == "after"][0]
        self.assertEqual(follower["due_at"], [r for r in self.rows() if r["job"] == "a"][0]["finished_at"])

    def test_a_restart_kills_its_orphaned_child_and_runs_the_occurrence_again_inside_its_grace(self):
        ops = self.ops()
        self.now = at("2026-10-05T02:00:30Z")
        ops.tick(self.house)
        orphan = self.children[0]
        self.now += 120
        again = self.ops()  # the House restarted; the old child is still alive
        self.assertEqual(again.recovered, ["a"])
        self.assertIn((orphan.pid, signal.SIGKILL), self.killed)
        row = [r for r in self.rows() if r["job"] == "a"][0]
        self.assertTrue(row["error"].startswith("interrupted"))
        again.tick(self.house)
        self.assertEqual(self.children[-1].job, "a")
        self.finish(self.children[-1])
        again.tick(self.house)
        row = [r for r in self.rows() if r["job"] == "a"][0]
        self.assertEqual((row["status"], row["attempts"]), ("ok", 2))

    def test_health_says_what_is_late_failed_and_running_today(self):
        ops = self.ops()
        self.now = at("2026-10-05T02:00:30Z")
        ops.tick(self.house)
        health = ops.health()
        self.assertEqual((health["running"], health["late"], health["day"]), ("a", ["b"], "2026-10-05"))
        self.finish(self.children[0], status="failed")
        ops.tick(self.house)
        self.assertEqual(ops.health()["failed"], ["a"])

    def test_receipts_go_to_the_house_lane_every_ten_minutes(self):
        lanes = []
        house = SimpleNamespace(alert=lambda *a, **k: None, _background=lambda key, fn, *args: lanes.append((key, args)))
        ops = self.ops()
        ops.tick(house)
        ops.tick(house)
        self.now += 601
        ops.tick(house)
        self.assertEqual([key for key, _ in lanes], ["house:ops-receipts", "house:ops-receipts"])

    def test_the_store_runs_each_occurrence_once(self):
        store = OpsStore(self.root)
        self.addCleanup(store.close)
        self.assertTrue(store.record("x", "2026-10-05T02:00:00Z", "missed", "2026-10-05T04:00:00Z"))
        self.assertFalse(store.record("x", "2026-10-05T02:00:00Z", "skipped", "2026-10-05T04:00:00Z"))
        with self.assertRaises(ValueError):
            store.record("x", "2026-10-06T02:00:00Z", "running", "2026-10-06T02:00:00Z")
        self.assertEqual(os.stat(store.path).st_mode & 0o777, 0o600)


class Child(unittest.TestCase):
    """The child's own bounds, in a real process."""

    def test_the_child_is_niced_and_its_address_space_is_bounded(self):
        if not Path("/proc/self/status").exists():
            self.skipTest("needs /proc")
        code = textwrap.dedent("""
            import json, os
            from league.ops.__main__ import limit
            got = limit(30, 64)
            try:
                block = bytearray(400 * 2 ** 20)
                big = True
            except MemoryError:
                big = False
            print(json.dumps({"nice": os.nice(0), "big": big, "limits": got}))
        """)
        out = subprocess.run([sys.executable, "-c", code], cwd=REPO, capture_output=True, text=True, timeout=60,
                             env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        self.assertEqual(out.returncode, 0, out.stderr)
        got = json.loads(out.stdout.strip().splitlines()[-1])
        self.assertEqual(got["nice"], 19)
        self.assertFalse(got["big"], "a 400 MB allocation passed a 64 MB headroom")
        self.assertEqual(got["limits"]["cpu_seconds"], 30)

    def test_run_job_skips_an_absent_module_and_fails_a_raising_job(self):
        from league.ops.__main__ import run_job
        from league.ops.context import Context

        with tempfile.TemporaryDirectory() as tmp:
            skipped = run_job("drills", root=Path(tmp), due_at=0.0) if not _present("league.ops.drills") else None
            if skipped is not None:
                self.assertEqual(skipped["status"], "skipped")

            class Broken:
                def get(self, *a, **k):
                    raise RuntimeError("the gateway is down")

            ctx = Context("clock", root=Path(tmp), due_at=0.0, config={}, gateway=Broken(), settings_value={})
            failed = run_job("clock", root=Path(tmp), due_at=0.0, ctx=ctx)
            self.assertEqual(failed["status"], "failed")
            self.assertIn("the gateway is down", failed["error"])
            self.assertEqual(run_job("nope", root=Path(tmp), due_at=0.0)["status"], "failed")


def _present(name):
    import importlib.util

    return importlib.util.find_spec(name) is not None


if __name__ == "__main__":
    unittest.main()
