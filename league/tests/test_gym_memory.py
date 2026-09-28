"""The replay frees each day at its close, not at Python's next full collection, and freeing it early changes nothing a
run returns. Synthetic stores only.

Each snapshot a program decides on caches its ChainView, and the view points back at the snapshot: a
reference cycle that held the snapshot, and through its greeks source the root-day's GreekBlocks and
DayChain, until a full collection. On a synthetic store (SPY and QQQ, the four benchmark programs each)
a worker's RSS was 637 MiB at day 10, 834 at day 40 and 1245 at day 150 (Sept 27, 2026); the replay
now breaks the cycle when it drops a snapshot (`ctx.Snapshot.release`, `engine.DayData.close`), and
it was 205, 221 and 234 MiB. The counts below are taken with the automatic collector OFF, so what
they see is what reference counting alone frees, whatever the interpreter's collection thresholds.

What the engine no longer holds is not all a worker holds: a view (or a ctx) a program keeps in its STATE keeps its
snapshot, and so that root-day's chain and greek blocks, as long as the program keeps it. A program that keeps one view
a day pins about one root-day a day (the review of #401: 237 MiB at day 40 without one, 2363 MiB with one on each of two
roots), so a worker's memory still grows with the days of a segment when its programs make it.
"""

import datetime as dt
import gc
import shutil
import tempfile
import unittest

try:
    import numpy  # noqa: F401
    import pyarrow  # noqa: F401
    HAVE = True
except ImportError:  # pragma: no cover
    HAVE = False

if HAVE:
    from league.gym import bench
    from league.gym import ctx as C
    from league.gym import engine as E
    from league.gym import runtime as R
    from league.gym import store as S
    from league.gym import synth
    from league.gym.day import ordinal
    from league.gym.events import EventCalendar

DAY_OBJECTS = ("DayChain", "GreekBlocks", "Snapshot", "ChainView")

# Keeps each day's first ctx.chain and reads its deltas the NEXT day, for the first time: a view on back-month contracts
# (4-7 days out) no other program of the batch solves, so the read reaches the closed day's GreekBlocks. The values
# go into a trade's tag, so a wrong or missing read changes the result.
KEEPER = '''
import numpy as np
NEEDS = {"roots": ["SPY"], "dte": [4, 7], "band": 0.2, "cadence": 30}
PARAMS = {}
STATE = {"held": None, "last": 100000}
def decide(ctx):
    out = [{"close": p["id"]} for p in ctx.positions if p["held_minutes"] >= 60]
    if ctx.minute < STATE["last"]:
        held = STATE["held"]
        if held is not None and not ctx.positions and not ctx.orders and ctx.chain.n:
            delta = held.delta
            tag = "d" + str(round(float(np.nansum(delta)), 6)) + ":" + str(int(np.isfinite(delta).sum())) + ":" + str(held.minute)
            dte = int(ctx.chain.expiries[0])
            out.append({"open": "debit_vertical", "legs": [{"side": "long", "right": "C", "dte": dte, "atm": 0},
                        {"side": "short", "right": "C", "rel": 0, "offset": 2.0}], "qty": 1, "tag": tag})
        STATE["held"] = ctx.chain
    STATE["last"] = ctx.minute
    return out
'''

# Keeps the whole ctx from one decision to the next. Within a day it reads the minute before's mids and underlying;
# at a new day's first decision it reads the previous day's last ctx, its gammas for the first time, and trades on it.
HOLDER = '''
import numpy as np
NEEDS = {"roots": ["QQQ"], "dte": [0, 7], "band": 0.2, "cadence": 13}
PARAMS = {}
STATE = {"prev": None, "seen": 0.0}
def decide(ctx):
    prev = STATE["prev"]
    STATE["prev"] = ctx
    out = [{"close": p["id"]} for p in ctx.positions if p["held_minutes"] >= 45]
    if prev is None:
        return out
    if ctx.minute >= prev.minute:
        STATE["seen"] += float(np.nansum(prev.chain.mid)) + prev.under.price
        return out
    gamma = prev.chain.gamma
    tag = "g" + str(round(float(np.nansum(gamma)), 8)) + ":" + str(prev.minute) + ":" + str(len(prev.positions)) + ":" + str(round(STATE["seen"], 2))
    if not ctx.positions and not ctx.orders and ctx.chain.n:
        out.append({"open": "debit_vertical", "legs": [{"side": "long", "right": "P", "dte": int(ctx.chain.expiries[0]), "atm": 0},
                    {"side": "short", "right": "P", "rel": 0, "offset": -2.0}], "qty": 1, "limit": {"mid": 1}, "tif": 20, "tag": tag})
    return out
'''


def live_counts() -> dict:
    counts = dict.fromkeys(DAY_OBJECTS, 0)
    for obj in gc.get_objects():
        name = type(obj).__name__
        if name in counts:
            counts[name] += 1
    return counts


def without_timing(result: dict) -> dict:
    out = {k: v for k, v in result.items() if k != "seconds"}
    out["runtime"] = {k: v for k, v in result["runtime"].items() if k != "decide_seconds"}
    return out


