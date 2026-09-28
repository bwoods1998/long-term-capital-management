"""The Gym's drift block (league/gym/results.py `drift`, Sept 27): each Train year's daily P&L fitted on the day's return
of the roots held, so a profit the market's own drift would have paid is not counted as the program's timing.

The fits are checked on invented series whose answer is known by construction (pure drift, pure timing, a signal-free
exposure, a zero-trade year, two roots), the split merge against the unsplit fit, and the engine end to end on a tiny
synthetic store (skipped without numpy and pyarrow). Synthetic data only.
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


def returns_of(seed: int = 3, *, sd: float = 0.01, roots: tuple[str, ...] = ("SPY",), extra: dict | None = None,
               timing: float = 0.0) -> dict[str, dict[str, float]]:
    """{day: {root: return}}: each year's drift plus noise; `timing` adds that much on a day after a decline (the
    mean reversion a timing signal can use), `extra` {root: added mean} a root's own drift."""
    rng = random.Random(seed)
    out: dict[str, dict[str, float]] = {}
    last = {r: 0.0 for r in roots}
    for day in DAYS:
        row = {}
        for r in roots:
            x = MU[day[:4]] + (extra or {}).get(r, 0.0) + rng.gauss(0.0, sd) + (timing if last[r] < 0 else 0.0)
            row[r] = x
            last[r] = x
        out[day] = row
    return out


def series(pnl_of, returns, roots=("SPY",), held=None):
    """(trades, daily) of a program whose day's P&L is pnl_of(day, returns) and that holds `held(day)` roots (a one-day
    trade on each root held; a day's P&L of zero with nothing held)."""
    trades, daily, equity = [], [], 10_000.0
    for i, day in enumerate(DAYS):
        on = held(day) if held else roots
        pnl = pnl_of(day, returns) if on else 0.0
        for r in on:
            trades.append({"id": len(trades) + 1, "day": day, "exit_day": day, "root": r, "pnl": pnl / len(on), "max_loss": 100.0})
        equity += pnl
        daily.append([day, pnl, equity])
    return trades, daily


def previous_declined(returns, root="SPY"):
    """day -> did `root` fall on the day before (the timing signal)."""
    out, last = {}, 0.0
    for day in DAYS:
        out[day] = last < 0
        last = returns[day][root]
    return out


