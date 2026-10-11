"""The panel's residual and its matched placebos (release E4, package D; league/xs/placebo.py): the pinned
pre-registration XSCREEN-1, section 3, held to the study's own conformance vectors and to its tests T2, T5 and T15.

SYNTHETIC DATA ONLY. The study's vectors (league/tests/fixtures/xs1_conformance.json, byte for byte) and their inputs
(xs1_conformance_inputs.npz) are seeded pseudo-random prices: no market row. The vectors' names 0..23 are the columns,
in that order, so "ascending asset id" is ascending column. `placebo.residual` and `placebo.run` read the bars and the
holdings log alone, so nothing here needs package C."""

from __future__ import annotations

import datetime as dt
import json
import math
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Sequence

import numpy as np

from league.equity import config as e1
from league.equity import screen as e1_screen
from league.equity.store import ordinal
from league.tests import test_xs_engine as fx
from league.xs import config, engine, placebo, results, store

FIXTURES = Path(__file__).resolve().parent / "fixtures"
HS = 0.0003
VECTORS = ("V1", "V2", "V3", "V4", "V5", "V6")
V_SPAN, H_SPAN = (0, 249), (250, 443)


def bars_of(opens: np.ndarray, closes: np.ndarray, *, first: int = 0, hs: float = HS) -> store.PanelBars:
    """A `PanelBars` whose total-return opens and closes are the arrays given (NaN: no valid price), with no REF
    column: the residual reads `adj` for prices and `raw` for which are valid."""
    n, m = opens.shape
    raw = np.full((n, m, 5), np.nan)
    raw[:, :, 0], raw[:, :, 3] = opens, closes
    raw[:, :, 1], raw[:, :, 2] = np.fmax(opens, closes), np.fmin(opens, closes)
    raw[:, :, 4] = 1.0
    days = np.array([ordinal(d) for d in fx.weekdays(dt.date(2031, 1, 6), n)], dtype=np.int32)
    return store.PanelBars(days=days, early=np.zeros(n, dtype=bool), first=first, raw=raw, adj=raw[:, :, :4].copy(),
                           elig0=np.ones((n, m), dtype=bool), ref=0, ids=np.arange(m, dtype=np.int32),
                           exit=np.zeros(m, dtype=np.int8), hs=np.full((m, 2), hs),
                           sector_perm=np.arange(11, dtype=np.int8), dither_key=b"fixture", window="look",
                           data_version="fixture")


def lot(lid: int, col: int, weight: float, decided: int, *, at: str = "open", exit: int | None = None,
        exit_at: str | None = "open", cell: int = 0, members: Sequence[int] = (), reason: str = "program",
        entry: int | None = None, hs: float = HS) -> dict[str, Any]:
    return {"lid": lid, "col": col, "weight": weight, "decided": decided,
            "entry": decided + 1 if entry is None else entry, "entry_at": at, "exit": exit,
            "exit_at": exit_at if exit is not None else None, "reason": reason if exit is not None else "open",
            "hs_open": hs, "hs_close": hs, "cell": cell, "members": np.array(sorted(members), dtype=np.int32)}


def log_of(lots: Sequence[dict[str, Any]], eligible: np.ndarray) -> engine.Log:
    """A holdings log by hand: the lots, and U(t) at every close (`eligible`: bool (n, m))."""
    log = engine.Log()
    log.lots.extend(lots)
    for t in range(eligible.shape[0]):
        log.decisions.append({"t": t, "called": True,
                              "derived": SimpleNamespace(elig=np.asarray(eligible[t], dtype=bool), rung="R0")})
    return log


class Vectors:
    """The study's vectors and their inputs, loaded once."""

    _loaded: "Vectors | None" = None

    def __init__(self) -> None:
        self.vectors = json.loads((FIXTURES / "xs1_conformance.json").read_text(encoding="utf-8"))["vectors"]
        with np.load(FIXTURES / "xs1_conformance_inputs.npz") as data:
            self.inputs = {name: data[name] for name in data.files}
        self.manifest = json.loads(bytes(self.inputs["manifest"]).decode("utf-8"))

    @classmethod
    def load(cls) -> "Vectors":
        if cls._loaded is None:
            cls._loaded = cls()
        return cls._loaded

    def vector(self, tag: str) -> dict[str, Any]:
        return self.vectors[self.manifest["vectors"][tag]["vector"]]

    def world(self, tag: str, name: str) -> np.ndarray:
        return self.inputs[f"{self.manifest['vectors'][tag]['world']}/{name}"]

    def case(self, tag: str) -> tuple[store.PanelBars, engine.Log]:
        """The vector's prices as bars and its holdings log as the engine would have written it."""
        get = lambda name: self.inputs[f"{tag}/{name}"]                     # noqa: E731
        start, members = get("member_start"), get("member")
        lots = []
        for i in range(len(get("lot_name"))):
            q = int(get("lot_q")[i])
            lots.append(lot(i + 1, int(get("lot_name")[i]), float(get("lot_weight")[i]), int(get("lot_d")[i]),
                            entry=int(get("lot_e")[i]), at=("open", "close")[int(get("lot_ea")[i])],
                            exit=None if q < 0 else q,
                            exit_at=None if q < 0 else ("open", "close")[int(get("lot_qa")[i])],
                            cell=int(get("lot_cell")[i]), members=members[start[i]:start[i + 1]].tolist()))
        return bars_of(self.world(tag, "O"), self.world(tag, "C")), log_of(lots, self.world(tag, "U"))


