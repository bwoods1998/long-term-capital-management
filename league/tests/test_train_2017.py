"""Train from 2017 (Sept 29, 2026; the full-history plan's PR B): Train's window and the swarm's starts reach 2017-01-03,
the 2017-2019 event and rate tables, a Gym store's first Train day read from its chains (so an image built from 2020 keeps
its 2019 history sessions out of Train), a per-root first Train day for images (`--root-first`), and THE BRIDGE: on an
image that also holds 2017-19, a Train run from 2020-01-02 gives exactly the rows it gives on the image without them.

What must not move is pinned against main before this change: stages 1-10 plan the same tasks (digests), the event and
rate tables from 2020 on and from 2025 on are the same (digests), an image built from 2020 or 2022 prunes as before,
and 2020 and 2022 spans keep their split and time limit. Synthetic stores and invented results only."""

from __future__ import annotations

import contextlib
import copy
import datetime as dt
import hashlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

DATA = Path(__file__).resolve().parents[2] / "scripts" / "data"
if str(DATA) not in sys.path:
    sys.path.insert(0, str(DATA))

import storelib as sl  # noqa: E402

from league.gym import events as EV  # noqa: E402 - standard library only
from league.swarm import settings as S  # noqa: E402
from league.swarm.researcher import OBJECTIVE, objective_for  # noqa: E402
from league.tests.swarm_fakes import FakeDriver  # noqa: E402
from league.tests.test_swarm_pool import PoolCase, job  # noqa: E402

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
T2017, T2020, T2022 = "2017-01-03", "2020-01-02", "2022-01-03"


def nyse_calendar() -> sl.Calendar:
    """NYSE's 2016-2021 full and early closes (and a few later ones), as ThetaData's calendar_year returns them."""
    full = ("2016-01-01", "2016-01-18", "2016-02-15", "2016-03-25", "2016-05-30", "2016-07-04", "2016-09-05", "2016-11-24",
            "2016-12-26",
            "2017-01-02", "2017-01-16", "2017-02-20", "2017-04-14", "2017-05-29", "2017-07-04", "2017-09-04", "2017-11-23",
            "2017-12-25",
            "2018-01-01", "2018-01-15", "2018-02-19", "2018-03-30", "2018-05-28", "2018-07-04", "2018-09-03", "2018-11-22",
            "2018-12-05", "2018-12-25",
            "2019-01-01", "2019-01-21", "2019-02-18", "2019-04-19", "2019-05-27", "2019-07-04", "2019-09-02", "2019-11-28",
            "2019-12-25",
            "2020-01-01", "2020-01-20", "2020-02-17", "2020-04-10", "2020-05-25", "2020-07-03", "2020-09-07", "2020-11-26",
            "2020-12-25", "2021-01-01", "2021-01-18", "2021-02-15", "2021-04-02", "2021-05-31", "2021-07-05", "2021-09-06",
            "2021-11-25", "2021-12-24", "2024-01-01", "2025-01-01", "2026-01-01")
    early = ("2016-11-25", "2017-07-03", "2017-11-24", "2018-07-03", "2018-11-23", "2018-12-24", "2019-07-03", "2019-11-29",
             "2019-12-24", "2020-11-27", "2020-12-24", "2021-11-26")
    rows = [{"date": d, "type": "full_close"} for d in full]
    rows += [{"date": d, "type": "early_close", "open": "09:30:00", "close": "13:00:00"} for d in early]
    return sl.Calendar.from_rows(rows)


def with_switch(value: object) -> dict:
    out = copy.deepcopy(S.DEFAULTS)
    if value is not None:
        out["gym"]["train_from"] = value
    return out