class Fits(unittest.TestCase):
    def test_pure_drift_has_no_alpha_and_fails_the_screen(self):
        """The same exposure every day (the placebo: P_t = k r_t): every dollar is drift, whatever the year's trend."""
        rets = returns_of()
        trades, daily = series(lambda day, r: 20_000.0 * r[day]["SPY"], rets)
        block = RS.drift(trades, daily, rets, ["SPY"])
        self.assertEqual(set(block["years"]), {"2022", "2023", "2024"})
        for year, row in block["years"].items():
            self.assertLess(abs(row["alpha_usd"]), 0.01, year)
            self.assertIsNone(row["t"], "an exact line in r: the alpha's error is not estimable")
            self.assertAlmostEqual(row["beta"], 20_000.0, places=2)
            self.assertAlmostEqual(row["drift_usd"], row["pnl"], places=1, msg="all of it is drift")
        self.assertGreater(block["years"]["2023"]["pnl"], 1000, "the bull year made money")
        verdict = evidence.drift_screen(evidence.drift_numbers(block))
        self.assertTrue(verdict["known"])
        self.assertFalse(verdict["passed"])

    def test_drift_with_noise_orthogonal_to_the_market_still_has_no_alpha(self):
        """A drift trade plus noise the market does not explain (orthogonal to 1 and r within each year): alpha is zero
        with an estimable error, so t is about zero, and the screen fails it."""
        rets = returns_of(seed=5)
        noise = {}
        for year in MU:
            days = [d for d in DAYS if d.startswith(year)]
            rs = [rets[d]["SPY"] for d in days]
            mr = sum(rs) / len(rs)
            w = [math.sin(i * 1.7) for i in range(len(days))]
            for basis in ([1.0] * len(days), [x - mr for x in rs]):  # Gram-Schmidt against the intercept and r
                dot = sum(a * b for a, b in zip(w, basis)) / sum(b * b for b in basis)
                w = [a - dot * b for a, b in zip(w, basis)]
            noise.update({d: 300.0 * x for d, x in zip(days, w)})
        trades, daily = series(lambda day, r: 20_000.0 * r[day]["SPY"] + noise[day], rets)
        block = RS.drift(trades, daily, rets, ["SPY"])
        for row in block["years"].values():
            self.assertLess(abs(row["t"]), 1e-6)
        self.assertLess(abs(block["pooled"]["t"]), 1e-6)
        self.assertFalse(evidence.drift_screen(evidence.drift_numbers(block))["passed"])

    def test_pure_timing_passes(self):
        """Long only on the day after a decline, when the root's return is higher: the timing is alpha, in every year,
        net of a dollar of costs a day held."""
        rets = returns_of(seed=7, timing=0.006)
        fell = previous_declined(rets)
        trades, daily = series(lambda day, r: 20_000.0 * r[day]["SPY"] - 1.0, rets, held=lambda day: ["SPY"] if fell[day] else [])
        block = RS.drift(trades, daily, rets, ["SPY"])
        for year, row in block["years"].items():
            self.assertGreater(row["alpha_usd"], 0, year)
            self.assertGreater(row["t"], 2.0, year)
            self.assertAlmostEqual(row["alpha_usd"] + row["drift_usd"], row["pnl"], places=1)
        self.assertGreater(block["pooled"]["t"], 3.0)
        self.assertAlmostEqual(block["pooled"]["alpha_usd"], sum(r["alpha_usd"] for r in block["years"].values()), places=1)
        verdict = evidence.drift_screen(evidence.drift_numbers(block))
        self.assertTrue(verdict["passed"], verdict)
        self.assertEqual((verdict["positive"], verdict["years"], verdict["need"]), (3, 3, 2))

    def test_the_pooled_line_keeps_each_years_beta(self):
        """More exposure in the bull year than in the bear year is three data points of timing, not evidence: with each
        year's own beta, a program that is pure drift within every year has no pooled alpha."""
        rets = returns_of(seed=11)
        size = {"2022": 5_000.0, "2023": 40_000.0, "2024": 10_000.0}
        trades, daily = series(lambda day, r: size[day[:4]] * r[day]["SPY"], rets)
        block = RS.drift(trades, daily, rets, ["SPY"])
        self.assertLess(abs(block["pooled"]["alpha_usd"]), 0.05)
        self.assertAlmostEqual(block["pooled"]["drift_usd"], block["pooled"]["pnl"], places=1)

    def test_a_zero_trade_year_has_no_alpha_and_does_not_move_the_pooled_t(self):
        rets = returns_of(seed=7, timing=0.004)
        fell = previous_declined(rets)
        on = lambda day: ["SPY"] if fell[day] and not day.startswith("2022") else []  # noqa: E731 - nothing in 2022
        trades, daily = series(lambda day, r: 20_000.0 * r[day]["SPY"], rets, held=on)
        block = RS.drift(trades, daily, rets, ["SPY"])
        idle = block["years"]["2022"]
        self.assertEqual((idle["pnl"], idle["alpha_usd"], idle["drift_usd"], idle["t"]), (0.0, 0.0, 0.0, None))
        self.assertGreater(idle["days"], 200, "a year without a trade is still a year of days")
        later = [d for d in daily if not d[0].startswith("2022")]
        alone = RS.drift([t for t in trades if not t["day"].startswith("2022")], later, rets, ["SPY"])
        self.assertAlmostEqual(block["pooled"]["t"], alone["pooled"]["t"], places=6)
        numbers = evidence.drift_numbers(block)
        self.assertTrue(evidence.drift_screen(numbers)["passed"], "2 of 3 years positive: all but one")
        strict = evidence.drift_screen(numbers, years_positive=3)
        self.assertFalse(strict["passed"])
        self.assertIn("positive in 2 of 3", strict["why"])

    def test_two_roots_regress_on_the_roots_held(self):
        """QQQ trends far more than SPY. A program that always holds QQQ is pure drift of what it held; against the two
        roots' mean it would look like alpha (its root choice), which the held basis does not credit. A day it holds
        nothing takes its own roots' mean; a day it holds both, theirs."""
        rets = returns_of(seed=13, roots=("SPY", "QQQ"), extra={"QQQ": 0.002})
        trades, daily = series(lambda day, r: 20_000.0 * r[day]["QQQ"], rets, roots=("SPY", "QQQ"), held=lambda day: ["QQQ"])
        block = RS.drift(trades, daily, rets, ["SPY", "QQQ"])
        self.assertLess(abs(block["pooled"]["alpha_usd"]), 0.05)
        pooled_mean = {d: {"MEAN": (r["SPY"] + r["QQQ"]) / 2} for d, r in rets.items()}
        naive = RS.drift([{**t, "root": "MEAN"} for t in trades], daily, pooled_mean, ["MEAN"])
        self.assertGreater(naive["pooled"]["alpha_usd"], 1000, "an equal-weight basis would credit the root choice")
        day0, day1, day2 = DAYS[:3]
        rows = RS.drift_rows([{"day": day1, "exit_day": day2, "root": "SPY"}, {"day": day2, "exit_day": day2, "root": "QQQ"}],
                             [[day0, 0.0, 1.0], [day1, 5.0, 1.0], [day2, 7.0, 1.0]], rets, ["SPY", "QQQ"])
        self.assertAlmostEqual(rows[0][2], (rets[day0]["SPY"] + rets[day0]["QQQ"]) / 2, msg="nothing held: its roots' mean")
        self.assertAlmostEqual(rows[1][2], rets[day1]["SPY"], msg="SPY held")
        self.assertAlmostEqual(rows[2][2], (rets[day2]["SPY"] + rets[day2]["QQQ"]) / 2, msg="both held")

    def test_days_without_a_return_or_outside_its_own_days_are_left_out(self):
        rets = returns_of(seed=3)
        rets[DAYS[0]] = {}  # the first day: no prior close
        trades, daily = series(lambda day, r: 1.0, rets)
        own = set(DAYS[:-10])
        block = RS.drift(trades, daily, rets, ["SPY"], own)
        self.assertEqual(sum(r["days"] for r in block["years"].values()), len(DAYS) - 11)


