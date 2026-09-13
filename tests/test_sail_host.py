"""No network: lifecycle transport/SDK are fakes; boot restart uses a temp guest."""

from datetime import timedelta
from contextlib import closing
import json
import sqlite3
import fcntl
import copy
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
import uuid

from portfolio_runtime import sail_host as h


def resource(prefix):
    return prefix + "_" + str(uuid.uuid4())


class Box:
    def __init__(self):
        self.files = {}
        self.commands = []
        self.fs = self
        self.running = False
        self.boot_id = str(uuid.uuid4())
        self.executions = {}
        self.current_exec = None

    def write(self, path, raw, **kwargs):
        self.files[path] = raw

    def read(self, path):
        return self.files[path]

    def exec(self, command, **kwargs):
        self.commands.append(command)
        if command == ["python3", "/workspace/host-probe.py"]:
            self.files["/workspace/host-status.json"] = json.dumps(
                {"running": self.running, "boot_id": self.boot_id}
            ).encode()
        if command == ["python3", "/workspace/host-stop.py"]:
            self.running = False
            if self.current_exec:
                self.executions[self.current_exec] = 0
        if command == "exec python3 /workspace/host-boot.py":
            key = kwargs["idempotency_key"]
            if key not in self.executions:
                self.executions[key] = None
                self.current_exec = key
                self.running = True
            return SimpleNamespace(
                exec_request_id=key, poll=lambda: self.executions[key]
            )
        return SimpleNamespace(wait=lambda: SimpleNamespace(exit_code=0))


class API:
    def __init__(self):
        self.calls = []
        self.rows = {}
        self.policies = {}
        self.boxes = {}
        self.fail_create = False
        self.checkpoints = {}

    def __call__(self, method, route, body=None, request_id=None):
        self.calls.append((method, route, body, request_id))
        if route == "/v1/sailboxes" and method == "POST":
            if self.fail_create:
                raise TimeoutError("uncertain")
            sid = resource("sb")
            self.boxes[sid] = Box()
            self.rows[sid] = {
                **body,
                "sailbox_id": sid,
                "status": "running",
                "vcpu_count": 1,
                "memory_mib": 2048,
                "state_disk_size_gib": body["state_disk_limit_gib"],
                "egress_policy": {"document": body["egress_policy"], "policy_id": None}
                if "egress_policy" in body
                else None,
                "http_policy": None,
            }
            return {"sailbox_id": sid}
        if route.startswith(("/v1/egress-policies/", "/v1/http-policies/")):
            return {"document": self.policies[route.rsplit("/", 1)[1]]}
        if route == "/v1/sailboxes/from_checkpoint":
            source = self.checkpoints[body["checkpoint_id"]]
            sid = resource("sb")
            self.rows[sid] = {
                **copy.deepcopy(self.rows[source]),
                "sailbox_id": sid,
                "name": body["name"],
                "http_policy": None,
            }
            self.boxes[sid] = Box()
            self.boxes[sid].files = copy.deepcopy(self.boxes[source].files)
            return {"sailbox_id": sid, "checkpoint_id": body["checkpoint_id"]}
        sid = route.split("/")[3]
        if route.endswith("/egress-policy"):
            pid = body["policy_id"]
            self.rows[sid]["egress_policy"] = {
                "document": self.policies[pid],
                "policy_id": pid,
            }
            return {}
        if route.endswith("/http-policy"):
            if method == "GET":
                if self.rows[sid]["http_policy"] is None:
                    error = RuntimeError("No policy attached")
                    error.status_code = 404
                    raise error
                return self.rows[sid]["http_policy"]
            pid = body["policy_id"]
            self.rows[sid]["http_policy"] = {"document": self.policies[pid], "id": pid}
            return {}
        if route.endswith("/checkpoint"):
            cp = resource("sbcp")
            self.checkpoints[cp] = sid
            return {
                "checkpoint_id": cp,
                "sailbox_id": sid,
                "expires_at": (h.now() + timedelta(days=1)).isoformat(),
            }
        if route.endswith("/sleep"):
            return {"sailbox_id": sid, "wake_at": body.get("wake_at")}
        return self.rows[sid]


class HostTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "portfolio_runtime").mkdir()
        (self.root / "data").mkdir()
        (self.root / "portfolio_runtime/runner.py").write_text('print("example")\n')
        (self.root / "data/evidence.json").write_text('{"source":"public"}')
        self.names = ["portfolio_runtime/runner.py", "data/evidence.json"]
        self.deadline = (h.now() + timedelta(hours=5)).isoformat()
        self.api = API()
        self.app = resource("app")
        self.host = h.SailHost(
            self.root / "local/control.json",
            api=self.api,
            box_factory=lambda sid: self.api.boxes[sid],
        )

    def tearDown(self):
        self.tmp.cleanup()

    def bundle(self, role="coordinator", config=None):
        return h.freeze_bundle(
            self.root,
            self.names,
            config or {"paper_only": True},
            role=role,
            deadline=self.deadline,
        )

    def ready(self):
        bundle = self.bundle()
        box = self.host.create(self.app, "paper-run", bundle)
        pid = resource("ep")
        doc = h.restricted_policy("sail_inference", publish_secret="site_publish")
        self.api.policies[pid] = doc
        self.host.bind_policy(pid, doc)
        self.host.install(bundle)
        return bundle, box

    def test_prepare_offline_and_reject_private_traversal_symlink_secret(self):
        self.bundle()
        self.assertEqual(self.api.calls, [])
        for name in [
            ".env",
            "../.env",
            ".data/portfolio.sqlite",
            "data/../.data/secret.json",
            "config/credentials.json",
            "/tmp/secret.json",
        ]:
            with (
                self.subTest(name=name),
                self.assertRaises((ValueError, FileNotFoundError)),
            ):
                h.freeze_bundle(self.root, [name], {}, deadline=self.deadline)
        (self.root / "data/link.json").symlink_to(self.root / "data/evidence.json")
        with self.assertRaises(ValueError):
            h.freeze_bundle(
                self.root, self.names + ["data/link.json"], {}, deadline=self.deadline
            )
        with self.assertRaises(ValueError):
            self.bundle(config={"nested": {"api_key": "never-upload"}})

    def test_manifest_bytes_cannot_change(self):
        bundle = self.bundle()
        bundle["files"]["data/evidence.json"] = b"{}"
        with self.assertRaises(ValueError):
            self.host.create(self.app, "paper-run", bundle)
        self.assertEqual(self.api.calls, [])

    def test_one_create_attach_coldstart_and_frozen_upload(self):
        bundle, box = self.ready()
        sid = self.host._read()["sailbox_id"]
        self.assertEqual(
            box.read("/workspace/data/evidence.json"),
            bundle["files"]["data/evidence.json"],
        )
        self.host.start()
        self.host.attach()
        self.host.start()
        creates = [c for c in self.api.calls if c[:2] == ("POST", "/v1/sailboxes")]
        self.assertEqual(len(creates), 1)
        self.assertFalse(any("systemd" in name for name in box.files))
        self.assertIn("/workspace/host-probe.py", box.files)
        self.assertEqual(len(self.host._read()["executions"]), 1)
        self.assertTrue(self.host._read()["executions"][0]["confirmed"])
        authority = json.loads(box.read("/workspace/host-authority.json"))
        self.assertEqual(authority["sailbox_id"], sid)
        with self.assertRaises(ValueError):
            self.host.install(bundle)

    def test_unconfirmed_create_cannot_allocate_twice(self):
        self.api.fail_create = True
        with self.assertRaises(TimeoutError):
            self.host.create(self.app, "paper-run", self.bundle())
        saved = self.host._read()
        with self.assertRaises(RuntimeError):
            self.host.create(self.app, "paper-run", self.bundle())
        self.assertEqual(len(self.api.calls), 1)
        self.assertEqual(self.host._read()["create_key"], saved["create_key"])

    def test_readback_wrong_identity_policy_resource_fails_before_upload(self):
        bundle = self.bundle()
        self.host.create(self.app, "paper-run", bundle)
        sid = self.host._read()["sailbox_id"]
        self.api.rows[sid]["volume_mounts"] = [{"volume_id": "parent-ledger"}]
        with self.assertRaises(ValueError):
            self.host.install(bundle)
        self.assertEqual(self.api.boxes[sid].files, {})

    def test_weekday_disk_is_frozen_and_exact_readback_is_required(self):
        bundle = self.bundle(config={"kind": "weekday_service", "paper_only": True})
        self.host.create(self.app, "week-service", bundle)
        self.host.create(self.app, "week-service", bundle)
        saved = self.host._read()
        self.assertEqual(saved["create_body"]["state_disk_limit_gib"], 32)
        creates = [c for c in self.api.calls if c[:2] == ("POST", "/v1/sailboxes")]
        self.assertEqual(len(creates), 1)
        with self.assertRaisesRegex(ValueError, "frozen inputs"):
            self.host.create(self.app, "week-service", self.bundle())
        for changed_disk in (8, 64):
            self.api.rows[saved["sailbox_id"]]["state_disk_size_gib"] = changed_disk
            with self.subTest(disk=changed_disk), self.assertRaisesRegex(ValueError, "resource isolation"):
                self.host.attach()
        self.assertEqual(self.api.boxes[saved["sailbox_id"]].files, {})

    def test_oneoff_disk_stays_small_and_weekday_cannot_be_a_branch(self):
        bundle = self.bundle()
        self.host.create(self.app, "oneoff", bundle)
        self.assertEqual(self.host._read()["create_body"]["state_disk_limit_gib"], 8)
        branch = self.bundle(role="research_branch", config={"kind": "weekday_service"})
        with self.assertRaisesRegex(ValueError, "coordinator disk"):
            h.bundle_disk_limit_gib(branch)

    def test_policy_is_route_scoped_and_rejects_broad_or_branch_publish(self):
        doc = h.restricted_policy("sail_inference", publish_secret="site_publish")
        rules = doc["rules"]["api.sailresearch.com"]
        self.assertEqual(rules[0]["match"], {"method": "POST", "path": "/v1/responses"})
        self.assertEqual(rules[-1]["respond"]["status"], 403)
        self.assertNotIn("site_publish", json.dumps(rules))
        h._validate_policy(doc, "coordinator", resource("sb"))
        with self.assertRaises(ValueError):
            h._validate_policy(doc, "research_branch", resource("sb"))
        rules[0]["match"]["path"] = {"prefix": "/v1/"}
        with self.assertRaises(ValueError):
            h._validate_policy(doc, "coordinator", resource("sb"))

    def test_weekday_guest_has_only_source_reads_publication_and_write_only_backups(self):
        own = resource("sb")
        backup = "portfolio-supervisor.example.workers.dev"
        doc = h.restricted_policy(
            "inference", publish_secret="public_journal", journal=True,
            sec_sources=True, daily_sources=True, backup_host=backup,
            backup_secret="backup_upload", own_box_id=own,
        )
        h._validate_policy(doc, "coordinator", own)

        def route(host, method, path):
            if host not in doc["allowlist"]:
                return False, None
            for rule in doc["rules"][host]:
                if "respond" in rule:
                    return False, None
                match = rule["match"]
                methods = match["method"] if isinstance(match["method"], list) else [match["method"]]
                wanted = match["path"]
                if method in methods and (path.startswith(wanted["prefix"]) if isinstance(wanted, dict) else path == wanted):
                    return True, rule.get("request", {}).get("set", {}).get("headers", {}).get("authorization")
            return False, None

        for host, path in [
            ("data.sec.gov", "/api/xbrl/companyfacts/CIK0001234567.json"),
            ("data.sec.gov", "/submissions/CIK0001234567.json"),
            ("www.sec.gov", "/Archives/edgar/data/1234567/filing.htm"),
            ("query1.finance.yahoo.com", "/v8/finance/chart/NVDA"),
            ("en.wikipedia.org", "/wiki/List_of_S%26P_500_companies"),
            ("en.wikipedia.org", "/wiki/List_of_S&P_500_companies"),
        ]:
            self.assertEqual(route(host, "GET", path), (True, None))
            self.assertFalse(route(host, "POST", path)[0])
        self.assertEqual(route("blakewoods.us", "POST", "/api/portfolio/research"), (True, "Bearer ${secrets.public_journal}"))
        self.assertEqual(route(backup, "PUT", "/v1/backups/private-object"), (True, "Bearer ${secrets.backup_upload}"))
        for host, method, path in [
            (backup, "GET", "/v1/backups/private-object"),
            (backup, "POST", "/v1/pause"),
            ("blakewoods.us", "GET", "/api/portfolio/notifications"),
            ("blakewoods.us", "POST", "/api/portfolio/research/unreviewed"),
            ("api.sailresearch.com", "GET", "/v2/usage/summary"),
            ("sailbox-api.sailresearch.com", "POST", "/v1/sailboxes"),
            ("api.schwabapi.com", "POST", "/trader/v1/accounts/private/orders"),
        ]:
            self.assertFalse(route(host, method, path)[0], (host, method, path))
        self.assertTrue(route("sailbox-api.sailresearch.com", "POST", f"/v1/sailboxes/{own}/sleep")[0])
        with self.assertRaises(ValueError):
            h._validate_policy(doc, "research_branch", own)
        broadened = copy.deepcopy(doc)
        broadened["rules"][backup][0]["match"]["method"] = ["PUT", "GET"]
        with self.assertRaises(ValueError):
            h._validate_policy(broadened, "coordinator", own)

    def test_checkpoint_only_sterile_seed_without_service_or_state(self):
        bundle = self.bundle("research_seed")
        box = self.host.create(self.app, "seed", bundle)
        self.host.install(bundle)
        self.assertNotIn("/workspace/host-authority.json", box.files)
        self.assertFalse(any("systemd" in k for k in box.files))
        cp = self.host.checkpoint_seed()
        self.assertEqual(self.host.checkpoint_seed(), cp)
        self.assertEqual(
            len([x for x in self.api.calls if x[1].endswith("/checkpoint")]), 1
        )
        with self.assertRaises(ValueError):
            self.host.start()

    def test_fork_has_new_task_config_without_parent_authority_or_ledger(self):
        seed_bundle = self.bundle("research_seed")
        seed_box = self.host.create(self.app, "seed", seed_bundle)
        self.host.install(seed_bundle)
        config = {
            "research_only": True,
            "assigned_task_ids": ["frozen-task-one"],
            "inference_budget_usd": "0.50",
        }
        child_bundle = self.bundle("research_branch", config)
        child = h.SailHost(
            self.root / "local/branch.json",
            api=self.api,
            box_factory=lambda sid: self.api.boxes[sid],
        )
        child_box = child.fork_research(self.host, child_bundle, "branch-one")
        child.fork_research(self.host, child_bundle, "branch-one")
        self.assertEqual(
            len([x for x in self.api.calls if x[1] == "/v1/sailboxes/from_checkpoint"]),
            1,
        )
        pid = resource("ep")
        doc = h.restricted_policy("sail_inference")
        self.api.policies[pid] = doc
        child.bind_policy(pid, doc)
        child.install(child_bundle)
        child.start()
        self.assertEqual(
            json.loads(child_box.files["/workspace/config/run.json"]), config
        )
        self.assertNotIn("/workspace/host-authority.json", seed_box.files)
        self.assertNotIn("/workspace/state", child_box.files)
        self.assertEqual(self.host._read()["policy"], {"no_network": True})
        self.assertEqual(child._read()["role"], "research_branch")

    def test_http_fork_rebinds_credentials_after_checkpoint_without_inheriting_them(
        self,
    ):
        doc = h.restricted_policy("sail_inference")
        seed = h.SailHost(
            self.root / "local/http-seed.json",
            api=self.api,
            box_factory=lambda sid: self.api.boxes[sid],
            policy_contract="http",
            allowed_hosts=tuple(doc["allowlist"]),
        )
        seed_bundle = self.bundle("research_seed")
        seed.create(self.app, "http-seed", seed_bundle)
        pid = resource("hp")
        self.api.policies[pid] = h.http_document(doc)
        seed.bind_policy(pid, doc)
        seed.install(seed_bundle)
        child = h.SailHost(
            self.root / "local/http-branch.json",
            api=self.api,
            box_factory=lambda sid: self.api.boxes[sid],
            policy_contract="http",
        )
        config = {
            "research_only": True,
            "assigned_task_ids": ["fixed-task"],
            "inference_budget_usd": "2",
        }
        bundle = self.bundle("research_branch", config)
        child.fork_research(seed, bundle, "http-child")
        child.fork_research(seed, bundle, "http-child")
        self.assertIsNone(child._read()["policy_id"])
        self.assertIsNone(child._read()["policy"])
        self.assertEqual(
            child._read()["create_body"]["network_policy"],
            seed._read()["create_body"]["network_policy"],
        )
        with self.assertRaises(ValueError):
            child.start()
        child.bind_policy(pid, doc)
        child.install(bundle)
        child.start()
        self.assertEqual(child._read()["policy_id"], pid)
        self.assertEqual(seed._read()["policy_id"], pid)
        self.assertEqual(
            len([c for c in self.api.calls if c[1] == "/v1/sailboxes/from_checkpoint"]),
            1,
        )

    def test_legacy_http_policy_preserves_exact_hosts_and_request_rules(self):
        doc = h.restricted_policy(
            "sail_inference", publish_secret="site_publish", sec_sources=True
        )
        host = h.SailHost(
            self.root / "local/legacy.json",
            api=self.api,
            box_factory=lambda sid: self.api.boxes[sid],
            policy_contract="http",
            allowed_hosts=tuple(doc["allowlist"]),
        )
        bundle = self.bundle()
        host.create(self.app, "legacy-host", bundle)
        pid = resource("hp")
        self.api.policies[pid] = h.http_document(doc)
        host.bind_policy(pid, doc)
        host.install(bundle)
        host.start()
        state = host._read()
        sid = state["sailbox_id"]
        self.assertEqual(
            state["create_body"]["network_policy"],
            {"mode": "allowlist", "allowed_hosts": doc["allowlist"]},
        )
        for name in ("data.sec.gov", "www.sec.gov"):
            self.assertNotIn("request", doc["rules"][name][0])
            self.assertEqual(doc["rules"][name][0]["match"]["method"], "GET")
        self.api.rows[sid]["network_policy"]["allowed_hosts"].append("evil.example")
        with self.assertRaises(ValueError):
            host.attach()

    def test_managed_exec_restart_reuses_state_and_changes_identity_only_after_confirmed_exit(
        self,
    ):
        _, box = self.ready()
        self.host.start()
        first = self.host._read()["executions"][0]["id"]
        self.host.start()
        self.assertEqual(len(self.host._read()["executions"]), 1)
        box.running = False
        box.executions[first] = 1
        self.host.start()
        self.assertEqual(len(self.host._read()["executions"]), 2)
        self.assertNotEqual(self.host._read()["executions"][1]["id"], first)
        box.running = False
        box.boot_id = str(uuid.uuid4())
        self.host.start()
        self.assertEqual(len(self.host._read()["executions"]), 3)
        self.assertEqual(
            len([c for c in self.api.calls if c[:2] == ("POST", "/v1/sailboxes")]), 1
        )

    def test_large_sqlite_backup_streams_compressed_and_preserves_voyage(self):
        _, box = self.ready()
        guest = self.root / "backup-guest"
        (guest / "state").mkdir(parents=True)
        source = guest / "state/requests.sqlite"
        with closing(sqlite3.connect(source)) as db, db:
            db.execute("CREATE TABLE records (body TEXT)")
            for _ in range(66):
                db.execute(
                    "INSERT INTO records VALUES(?)", ("repeated-evidence-" * 65536,)
                )
        with closing(sqlite3.connect(guest / "state/voyage.sqlite")) as db, db:
            db.execute("CREATE TABLE trace (sequence INTEGER)")
            db.execute("INSERT INTO trace VALUES(7)")
        self.assertGreater(source.stat().st_size, 64_000_000)

        def execute(command, **kwargs):
            actual = [
                sys.executable,
                "-c",
                command[2].replace("/workspace", str(guest)),
            ]
            result = subprocess.run(actual, capture_output=True)
            return SimpleNamespace(
                wait=lambda: SimpleNamespace(exit_code=result.returncode)
            )

        box.exec = execute
        box.read = lambda path: Path(
            path.replace("/workspace", str(guest))
        ).read_bytes()
        receipt = self.host.backup_state(self.root / "backup")
        self.assertEqual(set(receipt["files"]), {"requests.sqlite", "voyage.sqlite"})
        self.assertGreater(receipt["files"]["requests.sqlite"]["bytes"], 64_000_000)
        self.assertLess(
            receipt["files"]["requests.sqlite"]["compressed_bytes"], 1_000_000
        )
        self.assertFalse(receipt["raw_filings_included"])
        with closing(sqlite3.connect(self.root / "backup/requests.sqlite")) as db:
            self.assertEqual(
                db.execute("SELECT COUNT(*) FROM records").fetchone()[0], 66
            )
        with closing(sqlite3.connect(self.root / "backup/voyage.sqlite")) as db:
            self.assertEqual(db.execute("SELECT sequence FROM trace").fetchone()[0], 7)
        self.assertEqual(
            (self.root / "backup/requests.sqlite").stat().st_mode & 0o077, 0
        )

    def test_live_coordinator_can_never_fork(self):
        self.ready()
        with self.assertRaises(ValueError):
            self.host.checkpoint_seed()

    def test_wake_bounds_and_stop_latch(self):
        _, box = self.ready()
        self.host.start()
        self.host.sleep_until((h.now() + timedelta(minutes=10)).isoformat())
        with self.assertRaises(ValueError):
            self.host.sleep_until((h.now() + timedelta(days=1)).isoformat())
        self.host.stop()
        self.assertEqual(box.files["/workspace/host-paused"], b"paused\n")

    def test_branch_must_have_explicit_research_only_allocation(self):
        with self.assertRaises(ValueError):
            self.host.fork_research(
                self.host, self.bundle("research_branch"), "bad-branch"
            )
        self.assertEqual(self.api.calls, [])

    def test_real_boot_reopens_same_state_and_blocks_mutated_or_expired_bundle(self):
        guest = self.root / "guest"
        guest.mkdir()
        runtime = guest / "portfolio_runtime"
        runtime.mkdir()
        (runtime / "__init__.py").write_text("")
        text = "from pathlib import Path\np=Path('state/proof.txt');p.write_text(p.read_text()+'R' if p.exists() else 'R')\n"
        (runtime / "runner.py").write_text(text)
        config = b"{}"
        (guest / "config").mkdir()
        (guest / "config/run.json").write_bytes(config)
        files = {
            "portfolio_runtime/runner.py": text.encode(),
            "config/run.json": config,
        }
        manifest = {
            "schema_version": 1,
            "role": "coordinator",
            "deadline": self.deadline,
            "files": {
                k: {"sha256": h.sha(v), "bytes": len(v)} for k, v in files.items()
            },
        }
        (guest / "host-manifest.json").write_bytes(h.encoded(manifest))
        authority = {
            "role": "coordinator",
            "manifest_sha256": h.sha(h.encoded(manifest)),
        }
        (guest / "host-authority.json").write_bytes(h.encoded(authority))
        boot = guest / "host-boot.py"
        boot.write_text(h.BOOT.replace("/workspace", str(guest)))
        for _ in range(2):
            result = subprocess.run([sys.executable, str(boot)], capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((guest / "state/proof.txt").read_text(), "RR")
        with (guest / "state/coordinator.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.assertEqual(
                subprocess.run(
                    [sys.executable, str(boot)], capture_output=True
                ).returncode,
                0,
            )
        self.assertEqual((guest / "state/proof.txt").read_text(), "RR")
        (guest / "host-paused").write_text("paused")
        self.assertEqual(
            subprocess.run([sys.executable, str(boot)], capture_output=True).returncode,
            0,
        )
        self.assertEqual((guest / "state/proof.txt").read_text(), "RR")
        (guest / "host-paused").unlink()
        (runtime / "runner.py").write_text('print("changed")')
        self.assertEqual(
            subprocess.run([sys.executable, str(boot)], capture_output=True).returncode,
            78,
        )
        self.assertEqual((guest / "state/proof.txt").read_text(), "RR")


if __name__ == "__main__":
    unittest.main()
