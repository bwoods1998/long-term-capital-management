#!/usr/bin/env python
"""cal_cost7.py: SYNTHETIC calibration of COST-7 (the honest cost basis of EXEC-7) and FILL-7's selection charge.

SYNTHETIC ONLY: no lane data, no market data, no outcome of any event is read. See simlib.py for the generator.

What it measures
1. THE SELECTION CHARGE G (FILL-7): real-money entry attempts of the whole lane (Poisson(27) a session, the Oct 20-21
   count of sent event buys), each filled with the session's fill probability p_t ~ Beta(3, 1) (mean 0.75: A80's
   measured quarter of venue cancels, clustered by session as Oct 21's seven were); an unfilled attempt's shadow
   abnormal return carries +D, so that the TRUE shortfall of fills against attempts is G_true = 0.25 D. The rule:
   at checkpoints of 100, 200, 400, ... settled TRADABLE attempts, G_w = (1/n_F) sum_s k_s (mean_s,A - mean_s,F)
   (within session, so day shocks cancel), its EXACT within-session permutation sd
   SE = sqrt(sum_s k_s (n_s - k_s) / (n_s - 1) v_s) / n_F (v_s the session's population variance), and the charge
   in force G(t) = max(G(t-1), max(0, G_w - Z_G SE)) once n_U >= 10.
2. THE SLIPPAGE RATCHET M (COST-7): per side about 20 real fills a session; fills at the auction print have gap 0
   (EXECUTION-FACTS: 84 of 84); an EPISODE from session 20 puts 30% of fills at N(15, 10) bp worse (mean 4.5 bp a
   side). M_side(t) = max(M0, M_side(t-1), UCB_side(t)), UCB = mean + 1.645 SE over the trailing 250 fills, SE across
   sessions (session-clustered).
3. THE SCREEN'S FALSE PASSES against the REAL-MONEY null (true real after-cost mean exactly 0): judged a7 = real a +
   shift(t), shift(t) = d_imp + slip_true_RT(t) + G_true - (M_in(t) + M_out(t)) - G(t), applied to the whole record at
   each look (the cost basis in force at the look). Scenarios: base (shift -5 bp), the impact model wrong by its margin
   (d_imp +5: shift 0, the screen's own knife edge), hidden adverse selection 10/20/40 bp with the ratchet on and off,
   a slippage episode on and off, and the impact model wrong by twice its margin (d_imp +10).
4. POWER at true real after-cost edges 10, 20, 30, 60 bp an event: COST-7 (shift -5 bp) against today's replay costs
   (overcharge of 12 bp a round trip, liquid names, and 20 bp, thin names), at m0 = 0 and 10 bp.

Usage: cal_cost7.py [--R 2000] [--workers 4] [--out cal_cost7.out.json]
"""
from __future__ import annotations

import argparse
import json
import math
import multiprocessing as mp
import sys
import time

import numpy as np

import simlib as L

T = 120
M0 = 2.5e-4          # bp a side, as a return fraction
Z_G = 0.84
CHECKS = (100, 200, 400, 800, 1600, 3200, 6400)
ATT_RATE = 27.0
FILLS_SIDE = 20.0
CELLS = {
    "base": dict(rho_day=0.05, day="t3", drift_sd=0.0),
    "mid": dict(rho_day=0.05, day="crash", drift_sd=0.0010),
    "worst": dict(rho_day=0.15, day="crash", drift_sd=0.0020),
}


