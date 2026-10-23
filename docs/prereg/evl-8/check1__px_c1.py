#!/usr/bin/env python
"""px_c1.py: ADVERSARIAL CHECK #1 of PREREG-EVL-8 (statistics), the PX seats. SYNTHETIC ONLY: nothing here reads the
lane, the House, the gateway or any run record. The generator is the PX designer's (../price/px_calib.py `generate`,
imported unchanged); the screen is THE PX SCREEN (../calib/evl6d.py with looks 15..60, alpha 0.016/0.004, 10 bp margin,
guards, retirement, exhaustion at 60), exactly as ../calib/px8.py runs it under PX8_RULE=s15.

Attacks:
  TOPK   the money population: the shadow's K = 40 by the seat's ranking (slot 0 = most extreme) vs what money buys
         (the top 14 at Probe, A99; the top 4 at learning). mu is set PER RANK SLOT: the top 14 slots at mu_top, the
         rest at mu_rest. A pass when the top-14 mean is <= 0 is a pass of what money never earns. Measured with THE PX
         SCREEN as drafted and with the guard PREREG-EVL-6's check 2 proposed (the top-14 events of every block by the
         seat's ranking: their event-weighted mean a > 0 and mean r > 0 over the record).
  LOWLAM supply far below the designer's 8-40 a session (PX-GAP-O1 / PX-SURGE-ON on thin days): lam 3 and 5.
  SHARED the PX designer's family drift L_t shared by two ON seats (PX-DROP-ON and PX-SURGE-ON read one universe, one
         window, one benchmark): P(both pass) against the product of the marginals.
  GUARDPOW the power cost of the top-14 guard on a uniform edge.
Seeds 61,000,001 on (one per cell). Usage: px_c1.py run [--R 2000] [--workers 4] [--only substr]
"""
from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import os
import sys
import time

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")
import numpy as np  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
CALIB = os.path.abspath(os.path.join(HERE, "..", "calib"))
sys.path.insert(0, CALIB)
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "price")))
import px_calib as PX  # noqa: E402
import evl6d  # noqa: E402

CL = evl6d.CL
S15 = (15, 16, 18, 20, 22, 25, 30, 35, 40, 50, 60)
TOPK = 14


def to_sim(g):
    """px8.to_sim (left-packed, slot order kept: entry j of a block is the j-th ranked valid event)."""
    a, r, iss, valid, C = g["a"], g["r"], g["iss"], g["valid"], g["C"]
    order = np.argsort(~valid, axis=2, kind="stable")
    va = np.take_along_axis(valid, order, axis=2)
    aa = np.where(va, np.take_along_axis(a, order, axis=2), np.nan)
    rr = np.where(va, np.take_along_axis(r, order, axis=2), np.nan)
    ii = np.where(va, np.take_along_axis(iss, order, axis=2), -1)
    n = va.sum(axis=2)
    with np.errstate(invalid="ignore"):
        B = np.where(n > 0, np.nansum(aa, axis=2) / np.maximum(n, 1), np.nan)
        Rm = np.where(n > 0, np.nansum(rr, axis=2) / np.maximum(n, 1), np.nan)
    return {"B": B, "Rm": Rm, "n": n, "ctrl": C, "iss": ii, "a": aa, "r": rr}


def screen(sim, rep, guard=False, looks=S15):
    """evl6d.screen with THE PX SCREEN's looks; guard=True adds the top-14 money guard. (passed, session, retired)"""
    B, n, ctrl = sim["B"][rep], sim["n"][rep], sim["ctrl"][rep]
    iss, av, rv = sim["iss"][rep], sim["a"][rep], sim["r"][rep]
    T = len(B)
    blocks, bsess, ev_iss, ev_a = [], [], [], []
    ev_r = 0.0
    top_a = 0.0
    top_r = 0.0
    top_n = 0
    seen = set()
    k = 0
    for t in range(T):
        kk = int(n[t])
        if kk == 0:
            continue
        blocks.append(float(B[t]))
        bsess.append(t)
        ev_iss.extend(int(x) for x in iss[t, :kk])
        ev_a.extend(float(x) for x in av[t, :kk])
        ev_r += float(np.sum(rv[t, :kk]))
        kt = min(kk, TOPK)
        top_a += float(np.sum(av[t, :kt]))
        top_r += float(np.sum(rv[t, :kt]))
        top_n += kt
        seen.update(int(x) for x in iss[t, :kk])
        S = len(blocks)
        N = len(ev_a)
        if k < len(looks) and S >= looks[k] and S >= 6 and N >= 30 and len(seen) >= 30:
            while k < len(looks) and S >= looks[k]:
                k += 1
            al = evl6d.alpha(S)
            xb = np.array(blocks)
            mean_a = sum(ev_a) / N
            if mean_a < 0 and CL.zstat(-xb) >= 1.0 and CL.flip_p(-xb) <= al + evl6d.TIE:
                return False, -1, True
            x = xb - evl6d.MARGIN
            ok = (CL.zstat(x) >= 1.0 and mean_a > 0 and ev_r / N > 0
                  and xb.mean() > float(np.mean(ctrl[bsess])))
            if ok and guard:
                ok = top_a / top_n > 0 and top_r / top_n > 0
            if ok and CL.flip_p(x) <= al + evl6d.TIE and CL.issuer_p(ev_iss, ev_a, evl6d.B_ISS) <= evl6d.PI_MAX + evl6d.TIE:
                return True, t, False
        if S >= evl6d.HORIZON:
            return False, -1, True
    return False, -1, False


