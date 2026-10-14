"""FWD1-R's rule (league/ops/fwd1_rule.py): the receipt's conformance vectors, the bar, the haircut, the placebo leg,
the clock and THE PIN that starts it (policy.json `elane.forward_screen` held to docs/benchmarks/forward_screen_fwd1.json).

Every input is synthetic (numpy `default_rng` streams the vectors file states); no market data, no real figure."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import unittest
from pathlib import Path

import numpy as np

from league.ops import fwd1_rule as R

REPO = Path(__file__).resolve().parents[2]
VECTORS = REPO / "league" / "tests" / "fixtures" / "forward_screen_fwd1_vectors.json"
RECEIPT = REPO / R.RECEIPT_PATH
POLICY = REPO / "league" / "swarm" / "policy.json"


def pool(span: int, n: int, seed: int = 20261014) -> tuple[np.ndarray, ...]:
    rng = np.random.default_rng([seed, 2026, span, n])
    on = rng.random(n) < 0.6
    w = np.where(on, 0.5, 0.0)
    r = np.where(on, rng.normal(0.0004, 0.006, n), 0.0)
    r15 = r - np.where(on & (rng.random(n) < 0.15), 1e-4, 0.0)
    b = rng.normal(0.0003, 0.01, n)
    return r, r15, w, b


def streaky(span: int, n: int, seed: int = 20261014) -> tuple[np.ndarray, ...]:
    rng = np.random.default_rng([seed, 2027, span, n])
    w = np.full(n, 0.5)
    r = rng.normal(0.0, 0.004, n) + 0.003 * np.sign(np.sin(np.arange(n) / 9.0))
    r15 = r - np.where(rng.random(n) < 0.2, 1e-4, 0.0)
    b = rng.normal(0.0003, 0.01, n)
    return r, r15, w, b


def pools_of(name: str, nd: int | None, nc: int) -> tuple:
    gen = streaky if name == "V5" else pool
    return (None if nd is None else gen(0, nd)), gen(1, nc)


def forward(n: int, mean: float, seed: int) -> tuple[np.ndarray, ...]:
    rng = np.random.default_rng([seed, 7, n])
    on = rng.random(n) < 0.7
    w = np.where(on, 0.5, 0.0)
    r = np.where(on, rng.normal(mean, 0.005, n), 0.0)
    sides = np.where(on & (rng.random(n) < 0.3), 0.5, 0.0)
    r15 = r - sides * 1e-4 * 0.5
    has_ll = on & (rng.random(n) < 0.5)
    r_ll = np.where(has_ll, r + rng.normal(-1e-5, 2e-5, n), np.nan)
    return r, r15, w, sides, r_ll


def rows_of(r, r15, w) -> list[dict]:
    return [{"day": f"d{i:03d}", "r": float(r[i]), "w": float(w[i]), "b": 0.0, "r15": float(r15[i])} for i in range(len(r))]


class TheVectors(unittest.TestCase):
    """The receipt's conformance vectors (written by the study's own code at the adopted bars): every integer exactly,
    every float to 1e-12."""

    @classmethod
    def setUpClass(cls):
        cls.v = json.loads(VECTORS.read_text())

    def test_the_vectors_are_the_receipts(self):
        self.assertEqual(self.v["receipt_sha256"], hashlib.sha256(RECEIPT.read_bytes()).hexdigest())

    def test_own_floors_and_drift_kept(self):
        for name, row in self.v["floors"].items():
            pd_, pc_ = pools_of(name, row["pools"]["D"], row["pools"]["C"])
            for kind in ("ETF", "PANEL"):
                cells = R.floor_cells(kind, pd_, pc_)
                for case, cap in R.OWN_CAP.items():
                    key = f"{kind}|cap{cap}"
                    if key not in row:
                        continue
                    want = row[key]
                    with self.subTest(vector=name, key=key):
                        got = R.own_floor_k([[p[:3] for p in c] for c in cells], cap)
                        self.assertEqual(got["k_own"], want["k_own"])
                        self.assertEqual(got["cells"], want["cells"])
                        self.assertEqual(len(cells), want["n_cells"])
                        if kind == "ETF" and want["k_own"] is not None:
                            self.assertEqual(R.c_used("ETF", "N", got["k_own"]), want["c_used"])
                            ku = R.k_used("ETF", "N", got["k_own"])
                            self.assertAlmostEqual(R.drift_kept(cells, ku), want["drift_kept_at_c_used"], delta=1e-12)

    def test_forward_statistics(self):
        for name, ent in self.v["forward"].items():
            r, r15, w, sides, r_ll = forward(ent["n"], ent["mean"], ent["seed"])
            rows = rows_of(r, r15, w)
            ll = {rows[i]["day"]: float(r_ll[i]) for i in range(len(rows)) if math.isfinite(r_ll[i])}
            for g_bp in (2, 3):
                for use_ll in (False, True):
                    want = ent[f"g{g_bp}|{'ll' if use_ll else 'r'}"]
                    x, x15 = R.series("ETF", rows, g_bp=g_bp, sides=[float(s) for s in sides],
                                      live_like=ll if use_ll else None)
                    for j, k in enumerate(R.PLAN):
                        with self.subTest(vector=name, g=g_bp, ll=use_ll, k=k):
                            got = R.checkpoint(x, x15, k)
                            if want["t"][j] is None:
                                self.assertIsNone(got["t"])
                            else:
                                self.assertAlmostEqual(got["t"], want["t"][j], delta=1e-12)
                            self.assertAlmostEqual(got["S"], want["S"][j], delta=1e-12)
                            self.assertAlmostEqual(got["S15"], want["S15"][j], delta=1e-12)
                    for key, c in (("ETF|N", 2.61), ("PANEL|N", 2.06), ("PANEL|XS1", 3.16)):
                        first = next((k for k in R.PLAN if R.legs_pass(R.checkpoint(x, x15, k), c)), None)
                        with self.subTest(vector=name, g=g_bp, ll=use_ll, bar=key):
                            self.assertEqual(first, want["first_pass"][key])

    def test_the_pipeline(self):
        for name, p in self.v["pipeline"].items():
            nd, nc = self.v["floors"][p["pools"]]["pools"]["D"], self.v["floors"][p["pools"]]["pools"]["C"]
            cells = R.floor_cells(p["type"], *pools_of(p["pools"], nd, nc))
            k_own = R.own_floor_k([[q[:3] for q in c] for c in cells], R.OWN_CAP[p["case"]])["k_own"]
            c = R.c_used(p["type"], p["case"], k_own)
            ent = self.v["forward"][p["forward"]]
            r, r15, w, sides, _ = forward(ent["n"], ent["mean"], ent["seed"])
            x, x15 = R.series("ETF", rows_of(r, r15, w), g_bp=int(p["g"][1]), sides=[float(s) for s in sides])
            first = None if c is None else next((k for k in R.PLAN if R.legs_pass(R.checkpoint(x, x15, k), c)), None)
            with self.subTest(pipeline=name):
                self.assertEqual(k_own, p["k_own"])
                self.assertEqual(c, p["c_used"])
                self.assertEqual(first, p["first_pass"])

    def test_the_grid(self):
        self.assertEqual([R.grid_index(t) for t in self.v["grid"]["probes"]], self.v["grid"]["index"])

    def test_the_registrys_expected_passes(self):
        rule = R.Rule(receipt_sha256="0" * 64, figures=json.loads(RECEIPT.read_text())["figures"])
        got = R.expected_passes(rule, [tuple(x) for x in self.v["expected"]["lineages"]])
        for key, want in self.v["expected"]["sum_by_type_case"].items():
            self.assertAlmostEqual(got[key], want, delta=1e-4)


class TheBar(unittest.TestCase):
    def test_a_tie_passes_and_just_below_fails(self):
        c = R.c_used("ETF", "N", 100)
        self.assertEqual(c, 2.61)
        self.assertTrue(R.legs_pass({"t": 2.61, "S": 1e-3, "S15": 1e-3}, c))
        self.assertFalse(R.legs_pass({"t": math.nextafter(2.61, 0.0), "S": 1e-3, "S15": 1e-3}, c))
        self.assertEqual(R.grid_index(2.61), 261)
        self.assertEqual(R.grid_index(math.nextafter(2.61, 0.0)), 260)

    def test_a_sum_at_zero_or_a_flat_series_fails(self):
        self.assertFalse(R.legs_pass({"t": 4.0, "S": 0.0, "S15": 1e-3}, 2.06))
        self.assertFalse(R.legs_pass({"t": 4.0, "S": 1e-3, "S15": 1e-12}, 2.06))
        self.assertIsNone(R.t_stat([0.001] * 10))                     # std 0: no t, no pass
        self.assertFalse(R.legs_pass({"t": None, "S": 1e-2, "S15": 1e-2}, 2.06))

    def test_the_own_floor_and_the_margin(self):
        self.assertEqual(R.c_used("PANEL", "N", 150), 2.06)          # the global bar binds
        self.assertEqual(R.c_used("PANEL", "N", 240), 2.45)          # own floor + 0.05
        self.assertEqual(R.c_used("PANEL", "XS1", 250), 3.16)
        self.assertEqual(R.c_used("PANEL", "XS1", 320), 3.25)
        self.assertIsNone(R.c_used("ETF", "N", 496))                 # 5.01: ineligible
        self.assertEqual(R.c_used("ETF", "N", 495), 5.0)
        self.assertIsNone(R.c_used("ETF", "N", None))

    def test_the_own_floor_by_brute_force(self):
        """A small pool: k_cell is the smallest grid k whose pass count holds the cap, counted window by window."""
        r, r15, w, _ = pool(3, 140)
        got = R.own_floor_k([[(r, r15, w)]], 0.12)
        iw = np.zeros(len(r))
        for s in range(len(r) - R.KMAX + 1):
            iw[s:s + R.KMAX] += 1
        kappa = math.fsum((iw * r).tolist()) / math.fsum((iw * w).tolist())
        best = []
        for s in range(len(r) - R.KMAX + 1):
            x0 = r[s:s + R.KMAX] - w[s:s + R.KMAX] * kappa
            s0 = x0 - (r[s:s + R.KMAX] - r15[s:s + R.KMAX])
            top = -1
            for k in R.PLAN:
                pt = R.checkpoint(list(x0), list(s0), k)
                if pt["t"] is not None and pt["S"] > R.ZERO and pt["S15"] > R.ZERO:
                    top = max(top, R.grid_index(pt["t"]))
            best.append(top)
        worlds = len(best)
        k_cell = next(k for k in range(R.K_MAX + 1) if sum(1 for b in best if b >= k) * 10000 <= 1200 * worlds)
        self.assertEqual(got["k_own"], k_cell)

    def test_ineligible_floors(self):
        self.assertEqual(R.own_floor_k([], 0.12)["why"], "no cell")
        z = np.zeros(100)
        self.assertIn("no exposure", R.own_floor_k([[(z, z, z)]], 0.12)["why"])
        bad = np.full(100, np.nan)
        self.assertIn("not finite", R.own_floor_k([[(bad, bad, np.ones(100))]], 0.12)["why"])


class TheHaircut(unittest.TestCase):
    def test_etf_raised_to_the_measured_gap(self):
        self.assertEqual(R.haircut_bp("ETF", []), 2)
        self.assertEqual(R.haircut_bp("ETF", [1.0, 2.5]), 2)
        self.assertEqual(R.haircut_bp("ETF", [2.0, 2.6]), 3)          # mean 2.3, rounded up
        self.assertEqual(R.haircut_bp("ETF", [-4.0, -1.0]), 2)        # a favourable gap never lowers it
        self.assertEqual(R.haircut_bp("ETF", [float("nan")]), 2)

    def test_panel_three_until_twenty_lots(self):
        self.assertEqual(R.haircut_bp("PANEL", [0.0] * 19), 3)
        self.assertEqual(R.haircut_bp("PANEL", [0.5] * 20), 2)
        self.assertEqual(R.haircut_bp("PANEL", [4.2] * 20), 5)

    def test_the_series(self):
        rows = [{"day": "a", "r": 0.01, "w": 0.5, "b": 0.004, "r15": 0.009}]
        x, x15 = R.series("PANEL", rows, g_bp=3, sides=[0.5])
        self.assertAlmostEqual(x[0], 0.01 - 0.5 * 0.004 - 0.00015, delta=1e-15)
        self.assertAlmostEqual(x15[0], 0.009 - 0.5 * 0.004 - 0.00015, delta=1e-15)
        x, x15 = R.series("ETF", rows, g_bp=2, sides=[0.5], live_like={"a": 0.0095})
        self.assertAlmostEqual(x[0], 0.0095 - 0.0001, delta=1e-15)
        self.assertAlmostEqual(x15[0], 0.009 - 0.0005 - 0.0001, delta=1e-15)
        with self.assertRaises(ValueError):
            R.series("ETF", [{"day": "a", "r": 0.0, "w": 0.0, "b": 0.0, "r15": None}], g_bp=2, sides=[0.0])


class ThePlaceboLeg(unittest.TestCase):
    def test_at_most_119_of_999(self):
        t = 2.5
        draws = [3.0] * 119 + [1.0] * 880
        self.assertEqual(R.placebo_count(t, draws), 119)
        self.assertTrue(R.placebo_holds(119, 999))
        self.assertFalse(R.placebo_holds(R.placebo_count(t, [2.5] * 120 + [None] * 879), 999))  # a tie is at or above
        self.assertEqual(R.placebo_count(t, [None, float("nan"), 2.4]), 0)
        self.assertFalse(R.placebo_holds(0, 998))                       # another law's draws judge nothing
        self.assertIsNone(R.placebo_count(None, draws))

    def test_the_seed(self):
        want = int.from_bytes(hashlib.sha256(b"FWD1|" + b"a" * 64 + b"|" + b"b" * 64 + b"|placebo").digest()[:16], "big")
        self.assertEqual(R.placebo_seed("a" * 64, "b" * 64), want)


class TheClock(unittest.TestCase):
    @staticmethod
    def at(text: str) -> float:
        return dt.datetime.fromisoformat(text).replace(tzinfo=dt.timezone.utc).timestamp()

    def test_the_session_after_the_first_close_after_the_pin(self):
        self.assertEqual(R.start_after(self.at("2026-10-15T14:00:00")), dt.date(2026, 10, 16))   # in Thursday's session
        self.assertEqual(R.start_after(self.at("2026-10-15T21:00:00")), dt.date(2026, 10, 19))   # after its close
        self.assertEqual(R.start_after(self.at("2026-10-17T15:00:00")), dt.date(2026, 10, 20))   # a Saturday
        from league.ops import forward_db

        for text in ("2026-10-15T14:00:00", "2026-10-15T21:00:00", "2026-10-17T15:00:00", "2026-11-26T15:00:00",
                     "2026-11-27T19:30:00", "2026-12-24T20:00:00"):      # a holiday, a half day's close, its evening
            t = self.at(text)
            self.assertEqual(R.start_after(t), forward_db.first_day(forward_db.first_close(t)), text)
        self.assertEqual(R.forward_start(dt.date(2026, 10, 13), dt.date(2026, 10, 16)), dt.date(2026, 10, 16))
        self.assertEqual(R.forward_start(dt.date(2026, 10, 20), dt.date(2026, 10, 16)), dt.date(2026, 10, 20))


class ThePin(unittest.TestCase):
    """CI's pin: policy.json `elane.forward_screen` is the receipt file's, value for value, and this code's."""

    @classmethod
    def setUpClass(cls):
        cls.policy = json.loads(POLICY.read_text())
        cls.receipt = json.loads(RECEIPT.read_text())
        cls.block = R.pin(cls.policy)

    def test_the_pin_loads(self):
        rule, why = R.load(self.block)
        self.assertIsNone(why)
        self.assertEqual(rule.receipt_sha256, hashlib.sha256(RECEIPT.read_bytes()).hexdigest())
        self.assertEqual(R.rule(self.policy)[0], rule)

    def test_every_figure_is_the_receipts(self):
        for key in ("plan", "c_G", "c_margin", "haircut_bp", "haircut_floor_bp", "panel_lots", "own_cap", "owner_wall",
                    "figures"):
            self.assertEqual(self.block[key], self.receipt[key], key)
        self.assertEqual(self.block["placebo"], {k: self.receipt["placebo"][k] for k in ("draws", "count_max")})
        self.assertEqual(self.receipt["screen"], R.SCREEN)
        self.assertEqual(self.receipt["version"], 2)

    def test_the_receipts_bars_are_the_adopted_ones(self):
        self.assertEqual(self.receipt["c_G"], {"ETF": {"N": 2.61}, "PANEL": {"N": 2.06, "XS1": 3.16}})
        self.assertEqual(self.receipt["own_cap"], {"N": 0.12, "XS1": 0.024})
        for key, fig in self.receipt["figures"].items():
            self.assertLessEqual(fig["fp_ub"], fig["budget"], key)
            self.assertLessEqual(fig["fp_point"], 0.8 * fig["budget"] + 1e-12, key)

    def test_the_loader_refuses(self):
        good = dict(self.block)
        for change in ({"plan": [20, 60, 120, 250]}, {"c_G": {"ETF": {"N": 2.05}, "PANEL": {"N": 2.06, "XS1": 3.16}}},
                       {"c_G": {"ETF": {"N": 2.615}, "PANEL": {"N": 2.06, "XS1": 3.16}}},
                       {"haircut_bp": {"ETF": 1, "PANEL": 3}}, {"receipt_sha256": "F" * 64}, {"receipt_sha256": None},
                       {"own_cap": {"N": 0.15, "XS1": 0.024}}, {"placebo": {"draws": 999, "count_max": 150}},
                       {"name": "FGS"}, {"c_margin": 0.0}):
            with self.subTest(change=change):
                self.assertIsNone(R.load({**good, **change})[0])
        for key in R.PIN_KEYS:
            with self.subTest(missing=key):
                self.assertIsNone(R.load({k: v for k, v in good.items() if k != key})[0])
        figures = json.loads(json.dumps(good["figures"]))
        figures["ETF|N"]["fp_ub"] = 0.2
        self.assertIsNone(R.load({**good, "figures": figures})[0])
        self.assertIsNone(R.load({})[0])
        self.assertIsNone(R.load(None)[0])


