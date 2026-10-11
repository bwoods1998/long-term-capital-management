"""The panel program contract (league/xs/XS.md): NEEDS, PARAMS, the Gym's code rules imported unchanged, the answer.

D10's target rule is held here line by line (`normalize_target`); the KEEP rule that turns a valid target into orders
is the engine's (package D).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import tempfile
import unittest
from pathlib import Path

import numpy as np

from league.equity import program as e1
from league.gym import runtime
from league.xs import config
from league.xs.program import (ANSWER_KEYS, AT, NEEDS_KEYS, WEIGHT_SLACK, CodeRefused, Needs, NeedsRefused, XsProgram,
                               XsRunner, load_program, normalize_target, parse_needs)

CODE = """
import numpy as np

NEEDS = {"panel": "sp500", "history": 60, "max_names": 6, "rebalance": "weekly", "weekday": 2,
         "max_hold_sessions": 30}
PARAMS = {"k": 5, "weight": 0.2}
STATE = {"calls": 0}

def decide(ctx):
    STATE["calls"] += 1
    if ctx.mode == "boom":
        raise ValueError("boom")
    if ctx.mode == "slow":
        x = 0
        while True:
            x += 1
    if ctx.mode == "junk":
        return {"target": {int(ctx.ids[0]): 0.5}, "at": "open"}
    if ctx.mode == "hold":
        return {"hold": True}
    if ctx.mode == "none":
        return None
    if ctx.mode == "count":
        return {"target": {}, "at": "close", "calls": STATE["calls"]}
    picks = ctx.ids[:PARAMS["k"]]
    return {"target": {i: PARAMS["weight"] for i in picks}, "at": "close"}
