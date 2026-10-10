"""THE SHARE SCREEN S1 (league/equity/screen.py; release E1, amendment A9): the accounting on golden synthetic series
(open and close fills, fees), the pre-check, the look with F1's holdout guard, the floor on synthetic Train-era runs
(both world sets, the study's draws, ineligibility), refusal without a receipt, one try and one look a lineage (R3),
D3's same lineage, R4's flags and the line beside every live trade.

Invented prices, series and figures only. The receipt is league/tests/fixtures/equity_screen_fake.json (marked FAKE: the
study's keys, invented figures); the committed receipt is judged only through the repository's pin. `config.sell_fees`
and `config.half_spread` are core's: the accounting tests patch `sell_fees` with the documented rule (SEC and TAF, each
rounded up to the cent) and give every lot its `hs`. The floor's Train-era runs are synthetic bars built here (core's
`synth.synthetic_store` writes a store; the screen reads `Bars`, so a store adds nothing the bars do not)."""

from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import math
import os
import tempfile
import unittest
from decimal import ROUND_CEILING, Decimal
from pathlib import Path
from unittest import mock

import numpy as np

from league import ci
from league.equity import config, screen
from league.equity.store import Bars
from league.tests import REAL_POLICY_PATH

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "equity_screen_fake.json"
FAKE_SHA = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
EPOCH = dt.date(1970, 1, 1)
E0 = Decimal("1000")


def ordinal(day: dt.date) -> int:
    return (day - EPOCH).days


def weekdays(first: dt.date, last: dt.date) -> list[dt.date]:
    out, day = [], first
    while day <= last:
        if day.weekday() < 5:
            out.append(day)
        day += dt.timedelta(days=1)
    return out


def bars_of(days: list[dt.date], prices: dict[str, tuple[list[float], list[float]]], *, first: int = 0) -> Bars:
    """A `store.Bars` from (opens, closes) per symbol: adjustment=all equal to raw (no event)."""
    adj, raw = {}, {}
    for sym, (o, c) in prices.items():
        o, c = np.asarray(o, dtype=np.float64), np.asarray(c, dtype=np.float64)
        hi, lo = np.fmax(o, c), np.fmin(o, c)
        adj[sym] = np.column_stack([o, hi, lo, c])
        raw[sym] = np.column_stack([o, hi, lo, c, np.full(len(o), 1e6)])
    return Bars(days=np.array([ordinal(d) for d in days], dtype=np.int32), early=np.zeros(len(days), dtype=bool),
                first=first, symbols=tuple(prices), raw=raw, adj=adj, window="train")


def sell_fees(proceeds: Decimal, shares: Decimal) -> Decimal:
    """The documented rule (config.sell_fees, core's): SEC $27.80 a million of proceeds and TAF $0.000166 a share
    capped at $8.30, each rounded UP to the cent."""
    cent = Decimal("0.01")
    sec = (proceeds * Decimal("27.80") / Decimal(1_000_000)).quantize(cent, rounding=ROUND_CEILING)
    taf = min(shares * Decimal("0.000166"), Decimal("8.30")).quantize(cent, rounding=ROUND_CEILING)
    return sec + taf


def lot(lid, symbol, entry, entry_at, exit_=None, exit_at=None, *, weight, hs):
    return {"lid": lid, "symbol": symbol, "class": "etf", "weight": weight, "qty": "1", "entry_day": entry.isoformat(),
            "entry_at": entry_at, "entry_px": 0.0, "exit_day": exit_.isoformat() if exit_ else None,
            "exit_at": exit_at, "exit_px": None, "fees": "0", "div": "0", "hs": hs, "reason": "program",
            "held_sessions": 0}


def make_series(days: list[dt.date], r, *, w=None, b=None, exits=None, invested=None) -> screen.Series:
    n = len(days)
    r = np.asarray(r, dtype=np.float64)
    return screen.Series(days=np.array([ordinal(d) for d in days], dtype=np.int32), r=r,
                         w=np.full(n, 0.5) if w is None else np.asarray(w, dtype=np.float64),
                         b=np.zeros(n) if b is None else np.asarray(b, dtype=np.float64),
                         exits=np.zeros(n, dtype=np.int64) if exits is None else np.asarray(exits),
                         invested=np.ones(n, dtype=bool) if invested is None else np.asarray(invested, dtype=bool))


def exact(rng: np.random.Generator, n: int, mean: float, sd: float = 0.01) -> np.ndarray:
    """n daily values with exactly this mean (noise centred, then shifted): a t that does not hang on the seed."""
    z = rng.normal(0.0, sd, n)
    return z - z.mean() + mean


def receipt() -> screen.Receipt:
    return screen.load_receipt(FIXTURE, pinned_sha256=FAKE_SHA)


V_DAYS = weekdays(dt.date(2025, 1, 2), dt.date(2025, 12, 31))[:screen.V_LENGTH]
H_DAYS = weekdays(dt.date(2026, 1, 2), dt.date(2026, 12, 31))[:200]


