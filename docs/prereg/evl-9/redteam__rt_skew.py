#!/usr/bin/env python
"""rt_skew.py: does a pick set with RIGHT-SKEWED, mean-zero event returns pass PREREG-EVL-6's drafted screen more often
than the calibrated rate? (SYNTHETIC ONLY: no lane, House, gateway, store or market data is read.)

WHY (the red team): EVL-6's plausible grid has symmetric or LEFT-skewed events and jumps half down or 80% down
(evl6/PREREG-EVL-6.draft.md section 4.3). A learner trained on years of history can concentrate its picks on a
population no fixed program was calibrated on: lottery-like names (biotech catalysts, small high-volatility names)
whose event returns are right-skewed, mean zero. A one-sided sign-flip test is exact only for symmetric block values.

THE RECORD: T = 120 sessions; each session n ~ 3..8 picks (K = 8) from a population of 800 issuers (Zipf 0.8),
sigma_i log-uniform 3-8% a session; a = sigma_i e + c_t + jump - E[jump], c_t the session's day shock (rho_day 0.05
of a 5% event: sd 1.15%), e unit t(3), two-piece (left, right) scaled and re-centred to mean 0, unit variance;
jumps w.p. p_j of size +J (share q up) or -J, mean-compensated. Every event's mean a is EXACTLY 0 (the N1 null).
r = a + b_t, b_t ~ N(4 bp, 1%). Control: a 300-event pool from the same session (symmetric, mean 0, same c_t).
Screened by calib_evl7.screen_ev6 (imported unchanged), rules ev6d and ev6t.

Usage: rt_skew.py [--reps 2000]
"""
from __future__ import annotations

import os as _os
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    _os.environ.setdefault(_v, "1")
import argparse
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
EVL7 = os.path.join(os.path.dirname(os.path.dirname(HERE)), "evl7")
sys.path.insert(0, os.path.join(EVL7, "learner"))
sys.path.insert(0, os.path.join(EVL7, "calib"))
import calib_learner as cl  # noqa: E402
import calib_evl7 as ce  # noqa: E402

T, K, NI = 120, 8, 800


def two_piece(rng, size, left, right):
    x = rng.standard_t(3.0, size) / math.sqrt(3.0)
    x = np.where(x < 0, left * x, right * x)
    return x


def moments(left, right, n=2_000_000, seed=5):
    x = two_piece(np.random.default_rng(seed), n, left, right)
    return float(x.mean()), float(x.std())


