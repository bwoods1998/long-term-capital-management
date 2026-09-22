"""A desk's sandbox: forked from the lab image, woken on demand, fused per day, never a raise."""

from __future__ import annotations

import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from ltcm.sailbox import SailboxError
from ltcm.sandbox import (
    BUILD_HOSTS,
    SANDBOX_HOSTS,
    CodeRun,
    LabImage,
    SandboxManager,
    Toolbox,
    bounded,
)


class Exec:
    def __init__(self, output="", code=0, status="succeeded"):
        self.output = output
        self.stdout = output
        self.stderr = ""
        self.return_code = code
        self.status = status

    @property
    def ok(self):
        return self.return_code == 0

    def check(self):
        if not self.ok:
            raise SailboxError("failed")
        return self


class FakeClient:
    """Records every call; answers like the API would for a healthy fleet."""

    def __init__(self, *, status="running", exec_output="hello\n", exec_code=0, fail_exec=False):
        self.calls = []
        self.status = status
        self.exec_output = exec_output
        self.exec_code = exec_code
        self.fail_exec = fail_exec
        self.forks = 0

    def from_checkpoint(self, checkpoint, *, name):
        self.forks += 1
        self.calls.append(("fork", checkpoint, name))
        return {"sailbox_id": f"sb_{name}", "checkpoint_id": checkpoint, "status": "running"}

    def set_auto_sleep(self, box, *, automatic, min_seconds_before_sleep=None):
        self.calls.append(("autosleep", box, automatic, min_seconds_before_sleep))
        return {}

    def set_egress(self, box, allowlist):
        self.calls.append(("egress", box, tuple(allowlist)))
        return {"document": {"allowlist": list(allowlist)}}

    def get(self, box):
        self.calls.append(("get", box))
        return {"sailbox_id": box, "status": self.status}

    def resume(self, box, **kwargs):
        self.calls.append(("resume", box))
        self.status = "running"
        return {"status": "running"}

    def upload(self, box, path, content, *, mode=0o600, create_parents=True, timeout=300.0):
        self.calls.append(("upload", box, path, content.decode("utf-8"), mode))
        return {}

    def exec(self, box, command, *, timeout=600, **kwargs):
        self.calls.append(("exec", box, command, timeout))
        if self.fail_exec:
            raise SailboxError("exec refused")
        return Exec(self.exec_output, self.exec_code)

    def sleep(self, box, **kwargs):
        self.calls.append(("sleep", box))
        return {}

    def find_app(self, name, *, mint_if_missing=True):
        return {"id": "app_1", "name": name}

    def create(self, **kwargs):
        self.calls.append(("create", kwargs))
        return {"sailbox_id": "sb_image", "status": "running"}

    def checkpoint(self, box, *, name=None, ttl_seconds=None, **kwargs):
        self.calls.append(("checkpoint", box, name))
        self.ttl_seconds = ttl_seconds
        return {"checkpoint_id": "sbcp_image", "name": name, "expires_at": "2027-09-22T00:00:00Z"}


class SandboxCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.clock = [1_800_000_000.0]
        self.client = FakeClient()

    def manager(self, **kwargs):
        options = {"image": {"checkpoint_id": "sbcp_image"}, "clock": lambda: self.clock[0]}
        options.update(kwargs)
        return SandboxManager(
            self.client, self.root / "sandboxes.json", self.root / "toolbox", **options
        )