# ======================================================================================================== accounting
class Accounting(unittest.TestCase):
    """Section 2.2's legs (and A2's close legs), hand-computed on a 6-session path, to 1e-12."""

    DAYS = weekdays(dt.date(2022, 3, 7), dt.date(2022, 3, 14))      # six sessions d0..d5
    SPY = ([100.0, 101.0, 102.0, 101.0, 103.0, 104.0], [100.5, 101.5, 101.0, 102.0, 103.5, 105.0])
    QQQ = ([200.0, 202.0, 199.0, 201.0, 204.0, 203.0], [201.0, 200.0, 200.5, 203.0, 202.0, 206.0])

    def setUp(self):
        self.assertEqual(len(self.DAYS), 6)
        self.bars = bars_of(self.DAYS, {"SPY": self.SPY, "QQQ": self.QQQ})
        d = self.DAYS
        self.lots = [
            lot(1, "SPY", d[1], "open", d[4], "open", weight=0.5, hs=0.0001),      # open in, open out
            lot(2, "QQQ", d[1], "close", d[2], "open", weight=0.25, hs=0.0003),    # close in, next open out (A2)
            lot(3, "QQQ", d[2], "close", d[4], "close", weight=0.25, hs=0.0003),   # close in, close out (A2)
            lot(4, "SPY", d[4], "close", weight=0.2, hs=0.0001),                   # close in, still held
        ]
        self.calls = []

        def fees(proceeds, shares):
            self.calls.append((proceeds, shares))
            return sell_fees(proceeds, shares)

        patcher = mock.patch.object(config, "sell_fees", side_effect=fees)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_golden_legs_open_and_close_fills_and_fees(self):
        s = screen.series(self.lots, self.bars, universe=["SPY", "QQQ"], capital=E0)
        # Fees, each SEC + TAF rounded up to the cent on the constant-weight sale (proceeds omega E0, shares omega E0 /
        # entry fill): lot 2 250 / (200 x 1.0003) shares -> 0.01 + 0.01; lot 1 500 / (101 x 1.0001) -> 0.02 + 0.01;
        # lot 3 250 / (200.5 x 1.0003) -> 0.01 + 0.01.
        fee1, fee2, fee3 = 0.03, 0.02, 0.02
        want_r = [
            0.0,
            0.5 * (101.5 / (101.0 * 1.0001) - 1) + 0.25 * (1 / 1.0003 - 1),
            0.5 * (101.0 / 101.5 - 1) + (0.25 * (199.0 * (1 - 0.0003) / 200.0 - 1) - fee2 / 1000)
            + 0.25 * (1 / 1.0003 - 1),
            0.5 * (102.0 / 101.0 - 1) + 0.25 * (203.0 / 200.5 - 1),
            (0.5 * (103.0 * (1 - 0.0001) / 102.0 - 1) - fee1 / 1000)
            + (0.25 * (202.0 * (1 - 0.0003) / 203.0 - 1) - fee3 / 1000) + 0.2 * (1 / 1.0001 - 1),
            0.2 * (105.0 / 103.5 - 1),
        ]
        np.testing.assert_allclose(s.r, want_r, rtol=0, atol=1e-12)
        # Exposure: open entries and exits half, a close exit whole (held through), a close entry nothing at t.
        np.testing.assert_allclose(s.w, [0.0, 0.25, 0.5 + 0.125, 0.75, 0.25 + 0.25, 0.2], rtol=0, atol=1e-15)
        self.assertEqual(s.exits.tolist(), [0, 0, 1, 0, 2, 0])
        self.assertEqual(s.invested.tolist(), [False, True, True, True, True, True])
        spy, qqq = self.SPY[1], self.QQQ[1]
        want_b = [0.0] + [((spy[t] / spy[t - 1] - 1) + (qqq[t] / qqq[t - 1] - 1)) / 2 for t in range(1, 6)]
        np.testing.assert_allclose(s.b, want_b, rtol=0, atol=1e-15)
        self.assertEqual(s.days.tolist(), [ordinal(d) for d in self.DAYS])
        # The fee is asked for the constant-weight sale (proceeds omega E0; shares omega E0 over the entry fill).
        got = sorted((float(p), float(q)) for p, q in self.calls)
        want = sorted([(500.0, 500.0 / (101.0 * 1.0001)), (250.0, 250.0 / (200.0 * 1.0003)),
                       (250.0, 250.0 / (200.5 * 1.0003))])
        for (gp, gq), (wp, wq) in zip(got, want):
            self.assertAlmostEqual(gp, wp, places=9)
            self.assertAlmostEqual(gq, wq, places=9)

    def test_a_window_is_the_same_legs(self):
        whole = screen.series(self.lots, self.bars, universe=["SPY", "QQQ"], capital=E0)
        part = screen.series(self.lots, self.bars, universe=["SPY", "QQQ"], capital=E0, first=2, last=4)
        for name in ("r", "w", "b", "exits", "invested", "days"):
            np.testing.assert_array_equal(getattr(part, name), getattr(whole, name)[2:5], err_msg=name)
        self.assertEqual(screen.series(self.lots, bars_of(self.DAYS, {"SPY": self.SPY, "QQQ": self.QQQ}, first=3),
                                       universe=["SPY"], capital=E0).r.tolist(), whole.r[3:].tolist(),
                         "default: the bars' run sessions")

    def test_a_constant_return_path_earns_omega_g_a_held_session(self):
        g = 0.003
        closes = [100.0 * (1 + g) ** t for t in range(6)]
        bars = bars_of(self.DAYS, {"SPY": (closes, closes)})
        s = screen.series([lot(1, "SPY", self.DAYS[0], "close", weight=0.5, hs=0.0)], bars, universe=["SPY"],
                          capital=E0)
        np.testing.assert_allclose(s.r[1:], 0.5 * g, rtol=0, atol=1e-12)
        np.testing.assert_allclose(s.b[1:], g, rtol=0, atol=1e-12)
        self.assertEqual(s.r[0], 0.0, "a cost-free close entry costs nothing at t")
        x = screen.excess(s)
        np.testing.assert_allclose(x.sum(), s.r.sum() - s.w.mean() * s.b.sum(), rtol=0, atol=1e-12)

    def test_the_benchmark_counts_members_with_both_closes(self):
        qqq = (self.QQQ[0], [201.0, 200.0, 200.5, float("nan"), 202.0, 206.0])
        s = screen.series([], bars_of(self.DAYS, {"SPY": self.SPY, "QQQ": qqq}), universe=["SPY", "QQQ"],
                          capital=E0)
        spy = self.SPY[1]
        self.assertAlmostEqual(s.b[3], spy[3] / spy[2] - 1, places=15)
        self.assertAlmostEqual(s.b[4], spy[4] / spy[3] - 1, places=15)
        self.assertAlmostEqual(s.b[5], ((spy[5] / spy[4] - 1) + (206.0 / 202.0 - 1)) / 2, places=15)

    def test_a_lot_without_hs_reads_the_symbols_half_spread(self):
        row = {**self.lots[0], "hs": None}
        with mock.patch.object(config, "half_spread", return_value=0.0001) as hs:
            s = screen.series([row], self.bars, universe=["SPY"], capital=E0)
        hs.assert_called_with("SPY")
        self.assertAlmostEqual(s.r[1], 0.5 * (101.5 / (101.0 * 1.0001) - 1), places=15)

    def test_it_fails_closed(self):
        d = self.DAYS
        bad = [
            [lot(9, "SPY", d[2], "open", d[2], "close", weight=0.5, hs=0.0001)],     # sold in its entry session
            [lot(9, "SPY", d[2], "open", d[1], "open", weight=0.5, hs=0.0001)],      # sold before it
            [lot(9, "IWM", d[1], "open", weight=0.5, hs=0.0001)],                    # not in the bars
            [lot(9, "SPY", dt.date(2022, 3, 5), "open", weight=0.5, hs=0.0001)],     # not a session (a Saturday)
            [lot(9, "SPY", d[1], "noon", weight=0.5, hs=0.0001)],                    # not a fill point
            [lot(9, "SPY", d[1], "open", d[3], "noon", weight=0.5, hs=0.0001)],
            [lot(9, "SPY", d[1], "open", weight=float("nan"), hs=0.0001)],
            [lot(9, "SPY", d[1], "open", weight=0.0, hs=0.0001)],
            [lot(9, "SPY", d[1], "open", weight=0.5, hs=-0.1)],
        ]
        for lots in bad:
            with self.assertRaises(ValueError, msg=lots[0]):
                screen.series(lots, self.bars, universe=["SPY", "QQQ"], capital=E0)
        gap = (self.SPY[0], [100.5, 101.5, float("nan"), 102.0, 103.5, 105.0])
        with self.assertRaises(ValueError):
            screen.series([lot(9, "SPY", d[1], "open", weight=0.5, hs=0.0001)],
                          bars_of(self.DAYS, {"SPY": gap}), universe=["SPY"], capital=E0)
        with self.assertRaises(ValueError):
            screen.series([], self.bars, universe=["IWM"], capital=E0)
        with self.assertRaises(ValueError):
            screen.series([], self.bars, universe=[], capital=E0)
        with self.assertRaises(ValueError):
            screen.series([], self.bars, universe=["SPY"], capital=E0, first=4, last=2)
        with self.assertRaises(ValueError):
            screen.series([], self.bars, universe=["SPY"], capital="0")


