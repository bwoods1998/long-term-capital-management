"""The history fetch's controller (scripts/data/window.py) with a fake data box, and the nightly's handle changes it
relies on (exit 75 accepted, receipts, a daemon hook that never raises). No network."""

from __future__ import annotations

import contextlib
import datetime as dt
import json
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

DATA = Path(__file__).resolve().parents[2] / "scripts" / "data"
if str(DATA) not in sys.path:
    sys.path.insert(0, str(DATA))

import nightly  # noqa: E402
import storelib as sl  # noqa: E402
import window as wn  # noqa: E402
from locking import process_lock  # noqa: E402

UTC = dt.timezone.utc
ARGS = ("--stages 1,2,3,4,5,6,9,10,11 --order 1,2,3,5,4,6,9,10,11 --threads 8 "
        "--blocks /data/work/blocks.json --nightly-quiet")
BLOCKS = {"schema": 1, "11": {"job": "day", "roots": "core", "first": "2017-01-03", "last": "2019-12-31",
                              "history_sessions": 60}}


def at(text: str) -> dt.datetime:
    return dt.datetime.fromisoformat(text).replace(tzinfo=UTC)


class FakeOps:
    def __init__(self):
        self.awake_, self.running_ = True, False
        self.receipts, self.progress_ = {}, None
        self.started, self.stopped, self.woken, self.leases = [], 0, 0, 0
        self.ready = (True, "caught up")
        self.fail = None

    def awake(self):
        if self.fail:
            raise self.fail
        return self.awake_

    def wake(self):
        self.woken += 1
        self.awake_ = True

    def running(self):
        return self.running_

    def stop(self):
        self.stopped += 1
        self.running_ = False

    def receipt(self, path):
        return self.receipts.get(path)

    def progress(self):
        return self.progress_

    @contextlib.contextmanager
    def lease(self):
        self.leases += 1
        yield self

    def start(self, args, blocks):
        self.started.append((args, blocks))
        self.running_ = True
        return f"/data/work/restart-{len(self.started)}.exit"

    def nightly_ready(self, now):
        return self.ready