# ------------------------------------------------------------------------------------------------ the data box's rules
class Windows(unittest.TestCase):
    def test_train_reaches_2017_only_for_an_image_built_from_it(self):
        self.assertEqual(sl.TRAIN_EARLIEST, D(2017, 1, 3))
        first = D(2017, 1, 3)
        for day, window in ((D(2016, 12, 30), "pre"), (D(2017, 1, 3), "train"), (D(2018, 2, 5), "train"),
                            (D(2019, 12, 31), "train"), (D(2025, 6, 2), "validation"), (D(2026, 3, 2), "holdout")):
            self.assertEqual(sl.window_of(day, first), window, day)
        for day, window in ((D(2017, 1, 3), "pre"), (D(2019, 12, 31), "pre"), (D(2021, 12, 31), "pre"), (D(2022, 1, 3), "train")):
            self.assertEqual(sl.window_of(day), window, "the default (every stage, journal record and image) is unchanged")
        self.assertEqual(sl.window_of(D(2019, 12, 31), D(2020, 1, 2)), "pre", "an image built from 2020 is unchanged")
        for bad in (D(2016, 12, 30), D(2022, 1, 4)):
            with self.assertRaises(ValueError):
                sl.window_of(D(2023, 1, 3), bad)

    def test_the_sessions_of_2016_2019_and_the_history_before_2017(self):
        cal = nyse_calendar()
        counts = {y: len(cal.days(D(y, 1, 1), D(y, 12, 31))) for y in (2016, 2017, 2018, 2019, 2020, 2021)}
        self.assertEqual(counts, {2016: 252, 2017: 251, 2018: 251, 2019: 252, 2020: 253, 2021: 252})
        self.assertNotIn(D(2018, 12, 5), cal.days(D(2018, 12, 1), D(2018, 12, 31)), "the national day of mourning")
        history = sl.history_days(cal, D(2017, 1, 3))
        self.assertEqual((len(history), history[0], history[-1]), (60, D(2016, 10, 6), D(2016, 12, 30)))
        self.assertLessEqual((D(2017, 1, 3) - history[0]).days, 100, "inside the image check's history reach")

    def test_stages_1_to_10_plan_exactly_what_they_planned_before(self):
        """EARLY stays the literal 2020-01-02..2021-12-31 (stage 9 plans from it), whatever TRAIN_EARLIEST says. The
        digests are main's before Train from 2017 (computed with main's storelib on this calendar)."""
        self.assertEqual(sl.EARLY, (D(2020, 1, 2), D(2021, 12, 31)))
        rows = [{"date": d, "type": "full_close"} for d in (
            "2019-01-01", "2019-11-28", "2019-12-25", "2020-01-01", "2020-01-20", "2020-02-17", "2020-04-10", "2020-05-25",
            "2020-07-03", "2020-09-07", "2020-11-26", "2020-12-25", "2021-01-01", "2021-01-18", "2021-02-15", "2021-04-02",
            "2021-05-31", "2021-07-05", "2021-09-06", "2021-11-25", "2021-12-24", "2022-01-17", "2022-12-26", "2023-01-02",
            "2024-01-01", "2025-01-01", "2026-01-01", "2026-12-25", "2027-01-01")]
        rows += [{"date": d, "type": "early_close", "open": "09:30:00", "close": "13:00:00"}
                 for d in ("2019-11-29", "2019-12-24", "2020-11-27", "2020-12-24", "2021-11-26")]
        cal = sl.Calendar.from_rows(rows)

        def digest(tasks):
            text = "\n".join(f"{t.stage}|{t.id}|{t.window}" for t in tasks)
            return hashlib.sha256(text.encode()).hexdigest()[:16], len(tasks)

        self.assertEqual(digest(sl.plan(cal, stages=(9, 10))), ("7b5c760add9f334c", 3835))
        self.assertEqual(digest(sl.plan(cal, stages=(9, 10), early=["SPY", "IWM"])), ("da8e7638bc36ba2a", 1635))
        self.assertEqual(digest(sl.plan(cal, stages=(1, 2, 3, 4, 5, 6), names=["AAPL", "TSLA"], order=(1, 2, 3, 5, 4, 6))),
                         ("d81c442eb4af4be2", 11841))
        self.assertEqual(sl.stage_of("SPY", D(2019, 6, 3)), None, "no fixed stage reaches 2017-19 (the blocks do)")
        self.assertEqual(sl.stage_of("SPY", D(2020, 3, 16)), 9)

    def test_a_roots_own_first_day_is_parsed_and_refused_outside_the_image(self):
        first = D(2017, 1, 3)
        self.assertEqual(sl.parse_root_first("xsp=2020-01-02, AAPL=2020-01-02", first),
                         {"XSP": D(2020, 1, 2), "AAPL": D(2020, 1, 2)})
        self.assertEqual(sl.parse_root_first({"XSP": "2020-01-02"}, first), {"XSP": D(2020, 1, 2)})
        self.assertEqual(sl.parse_root_first("", first), {})
        self.assertEqual(sl.parse_root_first("SPY=2017-01-03", first), {"SPY": first}, "the image's own day is allowed")
        for bad in ("XSP=2016-12-30", "XSP=2022-01-04", "XSP", "XSP=soon", "X-P=2020-01-02", "XSP=2020-01-02,XSP=2021-01-04"):
            with self.assertRaises(ValueError, msg=bad):
                sl.parse_root_first(bad, first)
        with self.assertRaises(ValueError):
            sl.parse_root_first("XSP=2019-06-03", D(2020, 1, 2))  # before a 2020 image's first day
        with self.assertRaises(ValueError):
            sl.parse_root_first("XSP=2020-01-02", None)  # no image day


# ------------------------------------------------------------------------------------------------ the tables
class Tables(unittest.TestCase):
    @staticmethod
    def digest(cut_events: dt.date, cut_rates: dt.date, splits: bool) -> str:
        body = {"fomc": sorted(d.isoformat() for d in EV.FOMC if d >= cut_events),
                "cpi": sorted(d.isoformat() for d in EV.CPI if d >= cut_events),
                "jobs": sorted(d.isoformat() for d in EV.JOBS if d >= cut_events),
                "rates": [[d.isoformat(), r] for d, r in EV.RATES if d >= cut_rates]}
        if splits:
            body["splits"] = [[r, d.isoformat(), f] for r, d, f in EV.SPLITS]
        return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()[:16]

    def test_2020_on_and_2025_on_are_exactly_mains(self):
        """Main's digests before Train from 2017: nothing dated 2020 or later moved, the splits included, and no row
        dated 2025-2026 was added to any table the engine reads."""
        self.assertEqual(self.digest(D(2020, 1, 1), D(2019, 10, 31), True), "425d66d38f5ff70f")
        self.assertEqual(self.digest(D(2025, 1, 1), D(2025, 1, 1), False), "5fc01c92042eced4")

    def test_2017_2019_scheduled_fomc_cpi_and_jobs_days(self):
        for year in (2017, 2018, 2019):
            self.assertEqual(sum(d.year == year for d in EV.FOMC), 8, f"{year}: eight scheduled meetings")
            self.assertEqual(sum(d.year == year for d in EV.CPI), 12, year)
            self.assertEqual(sum(d.year == year for d in EV.JOBS), 12, year)
        self.assertIn(D(2018, 11, 8), EV.FOMC, "the Thursday after the 2018 election")
        self.assertNotIn(D(2019, 10, 4), EV.FOMC, "the unscheduled call of Oct 4, 2019 is no flag")
        self.assertIn(D(2019, 10, 4), EV.JOBS)
        self.assertIn(D(2017, 1, 18), EV.CPI, "December 2016's CPI")
        self.assertIn(D(2017, 1, 6), EV.JOBS, "December 2016's jobs report")
        self.assertIn(D(2017, 4, 14), EV.CPI, "released on Good Friday, as April 10, 2020's")
        early = [d for d in EV.FOMC | EV.CPI | EV.JOBS if d.year < 2020]
        self.assertTrue(all(d.weekday() < 5 for d in early))
        self.assertEqual(min(early), D(2017, 1, 6), "nothing before Train's first year")
        self.assertEqual(len([d for d in EV.FOMC if d.year < 2020]), 24)

    def test_rate_steps_back_to_december_2015(self):
        self.assertEqual(EV.RATES[0][0], D(2015, 12, 17))
        self.assertEqual([d for d, _ in EV.RATES], sorted(d for d, _ in EV.RATES))
        for day, rate in ((D(2016, 6, 15), 0.004), (D(2017, 1, 3), 0.0065), (D(2017, 3, 15), 0.0065), (D(2017, 3, 16), 0.009),
                          (D(2017, 6, 15), 0.0115), (D(2017, 12, 14), 0.014), (D(2018, 2, 5), 0.014), (D(2018, 3, 22), 0.0165),
                          (D(2018, 6, 14), 0.019), (D(2018, 9, 27), 0.0215), (D(2018, 12, 20), 0.024), (D(2019, 7, 31), 0.024),
                          (D(2019, 8, 1), 0.0215), (D(2019, 9, 19), 0.019), (D(2019, 10, 30), 0.019), (D(2019, 10, 31), 0.0165),
                          (D(2019, 11, 15), 0.0165), (D(2020, 3, 16), 0.0015)):
            self.assertAlmostEqual(EV.rate_on(day), rate, msg=str(day))
        # Every day from the table's first step on sits on a step of its own (none falls back to the first row).
        day = D(2016, 1, 4)
        while day <= D(2019, 12, 31):
            self.assertGreaterEqual(day, EV.RATES[0][0])
            day += dt.timedelta(days=17)


