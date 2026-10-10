"""The equity program contract (EQUITY.md): NEEDS, PARAMS, the options code rules imported unchanged, the intents."""

from __future__ import annotations

import unittest

import numpy as np

from league.equity import config
from league.equity.program import (CodeRefused, Needs, NeedsRefused, load_program, normalize_intents, parse_needs)
from league.gym import runtime

CODE = """
import numpy as np

NEEDS = {"symbols": ["spy", "QQQ", "SPY"], "history": 10, "max_hold_sessions": 5}
PARAMS = {"theta": 0.02, "share": 0.5}
STATE = {"calls": 0}

def decide(ctx):
    STATE["calls"] += 1
    if ctx == "boom":
        raise ValueError("boom")
    if ctx == "slow":
        x = 0
        while True:
            x += 1
    if ctx == "junk":
        return [{"buy": "SPY"}, {"sell": 1.5}, {"buy": "SPY", "share": 0.1, "at": "noon"}, {"buy": "SPY", "usd": 5}]
    return [{"buy": "SPY", "share": PARAMS["share"], "at": "close", "tag": "t"}, {"sell": 3}]
"""


class Needs_(unittest.TestCase):
    def test_defaults_and_normalization(self):
        needs = parse_needs({"symbols": "spy"})
        self.assertEqual(needs, Needs(("SPY",), config.DEFAULT_HISTORY, config.DEFAULT_MAX_HOLD))
        self.assertEqual(needs.as_dict(), {"symbols": ["SPY"], "history": 252, "max_hold_sessions": 20})
        self.assertEqual(parse_needs({"symbols": ["qqq", "SPY", "QQQ"], "history": 0, "max_hold_sessions": 60.0}),
                         Needs(("QQQ", "SPY"), 0, 60))

    def test_refusals(self):
        bad = [None, [], {"symbols": []}, {"symbols": ["SPY"], "cadence": 5}, {"symbols": ["TSLA"]},
               {"symbols": [f"S{i}" for i in range(3)]}, {"symbols": list(config.UNIVERSE)[:21]},
               {"symbols": ["SPY"], "history": 505}, {"symbols": ["SPY"], "history": -1},
               {"symbols": ["SPY"], "history": 2.5}, {"symbols": ["SPY"], "history": True},
               {"symbols": ["SPY"], "max_hold_sessions": 0}, {"symbols": ["SPY"], "max_hold_sessions": 61},
               {"symbols": [1]}]
        for raw in bad:
            with self.subTest(raw=raw), self.assertRaises(NeedsRefused):
                parse_needs(raw)
        self.assertTrue(issubclass(NeedsRefused, CodeRefused))
        self.assertTrue(issubclass(NeedsRefused, runtime.NeedsRefused))


class Loading(unittest.TestCase):
    def test_load_binds_params_and_names_the_run(self):
        program = load_program(CODE, name="p")
        self.assertEqual(program.needs, Needs(("SPY", "QQQ"), 10, 5))
        self.assertEqual(program.params, {"theta": 0.02, "share": 0.5})
        other = load_program(CODE, name="p", params={"share": 0.25})
        self.assertEqual(other.sha, program.sha)
        self.assertNotEqual(other.run_sha, program.run_sha)
        self.assertEqual(other.start().decide(None)[0]["share"], 0.25, "PARAMS are bound at the declaration")

    def test_the_options_code_rules_apply_unchanged(self):
        for code in (CODE.replace("import numpy as np", "import os"), CODE.replace("0.02", "2025"),
                     CODE.replace('"t"}', '"2025-01-02"}'), CODE.replace("def decide(ctx):", "def decide(ctx, x):"),
                     "NEEDS = {'symbols': ['SPY']}\ndef decide(ctx):\n    return []\n"):
            with self.subTest(code=code[:60]), self.assertRaises(CodeRefused):
                load_program(code)

    def test_bad_params_and_needs_are_needs_refused(self):
        with self.assertRaises(NeedsRefused):
            load_program(CODE, params={"nope": 1})
        with self.assertRaises(NeedsRefused):
            load_program(CODE, params={"share": "half"})
        with self.assertRaises(NeedsRefused):
            load_program(CODE.replace('"history": 10', '"history": 999'))


