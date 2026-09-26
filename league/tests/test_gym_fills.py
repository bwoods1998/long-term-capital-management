"""Honest fills: the minute after the decision, at the natural, capped by the quoted size; better
than natural only by the fill model's keyed draws (a trivial program edit cannot re-roll them); the
stress mode's 1.5x half-spread. Synthetic stores only."""

import datetime as dt
import shutil
import tempfile
import unittest

try:
    import numpy  # noqa: F401
    import pyarrow  # noqa: F401
    HAVE = True
except ImportError:  # pragma: no cover
    HAVE = False

if HAVE:
    from league.gym import engine as E
    from league.gym import fills as F
    from league.gym import runtime as R
    from league.gym import store as S
    from league.gym import synth

D1 = dt.date(2023, 3, 6)

OPENER = '''
NEEDS = {"roots": ["SPY"], "dte": [0, 3], "band": 0.2, "cadence": 5, "start": 600}
PARAMS = {"qty": 1, "limit": "natural", "tif": 0, "low": 400, "close_at": 0}
STATE = {"opened": False}
def decide(ctx):
    p = ctx.params
    if not STATE["opened"]:
        STATE["opened"] = True
        limit = p["limit"] if p["limit"] in ("natural", "mid") else {"mid": 1}
        return [{"open": "debit_vertical", "legs": [{"side": "long", "right": "C", "dte": 0, "strike": p["low"]},
                 {"side": "short", "right": "C", "dte": 0, "strike": p["low"] + 1}], "qty": p["qty"], "limit": limit,
                 "tif": p["tif"] or "day"}]
    if p["close_at"] and ctx.minute == p["close_at"]:
        return [{"close": pos["id"]} for pos in ctx.positions]
    return []
'''


def prog(name="opener", code=OPENER, **params):
    return R.load_program(code, name=name, params=params)


