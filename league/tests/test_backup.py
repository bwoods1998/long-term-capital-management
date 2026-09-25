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

    def test_a_failed_backup_is_recorded_is_not_a_crash_and_is_tried_again_after_a_backoff(self):
        """Sept 24, 2026: Sail's checkpoint service answered 503 for a quarter of an hour and the House tried at every
        tick, an error alert each time. A failure now waits 30 minutes, doubling with each failure in a row, capped at
        six hours; a success resets it."""
        self.sail.fail = RuntimeError("sail is down")
        row = self.backup.run()
        self.assertEqual((row["ok"], row["error"]), (False, "RuntimeError: sail is down"))
        self.assertFalse(self.backup.due())
        self.clock.advance(29 * 60)
        self.assertFalse(self.backup.due())
        self.clock.advance(60)
        self.assertTrue(self.backup.due())
        self.backup.run()  # the second failure in a row: an hour
        self.clock.advance(59 * 60)
        self.assertFalse(self.backup.due())
        self.clock.advance(60)
        self.assertTrue(self.backup.due())
        for _ in range(6):
            self.backup.run()
        self.assertEqual(len(self.backup.failures_in_a_row()), 8)
        self.assertEqual(self.backup.retry_after(8), 6 * 3600)  # capped
        self.clock.advance(6 * 3600)
        self.assertTrue(self.backup.due())
        self.sail.fail = None
        self.assertTrue(self.backup.run()["ok"])
        self.assertEqual(self.backup.failures_in_a_row(), [])
        self.assertFalse(self.backup.due())  # the next is a day on

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


class TheHousesAlert(unittest.TestCase):
    """The House's alert for a failed backup carries when the run of failures began (`began_at`), so the watchdog
    inherits a Sail outage that began before a promotion instead of rolling the release back for it (Sept 24, 2026)."""

    def test_the_alert_says_when_the_outage_began_and_the_watch_inherits_it(self):
        from league.tests.test_house import HouseCase
        from league.watchdog import read_health

        class Case(HouseCase):
            def runTest(self):
                pass

        case = Case()
        case.setUp()
        try:
            house, clock = case.house, case.clock
            sail = FakeSail([{"name": "ltcm-floor", "status": "running", "sailbox_id": "sb_house"}])
            sail.fail = RuntimeError("sailbox api 503: prepare checkpoint warm snapshot")
            house.backup = Backup(sail, house.ledger, clock=clock)
            house._run_backup()
            first = house.ledger.last("ops.alert").payload
            self.assertEqual((first["level"], first["failures"]), ("error", 1))
            began = first["began_at"]
            clock.advance(1801)
            promoted = clock()  # a release is promoted during the outage
            since = house.ledger.head()[0]
            clock.advance(60)
            house._run_backup()  # the second failure in a row, after the promotion
            second = house.ledger.last("ops.alert").payload
            self.assertEqual((second["began_at"], second["failures"]), (began, 2))
            self.assertIn("the next in 60 minutes", second["text"])
            house.tick()  # a fresh health.json for the watch to read
            watched = read_health(house.root, now=clock(), since_seq=since, inherited_before=promoted, stall_seconds=0)
            self.assertEqual(watched.detail.get("error_alerts"), 0, watched.reasons)
            self.assertGreaterEqual(watched.detail.get("inherited_alerts", 0), 1)
            fresh = read_health(house.root, now=clock(), since_seq=since, inherited_before=promoted - 3600, stall_seconds=0)
            self.assertFalse(fresh.ok)  # an outage that began after the promotion is the release's to answer for
        finally:
            case.tearDown()
