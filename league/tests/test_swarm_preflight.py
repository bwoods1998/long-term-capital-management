"""The preflight (league/swarm/preflight.py): agent API misuse is refused on a synthetic session before a Train run is
spent, and nothing that would run in the Gym is (no false refusals: every seed and example program passes)."""

from __future__ import annotations

import copy
import json
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

    def test_arithmetic_on_a_none(self):
        out = self.refused(program('x = ctx.params.get("missing") / 2.0\nreturn []'))
        self.assertIn("NoneType", out["error"])
        self.assertIn("is None", out["hint"])
        self.assertIn("k", out["hint"])  # the program's PARAMS keys are named

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
        out = self.check(program("t = 0\nfor i in range(10 ** 8):\n    t += i\nreturn []"), timeout=0.05)
        self.assertEqual(out["status"], "inconclusive", out)

    def test_a_numpy_api_error_is_inconclusive(self):
        # The House's numpy is not the Gym boxes' (requirements-gym.txt): an API one has and the other lacks says nothing.
        code = "import numpy as np\n" + program("x = np.not_in_this_numpy(1.0)\nreturn []")
        out = self.check(code)
        self.assertEqual(out["status"], "inconclusive", out)

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
        code = program('xs = [1.0, 2.0]\nv = xs[int(ctx.params["k"])]\nreturn []')
        self.steps = [{"calls": [("gym_sweep", {"code": code, "variants": [{"k": 0.0}, {"k": 5.0}]})]}, {"text": "ok"}]
        out = self.make().cycle(self.fam["id"])
        answer = self.answer()
        self.assertEqual((answer.get("status"), answer.get("stage")), ("refused", "preflight"), answer)
        self.assertEqual(answer["variant"], {"k": 5.0})
        self.assertIn("IndexError", answer["error"])
        self.assertEqual(len(self.pool.jobs), 1)
        self.assertEqual(out.get("preflight_refused"), 1)


if __name__ == "__main__":
    unittest.main()
