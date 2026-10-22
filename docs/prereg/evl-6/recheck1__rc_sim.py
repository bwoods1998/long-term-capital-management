#!/usr/bin/env python
"""rc_sim.py: RE-CHECK #1 of PREREG-EVL-6 (SYNTHETIC DATA ONLY; nothing here reads the lane, a price or a return).

An INDEPENDENT implementation, written from PREREG-EVL-6's text (sections 1.2-2 and 4.2), of
  (1) the generator of section 4.2 (issuers, sectors, Zipf popularity, cooldown, hot sectors, control counts
      Poisson(nbar/0.3 x Gamma(3,1/3)), the program's 30% of the control, the day shock AR(phi_day) with t(3) or
      crash-day innovations, sector and style factors, the volatility regime, the family drift AR(0.97), t(3) or
      left-skewed names, +-30% jumps, the knife edge N3), with optional structures used to try to break the claim:
      count coupling (cnt_kappa, money-weighted knife), count-residual coupling (kappa), drift-day correlation
      (drift_day_corr), a persistent volatility regime (vol_rho, vol_sd), issuer effects (issuer_tau);
  (2) the rule, evaluated ONLINE with no prefilter: looks at S_k in LOOKS from the first, the minimums, the exact
      sign-flip p over all 2^S vectors for S <= 16, the Monte Carlo p over 99,999 vectors for S >= 17 drawn afresh
      for every (run tag, S), q on -min(n,14) x B over the same vectors, RETIRE first, PASS with p <= alpha(S) (no
      tolerance), the guards (mean a > 0, mean r > 0, the top-14 means a > 0 and r > 0, beats its control), the
      issuer-block guard p_I <= 0.10 (9,999 vectors), the end of a run at its 60th block, and RUN 2 on blocks 61+.
Variants evaluated on the same paths: 'w' = this file; 'u' = this file's schedule with unweighted values and no
top-14 guard (D4 off); 'j' = the judge's draft (looks from 6, alpha 0.016 to S=20, 0.004 after, unweighted, no
top-14 guard).

Usage: rc_sim.py run --plan PLAN.json --out OUT.jsonl [--workers 8]
"""
from __future__ import annotations

import os

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import argparse  # noqa: E402
import dataclasses  # noqa: E402
import hashlib  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402

import numpy as np  # noqa: E402

CAP = 14
MARGIN = 0.0010
TIE = 1e-12
S_RUN = 60
MIN_EV, MIN_ISS, MIN_BLK = 30, 30, 6
ISS_G = 0.10
B_MC = 99_999
B_ISS = 4_999
NONE = 10 ** 6
SECTOR_W = np.array([.22, .14, .12, .11, .09, .08, .07, .06, .04, .04, .03])

LOOKS_6 = (9, 10, 11, 12, 13, 14, 15, 16, 18, 20, 22, 25, 30, 35, 40, 50, 60)
LOOKS_J = (6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 18, 20, 22, 25, 30, 35, 40, 50, 60)


def alpha_6(S):
    S = np.asarray(S)
    return np.where(S < 9, 0.0, np.where(S <= 14, 0.012, np.where(S <= 20, 0.010, 0.004)))


def alpha_j(S):
    S = np.asarray(S)
    return np.where(S < 6, 0.0, np.where(S <= 20, 0.016, 0.004))


LOOKS_12 = (12, 13, 14, 15, 16, 18, 20, 22, 25, 30, 35, 40, 50, 60)


def alpha_12(S):
    S = np.asarray(S)
    return np.where(S < 12, 0.0, np.where(S <= 14, 0.012, np.where(S <= 20, 0.006, 0.0025)))


# 'r12': the fixer's shortlisted schedule "looks from 12: 0.012 S12-14, 0.006 S15-20, 0.0025 S21-60", weighted + top-14
VARIANTS = {"w": (LOOKS_6, alpha_6, True), "u": (LOOKS_6, alpha_6, False), "j": (LOOKS_J, alpha_j, False),
            "r12": (LOOKS_12, alpha_12, True)}


