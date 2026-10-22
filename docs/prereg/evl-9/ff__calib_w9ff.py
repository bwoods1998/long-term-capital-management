#!/usr/bin/env python
"""calib_w9ff.py: PREREG-EVL-9's calibration for the FINAL MINIMAL FIX (the two re-checks' blockers). SYNTHETIC ONLY.

Nothing here reads the lane: no House, gateway, events.sqlite, live.sqlite, vault, run record, price, return, look or
band. It imports the fix round's calibration `evl9/final/calib_w9.py` UNCHANGED (its sha256 is printed by `selftest`
and recorded in SHA256SUMS.ff) and changes, by wrapping (never editing), exactly what the re-checks' fixes change:

  NOLEV  (re-check 1's blocker 2; PREREG-EVL-7's newest text, sha256 2f2cff59..., section 1.4 items 10-11): the learner's
         columns ln(adv20 / 1e7) and ln(prev_close / 20) (the lens's columns 28 and 29, the same index in this file's
         x) are DELETED: set to 0 in every session the learner sees, the population covariance and the prior included,
         after the truth is computed. A zero column decouples from the ridge (its row and column of A and its entry of b
         are 0, section 7.2's d_j rule zeroes it), so this is the same fit as removing it. D = 54 (EVL-WL-O1) and 56
         (EVL-WL-ON). The truth, the costs, the tiebreak and the benchmark split still read adv20.
  SP20   (re-check 1's blocker 1, fix (c)): section 2.3 (ii)'s issuer spacing is 20 sessions: an issuer is eligible to
         be picked at D only when the learner picked it in none of the 20 sessions before D (calib_w9.simulate's
         `last < t - 5` rewritten to `last < t - SPACING`, SPACING 20; the rest of simulate is unchanged). In a
         forward simulation the "20 after D" half of the rule never binds (sessions are decided in order).
  TAUS   (re-check 1's minor 5): history carried the issuers' OWN persistent effects through the static columns that
         stay (ln sig20 and the SIC groups; the two levels are deleted) and through g: re-check 1's rc9_taus.py
         construction, copied here (tau_h = rho_tau x tau_live + sqrt(1 - rho_tau^2) x independent; the prior's
         static-column slopes the in-sample projection of tau_h / sig_hat; g a static per-issuer score of correlation
         A_G = 0.13 with tau_h / sig_hat). rho_tau 0.5 is in the binding set, rho_tau 1 a named stress.
  LVSTY  (re-check 1's stress, rc9_stress.py): the low-volatility prior with an own-direction style drift.

THE BINDING SET (re-check 1's fix (a)): every history (H0, HD05, HD08, CHAR10, TAUH, ADV leak / rand / lowvol, N2 at ic
0.05 and 0.08, TAUS at rho_tau 0.5; H0 and ADV lowvol also without issuer effects) at pools 300, 600 and 800 (EVL-WL-ON)
and 300, 450 and 600 (EVL-WL-O1), at the frozen grid's worst corner (t(3)-body crash days clustered in high
volatility, left-skewed events, rho_day 0.15, phi_day 0.20, a 20 bp drift AR 0.97, 1% issuer effects), and the H0 day
law varied (crash days not clustered, no drift, 10 bp drift, counts that follow the day) at the middle pool.
THE PROTOCOL (select_w9ff.py): search 200 programs a cell; EVERY warm cell within 0.05 of the warm search maximum (no cap)
re-run on fresh seeds at 1,000 programs; every one of those within 0.03 of the round-1 maximum gets 1,000 more (2,000);
W9 = the maximum fresh rate.
Seeds (never used by any earlier EVL-6 to -11 stage: a grep of goal-2026-10-19 for 8xx/9xx million bases finds none):
861e6 + search, 862e6 + fresh round 1, 863e6 + fresh round 2, 864e6 + power, 865e6 + life, 866e6 + stresses,
867e6 + cold references (fresh).
Usage: calib_w9ff.py run --grid NAME [--workers 8] [--resume] | report --grid NAME | selftest
"""
from __future__ import annotations

