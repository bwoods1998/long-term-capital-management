"""The Gym store's backfill plan, windows, calendar and journal (scripts/data/storelib.py).

Standard library only: no network, no numpy, no polars.
"""

from __future__ import annotations

import datetime as dt
import sys
import tempfile
import unittest
from pathlib import Path

DATA = Path(__file__).resolve().parents[2] / "scripts" / "data"
if str(DATA) not in sys.path:
    sys.path.insert(0, str(DATA))

import storelib as sl  # noqa: E402

D = dt.date


def calendar() -> sl.Calendar:
    return sl.Calendar.from_rows([
        {"date": "2024-01-01", "type": "full_close"},
        {"date": "2024-11-28", "type": "full_close"},
        {"date": "2024-11-29", "type": "early_close", "open": "09:30:00", "close": "13:00:00"},
        {"date": "2025-01-01", "type": "full_close"},
        {"date": "2025-01-09", "type": "full_close"},
        {"date": "2026-01-01", "type": "full_close"},
    ])


class Windows(unittest.TestCase):
    def test_windows_by_date(self):
        self.assertEqual(sl.window_of(D(2022, 1, 3)), "train")
        self.assertEqual(sl.window_of(D(2024, 12, 31)), "train")
        self.assertEqual(sl.window_of(D(2025, 1, 2)), "validation")
        self.assertEqual(sl.window_of(D(2025, 12, 31)), "validation")
        self.assertEqual(sl.window_of(D(2026, 1, 2)), "holdout")
        self.assertEqual(sl.window_of(D(2026, 9, 25)), "holdout")
        self.assertEqual(sl.window_of(D(2026, 9, 28)), "forward")
        self.assertEqual(sl.window_of(D(2021, 12, 31)), "pre")

    def test_strike_range_judgement(self):
        self.assertEqual(sl.strike_range("SPY"), 25)
        self.assertGreater(sl.strike_range("SPXW"), 25)


class CalendarRules(unittest.TestCase):
    def test_weekends_holidays_and_half_days(self):
        cal = calendar()
        self.assertIsNone(cal.hours(D(2024, 11, 28)))
        self.assertEqual(cal.hours(D(2024, 11, 29)), (570, 780))
        self.assertEqual(cal.hours(D(2024, 11, 27)), (570, 960))
        self.assertIsNone(cal.hours(D(2024, 11, 30)))  # Saturday
        self.assertEqual(cal.previous(D(2024, 12, 2)), D(2024, 11, 29))
        self.assertEqual(cal.previous(D(2025, 1, 10)), D(2025, 1, 8))

    def test_json_round_trip(self):
        cal = calendar()
        again = sl.Calendar.from_json(cal.to_json())
        self.assertEqual(again.hours(D(2024, 11, 29)), (570, 780))
        self.assertFalse(again.is_trading(D(2025, 1, 9)))


class Plan(unittest.TestCase):
    def test_stage_order_and_sample_first(self):
        cal = calendar()
        first = [("SPY", D(2024, 3, 13)), ("XSP", D(2024, 3, 13)), ("SPY", D(2024, 11, 28))]
        tasks = sl.plan(cal, stages=(1, 2, 3, 5, 6), first=first)
        self.assertEqual(tasks[0].id, "day:SPY:2024-03-13")
        self.assertEqual(tasks[1].id, "day:XSP:2024-03-13")
        self.assertNotIn("day:SPY:2024-11-28", [t.id for t in tasks])  # a holiday is never planned
        stages = [t.stage for t in tasks]
        self.assertEqual(stages, sorted(stages))  # stages in the plan's order
        ids = [(t.stage, t.id) for t in tasks]
        self.assertEqual(len(ids), len(set(ids)))  # the sample is not planned twice
        stage1 = [t for t in tasks if t.stage == 1]
        self.assertTrue(all(D(2023, 1, 1) <= t.day <= D(2025, 12, 31) for t in stage1))
        self.assertEqual({t.root for t in stage1}, set(sl.CORE_FIVE))
        # within stage 1: 2024, then 2025, then 2023
        years = [t.day.year for t in stage1[len(first) - 1:]]
        self.assertEqual(years[0], 2024)
        self.assertLess(years.index(2025), years.index(2023))

    def test_a_stage_order_puts_the_calibration_samples_before_the_names(self):
        tasks = sl.plan(calendar(), stages=(1, 2, 3, 4, 5, 6), names=["AAPL"], order=(1, 2, 3, 5, 4, 6),
                        first=[("SPY", D(2024, 3, 13))])
        self.assertEqual(tasks[0].id, "day:SPY:2024-03-13")
        stages = [t.stage for t in tasks[1:]]
        runs = [s for i, s in enumerate(stages) if i == 0 or stages[i - 1] != s]
        self.assertEqual(runs, [1, 2, 3, 5, 4, 6])
        default = sl.plan(calendar(), stages=(4, 5), names=["AAPL"])
        self.assertLess(max(i for i, t in enumerate(default) if t.stage == 4), min(i for i, t in enumerate(default) if t.stage == 5))

    def test_holdout_is_its_own_stage_and_never_in_train_stages(self):
        tasks = sl.plan(calendar(), stages=(1, 2, 3))
        for task in tasks:
            if task.stage == 2:
                self.assertEqual(task.window, "holdout")
            else:
                self.assertIn(task.window, ("train", "validation"))

    def test_trade_quote_sample_is_train_one_day_in_five(self):
        cal = calendar()
        tasks = [t for t in sl.plan(cal, stages=(5,)) if t.root == "SPY"]
        train_days = cal.days(*sl.TRAIN)
        self.assertEqual(len(tasks), len(train_days[:: sl.TQ_EVERY]))
        self.assertTrue(all(t.window == "train" and t.job == "tq" for t in tasks))

    def test_names_and_back_months(self):
        tasks = sl.plan(calendar(), stages=(4, 6), names=["AAPL", "TSLA"])
        four = [t for t in tasks if t.stage == 4]
        self.assertEqual({t.root for t in four}, {"AAPL", "TSLA"})
        # Train + Validation first, then the holdout
        windows = [t.window for t in four]
        self.assertEqual(windows.index("holdout"), len(windows) - windows[::-1].index("validation"))
        six = [t for t in tasks if t.stage == 6]
        self.assertEqual({t.root for t in six}, set(sl.BACK_MONTH_ROOTS))
        self.assertTrue(all(t.job == "back" for t in six))


