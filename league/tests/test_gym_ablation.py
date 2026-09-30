"""Known synthetic opportunity: a real fill disappears under a global/default-captured ablation.

This is an execution-contract benchmark, not market alpha evidence. The existing future/fill and
package-bound suites test leakage and invalid fills; this control tests parameter causality through
the full replay path instead of merely inspecting a merged configuration dict.
"""

import datetime as dt
import tempfile
import unittest

try:
    import numpy  # noqa: F401
    import pyarrow  # noqa: F401
    HAVE = True
except ImportError:  # pragma: no cover
    HAVE = False


PROGRAM = """
NEEDS = {'roots': ['SPY'], 'dte': [0, 3], 'band': 0.1, 'cadence': 5, 'start': 600}
PARAMS = {'signal_on': 1}
P = PARAMS
STATE = {'opened': False}
def enabled(flag=P['signal_on']):
    return flag
def decide(ctx):
    if not enabled():
        return []
    if not STATE['opened']:
        STATE['opened'] = True
        return [{'open': 'debit_vertical', 'root': 'SPY', 'legs': [
            {'side': 'long', 'right': 'C', 'dte': 1, 'strike': 400},
            {'side': 'short', 'right': 'C', 'dte': 1, 'strike': 405}], 'qty': 1, 'limit': 'natural'}]
    if ctx.minute >= 700 and ctx.positions and not ctx.orders:
        return [{'close': ctx.positions[0]['id'], 'limit': 'natural'}]
    return []
"""


@unittest.skipUnless(HAVE, "numpy/pyarrow not installed (requirements-gym.txt)")
class ReplayAblation(unittest.TestCase):
    def test_the_off_control_removes_actual_trades_and_independent_reruns_are_identical(self):
        from league.gym import engine, runtime, store, synth

        first, expiry = dt.date(2023, 3, 6), dt.date(2023, 3, 7)
        with tempfile.TemporaryDirectory(prefix="gym-ablation-") as root:
            writer = synth.Writer(root)
            writer.calendar([first])
            synth.flat_day(writer, "SPY", first, [
                {"expiration": expiry, "strike": 400, "right": "C", "quotes": {571: (2.0, 2.1), 700: (3.0, 3.1)}},
                {"expiration": expiry, "strike": 405, "right": "C", "quotes": {571: (1.0, 1.1)}},
            ], prices=400.5)
            writer.finish()
            data = store.Store(root)
            cfg = engine.RunConfig(window="train", roots=("SPY",))
            on = runtime.load_program(PROGRAM, name="causal-control", params={"signal_on": 1})
            off = runtime.load_program(PROGRAM, name="causal-control", params={"signal_on": 0})
            [baseline] = engine.run([on], data, cfg)
            [ablated] = engine.run([off], data, cfg)
            [repeat] = engine.run([on], data, cfg)

        self.assertEqual((baseline["status"], ablated["status"], repeat["status"]), ("ok", "ok", "ok"))
        self.assertEqual((baseline["summary"]["trades"], ablated["summary"]["trades"]), (1, 0))
        self.assertEqual((baseline["fills"]["opens"], ablated["fills"]["opens"]), (1, 0))
        [trade] = baseline["trades"]
        self.assertEqual((trade["entry"], trade["exit"], trade["filled_minute"]), (1.1, 1.9, 601))
        self.assertAlmostEqual(trade["pnl"], 80.0 - trade["fees"], places=6)
        self.assertEqual(ablated["summary"]["pnl"], 0.0)
        self.assertEqual(baseline["result_sha"], repeat["result_sha"])
        self.assertNotEqual(baseline["run_id"], ablated["run_id"])


if __name__ == "__main__":
    unittest.main()
