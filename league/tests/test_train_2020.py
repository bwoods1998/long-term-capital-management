"""The 2020-21 Train extension (Sept 27, 2026): the windows and ordinals, stages 9 and 10 (with the history sessions and
the root filter), the calendar they need, the images' prune and inside check, the Gym's 2020-21 tables, its first Train
day and per-year roots, the swarm's switch (`gym.train_from`), the running span (the store's migrated objective), the
pool's stamp and its refusal of an image on another span, the worst-year score, the objective's migration (idle counts
restarted, idempotent) and the review's probes (#399). With the switch off (the default) nothing that runs today changes:
every test below that says "default" pins that. Synthetic stores and invented results only."""

from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path

DATA = Path(__file__).resolve().parents[2] / "scripts" / "data"
if str(DATA) not in sys.path:
    sys.path.insert(0, str(DATA))

import storelib as sl  # noqa: E402

from league.gym import events as EV  # noqa: E402 - standard library only
from league.swarm import evidence  # noqa: E402
from league.swarm import settings as S  # noqa: E402
from league.swarm.pool import ROBUSTNESS_PRIORITY  # noqa: E402
from league.swarm.researcher import (CORE_SPAN, OBJECTIVE, drift_verdict, idle_dead, idle_evaluations,  # noqa: E402
                                     migrate_objective, objective_for, span_of, version_drift)
from league.tests.swarm_fakes import FakeDriver, drift_block  # noqa: E402
from league.swarm.pool import GymPool  # noqa: E402
from league.tests.test_swarm_pool import PoolCase, job, settings as pool_settings  # noqa: E402
from league.tests.test_swarm_researcher import ResearcherCase  # noqa: E402
from league.tests.test_swarm_rounds import RoundCase  # noqa: E402
from league.tests.test_swarm_search import QueueingPool, yearly  # noqa: E402

try:
    import numpy  # noqa: F401
    import pyarrow  # noqa: F401
    HAVE_GYM = True
except ImportError:  # pragma: no cover
    HAVE_GYM = False
try:
    import polars as pl
except ImportError:  # pragma: no cover
    pl = None

D = dt.date
ON = "2020-01-02"
ON_OBJECTIVE = f"{OBJECTIVE}@{ON}"


def early_calendar() -> sl.Calendar:
    """NYSE's 2019-21 full and early closes (and a few later ones), as ThetaData's calendar_year returns them."""
    rows = [{"date": d, "type": "full_close"} for d in (
        "2019-01-01", "2019-11-28", "2019-12-25", "2020-01-01", "2020-01-20", "2020-02-17", "2020-04-10", "2020-05-25",
        "2020-07-03", "2020-09-07", "2020-11-26", "2020-12-25", "2021-01-01", "2021-01-18", "2021-02-15", "2021-04-02",
        "2021-05-31", "2021-07-05", "2021-09-06", "2021-11-25", "2021-12-24", "2024-01-01", "2025-01-01", "2026-01-01")]
    rows += [{"date": d, "type": "early_close", "open": "09:30:00", "close": "13:00:00"} for d in ("2019-11-29", "2019-12-24",
                                                                                                  "2020-11-27", "2020-12-24",
                                                                                                  "2021-11-26")]
    return sl.Calendar.from_rows(rows)


def with_switch(value: object) -> dict:
    out = copy.deepcopy(S.DEFAULTS)
    if value is not None:
        out["gym"]["train_from"] = value
    return out


def five(name="five", t=(0.5, 3.0, 2.0, 2.5, 3.0), trades=(60,) * 5, train_from=None, roots=None):
    """An invented 2020-2024 Train result with the Gym's per-year block (every root had data every year)."""
    r = yearly(name)
    r["by_year"] = {str(2020 + i): {"trades": trades[i], "days": 252, "days_traded": 30, "pnl": 100.0, "t_daily": t[i],
                                    "mean_return_on_max_loss_daily": 0.01, "quarters_positive": "4/4",
                                    "quarter_pnl": {f"{2020 + i}Q{q}": 25.0 for q in range(1, 5)},
                                    "roots": list(roots or r["roots"])} for i in range(5)}
    if train_from:
        r["train_from"] = train_from
    return r


def migrated(store, span: str) -> None:
    """The store as a swarm start leaves it after migrating to `span` (the running span)."""
    store.put("train_objective", objective_for(with_switch(span)))


# ------------------------------------------------------------------------------------------------ the data box's plan
class Windows(unittest.TestCase):
    def test_default_windows_are_unchanged_and_2020_21_are_pre(self):
        for day, window in ((D(2019, 12, 31), "pre"), (D(2020, 1, 2), "pre"), (D(2021, 12, 31), "pre"), (D(2022, 1, 3), "train"),
                            (D(2024, 12, 31), "train"), (D(2025, 1, 2), "validation"), (D(2026, 1, 2), "holdout"),
                            (D(2026, 9, 28), "forward")):
            self.assertEqual(sl.window_of(day), window, day)

    def test_train_from_moves_only_trains_first_day(self):
        self.assertEqual(sl.window_of(D(2020, 1, 2), D(2020, 1, 2)), "train")
        self.assertEqual(sl.window_of(D(2021, 12, 31), D(2020, 1, 2)), "train")
        self.assertEqual(sl.window_of(D(2019, 12, 31), D(2020, 1, 2)), "pre")
        self.assertEqual(sl.window_of(D(2025, 6, 2), D(2020, 1, 2)), "validation")
        self.assertEqual(sl.window_of(D(2026, 3, 2), D(2020, 1, 2)), "holdout", "the holdout stays sealed whatever Train's start")
        for bad in (D(2019, 12, 31), D(2022, 1, 4)):
            with self.assertRaises(ValueError):
                sl.window_of(D(2023, 1, 3), bad)

    def test_calendar_years_add_2019_21_only_for_stages_9_and_10(self):
        self.assertEqual(sl.calendar_years(), (2022, 2023, 2024, 2025, 2026, 2027), "the nightly job's years, as before")
        self.assertEqual(sl.calendar_years((1, 2, 3, 4, 5, 6, 7, 8)), sl.CALENDAR_YEARS)
        self.assertEqual(sl.calendar_years((9,)), (2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026, 2027))
        self.assertEqual(sl.calendar_years((1, 10)), sl.calendar_years((9,)))

    def test_a_calendar_covers_a_year_only_with_its_closes(self):
        cal = early_calendar()
        self.assertTrue(cal.covers(2019) and cal.covers(2020) and cal.covers(2021))
        self.assertFalse(cal.covers(2018))
        self.assertFalse(sl.Calendar({D(2020, 11, 27): (570, 780)}).covers(2020), "a half day alone is not the year")