def gen_shared(rng, b, lam, nz, kcap):
    """Two ON seats in one world: the family drift L_t (AR 0.97, the cell's sd) is the SAME for both; every other piece
    (counts, issuers, day and sector shocks, the benchmark draw, events) is drawn separately (the least correlation)."""
    nz0 = dict(nz, drift=0.0)
    gA = PX.generate(rng, b, lam, nz0, 0.0, 0.0, kcap)
    gB = PX.generate(rng, b, lam, nz0, 0.0, 0.0, kcap)
    L = PX.ar(rng, b, PX.T, 0.97, nz["drift"], lambda g, s: g.normal(0, 1, s))
    for g in (gA, gB):
        g["a"] = g["a"] + L[:, :, None]
        g["r"] = g["r"] + L[:, :, None]
        g["C"] = g["C"] + 0.5 * L
    return gA, gB


def run_cell(args):
    name, kind, noise, lam, kcap, mu_top, mu_rest, mu_c, R, seed = args
    t0 = time.time()
    rng = np.random.default_rng(seed)
    out = {"cell": name, "kind": kind, "noise": noise, "lam": lam, "K": kcap, "mu_top_bp": mu_top * 1e4,
           "mu_rest_bp": mu_rest * 1e4, "ctrl_bp": mu_c * 1e4, "R": R, "seed": seed}
    done = 0
    if kind == "shared":
        pa, pb, pab = 0, 0, 0
        while done < R:
            b = min(100, R - done)
            gA, gB = gen_shared(rng, b, lam, PX.NOISE[noise], kcap)
            sA, sB = to_sim(gA), to_sim(gB)
            for i in range(b):
                x = screen(sA, i)[0]
                y = screen(sB, i)[0]
                pa += x
                pb += y
                pab += x and y
            done += b
        out.update(pass_A=pa / R, pass_B=pb / R, pass_both=pab / R, product=(pa / R) * (pb / R),
                   p_B_given_A=(pab / pa if pa else None))
    else:
        mu = np.where(np.arange(kcap) < TOPK, mu_top, mu_rest)
        res0, res1, topm = [], [], []
        while done < R:
            b = min(100, R - done)
            g = PX.generate(rng, b, lam, PX.NOISE[noise], mu, mu_c, kcap)
            sim = to_sim(g)
            for i in range(b):
                res0.append(screen(sim, i, False))
                res1.append(screen(sim, i, True))
            done += b
        p0 = np.array([x[0] for x in res0])
        p1 = np.array([x[0] for x in res1])
        r0 = np.array([x[2] for x in res0])
        out.update(pass_drafted=float(p0.mean()), pass_with_top14_guard=float(p1.mean()),
                   retired_drafted=float(r0.mean()),
                   se_drafted=float(np.sqrt(p0.mean() * (1 - p0.mean()) / R)))
    out["secs"] = round(time.time() - t0, 1)
    return out


def cells(R):
    out = []
    seed = 61_000_001

    def add(*c):
        nonlocal seed
        out.append(c + (R, seed))
        seed += 1
    # TOPK: edge only below the money's top 14 (judged a, after cost)
    for noise in ("base", "worst"):
        for mt, mr in ((0.0, 0.0040), (0.0, 0.0060), (-0.0015, 0.0060), (-0.0015, 0.0080)):
            add(f"TOPK-{noise}-top{int(mt*1e4)}-rest{int(mr*1e4)}-lam40-K40", "topk", noise, 40, 40, mt, mr, 0.0)
    # GUARDPOW: uniform edges, the guard's power cost
    for noise in ("base", "worst"):
        for m in (0.0040, 0.0060):
            add(f"GPOW-{noise}-{int(m*1e4)}-lam40-K40", "topk", noise, 40, 40, m, m, 0.0)
    # LOWLAM: thin supply, the nulls
    for noise in ("worst", "stress"):
        for lam in (3, 5):
            for null, mc in (("N0", 0.0), ("NK", -0.0030)):
                add(f"LOW-{null}-{noise}-lam{lam}-K20", "topk", noise, lam, 20, 0.0, 0.0, mc)
    # SHARED drift: two ON seats in one world (the knife edge is not needed: the control carries half the drift)
    for noise, lam, k in (("worst", 40, 40), ("worst", 20, 20), ("stress", 40, 40), ("mid", 40, 40)):
        add(f"SHARED-{noise}-lam{lam}-K{k}", "shared", noise, lam, k, 0.0, 0.0, 0.0)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("run",))
    ap.add_argument("--R", type=int, default=2000)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--only", default="")
    ap.add_argument("--out", default=os.path.join(HERE, "px_c1"))
    a = ap.parse_args()
    todo = [c for c in cells(a.R) if a.only in c[0]]
    t0 = time.time()
    with mp.Pool(min(4, a.workers)) as pool, open(a.out + ".jsonl", "a") as fh:
        for i, res in enumerate(pool.imap_unordered(run_cell, todo)):
            fh.write(json.dumps(res) + "\n")
            fh.flush()
            print(f"{i + 1}/{len(todo)} {json.dumps(res)} [{time.time() - t0:.0f}s]", flush=True)


if __name__ == "__main__":
    main()
