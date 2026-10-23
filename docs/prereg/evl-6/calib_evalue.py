#!/usr/bin/env python
"""EVL-EPROC-1 calibration on SYNTHETIC data only (the pre-registration's calibration record).

Nothing here reads the live lane: no events.sqlite, no live.sqlite, no boxrun.py, no market data, no price, no look,
no band. Every number comes from the generator below, chosen blind to the lane's results.

    python calib_evalue.py selftest            # judge arithmetic vs eproc_ref.py (stdlib reference), bit-level
    python calib_evalue.py run [--workers N]   # the grid -> calib_evalue.out.jsonl + calib_evalue.summary.txt
    python calib_evalue.py summarize           # re-print the summary from the jsonl
    python calib_evalue.py life|extra|life2|fix  # 120-session lifetime cells, extra stresses, skew-fix variants
    python calib_evalue.py report              # every phase's worst cases per judge variant -> calib_evalue.report.txt

PHASES RUN (seeds fixed in run()): p40 = every core null x rho {0,.05,.15,.30} x n {85,30,13,8} at 4,000 programs and
40 sessions, stresses at rho {0,.05}, power at 2,000; life = key cells at 120 sessions (2,000 nulls, 1,000 power);
extra = skew at high rho, skew + drift, strong skew, everything stacked, the worst cells at 16,000; life2 / fix = the
worst skew and drift cells at 120 sessions with 4,000 programs and the money-process K / D variants, power at 2,000.

THE JUDGE (EVL-EPROC-1, exactly as written in eproc_ref.py; re-implemented vectorized over replicates, and checked
against eproc_ref.paths / promotion_guards by `selftest`):
  block t = the t-th session holding >= 1 TRADABLE event of P; capped a' = min(a, 0.25); n, x = mean a', q = within SS.
  se2 = (20*0.04^2 + sum q_i) / (20 + sum (n_i - 1)) over past blocks.
  scale of a unit series (u_i, m_i), k past: B = max(0, sum u^2 - k ubar^2 - se2 sum m); sc2 = max(smin^2,
  (5 s0^2 + B)/(5 + max(k-1, 0))); v = sc2 + se2 m_t; s = sqrt v; L = 2 s; d = 0.03 s.
  bet: z = (clip(u, -L, L) - d)/(L + d); g = clip((theta - d)(L + d)/(theta^2 + v), 0, 0.9); log W += log(1 + g z).
  W^A money: u = x, m = 1/n, s0 .006, smin .002, theta .006.  W^C: u = x - x^C, m = 1/n + 1/nC - 2 nboth/(n nC),
  s0 .001, smin .0005, theta .004 (no bet when m <= 1e-12).  R retirement: u = .002 - x, theta .004, fires at R >= 10.
  PROMOTE at the first block with W^A_t >= 6.667, max_{s<=t} W^C_s >= 6.667, G1 (mean raw a > 0, mean raw r > 0),
  G2 (>= 20 issuers, issuer-block sign-flip p <= 0.10 on per-issuer mean raw a), G3 (mean P block raw-a mean > mean
  C block raw-a mean over the same sessions). Retirement is checked first at each block (decide()'s order).
  Simulation shortcut, the only one: G2's sign-flip uses B = 4,999 numpy sign vectors (the rule pins 99,999 vectors
  from a seed string); it is a Monte Carlo p of the same test. FP is also reported without G2 (an upper bound).

ADJUSTMENT VARIANTS evaluated on the very same paths (judge only; the generator is shared):
  m0 = a money-null margin: W^A bets on u = x - m0 with target theta - m0 (H0^A becomes E[x | F] <= m0);
  thr_a / thr_c = the money / control-relative thresholds; K / D = the money process's clip and skew allowance
  (in predicted sd; the design's 2.0 and 0.03).

THE GENERATOR (per replicate = one READ program and its same-window family control; vectorized over replicates):
  universe   U = 3000 issuers in 11 sectors (weights .22 .14 .12 .11 .09 .08 .07 .06 .04 .04 .03); issuer popularity
             Zipf(zipf_s = 0.8) by a fixed rank (issuer repeats: popular names recur every few sessions).
  per issuer sigma_i ~ log-uniform [1%, 10%] a session (heteroskedastic names); style loadings beta_i,j ~ N(mu_j, 0.5)
             on 3 style factors (momentum-like, value-like, size-like), mu = (0.2, -0.1, 0.2); optional persistent
             effect tau_i ~ N(0, issuer_tau^2), demeaned over the universe; optional AR(1) issuer story shock.
  sessions   control count n_C,t ~ Poisson(nbar / p_read * Gamma(3, 1/3)) (CV 0.58), drawn WITHOUT replacement from the
             issuers not held by the control within the last 5 sessions (cooldown), weights Zipf x hot sector: with
             prob 0.5 a session has one hot sector whose issuers' weights are x4 (news-day sector clustering).
             READ = each control event independently with prob p_read = 0.30 (a random 30% subset: READ's events are
             a subset of C's, n_both = n_P; the control is 3.33x READ), or tilted on factor-1 loading (stress S4).
  per event  a = mu_family + D_t + h_t (c_t + s_{sector,t} + sum_j beta_ij f_jt + sigma_i e_it) + beta_i1 F_t
                 + tau_i + story_it + jump_it + skill * [READ-selected]
             c_t   residual DAY shock common to every event of the session: sd_c * unit t(3); sd_c^2 = rho_day/(1 -
                   rho_day) * V0, so rho_day = Var(c)/(event variance); V0 = E sigma^2 + jump var + sector var + factor
                   var = 0.00269 (event sd 5.2%); rho_day in {0, .05, .15, .30} gives sd_c = 0, 1.2%, 2.2%, 3.4%.
             s_k,t sector shock, sd 1.0% unit t(3) (sector clustering).    f_j,t style factor day returns, sd 0.6% t(3).
             e_it  unit t(3) (fat tails; two-piece left skew 1.4/0.6 in stress S1, applied to c_t too).
             jump  +-30% w.p. 0.005 (half down; 75% down in S1), mean-compensated, so the null mean is exactly mu.
             h_t   session volatility regime exp(x_t - .09), x AR(1) rho .9, sd .3, E h^2 = 1 (heteroskedastic days).
             D_t   family DRIFT common to READ and control: AR(1) stationary sd drift_sd, rho drift_rho (0 = none).
             F_t   factor-1 drift (stress S4 only), AR(1).
             a is floored at -1.0 (a 1e-4-probability event; bias < 0.1 bp).
             b_t   benchmark return N(4 bp, 1%) a session, shared by the session's events; r = a + b_t.
  NULLS      N1    no skill, mu_family 0: READ mean 0, READ - control 0 (both H0 true).
             N2+/- no skill, a constant common drift mu_family = +-30 bp (+: the money condition holds, selection is
                   null; -: both null).
             N3    "the absolute condition": READ beats its control by skill 60 bp but loses money on net:
                   mu_family = -60 bp so READ's mean is exactly 0 (H0^A true at its boundary, H0^C false).
             N3-AR N3 plus a zero-mean AR(1) family drift (sd 10/20/30 bp, rho .97 or .90): READ's long-run mean is 0
                   but its conditional mean wanders (H0^A's conditional form is FALSE for weeks at a time: the risk the
                   design names; its guarantee does not cover it, so it is calibrated).
             N2-AR no skill plus a 30 bp AR drift (W^C must hold it).
  STRESSES   S1 left skew; S2 persistent issuer effects (1%, Zipf .8; 2%, Zipf 1.1); S3 no cooldown + issuer story
             shocks 2% rho .6 (several events of one issuer close together); S4 READ tilted on factor-1 loading
             (+0.3 vs the family) with factor-1 drift 30 bp rho .97 (selection with no skill that the control-relative
             difference does NOT cancel); S5 N3 with skill 30 bp + AR 20 bp.
  POWER      skill 30, 60, 100 bp on READ events only, mu_family 0 (READ mean = skill; control mean 0.3 x skill).
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import math
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REF_DIR = os.path.expanduser("~/Work/.ltcm-main/scratch/evl-eproc")
OUT = os.path.join(HERE, "calib_evalue.out.jsonl")
SUMMARY = os.path.join(HERE, "calib_evalue.summary.txt")

# ------------------------------------------------------------------ EVL-EPROC-1 constants (eproc_ref.py, pinned)
WCLIP = 0.25
KCLIP = 2.0
DSKEW = 0.03
SE0, ME = 0.04, 20.0
SC0, MC, SCMIN = 0.006, 5.0, 0.002
SC0_C, SCMIN_C = 0.001, 0.0005
TH_A, TH_C, GMAX = 0.006, 0.004, 0.9
TH_RET_NULL, TH_DOWN_BET = 0.002, 0.004
THR = 1.0 / 0.15
THR_DOWN = 10.0
ISS_ALPHA, MIN_ISS = 0.10, 20
B_FLIPS = 4999

SECTOR_W = np.array([.22, .14, .12, .11, .09, .08, .07, .06, .04, .04, .03])


@dataclasses.dataclass(frozen=True)
class Gen:
    nbar: float = 85.0
    p_read: float = 0.30
    shape_n: float = 3.0
    rho_day: float = 0.05
    U: int = 3000
    zipf_s: float = 0.8
    hot_p: float = 0.5
    hot_mult: float = 4.0
    sd_sector: float = 0.010
    sd_factor: float = 0.006
    beta_mean: tuple = (0.2, -0.1, 0.2)
    beta_sd: float = 0.5
    sig_lo: float = 0.01
    sig_hi: float = 0.10
    skew_left: float = 1.0
    skew_right: float = 1.0
    jump_p: float = 0.005
    jump_size: float = 0.30
    jump_left: float = 0.5
    vol_sd: float = 0.30
    vol_rho: float = 0.90
    cooldown: int = 5
    issuer_tau: float = 0.0
    story_sd: float = 0.0
    story_rho: float = 0.6
    mu_family: float = 0.0
    drift_sd: float = 0.0
    drift_rho: float = 0.97
    skill: float = 0.0
    tilt: float = 0.0
    fdrift_sd: float = 0.0
    fdrift_rho: float = 0.97
    b_mu: float = 0.0004
    b_sd: float = 0.010

    def v0(self) -> float:
        es2 = (self.sig_hi ** 2 - self.sig_lo ** 2) / (2.0 * math.log(self.sig_hi / self.sig_lo))
        jv = self.jump_p * self.jump_size ** 2
        fv = sum(m * m + self.beta_sd ** 2 for m in self.beta_mean) * self.sd_factor ** 2
        return es2 + jv + self.sd_sector ** 2 + fv

    def sd_day(self) -> float:
        return math.sqrt(self.rho_day / (1.0 - self.rho_day) * self.v0()) if self.rho_day > 0 else 0.0


@dataclasses.dataclass(frozen=True)
class Judge:
    name: str
    m0: float = 0.0
    thr_a: float = THR
    thr_c: float = THR
    use_g2: bool = True
    use_ret: bool = True
    K: float = KCLIP       # money process only: session clip, in predicted sd
    D: float = DSKEW       # money process only: skew allowance, in predicted sd

    def akey(self):
        return (self.m0, self.K, self.D)


JUDGES = (
    Judge("design"),
    Judge("design_noG2", use_g2=False),
    Judge("design_noRet", use_ret=False),
    Judge("m0_05", m0=0.0005), Judge("m0_10", m0=0.0010), Judge("m0_15", m0=0.0015), Judge("m0_20", m0=0.0020),
    Judge("m0_25", m0=0.0025), Judge("m0_30", m0=0.0030),
    Judge("thrA_12.5", thr_a=12.5), Judge("thrA_20", thr_a=20.0), Judge("thrA_40", thr_a=40.0),
    Judge("thrAC_12.5", thr_a=12.5, thr_c=12.5),
    Judge("m0_10_thrA_12.5", m0=0.0010, thr_a=12.5), Judge("m0_15_thrA_12.5", m0=0.0015, thr_a=12.5),
    Judge("m0_20_thrA_12.5", m0=0.0020, thr_a=12.5), Judge("m0_15_thrAC_12.5", m0=0.0015, thr_a=12.5, thr_c=12.5),
    Judge("m0_20_thrAC_12.5", m0=0.0020, thr_a=12.5, thr_c=12.5),
    # added for the extra phase (finer grid near the 15% and 8% boundaries)
    Judge("m0_12.5", m0=0.00125), Judge("m0_17.5", m0=0.00175), Judge("m0_22.5", m0=0.00225),
    Judge("m0_17.5_thrA_12.5", m0=0.00175, thr_a=12.5), Judge("m0_15_thrA_10", m0=0.0015, thr_a=10.0),
    Judge("m0_20_thrAC_12.5_dup", m0=0.0020, thr_a=12.5, thr_c=12.5),
    # scale-proportional skew fixes (phase "fix"): wider money clip K, larger money skew allowance D
    Judge("K3", K=3.0), Judge("D06", D=0.06), Judge("m0_10_K3", m0=0.0010, K=3.0), Judge("m0_15_K3", m0=0.0015, K=3.0),
    Judge("m0_10_D06", m0=0.0010, D=0.06), Judge("m0_15_D06", m0=0.0015, D=0.06), Judge("m0_15_D10", m0=0.0015, D=0.10),
    Judge("m0_15_K3_D05", m0=0.0015, K=3.0, D=0.05), Judge("m0_20_K3", m0=0.0020, K=3.0),
    Judge("m0_20_D06", m0=0.0020, D=0.06),
    Judge("m0_15_K3_thrA_12.5", m0=0.0015, K=3.0, thr_a=12.5), Judge("m0_20_K3_thrA_12.5", m0=0.0020, K=3.0, thr_a=12.5),
    Judge("m0_20_K3_thrAC_12.5", m0=0.0020, K=3.0, thr_a=12.5, thr_c=12.5),
    Judge("m0_20_D06_thrAC_12.5", m0=0.0020, D=0.06, thr_a=12.5, thr_c=12.5),
)


# ------------------------------------------------------------------------------------------------ distributions
def _abs_mean_t(df: float) -> float:
    """E|T| / sd for a unit-variance t(df)."""
    return (2.0 * math.sqrt(df) * math.gamma((df + 1) / 2) / (math.sqrt(math.pi) * (df - 1) * math.gamma(df / 2))
            / math.sqrt(df / (df - 2.0)))


def unit_t3(rng, size, left=1.0, right=1.0):
    x = rng.standard_t(3.0, size) / math.sqrt(3.0)
    if left != 1.0 or right != 1.0:
        x = np.where(x < 0, left * x, right * x)
        m1 = (right - left) * _abs_mean_t(3.0) / 2.0
        m2 = (left ** 2 + right ** 2) / 2.0
        x = (x - m1) / math.sqrt(m2 - m1 ** 2)
    return x


# ------------------------------------------------------------------------------------------------ the judge
class Scale:
    """The predictable scale of one session-unit series (eproc_ref.Scale, vectorized)."""

    def __init__(self, R, sc0, scmin):
        self.sc0, self.scmin = sc0, scmin
        self.sx = np.zeros(R); self.sxx = np.zeros(R); self.sinv = np.zeros(R); self.k = np.zeros(R)

    def at(self, se2, mi):
        m = np.where(self.k > 0, self.sx / np.maximum(self.k, 1.0), 0.0)
        between = np.maximum(0.0, self.sxx - self.k * m * m - se2 * self.sinv)
        sc2 = np.maximum(self.scmin ** 2, (MC * self.sc0 ** 2 + between) / (MC + np.maximum(self.k - 1.0, 0.0)))
        v = sc2 + se2 * mi
        s = np.sqrt(v)
        return v, KCLIP * s, DSKEW * s

    def add(self, mask, u, mi):
        uu = np.where(mask, u, 0.0)
        self.sx += uu; self.sxx += uu * uu; self.sinv += np.where(mask, mi, 0.0); self.k += mask


def bet_inc(u, v, L, d, target):
    z = (np.clip(u, -L, L) - d) / (L + d)
    g = np.clip((target - d) * (L + d) / (target * target + v), 0.0, GMAX)
    return np.log1p(g * z)


class JudgeState:
    """All of EVL-EPROC-1's first-promotion machinery for R replicates and a list of judge variants."""

    def __init__(self, R, U, judges, flips):
        self.R, self.U, self.judges, self.flips = R, U, judges, flips
        self.sq = np.zeros(R); self.sdf = np.zeros(R)
        self.sa = Scale(R, SC0, SCMIN); self.sc = Scale(R, SC0_C, SCMIN_C)
        self.akeys = sorted({j.akey() for j in judges} | {(0.0, KCLIP, DSKEW)})
        self.lwa_m0 = {k: np.zeros(R) for k in self.akeys}
        self.lwc = np.zeros(R); self.maxlwc = np.full(R, -np.inf); self.lr = np.zeros(R)
        self.blocks = np.zeros(R, np.int32)
        self.cum_sa = np.zeros(R); self.cum_sr = np.zeros(R); self.cum_bm = np.zeros(R)
        self.cum_cbm = np.zeros(R); self.n_cblk = np.zeros(R)
        self.isum = np.zeros(R * U); self.icnt = np.zeros(R * U, np.int64)
        self.n_iss = np.zeros(R, np.int64)
        self.retired = np.full(R, np.nan)
        self.first = {k: np.full(R, np.nan) for k in ("WA", "WC", "R")}
        self.promo = {j.name: np.full(R, np.nan) for j in judges}
        self.promo_block = {j.name: np.full(R, np.nan) for j in judges}
        self.g2_calls = 0
        self.trace = None  # selftest: per-block logs

    def step(self, t, P, C, iss_flat, iss_a, rng):
        """One SESSION t (1-based). P: dict of per-rep arrays n, s1 (sum capped), s2 (sum sq capped), sa (sum raw a),
        sr (sum raw r); C: n, s1, sa, nboth. iss_flat / iss_a: the session's P events (rep*U + issuer, raw a)."""
        n = P["n"]; has = n > 0
        nn = np.maximum(n, 1)
        x = np.where(has, P["s1"] / nn, 0.0)
        q = np.where(has, P["s2"] - P["s1"] * x, 0.0)  # sum (a' - x)^2 = s2 - n x^2
        mi = 1.0 / nn
        se2 = (ME * SE0 ** 2 + self.sq) / (ME + self.sdf)
        v, L, d = self.sa.at(se2, mi)
        sd_ = np.sqrt(v)
        for (m0, kk, dd) in self.akeys:
            self.lwa_m0[(m0, kk, dd)] += np.where(has, bet_inc(x - m0, v, kk * sd_, dd * sd_, TH_A - m0), 0.0)
        self.lr += np.where(has, bet_inc(TH_RET_NULL - x, v, L, d, TH_DOWN_BET), 0.0)
        nc = C["n"]; hasc = has & (nc > 0)
        ncc = np.maximum(nc, 1)
        xc = np.where(hasc, C["s1"] / ncc, 0.0)
        mc = np.where(hasc, 1.0 / nn + 1.0 / ncc - 2.0 * C["nboth"] / (nn * ncc), 0.0)
        okc = hasc & (mc > 1e-12)
        diff = x - xc
        vc, Lc, dc = self.sc.at(se2, mc)
        self.lwc += np.where(okc, bet_inc(diff, vc, Lc, dc, TH_C), 0.0)
        self.sc.add(okc, diff, mc)
        self.sq += q; self.sdf += np.where(has, n - 1, 0)
        self.sa.add(has, x, mi)
        self.maxlwc = np.where(okc, np.maximum(self.maxlwc, self.lwc), self.maxlwc)
        # guards' running figures
        self.blocks += has
        self.cum_sa += P["sa"]; self.cum_sr += P["sr"]
        self.cum_bm += np.where(has, P["sa"] / nn, 0.0)
        self.cum_cbm += np.where(hasc, C["sa"] / ncc, 0.0); self.n_cblk += hasc
        if iss_flat.size:
            np.add.at(self.isum, iss_flat, iss_a)
            before = self.icnt[iss_flat] == 0
            np.add.at(self.icnt, iss_flat, 1)
            newi = np.bincount(iss_flat[before] // self.U, minlength=self.R) if before.any() else 0
            # duplicates inside one session cannot happen (one event per issuer per session), so `before` is exact
            self.n_iss += newi
        g1 = (self.cum_sa > 0) & (self.cum_sr > 0)
        g3 = (self.n_cblk > 0) & (self.cum_bm / np.maximum(self.blocks, 1) > self.cum_cbm / np.maximum(self.n_cblk, 1))
        giss = self.n_iss >= MIN_ISS
        lr10 = math.log(THR_DOWN)
        newly_ret = has & np.isnan(self.retired) & (self.lr >= lr10)
        for k, cond in (("WA", self.lwa_m0[(0.0, KCLIP, DSKEW)] >= math.log(THR)), ("WC", self.maxlwc >= math.log(THR)),
                        ("R", self.lr >= lr10)):
            self.first[k][np.isnan(self.first[k]) & cond] = t
        pcache = {}
        base = has & g1 & g3 & giss
        for j in self.judges:
            lwa = self.lwa_m0[j.akey()]
            alive = np.isnan(self.promo[j.name])
            if j.use_ret:
                alive &= np.isnan(self.retired) & ~newly_ret
            cand = alive & base & (lwa >= math.log(j.thr_a)) & (self.maxlwc >= math.log(j.thr_c))
            idx = np.nonzero(cand)[0]
            if idx.size and j.use_g2:
                ok = np.zeros(idx.size, bool)
                for ii, r in enumerate(idx):
                    if r not in pcache:
                        pcache[r] = self._signflip_p(r)
                    ok[ii] = pcache[r] <= ISS_ALPHA
                idx = idx[ok]
            self.promo[j.name][idx] = t
            self.promo_block[j.name][idx] = self.blocks[idx]
        self.retired[newly_ret] = t
        if self.trace is not None:
            self.trace.append({"has": has.copy(), "lwa": self.lwa_m0[(0.0, KCLIP, DSKEW)].copy(), "lwc": self.lwc.copy(),
                               "lr": self.lr.copy(), "g13iss": (g1 & g3 & giss).copy(), "v": v.copy()})

    def _signflip_p(self, r):
        self.g2_calls += 1
        lo = r * self.U
        c = self.icnt[lo:lo + self.U]
        nz = c > 0
        vals = self.isum[lo:lo + self.U][nz] / c[nz]
        n = vals.size
        if n > self.flips.shape[1]:
            raise ValueError("more issuers than flip columns")
        s = self.flips[:, :n] @ vals.astype(np.float32)
        thr = math.fsum(vals) - n * 1e-12 - 1e-6 * math.fsum(abs(vals))  # float32 rounding: ties count against
        return (1 + int(np.count_nonzero(s >= thr))) / (1 + self.flips.shape[0])


# ------------------------------------------------------------------------------------------------ the generator
def simulate(g: Gen, R: int, T: int, seed: int, judges=JUDGES, keep_events: int = 0, trace: bool = False):
    rng = np.random.default_rng(seed)
    U = g.U
    sector = rng.choice(len(SECTOR_W), size=U, p=SECTOR_W)
    logw = -g.zipf_s * np.log(np.arange(1, U + 1))
    isig = np.exp(rng.uniform(math.log(g.sig_lo), math.log(g.sig_hi), (R, U)))
    beta = (np.array(g.beta_mean)[None, None, :] + g.beta_sd * rng.standard_normal((R, U, 3))).astype(np.float64)
    tau = None
    if g.issuer_tau > 0:
        tau = g.issuer_tau * rng.standard_normal((R, U)); tau -= tau.mean(axis=1, keepdims=True)
    story = np.zeros((R, U)) if g.story_sd > 0 else None
    if g.tilt != 0.0:
        zb = (beta[:, :, 0] - g.beta_mean[0]) / g.beta_sd
        psel = np.minimum(0.95, g.p_read * np.exp(g.tilt * zb - g.tilt ** 2 / 2.0))
    else:
        psel = None
    last = np.full((R, U), -10_000, np.int32)
    lvol = rng.standard_normal(R) * g.vol_sd
    D = rng.standard_normal(R) * g.drift_sd if g.drift_sd > 0 else np.zeros(R)
    F = rng.standard_normal(R) * g.fdrift_sd if g.fdrift_sd > 0 else np.zeros(R)
    sd_c = g.sd_day()
    jmean = g.jump_p * g.jump_size * (1.0 - 2.0 * g.jump_left)
    rate_c = g.nbar / g.p_read
    flips = np.where(np.random.default_rng(seed + 99_991).random((B_FLIPS, U), np.float32) < 0.5, np.float32(-1.0),
                     np.float32(1.0))
    J = JudgeState(R, U, judges, flips)
    if trace:
        J.trace = []
    kept = {r: [] for r in range(keep_events)}
    totP = np.zeros(R); totC = np.zeros(R); sumP = np.zeros(R)
    rows = np.arange(R)
    hot_add = math.log(g.hot_mult)
    for t in range(1, T + 1):
        lvol = g.vol_rho * lvol + math.sqrt(1 - g.vol_rho ** 2) * g.vol_sd * rng.standard_normal(R)
        h = np.exp(lvol - g.vol_sd ** 2)
        if g.drift_sd > 0:
            D = g.drift_rho * D + math.sqrt(1 - g.drift_rho ** 2) * g.drift_sd * rng.standard_normal(R)
        if g.fdrift_sd > 0:
            F = g.fdrift_rho * F + math.sqrt(1 - g.fdrift_rho ** 2) * g.fdrift_sd * rng.standard_normal(R)
        if story is not None:
            story = g.story_rho * story + math.sqrt(1 - g.story_rho ** 2) * g.story_sd * rng.standard_normal((R, U))
        c_day = sd_c * unit_t3(rng, R, g.skew_left, g.skew_right) if sd_c > 0 else np.zeros(R)
        s_sec = g.sd_sector * unit_t3(rng, (R, len(SECTOR_W)))
        f_fac = g.sd_factor * unit_t3(rng, (R, 3))
        b = g.b_mu + g.b_sd * rng.standard_normal(R)
        # the control's events: n_C issuers without replacement (Gumbel top-k) among those out of cooldown
        elig = (t - last) > g.cooldown
        n_el = elig.sum(axis=1)
        nC = np.minimum(rng.poisson(rate_c * rng.gamma(g.shape_n, 1.0 / g.shape_n, R)), n_el)
        nmax = int(nC.max())
        if nmax == 0:
            J.step(t, {k: np.zeros(R) for k in ("n", "s1", "s2", "sa", "sr")},
                   {"n": np.zeros(R), "s1": np.zeros(R), "sa": np.zeros(R), "nboth": np.zeros(R)},
                   np.zeros(0, np.int64), np.zeros(0), rng)
            continue
        keys = logw[None, :] + rng.gumbel(size=(R, U))
        hot = np.where(rng.random(R) < g.hot_p, rng.integers(0, len(SECTOR_W), R), -1)
        keys += np.where(sector[None, :] == hot[:, None], hot_add, 0.0)
        keys[~elig] = -np.inf
        if nmax < U:
            idx = np.argpartition(-keys, nmax - 1, axis=1)[:, :nmax]
        else:
            idx = np.tile(np.arange(U), (R, 1))
        kv = np.take_along_axis(keys, idx, axis=1)
        idx = np.take_along_axis(idx, np.argsort(-kv, axis=1), axis=1)
        mask = np.arange(nmax)[None, :] < nC[:, None]
        er = np.broadcast_to(rows[:, None], mask.shape)[mask]
        ei = idx[mask]
        last[er, ei] = t
        E = er.size
        # READ selection
        if psel is None:
            sel = rng.random(E) < g.p_read
        else:
            sel = rng.random(E) < psel[er, ei]
        # returns
        noise = isig[er, ei] * unit_t3(rng, E, g.skew_left, g.skew_right)
        common = c_day[er] + s_sec[er, sector[ei]] + (beta[er, ei, :] * f_fac[er, :]).sum(axis=1)
        a = g.mu_family + D[er] + h[er] * (common + noise) + beta[er, ei, 0] * F[er]
        if g.jump_p > 0:
            hit = rng.random(E) < g.jump_p
            sgn = np.where(rng.random(E) < g.jump_left, -1.0, 1.0)
            a = a + hit * sgn * g.jump_size - jmean
        if tau is not None:
            a = a + tau[er, ei]
        if story is not None:
            a = a + story[er, ei]
        a = a + g.skill * sel
        a = np.maximum(a, -1.0)
        rr = a + b[er]
        ac = np.minimum(a, WCLIP)
        # program (READ) and control session figures
        pr = er[sel]
        nP = np.bincount(pr, minlength=R).astype(float)
        P = {"n": nP, "s1": np.bincount(pr, ac[sel], R), "s2": np.bincount(pr, ac[sel] ** 2, R),
             "sa": np.bincount(pr, a[sel], R), "sr": np.bincount(pr, rr[sel], R)}
        Cd = {"n": np.bincount(er, minlength=R).astype(float), "s1": np.bincount(er, ac, R),
              "sa": np.bincount(er, a, R), "nboth": nP}
        totP += nP; totC += Cd["n"]; sumP += P["sa"]
        J.step(t, P, Cd, pr.astype(np.int64) * U + ei[sel], a[sel], rng)
        if keep_events:
            for r in range(keep_events):
                m = er == r
                evs = [{"event": f"{t}-{int(i)}", "a": float(av), "r": float(rv), "issuer": int(i), "sel": bool(s)}
                       for i, av, rv, s in zip(ei[m], a[m], rr[m], sel[m])]
                kept[r].append({"day": t, "events": evs})
    return J, {"meanP": float(totP.mean() / T), "meanC": float(totC.mean() / T),
               "meanA_P": float(sumP.sum() / max(totP.sum(), 1)), "sd_day": sd_c, "v0": g.v0()}, kept


# ------------------------------------------------------------------------------------------------ cells
NB = (85, 30, 13, 8)
RHOS = (0.0, 0.05, 0.15, 0.30)


def cells(phase="p40"):
    """p40: every cell over 40 sessions (the task's horizon). life: key cells over 120 sessions (a program's looks
    continue for life; power medians beyond 40). quick: a small smoke version of p40."""
    out = []
    if phase == "life":
        return _life_cells()
    if phase == "extra":
        return _extra_cells()
    if phase == "fix":
        n3 = dict(skill=0.0060, mu_family=-0.0060)
        skew = dict(skew_left=1.4, skew_right=0.6, jump_left=0.75)
        out = []
        for lab, kw in (("X1 N3 + left skew + AR drift 30bp", dict(nbar=85, rho_day=0.0, **n3, **skew, drift_sd=0.0030)),
                        ("X2 N3 + strong left skew (t3 2.0/0.5, 85% jumps down)",
                         dict(nbar=85, rho_day=0.30, **n3, skew_left=2.0, skew_right=0.5, jump_left=0.85)),
                        ("X2 N3 + strong left skew (t3 2.0/0.5, 85% jumps down)",
                         dict(nbar=30, rho_day=0.30, **n3, skew_left=2.0, skew_right=0.5, jump_left=0.85)),
                        ("X2 N3 + strong left skew (t3 2.0/0.5, 85% jumps down)",
                         dict(nbar=85, rho_day=0.15, **n3, skew_left=2.0, skew_right=0.5, jump_left=0.85)),
                        ("S1 N3 + left skew (t3 1.4/0.6, 75% jumps down)", dict(nbar=85, rho_day=0.15, **n3, **skew)),
                        ("S1 N3 + left skew (t3 1.4/0.6, 75% jumps down)", dict(nbar=85, rho_day=0.30, **n3, **skew)),
                        ("N3-AR30 absolute + AR drift 30bp rho.97", dict(nbar=85, rho_day=0.0, **n3, drift_sd=0.0030)),
                        ("N3-AR30 absolute + AR drift 30bp rho.97", dict(nbar=30, rho_day=0.0, **n3, drift_sd=0.0030)),
                        ("N3-AR20 absolute + AR drift 20bp rho.97", dict(nbar=85, rho_day=0.0, **n3, drift_sd=0.0020)),
                        ("X3 everything: N3 + skew + AR30 + issuer 1% + no cooldown story 2%",
                         dict(nbar=85, rho_day=0.0, **n3, **skew, drift_sd=0.0030, issuer_tau=0.010, cooldown=0,
                              story_sd=0.020)),
                        ("N2+ no skill, common drift +30bp", dict(nbar=85, rho_day=0.0, mu_family=0.0030)),
                        ("N1 no skill", dict(nbar=85, rho_day=0.0)), ("N1 no skill", dict(nbar=8, rho_day=0.05)),
                        ("N3 absolute: READ beats C by 60bp, READ mean 0", dict(nbar=85, rho_day=0.05, **n3)),
                        ("N3 absolute: READ beats C by 60bp, READ mean 0", dict(nbar=8, rho_day=0.05, **n3))):
            out.append(("fix-null", lab, kw, 4000, 120))
        for mu in (0.0030, 0.0060, 0.0100):
            for rho in RHOS:
                for nb in NB:
                    out.append(("fix-power", f"P edge {int(mu * 1e4)}bp", dict(nbar=nb, rho_day=rho, skill=mu), 2000, 120))
        return out
    if phase == "life2":
        n3 = dict(skill=0.0060, mu_family=-0.0060)
        skew = dict(skew_left=1.4, skew_right=0.6, jump_left=0.75)
        return [("life-null", "X1 N3 + left skew + AR drift 30bp", dict(nbar=85, rho_day=0.0, **n3, **skew, drift_sd=0.0030), 2000, 120),
                ("life-null", "X2 N3 + strong left skew (t3 2.0/0.5, 85% jumps down)",
                 dict(nbar=85, rho_day=0.30, **n3, skew_left=2.0, skew_right=0.5, jump_left=0.85), 2000, 120),
                ("life-null", "S1 N3 + left skew (t3 1.4/0.6, 75% jumps down)", dict(nbar=85, rho_day=0.15, **n3, **skew), 2000, 120)]
    R_NULL, R_POW, T = (1000, 500, 40) if phase == "quick" else (4000, 2000, 40)
    core = {
        "N1 no skill": dict(),
        "N2+ no skill, common drift +30bp": dict(mu_family=0.0030),
        "N2- no skill, common drift -30bp": dict(mu_family=-0.0030),
        "N3 absolute: READ beats C by 60bp, READ mean 0": dict(skill=0.0060, mu_family=-0.0060),
        "N3-AR20 absolute + AR drift 20bp rho.97": dict(skill=0.0060, mu_family=-0.0060, drift_sd=0.0020),
        "N3-AR30 absolute + AR drift 30bp rho.97": dict(skill=0.0060, mu_family=-0.0060, drift_sd=0.0030),
        "N2-AR30 no skill + AR drift 30bp rho.97": dict(drift_sd=0.0030),
    }
    for (lab, kw) in core.items():
        for rho in RHOS:
            for nb in NB:
                out.append(("null", lab, dict(nbar=nb, rho_day=rho, **kw), R_NULL, T))
    stress = {
        "S1 N3 + left skew (t3 1.4/0.6, 75% jumps down)": dict(skill=0.0060, mu_family=-0.0060, skew_left=1.4,
                                                              skew_right=0.6, jump_left=0.75),
        "S1b N1 + left skew": dict(skew_left=1.4, skew_right=0.6, jump_left=0.75),
        "S2 N3 + issuer effect 1% Zipf .8": dict(skill=0.0060, mu_family=-0.0060, issuer_tau=0.010),
        "S2b N3 + issuer effect 2% Zipf 1.1": dict(skill=0.0060, mu_family=-0.0060, issuer_tau=0.020, zipf_s=1.1),
        "S3 N3 + no cooldown + story 2% rho.6": dict(skill=0.0060, mu_family=-0.0060, cooldown=0, story_sd=0.020),
        "S4 tilt (no skill) + factor-1 drift 30bp": dict(tilt=0.6, fdrift_sd=0.0030),
        "S5 N3 skill 30bp + AR drift 20bp": dict(skill=0.0030, mu_family=-0.0030, drift_sd=0.0020),
        "S6 N3-AR10 rho.97": dict(skill=0.0060, mu_family=-0.0060, drift_sd=0.0010),
        "S7 N3-AR20 rho.90": dict(skill=0.0060, mu_family=-0.0060, drift_sd=0.0020, drift_rho=0.90),
        "S8 N3-AR30 rho.90": dict(skill=0.0060, mu_family=-0.0060, drift_sd=0.0030, drift_rho=0.90),
    }
    for (lab, kw) in stress.items():
        for rho in (0.0, 0.05):
            for nb in NB:
                out.append(("stress", lab, dict(nbar=nb, rho_day=rho, **kw), R_NULL, T))
    for mu in (0.0030, 0.0060, 0.0100):
        for rho in RHOS:
            for nb in NB:
                out.append(("power", f"P edge {int(mu * 1e4)}bp", dict(nbar=nb, rho_day=rho, skill=mu), R_POW, T))
    return out


def _extra_cells():
    out = []
    T, R = 40, 4000
    n3 = dict(skill=0.0060, mu_family=-0.0060)
    skew = dict(skew_left=1.4, skew_right=0.6, jump_left=0.75)
    for rho in (0.15, 0.30):
        for nb in NB:
            out.append(("extra", "S1 N3 + left skew (t3 1.4/0.6, 75% jumps down)", dict(nbar=nb, rho_day=rho, **n3, **skew), R, T))
    for rho in (0.0, 0.05, 0.15):
        for nb in (85, 30):
            out.append(("extra", "X1 N3 + left skew + AR drift 30bp", dict(nbar=nb, rho_day=rho, **n3, **skew, drift_sd=0.0030), R, T))
    for rho in (0.05, 0.15, 0.30):
        for nb in (85, 30, 8):
            out.append(("extra", "X2 N3 + strong left skew (t3 2.0/0.5, 85% jumps down)",
                        dict(nbar=nb, rho_day=rho, **n3, skew_left=2.0, skew_right=0.5, jump_left=0.85), R, T))
    for rho in (0.0, 0.05):
        for nb in (85, 30):
            out.append(("extra", "X3 everything: N3 + skew + AR30 + issuer 1% + no cooldown story 2%",
                        dict(nbar=nb, rho_day=rho, **n3, **skew, drift_sd=0.0030, issuer_tau=0.010, cooldown=0,
                             story_sd=0.020), R, T))
    out.append(("extra", "X4 N3-AR30 worst cell, 16k reps", dict(nbar=85, rho_day=0.0, **n3, drift_sd=0.0030), 16000, T))
    out.append(("extra", "X5 N3-AR20 worst cell, 16k reps", dict(nbar=85, rho_day=0.0, **n3, drift_sd=0.0020), 16000, T))
    for mu in (0.0030, 0.0060, 0.0100):   # power for the new variants at the base settings
        for rho in (0.0, 0.05):
            for nb in NB:
                out.append(("extra-power", f"P edge {int(mu * 1e4)}bp", dict(nbar=nb, rho_day=rho, skill=mu), 2000, T))
    return out


def _life_cells():
    out = []
    T, R = 120, 2000
    life = {
        "N1 no skill": dict(),
        "N3 absolute: READ beats C by 60bp, READ mean 0": dict(skill=0.0060, mu_family=-0.0060),
        "N3-AR20 absolute + AR drift 20bp rho.97": dict(skill=0.0060, mu_family=-0.0060, drift_sd=0.0020),
        "N3-AR30 absolute + AR drift 30bp rho.97": dict(skill=0.0060, mu_family=-0.0060, drift_sd=0.0030),
        "S6 N3-AR10 rho.97": dict(skill=0.0060, mu_family=-0.0060, drift_sd=0.0010),
        "N2+ no skill, common drift +30bp": dict(mu_family=0.0030),
    }
    for (lab, kw) in life.items():
        for rho in (0.0, 0.05):
            for nb in NB:
                out.append(("life-null", lab, dict(nbar=nb, rho_day=rho, **kw), R, T))
    for mu in (0.0030, 0.0060, 0.0100):
        for rho in RHOS:
            for nb in NB:
                out.append(("life-power", f"P edge {int(mu * 1e4)}bp", dict(nbar=nb, rho_day=rho, skill=mu), 1000, T))
    return out


def _job(args):
    kind, lab, kw, R, T, seed = args
    t0 = time.time()
    J, info, _ = simulate(Gen(**kw), R, T, seed)
    res = {j: J.promo[j].tolist() for j in J.promo}
    res.update({"first_" + k: v.tolist() for k, v in J.first.items()})
    res["retired"] = J.retired.tolist()
    res["promo_block_design"] = J.promo_block["design"].tolist()
    return kind, lab, json.dumps(kw, sort_keys=True), R, T, info, res, time.time() - t0, J.g2_calls


def _rate(times, T):
    a = np.asarray(times, float)
    p = float(np.mean(~np.isnan(a) & (a <= T)))
    return p, math.sqrt(max(p * (1 - p), 1e-12) / a.size)


def _median(times):
    a = np.asarray(times, float)
    a = np.where(np.isnan(a), np.inf, a)
    m = float(np.median(a))
    return None if math.isinf(m) else m


def run(workers, phase="p40", chunk=500):
    from multiprocessing import Pool
    jobs, seed = [], {"p40": 20_261_021, "quick": 10_000, "life": 30_261_021, "extra": 40_261_021,
                      "life2": 50_261_021, "fix": 60_261_021}[phase]
    for kind, lab, kw, R, T in cells(phase):
        for c in range(0, R, chunk):
            seed += 1
            jobs.append((kind, lab, kw, min(chunk, R - c), T, seed))
    jobs.sort(key=lambda j: -j[2]["nbar"])
    acc = {}
    t0 = time.time()
    done = 0
    with Pool(workers) as pool:
        for kind, lab, kws, R, T, info, res, secs, g2 in pool.imap_unordered(_job, jobs):
            key = (kind, lab, kws, T)
            a = acc.setdefault(key, {"R": 0, "info": [], "res": {}, "secs": 0.0, "g2": 0})
            a["R"] += R; a["info"].append(info); a["secs"] += secs; a["g2"] += g2
            for k, v in res.items():
                a["res"].setdefault(k, []).extend(v)
            done += 1
            if done % 50 == 0:
                print(f"{done}/{len(jobs)} jobs, {time.time() - t0:.0f}s", flush=True)
    out_path = {"p40": OUT, "quick": OUT.replace(".out.", ".quick."), "life": OUT.replace(".out.", ".life."),
                "extra": OUT.replace(".out.", ".extra."), "life2": OUT.replace(".out.", ".life2."),
                "fix": OUT.replace(".out.", ".fix.")}[phase]
    with open(out_path, "w") as f:
        for (kind, lab, kws, T), a in sorted(acc.items()):
            kw = json.loads(kws)
            row = {"kind": kind, "model": lab, "gen": kw, "R": a["R"], "T": T,
                   "info": {k: float(np.mean([i[k] for i in a["info"]])) for k in a["info"][0]},
                   "cpu_s": round(a["secs"], 1), "g2_calls": a["g2"], "judges": {}}
            for j in [jj.name for jj in JUDGES]:
                row["judges"][j] = {}
                for TT in (40, 120):
                    if TT <= T:
                        p, se = _rate(a["res"][j], TT)
                        row["judges"][j][f"p{TT}"] = round(p, 5); row["judges"][j][f"se{TT}"] = round(se, 5)
                row["judges"][j]["median_T"] = _median(a["res"][j])
                tt = np.asarray(a["res"][j], float)
                tt = tt[~np.isnan(tt)]
                row["judges"][j]["median_if_promoted_40"] = float(np.median(tt[tt <= 40])) if (tt <= 40).any() else None
                row["judges"][j]["q25_40"] = float(np.percentile(tt[tt <= 40], 25)) if (tt <= 40).any() else None
            for k in ("first_WA", "first_WC", "first_R", "retired"):
                row[k] = {f"p{TT}": round(_rate(a["res"][k], TT)[0], 5) for TT in (40, 120) if TT <= T}
            pb = np.asarray(a["res"]["promo_block_design"], float)
            row["earliest_promo_block"] = float(np.nanmin(pb)) if (~np.isnan(pb)).any() else None
            f.write(json.dumps(row) + "\n")
    print(f"wrote {out_path} in {time.time() - t0:.0f}s")
    summarize(out_path)


def summarize(path=OUT):
    rows = [json.loads(l) for l in open(path)]
    lines = []
    w = lines.append
    w(f"EVL-EPROC-1 synthetic calibration ({path}); FP/power = P(promotion at any block within T sessions); SE beside.")
    w("Columns: n = READ events a session (control ~3.33x), rho = day-shock share of event variance.\n")
    for kind in ("null", "stress", "power", "life-null", "life-power", "extra", "extra-power", "fix-null", "fix-power"):
        sub = [r for r in rows if r["kind"] == kind]
        models = []
        for r in sub:
            if r["model"] not in models:
                models.append(r["model"])
        for mlab in models:
            w(f"== {kind}: {mlab}")
            w("   rho    n    R | design@40 (se)   @120 (se)  | noG2@40 noRet@40 | WA@40 WC@40 Ret@40 | med | m0_15@40 m0_20@40 thrA12.5@40 m0_15+12.5@40 m0_20+AC12.5@40")
            for r in sorted([r for r in sub if r["model"] == mlab], key=lambda r: (r["gen"]["rho_day"], -r["gen"]["nbar"])):
                J = r["judges"]
                d = J["design"]
                med = d["median_T"] if d["median_T"] is not None else float("nan")
                w("   %.2f %4d %5d | %.4f (%.4f) %.4f (%.4f) | %.4f  %.4f | %.3f %.3f %.3f | %5.1f | %.4f %.4f %.4f %.4f %.4f" % (
                    r["gen"]["rho_day"], r["gen"]["nbar"], r["R"], d["p40"], d["se40"], d.get("p120", float("nan")),
                    d.get("se120", float("nan")), J["design_noG2"]["p40"], J["design_noRet"]["p40"],
                    r["first_WA"]["p40"], r["first_WC"]["p40"], r["first_R"]["p40"], med,
                    J["m0_15"]["p40"], J["m0_20"]["p40"], J["thrA_12.5"]["p40"], J["m0_15_thrA_12.5"]["p40"],
                    J["m0_20_thrAC_12.5"]["p40"]))
            w("")
    txt = "\n".join(lines)
    print(txt)
    open(path.replace(".jsonl", ".summary.txt").replace(".out.summary", ".summary"), "w").write(txt + "\n")


def analyze(path=OUT, horizon=40):
    """Per judge variant: the worst FP over the core nulls and over the stresses (cell named), and power."""
    rows = [json.loads(l) for l in open(path)]
    key = f"p{horizon}"
    sek = f"se{horizon}"
    lines = [f"WORST-CASE FP within {horizon} sessions per judge variant ({path})"]
    w = lines.append
    for j in [jj.name for jj in JUDGES]:
        out = []
        for kinds in (("null", "life-null"), ("stress", "extra")):
            sub = [r for r in rows if r["kind"] in kinds and key in r["judges"].get(j, {})]
            if not sub:
                continue
            worst = max(sub, key=lambda r: r["judges"][j][key])
            out.append("%s max %.4f (se %.4f) at [%s, n=%d, rho=%.2f]" % (
                "/".join(kinds), worst["judges"][j][key], worst["judges"][j][sek], worst["model"][:44],
                worst["gen"]["nbar"], worst["gen"]["rho_day"]))
        excl = [r for r in rows if r["kind"] in ("null", "stress", "life-null", "extra") and key in r["judges"].get(j, {})
                and "AR30" not in r["model"] and "S8" not in r["model"]]
        if excl:
            worst = max(excl, key=lambda r: r["judges"][j][key])
            out.append("excluding the 30bp-drift cells max %.4f at [%s, n=%d, rho=%.2f]" % (
                worst["judges"][j][key], worst["model"][:44], worst["gen"]["nbar"], worst["gen"]["rho_day"]))
        w(f"  {j:22s} " + " | ".join(out))
    w("")
    w(f"POWER within {horizon} sessions (P promote, se, median session among all reps or None = not reached by T):")
    pw = [r for r in rows if r["kind"] in ("power", "life-power", "extra-power")]
    for j in ("design", "m0_10", "m0_12.5", "m0_15", "m0_17.5", "m0_20", "m0_22.5", "thrA_12.5", "m0_15_thrA_10",
              "m0_15_thrA_12.5", "m0_17.5_thrA_12.5", "m0_20_thrA_12.5", "m0_20_thrAC_12.5"):
        w(f"  -- {j}")
        for r in sorted(pw, key=lambda r: (r["gen"]["skill"], r["gen"]["rho_day"], -r["gen"]["nbar"])):
            d = r["judges"].get(j, {})
            if key not in d:
                continue
            w("     edge %3dbp rho %.2f n %3d: P %.3f (%.3f) median %s, median|promoted<=40 %s" % (
                round(r["gen"]["skill"] * 1e4), r["gen"]["rho_day"], r["gen"]["nbar"], d[key], d[sek],
                d["median_T"], d["median_if_promoted_40"]))
    txt = "\n".join(lines)
    print(txt)
    open(path.replace(".jsonl", f".analysis{horizon}.txt"), "w").write(txt + "\n")


def report():
    """Every phase's cells: the worst FP per judge variant at 40 and at 120 sessions (cell named)."""
    rows = []
    for ph in ("out", "extra", "life", "life2", "fix"):
        path = OUT.replace(".out.", f".{ph}.")
        if os.path.exists(path):
            rows += [dict(json.loads(l), phase=ph) for l in open(path)]
    nulls = [r for r in rows if r["kind"] in ("null", "stress", "extra", "life-null", "fix-null")]
    lines = ["EVL-EPROC-1 calibration record: worst false-promotion rate per judge variant over EVERY null and stress cell",
             "(all looks; FP = P(promotion at any block within the horizon); cell = model | n | rho_day | phase | R)", ""]
    names = [j.name for j in JUDGES]
    for j in names:
        out = []
        for h in (40, 120):
            k = f"p{h}"
            sub = [r for r in nulls if k in r["judges"].get(j, {})]
            if not sub:
                continue
            w = max(sub, key=lambda r: r["judges"][j][k])
            out.append("@%d %.4f se %.4f [%s | n%d | rho %.2f | %s | R %d]" % (
                h, w["judges"][j][k], w["judges"][j][f"se{h}"], w["model"][:40], w["gen"]["nbar"], w["gen"]["rho_day"],
                w["phase"], w["R"]))
        lines.append(f"{j:24s} " + "   ".join(out))
    txt = "\n".join(lines)
    print(txt)
    open(os.path.join(HERE, "calib_evalue.report.txt"), "w").write(txt + "\n")


# ------------------------------------------------------------------------------------------------ selftest
def selftest():
    """The vectorized judge equals eproc_ref (stdlib) on synthetic replicates: log W^A, W^C, R paths, and the
    promotion block with G2's sign-flip stubbed to pass (the stub only isolates the arithmetic)."""
    sys.path.insert(0, REF_DIR)
    import eproc_ref as E
    worst = 0.0
    mism = 0
    checked = 0
    n_pro = n_ret = 0
    for gkw, seed in ((dict(nbar=13, rho_day=0.05, skill=0.008), 11), (dict(nbar=8, rho_day=0.0, skill=0.004), 12),
                      (dict(nbar=30, rho_day=0.15), 13), (dict(nbar=8, rho_day=0.3, skill=0.006, mu_family=-0.006,
                                                                 drift_sd=0.003), 14),
                      (dict(nbar=30, rho_day=0.0, skill=-0.004), 15), (dict(nbar=85, rho_day=0.05, skill=0.003), 16)):
        nrep = 12
        J, info, kept = simulate(Gen(**gkw), nrep, 60, seed, judges=(Judge("design_noG2", use_g2=False),),
                                 keep_events=nrep, trace=True)
        for r in range(nrep):
            blocks, control = [], {}
            for s in kept[r]:
                pe = [e for e in s["events"] if e["sel"]]
                if pe:
                    blocks.append({"day": s["day"], "events": pe})
                    control[s["day"]] = s["events"]
            ref = E.paths(blocks, control=control)
            # my per-session trace at the sessions holding a block
            tr = [(i + 1, J.trace[i]) for i in range(len(J.trace)) if J.trace[i]["has"][r]]
            assert len(tr) == len(ref), (len(tr), len(ref))
            cmeans = {d: math.fsum(e["a"] for e in ev) / len(ev) for d, ev in control.items()}
            crossed = None
            ref_promo = None
            for (t, st), row in zip(tr, ref):
                worst = max(worst, abs(st["lwa"][r] - row["log_promo"]), abs(st["lwc"][r] - row["log_ctrl"]),
                            abs(st["lr"][r] - row["log_retire"]))
                checked += 1
                if crossed is None and row["log_ctrl"] >= math.log(E.THR_PROMO):
                    crossed = row["t"]
                ok, why = E.promotion_guards(blocks, row["t"], control_means=cmeans, signflip=lambda v, s: 0.0,
                                             seed_text="x")
                if ok != bool(st["g13iss"][r]):
                    mism += 1
                if ref_promo is None:
                    band = "learning"
                    mv, at = E.decide(ref[:row["t"]], band, has_control=True, guards_ok=lambda tt: ok,
                                      ctrl_crossed_at=crossed, sized_ctrl_crossed_at=None)
                    if mv == "retired":
                        ref_promo = ("retired", t)
                    elif mv == "probe":
                        ref_promo = ("probe", t)
            mine = J.promo["design_noG2"][r]
            mine_ret = J.retired[r]
            n_pro += ref_promo is not None and ref_promo[0] == "probe"
            n_ret += ref_promo is not None and ref_promo[0] == "retired"
            if ref_promo is None:
                if not np.isnan(mine):
                    mism += 1
            elif ref_promo[0] == "probe":
                if mine != ref_promo[1]:
                    mism += 1
                    print("promo mismatch", r, ref_promo, mine)
            else:
                if not (np.isnan(mine) or mine > ref_promo[1]) or mine_ret != ref_promo[1]:
                    mism += 1
                    print("retire mismatch", r, ref_promo, mine, mine_ret)
    print(f"selftest decisions exercised: promotions {n_pro}, retirements {n_ret}")
    print(f"selftest: {checked} blocks, max |log W difference| vs eproc_ref = {worst:.3e}; guard/decision mismatches = {mism}")
    if worst > 1e-9 or mism:
        raise SystemExit("SELFTEST FAILED")
    # sign-flip p: numpy version vs screen-style direct count on a toy vector (same definition, different vectors)
    rng = np.random.default_rng(5)
    vals = rng.standard_normal(40) * 0.02 + 0.004
    fl = np.where(rng.random((20000, 40)) < 0.5, -1.0, 1.0)
    p = (1 + np.count_nonzero(fl @ vals >= vals.sum() - 40e-12)) / 20001
    from math import erf, sqrt
    z = vals.sum() / math.sqrt((vals ** 2).sum())
    print(f"sign-flip p check: MC p {p:.4f}, normal approx {0.5 * (1 - erf(z / sqrt(2))):.4f}")
    print("selftest OK")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("selftest", "run", "quick", "life", "extra", "life2", "fix", "summarize", "analyze", "report",
                                    "time"))
    ap.add_argument("--horizon", type=int, default=40)
    ap.add_argument("--path", default=OUT)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--chunk", type=int, default=500)
    a = ap.parse_args()
    if a.cmd == "selftest":
        selftest()
    elif a.cmd in ("run", "quick", "life", "extra", "life2", "fix"):
        run(a.workers, phase={"run": "p40", "quick": "quick", "life": "life", "extra": "extra", "life2": "life2",
                              "fix": "fix"}[a.cmd],
            chunk=a.chunk)
    elif a.cmd == "summarize":
        summarize(a.path)
    elif a.cmd == "analyze":
        analyze(a.path, a.horizon)
    elif a.cmd == "report":
        report()
    elif a.cmd == "time":
        for nb in (85, 8):
            t0 = time.time()
            J, info, _ = simulate(Gen(nbar=nb, rho_day=0.05), 500, 40, 1)
            print(nb, f"{time.time() - t0:.1f}s for 500 reps x 40 sessions", info, "g2 calls", J.g2_calls)
