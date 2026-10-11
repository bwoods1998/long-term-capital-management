"""What a panel program sees (league/xs/ctx.py): the eligible set and the characteristics (the pinned
pre-registration's 3.1-3.3), the registered contract's fields (C1), the dither (E4-SPEC D7), and the two builders'
inputs.

Each definition is held as a formula: the characteristics and the cells against a plain loop written from the
pre-registration's text (and against the study's own conformance vector CH), the fields and the dither against their
expressions computed by hand. Every panel is synthetic (`league.xs.synth`): no market data.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
import json
import math
import pickle
import statistics
import tempfile
import unittest
from pathlib import Path

import numpy as np

from league.equity import ctx as e1ctx
from league.equity.store import from_ordinal, nyse_sessions, ordinal
from league.xs import config, ctx, store, synth
from league.xs.program import Needs

D = dt.date
REF = len(config.REF)
FIXTURES = Path(__file__).resolve().parent / "fixtures"
NEEDS = Needs("sp500", 252, 10, "weekly", 0, 60)
BOOK = {"cash": 1000.0, "equity": 1000.0, "budget": 1000.0, "params": {"theta": 0.5}}


def make_panel(folder: str, **kwargs) -> Path:
    args = {"n_assets": 60, "start": D(2023, 1, 3), "end": D(2025, 12, 31), "seed": 11}
    args.update(kwargs)
    return synth.synthetic_panel(Path(folder) / "equity-daily", **args)


class Panel(unittest.TestCase):
    """One synthetic panel and its Validation slice for a class of tests."""

    KWARGS: dict = {}

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = make_panel(cls.tmp.name, **cls.KWARGS)
        cls.panel = store.PanelStore(cls.root)
        cls.slice = cls.panel.bars("validation", history=252, run_key="test|validation|2025-01-02")
        cls.bars = cls.slice.bars

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def inputs(self, t: int | None = None, needs: Needs = NEEDS, **book) -> ctx.Inputs:
        return ctx.inputs_from_panel(self.bars, self.bars.first + 40 if t is None else t, needs=needs,
                                     **{**BOOK, **book})

    @staticmethod
    def edited(inputs: ctx.Inputs, **arrays) -> ctx.Inputs:
        return dataclasses.replace(inputs, **arrays)


# ---------------------------------------------------------------------------------------------- the plain references
def plain_slope(r, valid, rm):
    """The pre-registration's beta, as a loop: sum (R - mean R)(R_M - mean R_M) / sum (R_M - mean R_M)^2."""
    rows = [i for i in range(len(r)) if valid[i]]
    if len(rows) < config.MIN_VALID:
        return None
    a, b = [r[i] for i in rows], [rm[i] for i in rows]
    mean_a, mean_b = math.fsum(a) / len(a), math.fsum(b) / len(b)
    den = math.fsum((y - mean_b) ** 2 for y in b)
    return math.fsum((x - mean_a) * (y - mean_b) for x, y in zip(a, b)) / den if den > 0 else None


def plain_characteristics(c, cm, funds):
    """3.2 for ONE name on 253 closes: (beta, mom, sector), None / -1 where undefined."""
    def returns(closes):
        r = [closes[i + 1] / closes[i] - 1.0 if math.isfinite(closes[i + 1]) and math.isfinite(closes[i]) else 0.0
             for i in range(len(closes) - 1)]
        v = [math.isfinite(closes[i + 1]) and math.isfinite(closes[i]) for i in range(len(closes) - 1)]
        return r, v

    rm, vm = returns(cm)
    r, v = returns(c)
    v = [a and b for a, b in zip(v, vm)]
    beta = plain_slope(r, v, rm)
    near, far = c[len(c) - 1 - config.MOM_SKIP], c[len(c) - 1 - config.MOM_BACK]
    mom = near / far - 1.0 if math.isfinite(near) and math.isfinite(far) else None
    if beta is None:
        return None, mom, -1
    best, sector = None, -1
    for s, fund in enumerate(funds):
        rs, vs = returns(fund)
        vs = [a and b for a, b in zip(vs, vm)]
        beta_s = plain_slope(rs, vs, rm)
        both = [i for i in range(len(r)) if v[i] and vs[i]]
        if beta_s is None or len(both) < config.MIN_VALID:
            continue
        ei = [r[i] - beta * rm[i] for i in both]
        es = [rs[i] - beta_s * rm[i] for i in both]
        mi, ms = math.fsum(ei) / len(ei), math.fsum(es) / len(es)
        den = math.fsum((x - mi) ** 2 for x in ei) * math.fsum((y - ms) ** 2 for y in es)
        if not den > 0:
            continue
        rho = math.fsum((x - mi) * (y - ms) for x, y in zip(ei, es)) / math.sqrt(den)
        if best is None or rho > best:
            best, sector = rho, s
    return beta, mom, sector