# =========================================================================================== the pre-check and the look
class Steps(unittest.TestCase):
    def test_the_activity_line(self):
        days = V_DAYS
        n = len(days)
        r = np.full(n, 1e-4)

        def at(rt, inv):
            exits = np.zeros(n, dtype=np.int64)
            exits[:rt] = 1
            invested = np.zeros(n, dtype=bool)
            invested[:inv] = True
            return screen.precheck(make_series(days, r, exits=exits, invested=invested))

        self.assertTrue(at(20, 0)["passed"])
        self.assertFalse(at(19, 0)["passed"])
        self.assertTrue(at(0, 120)["passed"])
        self.assertFalse(at(19, 119)["passed"])
        self.assertEqual((at(19, 119)["round_trips"], at(19, 119)["invested_days"]), (19, 119))
        self.assertEqual(at(19, 119)["checks"], {"activity": False, "sum_positive": True})

    def test_the_sum_must_clear_zero(self):
        days = V_DAYS[:4]
        on = dict(invested=np.ones(4, dtype=bool))
        self.assertFalse(screen.precheck(make_series(days, [0.01, -0.01, 0.02, -0.02], **on))["passed"], "exactly 0")
        self.assertFalse(screen.precheck(make_series(days, [1e-12, 0, 0, 0], **on))["checks"]["sum_positive"])
        self.assertTrue(screen.precheck(make_series(days, [2e-12, 0, 0, 0], **on))["checks"]["sum_positive"])

    def test_the_excess_variant(self):
        """An always-in program that tracks its benchmark less its costs passes on r in a rising window, never on x."""
        n = len(V_DAYS)
        b = np.full(n, 0.001)
        r = 0.5 * b - 1e-6
        s = make_series(V_DAYS, r, w=np.full(n, 0.5), b=b)
        self.assertTrue(screen.precheck(s)["passed"])
        self.assertFalse(screen.precheck(s, variant="X")["passed"])
        np.testing.assert_allclose(screen.excess(s), r - 0.5 * 0.001, rtol=0, atol=1e-15)
        with self.assertRaises(ValueError):
            screen.precheck(s, variant="Y")

    def test_pooled_and_holdout_t(self):
        self.assertAlmostEqual(screen.pooled_t(np.array([1.0, 2.0, 3.0]), np.array([4.0])),
                               2.5 / np.std([1, 2, 3, 4], ddof=1) * 2.0, places=12)
        self.assertAlmostEqual(screen.holdout_t(np.array([1.0, 3.0])), 2.0 / math.sqrt(2.0) * math.sqrt(2.0), places=12)
        self.assertIsNone(screen.pooled_t(np.full(3, 0.01), np.full(2, 0.01)), "sd 0 fails")
        self.assertIsNone(screen.holdout_t(np.array([0.5])), "one value has no sd")
        self.assertIsNone(screen.pooled_t(np.array([1.0, np.nan]), np.array([1.0])))

    def _vh(self, seed=3, v_mean=0.002, h_mean=0.002):
        rng = np.random.default_rng(seed)
        v = make_series(V_DAYS, exact(rng, len(V_DAYS), v_mean))
        return v, make_series(H_DAYS, exact(rng, len(H_DAYS), h_mean))

    def test_t_exactly_at_c_passes(self):
        v, h = self._vh()
        t = screen.pooled_t(v.r, h.r)
        self.assertTrue(screen.look(v, h, c=t, c_H=None)["passed"])
        self.assertFalse(screen.look(v, h, c=float(np.nextafter(t, math.inf)), c_H=None)["passed"])

    def test_the_holdout_must_make_money(self):
        v, _ = self._vh()
        h = make_series(H_DAYS, np.concatenate([np.full(100, 0.004), np.full(100, -0.004)]))
        out = screen.look(v, h, c=0.0, c_H=None)
        self.assertFalse(out["passed"])
        self.assertEqual(out["checks"], {"t": True, "sum_h": False})

    def test_f1_the_holdout_only_guard(self):
        """Review fix F1: a strong Validation carries a weak holdout past the pooled t; t_H >= c_H stops it."""
        v, h = self._vh(seed=4, v_mean=0.004, h_mean=0.0007)
        t, t_h = screen.pooled_t(v.r, h.r), screen.holdout_t(h.r)
        self.assertGreater(t, 2.0)
        self.assertGreater(t_h, 0.0)
        guarded = screen.look(v, h, c=2.0, c_H=t_h + 0.5)
        self.assertFalse(guarded["passed"])
        self.assertEqual(guarded["checks"], {"t": True, "sum_h": True, "t_H": False})
        self.assertTrue(screen.look(v, h, c=2.0, c_H=t_h)["passed"], "t_H exactly at c_H passes")
        self.assertTrue(screen.look(v, h, c=2.0, c_H=None)["passed"], "S1-X has no guard")
        self.assertAlmostEqual(guarded["t_H"], t_h)
        self.assertEqual(guarded["n"], len(V_DAYS) + len(H_DAYS))

    def test_the_label(self):
        n_v, n_h = len(V_DAYS), len(H_DAYS)
        rng = np.random.default_rng(9)
        bv, bh = rng.normal(0.001, 0.01, n_v), rng.normal(0.001, 0.01, n_h)
        # Always in, at half the account, less a cost: beta (its excess is minus its costs).
        v = make_series(V_DAYS, 0.5 * bv - 1e-5, w=np.full(n_v, 0.5), b=bv)
        h = make_series(H_DAYS, 0.5 * bh - 1e-5, w=np.full(n_h, 0.5), b=bh)
        self.assertEqual(screen.label(v, h, c_X=1.1), "beta")
        # A program that earns well above what its exposure would have: alpha.
        v2 = make_series(V_DAYS, 0.5 * bv + rng.normal(0.003, 0.002, n_v), w=np.full(n_v, 0.5), b=bv)
        h2 = make_series(H_DAYS, 0.5 * bh + rng.normal(0.003, 0.002, n_h), w=np.full(n_h, 0.5), b=bh)
        self.assertEqual(screen.label(v2, h2, c_X=1.1), "alpha")


