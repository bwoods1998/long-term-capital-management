"""V3-A integration fixes, the ops lens: a job that reports `failed` is a failed receipt; the standing grant through the
runner's real `Context` (the release id from `<base>/current`, never the release directory); the monthly drills; the
runner holding jobs while the House is paused; dollar figures kept out of public alerts; a torn job store never stops
the House; pre-open check 3 with nothing to compare; the budget's p30 freshness in sessions; the pinned House box.
Disposable state and invented figures only."""
import json
import os
import sqlite3
import sys
import tempfile
import types
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from league.ops import schedule as S
from league.ops.registry import JOBS, Job, by_name
from league.ops.runner import Ops, redact
from league.ops.store import read_runs

REPO = Path(__file__).resolve().parents[2]


def at(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()


class FakeHouse:
    def __init__(self, pause=None, stopped=None):
        self.alerts = []
        self.pause = pause
        self._state = {"stopped": {"reason": stopped or ""}}

    def paused(self):
        return None if self.pause is None else {"reason": self.pause}

    def alert(self, level, text, **payload):
        self.alerts.append((level, text, payload))


class RunJobStatus(unittest.TestCase):
    def test_a_job_returning_failed_is_a_failed_result(self):
        from league.ops.__main__ import run_job

        module = types.ModuleType("league_ops_fake_failed")
        module.run = lambda ctx: {"status": "failed", "action": "refused", "error": "the grant was refused"}
        why = types.ModuleType("league_ops_fake_why")
        why.run = lambda ctx: {"status": "failed", "why": "nothing to compare"}
        jobs = {"fake": Job("fake", "league_ops_fake_failed", (S.daily(1),), grace=60),
                "why": Job("why", "league_ops_fake_why", (S.daily(1),), grace=60)}
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(sys.modules, {module.__name__: module, why.__name__: why}), \
                mock.patch("league.ops.registry.by_name", lambda: jobs):
            out = run_job("fake", root=Path(tmp), due_at=0.0)
            self.assertEqual((out["status"], out["error"]), ("failed", "the grant was refused"))
            self.assertEqual(out["summary"]["action"], "refused", "the job's receipt is kept")
            self.assertEqual(run_job("why", root=Path(tmp), due_at=0.0)["error"], "nothing to compare")


class GrantThroughTheRunner(unittest.TestCase):
    """`league/ops/grant.py` under `run_job` and the real `Context`: the release directory is never the release id."""

    def setUp(self):
        from league.tests.fakes import Clock
        from league.live_trading import GRANT_ID, STORE, LiveGrant

        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.base = Path(self.dir.name)
        self.root = self.base / "state"
        self.clock = Clock()
        grant = LiveGrant(self.root / STORE, clock=self.clock)
        grant.enable(GRANT_ID, "700", "5500")
        grant.close()
        self.clock.advance(3600)

    def ctx(self):
        from decimal import Decimal

        from league.ops.context import Context

        ctx = Context("grant", root=self.root, due_at=self.clock(), base=self.base, release=self.base / "releases" / "whatever",
                      config={"live_trading": {"ceiling_usd": "5500"}}, clock=self.clock, settings_value={})
        # The grant's money inputs are its own reads (league/ops/grant.py: only a mapping may hand them in): the
        # gateway readers are patched instead.
        patches = (mock.patch("league.ops.grant.read_equity_now", lambda config: Decimal("700")),
                   mock.patch("league.ops.grant._gateway_funding", lambda config: (lambda after: [])))
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        return ctx

    def owner_deploy(self, release):
        t = self.clock() - 120
        key = f"{release}@{int(t)}"
        rows = [{"ts": t, "deploy": key, "release": release, "stage": "promote", "ok": True, "current": release},
                {"ts": t + 1, "deploy": key, "release": release, "stage": "restart", "ok": True}]
        (self.base / "deploys.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))

    def moved(self):
        from league.constitution import CONSTITUTION

        return mock.patch.dict(CONSTITUTION["tuition"], max_agents=CONSTITUTION["tuition"]["max_agents"] + 1)

    def test_a_refusal_is_a_failed_receipt_and_an_unknown_release_refuses(self):
        from league.ops.__main__ import run_job

        self.owner_deploy("r-owner-2")  # on record, but `current` names no release
        with self.moved():
            out = run_job("grant", root=self.root, due_at=self.clock(), base=self.base, ctx=self.ctx())
        self.assertEqual(out["status"], "failed")
        self.assertIn("release is unknown", out["error"])
        self.assertIn("standing grant refused", out["error"], "the refusal is raised (GrantRefused): its text is the receipt")
        # The warning for a failed occurrence is the runner's (Ops raises it for every failed receipt: test_ops_runner).

    def test_the_release_id_comes_from_current(self):
        from league.ops.__main__ import run_job

        (self.base / "releases" / "r-owner-2").mkdir(parents=True)
        os.symlink("releases/r-owner-2", self.base / "current")
        self.owner_deploy("r-owner-2")
        with self.moved():
            out = run_job("grant", root=self.root, due_at=self.clock(), base=self.base, ctx=self.ctx())
        self.assertEqual((out["status"], out["summary"]["action"]), ("ok", "ratified"))
        self.assertEqual(out["summary"]["release"], "r-owner-2")


class RunnerHolds(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = self.base / "state"
        self.root.mkdir()
        self.now = at("2026-10-05T01:00:00Z")
        self.children = []
        self.jobs = (Job("mutating", "m.mutating", (S.daily(2, 0),), grace=3600),
                     Job("reader", "m.reader", (S.daily(2, 0),), grace=7200, in_pause=True),
                     Job("paid", "m.paid", (S.daily(2, 0),), grace=7200, in_pause=True, paid=True))

    def spawn(self, argv, job):
        child = SimpleNamespace(pid=800001 + len(self.children), returncode=None, argv=argv, job=job.name)
        child.poll = lambda: child.returncode
        self.children.append(child)
        return child

    def ops(self):
        ops = Ops(self.root, base=self.base, release=REPO, clock=lambda: self.now, spawn=self.spawn, kill=lambda p, s: None,
                  proc=lambda pid: None, present=lambda name: True, jobs=self.jobs)
        self.addCleanup(ops.close)
        return ops

    def rows(self):
        return {r["job"]: r for r in read_runs(self.root, "2000", "2100")}

    def test_a_paused_house_skips_what_does_not_run_in_a_pause(self):
        ops = self.ops()
        self.now = at("2026-10-05T02:00:30Z")
        ops.tick(FakeHouse(pause="prune"))
        rows = self.rows()
        self.assertEqual(rows["mutating"]["status"], "skipped")
        self.assertIn("the House is paused (prune)", rows["mutating"]["summary_json"])
        self.assertEqual([c.job for c in self.children], ["paid"], "a job that runs in a pause still starts")

    def test_a_stop_on_buying_work_skips_only_paid_jobs(self):
        ops = self.ops()
        self.now = at("2026-10-05T02:00:30Z")
        house = FakeHouse(stopped="the campaign's Sail allowance is closed")
        ops.tick(house)
        rows = self.rows()
        self.assertEqual(rows["paid"]["status"], "skipped")
        self.assertIn("stopped buying work", rows["paid"]["summary_json"])
        self.assertEqual(self.children[0].job, "mutating")

    def test_no_hold_without_a_house(self):
        ops = self.ops()
        self.now = at("2026-10-05T02:00:30Z")
        ops.tick(None)
        self.assertEqual({job: row["status"] for job, row in self.rows().items()}, {"mutating": "running"})

    def test_the_registry_marks_what_runs_in_a_pause(self):
        jobs = by_name()
        self.assertEqual({j.name for j in JOBS if j.in_pause}, {"budget", "clock", "preopen", "economics"})
        self.assertEqual({j.name for j in JOBS if j.paid}, {"postmortem", "agenda", "engineer"})
        longest = max(j.wall for j in JOBS)
        self.assertGreaterEqual(jobs["grant"].grace, longest + 5 * 60, "an hourly grant waits behind the longest job, never missed")
        self.assertEqual(len(jobs["drills"].triggers), 2)


class PublicAlerts(unittest.TestCase):
    def test_dollar_figures_are_redacted_and_kept_private(self):
        self.assertEqual(redact("preopen 2 grant FAIL: capital $87.20 (ceiling $2,000.00)"),
                         "preopen 2 grant FAIL: capital $[private] (ceiling $[private])")
        self.assertEqual(redact("no figure here"), "no figure here")
        with tempfile.TemporaryDirectory() as tmp:
            ops = Ops(Path(tmp), release=REPO, clock=lambda: at("2026-10-05T01:00:00Z"), spawn=lambda a, j: None,
                      kill=lambda p, s: None, proc=lambda pid: None, present=lambda n: True, jobs=())
            house = FakeHouse()
            ops._alert(house, "warning", "standing grant: capital $87.20 does not cover the smallest real stake")
            ops._alert(house, "info", "plain")
            ops.close()
        (level, text, payload), plain = house.alerts
        self.assertEqual(text, "standing grant: capital $[private] does not cover the smallest real stake")
        self.assertIn("$87.20", payload["_detail"])
        self.assertEqual(plain, ("info", "plain", {}))
        from league.ops.scoreboard import public_problems
        self.assertEqual(public_problems(text), [])


class Attach(unittest.TestCase):
    def test_a_torn_store_is_moved_aside_and_made_again(self):
        from league.ops import attach

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "state"
            root.mkdir()
            (root / "ops.sqlite").write_bytes(b"this is not a database at all" * 100)
            house = FakeHouse()
            house.clock = lambda: at("2026-10-05T01:00:00Z")
            ops = attach(house, root, base=Path(tmp))
            self.assertIsNotNone(ops)
            ops.close()
            self.assertTrue(any(p.name.startswith("ops.sqlite.corrupt-") for p in root.iterdir()))
            self.assertIn("moved aside", house.alerts[0][1])

    def test_a_store_that_cannot_open_leaves_the_house_without_jobs(self):
        from league.ops import attach

        house = FakeHouse()
        house.clock = lambda: 0.0
        with mock.patch("league.ops.runner.OpsStore", side_effect=sqlite3.OperationalError("database is locked")):
            self.assertIsNone(attach(house, Path(tempfile.gettempdir()) / "nowhere-ops-test"))
        self.assertIsNone(house.ops)
        self.assertIn("the House's jobs are off this run", house.alerts[0][1])


class PreopenGateway(unittest.TestCase):
    def test_check_3_fails_when_the_money_table_is_unreadable(self):
        from league.ops.preopen import check_gateway

        h = {"gateway": {"max_loss": {"order_equity_share": "0.1"}}, "errors": {"money": "ImportError: boom"}}
        c = check_gateway(h)
        self.assertFalse(c.ok)
        self.assertIn("money table is unreadable", c.headline())
        self.assertFalse(check_gateway({"gateway": {"max_loss": {"order_equity_share": "0.1"}}}).ok)


class P30Freshness(unittest.TestCase):
    def test_a_weekend_keeps_fridays_close_fresh(self):
        from league.ops.budget import economics_fresh

        friday_close = at("2026-10-16T20:00:00Z")
        self.assertTrue(economics_fresh(friday_close, at("2026-10-19T00:30:00Z")), "Monday 00:30Z: Friday is the last close")
        self.assertTrue(economics_fresh(friday_close, at("2026-10-19T20:20:00Z")), "Monday's own economics may still run")
        self.assertFalse(economics_fresh(friday_close, at("2026-10-20T00:30:00Z")), "Monday's close was missed")
        self.assertFalse(economics_fresh(friday_close + 3600, friday_close), "a cutoff in the future")

    def test_a_holiday_keeps_the_last_close_fresh(self):
        from league.ops.budget import economics_fresh

        wednesday_close = at("2026-11-25T21:00:00Z")  # Thanksgiving Thursday is closed
        self.assertTrue(economics_fresh(wednesday_close, at("2026-11-27T00:30:00Z")))


class HouseBox(unittest.TestCase):
    def test_the_config_pin_wins_over_the_environment(self):
        from league.ops.context import Context

        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"SAILBOX_ID": "sb_forkedfrom01"}):
            pinned = Context("economics", root=Path(tmp), due_at=0.0, config={"backup": {"box_id": "sb_thehouse001"}}, settings_value={})
            self.assertEqual(pinned.house_box(), "sb_thehouse001")
            bare = Context("economics", root=Path(tmp), due_at=0.0, config={}, settings_value={})
            self.assertEqual(bare.house_box(), "sb_forkedfrom01")


class Drills(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = self.base / "state"
        self.root.mkdir()
        self.now = [at("2026-11-07T15:00:30Z")]
        self.launched = []

    def ctx(self, **extra):
        class Health:
            def get(self, path):
                return {"ok": True}

        class Dead:
            def get(self, path):
                from league.ops.context import GatewayError
                raise GatewayError("drill")

        ctx = {"root": self.root, "base": self.base, "now": lambda: self.now[0], "gateway": Health(), "dead_gateway": Dead(),
               "notify": lambda facts: {"ok": True, "sent": True}, "config": {},
               "launch": lambda argv: self.launched.append(argv) or 4242,
               "lock_held": lambda path: False}
        ctx.update(extra)
        return ctx

    def guard_reading(self, age):
        db = sqlite3.connect(self.root / "swarm.sqlite")
        db.execute("CREATE TABLE kv (key TEXT PRIMARY KEY, value TEXT)")
        db.execute("INSERT INTO kv VALUES ('guard', ?)", (json.dumps({"last": {"balance": 1.0, "at": self.now[0] - age}}),))
        db.commit()
        db.close()

    def test_a_month_of_drills_launches_the_rollback_last_and_checks_it_later(self):
        from league.ops import drills

        self.guard_reading(600)
        with mock.patch("league.ops.budget._sent", lambda answer: True):
            out = drills.run(self.ctx())
        self.assertNotIn("status", out, out)
        self.assertEqual(out["ran"], ["funding", "sail_read", "gateway_outage", "swarm_kill", "rollback"])
        self.assertEqual(out["pending"], ["rollback"])
        self.assertEqual(out["drills"]["swarm_kill"]["ok"], None)
        self.assertEqual(self.launched[0][1:4], ["-m", "league.watchdog", "drill-rollback"])
        self.assertIn("gym_box_failure", out["not_drilled"])
        # 17:00Z: the verdict is on record; nothing else runs again.
        launched = at("2026-11-07T15:00:30Z")
        rows = [{"ts": launched + 300, "stage": "restart", "ok": True, "release": "drill-x"},
                {"ts": launched + 900, "stage": "restart", "ok": True, "release": "main-a"},
                {"ts": launched + 960, "stage": "drill", "outcome": "rolled_back", "ok": True, "release": "drill-x", "copy_of": "main-a"}]
        (self.base / "deploys.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
        self.now[0] = at("2026-11-07T17:00:30Z")
        out = drills.run(self.ctx())
        self.assertEqual(out["ran"], ["rollback"])
        self.assertTrue(out["drills"]["rollback"]["ok"])
        self.assertEqual(len(self.launched), 1, "launched once a month")
        self.assertEqual(drills.run(self.ctx())["status"], "skipped")

    def test_a_drill_that_does_not_recover_fails_the_run(self):
        from league.ops import drills

        class Down:
            def get(self, path):
                raise OSError("down")

        self.guard_reading(600)
        with mock.patch("league.ops.budget._sent", lambda answer: True):
            out = drills.run(self.ctx(gateway=Down()))
        self.assertEqual(out["status"], "failed")
        self.assertIn("gateway_outage", out["failed"])
        self.assertFalse(out["drills"]["gateway_outage"]["checks"]["recovered"])

    def test_a_rollback_with_no_verdict_fails_after_its_time(self):
        from league.ops import drills

        state = {"month": "2026-11", "drills": {n: {"ok": True} for n in drills.ORDER if n != "rollback"}}
        state["drills"]["rollback"] = {"launched": {"launched_ts": self.now[0]}, "checked": False}
        drills.save(self.root, state)
        self.now[0] += 600
        self.assertEqual(drills.run(self.ctx())["pending"], ["rollback"])
        self.now[0] += drills.ROLLBACK_VERDICT_SECONDS
        out = drills.run(self.ctx())
        self.assertEqual((out["status"], out["failed"]), ("failed", ["rollback"]))

    def test_the_swarm_kill_waits_for_a_new_swarm(self):
        from league.ops import drills

        (self.root / "swarm.lock").write_text(json.dumps({"pid": 111, "start": "9"}))
        killed = []

        def kill(pid, sig):
            killed.append(pid)
            (self.root / "swarm.lock").write_text(json.dumps({"pid": 222, "start": "10"}))
            (self.root / "swarm.heartbeat").write_text(json.dumps({"pid": 222, "at": self.now[0] + 30}))

        def sleep(seconds):
            self.now[0] += seconds

        ctx = self.ctx(lock_held=lambda path: True, proc=lambda pid: (["python", "-m", "league.swarm", "run", "--root", str(self.root)], "9"),
                       kill=kill, sleep=sleep)
        out = drills.drill_swarm_kill(ctx)
        self.assertEqual((out["ok"], killed), (True, [111]))
        # A pid that is not verifiably the swarm is never signalled.
        killed.clear()
        out = drills.drill_swarm_kill({**ctx, "proc": lambda pid: (["python", "something-else"], "9")})
        self.assertEqual((out["ok"], killed), (False, []))

    def test_the_drills_job_through_the_runner_is_present(self):
        from league.ops.__main__ import run_job

        with mock.patch("league.ops.drills.run", lambda ctx: {"status": "failed", "error": "drills that did not recover: x"}):
            out = run_job("drills", root=self.root, due_at=0.0, base=self.base)
        self.assertEqual(out["status"], "failed")


if __name__ == "__main__":
    unittest.main()