class RunTests(SandboxCase):
    def test_program_hash_is_not_replaced_by_uploaded_engine_hash(self):
        import hashlib
        source = "print('candidate')"
        self.assertEqual(self.manager().run("a", source).code_sha256, hashlib.sha256(source.encode()).hexdigest())

    def test_unknown_execution_is_not_overwritten_after_restart(self):
        manager = self.manager()
        self.client.exec = lambda *args, **kwargs: Exec("", code=None, status="unconfirmed")
        manager.run("a", "print(1)", timeout=60)
        result = self.manager().run("a", "print(2)", timeout=60)
        self.assertEqual(result.exit_code, 5)
        self.assertIn("prior sandbox execution", result.stdout)

    def test_the_first_run_forks_the_image_and_later_runs_reuse_the_box(self):
        manager = self.manager()
        first = manager.run("mullins", "print('hello')", purpose="probe")
        self.assertEqual(first.exit_code, 0)
        self.assertEqual(first.stdout, "hello\n")
        self.assertEqual(first.sandbox, "sb_lab-mullins")
        self.assertEqual(self.client.forks, 1)
        self.assertIn(("autosleep", "sb_lab-mullins", True, 300), self.client.calls)
        self.assertIn(("egress", "sb_lab-mullins", tuple(SANDBOX_HOSTS)), self.client.calls)
        self.assertNotIn("pypi.org", SANDBOX_HOSTS)
        second = manager.run("mullins", "print('again')", purpose="probe")
        self.assertEqual(self.client.forks, 1, "one sandbox per desk")
        self.assertEqual(second.sandbox, first.sandbox)
        self.assertEqual(manager.box_for("mullins"), "sb_lab-mullins")

    def test_the_code_and_the_toolbox_are_uploaded_and_run_with_a_timeout(self):
        manager = self.manager()
        Toolbox(self.root / "toolbox", "mullins").save("momentum", "def score():\n    return 1\n", "a signal")
        manager.run("mullins", "from toolbox.momentum import score\nprint(score())", purpose="use", timeout=40)
        uploads = [c for c in self.client.calls if c[0] == "upload"]
        paths = [c[2] for c in uploads]
        self.assertIn("/lab/toolbox/momentum.py", paths)
        self.assertIn("/lab/toolbox/__init__.py", paths)
        self.assertIn("/lab/run/main.py", paths)
        self.assertIn("/lab/labkit.py", paths, "labkit rides along on every run, so a fix needs no new image")
        self.assertIn("/lab/floor/ltcm/data/weather.py", paths, "the weather source predates the image")
        for module in ("broker.py", "data/__init__.py", "data/kalshi.py", "data/coinbase.py"):
            self.assertIn(f"/lab/floor/ltcm/{module}", paths, "the kit's whole data layer is the floor's, not the image's")
        for module in ("history.py", "backtest.py"):
            self.assertIn(f"/lab/floor/ltcm/{module}", paths, "a desk can backtest in its own sandbox")
        before = len([c for c in self.client.calls if c[0] == "upload" and c[2].startswith("/lab/floor/")])
        manager.run("mullins", "print(1)", purpose="again", timeout=40)
        after = len([c for c in self.client.calls if c[0] == "upload" and c[2].startswith("/lab/floor/")])
        self.assertEqual(after, before, "unchanged floor modules are not uploaded again")
        self.assertIn(("egress", "sb_lab-mullins", tuple(SANDBOX_HOSTS)), self.client.calls)
        run = [c for c in self.client.calls if c[0] == "exec"][-1]
        self.assertIn("timeout 40 python3 /lab/run/main.py", run[2][2])
        self.assertIn("PYTHONPATH=/lab:/lab/floor", run[2][2])
        self.assertEqual(run[3], 70, "the exec waits a little longer than the code may run")

    def test_labkit_compiles_and_reaches_the_event_source_through_the_real_route(self):
        from ltcm.sandbox import LABKIT

        compile(LABKIT, "labkit.py", "exec")
        self.assertIn('for attr in ("_source", "source")', LABKIT)
        self.assertIn("def kalshi_series(", LABKIT)
        self.assertIn("src.markets(series_ticker=", LABKIT)
        self.assertNotIn("event_markets", LABKIT, "the service's text index does not exist inside a sandbox")

    def test_a_sleeping_box_is_woken_first(self):
        manager = self.manager()
        manager.run("mullins", "print(1)")
        self.client.status = "sleeping"
        manager.run("mullins", "print(2)")
        self.assertIn(("resume", "sb_lab-mullins"), self.client.calls)

    def test_save_as_keeps_the_code_in_the_desks_toolbox(self):
        manager = self.manager()
        run = manager.run("mullins", "def edge():\n    return 0.08\n", purpose="edge rule", save_as="edge")
        self.assertEqual(run.saved_as, "edge")
        box = Toolbox(self.root / "toolbox", "mullins")
        self.assertEqual(list(box.files()), ["edge.py"])
        self.assertEqual(box.index()["edge"]["purpose"], "edge rule")
        bad = manager.run("mullins", "x = 1", save_as="Not Valid")
        self.assertEqual(bad.exit_code, 2)
        self.assertIn("tool name", bad.stdout)

    def test_failures_are_results_never_exceptions(self):
        self.client.fail_exec = True
        run = self.manager().run("mullins", "print(1)")
        self.assertEqual(run.exit_code, 5)
        self.assertIn("sandbox error", run.stdout)
        self.assertEqual(self.manager(image={}).run("mullins", "print(1)").exit_code, 3)
        self.assertEqual(self.manager().run("mullins", "   ").exit_code, 2)
        self.assertEqual(self.manager().run("mullins", "x" * 40_001).exit_code, 2)

    def test_a_failing_script_reports_its_code_and_output(self):
        self.client.exec_output = "Traceback: boom\n"
        self.client.exec_code = 1
        run = self.manager().run("mullins", "raise SystemExit(1)")
        self.assertEqual(run.exit_code, 1)
        self.assertIn("boom", run.stdout)

    def test_the_daily_fuse_stops_a_desk_in_a_loop(self):
        manager = self.manager(daily_seconds=100)
        self.clock[0] += 0  # each run "takes" 60 s on the fake clock
        original = manager.client.exec

        def slow_exec(box, command, **kwargs):
            self.clock[0] += 60
            return original(box, command, **kwargs)

        manager.client.exec = slow_exec
        self.assertEqual(manager.run("mullins", "print(1)").exit_code, 0)
        self.assertEqual(manager.seconds_today("mullins"), 60)
        self.assertEqual(manager.run("mullins", "print(2)").exit_code, 0)  # 40 s left: allowed, timeout shortened
        self.assertEqual(manager.run("mullins", "print(3)").exit_code, 4)
        self.assertIn("used up", manager.run("mullins", "print(3)").stdout)
        # A new day resets the fuse.
        self.clock[0] += 86_400
        self.assertEqual(manager.run("mullins", "print(4)").exit_code, 0)

    def test_output_is_bounded_and_the_payload_is_the_contract_shape(self):
        self.client.exec_output = "x" * 10_000
        run = self.manager().run("mullins", "print('x' * 10000)", purpose="p")
        self.assertLessEqual(len(run.stdout), 4_000 + 80)
        self.assertIn("more characters cut", run.stdout)
        payload = run.to_payload("mullins:20260915-1900:cadence:13:30")
        for key in ("session_id", "code_sha256", "language", "stdout", "exit_code", "seconds", "sandbox", "purpose"):
            self.assertIn(key, payload)
        self.assertEqual(payload["language"], "python")
        self.assertEqual(len(payload["code_sha256"]), 64)
        self.assertIsInstance(payload["exit_code"], int)
        self.assertIsInstance(payload["seconds"], str)

    def test_sleep_all_puts_every_sandbox_to_bed(self):
        manager = self.manager()
        manager.run("mullins", "print(1)")
        manager.run("hilibrand", "print(1)")
        self.assertEqual(manager.sleep_all(), 2)
        self.assertEqual(sorted(c for c in self.client.calls if c[0] == "sleep"), [("sleep", "sb_lab-hilibrand"), ("sleep", "sb_lab-mullins")])

    def test_state_holds_only_box_ids_and_usage(self):
        manager = self.manager()
        manager.run("mullins", "print(1)")
        raw = (self.root / "sandboxes.json").read_text(encoding="utf-8")
        state = json.loads(raw)
        self.assertEqual(state["boxes"], {"mullins": "sb_lab-mullins"})
        self.assertIn("used", state)
        for marker in ("bearer", "sk-", "token", "private key"):
            self.assertNotIn(marker, raw.lower())
        self.assertEqual((self.root / "sandboxes.json").stat().st_mode & 0o777, 0o600)


