"""POOL1's rule (league/ops/pool_rule.py, the owner's A55 as pre-registered in A55a): the pin and the receipt it pins,
the House-set cell key, the per-symbol timing alpha, the own floor under N0, N0R and N1 against brute force (a cell
and a cluster, with the bootstrap bound), the clusters, the caps, the zeroed-days void, stage 1, the placebo leg, the
demotion, the route and the words.

Every input is synthetic (numpy `default_rng` streams); no market data, no real figure, no POOL1 figure."""

from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import math
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path
from unittest import mock

import numpy as np

from league.ops import fwd1_rule as F
from league.ops import pool_rule as P

REPO = Path(__file__).resolve().parents[2]
POLICY = REPO / "league" / "swarm" / "policy.json"


def pin_block(sha: str = "a" * 64) -> dict:
    """A pin block carrying every constant as this code holds it."""
    return {"name": P.NAME, "prereg_sha256": P.PREREG_SHA256, "receipt_sha256": sha, **copy.deepcopy(P.CONSTANTS)}


def receipt_doc(*, cells: dict | None = None, u: dict | None = None, rho: float = 0.2, c_G: float = 1.7,
                floor: str = "R-REG", margin: float = 0.03) -> dict:
    """An INVENTED receipt of POOL1's shape (`pool_rule.RECEIPT_KEYS`): founders "equity:<cell>-<i>", pids 100+."""
    cells = cells or {"trend_momentum/sectors": ("trend_momentum", 4), "trend_momentum/index": ("trend_momentum", 3),
                      "reversal_liquidity/index": ("reversal_liquidity", 3)}
    founders, units, clusters = {}, {}, {}
    pid = 100
    for cell, (cid, m) in cells.items():
        cls, grp = cell.split("/")
        for i in range(m):
            founders[f"equity:{cell.replace('/', '-')}-{i}"] = {"pid": pid, "class": cls, "group": grp, "cell": cell,
                                                               "why": None, "merged_into": None}
            pid += 1
        units[cell] = {"class": cls, "group": grp, "cluster": cid, "stage1": {"refuted": False, "z": [0.5, 0.2]}}
        clusters.setdefault(cid, {"cells": [], "u": {str(k): list((u or {}).get(cid, (0.02, 0.03))) for k in P.U_COUNTS}})
        clusters[cid]["cells"].append(cell)
    founders["equity:out-0"] = {"pid": pid, "class": "event_premium", "group": "index", "cell": None,
                                "why": "an event reader", "merged_into": None}
    return {"name": P.NAME, "prereg_sha256": P.PREREG_SHA256,
            "calibration": {"code_sha256": "b" * 64, "decision_sha256": "c" * 64},
            "decision": {"floor": floor, "margin": margin, "c_G": c_G}, "rho_assign": rho,
            "regimes": {"vol": [0.009, 0.011], "ret": [0.0, 0.05], "disp": [0.011, 0.013], "tltgld": [-0.02, 0.02]},
            "founders": founders, "units": units, "clusters": clusters,
            "matched_floor": {g: {c: {str(m): 150 for m in (3, 4, 7, 10, 15)} for c in
                                  ("trend_momentum", "reversal_liquidity", "relative_value", "calendar_flow")}
                              for g in P.BASE_GROUPS},
            "beside": {cid: {k: 0.05 for k in P.BESIDE_KEYS} for cid in clusters},
            "expected": {cid: [0.04, 0.07, 0.1] for cid in clusters}}


def receipt(**kw) -> P.Receipt:
    rec, why = P.parse_receipt(receipt_doc(**kw), "d" * 64)
    assert rec is not None, why
    return rec


def sessions(first: str, n: int) -> tuple[str, ...]:
    day, out = dt.date.fromisoformat(first), []
    while len(out) < n:
        if day.weekday() < 5:
            out.append(day.isoformat())
        day += dt.timedelta(days=1)
    return tuple(out)


def synthetic_unit(seed: int = 3, *, eras=(400, 420), cells=("trend_momentum/sectors", "trend_momentum/index"), m=2,
                   joins=None, S=2):
    """INVENTED members and markets for the own floor: each member's per-symbol weights and returns, its frozen
    constants and a join offset; each era's market (SPY, sectors, TLT, GLD)."""
    rng = np.random.default_rng([seed, 2026, 1016])
    markets, era_R = [], []
    for e, n in enumerate(eras):
        days = sessions("2016-01-04" if e == 0 else "2022-01-03", n)
        spy = rng.normal(0.0004, 0.01, n)
        markets.append(P.Market(days=days, spy=spy, sectors=rng.normal(0.0003, 0.012, (4, n)),
                                tlt=rng.normal(0, 0.008, n), gld=rng.normal(0, 0.009, n)))
        era_R.append((days, np.vstack([spy, rng.normal(0.0002, 0.012, (S - 1, n))])))
    members = []
    for ci, cell in enumerate(cells):
        for j in range(m):
            eras_ = []
            for days, R in era_R:
                n = len(days)
                ws = np.abs(rng.normal(0.2, 0.1, (S, n))) * (rng.random((S, n)) < 0.5)
                rg = (ws * R).sum(axis=0) + rng.normal(0, 0.002, n) - 2e-5
                eras_.append(P.Era(days=days, rg=rg, gap=np.full(n, 1e-5), ws=ws, R=R, hs=np.full(S, 3e-4)))
            mu = np.concatenate([e.R for e in eras_], axis=1).mean(axis=1)
            wbar = np.concatenate([e.ws for e in eras_], axis=1).mean(axis=1)
            sigma = P.train_sigma([(e.rg, e.gap, e.ws, e.R) for e in eras_], mu, wbar)
            join = 0 if joins is None else joins[ci * m + j]
            members.append(P.FloorMember(key=f"L{ci}{j}", cell=cell, join=join, mu=mu, wbar=wbar,
                                         sigma=P.sigma_used(sigma, None), g=2e-4, eras=tuple(eras_)))
    return members, markets