class Running(unittest.TestCase):
    def test_a_runner_keeps_memory_and_counts_failures(self):
        runner = load_program(CODE).start(timeout=0.2, max_errors=3)
        self.assertEqual(len(runner.decide(None)), 2)
        self.assertFalse(runner.last_failed)
        self.assertEqual(runner.decide("boom"), [])
        self.assertTrue(runner.last_failed, "an exception is a failed decide")
        self.assertEqual(runner.decide("slow"), [])
        self.assertTrue(runner.last_failed, "a timeout is a failed decide")
        stats = runner.stats()
        self.assertEqual((stats["calls"], stats["errors"], stats["timeouts"]), (3, 2, 1))
        self.assertEqual(runner.decide("junk"), [{"buy": "SPY", "usd": 5.0, "at": "open", "tag": ""}],
                         "a small buy is well-formed: the $10 minimum is the sizer's, not the contract's")
        self.assertFalse(runner.last_failed, "malformed intents are errors, never a failed decide")
        self.assertTrue(runner.stats()["disqualified"])
        self.assertEqual(runner.decide(None), [])
        self.assertTrue(runner.last_failed, "a disqualified runner fails every decide")
        fresh = load_program(CODE).start()
        self.assertEqual(fresh.decide(None)[0]["tag"], "t", "a new runner starts with fresh module state")


class Intents(unittest.TestCase):
    def test_well_formed_intents_are_normalized(self):
        rows = normalize_intents([{"buy": " spy ", "share": np.float64(0.5)}, {"buy": "QQQ", "usd": 250, "at": "close",
                                                                               "tag": "x" * 100},
                                  {"sell": np.int64(17), "at": "open"}, {"sell": 4.0, "at": "close", "tag": 7},
                                  {"cancel": 3}])
        self.assertEqual(rows, [{"buy": "SPY", "share": 0.5, "at": "open", "tag": ""},
                                {"buy": "QQQ", "usd": 250.0, "at": "close", "tag": "x" * 64},
                                {"sell": 17, "at": "open", "tag": ""}, {"sell": 4, "at": "close", "tag": "7"},
                                {"cancel": 3}])
        self.assertEqual(normalize_intents(None), [])
        self.assertEqual(normalize_intents({"sell": 1}), [{"sell": 1, "at": "open", "tag": ""}])

    def test_malformed_intents_are_dropped_and_reported(self):
        errors = []
        bad = [{"buy": "SPY"}, {"buy": "SPY", "share": 0.5, "usd": 10}, {"buy": "SPY", "share": 1.5},
               {"buy": "SPY", "share": 0}, {"buy": "SPY", "usd": -1}, {"buy": "", "usd": 1},
               {"buy": "SPY", "usd": 1, "at": "noon"}, {"sell": -1}, {"sell": 1.5}, {"sell": True},
               {"cancel": "x"}, {"buy": "SPY", "sell": 1}, {}, "SPY", {"buy": "SPY", "usd": float("nan")}]
        self.assertEqual(normalize_intents(bad, errors.append), [])
        self.assertEqual(len(errors), len(bad))
        self.assertEqual(normalize_intents(7, errors.append), [])
        self.assertIn("list of intents", errors[-1])

    def test_at_most_twenty_count(self):
        errors = []
        rows = normalize_intents([{"sell": i} for i in range(25)], errors.append)
        self.assertEqual(len(rows), config.MAX_INTENTS)
        self.assertEqual(rows[-1]["sell"], 19)
        self.assertEqual(len(errors), 1)


if __name__ == "__main__":
    unittest.main()
