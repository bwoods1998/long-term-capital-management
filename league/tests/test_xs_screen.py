"""XS1, THE PANEL SCREEN (league/xs/screen.py; release E4; the pinned pre-registration XSCREEN-1 revision 2, section 4).

TheStudyVectors: all eight vectors of the study's file league/tests/fixtures/xs1_conformance.json, from the pools, the
series and the placebo t's of xs1_conformance_inputs.npz, run under the vector file's OWN bar (`k_XS`): every integer
and verdict exactly, every float to 1e-12; AND THE NINTH, by hand (the captain's A22 (4); xs1_conformance_c.json): a
2022-24 pool alone as a floor cell, and a tenth of the House's own shape, each counted here again by a brute-force
loop over every (Validation block, holdout block) pair. NoReceiptNoLook and TheCommittedPin (seal X10): nulls refuse,
a placebo block under another stratum fails closed, and the pin of the committed policy.json is the receipt file's,
value for value, through `screen.PIN_SOURCES`. Then the rule's parts at their edges: the receipt's loader, the series
and windows, the pre-check, the floor against brute force and every INELIGIBLE case, the look (119 placebos above
pass and 120 fail; t exactly at c_used passes and just below fails; the stress leg), the verdict's failure order, the
labels beside, the lineage in either series, and the sentence.

Invented series and figures only: no market data. The receipt is league/tests/fixtures/equity_screen_xs_fake.json
(marked FAKE: the real receipt's keys, invented figures); no threshold of a receipt is written in this file: a test
that needs one reads the fake, the vector file, or the committed pin.
"""

from __future__ import annotations

import copy
import dataclasses
import datetime as dt
import hashlib
import json
import math
import os
import tempfile
import unittest
from pathlib import Path

import numpy as np

from league import ci
from league.equity import config as e1
from league.equity import screen as s2
from league.equity.store import nyse_sessions
from league.tests import REAL_POLICY_PATH
from league.xs import config, placebo, results, screen

FIXTURES = Path(__file__).resolve().parent / "fixtures"
FAKE = FIXTURES / "equity_screen_xs_fake.json"
FAKE_SHA = hashlib.sha256(FAKE.read_bytes()).hexdigest()
VECTORS = FIXTURES / "xs1_conformance.json"
INPUTS = FIXTURES / "xs1_conformance_inputs.npz"
NINTH = FIXTURES / "xs1_conformance_c.json"
EPOCH = dt.date(1970, 1, 1)
CODE = "c0de" * 16
V_DAYS = [day for day, _ in nyse_sessions(*e1.WINDOWS["validation"])]
H_DAYS = [day for day, _ in nyse_sessions(e1.LOOK_FIRST, e1.LOOK_CAP)]
GRID = [k / 100 for k in range(501)]


def ordinal(day: dt.date) -> int:
    return (day - EPOCH).days


def receipt(**over) -> screen.ReceiptXS:
    """The fake receipt as the loader reads it, a field replaced where a test needs another."""
    return dataclasses.replace(screen.load_receipt(FAKE, pinned_sha256=FAKE_SHA), **over)


def make_series(days, x, *, w=None, exits=None, invested=None) -> screen.Series:
    n = len(days)
    return screen.Series(days=np.array([ordinal(d) for d in days], dtype=np.int32), r=np.asarray(x, dtype=np.float64),
                         w=np.full(n, 0.8) if w is None else np.asarray(w, dtype=np.float64), b=np.zeros(n),
                         exits=np.zeros(n, dtype=np.int64) if exits is None else np.asarray(exits, dtype=np.int64),
                         invested=np.ones(n, dtype=bool) if invested is None else np.asarray(invested, dtype=bool))


def exact(rng: np.random.Generator, n: int, mean: float, sd: float = 0.01) -> np.ndarray:
    """n daily values with exactly this mean (noise centred, then shifted): a t that does not hang on the seed."""
    z = sd * (rng.random(n) - 0.5) * math.sqrt(12.0)
    return z - z.mean() + mean


def daily(days, *, x, x15=None, r=None, u=None, w=None, bench=None, exits=None, invested=None) -> list[list]:
    """A run's `daily` rows in `results.DAILY`'s order (x15, r and u default to x; the basket to 0)."""
    n = len(days)
    x = np.asarray(x, dtype=np.float64)
    cols = {"r": x if r is None else r, "x": x, "x15": x if x15 is None else x15, "u": x if u is None else u,
            "w": np.full(n, 0.8) if w is None else w, "bench": np.zeros(n) if bench is None else bench,
            "exits": np.zeros(n, dtype=np.int64) if exits is None else exits,
            "invested": np.ones(n, dtype=bool) if invested is None else invested, "equity": np.full(n, 1000.0)}
    rows = []
    for i, day in enumerate(days):
        row: list = []
        for name in results.DAILY:
            if name == "day":
                row.append(day.isoformat())
            elif name == "exits":
                row.append(int(cols[name][i]))
            elif name == "invested":
                row.append(bool(cols[name][i]))
            else:
                row.append(float(cols[name][i]))
        rows.append(row)
    return rows


def placebo_block(ts, rc: screen.ReceiptXS, *, code: str = CODE, **over) -> dict:
    """A look run's placebo block as `placebo.run` writes it: the receipt's rung and draws, the seed the receipt and
    the program's code fix, the t of every draw on the holdout's sessions (None where undefined)."""
    ts = [None if t is None or not math.isfinite(t) else float(t) for t in ts]
    block = {"n": len(ts), "rung": rc.rung, "seed": screen.look_seed(rc.receipt_sha256, code),
             "spans": {"V": {"days": len(V_DAYS), "t": [None] * len(ts)}, "H": {"days": len(H_DAYS), "t": ts}},
             "reused": 0, "identity_share": 0.21}
    block.update(over)
    return block


def run_of(rows, block, rc: screen.ReceiptXS, **over) -> dict:
    """The look's run as the verdict reads it: its status, k, rung, daily rows and placebo block."""
    out = {"status": "ok", "k": 1.0, "rung": rc.rung, "capital": "1000", "daily": rows, "placebo": block}
    out.update(over)
    return out


def floor_of(rc: screen.ReceiptXS, k_p: int = 60, **over) -> dict:
    """A floor as `screen.floor` writes it for `rc` (an eligible one; invented figures)."""
    k_used = max(round(rc.c_XS * 100), k_p + round(rc.c_margin * 100))
    out = {"screen": "XS1", "eligible": True, "why": None, "method": "exact", "L": screen.H_LENGTH, "c_p": k_p / 100,
           "k_p": k_p, "c_used": k_used / 100, "k_used": k_used, "own_fp": 0.0432, "fp_cap": rc.fp_cap,
           "c_XS": rc.c_XS, "c_margin": rc.c_margin,
           "cells": {"C": {"pools": [751], "T": 231308, "k_cell": k_p, "kappa_H": 1e-5, "HO_0": 100000,
                           "HO_used": 9992}}}
    out.update(over)
    return out


def pool_series(span: int, x, w, *, lead=(9.9, -9.9)) -> screen.Series:
    """A Train-era series on the span's first sessions whose pool, from `POOL_SKIP` on, is (x, w): the two sessions
    before it are a run's first, which the floor drops (junk there must change nothing)."""
    x, w = np.asarray(x, dtype=np.float64), np.asarray(w, dtype=np.float64)
    days = [day for day, _ in nyse_sessions(*e1.TRAIN_ERA_SEGMENTS[span])][:len(x) + screen.POOL_SKIP]
    assert len(days) == len(x) + screen.POOL_SKIP, "the span is shorter than the pool"
    return make_series(days, np.concatenate([np.asarray(lead, dtype=np.float64), x]),
                       w=np.concatenate([np.ones(screen.POOL_SKIP), w]))


def seeded_pool(seed: int, n: int, lumpy: float = 0.0) -> tuple[np.ndarray, np.ndarray]:
    """An invented pool: invested on about nine sessions in ten at weight 0.8, a small noisy residual on them."""
    rng = np.random.default_rng([20261011, 77, seed, n])
    on = rng.random(n) < 0.9
    noise = 0.004 * (rng.random(n) + rng.random(n) + rng.random(n) - 1.5) * 2.0
    x = np.where(on, noise + lumpy * np.sin(np.arange(n) * 2.0 * math.pi / 380.0), 0.0)
    return x, np.where(on, 0.8, 0.0)


def t_stat(block) -> tuple[float, bool]:
    """The study's expression, written out: t = mean / std(ddof = 1) x sqrt(n) -> (t, defined)."""
    x = np.ascontiguousarray(block, dtype=np.float64)
    sd = x.std(ddof=1)
    if not sd >= 1e-12:
        return float("nan"), False
    t = x.mean() / sd * math.sqrt(len(x))
    return float(t), bool(math.isfinite(t))


def brute_cell(pools, L: int = 194, lv: int = 250, *, by_sets: bool = False) -> dict:
    """ONE FLOOR CELL BY BRUTE FORCE (the ninth vector's own derivation; nothing of league/xs/screen.py). `pools` =
    [(x, w)] as float lists. Every holdout block (pool k, start d: `L` consecutive sessions, circular inside the pool)
    is paired with EVERY Validation block (pool j, start b: `lv` sessions, circular), and the pair counts when the two
    share no session: by their session sets (`by_sets`, one pair at a time), or by the dot product of their indicator
    vectors (the same count, fast). -> T, each pool's W, kappa_H (pair-weighted), HO[0..500] and the grid points a t
    sits on to within 1e-7 (`ties`: such a k may round either way)."""
    lens = [len(x) for x, _ in pools]
    offsets = [sum(lens[:k]) for k in range(len(lens))]
    vblocks = [(j, b) for j, n in enumerate(lens) if n >= lv for b in range(n)]
    hblocks = [(k, d) for k, n in enumerate(lens) if n >= L for d in range(n)]

    def sessions(k: int, start: int, length: int) -> list[int]:
        return [offsets[k] + (start + i) % lens[k] for i in range(length)]

    if by_sets:
        vsets = [frozenset(sessions(j, b, lv)) for j, b in vblocks]
        weight = []
        for k, d in hblocks:
            hs = frozenset(sessions(k, d, L))
            weight.append(sum(1 for vs in vsets if vs.isdisjoint(hs)))
    else:
        mv = np.zeros((len(vblocks), sum(lens)))
        for row, (j, b) in enumerate(vblocks):
            mv[row, sessions(j, b, lv)] = 1.0
        mh = np.zeros((len(hblocks), sum(lens)))
        for row, (k, d) in enumerate(hblocks):
            mh[row, sessions(k, d, L)] = 1.0
        weight = [int(v) for v in ((mh @ mv.T) == 0).sum(1)] if len(vblocks) else [0] * len(hblocks)
    num = math.fsum(weight[i] * math.fsum(pools[k][0][(d + a) % lens[k]] for a in range(L))
                    for i, (k, d) in enumerate(hblocks))
    den = math.fsum(weight[i] * math.fsum(pools[k][1][(d + a) % lens[k]] for a in range(L))
                    for i, (k, d) in enumerate(hblocks))
    kappa = num / den if den > 0 else float("nan")
    ho = [0] * 501
    ties = set()
    for i, (k, d) in enumerate(hblocks):
        x, w = pools[k]
        block = [x[(d + a) % lens[k]] - w[(d + a) % lens[k]] * kappa for a in range(L)]
        t, ok = t_stat(block)
        if ok and abs(t * 100 - round(t * 100)) < 1e-7:
            ties.add(int(round(t * 100)))
        if ok and math.fsum(block) > 1e-12:
            for g in range(501):
                if t >= GRID[g]:
                    ho[g] += weight[i]
    per_pool: dict[int, set] = {}
    for i, (k, d) in enumerate(hblocks):
        per_pool.setdefault(k, set()).add(weight[i])
    return {"T": sum(weight), "W": [per_pool[k].pop() if len(per_pool.get(k, ())) == 1 else None
                                    for k in range(len(lens))], "kappa": kappa, "HO": ho, "ties": sorted(ties)}


