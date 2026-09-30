"""Executable parameter/state contract, including the ignored global-PARAMS ablation defect."""

import unittest
from types import SimpleNamespace

from league.gym.experiment import check_experiment
from league.gym.runtime import load_program, merge_params
from league.gym.safety import CodeRefused

BASE = "NEEDS = {'roots': ['SPY']}\nPARAMS = {'signal_on': 1, 'unused': 2, 'levels': [1, 2]}\n"


class Parameters(unittest.TestCase):
    def run_code(self, body, **params):
        program = load_program(BASE + body, params=params)
        runner = program.start()
        intents = runner.decide(SimpleNamespace(params=program.params))
        self.assertEqual(runner.errors, 0, runner.messages)
        return intents

    def test_global_param_ablation_turns_off_the_signal(self):
        code = "def decide(ctx):\n    return [{'cancel': 'signal'}] if PARAMS['signal_on'] else []\n"
        self.assertEqual(self.run_code(code), [{"cancel": "signal"}])
        self.assertEqual(self.run_code(code, signal_on=0), [])

    def test_aliases_scalar_captures_and_function_defaults_bind_before_execution(self):
        for setup, expression in (("p = PARAMS\nq = p\n", "q['signal_on']"),
                                  ("on = PARAMS['signal_on']\n", "on"),
                                  ("def on(p=PARAMS):\n    return p['signal_on']\n", "on()"),
                                  ("def on(p=PARAMS['signal_on']):\n    return p\n", "on()")):
            body = setup + "def decide(ctx):\n    return [{'cancel': 'signal'}] if " + expression + " else []\n"
            with self.subTest(expression=expression):
                self.assertEqual(self.run_code(body, signal_on=0), [])
                self.assertEqual(self.run_code(body, signal_on=1), [{"cancel": "signal"}])

    def test_ctx_and_global_params_have_the_same_initial_variant(self):
        self.assertEqual(self.run_code("def decide(ctx):\n    return [{'cancel': PARAMS['signal_on'] + ctx.params['signal_on']}]\n",
                                       signal_on=3), [{"cancel": 6}])

    def test_every_runner_has_independent_state_and_parameter_lists(self):
        code = BASE + "STATE = []\ndef decide(ctx):\n    STATE.append(1)\n    PARAMS['levels'].append(3)\n    return [{'cancel': len(STATE), 'note': str(PARAMS['levels'])}]\n"
        program = load_program(code, params={"levels": [7]})
        a, b = program.start(), program.start()
        self.assertEqual(a.decide(None), [{"cancel": 1, "note": "[7, 3]"}])
        self.assertEqual(a.decide(None), [{"cancel": 2, "note": "[7, 3, 3]"}])
        self.assertEqual(b.decide(None), [{"cancel": 1, "note": "[7, 3]"}])
        self.assertEqual(program.params["levels"], [7])
        self.assertEqual(program.start().decide(None), [{"cancel": 1, "note": "[7, 3]"}])

    def test_merge_does_not_share_mutable_values_with_the_caller(self):
        defaults, overrides = {"a": [1], "b": [2]}, {"a": [3]}
        merged = merge_params(defaults, overrides)
        merged["a"].append(4)
        merged["b"].append(5)
        self.assertEqual((defaults, overrides), ({"a": [1], "b": [2]}, {"a": [3]}))

    def test_rebinding_and_module_mutation_are_refused(self):
        for body in ("PARAMS = {'signal_on': 1}\ndef decide(ctx):\n    return []\n",
                     "def decide(ctx):\n    PARAMS = {}\n    return []\n",
                     "def helper(PARAMS):\n    return PARAMS\ndef decide(ctx):\n    return []\n",
                     "PARAMS['signal_on'] = 9\ndef decide(ctx):\n    return []\n",
                     "alias = PARAMS\nalias['levels'].append(9)\ndef decide(ctx):\n    return []\n"):
            with self.subTest(body=body), self.assertRaises(CodeRefused):
                load_program(BASE + body, params={"signal_on": 0})

    def test_annotated_and_computed_defaults_still_bind(self):
        code = "NEEDS = {'roots': ['SPY']}\nPARAMS: dict = dict(signal_on=1)\ndef decide(ctx):\n    return [{'cancel': PARAMS['signal_on']}]\n"
        self.assertEqual(load_program(code, params={"signal_on": 0}).start().decide(None), [{"cancel": 0}])


