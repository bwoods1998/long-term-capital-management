"""One program's failure is its own: a Gym batch runs on past a program that cannot load, one whose run the engine
cannot finish, and one that raises in decide, and returns for every other program exactly what it would have alone.

The Sept 30 14:03Z incident: one program of an eight-program Train batch parsed but did not compile (an assignment
expression in a comprehension's iterable, refused only at the compiler's symbol-table stage). The batch's load check
caught only `CodeRefused`, so the SyntaxError ended the batch (exit 1), the pool retried it, and all eight families got
"the Gym failed twice". Synthetic stores only; no program here is anyone's strategy."""

import datetime as dt
import shutil
import tempfile
import unittest
from unittest import mock

try:
    import numpy  # noqa: F401
    import pyarrow  # noqa: F401
    HAVE = True
except ImportError:  # pragma: no cover
    HAVE = False

if HAVE:
    from league.gym import batch as B
    from league.gym import engine as E
    from league.gym import runtime as R
    from league.gym import synth
    from league.gym.safety import CodeRefused, check_program

# Buys a one-lot call at the natural every seventh decision and closes it after 90 minutes: trades every day.
HEALTHY = '''
NEEDS = {"roots": ["SPY"], "dte": [0, 2], "band": 0.03, "cadence": CADENCE}
PARAMS = {"every": 7}
STATE = {"n": 0}
def decide(ctx):
    STATE["n"] += 1
    if STATE["n"] % ctx.params["every"] == 0 and not ctx.positions and not ctx.orders:
        return [{"open": "long_call", "legs": [{"side": "long", "right": "C", "dte": 1, "atm": 0}], "qty": 1}]
    return [{"close": p["id"]} for p in ctx.positions if p["held_minutes"] > 90]
'''
A = HEALTHY.replace("CADENCE", "30")
C = HEALTHY.replace("CADENCE", "15")
# The 14:03Z shape: parses, never compiles (the symbol table refuses a walrus in a comprehension's iterable).
NO_COMPILE = '''
NEEDS = {"roots": ["SPY"], "cadence": 30}
PARAMS = {}
def decide(ctx):
    picks = [i for i in range(n := 0)]
    return []
'''
# Raises inside its own decide on every call: the runner counts it and disqualifies it; no one else is touched.
RAISES_IN_DECIDE = '''
NEEDS = {"roots": ["SPY"], "cadence": 30}
PARAMS = {}
def decide(ctx):
    return [{"open": "long_call", "qty": 1 // 0}]
'''

VOLATILE = ("seconds",)


def stable(result):
    """A result without what a clock sets (the run's seconds, decide's seconds)."""
    out = {k: v for k, v in result.items() if k not in VOLATILE}
    if isinstance(out.get("runtime"), dict):
        out["runtime"] = {k: v for k, v in out["runtime"].items() if k != "decide_seconds"}
    return out


