"""POOL1 calibration: THE CONFORMANCE VECTORS CV1-CV12 (RECEIPT-CONTRACT POOL1-RECEIPT-1 section 6; DEVIATIONS D36).

Every output is produced by the calibration's own pinned functions; P1 reproduces each through its own route (the
"p1_route" of each vector) to 1e-9, in CI and once on the House at load, and refuses the receipt on any mismatch.
PURE: numpy, the standard library, the calibration's PREP modules (p1const, p1stat, p1members, p1units, p1engine)
and p1cluster; no fw9 path, no file I/O, no market row. P1 vendors this file byte for byte.

    vectors()          -> the receipt's "conformance" block {"version", "tolerance", "vectors": {CV1..CV12}}
    inputs(id, seed)   -> a generated vector's inputs (CV7, CV9: more than 500 numbers), canonical JSON-native
    match(got, want)   -> the mismatches under the contract's rule ([] when the two conform)

THE MATCH RULE (6.1): integers, booleans, strings and null exactly; floats |a - b| <= 1e-9 x max(1, |b|); non-finite
values are the strings "inf", "-inf" and "nan". Inputs of 500 numbers or fewer are inline; larger ones come from
inputs(id, seed), whose canonical JSON (sort_keys, separators (",", ":")) has the sha256 the vector names.

CV9 is the House pipeline end to end, generated in the House job's exact export format (meta rows and one_run
records): 12 lineages (the contract's list; its "11" omits one): trend_momentum/index x3 (S2), trend_momentum/sectors
x3 (FWD1, one with no FWD1 row), reversal_liquidity/index x3 (one with a hidden year, so its stage 1 reads s0 and s1
parts), a near-copy of a reversal member (merged), an equity_premium program and an event-word program (out); plus
one later trend_momentum/sectors lineage for the assignment. Eras of 430 and 560 sessions, B 200."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import math

import numpy as np

import p1cluster as C
import p1const as K
from p1engine import point_share, raise_to_wall, worlds
from p1members import EraPart, Member, cells_of, cutpoints, window_stats
from p1stat import alpha_windows, curve, floor_k, grid_index, legs_close, rreg_floor, sigma_tilde, \
    sigma_used, smallest_k, t_direct, tby
from p1units import bound_curve, share_curves, stationary_idx

VERSION = "POOL1-CONF-1"
TOLERANCE = 1e-9
SEEDS = {"CV7": 7007, "CV9": 9009}
EPOCH = dt.date(1970, 1, 1)
CV9_B = 200
CV9_CAP, CV9_WALL = 0.085, 0.11
CV9_CG, CV9_MIN = 170, 150


# ------------------------------------------------------------------------------------------------------- encoding
def enc(x):
    """JSON-native, with non-finite floats as "inf", "-inf", "nan" (6.1)."""
    if isinstance(x, dict):
        return {str(k): enc(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [enc(v) for v in x]
    if isinstance(x, np.ndarray):
        return enc(x.tolist())
    if isinstance(x, (bool, np.bool_)):
        return bool(x)
    if isinstance(x, (int, np.integer)):
        return int(x)
    if isinstance(x, (float, np.floating)):
        v = float(x)
        if math.isnan(v):
            return "nan"
        if math.isinf(v):
            return "inf" if v > 0 else "-inf"
        return v
    return x


def canonical(obj) -> str:
    return json.dumps(enc(obj), sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def sha256_of(obj) -> str:
    return hashlib.sha256(canonical(obj).encode()).hexdigest()


def _f(x):
    """A decoded value: the strings "inf", "-inf", "nan" back to floats."""
    if isinstance(x, str) and x in ("inf", "-inf", "nan"):
        return float(x)
    return x


def match(got, want, path: str = "", tol: float = TOLERANCE) -> list[str]:
    """The mismatches between `got` and `want` under 6.1's rule (both encoded with enc)."""
    got, want = enc(got), enc(want)
    out: list[str] = []
    if isinstance(want, dict):
        if not isinstance(got, dict) or set(got) != set(want):
            return [f"{path}: keys {sorted(got) if isinstance(got, dict) else type(got).__name__} != {sorted(want)}"]
        for k in sorted(want):
            out += match(got[k], want[k], f"{path}/{k}", tol)
        return out
    if isinstance(want, list):
        if not isinstance(got, list) or len(got) != len(want):
            return [f"{path}: length {len(got) if isinstance(got, list) else type(got).__name__} != {len(want)}"]
        for i, (a, b) in enumerate(zip(got, want)):
            out += match(a, b, f"{path}[{i}]", tol)
        return out
    if isinstance(want, bool) or isinstance(got, bool) or want is None or got is None or isinstance(want, str) \
            or isinstance(got, str) or isinstance(want, int) or isinstance(got, int):
        # exact, and of the same type: an integer never matches a float (6.1)
        return [] if (type(got) is type(want) and got == want) else [f"{path}: {got!r} != {want!r}"]
    a, b = float(got), float(want)
    if not abs(a - b) <= tol * max(1.0, abs(b)):
        return [f"{path}: {a!r} != {b!r}"]
    return []


