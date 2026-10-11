"""THE PANEL'S INDEPENDENT NAMES (release E4, package B; league/ops/equity_neff.py): D21's two figures as formulas
(the mean-correlation N_eff and the participation ratio, each against a hand value and against numpy's own
correlation and eigenvalues), the sector-residual returns they are read on (baskets re-formed monthly, a full series
or no name), the monthly job on Train segment 2, and the funnel's rows: independent asset-years beside simulated
program-years, and the replay multiple.

Every return, price and count here is invented (seeded uniform noise on the true NYSE calendar of 2021-24): no market
row is read. Package C's `league.xs.store.PanelStore` and `league.xs.ctx.derive` are met at their interface
(league/xs/E4_INTERFACES.md 6): the job is tested on what it asks of them and what it does with their answers."""

from __future__ import annotations

import ast
import datetime as dt
import json
import math
import sqlite3
import stat
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import numpy as np

from league.equity import store as eq_store
from league.ops import equity_neff as EN
from league.ops import guard
from league.ops.context import Context
from league.xs import config as xs_config
from league.xs import ctx as xs_ctx
from league.xs import store as xs_store

REF = len(xs_config.REF)
NOW = 1_800_000_000.0


def noise(seed: int, *shape: int) -> np.ndarray:
    """Invented uniform noise on [-0.5, 0.5) (`Generator.random`: the one stream numpy keeps across versions)."""
    return np.random.default_rng(seed).random(shape) - 0.5


def reference(x: np.ndarray) -> dict[str, float]:
    """D21 by numpy's own routines: the correlation matrix, its mean off-diagonal and its eigenvalues."""
    r = np.corrcoef(x, rowvar=False)
    n = r.shape[0]
    rho = (r.sum() - np.trace(r)) / (n * (n - 1))
    eig = np.linalg.eigvalsh(r)
    return {"rho": float(rho), "neff_rho": float(n / (1 + (n - 1) * rho)), "neff_pr": float(eig.sum() ** 2 / (eig ** 2).sum())}