# ------------------------------------------------------------------------------------------------ the swarm's switch
class Switch(unittest.TestCase):
    def test_2017_is_a_start_it_snaps_and_nothing_else_moves(self):
        self.assertEqual(S.TRAIN_EARLIEST, D(2017, 1, 3))
        self.assertEqual(S.TRAIN_STARTS, {2017: D(2017, 1, 3), 2020: D(2020, 1, 2), 2022: D(2022, 1, 3)})
        self.assertEqual((S.train_from(with_switch(T2017)), S.train_from_note(with_switch(T2017))), (D(2017, 1, 3), None))
        for near in ("2017-01-01", "2017-01-02", 2017):
            self.assertEqual(S.train_from(with_switch(near)), D(2017, 1, 3), near)
            self.assertIn("first session", S.train_from_note(with_switch(near)))
        for bad in ("2016-12-30", "2017-01-04", "2018-01-02", "2019-01-02", 2018):
            self.assertEqual(S.train_from(with_switch(bad)), D(2022, 1, 3), bad)
            self.assertIn("ignored", S.train_from_note(with_switch(bad)))
            self.assertEqual(S.train_from(with_switch(bad), D(2020, 1, 2)), D(2020, 1, 2), "a typo keeps the running span")
        self.assertEqual(S.train_from(S.DEFAULTS, D(2017, 1, 3)), D(2017, 1, 3), "a deleted key keeps it too")
        self.assertEqual(S.train_from(with_switch(T2020)), D(2020, 1, 2))
        self.assertEqual(S.train_from(with_switch(T2022), D(2017, 1, 3)), D(2022, 1, 3), "switching back is written out")
        self.assertIsNone(S.DEFAULTS["gym"]["train_from"])

    def test_the_span_its_years_split_time_limit_and_objective(self):
        self.assertEqual(S.train_years(with_switch(T2017)), tuple(range(2017, 2025)))
        self.assertEqual((S.train_split(S.DEFAULTS, D(2017, 1, 3)), S.run_timeout(S.DEFAULTS, D(2017, 1, 3))), (24, 2400.0))
        self.assertEqual((S.train_split(S.DEFAULTS, D(2020, 1, 2)), S.run_timeout(S.DEFAULTS, D(2020, 1, 2))), (16, 1500.0))
        self.assertEqual((S.train_split(S.DEFAULTS), S.run_timeout(S.DEFAULTS)), (8, 900.0))
        mine = copy.deepcopy(S.DEFAULTS)
        mine["gym"].update(train_split=16, run_timeout_seconds=1800)
        self.assertEqual((S.train_split(mine, D(2017, 1, 3)), S.run_timeout(mine, D(2017, 1, 3))), (16, 1800.0))
        self.assertEqual(S.objective_span(f"{OBJECTIVE}@{T2017}"), D(2017, 1, 3))
        self.assertEqual(objective_for(with_switch(T2017)), f"{OBJECTIVE}@{T2017}")
        self.assertEqual(S.objective_span(f"{OBJECTIVE}@2018-01-02"), D(2022, 1, 3), "never a span with no start")

    def test_the_prompts_name_eight_years(self):
        from league.swarm.architect import SYSTEM as ARCHITECT

        text = S.train_span_text(ARCHITECT, D(2017, 1, 3))
        self.assertIn("Train 2017-2024", text)
        self.assertIn("earn in 2017, 2018, 2019, 2020, 2021, 2022, 2023 and 2024 alike", text)
        self.assertIs(S.train_span_text(ARCHITECT, D(2022, 1, 3)), ARCHITECT)


class PoolSpan(PoolCase):
    def box(self, pool, train_first):
        box = self.ready_box(pool)
        box.train_first = train_first
        box.driver = FakeDriver(self.sail, "x", calls=self.calls, fail=lambda: self.failure, train_first=train_first)
        return box

    def test_a_2017_span_starts_there_with_split_24_and_2400_s(self):
        pool = self.pool()
        self.store.put("train_objective", objective_for(with_switch(T2017)))
        box = self.box(pool, T2017)
        a = pool.submit(job("a"))
        self.assertEqual((a.start, a.span), (T2017, T2017))
        self.clock.advance(9)
        pool.run_batch(box, pool._take(box))
        self.assertEqual((self.calls[-1]["start"], self.calls[-1]["split"], self.calls[-1]["timeout"]), (T2017, 24, 2400))
        self.assertEqual(a.result["train_from"], T2017)

    def test_a_2020_image_under_a_2017_swarm_and_a_2017_image_under_a_2020_swarm_are_refused(self):
        for running, image in ((T2017, T2020), (T2020, T2017)):
            self.calls.clear()
            pool = self.pool()
            self.store.put("train_objective", objective_for(with_switch(running)))
            box = self.box(pool, image)
            j = pool.submit(job(f"f{running[:4]}"))
            self.clock.advance(9)
            pool.run_batch(box, pool._take(box))
            self.assertEqual(self.calls, [], "nothing runs")
            self.assertIn(f"starts Train at {image}", j.error)


