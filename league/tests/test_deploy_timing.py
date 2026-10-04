"""Offline deployment admission, promotion crossings, and exact-attempt retry accounting."""

from __future__ import annotations

import contextlib
import datetime as dt
import importlib.util
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from league import watchdog as wd
from league.tests.test_watchdog import Case, World
from league.updater import Updater, updater_ships


def at(text):
    return dt.datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()


class CalendarAdmission(unittest.TestCase):
    def test_real_calendar_hold_has_an_explicit_next_time_and_closed_day_is_allowed(self):
        held = wd.deployment_timing(at("2026-10-05T12:00:00Z"))
        self.assertFalse(held["allowed"])
        self.assertEqual(held["deferred"], "session")
        self.assertEqual(held["next_eligible_ts"], at("2026-10-05T20:05:00Z"))
        self.assertTrue(wd.deployment_timing(at("2026-10-04T12:00:00Z"))["allowed"])

    def test_calendar_import_or_reader_failure_is_a_hold(self):
        for error in (ImportError("calendar missing"), RuntimeError("calendar unreadable")):
            with self.subTest(error=error), mock.patch.object(wd, "_drill_session", side_effect=error):
                held = wd.deployment_timing(at("2026-10-05T10:00:00Z"))
                self.assertFalse(held["allowed"])
                self.assertEqual(held["deferred"], "calendar")
                self.assertIsNone(held["next_eligible_ts"])

    def test_malformed_nonfinite_and_unrepresentable_windows_never_allow_deployment(self):
        invalid = [[], {}, {"starts": 1}, {"starts": True, "closes": 2},
                   {"starts": 0, "closes": float("nan")}, {"starts": float("inf"), "closes": 2},
                   {"starts": 1, "closes": 1}, {"starts": 2, "closes": 1},
                   {"starts": "bad", "closes": 2}, {"starts": -1e308, "closes": 0},
                   {"starts": 0, "closes": 1e308}]
        for window in invalid:
            with self.subTest(window=window):
                held = wd.deployment_timing(at("2026-10-05T10:00:00Z"), session=lambda _: window)
                self.assertFalse(held["allowed"])
                self.assertEqual(held["deferred"], "calendar")

    def test_invalid_or_unrepresentable_now_is_held_even_if_calendar_claims_closed(self):
        for value in (True, None, "bad", float("nan"), float("inf"), -1e308, 1e308):
            with self.subTest(now=value):
                self.assertFalse(wd.deployment_timing(value, session=lambda _: None)["allowed"])


