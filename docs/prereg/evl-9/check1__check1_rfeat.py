#!/usr/bin/env python
"""check1_rfeat.py (EVL-9 adversarial check #1, statistics): the registered learners' r1 / r5 / r20 columns are the
issuer's OWN trailing returns (PREREG-EVL-7 section 1.4 item 11, taken word for word by PREREG-EVL-9 section 4 item 8).
Every calibration so far (evl7 learner lens, evl9 learners lens, evl9 red team, evl9 judge) drew those columns as
fresh t(3) noise per event, so the WORST cells' "1% persistent issuer effect" (tau) was never visible to them.

SYNTHETIC ONLY: nothing here reads the lane, the House, the gateway, a store or any market data.

What is new against evl9/learners/calib_evl9.py `simulate` (copied below, otherwise unchanged):
  * every issuer has a daily abnormal return every session: its event return a when it is in the pool, else
    h_t (s_sector + beta . f + sig e) (no tau, no jump; tau_mode 'all' adds tau on every session);
  * columns 35-37 of X are r1 = d_{t-1}, r5 = sum d_{t-5..t-1}, r20 = sum d_{t-20..t-1}, clipped +-0.5 / +-1 / +-1.5
    (item 11's clips); the sessions before t = 0 are simulated (burn-in 25);
  * the prior's covariance S is re-estimated on these columns (so the warm prior has the right scale);
  * 'tauhist': the history slope also carries the population slope of y on (r1, r5, r20) implied by tau (a history era
    in which the same issuers carried the same effect, as W-TE-tau1 assumes);
  * recorded beside the record: the picks' mean tau (the path-conditional mean the generator's 'true edge' ignores).
Screened by PREREG-EVL-6's FINAL rule (evl9/judge/calib_evl9_final.py `version_f`, imported unchanged).
Usage: check1_rfeat.py run [--reps 1000] [--workers 4] | report
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
BURN = 25
RCOLS = (35, 36, 37)


@dataclasses.dataclass(frozen=True)
class RCell:
    base: cw.WCell
    rfeat: bool = True          # realistic r1/r5/r20
    tau_mode: str = "event"     # event | all
    tauhist: bool = False
    mask: bool = False          # THE FIX: an issuer's own pool sessions' changes are set to 0 in r1/r5/r20


def _daily_noise(rng, R, iss, h_t, s_sec, fac):
    sig = iss["sig"]
    e = cl.unit_t3(rng, (R, U))
    sec = iss["sector"]
    return h_t[:, None] * (np.take_along_axis(s_sec, sec, axis=1) + np.einsum("ruk,rk->ru", iss["beta"], fac) + sig * e)


_S: dict = {}


def pop_S(tau: float, tau_mode: str, mask: bool = False):
    """Within-session covariance of X with realistic r columns, and the population slope of y on X's r columns."""
    key = (round(tau, 6), tau_mode, mask)
    if key in _S:
        return _S[key]
    c = cw.WCell("pop", hist="cold", tau=tau, nbar=300.0, T=30)
    out = simulate(RCell(c, True, tau_mode, False, mask), 77_000_001, 16, collect=True)
    _S[key] = out
    return out


