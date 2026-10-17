"""x2 (HISTORY-PLAN.md section 5.3, "x2: zero mean for constant-weight holds on drifted synthetic stores";
league/deep/stat.py): a constant-weight hold scores zero however the market drifts, a static tilt gets no credit, and
timing that is really there shows; costs are charged at k x hs; the masked series takes its own mu.

Synthetic stores only (league/equity/synth.py)."""

from __future__ import annotations

import datetime as dt
import unittest

import numpy as np

from league.deep import stat as S
from league.equity import screen, synth
from league.equity.runner import Isolated
from league.live.decider import InlineDecider
from league.tests import deep_fakes as F

HOLD = '''NEEDS = {"symbols": %(symbols)s, "history": 1, "max_hold_sessions": 60}
PARAMS = {}


def decide(ctx):
    held = {p["symbol"] for p in ctx.positions}
    return [{"buy": s, "share": %(share)s, "at": "open"} for s in ctx.symbols if s not in held]
'''


def run(root, code, *, k=1.0, start=None, end=None):
    return Isolated(InlineDecider(), root).train(code, {}, name="x", start=start, end=end, k=k)


def part(r, symbols, keep=None):
    return S.Part(lots=r.result["lots"], bars=r.bars, symbols=tuple(symbols), capital=1000.0, first=int(r.bars.first),
                  last=int(r.bars.n) - 1, keep=keep)


class ZeroForAConstantHold(unittest.TestCase):
    def test_a_constant_weight_hold_scores_zero_on_drifted_stores(self):
        for drift in (0.25, -0.2):
            root = F.tmpdir(self) / "s"
            synth.synthetic_store(root, symbols=("SPY", "QQQ"), start=dt.date(2016, 1, 4), end=dt.date(2017, 12, 29),
                                  seed=4, drift=drift, vol=0.15)
            code = HOLD % {"symbols": ["SPY", "QQQ"], "share": 0.3}
            r = run(root, code)
            p = part(r, ("SPY", "QQQ"))
            x = S.x2([p], k=0.0)
            raw = screen.series(r.result["lots"], r.bars, universe=["SPY", "QQQ"], capital=1000.0).r
            # the drift is in r; it is not in x2 (the hold re-enters at the max hold, so a few entry legs remain)
            self.assertGreater(abs(float(np.mean(raw))), 20 * abs(float(np.mean(x))), drift)
            self.assertLess(abs(float(np.sum(x))), 0.02)
            t = S.t(x)
            self.assertTrue(t is None or abs(t) < 1.0)

    def test_a_static_tilt_gets_no_credit(self):
        root = F.tmpdir(self) / "s"
        synth.synthetic_store(root, symbols=("GLD", "XLK"), start=dt.date(2016, 1, 4), end=dt.date(2017, 12, 29),
                              seed=6, drift=0.3, vol=0.15)
        code = HOLD % {"symbols": ["GLD"], "share": 0.5}
        r = run(root, code)
        x = S.x2([part(r, ("GLD",))], k=0.0)
        self.assertLess(abs(float(np.sum(x))), 0.02)


class TimingShows(unittest.TestCase):
    def test_being_in_only_when_the_symbol_does_better_than_its_mean(self):
        """A planted edge: the program buys at a close only when tomorrow is up (it reads a NaN-free pattern the store
        was built with: the synthetic store's own up days are known to the test), so x2 is positive."""
        root = F.tmpdir(self) / "s"
        synth.synthetic_store(root, symbols=("SPY",), start=dt.date(2016, 1, 4), end=dt.date(2017, 12, 29), seed=2,
                              drift=0.0, vol=0.2)
        r0 = run(root, HOLD % {"symbols": ["SPY"], "share": 0.4})
        c = r0.bars.adj["SPY"][:, 3]
        ups = [i for i in range(1, len(c) - 1) if c[i + 1] > c[i]]
        lots = [{"lid": n, "symbol": "SPY", "weight": 0.4, "entry_day": r0.bars.day(i).isoformat(), "entry_at": "close",
                 "exit_day": r0.bars.day(i + 1).isoformat(), "exit_at": "close", "hs": 0.0001}
                for n, i in enumerate(ups[::2], 1)]
        p = S.Part(lots=lots, bars=r0.bars, symbols=("SPY",), capital=1000.0, first=int(r0.bars.first),
                   last=int(r0.bars.n) - 1)
        x = S.x2([p], k=1.0)
        self.assertGreater(S.t(x), 5.0)
        self.assertLess(float(np.sum(S.x2([p], k=40.0))), float(np.sum(x)), "costs at k x hs come off")


class TheMaskTakesItsOwnMean(unittest.TestCase):
    def test_masked_sessions_are_left_out_and_mu_is_the_kept_sessions(self):
        root = F.tmpdir(self) / "s"
        synth.synthetic_store(root, symbols=("SPY",), start=dt.date(2016, 1, 4), end=dt.date(2016, 12, 30), seed=3,
                              drift=0.1, vol=0.2)
        r = run(root, HOLD % {"symbols": ["SPY"], "share": 0.4})
        n = int(r.bars.n) - int(r.bars.first)
        keep = np.ones(n, dtype=bool)
        keep[100:140] = False
        p = part(r, ("SPY",), keep)
        self.assertEqual(S.x2([p], k=0.0, masked=True).shape, (n - 40,))
        self.assertEqual(S.x2([p], k=0.0).shape, (n,))
        self.assertLess(abs(float(np.sum(S.x2([p], k=0.0, masked=True)))), 0.02,
                        "a hold through the kept sessions is zero against their own mean")
        with self.assertRaises(ValueError):
            S.x2([S.Part(**{**p.__dict__, "keep": keep[:-1]})], k=1.0, masked=True)


if __name__ == "__main__":
    unittest.main()