@unittest.skipUnless(HAVE, "numpy/pyarrow not installed (requirements-gym.txt)")
class BatchIsolation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix="gym-batch-iso-")
        cls.days = synth.weekdays(dt.date(2023, 5, 1), 4)
        synth.generate(cls.dir, roots=("SPY",), days=cls.days, strikes_each_side=6, max_dte=3, seed=5)
        cls._alone = {}

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def batch(self, jobs, **kw):
        kw.setdefault("workers", 1)
        return B.run_batch(jobs, store_root=self.dir, window="train", roots=["SPY"], **kw)

    def alone(self, name, code, split=1):
        """The program's result run by itself (cached per split)."""
        key = (name, split)
        if key not in self._alone:
            [self._alone[key]] = self.batch([(name, code, {})], split=split)["results"]
        return self._alone[key]

    def assert_healthy_as_alone(self, doc, names, split=1):
        by_name = {r["program"]: r for r in doc["results"]}
        for name, code in names:
            got, solo = by_name[name], self.alone(name, code, split)
            self.assertEqual(got["status"], "ok", got.get("reason"))
            self.assertGreater(got["summary"]["trades"], 0)
            self.assertEqual(got["result_sha"], solo["result_sha"], name)
            self.assertEqual(stable(got), stable(solo), name)

    # ------------------------------------------------------------------ at the check
    def test_code_that_parses_but_never_compiles_is_refused_at_the_check(self):
        with self.assertRaises(CodeRefused) as caught:
            check_program(NO_COMPILE)
        self.assertIn("line 5", str(caught.exception))
        self.assertIn("does not compile", str(caught.exception))
        with self.assertRaises(CodeRefused):  # the load refuses it too: never a SyntaxError out of load_program
            R.load_program(NO_COMPILE)
        # An expression nested past the compiler's stack raises RecursionError while compiling (tens of thousands deep:
        # simulated, not built, so no interpreter's own stack limit is at stake here): refused the same way.
        with mock.patch("league.gym.safety.compile", side_effect=RecursionError("during compilation"), create=True):
            with self.assertRaises(CodeRefused) as caught:
                check_program(A)
        self.assertIn("does not compile: RecursionError", str(caught.exception))
        check_program(A)  # a healthy program still passes

    # ------------------------------------------------------------------ the batch's load check
    def test_the_batch_runs_on_past_a_program_that_cannot_compile(self):
        jobs = [("a", A, {}), ("broken", NO_COMPILE, {}), ("c", C, {})]
        doc = self.batch(jobs)
        statuses = [r["status"] for r in doc["results"]]
        self.assertEqual(statuses, ["ok", "refused", "ok"])
        self.assertIn("does not compile", doc["results"][1]["reason"])
        self.assertEqual(doc["results"][1]["trials"], 0)
        self.assertEqual(doc["batch"]["trials"], 2)
        self.assert_healthy_as_alone(doc, [("a", A), ("c", C)])

    def test_the_same_in_worker_processes(self):
        jobs = [("a", A, {}), ("broken", NO_COMPILE, {}), ("c", C, {})]
        doc = self.batch(jobs, workers=2)
        self.assertEqual([r["status"] for r in doc["results"]], ["ok", "refused", "ok"])
        self.assert_healthy_as_alone(doc, [("a", A), ("c", C)])

    def test_a_load_failure_of_any_other_kind_is_that_programs_alone(self):
        real = R.load_program

        def load(code, *, name="program", params=None):
            if name == "odd":
                raise RuntimeError("an unforeseen load failure")
            return real(code, name=name, params=params)

        with mock.patch.object(R, "load_program", load):
            doc = self.batch([("a", A, {}), ("odd", A, {}), ("c", C, {})])
        odd = doc["results"][1]
        self.assertEqual((odd["status"], odd["trials"]), ("refused", 0))
        self.assertIn("RuntimeError: an unforeseen load failure", odd["reason"])
        self.assert_healthy_as_alone(doc, [("a", A), ("c", C)])

    def test_a_program_that_fails_to_load_in_its_worker_is_that_programs_alone(self):
        real, seen = R.load_program, []

        def load(code, *, name="program", params=None):
            seen.append(name)
            if name == "flaky" and seen.count("flaky") > 1:  # the parent's check passes it; the worker's load fails
                raise R.CodeRefused("the program's module body ran past 5 s")
            return real(code, name=name, params=params)

        with mock.patch.object(R, "load_program", load):
            doc = self.batch([("a", A, {}), ("flaky", A, {}), ("c", C, {})])
        flaky = doc["results"][1]
        self.assertEqual((flaky["status"], flaky["trials"]), ("error", 0))
        self.assertIn("failed to load in its worker", flaky["reason"])
        self.assert_healthy_as_alone(doc, [("a", A), ("c", C)])

    # ------------------------------------------------------------------ during the run
    def test_a_program_raising_in_decide_is_charged_to_itself(self):
        doc = self.batch([("a", A, {}), ("raiser", RAISES_IN_DECIDE, {}), ("c", C, {})])
        raiser = doc["results"][1]
        self.assertEqual(raiser["status"], "disqualified")
        self.assertTrue(any("ZeroDivisionError" in m for m in raiser["runtime"]["messages"]), raiser["runtime"])
        self.assert_healthy_as_alone(doc, [("a", A), ("c", C)])

    def fault(self, name, exc, after=40):
        """Account.step raising `exc` for program `name` from its `after`-th step: an exception out of the engine's
        handling of that one program (what no program's own code can raise past its runner)."""
        real, calls = E.Account.step, {"n": 0}

        def step(account, day, mi, decide):
            if account.program.name == name:
                calls["n"] += 1
                if calls["n"] > after:
                    raise exc
            return real(account, day, mi, decide)

        return mock.patch.object(E.Account, "step", step)

    def test_an_engine_fault_on_one_program_ends_its_run_alone(self):
        for split in (1, 2):
            with self.subTest(split=split):
                with self.fault("faulty", KeyError("injected engine fault")):
                    doc = self.batch([("a", A, {}), ("faulty", A, {}), ("c", C, {})], split=split)
                faulty = doc["results"][1]
                self.assertEqual((faulty["status"], faulty["trials"]), ("error", 0))
                self.assertIn("injected engine fault", faulty["reason"])
                self.assertEqual(doc["batch"]["trials"], 2)
                self.assert_healthy_as_alone(doc, [("a", A), ("c", C)], split=split)

    def test_a_program_that_cannot_start_in_the_engine_is_that_programs_alone(self):
        real = R.Program.start

        def start(program, **kw):
            if program.name == "slow":
                raise R.ProgramTimeout("decide ran past its time limit")
            return real(program, **kw)

        programs = [R.load_program(A, name="a"), R.load_program(A, name="slow"), R.load_program(C, name="c")]
        with mock.patch.object(R.Program, "start", start):
            results = E.run(programs, B_store(self.dir), E.RunConfig(window="train", roots=("SPY",)), isolate=True)
        self.assertEqual([r["status"] for r in results], ["ok", "error", "ok"])
        self.assertIn("failed to start", results[1]["reason"])
        alone = E.run([programs[0]], B_store(self.dir), E.RunConfig(window="train", roots=("SPY",)))
        self.assertEqual(results[0]["result_sha"], alone[0]["result_sha"])

    def test_a_memory_error_still_fails_the_whole_unit(self):
        # The worker's memory cap is the unit's (batch._cap_memory): a MemoryError is no one program's, as before.
        with self.fault("hog", MemoryError()):
            doc = self.batch([("a", A, {}), ("hog", A, {}), ("c", C, {})])
        self.assertEqual([r["status"] for r in doc["results"]], ["error", "error", "error"])
        self.assertTrue(all("MemoryError" in r["reason"] for r in doc["results"]))

    def test_without_isolate_the_engine_raises_as_before(self):
        programs = [R.load_program(A, name="a"), R.load_program(A, name="faulty")]
        with self.fault("faulty", KeyError("injected engine fault")):
            with self.assertRaises(KeyError):
                E.run(programs, B_store(self.dir), E.RunConfig(window="train", roots=("SPY",)))


def B_store(root):
    from league.gym.store import Store

    return Store(root)


if __name__ == "__main__":
    unittest.main()