@dataclasses.dataclass
class G:
    nbar: float = 85.0
    rho_day: float = 0.05
    phi_day: float = 0.10
    day: str = "t3"            # t3 | crash
    ev_left: float = 1.0
    ev_right: float = 1.0
    jump_left: float = 0.5
    jump_p: float = 0.005
    jump_size: float = 0.30
    drift_sd: float = 0.0
    drift_rho: float = 0.97
    drift_day_corr: float = 0.0
    mu_family: float = 0.0
    skill: float = 0.0
    vol_sd: float = 0.30
    vol_rho: float = 0.90
    cnt_kappa: float = 0.0
    mw_knife: int = 0
    kappa: float = 0.0
    issuer_tau: float = 0.0
    crash_vol: float = 0.0     # crash-day probability 0.05 x exp(crash_vol x) / E[.], clipped at 0.09 (conditional mean 0, var 1)
    vol_fb: float = 0.0        # log-volatility rises by vol_fb the session after a crash day (knife re-centred numerically)
    crash_t3: int = 0          # crash days with t(3) (not normal) ordinary days, same mean and variance
    kappa_knife: int = 0       # with kappa: re-centre so the MONEY-weighted (min(n, 14)) mean is exactly zero
    U: int = 3000
    p_read: float = 0.30
    shape_n: float = 3.0


def t3_unit(rng, size, left=1.0, right=1.0):
    """A unit-variance t(3) draw; two-piece (left/right scales) re-standardized to mean 0, variance 1."""
    x = rng.standard_t(3.0, size) / math.sqrt(3.0)
    if left == 1.0 and right == 1.0:
        return x
    x = np.where(x < 0.0, left * x, right * x)
    eabs = 2.0 / math.pi                       # E|x| of a unit-variance t(3)
    m = (right - left) * eabs / 2.0
    v = (left * left + right * right) / 2.0 - m * m
    return (x - m) / math.sqrt(v)


def day_eps(rng, kind, n, pvec=None, with_hit=False, t3days=False):
    if kind == "t3":
        e = t3_unit(rng, n)
        return (e, np.zeros(n, bool)) if with_hit else e
    k = 3.0
    p = 0.05 if pvec is None else pvec
    m = p * k / (1.0 - p)
    s = np.sqrt((1.0 - p * (k * k + 1.0)) / (1.0 - p) - m * m)
    hit = rng.random(n) < p
    ordinary = t3_unit(rng, n) if t3days else rng.standard_normal(n)
    e = np.where(hit, rng.normal(-k, 1.0, n), m + s * ordinary)
    return (e, hit) if with_hit else e


def crash_p(g, x):
    if g.crash_vol <= 0:
        return None
    norm = math.exp(g.crash_vol ** 2 * g.vol_sd ** 2 / 2.0)
    return np.minimum(0.05 * np.exp(g.crash_vol * x) / norm, 0.09)