import os

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import argparse  # noqa: E402
import dataclasses  # noqa: E402
import hashlib  # noqa: E402
import inspect  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import sys  # noqa: E402
import textwrap  # noqa: E402
import time  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
FINAL = os.path.dirname(HERE)
sys.path.insert(0, FINAL)
import numpy as np  # noqa: E402
import calib_w9 as w  # noqa: E402

cl = w.cl
W9_SHA = hashlib.sha256(open(os.path.join(FINAL, "calib_w9.py"), "rb").read()).hexdigest()

# ------------------------------------------------------------------------------ SP20: the spacing rewrite
_src = textwrap.dedent(inspect.getsource(w.simulate))
assert _src.count("< t - 5)") == 1
_src = _src.replace("def simulate(", "def simulate_sp(").replace("< t - 5)", "< t - SPACING)")
w.SPACING = 20
exec(compile(_src, "calib_w9_simulate_sp", "exec"), w.__dict__)
w.simulate = w.simulate_sp

# ------------------------------------------------------------------------------ per-cell switches
SPACING: dict = {}        # cell name -> spacing (default 20)
NOLEV_OFF: set = set()    # cell names that keep the two levels (none in the registered runs)
TAUS: dict = {}           # cell name -> (rho_tau, A_G)
LV: set = set()           # LVSTY cells
_CUR: dict = {}

# ------------------------------------------------------------------------------ TAUS (re-check 1's rc9_taus.py, copied)
_orig_init = w.Gen.__init__
_orig_session = w.Gen.session
_orig_prior = w.prior
_orig_hd = w.hist_dirs


def _init(self, c, rng, R):
    _orig_init(self, c, rng, R)
    self.taus = None
    p = TAUS.get(c.name)
    if not p:
        return
    rho, a = p
    iss = self.iss
    U = cl.U
    tl = iss["tau"]
    th = rho * tl + math.sqrt(max(0.0, 1 - rho * rho)) * rng.normal(0, c.tau, tl.shape)
    lab = th / iss["sig_hat"]
    cnt = np.zeros((R, U))
    for _ in range(40):
        n = np.minimum(rng.poisson(c.nbar * rng.gamma(3.0, 1.0 / 3.0, R)), U)
        keys = iss["logp"] - np.log(-np.log(rng.random((R, U))))
        rk = np.argsort(np.argsort(-keys, axis=1), axis=1)
        cnt += rk < n[:, None]
    wt = cnt + 1e-9
    Xs = iss["ilev"]                                        # (R, U, 7): the lens's columns 28-34
    mx = (Xs * wt[..., None]).sum(1) / wt.sum(1)[:, None]
    Xc = Xs - mx[:, None, :]
    ml = (lab * wt).sum(1) / wt.sum(1)
    lc = lab - ml[:, None]
    A = np.einsum("rud,rue->rde", Xc * wt[..., None], Xc)
    b = np.einsum("rud,ru->rd", Xc * wt[..., None], lc)
    bs = np.linalg.solve(A + 1e-9 * np.eye(7)[None], b[..., None])[..., 0]
    sdl = np.sqrt((lc ** 2 * wt).sum(1) / wt.sum(1))
    zl = lc / sdl[:, None]
    g = a * zl + math.sqrt(1 - a * a) * rng.standard_normal((R, U))
    mg = (g * wt).sum(1) / wt.sum(1)
    sg = np.sqrt(((g - mg[:, None]) ** 2 * wt).sum(1) / wt.sum(1))
    g = (g - mg[:, None]) / sg[:, None]
    bg = ((g * lc) * wt).sum(1) / wt.sum(1)
    live = tl / iss["sig_hat"]
    lm = (live * wt).sum(1) / wt.sum(1)
    corr_live = ((g * (live - lm[:, None])) * wt).sum(1) / wt.sum(1) / np.sqrt(
        ((live - lm[:, None]) ** 2 * wt).sum(1) / wt.sum(1))
    self.taus = dict(g=g, bs=bs, bg=bg, corr_live=float(corr_live.mean()), sdl=float(sdl.mean()))
    _CUR["gen"] = self


