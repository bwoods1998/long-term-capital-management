#!/usr/bin/env python
"""search_judge.py: the judge's offline search over look schedules, thresholds, margins and guards, on calib_judge.py's
raw per-session arrays (synthetic only; reads no lane data).

A RULE = (schedule, alpha, m0, guards, retirement):
  schedule 'every:Smin:Smax'        a look at every session that adds a block, Smin <= S <= Smax
           'list:s1,s2,...'         a look at the first block session with S >= s_k (and the minimums), k = 1, 2, ...
           'events:n1,n2,...@Smin'  PREREG-EVL-3's kind: a look at the first close with >= n_k events, >= Smin blocks
  alpha    'cS:c' (c / S) | 'const:a' | 'pow:a:g' (a (S / 6)^-g)
  m0       the margin: p of mean(B - m0) > 0
  guards   'abs' (>= 30 events, >= 30 issuers, mean a > 0, mean r > 0) | 'full' (+ beats its control + issuer p <= 0.10)
  ret      True: at each look, mean a < 0 and the lower-tail p <= the same alpha retires the version first (EVL-6's
           retirement); the version never passes after.
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import report_judge as RJ  # noqa: E402

TIE = 1e-12


def look_mask(d, L, sched):
    Sat = d[f"L{L}_Sat"].astype(np.int64)
    has = d[f"L{L}_has"]
    mn = d[f"L{L}_min"]
    R, T = Sat.shape
    kind, _, arg = sched.partition(":")
    if kind == "every":
        smin, smax = (int(x) for x in arg.split(":"))
        return has & mn & (Sat >= smin) & (Sat <= smax)
    if kind == "list":
        sl = [int(x) for x in arg.split(",")]
        out = np.zeros((R, T), bool)
        prev = np.full(R, -1)
        ok = has & mn
        tt = np.arange(T)[None, :]
        for s_k in sl:
            cand = ok & (Sat >= s_k) & (tt > prev[:, None])
            anyc = cand.any(axis=1)
            first = np.where(anyc, cand.argmax(axis=1), -1)
            rr = np.nonzero(anyc)[0]
            out[rr, first[rr]] = True
            prev = np.where(anyc, first, T + 1)   # once a look is missed (horizon), later ones are too
        return out
    if kind == "mlistcap":
        lst, _, cap = arg.partition("@")
        base = look_mask(d, L, f"mlist:{lst}")
        return base & (d[f"L{L}_ne"] <= int(cap))
    if kind == "mlist":
        # PREREG-EVL-6 section 2 exactly: look k at the first close adding a block at which S >= s_k and the minimums
        # hold; every threshold reached by then is consumed by that one look (thresholds reached together are one look)
        sl = np.array([int(x) for x in arg.split(",")])
        out = np.zeros((R, T), bool)
        nxt = np.zeros(R, np.int64)          # index of the next unconsumed threshold
        ok = has & mn
        for t in range(T):
            live = nxt < sl.size
            thr = sl[np.minimum(nxt, sl.size - 1)]
            hit = ok[:, t] & live & (Sat[:, t] >= thr)
            if hit.any():
                out[hit, t] = True
                nxt[hit] = (Sat[hit, t][:, None] >= sl[None, :]).sum(axis=1)
        return out
    if kind == "events":
        ns_s, _, smin = arg.partition("@")
        ns = [int(x) for x in ns_s.split(",")]
        smin = int(smin)
        ne = d[f"L{L}_ne"]
        niss = d[f"L{L}_niss"]
        ok = has & (Sat >= smin) & (niss >= 30) & (ne >= 30)
        out = np.zeros((R, T), bool)
        j = np.zeros(R, np.int64)
        for t in range(T):
            nxt = np.array(ns + [10 ** 9])[np.minimum(j, len(ns))]
            hit = ok[:, t] & (ne[:, t] >= nxt) & (j < len(ns))
            out[hit, t] = True
            if hit.any():
                # thresholds reached together are one look
                reached = (ne[hit, t][:, None] >= np.array(ns)[None, :]).sum(axis=1)
                j[hit] = reached
        return out
    raise ValueError(sched)


def alpha_of(Sat, spec):
    kind, _, arg = spec.partition(":")
    S = np.maximum(Sat.astype(float), 1.0)
    if kind == "cS":
        return float(arg) / S
    if kind == "const":
        return np.full(Sat.shape, float(arg))
    if kind == "pow":
        a, g = (float(x) for x in arg.split(":"))
        return a * (S / 6.0) ** (-g)
    if kind == "step":
        a1, sb, a2 = arg.split(":")
        return np.where(S <= float(sb), float(a1), float(a2))
    raise ValueError(spec)


def first_pass(d, L, rule):
    sched, aspec, m0, guards, ret = rule
    lm = look_mask(d, L, sched)
    Sat = d[f"L{L}_Sat"]
    al = alpha_of(Sat, aspec)
    P = d[f"L{L}_P{m0}"]
    P = np.where(np.isnan(P), 9.0, P)
    g = d[f"L{L}_abs"] & d[f"L{L}_min"]
    if guards == "full":
        g = g & d[f"L{L}_ctrl"] & d[f"L{L}_iss"]
    pm = lm & (P <= al + TIE) & g
    R, T = pm.shape
    fp = np.where(pm.any(axis=1), pm.argmax(axis=1) + 1, 10 ** 6)
    if ret:
        PL = d[f"L{L}_PL"]
        PL = np.where(np.isnan(PL), 9.0, PL)
        rm = lm & d[f"L{L}_neg"] & (PL <= al + TIE)
        fr = np.where(rm.any(axis=1), rm.argmax(axis=1) + 1, 10 ** 6)
        fp = np.where(fp < fr, fp, 10 ** 6)
        return fp, fr
    return fp, np.full(R, 10 ** 6)


def combined(d, L, rule, mode):
    """mode 'alone': PREREG-EVL-6 only; 'union': PREREG-EVL-3's screen (with its retirement) or PREREG-EVL-6."""
    fn, fr = first_pass(d, L, rule)
    if mode == "alone":
        return np.where(fn < 10 ** 6, fn, -1)
    fo = np.where(d["old"] >= 1, d["old"].astype(np.int64), 10 ** 6)
    ro = np.where(d["old_ret"] >= 1, d["old_ret"].astype(np.int64), 10 ** 6)
    stop = np.minimum(ro, fr)
    u = np.minimum(np.where(fo < stop, fo, 10 ** 6), np.where(fn < stop, fn, 10 ** 6))
    return np.where(u < 10 ** 6, u, -1)