class TheFormula(unittest.TestCase):
    """D21: neff_rho = n / (1 + (n - 1) x the mean off-diagonal); neff_pr = (sum of eigenvalues)^2 / sum of squares."""

    def test_a_hand_matrix(self):
        # Two names that move together and a third unrelated to both: R = [[1, 1, 0], [1, 1, 0], [0, 0, 1]].
        x = np.array([[1.0, 2.0, 1.0], [-1.0, -2.0, 1.0], [1.0, 2.0, -1.0], [-1.0, -2.0, -1.0]])
        out = EN.neff(x)
        self.assertEqual((out["names"], out["sessions"]), (3, 4))
        self.assertAlmostEqual(out["rho"], 1 / 3, places=15)
        self.assertAlmostEqual(out["neff_rho"], 3 / (1 + 2 / 3), places=12)      # 1.8
        self.assertAlmostEqual(out["neff_pr"], (2 + 0 + 1) ** 2 / (4 + 0 + 1), places=12)   # eigenvalues 2, 0, 1: 1.8

    def test_identical_names_are_one_and_unrelated_names_are_all_of_them(self):
        one = np.tile(noise(1, 50, 1), (1, 6))
        out = EN.neff(one)
        self.assertAlmostEqual(out["neff_rho"], 1.0, places=9)
        self.assertAlmostEqual(out["neff_pr"], 1.0, places=9)
        # the rows of a Hadamard matrix: four columns with exactly zero correlation
        h = np.array([[1, 1, 1, 1], [1, -1, 1, -1], [1, 1, -1, -1], [1, -1, -1, 1],
                      [-1, -1, -1, -1], [-1, 1, -1, 1], [-1, -1, 1, 1], [-1, 1, 1, -1]], dtype=float)
        out = EN.neff(h)
        self.assertEqual((out["rho"], out["neff_rho"], out["neff_pr"]), (0.0, 4.0, 4.0))

    def test_it_is_numpys_correlation_and_eigenvalues_on_a_factor_world(self):
        for seed, names, sessions, load in ((5, 30, 200, 0.8), (6, 12, 60, 0.0), (7, 45, 400, 2.0)):
            x = load * noise(seed, sessions, 1) + noise(seed + 100, sessions, names)
            out, ref = EN.neff(x), reference(x)
            self.assertAlmostEqual(out["rho"], ref["rho"], places=12)
            self.assertAlmostEqual(out["neff_pr"], ref["neff_pr"], places=8)
            if ref["rho"] > 0:
                self.assertAlmostEqual(out["neff_rho"], ref["neff_rho"], places=8)
            self.assertLessEqual(out["neff_pr"], names)
            self.assertGreaterEqual(out["neff_pr"], 1.0)
        # a common factor lowers both figures
        loud = EN.neff(2.0 * noise(8, 300, 1) + noise(9, 300, 20))
        quiet = EN.neff(noise(9, 300, 20))
        self.assertLess(loud["neff_rho"], 0.5 * quiet["neff_rho"])
        self.assertLess(loud["neff_pr"], 0.5 * quiet["neff_pr"])

    def test_a_mean_correlation_at_or_under_zero_reads_every_name_and_no_more(self):
        x = noise(11, 40, 1)
        out = EN.neff(np.hstack([x, -x]))
        self.assertAlmostEqual(out["rho"], -1.0, places=12)
        self.assertEqual(out["neff_rho"], 2.0)             # the formula alone would divide by zero
        self.assertAlmostEqual(out["neff_pr"], 1.0, places=9)
        # residuals that sum to zero across names (a basket's own): the mean off-diagonal is about -1 / (n - 1)
        r = noise(12, 120, 8)
        out = EN.neff(r - r.mean(axis=1, keepdims=True))
        self.assertLess(out["rho"], 0.0)
        self.assertEqual(out["neff_rho"], 8.0)
        self.assertLess(out["neff_pr"], 8.0)

    def test_every_sum_is_exact_so_the_order_of_sessions_and_names_changes_nothing(self):
        """`math.fsum` returns the correctly rounded sum whatever the order (the built-in `sum` does not, and is not
        the same sum on Python 3.11 and 3.14): the figures are EQUAL, not close, under any reordering."""
        x = 1e3 * noise(21, 250, 18) + 0.4 * 1e3 * noise(22, 250, 1)
        base = EN.neff(x)
        rows = np.argsort(noise(23, 250))
        cols = np.argsort(noise(24, 18))
        self.assertEqual(EN.neff(x[rows]), base)
        self.assertEqual(EN.neff(x[::-1]), base)
        swapped = EN.neff(x[:, cols])
        self.assertEqual((swapped["rho"], swapped["neff_rho"], swapped["neff_pr"]),
                         (base["rho"], base["neff_rho"], base["neff_pr"]))

    def test_a_names_scale_and_level_change_nothing(self):
        x = noise(31, 90, 7) + 0.5 * noise(32, 90, 1)
        base = EN.neff(x)
        moved = EN.neff(x * np.array([1, 8, 0.25, 2, 16, 4, 0.5]) + np.array([0, 1, -2, 3, 0.5, 0, 0]))
        for key in ("rho", "neff_rho", "neff_pr"):
            self.assertAlmostEqual(moved[key], base[key], places=10)

    def test_what_is_no_matrix_is_refused(self):
        good = noise(41, 10, 3)
        cases = {
            "dimensions": good[:, 0],
            "at least": good[:2],
            "sessions of": good[:, :1],
            "missing or not finite": np.where(np.arange(30).reshape(10, 3) == 7, np.nan, good),
            "not finite": np.where(np.arange(30).reshape(10, 3) == 7, np.inf, good),
            "never move": np.hstack([good, np.full((10, 1), 0.25)]),
        }
        for why, x in cases.items():
            with self.assertRaisesRegex(ValueError, why, msg=why):
                EN.neff(x)


