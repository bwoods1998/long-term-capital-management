#!/usr/bin/env python
"""check1_adv.py (EVL-9 adversarial check #1, statistics): "a learner trained on ANY history". The calibration's warm
cells give the prior a slope from a sampling law around a modest history index (ic_h 0 / 0.05 / 0.08). A history with
look-ahead (a restated field, a label leaking into a column) or an overfit tree yields a CONFIDENT prior in an arbitrary
direction; an adversary choosing the history can point it anywhere in the 59/63-column span. This script gives the warm
learner adversarial priors and screens its forward record by PREREG-EVL-6's FINAL rule:

  leak    a look-ahead prior: all weight on ONE event column (col 39, the dmove-like column), standardised slope k
  rand    an overfit-noise prior: a random direction in standardised column space, standardised length k
  lowvol  the screen-seeking prior: all weight AGAINST ln(sig20) (col 30), i.e. history taught "low-volatility names
          win": the direction a history can take toward the screen's skew corner (in the generator every event carries
          the same +-30% jumps whatever its sigma, so low-sigma events are the most jump-dominated, left-skewed ones)

Guards (the draft's SHAPE GUARD, section 2.3 (iii)):
  none    no guard (what every calibration cell so far measured)
  g15     the guard as calibrated: the event's hold-period sigma >= 1.5% (sig_hat >= 0.015)
  g15on   the guard as REGISTERED for EVL-WL-ON: sig20 (close-to-close) >= 1.5% while the hold is overnight; with an
          overnight share f of daily variance the hold sigma is sqrt(f) x sig20, so the guard admits hold sigma >=
          1.5% x sqrt(f); here f = 0.30 (admits sig_hat >= 0.0082)

SYNTHETIC ONLY: the generator is evl9/learners/calib_evl9.py's (copied below; r columns as noise, as there).
Usage: check1_adv.py run [--reps 1000] [--workers 4] | report
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
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "judge"))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "learners"))
import calib_evl9_final as cf  # noqa: E402
import calib_evl9 as cw  # noqa: E402

cl = cw.cl
D, U = cl.D, cl.U


@dataclasses.dataclass(frozen=True)
class ACell:
    base: cw.WCell
    adv: str = ""          # '' | leak | rand | lowvol
    k: float = 0.30        # standardised prior slope length
    guard: float = 0.0     # minimum sig_hat x gscale admitted to be picked (0: none)
    gscale: float = 1.0    # the guard reads sig_hat / gscale (gscale = sqrt(f) for an overnight hold read on sig20)


def adv_beta(ac: ACell, rng, R):
    P = cw.population()
    sd = np.sqrt(np.diag(P["S"]))
    b = np.zeros((R, D))
    if ac.adv == "leak":
        b[:, 39] = ac.k / sd[39]
    elif ac.adv == "lowvol":
        b[:, 30] = -ac.k / sd[30]
    elif ac.adv == "rand":
        z = rng.normal(0, 1, (R, D))
        z /= np.linalg.norm(z, axis=1, keepdims=True)
        b = ac.k * z / sd[None, :]
    return b


def simulate(ac: ACell, seed: int, R: int) -> dict:
    c = ac.base
    P = cw.population()
    rng = np.random.default_rng(seed)
    T, K = c.T, c.K
    iss = cl.issuers(rng, R, cw._cl_cell(c))
    Nmax = int(c.nbar * 3.2) + 20
    sd_c = c.sd_day()
    zday = np.zeros(R)
    vx = rng.normal(0, 0.3, R)
    drift = rng.normal(0, c.drift_sd, R) if c.drift_sd else np.zeros(R)
    warm = c.hist == "warm" and c.n_eq > 0
    if warm:
        bhat = adv_beta(ac, rng, R) if ac.adv else cw.history_beta(c, rng, R)[0]
        A0 = np.broadcast_to(c.n_eq * P["S"], (R, D, D)).copy()
        b0 = np.einsum("rde,re->rd", A0, bhat)
        N0 = np.full(R, c.n_eq)
    else:
        A0 = np.zeros((R, D, D))
        b0 = np.zeros((R, D))
        N0 = np.zeros(R)
    A = np.zeros((R, D, D))
    bv = np.zeros((R, D))
    Nw = np.zeros(R)
    rows = np.zeros(R)
    nsess = np.zeros(R)
    pend: list = []
    delta = 2.0 ** (-1.0 / c.H)
    last = np.full((R, U), -10_000, dtype=np.int64)
    out_B = np.full((R, T), np.nan)
    out_Rm = np.full((R, T), np.nan)
    out_n = np.zeros((R, T), dtype=np.int16)
    out_ctrl = np.full((R, T), np.nan)
    out_iss = np.full((R, T, K), -1, dtype=np.int32)
    out_a = np.full((R, T, K), np.nan)
    out_sig = np.full((R, T), np.nan)
    for t in range(-c.pre, T):
        n_t = np.minimum(rng.poisson(c.nbar * rng.gamma(3.0, 1.0 / 3.0, R)), Nmax)
        g = -np.log(-np.log(rng.random((R, U))))
        keys = iss["logp"] + g
        ids = np.argpartition(-keys, Nmax - 1, axis=1)[:, :Nmax]
        order = np.argsort(-np.take_along_axis(keys, ids, axis=1), axis=1)
        ids = np.take_along_axis(ids, order, axis=1)
        valid = np.arange(Nmax)[None, :] < n_t[:, None]
        X, fam = cl.pool_features(rng, R, Nmax, iss, ids)
        Ey = np.zeros((R, Nmax))
        sig = np.take_along_axis(iss["sig"], ids, axis=1)
        sig_hat = np.take_along_axis(iss["sig_hat"], ids, axis=1)
        cost = np.take_along_axis(iss["cost"], ids, axis=1)
        sec = np.take_along_axis(iss["sector"], ids, axis=1)
        beta = np.take_along_axis(iss["beta"], ids[..., None], axis=1)
        tau = np.take_along_axis(iss["tau"], ids, axis=1)
        zday = c.phi_day * zday + math.sqrt(1 - c.phi_day ** 2) * cl.day_innov(rng, c.day, R)
        c_t = sd_c * zday
        vx = 0.9 * vx + math.sqrt(1 - 0.81) * rng.normal(0, 0.3, R)
        h_t = np.exp(vx - 0.09)
        s_sec = cl.unit_t3(rng, (R, 11)) * 0.010
        fac = cl.unit_t3(rng, (R, 3)) * 0.006
        if c.drift_sd:
            drift = c.drift_rho * drift + math.sqrt(1 - c.drift_rho ** 2) * rng.normal(0, c.drift_sd, R)
        b_t = rng.normal(0.0004, 0.010, R)
        e = cl.unit_t3(rng, (R, Nmax), 1.4, 0.6) if c.ev_skew else cl.unit_t3(rng, (R, Nmax))
        jl = 0.8 if c.ev_skew else c.jump_left
        jump = np.where(rng.random((R, Nmax)) < 0.005, np.where(rng.random((R, Nmax)) < jl, -0.30, 0.30), 0.0)
        jump = jump - 0.005 * 0.30 * (1 - 2 * jl)
        noise = h_t[:, None] * (c_t[:, None] + np.take_along_axis(s_sec, sec, axis=1)
                                + np.einsum("rnk,rk->rn", beta, fac) + sig * e)
        vf = valid.astype(float)
        nv = np.maximum(vf.sum(axis=1), 1)
        a = np.maximum(sig * Ey + drift[:, None] + noise + jump + tau, -1.0)
        r = a + b_t[:, None]
        y = np.clip(a / sig_hat, -5, 5)
        while pend and pend[0][0] <= t - c.lag:
            _, As, bs, ns = pend.pop(0)
            A = delta * A + As
            bv = delta * bv + bs
            Nw = delta * Nw + ns
            rows += ns
            nsess += (ns > 0)
        if t >= 0:
            elig = valid & (np.take_along_axis(last, ids, axis=1) < t - 5)
            if ac.guard > 0:
                elig = elig & (sig_hat / ac.gscale >= ac.guard)
            xbar = (X * vf[..., None]).sum(axis=1) / nv[:, None]
            Xc = X - xbar[:, None, :]
            ready = np.ones(R, dtype=bool) if warm else (rows >= 2000) & (nsess >= 3)
            At = A0 + A
            bt = b0 + bv
            Nt = np.maximum(N0 + Nw, 1.0)
            dsd = np.sqrt(np.maximum(np.einsum("rii->ri", At) / Nt[:, None], 1e-12))
            As_ = At / (dsd[:, :, None] * dsd[:, None, :]) + c.lam * np.eye(D)[None]
            beta_s = np.linalg.solve(As_, (bt / dsd)[..., None])[..., 0]
            ehat = np.einsum("rnd,rd->rn", Xc, beta_s / dsd)
            zhat = ehat - cost / sig_hat
            score = np.where(elig & ready[:, None] & (zhat > 0), zhat * sig_hat, -np.inf)
            top = np.argsort(-score, axis=1)[:, :K]
            ok = np.take_along_axis(score, top, axis=1) > -np.inf
            pa = np.where(ok, np.take_along_axis(a, top, axis=1), np.nan)
            pr = np.where(ok, np.take_along_axis(r, top, axis=1), np.nan)
            ps = np.where(ok, np.take_along_axis(sig, top, axis=1), np.nan)
            pid = np.where(ok, np.take_along_axis(ids, top, axis=1), -1)
            npk = ok.sum(axis=1)
            has = npk > 0
            with np.errstate(invalid="ignore"):
                out_B[has, t] = np.nanmean(pa[has], axis=1)
                out_Rm[has, t] = np.nanmean(pr[has], axis=1)
                out_sig[has, t] = np.nanmedian(ps[has], axis=1)
            out_n[:, t] = npk
            out_ctrl[:, t] = (a * vf).sum(axis=1) / nv
            out_iss[:, t, :] = pid
            out_a[:, t, :] = pa
            rr, kk = np.nonzero(ok)
            last[rr, pid[rr, kk]] = t
        ybar = (y * vf).sum(axis=1) / nv
        Xd = (X - ((X * vf[..., None]).sum(axis=1) / nv[:, None])[:, None, :]) * vf[..., None]
        yd = (y - ybar[:, None]) * vf
        pend.append((t, np.matmul(Xd.transpose(0, 2, 1), Xd), np.einsum("rnd,rn->rd", Xd, yd), vf.sum(axis=1)))
    return dict(B=out_B, Rm=out_Rm, n=out_n, ctrl=out_ctrl, iss=out_iss, a=out_a, sig=out_sig)


W, WN = cw.WORST, cw.WORST_NT
F_ON = 0.30


def cells():
    C = lambda name, adv="", k=0.30, guard=0.0, gscale=1.0, **kw: ACell(cw.WCell(name, **({"nbar": 300.0} | kw)), adv, k, guard, gscale)  # noqa: E731
    gs = math.sqrt(F_ON)
    return [
        C("ADV-leak-k30-worst", "leak", **W),
        C("ADV-rand-k60-worst-notau", "rand", k=0.60, **WN),
        C("ADV-lowvol-k30-worst", "lowvol", **W),
        C("ADV-lowvol-k30-worst-notau", "lowvol", **WN),
        C("ADV-lowvol-k30-worst-notau-g15", "lowvol", guard=0.015, **WN),
        C("ADV-lowvol-k30-worst-notau-g15on", "lowvol", guard=0.015, gscale=gs, **WN),
        C("ADV-lowvol-k30-worst-notau-phi20", "lowvol", **(WN | dict(phi_day=0.20))),
    ]


def _job(args):
    ac, seed, R = args
    t0 = time.time()
    sim = simulate(ac, seed, R)
    v = [cf.version_f(sim, i) for i in range(R)]
    with np.errstate(invalid="ignore"):
        sig_med = float(np.nanmedian(sim["sig"]))
    return dict(cell=ac.base.name, seed=seed, R=R, p1=[int(x[0]) for x in v], pv=[int(x[2]) for x in v],
                ev=float(sim["n"].mean()), sig_med=sig_med, secs=round(time.time() - t0, 1))


def run(reps, chunk, workers):
    from multiprocessing import Pool
    cs = cells()
    cw.population()
    jobs = [(c, 302_000_001 + 1000 * ci + j, chunk) for ci, c in enumerate(cs) for j in range(max(1, reps // chunk))]
    path = os.path.join(HERE, "check1_adv.jsonl")
    t0 = time.time()
    with Pool(workers) as pool, open(path, "a") as fh:
        for k, res in enumerate(pool.imap_unordered(_job, jobs)):
            fh.write(json.dumps(res) + "\n")
            fh.flush()
            print(f"{k + 1}/{len(jobs)} {res['cell']} {res['secs']}s total {time.time() - t0:.0f}s", flush=True)


def report():
    by: dict = {}
    for line in open(os.path.join(HERE, "check1_adv.jsonl")):
        d = json.loads(line)
        by.setdefault(d["cell"], []).append(d)
    out = []
    for cell, rs in by.items():
        n = sum(r["R"] for r in rs)
        p1 = sum(sum(r["p1"]) for r in rs) / n
        pv = sum(sum(r["pv"]) for r in rs) / n
        se = math.sqrt(max(p1 * (1 - p1), 1e-12) / n)
        out.append(f"{cell:36s} R={n:5d} run1 {p1:.4f} (se {se:.4f}) version {pv:.4f} | ev/s {np.mean([r['ev'] for r in rs]):.2f}"
                   f" | picks' median sigma {np.mean([r['sig_med'] for r in rs]) * 100:.2f}%")
    txt = "\n".join(out)
    print(txt)
    with open(os.path.join(HERE, "check1_adv.report.txt"), "w") as fh:
        fh.write(txt + "\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--reps", type=int, default=1000)
    r.add_argument("--chunk", type=int, default=50)
    r.add_argument("--workers", type=int, default=4)
    sub.add_parser("report")
    a = ap.parse_args()
    if a.cmd == "run":
        run(a.reps, a.chunk, min(4, a.workers))
    else:
        report()