@unittest.skipUnless(HAVE, "numpy/pyarrow not installed (requirements-gym.txt)")
class DayMemory(unittest.TestCase):
    DAYS = 6

    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix="gym-mem-")
        cls.days = synth.weekdays(dt.date(2023, 5, 1), cls.DAYS)
        synth.generate(cls.dir, roots=("SPY", "QQQ"), days=cls.days, strikes_each_side=8, max_dte=7, seed=5)
        cls.store = S.Store(cls.dir)
        cls.model = synth.uniform_model(0.08, ("SPY", "QQQ"), levels=(2, 3), size=5)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def programs(self, holders: bool = False):
        # The benchmark's workloads on both roots: a light cadence-10 trader, the two examples, and one that reads
        # every greek every minute (so every minute has a cached view and a greek block behind it); with `holders`,
        # two programs that keep what they were handed past its minute and its day.
        out = [R.load_program(code, name=f"{name}-{root}") for root in ("SPY", "QQQ")
               for name, code in bench.programs_for(root).items()]
        if holders:
            out += [R.load_program(KEEPER, name="keeper"), R.load_program(HOLDER, name="holder")]
        return out

    def run_engine(self, progress=None, keep=None, holders=False):
        cfg = E.RunConfig(window="train", roots=("SPY", "QQQ"), fill_model=self.model)
        return E.run(self.programs(holders), self.store, cfg, days=self.days, progress=progress, keep=keep)

    def test_a_days_objects_are_freed_by_reference_counting(self):
        gc.collect()
        before = live_counts()
        per_day = []
        was_enabled = gc.isenabled()
        gc.disable()
        try:
            results = self.run_engine(progress=lambda i, total, day: per_day.append(live_counts()))
            after = live_counts()
        finally:
            if was_enabled:
                gc.enable()
        self.assertTrue(all(r["status"] == "ok" for r in results), [r["runtime"] for r in results])
        self.assertGreater(sum(r["summary"]["trades"] for r in results), 0)
        self.assertEqual(len(per_day), self.DAYS)
        # At the end of each day (after the day is closed) nothing of it is left; before the fix every day's
        # chains, blocks and ~390 snapshots a root stayed until a full collection.
        for n, counts in enumerate(per_day, 1):
            for name in DAY_OBJECTS:
                self.assertLessEqual(counts[name] - before[name], 0, f"day {n}: {counts}")
        for name in DAY_OBJECTS:
            self.assertLessEqual(after[name] - before[name], 0, f"after the run: {after}")

    def test_freeing_early_changes_nothing_a_run_returns(self):
        # The replay before the fix: no snapshot releases its views, no day is closed early. The batch includes the
        # two programs that read what they kept after its day closed.
        keep_new, keep_old = [], []
        new = self.run_engine(keep=keep_new, holders=True)
        release, close = C.Snapshot.release, E.DayData.close
        C.Snapshot.release = lambda self: None
        E.DayData.close = lambda self: None
        try:
            old = self.run_engine(keep=keep_old, holders=True)
        finally:
            C.Snapshot.release, E.DayData.close = release, close
        for results in (new, old):
            for r in results:
                self.assertEqual(r["status"], "ok", (r["program"], r["runtime"]))
                self.assertEqual(r["runtime"]["errors"], 0, (r["program"], r["runtime"]["messages"]))
        self.assertEqual([r["run_id"] for r in new], [r["run_id"] for r in old])
        self.assertEqual([r["result_sha"] for r in new], [r["result_sha"] for r in old])
        self.assertEqual([without_timing(r) for r in new], [without_timing(r) for r in old])
        # Every fill (passive ones decided by the seeded draws included) and every day's equity, as the accounts saw them.
        self.assertEqual([a.fill_rows for a in keep_new], [a.fill_rows for a in keep_old])
        self.assertEqual([a.daily for a in keep_new], [a.daily for a in keep_old])
        self.assertGreater(sum(len(a.fill_rows) for a in keep_new), 0)
        self.assertGreater(sum(1 for a in keep_new for row in a.fill_rows if not row[3]), 0)  # passive fills: the draws ran
        # The holders traded on what they read after the close: a day's trades carry it in their tags, finite.
        by_name = {r["program"]: r for r in new}
        for name, mark in (("keeper", "d"), ("holder", "g")):
            tags = [t["tag"] for t in by_name[name]["trades"]]
            self.assertGreaterEqual(len(tags), 2, (name, tags))
            for tag in tags:
                self.assertTrue(tag.startswith(mark) and "nan" not in tag, (name, tag))

    def test_a_released_snapshots_view_still_answers(self):
        # A program may keep a view past its minute: releasing the snapshot's cache leaves the view working.
        snap = C.Snapshot("SPY", 600, 450.0, [1, 1], [450.0, 450.0], [True, False], [2.0, 1.9], [2.1, 2.0], rate=0.04)
        view = snap.view(snap.slice_index(0, 5, 0.1), key=("k",))
        self.assertIs(snap.view(snap.slice_index(0, 5, 0.1), key=("k",)), view)
        snap.release()
        self.assertEqual(view.iv.shape, (2,))
        self.assertTrue(numpy.isfinite(view.iv).all())
        self.assertIsNot(snap.view(snap.slice_index(0, 5, 0.1), key=("k",)), view)

    def test_a_closed_day_refuses_every_read(self):
        # Never "no chain today" after the close: that would settle every expiring position as expired_without_data.
        day = self.days[0]
        data = E.DayData(self.store, day, ("SPY",), EventCalendar(self.store.trading_days(), self.store.session),
                         E.History(11), ordinal(day))
        self.assertIsNotNone(data.snapshot("SPY", 5))
        data.close()
        self.assertTrue(data.closed)
        for read in (lambda: data.snapshot("SPY", 5), lambda: data.blocks("SPY"), lambda: data.under("SPY", 5, 0),
                     lambda: data.chains.get("SPY"), lambda: data.chains["SPY"], lambda: "SPY" in data.chains,
                     lambda: list(data.chains.items())):
            with self.assertRaises(E.DayClosed):
                read()


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
