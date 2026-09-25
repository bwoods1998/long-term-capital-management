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


# ------------------------------------------------------------------------ H2, Sept 25, 2026
def sail_503():
    from ltcm.sailbox import SailboxError

    return SailboxError("sailbox api 503: prepare checkpoint warm snapshot: rpc error: code = DeadlineExceeded", status=503)


class TheOutageIsOneErrorThenWarnings(unittest.TestCase):
    """Sept 24-25, 2026: Sail's checkpoint API answered 503 from 21:31:55Z to 01:55Z; 73 failed backups were 73 error
    alerts, and six releases were rolled back on them. `Backup.notice`: a Sail outage is ONE error alert when it
    begins, a warning at each later backoff step and an info with its length when it ends, every one marked
    `environment: "sail"`; the House's own failure is an unmarked error every time."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.clock = Clock()
        self.ledger = Ledger(Path(self.dir.name) / "l.sqlite", clock=self.clock)
        self.sail = FakeSail([{"name": "ltcm-floor", "status": "running", "sailbox_id": "sb_house"}])
        self.backup = Backup(self.sail, self.ledger, clock=self.clock)

    def tearDown(self):
        self.ledger.close()
        self.dir.cleanup()

    def attempt(self, **kw):
        before = self.backup.failures_in_a_row()
        return self.backup.notice(self.backup.run(**kw), before)

    def test_a_sail_outage_is_one_error_then_a_warning_a_step_then_an_info_with_its_length(self):
        self.assertIsNone(self.attempt())  # a routine success says nothing
        self.clock.advance(86400)
        self.sail.fail = sail_503()
        began = self.clock()
        level, text, payload = self.attempt()
        self.assertEqual((level, payload["environment"], payload["failures"]), ("error", "sail", 1))
        self.assertIn("failed on Sail's side (SailboxError: sailbox api 503", text)
        self.assertEqual(self.ledger.last("ops.deploy").payload["environment"], "sail")
        said = []
        for wait in (1800, 3600, 7200):
            self.clock.advance(wait)
            said.append(self.attempt())
        self.assertEqual([(lvl, p["environment"], p["failures"], p["began_at"]) for lvl, _, p in said],
                         [("warning", "sail", n, said[0][2]["began_at"]) for n in (2, 3, 4)])
        self.assertIn("Sail still fails the daily backup of the House box", said[-1][1])
        self.assertIn("the next in 240 minutes", said[-1][1])
        self.clock.advance(4 * 3600)
        self.sail.fail = None
        level, text, payload = self.attempt()
        self.assertEqual((level, payload["environment"], payload["failures"]), ("info", "sail", 4))
        self.assertEqual(payload["outage_seconds"], self.clock() - began)
        self.assertIn("succeeded again: the outage lasted 7 h 30 min (4 failed tries since", text)

    def test_the_houses_own_failure_is_an_unmarked_error_every_time(self):
        self.sail.fail = TypeError("checkpoint() got an unexpected keyword argument 'ttl'")
        first = self.attempt()
        self.clock.advance(1800)
        second = self.attempt()
        self.assertEqual([(lvl, "environment" in p, p["failures"]) for lvl, _, p in (first, second)], [("error", False, 1), ("error", False, 2)])
        self.assertEqual(second[2]["began_at"], first[2]["began_at"])
        self.assertNotIn("environment", self.ledger.last("ops.deploy").payload)
        # A release that breaks the backup during a Sail outage: its failures begin when they begin, not with the outage.
        self.clock.advance(3600)
        self.sail.fail = sail_503()
        self.assertEqual(self.attempt()[0], "warning")
        self.clock.advance(7200)
        self.sail.fail = KeyError("sailbox_id")
        level, _, payload = self.attempt()
        self.assertEqual((level, "environment" in payload), ("error", False))
        self.assertEqual(payload["began_at"], wd_iso(self.clock()))

    def test_a_failure_that_comes_back_during_a_shutdown_is_a_warning_and_the_next_house_announces_the_run(self):
        self.sail.fail = sail_503()
        level, text, payload = self.attempt(closing=lambda: True)
        self.assertEqual((level, payload["environment"]), ("warning", "sail"))
        self.assertIn("while the House was shutting down", text)
        self.assertTrue(self.ledger.last("ops.deploy").payload["during_shutdown"])
        self.clock.advance(1800)
        self.assertEqual(self.attempt()[0], "error", "the run had not been announced by a House that was running")
        self.clock.advance(3600)
        self.assertEqual(self.attempt()[0], "warning")


def wd_iso(epoch):
    from league.ledger import now_iso

    return now_iso(lambda: epoch)


class AHouseCase:
    """A House from test_house's fixture, with a Sail that can fail its backups and a release directory to deploy into."""

    def __init__(self, test):
        from league.tests.test_house import HouseCase
        from league.tests.test_watchdog import make_tree
        from league.watchdog import Releases

        class Case(HouseCase):
            def runTest(self):
                pass

        self.case = Case()
        self.case.setUp()
        test.addCleanup(self.case.tearDown)
        self.house, self.clock = self.case.house, self.case.clock
        self.tmp = Path(self.case.dir.name)
        self.make_tree = make_tree
        self.releases = Releases(self.tmp / "workspace", clock=self.clock)
        self.releases.stage(make_tree(self.tmp / "src-1", "v1"), "rel-0001")
        self.releases.promote("rel-0001")
        self.house.tick()  # the House under rel-0001, with a health.json, and no backup yet
        self.house.wait(30)
        self.sail = FakeSail([{"name": "ltcm-floor", "status": "running", "sailbox_id": "sb_house"}])
        self.house.backup = Backup(self.sail, self.house.ledger, clock=self.clock)

    def deploy(self, during_watch, *, on_restart=None, watch_seconds=2700, watch_every=900):
        """Deploy rel-0002 through the real watchdog and the real `HouseHealth`; `during_watch(n)` runs before the n-th
        reading, then the House ticks (and its background work, the backup among it, finishes)."""
        from league.watchdog import Health, HouseHealth, Watchdog

        watch = HouseHealth(self.house.root, clock=self.clock, restart_within=None)
        readings = []

        def restart():
            if on_restart is not None:
                on_restart()
            self.house._record_start()  # the new release's House starts
            return {"ran": True}

        def sleep(seconds):
            self.clock.advance(seconds)
            during_watch(len(readings))
            readings.append(seconds)
            self.house.tick()
            self.house.wait(30)

        dog = Watchdog(self.releases, run_canary=lambda *_: Health(True, (), {"ticks": "fine"}), restart_house=restart,
                       read_house_health=watch, clock=self.clock, sleep=sleep)
        return dog.deploy(self.make_tree(self.tmp / "src-2", "v2"), "rel-0002", watch_seconds=watch_seconds, watch_every=watch_every)

    def watch_rows(self):
        return [row for row in self.releases.history() if row.get("stage") == "watch"]

    def backup_alerts(self):
        return [e.payload for e in self.house.ledger.read(kinds="ops.alert", limit=500) if "backup" in str(e.payload.get("text"))]


