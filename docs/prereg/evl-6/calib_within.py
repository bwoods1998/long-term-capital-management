#!/usr/bin/env python3
"""calib_within.py: Monte Carlo calibration of the WSP-IUT promotion design (event lane), SYNTHETIC DATA ONLY.

Blind by construction: this script reads no file of the live lane (no events.sqlite, no live.sqlite, no price, no
return, no look, no band) and calls no market data. Every event below is drawn from the generator described here.
It is the calibration record of the pre-registration: keep it beside its output.

THE DESIGN CALIBRATED ("WSP-IUT"), exactly as a coder would run it on stored rows:
(A) ABSOLUTE. Block = entry session; B_s = mean a of that session's TRADABLE READ events; S = number of blocks.
    p_A = one-sided sign-flip p for mean(B) > 0: exact over all 2^S sign vectors for S <= 16
    (#{v : sum v|B| >= sum B - S*1e-12} / 2^S), else (1 + #{b : sum v_b|B| >= sum B - 1e-12}) / (1 + 99,999).
    A crosses when p_A <= alpha_A(S) + 1e-12, alpha_A(S) = c / S for 6 <= S <= 250 (design c = 0.125).
(abs) mean a > 0 and mean r > 0 over the look's READ events; minimums S >= 6, >= 30 events, >= 30 distinct issuers.
(R) RELATIVE. Units = distinct issuers of the control in session s; Z = 1 when the READ program holds the issuer in s
    (a_u = READ's own a), else a_u = the control's a (mean if several). y = clip(a / max(sigma60, .005), -5, 5);
    within-session OLS residual on [1, IWM, ln sigma60 (n >= 6), tech, health, finance (n >= 40)]; D_s, V_s
    (studentised, n-1 variances, pooled variance for a group of one), w_s = n1 n0 / n; T = sum w D / sqrt(sum w^2 V);
    p_R = (1 + #{b : T*_b >= T - 1e-12}) / (1 + B_R), per-session relabelings fixed once drawn (identical at every
    look). R holds when >= 20 READ and >= 20 non-READ units and p_R <= 0.20.
PASS at a look = A crosses AND abs AND R. A look happens at every session with >= 1 new READ event.

Outputs per cell: the first-pass session of every program for a grid of c (alpha_A = c/S), block floors and R levels,
for PASS and for A+abs alone (the intersection-union worst case: the FP when the control is so much worse that R
always holds). From those: FP with standard errors at horizons 40, 60, 120, 250 sessions; power and median sessions.

Usage:
  calib_within.py pilot              # timing + prefilter validation (full Monte Carlo at every look)
  calib_within.py run [--only REGEX] [--workers 8]
  calib_within.py report             # tables from calib_within.out.jsonl
"""
from __future__ import annotations

import os
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

import argparse
import hashlib
import itertools
import json
import math
import multiprocessing as mp
import re
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "calib_within.out.jsonl")

# ------------------------------------------------------------------------------------------------ the design's rules
C_DESIGN = 0.125
S_MIN, S_MAX = 6, 250
MIN_EV, MIN_ISS = 30, 30
R_MIN_UNITS = 20
R_LEVEL = 0.20
B_A = 99_999
EXACT_S = 16
TIE = 1e-12
C_GRID = (0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.09, 0.10, 0.11, 0.125, 0.14, 0.15, 0.175, 0.20, 0.25, 0.30, 0.40,
          0.50)
C_MAX = max(C_GRID)
FLOORS = (6, 7, 8, 10)
R_LEVELS = (0.05, 0.10, 0.20)  # PASS variants; index 0 of the last axis is A+abs alone
HORIZONS = (40, 60, 120, 250)
Z_PRE = 1.0  # S > 16: below this z the sign-flip p cannot reach C_MAX/S (validated by `pilot`)

# ------------------------------------------------------------------------------------- shared sign-flip machinery
PAT: dict[int, np.ndarray] = {}
SIGNS: np.ndarray | None = None


def _init_tables():
    global SIGNS
    for S in range(S_MIN, EXACT_S + 1):
        PAT[S] = np.array(list(itertools.product((-1.0, 1.0), repeat=S)))
    rng = np.random.default_rng(20261021)
    # row j = the sign of block j in each of the 99,999 vectors; a program's vector sums are kept incrementally
    SIGNS = np.where(rng.random((S_MAX, B_A), dtype=np.float32) < 0.5, -1, 1).astype(np.int8)