class SameDeskRunTests(SandboxCase):
    def test_unrelated_boxes_start_concurrently_and_merge_state(self):
        import threading
        from concurrent.futures import ThreadPoolExecutor
        manager = self.manager()
        rendezvous = threading.Barrier(3)
        original = self.client.from_checkpoint
        def fork(*args, **kwargs):
            rendezvous.wait(timeout=3)
            manager._charge(kwargs["name"][4:], 7)
            return original(*args, **kwargs)
        self.client.from_checkpoint = fork
        with ThreadPoolExecutor(max_workers=3) as pool:
            boxes = list(pool.map(manager.ensure_box, ["a", "b", "c"]))
        self.assertEqual(len(set(boxes)), 3)
        self.assertEqual(set(manager.state()["boxes"]), {"a", "b", "c"})
        self.assertEqual([manager.seconds_today(d) for d in ["a", "b", "c"]], [7, 7, 7])

    def test_same_box_is_forked_once_under_concurrency(self):
        from concurrent.futures import ThreadPoolExecutor
        manager = self.manager()
        with ThreadPoolExecutor(max_workers=8) as pool:
            boxes = list(pool.map(manager.ensure_box, ["a"] * 8))
        self.assertEqual(len(set(boxes)), 1)
        self.assertEqual(self.client.forks, 1)

    def test_two_runs_on_one_desk_never_swap_programs(self):
        """A strategy tick and a Foundry dry run on one desk at once: each executes its own
        `/lab/run/main.py`. Until Sept 16, 2026 the second upload could land between the first
        run's upload and its exec, so the first ran the second's program."""
        import threading
        import time as _time

        client = self.client
        files = {}
        lock = threading.Lock()
        base_upload = client.upload

        def upload(box, path, content, **kwargs):
            base_upload(box, path, content, **kwargs)
            with lock:
                files[(box, path)] = content.decode("utf-8")
            if path.endswith("/run/main.py"):
                _time.sleep(0.05)  # the next run's upload lands here without a lock
            return {}

        def execute(box, command, *, timeout=600, **kwargs):
            client.calls.append(("exec", box, command, timeout))
            _time.sleep(0.02)
            with lock:
                return Exec(files.get((box, "/lab/run/main.py"), ""))

        client.upload, client.exec = upload, execute
        manager = self.manager()
        manager.run("mullins", "print('warm')")  # the box exists before the race
        results = {}

        def run(label):
            results[label] = manager.run("mullins", f"print('{label}')", purpose=label).stdout

        threads = [threading.Thread(target=run, args=(label,)) for label in ("strategy", "dry-run", "session")]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(10)
        self.assertEqual(results, {label: f"print('{label}')" for label in ("strategy", "dry-run", "session")})