CELLS = [
    dict(name="SYM", left=1.0, right=1.0, pj=0.0, J=0.0, q=0.5),
    dict(name="SYM-jumps0.5pct-30", left=1.0, right=1.0, pj=0.005, J=0.30, q=0.5),
    dict(name="LEFT-1.4/0.6-jumps80down", left=1.4, right=0.6, pj=0.005, J=0.30, q=0.2),
    dict(name="RIGHT-0.6/1.4", left=0.6, right=1.4, pj=0.0, J=0.0, q=0.5),
    dict(name="RIGHT-0.6/1.4-jumps1pct-60up", left=0.6, right=1.4, pj=0.01, J=0.60, q=1.0),
    dict(name="RIGHT-lottery-jumps3pct-100up", left=0.8, right=1.2, pj=0.03, J=1.00, q=1.0),
    # the steamroller: a small steady gain, a rare large loss (deal-break-like), mean exactly 0
    dict(name="LEFT-steamroller-sig1-jumps1pct-30down", left=1.0, right=1.0, pj=0.01, J=0.30, q=0.0, sig=(0.01, 0.01)),
    dict(name="LEFT-steamroller-sig2-jumps2pct-20down", left=1.0, right=1.0, pj=0.02, J=0.20, q=0.0, sig=(0.02, 0.02)),
    dict(name="LEFT-steamroller-sig3to8-jumps1pct-30down", left=1.0, right=1.0, pj=0.01, J=0.30, q=0.0),
]
CELLS3 = [
    dict(name="LEFT-steamroller-sig1to1.5-jumps1pct-30down", left=1.0, right=1.0, pj=0.01, J=0.30, q=0.0,
         sig=(0.010, 0.015)),
    dict(name="LEFT-steamroller-sig1to1.5-jumps0.5pct-30down", left=1.0, right=1.0, pj=0.005, J=0.30, q=0.0,
         sig=(0.010, 0.015)),
]
CELLS2 = [
    dict(name="LEFT-steamroller-sig1.5to2.5-jumps0.5pct-30down", left=1.0, right=1.0, pj=0.005, J=0.30, q=0.0,
         sig=(0.015, 0.025)),
    dict(name="LEFT-steamroller-sig1.5to2.5-jumps1pct-30down", left=1.0, right=1.0, pj=0.01, J=0.30, q=0.0,
         sig=(0.015, 0.025)),
    dict(name="LEFT-steamroller-sig1-jumps0.3pct-30down", left=1.0, right=1.0, pj=0.003, J=0.30, q=0.0, sig=(0.01, 0.01)),
    dict(name="MIX25-steamroller-sig1-jumps1pct-30down", left=1.0, right=1.0, pj=0.01, J=0.30, q=0.0, sig=(0.01, 0.01),
         mix=0.25),
    dict(name="MIX50-steamroller-sig1-jumps1pct-30down", left=1.0, right=1.0, pj=0.01, J=0.30, q=0.0, sig=(0.01, 0.01),
         mix=0.50),
]


def sim_cell(c, reps, seed):
    rng = np.random.default_rng(seed)
    m1, s1 = moments(c["left"], c["right"])
    out = dict(B=np.zeros((reps, T)), Rm=np.zeros((reps, T)), n=np.zeros((reps, T), dtype=np.int16),
               ctrl=np.zeros((reps, T)), iss=np.full((reps, T, K), -1, dtype=np.int32), a=np.full((reps, T, K), np.nan))
    logp = -0.8 * np.log(np.arange(1, NI + 1, dtype=float))
    p = np.exp(logp) / np.exp(logp).sum()
    for rep in range(reps):
        lo, hi = c.get("sig", (0.03, 0.08))
        sig = np.exp(rng.uniform(math.log(lo), math.log(hi), NI))
        sig_sym = np.exp(rng.uniform(math.log(0.03), math.log(0.08), NI))
        sd_c = math.sqrt(0.05 / 0.95) * math.sqrt(lo * hi)
        for t in range(T):
            n = int(rng.integers(3, K + 1))
            ids = rng.choice(NI, size=n, replace=False, p=p)
            e = (two_piece(rng, n, c["left"], c["right"]) - m1) / s1
            jmp = np.where(rng.random(n) < c["pj"], np.where(rng.random(n) < c["q"], c["J"], -c["J"]), 0.0)
            jmp = jmp - c["pj"] * c["J"] * (2 * c["q"] - 1)
            ct = sd_c * cl.unit_t3(rng, 1)[0]
            sg = sig[ids]
            if c.get("mix") is not None:
                steam = rng.random(n) < c["mix"]
                sg = np.where(steam, sg, sig_sym[ids])
                jmp = np.where(steam, jmp, 0.0)
            a = np.maximum(sg * e + ct + jmp, -1.0)
            bt = rng.normal(0.0004, 0.01)
            out["B"][rep, t] = a.mean()
            out["Rm"][rep, t] = (a + bt).mean()
            out["n"][rep, t] = n
            out["ctrl"][rep, t] = ct + 0.05 * rng.standard_normal() / math.sqrt(300)
            out["iss"][rep, t, :n] = ids
            out["a"][rep, t, :n] = a
    res = {}
    for rule in ("ev6d", "ev6t"):
        ps = [ce.screen_ev6(out, rep, rule)[0] for rep in range(reps)]
        res[rule] = float(np.mean(ps))
        # the same screen with the TOP-TRIM guard inside the PASS (section: the red team's guard G-SKEW)
        pt = [screen_trim(out, rep, rule)[0] for rep in range(reps)]
        res[rule + "_trim"] = float(np.mean(pt))
    # the block values' skewness (pooled)
    B = out["B"].ravel()
    sk = float(((B - B.mean()) ** 3).mean() / B.std() ** 3)
    return res, sk


