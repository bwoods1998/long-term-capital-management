"""The backfill's blocks (stages 11 and up) and the nightly job's quiet window (scripts/data/storelib.py).

Standard library only: no network, no polars. The blocks here are synthetic: which roots and days the vendor serves
lives only in the private blocks file on the data box.
"""

from __future__ import annotations

import datetime as dt
import sys
import unittest
from pathlib import Path
from unittest import mock

DATA = Path(__file__).resolve().parents[2] / "scripts" / "data"
if str(DATA) not in sys.path:
    sys.path.insert(0, str(DATA))

import storelib as sl  # noqa: E402

D = dt.date
UTC = dt.timezone.utc

#: NYSE full closes 2016-2021 (the 2018-12-05 national day of mourning included) and one per later year, so
#: `Calendar.covers` holds for every year a test plans.
CLOSES = """
2016-01-01 2016-01-18 2016-02-15 2016-03-25 2016-05-30 2016-07-04 2016-09-05 2016-11-24 2016-12-26
2017-01-02 2017-01-16 2017-02-20 2017-04-14 2017-05-29 2017-07-04 2017-09-04 2017-11-23 2017-12-25
2018-01-01 2018-01-15 2018-02-19 2018-03-30 2018-05-28 2018-07-04 2018-09-03 2018-11-22 2018-12-05 2018-12-25
2019-01-01 2019-01-21 2019-02-18 2019-04-19 2019-05-27 2019-07-04 2019-09-02 2019-11-28 2019-12-25
2020-01-01 2020-01-20 2020-02-17 2020-04-10 2020-05-25 2020-07-03 2020-09-07 2020-11-26 2020-12-25
2021-01-01 2021-01-18 2021-02-15 2021-04-02 2021-05-31 2021-07-05 2021-09-06 2021-11-25 2021-12-24
2015-01-01 2022-01-17 2023-01-02 2024-01-01 2025-01-01 2026-01-01 2027-01-01
""".split()

NAMES = [f"N{i:02d}X" for i in range(20)]


def calendar(drop_year: int | None = None) -> sl.Calendar:
    return sl.Calendar({D.fromisoformat(d): None for d in CLOSES if int(d[:4]) != drop_year})


def blocks_file(**over) -> dict:
    data = {
        "schema": 1,
        "11": {"what": "core 2017-19", "job": "day", "roots": "core", "first": "2017-01-03", "last": "2019-12-31",
               "history_sessions": 60},
        "13": {"what": "names 2020-21", "job": "day", "roots": "names", "first": "2020-01-02", "last": "2021-12-31",
               "history_sessions": 60},
        "12": {"what": "back months 2017-19", "job": "back", "roots": ["SPY", "QQQ"], "first": "2017-01-03",
               "last": "2019-12-31", "after": 11},
        "16": {"what": "names 2018-19", "job": "day", "roots": "names", "first": "2018-01-02", "last": "2019-12-31",
               "skip": ["N19X"], "root_first": {name: "2018-07-02" for name in NAMES[16:19]}},
    }
    data.update(over)
    return {k: v for k, v in data.items() if v is not None}


def parsed(**over) -> dict:
    return sl.parse_blocks(blocks_file(**over), names=NAMES)


class Sessions(unittest.TestCase):
    def test_session_counts_and_history_dates(self):
        cal = calendar()
        counts = {year: len(cal.days(D(year, 1, 1), D(year, 12, 31))) for year in range(2016, 2022)}
        self.assertEqual(counts, {2016: 252, 2017: 251, 2018: 251, 2019: 252, 2020: 253, 2021: 252})
        q4_2016 = sl.history_days(cal, D(2017, 1, 3))
        self.assertEqual((q4_2016[0], q4_2016[-1], len(q4_2016)), (D(2016, 10, 6), D(2016, 12, 30), 60))
        q4_2019 = sl.history_days(cal, D(2020, 1, 2))
        self.assertEqual((q4_2019[0], q4_2019[-1]), (D(2019, 10, 7), D(2019, 12, 31)))