# ------------------------------------------------------------------------------------------------ the Gym and the bridge
#: A program whose trades depend on its history (NEEDS history 15) and on what it remembers (the days it has seen).
HISTORY_PROGRAM = """import numpy as np
NEEDS = {"roots": ["SPY"], "dte": [0, 3], "band": 0.05, "cadence": 30, "history": 15}
PARAMS = {}
STATE = {"days": 0, "last": 10 ** 6, "opened": -1}


def decide(ctx):
    if ctx.minute < STATE["last"]:
        STATE["days"] = STATE["days"] + 1
    STATE["last"] = ctx.minute
    intents = []
    for pos in ctx.positions:
        if ctx.minutes_to_close <= 90 and not any(o["position"] == pos["id"] for o in ctx.orders):
            intents.append({"close": pos["id"], "limit": "natural"})
    chain = ctx.chain
    if chain is None or chain.n == 0 or ctx.positions or STATE["opened"] == STATE["days"] or ctx.minute < 600:
        return intents
    closes = np.asarray(ctx.under.closes)
    if closes.size < 3:
        return intents
    up = float(ctx.under.price) > float(np.mean(closes[-10:]))
    right = "C" if up == (STATE["days"] % 2 == 0) else "P"
    listed = [int(d) for d in chain.expiries if 1 <= d <= 3]
    if not listed:
        return intents
    intents.append({"open": "long_call" if right == "C" else "long_put", "root": "SPY",
                    "legs": [{"side": "long", "right": right, "dte": listed[0], "atm": 0}],
                    "qty": 1, "limit": "natural", "tag": "h"})
    STATE["opened"] = STATE["days"]
    return intents
"""


def _synthetic_days() -> list[dt.date]:
    from league.gym.synth import weekdays

    late_2019 = weekdays(D(2019, 12, 2), 30, skip=(D(2019, 12, 24), D(2019, 12, 25)))  # no half day: synth has none
    late_2019 = [d for d in late_2019 if d.year == 2019]
    return late_2019 + weekdays(D(2020, 1, 2), 12, skip=(D(2020, 1, 20),)) + weekdays(D(2022, 1, 3), 4)


@unittest.skipUnless(HAVE_GYM, "numpy/pyarrow not installed (requirements-gym.txt)")
class Bridge(unittest.TestCase):
    """Image T (2019 chains, Train from its first day) and image N (the same files without the 2019 chains: the underlying
    alone for those sessions, as history), built from one synthetic market so every shared file is byte-identical, as the
    data box keeps a journaled underlying (PR #413's `kept_underlying`)."""

    @classmethod
    def setUpClass(cls):
        import pyarrow.parquet as pq
        from league.gym import synth

        cls.dir = Path(tempfile.mkdtemp(prefix="train2017-"))
        cls.days = _synthetic_days()
        cls.t = cls.dir / "t"
        synth.generate(cls.t, roots=("SPY",), days=cls.days, strikes_each_side=3, max_dte=3, seed=11)
        cls.n = cls.dir / "n"
        shutil.copytree(cls.t, cls.n)
        for kind in ("nbbo", "oi"):
            for path in (cls.n / kind / "SPY").glob("2019-*.parquet"):
                path.unlink()
        manifest = pq.read_table(cls.n / "manifest.parquet").to_pylist()
        kept = [r for r in manifest if not (r["kind"] in ("nbbo", "oi") and r["date"] < D(2020, 1, 2))]
        for r in kept:
            if r["date"] < D(2020, 1, 2):
                r["window"] = "history"
        pq.write_table(pyarrow.Table.from_pylist(kept, schema=pq.read_schema(cls.t / "manifest.parquet")), cls.n / "manifest.parquet")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def run_batch(self, root, **kw):
        from league.gym import batch

        return batch.run_batch([("h", HISTORY_PROGRAM, {})], store_root=str(root), window="train", roots=["SPY"], workers=1, **kw)

    def test_each_store_starts_train_at_its_first_chain(self):
        from league.gym.store import Store, describe

        t, n = Store(self.t), Store(self.n)
        self.assertEqual((t.train_first(), n.train_first()), (self.days[0], D(2020, 1, 2)))
        on = [d for d in self.days if d >= D(2020, 1, 2)]
        self.assertEqual(n.days("train", ["SPY"]), on)
        self.assertEqual(n.days("train", ["SPY"], kind="underlying"), on, "the history sessions are never Train days")
        self.assertEqual(n.days("train", []), on)
        self.assertEqual(t.days("train", ["SPY"]), self.days)
        self.assertEqual(n.history_days(D(2020, 1, 2), 60), [d for d in self.days if d.year == 2019], "the history is there")
        report = describe(n, "train", ["SPY"])
        self.assertEqual((report["train_first"], report["roots"]["SPY"]["underlying"]), (T2020, len(on)))
        self.assertEqual(describe(t, "train", ["SPY"])["train_first"], self.days[0].isoformat())

    def test_a_run_from_2020_is_the_same_on_both_images(self):
        for split in (1, 2):
            n = self.run_batch(self.n, start=D(2020, 1, 2), split=split)
            t = self.run_batch(self.t, start=D(2020, 1, 2), split=split)
            self.assertEqual((n["batch"]["first_day"], t["batch"]["first_day"]), (T2020, T2020))
            self.assertEqual((n["batch"]["train_first"], t["batch"]["train_first"]), (T2020, self.days[0].isoformat()),
                             "the stamp says which image: the pool refuses T under a 2020 swarm")
            rn, rt = n["results"][0], t["results"][0]
            self.assertGreater(len(rn["trades"]), 3, "the program trades")
            clock = ("seconds", "decide_seconds")  # wall-clock time, never a result

            def plain(result):
                out = {k: v for k, v in result.items() if k not in clock}
                out["runtime"] = {k: v for k, v in (result.get("runtime") or {}).items() if k not in clock}
                return out

            pn, pt = plain(rn), plain(rt)
            moved = {k for k in set(pn) | set(pt) if pn.get(k) != pt.get(k)}
            self.assertLessEqual(moved, {"data_version"},
                                 f"split {split}: only the data version (the calendar's hash) may move")
            self.assertEqual((rn["trades"], rn["daily"], rn["by_year"]), (rt["trades"], rt["daily"], rt["by_year"]))

    def test_the_2019_chains_are_traded_only_from_the_images_own_first_day(self):
        whole = self.run_batch(self.t, split=1)["results"][0]
        self.assertEqual(sorted(whole["by_year"]), ["2019", "2020", "2022"])
        self.assertEqual(self.run_batch(self.n, split=1)["batch"]["first_day"], T2020, "N has no 2019 Train day")