class TheResiduals(unittest.TestCase):
    """A name's return less its sector's equal-weight mean, sectors re-formed monthly; a full series or no name."""

    def setUp(self):
        # 4 sessions (two months of two), 6 columns. Month 0: sector 0 = {0, 1, 2}, sector 1 = {3, 4}, column 5 alone
        # in sector 2. Month 1: column 2 moves to sector 1.
        self.r = np.array([[0.03, 0.01, -0.01, 0.02, 0.04, 0.05],
                           [0.00, 0.02, 0.04, -0.02, 0.02, 0.01],
                           [0.01, 0.03, 0.05, 0.01, 0.03, -0.02],
                           [-0.02, 0.02, 0.00, 0.04, -0.04, 0.03]])
        self.month = [0, 0, 1, 1]
        self.sector = np.array([[0, 0, 0, 1, 1, 2], [0, 0, 1, 1, 1, 2]])
        self.elig = np.ones((2, 6), dtype=bool)

    def test_the_hand_example(self):
        out = EN.residuals(self.r, self.month, self.sector, self.elig)
        self.assertEqual(out["columns"], [0, 1, 2, 3, 4])
        self.assertEqual(out["dropped"], {"no_return": 0, "not_eligible": 0, "flat": 1})   # column 5: a basket of one
        want = np.array([
            [0.03 - 0.01, 0.01 - 0.01, -0.01 - 0.01, 0.02 - 0.03, 0.04 - 0.03],             # means 0.01 and 0.03
            [0.00 - 0.02, 0.02 - 0.02, 0.04 - 0.02, -0.02 - 0.00, 0.02 - 0.00],             # means 0.02 and 0.00
            [0.01 - 0.02, 0.03 - 0.02, 0.05 - 0.03, 0.01 - 0.03, 0.03 - 0.03],              # means 0.02 and 0.03
            [-0.02 - 0.00, 0.02 - 0.00, 0.00 - 0.00, 0.04 - 0.00, -0.04 - 0.00]])           # means 0.00 and 0.00
        np.testing.assert_allclose(out["x"], want, rtol=0, atol=1e-15)

    def test_a_name_without_a_full_series_is_no_name_but_still_stands_in_its_basket(self):
        r = self.r.copy()
        r[1, 1] = np.nan                    # column 1 has no return on session 1
        elig = self.elig.copy()
        elig[1, 4] = False                  # column 4 is not eligible in month 1
        out = EN.residuals(r, self.month, self.sector, elig)
        self.assertEqual(out["columns"], [0, 2, 3])
        self.assertEqual(out["dropped"], {"no_return": 1, "not_eligible": 1, "flat": 1})
        x = dict(zip(out["columns"], out["x"].T))
        # session 0, sector 0: column 1's return still counts in the mean (0.01)
        self.assertAlmostEqual(x[0][0], 0.03 - 0.01, places=15)
        # session 1, sector 0: column 1 has none, so the mean is over columns 0 and 2 (0.02)
        self.assertAlmostEqual(x[0][1], 0.00 - 0.02, places=15)
        self.assertAlmostEqual(x[2][1], 0.04 - 0.02, places=15)
        # month 0, sector 1: column 4 is in the basket (mean 0.03, 0.00); month 1 without it: columns 2 and 3
        self.assertAlmostEqual(x[3][0], 0.02 - 0.03, places=15)
        self.assertAlmostEqual(x[3][2], 0.01 - 0.03, places=15)
        self.assertAlmostEqual(x[3][3], 0.04 - 0.02, places=15)

    def test_a_name_with_no_sector_at_a_formation_is_dropped(self):
        sector = self.sector.copy()
        sector[0, 0] = -1
        out = EN.residuals(self.r, self.month, sector, self.elig)
        self.assertEqual(out["columns"], [1, 2, 3, 4])
        self.assertEqual(out["dropped"]["not_eligible"], 1)
        self.assertAlmostEqual(out["x"][0, 0], 0.01 - 0.00, places=15)     # sector 0 of month 0 is columns 1 and 2

    def test_residuals_of_one_sector_sum_to_zero_when_every_basket_name_is_kept(self):
        r = noise(51, 40, 9) * 0.05
        out = EN.residuals(r, [0] * 20 + [1] * 20, np.zeros((2, 9), dtype=int), np.ones((2, 9), dtype=bool))
        self.assertEqual(out["columns"], list(range(9)))
        np.testing.assert_allclose(out["x"].sum(axis=1), 0.0, atol=1e-15)

    def test_shapes_that_do_not_agree_are_refused(self):
        for args in ((self.r[0], self.month, self.sector, self.elig),
                     (self.r, [0, 0, 1], self.sector, self.elig),
                     (self.r, self.month, self.sector[:, :5], self.elig[:, :5]),
                     (self.r, self.month, self.sector, self.elig[:1]),
                     (self.r, [0, 0, 1, 2], self.sector, self.elig),
                     (self.r, [1, 1, 0, 0], self.sector, self.elig)):
            with self.assertRaises(ValueError):
                EN.residuals(*args)

    def test_no_session_is_no_name(self):
        out = EN.residuals(np.zeros((0, 3)), [], np.zeros((1, 3), dtype=int), np.ones((1, 3), dtype=bool))
        self.assertEqual((out["columns"], out["x"].shape), ([], (0, 0)))


class TheFormations(unittest.TestCase):
    def test_a_month_is_formed_at_the_close_before_its_first_session(self):
        days = [d for d, _ in eq_store.nyse_sessions(dt.date(2021, 12, 27), dt.date(2022, 3, 4))]
        first = days.index(dt.date(2022, 1, 3))
        month, formed = EN.formations(days, first)
        self.assertEqual(len(month), len(days) - first)
        self.assertEqual([days[i].isoformat() for i in formed], ["2021-12-31", "2022-01-31", "2022-02-28"])
        self.assertEqual(sorted(set(month)), [0, 1, 2])
        self.assertEqual([m for m, d in zip(month, days[first:]) if d.month == 2], [1] * 19)

    def test_a_slice_with_no_look_back_or_no_run_has_no_formation(self):
        days = [d for d, _ in eq_store.nyse_sessions(dt.date(2022, 1, 3), dt.date(2022, 1, 31))]
        for first in (0, len(days), -1):
            with self.assertRaises(ValueError):
                EN.formations(days, first)