def _session(self, wh_dir, P):
    s = _orig_session(self, wh_dir, P)
    if getattr(self, "taus", None) is not None:
        gi = len(w.KEEP) + 17
        s["X"][..., gi] = np.take_along_axis(self.taus["g"], s["ids"], axis=1)
    if self.c.name not in NOLEV_OFF:
        s["X"][..., 28:30] = 0.0                            # NOLEV: ln(adv20/1e7), ln(prev_close/20) deleted
    return s


def _prior_rand(c, P, rng, R):
    """ADV rand with the two levels deleted: calib_w9.prior's own draw (the same rng calls in the same order), with the
    random direction drawn over the LIVE columns only (a deleted column has variance 0, and calib_w9's z / sd would
    put inf x 0 = NaN into b_0). Everything else is calib_w9.prior's."""
    Dt = w.ncols(c.learner)
    S = P["S"].copy()
    gi = len(w.KEEP) + 17
    sc = np.ones(Dt)
    sc[gi] = math.sqrt(0.8)
    S = S * np.outer(sc, sc)
    A0 = c.n_eq * S
    sd = np.sqrt(np.diag(P["S"]))
    live = sd > 0
    z = rng.normal(0, 1, (R, Dt))
    z[:, ~live] = 0.0
    z /= np.linalg.norm(z, axis=1, keepdims=True)
    b = np.zeros((R, Dt))
    b[:, live] = c.adv_k * z[:, live] / sd[None, live]
    bp = b + P["b_cost"][None, :]
    b0 = np.einsum("de,re->rd", A0, bp)
    return np.broadcast_to(A0, (R, Dt, Dt)).copy(), b0, np.full(R, c.n_eq)


def _prior(c, P, rng, R):
    if c.adv == "rand":
        return _prior_rand(c, P, rng, R)
    gen = _CUR.get("gen")
    if c.name not in TAUS or gen is None or gen.taus is None:
        return _orig_prior(c, P, rng, R)
    Dt = w.ncols(c.learner)
    S = P["S"].copy()
    gi = len(w.KEEP) + 17
    sc = np.ones(Dt)
    sc[gi] = math.sqrt(0.8)
    S = S * np.outer(sc, sc)
    A0 = c.n_eq * S
    _, bh0 = w.hist_dirs(c, P)
    bh = np.broadcast_to(bh0, (R, Dt)).copy()
    for k, col in enumerate(range(28, 35)):
        bh[:, w.KEEP.index(col)] += gen.taus["bs"][:, k]
    bh[:, gi] += gen.taus["bg"]
    Lc = np.linalg.cholesky(P["S"] + 1e-10 * np.eye(Dt))
    folds = []
    for _k in range(4):
        z = rng.normal(0, 1, (R, Dt))
        noise = np.linalg.solve(Lc.T, z.T).T * math.sqrt(w.DE * P["s2"] / (w.N_HIST / 4.0))
        folds.append(bh + noise)
    F = np.stack(folds)
    full = F.mean(axis=0)
    dis = (np.sign(F) != np.sign(full)[None]).sum(axis=0)
    bp = np.where(dis >= 2, 0.0, full)
    b0 = np.einsum("de,re->rd", A0, bp)
    return np.broadcast_to(A0, (R, Dt, Dt)).copy(), b0, np.full(R, c.n_eq)


def _hd(c, P):
    wg, bh = _orig_hd(c, P)
    if c.name in LV:
        d = np.zeros(w.D0)
        d[30] = -1.0 / 1.044
        return d, bh
    return wg, bh


w.Gen.__init__ = _init
w.Gen.session = _session
w.prior = _prior
w.hist_dirs = _hd

# ------------------------------------------------------------------------------ cells
WORST = dict(shape="crasht3cl", phi_day=0.20, rho_day=0.15, ev_skew=True, tau=0.01, drift_sd=0.0020)
POOLS = {"ON": (300.0, 600.0, 800.0), "O1": (300.0, 450.0, 600.0)}
MID = {"ON": 600.0, "O1": 450.0}


