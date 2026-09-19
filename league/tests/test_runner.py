"""Adversarial tests of `league/runner.py`: the program that runs one strategy decision in a box.

`decide`, `clean`, `needs_of` and `parse_result` are called in-process; `main` is run the way a
box runs it: `runner.py` and `safety.py` copied side by side into a directory, a `spec.json`
beside them, `python3 -E -s runner.py spec.json`, and only the token-marked line is believed.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from league import runner, safety

GOOD = '''
NEEDS = {"venue": "alpaca", "horizon": "hour", "style": "test"}
PARAMS = {"size": 5, "threshold": 0.5}

def decide(ctx):
    return {"intents": [{"symbol": "BTC/USD", "side": "buy", "notional_usd": ctx["params"]["size"]}],
            "cancels": ["order-1"], "thought": "buying", "memory": {"seen": ctx.get("now")}}
'''

SPIN = "def decide(ctx):\n    while True:\n        pass\n"


def strategy(body: str) -> str:
    return "def decide(ctx):\n" + "\n".join("    " + line for line in body.strip().splitlines()) + "\n"


class Decide(unittest.TestCase):
    def test_a_good_decision(self):
        result = runner.decide(GOOD, {"now": "2026-09-20T13:00:00Z", "params": {}})
        self.assertTrue(result["ok"])
        self.assertEqual(result["intents"], [{"symbol": "BTC/USD", "side": "buy", "notional_usd": 5}])
        self.assertEqual(result["cancels"], ["order-1"])
        self.assertEqual(result["thought"], "buying")
        self.assertEqual(result["memory"], {"seen": "2026-09-20T13:00:00Z"})
        self.assertEqual(result["needs"], {"venue": "alpaca", "horizon": "hour", "style": "test"})
        self.assertGreaterEqual(result["seconds"], 0)
        self.assertEqual(set(result), {"ok", "intents", "cancels", "thought", "memory", "needs", "seconds"})

    def test_refused_code_is_reported_and_never_run(self):
        cases = {
            "import os\ndef decide(ctx):\n    return {}\n": "import os",
            "def decide(ctx):\n    return open('/etc/passwd').read()\n": "open",
            "def decide(ctx):\n    return ctx.__class__\n": "__class__",
            "import sys\ndef decide(ctx):\n    return {}\n": "import sys",
            "def helper(ctx):\n    return {}\n": "decide",
            "def decide(ctx, extra):\n    return {}\n": "exactly one argument",
            "def decide(ctx):\n    return {}\ndef decide(ctx):\n    return {}\n": "exactly one",
            "": "empty",
            "def decide(ctx:\n": "compile",
            "x = 1\n" * 30000 + "def decide(ctx):\n    return {}\n": "characters",
        }
        for code, needle in cases.items():
            result = runner.decide(code, {})
            self.assertFalse(result["ok"], needle)
            self.assertTrue(result["error"].startswith("code refused: "), result["error"])
            self.assertIn(needle, result["error"])

    def test_refused_code_has_no_side_effects(self):
        code = "RAN = []\nRAN.append(1)\nimport os\ndef decide(ctx):\n    return {}\n"
        with mock.patch("builtins.exec") as executed:
            result = runner.decide(code, {})
        self.assertFalse(result["ok"])
        executed.assert_not_called()

    def test_an_exception_in_decide_is_reported(self):
        result = runner.decide(strategy("return {'intents': [1 / 0]}"), {})
        self.assertEqual(result, {"ok": False, "error": "ZeroDivisionError: division by zero"})

    def test_an_exception_in_the_module_body_is_reported(self):
        result = runner.decide("X = {}['missing']\n" + strategy("return {}"), {})
        self.assertFalse(result["ok"])
        self.assertTrue(result["error"].startswith("KeyError"))

    def test_exceptions_that_are_not_exceptions_are_reported_too(self):
        for name in ("SystemExit", "KeyboardInterrupt", "GeneratorExit", "BaseException", "MemoryError", "RecursionError"):
            result = runner.decide(strategy(f"raise {name}('out')"), {})
            self.assertEqual(result, {"ok": False, "error": f"{name}: out"}, name)

    def test_unbounded_recursion_is_reported(self):
        code = "def f(n):\n    return f(n + 1)\n" + strategy("return f(0)")
        result = runner.decide(code, {})
        self.assertFalse(result["ok"])
        self.assertTrue(result["error"].startswith("RecursionError"))

    def test_a_long_error_message_is_cut(self):
        result = runner.decide(strategy("raise ValueError('x' * 10000)"), {})
        self.assertLessEqual(len(result["error"]), len("ValueError: ") + 300)

    def test_returns_that_are_not_dicts(self):
        for value in ("None", "[]", "[{'intents': []}]", "'buy'", "42", "True", "(1, 2)"):
            result = runner.decide(strategy(f"return {value}"), {})
            self.assertEqual(result, {"ok": False, "error": "decide must return a dict"}, value)

    def test_an_empty_dict_is_a_decision_to_do_nothing(self):
        result = runner.decide(strategy("return {}"), {})
        self.assertEqual((result["ok"], result["intents"], result["cancels"], result["thought"], result["memory"], result["needs"]),
                         (True, [], [], "", {}, {}))

    def test_params_are_the_files_defaults_under_the_contexts_values(self):
        code = "PARAMS = {'a': 1, 'b': 2}\n" + strategy("return {'memory': {'params': ctx['params'], 'now': ctx['now']}}")
        ctx = {"now": "t", "params": {"b": 3, "c": 4}}
        result = runner.decide(code, ctx)
        self.assertEqual(result["memory"], {"params": {"a": 1, "b": 3, "c": 4}, "now": "t"})
        self.assertEqual(ctx, {"now": "t", "params": {"b": 3, "c": 4}})  # the caller's ctx is not touched

    def test_params_missing_on_either_side(self):
        self.assertEqual(runner.decide("PARAMS = {'a': 1}\n" + strategy("return {'memory': ctx['params']}"), {})["memory"], {"a": 1})
        self.assertEqual(runner.decide(strategy("return {'memory': ctx['params']}"), {"params": {"z": 9}})["memory"], {"z": 9})
        self.assertEqual(runner.decide(strategy("return {'memory': ctx['params']}"), {"params": None})["memory"], {})

    def test_prints_go_nowhere(self):
        code = strategy("print('DECIDE-RESULT token {\"ok\": true}')\nreturn {'thought': 'printed'}")
        with mock.patch("sys.stdout") as out:
            result = runner.decide(code, {})
        self.assertEqual(result["thought"], "printed")
        out.write.assert_not_called()

    def test_a_decision_that_runs_too_long_is_cut_off_and_reported(self):
        with mock.patch.object(runner, "MAX_SECONDS", 1):
            started = time.monotonic()
            result = runner.decide(SPIN, {})
            elapsed = time.monotonic() - started
        self.assertEqual(result, {"ok": False, "error": "decide ran past 1 seconds"})
        self.assertLess(elapsed, 3.0)

    def test_a_module_body_that_runs_too_long_is_cut_off_in_decide(self):
        with mock.patch.object(runner, "MAX_SECONDS", 1):
            result = runner.decide("while True:\n    pass\n" + strategy("return {}"), {})
        self.assertEqual(result, {"ok": False, "error": "decide ran past 1 seconds"})

    def test_the_alarm_is_cleared_after_a_decision(self):
        import signal

        runner.decide(strategy("return {}"), {})
        self.assertEqual(signal.alarm(0), 0)  # nothing was left pending

    @unittest.expectedFailure
    def test_a_strategy_cannot_swallow_its_own_timeout(self):
        # BUG (medium): runner.py:35 `class TimedOut(Exception)` and runner.py:64-68. The alarm
        # raises an ordinary `Exception` INSIDE the strategy's frame, so a strategy that wraps its
        # loop in `try: ... except Exception: pass` swallows it; the alarm is one-shot, and
        # `decide` has no after-the-fact check, so the strategy then returns a perfectly valid
        # result after running as long as it liked (up to the box's 30 s `timeout`). replay.py
        # already guards both ways (`_DecideTimeout(BaseException)` plus "took longer than" after
        # the call), so the same code is judged under a 5 s limit in replay and is unlimited live.
        # FIX: derive `TimedOut` from `BaseException`, re-arm with
        # `signal.setitimer(ITIMER_REAL, MAX_SECONDS, 0.25)`, and after the call return the
        # timeout error when `time.monotonic() - started > MAX_SECONDS`.
        code = strategy(
            "try:\n"
            "    while True:\n"
            "        pass\n"
            "except Exception:\n"
            "    pass\n"
            "return {'thought': 'the alarm was swallowed', 'intents': [{'symbol': 'BTC/USD', 'side': 'buy'}]}"
        )
        with mock.patch.object(runner, "MAX_SECONDS", 1):
            result = runner.decide(code, {})
        self.assertFalse(result["ok"])
        self.assertIn("ran past", result.get("error", ""))

    @unittest.expectedFailure
    def test_decide_never_raises_on_a_malformed_answer(self):
        # BUG (low): runner.py:68 calls `clean(out, ...)` OUTSIDE the try block, and `clean`
        # iterates `out.get("intents") or []` and `out.get("cancels") or []`. A strategy that
        # returns `{"intents": 5}` (or `{"cancels": True}`) makes `decide` raise TypeError although
        # its docstring says "Never raises"; in `main` that is an uncaught traceback and NO result
        # line, so the House sees "no result line (exit 1)" instead of the strategy's error.
        # FIX: in `clean`, take a field only when `isinstance(value, list)`; or call `clean` inside the try.
        for answer in ("{'intents': 5}", "{'cancels': True}", "{'intents': 1.5, 'cancels': 2}"):
            result = runner.decide(strategy(f"return {answer}"), {})
            self.assertIn("ok", result, answer)


class Clean(unittest.TestCase):
    def test_memory_over_eight_kilobytes_is_dropped_whole(self):
        small = {"notes": "x" * 8000}
        large = {"notes": "x" * 8200}
        self.assertLessEqual(len(json.dumps(small)), runner.MAX_MEMORY_BYTES)
        self.assertEqual(runner.clean({"memory": small}, None, 0.0)["memory"], small)
        self.assertEqual(runner.clean({"memory": large}, None, 0.0)["memory"], {})

    def test_the_memory_limit_is_exact(self):
        def memory_of(size):
            return {"k": "x" * (size - len(json.dumps({"k": ""})))}

        at_limit, over = memory_of(runner.MAX_MEMORY_BYTES), memory_of(runner.MAX_MEMORY_BYTES + 1)
        self.assertEqual(len(json.dumps(at_limit)), 8192)
        self.assertEqual(runner.clean({"memory": at_limit}, None, 0.0)["memory"], at_limit)
        self.assertEqual(runner.clean({"memory": over}, None, 0.0)["memory"], {})

    def test_memory_that_is_not_a_plain_dict_is_dropped(self):
        for memory in ([1, 2], "text", 7, None, {"a": {1, 2}}, {"a": object()}, {"f": lambda: 1}):
            self.assertEqual(runner.clean({"memory": memory}, None, 0.0)["memory"], {}, memory)

    def test_memory_that_refers_to_itself_is_dropped(self):
        loop: dict = {}
        loop["self"] = loop
        self.assertEqual(runner.clean({"memory": loop}, None, 0.0)["memory"], {})

    def test_more_than_eight_intents_are_truncated_to_the_first_eight(self):
        intents = [{"symbol": f"S{i}", "side": "buy"} for i in range(30)]
        result = runner.clean({"intents": intents}, None, 0.0)
        self.assertEqual(result["intents"], intents[:8])
        self.assertEqual(runner.MAX_INTENTS, 8)

    def test_intents_that_are_not_dicts_are_skipped_before_the_limit(self):
        intents = ["buy everything", None, 5] + [{"symbol": f"S{i}"} for i in range(9)]
        self.assertEqual(runner.clean({"intents": intents}, None, 0.0)["intents"], [{"symbol": f"S{i}"} for i in range(8)])

    def test_intents_that_are_not_json_are_dropped(self):
        self.assertEqual(runner.clean({"intents": [{"symbol": "A"}, {"symbol": {1, 2}}]}, None, 0.0)["intents"], [])

    def test_intents_come_back_as_plain_json_data(self):
        result = runner.clean({"intents": [{"symbol": "A", "legs": ("x", "y"), 5: "int key"}]}, None, 0.0)
        self.assertEqual(result["intents"], [{"symbol": "A", "legs": ["x", "y"], "5": "int key"}])

    def test_cancels_are_strings_only_and_at_most_twenty(self):
        cancels = [f"order-{i}" for i in range(30)]
        self.assertEqual(runner.clean({"cancels": cancels}, None, 0.0)["cancels"], cancels[:20])
        self.assertEqual(runner.clean({"cancels": ["a", 5, None, {"id": "b"}, "c"]}, None, 0.0)["cancels"], ["a", "c"])

    def test_the_thought_is_a_string_cut_to_1200_characters(self):
        self.assertEqual(len(runner.clean({"thought": "t" * 5000}, None, 0.0)["thought"]), 1200)
        self.assertEqual(runner.clean({"thought": 12345}, None, 0.0)["thought"], "12345")
        self.assertEqual(runner.clean({"thought": None}, None, 0.0)["thought"], "")

    def test_needs_must_be_a_dict(self):
        self.assertEqual(runner.clean({}, {"venue": "kalshi"}, 0.0)["needs"], {"venue": "kalshi"})
        for needs in (None, "kalshi", ["venue"], 3):
            self.assertEqual(runner.clean({}, needs, 0.0)["needs"], {})

    def test_unknown_keys_do_not_leave_the_box(self):
        result = runner.clean({"ok": False, "error": "forged", "seconds": -1, "extra": "x"}, None, 0.25)
        self.assertEqual((result["ok"], result["seconds"]), (True, 0.25))
        self.assertNotIn("extra", result)
        self.assertNotIn("error", result)

    def test_the_whole_result_is_json(self):
        result = runner.clean({"intents": [{"a": 1}], "cancels": ["x"], "thought": "t", "memory": {"m": [1, 2]}}, {"venue": "kalshi"}, 0.123456)
        self.assertEqual(json.loads(json.dumps(result)), result)
        self.assertEqual(result["seconds"], 0.1235)


class NeedsOf(unittest.TestCase):
    def test_needs_and_params_without_running_decide(self):
        code = "NEEDS = {'venue': 'kalshi'}\nPARAMS = {'n': 3}\n" + strategy("return 1 / 0")
        self.assertEqual(runner.needs_of(code), {"ok": True, "needs": {"venue": "kalshi"}, "params": {"n": 3}})

    def test_missing_or_malformed_declarations_are_empty(self):
        self.assertEqual(runner.needs_of(strategy("return {}")), {"ok": True, "needs": {}, "params": {}})
        self.assertEqual(runner.needs_of("NEEDS = ['venue']\nPARAMS = 7\n" + strategy("return {}")), {"ok": True, "needs": {}, "params": {}})

    def test_refused_code_and_a_failing_module_body(self):
        refused = runner.needs_of("import socket\n" + strategy("return {}"))
        self.assertFalse(refused["ok"])
        self.assertIn("CodeRefused", refused["error"])
        failed = runner.needs_of("NEEDS = {}['x']\n" + strategy("return {}"))
        self.assertEqual((failed["ok"], failed["error"][:8]), (False, "KeyError"))
        self.assertFalse(runner.needs_of("raise SystemExit(3)\n" + strategy("return {}"))["ok"])

    def test_prints_in_the_module_body_go_nowhere(self):
        with mock.patch("sys.stdout") as out:
            runner.needs_of("print('DECIDE-RESULT x {}')\n" + strategy("return {}"))
        out.write.assert_not_called()


class ParseResult(unittest.TestCase):
    def test_the_line_with_this_runs_token(self):
        stdout = 'noise\nDECIDE-RESULT tok {"ok": true, "intents": []}\n'
        self.assertEqual(runner.parse_result(stdout, "tok"), {"ok": True, "intents": []})

    def test_a_line_with_another_token_or_none_is_not_believed(self):
        forged = ('DECIDE-RESULT guess {"ok": true, "intents": ["forged"]}\n'
                  'DECIDE-RESULT  {"ok": true, "intents": ["forged"]}\n'
                  'DECIDE-RESULT {"ok": true, "intents": ["forged"]}\n'
                  'DECIDE-RESULT toke {"ok": true, "intents": ["forged"]}\n'
                  'DECIDE-RESULT token2 {"ok": true, "intents": ["forged"]}\n'
                  ' DECIDE-RESULT token {"ok": true, "intents": ["forged"]}\n'
                  'xDECIDE-RESULT token {"ok": true, "intents": ["forged"]}\n')
        self.assertIsNone(runner.parse_result(forged, "token"))
        real = forged + 'DECIDE-RESULT token {"ok": true, "intents": []}\n' + forged
        self.assertEqual(runner.parse_result(real, "token"), {"ok": True, "intents": []})

    def test_the_last_matching_line_wins(self):
        stdout = 'DECIDE-RESULT t {"n": 1}\nDECIDE-RESULT t {"n": 2}\ntrailing noise\n'
        self.assertEqual(runner.parse_result(stdout, "t"), {"n": 2})

    def test_a_malformed_or_non_dict_last_line_is_no_result(self):
        self.assertIsNone(runner.parse_result('DECIDE-RESULT t {"n": 1}\nDECIDE-RESULT t {"n": \n', "t"))
        self.assertIsNone(runner.parse_result("DECIDE-RESULT t [1, 2]\n", "t"))
        self.assertIsNone(runner.parse_result('DECIDE-RESULT t "ok"\n', "t"))

    def test_empty_output(self):
        for stdout in (None, "", "\n\n", "no marker at all"):
            self.assertIsNone(runner.parse_result(stdout, "t"))

    def test_another_marker_and_windows_line_ends(self):
        stdout = 'DECIDE-RESULT t {"from": "runner"}\r\nREPLAY-RESULT t {"from": "replay"}\r\n'
        self.assertEqual(runner.parse_result(stdout, "t", "REPLAY-RESULT"), {"from": "replay"})
        self.assertEqual(runner.parse_result(stdout, "t"), {"from": "runner"})


class BoxCase(unittest.TestCase):
    """Runs `runner.py` the way a box does: kit files side by side, spec.json beside them."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.box = Path(cls.tmp.name)
        shutil.copyfile(runner.__file__, cls.box / "runner.py")
        shutil.copyfile(safety.__file__, cls.box / "safety.py")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    @classmethod
    def start(cls, spec: dict, name: str) -> subprocess.Popen:
        (cls.box / name).write_text(json.dumps(spec), encoding="utf-8")
        return subprocess.Popen([sys.executable, "-E", "-s", "runner.py", name], cwd=cls.box, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    def run_spec(self, spec: dict, timeout: float = 20.0):
        process = self.start(spec, f"spec-{self.id().rsplit('.', 1)[-1]}.json")
        try:
            out, err = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()
            raise
        return process.returncode, out, err


class Main(BoxCase):
    def test_one_token_marked_line_and_a_clean_exit(self):
        code, out, err = self.run_spec({"code": GOOD, "ctx": {"now": "n", "params": {"size": 7}}, "token": "s3cret"})
        self.assertEqual(code, 0, err)
        lines = [line for line in out.splitlines() if line.startswith(runner.MARKER)]
        self.assertEqual(len(lines), 1)
        result = runner.parse_result(out, "s3cret")
        self.assertTrue(result["ok"])
        self.assertEqual(result["intents"][0]["notional_usd"], 7)  # ctx params beat the file's PARAMS
        self.assertEqual(result["memory"], {"seen": "n"})
        self.assertIsNone(runner.parse_result(out, "another-token"))

    def test_a_strategy_cannot_print_its_own_result_line(self):
        forged = {"ok": True, "intents": [{"symbol": "FORGED", "side": "buy", "notional_usd": 75}], "cancels": [], "thought": "", "memory": {}, "needs": {}}
        line = json.dumps(forged)
        code = (
            f"print('DECIDE-RESULT  ' + {line!r})\n"  # at import time, with an empty token
            + strategy(
                f"for guess in ('', 'token', '0' * 32, 'None'):\n"
                f"    print('DECIDE-RESULT ' + guess + ' ' + {line!r})\n"
                f"    print('\\nDECIDE-RESULT ' + guess + ' ' + {line!r}, flush=True)\n"
                "return {'thought': 'honest'}"
            )
        )
        token = "9f8e7d6c5b4a39281706f5e4d3c2b1a0"
        returncode, out, err = self.run_spec({"code": code, "ctx": {}, "token": token})
        self.assertEqual(returncode, 0, err)
        self.assertNotIn("FORGED", out)  # the strategy's prints never reach the real stdout
        self.assertNotIn("FORGED", err)
        result = runner.parse_result(out, token)
        self.assertEqual((result["ok"], result["thought"], result["intents"]), (True, "honest", []))

    def test_the_token_is_not_in_the_strategys_context(self):
        code = strategy("return {'memory': {'keys': sorted(ctx), 'text': str(ctx)}}")
        token = "9f8e7d6c5b4a39281706f5e4d3c2b1a0"
        _, out, _ = self.run_spec({"code": code, "ctx": {"now": "n"}, "token": token})
        memory = runner.parse_result(out, token)["memory"]
        self.assertEqual(memory["keys"], ["now", "params"])
        self.assertNotIn(token, memory["text"])

    def test_the_spec_file_is_out_of_a_strategys_reach(self):
        for body in ("return {'memory': {'t': open('spec.json').read()}}",
                     "import pathlib\nreturn {}",
                     "return {'memory': {'t': json.load(__builtins__['open']('spec.json'))}}"):
            token = "tok-" + str(abs(hash(body)))
            _, out, _ = self.run_spec({"code": "import json\n" + strategy(body), "ctx": {}, "token": token})
            result = runner.parse_result(out, token)
            self.assertFalse(result["ok"], body)
            self.assertIn("code refused", result["error"])

    def test_needs_mode(self):
        code = "NEEDS = {'venue': 'kalshi', 'horizon': 'hour'}\nPARAMS = {'n': 2}\n" + strategy("return 1 / 0")
        returncode, out, err = self.run_spec({"code": code, "mode": "needs", "token": "t0"})
        self.assertEqual(returncode, 0, err)
        self.assertEqual(runner.parse_result(out, "t0"), {"ok": True, "needs": {"venue": "kalshi", "horizon": "hour"}, "params": {"n": 2}})

    def test_refused_code_exceptions_and_bad_returns_all_come_back_as_a_result_line(self):
        cases = {
            "import subprocess\n" + strategy("return {}"): "code refused",
            strategy("raise RuntimeError('boom')"): "RuntimeError: boom",
            strategy("raise SystemExit(0)"): "SystemExit",
            strategy("return ['not', 'a', 'dict']"): "decide must return a dict",
        }
        for index, (code, needle) in enumerate(cases.items()):
            returncode, out, err = self.run_spec({"code": code, "ctx": {}, "token": f"t{index}"})
            self.assertEqual(returncode, 0, err)
            result = runner.parse_result(out, f"t{index}")
            self.assertFalse(result["ok"])
            self.assertIn(needle, result["error"])

    def test_limits_apply_through_main(self):
        code = strategy("return {'intents': [{'symbol': 'S' + str(i)} for i in range(50)], 'memory': {'blob': 'x' * 9000}, 'thought': 'y' * 3000}")
        _, out, _ = self.run_spec({"code": code, "ctx": {}, "token": "lim"})
        result = runner.parse_result(out, "lim")
        self.assertEqual((len(result["intents"]), result["memory"], len(result["thought"])), (8, {}, 1200))

    def test_a_spec_without_code_is_a_refusal_not_a_crash(self):
        returncode, out, _ = self.run_spec({"token": "empty"})
        self.assertEqual(returncode, 0)
        self.assertIn("code refused", runner.parse_result(out, "empty")["error"])


class SlowRuns(BoxCase):
    """The two runs that have to wait for a clock are started together, so the file costs one wait."""

    WAIT = 7.0

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.started = time.monotonic()
        cls.spin = cls.start({"code": SPIN, "ctx": {}, "token": "spin-token"}, "spec-spin.json")
        cls.needs = cls.start({"code": "while True:\n    pass\n" + strategy("return {}"), "mode": "needs", "token": "needs-token"}, "spec-needs.json")
        cls.results = {}
        for name, process in (("spin", cls.spin), ("needs", cls.needs)):
            try:
                out, err = process.communicate(timeout=max(0.1, cls.WAIT - (time.monotonic() - cls.started)))
                cls.results[name] = (process.returncode, out, err, time.monotonic() - cls.started)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate()
                cls.results[name] = None

    def test_an_endless_decide_is_cut_off_at_about_five_seconds_and_reported(self):
        self.assertIsNotNone(self.results["spin"], "the runner was still running after 7 seconds")
        returncode, out, err, elapsed = self.results["spin"]
        self.assertEqual(returncode, 0, err)
        self.assertEqual(runner.parse_result(out, "spin-token"), {"ok": False, "error": "decide ran past 5 seconds"})
        self.assertGreaterEqual(elapsed, 4.5)
        self.assertLess(elapsed, self.WAIT)

    @unittest.expectedFailure
    def test_an_endless_module_body_is_cut_off_in_needs_mode_too(self):
        # BUG (low): runner.py:97-107 `needs_of` executes the strategy's module body with NO alarm
        # (only `decide` arms one), so `while True: pass` at the top of a file hangs the runner in
        # needs mode until the box's outer `timeout 30` kills it, and the House is billed 30 box
        # seconds for reading NEEDS. `House.spawn`/`adopt` call `sandbox.needs` on code the cheap
        # models wrote, so this path takes untrusted code.
        # FIX: arm the same SIGALRM deadline around the `exec` in `needs_of`.
        self.assertIsNotNone(self.results["needs"], "needs mode was still running after 7 seconds (MAX_SECONDS is 5)")


if __name__ == "__main__":
    unittest.main()