class BlockPlans(unittest.TestCase):
    def plan(self, stages, **kw):
        return sl.plan(calendar(), stages=stages, names=NAMES, blocks=parsed(), **kw)

    def test_counts_per_block(self):
        tasks = self.plan((11, 13, 12, 16), order=(11, 13, 12, 16))
        by = {}
        for task in tasks:
            by.setdefault((task.stage, task.job), 0)
            by[(task.stage, task.job)] += 1
        self.assertEqual(by[(11, "day")], 5 * 754)
        self.assertEqual(by[(11, "under")], 5 * 60)
        self.assertEqual(by[(13, "day")], 20 * 505)
        self.assertEqual(by[(13, "under")], 20 * 60)
        self.assertEqual(by[(12, "back")], 2 * 754)
        cal = calendar()
        late = len(cal.days(D(2018, 7, 2), D(2019, 12, 31)))
        self.assertEqual(by[(16, "day")], 16 * 503 + 3 * late)  # one skipped, three from their own first day
        self.assertNotIn((16, "under"), by)
        self.assertEqual(sum(by.values()), 4070 + 11300 + 1508 + 16 * 503 + 3 * late)

    def test_history_comes_first_and_every_block_day_is_pre(self):
        tasks = [t for t in self.plan((11,)) if t.stage == 11]
        self.assertEqual({t.job for t in tasks[:300]}, {"under"})
        self.assertEqual(min(t.day for t in tasks), D(2016, 10, 6))
        self.assertTrue(all(t.window == "pre" and t.day < sl.TRAIN[0] for t in tasks))

    def test_stage_order(self):
        tasks = self.plan((1, 2, 3, 9, 10, 11, 13, 12, 16), order=(1, 2, 3, 9, 10, 11, 13, 12, 16))
        runs = [s for i, s in enumerate(t.stage for t in tasks) if i == 0 or tasks[i - 1].stage != s]
        self.assertEqual(runs, [1, 2, 3, 9, 10, 11, 13, 12, 16])

    def test_stages_one_to_ten_are_unchanged_by_a_blocks_file(self):
        stages = (1, 2, 3, 4, 5, 6, 9, 10)
        order = (1, 2, 3, 5, 4, 6, 9, 10)
        plain = sl.plan(calendar(), stages=stages, names=NAMES, order=order)
        with_blocks = sl.plan(calendar(), stages=stages, names=NAMES, order=order, blocks=parsed())
        self.assertEqual([(t.stage, t.id) for t in plain], [(t.stage, t.id) for t in with_blocks])
        self.assertEqual(len([t for t in plain if t.stage == 9]), 2825)
        self.assertEqual(len([t for t in plain if t.stage == 10]), 1010)

    def test_calendar_years_and_the_calendar_must_cover_them(self):
        blocks = parsed()
        self.assertEqual(sl.calendar_years((11,), blocks)[:4], (2016, 2017, 2018, 2019))
        self.assertEqual(sl.calendar_years((1, 2), blocks), sl.CALENDAR_YEARS)
        with self.assertRaisesRegex(ValueError, "lacks 2016"):
            sl.plan(calendar(drop_year=2016), stages=(11,), names=NAMES, blocks=blocks)

    def test_a_planned_stage_needs_its_block(self):
        with self.assertRaisesRegex(ValueError, "no block"):
            sl.plan(calendar(), stages=(11, 14), names=NAMES, blocks=parsed())

    def test_back_months_after_their_day_block(self):
        with self.assertRaisesRegex(ValueError, "after block 11"):
            sl.plan(calendar(), stages=(11, 12), names=NAMES, blocks=parsed(), order=(12, 11))
        alone = sl.plan(calendar(), stages=(12,), names=NAMES, blocks=parsed())  # the day block already ran
        self.assertEqual(len(alone), 1508)

    def test_first_routes_a_root_day_to_its_block_and_never_past_2022(self):
        blocks = parsed()
        self.assertEqual(sl.stage_of("SPY", D(2018, 6, 13), blocks=blocks), 11)
        self.assertEqual(sl.stage_of("N00X", D(2018, 6, 13), blocks=blocks), 16)
        self.assertEqual(sl.stage_of("N00X", D(2020, 6, 15), blocks=blocks), 13)
        self.assertIsNone(sl.stage_of("N19X", D(2018, 6, 13), blocks=blocks))  # skipped
        self.assertIsNone(sl.stage_of("N16X", D(2018, 6, 13), blocks=blocks))  # before its own first day
        self.assertEqual(sl.stage_of("N16X", D(2018, 7, 2), blocks=blocks), 16)
        self.assertEqual(sl.stage_of("SPY", D(2020, 6, 15), blocks=blocks), 9)
        self.assertEqual(sl.stage_of("SPY", D(2023, 6, 14), blocks=blocks), 1)
        self.assertIsNone(sl.stage_of("SPY", D(2015, 6, 15), blocks=blocks))
        tasks = sl.plan(calendar(), stages=(11,), names=NAMES, blocks=blocks, first=[("SPY", D(2018, 2, 5))])
        self.assertEqual((tasks[0].stage, tasks[0].id), (11, "day:SPY:2018-02-05"))