class Controller(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state = Path(self.tmp.name) / "state"
        self.state.mkdir()
        self.blocks = Path(self.tmp.name) / "blocks.json"
        self.blocks.write_text(json.dumps(BLOCKS))
        self.now = [at("2026-09-29T03:00")]
        self.ops = FakeOps()

    def enable(self, args=ARGS, not_before="2026-09-29T07:30:00Z"):
        return wn.enable(self.state, self.blocks, args, not_before=not_before, names=[], clock=lambda: self.now[0])

    def tick(self, when=None):
        if when:
            self.now[0] = at(when)
        return wn.Window(self.state, ops=lambda: self.ops, clock=lambda: self.now[0]).tick()

    def finish(self, code, done=None):
        self.ops.running_ = False
        self.ops.receipts[f"/data/work/restart-{len(self.ops.started)}.exit"] = code
        if done is not None:
            self.ops.progress_ = {"stages": {"11": {"done": done, "planned": 4070}}}

    def test_enable_refuses_arguments_that_could_hold_the_session_or_skip_the_blocks(self):
        for args, pattern in ((ARGS.replace(" --nightly-quiet", ""), "nightly-quiet"),
                              (ARGS.replace("/data/work/blocks.json", "/tmp/b.json"), "uploaded blocks"),
                              (ARGS + " --forward-days 2026-09-28", "forward days"),
                              (ARGS.replace("9,10,11", "9,10"), "no block"),
                              (ARGS.replace("1,2,3,4", "1,2,3,7"), "nightly job")):
            with self.assertRaisesRegex(ValueError, pattern):
                self.enable(args)
        with self.assertRaisesRegex(SystemExit, "no block"):
            self.enable(ARGS.replace("9,10,11", "9,10,11,13"))
        self.blocks.write_text(json.dumps({**BLOCKS, "11": {**BLOCKS["11"], "last": "2022-06-30"}}))
        with self.assertRaisesRegex(ValueError, "before Train"):
            self.enable()

    def test_enable_keeps_its_records_private(self):
        record = self.enable()
        self.assertEqual((record["stages"], record["phase"], record["enabled"]), ([11], "waiting", True))
        folder = self.state / wn.DIR_NAME
        self.assertEqual(stat.S_IMODE(folder.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE((folder / "blocks.json").stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE((folder / "window.json").stat().st_mode), 0o600)

    def test_waits_for_its_time_and_the_nightly_then_starts_once(self):
        self.enable()
        self.assertEqual(self.tick()["phase"], "waiting")  # 03:00Z, not before 07:30Z
        self.ops.ready = (False, "the nightly has not finished 2026-09-28")
        self.assertEqual(self.tick("2026-09-29T07:31")["phase"], "waiting-nightly")
        self.assertEqual(self.ops.started, [])
        self.ops.ready = (True, "caught up")
        record = self.tick("2026-09-29T07:32")
        self.assertEqual(record["phase"], "running")
        self.assertEqual(self.ops.started, [(ARGS, self.blocks.read_bytes())])
        self.assertEqual(record["starts"][0]["receipt"], "/data/work/restart-1.exit")
        self.assertEqual(self.tick("2026-09-29T07:33")["phase"], "running")
        self.assertEqual(len(self.ops.started), 1)

    def test_pauses_before_the_window_and_resumes_after_without_a_stall(self):
        self.enable(not_before=None)
        self.tick("2026-09-29T08:00")
        self.assertEqual(self.tick("2026-09-30T05:26")["phase"], "running")  # the runner stops itself first
        record = self.tick("2026-09-30T05:28")
        self.assertEqual((record["phase"], self.ops.stopped, self.ops.leases), ("paused", 1, 2))
        self.assertEqual(record["starts"][-1]["stopped"], "backstop before the quiet window")
        self.ops.receipts["/data/work/restart-1.exit"] = 143
        self.ops.awake_ = False
        self.assertEqual(self.tick("2026-09-30T06:10")["phase"], "quiet")
        self.assertEqual(self.ops.woken, 0)  # never woken inside the window
        record = self.tick("2026-09-30T07:31")
        self.assertEqual((record["phase"], record["stalls"], len(self.ops.started), self.ops.woken), ("running", 0, 2, 1))

    def test_a_run_the_window_deferred_is_not_a_stall(self):
        self.enable(not_before=None)
        self.tick("2026-09-29T08:00")
        self.finish(sl.QUIET_EXIT, done=100)
        record = self.tick("2026-09-30T07:40")
        self.assertEqual((record["phase"], record["stalls"], len(self.ops.started)), ("running", 0, 2))

    def test_a_clean_exit_is_complete_and_final(self):
        self.enable(not_before=None)
        self.tick("2026-09-29T08:00")
        self.finish(0, done=4070)
        self.assertEqual(self.tick("2026-09-29T12:00")["phase"], "complete")
        self.assertEqual(self.tick("2026-09-29T12:01")["phase"], "complete")
        self.assertEqual(len(self.ops.started), 1)

    def test_two_runs_without_progress_stall_and_nothing_restarts(self):
        self.enable(not_before=None)
        self.ops.progress_ = {"stages": {"11": {"done": 50, "planned": 4070}}}
        self.tick("2026-09-29T08:00")
        self.finish(1, done=50)
        record = self.tick("2026-09-29T10:00")
        self.assertEqual((record["phase"], record["stalls"]), ("waiting", 1))
        self.assertIn("retry after", record["why"])
        record = self.tick("2026-09-29T10:31")
        self.assertEqual((record["phase"], len(self.ops.started)), ("running", 2))
        self.finish(1, done=50)
        record = self.tick("2026-09-29T13:00")
        self.assertEqual(record["phase"], "stalled")
        self.tick("2026-09-29T20:00")
        self.assertEqual(len(self.ops.started), 2)

    def test_a_failed_run_that_made_progress_is_not_a_stall(self):
        self.enable(not_before=None)
        self.ops.progress_ = {"stages": {"11": {"done": 50, "planned": 4070}}}
        self.tick("2026-09-29T08:00")
        self.finish(1, done=900)
        record = self.tick("2026-09-29T10:00")
        self.assertEqual(record["stalls"], 0)
        self.assertEqual(self.tick("2026-09-29T10:31")["phase"], "running")

    def test_nothing_starts_just_before_the_window_and_the_box_is_woken_to_start(self):
        self.enable(not_before=None)
        record = self.tick("2026-09-29T05:15")
        self.assertEqual(record["phase"], "waiting")
        self.assertIn("quiet window is near", record["why"])
        self.ops.awake_ = False
        self.assertEqual(self.tick("2026-09-29T07:45")["phase"], "running")
        self.assertEqual(self.ops.woken, 1)

    def test_a_tick_never_raises(self):
        self.enable(not_before=None)
        self.ops.fail = RuntimeError("the Sail API is down")
        record = self.tick("2026-09-29T08:00")
        self.assertIn("the Sail API is down", record["error"])
        self.ops.fail = SystemExit("no data box recorded")
        self.assertIn("no data box", self.tick("2026-09-29T08:01")["error"])
        self.assertEqual(self.ops.started, [])

    def test_a_changed_blocks_file_is_never_uploaded(self):
        self.enable(not_before=None)
        (self.state / wn.DIR_NAME / "blocks.json").write_text(json.dumps({**BLOCKS, "13": BLOCKS["11"]}))
        record = self.tick("2026-09-29T08:00")
        self.assertIn("changed since", record["error"])
        self.assertEqual(self.ops.started, [])

    def test_disable_stops_under_the_lease(self):
        self.enable(not_before=None)
        self.tick("2026-09-29T08:00")
        record = wn.disable(self.state, stop=True, ops=lambda: self.ops)
        self.assertEqual((record["phase"], self.ops.stopped), ("disabled", 1))
        self.assertEqual(self.tick("2026-09-29T09:00"), {"phase": "disabled"})

    def test_the_daemon_leaves_the_ticks_to_a_standalone_loop(self):
        self.assertIsNone(wn.daemon_tick(self.state, ops=lambda: self.ops))
        self.enable(not_before=None)
        with process_lock(self.state / wn.DIR_NAME / "window.lock"):
            self.assertEqual(wn.daemon_tick(self.state, ops=lambda: self.ops), "standalone")
        with mock.patch.object(wn, "utcnow", lambda: at("2026-09-29T08:00")):
            self.assertEqual(wn.daemon_tick(self.state, ops=lambda: self.ops), "running")

    def test_times_are_parsed_not_compared_as_text(self):
        self.assertEqual(wn.parse_time("2026-09-29T07:30:00Z"), wn.parse_time("2026-09-29T03:30:00.123-04:00")
                         - dt.timedelta(microseconds=123000))
        with self.assertRaises(ValueError):
            wn.parse_time("2026-09-29T07:30:00")


class FakeResult:
    def __init__(self, stdout="", ok=True):
        self.stdout, self.ok, self.output = stdout, ok, stdout

    def check(self):
        return self


class FakeApi:
    def __init__(self, receipt):
        self.receipt_text = receipt

    def exec(self, box, command, timeout=60, background=False, on_output=None):
        if isinstance(command, list) and command[0].endswith("python"):
            return FakeResult("no")  # backfill_running
        if isinstance(command, list) and command[:2] == ["bash", "-c"] and command[2].startswith("cat "):
            return FakeResult(self.receipt_text)
        return FakeResult("")


class NightlyHandle(unittest.TestCase):
    def test_a_start_the_quiet_window_defers_is_not_an_error(self):
        handle = nightly.BoxHandle(FakeApi("75"), "sb_test")
        receipt = handle.start_backfill("--stages 11 --nightly-quiet")
        self.assertTrue(receipt.startswith("/data/work/restart-") and receipt.endswith(".exit"))
        self.assertEqual(handle.receipt(receipt), 75)
        with self.assertRaisesRegex(RuntimeError, "exited with 2"):
            nightly.BoxHandle(FakeApi("2"), "sb_test").start_backfill("--stages 11")

    def test_the_daemon_hook_never_raises(self):
        with mock.patch.object(wn, "daemon_tick", side_effect=SystemExit("no data box recorded")):
            self.assertIn("SystemExit", nightly.window_hook(Path("/nonexistent")))
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(nightly.window_hook(Path(tmp)))


if __name__ == "__main__":
    unittest.main()
