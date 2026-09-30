"""The preflight (league/swarm/preflight.py): agent API misuse is refused on a synthetic session before a Train run is
spent, and nothing that would run in the Gym is (no false refusals: every seed and example program passes)."""

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
    def check(self, code, params=None, roots=None, timeout=1.0):
        from league.live.decider import InlineDecider
        from league.swarm.preflight import run

        return run(code, params or {}, InlineDecider(timeout=timeout, max_errors=10 ** 9), universe=roots)

    def refused(self, code, stage="decide", **kw):
        out = self.check(code, **kw)
        self.assertEqual(out["status"], "refused", out)
        self.assertEqual(out["stage"], stage, out)
        return out

    def passed(self, code, **kw):
        out = self.check(code, **kw)
        self.assertNotEqual(out["status"], "refused", out)
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
        # A None can be a search that found nothing on this made-up market: never a refusal (the Gym judges it). The
        # advice for one still names the program's PARAMS.
        from league.swarm.preflight import advice

        out = self.check(program('x = ctx.params.get("missing") / 2.0\nreturn []'))
        self.assertEqual(out["status"], "inconclusive", out)
        self.assertIn("market", out["why"])
        hint = advice("line 5: TypeError: unsupported operand type(s) for /: 'NoneType' and 'float'", params={"k": 1.0})
        self.assertIn("is None", hint)
        self.assertIn(": k", hint)

    def test_a_root_it_never_asked_for(self):
        out = self.refused(program('u = ctx.underlyings["QQQ"]\nreturn []'))
        self.assertIn("KeyError: 'QQQ'", out["error"])
        self.assertIn("SPY", out["hint"])

    def test_state_that_never_fills_errs_every_session(self):
        out = self.refused(program('prev = STATE["last"]\nSTATE["last"] = ctx.under.price\nreturn []'))
        self.assertIn("KeyError: 'last'", out["error"])
        self.assertIn("STATE", out["hint"])

    def test_a_params_key_read_from_the_wrong_place(self):
        out = self.refused(program('n = STATE["k"]\nreturn []'))
        self.assertIn("ctx.params['k']", out["hint"])

    def test_the_advice_names_the_declared_params(self):
        out = self.refused(program('x = PARAMS["window"]\nreturn []'))
        self.assertIn("KeyError: 'window'", out["error"])
        self.assertIn(": k", out["hint"])

    def test_a_module_body_that_fails_to_load(self):
        code = HEAD + 'TABLE = {"a": 1}\nFIRST = TABLE["b"]\ndef decide(ctx):\n    return []\n'
        out = self.refused(code, stage="load")
        self.assertIn("fails to load", out["error"])
        self.assertEqual(out["line"], 5)

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
        # Errs on its first 10 calls (fewer than the Gym's 25), then runs.
        self.passed(program('STATE["n"] = STATE.get("n", 0) + 1\nif STATE["n"] <= 10:\n    raise ValueError("warming")\nreturn []'))

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

    def test_a_numpy_api_error_is_inconclusive(self):
        # The House's numpy is not the Gym boxes' (requirements-gym.txt): an API one has and the other lacks says nothing.
        code = "import numpy as np\n" + program("x = np.not_in_this_numpy(1.0)\nreturn []")
        out = self.check(code)
        self.assertEqual(out["status"], "inconclusive", out)

    def test_a_missing_stdlib_function_is_inconclusive(self):
        # The House runs Python 3.11; the Gym's boxes 3.12+ (math.sumprod, int.is_integer): not the program's fault.
        out = self.check("import math\n" + program("x = math.not_in_this_python([1.0], [2.0])\nreturn []"))
        self.assertEqual(out["status"], "inconclusive", out)

    def test_what_is_this_box_and_what_is_the_program(self):
        from league.swarm.preflight import environmental

        for message in ("line 5: AttributeError: module 'math' has no attribute 'sumprod'",
                        "line 5: AttributeError: module 'numpy.linalg' has no attribute 'vecdot'",
                        "line 5: AttributeError: 'int' object has no attribute 'is_integer'",
                        "line 5: AttributeError: 'float' object has no attribute 'from_number'",
                        "line 5: AttributeError: 'numpy.ndarray' object has no attribute 'to_device'",
                        "line 5: MemoryError: Unable to allocate 2.24 GiB for an array with shape (20000, 15000)",
                        "line 5: MemoryError: ", "decide recursed too deep",
                        "line 5: TypeError: sort() got an unexpected keyword argument 'stable'"):
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

    def test_an_error_on_the_market_numbers_is_inconclusive(self):
        from league.swarm.preflight import market_dependent

        head = "import numpy as np\n" + HEAD
        for body in ("i = np.flatnonzero(ctx.chain.strike == round(ctx.under.price) + 0.25)[0]\nreturn []",
                     "x = 1.0 / (ctx.chain.n * 0)\nreturn []",
                     "k = min(s for s in ctx.chain.strike if s < 0)\nreturn []"):
            out = self.check(program(body, head=head))
            self.assertEqual(out["status"], "inconclusive", (body, out))
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
                        "only length-1 arrays can be converted to Python scalars"):
            self.assertTrue(market_dependent(f"line 5: TypeError: {message}"), message)
        self.assertTrue(market_dependent("line 5: LinAlgError: SVD did not converge in Linear Least Squares"))
        self.assertFalse(market_dependent("line 5: KeyError: 'window'"))
        for message in ("ValueError: The truth value of an array with more than one element is ambiguous. Use a.any() or "
                        "a.all()", "ValueError: could not convert string to float: 'SPY'",
                        "TypeError: 'UnderlyingView' object is not subscriptable",
                        "TypeError: expected x and y to have same length", "ValueError: fp and xp are not of the same length.",
                        "TypeError: unsupported operand type(s) for -: 'list' and 'float'"):
            self.assertFalse(market_dependent(f"line 5: {message}"), message)

    def test_an_empty_selection_never_refuses_on_this_runtime(self):
        # Raised here, on the Python and numpy these tests run on (CI: 3.11 with numpy 2.4.4, the House's; 3.14 with
        # numpy 2.5.3), and read as the Gym's Runner reports them: whatever each runtime says, an empty selection, or
        # one turned into a single number, is the market's doing; the misuses are not.
        import warnings

        from league.swarm.preflight import market_dependent

        empty, two = numpy.zeros(0), numpy.array([1.0, 2.0])
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
                  "1/0": lambda: 1 / 0, "np.linalg": lambda: numpy.linalg.inv(numpy.zeros((2, 2)))}
        misuse = {"a list as a mapping": lambda: [].items(), "two as one boolean": lambda: bool(two),
                  "a string as a number": lambda: float("SPY"), "a dict as an object": lambda: {}.price,
                  "arrays of two lengths": lambda: numpy.interp(0.3, two, empty)}
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

        def finer(root, *, sparse=False):
            return real(root, sparse=True) if sparse else (real(root)[0], 0.5, PF.DAILY)

        head = ('import numpy as np\nNEEDS = {"roots": ["TSLA"], "dte": [0, 7], "band": 0.05, "cadence": 5, "history": 5}\n'
                'PARAMS = {"edge": 50.0}\nSTATE = {}\n')
        body = ("c = ctx.chain\nk = round(ctx.under.price / 2.5) * 2.5\natm = c.is_call & np.isclose(c.strike, k, atol=1.0)\n"
                "if c.ask[atm] - c.bid[atm] > ctx.params[\"edge\"]:\n    return []\nreturn []")
        with mock.patch.object(PF, "listing", finer):
            out = self.check(program(body, head=head))
        self.assertEqual(out["status"], "inconclusive", out)
        self.assertIn("sparser listing", out["why"])
        self.assertIn("truth value of an array", out["why"])
        # The same misuse on every chain still refuses, confirmed on the sparser listing.
        out = self.refused(program("for pid, p in ctx.positions.items():\n    pass\nreturn []"))
        self.assertIn("again on a sparser listing", out["why"])

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
            out = self.check(program(body, head=head), {"max_spread": 0.04})
            self.assertEqual(out["status"], "passed", (what, out))
            # A filter no quote could meet here keeps nothing on the tightest market either: never a refusal still.
            for cap in (0.01, 0.002):
                out = self.check(program(body, head=head), {"max_spread": cap})
                self.assertNotEqual(out["status"], "refused", (what, cap, out))

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

    def test_a_refusal_must_recur_on_other_numbers(self):
        # Each errs on every call of the listed market and of the sparser listing (the same numbers), but not on one of
        # the others: a STATE key written only on one-tick quotes, only at a high vol, only at a low vol.
        head = ('import numpy as np\nNEEDS = {"roots": ["SPY"], "dte": [0, 7], "band": 0.05, "cadence": 5, "history": 10}\n'
                'PARAMS = {}\nSTATE = {}\n')
        atm = ("c = ctx.chain\ni = np.flatnonzero(c.is_call & (c.dte == c.dte.max()))\n"
               "iv = float(c.iv[i[np.argmin(np.abs(c.strike[i] - c.spot))]])\n")
        for condition, spared in (("(c.spread <= 0.0101).all()", "one tick wide"), ("iv > 0.28", "one tick wide"),
                                  ("iv < 0.12", "three times as wide")):
            out = self.check(program(atm + f'if {condition}:\n    STATE["seen"] = True\nx = STATE["seen"]\nreturn []', head=head))
            self.assertEqual(out["status"], "inconclusive", (condition, out))
            self.assertIn(spared, out["why"], condition)
            self.assertIn("KeyError: 'seen'", out["why"], condition)
        # Where another market could not say (there, an error its numbers cause), neither can the preflight: its reason.
        out = self.check(program("c = ctx.chain\nif (c.spread <= 0.0101).all():\n    k = c.strike[c.strike < 0][0]\n"
                                 "for pid, p in ctx.positions.items():\n    pass\nreturn []", head=head))
        self.assertEqual(out["status"], "inconclusive", out)
        self.assertIn("one tick wide", out["why"])
        self.assertIn("IndexError", out["why"])
        # A misuse on any market is refused, on every one of them.
        out = self.refused(program("for pid, p in ctx.positions.items():\n    pass\nreturn []"))
        for words in ("sparser listing", "one tick wide", "three times as wide"):
            self.assertIn(words, out["why"])

    def test_the_chain_is_the_listing(self):
        # The listed step, the store's strikes a side of the open's money (40 for SPXW only, as storelib's STRIKE_RANGE),
        # the root's expiry weekdays and the store's reach in days to expiry (14; SPY and QQQ 45); the sparse listing:
        # Fridays and the next wider step.
        from league.swarm.preflight import FRIDAY, Market, STORE_DEFAULT_STRIKES, listing

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

    def test_a_streak_the_runners_list_cannot_name_is_inconclusive(self):
        # Ten distinct warm-up errors fill the Runner's message list (it keeps ten); the streak after them is not in it,
        # so neither its line nor whether it is this box's error can be known.
        for tail in ("for pid, p in ctx.positions.items():\n        pass", "x = np.not_in_this_numpy(1.0)"):
            body = ('n = STATE.get("n", 0) + 1\nSTATE["n"] = n\nif n <= 20 and n % 2 == 0:\n'
                    '    raise ValueError("warm " + str(n))\nif n > 20:\n    ' + tail + "\nreturn []")
            out = self.check(program(body, head="import numpy as np\n" + HEAD))
            self.assertEqual(out["status"], "inconclusive", (tail, out))

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

    def test_a_sweep_with_a_failing_variant_is_refused_whole(self):
        code = program('if ctx.params["k"] > 1:\n    for pid, p in ctx.positions.items():\n        pass\nreturn []')
        self.steps = [{"calls": [("gym_sweep", {"code": code, "variants": [{"k": 0.0}, {"k": 5.0}]})]}, {"text": "ok"}]
        out = self.make().cycle(self.fam["id"])
        answer = self.answer()
        self.assertEqual((answer.get("status"), answer.get("stage")), ("refused", "preflight"), answer)
        self.assertEqual(answer["variant"], {"k": 5.0})
        self.assertIn("'list' object has no attribute 'items'", answer["error"])
        self.assertEqual(len(self.pool.jobs), 1)
        self.assertEqual(out.get("preflight_refused"), 1)


if __name__ == "__main__":
    unittest.main()
