"""A `long_single` family's program in the Gym (Sept 29, 2026): ONE program that buys a long call on one rule and a long put
on another. The Gym runs programs, never families: nothing in `league/gym` reads a family's declared structure (the
engine, the batch driver and the swarm's Gym job carry code, parameters, roots and a window only), so a program's intents
are judged one by one by their own type, as the House's classifier and the venue rules judge them. The engine needs no
change for `long_single`, and none is made: any edit under `league/gym` would move the Gym bundle's version and send every
validated family back through Validation.

Every store here is synthetic and tiny (`league.gym.synth`); the expected numbers are worked out by hand from the quotes
written. Skips cleanly when numpy or pyarrow is absent (requirements-gym.txt)."""

import datetime as dt
import inspect
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
    from league.gym import runtime as R
    from league.gym import store as S
    from league.gym import synth

REPO = Path(__file__).resolve().parents[2]
D1 = dt.date(2023, 3, 6)

# The side rule here is a clock (a call first, a put ten minutes later) so the test's numbers are by hand; a real family's
# rule is its mechanism's, stated in its notebook.
LONG_SINGLE = '''
NEEDS = {"roots": ["SPY"], "dte": [0, 3], "band": 0.2, "cadence": 5, "start": 600}
PARAMS = {}
STATE = {"sent": 0}
def decide(ctx):
    out = []
    if ctx.minute == 600 and STATE["sent"] == 0:
        STATE["sent"] = 1
        out.append({"open": "long_call", "legs": [{"side": "long", "right": "C", "dte": 0, "strike": 401}], "qty": 1,
                    "tag": "up"})
    elif ctx.minute == 610 and STATE["sent"] == 1:
        STATE["sent"] = 2
        out.append({"open": "long_put", "legs": [{"side": "long", "right": "P", "dte": 0, "strike": 399}], "qty": 2,
                    "tag": "down"})
    if ctx.minute == 720:
        out += [{"close": p["id"]} for p in ctx.positions]
    return out
'''


@unittest.skipUnless(HAVE, "numpy/pyarrow not installed (requirements-gym.txt)")
class LongSingleInTheGym(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="gym-long-single-")
        w = synth.Writer(self.dir)
        w.calendar([D1])
        synth.flat_day(w, "SPY", D1, [
            {"expiration": D1, "strike": 401, "right": "C", "quotes": {571: (1.00, 1.05), 700: (1.50, 1.55)}},
            {"expiration": D1, "strike": 399, "right": "P", "quotes": {571: (0.80, 0.85), 700: (0.60, 0.65)}},
        ], prices=400.0)
        w.finish()
        self.store = S.Store(self.dir)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def run_program(self, code):
        [result] = E.run([R.load_program(code, name="two-sided")], self.store, E.RunConfig(window="train", roots=("SPY",)))
        self.assertEqual(result["status"], "ok", result["runtime"])
        return result

    def test_one_program_opens_a_long_call_and_a_long_put_each_as_its_own_type(self):
        r = self.run_program(LONG_SINGLE)
        trades = sorted(r["trades"], key=lambda t: t["tag"])
        self.assertEqual([(t["type"], t["tag"], t["qty"]) for t in trades], [("long_put", "down", 2), ("long_call", "up", 1)])
        put, call = trades
        # The call: decision 600, filled at 601 at its ask 1.05; closed at 721 at its bid 1.50. One long leg: its maximum
        # loss is its premium (105 a contract), its own unit.
        self.assertEqual((call["entry"], call["exit"], call["max_loss"]), (1.05, 1.50, 105.0))
        # The put: decision 610, filled at 611 at its ask 0.85, two contracts; closed at 721 at its bid 0.60.
        self.assertEqual((put["entry"], put["exit"], put["max_loss"]), (0.85, 0.60, 170.0))
        self.assertEqual(r["fills"]["reject_reasons"], {}, "neither side was refused")
        # Each trade's maximum loss is its own: the median per structure the live path's typical unit reads mixes both.
        self.assertEqual(r["summary"]["median_max_loss_per_structure"], round((105.0 + 85.0) / 2, 2))

    def test_the_gym_never_reads_a_familys_declared_structure(self):
        # The run's inputs: programs (code, NEEDS, PARAMS), a store and a RunConfig (window, roots, ...). None of them has a
        # structure, so there is nothing for a family's declared type to be checked against, and nothing to change.
        self.assertNotIn("structure", inspect.signature(E.run).parameters)
        self.assertNotIn("structure", {f for f in E.RunConfig.__dataclass_fields__})
        for path in (REPO / "league" / "gym").glob("*.py"):
            text = path.read_text(encoding="utf-8")
            for word in ("long_single", "family_structure", '["structure"]', "get(\"structure\")"):
                self.assertNotIn(word, text, f"{path.name} reads a family's structure")

    def test_a_long_single_intent_is_refused_as_an_order_type(self):
        # A family's declared structure is never an order type: an intent naming it opens nothing.
        code = LONG_SINGLE.replace('"open": "long_call"', '"open": "long_single"')
        r = self.run_program(code)
        self.assertEqual([t["type"] for t in r["trades"]], ["long_put"])
        self.assertTrue(r["fills"]["reject_reasons"], "the long_single intent was refused")


if __name__ == "__main__":
    unittest.main()
