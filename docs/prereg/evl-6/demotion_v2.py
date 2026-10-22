#!/usr/bin/env python
"""demotion_v2.py: PREREG-EVL-6 section 3's demotion as the captain's D10 and D15 set it (SYNTHETIC ONLY).

demotion_final.py's Probe-stay simulation (its lots, its ranking, its Sized move) on calib_v2.py's generator (the
widened grid's day shapes and the day-following counts), with:
  1. THE MONEY STOP over THE WHOLE STAY (D10): after each session's settlements, the stay's real-money Probe+ events
     so far (all of them, from the stay's first) have lost, net, more than 10% of their summed buy cost
     (stop 'whole:0.10'; 'last50:X' is the earlier variant over the last 50, 'none' no money stop);
  2. THE STAY'S LOWER TAIL at a stay look (the chosen schedule's alpha(S), the stay's own shadow record): mean a < 0 and
     q <= alpha(S) + 1e-12;
  3. THE FIXED READS (D3, D15): at the stay's 100th, 200th, ... real-money Probe+ event (ordered by session, then rank),
     the one-sided session-block sign-flip p for a mean BELOW zero over ALL its real-money events so far <= READ_P
     (0.15 by D15; 0.20 was the earlier text).
THE ORDER at a close: the fixed reads crossed by that session's settled events (in their order), then the money stop,
then the stay's look (its lower tail, then Sized). SIZED as demotion_final.py: a stay PASS with >= 30 real events whose
SUMMED P&L is > 0.
A TRUE EDGE with counts that follow the day (mw_knife): the program's money-weighted mean a is exactly the edge (the
knife of calib_v2 with no skill, plus the edge on the program's events).
Reported: P(demoted by the 100th / 300th / 500th / 1,000th / 2,000th / 3,000th real event), combined and by trigger,
the share of stays that reach each horizon, and for a zero-edge (a false pass's stay) or cost-only program the events
and dollars until demotion.

Usage: demotion_v2.py --rule JSON --out FILE [--read-p 0.15] [--stop whole:0.10] [--only SUBSTR] [--seed0 N]
"""
from __future__ import annotations

import os

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import argparse  # noqa: E402
import dataclasses  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402

import numpy as np  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import calib_final as CF  # noqa: E402
import calib_v2 as V  # noqa: E402
import demotion_final as DF  # noqa: E402
import search_final as SF  # noqa: E402

TIE = 1e-12
CAP_P, CAP_S = 14, 8
LOT_P, LOT_S = 67.9, 190.0
READ_EVERY = 100
N_MAX = 3000
HORIZONS = (100, 300, 500, 1000, 2000, 3000)