def simulate(rc: RCell, seed: int, R: int, collect: bool = False) -> dict:
    c = rc.base
    P = cw.population()
    rng = np.random.default_rng(seed)
    T, K = c.T, c.K
    iss = cl.issuers(rng, R, cw._cl_cell(c))
    Nmax = int(c.nbar * 3.2) + 20
    sd_c = c.sd_day()
    zday = np.zeros(R)
    vx = rng.normal(0, 0.3, R)
    drift = rng.normal(0, c.drift_sd, R) if c.drift_sd else np.zeros(R)
    kap = rng.normal(0, c.drift_c, R) if c.drift_c else np.zeros(R)
    ring = np.zeros((20, R, U))
    warm = c.hist == "warm" and c.n_eq > 0 and not collect
    if warm:
        if rc.rfeat:
            ps = pop_S(c.tau, rc.tau_mode, rc.mask)
            S_use = ps["S"]
        else:
            S_use = P["S"]
        bhat, _ = cw.history_beta(c, rng, R)
        if rc.tauhist:
            bhat = bhat + ps["slope_r"][None, :]
        A0 = np.broadcast_to(c.n_eq * S_use, (R, D, D)).copy()
        b0 = np.einsum("rde,re->rd", A0, bhat)
        N0 = np.full(R, c.n_eq)
    else:
        A0 = np.zeros((R, D, D))
        b0 = np.zeros((R, D))
        N0 = np.zeros(R)
    if c.ic_h > 0:
        wh = (c.rho_h * P["w"] / P["sd"] + math.sqrt(max(0.0, 1 - c.rho_h ** 2)) * P["wp"] / P["sdp"])
    else:
        wh = P["w"] / P["sd"]
    A = np.zeros((R, D, D))
    bv = np.zeros((R, D))
    Nw = np.zeros(R)
    rows = np.zeros(R)
    nsess = np.zeros(R)
    pend: list = []
    delta = 2.0 ** (-1.0 / c.H) if math.isfinite(c.H) else 1.0
    last = np.full((R, U), -10_000, dtype=np.int64)
    out_B = np.full((R, T), np.nan)
    out_Rm = np.full((R, T), np.nan)
    out_n = np.zeros((R, T), dtype=np.int16)
    out_ctrl = np.full((R, T), np.nan)
    out_iss = np.full((R, T, K), -1, dtype=np.int32)
    out_a = np.full((R, T, K), np.nan)
    out_tau = np.full((R, T), np.nan)
    Sacc = np.zeros((D, D))
    nacc = 0.0
    XY = np.zeros(D)
    for t in range(-BURN - c.pre, T):
        n_t = np.minimum(rng.poisson(c.nbar * rng.gamma(3.0, 1.0 / 3.0, R)), Nmax)
        g = -np.log(-np.log(rng.random((R, U))))
        keys = iss["logp"] + g
        ids = np.argpartition(-keys, Nmax - 1, axis=1)[:, :Nmax]
        order = np.argsort(-np.take_along_axis(keys, ids, axis=1), axis=1)
        ids = np.take_along_axis(ids, order, axis=1)
        valid = np.arange(Nmax)[None, :] < n_t[:, None]
        X, fam = cl.pool_features(rng, R, Nmax, iss, ids)
        if rc.rfeat:
            k1 = (t - 1) % 20
            r1 = np.take_along_axis(ring[k1], ids, axis=1)
            r5 = sum(np.take_along_axis(ring[(t - j) % 20], ids, axis=1) for j in range(1, 6))
            r20 = np.take_along_axis(ring.sum(axis=0), ids, axis=1)
            X[..., 35] = np.clip(r1, -0.5, 0.5)
            X[..., 36] = np.clip(r5, -1.0, 1.0)
            X[..., 37] = np.clip(r20, -1.5, 1.5)
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
        if c.drift_c:
            kap = c.drift_rho * kap + math.sqrt(1 - c.drift_rho ** 2) * rng.normal(0, c.drift_c, R)
        b_t = rng.normal(0.0004, 0.010, R)
        e = cl.unit_t3(rng, (R, Nmax), 1.4, 0.6) if c.ev_skew else cl.unit_t3(rng, (R, Nmax))
        jl = 0.8 if c.ev_skew else c.jump_left
        jump = np.where(rng.random((R, Nmax)) < 0.005, np.where(rng.random((R, Nmax)) < jl, -0.30, 0.30), 0.0)
        jump = jump - 0.005 * 0.30 * (1 - 2 * jl)
        noise = h_t[:, None] * (c_t[:, None] + np.take_along_axis(s_sec, sec, axis=1)
                                + np.einsum("rnk,rk->rn", beta, fac) + sig * e)
        vf = valid.astype(float)
        nv = np.maximum(vf.sum(axis=1), 1)
        chard = 0.0
        if c.drift_c:
            uh = X @ wh
            uh = uh - (uh * vf).sum(axis=1, keepdims=True) / nv[:, None]
            chard = kap[:, None] * uh
        a = sig * Ey + drift[:, None] + chard + noise + jump + tau
        a = np.maximum(a, -1.0)
        r = a + b_t[:, None]
        y = np.clip(a / sig_hat, -5, 5)
        # the issuers' daily abnormal returns of session t (event return where in the pool)
        if rc.rfeat:
            dly = _daily_noise(rng, R, iss, h_t, s_sec, fac)
            if rc.tau_mode == "all":
                dly = dly + iss["tau"]
            rr_, nn_ = np.nonzero(valid)
            dly[rr_, ids[rr_, nn_]] = 0.0 if rc.mask else a[rr_, nn_]
            ring[t % 20] = dly
        if t < -c.pre:
            continue
        if collect:
            Xd = (X - ((X * vf[..., None]).sum(axis=1) / nv[:, None])[:, None, :]) * vf[..., None]
            yd = (y - ((y * vf).sum(axis=1) / nv)[:, None]) * vf
            Sacc += np.einsum("rnd,rne->de", Xd, Xd)
            XY += np.einsum("rnd,rn->d", Xd, yd)
            nacc += vf.sum()
            continue
        while pend and pend[0][0] <= t - c.lag:
            _, As, bs, ns = pend.pop(0)
            A = delta * A + As
            bv = delta * bv + bs
            Nw = delta * Nw + ns
            rows += ns
            nsess += (ns > 0)
        if t >= 0:
            elig = valid & (np.take_along_axis(last, ids, axis=1) < t - 5)
            xbar = (X * vf[..., None]).sum(axis=1) / nv[:, None]
            Xc = X - xbar[:, None, :]
            ready = np.ones(R, dtype=bool) if warm else (rows >= 2000) & (nsess >= 3)
            At = A0 + A
            bt = b0 + bv
            Nt = np.maximum(N0 + Nw, 1.0)
            dsd = np.sqrt(np.maximum(np.einsum("rii->ri", At) / Nt[:, None], 1e-12))
            As_ = At / (dsd[:, :, None] * dsd[:, None, :]) + c.lam * np.eye(D)[None]
            bs_ = bt / dsd
            beta_s = np.linalg.solve(As_, bs_[..., None])[..., 0]
            bhat_t = beta_s / dsd
            ehat = np.einsum("rnd,rd->rn", Xc, bhat_t)
            zhat = ehat - cost / sig_hat
            key = zhat * sig_hat if c.rank == "a" else zhat
            score = np.where(elig & ready[:, None] & (zhat > 0), key, -np.inf)
            top = np.argsort(-score, axis=1)[:, :K]
            ok = np.take_along_axis(score, top, axis=1) > -np.inf
            pa = np.where(ok, np.take_along_axis(a, top, axis=1), np.nan)
            pr = np.where(ok, np.take_along_axis(r, top, axis=1), np.nan)
            pt = np.where(ok, np.take_along_axis(tau, top, axis=1), np.nan)
            pid = np.where(ok, np.take_along_axis(ids, top, axis=1), -1)
            npk = ok.sum(axis=1)
            has = npk > 0
            with np.errstate(invalid="ignore"):
                out_B[has, t] = np.nanmean(pa[has], axis=1)
                out_Rm[has, t] = np.nanmean(pr[has], axis=1)
                out_tau[has, t] = np.nanmean(pt[has], axis=1)
            out_n[:, t] = npk
            out_ctrl[:, t] = (a * vf).sum(axis=1) / nv
            out_iss[:, t, :] = pid
            out_a[:, t, :] = pa
            rr, kk = np.nonzero(ok)
            last[rr, pid[rr, kk]] = t
        ybar = (y * vf).sum(axis=1) / nv
        Xd = (X - ((X * vf[..., None]).sum(axis=1) / nv[:, None])[:, None, :]) * vf[..., None]
        yd = (y - ybar[:, None]) * vf
        As = np.matmul(Xd.transpose(0, 2, 1), Xd)
        bs = np.einsum("rnd,rn->rd", Xd, yd)
        pend.append((t, As, bs, vf.sum(axis=1)))
    if collect:
        S = Sacc / nacc
        slope = np.zeros(D)
        idx = list(RCOLS)
        sub = S[np.ix_(idx, idx)]
        slope[idx] = np.linalg.solve(sub + 1e-12 * np.eye(3), (XY / nacc)[idx])
        return dict(S=S, slope_r=slope)
    return dict(B=out_B, Rm=out_Rm, n=out_n, ctrl=out_ctrl, iss=out_iss, a=out_a, tau=out_tau)


