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

SINGLE = OPENER.replace('"open": "debit_vertical"', '"open": "long_call"').replace(
    ',\n                 {"side": "short", "right": "C", "dte": 0, "strike": p["low"] + 1}]', "]")


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
        model = synth.uniform_model(0.05, ("SPY",), levels=(2,), size=10)
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

    def test_a_mid_limit_on_a_one_tick_spread_is_the_touch_and_fills_by_the_touch_cell(self):
        # SPY 400C quoted 1.00 x 1.01: the mid 1.005 is off the penny, so "mid" is the bid (q = -1, the touch).
        store = self.make([{"expiration": D1, "strike": 400, "right": "C", "quotes": {571: (1.00, 1.01)}}])
        mid = prog(name="touch", code=SINGLE, limit="mid", tif=60)
        cells = lambda q: {F.cell("SPY", q, 1, 0, 0.0, t): 0.2 for t in (600, 700, 950)}  # noqa: E731
        # A table without the touch bucket (fitted before it existed) never fills it: no neighbour's rate.
        old = self.run_one(store, mid, fill_model=F.FillModel(hazard={**cells(-0.1), **cells(0.1)}, source="old"))
        self.assertEqual((old["summary"]["trades"], old["fills"]["expired"]), (0, 1))
        touch = self.run_one(store, mid, fill_model=F.FillModel(hazard=cells(-1.0), source="touch"))
        [t] = touch["trades"]
        self.assertEqual(t["entry"], 1.00)                  # filled at its limit, the bid
        self.assertGreater(t["filled_minute"], 601)         # after waiting for its keyed draw
        # The same draws again: a second run fills on the same minute.
        again = self.run_one(store, mid, fill_model=F.FillModel(hazard=cells(-1.0), source="touch"))
        self.assertEqual(again["trades"][0]["filled_minute"], t["filled_minute"])

    def test_the_touch_cell_and_behind_it(self):
        model = F.FillModel(hazard={F.cell("SPY", -1.0, 1, 0, 0.0, 700): 0.3}, source="t")
        self.assertEqual(F.q_bucket(-1.0), 0)
        self.assertEqual(F.q_bucket(-0.3), 0)
        atm = [(0, 0.0)]
        self.assertEqual(model.p("SPY", -1.0 - 1e-9, atm, 700), 0.3)   # float noise at the touch is the touch
        self.assertEqual(model.p("SPY", -0.5, atm, 700), 0.3)          # inside the spread: the touch's (lower) rate
        self.assertEqual(model.p("SPY", -1.2, atm, 700), 0.0)          # behind the touch: only the market fills it
        self.assertEqual(model.p("SPY", -1.0, atm * 2, 700), 0.0)      # a package needs its own (complex) cells
        self.assertEqual(model.p("QQQ", -1.0, atm, 700), 0.0)          # another root's cells are not this root's

    def test_a_passive_fill_still_waits_for_an_unfavourable_next_minute(self):
        # 1.00 x 1.01 on even minutes, 1.01 x 1.02 on odd ones. A buy resting at 1.00 is at the touch only on an
        # even minute, and the next minute's mid is always higher then: a fill there would be just before the
        # market moves its way, so even a certain touch cell never fills it (on odd minutes it is behind the touch).
        quotes = {m: (1.00, 1.01) if m % 2 == 0 else (1.01, 1.02) for m in range(571, 700)}
        store = self.make([{"expiration": D1, "strike": 400, "right": "C", "quotes": quotes}])
        self.addCleanup(shutil.rmtree, self.dir, True)
        model = F.FillModel(hazard={F.cell("SPY", -1.0, 1, 0, 0.0, t): 1.0 for t in (600, 700)}, source="certain")
        r = self.run_one(store, prog(name="rising", code=SINGLE, limit="mid", tif=60), fill_model=model)
        self.assertEqual((r["summary"]["trades"], r["fills"]["expired"]), (0, 1))
        flat = self.make([{"expiration": D1, "strike": 400, "right": "C", "quotes": {571: (1.00, 1.01)}}])
        [t] = self.run_one(flat, prog(name="flat", code=SINGLE, limit="mid", tif=60), fill_model=model)["trades"]
        self.assertEqual((t["entry"], t["filled_minute"]), (1.00, 601))   # the same cell, a flat next minute: filled

    def test_a_package_takes_its_lowest_leg_each_at_its_own_cell_capped_by_the_single_leg_rate(self):
        near, far = (0, 0.001), (0, 0.02)                     # k0 and k2 (1.5-3% from the money)
        hazard = {F.cell("SPY", 0.1, 2, 0, 0.001, 700): 0.30, F.cell("SPY", 0.1, 1, 0, 0.001, 700): 0.20,
                  F.cell("SPY", 0.1, 2, 0, 0.02, 700): 0.05, F.cell("SPY", 0.1, 1, 0, 0.02, 700): 0.40}
        model = F.FillModel(hazard=hazard, source="t")
        self.assertEqual(model.p("SPY", 0.1, [near, far], 700), 0.05)   # the far leg's complex rate is the lowest
        self.assertEqual(model.p("SPY", 0.1, [near, near], 700), 0.20)  # 0.30 complex capped by the leg's 0.20 single
        self.assertEqual(model.p("SPY", 0.1, [near], 700), 0.20)        # one leg: its single-leg cell
        # A leg 8 or more days out is never modelled, whatever the table holds: natural fills only.
        hazard[F.cell("SPY", 0.1, 2, 9, 0.001, 700)] = hazard[F.cell("SPY", 0.1, 1, 9, 0.001, 700)] = 0.5
        self.assertEqual(F.FillModel(hazard=hazard).p("SPY", 0.1, [near, (9, 0.001)], 700), 0.0)
        self.assertEqual(model.p("SPY", 0.1, [near, (0, float("nan"))], 700), 0.0)  # moneyness unknown: none

    def test_a_calendar_with_a_back_leg_past_seven_days_fills_only_at_the_natural(self):
        store = self.make([
            {"expiration": D1, "strike": 400, "right": "C", "quotes": {571: (1.00, 1.10)}},
            {"expiration": D1 + dt.timedelta(days=9), "strike": 400, "right": "C", "quotes": {571: (3.00, 3.10)}}])
        code = SINGLE.replace('"open": "long_call", "legs": [{"side": "long", "right": "C", "dte": 0, "strike": p["low"]}]',
                              '"open": "calendar", "legs": [{"side": "short", "right": "C", "dte": 0, "strike": p["low"]}, '
                              '{"side": "long", "right": "C", "dte": 9, "strike": p["low"]}]').replace('"dte": [0, 3]', '"dte": [0, 9]')
        r = self.run_one(store, prog(name="cal", code=code, limit="mid", tif=60), fill_model=synth.uniform_model(1.0, ("SPY",)))
        self.assertEqual((r["fills"]["opens"], r["summary"]["trades"], r["fills"]["expired"]), (1, 0, 1))

    def test_a_passive_fill_takes_the_modelled_size_and_orders_share_a_minutes_liquidity(self):
        store = self.make([{"expiration": D1, "strike": 400, "right": "C", "quotes": {571: (1.00, 1.01)}}])
        # Two contracts beyond the queue at the touch a minute: 5 lots fill 2, 2, 1 at 601, 602, 603.
        model = synth.uniform_model(1.0, ("SPY",), levels=(0,), classes=("s",), size=2)
        r = self.run_one(store, prog(name="big", code=SINGLE, limit="mid", tif=60, qty=5), fill_model=model)
        [t] = r["trades"]
        self.assertEqual((t["qty"], t["entry"], t["filled_minute"]), (5, 1.00, 601))
        self.assertEqual((r["fills"]["fills"], r["fills"]["partial_fills"]), (3 + 1, 1))   # and the window-end close
        # Unknown size: one structure a minute.
        bare = F.FillModel(hazard=model.hazard, source="no sizes")
        r = self.run_one(store, prog(name="bare", code=SINGLE, limit="mid", tif=60, qty=3), fill_model=bare)
        self.assertEqual(r["fills"]["fills"], 3 + 1)
        # Two orders on the same contract in the same minute share its 3 contracts: 2 + 1 at 601, the last at 602.
        both = SINGLE.replace('return [{"open": "long_call"', 'return [{"open": "long_call", "tag": "b"').replace(
            '"tif": p["tif"] or "day"}]', '"tif": p["tif"] or "day"}] * 2')
        model3 = synth.uniform_model(1.0, ("SPY",), levels=(0,), classes=("s",), size=3)
        r = self.run_one(store, prog(name="two", code=both, limit="mid", tif=60, qty=2), fill_model=model3)
        self.assertEqual(sorted(t["filled_minute"] for t in r["trades"]), [601, 601])
        self.assertEqual(r["fills"]["fills"], 3 + 2)

    def test_stress_widens_what_a_fill_costs_never_which_limits_can_fill(self):
        store = self.make([{"expiration": D1, "strike": 400, "right": "C", "quotes": {571: (1.00, 1.10)}}])
        model = synth.uniform_model(1.0, ("SPY",), levels=(0,), classes=("s",), size=10)
        behind = SINGLE.replace('limit = p["limit"] if p["limit"] in ("natural", "mid") else {"mid": 1}',
                                'limit = {"price": 0.99} if p["limit"] == "behind" else {"price": 1.00}')
        # 0.99 is behind the 1.00 bid (q = -1.2 on the real quotes; it would be -0.8 against the 1.5x-stressed spread).
        for stress in (1.0, 1.5):
            r = self.run_one(store, prog(name="behind", code=behind, limit="behind", tif=60), fill_model=model, stress=stress)
            self.assertEqual(r["summary"]["trades"], 0, stress)
        # At the touch it fills, and under stress pays the extra half-spread: 1.00 + 0.5 x 0.05.
        r = self.run_one(store, prog(name="touch", code=behind, limit="touch", tif=60), fill_model=model, stress=1.5)
        self.assertEqual(r["trades"][0]["entry"], 1.025)

    def test_draws_are_keyed_and_uniform(self):
        u = F.draw([11, 22], 19422, 601, "buy")
        self.assertEqual(u, F.draw([22, 11], 19422, 601, "buy"))
        self.assertNotEqual(u, F.draw([11, 22], 19422, 602, "buy"))
        self.assertNotEqual(u, F.draw([11, 22], 19422, 601, "sell"))
        xs = [F.draw([1], 1, m, "buy") for m in range(2000)]
        self.assertTrue(all(0.0 <= x < 1.0 for x in xs))
        self.assertAlmostEqual(sum(xs) / len(xs), 0.5, delta=0.03)
        self.assertEqual(F.FillModel().p("SPY", 0.2, [(0, 0.0)] * 2, 700), 0.0)  # the default: natural only
        self.assertEqual(F.FillModel().p("SPY", 1.0, [(0, 0.0)] * 2, 700), 1.0)

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