class SignFlip:
    """The session-block sign-flip p at every look. S <= 16: exact over all 2^S vectors. S > 16: Monte Carlo over the
    99,999 vectors of SIGNS, whose signed sums are carried from look to look (a settled block never changes), so
    p = (1 + #{b : sum_s v_bs |B_s| >= sum_s B_s - 1e-12}) / (1 + 99,999). (The registered rule draws a fresh seed
    per S; nesting the vectors changes only how the Monte Carlo error is shared across looks, not any look's size.)"""

    def __init__(self):
        self.P = np.zeros(B_A)
        self.x = []

    def add(self, b):
        self.x.append(b)
        self.P += SIGNS[len(self.x) - 1] * abs(b)

    def p(self, prefilter=True):
        x = np.asarray(self.x)
        S = x.size
        T = float(x.sum())
        q = math.sqrt(float((x * x).sum()))
        z = T / q if q > 0 else 0.0
        if S <= EXACT_S:
            return float(np.count_nonzero(PAT[S] @ np.abs(x) >= T - S * TIE)) / (1 << S), z
        if prefilter and z < Z_PRE:
            return float("nan"), z
        return (1 + int(np.count_nonzero(self.P >= T - TIE))) / (1 + B_A), z


# -------------------------------------------------------------------------------------------- the R statistic
def residualize(y, iwm, ls, tech, health, fin):
    n = y.size
    cols = [np.ones(n), iwm]
    if n >= 6:
        cols.append(ls)
    if n >= 40:
        cols += [tech, health, fin]
    X = np.column_stack(cols)
    keep = [0] + [j for j in range(1, X.shape[1]) if np.ptp(X[:, j]) > 0]
    X = X[:, keep]
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    return y - X @ beta


def _dv(s1, q1, tot, tot2, n1, n0, pooled):
    s0 = tot - s1
    q0 = tot2 - q1
    m1 = s1 / n1
    m0 = s0 / n0
    v1 = np.maximum((q1 - n1 * m1 * m1) / (n1 - 1), 0.0) if n1 > 1 else pooled
    v0 = np.maximum((q0 - n0 * m0 * m0) / (n0 - 1), 0.0) if n0 > 1 else pooled
    return m1 - m0, v1 / n1 + v0 / n0


def session_perm(e, Z, B, rng):
    n = e.size
    n1 = int(Z.sum())
    n0 = n - n1
    if n1 < 1 or n0 < 1:
        return None
    w = n1 * n0 / n
    e2 = e * e
    tot, tot2 = float(e.sum()), float(e2.sum())
    pooled = float(e.var(ddof=1)) if n > 1 else 0.0
    D, V = _dv(float(e[Z].sum()), float(e2[Z].sum()), tot, tot2, n1, n0, pooled)
    k = min(n1, n0)
    keys = rng.random((B, n), dtype=np.float32)
    idx = np.argpartition(keys, k - 1, axis=1)[:, :k]  # a uniform k-subset per draw
    s = e[idx].sum(1)
    qq = e2[idx].sum(1)
    if k != n1:  # drew the non-READ group: complement
        s, qq = tot - s, tot2 - qq
    Dp, Vp = _dv(s, qq, tot, tot2, n1, n0, pooled)
    return w * D, w * w * V, w * Dp, w * w * Vp, n1, n0


# ------------------------------------------------------------------------------------------------- the generator
SEC_P = np.array([0.12, 0.10, 0.14, 0.12, 0.10, 0.10, 0.08, 0.08, 0.08, 0.08])  # 0-1 tech, 2 health, 3 finance

BASE = dict(
    rate=85,            # mean READ events a session (control = rate / q)
    q=0.30,             # READ = a random 30% of the control's events (per event)
    gamma_shape=2.0,    # session count multiplier ~ Gamma(2, 1/2): CV 0.71 (news days, earnings season)
    NU=3000, zipf=0.7,  # issuer universe and popularity (top names recur in most sessions)
    p_dup=0.05,         # share of extra same-issuer events in a session (corr 0.8 with the first)
    rho_day=0.05,       # residual day shock: share of an event's (non-jump) variance, loading beta ~ U(.5,1.5)
    rho_sec=0.05,       # 10 sector shocks a session
    rho_fac=0.05,       # signed factor (momentum/value) with N(0,1) loadings
    rho_iss=0.10,       # issuer AR(1) state, phi_iss a session (repeat names close together)
    phi_iss=0.8,
    phi_day=0.10,       # day shock and factor AR(1) across sessions (factor momentum)
    kappa=10.0,         # sector clustering of a session's events: Dirichlet(kappa * SEC_P)
    day="t4",           # 't4' | 'crash' (5% days at -3 sd, skew -1.6) | 'crashx' (3% at -4.5 sd, skew -3.0)
    jump="sym",         # 'sym' +-30% at 0.25% each | 'left' -30% 0.8%, +30% 0.2% | 'leftx' -30% 1.5%, +30% 0.2%
    mu_read=0.0, mu_non=0.0, edge=0.0,  # edge goes to READ events only
    theta=0.0,          # READ tilt on the signed factor loading (odds exp(theta g))
    H=250, N=3000,
)
JUMPS = {"sym": (0.0025, 0.0025), "left": (0.008, 0.002), "leftx": (0.015, 0.002), "none": (0.0, 0.0)}
CRASH = {"crash": (0.05, 3.0), "crashx": (0.03, 4.5), "crashm": (0.05, 2.0)}  # skew -1.6, -3.0, -0.5