def synthetic_bars(*, names: int = 36, sectors: int = 4, seed: int = 61, load: float = 0.03, gaps=None) -> SimpleNamespace:
    """A `league.xs.store.PanelBars` of invented prices on the true sessions of 2021-24 (the look-back year, then
    Train segment 2): `names` member columns after the REF columns, each moved by its sector's invented factor and
    its own noise. `gaps`: {column: session index} whose bar is a zero-volume bar (no valid bar that day)."""
    calendar = eq_store.nyse_sessions(dt.date(2021, 1, 4), xs_config.TRAIN_SEGMENTS[1][1])
    days = [d for d, _ in calendar]
    first = days.index(xs_config.TRAIN_SEGMENTS[1][0])
    n, m = len(days), REF + names
    sector_of = np.arange(names) % sectors
    moves = load * 2 * noise(seed, n, sectors)[:, sector_of] + 0.02 * noise(seed + 1, n, names)
    close = np.full((n, m), 100.0)
    close[:, REF:] = 50.0 * np.cumprod(1.0 + moves, axis=0)
    raw = np.empty((n, m, 5))
    raw[:, :, :4] = close[:, :, None]
    raw[:, :, 4] = 1_000_000.0
    for column, index in (gaps or {}).items():
        raw[index, column, 4] = 0.0
    adj = np.repeat((close * 0.9)[:, :, None], 4, axis=2)      # a dividend's restatement: a constant factor
    elig0 = np.ones((n, m), dtype=bool)
    elig0[:, :REF] = False
    bars = xs_store.PanelBars(
        days=np.array([eq_store.ordinal(d) for d in days], dtype=np.int32), early=np.array([e for _, e in calendar]),
        first=first, raw=raw, adj=adj, elig0=elig0, ref=REF, ids=np.arange(1000, 1000 + names, dtype=np.int32),
        exit=np.zeros(m, dtype=np.int8), hs=np.full((m, 2), 0.0003), sector_perm=np.arange(11, dtype=np.int8),
        dither_key=b"test", window="train", data_version="synthetic")
    return SimpleNamespace(bars=bars, days=days, first=first, sector_of=sector_of, moves=moves, names=names)


class Derive:
    """Package C's `ctx.inputs_from_panel` and `ctx.derive` at their interface: the inputs are the decision's index,
    the answer a `Derived` whose sectors and eligible set the test fixed."""

    def __init__(self, world: SimpleNamespace, *, out=(), mover=None):
        self.world, self.out, self.mover = world, dict(out), mover
        self.asked: list[int] = []
        self.needs: list = []

    def inputs_from_panel(self, bars, t, *, needs, positions=(), closed=(), rejects=(), cash, equity, budget, params):
        assert bars is self.world.bars and (cash, equity, budget, params) == (0.0, 0.0, 0.0, {})
        self.needs.append(needs)
        return t

    def derive(self, inputs, *, rung=None):
        t = int(inputs)
        self.asked.append(t)
        m = REF + self.world.names
        sector = np.full(m, -1, dtype=np.int8)
        sector[REF:] = self.world.sector_of
        elig = np.zeros(m, dtype=bool)
        elig[REF:] = True
        for column, months in self.out.items():
            if len(self.asked) - 1 in months:
                elig[column] = False
        if self.mover is not None and len(self.asked) - 1 >= self.mover[1]:
            sector[self.mover[0]] = self.mover[2]
        blank = np.zeros(m)
        return xs_ctx.Derived(elig=elig, beta=blank, mom=blank, sector=sector, bg=sector, mg=sector,
                              cell=sector.astype(np.int32), rung="R0")

    def patched(self):
        return mock.patch.multiple(xs_ctx, inputs_from_panel=self.inputs_from_panel, derive=self.derive)


def plain_reference(world: SimpleNamespace) -> dict[str, float]:
    """D21 written the plain way for the synthetic world (every name in its own fixed sector all window)."""
    close = world.bars.adj[:, REF:, 3]
    r = (close[world.first:] / close[world.first - 1:-1] - 1.0)
    x = r.copy()
    for code in sorted(set(world.sector_of.tolist())):
        members = world.sector_of == code
        x[:, members] = r[:, members] - r[:, members].mean(axis=1, keepdims=True)
    return reference(x)


