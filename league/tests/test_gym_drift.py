"""The Gym's drift block (league/gym/results.py `drift`, Sept 27): each Train year, the exposure a program held (the slope
of its P&L on the move of the roots it held, over the hours it held them, held days only) is charged the roots'
unconditional drift over those hours; what is left is its alpha, with the t of the drift-adjusted daily P&L.

Checked on invented series whose answer is known by construction: pure drift, a calm-day and a volatile-day holder
without timing (the review of #398: a slope over every day weighs held days by their variance), a real rebound edge on
volatile days, an overnight holder (the drift lives overnight), pure timing, a zero-trade year, two roots, the split merge
against the unsplit fit, and the engine end to end on a tiny synthetic store (skipped without numpy and pyarrow).
Synthetic data only.
"""

from __future__ import annotations

import datetime as dt
import math
import random
import shutil
import tempfile
import unittest

from league.gym import results as RS
from league.swarm import evidence

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

FULL = 390.0


def train_days() -> list[str]:
    """Every weekday of 2022-2024 (a stand-in for the Train calendar)."""
    out, d = [], dt.date(2022, 1, 3)
    while d <= dt.date(2024, 12, 31):
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += dt.timedelta(days=1)
    return out


DAYS = train_days()
#: Each year's drift: a bear, a bull and a flat year (a daily mean return).
MU = {"2022": -0.0008, "2023": 0.0012, "2024": 0.0001}


def market(seed: int = 3, *, sd: float = 0.01, roots: tuple[str, ...] = ("SPY",), extra: dict | None = None, timing: float = 0.0,
           sd_of=None) -> dict[str, dict[str, dict[str, float]]]:
    """{day: {root: {"ret_on", "ret_in", "session", "ret"}}}, the engine's regimes: each year's drift plus noise, all of the
    day's move overnight (so a full day's return is exact); `timing` adds that much on a day after a decline (what a timing
    signal can use), `extra` {root: added mean}, `sd_of(day)` a day's own volatility."""
    rng = random.Random(seed)
    out: dict[str, dict[str, dict[str, float]]] = {}
    last = {r: 0.0 for r in roots}
    for day in DAYS:
        row = {}
        for r in roots:
            x = MU[day[:4]] + (extra or {}).get(r, 0.0) + rng.gauss(0.0, sd_of(day) if sd_of else sd) + (timing if last[r] < 0 else 0.0)
            row[r] = {"ret_on": x, "ret_in": 0.0, "session": FULL, "ret": x}
            last[r] = x
        out[day] = row
    return out


def program(pnl_of, returns, held):
    """(daily, exposure) of a program that holds `held(day)` roots all day (carried from the prior close, to the close) and
    makes pnl_of(day) on a day it holds any (nothing on a flat day)."""
    daily, exposure, equity = [], {}, 10_000.0
    for day in DAYS:
        on = held(day)
        pnl = pnl_of(day) if on else 0.0
        if on:
            exposure[day] = {r: (1, FULL, returns[day][r]["ret"]) for r in on}
        equity += pnl
        daily.append([day, pnl, equity])
    return daily, exposure


def previous_declined(returns, root="SPY"):
    """day -> did `root` fall on the day before (the timing signal)."""
    out, last = {}, 0.0
    for day in DAYS:
        out[day] = last < 0
        last = returns[day][root]["ret"]
    return out


def screen(block, **kw):
    return evidence.drift_screen(evidence.drift_numbers(block), **kw)


