"""Block tasks (stage 11 and up) and the quiet window in the backfill runner (scripts/data/backfill.py), with a fake
ThetaData and a fake `frames` module: no network, no polars."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

DATA = Path(__file__).resolve().parents[2] / "scripts" / "data"
if str(DATA) not in sys.path:
    sys.path.insert(0, str(DATA))

import backfill as bf  # noqa: E402
import storelib as sl  # noqa: E402

bf.log.addHandler(logging.NullHandler())
bf.log.propagate = False

D = dt.date


class Frame:
    def __init__(self, height=3):
        self.height = height


def fake_frames() -> types.ModuleType:
    module = types.ModuleType("frames")

    def write(frame, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        blob = f"{type(frame).__name__}:{frame.height}".encode()
        path.write_bytes(blob)
        return frame.height, hashlib.sha256(blob).hexdigest(), len(blob)

    module.write = write
    module.expirations = lambda listed, day, max_dte: list(listed)
    module.underlying = lambda greeks, open_min, close_min: Frame()
    module.open_interest = lambda oi, day, max_dte: Frame()
    return module


def fake_build_nbbo(chunks, day, target, *, open_min, close_min, max_dte, min_dte=0, merge_with=None):
    path = Path(target)
    path.parent.mkdir(parents=True, exist_ok=True)
    blob = (path.read_bytes() if merge_with else b"") + f"nbbo:{max_dte}".encode()
    path.write_bytes(blob)
    return {"rows": 10, "sha256": hashlib.sha256(blob).hexdigest(), "bytes": len(blob), "stats": {}}


class FakeTheta:
    def __init__(self, *, expiries=(D(2018, 2, 9), D(2018, 2, 16), D(2018, 3, 16)), greeks=True):
        self.expiries = list(expiries)
        self.greeks = greeks
        self.calls = []

    def call(self, method, *args, **kwargs):
        self.calls.append(method)
        if method == "option_list_contracts":
            return self.expiries
        if method == "option_history_greeks_first_order":
            return object() if self.greeks else None
        if method == "option_history_open_interest":
            return object()
        raise AssertionError(method)

    def call_raw(self, method, *args, **kwargs):
        self.calls.append(method)
        return [(1, b"x")]


class BlockTasks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = bf.Store(str(Path(self.tmp.name) / "store"), str(Path(self.tmp.name) / "work"))
        patches = [mock.patch.dict(sys.modules, {"frames": fake_frames()}),
                   mock.patch.object(bf, "build_nbbo", fake_build_nbbo), mock.patch.object(bf, "LISTINGS", None)]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        self.calendar = sl.Calendar({})

    def journal_underlying(self, root, day):
        path = self.store.path("underlying", root, day)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"history")
        self.store.journal.append(sl.file_record("underlying", root, day, rows=1, sha256="h", size=7,
                                                 source="history", fetched_at=sl.utc_now()))
        return path

    def files(self):
        return set(self.store.journal.files())

    def test_a_block_day_keeps_the_journaled_underlying(self):
        day = D(2019, 12, 16)
        path = self.journal_underlying("SPY", day)
        theta = FakeTheta(expiries=[D(2019, 12, 18), D(2019, 12, 20)])
        record = bf.run_task(sl.Task(11, "day", "SPY", day), theta, self.store, self.calendar)
        self.assertEqual(record["status"], "ok")
        self.assertTrue(record["kept_underlying"])
        self.assertEqual(sorted(record["files"]), ["nbbo", "oi"])
        self.assertNotIn("option_history_greeks_first_order", theta.calls)
        self.assertEqual(path.read_bytes(), b"history")
        self.assertIn("nbbo/SPY/2019-12-16.parquet", self.files())

    def test_a_block_under_task_keeps_it_too(self):
        day = D(2019, 12, 16)
        self.journal_underlying("N00X", day)
        theta = FakeTheta()
        record = bf.run_task(sl.Task(13, "under", "N00X", day), theta, self.store, self.calendar)
        self.assertEqual((record["status"], record["files"], theta.calls), ("ok", [], []))

    def test_stage_nine_still_fetches_as_before(self):
        day = D(2019, 12, 16)
        self.journal_underlying("SPY", day)
        theta = FakeTheta(expiries=[D(2019, 12, 18)])
        bf.run_task(sl.Task(9, "under", "SPY", day), theta, self.store, self.calendar)
        self.assertIn("option_history_greeks_first_order", theta.calls)

    def test_a_block_day_without_an_underlying_keeps_nothing(self):
        day = D(2018, 2, 5)
        theta = FakeTheta(greeks=False)
        with self.assertRaises(bf.UnderlyingMissing):
            bf.run_task(sl.Task(11, "day", "SPY", day), theta, self.store, self.calendar)
        self.assertEqual(self.files(), set())
        self.assertFalse(self.store.path("nbbo", "SPY", day).exists())
        self.assertFalse(self.store.path("oi", "SPY", day).exists())
        self.assertIsNone(self.store.load_expiries("SPY", day))

    def test_stages_one_to_ten_still_journal_then_raise(self):
        day = D(2024, 3, 13)
        with self.assertRaisesRegex(RuntimeError, "underlying series is missing") as caught:
            bf.run_task(sl.Task(1, "day", "SPY", day), FakeTheta(expiries=[D(2024, 3, 15)], greeks=False),
                        self.store, self.calendar)
        self.assertNotIsInstance(caught.exception, bf.UnderlyingMissing)
        self.assertIn("nbbo/SPY/2024-03-13.parquet", self.files())

    def test_block_back_months_wait_for_a_journaled_day(self):
        day = D(2018, 2, 5)
        task = sl.Task(12, "back", "SPY", day)
        # the day's file and expiry list exist, but its task failed (never journaled ok): no merge
        self.store.save_expiries("SPY", day, [D(2018, 2, 9), D(2018, 3, 2)])
        self.store.path("nbbo", "SPY", day).parent.mkdir(parents=True, exist_ok=True)
        self.store.path("nbbo", "SPY", day).write_bytes(b"front")
        with self.assertRaisesRegex(RuntimeError, "not journaled ok"):
            bf.run_task(task, FakeTheta(), self.store, self.calendar)
        self.assertEqual(self.store.path("nbbo", "SPY", day).read_bytes(), b"front")
        # journaled ok: the back months merge
        self.store.journal.append({"type": "task", "stage": 11, "task": "day:SPY:2018-02-05", "status": "ok"})
        fresh = bf.Store(str(self.store.root), str(self.store.work))
        record = bf.run_task(task, FakeTheta(), fresh, self.calendar)
        self.assertEqual(record["status"], "ok")
        self.assertTrue(fresh.path("nbbo", "SPY", day).read_bytes().startswith(b"front"))

    def test_block_back_months_of_an_empty_day_are_empty(self):
        day = D(2018, 2, 5)
        self.store.journal.append({"type": "task", "stage": 11, "task": "day:QQQ:2018-02-05", "status": "empty"})
        record = bf.run_task(sl.Task(12, "back", "QQQ", day), FakeTheta(), self.store, self.calendar)
        self.assertEqual(record["status"], "empty")

    def test_the_day_index_follows_the_runner(self):
        day = D(2018, 2, 5)
        self.assertIsNone(self.store.day_status("SPY", day))
        self.store.note_task(11, "day:SPY:2018-02-05", "empty")
        self.assertEqual(self.store.day_status("SPY", day), "empty")
        self.store.note_task(16, "day:SPY:2018-02-05", "ok")
        self.assertEqual(self.store.day_status("SPY", day), "ok")

    def test_a_block_task_that_could_touch_stages_one_to_ten_is_refused_before_any_request(self):
        for task in (sl.Task(11, "day", "SPY", D(2022, 1, 3)), sl.Task(11, "day", "SPY", D(2020, 6, 15)),
                     sl.Task(12, "back", "SPY", D(2023, 1, 3))):
            theta = FakeTheta()
            with self.assertRaises(ValueError):
                bf.run_task(task, theta, self.store, self.calendar)
            self.assertEqual(theta.calls, [])


class RunnerRules(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = bf.Store(str(Path(self.tmp.name) / "store"), str(Path(self.tmp.name) / "work"))
        patch = mock.patch.object(bf, "compile_store", lambda *a, **k: {})
        patch.start()
        self.addCleanup(patch.stop)
        self.theta = bf.Theta(lambda: object(), bf.Limiter(4), sleep=lambda s: None)

    def test_a_block_day_the_vendor_never_completes_is_final_after_the_passes_attempts(self):
        tasks = [sl.Task(16, "day", "N00X", D(2018, 1, 3)), sl.Task(16, "day", "N00X", D(2018, 1, 4))]
        calls = []

        def task_fn(task, *rest):
            calls.append(task.id)
            if task.day == D(2018, 1, 3):
                raise bf.UnderlyingMissing("NBBO exists but the underlying series is missing")
            return {"status": "ok"}

        status = bf.Runner(tasks, self.theta, self.store, sl.Calendar({}), threads=2, progress_every=0.05,
                           task_fn=task_fn).run()
        self.assertEqual(status, 0)
        self.assertEqual(calls.count("day:N00X:2018-01-03"), 3)
        done = self.store.journal.done()["16:day:N00X:2018-01-03"]
        self.assertEqual((done["status"], done["absent"], done["why"]), ("empty", True, bf.ABSENT_WHY))
        self.assertEqual(self.store.day_status("N00X", D(2018, 1, 3)), "empty")

    def test_stages_one_to_ten_keep_retrying_a_missing_underlying(self):
        tasks = [sl.Task(1, "day", "SPY", D(2024, 3, 13))]

        def task_fn(task, *rest):
            raise bf.UnderlyingMissing("x")

        status = bf.Runner(tasks, self.theta, self.store, sl.Calendar({}), threads=1, progress_every=0.05,
                           task_fn=task_fn).run()
        self.assertEqual(status, 1)
        self.assertEqual(self.store.journal.done(), {})

    def test_a_runner_past_its_stop_time_starts_nothing_and_says_so(self):
        tasks = [sl.Task(11, "day", "SPY", D(2018, 2, day)) for day in (5, 6, 7)]
        ran = []
        runner = bf.Runner(tasks, self.theta, self.store, sl.Calendar({}), threads=2, progress_every=0.05,
                           task_fn=lambda task, *r: ran.append(task.id) or {"status": "ok"}, stop_at=0.0)
        self.assertEqual(runner.run(), sl.QUIET_EXIT)
        self.assertTrue(runner.quiet)
        self.assertEqual(ran, [])
        self.assertEqual(len(sl.pending(tasks, self.store.journal)), 3)
        progress = json.loads((self.store.work / "progress.json").read_text())
        self.assertTrue(progress["stopped_for_quiet_window"])

    def test_a_runner_stops_dispatching_when_its_stop_time_comes(self):
        tasks = [sl.Task(11, "day", "SPY", D(2018, 2, day)) for day in (5, 6, 7, 8, 9)]
        clock = [0.0]

        def task_fn(task, *rest):
            clock[0] += 1.0
            return {"status": "ok"}

        runner = bf.Runner(tasks, self.theta, self.store, sl.Calendar({}), threads=1, progress_every=0.05,
                           task_fn=task_fn, stop_at=2.0, clock=lambda: clock[0])
        self.assertEqual(runner.run(), sl.QUIET_EXIT)
        self.assertEqual(len(sl.pending(tasks, self.store.journal)), 3)


class QuietLogin(unittest.TestCase):
    def test_no_login_inside_the_window(self):
        made = []
        inside = lambda: dt.datetime(2026, 9, 29, 5, 25, tzinfo=dt.timezone.utc)  # noqa: E731 - 5 min before
        outside = lambda: dt.datetime(2026, 9, 29, 8, 0, tzinfo=dt.timezone.utc)  # noqa: E731
        with self.assertRaises(bf.QuietWindow):
            bf.quiet_guard(lambda: made.append(1), 600, clock=inside)()
        self.assertEqual(made, [])
        bf.quiet_guard(lambda: made.append(1), 600, clock=outside)()
        self.assertEqual(made, [1])

    def test_a_reauthentication_inside_the_window_is_refused(self):
        class Client:
            def option_history_quote(self):
                raise type("E", (Exception,), {"code": lambda self: type("C", (), {"name": "UNAUTHENTICATED"})()})()

        clock = [dt.datetime(2026, 9, 29, 5, 0, tzinfo=dt.timezone.utc)]
        theta = bf.Theta(bf.quiet_guard(Client, 600, clock=lambda: clock[0]), bf.Limiter(1), sleep=lambda s: None)
        clock[0] = dt.datetime(2026, 9, 29, 5, 21, tzinfo=dt.timezone.utc)
        with self.assertRaises(bf.QuietWindow):
            theta.call("option_history_quote")

    def test_the_runner_exits_75_inside_the_window_before_authenticating(self):
        with tempfile.TemporaryDirectory() as tmp:
            def never():
                raise AssertionError("logged in inside the quiet window")

            with mock.patch.object(bf, "open_client", never), mock.patch.object(bf.sl, "in_quiet", lambda *a: True):
                code = bf._main(["--store", f"{tmp}/store", "--work", f"{tmp}/work", "run", "--stages", "11",
                                 "--blocks", f"{tmp}/none.json", "--nightly-quiet"])
            self.assertEqual(code, sl.QUIET_EXIT)
            self.assertFalse(Path(tmp, "work", "backfill.pid").exists())
            for handler in list(bf.log.handlers):
                if isinstance(handler, logging.FileHandler):
                    bf.log.removeHandler(handler)
                    handler.close()

    def test_one_refuses_a_block_task_inside_the_window_and_on_a_live_day(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(bf, "open_client", lambda: (_ for _ in ()).throw(AssertionError("login"))), \
                    mock.patch.object(bf.sl, "in_quiet", lambda *a: True):
                self.assertEqual(bf._main(["--store", f"{tmp}/s", "--work", f"{tmp}/w", "one", "day:SPY:2018-02-05",
                                           "--stage", "11"]), sl.QUIET_EXIT)
                with self.assertRaises(ValueError):
                    bf._main(["--store", f"{tmp}/s", "--work", f"{tmp}/w", "one", "day:SPY:2024-03-13", "--stage", "11"])


if __name__ == "__main__":
    unittest.main()