# ============================================================================================ the study's vectors
class TheStudyVectors(unittest.TestCase):
    """XSCREEN-1's conformance vectors (HOUSE-RULE-XS1 section 9), all eight, and the ninth by hand."""

    @classmethod
    def setUpClass(cls):
        cls.doc = json.loads(VECTORS.read_text(encoding="utf-8"))
        cls.vectors = cls.doc["vectors"]
        cls.inputs = np.load(INPUTS)
        cls.k_xs = int(cls.doc["k_XS"])
        # THE VECTORS RUN UNDER THEIR OWN BAR: the fake receipt's shape with the vector file's k_XS, never a pin's
        cls.rc = receipt(c_XS=cls.k_xs / 100)
        cls.floors = {}
        for key, vector in cls.vectors.items():
            if "look" in vector:
                tag = key.split()[0]
                cls.floors[tag] = screen.floor(cls.segments(tag), receipt=cls.rc)

    @classmethod
    def tearDownClass(cls):
        cls.inputs.close()

    @classmethod
    def segments(cls, tag: str) -> list:
        out = []
        for span, label in ((0, "pool_d"), (1, "pool_c")):
            if f"{tag}/{label}_x" in cls.inputs.files:
                out.append(pool_series(span, cls.inputs[f"{tag}/{label}_x"], cls.inputs[f"{tag}/{label}_w"]))
            else:
                out.append(None)
        return out

    def looks(self):
        for key, vector in self.vectors.items():
            if "look" in vector:
                yield key.split()[0], vector

    def test_there_are_eight_and_they_run_under_their_own_bar(self):
        self.assertEqual(sorted(self.vectors), ["CH", "H", "V1 pass", "V2 fail", "V3 pre-check", "V4 stress",
                                                "V5 own floor", "V6 ineligible"])
        self.assertEqual({v["inputs"]["k_XS"] for _, v in self.looks()}, {self.k_xs})
        self.assertEqual(self.rc.c_XS, self.k_xs / 100)
        self.assertNotEqual(receipt().c_XS, self.rc.c_XS, "the fake's own bar is another: no vector reads a receipt's")
        self.assertEqual((self.doc["world"]["validation"], self.doc["world"]["holdout"]),
                         ([0, len(V_DAYS) - 1], [len(V_DAYS), len(V_DAYS) + len(H_DAYS) - 1]))

    def test_the_floor_of_every_vector_from_its_pools(self):
        """T, k_cell, HO[0], HO[k_used], kappa_H, k_p, k_used and own_fp: the integers exactly, the floats to 1e-12
        (they are equal to the last bit: the enumeration is the reference's own arithmetic)."""
        for tag, vector in self.looks():
            with self.subTest(vector=tag):
                want, got = vector["floor"], self.floors[tag]
                self.assertEqual((got["eligible"], got["why"], got["k_p"]), (want["eligible"], want["why"], want["k_p"]))
                self.assertEqual(list(got["cells"]), list(want["cells"]))
                for name, cell in want["cells"].items():
                    mine = got["cells"][name]
                    self.assertEqual((mine["T"], mine["k_cell"], mine["HO_0"], mine["HO_used"]),
                                     (cell["T"], cell["k_cell"], cell["HO_at_0"], cell["HO_at_k_used"]), name)
                    self.assertAlmostEqual(mine["kappa_H"], cell["kappa_H"], delta=1e-12)
                    self.assertEqual(mine["kappa_H"], cell["kappa_H"], "to the last bit")
                look = vector["look"]
                self.assertEqual(got["k_used"], look.get("k_used"))
                if want["eligible"]:
                    self.assertEqual((got["c_p"], got["c_used"]), (want["k_p"] / 100, look["k_used"] / 100))
                    self.assertAlmostEqual(got["own_fp"], look["own_fp"], delta=1e-12)
                    self.assertTrue(screen.floor_fits(got, self.rc))
                else:
                    self.assertEqual((got["own_fp"], got["cells"]), (None, {}))

    def test_the_cells_each_vector_has(self):
        self.assertEqual({tag: list(fl["cells"]) for tag, fl in self.floors.items()},
                         {"V1": ["both", "D"], "V2": ["both", "D"], "V3": ["both", "D"], "V4": ["both", "D"],
                          "V5": ["both", "D"], "V6": []})
        self.assertEqual(self.floors["V5"]["k_used"], self.floors["V5"]["k_p"] + round(self.rc.c_margin * 100),
                         "V5: the program's own floor binds above the screen's bar")
        self.assertEqual(self.floors["V1"]["k_used"], self.k_xs, "V1: the screen's bar binds")

    def run_of(self, tag: str, vector: dict, rc: screen.ReceiptXS) -> dict:
        """The vector's look run: its 444 sessions as 2025's 250 and the holdout's 194, the reference's series and
        its 999 placebo t's on the holdout, drawn under the vector's own seed."""
        get = lambda name: self.inputs[f"{tag}/{name}"]                     # noqa: E731
        rows = daily(V_DAYS + H_DAYS, x=get("x"), x15=get("x15"), r=get("r"), u=get("u"), w=get("w"), bench=get("B"),
                     exits=get("exits"), invested=get("invested"))
        block = placebo_block(get("placebo_t_H").tolist(), rc, code=vector["inputs"]["program_code_sha256"])
        self.assertEqual(str(block["seed"]), vector["inputs"]["placebo_seed"], "the seed the vector was drawn under")
        return run_of(rows, block, rc)

    def test_the_look_and_the_verdict_of_every_vector(self):
        """From the series and the placebo t's: the pre-check, the look's legs, the grid index, the placebo count, the
        verdict, and whether a look was spent."""
        for tag, vector in self.looks():
            with self.subTest(vector=tag):
                want, fl = vector["look"], self.floors[tag]
                rc = dataclasses.replace(self.rc, receipt_sha256=vector["inputs"]["receipt_sha256"])
                got = screen.verdict(self.run_of(tag, vector, rc), receipt=rc, program_floor=fl,
                                     code_sha256=vector["inputs"]["program_code_sha256"])
                self.assertEqual(got["screen"], "XS1")
                self.assertTrue(got["windows"]["ok"], got["windows"])
                pre = got["precheck"]
                spent = bool(fl["eligible"]) and screen.look_permitted(0, precheck_passed=pre["passed"])
                self.assertEqual(spent, want["look_spent"], "whether a look was spent")
                if want["verdict"] == "INELIGIBLE":
                    self.assertEqual((got["passed"], got["why"]), (False, f"the floor: {want['why']}"))
                    self.assertIsNone(got["look"], "no look is judged without a floor")
                    continue
                self.assertEqual((pre["round_trips"], pre["invested_days"], pre["passed"]),
                                 (want["RT_V"], want["ID_V"], want["precheck"]))
                self.assertEqual(pre["sum"], want["sum_V"], "math.fsum, as the reference")
                self.assertEqual((got["k_used"], got["c_used"]), (want["k_used"], want["k_used"] / 100))
                self.assertAlmostEqual(got["own_fp"], want["own_fp"], delta=1e-12)
                if want["verdict"] == "REFUSED AT THE PRE-CHECK":
                    self.assertEqual((got["passed"], got["why"]), (False, "the pre-check: sum_positive"))
                    continue
                look = got["look"]
                self.assertEqual((look["sum_h"], look["sum_h15"]), (want["sum_H"], want["sum_H_x15"]))
                self.assertAlmostEqual(look["t_H"], want["t_H"], delta=1e-12)
                self.assertEqual((look["grid_index"], look["count"], look["n_placebo"]),
                                 (want["grid_index"], want["placebo_count"], 999))
                self.assertEqual(round(look["p_plac"] * 1000), want["p_plac_thousandths"])
                legs = want["legs"]
                self.assertEqual(look["t_H"] is not None, legs["t_defined"])
                self.assertEqual({key: look["checks"][key] for key in ("sum_h", "sum_h15", "t_H", "placebo")},
                                 {"sum_h": legs["sum_H_positive"], "sum_h15": legs["stress_sum_positive"],
                                  "t_H": legs["t_at_or_above_c_used"], "placebo": legs["placebo_rank_ok"]})
                self.assertEqual(got["passed"], want["verdict"] == "PASS")
                failed = [key for key in ("sum_h", "sum_h15", "t_H", "placebo") if not look["checks"][key]]
                self.assertEqual(got["why"], None if got["passed"] else "the look: " + ", ".join(failed))
                self.assertEqual((got["t_H"], got["count"], got["p_plac"]), (look["t_H"], look["count"], look["p_plac"]))

    def test_each_vector_fails_or_passes_on_the_leg_it_was_built_for(self):
        verdicts = {}
        for tag, vector in self.looks():
            rc = dataclasses.replace(self.rc, receipt_sha256=vector["inputs"]["receipt_sha256"])
            verdicts[tag] = screen.verdict(self.run_of(tag, vector, rc), receipt=rc, program_floor=self.floors[tag],
                                           code_sha256=vector["inputs"]["program_code_sha256"])
        self.assertEqual({tag: v["why"] for tag, v in verdicts.items()},
                         {"V1": None, "V2": "the look: t_H, placebo", "V3": "the pre-check: sum_positive",
                          "V4": "the look: sum_h15, t_H, placebo", "V5": "the look: t_H",
                          "V6": "the floor: no floor cell"})
        self.assertTrue(verdicts["V1"]["passed"])
        v5 = verdicts["V5"]["look"]
        self.assertTrue(self.k_xs <= v5["grid_index"] < verdicts["V5"]["k_used"],
                        "V5 clears the screen's bar and not its own floor + the margin")

    def test_the_seed_is_the_receipts_and_the_codes(self):
        for _, vector in self.looks():
            inputs = vector["inputs"]
            mine = screen.look_seed(inputs["receipt_sha256"], inputs["program_code_sha256"])
            self.assertEqual(str(mine), inputs["placebo_seed"])
            try:                                             # package D's own (a Step 0 stub until D lands)
                theirs = placebo.look_seed(inputs["receipt_sha256"], inputs["program_code_sha256"])
            except NotImplementedError:
                theirs = mine
            self.assertEqual(theirs, mine, "one seed rule: the judge reads the seed the draw was made under")
        self.assertNotEqual(screen.look_seed("0" * 64, "f" * 64), screen.look_seed("0" * 64, "e" * 64))
        self.assertNotEqual(screen.look_seed("0" * 64, "f" * 64), screen.look_seed("1" * 64, "f" * 64))
        for bad in (("0" * 63, "f" * 64), ("0" * 64, None), ("0" * 64, "F" * 64)):
            with self.assertRaises(ValueError):
                screen.look_seed(*bad)

    def test_h_the_hand_vector(self):
        """PREREG 3.6's one lot: its literal series through the reader; x = r - B and the stress leg x15 = x - 0.5 s -
        f; one round trip is no activity; its basket carried more than its picks; and the three counterparts' placebo
        residuals average to zero and rank the program's t."""
        h = self.vectors["H"]
        days = V_DAYS[:3]
        rows = daily(days, x=h["x"], x15=h["x15"], r=h["r"], w=h["w"], bench=h["B"], exits=h["exits"],
                     invested=h["invested"])
        sx, s15, sr = (screen.series({"daily": rows}, column) for column in ("x", "x15", "r"))
        self.assertEqual((sx.r.tolist(), s15.r.tolist(), sr.r.tolist()), (h["x"], h["x15"], h["r"]))
        self.assertEqual((sx.w.tolist(), sx.exits.tolist(), sx.invested.tolist()), (h["w"], h["exits"], h["invested"]))
        for t in range(3):
            self.assertAlmostEqual(h["x"][t], h["r"][t] - h["B"][t], delta=1e-18)
            self.assertAlmostEqual(h["x15"][t], h["x"][t] - config.STRESS_SPREAD * h["s"][t]
                                   - config.STRESS_FEES * h["f"][t], delta=1e-18)
        self.assertAlmostEqual(h["f"][2], h["fee_usd"] / float(config.XS_SLEEVE_USD), delta=1e-18)
        pre = screen.precheck(sx)
        self.assertEqual((pre["round_trips"], pre["invested_days"], pre["sum"]), (1, 2, math.fsum(h["x"])))
        self.assertEqual(pre["checks"], {"activity": False, "sum_positive": True})
        beside = screen.labels({"daily": rows})
        self.assertEqual((beside["basket"], beside["label"]), ("basket-led", "unmeasured"))
        self.assertEqual((beside["sum_bench"], beside["sum_x"]), (math.fsum(h["B"]), math.fsum(h["x"])))
        by = h["placebo_residual_by_counterpart"]
        for t in range(3):
            self.assertAlmostEqual(math.fsum(by[name][t] for name in "abc"), 0.0, delta=1e-18)
        ts = {name: t_stat(by[name]) for name in "abc"}
        mine, defined = t_stat(h["x"])
        self.assertTrue(defined and all(ok for _, ok in ts.values()))
        above = sum(1 for name in "abc" if ts[name][0] >= mine)
        got = screen.look(sx, sx, h15=s15, c_used=0.0, placebo_t=[ts[name][0] for name in "abc"])
        self.assertEqual((got["count"], got["n_placebo"], got["p_plac"]), (above, 3, (1 + above) / 4))
        self.assertAlmostEqual(got["t_H"], mine, delta=1e-12)

    def test_ch_the_cells_are_the_receipts_rung(self):
        """CH's hundred names: the cell of each by the stratum the receipt names (`config.RUNGS[rung]`), written out:
        beta groups by rank within the sector, momentum groups by rank within the beta group, ties by the lower name,
        a sector of four or fewer names pooled."""
        cells = self.vectors["CH"]["cells"]
        names = [j for j in range(cells["names"]) if j not in cells["not_in_U"]]
        table = config.RUNGS[self.rc.rung]
        want = {}
        for sector in sorted({cells["sector"][j] for j in names}):
            inside = [j for j in names if cells["sector"][j] == sector]
            n = len(inside)
            groups = next((g for minimum, g in table if n >= minimum), None)
            if groups is None:
                self.assertLess(n, config.MIN_CELL)
                want.update({j: config.SMALL_CELL for j in inside})
                continue
            nb, nm = groups
            by_beta = sorted(inside, key=lambda j: (cells["beta"][j], j))
            for bg in range(nb):
                group = sorted((j for q, j in enumerate(by_beta) if (q * nb) // n == bg),
                               key=lambda j: (cells["mom"][j], j))
                for q, j in enumerate(group):
                    want[j] = config.CELL_SECTOR * sector + config.CELL_BETA * bg + (q * nm) // len(group)
        self.assertEqual([want.get(j, -1) for j in range(cells["names"])], cells["cell_id"])
        sizes = {}
        for j in names:
            sizes[want[j]] = sizes.get(want[j], 0) + 1
        self.assertTrue(all(count >= config.MIN_CELL for cell, count in sizes.items() if cell != config.SMALL_CELL))
        rows = self.vectors["CH"]["characteristics"]
        self.assertEqual([row["sector"] for row in rows if row["beta"] is None], [-1], "no beta, no sector")

    # ------------------------------------------------------------------------------- the ninth, by hand (A22 (4))
    def ninth(self) -> dict:
        doc = json.loads(NINTH.read_text(encoding="utf-8"))
        self.assertEqual(doc["k_XS"], self.k_xs, "the ninth runs under the study's vector bar")
        self.assertEqual((doc["rule"]["L"], doc["rule"]["LV"], doc["rule"]["margin_k"], doc["rule"]["k_max"]),
                         (screen.H_LENGTH, screen.V_LENGTH, round(self.rc.c_margin * 100), screen.K_MAX))
        return doc["vectors"]

    @staticmethod
    def pools_of(vector: dict) -> dict:
        """The fixture's integer pools as floats: x = x_micro / 1e6, w = w_centi / 100."""
        out = {}
        for label, pool in vector["pools"].items():
            out[label] = None if pool is None else ([v / 1e6 for v in pool["x_micro"]],
                                                    [v / 100 for v in pool["w_centi"]])
        return out

    def test_the_ninths_pools_are_its_generator(self):
        """The pools are integers anyone can write again: sha256 of a counter, no numpy stream."""
        def draw(tag, t, j):
            return int.from_bytes(hashlib.sha256(f"XS1|ninth|{tag}|{t}|{j}".encode()).digest()[:4], "big")

        for name, vector in self.ninth().items():
            for label, spec in vector["inputs"]["generator"].items():
                if spec is None:
                    self.assertIsNone(vector["pools"][label], name)
                    continue
                xs, ws = [], []
                for t in range(spec["n"]):
                    on = draw(spec["tag"], t, 0) % 10 != 0
                    noise = sum(draw(spec["tag"], t, j) % 2001 - 1000 for j in (2, 3, 4, 5))
                    wave = (spec["swing"] * (380 - 4 * abs(t % 380 - 190))) // 380
                    xs.append(3 * noise + wave if on else 0)
                    ws.append(60 + 20 * (draw(spec["tag"], t, 1) % 3) if on else 0)
                self.assertEqual((vector["pools"][label]["x_micro"], vector["pools"][label]["w_centi"]), (xs, ws), name)

    def check_by_hand(self, name: str, cells: tuple[str, ...]) -> None:
        vector = self.ninth()[name]
        pools = self.pools_of(vector)
        want = vector["floor"]
        self.assertEqual(tuple(want["cells"]), cells)
        members = {"both": ["pool_d", "pool_c"], "D": ["pool_d"], "C": ["pool_c"]}
        # (1) the fixture's figures are the brute-force loop's, counted here again, pair by pair
        k_cells = {}
        for cell, row in want["cells"].items():
            brute = brute_cell([pools[label] for label in members[cell]])
            self.assertEqual(brute["ties"], [], "no block of the vector sits on a grid point")
            self.assertEqual((brute["T"], brute["W"], brute["kappa"]), (row["T"], row["W"], row["kappa_H"]), cell)
            k_cell = next(k for k in range(501) if brute["HO"][k] * 100 <= 12 * brute["T"])
            k_cells[cell] = k_cell
            self.assertEqual((k_cell, brute["HO"][0], brute["HO"][want["k_used"]], brute["HO"][k_cell]),
                             (row["k_cell"], row["HO_at_0"], row["HO_at_k_used"], row["HO_at_k_cell"]), cell)
            if k_cell:
                self.assertEqual(brute["HO"][k_cell - 1], row["HO_below_k_cell"])
                self.assertGreater(brute["HO"][k_cell - 1] * 100, 12 * brute["T"], "the step below does not hold 12%")
            n = [len(pools[label][0]) for label in members[cell]]
            self.assertEqual(row["pools"], n)
            # T by its formula: one pool of n holds n (n - 443) pairs; two hold, a pool, n x (the other + n - 443)
            alone = [max(0, m - screen.V_LENGTH - screen.H_LENGTH + 1) for m in n]
            self.assertEqual(row["T"], sum(m * (sum(n) - m + alone[i]) for i, m in enumerate(n)))
        self.assertEqual(want["k_p"], max(k_cells.values()))
        self.assertEqual(want["k_used"], max(self.k_xs, want["k_p"] + round(self.rc.c_margin * 100)))
        # (2) and `floor` reproduces them: every integer exactly, the floats to 1e-12
        segments = [None if pools[label] is None else pool_series(span, *pools[label])
                    for span, label in ((0, "pool_d"), (1, "pool_c"))]
        got = screen.floor(segments, receipt=self.rc)
        self.assertEqual((got["eligible"], got["why"], got["k_p"], got["k_used"]),
                         (True, None, want["k_p"], want["k_used"]))
        self.assertEqual((got["c_p"], got["c_used"]), (want["c_p"], want["c_used"]))
        self.assertAlmostEqual(got["own_fp"], want["own_fp"], delta=1e-12)
        self.assertEqual(tuple(got["cells"]), cells)
        for cell, row in want["cells"].items():
            mine = got["cells"][cell]
            self.assertEqual((mine["pools"], mine["T"], mine["k_cell"], mine["HO_0"], mine["HO_used"]),
                             (row["pools"], row["T"], row["k_cell"], row["HO_at_0"], row["HO_at_k_used"]), cell)
            self.assertAlmostEqual(mine["kappa_H"], row["kappa_H"], delta=1e-12)

    def test_the_ninth_by_hand_the_2022_24_pool_alone(self):
        """A22 (4): no 2016-19 pool and a 2022-24 pool of 600 sessions: the one floor cell is "C". Counted three
        ways that agree: pair by pair on the blocks' session sets, by their indicator vectors, and by `floor`."""
        vector = self.ninth()["V9 C alone"]
        self.assertEqual(vector["inputs"]["train_pools"], {"n_2016_19": None, "n_2022_24": 600})
        self.check_by_hand("V9 C alone", ("C",))
        pool = self.pools_of(vector)["pool_c"]
        plain, fast = brute_cell([pool], by_sets=True), brute_cell([pool])
        self.assertEqual(plain, fast, "the session sets and the indicator vectors count the same pairs")
        self.assertEqual((plain["T"], plain["W"]), (600 * 157, [157]), "600 holdout starts, 157 Validation blocks each")
        self.assertGreater(vector["floor"]["k_used"], self.k_xs, "its own floor binds: the cell decides the bar")

    def test_the_tenth_the_houses_own_three_cells(self):
        """The House's shape: pools of 752 and 751 sessions (its Train segments of 754 and 753 less the two skipped).
        All three cells exist; the 2022-24 pool alone has the highest floor and sets k_p."""
        vector = self.ninth()["V10 three cells"]
        lengths = [len([d for d, _ in nyse_sessions(*segment)]) - screen.POOL_SKIP for segment in config.TRAIN_SEGMENTS]
        self.assertEqual(vector["inputs"]["train_pools"], {"n_2016_19": lengths[0], "n_2022_24": lengths[1]})
        self.check_by_hand("V10 three cells", ("both", "D", "C"))
        cells = vector["floor"]["cells"]
        self.assertEqual(vector["floor"]["k_p"], cells["C"]["k_cell"])
        self.assertGreater(cells["C"]["k_cell"], max(cells["both"]["k_cell"], cells["D"]["k_cell"]))


# ================================================================================================ seal X10
class NoReceiptNoLook(unittest.TestCase):
    """A screen with no pinned receipt refuses every program; a placebo block under another stratum fails closed."""

    def test_nulls_refuse(self):
        from league.swarm import elane_xs

        self.assertEqual(tuple(elane_xs.SCREEN_NULLS), screen.PIN_KEYS)
        for block in (None, {}, dict.fromkeys(screen.PIN_KEYS), dict(elane_xs.SCREEN_NULLS), "XS1", 7, []):
            self.assertIsNone(screen.pinned_receipt(block), block)

    def test_no_receipt_judges_nothing(self):
        rc = receipt()
        rng = np.random.default_rng(3)
        rows = daily(V_DAYS + H_DAYS, x=exact(rng, len(V_DAYS) + len(H_DAYS), 0.002))
        run = run_of(rows, placebo_block([0.0] * rc.placebo_draws, rc), rc)
        s2_receipt = s2.load_receipt_s2(FIXTURES / "equity_screen_2_fake.json", pinned_sha256=hashlib.sha256(
            (FIXTURES / "equity_screen_2_fake.json").read_bytes()).hexdigest())
        for none in (None, {}, dataclasses.asdict(rc), s2_receipt, "XS1"):
            with self.assertRaises(screen.ScreenRefused):
                screen.verdict(run, receipt=none, program_floor=floor_of(rc), code_sha256=CODE)
            with self.assertRaises(screen.ScreenRefused):
                screen.floor([None, pool_series(1, *seeded_pool(1, 600))], receipt=none)
            with self.assertRaises(screen.ScreenRefused):
                screen.beside_line({"screen": "XS1"}, none, n_cell=0)
            self.assertFalse(screen.floor_fits(floor_of(rc), none))
        self.assertTrue(screen.verdict(run, receipt=rc, program_floor=floor_of(rc), code_sha256=CODE)["passed"],
                        "the same run under a receipt is judged")

    def test_a_placebo_block_under_another_stratum_fails_closed(self):
        rc = receipt()
        rng = np.random.default_rng(3)
        rows = daily(V_DAYS + H_DAYS, x=exact(rng, len(V_DAYS) + len(H_DAYS), 0.002))
        ts = [0.0] * rc.placebo_draws
        other = next(r for r in screen.RUNGS if r != rc.rung)
        for run, word in ((run_of(rows, placebo_block(ts, rc, rung=other), rc), "the placebo block: drawn at rung"),
                          (run_of(rows, placebo_block(ts, rc, rung="R3"), rc), "the placebo block: drawn at rung"),
                          (run_of(rows, placebo_block(ts, rc, rung=None), rc), "the placebo block: drawn at rung"),
                          (run_of(rows, placebo_block(ts, rc), rc, rung=other), "the run: the run's residual is at rung")):
            got = screen.verdict(run, receipt=rc, program_floor=floor_of(rc), code_sha256=CODE)
            self.assertFalse(got["passed"])
            self.assertTrue(got["why"].startswith(word), got["why"])
            self.assertIsNone(got["look"], "no leg is judged on a block of another stratum")


class TheCommittedPin(unittest.TestCase):
    """CI's pin: policy.json `elane.screens.equity_xs` is the receipt file's, value for value (`screen.PIN_SOURCES`)."""

    def block(self):
        policy = json.loads(Path(REAL_POLICY_PATH).read_text())
        elane = policy.get("elane") if isinstance(policy.get("elane"), dict) else {}
        screens = elane.get("screens") if isinstance(elane.get("screens"), dict) else {}
        return screens.get("equity_xs")

    def test_the_committed_pin_is_the_receipts(self):
        """With nulls (as the lane ships until the integrator lands the receipt) every panel look refuses, and the
        tree holds no receipt without its pin. Once pinned: the sha is the file's bytes', every pinned value is the
        one at its `PIN_SOURCES` place, in `PIN_KEYS`' order, and the loader reads the file to the same receipt."""
        block = self.block()
        path = Path(ci.REPO) / screen.RECEIPT_PATH
        pinned = screen.pinned_receipt(block)
        if pinned is None:
            self.assertFalse(path.exists(), "a receipt in the tree needs its pin in the same commit")
            self.assertTrue(block is None or all(value is None for value in block.values()),
                            "a pin is whole or it is nulls: a half-filled block is neither")
            with self.assertRaises(screen.ScreenRefused):
                screen.verdict({}, receipt=pinned, program_floor={"eligible": True}, code_sha256=CODE)
            return
        self.assertTrue(path.exists(), f"a pinned receipt needs its file ({path.name})")
        self.assertEqual(pinned.receipt_sha256, hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertEqual(list(block), list(screen.PIN_KEYS))
        self.assertEqual(block, screen.pin(path), "every value copied from the receipt, none typed")
        loaded = screen.load_receipt(path, pinned_sha256=pinned.receipt_sha256)
        self.assertEqual(dataclasses.replace(loaded, fp={}), dataclasses.replace(pinned, fp={}))
        self.assertEqual((loaded.c_XS, loaded.rung), (pinned.c_XS, pinned.rung))
        doc = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(doc["name"], screen.RECEIPT_NAME)
        # its bar is READ, never written: the floor of one program under the pinned receipt and under the same
        # receipt at a higher bar differ by the bar and by nothing else
        segments = [None, pool_series(1, *seeded_pool(1, 600))]
        fl = screen.floor(segments, receipt=pinned)
        self.assertEqual(fl["k_used"], max(round(pinned.c_XS * 100), fl["k_p"] + round(pinned.c_margin * 100)))
        step = 0.5 if pinned.c_XS <= 2.5 else -0.5
        moved = screen.floor(segments, receipt=dataclasses.replace(pinned, c_XS=pinned.c_XS + step))
        self.assertEqual(moved["k_used"], max(round((pinned.c_XS + step) * 100),
                                              fl["k_p"] + round(pinned.c_margin * 100)))
        self.assertEqual((moved["k_p"], moved["cells"]["C"]["k_cell"]), (fl["k_p"], fl["cells"]["C"]["k_cell"]))

    def test_the_pin_sources_name_every_pinned_value(self):
        self.assertEqual(set(screen.PIN_SOURCES), set(screen.PIN_KEYS) - {"receipt_sha256"})
        fake = json.loads(FAKE.read_text(encoding="utf-8"))
        block = screen.pin(FAKE)
        self.assertEqual(list(block), list(screen.PIN_KEYS))
        self.assertEqual(block["receipt_sha256"], FAKE_SHA)
        for key, source in screen.PIN_SOURCES.items():
            value = fake
            for part in source.split("."):
                value = value[part]
            self.assertEqual(block[key], value, key)
        self.assertEqual(screen.pinned_receipt(block), receipt(fp={}), "the pin alone is the receipt the House runs")
        self.assertEqual(screen.pinned_receipt(json.loads(json.dumps(block))), receipt(fp={}), "as policy.json holds it")


# ================================================================================================== the receipt
class Receipts(unittest.TestCase):
    def test_the_loader_pins_the_sha(self):
        self.assertEqual(screen.receipt_sha256(FAKE), FAKE_SHA)
        self.assertIsNone(screen.receipt_sha256(FAKE.with_name("no-such-receipt.json")))
        rc = receipt()
        fake = json.loads(FAKE.read_text(encoding="utf-8"))
        self.assertEqual((rc.receipt_sha256, rc.c_XS, rc.c_margin, rc.alpha_plac, rc.placebo_draws, rc.rung),
                         (FAKE_SHA, fake["c_XS"], fake["c_margin"], fake["alpha_plac"], fake["placebo_draws"],
                          fake["stratum"]["rung"]))
        self.assertEqual((rc.fp_cap, rc.owner_wall, rc.validation_tries, rc.holdout_looks, rc.retry),
                         (fake["fp_cap"], fake["owner_wall"], 1, 1, False))
        self.assertEqual(rc.flags["X3"], ("FAKE: an invented flag",))
        self.assertEqual(rc.screen_flags, ("style-open",))
        self.assertEqual(set(rc.fp), set(screen.FP_KEYS))
        self.assertEqual(rc.beside, fake["stated_beside_every_live_trade"])
        for pin in ("f" * 64, FAKE_SHA.upper(), FAKE_SHA[:63], None, "", 7):
            with self.assertRaises(screen.ScreenRefused, msg=pin):
                screen.load_receipt(FAKE, pinned_sha256=pin)
        with self.assertRaises(screen.ScreenRefused):
            screen.load_receipt(FAKE.with_name("no-such-receipt.json"), pinned_sha256=FAKE_SHA)
        with self.assertRaises(screen.ScreenRefused):
            screen.pin(FAKE.with_name("no-such-receipt.json"))

    def test_the_fake_is_shaped_as_the_real_receipt(self):
        fake = json.loads(FAKE.read_text(encoding="utf-8"))
        self.assertEqual(set(screen.RECEIPT_KEYS) - set(fake), set())
        self.assertEqual(set(fake) - set(screen.RECEIPT_KEYS), {"eligibility", "beside_calibrated_reading"},
                         "a receipt may carry more than its keys (the adopted one adds these two)")
        self.assertIn("FAKE", fake["study"])
        self.assertIn("FAKE", fake["note"])
        self.assertNotEqual(fake["name"], screen.RECEIPT_NAME)
        for field in screen.BESIDE_FIELDS:
            self.assertIn("{" + field + "}", fake["stated_beside_every_live_trade"])

    def load(self, edit):
        doc = json.loads(FAKE.read_text(encoding="utf-8"))
        edit(doc)
        with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as tmp:
            path = Path(tmp) / "receipt.json"
            path.write_text(json.dumps(doc))
            return screen.load_receipt(path, pinned_sha256=hashlib.sha256(path.read_bytes()).hexdigest())

    def test_a_malformed_receipt_refuses(self):
        edits = [
            lambda d: d.pop("stated_beside_every_live_trade"), lambda d: d.pop("sha256"), lambda d: d.pop("ladder"),
            lambda d: d.pop("style_known_rate"), lambda d: d.update(screen="S2"), lambda d: d.update(screen=None),
            lambda d: d.update(contract="C-XS-2"), lambda d: d["contract"].update(name="C-XS-2"),
            lambda d: d.update(contract={}),
            lambda d: d.update(c_XS=3.01), lambda d: d.update(c_XS=-0.01), lambda d: d.update(c_XS=1.105),
            lambda d: d.update(c_XS="1.1"), lambda d: d.update(c_XS=None), lambda d: d.update(c_XS=True),
            lambda d: d.update(c_XS=float("nan")),
            lambda d: d.update(c_margin=0.04), lambda d: d.update(c_margin=0.0), lambda d: d.update(c_margin=0.055),
            lambda d: d.update(c_margin=None),
            lambda d: d.update(alpha_plac=0.13), lambda d: d.update(alpha_plac=0.0), lambda d: d.update(alpha_plac="0.12"),
            lambda d: d.update(fp_cap=0.13), lambda d: d.update(fp_cap=0.0), lambda d: d.update(fp_cap=None),
            lambda d: d.update(owner_wall=0.16), lambda d: d.update(owner_wall=None), lambda d: d.update(owner_wall=-0.1),
            lambda d: d.update(placebo_draws=1000), lambda d: d.update(placebo_draws=998),
            lambda d: d.update(placebo_draws=999.5), lambda d: d.update(placebo_draws=True),
            lambda d: d["stratum"].update(rung="R2"), lambda d: d["stratum"].update(rung="R3"),
            lambda d: d["stratum"].update(rung=None), lambda d: d["stratum"].pop("rung"),
            lambda d: d["stratum"].update(rung=["R0"]), lambda d: d.update(stratum="R0"),
            lambda d: d["lineage"].update(validation_tries=2), lambda d: d["lineage"].update(holdout_looks=2),
            lambda d: d["lineage"].update(holdout_looks=0), lambda d: d["lineage"].pop("validation_tries"),
            lambda d: d["lineage"].update(series=["x"]), lambda d: d["lineage"].update(series=["u", "x"]),
            lambda d: d["lineage"].update(series="xu"),
            lambda d: d.update(R3_retry_permitted=True), lambda d: d.update(R3_retry_permitted="no"),
            lambda d: d.update(R3_retry_permitted=None),
            lambda d: d.update(flags={"X1": "a string, not a list"}), lambda d: d.update(flags=["X1"]),
            lambda d: d.update(flags={"X1": [1]}), lambda d: d.update(flags=None),
            lambda d: d.update(screen_flags=["another flag"]), lambda d: d.update(screen_flags="style-open"),
            lambda d: d.update(screen_flags=["style-open", "style-open"]), lambda d: d.update(screen_flags=None),
            lambda d: d.update(screen_flags=[["style-open"]]),
            lambda d: d.update(stated_beside_every_live_trade="XS1, bar {c_used}"),
            lambda d: d.update(stated_beside_every_live_trade=None),
            lambda d: d["precheck"].update(rt_min=25), lambda d: d["precheck"].update(id_min=100),
            lambda d: d.update(precheck="(RT >= 20 or ID >= 120)"),
            lambda d: d["floor"].update(method="worlds"), lambda d: d.update(floor={}),
            lambda d: d["windows"].update(calibrated_L=251),
            lambda d: d["windows"].update(holdout="2026-01-02 .. 2026-12-31"),
            lambda d: d["windows"].update(holdout="the holdout"), lambda d: d.update(windows=None),
            lambda d: d["stratum"].update(window=250), lambda d: d["stratum"].update(min_valid=60),
            lambda d: d["stratum"].update(min_cell=4), lambda d: d["stratum"].update(market="QQQ"),
            lambda d: d["stratum"].update(funds=list(reversed(d["stratum"]["funds"]))),
            lambda d: d["stratum"].update(funds=d["stratum"]["funds"][:-1]), lambda d: d["stratum"].update(funds="XLB"),
        ]
        for i, edit in enumerate(edits):
            with self.assertRaises(screen.ScreenRefused, msg=i):
                self.load(edit)
        with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as tmp:
            for text in ("{not json", "[]", '"XS1"'):
                path = Path(tmp) / "not.json"
                path.write_text(text)
                with self.assertRaises(screen.ScreenRefused):
                    screen.load_receipt(path, pinned_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
                with self.assertRaises(screen.ScreenRefused):
                    screen.pin(path)

    def test_a_receipt_may_be_narrower_never_wider_and_may_carry_more(self):
        """A rebuilt receipt at another bar loads (the captain may land one): c_XS is read, never written. The bar
        may be made narrower (a lower placebo bar, cap or wall; a wider margin; the fallback rung)."""
        fake = json.loads(FAKE.read_text(encoding="utf-8"))
        rebuilt = self.load(lambda d: d.update(c_XS=d["c_XS"] + 0.08))
        self.assertAlmostEqual(rebuilt.c_XS, fake["c_XS"] + 0.08, delta=1e-12)
        self.assertEqual(self.load(lambda d: d.update(c_XS=0)).c_XS, 0.0)
        self.assertEqual(self.load(lambda d: d.update(c_XS=3)).c_XS, 3.0)
        self.assertEqual(self.load(lambda d: d.update(alpha_plac=0.1)).alpha_plac, 0.1)
        self.assertEqual(self.load(lambda d: d.update(fp_cap=0.1)).fp_cap, 0.1)
        self.assertEqual(self.load(lambda d: d.update(owner_wall=0.14)).owner_wall, 0.14)
        self.assertEqual(self.load(lambda d: d.update(c_margin=0.06)).c_margin, 0.06)
        self.assertEqual(self.load(lambda d: d["stratum"].update(rung="R1")).rung, "R1")
        self.assertEqual(self.load(lambda d: d.update(screen_flags=[])).screen_flags, ())
        self.assertEqual(self.load(lambda d: d.update(contract="C-XS-1")).rung, fake["stratum"]["rung"])
        self.assertEqual(self.load(lambda d: d.update(a_key_beyond={"any": "thing"})).c_XS, fake["c_XS"])
        self.assertEqual(self.load(lambda d: d.update(placebo_draws=999.0)).placebo_draws, 999)

    def test_the_policy_block(self):
        good = screen.pin(FAKE)
        self.assertEqual(screen.pinned_receipt(good), receipt(fp={}))
        self.assertEqual(screen.pinned_receipt({**good, "fp": {"style_known_max": 0.2}}).fp, {"style_known_max": 0.2})
        overs = [{"receipt_sha256": None}, {"receipt_sha256": "F" * 64}, {"receipt_sha256": "f" * 63},
                 {"name": "S2"}, {"screen": "S2"}, {"name": None}, {"screen": "equity_screen_xs_1"},
                 {"c_XS": None}, {"c_XS": float("nan")}, {"c_XS": True}, {"c_XS": 3.01}, {"c_XS": -0.1},
                 {"c_XS": 1.234}, {"c_margin": 0.04}, {"c_margin": None}, {"alpha_plac": 0.13}, {"alpha_plac": 0},
                 {"fp_cap": None}, {"fp_cap": 0.0}, {"fp_cap": 0.5}, {"owner_wall": 0.0}, {"owner_wall": "0.15"},
                 {"owner_wall": 0.2}, {"placebo_draws": 200}, {"placebo_draws": None}, {"rung": "R2"}, {"rung": None},
                 {"validation_tries": 2}, {"validation_tries": None}, {"holdout_looks": 2}, {"retry": True},
                 {"retry": None}, {"retry": "false"}, {"retry": 0}, {"flags": ["X1"]}, {"flags": {"X1": [1]}},
                 {"flags": None}, {"screen_flags": ["x"]}, {"screen_flags": None}, {"beside": None},
                 {"beside": "XS1, bar {c_used}"}]
        for over in overs:
            self.assertIsNone(screen.pinned_receipt({**good, **over}), over)
        for missing in screen.PIN_KEYS:
            self.assertIsNone(screen.pinned_receipt({k: v for k, v in good.items() if k != missing}), missing)

    def test_the_figures_the_pre_registration_fixes(self):
        """The module's constants are the pre-registration's (which every receipt must state), and the placebo bar's
        integer is the one 0.12 of 1,000 gives: 119 pass, 120 fail."""
        self.assertEqual((screen.FP_CAP, screen.OWNER_WALL, screen.ALPHA_PLAC, screen.C_MARGIN), (0.12, 0.15, 0.12, 0.05))
        self.assertEqual((screen.PLACEBO_DRAWS, placebo.DRAWS), (999, 999))
        self.assertTrue((1 + screen.PLACEBO_COUNT_MAX) * 100 <= 12 * (screen.PLACEBO_DRAWS + 1)
                        < (2 + screen.PLACEBO_COUNT_MAX) * 100)
        self.assertEqual((screen.H_LENGTH, screen.V_LENGTH), (len(H_DAYS), len(V_DAYS)))
        self.assertEqual((screen.MIN_POOL_BOTH, screen.MIN_POOL_ALONE, screen.POOL_SKIP), (251, 550, 2))
        self.assertEqual((screen.ACTIVITY_ROUND_TRIPS, screen.ACTIVITY_INVESTED_DAYS, screen.SAME_LINEAGE_CORR),
                         (s2.ACTIVITY_ROUND_TRIPS, s2.ACTIVITY_INVESTED_DAYS, s2.SAME_LINEAGE_CORR))
        self.assertEqual(screen.GRID.tolist(), GRID)
        self.assertEqual(screen.GRID.tolist(), s2.GRID.tolist(), "the study's grid is S2's")
        self.assertEqual(len(e1.TRAIN_ERA_SEGMENTS), 2, "the floor's cells are named for two Train-era spans")
        for (first, last), (era_first, era_last) in zip(config.TRAIN_SEGMENTS, e1.TRAIN_ERA_SEGMENTS):
            self.assertTrue(era_first <= first <= last <= era_last, "the House's segments lie in the floor's spans")
        self.assertEqual(placebo.LOOK_SEED, "XS1|{receipt}|{code}|placebo")
        self.assertIs(screen.holdout_t, s2.holdout_t)
        self.assertIs(screen.look_permitted, s2.look_permitted)
        self.assertIs(screen.ScreenRefused, s2.ScreenRefused)
        self.assertIs(screen.Series, s2.Series)


# ========================================================================================== the series and windows
class TheSeries(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(5)
        n = len(V_DAYS) + len(H_DAYS)
        self.x = exact(rng, n, 0.001)
        self.cols = {"x15": self.x - 1e-5, "r": self.x + 2e-4, "u": self.x * 0.5, "w": rng.random(n),
                     "bench": np.full(n, 2e-4), "exits": (rng.random(n) < 0.3).astype(np.int64),
                     "invested": rng.random(n) < 0.9}
        self.rows = daily(V_DAYS + H_DAYS, x=self.x, **self.cols)

    def test_each_column_is_read_as_a_series(self):
        for column, values in (("x", self.x), ("x15", self.cols["x15"]), ("r", self.cols["r"]), ("u", self.cols["u"])):
            s = screen.series({"daily": self.rows}, column)
            self.assertIsInstance(s, s2.Series)
            np.testing.assert_array_equal(s.r, values)
            np.testing.assert_array_equal(s.days, [ordinal(d) for d in V_DAYS + H_DAYS])
            np.testing.assert_array_equal(s.w, self.cols["w"])
            np.testing.assert_array_equal(s.exits, self.cols["exits"])
            np.testing.assert_array_equal(s.invested, self.cols["invested"])
            self.assertEqual((s.days.dtype, s.b.tolist()), (np.int32, [0.0] * len(self.x)))
        np.testing.assert_array_equal(screen.series({"daily": self.rows}).r, self.x)
        np.testing.assert_array_equal(screen.series({"daily": json.loads(json.dumps(self.rows))}).r, self.x)

    def test_it_fails_closed(self):
        bad_rows = []
        for i, value in ((2, float("nan")), (2, float("inf")), (2, None), (2, "0.1"), (2, True),
                         (results.DAILY.index("w"), float("nan")), (results.DAILY.index("exits"), -1),
                         (results.DAILY.index("exits"), 0.5), (results.DAILY.index("invested"), "yes"),
                         (results.DAILY.index("invested"), 2), (0, "not a day"), (0, None)):
            rows = copy.deepcopy(self.rows)
            rows[7][i] = value
            bad_rows.append(rows)
        short = copy.deepcopy(self.rows)
        short[3] = short[3][:-1]
        swapped = copy.deepcopy(self.rows)
        swapped[3], swapped[4] = swapped[4], swapped[3]
        twice = copy.deepcopy(self.rows)
        twice[4][0] = twice[3][0]
        for rows in (*bad_rows, short, swapped, twice, [], None, "rows", [self.rows[0][:3]], ["a row"]):
            with self.assertRaises(ValueError):
                screen.series({"daily": rows})
        for result in (None, {}, [], "result"):
            with self.assertRaises(ValueError):
                screen.series(result)
        for column in ("bench", "w", "equity", "day", "s", ""):
            with self.assertRaises(ValueError, msg=column):
                screen.series({"daily": self.rows}, column)

    def test_the_look_run_is_cut_in_two(self):
        v, h = screen.split(screen.series({"daily": self.rows}))
        self.assertEqual((len(v.days), len(h.days)), (len(V_DAYS), len(H_DAYS)))
        np.testing.assert_array_equal(v.r, self.x[:len(V_DAYS)])
        np.testing.assert_array_equal(h.r, self.x[len(V_DAYS):])
        np.testing.assert_array_equal(h.exits, self.cols["exits"][len(V_DAYS):])
        self.assertEqual((int(v.days[0]), int(h.days[-1])), (ordinal(V_DAYS[0]), ordinal(H_DAYS[-1])))
        got = screen.windows(v, h)
        self.assertEqual(got, {"ok": True, "why": None,
                               "validation": {"first": V_DAYS[0].isoformat(), "last": V_DAYS[-1].isoformat(),
                                              "sessions": len(V_DAYS)},
                               "holdout": {"first": H_DAYS[0].isoformat(), "last": H_DAYS[-1].isoformat(),
                                           "sessions": len(H_DAYS)}})

    def test_a_session_in_neither_window_is_refused(self):
        after = [day for day, _ in nyse_sessions(e1.LOOK_CAP + dt.timedelta(days=1), dt.date(2026, 10, 30))]
        before = [day for day, _ in nyse_sessions(dt.date(2024, 12, 1), dt.date(2024, 12, 31))]
        for days in (V_DAYS + H_DAYS + after[:1], before[-1:] + V_DAYS + H_DAYS):
            with self.assertRaises(ValueError):
                screen.split(make_series(days, np.zeros(len(days))))
        v, h = screen.split(make_series(V_DAYS[10:], np.zeros(len(V_DAYS) - 10)))
        self.assertEqual((len(v.days), len(h.days)), (len(V_DAYS) - 10, 0), "a Validation run alone has no holdout")

    def test_the_windows_are_the_calibrated_ones(self):
        zeros = lambda days: make_series(days, np.zeros(len(days)))            # noqa: E731
        good_v, good_h = zeros(V_DAYS), zeros(H_DAYS)
        self.assertTrue(screen.windows(good_v, good_h)["ok"])
        cases = [(zeros(V_DAYS[:-1]), good_h, "Validation"), (zeros(V_DAYS[1:]), good_h, "Validation"),
                 (zeros([]), good_h, "Validation"), (zeros(H_DAYS + V_DAYS[:56]), good_h, "Validation"),
                 (good_v, zeros(H_DAYS[:-1]), "holdout"), (good_v, zeros(H_DAYS[1:]), "holdout"),
                 (good_v, zeros([]), "holdout"), (good_v, zeros(V_DAYS[:len(H_DAYS)]), "holdout"),
                 (zeros(V_DAYS[:-1] + V_DAYS[-2:-1]), good_h, "Validation"),
                 (good_v, zeros(H_DAYS[:-1] + H_DAYS[-2:-1]), "holdout")]
        for v, h, word in cases:
            got = screen.windows(v, h)
            self.assertFalse(got["ok"])
            self.assertIn(word, got["why"])
        after = [day for day, _ in nyse_sessions(e1.LOOK_CAP + dt.timedelta(days=1), dt.date(2026, 10, 30))]
        late = screen.windows(good_v, zeros(H_DAYS[1:] + after[:1]))
        self.assertFalse(late["ok"], "194 sessions that end after the cap are not the calibrated holdout")


# ====================================================================================================== the pre-check
class ThePreCheck(unittest.TestCase):
    def series(self, x=None, *, exits=0, invested=250):
        n = len(V_DAYS)
        x = np.full(n, 1e-4) if x is None else np.asarray(x, dtype=np.float64)
        e = np.zeros(n, dtype=np.int64)
        e[:exits] = 1
        inv = np.zeros(n, dtype=bool)
        inv[:invested] = True
        return make_series(V_DAYS, x, exits=e, invested=inv)

    def test_the_activity_line(self):
        for exits, invested, active in ((20, 0, True), (19, 0, False), (0, 120, True), (0, 119, False),
                                        (19, 119, False), (20, 120, True), (0, 0, False)):
            got = screen.precheck(self.series(exits=exits, invested=invested))
            self.assertEqual((got["round_trips"], got["invested_days"], got["checks"]["activity"], got["passed"]),
                             (exits, invested, active, active))
        two = self.series(exits=10, invested=0)
        two.exits[:10] = 2                                  # two lots fully exited in one session count as two
        self.assertTrue(screen.precheck(two)["checks"]["activity"])

    def test_the_sum_must_clear_zero_and_is_exact(self):
        n = len(V_DAYS)
        self.assertFalse(screen.precheck(self.series(np.zeros(n)))["passed"])
        self.assertFalse(screen.precheck(self.series(np.full(n, -1e-4)))["passed"])
        edge = np.zeros(n)
        edge[0] = 1e-12
        self.assertFalse(screen.precheck(self.series(edge))["checks"]["sum_positive"], "exactly 1e-12 is not above it")
        edge[0] = 1.1e-12
        self.assertTrue(screen.precheck(self.series(edge))["checks"]["sum_positive"])
        # math.fsum: a plain running sum loses the small term between the two large ones
        x = np.zeros(n)
        x[:3] = (1e16, 2e-12, -1e16)
        got = screen.precheck(self.series(x))
        self.assertEqual((got["sum"], got["checks"]["sum_positive"]), (2e-12, True))
        self.assertEqual(float(np.cumsum(x)[-1]), 0.0, "what a running sum would have read")
        self.assertEqual(set(got), {"passed", "round_trips", "invested_days", "sum", "sessions", "checks"})
        self.assertEqual(got["sessions"], n)


# ======================================================================================================== the floor
def set_brute(pools, L: int, lv: int) -> dict:
    """The plainest enumeration, E1's own test's: every (V pool, V start, H pool, H start) tuple whose two blocks
    share no session, listed one by one."""
    lens = [len(x) for x, _ in pools]
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
                    tuples.append((c, d))
    return {"T": len(tuples), "per_block": {key: tuples.count(key) for key in set(tuples)}}


class TheFloorByBruteForce(unittest.TestCase):
    """The exact enumeration against direct counts, with V and H shrunk (V 5 sessions, H 3): pools shorter than V + H,
    one pool, two, three. A t that sits on a grid point may round either way, so its k is left out."""

    def test_every_pair(self):
        rng = np.random.default_rng(20261011)
        for lens in ([13, 9], [9], [7, 12], [12, 6, 8], [20], [4, 9], [5, 3], [8]):
            pools = []
            for n in lens:
                w = rng.random(n) * (rng.random(n) > 0.2)
                pools.append((((rng.random(n) - 0.48) * 0.04 * (w > 0) + 0.001 * w).tolist(), w.tolist()))
            arrays = [(np.array(x), np.array(w)) for x, w in pools]
            fast, plain, sets = brute_cell(pools, 3, 5), brute_cell(pools, 3, 5, by_sets=True), set_brute(pools, 3, 5)
            self.assertEqual({k: v for k, v in fast.items()}, {k: v for k, v in plain.items()}, lens)
            self.assertEqual(fast["T"], sets["T"], lens)
            weights, total = screen._tuple_weights(lens, 3, 5)
            self.assertEqual(total, fast["T"], lens)
            if total == 0:
                with self.assertRaises(ValueError):
                    screen._enumerate(arrays, L=3, lv=5)
                continue
            ho, t, kappa, w_used = screen._enumerate(arrays, L=3, lv=5)
            self.assertEqual((t, w_used), (fast["T"], weights), lens)
            self.assertEqual([w for w, n in zip(weights, lens) if n >= 3],
                             [w for w, n in zip(fast["W"], lens) if n >= 3], lens)
            for (k, d), count in sets["per_block"].items():
                self.assertEqual(count, weights[k], "every holdout block of a pool pairs with W Validation blocks")
            self.assertAlmostEqual(kappa, fast["kappa"], delta=1e-15)
            keep = [k for k in range(501) if k not in fast["ties"]]
            self.assertEqual([int(ho[k]) for k in keep], [fast["HO"][k] for k in keep], lens)
            self.assertGreater(len(keep), 480)
            self.assertEqual(len(ho), 501)
            self.assertTrue(all(ho[k] >= ho[k + 1] for k in range(500)), "a higher bar is cleared by no more blocks")

    def test_the_pair_counts_by_their_formula(self):
        """One pool of n: W = n - V - L + 1 and T = n W; a pool shorter than V + L holds no pair; two pools: each
        holdout block pairs with every Validation block of the other pool, and with its own pool's that fit."""
        self.assertEqual(screen._tuple_weights([20], 3, 5), ([13], 260))
        self.assertEqual(screen._tuple_weights([7], 3, 5), ([0], 0))
        self.assertEqual(screen._tuple_weights([7, 12], 3, 5), ([12, 7 + 5], 7 * 12 + 12 * 12))
        self.assertEqual(screen._tuple_weights([4, 9], 3, 5), ([9, 2], 4 * 9 + 9 * 2), "a pool too short for V holds H")
        self.assertEqual(screen._tuple_weights([2, 9], 3, 5), ([0, 2], 18), "a pool too short for H holds neither")
        # at the rule's own lengths: the study's cells and the House's
        self.assertEqual(screen._tuple_weights([1004, 499]), ([499 + 561, 1004 + 56], 1593180))
        self.assertEqual(screen._tuple_weights([1004]), ([561], 563244))
        self.assertEqual(screen._tuple_weights([752, 751]), ([751 + 309, 752 + 308], 1593180))
        self.assertEqual(screen._tuple_weights([751]), ([308], 231308))
        self.assertEqual(screen._tuple_weights([443]), ([0], 0), "443 sessions hold no V beside an H")
        self.assertEqual(screen._tuple_weights([444]), ([1], 444))

    def test_the_grid_index(self):
        for k in range(501):
            self.assertEqual(screen._grid_index(GRID[k]), k, "t exactly at k / 100 clears step k")
            below = float(np.nextafter(GRID[k], -math.inf))
            self.assertEqual(screen._grid_index(below), k - 1, "and the float just below it does not")
        self.assertEqual((screen._grid_index(None), screen._grid_index(-0.5), screen._grid_index(float("nan"))),
                         (-1, -1, -1))
        self.assertEqual((screen._grid_index(5.0), screen._grid_index(77.0), screen._grid_index(float("inf"))),
                         (500, 500, 500))

    def test_at_the_rules_own_lengths_on_a_pool_alone(self):
        """L 194 and V 250 on a seeded pool of 560 sessions: `floor`'s cell against the brute force, every k."""
        x, w = seeded_pool(4, 560, lumpy=0.0015)
        rc = receipt()
        got = screen.floor([None, pool_series(1, x, w)], receipt=rc)
        brute = brute_cell([(x.tolist(), w.tolist())])
        self.assertEqual(brute["ties"], [])
        cell = got["cells"]["C"]
        k_cell = next(k for k in range(501) if brute["HO"][k] * 100 <= 12 * brute["T"])
        self.assertEqual((cell["T"], cell["k_cell"], cell["HO_0"], cell["HO_used"]),
                         (brute["T"], k_cell, brute["HO"][0], brute["HO"][got["k_used"]]))
        ho, total, kappa, _ = screen._enumerate([(x, w)])
        self.assertEqual((ho.tolist(), total), (brute["HO"], brute["T"]))
        self.assertAlmostEqual(kappa, brute["kappa"], delta=1e-15)


class TheFloor(unittest.TestCase):
    """The floor's cells, its figures as run, and every INELIGIBLE case (no look)."""

    def setUp(self):
        self.rc = receipt()

    def floor(self, n_d, n_c, *, rc=None, lumpy=0.0):
        segments = [None if n_d is None else pool_series(0, *seeded_pool(0, n_d, lumpy)),
                    None if n_c is None else pool_series(1, *seeded_pool(1, n_c, lumpy))]
        return screen.floor(segments, receipt=self.rc if rc is None else rc)

    def test_the_cells_by_the_pools_lengths(self):
        """(i) both pools together when each has at least 251 sessions; (ii) each single pool of at least 550."""
        cases = {(None, 549): [], (None, 550): ["C"], (549, None): [], (550, None): ["D"], (250, 251): [],
                 (251, 250): [], (251, 251): ["both"], (250, 550): ["C"], (550, 250): ["D"], (251, 550): ["both", "C"],
                 (550, 251): ["both", "D"], (550, 550): ["both", "D", "C"], (None, None): [], (100, 100): []}
        for (n_d, n_c), cells in cases.items():
            got = self.floor(n_d, n_c)
            self.assertEqual((got["eligible"], list(got["cells"])), (bool(cells), cells), (n_d, n_c))
            if not cells:
                self.assertEqual((got["why"], got["k_p"], got["k_used"], got["own_fp"]),
                                 (screen.NO_CELL_WHY, None, None, None))
            else:
                self.assertEqual([got["cells"][c]["pools"] for c in cells],
                                 [{"both": [n_d, n_c], "D": [n_d], "C": [n_c]}[c] for c in cells])
        self.assertEqual(screen.FLOOR_CELLS, ("both", "D", "C"))

    def test_what_it_states_and_that_it_fits_its_receipt(self):
        got = self.floor(752, 751)
        self.assertEqual(set(got), {"screen", "eligible", "why", "method", "L", "c_p", "k_p", "c_used", "k_used",
                                    "own_fp", "fp_cap", "c_XS", "c_margin", "cells"})
        self.assertEqual((got["screen"], got["method"], got["L"]), ("XS1", "exact", screen.H_LENGTH))
        self.assertEqual((got["fp_cap"], got["c_XS"], got["c_margin"]), (self.rc.fp_cap, self.rc.c_XS, self.rc.c_margin))
        self.assertEqual(got["k_p"], max(cell["k_cell"] for cell in got["cells"].values()))
        self.assertEqual(got["k_used"], max(round(self.rc.c_XS * 100), got["k_p"] + round(self.rc.c_margin * 100)))
        self.assertEqual((got["c_p"], got["c_used"]), (got["k_p"] / 100, got["k_used"] / 100))
        self.assertEqual(got["own_fp"], max(c["HO_used"] / c["T"] for c in got["cells"].values()))
        self.assertLessEqual(got["own_fp"], self.rc.fp_cap, "in-sample: at most the cap by construction")
        for cell in got["cells"].values():
            self.assertEqual(set(cell), {"pools", "T", "k_cell", "kappa_H", "HO_0", "HO_used"})
            self.assertLessEqual(cell["HO_used"] * 100, 12 * cell["T"])
        self.assertEqual(json.loads(json.dumps(got)), got, "plain figures: the family's state keeps it as it is")
        self.assertTrue(screen.floor_fits(got, self.rc))
        self.assertTrue(screen.floor_fits(json.loads(json.dumps(got)), self.rc))
        self.assertTrue(screen.floor_fits(self.floor(None, 100), self.rc), "an ineligible floor run by this receipt fits")
        # a rebuilt receipt at another bar, margin or cap: the floor is run again
        for other in (dataclasses.replace(self.rc, c_XS=self.rc.c_XS + 0.08),
                      dataclasses.replace(self.rc, c_margin=0.06), dataclasses.replace(self.rc, fp_cap=0.1)):
            self.assertFalse(screen.floor_fits(got, other))
            self.assertTrue(screen.floor_fits(self.floor(752, 751, rc=other), other))
        for junk in (None, {}, "floor", {**got, "screen": "S2"}, {**got, "method": "worlds"}, {**got, "L": 251},
                     {k: v for k, v in got.items() if k != "eligible"}, {**got, "c_XS": None}):
            self.assertFalse(screen.floor_fits(junk, self.rc), junk)

    def test_the_bar_is_the_screens_or_the_programs_own_floor_plus_the_margin(self):
        """c_used = max(c_XS, c_p + c_margin): the same pools under a low bar and a high one; the own floor can only
        raise the bar, and a rebuilt receipt moves k_used and nothing of the cells."""
        quiet = self.floor(752, 751)
        swing = self.floor(752, 751, lumpy=0.002)
        self.assertGreater(swing["k_p"], quiet["k_p"], "a regime swing in the residual raises the program's own floor")
        low = dataclasses.replace(self.rc, c_XS=0.0)
        high = dataclasses.replace(self.rc, c_XS=3.0)
        margin = round(self.rc.c_margin * 100)
        for fl in (quiet, swing):
            under_low = screen.floor([pool_series(0, *seeded_pool(0, 752, 0.002 if fl is swing else 0.0)),
                                      pool_series(1, *seeded_pool(1, 751, 0.002 if fl is swing else 0.0))], receipt=low)
            self.assertEqual((under_low["k_p"], under_low["k_used"]), (fl["k_p"], fl["k_p"] + margin))
            self.assertEqual({c: (v["T"], v["k_cell"], v["HO_0"]) for c, v in under_low["cells"].items()},
                             {c: (v["T"], v["k_cell"], v["HO_0"]) for c, v in fl["cells"].items()})
        self.assertEqual(self.floor(752, 751, rc=high)["k_used"], 300, "the screen's bar binds where it is higher")

    def test_deterministic_placed_by_days_and_blind_to_the_two_skipped_sessions(self):
        d, c = seeded_pool(0, 600), seeded_pool(1, 580)
        base = screen.floor([pool_series(0, *d), pool_series(1, *c)], receipt=self.rc)
        self.assertEqual(screen.floor([pool_series(0, *d), pool_series(1, *c)], receipt=self.rc), base)
        self.assertEqual(screen.floor([pool_series(1, *c), pool_series(0, *d)], receipt=self.rc), base,
                         "a series is placed by its days, never by its position")
        self.assertEqual(screen.floor([None, pool_series(1, *c), None, pool_series(0, *d)], receipt=self.rc), base)
        self.assertEqual(screen.floor([pool_series(0, *d, lead=(0.0, 123.0)), pool_series(1, *c, lead=(-5.0, 5.0))],
                                      receipt=self.rc), base, "the first two sessions of a run are not in its pool")
        moved = (c[0].copy(), c[1])
        moved[0][0] += 0.01                                  # the pool's own first session IS in it
        self.assertNotEqual(screen.floor([pool_series(0, *d), pool_series(1, *moved)], receipt=self.rc), base)
        self.assertEqual(base["cells"]["both"]["pools"], [600, 580])

    def test_the_houses_own_segments_give_all_three_cells(self):
        """Train segments of 754 and 753 sessions (`config.TRAIN_SEGMENTS`), each run from its own first session."""
        segments = []
        for span, (first, last) in enumerate(config.TRAIN_SEGMENTS):
            days = [day for day, _ in nyse_sessions(first, last)]
            x, w = seeded_pool(span, len(days))
            segments.append(make_series(days, x, w=w))
        got = screen.floor(segments, receipt=self.rc)
        self.assertEqual((got["eligible"], list(got["cells"])), (True, ["both", "D", "C"]))
        self.assertEqual([got["cells"][c]["pools"] for c in ("both", "D", "C")], [[752, 751], [752], [751]])
        self.assertEqual([got["cells"][c]["T"] for c in ("both", "D", "C")], [1593180, 752 * 309, 751 * 308])

    def test_a_session_outside_the_spans_is_ineligible(self):
        x, w = seeded_pool(1, 600)
        good = pool_series(1, x, w)
        spans = [(dt.date(2020, 1, 2), dt.date(2023, 12, 29)), (dt.date(2021, 1, 4), dt.date(2023, 12, 29)),
                 (dt.date(2023, 1, 3), dt.date(2025, 12, 31)), (dt.date(2025, 1, 2), dt.date(2026, 10, 9)),
                 (dt.date(2019, 6, 3), dt.date(2022, 6, 30)), (dt.date(2021, 12, 31), dt.date(2024, 12, 31))]
        before = [dt.date(2015, 6, 1) + dt.timedelta(days=i) for i in range(900)]
        listed = [[day for day, _ in nyse_sessions(first, last)][:602] for first, last in spans]
        listed.append([day for day in before if day.weekday() < 5][:602])        # a run that starts before 2016
        for days in listed:
            got = screen.floor([None, make_series(days, np.concatenate([[0.0, 0.0], x[:len(days) - 2]]),
                                                  w=np.ones(len(days)))], receipt=self.rc)
            self.assertEqual((got["eligible"], got["cells"]), (False, {}), (days[0], days[-1]))
            self.assertIn("outside the Train-era spans", got["why"])
        twice = screen.floor([good, pool_series(1, *seeded_pool(2, 560))], receipt=self.rc)
        self.assertEqual((twice["eligible"], twice["why"]), (False, "two series for one Train-era span"))
        # a short series outside the spans still makes the program ineligible: no session of 2025 enters a floor
        stray = make_series(V_DAYS[:5], np.zeros(5))
        self.assertFalse(screen.floor([good, stray], receipt=self.rc)["eligible"])

    def test_no_exposure_and_series_that_are_not_finite(self):
        x, w = seeded_pool(1, 600)
        idle = screen.floor([None, pool_series(1, np.zeros(600), np.zeros(600))], receipt=self.rc)
        self.assertEqual((idle["eligible"], idle["why"]), (False, "cell C: no exposure in the pool (kappa is undefined)"))
        for bad in (float("nan"), float("inf"), -float("inf")):
            for column in (0, 1):
                pool = [x.copy(), w.copy()]
                pool[column][300] = bad
                got = screen.floor([None, pool_series(1, *pool)], receipt=self.rc)
                self.assertEqual((got["eligible"], got["why"]), (False, "cell C: the pool series are not finite"))
        # in the pooled cell too, whichever pool carries it
        d = seeded_pool(0, 300)
        d[0][17] = float("nan")
        got = screen.floor([pool_series(0, *d), pool_series(1, x, w)], receipt=self.rc)
        self.assertEqual((got["eligible"], got["why"]), (False, "cell both: the pool series are not finite"))
        # values past what a sum can hold are no series either (never an exception out of the floor)
        huge = x.copy()
        huge[:4] = 1.7e308
        with np.errstate(over="ignore", invalid="ignore"):
            got = screen.floor([None, pool_series(1, huge, w)], receipt=self.rc)
        self.assertEqual((got["eligible"], got["why"]), (False, "cell C: the pool series are not finite"))

    def test_no_k_on_the_grid_holds_the_cap(self):
        """One loss day and a steady small gain otherwise: at zero edge almost every holdout that misses the loss day
        shows an enormous t_H, so no c on 0.00..5.00 holds the holdout-only rate at the cap."""
        n = 751
        rng = np.random.default_rng(16)
        x = 1e-4 + 1e-7 * (rng.random(n) - 0.5)
        x[n // 2] = -1e-4 * (n - 1)
        got = screen.floor([None, pool_series(1, x, np.full(n, 0.5))], receipt=self.rc)
        self.assertFalse(got["eligible"])
        self.assertIn("cell C: no k on 0..500 holds", got["why"])
        self.assertEqual((got["k_p"], got["k_used"], got["cells"]), (None, None, {}))

    def test_k_used_above_the_grid_is_ineligible(self):
        swing = seeded_pool(1, 751, lumpy=0.002)
        base = screen.floor([None, pool_series(1, *swing)], receipt=self.rc)
        self.assertTrue(base["eligible"])
        wide = dataclasses.replace(self.rc, c_margin=(screen.K_MAX - base["k_p"]) / 100)
        at = screen.floor([None, pool_series(1, *swing)], receipt=wide)
        self.assertEqual((at["eligible"], at["k_used"]), (True, screen.K_MAX), "k_used of exactly 500 is on the grid")
        wider = dataclasses.replace(self.rc, c_margin=(screen.K_MAX - base["k_p"] + 1) / 100)
        over = screen.floor([None, pool_series(1, *swing)], receipt=wider)
        self.assertEqual((over["eligible"], over["k_used"], over["own_fp"], over["cells"]), (False, None, None, {}))
        self.assertEqual((over["k_p"], over["c_p"]), (base["k_p"], base["k_p"] / 100), "its own floor is still stated")
        self.assertIn("k_used > 500", over["why"])

    def test_malformed_series_raise(self):
        x, w = seeded_pool(1, 600)
        good = pool_series(1, x, w)
        short = s2.Series(days=good.days, r=good.r[:-1], w=good.w, b=good.b, exits=good.exits, invested=good.invested)
        with self.assertRaises(ValueError):
            screen.floor([None, short], receipt=self.rc)
        mixed = s2.Series(days=good.days[::-1].copy(), r=good.r, w=good.w, b=good.b, exits=good.exits,
                          invested=good.invested)
        with self.assertRaises(ValueError):
            screen.floor([None, mixed], receipt=self.rc)
        self.assertFalse(screen.floor([], receipt=self.rc)["eligible"])
        self.assertFalse(screen.floor([None, None], receipt=self.rc)["eligible"])

    def test_a_lower_cap_gives_a_higher_floor(self):
        """The cap is the receipt's, held as an exact fraction: at 10% the floor is no lower than at 12%."""
        swing = [None, pool_series(1, *seeded_pool(1, 751, lumpy=0.001))]
        at_cap = screen.floor(swing, receipt=self.rc)
        tighter = screen.floor(swing, receipt=dataclasses.replace(self.rc, fp_cap=0.1))
        self.assertGreaterEqual(tighter["k_p"], at_cap["k_p"])
        cell = tighter["cells"]["C"]
        self.assertLessEqual(cell["HO_used"] * 10, cell["T"])
        self.assertEqual(tighter["fp_cap"], 0.1)


# ========================================================================================================= the look
class TheLook(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(41)
        self.v = make_series(V_DAYS, exact(rng, len(V_DAYS), 0.0016))
        self.h = make_series(H_DAYS, exact(rng, len(H_DAYS), 0.0016))
        self.h15 = make_series(H_DAYS, self.h.r - 2e-4)
        self.t_h = screen.holdout_t(self.h.r)
        self.draws = receipt().placebo_draws

    def placebos(self, above: int, *, undefined: int = 0) -> list:
        """The receipt's number of placebo t's: `above` of them at or above the program's, `undefined` of them None or
        not finite, the rest below it."""
        ts: list = [self.t_h] * above + [None, float("nan"), float("inf") * 0.0][:1] * 0
        ts += [None if i % 2 else float("nan") for i in range(undefined)]
        ts += [self.t_h - 1.0] * (self.draws - len(ts))
        return ts

    def look(self, **over):
        args = {"h15": self.h15, "c_used": 1.0, "placebo_t": self.placebos(0)}
        args.update(over)
        return screen.look(args.pop("v", self.v), args.pop("h", self.h), **args)

    def test_a_pass_and_what_it_states(self):
        got = self.look()
        self.assertEqual(set(got), {"passed", "t_H", "sum_h", "sum_h15", "count", "n_placebo", "p_plac", "c_used",
                                    "grid_index", "precheck_result", "checks"})
        self.assertTrue(got["passed"])
        self.assertEqual(got["checks"], {"precheck": True, "sum_h": True, "sum_h15": True, "t_H": True, "placebo": True})
        self.assertEqual((got["t_H"], got["count"], got["n_placebo"], got["p_plac"]),
                         (self.t_h, 0, self.draws, 1 / (self.draws + 1)))
        self.assertEqual((got["sum_h"], got["sum_h15"]), (math.fsum(self.h.r.tolist()), math.fsum(self.h15.r.tolist())))
        self.assertEqual(got["grid_index"], int(math.floor(self.t_h * 100)))
        self.assertEqual(got["precheck_result"], screen.precheck(self.v))

    def test_119_placebos_above_pass_and_120_fail(self):
        """T8: p_plac <= 0.12 in integers, (1 + count) x 100 <= 12 x 1000; a placebo t equal to the program's counts
        as above; an undefined one as not above."""
        at = self.look(placebo_t=self.placebos(screen.PLACEBO_COUNT_MAX))
        self.assertEqual((at["count"], at["checks"]["placebo"], at["passed"]), (119, True, True))
        self.assertEqual(at["p_plac"], 0.12)
        over = self.look(placebo_t=self.placebos(screen.PLACEBO_COUNT_MAX + 1))
        self.assertEqual((over["count"], over["checks"]["placebo"], over["passed"]), (120, False, False))
        self.assertEqual({k: v for k, v in over["checks"].items() if k != "placebo"},
                         {"precheck": True, "sum_h": True, "sum_h15": True, "t_H": True})
        holes = self.look(placebo_t=self.placebos(screen.PLACEBO_COUNT_MAX, undefined=300))
        self.assertEqual((holes["count"], holes["n_placebo"], holes["passed"]), (119, self.draws, True))
        just_below = [float(np.nextafter(self.t_h, -math.inf))] * self.draws
        self.assertEqual(self.look(placebo_t=just_below)["count"], 0)
        self.assertEqual(self.look(placebo_t=[self.t_h] * self.draws)["count"], self.draws)

    def test_the_placebo_bar_is_the_receipts_alpha_in_integers(self):
        """A receipt may state a lower bar: at 0.10 of 1,000, 99 above pass and 100 fail; at 0.12 of four draws, none
        above is 1 / 5: a fail."""
        self.assertTrue(self.look(placebo_t=self.placebos(99), alpha=0.1)["checks"]["placebo"])
        self.assertFalse(self.look(placebo_t=self.placebos(100), alpha=0.1)["checks"]["placebo"])
        few = self.look(placebo_t=[self.t_h - 1.0] * 4)
        self.assertEqual((few["count"], few["p_plac"], few["checks"]["placebo"]), (0, 0.2, False))
        none = self.look(placebo_t=[])
        self.assertEqual((none["count"], none["p_plac"], none["checks"]["placebo"]), (0, None, False),
                         "no placebo, no rank: a fail")
        for bad in (0.0, 1.0, -0.1, float("nan"), None, "0.12", True):
            with self.assertRaises(ValueError, msg=bad):
                self.look(alpha=bad)
        for bad in ("1.0", True, [1.0], b"1"):
            with self.assertRaises(ValueError, msg=bad):
                self.look(placebo_t=[bad] + [0.0] * (self.draws - 1))

    def test_t_exactly_at_c_used_passes_and_just_below_fails(self):
        """The bar is held on the grid: the smallest shift of the holdout's mean that reaches grid step k passes, and
        the float before it fails, the two t's a rounding apart on either side of k / 100."""
        k = 130
        base = self.h.r - self.h.r.mean()
        lo, hi = 0.0, 0.01
        for _ in range(200):
            mid = (lo + hi) / 2.0
            if mid in (lo, hi):
                break
            if screen._grid_index(screen.holdout_t(base + mid)) >= k:
                hi = mid
            else:
                lo = mid
        at, under = make_series(H_DAYS, base + hi), make_series(H_DAYS, base + lo)
        t_at, t_under = screen.holdout_t(at.r), screen.holdout_t(under.r)
        self.assertTrue(t_under < k / 100 <= t_at)
        self.assertLess(t_at - t_under, 1e-11, "the two holdouts differ by one rounding of the mean")
        passes = self.look(h=at, h15=make_series(H_DAYS, at.r), c_used=k / 100)
        fails = self.look(h=under, h15=make_series(H_DAYS, under.r), c_used=k / 100)
        self.assertEqual((passes["checks"]["t_H"], passes["passed"], passes["grid_index"]), (True, True, k))
        self.assertEqual((fails["checks"]["t_H"], fails["passed"], fails["grid_index"]), (False, False, k - 1))
        self.assertEqual({key: ok for key, ok in fails["checks"].items() if key != "t_H"},
                         {"precheck": True, "sum_h": True, "sum_h15": True, "placebo": True})
        self.assertFalse(self.look(h=at, h15=make_series(H_DAYS, at.r), c_used=(k + 1) / 100)["passed"])

    def test_the_sum_and_the_sd_of_the_holdout(self):
        n = len(H_DAYS)
        zero = make_series(H_DAYS, np.zeros(n))
        got = self.look(h=zero, h15=zero, c_used=0.0)
        self.assertEqual((got["passed"], got["t_H"], got["count"], got["grid_index"]), (False, None, None, -1))
        self.assertEqual(got["checks"], {"precheck": True, "sum_h": False, "sum_h15": False, "t_H": False,
                                         "placebo": False})
        flat = make_series(H_DAYS, np.full(n, 0.001))
        got = self.look(h=flat, h15=flat, c_used=0.0)
        self.assertEqual((got["checks"]["sum_h"], got["t_H"], got["checks"]["t_H"], got["passed"]),
                         (True, None, False, False), "a holdout with no spread has no t: a fail, even at a bar of zero")
        loses = make_series(H_DAYS, exact(np.random.default_rng(2), n, -0.0005))
        got = self.look(h=loses, h15=loses, c_used=0.0, placebo_t=[-9.0] * self.draws)
        self.assertEqual((got["checks"]["sum_h"], got["checks"]["t_H"], got["passed"]), (False, False, False))
        # the sums are exact: a holdout whose plain running sum reads zero
        x = np.zeros(n)
        x[:3] = (1e16, 2e-12, -1e16)
        tiny = make_series(H_DAYS, x)
        self.assertEqual(self.look(h=tiny, h15=tiny, c_used=0.0)["sum_h"], 2e-12)
        # and a sum that is no number is never above zero: no exception, a fail
        for values in ((1.7e308, 1.7e308), (float("inf"), -float("inf")), (float("nan"), 1.0)):
            x = np.full(n, 0.001)
            x[:2] = values
            wild = make_series(H_DAYS, x)
            with np.errstate(over="ignore", invalid="ignore"):
                got = self.look(h=wild, h15=wild, c_used=0.0)
            self.assertEqual((got["checks"]["sum_h"], got["passed"]), (False, False), values)
            self.assertTrue(math.isnan(got["sum_h"]), values)

    def test_the_stress_leg(self):
        """sum_H x15 > 1e-12: the program must stay positive at 1.5 times the spread with its sell fees doubled."""
        costly = make_series(H_DAYS, self.h.r - 2.0 * self.h.r.mean())
        got = self.look(h15=costly)
        self.assertEqual(got["checks"], {"precheck": True, "sum_h": True, "sum_h15": False, "t_H": True,
                                         "placebo": True})
        self.assertFalse(got["passed"])
        self.assertLess(got["sum_h15"], 0.0)
        with self.assertRaises(ValueError):
            self.look(h15=make_series(H_DAYS[:-1], self.h15.r[:-1]))
        with self.assertRaises(ValueError):
            self.look(h15=make_series(H_DAYS[1:] + H_DAYS[:1], self.h15.r))

    def test_a_failed_precheck_fails_the_look(self):
        idle = make_series(V_DAYS, self.v.r, invested=np.zeros(len(V_DAYS), dtype=bool))
        got = self.look(v=idle)
        self.assertEqual(got["checks"], {"precheck": False, "sum_h": True, "sum_h15": True, "t_H": True, "placebo": True})
        self.assertFalse(got["passed"])
        self.assertFalse(screen.look_permitted(0, precheck_passed=got["checks"]["precheck"]), "and spends no look")

    def test_c_used_lies_on_the_grid(self):
        for bad in (None, True, float("nan"), "1.3", 1.305, -0.01, 5.01):
            with self.assertRaises(ValueError, msg=bad):
                self.look(c_used=bad)
        self.assertEqual(self.look(c_used=0)["c_used"], 0.0)
        self.assertFalse(self.look(c_used=5.0)["passed"])


# ====================================================================================================== the verdict
class TheVerdict(unittest.TestCase):
    def setUp(self):
        self.rc = receipt()
        rng = np.random.default_rng(21)
        self.xv = exact(rng, len(V_DAYS), 0.0012)
        self.xh = exact(rng, len(H_DAYS), 0.0024)
        self.x = np.concatenate([self.xv, self.xh])
        self.t_h = screen.holdout_t(self.xh)
        self.floor = floor_of(self.rc)
        self.assertGreater(self.t_h, self.floor["c_used"] + 0.5)

    def rows(self, **over):
        cols = {"x": self.x, "x15": self.x - 1e-4, "r": self.x + 3e-4, "bench": np.full(len(self.x), 3e-4)}
        cols.update(over)
        return daily(V_DAYS + H_DAYS, **cols)

    def look_run(self, rows=None, block=None, **over):
        block = placebo_block([self.t_h - 1.0] * self.rc.placebo_draws, self.rc) if block is None else block
        return run_of(self.rows() if rows is None else rows, block, self.rc, **over)

    def judge(self, **over):
        args = {"receipt": self.rc, "program_floor": self.floor, "code_sha256": CODE}
        args.update(over)
        return screen.verdict(args.pop("run") if "run" in args else self.look_run(), **args)

    def test_a_pass_and_what_it_states(self):
        got = self.judge()
        self.assertEqual(set(got), {"screen", "passed", "why", "c_used", "c_p", "k_used", "t_H", "sum_h", "sum_h15",
                                    "p_plac", "count", "n_placebo", "rung", "own_fp", "t_raw", "t_nw5", "basket",
                                    "label", "loadings", "identity_share", "precheck", "look", "windows", "flags",
                                    "receipt"})
        self.assertEqual((got["screen"], got["passed"], got["why"]), ("XS1", True, None))
        self.assertEqual((got["c_used"], got["c_p"], got["k_used"], got["own_fp"]),
                         (self.floor["c_used"], self.floor["c_p"], self.floor["k_used"], self.floor["own_fp"]))
        self.assertEqual((got["t_H"], got["count"], got["n_placebo"], got["p_plac"]),
                         (self.t_h, 0, self.rc.placebo_draws, 1 / (self.rc.placebo_draws + 1)))
        self.assertEqual((got["sum_h"], got["sum_h15"]),
                         (math.fsum(self.xh.tolist()), math.fsum((self.xh - 1e-4).tolist())))
        self.assertEqual((got["rung"], got["receipt"], got["identity_share"]), (self.rc.rung, FAKE_SHA, 0.21))
        self.assertEqual(got["t_raw"], screen.holdout_t(self.xh + 3e-4), "the raw P&L's t on H, beside")
        self.assertIsInstance(got["t_nw5"], float)
        self.assertEqual((got["basket"], got["label"], got["loadings"]), ("selection-led", "unmeasured", {}))
        heavy = self.judge(run=self.look_run(self.rows(bench=np.full(len(self.x), 3e-3))))
        self.assertEqual((heavy["basket"], heavy["passed"]), ("basket-led", True), "a label beside, never a gate")
        self.assertEqual(got["flags"], ["X3: FAKE: an invented flag", "style-open"])
        self.assertTrue(got["precheck"]["passed"] and got["look"]["passed"] and got["windows"]["ok"])
        self.assertEqual(json.loads(json.dumps(got)), got, "plain figures: the look's record keeps it as it is")

    def test_the_failure_order(self):
        """The first failed condition is `why`: the floor; the run and its placebo block; the windows; the pre-check;
        the look."""
        idle = np.zeros(len(self.x), dtype=bool)
        idle[len(V_DAYS):] = True                                    # no lot held on any Validation close
        weak = np.concatenate([self.xv, self.xh - self.xh.mean() + 1e-6])
        stray = daily(V_DAYS[1:] + H_DAYS, x=weak[1:], invested=idle[1:])
        other = placebo_block([0.0] * self.rc.placebo_draws, self.rc, rung="R9")
        bad_floor = {**self.floor, "eligible": False, "why": "no floor cell"}
        steps = [
            (dict(run=self.look_run(stray, other, status="disqualified"), program_floor=bad_floor), "the floor: no floor cell"),
            (dict(run=self.look_run(stray, other, status="disqualified")), "the run: the run ended 'disqualified'"),
            (dict(run=self.look_run(stray, other)), "the placebo block: drawn at rung 'R9'"),
            (dict(run=self.look_run(stray)), "the windows: the Validation series is not calendar 2025's 250 sessions (249)"),
            (dict(run=self.look_run(daily(V_DAYS + H_DAYS, x=weak, invested=idle))), "the pre-check: activity"),
            (dict(run=self.look_run(daily(V_DAYS + H_DAYS, x=weak))), "the look: t_H"),
        ]
        for args, why in steps:
            got = self.judge(**args)
            self.assertFalse(got["passed"])
            self.assertTrue(got["why"].startswith(why), (got["why"], why))
        self.assertTrue(self.judge()["passed"])

    def test_c_used_is_the_larger_of_the_screens_bar_and_the_own_floor_plus_the_margin(self):
        k_xs, margin = round(self.rc.c_XS * 100), round(self.rc.c_margin * 100)
        low = self.judge(program_floor=floor_of(self.rc, k_p=k_xs - margin - 20))
        self.assertEqual((low["k_used"], low["c_p"]), (k_xs, (k_xs - margin - 20) / 100), "a low own floor buys nothing")
        edge = self.judge(program_floor=floor_of(self.rc, k_p=k_xs - margin))
        self.assertEqual(edge["k_used"], k_xs)
        high = self.judge(program_floor=floor_of(self.rc, k_p=k_xs + 30))
        self.assertEqual((high["k_used"], high["c_used"]), (k_xs + 30 + margin, (k_xs + 30 + margin) / 100))
        # the bar a look met is the one the verdict held it to
        k_t = int(math.floor(self.t_h * 100))
        self.assertTrue(self.judge(program_floor=floor_of(self.rc, k_p=k_t - margin))["passed"])
        over = self.judge(program_floor=floor_of(self.rc, k_p=k_t - margin + 1))
        self.assertEqual((over["passed"], over["why"]), (False, "the look: t_H"))

    def test_the_floor_must_be_eligible_the_receipts_and_whole(self):
        rebuilt = dataclasses.replace(self.rc, c_XS=self.rc.c_XS + 0.08)
        cases = [
            ({**self.floor, "eligible": False, "why": None}, "the floor: not eligible"),
            ({**self.floor, "screen": "S2"}, "the floor: not an XS1 floor (S2)"),
            ({}, "the floor: not an XS1 floor (none)"), (None, "the floor: not an XS1 floor (none)"),
            ({**self.floor, "method": "worlds"}, "the floor: not an exact floor"),
            ({**self.floor, "L": 251}, "the floor: not an exact floor"),
            ({**self.floor, "fp_cap": 0.2}, "the floor: run at fp_cap 0.2"),
            ({**self.floor, "c_margin": 0.0}, "the floor: run at c_margin 0.0"),
            (floor_of(rebuilt), "the floor: run at c_XS"),
            ({**self.floor, "k_used": self.floor["k_used"] - 1}, "the floor: k_used"),
            ({**self.floor, "k_used": None}, "the floor: k_used"),
            ({**self.floor, "k_p": None}, "the floor: k_p"), ({**self.floor, "k_p": 501}, "the floor: k_p"),
            ({**self.floor, "k_p": 499, "k_used": 504}, "the floor: k_used"),
            ({**self.floor, "own_fp": None}, "the floor: own_fp"), ({**self.floor, "own_fp": 1.5}, "the floor: own_fp"),
        ]
        for fl, why in cases:
            got = self.judge(program_floor=fl)
            self.assertFalse(got["passed"], fl)
            self.assertTrue(got["why"].startswith(why), (got["why"], why))
            self.assertEqual((got["look"], got["c_used"], got["t_H"]), (None, None, None), "no leg without a floor")
            self.assertIsNotNone(got["precheck"], "what is read beside is still read")
        # the receipt rebuilt at another bar judges the same run with its own floor
        self.assertTrue(self.judge(receipt=rebuilt, program_floor=floor_of(rebuilt),
                                     run=run_of(self.rows(), placebo_block([0.0] * 999, rebuilt), rebuilt))["passed"])

    def test_the_run_must_have_ended_ok_at_k_1_on_the_receipts_rung(self):
        for over, why in (({"status": "disqualified"}, "the run: the run ended 'disqualified': a partial series"),
                          ({"status": "error"}, "the run: the run ended 'error'"),
                          ({"status": None}, "the run: the run ended None"),
                          ({"k": 1.5}, "the run: the run is at k 1.5"), ({"k": None}, "the run: the run is at k None"),
                          ({"k": "1.0"}, "the run: the run is at k '1.0'"),
                          ({"rung": "R1"}, "the run: the run's residual is at rung 'R1'"),
                          ({"rung": None}, "the run: the run's residual is at rung None")):
            got = self.judge(run=self.look_run(**over))
            self.assertFalse(got["passed"])
            self.assertTrue(got["why"].startswith(why), (got["why"], why))
            self.assertIsNone(got["look"])
        self.assertTrue(self.judge(run=self.look_run(k=1))["passed"])

    def test_the_placebo_block_must_be_the_receipts_draw_under_the_fixed_seed(self):
        ts = [self.t_h - 1.0] * self.rc.placebo_draws
        good = placebo_block(ts, self.rc)
        spans = lambda **h: {"V": good["spans"]["V"], "H": {**good["spans"]["H"], **h}}      # noqa: E731
        cases = [
            (None, "the placebo block: the run carries no placebo block"),
            ("block", "the placebo block: the run carries no placebo block"),
            ({**good, "n": 998}, "the placebo block: 998 draws"),
            (placebo_block(ts[:-1], self.rc), "the placebo block: 998 draws"),
            (placebo_block(ts + [0.0], self.rc), "the placebo block: 1000 draws"),
            ({**good, "n": True}, "the placebo block: True draws"),
            ({**good, "seed": good["seed"] + 1}, "the placebo block: drawn under another seed"),
            ({**good, "seed": None}, "the placebo block: drawn under another seed"),
            (placebo_block(ts, self.rc, code="f" * 64), "the placebo block: drawn under another seed"),
            (placebo_block(ts, dataclasses.replace(self.rc, receipt_sha256="0" * 64)),
             "the placebo block: drawn under another seed"),
            ({**good, "spans": {"V": good["spans"]["V"]}}, "the placebo block: no t for every draw"),
            ({**good, "spans": None}, "the placebo block: no t for every draw"),
            ({**good, "spans": spans(t=ts[:-1])}, "the placebo block: no t for every draw"),
            ({**good, "spans": spans(t="ts")}, "the placebo block: no t for every draw"),
            ({**good, "spans": spans(days=len(H_DAYS) - 1)}, "the placebo block: read on 193 sessions"),
            ({**good, "spans": spans(days=None)}, "the placebo block: read on None sessions"),
            ({**good, "spans": spans(days=[d.isoformat() for d in H_DAYS[:-1]])}, "the placebo block: read on 193"),
            ({**good, "spans": spans(t=["1.0"] + ts[1:])}, "the placebo block: a placebo t that is no number"),
            ({**good, "spans": spans(t=[True] + ts[1:])}, "the placebo block: a placebo t that is no number"),
        ]
        for block, why in cases:
            run = self.look_run()
            run["placebo"] = block
            got = self.judge(run=run)
            self.assertFalse(got["passed"], why)
            self.assertTrue(got["why"].startswith(why), (got["why"], why))
            self.assertIsNone(got["look"], "no leg is judged without the receipt's own draw")
        for code in (None, "f" * 63, 7):
            got = self.judge(code_sha256=code)
            self.assertTrue(got["why"].startswith("the placebo block: the program code's sha256"), got["why"])
        # the seed as a string (a JSON store may hand a 128-bit integer back so), and the sessions listed
        as_text = {**good, "seed": str(good["seed"]), "spans": spans(days=[d.isoformat() for d in H_DAYS])}
        run = self.look_run()
        run["placebo"] = json.loads(json.dumps(as_text))
        self.assertTrue(self.judge(run=run)["passed"])
        # an undefined placebo t (None, or not a finite number) is not above
        holes = placebo_block([None, float("nan")] * 400 + [self.t_h + 1.0] * 119 + [0.0] * 80, self.rc)
        got = self.judge(run=self.look_run(block=holes))
        self.assertEqual((got["count"], got["passed"]), (119, True))

    def test_each_leg_of_the_look_alone(self):
        draws = self.rc.placebo_draws
        self.assertEqual(self.judge(run=self.look_run(self.rows(x15=self.x - 1e-2)))["why"], "the look: sum_h15")
        crowd = placebo_block([self.t_h] * 120 + [0.0] * (draws - 120), self.rc)
        got = self.judge(run=self.look_run(block=crowd))
        self.assertEqual((got["why"], got["count"], got["p_plac"]), ("the look: placebo", 120, 121 / (draws + 1)))
        at_bar = placebo_block([self.t_h] * 119 + [0.0] * (draws - 119), self.rc)
        self.assertTrue(self.judge(run=self.look_run(block=at_bar))["passed"])
        loses = np.concatenate([self.xv, -self.xh])
        got = self.judge(run=self.look_run(daily(V_DAYS + H_DAYS, x=loses)))
        self.assertEqual(got["why"], "the look: sum_h, sum_h15, t_H, placebo")
        flat = np.concatenate([self.xv, np.full(len(H_DAYS), 0.001)])
        got = self.judge(run=self.look_run(daily(V_DAYS + H_DAYS, x=flat)))
        self.assertEqual((got["why"], got["t_H"], got["count"]), ("the look: t_H, placebo", None, None))
        negative_v = np.concatenate([-self.xv, self.xh])
        got = self.judge(run=self.look_run(daily(V_DAYS + H_DAYS, x=negative_v)))
        self.assertEqual(got["why"], "the pre-check: sum_positive")

    def test_it_never_raises_after_a_receipt(self):
        """A look is spent by the time the verdict is asked: whatever cannot be read fails the program closed."""
        good = self.look_run()
        junk_rows = copy.deepcopy(good["daily"])
        junk_rows[5][2] = float("nan")
        runs = [None, {}, [], "run", 7, {**good, "daily": None}, {**good, "daily": []}, {**good, "daily": junk_rows},
                {**good, "daily": good["daily"][:300]}, {**good, "daily": [["2025-01-02"]]},
                {k: v for k, v in good.items() if k != "daily"}]
        for run in runs:
            got = self.judge(run=run)
            self.assertEqual(got["passed"], False, run if not isinstance(run, dict) else sorted(run))
            self.assertTrue(got["why"])
            self.assertEqual(got["label"], "unmeasured")
            self.assertIn("style-open", got["flags"], "a flag is never lost to a run that cannot be read")
        unread = self.judge(run={**good, "daily": junk_rows})
        self.assertTrue(unread["why"].startswith("the windows: the look's series cannot be read"), unread["why"])
        short = self.judge(run={**good, "daily": good["daily"][:300]})
        self.assertTrue(short["why"].startswith("the windows: the holdout is not the 194 sessions"), short["why"])
        for french in ("french", 7, {"days": 3}, {"factors": {}}, {"days": None, "factors": {"SMB": [1.0]}}):
            self.assertTrue(self.judge(french=french)["passed"], "a label that cannot be read is unmeasured, no more")

    def test_days_after_the_cap_are_never_judged(self):
        """The look's run ends at the holdout's last session: a forward day in it is a mis-sliced run."""
        after = [day for day, _ in nyse_sessions(e1.LOOK_CAP + dt.timedelta(days=1), dt.date(2026, 10, 30))][:3]
        rows = daily(V_DAYS + H_DAYS + after, x=np.concatenate([self.x, np.full(3, 0.5)]))
        got = self.judge(run=self.look_run(rows))
        self.assertFalse(got["passed"])
        self.assertTrue(got["why"].startswith("the windows: the look's series cannot be read (3 session(s) in neither"))


# ================================================================================================ the labels beside
class TheLabels(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(8)
        self.n = len(V_DAYS) + len(H_DAYS)
        self.x = exact(rng, self.n, 0.001)
        self.rng = rng

    def french(self, days, columns) -> dict:
        return {"days": [d.isoformat() for d in days],
                "factors": {name: np.asarray(columns[i], dtype=np.float64).tolist()
                            for i, name in enumerate(screen.FRENCH_FACTORS)}}

    def test_the_basket_share(self):
        cases = [(0.0020, "basket-led"), (0.0005, "selection-led"), (-0.001, "selection-led")]
        for per_day, label in cases:
            rows = daily(V_DAYS + H_DAYS, x=self.x, bench=np.full(self.n, per_day))
            got = screen.labels({"daily": rows})
            self.assertEqual((got["basket"], got["label"], got["loadings"], got["french_days"]),
                             (label, "unmeasured", {}, 0))
            self.assertEqual(got["sum_x"], math.fsum(self.x.tolist()))
        equal = daily(V_DAYS + H_DAYS, x=self.x, bench=self.x)
        self.assertEqual(screen.labels({"daily": equal})["basket"], "basket-led", "at least the sum of x")
        self.assertEqual(screen.BASKET_LABELS, ("basket-led", "selection-led"))
        with self.assertRaises(ValueError):
            screen.labels({"daily": []})

    def factors(self, n):
        return [0.01 * (self.rng.random(n) - 0.5) for _ in screen.FRENCH_FACTORS]

    def test_the_french_label(self):
        """A residual made orthogonal to the five factors and the constant loads on none; a loading planted on one
        or two of them is named, in the factors' own order, whatever its sign."""
        days = V_DAYS + H_DAYS
        columns = self.factors(self.n)
        noise = 0.001 * (self.rng.random(self.n) - 0.5)
        design = np.column_stack([np.ones(self.n), *columns])
        clean = noise - design @ np.linalg.lstsq(design, noise, rcond=None)[0]
        rows = lambda x: {"daily": daily(days, x=x)}                         # noqa: E731
        none = screen.labels(rows(clean), french=self.french(days, columns))
        self.assertEqual((none["label"], none["french_days"]), ("no style loading found", self.n))
        self.assertTrue(all(abs(none["loadings"][name]["t"]) < 1e-6 for name in screen.FRENCH_FACTORS))
        got = screen.labels(rows(clean + 0.3 * columns[1]), french=self.french(days, columns))
        self.assertEqual((got["label"], got["french_days"]), ("style-loaded: SMB", self.n))
        self.assertGreater(abs(got["loadings"]["SMB"]["t"]), 10.0)
        self.assertAlmostEqual(got["loadings"]["SMB"]["b"], 0.3, delta=1e-9)
        two = screen.labels(rows(clean - 0.3 * columns[4] + 0.2 * columns[0]), french=self.french(days, columns))
        self.assertEqual(two["label"], "style-loaded: Mkt-RF, ST_Rev", "in the factors' own order, either sign")
        self.assertLess(two["loadings"]["ST_Rev"]["t"], -10.0)
        # the bar is |t| >= 2.0, on the loadings' own t
        for name in screen.FRENCH_FACTORS:
            t = got["loadings"][name]["t"]
            self.assertEqual(abs(t) >= screen.FRENCH_T, name == "SMB", name)
        self.assertEqual(screen.flags_of(receipt(), none["label"]), ["X3: FAKE: an invented flag"])
        self.assertEqual(screen.flags_of(receipt(), got["label"]), ["X3: FAKE: an invented flag", "style-open"])
        self.assertEqual(screen.flags_of(receipt(), "unmeasured")[-1], "style-open")
        self.assertEqual(screen.flags_of(receipt(), None)[-1], "style-open")
        self.assertEqual(screen.flags_of(receipt(screen_flags=(), flags={}), "unmeasured"), [])

    def test_fewer_than_120_covered_days_is_unmeasured(self):
        days = V_DAYS + H_DAYS
        columns = self.factors(self.n)
        x = 0.001 * (self.rng.random(self.n) - 0.5) + 0.3 * columns[1]
        result = {"daily": daily(days, x=x)}
        for covered, measured in ((screen.FRENCH_MIN_DAYS - 1, False), (screen.FRENCH_MIN_DAYS, True)):
            part = self.french(days[:covered], [c[:covered] for c in columns])
            got = screen.labels(result, french=part)
            self.assertEqual((got["label"] != "unmeasured", got["french_days"]), (measured, covered))
        # days the release covers outside V and H are not read; a missing factor, or one with a hole, is not either
        early = [day for day, _ in nyse_sessions(dt.date(2024, 1, 2), dt.date(2024, 12, 31))]
        outside = self.french(early + days[:50], [np.concatenate([np.zeros(len(early)), c[:50]]) for c in columns])
        self.assertEqual(screen.labels(result, french=outside)["label"], "unmeasured")
        whole = self.french(days, columns)
        lacking = {**whole, "factors": {k: v for k, v in whole["factors"].items() if k != "Mom"}}
        self.assertEqual(screen.labels(result, french=lacking)["label"], "unmeasured")
        ragged = {**whole, "factors": {**whole["factors"], "Mom": whole["factors"]["Mom"][:-1]}}
        self.assertEqual(screen.labels(result, french=ragged)["label"], "unmeasured")
        holed = copy.deepcopy(whole)
        for i in range(self.n - screen.FRENCH_MIN_DAYS + 1):
            holed["factors"]["HML"][i] = float("nan")
        self.assertEqual(screen.labels(result, french=holed)["french_days"], screen.FRENCH_MIN_DAYS - 1)
        collinear = copy.deepcopy(whole)
        collinear["factors"]["HML"] = collinear["factors"]["SMB"]
        self.assertEqual(screen.labels(result, french=collinear)["label"], "unmeasured")
        for french in (None, {}, {"days": [], "factors": {}}, "french"):
            self.assertEqual(screen.labels(result, french=french)["label"], "unmeasured")

    def test_the_loadings_are_ordinary_least_squares(self):
        n, names = 300, ("a", "b", "c")
        f = np.column_stack([0.02 * (self.rng.random(n) - 0.5) for _ in names])
        y = 0.0004 + f @ np.array([0.5, -1.25, 0.0]) + 0.003 * (self.rng.random(n) - 0.5)
        got = screen.loadings(y, f, names)
        self.assertEqual(list(got), ["alpha", *names])
        design = np.column_stack([np.ones(n), f])
        beta, *_ = np.linalg.lstsq(design, y, rcond=None)
        resid = y - design @ beta
        cov = (resid @ resid) / (n - 4) * np.linalg.inv(design.T @ design)
        ts = beta / np.sqrt(np.diag(cov))
        self.assertAlmostEqual(got["alpha"]["a"], beta[0], delta=1e-12)
        self.assertAlmostEqual(got["alpha"]["t"], ts[0], delta=1e-7)
        for j, name in enumerate(names, start=1):
            self.assertAlmostEqual(got[name]["b"], beta[j], delta=1e-10)
            self.assertAlmostEqual(got[name]["t"], ts[j], delta=1e-7)
        # the t does not hang on a factor's unit (the library prints percent)
        scaled = screen.loadings(y, f * 100.0, names)
        for name in names:
            self.assertAlmostEqual(scaled[name]["t"], got[name]["t"], delta=1e-7)
            self.assertAlmostEqual(scaled[name]["b"] * 100.0, got[name]["b"], delta=1e-10)
        perfect = screen.loadings(0.001 + f @ np.array([1.0, 2.0, 3.0]), f, names)
        self.assertTrue(all(perfect[name]["t"] is None or abs(perfect[name]["t"]) > 1e6 for name in names))

    def test_loadings_that_cannot_be_formed_raise(self):
        n = 50
        f = np.column_stack([self.rng.random(n), self.rng.random(n)])
        y = self.rng.random(n)
        bad = [(y, f[:, :1], ("a", "b")), (y[:-1], f, ("a", "b")), (y, f, ("a", "a")), (y, f, ("alpha", "b")),
               (y, f, ()), (y, np.column_stack([f[:, 0], f[:, 0]]), ("a", "b")), (y, f * 0.0, ("a", "b")),
               (y[:3], f[:3], ("a", "b")), (np.where(np.arange(n) == 4, np.nan, y), f, ("a", "b")),
               (y, np.where(np.arange(n)[:, None] == 4, np.inf, f), ("a", "b")), (y, f.ravel(), ("a", "b"))]
        for x, factors, names in bad:
            with self.assertRaises(ValueError):
                screen.loadings(x, factors, names)

    def test_the_newey_west_t_beside(self):
        """Bartlett weights, five lags, written out: for a series with no serial dependence it is near the plain t."""
        x = self.x[:194]
        n, m = len(x), float(np.mean(x))
        d = x - m
        s = float(d @ d) / n + sum(2.0 * (1.0 - lag / 6.0) * float(d[lag:] @ d[:-lag]) / n for lag in range(1, 6))
        self.assertAlmostEqual(screen._t_nw(x), m / math.sqrt(s / n), delta=1e-9)
        self.assertAlmostEqual(screen._t_nw(x), screen.holdout_t(x), delta=0.35 * abs(screen.holdout_t(x)))
        self.assertIsNone(screen._t_nw(np.zeros(50)))
        self.assertIsNone(screen._t_nw(np.array([1.0])))
        self.assertIsNone(screen._t_nw(np.array([1.0, float("nan"), 2.0])))


# ====================================================================================================== the lineage
class TheLineage(unittest.TestCase):
    """4.6: the same template, or 0.7 or more in the residual x OR in the universe excess u; no Validation-only
    retry; one look, only after a passed pre-check."""

    def setUp(self):
        rng = np.random.default_rng(12)
        self.n = 700
        self.days = [day for day, _ in nyse_sessions(*e1.TRAIN_ERA_SEGMENTS[1])][:self.n]
        self.a, self.b, self.c = (rng.random(self.n) - 0.5 for _ in range(3))

    def test_either_series_binds(self):
        near = 0.9 * self.a + 0.1 * self.b
        self.assertTrue(screen.same_lineage(self.a, self.b, near, self.c), "the residual correlates")
        self.assertTrue(screen.same_lineage(self.a, self.b, self.c, 0.9 * self.b + 0.1 * self.a),
                        "two variants that hold other names: x does not correlate, their shared tilt (u) does")
        self.assertFalse(screen.same_lineage(self.a, self.b, self.c, self.c))
        self.assertTrue(screen.same_lineage(self.a, self.b, self.c, self.c, same_template=True))
        self.assertTrue(screen.same_lineage(None, None, None, None, same_template=True))
        self.assertFalse(screen.same_lineage(self.a, self.b, -self.a, -self.b), "a mirror is not the same lineage")

    def test_it_is_e1s_correlation_on_each_series(self):
        for scale in (0.3, 0.5, 0.7, 0.9, 1.1, 1.5):
            other = self.a + scale * self.b
            want = s2.same_lineage(self.a, other)
            self.assertEqual(screen.same_lineage(self.a, self.c, other, self.b), want, scale)
            self.assertEqual(screen.same_lineage(self.c, self.a, self.b, other), want, scale)
        self.assertEqual(screen.SAME_LINEAGE_CORR, s2.SAME_LINEAGE_CORR)
        self.assertEqual(screen.LINEAGE_SERIES, ("x", "u"))

    def test_series_by_session_are_aligned_on_their_common_days(self):
        x = make_series(self.days, self.a)
        u = make_series(self.days, self.b)
        shifted = make_series(self.days[100:], self.a[100:])               # the same program over a later start
        other_u = {d.isoformat(): float(v) for d, v in zip(self.days, self.c)}
        self.assertTrue(screen.same_lineage(x, u, shifted, other_u))
        self.assertFalse(screen.same_lineage(x, u, make_series(self.days, self.c), other_u))

    def test_a_no_needs_both_series_read(self):
        with self.assertRaises(ValueError):
            screen.same_lineage(self.a, None, self.c, self.b)
        with self.assertRaises(ValueError):
            screen.same_lineage(self.a, self.b, self.c, self.b[:-1])
        with self.assertRaises(ValueError):
            screen.same_lineage(self.a, self.b, self.c[:-1], self.b)
        self.assertTrue(screen.same_lineage(self.a, None, self.a, None), "the residual already binds")

    def test_no_validation_only_retry_and_one_look(self):
        rc = receipt()
        self.assertIs(rc.retry, False)
        for facts in ({}, {"first_precheck_failed": True}, {"first_precheck_failed": True, "tries": 1, "looks": 0},
                      {"retry_sha": "a", "recorded_sha": "a", "first_precheck_failed": True}):
            self.assertIs(screen.retry_permitted(rc, **facts), False)
        self.assertIs(screen.retry_permitted(), False)
        self.assertIs(screen.retry_permitted(None), False)
        self.assertEqual((screen.VALIDATION_TRIES, screen.LOOKS_PER_LINEAGE), (rc.validation_tries, rc.holdout_looks))
        self.assertTrue(screen.look_permitted(0, precheck_passed=True))
        self.assertFalse(screen.look_permitted(1, precheck_passed=True), "one look a lineage")
        self.assertFalse(screen.look_permitted(0, precheck_passed=False), "a failed pre-check spends no look")
        self.assertFalse(screen.look_permitted(0, precheck_passed=None))


# ===================================================================================================== the sentence
class TheSentence(unittest.TestCase):
    def setUp(self):
        self.rc = receipt()
        self.verdict = {"screen": "XS1", "passed": True, "c_used": 1.35, "c_p": 1.3, "own_fp": 0.01397,
                        "basket": "selection-led", "label": "unmeasured", "flags": ["style-open"]}

    def test_every_placeholder_is_filled(self):
        line = screen.beside_line(self.verdict, self.rc, n_cell=1)
        self.assertEqual(line, self.rc.beside.replace("{c_used}", "1.35").replace("{c_p}", "1.30")
                         .replace("{own_fp}", "1.40").replace("{n_cell}", "1").replace("{basket}", "selection-led")
                         .replace("{label}", "unmeasured").replace("{flags}", "style-open"))
        for field in screen.BESIDE_FIELDS:
            self.assertNotIn("{" + field + "}", line)
        many = screen.beside_line({**self.verdict, "flags": ["X3: a flag", "style-open"], "label": "style-loaded: SMB"},
                                  self.rc, n_cell=0)
        self.assertIn("flags: X3: a flag; style-open.", many)
        self.assertIn("French factors: style-loaded: SMB;", many)
        self.assertIn("cell: 0;", many)
        self.assertIn("flags: none.", screen.beside_line({**self.verdict, "flags": []}, self.rc, n_cell=2))
        self.assertEqual(screen.BESIDE_FIELDS, ("c_used", "c_p", "own_fp", "n_cell", "basket", "label", "flags"))

    def test_a_pass_is_never_stated_with_a_hole(self):
        for over in ({"c_used": None}, {"c_used": 1.355}, {"c_p": None}, {"own_fp": None}, {"own_fp": 1.2},
                     {"basket": None}, {"basket": "both"}, {"label": None}, {"label": " "}, {"flags": None},
                     {"flags": "style-open"}, {"flags": [1]}, {"flags": [""]}):
            with self.assertRaises(ValueError, msg=over):
                screen.beside_line({**self.verdict, **over}, self.rc, n_cell=0)
            unknown = {k: v for k, v in {**self.verdict, **over}.items() if k != "passed"}
            with self.assertRaises(ValueError, msg=over):
                screen.beside_line(unknown, self.rc, n_cell=0)
        for n_cell in (None, -1, 1.5, "1", True):
            with self.assertRaises(ValueError, msg=n_cell):
                screen.beside_line(self.verdict, self.rc, n_cell=n_cell)
        with self.assertRaises(ValueError):
            screen.beside_line({**self.verdict, "screen": "S2"}, self.rc, n_cell=0)
        with self.assertRaises(ValueError):
            screen.beside_line(None, self.rc, n_cell=0)
        with self.assertRaises(ValueError):
            screen.beside_line(self.verdict, dataclasses.replace(self.rc, beside="XS1, bar {c_used}"), n_cell=0)

    def test_a_failed_verdict_reads_unmeasured_where_it_lacks_a_figure(self):
        """A look is spent either way and its record keeps the sentence: a verdict that did not pass has no trade to
        stand beside, so a figure it lacks reads "unmeasured" and the House's record of the look never fails."""
        failed = {"screen": "XS1", "passed": False, "why": "the floor: no floor cell", "c_used": None, "c_p": None,
                  "own_fp": None, "basket": None, "label": "unmeasured", "flags": ["style-open"]}
        line = screen.beside_line(failed, self.rc, n_cell=3)
        self.assertEqual(line, self.rc.beside.replace("{c_used}", "unmeasured").replace("{c_p}", "unmeasured")
                         .replace("{own_fp}", "unmeasured").replace("{n_cell}", "3").replace("{basket}", "unmeasured")
                         .replace("{label}", "unmeasured").replace("{flags}", "style-open"))
        with self.assertRaises(ValueError):
            screen.beside_line(failed, self.rc, n_cell=None)

    def test_a_verdict_and_its_sentence(self):
        """From a judged run to the line a report prints: every figure the verdict's own."""
        rng = np.random.default_rng(21)
        x = np.concatenate([exact(rng, len(V_DAYS), 0.0012), exact(rng, len(H_DAYS), 0.0024)])
        fl = floor_of(self.rc, k_p=140)
        run = run_of(daily(V_DAYS + H_DAYS, x=x), placebo_block([0.0] * self.rc.placebo_draws, self.rc), self.rc)
        got = screen.verdict(run, receipt=self.rc, program_floor=fl, code_sha256=CODE)
        self.assertTrue(got["passed"])
        line = screen.beside_line(got, self.rc, n_cell=1)
        for words in (f"t >= {fl['c_used']:.2f}", f"own floor {fl['c_p']:.2f} + 0.05",
                      f"holdout-only rate is {100 * fl['own_fp']:.2f}%", "cell: 1;", "its P&L is selection-led",
                      "French factors: unmeasured", "flags: X3: FAKE: an invented flag; style-open."):
            self.assertIn(words, line)


if __name__ == "__main__":
    unittest.main()