class SplitMerge(unittest.TestCase):
    """The pool splits Train in eight: the merged block is the unsplit fit on the same days."""

    def test_merging_eight_segments_equals_the_unsplit_fit(self):
        rets = returns_of(seed=17, roots=("SPY", "QQQ"), timing=0.003)
        fell = previous_declined(rets, "QQQ")
        held = lambda day: ["QQQ"] if fell[day] else (["SPY"] if day.endswith("5") else [])  # noqa: E731
        trades, daily = series(lambda day, r: 15_000.0 * sum(r[day][x] for x in held(day)) - 0.5, rets, roots=("SPY", "QQQ"),
                               held=held)
        whole = RS.drift(trades, daily, rets, ["SPY", "QQQ"])
        size = math.ceil(len(DAYS) / 8)
        parts = []
        for i in range(0, len(DAYS), size):
            span = set(DAYS[i:i + size])
            parts.append({"drift": RS.drift([t for t in trades if t["day"] in span], [d for d in daily if d[0] in span], rets,
                                            ["SPY", "QQQ"])})
        self.assertEqual(len(parts), 8)
        self.assertTrue(any(len(p["drift"]["years"]) == 2 for p in parts), "a segment spans a new year")
        merged = RS.merge_drift(parts)
        for year in whole["years"]:
            for key in ("days", "pnl", "alpha", "alpha_usd", "t", "beta", "drift_usd", "mean_return"):
                self.assertAlmostEqual(merged["years"][year][key], whole["years"][year][key], delta=1e-3 * max(1.0, abs(whole["years"][year][key])),
                                       msg=f"{year} {key}")
            for a, b in zip(merged["years"][year]["moments"], whole["years"][year]["moments"]):
                self.assertAlmostEqual(a, b, delta=1e-9 * max(1.0, abs(b)))
        for key in ("days", "pnl", "alpha_usd", "t", "drift_usd"):
            self.assertAlmostEqual(merged["pooled"][key], whole["pooled"][key], delta=1e-3 * max(1.0, abs(whole["pooled"][key])), msg=key)

    def test_a_segment_without_the_block_leaves_the_merge_without_one(self):
        rets = returns_of()
        trades, daily = series(lambda day, r: 1.0, rets)
        block = RS.drift(trades, daily, rets, ["SPY"])
        self.assertIsNone(RS.merge_drift([{"drift": block}, {}]), "a segment from before the block: not screened")

    def test_combining_with_an_empty_set_is_the_other(self):
        m = RS.drift_moments([(0.01, 5.0), (-0.02, -3.0), (0.005, 1.0)])
        self.assertEqual(RS.combine_moments([0, 0.0, 0.0, 0.0, 0.0, 0.0], m), m)
        self.assertEqual(RS.combine_moments(m, [0, 0.0, 0.0, 0.0, 0.0, 0.0]), m)


