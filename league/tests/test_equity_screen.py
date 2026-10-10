"""THE SHARE SCREEN S1 (league/equity/screen.py; release E1, amendment A9): the accounting on golden synthetic series
(open and close fills, fees), the pre-check, the look with F1's holdout guard, the floor on synthetic Train-era runs
(both world sets, the study's draws, ineligibility), refusal without a receipt, one try and one look a lineage (R3),
D3's same lineage, R4's flags and the line beside every live trade. AND S2 BESIDE IT (amendment A11, HOUSE-RULE.md
section 9): every conformance vector reproduced exactly, the exact floor against brute force, eligibility, the look and
the verdict at their boundaries, A12's look cap, receipt 2's loader, and the routing of every entry point by the pinned
receipt (an "S1" block runs S1, an "S2" block runs S2; no pinned receipt refuses).

Invented prices, series and figures only. The receipts are league/tests/fixtures/equity_screen_fake.json and
equity_screen_2_fake.json (marked FAKE: each study's keys, invented figures; receipt 2's fake floor 0.90 and margin 0.05
are the ones the conformance vectors were computed with); the committed receipts are judged only through the
repository's pin. The conformance pools are HOUSE-RULE.md's synthetic generator (numpy 2.5.3's Generator streams). `config.sell_fees`
and `config.half_spread` are core's: the accounting tests patch `sell_fees` with the documented rule (SEC and TAF, each
rounded up to the cent) and give every lot its `hs`. The floor's Train-era runs are synthetic bars built here (core's
`synth.synthetic_store` writes a store; the screen reads `Bars`, so a store adds nothing the bars do not)."""

from __future__ import annotations

import copy
import dataclasses
import datetime as dt
import hashlib
import inspect
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
        """CI's pin, ROUTED by each lane's block (A11): a lane's screen block in the committed policy.json that pins a
        receipt must name the sha256 of its screen's file (docs/benchmarks/equity_screen_1.json for "S1",
        equity_screen_2.json for "S2"), which `load_receipt` reads, by the block's screen, to the same figures; with
        none pinned (E1 merges so: the integrator pins it), every verdict refuses."""
        policy = json.loads(Path(REAL_POLICY_PATH).read_text())
        elane = policy.get("elane") if isinstance(policy.get("elane"), dict) else {}
        screens = elane.get("screens") if isinstance(elane.get("screens"), dict) else {}
        for lane in ("beta", "equity"):
            block = screens.get(lane)
            pinned = screen.pinned_receipt(block)
            if pinned is None:
                with self.assertRaises(screen.ScreenRefused):
                    screen.verdict(make_series(V_DAYS, np.ones(250)), make_series(H_DAYS, np.ones(200)),
                                   receipt=pinned, program_floor={"eligible": True})
                continue
            which = screen.screen_of(pinned)
            self.assertEqual(which, screen.screen_of(block), lane)
            path = Path(ci.REPO) / screen.receipt_path(pinned)
            self.assertTrue(path.exists(), f"a pinned receipt needs its file ({path.name})")
            loaded = screen.load_receipt(path, pinned_sha256=pinned.receipt_sha256, screen=which)
            self.assertEqual(dataclasses.replace(loaded, fp={}), dataclasses.replace(pinned, fp={}), lane)


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


# ================================================================================================= S2 (amendment A11)
FIXTURE_S2 = FIXTURE.with_name("equity_screen_2_fake.json")
FAKE_SHA_S2 = hashlib.sha256(FIXTURE_S2.read_bytes()).hexdigest()
#: 2026's NYSE holidays from Jan 2 through Oct 9: the holdout's sessions are the weekdays without them.
HOLIDAYS_2026 = {dt.date(2026, 1, 19), dt.date(2026, 2, 16), dt.date(2026, 4, 3), dt.date(2026, 5, 25),
                 dt.date(2026, 6, 19), dt.date(2026, 7, 3), dt.date(2026, 9, 7)}


def receipt_s2() -> screen.ReceiptS2:
    return screen.load_receipt_s2(FIXTURE_S2, pinned_sha256=FAKE_SHA_S2)


def s2_block(**over) -> dict:
    """A policy.json `elane.screens.<lane>` block pinning the fake receipt 2 (HOUSE-RULE section 9's shape)."""
    rc = receipt_s2()
    b = {"name": "S2", "receipt_sha256": rc.receipt_sha256, "c_R": 0.0, "c_H_floor": rc.c_H_floor,
         "c_H_margin": rc.c_H_margin, "c_X": rc.c_X, "fp_cap": rc.fp_cap, "owner_wall": rc.owner_wall,
         "retry": rc.retry, "r4": {k: list(v) for k, v in rc.r4.items()}, "beside": rc.beside}
    b.update(over)
    return b


def conformance_pool(span: int, n: int) -> dict:
    """HOUSE-RULE section 9's synthetic pool: about 60% invested days at w 0.5, r ~ N(4e-4, 6e-3) on them, 0 else."""
    rng = np.random.default_rng([20261010, 2026, span, n])
    on = rng.random(n) < 0.6
    w = np.where(on, 0.5, 0.0)
    r = np.where(on, rng.normal(0.0004, 0.006, n), 0.0)
    b = rng.normal(0.0004, 0.01, n)
    exits = (on & (rng.random(n) < 0.15)).astype(np.int64)
    return dict(r=r, w=w, b=b, exits=exits, invested=on)


def pool_series(span: int, n: int, *, pool: dict | None = None) -> screen.Series:
    """A Train-era series (on the span's first n + 2 weekdays) whose pool, from POOL_SKIP on, is `pool` (default
    `conformance_pool(span, n)`): the two sessions before it are a run's first, which the floor drops."""
    p = conformance_pool(span, n) if pool is None else pool
    days = weekdays(*config.TRAIN_ERA_SEGMENTS[span])[:n + screen.POOL_SKIP]
    assert len(days) == n + screen.POOL_SKIP
    lead = screen.POOL_SKIP
    return screen.Series(days=np.array([ordinal(d) for d in days], dtype=np.int32),
                         r=np.concatenate([np.zeros(lead), p["r"]]), w=np.concatenate([np.zeros(lead), p["w"]]),
                         b=np.concatenate([np.zeros(lead), p["b"]]),
                         exits=np.concatenate([np.zeros(lead, dtype=np.int64), p["exits"]]),
                         invested=np.concatenate([np.zeros(lead, dtype=bool), p["invested"]]))