# --------------------------------------------------------------------------------------------- generated inputs
def _weekdays(first: str, n: int) -> list[str]:
    d = dt.date.fromisoformat(first)
    out = []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += dt.timedelta(days=1)
    return out


def _num(x: float) -> float:
    return float(f"{float(x):.12g}")


def _cv7(seed: int) -> dict:
    """A 126-session prices record per era (the House job's prices() format): SPY, TLT, GLD and four sectors, XLC
    listing late in e0 (None before its listing)."""
    g = np.random.default_rng([K.SEED_ROOT, 7, seed])
    out = {"version": "conformance", "missing": []}
    for e, first in ((0, "2016-01-04"), (1, "2022-01-03")):
        days = _weekdays(first, 126)
        ent = {"days": days}
        f = g.standard_normal(126) * 0.007
        for s, beta in (("SPY", 1.0), ("TLT", -0.3), ("GLD", 0.2), ("XLK", 1.2), ("XLE", 0.8), ("XLF", 1.0),
                        ("XLC", 1.1)):
            r = beta * f + g.standard_normal(126) * 0.008
            v = [0.0] + [_num(x) for x in r[1:]]
            if s == "XLC" and e == 0:
                v = [None] * 40 + [0.0] + v[41:]
            ent[s] = v
        out[f"e{e}"] = ent
    return out


#: CV9's lineages: (lineage, class, symbol, signal, lookback, ticket, extra)
CV9_PLAN = (
    ("tm_i1", "trend_momentum", "SPY", "trend", 20, "S2", {}),
    ("tm_i2", "trend_momentum", "QQQ", "trend", 40, "S2", {}),
    ("tm_i3", "trend_momentum", "IWM", "trend", 60, "S2", {}),
    ("tm_s1", "trend_momentum", "XLK", "trend", 30, "FWD1", {"seat": True}),
    ("tm_s2", "trend_momentum", "XLE", "trend", 45, "FWD1", {"seat": True}),
    ("tm_s3", "trend_momentum", "XLV", "trend", 25, "FWD1", {"seat": True, "no_row": True}),
    ("rl_i1", "reversal_liquidity", "SPY", "reversal", 5, "S2", {}),
    ("rl_i2", "reversal_liquidity", "QQQ", "reversal", 3, "S2", {"hidden": 2017}),
    ("rl_i3", "reversal_liquidity", "IWM", "reversal", 10, "S2", {}),
    ("rl_copy", "reversal_liquidity", "SPY", "copy", 5, "S2", {"copy_of": "rl_i1"}),
    ("eq1", "equity_premium", "SPY", "hold", 0, "S2", {}),
    ("ev1", "trend_momentum", "QQQ", "trend", 15, "S2", {"event_word": True}),
)
CV9_LATER = ("tm_s4", "trend_momentum", "XLF", "trend", 35, "FWD1", {"seat": True})
CV9_SYMS = ("SPY", "QQQ", "IWM", "TLT", "GLD", "XLK", "XLE", "XLF", "XLV")


