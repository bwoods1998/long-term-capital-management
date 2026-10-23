#!/usr/bin/env python
"""px_demotion8.py: the captain's F3 for PREREG-EVL-8 (SYNTHETIC ONLY): the false-demotion rate of a TRUE PX edge under
PREREG-EVL-6 section 3's FROZEN demotion (its three triggers, word for word), with up to 14 Probe buys a session
sharing one day shock, on px_final8.py's generator (the PX designer's, with the frozen plausible grid's day shapes).

Nothing here reads the lane, the House, the gateway or any market data. Every number comes from the generator.

A PROBE STAY of one PX seat (demotion_v2.py's stay, ported to the PX paths): its shadow record is every event of the
seat (the shadow's K), ranked by the seat's own order (the generator's slot order, uninformative about returns); real
money buys the top min(n_s, 14) events a session at Probe (A99's 14 slots, at-size lots of $67.9, EVL-6 section 4.8's
mean) and the top min(n_s, 8) at Sized ($190 lots); r = a + m_t (the benchmark's window return), the judged cost
basis (conservative: a Probe lot's fees are 6-8 bp a round trip against the replay's 14.16 bp). THE TRIGGERS, in
PREREG-EVL-6 section 3's order at each close once that session's real-money events have settled:
  3. THE STAY'S FIXED READS: at the stay's 100th, 200th, ... real-money Probe+ event (ordered by session, then rank),
     the one-sided session-block sign-flip p for a mean BELOW zero over ALL its real-money events so far, block value
     the mean of a session's events' r (the last block may be partial), <= 0.15 + 1e-12 (exact <= 16 blocks, else
     demotion_final.p_rows's vectors);
  1. THE MONEY STOP: the stay's real-money events so far have lost, net, more than 10% of their summed buy cost;
  2. THE STAY'S LOWER TAIL at a stay look: the stay record's mean a < 0 and q <= alpha(S) + 1e-12 (q on the values
     -min(n_s, CAP) B_s, CAP the band's open cap: 14 at Probe, 8 at Sized). The lower tail is read at PREREG-EVL-6's
     frozen looks from the 22nd stay block (check 2's minor 15: demoting sooner trades less).
SIZED at a stay look of THE PX SCREEN's schedule (looks from --pass-start, alpha by S): p <= alpha(S) on
min(n_s, 14) x (B_s - 10 bp), mean a > 0, mean r > 0, the top-14 means a > 0 and r > 0 (the control and issuer guards
taken as holding: more Sized, larger lots, more money-stop exposure), and >= 30 real-money events whose summed P&L > 0.
Reported: P(demoted by the stay's 300th / 1,000th / 2,000th / 3,000th Probe+ event), combined and by trigger, and the
share of stays that reach each horizon (a figure where fewer than 99% reach it is a lower bound).

Usage: px_demotion8.py --pass-start F [--workers 8] [--out FILE] [--only SUBSTR] [--R N]
"""
from __future__ import annotations

import os

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import argparse  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import px_final8 as X  # noqa: E402  (imports PREREG-EVL-6's frozen calib_final / search_final and the PX generator)

import numpy as np  # noqa: E402

CF, SF, PX = X.CF, X.SF, X.PX
sys.path.insert(0, X.EVL6F)
import demotion_final as DF  # noqa: E402  (PREREG-EVL-6's frozen read p, unchanged)

TIE = 1e-12
CAP_P, CAP_S = 14, 8
LOT_P, LOT_S = 67.9, 190.0
READ_EVERY, READ_P, STOP = 100, 0.15, 0.10
N_MAX = 3000
HORIZONS = (100, 300, 500, 1000, 2000, 3000)