def conformance_segments(n_0: int | None, n_1: int) -> list:
    return [None if n_0 is None else pool_series(0, n_0), pool_series(1, n_1)]


#: HOUSE-RULE.md section 9's conformance vectors (work/adopt/conformance.json; synthetic pools, floor 0.90, margin 0.05):
#: (n_0, n_1) -> c_pF1, c_H,used, own_fp, holdout_only, drift_kept and, per cell, T, k_F1, HO[k_used], G_N0[k_used],
#: G_N1[k_used], kappa_V, kappa_H. The House must reproduce every integer exactly.
CONFORMANCE = {
    "V1": {"n": (1004, 751), "c_pF1": 1.2, "c_H_used": 1.25, "own_fp": 0.016961896005720706,
           "holdout_only": 0.10883190883190884, "drift_kept": 0.1102057865404479, "cells": {
               "IND22-NO|194": (231308, 88, 6468, 1051, 20544, 0.0014957300051544158, 0.0014957300051544158),
               "IND22-NO|251": (188501, 94, 2510, 335, 19320, 0.0014957300051544158, 0.0014957300051544158),
               "IND1622-NO|194": (2302560, 100, 195488, 34644, 206247, 0.00090319869842263, 0.00090319869842263),
               "IND1622-NO|251": (2202525, 120, 239705, 37359, 242731, 0.00090319869842263, 0.00090319869842263)}},
    "V2": {"n": (1004, 400), "c_pF1": 0.61, "c_H_used": 0.9, "own_fp": 0.03275655643407267,
           "holdout_only": 0.0881704628949302, "drift_kept": 0.09385922567399115, "cells": {
               "IND1622-NO|194": (1366444, 61, 120480, 44760, 123031, 0.0005674426375355492, 0.0005674426375355492),
               "IND1622-NO|251": (1309216, 56, 79316, 28914, 122882, 0.0005721864937631882, 0.0005721864937631882)}},
    "V3": {"n": (None, 751), "c_pF1": 0.94, "c_H_used": 0.99, "own_fp": 0.012740588306500423,
           "holdout_only": 0.08921438082556592, "drift_kept": 0.18054546129728755, "cells": {
               "IND22-NO|194": (231308, 88, 18788, 2947, 29423, 0.0014957300051544158, 0.0014957300051544158),
               "IND22-NO|251": (188501, 94, 16817, 886, 34033, 0.0014957300051544158, 0.0014957300051544158)}},
}


class S2Conformance(unittest.TestCase):
    """HOUSE-RULE section 9: the House reproduces every conformance vector exactly."""

    def test_every_vector(self):
        rc = receipt_s2()
        self.assertEqual((rc.fp_cap, rc.c_H_floor, rc.c_H_margin), (0.12, 0.9, 0.05), "the vectors' settings")
        for name, want in CONFORMANCE.items():
            n_0, n_1 = want["n"]
            fl = screen.floor_s2(conformance_segments(n_0, n_1), receipt=rc)
            self.assertTrue(fl["eligible"], (name, fl["why"]))
            self.assertEqual((fl["screen"], fl["method"], fl["why"]), ("S2", "exact", None), name)
            self.assertEqual((fl["c_pF1"], fl["c_H_used"]), (want["c_pF1"], want["c_H_used"]), name)
            self.assertEqual((fl["k_F1"], fl["k_used"]), (round(want["c_pF1"] * 100), round(want["c_H_used"] * 100)))
            self.assertEqual((fl["own_fp"], fl["holdout_only"], fl["drift_kept"]),
                             (want["own_fp"], want["holdout_only"], want["drift_kept"]), name)
            self.assertEqual(set(fl["cells"]), set(want["cells"]), name)
            self.assertEqual(list(fl["sets"]), list(dict.fromkeys(c.split("|")[0] for c in want["cells"])), name)
            for cell, (T, k_f1, ho, g0, g1, kappa_v, kappa_h) in want["cells"].items():
                set_name, L = cell.split("|")
                self.assertEqual(fl["cells"][cell], {"T": T, "HO_used": ho, "G_N0_used": g0, "G_N1_used": g1},
                                 (name, cell))
                self.assertEqual(fl["sets"][set_name]["by_L"][L], {"k_F1": k_f1, "T": T}, (name, cell))
                pools = ([conformance_pool(0, n_0)] if set_name == "IND1622-NO" else []) + [conformance_pool(1, n_1)]
                self.assertEqual(fl["sets"][set_name]["pools"], [len(p["r"]) for p in pools])
                consts = screen._role_constants(pools, int(L))
                self.assertEqual((consts["kappa_V"], consts["kappa_H"]), (kappa_v, kappa_h), (name, cell))
            json.dumps(fl)                                       # the family state keeps it as JSON

    def test_v4_is_ineligible(self):
        fl = screen.floor_s2(conformance_segments(None, 549), receipt=receipt_s2())
        self.assertFalse(fl["eligible"])
        self.assertEqual(fl["why"], "no eligible floor set (IND22-NO needs a 2022-24 pool >= 550; IND1622-NO needs "
                                    "2016-19 and 2022-24 pools >= 251 each)")
        self.assertIsNone(fl["c_H_used"])

    def test_deterministic_and_placed_by_days(self):
        rc = receipt_s2()
        a = screen.floor_s2([pool_series(0, 1004), pool_series(1, 751)], receipt=rc)
        b = screen.floor_s2([pool_series(1, 751), None, pool_series(0, 1004)], receipt=rc)
        self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True))

    def test_c_h_used_is_the_receipts_floor_or_c_pf1_plus_its_margin(self):
        rc = receipt_s2()
        segs = conformance_segments(None, 751)                                   # c_pF1 0.94
        for c_floor, c_margin, want in ((0.9, 0.05, 0.99), (1.5, 0.05, 1.5), (0.0, 0.0, 0.94), (0.9, 0.2, 1.14)):
            fl = screen.floor_s2(segs, receipt=dataclasses.replace(rc, c_H_floor=c_floor, c_H_margin=c_margin))
            self.assertEqual((fl["c_pF1"], fl["c_H_used"]), (0.94, want), (c_floor, c_margin))
            self.assertEqual((fl["c_H_floor"], fl["c_H_margin"]), (c_floor, c_margin), "as run")
        over = screen.floor_s2(segs, receipt=dataclasses.replace(rc, c_H_margin=5.0))
        self.assertFalse(over["eligible"], "k_used > 500")
        self.assertIn("above 5.00", over["why"])
        self.assertEqual(over["c_pF1"], 0.94)


