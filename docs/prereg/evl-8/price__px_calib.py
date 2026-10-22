#!/usr/bin/env python
"""px_calib.py: SYNTHETIC calibration of the price-event lane's (PX) seatable programs under the lane's judges.

SYNTHETIC ONLY. Nothing here reads the House, the gateway, events.sqlite, live.sqlite, any run record or any market
data: no price, bar, volume, return, look or band of any symbol or program. Every number comes from the generator
below, whose shape was chosen blind from the EVL-6 judge's risk set (goal-2026-10-19/evl6/PREREG-EVL-6.draft.md
section 4.2) plus the risks a price lane adds (selection on past returns: high-beta losers against an index benchmark,
sector-concentrated selections, distress jumps, repeat losers, vol-regime-driven counts).

A PX SEAT (PX-DROP-ON, PX-GAP-O1, PX-SURGE-ON of the design): each session t the rule qualifies n0_t ~ Poisson(lam x
G_t x h_t / E[h]) names (G ~ Gamma(3, 1/3): count CV 0.58; h the vol regime: more extreme movers in volatile
sessions), at most K = 20 taken (the top 20 by its rank), one event per issuer (duplicates dropped). Its events'
abnormal returns (one-session hold, a = r - b against the name's IWM/SPY benchmark, after the judge's cost):

  a_it = mu + L_t + (beta_i - 1)(m_t - mu_m) + h_t (c_t + s_{sector(i), t} + sigma_i e_it) + J_it + tau_i
  r_it = a_it + m_t   (b_t = m_t, the benchmark's same-window return)

  issuers: a pool of 2,000 (the PX universe at ADV >= $10M, a scenario), 11 sectors (weights .22 .14 .12 .11 .09 .08
  .07 .06 .04 .04 .03), Zipf(0.8) popularity (repeat losers recur), sigma_i log-uniform 1.5%-6% a window, beta_i ~
  N(beta_mean, 0.3) (losers are high beta), tau_i ~ N(0, tau) a persistent issuer effect (popularity-demeaned);
  hot sector: on half the sessions one sector draws 4x its weight (a sector sell-off fills the loser list);
  m_t: the benchmark's window return, mu_m = 4 bp, sd 0.8%, t3, with CRASH DAYS where named (5% of sessions at
  -3 sd: the beta mismatch then hits a); c_t: the basket's residual day shock, sd_c, AR(phi), t3 or crash
  innovations; s: sector shocks sd 0.8% t3; L_t: a persistent family drift AR(0.97), stationary sd drift;
  h_t = exp(x_t - .09), x AR(0.9) sd 0.3; e: unit t3 or LEFT-SKEWED (two-piece t3, scales 1.4/0.6, standardized);
  J: +-30% w.p. p_jump an event, down share dshare, mean-compensated. Every null's mean a is EXACTLY mu.
  CONTROL (the seat's named control: every no-news PX universe name in the same window, equal-weighted): its block
  C_t = mu_c + 0.5 L_t + 0.05 (m_t - mu_m) + h_t (0.5 c_t + 0.3% z_t).

NULLS: N0 (mu = 0, mu_c = 0); NK THE KNIFE EDGE (mu = 0 while the control loses 30 bp: "beats its control" never
protects; also the no-control figure). POWER: mu = 10, 20, 30, 40, 60, 80 bp (judged a, i.e. after the judge's cost),
mu_c = 0.

THE JUDGES (applied to the same paths; every p a one-sided sign-flip, ties against the program, exact over 2^S vectors
for S <= 16, else (1 + #) / 20,000 over 19,999 fixed vectors; a p is computed only where z = sum x / sqrt(sum x^2)
>= 1.0, which no alpha here below 0.02 can need below):
  J6  the EVL-6 judge's leading 10%-cap candidate as goal-2026-10-19/evl7/learner/calib_learner.py describes it
      ('L12'): looks at the first block-adding close with S >= 7, 8, 9, 10, 11, 12, 14, 16, 18, 20, 25, 30 and >= 30
      events and >= 30 issuers (deferred to the first later block where they hold; thresholds reached together are
      one look); RETIRE first when mean a < 0 and the lower-tail p (values -B) <= 0.01; PASS when p of mean(B - 10 bp)
      > 0 <= 0.01, mean a > 0, mean r > 0, beats its control (mean block > the control's over the same sessions) and
      the issuer-block p (issuer means of a, no margin, 999 vectors) <= 0.10; after the S = 30 look without a pass:
      exhausted (retired). PREREG-EVL-6's final constants are the frozen file's; this is the candidate's.
  J3  PREREG-EVL-3 section 3 as registered, minus its skew check (which only tightens: an upper bound): looks at the
      first close with >= 60, 90, 135, 200, 300, 450, 675, 1000, 1500, 2250 events, >= 40 issuers and >= 8 blocks
      (thresholds reached together are one look); PASS when the session-block p (no margin) <= 0.018, the issuer-block
      p (4,999 vectors) <= 0.018, mean a > 0, mean r > 0 and beats its control; RETIRE at a held look with mean a < 0
      and the reversed session-block p <= 0.05.
Also written per cell: the median block sd (the noise a seat's test sees) and the mean events a session.

Usage: px_calib.py run [--R 2000] [--Rp 1000] [--workers 4] [--out px_calib]   |   px_calib.py selftest
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
import multiprocessing as mp
import os
import sys
import time

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")
import numpy as np  # noqa: E402

T = 120
K = 20
NPOOL = 2000
SECTOR_W = np.array([.22, .14, .12, .11, .09, .08, .07, .06, .04, .04, .03])
NV = 19999
J6_LOOKS = (7, 8, 9, 10, 11, 12, 14, 16, 18, 20, 25, 30)
J6_ALPHA = 0.01
J6_MARGIN = 0.0010
J6_PI = 0.10
J3_LOOKS = (60, 90, 135, 200, 300, 450, 675, 1000, 1500, 2250)
J3_ALPHA = 0.018
J3_RETIRE = 0.05

NOISE = {
    "quiet":  dict(sd_c=0.003, phi=0.10, day="t3",    drift=0.0,    beta=1.0,  crash_m=False, ev="t3",   pj=0.005, dshare=0.5, tau=0.0, sig=(0.010, 0.040)),
    "base":   dict(sd_c=0.004, phi=0.10, day="t3",    drift=0.0,    beta=1.0,  crash_m=False, ev="t3",   pj=0.005, dshare=0.5, tau=0.0, sig=(0.015, 0.060)),
    "mid":    dict(sd_c=0.008, phi=0.10, day="crash", drift=0.0010, beta=1.25, crash_m=True,  ev="t3",   pj=0.005, dshare=0.5, tau=0.005, sig=(0.015, 0.060)),
    "worst":  dict(sd_c=0.015, phi=0.25, day="crash", drift=0.0020, beta=1.3,  crash_m=True,  ev="skew", pj=0.005, dshare=0.8, tau=0.010, sig=(0.015, 0.060)),
    "stress": dict(sd_c=0.022, phi=0.25, day="crash", drift=0.0030, beta=1.5,  crash_m=True,  ev="skew", pj=0.010, dshare=0.9, tau=0.010, sig=(0.015, 0.060)),
}


# ------------------------------------------------------------------------------------------------- random pieces
def t3_unit(rng, size):
    return rng.standard_t(3, size=size) / math.sqrt(3.0)


def crash_unit(rng, size):
    """5% of draws N(-3, 1), the rest N(m, s) with mean and variance set so the whole is mean 0, variance 1."""
    crash = rng.random(size) < 0.05
    # mixture: 0.05 N(-3,1) + 0.95 N(m, s^2): mean 0 -> m = 0.15/0.95; var 1 -> 0.05(1+9) + 0.95(s^2 + m^2) = 1
    m = 0.15 / 0.95
    s2 = (1.0 - 0.05 * 10.0) / 0.95 - m * m
    out = rng.normal(m, math.sqrt(s2), size)
    out[crash] = rng.normal(-3.0, 1.0, crash.sum())
    return out


_SKEW = None


def skew_unit(rng, size):
    """Two-piece t3 (left scale 1.4, right 0.6), standardized to mean 0 and variance 1 by a fixed big-sample constant."""
    global _SKEW
    if _SKEW is None:
        g = np.random.default_rng(12345)
        x = g.standard_t(3, size=4_000_000)
        y = np.where(x < 0, 1.4 * x, 0.6 * x)
        _SKEW = (float(y.mean()), float(y.std()))
    x = rng.standard_t(3, size=size)
    y = np.where(x < 0, 1.4 * x, 0.6 * x)
    return (y - _SKEW[0]) / _SKEW[1]


def ar(rng, R, T_, rho, sd, innov):
    z = np.zeros((R, T_))
    e = innov(rng, (R, T_))
    z[:, 0] = e[:, 0]
    k = math.sqrt(1 - rho * rho)
    for t in range(1, T_):
        z[:, t] = rho * z[:, t - 1] + k * e[:, t]
    return sd * z


# ------------------------------------------------------------------------------------------------- the generator
def pool(rng, tau, sig=(0.015, 0.060)):
    sector = rng.choice(len(SECTOR_W), size=NPOOL, p=SECTOR_W)
    pop = (1.0 + rng.permutation(NPOOL)) ** -0.8
    sigma = np.exp(rng.uniform(math.log(sig[0]), math.log(sig[1]), NPOOL))
    beta_dev = rng.normal(0.0, 0.3, NPOOL)
    tau_i = rng.normal(0.0, tau, NPOOL) if tau > 0 else np.zeros(NPOOL)
    w = pop / pop.sum()
    tau_i = tau_i - (w * tau_i).sum()
    # within-sector CDFs
    cdfs, members = [], []
    for k in range(len(SECTOR_W)):
        idx = np.nonzero(sector == k)[0]
        p = pop[idx] / pop[idx].sum()
        cdfs.append(np.cumsum(p))
        members.append(idx)
    sec_share = np.array([pop[sector == k].sum() for k in range(len(SECTOR_W))]) / pop.sum()
    return dict(sector=sector, sigma=sigma, beta_dev=beta_dev, tau=tau_i, cdfs=cdfs, members=members, sec_share=sec_share)


def generate(rng, R, lam, nz, mu, mu_c, kcap=K):
    K_ = kcap
    P = pool(rng, nz["tau"], nz["sig"])
    nsec = len(SECTOR_W)
    x = ar(rng, R, T, 0.9, 0.3, lambda g, s: g.normal(0, 1, s))
    h = np.exp(x - 0.09)
    innov_day = crash_unit if nz["day"] == "crash" else t3_unit
    c = ar(rng, R, T, nz["phi"], nz["sd_c"], innov_day)
    L = ar(rng, R, T, 0.97, nz["drift"], lambda g, s: g.normal(0, 1, s)) if nz["drift"] > 0 else np.zeros((R, T))
    mu_m, sd_m = 0.0004, 0.008
    m = mu_m + sd_m * (crash_unit(rng, (R, T)) if nz["crash_m"] else t3_unit(rng, (R, T)))
    s = 0.008 * t3_unit(rng, (R, T, nsec))
    # counts
    G = rng.gamma(3.0, 1.0 / 3.0, (R, T))
    lam_t = lam * G * h / h.mean()
    n0 = np.minimum(rng.poisson(lam_t), K_)
    # sectors of the K slots: hot sector on half the sessions draws 4x its share
    hot = rng.random((R, T)) < 0.5
    hot_k = rng.choice(nsec, size=(R, T), p=P["sec_share"])
    base = P["sec_share"]
    u = rng.random((R, T, K_))
    sec = np.empty((R, T, K_), dtype=np.int64)
    cum0 = np.cumsum(base)
    sec_nohot = np.minimum(np.searchsorted(cum0, u), nsec - 1)
    sec[:] = sec_nohot
    for k in range(nsec):
        sel = hot & (hot_k == k)
        if not sel.any():
            continue
        p = base.copy()
        p[k] *= 4.0
        p /= p.sum()
        cum = np.cumsum(p)
        sec[sel] = np.minimum(np.searchsorted(cum, u[sel]), nsec - 1)
    iss = np.empty((R, T, K_), dtype=np.int64)
    u2 = rng.random((R, T, K_))
    for k in range(nsec):
        sel = sec == k
        pos = np.minimum(np.searchsorted(P["cdfs"][k], u2[sel]), len(P["members"][k]) - 1)
        iss[sel] = P["members"][k][pos]
    slot = np.arange(K_)[None, None, :]
    valid = slot < n0[:, :, None]
    # one event per issuer per session: drop duplicates
    flat = np.where(valid, iss, -1).reshape(R * T, K_)
    order = np.argsort(flat, axis=1, kind="stable")
    srt = np.take_along_axis(flat, order, axis=1)
    dup_sorted = np.zeros_like(srt, dtype=bool)
    dup_sorted[:, 1:] = (srt[:, 1:] == srt[:, :-1]) & (srt[:, 1:] >= 0)
    dup = np.zeros_like(dup_sorted)
    np.put_along_axis(dup, order, dup_sorted, axis=1)
    valid = valid & ~dup.reshape(R, T, K_)
    # event values
    ev = skew_unit if nz["ev"] == "skew" else t3_unit
    e = ev(rng, (R, T, K_))
    sig = P["sigma"][iss]
    bdev = (nz["beta"] - 1.0) + P["beta_dev"][iss]
    s_ev = np.take_along_axis(s, sec, axis=2)
    jump = np.zeros((R, T, K_))
    if nz["pj"] > 0:
        jh = rng.random((R, T, K_)) < nz["pj"]
        down = rng.random((R, T, K_)) < nz["dshare"]
        jump = np.where(jh, np.where(down, -0.30, 0.30), 0.0)
        jump -= nz["pj"] * 0.30 * (1 - 2 * nz["dshare"])
    tau_ev = P["tau"][iss]
    if nz["tau"] > 0:
        tau_ev = tau_ev - tau_ev[valid].mean()
    a = (mu + L[:, :, None] + bdev * (m - mu_m)[:, :, None]
         + h[:, :, None] * (c[:, :, None] + s_ev + sig * e) + jump + tau_ev)
    a = np.maximum(a, -1.0)
    r = a + m[:, :, None]
    zc = rng.normal(0, 1, (R, T))
    C = mu_c + 0.5 * L + 0.05 * (m - mu_m) + h * (0.5 * c + 0.003 * zc)
    return dict(a=a, r=r, iss=iss, valid=valid, C=C)


# ------------------------------------------------------------------------------------------------- sign-flip p
_EXACT = {}
_V = None
_VI = {}


def exact_signs(S):
    if S not in _EXACT:
        b = np.arange(2 ** S, dtype=np.int64)[:, None]
        bits = (b >> np.arange(S)[None, :]) & 1
        _EXACT[S] = (2 * bits - 1).astype(np.float64)
    return _EXACT[S]


def mc_signs():
    global _V
    if _V is None:
        g = np.random.default_rng(20261022)
        _V = (2 * g.integers(0, 2, size=(NV, 160)) - 1).astype(np.float64)
    return _V


def issuer_signs(nvec, n):
    key = nvec
    if key not in _VI or _VI[key].shape[1] < n:
        g = np.random.default_rng(777 + nvec)
        _VI[key] = (2 * g.integers(0, 2, size=(nvec, max(n, 2500))) - 1).astype(np.float64)
    return _VI[key][:, :n]


def signflip_p(x):
    """One-sided sign-flip p of sum(x) > 0, ties against (exact for S <= 16, else 19,999 fixed vectors)."""
    S = len(x)
    tot = math.fsum(x) - S * 1e-12
    if S <= 16:
        M = exact_signs(S)
        return float(np.count_nonzero(M @ x >= tot)) / M.shape[0]
    V = mc_signs()[:, :S]
    return (1.0 + np.count_nonzero(V @ x >= tot)) / (NV + 1.0)


def zstat(x):
    q = math.sqrt(float(np.dot(x, x)))
    return 0.0 if q == 0 else float(np.sum(x)) / q


def issuer_p(a_ev, iss_ev, nvec):
    ids, inv = np.unique(iss_ev, return_inverse=True)
    sums = np.bincount(inv, weights=a_ev)
    cnt = np.bincount(inv)
    vals = sums / cnt
    if zstat(vals) < 1.0:
        return 1.0
    V = issuer_signs(nvec, len(vals))
    tot = math.fsum(vals) - len(vals) * 1e-12
    return (1.0 + np.count_nonzero(V @ vals >= tot)) / (nvec + 1.0)


# ------------------------------------------------------------------------------------------------- the judges
def judge_rep(a, r, iss, valid, C):
    """(J6 outcome, J3 outcome) for one replicate: each (status, session) with status 'pass', 'retire', 'exhaust',
    'none'; the session is 1-based (the close at which the look is written)."""
    n_t = valid.sum(axis=1)
    blocks = np.nonzero(n_t > 0)[0]
    B = np.array([a[t, valid[t]].mean() for t in blocks]) if len(blocks) else np.zeros(0)
    # cumulative event-level sums at each block
    a_sum = np.cumsum([a[t, valid[t]].sum() for t in blocks]) if len(blocks) else np.zeros(0)
    r_sum = np.cumsum([r[t, valid[t]].sum() for t in blocks]) if len(blocks) else np.zeros(0)
    n_cum = np.cumsum(n_t[blocks]) if len(blocks) else np.zeros(0)
    seen = set()
    iss_cum = []
    for t in blocks:
        seen.update(iss[t, valid[t]].tolist())
        iss_cum.append(len(seen))
    Cb = C[blocks] if len(blocks) else np.zeros(0)

    def record(j):  # events of blocks 0..j
        ts = blocks[: j + 1]
        return np.concatenate([a[t, valid[t]] for t in ts]), np.concatenate([iss[t, valid[t]] for t in ts])

    # J6
    j6 = ("none", None)
    pending = list(J6_LOOKS)
    for j in range(len(blocks)):
        S = j + 1
        if not pending or pending[0] > S:
            continue
        if n_cum[j] < 30 or iss_cum[j] < 30:
            continue
        pending = [k for k in pending if k > S]
        sess = int(blocks[j]) + 1
        mean_a = a_sum[j] / n_cum[j]
        mean_r = r_sum[j] / n_cum[j]
        x = B[:S]
        if mean_a < 0 and zstat(-x) >= 1.0 and signflip_p(-x) <= J6_ALPHA + 1e-12:
            j6 = ("retire", sess)
            break
        xm = x - J6_MARGIN
        if (mean_a > 0 and mean_r > 0 and x.mean() > Cb[:S].mean() and zstat(xm) >= 1.0
                and signflip_p(xm) <= J6_ALPHA + 1e-12):
            ae, ie = record(j)
            if issuer_p(ae, ie, 999) <= J6_PI + 1e-12:
                j6 = ("pass", sess)
                break
        if not pending:
            j6 = ("exhaust", sess)
            break
    # J3
    j3 = ("none", None)
    pend3 = list(J3_LOOKS)
    for j in range(len(blocks)):
        S = j + 1
        if not pend3 or n_cum[j] < pend3[0]:
            continue
        if iss_cum[j] < 40 or S < 8:
            continue
        pend3 = [k for k in pend3 if k > n_cum[j]]
        sess = int(blocks[j]) + 1
        mean_a = a_sum[j] / n_cum[j]
        mean_r = r_sum[j] / n_cum[j]
        x = B[:S]
        if (mean_a > 0 and mean_r > 0 and x.mean() > Cb[:S].mean() and zstat(x) >= 1.0
                and signflip_p(x) <= J3_ALPHA + 1e-12):
            ae, ie = record(j)
            if issuer_p(ae, ie, 4999) <= J3_ALPHA + 1e-12:
                j3 = ("pass", sess)
                break
        if mean_a < 0 and zstat(-x) >= 1.0 and signflip_p(-x) <= J3_RETIRE + 1e-12:
            j3 = ("retire", sess)
            break
    return j6, j3, (float(B.std(ddof=1)) if len(B) > 2 else float("nan")), float(n_t.mean())


def run_cell(args):
    name, kind, noise, lam, kcap, mu, mu_c, R, seed = args
    t0 = time.time()
    rng = np.random.default_rng(seed)
    out6, out3, bsd, nmean = [], [], [], []
    BATCH = 100
    done = 0
    while done < R:
        b = min(BATCH, R - done)
        g = generate(rng, b, lam, NOISE[noise], mu, mu_c, kcap)
        for i in range(b):
            j6, j3, sd, nm = judge_rep(g["a"][i], g["r"][i], g["iss"][i], g["valid"][i], g["C"][i])
            out6.append(j6)
            out3.append(j3)
            bsd.append(sd)
            nmean.append(nm)
        done += b

    def summ(outs):
        st = [o[0] for o in outs]
        ss = np.array([o[1] if o[0] == "pass" else 10 ** 6 for o in outs])
        res = {"pass": st.count("pass") / R, "retire": st.count("retire") / R, "exhaust": st.count("exhaust") / R}
        for horizon in (10, 20, 30, 60, 120):
            res[f"pass_by_{horizon}"] = float(np.mean(ss <= horizon))
        passed = ss[ss < 10 ** 6]
        res["median_pass_session"] = float(np.median(passed)) if len(passed) else None
        return res

    return {"cell": name, "kind": kind, "noise": noise, "lam": lam, "kcap": kcap, "mu_bp": round(mu * 1e4, 1),
            "ctrl_bp": round(mu_c * 1e4, 1), "R": R, "J6": summ(out6), "J3": summ(out3),
            "block_sd_bp": round(float(np.nanmedian(bsd)) * 1e4, 1), "events_per_session": round(float(np.mean(nmean)), 2),
            "secs": round(time.time() - t0, 1),
            "seed": seed}


def cells(R, Rp):
    out = []
    seed = 82_000_001
    LK = ((8, 20), (20, 20), (40, 20), (40, 40))
    for noise, (lam, kcap), null in itertools.product(("quiet", "base", "mid", "worst", "stress"), LK, ("N0", "NK")):
        mu_c = 0.0 if null == "N0" else -0.0030
        out.append((f"{null}-{noise}-lam{lam}-K{kcap}", "null", noise, lam, kcap, 0.0, mu_c, R, seed))
        seed += 1
    for noise, (lam, kcap), mu in itertools.product(("quiet", "base", "mid", "worst"), LK, (10, 20, 30, 40, 60, 80)):
        out.append((f"P{mu}-{noise}-lam{lam}-K{kcap}", "power", noise, lam, kcap, mu * 1e-4, 0.0, Rp, seed))
        seed += 1
    return out


def selftest():
    # exact sign-flip on a tiny case
    x = np.array([1.0, 2.0, -0.5])
    p = signflip_p(x)
    brute = sum(1 for s in itertools.product((-1, 1), repeat=3) if np.dot(s, x) >= x.sum() - 3e-12) / 8
    assert abs(p - brute) < 1e-12, (p, brute)
    # null mean exactly zero by construction (large sample)
    rng = np.random.default_rng(1)
    g = generate(rng, 200, 20, NOISE["worst"], 0.0, 0.0)
    m = g["a"][g["valid"]].mean()
    print("selftest: sign-flip ok; worst-cell null mean a = %.5f (n=%d)" % (m, g["valid"].sum()))
    g = generate(rng, 200, 20, NOISE["base"], 0.0, 0.0)
    print("selftest: base-cell null mean a = %.5f; mean events a session %.2f" % (g["a"][g["valid"]].mean(), g["valid"].sum(axis=2).mean()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("run", "selftest"))
    ap.add_argument("--R", type=int, default=2000)
    ap.add_argument("--Rp", type=int, default=1000)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--out", default="px_calib")
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    if a.cmd == "selftest":
        selftest()
        return
    todo = cells(a.R, a.Rp)
    if a.only:
        todo = [c for c in todo if a.only in c[0]]
    t0 = time.time()
    with mp.Pool(min(4, a.workers)) as pool_, open(a.out + ".jsonl", "w") as fh:
        for i, res in enumerate(pool_.imap_unordered(run_cell, todo)):
            fh.write(json.dumps(res) + "\n")
            fh.flush()
            print(f"{i + 1}/{len(todo)} {res['cell']} J6 {res['J6']['pass']:.3f} J3 {res['J3']['pass']:.3f} "
                  f"blocksd {res['block_sd_bp']} n {res['events_per_session']} ({res['secs']}s, {time.time() - t0:.0f}s)",
                  flush=True)


if __name__ == "__main__":
    main()
