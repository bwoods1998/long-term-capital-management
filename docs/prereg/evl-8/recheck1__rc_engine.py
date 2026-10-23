#!/usr/bin/env python
"""rc_engine.py (RE-CHECK #1 of PREREG-EVL-8, SYNTHETIC ONLY): an INDEPENDENT implementation of PREREG-EVL-6 sections
1.2-2 AS FROZEN (sha256 0f67f94e...), written from the frozen text, with no shortcut: p and q by the text's own Monte
Carlo (99,999 vectors of random.Random(seed).getrandbits(S), seed = the first 8 bytes of sha256 of the seed string
f"{id}|v1|evl6|{tag}S{S}", bit j set = +1 for value j), the issuer-block p over 99,999 vectors with the "|issuer"
seed string, no z prefilter, RETIRE first, then PASS with every guard, looks at 22, 25, 30, 35, 40, 50, 60 (thresholds
reached together are one look), the minimums, the run ending at its 60th block and run 2 from block 61. CAP = 4 (F4).
Each replicate is a different program id (so the sign vectors differ between replicates, as between programs).

It runs on the PX generator's arrays (px_final8.generate, read only) and compares, replicate by replicate, with the
fixer's pipeline (px_final8.records + search_final.first_pass / two_runs) on the SAME arrays.

Usage: rc_engine.py CELLSPEC_JSON SEED R OUT
"""
from __future__ import annotations

import os
import sys

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
os.environ["FINAL_ARR"] = os.path.join(HERE, "arr")
os.environ["V2_ARR"] = os.path.join(HERE, "arr")
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_v, "1")
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "final")))

import hashlib  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import random  # noqa: E402
import time  # noqa: E402

import numpy as np  # noqa: E402

import px_final8 as X  # noqa: E402

LOOKS = (22, 25, 30, 35, 40, 50, 60)
S_RUN = 60
MARGIN = 0.0010
TIE = 1e-12
NV = 99_999
CAP = 4


def alpha(S):
    return 0.020 if 22 <= S <= 30 else (0.006 if 31 <= S <= 40 else (0.001 if 41 <= S <= 60 else 0.0))


def seed_of(s):
    return int.from_bytes(hashlib.sha256(s.encode()).digest()[:8], "big")


def signs(seed_string, S):
    rnd = random.Random(seed_of(seed_string))
    nb = (S + 7) // 8
    buf = b"".join(rnd.getrandbits(S).to_bytes(nb, "little") for _ in range(NV))
    bits = np.unpackbits(np.frombuffer(buf, np.uint8).reshape(NV, nb), axis=1, bitorder="little")[:, :S]
    return np.where(bits == 1, 1.0, -1.0)


def mc_p(y, seed_string):
    y = np.asarray(y, float)
    S = y.size
    obs = math.fsum(y)
    thr = obs - S * TIE
    M = signs(seed_string, S) @ y
    cnt = int(np.count_nonzero(M >= thr))
    return (1 + cnt) / (1 + NV)


def issuer_p(vals, seed_string):
    n = vals.size
    rnd = random.Random(seed_of(seed_string))
    nb = (n + 7) // 8
    obs = math.fsum(vals)
    thr = obs - n * TIE
    cnt = 0
    done = 0
    while done < NV:
        m = min(10_000, NV - done)
        buf = b"".join(rnd.getrandbits(n).to_bytes(nb, "little") for _ in range(m))
        bits = np.unpackbits(np.frombuffer(buf, np.uint8).reshape(m, nb), axis=1, bitorder="little")[:, :n]
        sg = np.where(bits == 1, 1.0, -1.0)
        cnt += int(np.count_nonzero(sg @ vals >= thr))
        done += m
    return (1 + cnt) / (1 + NV)


