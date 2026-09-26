"""Determinism: the same inputs give the same result hash, whatever else shares the batch; the
example programs (founders' mechanisms) run clean. Synthetic stores only."""

import datetime as dt
import shutil
import tempfile
import unittest
from pathlib import Path

try:
    import numpy  # noqa: F401
    import pyarrow  # noqa: F401
    HAVE = True
except ImportError:  # pragma: no cover
    HAVE = False

if HAVE:
    from league.gym import engine as E
    from league.gym import fills as F
    from league.gym import results as RS
    from league.gym import runtime as R
    from league.gym import store as S
    from league.gym import synth

EXAMPLES = Path(__file__).resolve().parents[1] / "gym" / "examples"
MID_TRADER = '''
NEEDS = {"roots": ["SPY"], "dte": [0, 2], "band": 0.03, "cadence": 15}
PARAMS = {"k": 1}
def decide(ctx):
    out = [{"close": p["id"], "limit": {"mid": ctx.params["k"]}, "tif": 10} for p in ctx.positions if p["held_minutes"] > 60]
    if not ctx.positions and not ctx.orders and ctx.minute < 900:
        out.append({"open": "debit_vertical", "legs": [{"side": "long", "right": "C", "dte": 1, "atm": 0},
                    {"side": "short", "right": "C", "rel": 0, "offset": 2.0}], "max_loss": 300, "limit": {"mid": ctx.params["k"]}, "tif": 10})
    return out
'''


@unittest.skipUnless(HAVE, "numpy/pyarrow not installed (requirements-gym.txt)")
class Determinism(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix="gym-det-")
        cls.days = synth.weekdays(dt.date(2023, 5, 1), 8)
        synth.generate(cls.dir, roots=("SPY",), days=cls.days, strikes_each_side=10, max_dte=4, seed=11)
        cls.store = S.Store(cls.dir)
        cls.model = F.FillModel(hazard={F.cell(q, 2, d, m, t): 0.08 for q in (0.1, 0.3) for d in (0, 1, 2)
                                        for m in (0.0, 0.01) for t in (600, 700, 950)}, source="test")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def programs(self):
        return [R.load_program((EXAMPLES / "condor_vrp.py").read_text(), name="condor", params={"vrp_min": 0.5}),
                R.load_program((EXAMPLES / "putspread_dip.py").read_text(), name="dip", params={"trend_days": 2, "dip_pct": 0.05}),
                R.load_program(MID_TRADER, name="mid")]

    def cfg(self, **kw):
        return E.RunConfig(window="train", roots=("SPY",), fill_model=self.model, **kw)

    def test_same_inputs_same_hash(self):
        a = E.run(self.programs(), self.store, self.cfg())
        b = E.run(self.programs(), self.store, self.cfg())
        self.assertEqual([r["result_sha"] for r in a], [r["result_sha"] for r in b])
        self.assertEqual([r["run_id"] for r in a], [r["run_id"] for r in b])
        self.assertGreater(a[0]["summary"]["trades"], 0)
        self.assertGreater(a[2]["fills"]["fills"], 0)

    def test_the_batch_does_not_change_a_programs_result(self):
        together = E.run(self.programs(), self.store, self.cfg())
        for i, program in enumerate(self.programs()):
            [alone] = E.run([program], self.store, self.cfg())
            self.assertEqual(alone["result_sha"], together[i]["result_sha"], program.name)

    def test_what_changes_the_identity(self):
        [base] = E.run(self.programs()[:1], self.store, self.cfg())
        tweaked = R.load_program((EXAMPLES / "condor_vrp.py").read_text(), name="condor", params={"vrp_min": 0.6})
        [other] = E.run([tweaked], self.store, self.cfg())
        self.assertNotEqual(base["run_id"], other["run_id"])
        [stressed] = E.run(self.programs()[:1], self.store, self.cfg(stress=1.5))
        self.assertNotEqual(base["run_id"], stressed["run_id"])
        renamed = R.load_program((EXAMPLES / "condor_vrp.py").read_text(), name="another name", params={"vrp_min": 0.5})
        self.assertEqual(renamed.run_sha, self.programs()[0].run_sha)
        self.assertEqual(base["trials"], 1)
        # The data version names exactly the files read.
        self.assertEqual(self.store.data_version(["SPY"], self.days), base["data_version"])
        self.assertNotEqual(self.store.data_version(["SPY"], self.days[:-1]), base["data_version"])

    def test_examples_run_clean_and_views_hide_what_they_must(self):
        results = E.run(self.programs(), self.store, self.cfg())
        for r in results:
            self.assertEqual(r["status"], "ok", r["runtime"])
            self.assertEqual(r["runtime"]["errors"], 0, r["runtime"]["messages"])
            self.assertEqual(len(r["daily"]), len(self.days))
            self.assertAlmostEqual(sum(d[1] for d in r["daily"]), r["summary"]["pnl"], places=2)
        v = RS.view(results[0], "validation")
        self.assertNotIn("trades", v)
        self.assertNotIn("daily", v)
        hashes = ("run_id", "run_sha", "program_sha", "result_sha", "data_version", "fill_model", "code", "tables")
        self.assertNotIn("2023", RS.canonical({k: x for k, x in v.items() if k not in hashes}))
        self.assertEqual(set(RS.view(results[0], "gate")), {"run_id", "status", "trials"})

    def test_segments_merge_into_one_trial(self):
        whole = E.run(self.programs()[:1], self.store, self.cfg())[0]
        parts = [E.run(self.programs()[:1], self.store, self.cfg(start=self.days[0], end=self.days[3]))[0],
                 E.run(self.programs()[:1], self.store, self.cfg(start=self.days[4], end=self.days[-1]))[0]]
        merged = RS.merge(parts)
        self.assertEqual(merged["trials"], 1)
        self.assertEqual(len(merged["daily"]), len(whole["daily"]))
        self.assertEqual(merged["summary"]["trades"], sum(p["summary"]["trades"] for p in parts))
        self.assertEqual(RS.merge(parts)["result_sha"], merged["result_sha"])


