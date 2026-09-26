"""The store reader and the greeks: grids built from store-v1 files exactly, no minute borrowed from
the future, and Black-Scholes inverted accurately. Synthetic stores only."""

import datetime as dt
import math
import shutil
import tempfile
import unittest

try:
    import numpy as np
    import pyarrow  # noqa: F401
    HAVE = True
except ImportError:  # pragma: no cover
    HAVE = False

if HAVE:
    from league.gym import ctx as C
    from league.gym import events as EV
    from league.gym import greeks as G
    from league.gym import store as S
    from league.gym import synth

D1, D2 = dt.date(2024, 3, 14), dt.date(2024, 3, 15)


@unittest.skipUnless(HAVE, "numpy/pyarrow not installed (requirements-gym.txt)")
class TheStore(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="gym-store-")
        w = synth.Writer(self.dir)
        w.calendar([D1, D2])
        # Written deliberately out of order: the reader must sort by (expiry, strike, right, minute).
        w.nbbo("SPY", D1, expiration=[D2, D1, D1, D1, D2], strike=[401.0, 400.0, 400.0, 400.0, 401.0],
               right=["P", "C", "C", "P", "P"], minute=[572, 572, 571, 571, 571], bid=[1.0, 2.1, 2.0, 1.5, 0.9],
               ask=[1.1, 2.2, 2.1, 1.6, 1.0], bid_size=[1, 2, 3, 4, 5], ask_size=[6, 7, 8, 9, 10])
        w.underlying("SPY", D1, [571, 572, 600], [400.0, 401.0, 402.0])
        w.oi("SPY", D1, expiration=[D2, D1], strike=[401.0, 400.0], right=["P", "C"], open_interest=[77, 55])
        w.finish()
        self.store = S.Store(self.dir)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_chain_grid(self):
        ch = self.store.chain("SPY", D1)
        self.assertEqual(ch.bid.shape, (391, 3))                 # minute-major, 09:30..16:00
        self.assertEqual(list(ch.strike), [400.0, 400.0, 401.0])
        self.assertEqual(list(ch.is_call), [True, False, False])
        self.assertEqual(list(ch.dte), [0, 0, 1])
        self.assertTrue(np.isnan(ch.bid[0]).all())               # no row at 09:30: no quote
        self.assertAlmostEqual(float(ch.bid[1, 0]), 2.0, places=5)
        self.assertAlmostEqual(float(ch.bid[2, 0]), 2.1, places=5)
        self.assertTrue(np.isnan(ch.bid[3, 0]))                  # a minute without a row is no quote, not the last one
        self.assertEqual(int(ch.ask_size[1, 2]), 10)
        self.assertEqual(list(ch.oi), [55, 0, 77])
        self.assertEqual(list(ch.index_of(ch.key[::-1])), [2, 1, 0])
        self.assertEqual(int(ch.index_of(np.array([12345]))[0]), -1)

    def test_underlying_holds_the_last_price_never_a_later_one(self):
        u = self.store.underlying("SPY", D1)
        self.assertTrue(math.isnan(u.price[0]))                  # 09:30: nothing yet, and never back-filled
        self.assertEqual(u.price[1], 400.0)
        self.assertEqual(u.price[3], 401.0)                      # 09:33 holds 09:32's price
        self.assertEqual(u.price[29], 401.0)
        self.assertEqual(u.price[30], 402.0)

    def test_missing_data_is_a_clear_error(self):
        with self.assertRaises(S.MissingData):
            self.store.chain("QQQ", D1)
        with self.assertRaises(S.MissingData):
            S.Store(self.dir + "-nowhere")
        self.assertEqual(self.store.days("train", ["SPY"]), [D1])
        self.assertEqual(S.describe(self.store, "train", ["SPY", "QQQ"])["roots"]["QQQ"]["nbbo"], 0)

    def test_trade_quote_is_train_only(self):
        with self.assertRaises(S.StoreRefused):
            self.store.trade_quote("SPY", dt.date(2025, 3, 3))