def brute(pools, L, lv, null, edge, act):
    """Direct enumeration of every valid (V piece, V start, H piece, H start) tuple (house_ref's test T3): T, the
    inclusion-weighted role constants from direct counts, and the holdout-only and gate counts at every grid c."""
    lens = [len(p["r"]) for p in pools]
    tuples = []
    for a, na in enumerate(lens):
        if na < lv:
            continue
        for b in range(na):
            vset = {(b + i) % na for i in range(lv)}
            for c, nc in enumerate(lens):
                if nc < L:
                    continue
                for d in range(nc):
                    if a == c and vset & {(d + i) % nc for i in range(L)}:
                        continue
                    tuples.append((a, b, c, d))
    cv, ch = [np.zeros(n) for n in lens], [np.zeros(n) for n in lens]
    for a, b, c, d in tuples:
        for i in range(lv):
            cv[a][(b + i) % lens[a]] += 1
        for i in range(L):
            ch[c][(d + i) % lens[c]] += 1
    k = range(len(pools))
    kv = sum(cv[j] @ pools[j]["r"] for j in k) / sum(cv[j] @ pools[j]["w"] for j in k)
    kh = sum(ch[j] @ pools[j]["r"] for j in k) / sum(ch[j] @ pools[j]["w"] for j in k)
    mv = sum(cv[j] @ pools[j]["b"] for j in k) / sum(cv[j].sum() for j in k)
    mh = sum(ch[j] @ pools[j]["b"] for j in k) / sum(ch[j].sum() for j in k)
    gv, gh = (kv, kh) if null == "N0" else (kv - mv, kh - mh)
    gv, gh = gv - edge / 252.0, gh - edge / 252.0
    ts, pres = [], []
    for a, b, c, d in tuples:
        pa, pc = pools[a], pools[c]
        vi = [(b + i) % lens[a] for i in range(lv)]
        hi = [(d + i) % lens[c] for i in range(L)]
        xv = np.array([pa["r"][i] - pa["w"][i] * gv for i in vi])
        xh = np.array([pc["r"][i] - pc["w"][i] * gh for i in hi])
        active = sum(pa["exits"][i] for i in vi) >= act[0] or sum(pa["invested"][i] for i in vi) >= act[1]
        sd = xh.std(ddof=1)
        if not (xh.sum() > screen.ZERO and sd >= screen.ZERO):
            continue
        ts.append(xh.mean() / sd * math.sqrt(L))
        pres.append(bool(active and xv.sum() > screen.ZERO))
    ts, pres = np.array(ts), np.array(pres, dtype=bool)
    hit = ts[:, None] >= screen.GRID[None, :] if len(ts) else np.zeros((0, len(screen.GRID)), dtype=bool)
    ties = sorted({int(round(t * 100)) for t in ts if abs(t * 100 - round(t * 100)) < 1e-7})
    return {"T": len(tuples), "ho": hit.sum(0), "gate": hit[pres].sum(0), "kappa_V": kv, "kappa_H": kh, "m_V": mv,
            "m_H": mh, "ties": ties}


class S2BruteForce(unittest.TestCase):
    """The exact cell against direct enumeration, with V and H shrunk (V 5, H 3, activity 1 round trip or 3 invested
    days): pieces shorter than V + H, a single piece, several pieces; under N0, N1 and with an edge. A t_H that equals a
    grid point in exact arithmetic may round either way, so its k is left out (as house_ref's test does)."""

    def test_every_tuple(self):
        rng = np.random.default_rng(20261010)
        for lens in ([13, 9], [9], [7, 12], [12, 6, 8], [20], [4, 9]):
            pools = []
            for n in lens:
                w = rng.uniform(0.0, 1.0, n) * (rng.uniform(size=n) > 0.2)
                pools.append(dict(r=rng.normal(0.001, 0.02, n) * (w > 0) + 0.001 * w, w=w,
                                  b=rng.normal(0.0005, 0.01, n), exits=rng.integers(0, 2, n), invested=w > 0))
            for null, edge in (("N0", 0.0), ("N1", 0.0), ("N0", 2.5)):
                bf = brute(pools, 3, 5, null, edge, (1, 3))
                ex = screen._exact_cell(pools, 3, null=null, edge=edge, lv=5, act=(1, 3))
                keep = np.ones(len(screen.GRID), dtype=bool)
                keep[[k for k in bf["ties"] if 0 <= k < len(keep)]] = False
                what = (lens, null, edge)
                self.assertEqual(ex["T"], bf["T"], what)
                np.testing.assert_array_equal(ex["holdout_only"][keep], bf["ho"][keep], err_msg=str(what))
                np.testing.assert_array_equal(ex["gate"][keep], bf["gate"][keep], err_msg=str(what))
                for key in ("kappa_V", "kappa_H", "m_V", "m_H"):
                    self.assertAlmostEqual(ex["consts"][key], bf[key], delta=1e-12, msg=(what, key))
                self.assertGreater(int(keep.sum()), 400, what)

    def test_the_counts_in_one_piece(self):
        """One piece of n: T = n (n - V - L + 1); W = U = n - V - L + 1; a piece shorter than V + H holds no pair."""
        U, W, T = screen._tuple_counts([20], 3, 5)
        self.assertEqual((U.tolist(), W.tolist(), T), ([13], [13], 260))
        U, W, T = screen._tuple_counts([7, 12], 3, 5)
        self.assertEqual((U.tolist(), W.tolist()), ([12 + 0, 7 + 5], [12 + 0, 7 + 5]))
        self.assertEqual(T, 7 * 12 + 12 * 12)
        self.assertEqual(screen._tuple_counts([7], 3, 5)[2], 0)


