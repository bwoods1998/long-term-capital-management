"""A Gym worker's memory does not grow with the days of its segment, and freeing each day early changes
nothing a run returns. Synthetic stores only.

Each snapshot a program decides on caches its ChainView, and the view points back at the snapshot: a
reference cycle that held the snapshot, and through its greeks source the root-day's GreekBlocks and
DayChain, until a full collection. On a synthetic store (SPY and QQQ, the four benchmark programs each)
a worker's RSS was 637 MiB at day 10, 834 at day 40 and 1245 at day 150 (Sept 27, 2026); the replay
now breaks the cycle when it drops a snapshot (`ctx.Snapshot.release`, `engine.DayData.close`), and
it was 205, 221 and 234 MiB. The counts below are taken with the automatic collector OFF, so what
they see is what reference counting alone frees, whatever the interpreter's collection thresholds.
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

DAY_OBJECTS = ("DayChain", "GreekBlocks", "Snapshot", "ChainView")


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
        synth.generate(cls.dir, roots=("SPY", "QQQ"), days=cls.days, strikes_each_side=8, max_dte=3, seed=5)
        cls.store = S.Store(cls.dir)
        cls.model = synth.uniform_model(0.08, ("SPY", "QQQ"), levels=(2, 3), size=5)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def programs(self):
        # The benchmark's workloads on both roots: a light cadence-10 trader, the two examples, and one that reads
        # every greek every minute (so every minute has a cached view and a greek block behind it).
        return [R.load_program(code, name=f"{name}-{root}") for root in ("SPY", "QQQ")
                for name, code in bench.programs_for(root).items()]

    def run_engine(self, progress=None, keep=None):
        cfg = E.RunConfig(window="train", roots=("SPY", "QQQ"), fill_model=self.model)
        return E.run(self.programs(), self.store, cfg, days=self.days, progress=progress, keep=keep)

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
        # The replay before the fix: no snapshot releases its views, no day is closed early.
        keep_new, keep_old = [], []
        new = self.run_engine(keep=keep_new)
        release, close = C.Snapshot.release, E.DayData.close
        C.Snapshot.release = lambda self: None
        E.DayData.close = lambda self: None
        try:
            old = self.run_engine(keep=keep_old)
        finally:
            C.Snapshot.release, E.DayData.close = release, close
        self.assertEqual([r["run_id"] for r in new], [r["run_id"] for r in old])
        self.assertEqual([r["result_sha"] for r in new], [r["result_sha"] for r in old])
        self.assertEqual([without_timing(r) for r in new], [without_timing(r) for r in old])
        # Every fill (passive ones decided by the seeded draws included) and every day's equity, as the accounts saw them.
        self.assertEqual([a.fill_rows for a in keep_new], [a.fill_rows for a in keep_old])
        self.assertEqual([a.daily for a in keep_new], [a.daily for a in keep_old])
        self.assertGreater(sum(len(a.fill_rows) for a in keep_new), 0)
        self.assertGreater(sum(1 for a in keep_new for row in a.fill_rows if not row[3]), 0)  # passive fills: the draws ran

    def test_a_released_snapshots_view_still_answers(self):
        # A program may keep a view past its minute: releasing the snapshot's cache leaves the view working.
        snap = C.Snapshot("SPY", 600, 450.0, [1, 1], [450.0, 450.0], [True, False], [2.0, 1.9], [2.1, 2.0], rate=0.04)
        view = snap.view(snap.slice_index(0, 5, 0.1), key=("k",))
        self.assertIs(snap.view(snap.slice_index(0, 5, 0.1), key=("k",)), view)
        snap.release()
        self.assertEqual(view.iv.shape, (2,))
        self.assertTrue(numpy.isfinite(view.iv).all())
        self.assertIsNot(snap.view(snap.slice_index(0, 5, 0.1), key=("k",)), view)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