class PolicyTests(unittest.TestCase):
    def test_a_sandbox_can_reach_data_and_never_money_or_credit(self):
        for host in SANDBOX_HOSTS:
            self.assertNotIn("workers.dev", host)
            self.assertNotIn("sailresearch", host)
        self.assertTrue(set(SANDBOX_HOSTS) < set(BUILD_HOSTS))
        self.assertIn("pypi.org", BUILD_HOSTS)

    def test_bounded_keeps_the_head_and_the_tail(self):
        text = "a" * 5000 + "END"
        cut = bounded(text, 1000)
        self.assertTrue(cut.startswith("a" * 100))
        self.assertTrue(cut.endswith("END"))
        self.assertEqual(bounded("short"), "short")


class LabImageTests(unittest.TestCase):
    def test_the_image_is_built_once_provisioned_checked_and_recorded(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        (root / "ltcm" / "data").mkdir(parents=True)
        (root / "ltcm" / "__init__.py").write_text("", encoding="utf-8")
        (root / "ltcm" / "broker.py").write_text("# broker", encoding="utf-8")
        (root / "ltcm" / "data" / "__init__.py").write_text("# data", encoding="utf-8")
        client = FakeClient(exec_output="labkit ok\n")
        said = []
        image = LabImage(client, app="ltcm", repo_root=root, record_path=root / ".data" / "lab_image.json")
        record = image.build(say=said.append)
        self.assertEqual(record["checkpoint_id"], "sbcp_image")
        self.assertEqual(record["box_id"], "sb_image")
        self.assertIn("ltcm/data/__init__.py", record["files"])
        create = [c for c in client.calls if c[0] == "create"][0][1]
        self.assertEqual(create["size"], "s")
        self.assertIn("pypi.org", create["egress"]["allowlist"])
        uploads = [c[2] for c in client.calls if c[0] == "upload"]
        self.assertIn("/lab/labkit.py", uploads)
        self.assertIn("/lab/floor/ltcm/data/__init__.py", uploads)
        self.assertIn(("checkpoint", "sb_image", "ltcm-lab-image"), client.calls)
        # Sail's default lifetime is seven days; the image every agent box starts from must outlive that.
        self.assertEqual(client.ttl_seconds, 365 * 86400)
        self.assertEqual(image.record()["expires_at"], "2027-09-22T00:00:00Z")
        self.assertIn(("sleep", "sb_image"), client.calls)
        self.assertEqual(image.record()["checkpoint_id"], "sbcp_image")
        self.assertTrue(any("labkit ok" in line for line in said))


if __name__ == "__main__":
    unittest.main()


class LeaseReleaseTests(unittest.TestCase):
    def test_foundry_leases_are_released_by_prefix_and_desk_leases_kept(self):
        import tempfile, time as _time
        from pathlib import Path
        from ltcm.sandbox import SandboxManager
        with tempfile.TemporaryDirectory() as tmp:
            manager = SandboxManager(None, Path(tmp) / "sandboxes.json", Path(tmp) / "toolbox", clock=lambda: 1000.0)
            state = manager.state()
            state["uncertain_until"] = {"foundry-0": 5000.0, "foundry-7": 5000.0, "mullins": 5000.0}
            manager._save(state)
            self.assertFalse(manager.ready_for_run("foundry-0"))
            self.assertEqual(manager.release_leases("foundry-"), 2)
            self.assertTrue(manager.ready_for_run("foundry-0"))
            self.assertFalse(manager.ready_for_run("mullins"), "a desk's own lease is kept")
            self.assertEqual(manager.release_leases("foundry-"), 0)