class S2Eligibility(unittest.TestCase):
    def setUp(self):
        self.rc = receipt_s2()

    def floor(self, segments):
        return screen.floor_s2(segments, receipt=self.rc)

    def test_the_sets(self):
        no_22 = self.floor([pool_series(0, 1004)])
        self.assertFalse(no_22["eligible"], "no 2022-24 pool")
        self.assertEqual(no_22["why"], screen.NO_SET_WHY)
        self.assertFalse(self.floor([None, pool_series(1, 549)])["eligible"], "549 and no 2016-19 pool")
        with_16 = self.floor([pool_series(0, 1004), pool_series(1, 549)])
        self.assertTrue(with_16["eligible"], with_16["why"])
        self.assertEqual(list(with_16["sets"]), ["IND1622-NO"], "549 with a 2016-19 pool: IND1622-NO only")
        self.assertEqual(list(self.floor([None, pool_series(1, 550)])["sets"]), ["IND22-NO"])
        self.assertEqual(list(self.floor([pool_series(0, 250), pool_series(1, 751)])["sets"]), ["IND22-NO"],
                         "a 2016-19 pool of 250 adds no set")
        self.assertEqual(list(self.floor([pool_series(0, 251), pool_series(1, 400)])["sets"]), ["IND1622-NO"])

    def test_no_exposure_and_series_that_are_not_finite(self):
        idle = conformance_pool(1, 751)
        idle["w"], idle["r"] = np.zeros(751), np.zeros(751)
        fl = self.floor([None, pool_series(1, 751, pool=idle)])
        self.assertFalse(fl["eligible"])
        self.assertIn("no exposure", fl["why"])
        for key in ("r", "w", "b"):
            bad = conformance_pool(1, 751)
            bad[key] = bad[key].copy()
            bad[key][10] = np.nan
            fl = self.floor([None, pool_series(1, 751, pool=bad)])
            self.assertFalse(fl["eligible"], key)
            self.assertIn("not finite", fl["why"], key)
            self.assertEqual(fl["cells"], {}, "an ineligible floor states no figure")

    def test_the_walls(self):
        """No world ever holds a 2020, 2021, 2025 or 2026 session; two series for one span; unequal arrays."""
        seg22 = pool_series(1, 751)
        for span in ((dt.date(2020, 1, 2), dt.date(2021, 12, 31)), (dt.date(2019, 6, 3), dt.date(2020, 6, 30)),
                     (dt.date(2025, 1, 2), dt.date(2025, 12, 31))):
            days = weekdays(*span)[:300]
            fl = self.floor([make_series(days, np.full(len(days), 1e-4)), seg22])
            self.assertFalse(fl["eligible"], span)
            self.assertIn("Train-era", fl["why"])
        two = self.floor([seg22, pool_series(1, 600)])
        self.assertFalse(two["eligible"])
        self.assertIn("two series", two["why"])
        ragged = dataclasses.replace(seg22, w=seg22.w[:-1])
        with self.assertRaises(ValueError):
            self.floor([ragged])
        self.assertFalse(self.floor([])["eligible"])
        with self.assertRaises(screen.ScreenRefused):
            screen.floor_s2([seg22], receipt=None)
        with self.assertRaises(screen.ScreenRefused):
            screen.floor_s2([seg22], receipt=receipt())

    def test_no_c_on_the_grid_holds_the_cap(self):
        """One loss day and a steady small gain otherwise: at zero edge almost every holdout that misses the loss day
        shows an enormous t_H, so no c <= 5.00 holds the holdout-only rate at 12%."""
        n = 751
        rng = np.random.default_rng(16)
        p = conformance_pool(1, n)
        p["w"] = np.full(n, 0.5)
        p["r"] = 1e-4 + rng.normal(0.0, 1e-7, n)
        p["r"][n // 2] = -1e-4 * (n - 1)
        fl = self.floor([None, pool_series(1, n, pool=p)])
        self.assertFalse(fl["eligible"])
        self.assertIn("no c <= 5.00", fl["why"])


def s2_floor_of(c_pF1=0.60, **over):
    """An S2 floor as `floor_s2` writes it for the fake receipt (an eligible one; invented figures)."""
    k_used = max(90, round(c_pF1 * 100) + 5)
    base = {"screen": "S2", "eligible": True, "why": None, "method": "exact", "c_pF1": c_pF1,
            "c_H_used": k_used / 100, "k_F1": round(c_pF1 * 100), "k_used": k_used, "fp_cap": 0.12,
            "c_H_floor": 0.9, "c_H_margin": 0.05, "sets": {}, "own_fp": 0.0212, "holdout_only": 0.0987,
            "drift_kept": 0.1543, "cells": {}}
    base.update(over)
    return base


def sessions_2026(last: dt.date) -> list[dt.date]:
    return [d for d in weekdays(dt.date(2026, 1, 2), last) if d not in HOLIDAYS_2026]


class S2Look(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(41)
        self.v = make_series(V_DAYS, exact(rng, len(V_DAYS), 0.0016))
        self.h = make_series(H_DAYS, exact(rng, len(H_DAYS), 0.0016))
        self.t_h = screen.holdout_t(self.h.r)

    def test_t_h_exactly_at_c_passes_and_just_below_fails(self):
        at = screen.look_s2(self.v, self.h, c_H=self.t_h)
        self.assertTrue(at["passed"])
        self.assertEqual(at["checks"], {"precheck": True, "sum_h": True, "t_H": True})
        above = screen.look_s2(self.v, self.h, c_H=float(np.nextafter(self.t_h, math.inf)))
        self.assertFalse(above["passed"])
        self.assertEqual(above["checks"], {"precheck": True, "sum_h": True, "t_H": False})
        self.assertEqual(at["t_H"], screen.holdout_t(self.h.r))
        self.assertEqual(at["n"], len(V_DAYS) + len(H_DAYS))

    def test_sum_h_and_sd_h(self):
        zero = screen.look_s2(self.v, make_series(H_DAYS, np.zeros(len(H_DAYS))), c_H=0.0)
        self.assertFalse(zero["passed"])
        self.assertFalse(zero["checks"]["sum_h"])
        self.assertIsNone(zero["t_H"])
        flat = screen.look_s2(self.v, make_series(H_DAYS, np.full(len(H_DAYS), 0.001)), c_H=0.0)
        self.assertFalse(flat["passed"], "sd_H = 0 fails")
        self.assertEqual(flat["checks"], {"precheck": True, "sum_h": True, "t_H": False})
        loses = make_series(H_DAYS, exact(np.random.default_rng(2), len(H_DAYS), -0.0005))
        self.assertFalse(screen.look_s2(self.v, loses, c_H=-5.0)["checks"]["sum_h"], "a losing holdout fails")

    def test_a_failed_precheck_fails(self):
        idle = make_series(V_DAYS, self.v.r, invested=np.zeros(len(V_DAYS), dtype=bool))
        out = screen.look_s2(idle, self.h, c_H=0.0)
        self.assertFalse(out["passed"])
        self.assertEqual(out["checks"], {"precheck": False, "sum_h": True, "t_H": True})

    def test_the_pooled_t_never_gates(self):
        """c_R = 0: a Validation barely above zero drags the pooled t under receipt 1's c_R; S2 passes regardless."""
        self.assertNotIn("c_R", inspect.signature(screen.look_s2).parameters)
        rng = np.random.default_rng(43)
        v = make_series(V_DAYS, exact(rng, len(V_DAYS), 0.00001, sd=0.05))
        h = make_series(H_DAYS, exact(rng, len(H_DAYS), 0.003, sd=0.01))
        out = screen.look_s2(v, h, c_H=1.0)
        self.assertTrue(out["passed"])
        self.assertLess(out["t"], receipt().c_R, "the pooled t is reported, below S1's bar")
        self.assertFalse(screen.look(v, h, c=receipt().c_R, c_H=1.0)["passed"], "S1 would have failed it")

    def test_c_h_must_be_a_number(self):
        for bad in (None, True, float("nan"), "0.9"):
            with self.assertRaises(ValueError, msg=bad):
                screen.look_s2(self.v, self.h, c_H=bad)


class S2Verdict(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(21)
        n_v, n_h = len(V_DAYS), len(H_DAYS)
        self.v = make_series(V_DAYS, exact(rng, n_v, 0.0016), b=exact(rng, n_v, 0.0))
        self.h = make_series(H_DAYS, exact(rng, n_h, 0.0016), b=exact(rng, n_h, 0.0))
        self.t_h = screen.holdout_t(self.h.r)
        self.assertTrue(1.5 < self.t_h < 3.5, self.t_h)
        self.rc = receipt_s2()

    def test_refused_without_a_receipt(self):
        for rc in (None, receipt()):
            with self.assertRaises(screen.ScreenRefused):
                screen.verdict_s2(self.v, self.h, receipt=rc, program_floor=s2_floor_of())
        with self.assertRaises(screen.ScreenRefused):
            screen.verdict(self.v, self.h, receipt=None, program_floor=s2_floor_of())

    def test_a_pass_and_what_it_states(self):
        out = screen.verdict_s2(self.v, self.h, receipt=self.rc, program_floor=s2_floor_of(c_pF1=1.2))
        self.assertTrue(out["passed"], out["why"])
        self.assertEqual((out["screen"], out["c_R"], out["c_pF1"], out["c_H"]), ("S2", 0.0, 1.2, 1.25))
        self.assertEqual(out["t_H"], self.t_h)
        self.assertAlmostEqual(out["t"], screen.pooled_t(self.v.r, self.h.r))
        self.assertEqual((out["own_fp"], out["holdout_only"], out["drift_kept"]), (0.0212, 0.0987, 0.1543))
        self.assertIsNone(out["fp_x"], "no S1 floor: S1-X's FP is unmeasured")
        self.assertEqual(out["label"], screen.label(self.v, self.h, c_X=self.rc.c_X), "S1-X, unchanged")
        self.assertEqual((out["receipt"], out["fp_cap"]), (FAKE_SHA_S2, 0.12))
        self.assertEqual(out["r4"], ["A3: FAKE: an invented wall flag"])
        self.assertEqual(out["deviations"], list(screen.DEVIATIONS))
        self.assertEqual(out["look"]["checks"], {"precheck": True, "sum_h": True, "t_H": True})
        self.assertTrue(out["windows"]["ok"])
        json.dumps(out)
        with_s1 = screen.verdict_s2(self.v, self.h, receipt=self.rc, program_floor=s2_floor_of(),
                                    s1_floor=floor_of())
        self.assertEqual(with_s1["fp_x"], (20_000 - 30 * 110) / 20_000, "S1-X's FP read from the S1 floor at c_X")
        ineligible_s1 = screen.verdict_s2(self.v, self.h, receipt=self.rc, program_floor=s2_floor_of(),
                                          s1_floor=floor_of(eligible=False))
        self.assertIsNone(ineligible_s1["fp_x"])

    def test_c_h_is_the_floor_or_c_pf1_plus_the_margin(self):
        low = screen.verdict_s2(self.v, self.h, receipt=self.rc, program_floor=s2_floor_of(c_pF1=0.1))
        self.assertEqual((low["c_pF1"], low["c_H"]), (0.1, 0.9))
        high = screen.verdict_s2(self.v, self.h, receipt=self.rc, program_floor=s2_floor_of(c_pF1=0.86))
        self.assertEqual(high["c_H"], 0.91)

    def test_the_boundary_on_the_grid(self):
        """c_H,used at the grid point at or below t_H passes; one grid step above it fails, at step 2."""
        k = int(np.searchsorted(screen.GRID, self.t_h, side="right") - 1)
        at = screen.verdict_s2(self.v, self.h, receipt=self.rc, program_floor=s2_floor_of(c_pF1=(k - 5) / 100))
        self.assertEqual(at["c_H"], k / 100)
        self.assertTrue(at["passed"], at["why"])
        above = screen.verdict_s2(self.v, self.h, receipt=self.rc, program_floor=s2_floor_of(c_pF1=(k - 4) / 100))
        self.assertEqual(above["c_H"], (k + 1) / 100)
        self.assertFalse(above["passed"])
        self.assertEqual(above["why"], "step 2, the look: t_H")

    def test_the_floor_must_be_eligible_and_the_receipts(self):
        cases = (
            (s2_floor_of(eligible=False, why=screen.NO_SET_WHY), "no eligible floor set"),
            ({}, "not an S2 floor"),
            (floor_of(), "not an S2 floor (S1)"),
            (s2_floor_of(method="monte carlo"), "not an exact floor"),
            (s2_floor_of(fp_cap=0.10), "fp_cap"),
            (s2_floor_of(c_H_floor=1.0), "c_H_floor"),
            (s2_floor_of(c_H_margin=0.1), "c_H_margin"),
            (s2_floor_of(c_H_used=0.7), "c_H,used"),
            ({**s2_floor_of(), "c_pF1": None}, "c_H,used"),
            ({**s2_floor_of(), "c_pF1": 0.605}, "c_H,used"),
            (s2_floor_of(c_pF1=4.99, c_H_used=5.04), "c_H,used"),
        )
        for fl, why in cases:
            out = screen.verdict_s2(self.v, self.h, receipt=self.rc, program_floor=fl)
            self.assertFalse(out["passed"], why)
            self.assertTrue(out["why"].startswith("step 0, the floor: "), out["why"])
            self.assertIn(why, out["why"])
            self.assertIsNone(out["look"], "no look is read off a floor that does not fit")
            self.assertIn(out["label"], ("alpha", "beta"), "the label is computed for every program")

    def test_the_precheck_and_the_look_in_order(self):
        n = len(V_DAYS)
        idle = make_series(V_DAYS, self.v.r, invested=np.zeros(n, dtype=bool))
        out = screen.verdict_s2(idle, self.h, receipt=self.rc, program_floor=s2_floor_of())
        self.assertEqual(out["why"], "step 1, the pre-check: activity")
        flat = make_series(H_DAYS, np.zeros(len(H_DAYS)))
        out = screen.verdict_s2(self.v, flat, receipt=self.rc, program_floor=s2_floor_of())
        self.assertEqual(out["why"], "step 2, the look: sum_h, t_H")
        both = screen.verdict_s2(idle, flat, receipt=self.rc, program_floor=s2_floor_of())
        self.assertEqual(both["why"], "step 1, the pre-check: activity", "the first failed condition")

    def test_a12_the_look_cap(self):
        """A12: an S2 look reads the holdout through 2026-10-09 at the latest: exactly 2026's 194 sessions; one more
        session (Oct 12) fails the windows whatever config.LOOK_CAP says, and an earlier config cap still binds."""
        self.assertEqual(screen.S2_LOOK_CAP, dt.date(2026, 10, 9))
        days = sessions_2026(dt.date(2026, 10, 9))
        self.assertEqual(len(days), 194)
        rng = np.random.default_rng(5)
        h = make_series(days, exact(rng, 194, 0.0016))
        fl = s2_floor_of(c_pF1=0.1)
        self.assertTrue(screen.verdict_s2(self.v, h, receipt=self.rc, program_floor=fl)["windows"]["ok"])
        late = sessions_2026(dt.date(2026, 10, 12))
        self.assertEqual(late[-1], dt.date(2026, 10, 12))
        h_late = make_series(late, exact(rng, len(late), 0.0016))
        with mock.patch.object(config, "LOOK_CAP", dt.date(2026, 12, 31)):
            out = screen.verdict_s2(self.v, h_late, receipt=self.rc, program_floor=fl)
            self.assertFalse(out["passed"])
            self.assertEqual(out["why"], "the windows: the holdout is not 194..251 sessions inside "
                                         "2026-01-02..2026-10-09 (195)")
            s1 = screen.verdict(self.v, h_late, receipt=receipt(), program_floor=floor_of())
            self.assertTrue(s1["windows"]["ok"], "S1's windows are receipt 1's (D6), config's cap")
        with mock.patch.object(config, "LOOK_CAP", dt.date(2026, 10, 2)):
            out = screen.verdict_s2(self.v, h, receipt=self.rc, program_floor=fl)
            self.assertIn("2026-01-02..2026-10-02", out["why"], "an earlier config cap binds S2 too")
        short = make_series(days[:193], h.r[:193])
        self.assertIn("the windows", screen.verdict_s2(self.v, short, receipt=self.rc, program_floor=fl)["why"])

    def test_the_line_beside_every_live_trade(self):
        out = screen.verdict_s2(self.v, self.h, receipt=self.rc, program_floor=s2_floor_of(c_pF1=1.2),
                                s1_floor=floor_of())
        line = screen.beside_line_s2(out, self.rc)
        self.assertTrue(line.startswith("S2, c_R = 0 (no pooled-t bar), c_H,used = 1.25; this program's FP at zero "
                                        "edge = 2.12% "), line)
        self.assertIn("its holdout-only rate at c_H,used = 9.87%", line)
        self.assertIn("drift-kept pass rate = 15.43%", line)
        self.assertIn(f"S1-X: {out['label']} (FP 83.50%)", line)
        self.assertIn("contamination: FAKE fixture sentence", line)
        self.assertTrue(line.endswith("; R4 flags: A3: FAKE: an invented wall flag"), line)
        self.assertNotIn("{", line)
        bare = screen.beside_line_s2({"label": "beta"}, self.rc)
        self.assertIn("c_H,used = unmeasured", bare)
        self.assertIn("S1-X: beta (FP unmeasured%)", bare)
        self.assertNotIn("R4 flags", bare)


class S2Receipts(unittest.TestCase):
    def test_the_loader_pins_the_sha(self):
        rc = receipt_s2()
        self.assertIsInstance(rc, screen.ReceiptS2)
        self.assertEqual((rc.receipt_sha256, rc.c_R, rc.c_H_floor, rc.c_H_margin, rc.c_X, rc.fp_cap, rc.owner_wall,
                          rc.retry), (FAKE_SHA_S2, 0.0, 0.9, 0.05, 1.1, 0.12, 0.15, True))
        self.assertEqual(rc.r4["A3"], ("FAKE: an invented wall flag",))
        self.assertEqual(set(rc.fp), {"fp_zero_edge", "power"})
        for pin in ("f" * 64, FAKE_SHA_S2.upper(), FAKE_SHA_S2[:63], None, "", FAKE_SHA):
            with self.assertRaises(screen.ScreenRefused, msg=pin):
                screen.load_receipt_s2(FIXTURE_S2, pinned_sha256=pin)
        with self.assertRaises(screen.ScreenRefused):
            screen.load_receipt_s2(FIXTURE_S2.with_name("no-such-receipt.json"), pinned_sha256=FAKE_SHA_S2)

    def test_the_routed_loader_and_s1s_loader(self):
        """S1's `load_receipt` refuses receipt 2 (it lacks receipt 1's keys); the loader routed to "S2" reads it; and
        receipt 2's loader refuses receipt 1."""
        with self.assertRaises(screen.ScreenRefused):
            screen.load_receipt(FIXTURE_S2, pinned_sha256=FAKE_SHA_S2)
        self.assertEqual(screen.load_receipt(FIXTURE_S2, pinned_sha256=FAKE_SHA_S2, screen="S2"), receipt_s2())
        self.assertEqual(screen.load_receipt(FIXTURE, pinned_sha256=FAKE_SHA, screen="S1"), receipt())
        with self.assertRaises(screen.ScreenRefused):
            screen.load_receipt_s2(FIXTURE, pinned_sha256=FAKE_SHA)
        with self.assertRaises(screen.ScreenRefused):
            screen.load_receipt(FIXTURE_S2, pinned_sha256=FAKE_SHA_S2, screen="S3")
        for pin in (None, ""):
            with self.assertRaises(screen.ScreenRefused, msg="no receipt pinned"):
                screen.load_receipt(FIXTURE_S2, pinned_sha256=pin, screen="S2")

    def test_a_malformed_receipt_refuses(self):
        doc = json.loads(FIXTURE_S2.read_text())
        edits = [
            lambda d: d.update(c_R=0.5),
            lambda d: d.update(c_R=None),
            lambda d: d.update(c_H_floor=0.905),
            lambda d: d.update(c_H_margin=0.055),
            lambda d: d.update(c_H_floor=5.01),
            lambda d: d.update(c_H_margin="0.05"),
            lambda d: d.pop("c_H_margin"),
            lambda d: d.pop("stated_beside_every_live_trade"),
            lambda d: d.pop("power"),
            lambda d: d.pop("screen"),
            lambda d: d.update(screen="S1"),
            lambda d: d["lineage"].update(validation_tries=1),
            lambda d: d["lineage"].update(validation_tries=3),
            lambda d: d["lineage"].update(holdout_looks=2),
            lambda d: d["precheck"].update(rt_min=25),
            lambda d: d["floor"].update(method="monte carlo"),
            lambda d: d["windows"].update(holdout="2026-01-02 .. 2026-12-31 (D6)"),
            lambda d: d.update(R3_retry_permitted="yes"),
            lambda d: d.update(c_X=None),
            lambda d: d.update(fp_cap=1.0),
            lambda d: d.update(owner_wall=0.0),
            lambda d: d.update(R4_flags={"A1": "a string, not a list"}),
            lambda d: d.update(stated_beside_every_live_trade="S2, c_H,used = {c_H}; FP {own_fp}%"),
        ]
        with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as tmp:
            for i, edit in enumerate(edits):
                bad = copy.deepcopy(doc)
                edit(bad)
                path = Path(tmp) / f"bad{i}.json"
                path.write_text(json.dumps(bad))
                with self.assertRaises(screen.ScreenRefused, msg=i):
                    screen.load_receipt_s2(path, pinned_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            path = Path(tmp) / "not.json"
            path.write_text("{not json")
            with self.assertRaises(screen.ScreenRefused):
                screen.load_receipt_s2(path, pinned_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            path = Path(tmp) / "list.json"
            path.write_text("[]")
            with self.assertRaises(screen.ScreenRefused):
                screen.load_receipt_s2(path, pinned_sha256=hashlib.sha256(path.read_bytes()).hexdigest())

    def test_the_policy_block(self):
        rc = screen.pinned_receipt_s2(s2_block())
        self.assertEqual(rc, dataclasses.replace(receipt_s2(), fp={}))
        by_screen = s2_block(screen="S2")
        del by_screen["name"]
        self.assertEqual(screen.pinned_receipt_s2(by_screen), rc, "`screen` names it too")
        del_name = s2_block()
        del del_name["name"]
        self.assertIsNone(screen.pinned_receipt_s2(del_name), "a block naming no screen is receipt 1's")
        self.assertIsNone(screen.pinned_receipt_s2(s2_block(owner_wall=None)).owner_wall, "the wall is optional")
        self.assertFalse(screen.pinned_receipt_s2(s2_block(retry="true")).retry, "a retry is a literal true")
        self.assertEqual(screen.pinned_receipt_s2(s2_block(r4=None)).r4, {})
        self.assertIsNone(screen.pinned_receipt_s2(None))
        for over in ({"receipt_sha256": None}, {"receipt_sha256": "F" * 64}, {"c_R": None}, {"c_R": 0.01},
                     {"c_R": True}, {"c_H_floor": None}, {"c_H_floor": 0.905}, {"c_H_floor": -0.01},
                     {"c_H_margin": None}, {"c_H_margin": 5.01}, {"c_X": None}, {"c_X": float("nan")},
                     {"fp_cap": 0.0}, {"fp_cap": 1.0}, {"owner_wall": 0.0}, {"owner_wall": "0.15"},
                     {"r4": ["A1"]}, {"beside": None}, {"beside": "S2, c_H,used = {c_H}"}, {"name": "S1"},
                     {"name": "S3"}, {"name": "S1", "screen": "S2"}):
            self.assertIsNone(screen.pinned_receipt_s2(s2_block(**over)), over)


class Routing(unittest.TestCase):
    """A11: the pinned block's screen picks the code. Every public entry point routes on the receipt it is handed: an
    "S1" block runs S1 (receipt 1), an "S2" block runs S2 (receipt 2); no pinned receipt refuses."""

    def setUp(self):
        rc = receipt()
        self.s1_block = {"name": "S1", "receipt_sha256": rc.receipt_sha256, "c_R": rc.c_R, "c_X": rc.c_X,
                         "fp_cap": rc.fp_cap, "owner_wall": rc.owner_wall, "retry": rc.retry,
                         "r4": {k: list(v) for k, v in rc.r4.items()}, "beside": rc.beside}
        self.rc1, self.rc2 = receipt(), receipt_s2()

    def test_screen_of_and_the_receipt_path(self):
        for pin, want in ((self.rc1, "S1"), (self.rc2, "S2"), ({}, "S1"), ({"name": "S1"}, "S1"),
                          ({"name": "S2"}, "S2"), ({"screen": "S2"}, "S2"), ({"screen": "S2", "name": "S2"}, "S2"),
                          ({"screen": "S2", "name": "S1"}, None), ({"name": "D2"}, None), ({"name": ["S2"]}, None),
                          (None, None), ("S2", None)):
            self.assertEqual(screen.screen_of(pin), want, pin)
        self.assertEqual(screen.receipt_path(self.rc1), "docs/benchmarks/equity_screen_1.json")
        self.assertEqual(screen.receipt_path({"name": "S2"}), "docs/benchmarks/equity_screen_2.json")
        self.assertIsNone(screen.receipt_path({"name": "D2"}))

    def test_the_pin(self):
        self.assertIsInstance(screen.pinned_receipt(self.s1_block), screen.Receipt)
        self.assertEqual(screen.pinned_receipt(s2_block()), screen.pinned_receipt_s2(s2_block()))
        self.assertIsInstance(screen.pinned_receipt(s2_block()), screen.ReceiptS2)
        self.assertIsNone(screen.pinned_receipt({**self.s1_block, "name": "S2"}), "an S2 block needs receipt 2's")
        self.assertIsNone(screen.pinned_receipt({**self.s1_block, "screen": "S2"}), "screen and name disagree")
        self.assertIsNone(screen.pinned_receipt(s2_block(name="S1")), "an S1 block needs receipt 1's figures")
        self.assertIsNone(screen.pinned_receipt(None))

    def test_the_floor(self):
        self.assertEqual(screen.floor([], receipt=self.rc1)["screen"], "S1")
        self.assertEqual(screen.floor([], fp_cap=0.12)["screen"], "S1", "E1's call, unchanged")
        self.assertEqual(screen.floor([], receipt=self.rc2)["screen"], "S2")
        segs = conformance_segments(None, 751)
        self.assertEqual(screen.floor(segs, receipt=self.rc2), screen.floor_s2(segs, receipt=self.rc2))
        with self.assertRaises(screen.ScreenRefused):
            screen.floor(segs)
        with self.assertRaises(screen.ScreenRefused):
            screen.floor(segs, receipt=s2_block())
        with self.assertRaises(ValueError):
            screen.floor([], receipt=self.rc1, fp_cap=0.10)

    def test_floor_fits(self):
        s1 = floor_of()
        s2 = screen.floor_s2(conformance_segments(None, 549), receipt=self.rc2)       # ineligible: still a fit
        self.assertTrue(screen.floor_fits(s1, self.rc1))
        self.assertFalse(screen.floor_fits(s1, self.rc2), "an S1 floor cached for a version is not S2's")
        self.assertTrue(screen.floor_fits(s2, self.rc2))
        self.assertFalse(screen.floor_fits(s2, self.rc1))
        self.assertFalse(screen.floor_fits(s2, dataclasses.replace(self.rc2, c_H_floor=1.0)))
        self.assertFalse(screen.floor_fits(s1, dataclasses.replace(self.rc1, fp_cap=0.10)))
        self.assertFalse(screen.floor_fits({}, self.rc2))
        self.assertFalse(screen.floor_fits(s2, None))

    def test_the_whole_chain_routes_by_the_block(self):
        """elane's chain (pinned_receipt -> floor -> verdict -> beside_line) on one program, under each block."""
        rng = np.random.default_rng(21)
        v = make_series(V_DAYS, exact(rng, len(V_DAYS), 0.0016), b=exact(rng, len(V_DAYS), 0.0))
        h = make_series(H_DAYS, exact(rng, len(H_DAYS), 0.0016), b=exact(rng, len(H_DAYS), 0.0))
        rc2 = screen.pinned_receipt(s2_block())
        fl2 = screen.floor(conformance_segments(1004, 751), receipt=rc2)
        out2 = screen.verdict(v, h, receipt=rc2, program_floor=fl2)
        self.assertEqual((out2["screen"], out2["c_H"], out2["c_R"]), ("S2", 1.25, 0.0))
        self.assertTrue(out2["passed"], out2["why"])
        line2 = screen.beside_line(out2, rc2)
        self.assertTrue(line2.startswith("S2, c_R = 0"), line2)
        self.assertNotIn("{", line2)
        rc1 = screen.pinned_receipt(self.s1_block)
        out1 = screen.verdict(v, h, receipt=rc1, program_floor=floor_of())
        self.assertEqual((out1["screen"], out1["c_used"]), ("S1", 1.25))
        line1 = screen.beside_line(out1, rc1)
        self.assertTrue(line1.startswith("S1-R, c_used = 1.25"), line1)
        self.assertNotIn("{", line1)
        # A floor of the other screen fails step 0 either way; a verdict beside the other receipt's line is an error.
        self.assertIn("step 0", screen.verdict(v, h, receipt=rc1, program_floor=fl2)["why"])
        self.assertIn("step 0", screen.verdict(v, h, receipt=rc2, program_floor=floor_of())["why"])
        with self.assertRaises(ValueError):
            screen.beside_line(out2, rc1)
        with self.assertRaises(ValueError):
            screen.beside_line(out1, rc2)
        with self.assertRaises(screen.ScreenRefused):
            screen.beside_line(out2, None)

    def test_the_lineage_reads_either_receipt(self):
        for rc in (self.rc1, self.rc2):
            self.assertTrue(screen.retry_permitted(rc, first_precheck_failed=True))
            self.assertFalse(screen.retry_permitted(dataclasses.replace(rc, retry=False), first_precheck_failed=True))
            self.assertEqual(screen.r4_flags(rc), ["A3: FAKE: an invented wall flag"])


if __name__ == "__main__":
    unittest.main()