def simulate_stay(g: V.Gen2, R: int, T: int, seed: int, rule: SF.Rule, read_p: float, stop: str):
    kind, _, xv = stop.partition(":")
    xv = float(xv) if xv else 0.0
    rng = np.random.default_rng(seed)
    U = g.U
    sector = rng.choice(len(CF.SECTOR_W), size=U, p=CF.SECTOR_W)
    logw = -g.zipf_s * np.log(np.arange(1, U + 1))
    isig = np.exp(rng.uniform(math.log(g.sig_lo), math.log(g.sig_hi), (R, U)))
    beta = np.array(g.beta_mean)[None, None, :] + g.beta_sd * rng.standard_normal((R, U, 3))
    last = np.full((R, U), -10_000, np.int32)
    lvol = rng.standard_normal(R) * g.vol_sd
    D = rng.standard_normal(R) * g.drift_sd if g.drift_sd > 0 else np.zeros(R)
    z, _ = V.day_innov2(rng, g, R, lvol)
    sd_c = g.sd_day()
    jmean = g.jump_p * g.jump_size * (1.0 - 2.0 * g.jump_left)
    rate_c = g.nbar / g.p_read
    hot_add = math.log(g.hot_mult)
    rows = np.arange(R)
    if g.mw_knife:
        mu_family = V.knife_mu2(dataclasses.replace(g, skill=0.0)) + g.mu_family
    else:
        mu_family = g.mu_family
    Emult = V.count_norm(g)
    X = np.zeros((R, CF.S_RUN + 1)); W = np.zeros((R, CF.S_RUN + 1)); S = np.zeros(R, np.int64)
    ca = np.zeros(R); cr = np.zeros(R); ne = np.zeros(R, np.int64); ta = np.zeros(R); tr = np.zeros(R)
    seen = np.zeros((R, U), bool); niss = np.zeros(R, np.int64)
    sl = np.array([s for s in SF.LOOKS if s >= rule.start]); nxt = np.zeros(R, np.int64)
    band = np.zeros(R, np.int8)
    why = np.zeros(R, np.int8)
    nreal = np.zeros(R, np.int64)
    pnl_cum = np.zeros((R, N_MAX + 200 + 1))
    cost_cum = np.zeros((R, N_MAX + 200 + 1))
    blk_sum = np.zeros((R, N_MAX + 1)); blk_n = np.zeros((R, N_MAX + 1), np.int64); nblk = np.zeros(R, np.int64)
    dem_at = np.full(R, 10 ** 6, np.int64)
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
        eps, _ = V.day_innov2(rng, g, R, lvol)
        z = g.phi_day * z + math.sqrt(1 - g.phi_day ** 2) * eps
        c_day = sd_c * z
        s_sec = g.sd_sector * CF.unit_t3(rng, (R, len(CF.SECTOR_W)))
        f_fac = g.sd_factor * CF.unit_t3(rng, (R, 3))
        b = g.b_mu + g.b_sd * rng.standard_normal(R)
        elig = (t - last) > g.cooldown
        n_el = elig.sum(axis=1)
        mult = np.exp(g.cnt_kappa * np.minimum(np.abs(eps), 4.0)) / Emult if g.cnt_kappa > 0 else 1.0
        nC = np.minimum(rng.poisson(rate_c * mult * rng.gamma(g.shape_n, 1.0 / g.shape_n, R)), n_el)
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
        a = mu_family + D[er] + h[er] * (common + noise)
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
        cap_r = np.where(band == 1, CAP_S, CAP_P)
        lot_r = np.where(band == 1, LOT_S, LOT_P)
        real = sel & (pos <= cap_r[er]) & live[er]
        rr_real = rr_[real]
        er_real = er[real]
        m = np.bincount(er_real, minlength=R)
        order_start = np.r_[0, np.cumsum(m)[:-1]]
        for r in np.nonzero(m > 0)[0]:
            k0 = int(nreal[r])
            vals = rr_real[order_start[r]:order_start[r] + m[r]]
            k1 = min(k0 + vals.size, N_MAX + 200)
            vals = vals[:k1 - k0]
            pnl_cum[r, k0 + 1:k1 + 1] = pnl_cum[r, k0] + np.cumsum(lot_r[r] * vals)
            cost_cum[r, k0 + 1:k1 + 1] = cost_cum[r, k0] + lot_r[r] * np.arange(1, k1 - k0 + 1)
            while next_read[r] <= k1 and band[r] < 2:
                j = int(next_read[r] - k0)
                nb = int(nblk[r])
                Vb = list(blk_sum[r, :nb] / np.maximum(blk_n[r, :nb], 1)) + [float(vals[:j].mean())]
                if DF.p_rows(-np.array(Vb)[None, :])[0] <= read_p:
                    band[r] = 2; why[r] = 3; dem_at[r] = int(next_read[r])
                next_read[r] += READ_EVERY
            if band[r] < 2:
                if nblk[r] <= N_MAX:
                    blk_sum[r, nblk[r]] = vals.sum(); blk_n[r, nblk[r]] = vals.size; nblk[r] += 1
                nreal[r] = k1
        alive = (band < 2) & (m > 0)
        n_now = nreal
        if kind == "whole":
            hit_stop = alive & (pnl_cum[rows, n_now] < -xv * cost_cum[rows, n_now])
        elif kind == "last50":
            lo = np.maximum(n_now - 50, 0)
            net = pnl_cum[rows, n_now] - pnl_cum[rows, lo]
            hit_stop = alive & (net < -xv * (cost_cum[rows, n_now] - cost_cum[rows, lo]))
        else:
            hit_stop = np.zeros(R, bool)
        band[hit_stop] = 2; why[hit_stop] = 1; dem_at[hit_stop] = n_now[hit_stop]
        if look_rows.size:
            lr = look_rows[band[look_rows] < 2]
            if lr.size:
                negr = lr[ca[lr] < 0]
                for Sv in np.unique(S[negr]):
                    rs = negr[S[negr] == Sv]
                    Y = -np.minimum(W[rs, :Sv], CF.CAP) * X[rs, :Sv]
                    q = CF.signflip_p_rows(Y, int(Sv))
                    hitq = q <= rule.alpha(np.full(rs.size, Sv)) + TIE
                    band[rs[hitq]] = 2; why[rs[hitq]] = 2; dem_at[rs[hitq]] = nreal[rs[hitq]]
                pos_r = lr[(band[lr] == 0) & (ca[lr] > 0) & (cr[lr] > 0) & (ta[lr] > 0) & (tr[lr] > 0)]
                for Sv in np.unique(S[pos_r]):
                    rs = pos_r[S[pos_r] == Sv]
                    Y = np.minimum(W[rs, :Sv], CF.CAP) * (X[rs, :Sv] - CF.MARGIN)
                    p = CF.signflip_p_rows(Y, int(Sv))
                    k = nreal[rs]
                    go = (p <= rule.alpha(np.full(rs.size, Sv))) & (k >= 30) & (pnl_cum[rs, k] > 0)
                    band[rs[go]] = 1; sized_at[rs[go]] = k[go]
    end_k = np.minimum(np.where(dem_at < 10 ** 6, dem_at, nreal), N_MAX + 200)
    return {"dem_at": dem_at, "why": why, "nreal": nreal, "sized_at": sized_at, "pnl_end": pnl_cum[rows, end_k],
            "t_end": np.full(R, T)}