def _signal(R: np.ndarray, kind: str, lb: int) -> np.ndarray:
    """A weight path (T,) decided at the previous close: trend (long 0.5 when the trailing lb-session return is up),
    reversal (long 0.5 after a trailing lb-session drop), hold (1.0)."""
    T = len(R)
    W = np.zeros(T)
    lc = np.concatenate([[0.0], np.cumsum(np.log1p(R))])
    for t in range(1, T):
        if kind == "hold":
            W[t] = 1.0
            continue
        a = max(0, t - lb)
        back = lc[t] - lc[a]
        if kind == "trend":
            W[t] = 0.5 if back > 0 else 0.0
        elif kind == "reversal":
            W[t] = 0.5 if back < -0.004 * math.sqrt(lb) else 0.0
    return W


def _payload(days: list[str], R: np.ndarray, W: np.ndarray, sym: str, k: float, i0: int, i1: int, pid: int,
             part: str) -> dict:
    """One run in the House job's one_run format (a single-symbol universe)."""
    hs = np.array([K.HS_BP[sym] / 1e4])
    Wm = W[None, :]
    Rm = R[None, :]
    r, r15, sides, _ = legs_close(Wm, Rm, hs, k15=1.5)
    rr = r if k == 1.0 else r15
    sl = slice(i0, i1)
    out = {"pid": pid, "part": part, "status": "ok", "span": [days[i0], days[i1 - 1]], "k": float(k),
           "days": [(dt.date.fromisoformat(d) - EPOCH).days for d in days[sl]], "r": [_num(x) for x in rr[sl]],
           "universe": [sym], "capital": 1000.0, "skip": 2}
    if k != 1.0:
        return out
    exits = (np.diff(np.concatenate([[0.0], W])) < 0).astype(int)
    out.update(w=[_num(x) for x in W[sl]], b=[_num(x) for x in R[sl]], exits=[int(x) for x in exits[sl]],
               invested=[int(x > 0) for x in W[sl]], lots=int(exits.sum()), sides=[_num(x) for x in sides[sl]],
               ws=({sym: [_num(x) for x in W[sl]]} if W[sl].any() else {}), R={sym: [_num(x) for x in R[sl]]})
    return out


def _cv9(seed: int) -> dict:
    g = np.random.default_rng([K.SEED_ROOT, 9, seed])
    prices = {"version": "conformance", "missing": []}
    eras = []
    for e, first, n in ((0, "2016-01-04", 430), (1, "2022-01-03", 560)):
        days = _weekdays(first, n)
        f = g.standard_normal(n) * 0.006
        R = {}
        for s in CV9_SYMS:
            beta = {"TLT": -0.3, "GLD": 0.2}.get(s, 1.0)
            r = beta * f + g.standard_normal(n) * 0.009 + 0.0002
            R[s] = np.array([0.0] + [_num(x) for x in r[1:]])
        prices[f"e{e}"] = {"days": days, **{s: R[s].tolist() for s in CV9_SYMS}}
        eras.append((days, R))
    meta_rows, runs = [], {}
    paths: dict = {}
    for i, (lin, cls, sym, kind, lb, ticket, extra) in enumerate(CV9_PLAN + (CV9_LATER,)):
        pid = 201 + i
        hidden = extra.get("hidden")
        seen = [["2016-01-04", "2019-12-31"], ["2022-01-03", "2024-12-31"]]
        if hidden:
            seen = [["2016-01-04", f"{hidden - 1}-12-31"], ["2022-01-03", "2024-12-31"]]
        no_row = extra.get("no_row")
        meta_rows.append({
            "lineage": f"equity:{lin}", "pid": pid, "key": f"{lin}@1", "family": lin, "version": 1, "lane": "equity",
            "reason": "train_pass", "ugroup": C_group([sym]), "first_day": "2026-10-13" if lin != CV9_LATER[0]
            else "2026-10-30", "program_sha": f"sha-{lin}", "needs_symbols": [sym], "declared_class": cls,
            "inputs": ["closes"], "infer_key_class": cls, "event_word": bool(extra.get("event_word")),
            "event_field": False, "seen_spans": seen, "hidden": bool(hidden), "seat_shape": bool(extra.get("seat")),
            "reached_sealed": ticket == "S2", "fwd1_type": ("ETF" if ticket == "FWD1" and not no_row else None),
            "fwd1_case": ("N" if ticket == "FWD1" and not no_row else None),
            "fwd1_judged": (1 if ticket == "FWD1" and not no_row else None), "lineage_pids": [pid],
            "panel": False})
        if extra.get("event_word") or cls == "equity_premium":
            continue                                     # the House job runs no out-by-meta program (run_list)
        for e, (days, R) in enumerate(eras):
            if kind == "copy":
                W = paths[(extra["copy_of"], e)] * (1.0 + 0.05 * g.standard_normal(len(days)))
            else:
                W = _signal(R[sym], kind, lb)
            paths[(lin, e)] = W
            for part, k in (("k10", 1.0), ("k15", 1.5)):
                runs[f"{pid}_e{e}{part}"] = _payload(days, R[sym], W, sym, k, 2, len(days), pid, f"e{e}{part}")
        if hidden:
            for j, (lo, hi) in enumerate(seen):
                e = 0 if lo < "2021" else 1
                days, R = eras[e]
                i0 = 2
                i1 = max(t for t, d in enumerate(days) if d <= hi) + 1
                runs[f"{pid}_s{j}"] = _payload(days, R[sym], paths[(lin, e)], sym, 1.0, i0, i1, pid, f"s{j}")
    hc0 = C.house_context(prices, np.zeros((4, 2)))
    stats = np.concatenate([window_stats(hc0["bases"][e], None, np.arange(0, hc0["eras"][e].T - K.L + 1))
                            for e in (0, 1)])
    cuts = cutpoints(stats)
    return {"meta": {"version": "conformance", "members": meta_rows[:-1], "lineages": len(meta_rows) - 1,
                     "errors": []},
            "later": meta_rows[-1], "prices": prices, "runs": runs, "cuts": cuts.tolist()}