class BlockRefusals(unittest.TestCase):
    def refused(self, pattern, **over):
        with self.assertRaisesRegex(ValueError, pattern):
            sl.plan(calendar(), stages=[int(k) for k in blocks_file(**over) if k != "schema"], names=NAMES,
                    blocks=sl.parse_blocks(blocks_file(**over), names=NAMES))

    def test_never_train_or_later(self):
        self.refused("before Train's first day", **{"13": {"job": "day", "roots": "names", "first": "2020-01-02",
                                                           "last": "2022-01-03"}})
        self.refused("before Train's first day", **{"13": {"job": "day", "roots": "names", "first": "2024-01-02",
                                                           "last": "2024-12-31"}})

    def test_never_the_core_roots_2020_21_chains_or_back_months(self):
        self.refused("stages 9 and 10 own", **{"11": {"job": "day", "roots": "core", "first": "2017-01-03",
                                                     "last": "2020-01-02"}})
        self.refused("stages 9 and 10 own", **{"14": {"job": "day", "roots": ["IWM"], "first": "2021-06-01",
                                                     "last": "2021-06-30"}})
        self.refused("stages 9 and 10 own", **{"11": {"job": "day", "roots": "core", "first": "2017-01-03",
                                                     "last": "2021-12-31"},
                                              "12": {"job": "back", "roots": ["SPY"], "first": "2020-01-02",
                                                     "last": "2020-03-31", "after": 11}})

    def test_two_blocks_never_plan_the_same_chain(self):
        self.refused("both plan it", **{"14": {"job": "day", "roots": ["N00X"], "first": "2019-06-03",
                                               "last": "2019-06-07"}})

    def test_a_check_per_task(self):
        for task in (sl.Task(11, "day", "SPY", D(2022, 1, 3)), sl.Task(11, "day", "SPY", D(2020, 1, 2)),
                     sl.Task(11, "back", "QQQ", D(2021, 12, 31)), sl.Task(11, "tq", "SPY", D(2018, 1, 3)),
                     sl.Task(10, "day", "SPY", D(2018, 1, 3)), sl.Task(12, "under", "SPY", D(2026, 9, 28))):
            with self.assertRaises(ValueError, msg=str(task)):
                sl.check_block_task(task)
        sl.check_block_task(sl.Task(11, "under", "SPY", D(2019, 12, 16)))  # a history session: the job keeps it
        sl.check_block_task(sl.Task(11, "day", "SPY", D(2019, 12, 16)))  # a chain stage 9 never fetched

    def test_malformed_files(self):
        bad = [
            ({"schema": 2}, "schema 1"),
            (blocks_file(**{"10": {"job": "day", "roots": "core", "first": "2017-01-03", "last": "2017-12-29"}}), "1-10"),
            (blocks_file(**{"14": {"job": "tq", "roots": "core", "first": "2017-01-03", "last": "2017-12-29"}}), "job"),
            (blocks_file(**{"14": {"job": "day", "roots": "core", "first": "2017-01-03", "last": "2017-12-29",
                                   "extra": 1}}), "unknown fields"),
            (blocks_file(**{"14": {"job": "day", "roots": "spy", "first": "2017-01-03", "last": "2017-12-29"}}), "roots"),
            (blocks_file(**{"14": {"job": "day", "roots": ["spy"], "first": "2017-01-03", "last": "2017-12-29"}}), "not a root"),
            (blocks_file(**{"14": {"job": "day", "roots": ["SPY", "SPY"], "first": "2017-01-03", "last": "2017-12-29"}}), "twice"),
            (blocks_file(**{"14": {"job": "day", "roots": ["SPY"], "first": "1017-01-03", "last": "2017-12-29"}}), "before"),
            (blocks_file(**{"14": {"job": "day", "roots": ["SPY"], "first": "2017-06-01", "last": "2017-01-03"}}), "before first"),
            (blocks_file(**{"14": {"job": "day", "roots": ["SPY"], "first": "2017-01-03", "last": "2017-12-29",
                                   "history_sessions": 61}}), "history_sessions"),
            (blocks_file(**{"14": {"job": "day", "roots": ["SPY"], "first": "2017-01-03", "last": "2017-12-29",
                                   "history_sessions": True}}), "history_sessions"),
            (blocks_file(**{"14": {"job": "day", "roots": ["SPY"], "first": "2017-01-03", "last": "2017-12-29",
                                   "root_first": {"QQQ": "2017-06-01"}}}), "not one of its roots"),
            (blocks_file(**{"14": {"job": "day", "roots": ["SPY"], "first": "2017-01-03", "last": "2017-12-29",
                                   "skip": ["QQQ"]}}), "skip"),
            (blocks_file(**{"14": {"job": "back", "roots": ["SPY"], "first": "2017-01-03", "last": "2017-12-29"}}), "after"),
            (blocks_file(**{"14": {"job": "back", "roots": ["SPY"], "first": "2017-01-03", "last": "2017-12-29",
                                   "after": 13}}), "does not fetch"),
            (blocks_file(**{"14": {"job": "back", "roots": ["SPY"], "first": "2017-01-03", "last": "2017-12-29",
                                   "after": 12}}), "not a day block"),
            (blocks_file(**{"14": {"job": "day", "roots": ["SPY"], "first": "2017-01-03", "last": "2017-12-29",
                                   "after": 11}}), "only a back block"),
        ]
        for data, pattern in bad:
            with self.assertRaisesRegex(ValueError, pattern, msg=pattern):
                sl.parse_blocks(data, names=NAMES)
        with self.assertRaisesRegex(ValueError, "no names"):
            sl.parse_blocks(blocks_file(), names=[])


