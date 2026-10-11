"""Release E3, THE OUT-OF-FOLD ARITHMETIC (league/swarm/elane_effects.py; D15): the Newey-West standard error and the
contribution of a hidden run against values worked by hand, the series' bytes and sha, what a hidden run must be (one
work year, ended "ok" or "disqualified"), the measured horizon and the seen-year cost facts; and, on E1's own runner
and screen accounting, the same figures from an independent computation. Every program, price and number here is
invented."""

from __future__ import annotations

import datetime as dt
import hashlib
import math
import struct
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from league.equity import config, screen
from league.equity.store import Bars, nyse_sessions, ordinal
from league.swarm import elane, elane_effects, elane_folds
from league.tests import elane_e2_fakes as fx
from league.tests import elane_e3_fakes as e3


def flat_bars(year: int, prices: list[float]) -> Bars:
    """An invented slice: the year's first sessions, each opening and closing at its price (high = low = close)."""
    days = [d for d, _ in nyse_sessions(dt.date(year, 1, 1), dt.date(year, 12, 31))][:len(prices)]
    level = np.array(prices, dtype=np.float64)
    raw = np.column_stack([level, level, level, level, np.full(len(days), 1e6)])
    return Bars(days=np.array([ordinal(d) for d in days], dtype=np.int32), early=np.zeros(len(days), dtype=bool), first=0,
                symbols=("SPY",), raw={"SPY": raw}, adj={"SPY": raw[:, :4].copy()}, window="train", data_version="fake")


def lot(bars: Bars, entry: int, exit_: int | None, *, weight: float = 0.5, entry_at: str = "close",
        exit_at: str = "open", lid: int = 1) -> dict:
    return {"lid": lid, "symbol": "SPY", "class": "etf", "weight": weight, "entry_day": bars.day(entry).isoformat(),
            "entry_at": entry_at, "exit_day": bars.day(exit_).isoformat() if exit_ is not None else None,
            "exit_at": exit_at if exit_ is not None else None, "hs": None, "held_sessions": (exit_ or bars.n - 1) - entry}


def run_of(bars: Bars, lots: list[dict], *, status: str = "ok", **extra) -> SimpleNamespace:
    result = {"status": status, "capital": "1000", "needs": {"symbols": ["SPY"], "history": 0, "max_hold_sessions": 5},
              "symbols": ["SPY"], "lots": lots, "run_sha": "fake-run-sha", **extra}
    return SimpleNamespace(result=result, bars=bars)