class TheSentences(unittest.TestCase):
    def setUp(self):
        self.rule = R.Rule(receipt_sha256="0" * 64, figures=json.loads(RECEIPT.read_text())["figures"])

    def test_the_words_hold_no_t_and_no_pnl(self):
        said = R.words(self.rule, typ="ETF", case="N", k=10, start="2026-10-16", c_used_value=2.61, k_own=200,
                       observed=1, judged=12, expected=0.33)
        self.assertIn("WEAK SCREEN", said)
        self.assertNotIn("t =", said)
        self.assertNotIn("P&L", said)
        self.assertIn("contamination is zero by construction for the judged sessions", said.lower())
        self.assertIn("1 forward passes of 12 ETF case N lineages", said)

    def test_the_beside_line(self):
        line = R.beside(self.rule, typ="ETF", case="N", k=10, start="2026-10-16", t=3.1, c_used_value=2.61,
                        k_own=200, g_bp=2, pnl=0.012, drift=0.21, observed=1, judged=12, expected=0.33)
        self.assertIn("t = 3.10 >= bar 2.61", line)
        self.assertIn("21.0% of its own Train-era", line)
        self.assertIn("WEAK SCREEN", line)
        self.assertIn("in the same fill world", line)
        panel = R.beside(self.rule, typ="PANEL", case="XS1", k=20, start="2026-10-16", t=3.4, c_used_value=3.16,
                         k_own=300, g_bp=3, pnl=0.01, drift=None, observed=0, judged=3, expected=0.1)
        self.assertIn("with its XS1 look (at most 12.0% a program) the combined rate is at most 15.0%", panel)
        self.assertNotIn("WEAK", panel)
        self.assertIn("WEAK at this checkpoint", R.beside(self.rule, typ="PANEL", case="N", k=5, start="x", t=3.0,
                                                          c_used_value=2.06, k_own=150, g_bp=3, pnl=0.0, drift=None,
                                                          observed=0, judged=1, expected=0.05))


    def test_a_panel_pass_states_a34s_two_sentences(self):
        """The captain's A34 point 5: beside every panel trade the forward length, the measured zero-edge rate at that
        checkpoint (the receipt's), and that a historical look would pass a memory-holder 10-99% (why there is none)."""
        curve = self.rule.figure("PANEL", "N")["zero_edge_by_checkpoint"]
        for k in (5, 20):
            common = dict(typ="PANEL", case="N", k=k, start="2026-10-16", c_used_value=2.06, k_own=150, observed=0,
                          judged=4, expected=0.2)
            rate = f"{100.0 * float(curve[R.PLAN.index(k)]):.1f}%"
            for text in (R.words(self.rule, **common),
                         R.beside(self.rule, t=3.0, g_bp=3, pnl=0.01, drift=None, **common)):
                with self.subTest(k=k):
                    self.assertIn(f"checkpoint {k} of 5-60 counted forward sessions since 2026-10-16", text)
                    self.assertIn(f"Measured zero-edge pass rate by checkpoint {k}: {rate}", text)
                    self.assertIn("memory-holding author 10-99%", text)
        etf = R.words(self.rule, typ="ETF", case="N", k=10, start="x", c_used_value=2.61, k_own=200, observed=0,
                      judged=1, expected=0.1)
        self.assertNotIn("memory-holding", etf)


if __name__ == "__main__":
    unittest.main()
