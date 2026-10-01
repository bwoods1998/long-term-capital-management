"""The evaluator benchmark suite: pinned cases, the static contract's answers, variant judging, the report's own
arithmetic (aggregate, headline, compare, receipt, exit codes) and the fast probes.

The full suite (eight worlds through every stage) runs from the CLI, not here: these tests check its parts on one
validation-only world and on fabricated rows so CI stays fast. Synthetic stores only.
"""

import json
import random
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from league.gym.experiment import check_experiment
from league.gym.safety import CodeRefused
from league.swarm import evaluator_benchmarks as EB

try:
    import numpy  # noqa: F401
    import pyarrow  # noqa: F401
    HAVE = True
except ImportError:  # pragma: no cover
    HAVE = False

#: Probes the static check refuses today. The check may come to refuse more (release B's numpy fix refuses the memo
#: probe), never fewer: a test of containment, not equality.
REFUSED = {"leak_array_base", "leak_private_attr", "leak_date_literal"}
#: The smallest set of names that, added to NUMPY_BANNED, closes everything the reach walk finds on numpy 2.4 and 2.5
#: (EVALUATOR_1's recommendation): the two dicts, np.polynomial (36 arrays and a setter), np.dtypes' registry, np.matlib
#: (rand and randn draw from numpy.random's shared generator) and np.matrixlib (its defmatrix module hands out
#: numpy._core.numeric: 14 writable registries, sctypeDict again as `typeDict`, three setters and standard-library
#: modules outside the import allowlist).
SMALLEST_DENYLIST = frozenset({"typecodes", "sctypeDict", "polynomial", "register_dlpack_dtype", "matlib", "matrixlib"})


def eval_path(path):
    """The object a walk path names (`np.` and `math.` paths only), read the way a program reads it."""
    import math

    import numpy as np

    return eval(path, {"np": np, "math": math})  # noqa: S307 - the walk's own paths, in a test


