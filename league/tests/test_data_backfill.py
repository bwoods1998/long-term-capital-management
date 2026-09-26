"""The backfill runner with a fake ThetaData (scripts/data/backfill.py): retries, re-authentication,
the slot limiter, resumption from the journal, and the key file's rules. No network, no polars."""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

DATA = Path(__file__).resolve().parents[2] / "scripts" / "data"
if str(DATA) not in sys.path:
    sys.path.insert(0, str(DATA))

import backfill as bf  # noqa: E402
import logging  # noqa: E402

bf.log.addHandler(logging.NullHandler())
bf.log.propagate = False
import storelib as sl  # noqa: E402


class FakeRpcError(Exception):
    def __init__(self, name):
        super().__init__(name)
        self._name = name

    def code(self):
        return type("Code", (), {"name": self._name})()


class NoDataFoundError(Exception):
    pass


class FakeClient:
    def __init__(self, script, log):
        self.script = script
        self.log = log

    def option_history_quote(self, *args, **kwargs):
        self.log.append(("quote", id(self)))
        step = self.script.pop(0) if self.script else "ok"
        if step == "ok":
            return {"rows": 1}
        if step == "nodata":
            raise NoDataFoundError("none")
        raise FakeRpcError(step)


def theta_with(script, attempts=4):
    log, made = [], []

    def factory():
        client = FakeClient(script, log)
        made.append(client)
        return client

    theta = bf.Theta(factory, bf.Limiter(2), attempts=attempts, sleep=lambda s: None)
    return theta, log, made


class ThetaCalls(unittest.TestCase):
    def test_retries_transient_errors(self):
        theta, log, _ = theta_with(["UNAVAILABLE", "RESOURCE_EXHAUSTED", "ok"])
        self.assertEqual(theta.call("option_history_quote"), {"rows": 1})
        self.assertEqual(len(log), 3)
        self.assertEqual(theta.requests, 3)

    def test_no_data_is_none_not_an_error(self):
        theta, _, _ = theta_with(["nodata"])
        self.assertIsNone(theta.call("option_history_quote"))
        theta, _, _ = theta_with(["NOT_FOUND"])
        self.assertIsNone(theta.call("option_history_quote"))

    def test_expired_session_re_authenticates_once(self):
        theta, log, made = theta_with(["UNAUTHENTICATED", "ok"])
        self.assertEqual(theta.call("option_history_quote"), {"rows": 1})
        self.assertEqual(len(made), 2)  # a new session, made once
        self.assertNotEqual(log[0][1], log[1][1])

    def test_bad_request_is_not_retried(self):
        theta, log, _ = theta_with(["INVALID_ARGUMENT", "ok"])
        with self.assertRaises(FakeRpcError):
            theta.call("option_history_quote")
        self.assertEqual(len(log), 1)

    def test_gives_up_after_the_attempts(self):
        theta, log, _ = theta_with(["UNAVAILABLE"] * 5, attempts=3)
        with self.assertRaises(FakeRpcError):
            theta.call("option_history_quote")
        self.assertEqual(len(log), 3)


class SlotLimiter(unittest.TestCase):
    def test_never_more_than_the_limit_at_once(self):
        limiter = bf.Limiter(2)
        peak, now, lock = [0], [0], threading.Lock()

        def work():
            with limiter:
                with lock:
                    now[0] += 1
                    peak[0] = max(peak[0], now[0])
                time.sleep(0.02)
                with lock:
                    now[0] -= 1

        threads = [threading.Thread(target=work) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(peak[0], 2)

    def test_the_slots_file_changes_the_limit_and_is_capped_at_four(self):
        with tempfile.TemporaryDirectory() as tmp:
            slots = Path(tmp) / "slots"
            slots.write_text("9")
            limiter = bf.Limiter(1, str(slots))
            limiter._checked = -100.0
            with limiter:
                self.assertEqual(limiter.limit, 4)
            slots.write_text("3")
            limiter._checked = -100.0
            with limiter:
                self.assertEqual(limiter.limit, 3)


class KeyFile(unittest.TestCase):
    def test_reads_the_key_and_refuses_an_open_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "thetadata.env"
            path.write_text("OTHER=1\nTHETADATA_API_KEY=abc123\n")
            path.chmod(0o600)
            self.assertEqual(bf.read_key(str(path)), "abc123")
            path.chmod(0o644)
            with self.assertRaises(SystemExit) as caught:
                bf.read_key(str(path))
            self.assertNotIn("abc123", str(caught.exception))


def calendar():
    return sl.Calendar({dt.date(2024, 1, 1): None})


class RunnerResume(unittest.TestCase):
    def test_runs_every_task_once_retries_failures_and_resumes(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = bf.Store(str(Path(tmp) / "store"), str(Path(tmp) / "work"))
            tasks = sl.plan(calendar(), stages=(1,))[:12]
            calls, failed_once = [], set()
            lock = threading.Lock()

            def task_fn(task, theta, store_, cal):
                with lock:
                    calls.append(task.id)
                    if task.id == tasks[3].id and task.id not in failed_once:
                        failed_once.add(task.id)
                        raise RuntimeError("transient")
                rel = sl.rel_path("nbbo", task.root, task.day)
                store_.journal.append(sl.file_record("nbbo", task.root, task.day, rows=1, sha256="x", size=1,
                                                     source="fake", fetched_at=sl.utc_now()))
                return {"status": "ok", "files": [rel]}

            theta = bf.Theta(lambda: object(), bf.Limiter(4), sleep=lambda s: None)
            runner = bf.Runner(tasks, theta, store, calendar(), threads=3, progress_every=0.05, task_fn=task_fn)
            original = bf.compile_store
            bf.compile_store = lambda *a, **k: {}
            try:
                self.assertEqual(runner.run(), 0)
                self.assertEqual(sorted(calls), sorted([t.id for t in tasks] + [tasks[3].id]))
                progress = json.loads((store.work / "progress.json").read_text())
                self.assertEqual(progress["stages"]["1"]["done"], 12)
                calls.clear()
                again = bf.Runner(tasks, theta, store, calendar(), threads=3, progress_every=0.05, task_fn=task_fn)
                again.run()
                self.assertEqual(calls, [])  # everything was journaled: nothing is fetched twice
            finally:
                bf.compile_store = original

    def test_a_task_that_keeps_failing_stops_after_the_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = bf.Store(str(Path(tmp) / "store"), str(Path(tmp) / "work"))
            tasks = sl.plan(calendar(), stages=(1,))[:2]
            calls = []

            def task_fn(task, *rest):
                calls.append(task.id)
                if task.id == tasks[0].id:
                    raise RuntimeError("always")
                return {"status": "empty", "why": "fake"}

            theta = bf.Theta(lambda: object(), bf.Limiter(4), sleep=lambda s: None)
            original = bf.compile_store
            bf.compile_store = lambda *a, **k: {}
            try:
                bf.Runner(tasks, theta, store, calendar(), threads=2, max_failures=3, progress_every=0.05,
                          task_fn=task_fn).run()
            finally:
                bf.compile_store = original
            self.assertEqual(calls.count(tasks[0].id), 3)
            self.assertEqual(calls.count(tasks[1].id), 1)
            errors = [r for r in store.journal.records() if r.get("status") == "error"]
            self.assertEqual(len(errors), 3)
            self.assertIn("always", errors[0]["error"])


if __name__ == "__main__":
    unittest.main()