class WatchdogAdmission(Case):
    def setUp(self):
        super().setUp()
        self.clock.now = at("2026-10-05T11:54:00Z")
        self.world = World(self.clock)
        self.dog = wd.Watchdog(self.releases, run_canary=self.world.run_canary, restart_house=self.world.restart_house,
                               read_house_health=self.world.read_house_health, clock=self.clock, sleep=self.world.sleep)
        self.staged("rel-old")
        self.releases.promote("rel-old")

    def updater(self):
        updater = object.__new__(Updater)
        updater.releases = self.releases
        return updater

    def deploy(self, **kwargs):
        return self.dog.deploy(self.tree("new"), "rel-new", watch_seconds=0, **kwargs)

    def assert_not_promoted(self, result):
        self.assertEqual(result["verdict"], "refused")
        self.assertIs(result["unjudged"], True)
        self.assertEqual((self.releases.current(), self.releases.previous()), ("rel-old", None))
        self.assertEqual(self.world.restarts, 0)
        self.assertFalse(any(row["stage"] == "promote" for row in result["stages"]))

    def test_direct_owner_and_attested_entries_are_held_before_staging(self):
        self.clock.now = at("2026-10-05T12:00:00Z")
        for attestation in (None, {"sha": "a" * 40}):
            with self.subTest(attested=bool(attestation)):
                result = self.deploy(attestation=attestation)
                self.assert_not_promoted(result)
                self.assertEqual([row["stage"] for row in result["stages"]], ["verdict"])
                self.assertEqual(result["deferred"], "session")
                self.assertFalse((self.base / "releases" / "rel-new").exists())
        self.assertEqual(self.world.canary_calls, [])

    def test_canary_crossing_the_hold_is_refused_before_links_or_restart(self):
        real = self.world.run_canary

        def slow_canary(*args):
            self.clock.advance(120)
            return real(*args)

        self.dog.run_canary = slow_canary
        result = self.deploy()
        self.assert_not_promoted(result)
        self.assertEqual(result["deferred"], "session")
        self.assertEqual({row["attempt"] for row in result["stages"]}, {result["attempt"]})
        self.assertEqual(len(result["attempt"]), 32)
        self.assertNotIn("rel-new", self.updater().tried(), "a timing hold does not refute a candidate")

    def test_health_reader_crossing_the_hold_is_checked_immediately_before_promotion(self):
        real = self.world.read_house_health

        def slow_reader():
            self.clock.advance(120)
            return real()

        self.dog.read_house_health = slow_reader
        result = self.deploy()
        self.assert_not_promoted(result)
        self.assertEqual(result["deferred"], "session")

    def test_calendar_failure_at_entry_does_no_staging_or_canary(self):
        self.dog.deployment_session = mock.Mock(side_effect=RuntimeError("calendar missing"))
        result = self.deploy()
        self.assert_not_promoted(result)
        self.assertEqual(result["deferred"], "calendar")
        self.assertEqual(self.world.canary_calls, [])
        self.assertFalse((self.base / "releases" / "rel-new").exists())

    def test_calendar_failure_after_canary_preserves_current(self):
        self.dog.deployment_session = mock.Mock(side_effect=[None, RuntimeError("second read missing")])
        result = self.deploy()
        self.assert_not_promoted(result)
        self.assertEqual(result["deferred"], "calendar")
        self.assertEqual(len(self.world.canary_calls), 1)

    def test_deferred_staged_candidate_can_retry_after_close_with_a_new_attempt(self):
        real = self.world.run_canary

        def slow_canary(*args):
            self.clock.advance(120)
            return real(*args)

        self.dog.run_canary = slow_canary
        first = self.deploy(attestation={"sha": "a" * 40})
        self.assert_not_promoted(first)
        self.assertEqual(updater_ships(self.releases.history()), [])
        self.clock.now = at("2026-10-05T20:05:00Z")
        second = self.deploy(attestation={"sha": "a" * 40})
        self.assertEqual(second["verdict"], "promoted")
        self.assertNotEqual(first["attempt"], second["attempt"])
        self.assertEqual(self.world.restarts, 1)

    def test_same_second_later_deferral_does_not_erase_a_real_canary_failure(self):
        self.world.canary = wd.Health(False, ("synthetic failure",), {})
        failed = self.deploy()
        self.dog.deployment_session = lambda now: {"starts": now - 1, "closes": now + 100}
        deferred = self.deploy()
        self.assertEqual(failed["deploy"], deferred["deploy"])
        self.assertNotEqual(failed["attempt"], deferred["attempt"])
        self.assertIn("rel-new", self.updater().tried())

    def test_same_second_later_failure_still_retires_an_earlier_deferred_candidate(self):
        self.dog.deployment_session = lambda now: {"starts": now - 1, "closes": now + 100}
        deferred = self.deploy()
        self.dog.deployment_session = lambda now: None
        self.world.canary = wd.Health(False, ("synthetic failure",), {})
        failed = self.deploy()
        self.assertEqual(failed["deploy"], deferred["deploy"])
        self.assertNotEqual(failed["attempt"], deferred["attempt"])
        self.assertIn("rel-new", self.updater().tried())

    def test_same_second_later_deferral_does_not_merge_a_prior_promotions_train_record(self):
        first = self.deploy(attestation={"sha": "a" * 40})
        self.dog.deployment_session = lambda now: {"starts": now - 1, "closes": now + 100}
        later = self.deploy(attestation={"sha": "a" * 40})
        self.assertEqual(first["deploy"], later["deploy"])
        ships = updater_ships(self.releases.history())
        self.assertEqual(len(ships), 1)
        self.assertEqual((ships[0]["attempt"], ships[0]["verdict"]), (first["attempt"], "promoted"))

    def test_recovery_rollback_still_runs_during_blackout_without_calendar_permission(self):
        self.staged("rel-new")
        self.releases.promote("rel-new")
        self.clock.now = at("2026-10-05T12:00:00Z")
        reader = mock.Mock(side_effect=RuntimeError("calendar missing"))
        self.dog.deployment_session = reader
        result = self.dog.rollback("synthetic recovery")
        self.assertTrue(result["ok"])
        self.assertEqual(self.releases.current(), "rel-old")
        self.assertEqual(self.world.restarts, 1)
        reader.assert_not_called()

    def test_legacy_and_malformed_attempts_keep_real_judgment_and_train_grouping(self):
        for index, token in enumerate((None, [], {}, "not-a-uuid")):
            release = f"legacy-{index}"
            row = {"deploy": f"{release}@1", "release": release, "sha": "a" * 40}
            if token is not None:
                row["attempt"] = token
            self.releases.record({**row, "stage": "start"})
            self.releases.record({**row, "stage": "promote", "ok": True})
            self.releases.record({**row, "stage": "verdict", "verdict": "refused"})
            self.assertIn(release, self.updater().tried())
        ships = updater_ships(self.releases.history())
        self.assertEqual({row["release"] for row in ships}, {f"legacy-{i}" for i in range(4)})

    def test_contradictory_token_cannot_erase_a_promote_rollback_or_real_verdict(self):
        for index, judged in enumerate(({"stage": "promote", "ok": True}, {"stage": "rollback", "ok": True},
                                        {"stage": "verdict", "verdict": "refused"})):
            release, token = f"judged-{index}", f"{index:032x}"
            row = {"deploy": f"{release}@1", "release": release, "attempt": token}
            self.releases.record({**row, "stage": "start"})
            self.releases.record({**row, **judged})
            self.releases.record({**row, "stage": "verdict", "verdict": "refused", "unjudged": True, "deferred": "session"})
            self.assertIn(release, self.updater().tried())