def stay(g, pass_start, seed):
    a, r, valid = g["a"], g["r"], g["valid"]
    R, Tn, K = a.shape
    iss = g["iss"]
    rows = np.arange(R)
    tail_sl = np.array([s for s in SF.LOOKS if s >= 22])
    pass_sl = np.array([s for s in SF.LOOKS if s >= pass_start])
    pass_rule = SF.Rule(pass_start, X.PIECES)
    tail_rule = SF.Rule(22, X.PIECES)
    Xb = np.zeros((R, CF.S_RUN + 1)); W = np.zeros((R, CF.S_RUN + 1)); S = np.zeros(R, np.int64)
    ca = np.zeros(R); cr = np.zeros(R); ne = np.zeros(R, np.int64); ta = np.zeros(R); tr = np.zeros(R)
    seen = np.zeros((R, X.NPOOL), bool); niss = np.zeros(R, np.int64)
    nxt_t = np.zeros(R, np.int64); nxt_p = np.zeros(R, np.int64)
    band = np.zeros(R, np.int8); why = np.zeros(R, np.int8)
    nreal = np.zeros(R, np.int64)
    pnl_cum = np.zeros((R, N_MAX + 200 + 1)); cost_cum = np.zeros((R, N_MAX + 200 + 1))
    blk_sum = np.zeros((R, N_MAX + 1)); blk_n = np.zeros((R, N_MAX + 1), np.int64); nblk = np.zeros(R, np.int64)
    dem_at = np.full(R, 10 ** 6, np.int64)
    next_read = np.full(R, READ_EVERY, np.int64)
    sized_at = np.full(R, -1, np.int64)
    for t in range(Tn):
        live = (band < 2) & (nreal < N_MAX)
        if not live.any():
            break
        v = valid[:, t, :]
        rank = np.cumsum(v, axis=1)
        at = np.where(v, a[:, t, :], 0.0)
        rt = np.where(v, r[:, t, :], 0.0)
        nP = v.sum(axis=1)
        has = (nP > 0) & live
        sP = at.sum(axis=1); sR = rt.sum(axis=1)
        top = v & (rank <= CAP_P)
        hr = np.nonzero(has)[0]
        ok = hr[S[hr] <= CF.S_RUN]
        Xb[ok, S[ok]] = sP[ok] / nP[ok]
        W[ok, S[ok]] = nP[ok]
        S[hr] += 1
        ca += np.where(has, sP, 0.0); cr += np.where(has, sR, 0.0); ne += np.where(has, nP, 0)
        ta += np.where(has, np.where(top, at, 0.0).sum(axis=1), 0.0)
        tr += np.where(has, np.where(top, rt, 0.0).sum(axis=1), 0.0)
        er, ek = np.nonzero(v & has[:, None])
        if er.size:
            ei = iss[:, t, :][er, ek]
            newi = ~seen[er, ei]
            seen[er, ei] = True
            niss += np.bincount(er[newi], minlength=R)
        mn = (ne >= CF.MIN_EV) & (niss >= CF.MIN_ISS) & (S >= CF.MIN_BLK)
        thr_t = tail_sl[np.minimum(nxt_t, tail_sl.size - 1)]
        lk_t = has & mn & (S <= CF.S_RUN) & (nxt_t < tail_sl.size) & (S >= thr_t)
        lt_rows = np.nonzero(lk_t)[0]
        if lt_rows.size:
            nxt_t[lt_rows] = (S[lt_rows][:, None] >= tail_sl[None, :]).sum(axis=1)
        thr_p = pass_sl[np.minimum(nxt_p, pass_sl.size - 1)]
        lk_p = has & mn & (S <= CF.S_RUN) & (nxt_p < pass_sl.size) & (S >= thr_p)
        lp_rows = np.nonzero(lk_p)[0]
        if lp_rows.size:
            nxt_p[lp_rows] = (S[lp_rows][:, None] >= pass_sl[None, :]).sum(axis=1)
        cap_r = np.where(band == 1, CAP_S, CAP_P)
        lot_r = np.where(band == 1, LOT_S, LOT_P)
        real = v & (rank <= cap_r[:, None]) & live[:, None]
        m = real.sum(axis=1)
        for rr_ in np.nonzero(m > 0)[0]:
            vals = rt[rr_][real[rr_]]                        # in rank order
            k0 = int(nreal[rr_])
            k1 = min(k0 + vals.size, N_MAX + 200)
            vals = vals[:k1 - k0]
            pnl_cum[rr_, k0 + 1:k1 + 1] = pnl_cum[rr_, k0] + np.cumsum(lot_r[rr_] * vals)
            cost_cum[rr_, k0 + 1:k1 + 1] = cost_cum[rr_, k0] + lot_r[rr_] * np.arange(1, k1 - k0 + 1)
            while next_read[rr_] <= k1 and band[rr_] < 2:
                j = int(next_read[rr_] - k0)
                nb = int(nblk[rr_])
                Vb = list(blk_sum[rr_, :nb] / np.maximum(blk_n[rr_, :nb], 1)) + [float(vals[:j].mean())]
                if DF.p_rows(-np.array(Vb)[None, :])[0] <= READ_P + TIE:
                    band[rr_] = 2; why[rr_] = 3; dem_at[rr_] = int(next_read[rr_])
                next_read[rr_] += READ_EVERY
            if band[rr_] < 2:
                if nblk[rr_] <= N_MAX:
                    blk_sum[rr_, nblk[rr_]] = vals.sum(); blk_n[rr_, nblk[rr_]] = vals.size; nblk[rr_] += 1
                nreal[rr_] = k1
        alive = (band < 2) & (m > 0)
        hit_stop = alive & (pnl_cum[rows, nreal] < -STOP * cost_cum[rows, nreal])
        band[hit_stop] = 2; why[hit_stop] = 1; dem_at[hit_stop] = nreal[hit_stop]
        if lt_rows.size:
            lr = lt_rows[(band[lt_rows] < 2) & (ca[lt_rows] < 0)]
            for Sv in np.unique(S[lr]):
                rs = lr[S[lr] == Sv]
                capv = np.where(band[rs] == 1, CAP_S, CAP_P)[:, None]
                Y = -np.minimum(W[rs, :Sv], capv) * Xb[rs, :Sv]
                q = CF.signflip_p_rows(Y, int(Sv))
                hitq = q <= tail_rule.alpha(np.full(rs.size, Sv)) + TIE
                band[rs[hitq]] = 2; why[rs[hitq]] = 2; dem_at[rs[hitq]] = nreal[rs[hitq]]
        if lp_rows.size:
            pr_ = lp_rows[(band[lp_rows] == 0) & (ca[lp_rows] > 0) & (cr[lp_rows] > 0) & (ta[lp_rows] > 0)
                          & (tr[lp_rows] > 0)]
            for Sv in np.unique(S[pr_]):
                rs = pr_[S[pr_] == Sv]
                Y = np.minimum(W[rs, :Sv], CAP_P) * (Xb[rs, :Sv] - CF.MARGIN)
                p = CF.signflip_p_rows(Y, int(Sv))
                k = nreal[rs]
                go = (p <= pass_rule.alpha(np.full(rs.size, Sv))) & (k >= 30) & (pnl_cum[rs, k] > 0)
                band[rs[go]] = 1; sized_at[rs[go]] = k[go]
    end_k = np.minimum(np.where(dem_at < 10 ** 6, dem_at, nreal), N_MAX + 200)
    return {"dem_at": dem_at, "why": why, "nreal": nreal, "sized_at": sized_at, "pnl_end": pnl_cum[rows, end_k]}