class TheStudyVectors(unittest.TestCase):
    """XSCREEN-1's conformance vectors: league/xs/placebo.py and the study's plain reference were written apart and
    agree on every integer, on every series to 1e-12 and on every placebo t to 1e-9."""

    @classmethod
    def setUpClass(cls):
        cls.data = Vectors.load()
        cls.cases = {tag: cls.data.case(tag) for tag in VECTORS}
        cls.series = {tag: placebo.residual(*cls.cases[tag]) for tag in VECTORS}

    def test_the_daily_series_r_b_x_x15_s_f_w_and_u_to_1e_12(self):
        for tag in VECTORS:
            series = self.series[tag]
            for mine, theirs in (("r", "r"), ("bench", "B"), ("x", "x"), ("x15", "x15"), ("s", "s"), ("f", "f"),
                                 ("w", "w"), ("u", "u")):
                with self.subTest(vector=tag, series=mine):
                    want = self.data.inputs[f"{tag}/{theirs}"]
                    self.assertEqual(series[mine].shape, want.shape)
                    self.assertLessEqual(float(np.max(np.abs(series[mine] - want))), 1e-12)
            self.assertEqual(len(series["days"]), 444)

    def test_the_integers_exits_and_invested_exactly(self):
        for tag in VECTORS:
            with self.subTest(vector=tag):
                series = self.series[tag]
                self.assertEqual(series["exits"].tolist(), self.data.inputs[f"{tag}/exits"].tolist())
                self.assertEqual(series["invested"].tolist(), self.data.inputs[f"{tag}/invested"].tolist())
                want = self.data.vector(tag)["series"]
                self.assertEqual((int(series["exits"][:250].sum()), int(series["invested"][:250].sum())),
                                 (want["RT_V"], want["ID_V"]))
                self.assertEqual((int(series["exits"][250:].sum()), int(series["invested"][250:].sum())),
                                 (want["exits_H"], want["invested_H"]))

    def test_the_looks_sums_are_the_vectors_own(self):
        for tag in VECTORS:
            with self.subTest(vector=tag):
                series, want = self.series[tag], self.data.vector(tag)["series"]
                for mine, key, part in (("x", "sum_V_x", slice(0, 250)), ("x", "sum_H_x", slice(250, 444)),
                                        ("x15", "sum_H_x15", slice(250, 444)), ("w", "sum_H_w", slice(250, 444)),
                                        ("s", "sum_H_s", slice(250, 444)), ("f", "sum_H_f", slice(250, 444)),
                                        ("bench", "sum_H_B", slice(250, 444))):
                    self.assertAlmostEqual(math.fsum(series[mine][part].tolist()), want[key], delta=1e-12)
                row = self.data.manifest["vectors"][tag]
                self.assertAlmostEqual(math.fsum(series["u"][:250].tolist()), row["sum_V_u"], delta=1e-12)
                self.assertAlmostEqual(math.fsum(series["u"][250:].tolist()), row["sum_H_u"], delta=1e-12)

    def test_x_is_r_less_b_and_the_stress_residual_is_x_less_half_the_spread_and_the_fees(self):
        for tag in VECTORS:
            series = self.series[tag]
            self.assertTrue(np.array_equal(series["x"], series["r"] - series["bench"]))
            self.assertTrue(np.array_equal(series["x15"], series["x"] - config.STRESS_SPREAD * series["s"]
                                           - config.STRESS_FEES * series["f"]))
            self.assertTrue(np.allclose(series["g"], series["x"] + series["c"], atol=0, rtol=0))
            self.assertTrue((series["c"] >= -1e-15).all(), "a cost is never a gain")
            self.assertTrue(np.allclose(series["c"], series["s"] + series["f"], atol=1e-15))

    def test_the_exit_law_each_members_leaving_session_is_the_studys(self):
        """A member leaves at the open after the first close past the lot's decision at which it is out of U."""
        for tag in VECTORS:
            with self.subTest(vector=tag):
                bars, log = self.cases[tag]
                tables = placebo._Tables(bars, log)
                leaving = self.data.inputs[f"{tag}/member_leave"]
                start = self.data.inputs[f"{tag}/member_start"]
                counted = 0
                for i, row in enumerate(log.lots):
                    members = row["members"]
                    out = tables.next_out[row["decided"] + 1, members]
                    mine = np.where(out < tables.n, out + 1, -1)
                    theirs = leaving[start[i]:start[i + 1]].astype(np.int64)
                    theirs = np.where(theirs > tables.n - 1, -1, theirs)      # a leave past the slice is none in it
                    self.assertEqual(np.where(mine > tables.n - 1, -1, mine).tolist(), theirs.tolist(), row["lid"])
                    last = tables.n - 1 if row["exit"] is None else row["exit"]
                    counted += int(np.sum((mine >= 0) & (mine <= last)))
                self.assertEqual(counted, self.data.vector(tag)["lots"]["members_leaving"])

    def test_the_counterparts_of_the_first_and_the_last_draw_and_their_sum_over_all_draws(self):
        for tag in VECTORS:
            with self.subTest(vector=tag):
                bars, log = self.cases[tag]
                tables = placebo._Tables(bars, log)
                lots = placebo._rows(tables, log, 1.0)
                seed = int(self.data.manifest["vectors"][tag]["placebo_seed"])
                positions, reused = placebo._draw(lots, placebo.DRAWS, seed, tables.m)
                want = self.data.vector(tag)["placebos"]
                self.assertEqual([int(p[0]) for p in positions], want["counterpart_position_draw_0"])
                self.assertEqual([int(p[998]) for p in positions], want["counterpart_position_draw_998"])
                self.assertEqual(sum(int(p.sum()) for p in positions), want["position_sum_all_draws"])
                self.assertEqual(reused, 0, "the vectors' cells are never exhausted")

    def test_the_placebo_ts_on_the_holdout_to_1e_9_and_each_looks_count(self):
        for tag in VECTORS:
            with self.subTest(vector=tag):
                bars, log = self.cases[tag]
                seed = int(self.data.manifest["vectors"][tag]["placebo_seed"])
                block = placebo.run(bars, log, n=placebo.DRAWS, seed=seed, spans={"V": V_SPAN, "H": H_SPAN})
                self.assertEqual((block["n"], block["rung"], block["seed"], block["lots"]),
                                 (999, "R0", seed, len(log.lots)))
                self.assertEqual((block["spans"]["V"]["days"], block["spans"]["H"]["days"]), (250, 194))
                mine = np.array([np.nan if t is None else t for t in block["spans"]["H"]["t"]])
                theirs = self.data.inputs[f"{tag}/placebo_t_H"]
                self.assertTrue(np.array_equal(np.isnan(mine), np.isnan(theirs)))
                self.assertLessEqual(float(np.nanmax(np.abs(mine - theirs))), 1e-9)
                look = self.data.vector(tag)["look"]
                t_h = results.t_stat(self.series[tag]["x"][250:])
                self.assertEqual(block["spans"]["H"]["t_x"], t_h)
                if look.get("look_spent"):
                    self.assertAlmostEqual(t_h, look["t_H"], delta=1e-12)
                    count = placebo.count_above(t_h, block["spans"]["H"]["t"])
                    self.assertEqual(count, look["placebo_count"])
                    self.assertEqual(block["spans"]["H"]["count"], look["placebo_count"])
                    self.assertEqual(round(placebo.p_value(t_h, block["spans"]["H"]["t"]) * 1000),
                                     look["p_plac_thousandths"])
                # each draw's sum and sum of squares are that draw's own sessions'
                row = block["spans"]["H"]
                self.assertEqual((len(row["sum"]), len(row["sumsq"])), (999, 999))
                self.assertTrue(all(q >= 0 for q in row["sumsq"]))

    def test_the_seed_of_the_vectors_is_the_looks_seed_of_their_stand_in_shas(self):
        for tag in VECTORS:
            inputs = self.data.vector(tag)["inputs"]
            self.assertEqual(str(placebo.look_seed(inputs["receipt_sha256"], inputs["program_code_sha256"])),
                             inputs["placebo_seed"])

    def test_the_hand_vector_h(self):
        """The pre-registration's 3.6: one lot of weight 0.2 on a, bought at the open of e, sold at the open of e + 2;
        its cell is {a, b, c}; hs 3 bp; E0 1,000; the fee is $0.02."""
        vector = self.data.vectors["H"]
        opens = np.full((5, 3), np.nan)
        closes = np.full((5, 3), np.nan)
        for col, name in enumerate("abc"):
            o, c = vector["inputs"]["open"][name], vector["inputs"]["close"][name]
            opens[1, col], opens[3, col] = o[0], o[2]
            closes[1, col], closes[2, col] = c[0], c[1]
        closes[0] = (100, 50, 20)
        opens[2], closes[3] = (101.5, 50.2, 19.9), (103.5, 50.6, 20.3)
        bars = bars_of(opens, closes, first=1, hs=vector["inputs"]["hs"])
        log = log_of([lot(1, 0, 0.2, 0, exit=3, cell=7, members=(0, 1, 2))], np.ones((5, 3), dtype=bool))
        series = placebo.residual(bars, log, capital=vector["inputs"]["E0"])
        for mine, theirs in (("r", "r"), ("bench", "B"), ("x", "x"), ("w", "w"), ("s", "s"), ("f", "f"),
                             ("x15", "x15")):
            self.assertLessEqual(float(np.max(np.abs(series[mine][:3] - np.array(vector[theirs])))), 1e-12, mine)
        self.assertEqual(series["exits"][:3].tolist(), vector["exits"])
        self.assertEqual(series["invested"][:3].tolist(), vector["invested"])
        self.assertAlmostEqual(float(series["f"][2]) * 1000, vector["fee_usd"], places=12)
        # the three counterparts: w x (its leg - the cell's mean), and their mean is zero every session
        tables = placebo._Tables(bars, log)
        rows = placebo._rows(tables, log, 1.0)
        _, filled = placebo._residual(tables, rows, 1000.0, config.VANISH_HAIRCUT, True)
        mean = filled[0].mean(0)
        for col, name in enumerate("abc"):
            got = 0.2 * (filled[0][col] - mean)
            self.assertLessEqual(float(np.max(np.abs(got - np.array(vector["placebo_residual_by_counterpart"][name])))),
                                 1e-12, name)
        self.assertLessEqual(float(np.max(np.abs((0.2 * (filled[0] - mean)).mean(0)))), 1e-15)
        # every draw is one of the three, and its series is that counterpart's
        block = placebo.run(bars, log, n=60, seed=3, capital=1000.0)
        positions, _ = placebo._draw(rows, 60, 3, 3)
        sums = {col: math.fsum((0.2 * (filled[0][col] - mean)).tolist()[:3]) for col in range(3)}
        self.assertEqual(set(positions[0].tolist()), {0, 1, 2})
        for m in range(60):
            self.assertAlmostEqual(block["spans"]["run"]["sum"][m], sums[int(positions[0][m])], delta=1e-15)

    def test_the_hand_vectors_close_fill_twin(self):
        """T2's twin: the same lot bought at the close of e and sold at the close of e + 2."""
        closes = np.array([[100, 50, 20], [101, 50, 19.8], [102.01, 50.5, 19.8], [103.5, 50.6, 20.3],
                           [104.0, 50.0, 20.0]])
        opens = closes * 0.999
        bars = bars_of(opens, closes, first=1)
        log = log_of([lot(1, 0, 0.2, 0, at="close", exit=3, exit_at="close", cell=7, members=(0, 1, 2))],
                     np.ones((5, 3), dtype=bool))
        series = placebo.residual(bars, log, capital=1000)
        legs = np.array([[0.0, 102.01 / 101 - 1, 103.5 / 102.01 - 1], [0.0, 50.5 / 50 - 1, 50.6 / 50.5 - 1],
                         [0.0, 0.0, 20.3 / 19.8 - 1]])
        fee = float(e1.sell_fees(200, 0.2 * 1000 / (101 * (1 + HS)))) / 1000
        r = [0.2 * (1 / (1 + HS) - 1), 0.2 * legs[0, 1], 0.2 * (103.5 * (1 - HS) / 102.01 - 1) - fee]
        bench = (0.2 * legs.mean(0)).tolist()
        self.assertLessEqual(float(np.max(np.abs(series["r"][:3] - np.array(r)))), 1e-15)
        self.assertLessEqual(float(np.max(np.abs(series["bench"][:3] - np.array(bench)))), 1e-15)
        self.assertEqual(series["w"][:3].tolist(), [0.0, 0.2, 0.2])
        self.assertEqual(series["exits"][:3].tolist(), [0, 0, 1])
        self.assertEqual(series["invested"][:3].tolist(), [True, True, True])
        self.assertAlmostEqual(float(series["s"][0]), 0.2 * (1 - 1 / (1 + HS)), places=15)
        self.assertAlmostEqual(float(series["s"][2]), 0.2 * HS * 103.5 / 102.01, places=15)
        self.assertEqual(series["x"][3], 0.0, "no leg after the exit")