class FastExperimentChecks(unittest.TestCase):
    def check(self, body, **params):
        return check_experiment(BASE + body, params)

    def test_unused_changed_override_is_refused_without_running_code(self):
        code = "def decide(ctx):\n    return [{'cancel': ctx.params['signal_on']}]\n"
        with self.assertRaisesRegex(CodeRefused, "never read.*unused"):
            self.check(code, unused=3)
        self.assertEqual(self.check(code, signal_on=0)["changed"], ["signal_on"])
        # No module execution: this check cannot spend seconds in a hostile loop.
        self.assertEqual(self.check("while True:\n    pass\n" + code)["parameter_reads"], ["signal_on"])

    def test_global_alias_and_default_capture_reads_are_recognized(self):
        for body in ("p = PARAMS\nq = p\ndef decide(ctx):\n    return [{'cancel': q.get('signal_on')}]\n",
                     "on = PARAMS['signal_on']\ndef decide(ctx):\n    return [{'cancel': on}]\n",
                     "def helper(p=PARAMS):\n    return p['signal_on']\ndef decide(ctx):\n    return [{'cancel': helper()}]\n"):
            with self.subTest(body=body):
                self.assertEqual(self.check(body, signal_on=0)["parameter_reads"], ["signal_on"])
                with self.assertRaisesRegex(CodeRefused, "never read.*unused"):
                    self.check(body, unused=3)

    def test_dynamic_and_escaped_parameter_reads_are_inconclusive(self):
        for body in ("def decide(ctx):\n    key = 'signal_on'\n    return [{'cancel': ctx.params[key]}]\n",
                     "def decide(ctx):\n    p = dict(ctx.params)\n    return [{'cancel': p['unused']}]\n",
                     "def decide(ctx):\n    p = getattr(ctx, 'params')\n    return [{'cancel': p['unused']}]\n",
                     "def helper(p):\n    return p['unused']\ndef decide(ctx):\n    return [{'cancel': helper(PARAMS)}]\n"):
            with self.subTest(body=body):
                self.assertIsNone(self.check(body, unused=3)["parameter_reads"])

    def test_zero_activity_and_explicit_defaults_are_not_refused(self):
        self.assertEqual(self.check("def decide(ctx):\n    return []\n")["changed"], [])
        self.assertEqual(self.check("def decide(ctx):\n    return []\n", unused=2)["changed"], [])
        # Static use is not a claim that the decision changes; rare and conditional signals are legitimate.
        self.assertEqual(self.check("def decide(ctx):\n    if ctx.minute < 0:\n        return [{'cancel': PARAMS['signal_on']}]\n    return []\n",
                                    signal_on=0)["changed"], ["signal_on"])

    def test_invalid_types_keys_and_ambiguous_bindings_fail_before_replay(self):
        for params in ({"unknown": 1}, {"signal_on": True}, {"signal_on": float("nan")}):
            with self.subTest(params=params), self.assertRaises(CodeRefused):
                self.check("def decide(ctx):\n    return []\n", **params)
        with self.assertRaises(CodeRefused):
            check_experiment("NEEDS = {'roots': ['SPY']}\nPARAMS = alias = {}\ndef decide(ctx):\n    return []\n")
        with self.assertRaisesRegex(CodeRefused, "roots"):
            check_experiment("NEEDS = {}\nPARAMS = {}\ndef decide(ctx):\n    return []\n")


if __name__ == "__main__":
    unittest.main()
