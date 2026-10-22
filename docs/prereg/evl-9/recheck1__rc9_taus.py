#!/usr/bin/env python
"""rc9_taus.py: RE-CHECK 1 of PREREG-EVL-9, the TAUS cells (SYNTHETIC ONLY).

THE CHANNEL W1 LEFT OPEN. W1 dropped the own-return columns r1/r5/r20 (and gap); TAUH covers a history that carried the
population slope of y on dmove. No cell of calib_w9 lets HISTORY carry the issuers' OWN persistent effects through the
columns that stay: the static issuer columns (ln adv20, ln prev_close, ln sig20, SIC groups) and the tree score g,
fitted on 1,200 sessions of the same issuers. TAUS: history's issuer effect tau_h = rho_tau x tau_live +
sqrt(1 - rho_tau^2) x independent (each N(0, tau)); the prior's static-column slopes are the in-sample (row-weighted)
projection of tau_h / sig_hat on those columns, and g is a static per-issuer score whose correlation with tau_h /
sig_hat is A_G, with the prior's slope on g its history regression slope. A_G = 0.13 is the best the registered tree
reached on the static columns in taus_tree.py (its 200-issuer best-split rule often stops it at the root: 0 there).
Everything else is calib_w9.simulate (imported unchanged; Gen and prior are wrapped, not edited)."""
import argparse, json, math, os, sys, time, dataclasses
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "final"))
import numpy as np  # noqa: E402
import calib_w9 as w  # noqa: E402
import calib_learner as cl  # noqa: E402

TAUS: dict = {}
_CUR: dict = {}
_orig_init = w.Gen.__init__
_orig_session = w.Gen.session
_orig_prior = w.prior


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
    # history row weights: the lens's pool law, 40 sessions of draws
    cnt = np.zeros((R, U))
    for _ in range(40):
        n = np.minimum(rng.poisson(c.nbar * rng.gamma(3.0, 1.0 / 3.0, R)), U)
        keys = iss["logp"] - np.log(-np.log(rng.random((R, U))))
        rk = np.argsort(np.argsort(-keys, axis=1), axis=1)
        cnt += rk < n[:, None]
    wt = cnt + 1e-9
    Xs = iss["ilev"]                                        # (R, U, 7)
    mx = (Xs * wt[..., None]).sum(1) / wt.sum(1)[:, None]
    Xc = Xs - mx[:, None, :]
    ml = (lab * wt).sum(1) / wt.sum(1)
    lc = lab - ml[:, None]
    A = np.einsum("rud,rue->rde", Xc * wt[..., None], Xc)
    b = np.einsum("rud,ru->rd", Xc * wt[..., None], lc)
    bs = np.linalg.solve(A + 1e-9 * np.eye(7)[None], b[..., None])[..., 0]   # (R, 7)
    sdl = np.sqrt((lc ** 2 * wt).sum(1) / wt.sum(1))
    zl = lc / sdl[:, None]
    g = a * zl + math.sqrt(1 - a * a) * rng.standard_normal((R, U))
    mg = (g * wt).sum(1) / wt.sum(1)
    sg = np.sqrt(((g - mg[:, None]) ** 2 * wt).sum(1) / wt.sum(1))
    g = (g - mg[:, None]) / sg[:, None]
    bg = ((g * lc) * wt).sum(1) / wt.sum(1)                 # cov(g, label) / var(g), var(g) = 1
    live = tl / iss["sig_hat"]
    lm = (live * wt).sum(1) / wt.sum(1)
    corr_live = ((g * (live - lm[:, None])) * wt).sum(1) / wt.sum(1) / np.sqrt(((live - lm[:, None]) ** 2 * wt).sum(1) / wt.sum(1))
    self.taus = dict(g=g, bs=bs, bg=bg, corr_live=float(corr_live.mean()), sdl=float(sdl.mean()))
    _CUR["gen"] = self


def _session(self, wh_dir, P):
    s = _orig_session(self, wh_dir, P)
    if self.taus is not None:
        gi = len(w.KEEP) + 17
        s["X"][..., gi] = np.take_along_axis(self.taus["g"], s["ids"], axis=1)
    return s


def _prior(c, P, rng, R):
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


w.Gen.__init__ = _init
w.Gen.session = _session
w.prior = _prior

BASE = dict(shape="crasht3cl", phi_day=0.20, rho_day=0.15, ev_skew=True, tau=0.01, drift_sd=0.0020, ic_h=0.0)


def cells():
    out = []
    for learner, tauh in (("O1", False), ("ON", True)):
        for rho, a in ((1.0, 0.13), (0.5, 0.13), (1.0, 0.0)):
            c = w.mk(learner=learner, tauh=tauh, **BASE)
            c = dataclasses.replace(c, name=c.name + f"-TAUS{int(rho * 10):02d}a{int(a * 100):02d}")
            TAUS[c.name] = (rho, a)
            out.append((c, 300))
        c = w.mk(learner=learner, hist="cold", **BASE)
        c = dataclasses.replace(c, name=c.name + "-TAUScoldref")
        out.append((c, 300))
    return out, 771_000_001


def _job(args):
    cells()                                     # the registry in each worker
    c, seed, R = args
    res = w._job((c, seed, R))
    g = _CUR.get("gen")
    if g is not None and getattr(g, "taus", None) is not None and c.name in TAUS:
        res["taus_corr_live"] = g.taus["corr_live"]
        res["taus_bg"] = float(np.mean(g.taus["bg"]))
    _CUR.clear()
    return res


def run(workers, chunk=50, only_smoke=False):
    from multiprocessing import Pool
    cs, seed0 = cells()
    if only_smoke:
        c, _ = cs[0]
        c = dataclasses.replace(c, T=25)
        TAUS[c.name] = TAUS[cs[0][0].name]
        t0 = time.time()
        r = _job((c, 1, 6))
        print("smoke", c.name, round(time.time() - t0, 1), "s", {k: r[k] for k in ("ev_s", "tau_bp", "taus_corr_live", "taus_bg")})
        return
    for c, _ in cs:
        w.population(c.learner, c.tau, c.tau_mode)
    jobs = []
    for ci, (c, reps) in enumerate(cs):
        for j in range(reps // chunk):
            jobs.append((c, seed0 + 1000 * ci + j, chunk))
    jobs.sort(key=lambda x: ((x[1] - seed0) % 1000, (x[1] - seed0) // 1000))
    path = os.path.join(HERE, "rc9.taus.jsonl")
    t0 = time.time()
    with Pool(min(8, workers)) as pool, open(path, "w") as fh:
        for k, res in enumerate(pool.imap_unordered(_job, jobs)):
            fh.write(json.dumps(res) + "\n")
            fh.flush()
            print(f"taus: {k + 1}/{len(jobs)} {res['cell']} seed {res['seed']} {res['secs']}s total {time.time() - t0:.0f}s",
                  flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("run", "smoke"))
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()
    run(a.workers, only_smoke=(a.cmd == "smoke"))