class EarlyStages(unittest.TestCase):
    def test_stage_9_is_the_history_sessions_then_the_core_five_and_stage_10_the_back_months(self):
        cal = early_calendar()
        tasks = sl.plan(cal, stages=(9, 10))
        under = [t for t in tasks if t.stage == 9 and t.job == "under"]
        nine = [t for t in tasks if t.stage == 9 and t.job == "day"]
        ten = [t for t in tasks if t.stage == 10]
        days = cal.days(*sl.EARLY)
        self.assertEqual(len(days), 253 + 252, "2020 had 253 sessions and 2021 had 252")
        history = sl.history_days(cal, sl.EARLY[0])
        self.assertEqual((len(history), history[0], history[-1]), (60, D(2019, 10, 7), D(2019, 12, 31)))
        self.assertNotIn(D(2019, 11, 28), history, "Thanksgiving 2019 is no session")
        self.assertEqual(len(under), 5 * 60)
        self.assertTrue(all(t.window == "pre" for t in under))
        self.assertEqual(len(nine), 5 * len(days))
        self.assertEqual({t.root for t in nine}, set(sl.CORE_FIVE))
        self.assertEqual(len(ten), 2 * len(days))
        self.assertEqual({t.root for t in ten}, set(sl.BACK_MONTH_ROOTS))
        self.assertTrue(all(t.job == "back" for t in ten))
        order = [(t.stage, t.job) for t in tasks]
        self.assertEqual(sorted(set(order), key=order.index), [(9, "under"), (9, "day"), (10, "back")])
        self.assertTrue(all(t.window == "pre" for t in tasks), "journaled as 'pre': no image takes them by default")
        ids = {t.id for t in nine}
        self.assertNotIn("day:SPY:2020-04-10", ids, "Good Friday is never planned")
        self.assertIn("day:SPY:2020-11-27", ids)
        self.assertEqual(cal.hours(D(2020, 11, 27)), (570, 780), "the half day keeps its 13:00 close")

    def test_early_roots_leave_a_root_out_of_both_stages(self):
        tasks = sl.plan(early_calendar(), stages=(9, 10), early=["SPY", "IWM", "SPXW"])
        self.assertEqual({t.root for t in tasks if t.stage == 9}, {"SPY", "IWM", "SPXW"})
        self.assertEqual({t.root for t in tasks if t.stage == 10}, {"SPY"}, "QQQ's back months go with QQQ")
        with self.assertRaises(ValueError):
            sl.plan(early_calendar(), stages=(9,), early=["AAPL"])

    def test_the_early_stages_come_after_the_existing_ones_and_leave_them_as_they_were(self):
        cal = early_calendar()
        before = sl.plan(cal, stages=(1, 2, 3, 4, 5, 6), names=["AAPL"], order=(1, 2, 3, 5, 4, 6))
        both = sl.plan(cal, stages=(1, 2, 3, 4, 5, 6, 9, 10), names=["AAPL"], order=(1, 2, 3, 5, 4, 6))
        self.assertEqual([(t.stage, t.id) for t in both[:len(before)]], [(t.stage, t.id) for t in before])
        self.assertEqual({t.stage for t in both[len(before):]}, {9, 10})
        self.assertTrue(all(t.day >= sl.TRAIN[0] for t in before), "stages 1-6 never reach before 2022-01-03")
        self.assertFalse(any(t.root == "AAPL" for t in both if t.stage in (9, 10)), "the names are not part of stages 9-10")

    def test_the_early_stages_refuse_a_calendar_without_2019_21(self):
        with self.assertRaises(ValueError) as caught:
            sl.plan(sl.Calendar({D(2024, 1, 1): None}), stages=(9,))
        self.assertIn("2019, 2020, 2021", str(caught.exception))
        self.assertEqual(sl.plan(sl.Calendar({}), stages=(1,))[0].stage, 1, "the other stages never ask for 2019-21")

    def test_stage_of_puts_an_early_core_day_in_stage_9_and_no_name_day_anywhere(self):
        self.assertEqual(sl.stage_of("SPY", D(2020, 3, 16)), 9)
        self.assertEqual(sl.stage_of("SPXW", D(2021, 12, 31)), 9)
        self.assertIsNone(sl.stage_of("AAPL", D(2020, 3, 16)))
        self.assertEqual(sl.stage_of("SPY", D(2022, 6, 1)), 3)
        tasks = sl.plan(early_calendar(), stages=(9,), first=[("QQQ", D(2020, 3, 16))])
        self.assertEqual(tasks[0].id, "day:QQQ:2020-03-16")

    def test_stage_of_and_first_honour_early_roots(self):
        self.assertIsNone(sl.stage_of("XSP", D(2020, 3, 16), early=["SPY", "QQQ"]))
        self.assertEqual(sl.stage_of("SPY", D(2020, 3, 16), early=["SPY", "QQQ"]), 9)
        self.assertEqual(sl.stage_of("XSP", D(2024, 3, 13), early=["SPY"]), 1, "2022 on: the early roots change nothing")
        tasks = sl.plan(early_calendar(), stages=(9,), early=["SPY"], first=[("XSP", D(2020, 3, 16)), ("SPY", D(2020, 3, 17))])
        self.assertEqual(tasks[0].id, "day:SPY:2020-03-17")
        self.assertNotIn("XSP", {t.root for t in tasks})


@unittest.skipIf(pl is None, "polars/pyarrow are not installed here (they are on the data box)")
class Backfill(unittest.TestCase):
    def store(self, tmp):
        import backfill as bf

        return bf, bf.Store(root=f"{tmp}/store", work=f"{tmp}/work")

    def test_a_narrower_calendar_request_never_drops_a_cached_year(self):
        """The review's probe (CalendarShrink): `one` on another year's day refetches the union, not its own years."""
        class Client:
            def __init__(self):
                self.calls = []

            def call(self, method, year):
                self.calls.append(int(year))
                y = int(year)
                return pl.DataFrame([{"date": f"{y}-01-01", "type": "full_close"},
                                     {"date": f"{y}-11-2{6 if y == 2021 else 7}", "type": "early_close", "open": "09:30:00",
                                      "close": "13:00:00"}])

        with tempfile.TemporaryDirectory() as tmp:
            _, store = self.store(tmp)
            client = Client()
            store.calendar(client, years=sl.calendar_years([9]))
            cal = store.calendar(client, years=sorted(set(sl.CALENDAR_YEARS) | {2018}))
            cached = json.loads((Path(tmp) / "work" / "calendar.json").read_text())
            self.assertEqual(cached["years"], [str(y) for y in range(2018, 2028)])
            self.assertTrue(cal.covers(2020) and cal.covers(2021))
            self.assertEqual(store.calendar(None).hours(D(2020, 11, 27)), (570, 780))
            before = len(client.calls)
            store.calendar(client, years=sl.CALENDAR_YEARS)
            self.assertEqual(len(client.calls), before, "the nightly job's years are cached: no refetch")

    def test_the_under_job_writes_the_underlying_alone(self):
        import backfill as bf

        class Theta:
            def call(self, method, *args, **kw):
                if method == "option_list_contracts":
                    return pl.DataFrame({"expiration": ["2019-12-20", "2019-12-27"], "strike": [320.0, 320.0], "right": ["C", "C"],
                                         "symbol": ["SPY", "SPY"]})
                if method == "option_history_greeks_first_order":
                    return pl.DataFrame({"timestamp": [dt.datetime(2019, 12, 16, 9, 31), dt.datetime(2019, 12, 16, 9, 32)],
                                         "underlying_price": [320.0, 320.5]})
                raise AssertionError(method)

        with tempfile.TemporaryDirectory() as tmp:
            _, store = self.store(tmp)
            out = bf.run_task(sl.Task(9, "under", "SPY", D(2019, 12, 16)), Theta(), store, early_calendar())
            self.assertEqual((out["status"], out["files"]), ("ok", ["underlying"]))
            self.assertTrue(store.path("underlying", "SPY", D(2019, 12, 16)).exists())
            self.assertFalse(store.path("nbbo", "SPY", D(2019, 12, 16)).exists())
            [record] = store.journal.files().values()
            self.assertEqual((record["kind"], record["window"]), ("underlying", "pre"))

    def test_a_back_month_task_on_a_day_the_chain_task_found_empty_is_empty_not_failing(self):
        import backfill as bf

        with tempfile.TemporaryDirectory() as tmp:
            _, store = self.store(tmp)
            task = sl.Task(10, "back", "QQQ", D(2020, 3, 16))
            with self.assertRaises(RuntimeError):
                bf.run_task(task, None, store, early_calendar())  # the day task has not run yet: wait for it
            store.journal.append({"type": "task", "stage": 9, "task": "day:QQQ:2020-03-16", "status": "empty"})
            self.assertEqual(bf.run_task(task, None, store, early_calendar())["status"], "empty")