class TheAccounting(unittest.TestCase):
    """T2 and T15: r is E1's constant-weight accounting; an invalid own-name day is neutral; u is the residual with
    ONE cell."""

    @classmethod
    def setUpClass(cls):
        cls.data = Vectors.load()

    def test_r_w_exits_and_invested_are_e1s_series_on_the_same_lots(self):
        case = fx.EngineCase("run_log")
        fx.Core.install(case)
        try:
            panel = fx.panel(sessions=90)
            _, log = case.run_log(fx.Program(fx.keyed(5), max_hold_sessions=9), panel)
        finally:
            case.doCleanups()
        self.assertGreater(len(log.lots), 30)
        self.assertTrue(any(row["reason"] == "max_hold" for row in log.lots))
        symbols = {col: f"C{col}" for col in range(panel.raw.shape[1])}
        e1_bars = SimpleNamespace(days=panel.days, first=panel.first,
                                  adj={symbols[col]: panel.adj[:, col] for col in symbols})
        rows = [{"lid": row["lid"], "symbol": symbols[row["col"]], "weight": row["weight"],
                 "entry_day": int(panel.days[row["entry"]]), "entry_at": row["entry_at"],
                 "exit_day": None if row["exit"] is None else int(panel.days[row["exit"]]),
                 "exit_at": row["exit_at"], "hs": row["hs_open"]} for row in log.lots]
        theirs = e1_screen.series(rows, e1_bars, universe=[symbols[fx.REF]], capital=1000)
        mine = placebo.residual(panel, log)
        self.assertLessEqual(float(np.max(np.abs(mine["r"] - theirs.r))), 1e-12)
        self.assertLessEqual(float(np.max(np.abs(mine["w"] - theirs.w))), 1e-12)
        self.assertEqual(mine["exits"].tolist(), theirs.exits.tolist())
        self.assertEqual(mine["invested"].tolist(), theirs.invested.tolist())
        self.assertEqual(mine["days"].tolist(), theirs.days.tolist())

    def test_an_invalid_leg_of_the_lots_own_name_is_neutral_and_pays_no_cost(self):
        rng = np.random.default_rng(11)
        closes = 50.0 * np.exp(np.cumsum(rng.normal(0, 0.01, (12, 6)), axis=0))
        opens = closes * (1 + rng.normal(0, 0.002, (12, 6)))
        closes[5, 0] = np.nan                               # the lot's own name has no close on session 5
        members = (0, 1, 2, 3)
        log = log_of([lot(1, 0, 0.2, 1, exit=9, cell=3, members=members)], np.ones((12, 6), dtype=bool))
        series = placebo.residual(bars_of(opens, closes), log)
        # sessions 5 and 6 read the missing close: the lot earns its cell's mean there, so x is 0 and no cost is booked
        for t in (5, 6):
            self.assertEqual(series["x"][t], 0.0)
            self.assertEqual((series["s"][t], series["f"][t], series["c"][t]), (0.0, 0.0, 0.0))
            self.assertNotEqual(series["bench"][t], 0.0)
            self.assertEqual(series["r"][t], series["bench"][t])
            self.assertEqual(series["w"][t], 0.2, "its exposure is still counted")
        self.assertNotEqual(series["x"][4], 0.0)
        # and the cell's mean on those sessions is over the members with a valid leg: the lot's own name is left out
        with np.errstate(invalid="ignore"):
            mean = np.mean(closes[5, 1:4] / closes[4, 1:4] - 1.0)
        self.assertAlmostEqual(float(series["bench"][5]), 0.2 * float(mean), places=15)

    def test_an_exit_on_an_invalid_price_is_neutral_and_still_an_exit(self):
        rng = np.random.default_rng(12)
        closes = 50.0 * np.exp(np.cumsum(rng.normal(0, 0.01, (10, 5)), axis=0))
        opens = closes * 1.001
        closes[5, 0] = np.nan                               # the close before the open exit
        log = log_of([lot(1, 0, 0.2, 1, exit=6, cell=3, members=(0, 1, 2))], np.ones((10, 5), dtype=bool))
        series = placebo.residual(bars_of(opens, closes), log)
        self.assertEqual((series["x"][6], series["f"][6], series["s"][6]), (0.0, 0.0, 0.0))
        self.assertEqual((int(series["exits"][6]), bool(series["invested"][6]), float(series["w"][6])),
                         (1, False, 0.1))

    def test_u_is_the_residual_with_one_cell_every_name_of_u_that_passes_entry_validity(self):
        for tag in ("V1", "V2"):
            bars, log = self.data.case(tag)
            eligible, entry_ok = self.data.world(tag, "U"), self.data.world(tag, "entry_ok")
            one = engine.Log()
            for row in log.lots:
                members = [j for j in range(24) if eligible[row["decided"], j] and entry_ok[row["entry"], j]]
                one.lots.append({**row, "cell": config.UNIVERSE_CELL, "members": np.array(members, dtype=np.int32)})
            one.decisions.extend(log.decisions)
            whole = placebo.residual(bars, one)
            series = placebo.residual(bars, log)
            self.assertLessEqual(float(np.max(np.abs(series["u"] - whole["x"]))), 1e-12)
            self.assertTrue(np.array_equal(whole["u"], whole["x"]), "with one cell the residual IS the universe excess")
            self.assertTrue(np.array_equal(series["w"], whole["w"]))
            self.assertFalse(np.array_equal(series["u"], series["x"]))
            # r itself differs on the sessions a lot's own leg is invalid (it carries its cell's mean there)
            self.assertEqual(int(np.sum(series["r"] != whole["r"])),
                             self.data.manifest["vectors"][tag]["sessions_r_differs_under_one_cell"])

    def test_two_bands_of_one_rule_correlate_in_u_and_not_in_x(self):
        """T15: on a panel with a strong common factor inside a sector, two rank bands of one rule share their sector
        tilt (u keeps it) and nothing else (x removes it); the correlation is E1's `same_lineage`."""
        rng = np.random.default_rng(21)
        n, m = 260, 40
        sector = np.arange(m) % 2
        factor = rng.normal(0.0, 0.012, (n, 2))
        moves = factor[:, sector] + rng.normal(0.0, 0.006, (n, m))
        closes = 50.0 * np.exp(np.cumsum(np.log1p(moves), axis=0))
        opens = np.vstack([closes[:1], closes[:-1]])
        bars = bars_of(opens, closes)
        cell_members = {s: [j for j in range(m) if sector[j] == s] for s in (0, 1)}

        def band(offset: int) -> engine.Log:
            lots, lid = [], 1
            for d in range(0, n - 6, 5):
                for rank in range(5):
                    col = cell_members[0][(offset + rank) % 20]      # always sector 0: the rule's tilt
                    lots.append(lot(lid, col, 0.2, d, exit=d + 6, cell=100, members=cell_members[0]))
                    lid += 1
            return log_of(lots, np.ones((n, m), dtype=bool))

        first, second = placebo.residual(bars, band(0)), placebo.residual(bars, band(10))
        in_u = float(np.corrcoef(first["u"], second["u"])[0, 1])
        in_x = float(np.corrcoef(first["x"], second["x"])[0, 1])
        self.assertGreater(in_u, e1_screen.SAME_LINEAGE_CORR)
        self.assertLess(in_x, e1_screen.SAME_LINEAGE_CORR)
        self.assertTrue(e1_screen.same_lineage(first["u"], second["u"]))
        self.assertFalse(e1_screen.same_lineage(first["x"], second["x"]))

    def test_the_stress_residual_at_one_and_a_half_times_the_spread(self):
        """x15 at k 1.0 charges what a run at k 1.5 charges in spread (to first order), and each sell fee twice."""
        bars, log = self.data.case("V1")
        base = placebo.residual(bars, log)
        wide = placebo.residual(bars, log, k=1.5)
        spread_15 = math.fsum(wide["s"].tolist())
        self.assertAlmostEqual(spread_15, 1.5 * math.fsum(base["s"].tolist()), delta=1e-5)
        want = math.fsum(wide["x"].tolist()) - math.fsum(base["f"].tolist())
        self.assertAlmostEqual(math.fsum(base["x15"].tolist()), want, delta=1e-5)

    def test_it_fails_closed_on_a_log_it_cannot_read(self):
        bars, log = self.data.case("V2")
        good = log.lots[0]
        for change, words in (({"col": 24}, "column"), ({"weight": float("nan")}, "weight"), ({"weight": 0.0}, "weight"),
                              ({"entry": good["decided"]}, "sessions"), ({"exit": good["entry"], "exit_at": "open"},
                                                                         "entry session"),
                              ({"exit": 444, "exit_at": "open"}, "exit session"), ({"entry_at": "noon"}, "entry at"),
                              ({"members": np.array([1, 0])}, "ascending"),
                              ({"members": np.array([c for c in good["members"] if c != good["col"]])}, "own name"),
                              ({"hs_open": -0.1}, "half-spread"), ({"decided": None}, "malformed")):
            bad = engine.Log()
            bad.lots.append({**good, **change})
            bad.decisions.extend(log.decisions)
            with self.subTest(change=change), self.assertRaises(ValueError) as caught:
                placebo.residual(bars, bad)
            self.assertIn(words, str(caught.exception))
        other = engine.Log()
        other.lots.extend(log.lots)
        other.decisions.append({"t": 0, "called": True, "derived": SimpleNamespace(
            elig=np.ones(24, dtype=bool), rung="R1")})
        with self.assertRaises(ValueError) as caught:
            placebo.residual(bars, other)
        self.assertIn("rung", str(caught.exception))
        for bad in ({"rung": "R9"}, {"haircut": 1.5}, {"k": -1.0}, {"capital": 0}):
            with self.assertRaises(ValueError):
                placebo.residual(bars, log, **bad)
        with self.assertRaises(ValueError):
            placebo.run(bars, log, n=0, seed=1)
        with self.assertRaises(ValueError):
            placebo.run(bars, log, n=5, seed=1, spans={"H": (250, 444)})

    def test_what_the_bars_say_validity_entry_validity_and_the_vanish_sessions(self):
        bars = fx.panel(sessions=12, names=4, first=2)
        raw, adj = bars.raw.copy(), bars.adj.copy()
        col = fx.REF
        raw[3, col, 4] = 0.0                                  # the vendor's flat bar of a halted name: no valid bar
        raw[5, col + 1], adj[5, col + 1] = np.nan, np.nan       # no bar
        adj[7, col + 2, 0] = np.nan                           # an open with no adjusted price
        raw[8:11, col + 3], adj[8:11, col + 3] = np.nan, np.nan  # three sessions dark
        changed = fx.changed(bars, raw=raw, adj=adj)
        open_ok, close_ok = placebo.validity(changed)
        self.assertFalse(open_ok[3, col] or close_ok[3, col])
        self.assertFalse(open_ok[5, col + 1] or close_ok[5, col + 1])
        self.assertEqual((bool(open_ok[7, col + 2]), bool(close_ok[7, col + 2])), (False, True))
        opens, closes = placebo.prices(changed)
        self.assertTrue(np.isnan(opens[3, col]) and np.isnan(closes[5, col + 1]) and np.isnan(opens[7, col + 2]))
        self.assertEqual(float(closes[7, col + 2]), float(adj[7, col + 2, 3]))
        ok = placebo.entry_validity(open_ok, close_ok)
        self.assertFalse(ok[2, col], "no valid close the session after")
        self.assertFalse(ok[3, col])
        self.assertTrue(ok[4, col])
        self.assertFalse(ok[7, col + 2], "no valid open at the fill")
        self.assertTrue(ok[11].all(), "the last session reads no session after it")
        vanish = placebo.vanish_sessions(close_ok)
        self.assertEqual(np.argwhere(vanish).tolist(), [[10, col + 3]])
        self.assertFalse(placebo.vanish_sessions(close_ok, sessions=4).any())
        self.assertEqual(np.argwhere(placebo.vanish_sessions(close_ok, sessions=1)).tolist(),
                         [[3, col], [5, col + 1], [8, col + 3]])