def cells():
    out = []
    cor = dict(sd_c=0.022, phi=0.20, drift=0.0020, mu_c=0.0)
    for day in ("crasht3cl", "crashcl", "crasht3", "crash"):
        for ev in ("t3", "skew"):
            out.append((f"40bp|{day}|{ev}|rho15 phi.20 d20", X.cell(day=day, ev=ev, lam=40, K=40, mu=0.0040, **cor), 2000, 300))
    for day in ("crasht3cl", "crash"):
        for ev in ("t3", "skew"):
            out.append((f"40bp|{day}|{ev}|rho15 phi.20 d20", X.cell(day=day, ev=ev, lam=20, K=20, mu=0.0040, **cor), 2000, 360))
            out.append((f"40bp|{day}|{ev}|rho15 phi.20 d20", X.cell(day=day, ev=ev, lam=8, K=20, mu=0.0040, **cor), 2000, 420))
            out.append((f"60bp|{day}|{ev}|rho15 phi.20 d20", X.cell(day=day, ev=ev, lam=40, K=40, mu=0.0060, **cor), 2000, 300))
            out.append((f"0bp (a false pass's stay)|{day}|{ev}|rho15 phi.20 d20",
                        X.cell(day=day, ev=ev, lam=40, K=40, mu=0.0, **cor), 2000, 300))
    b = PX.NOISE["base"]
    for mu, nm in ((0.0040, "40bp"), (0.0060, "60bp"), (0.0, "0bp (a false pass's stay)"), (-0.0015, "-15bp (cost only)")):
        for lam, K, Tn in ((40, 40, 300), (8, 20, 420)):
            out.append((f"{nm}|base (the PX designer's)", dict(X.cell(sd_c=b["sd_c"], phi=0.10, day="t3", ev="t3", lam=lam,
                                                                     K=K, mu=mu, mu_c=0.0, crash_m=False), beta=1.0,
                                                              tau=0.0), 2000, Tn))
    for nz in ("worst", "stress"):
        d = PX.NOISE[nz]
        out.append((f"40bp|STRESS the PX designer's {nz} (phi .25)",
                    dict(X.cell(sd_c=d["sd_c"], phi=d["phi"], day=d["day"], drift=d["drift"], ev=d["ev"], lam=40, K=40,
                                crash_m=d["crash_m"], dshare=d["dshare"], mu=0.0040, mu_c=0.0), beta=d["beta"],
                         tau=d["tau"], sig=d["sig"], pj=d["pj"]), 2000, 300))
    out.append(("40bp|STRESS crasht3cl skew rho15 phi.25 d20",
                X.cell(sd_c=0.022, phi=0.25, day="crasht3cl", ev="skew", drift=0.0020, lam=40, K=40, mu=0.0040, mu_c=0.0),
                2000, 300))
    return out


