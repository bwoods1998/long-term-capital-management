"""Offline checks for host identities, private bundles and external recovery."""

from datetime import timedelta
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import host_runtime as cli
from portfolio_runtime.sail_host import freeze_bundle, now


class HostCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.calls = []
        self.deployment = cli.HostDeployment(
            self.root / "host",
            api=lambda *args: self.calls.append(args),
            box_factory=lambda sid: None,
            secret_set=lambda *args: self.calls.append(args),
            inference_api=lambda *args: self.calls.append(args),
        )
        self.config = {
            "schema_version": 1,
            "key_fingerprint": hashlib.sha256(b"test-only").hexdigest(),
            "ends_epoch": 2000,
            "branch_allocations": [{"id": "test", "budget_usd": "2"}],
        }

    def tearDown(self):
        self.tmp.cleanup()

    def test_guest_config_removes_private_path_and_fixes_authority(self):
        local = {
            **self.config,
            "publish_token_path": "/private/secret",
            "state_dir": "/private/journals",
            "evidence_path": "/private/evidence",
            "voyage_id": "old",
            "fetch_filings": True,
        }
        guest = cli.guest_config(local, voyage_id="voy_saved")
        self.assertNotIn("publish_token_path", guest)
        self.assertEqual(guest["state_dir"], "/workspace/state")
        self.assertEqual(guest["evidence_path"], "/workspace/data/sp500-evidence.json")
        self.assertTrue(guest["injected_auth"])
        self.assertEqual(guest["voyage_id"], "voy_saved")
        self.assertEqual(guest["branch_allocations"], self.config["branch_allocations"])
        with self.assertRaises(ValueError):
            cli.guest_config({**local, "api_key": "test-only"})
        self.assertEqual(self.calls, [])

    def test_intent_is_durable_before_io_and_rejects_changed_contract(self):
        state = self.deployment.intent(self.config, "app_example")
        self.assertEqual(self.deployment.read(), state)
        self.assertEqual(
            self.deployment.intent(self.config, "app_example")["identity"],
            state["identity"],
        )
        with self.assertRaises(ValueError):
            self.deployment.intent({**self.config, "ends_epoch": 2001}, "app_example")
        self.assertEqual(self.calls, [])

    def test_voyage_ambiguous_create_never_reissues_post(self):
        state = self.deployment.intent(self.config, "app_example")

        def transport(*args):
            self.assertTrue(self.deployment.read()["voyage_attempted"])
            self.calls.append(args)
            raise TimeoutError("unconfirmed")

        self.deployment.inference_api = transport
        with self.assertRaises(TimeoutError):
            self.deployment.ensure_voyage(state)
        with self.assertRaises(RuntimeError):
            self.deployment.ensure_voyage(self.deployment.read())
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.calls[0][3], state["voyage_create_key"])

    def test_voyage_saved_id_reused_and_verified(self):
        state = self.deployment.intent(self.config, "app_example")
        identity = "voy_12345678"

        def transport(method, route, *args):
            self.calls.append((method, route))
            return {"id": identity}

        self.deployment.inference_api = transport
        self.assertEqual(self.deployment.ensure_voyage(state), identity)
        self.assertEqual(
            self.deployment.ensure_voyage(self.deployment.read()), identity
        )
        self.assertEqual([v[0] for v in self.calls], ["POST", "GET"])

    def test_bundle_readback_rejects_replacement(self):
        (self.root / "portfolio_runtime").mkdir()
        source = self.root / "portfolio_runtime/runner.py"
        source.write_text("pass\n")
        deadline = (now() + timedelta(hours=1)).isoformat()
        bundle = freeze_bundle(
            self.root, ["portfolio_runtime/runner.py"], {}, deadline=deadline
        )
        target = self.root / "frozen"
        cli.save_bundle(target, bundle)
        self.assertEqual(cli.load_bundle(target)["sha256"], bundle["sha256"])
        source.write_text("raise RuntimeError()\n")
        changed = freeze_bundle(
            self.root, ["portfolio_runtime/runner.py"], {}, deadline=deadline
        )
        with self.assertRaises(ValueError):
            cli.save_bundle(target, changed)
        (target / "portfolio_runtime/runner.py").write_text("changed")
        with self.assertRaises(ValueError):
            cli.load_bundle(target)

    def test_watchdog_recovers_missing_progress_then_backs_up_and_sleeps(self):
        calls = []
        clock = [1000]

        class Host:
            def _read(self):
                return {
                    "deadline": "1970-01-01T00:23:40+00:00",
                    "sailbox_id": "sb_example",
                }

            def attach(self):
                def read(path):
                    raise FileNotFoundError(path)

                return SimpleNamespace(fs=SimpleNamespace(read=read))

            def _probe(self, box):
                return {"running": False}

            def start(self):
                calls.append("start")
                return {"started_new_process": len(calls) == 1}

            def stop(self, **kwargs):
                calls.append("stop")

            def backup_state(self, path):
                calls.append("backup")

        self.deployment.host = Host()
        self.deployment.status = lambda: {"status": "running"}
        self.deployment.backup = lambda path: calls.append("backup")
        self.deployment.api = lambda *args: calls.append("sleep")
        with (
            patch.object(cli.time, "time", side_effect=lambda: clock[0]),
            patch.object(
                cli.time,
                "sleep",
                side_effect=lambda seconds: clock.__setitem__(0, clock[0] + seconds),
            ),
        ):
            self.assertTrue(self.deployment.monitor()["finished"])
        self.assertEqual(calls[-3:], ["stop", "backup", "sleep"])
        self.assertGreaterEqual(calls.count("stop"), 2)
        self.assertEqual(
            json.loads((self.root / "host/observed/watchdog.json").read_text())[
                "phase"
            ],
            "finished",
        )

    def test_deadline_always_sleeps_box_if_backup_fails(self):
        calls = []
        self.deployment.host = SimpleNamespace(
            _read=lambda: {
                "deadline": "1970-01-01T00:00:01+00:00",
                "sailbox_id": "sb_example",
            },
            attach=lambda: None,
            _probe=lambda box: {"running": False},
            stop=lambda **kwargs: calls.append("stop"),
            backup_state=lambda path: (_ for _ in ()).throw(
                RuntimeError("backup failed")
            ),
        )
        self.deployment.api = lambda *args: calls.append("sleep")
        self.deployment.backup = lambda path: (_ for _ in ()).throw(
            RuntimeError("backup failed")
        )
        with self.assertRaises(RuntimeError):
            self.deployment.monitor()
        self.assertEqual(calls, ["stop", "sleep"])

    def test_private_reader_rejects_public_and_symlink_secret(self):
        path = self.root / "key"
        path.write_text("private-example")
        path.chmod(0o644)
        with self.assertRaises(ValueError):
            cli.private_read(path)
        path.chmod(0o600)
        self.assertEqual(cli.private_read(path), "private-example")
        link = self.root / "link"
        link.symlink_to(path)
        with self.assertRaises(ValueError):
            cli.private_read(link)


if __name__ == "__main__":
    unittest.main()
