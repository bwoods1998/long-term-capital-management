"""The fill model's calibration: rates counted by hand from a tiny synthetic day, Train only, the
multi-leg hazard halved and capped, and the fitted table used by the engine. Synthetic data only."""

import datetime as dt
import json
import shutil
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

try:
    import numpy  # noqa: F401
    import pyarrow  # noqa: F401
    HAVE = True
except ImportError:  # pragma: no cover
    HAVE = False

if HAVE:
    from league.gym import calibrate as CAL
    from league.gym import engine as E
    from league.gym import fills as F
    from league.gym import runtime as R
    from league.gym import store as S
    from league.gym import synth

D1 = dt.date(2023, 3, 6)
DV = dt.date(2025, 3, 3)


def prints(rows):
    cols = {k: [] for k in ("expiration", "strike", "right", "ms_of_day", "price", "size", "condition", "exchange", "bid", "ask",
                            "bid_size", "ask_size")}
    for minute, price, condition in rows:
        for k, v in (("expiration", D1), ("strike", 400.0), ("right", "C"), ("ms_of_day", minute * 60000 + 5000), ("price", price),
                     ("size", 1), ("condition", condition), ("exchange", 1), ("bid", 1.00), ("ask", 1.10), ("bid_size", 10),
                     ("ask_size", 10)):
            cols[k].append(v)
    return cols


@unittest.skipUnless(HAVE, "numpy/pyarrow not installed (requirements-gym.txt)")
class Calibration(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="gym-cal-"))
        w = synth.Writer(self.dir)
        w.calendar([D1, DV])
        synth.flat_day(w, "SPY", D1, [{"expiration": D1, "strike": 400, "right": "C", "quotes": {571: (1.00, 1.10)}}], prices=400.0)
        # At 10:00 a print at the mid; at 10:10 one at the ask; at 10:20 a multi-leg print at the mid.
        w.trade_quote("SPY", D1, prints([(600, 1.05, 18), (610, 1.10, 18), (620, 1.05, 130), (625, 1.05, 138)]))
        synth.flat_day(w, "SPY", DV, [{"expiration": DV, "strike": 400, "right": "C", "quotes": {571: (1.00, 1.10)}}], prices=400.0)
        w.finish()
        self.store = S.Store(self.dir)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_rates_counted_by_hand(self):
        table = CAL.fit(self.store, ["SPY"], days=[D1], min_exposure=10)
        # Exposure of the (0 DTE, at the money, to 10:30) cell: minutes 09:31..10:29 quoted = 59, twice (buys, sells).
        # Level 0 (bucket q2): a resting buy at the mid meets the 10:00 print (at or below the mid); a resting sell
        # meets 10:00 and 10:10 (at or above the mid): 3 hits of 118.
        single = CAL.wilson_lower(3, 118)
        self.assertAlmostEqual(table["hazard"]["q2|s|d0|k0|t0"], round(single, 6))
        # Level 0.75 (q5): a buy at mid + 0.75 half-spreads meets the 10:00 print; a sell at mid - 0.75 meets both.
        self.assertAlmostEqual(table["hazard"]["q5|s|d0|k0|t0"], round(CAL.wilson_lower(3, 118), 6))
        # Level -0.25 (q1): a buy below the mid meets nothing; a sell above it (mid + 0.25) meets the 10:10 print.
        self.assertAlmostEqual(table["hazard"]["q1|s|d0|k0|t0"], round(CAL.wilson_lower(1, 118), 6))
        # Multi-leg: the 10:20 complex print (buy and sell side: 2 hits), halved, never above single.
        self.assertAlmostEqual(table["hazard"]["q2|m|d0|k0|t0"], round(min(single, 0.5 * CAL.wilson_lower(2, 118)), 6))
        meta = table["meta"]["fitted_on"]
        self.assertEqual((meta["prints"], meta["multi"], meta["stock_option"]), (3, 1, 1))  # the 138 print is a stock-option package
        self.assertEqual(table["meta"]["conditions"], {18: 2, 130: 1, 138: 1})

    def test_train_only(self):
        with self.assertRaises(S.StoreRefused):
            CAL.fit(self.store, ["SPY"], days=[DV])
        with self.assertRaises(S.StoreRefused):
            self.store.trade_quote("SPY", DV)

    def test_zero_print_contracts_remain_in_the_exposure(self):
        w = synth.Writer(self.dir)
        synth.flat_day(w, "SPY", D1, [
            {"expiration": D1, "strike": 400, "right": "C", "quotes": {571: (1.00, 1.10)}},
            {"expiration": D1, "strike": 400, "right": "P", "quotes": {571: (1.00, 1.10)}},
        ], prices=400.0)
        table = CAL.fit(self.store, ["SPY"], days=[D1], min_exposure=10)
        # Same three single-leg side hits, twice the population. No put print is needed.
        self.assertAlmostEqual(table["hazard"]["q2|s|d0|k0|t0"], round(CAL.wilson_lower(3, 236), 6))

    def test_hits_need_the_corresponding_quote_and_a_known_spot(self):
        chain = self.store.chain("SPY", D1)
        chain.bid[600 - chain.open_min, :] = numpy.nan  # remove the mid print's quote exposure
        chain.underlying.price[610 - chain.open_min] = numpy.nan  # remove the ask print's spot
        with patch.object(self.store, "chain", return_value=chain):
            table = CAL.fit(self.store, ["SPY"], days=[D1], min_exposure=10)
        self.assertEqual(table["meta"]["fitted_on"]["single"], 0)
        self.assertEqual(table["hazard"], {})

    def test_the_cli_writes_where_it_is_told_and_the_engine_uses_it(self):
        out = self.dir / "cal" / "fill_model.json"
        self.assertEqual(CAL.main(["--store", str(self.dir), "--roots", "SPY", "--out", str(out), "--min-exposure", "10"]), 0)
        self.assertEqual(out.stat().st_mode & 0o777, 0o600)
        model = F.FillModel.load(out)
        self.assertNotEqual(model.version, "natural-only")
        self.assertEqual(model.source, str(out))
        program = R.load_program('''
NEEDS = {"roots": ["SPY"], "dte": [0, 1], "band": 0.2, "cadence": 5}
PARAMS = {}
def decide(ctx):
    if not ctx.positions and not ctx.orders and ctx.minute == 576:
        return [{"open": "long_call", "legs": [{"side": "long", "right": "C", "dte": 0, "strike": 400}], "qty": 1, "limit": "mid"}]
    return []
''')
        [natural_only] = E.run([program], self.store, E.RunConfig(window="train", roots=("SPY",)), days=[D1])
        self.assertEqual(natural_only["summary"]["trades"], 0)
        boosted = F.FillModel(hazard={k: min(1.0, v * 20) for k, v in model.hazard.items()}, source="x20")
        [calibrated] = E.run([program], self.store, E.RunConfig(window="train", roots=("SPY",), fill_model=boosted), days=[D1])
        self.assertEqual(calibrated["summary"]["trades"], 1)
        self.assertEqual(calibrated["trades"][0]["entry"], 1.05)   # filled at its limit, the mid
        self.assertNotEqual(calibrated["fill_model"], natural_only["fill_model"])


if __name__ == "__main__":
    unittest.main()