class TheMeasure(unittest.TestCase):
    def test_returns_need_a_valid_bar_on_both_sessions(self):
        world = synthetic_bars(names=6, gaps={REF + 2: 400, REF + 4: 252})
        r = EN.panel_returns(world.bars)
        self.assertEqual(r.shape, (len(world.days) - world.first, REF + 6))
        close = world.bars.adj[:, :, 3]
        want = close[world.first:] / close[world.first - 1:-1] - 1.0
        gone = np.isnan(r)
        np.testing.assert_allclose(r[~gone], want[~gone], rtol=0, atol=0)
        # a zero-volume bar is no valid bar: its own return and the next session's are missing, nothing else
        self.assertEqual(sorted(zip(*np.nonzero(gone))), sorted(
            [(400 - world.first, REF + 2), (401 - world.first, REF + 2), (252 - world.first, REF + 4),
             (253 - world.first, REF + 4)]))
        self.assertEqual(world.first, 252)

    def test_it_is_d21_on_the_sector_residuals_of_the_segment(self):
        world = synthetic_bars()
        fake = Derive(world)
        with fake.patched():
            out = EN.measure(world.bars)
        ref = plain_reference(world)
        self.assertEqual((out["names"], out["columns"], out["sessions"]), (36, 36, len(world.days) - world.first))
        self.assertEqual(out["window"], ["2022-01-03", "2024-12-31"])
        self.assertEqual(out["dropped"], {"no_return": 0, "not_eligible": 0, "flat": 0})
        self.assertAlmostEqual(out["rho"], ref["rho"], places=12)
        self.assertAlmostEqual(out["neff_pr"], ref["neff_pr"], places=8)
        self.assertEqual(out["neff_rho"], 36.0)       # sector residuals: the mean off-diagonal is under zero
        self.assertLess(out["rho"], 0.0)

    def test_the_sector_factor_is_what_the_residual_removes(self):
        world = synthetic_bars()
        with Derive(world).patched():
            out = EN.measure(world.bars)
        close = world.bars.adj[:, REF:, 3]
        raw = EN.neff(close[world.first:] / close[world.first - 1:-1] - 1.0)
        self.assertLess(raw["neff_pr"], 8.0)           # four invented sector factors drive 36 names
        self.assertGreater(out["neff_pr"], 3 * raw["neff_pr"])
        self.assertGreater(out["neff_pr"], 24.0)

    def test_derive_is_asked_once_a_month_at_the_close_before_it(self):
        world = synthetic_bars(names=8)
        fake = Derive(world)
        with fake.patched():
            EN.measure(world.bars)
        asked = [world.days[t] for t in fake.asked]
        self.assertEqual(len(asked), 36)
        self.assertEqual(asked[0], dt.date(2021, 12, 31))
        for day in asked:
            after = world.days[world.days.index(day) + 1]
            self.assertNotEqual((day.year, day.month), (after.year, after.month))
        self.assertTrue(all(t < world.first or world.days[t].year >= 2022 for t in fake.asked))
        needs = fake.needs[0]
        self.assertEqual((needs.panel, needs.history, needs.rebalance), ("sp500", xs_config.MAX_HISTORY, "monthly"))

    def test_a_name_out_for_a_month_or_missing_a_bar_is_not_counted_and_one_that_changes_sector_is(self):
        world = synthetic_bars(gaps={REF + 5: 600})
        fake = Derive(world, out={REF + 3: {7}}, mover=(REF + 9, 12, 2))
        with fake.patched():
            out = EN.measure(world.bars)
        self.assertEqual(out["names"], 34)
        self.assertEqual(out["dropped"], {"no_return": 1, "not_eligible": 1, "flat": 0})

    def test_too_few_names_is_no_matrix(self):
        world = synthetic_bars(names=4, sectors=4)        # every basket is one name: every residual is flat
        with Derive(world).patched():
            with self.assertRaisesRegex(ValueError, "0 names have a full series"):
                EN.measure(world.bars)


class Store:
    """Package C's `PanelStore` at its interface: what the job asks of it, and the slice the test built."""

    asked: list = []
    world: SimpleNamespace | None = None
    answer = "ok"
    fail: Exception | None = None

    def __init__(self, root, *, gate=None):
        type(self).asked.append(("open", Path(root), gate))

    def verdict(self):
        return type(self).answer

    def train(self, start, end, *, history, run_key, half=None):
        type(self).asked.append(("train", start, end, history, run_key, half))
        if type(self).fail is not None:
            raise type(self).fail
        return SimpleNamespace(bars=type(self).world.bars, aids=None, run_key=run_key)