def lane_G(seed, R, cell, G_true, ratchet=True, z_g=Z_G):
    """The charge G(t) in force after each session t (R x T), and its record."""
    rng = np.random.default_rng(seed)
    dp = L.DayProcess(rng, R, **cell)
    D = G_true / 0.25
    # cumulative sufficient statistics
    n_cum = np.zeros(R)
    nF = np.zeros(R)
    nU = np.zeros(R)
    gnum = np.zeros(R)     # sum_s k_s (mean_A - mean_F)
    vsum = np.zeros(R)     # sum_s k_s (n_s - k_s)/(n_s - 1) v_s
    Gt = np.zeros((R, T))
    G = np.zeros(R)
    nxt = np.zeros(R, np.int64)  # next checkpoint index
    rows = np.arange(R)
    first_charge = np.full(R, -1)
    for t in range(T):
        c, Dd, h, b = dp.step()
        n = rng.poisson(ATT_RATE, R)
        tot = int(n.sum())
        er = np.repeat(rows, n)
        a = Dd[er] + h[er] * (c[er] + L.event_noise(rng, tot))
        p = rng.beta(3.0, 1.0, R)
        f = rng.random(tot) < p[er]
        a = a + np.where(f, 0.0, D)
        sA = np.bincount(er, a, R)
        sF = np.bincount(er, a * f, R)
        k = np.bincount(er, f.astype(float), R)
        s2 = np.bincount(er, a * a, R)
        nn = n.astype(float)
        mA = np.where(nn > 0, sA / np.maximum(nn, 1), 0.0)
        mF = np.where(k > 0, sF / np.maximum(k, 1), 0.0)
        v = np.where(nn > 0, s2 / np.maximum(nn, 1) - mA * mA, 0.0)
        use = (k > 0) & (k < nn)
        gnum += np.where(use, k * (mA - mF), 0.0)
        vsum += np.where(use & (nn > 1), k * (nn - k) / np.maximum(nn - 1, 1) * v, 0.0)
        n_cum += nn
        nF += k
        nU += nn - k
        if ratchet:
            while True:
                due = (nxt < len(CHECKS)) & (n_cum >= np.array(CHECKS)[np.minimum(nxt, len(CHECKS) - 1)])
                if not due.any():
                    break
                gw = gnum / np.maximum(nF, 1)
                se = np.sqrt(vsum) / np.maximum(nF, 1)
                cand = np.maximum(0.0, gw - z_g * se)
                upd = due & (nU >= 10)
                newG = np.where(upd, np.maximum(G, cand), G)
                ch = (newG > G) & (first_charge < 0)
                first_charge[ch] = t
                G = newG
                nxt = np.where(due, nxt + 1, nxt)
        Gt[:, t] = G
    return Gt, first_charge


def lane_M(seed, R, episode, ratchet=True):
    """M_in(t) + M_out(t) in force after each session (R x T) and the true slippage round trip (R x T)."""
    rng = np.random.default_rng(seed)
    Mt = np.zeros((R, T))
    slip = np.zeros((R, T))
    M = {"in": np.full(R, M0), "out": np.full(R, M0)}
    hist = {"in": [], "out": []}   # per session: (n, sum, sumsq)
    for t in range(T):
        on = episode and t >= 20
        for side in ("in", "out"):
            n = rng.poisson(FILLS_SIDE, R)
            # per-session sums of gaps: 30% of fills N(15, 10) bp when on, else 0
            if on:
                m = rng.binomial(n, 0.30)
                tot = int(m.sum())
                g = 0.0015 + 0.0010 * rng.standard_normal(tot)
                er = np.repeat(np.arange(R), m)
                s = np.bincount(er, g, R)
            else:
                s = np.zeros(R)
            hist[side].append((n.astype(float), s))
            if ratchet:
                # trailing sessions holding >= 250 fills (about 12 sessions)
                nsum = np.zeros(R)
                means = []
                ns = []
                for j in range(len(hist[side]) - 1, -1, -1):
                    nj, sj = hist[side][j]
                    means.append(np.where(nj > 0, sj / np.maximum(nj, 1), 0.0))
                    ns.append(nj)
                    nsum += nj
                    if (nsum >= 250).all() or len(means) >= 30:
                        break
                Ms = np.array(means)
                Ns = np.array(ns)
                w = Ns / np.maximum(Ns.sum(axis=0), 1)
                mean = (w * Ms).sum(axis=0)
                k = Ms.shape[0]
                if k >= 3:
                    var_b = ((Ms - Ms.mean(axis=0)) ** 2).sum(axis=0) / (k - 1)
                    ucb = mean + 1.645 * np.sqrt(var_b / k)
                    ok = nsum >= 30
                    M[side] = np.where(ok, np.maximum(M[side], ucb), M[side])
        Mt[:, t] = M["in"] + M["out"]
        slip[:, t] = (0.30 * 0.0015 * 2.0) if on else 0.0
    return Mt, slip