class RootHistory(unittest.TestCase):
    def test_meta_was_listed_as_fb_before_the_ticker_change(self):
        self.assertEqual(sl.source_root("META", D(2022, 6, 8)), "FB")
        self.assertEqual(sl.source_root("META", D(2022, 6, 9)), "META")
        self.assertEqual(sl.source_root("SPY", D(2022, 1, 3)), "SPY")

    def test_an_invalidated_task_is_pending_again(self):
        with tempfile.TemporaryDirectory() as tmp:
            journal = sl.Journal(Path(tmp) / "j.jsonl")
            task = sl.Task(4, "day", "META", D(2022, 1, 7))
            journal.append({"type": "task", "stage": 4, "task": task.id, "status": "ok"})
            self.assertEqual(sl.pending([task], journal), [])
            journal.append({"type": "task", "stage": 4, "task": task.id, "status": "invalidated"})
            self.assertEqual(sl.pending([task], journal), [task])


class Paths(unittest.TestCase):
    def test_paths_round_trip_and_refuse_junk(self):
        rel = sl.rel_path("nbbo", "SPY", D(2024, 3, 13))
        self.assertEqual(rel, "nbbo/SPY/2024-03-13.parquet")
        self.assertEqual(sl.parse_rel_path(rel), ("nbbo", "SPY", D(2024, 3, 13)))
        with self.assertRaises(ValueError):
            sl.rel_path("nbbo", "../x", D(2024, 3, 13))
        with self.assertRaises(ValueError):
            sl.rel_path("quotes", "SPY", D(2024, 3, 13))
        self.assertIsNone(sl.parse_rel_path("nbbo/SPY/notadate.parquet"))


class JournalResume(unittest.TestCase):
    def test_done_tasks_are_skipped_and_errors_retried(self):
        with tempfile.TemporaryDirectory() as tmp:
            journal = sl.Journal(Path(tmp) / "journal.jsonl")
            tasks = sl.plan(calendar(), stages=(1,), first=[("SPY", D(2024, 3, 13))])[:3]
            journal.append({"type": "task", "stage": 1, "task": tasks[0].id, "status": "ok"})
            journal.append({"type": "task", "stage": 1, "task": tasks[1].id, "status": "error"})
            journal.append({"type": "task", "stage": 1, "task": tasks[2].id, "status": "empty"})
            left = sl.pending(tasks, journal)
            self.assertEqual([t.id for t in left], [tasks[1].id])

    def test_torn_last_line_is_ignored_and_last_file_record_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "journal.jsonl"
            journal = sl.Journal(path)
            day = D(2024, 3, 13)
            journal.append(sl.file_record("nbbo", "SPY", day, rows=1, sha256="a", size=1, source="s", fetched_at="t"))
            journal.append(sl.file_record("nbbo", "SPY", day, rows=2, sha256="b", size=2, source="s", fetched_at="t"))
            with open(path, "a") as handle:
                handle.write('{"type": "file", "path": ')  # a crash mid-line
            files = journal.files()
            self.assertEqual(files["nbbo/SPY/2024-03-13.parquet"]["sha256"], "b")
            self.assertEqual(files["nbbo/SPY/2024-03-13.parquet"]["window"], "train")
            journal.append({"type": "removed", "path": "nbbo/SPY/2024-03-13.parquet"})
            self.assertEqual(journal.files(), {})

    def test_summary_counts_underlying_days_by_window(self):
        with tempfile.TemporaryDirectory() as tmp:
            journal = sl.Journal(Path(tmp) / "j.jsonl")
            cal = calendar()
            tasks = sl.plan(cal, stages=(1, 2))
            for task in tasks[:4]:
                journal.append({"type": "task", "stage": task.stage, "task": task.id, "status": "ok"})
                journal.append(sl.file_record("nbbo", task.root, task.day, rows=1, sha256="x", size=1, source="s", fetched_at="t"))
            summary = sl.summarize(tasks, journal)
            self.assertEqual(summary["stages"]["1"]["done"], 4)
            self.assertEqual(sum(summary["underlying_days"]["train"].values()), 4)
            self.assertIsNone(sl.eta_hours(10, 0))
            self.assertEqual(sl.eta_hours(10, 5), 2.0)

    def test_sha256_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x"
            path.write_bytes(b"abc")
            digest, size = sl.sha256_file(path)
            self.assertEqual(size, 3)
            self.assertEqual(digest, "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")


if __name__ == "__main__":
    unittest.main()
