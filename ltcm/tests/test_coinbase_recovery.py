"""Owner exit-only recovery is stopped-process-only, narrow and idempotent."""
import json
import tempfile
import unittest
from pathlib import Path

from scripts.recover_coinbase_exits import recover


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.path = self.root / ".data/ltcm/strategies.json"
        self.path.parent.mkdir(parents=True)
        self.data = {"schema_version": 1, "desks": {
            desk: {"spot_quotes": {"house": True, "enabled": False, "note": "paused Sept 17: fee failure", "params": {"spread": 0.01}},
                   "hourly_reversion": {"house": True, "enabled": False}}
            for desk in ("hilibrand", "hilibrand-3")}}
        self.data["desks"]["mullins"] = {"kalshi_favorites": {"enabled": True}}
        self.path.write_text(json.dumps(self.data))

    def test_dry_run_and_running_floor_never_change_state(self):
        before = self.path.read_bytes()
        self.assertEqual(recover(self.root)["changed"], ["hilibrand", "hilibrand-3"])
        with self.assertRaisesRegex(RuntimeError, "stop the supervised"):
            recover(self.root, apply=True)
        self.assertEqual(self.path.read_bytes(), before)

    def test_only_audited_rows_change_once_with_backup_and_bids_off(self):
        (self.root / "STOP").touch()
        before = self.path.read_bytes()
        result = recover(self.root, apply=True)
        self.assertEqual(Path(result["backup"]).read_bytes(), before)
        desks = json.loads(self.path.read_text())["desks"]
        self.assertEqual(desks["mullins"], self.data["desks"]["mullins"])
        for desk in ("hilibrand", "hilibrand-3"):
            self.assertTrue(desks[desk]["spot_quotes"]["enabled"])
            self.assertFalse(desks[desk]["spot_quotes"]["params"]["bid"])
            self.assertFalse(desks[desk]["hourly_reversion"]["enabled"])
        self.assertEqual(recover(self.root, apply=True)["changed"], [])

    def test_changed_owner_row_aborts_the_whole_migration(self):
        self.data["desks"]["hilibrand-3"]["spot_quotes"]["enabled"] = True
        self.path.write_text(json.dumps(self.data))
        before = self.path.read_bytes()
        (self.root / "STOP").touch()
        with self.assertRaises(ValueError):
            recover(self.root, apply=True)
        self.assertEqual(self.path.read_bytes(), before)