def screen_trim(sim, rep, rule, trim_share=0.01):
    """calib_evl7.screen_ev6 with one more PASS condition: the record's mean a with its top max(1, floor(N x
    trim_share)) events by a removed is > 0 (a pass may not rest on a few lottery wins)."""
    P = ce.RULES[rule]
    B, Rm, n, ctrl = sim["B"][rep], sim["Rm"][rep], sim["n"][rep], sim["ctrl"][rep]
    iss, av = sim["iss"][rep], sim["a"][rep]
    blocks, bsess, ev_iss, ev_a = [], [], [], []
    ev_r_sum = 0.0
    seen = set()
    k = 0
    for t in range(len(B)):
        kk = int(n[t])
        if kk == 0:
            continue
        a_t = av[t, :kk].astype(float)
        blocks.append(float(a_t.mean()))
        bsess.append(t)
        ev_iss.extend(int(x) for x in iss[t, :kk])
        ev_a.extend(float(x) for x in a_t)
        ev_r_sum += float(Rm[t]) * kk
        seen.update(int(x) for x in iss[t, :kk])
        S, N = len(blocks), len(ev_a)
        look = False
        if k < len(ce.EV6_LOOKS) and S >= ce.EV6_LOOKS[k] and N >= ce.MIN_N and len(seen) >= ce.MIN_ISS:
            look = True
            while k < len(ce.EV6_LOOKS) and S >= ce.EV6_LOOKS[k]:
                k += 1
        if look:
            alpha = P["a_lo"] if S <= P["s_sw"] else P["a_hi"]
            xb = np.array(blocks)
            mean_a = sum(ev_a) / N
            if mean_a < 0 and cl.zstat(-xb) >= cl.Z_PRE and cl.flip_p(-xb) <= alpha + cl.TIE:
                return False, -1
            x = xb - P["m0"]
            if cl.zstat(x) >= cl.Z_PRE and cl.flip_p(x) <= alpha + cl.TIE and mean_a > 0 and ev_r_sum / N > 0:
                cm = float(np.mean(ctrl[bsess]))
                drop = max(1, int(N * trim_share))
                trimmed = np.sort(np.array(ev_a))[:-drop]
                if (xb.mean() > cm and cl.issuer_p(ev_iss, ev_a, cl.B_ISS6) <= ce.ISS_ALPHA + cl.TIE
                        and trimmed.mean() > 0):
                    return True, t
        if S >= ce.HORIZON:
            return False, -1
    return False, -1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=2000)
    ap.add_argument("--set", default="1")
    a = ap.parse_args()
    rows = []
    cells = {"1": CELLS, "2": CELLS2, "3": CELLS3}[a.set]
    off = {"1": 0, "2": 100, "3": 200}[a.set]
    for i, c in enumerate(cells):
        res, sk = sim_cell(c, a.reps, 96_000_001 + off + i)
        se = {k: math.sqrt(v * (1 - v) / a.reps) for k, v in res.items()}
        row = dict(cell=c["name"], reps=a.reps, block_skew=round(sk, 3), **{f"{k}_pass": round(v, 4) for k, v in res.items()},
                   **{f"{k}_se": round(v, 4) for k, v in se.items()})
        rows.append(row)
        print(json.dumps(row), flush=True)
    with open(os.path.join(HERE, f"rt_skew.out{'' if a.set == '1' else a.set}.jsonl"), "w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


if __name__ == "__main__":
    main()