class AVendorsOutageNeverRollsBackARelease(unittest.TestCase):
    """H2's regression tests, through the real watchdog, the real `HouseHealth` and a real House."""

    def test_a_release_watched_during_a_backup_outage_that_begins_inside_the_watch_is_promoted(self):
        world = AHouseCase(self)

        def during(n):
            if n == 0:
                world.sail.fail = sail_503()  # Sail's checkpoint API goes down after the promotion

        result = world.deploy(during)
        self.assertEqual(result["verdict"], "promoted", result["reasons"])
        self.assertEqual([(a["level"], a.get("environment")) for a in world.backup_alerts()], [("error", "sail"), ("warning", "sail")])
        last = world.watch_rows()[-1]["detail"]
        self.assertEqual((last["error_alerts"], last["environment_alerts"]), (0, 1))  # the watch reads errors; the warning is not one
        self.assertEqual(last["environment_first"]["service"], "sail")
        self.assertEqual(world.releases.current(), "rel-0002")

    def test_the_old_houses_in_flight_backup_error_after_the_promotion_does_not_roll_it_back(self):
        """Sept 25, 2026, 00:04:42Z: the owner's release was promoted while the OLD House's backup was in Sail's
        checkpoint call; it failed at 00:05:55Z, after the reading the watch counts from and before the old House
        exited, and the release was rolled back at 00:06:12Z on "reading 3: 1 error alert(s) since seq 610396"."""
        world = AHouseCase(self)
        world.sail.fail = sail_503()

        def old_house_backup_fails():
            world.house._run_backup()  # the old process, still up after the promotion (not yet told to stop)

        result = world.deploy(lambda n: None, on_restart=old_house_backup_fails)
        self.assertEqual(result["verdict"], "promoted", result["reasons"])
        first = world.watch_rows()[0]["detail"]
        self.assertEqual((first["error_alerts"], first["environment_alerts"]), (0, 1))
        self.assertLess(first["environment_first"]["seq"], min(e.seq for e in world.house.ledger.read(kinds="ops.started", limit=500)
                                                               if e.seq > first["since_seq"]))

    def test_a_release_whose_first_tick_raises_still_rolls_back_during_an_outage(self):
        world = AHouseCase(self)
        world.sail.fail = sail_503()

        def during(n):
            if n == 0:  # what league/__main__.py writes when the new release's tick raises
                world.house.alert("error", "tick failed: KeyError: 'settled'")

        result = world.deploy(during)
        self.assertEqual(result["verdict"], "rolled_back")
        self.assertIn("reading 3: 1 error alert(s)", result["reasons"][0])
        self.assertIn("tick failed: KeyError: 'settled'", result["reasons"][0])
        self.assertGreaterEqual(world.watch_rows()[-1]["detail"]["environment_alerts"], 1)
        self.assertEqual(world.releases.current(), "rel-0001")


