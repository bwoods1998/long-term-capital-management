# PREREG-EVL-8 FINAL-FIX COPY (evl8/final/calib_meta_b8.py) of ./calib_meta_f8.py with ONE added knob, Cell.beta_day
# (re-check 1's major 2, its recheck1/calib_meta_rc.py knob reproduced): each issuer's loading on the residual day shock
# c_t is clip(1 + beta_day x its volatility z-score, 0.2, 2.5), so pools mix high- and low-beta names and sub-rules on
# the volatility tercile (and pairs with it) carry a day-shock tilt that pool-relative scoring does not cancel.
# beta_day = 0 draws exactly as calib_meta_f8.py (meta_life8.py `selftest` checks it). Nothing else is changed.
# PREREG-EVL-8 FINAL COPY (evl8/final/calib_meta_f8.py) of check 1's ../check1/calib_meta_c1.py (itself ../meta/calib_meta.py with
# Cell.fac_sd and Cell.load_all): adds PREREG-EVL-6's frozen-grid day shapes 'crasht3', 'crashcl', 'crasht3cl' (calib_v2.py's:
# crash days at -3 sd with a t(3) body, clustered in high-volatility regimes, or both); for those shapes only the volatility
# state is updated before the day shock (the clustered crash probability reads it); every other shape draws exactly as before.
# THE SIMULATOR'S EVL6 PATH IS THE JUDGE'S; this copy changes nothing else.
#!/usr/bin/env python
"""calib_meta.py: SYNTHETIC calibration of PREREG-EVL-8's META-LEARNERS (lens: meta, workflow gusher).

Nothing here reads the live lane: no events.sqlite, no live.sqlite, no House, no gateway, no market data, no price,
no return, no look, no band. Every number comes from the generator below, chosen blind.

THE META-PROGRAM UNDER TEST ("MRL-EB": the meta rule-learner, empirical-Bayes lower-confidence ranker), per replicate:
  each session t a POOL of n_t candidate events at one auction (the union of the auction's controls: every eligible
  event, one per issuer). A FAMILY of J sub-rules: every single feature f and every pair (f, g) of features from
  different groups (a predicate over pre-decision attributes: family, verdict score thresholds, source, knowable hour,
  coverage, the issuer's liquidity / price / volatility terciles, keyword flags ...). J = 369 (base), 590 (wide), 790
  (wide2). Sub-rule j's block at a SETTLED session s: n_js events, B_js = mean a, RELATIVE block R_js = B_js - P_s (P_s
  the pool's mean a: the day shock and any stream-wide drift cancel), noise V_js = SF^2 + sig2 / n_js.
  STATE (exponential forgetting w = 2^(-age / H)): A_j = sum w / V_js, G_j = sum w R_js / V_js, blocks_j (unforgotten).
  POSTERIOR (normal prior N(0, TAU^2) on the relative edge, Efron and Morris 1975's empirical Bayes):
    mean_j = G_j / (A_j + TAU^-2), sd_j = (A_j + TAU^-2)^-1/2, LCB_j = mean_j - Z sd_j (a sub-rule with < MINB settled
    blocks is asleep: -inf).
  LEVEL (EVL-7's V1, no timing): the pool's predicted after-cost mean is -cbar_t (its gross abnormal mean zero),
    cbar_t = the pool's mean round-trip cost at t (known before the decision: the cost model).
  EVENT SCORE: s_e = max over the AWAKE sub-rules j containing e of LCB_j ('eb'), or of G_j ('hedge': exponential
    weights exp(eta G_j) ranked, i.e. follow the precision-weighted cumulative gain, with the same LCB hurdle);
    PICK: eligible (not picked in the last 5 sessions), -cbar_t + LCB_best(e) > HURDLE, the top K by s_e.
  'rand': K random pool events (a FIXED program at the same rate: the reference); 'fixed': one sub-rule drawn at
  random, its events (top K by a random rank): a fixed birth.
  Settlement LAG = 2 sessions (an overnight program's events settle the night after their exit; the open program's the
  same night, so 2 is the conservative one); the sub-rules' records start at the meta's registration (PRE = 0).
THE RECORD = the meta's picks (one session each); its CONTROL = the pool's mean a of the session.

THE GENERATOR (EVL-6's judge risk set, goal-2026-10-19/evl6/judge/calib_judge.py, re-implemented with attributes):
  3000 issuers, 11 sectors, Zipf(0.8) popularity (the same names recur), one hot sector (x4) on half the sessions,
  sigma_i log-uniform 1%-10%, three style factors (loadings N((.2,-.1,.2), .5^2), optionally correlated with the
  volatility tercile: LOADCORR), persistent issuer effect tau_i ~ N(0, TAU_I), vol regime h_t = exp(x_t - .09).
  a = mu_e + D_t + Dfam_{f,t} + h_t (c_t + s_sector,t + beta_i . f_t + sigma_i e_it) + jump + tau_i, floor -1;
  r = a + b_t, b_t ~ N(4 bp, 1%).  c_t: the residual DAY shock common to the session's events, sd_c z_t,
  z_t = PHI z_{t-1} + sqrt(1-PHI^2) eps_t, eps 't3' or 'crash' (5% of sessions N(-3, 1)); sd_c^2 = rho/(1-rho) V0.
  e_it unit t3 or LEFT-SKEWED (two-piece t3 1.4/0.6, jumps 80% down); jumps +-30% w.p. 0.5%, mean-compensated.
  D_t stream-wide AR(.97) drift (no selection escapes it); Dfam per-family zero-mean AR(.97) drifts (selection CAN
  chase them: a real, persistent edge in that world, reported as the picks' TRUE mean).
  ROUND-TRIP COST c_e: 11 bp (liquid terciles 1-2), 21 bp (thin tercile 0): the replay's allowance.
MEANS mu_e:  N0 every event exactly 0 after cost (the hurdle's worst case: everything breaks even);
  N1 every event -c_e (no edge: the pool loses its cost); N2 THE KNIFE EDGE: the TRUE rules' events exactly 0 after
  cost, every other event -c_e (the meta can learn them perfectly and still earns exactly 0; beats its pool);
  A (power): the true rules' events +EDGE after cost, every other -c_e.  TRUE RULES: 'r1' one pair (score>=2 AND the
  top liquidity tercile); 'r3' that pair, (family=price AND volatility tercile 2) and (source 1 AND hour 0);
  'r1n' one NARROW pair (score=3 AND hour 0).
TRUE MEAN of a pick = mu_e + D_t + Dfam + tau_i (its expectation given the world): a replicate whose picks' true mean
  is <= 0 is a NULL replicate whatever the cell; FP = P(pass AND picks' true mean <= 0) and P(pass | true mean <= 0).

THE SCREENS (goal-2026-10-19/evl7/learner/calib_learner.py screen_one, imported unchanged): EVL3 (PREREG-EVL-3 as
registered minus its skew check: an upper bound), L12 (the EVL-6 judge's leading 10%-cap candidate: looks at
S >= 7 ... 30, p of mean(B - 10 bp) <= 0.01, guards, retirement) and E840 (c/S, c = 0.125, 8..40 blocks).

Usage: calib_meta.py run --grid GRID [--workers 4] [--reps R] [--chunk C] [--out PREFIX] | selftest
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
EVL7 = os.path.abspath(os.path.join(HERE, "..", "..", "evl7", "learner"))
sys.path.insert(0, EVL7)
import calib_learner as CL  # noqa: E402  (the EVL-7 learner's screens, unchanged)

V0 = 0.0027
U = 3000
SECTOR_W = np.array([.22, .14, .12, .11, .09, .08, .07, .06, .04, .04, .03])
FAM_P = np.array([.60, .08, .07, .25])            # news, 8k, ern, price (the auction's pools)
SCORE_LV = np.array([-3, -2, -1, 0, 1, 2, 3, 9])  # 9 = missing verdict
SCORE_P = np.array([.04, .06, .08, .30, .16, .20, .08, .08])
SRC_P = np.array([.5, .3, .2])
HOUR_P = np.array([.25, .25, .25, .25])
COV_P = np.array([.5, .3, .2])
KW_P = (.10, .08, .06, .15)
EXTRA_P = np.array([.4, .35, .25])
WALK = 200                                      # sub-rules walked a decision at most


@dataclasses.dataclass(frozen=True)
class Cell:
    name: str
    mean: str = "N0"          # N0 | N1 | N2 | A
    rules: str = "r1"         # r1 | r3 | r1n (the true rules, N2 and A)
    edge: float = 0.0         # A: the true rules' after-cost mean
    nbar: float = 300.0
    T: int = 120
    rho_day: float = 0.05
    day: str = "t3"
    phi_day: float = 0.10
    ev_skew: bool = False
    drift_sd: float = 0.0
    drift_rho: float = 0.97
    fam_drift_sd: float = 0.0
    tau_i: float = 0.0
    fac_rho: float = 0.0
    load_corr: float = 0.0
    fac_sd: float = 0.006     # CHECK1: the style factors' session sd (the designer fixed 0.006)
    load_all: bool = False    # CHECK1: tie factor 1 to the liquidity tercile and factor 2 to the price tercile too
    width: str = "base"       # base | wide | wide2 (J = 369 | 590 | 790)
    algo: str = "eb"          # eb | hedge | rand | fixed
    K: int = 16
    H: float = 60.0
    tau: float = 0.0030       # prior sd of a sub-rule's relative edge
    sf: float = 0.0020        # block-noise floor of a relative block (sector / style clustering)
    z: float = 3.0
    hurdle: float = 0.0
    minb: int = 3
    lag: int = 2
    warm: int = 10            # no pick before session `warm` (the sub-rules' records grow from session 0)
    switch_at: int = 0        # A: from this session the true rule is (family 3 AND volatility tercile 2) instead
    beta_day: float = 0.0     # FINAL-FIX: the day-shock loading's spread on the volatility z-score

    def sd_day(self) -> float:
        return math.sqrt(self.rho_day / (1.0 - self.rho_day) * V0) if self.rho_day > 0 else 0.0


WORST = dict(rho_day=0.15, day="crash", ev_skew=True, drift_sd=0.0020, tau_i=0.01)


# ------------------------------------------------------------------------------------------------ features
def feature_table(width: str):
    """[(name, group)] and a builder of X from the attribute arrays."""
    feats = []
    for k in range(4):
        feats.append((f"fam{k}", "fam"))
    feats += [("s>=1", "score"), ("s>=2", "score"), ("s=3", "score"), ("s<=-1", "score"), ("s_miss", "score")]
    for k in range(3):
        feats.append((f"src{k}", "src"))
    for k in range(4):
        feats.append((f"hour{k}", "hour"))
    for k in range(3):
        feats.append((f"cov{k}", "cov"))
    for k in range(3):
        feats.append((f"liq{k}", "liq"))
    for k in range(3):
        feats.append((f"px{k}", "px"))
    for k in range(3):
        feats.append((f"vol{k}", "vol"))
    if width in ("wide", "wide2", "wide3", "wide4"):
        for k in range(4):
            feats.append((f"kw{k}", f"kw{k}"))
        for k in range(3):
            feats.append((f"x1_{k}", "x1"))
    if width in ("wide2", "wide3", "wide4"):
        for k in range(3):
            feats.append((f"x2_{k}", "x2"))
        for k in range(3):
            feats.append((f"x3_{k}", "x3"))
    if width in ("wide3", "wide4"):
        for x in ("x4", "x5"):
            for k in range(3):
                feats.append((f"{x}_{k}", x))
    if width == "wide4":
        for x in ("x6", "x7", "x8"):
            for k in range(3):
                feats.append((f"{x}_{k}", x))
    return feats


def pair_valid(feats):
    F = len(feats)
    g = [x[1] for x in feats]
    ok = np.zeros((F, F), bool)
    for i in range(F):
        for j in range(F):
            ok[i, j] = (i == j) or (g[i] != g[j])
    return ok


def build_X(feats, att):
    cols = []
    for name, grp in feats:
        if grp == "fam":
            cols.append(att["fam"] == int(name[3:]))
        elif grp == "score":
            s = att["score"]
            cols.append({"s>=1": (s >= 1) & (s <= 3), "s>=2": (s >= 2) & (s <= 3), "s=3": s == 3,
                         "s<=-1": s <= -1, "s_miss": s == 9}[name])
        elif grp in ("src", "hour", "cov", "liq", "px", "vol"):
            cols.append(att[grp] == int(name[len(grp):]))
        elif grp.startswith("kw"):
            cols.append(att[grp])
        elif grp in ("x1", "x2", "x3", "x4", "x5", "x6", "x7", "x8"):
            cols.append(att[grp] == int(name.split("_")[1]))
    return np.stack(cols, axis=-1)


def true_rule_mask(feats, rules: str) -> list[tuple[int, int]]:
    ix = {n: i for i, (n, _) in enumerate(feats)}
    if rules == "r1":
        return [(ix["s>=2"], ix["liq2"])]
    if rules == "r1n":
        return [(ix["s=3"], ix["hour0"])]
    if rules == "r3":
        return [(ix["s>=2"], ix["liq2"]), (ix["fam3"], ix["vol2"]), (ix["src1"], ix["hour0"])]
    raise ValueError(rules)


# ------------------------------------------------------------------------------------------------ issuers
def issuers(rng, R, cell):
    ranks = np.argsort(rng.random((R, U)), axis=1) + 1
    logp = -0.8 * np.log(ranks.astype(float))
    sector = rng.choice(11, size=(R, U), p=SECTOR_W)
    lsig = rng.uniform(math.log(0.01), math.log(0.10), (R, U))
    sig = np.exp(lsig)
    zs = (lsig - lsig.mean(axis=1, keepdims=True)) / lsig.std(axis=1, keepdims=True)
    beta = rng.normal(0, 0.5, (R, U, 3)) + np.array([0.2, -0.1, 0.2])
    if cell.load_corr:
        beta[..., 0] = 0.2 + 0.5 * (cell.load_corr * zs + math.sqrt(1 - cell.load_corr ** 2) * rng.normal(0, 1, (R, U)))
    tau = rng.normal(0, cell.tau_i, (R, U)) if cell.tau_i > 0 else np.zeros((R, U))
    lnadv = -0.6 * zs + 0.8 * rng.normal(0, 1, (R, U))
    lnpx = -0.4 * zs + 0.9 * rng.normal(0, 1, (R, U))
    if cell.load_all and cell.load_corr:      # CHECK1: size (liquidity) and price style factors as well
        c_ = cell.load_corr
        for f_, x_ in ((1, lnadv), (2, lnpx)):
            zx = (x_ - x_.mean(axis=1, keepdims=True)) / x_.std(axis=1, keepdims=True)
            beta[..., f_] = 0.5 * (c_ * zx + math.sqrt(1 - c_ ** 2) * rng.normal(0, 1, (R, U)))

    def terc(x):
        q = np.quantile(x, [1 / 3, 2 / 3], axis=1)
        return (x > q[0][:, None]).astype(np.int8) + (x > q[1][:, None]).astype(np.int8)

    liq, px, vol = terc(lnadv), terc(lnpx), terc(lsig)
    cost = np.where(liq == 0, 0.0021, 0.0011)
    lb = np.clip(1.0 + cell.beta_day * zs, 0.2, 2.5) if cell.beta_day else np.ones((R, U))
    return dict(logp=logp, sector=sector, sig=sig, beta=beta, tau=tau, liq=liq, px=px, vol=vol, cost=cost, lb=lb)


def unit_t3(rng, size, left=1.0, right=1.0):
    return CL.unit_t3(rng, size, left, right)


NEW_DAYS = ("crasht3", "crashcl", "crasht3cl")


def day_innov_f8(rng, kind, R, x):
    """calib_v2.day_innov2's three shapes on this simulator's volatility state x (stationary sd 0.3): 5% of sessions
    N(-3, 1) (clustered: p_t = 0.05 exp(2 x_t) / E[exp(2 x)], at most 0.09), the rest m + s x a normal or t(3) body,
    m and s set so the day has mean 0 and variance 1."""
    k = 3.0
    p = np.minimum(0.05 * np.exp(2.0 * x) / math.exp(2.0 ** 2 * 0.3 ** 2 / 2.0), 0.09) if kind.endswith("cl") else 0.05
    m = p * k / (1.0 - p)
    s = np.sqrt((1.0 - p * (k * k + 1.0)) / (1.0 - p) - m * m)
    hit = rng.random(R) < p
    crash = rng.normal(-k, 1.0, R)
    body = unit_t3(rng, R) if "t3" in kind else rng.standard_normal(R)
    return np.where(hit, crash, m + s * body)


# ------------------------------------------------------------------------------------------------ simulation
def simulate(cell: Cell, seed: int, R: int) -> dict:
    rng = np.random.default_rng(seed)
    T, K = cell.T, cell.K
    feats = feature_table(cell.width)
    F = len(feats)
    pv = pair_valid(feats)
    IU, JU = np.nonzero(np.triu(pv))
    trule = true_rule_mask(feats, cell.rules) if cell.mean in ("N2", "A") else []
    iss = issuers(rng, R, cell)
    Nmax = int(cell.nbar * 3.2) + 20
    sd_c = cell.sd_day()
    zday = np.zeros(R)
    vx = rng.normal(0, 0.3, R)
    drift = rng.normal(0, cell.drift_sd, R) if cell.drift_sd else np.zeros(R)
    fdrift = rng.normal(0, cell.fam_drift_sd, (R, 4)) if cell.fam_drift_sd else np.zeros((R, 4))
    fac = np.zeros((R, 3))
    # learner state
    A = np.zeros((R, F, F))
    G = np.zeros((R, F, F))
    NB = np.zeros((R, F, F))
    s2_sum = np.zeros(R)
    s2_n = np.zeros(R)
    pend: list = []
    delta = 2.0 ** (-1.0 / cell.H) if math.isfinite(cell.H) else 1.0
    fixed_rule = None
    if cell.algo == "fixed":
        cand = np.argwhere(np.triu(pv))
        fixed_rule = cand[rng.integers(0, len(cand), R)]          # (R, 2): one random sub-rule a replicate
    last = np.full((R, U), -10_000, dtype=np.int64)
    out_B = np.full((R, T), np.nan)
    out_Rm = np.full((R, T), np.nan)
    out_n = np.zeros((R, T), dtype=np.int16)
    out_ctrl = np.full((R, T), np.nan)
    out_iss = np.full((R, T, K), -1, dtype=np.int32)
    out_a = np.full((R, T, K), np.nan)
    out_true = np.full((R, T, K), np.nan)
    out_ntrue = np.zeros((R, T), dtype=np.int16)      # picks inside a true rule
    PADF = F
    eye_pad = None
    for t in range(T):
        # ---- the pool of session t
        n_t = np.minimum(rng.poisson(cell.nbar * rng.gamma(3.0, 1.0 / 3.0, R)), Nmax)
        hot = rng.integers(0, 11, R)
        hotday = rng.random(R) < 0.5
        g = -np.log(-np.log(rng.random((R, U))))
        keys = iss["logp"] + g + np.where((iss["sector"] == hot[:, None]) & hotday[:, None], math.log(4.0), 0.0)
        ids = np.argpartition(-keys, Nmax - 1, axis=1)[:, :Nmax]
        order = np.argsort(-np.take_along_axis(keys, ids, axis=1), axis=1)
        ids = np.take_along_axis(ids, order, axis=1)
        Ncur = max(int(n_t.max()), 1)
        ids = ids[:, :Ncur]                    # (the n_t largest keys of each replicate are its first n_t)
        valid = np.arange(Ncur)[None, :] < n_t[:, None]
        att = dict(fam=rng.choice(4, size=(R, Ncur), p=FAM_P),
                   score=SCORE_LV[rng.choice(8, size=(R, Ncur), p=SCORE_P)],
                   src=rng.choice(3, size=(R, Ncur), p=SRC_P), hour=rng.choice(4, size=(R, Ncur), p=HOUR_P),
                   cov=rng.choice(3, size=(R, Ncur), p=COV_P),
                   liq=np.take_along_axis(iss["liq"], ids, axis=1), px=np.take_along_axis(iss["px"], ids, axis=1),
                   vol=np.take_along_axis(iss["vol"], ids, axis=1))
        for k in range(4):
            att[f"kw{k}"] = rng.random((R, Ncur)) < KW_P[k]
        for x in ("x1", "x2", "x3", "x4", "x5", "x6", "x7", "x8"):
            att[x] = rng.choice(3, size=(R, Ncur), p=EXTRA_P)
        Xb = build_X(feats, att) & valid[..., None]                   # (R, N, F) bool
        X = Xb.astype(np.float64)
        cost = np.take_along_axis(iss["cost"], ids, axis=1)
        intrue = np.zeros((R, Ncur), bool)
        if cell.switch_at and t == cell.switch_at:
            ixs = {nm: i for i, (nm, _) in enumerate(feats)}
            trule = [(ixs["fam3"], ixs["vol2"])]
        for (f1, f2) in trule:
            intrue |= Xb[..., f1] & Xb[..., f2]
        if cell.mean == "N0":
            mu = np.zeros((R, Ncur))
        elif cell.mean == "N1":
            mu = -cost
        elif cell.mean == "N2":
            mu = np.where(intrue, 0.0, -cost)
        else:
            mu = np.where(intrue, cell.edge, -cost)
        sig = np.take_along_axis(iss["sig"], ids, axis=1)
        sec = np.take_along_axis(iss["sector"], ids, axis=1)
        beta = np.take_along_axis(iss["beta"], ids[..., None], axis=1)
        tau = np.take_along_axis(iss["tau"], ids, axis=1)
        # ---- day-level shocks
        if cell.day in NEW_DAYS:                                        # F8 FINAL: the frozen grid's day shapes
            vx = 0.9 * vx + math.sqrt(1 - 0.81) * rng.normal(0, 0.3, R)
            zday = cell.phi_day * zday + math.sqrt(1 - cell.phi_day ** 2) * day_innov_f8(rng, cell.day, R, vx)
        else:
            zday = cell.phi_day * zday + math.sqrt(1 - cell.phi_day ** 2) * CL.day_innov(rng, cell.day, R)
            vx = 0.9 * vx + math.sqrt(1 - 0.81) * rng.normal(0, 0.3, R)
        c_t = sd_c * zday
        h_t = np.exp(vx - 0.09)
        s_sec = unit_t3(rng, (R, 11)) * 0.010
        if cell.fac_rho:
            fac = cell.fac_rho * fac + math.sqrt(1 - cell.fac_rho ** 2) * unit_t3(rng, (R, 3)) * cell.fac_sd
        else:
            fac = unit_t3(rng, (R, 3)) * cell.fac_sd
        if cell.drift_sd:
            drift = cell.drift_rho * drift + math.sqrt(1 - cell.drift_rho ** 2) * rng.normal(0, cell.drift_sd, R)
        if cell.fam_drift_sd:
            fdrift = cell.drift_rho * fdrift + math.sqrt(1 - cell.drift_rho ** 2) * rng.normal(0, cell.fam_drift_sd, (R, 4))
        b_t = rng.normal(0.0004, 0.010, R)
        e = unit_t3(rng, (R, Ncur), 1.4, 0.6) if cell.ev_skew else unit_t3(rng, (R, Ncur))
        jl = 0.8 if cell.ev_skew else 0.5
        jump = np.where(rng.random((R, Ncur)) < 0.005, np.where(rng.random((R, Ncur)) < jl, -0.30, 0.30), 0.0)
        jump = jump - 0.005 * 0.30 * (1 - 2 * jl)
        fd = np.take_along_axis(fdrift, att["fam"], axis=1)
        lbe = np.take_along_axis(iss["lb"], ids, axis=1)
        noise = h_t[:, None] * (lbe * c_t[:, None] + np.take_along_axis(s_sec, sec, axis=1)
                                + np.einsum("rnk,rk->rn", beta, fac) + sig * e)
        truth = mu + drift[:, None] + fd + tau
        a = np.maximum(truth + noise + jump, -1.0)
        r = a + b_t[:, None]
        vf = valid.astype(float)
        nv = np.maximum(vf.sum(axis=1), 1)
        cbar = (cost * vf).sum(axis=1) / nv
        # ---- settled sessions enter the state
        while pend and pend[0][0] <= t - cell.lag:
            _, dA, dG, dN, s2 = pend.pop(0)
            A = delta * A + dA
            G = delta * G + dG
            NB = NB + dN
            s2_sum += s2
            s2_n += 1
        # ---- the decision of session t
        elig = valid & (np.take_along_axis(last, ids, axis=1) < t - 5)
        if cell.algo in ("eb", "hedge"):
            # THE RULE WALK (exactly the House's algorithm): the awake sub-rules in rank order; each in turn gives
            # its eligible events not yet taken (in the event order: here a random one) until K are taken; EB stops at
            # the first sub-rule whose predicted after-cost mean (-cbar + LCB) fails the hurdle, HEDGE (ranked by the
            # cumulative precision-weighted gain G) skips such a sub-rule.
            prec = A[:, IU, JU] + 1.0 / cell.tau ** 2                       # (R, J)
            mean_j = G[:, IU, JU] / prec
            lcb = mean_j - cell.z / np.sqrt(prec)
            awake = NB[:, IU, JU] >= cell.minb
            passj = awake & ((-cbar[:, None] + lcb) > cell.hurdle)
            key = lcb if cell.algo == "eb" else G[:, IU, JU]
            key = np.where(passj, key, -np.inf)
            nwalk = min(WALK, key.shape[1])
            rord = np.argsort(-key, axis=1)[:, :nwalk]                    # (R, nwalk)
            rkey = np.take_along_axis(key, rord, axis=1)
            prio = rng.random((R, Ncur))                                  # the within-rule event order
            score = np.full((R, Ncur), -np.inf)
            taken = np.zeros((R, Ncur), bool)
            cnt = np.zeros(R, np.int64)
            ar = np.arange(R)
            for k in range(nwalk):
                live = np.isfinite(rkey[:, k]) & (cnt < K)
                if not live.any():
                    break
                f1 = IU[rord[:, k]]
                f2 = JU[rord[:, k]]
                mem = Xb[ar, :, f1] & Xb[ar, :, f2] & elig & ~taken & live[:, None]
                if not mem.any():
                    continue
                need = (K - cnt)
                # take the `need` members with the highest prio
                pm = np.where(mem, prio, -1.0)
                order_ = np.argsort(-pm, axis=1)
                rank_ = np.empty_like(order_)
                np.put_along_axis(rank_, order_, np.arange(Ncur)[None, :].repeat(R, 0), axis=1)
                take = mem & (rank_ < need[:, None])
                taken |= take
                score = np.where(take, rkey[:, k][:, None] * 1.0 + 1e-9 * prio, score)
                cnt += take.sum(axis=1)
            ready = np.full(R, t >= cell.warm)
        elif cell.algo == "rand":
            score = np.where(elig, rng.random((R, Ncur)), -np.inf)
            ready = np.ones(R, bool)
        elif cell.algo == "truth":
            # the BEST FIXED PROGRAM: the true rules' own events from session 0 (no learning; K a session)
            score = np.where(elig & intrue, rng.random((R, Ncur)), -np.inf)
            ready = np.ones(R, bool)
        else:   # fixed: one sub-rule's events
            f1, f2 = fixed_rule[:, 0], fixed_rule[:, 1]
            inr = np.take_along_axis(Xb, f1[:, None, None].repeat(Ncur, 1), axis=2)[..., 0] & \
                np.take_along_axis(Xb, f2[:, None, None].repeat(Ncur, 1), axis=2)[..., 0]
            score = np.where(elig & inr, rng.random((R, Ncur)), -np.inf)
            ready = np.ones(R, bool)
        top = np.argsort(-score, axis=1)[:, :K]
        ok = np.take_along_axis(score, top, axis=1) > -np.inf
        ok &= ready[:, None]
        pa = np.where(ok, np.take_along_axis(a, top, axis=1), np.nan)
        pr = np.where(ok, np.take_along_axis(r, top, axis=1), np.nan)
        pid = np.where(ok, np.take_along_axis(ids, top, axis=1), -1)
        ptr = np.where(ok, np.take_along_axis(truth, top, axis=1), np.nan)
        pin = np.where(ok, np.take_along_axis(intrue, top, axis=1), False)
        npk = ok.sum(axis=1)
        has = npk > 0
        # left-pack (argsort of -score already puts finite first)
        with np.errstate(invalid="ignore"):
            out_B[has, t] = np.nanmean(pa[has], axis=1)
            out_Rm[has, t] = np.nanmean(pr[has], axis=1)
        out_n[:, t] = npk
        out_ctrl[:, t] = (a * vf).sum(axis=1) / nv
        out_iss[:, t, :] = pid
        out_a[:, t, :] = pa
        out_true[:, t, :] = ptr
        out_ntrue[:, t] = pin.sum(axis=1)
        rr, kk = np.nonzero(ok)
        last[rr, pid[rr, kk]] = t
        # ---- this session's sub-rule statistics (settle after `lag` sessions)
        if cell.algo in ("eb", "hedge"):
            P_s = (a * vf).sum(axis=1) / nv
            n = np.matmul(X.transpose(0, 2, 1), X)                       # (R, F, F) counts (pairs; diag singles)
            Sa = np.matmul(X.transpose(0, 2, 1), X * a[..., None])
            dev = np.clip(a - P_s[:, None], -0.10, 0.10) * vf
            s2_now = (dev ** 2).sum(axis=1) / np.maximum(nv - 1, 1)
            s2_est = np.maximum(np.where(s2_n > 0, (s2_sum + s2_now) / (s2_n + 1), s2_now), 0.015 ** 2)
            has_n = n > 0
            with np.errstate(invalid="ignore", divide="ignore"):
                Rel = np.where(has_n, Sa / np.maximum(n, 1) - P_s[:, None, None], 0.0)
                V = cell.sf ** 2 + s2_est[:, None, None] / np.maximum(n, 1)
            dA = np.where(has_n, 1.0 / V, 0.0)
            dG = np.where(has_n, Rel / V, 0.0)
            pend.append((t, dA, dG, has_n.astype(float), s2_now))
    return dict(B=out_B, Rm=out_Rm, n=out_n, ctrl=out_ctrl, iss=out_iss, a=out_a, true=out_true, ntrue=out_ntrue)


# ------------------------------------------------------------------------------------------------ summary
RULES = ("EVL3", "L12", "E840")


def reduce_sim(cell: Cell, sim: dict) -> dict:
    """Per-replicate screen results and the aggregates (in the worker: the screens run in parallel)."""
    R = sim["B"].shape[0]
    with np.errstate(invalid="ignore"):
        tm = np.nanmean(sim["true"].reshape(R, -1), axis=1) if np.isfinite(sim["true"]).any() else np.zeros(R)
    tm = np.where(np.isnan(tm), 0.0, tm)
    out = {"tm": tm}
    for rule in RULES:
        res = [CL.screen_one(sim, i, rule) for i in range(R)]
        out[rule] = np.array([[x[0], x[1], x[2]] for x in res], dtype=np.int64)
    n = sim["n"].astype(np.int64)
    out["n"] = n
    out["ntrue"] = sim["ntrue"].astype(np.int64)
    a = sim["a"]
    tr = sim["true"]
    out["sum_a"] = float(np.nansum(a))
    out["sum_true"] = float(np.nansum(tr))
    out["sum_ctrl"] = float(np.nansum(sim["ctrl"]))
    out["n_ctrl"] = int(np.isfinite(sim["ctrl"]).sum())
    T = cell.T
    out["seg_true"] = np.array([np.nansum(tr[:, lo:lo + 10, :]) for lo in range(0, T, 10)])
    return out


def summarise(cell: Cell, parts: list) -> dict:
    tm = np.concatenate([p["tm"] for p in parts])
    R = tm.size
    null_rep = tm <= 0.0
    out = {"cell": dataclasses.asdict(cell), "R": int(R), "null_share": float(null_rep.mean())}
    for rule in RULES:
        res = np.concatenate([p[rule] for p in parts], axis=0)
        passed = res[:, 0].astype(bool)
        when = res[:, 1]
        ret = res[:, 2].astype(bool)
        d = {"pass": float(passed.mean()), "retired": float(ret.mean()),
             "pass_and_null": float((passed & null_rep).mean()),
             "pass_given_null": float((passed & null_rep).sum() / max(null_rep.sum(), 1))}
        for h in (20, 40, 60, 120, 300):
            if h <= cell.T:
                d[f"by{h}"] = float((passed & (when < h)).mean())
        if passed.any():
            d["median_pass_session"] = float(np.median(when[passed]) + 1)
            d["true_mean_bp_of_passers"] = float(np.mean(tm[passed]) * 1e4)
        out[rule] = d
    n = np.concatenate([p["n"] for p in parts], axis=0)
    ntrue = np.concatenate([p["ntrue"] for p in parts], axis=0)
    npk = int(n.sum())
    out["events_per_session"] = float(n.mean())
    out["sessions_with_picks"] = float((n > 0).mean())
    out["mean_a_picks_bp"] = (sum(p["sum_a"] for p in parts) / npk * 1e4) if npk else None
    out["true_mean_picks_bp"] = (sum(p["sum_true"] for p in parts) / npk * 1e4) if npk else None
    out["mean_ctrl_bp"] = sum(p["sum_ctrl"] for p in parts) / max(sum(p["n_ctrl"] for p in parts), 1) * 1e4
    out["share_in_true_rules"] = float(ntrue.sum() / npk) if npk else None
    seg = np.sum([p["seg_true"] for p in parts], axis=0)
    curve = {}
    for i, lo in enumerate(range(0, cell.T, 10)):
        nn = n[:, lo:lo + 10]
        k = int(nn.sum())
        curve[f"{lo + 1}-{lo + 10}"] = {"true_bp": round(float(seg[i] / k * 1e4), 2) if k else None,
                                        "ev": round(float(nn.mean()), 2),
                                        "in_true": round(float(ntrue[:, lo:lo + 10].sum() / k), 3) if k else None}
    out["curve"] = curve
    return out


# ------------------------------------------------------------------------------------------------ grids
def grid(name: str) -> list[Cell]:
    cells: list[Cell] = []
    if name == "smoke":
        cells.append(Cell("smoke-N0", T=30, nbar=200))
        cells.append(Cell("smoke-A", mean="A", edge=0.004, T=30, nbar=200))
    elif name == "null":
        for nb in (300, 800):
            cells.append(Cell(f"N0-base-n{nb}", nbar=nb))
            cells.append(Cell(f"N0-worst-n{nb}", nbar=nb, **WORST))
            cells.append(Cell(f"N1-worst-n{nb}", mean="N1", nbar=nb, **WORST))
            cells.append(Cell(f"N2r1-worst-n{nb}", mean="N2", rules="r1", nbar=nb, **WORST))
            cells.append(Cell(f"N2r3-worst-n{nb}", mean="N2", rules="r3", nbar=nb, **WORST))
        cells.append(Cell("N0-worst-n300-rand", nbar=300, algo="rand", **WORST))
        cells.append(Cell("N0-worst-n300-fixed", nbar=300, algo="fixed", **WORST))
        cells.append(Cell("N0-base-n300-rand", nbar=300, algo="rand"))
    elif name == "nullJ":
        for w in ("wide", "wide2"):
            cells.append(Cell(f"N0-worst-n300-{w}", nbar=300, width=w, **WORST))
            cells.append(Cell(f"N2r3-worst-n300-{w}", mean="N2", rules="r3", nbar=300, width=w, **WORST))
        cells.append(Cell("N0-worst-n300-hedge", nbar=300, algo="hedge", **WORST))
        cells.append(Cell("N2r3-worst-n300-hedge", mean="N2", rules="r3", nbar=300, algo="hedge", **WORST))
        cells.append(Cell("N0-worst-n300-z0", nbar=300, z=0.0, **WORST))
        cells.append(Cell("N0-worst-n300-K32", nbar=300, K=32, **WORST))
        cells.append(Cell("N0-worst-n300-K8", nbar=300, K=8, **WORST))
        cells.append(Cell("N0-worst-n300-H20", nbar=300, H=20.0, **WORST))
    elif name == "stress":
        cells.append(Cell("N0-worst-notau-n300", nbar=300, **(WORST | dict(tau_i=0.0))))
        cells.append(Cell("N0-rho30-n300", nbar=300, **(WORST | dict(rho_day=0.30))))
        cells.append(Cell("N0-famdrift20-n300", nbar=300, fam_drift_sd=0.0020, **WORST))
        cells.append(Cell("N0-tau3-n300", nbar=300, **(WORST | dict(tau_i=0.03))))
        cells.append(Cell("N0-loadcorr-fac25-n300", nbar=300, load_corr=0.7, fac_rho=0.25, **WORST))
        cells.append(Cell("N0-mom40-n300", nbar=300, **(WORST | dict(rho_day=0.30, phi_day=0.40))))
        cells.append(Cell("N0-drift30-n300", nbar=300, **(WORST | dict(drift_sd=0.0030))))
        cells.append(Cell("N2r1n-worst-n300", mean="N2", rules="r1n", nbar=300, **WORST))
        cells.append(Cell("N0-worst-n300-lag1", nbar=300, lag=1, **WORST))
        cells.append(Cell("N0-worst-n300-T300", nbar=300, T=300, **WORST))
    elif name == "tune":
        base = dict(mean="A", rules="r1", nbar=300)
        for edge in (0.0040,):
            for (z, tau, sf, H) in ((1.0, 0.003, 0.002, 60.0), (0.0, 0.003, 0.002, 60.0), (2.0, 0.003, 0.002, 60.0),
                                    (1.0, 0.006, 0.002, 60.0), (1.0, 0.003, 0.004, 60.0), (1.0, 0.003, 0.001, 60.0),
                                    (1.0, 0.003, 0.002, float("inf")), (1.0, 0.003, 0.002, 20.0)):
                cells.append(Cell(f"T-e{int(edge*1e4)}-z{z}-tau{tau}-sf{sf}-H{H}", edge=edge, z=z, tau=tau, sf=sf, H=H,
                                  **base))
        cells.append(Cell("T-N0-z1", nbar=300))
        cells.append(Cell("T-N0-z0", nbar=300, z=0.0))
        cells.append(Cell("T-N0-z2", nbar=300, z=2.0))
    elif name == "tune2":
        for edge, rules in ((0.0040, "r1"), (0.0060, "r1"), (0.0040, "r3")):
            base = dict(mean="A", rules=rules, nbar=300, edge=edge)
            for (z, warm, K, H) in ((2.0, 0, 16, 60.0), (2.0, 15, 16, 60.0), (2.0, 25, 16, 60.0), (3.0, 0, 16, 60.0),
                                    (3.0, 15, 16, 60.0), (2.0, 15, 24, 60.0), (2.0, 15, 16, 120.0)):
                cells.append(Cell(f"T2-{rules}-e{int(edge*1e4)}-z{z}-w{warm}-K{K}-H{H}", z=z, warm=warm, K=K, H=H, **base))
        for (z, warm, K, H) in ((2.0, 15, 16, 60.0), (3.0, 15, 16, 60.0), (2.0, 15, 24, 60.0)):
            cells.append(Cell(f"T2-N0-worst-z{z}-w{warm}-K{K}", nbar=300, z=z, warm=warm, K=K, H=H, **WORST))
            cells.append(Cell(f"T2-N2r3-worst-z{z}-w{warm}-K{K}", mean="N2", rules="r3", nbar=300, z=z, warm=warm, K=K,
                              H=H, **WORST))
    elif name == "tune3":
        for (z, K, warm) in ((3.0, 16, 10), (3.0, 24, 10), (4.0, 16, 10), (2.5, 16, 10)):
            tag = f"z{z}-K{K}-w{warm}"
            hp = dict(z=z, K=K, warm=warm)
            cells.append(Cell(f"T3-r1-e40-{tag}", mean="A", rules="r1", edge=0.004, nbar=300, **hp))
            cells.append(Cell(f"T3-r3-e30-{tag}", mean="A", rules="r3", edge=0.003, nbar=300, **hp))
            cells.append(Cell(f"T3-r1-e60-{tag}", mean="A", rules="r1", edge=0.006, nbar=300, **hp))
            cells.append(Cell(f"T3-N0-base-{tag}", nbar=300, **hp))
            cells.append(Cell(f"T3-N0-worstnotau-{tag}", nbar=300, **(WORST | dict(tau_i=0.0)), **hp))
    elif name == "fnull":
        NT = WORST | dict(tau_i=0.0)
        for nb in (300, 800):
            cells.append(Cell(f"F-N0-base-n{nb}", nbar=nb))
            cells.append(Cell(f"F-N0-worst-n{nb}", nbar=nb, **WORST))
            cells.append(Cell(f"F-N0-worstnotau-n{nb}", nbar=nb, **NT))
        cells.append(Cell("F-N1-worst-n300", mean="N1", nbar=300, **WORST))
        cells.append(Cell("F-N2r1-worst-n300", mean="N2", rules="r1", nbar=300, **WORST))
        cells.append(Cell("F-N2r3-worst-n300", mean="N2", rules="r3", nbar=300, **WORST))
        cells.append(Cell("F-N2r3-worstnotau-n300", mean="N2", rules="r3", nbar=300, **NT))
        cells.append(Cell("F-N0-worstnotau-n300-wide2", nbar=300, width="wide2", **NT))
        cells.append(Cell("F-N0-worstnotau-n300-wide3", nbar=300, width="wide3", **NT))
        cells.append(Cell("F-N0-worst-n300-wide3", nbar=300, width="wide3", **WORST))
        cells.append(Cell("F-N0-worst-n300-rand", nbar=300, algo="rand", **WORST))
        cells.append(Cell("F-N0-worstnotau-n300-rand", nbar=300, algo="rand", **NT))
    elif name == "fstress":
        NT = WORST | dict(tau_i=0.0)
        cells.append(Cell("S-N0-rho30-n300", nbar=300, **(NT | dict(rho_day=0.30))))
        cells.append(Cell("S-N0-famdrift20-n300", nbar=300, fam_drift_sd=0.0020, **NT))
        cells.append(Cell("S-N0-tau3-n300", nbar=300, **(WORST | dict(tau_i=0.03))))
        cells.append(Cell("S-N0-loadcorr-fac25-n300", nbar=300, load_corr=0.7, fac_rho=0.25, **NT))
        cells.append(Cell("S-N0-mom40-rho30-n300", nbar=300, **(NT | dict(rho_day=0.30, phi_day=0.40))))
        cells.append(Cell("S-N0-drift30ar99-n300", nbar=300, **(NT | dict(drift_sd=0.0030, drift_rho=0.99))))
        cells.append(Cell("S-N2r1n-worstnotau-n300", mean="N2", rules="r1n", nbar=300, **NT))
        cells.append(Cell("S-N0-worstnotau-n300-lag1", nbar=300, lag=1, **NT))
        cells.append(Cell("S-N0-worstnotau-n300-T300", nbar=300, T=300, **NT))
        cells.append(Cell("S-N0-worstnotau-n300-hedge", nbar=300, algo="hedge", **NT))
        cells.append(Cell("S-N0-worstnotau-n300-z2", nbar=300, z=2.0, **NT))
        cells.append(Cell("S-N0-worstnotau-n300-K24", nbar=300, K=24, **NT))
        cells.append(Cell("S-N0-worstnotau-n100", nbar=100, **NT))
        cells.append(Cell("S-N2r3-worstnotau-n800-wide3", mean="N2", rules="r3", nbar=800, width="wide3", **NT))
    elif name == "fgrow":
        NT = WORST | dict(tau_i=0.0)
        cells.append(Cell("G-N0-worstnotau-n300-wide4", nbar=300, width="wide4", **NT))
        cells.append(Cell("G-N2r3-worstnotau-n300-wide4", mean="N2", rules="r3", nbar=300, width="wide4", **NT))
        cells.append(Cell("G-N0-worst-n300-wide4", nbar=300, width="wide4", **WORST))
        cells.append(Cell("G-r1-e60-base-n300-wide4", mean="A", rules="r1", edge=0.006, nbar=300, width="wide4"))
    elif name == "fref":
        for edge in (0.0040, 0.0060):
            e = int(edge * 1e4)
            cells.append(Cell(f"R-truthK16-r1-e{e}-base-n300", mean="A", rules="r1", edge=edge, nbar=300, algo="truth"))
            cells.append(Cell(f"R-truthK64-r1-e{e}-base-n300", mean="A", rules="r1", edge=edge, nbar=300, algo="truth",
                              K=64))
            cells.append(Cell(f"R-truthK16-r3-e{e}-base-n300", mean="A", rules="r3", edge=edge, nbar=300, algo="truth"))
    elif name == "fpower":
        for edge in (0.0020, 0.0030, 0.0040, 0.0060):
            e = int(edge * 1e4)
            cells.append(Cell(f"P-r1-e{e}-base-n300", mean="A", rules="r1", edge=edge, nbar=300))
            cells.append(Cell(f"P-r1-e{e}-base-n800", mean="A", rules="r1", edge=edge, nbar=800))
            cells.append(Cell(f"P-r3-e{e}-base-n300", mean="A", rules="r3", edge=edge, nbar=300))
        for edge in (0.0040, 0.0060):
            e = int(edge * 1e4)
            cells.append(Cell(f"P-r3-e{e}-worst-n300", mean="A", rules="r3", edge=edge, nbar=300, **WORST))
            cells.append(Cell(f"P-r1-e{e}-rho0-n300", mean="A", rules="r1", edge=edge, nbar=300, rho_day=0.0))
            cells.append(Cell(f"P-r1n-e{e}-base-n300", mean="A", rules="r1n", edge=edge, nbar=300))
            cells.append(Cell(f"P-r1-e{e}-base-n300-rand", mean="A", rules="r1", edge=edge, nbar=300, algo="rand"))
            cells.append(Cell(f"P-r1-e{e}-base-n300-wide3", mean="A", rules="r1", edge=edge, nbar=300, width="wide3"))
        cells.append(Cell("P-r1-e60-switch60-base-n300", mean="A", rules="r1", edge=0.006, nbar=300, switch_at=60))
        cells.append(Cell("P-r1-e100-base-n300", mean="A", rules="r1", edge=0.010, nbar=300))
        cells.append(Cell("P-r1-e60-base-n300-T300", mean="A", rules="r1", edge=0.006, nbar=300, T=300))
        cells.append(Cell("P-r1-e40-base-n300-T300", mean="A", rules="r1", edge=0.004, nbar=300, T=300))
    elif name == "power":
        for edge in (0.0020, 0.0030, 0.0040, 0.0060):
            for nb in (300, 800):
                cells.append(Cell(f"A-r1-e{int(edge*1e4)}-base-n{nb}", mean="A", rules="r1", edge=edge, nbar=nb))
            cells.append(Cell(f"A-r3-e{int(edge*1e4)}-base-n300", mean="A", rules="r3", edge=edge, nbar=300))
            cells.append(Cell(f"A-r3-e{int(edge*1e4)}-worst-n300", mean="A", rules="r3", edge=edge, nbar=300, **WORST))
        for edge in (0.0030, 0.0060):
            cells.append(Cell(f"A-r1-e{int(edge*1e4)}-base-n300-rand", mean="A", rules="r1", edge=edge, nbar=300,
                              algo="rand"))
            cells.append(Cell(f"A-r1-e{int(edge*1e4)}-base-n300-K32", mean="A", rules="r1", edge=edge, nbar=300, K=32))
            cells.append(Cell(f"A-r1-e{int(edge*1e4)}-base-n300-hedge", mean="A", rules="r1", edge=edge, nbar=300,
                              algo="hedge"))
            cells.append(Cell(f"A-r1n-e{int(edge*1e4)}-base-n300", mean="A", rules="r1n", edge=edge, nbar=300))
            cells.append(Cell(f"A-r1-e{int(edge*1e4)}-rho0-n300", mean="A", rules="r1", edge=edge, nbar=300,
                              rho_day=0.0))
    return cells


def _job(args):
    cell, seed, R = args
    t0 = time.time()
    sim = simulate(cell, seed, R)
    return cell, reduce_sim(cell, sim), time.time() - t0


def run(gridname: str, reps: int, chunk: int, workers: int, out: str, seed0: int, only: str | None = None):
    from multiprocessing import Pool
    cells = grid(gridname)
    if only:
        cells = [c for c in cells if only in c.name]
    jobs = []
    for ci, cell in enumerate(cells):
        for j in range(max(1, reps // chunk)):
            jobs.append((cell, seed0 + 1000 * ci + j, chunk))
    t0 = time.time()
    parts: dict = {}
    with Pool(workers) as pool, open(out + ".jsonl", "w") as fh:
        done_cells = set()
        need = {c.name: max(1, reps // chunk) for c in cells}
        for k, (cell, sim, dt_) in enumerate(pool.imap_unordered(_job, jobs)):
            parts.setdefault(cell.name, []).append(sim)
            if (k + 1) % 5 == 0 or k + 1 == len(jobs):
                print(f"{gridname}: {k + 1}/{len(jobs)} jobs, {time.time() - t0:.0f}s (last {dt_:.0f}s)", flush=True)
            if len(parts[cell.name]) == need[cell.name] and cell.name not in done_cells:
                done_cells.add(cell.name)
                s = summarise(cell, parts.pop(cell.name))
                fh.write(json.dumps(s) + "\n")
                fh.flush()
                print(json.dumps({"cell": cell.name, **{r: {kk: (round(v, 4) if isinstance(v, float) else v)
                                                          for kk, v in s[r].items()} for r in RULES},
                                  "ev": round(s["events_per_session"], 2), "with": round(s["sessions_with_picks"], 3),
                                  "true_bp": s["true_mean_picks_bp"], "null_share": s["null_share"],
                                  "in_true": s["share_in_true_rules"]}), flush=True)


def selftest():
    c = Cell("st", T=12, nbar=100)
    sim = simulate(c, 3, 4)
    print("selftest: shapes", {k: v.shape for k, v in sim.items()})
    feats = feature_table("base")
    pv = pair_valid(feats)
    J = int(np.triu(pv).sum())
    print("selftest: F", len(feats), "J (singles + pairs)", J)
    for w in ("wide", "wide2"):
        fw = feature_table(w)
        print("selftest:", w, "F", len(fw), "J", int(np.triu(pair_valid(fw)).sum()))
    s = summarise(c, [reduce_sim(c, sim)])
    print("selftest: ev", s["events_per_session"], "ok")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("run", "selftest"))
    ap.add_argument("--grid", default="smoke")
    ap.add_argument("--reps", type=int, default=2000)
    ap.add_argument("--chunk", type=int, default=100)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--seed", type=int, default=88_000_001)
    ap.add_argument("--only", default=None)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    if a.cmd == "selftest":
        selftest()
    else:
        run(a.grid, a.reps, a.chunk, a.workers, a.out or os.path.join(HERE, f"calib_meta.{a.grid}"), a.seed, a.only)