def C_group(symbols) -> str:
    """The House group of an ETF symbol list, as fw9's elane_train.symbols_group gives it for ETFs (a pure stand-in:
    P1 calls fw9's own function, which agrees on every ETF)."""
    seen = set()
    for s in symbols:
        s = str(s).upper()
        if s in K.IDX:
            seen.add("index")
        elif s in K.DEFN:
            seen.add("defensive")
        elif s.startswith("XL"):
            seen.add("sectors")
    return "+".join(x for x in ("index", "sectors", "defensive", "stocks") if x in seen) or "none"


def inputs(vid: str, seed: int) -> dict:
    """A generated vector's inputs, JSON-native (no non-finite value)."""
    if vid == "CV7":
        return _cv7(seed)
    if vid == "CV9":
        return _cv9(seed)
    raise KeyError(vid)


def _gen(vid: str) -> dict:
    seed = SEEDS[vid]
    return {"generator": "p1conform.inputs", "id": vid, "seed": seed, "sha256": sha256_of(inputs(vid, seed))}


# ------------------------------------------------------------------------------------------------------ the vectors
def cv1() -> dict:
    W = np.array([[0.5, 0.5, 0.0, 0.5, 0.5], [0.0, 0.0, 0.5, 0.0, 0.0]])
    R = np.array([[0.010, -0.020, 0.005, 0.003, -0.001], [0.002, 0.001, -0.004, 0.006, 0.000]])
    mu = np.array([0.001, 0.0005])
    wbar = np.array([0.4, 0.1])
    hs = np.array([1e-4, 3e-4])
    haircut = 2e-4
    starts = [0, 2]
    r, r15, sides, gross = legs_close(W, R, hs)
    base = r - haircut * sides - (W * mu[:, None]).sum(0)
    a = alpha_windows(base, W, R - mu[:, None], wbar, np.array(starts), 5)
    return {"what": "per-symbol alpha a(J, l) with what restarted at J: 2 symbols, 5 sessions, starts [0, 2]; legs "
                    "close to close (r = sum W R - sum hs |dW|, r15 at 1.5 hs), base = r - haircut sides - sum W mu, "
                    "X = R - mu, prior 20",
            "calib": "p1stat.alpha_windows", "p1_route": "pool_rule.alpha (the forward statistic) on days J.. with "
            "what restarted at J; and the vendored p1stat.alpha_windows",
            "inputs": {"W": W, "R": R, "mu": mu, "wbar": wbar, "hs": hs, "haircut": haircut, "starts": starts,
                       "nlag": 5, "prior": K.PRIOR, "k15": 1.5},
            "outputs": {"r": r, "r15": r15, "sides": sides, "gross": gross, "base": base, "a": a}}