# ------------------------------------------------------------------------------------------------ the images
@unittest.skipIf(pl is None, "polars/pyarrow are not installed here (they are on the data box)")
class ImagesPrune(unittest.TestCase):
    """A data box that holds earlier files as well (core chains from 2017 with the underlying of the sessions before,
    a name's underlying before 2020 and a stray earlier chain of it), pruned as image N (from 2020) and image T (from
    2017)."""

    CHAINS = {"SPY": (D(2017, 1, 3), D(2017, 3, 1), D(2019, 6, 3), D(2019, 12, 16), D(2020, 3, 16), D(2021, 6, 1), D(2024, 3, 13),
                      D(2025, 6, 11)),
              "XSP": (D(2017, 3, 1), D(2019, 6, 3), D(2019, 12, 16), D(2020, 3, 16), D(2021, 6, 1), D(2024, 3, 13), D(2025, 6, 11)),
              "AAPL": (D(2019, 6, 3), D(2020, 3, 16), D(2021, 6, 1), D(2024, 3, 13), D(2025, 6, 11))}
    UNDER_ONLY = {"SPY": (D(2016, 6, 1), D(2016, 12, 15)), "XSP": (D(2016, 12, 15),), "AAPL": (D(2019, 12, 16),)}

    def build(self, tmp):
        import backfill as bf
        import frames as fr

        store = bf.Store(str(Path(tmp) / "store"), str(Path(tmp) / "work"))
        store.work.mkdir(parents=True, exist_ok=True)
        cal = nyse_calendar()
        (store.work / "calendar.json").write_text(json.dumps({"years": [str(y) for y in range(2016, 2028)],
                                                              "exceptions": cal.to_json()}))
        frame = pl.DataFrame({"expiration": [D(2024, 3, 13)], "strike": [500.0], "right": ["C"], "minute": [600],
                              "bid": [1.0], "ask": [1.1], "bid_size": [5], "ask_size": [5]}, schema=fr.NBBO_SCHEMA)
        under = pl.DataFrame({"minute": [600], "price": [300.0]}, schema=fr.UNDERLYING_SCHEMA)

        def put(kind, root, day, data):
            rows, digest, size = fr.write(data, store.path(kind, root, day))
            store.journal.append(sl.file_record(kind, root, day, rows=rows, sha256=digest, size=size, source="t",
                                                fetched_at="2026-09-29T00:00:00Z"))

        for root, days in self.CHAINS.items():
            for day in days:
                put("nbbo", root, day, frame)
                put("underlying", root, day, under)
                store.save_expiries(root, day, [day])
        for root, days in self.UNDER_ONLY.items():
            for day in days:
                put("underlying", root, day, under)
        return bf, store, cal

    def names(self, store, kind="nbbo"):
        return sorted(f"{p.parent.name}/{p.stem}" for p in store.root.glob(f"{kind}/*/*.parquet"))

    def manifest(self, store):
        m = pl.read_parquet(store.root / "manifest.parquet")
        return sorted((r["kind"], r["root"], str(r["date"]), r["window"]) for r in m.iter_rows(named=True))

    def inside(self, store):
        """The inside check's facts of a pruned store, from the same store code the sealed box runs (the network, key
        and process facts as a clean box reports them)."""
        import pathlib
        import images

        out = {}
        exec(images.STORE_FACTS, {"store": pathlib.Path(store.root), "out": out})
        return {"network": ["NETWORK-CLOSED x OSError"], "key_file": False, "key_mentions": [], "store_non_parquet": [],
                "processes": "", "work_exists": False, **out}

    def test_image_n_from_a_box_that_holds_2017_19_is_what_the_2020_rules_keep(self):
        with tempfile.TemporaryDirectory() as tmp:
            bf, store, cal = self.build(tmp)
            bf.prune(store, ["train", "validation"], drop_key=False, drop_work=False, calendar=cal, train_from=D(2020, 1, 2))
            on = ["2020-03-16", "2021-06-01", "2024-03-13", "2025-06-11"]
            self.assertEqual(self.names(store), sorted(f"{r}/{d}" for r in ("AAPL", "SPY", "XSP") for d in on),
                             "no chain before 2020: every earlier file is 'pre' to it")
            history = [row for row in self.manifest(store) if row[3] == "history"]
            self.assertEqual(history, [("underlying", r, "2019-12-16", "history") for r in ("AAPL", "SPY", "XSP")])
            calendar = pl.read_parquet(store.root / "calendar.parquet")["date"].to_list()
            self.assertEqual(calendar[0], D(2019, 12, 16))
            self.assertTrue(all(d >= D(2019, 10, 7) for d in calendar))

    def test_image_t_keeps_2017_19_the_history_before_2017_and_each_roots_own_first_day(self):
        with tempfile.TemporaryDirectory() as tmp:
            bf, store, cal = self.build(tmp)
            bf.prune(store, ["train", "validation"], drop_key=False, drop_work=False, calendar=cal, train_from=D(2017, 1, 3),
                     root_first={"XSP": "2020-01-02", "AAPL": "2020-01-02"})
            spy = [f"SPY/{d}" for d in self.CHAINS["SPY"]]
            late = ["2020-03-16", "2021-06-01", "2024-03-13", "2025-06-11"]
            self.assertEqual(self.names(store), sorted(spy + [f"XSP/{d}" for d in late] + [f"AAPL/{d}" for d in late]))
            rows = self.manifest(store)
            self.assertIn(("underlying", "SPY", "2016-12-15", "history"), rows, "SPY's history before 2017-01-03")
            self.assertNotIn("SPY/2016-06-01", self.names(store, "underlying"), "before the 60 sessions: gone")
            self.assertIn(("nbbo", "SPY", "2019-12-16", "train"), rows)
            self.assertIn(("underlying", "XSP", "2019-12-16", "history"), rows, "XSP's history is before ITS first day")
            self.assertIn(("underlying", "AAPL", "2019-12-16", "history"), rows)
            self.assertNotIn("XSP/2016-12-15", self.names(store, "underlying"), "not XSP's history any more")
            self.assertEqual({r[3] for r in rows}, {"history", "train", "validation"})
            self.assertEqual({r[0] for r in rows if r[3] == "history"}, {"underlying"})
            expiries = pl.read_parquet(store.root / "expiries.parquet")
            self.assertEqual(expiries.filter(pl.col("root") == "XSP")["date"].min(), D(2020, 3, 16))
            self.assertEqual(expiries.filter(pl.col("root") == "SPY")["date"].min(), D(2017, 1, 3))
            calendar = pl.read_parquet(store.root / "calendar.parquet")["date"].to_list()
            self.assertEqual(calendar[0], D(2016, 12, 15))
            self.assertIn(D(2019, 12, 16), calendar)
            self.assertNotIn(D(2018, 12, 5), calendar, "no session that day")

    def test_without_root_first_a_partial_early_name_would_enter_train(self):
        """Why the build lists every root fetched only from 2020 at 2020-01-02: pruning keeps files by date, not by stage.
        So the build refuses such an image before it forks (`test_a_build_from_2017_holds_every_name_to_2020`), and the
        inside check refuses it if one is made anyway: every name outside --early-names is held to 2020-01-02."""
        import images

        with tempfile.TemporaryDirectory() as tmp:
            bf, store, cal = self.build(tmp)
            bf.prune(store, ["train", "validation"], drop_key=False, drop_work=False, calendar=cal, train_from=D(2017, 1, 3))
            self.assertIn("AAPL/2019-06-03", self.names(store))
            self.assertIn(("underlying", "AAPL", "2019-12-16", "train"), self.manifest(store))
            facts = self.inside(store)
            problems = images.problems_of(facts, "gym", train_from=T2017)
            why = " (a name enters Train before 2020-01-02 only with its split rows and --early-names)"
            self.assertEqual(problems, ["the first nbbo file of AAPL 2019-06-03 is before 2020-01-02" + why,
                                        "the first underlying file of AAPL 2019-06-03 is before 2019-09-24" + why])
            self.assertEqual(images.problems_of(facts, "gym", train_from=T2017, early_names=["AAPL"]), [],
                             "the operator's leave, once AAPL's split rows are in")
            self.assertTrue(images.problems_of(facts, "gym", train_from=T2017, root_first={"AAPL": "2019-01-02"}),
                            "a first day before 2020 is no leave for a name")

    def test_the_inside_check_passes_image_t_and_refuses_one_whose_first_chain_is_not_its_train_from(self):
        import images

        with tempfile.TemporaryDirectory() as tmp:
            bf, store, cal = self.build(tmp)
            own = {"XSP": T2020, "AAPL": T2020}
            bf.prune(store, ["train", "validation"], drop_key=False, drop_work=False, calendar=cal, train_from=D(2017, 1, 3),
                     root_first=own)
            facts = self.inside(store)
            self.assertEqual(facts["first_by_kind"]["nbbo"], T2017)
            self.assertEqual(images.problems_of(facts, "gym", train_from=T2017, root_first=own), [])
            # The same box without a chain on 2017-01-03 (a day the vendor left empty, say): the Gym would read Train's
            # first day as 2017-03-01 and the pool would refuse every Train run from 2017-01-03.
            for kind in ("nbbo", "underlying"):
                store.path(kind, "SPY", D(2017, 1, 3)).unlink()
            short = self.inside(store)
            self.assertEqual(short["first_by_kind"]["nbbo"], "2017-03-01")
            self.assertEqual(images.problems_of(short, "gym", train_from=T2017, root_first=own),
                             ["the first chain (nbbo) is 2017-03-01, not the image's first Train day 2017-01-03: the Gym "
                              "would read 2017-03-01 as its first Train day and the pool would refuse every Train run "
                              "from 2017-01-03"])

    def test_root_first_and_early_roots_never_mix_and_need_train_from(self):
        import backfill as bf
        import images

        with self.assertRaises(ValueError):
            bf.ImageView(nyse_calendar(), D(2020, 1, 2), ["SPY"], {"XSP": "2021-01-04"})
        with self.assertRaises(ValueError):
            bf.ImageView(nyse_calendar(), None, None, {"XSP": "2021-01-04"})
        with self.assertRaises(ValueError, msg="--early-roots from 2017 would give a left-out root 2016's history only"):
            bf.ImageView(nyse_calendar(), D(2017, 1, 3), ["SPY"])
        bf.ImageView(nyse_calendar(), D(2020, 1, 2), ["SPY"])  # as it was for the images built from 2020
        for kwargs in ({"root_first": {"XSP": "2020-01-02"}},
                       {"train_from": D(2017, 1, 3), "early_roots": ("SPY",), "root_first": {"XSP": "2020-01-02"}},
                       {"train_from": D(2017, 1, 3), "root_first": {"XSP": "2016-12-30"}},
                       {"train_from": D(2016, 12, 30)}):
            with self.assertRaises((SystemExit, ValueError), msg=str(kwargs)):
                images.build("gym", version="t", force=True, **kwargs)
        with self.assertRaises(SystemExit):
            images.build("gate", version="t", force=True, train_from=D(2017, 1, 3))

    def test_a_build_from_2017_holds_every_name_to_2020(self):
        """Refused before any Sail call (no client, no fork): a name without a first day on or after 2020-01-02 and
        without --early-names, a build without --roots, --early-roots from 2017, --early-names from 2020 or naming a core
        root or a root the build does not keep."""
        import boxlib as bl
        import images

        roots = ("SPY", "XSP", "AAPL", "TQQQ")
        both = {"AAPL": T2020, "TQQQ": T2020}
        refused = ({"train_from": D(2017, 1, 3), "roots": roots},
                   {"train_from": D(2017, 1, 3), "roots": roots, "root_first": {"AAPL": T2020}},
                   {"train_from": D(2017, 1, 3), "roots": roots, "root_first": {"AAPL": T2020, "TQQQ": "2018-01-02"}},
                   {"train_from": D(2017, 1, 3), "root_first": both},
                   {"train_from": D(2017, 1, 3), "roots": roots, "root_first": {"AAPL": T2020}, "early_names": "TQQQ,MU"},
                   {"train_from": D(2017, 1, 3), "roots": roots, "root_first": both, "early_names": "SPY"},
                   {"train_from": D(2017, 1, 3), "roots": roots, "early_roots": ("SPY",)},
                   {"train_from": D(2020, 1, 2), "roots": roots, "early_names": "AAPL"})
        for kwargs in refused:
            with self.subTest(kwargs=kwargs), self.assertRaises(SystemExit):
                images.build("gym", version="t", force=True, **kwargs)
        self.assertEqual(images.names_without_a_first_day(roots, {"AAPL": D(2020, 1, 2)}), ["TQQQ"])
        self.assertEqual(images.names_without_a_first_day(roots, {"AAPL": D(2021, 1, 4), "TQQQ": D(2019, 12, 31)},
                                                          ["TQQQ"]), [])
        with self.assertRaises(ValueError):
            images.parse_names("AAPL,aapl")

        class Reached(Exception):
            pass

        accepted = ({"train_from": D(2017, 1, 3), "roots": roots, "root_first": both},
                    {"train_from": D(2017, 1, 3), "roots": roots, "root_first": {"AAPL": T2020, "XSP": T2020},
                     "early_names": "TQQQ"},
                    {"train_from": D(2020, 1, 2), "roots": roots},
                    {"train_from": D(2020, 1, 2), "early_roots": ("SPY",)})
        for kwargs in accepted:
            with self.subTest(kwargs=kwargs), tempfile.TemporaryDirectory() as tmp, bl.using_state(Path(tmp)), \
                    mock.patch.object(bl, "client", side_effect=Reached), self.assertRaises(Reached):
                images.build("gym", version="t", force=True, **kwargs)

    def test_verify_reads_the_recorded_first_day_for_its_root_first(self):
        import images

        entry = {"train_from": T2017, "root_first": {"XSP": T2020}, "early_names": None}
        self.assertEqual(images.verify_arguments(entry), {"train_from": T2017, "root_first": {"XSP": T2020},
                                                          "early_names": None})
        self.assertEqual(images.verify_arguments(entry, root_first="XSP=2020-01-02,AAPL=2020-01-02", early_names="TQQQ"),
                         {"train_from": T2017, "root_first": {"AAPL": T2020, "XSP": T2020}, "early_names": ["TQQQ"]},
                         "--root-first without --train-from, read against the recorded 2017-01-03")
        self.assertEqual(images.verify_arguments({}, train_from=T2020)["root_first"], None)
        for entry_, kwargs in (({}, {"root_first": "XSP=2020-01-02"}),
                               ({"train_from": T2020}, {"root_first": "XSP=2019-01-02"}),
                               (entry, {"early_names": "SPY"})):
            with self.subTest(kwargs=kwargs), self.assertRaises(SystemExit):
                images.verify_arguments(entry_, **kwargs)

    def test_the_prune_arguments_and_the_cli(self):
        import images

        spec = images.KINDS["gym"]
        self.assertEqual(images.prune_arguments(spec), spec["prune"], "an image built as before gets the same prune")
        self.assertEqual(images.prune_arguments(spec, train_from=D(2020, 1, 2)), spec["prune"] + " --train-from 2020-01-02")
        self.assertEqual(images.prune_arguments(spec, train_from=D(2017, 1, 3), root_first={"XSP": D(2020, 1, 2), "AAPL": D(2020, 1, 2)}),
                         spec["prune"] + " --train-from 2017-01-03 --root-first AAPL=2020-01-02,XSP=2020-01-02")
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            bf, store, cal = self.build(tmp)
            out = bf._main(["--store", str(store.root), "--work", str(store.work), "prune", "--keep", "train,validation",
                            "--train-from", T2017, "--root-first", "XSP=2020-01-02,AAPL=2020-01-02"])
            self.assertEqual(out, 0)
            self.assertNotIn("XSP/2017-03-01", self.names(store))
            with self.assertRaises(ValueError):
                bf._main(["--store", str(store.root), "--work", str(store.work), "prune", "--keep", "train,validation",
                          "--root-first", "XSP=2020-01-02"])

    def test_the_inside_check_holds_each_root_to_its_own_day(self):
        import images

        facts = {"network": ["NETWORK-CLOSED x OSError"], "key_file": False, "key_mentions": [], "store_non_parquet": [],
                 "processes": "", "dated_after_validation": 0, "manifest_windows": ["history", "train", "validation"],
                 "manifest_last": "2025-12-31", "calendar_last": "2025-12-31", "expiries_last_date": "2025-12-31",
                 "work_exists": False, "gate_mark": False, "first_date": "2016-10-06", "manifest_first": "2016-10-06",
                 "calendar_first": "2016-10-06", "first_by_kind": {"nbbo": "2017-01-03", "oi": "2017-01-03", "underlying": "2016-10-06"},
                 "history_kinds": ["underlying"],
                 "first_by_root": {"nbbo": {"SPY": "2017-01-03", "XSP": "2020-01-02", "AAPL": "2020-01-02"},
                                   "underlying": {"SPY": "2016-10-06", "XSP": "2019-10-07", "AAPL": "2019-10-07"}}}
        own = {"XSP": T2020, "AAPL": T2020}
        self.assertEqual(images.problems_of(facts, "gym", train_from=T2017, root_first=own), [])
        self.assertEqual(images.problems_of(facts, "gym", train_from=T2017), [], "as a 2017 image without per-root days")
        self.assertTrue(images.problems_of(facts, "gym", train_from=T2020), "a 2017 image is not a 2020 one")
        early_xsp = copy.deepcopy(facts)
        early_xsp["first_by_root"]["nbbo"]["XSP"] = "2017-01-03"
        self.assertTrue(any("first nbbo file of XSP" in p for p in images.problems_of(early_xsp, "gym", train_from=T2017, root_first=own)))
        far = copy.deepcopy(facts)
        far["first_by_root"]["underlying"]["AAPL"] = "2019-06-03"
        self.assertTrue(any("underlying file of AAPL" in p for p in images.problems_of(far, "gym", train_from=T2017, root_first=own)))
        blind = {k: v for k, v in facts.items() if k != "first_by_root"}
        self.assertTrue(any("first_by_root" in p for p in images.problems_of(blind, "gym", train_from=T2017, root_first=own)))
        self.assertTrue(any("first_by_root" in p for p in images.problems_of(blind, "gym", train_from=T2017)),
                        "from 2017 the names are checked root by root even without --root-first")
        early_name = copy.deepcopy(facts)
        early_name["first_by_root"]["nbbo"]["TQQQ"] = "2017-01-03"
        early_name["first_by_root"]["underlying"]["TQQQ"] = "2016-10-06"
        found = images.problems_of(early_name, "gym", train_from=T2017, root_first=own)
        self.assertEqual(len(found), 2, found)
        self.assertTrue(all("TQQQ" in p and "--early-names" in p for p in found))
        self.assertIn("the first underlying file of TQQQ 2016-10-06 is before 2019-09-24", found[1])
        self.assertEqual(images.problems_of(early_name, "gym", train_from=T2017, root_first=own, early_names=["TQQQ"]), [])
        late_chain = {**facts, "first_by_kind": {**facts["first_by_kind"], "nbbo": "2019-11-01", "oi": "2019-11-01"}}
        self.assertTrue(any("first chain (nbbo) is 2019-11-01" in p
                            for p in images.problems_of(late_chain, "gym", train_from=T2017, root_first=own)),
                        "the reviewer's image: built from 2017, first chain in November 2019")
        too_far = {**facts, "first_by_kind": {**facts["first_by_kind"], "underlying": "2016-09-01"}}
        self.assertTrue(images.problems_of(too_far, "gym", train_from=T2017), "more than 100 days before 2017-01-03")
        self.assertIn("first_by_root", images.INSIDE_CHECK)