class TheJob(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state = Path(self.tmp.name) / "state"
        self.root = self.state / EN.STORE_DIR
        self.ctx = Context("equity_neff", root=self.state, due_at=NOW, clock=lambda: NOW, gateway=object(), config={},
                           settings_value={})
        self.world = synthetic_bars(names=20)
        Store.asked, Store.world, Store.answer, Store.fail = [], self.world, "ok", None
        self.derive = Derive(self.world)
        for patch in (mock.patch.object(xs_store, "PanelStore", Store), self.derive.patched()):
            patch.start()
            self.addCleanup(patch.stop)
        quiet = mock.patch.object(xs_config, "quiet", return_value=None)
        self.quiet = quiet.start()
        self.addCleanup(quiet.stop)

    def manifest(self):
        (self.root / "panel").mkdir(parents=True, exist_ok=True)
        (self.root / "panel" / "PANEL_MANIFEST.json").write_text("{}")

    def test_it_asks_the_quiet_windows_first_with_its_own_wall(self):
        self.manifest()
        self.quiet.return_value = "inside the open wall"
        self.assertEqual(EN.run(self.ctx), {"status": "skipped", "why": "inside the open wall"})
        self.quiet.assert_called_once_with(NOW, EN.WALL_S)
        self.assertEqual((EN.WALL_S, Store.asked, (self.root / EN.FILE).exists()), (900, [], False))
        self.quiet.side_effect = RuntimeError("no calendar")
        out = EN.run(self.ctx)
        self.assertEqual((out["status"], Store.asked), ("skipped", []))
        self.assertIn("could not be read", out["why"])
        self.assertEqual([a["level"] for a in self.ctx.alerts], ["warning"])

    def test_before_the_panel_store_exists_or_while_it_is_insufficient_it_is_skipped(self):
        self.assertEqual(EN.run(self.ctx), {"status": "skipped", "why": "no panel store yet"})
        self.assertEqual(Store.asked, [])
        self.manifest()
        Store.answer = "insufficient"
        out = EN.run(self.ctx)
        self.assertEqual(out["status"], "skipped")
        self.assertIn("insufficient", out["why"])
        self.assertFalse((self.root / EN.FILE).exists())
        self.assertEqual([a[0] for a in Store.asked], ["open"])

    def test_it_reads_train_segment_two_and_no_sealed_window(self):
        self.manifest()
        out = EN.run(self.ctx)
        self.assertTrue(out["ok"])
        start, end = xs_config.TRAIN_SEGMENTS[1]
        self.assertEqual((start, end), (dt.date(2022, 1, 3), dt.date(2024, 12, 31)))
        self.assertEqual(Store.asked, [("open", self.root, None),
                                       ("train", start, end, xs_config.MAX_HISTORY, EN.RUN_KEY, None)])
        self.assertEqual(out["window"], ["2022-01-03", "2024-12-31"])

    def test_the_file_is_the_layouts_and_the_receipt_carries_counts_and_n_eff_only(self):
        self.manifest()
        (self.root / EN.FILE).write_text(json.dumps({"another": {"neff_pr": 3.0}}))
        with Derive(self.world).patched():
            want = EN.measure(self.world.bars)
        out = EN.run(self.ctx)
        path = self.root / EN.FILE
        held = json.loads(path.read_text())
        self.assertEqual(held["another"], {"neff_pr": 3.0})
        row = held["sp500"]
        self.assertLessEqual({"window", "names", "rho", "neff_rho", "neff_pr", "computed_at"}, set(row))
        self.assertEqual(row, {"window": ["2022-01-03", "2024-12-31"], "names": 20, "rho": round(want["rho"], 6),
                               "neff_rho": round(want["neff_rho"], 2), "neff_pr": round(want["neff_pr"], 2),
                               "computed_at": "2027-01-15T08:00:00Z", "sessions": want["sessions"], "columns": 20,
                               "dropped": {"no_return": 0, "not_eligible": 0, "flat": 0}, "coverage": "ok"})
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(out, {"ok": True, "panel": "sp500", "names": 20, "sessions": want["sessions"], "columns": 20,
                               "neff_rho": row["neff_rho"], "neff_pr": row["neff_pr"],
                               "window": row["window"], "dropped": row["dropped"]})
        self.assertNotIn("rho", out)
        self.assertEqual(EN.panel_neff(self.state), row["neff_pr"])

    def test_a_store_that_cannot_be_read_is_a_failed_receipt_and_the_last_file_stays(self):
        self.manifest()
        (self.root / EN.FILE).write_text(json.dumps({"sp500": {"neff_pr": 77.0}}))
        Store.fail = eq_store.MissingData("panel/adj.npy does not match its manifest")
        out = EN.run(self.ctx)
        self.assertEqual((out["status"], out["ok"]), ("failed", False))
        self.assertIn("MissingData", out["error"])
        self.assertEqual(json.loads((self.root / EN.FILE).read_text()), {"sp500": {"neff_pr": 77.0}})

    def test_an_unbuilt_interface_is_a_failed_receipt_never_a_crash(self):
        self.manifest()
        Store.fail = NotImplementedError("a stub")
        self.assertEqual(EN.run(self.ctx)["status"], "failed")

    def test_the_state_directory_is_the_equity_lanes(self):
        from league.ops import equity_data

        self.assertEqual(EN.STORE_DIR, equity_data.STORE_DIR)
        self.assertEqual(EN.FILE, "neff.json")


# ------------------------------------------------------------------------------------------------- the funnel's rows
SPEC = {"mechanism": "an invented mechanism, long enough to be a sentence", "roots": ["SPY"]}


class TheFunnelsRows(unittest.TestCase):
    def setUp(self):
        from league.swarm.store import SwarmStore

        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.at = NOW - 3600.0
        self.store = SwarmStore(self.root, clock=lambda: self.at)
        self.addCleanup(self.store.close)
        self.runs = 0

    def family(self, fid: str, lane: str | None, structure: str) -> None:
        if lane is None:
            self.store.add_family({**SPEC, "id": fid, "structure": structure}, origin="seed")
            return
        self.store.add_family({**SPEC, "id": fid, "structure": "etf", "lane": lane}, origin="seed")
        if structure != "etf":
            # A panel (or stock) family as its release writes it; the row is what the funnel reads.
            db = sqlite3.connect(self.root / "swarm.sqlite")
            db.execute("UPDATE families SET structure=? WHERE id=?", (structure, fid))
            db.commit()
            db.close()

    def run_(self, fid: str, days, *, window: str = "train", status: str = "ok", trials: int = 1, at: float | None = None):
        self.runs += 1
        self.at = NOW - 3600.0 if at is None else at
        self.store.add_run(fid, 1, {"run_id": f"r{self.runs}", "status": status, "trials": trials,
                                    "summary": {"days": days}}, window=window, stress=1.0, purpose="elane_train",
                           prune=False)

    def rows(self, start: float = NOW - 86400.0, end: float = NOW) -> dict:
        return guard.read(self.root / "swarm.sqlite", lambda db: EN.funnel_rows(self.root, db, start, end))

    def neff_file(self, value) -> None:
        folder = self.root / EN.STORE_DIR
        folder.mkdir(exist_ok=True)
        (folder / EN.FILE).write_text(json.dumps({"sp500": {"neff_pr": value}}))

    def test_program_years_beside_independent_asset_years_and_the_replay_multiple(self):
        self.family("etf-beta", "beta", "etf")
        self.family("etf-eq", "equity", "etf")
        self.family("panel-a", "equity", "panel")
        self.family("panel-b", "equity", "panel")
        self.family("options", None, "long_call")
        for _ in range(40):
            self.run_("etf-eq", 1764)                    # 40 runs of E1's whole Train era: 280 program-years
        self.run_("etf-beta", 252)
        for fid, days in (("panel-a", 754), ("panel-b", 500), ("panel-b", 246)):
            self.run_(fid, days)                         # 1,500 sessions: 5.95 program-years, under the era's 6
        self.run_("options", 5000)                       # not an equity lane
        self.run_("panel-a", 9999, status="refused")     # the Gym refused it: not a run
        self.run_("panel-a", 9999, status="error")
        self.run_("panel-a", 9999, trials=0)             # no trial
        self.run_("panel-a", 9999, window="validation")  # not a Train run
        self.run_("panel-a", 9999, at=NOW - 2 * 86400.0)  # outside the window
        self.neff_file(80.0)
        out = self.rows()
        self.assertEqual(sorted(out), ["beta", "equity"])
        self.assertEqual(out["equity"]["etf"], {
            "train_runs": 40, "program_years": 280.0, "train_years": 7.0, "neff": 2.3, "neff_source": "default",
            "independent_asset_years": 16.1, "replay_multiple": round(280.0 / 16.1, 2)})
        self.assertEqual(out["beta"]["etf"], {
            "train_runs": 1, "program_years": 1.0, "train_years": 1.0, "neff": 2.3, "neff_source": "default",
            "independent_asset_years": 2.3, "replay_multiple": round(1 / 2.3, 2)})
        years = 1500 / 252
        self.assertEqual(out["equity"]["panel"], {
            "train_runs": 3, "program_years": round(years, 2), "train_years": round(years, 2), "neff": 80.0,
            "neff_source": "neff.json", "independent_asset_years": round(years * 80.0, 2),
            "replay_multiple": round(1 / 80.0, 2)})
        self.assertNotIn("panel", out["beta"])

    def test_the_train_years_read_never_pass_the_structures_era_and_trials_count(self):
        self.family("panel-a", "equity", "panel")
        self.neff_file(50)
        self.run_("panel-a", 754, trials=10)             # 7,540 sessions: 29.92 program-years of 6 Train years
        row = self.rows()["equity"]["panel"]
        self.assertEqual((row["train_runs"], row["program_years"], row["train_years"]), (1, 29.92, 6.0))
        self.assertEqual((row["independent_asset_years"], row["replay_multiple"]), (300.0, 0.1))

    def test_no_n_eff_is_none_never_zero(self):
        self.family("panel-a", "equity", "panel")
        self.family("stock-a", "equity", "stock")
        self.run_("panel-a", 754)
        self.run_("stock-a", 504)
        for value in (None, 0, -3, "x", float("nan")):
            if value is not None:
                self.neff_file(value)
            out = self.rows()["equity"]
            for structure in ("panel", "stock"):
                self.assertEqual((out[structure]["neff"], out[structure]["neff_source"],
                                  out[structure]["independent_asset_years"], out[structure]["replay_multiple"]),
                                 (None, None, None, None), (value, structure))
            self.assertEqual(out["stock"]["program_years"], 2.0)
        self.assertIsNone(EN.panel_neff(self.root))

    def test_a_lane_with_a_family_and_no_run_reads_zero_runs_and_no_multiple(self):
        self.family("etf-eq", "equity", "etf")
        out = self.rows()
        self.assertEqual(out, {"beta": {}, "equity": {"etf": {
            "train_runs": 0, "program_years": 0.0, "train_years": 0.0, "neff": 2.3, "neff_source": "default",
            "independent_asset_years": 0.0, "replay_multiple": None}}})

    def test_release_e3s_figure_is_read_when_its_report_carries_one(self):
        from league.equity import config as eq_config

        years = len(eq_store.nyse_sessions(dt.date(2016, 1, 4), eq_config.LOOK_CAP)) / 252
        self.assertEqual(EN.etf_neff(self.root), (2.3, "default"))
        (self.root / EN.FORWARD_REPORT).write_text(json.dumps({"cey": {"hist_iy": 3.1 * years, "day": "2026-10-09"}}))
        value, source = EN.etf_neff(self.root)
        self.assertEqual(source, "forward-report")
        self.assertAlmostEqual(value, 3.1, places=12)
        self.family("etf-eq", "equity", "etf")
        self.family("stock-a", "equity", "stock")
        self.run_("etf-eq", 1764)
        self.run_("stock-a", 1764)
        out = self.rows()["equity"]
        for structure in ("etf", "stock"):
            self.assertEqual((out[structure]["neff"], out[structure]["neff_source"],
                              out[structure]["independent_asset_years"]), (3.1, "forward-report", 21.7))
        # a figure under one name is one name; a report without the figure is the default
        (self.root / EN.FORWARD_REPORT).write_text(json.dumps({"cey": {"hist_iy": 0.2 * years}}))
        self.assertEqual(EN.etf_neff(self.root), (1.0, "forward-report"))
        for report in ({"cey": {"hist_iy": None}}, {"cey": {"day": None}}, {"mode": "off"}, [], {"cey": {"hist_iy": True}}):
            (self.root / EN.FORWARD_REPORT).write_text(json.dumps(report))
            self.assertEqual(EN.etf_neff(self.root), (2.3, "default"))

    def test_the_train_years_are_the_lanes_own(self):
        from league.equity import config as eq_config

        era = sum(end.year - start.year + 1 for start, end in eq_config.TRAIN_ERA_SEGMENTS)
        self.assertEqual((EN.TRAIN_YEARS["etf"], EN.TRAIN_YEARS["stock"]), (era, era))
        self.assertEqual(EN.TRAIN_YEARS["panel"], len(xs_config.TRAIN_YEARS))
        self.assertEqual(EN.ETF_NEFF_DEFAULT, 2.3)

    def test_the_rows_read_only_and_carry_no_return(self):
        self.family("panel-a", "equity", "panel")
        self.run_("panel-a", 754)
        self.neff_file(60)
        before = (self.root / "swarm.sqlite").read_bytes()
        out = self.rows()
        self.assertEqual((self.root / "swarm.sqlite").read_bytes(), before)
        self.assertEqual(set(out["equity"]["panel"]), {"train_runs", "program_years", "train_years", "neff",
                                                       "neff_source", "independent_asset_years", "replay_multiple"})

    def test_the_module_imports_the_standard_library_alone(self):
        """The funnel imports `funnel_rows` and stays standard library only: numpy, league.xs and league.equity are
        imported inside the functions that need them."""
        tree = ast.parse(Path(EN.__file__).read_text())
        top = set()
        for node in tree.body:
            if isinstance(node, ast.Import):
                top.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                top.add(("." * node.level) + (node.module or ""))
        self.assertEqual(top, {"__future__", "datetime", "json", "math", "sqlite3", "pathlib", "typing"})


if __name__ == "__main__":
    unittest.main()