def rate(f, H):
    return float(np.mean((f >= 1) & (f <= H)))


def med(f):
    f = np.asarray(f).astype(np.int64)
    x = np.where(f >= 1, f, 10 ** 6).astype(float)
    v = float(np.median(x))
    return None if v >= 10 ** 6 else v


_CACHE: dict = {}


def load(phases=("main", "stress", "noskill", "life", "power", "power120")):
    if "meta" not in _CACHE:
        meta = [m for m in RJ._meta() if m["phase"] in phases]
        _CACHE["meta"] = meta
        _CACHE["data"] = {m["path"]: dict(np.load(m["path"])) for m in meta}
    return _CACHE["meta"], _CACHE["data"]


def evaluate(rule, mode="alone", lag=0, H=120, verbose=False):
    meta, data = load()
    worst_p = (0.0, None)
    worst_s = (0.0, None)
    base = 0.0
    pw = {}
    for m in meta:
        d = data[m["path"]]
        f = combined(d, lag, rule, mode)
        if RJ.is_null(m):
            v = rate(f, min(H, m["T"]))
            if RJ.plausible(m):
                if v > worst_p[0]:
                    worst_p = (v, RJ.lab(m))
            elif v > worst_s[0]:
                worst_s = (v, RJ.lab(m))
            g = m["gen"]
            if m["cell"] == "N3|sym|nodrift" and abs(g["rho_day"] - 0.05) < 1e-9:
                base = max(base, v)
            if verbose:
                print(f"   {RJ.lab(m)}: {v:.4f} {'P' if RJ.plausible(m) else 'S'}")
        elif m["phase"].startswith("power"):
            g = m["gen"]
            key = (round(g["skill"] * 1e4), g["rho_day"], int(g["nbar"]), m["T"])
            pw[key] = {h: rate(f, h) for h in (8, 10, 12, 15, 20, 30, 40, 60, 120) if h <= m["T"]} | {"med": med(f)}
    return {"worst": worst_p, "stress": worst_s, "base": base, "power": pw}