class TheNeweyWestStandardError(unittest.TestCase):
    def test_a_hand_value(self):
        # x = 1, 2, 3, 4: the mean is 2.5 and the deviations -1.5, -0.5, 0.5, 1.5; g_0 = 5 / 4, g_1 = 1.25 / 4,
        # g_2 = -1.5 / 4, g_3 = -2.25 / 4.
        x = [1.0, 2.0, 3.0, 4.0]
        self.assertAlmostEqual(elane_effects.nw_se(x, 0), math.sqrt(1.25 / 4), places=15)
        self.assertAlmostEqual(elane_effects.nw_se(x, 1), 0.625, places=15)      # (1.25 + 2 * (1/2) * 0.3125) / 4
        want = (1.25 + 2 * ((5 / 6) * 0.3125 + (4 / 6) * -0.375 + (3 / 6) * -0.5625)) / 4
        self.assertAlmostEqual(elane_effects.nw_se(x), math.sqrt(want), places=15)
        self.assertEqual(elane_effects.NW_LAG, 5)
        self.assertEqual(elane_effects.nw_se(x), elane_effects.nw_se(x, 5))
        # A lag past the series adds no term (g_l is an empty sum from l = n on); the Bartlett weights are the lag's own.
        wide = (1.25 + 2 * ((50 / 51) * 0.3125 + (49 / 51) * -0.375 + (48 / 51) * -0.5625)) / 4
        self.assertAlmostEqual(elane_effects.nw_se(x, 50), math.sqrt(wide), places=15)

    def test_the_formula_term_by_term(self):
        rng = np.random.default_rng(11)
        x = [float(v) for v in rng.normal(0.0, 0.01, 40)]
        n, lag = len(x), 5
        mean = math.fsum(x) / n
        gamma = [math.fsum((x[t] - mean) * (x[t - step] - mean) for t in range(step, n)) / n for step in range(lag + 1)]
        want = math.sqrt((gamma[0] + 2 * math.fsum((1 - step / (lag + 1)) * gamma[step] for step in range(1, lag + 1))) / n)
        self.assertAlmostEqual(elane_effects.nw_se(x), want, places=15)
        self.assertAlmostEqual(elane_effects.nw_se(np.array(x)), want, places=15)

    def test_too_few_values_or_no_spread_is_none(self):
        self.assertIsNone(elane_effects.nw_se([]))
        self.assertIsNone(elane_effects.nw_se([0.3]))
        self.assertIsNone(elane_effects.nw_se([0.0] * 30))
        # The mean is summed exactly (`math.fsum`): ten tenths are one, so a constant series has no spread at all. The
        # built-in sum of Python 3.11 gives 0.9999999999999999 and a spread of rounding noise.
        self.assertIsNone(elane_effects.nw_se([0.1] * 10))
        self.assertIsNone(elane_effects.t_stat([0.1] * 10))
        self.assertIsNone(elane_effects.nw_se([float("nan"), 1.0, 2.0]))

    def test_the_t_is_the_one_sample_t(self):
        self.assertAlmostEqual(elane_effects.t_stat([1.0, 2.0, 3.0]), 2.0 / 1.0 * math.sqrt(3), places=14)
        self.assertIsNone(elane_effects.t_stat([1.0]))
        self.assertIsNone(elane_effects.t_stat([2.0, 2.0, 2.0]))