class TheShutdownNeverWaitsOnSail(unittest.TestCase):
    """Graceful shutdown waits at most `House.SHUTDOWN_WAIT_SECONDS` (5 s) for background work in flight, and a
    backup the shutdown cut off writes nothing: no row, and no error alert."""

    def test_a_backup_hung_in_sails_checkpoint_call_cannot_hold_the_shutdown_and_writes_nothing(self):
        import inspect
        import threading
        import time

        from league.house import House
        from league.ledger import Ledger as Reader

        self.assertEqual(House.SHUTDOWN_WAIT_SECONDS, 5.0)
        self.assertEqual(inspect.signature(House.close).parameters["wait"].default, 5.0)
        world = AHouseCase(self)
        house = world.house
        entered, release = threading.Event(), threading.Event()

        class HungSail(FakeSail):
            def checkpoint(self, box, **kw):
                entered.set()
                release.wait(30)  # Sept 25, 2026: each failing checkpoint call took 150-162 s
                raise sail_503()

        house.backup = Backup(HungSail([{"name": "ltcm-floor", "status": "running", "sailbox_id": "sb_house"}]), house.ledger, clock=world.clock)
        self.assertTrue(house._background("backup", house._run_backup))
        self.assertTrue(entered.wait(10))
        head = house.ledger.head()[0]
        started = time.monotonic()
        house.close(wait=0.3)
        self.assertLess(time.monotonic() - started, 5.0, "the shutdown waited on the backup")
        release.set()
        house.wait(10)  # the backup's thread ends against a closed ledger
        reader = Reader(house.root / "ledger.sqlite", clock=world.clock)
        self.addCleanup(reader.close)
        after = [e for e in reader.read(after=head, limit=100)]
        self.assertEqual([(e.kind, e.payload.get("what"), e.payload.get("level")) for e in after if e.kind in ("ops.deploy", "ops.alert")], [])

    def test_a_backup_that_fails_while_the_house_shuts_down_is_a_warning(self):
        world = AHouseCase(self)
        world.sail.fail = sail_503()
        world.house.begin_close()  # TERM
        world.house._run_backup()
        alert = world.backup_alerts()[-1]
        self.assertEqual((alert["level"], alert["environment"]), ("warning", "sail"))


class TermEndsTheLoopsWait(unittest.TestCase):
    """`python3 -m league run` on TERM: the loop ends after the tick in hand. Until Sept 25, 2026 it then slept out the
    rest of the tick's minute (`time.sleep` sleeps through a signal); TERM-to-exit took 24-82 s over the 13 restarts
    from 18:43Z Sept 24, the old House writing rows -- a backup's error among them -- into the new release's watch."""

    def test_a_term_after_a_tick_ends_the_loop_at_once(self):
        import os
        import signal
        import threading
        import time
        from unittest import mock

        import league.__main__ as entry

        previous = signal.getsignal(signal.SIGTERM)
        self.addCleanup(signal.signal, signal.SIGTERM, previous)
        house = mock.MagicMock()
        house.registry.living.return_value = ["an agent"]
        house.settings.tick_seconds = 60
        ticks = []

        def tick():
            ticks.append(time.monotonic())
            if len(ticks) == 1:  # TERM lands while the loop waits for the next tick
                threading.Timer(0.2, os.kill, (os.getpid(), signal.SIGTERM)).start()
            return {"at": "now", "woke": [], "orders": 0, "deaths": [], "reconciled": {}, "budget": "open"}

        house.tick.side_effect = tick
        with tempfile.TemporaryDirectory() as root, mock.patch.object(entry, "build", return_value=house), \
                mock.patch.object(entry, "load_config", return_value={}), mock.patch("sys.stdout"):
            started = time.monotonic()
            self.assertEqual(entry.main(["run", "--root", root]), 0)
            took = time.monotonic() - started
        self.assertEqual(len(ticks), 1)
        self.assertLess(took, 5.0, "the loop slept out the tick's minute after TERM")
        house.begin_close.assert_called_once()
        house.sandbox.sleep_all.assert_called_once()
        house.close.assert_called_once()


class TheRepeatEscalationCarriesTheMarker(unittest.TestCase):
    """`House.alert` escalates a warning that repeats 10 times in 30 minutes into one error (L3, Sept 24, 2026). A run of
    a service's failures escalates marked, so the watch never rolls back on it; a run that mixes in the House's own
    failure of the same folded text escalates unmarked."""

    def test_a_services_run_escalates_marked_and_a_mixed_run_does_not(self):
        world = AHouseCase(self)
        house = world.house
        for n in range(10):
            world.clock.advance(60)
            house.alert("warning", f"publishing failed (PublishError: the site refused the checkpoint: HTTP 50{n % 4})", environment="site")
        escalated = house.ledger.last("ops.alert").payload
        self.assertEqual((escalated["level"], escalated.get("environment")), ("error", "site"))
        self.assertIn("a warning repeated 10 times in 30 minutes", escalated["text"])
        world.clock.advance(3600)  # the run goes quiet
        for n in range(10):
            world.clock.advance(60)
            house.alert("warning", f"its box did not run (SailboxError: sailbox api 40{n % 2})", **({"environment": "sail"} if n != 4 else {}))
        mixed = house.ledger.last("ops.alert").payload
        self.assertEqual(mixed["level"], "error")
        self.assertNotIn("environment", mixed, "one of the run's warnings was the House's own")


if __name__ == "__main__":
    unittest.main()