def tag(c, suffix, **reg):
    c = dataclasses.replace(c, name=c.name + suffix)
    if "taus" in reg:
        TAUS[c.name] = reg["taus"]
    if reg.get("lv"):
        LV.add(c.name)
    if "sp" in reg:
        SPACING[c.name] = reg["sp"]
    return c


def histories(L, n):
    on = L == "ON"
    out = [
        w.mk(learner=L, ic_h=0.0, nbar=n, **WORST),
        w.mk(learner=L, ic_h=0.05, nbar=n, **WORST),
        w.mk(learner=L, ic_h=0.08, nbar=n, **WORST),
        w.mk(learner=L, ic_h=0.08, drift_c=0.0010, nbar=n, **WORST),
        w.mk(learner=L, adv="leak", adv_k=0.30, nbar=n, **WORST),
        w.mk(learner=L, adv="rand", adv_k=0.60, nbar=n, **WORST),
        w.mk(learner=L, adv="lowvol", adv_k=0.30, nbar=n, **WORST),
        w.mk(learner=L, null="N2", ic=0.05, ic_h=0.05, nbar=n, **WORST),
        w.mk(learner=L, null="N2", ic=0.08, ic_h=0.08, nbar=n, **WORST),
        tag(w.mk(learner=L, ic_h=0.0, tauh=on, nbar=n, **WORST), "-TAUS05a13", taus=(0.5, 0.13)),
        w.mk(learner=L, ic_h=0.0, nbar=n, **dict(WORST, tau=0.0)),
        w.mk(learner=L, adv="lowvol", adv_k=0.30, nbar=n, **dict(WORST, tau=0.0)),
    ]
    if on:
        out.append(w.mk(learner=L, ic_h=0.0, tauh=True, nbar=n, **WORST))
    return out