"""


class Ctx:
    """What a runner needs of a ctx: its ids (and this test's switch)."""

    def __init__(self, mode: str = "", n: int = 20):
        self.mode = mode
        self.ids = np.arange(1000, 1000 + n, dtype=np.int32) * 7


IDS = Ctx().ids


class TheNeeds(unittest.TestCase):
    def test_defaults(self):
        needs = parse_needs({"panel": "sp500", "rebalance": "weekly"})
        self.assertEqual(needs, Needs("sp500", 252, 10, "weekly", 0, 60))
        self.assertEqual(needs.as_dict(), {"panel": "sp500", "history": 252, "max_names": 10, "rebalance": "weekly",
                                           "weekday": 0, "max_hold_sessions": 60})
        self.assertEqual(tuple(needs.as_dict()), NEEDS_KEYS)
        self.assertEqual(parse_needs({"panel": "sp500", "rebalance": "monthly", "history": 20.0, "max_names": 40,
                                      "max_hold_sessions": 5}), Needs("sp500", 20, 40, "monthly", 0, 5))

    def test_the_parent_reads_back_what_the_child_parsed(self):
        """The runner's parent re-parses the child's `as_dict`: it is the same NEEDS, a monthly program's too."""
        for raw in ({"panel": "sp500", "rebalance": "weekly", "weekday": 4, "history": 21, "max_names": 5,
                     "max_hold_sessions": 6}, {"panel": "sp500", "rebalance": "monthly"}):
            needs = parse_needs(raw)
            self.assertEqual(parse_needs(json.loads(json.dumps(needs.as_dict()))), needs)

    def test_the_bounds(self):
        self.assertEqual((config.MIN_HISTORY, config.MAX_HISTORY), (20, 252))
        self.assertEqual((config.MIN_NAMES, config.MAX_NAMES), (5, 40))
        self.assertEqual((config.MIN_HOLD_CAP, config.MAX_HOLD_CAP), (5, 60))
        base = {"panel": "sp500", "rebalance": "weekly"}
        for key, low, high in (("history", 20, 252), ("max_names", 5, 40), ("max_hold_sessions", 5, 60),
                               ("weekday", 0, 4)):
            for value in (low, high):
                self.assertEqual(getattr(parse_needs({**base, key: value}), key), value)
            for value in (low - 1, high + 1):
                with self.subTest(key=key, value=value), self.assertRaises(NeedsRefused):
                    parse_needs({**base, key: value})

    def test_refusals(self):
        base = {"panel": "sp500", "rebalance": "weekly"}
        bad = [None, [], "sp500", {}, {"panel": "sp500"}, {"rebalance": "weekly"},
               {**base, "panel": "nasdaq100"}, {**base, "panel": ["sp500"]}, {**base, "panel": None},
               {**base, "rebalance": "daily"}, {**base, "rebalance": "Weekly"}, {**base, "rebalance": 5},
               {**base, "symbols": ["SPY"]}, {**base, "cadence": 5},
               {**base, "history": 2.5}, {**base, "history": True}, {**base, "history": "60"},
               {**base, "history": float("nan")}, {**base, "max_names": None},
               {"panel": "sp500", "rebalance": "monthly", "weekday": 3}]
        for raw in bad:
            with self.subTest(raw=raw), self.assertRaises(NeedsRefused):
                parse_needs(raw)
        self.assertIs(NeedsRefused, e1.NeedsRefused)
        self.assertTrue(issubclass(NeedsRefused, CodeRefused))
        self.assertTrue(issubclass(NeedsRefused, runtime.NeedsRefused))

    def test_a_daily_schedule_is_never_a_panel_programs(self):
        self.assertEqual(config.REBALANCE, ("weekly", "monthly"))
        with self.assertRaises(NeedsRefused) as caught:
            parse_needs({"panel": "sp500", "rebalance": "daily"})
        self.assertIn("never daily", str(caught.exception))


class Loading(unittest.TestCase):
    def test_load_binds_params_and_names_the_run(self):
        program = load_program(CODE, name="p")
        self.assertIsInstance(program, XsProgram)
        self.assertEqual(program.needs, Needs("sp500", 60, 6, "weekly", 2, 30))
        self.assertEqual(program.params, {"k": 5, "weight": 0.2})
        self.assertEqual(program.sha, hashlib.sha256(CODE.encode()).hexdigest())
        self.assertEqual(program.run_sha,
                         hashlib.sha256((program.sha + runtime.canonical(program.params)).encode()).hexdigest())
        other = load_program(CODE, name="p", params={"weight": 0.1})
        self.assertEqual(other.params, {"k": 5, "weight": 0.1})
        self.assertEqual(other.sha, program.sha)
        self.assertNotEqual(other.run_sha, program.run_sha)
        answer = other.start().decide(Ctx())
        self.assertEqual(set(answer["target"].values()), {0.1})

    def test_the_gyms_code_rules_apply_unchanged(self):
        for bad in ("import os\n" + CODE, CODE.replace("import numpy as np", "import datetime"),
                    CODE + "\nopen('x')\n", CODE.replace("def decide(ctx):", "def choose(ctx):"),
                    CODE.replace('PARAMS = {"k": 5, "weight": 0.2}', ""), "NEEDS = {\n", ""):
            with self.subTest(code=bad[:40]), self.assertRaises(CodeRefused):
                load_program(bad)

    def test_needs_and_params_refusals_are_e1s_classes(self):
        with self.assertRaises(NeedsRefused):
            load_program(CODE.replace('"rebalance": "weekly"', '"rebalance": "daily"'))
        with self.assertRaises(NeedsRefused):
            load_program(CODE.replace('"panel": "sp500", ', ""))
        with self.assertRaises(NeedsRefused):
            load_program(CODE, params={"unknown": 1})
        with self.assertRaises(CodeRefused):
            load_program(CODE + '\nPARAMS["k"] = 9\n')
        with self.assertRaises(CodeRefused):
            load_program(CODE + "\nraise ValueError('at load')\n")


class TheRunner(unittest.TestCase):
    def setUp(self):
        self.program = load_program(CODE, name="p")

    def test_a_target_comes_back_normalized(self):
        runner = self.program.start()
        self.assertIsInstance(runner, XsRunner)
        answer = runner.decide(Ctx())
        self.assertEqual(answer, {"target": {int(i): 0.2 for i in IDS[:5]}, "at": "close"})
        self.assertTrue(all(type(k) is int and type(v) is float for k, v in answer["target"].items()))
        self.assertFalse(runner.last_failed)
        self.assertEqual(runner.stats()["calls"], 1)

    def test_a_hold_and_none_are_holds_and_not_errors(self):
        runner = self.program.start()
        for mode in ("hold", "none"):
            self.assertEqual(runner.decide(Ctx(mode)), {"hold": True})
            self.assertFalse(runner.last_failed)
        self.assertEqual((runner.stats()["calls"], runner.stats()["errors"]), (2, 0))

    def test_the_modules_globals_are_the_runs_memory_and_a_start_is_fresh(self):
        runner = self.program.start()
        for _ in range(3):
            runner.decide(Ctx())
        self.assertEqual(runner._namespace["STATE"]["calls"], 3)
        self.assertEqual(self.program.start()._namespace["STATE"]["calls"], 0)

    def test_a_decide_that_raises_failed_and_is_a_hold(self):
        runner = self.program.start()
        self.assertEqual(runner.decide(Ctx("boom")), {"hold": True})
        self.assertTrue(runner.last_failed)
        stats = runner.stats()
        self.assertEqual((stats["calls"], stats["errors"], stats["timeouts"], stats["disqualified"]), (1, 1, 0, None))
        self.assertIn("ValueError: boom", stats["messages"][0])
        runner.decide(Ctx())
        self.assertFalse(runner.last_failed, "the flag is the LAST call's")

    def test_a_malformed_target_is_an_error_and_never_a_failed_decide(self):
        """D10: an invalid target is the program's error (counted, positions held); the House's exit rule counts
        failed decides, never these."""
        runner = self.program.start()
        self.assertEqual(runner.decide(Ctx("junk")), {"hold": True})
        self.assertFalse(runner.last_failed)
        stats = runner.stats()
        self.assertEqual((stats["calls"], stats["errors"]), (1, 1))
        self.assertIn("malformed answer", stats["messages"][0])
        self.assertEqual(runner.decide(Ctx("count")), {"hold": True}, "an answer with a key of its own is malformed")

    def test_a_decide_past_its_limit_failed(self):
        runner = self.program.start(timeout=0.05)
        self.assertEqual(runner.decide(Ctx("slow")), {"hold": True})
        self.assertTrue(runner.last_failed)
        stats = runner.stats()
        self.assertEqual((stats["timeouts"], stats["errors"]), (1, 1))

    def test_too_many_errors_disqualify_and_every_later_call_failed(self):
        runner = self.program.start(max_errors=3)
        for _ in range(3):
            runner.decide(Ctx("boom"))
        self.assertTrue(runner.disqualified)
        calls = runner.stats()["calls"]
        self.assertEqual(runner.decide(Ctx()), {"hold": True})
        self.assertTrue(runner.last_failed)
        self.assertEqual(runner.stats()["calls"], calls, "a disqualified runner is not called")
        self.assertEqual(sorted(runner.stats()), ["calls", "disqualified", "errors", "messages", "seconds", "timeouts"])

    def test_the_runs_budget_disqualifies(self):
        runner = self.program.start(budget_seconds=0.0)
        self.assertEqual(runner.decide(Ctx()), {"hold": True})
        self.assertTrue(runner.last_failed)
        self.assertIn("budget", runner.disqualified)


class TheTarget(unittest.TestCase):
    """D10 / the pre-registration's C2: a target is valid iff every id is in ctx.ids, every w is finite and 0 < w <=
    0.20 + 1e-9, sum w <= 1 + 1e-9, and it names 0 names or MIN_NAMES..max_names."""

    def good(self, n: int = 5, w: float = 0.2) -> dict:
        return {int(i): w for i in IDS[:n]}

    def malformed(self, raw, max_names: int = 10) -> str:
        said: list[str] = []
        self.assertEqual(normalize_target(raw, IDS, max_names, said.append), {"hold": True})
        self.assertEqual(len(said), 1, "a malformed answer is reported once")
        self.assertTrue(said[0].startswith("malformed answer: "))
        return said[0]

    def test_a_valid_target(self):
        said: list[str] = []
        self.assertEqual(normalize_target({"target": self.good(), "at": "close"}, IDS, 10, said.append),
                         {"target": self.good(), "at": "close"})
        self.assertEqual(normalize_target({"target": self.good(8, 0.125)}, IDS, 10, said.append),
                         {"target": self.good(8, 0.125), "at": "open"})
        self.assertEqual(said, [])
        self.assertEqual((AT, ANSWER_KEYS), (("open", "close"), ("target", "at", "hold")))

    def test_all_cash_and_the_holds(self):
        said: list[str] = []
        self.assertEqual(normalize_target({"target": {}, "at": "open"}, IDS, 10, said.append),
                         {"target": {}, "at": "open"})
        self.assertEqual(normalize_target({"hold": True}, IDS, 10, said.append), {"hold": True})
        self.assertEqual(normalize_target(None, IDS, 10, said.append), {"hold": True})
        self.assertEqual(said, [])

    def test_a_target_through_json_is_the_same_target(self):
        """The child answers JSON: a target's keys come back as strings and are read with int()."""
        answer = normalize_target({"target": self.good(), "at": "close"}, IDS, 10)
        back = json.loads(json.dumps(answer))
        self.assertTrue(all(isinstance(k, str) for k in back["target"]))
        self.assertEqual(normalize_target(back, IDS, 10), answer)

    def test_numpy_keys_and_weights(self):
        raw = {"target": {np.int32(i): np.float64(0.2) for i in IDS[:5]}, "at": "open"}
        answer = normalize_target(raw, IDS, 10)
        self.assertEqual(answer, {"target": self.good(), "at": "open"})
        self.assertTrue(all(type(k) is int and type(v) is float for k, v in answer["target"].items()))
        self.assertEqual(normalize_target({"target": {float(i): 0.2 for i in IDS[:5]}}, IDS, 10)["target"], self.good())

    def test_the_ids_come_back_ascending(self):
        raw = {"target": {int(i): 0.1 for i in IDS[:6][::-1]}}
        self.assertEqual(list(normalize_target(raw, IDS, 10)["target"]), sorted(int(i) for i in IDS[:6]))

    def test_a_weight_of_zero_is_the_ids_absence(self):
        raw = {"target": {**self.good(5), int(IDS[7]): 0.0, int(IDS[8]): 0}}
        self.assertEqual(normalize_target(raw, IDS, 5)["target"], self.good(5))
        self.assertEqual(normalize_target({"target": {int(i): 0.0 for i in IDS[:3]}}, IDS, 10)["target"], {})

    def test_every_id_is_in_the_ctx(self):
        why = self.malformed({"target": {**self.good(4), 999999: 0.2}})
        self.assertIn("not in ctx.ids", why)
        self.malformed({"target": {**self.good(5), 999999: 0.0}})          # even at weight zero
        self.malformed({"target": {**self.good(4), "ZQAA": 0.2}})
        self.malformed({"target": {**self.good(4), 7001.5: 0.2}})
        self.malformed({"target": {**self.good(4), True: 0.2}})
        self.malformed({"target": {**self.good(4), None: 0.2}})
        self.malformed({"target": {**self.good(5), str(int(IDS[0])): 0.1}}, 10)   # one slot named twice

    def test_the_weights(self):
        cap = config.MAX_WEIGHT
        edge = {**self.good(4, 0.19), int(IDS[9]): cap + WEIGHT_SLACK / 2}
        self.assertEqual(normalize_target({"target": edge}, IDS, 10)["target"], edge)
        self.assertIn("at most 0.20", self.malformed({"target": {**self.good(4, 0.1), int(IDS[9]): cap + 1e-6}}))
        self.assertIn("long only", self.malformed({"target": {**self.good(4), int(IDS[9]): -0.01}}))
        for value in (float("nan"), float("inf"), "0.2", None, True, [0.2]):
            with self.subTest(value=value):
                self.malformed({"target": {**self.good(4), int(IDS[9]): value}})

    def test_the_sum(self):
        full = {int(i): 0.2 for i in IDS[:5]}
        self.assertEqual(normalize_target({"target": full}, IDS, 10)["target"], full)
        nudged = {int(i): 0.2 + WEIGHT_SLACK / 10 for i in IDS[:5]}
        self.assertEqual(normalize_target({"target": nudged}, IDS, 10)["target"], nudged)
        over = {**{int(i): 0.2 for i in IDS[:5]}, int(IDS[5]): 0.01}
        self.assertIn("sum to at most 1", self.malformed({"target": over}))

    def test_the_count(self):
        self.assertIn("5 to 10 names", self.malformed({"target": self.good(4)}))
        self.malformed({"target": self.good(1)})
        self.assertEqual(len(normalize_target({"target": self.good(10, 0.1)}, IDS, 10)["target"]), 10)
        self.assertIn("5 to 10 names", self.malformed({"target": self.good(11, 0.05)}))
        self.assertEqual(len(normalize_target({"target": self.good(11, 0.05)}, IDS, 12)["target"]), 11)
        self.assertEqual(config.MIN_NAMES * config.MAX_WEIGHT, 1.0, "five names at the cap are a full sleeve")

    def test_the_answers_shape(self):
        for raw in ("hold", 5, [], [{"target": {}}], {"hold": False}, {"hold": 1}, {}, {"at": "open"},
                    {"hold": True, "at": "open"}, {"hold": True, "target": self.good()},
                    {"target": self.good(), "at": "noon"}, {"target": self.good(), "at": None},
                    {"target": self.good(), "tag": "x"}, {"target": [int(i) for i in IDS[:5]]},
                    {"target": {int(i): 0.001 for i in np.arange(200)}}):
            with self.subTest(raw=str(raw)[:50]):
                self.malformed(raw)

    def test_whatever_an_object_does_when_read_it_is_a_malformed_answer(self):
        class Bomb(dict):
            def items(self):
                raise RuntimeError("no")

        self.assertIn("RuntimeError", self.malformed({"target": Bomb(self.good())}))
        self.assertEqual(normalize_target({"target": Bomb(self.good())}, IDS, 10), {"hold": True})



class TheContractShownToAuthors(unittest.TestCase):
    """league/xs/XS.md: its example is a program the House loads, and its tables are the code's."""

    @classmethod
    def setUpClass(cls):
        text = (Path(__file__).resolve().parents[1] / "xs" / "XS.md").read_text(encoding="utf-8")
        cls.example = re.search(r"```python\n(.*?)```", text, re.S).group(1)
        cls.text = " ".join(text.split())

    def has(self, words: str) -> None:
        self.assertTrue(words in self.text, f"XS.md does not say {words!r}")

    def test_the_example_loads_and_answers_a_valid_target_on_a_real_ctx(self):
        from league.xs import ctx, store, synth

        program = load_program(self.example, name="xs-md-example")
        self.assertEqual(program.needs, Needs("sp500", 60, 8, "weekly", 0, 30))
        with tempfile.TemporaryDirectory() as tmp:
            root = synth.synthetic_panel(Path(tmp) / "equity-daily", n_assets=60, seed=3, start=dt.date(2023, 6, 1),
                                         end=dt.date(2025, 6, 30))
            bars = store.PanelStore(root).bars("validation", history=program.needs.history, run_key="example").bars
            runner = program.start()
            for t in (bars.first - 1, bars.first + 30, bars.first + 31):
                built = ctx.build(ctx.inputs_from_panel(bars, t, needs=program.needs, cash=1000.0, equity=1000.0,
                                                        budget=1000.0, params=program.params))
                answer = runner.decide(built)
                self.assertFalse(runner.last_failed)
                self.assertEqual(answer["at"], "open")
                self.assertEqual(len(answer["target"]), 8)
                self.assertTrue(set(answer["target"]) <= set(built.ids.tolist()))
                self.assertEqual(set(answer["target"].values()), {0.125})
            self.assertEqual(runner.stats()["errors"], 0, runner.stats()["messages"])
            few = ctx.build(ctx.inputs_from_panel(bars, 100, needs=program.needs, cash=0.0, equity=0.0, budget=0.0,
                                                  params=program.params))
            self.assertEqual((few.n, runner.decide(few)), (0, {"hold": True}))

    def test_it_names_every_slot_of_the_ctx_and_every_key_of_needs(self):
        from league.xs import ctx

        for slot in ctx.XsCtx.__slots__:
            self.has(f"`ctx.{slot}`")
        for field in ctx.FIELDS:
            self.has(f".{field}")
        for key in NEEDS_KEYS:
            self.has(f"| `{key}` |")
        for banned in ("ctx.symbols", "ctx.bars", "ctx.prices", "ctx.events", "ctx.caps", "dv_decile", "`ctx.close`",
                       "ctx.open", "ctx.high", "ctx.volume"):
            self.assertFalse(banned in self.text, f"XS.md names {banned}")

    def test_its_figures_are_the_codes(self):
        for figure in (f"{config.MIN_HISTORY}-{config.MAX_HISTORY}", f"{config.MIN_NAMES}-{config.MAX_NAMES}",
                       f"{config.MIN_HOLD_CAP}-{config.MAX_HOLD_CAP}", f"at most {config.MAX_WEIGHT:.2f}",
                       f"{config.MAX_BUYS} buys and {config.MAX_SELLS} sells", f"{config.DERIVE_SESSIONS} sessions",
                       f"{config.REL_VOLUME_SESSIONS} sessions", f"less {int(config.VANISH_HAIRCUT * 100)}%",
                       f"under {int(config.HS_FLOOR_BP)} basis points", f"{config.CTX_PLACES} decimals",
                       f"{config.BETA_PLACES} decimals", f"under ${config.MIN_NAME_USD}",
                       f"{ctx_min_valid()} traded sessions"):
            self.has(figure)


def ctx_min_valid() -> int:
    from league.xs import ctx

    return ctx.REL_VOLUME_MIN_VALID


if __name__ == "__main__":
    unittest.main()