def cv2() -> dict:
    g = np.random.default_rng(42)
    D = g.standard_normal((3, 120)) * 0.3 + 0.1
    T = tby(D, D)
    td = [t_direct(D[i], D[i]) for i in range(3)]
    return {"what": "T by look 40/60/120 on 3 rows of D (D15 = D): each look's T with math.fsum, and tby's best "
                    "valid T by each look (cumulative max)",
            "calib": "p1stat.t_direct per look; p1stat.tby cumulative",
            "p1_route": "pool_rule.t_stat (fsum) per look; the vendored p1stat.tby",
            "inputs": {"D": D, "D15": "D", "plan": list(K.PLAN)}, "outputs": {"t_direct": td, "tby": T}}


def cv3() -> dict:
    T = [-math.inf, math.nan, -0.5, 0.0, 0.00999, 1.5799999999, 1.58, 4.99, 5.0, 7.3]
    return {"what": "the grid: the largest k in 0..500 with k / 100 <= T; -1 for -inf, NaN or T < 0; 500 at or "
                    "above 5", "calib": "p1stat.grid_index",
            "p1_route": "the vendored p1stat.grid_index (P1's own grid leaves the floor path)",
            "inputs": {"T": T}, "outputs": {"k": grid_index(np.array(T))}}


def cv4() -> dict:
    g0 = np.random.default_rng([K.SEED_ROOT, 4])
    gi = g0.integers(-1, 300, 60).astype(np.int64)
    w = np.array([(1.0, 0.5, 1.0 / 3.0)[i % 3] for i in range(60)])
    cells = g0.random((60, 3)) < 0.4
    cells[0, :] = True
    out = {}
    for cap in (0.12, 0.07):
        tot = float(w.sum())
        out[str(cap)] = {"floor_k": floor_k(gi, w, cap), "rreg_floor": rreg_floor(gi, w, cells, cap),
                         "smallest_k": smallest_k(curve(gi, w) / tot, cap)}
    return {"what": "floors on weighted worlds: 60 grid indices, weights 1, 1/2 and 1/3 (the N1 shape), 3 regime "
                    "columns, caps 0.12 and 0.07", "calib": "p1stat.floor_k, p1stat.rreg_floor, p1stat.smallest_k",
            "p1_route": "vendored", "inputs": {"g": gi, "w": w, "cells": cells, "caps": [0.12, 0.07]},
            "outputs": {"by_cap": out, "curve": curve(gi, w)}}


def cv5() -> dict:
    g0 = np.random.default_rng([K.SEED_ROOT, 5])
    gb = g0.integers(-1, 260, (8, 15)).astype(np.int64)
    gp = g0.integers(-1, 260, 15).astype(np.int64)
    w = 0.5
    counts = share_curves(gb, w)
    share_b = counts / (w * gb.shape[1])
    ps = point_share(gp, np.full(15, w))
    bd = bound_curve(share_b, ps)
    return {"what": "the bound: share_curves of 8 resamples x 15 windows at weight 0.5, normalized by 0.5 x 15 (as "
                    "p1cluster.shares_from does), the point share of 15 windows at weight 0.5, the bound max(q97.5, "
                    "point + q97.5 - mean) at all 501 k, and the raise to the wall from k0 2 at wall 0.09",
            "calib": "p1units.share_curves, p1engine.point_share, p1units.bound_curve, p1engine.raise_to_wall",
            "p1_route": "vendored", "inputs": {"g_b": gb, "w": w, "g": gp, "k0": 2, "wall": 0.09},
            "outputs": {"share_curves": counts, "point_share": ps, "bound_curve": bd,
                        "raise_to_wall": raise_to_wall(2, bd, 0.09)}}


def cv6() -> dict:
    seed = [K.SEED_ROOT, 902, 7, 0]
    return {"what": "stationary block bootstrap indices (mean block 120), n 23, B 5 (proves the numpy RNG stream)",
            "calib": "p1units.stationary_idx", "p1_route": "vendored",
            "inputs": {"n": 23, "B": 5, "seed": seed, "mean_block": K.BLOCK_MEAN},
            "outputs": {"idx": stationary_idx(23, 5, seed)}}