def cells():
    """(label, gen, stays, sessions). The 60 bp cells at rho_day 0.15, phi_day 0.20 and a 20 bp drift are the worst
    plausible ones of the widened grid for demotion: every day shape (crash days with a normal body, a t(3) body,
    clustered, both) with symmetric and with left-skewed events."""
    out = []
    cor = dict(rho_day=0.15, phi_day=0.20, drift_sd=0.0020)
    shapes = {}
    for dt in ("crash", "T", "C", "TC"):
        for ev in ("sym", "skew"):
            nm, kw = V.shape_kw(dt, ev)
            shapes[nm] = kw
    for nm in ("dayskewTC", "bothTC", "dayskewC", "dayskewT", "dayskew", "both", "bothC", "bothT"):
        out.append((f"60bp|{nm}, AR20, rho.15, phi.20", dict(nbar=85, skill=0.006, **cor, **shapes[nm]), 4000, 420))
    for nm in ("dayskewTC", "bothTC", "dayskewC", "dayskew"):
        out.append((f"60bp|{nm}, AR20, rho.15, phi.20", dict(nbar=30, skill=0.006, **cor, **shapes[nm]), 3000, 420))
        out.append((f"60bp|{nm}, AR20, rho.15, phi.20", dict(nbar=13, skill=0.006, **cor, **shapes[nm]), 2000, 420))
    for nm in ("dayskewTC", "bothTC"):
        for nb in (8, 3):
            out.append((f"60bp|{nm}, AR20, rho.15, phi.20", dict(nbar=nb, skill=0.006, **cor, **shapes[nm]), 2000, 420))
            out.append((f"60bp|{nm}, AR20, rho.15, phi.20, counts follow the day",
                        dict(nbar=nb, skill=0.006, **cor, **shapes[nm], cnt_kappa=0.3, mw_knife=14), 2000, 420))
    for nb in (85, 13):
        out.append(("60bp|base: sym, rho.05", dict(nbar=nb, skill=0.006, rho_day=0.05), 2000, 300))
        out.append(("60bp|sym, rho 0", dict(nbar=nb, skill=0.006, rho_day=0.0), 2000, 300))
        out.append(("100bp|dayskewTC, AR20, rho.15, phi.20", dict(nbar=nb, skill=0.010, **cor, **shapes["dayskewTC"]),
                    2000, 300))
        out.append(("60bp|STRESS dayskewTC, AR20, rho.15, phi.25", dict(nbar=nb, skill=0.006, rho_day=0.15, phi_day=0.25,
                                                                        drift_sd=0.0020, **shapes["dayskewTC"]), 2000, 300))
        out.append(("60bp|STRESS both, AR20, rho.30", dict(nbar=nb, skill=0.006, rho_day=0.30, drift_sd=0.0020,
                                                           **shapes["both"]), 2000, 300))
    for nm in ("dayskewTC", "both"):
        out.append((f"0bp (knife edge)|{nm}, AR20, rho.15, phi.20", dict(nbar=85, skill=0.006, mu_family=-0.006, **cor,
                                                                         **shapes[nm]), 2000, 300))
    out.append(("0bp (knife edge)|base", dict(nbar=85, skill=0.006, mu_family=-0.006, rho_day=0.05), 2000, 300))
    for nb in (85, 13):
        out.append(("-15bp (cost only)|base", dict(nbar=nb, skill=0.006, mu_family=-0.0075, rho_day=0.05), 2000, 300))
    return out


