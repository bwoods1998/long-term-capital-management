"""The fill model's calibration: rates counted by hand from a tiny synthetic day (the MLE, shrunk toward
coarser cells), Train only, exposure within the trade sample's band, the multi-leg hazard from complex
prints, the touch behind its queue, and the fitted table used by the engine. Synthetic data only."""

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
P = 100.0   # the shrinkage prior these tests use: pseudo side-minutes
FLOOR = 50.0  # the exposure floor these tests use (a day of one contract is 778 side-minutes)
# The one 0 DTE contract is quoted 09:31-15:59: 389 contract-minutes, each a resting buy and a resting sell. By time
# of day: to 10:30 59 minutes (118 side-minutes), to 15:00 270 (540), after 60 (120); 778 side-minutes in all.


def shrunk(hits, exposure, parent):
    """One cell's estimate: its hits and side-minutes, pulled toward its parent's rate by P pseudo side-minutes."""
    return round((hits + P * parent) / (exposure + P), 6)


def prints(rows):
    cols = {k: [] for k in ("expiration", "strike", "right", "ms_of_day", "price", "size", "condition", "exchange", "bid", "ask",
                            "bid_size", "ask_size")}
    for row in rows:
        minute, price, condition = row[:3]
        size = row[3] if len(row) > 3 else 1
        for k, v in (("expiration", D1), ("strike", 400.0), ("right", "C"), ("ms_of_day", minute * 60000 + 5000), ("price", price),
                     ("size", size), ("condition", condition), ("exchange", 1), ("bid", 1.00), ("ask", 1.10), ("bid_size", 10),
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
        table = CAL.fit(self.store, ["SPY"], days=[D1], prior=P, min_bucket=FLOOR)
        h = table["hazard"]
        # Level 0 (bucket q2): a resting buy at the mid meets the 10:00 print (at or below the mid); a resting sell
        # meets 10:00 and 10:10 (at or above the mid): 3 hits, all before 10:30. Every hit and minute is at 0 DTE and
        # at the money, so the pooled, DTE and moneyness levels all estimate 3/778; the time cells shrink toward it.
        pooled = 3 / 778
        self.assertEqual(h["SPY|q2|s|d0|k0|t0"], shrunk(3, 118, pooled))
        self.assertEqual(h["SPY|q2|s|d0|k0|t1"], shrunk(0, 540, pooled))    # no print after 10:30: small, never zero
        self.assertNotIn("SPY|q2|s|d0|k2|t0", h)                           # no exposure there: no cell, natural only
        # 1-2, 3-7 and 8+ days were never sampled here: no cells at all (natural fills only), never a neighbour's.
        self.assertEqual([k for k in h if "|d0|" not in k], [])
        self.assertEqual(F.FillModel.from_json(table).p("SPY", 0.0, [(10, 0.0)], 600), 0.0)
        # Every cell is SPY's: another root reads zero.
        self.assertEqual(F.FillModel.from_json(table).p("QQQ", 0.0, [(0, 0.0)], 600), 0.0)
        # Level 0.75 (q5): a buy at mid + 0.75 half-spreads meets the 10:00 print; a sell at mid - 0.75 meets both.
        self.assertEqual(h["SPY|q5|s|d0|k0|t0"], shrunk(3, 118, pooled))
        # Level -0.25 (q1): a buy below the mid meets nothing; a sell above it (mid + 0.25) meets the 10:10 print.
        self.assertEqual(h["SPY|q1|s|d0|k0|t0"], shrunk(1, 118, 1 / 778))
        # The touch (q0): the 10:10 print at the ask is 1 contract against 100 displayed: no fill, so no touch cells.
        self.assertFalse([k for k in h if k.startswith("SPY|q0|")])
        # Multi-leg: the 10:20 complex print at the mid (buy and sell side: 2 hits), from complex prints directly.
        self.assertEqual(h["SPY|q2|m|d0|k0|t0"], shrunk(2, 118, 2 / 778))
        # Monotone in the level: a limit nearer the natural never fills less often.
        for cell in ("d0|k0|t0", "d0|k0|t1", "d0|k0|t2"):
            rates = [h.get(f"SPY|q{q}|s|{cell}", 0.0) for q in range(6)]
            self.assertEqual(rates, sorted(rates), cell)
        # Size: every hit here traded one contract beyond the (empty, inside the spread) queue.
        self.assertEqual(table["size"]["SPY|q2|s|d0"], 1)
        meta = table["meta"]["fitted_on"]
        self.assertEqual((meta["prints"], meta["multi"], meta["stock_option"]), (3, 1, 1))  # the 138 print is a stock-option package
        self.assertEqual(table["meta"]["conditions"], {18: 2, 130: 1, 138: 1})

    def test_the_touch_counts_only_volume_through_the_displayed_queue(self):
        # The NBBO file shows 100 contracts on each side (flat_day's default size). At the bid, 10:00 prints 60 and
        # 40 (100 in all: the queue ahead, nothing left for a new order) and 10:05 prints 70 then 31 (101: one
        # contract reaches the order). At the ask, 10:10 prints 150 in one trade. Multi-leg: a complex print of
        # 101 at the bid at 10:20.
        w = synth.Writer(self.dir)
        w.trade_quote("SPY", D1, prints([(600, 1.00, 18, 60), (600, 1.00, 18, 40), (605, 1.00, 18, 70), (605, 0.99, 18, 31),
                                         (610, 1.10, 18, 150), (620, 1.00, 130, 101)]))
        table = CAL.fit(self.store, ["SPY"], days=[D1], prior=P, min_bucket=FLOOR)
        # Single-leg touch hits: 10:05 (a resting buy) and 10:10 (a resting sell); 10:00 is absorbed by the queue.
        self.assertEqual(table["hazard"]["SPY|q0|s|d0|k0|t0"], shrunk(2, 118, 2 / 778))
        # Multi-leg: one complex contract-minute through the queue.
        self.assertEqual(table["hazard"]["SPY|q0|m|d0|k0|t0"], shrunk(1, 118, 1 / 778))
        # Size beyond the queue: the single-leg touch fills found 1 (10:05) and 50 (10:10) contracts: the lower median, 1.
        self.assertEqual((table["size"]["SPY|q0|s|d0"], table["size"]["SPY|q0|m|d0"]), (1, 1))
        # A quarter-spread short of the mid (q1) there is no queue ahead: the buys found 100 (10:00) and 101 (10:05)
        # contracts, the sell 150 (10:10): the lower median, 101.
        self.assertEqual(table["size"]["SPY|q1|s|d0"], 101)
        self.assertEqual((CAL.lower_median(numpy.bincount([1, 50, 70])), CAL.lower_median(numpy.zeros(3, int))), (50, 1))
        # The touch is never credited more than a level inside the spread (q1, a quarter-spread short of the mid).
        self.assertLessEqual(table["hazard"]["SPY|q0|s|d0|k0|t0"], table["hazard"]["SPY|q1|s|d0|k0|t0"])
        # And the engine reads the fitted cell for a one-tick "mid" limit (q = -1).
        model = F.FillModel.from_json(table)
        self.assertEqual(model.p("SPY", -1.0, [(0, 0.0)], 600), table["hazard"]["SPY|q0|s|d0|k0|t0"])
        self.assertEqual(model.sizes("SPY", -1.0, [(0, 0.0)], [1]), [1])

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
        table = CAL.fit(self.store, ["SPY"], days=[D1], prior=P, min_bucket=FLOOR)
        # Same three single-leg side hits, twice the population (the put at the same strike is in the sample's
        # band and was quoted all day). No put print is needed.
        self.assertEqual(table["hazard"]["SPY|q2|s|d0|k0|t0"], shrunk(3, 236, 3 / 1556))

    def test_exposure_is_the_trade_samples_band_only(self):
        # Calls from 398 to 402 and 410 around 400.00, and a sample of one strike each side of the money: the
        # sample covered 399-401, widened to 402 where a print shows it was sampled. 398 and 410 never were, so
        # their quiet minutes are not counted as misses.
        w = synth.Writer(self.dir)
        synth.flat_day(w, "SPY", D1, [{"expiration": D1, "strike": k, "right": "C", "quotes": {571: (1.00, 1.10)}}
                                      for k in (398, 399, 400, 401, 402, 410)], prices=400.0)
        rows = prints([(600, 1.05, 18), (610, 1.10, 18)])
        rows["strike"] = [400.0, 400.0]
        extra = prints([(700, 1.05, 18)])
        for k in rows:
            rows[k] += extra[k]
        rows["strike"][-1] = 402.0
        w.trade_quote("SPY", D1, rows)
        table = CAL.fit(self.store, ["SPY"], days=[D1], prior=P, sample_strikes=1, min_bucket=FLOOR)
        self.assertEqual(table["meta"]["fitted_on"]["contract_minutes"], 4 * 389)
        # All four are within 0.5% of the money (402/400 is just under 1.005 in floating point). The 10:00 and 10:10
        # prints are 3 q2 hits before 10:30 and the 11:40 one 2 more: 5 of 4 x 778 side-minutes in all.
        pooled = 5 / (4 * 778)
        self.assertEqual(table["hazard"]["SPY|q2|s|d0|k0|t0"], shrunk(3, 4 * 118, pooled))
        self.assertEqual(table["hazard"]["SPY|q2|s|d0|k0|t1"], shrunk(2, 4 * 540, pooled))

    def test_shrinkage_by_hand(self):
        # SPY: two cells of DTE bucket 0 at the money, 100 side-minutes with 10 hits before 10:30 and 900 with none
        # later. QQQ: 1000 side-minutes before 10:30 with no hit. Every root pooled: 10 of 2000.
        code = lambda m: int(CAL._cells(numpy.array([0]), numpy.array([0.0]), numpy.array([m]))[0])  # noqa: E731
        exposure = {("SPY", code(600)): 100.0, ("SPY", code(700)): 900.0, ("QQQ", code(600)): 1000.0}
        hits = {("SPY", code(600)): 10.0}
        rates = CAL.shrink(exposure, hits, 100.0, 50.0)
        spy = (10 + 100 * 0.005) / 1100                                        # SPY's 10/1000, toward the pool's 0.005
        spy_d = (10 + 100 * spy) / 1100                                        # (SPY, d0): the same data, toward SPY's
        spy_dk = (10 + 100 * spy_d) / 1100                                     # (SPY, d0, k0): again
        self.assertAlmostEqual(rates["SPY", 0, 0, 0], (10 + 100 * spy_dk) / 200)
        self.assertAlmostEqual(rates["SPY", 0, 0, 1], (0 + 100 * spy_dk) / 1000)
        self.assertAlmostEqual(rates["SPY", 0, 0, 2], spy_dk)                  # no data there: the parent, not zero
        self.assertNotIn(("SPY", 0, 1, 0), rates)                              # another moneyness, never seen: no cells
        qqq = (0 + 100 * 0.005) / 1100                                         # QQQ never filled: pulled up by the pool only
        qqq_dk = (0 + 100 * ((0 + 100 * qqq) / 1100)) / 1100
        self.assertAlmostEqual(rates["QQQ", 0, 0, 0], (0 + 100 * qqq_dk) / 1100)
        self.assertLess(rates["QQQ", 0, 0, 0], 0.0005)
        self.assertNotIn(("SPY", 1, 0, 0), rates)                              # a DTE bucket never sampled: no cells
        self.assertNotIn(("IWM", 0, 0, 0), rates)                              # a root never sampled: no cells
        self.assertEqual(CAL.shrink({}, {}, 100.0), {})                        # no exposure at all: nothing to say

    def test_a_moneyness_bucket_below_the_floor_has_no_cells(self):
        # SPY at 0 DTE: 20000 side-minutes at the money with 200 hits (1%), and a far wing (over 3% out) sampled for
        # only 40 side-minutes with no hit. Without the floor the wing would take a rate pulled toward the 1% its
        # (root, dte) parent mostly measures at the money; with it, the wing has no cells: natural fills only.
        cells = lambda money: int(CAL._cells(numpy.array([0]), numpy.array([money]), numpy.array([600]))[0])  # noqa: E731
        exposure = {("SPY", cells(0.0)): 20000.0, ("SPY", cells(0.04)): 40.0}
        hits = {("SPY", cells(0.0)): 200.0}
        loose = CAL.shrink(exposure, hits, 600.0, 0.0)
        self.assertGreater(loose["SPY", 0, 3, 0], 0.005)                       # the optimism the floor removes
        floored = CAL.shrink(exposure, hits, 600.0, 6000.0)
        self.assertNotIn(("SPY", 0, 3, 0), floored)
        self.assertIn(("SPY", 0, 0, 0), floored)
        self.assertEqual(CAL.MIN_BUCKET, 6000.0)
        # A package with that wing as a leg reads zero, whatever its body's rate.
        table = {f"SPY|q2|{c}|d0|k{k}|t0": r for (_, d, k, t), r in floored.items() for c in "sm"}
        model = F.FillModel(hazard=table)
        self.assertGreater(model.p("SPY", 0.0, [(0, 0.0), (0, 0.0)], 600), 0.0)
        self.assertEqual(model.p("SPY", 0.0, [(0, 0.0), (0, 0.04)], 600), 0.0)

    def test_hits_need_the_corresponding_quote_and_a_known_spot(self):
        chain = self.store.chain("SPY", D1)
        chain.bid[600 - chain.open_min, :] = numpy.nan  # remove the mid print's quote exposure
        chain.underlying.price[610 - chain.open_min] = numpy.nan  # remove the ask print's spot
        with patch.object(self.store, "chain", return_value=chain):
            table = CAL.fit(self.store, ["SPY"], days=[D1], prior=P, min_bucket=FLOOR)
        self.assertEqual(table["meta"]["fitted_on"]["single"], 0)
        self.assertEqual([k for k in table["hazard"] if "|s|" in k], [])   # no single-leg print survived
        self.assertIn("SPY|q2|m|d0|k0|t0", table["hazard"])                     # the 10:20 complex print did

    def test_the_cli_writes_where_it_is_told_and_the_engine_uses_it(self):
        out = self.dir / "cal" / "fill_model.json"
        self.assertEqual(CAL.main(["--store", str(self.dir), "--roots", "SPY", "--out", str(out), "--prior", "100", "--min-bucket", "50"]), 0)
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