@unittest.skipIf(pl is None or not HAVE_GYM, "polars, numpy and pyarrow are needed (they are on the data box and in CI)")
class BridgeThroughThePrune(unittest.TestCase):
    """The bridge end to end: one synthetic data box holding late 2019 as an earlier-years fetch would (chains, with
    the underlying stage 9 journaled first), pruned as image N (from 2020) and image T (from 2017); the same program
    from 2020-01-02 on both gives the same trades, days and years."""

    def test_the_same_run_on_both_images(self):
        import backfill as bf
        from league.gym import batch, synth

        days = _synthetic_days()
        cal = nyse_calendar()
        self.assertTrue(all(cal.is_trading(d) for d in days))
        with tempfile.TemporaryDirectory(prefix="train2017-box-") as tmp:
            box = Path(tmp) / "box"
            synth.generate(box / "store", roots=("SPY",), days=days, strikes_each_side=3, max_dte=3, seed=5)
            store = bf.Store(str(box / "store"), str(box / "work"))
            store.work.mkdir(parents=True, exist_ok=True)
            (store.work / "calendar.json").write_text(json.dumps({"years": [str(y) for y in range(2016, 2028)],
                                                                  "exceptions": cal.to_json()}))
            for kind in ("nbbo", "underlying", "oi"):
                for path in sorted((store.root / kind / "SPY").glob("*.parquet")):
                    day = D.fromisoformat(path.stem)
                    data = path.read_bytes()
                    store.journal.append(sl.file_record(kind, "SPY", day, rows=1, sha256=hashlib.sha256(data).hexdigest(),
                                                        size=len(data), source="synthetic", fetched_at="2026-09-29T00:00:00Z"))
            results = {}
            for name, first in (("n", D(2020, 1, 2)), ("t", D(2017, 1, 3))):
                shutil.copytree(box, Path(tmp) / name)
                image = bf.Store(str(Path(tmp) / name / "store"), str(Path(tmp) / name / "work"))
                bf.prune(image, ["train", "validation"], drop_key=False, drop_work=False, calendar=cal, train_from=first)
                results[name] = batch.run_batch([("h", HISTORY_PROGRAM, {})], store_root=str(image.root), window="train",
                                                roots=["SPY"], workers=1, split=2, start=D(2020, 1, 2))
            n, t = results["n"], results["t"]
            self.assertEqual((n["batch"]["train_first"], t["batch"]["train_first"]), (T2020, "2019-12-02"))
            rn, rt = n["results"][0], t["results"][0]
            self.assertGreater(len(rn["trades"]), 3)
            self.assertEqual((rn["trades"], rn["daily"], rn["by_year"]), (rt["trades"], rt["daily"], rt["by_year"]))


if __name__ == "__main__":
    unittest.main()