@unittest.skipIf(pl is None, "polars/pyarrow are not installed here (they are on the data box)")
class ImagesPrune(unittest.TestCase):
    CHAINS = (D(2020, 3, 16), D(2021, 6, 1), D(2024, 3, 13), D(2025, 6, 11), D(2026, 3, 11), D(2026, 9, 28))
    HISTORY = (D(2019, 10, 4), D(2019, 12, 16))   # before the 60 sessions, and inside them

    def build(self, tmp, roots=("SPY",)):
        import backfill as bf
        import frames as fr

        store = bf.Store(str(Path(tmp) / "store"), str(Path(tmp) / "work"))
        store.work.mkdir(parents=True, exist_ok=True)
        cal = early_calendar()
        (store.work / "calendar.json").write_text(json.dumps({"years": [str(y) for y in sl.calendar_years((9,))],
                                                              "exceptions": cal.to_json()}))
        frame = pl.DataFrame({"expiration": [D(2024, 3, 13)], "strike": [500.0], "right": ["C"], "minute": [600],
                              "bid": [1.0], "ask": [1.1], "bid_size": [5], "ask_size": [5]}, schema=fr.NBBO_SCHEMA)
        under = pl.DataFrame({"minute": [600], "price": [300.0]}, schema=fr.UNDERLYING_SCHEMA)

        def put(kind, root, day, data):
            rows, digest, size = fr.write(data, store.path(kind, root, day))
            store.journal.append(sl.file_record(kind, root, day, rows=rows, sha256=digest, size=size, source="t",
                                                fetched_at="2026-09-27T00:00:00Z"))

        for root in roots:
            for day in self.CHAINS:
                put("nbbo", root, day, frame)
                put("underlying", root, day, under)
                store.save_expiries(root, day, [day])
            for day in self.HISTORY:
                put("underlying", root, day, under)
        return bf, store, cal

    def names(self, store, kind="nbbo"):
        return sorted(f"{p.parent.name}/{p.stem}" for p in store.root.glob(f"{kind}/*/*.parquet"))

    def test_the_journal_labels_the_early_days_pre_and_the_data_box_keeps_them(self):
        with tempfile.TemporaryDirectory() as tmp:
            bf, store, cal = self.build(tmp)
            labels = {(r["kind"], r["date"]): r["window"] for r in store.journal.files().values()}
            self.assertEqual((labels[("nbbo", "2020-03-16")], labels[("underlying", "2019-12-16")]), ("pre", "pre"))
            bf.compile_store(store, cal)  # the data box's own compile (every run ends with it)
            self.assertEqual(pl.read_parquet(store.root / "manifest.parquet").height, 2 * len(self.CHAINS) + 2)

    def test_a_default_gym_prune_drops_2019_21_exactly_as_before(self):
        with tempfile.TemporaryDirectory() as tmp:
            bf, store, cal = self.build(tmp)
            bf.prune(store, ["train", "validation"], drop_key=False, drop_work=False, calendar=cal)
            self.assertEqual(self.names(store), ["SPY/2024-03-13", "SPY/2025-06-11"])
            self.assertEqual(self.names(store, "underlying"), ["SPY/2024-03-13", "SPY/2025-06-11"])
            manifest = pl.read_parquet(store.root / "manifest.parquet")
            self.assertEqual(sorted(set(manifest["window"].to_list())), ["train", "validation"])
            calendar = pl.read_parquet(store.root / "calendar.parquet")
            self.assertEqual(calendar["date"].min(), sl.TRAIN[0], "the calendar starts 2022-01-03, as every image's did")

    def test_train_from_keeps_2020_21_as_train_and_the_60_sessions_before_as_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            bf, store, cal = self.build(tmp)
            bf.prune(store, ["train", "validation"], drop_key=False, drop_work=False, calendar=cal, train_from=D(2020, 1, 2))
            self.assertEqual(self.names(store), ["SPY/2020-03-16", "SPY/2021-06-01", "SPY/2024-03-13", "SPY/2025-06-11"])
            self.assertEqual(self.names(store, "underlying")[:2], ["SPY/2019-12-16", "SPY/2020-03-16"],
                             "the history session stays, the one before the 60 goes")
            manifest = pl.read_parquet(store.root / "manifest.parquet").sort(["date", "kind"])
            history = manifest.filter(pl.col("window") == "history")
            self.assertEqual((history["kind"].to_list(), history["date"].to_list()), (["underlying"], [D(2019, 12, 16)]))
            self.assertEqual(sorted(set(manifest["window"].to_list())), ["history", "train", "validation"])
            calendar = pl.read_parquet(store.root / "calendar.parquet")["date"].to_list()
            self.assertEqual(calendar[0], D(2019, 12, 16), "the history sessions are sessions (the Gym reads them as history)")
            self.assertIn(D(2019, 12, 31), calendar)
            self.assertNotIn(D(2020, 4, 10), calendar, "Good Friday 2020 is no session")
            self.assertLessEqual(max(calendar), D(2025, 12, 31))

    def test_early_roots_keep_only_those_roots_2020_21_days(self):
        with tempfile.TemporaryDirectory() as tmp:
            bf, store, cal = self.build(tmp, roots=("SPY", "XSP"))
            bf.prune(store, ["train", "validation"], drop_key=False, drop_work=False, calendar=cal, train_from=D(2020, 1, 2),
                     early_roots=["SPY"])
            self.assertEqual(self.names(store), ["SPY/2020-03-16", "SPY/2021-06-01", "SPY/2024-03-13", "SPY/2025-06-11",
                                                 "XSP/2024-03-13", "XSP/2025-06-11"])
            expiries = pl.read_parquet(store.root / "expiries.parquet")
            self.assertEqual(expiries.filter(pl.col("root") == "XSP")["date"].min(), D(2024, 3, 13))

    def test_the_gate_never_takes_2019_21_and_its_journal_never_lists_them(self):
        with tempfile.TemporaryDirectory() as tmp:
            bf, store, cal = self.build(tmp)
            bf.prune(store, ["train", "validation", "holdout", "forward"], drop_key=False, drop_work=False, calendar=cal,
                     keep_journal=True)
            self.assertTrue(all(r["date"] >= "2022-01-03" for r in store.journal.files().values()))
            self.assertFalse(store.path("nbbo", "SPY", D(2020, 3, 16)).exists())

    def test_the_inside_check_holds_each_image_to_its_first_day(self):
        import images

        facts = {"network": ["NETWORK-CLOSED x OSError"], "key_file": False, "key_mentions": [], "store_non_parquet": [],
                 "processes": "", "dated_after_validation": 0, "manifest_windows": ["train", "validation"],
                 "manifest_last": "2025-12-31", "calendar_last": "2025-12-31", "expiries_last_date": "2025-12-31",
                 "work_exists": False, "gate_mark": False, "first_date": "2022-01-03", "manifest_first": "2022-01-03",
                 "calendar_first": "2022-01-03", "first_by_kind": {"nbbo": "2022-01-03", "underlying": "2022-01-03"},
                 "history_kinds": []}
        self.assertEqual(images.problems_of(facts, "gym"), [], "today's images pass as before")
        early = {**facts, "first_date": "2019-10-07", "manifest_first": "2019-10-07", "calendar_first": "2019-10-07",
                 "first_by_kind": {"nbbo": "2020-01-02", "oi": "2020-01-02", "underlying": "2019-10-07"},
                 "manifest_windows": ["history", "train", "validation"], "history_kinds": ["underlying"]}
        self.assertGreaterEqual(len(images.problems_of(early, "gym")), 4, "2019-21 in a Gym image built without the switch")
        self.assertEqual(images.problems_of(early, "gym", train_from=ON), [])
        chain_before = {**early, "first_by_kind": {**early["first_by_kind"], "nbbo": "2019-12-16"}}
        self.assertTrue(any("first nbbo" in p for p in images.problems_of(chain_before, "gym", train_from=ON)))
        oi_history = {**early, "history_kinds": ["oi", "underlying"]}
        self.assertTrue(any("underlying only" in p for p in images.problems_of(oi_history, "gym", train_from=ON)))
        too_far = {**early, "first_by_kind": {**early["first_by_kind"], "underlying": "2019-06-03"}}
        self.assertTrue(images.problems_of(too_far, "gym", train_from=ON))
        gate = {**early, "gate_mark": True, "manifest_windows": ["train", "validation", "holdout", "forward"]}
        self.assertTrue(any("never carries" in p for p in images.problems_of(gate, "gate")))
        with self.assertRaises(SystemExit):
            images.build("gate", version="t", force=True, train_from=D(2020, 1, 2))
        with self.assertRaises(SystemExit):
            images.build("gym", version="t", force=True, early_roots=("SPY",))


# ------------------------------------------------------------------------------------------------ the Gym
@unittest.skipUnless(HAVE_GYM, "numpy/pyarrow not installed (requirements-gym.txt)")
class GymWindows(unittest.TestCase):
    def test_train_reaches_2020_and_nothing_else_moves(self):
        from league.gym import day as G

        self.assertEqual(G.WINDOWS["train"], (D(2020, 1, 2), D(2024, 12, 31)))
        for day, window in ((D(2019, 12, 31), "pre"), (D(2020, 1, 1), "pre"), (D(2020, 1, 2), "train"), (D(2021, 12, 31), "train"),
                            (D(2022, 1, 3), "train"), (D(2025, 1, 1), "gap"), (D(2025, 1, 2), "validation"),
                            (D(2026, 1, 2), "holdout"), (D(2026, 9, 25), "holdout"), (D(2026, 9, 26), "forward")):
            self.assertEqual(G.window_of(day), window, day)
        self.assertEqual(G.SEALED, ("holdout", "forward"))

    def test_ordinals_and_contract_keys_count_from_1970_not_from_a_window(self):
        from league.gym import day as G

        self.assertEqual(G.EPOCH, D(1970, 1, 1))
        self.assertEqual((G.ordinal(D(2020, 1, 2)), G.ordinal(D(2022, 1, 3)), G.ordinal(D(2026, 9, 25))), (18263, 18995, 20721))
        for day in (D(2019, 10, 7), D(2020, 1, 2), D(2020, 3, 16), D(2021, 12, 31), D(2024, 2, 29)):
            self.assertEqual(G.from_ordinal(G.ordinal(day)), day)
        key = G.contract_key([18995], [450.5], [False])
        self.assertEqual(int(key[0]), (18995 * 100_000_000 + 450_500) * 2 + 1)
        early, late = G.contract_key([18263, 18995], [300.0, 300.0], [True, True])
        self.assertLess(int(early), int(late), "an early expiry still sorts first")

    def test_the_swarm_the_data_box_and_the_gym_agree_on_the_dates(self):
        from league.gym import day as G

        self.assertEqual(S.TRAIN_EARLIEST, G.WINDOWS["train"][0])
        self.assertEqual(S.TRAIN_END, G.WINDOWS["train"][1])
        self.assertEqual(S.TRAIN_CORE_START, G.TRAIN_CORE_START)
        self.assertEqual((sl.TRAIN_EARLIEST, sl.TRAIN[0], sl.TRAIN[1]), (S.TRAIN_EARLIEST, S.TRAIN_CORE_START, S.TRAIN_END))
        self.assertEqual(sorted(S.TRAIN_STARTS.values()), [sl.TRAIN_EARLIEST, sl.TRAIN[0]])
        day = D(2019, 9, 20)
        while day <= D(2026, 10, 5):
            self.assertEqual(sl.window_of(day, sl.TRAIN_EARLIEST), G.window_of(day), day)
            day += dt.timedelta(days=1)