class ThePlaceboLaw(unittest.TestCase):
    """The pre-registration's 3.5 and its test T5."""

    @classmethod
    def setUpClass(cls):
        cls.data = Vectors.load()

    def world(self, n: int = 40, m: int = 12, seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
        rng = np.random.default_rng([31, seed])
        closes = 50.0 * np.exp(np.cumsum(rng.normal(0, 0.01, (n, m)), axis=0))
        return closes * (1 + rng.normal(0, 0.002, (n, m))), closes

    def test_counterparts_lie_in_the_lots_cell_and_are_distinct_within_a_draw(self):
        bars, log = self.data.case("V4")
        tables = placebo._Tables(bars, log)
        lots = placebo._rows(tables, log, 1.0)
        positions, _ = placebo._draw(lots, 200, 77, tables.m)
        for row, took in zip(lots, positions):
            self.assertTrue(((took >= 0) & (took < len(row.members))).all())
        # at one decision and cell, a draw's counterparts are distinct names
        groups: dict[tuple[int, int], list[int]] = {}
        for i, row in enumerate(lots):
            groups.setdefault((row.decided, row.cell), []).append(i)
        self.assertTrue(any(len(g) > 1 for g in groups.values()))
        for group in groups.values():
            names = np.stack([lots[i].members[positions[i]] for i in group])
            for draw in range(200):
                self.assertEqual(len(set(names[:, draw].tolist())), len(group))
        # and across decisions a draw never holds one name for two lots at once (no cell is exhausted here)
        for draw in (0, 57, 199):
            held: dict[int, int] = {}
            for i, row in sorted(enumerate(lots), key=lambda item: item[1].decided):
                name = int(row.members[positions[i][draw]])
                self.assertFalse(held.get(name, -1) > row.decided + 1, "a held member is not drawn again")
                held[name] = max(held.get(name, -1), 10 ** 9 if row.exit is None else row.exit)

    def test_a_held_member_is_reused_only_when_the_cell_has_no_free_member(self):
        opens, closes = self.world()
        eligible = np.ones((40, 12), dtype=bool)
        cell = (0, 1, 2)
        lots = [lot(1, 0, 0.2, 0, exit=30, cell=5, members=cell), lot(2, 1, 0.2, 0, exit=30, cell=5, members=cell),
                lot(3, 2, 0.2, 5, exit=30, cell=5, members=cell),      # the third member is still free
                lot(4, 0, 0.1, 10, exit=30, cell=5, members=cell)]      # now every member is held: one is reused
        log = log_of(lots, eligible)
        bars = bars_of(opens, closes)
        tables = placebo._Tables(bars, log)
        rows = placebo._rows(tables, log, 1.0)
        positions, reused = placebo._draw(rows, 500, 5, tables.m)
        self.assertEqual(reused, 500, "only the fourth lot's counterpart is a member the draw already holds")
        for draw in range(500):
            self.assertEqual({int(positions[i][draw]) for i in range(3)}, {0, 1, 2})
        self.assertEqual(placebo.run(bars, log, n=500, seed=5)["reused"], 500)

    def test_the_counterpart_of_a_lot_that_exits_at_the_next_fill_is_released(self):
        opens, closes = self.world()
        eligible = np.ones((40, 12), dtype=bool)
        cell = (0, 1)
        # the first two lots exit at the fill of the second decision (session 6): their names are free again at it
        lots = [lot(1, 0, 0.2, 0, exit=6, cell=5, members=cell), lot(2, 1, 0.2, 0, exit=6, cell=5, members=cell),
                lot(3, 0, 0.2, 5, exit=20, cell=5, members=cell), lot(4, 1, 0.2, 5, exit=20, cell=5, members=cell)]
        tables = placebo._Tables(bars_of(opens, closes), log_of(lots, eligible))
        _, reused = placebo._draw(placebo._rows(tables, log_of(lots, eligible), 1.0), 300, 9, tables.m)
        self.assertEqual(reused, 0)
        lots[0]["exit"], lots[1]["exit"] = 7, 7                 # one session later they are still held at that fill
        _, reused = placebo._draw(placebo._rows(tables, log_of(lots, eligible), 1.0), 300, 9, tables.m)
        self.assertEqual(reused, 600)

    def test_the_draw_is_uniform_without_replacement(self):
        """An enumerable case: 2 lots of one decision in a cell of 4. The 12 ordered pairs are equally likely
        (chi-square, 11 degrees of freedom: p > 0.001 is a statistic under 31.26)."""
        opens, closes = self.world()
        cell = (2, 5, 7, 9)
        lots = [lot(1, 5, 0.2, 0, exit=10, cell=5, members=cell), lot(2, 9, 0.15, 0, exit=10, cell=5, members=cell)]
        log = log_of(lots, np.ones((40, 12), dtype=bool))
        tables = placebo._Tables(bars_of(opens, closes), log)
        draws = 24_000
        positions, _ = placebo._draw(placebo._rows(tables, log, 1.0), draws, 20261011, tables.m)
        counts: dict[tuple[int, int], int] = {}
        for a, b in zip(positions[0].tolist(), positions[1].tolist()):
            counts[(a, b)] = counts.get((a, b), 0) + 1
        self.assertEqual(len(counts), 12)
        self.assertTrue(all(a != b for a, b in counts))
        expected = draws / 12
        chi = sum((c - expected) ** 2 / expected for c in counts.values())
        self.assertLess(chi, 31.26)
        # the heavier lot takes the smallest key: the order within a cell is (weight descending, column ascending)
        swapped = [dict(lots[1], lid=1), dict(lots[0], lid=2)]
        again, _ = placebo._draw(placebo._rows(tables, log_of(swapped, np.ones((40, 12), dtype=bool)), 1.0), draws,
                                 20261011, tables.m)
        self.assertTrue(np.array_equal(again[1], positions[0]) and np.array_equal(again[0], positions[1]))

    def test_the_seed_reproduces_exactly_and_another_seed_is_another_draw(self):
        bars, log = self.data.case("V2")
        one = placebo.run(bars, log, n=50, seed=123, spans={"H": H_SPAN})
        two = placebo.run(bars, log, n=50, seed=123, spans={"H": H_SPAN})
        self.assertEqual(one, two)
        other = placebo.run(bars, log, n=50, seed=124, spans={"H": H_SPAN})
        self.assertNotEqual(other["spans"]["H"]["t"], one["spans"]["H"]["t"])
        self.assertAlmostEqual(one["identity_share"], 1 / 6, delta=0.03)       # the vectors' cells hold 6 names

    def test_the_mean_of_many_draws_residual_tends_to_zero(self):
        bars, log = self.data.case("V2")
        block = placebo.run(bars, log, n=600, seed=5)
        sums = np.array(block["spans"]["run"]["sum"])
        self.assertLess(abs(float(sums.mean())), 4 * float(sums.std()) / math.sqrt(600))
        self.assertGreater(float(sums.std()), 0.01)

    def test_the_exit_law_a_member_out_of_u_takes_the_open_exit_leg_and_is_gone(self):
        opens, closes = self.world(n=30, m=8, seed=4)
        eligible = np.ones((30, 8), dtype=bool)
        eligible[12:, 3] = False                                # member 3 is out of U from the close of session 12
        cell = (1, 3, 5, 6)
        log = log_of([lot(1, 1, 0.2, 5, exit=20, cell=5, members=cell)], eligible)
        bars = bars_of(opens, closes)
        tables = placebo._Tables(bars, log)
        row = placebo._rows(tables, log, 1.0)[0]
        legs = placebo._legs(tables, row, row.members, config.VANISH_HAIRCUT)
        k = lambda t: t - row.entry                             # noqa: E731
        self.assertAlmostEqual(float(legs[1, k(12)]), closes[12, 3] / closes[11, 3] - 1, places=15)
        self.assertAlmostEqual(float(legs[1, k(13)]), opens[13, 3] / closes[12, 3] - 1, places=15)   # sold at the open
        self.assertTrue(np.isnan(legs[1, k(14):]).all(), "gone from the session after")
        self.assertTrue(np.isfinite(np.delete(legs, 1, axis=0)).all())
        # the mean over the members of (leg - the cell's mean) is zero to 1e-12 every session, the leaver included
        _, filled = placebo._residual(tables, [row], 1000, config.VANISH_HAIRCUT, True)
        mean = np.nanmean(legs, axis=0)
        self.assertLessEqual(float(np.max(np.abs((filled[0] - mean[None, :]).mean(0)))), 1e-12)
        self.assertTrue(np.array_equal(filled[0][1, k(14):], mean[k(14):]), "as a counterpart it is the cell's mean")
        series = placebo.residual(bars, log)
        self.assertAlmostEqual(float(series["bench"][14]), 0.2 * float(np.mean(
            closes[14, [1, 5, 6]] / closes[13, [1, 5, 6]] - 1)), places=15)
        # a lot that is closed before the member leaves never sees it leave
        early = log_of([lot(1, 1, 0.2, 5, exit=12, cell=5, members=cell)], eligible)
        first = placebo._rows(placebo._Tables(bars, early), early, 1.0)[0]
        self.assertTrue(np.isfinite(placebo._legs(placebo._Tables(bars, early), first, first.members, 0.3)).all())

    def test_the_rank(self):
        ts = [0.5, None, float("nan"), 1.5, 2.0, -1.0]
        self.assertEqual(placebo.count_above(1.5, ts), 2)
        self.assertEqual(placebo.count_above(2.5, ts), 0)
        self.assertEqual(placebo.count_above(-5.0, ts), 4, "an undefined placebo t counts as not above")
        self.assertEqual(placebo.p_value(1.5, ts), 3 / 7)
        self.assertIsNone(placebo.count_above(None, ts))
        self.assertIsNone(placebo.p_value(float("nan"), ts))
        # the pre-registered bar in integers: 119 of 999 at or above passes 0.12, 120 does not
        for count, passes in ((119, True), (120, False)):
            draws = [1.0] * count + [0.0] * (placebo.DRAWS - count)
            self.assertEqual(placebo.count_above(0.5, draws), count)
            self.assertEqual((1 + count) * 100 <= 12 * (placebo.DRAWS + 1), passes)
            self.assertEqual(placebo.p_value(0.5, draws) <= 0.12, passes)

    def test_the_pooled_statistic_pairs_a_draw_of_one_run_with_the_same_draw_of_the_next(self):
        first = self.data.case("V1")
        second = self.data.case("V4")
        blocks = [placebo.run(*first, n=30, seed=1), placebo.run(*second, n=30, seed=2)]
        pooled = placebo.stat(blocks)
        self.assertEqual(pooled.shape, (30,))
        for case, block, seed in ((first, blocks[0], 1), (second, blocks[1], 2)):
            alone = placebo.stat([block])
            mine = np.array([np.nan if t is None else t for t in block["spans"]["run"]["t"]])
            self.assertLessEqual(float(np.nanmax(np.abs(alone - mine))), 1e-9, "one block pooled is its own t")
        # against the draws' own concatenated series
        series = []
        for (bars, log), seed in ((first, 1), (second, 2)):
            tables = placebo._Tables(bars, log)
            rows = placebo._rows(tables, log, 1.0)
            z, filled = placebo._residual(tables, rows, 1000, config.VANISH_HAIRCUT, True)
            positions, _ = placebo._draw(rows, 30, seed, tables.m)
            total = np.zeros((tables.n, 30))
            for row, legs, took in zip(rows, filled, positions):
                total[row.entry:row.entry + legs.shape[1]] += row.weight * legs[took].T
            series.append(total - z["bench"][:, None])
        both = np.vstack(series)
        for m in range(30):
            self.assertAlmostEqual(float(pooled[m]), results.t_stat(both[:, m]), delta=1e-9)
        with self.assertRaises(ValueError):
            placebo.stat([blocks[0], placebo.run(*second, n=20, seed=2)])
        with self.assertRaises(ValueError):
            placebo.stat(blocks, span="H")
        with self.assertRaises(ValueError):
            placebo.stat([])


class TheDrawIsFixed(unittest.TestCase):
    """Seal X11: the draw's stream. `Generator.random` is one 53-bit double a 64-bit PCG64 output, in order, in every
    numpy; the law calls nothing else."""

    SEED = placebo.look_seed("0" * 64, "f" * 64)
    GOLDEN = (0.4822266860399391, 0.6349748613768404, 0.9039391597608823, 0.6748351319706711, 0.20881005640215677)

    def test_the_seeds(self):
        self.assertEqual(self.SEED, 25539167690346316859240858469936157132)
        self.assertEqual(self.SEED, int.from_bytes(__import__("hashlib").sha256(
            ("XS1|" + "0" * 64 + "|" + "f" * 64 + "|placebo").encode()).digest()[:16], "big"))
        train = placebo.train_seed("a" * 64, "train")
        self.assertNotEqual(train, placebo.train_seed("a" * 64, "validation"))
        self.assertNotEqual(train, placebo.train_seed("b" * 64, "train"))
        self.assertNotEqual(train, placebo.look_seed("train", "a" * 64))
        self.assertTrue(0 <= train < 2 ** 128)

    def test_five_golden_doubles_of_the_fixed_seed(self):
        rng = np.random.default_rng(self.SEED)
        self.assertEqual(tuple(rng.random((1, 5))[0].tolist()), self.GOLDEN)

    def test_a_golden_first_pick_for_each_of_the_first_three_decisions(self):
        """The study's own vector: the counterparts the first and the last draw give the lots of its first three
        decisions (and `TheStudyVectors` holds every lot's)."""
        data = Vectors.load()
        bars, log = data.case("V1")
        tables = placebo._Tables(bars, log)
        rows = placebo._rows(tables, log, 1.0)
        positions, _ = placebo._draw(rows, placebo.DRAWS, self.SEED, tables.m)
        decisions = sorted({row.decided for row in rows})[:3]
        want = data.vectors["V1 pass"]["placebos"]
        picked = 0
        for i, row in enumerate(rows):
            if row.decided in decisions:
                self.assertEqual(int(positions[i][0]), want["counterpart_position_draw_0"][i])
                self.assertEqual(int(positions[i][998]), want["counterpart_position_draw_998"][i])
                picked += 1
        self.assertGreaterEqual(picked, 3)

    def test_the_law_calls_random_once_a_decision_and_cell_and_nothing_else(self):
        data = Vectors.load()
        bars, log = data.case("V2")
        tables = placebo._Tables(bars, log)
        rows = placebo._rows(tables, log, 1.0)
        calls: list[tuple[int, int]] = []

        class Recorder:
            def __init__(self, seed: int):
                self.rng = np.random.Generator(np.random.PCG64(seed))

            def random(self, shape: tuple[int, int]) -> np.ndarray:
                calls.append(shape)
                return self.rng.random(shape)

            def __getattr__(self, name: str) -> Any:
                raise AssertionError(f"the law calls rng.{name}")

        real = np.random.default_rng
        np.random.default_rng = Recorder
        try:
            placebo._draw(rows, 40, 5, tables.m)
        finally:
            np.random.default_rng = real
        groups = {(row.decided, row.cell): len(row.members) for row in rows}
        self.assertEqual(calls, [(40, groups[key]) for key in sorted(groups)])


class ExactUnderExchangeability(unittest.TestCase):
    """Seal X11 and the pre-registration's T6, on synthetic panels with no predictability: programs whose new names
    ARE a uniform draw from their cells pass the placebo bar at the bar's own rate, and a planted edge is found."""

    DRAWS = 99
    BAR = 11                                  # (1 + 11) / 100 = 0.12
    SESSIONS, NAMES = 46, 12

    def program(self, index: int, plant: float = 0.0) -> tuple[store.PanelBars, engine.Log]:
        rng = np.random.default_rng([20261011, 6, index])
        n, m = self.SESSIONS, self.NAMES
        cells_ = {7: list(range(0, 6)), 8: list(range(6, 12))}
        lots, lid = [], 1
        for d in range(0, n - 7, 5):
            for cell, members in cells_.items():
                picks = rng.permutation(members)[:2]            # a uniform draw without replacement from the cell
                for weight, col in zip((0.2, 0.15), picks):
                    lots.append(lot(lid, int(col), weight, d, exit=d + 6, cell=cell, members=members))
                    lid += 1
        moves = rng.normal(0.0, 0.012, (n, m))
        for row in lots:
            moves[row["entry"]:row["exit"], row["col"]] += plant
        closes = 50.0 * np.exp(np.cumsum(np.log1p(moves), axis=0))
        opens = np.vstack([closes[:1], closes[:-1]]) * (1 + rng.normal(0, 0.002, (n, m)))
        return bars_of(opens, closes), log_of(lots, np.ones((n, m), dtype=bool))

    def test_two_thousand_null_programs_pass_at_the_bars_rate(self):
        programs, passed = 2000, 0
        for index in range(programs):
            bars, log = self.program(index)
            block = placebo.run(bars, log, n=self.DRAWS, seed=index, k=0.0)
            count = block["spans"]["run"]["count"]
            passed += count is not None and count <= self.BAR
        rate = passed / programs
        sigma = math.sqrt(0.12 * 0.88 / programs)
        self.assertLessEqual(rate, 0.12 + 3 * sigma, "never above the bar by more than sampling noise")
        self.assertGreaterEqual(rate, 0.12 - 4 * sigma - 0.01, "and exact, not merely conservative")

    def test_the_net_residual_passes_no_more_often_than_the_gross(self):
        gross = net = 0
        for index in range(400):
            bars, log = self.program(index)
            for k, into in ((0.0, "gross"), (1.0, "net")):
                count = placebo.run(bars, log, n=self.DRAWS, seed=index, k=k)["spans"]["run"]["count"]
                if count is not None and count <= self.BAR:
                    gross, net = gross + (into == "gross"), net + (into == "net")
        self.assertLessEqual(net, gross)

    def test_a_planted_edge_is_found(self):
        found = 0
        for index in range(60):
            bars, log = self.program(index, plant=0.006)
            count = placebo.run(bars, log, n=self.DRAWS, seed=index)["spans"]["run"]["count"]
            found += count is not None and count <= self.BAR
        self.assertGreaterEqual(found, 54)


if __name__ == "__main__":
    unittest.main()