CUTS = {"vol": (0.0095, 0.0105), "ret": (0.02, 0.06), "disp": (0.0118, 0.0122), "tltgld": (-0.02, 0.02)}


# ------------------------------------------------------------------------------------------------------- the pin
class ThePin(unittest.TestCase):
    def test_the_exact_block_loads(self):
        held, why = P.load(pin_block())
        self.assertIsNone(why)
        self.assertEqual(held.receipt_sha256, "a" * 64)

    def test_every_refusal(self):
        self.assertEqual(P.load({})[0], None)
        self.assertIn("no pooled screen is pinned", P.load(None)[1])
        for key in P.PIN_KEYS:
            block = pin_block()
            del block[key]
            with self.subTest(missing=key):
                self.assertIsNone(P.load(block)[0])
        self.assertIsNone(P.load({**pin_block(), "name": "POOL2"})[0])
        self.assertIsNone(P.load({**pin_block(), "prereg_sha256": "e" * 64})[0])
        for bad in ("A" * 64, "a" * 63, 12, None):
            self.assertIsNone(P.load({**pin_block(), "receipt_sha256": bad})[0])

    def test_no_constant_can_move(self):
        """A pin moves no bar, cap, plan or rule: every constant of the code, changed, is refused."""
        def changed(value):
            if isinstance(value, bool):
                return not value
            if isinstance(value, (int, float)):
                return value + 1
            if isinstance(value, str):
                return value + "x"
            if isinstance(value, list):
                return value[:-1] if value else [1]
            if isinstance(value, dict):
                k = sorted(value)[0]
                return {**value, k: changed(value[k])}
            raise AssertionError(value)

        for key, value in P.CONSTANTS.items():
            with self.subTest(key=key):
                held, why = P.load({**pin_block(), key: changed(value)})
                self.assertIsNone(held)
                self.assertIn(key, why)

    def test_the_branch_pins_nothing_until_the_receipt_ships(self):
        """P1 is built before the calibration (DEVIATIONS.log D1): the repository's policy.json carries no POOL1 pin, so
        the job judges nothing. Once a pin ships, its receipt must be the file at RECEIPT_PATH by sha256 and parse
        whole (the conformance check CI holds, as fwd1_rule's)."""
        policy = json.loads(POLICY.read_text())
        block = P.pin(policy)
        receipt_path = REPO / P.RECEIPT_PATH
        if not block:
            self.assertIsNone(P.rule(policy, repo=REPO)[0])
            self.assertIn("no pooled screen is pinned", P.rule(policy, repo=REPO)[1])
            return
        held, why = P.load(block)
        self.assertIsNotNone(held, why)
        self.assertTrue(receipt_path.exists())
        self.assertEqual(hashlib.sha256(receipt_path.read_bytes()).hexdigest(), held.receipt_sha256)
        rec, why = P.rule(policy, repo=REPO)
        self.assertIsNotNone(rec, why)

    def test_policy_ships_record_with_seats_off(self):
        policy = json.loads(POLICY.read_text())
        self.assertEqual(policy["elane"]["pool"]["mode"], "record")
        self.assertEqual(policy["elane"]["pool"]["seats"], "off")