def cv7() -> dict:
    prices = inputs("CV7", SEEDS["CV7"])
    hc0 = C.house_context(prices, np.zeros((4, 2)))
    stats = {e: window_stats(hc0["bases"][e], None, np.arange(0, hc0["eras"][e].T - K.L + 1)) for e in (0, 1)}
    cuts = cutpoints(np.concatenate([stats[0], stats[1]]))
    hc = C.house_context(prices, cuts)
    return {"what": "regime cells on a generated 126-session prices record per era (SPY, TLT, GLD and four sectors, "
                    "XLC listing late in e0): the window statistics (vol, ret, disp by the launch-ordered prefix "
                    "rule, gap), the tercile cutpoints over both eras' windows, and the cells and vol terciles",
            "calib": "p1cluster.house_context -> p1members.window_stats, p1members.cutpoints, p1members.cells_of",
            "p1_route": "P1's market path: its pool_market record into the vendored p1cluster.house_context",
            "inputs": _gen("CV7"),
            "outputs": {"stats": {f"e{e}": stats[e] for e in (0, 1)}, "cuts": cuts,
                        "cells": {f"e{e}": hc["cells"][e] for e in (0, 1)},
                        "cells_direct": {f"e{e}": cells_of(stats[e], cuts) for e in (0, 1)},
                        "vt": {f"e{e}": hc["vt"][e] for e in (0, 1)}}}


def cv8() -> dict:
    g0 = np.random.default_rng([K.SEED_ROOT, 8])
    T, p0, p1, off = 30, 2, 28, 7
    syms = ("SPY", "XLK")
    W = np.zeros((2, T))
    W[:, p0:p1] = g0.choice([0.0, 0.25, 0.5], size=(2, p1 - p0))
    R = np.round(g0.standard_normal((2, T)) * 0.01, 6)
    hs = np.array([K.HS_BP[s] / 1e4 for s in syms])
    r, r15, sides, _ = legs_close(W, R, hs, k15=K.K_STRESS)
    noise = np.round(g0.standard_normal(T) * 1e-5, 8)
    r = np.where((np.arange(T) >= p0) & (np.arange(T) < p1), r + noise, 0.0)
    r15 = np.where((np.arange(T) >= p0) & (np.arange(T) < p1), r15 + noise, 0.0)
    sides = np.where((np.arange(T) >= p0) & (np.arange(T) < p1), sides, 0.0)
    mu = np.array([0.0004, -0.0002])
    wbar = np.array([0.2, 0.3])
    mm = Member(name="CV8", family="cv8", group="index", cls="trend_momentum", syms=syms,
                parts=[EraPart(p0=p0, p1=p1, W=W, r=r, r15=r15, sides=sides, R=R, lots=True)], mu=mu, wbar=wbar,
                sigma=0.01)
    span = (p0, p1)
    Wr, base, c15, dS = mm.path(0, off, span)
    a_first, M = mm.A(0, off, span)
    W0, base0, c150, _ = mm.path(0)
    return {"what": "a lot-accounted member's N1 path: S 2, T 30, pool [2, 28), offset 7, rolled inside the span "
                    "(np.roll(seg, -offset)), legs recomputed close to close (stress 1.5), base = r - 2 bp sides - "
                    "sum W mu; the window matrix's first rows and the era-restart alpha; the unrolled path beside",
            "calib": "p1members.Member.path, Member.A, Member.a_era", "p1_route": "vendored",
            "inputs": {"syms": list(syms), "W": W, "R": R, "r": r, "r15": r15, "sides": sides, "mu": mu,
                       "wbar": wbar, "p0": p0, "p1": p1, "offset": off},
            "outputs": {"hs": mm.hs, "rolled": {"W": Wr, "base": base, "c15": c15, "dS": dS},
                        "A_first": a_first, "A_rows": M[:3, :p1 - p0], "a_era": mm.a_era(0, off, span),
                        "unrolled": {"base": base0, "c15": c150, "a_era": mm.a_era(0)}}}