@unittest.skipUnless(HAVE, "numpy/pyarrow not installed (requirements-gym.txt)")
class TheGreeks(unittest.TestCase):
    def test_normal_cdf(self):
        x = np.linspace(-6, 6, 241)
        ref = np.array([0.5 * math.erfc(-v / math.sqrt(2)) for v in x])
        self.assertLess(float(np.max(np.abs(G.norm_cdf(x) - ref))), 1e-7)

    def test_implied_vol_round_trip(self):
        rng = np.random.default_rng(3)
        n = 400
        spot = 450.0
        strike = spot * (1 + rng.uniform(-0.06, 0.06, n))
        dte = rng.integers(0, 15, n)
        call = rng.random(n) < 0.5
        vol = rng.uniform(0.08, 0.8, n)
        years = G.years_to_expiry(dte, 700)
        price = G.bs_price(spot, strike, years, 0.05, vol, call)
        iv = G.implied_vol(price, spot, strike, years, 0.05, call)
        intrinsic = np.where(call, np.maximum(spot - strike * np.exp(-0.05 * years), 0), np.maximum(strike * np.exp(-0.05 * years) - spot, 0))
        solvable = (price - intrinsic) > 1e-4
        self.assertLess(float(np.nanmax(np.abs(iv - vol)[solvable])), 1e-4)
        self.assertTrue(np.isnan(G.implied_vol(0.5, 450.0, 400.0, 0.01, 0.05, True)))   # under intrinsic

    def test_greeks_signs_and_parity(self):
        d_call, g, t, v = G.greeks(450.0, 450.0, 5 / 365, 0.04, 0.2, True)
        d_put = G.greeks(450.0, 450.0, 5 / 365, 0.04, 0.2, False)[0]
        self.assertAlmostEqual(float(d_call - d_put), 1.0, places=9)
        self.assertGreater(float(g), 0)
        self.assertLess(float(t), 0)
        self.assertGreater(float(v), 0)

    def test_snapshot_computes_greeks_on_demand_and_parity_spot(self):
        strikes = np.array([445.0, 445.0, 450.0, 450.0, 455.0, 455.0])
        calls = np.array([True, False] * 3)
        years = G.years_to_expiry(np.zeros(6), 700)
        mid = G.bs_price(451.0, strikes, years, 0.04, 0.15, calls)
        snap = C.Snapshot("XSP", 700, 451.0, np.zeros(6), strikes, calls, np.maximum(mid - 0.01, 0.0), mid + 0.01, rate=0.04)
        view = snap.view(snap.slice_index(0, 0, 0.05))
        self.assertEqual(view.n, 6)
        self.assertFalse(snap._done.any())
        # At the money the mid is the model's price: its vol comes back. (A wing's time value is a few
        # hundredths, and a quote's cent moves its vol a lot: that is the market, not the solver.)
        self.assertTrue(np.all(np.abs(view.iv[2:4] - 0.15) < 0.002), view.iv)
        self.assertTrue(snap._done.all())
        self.assertAlmostEqual(C.parity_spot(np.zeros(6), strikes, calls, mid, 450.0), 451.0, delta=0.05)


class TheEvents(unittest.TestCase):
    def test_flags(self):
        days = [dt.date(2024, 3, 14), dt.date(2024, 3, 15), dt.date(2024, 3, 28), dt.date(2024, 4, 1)]
        cal = EV.EventCalendar(days)
        self.assertTrue(cal.flags(dt.date(2024, 3, 15))["monthly_opex"])
        self.assertTrue(cal.flags(dt.date(2024, 3, 28))["quarter_end"])   # the 29th was Good Friday
        self.assertTrue(cal.flags(dt.date(2024, 1, 31))["fomc"])
        self.assertTrue(cal.flags(dt.date(2024, 2, 13))["cpi"])
        self.assertTrue(cal.flags(dt.date(2024, 8, 2))["jobs"])
        self.assertEqual(cal.next_day(dt.date(2024, 3, 15)), dt.date(2024, 3, 28))
        self.assertAlmostEqual(EV.rate_on(dt.date(2024, 1, 10)), 0.054)
        good_friday = EV.EventCalendar([dt.date(2022, 4, 14), dt.date(2022, 4, 18)])
        self.assertTrue(good_friday.monthly_opex(dt.date(2022, 4, 14)))  # the expiry moves to Thursday


if __name__ == "__main__":
    unittest.main()
