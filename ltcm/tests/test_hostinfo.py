"""`describe_host()` on a box and on a laptop, with every source of truth injected.

No test here reads the real `/proc`, the real environment or the real hostname, so the same
assertions hold whether they run on the MacBook or on the Sailbox they describe.
"""

from __future__ import annotations

import unittest

from ltcm.hostinfo import describe_host, memory_bytes, on_sailbox, uptime_seconds

PROC = {
    "/proc/uptime": "8123.45 31900.11\n",
    "/proc/sys/kernel/random/boot_id": "3f2a1b0c-1111-2222-3333-444455556666\n",
    "/proc/meminfo": "MemTotal:       16384000 kB\nMemFree: 900 kB\nMemAvailable:   15000000 kB\n",
}


def reader(path: str) -> str:
    return PROC[path]  # KeyError for anything else: nothing else may be read


def angry(path: str) -> str:
    raise OSError("no /proc here")


def describe(env=None, **kwargs):
    defaults = {
        "reader": reader,
        "clock": lambda: 1789000000.0,
        "disk_usage": lambda _root: (32 * 1024**3, 4 * 1024**3, 28 * 1024**3),
        "hostname": lambda: "sailbox-7",
    }
    defaults.update(kwargs)
    return describe_host(env if env is not None else {}, **defaults)


class LocalTests(unittest.TestCase):
    def test_an_empty_environment_is_the_owners_machine(self):
        report = describe()
        self.assertEqual(report["host"], "local")
        self.assertNotIn("box_id", report)
        self.assertNotIn("detected_via", report)
        self.assertIs(report["sandbox"], False)

    def test_the_local_description_is_still_complete(self):
        report = describe()
        self.assertEqual(report["uptime_seconds"], 8123.45)
        self.assertEqual(report["boot_id"], "3f2a1b0c-1111-2222-3333-444455556666")
        self.assertEqual(report["memory_total_bytes"], 16384000 * 1024)
        self.assertEqual(report["disk_free_bytes"], 28 * 1024**3)
        self.assertEqual(report["hostname"], "sailbox-7")
        self.assertEqual(report["checked_at"], "2026-09-10T00:26:40Z")
        self.assertIn("python", report)
        self.assertIsInstance(report["pid"], int)

    def test_a_sailbox_variable_belonging_to_something_else_is_ignored(self):
        self.assertEqual(describe({"SAILBOX": "yes", "SAIL_API_KEY": "sk-x"})["host"], "local")


class SailboxTests(unittest.TestCase):
    def test_the_box_id_variable_identifies_the_host(self):
        report = describe({"SAILBOX_ID": "sb_9c8f1e2a", "IS_SANDBOX": "1", "SAIL_APP": "ltcm"})
        self.assertEqual(report["host"], "sailbox")
        self.assertEqual(report["box_id"], "sb_9c8f1e2a")
        self.assertEqual(report["app"], "ltcm")
        self.assertEqual(report["detected_via"], "SAILBOX_ID")
        self.assertIs(report["sandbox"], True)

    def test_the_sandbox_marker_alone_names_the_host_but_invents_no_id(self):
        report = describe({"IS_SANDBOX": "1"})
        self.assertEqual(report["host"], "sailbox")
        self.assertNotIn("box_id", report)
        self.assertEqual(report["detected_via"], "IS_SANDBOX")

    def test_a_region_is_reported_when_sail_sets_one(self):
        self.assertEqual(describe({"SAILBOX_ID": "sb_1", "SAIL_REGION": "us-east"})["region"],
                         "us-east")
        self.assertNotIn("region", describe({"SAILBOX_ID": "sb_1"}))

    def test_the_alternate_variable_name_is_accepted(self):
        self.assertEqual(describe({"SAIL_SAILBOX_ID": "sb_2"})["box_id"], "sb_2")

    def test_on_sailbox_is_the_cheap_form_of_the_same_question(self):
        self.assertTrue(on_sailbox({"SAILBOX_ID": "sb_1"}))
        self.assertTrue(on_sailbox({"IS_SANDBOX": "1"}))
        self.assertFalse(on_sailbox({"IS_SANDBOX": "0"}))
        self.assertFalse(on_sailbox({}))


class HostileInputTests(unittest.TestCase):
    def test_an_absurd_value_is_dropped_rather_than_carried(self):
        report = describe({"SAILBOX_ID": "s" * 5000})
        self.assertEqual(report["host"], "local")
        self.assertNotIn("box_id", report)

    def test_control_characters_are_dropped(self):
        self.assertEqual(describe({"SAILBOX_ID": "sb_1\nHost: evil"})["host"], "local")

    def test_an_unreadable_proc_does_not_raise(self):
        report = describe({"SAILBOX_ID": "sb_1"}, reader=angry)
        self.assertEqual(report["host"], "sailbox")
        self.assertIsNone(report["uptime_seconds"])
        self.assertNotIn("boot_id", report)
        self.assertNotIn("memory_total_bytes", report)

    def test_a_failing_disk_or_hostname_lookup_does_not_raise(self):
        def boom(*_args):
            raise OSError("no")

        report = describe({}, disk_usage=boom, hostname=boom)
        self.assertNotIn("disk_free_bytes", report)
        self.assertEqual(report["hostname"], "unknown")

    def test_garbage_in_proc_uptime_is_survived(self):
        self.assertIsNone(uptime_seconds(lambda _p: "not a number\n"))
        self.assertIsNone(uptime_seconds(lambda _p: ""))

    def test_garbage_in_meminfo_is_survived(self):
        self.assertEqual(memory_bytes(lambda _p: "MemTotal: lots of kB\n"), {})

    def test_the_real_environment_never_raises(self):
        # The one call that touches this machine: it must answer, whatever the machine is.
        report = describe_host()
        self.assertIn(report["host"], ("local", "sailbox"))
        self.assertIn("checked_at", report)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