class Fits(unittest.TestCase):
    def test_pure_drift_has_no_alpha_and_fails_the_screen(self):
        """The same exposure every day (the placebo): every dollar is drift, whatever the year's trend."""
        rets = market()
        daily, exposure = program(lambda day: 20_000.0 * rets[day]["SPY"]["ret"], rets, lambda day: ["SPY"])
        block = RS.drift(daily, rets, exposure, ["SPY"])
        self.assertEqual(set(block["years"]), {"2022", "2023", "2024"})
        for year, row in block["years"].items():
            self.assertLess(abs(row["alpha_usd"]), 0.01, year)
            self.assertIsNone(row["t"], "no variance left once the drift is charged: pure drift")
            self.assertAlmostEqual(row["beta"], 20_000.0, places=2)
            self.assertAlmostEqual(row["drift_usd"], row["pnl"], places=1, msg="all of it is drift")
            self.assertEqual(row["held_days"], row["days"])
        self.assertGreater(block["years"]["2023"]["pnl"], 1000, "the bull year made money")
        verdict = screen(block)
        self.assertEqual((verdict["known"], verdict["passed"]), (True, False))

    def holders(self, calm_hold: bool, n: int = 60_000):
        """One long bull year: calm days (0.4x the variance) and volatile days (1.6x), the same mean; a program holds the
        calm (or the volatile) ones only, with no timing at all."""
        rng = random.Random(29)
        days = [f"2023-{i:06d}" for i in range(n)]
        rets, daily, exposure = {}, [], {}
        for day in days:
            calm = rng.random() < 0.5
            r = rng.gauss(0.0009, 0.0085 * math.sqrt(0.4 if calm else 1.6))
            rets[day] = {"SPY": {"ret_on": r, "ret_in": 0.0, "session": FULL}}
            held = calm == calm_hold
            daily.append([day, 5000.0 * r if held else 0.0, 0.0])
            if held:
                exposure[day] = {"SPY": (1, FULL, r)}
        return RS.drift_fit(RS.drift_stats(RS.drift_rows(daily, rets, exposure, ["SPY"]))["2023"])

    def test_a_calm_or_volatile_day_holder_without_timing_has_no_alpha(self):
        """The review of #398: a slope over EVERY day weighs held days by their variance, so a calm-day holder's drift passed
        for 59% alpha. Held days only, beta is the exposure and alpha is noise around zero either way."""
        for calm in (True, False):
            f = self.holders(calm)
            self.assertAlmostEqual(f["beta"], 5000.0, delta=50.0)
            self.assertLess(abs(f["alpha_usd"]), 0.08 * f["pnl"], (calm, f))
            self.assertLess(abs(f["t"]), 2.5, (calm, f))

    def test_a_rebound_edge_on_volatile_days_is_alpha(self):
        """Long only after a down day, when the next day's mean is twice the year's AND its variance 2.5x: a real edge that a
        variance-weighted slope measured as a loss. Its alpha is the exposure times the mean difference."""
        rng = random.Random(31)
        n, daily, rets, exposure, truth_r = 80_000, [], {}, {}, []
        for i in range(n):
            day = f"2023-{i:06d}"
            signal = rng.random() < 0.15
            r = rng.gauss(0.0018, 0.0085 * math.sqrt(2.5)) if signal else rng.gauss(0.0009, 0.0085)
            rets[day] = {"SPY": {"ret_on": r, "ret_in": 0.0, "session": FULL}}
            daily.append([day, 5000.0 * r if signal else 0.0, 0.0])
            truth_r.append((signal, r))
            if signal:
                exposure[day] = {"SPY": (1, FULL, r)}
        f = RS.drift_fit(RS.drift_stats(RS.drift_rows(daily, rets, exposure, ["SPY"]))["2023"])
        mean_all = sum(r for _, r in truth_r) / n
        held = sum(1 for s, _ in truth_r if s)
        truth = 5000.0 * held * (0.0018 - mean_all)
        self.assertGreater(f["alpha_usd"], 0)
        self.assertLess(abs(f["alpha_usd"] - truth), 0.2 * truth, (f["alpha_usd"], truth))
        self.assertGreater(f["t"], 3.0)

    def test_an_overnight_holder_is_charged_the_overnight_drift(self):
        """Held from the prior close to an hour after the open every day, when the drift lives overnight: its P&L is all
        drift. Measured over the hours held (the move from the prior close to its exit), it has no alpha; measured close to
        close (the day's return over hours it did not hold) half its P&L would have passed for alpha."""
        rng = random.Random(37)
        n, daily, rets, exposure, naive = 60_000, [], {}, {}, {}
        for i in range(n):
            day = f"2023-{i:06d}"
            o, m, a = rng.gauss(0.0009, 0.0085 * math.sqrt(0.3)), rng.gauss(0, 0.0085 * math.sqrt(0.2)), rng.gauss(0, 0.0085 * math.sqrt(0.5))
            rets[day] = {"SPY": {"ret_on": o, "ret_in": m + a, "session": FULL}}
            naive[day] = {"SPY": {"ret_on": o + m + a, "ret_in": 0.0, "session": FULL}}
            daily.append([day, 5000.0 * (o + m), 0.0])
            exposure[day] = {"SPY": (1, 60.0, o + m)}
        f = RS.drift_fit(RS.drift_stats(RS.drift_rows(daily, rets, exposure, ["SPY"]))["2023"])
        self.assertLess(abs(f["alpha_usd"]), 0.05 * f["pnl"], f)
        close_to_close = {day: {"SPY": (1, FULL, naive[day]["SPY"]["ret_on"])} for day in exposure}
        g = RS.drift_fit(RS.drift_stats(RS.drift_rows(daily, naive, close_to_close, ["SPY"]))["2023"])
        self.assertGreater(g["alpha_usd"], 0.3 * g["pnl"], "the bias the held hours remove")

    def test_pure_timing_passes(self):
        """Long only on the day after a decline, when the root's return is higher: the timing is alpha, in every year,
        net of a dollar of costs a day held."""
        rets = market(seed=7, timing=0.006)
        fell = previous_declined(rets)
        daily, exposure = program(lambda day: 20_000.0 * rets[day]["SPY"]["ret"] - 1.0, rets, lambda day: ["SPY"] if fell[day] else [])
        block = RS.drift(daily, rets, exposure, ["SPY"])
        for year, row in block["years"].items():
            self.assertGreater(row["alpha_usd"], 0, year)
            self.assertGreater(row["t"], 2.0, year)
            self.assertAlmostEqual(row["alpha_usd"] + row["drift_usd"], row["pnl"], places=1)
        self.assertGreater(block["pooled"]["t"], 3.0)
        self.assertAlmostEqual(block["pooled"]["alpha_usd"], sum(r["alpha_usd"] for r in block["years"].values()), places=1)
        verdict = screen(block)
        self.assertTrue(verdict["passed"], verdict)
        self.assertEqual((verdict["positive"], verdict["years"], verdict["need"]), (3, 3, 2))

    def test_an_always_held_carry_is_alpha_and_market_noise_does_not_hide_it(self):
        """Held every day with a real carry of a dollar a day beside the exposure: the t of the drift-adjusted P&L carries
        each day's share of the drift estimate, so the market's noise (which the exposure's drift charge cancels over a
        year held every day) does not swamp the carry."""
        rets = market(seed=41)
        rng = random.Random(43)
        noise = {day: rng.gauss(0.0, 2.0) for day in DAYS}
        daily, exposure = program(lambda day: 20_000.0 * rets[day]["SPY"]["ret"] + 1.0 + noise[day], rets, lambda day: ["SPY"])
        block = RS.drift(daily, rets, exposure, ["SPY"])
        self.assertAlmostEqual(block["pooled"]["alpha_usd"], len(DAYS) + sum(noise.values()), delta=5.0)
        self.assertGreater(block["pooled"]["t"], 5.0)

    def test_a_zero_trade_year_has_no_alpha(self):
        rets = market(seed=7, timing=0.006)
        fell = previous_declined(rets)
        daily, exposure = program(lambda day: 20_000.0 * rets[day]["SPY"]["ret"], rets,
                                  lambda day: ["SPY"] if fell[day] and not day.startswith("2022") else [])
        block = RS.drift(daily, rets, exposure, ["SPY"])
        idle = block["years"]["2022"]
        self.assertEqual((idle["pnl"], idle["alpha_usd"], idle["drift_usd"], idle["t"], idle["held_days"]), (0.0, 0.0, 0.0, None, 0))
        self.assertGreater(idle["days"], 200, "a year without a trade is still a year of days")
        later = RS.drift([d for d in daily if not d[0].startswith("2022")], rets, exposure, ["SPY"])
        self.assertAlmostEqual(block["pooled"]["alpha_usd"], later["pooled"]["alpha_usd"], places=2)
        self.assertLessEqual(block["pooled"]["t"], later["pooled"]["t"], "its days of nothing never raise the t")
        numbers = evidence.drift_numbers(block)
        self.assertTrue(evidence.drift_screen(numbers)["passed"], "2 of 3 years positive: all but one")
        strict = evidence.drift_screen(numbers, years_positive=3)
        self.assertFalse(strict["passed"])
        self.assertIn("positive in 2 of 3", strict["why"])

    def test_two_roots_are_each_charged_their_own_drift(self):
        """QQQ trends far more than SPY. A program that always holds QQQ is pure drift of what it held: charged QQQ's own
        drift (not the two roots' mean, which would credit the root choice as alpha)."""
        rets = market(seed=13, roots=("SPY", "QQQ"), extra={"QQQ": 0.002})
        daily, exposure = program(lambda day: 20_000.0 * rets[day]["QQQ"]["ret"], rets, lambda day: ["QQQ"])
        block = RS.drift(daily, rets, exposure, ["SPY", "QQQ"])
        self.assertLess(abs(block["pooled"]["alpha_usd"]), 0.05)
        both, exposure2 = program(lambda day: 10_000.0 * (rets[day]["SPY"]["ret"] + rets[day]["QQQ"]["ret"]), rets,
                                  lambda day: ["SPY", "QQQ"])
        block2 = RS.drift(both, rets, exposure2, ["SPY", "QQQ"])
        self.assertLess(abs(block2["pooled"]["alpha_usd"]), 0.05, "both held: each charged its own drift")
        self.assertAlmostEqual(block2["years"]["2023"]["beta"], 20_000.0, delta=1.0, msg="x is the held roots' mean move")

    def test_days_without_a_full_days_return_or_outside_its_own_days_are_left_out(self):
        rets = market(seed=3)
        rets[DAYS[0]] = {"SPY": {"ret_on": float("nan"), "ret_in": 0.0, "session": FULL, "ret": 0.0}}  # no prior close
        daily, exposure = program(lambda day: 1.0, rets, lambda day: ["SPY"])
        block = RS.drift(daily, rets, exposure, ["SPY"], set(DAYS[:-10]))
        self.assertEqual(sum(r["days"] for r in block["years"].values()), len(DAYS) - 11)