def grid(name):
    cells = []
    if name == "search":
        for L in ("O1", "ON"):
            for n in POOLS[L]:
                cells += histories(L, n)
            m = MID[L]
            cells.append(w.mk(learner=L, ic_h=0.0, nbar=m, **dict(WORST, shape="crasht3")))
            cells.append(w.mk(learner=L, ic_h=0.0, nbar=m, **dict(WORST, drift_sd=0.0)))
            cells.append(w.mk(learner=L, ic_h=0.0, nbar=m, **dict(WORST, drift_sd=0.0010)))
            cells.append(w.mk(learner=L, ic_h=0.0, nbar=m, cnt=0.3, **WORST))
            for n in POOLS[L]:
                cells.append(w.mk(learner=L, hist="cold", nbar=n, **WORST))
        return cells, 861_000_001
    if name == "power":
        PB = dict(shape="t3", rho_day=0.05, phi_day=0.10, ev_skew=False, drift_sd=0.0, tau=0.0)
        for L, pool in (("O1", 300.0), ("ON", 600.0)):
            for ic in (0.03, 0.05, 0.08):
                cells.append(w.mk(learner=L, null="A", ic=ic, hist="cold", nbar=pool, **PB))
                for rho in (1.0, 0.7, 0.0):
                    cells.append(w.mk(learner=L, null="A", ic=ic, ic_h=ic, rho_h=rho, nbar=pool, **PB))
        for hist, rho in (("cold", 1.0), ("warm", 1.0), ("warm", 0.7)):
            cells.append(w.mk(learner="ON", null="A", ic=0.05, ic_h=0.05, rho_h=rho, hist=hist, nbar=600.0,
                              **dict(WORST, tau=0.0)))
        # SP20's power price at the same cells under the old spacing (re-check 1's fix2 comparison)
        for L, pool in (("O1", 300.0), ("ON", 600.0)):
            cells.append(tag(w.mk(learner=L, null="A", ic=0.05, ic_h=0.05, rho_h=1.0, nbar=pool, **PB), "-SP05", sp=5))
        return cells, 864_000_001
    if name == "stress":
        for L in ("O1", "ON"):
            m = MID[L]
            cells.append(w.mk(learner=L, ic_h=0.0, nbar=m, **dict(WORST, phi_day=0.25)))
            cells.append(w.mk(learner=L, ic_h=0.0, nbar=m, **dict(WORST, shape="crash", rho_day=0.30, phi_day=0.10)))
            cells.append(w.mk(learner=L, ic_h=0.0, nbar=m, **dict(WORST, shape="crash", rho_day=0.30, phi_day=0.40)))
            cells.append(w.mk(learner=L, ic_h=0.0, nbar=m, **dict(WORST, drift_sd=0.0030)))
            cells.append(w.mk(learner=L, ic_h=0.08, drift_c=0.0020, nbar=m, **WORST))
            cells.append(w.mk(learner=L, ic_h=0.08, drift_c=0.0030, nbar=m, **WORST))
            cells.append(w.mk(learner=L, ic_h=0.0, sec_drift=0.0020, nbar=m, **dict(WORST, tau=0.0)))
            cells.append(w.mk(learner=L, ic_h=0.0, guard=False, nbar=m, **WORST))
            cells.append(w.mk(learner=L, adv="lowvol", adv_k=0.30, guard=False, nbar=m, **WORST))
            cells.append(w.mk(learner=L, adv="lowvol", adv_k=0.60, nbar=m, **WORST))
            cells.append(tag(w.mk(learner=L, adv="lowvol", adv_k=0.30, drift_c=0.0010, nbar=m, **WORST), "-LVSTY10",
                             lv=True))
            cells.append(tag(w.mk(learner=L, ic_h=0.0, tauh=(L == "ON"), nbar=m, **WORST), "-TAUS10a13",
                             taus=(1.0, 0.13)))
            cells.append(tag(w.mk(learner=L, adv="lowvol", adv_k=0.30, nbar=m, **WORST), "-SP05", sp=5))
        cells.append(w.mk(learner="ON", ic_h=0.0, tau_mode="all", nbar=600.0, **WORST))
        cells.append(w.mk(learner="ON", ic_h=0.0, tau_mode="all", tauh=True, nbar=600.0, **WORST))
        cells.append(w.mk(learner="ON", ic_h=0.0, tauh=True, nbar=600.0, **dict(WORST, tau=0.02)))
        return cells, 866_000_001
    if name in ("fresh1", "fresh2", "life", "coldref"):
        names = json.loads(os.environ["W9F_CELLS"])
        reg = {c.name: c for c in all_cells()}
        cs = [reg[n] for n in names]
        if name == "life":
            out = []
            for c in cs:
                c2 = dataclasses.replace(c, T=200, name=c.name + "-T200")
                for d, key in ((TAUS, "taus"), (SPACING, "sp")):
                    if c.name in d:
                        d[c2.name] = d[c.name]
                if c.name in LV:
                    LV.add(c2.name)
                out.append(c2)
            cs = out
        base = {"fresh1": 862_000_001, "fresh2": 863_000_001, "life": 865_000_001, "coldref": 867_000_001}[name]
        return cs, base
    if name == "smoke":
        return [dataclasses.replace(c, T=30, name=c.name + "-smoke") for c in grid("search")[0][:1]], 860_000_001
    raise SystemExit(f"unknown grid {name}")


def all_cells():
    out = []
    for g in ("search", "power", "stress"):
        out += grid(g)[0]
    return out


all_cells()                     # the registry (TAUS, LV, SPACING) in every process, the workers included


def _job(args):
    c, seed, R = args
    w.SPACING = SPACING.get(c.name, 20)
    res = w._job((c, seed, R))
    res["spacing"] = w.SPACING
    res["nolev"] = c.name not in NOLEV_OFF
    g = _CUR.pop("gen", None)
    if g is not None and getattr(g, "taus", None) is not None:
        res["taus_corr_live"] = g.taus["corr_live"]
    _CUR.clear()
    return res