class Tables(unittest.TestCase):
    def test_2022_on_is_exactly_the_table_before_the_extension(self):
        cut = D(2022, 1, 1)
        body = {"fomc": sorted(d.isoformat() for d in EV.FOMC if d >= cut), "cpi": sorted(d.isoformat() for d in EV.CPI if d >= cut),
                "jobs": sorted(d.isoformat() for d in EV.JOBS if d >= cut),
                "rates": [[d.isoformat(), r] for d, r in EV.RATES if d >= D(2021, 1, 1)]}
        self.assertEqual(hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()[:16], "a8e5a456404e23eb")
        self.assertAlmostEqual(EV.rate_on(D(2022, 6, 1)), 0.009)

    def test_2020_21_events_and_rates(self):
        self.assertEqual(sum(d.year == 2020 for d in EV.FOMC), 7, "scheduled meetings only: March 17-18 was cancelled")
        self.assertEqual(sum(d.year == 2021 for d in EV.FOMC), 8)
        for day in (D(2020, 3, 3), D(2020, 3, 16), D(2020, 3, 18)):
            self.assertNotIn(day, EV.FOMC, "an unscheduled or cancelled meeting is never a flag (events_next would leak it)")
        self.assertIn(D(2020, 6, 10), EV.FOMC)
        self.assertEqual((sum(d.year == 2020 for d in EV.CPI), sum(d.year == 2021 for d in EV.CPI)), (12, 12))
        self.assertEqual((sum(d.year == 2020 for d in EV.JOBS), sum(d.year == 2021 for d in EV.JOBS)), (12, 12))
        self.assertIn(D(2020, 7, 2), EV.JOBS)
        self.assertIn(D(2021, 11, 10), EV.CPI)
        self.assertAlmostEqual(EV.rate_on(D(2019, 11, 15)), 0.0165, msg="the history sessions' rate")
        self.assertAlmostEqual(EV.rate_on(D(2020, 1, 15)), 0.0165)
        self.assertAlmostEqual(EV.rate_on(D(2020, 3, 10)), 0.0115)
        self.assertAlmostEqual(EV.rate_on(D(2020, 3, 16)), 0.0015)
        self.assertAlmostEqual(EV.rate_on(D(2021, 7, 1)), 0.0015)


@unittest.skipUnless(HAVE_GYM, "numpy/pyarrow not installed (requirements-gym.txt)")
class GymRuns(unittest.TestCase):
    SPY = "import math\nimport numpy as np\nNEEDS = {'roots': ['SPY']}\nPARAMS = {}\ndef decide(ctx):\n    return []\n"
    POOLED = "import math\nimport numpy as np\nNEEDS = {'roots': ['SPY', 'QQQ']}\nPARAMS = {}\ndef decide(ctx):\n    return []\n"
    DAYS = (D(2021, 12, 28), D(2021, 12, 29), D(2021, 12, 30), D(2021, 12, 31), D(2022, 1, 3), D(2022, 1, 4), D(2022, 1, 5))

    def setUp(self):
        from league.gym import synth

        self.dir = tempfile.mkdtemp(prefix="train2020-")
        synth.generate(self.dir, roots=("SPY", "QQQ"), days=list(self.DAYS), strikes_each_side=2, max_dte=2)
        for day in self.DAYS[1:4]:  # QQQ has one 2021 chain of four here (a root with stray early sessions, or a name)
            (Path(self.dir) / "nbbo" / "QQQ" / f"{day.isoformat()}.parquet").unlink()

    def tearDown(self):
        import shutil

        shutil.rmtree(self.dir, ignore_errors=True)

    def run_batch(self, code, roots, **kw):
        from league.gym import batch

        return batch.run_batch([("p", code, {})], store_root=self.dir, window="train", roots=roots, workers=1, **kw)

    def test_a_store_that_holds_2021_reports_it_and_the_switchs_start_cuts_it(self):
        from league.gym.store import Store, describe

        store = Store(self.dir)
        self.assertEqual(len(store.days("train", ["SPY"])), 7)
        self.assertEqual(store.train_first(), D(2021, 12, 28))
        self.assertEqual(describe(store, "train", ["SPY"])["train_first"], "2021-12-28")
        whole = self.run_batch(self.SPY, ["SPY"], split=2)
        self.assertEqual((whole["batch"]["first_day"], whole["batch"]["days"], whole["batch"]["train_first"]),
                         ("2021-12-28", 7, "2021-12-28"))
        self.assertEqual(sorted(whole["results"][0]["by_year"]), ["2021", "2022"])
        cut = self.run_batch(self.SPY, ["SPY"], split=2, start=S.TRAIN_CORE_START)
        self.assertEqual((cut["batch"]["first_day"], cut["batch"]["days"]), ("2022-01-03", 3))
        self.assertEqual(sorted(cut["results"][0]["by_year"]), ["2022"])
        self.assertEqual(sorted(evidence.train_score(whole["results"][0], first_year=2022)["years"]), ["2022"])
        self.assertEqual(sorted(evidence.train_score(whole["results"][0])["years"]), ["2021", "2022"])

    def test_a_year_counts_only_when_every_root_had_data_on_half_its_days(self):
        pooled = self.run_batch(self.POOLED, ["SPY", "QQQ"], split=2)["results"][0]
        self.assertEqual(pooled["by_year"]["2021"]["root_days"], {"QQQ": 1, "SPY": 4})
        self.assertEqual(pooled["by_year"]["2021"]["roots"], ["SPY"], "one stray session of four is not a 2021 root")
        self.assertEqual(pooled["by_year"]["2022"]["roots"], ["QQQ", "SPY"])
        whole = self.run_batch(self.POOLED, ["SPY", "QQQ"], split=1)["results"][0]
        self.assertEqual(whole["by_year"]["2021"]["root_days"], pooled["by_year"]["2021"]["root_days"], "a split run merges exactly")
        self.assertEqual(sorted(evidence.train_score(pooled)["years"]), ["2022"], "2021 would score SPY alone")
        alone = self.run_batch(self.SPY, ["SPY", "QQQ"])["results"][0]
        self.assertEqual(sorted(evidence.train_score(alone)["years"]), ["2021", "2022"], "SPY had every year")

    def test_the_drift_block_carries_its_roots_their_days_and_its_sums(self):
        split = self.run_batch(self.POOLED, ["SPY", "QQQ"], split=2)["results"][0]["drift"]
        whole = self.run_batch(self.POOLED, ["SPY", "QQQ"], split=1)["results"][0]["drift"]
        self.assertEqual(split["roots"], ["QQQ", "SPY"])
        for block in (split, whole):
            # A day's return needs the prior close: QQQ's one 2021 session (the first day) has none.
            self.assertEqual((block["years"]["2021"]["days"], block["years"]["2021"]["root_days"]), (3, {"SPY": 3}))
            self.assertEqual(block["years"]["2022"]["root_days"], {"QQQ": 3, "SPY": 3})
            self.assertTrue(all({"sum_sq", "sum_pp"} <= set(row) for row in block["years"].values()))
        self.assertEqual(split["years"], whole["years"], "a split run merges exactly")
        numbers = evidence.drift_numbers(split)
        self.assertEqual((numbers["roots"], numbers["years"]["2021"]["root_days"]), (["QQQ", "SPY"], {"SPY": 3}))
        kept, left = evidence.drift_years(numbers, 2020)
        self.assertEqual((sorted(kept), left), (["2022"], ["2021"]))