def job(args):
    kind, cell_name, nbar, scen, R, seed = args
    cell = CELLS[cell_name]
    t0 = time.time()
    B, BR, N = L.gen_blocks(seed, R, T, nbar, **cell)
    Xc, Rc, Nc, cnt, sess = L.compress(B, N, BR)
    out = {"kind": kind, "cell": cell_name, "nbar": nbar, "scen": scen, "R": R}
    if kind == "fp":
        name, d_imp, G_true, episode, ratchet, z_g = scen
        Gt, fc = lane_G(seed + 1, R, cell, G_true, ratchet=ratchet, z_g=z_g)
        Mt, slip = lane_M(seed + 2, R, episode, ratchet=ratchet)
        shift = d_imp + slip + G_true - Mt - Gt
        first = L.screen_first_pass(Xc, Rc, Nc, cnt, sess, shift=shift, m0=0.0)
        out.update(name=name, fp60=float(np.mean((first >= 0) & (first < 60))), fp120=float(np.mean(first >= 0)),
                   shift_mean_t20=float(shift[:, 19].mean() * 1e4), shift_mean_t60=float(shift[:, 59].mean() * 1e4),
                   shift_mean_t119=float(shift[:, 119].mean() * 1e4),
                   G_t20=float(Gt[:, 19].mean() * 1e4), G_t60=float(Gt[:, 59].mean() * 1e4),
                   G_t119=float(Gt[:, 119].mean() * 1e4), G_any=float(np.mean(Gt[:, 119] > 0)),
                   G_first_med=float(np.median(fc[fc >= 0])) if (fc >= 0).any() else None,
                   M_t60=float(Mt[:, 59].mean() * 1e4), M_t119=float(Mt[:, 119].mean() * 1e4))
    else:
        name, edge, shift0, m0 = scen
        shift = np.full((R, T), edge + shift0)
        first = L.screen_first_pass(Xc, Rc, Nc, cnt, sess, shift=shift, m0=m0)
        out.update(name=name, edge_bp=edge * 1e4, shift_bp=shift0 * 1e4, m0_bp=m0 * 1e4,
                   **{f"by{s}": float(np.mean((first >= 0) & (first < s))) for s in (10, 20, 40, 60, 120)},
                   med=float(np.median(np.where(first >= 0, first + 1, 10 ** 6))) if (first >= 0).mean() >= 0.5 else None)
    out["secs"] = round(time.time() - t0, 1)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--R", type=int, default=2000)
    ap.add_argument("--Rp", type=int, default=1000)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--out", default="cal_cost7.out.jsonl")
    ap.add_argument("--quick", action="store_true")
    a = ap.parse_args()
    bp = 1e-4
    fp_scen = []
    for z_g in (0.84, 1.645):
        fp_scen += [
            (f"A base (true cost = model) zG={z_g}", 0.0, 0.0, False, True, z_g),
            (f"B impact model short by its margin (+5 bp) zG={z_g}", 5 * bp, 0.0, False, True, z_g),
            (f"C hidden selection 10 bp, ratchet zG={z_g}", 0.0, 10 * bp, False, True, z_g),
            (f"C hidden selection 20 bp, ratchet zG={z_g}", 0.0, 20 * bp, False, True, z_g),
            (f"C hidden selection 40 bp, ratchet zG={z_g}", 0.0, 40 * bp, False, True, z_g),
            (f"D slippage episode 9 bp RT from s20, ratchet zG={z_g}", 0.0, 0.0, True, True, z_g),
            (f"E impact model short by 2x margin (+10 bp) zG={z_g}", 10 * bp, 0.0, False, True, z_g)]
    fp_scen += [
        ("A0 base, NO ratchet", 0.0, 0.0, False, False, 0.0),
        ("B0 impact short by margin, NO ratchet", 5 * bp, 0.0, False, False, 0.0),
        ("C hidden selection 10 bp, NO ratchet", 0.0, 10 * bp, False, False, 0.0),
        ("C hidden selection 20 bp, NO ratchet", 0.0, 20 * bp, False, False, 0.0),
        ("C hidden selection 40 bp, NO ratchet", 0.0, 40 * bp, False, False, 0.0),
        ("D slippage episode 9 bp RT from s20, NO ratchet", 0.0, 0.0, True, False, 0.0)]
    pw_scen = []
    for edge in (10, 20, 30, 60):
        for nm, s0 in (("COST-7", -5), ("replay liquid", -12), ("replay thin", -20)):
            for m0 in (0, 10):
                pw_scen.append((f"{nm} m0={m0}", edge * bp, s0 * bp, m0 * bp))
    jobs = []
    seed = 7_100_001
    cells = ["base", "mid", "worst"] if not a.quick else ["base"]
    nbars = (13, 30) if not a.quick else (13,)
    for cn in cells:
        for nb in nbars:
            for sc in fp_scen:
                jobs.append(("fp", cn, nb, sc, a.R, seed))
            seed += 10
    for cn in (["base", "worst"] if not a.quick else ["base"]):
        for nb in nbars:
            for sc in pw_scen:
                jobs.append(("pw", cn, nb, sc, a.Rp, seed))
            seed += 10
    t0 = time.time()
    with mp.Pool(a.workers) as pool, open(a.out, "w") as fh:
        for i, r in enumerate(pool.imap_unordered(job, jobs), 1):
            fh.write(json.dumps(r) + "\n")
            fh.flush()
            if i % 10 == 0:
                print(f"{i}/{len(jobs)} {time.time() - t0:.0f}s", file=sys.stderr, flush=True)
    print(f"done {len(jobs)} jobs {time.time() - t0:.0f}s", file=sys.stderr)


if __name__ == "__main__":
    main()