class TheContribution(unittest.TestCase):
    PRICES = [100.0, 102.0, 101.0, 103.0, 104.0, 104.0]

    def by_hand(self) -> tuple[list[float], list[float]]:
        """x and w of one lot (half the sleeve, bought at the second session's close, sold at the fourth's open) on
        `PRICES`, from the screen's accounting written out: the entry pays the half-spread and carries no exposure
        that session; the held session earns the close-to-close move at full weight; the exit sells at the open less
        the half-spread and the sell fees, at half weight. The benchmark is the symbol's own close-to-close move."""
        hs = config.half_spread("SPY")
        weight, e0 = 0.5, 1000.0
        fill = 102.0 * (1.0 + hs)
        fee = float(config.sell_fees(config.Decimal(str(weight)) * config.Decimal("1000"),
                                     config.Decimal(str(weight * e0 / fill)))) / e0
        self.assertAlmostEqual(fee, 0.00003, places=12, msg="two cents of SEC fee and one of TAF on a $500 sale")
        r = [0.0, weight * (1.0 / (1.0 + hs) - 1.0), weight * (101.0 / 102.0 - 1.0),
             weight * (103.0 * (1.0 - hs) / 101.0 - 1.0) - fee, 0.0, 0.0]
        w = [0.0, 0.0, weight, weight / 2.0, 0.0, 0.0]
        b = [0.0, 102.0 / 100.0 - 1.0, 101.0 / 102.0 - 1.0, 103.0 / 101.0 - 1.0, 104.0 / 103.0 - 1.0, 0.0]
        return [ri - wi * bi for ri, wi, bi in zip(r, w, b)], w

    def test_golden_values(self):
        bars = flat_bars(2018, self.PRICES)
        c = elane_effects.contribution(run_of(bars, [lot(bars, 1, 3)]), k=1.0)
        x, w = self.by_hand()
        n = len(x)
        mean_x, mean_w = math.fsum(x) / n, math.fsum(w) / n
        self.assertEqual((c["year"], c["k"], c["status"], c["n_days"], c["n_lots"]), (2018, 1.0, "ok", 6, 1))
        self.assertAlmostEqual(c["exp_mean"], 0.125, places=15)
        self.assertAlmostEqual(c["exp_mean"], mean_w, places=15)
        self.assertAlmostEqual(c["e_ann"], 252 * mean_x / mean_w, places=12)
        self.assertAlmostEqual(c["se_ann"], 252 * elane_effects.nw_se(x, 5) / mean_w, places=12)
        sd = math.sqrt(math.fsum((v - mean_x) ** 2 for v in x) / (n - 1))
        self.assertAlmostEqual(c["t_x"], mean_x / sd * math.sqrt(n), places=10)
        self.assertEqual(c["run_sha"], "fake-run-sha")
        # The held session's excess is nothing (the lot moved as the benchmark did); the exit's is its costs and the
        # open against the close at half weight.
        got = struct.unpack("<6f", c["x"])
        for mine, want in zip(got, x):
            self.assertAlmostEqual(mine, want, places=9)
        self.assertEqual(got[0], 0.0)
        self.assertAlmostEqual(got[2], 0.0, places=12)
        self.assertEqual(struct.unpack("<6f", c["w"]), (0.0, 0.0, 0.5, 0.25, 0.0, 0.0))

    def test_the_series_bytes_and_their_sha(self):
        bars = flat_bars(2018, self.PRICES)
        c = elane_effects.contribution(run_of(bars, [lot(bars, 1, 3)]), k=1.5)
        self.assertEqual(c["k"], 1.5)
        self.assertEqual(struct.unpack("<6i", c["days"]), tuple(int(d) for d in bars.days), "int32 little-endian ordinals")
        self.assertEqual((len(c["days"]), len(c["x"]), len(c["w"])), (24, 24, 24), "four bytes a session each")
        self.assertEqual(c["series_sha"], hashlib.sha256(c["days"] + c["x"] + c["w"]).hexdigest())
        again = elane_effects.contribution(run_of(bars, [lot(bars, 1, 3)]), k=1.5)
        self.assertEqual((again["series_sha"], again["x"]), (c["series_sha"], c["x"]), "the same run, the same bytes")
        other = elane_effects.contribution(run_of(bars, [lot(bars, 1, 3, weight=0.25)]), k=1.5)
        self.assertNotEqual(other["series_sha"], c["series_sha"])

    def test_a_disqualified_year_is_recorded_as_it_traded(self):
        bars = flat_bars(2022, self.PRICES)
        c = elane_effects.contribution(run_of(bars, [lot(bars, 1, 3)], status="disqualified",
                                              reason="25 errors"), k=1.0)
        self.assertEqual((c["status"], c["year"], c["n_lots"]), ("disqualified", 2022, 1))
        self.assertIsNotNone(c["e_ann"])
        self.assertEqual(elane_effects.STATUSES, ("ok", "disqualified"))

    def test_a_year_never_in_the_market_has_no_annualized_figure(self):
        bars = flat_bars(2019, self.PRICES)
        c = elane_effects.contribution(run_of(bars, []), k=1.0)
        self.assertEqual((c["n_days"], c["n_lots"], c["exp_mean"]), (6, 0, 0.0))
        self.assertEqual((c["e_ann"], c["se_ann"], c["t_x"]), (None, None, None))
        self.assertEqual(struct.unpack("<6f", c["x"]), (0.0,) * 6)

    def test_what_is_not_a_hidden_run_is_refused(self):
        bars = flat_bars(2018, self.PRICES)
        for status in ("no_data", "error", "refused", "None", ""):
            with self.assertRaises(ValueError, msg=status):
                elane_effects.contribution(run_of(bars, [lot(bars, 1, 3)], status=status), k=1.0)
        with self.assertRaises(ValueError):
            elane_effects.contribution(SimpleNamespace(result={"status": "ok", "lots": []}, bars=None), k=1.0)
        with self.assertRaises(ValueError):
            elane_effects.contribution(SimpleNamespace(result=None, bars=bars), k=1.0)
        with self.assertRaises(ValueError, msg="a lot the bars cannot price (the screen's own refusal)"):
            elane_effects.contribution(run_of(bars, [{**lot(bars, 1, 3), "entry_day": "2018-06-29"}]), k=1.0)

    def test_only_one_work_year_is_ever_scored(self):
        """Fail closed: a run with sessions of the reserve, of Validation or of the holdout, or of two years, gives no
        figure (THE RESERVE STAYS SEALED; no sealed window is scored out of fold)."""
        for year in (*elane_folds.RESERVE_YEARS, 2025, 2026):
            bars = flat_bars(year, self.PRICES)
            with self.assertRaises(ValueError, msg=year):
                elane_effects.contribution(run_of(bars, [lot(bars, 1, 3)]), k=1.0)
        days = [d for d, _ in nyse_sessions(dt.date(2018, 12, 26), dt.date(2019, 1, 4))]
        level = np.linspace(100.0, 103.0, len(days))
        raw = np.column_stack([level, level, level, level, np.full(len(days), 1e6)])
        two = Bars(days=np.array([ordinal(d) for d in days], dtype=np.int32), early=np.zeros(len(days), dtype=bool),
                   first=0, symbols=("SPY",), raw={"SPY": raw}, adj={"SPY": raw[:, :4].copy()}, window="train")
        with self.assertRaises(ValueError):
            elane_effects.contribution(run_of(two, []), k=1.0)
        for year in elane_folds.WORK_YEARS:
            bars = flat_bars(year, self.PRICES)
            self.assertEqual(elane_effects.contribution(run_of(bars, [lot(bars, 1, 3)]), k=1.0)["year"], year)

    def test_on_e1s_runner_the_figures_are_the_screens_series(self):
        """E1's `Isolated` over its synthetic store (invented prices), the year's own run: the contribution is D15 on
        `screen.series` of that run's lots and bars, computed here with numpy (to a stated tolerance)."""
        from league.equity import synth
        from league.equity.runner import Isolated
        from league.live.decider import InlineDecider

        with tempfile.TemporaryDirectory() as tmp:
            root = synth.synthetic_store(Path(tmp) / elane.STORE_DIR, symbols=("SPY", "QQQ"), end=dt.date(2024, 12, 31),
                                         seed=9, drift=0.05, vol=0.15)
            code = fx.program().replace('"symbols": ["SPY"]', '"symbols": ["SPY", "QQQ"]')
            first, last = elane_folds.hidden_span(2023)
            run = Isolated(InlineDecider(), root).train(code, {}, name="p", start=first, end=last, k=1.0)
        c = elane_effects.contribution(run, k=1.0)
        s = screen.series(run.result["lots"], run.bars, universe=["SPY", "QQQ"], capital=run.result["capital"])
        x = s.r - s.w * s.b
        n = len(x)
        self.assertEqual((c["n_days"], c["n_lots"], c["year"]), (n, len(run.result["lots"]), 2023))
        self.assertEqual(n, len(nyse_sessions(first, last)))
        self.assertAlmostEqual(c["exp_mean"], float(np.mean(s.w)), places=12)
        self.assertAlmostEqual(c["e_ann"], 252 * float(np.mean(x)) / float(np.mean(s.w)), places=9)
        self.assertAlmostEqual(c["t_x"], float(np.mean(x) / np.std(x, ddof=1) * math.sqrt(n)), places=8)
        d = x - np.mean(x)
        gamma = [float(np.sum(d[step:] * d[:n - step]) / n) for step in range(6)]
        nw = math.sqrt((gamma[0] + 2 * sum((1 - step / 6) * gamma[step] for step in range(1, 6))) / n)
        self.assertAlmostEqual(c["se_ann"], 252 * nw / float(np.mean(s.w)), places=9)
        np.testing.assert_array_equal(np.frombuffer(c["days"], dtype="<i4"), s.days)
        np.testing.assert_array_equal(np.frombuffer(c["x"], dtype="<f4"), x.astype("<f4"))
        np.testing.assert_array_equal(np.frombuffer(c["w"], dtype="<f4"), s.w.astype("<f4"))
        self.assertEqual(c["run_sha"], run.result["run_sha"])
        self.assertNotAlmostEqual(c["e_ann"], 252 * float(np.mean(screen.excess(s))) / float(np.mean(s.w)), places=6,
                                  msg="the DAILY excess r - w b, never the screen's window-mean excess")