class QuietWindow(unittest.TestCase):
    def at(self, text):
        return dt.datetime.fromisoformat(text).replace(tzinfo=UTC)

    def test_summer_window_with_the_runners_margin(self):
        self.assertEqual(sl.quiet_window(D(2026, 9, 29)), (self.at("2026-09-29T05:30"), self.at("2026-09-29T07:30")))
        self.assertFalse(sl.in_quiet(self.at("2026-09-29T05:24"), 300))
        self.assertTrue(sl.in_quiet(self.at("2026-09-29T05:26"), 300))
        self.assertTrue(sl.in_quiet(self.at("2026-09-29T07:29")))
        self.assertFalse(sl.in_quiet(self.at("2026-09-29T07:31")))
        self.assertFalse(sl.in_quiet(self.at("2026-09-29T13:00"), 600))

    def test_winter_window_after_the_november_change(self):
        self.assertEqual(sl.quiet_window(D(2026, 11, 2)), (self.at("2026-11-02T05:30"), self.at("2026-11-02T08:30")))
        self.assertEqual(sl.quiet_window(D(2026, 11, 1)), (self.at("2026-11-01T05:30"), self.at("2026-11-01T08:30")))
        self.assertEqual(sl.quiet_window(D(2026, 10, 31)), (self.at("2026-10-31T05:30"), self.at("2026-10-31T07:30")))
        self.assertTrue(sl.in_quiet(self.at("2026-11-03T08:29")))
        self.assertFalse(sl.in_quiet(self.at("2026-11-03T08:31")))

    def test_every_night_and_the_next_window(self):
        # Also a night with no nightly job (after a weekend day): the window is kept every night.
        self.assertTrue(sl.in_quiet(self.at("2026-10-04T06:00")))
        self.assertEqual(sl.next_quiet(self.at("2026-09-29T23:00"))[0], self.at("2026-09-30T05:30"))
        self.assertEqual(sl.next_quiet(self.at("2026-09-29T06:00"))[0], self.at("2026-09-29T05:30"))
        offset = dt.datetime(2026, 9, 29, 3, 30, tzinfo=dt.timezone(dt.timedelta(hours=-4)))  # 07:30Z
        self.assertFalse(sl.in_quiet(offset))

    def test_without_a_time_zone_database_the_widest_window(self):
        with mock.patch.dict(sys.modules, {"zoneinfo": None}):
            self.assertEqual(sl.quiet_window(D(2026, 9, 29)), (self.at("2026-09-29T05:30"), self.at("2026-09-29T08:30")))


if __name__ == "__main__":
    unittest.main()
