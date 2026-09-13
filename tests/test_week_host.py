"""Offline cloud preparation must freeze seed identity without expanding pace."""
from contextlib import closing
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("week_host", SCRIPTS / "week_host.py")
week_host = importlib.util.module_from_spec(spec)
spec.loader.exec_module(week_host)


class PreparationTests(unittest.TestCase):
    def test_seed_transfer_does_not_replace_the_serializable_deployment_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "seed").mkdir()
            raw = b"checked seed fixture"
            (root / "seed/paper.sqlite").write_bytes(raw)
            (root / "run.json").write_text(json.dumps({"seed_dir": "/workspace/state/seed", "service_id": "week-test"}))
            (root / "seed.json").write_text(json.dumps({"source": str(root / "seed"), "files": {"paper.sqlite": {"sha256": week_host.sha(raw), "bytes": len(raw)}}}))
            receipt = {"installed": True, "manifest_sha256": "a" * 64}
            def execute(args, **kwargs):
                result = SimpleNamespace(exit_code=0, stdout=json.dumps({"sha256": args[-2], "bytes": int(args[-1]), "integrity": "ok"}))
                return SimpleNamespace(wait=lambda: result)
            box = SimpleNamespace(fs=SimpleNamespace(write=lambda *args, **kwargs: None), exec=execute)
            host = SimpleNamespace(provision=lambda *args, **kwargs: receipt,
                host=SimpleNamespace(attach=lambda: box, _read=lambda: {"started": False, "manifest_sha256": "a" * 64}))
            with patch.object(week_host, "clients", return_value=("test-key", {})), patch.object(week_host, "HostDeployment", return_value=host), patch.object(week_host, "private_read", return_value="test-token"):
                result = week_host.provision(root, "test-app")
            self.assertEqual(json.loads(json.dumps(result)), receipt)

    def test_large_ceiling_keeps_exploration_pace_and_checked_seed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            anchor = root / ".data/runtime/account-anchor.json"
            anchor.parent.mkdir(parents=True)
            anchor.write_text(json.dumps({"created_at": "2026-09-13T15:34:12Z"}))
            seed = root / "seed"
            seed.mkdir()
            for name in ("paper.sqlite", "research.sqlite", "requests.sqlite"):
                with closing(sqlite3.connect(seed / name)) as db, db:
                    db.execute("CREATE TABLE saved(id INTEGER PRIMARY KEY)")
            with patch.object(week_host, "ROOT", root), patch.object(week_host, "load_api_key", return_value="test-only-private-key"):
                config = week_host.prepare(root / "week", total="1000", starts="2026-09-14T04:00:00Z", ends="2026-09-19T04:00:00Z", seed=seed)
            self.assertEqual(config["session_inference_budget_usd"], "4.625")
            self.assertTrue(config["adaptive_spending"])
            self.assertEqual(config["weekly_inference_budget_usd"], "992.5")
            frozen = json.loads((root / "week/seed.json").read_text())
            self.assertEqual(len(frozen["files"]), 3)
            self.assertNotIn("test-only-private-key", (root / "week/run.json").read_text())
            self.assertEqual((root / "week/run.json").stat().st_mode & 0o077, 0)

    def test_invalid_window_is_rejected_before_private_credentials(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(week_host, "load_api_key") as key:
            for total, start, end in (("NaN", "bad", "bad"), ("1000", "2026-09-19T04:00:00Z", "2026-09-14T04:00:00Z")):
                with self.assertRaises(ValueError):
                    week_host.prepare(Path(directory) / "new", total=total, starts=start, ends=end, seed=directory)
            key.assert_not_called()


if __name__ == "__main__":
    unittest.main()