def score(res, skill=60, rho=0.05, h=20):
    vals = [v[h] for (sk, r, n, T), v in res["power"].items() if sk == skill and abs(r - rho) < 1e-9 and T == 60
            and h in v]
    return float(np.mean(vals)) if vals else float("nan")


def grid(mode, lag, H, out_path):
    meta, data = load()
    rules = []
    for m0 in (0.0, 0.0005, 0.001, 0.0015, 0.002):
        for guards in ("full",):
            for ret in (True, False):
                for smin in (6, 7, 8):
                    for smax in (40, 60, 120):
                        for c in (0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.09, 0.10, 0.125):
                            rules.append((f"every:{smin}:{smax}", f"cS:{c}", m0, guards, ret))
                for sl in ("6,8,10,13,17,22,30,40,60,90", "7,9,12,16,21,28,38,50,70,100", "8,10,12,15,20,25,30,40,60",
                           "6,7,8,9,10,12,14,16,20,25,30,40", "7,8,9,10,11,12,14,16,18,20,25,30"):
                    for a in (0.004, 0.006, 0.008, 0.010, 0.012, 0.015, 0.018):
                        rules.append((f"list:{sl}", f"const:{a}", m0, guards, ret))
                    for a, gm in ((0.03, 0.5), (0.02, 0.5), (0.04, 1.0), (0.03, 1.0), (0.025, 0.75), (0.02, 0.25)):
                        rules.append((f"list:{sl}", f"pow:{a}:{gm}", m0, guards, ret))
                for ev in ("60,90,135,200,300,450,675,1000,1500,2250@8", "30,45,68,101,152,228,342,513,769,1153,1730,2595@7"):
                    for a in (0.008, 0.010, 0.012, 0.015, 0.018):
                        rules.append((f"events:{ev}", f"const:{a}", m0, guards, ret))
    global _ARGS
    _ARGS = (mode, lag, H)
    from multiprocessing import get_context
    with get_context("fork").Pool(int(os.environ.get("SEARCH_WORKERS", "12"))) as pool, open(out_path, "w") as fh:
        for i, row in enumerate(pool.imap_unordered(_one, rules, chunksize=4)):
            fh.write(json.dumps(row) + "\n")
            if i % 100 == 0:
                print(f"{i}/{len(rules)}", flush=True)


_ARGS = None


def _one(rule):
    mode, lag, H = _ARGS
    res = evaluate(rule, mode, lag, H)
    return {"rule": rule, "mode": mode, "lag": lag, "H": H, "worst": res["worst"], "stress": res["stress"],
            "base": res["base"], "s20": score(res, 60, 0.05, 20), "s15": score(res, 60, 0.05, 15),
            "s10": score(res, 60, 0.05, 10), "s40": score(res, 60, 0.05, 40),
            "s20_100": score(res, 100, 0.05, 20), "s20_30": score(res, 30, 0.05, 20),
            "power": {f"{k[0]}|{k[1]}|{k[2]}|{k[3]}": v for k, v in res["power"].items()}}


def grid2(mode, lag, H, out_path):
    rules = []
    lists = {"A": "7,8,9,10,11,12,14,16,18,20,25,30",
             "B": "7,8,9,10,11,12,14,16,18,20,25,30,40,50,60",
             "C": "7,8,9,10,11,12,14,16,18,20,25,30,40,50,60,80,100,120",
             "D": "6,7,8,9,10,11,12,14,16,18,20,25,30,40,50,60",
             "E": "7,8,9,10,12,14,16,20,25,30,40,50,60,80,100"}
    for m0 in (0.0005, 0.001, 0.0015):
        for key, sl in lists.items():
            for a in (0.010, 0.012, 0.015, 0.018):
                rules.append((f"list:{sl}", f"const:{a}", m0, "full", True))
                for b in (0.004, 0.006, 0.008):
                    if b < a:
                        rules.append((f"list:{sl}", f"step:{a}:20:{b}", m0, "full", True))
            for a, g in ((0.02, 0.25), (0.02, 0.5), (0.025, 0.5), (0.03, 0.5), (0.025, 0.75), (0.03, 0.75), (0.03, 1.0)):
                rules.append((f"list:{sl}", f"pow:{a}:{g}", m0, "full", True))
    global _ARGS
    _ARGS = (mode, lag, H)
    from multiprocessing import get_context
    with get_context("fork").Pool(int(os.environ.get("SEARCH_WORKERS", "12"))) as pool, open(out_path, "w") as fh:
        for i, row in enumerate(pool.imap_unordered(_one, rules, chunksize=2)):
            fh.write(json.dumps(row) + "\n")
            if i % 50 == 0:
                print(f"{i}/{len(rules)}", flush=True)