def _crash_params(p, k):
    m = p * k / (1 - p)
    s2 = (1 - p * (k * k + 1)) / (1 - p) - m * m
    return m, math.sqrt(s2)


class Program:
    def __init__(self, cfg, seed):
        ss = np.random.SeedSequence(seed)
        g1, g2 = ss.spawn(2)
        self.rng = np.random.default_rng(g1)
        self.prng = np.random.default_rng(g2)  # R relabelings only
        self.cfg = cfg
        rng = self.rng
        NU = cfg["NU"]
        self.NU = NU
        self.sig = np.exp(rng.uniform(math.log(0.01), math.log(0.10), NU))
        self.sec = rng.choice(10, NU, p=SEC_P)
        self.iwm = (rng.random(NU) < np.where(self.sig > 0.03, 0.7, 0.3)).astype(float)
        self.beta = rng.uniform(0.5, 1.5, NU) / math.sqrt(13.0 / 12.0)
        self.g = rng.standard_normal(NU)
        sig60 = self.sig * np.exp(0.2 * rng.standard_normal(NU)) / 1.5
        self.sig60 = np.maximum(sig60, 0.005)
        self.ls = np.log(self.sig60)
        self.tech = (self.sec <= 1).astype(float)
        self.health = (self.sec == 2).astype(float)
        self.fin = (self.sec == 3).astype(float)
        self.pop = (rng.permutation(NU) + 1.0) ** (-cfg["zipf"])
        th = cfg["theta"]
        self.qsel = np.minimum(cfg["q"] * np.exp(th * self.g - 0.5 * th * th), 0.95)
        self.u = np.zeros(NU)
        self.last = np.full(NU, -10_000)
        self.zd = 0.0
        self.h = 0.0
        self.lv = 0.0
        rs = cfg["rho_day"] + cfg["rho_sec"] + cfg["rho_fac"] + cfg["rho_iss"]
        assert rs < 1
        self.w_day, self.w_sec, self.w_fac, self.w_iss, self.w_e = (math.sqrt(cfg["rho_day"]), math.sqrt(cfg["rho_sec"]),
                                                                   math.sqrt(cfg["rho_fac"]), math.sqrt(cfg["rho_iss"]),
                                                                   math.sqrt(1 - rs))
        self.p_dn, self.p_up = JUMPS[cfg["jump"]]
        self.j_off = -0.30 * (self.p_up - self.p_dn)  # keeps E[a] at mu exactly
        if cfg["day"] in CRASH:
            p, k = CRASH[cfg["day"]]
            self.crash = (p, k) + _crash_params(p, k)
        else:
            self.crash = None
        self.lam_c = cfg["rate"] / cfg["q"]

    def _day_innov(self):
        rng = self.rng
        if self.crash is None:
            return rng.standard_t(4) / math.sqrt(2.0)
        p, k, m, s = self.crash
        if rng.random() < p:
            return rng.normal(-k, 1.0)
        return rng.normal(m, s)

    def session(self, s):
        """One session's events. Returns (read_a, read_r, read_iss, unit_tuple) or None when no control event."""
        cfg, rng = self.cfg, self.rng
        pd = cfg["phi_day"]
        self.zd = pd * self.zd + math.sqrt(1 - pd * pd) * self._day_innov()
        self.h = pd * self.h + math.sqrt(1 - pd * pd) * rng.standard_normal()
        self.lv = 0.95 * self.lv + math.sqrt(1 - 0.95 ** 2) * 0.25 * rng.standard_normal()
        v = math.exp(self.lv)
        f = rng.standard_normal(10)
        b_spy = 0.0003 + 0.009 * rng.standard_normal()
        b_iwm = b_spy + 0.005 * rng.standard_normal()
        G = rng.gamma(cfg["gamma_shape"], 1.0 / cfg["gamma_shape"])
        nc = min(int(rng.poisson(self.lam_c * G)), self.NU // 2)
        if nc == 0:
            return None
        pi = rng.dirichlet(SEC_P * cfg["kappa"])
        w = self.pop * (pi / SEC_P)[self.sec]
        keys = np.log(rng.random(self.NU)) / w
        idx = np.argpartition(-keys, nc - 1)[:nc]  # weighted sample without replacement (Efraimidis-Spirakis)
        gap = np.minimum(s - self.last[idx], 200)
        ph = cfg["phi_iss"] ** gap
        self.u[idx] = ph * self.u[idx] + np.sqrt(1 - ph * ph) * rng.standard_normal(nc)
        self.last[idx] = s
        nd = int(rng.binomial(nc, cfg["p_dup"]))
        unit = np.concatenate([np.arange(nc), rng.integers(0, nc, nd)]) if nd else np.arange(nc)
        iss = idx[unit]
        eps_u = rng.standard_t(3, nc) / math.sqrt(3.0)
        eps = eps_u[unit]
        if nd:
            eps[nc:] = math.sqrt(0.8) * eps[nc:] + math.sqrt(0.2) * rng.standard_t(3, nd) / math.sqrt(3.0)
        jr = rng.random(nc)
        jump_u = np.where(jr < self.p_dn, -0.30, np.where(jr < self.p_dn + self.p_up, 0.30, 0.0)) + self.j_off
        comp = (self.w_day * self.beta[iss] * self.zd + self.w_sec * f[self.sec[iss]] + self.w_fac * self.g[iss] * self.h
                + self.w_iss * self.u[iss] + self.w_e * eps)
        a = self.sig[iss] * v * comp + jump_u[unit]
        read = rng.random(unit.size) < self.qsel[iss]
        a = a + np.where(read, cfg["mu_read"] + cfg["edge"], cfg["mu_non"])
        a = np.maximum(a, -0.95)
        r = a + np.where(self.iwm[iss] > 0, b_iwm, b_spy)
        # R units (distinct control issuers this session)
        n_read = np.bincount(unit[read], minlength=nc)
        s_read = np.bincount(unit[read], weights=a[read], minlength=nc)
        n_all = np.bincount(unit, minlength=nc)
        s_all = np.bincount(unit, weights=a, minlength=nc)
        Z = n_read > 0
        au = np.where(Z, s_read / np.maximum(n_read, 1), s_all / n_all)
        y = np.clip(au / self.sig60[idx], -5.0, 5.0)
        units = (y, Z, self.iwm[idx], self.ls[idx], self.tech[idx], self.health[idx], self.fin[idx])
        return a[read], r[read], iss[read], units


def simulate(cfg, seed, B_R=999, prefilter=True, trace=False):
    """One program to horizon H (or until it passes at the smallest grid c, every floor and R level)."""
    P = Program(cfg, seed)
    H = cfg["H"]
    blocks = []
    sf = SignFlip()
    sum_a = sum_r = 0.0
    nev = 0
    seen = np.zeros(P.NU, bool)
    store = {}
    r_done = 0
    cWD = cW2V = 0.0
    cWDp = np.zeros(B_R)
    cW2Vp = np.zeros(B_R)
    n1t = n0t = 0
    looks = []  # (session, S, pA, absok, pR, Rmin)
    zlog = []
    for s in range(1, H + 1):
        out = P.session(s)
        if out is None:
            continue
        ra, rr, ri, units = out
        store[s] = units
        if ra.size == 0:
            continue
        blocks.append(float(ra.mean()))
        sf.add(blocks[-1])
        sum_a += float(ra.sum())
        sum_r += float(rr.sum())
        nev += ra.size
        seen[ri] = True
        S = len(blocks)
        if S < S_MIN or S > S_MAX or nev < MIN_EV or int(seen.sum()) < MIN_ISS:
            continue
        absok = sum_a > 0 and sum_r > 0
        pA, z = sf.p(prefilter=prefilter)
        pR = float("nan")
        rmin = False
        if absok and pA == pA and pA <= C_MAX / S + TIE:
            for t in range(r_done + 1, s + 1):
                un = store.pop(t, None)
                if un is None:
                    continue
                y, Z, iw, ls, te, he, fi = un
                if Z.all() or not Z.any():
                    continue
                e = residualize(y, iw, ls, te, he, fi)
                res = session_perm(e, Z, B_R, P.prng)
                if res is None:
                    continue
                wd, w2v, wdp, w2vp, n1, n0 = res
                cWD += wd
                cW2V += w2v
                cWDp += wdp
                cW2Vp += w2vp
                n1t += n1
                n0t += n0
            r_done = s
            T = cWD / math.sqrt(cW2V) if cW2V > 0 else 0.0
            with np.errstate(divide="ignore", invalid="ignore"):
                Tp = np.where(cW2Vp > 0, cWDp / np.sqrt(np.where(cW2Vp > 0, cW2Vp, 1.0)), 0.0)
            pR = (1 + int(np.count_nonzero(Tp >= T - TIE))) / (1 + B_R)
            rmin = n1t >= R_MIN_UNITS and n0t >= R_MIN_UNITS
        looks.append((s, S, pA, absok, pR, rmin))
        if trace:
            zlog.append((S, z, pA))
        # stop once every grid combination has passed
        if (absok and S >= max(FLOORS) and pA == pA and pA <= min(C_GRID) / S + TIE and rmin
                and pR <= min(R_LEVELS) + TIE):
            break
    return looks, zlog


def first_passes(looks):
    """int16 array [len(C_GRID), len(FLOORS), 1 + len(R_LEVELS)]: first session passing (-1 none); and blocks S."""
    out = np.full((len(C_GRID), len(FLOORS), 1 + len(R_LEVELS)), -1, np.int16)
    outS = np.full_like(out, -1)
    if not looks:
        return out, outS
    L = np.array(looks, dtype=float)
    sess, S, pA, absok, pR, rmin = L.T
    pA = np.where(np.isnan(pA), 9.0, pA)
    pR = np.where(np.isnan(pR), 9.0, pR)
    for i, c in enumerate(C_GRID):
        cr = (pA <= c / S + TIE) & (absok > 0)
        for j, fl in enumerate(FLOORS):
            m = cr & (S >= fl)
            for k in range(1 + len(R_LEVELS)):
                mm = m if k == 0 else m & (rmin > 0) & (pR <= R_LEVELS[k - 1] + TIE)
                w = np.flatnonzero(mm)
                if w.size:
                    out[i, j, k] = int(sess[w[0]])
                    outS[i, j, k] = int(S[w[0]])
    return out, outS


# ----------------------------------------------------------------------------------------------------- the cells
def cells():
    out = []

    def add(name, **kw):
        cfg = dict(BASE)
        cfg.update(kw)
        out.append((name, cfg))

    rates = (85, 30, 13, 8)
    rhos = (0.0, 0.05, 0.15, 0.30)
    shapes = {"sym": dict(day="t4", jump="sym"), "dayskew": dict(day="crash", jump="sym"),
              "evskew": dict(day="t4", jump="left"), "both": dict(day="crash", jump="left")}
    # 1. owner null at the boundary E[a] = 0, READ = random 30% of the control (64 cells, all looks to 250)
    for sh, kw in shapes.items():
        for rho in rhos:
            for m in rates:
                add(f"null_{sh}_rho{rho:.2f}_m{m}", rate=m, rho_day=rho, H=250, N=2000, **kw)
    # 2. common drift: negative (owner null below the boundary) and positive (no reading skill, R's job)
    for rho in (0.05, 0.30):
        for m in rates:
            add(f"drift-30_both_rho{rho:.2f}_m{m}", rate=m, rho_day=rho, mu_read=-0.003, mu_non=-0.003, day="crash",
                jump="left", H=250, N=2000)
    for mu in (0.003, 0.006):
        for rho in (0.05,):
            for m in rates:
                add(f"drift+{int(mu * 1e4)}_sym_rho{rho:.2f}_m{m}", rate=m, rho_day=rho, mu_read=mu, mu_non=mu, H=60,
                    N=2000)
    # 3. intersection-union worst case: READ at zero, control 50 bp worse (R has power, A alone guards)
    for rho in (0.05, 0.15):
        for m in (85, 8):
            add(f"iut_sym_rho{rho:.2f}_m{m}", rate=m, rho_day=rho, mu_read=0.0, mu_non=-0.005, H=60, N=2000)
    # 4. selection tilt on a signed factor (R's known failure), zero and positive drift
    for th in (0.5, 1.0):
        for mu in (0.0, 0.003):
            add(f"tilt{th}_mu{int(mu * 1e4)}_rho0.05_fac0.15_m85", rate=85, rho_day=0.05, rho_fac=0.15, theta=th,
                mu_read=mu, mu_non=mu, H=60, N=2000)
    # 5. stresses beyond the plausible grid (named, not the calibration point)
    for m in (85, 8):
        add(f"stress_crashx_leftx_rho0.30_m{m}", rate=m, rho_day=0.30, day="crashx", jump="leftx", H=250, N=2000)
        add(f"stress_ar_both_rho0.30_m{m}", rate=m, rho_day=0.30, day="crash", jump="left", phi_day=0.25,
            rho_iss=0.20, phi_iss=0.9, H=250, N=2000)
    # 6. power: edge on READ events only, control otherwise at zero, symmetric shape
    for e in (0.003, 0.006, 0.010):
        for rho in rhos:
            for m in rates:
                add(f"power{int(e * 1e4)}_sym_rho{rho:.2f}_m{m}", rate=m, rho_day=rho, edge=e, H=60, N=1000)
    # 7. sensitivity of the worst case: milder skew, no factor momentum, and a 10,000-program replicate
    for rho in (0.15, 0.30):
        for m in (85, 8):
            add(f"sens_dayskewmild_rho{rho:.2f}_m{m}", rate=m, rho_day=rho, day="crashm", jump="sym", H=250, N=2000)
    for m in (85, 8):
        add(f"sens_dayskew_noAR_rho0.30_m{m}", rate=m, rho_day=0.30, day="crash", jump="sym", phi_day=0.0, H=250,
            N=2000)
    add("sens_sym_noAR_rho0.30_m85", rate=85, rho_day=0.30, day="t4", jump="sym", phi_day=0.0, H=250, N=2000)
    add("worst10k_dayskew_rho0.30_m85", rate=85, rho_day=0.30, day="crash", jump="sym", H=250, N=10000)
    return out


def cell_seed(name):
    return int.from_bytes(hashlib.sha256(name.encode()).digest()[:4], "big")


def _work(args):
    name, cfg, lo, hi, B_R = args
    base = cell_seed(name)
    fps, fpS = [], []
    t0 = time.time()
    for i in range(lo, hi):
        looks, _ = simulate(cfg, [base, i], B_R=B_R)
        a, b = first_passes(looks)
        fps.append(a)
        fpS.append(b)
    return name, lo, np.stack(fps), np.stack(fpS), time.time() - t0


def summarize(name, cfg, fp, fpS, secs):
    N = fp.shape[0]
    res = {"cell": name, "cfg": cfg, "N": N, "cpu_s": round(secs, 1)}
    ci, fj = C_GRID.index(C_DESIGN), FLOORS.index(6)
    kR = 1 + R_LEVELS.index(R_LEVEL)

    def rate(arr, H):
        p = float(np.mean((arr >= 0) & (arr <= H)))
        return round(p, 4), round(math.sqrt(max(p * (1 - p), 1e-12) / N), 4)

    hz = [h for h in HORIZONS if h <= cfg["H"]]
    res["design"] = {f"H{h}": {"pass": rate(fp[:, ci, fj, kR], h), "Aonly": rate(fp[:, ci, fj, 0], h)} for h in hz}
    # grid at the cell's own horizon and at 40
    grid = {}
    for h in sorted(set([40, cfg["H"]])):
        g = {}
        for i, c in enumerate(C_GRID):
            for j, fl in enumerate(FLOORS):
                for k in range(1 + len(R_LEVELS)):
                    p = float(np.mean((fp[:, i, j, k] >= 0) & (fp[:, i, j, k] <= h)))
                    g[f"{c}|{fl}|{k}"] = round(p, 4)
        grid[f"H{h}"] = g
    res["grid"] = grid
    # timing of passes for the design (sessions)
    d = fp[:, ci, fj, kR].astype(float)
    dS = fpS[:, ci, fj, kR].astype(float)
    for h in sorted(set([40, cfg["H"]])):
        ok = (d >= 0) & (d <= h)
        full = np.where(ok, d, np.inf)
        med = float(np.median(full))
        res[f"timing_H{h}"] = {"median_session_all": (med if math.isfinite(med) else None),
                               "median_session_passers": (float(np.median(d[ok])) if ok.any() else None),
                               "q25_session_passers": (float(np.percentile(d[ok], 25)) if ok.any() else None),
                               "median_blocks_passers": (float(np.median(dS[ok])) if ok.any() else None)}
    # medians on the grid (sessions, all programs, inf when not passed) for power tables
    meds = {}
    for i, c in enumerate(C_GRID):
        for j, fl in enumerate(FLOORS):
            k = kR
            x = fp[:, i, j, k].astype(float)
            full = np.where((x >= 0) & (x <= 40), x, np.inf)
            mm = float(np.median(full))
            meds[f"{c}|{fl}"] = mm if math.isfinite(mm) else None
    res["median40_grid"] = meds
    return res


def run(only=None, workers=8, B_R=999, nscale=1.0, chunk=50):
    _init_tables()
    done = set()
    if os.path.exists(OUT):
        with open(OUT) as fh:
            for line in fh:
                try:
                    done.add(json.loads(line)["cell"])
                except Exception:
                    pass
    order = ("null_", "sens_", "worst", "iut_", "power", "drift", "tilt", "stress_")
    todo = [(n, c) for n, c in cells() if (only is None or re.search(only, n)) and n not in done]
    todo.sort(key=lambda nc: next((i for i, p in enumerate(order) if nc[0].startswith(p)), 99))
    print(f"{len(todo)} cells to run ({len(done)} on record)", flush=True)
    ctx = mp.get_context("fork")
    tasks = []
    for name, cfg in todo:
        N = int(cfg["N"] * nscale)
        cfg = dict(cfg, N=N)
        for lo in range(0, N, chunk):
            tasks.append((name, cfg, lo, min(N, lo + chunk), B_R))
    cfgs = {n: dict(c, N=int(c["N"] * nscale)) for n, c in todo}
    parts = {n: [] for n, _ in todo}
    need = {n: math.ceil(cfgs[n]["N"] / chunk) for n in parts}
    t0 = time.time()
    with ctx.Pool(workers) as pool:
        for name, lo, fp, fpS, secs in pool.imap_unordered(_work, tasks):
            parts[name].append((lo, fp, fpS, secs))
            if len(parts[name]) == need[name]:
                parts[name].sort(key=lambda t: t[0])
                FP = np.concatenate([p[1] for p in parts[name]])
                FPS = np.concatenate([p[2] for p in parts[name]])
                res = summarize(name, cfgs[name], FP, FPS, sum(p[3] for p in parts[name]))
                np.savez_compressed(os.path.join(SHM, f"{name}.npz"), fp=FP, fpS=FPS)
                with open(OUT, "a") as fh:
                    fh.write(json.dumps(res) + "\n")
                parts[name] = []
                d = res["design"]
                hk = max(d)
                print(f"[{time.time() - t0:7.0f}s] {name:42s} N={res['N']} pass{hk}={d[hk]['pass']} "
                      f"Aonly{hk}={d[hk]['Aonly']} cpu={res['cpu_s']}", flush=True)


SHM = os.environ.get("CALIB_SHM", "/dev/shm/calib-within")
os.makedirs(SHM, exist_ok=True)


def pilot():
    """Timing and the prefilter check: full Monte Carlo at every look (no z cut, no Hoeffding shortcut)."""
    _init_tables()
    rows = []
    worst_z = []
    for name, cfg in cells():
        if not re.match(r"null_(sym|both)_rho0\.(00|30)_m(85|8)$|power100_sym_rho0.05_m85$", name):
            continue
        cfg = dict(cfg, H=60)
        t0 = time.time()
        zmin = math.inf
        n = 40
        nl = 0
        for i in range(n):
            looks, zl = simulate(cfg, [cell_seed(name), 10_000 + i], prefilter=False, trace=True)
            for S, z, p in zl:
                nl += 1
                if S > EXACT_S and p <= C_MAX / S + TIE:
                    zmin = min(zmin, z)
                if S <= EXACT_S and p <= C_MAX / S + TIE:
                    zmin = min(zmin, z)
        dt = (time.time() - t0) / n
        rows.append((name, round(dt, 3), nl, zmin))
        print(name, "sec/program (H=60, full MC):", round(dt, 3), "looks", nl, "min z among p<=C_MAX/S:", zmin,
              flush=True)
        worst_z.append(zmin)
    # timing with the prefilter at H=250
    for name, cfg in cells():
        if name not in ("null_both_rho0.30_m85", "null_both_rho0.30_m8", "power30_sym_rho0.05_m85"):
            continue
        t0 = time.time()
        for i in range(10):
            simulate(cfg, [cell_seed(name), 20_000 + i])
        print(name, "sec/program (own H, prefilter):", round((time.time() - t0) / 10, 3), flush=True)
    print("global min z among p <= C_MAX/S:", min(worst_z), "(prefilter Z_PRE =", Z_PRE, ")")


def report():
    """Tables: owner-null FP (A+abs alone = the intersection-union worst case; PASS = with R at the random-subset null),
    the worst case, the c-grid adjustment, skill nulls, power. Writes calib_within.summary.json beside the script."""
    rows = [json.loads(l) for l in open(OUT)]
    by = {r["cell"]: r for r in rows}
    summ = {"cells": len(rows)}
    kR = 1 + R_LEVELS.index(R_LEVEL)

    def g(r, h, c, fl, k):
        return r["grid"][f"H{h}"][f"{c}|{fl}|{k}"]

    def se(p, n):
        return math.sqrt(max(p * (1 - p), 1e-12) / n)

    plaus = [r for r in rows if r["cell"].startswith("null_")]
    print("\nOWNER NULL (E[a] = 0, READ a random 30% of the control), design c = 0.125, floor 6")
    print(f"{'cell':34s} {'N':>5s} | A+abs alone: H40   H250    | PASS(R at 0.20): H40  H250")
    tab = []
    for r in plaus:
        N = r["N"]
        a40, a250 = g(r, 40, C_DESIGN, 6, 0), g(r, 250, C_DESIGN, 6, 0)
        p40, p250 = g(r, 40, C_DESIGN, 6, kR), g(r, 250, C_DESIGN, 6, kR)
        tab.append({"cell": r["cell"], "N": N, "Aonly_H40": a40, "Aonly_H250": a250, "pass_H40": p40, "pass_H250": p250,
                    "se_Aonly_H250": round(se(a250, N), 4)})
        print(f"{r['cell']:34s} {N:5d} | {a40:.3f}({se(a40, N):.3f}) {a250:.3f}({se(a250, N):.3f}) | "
              f"{p40:.3f}({se(p40, N):.3f}) {p250:.3f}({se(p250, N):.3f})")
    summ["owner_null"] = tab
    if plaus:
        w = max(tab, key=lambda t: t["Aonly_H250"])
        w40 = max(tab, key=lambda t: t["Aonly_H40"])
        summ["worst_H250"] = w
        summ["worst_H40"] = w40
        print("WORST (A+abs alone, all looks to 250):", w)
        print("WORST (A+abs alone, within 40 sessions):", w40)
        # c-grid: max over plausible cells of A+abs-alone FP at H250
        print("\nc-GRID (alpha_A = c/S): worst plausible A+abs-alone FP, all looks to 250 / within 40, by block floor")
        cg = {}
        for fl in FLOORS:
            line = []
            for c in C_GRID:
                m250 = max(g(r, 250, c, fl, 0) for r in plaus)
                m40 = max(g(r, 40, c, fl, 0) for r in plaus)
                cg[f"{c}|{fl}"] = (m250, m40)
                line.append(f"{c}:{m250:.3f}/{m40:.3f}")
            print(f" floor {fl}: " + "  ".join(line))
        summ["c_grid_worst"] = cg
        for target in (0.15, 0.08):
            ok = [c for c in C_GRID if cg[f"{c}|6"][0] <= target]
            summ[f"max_c_floor6_at_{target}"] = max(ok) if ok else None
            print(f" largest grid c (floor 6) with worst FP <= {target}: {max(ok) if ok else None}")
    others = [r for r in rows if not r["cell"].startswith(("null_", "power"))]
    print("\nOTHER NULLS AND STRESSES (design): A+abs alone and PASS, at H40 and the cell's H")
    oth = []
    for r in others:
        H = r["cfg"]["H"]
        N = r["N"]
        a40, aH = g(r, 40, C_DESIGN, 6, 0), g(r, H, C_DESIGN, 6, 0)
        p40, pH = g(r, 40, C_DESIGN, 6, kR), g(r, H, C_DESIGN, 6, kR)
        p40_10 = g(r, 40, C_DESIGN, 6, 2)
        oth.append({"cell": r["cell"], "N": N, "H": H, "Aonly_H40": a40, "Aonly_H": aH, "pass_H40": p40, "pass_H": pH,
                    "pass_H40_R0.10": p40_10, "pass_H40_R0.05": g(r, 40, C_DESIGN, 6, 1)})
        print(f"{r['cell']:44s} N={N} H={H} | A {a40:.3f}({se(a40, N):.3f}) {aH:.3f}({se(aH, N):.3f}) | "
              f"PASS {p40:.3f}({se(p40, N):.3f}) {pH:.3f}({se(pH, N):.3f}) | PASS@R.10 {p40_10:.3f}")
    summ["other"] = oth
    pw = [r for r in rows if r["cell"].startswith("power")]
    print("\nPOWER (design c = 0.125, floor 6, R at 0.20): P(promoted by 40) / by 60, median session (all, passers)")
    ptab = []
    for r in pw:
        N = r["N"]
        p40, p60 = g(r, 40, C_DESIGN, 6, kR), g(r, 60, C_DESIGN, 6, kR)
        t = r["timing_H60"]
        ptab.append({"cell": r["cell"], "N": N, "P40": p40, "P60": p60, "se40": round(se(p40, N), 4),
                     "median_all_H60": t["median_session_all"], "median_passers_H60": t["median_session_passers"],
                     "Aonly_P40": g(r, 40, C_DESIGN, 6, 0), "median40_grid": r["median40_grid"],
                     "P40_grid": {f"{c}|{fl}": g(r, 40, c, fl, kR) for c in C_GRID for fl in FLOORS}})
        print(f"{r['cell']:30s} N={N} P40 {p40:.3f}({se(p40, N):.3f}) P60 {p60:.3f} med_all "
              f"{t['median_session_all']} med_pass {t['median_session_passers']}  A-only P40 {g(r, 40, C_DESIGN, 6, 0):.3f}")
    summ["power"] = ptab
    with open(os.path.join(HERE, "calib_within.summary.json"), "w") as fh:
        json.dump(summ, fh, indent=1)
    return by


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["pilot", "run", "report", "list"])
    ap.add_argument("--only")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--br", type=int, default=999)
    ap.add_argument("--nscale", type=float, default=1.0)
    ap.add_argument("--chunk", type=int, default=50)
    a = ap.parse_args()
    if a.cmd == "pilot":
        pilot()
    elif a.cmd == "run":
        run(a.only, a.workers, a.br, a.nscale, a.chunk)
    elif a.cmd == "report":
        report()
    else:
        for n, c in cells():
            print(n, c["H"], c["N"])