class PinnedDefinition(unittest.TestCase):
    def test_the_pin_is_the_suites_hash(self):
        # A change to any case, template, world setting, variant or line of the suite's code moves the hash: bump
        # SUITE_ID and re-pin deliberately, never quietly.
        self.assertEqual(EB.source_pin(), EB.suite_fingerprint())
        self.assertEqual(EB.PINNED_SUITE_SHA, EB.source_pin())

    def test_every_case_has_a_known_answer(self):
        ids = [c["id"] for c in EB.CASES]
        self.assertEqual(len(ids), len(set(ids)))
        kinds = {c["kind"] for c in EB.CASES}
        self.assertEqual(kinds, {"negative", "positive", "smoke", "proof", "ablation"})
        for case in EB.CASES:
            if case.get("finding"):
                self.assertIn(case["finding"]["code_excerpt"], EB.render(case, _tiny_world()), case["id"])

    def test_worlds_are_deterministic_and_independent(self):
        self.assertEqual(EB.truth(3), EB.truth(3))
        self.assertNotEqual(EB.truth(3)["days"][10]["seed"], EB.truth(4)["days"][10]["seed"])
        windows = EB.sessions()
        self.assertGreaterEqual(min(len(windows["train"]) // 3, len(windows["validation"])), 60)

    def test_cohorts_are_independent_and_development_keeps_its_streams(self):
        # Development's streams are the suite's first ones (EVALUATOR_1); confirmation's never repeat them.
        self.assertEqual(EB._seed("development", "world", 0), EB.digest([EB.SUITE_ID, "world", 0]))
        self.assertNotEqual(EB.truth(0)["days"][10]["seed"], EB.truth(0, "confirmation")["days"][10]["seed"])
        dev = EB.search_outcomes("noise_low_search", 0, 0, [2025])
        conf = EB.search_outcomes("noise_low_search", 0, 0, [2025], cohort="confirmation")
        self.assertEqual(len(dev["trades"]), len(conf["trades"]))
        self.assertNotEqual([t["pnl"] for t in dev["trades"]], [t["pnl"] for t in conf["trades"]])
        with self.assertRaises(ValueError):
            EB.truth(0, "holdout")

    def test_the_vendored_bound_is_the_exact_clopper_pearson_bound(self):
        # Checked against the binomial definition, never against the scored tree's `league.stats` (the suite vendors
        # the bound so a tree can change its own without moving the suite or failing here).
        import math

        for n in (1, 8, 40, 136, 512):
            for k in sorted({0, 1, n // 3, n - 1, n}):
                upper = EB.exact_upper(k, n, 0.025)
                if k >= n:
                    self.assertEqual(upper, 1.0)
                    continue
                cdf = sum(math.comb(n, i) * upper ** i * (1.0 - upper) ** (n - i) for i in range(k + 1))
                self.assertAlmostEqual(cdf, 0.025, places=9, msg=(k, n))
        self.assertAlmostEqual(EB.exact_upper(0, 136, 0.025), 1.0 - 0.025 ** (1.0 / 136), places=12)

    @unittest.skipUnless(HAVE, "numpy/pyarrow not installed (requirements-gym.txt)")
    def test_the_vendored_normal_is_within_the_approximations_error_of_the_true_one(self):
        # Abramowitz and Stegun 26.2.17 is good to 7.5e-8: checked against math.erf, not against the tree's greeks,
        # which may change (an erf-based CDF, say) without touching the pinned suite.
        import math

        import numpy as np

        x = np.linspace(-8.0, 8.0, 2001)
        exact = np.array([0.5 * (1.0 + math.erf(v / math.sqrt(2.0))) for v in x])
        self.assertLess(float(np.max(np.abs(EB.norm_cdf(x) - exact))), 1e-7)
        self.assertAlmostEqual(float(EB.norm_cdf(0.0)), 0.5, places=7)


class StaticContract(unittest.TestCase):
    def test_the_static_check_refuses_what_it_can_see_and_never_a_control(self):
        world = _tiny_world()
        refused = set()
        for case in (c for c in EB.CASES if c["kind"] in EB.PIPELINE_KINDS):
            try:
                check_experiment(EB.render(case, world), {})
            except CodeRefused:
                refused.add(case["id"])
        self.assertLessEqual(REFUSED, refused)
        controls = {c["id"] for c in EB.CASES if c["family"] == "signal" or c.get("review_dependent")}
        self.assertFalse(refused & controls, "a signal control or a memorized table must reach the pipeline")

    def test_the_static_contract_sees_one_of_three_broken_switches(self):
        refused = {}
        for case in (c for c in EB.CASES if c["kind"] == "ablation"):
            try:
                check_experiment(EB.render(case), {"signal_on": 0})
                refused[case["id"]] = False
            except CodeRefused:
                refused[case["id"]] = True
        self.assertEqual({k for k, v in refused.items() if v}, {"ablation_shadow_config"})


class Variants(unittest.TestCase):
    def row(self, trades_per_year, validation_trades):
        years = {str(y): {"trades": trades_per_year, "days_traded": trades_per_year, "pnl": 10.0, "t_daily": 2.0}
                 for y in (2022, 2023, 2024)}
        checks = {"status_ok": True, "trades": validation_trades >= 50, "days": validation_trades >= 25, "mean_positive": True,
                  "t": True, "dsr": True, "quarters": True, "stress": True}
        return {"stages": {"static": True, "train_eligible": trades_per_year >= 40, "train_stress": True, "drift": True,
                           "validation": all(checks.values()), "review": True, "holdout": True},
                "train": {"status": "ok", "years": years, "quarters": "12/12", "trades": 3 * trades_per_year,
                          "days_traded": 3 * trades_per_year, "t_daily": 3.0, "pnl": 30.0},
                "validation": {"checks": checks, "numbers": {"trades": validation_trades, "days": validation_trades}}}

    def test_floors_are_the_only_difference_between_current_and_sparse_floors(self):
        sparse, dense = self.row(12, 12), self.row(60, 60)
        self.assertFalse(EB.variant_verdict(sparse, EB.VARIANTS["current"]))
        self.assertTrue(EB.variant_verdict(sparse, EB.VARIANTS["sparse_floors"]))
        self.assertTrue(EB.variant_verdict(dense, EB.VARIANTS["current"]))
        failing = self.row(12, 12)
        failing["validation"]["checks"]["t"] = False
        self.assertFalse(EB.variant_verdict(failing, EB.VARIANTS["no_floors"]))  # t >= 2 never loosens

    def test_the_current_variant_reproduces_the_pipelines_verdict(self):
        for row in (self.row(12, 12), self.row(45, 45), self.row(60, 60)):
            self.assertEqual(EB.variant_verdict(row, EB.VARIANTS["current"]), all(row["stages"].values()))

    def test_search_lineage_is_deterministic_and_uses_the_real_lines(self):
        first = EB.search_trial("signal_sparse", 0)
        self.assertEqual(first, EB.search_trial("signal_sparse", 0))
        self.assertEqual(first["current"]["candidates"], 0)  # 12 trades a year: never Train-eligible today
        self.assertEqual(set(first), set(EB.VARIANTS))


@unittest.skipUnless(HAVE, "numpy/pyarrow not installed (requirements-gym.txt)")
class OneWorld(unittest.TestCase):
    """The validation window of one world: the planted signal is real, the invalid fills are not, STATE resets."""

    @classmethod
    def setUpClass(cls):
        from league.gym.store import Store

        cls.dir = Path(tempfile.mkdtemp(prefix="evaluator-suite-test-"))
        world = EB.truth(0)
        cls.world = {**world, **EB.write_world(cls.dir, world, windows=("validation",))}
        cls.store = Store(cls.dir)

    @classmethod
    def tearDownClass(cls):
        EB.clear_numpy_marks()
        shutil.rmtree(cls.dir, ignore_errors=True)

    def load(self, case_id, params=None):
        from league.gym.runtime import load_program

        case = next(c for c in EB.CASES if c["id"] == case_id)
        return load_program(EB.render(case, self.world), name=case_id, params=params or {})

    def test_planted_moves_follow_the_tells_and_the_absent_channel_is_noise(self):
        rows = [(r, m) for r, m in zip(self.world["days"], self.world["moves"]) if m and r["window"] != "history"]
        dense = sum(m["dense"] * r["tells"][EB.CHANNELS["dense"]["k"]] for r, m in rows) / len(rows)
        absent = sum(m["absent"] * r["tells"][EB.CHANNELS["absent"]["k"]] for r, m in rows) / len(rows)
        self.assertGreater(dense, 0.4)
        self.assertLess(abs(absent), 0.3)

    def test_no_invalid_fill_is_ever_made(self):
        names = ("fill_close_above_width", "fill_open_below_zero", "fill_crossed_quotes", "fill_stale_quote")
        results = EB.run([self.load(n) for n in names], self.store, "validation")
        for name, result in zip(names, results):
            self.assertEqual(result["status"], "ok", name)
            self.assertGreater(result["summary"]["trades"], 40, name)  # the probes do trade: the market is there
            self.assertLess(result["summary"]["pnl"], 0.0, name)
            self.assertEqual(EB.impossible_fills(name, result), 0, name)
        for t in results[0]["trades"] + results[1]["trades"]:  # a 1-wide debit vertical trades inside [0, 1]
            self.assertGreater(t["entry"], 0.0)
            self.assertLessEqual(t["entry"], 1.0)
            self.assertLessEqual(t["exit"], 1.0)

    def test_a_memorized_session_list_recognizes_its_window_and_trades_on_memory(self):
        # The review-dependent probe the level-invariance probe cannot see: it must really carry its memory, or its
        # promotion in the suite would say nothing about the review's load.
        [result] = EB.run([self.load("leak_memorized_sessions")], self.store, "validation")
        rate = EB.hit_rate(result, self.world)
        self.assertGreater(rate["trades"], 50)
        self.assertGreater(rate["rate"], 0.95)

    def test_the_refused_leak_probes_would_profit_if_the_static_check_let_them_through(self):
        # The suite opens the static check for the probes it refused (in-process, for their loads only): the greek-cache
        # and date-table probes must then read the absent window's future, or their refusal would say nothing. The
        # array-base probe has a second guard (the engine's copy: an array's base is a bytes copy of today so far), so
        # it reads bytes, not prices, and learns nothing even opened.
        from league.gym import runtime

        names = ("leak_private_attr", "leak_date_literal", "leak_array_base")
        closed = runtime.check_program
        opened = EB.opened_routes(self.store, self.world,
                                  {n: EB.render(next(c for c in EB.CASES if c["id"] == n), self.world) for n in names})
        self.assertIs(runtime.check_program, closed)  # the check is closed again
        for name in names[:2]:
            self.assertTrue(opened[name]["loaded"] and opened[name]["status"] == "ok", opened[name])
            self.assertGreater(opened[name]["trades"], 50, name)
            self.assertGreater(opened[name]["rate"], 0.9, name)
            self.assertGreater(opened[name]["pnl"], 0.0, name)
        self.assertEqual(opened["leak_array_base"]["status"], "ok")
        self.assertGreater(opened["leak_array_base"]["trades"], 50)
        self.assertLess(opened["leak_array_base"]["rate"], 0.7)  # a coin's hit rate: no information
        for name in names:  # and closed, each is refused
            with self.assertRaises(CodeRefused):
                self.load(name)

    def test_the_walk_reads_the_names_no_dir_lists(self):
        # np.matrixlib is in numpy's dict but hidden by its __dir__; np.matlib resolves only in its module __getattr__
        # (and is in numpy's dict only once something has read it). The walk reads both, as a program can.
        import numpy as np

        self.assertNotIn("matlib", dir(np))
        self.assertNotIn("matrixlib", dir(np))
        self.assertTrue({"matlib", "matrixlib", "linalg", "polynomial"} <= EB._module_names(np))

        # any module __getattr__: the names it compares against, and the keys of a module container it reads
        module = type(np)("ltcm_bench_lazy")
        exec("CHOICES = {'third': 1}\n"  # noqa: S102 - a fabricated module, in a test
             "def __getattr__(name):\n"
             "    if name in ('hidden', 'other') or name in CHOICES:\n"
             "        return 1\n"
             "    raise AttributeError(name)\n", vars(module))
        self.assertTrue({"hidden", "other", "third"} <= EB._module_names(module))
        self.assertNotIn("hidden", dir(module))
        # a shared generator: np.matlib.rand reads np.random; numpy.random's own callables and bound methods count too
        generators = EB.REACH["shared_generators"]
        self.assertTrue(EB._draws(np.matlib.rand, generators))
        self.assertTrue(EB._draws(np.matlib.randn, generators))
        self.assertTrue(EB._draws(np.random.rand, generators))
        self.assertTrue(EB._draws(np.random.default_rng, generators))
        self.assertFalse(EB._draws(np.mean, generators))
        self.assertFalse(EB._draws(np.matlib.zeros, generators))
        self.assertFalse(EB._draws(np.polynomial.Polynomial, generators))

    def test_the_walk_finds_every_writable_object_a_program_reaches(self):
        # numpy 2.4 and 2.5 (the CI's two) both expose the two dicts, np.polynomial's 36 module and class arrays and 14
        # registries of numpy's core through np.matrixlib (its defmatrix module binds numpy._core.numeric as `N`); the
        # walk must find them through the lazily imported submodules, the hidden names and the classes, find np.matlib's
        # two draws from the shared generator, and refuse every attribute write.
        import numpy as np
        from league.gym.safety import check_program

        walk = EB.numpy_walk()
        polynomial = [p for p in walk["writable"] if p.startswith("np.polynomial.")]
        internal = [p for p in walk["writable"] if p.removeprefix("list(").startswith("np.matrixlib.")]
        self.assertTrue({"np.typecodes", "np.sctypeDict"} <= set(walk["writable"]), walk["writable"])
        self.assertEqual(len(polynomial), 36, polynomial)
        self.assertEqual(len(internal), 14, internal)
        self.assertEqual(len(walk["writable"]), 2 + 36 + 14, walk["writable"])
        self.assertIn("np.polynomial.polynomial.polyx", polynomial)
        self.assertIn("np.polynomial.Polynomial.domain", polynomial)
        self.assertIn("np.matrixlib.defmatrix.N.numerictypes.sctypes", internal)
        self.assertIn("np.matrixlib.defmatrix.N.overrides.ARRAY_FUNCTIONS", internal)
        self.assertIn("np.polynomial.set_default_printstyle", walk["setters"])
        self.assertIn("np.matrixlib.defmatrix.set_module", walk["setters"])
        self.assertIn("np.matrixlib.defmatrix.N.multiarray.set_typeDict", walk["setters"])
        if hasattr(np.dtypes, "register_dlpack_dtype"):  # numpy 2.5
            self.assertIn("np.dtypes.register_dlpack_dtype", walk["setters"])
        self.assertEqual(len(walk["setters"]), len(set(map(id, (eval_path(p) for p in walk["setters"])))))  # one per callable
        self.assertEqual(walk["draws"], ["np.matlib.rand", "np.matlib.randn"])
        self.assertIn("np.seterr", walk["refused_containers"])  # a banned setter is seen, and refused
        self.assertEqual(walk["foreign_modules"]["functools"], "np.polynomial.polyutils.functools")
        self.assertEqual(walk["foreign_modules"]["ast"], "np.matrixlib.defmatrix.ast")
        self.assertTrue(all(path.startswith("np.matrixlib.") for name, path in walk["foreign_modules"].items()
                            if name != "functools"), walk["foreign_modules"])
        self.assertEqual(walk["attribute_writes"], [])
        self.assertTrue(walk["walk"]["complete"])
        for target in walk["_targets"]:  # every exact write test is admitted by the check (else it would prove nothing)
            write, read = EB._write_test(target["path"], target["obj"])
            check_program(EB.reach_program(body=f"{write}\nseen = {read}"))

    def test_the_numpy_proofs_hold_only_when_every_object_is_closed(self):
        # A partial fix (refusing np.typecodes only) leaves the sctypeDict, polynomial and draws proofs and the reach proof
        # failing; refusing both dicts (round 2's 'whole fix') leaves np.polynomial, np.matrixlib and np.matlib open;
        # round 3's four names (the dicts, polynomial, register_dlpack_dtype) still leave np.matrixlib's 14 registries
        # and np.matlib's draws; only SMALLEST_DENYLIST makes every numpy proof hold. The check is patched in-process only.
        import numpy as np
        from league.gym import safety

        def proofs_with(banned):
            with mock.patch.object(safety, "NUMPY_BANNED", safety.NUMPY_BANNED | banned), \
                    mock.patch.object(EB, "split_proof", lambda root: {"held": True, "claim": "stubbed (no Train here)"}):
                return EB.proofs(self.store, self.dir)

        def rooted(paths, root):
            return [p for p in paths if p.removeprefix("list(").startswith(root)]

        numpy_proofs = [c["id"] for c in EB.CASES if c["id"].startswith("state_numpy_")]
        self.assertIn("state_numpy_draws", numpy_proofs)
        EB.numpy_walk()  # first, the imports a program's reads make (each adds its functions to ARRAY_FUNCTIONS)
        pristine = (np.polynomial.polynomial.polyx.copy(), np.polynomial.Polynomial.domain.copy(), dict(np.typecodes),
                    set(np.matrixlib.defmatrix.N.overrides.ARRAY_FUNCTIONS))
        partial = proofs_with(frozenset({"typecodes"}))
        self.assertTrue(partial["state_numpy_runs"]["held"] and partial["state_numpy_batchmates"]["held"])
        self.assertIn("refused", partial["state_numpy_runs"])
        for name in ("state_numpy_runs_sctypedict", "state_numpy_runs_polynomial"):
            self.assertFalse(partial[name]["held"], name)
            self.assertGreater(partial[name]["trades"][0], 50, name)
            self.assertEqual(partial[name]["trades"][1], 0, name)
        self.assertFalse(partial["state_numpy_batchmates_sctypedict"]["held"])
        self.assertFalse(partial["state_numpy_batchmates_polynomial"]["held"])
        # the shared generator: the same program on the same days trades every session both times, on different sides
        self.assertFalse(partial["state_numpy_draws"]["held"])
        self.assertEqual(partial["state_numpy_draws"]["trades"][0], partial["state_numpy_draws"]["trades"][1])
        self.assertGreater(partial["state_numpy_draws"]["trades"][0], 50)
        reach = partial["state_numpy_reachable"]
        self.assertFalse(reach["held"])
        self.assertIn("np.sctypeDict", reach["reachable"])
        self.assertNotIn("np.typecodes", reach["reachable"])
        self.assertIn("np.typecodes", reach["refused_containers"])
        self.assertEqual(reach["channels"], {"runs": True, "batchmates": True})

        dicts = proofs_with(frozenset({"typecodes", "sctypeDict"}))
        for name in ("state_numpy_runs", "state_numpy_batchmates", "state_numpy_runs_sctypedict",
                     "state_numpy_batchmates_sctypedict"):
            self.assertTrue(dicts[name]["held"], name)
        self.assertFalse(dicts["state_numpy_runs_polynomial"]["held"])
        self.assertEqual(dicts["state_numpy_runs_polynomial"]["trades"][1], 0)
        self.assertFalse(dicts["state_numpy_batchmates_polynomial"]["held"])
        self.assertFalse(dicts["state_numpy_draws"]["held"])
        reach = dicts["state_numpy_reachable"]
        self.assertFalse(reach["held"])
        # np.matrixlib's 14, plus sctypeDict itself under another name: numerictypes binds it as `typeDict` too, so
        # refusing a name does not refuse the object
        alias = "np.matrixlib.defmatrix.N.numerictypes.typeDict"
        self.assertIn(alias, reach["reachable"])
        self.assertIs(eval_path(alias), np.sctypeDict)
        self.assertEqual(len(rooted(reach["reachable"], "np.polynomial.")), 36, reach["reachable"])
        self.assertEqual(len(rooted(reach["reachable"], "np.matrixlib.")), 15, reach["reachable"])
        self.assertEqual(len(reach["reachable"]), 51, reach["reachable"])
        self.assertIn("np.polynomial.set_default_printstyle", reach["setters"])

        four = proofs_with(frozenset({"typecodes", "sctypeDict", "polynomial", "register_dlpack_dtype"}))
        for name in numpy_proofs:
            self.assertEqual(four[name]["held"], name not in ("state_numpy_draws", "state_numpy_reachable"), name)
        reach = four["state_numpy_reachable"]
        self.assertEqual(len(reach["reachable"]), 15, reach["reachable"])
        self.assertIn(alias, reach["reachable"])
        self.assertEqual(rooted(reach["reachable"], "np.matrixlib."), reach["reachable"])
        self.assertEqual(rooted(reach["setters"], "np.matrixlib."), reach["setters"])
        self.assertEqual(reach["draws"], ["np.matlib.rand", "np.matlib.randn"])

        closed = proofs_with(SMALLEST_DENYLIST)
        self.assertTrue(all(closed[name]["held"] for name in numpy_proofs), {n: closed[n] for n in numpy_proofs})
        self.assertIn("refused", closed["state_numpy_draws"])
        for key in ("reachable", "writable", "setters", "draws"):
            self.assertEqual(closed["state_numpy_reachable"][key], [], key)
        self.assertEqual(closed["state_numpy_reachable"]["foreign_modules"], {})
        # every probe's write was put back
        self.assertTrue(np.array_equal(np.polynomial.polynomial.polyx, pristine[0]))
        self.assertTrue(np.array_equal(np.polynomial.Polynomial.domain, pristine[1]))
        self.assertEqual(dict(np.typecodes), pristine[2])
        self.assertEqual(set(np.matrixlib.defmatrix.N.overrides.ARRAY_FUNCTIONS), pristine[3])
        self.assertEqual(EB.clear_numpy_marks(), 0)

    def test_the_reach_proof_is_behavioral(self):
        # A fix that leaves every writable object reachable but keeps writes from outliving a program (here: an engine
        # that runs each program alone and puts numpy back after it) holds without refusing a single object. It must
        # still refuse the setters and the draws: isolation does not make a call to a process-wide registry, or a draw
        # from a generator the operating system seeded, repeatable. The walk still lists the objects.
        from league.gym import safety

        walk = EB.numpy_walk()
        real_run = EB.run

        def isolating(programs, store, window, *, stress=1.0):
            out = []
            for program in programs:
                kept = EB.Restorer(walk["_targets"])
                try:
                    out += real_run([program], store, window, stress=stress)
                finally:
                    kept.reset()
            return out

        calls = frozenset(p.rsplit(".", 1)[-1] for p in walk["setters"] + walk["draws"])
        with mock.patch.object(safety, "NUMPY_BANNED", safety.NUMPY_BANNED | calls), mock.patch.object(EB, "run", isolating):
            reach = EB.numpy_reach(self.store)
        self.assertTrue(reach["held"], {k: v for k, v in reach.items() if k != "writable"})
        self.assertEqual(reach["writable"], walk["writable"])
        self.assertEqual(reach["reachable"], [])
        self.assertGreater(reach["trades"][0], 50)
        self.assertEqual(len(set(reach["trades"])), 1)
        # isolation alone, with the setters and draws still reachable, does not hold
        with mock.patch.object(EB, "run", isolating):
            reach = EB.numpy_reach(self.store)
        self.assertFalse(reach["held"])
        self.assertEqual(reach["reachable"], [])
        self.assertEqual(reach["draws"], walk["draws"])
        # and without the isolation, the same proof fails on every object, through the run and the batch
        with mock.patch.object(safety, "NUMPY_BANNED", safety.NUMPY_BANNED | calls):
            reach = EB.numpy_reach(self.store)
        self.assertFalse(reach["held"])
        self.assertEqual(reach["reachable"], walk["writable"])
        self.assertEqual(reach["trades"][1:], [0, 0])

    def test_historical_volume_without_receipts_is_hidden(self):
        [result] = EB.run([self.load("leak_volume_bars")], self.store, "validation")
        self.assertEqual({t.get("tag") for t in result["trades"]}, {"coin"})

    def test_state_resets_and_the_numpy_probe_measures_its_channel(self):
        import numpy as np
        from league.gym.runtime import load_program

        fresh = self.load("state_fresh_runs")
        first, second = EB.run([fresh], self.store, "validation"), EB.run([fresh], self.store, "validation")
        self.assertEqual(EB.trade_rows(first[0]), EB.trade_rows(second[0]))
        self.assertEqual(len(first[0]["trades"]), 5)
        try:
            probe = load_program(EB.STATE_PROGRAMS["state_numpy_runs"].lstrip("\n"), name="numpy-runs")
        except CodeRefused:
            return  # the static check closes the channel: the proof holds by refusal
        try:
            EB.clear_numpy_marks()
            [clean] = EB.run([probe], self.store, "validation")
            np.typecodes[EB.NUMPY_MARK_PREFIX + "run"] = "1"  # what an earlier run in this process leaves behind
            [marked] = EB.run([probe], self.store, "validation")
        finally:
            self.assertGreaterEqual(EB.clear_numpy_marks(), 1)
        self.assertGreater(len(clean["trades"]), 0)
        self.assertEqual(len(marked["trades"]), 0)

    def test_the_batch_mate_probe_compares_a_reader_alone_and_after_a_writer(self):
        out = EB.mates(self.store, "state_ctx_mate_writer", "state_ctx_mate_reader", "claim")
        if "refused" in out:
            return  # the static check closes the channel
        self.assertGreater(out["trades"][0], 50)
        self.assertEqual(out["held"], out["trades"][0] == out["trades"][1])

    def test_ablation_probe_tells_a_working_switch_from_an_ignored_one(self):
        on, off = self.load("ablation_ctx_params"), self.load("ablation_ctx_params", {"signal_on": 0})
        ignored_off = self.load("ablation_read_ignored", {"signal_on": 0})
        results = EB.run([on, off, ignored_off], self.store, "validation")
        self.assertGreater(len(results[0]["trades"]), 50)
        self.assertEqual(len(results[1]["trades"]), 0)
        self.assertEqual(len(results[2]["trades"]), len(results[0]["trades"]))

    def test_the_level_probe_world_scales_prices_and_nothing_else(self):
        from league.gym.store import Store

        scaled_dir = Path(tempfile.mkdtemp(prefix="evaluator-suite-scaled-"))
        try:
            EB.write_world(scaled_dir, EB.truth(0), level_scale=1.25, windows=("validation",))
            dense = self.load("planted_dense")
            [normal] = EB.run([dense], self.store, "validation")
            [scaled] = EB.run([dense], Store(scaled_dir), "validation")
        finally:
            shutil.rmtree(scaled_dir, ignore_errors=True)
        self.assertEqual([t["type"] for t in normal["trades"]], [t["type"] for t in scaled["trades"]])
        self.assertAlmostEqual(normal["summary"]["t_daily"], scaled["summary"]["t_daily"], delta=0.2)


class Report(unittest.TestCase):
    """The code that produces the headline a release is compared on, on fabricated rows (no engine, no store)."""

    def rows(self, reps=4):
        out = []
        for r in range(reps):
            cases = {}
            for c in EB.CASES:
                if c["kind"] not in EB.PIPELINE_KINDS:
                    continue
                if c["id"] in ("leak_memorized_levels", "planted_regime_years") or (c["id"] == "planted_dense" and r):
                    row = _passing_row()
                elif c["id"] == "fill_crossed_quotes":
                    row = _stopped_row("train_stress", impossible=1 if r == 0 else 0)
                else:
                    row = _stopped_row("static" if c["id"] in REFUSED else "train_stress")
                promoted = row["promoted"] and not (c["id"] == "leak_memorized_levels" and r >= 2)
                row = {**row, "promoted": promoted, "stopped_at": None if promoted else row["stopped_at"] or "holdout"}
                if c["id"] == "leak_memorized_levels":  # promoted in 2 of 4 worlds, flagged in all 4
                    row["probes"] = {**row["probes"], "level_invariance": {"flagged": True}}
                    row["stages"] = {**row["stages"], "holdout": promoted}
                if c["id"] == "leak_numpy_memo":  # its stress twin learns from the normal run in every world
                    row["probes"] = {**row["probes"], "stress_contaminated": True}
                if c.get("finding"):
                    row["review_contract"] = {"grounded_rejection_kept": True, "ungrounded_rejection_downgraded": True}
                cases[c["id"]] = row
            proofs = {name: {"held": name != "state_ctx_batchmates", "claim": name, "trades": [5, 5]}
                      for name in ("state_fresh_runs", "state_ctx_batchmates")}
            ablations = {"ablation_ctx_params": {"broken": False, "static_refused": False, "behavioral_effective": True,
                                                 "static_reason": None},
                         "ablation_read_ignored": {"broken": True, "static_refused": False, "behavioral_effective": False,
                                                   "static_reason": None}}
            out.append({"cases": cases, "proofs": proofs, "ablations": ablations})
        return out

    def search(self):
        def trial(noise_looks):
            return {name: {"promoted": False, "candidates": 3, "validations": 2,
                           "looks": noise_looks if name in ("no_floors", "sparse_floors") else 0} for name in EB.VARIANTS}
        signal = {name: {"promoted": name != "current", "candidates": 1, "validations": 1, "looks": 1} for name in EB.VARIANTS}
        return {"noise_sparse_search": [trial(1), trial(0)], "signal_sparse": [signal, signal]}

    def report(self):
        out = EB.aggregate(self.rows(), self.search())
        report = {"suite": EB.SUITE_ID, "suite_sha": "s", "cohort": "development", "pinned": True, "full_protocol": True,
                  "tree": {"fixture_sha": "f"}, "runtime": {"python": "3", "numpy": "2", "elapsed_seconds": 1.0}, **out}
        report["headline"] = EB.headline(report)
        return report

    def test_rates_count_case_worlds_and_whole_cases(self):
        rates = self.report()["rates"]
        negatives = [c for c in EB.CASES if c["kind"] == "negative"]
        self.assertEqual(rates["false_promotion"]["count"], 2)
        self.assertEqual(rates["false_promotion"]["of"], 4 * len(negatives))
        self.assertEqual(rates["false_promotion_mechanical_scope"]["count"], 0)
        self.assertEqual((rates["negative_cases_promoted"]["count"], rates["negative_cases_promoted"]["of"]),
                         (1, len(negatives)))
        positives = [c for c in EB.CASES if c["kind"] == "positive"]
        self.assertEqual(rates["missed_signal"]["count"], 4 * len(positives) - 3 - 4)
        self.assertEqual(rates["positive_cases_missed_in_any_world"]["count"], len(positives) - 1)
        low, high = rates["false_promotion"]["lower_95"], rates["false_promotion"]["upper_95"]
        self.assertLess(low, rates["false_promotion"]["rate"])
        self.assertGreater(high, rates["false_promotion"]["rate"])

    def test_the_level_probe_counts_detections_among_promoted_runs_only(self):
        detected = self.report()["level_invariance_probe"]["detected"]
        self.assertEqual((detected["count"], detected["of"]), (2, 2))  # flagged 4 times, promoted twice
        self.assertLessEqual(detected["rate"], 1.0)

    def test_smoke_cases_are_recorded_and_kept_out_of_the_rates(self):
        report = self.report()
        self.assertEqual(report["cases"]["leak_events_next"]["kind"], "smoke")
        self.assertIn("leak_events_next", report["headline"]["promoted_by_case"])
        negatives = [c for c in EB.CASES if c["kind"] == "negative"]
        self.assertEqual(report["rates"]["false_promotion"]["of"], 4 * len(negatives))

    def test_the_headline_is_a_per_case_vector(self):
        head = self.report()["headline"]
        self.assertEqual(head["promoted_by_case"]["leak_memorized_levels"], 2)
        self.assertEqual(head["missed_by_case"]["planted_dense"], 1)
        self.assertEqual(head["refused"], sorted(REFUSED))
        self.assertEqual(head["impossible_fills"], 1)
        self.assertEqual(head["impossible_fills_by_case"]["fill_crossed_quotes"], 1)
        self.assertEqual(head["impossible_fills_by_case"]["fill_stale_quote"], 0)
        self.assertEqual(head["stress_contaminated"], {"leak_numpy_memo": 4})
        self.assertEqual(set(head["review_contract"]), {c["id"] for c in EB.CASES if c.get("finding")})
        self.assertEqual(head["proofs_failed"], ["state_ctx_batchmates"])
        self.assertEqual(head["runtime"], {"python": "3", "numpy": "2"})
        self.assertIn("aligned_floors", head["owner_rule"])
        # A development run's verdicts are unconfirmed: none can be cited as meeting the rule.
        self.assertTrue(all(v["met_and_confirmed"] is None for v in head["owner_rule"].values()))

    def test_a_confirmation_run_records_whether_each_verdict_was_met_and_confirmed(self):
        frozen = {"headline": {"owner_rule": {"aligned_floors": {"met": True}, "current": {"met": False},
                                              "no_floors": {"met": True}}}}
        variants = {"aligned_floors": {"owner_rule": {"met": True}}, "current": {"owner_rule": {"met": False}},
                    "no_floors": {"owner_rule": {"met": False}}, "sparse_floors": {"owner_rule": {"met": True}}}
        out = EB.confirm_owner_rule(frozen, variants)
        self.assertEqual(out["aligned_floors"], {"development_met": True, "confirmation_met": True, "met_and_confirmed": True})
        self.assertFalse(out["no_floors"]["met_and_confirmed"])  # met on development only
        self.assertFalse(out["sparse_floors"]["met_and_confirmed"])  # never judged on development
        self.assertIsNone(out["sparse_floors"]["development_met"])
        report = {**self.report(), "cohort": "confirmation"}
        report["owner_rule_confirmation"] = EB.confirm_owner_rule(
            {"headline": {"owner_rule": {name: {"met": True} for name in EB.VARIANTS}}}, report["variants"])
        head = EB.headline(report)
        self.assertEqual({name: v["met_and_confirmed"] for name, v in head["owner_rule"].items()},
                         {name: v["owner_rule"]["met"] for name, v in report["variants"].items()})

    def test_the_owner_rule_has_power_and_rejects_the_no_floors_reference(self):
        report = self.report()
        no_floors = report["variants"]["no_floors"]["owner_rule"]
        self.assertFalse(no_floors["met"])
        self.assertEqual(no_floors["noise_bands_with_more_looks"], ["noise_sparse_search"])
        self.assertTrue(report["verdict_sensitivity"]["no_floors_rejected"])
        self.assertTrue(report["verdict_sensitivity"]["noise_looks_see_no_floors"])
        self.assertTrue(report["variants"]["current"]["owner_rule"]["checks"]["noise_looks_not_higher_in_any_band"])
        self.assertFalse(report["variants"]["current"]["owner_rule"]["met"])  # it does not lower misses against itself

    def test_compare_lists_regressions_case_by_case(self):
        old = self.report()
        new = json.loads(json.dumps(old["headline"]))
        new["promoted_by_case"]["leak_memorized_levels"] = 0
        new["promoted_by_case"]["fill_crossed_quotes"] = 2
        new["refused"] = sorted(REFUSED - {"leak_private_attr"})
        new["proofs_held"]["state_fresh_runs"] = 3
        new["ablations"]["ablation_read_ignored"]["static_refused"] = 4
        out = EB.compare(old, new)
        self.assertTrue(out["comparable"])
        self.assertIn("fill_crossed_quotes promoted: 0 then 2", out["regressions"])
        self.assertIn("leak_private_attr is no longer refused by the static check", out["regressions"])
        self.assertIn("proof state_fresh_runs held: 4 then 3", out["regressions"])
        self.assertIn("leak_memorized_levels promoted: 2 then 0", out["improvements"])
        self.assertIn("ablation_read_ignored static refusals: 0 then 4", out["improvements"])
        new["tree"] = {"fixture_sha": "other"}
        self.assertFalse(EB.compare(old, new)["comparable"])

    def test_compare_steps_the_review_contract_and_contamination_per_case(self):
        # Same totals, different cases: each move shows. A weakened review-contract answer is a regression.
        old = self.report()
        new = json.loads(json.dumps(old["headline"]))
        new["review_contract"]["leak_memorized_levels"]["ungrounded_rejection_downgraded"] = False
        new["stress_contaminated"] = {"fill_passive_spread": 4}
        new["impossible_fills_by_case"] = {**new["impossible_fills_by_case"], "fill_crossed_quotes": 0, "fill_stale_quote": 1}
        out = EB.compare(old, new)
        self.assertTrue(out["comparable"])
        self.assertIn("leak_memorized_levels review contract ungrounded_rejection_downgraded: True then False",
                      out["regressions"])
        self.assertIn("fill_passive_spread stress-contaminated runs: 0 then 4", out["regressions"])
        self.assertIn("leak_numpy_memo stress-contaminated runs: 4 then 0", out["improvements"])
        self.assertIn("fill_stale_quote impossible fills: 0 then 1", out["regressions"])
        self.assertIn("fill_crossed_quotes impossible fills: 1 then 0", out["improvements"])
        del new["review_contract"]["leak_numpy_memo"]
        self.assertIn("leak_numpy_memo review contract: {'grounded_rejection_kept': True, 'ungrounded_rejection_downgraded': "
                      "True} then None (the case set changed)", EB.compare(old, new)["regressions"])
        self.assertEqual(EB.compare(old, old)["regressions"], [])

    def test_the_receipt_keeps_a_reproducible_rows_digest(self):
        report = {**self.report(), "replication_rows": [{"cases": {}, "seconds": 1.0}, {"cases": {}, "seconds": 2.0}]}
        receipt = EB.receipt(report)
        self.assertNotIn("replication_rows", receipt)
        self.assertEqual(receipt["replication_rows_sha256"], EB.digest([{"cases": {}}, {"cases": {}}]))
        self.assertEqual(EB._headline_of(receipt), report["headline"])

    @unittest.skipUnless(HAVE, "numpy/pyarrow not installed (requirements-gym.txt)")
    def test_a_refused_numpy_probe_leaves_the_proofs_whole(self):
        # The recommended release-B fix refuses numpy's mutable module attributes. Then every numpy probe is refused, the
        # proofs hold by refusal, and the report is still built (no KeyError at the end of a long run).
        from league.gym import runtime

        real = runtime.load_program

        def refusing(code, *args, **kwargs):
            if any(name in code for name in ("np.typecodes", "np.sctypeDict", "np.polynomial", "np.dtypes", "np.matlib",
                                             "np.matrixlib")):
                raise CodeRefused("numpy module attributes are not allowed (simulated)")
            return real(code, *args, **kwargs)

        def fake_run(programs, store, window, *, stress=1.0):
            return [{"status": "ok", "trades": [{"day": "2025-01-02"}] * 5, "summary": {}} for _ in programs]

        with mock.patch.object(runtime, "load_program", refusing), mock.patch.object(EB, "run", fake_run), \
                mock.patch.object(EB, "split_proof", lambda root: {"held": True, "claim": "stub"}), \
                mock.patch.object(EB, "mates", lambda *a, **k: {"held": True, "claim": "stub"}):
            proofs = EB.proofs(store=None, root=Path("unused"))
        self.assertEqual(set(proofs), {c["id"] for c in EB.CASES if c["kind"] == "proof"})
        for name in [c["id"] for c in EB.CASES if c["id"].startswith("state_numpy_")]:
            self.assertTrue(proofs[name]["held"], name)
        self.assertIn("refused", proofs["state_numpy_draws"])
        reach = proofs["state_numpy_reachable"]
        self.assertEqual((reach["writable"], reach["setters"], reach["draws"]), ([], [], []))
        self.assertTrue({"np.typecodes", "np.sctypeDict", "np.polynomial.polynomial.polyx",
                         "np.polynomial.set_default_printstyle", "np.matlib.rand",
                         "np.matrixlib.defmatrix.N.overrides.ARRAY_FUNCTIONS"} <= set(reach["refused_containers"]))
        rows = self.rows(2)
        for row in rows:
            row["proofs"] = proofs
        out = EB.aggregate(rows, self.search())
        self.assertEqual(out["proofs"]["state_numpy_batchmates"]["held"], 2)
        self.assertEqual(out["proofs"]["state_numpy_reachable"]["observed"], [])
        self.assertNotIn("state", out["facts_contradicted"])

    def test_the_case_figures_and_opened_routes_come_from_the_worlds(self):
        rows = self.rows(2)
        stop = _stopped_row("validation")
        stop["validation"] = {"checks": {**stop["validation"]["checks"], "trades": False},
                              "numbers": {"trades": 45, "days": 45, "t": 3.5}}
        rows[0]["cases"]["planted_medium"] = stop
        rows[1]["cases"]["planted_medium"]["validation"] = {"checks": {}, "numbers": {"trades": 52, "t": 4.25}}
        for i, row in enumerate(rows):
            row["opened"] = {"leak_private_attr": {"loaded": True, "status": "ok", "trades": 60, "hits": 59, "rate": 0.98,
                                                   "t_daily": 7.0 + i, "pnl": 10.0 - 15.0 * i}}
        out = EB.aggregate(rows, self.search())
        medium = out["cases"]["planted_medium"]["figures"]
        self.assertEqual(medium["train_trades_per_year"], [60, 60])
        self.assertEqual(medium["validation_trades"], [45, 52])
        self.assertEqual(medium["validation_t"], [3.5, 4.25])
        self.assertEqual(medium["validation_t_median"], 3.875)
        self.assertEqual(medium["validation_stops"], {"trades": [45], "t": [3.5], "failed_checks": {"trades": 1}})
        self.assertEqual(out["cases"]["leak_private_attr"]["opened"],
                         {"worlds": 2, "loaded": 2, "trades": 120, "hits": 118, "direction_hit_rate": 0.9833,
                          "t_daily": [7.0, 8.0], "profitable_worlds": 1})
        self.assertNotIn("figures", out["cases"]["leak_private_attr"])  # refused: no world ran it
        self.assertNotIn("opened", out["cases"]["planted_medium"])

    def test_the_level_flag_counts_a_run_that_stopped_trading(self):
        self.assertTrue(EB._level_flag(3.0, None))
        self.assertTrue(EB._level_flag(3.0, 1.0))
        self.assertFalse(EB._level_flag(3.0, 2.9))
        self.assertFalse(EB._level_flag(1.0, None))
        self.assertFalse(EB._level_flag(None, 0.0))


class Admission(unittest.TestCase):
    def frozen(self, **changes):
        tree = {"execution_sha256": "e", "evaluator_sha": "v", "fixture_sha": "f"}
        return {"cohort": "development", "pinned": True, "suite_sha": "s", "replications": 8, "search_replications": 128,
                "tree": tree, "headline": {"suite": EB.SUITE_ID}, **changes}

    def test_confirmation_needs_the_frozen_development_report_of_the_same_suite_and_tree(self):
        tree = {"execution_sha256": "e", "evaluator_sha": "v", "fixture_sha": "f"}
        self.assertEqual(EB.admit_confirmation(self.frozen(), "s", 8, 128, tree), EB.digest({"suite": EB.SUITE_ID}))
        for bad in (None, self.frozen(cohort="confirmation"), self.frozen(suite_sha="t"), self.frozen(replications=4),
                    self.frozen(tree={**tree, "evaluator_sha": "w"}), self.frozen(pinned=False)):
            with self.assertRaises(ValueError):
                EB.admit_confirmation(bad, "s", 8, 128, tree)


class Cli(unittest.TestCase):
    def test_benchmarks_dispatches_the_evaluator_suite(self):
        from league.swarm import benchmarks

        with mock.patch.object(EB, "main", return_value=7) as called:
            self.assertEqual(benchmarks.main(["--suite", "evaluator", "--json"]), 7)
        called.assert_called_once_with(["--suite", "evaluator", "--json"])

    def fake(self, pinned):
        report = Report().report()
        return {**report, "pinned": pinned, "pinned_sha": "p" * 64, "suite_sha": "s" * 64, "replication_rows": []}

    def test_exit_codes(self):
        def quiet():
            return mock.patch("builtins.print")

        with quiet(), mock.patch.object(EB, "scorable", return_value=[]), \
                mock.patch.object(EB, "suite", return_value=self.fake(False)):
            self.assertEqual(EB.main(["--suite", "evaluator"]), 3)
        with quiet(), mock.patch.object(EB, "scorable", return_value=[]), \
                mock.patch.object(EB, "suite", return_value=self.fake(True)):
            self.assertEqual(EB.main(["--suite", "evaluator"]), 0)
        with quiet(), mock.patch.object(EB, "scorable", return_value=["league.gym.experiment.check_experiment"]):
            self.assertEqual(EB.main(["--suite", "evaluator"]), 5)
        with quiet(), mock.patch.object(EB, "scorable", return_value=[]), \
                mock.patch.object(EB, "suite", side_effect=ValueError("confirmation is not admissible")), \
                tempfile.TemporaryDirectory() as temp:
            frozen = Path(temp) / "dev.json"
            frozen.write_text("{}")
            self.assertEqual(EB.main(["--suite", "evaluator", "--cohort", "confirmation", "--frozen", str(frozen)]), 2)
        with quiet(), mock.patch("sys.stderr"), self.assertRaises(SystemExit):
            EB.main(["--suite", "evaluator", "--cohort", "confirmation"])

    def test_compare_exits_4_on_a_regression(self):
        old = self.fake(True)
        worse = json.loads(json.dumps(old["headline"]))
        worse["promoted_by_case"]["fill_stale_quote"] = 1
        with tempfile.TemporaryDirectory() as temp, mock.patch("builtins.print"), \
                mock.patch.object(EB, "scorable", return_value=[]), mock.patch.object(EB, "suite", return_value=old):
            path = Path(temp) / "old.json"
            path.write_text(json.dumps({"headline": worse}))
            self.assertEqual(EB.main(["--suite", "evaluator", "--compare", str(path)]), 0)  # the new run improved on it
            path.write_text(json.dumps({"headline": {**worse, "promoted_by_case": {
                **worse["promoted_by_case"], "fill_stale_quote": 0, "leak_memorized_levels": 0}}}))
            self.assertEqual(EB.main(["--suite", "evaluator", "--compare", str(path)]), 4)

    def test_tree_mode_runs_this_suite_file_in_a_child_with_the_tree_first(self):
        from types import SimpleNamespace

        tree = Path(EB.__file__).resolve().parents[2]
        args = SimpleNamespace(json=True, output=Path("out.json"), receipt=None, compare=None, frozen=None, scratch=None,
                               replications=2, search_replications=None, allow_unpinned=False, cohort="development")
        with mock.patch("subprocess.run", return_value=SimpleNamespace(returncode=0)) as called:
            self.assertEqual(EB.run_on_tree(tree, args), 0)
        command = called.call_args.args[0]
        self.assertEqual(command[3:5], [str(tree), str(Path(EB.__file__).resolve())])
        self.assertIn("--cohort", command)
        self.assertEqual(command[command.index("--output") + 1], str(Path("out.json").resolve()))
        self.assertEqual(command[command.index("--replications") + 1], "2")
        self.assertNotIn("PYTHONPATH", called.call_args.kwargs["env"])


class ReportDocument(unittest.TestCase):
    """EVALUATOR_1.md's tables are rendered from the committed receipts, and the receipts are the pinned suite's."""

    def test_the_reports_tables_are_its_receipts(self):
        docs = Path(__file__).resolve().parents[2] / "docs" / "benchmarks"
        dev = json.loads((docs / "evaluator_1.json").read_text())
        conf = json.loads((docs / "evaluator_1_confirmation.json").read_text())
        for receipt, cohort in ((dev, "development"), (conf, "confirmation")):
            self.assertEqual(receipt["cohort"], cohort)
            self.assertTrue(receipt["pinned"] and receipt["full_protocol"])
            self.assertEqual(receipt["suite_sha"], EB.PINNED_SUITE_SHA)  # the receipts are this pinned suite's
        self.assertEqual(conf["frozen_development_headline_sha"], EB.digest(dev["headline"]))
        text = (docs / "EVALUATOR_1.md").read_text()
        for name, table in doc_tables(dev, conf).items():
            self.assertIn(table, text, f"EVALUATOR_1.md's {name} table is not its receipts':\n{table}")


#: The pipeline's stages, in order, as EVALUATOR_1 names them.
STAGE_NAMES = {"static": "static", "train_eligible": "Train eligibility", "train_stress": "Train stress", "drift": "drift",
               "validation": "Validation", "review": "review", "holdout": "holdout"}
#: The owner-rule checks, as EVALUATOR_1's verdict column names a failed one.
CHECK_NAMES = {"engine_false_promotions_not_higher": "engine false promotions rise",
               "search_false_promotions_not_higher": "search false promotions rise",
               "engine_negative_looks_not_higher": "engine looks rise", "noise_looks_not_higher_in_any_band": "noise looks rise",
               "missed_signals_lower": "misses do not fall"}


def _pct(x):
    return f"{100 * x:.1f}%"


def _rate_cell(r):
    if not r["count"]:
        return f"0/{r['of']} (95% upper {_pct(r['upper_95'])})"
    return f"{r['count']}/{r['of']} ({_pct(r['rate'])}; 95% {100 * r['lower_95']:.1f}–{100 * r['upper_95']:.1f}%)"


def _stops(case):
    order = list(STAGE_NAMES)
    stops = sorted(((k, n) for k, n in case["stopped_at"].items() if k != "promoted"), key=lambda kv: order.index(kv[0]))
    text = f"{case['promoted']}/{case['of']}"
    return text + (f" ({', '.join(f'{STAGE_NAMES[k]} {n}' for k, n in stops)})" if stops else "")


def _both(a, b):
    return a if a == b else f"{a} / {b}"


def _table(head, rows):
    lines = ["| " + " | ".join(head) + " |", "| " + " | ".join("---" for _ in head) + " |"]
    return "\n".join(lines + ["| " + " | ".join(str(c) for c in row) + " |" for row in rows])


def doc_tables(dev, conf):
    """EVALUATOR_1.md's tables, rendered from the development and confirmation receipts."""
    cohorts = (dev, conf)
    out = {}
    r = [c["rates"] for c in cohorts]

    def one_sided(x):
        return f"{x['count']}/{x['of']} (one-sided 95% upper {_pct(x['upper_95_one_sided'])})"

    out["headline"] = _table(["Rate", "Development", "Confirmation"], [
        ["False promotion, every negative case-world", *(_rate_cell(x["false_promotion"]) for x in r)],
        ["False promotion, what the mechanical stages are meant to stop",
         *(_rate_cell(x["false_promotion_mechanical_scope"]) for x in r)],
        ["Negative cases promoted in any world", *(f"{x['negative_cases_promoted']['count']}/{x['negative_cases_promoted']['of']}"
                                                   for x in r)],
        ["Negative cases promoted, mechanical scope", *(one_sided(x["negative_cases_promoted_mechanical_scope"]) for x in r)],
        ["Missed signal, planted case-worlds", *(_rate_cell(x["missed_signal"]) for x in r)],
        ["Planted cases missed in at least one world",
         *(f"{x['positive_cases_missed_in_any_world']['count']}/{x['positive_cases_missed_in_any_world']['of']}" for x in r)],
    ])
    ids = [c["id"] for c in EB.CASES]
    signal = [cid for cid in ids if dev["cases"].get(cid, {}).get("family") == "signal"]
    out["signal cases"] = _table(["Case", "Answer", "Development", "Confirmation"], [
        [f"`{cid}`", "edge" if dev["cases"][cid]["kind"] == "positive" else "no edge",
         *(_stops(c["cases"][cid]) for c in cohorts)] for cid in signal])

    def leak(case):
        text = _stops(case)
        if case.get("opened"):
            o = case["opened"]
            lo, hi = o["t_daily"]
            text += (f"; opened: hit {o['direction_hit_rate']:.2f}, t {lo:.1f} to {hi:.1f}, "
                     f"profitable in {o['profitable_worlds']}/{o['worlds']}")
        elif case.get("direction_hit_rate") is not None:
            text += f"; hit {case['direction_hit_rate']:.2f}"
        if case.get("stress_contaminated"):
            text += f"; stress run contaminated {case['stress_contaminated']}/{case['of']}"
        return text

    leakage = [cid for cid in ids if dev["cases"].get(cid, {}).get("family") == "leakage"]
    out["leakage"] = _table(["Probe", "Development", "Confirmation"], [
        [f"`{cid}`" + (" (smoke)" if dev["cases"][cid]["kind"] == "smoke" else ""), *(leak(c["cases"][cid]) for c in cohorts)]
        for cid in leakage])

    def grouped(paths):
        """Paths by the module attribute they go through (`np.polynomial`): a group of more than two is counted."""
        groups = {}
        for path in paths:
            groups.setdefault(".".join(path.removeprefix("list(").split(".")[:2]), []).append(path)
        parts = []
        for root, members in groups.items():
            parts += [f"`{p}`" for p in members] if len(members) <= 2 else [f"{len(members)} through `{root}`"]
        return ", ".join(parts)

    def observed(proof):
        seen = proof.get("observed")
        if isinstance(proof.get("reachable"), list) or "setters" in proof:
            paths = proof["observed"] or []
            text = f"{len(paths)} reachable" + (f": {grouped(paths)}" if paths else "")
            for key in ("setters", "draws"):
                if proof.get(key):
                    text += f"; {key} {grouped(proof[key])}"
            return text
        if isinstance(seen, list):
            return ", ".join(str(x) for x in seen)
        return "refused" if proof.get("refused") else str(seen)

    proofs = [cid for cid in ids if cid in dev["proofs"]]
    out["state"] = _table(["Proof", "Fact", "Development", "Confirmation", "Observed (development, first world)"], [
        [f"`{name}`", dev["proofs"][name]["fact"], *(f"{c['proofs'][name]['held']}/{c['proofs'][name]['of']}" for c in cohorts),
         observed(dev["proofs"][name])] for name in proofs])
    out["ablations"] = _table(["Switch", "Broken", "Static contract refuses the off override", "Off variant still trades"], [
        [f"`{name}`", "yes" if a["broken"] else "no",
         _both(*(f"{c['ablations'][name]['static_refused']}/{c['ablations'][name]['of']}" for c in cohorts)),
         _both(*(f"{c['ablations'][name]['of'] - c['ablations'][name]['behavioral_effective']}/{c['ablations'][name]['of']}"
                 for c in cohorts))] for name in EB.ABLATIONS for a in [dev["ablations"][name]]])

    def verdict(c, name):
        if name == "current":
            return "reference"
        rule = c["variants"][name]["owner_rule"]
        failed = [text for k, text in CHECK_NAMES.items() if not rule["checks"][k]]
        return "met" if rule["met"] else "not met: " + ", ".join(failed)

    def cell(key, name, extra=None):
        values = []
        for c in cohorts:
            v = c["variants"][name]
            text = str(v[key]["count"])
            if extra:
                text += f" ({v[extra]['leak_memorized_sparse']})"
            values.append(text)
        return " / ".join(values)

    out["variants"] = _table(["Variant", "Engine false (sparse table)", "Engine missed", "Search false", "Noise looks",
                              "Search missed", "Verdict"], [
        [f"`{name}`", cell("engine_false_promotion", name, "engine_false_promotion_by_case"),
         cell("engine_missed_signal", name), cell("search_false_promotion", name),
         cell("search_noise_holdout_looks", name), cell("search_missed_signal", name),
         _both(verdict(dev, name), verdict(conf, name))] for name in EB.VARIANTS])

    def band(case):
        spec = EB.SEARCH["cases"][case]
        kind = "planted" if spec["positive"] else "noise"
        tails = ", t3" if spec.get("tails") else ""
        return f"{kind}, {spec['trades_per_year']} a year{tails}"

    rows = []
    for case, spec in EB.SEARCH["cases"].items():
        if spec["positive"] and spec["trades_per_year"] != 48:
            continue
        key = "promoted" if spec["positive"] else "lineages_with_look"
        label = band(case) + (": promoted" if spec["positive"] else "")
        rows.append([label, *(c["variants"][name]["search_by_case"][case][key] for c in cohorts
                              for name in ("current", "aligned_floors"))])
    out["bands"] = _table(["Band (128 lineages each)", "`current` dev", "`aligned_floors` dev", "`current` conf",
                           "`aligned_floors` conf"], rows)
    return out


def _passing_row():
    years = {str(y): {"trades": 60, "days_traded": 60, "pnl": 10.0, "t_daily": 2.5} for y in (2022, 2023, 2024)}
    checks = {"status_ok": True, "trades": True, "days": True, "mean_positive": True, "t": True, "dsr": True,
              "quarters": True, "stress": True}
    return {"stages": {"static": True, "train_eligible": True, "train_stress": True, "drift": True, "validation": True,
                       "review": True, "holdout": True},
            "promoted": True, "stopped_at": None, "probes": {"stress_contaminated": False, "level_invariance": {"flagged": False}},
            "train": {"status": "ok", "years": years, "quarters": "12/12", "trades": 180, "days_traded": 180, "t_daily": 3.0,
                      "pnl": 30.0},
            "validation": {"checks": checks, "numbers": {"trades": 60, "days": 60}},
            "validation_pooled": {"checks": checks, "numbers": {"trades": 120, "days": 120}}}


def _stopped_row(stage, impossible=0):
    if stage == "static":
        return {"stages": {"static": False}, "promoted": False, "stopped_at": "static", "refused": "refused (fabricated)"}
    row = _passing_row()
    row["stages"] = {**row["stages"], stage: False}
    probes = {**row["probes"], "impossible_fills": impossible}
    return {**row, "promoted": False, "stopped_at": stage, "probes": probes}


def _tiny_world():
    world = EB.truth(0)
    rng = random.Random(0)
    return {**world, "moves": [{"absent": 1.0} if r["window"] != "history" else {} for r in world["days"]],
            "opens": [400.0 + i * 0.37 for i in range(len(world["days"]))],
            "marks": ["".join(rng.choice("ud") for _ in EB.MARK_INDEXES) for _ in world["days"]]}


if __name__ == "__main__":
    unittest.main()