W, WN = cw.WORST, cw.WORST_NT


def cells():
    C = lambda name, rf=True, mode="event", th=False, mask=False, **k: RCell(cw.WCell(name, **({"nbar": 300.0} | k)), rf, mode, th, mask)  # noqa: E731
    return [
        C("REPRO-noiseR-HD08-worst", rf=False, ic_h=0.08, **W),          # the judge's N1-HD08-worst (0.069), fresh seeds
        C("REPRO-noiseR-cold-worst", rf=False, hist="cold", **W),       # the judge's N1-cold-worst (0.084)
        C("R-cold-worst-notau", hist="cold", **WN),
        C("R-HD08-worst-notau", ic_h=0.08, **WN),
        C("R-cold-worst-tau1", hist="cold", **W),
        C("R-H0-worst-tau1", ic_h=0.0, **W),
        C("R-HD08-worst-tau1", ic_h=0.08, **W),
        C("R-H0-worst-tau1-tauhist", ic_h=0.0, th=True, **W),
        C("R-cold-worst-tau05", hist="cold", **(W | dict(tau=0.005))),
        C("R-H0-worst-tau05-tauhist", ic_h=0.0, th=True, **(W | dict(tau=0.005))),
        C("R-cold-worst-tau1-all", mode="all", hist="cold", **W),
        C("R-cold-base-tau1", hist="cold", tau=0.01),
        C("RM-cold-worst-tau1", mask=True, hist="cold", **W),
        C("RM-H0-worst-tau1-tauhist", mask=True, ic_h=0.0, th=True, **W),
        C("R-H0-worst-tau1-tauhist-T300", ic_h=0.0, th=True, **(W | dict(T=300))),
        C("RM-H0-worst-tau1-tauhist-T300", mask=True, ic_h=0.0, th=True, **(W | dict(T=300))),
    ]


