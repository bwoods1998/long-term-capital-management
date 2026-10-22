#!/usr/bin/env python
"""demotion_final.py: PREREG-EVL-6 section 3's demotion, all three triggers together (SYNTHETIC ONLY).

A Probe STAY of one program on calib_final.py's generator (crash days, skewed events, drift, day-shock momentum, the
volatility regime, sigma_i 1-10% t(3), +-30% jumps, sector and style factors), the program's true edge on all its
events. Each session the program has n_s TRADABLE shadow events; real money buys its top min(n_s, 14) by its own
ranking at Probe (A99: at most 14 open, each lot at Done's size: the mean at-size lot $67.9 = 1.022 x a 3.5% target
of E = $1,898, A98) and its top min(n_s, 8) at Sized (10% target: $190 a lot, at most 8 open). A lot's P&L = lot x r,
r the event's after-cost return (the shadow's; fills at the auction price, so the fill-based after-fee r is at least
this: conservative). The stay is demoted at the first of:
  1. THE MONEY STOP (stay-limited): after each session's settlements, the stay's last 50 settled real-money Probe+
     events (all of them when fewer than 50) lost more than $150 net;
  2. THE STAY'S LOWER TAIL: at a stay look (this file's schedule and alpha(S), the stay's own shadow record, its 60th
     block the last), mean a < 0 and q <= alpha(S) + 1e-12, q the weighted lower-tail sign-flip;
  3. THE FIXED READS (D3): at the stay's 100th, 200th, ... real-money Probe+ event (ordered by session, then rank),
     the one-sided session-block sign-flip p for a mean BELOW zero over ALL its real-money events so far (block =
     entry session, value = the mean r of its real events, the last block partial) <= READ_P (0.20).
SIZED: at a stay look whose stay record passes (p <= alpha(S) on the weighted margin values, mean a > 0, mean r > 0,
the top-14 means > 0; the control and issuer guards are taken as holding: more Sized, larger lots, more money-stop
demotions, so conservative) once the stay holds >= 30 real events with P&L > 0 (fills within 15 bp assumed).
Reported: P(demoted by the 100th / 300th / 500th / 1000th real event), combined and by trigger; for a zero-edge or
cost-only program the mean Probe+ events and dollars until demotion within the horizon.

Usage: demotion_final.py --rule JSON [--workers N] --out FILE
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

import numpy as np  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import calib_final as CF  # noqa: E402  (the generator's pieces; calib_final.simulate itself is not used)
import search_final as SF  # noqa: E402

TIE = 1e-12
CAP_P, CAP_S = 14, 8
LOT_P, LOT_S = 67.9, 190.0
STOP_N, STOP_USD = 50, 150.0
READ_EVERY, READ_P = 100, 0.20
N_MAX = 1000
B_READ = 9_999
SIGNS_R = None


def _signs_r(n):
    global SIGNS_R
    if SIGNS_R is None or SIGNS_R.shape[1] < n:
        SIGNS_R = np.where(np.random.default_rng(20261024).random((B_READ, max(n, 400))) < 0.5, -1.0, 1.0)
    return SIGNS_R


def p_rows(Y):
    """One-sided sign-flip p of mean > 0, rows of Y with their own lengths given by NaN padding."""
    out = np.empty(Y.shape[0])
    for i in range(Y.shape[0]):
        y = Y[i][~np.isnan(Y[i])]
        S = y.size
        if S <= CF.EXACT_S:
            out[i] = CF.signflip_p_rows(y[None, :], S)[0]
        else:
            M = _signs_r(S)[:, :S] @ np.abs(y)
            out[i] = (1 + np.count_nonzero(M >= y.sum() - S * TIE)) / (1.0 + B_READ)
    return out


def simulate_stay(g: CF.Gen, R: int, T: int, seed: int, rule: SF.Rule, read_p: float = READ_P, stop: str = "usd150"):
    """stop: 'usd150' (PREREG-EVL-3's: the last 50 lost more than $150 net), 'pct:X' (the last 50 lost more than X of
    their summed buy cost), 'none'."""
    stop_pct = float(stop.split(':')[1]) if stop.startswith('pct:') else None
    rng = np.random.default_rng(seed)
    U = g.U
    sector = rng.choice(len(CF.SECTOR_W), size=U, p=CF.SECTOR_W)
    logw = -g.zipf_s * np.log(np.arange(1, U + 1))
    isig = np.exp(rng.uniform(math.log(g.sig_lo), math.log(g.sig_hi), (R, U)))
    beta = np.array(g.beta_mean)[None, None, :] + g.beta_sd * rng.standard_normal((R, U, 3))
    last = np.full((R, U), -10_000, np.int32)
    lvol = rng.standard_normal(R) * g.vol_sd
    D = rng.standard_normal(R) * g.drift_sd if g.drift_sd > 0 else np.zeros(R)
    z, _ = CF.day_innov(rng, g.day, R)
    sd_c = g.sd_day()
    jmean = g.jump_p * g.jump_size * (1.0 - 2.0 * g.jump_left)
    rate_c = g.nbar / g.p_read
    hot_add = math.log(g.hot_mult)
    rows = np.arange(R)
    # the stay's shadow record (for its looks)
    X = np.zeros((R, CF.S_RUN + 1)); W = np.zeros((R, CF.S_RUN + 1)); S = np.zeros(R, np.int64)
    ca = np.zeros(R); cr = np.zeros(R); ne = np.zeros(R, np.int64); ta = np.zeros(R); tr = np.zeros(R)
    seen = np.zeros((R, U), bool); niss = np.zeros(R, np.int64)
    sl = np.array([s for s in SF.LOOKS if s >= rule.start]); nxt = np.zeros(R, np.int64)
    # real money
    band = np.zeros(R, np.int8)                  # 0 probe, 1 sized, 2 demoted
    why = np.zeros(R, np.int8)                   # 1 money stop, 2 lower tail, 3 fixed read
    nreal = np.zeros(R, np.int64)
    pnl_cum = np.zeros((R, N_MAX + 200 + 1))     # cumulative P&L by real event
    cost_cum = np.zeros((R, N_MAX + 200 + 1))    # cumulative buy cost by real event
    blk_sum = np.zeros((R, N_MAX + 1)); blk_n = np.zeros((R, N_MAX + 1), np.int64); nblk = np.zeros(R, np.int64)
    dem_at = np.full(R, 10 ** 6, np.int64)       # the real-event count at demotion
    next_read = np.full(R, READ_EVERY, np.int64)
    sized_at = np.full(R, -1, np.int64)
    for t in range(1, T + 1):
        live = (band < 2) & (nreal < N_MAX)
        if not live.any():
            break
        lvol = g.vol_rho * lvol + math.sqrt(1 - g.vol_rho ** 2) * g.vol_sd * rng.standard_normal(R)
        h = np.exp(lvol - g.vol_sd ** 2)
        if g.drift_sd > 0:
            D = g.drift_rho * D + math.sqrt(1 - g.drift_rho ** 2) * g.drift_sd * rng.standard_normal(R)
        eps, _ = CF.day_innov(rng, g.day, R)
        z = g.phi_day * z + math.sqrt(1 - g.phi_day ** 2) * eps
        c_day = sd_c * z
        s_sec = g.sd_sector * CF.unit_t3(rng, (R, len(CF.SECTOR_W)))
        f_fac = g.sd_factor * CF.unit_t3(rng, (R, 3))
        b = g.b_mu + g.b_sd * rng.standard_normal(R)
        elig = (t - last) > g.cooldown
        n_el = elig.sum(axis=1)
        nC = np.minimum(rng.poisson(rate_c * rng.gamma(g.shape_n, 1.0 / g.shape_n, R)), n_el)
        nmax = int(nC.max())
        if nmax == 0:
            continue
        keys = logw[None, :] + rng.gumbel(size=(R, U))
        hot = np.where(rng.random(R) < g.hot_p, rng.integers(0, len(CF.SECTOR_W), R), -1)
        keys += np.where(sector[None, :] == hot[:, None], hot_add, 0.0)
        keys[~elig] = -np.inf
        idx = np.argpartition(-keys, nmax - 1, axis=1)[:, :nmax] if nmax < U else np.tile(np.arange(U), (R, 1))
        kv = np.take_along_axis(keys, idx, axis=1)
        idx = np.take_along_axis(idx, np.argsort(-kv, axis=1), axis=1)
        mask = np.arange(nmax)[None, :] < nC[:, None]
        er = np.broadcast_to(rows[:, None], mask.shape)[mask]
        ei = idx[mask]
        last[er, ei] = t
        E = er.size
        sel = rng.random(E) < g.p_read
        noise = isig[er, ei] * CF.unit_t3(rng, E, g.ev_left, g.ev_right)
        common = c_day[er] + s_sec[er, sector[ei]] + (beta[er, ei, :] * f_fac[er, :]).sum(axis=1)
        a = g.mu_family + D[er] + h[er] * (common + noise)
        if g.jump_p > 0:
            hit = rng.random(E) < g.jump_p
            sgn = np.where(rng.random(E) < g.jump_left, -1.0, 1.0)
            a = a + hit * sgn * g.jump_size - jmean
        a = a + g.skill * sel
        a = np.maximum(a, -1.0)
        rr_ = a + b[er]
        cs = np.cumsum(sel)
        first = np.r_[True, er[1:] != er[:-1]]
        start_idx = np.maximum.accumulate(np.where(first, np.arange(E), 0))
        pos = cs - (cs[start_idx] - sel[start_idx])
        top = sel & (pos <= CF.CAP)
        pr, pa, prr = er[sel], a[sel], rr_[sel]
        nP = np.bincount(pr, minlength=R)
        sP = np.bincount(pr, pa, R)
        sR = np.bincount(pr, prr, R)
        has = (nP > 0) & live
        # ---- the stay's shadow record and its look
        hr = np.nonzero(has)[0]
        ok = hr[S[hr] <= CF.S_RUN]
        X[ok, S[ok]] = sP[ok] / nP[ok]
        W[ok, S[ok]] = nP[ok]
        S[hr] += 1
        ca += np.where(has, sP, 0.0); cr += np.where(has, sR, 0.0); ne += np.where(has, nP, 0)
        ta += np.where(has, np.bincount(er[top], a[top], R), 0.0)
        tr += np.where(has, np.bincount(er[top], rr_[top], R), 0.0)
        pi_ = ei[sel]
        hm = has[pr]
        newi = ~seen[pr[hm], pi_[hm]]
        seen[pr[hm], pi_[hm]] = True
        niss += np.bincount(pr[hm][newi], minlength=R)
        mn = (ne >= CF.MIN_EV) & (niss >= CF.MIN_ISS) & (S >= CF.MIN_BLK)
        thr = sl[np.minimum(nxt, sl.size - 1)]
        lk = has & mn & (S <= CF.S_RUN) & (nxt < sl.size) & (S >= thr)
        look_rows = np.nonzero(lk)[0]
        if look_rows.size:
            nxt[look_rows] = (S[look_rows][:, None] >= sl[None, :]).sum(axis=1)
        # ---- real money this session (bought in the band held at the session's decision)
        cap_r = np.where(band == 1, CAP_S, CAP_P)
        lot_r = np.where(band == 1, LOT_S, LOT_P)
        real = sel & (pos <= cap_r[er]) & live[er]
        rr_real = rr_[real]
        er_real = er[real]
        m = np.bincount(er_real, minlength=R)
        # per row: the real events in rank order (er sorted by row, rank order kept)
        order_start = np.r_[0, np.cumsum(m)[:-1]]
        demote_now = np.zeros(R, bool)
        rws = np.nonzero(m > 0)[0]
        for r in rws:
            k0 = int(nreal[r])
            vals = rr_real[order_start[r]:order_start[r] + m[r]]
            k1 = min(k0 + vals.size, N_MAX + 200)
            vals = vals[:k1 - k0]
            pnl_cum[r, k0 + 1:k1 + 1] = pnl_cum[r, k0] + np.cumsum(lot_r[r] * vals)
            cost_cum[r, k0 + 1:k1 + 1] = cost_cum[r, k0] + lot_r[r] * np.arange(1, k1 - k0 + 1)
            # the fixed reads crossing inside this session
            while next_read[r] <= k1 and band[r] < 2:
                j = int(next_read[r] - k0)           # this session's first j events are in the read
                nb = int(nblk[r])
                V = list(blk_sum[r, :nb] / np.maximum(blk_n[r, :nb], 1)) + [float(vals[:j].mean())]
                y = -np.array(V)
                if p_rows(y[None, :])[0] <= read_p:
                    band[r] = 2; why[r] = 3; dem_at[r] = int(next_read[r])
                next_read[r] += READ_EVERY
            if band[r] < 2:
                blk_sum[r, nblk[r]] = vals.sum(); blk_n[r, nblk[r]] = vals.size; nblk[r] += 1
                nreal[r] = k1
        # the money stop after the session's settlements
        alive = (band < 2) & (m > 0)
        n_now = nreal
        lo = np.maximum(n_now - STOP_N, 0)
        net = pnl_cum[rows, n_now] - pnl_cum[rows, lo]
        if stop == 'none':
            hit_stop = np.zeros(R, bool)
        elif stop_pct is not None:
            hit_stop = alive & (net < -stop_pct * (cost_cum[rows, n_now] - cost_cum[rows, lo]))
        else:
            hit_stop = alive & (net < -STOP_USD)
        band[hit_stop] = 2; why[hit_stop] = 1; dem_at[hit_stop] = n_now[hit_stop]
        # the stay's look: lower tail first, then Sized
        if look_rows.size:
            lr = look_rows[band[look_rows] < 2]
            if lr.size:
                al = rule.alpha(S[lr])
                negr = lr[ca[lr] < 0]
                if negr.size:
                    for Sv in np.unique(S[negr]):
                        rs = negr[S[negr] == Sv]
                        Y = -np.minimum(W[rs, :Sv], CF.CAP) * X[rs, :Sv]
                        q = CF.signflip_p_rows(Y, int(Sv))
                        aa = rule.alpha(np.full(rs.size, Sv))
                        hitq = q <= aa + TIE
                        band[rs[hitq]] = 2; why[rs[hitq]] = 2; dem_at[rs[hitq]] = nreal[rs[hitq]]
                pos_r = lr[(band[lr] == 0) & (ca[lr] > 0) & (cr[lr] > 0) & (ta[lr] > 0) & (tr[lr] > 0)]
                if pos_r.size:
                    for Sv in np.unique(S[pos_r]):
                        rs = pos_r[S[pos_r] == Sv]
                        Y = np.minimum(W[rs, :Sv], CF.CAP) * (X[rs, :Sv] - CF.MARGIN)
                        p = CF.signflip_p_rows(Y, int(Sv))
                        aa = rule.alpha(np.full(rs.size, Sv))
                        k = nreal[rs]
                        pnl_ok = pnl_cum[rs, k] > 0
                        go = (p <= aa) & (k >= 30) & pnl_ok
                        band[rs[go]] = 1; sized_at[rs[go]] = k[go]
    return {"dem_at": dem_at, "why": why, "nreal": nreal, "sized_at": sized_at,
            "pnl_end": pnl_cum[rows, np.minimum(np.where(dem_at < 10 ** 6, dem_at, nreal), N_MAX + 200)]}


CELLS = []


def cells():
    N3s = CF.SHAPES
    out = []
    worst = dict(rho_day=0.15, phi_day=0.20, drift_sd=0.0020, **N3s["both"])
    for nb, T in ((85, 140), (30, 140), (13, 150), (8, 160), (3, 160)):
        out.append(("60bp|worst: both, AR20, rho.15, phi.20", dict(nbar=nb, skill=0.006, **worst), 4000, T))
    for nb, T in ((85, 140), (13, 150), (8, 160)):
        out.append(("60bp|dayskew, AR20, rho.15, phi.20", dict(nbar=nb, skill=0.006, rho_day=0.15, phi_day=0.20,
                                                               drift_sd=0.0020, **N3s["dayskew"]), 2000, T))
        out.append(("60bp|sym, rho.15, phi.20", dict(nbar=nb, skill=0.006, rho_day=0.15, phi_day=0.20), 2000, T))
        out.append(("60bp|base: sym, rho.05", dict(nbar=nb, skill=0.006, rho_day=0.05), 2000, T))
        out.append(("60bp|sym, rho 0", dict(nbar=nb, skill=0.006, rho_day=0.0), 2000, T))
        out.append(("60bp|STRESS both, AR20, rho.30", dict(nbar=nb, skill=0.006, rho_day=0.30, drift_sd=0.0020,
                                                           **N3s["both"]), 2000, T))
        out.append(("60bp|STRESS both, AR20, rho.15, phi.25", dict(nbar=nb, skill=0.006, rho_day=0.15, phi_day=0.25,
                                                                   drift_sd=0.0020, **N3s["both"]), 2000, T))
        out.append(("100bp|worst", dict(nbar=nb, skill=0.010, **worst), 2000, T))
        out.append(("0bp (knife edge)|worst", dict(nbar=nb, skill=0.006, mu_family=-0.006, **worst), 2000, T))
        out.append(("0bp (knife edge)|base", dict(nbar=nb, skill=0.006, mu_family=-0.006, rho_day=0.05), 2000, T))
        out.append(("-15bp (cost only)|base", dict(nbar=nb, skill=0.006, mu_family=-0.0075, rho_day=0.05), 2000, T))
    return out


def _job(args):
    lab, kw, R, T, seed, rule_key, read_p, stop = args
    t0 = time.time()
    res = simulate_stay(CF.Gen(**kw), R, T, seed, SF.Rule.of(rule_key), read_p, stop)
    return lab, kw, R, T, seed, {k: v.tolist() for k, v in res.items()}, time.time() - t0, (read_p, stop)


def summarize(rows):
    groups: dict = {}
    for lab, kw, R, T, seed, res, secs, read_p in rows:
        key = (lab, kw["nbar"], read_p)   # read_p = (read p, stop)
        groups.setdefault(key, []).append(res)
    out = []
    for (lab, nb, read_p), rs in sorted(groups.items(), key=lambda x: (x[0][0], -x[0][1], x[0][2])):
        dem = np.concatenate([np.array(r["dem_at"]) for r in rs])
        why = np.concatenate([np.array(r["why"]) for r in rs])
        nreal = np.concatenate([np.array(r["nreal"]) for r in rs])
        sized = np.concatenate([np.array(r["sized_at"]) for r in rs])
        pnl = np.concatenate([np.array(r["pnl_end"]) for r in rs])
        row = {"cell": lab, "nbar": nb, "read_p": read_p[0], "stop": read_p[1], "R": int(dem.size)}
        for k in (100, 300, 500, 1000):
            reach = float(np.mean((nreal >= k) | (dem <= k)))
            row[f"by{k}"] = float(np.mean(dem <= k)) if reach > 0.99 else None
            row[f"by{k}_reached"] = reach
            for code, nm in ((1, "stop"), (2, "tail"), (3, "read")):
                row[f"by{k}_{nm}"] = float(np.mean((dem <= k) & (why == code)))
        row["by_end"] = float(np.mean(dem < 10 ** 6))
        row["mean_real_events"] = float(np.mean(np.where(dem < 10 ** 6, dem, nreal)))
        row["sized"] = float(np.mean(sized >= 0))
        row["mean_pnl_usd"] = float(np.mean(pnl))
        out.append(row)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--rule", required=True)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--out", required=True)
    ap.add_argument("--read-p", default="0.20")
    ap.add_argument("--only", default="")
    ap.add_argument("--R", type=int, default=0)
    ap.add_argument("--stop", default="usd150")
    ap.add_argument("--rates", default="")
    ap.add_argument("--seed0", type=int, default=118_000_000)
    a = ap.parse_args()
    from multiprocessing import get_context
    jobs = []
    seed = 118_000_000
    for read_p in (float(x) for x in a.read_p.split(",")):
      for stop in a.stop.split(","):
        seed = a.seed0 + 1_000 * int(round(read_p * 100)) + 100_000 * (1 + a.stop.split(",").index(stop))
        for lab, kw, R, T in cells():
            if a.only and not any(o in lab for o in a.only.split("+")):
                continue
            if a.rates and kw["nbar"] not in [float(x) for x in a.rates.split(",")]:
                continue
            R = a.R or R
            for c in range(0, R, 500):
                seed += 1
                jobs.append((lab, kw, min(500, R - c), T, seed, a.rule, read_p, stop))
    jobs.sort(key=lambda j: -j[1]["nbar"] * j[3])
    t0 = time.time()
    done = []
    with get_context("fork").Pool(min(a.workers, 8)) as pool:
        for k, row in enumerate(pool.imap_unordered(_job, jobs), 1):
            done.append(row)
            if k % 10 == 0 or k == len(jobs):
                print(f"{k}/{len(jobs)} {time.time() - t0:.0f}s", flush=True)
    summ = summarize(done)
    json.dump({"rule": a.rule, "rows": summ}, open(a.out, "w"), indent=1)
    for r in summ:
        print(json.dumps(r))
