"""A program gets nothing from the future, the date or the year; the safety check refuses what could
reach them; the runtime contains a misbehaving program. Synthetic stores only."""

import datetime as dt
import math
import shutil
import tempfile
import unittest

try:
    import numpy as np
    import pyarrow  # noqa: F401
    HAVE = True
except ImportError:  # pragma: no cover
    HAVE = False

if HAVE:
    from league.gym import engine as E
    from league.gym import runtime as R
    from league.gym import store as S
    from league.gym import synth
    from league.gym.ctx import ChainView, Ctx, UnderlyingView
    from league.gym.safety import CodeRefused, check_program

D1, D2 = dt.date(2024, 3, 14), dt.date(2024, 3, 15)

WATCHER = '''
import numpy as np
NEEDS = {"roots": ["SPY"], "dte": [0, 3], "band": 0.2, "cadence": 1, "history": 5}
PARAMS = {}
SEEN = {"rows": [], "attempts": []}
def decide(ctx):
    ch = ctx.chain
    pick = np.flatnonzero((ch.strike == 400.0) & ch.is_call & (ch.dte == 1))
    bid = float(ch.bid[pick[0]]) if pick.size else -1.0
    SEEN["rows"].append([ctx.minute, bid, int(ctx.under.prices.size), float(ctx.under.price), int(ctx.under.closes.size),
                         float(ctx.under.prior_close) if ctx.under.closes.size else -1.0])
    SEEN["attempts"].append([getattr(ctx, "date", None), getattr(ctx, "year", None), getattr(ctx, "day", None),
                             getattr(ctx, "today", None), getattr(ctx.chain, "expiration", None)])
    if ctx.minute == 700:
        return [{"note": ctx.date}]
    return []
'''