def _job(args):
    rc, seed, R = args
    t0 = time.time()
    sim = simulate(rc, seed, R)
    v = [cf.version_f(sim, i) for i in range(R)]
    with np.errstate(invalid="ignore"):
        tau_bp = float(np.nanmean(sim["tau"]) * 1e4)
        a_bp = float(np.nanmean(sim["a"]) * 1e4)
    return dict(cell=rc.base.name, seed=seed, R=R, p1=[int(x[0]) for x in v], pv=[int(x[2]) for x in v],
                w1=[int(x[1]) for x in v], tau_bp=tau_bp, a_bp=a_bp, ev=float(sim["n"].mean()), secs=round(time.time() - t0, 1))


def run(reps, chunk, workers, only=None):
    from multiprocessing import Pool
    cs = cells()
    if only:
        cs = [c for c in cs if c.base.name in only]
    for c in cs:   # pre-compute the population S in the parent (forked workers inherit it)
        if c.rfeat and c.base.hist == "warm":
            pop_S(c.base.tau, c.tau_mode, c.mask)
    cw.population()
    jobs = [(c, 301_000_001 + 1000 * ci + j, chunk) for ci, c in enumerate(cs) for j in range(max(1, reps // chunk))]
    path = os.path.join(HERE, "check1_rfeat.jsonl")
    t0 = time.time()
    with Pool(workers) as pool, open(path, "a") as fh:
        for k, res in enumerate(pool.imap_unordered(_job, jobs)):
            fh.write(json.dumps(res) + "\n")
            fh.flush()
            print(f"{k + 1}/{len(jobs)} {res['cell']} {res['secs']}s total {time.time() - t0:.0f}s", flush=True)


def report():
    by: dict = {}
    for line in open(os.path.join(HERE, "check1_rfeat.jsonl")):
        d = json.loads(line)
        by.setdefault(d["cell"], []).append(d)
    out = []
    for cell, rs in by.items():
        n = sum(r["R"] for r in rs)
        p1 = sum(sum(r["p1"]) for r in rs) / n
        pv = sum(sum(r["pv"]) for r in rs) / n
        se = math.sqrt(max(p1 * (1 - p1), 1e-12) / n)
        tau_bp = np.mean([r["tau_bp"] for r in rs])
        a_bp = np.mean([r["a_bp"] for r in rs])
        ev = np.mean([r["ev"] for r in rs])
        out.append(f"{cell:30s} R={n:5d} run1 {p1:.4f} (se {se:.4f}) version {pv:.4f} | picks' mean tau {tau_bp:+.1f} bp,"
                   f" mean a {a_bp:+.1f} bp | ev/s {ev:.2f}")
    txt = "\n".join(out)
    print(txt)
    with open(os.path.join(HERE, "check1_rfeat.report.txt"), "w") as fh:
        fh.write(txt + "\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--reps", type=int, default=1000)
    r.add_argument("--chunk", type=int, default=50)
    r.add_argument("--workers", type=int, default=4)
    r.add_argument("--only", nargs="*")
    sub.add_parser("report")
    a = ap.parse_args()
    if a.cmd == "run":
        run(a.reps, a.chunk, min(4, a.workers), a.only)
    else:
        report()
