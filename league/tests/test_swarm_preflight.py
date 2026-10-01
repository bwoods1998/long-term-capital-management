"""The preflight (league/swarm/preflight.py): market-independent misuse of the ctx API is refused on synthetic sessions
before a Train run is spent, and nothing that would run in the Gym is (no false refusals): every error the market's
numbers could cause or spare is advisory, its warnings go to the researcher and the run goes ahead."""

from __future__ import annotations

import copy
import json
import math
import tempfile
import unittest
from pathlib import Path

try:
    import numpy  # noqa: F401

    HAVE = True
except ImportError:  # pragma: no cover
    HAVE = False

HEAD = 'NEEDS = {"roots": ["SPY"], "dte": [0, 7], "band": 0.05, "cadence": 5, "history": 10}\nPARAMS = {"k": 1.0}\nSTATE = {}\n'


def program(body: str, head: str = HEAD) -> str:
    return head + "def decide(ctx):\n" + "".join("    " + line + "\n" for line in body.strip("\n").splitlines())


@unittest.skipUnless(HAVE, "numpy not installed")
class Preflight(unittest.TestCase):
    def check(self, code, params=None, roots=None, timeout=1.0, capital=None):
        from league.live.decider import InlineDecider
        from league.swarm.preflight import run

        return run(code, params or {}, InlineDecider(timeout=timeout, max_errors=10 ** 9), universe=roots, capital=capital)

    def refused(self, code, stage="decide", **kw):
        out = self.check(code, **kw)
        self.assertEqual(out["status"], "refused", out)
        self.assertEqual(out["stage"], stage, out)
        return out

    def passed(self, code, **kw):
        out = self.check(code, **kw)
        self.assertNotEqual(out["status"], "refused", out)
        return out

    def advisory(self, code, **kw):
        out = self.check(code, **kw)
        self.assertEqual(out["status"], "advisory", out)
        self.assertTrue(out["warnings"], out)
        for warning in out["warnings"]:
            self.assertTrue(warning.get("error") and warning.get("hint"), warning)
        return out

    # ------------------------------------------------------------------ what it catches (Sept 30's disqualifications)
    def test_positions_used_as_a_mapping(self):
        out = self.refused(program("for pid, p in ctx.positions.items():\n    pass\nreturn []"))
        self.assertEqual(out["line"], 5)
        self.assertEqual(out["source"], "for pid, p in ctx.positions.items():")
        self.assertIn("'list' object has no attribute 'items'", out["error"])
        self.assertIn("LISTS", out["hint"])
        self.assertGreaterEqual(out["calls"], 25)

    def test_the_underlying_read_as_a_dict(self):
        out = self.refused(program('px = ctx.under.get("price")\nreturn []'))
        self.assertIn("UnderlyingView", out["error"])
        self.assertIn("ATTRIBUTE", out["hint"])
        self.assertIn("prior_close", out["hint"])

    def test_a_chain_field_misnamed(self):
        out = self.refused(program("s = ctx.chain.strikes\nreturn []"))
        self.assertIn("Did you mean `strike`", out["hint"])

    def test_arithmetic_on_a_none_is_left_to_the_gym(self):
        # A None can be a search that found nothing on this made-up market: never a refusal (the Gym judges it), but an
        # advisory whose warning carries the line and the API. The advice for one still names the program's PARAMS.
        from league.swarm.preflight import advice

        out = self.advisory(program('x = ctx.params.get("missing") / 2.0\nreturn []'))
        self.assertIn("market", out["why"])
        self.assertEqual((out["line"], out["source"]), (5, 'x = ctx.params.get("missing") / 2.0'))
        self.assertIn("is None", out["hint"])
        self.assertIn("made-up market", out["warnings"][0]["may_be"])
        hint = advice("line 5: TypeError: unsupported operand type(s) for /: 'NoneType' and 'float'", params={"k": 1.0})
        self.assertIn("is None", hint)
        self.assertIn(": k", hint)

    def test_a_root_it_never_asked_for(self):
        out = self.refused(program('u = ctx.underlyings["QQQ"]\nreturn []'))
        self.assertIn("KeyError: 'QQQ'", out["error"])
        self.assertIn("SPY", out["hint"])

    def test_state_that_never_fills_is_advisory(self):
        # STATE is the program's own: a key only a market condition would write is advisory, whatever the line reads.
        out = self.advisory(program('prev = STATE["last"]\nSTATE["last"] = ctx.under.price\nreturn []'))
        self.assertIn("KeyError: 'last'", out["error"])
        self.assertIn("STATE", out["hint"])

    def test_a_params_key_read_from_the_wrong_place(self):
        out = self.advisory(program('n = STATE["k"]\nreturn []'))
        self.assertIn("ctx.params['k']", out["hint"])

    def test_the_advice_names_the_declared_params(self):
        # A key the program never declared is never in its PARAMS (only read, never written) nor in ctx.params.
        for line in ('x = PARAMS["window"]', 'x = ctx.params["window"]', 'p = ctx.params\nx = p["window"]'):
            out = self.refused(program(line + "\nreturn []"))
            self.assertIn("KeyError: 'window'", out["error"])
            self.assertIn(": k", out["hint"])
            self.assertIn("never a key", out["why"])
        # A PARAMS the program writes to could hold it by then: advisory.
        self.advisory(program('if ctx.events["fomc"]:\n    PARAMS["window"] = 3\nx = PARAMS["window"]\nreturn []'))

    def test_a_module_body_that_fails_to_load_is_left_to_the_gym(self):
        # Only the static code check refuses at load: a module body runs here on the House's Python and numpy, not the
        # Gym's, so even one that fails on every version is advisory (the Gym's load refuses it, on its own runtime).
        code = HEAD + 'TABLE = {"a": 1}\nFIRST = TABLE["b"]\ndef decide(ctx):\n    return []\n'
        out = self.advisory(code)
        self.assertEqual((out["stage"], out["calls"]), ("load", 0))
        self.assertIn("fails to load", out["error"])
        self.assertEqual(out["line"], 5)
        self.assertIn("Gym", out["warnings"][0]["may_be"])
        self.assertIn("static code check", out["why"])

    def test_only_the_static_code_check_refuses_at_load(self):
        from league.swarm.preflight import static_refusal

        for head, why in (("import os\n", "import os is not allowed"), ("X = 2024\n", "reads as a year"),
                          ("X = eval('1')\n", "eval is not allowed")):
            code = head + program("return []")
            out = self.refused(code, stage="load")
            self.assertIn(why, out["error"])
            self.assertEqual(out["error"], static_refusal(code))
            self.assertEqual(out["calls"], 0)
            self.assertIn("nothing of the program ran", out["hint"])
        self.assertIsNone(static_refusal(program("return []")))

    def test_a_load_that_differs_by_runtime_is_never_refused(self):
        # Module bodies that load on the Gym's Python 3.12+ and numpy 2.5 and not on the House's 3.11 and numpy 2.4: a
        # float sum (compensated from 3.12), a slice as a dict key (hashable from 3.12), math.nextafter(steps=) (3.12),
        # and the same float sum turned into a size. On 3.11 each is advisory at load; on 3.12+ each passes.
        import sys

        bodies = ("WEIGHTS = [0.1] * 10\nassert sum(WEIGHTS) == 1.0\n",
                  "WINDOWS = {slice(0, 30): 'open', slice(30, 390): 'day'}\n",
                  "import math\nEPS = math.nextafter(0.0, 1.0, steps=4)\n",
                  "STEPS = int(sum([0.1] * 10))\nSIZE = 1.0 / STEPS\n",
                  "X = true\n",  # a name never bound: the Gym's load refuses it, and judges it
                  )
        for body in bodies:
            code = HEAD + body + "def decide(ctx):\n    return []\n"
            out = self.check(code)
            self.assertIn(out["status"], ("advisory", "passed"), (body, out))
            if out["status"] == "advisory":
                self.assertEqual(out["stage"], "load", out)
                self.assertTrue(out["warnings"][0]["may_be"], out)
            elif body != "X = true\n":
                self.assertGreaterEqual(sys.version_info[:2], (3, 12), out)
        # NEEDS a load refuses (check_experiment refuses a literal one before the researcher's preflight): advisory here.
        bad = HEAD.replace('"cadence": 5', '"cadence": 0') + "def decide(ctx):\n    return []\n"
        out = self.advisory(bad)
        self.assertIn("NEEDS['cadence']", out["error"])

    # ------------------------------------------------------------------ what it must never refuse
    def test_every_seed_and_example_program_passes(self):
        from league.swarm.seeds import SEEDS, program_for

        examples = sorted((Path(__file__).resolve().parents[1] / "gym" / "examples").glob("*.py"))
        programs = [(spec["id"], *program_for(spec)) for spec in SEEDS] + [(p.name, p.read_text(), {}) for p in examples]
        self.assertGreater(len(programs), 40)
        refused = [(name, out) for name, code, params in programs
                   if (out := self.check(code, params))["status"] == "refused"]
        self.assertEqual(refused, [])

    def test_a_warm_up_error_that_stops_is_not_refused(self):
        # Errs on its first 10 calls (fewer than the Gym's 25), then runs: advisory, with its line.
        out = self.advisory(program('STATE["n"] = STATE.get("n", 0) + 1\nif STATE["n"] <= 10:\n    raise ValueError("warming")\nreturn []'))
        self.assertIn("10 of", out["why"])
        self.assertEqual(out["line"], 7)

    def test_an_error_on_one_weekday_only_is_not_refused(self):
        self.passed(program('if ctx.weekday == 1:\n    raise ValueError("tuesday")\nreturn []'))

    def test_a_program_that_trades_first_is_left_to_the_gym(self):
        # It assumes its open filled: the flat preflight cannot know, so the first intent ends it.
        body = ('if not STATE.get("sent"):\n    STATE["sent"] = True\n'
                '    return [{"open": "long_call", "root": "SPY", "legs": [{"side": "long", "right": "C", "dte": 0, "atm": 0}], "qty": 1}]\n'
                'p = ctx.positions[0]\nreturn []')
        out = self.passed(program(body))
        self.assertEqual(out["calls"], 1)

    def test_a_slow_call_is_inconclusive_not_refused(self):
        # A call past its limit on this box says nothing about a Gym box. (A stand-in decider reports the timeout: the
        # real limit is SIGALRM in the decider's child, which other tests in this process may have claimed.)
        from league.swarm.preflight import run

        class Slow:
            restarts = 0

            def load(self, key, code, params, name):
                return {"needs": {"roots": ["SPY"], "dte": [0, 7], "band": 0.05, "cadence": 5, "history": 10,
                                  "start": 571, "end": 958}}

            def decide(self, snaps, unders, jobs):
                return {jobs[0]["key"]: {"intents": [], "stats": {"calls": 1, "errors": 1, "timeouts": 1,
                                                                  "messages": ["decide ran past 1.00 s"]}}}

            def drop(self, key):
                pass

        out = run(program("return []"), {}, Slow())
        self.assertEqual(out["status"], "inconclusive", out)
        self.assertEqual(out["calls"], 1)

    def test_a_numpy_api_error_is_advisory(self):
        # The House's numpy is not the Gym boxes' (requirements-gym.txt): an API one has and the other lacks says nothing.
        out = self.advisory("import numpy as np\n" + program("x = np.not_in_this_numpy(1.0)\nreturn []"))
        self.assertIn("this box", out["warnings"][0]["may_be"])

    def test_a_missing_stdlib_function_is_advisory(self):
        # The House runs Python 3.11; the Gym's boxes 3.12+ (math.sumprod, int.is_integer): not the program's fault.
        out = self.advisory("import math\n" + program("x = math.not_in_this_python([1.0], [2.0])\nreturn []"))
        self.assertIn("this box", out["why"])

    def test_what_is_this_box_and_what_is_the_program(self):
        from league.swarm.preflight import environmental

        for message in ("line 5: AttributeError: module 'math' has no attribute 'sumprod'",
                        "line 5: AttributeError: module 'numpy.linalg' has no attribute 'vecdot'",
                        "line 5: AttributeError: 'int' object has no attribute 'is_integer'",
                        "line 5: AttributeError: 'float' object has no attribute 'from_number'",
                        "line 5: AttributeError: 'numpy.ndarray' object has no attribute 'to_device'",
                        "line 5: MemoryError: Unable to allocate 2.24 GiB for an array with shape (20000, 15000)",
                        "line 5: MemoryError: ", "decide recursed too deep",
                        "line 5: TypeError: sort() got an unexpected keyword argument 'stable'",
                        # Every keyword complaint, whatever the version's words: keywords are what newer versions add.
                        "line 5: TypeError: str.replace() takes no keyword arguments",
                        "line 5: TypeError: replace() takes no keyword arguments",
                        "line 5: TypeError: math.nextafter() takes no keyword arguments",
                        "line 5: TypeError: 'cmp' is an invalid keyword argument for sort()",
                        "line 5: TypeError: f() missing 1 required keyword-only argument: 'k'",
                        "line 5: TypeError: f() got some positional-only arguments passed as keyword arguments: 'a'"):
            self.assertTrue(environmental(message), message)
        for message in ("line 5: AttributeError: 'list' object has no attribute 'items'",
                        "line 5: AttributeError: 'UnderlyingView' object has no attribute 'get'",
                        "line 5: AttributeError: 'dict' object has no attribute 'signal_on'",
                        "line 5: AttributeError: 'Ctx' object has no attribute 'cadence'",
                        "line 5: AttributeError: 'numpy.ndarray' object has no attribute 'get'",
                        "line 5: AttributeError: 'float' object has no attribute 'price'",
                        "line 5: AttributeError: 'numpy.float64' object has no attribute 'strike'",
                        "line 5: TypeError: 'UnderlyingView' object is not subscriptable",
                        "line 5: KeyError: 'last'"):
            self.assertFalse(environmental(message), message)

    def test_an_error_on_the_market_numbers_is_advisory(self):
        from league.swarm.preflight import market_dependent

        head = "import numpy as np\n" + HEAD
        for body in ("i = np.flatnonzero(ctx.chain.strike == round(ctx.under.price) + 0.25)[0]\nreturn []",
                     "x = 1.0 / (ctx.chain.n * 0)\nreturn []",
                     "k = min(s for s in ctx.chain.strike if s < 0)\nreturn []"):
            out = self.advisory(program(body, head=head))
            self.assertIn("market", out["why"])
        self.assertTrue(market_dependent("line 5: KeyError: 450.0"))
        self.assertTrue(market_dependent("line 5: KeyError: np.float64(450.0)"))
        # Each runtime's own words: the House's Python 3.11 with numpy 2.4.4, and 3.14 with numpy 2.5.3.
        for message in ("min() arg is an empty sequence", "min() iterable argument is empty",
                        "math domain error", "expected a positive input, got 0.0", "expected a nonnegative input, got -1.0",
                        "expected a number in range from -1 up to 1, got 2.0", "expected a finite input, got inf",
                        "expected argument value > -1, got -1.0", "2 is not in list", "list.index(x): x not in list",
                        "can only convert an array of size 1 to a Python scalar", "array of sample points is empty",
                        "zero-size array to reduction operation minimum which has no identity",
                        "The truth value of an empty array is ambiguous. Use `array.size > 0` to check that an array is not "
                        "empty.", "attempt to get argmin of an empty sequence", "not enough values to unpack (expected 2, got 0)"):
            self.assertTrue(market_dependent(f"line 5: ValueError: {message}"), message)
        for message in ("expected non-empty vector for x", "only 0-dimensional arrays can be converted to Python scalars",
                        "only length-1 arrays can be converted to Python scalars", "expected x and y to have same length",
                        "unsupported format string passed to numpy.ndarray.__format__"):
            self.assertTrue(market_dependent(f"line 5: TypeError: {message}"), message)
        # The reviews' empty selections and different lengths (the same words on both runtimes): a zero in a shape, a
        # selection too short for what was asked, two selections' lengths, a search that found nothing.
        for message in ("operands could not be broadcast together with shapes (46,) (0,) ",
                        "operands could not be broadcast together with shapes (46,) (45,) ",
                        "shapes (0,) and (3,) not aligned: 0 (dim 0) != 3 (dim 0)",
                        "could not broadcast input array from shape (0,) into shape (3,)",
                        "matmul: Input operand 1 has a mismatch in its core dimension 0, with gufunc signature "
                        "(n?,k),(k,m?)->(n?,m?) (size 3 is different from 0)", "fp and xp are not of the same length.",
                        "All-NaN slice encountered", "tuple.index(x): x not in tuple",
                        "zip() argument 2 is longer than argument 1", "zip() argument 2 is shorter than argument 1",
                        "Shape of array too small to calculate a numerical gradient, at least (edge_order + 1) elements "
                        "are required.", "cannot select an axis to squeeze out which has size not equal to one",
                        "kth(=5) out of bounds (2)", "Number of samples, -1, must be non-negative.",
                        "negative dimensions are not allowed", "range() arg 3 must not be zero"):
            self.assertTrue(market_dependent(f"line 5: ValueError: {message}"), message)
        for message in ("KeyError: 'pop from an empty set'", "KeyError: 'popitem(): dictionary is empty'",
                        "KeyError: '451.0'", "LinAlgError: SVD did not converge in Linear Least Squares"):
            self.assertTrue(market_dependent(f"line 5: {message}"), message)
        self.assertFalse(market_dependent("line 5: KeyError: 'window'"))
        for message in ("ValueError: The truth value of an array with more than one element is ambiguous. Use a.any() or "
                        "a.all()", "ValueError: could not convert string to float: 'SPY'",
                        "TypeError: 'UnderlyingView' object is not subscriptable",
                        "TypeError: type numpy.ndarray doesn't define __round__ method", "ValueError: substring not found",
                        "TypeError: unsupported operand type(s) for -: 'list' and 'float'", "KeyError: 'rich_put'"):
            self.assertFalse(market_dependent(f"line 5: {message}"), message)

    def test_an_empty_selection_never_refuses_on_this_runtime(self):
        # Raised here, on the Python and numpy these tests run on (CI: 3.11 with numpy 2.4.4, the House's; 3.14 with
        # numpy 2.5.3), and read as the Gym's Runner reports them: whatever each runtime says, an empty selection, one
        # turned into a single number, or two of different lengths, is the market's doing; the misuses are not.
        import warnings

        from league.swarm.preflight import market_dependent

        empty, one, two, three = numpy.zeros(0), numpy.array([1.5]), numpy.array([1.0, 2.0]), numpy.array([1.0, 2.0, 3.0])
        nan2 = numpy.array([numpy.nan, numpy.nan])
        spared = {"min()": lambda: min(empty), "max() of a list": lambda: max([]), "np.min": lambda: numpy.min(empty),
                  "argmax": lambda: numpy.argmax(empty), "np.interp": lambda: numpy.interp(0.3, empty, empty),
                  "np.polyfit": lambda: numpy.polyfit(empty, empty, 2), "item()": lambda: empty.item(),
                  "item() of two": lambda: two.item(), "float()": lambda: float(empty),
                  "float(np.squeeze())": lambda: float(numpy.squeeze(empty)), "int()": lambda: int(empty),
                  "truth value": lambda: bool(empty), "[0]": lambda: empty[0], "np.percentile": lambda: numpy.percentile(empty, 50),
                  "np.average": lambda: numpy.average(empty, weights=empty), "unpack": lambda: exec("a, b = e", {"e": empty}),
                  "math.log(0)": lambda: math.log(0.0), "math.sqrt(-1)": lambda: math.sqrt(-1.0),
                  "math.acos(2)": lambda: math.acos(2.0), "int(nan)": lambda: int(float("nan")),
                  "reshape": lambda: empty.reshape(2), "np.stack": lambda: numpy.stack([]),
                  "list.index": lambda: [1.0].index(2.0), "next()": lambda: next(iter(empty)),
                  "1/0": lambda: 1 / 0, "np.linalg": lambda: numpy.linalg.inv(numpy.zeros((2, 2))),
                  # The reviews' (round 3): a zero-length operand, a count too small, a search that found nothing.
                  "a broadcast with an empty one": lambda: two - empty, "np.dot": lambda: numpy.dot(empty, three),
                  "an assignment": lambda: exec("a = np.zeros(3)\na[:] = e", {"np": numpy, "e": empty}),
                  "matmul": lambda: empty @ three, "np.nanargmin of all-NaN": lambda: numpy.nanargmin(nan2),
                  "tuple.index": lambda: (1.0,).index(2.0), "zip(strict=True)": lambda: list(zip(empty, two, strict=True)),
                  "np.gradient": lambda: numpy.gradient(numpy.array([1.0])),
                  "np.squeeze(axis=0) of two": lambda: numpy.squeeze(two, axis=0),
                  "np.squeeze(axis=0) of none": lambda: numpy.squeeze(empty, axis=0),
                  "set().pop()": lambda: set().pop(), "{}.popitem()": lambda: {}.popitem(),
                  "np.partition past the selection": lambda: numpy.partition(two, 5),
                  "np.linspace of a count less one": lambda: numpy.linspace(0.0, 1.0, empty.size - 1),
                  "np.zeros of a count less one": lambda: numpy.zeros(empty.size - 1),
                  "a format of a selection": lambda: f"{two:.2f}",
                  # Two selections of different lengths: each is as long as the market makes it.
                  "a broadcast of two lengths": lambda: two - three, "np.interp of two lengths": lambda: numpy.interp(0.3, two, empty),
                  "np.polyfit of two lengths": lambda: numpy.polyfit(two, three, 1)}
        misuse = {"a list as a mapping": lambda: [].items(), "two as one boolean": lambda: bool(two),
                  "a string as a number": lambda: float("SPY"), "a dict as an object": lambda: {}.price,
                  "round() of an array": lambda: round(numpy.squeeze(one)), "a list less a number": lambda: [1.0] - 1.0}
        for table, expected in ((spared, True), (misuse, False)):
            for what, raise_it in table.items():
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    try:
                        raise_it()
                    except Exception as exc:  # noqa: BLE001 - every error is the point
                        message = f"line 5: {type(exc).__name__}: {str(exc)[:160]}"
                    else:
                        self.fail(f"{what} raised nothing on this runtime")
                self.assertEqual(market_dependent(message), expected, (what, message))

    def test_a_listed_strike_looked_up_exactly_is_found(self):
        # Reviewers' false refusals: a spread whose wing is found by exact strike on the listed grid (5-point SPXW, $1
        # SPY past a 0.114 band, $0.5 and $2.5 names, a $1 name at its price) runs clean in the Gym and must here too.
        cases = (("SPXW", 0.05, "k = math.floor(s / 5) * 5 - 10", 5.0),
                 ("SPXW", 0.10, "k = math.floor(s / 5) * 5 - 40", 10.0),
                 ("SPY", 0.15, "k = float(round(s)) - 3", 1.0),
                 ("QQQ", 0.20, "k = float(round(s)) - 2", 1.0),
                 ("MARA", 0.10, "k = math.floor(s * 2) / 2", 0.5),
                 ("SLV", 0.10, "k = math.floor(s * 2) / 2 - 1", 0.5),
                 ("TSLA", 0.20, "k = math.floor(s / 2.5) * 2.5 - 5", 2.5),
                 ("NVDA", 0.20, "k = math.floor(s / 2.5) * 2.5 - 5", 2.5),
                 ("AMZN", 0.20, "k = float(round(s)) - 3", 1.0))
        for root, band, pick, width in cases:
            head = (f'import math\nimport numpy as np\nNEEDS = {{"roots": ["{root}"], "dte": [0, 2], "band": {band}, '
                    f'"cadence": 5, "history": 10}}\nPARAMS = {{}}\nSTATE = {{}}\n')
            if root not in ("SPXW", "SPY", "QQQ"):  # a Friday-only root lists nothing 0-2 days out on a Tuesday
                head = head.replace('"dte": [0, 2]', '"dte": [0, 7]')
            body = (f"c = ctx.chain\ns = ctx.under.price\n{pick}\nputs = ~c.is_call & (c.dte == c.dte.min())\n"
                    f"i = np.flatnonzero(puts & (c.strike == k))[0]\nj = np.flatnonzero(puts & (c.strike == k - {width}))[0]\n"
                    "return []")
            out = self.check(program(body, head=head))
            self.assertEqual((out["status"], out.get("errors")), ("passed", 0), (root, band, out))

    def test_a_single_contract_selection_is_not_refused(self):
        # The verification review's probe: a mask that keeps exactly one contract on the listed chain (an ATM strike
        # within half a step; every expiry of a Friday-only root in [0, 7], which is one), used as one number. A chain
        # finer than the listed one (every $0.5, an expiry every weekday) keeps several, and the truth value of that
        # array raised on every call.
        cases = (("SPY", "k = float(round(s))", 0.5, "(c.dte == c.dte.min()) & "),
                 ("QQQ", "k = float(round(s))", 0.5, "(c.dte == c.dte.min()) & "),
                 ("TSLA", "k = round(s / 2.5) * 2.5", 1.0, "(c.dte == c.dte.min()) & "),
                 ("TSLA", "k = round(s / 2.5) * 2.5", 1.0, ""),
                 ("MARA", "k = round(s * 2) / 2", 0.2, ""),
                 ("AMZN", "k = float(round(s))", 0.4, ""))
        for root, pick, atol, near in cases:
            head = (f'import numpy as np\nNEEDS = {{"roots": ["{root}"], "dte": [0, 7], "band": 0.05, "cadence": 5, '
                    f'"history": 5}}\nPARAMS = {{"edge": 50.0}}\nSTATE = {{}}\n')
            body = (f"c = ctx.chain\ns = ctx.under.price\n{pick}\n"
                    f"atm = c.is_call & {near}np.isclose(c.strike, k, atol={atol})\n"
                    "if c.ask[atm] - c.bid[atm] > ctx.params[\"edge\"]:\n"
                    f"    return [{{\"open\": \"long_call\", \"root\": \"{root}\", \"qty\": 1}}]\n"
                    "x = float(c.mid[atm].sum())\nreturn []")
            out = self.check(program(body, head=head))
            self.assertEqual((out["status"], out.get("errors")), ("passed", 0), (root, near, out))

    def test_a_chain_finer_than_the_gyms_never_refuses_on_its_own(self):
        # Were a root's listing finer than the Gym's store on some day, a single-contract selection would keep several
        # contracts and raise on every call; the refusal must recur on the sparser listing, where it does not.
        from unittest import mock

        import league.swarm.preflight as PF

        real = PF.listing

        def finer(root, *, sparse=False, dense=False):
            return real(root, sparse=True) if sparse else (real(root)[0], 0.5, PF.DAILY)

        head = ('import numpy as np\nNEEDS = {"roots": ["TSLA"], "dte": [0, 7], "band": 0.05, "cadence": 5, "history": 5}\n'
                'PARAMS = {"edge": 50.0}\nSTATE = {}\n')
        body = ("c = ctx.chain\nk = round(ctx.under.price / 2.5) * 2.5\natm = c.is_call & np.isclose(c.strike, k, atol=1.0)\n"
                "if c.ask[atm] - c.bid[atm] > ctx.params[\"edge\"]:\n    return []\nreturn []")
        with mock.patch.object(PF, "listing", finer):
            out = self.advisory(program(body, head=head))
        self.assertIn("truth value of an array", out["error"])
        # The same misuse on every chain still refuses, confirmed on the sparser listing.
        out = self.refused(program("for pid, p in ctx.positions.items():\n    pass\nreturn []"))
        self.assertIn("on a sparser and a denser listing", out["why"])

    def test_a_chain_coarser_than_the_gyms_never_refuses_on_its_own(self):
        # The correctness review's false refusals (round 3): IWM is listed Monday, Wednesday and Friday, so a calendar
        # between the 0- and 1-day expiries never finds both on one session. The Gym lists IWM every weekday from spring
        # 2024 and runs these clean there; the denser listing holds both and spares them, stated or not.
        head = ('import numpy as np\nNEEDS = {"roots": ["IWM"], "dte": [0, 1], "band": 0.05, "cadence": 5, "history": 10}\n'
                'PARAMS = {}\nSTATE = {}\n')
        stated = "c = ctx.chain\nd = c.mid[(c.dte == 1) & c.is_call] - c.mid[(c.dte == 0) & c.is_call]\nreturn []"
        gated = ("c = ctx.chain\nf = (c.dte == 0) & c.is_call\nb = (c.dte == 1) & c.is_call\nif f.any() and b.any():\n"
                 "    STATE[\"cal\"] = 1\nx = STATE[\"cal\"]\nreturn []")
        out = self.advisory(program(stated, head=head))
        self.assertIn("broadcast together with shapes", out["why"])
        out = self.advisory(program(gated, head=head))
        self.assertIn("KeyError: 'cal'", out["why"])
        # XSP lists every weekday (the store's 2024 sample): both run clean on the listing itself.
        for body in (stated, gated):
            out = self.check(program(body, head=head.replace('"IWM"', '"XSP"')))
            self.assertEqual((out["status"], out.get("errors")), ("passed", 0), out)
        # A misuse after the same calendar still refuses on every market, the denser one too.
        out = self.refused(program(gated.replace('x = STATE["cal"]', "for pid, p in ctx.positions.items():\n    pass"),
                                   head=head))
        self.assertIn("denser listing", out["why"])

    def test_a_selection_read_whatever_its_count_is_never_refused(self):
        # The evidence review's case: np.squeeze(axis=0) of a selection raises on none and on several alike, as .item()
        # does; neither refuses.
        head = "import numpy as np\n" + HEAD
        pick = "sel = c.mid[(c.iv > 0.5) & c.is_call & (c.dte == c.dte.min())]\n"
        for read in ("px = float(np.squeeze(sel, axis=0))", "px = sel.item()"):
            self.advisory(program("c = ctx.chain\n" + pick + read + "\nreturn []", head=head))

    def test_a_wide_quote_on_a_deep_book_exists(self):
        # The correctness review's nit: a filter for wide quotes on deep books kept nothing on any market (the listing's
        # books were thin, the tight market's quotes a tick, the wide market's books thin), so STATE never filled. The
        # listing's books now run from one contract to thousands on a log scale, at every quote width.
        head = "import numpy as np\n" + HEAD
        body = ("c = ctx.chain\nroom = (c.spread >= 0.03) & (c.bid_size >= 500) & (c.ask_size >= 500)\n"
                "if room.any():\n    STATE[\"t\"] = int(np.flatnonzero(room)[0])\nt = STATE[\"t\"]\nreturn []")
        out = self.check(program(body, head=head))
        self.assertEqual((out["status"], out.get("errors")), ("passed", 0), out)
        from league.swarm.preflight import Market

        needs = {"roots": ["SPY"], "dte": [0, 7], "band": 0.05, "cadence": 5, "history": 5, "start": 571, "end": 958}
        snap = Market(["SPY"], needs).snapshot("SPY", 0, 60)
        self.assertLess(int(snap.bid_size.min()), 10)
        self.assertGreater(int(snap.bid_size.max()), 1_000)

    LIQUID = {
        # The verification review's probes: each errs on every call only when its liquidity filter keeps nothing.
        "a STATE key written when the filter keeps something": (
            'c = ctx.chain\nliquid = c.is_call & (c.spread <= ctx.params["max_spread"] * c.mid)\n'
            'if liquid.any():\n    STATE["ref_iv"] = float(np.median(c.iv[liquid]))\nref = STATE["ref_iv"]\nreturn []'),
        "np.interp over the kept contracts": (
            'c = ctx.chain\nliquid = c.is_call & (c.spread <= ctx.params["max_spread"] * c.mid)\n'
            'order = np.argsort(c.delta[liquid])\n'
            'k30 = float(np.interp(0.30, c.delta[liquid][order], c.strike[liquid][order]))\nreturn []'),
        "np.polyfit over the kept contracts": (
            'c = ctx.chain\nliquid = ~c.is_call & (c.spread <= ctx.params["max_spread"] * c.mid)\n'
            'fit = np.polyfit(c.strike[liquid] / c.spot - 1.0, c.iv[liquid], 2)\nreturn []'),
        "item() of the kept contract": (
            'c = ctx.chain\nliquid = c.is_call & (c.dte == c.dte.min()) & (c.spread <= ctx.params["max_spread"] * c.mid)\n'
            'atm = liquid & (np.abs(c.strike - c.spot) <= 0.5)\npx = c.mid[atm].item()\nreturn []'),
        "float(np.squeeze()) of the kept contract": (
            'c = ctx.chain\nliquid = c.is_call & (c.dte == c.dte.min()) & (c.spread <= ctx.params["max_spread"] * c.mid)\n'
            'atm = liquid & (np.abs(c.strike - c.spot) <= 0.5)\npx = float(np.squeeze(c.mid[atm]))\nreturn []'),
        "a local set when the filter keeps something": (
            'c = ctx.chain\nliquid = c.is_call & (c.spread <= ctx.params["max_spread"] * c.mid)\n'
            'if liquid.any():\n    best = float(np.max(c.mid[liquid]))\nx = best * 2\nreturn []'),
    }

    def test_a_liquidity_filter_never_refuses(self):
        # The review's false refusals: at a half-spread of 3% of every mid, a filter at 4% kept nothing, the program
        # then erred on every call, and the sparser listing (the same quotes) "confirmed" it. The Gym runs these clean.
        head = ('import numpy as np\nNEEDS = {"roots": ["SPY"], "dte": [0, 7], "band": 0.05, "cadence": 5, "history": 10}\n'
                'PARAMS = {"max_spread": 0.04}\nSTATE = {}\n')
        for what, body in self.LIQUID.items():
            # At 4% each keeps contracts on most minutes: passed, or advisory where a minute's quotes keep none or two.
            out = self.check(program(body, head=head), {"max_spread": 0.04})
            self.assertIn(out["status"], ("passed", "advisory"), (what, out))
            self.assertLess(out.get("errors") or 0, 25, (what, out))
            # A filter no quote could meet here keeps nothing on the tightest market either: advisory, never refused.
            for cap in (0.01, 0.002):
                out = self.check(program(body, head=head), {"max_spread": cap})
                self.assertIn(out["status"], ("passed", "advisory"), (what, cap, out))

    def test_the_quotes_are_tight_near_the_money_and_never_under_a_tick(self):
        # Near the money no wider than the Gym's own synthetic store (3% of the mid), so a 4% liquidity filter keeps calls
        # there on every root at every minute; wider away from it; on the venue's tick grid, at least one tick wide.
        from league.gym import venue
        from league.swarm.preflight import Market

        for root in ("SPY", "QQQ", "IWM", "SPXW", "GLD", "TSLA", "NVDA", "MARA", "XYZ"):
            needs = {"roots": [root], "dte": [0, 7], "band": 0.5, "cadence": 5, "history": 5, "start": 571, "end": 958}
            widths = {}
            for regime in ("listed", "tight", "wide"):
                market, near, far = Market([root], needs, regime=regime), [], []
                for s in (0, 1):
                    for mi in (5, 120, 380):
                        snap = market.snapshot(root, s, mi)
                        c = snap.view(snap.slice_index(0, 7, 0.5))
                        # The venue's tick at each premium (away from $3, where it changes and the model's mid decides).
                        clear = numpy.abs(c.mid - 3.0) > 0.15
                        tick = numpy.array([venue.leg_tick(root, float(m)) for m in c.mid])[clear]
                        spread, bid = c.spread[clear], c.bid[clear]
                        self.assertTrue((spread >= tick - 1e-9).all(), (root, regime))
                        self.assertTrue(numpy.allclose(numpy.round(bid / tick) * tick, bid), (root, regime))
                        if regime == "tight":
                            self.assertTrue(numpy.allclose(spread, tick), (root, "one tick"))
                        share, delta = c.spread / c.mid, numpy.abs(c.delta)
                        near += share[(delta >= 0.4) & (delta <= 0.6)].tolist()
                        far += share[delta < 0.1].tolist()
                        if regime == "listed":
                            kept = c.is_call & (numpy.abs(c.strike / c.spot - 1.0) <= 0.025) & (share <= 0.04)
                            self.assertGreater(int(kept.sum()), 0, (root, s, mi))
                widths[regime] = float(numpy.median(near))
                if regime == "listed":
                    self.assertLessEqual(widths[regime], 0.03, root)
                    self.assertGreater(float(numpy.median(far)), widths[regime], root)
            self.assertLess(widths["tight"], widths["listed"], root)
            self.assertGreater(widths["wide"], widths["listed"], root)

    def test_a_refusal_must_recur_at_the_same_line_on_every_market(self):
        # A misuse behind a branch the made-up numbers open on the listed market but not on another: advisory, naming the
        # market that spared it (one-tick quotes, the wide market's lower price, known volumes on the saturated market).
        head = ('import numpy as np\nNEEDS = {"roots": ["SPY"], "dte": [0, 7], "band": 0.05, "cadence": 5, "history": 10}\n'
                'PARAMS = {}\nSTATE = {}\n')
        atm = ("c = ctx.chain\ni = np.flatnonzero(c.is_call & (c.dte == c.dte.max()))\n"
               "iv = float(c.iv[i[np.argmin(np.abs(c.strike[i] - c.spot))]])\n")
        for condition, spared in (("not (c.spread <= 0.0101).all()", "one tick wide"), ("ctx.under.price > 425", "three times as wide"),
                                  ("ctx.under.volume != ctx.under.volume", "saturated")):
            out = self.advisory(program(atm + f"if {condition}:\n    for pid, p in ctx.positions.items():\n        pass\n"
                                              "return []", head=head))
            self.assertIn(spared, out["why"], condition)
            self.assertIn("'list' object has no attribute 'items'", out["why"], condition)
            self.assertIn("LISTS", out["hint"], condition)
        # Where another market raises something else first (there, an error its numbers cause), the misuse is advisory.
        out = self.advisory(program("c = ctx.chain\nif (c.spread <= 0.0101).all():\n    k = c.strike[c.strike < 0][0]\n"
                                    "for pid, p in ctx.positions.items():\n    pass\nreturn []", head=head))
        self.assertIn("one tick wide", out["why"])
        self.assertIn("IndexError", out["why"])
        # The same misuse at ANOTHER line on one market is not the same line: advisory (the rule is strict).
        out = self.advisory(program('c = ctx.chain\nif (c.spread <= 0.0101).all():\n    x = ctx.under.get("a")\n'
                                    'x = ctx.under.get("b")\nreturn []', head=head))
        self.assertIn("line 8", out["why"])
        # A misuse on any market is refused, on every one of them.
        out = self.refused(program("for pid, p in ctx.positions.items():\n    pass\nreturn []"))
        for words in ("saturated market", "sparser", "denser", "one tick wide", "three times as wide"):
            self.assertIn(words, out["why"])

    def test_the_chain_is_the_listing(self):
        # The listed step, the store's strikes a side of the open's money (40 for SPXW only, as storelib's STRIKE_RANGE),
        # the root's expiry weekdays and the store's reach in days to expiry (14; SPY and QQQ 45); the sparse listing:
        # Fridays and the next wider step; the dense one: every weekday and the next finer step too.
        from league.swarm.preflight import FRIDAY, Market, STORE_DEFAULT_STRIKES, listing, strikes

        for root, step, weekdays, reach in (("SPXW", 5.0, {0, 1, 2, 3, 4}, 14), ("SPX", 5.0, {4}, 14),
                                            ("SPY", 1.0, {0, 1, 2, 3, 4}, 45), ("IWM", 1.0, {0, 2, 4}, 14),
                                            ("MARA", 0.5, {4}, 14), ("AMZN", 1.0, {4}, 14), ("TSLA", 2.5, {4}, 14),
                                            ("SMCI", 2.5, {4}, 14), ("XYZ", 1.0, {4}, 14)):
            self.assertEqual(listing(root)[1:], (step, tuple(sorted(weekdays))), root)
            needs = {"roots": [root], "dte": [0, 60], "band": 0.5, "cadence": 5, "history": 5, "start": 571, "end": 958}
            market = Market([root], needs)
            for s, weekday in enumerate(market.weekdays):
                snap = market.snapshot(root, s, 0)
                for d in numpy.unique(snap.dte).tolist():
                    self.assertLessEqual(d, reach, root)
                    self.assertIn((weekday + d) % 7, weekdays if d <= 14 else {4}, (root, weekday, d))
                ks = numpy.unique(snap.strike[snap.dte == snap.dte.min()])
                self.assertTrue(numpy.allclose(numpy.diff(ks), step), root)
                # The strikes a side of the open's money (a grid that would pass zero stops above it).
                side = 40 if root == "SPXW" else STORE_DEFAULT_STRIKES
                atm = int(numpy.argmin(numpy.abs(ks - snap.spot)))
                self.assertLessEqual(abs(float(ks[atm]) - snap.spot), step, root)
                self.assertEqual(ks.size - 1 - atm, side, root)
                self.assertTrue(atm == side or (atm < side and ks[0] <= step + 1e-9), (root, atm))
            thin = Market([root], needs, sparse=True)
            sparse = thin.snapshot(root, 0, 0)
            self.assertEqual({(thin.weekdays[0] + d) % 7 for d in numpy.unique(sparse.dte).tolist()}, set(FRIDAY), root)
            wider = numpy.diff(numpy.unique(sparse.strike[sparse.dte == sparse.dte.min()]))
            fixed = root in ("SPXW", "SPX", "SPY", "IWM")
            self.assertTrue(numpy.allclose(wider, step if fixed else {0.5: 1.0, 1.0: 2.5, 2.5: 5.0}[step]), root)
            # The dense listing, on the listing's own weekdays: an expiry every weekday out to 14 days, and the next
            # finer step's strikes beside the root's own across the listing's span (a fixed-step root keeps its step).
            dense = Market([root], needs, regime="dense")
            self.assertEqual(dense.weekdays, market.weekdays, root)
            for s, weekday in enumerate(dense.weekdays):
                snap = dense.snapshot(root, s, 0)
                days = numpy.unique(snap.dte).tolist()
                self.assertEqual([d for d in days if d <= 14], [d for d in range(15) if (weekday + d) % 7 < 5], root)
                ks = numpy.unique(snap.strike[snap.dte == snap.dte.min()])
                own = strikes(root, float(dense.days[root][s]["path"][0]))
                self.assertTrue(numpy.isin(numpy.round(own, 6), numpy.round(ks, 6)).all(), root)
                fine = step if fixed or step == 0.5 else {1.0: 0.5, 2.5: 1.0, 5.0: 2.5}[step]
                self.assertEqual(ks.size > own.size, fine != step, root)
                self.assertTrue(numpy.isin(numpy.round(fine * numpy.round(own[len(own) // 2] / fine) + fine, 6),
                                           numpy.round(ks, 6)), root)

    def test_the_sessions_fall_on_days_the_roots_list(self):
        # Midweek when every weekday lists (SPY); a Friday-only root 10-20 days out lists on Monday (11), Tuesday (10) and
        # Friday (14), so a misuse behind a check for an empty chain is caught there, not passed on quiet Wednesdays.
        from league.swarm.preflight import session_weekdays

        self.assertEqual(session_weekdays(["SPY"], {"dte": [0, 7]}), (1, 2, 3))
        self.assertEqual(session_weekdays(["AAPL", "MSFT"], {"dte": [10, 20]}), (0, 1, 4))
        head = ('NEEDS = {"roots": ["AAPL", "MSFT"], "dte": [10, 20], "band": 0.10, "cadence": 30, "history": 5}\n'
                'PARAMS = {}\nSTATE = {}\n')
        out = self.refused(program('c = ctx.chains.get("MSFT")\nif c is None or c.n == 0:\n    return []\n'
                                   'px = ctx.underlyings["MSFT"].get("price")\nreturn []', head=head))
        self.assertIn("UnderlyingView", out["error"])

    def test_a_streak_the_runners_list_cannot_name_is_advisory(self):
        # Ten distinct warm-up errors fill the Runner's message list (it keeps ten); the streak after them is not in it,
        # so neither its line nor whether it is this box's error can be known.
        for tail in ("for pid, p in ctx.positions.items():\n        pass", "x = np.not_in_this_numpy(1.0)"):
            body = ('n = STATE.get("n", 0) + 1\nSTATE["n"] = n\nif n <= 20 and n % 2 == 0:\n'
                    '    raise ValueError("warm " + str(n))\nif n > 20:\n    ' + tail + "\nreturn []")
            out = self.advisory(program(body, head="import numpy as np\n" + HEAD))
            self.assertIn("Runner's list", out["why"], tail)

    DEEP = {what: body.replace('(c.spread <= ctx.params["max_spread"] * c.mid)',
                               '(c.bid_size >= ctx.params["depth"]) & (c.ask_size >= ctx.params["depth"])')
            for what, body in LIQUID.items()}

    def test_a_depth_filter_past_the_listings_books_is_advisory(self):
        # Round 5's false refusal: the listing's books stop at 5,000 contracts while real SPY NBBO sizes reach 10-31k, so a
        # depth filter above 5,000 kept nothing and the program erred on every call. Advisory now, whatever it then does
        # with the empty selection; and the saturated market's books reach past any real size.
        from league.swarm.preflight import Market

        head = ('import numpy as np\nNEEDS = {"roots": ["SPY"], "dte": [0, 7], "band": 0.05, "cadence": 5, "history": 10}\n'
                'PARAMS = {"depth": 5000}\nSTATE = {}\n')
        for what, body in self.DEEP.items():
            self.assertIn("depth", body, what)
            for depth in (10_000, 20_000, 31_000):
                out = self.advisory(program(body, head=head), params={"depth": depth})
                self.assertNotIn("stage", out, (what, depth))
        needs = {"roots": ["SPY"], "dte": [0, 7], "band": 0.05, "cadence": 5, "history": 5, "start": 571, "end": 958}
        listed, saturated = Market(["SPY"], needs).snapshot("SPY", 0, 60), Market(["SPY"], needs, regime="saturated").snapshot("SPY", 0, 60)
        self.assertLessEqual(int(listed.bid_size.max()), 5_000)
        self.assertGreater(int((saturated.bid_size >= 31_000).sum()), 50)

    def test_every_earlier_false_refusal_is_advisory(self):
        # Each class a verification round found refused (a program that runs in the Gym): a quote-width filter that keeps
        # nothing here, an empty selection, a selection read as one number, a depth filter past the listing's books.
        # Every one is advisory: the run goes ahead with the warning.
        head = ('import numpy as np\nNEEDS = {"roots": ["SPY"], "dte": [0, 7], "band": 0.05, "cadence": 5, "history": 10}\n'
                'PARAMS = {"max_spread": 0.04}\nSTATE = {}\n')
        for what, body in self.LIQUID.items():  # no quote is narrower than a tick: a 0 cap keeps nothing on any market
            self.advisory(program(body, head=head), params={"max_spread": 0.0})
        iwm = head.replace('"SPY"], "dte": [0, 7]', '"IWM"], "dte": [0, 1]')
        empty = ("c = ctx.chain\nd = c.mid[(c.dte == 1) & c.is_call] - c.mid[(c.dte == 0) & c.is_call]\nreturn []",
                 "c = ctx.chain\nf = (c.dte == 0) & c.is_call\nb = (c.dte == 1) & c.is_call\nif f.any() and b.any():\n"
                 "    STATE[\"cal\"] = 1\nx = STATE[\"cal\"]\nreturn []")
        for body in empty:
            self.advisory(program(body, head=iwm))
        pick = "c = ctx.chain\nsel = c.mid[(c.iv > 0.5) & c.is_call & (c.dte == c.dte.min())]\n"
        for read in ("px = float(np.squeeze(sel, axis=0))", "px = sel.item()", "px = float(np.squeeze(sel))",
                     "k = min(c.strike[c.strike < 0])"):
            self.advisory(program(pick + read + "\nreturn []", head=head))

    def test_the_diagnostics_misuse_is_refused(self):
        # The misuse in the retained disqualifications of Sept 30 (train-failure-diagnostic-20260930): list-as-mapping,
        # UnderlyingView.get and [...], a ChainView read as a dict or iterated, ctx fields that do not exist, a root never
        # asked for, a PARAMS key never declared. Operations on a None are advisory (a None can be the market's).
        head = ('import numpy as np\nNEEDS = {"roots": ["SPY", "QQQ"], "dte": [0, 7], "band": 0.05, "cadence": 5, '
                '"history": 10}\nPARAMS = {"zmin": 1.5, "max_positions": 2}\nSTATE = {}\n')
        refused = {
            "for posid in list(ctx.positions.keys()):\n    pass": "'list' object has no attribute 'keys'",
            "for pos in ctx.positions.values():\n    pass": "'list' object has no attribute 'values'",
            'has = any(p.get("type") == "x" for p in ctx.positions.values())': "no attribute 'values'",
            'under = ctx.underlyings.get("SPY")\nif under is None or len(under.get("closes", [])) < 3:\n    return []':
                "'UnderlyingView' object has no attribute 'get'",
            'if ctx.underlyings["QQQ"].get("prices") is None:\n    return []': "no attribute 'get'",
            'u = ctx.under\nprice = u["price"]': "'UnderlyingView' object is not subscriptable",
            'closes = {r: list(ctx.underlyings[r]["closes"]) for r in ctx.roots}': "not subscriptable",
            'chain = ctx.chain\nif chain is None or chain["n"] == 0:\n    return []': "'ChainView' object is not subscriptable",
            'calls = [c for c in ctx.chains["QQQ"] if c["is_call"]]': "'ChainView' object is not iterable",
            'if not ctx.underlies.keys():\n    return []': "'Ctx' object has no attribute 'underlies'",
            'near = ctx.NEEDS["dte"][0]': "'Ctx' object has no attribute 'NEEDS'",
            'day = ctx.weekday if "minute" not in ctx else ctx.minute': "'Ctx'",
            'p = ctx.params\nstrong = 2.0 >= p.zmin': "'dict' object has no attribute 'zmin'",
            'if len(ctx.positions) >= PARAMS["max_position"]:\n    return []': "KeyError: 'max_position'",
            'u = ctx.underlyings["TSLA"]': "KeyError: 'TSLA'",
        }
        for body, words in refused.items():
            out = self.refused(program(body + "\nreturn []", head=head))
            self.assertIn(words, out["error"], body)
            self.assertTrue(out["hint"] and out["misuse"], out)
        for body in ('x = ctx.params.get("vol_max") >= 0.3', 'u = ctx.underlyings.get("IWM")\nx = u.price'):
            self.advisory(program(body + "\nreturn []", head=head))

    def test_misuse_is_read_off_the_receiver(self):
        # The classifier on its own: a plain list, dict or number misuses the ctx API only when the receiver on the line
        # is a ctx field of that type, through every binding of every alias; the program's own containers never are.
        from league.swarm.preflight import api_misuse

        def misuse(body, message, line=None):
            code = program(body)
            n = line or len(code.splitlines())
            return api_misuse(f"line {n}: {message}", code, roots=["SPY"], params={})

        items = "AttributeError: 'list' object has no attribute 'items'"
        self.assertTrue(misuse("x = ctx.positions.items()", items))
        self.assertTrue(misuse("pos = ctx.positions\nrows = pos\nx = rows.items()", items))
        self.assertTrue(misuse("def inner():\n    return ctx.orders.items()\nx = inner()", items, 6))
        self.assertIsNone(misuse('book = STATE.get("b", [])\nx = book.items()', items))
        self.assertIsNone(misuse('x = ctx.positions\nif ctx.minute > 600:\n    x = STATE.get("m", [])\ny = x.items()', items))
        self.assertIsNone(misuse("x = ctx.positions.items()", "AttributeError: 'NoneType' object has no attribute 'items'"))
        self.assertIsNone(misuse("x = ctx.orders", items))  # no `.items` on the line: not located
        helper = (HEAD + "def pick(ctx, r):\n    return ctx.chains[r].strike.items()\n"
                  "def decide(ctx):\n    return pick(ctx, 'SPY')\n")
        self.assertTrue(api_misuse("line 5: AttributeError: 'numpy.ndarray' object has no attribute 'items'", helper,
                                   roots=["SPY"]))
        loop = "for r, c in ctx.chains.items():\n    x = c.strike.items()"
        self.assertTrue(misuse(loop, "AttributeError: 'numpy.ndarray' object has no attribute 'items'"))
        # getattr with a name the program computed may be what raised: never misuse.
        self.assertIsNone(misuse('x = getattr(ctx.under, STATE.get("f", "vwap"))',
                                 "AttributeError: 'UnderlyingView' object has no attribute 'vwap'"))
        self.assertTrue(misuse("x = ctx.under.vwap", "AttributeError: 'UnderlyingView' object has no attribute 'vwap'"))
        # KeyError: only a key a ctx dict can never hold, and only when nothing else on the line could have raised it.
        self.assertTrue(misuse('x = ctx.chains["QQQ"]', "KeyError: 'QQQ'"))
        self.assertIsNone(misuse('x = ctx.chains["SPY"]', "KeyError: 'SPY'"))  # a NEEDS root without data now
        self.assertIsNone(misuse('x = ctx.events["fomc"]', "KeyError: 'fomc'"))
        self.assertIsNone(misuse('x = "{a}".format(**STATE) + ctx.chains[r].root', "KeyError: 'a'"))
        self.assertIsNone(misuse('x = STATE[k] + ctx.chains[r].n', "KeyError: 'QQQ'"))
        # A ctx dict is built afresh for each call: one the program writes to, mutates or hands on could hold the key on
        # some markets only. So could a ctx field the program reassigns (Ctx's slots take an assignment).
        self.assertIsNone(misuse('if ctx.minute > 900:\n    ctx.chains["QQQ"] = ctx.chain\nx = ctx.chains["QQQ"]', "KeyError: 'QQQ'"))
        self.assertIsNone(misuse('d = ctx.params\nif ctx.minute > 900:\n    d.update(window=1)\nx = ctx.params["window"]',
                                 "KeyError: 'window'"))
        self.assertIsNone(misuse('STATE["p"] = ctx.params\nx = ctx.params["window"]', "KeyError: 'window'"))
        self.assertTrue(misuse('d = ctx.params\nn = len(d) + len(ctx.params.keys())\nx = d["window"]', "KeyError: 'window'"))
        self.assertIsNone(misuse('if ctx.minute > 900:\n    ctx.positions = {}\nx = ctx.positions.items()', items))
        # Numbers, lists and arrays by their receivers.
        self.assertTrue(misuse("x = ctx.under.price[-1]", "TypeError: 'float' object is not subscriptable"))
        self.assertIsNone(misuse('x = STATE.get("p", 0.0)[-1]', "TypeError: 'float' object is not subscriptable"))
        self.assertTrue(misuse("x = ctx.positions()", "TypeError: 'list' object is not callable"))
        self.assertIsNone(misuse('x = STATE["f"]()', "TypeError: 'list' object is not callable"))
        self.assertTrue(misuse("x = ctx.chain.mid[:, 0]", "IndexError: too many indices for array: array is 1-dimensional, "
                                                          "but 2 were indexed"))
        self.assertIsNone(misuse("a = np.zeros(3)\nx = a[:, 0]", "IndexError: too many indices for array: array is "
                                                                  "1-dimensional, but 2 were indexed"))
        self.assertIsNone(misuse("x = ctx.chain.mid[5]", "IndexError: index 5 is out of bounds for axis 0 with size 3"))
        # Never an error this box or the market's numbers may cause, and never the classifier's own failure.
        self.assertIsNone(misuse("x = ctx.under.price.is_integer()", "AttributeError: 'float' object has no attribute "
                                                                      "'is_integer'"))
        self.assertIsNone(misuse("x = min(ctx.chain.strike[ctx.chain.strike < 0])",
                                 "ValueError: min() arg is an empty sequence"))
        self.assertIsNone(api_misuse("line 1: AttributeError: 'list' object has no attribute 'items'", "def (:", roots=[]))
        # A ctx method's wrong argument count only without keywords: `str.replace(count=)` is valid from Python 3.13.
        self.assertIsNone(misuse('x = ctx.root.replace("W", "", count=1)', "TypeError: str.replace() takes no keyword "
                                                                           "arguments"))
        self.assertIsNone(misuse('x = ctx.positions.index(1, start=0)', "TypeError: list.index() takes at least 1 "
                                                                         "argument (0 given)"))
        self.assertTrue(misuse('x = ctx.positions.append()', "TypeError: list.append() takes exactly one argument "
                                                             "(0 given)"))

    def test_the_receivers_scopes_are_pythons(self):
        # `_Source` resolves a name as Python does: a comprehension's targets are its own (not the function's), its first
        # iterable and a function's default values belong to the scope around it, and a name a nested function rebinds
        # with `nonlocal` is unknown in the scope it rebinds.
        from league.swarm.preflight import api_misuse

        def misuse(code, message):
            return api_misuse(message, code, roots=["SPY"], params={})

        mean = "AttributeError: 'dict' object has no attribute 'mean'"
        items = "AttributeError: 'list' object has no attribute 'items'"
        glob = HEAD + 'p = {}\ndef decide(ctx):\n    ids = [p["id"] for p in ctx.positions]\n    m = p.mean()\n    return []\n'
        self.assertIsNone(misuse(glob, f"line 7: {mean}"))  # the module's `p`, not the comprehension's
        own = program("ids = [p.mean() for p in ctx.positions]\nreturn []")
        self.assertTrue(misuse(own, f"line 5: {mean}"))  # inside it, its own target: a position row
        nested = program("rows = [q for p in ctx.positions for q in p.mean()]\nreturn []")
        self.assertTrue(misuse(nested, f"line 5: {mean}"))  # a later iterable sees the comprehension's targets
        first = program("p = ctx.positions\nx = [p for p in p.items()]\nreturn []")
        self.assertTrue(misuse(first, f"line 6: {items}"))  # the first iterable is the function's: its `p`
        walrus = program("ys = [(rows := ctx.positions) for _ in range(1)]\nx = rows.items()\nreturn []")
        self.assertTrue(misuse(walrus, f"line 6: {items}"))  # an assignment expression binds in the function
        swap = program('rows = ctx.positions\ndef swap():\n    nonlocal rows\n    rows = STATE.get("book", [])\nswap()\n'
                       "n = rows.items()\nreturn []")
        self.assertIsNone(misuse(swap, f"line 10: {items}"))
        deep = program('rows = ctx.positions\ndef outer():\n    def inner():\n        nonlocal rows\n        rows = {}\n'
                       "    inner()\nouter()\nn = rows.items()\nreturn []")
        self.assertIsNone(misuse(deep, f"line 12: {items}"))
        default = program('rows = STATE.get("b", [])\ndef f(rows=ctx.positions):\n    return rows.items()\nreturn f()')
        self.assertIsNone(misuse(default, f"line 7: {items}"))  # `rows` in f is a parameter: unknown
        late = program('p = ctx.positions\ndef f(p=None, q=p.items()):\n    return q\nreturn []')
        self.assertTrue(misuse(late, f"line 6: {items}"))  # a default value runs in decide: decide's `p`, not f's

    def test_the_saturated_market(self):
        # Every calendar day of the dte range lists an expiry; every listed strike is there with half the finer step
        # beside it and the far wings; each contract has its own vol, its quote any width from one tick to past its mid,
        # its books up to a million; the underlying's volumes are known.
        from league.gym import venue
        from league.swarm.preflight import Market, strikes

        needs = {"roots": ["SPY"], "dte": [0, 10], "band": 0.05, "cadence": 5, "history": 5, "start": 571, "end": 958}
        listed, market = Market(["SPY"], needs), Market(["SPY"], needs, regime="saturated")
        self.assertEqual(market.weekdays, listed.weekdays)
        snap = market.snapshot("SPY", 0, 60)
        self.assertEqual(sorted(numpy.unique(snap.dte).tolist()), list(range(11)))
        ks = numpy.unique(snap.strike)
        own = strikes("SPY", float(market.days["SPY"][0]["path"][0]))
        self.assertTrue(numpy.isin(numpy.round(own, 6), numpy.round(ks, 6)).all())
        self.assertTrue(numpy.isin(numpy.round(own[len(own) // 2] + 0.5, 6), numpy.round(ks, 6)))
        self.assertGreater(float(ks.max() / snap.spot), 1.09)
        c = snap.view(snap.slice_index(0, 10, 0.05))
        share = c.spread / c.mid
        self.assertLess(float(numpy.nanmin(share)), 0.005)
        self.assertGreater(float(numpy.nanmax(share)), 0.5)
        tick = numpy.array([venue.leg_tick("SPY", float(m)) for m in c.mid])
        self.assertTrue((c.spread >= tick - 1e-9).all())
        iv = c.iv[numpy.isfinite(c.iv)]
        self.assertLess(float(iv.min()), 0.08)
        self.assertGreater(float(iv.max()), 1.5)
        self.assertLess(int(c.bid_size.min()), 10)
        self.assertGreater(int(c.bid_size.max()), 100_000)
        self.assertTrue(numpy.isfinite(market.under("SPY", 1, 30).volume))
        self.assertTrue(numpy.isnan(listed.under("SPY", 1, 30).volume))

    def test_the_account_is_the_runs_capital(self):
        # A program that sizes by its account takes, here, the branch the run's capital (`gym.capital`) opens in the Gym.
        code = program("if ctx.cash > 50000 and ctx.equity > 50000 and ctx.budget > 50000 and ctx.buying_power > 50000:\n"
                       "    for pid, p in ctx.positions.items():\n        pass\nreturn []")
        self.assertEqual(self.check(code)["status"], "passed")
        self.refused(code, capital=100_000)
        self.refused(code, capital="100000")
        for unusable in ("x", -5.0, 0, float("nan"), float("inf")):  # the default account
            self.assertEqual(self.check(code, capital=unusable)["status"], "passed", unusable)

    def test_roots_outside_the_run_are_not_decided_on(self):
        out = self.check(program('u = ctx.under.get("price")\nreturn []'), roots=["QQQ"])
        self.assertEqual(out["status"], "passed")
        self.assertEqual(out["calls"], 0)

    def test_the_market_is_what_the_program_asked_for(self):
        from league.swarm.preflight import Market, decision_minutes

        needs = {"roots": ["SPY", "GLD"], "dte": [0, 30], "band": 0.10, "cadence": 15, "history": 20, "start": 600, "end": 900}
        market = Market(["SPY", "GLD"], needs)
        snap = market.snapshot("GLD", 0, 30)
        chain = snap.view(snap.slice_index(0, 30, 0.10))
        self.assertGreater(chain.n, 100)
        self.assertLessEqual(int(chain.dte.max()), 30)
        self.assertTrue((abs(chain.strike / chain.spot - 1) <= 0.10).all())
        under = market.under("SPY", 1, 30)
        self.assertEqual(len(under.closes), 20)
        self.assertEqual(len(under.prices), 31)
        self.assertTrue(numpy.isnan(under.volume))
        self.assertEqual(decision_minutes(needs)[:2], [30, 45])
        self.assertEqual(Market(["SPY"], {**needs, "history": 0}).under("SPY", 0, 5).closes.shape, (0,))


class SandboxSpawn(unittest.TestCase):
    """The preflight's child is `league.live.decider.Decider`'s own spawn (#443's fail-closed start, namespace probe and
    retry, env and limits), under `PREFLIGHT_UID` instead of 65534. Each scenario runs on both classes: a preflight that
    copied or replaced the decider's spawn would part from it here the first time the decider changed."""

    def setUp(self):
        import tempfile

        from league.live import decider as D
        from league.swarm import preflight as PF

        self.D, self.PF = D, PF
        self.Sandbox = PF._sandbox()
        self.tmp = tempfile.mkdtemp(prefix="preflight-spawn-")
        self.addCleanup(self._clean)
        self.made: list = []

    def _clean(self):
        import os
        import shutil

        for path in [*self.made, self.tmp]:
            if path and os.path.isdir(path):
                for dirpath, _, _ in os.walk(path):
                    os.chmod(dirpath, 0o755)
                shutil.rmtree(path)

    def scenario(self, cls, *, isolated, allow=False, probes=(True,), windows=1):
        """Spawn `windows` times (each after the retry window) with the namespace probe answering `probes` in turn:
        what happened each time, the Popen calls and the probe's credentials."""
        from unittest import mock

        D = self.D
        popens, probed, answers = [], [], iter(probes)

        def popen(command, **kwargs):
            popens.append((command, kwargs))
            return mock.Mock(pid=4242)

        def probe(timeout=10.0, *, credentials=None):
            probed.append(dict(credentials or {}))
            return next(answers)

        outcomes = []
        with mock.patch.object(D, "protect_house_process"), mock.patch("subprocess.Popen", popen), \
                mock.patch.object(D, "_netns_available", probe), mock.patch("tempfile.tempdir", self.tmp), \
                mock.patch.object(self.PF, "child_uids", return_value=(self.PF.PREFLIGHT_UID,) * 2):
            d = cls(timeout=1.0, max_errors=10 ** 9, allow_unisolated=allow)
            d.isolated = isolated
            for n in range(windows):
                if n:
                    d._netns_retry_at = float("-inf")  # NETNS_RETRY_SECONDS have passed
                try:
                    d._spawn()
                    outcomes.append("spawned")
                except D.DeciderError:
                    outcomes.append("refused")
                self.made.append(d._runtime)
                d.proc = None
            # A second spawn inside the retry window never probes again after a failure.
            if outcomes[-1] == "refused" and isolated:
                before = len(probed)
                try:
                    d._spawn()
                except D.DeciderError:
                    outcomes.append("refused in the window")
                self.assertEqual(len(probed), before)
        return outcomes, popens, probed, d

    def same_but_uid(self, live, pre):
        (live_out, live_popen, live_probe, _), (pre_out, pre_popen, pre_probe, _) = live, pre
        self.assertEqual(live_out, pre_out)
        self.assertEqual(len(live_popen), len(pre_popen))
        for (lc, lk), (pc, pk) in zip(live_popen, pre_popen):
            self.assertEqual(lc, pc)
            strip = lambda kw: {k: v for k, v in kw.items() if k not in ("user", "group", "cwd")}  # noqa: E731
            self.assertEqual(strip(lk), strip(pk))
        self.assertEqual(len(live_probe), len(pre_probe))

    def test_the_spawn_is_the_deciders_own(self):
        from unittest import mock

        with mock.patch.object(self.D.Decider, "_spawn") as spawn:
            self.Sandbox(timeout=1.0, max_errors=10 ** 9)._spawn(3.0)
        spawn.assert_called_once_with(3.0)
        self.assertTrue(issubclass(self.Sandbox, self.D.Decider))
        own = {k for k in vars(self.Sandbox) if not k.startswith("__")}
        self.assertEqual(own, {"uid", "_namespace", "_spawn"}, "the preflight overrides only its uid's seams")

    def test_on_the_root_house_only_the_uid_differs(self):
        PF = self.PF
        live = self.scenario(self.D.Decider, isolated=True)
        pre = self.scenario(self.Sandbox, isolated=True)
        self.same_but_uid(live, pre)
        (_, [(_, kw_live)], [probe_live], _), (_, [(command, kw_pre)], [probe_pre], _) = live, pre
        self.assertEqual((kw_live["user"], kw_live["group"], kw_live["extra_groups"]), (65534, 65534, []))
        self.assertEqual((kw_pre["user"], kw_pre["group"], kw_pre["extra_groups"]), (PF.PREFLIGHT_UID, PF.PREFLIGHT_UID, []))
        self.assertEqual(probe_pre["user"], PF.PREFLIGHT_UID, "the namespace probe runs as the preflight's uid")
        self.assertEqual(probe_live["user"], 65534)
        self.assertEqual(command[:3], ["unshare", "--net", "--map-root-user"])
        self.assertEqual(command[-2:], ["-m", "league.live.decider"], "the decider's child (its limit_child)")
        self.assertEqual(kw_pre["env"]["OPENBLAS_NUM_THREADS"], "1")
        self.assertNotIn("GATEWAY_TOKEN", kw_pre["env"])

    def test_off_a_root_house_it_fails_closed(self):
        live = self.scenario(self.D.Decider, isolated=False)
        pre = self.scenario(self.Sandbox, isolated=False)
        self.same_but_uid(live, pre)
        self.assertEqual(pre[0], ["refused"])
        self.assertEqual(pre[1], [], "no child")
        # A test's explicit allowance, as for the decider: no credentials to change.
        live = self.scenario(self.D.Decider, isolated=False, allow=True)
        pre = self.scenario(self.Sandbox, isolated=False, allow=True)
        self.same_but_uid(live, pre)
        self.assertNotIn("user", pre[1][0][1])

    def test_a_failed_namespace_probe_is_retried_as_the_deciders(self):
        for probes in ((False, True), (False, False)):
            live = self.scenario(self.D.Decider, isolated=True, probes=probes, windows=2)
            pre = self.scenario(self.Sandbox, isolated=True, probes=probes, windows=2)
            self.same_but_uid(live, pre)
            self.assertEqual(pre[0][0], "refused", probes)
            self.assertEqual(pre[0][1], "spawned" if probes[1] else "refused", probes)

    def test_a_child_that_is_not_the_preflights_uid_is_killed(self):
        # Should a later decider stop handing its credentials to _namespace, the child would run as 65534.
        from unittest import mock

        D = self.D
        killed = []
        with mock.patch.object(D, "protect_house_process"), mock.patch("subprocess.Popen", return_value=mock.Mock(pid=4242)), \
                mock.patch.object(D, "_netns_available", return_value=True), mock.patch("tempfile.tempdir", self.tmp), \
                mock.patch.object(self.PF, "child_uids", return_value=(65534, 65534)):
            d = self.Sandbox(timeout=1.0, max_errors=10 ** 9)
            d.isolated = True
            d._kill = lambda: killed.append(d.proc)
            with self.assertRaises(D.DeciderError):
                d._spawn()
            self.made.append(d._runtime)
        self.assertEqual(len(killed), 1)

    def test_the_child_runs_at_the_lowest_priority(self):
        # The House has one core and the live decider's child runs at nice 5: the preflight's child is reniced to 19
        # right after its spawn, so the live minute wins the core. A stand-in (a test's mock) is never reniced.
        import os
        import subprocess
        import sys
        from unittest import mock

        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        try:
            self.PF._lowest_priority(child)
            self.assertEqual(os.getpriority(os.PRIO_PROCESS, child.pid), self.PF.PREFLIGHT_NICE)
        finally:
            child.kill()
            child.wait()
        with mock.patch("os.setpriority") as renice:
            self.PF._lowest_priority(mock.Mock(pid=4242))
            self.PF._lowest_priority(None)
        renice.assert_not_called()
        with mock.patch.object(self.D.Decider, "_spawn"), mock.patch.object(self.PF, "_lowest_priority") as lowest:
            self.Sandbox(timeout=1.0, max_errors=10 ** 9)._spawn(3.0)
        lowest.assert_called_once()

    @unittest.skipUnless(Path("/proc/self/status").exists(), "no /proc")
    def test_the_uid_is_read_back_from_proc(self):
        import os

        self.assertEqual(self.PF.child_uids(os.getpid()), (os.getuid(), os.geteuid()))
        self.assertEqual(self.PF.child_uids(2 ** 22 + 12345), ())


@unittest.skipUnless(HAVE, "numpy not installed")
class ResearcherPreflight(unittest.TestCase):
    """gym_run and gym_sweep: a refused preflight makes no version, no Gym job, no trial, and is written in the notebook."""

    def setUp(self):
        from league.live.decider import InlineDecider
        from league.swarm import settings as S
        from league.swarm.models import ModelRouter
        from league.swarm.preflight import Preflight as Check
        from league.swarm.researcher import Researcher
        from league.swarm.seeds import SEEDS, family_spec, program_for
        from league.swarm.store import SwarmStore
        from league.tests.swarm_fakes import Clock, provider
        from league.tests.test_swarm_researcher import FakePool

        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        root = Path(self.dir.name)
        self.clock = Clock()
        self.store = SwarmStore(root, clock=self.clock)
        self.addCleanup(self.store.close)
        self.settings = copy.deepcopy(S.DEFAULTS)
        self.steps: list = []
        self.provider, self.sail = provider(root / "p.sqlite", lambda body: self.steps.pop(0) if self.steps else {"text": "done"})
        self.addCleanup(self.provider.close)
        router = ModelRouter(self.store, self.provider, settings=self.settings)
        self.pool = FakePool()
        spec = next(s for s in SEEDS if s["id"] == "condor-vrp")
        self.fam = self.store.add_family(family_spec(spec), origin="seed")
        self.check = Check(InlineDecider(timeout=1.0, max_errors=10 ** 9))
        self.make = lambda: Researcher(self.store, router, self.pool, self.settings, clock=self.clock, starter=program_for,
                                       background=False, preflight=self.check)
        self.make().cycle(self.fam["id"])  # the starter's own Train run (it passes the preflight)
        self.assertEqual(len(self.pool.jobs), 1)

    def answer(self):
        from league.tests.test_swarm_researcher import calls_in

        return json.loads(calls_in(self.sail.bodies[-1])[-1]["output"])

    def test_a_misuse_is_refused_before_the_gym(self):
        bad = program('for pid, p in ctx.positions.items():\n    pass\nif ctx.params["k"] > 9:\n    return []\nreturn []')
        revisions = self.store.family(self.fam["id"])["revisions"]
        self.steps = [{"calls": [("gym_run", {"code": bad, "params": {"k": 2.0}})]}, {"text": "ok"}]
        out = self.make().cycle(self.fam["id"])
        answer = self.answer()
        self.assertEqual((answer["status"], answer["stage"]), ("refused", "preflight"), answer)
        self.assertIn("'list' object has no attribute 'items'", answer["error"])
        self.assertIn("LISTS", answer["hint"])
        self.assertEqual(answer["source"], "for pid, p in ctx.positions.items():")
        self.assertEqual(len(self.pool.jobs), 1, "no Gym job")
        self.assertEqual(self.store.family(self.fam["id"])["revisions"], revisions, "no version")
        self.assertEqual(out.get("preflight_refused"), 1)
        self.assertEqual(out.get("run_refused"), 1)
        notes = [n["text"] for n in self.store.notebook(self.fam["id"])]
        self.assertTrue(any(n.startswith("Preflight refused") and "LISTS" in n for n in notes), notes)

    def test_a_valid_program_goes_on_to_the_gym(self):
        from league.swarm.seeds import SEEDS, program_for

        code, _ = program_for(next(s for s in SEEDS if s["id"] == "condor-vrp"))
        self.steps = [{"calls": [("gym_run", {"code": code, "params": {"vrp_min": 1.3}})]}, {"text": "ok"}]
        out = self.make().cycle(self.fam["id"])
        self.assertEqual(len(self.pool.jobs), 2)
        self.assertEqual(out.get("preflight"), 1)
        self.assertNotIn("preflight_refused", out)

    def test_an_inconclusive_preflight_is_counted_and_runs(self):
        self.check = lambda *args, **kwargs: {"status": "inconclusive", "why": "another preflight held the sandbox"}
        bad = program('px = ctx.under.get("price")\nreturn []')
        self.steps = [{"calls": [("gym_run", {"code": bad})]}, {"text": "ok"}]
        out = self.make().cycle(self.fam["id"])
        self.assertEqual(len(self.pool.jobs), 2)
        self.assertEqual(out.get("preflight_inconclusive"), 1)
        self.assertEqual(out.get("preflight_inconclusive_why"), "another preflight held the sandbox")

    def test_switched_off_in_settings(self):
        self.settings["researcher"]["preflight"] = False
        bad = program('px = ctx.under.get("price")\nreturn []')
        self.steps = [{"calls": [("gym_run", {"code": bad})]}, {"text": "ok"}]
        self.make().cycle(self.fam["id"])
        self.assertEqual(len(self.pool.jobs), 2, "off: the Gym runs it as before")

    def test_a_broken_preflight_never_blocks_a_run(self):
        def broken(*args, **kwargs):
            raise RuntimeError("the sandbox is gone")

        self.check = broken
        bad = program('px = ctx.under.get("price")\nreturn []')
        self.steps = [{"calls": [("gym_run", {"code": bad})]}, {"text": "ok"}]
        out = self.make().cycle(self.fam["id"])
        self.assertEqual(len(self.pool.jobs), 2)
        self.assertIn("preflight_error", out)

    def test_an_advisory_rides_along_with_the_run(self):
        # decide raised on every call, but not with a misuse no market could spare: the run goes to the Gym, and its
        # answer carries the preflight's warning (the line, its source, the API).
        code = program('prev = STATE["last"]\nSTATE["last"] = ctx.under.price\nif ctx.params["k"] > 9:\n    return []\nreturn []')
        self.steps = [{"calls": [("gym_run", {"code": code, "params": {"k": 2.0}})]}, {"text": "ok"}]
        out = self.make().cycle(self.fam["id"])
        answer = self.answer()
        self.assertEqual(len(self.pool.jobs), 2, "the run went ahead")
        self.assertEqual(out.get("preflight_advisory"), 1)
        self.assertNotIn("preflight_refused", out)
        note = answer["preflight"]
        self.assertEqual(note["status"], "advisory")
        self.assertIn("went ahead", note["note"])
        warning = note["warnings"][0]
        self.assertIn("KeyError: 'last'", warning["error"])
        self.assertEqual(warning["source"], 'prev = STATE["last"]')
        self.assertIn("STATE", warning["hint"])
        notes = [n["text"] for n in self.store.notebook(self.fam["id"])]
        self.assertFalse(any(n.startswith("Preflight refused") for n in notes), notes)

    def test_a_sweeps_advisories_name_their_variants(self):
        code = program('if ctx.params["k"] > 1:\n    x = STATE["never"]\nreturn []')
        self.steps = [{"calls": [("gym_sweep", {"code": code, "variants": [{"k": 2.0}, {"k": 5.0}, {"k": 0.0}]})]},
                      {"text": "ok"}]
        out = self.make().cycle(self.fam["id"])
        answer = self.answer()
        self.assertEqual(len(self.pool.jobs), 4, "every variant went ahead")
        self.assertEqual(out.get("preflight_advisory"), 2)
        rows = answer["preflight"]["variants"]
        self.assertEqual([r["variant"] for r in rows], [{"k": 2.0}, {"k": 5.0}])
        self.assertIn("KeyError: 'never'", rows[0]["warnings"][0]["error"])

    def test_a_sweep_drops_only_its_refused_variants(self):
        # One variant misuses the ctx API on a branch only it takes: it alone is dropped (no version, job or trial) and
        # reported; the others run.
        code = program('if ctx.params["k"] > 1:\n    for pid, p in ctx.positions.items():\n        pass\nreturn []')
        revisions, versions = self.store.family(self.fam["id"])["revisions"], len(self.store.versions(self.fam["id"]))
        self.steps = [{"calls": [("gym_sweep", {"code": code, "variants": [{"k": 0.0}, {"k": 5.0}, {"k": 0.5}]})]},
                      {"text": "ok"}]
        out = self.make().cycle(self.fam["id"])
        answer = self.answer()
        self.assertEqual(answer.get("status"), "ok", answer)
        self.assertEqual(sorted(job.params["k"] for job in self.pool.jobs[1:]), [0.0, 0.5])
        self.assertEqual((answer["variants"], len(answer["table"])), (2, 2))
        self.assertEqual(self.store.family(self.fam["id"])["revisions"], revisions + 1, "the sweep that ran is one revision")
        self.assertEqual(len(self.store.versions(self.fam["id"])), versions + 2, "a version per variant that ran")
        [row] = answer["refused_variants"]
        self.assertEqual(row["params"], {"k": 5.0})
        self.assertIn("'list' object has no attribute 'items'", row["error"])
        self.assertEqual(row["source"], "for pid, p in ctx.positions.items():")
        self.assertIn("LISTS", row["hint"])
        self.assertTrue(row["misuse"])
        self.assertIn("refused 1 variant", answer["refused_note"])
        self.assertEqual(out.get("preflight_refused"), 1)
        self.assertNotIn("run_refused", out, "the sweep ran: not a refusal of the researcher's doing")
        notes = [n["text"] for n in self.store.notebook(self.fam["id"])]
        self.assertTrue(any(n.startswith("Preflight refused") and "variant 2 of 3" in n for n in notes), notes)

    def test_a_sweep_whose_every_new_variant_is_refused_is_refused(self):
        code = program('if ctx.params["k"] > 1:\n    for pid, p in ctx.positions.items():\n        pass\nreturn []')
        self.steps = [{"calls": [("gym_sweep", {"code": code, "variants": [{"k": 5.0}, {"k": 7.0}]})]}, {"text": "ok"}]
        out = self.make().cycle(self.fam["id"])
        answer = self.answer()
        self.assertEqual((answer.get("status"), answer.get("stage")), ("refused", "preflight"), answer)
        self.assertEqual(answer["variant"], {"k": 5.0})
        self.assertIn("'list' object has no attribute 'items'", answer["error"])
        self.assertEqual([r["params"] for r in answer["refused_variants"]], [{"k": 5.0}, {"k": 7.0}])
        self.assertIn("every new variant", answer["reason"])
        self.assertEqual(len(self.pool.jobs), 1)
        self.assertEqual((out.get("preflight_refused"), out.get("run_refused")), (2, 1))

    def test_the_runs_capital_reaches_the_preflight(self):
        # The run's capital (`gym.capital`), not the default 10k: a misuse only an account over 50k reaches is refused.
        bad = program('if ctx.cash > 50000:\n    for pid, p in ctx.positions.items():\n        pass\nreturn []')
        self.assertEqual(self.check(bad)["status"], "passed", "at 10k the branch is never taken")
        self.settings["gym"]["capital"] = 100_000.0
        self.steps = [{"calls": [("gym_run", {"code": bad})]}, {"text": "ok"}]
        out = self.make().cycle(self.fam["id"])
        self.assertEqual(out.get("preflight_refused"), 1)
        self.assertEqual(len(self.pool.jobs), 1, "no Gym job")

    def test_a_load_only_the_house_fails_rides_along(self):
        # A module body the House's Python cannot load (whatever the reason) is the Gym's to judge: the run goes ahead,
        # with the load's warning.
        code = HEAD + 'TABLE = {"a": 1}\nFIRST = TABLE.get("b", {})["c"]\ndef decide(ctx):\n    return []\n'
        self.steps = [{"calls": [("gym_run", {"code": code})]}, {"text": "ok"}]
        out = self.make().cycle(self.fam["id"])
        answer = self.answer()
        self.assertEqual(len(self.pool.jobs), 2)
        self.assertEqual(out.get("preflight_advisory"), 1)
        self.assertIn("fails to load", answer["preflight"]["warnings"][0]["error"])


if __name__ == "__main__":
    unittest.main()