# ========================================================================================================= the floor
def always_in(span: tuple[dt.date, dt.date], *, seed: int, drift: float = 0.0, sessions: int | None = None,
              symbol: str = "SPY") -> screen.Series:
    """An always-in program's Train-era series on synthetic GBM bars: one lot, bought at the open of the run's second
    session and held (the engine's run of a buy-and-hold program), through `screen.series`."""
    days = weekdays(*span)[:sessions]
    rng = np.random.default_rng(seed)
    ret = rng.normal(drift, 0.011, len(days))
    closes = 100.0 * np.cumprod(1.0 + ret)
    opens = closes / (1.0 + rng.normal(0.0, 0.004, len(days)))
    with mock.patch.object(config, "sell_fees", side_effect=sell_fees):
        return screen.series([lot(1, symbol, days[1], "open", weight=0.5, hs=0.0001)],
                             bars_of(days, {symbol: (opens.tolist(), closes.tolist())}), universe=[symbol],
                             capital=E0)


SPAN_16, SPAN_22 = config.TRAIN_ERA_SEGMENTS


class Floor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.seg16 = always_in(SPAN_16, seed=11, drift=0.0004)
        cls.seg22 = always_in(SPAN_22, seed=12, drift=0.0002)
        cls.floor = screen.floor([cls.seg16, cls.seg22], fp_cap=0.12)

    def test_both_world_sets_and_the_maxima(self):
        fl = self.floor
        self.assertTrue(fl["eligible"], fl["why"])
        self.assertEqual(set(fl["sets"]), {"IND22", "IND1622"})
        self.assertEqual(fl["sets"]["IND22"]["pool"], len(self.seg22.days) - 2, "a pool starts at first decision + 2")
        self.assertEqual(fl["sets"]["IND1622"]["pool"], len(self.seg16.days) + len(self.seg22.days) - 4)
        for name, row in fl["sets"].items():
            self.assertEqual(row["c_p"], max(row["by_L"][str(L)]["c_p"] for L in screen.H_LENGTHS), name)
            self.assertEqual(row["c_H"], max(row["by_L"][str(L)]["c_H"] for L in screen.H_LENGTHS), name)
        self.assertEqual(fl["c_p"], max(row["c_p"] for row in fl["sets"].values()))
        self.assertEqual(fl["c_H"], max(row["c_H"] for row in fl["sets"].values()))
        self.assertEqual(fl["worlds"], 20_000)
        self.assertEqual(fl["seeds"]["IND22"]["194"], [20261010, 1010, 3, 194, 0])
        self.assertEqual(fl["seeds"]["IND1622"]["251"], [20261010, 1010, 5, 251, 0])
        # The program's own FP at c_p is under the cap in every cell (that is what c_p is), and the grid is 0.01.
        self.assertLessEqual(fl["own_fp"], 0.12)
        self.assertEqual(fl["own_fp"], screen.fp_at(fl, "R_N0", fl["c_p"]))
        self.assertGreater(screen.fp_at(fl, "R_N0", fl["c_p"] - 0.01), 0.12 - 1e-12 if fl["c_p"] > 0 else -1)
        self.assertAlmostEqual(round(fl["c_p"] * 100), fl["c_p"] * 100, places=9)
        # The holdout-only guard has its own point; a Gaussian-ish always-in program needs a c near the prior's.
        self.assertTrue(0.3 <= fl["c_p"] <= 2.5 and 0.3 <= fl["c_H"] <= 2.5, (fl["c_p"], fl["c_H"]))
        self.assertIsNotNone(fl["drift_kept"])
        json.dumps(fl)                                   # the family state keeps it as JSON

    def test_deterministic_and_placed_by_days(self):
        again = screen.floor([self.seg22, None, self.seg16], fp_cap=0.12)
        self.assertEqual(json.dumps(again, sort_keys=True), json.dumps(self.floor, sort_keys=True))

    def test_a_program_without_the_2016_19_history_uses_ind22_alone(self):
        fl = screen.floor([None, self.seg22], fp_cap=0.12)
        self.assertTrue(fl["eligible"])
        self.assertEqual(set(fl["sets"]), {"IND22"})
        self.assertEqual(fl["sets"]["IND22"], self.floor["sets"]["IND22"], "the same worlds, the same cell")
        only16 = screen.floor([self.seg16], fp_cap=0.12)
        self.assertEqual(set(only16["sets"]), {"IND1622"})
        self.assertEqual(only16["sets"]["IND1622"]["pool"], len(self.seg16.days) - 2)

    def test_the_300_session_pool(self):
        short = always_in(SPAN_22, seed=13, sessions=301)              # a pool of 299
        fl = screen.floor([short], fp_cap=0.12)
        self.assertFalse(fl["eligible"])
        self.assertIn("300", fl["why"])
        self.assertTrue(screen.floor([always_in(SPAN_22, seed=13, sessions=302)], fp_cap=0.12)["eligible"])
        mixed = screen.floor([always_in(SPAN_16, seed=14, sessions=301), self.seg22], fp_cap=0.12)
        self.assertEqual(set(mixed["sets"]), {"IND22"}, "a short 2016-19 history adds no world set")

    def test_the_walls(self):
        """No world ever holds a 2020, 2021, 2025 or 2026 session: a series reaching one makes the program
        ineligible."""
        for span in ((dt.date(2020, 1, 2), dt.date(2021, 12, 31)), (dt.date(2019, 6, 3), dt.date(2020, 6, 30)),
                     (dt.date(2025, 1, 2), dt.date(2025, 12, 31))):
            fl = screen.floor([always_in(span, seed=15), self.seg22], fp_cap=0.12)
            self.assertFalse(fl["eligible"], span)
            self.assertIn("Train-era", fl["why"])
        self.assertFalse(screen.floor([self.seg22, self.seg22], fp_cap=0.12)["eligible"], "two series for one span")
        self.assertFalse(screen.floor([], fp_cap=0.12)["eligible"])
        with self.assertRaises(ValueError):
            screen.floor([self.seg22], fp_cap=0.0)
        with self.assertRaises(ValueError):
            screen.floor([self.seg22], fp_cap=True)

    def test_never_invested_and_a_threshold_off_the_grid(self):
        days = weekdays(*SPAN_22)
        n = len(days)
        idle = make_series(days, np.zeros(n), w=np.zeros(n), invested=np.zeros(n, dtype=bool))
        self.assertIn("no exposure", screen.floor([idle], fp_cap=0.12)["why"])
        # One loss day and a steady small gain otherwise: at zero edge, every world that misses the loss day shows an
        # enormous t, so no grid c holds 12%.
        rng = np.random.default_rng(16)
        r = 1e-4 + rng.normal(0.0, 1e-7, n)
        r[n // 2] = -1e-4 * (n - 1)
        fl = screen.floor([make_series(days, r)], fp_cap=0.12)
        self.assertFalse(fl["eligible"])
        self.assertIn("above 5.00", fl["why"])
        self.assertIsNone(fl["c_p"])

    def test_the_study_draws_and_the_direct_statistic(self):
        """The vectorized cell is the public rule: its world draws follow the study's order (V piece, V start, H piece,
        H start, from default_rng([20261010, 1010, set_id, L, 0])), and every world's t* equals `precheck` + `look`
        computed directly on that world's null series."""
        worlds = 300
        parts = [self.seg16, self.seg22]
        arrays = {k: np.concatenate([np.asarray(getattr(p, k), dtype=float) for p in parts])
                  for k in ("r", "w", "b", "exits", "invested")}
        sizes = np.array([len(p.days) for p in parts])
        g0 = np.array([2, sizes[0] + 2])
        lens = sizes - 2
        pool = np.concatenate([np.arange(g, g + n) for g, n in zip(g0, lens)])
        kappa = arrays["r"][pool].sum() / arrays["w"][pool].sum()
        m_p = arrays["b"][pool].mean()
        cell = screen._cell(arrays, g0, lens, {"kappa": kappa, "m_P": m_p}, 5, 194, worlds)

        rng = np.random.default_rng([20261010, 1010, 5, 194, 0])
        p = lens / lens.sum()
        pv = rng.choice(2, size=worlds, p=p)
        sv = rng.integers(0, lens[pv])
        ph = rng.choice(2, size=worlds, p=p)
        sh = rng.integers(0, lens[ph])
        direct = {"R_N0": [], "X": [], "H": []}
        for i in range(worlds):
            iv = g0[pv[i]] + (sv[i] + np.arange(250)) % lens[pv[i]]
            ih = g0[ph[i]] + (sh[i] + np.arange(194)) % lens[ph[i]]

            def world(idx, null):
                return screen.Series(days=np.zeros(len(idx), dtype=np.int32), r=null[idx], w=arrays["w"][idx],
                                     b=arrays["b"][idx] - m_p, exits=arrays["exits"][idx],
                                     invested=arrays["invested"][idx].astype(bool))

            r0 = arrays["r"] - arrays["w"] * kappa
            v, h = world(iv, r0), world(ih, r0)
            for key, variant in (("R_N0", "R"), ("X", "X")):
                pre = screen.precheck(v, variant=variant)
                lk = screen.look(v, h, c=-math.inf, c_H=None, variant=variant)
                direct[key].append(lk["t"] if pre["passed"] and lk["passed"] else -math.inf)
            t_h = screen.holdout_t(h.r)
            direct["H"].append(t_h if t_h is not None and h.r.sum() > screen.ZERO else -math.inf)
        for key, ts in direct.items():
            np.testing.assert_array_equal(cell[key], screen._pass_counts(np.array(ts)), err_msg=key)

    def test_fp_at_reads_the_worst_cell_at_or_below_c(self):
        fl = {"worlds": 100, "curves": {"IND22": {"194": {"R_N0": [100, 50, 20], "R_N1": [100, 90], "X": [5]},
                                                  "251": {"R_N0": [100, 60, 10], "R_N1": [100], "X": []}}}}
        self.assertEqual(screen.fp_at(fl, "R_N0", 0.01), 0.6)
        self.assertEqual(screen.fp_at(fl, "R_N0", 0.015), 0.6, "between grid points: the lower point")
        self.assertEqual(screen.fp_at(fl, "R_N0", 0.02), 0.2)
        self.assertEqual(screen.fp_at(fl, "R_N0", 3.0), 0.0)
        self.assertEqual(screen.fp_at(fl, "R_N1", 0.01), 0.9)
        self.assertEqual(screen.fp_at(fl, "X", 0.0), 0.05)
        self.assertIsNone(screen.fp_at({}, "R_N0", 1.0))
        self.assertIsNone(screen.fp_at({"worlds": 100, "curves": {"IND22": {"194": {}}}}, "R_N0", 1.0))


# ======================================================================================================= the receipt
class Receipts(unittest.TestCase):
    def test_the_loader_pins_the_sha(self):
        self.assertEqual(screen.receipt_sha256(FIXTURE), FAKE_SHA)
        self.assertIsNone(screen.receipt_sha256(FIXTURE.with_name("no-such-receipt.json")))
        rc = receipt()
        self.assertEqual((rc.receipt_sha256, rc.c_R, rc.c_X, rc.fp_cap, rc.owner_wall, rc.retry),
                         (FAKE_SHA, 1.25, 1.1, 0.12, 0.15, True))
        self.assertEqual(rc.r4["A3"], ("FAKE: an invented wall flag",))
        self.assertEqual(set(rc.fp), {"fp_zero_edge_at_cR", "power_at_cR", "binding_R"})
        for pin in ("f" * 64, FAKE_SHA.upper(), FAKE_SHA[:63], None, ""):
            with self.assertRaises(screen.ScreenRefused, msg=pin):
                screen.load_receipt(FIXTURE, pinned_sha256=pin)
        with self.assertRaises(screen.ScreenRefused):
            screen.load_receipt(FIXTURE.with_name("no-such-receipt.json"), pinned_sha256=FAKE_SHA)

    def test_a_malformed_receipt_refuses(self):
        doc = json.loads(FIXTURE.read_text())
        edits = [
            lambda d: d.pop("stated_beside_every_live_trade"),
            lambda d: d.pop("sha256"),
            lambda d: d.update(c_R=7.0),
            lambda d: d.update(c_R="1.25"),
            lambda d: d.update(c_X=None),
            lambda d: d.update(fp_cap=1.0),
            lambda d: d.update(owner_wall=-0.1),
            lambda d: d.update(R3_retry_permitted="yes"),
            lambda d: d["precheck"].update(rt_min=25),
            lambda d: d["lineage"].update(holdout_looks=2),
            lambda d: d.update(R4_flags={"A1": "a string, not a list"}),
            lambda d: d.update(stated_beside_every_live_trade="S1-R, c_used = {c_used}"),
        ]
        with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as tmp:
            for i, edit in enumerate(edits):
                bad = copy.deepcopy(doc)
                edit(bad)
                path = Path(tmp) / f"bad{i}.json"
                path.write_text(json.dumps(bad))
                with self.assertRaises(screen.ScreenRefused, msg=i):
                    screen.load_receipt(path, pinned_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            path = Path(tmp) / "not.json"
            path.write_text("{not json")
            with self.assertRaises(screen.ScreenRefused):
                screen.load_receipt(path, pinned_sha256=hashlib.sha256(path.read_bytes()).hexdigest())

    def block(self, **over):
        rc = receipt()
        b = {"name": "S1", "receipt_sha256": rc.receipt_sha256, "c_R": rc.c_R, "c_X": rc.c_X, "fp_cap": rc.fp_cap,
             "owner_wall": rc.owner_wall, "retry": rc.retry, "r4": {k: list(v) for k, v in rc.r4.items()},
             "beside": rc.beside}
        b.update(over)
        return b

    def test_the_policy_block(self):
        rc = screen.pinned_receipt(self.block())
        self.assertEqual(rc, screen.Receipt(**{**receipt().__dict__, "fp": {}}))
        self.assertIsNone(screen.pinned_receipt(None))
        self.assertIsNone(screen.pinned_receipt("S1"))
        self.assertIsNone(screen.pinned_receipt(self.block(owner_wall=None)).owner_wall, "the wall is optional")
        self.assertFalse(screen.pinned_receipt(self.block(retry="true")).retry, "a retry is a literal true")
        self.assertEqual(screen.pinned_receipt(self.block(r4=None)).r4, {})
        for over in ({"receipt_sha256": None}, {"receipt_sha256": "F" * 64}, {"receipt_sha256": "f" * 63},
                     {"c_R": None}, {"c_R": float("nan")}, {"c_R": True}, {"c_R": 5.01}, {"c_R": -0.1},
                     {"c_X": None}, {"fp_cap": None}, {"fp_cap": 0.0}, {"fp_cap": 1.0}, {"name": "D2"},
                     {"owner_wall": 0.0}, {"owner_wall": "0.15"}, {"r4": ["A1"]}, {"r4": {"A1": [1]}},
                     {"beside": None}, {"beside": "S1-R, c_used = {c_used}"}):
            self.assertIsNone(screen.pinned_receipt(self.block(**over)), over)

    def test_the_committed_pin(self):
        """CI's pin: a lane's screen block in the committed policy.json that pins a receipt must name the sha256 of
        docs/benchmarks/equity_screen_1.json, which `load_receipt` reads to the same figures; with none pinned (E1
        merges so: the integrator pins it), every verdict refuses."""
        policy = json.loads(Path(REAL_POLICY_PATH).read_text())
        elane = policy.get("elane") if isinstance(policy.get("elane"), dict) else {}
        screens = elane.get("screens") if isinstance(elane.get("screens"), dict) else {}
        path = Path(ci.REPO) / screen.RECEIPT_PATH
        for lane in ("beta", "equity"):
            pinned = screen.pinned_receipt(screens.get(lane))
            if pinned is None:
                with self.assertRaises(screen.ScreenRefused):
                    screen.verdict(make_series(V_DAYS, np.ones(250)), make_series(H_DAYS, np.ones(200)),
                                   receipt=pinned, program_floor={"eligible": True})
                continue
            self.assertTrue(path.exists(), "a pinned receipt needs its file")
            loaded = screen.load_receipt(path, pinned_sha256=pinned.receipt_sha256)
            self.assertEqual((loaded.c_R, loaded.c_X, loaded.fp_cap, loaded.owner_wall, loaded.retry, loaded.r4,
                              loaded.beside),
                             (pinned.c_R, pinned.c_X, pinned.fp_cap, pinned.owner_wall, pinned.retry, pinned.r4,
                              pinned.beside), lane)


# ======================================================================================================= the verdict
def floor_of(c_p=0.8, c_H=0.9, **over):
    """A floor result as `floor` writes it (an eligible one; curves of an invented program)."""
    curve = [20_000 - 30 * k for k in range(500)]
    base = {"screen": "S1", "eligible": True, "why": None, "c_p": c_p, "c_H": c_H, "fp_cap": 0.12, "worlds": 20_000,
            "sets": {}, "seeds": {}, "own_fp": None, "drift_kept": None,
            "curves": {"IND22": {"194": {"R_N0": curve, "R_N1": [min(20_000, x + 4000) for x in curve], "X": curve}}}}
    base.update(over)
    return base


class Verdict(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(21)
        n_v, n_h = len(V_DAYS), len(H_DAYS)
        self.v = make_series(V_DAYS, exact(rng, n_v, 0.0016), b=exact(rng, n_v, 0.0))
        self.h = make_series(H_DAYS, exact(rng, n_h, 0.0016), b=exact(rng, n_h, 0.0))
        self.t = screen.pooled_t(self.v.r, self.h.r)
        self.t_h = screen.holdout_t(self.h.r)
        self.assertTrue(2.5 < self.t < 4.5 and 1.5 < self.t_h < 3.5, (self.t, self.t_h))
        self.rc = receipt()

    def test_refused_without_a_receipt(self):
        with self.assertRaises(screen.ScreenRefused):
            screen.verdict(self.v, self.h, receipt=None, program_floor=floor_of())

    def test_a_pass_and_what_it_states(self):
        out = screen.verdict(self.v, self.h, receipt=self.rc, program_floor=floor_of())
        self.assertTrue(out["passed"], out["why"])
        self.assertEqual((out["screen"], out["c_R"], out["c_p"], out["c_H"], out["c_used"]),
                         ("S1", 1.25, 0.8, 0.9, 1.25))
        self.assertAlmostEqual(out["t"], self.t)
        self.assertAlmostEqual(out["t_H"], self.t_h)
        self.assertEqual(out["own_fp"], (20_000 - 30 * 125) / 20_000, "the program's FP read at c_used")
        self.assertEqual(out["drift_kept"], min(20_000, 20_000 - 30 * 125 + 4000) / 20_000)
        self.assertEqual(out["fp_x"], (20_000 - 30 * 110) / 20_000, "S1-X's FP at c_X")
        self.assertEqual(out["label"], "alpha")
        self.assertEqual(out["receipt"], FAKE_SHA)
        self.assertEqual(out["r4"], ["A3: FAKE: an invented wall flag"])
        self.assertEqual(out["deviations"], list(screen.DEVIATIONS))
        self.assertIn("A2 close fills", out["deviations"][0])
        self.assertTrue(out["windows"]["ok"])
        json.dumps(out)

    def test_c_used_is_the_larger_of_c_r_and_c_p(self):
        above = screen.verdict(self.v, self.h, receipt=self.rc, program_floor=floor_of(c_p=round(self.t + 0.01, 2)))
        self.assertEqual(above["c_used"], round(self.t + 0.01, 2))
        self.assertFalse(above["passed"])
        self.assertIn("step 2", above["why"])
        below = screen.verdict(self.v, self.h, receipt=self.rc, program_floor=floor_of(c_p=0.0))
        self.assertEqual(below["c_used"], 1.25)

    def test_f1_fails_a_weak_holdout(self):
        out = screen.verdict(self.v, self.h, receipt=self.rc, program_floor=floor_of(c_H=round(self.t_h + 0.01, 2)))
        self.assertFalse(out["passed"])
        self.assertEqual(out["look"]["checks"], {"t": True, "sum_h": True, "t_H": False})
        self.assertIn("t_H", out["why"])

    def test_the_floor_must_be_eligible_and_the_receipts(self):
        for fl, why in ((floor_of(eligible=False, why="no pool of >= 300 sessions"), "300"),
                        (floor_of(c_p=None), "floor"), (floor_of(c_H=7.0), "floor"), ({}, "floor"),
                        (floor_of(fp_cap=0.10), "fp_cap")):
            out = screen.verdict(self.v, self.h, receipt=self.rc, program_floor=fl)
            self.assertFalse(out["passed"])
            self.assertIn(why, out["why"])
            self.assertIn(out["label"], ("alpha", "beta"), "the label is computed for every program")

    def test_the_precheck_gates(self):
        n = len(V_DAYS)
        idle = make_series(V_DAYS, self.v.r, invested=np.zeros(n, dtype=bool))
        out = screen.verdict(idle, self.h, receipt=self.rc, program_floor=floor_of())
        self.assertFalse(out["passed"])
        self.assertEqual(out["why"], "step 1, the pre-check: activity")

    def test_the_calibrated_windows(self):
        ok = floor_of()
        cases = [
            (make_series(weekdays(dt.date(2024, 1, 2), dt.date(2024, 12, 31))[:250], self.v.r), self.h),
            (make_series(V_DAYS[:249], self.v.r[:249]), self.h),
            (self.v, make_series(H_DAYS[:193], self.h.r[:193])),
            (self.v, make_series(weekdays(dt.date(2026, 1, 2), dt.date(2027, 1, 29))[:252],
                                 exact(np.random.default_rng(1), 252, 0.0016))),
            (self.v, make_series(weekdays(dt.date(2026, 6, 1), dt.date(2027, 6, 1))[:200], self.h.r)),
        ]
        for v, h in cases:
            out = screen.verdict(v, h, receipt=self.rc, program_floor=ok)
            self.assertFalse(out["passed"])
            self.assertIn("the windows", out["why"])
        edge = screen.verdict(self.v, make_series(H_DAYS[:194], self.h.r[:194]), receipt=self.rc, program_floor=ok)
        self.assertTrue(edge["windows"]["ok"], "194 sessions is calibrated")

    def test_the_line_beside_every_live_trade(self):
        out = screen.verdict(self.v, self.h, receipt=self.rc, program_floor=floor_of())
        line = screen.beside_line(out, self.rc)
        self.assertTrue(line.startswith("S1-R, c_used = 1.25, c_H = 0.90, this program's FP at zero edge = 81.25% "),
                        line)
        self.assertIn("drift-kept pass rate = 100.00%", line)
        self.assertIn("S1-X: alpha (FP 83.50%)", line)
        self.assertIn("contamination: FAKE fixture sentence", line)
        self.assertTrue(line.endswith("; R4 flags: A3: FAKE: an invented wall flag"), line)
        self.assertNotIn("{", line)
        bare = screen.beside_line({"label": "beta"}, self.rc)
        self.assertIn("c_used = unmeasured", bare)
        self.assertIn("S1-X: beta", bare)
        self.assertNotIn("R4 flags", bare)


# ======================================================================================================= the lineage
class Lineage(unittest.TestCase):
    def test_r3_the_one_validation_only_retry(self):
        rc = receipt()
        self.assertTrue(screen.retry_permitted(rc, first_precheck_failed=True))
        self.assertFalse(screen.retry_permitted(None, first_precheck_failed=True), "no receipt: no retry")
        self.assertFalse(screen.retry_permitted(screen.Receipt(**{**rc.__dict__, "retry": False}),
                                                first_precheck_failed=True), "the receipt must permit it")
        self.assertFalse(screen.retry_permitted(rc, first_precheck_failed=False), "only after a FAILED pre-check")
        self.assertFalse(screen.retry_permitted(rc, first_precheck_failed=True, tries=2), "never a third try")
        self.assertFalse(screen.retry_permitted(rc, first_precheck_failed=True, looks=1), "never after a look")
        self.assertTrue(screen.retry_permitted(rc, first_precheck_failed=True, retry_sha="ab", recorded_sha="ab"))
        self.assertFalse(screen.retry_permitted(rc, first_precheck_failed=True, retry_sha="ab", recorded_sha="cd"),
                         "the version hashed at the first try, and no other")
        self.assertFalse(screen.retry_permitted(rc, first_precheck_failed=True, retry_sha="ab"))
        self.assertFalse(screen.retry_permitted(rc, first_precheck_failed=True, recorded_sha="ab"))

    def test_one_look_a_lineage(self):
        self.assertTrue(screen.look_permitted(0, precheck_passed=True))
        self.assertFalse(screen.look_permitted(1, precheck_passed=True), "one look a lineage")
        self.assertFalse(screen.look_permitted(0, precheck_passed=False), "a failed pre-check spends no look")
        # A lineage's path: try 1 fails its pre-check (no look), R3's retry passes it, the one look is spent; nothing
        # follows.
        rc = receipt()
        tries, looks = 1, 0
        self.assertFalse(screen.look_permitted(looks, precheck_passed=False))
        self.assertTrue(screen.retry_permitted(rc, first_precheck_failed=True, tries=tries, looks=looks))
        tries += 1
        self.assertTrue(screen.look_permitted(looks, precheck_passed=True))
        looks += 1
        self.assertFalse(screen.look_permitted(looks, precheck_passed=True))
        self.assertFalse(screen.retry_permitted(rc, first_precheck_failed=True, tries=tries, looks=looks))

    def test_d3_same_lineage(self):
        rng = np.random.default_rng(31)
        a = rng.normal(0, 0.01, 500)
        close = 0.9 * a + math.sqrt(1 - 0.81) * rng.normal(0, 0.01, 500)
        far = 0.3 * a + math.sqrt(1 - 0.09) * rng.normal(0, 0.01, 500)
        self.assertTrue(screen.same_lineage(a, close))
        self.assertFalse(screen.same_lineage(a, far))
        self.assertTrue(screen.same_lineage(a, far, same_template=True), "the same template is the same lineage")
        self.assertFalse(screen.same_lineage(a, np.zeros(500)), "no variance, no correlation")
        with self.assertRaises(ValueError):
            screen.same_lineage(a, close[:-1])
        # Aligned on common sessions: two series over overlapping spans.
        days = weekdays(dt.date(2022, 1, 3), dt.date(2024, 12, 31))[:600]
        s1 = make_series(days[:500], a)
        s2 = make_series(days[100:600], np.concatenate([close[100:], rng.normal(0, 0.01, 100)]))
        self.assertTrue(screen.same_lineage(s1, s2))
        by_day = {d.isoformat(): float(x) for d, x in zip(days[100:600], s2.r)}
        self.assertTrue(screen.same_lineage(s1, by_day))
        self.assertFalse(screen.same_lineage(s1, {days[0].isoformat(): 0.1}), "under two common sessions")
        with self.assertRaises(ValueError):
            screen.same_lineage(s1, a)

    def test_r4_flags(self):
        rc = receipt()
        self.assertEqual(screen.r4_flags(rc, "A3"), ["FAKE: an invented wall flag"])
        self.assertEqual(screen.r4_flags(rc, "A1"), [])
        self.assertEqual(screen.r4_flags(rc), ["A3: FAKE: an invented wall flag"])
        self.assertEqual(screen.r4_flags(None), [])


if __name__ == "__main__":
    unittest.main()