def grid3(mode, lag, H, out_path):
    rules = []
    lists = {"A": "7,8,9,10,11,12,14,16,18,20,25,30",
             "B": "7,8,9,10,11,12,14,16,18,20,25,30,40,50,60",
             "C": "7,8,9,10,11,12,14,16,18,20,25,30,40,50,60,80,100,120",
             "F": "7,8,9,10,11,12,13,14,15,16,18,20,22,25,30,35,40,50,60"}
    for m0 in (0.0005, 0.001):
        for key, sl in lists.items():
            for a1 in (0.015, 0.016, 0.018, 0.020):
                for sb in (16, 20, 25):
                    for a2 in (0.003, 0.004, 0.005, 0.006, 0.008):
                        rules.append((f"mlist:{sl}", f"step:{a1}:{sb}:{a2}", m0, "full", True))
    global _ARGS
    _ARGS = (mode, lag, H)
    from multiprocessing import get_context
    with get_context("fork").Pool(int(os.environ.get("SEARCH_WORKERS", "12"))) as pool, open(out_path, "w") as fh:
        for i, row in enumerate(pool.imap_unordered(_one, rules, chunksize=2)):
            fh.write(json.dumps(row) + "\n")
            if i % 50 == 0:
                print(f"{i}/{len(rules)}", flush=True)


def frontier(path, cap=0.10, key="s20", top=25):
    rows = [json.loads(l) for l in open(path)]
    ok = [r for r in rows if r["worst"][0] <= cap]
    ok.sort(key=lambda r: -r[key])
    print(f"{len(ok)}/{len(rows)} rules with worst plausible <= {cap}; best by {key}:")
    for r in ok[:top]:
        print(f"  {r[key]:.3f} s10 {r['s10']:.3f} s15 {r['s15']:.3f} s20 {r['s20']:.3f} s40 {r['s40']:.3f} "
              f"100bp@20 {r['s20_100']:.3f} 30bp@20 {r['s20_30']:.3f} | worst {r['worst'][0]:.4f} [{r['worst'][1]}] "
              f"base {r['base']:.4f} stress {r['stress'][0]:.4f} | {r['rule']}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["grid", "grid2", "grid3", "frontier", "eval"])
    ap.add_argument("--mode", default="alone")
    ap.add_argument("--lag", type=int, default=0)
    ap.add_argument("--H", type=int, default=120)
    ap.add_argument("--out", default=None)
    ap.add_argument("--cap", type=float, default=0.10)
    ap.add_argument("--key", default="s20")
    ap.add_argument("--rule", default=None)
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()
    out = a.out or os.path.join(HERE, f"search_{a.mode}_L{a.lag}_H{a.H}.jsonl")
    if a.cmd == "grid":
        grid(a.mode, a.lag, a.H, out)
    elif a.cmd == "grid2":
        grid2(a.mode, a.lag, a.H, out)
    elif a.cmd == "grid3":
        grid3(a.mode, a.lag, a.H, out)
    elif a.cmd == "frontier":
        frontier(out, a.cap, a.key)
    else:
        rule = json.loads(a.rule)
        res = evaluate(tuple(rule), a.mode, a.lag, a.H, a.verbose)
        print(json.dumps({k: v for k, v in res.items() if k != "power"}))
        for k, v in sorted(res["power"].items()):
            print(k, v)