class TheHorizonAndTheCosts(unittest.TestCase):
    @staticmethod
    def held(*sessions, open_: int = 0) -> list[dict]:
        return ([{"exit_day": "2018-01-05", "held_sessions": h} for h in sessions]
                + [{"exit_day": None, "held_sessions": 40}] * open_)

    def test_the_horizon_is_the_median_hold_of_the_closed_lots(self):
        self.assertEqual(elane_effects.HORIZONS, tuple(e3.elane_births.EQUITY_HOLDING), "the card's own holding buckets")
        self.assertIsNone(elane_effects.horizon([]))
        self.assertIsNone(elane_effects.horizon(self.held(open_=3)), "an open lot has no hold yet")
        for sessions, want in (((1,), "days_1_3"), ((1, 1, 3), "days_1_3"), ((3, 3), "days_1_3"), ((3, 4), "days_4_10"),
                               ((4,), "days_4_10"), ((10, 10, 10), "days_4_10"), ((10, 11), "days_11_plus"),
                               ((11,), "days_11_plus"), ((1, 2, 60, 60, 60), "days_11_plus")):
            self.assertEqual(elane_effects.horizon(self.held(*sessions, open_=2)), want, sessions)
        self.assertEqual(elane_effects.horizon([{"exit_day": "2018-01-05", "held_sessions": None}, None, "lot",
                                                {"exit_day": "2018-01-05", "held_sessions": 2}]), "days_1_3")

    @staticmethod
    def result(pnl: float, weights: tuple[float, ...], years: tuple[str, ...], open_: int = 0) -> dict:
        lots = ([{"exit_day": "2018-01-05", "weight": w, "held_sessions": 2} for w in weights]
                + [{"exit_day": None, "weight": 0.5, "held_sessions": 9}] * open_)
        return {"summary": {"pnl": pnl}, "capital": "1000", "lots": lots, "by_year": {y: {} for y in years}}

    def test_the_cost_facts_by_hand(self):
        seen10 = [self.result(20.0, (0.5, 0.25), ("2016", "2017")), self.result(10.0, (0.25,), ("2019",), open_=1)]
        seen15 = [self.result(17.0, (0.5, 0.25), ("2016", "2017")), self.result(7.0, (0.25,), ("2019",))]
        out = elane_effects.costs(seen10, seen15)
        # pnl_10 = 30, pnl_15 = 24: C = 2 x 6 = 12 (the half-spreads at 1.0x), G = 42; three closed lots of $500, $250
        # and $250 (RT x Nbar = $1,000) over three seen years.
        self.assertAlmostEqual(out["cost_bp"], 12.0 / 1000.0 * 1e4, places=9)
        self.assertAlmostEqual(out["gross_bp"], 42.0 / 1000.0 * 1e4, places=9)
        self.assertAlmostEqual(out["rt_per_year"], 1.0, places=12)
        self.assertEqual(set(out), {"gross_bp", "cost_bp", "rt_per_year"})

    def test_no_closed_lot_or_no_figure_is_none(self):
        none = {"gross_bp": None, "cost_bp": None, "rt_per_year": None}
        self.assertEqual(elane_effects.costs([], []), none)
        self.assertEqual(elane_effects.costs(None, None), none)
        self.assertEqual(elane_effects.costs([self.result(5.0, (), ("2016",), open_=2)],
                                             [self.result(4.0, (), ("2016",))]), none, "RT = 0")
        # An invented runner's result (no lots at all) reads the same: nothing closed, nothing said.
        self.assertEqual(elane_effects.costs([fx.train_result()], [fx.train_result(k=1.5)]), none)
        # The round trips a year stand without a P&L; the bp figures do not.
        out = elane_effects.costs([{**self.result(5.0, (0.5,), ("2016", "2017")), "summary": {}}],
                                  [self.result(4.0, (0.5,), ("2016", "2017"))])
        self.assertEqual(out, {"gross_bp": None, "cost_bp": None, "rt_per_year": 0.5})


if __name__ == "__main__":
    unittest.main()