@unittest.skipUnless(HAVE, "numpy/pyarrow not installed (requirements-gym.txt)")
class HonestFills(unittest.TestCase):
    def make(self, contracts, prices=400.5):
        self.dir = tempfile.mkdtemp(prefix="gym-fills-")
        w = synth.Writer(self.dir)
        w.calendar([D1])
        synth.flat_day(w, "SPY", D1, contracts, prices=prices)
        w.finish()
        return S.Store(self.dir)

    def tearDown(self):
        shutil.rmtree(getattr(self, "dir", ""), ignore_errors=True)

    def run_one(self, store, program, **cfg):
        [r] = E.run([program], store, E.RunConfig(window="train", roots=("SPY",), **cfg))
        self.assertEqual(r["status"], "ok", r["runtime"])
        return r

    def test_fills_against_the_next_minute_not_the_decision_minute(self):
        # At 600 the natural is 2.10 - 1.40 = 0.70 (the limit); at 601 the long leg's ask is 2.30: natural 0.90,
        # so nothing fills at 601; at 610 the quotes return and the resting limit fills at 0.70.
        store = self.make([
            {"expiration": D1, "strike": 400, "right": "C", "quotes": {571: (2.00, 2.10), 601: (2.20, 2.30), 610: (2.00, 2.10)}},
            {"expiration": D1, "strike": 401, "right": "C", "quotes": {571: (1.40, 1.50)}}])
        [t] = self.run_one(store, prog())["trades"]
        self.assertEqual((t["entry"], t["filled_minute"]), (0.70, 610))

    def test_price_improvement_at_arrival_fills_at_the_new_natural(self):
        store = self.make([
            {"expiration": D1, "strike": 400, "right": "C", "quotes": {571: (2.00, 2.10), 601: (1.90, 2.00)}},
            {"expiration": D1, "strike": 401, "right": "C", "quotes": {571: (1.40, 1.50)}}])
        [t] = self.run_one(store, prog())["trades"]
        self.assertEqual((t["entry"], t["filled_minute"]), (0.60, 601))

    def test_size_is_capped_by_the_quoted_size(self):
        store = self.make([
            {"expiration": D1, "strike": 400, "right": "C", "quotes": {571: (2.00, 2.10)}, "size": 3},
            {"expiration": D1, "strike": 401, "right": "C", "quotes": {571: (1.40, 1.50)}}])
        r = self.run_one(store, prog(qty=5))
        [t] = r["trades"]
        self.assertEqual(t["qty"], 5)
        self.assertEqual(r["fills"]["fills"], 2 + 1)      # 3 at 601, 2 at 602, then the window-end close
        self.assertEqual(r["fills"]["partial_fills"], 1)

    def test_a_mid_order_does_not_fill_without_a_calibrated_model(self):
        store = self.make([
            {"expiration": D1, "strike": 400, "right": "C", "quotes": {571: (2.00, 2.10)}},
            {"expiration": D1, "strike": 401, "right": "C", "quotes": {571: (1.40, 1.50)}}])
        r = self.run_one(store, prog(limit="mid", tif=30))
        self.assertEqual(r["summary"]["trades"], 0)
        self.assertEqual(r["fills"]["expired"], 1)

    def test_calibrated_fills_are_keyed_by_contract_and_minute_not_the_program(self):
        contracts = []
        for k in (399, 400, 401):
            contracts.append({"expiration": D1, "strike": k, "right": "C",
                              "quotes": {571: (2.00 - 0.6 * (k - 400), 2.10 - 0.6 * (k - 400))}})
        store = self.make(contracts)
        model = F.FillModel(hazard={F.cell(q, 2, 0, m, t): 0.05 for q in (0.1,) for m in (0.0, 0.01, 0.02, 0.04)
                                    for t in (600, 700, 950)}, source="test")
        a = self.run_one(store, prog(limit="mid1"), fill_model=model)
        edited = OPENER.replace("STATE = {", "# a comment the researcher added\nSTATE = {").replace(
            '"close_at": 0}', '"close_at": 0, "unused": 3}')
        b = self.run_one(store, prog(name="edited", code=edited, limit="mid1"), fill_model=model)
        [ta], [tb] = a["trades"], b["trades"]
        self.assertNotEqual(a["run_sha"], b["run_sha"])
        self.assertEqual((ta["filled_minute"], ta["entry"]), (tb["filled_minute"], tb["entry"]))
        self.assertGreater(ta["filled_minute"], 601)       # it waited for its draw
        self.assertLess(ta["entry"], 0.70)                  # and filled better than the natural
        other = self.run_one(store, prog(limit="mid1", low=399), fill_model=model)
        [to] = other["trades"]
        self.assertNotEqual(to["filled_minute"], ta["filled_minute"])  # other contracts, other draws

    def test_draws_are_keyed_and_uniform(self):
        u = F.draw([11, 22], 19422, 601, "buy")
        self.assertEqual(u, F.draw([22, 11], 19422, 601, "buy"))
        self.assertNotEqual(u, F.draw([11, 22], 19422, 602, "buy"))
        self.assertNotEqual(u, F.draw([11, 22], 19422, 601, "sell"))
        xs = [F.draw([1], 1, m, "buy") for m in range(2000)]
        self.assertTrue(all(0.0 <= x < 1.0 for x in xs))
        self.assertAlmostEqual(sum(xs) / len(xs), 0.5, delta=0.03)
        self.assertEqual(F.FillModel().p(0.2, 2, 0, 0.0, 700), 0.0)  # the default: natural only
        self.assertEqual(F.FillModel().p(1.0, 2, 0, 0.0, 700), 1.0)

    def test_stress_widens_every_half_spread(self):
        store = self.make([
            {"expiration": D1, "strike": 400, "right": "C", "quotes": {571: (2.00, 2.10)}},
            {"expiration": D1, "strike": 401, "right": "C", "quotes": {571: (1.40, 1.50)}}])
        plain = self.run_one(store, prog(close_at=700))["trades"][0]
        stressed = self.run_one(store, prog(close_at=700), stress=1.5)["trades"][0]
        # Mids 2.05 and 1.45, half-spreads 0.05 -> 0.075: open at 2.125 - 1.375 = 0.75; close at 1.975 - 1.525 = 0.45.
        self.assertEqual((plain["entry"], plain["exit"]), (0.70, 0.50))
        self.assertEqual((stressed["entry"], stressed["exit"]), (0.75, 0.45))
        self.assertLess(stressed["pnl"], plain["pnl"])


if __name__ == "__main__":
    unittest.main()
