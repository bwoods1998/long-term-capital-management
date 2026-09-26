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
        cls.model = synth.uniform_model(0.08, ("SPY",), levels=(2, 3), size=5)

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


# Buys the XSP 450 call (expiring D4) at 10:00 whenever it holds nothing; tags the trade with the sessions it
# has seen (a STATE counter), so a warm-up's replayed days show in the tag.
HOLDER = '''
NEEDS = {"roots": ["XSP"], "dte": [0, 10], "band": 0.2, "cadence": 5, "start": 600}
PARAMS = {}
STATE = {"sessions": 0, "last": 10000}
def decide(ctx):
    if ctx.minute < STATE["last"]:
        STATE["sessions"] += 1
    STATE["last"] = ctx.minute
    if not ctx.positions and not ctx.orders and ctx.minute == 600:
        return [{"open": "long_call", "legs": [{"side": "long", "right": "C", "dte": 0, "strike": 450}], "qty": 1,
                 "tag": str(STATE["sessions"])}]
    return []
'''


@unittest.skipUnless(HAVE, "numpy/pyarrow not installed (requirements-gym.txt)")
class SplitBoundaries(unittest.TestCase):
    """A split run's inner boundaries are an accounting split: open positions valued at the mid with no fee, and
    STATE warmed on the prior days without trading. Hand-computed; XSP (cash-settled) keeps the arithmetic short."""

    D = [dt.date(2023, 3, 6), dt.date(2023, 3, 7), dt.date(2023, 3, 8), dt.date(2023, 3, 9)]
    V = [dt.date(2025, 3, 3), dt.date(2025, 3, 4), dt.date(2025, 3, 5), dt.date(2025, 3, 6)]

    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix="gym-split-")
        w = synth.Writer(cls.dir)
        w.calendar(cls.D + cls.V)
        for days in (cls.D, cls.V):
            for day, (bid, ask) in zip(days, ((2.00, 2.10), (1.80, 1.90), (1.20, 1.30), (0.60, 0.70))):
                synth.flat_day(w, "XSP", day, [{"expiration": days[3], "strike": 450, "right": "C", "quotes": {571: (bid, ask)}}],
                               prices=450.5)
        w.finish()
        cls.store = S.Store(cls.dir)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def batch(self, split, window="train", doc=None):
        from league.gym import batch as B
        out = B.run_batch([("holder", HOLDER, {})], store_root=self.dir, window=window, roots=["XSP"], split=split,
                          stress_twin=False, _raw=True)
        if doc is not None:
            doc.update(out["batch"])
        [result] = out["results"]
        self.assertEqual(result["status"], "ok", result.get("runtime"))
        return result

    def test_a_segment_end_values_open_positions_at_the_mid_with_no_fee(self):
        # A segment another continues (split_mark): bought D1 at 2.10 (fee 0.55: 0.0403 + 0.50, rounded up),
        # valued at D1's closing mid 2.05 with no fee: (2.05 - 2.10) x 100 - 0.55 = -5.55.
        [t] = E.run([R.load_program(HOLDER, name="h")], self.store, E.RunConfig(window="train", roots=("XSP",), split_mark=True),
                    days=self.D[:1])[0]["trades"]
        self.assertEqual((t["exit_reason"], t["entry"], t["exit"], t["fees"], t["pnl"]), ("split_mark", 2.10, 2.05, 0.55, -5.55))
        # The window's end closes at the natural as before: sold at the 2.00 bid, fee 0.55: -10.00 - 1.10 = -11.10.
        [t] = E.run([R.load_program(HOLDER, name="h")], self.store, E.RunConfig(window="train", roots=("XSP",)),
                    days=self.D[:1])[0]["trades"]
        self.assertEqual((t["exit_reason"], t["exit"], t["fees"], t["pnl"]), ("window_end", 2.00, 1.10, -11.10))

    def test_split_two_by_hand(self):
        whole, split = self.batch(1), self.batch(2)
        # Unsplit: bought D1 at 2.10, settled D4 at intrinsic 0.50 (450.5 - 450): -160.00 - 0.55.
        self.assertEqual([(t["exit_reason"], t["pnl"], t["tag"]) for t in whole["trades"]], [("settled", -160.55, "1")])
        # Split in two (D1-D2, D3-D4): the first segment's position is valued at D2's closing mid 1.85 with no fee;
        # the second segment's program replays D1 and D2 without trading (its STATE has seen 3 sessions on D3),
        # buys D3 at 1.30 and is settled D4 at 0.50.
        self.assertEqual([(t["exit_reason"], t["entry"], t["exit"], t["pnl"], t["tag"]) for t in split["trades"]],
                         [("split_mark", 2.10, 1.85, -25.55, "1"), ("settled", 1.30, 0.50, -80.55, "3")])
        # The daily P&L up to the boundary is the unsplit run's (the mid is where the day's equity marked it).
        self.assertEqual([round(d[1], 2) for d in whole["daily"]], [-5.55, -20.0, -60.0, -75.0])
        self.assertEqual([round(d[1], 2) for d in split["daily"]], [-5.55, -20.0, -5.55, -75.0])
        self.assertAlmostEqual(sum(d[1] for d in split["daily"]), split["summary"]["pnl"], places=6)
        # Deterministic: the same split gives the same hash.
        self.assertEqual(self.batch(2)["result_sha"], split["result_sha"])
        self.assertNotEqual(whole["run_id"], split["run_id"])

    def test_validation_is_never_split(self):
        # The pool once asked for Validation in 4 segments: a mid mark would then count as selection evidence. The Gym
        # runs every window but Train whole, whatever the split asked, and says so.
        asked, whole = {}, {}
        split = self.batch(4, "validation", asked)
        one = self.batch(1, "validation", whole)
        self.assertEqual((asked["split"], whole["split"]), (1, 1))
        self.assertEqual(split["result_sha"], one["result_sha"])
        self.assertEqual([(t["exit_reason"], t["pnl"]) for t in split["trades"]], [("settled", -160.55)])
        self.assertEqual(self.batch(2, "train", asked)["trades"][0]["exit_reason"], "split_mark")   # Train still splits
        self.assertEqual(asked["split"], 2)
        from league.swarm import settings
        self.assertEqual(settings.DEFAULTS["gym"]["validation_split"], 1)

    def test_warm_up_decides_but_never_trades(self):
        cfg = E.RunConfig(window="train", roots=("XSP",), start=self.D[2], end=self.D[3], warmup=5)
        [r] = E.run([R.load_program(HOLDER, name="h")], self.store, cfg)
        # Only D1 and D2 precede D3 in the window: two warm-up days, then D3's first decision is its third session.
        self.assertEqual([t["tag"] for t in r["trades"]], ["3"])
        self.assertEqual(len(r["daily"]), 2)                          # no daily rows for warm-up days
        self.assertEqual(r["fills"]["orders"], 1)                      # the warm-up's intents never became orders
        self.assertEqual(r["data_version"], self.store.data_version(["XSP"], self.D))   # warm-up files are part of the data
        [cold] = E.run([R.load_program(HOLDER, name="h")], self.store,
                       E.RunConfig(window="train", roots=("XSP",), start=self.D[2], end=self.D[3]))
        self.assertEqual([t["tag"] for t in cold["trades"]], ["1"])
        self.assertNotEqual(cold["run_id"], r["run_id"])


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