def _job(args):
    lab, kw, R, T, seed, rule_key, read_p, stop = args
    t0 = time.time()
    res = simulate_stay(V.Gen2(**kw), R, T, seed, SF.Rule.of(rule_key), read_p, stop)
    return lab, kw, R, T, seed, {k: v.tolist() for k, v in res.items()}, time.time() - t0, (read_p, stop)


def summarize(rows):
    groups: dict = {}
    for lab, kw, R, T, seed, res, secs, rp in rows:
        groups.setdefault((lab, kw["nbar"], rp), []).append(res)
    out = []
    for (lab, nb, rp), rs in sorted(groups.items(), key=lambda x: (x[0][0], -x[0][1], x[0][2])):
        cat = {k: np.concatenate([np.array(r[k]) for r in rs]) for k in rs[0]}
        dem, why, nreal, sized, pnl = cat["dem_at"], cat["why"], cat["nreal"], cat["sized_at"], cat["pnl_end"]
        row = {"cell": lab, "nbar": nb, "read_p": rp[0], "stop": rp[1], "R": int(dem.size)}
        for k in HORIZONS:
            reach = float(np.mean((nreal >= k) | (dem <= k)))
            row[f"by{k}_reached"] = round(reach, 4)
            row[f"by{k}"] = round(float(np.mean(dem <= k)), 4) if reach > 0.99 else None
            row[f"by{k}_lower_bound"] = round(float(np.mean(dem <= k)), 4)
            for code, nm in ((1, "stop"), (2, "tail"), (3, "read")):
                row[f"by{k}_{nm}"] = round(float(np.mean((dem <= k) & (why == code))), 4)
        row["se1000"] = round(math.sqrt(max(row["by1000_lower_bound"] * (1 - row["by1000_lower_bound"]), 1e-12) / dem.size), 4)
        row["by_end"] = round(float(np.mean(dem < 10 ** 6)), 4)
        row["mean_real_events_before_demotion_or_end"] = round(float(np.mean(np.where(dem < 10 ** 6, dem, nreal))), 1)
        row["mean_real_events_of_first_1000"] = round(float(np.mean(np.minimum(np.where(dem < 10 ** 6, dem, nreal), 1000))), 1)
        row["sized"] = round(float(np.mean(sized >= 0)), 4)
        row["mean_pnl_usd"] = round(float(np.mean(pnl)), 1)
        out.append(row)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--rule", required=True)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--out", required=True)
    ap.add_argument("--read-p", default="0.15")
    ap.add_argument("--stop", default="whole:0.10")
    ap.add_argument("--only", default="")
    ap.add_argument("--R", type=int, default=0)
    ap.add_argument("--rates", default="")
    ap.add_argument("--seed0", type=int, default=124_000_000)
    a = ap.parse_args()
    from multiprocessing import get_context
    jobs = []
    stops = a.stop.split(",")
    reads = [float(x) for x in a.read_p.split(",")]
    for ir, read_p in enumerate(reads):
        for js, stop in enumerate(stops):
            seed = a.seed0 + 1_000_000 * ir + 100_000 * js
            for lab, kw, R, T in cells():
                if a.only and not any(o in lab for o in a.only.split("+")):
                    continue
                if a.rates and kw["nbar"] not in [float(x) for x in a.rates.split(",")]:
                    continue
                R = a.R or R
                for c in range(0, R, 250):
                    seed += 1
                    jobs.append((lab, kw, min(250, R - c), T, seed, a.rule, read_p, stop))
    jobs.sort(key=lambda j: -j[1]["nbar"] * j[3])
    t0 = time.time()
    done = []
    with get_context("fork").Pool(min(a.workers, 8)) as pool:
        for k, row in enumerate(pool.imap_unordered(_job, jobs), 1):
            done.append(row)
            if k % 20 == 0 or k == len(jobs):
                print(f"{k}/{len(jobs)} {time.time() - t0:.0f}s", flush=True)
    summ = summarize(done)
    json.dump({"rule": a.rule, "seed0": a.seed0, "rows": summ}, open(a.out, "w"), indent=1)
    for r in summ:
        print(json.dumps(r))