class Views(unittest.TestCase):
    def test_only_train_carries_the_block(self):
        rets = returns_of()
        trades, daily = series(lambda day, r: 1.0, rets)
        result = {"run_id": "r", "status": "ok", "summary": {"trades": 1}, "fills": {}, "breakdown": {}, "daily": daily,
                  "trades": trades, "drift": RS.drift(trades, daily, rets, ["SPY"])}
        self.assertIn("drift", RS.view(result, "train"))
        for window in ("validation", "holdout", "forward", "gate"):
            self.assertNotIn("drift", RS.view(result, window), window)
        self.assertNotIn("drift", RS.view(result, "validation")["summary"])


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

    def run_one(self, **kw):
        cfg = E.RunConfig(roots=("SPY",), fill_model=self.model, **kw)
        return E.run([R.load_program(self.PROGRAM, name="p")], self.store, cfg)[0]

    def closes(self):
        """{day: {"SPY": close-to-close return}} straight from the store's underlying files."""
        out, last = {}, None
        for day in self.train:
            price = self.store.underlying("SPY", day).price
            close = float(price[numpy.isfinite(price)][-1])
            if last is not None:
                out[day.isoformat()] = {"SPY": close / last - 1.0}
            last = close
        return out

    def test_a_train_run_carries_the_block_and_its_returns_are_the_stores_closes(self):
        result = self.run_one(window="train")
        self.assertEqual(result["status"], "ok", result["runtime"])
        self.assertGreater(result["summary"]["trades"], 0)
        block = result["drift"]
        self.assertEqual(set(block["years"]), {"2022", "2023"})
        self.assertEqual(sum(r["days"] for r in block["years"].values()), len(self.train) - 1,
                         "every day but the first (no close before it in the store)")
        expected = RS.drift(result["trades"], result["daily"], self.closes(), ["SPY"])
        for year in block["years"]:
            for key in ("pnl", "alpha_usd", "drift_usd", "beta", "mean_return"):
                self.assertAlmostEqual(block["years"][year][key], expected["years"][year][key], places=2, msg=f"{year} {key}")
        self.assertAlmostEqual(sum(r["pnl"] for r in block["years"].values()) + result["daily"][0][1], result["summary"]["account_pnl"],
                               places=1)

    def test_split_segments_merge_into_the_fit_of_the_merged_series(self):
        parts = [self.run_one(window="train", start=self.train[0], end=self.train[4], split_mark=True),
                 self.run_one(window="train", start=self.train[5], end=self.train[-1], warmup=5)]
        merged = RS.merge(parts)
        expected = RS.drift(merged["trades"], merged["daily"], self.closes(), ["SPY"])
        self.assertEqual(set(merged["drift"]["years"]), set(expected["years"]))
        for year in expected["years"]:
            for key in ("days", "pnl", "alpha_usd", "drift_usd", "beta"):
                self.assertAlmostEqual(merged["drift"]["years"][year][key], expected["years"][year][key], places=2, msg=f"{year} {key}")

    def test_a_validation_run_computes_no_block(self):
        result = self.run_one(window="validation")
        self.assertEqual(result["status"], "ok", result["runtime"])
        self.assertNotIn("drift", result)


if __name__ == "__main__":
    unittest.main()