def run_screen(a, r, iss, valid, C, rep, start_block, run_tag):
    """One run of one replicate: returns ('pass'|'retire'|'end'|'open', session index 1-based or None)."""
    T = a.shape[0]
    pid = f"PX-RC{rep}"
    blocks, ns, cvals = [], [], []
    ev_a, ev_r, ev_i = [], [], []
    top_a, top_r = [], []
    gblock = 0
    k = 0
    for t in range(T):
        v = valid[t]
        n = int(v.sum())
        if n == 0:
            continue
        gblock += 1
        if gblock <= start_block:
            continue
        at, rt, it = a[t][v], r[t][v], iss[t][v]
        blocks.append(math.fsum(at) / n); ns.append(n); cvals.append(float(C[t]))
        ev_a.extend(at.tolist()); ev_r.extend(rt.tolist()); ev_i.extend(it.tolist())
        top_a.extend(at[:CAP].tolist()); top_r.extend(rt[:CAP].tolist())   # slot order = the ranking
        S = len(blocks)
        if S > S_RUN:
            break
        N = len(ev_a)
        niss = len(set(ev_i))
        if k < len(LOOKS) and S >= LOOKS[k] and N >= 30 and niss >= 30 and S >= 6:
            while k < len(LOOKS) and S >= LOOKS[k]:
                k += 1
            al = alpha(S)
            w = np.minimum(np.array(ns, float), CAP)
            xb = np.array(blocks)
            mean_a = math.fsum(ev_a) / N
            if mean_a < 0:
                q = mc_p(-w * xb, f"{pid}|v1|evl6|{run_tag}S{S}")
                if q <= al + 1e-12:
                    return "retire", t + 1
            mean_r = math.fsum(ev_r) / N
            ok = (mean_a > 0 and mean_r > 0 and math.fsum(top_a) > 0 and math.fsum(top_r) > 0
                  and float(np.mean(xb)) > float(np.mean(cvals)))
            if ok:
                p = mc_p(w * (xb - MARGIN), f"{pid}|v1|evl6|{run_tag}S{S}")
                if p <= al:
                    ids = np.array(ev_i); av = np.array(ev_a)
                    u, inv = np.unique(ids, return_inverse=True)
                    vals = np.bincount(inv, weights=av) / np.bincount(inv)
                    if issuer_p(vals, f"{pid}|v1|evl6|{run_tag}S{S}|issuer") <= 0.10:
                        return "pass", t + 1
        if S == S_RUN:
            return "end", t + 1
    return "open", None


def one(args):
    c, seed, lo, hi = args
    rng = np.random.default_rng(seed)
    R = c["_R"]
    g = X.generate(rng, R, c)
    out = []
    for i in range(lo, hi):
        res1, t1 = run_screen(g["a"][i], g["r"][i], g["iss"][i], g["valid"][i], g["C"][i], i, 0, "")
        p2 = False
        if res1 == "end":
            res2, t2 = run_screen(g["a"][i], g["r"][i], g["iss"][i], g["valid"][i], g["C"][i], i, 60, "run2|")
            p2 = res2 == "pass" and t2 <= 120
        out.append((i, res1 == "pass" and t1 <= 120, (res1 == "pass" and t1 <= 120) or p2))
    return out


if __name__ == "__main__":
    from multiprocessing import get_context
    spec = json.loads(sys.argv[1]) if sys.argv[1].startswith("{") else json.load(open(sys.argv[1]))
    seed, R, outp = int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
    c = dict(spec); c["_R"] = R
    t0 = time.time()
    g = X.generate(np.random.default_rng(seed), R, c)
    d, info = X.records(g, X.CAP_LEARN, control=True, seed=seed)
    fp, _, _ = X.SF.first_pass(d, "", X.RULES[22])
    _, any2 = X.SF.two_runs(d, X.RULES[22])
    fx1 = fp <= 120
    fx2 = any2 <= 120
    print(f"fixer pipeline: per run {fx1.mean():.4f}, two runs {fx2.mean():.4f} ({time.time() - t0:.0f}s)", flush=True)
    step = max(1, R // 64)
    jobs = [(c, seed, lo, min(R, lo + step)) for lo in range(0, R, step)]
    mine1 = np.zeros(R, bool); mine2 = np.zeros(R, bool)
    with get_context("fork").Pool(8) as pool:
        for k, part in enumerate(pool.imap_unordered(one, jobs), 1):
            for i, p1, p2 in part:
                mine1[i] = p1; mine2[i] = p2
            if k % 8 == 0:
                print(f"{k}/{len(jobs)} {time.time() - t0:.0f}s", flush=True)
    res = {"cell": X.label(spec), "seed": seed, "R": R,
           "fixer_run1": float(fx1.mean()), "mine_run1": float(mine1.mean()),
           "fixer_two": float(fx2.mean()), "mine_two": float(mine2.mean()),
           "both_run1": int((fx1 & mine1).sum()), "fixer_only_run1": int((fx1 & ~mine1).sum()),
           "mine_only_run1": int((~fx1 & mine1).sum()),
           "fixer_only_two": int((fx2 & ~mine2).sum()), "mine_only_two": int((~fx2 & mine2).sum()),
           "secs": round(time.time() - t0)}
    print(json.dumps(res))
    with open(outp, "a") as fh:
        fh.write(json.dumps(res) + "\n")