# ------------------------------------------------------------------------------------------------ the swarm's switch
class Switch(unittest.TestCase):
    def test_unset_is_2022_a_start_is_taken_a_near_miss_snaps_and_the_rest_is_named(self):
        self.assertIsNone(S.DEFAULTS["gym"]["train_from"], "unset: the running span stays")
        self.assertEqual((S.train_from(S.DEFAULTS), S.train_from_note(S.DEFAULTS)), (D(2022, 1, 3), None))
        self.assertEqual((S.train_from(with_switch(ON)), S.train_from_note(with_switch(ON))), (D(2020, 1, 2), None))
        self.assertEqual(S.train_from(with_switch("2020-01-01")), D(2020, 1, 2))
        self.assertIn("first session", S.train_from_note(with_switch("2020-01-01")))
        for bad in ("2019-12-31", "2021-01-04", "2020-06-01", "yes", "", 7):
            self.assertEqual(S.train_from(with_switch(bad)), D(2022, 1, 3), bad)
            self.assertIn("ignored", S.train_from_note(with_switch(bad)), bad)
        self.assertEqual(S.train_from(None), D(2022, 1, 3))

    def test_a_typo_or_a_deleted_key_while_on_keeps_the_running_span(self):
        on = D(2020, 1, 2)
        for bad in ("2020-1-2", "2022-01-04", "yes"):
            self.assertEqual(S.train_from(with_switch(bad), on), on, bad)
            self.assertIn("keeps Train from 2020-01-02", S.train_from_note(with_switch(bad), on))
        self.assertEqual((S.train_from(S.DEFAULTS, on), S.train_from_note(S.DEFAULTS, on)[:26]), (on, "gym.train_from is not set:"))
        self.assertEqual((S.train_from(with_switch("2022-01-03"), on), S.train_from_note(with_switch("2022-01-03"), on)),
                         (D(2022, 1, 3), None), "switching back is written out")
        self.assertEqual(S.train_years(S.DEFAULTS), (2022, 2023, 2024))
        self.assertEqual(S.train_years(with_switch(ON)), (2020, 2021, 2022, 2023, 2024))

    def test_the_running_span_is_the_stores_migrated_objective(self):
        self.assertEqual(S.objective_span(None), D(2022, 1, 3))
        self.assertEqual(S.objective_span(OBJECTIVE), D(2022, 1, 3))
        self.assertEqual(S.objective_span(ON_OBJECTIVE), D(2020, 1, 2))
        self.assertEqual(S.objective_span(f"{OBJECTIVE}@2020-06-01"), D(2022, 1, 3), "never a span the Gym has no image for")
        self.assertEqual(objective_for(S.DEFAULTS), OBJECTIVE)
        self.assertEqual(objective_for(with_switch(ON)), ON_OBJECTIVE)
        self.assertEqual(objective_for(with_switch("typo"), D(2020, 1, 2)), ON_OBJECTIVE, "a typo while on keeps the span")
        self.assertEqual(objective_for(S.DEFAULTS, D(2020, 1, 2)), ON_OBJECTIVE, "a deleted key while on keeps the span")
        self.assertEqual((span_of({}), span_of(None), span_of({"train_from": ON})), (CORE_SPAN, CORE_SPAN, ON))

    def test_the_split_and_time_limit_follow_the_span_unless_the_operator_sets_them(self):
        self.assertEqual((S.train_split(S.DEFAULTS), S.run_timeout(S.DEFAULTS)), (8, 900.0), "the defaults as before")
        self.assertEqual((S.train_split(S.DEFAULTS, D(2020, 1, 2)), S.run_timeout(S.DEFAULTS, D(2020, 1, 2))), (16, 1500.0))
        mine = copy.deepcopy(S.DEFAULTS)
        mine["gym"].update(train_split=12, run_timeout_seconds=1200)
        self.assertEqual((S.train_split(mine, D(2020, 1, 2)), S.run_timeout(mine, D(2020, 1, 2))), (12, 1200.0))

    def test_swarm_json_asks_for_it_without_a_deploy(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(S.train_from(S.load(tmp, config={})), D(2022, 1, 3))
            (Path(tmp) / "swarm.json").write_text(json.dumps({"gym": {"train_from": ON}}))
            self.assertEqual(S.train_from(S.load(tmp, config={})), D(2020, 1, 2))
            (Path(tmp) / "swarm.json").write_text(json.dumps({"gym": {}}))  # the key deleted
            self.assertEqual(S.train_from(S.load(tmp, config={}), D(2020, 1, 2)), D(2020, 1, 2))

    def test_the_prompts_name_the_span_and_are_the_same_string_while_2022(self):
        from league.swarm.architect import SYSTEM as ARCHITECT
        from league.swarm.diagnostician import SYSTEM as DIAGNOSTICIAN
        from league.swarm.researcher import CONTRACT

        contract = CONTRACT.read_text(encoding="utf-8")
        for text in (ARCHITECT, DIAGNOSTICIAN, contract):
            self.assertIs(S.train_span_text(text, D(2022, 1, 3)), text)
            self.assertNotIn("2022-2024", S.train_span_text(text, D(2020, 1, 2)))
        on = S.train_span_text(ARCHITECT, D(2020, 1, 2))
        self.assertIn("Train 2020-2024", on)
        self.assertIn("earn in 2020, 2021, 2022, 2023 and 2024 alike", on)
        self.assertIn("Train (2020-2024) is yours", S.train_span_text(contract, D(2020, 1, 2)))


class Notice(unittest.TestCase):
    def swarm(self, tmp):
        from league.swarm.store import SwarmStore

        store = SwarmStore(Path(tmp))
        self.addCleanup(store.close)
        clock = types.SimpleNamespace(t=1_000_000.0)
        return types.SimpleNamespace(store=store, settings=copy.deepcopy(S.DEFAULTS), clock=lambda: clock.t, span_alert=None), clock

    def notice(self, swarm):
        from league.swarm.loop import Swarm

        return Swarm.train_span_notice(swarm)

    def test_the_loop_names_a_pending_switch_and_repeats_until_it_is_resolved(self):
        from league.swarm.loop import TRAIN_SPAN_NOTICE_EVERY

        with tempfile.TemporaryDirectory() as tmp:
            swarm, clock = self.swarm(tmp)
            self.assertIsNone(self.notice(swarm), "off, and nothing asked: silent")
            self.assertIsNone(swarm.span_alert)
            swarm.settings["gym"]["train_from"] = ON
            first = self.notice(swarm)
            self.assertEqual((first["action"], first["wanted"], first["running"], first["alert"]),
                             ("train_span_pending", ON, "2022-01-03", True))
            self.assertIsNone(self.notice(swarm), "not every loop as an event")
            self.assertEqual(swarm.span_alert["action"], "train_span_pending", "but in every loop's heartbeat")
            clock.t += TRAIN_SPAN_NOTICE_EVERY
            self.assertIsNotNone(self.notice(swarm), "and again while it stands")
            migrated(swarm.store, ON)
            self.assertIsNone(self.notice(swarm), "migrated: nothing pending")
            self.assertIsNone(swarm.span_alert)

    def test_a_typo_or_a_deleted_key_while_on_alerts_and_keeps_the_span(self):
        from league.swarm.loop import TRAIN_SPAN_NOTICE_EVERY

        with tempfile.TemporaryDirectory() as tmp:
            swarm, clock = self.swarm(tmp)
            migrated(swarm.store, ON)
            swarm.settings["gym"]["train_from"] = "2020-1-2"
            bad = self.notice(swarm)
            self.assertEqual((bad["action"], bad["wanted"], bad["running"]), ("train_from_setting", ON, ON))
            self.assertIn("keeps Train from 2020-01-02", bad["text"])
            clock.t += TRAIN_SPAN_NOTICE_EVERY
            self.assertIsNotNone(self.notice(swarm), "it keeps alerting")
            swarm.settings["gym"].pop("train_from")
            gone = self.notice(swarm)
            self.assertIn("is not set", gone["text"])
            self.assertEqual(migrate_objective(swarm.store, settings=swarm.settings), {"migrated": 0, "with_best": 0, "failed": 0},
                             "a restart with the key deleted migrates nothing")
            self.assertEqual(swarm.store.get("train_objective"), ON_OBJECTIVE)

    def test_off_a_typo_is_harmless_but_named(self):
        with tempfile.TemporaryDirectory() as tmp:
            swarm, _ = self.swarm(tmp)
            swarm.settings["gym"]["train_from"] = "2020-06-01"
            bad = self.notice(swarm)
            self.assertIn("ignored", bad["text"])
            self.assertEqual((bad["wanted"], bad["running"]), ("2022-01-03", "2022-01-03"))


# ------------------------------------------------------------------------------------------------ the score
class WorstYear(unittest.TestCase):
    def test_2020_and_2021_enter_the_worst_year_only_when_on(self):
        r = five()
        off = evidence.train_score(r, first_year=2022)
        on = evidence.train_score(r, first_year=2020)
        self.assertEqual((off["worst_year"], off["score"], sorted(off["years"])), ("2022", 2.0, ["2022", "2023", "2024"]))
        self.assertEqual((on["worst_year"], on["score"], len(on["years"])), ("2020", 0.5, 5))
        self.assertEqual((off["quarters"], on["quarters"]), ("12/12", "20/20"))

    def test_a_thin_early_year_blocks_eligibility_only_when_on(self):
        r = five(trades=(10, 60, 60, 60, 60))
        self.assertTrue(evidence.train_score(r, first_year=2022)["eligible"])
        on = evidence.train_score(r, first_year=2020)
        self.assertFalse(on["eligible"])
        self.assertIn("2020 has 10 trades", on["why"])

    def test_an_early_year_without_every_root_is_left_out(self):
        r = five(roots=["SPY"])
        r["roots"] = ["SPY", "AAPL"]
        self.assertEqual(sorted(evidence.train_score(r, first_year=2020)["years"]), ["2022", "2023", "2024"])
        r["by_year"]["2022"]["roots"] = ["SPY"]
        self.assertIn("2022", evidence.train_score(r, first_year=2020)["years"], "2022 on: scored as it always was")

    def test_a_three_year_result_scores_as_before(self):
        r = yearly("three", t=(2.0, 2.5, 3.0))
        self.assertEqual(evidence.train_score(r), evidence.train_score(r, first_year=2022))


# ------------------------------------------------------------------------------------------------ the pool
class PoolSpan(PoolCase):
    def box(self, pool, train_first):
        box = self.ready_box(pool)
        box.train_first = train_first
        box.driver = FakeDriver(self.sail, "x", calls=self.calls, fail=lambda: self.failure, train_first=train_first)
        return box

    def test_every_train_job_starts_at_the_running_span_not_the_setting(self):
        pool = self.pool(train_from=ON)  # asked for, but no start migrated to it yet
        box = self.box(pool, "2022-01-03")
        train = pool.submit(job("a"))
        validation = pool.submit(job("b", window="validation"))
        holdout = pool.submit(job("c", window="holdout", gate="holdout look c v1"))
        self.assertEqual((train.start, train.span, validation.start, holdout.start), ("2022-01-03", "2022-01-03", None, None))
        self.clock.advance(9)
        pool.run_batch(box, pool._take(box))
        self.assertEqual((self.calls[-1]["start"], self.calls[-1]["split"], self.calls[-1]["timeout"]), ("2022-01-03", 8, 900))
        self.assertEqual(train.result["train_from"], "2022-01-03")

    def test_migrated_on_train_and_robustness_jobs_start_in_2020_split_16_and_an_explicit_start_stays(self):
        pool = self.pool()
        migrated(self.store, ON)
        box = self.box(pool, ON)
        first = job("a")
        robust = job("r", stress=1.5, priority=ROBUSTNESS_PRIORITY)
        robust.purpose = "robustness"
        own = job("o")
        own.start = "2023-01-03"
        a, r, o = pool.submit(first), pool.submit(robust), pool.submit(own)
        self.assertEqual((a.start, r.start, o.start, o.span), (ON, ON, "2023-01-03", None))
        self.clock.advance(9)
        pool.run_batch(box, pool._take(box))
        self.assertEqual((self.calls[-1]["start"], self.calls[-1]["split"], self.calls[-1]["timeout"]), (ON, 16, 1500))
        self.assertEqual(a.result["train_from"], ON)

    def test_an_image_on_another_span_is_refused_both_ways_and_alerts_once(self):
        """The review's probe (WrongImage) at the pool: a 2022 image under a 2020 swarm would label three years as five;
        a 2020 image under a 2022 swarm would give January 2022 a history the old image never had."""
        for running, image in ((ON, "2022-01-03"), (CORE_SPAN, ON)):
            self.calls.clear()
            pool = self.pool()
            migrated(self.store, running)
            box = self.box(pool, image)
            jobs = [pool.submit(job(f"f{running[:4]}{i}")) for i in range(2)]
            self.clock.advance(9)
            pool.run_batch(box, pool._take(box))
            self.assertEqual(self.calls, [], "nothing runs")
            for j in jobs:
                self.assertIn(f"starts Train at {image}", j.error)
                self.assertIsNone(j.result)
        alerts = [e for e in self.store.events_after(0) if e["payload"].get("action") == "train_span_mismatch"]
        self.assertEqual(len(alerts), 2)

    def test_a_batch_that_reports_another_span_is_never_delivered(self):
        pool = self.pool()
        migrated(self.store, ON)
        box = self.box(pool, None)              # a box adopted without a recorded first day
        box.driver = FakeDriver(self.sail, "x", calls=self.calls, train_first="2022-01-03")
        a = pool.submit(job("a"))
        self.clock.advance(9)
        pool.run_batch(box, pool._take(box))
        self.assertEqual(len(self.calls), 1)
        self.assertIsNone(a.result)
        self.assertIn("starts Train at 2022-01-03", a.error)
        self.assertEqual(box.train_first, "2022-01-03", "learned from the batch: the next one is refused before it runs")

    def test_validation_is_never_refused_for_the_span(self):
        pool = self.pool()
        migrated(self.store, ON)
        box = self.box(pool, "2022-01-03")
        v = pool.submit(job("v", window="validation"))
        self.clock.advance(9)
        pool.run_batch(box, pool._take(box))
        self.assertIsNotNone(v.result)
        self.assertNotIn("train_from", v.result)


# ------------------------------------------------------------------------------------------------ the researcher
class ResearcherSpan(ResearcherCase):
    def cycle(self, answer, params=None):
        self.pool = QueueingPool(answer)
        self.steps = [{"calls": [("gym_run", {"params": params or {"vrp_min": 1.3}})]}, {"text": "ok"}] if params is not False else []
        self.researcher().cycle(self.fam["id"])
        return self.store.family(self.fam["id"])

    def test_flip_without_restart_changes_nothing(self):
        """The review's probe (FlipWithoutRestart): swarm.json says 2020 at once, but the running span is the store's."""
        self.cycle(lambda job: yearly(job.name, t=(3.0, 3.1, 3.2)), params=False)
        migrate_objective(self.store, settings=S.DEFAULTS)
        before = self.store.family(self.fam["id"])
        self.settings["gym"]["train_from"] = ON
        researcher = self.researcher()
        self.assertEqual((researcher.train_span(), researcher.prompt()), (CORE_SPAN, researcher.system))
        # A five-year result that lands anyway (a stray labelled 2020) never enters the candidates or the best.
        for i in range(3):
            after = self.cycle(lambda job: five(job.name, t=(9.0,) * 5, train_from=ON), params={"vrp_min": 1.0 + i / 10})
        self.assertEqual((after["best_train"], after["state"]["train_candidates"]),
                         (before["best_train"], before["state"]["train_candidates"]))

    def test_a_run_over_the_old_span_never_beats_the_new_best(self):
        """The review's probe (reverse): migrated on, a 3-year result (queued before the switch) lands late."""
        migrated(self.store, ON)
        fam = self.cycle(lambda job: five(job.name, t=(0.4, 2.0, 2.0, 2.0, 2.0), train_from=ON), params=False)
        self.assertEqual(fam["best_train"], 0.4, "2020's t is the worst year")
        fam = self.cycle(lambda job: dict(yearly(job.name, t=(2.0, 2.5, 3.0)), train_from=CORE_SPAN))
        self.assertEqual(fam["best_train"], 0.4)
        self.assertEqual([c[0] for c in fam["state"]["train_candidates"]], [0.4])
        rows = sorted(self.store.runs(self.fam["id"], window="train"), key=lambda r: r["version"])
        self.assertEqual([r["summary"]["train_from"] for r in rows], [ON, CORE_SPAN], "each row keeps its own span")
        self.assertEqual(rows[1]["summary"]["train_score"], 2.0, "scored over its own span, which is not the running one")

    def test_the_evaluation_key_carries_a_span_other_than_2022(self):
        researcher = self.researcher()
        off = researcher.eval_key("x", {}, stress=1.0, window="train", roots=["SPY"])
        self.assertEqual(off, researcher.eval_key("x", {}, stress=1.0, window="train", roots=["SPY"], current=False,
                                                  image=None, bundle=None, span=CORE_SPAN), "the key it always was")
        migrated(self.store, ON)
        on = researcher.eval_key("x", {}, stress=1.0, window="train", roots=["SPY"])
        self.assertNotEqual(on, off)
        self.assertEqual(researcher.eval_key("x", {}, stress=1.0, window="validation", roots=["SPY"]),
                         researcher.eval_key("x", {}, stress=1.0, window="validation", roots=["SPY"], current=False,
                                             span=CORE_SPAN), "Validation is the same whatever Train's span")

    def test_a_stored_run_over_another_span_is_never_scored_into_the_best(self):
        fid = self.fam["id"]
        v = self.store.add_version(fid, "# v\nNEEDS = {'roots': ['SPY']}\n", {}, author="t")
        researcher = self.researcher()
        recorded, _ = researcher._with_score(five("old", t=(3.0,) * 5, train_from=ON), 1.0)
        run = self.store.add_run(fid, v["n"], recorded, window="train", stress=1.0, purpose="train")
        out: dict = {}
        view = researcher._stored_run(self.store.family(fid), self.store.run(run["run_id"]), out, code="# v", stress=1.0)
        self.assertIsNone(self.store.family(fid)["best_train"])
        self.assertIn("Train now starts 2022-01-03", view["train_score"]["why_not_eligible"])
        migrated(self.store, ON)
        researcher._stored_run(self.store.family(fid), self.store.run(run["run_id"]), out, code="# v", stress=1.0)
        self.assertEqual(self.store.family(fid)["best_train"], 3.0, "over the running span it counts")

    def test_a_row_from_the_other_span_cannot_be_submitted(self):
        fid = self.fam["id"]
        researcher = self.researcher()
        v1 = self.store.add_version(fid, "# v1\nNEEDS = {'roots': ['SPY']}\n", {}, author="t")
        v2 = self.store.add_version(fid, "# v2\nNEEDS = {'roots': ['SPY']}\n", {}, author="t")
        old = self.store.add_run(fid, v1["n"], researcher._with_score(yearly("three", t=(3.0, 3.1, 3.2)), 1.0)[0],
                                 window="train", stress=1.0, purpose="train")
        new = self.store.add_run(fid, v2["n"], researcher._with_score(five("five", t=(0.9,) + (2.0,) * 4, train_from=ON), 1.0)[0],
                                 window="train", stress=1.0, purpose="train")
        self.assertTrue(researcher.eligible_run(self.fam, self.store.run(old["run_id"]))[0], "off: a 3-year run, as before")
        ok, why = researcher.eligible_run(self.fam, self.store.run(new["run_id"]))
        self.assertFalse(ok)
        self.assertIn("Train from 2020-01-02", why)
        migrated(self.store, ON)
        ok, why = researcher.eligible_run(self.fam, self.store.run(old["run_id"]))
        self.assertFalse(ok)
        self.assertIn("Train now starts 2020-01-02", why)
        self.assertTrue(researcher.eligible_run(self.fam, self.store.run(new["run_id"]))[0])

    def test_a_robustness_run_over_another_span_is_a_trial_and_never_this_spans_robustness(self):
        fid = self.fam["id"]
        researcher = self.researcher()
        migrated(self.store, ON)
        trials = self.store.family(fid)["trials"]
        researcher.robust_landed(fid, 1, "stress_1.5", 1.5, dict(yearly("stale", pnl=-50.0, stress=1.5), train_from=CORE_SPAN))
        fam = self.store.family(fid)
        self.assertEqual(fam["trials"], trials + 1)
        self.assertEqual(((fam["state"] or {}).get("robustness") or {}), {})
        self.assertEqual((fam["state"] or {}).get("robust_failed") or [], [], "a 3-year loss at 1.5x never demotes a 5-year best")

    def test_the_researchers_prompt_names_the_running_span(self):
        researcher = self.researcher()
        self.assertIs(researcher.prompt(), researcher.system)
        migrated(self.store, ON)
        self.assertIn("Train (2020-2024) is yours", researcher.prompt())
        self.assertEqual(researcher.run_timeout(), 1500.0)


class Migration(ResearcherCase):
    def seed_runs(self):
        fid = self.fam["id"]
        researcher = self.researcher()
        v1 = self.store.add_version(fid, "# v1\nNEEDS = {'roots': ['SPY']}\n", {}, author="t")
        v2 = self.store.add_version(fid, "# v2\nNEEDS = {'roots': ['SPY']}\n", {}, author="t")
        old = self.store.add_run(fid, v1["n"], researcher._with_score(yearly("three", t=(3.0, 3.1, 3.2)), 1.0)[0],
                                 window="train", stress=1.0, purpose="train")
        new = self.store.add_run(fid, v2["n"], researcher._with_score(five("five", t=(0.9,) + (2.0,) * 4, train_from=ON), 1.0)[0],
                                 window="train", stress=1.0, purpose="train")
        return fid, v1, v2, old, new

    def test_off_nothing_moves_on_only_the_new_span_counts_and_off_again_restores(self):
        fid, v1, v2, old, new = self.seed_runs()
        self.assertEqual(migrate_objective(self.store, settings=S.DEFAULTS)["migrated"], 1)  # the store's first pass
        fam = self.store.family(fid)
        self.assertEqual((fam["best_version"], fam["best_train"]), (v1["n"], 3.0), "off: the 3-year run's worst year, 2022")
        self.assertEqual(migrate_objective(self.store, settings=S.DEFAULTS), {"migrated": 0, "with_best": 0, "failed": 0},
                         "off: a restart changes nothing")
        notes = len(self.store.notebook(fid))
        on = migrate_objective(self.store, settings=with_switch(ON))
        self.assertEqual(on, {"migrated": 1, "with_best": 1, "failed": 0})
        fam = self.store.family(fid)
        self.assertEqual((fam["best_version"], fam["best_train"]), (v2["n"], 0.9), "only the 5-year run, worst year 2020")
        self.assertEqual(fam["state"]["previous_best"]["objective"], OBJECTIVE, "the objective its best was chosen under")
        self.assertEqual(fam["state"]["legacy_best"]["objective"], "full-Train t_daily, 30-trade floor", "Sept 26's record stays")
        self.assertEqual((fam["state"]["objective_migrated"], fam["state"]["robustness"]), (ON_OBJECTIVE, {}))
        self.assertEqual(self.store.get("train_objective"), ON_OBJECTIVE)
        self.assertEqual(len(self.store.notebook(fid)), notes + 1)
        self.assertIn("2020-01-02", self.store.notebook(fid, limit=1)[-1]["text"])
        self.assertEqual(migrate_objective(self.store, settings=with_switch(ON))["migrated"], 0, "once per span")
        self.assertEqual(migrate_objective(self.store, settings=S.DEFAULTS)["migrated"], 0, "the key deleted: the span stays")
        back = migrate_objective(self.store, settings=with_switch("2022-01-03"))
        self.assertEqual(back["migrated"], 1)
        fam = self.store.family(fid)
        self.assertEqual((fam["best_version"], fam["best_train"]), (v1["n"], 3.0), "the rollback scores the 3-year runs again")
        self.assertEqual(fam["state"]["previous_best"]["objective"], ON_OBJECTIVE)

    def test_a_family_born_after_the_first_pass_is_labelled_with_the_stores_objective(self):
        self.store.put("train_objective", OBJECTIVE)  # the store's first pass ran before this family was born
        self.store.update_family(self.fam["id"], best_train=2.5)
        migrate_objective(self.store, settings=with_switch(ON))
        state = self.store.family(self.fam["id"])["state"]
        self.assertNotIn("legacy_best", state)
        self.assertEqual((state["previous_best"]["objective"], state["previous_best"]["best_train"]), (OBJECTIVE, 2.5))

    def test_an_interrupted_flip_comes_back_when_the_switch_goes_back(self):
        """A start died mid-pass toward 2020 (some families moved, the store's objective not yet), then the owner set the
        switch back: the next start brings the moved families back and leaves the rest alone."""
        fid, *_ = self.seed_runs()
        migrate_objective(self.store, settings=S.DEFAULTS)
        other = self.store.add_family({**self.fam["spec"], "id": "other-fam"}, origin="seed")["id"]
        self.store.set_state(other, objective_migrated=OBJECTIVE)
        self.store.set_state(fid, objective_migrated=ON_OBJECTIVE)  # moved by the interrupted pass
        self.store.update_family(fid, best_train=None, best_version=None)
        out = migrate_objective(self.store, settings=S.DEFAULTS)
        self.assertEqual(out["migrated"], 1)
        fam = self.store.family(fid)
        self.assertEqual((fam["best_train"], fam["state"]["objective_migrated"]), (3.0, OBJECTIVE))
        self.assertNotIn("previous_best", self.store.family(other)["state"])


class FlipRetirement(RoundCase):
    """B2: the flip empties most bests; the idle rule and the dormancy clause must not read that as death."""

    def setUp(self):
        super().setUp()
        self.settings["tournament"].update(retire_revisions=10 ** 6, retire_evaluations=10 ** 6)
        self.settings["population"].update(start=2, floor=0)

    def test_the_flip_restarts_the_idle_count_and_dormancy_and_the_tournament_retires_no_one(self):
        from league.swarm.tournament import Tournament

        for fid in ("a", "b", "c"):
            self.family(fid)
            self.store.update_family(fid, best_train=1.5, trials=400, since_val_trials=400)
        self.store.set_state("c", dormant_cycles=45, validated_trials=100)
        self.store.put("train_objective", OBJECTIVE)
        self.assertEqual(Tournament(self.store, self.pool, self.settings).retirements(self.store.families(alive=True)), [],
                         "eligible bests: no one is dead before the flip")
        migrate_objective(self.store, settings=with_switch(ON))
        fams = self.store.families(alive=True)
        self.assertTrue(all(f["best_train"] is None for f in fams), "no 5-year runs yet: every best is empty")
        self.assertEqual([idle_evaluations(f) for f in fams], [0, 0, 0])
        self.assertEqual([(f["state"] or {}).get("dormant_cycles") for f in fams], [0, 0, 0])
        self.assertEqual([idle_dead(f, self.settings) for f in fams], [None, None, None])
        self.assertEqual(Tournament(self.store, self.pool, self.settings).retirements(self.store.families(alive=True)), [])
        # Then the rule runs again from the flip: 150 evaluations over the new span without an eligible version.
        self.store.update_family("a", trials=550, since_val_trials=550)
        self.store.update_family("b", trials=549, since_val_trials=549)
        [row] = Tournament(self.store, self.pool, self.settings).retirements(self.store.families(alive=True))
        self.assertEqual(row["family"], "a")
        self.assertIn("150 Gym evaluations since Train's span changed", row["why"])


# ------------------------------------------------------------------------------------------------ the drift screen
def early_block(alpha=(-40.0, 60.0, 60.0, 60.0, 60.0), roots=("SPY",), root_days=None, sums=True) -> dict:
    """An invented 2020-2024 drift block with the extension's extents (every year 250 days)."""
    block = drift_block(t=2.0, alpha_usd=60.0, years=("2020", "2021", "2022", "2023", "2024"))
    for i, year in enumerate(sorted(block["years"])):
        row = block["years"][year]
        row["alpha_usd"] = alpha[i]
        row["root_days"] = dict((root_days or {}).get(year) or {r: 250 for r in roots})
        if sums:
            row["sum_sq"], row["sum_pp"] = 250 * 40.0, 250 * 60.0
    block["roots"] = list(roots)
    return block


class DriftSpan(unittest.TestCase):
    def test_the_screen_counts_the_spans_years_and_all_but_one_of_them(self):
        numbers = evidence.drift_numbers(early_block())
        full = evidence.drift_screen(numbers, first_year=2020)
        self.assertEqual((full["years"], full["positive"], full["need"], full["passed"]), (5, 4, 4, True),
                         "2020's negative alpha is the one year allowed")
        core = evidence.drift_screen(numbers, first_year=2022)
        self.assertEqual((core["years"], core["need"], core["left_out"]), (3, 2, ["2020", "2021"]))
        from league.gym.results import _t_of
        self.assertAlmostEqual(core["t"], _t_of(180.0, 750 * 40.0, 750, 750 * 60.0), msg="the pooled t refitted over 2022-2024")
        self.assertNotAlmostEqual(core["t"], numbers["pooled"]["t"])

    def test_a_year_a_root_lacked_data_in_is_left_out_as_the_train_score_does(self):
        days = {"2020": {"SPY": 250, "AAPL": 0}, "2021": {"SPY": 250, "AAPL": 100}}
        numbers = evidence.drift_numbers(early_block(alpha=(-40.0, -40.0, 60.0, 60.0, 60.0), roots=("SPY", "AAPL"), root_days=days))
        verdict = evidence.drift_screen(numbers, first_year=2020)
        self.assertEqual((verdict["years"], verdict["left_out"], verdict["positive"], verdict["passed"]), (3, ["2020", "2021"], 3, True),
                         "scored on SPY alone in 2020-21 it would fail two of five")
        both = evidence.drift_numbers(early_block(alpha=(-40.0, -40.0, 60.0, 60.0, 60.0)))
        self.assertFalse(evidence.drift_screen(both, first_year=2020)["passed"], "a SPY-only program fails 2 of 5")

    def test_figures_that_cannot_be_refitted_are_not_known_and_a_three_year_block_is_as_before(self):
        old = evidence.drift_numbers(early_block(sums=False))
        self.assertFalse(evidence.drift_screen(old, first_year=2022)["known"], "years to leave out, no sums to refit with")
        self.assertTrue(evidence.drift_screen(old, first_year=2020)["known"], "nothing left out: the stored pooled t stands")
        three = evidence.drift_numbers(drift_block())
        self.assertEqual(evidence.drift_screen(three, first_year=2022), evidence.drift_screen(three))


class DriftSpanResearcher(ResearcherCase):
    def row(self, n, block, span=None):
        r = yearly(f"v{n}")
        r["drift"] = block
        if span:
            r["train_from"] = span
        recorded, _ = self.researcher()._with_score(r, 1.0)
        return self.store.add_run(self.fam["id"], n, recorded, window="train", stress=1.0, purpose="train")

    def test_version_drift_reads_the_running_spans_rows_only(self):
        fid = self.fam["id"]
        v = self.store.add_version(fid, "# v\nNEEDS = {'roots': ['SPY']}\n", {}, author="t")
        self.row(v["n"], drift_block())                                   # a 2022-2024 run: passes
        fam = self.store.family(fid)
        self.assertIsNotNone(version_drift(self.store, fam, v["n"]))
        self.assertTrue(drift_verdict(self.store, fam, v["n"], self.settings)["passed"])
        migrated(self.store, ON)
        self.assertIsNone(version_drift(self.store, fam, v["n"]), "a 3-year run never screens a version over 2020-2024")
        self.assertFalse(drift_verdict(self.store, fam, v["n"], self.settings)["known"])
        self.row(v["n"], early_block(alpha=(-40.0, -40.0, 60.0, 60.0, 60.0)), span=ON)
        verdict = drift_verdict(self.store, self.store.family(fid), v["n"], self.settings)
        self.assertEqual((verdict["known"], verdict["years"], verdict["passed"]), (True, 5, False), "2 of 5 negative: fails")

    def test_the_migration_clears_the_submitted_run_and_the_old_spans_drift_marks(self):
        fid = self.fam["id"]
        self.store.put("train_objective", OBJECTIVE)
        self.store.set_state(fid, submitted_run="run-old", submitted_note="mine", drift_failed={"3": "t 0.4 over 2022-2024"})
        migrate_objective(self.store, settings=with_switch(ON))
        state = self.store.family(fid)["state"]
        self.assertEqual((state.get("submitted_run"), state.get("submitted_note"), state.get("drift_failed")), (None, None, {}))


# ------------------------------------------------------------------------------------------------ the verifier's pool probe
class OffStartPath(PoolCase):
    """The verifier's probe of #399 (daaf14ea), switch OFF, through the pool's real start, adopt and dispatch paths."""

    def mk(self, train_first, **gym):
        return GymPool(self.store, self.sail, pool_settings(**gym), clock=self.clock, threaded=False, allowed=lambda k: self.allowed[k],
                       driver_factory=lambda client, box: FakeDriver(client, box, calls=self.calls, fail=lambda: self.failure,
                                                                    train_first=train_first))

    def drive(self, pool):
        t = pool.submit(job("t"))
        r = job("r", stress=1.5, priority=ROBUSTNESS_PRIORITY)
        r.purpose = "robustness"
        r = pool.submit(r)
        v = pool.submit(job("v", window="validation"))
        h = pool.submit(job("h", window="holdout", gate="holdout look h v1"))
        f = pool.submit(job("f", window="forward", gate="forward f v1"))
        pool.manage()
        for step in (20, 1300):  # the second pass ages the robustness run (one box: it waits for the inner loop first)
            self.clock.advance(step)
            for _ in range(8):
                for box in list(pool.boxes.values()):
                    if box.state in ("ready", "asleep"):
                        batch = pool._take(box)
                        if batch:
                            pool.run_batch(box, batch)
        return t, r, v, h, f

    def check(self, jobs, label):
        t, r, v, h, f = jobs
        for j in jobs:
            self.assertIsNone(j.error, f"{label}: {j.family} refused: {j.error}")
            self.assertIsNotNone(j.result, f"{label}: {j.family} no result")
        self.assertEqual((t.start, t.span, r.start, v.start, h.start, f.start),
                         ("2022-01-03", "2022-01-03", "2022-01-03", None, None, None))
        self.assertEqual(t.result["train_from"], "2022-01-03")
        train_calls = [c for c in self.calls if c["window"] == "train"]
        self.assertTrue(train_calls and all((c["start"], c["split"], c["timeout"]) == ("2022-01-03", 8, 900) for c in train_calls))
        other = [c for c in self.calls if c["window"] != "train"]
        self.assertTrue(other and all((c["start"], c["timeout"]) == (None, 900) for c in other))
        alerts = [e for e in self.store.events_after(0)
                  if e["payload"].get("action") in ("train_span_mismatch", "train_span_pending", "train_from_setting")]
        self.assertEqual(alerts, [])

    def test_off_store_migrated_on_main_the_adopted_image_reports_2022_01_03(self):
        self.store.put("train_objective", OBJECTIVE)  # production: main's Sept 26 pass
        self.assertEqual(migrate_objective(self.store, settings=S.DEFAULTS), {"migrated": 0, "with_best": 0, "failed": 0})
        pool = self.mk("2022-01-03", start_boxes=1)
        jobs = self.drive(pool)
        gym = [b for b in pool.boxes.values() if b.kind == "gym"]
        self.assertTrue(gym and all(b.train_first == "2022-01-03" for b in gym))
        self.assertEqual([(row.get("detail") or {}).get("train_first") for row in self.store.boxes() if row["kind"] == "gym"],
                         ["2022-01-03"])
        self.check(jobs, "adopted image")

    def test_off_a_box_that_does_not_report_train_first(self):
        self.store.put("train_objective", OBJECTIVE)
        self.check(self.drive(self.mk(None, start_boxes=1)), "no report")

    def test_off_store_never_migrated(self):
        self.check(self.drive(self.mk("2022-01-03", start_boxes=1)), "unmigrated")

    def test_off_adopted_box_without_recorded_train_first(self):
        self.store.put("train_objective", OBJECTIVE)
        self.store.upsert_box("sb_00000001-0000-0000-0000-000000000000", kind="gym", version="sbcp_11111111-aaaa", state="asleep",
                              detail={"roots": ["SPY", "QQQ", "IWM", "XSP", "SPXW"], "name": "x"})
        pool = self.mk("2022-01-03")
        self.assertEqual(pool.adopt(), 1)
        box = pool.boxes["sb_00000001-0000-0000-0000-000000000000"]
        self.assertIsNone(box.train_first)
        t = pool.submit(job("t"))
        self.clock.advance(20)
        pool.run_batch(box, pool._take(box))
        self.assertIsNone(t.error)
        self.assertEqual((t.result["train_from"], box.train_first), ("2022-01-03", "2022-01-03"))

    def test_explicit_operator_split_and_timeout_are_kept(self):
        self.store.put("train_objective", OBJECTIVE)
        self.check(self.drive(self.mk("2022-01-03", start_boxes=1, train_split=8, run_timeout_seconds=900)), "explicit")

    def test_legacy_split_key_and_string_values(self):
        self.store.put("train_objective", OBJECTIVE)
        self.check(self.drive(self.mk("2022-01-03", start_boxes=1, train_split="8", run_timeout_seconds="900")), "strings")


if __name__ == "__main__":
    unittest.main()