def hc_mean(g):
    """E[h_t c_t] under vol feedback (numerical, one long path, fixed seed), so the knife edge can be re-centred."""
    rr = np.random.default_rng(86_420)
    M, B = 400_000, 50
    x = g.vol_sd * rr.standard_normal(B); z = day_eps(rr, g.day, B); prev = np.zeros(B, bool)
    acc = 0.0; cnt = 0
    for t in range(M // B + 200):
        x = g.vol_rho * x + math.sqrt(1 - g.vol_rho ** 2) * g.vol_sd * rr.standard_normal(B) + g.vol_fb * prev
        e, hit = day_eps(rr, g.day, B, crash_p(g, x), with_hit=True)
        z = g.phi_day * z + math.sqrt(1 - g.phi_day ** 2) * e
        if t >= 200:
            acc += float((np.exp(x - g.vol_sd ** 2) * z).sum()); cnt += B
        prev = hit
    return sd_day(g) * acc / cnt


def v0(g: G):
    """Event variance with no day shock (section 4.2: V0 = 0.0027)."""
    lo, hi = 0.01, 0.10
    es2 = (hi * hi - lo * lo) / (2.0 * math.log(hi / lo))
    fv = sum(m * m + 0.25 for m in (0.2, -0.1, 0.2)) * 0.006 ** 2
    return es2 + g.jump_p * g.jump_size ** 2 + 0.010 ** 2 + fv


def sd_day(g: G):
    return math.sqrt(g.rho_day / (1.0 - g.rho_day) * v0(g)) if g.rho_day > 0 else 0.0


def knife_mu_money(g: G):
    """mu_family making the program's mean a weighted by min(n, mw_knife) exactly zero when counts follow |eps|."""
    rr = np.random.default_rng(97_531)
    M = 3_000_000
    eps = day_eps(rr, g.day, M, t3days=bool(g.crash_t3))
    mult = np.exp(g.cnt_kappa * np.minimum(np.abs(eps), 4.0))
    mult = mult / mult.mean()
    nC = rr.poisson(g.nbar / g.p_read * mult * rr.gamma(g.shape_n, 1.0 / g.shape_n, M))
    n = rr.binomial(nC, g.p_read)
    w = np.minimum(n, g.mw_knife).astype(float)
    ew = float((w * eps).sum() / w.sum())
    Eh = math.exp(-g.vol_sd ** 2 / 2.0)
    return -g.skill - Eh * sd_day(g) * math.sqrt(1.0 - g.phi_day ** 2) * ew


# ------------------------------------------------------------------------------------------------ sign flips
_EXACT: dict = {}


def exact_signs(S):
    if S not in _EXACT:
        b = np.arange(1 << S, dtype=np.int64)[:, None]
        bits = (b >> np.arange(S)[None, :]) & 1
        _EXACT[S] = np.where(bits == 1, 1.0, -1.0)
    return _EXACT[S]


class Vectors:
    """Monte Carlo sign vectors: a fresh set per (tag, S), drawn from a seed string (the rule's own form)."""

    def __init__(self, base):
        self.base = base
        self.cache: dict = {}

    def get(self, tag, S):
        k = (tag, S)
        if k not in self.cache:
            if len(self.cache) > 64:
                self.cache.clear()
            sd = int.from_bytes(hashlib.sha256(f"{self.base}|{tag}S{S}".encode()).digest()[:8], "big")
            self.cache[k] = np.random.default_rng(sd).integers(0, 2, (B_MC, S), dtype=np.int8)
        return self.cache[k]


def signflip_p(Y, S, vecs, tag):
    """Rows of Y (k x S): one-sided sign-flip p of mean > 0 (ties against the program)."""
    T = Y.sum(axis=1) - S * TIE
    out = np.empty(Y.shape[0])
    if S <= 16:
        P = exact_signs(S)
        for lo in range(0, Y.shape[0], 64):
            hi = min(lo + 64, Y.shape[0])
            M = P @ Y[lo:hi].T
            out[lo:hi] = np.count_nonzero(M >= T[None, lo:hi], axis=0) / float(1 << S)
        return out
    V = vecs.get(tag, S).astype(np.float64) * 2.0 - 1.0
    for lo in range(0, Y.shape[0], 64):
        hi = min(lo + 64, Y.shape[0])
        M = V @ Y[lo:hi].T
        out[lo:hi] = (1 + np.count_nonzero(M >= T[None, lo:hi], axis=0)) / (1.0 + B_MC)
    return out


# ------------------------------------------------------------------------------------------------ simulate
class Rec:
    def __init__(self, R, U):
        self.S = np.zeros(R, np.int64)
        self.X = np.zeros((R, S_RUN))
        self.N = np.zeros((R, S_RUN))
        self.ne = np.zeros(R, np.int64)
        self.niss = np.zeros(R, np.int64)
        self.ca = np.zeros(R); self.cr = np.zeros(R); self.ta = np.zeros(R); self.tr = np.zeros(R)
        self.cbm = np.zeros(R); self.ccm = np.zeros(R)
        self.isum = np.zeros((R, U)); self.icnt = np.zeros((R, U), np.int32)


def simulate(g: G, R: int, T: int, seed: int, variants=("w", "u", "j")):
    rng = np.random.default_rng(seed)
    U = g.U
    vecs = Vectors(f"rc1|{seed}")
    iss_flips = np.where(np.random.default_rng(seed ^ 0x5EED).random((B_ISS, U)) < 0.5, -1.0, 1.0).astype(np.float32)
    sector = rng.choice(len(SECTOR_W), size=U, p=SECTOR_W)
    logw = -0.8 * np.log(np.arange(1, U + 1))
    sig = np.exp(rng.uniform(math.log(0.01), math.log(0.10), (R, U)))
    beta = np.array([0.2, -0.1, 0.2])[None, None, :] + 0.5 * rng.standard_normal((R, U, 3))
    tau = None
    if g.issuer_tau > 0:
        tau = g.issuer_tau * rng.standard_normal((R, U))
        tau -= tau.mean(axis=1, keepdims=True)
    last = np.full((R, U), -10 ** 6, np.int64)
    x = g.vol_sd * rng.standard_normal(R)
    D = g.drift_sd * rng.standard_normal(R)
    z = day_eps(rng, g.day, R)
    sdc = sd_day(g)
    mu = knife_mu_money(g) if g.mw_knife else g.mu_family
    if g.vol_fb:
        mu = mu - hc_mean(g)
    if g.kappa and g.kappa_knife:
        rr = np.random.default_rng(24_680)
        Gk = rr.gamma(g.shape_n, 1.0 / g.shape_n, 4_000_000)
        nk = rr.binomial(rr.poisson(g.nbar / g.p_read * Gk), g.p_read)
        wk = np.minimum(nk, CAP).astype(float)
        mu = mu - g.kappa * float((wk * (1.0 / g.shape_n - (Gk - 1.0))).sum() / wk.sum())
    prev_hit = np.zeros(R, bool)
    jmean = g.jump_p * g.jump_size * (1.0 - 2.0 * g.jump_left)
    cmult_norm = 1.0
    if g.cnt_kappa > 0:
        e_ = day_eps(np.random.default_rng(13_579), g.day, 2_000_000)
        cmult_norm = float(np.exp(g.cnt_kappa * np.minimum(np.abs(e_), 4.0)).mean())
    rows = np.arange(R)
    recs = [Rec(R, U), Rec(R, U)]
    gS = np.zeros(R, np.int64)          # global blocks so far
    # per variant, per record: state 0 learning, 1 passed, 2 retired, 3 ended; the session; the next look index
    st = {v: [np.zeros(R, np.int8), np.zeros(R, np.int8)] for v in variants}
    at = {v: [np.full(R, NONE, np.int64), np.full(R, NONE, np.int64)] for v in variants}
    nx = {v: [np.zeros(R, np.int64), np.zeros(R, np.int64)] for v in variants}
    ew_num = ew_den = mw_num = mw_den = 0.0
    for t in range(1, T + 1):
        x = g.vol_rho * x + math.sqrt(1.0 - g.vol_rho ** 2) * g.vol_sd * rng.standard_normal(R) + g.vol_fb * prev_hit
        h = np.exp(x - g.vol_sd ** 2)
        eps, prev_hit = day_eps(rng, g.day, R, crash_p(g, x), with_hit=True, t3days=bool(g.crash_t3))
        if g.drift_sd > 0:
            if g.drift_day_corr:
                innov = g.drift_day_corr * eps + math.sqrt(1 - g.drift_day_corr ** 2) * rng.standard_normal(R)
            else:
                innov = rng.standard_normal(R)
            D = g.drift_rho * D + math.sqrt(1.0 - g.drift_rho ** 2) * g.drift_sd * innov
        z = g.phi_day * z + math.sqrt(1.0 - g.phi_day ** 2) * eps
        c = sdc * z
        ssec = 0.010 * t3_unit(rng, (R, len(SECTOR_W)))
        fac = 0.006 * t3_unit(rng, (R, 3))
        bench = 0.0004 + 0.010 * rng.standard_normal(R)
        elig = (t - last) > 5
        Gm = rng.gamma(g.shape_n, 1.0 / g.shape_n, R)
        mult = np.exp(g.cnt_kappa * np.minimum(np.abs(eps), 4.0)) / cmult_norm if g.cnt_kappa > 0 else 1.0
        nC = np.minimum(rng.poisson(g.nbar / g.p_read * mult * Gm), elig.sum(axis=1))
        nmax = int(nC.max())
        if nmax == 0:
            continue
        key = logw[None, :] + rng.gumbel(size=(R, U))
        hot = np.where(rng.random(R) < 0.5, rng.integers(0, len(SECTOR_W), R), -1)
        key = key + np.where(sector[None, :] == hot[:, None], math.log(4.0), 0.0)
        key[~elig] = -np.inf
        if nmax < U:
            idx = np.argpartition(-key, nmax - 1, axis=1)[:, :nmax]
        else:
            idx = np.tile(np.arange(U), (R, 1))
        idx = np.take_along_axis(idx, np.argsort(-np.take_along_axis(key, idx, axis=1), axis=1), axis=1)
        m = np.arange(nmax)[None, :] < nC[:, None]
        er = np.broadcast_to(rows[:, None], m.shape)[m]
        ei = idx[m]
        last[er, ei] = t
        E = er.size
        prog = rng.random(E) < g.p_read
        e = t3_unit(rng, E, g.ev_left, g.ev_right)
        common = c[er] + ssec[er, sector[ei]] + (beta[er, ei] * fac[er]).sum(axis=1)
        a = mu + D[er] + h[er] * (common + sig[er, ei] * e)
        if g.kappa:
            a = a + g.kappa * (1.0 / g.shape_n - (Gm[er] - 1.0))
        jh = rng.random(E) < g.jump_p
        js = np.where(rng.random(E) < g.jump_left, -1.0, 1.0)
        a = a + jh * js * g.jump_size - jmean
        if tau is not None:
            a = a + tau[er, ei]
        a = a + g.skill * prog
        a = np.maximum(a, -1.0)
        r = a + bench[er]
        # rank of each program event in its row's draw order
        pr = er[prog]
        cum = np.cumsum(prog)
        first = np.r_[True, er[1:] != er[:-1]]
        base = np.maximum.accumulate(np.where(first, cum - prog, 0))
        rank = cum - base
        top = prog & (rank <= CAP)
        n = np.bincount(pr, minlength=R)
        sa = np.bincount(pr, a[prog], R)
        sr = np.bincount(pr, r[prog], R)
        tA = np.bincount(er[top], a[top], R)
        tR = np.bincount(er[top], r[top], R)
        nc = np.bincount(er, minlength=R)
        sc = np.bincount(er, a, R)
        has = n > 0
        B = np.where(has, sa / np.maximum(n, 1), 0.0)
        Cm = np.where(nc > 0, sc / np.maximum(nc, 1), 0.0)
        ew_num += float(sa.sum()); ew_den += float(n.sum())
        mw_num += float((np.minimum(n, CAP) * B).sum()); mw_den += float(np.minimum(n, CAP).sum())
        pi_ = ei[prog]
        pa = a[prog]
        for k, rec in enumerate(recs):
            act = has & (((gS >= S_RUN) & (rec.S < S_RUN)) if k == 1 else (gS < S_RUN))
            if not act.any():
                continue
            ar = np.nonzero(act)[0]
            rec.X[ar, rec.S[ar]] = B[ar]
            rec.N[ar, rec.S[ar]] = n[ar]
            rec.S[ar] += 1
            rec.ne[ar] += n[ar]
            rec.ca[ar] += sa[ar]; rec.cr[ar] += sr[ar]; rec.ta[ar] += tA[ar]; rec.tr[ar] += tR[ar]
            rec.cbm[ar] += B[ar]; rec.ccm[ar] += Cm[ar]
            pm = act[pr]
            fl = pr[pm] * U + pi_[pm]
            ic = rec.icnt.reshape(-1)
            newi = ic[fl] == 0
            # an issuer appears at most once a session for a program (the cooldown), so fl has no repeats
            np.add.at(rec.isum.reshape(-1), fl, pa[pm])
            np.add.at(ic, fl, 1)
            rec.niss += np.bincount(pr[pm][newi], minlength=R)
            S = rec.S
            mn = (rec.ne >= MIN_EV) & (rec.niss >= MIN_ISS) & (S >= MIN_BLK)
            for v in variants:
                looks, afun, weighted = VARIANTS[v]
                L = np.array(looks)
                stv, atv, nxv = st[v][k], at[v][k], nx[v][k]
                thr = L[np.minimum(nxv, L.size - 1)]
                lk = act & mn & (stv == 0) & (nxv < L.size) & (S >= thr) & (S <= S_RUN)
                lr = np.nonzero(lk)[0]
                if lr.size:
                    nxv[lr] = (S[lr][:, None] >= L[None, :]).sum(axis=1)
                    tag = f"run{k + 1}|"     # one vector set per (run, S), shared by the variants
                    for Sv in np.unique(S[lr]):
                        rs = lr[S[lr] == Sv]
                        al = float(afun(Sv))
                        Xs, Ns = rec.X[rs, :Sv], rec.N[rs, :Sv]
                        Wt = np.minimum(Ns, CAP) if weighted else np.ones_like(Ns)
                        # RETIRE first: mean a < 0 and q <= alpha + 1e-12
                        neg = rec.ca[rs] < 0
                        retired = np.zeros(rs.size, bool)
                        if neg.any():
                            q = signflip_p(-Wt[neg] * Xs[neg], int(Sv), vecs, tag)
                            retired[np.nonzero(neg)[0][q <= al + TIE]] = True
                        rr_ = rs[retired]
                        stv[rr_] = 2; atv[rr_] = t
                        cand = rs[~retired]
                        gd = (rec.ca[cand] > 0) & (rec.cr[cand] > 0) & (rec.cbm[cand] > rec.ccm[cand])
                        if weighted:
                            gd &= (rec.ta[cand] > 0) & (rec.tr[cand] > 0)
                        cand = cand[gd]
                        if cand.size:
                            Wc = np.minimum(rec.N[cand, :Sv], CAP) if weighted else 1.0
                            p = signflip_p(Wc * (rec.X[cand, :Sv] - MARGIN), int(Sv), vecs, tag)
                            pc = cand[p <= al]
                            for i in pc:
                                cnt = rec.icnt[i]
                                nz = cnt > 0
                                vals = (rec.isum[i][nz] / cnt[nz]).astype(np.float64)
                                ssum = (iss_flips[:, :vals.size] @ vals.astype(np.float32)).astype(np.float64)
                                pI = (1 + np.count_nonzero(ssum >= math.fsum(vals) - vals.size * TIE)) / (1.0 + B_ISS)
                                if pI <= ISS_G:
                                    stv[i] = 1; atv[i] = t
                ended = act & (stv == 0) & (S >= S_RUN)
                stv[ended] = 3; atv[ended] = t
        gS += has
    out = {}
    for v in variants:
        for k in range(2):
            out[f"{v}{k + 1}_st"] = st[v][k].tolist()
            out[f"{v}{k + 1}_at"] = at[v][k].tolist()
    out["S1"] = recs[0].S.tolist()
    out["ew_mean_bp"] = 1e4 * ew_num / max(ew_den, 1e-300)
    out["mw_mean_bp"] = 1e4 * mw_num / max(mw_den, 1e-300)
    out["mu_family"] = mu
    return out


def _job(args):
    lab, kw, R, T, seed, variants = args
    t0 = time.time()
    res = simulate(G(**kw), R, T, seed, variants)
    return {"lab": lab, "gen": kw, "R": R, "T": T, "seed": seed, "secs": round(time.time() - t0, 1), **res}


def run(plan_path, out_path, workers, chunk):
    from multiprocessing import get_context
    plan = json.load(open(plan_path))
    jobs = []
    for c in plan["cells"]:
        seed = c["seed0"]
        for lo in range(0, c["R"], chunk):
            seed += 1
            jobs.append((c["lab"], c["gen"], min(chunk, c["R"] - lo), c.get("T", 120), seed,
                         tuple(c.get("variants", ["w", "u", "j"]))))
    jobs.sort(key=lambda j: -j[1].get("nbar", 85))
    t0 = time.time()
    with get_context("fork").Pool(min(workers, 8)) as pool, open(out_path, "a") as fh:
        for k, row in enumerate(pool.imap_unordered(_job, jobs), 1):
            fh.write(json.dumps(row) + "\n")
            fh.flush()
            if k % 8 == 0 or k == len(jobs):
                print(f"{k}/{len(jobs)} jobs {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["run", "one"])
    ap.add_argument("--plan")
    ap.add_argument("--out")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--chunk", type=int, default=250)
    a = ap.parse_args()
    if a.cmd == "run":
        run(a.plan, a.out, a.workers, a.chunk)
    else:
        t0 = time.time()
        res = simulate(G(nbar=85, rho_day=0.15, phi_day=0.20, day="crash", ev_left=1.4, ev_right=0.6, jump_left=0.8,
                         drift_sd=0.0020, skill=0.006, mu_family=-0.006), 50, 120, 150_000_001)
        print(time.time() - t0, {k: (v if not isinstance(v, list) else sum(1 for x in v if x == 1))
                                 for k, v in res.items()})