def _job(args):
    lab, c, R, Tn, seed, pass_start = args
    t0 = time.time()
    rng = np.random.default_rng(seed)
    g = X.generate(rng, R, c, Tn=Tn)
    res = stay(g, pass_start, seed)
    return lab, c, R, Tn, seed, {k: v.tolist() for k, v in res.items()}, time.time() - t0


def summarize(rows):
    groups: dict = {}
    for lab, c, R, Tn, seed, res, secs in rows:
        groups.setdefault((lab, c["lam"]), []).append((res, seed))
    out = []
    for (lab, lam), rs in sorted(groups.items()):
        cat = {k: np.concatenate([np.array(r[k]) for r, _ in rs]) for k in rs[0][0]}
        dem, why, nreal, sized = cat["dem_at"], cat["why"], cat["nreal"], cat["sized_at"]
        row = {"cell": lab, "lam": lam, "R": int(dem.size), "seeds": [min(s for _, s in rs), max(s for _, s in rs)]}
        for k in HORIZONS:
            reach = float(np.mean((nreal >= k) | (dem <= k)))
            row[f"by{k}_reached"] = round(reach, 4)
            row[f"by{k}"] = round(float(np.mean(dem <= k)), 4)
            for code, nm in ((1, "stop"), (2, "tail"), (3, "read")):
                row[f"by{k}_{nm}"] = round(float(np.mean((dem <= k) & (why == code))), 4)
        row["se1000"] = round(math.sqrt(max(row["by1000"] * (1 - row["by1000"]), 1e-12) / dem.size), 4)
        row["sized"] = round(float(np.mean(sized >= 0)), 4)
        row["mean_pnl_usd"] = round(float(np.mean(cat["pnl_end"])), 1)
        row["mean_real_events_of_first_1000"] = round(float(np.mean(np.minimum(np.where(dem < 10 ** 6, dem, nreal), 1000))), 1)
        out.append(row)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--pass-start", type=int, required=True)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--out", default=os.path.join(HERE, "px_demotion8.json"))
    ap.add_argument("--only", default="")
    ap.add_argument("--R", type=int, default=0)
    ap.add_argument("--seed0", type=int, default=178_000_000)
    ap.add_argument("--chunk", type=int, default=200)
    a = ap.parse_args()
    from multiprocessing import get_context
    jobs = []
    seed = a.seed0
    for lab, c, R, Tn in cells():
        if a.only and not any(o in lab for o in a.only.split("+")):
            continue
        R = a.R or R
        for k in range(0, R, a.chunk):
            seed += 1
            jobs.append((lab, c, min(a.chunk, R - k), Tn, seed, a.pass_start))
    jobs.sort(key=lambda j: -j[1]["lam"] * j[3])
    t0 = time.time()
    done = []
    with get_context("fork").Pool(min(a.workers, 8)) as pool:
        for k, row in enumerate(pool.imap_unordered(_job, jobs), 1):
            done.append(row)
            if k % 10 == 0 or k == len(jobs):
                print(f"{k}/{len(jobs)} {time.time() - t0:.0f}s", flush=True)
    summ = summarize(done)
    json.dump({"pass_start": a.pass_start, "seed0": a.seed0, "rows": summ}, open(a.out, "w"), indent=1)
    for r_ in summ:
        print(json.dumps({k: r_[k] for k in ("cell", "lam", "R", "by300", "by1000", "by1000_reached", "by2000",
                                              "by2000_reached", "by3000", "by3000_reached", "by1000_read",
                                              "by1000_stop", "by1000_tail", "sized", "se1000")}))