def cv9() -> dict:
    inp = inputs("CV9", SEEDS["CV9"])
    meta, prices, runs = inp["meta"], inp["prices"], inp["runs"]
    cuts = np.array(inp["cuts"])
    hc = C.house_context(prices, cuts)
    records, members = [], []
    for m in sorted(meta["members"], key=lambda x: x["pid"]):
        rec, mm = C.member_from_runs(m, runs, hc, C_group)
        records.append(rec)
        if mm is not None:
            members.append(mm)
    kept, merged = C.merge_copies(members, hc)
    cc = C.cells_and_clusters(kept, hc)
    lin = {mm.name: mm.family for mm in members}
    cell_id = {k: f"{k[0]}/{k[1]}" for k in cc["cells"]}
    out = {"records": [{"lineage": r["lineage"], "status": r["status"], "group": r.get("group")} for r in records],
           "merged": {lin[a]: lin[b] for a, b in merged.items()},
           "constants": {mm.family: {"mu": mm.mu, "wbar": mm.wbar, "sigma": mm.sigma, "abar": mm.abar,
                                     "abar_v": mm.abar_v, "kind": mm.meta["kind"], "group": mm.group}
                         for mm in kept},
           "cells": {cell_id[k]: [lin[x.name] for x in v] for k, v in cc["cells"].items()},
           "below": cc["below"], "cell_within": {cell_id[k]: v for k, v in cc["cell_within"].items()},
           "clusters": {cid: [cell_id[k] for k in keys] for cid, keys in cc["clusters"].items()},
           "joins": [j["joined"] for j in cc["joins"]], "rho_assign": cc["rho_assign"], "loo": cc["loo"]}
    floors = {}
    for ci, (cname, keys) in enumerate(sorted(cc["clusters"].items())):
        ms = [mm for k in keys for mm in cc["cells"][k]]
        sig_u = {}
        for k in keys:
            st = sigma_tilde([x.sigma for x in cc["cells"][k]])
            for x in cc["cells"][k]:
                sig_u[x.name] = float(sigma_used(np.array([x.sigma]), st)[0])
        s1 = C.stage1(ms, sig_u, runs, hc)
        runs_ = {"joins_0": None}
        sector = [x for k in keys if k[1] == "sectors" for x in cc["cells"][k]]
        if sector:
            runs_["join_25"] = {sector[0].name: 25}
        res = {"stage1": s1, "boot_seed": ci}
        for label, joins in runs_.items():
            cf = C.cluster_floor(cname, keys, cc["cells"], hc, cuts, CV9_B, ci, CV9_CAP, CV9_WALL, joins=joins)
            if cf is None:
                res[label] = None
                continue
            fl = cf["floor"]
            near = {}
            for null in K.NULLS:
                g, w, _ = worlds(cf["proxy"], cf["point"], "IN", null, hc["cells"])
                ps = point_share(g, w)
                bd = bound_curve(cf["shares"][null]["IN"], ps)
                for fd in K.FLOOR_DEFS:
                    f = fl["floor"][null][fd]["IN"]
                    if f is None:
                        near[f"{null}|{fd}"] = None
                        continue
                    near[f"{null}|{fd}"] = {str(k): [ps[k], bd[k]] for k in (f - 1, f, f + 1) if 0 <= k <= K.K_MAX}
            res[label] = {
                "joins": {lin[n]: v for n, v in (joins or {}).items()},
                "span": {f"e{e}": list(v) for e, v in cf["span"].items()},
                "floor": fl["floor"], "c_own": fl["c_own"], "near_floor_IN": near,
                "windows": {f"e{e}|{key}": int(len(J)) for (e, key), (J, _) in sorted(cf["point"].items())},
                "k_used": {f"{fd}+{mg}": C.k_used_for(fl["c_own"][fd]["IN"], CV9_MIN, CV9_CG, mg)
                           for fd, mg in K.RULES}}
        floors[cname] = res
    out["floors"] = floors
    later = inp["later"]
    rec, mm = C.member_from_runs(later, runs, hc, C_group)
    assign = None
    if mm is not None:
        z = C.z_on_calendar(mm, hc)
        Z = {x.name: C.z_on_calendar(x, hc) for x in kept}
        cand = {cell_id[k]: np.array([Z[x.name] for x in v]) for k, v in cc["cells"].items() if k[1] == mm.group}
        cell, corr = C.assign_cell(z, cand, cc["rho_assign"])
        assign = {"group": mm.group, "kind": mm.meta["kind"], "corr": corr, "cell": cell}
    out["later"] = {"lineage": later["lineage"], "status": rec["status"], "assignment": assign}
    return {"what": "the House pipeline end to end in the House job's export format (module docstring): members "
                    "(member_from_runs, the group of a symbol as fw9's for ETFs), the copy merge, cells, clusters, "
                    "joins, rho_assign and loo, the constants (fit_constants at the 2 bp floor haircut), the ticket "
                    "kinds, stage 1, then cluster_floor per cluster (boot seed its index in sorted clusters) at cap "
                    "0.085 and wall 0.11 with joins all 0, and again with one sector member joining at lag 25: "
                    "floors, c_own, the point share and bound at k in {f-1, f, f+1}, window counts per (era, "
                    "variant), k_used for the 6 rules at c_G 170 and minimum 150; and a later lineage's assignment",
            "calib": "p1cluster.member_from_runs, merge_copies, cells_and_clusters, z_on_calendar, ticket_kind, "
                     "stage1, cluster_floor, k_used_for, assign_cell",
            "p1_route": "P1's adapter: the records as pool_train rows into p1cluster.member_from_runs, then the "
                        "merge, the cells and cluster_floor (a look's code path)",
            "inputs": {**_gen("CV9"), "B": CV9_B, "cap": CV9_CAP, "wall": CV9_WALL, "c_G_k": CV9_CG,
                       "minimum_k": CV9_MIN},
            "outputs": out}