if __name__ == "__main__":
    unittest.main()


MUTATOR = '''
NEEDS = {"roots": ["SPY"], "dte": [0, 2], "band": 0.03, "cadence": 30}
PARAMS = {"marks": [1.0]}
def decide(ctx):
    ctx.params["marks"].append(ctx.minute)
    if len(ctx.params["marks"]) % 7 == 0 and not ctx.positions:
        return [{"open": "long_call", "legs": [{"side": "long", "right": "C", "dte": 1, "atm": 0}], "qty": 1}]
    return [{"close": p["id"]} for p in ctx.positions if p["held_minutes"] > 90]
'''


@unittest.skipUnless(HAVE, "numpy/pyarrow not installed (requirements-gym.txt)")
class Isolation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix="gym-iso-")
        synth.generate(cls.dir, roots=("SPY",), days=synth.weekdays(dt.date(2023, 5, 1), 3), strikes_each_side=5, max_dte=3)
        cls.store = S.Store(cls.dir)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def test_a_program_that_mutates_its_params_touches_only_its_own_run(self):
        program = R.load_program(MUTATOR, name="mutator")
        cfg = E.RunConfig(window="train", roots=("SPY",))
        [alone] = E.run([program], self.store, cfg)
        pair = E.run([program, program], self.store, cfg)
        [again] = E.run([program], self.store, cfg)
        self.assertEqual(program.params, {"marks": [1.0]})
        self.assertGreater(alone["summary"]["trades"], 0)
        self.assertEqual({alone["result_sha"], again["result_sha"], pair[0]["result_sha"], pair[1]["result_sha"]},
                         {alone["result_sha"]})

    def test_rules_are_read_only_and_a_compute_budget_disqualifies(self):
        code = MUTATOR.replace('ctx.params["marks"].append(ctx.minute)', 'ctx.rules["SPY"]["types"].append("naked_call")')
        [r] = E.run([R.load_program(code)], self.store, E.RunConfig(window="train", roots=("SPY",)))
        self.assertTrue(any("AttributeError" in m for m in r["runtime"]["messages"]), r["runtime"])
        [slow] = E.run([R.load_program(MUTATOR)], self.store, E.RunConfig(window="train", roots=("SPY",), max_decide_seconds=0.0))
        self.assertEqual(slow["status"], "disqualified")
        self.assertIn("budget", slow["runtime"]["disqualified"])

    def test_a_failed_worker_unit_is_reported_not_fatal(self):
        from unittest import mock
        from league.gym import batch as B
        jobs = [("mutator", MUTATOR, {})]
        with mock.patch.object(B, "_unit", side_effect=RuntimeError("worker died")):
            doc = B.run_batch(jobs, store_root=self.dir, window="train", roots=["SPY"], workers=1)
        [r] = doc["results"]
        self.assertEqual((r["status"], r["trials"]), ("error", 0))
        self.assertIn("worker died", r["reason"])
        self.assertEqual(doc["batch"]["trials"], 0)