class TheReceipt(unittest.TestCase):
    def test_a_whole_receipt_parses(self):
        rec = receipt()
        self.assertEqual(rec.floor, "R-REG")
        self.assertEqual(rec.c_G, 1.7)
        self.assertEqual(set(rec.units), {"trend_momentum/sectors", "trend_momentum/index", "reversal_liquidity/index"})
        self.assertEqual(rec.cluster_of("trend_momentum/index"), "trend_momentum")
        self.assertEqual(len(rec.units["trend_momentum/sectors"].founders), 4)
        self.assertNotIn("equity:out-0", rec.units["trend_momentum/index"].founders)

    def test_refused_whole_on_any_defect(self):
        cases = {
            "no rule": lambda d: d.__setitem__("decision", None),
            "floor": lambda d: d["decision"].__setitem__("floor", "LOOSE"),
            "margin": lambda d: d["decision"].__setitem__("margin", 0.02),
            "c_G off grid": lambda d: d["decision"].__setitem__("c_G", 1.705),
            "c_G range": lambda d: d["decision"].__setitem__("c_G", 1.30),
            "rho": lambda d: d.__setitem__("rho_assign", 1.5),
            "prereg": lambda d: d.__setitem__("prereg_sha256", "0" * 64),
            "cut": lambda d: d["regimes"].__setitem__("vol", [0.02, 0.01]),
            "few founders": lambda d: [d["founders"].pop(k) for k in list(d["founders"]) if "reversal" in k][:1],
            "u table": lambda d: d["clusters"]["trend_momentum"]["u"].pop("60"),
            "u bound": lambda d: d["clusters"]["trend_momentum"]["u"].__setitem__("0", [0.05, 0.04]),
            "cell": lambda d: d["founders"]["equity:out-0"].__setitem__("cell", "x/stocks"),
            "expected": lambda d: d["expected"].__setitem__("trend_momentum", [0.1, 0.05, 0.2]),
            "matched": lambda d: d["matched_floor"]["sectors"].pop("trend_momentum"),
        }
        for name, change in cases.items():
            doc = receipt_doc()
            change(doc)
            with self.subTest(defect=name):
                self.assertIsNone(P.parse_receipt(doc, "d" * 64)[0])
        self.assertIn("adopted no rule", P.parse_receipt({**receipt_doc(), "decision": None}, "d" * 64)[1])

    def test_read_only_at_the_pins_sha(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pool_screen_1.json"
            raw = json.dumps(receipt_doc()).encode()
            path.write_bytes(raw)
            ok, why = P.load_receipt(path, P.Pin(hashlib.sha256(raw).hexdigest()))
            self.assertIsNotNone(ok, why)
            self.assertIsNone(P.load_receipt(path, P.Pin("f" * 64))[0])
            self.assertIsNone(P.load_receipt(Path(tmp) / "absent.json", P.Pin("f" * 64))[0])

    def test_u_at_takes_the_count_read_or_the_next_larger(self):
        doc = receipt_doc()
        doc["clusters"]["trend_momentum"]["u"] = {str(k): [0.01 * i, 0.01 * i + 0.01] for i, k in enumerate(P.U_COUNTS)}
        rec, _ = P.parse_receipt(doc, "d" * 64)
        self.assertEqual(rec.u_at("trend_momentum", 5), (0.01, 0.02))
        self.assertEqual(rec.u_at("trend_momentum", 7), (0.02, 0.03))           # between 5 and 10: 10's row
        self.assertEqual(rec.u_at("trend_momentum", 60), (0.07, 0.08))
        self.assertIsNone(rec.u_at("trend_momentum", 61))

    def test_the_matched_floor_takes_m_or_the_larger_neighbour(self):
        doc = receipt_doc()
        doc["matched_floor"]["sectors"]["trend_momentum"] = {"3": 150, "4": 160, "7": 140}
        rec, _ = P.parse_receipt(doc, "d" * 64)
        self.assertEqual(rec.matched("sectors", "trend_momentum", 4), 160)
        self.assertEqual(rec.matched("sectors", "trend_momentum", 5), 160)     # 4 and 7: the larger
        self.assertEqual(rec.matched("sectors", "trend_momentum", 20), 140)
        self.assertIsNone(rec.matched("sectors", "unknown_class", 4))


# ---------------------------------------------------------------------------------------------------- the cell key
class TheCellKey(unittest.TestCase):
    def test_the_group_holds_more_than_two_thirds(self):
        self.assertEqual(P.group_of({"SPY": 3.0, "XLK": 1.0}), ("index", None))
        self.assertEqual(P.group_of({"SPY": 2.0, "XLK": 1.0})[0], None)           # exactly 2/3 is not more
        self.assertEqual(P.group_of({"XLK": 5.0, "XLE": 2.0, "SPY": 1.0}), ("sectors", None))
        self.assertEqual(P.group_of({"TLT": 1.0, "GLD": 1.0}), ("defensive", None))
        self.assertIn("stocks", P.group_of({"SPY": 1.0}, ["SPY", "AAPL"])[1])
        self.assertIn("no Train-era exposure", P.group_of({"SPY": 0.0})[1])

    def test_needs_padding_and_mixed_labels_split_nothing(self):
        # NEEDS "index+sectors", held almost wholly in SPY: the index group, whatever the registry's ugroup says
        self.assertEqual(P.group_of({"SPY": 9.0, "XLK": 0.0, "XLE": 0.5}, ["SPY", "XLK", "XLE"]), ("index", None))

    def test_the_event_code_scan(self):
        self.assertTrue(P.reads_events("def decide(ctx):\n    return ctx.events['fomc']\n"))
        self.assertTrue(P.reads_events("def decide(ctx):\n    return getattr(ctx, 'events_next')\n"))
        self.assertTrue(P.reads_events("def decide(ctx):\n    return ctx['events']\n"))
        self.assertTrue(P.reads_events("def decide(ctx:\n"))                 # does not parse: an event reader
        self.assertTrue(P.reads_events(None))
        self.assertFalse(P.reads_events("def decide(ctx):\n    return ctx.bars['SPY']  # events in a comment\n"))

    def test_what_is_out(self):
        card = {"mechanism_class": "trend_momentum", "inputs": ["underlying_price"]}
        self.assertIsNone(P.excluded(panel=False, symbols=["SPY"], card=card, code="x = 1\n"))
        self.assertIn("panel", P.excluded(panel=True, symbols=["SPY"], card=card, code="x = 1\n"))
        self.assertIn("stocks", P.excluded(panel=False, symbols=["SPY", "AAPL"], card=card, code="x = 1\n"))
        self.assertIn("equity_premium", P.excluded(panel=False, symbols=["SPY"], code="x = 1\n",
                                                   card={"mechanism_class": "equity_premium"}))
        self.assertIn("event reader", P.excluded(panel=False, symbols=["SPY"], code="x = 1\n",
                                                 card={"inputs": ["event_calendar"]}))
        self.assertIn("event reader", P.excluded(panel=False, symbols=["SPY"], card=card, code="y = ctx.events\n"))
        self.assertIn("1%", P.excluded(panel=False, symbols=["SPY"], card=card, code="", mean_exposure=0.009))
        self.assertIsNone(P.excluded(panel=False, symbols=["SPY"], card=card, code="", mean_exposure=0.01))
        self.assertEqual(P.excluded(panel=False, symbols=["SPY"], card=card, code="", group_why="no group"), "no group")

    def test_the_member_is_the_first_passing_pid(self):
        rows = [{"pid": 7, "reason": "train_fail"}, {"pid": 9, "reason": "train_pass"}, {"pid": 8, "reason": "seed"}]
        self.assertEqual(P.member_pid(rows), 8)
        self.assertIsNone(P.member_pid([{"pid": 3, "reason": "train_fail"}]))


# --------------------------------------------------------------------------------------------------- the statistic
def loop_alpha(rg, gap, ws, R, mu, wbar, include=None, prior=20):
    """The PREREG's formula, one day at a time."""
    S, n = ws.shape
    inc = [True] * n if include is None else list(include)
    a, a15 = [], []
    for t in range(n):
        cnt = sum(1 for u in range(t) if inc[u])
        what = [(prior * wbar[s] + sum(ws[s, u] for u in range(t) if inc[u])) / (prior + cnt) for s in range(S)]
        v = rg[t] - sum(ws[s, t] * mu[s] for s in range(S)) - sum(what[s] * (R[s, t] - mu[s]) for s in range(S))
        a.append(v)
        a15.append(v - gap[t])
    return np.array(a), np.array(a15)


class TheStatistic(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng([7, 1016])
        self.S, self.n = 3, 60
        self.ws = np.abs(rng.normal(0.2, 0.1, (self.S, self.n))) * (rng.random((self.S, self.n)) < 0.5)
        self.R = rng.normal(0.0003, 0.01, (self.S, self.n))
        self.mu, self.wbar = self.R.mean(axis=1), self.ws.mean(axis=1)
        self.rg = (self.ws * self.R).sum(axis=0) - 1e-4 * rng.random(self.n)
        self.gap = 1e-5 * rng.random(self.n)

    def test_the_per_symbol_alpha_against_a_direct_loop(self):
        include = np.arange(self.n) % 7 != 3
        a, a15 = P.alpha(self.rg, self.gap, self.ws, self.R, self.mu, self.wbar, include=include)
        la, la15 = loop_alpha(self.rg, self.gap, self.ws, self.R, self.mu, self.wbar, include=include)
        np.testing.assert_allclose(a, la, rtol=0, atol=1e-15)
        np.testing.assert_allclose(a15, la15, rtol=0, atol=1e-15)

    def test_a_static_tilt_and_a_padded_needs_list_score_zero(self):
        tilt = np.tile(np.array([[0.4], [0.1], [0.0]]), (1, self.n))     # a static tilt; the third symbol unheld
        rg = (tilt * self.R).sum(axis=0)
        a, _ = P.alpha(rg, np.zeros(self.n), tilt, self.R, self.mu, tilt[:, 0])
        self.assertLess(float(np.abs(a).max()), 1e-15)
        # padding: an unheld symbol added to the NEEDS list changes nothing
        a2, _ = P.alpha(rg, np.zeros(self.n), tilt[:2], self.R[:2], self.mu[:2], tilt[:2, 0])
        np.testing.assert_allclose(a, a2, atol=1e-16)

    def test_one_symbol_is_the_drafts_scalar_form(self):
        w, R = self.ws[:1], self.R[:1]
        a, _ = P.alpha(self.rg, self.gap, w, R, self.mu[:1], self.wbar[:1])
        csum = np.concatenate([[0.0], np.cumsum(w[0])[:-1]])
        what = (20 * self.wbar[0] + csum) / (20 + np.arange(self.n))
        scalar = self.rg - w[0] * self.mu[0] - what * (R[0] - self.mu[0])
        np.testing.assert_allclose(a, scalar, atol=1e-16)

    def test_sigma_used_caps_a_weight_at_three_times_the_founders_median(self):
        tilde = P.sigma_tilde([0.01, 0.02, 0.04])
        self.assertAlmostEqual(tilde, 0.02)
        self.assertEqual(P.sigma_used(0.001, tilde), 0.02 / 3)
        self.assertEqual(P.sigma_used(0.0001, None), P.SIGMA_FLOOR)
        self.assertEqual(P.sigma_used(0.05, tilde), 0.05)
        self.assertLessEqual(1 / P.sigma_used(1e-9, tilde), 3 / tilde + 1e-9)

    def test_the_cell_day_and_t(self):
        z = np.array([[1.0, 0.0, 2.0], [3.0, 4.0, 0.0]])
        active = np.array([[True, True, True], [False, True, True]])
        np.testing.assert_allclose(P.cell_day(z, active), [1.0, 2.0, 1.0])
        x = list(np.random.default_rng(3).normal(0.1, 1.0, 40))
        self.assertEqual(P.t_stat(x), F.t_stat(x))
        point = P.look(x, x, 40)
        self.assertEqual(point["T"], F.t_stat(x))
        self.assertTrue(P.legs_pass({"T": 1.71, "S15": 1e-9}, 1.70))
        self.assertFalse(P.legs_pass({"T": 1.71, "S15": 1e-13}, 1.70))
        self.assertFalse(P.legs_pass({"T": None, "S15": 1.0}, 1.70))
        with self.assertRaises(ValueError):
            P.look(x[:39], x[:39], 40)

    def test_the_bar_on_the_grid(self):
        self.assertEqual(P.k_used(1.70, 0.03, 150), 170)
        self.assertEqual(P.k_used(1.70, 0.03, 180), 183)
        self.assertEqual(P.k_used(1.70, 0.05, 496), None)                      # above 5.00: ineligible
        self.assertIsNone(P.k_used(1.70, 0.0, None))

    def test_lot_exposure_is_screen_series_accounting_a_symbol(self):
        from league.equity import screen
        from league.equity.store import Bars

        rng = np.random.default_rng(3)
        n = 40
        epoch = dt.date(1970, 1, 1)
        days = np.arange(n, dtype=np.int32) + (dt.date(2022, 1, 3) - epoch).days
        syms = ("SPY", "QQQ")
        adj = {}
        for s in syms:
            c = 100 * np.cumprod(1 + rng.normal(0, 0.01, n))
            o = c * (1 + rng.normal(0, 0.002, n))
            adj[s] = np.stack([o, o, o, c], axis=1)
        bars = Bars(days=days, early=np.zeros(n, bool), first=2, symbols=syms, raw={s: np.zeros((n, 5)) for s in syms},
                    adj=adj, window="t")
        iso = [(epoch + dt.timedelta(days=int(d))).isoformat() for d in days]
        lots = [{"lid": 1, "symbol": "SPY", "weight": 0.3, "entry_day": iso[3], "entry_at": "open", "exit_day": iso[9],
                 "exit_at": "open"},
                {"lid": 2, "symbol": "QQQ", "weight": 0.2, "entry_day": iso[5], "entry_at": "close",
                 "exit_day": iso[12], "exit_at": "close"},
                {"lid": 3, "symbol": "SPY", "weight": 0.1, "entry_day": iso[1], "entry_at": "open", "exit_day": iso[4],
                 "exit_at": "close"},
                {"lid": 4, "symbol": "QQQ", "weight": 0.25, "entry_day": iso[30], "entry_at": "open", "exit_day": None}]
        whole = screen.series(lots, bars, universe=list(syms), capital=1000)
        run_days = [(epoch + dt.timedelta(days=int(d))).isoformat() for d in whole.days]
        ex = P.lot_exposure(lots, run_days, syms)
        np.testing.assert_array_equal(ex.sum(axis=0), whole.w)
        for i, s in enumerate(syms):
            one = screen.series([lot for lot in lots if lot["symbol"] == s], bars, universe=list(syms), capital=1000)
            np.testing.assert_array_equal(one.w, ex[i])
        with self.assertRaises(ValueError):
            P.lot_exposure([{**lots[0], "symbol": "IWM"}], run_days, syms)

    def test_the_series_sha_names_one_series(self):
        a = P.series_sha(["2026-10-26"], [0.1], [0.05])
        self.assertEqual(a, P.series_sha(["2026-10-26"], [0.1], [0.05]))
        self.assertNotEqual(a, P.series_sha(["2026-10-26"], [0.1 + 1e-17 * 10], [0.05]))


# ------------------------------------------------------------------------------------------------------ the floor
def brute_worlds(members, markets, null, *, L=P.WINDOW):
    """THE NULL WORLDS one window at a time (the module docstring's definitions, by loops over `P.alpha`): each
    world's best T over cells and looks, its labels and its era."""
    n0, n0r = {}, {}
    for m in members:
        allx, per_k = [], {0: [], 1: [], 2: []}
        for e, market in enumerate(markets):
            era = m.eras[e]
            a = P.alpha(era.rg, era.gap, era.ws, era.R, m.mu, m.wbar)[0]
            allx.extend(a.tolist())
            lab = P.regime_labels(P.regime_stats(market, L=L), CUTS, ("vol",))["vol"]
            for s, k in enumerate(lab):
                per_k[int(k)].extend(a[s:s + L].tolist())
        n0[m.key] = math.fsum(allx) / len(allx)
        n0r[m.key] = {k: (math.fsum(v) / len(v) if v else n0[m.key]) for k, v in per_k.items()}
    out = []
    for e, market in enumerate(markets):
        n = len(market.days)
        lab = P.regime_labels(P.regime_stats(market, L=L), CUTS, ("vol",))["vol"]
        offsets = [None] if null != "N1" else list(P.n1_offsets(n))
        for off in offsets:
            for s in range(n - L + 1):
                best = -math.inf
                for cell in sorted({m.cell for m in members}):
                    zs, z15s, joins = [], [], []
                    for m in members:
                        if m.cell != cell:
                            continue
                        era = m.eras[e] if off is None else P.n1_path(m.eras[e], off, m.g)
                        a, a15 = P.alpha(era.rg[s:s + L], era.gap[s:s + L], era.ws[:, s:s + L], era.R[:, s:s + L],
                                         m.mu, m.wbar)
                        g = n0[m.key] if null == "N0" else n0r[m.key][int(lab[s])] if null == "N0R" else 0.0
                        zs.append((a - g) / m.sigma)
                        z15s.append((a15 - g) / m.sigma)
                        joins.append(m.join)
                    D, D15 = [], []
                    for t in range(L):
                        act = [i for i, j in enumerate(joins) if t >= j]
                        D.append(math.fsum(zs[i][t] for i in act) / max(1, len(act)))
                        D15.append(math.fsum(z15s[i][t] for i in act) / max(1, len(act)))
                    for k in P.PLAN:
                        t = F.t_stat(D[:k])
                        if t is not None and math.fsum(D15[:k]) > P.ZERO:
                            best = max(best, t)
                out.append((best, s, e))
    return out


def brute_floor(Ts, cap):
    worlds = len(Ts)
    capq = Fraction(repr(float(cap)))
    for k in range(P.K_MAX + 1):
        if Fraction(sum(1 for t in Ts if F.grid_index(t if t != -math.inf else None) >= k)) <= capq * worlds:
            return k
    return None


class TheOwnFloor(unittest.TestCase):
    def test_window_alpha_is_the_loop_over_every_window(self):
        members, _ = synthetic_unit(eras=(150, 130), m=1, cells=("trend_momentum/sectors",))
        era = members[0].eras[0]
        A, A15 = P.window_alpha(era.rg, era.gap, era.ws, era.R, members[0].mu, members[0].wbar, L=30)
        for s in (0, 11, 120):
            a, a15 = P.alpha(era.rg[s:s + 30], era.gap[s:s + 30], era.ws[:, s:s + 30], era.R[:, s:s + 30],
                             members[0].mu, members[0].wbar)
            np.testing.assert_allclose(A[s], a, atol=1e-15)
            np.testing.assert_allclose(A15[s], a15, atol=1e-15)

    def test_the_worlds_against_brute_force_for_a_cell_and_a_cluster(self):
        for cells, joins in ((("trend_momentum/sectors",), None),
                             (("trend_momentum/sectors", "trend_momentum/index"), [0, 30, 0, 0])):
            members, markets = synthetic_unit(cells=cells, joins=joins)
            am, amk = P.aligned(members, markets)
            for null in P.NULLS:
                with self.subTest(cells=len(cells), null=null):
                    T, labels = P._world_T(am, amk, null, axes=P.unit_axes(cells), cuts=CUTS)
                    brute = brute_worlds(am, amk, null)
                    self.assertEqual(len(T), len(brute))
                    np.testing.assert_array_equal(P.grid(T), P.grid(np.array([b[0] for b in brute])))
                    for cap in (0.12, 0.05):
                        self.assertEqual(P.floors(P.grid(T), labels, cap)["POOLED"], brute_floor([b[0] for b in brute], cap))
                    if null == "N1":
                        self.assertEqual(len(T), sum(len(P.n1_offsets(len(m.days))) * (len(m.days) - P.WINDOW + 1)
                                                     for m in amk))

    def test_the_regime_floor_is_the_worst_regime_cell(self):
        members, markets = synthetic_unit(cells=("trend_momentum/sectors",))
        am, amk = P.aligned(members, markets)
        T, labels = P._world_T(am, amk, "N0", axes=("vol", "ret", "disp"), cuts=CUTS)
        g = P.grid(T)
        fl = P.floors(g, labels, 0.12)
        worst = 0
        for axis, lab in labels.items():
            for k in range(3):
                sel = np.asarray(lab) == k
                if sel.any():
                    worst = max(worst, brute_floor([t for t, keep in zip(T, sel) if keep], 0.12))
        self.assertEqual(fl["R-REG"], max(worst, fl["POOLED"]))
        self.assertLessEqual(set(fl["cells"]), {f"{a}{k}" for a in ("vol", "ret", "disp") for k in range(3)})
        self.assertEqual({c[:-1] for c in fl["cells"]}, {"vol", "ret", "disp"})   # a regime cell with no world sets none
        self.assertEqual(P.unit_axes(["a/index"]), ("vol", "ret"))
        self.assertEqual(P.unit_axes(["a/index", "b/defensive"]), ("vol", "ret", "tltgld"))

    def test_n1_kills_timing_and_keeps_the_path(self):
        members, _ = synthetic_unit(eras=(400, 420), m=1, cells=("trend_momentum/sectors",))
        era = members[0].eras[0]
        rolled = P.n1_path(era, 262, 2e-4)
        np.testing.assert_array_equal(rolled.ws[:, 262:], era.ws[:, :-262])
        np.testing.assert_array_equal(np.sort(rolled.ws.ravel()), np.sort(era.ws.ravel()))
        self.assertEqual(P.n1_offsets(400), (262,))
        self.assertEqual(P.n1_offsets(382), ())                              # 262 is not under 382 - 120
        self.assertEqual(P.n1_offsets(1000), (262, 409, 535, 661, 787))

    def test_the_bootstrap_is_seeded_and_its_bound_exact(self):
        members, markets = synthetic_unit(cells=("trend_momentum/sectors",))
        am, amk = P.aligned(members, markets)
        axes = P.unit_axes(["trend_momentum/sectors"])
        h1 = P.bootstrap_histograms(am, amk, "N0", unit="u", draws=range(8), cuts=CUTS, axes=axes)
        h2 = P.bootstrap_histograms(am, amk, "N0", unit="u", draws=[3, 1], cuts=CUTS, axes=axes)
        self.assertEqual(h1[3], h2[3])
        self.assertEqual(h1[1], h2[1])
        self.assertNotEqual(h1[0], h1[1])
        n1 = P.bootstrap_histograms(am, amk, "N1", unit="u", draws=range(2), cuts=CUTS, axes=axes)
        self.assertTrue(all(row["worlds"] == sum(len(m.days) - P.WINDOW + 1 for m in amk) for row in n1.values()))
        for wall in (0.03, 0.10, 0.15):
            k = P.bound_k(h1, wall)
            # direct: the ceil(39/40 x 8) = 8th smallest share, at the smallest k where it is at or under the wall
            def share(row, kk):
                return Fraction(sum(v for key, v in row["hist"].items() if int(key) >= kk), row["worlds"])
            want = next((kk for kk in range(P.K_MAX + 1)
                         if sorted(share(r, kk) for r in h1.values())[math.ceil(Fraction(39, 40) * 8) - 1]
                         <= Fraction(repr(wall))), None)
            self.assertEqual(k, want)

    def test_the_own_floor_waits_for_its_resamples_and_takes_the_matched_minimum(self):
        members, markets = synthetic_unit(cells=("trend_momentum/sectors",))
        caps = P.caps(0.02, 0.03)
        out = P.own_floor(members, markets, unit="u", floor_def="POOLED", caps_=caps, cuts=CUTS, matched_k=120, hists={})
        self.assertIsNone(out["k_own"])
        self.assertIn("resamples", out["why"])
        am, amk = P.aligned(members, markets)
        axes = P.unit_axes(["trend_momentum/sectors"])
        with mock.patch.object(P, "BOOT_RESAMPLES", 6):
            hists = {null: P.bootstrap_histograms(am, amk, null, unit="u", draws=range(6), cuts=CUTS, axes=axes)
                     for null in P.NULLS}
            out = P.own_floor(members, markets, unit="u", floor_def="R-REG", caps_=caps, cuts=CUTS, matched_k=0,
                              hists=hists)
            self.assertIsNotNone(out["k_own"], out["why"])
            self.assertEqual(out["k_own"], max(out["nulls"][n]["bound"] for n in P.NULLS))
            self.assertTrue(all(out["nulls"][n]["bound"] >= out["nulls"][n]["floor"] for n in P.NULLS))
            high = P.own_floor(members, markets, unit="u", floor_def="R-REG", caps_=caps, cuts=CUTS, matched_k=499,
                               hists=hists)
            self.assertEqual(high["k_own"], 499)
            waits = P.own_floor(members, markets, unit="u", floor_def="R-REG", caps_=caps, cuts=CUTS, matched_k=None,
                                hists=hists)
            self.assertIsNone(waits["k_own"])


# ------------------------------------------------------------------------------------------------- clusters, caps
def series_of(x, start="2016-01-04"):
    return list(sessions(start, len(x))), list(x)


class TheClusters(unittest.TestCase):
    def test_the_member_rule_joins_one_mechanism_split_in_two(self):
        rng = np.random.default_rng(11)
        n = 600
        common = rng.normal(0, 1, n)
        other = rng.normal(0, 1, n)

        def mem(base, rho):
            return series_of(rho * base + math.sqrt(1 - rho * rho) * rng.normal(0, 1, n))

        clusters = {"A": {"A/index": [mem(common, 0.5) for _ in range(3)]},
                    "B": {"B/index": [mem(common, 0.5) for _ in range(3)]},
                    "C": {"C/index": [mem(other, 0.5) for _ in range(3)]}}
        groups = P.member_join(clusters)
        self.assertIn(["A", "B"], groups)
        self.assertIn(["C"], groups)

    def test_the_class_rule_then_the_member_rule(self):
        """All judged cells of one declared class are one cluster whatever their group; cells of other classes join
        it only by the member rule."""
        rng = np.random.default_rng(14)
        n = 600
        common, other = rng.normal(0, 1, n), rng.normal(0, 1, n)

        def mem(base):
            return series_of(0.5 * base + math.sqrt(0.75) * rng.normal(0, 1, n))

        cells = {"trend_momentum/index": ("trend_momentum", [series_of(rng.normal(0, 1, n)) for _ in range(3)]),
                 "trend_momentum/sectors": ("trend_momentum", [series_of(rng.normal(0, 1, n)) for _ in range(3)]),
                 "relative_value/index": ("relative_value", [mem(common) for _ in range(3)]),
                 "reversal_liquidity/index": ("reversal_liquidity", [mem(common) for _ in range(3)]),
                 "calendar_flow/index": ("calendar_flow", [mem(other) for _ in range(3)])}
        groups = P.cluster(cells)
        self.assertIn(["trend_momentum/index", "trend_momentum/sectors"], groups)   # one class: one cluster
        self.assertIn(["relative_value/index", "reversal_liquidity/index"], groups)  # one mechanism, two labels
        self.assertIn(["calendar_flow/index"], groups)

    def test_the_prereg_names(self):
        x = list(np.random.default_rng(4).normal(0.2, 1, 40))
        self.assertEqual(P.t_k(x, 40), F.t_stat(x))
        self.assertTrue(P.pass_k(x, x, 40, -5.0, True))
        self.assertFalse(P.pass_k(x, x, 40, -5.0, False))
        self.assertEqual(P.u_cap(0.03, 0.05), P.caps(0.03, 0.05))
        np.testing.assert_allclose(P.member_z([0.002, -0.001], 0.001), [2.0, -1.0])
        row = {"type": "ETF", "case_": "N", "judged": 1, "status": "pending"}
        self.assertEqual(P.route_of(row, unit_judged=True, refuted=False, report_only=False), "pool")
        self.assertEqual(P.route_of(row, unit_judged=True, refuted=False, report_only=True), "per_program")

    def test_two_independent_mechanisms_never_join(self):
        rng = np.random.default_rng(12)
        clusters = {k: {f"{k}/index": [series_of(rng.normal(0, 1, 500)) for _ in range(3)]} for k in "XY"}
        self.assertEqual(P.member_join(clusters), [["X"], ["Y"]])

    def test_the_caps_and_report_only(self):
        c = P.caps(0.03, 0.05)
        self.assertAlmostEqual(c.cap, 0.09)
        self.assertAlmostEqual(c.wall, 0.10)
        self.assertFalse(c.report_only)
        r = P.caps(0.12, 0.2)
        self.assertTrue(r.report_only)
        self.assertEqual((r.cap, r.wall), (0.12, 0.15))
        self.assertEqual(P.joined_u([(0.03, 0.05), (0.04, 0.06)]), (0.07, 0.11))
        self.assertEqual(P.joined_u([(0.8, 0.9), (0.4, 0.5)]), (1.0, 1.0))

    def test_the_assignment_and_the_copy_merge(self):
        rng = np.random.default_rng(13)
        n = 500
        a, b = rng.normal(0, 1, n), rng.normal(0, 1, n)
        cells = {"x/index": series_of(a), "y/index": series_of(b)}
        z = series_of(0.6 * a + 0.8 * rng.normal(0, 1, n))
        target, corrs = P.assign(z, cells, 0.3)
        self.assertEqual(target, "x/index")
        self.assertGreater(corrs["x/index"], corrs["y/index"])
        self.assertEqual(P.assign(z, cells, 0.99)[0], None)
        near = series_of(a + 0.1 * rng.normal(0, 1, n))
        self.assertEqual(P.merge_copy(near, "s1", [("L1", 5, series_of(a), "s0"), ("L0", 3, None, "s9")]), "L1")
        self.assertEqual(P.merge_copy(series_of(b), "s9", [("L1", 5, series_of(a), "s0"), ("L0", 3, None, "s9")]), "L0")
        self.assertIsNone(P.merge_copy(series_of(b), "s1", [("L1", 5, series_of(a), "s0")]))


# --------------------------------------------------------------------------------------------- void, stage 1, placebo
class TheVoidStageOneAndPlacebo(unittest.TestCase):
    def test_the_zeroed_days_void(self):
        k = 40
        b = [0.001 * (i + 1) for i in range(k)]                   # the last 4 sessions are the top decile of |b|
        clustered = [(b[i], 3 if i >= 36 else 0, 5) for i in range(k)]
        self.assertTrue(P.mar_void(clustered)["void"])
        spread = [(b[i], 1 if i % 4 == 0 else 0, 5) for i in range(k)]
        self.assertFalse(P.mar_void(spread)["void"])
        one = [(b[i], 1 if i == 39 else 0, 5) for i in range(k)]   # one zeroed day on a big move: p 0.1, not void
        out = P.mar_void(one)
        self.assertFalse(out["void"])
        self.assertAlmostEqual(out["p"], 0.1)
        self.assertEqual(sum(P.mar_void(clustered)["by_decile"]), 12)
        self.assertAlmostEqual(P.binom_tail(2, 2, 0.1), 0.01)

    def test_stage_one_refutes_never_confirms(self):
        rng = np.random.default_rng(5)
        good = list(rng.normal(0.2, 1, 300))
        bad = list(rng.normal(-0.3, 1, 300))
        self.assertFalse(P.stage1([good, good], readable=3)["refuted"])
        self.assertTrue(P.stage1([good, bad], readable=3)["refuted"])
        self.assertFalse(P.stage1([bad, bad], readable=2)["refuted"])          # fewer than M_MIN readable
        x = [1.0, -1.0, 2.0, 0.5, -0.5, 1.5, 0.0, 1.0, 2.0, -1.0]
        n, m = len(x), sum(x) / len(x)
        d = [v - m for v in x]
        var = sum(v * v for v in d) / n + 2 * sum((1 - lag / 6) * sum(d[t] * d[t - lag] for t in range(lag, n)) / n
                                                  for lag in range(1, 6))
        self.assertAlmostEqual(P.newey_west_z(x), m / math.sqrt(var / n))

    def test_the_placebo_leg(self):
        seed = P.placebo_seed("e" * 64, "trend_momentum/sectors", 40)
        self.assertEqual(seed, int.from_bytes(hashlib.sha256(f"{'e' * 64}|trend_momentum/sectors|40".encode()).digest()[:16],
                                              "big"))
        draws = P.placebo_draws(50, 4, seed)
        self.assertEqual(len(draws), 999)
        self.assertTrue(all(len(set(d)) == 4 and all(0 <= i < 50 for i in d) for d in draws))
        self.assertEqual(draws, P.placebo_draws(50, 4, seed))
        pseudo = list(np.random.default_rng(2).normal(0, 1, 999)) + [None]
        self.assertEqual(P.placebo_count(1.5, pseudo), sum(1 for v in pseudo if v is not None and v >= 1.5))
        self.assertTrue(P.placebo_holds(149, 999))
        self.assertFalse(P.placebo_holds(150, 999))
        self.assertFalse(P.placebo_holds(10, 998))
        with self.assertRaises(ValueError):
            P.placebo_draws(3, 4, seed)
        self.assertEqual(P.control_wbar({"symbols": ["XLK", "XLE"], "f": 0.5}), {"XLK": 0.25, "XLE": 0.25})


# ----------------------------------------------------------------------------------------- demotion, route, words
class TheDemotionRouteAndWords(unittest.TestCase):
    def test_the_demotion(self):
        rng = np.random.default_rng(9)
        good = list(rng.normal(0.3, 1, 20))
        bad = list(rng.normal(-1.0, 1, 20))
        every = list(rng.normal(0.3, 1, 60)) + good
        self.assertIsNone(P.demote(good, good, every))
        self.assertIn("post-pass T", P.demote(bad, bad, every))
        self.assertIsNone(P.demote(good[:19], good[:19], every))               # read every 20th post-pass session
        self.assertIn("all cell sessions", P.demote(good, good, [-abs(v) for v in every]))
        post60 = list(rng.normal(0.3, 1, 60))
        self.assertIn("stress", P.demote(post60, [-1.0] * 60, every + post60))
        self.assertIsNone(P.demote(post60[:40], [-1.0] * 40, every + post60[:40]))   # the stress test at 60 and 120

    def test_the_pool_route(self):
        row = {"type": "ETF", "case_": "N", "judged": 1, "status": "fail"}
        self.assertTrue(P.on_pool_route(row, unit_judged=True, refuted=False, report_only=False))
        self.assertTrue(P.on_pool_route({**row, "status": "pending"}, unit_judged=True, refuted=False, report_only=False))
        self.assertFalse(P.on_pool_route({**row, "status": "pass"}, unit_judged=True, refuted=False, report_only=False))
        self.assertFalse(P.on_pool_route({**row, "status": "void"}, unit_judged=True, refuted=False, report_only=False))
        self.assertFalse(P.on_pool_route({**row, "type": "PANEL"}, unit_judged=True, refuted=False, report_only=False))
        self.assertFalse(P.on_pool_route({**row, "judged": 0}, unit_judged=True, refuted=False, report_only=False))
        self.assertFalse(P.on_pool_route(row, unit_judged=True, refuted=True, report_only=False))
        self.assertFalse(P.on_pool_route(row, unit_judged=True, refuted=False, report_only=True))
        self.assertFalse(P.on_pool_route(row, unit_judged=False, refuted=False, report_only=False))
        self.assertFalse(P.on_pool_route(None, unit_judged=True, refuted=False, report_only=False))

    def test_the_words_carry_no_figure(self):
        self.assertEqual(P.words("trend_momentum/sectors", "PASS"), "POOL1 unit trend_momentum/sectors: PASS")
        with self.assertRaises(ValueError):
            P.words("x/index", "not passed at 40")
        self.assertEqual(P.figure_free({"version": 1, "a": "b", "c": [None, True, "2026-10-26"]}), [])
        self.assertEqual(P.figure_free({"t": 1.7}), ["t"])
        self.assertEqual(P.figure_free({"k": 40}), ["k"])
        self.assertEqual(P.figure_free({"w": "passed with T 1.92"}), ["w"])
        self.assertEqual(P.figure_free({"w": "12% at zero edge"}), ["w"])
        self.assertEqual(P.figure_free({"rows": [{"version": 3}]}), [])

    def test_the_floor_wide_expected_passes(self):
        rec = receipt()
        self.assertEqual(P.expected_passes([("trend_momentum", 40), ("reversal_liquidity", 120)], rec), 0.14)
        self.assertEqual(P.expected_passes([("unknown", 40)], rec), 0.0)
        text = P.beside(rec, cell="trend_momentum/sectors", cluster="trend_momentum", k=40, T=1.9, c_used_value=1.83,
                        own_t=0.5, passes=1, judged=5, expected=0.2, u_point=0.04, u_bound=0.06)
        for needle in ("WEAK", "no bound", "N1", "1 passes of 5 units", "contamination", "close-rate key"):
            self.assertIn(needle.lower(), text.lower())


if __name__ == "__main__":
    unittest.main()