class SplitMerge(unittest.TestCase):
    """The pool splits Train in eight: the merged block is the unsplit fit on the same days."""

    def test_merging_eight_segments_equals_the_unsplit_fit(self):
        rets = market(seed=17, roots=("SPY", "QQQ"), timing=0.003)
        for day in DAYS:  # some of each day's move intraday, so the per-minute drift is exercised
            for r in ("SPY", "QQQ"):
                x = rets[day][r]["ret_on"]
                rets[day][r].update(ret_on=0.4 * x, ret_in=0.6 * x)
        fell = previous_declined({d: {"QQQ": {"ret": rets[d]["QQQ"]["ret_on"]}} for d in DAYS}, "QQQ")
        daily, exposure, equity = [], {}, 0.0
        for i, day in enumerate(DAYS):
            spans = {}
            if fell[day]:
                spans["QQQ"] = (1, 200.0, rets[day]["QQQ"]["ret_on"] + 0.3 * rets[day]["QQQ"]["ret_in"])
            if day.endswith("5"):
                spans["SPY"] = (0, 90.0, 0.2 * rets[day]["SPY"]["ret_in"])
            pnl = 15_000.0 * sum(x[2] for x in spans.values()) - 0.5 if spans else 0.0
            if spans:
                exposure[day] = spans
            equity += pnl
            daily.append([day, pnl, equity])
        whole = RS.drift(daily, rets, exposure, ["SPY", "QQQ"])
        size = math.ceil(len(DAYS) / 8)
        parts = []
        for i in range(0, len(DAYS), size):
            span = set(DAYS[i:i + size])
            parts.append({"drift": RS.drift([d for d in daily if d[0] in span], rets, exposure, ["SPY", "QQQ"])})
        self.assertEqual(len(parts), 8)
        self.assertTrue(any(len(p["drift"]["years"]) == 2 for p in parts), "a segment spans a new year")
        merged = RS.merge_drift(parts)
        for year in whole["years"]:
            for key in ("days", "held_days", "pnl", "alpha", "alpha_usd", "t", "beta", "drift_usd"):
                self.assertAlmostEqual(merged["years"][year][key], whole["years"][year][key],
                                       delta=1e-6 * max(1.0, abs(whole["years"][year][key])), msg=f"{year} {key}")
        for key in ("days", "held_days", "pnl", "alpha_usd", "t", "drift_usd"):
            self.assertAlmostEqual(merged["pooled"][key], whole["pooled"][key], delta=1e-6 * max(1.0, abs(whole["pooled"][key])), msg=key)
        self.assertGreater(whole["pooled"]["t"], 1.0)

    def test_a_segment_without_the_block_leaves_the_merge_without_one(self):
        rets = market()
        daily, exposure = program(lambda day: 1.0, rets, lambda day: ["SPY"])
        block = RS.drift(daily, rets, exposure, ["SPY"])
        self.assertIsNone(RS.merge_drift([{"drift": block}, {}]), "a segment from before the block: not screened")

    def test_combining_with_an_empty_set_is_the_other(self):
        m = RS.drift_moments([(0.01, 5.0), (-0.02, -3.0), (0.005, 1.0)])
        self.assertEqual(RS.combine_moments([0, 0.0, 0.0, 0.0, 0.0, 0.0], m), m)
        self.assertEqual(RS.combine_moments(m, [0, 0.0, 0.0, 0.0, 0.0, 0.0]), m)