@unittest.skipUnless(HAVE, "numpy/pyarrow not installed (requirements-gym.txt)")
class NothingFromTheFuture(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="gym-future-")
        w = synth.Writer(self.dir)
        w.calendar([D1, D2])
        for day, base in ((D1, 400.0), (D2, 410.0)):
            synth.flat_day(w, "SPY", day, [
                {"expiration": day + dt.timedelta(days=1), "strike": 400, "right": "C",
                 "quotes": {571: (2.00, 2.10), 700: (5.00, 5.10)}}],
                prices={570: base, 700: base + 5.0})
        w.finish()
        self.store = S.Store(self.dir)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_each_decision_sees_its_own_minute_only(self):
        keep = []
        [r] = E.run([R.load_program(WATCHER, name="watcher")], self.store, E.RunConfig(window="train", roots=("SPY",)), keep=keep)
        seen = keep[0].runner._namespace["SEEN"]
        rows = seen["rows"]
        first_day = [row for row in rows[: len(rows) // 2]]
        by_minute = {row[0]: row for row in first_day}
        # The quote and the price that change at 700 are invisible at 699 and visible at 700.
        self.assertEqual(by_minute[699][1], 2.00)
        self.assertEqual(by_minute[700][1], 5.00)
        self.assertEqual(by_minute[699][3], 400.0)
        self.assertEqual(by_minute[700][3], 405.0)
        # Today's prices run from the open to now, never further.
        for minute, _, n_prices, _, _, _ in first_day:
            self.assertEqual(n_prices, minute - 570 + 1)
        # The second day's history holds the first day's close and nothing of its own.
        second = [row for row in rows if row[4] == 1]
        self.assertEqual(len(second), len(rows) // 2)
        self.assertTrue(all(row[5] == 405.0 for row in second))       # day one's close
        self.assertTrue(all(row[4] == 0 for row in first_day))         # no history before the first day
        # The date, the year and any expiry date are simply not there.
        for attempt in seen["attempts"]:
            self.assertEqual(attempt, [None, None, None, None, None])
        # ctx.date raised (an AttributeError the runtime counted), and the run went on.
        self.assertEqual(r["runtime"]["errors"], 2)
        self.assertTrue(any("AttributeError" in m for m in r["runtime"]["messages"]))
        self.assertEqual(r["status"], "ok")

    def test_ctx_holds_no_date_and_its_arrays_are_read_only_copies(self):
        grabbed = []

        class Spy(R.Runner):
            def decide(self, ctx):
                grabbed.append(ctx)
                return []

        program = R.load_program(WATCHER, name="watcher")
        acc = E.Account(program, E.RunConfig(window="train", roots=("SPY",)), ("SPY",))
        acc.runner = Spy(program)
        data = E.DayData(self.store, D1, ("SPY",), __import__("league.gym.events", fromlist=["x"]).EventCalendar(
            self.store.trading_days(), self.store.session), E.History(5), S.ordinal(D1))
        acc.begin_day(data)
        data.advance(100)
        acc.step(data, 100, True)
        [ctx] = grabbed
        iso = __import__("re").compile(r"20[0-9]{2}")

        def walk(value, depth=0):
            self.assertFalse(isinstance(value, (dt.date, dt.datetime)), value)
            if isinstance(value, str):
                self.assertIsNone(iso.search(value), value)
            elif isinstance(value, dict):
                for k, v in value.items():
                    walk(k, depth + 1)
                    walk(v, depth + 1)
            elif isinstance(value, (list, tuple)):
                for v in value:
                    walk(v, depth + 1)
            elif isinstance(value, (ChainView, UnderlyingView, Ctx)):
                for name in type(value).__slots__:
                    if not name.startswith("_"):
                        walk(getattr(value, name), depth + 1)
            elif isinstance(value, np.ndarray):
                # never a view of the engine's grid (it would carry the rest of the day), never writeable
                self.assertNotIsInstance(value.base, np.ndarray)
                self.assertFalse(value.flags.writeable)
                with self.assertRaises(ValueError):
                    value.setflags(write=True)
            elif isinstance(value, (int, float)) and not isinstance(value, bool) and depth <= 1:
                self.assertFalse(2019 <= value <= 2030, value)

        walk(ctx)
        for name in ("iv", "delta", "gamma", "theta", "vega"):
            arr = getattr(ctx.chain, name)
            self.assertNotIsInstance(arr.base, np.ndarray)
            self.assertFalse(arr.flags.writeable)
        with self.assertRaises(ValueError):
            ctx.chain.bid[0] = 1.0

    def test_holdout_and_forward_days_never_open_without_the_gate(self):
        w = synth.Writer(self.dir + "-sealed")
        day = dt.date(2026, 3, 2)
        w.calendar([day])
        synth.flat_day(w, "SPY", day, [{"expiration": day, "strike": 400, "right": "C", "quotes": {571: (1.0, 1.1)}}], prices=400.0)
        w.finish()
        try:
            store = S.Store(self.dir + "-sealed")
            with self.assertRaises(S.StoreRefused):
                store.chain("SPY", day)
            with self.assertRaises(S.StoreRefused):
                store.days("holdout", ["SPY"])
            with self.assertRaises(S.StoreRefused):
                E.run([R.load_program(WATCHER)], store, E.RunConfig(window="train"), days=[day])
            with self.assertRaises(S.StoreRefused):
                S.mint_gate_capability(self.dir + "-sealed", "the gate")   # no GATE mark: a Gym box
            with self.assertRaises(TypeError):
                S.GateCapability()
            w.gate_mark()
            gate = S.mint_gate_capability(self.dir + "-sealed", "holdout look for lineage 7")
            sealed = S.Store(self.dir + "-sealed", gate=gate)
            self.assertEqual(sealed.days("holdout", ["SPY"]), [day])
            self.assertEqual(sealed.chain("SPY", day).contracts, 1)
            with self.assertRaises(S.StoreRefused):
                S.Store(self.dir + "-sealed", gate="yes")
            self.assertEqual(S.window_of(dt.date(2024, 12, 31)), "train")
            self.assertEqual(S.window_of(dt.date(2025, 1, 2)), "validation")
            self.assertEqual(S.window_of(dt.date(2026, 9, 25)), "holdout")
            self.assertEqual(S.window_of(dt.date(2026, 9, 28)), "forward")
        finally:
            shutil.rmtree(self.dir + "-sealed", ignore_errors=True)


GOOD = "import math\nimport numpy as np\nNEEDS = {'roots': ['SPY']}\nPARAMS = {}\ndef decide(ctx):\n    return []\n"


@unittest.skipUnless(HAVE, "numpy/pyarrow not installed (requirements-gym.txt)")
class TheSafetyCheck(unittest.TestCase):
    def refused(self, body, fragment=""):
        code = "import numpy as np\nNEEDS = {'roots': ['SPY']}\nPARAMS = {}\n" + body
        with self.assertRaises(CodeRefused) as caught:
            check_program(code)
        self.assertIn(fragment, str(caught.exception))

    def test_a_plain_program_passes(self):
        check_program(GOOD)
        R.load_program(GOOD)

    def test_date_literals_are_refused(self):
        self.refused("def decide(ctx):\n    return 2024\n", "year")
        self.refused("def decide(ctx):\n    return 2019.0\n", "year")
        self.refused("def decide(ctx):\n    return 20240315\n", "date")
        self.refused("def decide(ctx):\n    return '2024-03-15'\n", "date")
        self.refused("def decide(ctx):\n    return 'after the 2022 selloff'\n", "year")
        self.refused("X = {'2025/01/02': 1}\ndef decide(ctx):\n    return []\n", "date")
        check_program(GOOD.replace("return []", "return [2018, 2031, 1500, 960, 'q3']"))

    def test_the_ways_out_are_refused(self):
        self.refused("import datetime\ndef decide(ctx):\n    return []\n", "math and numpy")
        self.refused("import os\ndef decide(ctx):\n    return []\n", "math and numpy")
        self.refused("from numpy import load\ndef decide(ctx):\n    return []\n", "load")
        self.refused("import numpy.random\ndef decide(ctx):\n    return []\n", "math and numpy")
        self.refused("def decide(ctx):\n    return np.random.rand()\n", "random")
        self.refused("def decide(ctx):\n    return np.datetime64('now')\n", "datetime64")
        self.refused("def decide(ctx):\n    return ctx.chain.bid.base\n", "base")
        self.refused("def decide(ctx):\n    return ctx.chain._snap\n", "_snap")
        self.refused("def decide(ctx):\n    return ctx.__class__\n", "__class__")
        self.refused("def decide(ctx):\n    return getattr(ctx, 'chain' + '_')\n", "literal")
        self.refused("def decide(ctx):\n    print(ctx)\n    return []\n", "print")
        self.refused("def decide(ctx):\n    return open('/data/store/VERSION').read()\n", "open")
        self.refused("def decide(ctx):\n    return eval('1')\n", "eval")
        self.refused("class A:\n    pass\ndef decide(ctx):\n    return []\n", "classes")
        self.refused("def decide(ctx):\n    ctx.cash = 1\n    return []\n", "assigning")
        self.refused("def decide(ctx):\n    return np.load('x')\n", "load")
        self.refused("def decide(ctx):\n    ctx.chain.bid.tofile('x')\n    return []\n", "tofile")
        self.refused("def decide(ctx):\n    return hash('x')\n", "hash")
        self.refused("def decide(ctx, extra):\n    return []\n", "one argument")
        with self.assertRaises(CodeRefused):
            check_program("NEEDS = {}\ndef decide(ctx):\n    return []\n")  # no PARAMS

    def test_needs_and_params_are_validated(self):
        with self.assertRaises(R.NeedsRefused):
            R.load_program(GOOD.replace("{'roots': ['SPY']}", "{'roots': ['SPY'], 'cadence': 0}"))
        with self.assertRaises(R.NeedsRefused):
            R.load_program(GOOD.replace("{'roots': ['SPY']}", "{'roots': []}"))
        with self.assertRaises(R.NeedsRefused):
            R.load_program(GOOD.replace("{'roots': ['SPY']}", "{'roots': ['SPY'], 'fetch': 'x'}"))
        p = R.load_program(GOOD.replace("PARAMS = {}", "PARAMS = {'a': 1.0}"), params={"a": 2})
        self.assertEqual(p.params, {"a": 2})
        with self.assertRaises(R.NeedsRefused):
            R.load_program(GOOD.replace("PARAMS = {}", "PARAMS = {'a': 1.0}"), params={"b": 2})
        with self.assertRaises(R.NeedsRefused):
            R.load_program(GOOD.replace("PARAMS = {}", "PARAMS = {'a': 1.0}"), params={"a": "x"})


@unittest.skipUnless(HAVE, "numpy/pyarrow not installed (requirements-gym.txt)")
class TheRuntime(unittest.TestCase):
    def test_a_runaway_decide_is_stopped_and_counted(self):
        code = GOOD.replace("    return []", "    x = 0\n    while True:\n        x += 1")
        runner = R.load_program(code).start(timeout=0.05, max_errors=2)
        self.assertEqual(runner.decide(None), [])
        self.assertEqual(runner.timeouts, 1)
        self.assertEqual(runner.decide(None), [])
        self.assertTrue(runner.disqualified)
        self.assertEqual(runner.decide(None), [])
        self.assertEqual(runner.calls, 2)

    def test_errors_are_caught_with_the_programs_line(self):
        runner = R.load_program(GOOD.replace("    return []", "    return 1 / 0")).start()
        self.assertEqual(runner.decide(None), [])
        self.assertIn("line 6", runner.messages[0])
        self.assertIn("ZeroDivisionError", runner.messages[0])

    def test_intents_are_normalized_from_numpy(self):
        code = GOOD.replace("    return []", "    return [{'close': np.int64(3)}, {'bogus': 1}, {'cancel': 1, 'close': 2}]")
        runner = R.load_program(code).start()
        self.assertEqual(runner.decide(None), [{"close": 3}])
        self.assertEqual(runner.errors, 2)

    def test_state_is_fresh_for_each_run(self):
        code = GOOD.replace("PARAMS = {}", "PARAMS = {}\nS = {'n': 0}").replace("    return []", "    S['n'] += 1\n    return [{'close': S['n']}]")
        program = R.load_program(code)
        a, b = program.start(), program.start()
        a.decide(None)
        self.assertEqual(a.decide(None), [{"close": 2}])
        self.assertEqual(b.decide(None), [{"close": 1}])

    def test_imports_at_run_time_reach_only_math_and_numpy(self):
        self.assertIs(R._importer("math"), math)
        self.assertIs(R._importer("numpy"), np)
        for name in ("os", "sys", "subprocess", "pickle", "socket", "importlib"):
            with self.assertRaises(ImportError):
                R._importer(name)

    def test_numpy_works_inside_a_program_in_a_fresh_interpreter(self):
        # numpy's C code imports its own submodules lazily through the CALLING frame's builtins (the
        # program's); a warm process hides that, so this runs where nothing is imported yet.
        import subprocess
        import sys
        code = ("import numpy as np\nNEEDS = {'roots': ['SPY']}\nPARAMS = {}\ndef decide(ctx):\n"
                "    x = np.arange(50.0)\n    return [{'cancel': int(np.std(x) + np.percentile(x, 90) + np.median(x) + np.var(x)"
                " + np.linalg.norm(x) + np.nanmean(x) + np.corrcoef(x, x)[0, 1] + np.polyfit(x, x, 1)[0] + np.cumsum(x)[-1]"
                " + np.quantile(x, 0.5) + np.argsort(x)[0] + np.round(np.mean(x), 2) + np.searchsorted(x, 3.0)"
                " + x.any() + x.all() + x.mean() + x.std() + x.var() + x.max() + x.min() + x.sum() + x.prod()"
                " + x.clip(0, 1).sum() + x.round(2).sum() + x.cumsum()[-1] + x.argmax() + x.dot(x))}]\n")
        script = ("import sys\nfrom league.gym.runtime import load_program\nr = load_program(sys.stdin.read()).start()\n"
                  "print(r.decide(None), r.messages)\n")
        done = subprocess.run([sys.executable, "-c", script], input=code, capture_output=True, text=True,
                              cwd=str(__import__("pathlib").Path(__file__).resolve().parents[2]))
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("[{'cancel':", done.stdout)
        self.assertIn("[]", done.stdout.split("]", 1)[1] + "]")


if __name__ == "__main__":
    unittest.main()
