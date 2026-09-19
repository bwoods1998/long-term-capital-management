"""The daily checkpoint of the House box: the league's memory must outlive one disk."""

import tempfile
import unittest
from pathlib import Path

from league.backup import Backup
from league.ledger import Ledger
from league.tests.fakes import Clock


class FakeSail:
    def __init__(self, boxes):
        self.boxes, self.made, self.fail = boxes, [], None

    def list_boxes(self, *, limit=100):
        return self.boxes

    def checkpoint(self, box, *, name=None, ttl_seconds=None):
        if self.fail:
            raise self.fail
        self.made.append((box, name, ttl_seconds))
        return {"checkpoint_id": "sbcp_1", "sailbox_id": box}


class BackupTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.clock = Clock()
        self.ledger = Ledger(Path(self.dir.name) / "l.sqlite", clock=self.clock)
        self.sail = FakeSail([{"name": "ltcm-floor", "status": "running", "sailbox_id": "sb_house"}, {"name": "league-x", "status": "sleeping", "sailbox_id": "sb_agent"}])
        self.backup = Backup(self.sail, self.ledger, clock=self.clock)

    def tearDown(self):
        self.ledger.close()
        self.dir.cleanup()

    def test_the_house_box_is_checkpointed_once_a_day_under_a_dated_name_kept_a_week(self):
        self.assertTrue(self.backup.due())
        row = self.backup.run()
        self.assertEqual((row["ok"], row["name"], row["checkpoint_id"]), (True, "league-2026-09-10", "sbcp_1"))
        self.assertEqual(self.sail.made, [("sb_house", "league-2026-09-10", 7 * 86400)])
        self.assertFalse(self.backup.due())
        self.clock.advance(23 * 3600)
        self.assertFalse(self.backup.due())
        self.clock.advance(2 * 3600)
        self.assertTrue(self.backup.due())

    def test_a_failed_backup_is_recorded_is_not_a_crash_and_is_tried_again(self):
        self.sail.fail = RuntimeError("sail is down")
        row = self.backup.run()
        self.assertEqual((row["ok"], row["error"]), (False, "RuntimeError: sail is down"))
        self.assertTrue(self.backup.due())

    def test_it_never_guesses_which_box_is_the_house(self):
        self.sail.boxes = [{"name": "ltcm-floor", "status": "running", "sailbox_id": "a"}, {"name": "ltcm-floor", "status": "running", "sailbox_id": "b"}]
        self.assertIn("2 running boxes", self.backup.run()["error"])
        self.assertEqual(self.sail.made, [])

    def test_the_record_is_private(self):
        self.backup.run()
        entry = self.ledger.last("ops.deploy")
        self.assertFalse(entry.public)


if __name__ == "__main__":
    unittest.main()