class OwnerConsoleAdmission(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location("floor_for_timing_test", Path(__file__).resolve().parents[2] / "scripts" / "floor_box.py")
        self.floor = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.floor)
        self.now = at("2026-10-05T11:54:00Z")
        self.api = mock.Mock()
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.mocks = {}
        values = {"read_state": {}, "require_box": "fake-box", "client": self.api, "code_files": {},
                  "tarball": b"synthetic release", "release_id_for": "rel-new",
                  "probe": {"env": "yes", "runnable": "no"}, "structure_gaps": [], "write_scripts": None,
                  "push_release": "/incoming/inactive", "remember_release": None, "write_state": None,
                  "watchdog_launch": "synthetic command", "say": None}
        for name, value in values.items():
            self.mocks[name] = self.stack.enter_context(mock.patch.object(self.floor, name, return_value=value))
        self.stack.enter_context(mock.patch.object(self.floor.time, "time", side_effect=lambda: self.now))
        self.args = SimpleNamespace(force_structures_risk=True, no_wait=True, timeout=1, poll_seconds=1)

    def test_blackout_and_unknown_time_refuse_before_state_client_or_remote_work(self):
        for moment in (at("2026-10-05T12:00:00Z"), float("nan"), float("inf")):
            with self.subTest(now=moment):
                self.now = moment
                with self.assertRaises(SystemExit):
                    self.floor.cmd_deploy(self.args)
        self.mocks["read_state"].assert_not_called()
        self.mocks["client"].assert_not_called()
        self.mocks["write_scripts"].assert_not_called()
        self.api.exec.assert_not_called()

    def test_slow_probe_crossing_hold_refuses_before_first_remote_mutation(self):
        def slow_probe(*args):
            self.now += 120
            return {"env": "yes", "runnable": "no"}

        self.mocks["probe"].side_effect = slow_probe
        with self.assertRaises(SystemExit):
            self.floor.cmd_deploy(self.args)
        self.mocks["write_scripts"].assert_not_called()
        self.mocks["push_release"].assert_not_called()
        self.api.exec.assert_not_called()

    def test_upload_crossing_hold_never_launches_the_watchdog(self):
        def slow_upload(*args):
            self.now += 120
            return "/incoming/inactive"

        self.mocks["push_release"].side_effect = slow_upload
        with self.assertRaises(SystemExit):
            self.floor.cmd_deploy(self.args)
        self.mocks["write_scripts"].assert_called_once()
        self.mocks["push_release"].assert_called_once()
        self.mocks["write_state"].assert_not_called()
        self.api.exec.assert_not_called()

    def test_local_bookkeeping_crossing_hold_is_rechecked_immediately_before_launch(self):
        self.mocks["write_state"].side_effect = lambda *args: setattr(self, "now", self.now + 120)
        with self.assertRaises(SystemExit):
            self.floor.cmd_deploy(self.args)
        self.api.exec.assert_not_called()

    def test_afterclose_allowed_path_reaches_only_the_fake_watchdog_launcher(self):
        self.now = at("2026-10-05T20:05:00Z")
        self.assertEqual(self.floor.cmd_deploy(self.args), 0)
        self.api.exec.assert_called_once()


if __name__ == "__main__":
    unittest.main()