def plain_cells(names, sector, beta, mom, rung="R0"):
    """3.3 as the pre-registration writes it: {name: cell id}."""
    out = {}
    for g in sorted({sector[i] for i in names}):
        inside = sorted(i for i in names if sector[i] == g)
        n = len(inside)
        if n <= 4:
            out.update({i: config.SMALL_CELL for i in inside})
            continue
        nb, nm = next(groups for least, groups in config.RUNGS[rung] if n >= least)
        by_beta = sorted(inside, key=lambda i: (beta[i], i))
        for b in range(nb):
            group = [i for q, i in enumerate(by_beta) if (q * nb) // n == b]
            for q, i in enumerate(sorted(group, key=lambda i: (mom[i], i))):
                out[i] = 100 * g + 10 * b + (q * nm) // len(group)
    return out


def random_closes(seed: int, names: int = 12, funds: int = 4, length: int = config.DERIVE_SESSIONS):
    rng = np.random.default_rng(seed)
    rm = rng.normal(0.0003, 0.01, length)
    fund_r = [rng.uniform(0.7, 1.2) * rm + rng.normal(0, 0.006, length) for _ in range(funds)]
    market = 100 * np.exp(np.cumsum(rm))
    fund_c = np.stack([50 * np.exp(np.cumsum(r)) for r in fund_r], axis=1)
    closes = np.empty((length, names))
    for i in range(names):
        r = rng.uniform(0.5, 1.5) * rm + 0.8 * fund_r[i % funds] + rng.normal(0, 0.01, length)
        closes[:, i] = 30 * np.exp(np.cumsum(r))
    return closes, market, fund_c


class TheCharacteristics(unittest.TestCase):
    """The pre-registration's 3.2: beta, the 12-1 momentum and the statistical sector."""

    def check(self, closes, market, funds):
        beta, mom, sector = ctx.characteristics(closes, market, funds)
        for i in range(closes.shape[1]):
            want = plain_characteristics(closes[:, i].tolist(), market.tolist(),
                                         [funds[:, s].tolist() for s in range(funds.shape[1])])
            with self.subTest(name=i):
                if want[0] is None:
                    self.assertTrue(math.isnan(beta[i]))
                else:
                    self.assertAlmostEqual(float(beta[i]), want[0], delta=1e-12)
                if want[1] is None:
                    self.assertTrue(math.isnan(mom[i]))
                else:
                    self.assertEqual(float(mom[i]), want[1])
                self.assertEqual(int(sector[i]), want[2])
        return beta, mom, sector

    def test_against_the_formula_as_a_loop(self):
        for seed in (1, 2, 3):
            closes, market, funds = random_closes(seed)
            beta, _, sector = self.check(closes, market, funds)
            self.assertTrue(np.isfinite(beta).all())
            self.assertEqual(sector.tolist(), [i % 4 for i in range(12)], "each name follows the fund it was built on")

    def test_holes_and_the_200_valid_returns(self):
        closes, market, funds = random_closes(4)
        closes[40:45, 3] = np.nan            # a hole: 6 invalid returns, still 246 valid
        closes[1:53, 6] = np.nan             # 253 - 53 = 200 closes: 199 valid returns: no beta, no sector
        closes[1:52, 7] = np.nan             # 201 closes: 200 valid returns: it has both
        funds[:60, 2] = np.nan               # the third fund starts late: 192 valid returns, never ranked
        closes[0, 8] = np.nan                # no c(d - 252): no momentum (beta and sector exist)
        closes[-1 - config.MOM_SKIP, 9] = np.nan
        beta, mom, sector = self.check(closes, market, funds)
        self.assertTrue(math.isnan(beta[6]) and sector[6] == -1 and math.isfinite(mom[6]))
        self.assertTrue(math.isfinite(beta[7]) and sector[7] >= 0)
        self.assertNotIn(2, sector.tolist())
        self.assertTrue(math.isnan(mom[8]) and math.isnan(mom[9]) and math.isfinite(beta[8]) and sector[8] >= 0)

    def test_a_tie_goes_to_the_first_fund(self):
        closes, market, funds = random_closes(5)
        twin = np.concatenate([funds[:, :1], funds], axis=1)      # fund 0 twice: columns 0 and 1 tie exactly
        _, _, sector = self.check(closes, market, twin)
        self.assertNotIn(1, sector.tolist())
        self.assertIn(0, sector.tolist())

    def test_the_momentum_is_the_12_1_return(self):
        closes, market, funds = random_closes(6)
        _, mom, _ = ctx.characteristics(closes, market, funds)
        self.assertEqual((config.MOM_SKIP, config.MOM_BACK, config.WINDOW), (21, 252, 252))
        self.assertEqual(mom.tolist(), (closes[-22] / closes[0] - 1.0).tolist())

    def test_a_window_a_session_short_has_no_momentum(self):
        """D1: a segment's first decision holds 252 sessions: beta and the sector exist, the momentum does not."""
        closes, market, funds = random_closes(7)
        beta, mom, sector = ctx.characteristics(closes[1:], market[1:], funds[1:])
        self.assertTrue(np.isnan(mom).all())
        self.assertTrue(np.isfinite(beta).all() and (sector >= 0).all())
        longer = np.concatenate([closes[:5] * 3.0, closes])        # sessions before the window are never read
        self.assertTrue(np.array_equal(ctx.characteristics(longer, np.concatenate([market[:5], market]),
                                                           np.concatenate([funds[:5], funds]))[0],
                                       ctx.characteristics(closes, market, funds)[0]))

    def test_a_session_the_market_has_no_close_is_valid_for_no_one(self):
        closes, market, funds = random_closes(8)
        market[100] = np.nan
        beta, _, _ = self.check(closes, market, funds)
        self.assertTrue(np.isfinite(beta).all())

    def test_shapes_are_checked(self):
        closes, market, funds = random_closes(9)
        with self.assertRaises(ValueError):
            ctx.characteristics(closes, market[:-1], funds)
        with self.assertRaises(ValueError):
            ctx.characteristics(closes[:, 0], market, funds)


class TheStudysVector(unittest.TestCase):
    """XSCREEN-1's conformance vector CH (league/tests/fixtures/xs1_conformance.json): the characteristics on a
    253-session window and the cells of 100 names."""

    #: numpy's first normal of the vector's seed, as the study drew it (numpy does not promise a Generator's stream
    #: across versions: a numpy that draws another world cannot rebuild the vector's inputs).
    FIRST_DRAW = None

    @classmethod
    def setUpClass(cls):
        cls.vector = json.loads((FIXTURES / "xs1_conformance.json").read_text())["vectors"]["CH"]

    def world(self):
        """The study's generator for CH, to the letter (conformance_xs1.characteristics_vector)."""
        rng = np.random.default_rng([20261011, 9400])
        n = config.WINDOW + 1
        rm = rng.normal(0.0003, 0.010, n)
        fund_r = [0.9 * rm + rng.normal(0, 0.006, n), 1.1 * rm + rng.normal(0, 0.006, n),
                  1.0 * rm + rng.normal(0, 0.006, n)]
        c_m = 100 * np.exp(np.cumsum(np.log1p(rm)))
        c_f = [50 * np.exp(np.cumsum(np.log1p(r))) for r in fund_r] + [np.full(n, np.nan)] * 8
        c_f[2][:60] = np.nan
        names = []
        for i in range(8):
            b = 0.6 + 0.1 * i
            r = b * rm + 0.7 * (fund_r[i % 2] - (0.9 if i % 2 == 0 else 1.1) * rm) + rng.normal(0, 0.010, n)
            c = 30 * np.exp(np.cumsum(np.log1p(r)))
            if i == 3:
                c[40:45] = np.nan
            if i == 6:
                c[1:70] = np.nan
            names.append(c)
        return np.stack(names, axis=1), c_m, np.stack(c_f, axis=1)

    def test_the_characteristics(self):
        closes, market, funds = self.world()
        self.assertEqual(funds.shape[1], len(config.FUNDS))
        beta, mom, sector = ctx.characteristics(closes, market, funds)
        rows = self.vector["characteristics"]
        if rows[0]["mom"] != float(mom[0]):
            self.skipTest("this numpy draws another stream for the vector's seed: its inputs cannot be rebuilt here")
        for row in rows:
            i = row["name"]
            with self.subTest(name=i):
                if row["beta"] is None:
                    self.assertTrue(math.isnan(beta[i]))
                else:
                    self.assertAlmostEqual(float(beta[i]), row["beta"], delta=1e-12)
                self.assertAlmostEqual(float(mom[i]), row["mom"], delta=1e-15)
                self.assertEqual(int(sector[i]), row["sector"])

    def test_the_cells_of_100_names(self):
        block = self.vector["cells"]
        n = block["names"]
        elig = np.ones(n, dtype=bool)
        elig[block["not_in_U"]] = False
        bg, mg, cell = ctx.cells(elig, np.array(block["sector"], dtype=np.int8), np.array(block["beta"]),
                                 np.array(block["mom"]))
        self.assertEqual(cell.tolist(), block["cell_id"])
        inside = cell[elig]
        self.assertTrue(np.array_equal(inside[inside != config.SMALL_CELL] % 10, mg[elig][inside != config.SMALL_CELL]))
        self.assertTrue((bg[~elig] == -1).all() and (mg[~elig] == -1).all())


class TheCells(unittest.TestCase):
    """The pre-registration's 3.3."""

    def test_the_group_counts_by_the_sectors_size(self):
        want = {4: None, 5: (1, 1), 9: (1, 1), 10: (1, 2), 19: (1, 2), 20: (2, 2), 44: (2, 2), 45: (3, 3), 500: (3, 3)}
        for n, groups in want.items():
            self.assertEqual(ctx.group_counts(n, "R0"), groups, n)
        for n, groups in {4: None, 5: (1, 1), 10: (1, 2), 20: (2, 2), 45: (2, 2), 500: (2, 2)}.items():
            self.assertEqual(ctx.group_counts(n, "R1"), groups, n)
        for rung in ("R2", "R3", "RB", ""):
            with self.assertRaises(ValueError):
                ctx.group_counts(50, rung)
        self.assertEqual((config.RUNG, config.MIN_CELL, config.SMALL_CELL), ("R0", 5, 9999))

    def test_against_the_text_as_a_loop_with_ties(self):
        for seed, rung in ((1, "R0"), (2, "R0"), (3, "R1"), (4, None)):
            rng = np.random.default_rng(seed)
            m = 400
            sector = rng.choice(11, m, p=[0.3, 0.2, 0.14, 0.1, 0.07, 0.06, 0.04, 0.03, 0.03, 0.02, 0.01]).astype(np.int8)
            beta = np.round(rng.normal(1.0, 0.3, m), 1)              # rounded: many ties, broken by the column
            mom = np.round(rng.normal(0.0, 0.2, m), 1)
            elig = rng.random(m) < 0.9
            bg, mg, cell = ctx.cells(elig, sector, beta, mom, rung=rung)
            names = np.flatnonzero(elig).tolist()
            want = plain_cells(names, sector.tolist(), beta.tolist(), mom.tolist(), rung or "R0")
            self.assertEqual({i: int(cell[i]) for i in names}, want)
            self.assertTrue((cell[~elig] == -1).all())
            regular = cell[elig & (cell != config.SMALL_CELL)]
            ids, counts = np.unique(regular, return_counts=True)
            self.assertGreaterEqual(int(counts.min()), config.MIN_CELL, "every cell outside the pooled one has 5 names")
            self.assertTrue(np.array_equal(cell[elig & (cell != config.SMALL_CELL)],
                                           (config.CELL_SECTOR * sector.astype(np.int32) + config.CELL_BETA * bg + mg)
                                           [elig & (cell != config.SMALL_CELL)]))

    def test_small_sectors_share_one_cell(self):
        sector = np.array([0] * 4 + [1] * 3 + [2] * 6, dtype=np.int8)
        m = sector.shape[0]
        bg, mg, cell = ctx.cells(np.ones(m, dtype=bool), sector, np.linspace(0.5, 1.5, m), np.linspace(-0.2, 0.2, m))
        self.assertEqual(cell.tolist(), [9999] * 7 + [200] * 6)
        self.assertEqual((bg[:7].tolist(), mg[:7].tolist()), ([0] * 7, [0] * 7))

    def test_terciles_are_nested_beta_then_momentum(self):
        m = 45
        beta = np.arange(m, dtype=np.float64)
        mom = -np.arange(m, dtype=np.float64)
        bg, mg, cell = ctx.cells(np.ones(m, dtype=bool), np.full(m, 3, dtype=np.int8), beta, mom)
        self.assertEqual(bg.tolist(), [0] * 15 + [1] * 15 + [2] * 15)
        self.assertEqual(mg[:15].tolist(), [2] * 5 + [1] * 5 + [0] * 5, "the lowest momentum of a beta group is 0")
        self.assertEqual(sorted(set(cell.tolist())), [300, 301, 302, 310, 311, 312, 320, 321, 322])

    def test_no_one_eligible(self):
        bg, mg, cell = ctx.cells(np.zeros(5, dtype=bool), np.zeros(5, dtype=np.int8), np.ones(5), np.ones(5))
        self.assertTrue((cell == -1).all() and (bg == -1).all() and (mg == -1).all())


class Derive(Panel):
    """The eligible set U(t) (3.1) and `derive`, the one reader."""

    def test_u_is_the_parents_part_and_two_valid_closes_and_the_three_characteristics(self):
        inputs = self.inputs()
        derived = ctx.derive(inputs)
        valid = store.valid_bars(inputs.raw) & (inputs.adj[:, :, 3] > 0)
        want = (inputs.elig0 & valid[-1] & valid[-2] & np.isfinite(derived.beta) & np.isfinite(derived.mom)
                & (derived.sector >= 0))
        self.assertTrue(np.array_equal(derived.elig, want))
        self.assertGreater(int(derived.elig.sum()), 40)
        self.assertFalse(derived.elig[:REF].any(), "a REF column is never eligible")
        self.assertTrue((derived.sector[:REF] == -1).all())
        self.assertTrue((derived.cell[~derived.elig] == -1).all() and (derived.cell[derived.elig] >= 0).all())
        self.assertEqual(derived.rung, "R0")
        self.assertEqual(ctx.derive(inputs, rung="R1").rung, "R1")
        with self.assertRaises(ValueError):
            ctx.derive(inputs, rung="R3")
        for array in (derived.elig, derived.beta, derived.cell):
            with self.assertRaises(ValueError):
                array[0] = 0

    def test_the_characteristics_are_the_formulas_on_the_adjusted_closes(self):
        inputs = self.inputs()
        derived = ctx.derive(inputs)
        closes = np.where(store.valid_bars(inputs.raw), inputs.adj[:, :, 3], np.nan)
        funds = [closes[:, col].tolist() for col in config.FUND_COLUMNS]
        market = closes[:, config.MARKET_COLUMN].tolist()
        for col in range(REF, REF + 12):
            beta, mom, sector = plain_characteristics(closes[:, col].tolist(), market, funds)
            self.assertAlmostEqual(float(derived.beta[col]), beta, delta=1e-12)
            self.assertEqual(float(derived.mom[col]), mom)
            self.assertEqual(int(derived.sector[col]), sector)
        bg, mg, cell = ctx.cells(derived.elig, derived.sector, derived.beta, derived.mom)
        self.assertTrue(np.array_equal(cell, derived.cell) and np.array_equal(bg, derived.bg))

    def test_the_market_and_the_funds_are_read_from_their_ref_columns(self):
        self.assertEqual(config.REF[config.MARKET_COLUMN], "SPY")
        self.assertEqual([config.REF[c] for c in config.FUND_COLUMNS], list(config.FUNDS))
        inputs = self.inputs()
        derived = ctx.derive(inputs)
        self.assertAlmostEqual(float(derived.beta[config.MARKET_COLUMN]), 1.0, delta=1e-12)
        # a synthetic name is built on one fund: its statistical sector is that fund, for nearly every name
        found = derived.sector[derived.elig]
        self.assertGreaterEqual(len(set(found.tolist())), 6)

    def test_a_flat_bar_of_volume_zero_is_no_close(self):
        """D4: the vendor's bar for a session without a trade. At t or at t - 1 the name is outside U."""
        inputs = self.inputs()
        col = int(np.flatnonzero(ctx.derive(inputs).elig)[0])
        for row in (-1, -2):
            raw = np.array(inputs.raw)
            raw[row, col, 4] = 0.0
            self.assertFalse(ctx.derive(self.edited(inputs, raw=raw)).elig[col])
        raw = np.array(inputs.raw)
        raw[-3, col, 4] = 0.0                                    # further back it costs two returns, not the name
        self.assertTrue(ctx.derive(self.edited(inputs, raw=raw)).elig[col])
        raw = np.array(inputs.raw)
        raw[-1, col, :] = np.nan
        self.assertFalse(ctx.derive(self.edited(inputs, raw=raw)).elig[col])

    def test_a_name_enters_once_it_has_253_sessions(self):
        inputs = self.inputs()
        col = int(np.flatnonzero(ctx.derive(inputs).elig)[0])
        raw, adj = np.array(inputs.raw), np.array(inputs.adj)
        raw[0, col, :], adj[0, col, :] = np.nan, np.nan           # its first bar is the window's second session
        derived = ctx.derive(self.edited(inputs, raw=raw, adj=adj))
        self.assertTrue(math.isnan(derived.mom[col]) and math.isfinite(derived.beta[col]))
        self.assertFalse(derived.elig[col], "a name with no 12-1 momentum is not eligible")
        short = ctx.derive(self.inputs(self.bars.first - 2))      # the slice's own first rows: fewer than 253
        self.assertEqual(self.inputs(self.bars.first - 2).days.shape[0], config.DERIVE_SESSIONS - 1)
        self.assertFalse(short.elig.any())

    def test_the_parents_part_is_needed(self):
        inputs = self.inputs()
        col = int(np.flatnonzero(ctx.derive(inputs).elig)[0])
        elig0 = np.array(inputs.elig0)
        elig0[col] = False
        self.assertFalse(ctx.derive(self.edited(inputs, elig0=elig0)).elig[col])

    def test_ineligible_names_the_open_lots_outside_u(self):
        inputs = self.inputs()
        derived = ctx.derive(inputs)
        inside = int(np.flatnonzero(derived.elig)[0])
        outside = int(np.flatnonzero(~derived.elig[REF:])[0]) + REF if (~derived.elig[REF:]).any() else None
        lots = [{"lid": 4, "col": inside}, {"lid": 9, "col": inside}]
        if outside is not None:
            lots.append({"lid": 7, "col": outside})
        book = self.edited(inputs, positions=tuple(lots))
        self.assertEqual(ctx.ineligible(book, derived), [7] if outside is not None else [])
        elig0 = np.array(inputs.elig0)
        elig0[inside] = False
        edited = self.edited(book, elig0=elig0)
        self.assertEqual(sorted(ctx.ineligible(edited, ctx.derive(edited))), [4, 7, 9] if outside is not None else [4, 9])

    def test_inputs_that_do_not_agree_are_refused(self):
        inputs = self.inputs()
        for bad in ({"raw": np.array(inputs.raw)[:-1]}, {"adj": np.array(inputs.adj)[:, :-1]}, {"ref": 11},
                    {"ids": np.array(inputs.ids)[:-1]}, {"elig0": np.array(inputs.elig0)[:-1]}):
            with self.subTest(bad=list(bad)), self.assertRaises(ValueError):
                ctx.derive(self.edited(inputs, **bad))


class TheDither(unittest.TestCase):
    """E4-SPEC D7's dither, as a formula."""

    KEY = hashlib.sha256(b"a run's dither key").digest()

    def test_the_expression(self):
        for ident, session, field in ((123456, 19000, b"c"), (-1, 20123, b"o"), (7, 1, b"v")):
            digest = hashlib.sha256(self.KEY + b"|" + str(ident).encode() + b"|" + str(session).encode() + b"|"
                                    + field).digest()
            want = (int.from_bytes(digest[:8], "big") / 2 ** 64 - 0.5) * 0.01
            self.assertEqual(ctx.dither(self.KEY, ident, session, field), want)
        digest = hashlib.sha256(self.KEY + b"|lot|" + b"42").digest()
        self.assertEqual(ctx.lot_dither(self.KEY, 42), (int.from_bytes(digest[:8], "big") / 2 ** 64 - 0.5) * 0.01)
        self.assertEqual((config.DITHER_HALF, ctx.MARKET_ID, ctx.DITHER_FIELDS), (0.005, -1, (b"o", b"h", b"l", b"c", b"v")))

    def test_it_is_uniform_on_half_a_cent_either_side(self):
        draws = np.array([ctx.dither(self.KEY, i, 19000 + i % 7, b"c") for i in range(4000)])
        self.assertTrue((draws >= -0.005).all() and (draws < 0.005).all())
        counts, _ = np.histogram(draws, bins=10, range=(-0.005, 0.005))
        self.assertTrue((np.abs(counts - 400) < 5 * math.sqrt(400 * 0.9)).all(), counts.tolist())
        self.assertLess(abs(float(draws.mean())), 3 * 0.01 / math.sqrt(12 * 4000))

    def test_one_dither_a_bar_and_field_for_the_whole_run(self):
        idents = np.array([-1, 5, 99, 123456789], dtype=np.int64)
        sessions = np.array([19000, 19001, 19004], dtype=np.int32)
        ctx._DITHERS.clear()
        first = ctx._dithers(self.KEY, idents, sessions)
        for s, session in enumerate(sessions.tolist()):
            for i, ident in enumerate(idents.tolist()):
                for f, field in enumerate(ctx.DITHER_FIELDS):
                    self.assertEqual(first[s, i, f], ctx.dither(self.KEY, ident, session, field))
        again = ctx._dithers(self.KEY, idents, np.array([19004, 19000, 19007], dtype=np.int32))
        self.assertTrue(np.array_equal(again[0], first[2]) and np.array_equal(again[1], first[0]))
        other = ctx._dithers(hashlib.sha256(b"another run").digest(), idents, sessions)
        self.assertFalse(np.array_equal(other, first))
        self.assertLessEqual(len(ctx._DITHERS), ctx._DITHER_RUNS)

    def test_the_kept_dithers_are_bounded(self):
        ctx._DITHERS.clear()
        idents = np.array([1], dtype=np.int64)
        for run in range(ctx._DITHER_RUNS + 3):
            ctx._dithers(hashlib.sha256(str(run).encode()).digest(), idents, np.array([1, 2], dtype=np.int32))
        self.assertEqual(len(ctx._DITHERS), ctx._DITHER_RUNS)


class Build(Panel):
    """The ctx of the registered contract C1."""

    #: Fifteen names pay a dividend and five split 4 for 1 in February 2025.
    PAYERS, SPLITTERS = tuple(range(100, 115)), tuple(range(115, 120))
    KWARGS = {"dividends": {aid: [(D(2024, 9, 16), 0.4), (D(2025, 2, 18), 0.4)] for aid in PAYERS},
              "splits": {aid: (D(2025, 2, 3), 4.0) for aid in SPLITTERS}}

    def test_exactly_the_contracts_slots(self):
        c = ctx.build(self.inputs())
        self.assertEqual(ctx.XsCtx.__slots__, (
            "n", "ids", "ret", "oret", "iret", "range", "rel_volume", "sector", "beta", "mkt", "positions", "closed",
            "rejects", "cash", "equity", "budget", "weekday", "session_of_month", "sessions_left_in_month",
            "last_session_of_week", "max_names", "params"))
        self.assertFalse(hasattr(c, "__dict__"))
        for name in ctx.XsCtx.__slots__:
            self.assertIsNotNone(getattr(c, name), name)
        self.assertEqual(ctx.Fields.__slots__, ctx.FIELDS)

    def test_the_slots_are_u_in_ascending_id(self):
        inputs = self.inputs()
        derived = ctx.derive(inputs)
        c = ctx.build(inputs)
        self.assertEqual(c.n, int(derived.elig.sum()))
        self.assertTrue(np.array_equal(c.ids, inputs.ids[derived.elig[REF:]]))
        self.assertTrue((np.diff(c.ids) > 0).all())
        h = NEEDS.history
        for name in ctx.FIELDS:
            self.assertEqual(getattr(c, name).shape, (c.n, h + 1), name)
            self.assertEqual(getattr(c.mkt, name).shape, (h + 1,), name)
        self.assertEqual((c.ids.dtype, c.sector.dtype, c.beta.dtype, c.ret.dtype),
                         (np.dtype(np.int32), np.dtype(np.int8), np.dtype(np.float64), np.dtype(np.float64)))
        self.assertEqual((c.sector.shape, c.beta.shape), ((c.n,), (c.n,)))

    def test_the_fields_are_ratios_of_dithered_adjusted_prices(self):
        """ret = c' / c'(-1) - 1, oret = o' / c'(-1) - 1, iret = c' / o' - 1, range = (h' - l') / c', each price p' =
        the bar's adjusted price + its own u; 6 decimals."""
        inputs = self.inputs()
        derived = ctx.derive(inputs)
        c = ctx.build(inputs)
        key, days = inputs.dither_key, inputs.days.tolist()
        slots = np.flatnonzero(derived.elig)
        for at in (0, 7, c.n - 1, None):                                        # None: the market
            col = config.MARKET_COLUMN if at is None else int(slots[at])
            ident = ctx.MARKET_ID if at is None else int(c.ids[at])
            got = c.mkt if at is None else None

            def price(row: int, field: int) -> float:
                return float(inputs.adj[row, col, field]) + ctx.dither(key, ident, days[row], ctx.DITHER_FIELDS[field])

            for back in (0, 1, 5, 100, 251):
                row = len(days) - 1 - back
                o, h, low, close, prev = price(row, 0), price(row, 1), price(row, 2), price(row, 3), price(row - 1, 3)
                want = {"ret": close / prev - 1, "oret": o / prev - 1, "iret": close / o - 1, "range": (h - low) / close}
                for name, value in want.items():
                    field = getattr(got, name) if at is None else getattr(c, name)[at]
                    self.assertEqual(float(field[-1 - back]), round(value, config.CTX_PLACES), (at, back, name))
        self.assertTrue(np.isnan(c.ret[:, 0]).all() and np.isnan(c.oret[:, 0]).all(), "the first return has no close before")
        self.assertTrue(np.isfinite(c.iret[:, 0]).all())

    def test_a_field_is_rounded_to_six_decimals_and_beta_to_two(self):
        c = ctx.build(self.inputs())
        for name in ctx.FIELDS:
            values = getattr(c, name)
            values = values[np.isfinite(values)]
            self.assertTrue(np.array_equal(values, np.round(values, 6)), name)
        self.assertTrue(np.array_equal(c.beta, np.round(c.beta, 2)))
        self.assertEqual((config.CTX_PLACES, config.BETA_PLACES), (6, 2))
        derived = ctx.derive(self.inputs())
        self.assertTrue(np.array_equal(c.beta, np.round(derived.beta[derived.elig], 2)))

    def test_the_sector_is_relabelled_by_the_runs_salt(self):
        inputs = self.inputs()
        derived = ctx.derive(inputs)
        c = ctx.build(inputs)
        perm = np.asarray(inputs.sector_perm)
        self.assertEqual(sorted(perm.tolist()), list(range(11)))
        self.assertTrue(np.array_equal(c.sector, perm[derived.sector[derived.elig]]))
        self.assertFalse(np.array_equal(c.sector, derived.sector[derived.elig]), "the House's own code never shows")
        with self.assertRaises(ValueError):
            ctx.build(self.edited(inputs, sector_perm=np.zeros(11, dtype=np.int8)))

    def test_rel_volume_is_the_volume_over_its_trailing_median(self):
        """The volume on the total-return basis, times (1 + u_v); over the median of the 63 sessions through it."""
        inputs = self.inputs()
        derived = ctx.derive(inputs)
        c = ctx.build(inputs)
        key, days = inputs.dither_key, inputs.days.tolist()
        self.assertEqual((config.REL_VOLUME_SESSIONS, ctx.REL_VOLUME_MIN_VALID), (63, 32))
        slots = np.flatnonzero(derived.elig)
        for at in (0, 3, None):
            col = config.MARKET_COLUMN if at is None else int(slots[at])
            ident = ctx.MARKET_ID if at is None else int(c.ids[at])

            def volume(row: int) -> float:
                raw, adj = inputs.raw[row, col], inputs.adj[row, col]
                return float(raw[4] * raw[3] / adj[3] * (1.0 + ctx.dither(key, ident, days[row], b"v")))

            got = c.mkt.rel_volume if at is None else c.rel_volume[at]
            for back in (0, 1, 60, 190):
                row = len(days) - 1 - back
                median = statistics.median(volume(r) for r in range(row - 62, row + 1))
                self.assertAlmostEqual(float(got[-1 - back]), round(volume(row) / median, 6), delta=1.5e-6)
            self.assertTrue(np.isnan(got[:62]).all(), "the decision does not hold the 63 sessions through these")
            self.assertTrue(np.isfinite(got[62:]).all())

    def test_rel_volume_reads_a_session_the_inputs_do_not_hold_as_one_without_a_bar(self):
        """The Gym's first windows of a store are shorter than a live fetch's 253 rows, whose missing sessions are
        rows of NaN: both give the same field."""
        inputs = self.inputs()
        cut = 150
        short = self.edited(inputs, days=np.array(inputs.days)[cut:], raw=np.array(inputs.raw)[cut:],
                            adj=np.array(inputs.adj)[cut:])
        raw, adj = np.array(inputs.raw), np.array(inputs.adj)
        raw[:cut], adj[:cut] = np.nan, np.nan
        raw[:cut, config.MARKET_COLUMN], adj[:cut, config.MARKET_COLUMN] = np.nan, np.nan
        padded = self.edited(inputs, raw=raw, adj=adj)
        a, b = ctx.build(short), ctx.build(padded)
        self.assertEqual((a.n, b.n), (0, 0), "253 sessions of history are not there: no slot")
        for name in ctx.FIELDS:
            self.assertTrue(np.array_equal(getattr(a.mkt, name), getattr(b.mkt, name), equal_nan=True), name)
        self.assertTrue(np.isnan(a.mkt.rel_volume[:cut + 31]).all(), "fewer than 32 sessions with a bar")
        self.assertTrue(np.isfinite(a.mkt.rel_volume[cut + 31:]).all())
        self.assertEqual(ctx.ctx_bytes(a), ctx.ctx_bytes(b))

    def test_rel_volume_needs_its_valid_bars_and_ignores_the_missing(self):
        inputs = self.inputs()
        col = int(np.flatnonzero(ctx.derive(inputs).elig)[0])
        raw = np.array(inputs.raw)
        raw[-90:-40, col, 4] = 0.0                                 # fifty sessions without a trade
        edited = self.edited(inputs, raw=raw)
        derived = ctx.derive(edited)
        self.assertTrue(derived.elig[col], "201 valid returns and both momentum closes: still in U")
        c = ctx.build(edited)
        at = int(np.flatnonzero(derived.elig).tolist().index(col))
        self.assertTrue(np.isnan(c.rel_volume[at, -90:-9]).all(), "no bar, then fewer than 32 valid bars in the 63")
        self.assertTrue(np.isfinite(c.rel_volume[at, -9:]).all(), "32 valid bars: the missing ones are not in the median")
        self.assertTrue(np.isnan(c.ret[at, -90:-39]).all() and np.isfinite(c.ret[at, -39:]).all())
        self.assertTrue(np.isnan(c.iret[at, -90:-40]).all() and np.isfinite(c.iret[at, -40:]).all())

    def test_a_split_leaves_no_step_in_the_volume(self):
        """Five names split 4 for 1 in February 2025: their adjusted prices are a quarter of the raw ones before it,
        and `rel_volume` reads the volume on that basis: nothing dates the session."""
        t = self.bars.days.tolist().index(ordinal(D(2025, 3, 31)))
        inputs = self.inputs(t)
        derived = ctx.derive(inputs)
        c = ctx.build(inputs)
        split_row = inputs.days.tolist().index(ordinal(D(2025, 2, 3)))
        seen = 0
        for aid in self.SPLITTERS:
            column = self.slice.aids.tolist().index(aid)
            ratio = inputs.adj[:, column, 3] / inputs.raw[:, column, 3]
            self.assertAlmostEqual(float(ratio[0]), 0.25, delta=0.01)
            self.assertAlmostEqual(float(ratio[-1]), 1.0, delta=0.01)
            if not derived.elig[column]:
                continue
            seen += 1
            row = c.rel_volume[np.flatnonzero(derived.elig).tolist().index(column)]
            before, after = row[split_row - 40:split_row], row[split_row:split_row + 40]
            # the raw share volume is four times larger from the ex-day on; on the total-return basis it has no step
            shares = inputs.raw[:, column, 4]
            self.assertGreater(float(np.median(shares[split_row:split_row + 40]) / np.median(shares[split_row - 40:split_row])), 2.5)
            self.assertLess(abs(math.log(float(np.median(after)) / float(np.median(before)))), math.log(1.6))
        self.assertGreater(seen, 0)

    def test_the_arrays_are_read_only_over_immutable_buffers(self):
        c = ctx.build(self.inputs())
        for array in (c.ids, c.ret, c.rel_volume, c.sector, c.beta, c.mkt.ret, c.mkt.range):
            with self.assertRaises(ValueError):
                array[0] = 1
            with self.assertRaises(ValueError):
                array.setflags(write=True)

    def test_the_calendars_four_counts(self):
        days = self.bars.days.tolist()

        def at(day: dt.date):
            return ctx.build(self.inputs(days.index(ordinal(day))))

        first = at(D(2025, 4, 1))
        self.assertEqual((first.weekday, first.session_of_month, first.last_session_of_week), (1, 1, False))
        self.assertEqual(first.sessions_left_in_month, len(nyse_sessions(D(2025, 4, 2), D(2025, 4, 30))))
        last = at(D(2025, 4, 30))
        self.assertEqual((last.weekday, last.sessions_left_in_month), (2, 0))
        self.assertEqual(last.session_of_month, len(nyse_sessions(D(2025, 4, 1), D(2025, 4, 30))))
        self.assertTrue(at(D(2025, 4, 11)).last_session_of_week, "a Friday")
        self.assertTrue(at(D(2025, 4, 17)).last_session_of_week, "the Thursday before Good Friday")
        self.assertFalse(at(D(2025, 4, 16)).last_session_of_week)
        self.assertTrue(at(D(2025, 5, 30)).last_session_of_week and at(D(2025, 5, 30)).sessions_left_in_month == 0)
        for name in ("weekday", "session_of_month", "sessions_left_in_month", "max_names"):
            self.assertIs(type(getattr(first, name)), int, name)
        self.assertIs(type(first.last_session_of_week), bool)

    def test_a_held_lots_weight_and_ret_are_dithered_and_the_equity_is_marked_at_them(self):
        inputs = self.inputs()
        derived = ctx.derive(inputs)
        col_a, col_b = (int(x) for x in np.flatnonzero(derived.elig)[:2])
        t = len(inputs.days) - 1
        lots = ({"lid": 3, "col": col_a, "qty": 1.25, "value": 0.0, "entry_value": 180.0, "held_sessions": 4,
                 "at": "open", "tag": "a"},
                {"lid": 8, "col": col_b, "qty": 0.5, "value": 0.0, "entry_value": 40.0, "held_sessions": 0,
                 "at": "close", "tag": ""})
        c = ctx.build(self.edited(inputs, positions=lots, cash=612.337, equity=999999.0))
        key, day = inputs.dither_key, int(inputs.days[t])
        closes = [float(inputs.raw[t, col, 3]) + ctx.dither(key, int(inputs.ids[col - REF]), day, b"c")
                  for col in (col_a, col_b)]
        equity = round(612.337 + 1.25 * closes[0] + 0.5 * closes[1], 2)
        self.assertEqual((c.cash, c.equity), (612.34, equity))
        want = []
        for lot, close in zip(lots, closes):
            basis = lot["entry_value"] / lot["qty"] + ctx.lot_dither(key, lot["lid"])
            want.append({"id": lot["lid"], "slot": int(inputs.ids[lot["col"] - REF]),
                         "weight": round(lot["qty"] * close / equity, 4), "ret": round(close / basis - 1.0, 4),
                         "held_sessions": lot["held_sessions"], "at": lot["at"], "tag": lot["tag"]})
        self.assertEqual(c.positions, want)
        self.assertEqual(list(c.positions[0]), ["id", "slot", "weight", "ret", "held_sessions", "at", "tag"])
        self.assertEqual((ctx.LOT_PLACES, ctx.USD_PLACES), (4, 2))

    def test_a_lot_of_a_name_with_no_bar_at_t_is_marked_at_its_last_bar(self):
        inputs = self.inputs()
        col = int(np.flatnonzero(ctx.derive(inputs).elig)[0])
        raw, adj = np.array(inputs.raw), np.array(inputs.adj)
        raw[-2:, col, :], adj[-2:, col, :] = np.nan, np.nan
        lot = {"lid": 5, "col": col, "qty": 2.0, "value": 1.0, "entry_value": 100.0, "held_sessions": 9, "at": "open",
               "tag": ""}
        edited = self.edited(inputs, raw=raw, adj=adj, positions=(lot,), cash=10.0)
        c = ctx.build(edited)
        row = len(inputs.days) - 3
        self.assertEqual(e1ctx._factor_row(raw[:, col], adj[:, col]), row)
        close = float(raw[row, col, 3]) + ctx.dither(inputs.dither_key, int(inputs.ids[col - REF]),
                                                     int(inputs.days[row]), b"c")
        self.assertEqual(c.equity, round(10.0 + 2.0 * close, 2))
        self.assertNotIn(int(inputs.ids[col - REF]), c.ids.tolist(), "it is outside U: no slot")
        self.assertEqual(c.positions[0]["slot"], int(inputs.ids[col - REF]), "but its lot still names its id")
        gone = np.array(inputs.raw)
        gone[:, col, :] = np.nan
        blank = ctx.build(self.edited(inputs, raw=gone, adj=np.where(np.isnan(gone[:, :, :4]), np.nan, inputs.adj),
                                      positions=({**lot, "value": 77.0},), cash=10.0, equity=87.004))
        self.assertEqual((blank.equity, blank.positions[0]["ret"]), (87.0, None), "no bar at all: the book's own mark")

    def test_closed_lots_rejects_and_the_sleeves_figures(self):
        inputs = self.inputs()
        col = int(np.flatnonzero(ctx.derive(inputs).elig)[0])
        closed = ({"lid": 2, "col": col, "net_ret": 0.0123456, "held_sessions": 5, "reason": "max_hold", "tag": "t"},)
        c = ctx.build(self.edited(inputs, closed=closed, rejects=("order cap", "no bar"), budget=557.254))
        self.assertEqual(c.closed, [{"id": 2, "slot": int(inputs.ids[col - REF]), "net_ret": 0.0123,
                                     "held_sessions": 5, "reason": "max_hold", "tag": "t"}])
        self.assertEqual((c.rejects, c.budget, c.max_names, c.params), (["order cap", "no bar"], 557.25, 10,
                                                                        {"theta": 0.5}))
        c.params["theta"] = 9
        self.assertEqual(inputs.params, {"theta": 0.5}, "the ctx's PARAMS are a copy")
        lot = {"lid": 1, "col": col, "qty": 1.0, "value": 1.0, "entry_value": 1.0, "held_sessions": 0, "at": "open"}
        done = {"lid": 1, "col": col, "net_ret": 0.0, "held_sessions": 0, "reason": "x"}
        for bad in ({"positions": ({**lot, "col": 0},)}, {"closed": ({**done, "col": 10 ** 6},)},
                    {"positions": ({k: v for k, v in lot.items() if k != "qty"},)},
                    {"positions": ({**lot, "entry_value": "much"},)},
                    {"closed": ({k: v for k, v in done.items() if k != "reason"},)},
                    {"closed": ({**done, "net_ret": "some"},)}):
            with self.subTest(bad=str(bad)[:60]), self.assertRaises(ValueError):
                ctx.build(self.edited(inputs, **bad))
        with self.assertRaises(ValueError):
            ctx.ineligible(self.edited(inputs, positions=({"lid": 1},)), ctx.derive(inputs))
        self.assertEqual(ctx.build(self.edited(inputs, positions=(lot,))).positions[0]["tag"], "", "a tag is optional")

    def test_a_shorter_history_is_the_same_ctxs_last_columns(self):
        long = ctx.build(self.inputs())
        short = ctx.build(self.inputs(needs=Needs("sp500", 20, 7, "monthly", 0, 30)))
        self.assertEqual((short.ret.shape, short.max_names), ((long.n, 21), 7))
        for name in ctx.FIELDS:
            self.assertTrue(np.array_equal(getattr(short, name), getattr(long, name)[:, -21:], equal_nan=True), name)
            self.assertTrue(np.array_equal(getattr(short.mkt, name), getattr(long.mkt, name)[-21:], equal_nan=True))
        for history in (19, 253):
            with self.assertRaises(ValueError):
                ctx.build(self.edited(self.inputs(), history=history))

    def test_a_decision_short_of_its_history_has_no_slot_and_the_market_is_padded(self):
        """A segment's first decision: 252 sessions. No name has a momentum, so no slot; the market's arrays keep
        their shape."""
        inputs = self.inputs(self.bars.first - 2)
        c = ctx.build(inputs)
        self.assertEqual((c.n, c.ret.shape, c.mkt.ret.shape), (0, (0, 253), (253,)))
        self.assertTrue(np.isnan(c.mkt.ret[:2]).all() and np.isfinite(c.mkt.ret[2:]).all())

    def test_the_market_needs_its_bar_at_t(self):
        inputs = self.inputs()
        raw = np.array(inputs.raw)
        raw[-1, config.MARKET_COLUMN, 4] = 0.0
        with self.assertRaises(ValueError) as caught:
            ctx.build(self.edited(inputs, raw=raw))
        self.assertIn("SPY", str(caught.exception))

    def test_the_same_inputs_give_the_same_bytes_whatever_this_process_kept(self):
        inputs = self.inputs()
        first = ctx.ctx_bytes(ctx.build(inputs))
        self.assertEqual(ctx.ctx_bytes(ctx.build(inputs)), first)
        self.assertEqual(ctx.ctx_bytes(ctx.build(inputs, ctx.derive(inputs))), first)
        ctx._DITHERS.clear()
        ctx._REL.clear()
        self.assertEqual(ctx.ctx_bytes(ctx.build(inputs)), first)
        self.assertEqual(ctx.ctx_bytes(ctx.build(pickle.loads(pickle.dumps(inputs)))), first, "as the child reads it")
        with self.assertRaises(ValueError):
            ctx.build(inputs, ctx.derive(self.edited(inputs, raw=np.array(inputs.raw)[:, :-1],
                                                     adj=np.array(inputs.adj)[:, :-1],
                                                     elig0=np.array(inputs.elig0)[:-1], ids=np.array(inputs.ids)[:-1])))

    def test_what_is_kept_is_kept_by_content(self):
        """A kept `rel_volume` row is the row a fresh computation gives: other volumes under the same run key and ids
        are never answered from memory."""
        inputs = self.inputs()
        ctx.build(inputs)
        raw = np.array(inputs.raw)
        raw[-30:, REF:, 4] *= 3.0
        edited = self.edited(inputs, raw=raw)
        kept = ctx.ctx_bytes(ctx.build(edited))
        ctx._REL.clear()
        ctx._DITHERS.clear()
        self.assertEqual(ctx.ctx_bytes(ctx.build(edited)), kept)
        self.assertNotEqual(kept, ctx.ctx_bytes(ctx.build(inputs)))

    def test_a_bars_fields_are_the_same_numbers_in_every_ctx_of_a_run(self):
        """No as-of product is formed: across an ex-dividend date and a split, a later ctx shows an earlier bar
        exactly as the earlier ctx did (two views of one bar give a program nothing to compare)."""
        days = self.bars.days.tolist()
        early_t, late_t = days.index(ordinal(D(2025, 1, 31))), days.index(ordinal(D(2025, 3, 31)))
        gap = late_t - early_t
        early, late = ctx.build(self.inputs(early_t)), ctx.build(self.inputs(late_t))
        common = sorted(set(early.ids.tolist()) & set(late.ids.tolist()))
        self.assertGreater(len(common), 30)
        a = [early.ids.tolist().index(i) for i in common]
        b = [late.ids.tolist().index(i) for i in common]
        for name in ("ret", "oret", "iret", "range"):
            self.assertTrue(np.array_equal(getattr(early, name)[a][:, gap + 1:], getattr(late, name)[b][:, 1:-gap],
                                           equal_nan=True), name)
            self.assertTrue(np.array_equal(getattr(early.mkt, name)[gap + 1:], getattr(late.mkt, name)[1:-gap],
                                           equal_nan=True), name)
        # a dividend or a split fell between the two days for some of them
        idents = {aid: int(self.bars.ids[self.slice.aids.tolist().index(aid) - REF])
                  for aid in (*self.PAYERS, *self.SPLITTERS)}
        self.assertGreaterEqual(len([a for a in self.PAYERS if idents[a] in common]), 5)
        self.assertGreaterEqual(len([a for a in self.SPLITTERS if idents[a] in common]), 1)


class TheVendorsCents(unittest.TestCase):
    """adjustment=all is served rounded to the cent: two fetches of one history differ by that rounding, so a live
    ctx equals a later store's only within it (never byte for byte by assumption)."""

    def test_two_vintages_agree_within_the_cents_bound(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = {"dividends": {aid: [(D(2025, 11, 17), 0.5)] for aid in range(100, 130)}, "churn": 0.0}
            before = store.PanelStore(make_panel(tmp + "/a", as_of=D(2025, 9, 30), **args))
            after = store.PanelStore(make_panel(tmp + "/b", **args))
            kwargs = {"history": 252, "run_key": "k", "start": D(2025, 9, 1), "end": D(2025, 9, 30)}
            old, new = before.bars("validation", **kwargs).bars, after.bars("validation", **kwargs).bars
            t = old.n - 1
            self.assertEqual(int(old.days[t]), int(new.days[t]))
            self.assertTrue(np.array_equal(old.raw[:t + 1], new.raw[:t + 1], equal_nan=True), "one raw history")
            self.assertFalse(np.array_equal(old.adj[:t + 1], new.adj[:t + 1], equal_nan=True), "two vintages")
            a = ctx.build(ctx.inputs_from_panel(old, t, needs=NEEDS, **BOOK))
            b = ctx.build(ctx.inputs_from_panel(new, t, needs=NEEDS, **BOOK))
            self.assertTrue(np.array_equal(a.ids, b.ids), "the same names are eligible under both")
            self.assertNotEqual(ctx.ctx_bytes(a), ctx.ctx_bytes(b))
            worst = float(np.nanmax(np.abs(a.ret - b.ret)))
            lowest = float(np.nanmin(new.adj[:t + 1, REF:, 3]))
            self.assertGreater(worst, 0.0)
            self.assertLess(worst, 2 * config.rounding_bound(lowest, lowest) + 2e-6,
                            "a return differs by no more than the cent rounding of its two prices explains")


class TheInputs(Panel):
    """The Gym's inputs and the live path's: one ctx."""

    def test_the_gyms_inputs_never_hold_a_row_after_t(self):
        t = self.bars.first + 25
        inputs = self.inputs(t)
        self.assertEqual(inputs.days.shape[0], config.DERIVE_SESSIONS)
        self.assertEqual(int(inputs.days[-1]), int(self.bars.days[t]))
        self.assertTrue(np.array_equal(inputs.raw, self.bars.raw[t - 252:t + 1], equal_nan=True))
        self.assertTrue(np.array_equal(inputs.elig0, self.bars.elig0[t]))
        self.assertEqual((inputs.ref, inputs.history, inputs.max_names), (REF, 252, 10))
        # the same slice with everything after t replaced by garbage gives the same ctx, byte for byte
        raw, adj, elig0 = np.array(self.bars.raw), np.array(self.bars.adj), np.array(self.bars.elig0)
        raw[t + 1:], adj[t + 1:], elig0[t + 1:] = 1e9, 1e9, True
        cut = dataclasses.replace(self.bars, raw=raw, adj=adj, elig0=elig0)
        self.assertEqual(ctx.ctx_bytes(ctx.build(ctx.inputs_from_panel(cut, t, needs=NEEDS, **BOOK))),
                         ctx.ctx_bytes(ctx.build(inputs)))
        for bad in (-1, self.bars.n):
            with self.assertRaises(ValueError):
                self.inputs(bad)

    def test_the_calendar_around_t_is_e1s(self):
        inputs = self.inputs()
        trading, early = e1ctx.calendar_around(from_ordinal(int(inputs.days[-1])))
        self.assertTrue(np.array_equal(inputs.trading_days, trading) and np.array_equal(inputs.early, early))

    def test_the_live_builder_gives_the_gyms_bytes(self):
        """I6 on a synthetic panel (package D's `test_xs_i6` is the seal; this holds the helper to its word)."""
        cases = synth.same_ctx_cases(self.root, history=60, count=6, seed=3)
        self.assertEqual(len(cases), 6)
        self.assertTrue(any(case["straddles"] for case in cases), "one case straddles an index change")
        for case in cases:
            live = ctx.inputs_from_fetch(case["raw_rows"], case["all_rows"], day=case["day"],
                                         columns=case["columns"], **case["common"])
            self.assertEqual(ctx.ctx_bytes(ctx.build(live)), ctx.ctx_bytes(ctx.build(case["gym"])), case["day"])
            self.assertEqual(case["columns"][:REF], list(config.REF))
            self.assertEqual(len(case["columns"]), len(set(case["columns"])))
            members = {aid for aid, _ in self.panel.universe().members(case["day"])}
            extra = [int(a) for a in case["aids"][REF:] if int(a) not in members]
            self.assertLessEqual(len(extra), 2)
            self.assertTrue(all(lot["col"] >= REF for lot in case["common"]["positions"]))
            held = {int(case["aids"][lot["col"]]) for lot in case["common"]["positions"]}
            self.assertTrue(set(extra) <= held, "the names that left the index are held")
            # the helper's book: lots 1 and 2 left the index (the House's exits), lot 3 is a slot of the day
            gym = ctx.build(case["gym"])
            self.assertEqual([lot["id"] for lot in gym.positions], [1, 2, 3])
            self.assertEqual(ctx.ineligible(case["gym"], ctx.derive(case["gym"])), [1, 2])
            self.assertEqual([lot["slot"] in gym.ids.tolist() for lot in gym.positions], [False, False, True])
        self.assertTrue(any(len([a for a in case["aids"][REF:] if not self.panel.universe().member(int(a), case["day"])])
                            == 2 for case in cases))

    def test_rows_become_arrays_on_the_days_253_sessions(self):
        case = synth.same_ctx_cases(self.root, history=20, count=1, seed=1)[0]
        day, columns = case["day"], case["columns"]
        days, raw, adj = ctx.rows_to_arrays(case["raw_rows"], case["all_rows"], day=day, columns=columns)
        self.assertEqual(days.tolist(), [ordinal(d) for d in ctx.fetch_sessions(day)])
        self.assertEqual((days.shape[0], raw.shape, adj.shape),
                         (253, (253, len(columns), 5), (253, len(columns), 4)))
        self.assertTrue(np.array_equal(raw, case["gym"].raw, equal_nan=True))
        self.assertTrue(np.array_equal(adj, case["gym"].adj, equal_nan=True))
        # one chunk at a time: the columns are the same arrays
        half = len(columns) // 2
        left = ctx.rows_to_arrays(case["raw_rows"], case["all_rows"], day=day, columns=columns[:half])
        right = ctx.rows_to_arrays(case["raw_rows"], case["all_rows"], day=day, columns=columns[half:])
        self.assertTrue(np.array_equal(np.concatenate([left[1], right[1]], axis=1), raw, equal_nan=True))
        self.assertTrue(np.array_equal(left[0], right[0]))
        # a symbol with no row is a column of NaN; a row after the day is dropped
        later = {"t": synth._stamp(D(2026, 6, 1)), "o": 1.0, "h": 1.0, "l": 1.0, "c": 1.0, "v": 1.0}
        rows = {**case["raw_rows"], columns[0]: [*case["raw_rows"][columns[0]], later]}
        _, again, _ = ctx.rows_to_arrays(rows, case["all_rows"], day=day, columns=[columns[0], "NOSUCH"])
        self.assertTrue(np.array_equal(again[:, 0], raw[:, 0], equal_nan=True) and np.isnan(again[:, 1]).all())

    def test_rows_that_cannot_be_placed_are_refused(self):
        case = synth.same_ctx_cases(self.root, history=20, count=1, seed=1)[0]
        day, symbol = case["day"], case["columns"][0]
        rows = case["raw_rows"][symbol]
        with self.assertRaises(ValueError) as caught:
            ctx.rows_to_arrays({symbol: [*rows, rows[-1]]}, case["all_rows"], day=day, columns=[symbol])
        self.assertIn("twice", str(caught.exception))
        saturday = day - dt.timedelta(days=(day.weekday() + 2) % 7 or 7)
        self.assertEqual(saturday.weekday(), 5)
        weekend = {**rows[-1], "t": synth._stamp(saturday)}
        with self.assertRaises(ValueError) as caught:
            ctx.rows_to_arrays({symbol: [*rows, weekend]}, case["all_rows"], day=day, columns=[symbol])
        self.assertIn("not a session", str(caught.exception))
        with self.assertRaises(ValueError):
            ctx.rows_to_arrays(case["raw_rows"], case["all_rows"], day=saturday, columns=[symbol])

    def test_the_live_inputs_are_refused_when_they_cannot_be_a_decisions(self):
        case = synth.same_ctx_cases(self.root, history=20, count=1, seed=2)[0]
        day, columns, common = case["day"], case["columns"], case["common"]
        days, raw, adj = ctx.rows_to_arrays(case["raw_rows"], case["all_rows"], day=day, columns=columns)
        ctx.inputs_from_arrays(days, raw, adj, day=day, **common)
        no_spy = raw.copy()
        no_spy[-1, config.MARKET_COLUMN, :] = np.nan
        with self.assertRaises(ValueError) as caught:
            ctx.inputs_from_arrays(days, no_spy, adj, day=day, **common)
        self.assertIn("disagree", str(caught.exception))
        gone = adj.copy()
        gone[-1, config.MARKET_COLUMN, :] = np.nan
        with self.assertRaises(ValueError) as caught:
            ctx.inputs_from_arrays(days, no_spy, gone, day=day, **common)
        self.assertIn("SPY has no bar", str(caught.exception))
        flat = raw.copy()
        flat[-1, config.MARKET_COLUMN, 4] = 0.0
        with self.assertRaises(ValueError):
            ctx.inputs_from_arrays(days, flat, adj, day=day, **common)
        odd = adj.copy()
        odd[5, REF + 1, :] = np.nan
        with self.assertRaises(ValueError) as caught:
            ctx.inputs_from_arrays(days, raw, odd, day=day, **common)
        self.assertIn("disagree on their sessions", str(caught.exception))
        with self.assertRaises(ValueError):
            ctx.inputs_from_arrays(days[:-1], raw[:-1], adj[:-1], day=day, **common)
        with self.assertRaises(ValueError):
            ctx.inputs_from_arrays(days, raw[:, :, :4], adj, day=day, **common)
        rows = {s: case["raw_rows"][s] for s in columns}
        rows["SPY"] = rows["SPY"][:-1]
        with self.assertRaises(ValueError):
            ctx.inputs_from_fetch(rows, case["all_rows"], day=day, columns=columns, **common)

    def test_a_fetchs_sessions_never_cross_the_reserve(self):
        self.assertEqual(len(ctx.fetch_sessions(D(2026, 10, 9))), 253)
        early = ctx.fetch_sessions(D(2021, 3, 1))
        self.assertEqual(early[0], D(2021, 1, 4))
        self.assertLess(len(early), 253)
        self.assertEqual(len(ctx.fetch_sessions(D(2019, 12, 31))), 253)
        for closed in (D(2026, 10, 10), D(2020, 6, 1), D(2015, 6, 1)):
            with self.assertRaises(ValueError):
                ctx.fetch_sessions(closed)


class TheBytes(Panel):
    def test_the_prefix_is_the_panels_own(self):
        data = ctx.ctx_bytes(ctx.build(self.inputs()))
        self.assertTrue(data.startswith(b"xs-ctx-1;"))
        self.assertEqual(ctx.CTX_PREFIX, b"xs-ctx-1;")
        self.assertFalse(data.startswith(b"equity-ctx-1;"))

    def test_every_slot_is_in_the_bytes(self):
        c = ctx.build(self.inputs())
        base = ctx.ctx_bytes(c)
        changes = {"n": c.n + 1, "ids": c.ids[::-1].copy(), "ret": c.ret * 2, "oret": c.oret * 2, "iret": c.iret * 2,
                   "range": c.range * 2, "rel_volume": c.rel_volume * 2, "sector": (c.sector + 1).astype(np.int8),
                   "beta": c.beta + 0.01, "positions": [{"id": 1}], "closed": [{"id": 2}], "rejects": ["x"],
                   "cash": c.cash + 1, "equity": c.equity + 1, "budget": c.budget + 1, "weekday": c.weekday + 1,
                   "session_of_month": c.session_of_month + 1, "sessions_left_in_month": c.sessions_left_in_month + 1,
                   "last_session_of_week": not c.last_session_of_week, "max_names": c.max_names + 1,
                   "params": {"theta": 1.0}}
        for name, value in changes.items():
            other = ctx.XsCtx(**{slot: getattr(c, slot) for slot in ctx.XsCtx.__slots__})
            object.__setattr__(other, name, value)
            self.assertNotEqual(ctx.ctx_bytes(other), base, name)
        for name in ctx.FIELDS:
            other = ctx.XsCtx(**{slot: getattr(c, slot) for slot in ctx.XsCtx.__slots__})
            fields = {field: getattr(c.mkt, field) for field in ctx.FIELDS}
            fields[name] = fields[name] * 2
            object.__setattr__(other, "mkt", ctx.Fields(**fields))
            self.assertNotEqual(ctx.ctx_bytes(other), base, f"mkt.{name}")
        self.assertEqual(set(changes) | {"mkt"}, set(ctx.XsCtx.__slots__))


if __name__ == "__main__":
    unittest.main()