class Views(unittest.TestCase):
    def test_only_train_carries_the_block(self):
        rets = market()
        daily, exposure = program(lambda day: 1.0, rets, lambda day: ["SPY"])
        result = {"run_id": "r", "status": "ok", "summary": {"trades": 1}, "fills": {}, "breakdown": {}, "daily": daily,
                  "trades": [], "drift": RS.drift(daily, rets, exposure, ["SPY"])}
        self.assertIn("drift", RS.view(result, "train"))
        for window in ("validation", "holdout", "forward", "gate"):
            self.assertNotIn("drift", RS.view(result, window), window)
        self.assertNotIn("drift", RS.view(result, "validation")["summary"])
        self.assertNotIn("stats", evidence.drift_numbers(result["drift"])["years"]["2023"], "a run row keeps the figures only")


@unittest.skipUnless(HAVE, "numpy/pyarrow not installed (requirements-gym.txt)")
class Engine(unittest.TestCase):
    """End to end on a synthetic store spanning a Train year boundary (and a few Validation days)."""

    PROGRAM = '''
NEEDS = {"roots": ["SPY"], "dte": [0, 4], "band": 0.05, "cadence": 30}
PARAMS = {}
def decide(ctx):
    out = [{"close": p["id"]} for p in ctx.positions if p["held_minutes"] > 400]
    if not ctx.positions and not ctx.orders and ctx.minute < 700:
        out.append({"open": "long_call", "legs": [{"side": "long", "right": "C", "dte": 2, "atm": 0}], "qty": 1})
    return out
'''

    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix="gym-drift-")
        cls.train = synth.weekdays(dt.date(2022, 12, 22), 10)
        cls.valid = synth.weekdays(dt.date(2025, 1, 6), 3)
        synth.generate(cls.dir, roots=("SPY",), days=cls.train + cls.valid, strikes_each_side=6, max_dte=4, seed=21)
        cls.store = S.Store(cls.dir)
        cls.model = synth.uniform_model(0.5, ("SPY",), levels=(2, 3), size=5)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def run_one(self, keep=None, **kw):
        cfg = E.RunConfig(roots=("SPY",), fill_model=self.model, **kw)
        return E.run([R.load_program(self.PROGRAM, name="p")], self.store, cfg, keep=keep)[0]

    def prices(self, day):
        price = self.store.underlying("SPY", day).price
        return price, numpy.flatnonzero(numpy.isfinite(price))

    def components(self):
        """{day: {"SPY": {"ret_on", "ret_in", "session"}}} straight from the store's underlying files."""
        out, last = {}, None
        for day in self.train:
            price, known = self.prices(day)
            first, close = float(price[known[0]]), float(price[known[-1]])
            if last is not None:
                out[day.isoformat()] = {"SPY": {"ret_on": first / last - 1.0, "ret_in": close / first - 1.0,
                                                "session": float(known[-1] - known[0])}}
            last = close
        return out

    def test_a_train_run_carries_the_block_and_its_hours_held_are_the_positions(self):
        accounts = []
        result = self.run_one(keep=accounts, window="train")
        self.assertEqual(result["status"], "ok", result["runtime"])
        self.assertGreater(result["summary"]["trades"], 0)
        exposure = accounts[0].exposure
        # Each trade's entry day: held from its fill minute; the return over the hours held is the store's.
        first = result["trades"][0]
        day = dt.date.fromisoformat(first["day"])
        carried, minutes, ret = exposure[first["day"]]["SPY"]
        price, known = self.prices(day)
        start = first["filled_minute"] - 570
        self.assertNotEqual(first["exit_day"], first["day"], "held overnight: open to its day's close")
        end = int(known[-1])
        self.assertEqual(carried, 0, "the run's first position: nothing was carried into its day")
        self.assertAlmostEqual(ret, float(price[end]) / float(price[start]) - 1.0, places=9)
        self.assertEqual(minutes, float(end - start))
        # Its exit day: held from the prior close (carried) to the exit.
        exit_day = dt.date.fromisoformat(first["exit_day"])
        carried, minutes, ret = exposure[first["exit_day"]]["SPY"]
        self.assertEqual(carried, 1)
        prior = self.train[self.train.index(exit_day) - 1]
        before, known_before = self.prices(prior)
        price, known = self.prices(exit_day)
        self.assertGreaterEqual(minutes, float(first["exit_minute"] - 570), "to its exit, or to the close if it reopened")
        self.assertAlmostEqual(ret, float(price[int(minutes)]) / float(before[known_before[-1]]) - 1.0, places=9)
        block = result["drift"]
        self.assertEqual(set(block["years"]), {"2022", "2023"})
        self.assertEqual(sum(r["days"] for r in block["years"].values()), len(self.train) - 1,
                         "every day but the first (no close before it in the store)")
        expected = RS.drift(result["daily"], self.components(), exposure, ["SPY"])
        for year in block["years"]:
            for key in ("pnl", "held_days", "alpha_usd", "drift_usd", "beta"):
                self.assertAlmostEqual(block["years"][year][key], expected["years"][year][key], places=2, msg=f"{year} {key}")

    def test_split_segments_merge_into_the_fit_of_the_merged_series(self):
        accounts: list = []
        parts = [self.run_one(keep=accounts, window="train", start=self.train[0], end=self.train[4], split_mark=True),
                 self.run_one(keep=accounts, window="train", start=self.train[5], end=self.train[-1], warmup=5)]
        merged = RS.merge(parts)
        exposure = {**accounts[0].exposure, **accounts[1].exposure}
        expected = RS.drift(merged["daily"], self.components(), exposure, ["SPY"])
        self.assertEqual(set(merged["drift"]["years"]), set(expected["years"]))
        for year in expected["years"]:
            for key in ("days", "held_days", "pnl", "alpha_usd", "drift_usd", "beta"):
                self.assertAlmostEqual(merged["drift"]["years"][year][key], expected["years"][year][key], places=2, msg=f"{year} {key}")

    def test_a_validation_run_computes_no_block(self):
        result = self.run_one(window="validation")
        self.assertEqual(result["status"], "ok", result["runtime"])
        self.assertNotIn("drift", result)


if __name__ == "__main__":
    unittest.main()