def run(gname, workers, reps=None, chunk=50, resume=False):
    from multiprocessing import Pool
    cells, seed0 = grid(gname)
    R = reps or int(os.environ.get("W9F_REPS", "200"))
    for c in cells:
        w.population(c.learner, c.tau, c.tau_mode)
    path = os.path.join(HERE, f"ff.{gname}.jsonl")
    done = set()
    if resume and os.path.exists(path):
        for line in open(path):
            r = json.loads(line)
            done.add((r["cell"], r["seed"]))
    jobs = [(c, seed0 + 1000 * ci + j, chunk) for ci, c in enumerate(cells) for j in range(max(1, R // chunk))
            if (c.name, seed0 + 1000 * ci + j) not in done]
    # big pools first inside each round, so the tail of a stage is short jobs
    jobs.sort(key=lambda x: ((x[1] - seed0) % 1000, -x[0].nbar))
    t0 = time.time()
    with Pool(min(8, workers)) as pool, open(path, "a" if resume else "w") as fh:
        for k, res in enumerate(pool.imap_unordered(_job, jobs)):
            fh.write(json.dumps(res) + "\n")
            fh.flush()
            print(f"{gname}: {k + 1}/{len(jobs)} {res['cell']} seed {res['seed']} {res['secs']}s total "
                  f"{time.time() - t0:.0f}s", flush=True)


def load(tagname):
    by: dict = {}
    p = os.path.join(HERE, f"ff.{tagname}.jsonl")
    if os.path.exists(p):
        for line in open(p):
            r = json.loads(line)
            by.setdefault(r["cell"], []).append(r)
    return by


def report(gname):
    by = load(gname)
    print(f"== ff.{gname}.jsonl ({sum(len(v) for v in by.values())} jobs; calib_w9.py sha256 {W9_SHA})")
    rows = sorted(((w.summarise(p), n) for n, p in by.items()), key=lambda x: -x[0]["run1"])
    for s, name in rows:
        extra = ""
        if "life3" in s:
            extra = (f" | LIFE(<=3 runs) {s['life3']:.4f} by60 {s['life3_by60']:.3f} by120 {s['life3_by120']:.3f} "
                     f"runs {s['life3_runs']:.2f}")
        print(f"{name:<74} R={s['R']:<5} RUN1 {s['run1']:.4f} (se {s['run1_se']:.4f}) cm<=0 {s['cm0']:.4f} "
              f"cm<=10bp {s['cm10']:.4f} by25/40/60/120 {s['by25']:.3f}/{s['by40']:.3f}/{s['by60']:.3f}/"
              f"{s['by120']:.3f} | VERSION by120 {s['v120']:.4f} | ev/s {s['ev_s']:.2f} tau {s['tau_bp']:+.1f}bp "
              f"sig {s['sig']:.3f} guarded/s {s['guarded']:.1f}{extra}")
        if "-ic" in name:
            print("      picks' true a edge (bp) " + " ".join(f"{k}:{v}" for k, v in s["edge_bp"].items()))


def selftest():
    print("calib_w9.py sha256", W9_SHA)
    for L in ("O1", "ON"):
        P = w.population(L, 0.01, "event")
        S = P["S"]
        print(L, "columns", w.ncols(L), "zeroed (diag S == 0):", [int(j) for j in np.where(np.diag(S) < 1e-18)[0]],
              "live columns", int((np.diag(S) >= 1e-18).sum()))
    c = grid("smoke")[0][0]
    t0 = time.time()
    r = _job((c, 1, 10))
    print(c.name, round(time.time() - t0, 1), "s", "ev/s", round(r["ev_s"], 2), "spacing", r["spacing"], "nolev",
          r["nolev"])
    n = {g: len(grid(g)[0]) for g in ("search", "power", "stress")}
    print("cells", n, "TAUS", sorted(TAUS), "LV", sorted(LV))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("run", "report", "selftest"))
    ap.add_argument("--grid", default="search")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--reps", type=int, default=None)
    ap.add_argument("--resume", action="store_true")
    a = ap.parse_args()
    if a.cmd == "run":
        run(a.grid, a.workers, a.reps, resume=a.resume)
    elif a.cmd == "report":
        report(a.grid)
    else:
        selftest()