def cv10() -> dict:
    cases = [(0.05, 0.08, []), (0.119999, 0.10, []), (0.12, 0.13, []), (0.10, 0.15, []),
             (0.02, 0.03, [{"lineage": "equity:x", "kind": "S2", "why": "S2's bar raised ValueError"}])]
    return {"what": "the caps rule: report-only on U point >= 0.12, U bound >= 0.15 (WALL_u <= 0) or a dropped "
                    "ticket; else CAP_u = 0.12 - point, WALL_u = 0.15 - bound",
            "calib": "p1cluster.caps_rule", "p1_route": "pool_rule.caps",
            "inputs": {"cases": [{"u_point": a, "u_bound": b, "dropped": d} for a, b, d in cases]},
            "outputs": {"caps": [C.caps_rule(a, b, d) for a, b, d in cases]}}


def cv11() -> dict:
    texts = ["x = ctx.events", 'x = ctx["events_next"]', 'name = "events"', "# events", "eventsx = 1",
             "my_events = []", "def decide(ctx:\n    return [", "ctx.event_calendar"]
    return {"what": "the event reader: the word events or events_next anywhere in the frozen code",
            "calib": "p1cluster.event_word",
            "p1_route": "pool_rule.reads_events (the union): True wherever the regex says True",
            "inputs": {"texts": texts}, "outputs": {"event_word": [C.event_word(t) for t in texts]}}


def cv12() -> dict:
    cases = [(None, 150, 170, 3), (120, 150, 170, 0), (180, 150, 170, 3), (160, 501, 170, 0), (498, None, 170, 3),
             (497, None, 170, 3), (497, 150, 170, 5), (100, None, 140, 5), (0, 0, 140, 0), (250, 300, 140, 3)]
    return {"what": "the bar: k_own = max(c_own, minimum), c_used = max(c_G, k_own + margin); None (ineligible) when "
                    "c_own is None or k_own + margin > 500",
            "calib": "p1cluster.k_used_for", "p1_route": "pool_rule.k_used",
            "inputs": {"cases": [{"c_own": a, "minimum": b, "c_G": c, "margin": d} for a, b, c, d in cases]},
            "outputs": {"k_used": [C.k_used_for(a, b, c, d) for a, b, c, d in cases]}}


def vectors() -> dict:
    """The receipt's "conformance" block (6.1), every value encoded (enc)."""
    vs = {"CV1": cv1(), "CV2": cv2(), "CV3": cv3(), "CV4": cv4(), "CV5": cv5(), "CV6": cv6(), "CV7": cv7(),
          "CV8": cv8(), "CV9": cv9(), "CV10": cv10(), "CV11": cv11(), "CV12": cv12()}
    return enc({"version": VERSION, "tolerance": TOLERANCE, "vectors": vs})
