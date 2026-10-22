#!/usr/bin/env python
"""calib_evl7.py: the JUDGE's re-calibration of PREREG-EVL-7's learners under PREREG-EVL-6's DRAFT screen (synthetic only).

Nothing here reads the lane, the House, the gateway, events.sqlite, live.sqlite or any market data. Every number is
drawn from evl7/learner/calib_learner.py's generator and learner (imported unchanged; the same seeds as its own
run_final.sh, so the paths are the very paths its L12 / E840 figures were measured on).

WHY: the learner lens measured its false passes under two of the EVL-6 judge's search candidates (L12, E840). The
EVL-6 draft (evl6/PREREG-EVL-6.draft.md, sections 1-3) chose a different rule. This script applies THAT rule:

  EV6  looks at the first block-adding close with S >= S_k, S_k = 6,7,...,16,18,20,22,25,30,35,40,50,60 AND >= 30
       events AND >= 30 issuers (thresholds reached together are one look); alpha(S) = A_LO for S <= S_SW, else A_HI;
       at a look, in order: RETIRE when mean a < 0 and the lower-tail p q <= alpha(S); PASS when p of mean(B - M0) > 0
       <= alpha(S), mean a > 0, mean r > 0, the mean block value > the control's over the same sessions (the learner's
       control is its POOL record) and the issuer-block p <= 0.10; EXHAUSTION: a version not passed at its 60th block
       is retired. The draft's constants: A_LO 0.016, S_SW 20, A_HI 0.004, M0 10 bp ("ev6d"); the EVL-6 check's
       tighter variant 0.014 / 20 / 0.0035 with M0 15 bp ("ev6t") is run beside, so the figure is known whichever
       EVL-6 freezes.
  CHAIN  PREREG-EVL-7's re-entry: after a retirement or an exhaustion at session e, the next version's record starts
       at session e + 1; at most 3 versions an id.
  COST7  (power only) the honest cost basis of PREREG-EVL-7 section 2 in place of the replay's: each pick's value is
       raised by DELTA_i = (the replay allowance in the generator, 11 bp liquid / 21 bp thin) - C7 (C7 = 11 bp liquid,
       11 bp thin: margin 5 + fees about 5 at learning size + impact about 1), i.e. +0 bp liquid and +10 bp thin; the
       pool control is raised by the pool's mean DELTA (the issuers' unweighted mean). Under a null the cost basis
       changes nothing (the null is "mean of the judged value = 0" whichever cost defines it), so COST7 is not run on
       the nulls.
  D57  (power and null) the learner with 17 more feature columns (the free headline and staleness flags PREREG-EVL-7
       adds: 16 keyword flags and dup_72h), drawn as pure noise binaries (p 0.02-0.30) and one noise continuous: the
       price of carrying them when they carry nothing.

Usage: calib_evl7.py run --grid {null,null800,life,power,d57} [--reps R] [--workers 4]  |  report
"""
from __future__ import annotations

import os

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import argparse  # noqa: E402
import dataclasses  # noqa: E402
import glob  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402

import numpy as np  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "learner"))
import calib_learner as cl  # noqa: E402

EV6_LOOKS = (6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 18, 20, 22, 25, 30, 35, 40, 50, 60)
RULES = {
    "ev6d": dict(a_lo=0.016, s_sw=20, a_hi=0.004, m0=0.0010),
    "ev6t": dict(a_lo=0.014, s_sw=20, a_hi=0.0035, m0=0.0015),
}
HORIZON = 60
MIN_N = 30
MIN_ISS = 30
ISS_ALPHA = 0.10
C7 = 0.0011
FINAL = dict(rank="a", lam=8000.0, kappa=0.0)     # the learner lens's final design (run_final.sh)
EXTRA = 17                                       # D57: the added columns


# --------------------------------------------------------------------------------------------- the EV6 screen
def screen_ev6(sim, rep, rule, start=0, delta=None, dctrl=0.0):
    """(passed, session of pass or -1, ended 'retire' | 'exhaust' | None, session it ended or -1) for one replicate.
    `delta` (T, K) adds the COST7 shift to each pick's a and r; `dctrl` to the pool control."""
    P = RULES[rule]
    B, Rm, n, ctrl = sim["B"][rep], sim["Rm"][rep], sim["n"][rep], sim["ctrl"][rep]
    iss, av = sim["iss"][rep], sim["a"][rep]
    T = len(B)
    blocks, bsess, ev_iss, ev_a = [], [], [], []
    ev_r_sum = 0.0
    seen: set = set()
    k = 0
    for t in range(start, T):
        kk = int(n[t])
        if kk == 0:
            continue
        a_t = av[t, :kk].astype(float)
        if delta is not None:
            a_t = a_t + delta[t, :kk]
        b_t = float(a_t.mean())
        r_t = float(Rm[t]) + (float(delta[t, :kk].mean()) if delta is not None else 0.0)
        blocks.append(b_t)
        bsess.append(t)
        ev_iss.extend(int(x) for x in iss[t, :kk])
        ev_a.extend(float(x) for x in a_t)
        ev_r_sum += r_t * kk
        seen.update(int(x) for x in iss[t, :kk])
        S = len(blocks)
        N = len(ev_a)
        look = False
        if k < len(EV6_LOOKS) and S >= EV6_LOOKS[k] and N >= MIN_N and len(seen) >= MIN_ISS:
            look = True
            while k < len(EV6_LOOKS) and S >= EV6_LOOKS[k]:
                k += 1
        if look:
            alpha = P["a_lo"] if S <= P["s_sw"] else P["a_hi"]
            xb = np.array(blocks)
            mean_a = sum(ev_a) / N
            if mean_a < 0 and cl.zstat(-xb) >= cl.Z_PRE and cl.flip_p(-xb) <= alpha + cl.TIE:
                return False, -1, "retire", t
            x = xb - P["m0"]
            if cl.zstat(x) >= cl.Z_PRE and cl.flip_p(x) <= alpha + cl.TIE and mean_a > 0 and ev_r_sum / N > 0:
                cm = float(np.mean(ctrl[bsess])) + dctrl
                if xb.mean() > cm and cl.issuer_p(ev_iss, ev_a, cl.B_ISS6) <= ISS_ALPHA + cl.TIE:
                    return True, t, None, t
        if S >= HORIZON:
            return False, -1, "exhaust", t
    return False, -1, None, -1


def chain_ev6(sim, rep, rule, versions=3, delta=None, dctrl=0.0):
    start = 0
    for v in range(1, versions + 1):
        ok, when, ended, end = screen_ev6(sim, rep, rule, start, delta, dctrl)
        if ok:
            return True, when, v
        if ended is None or end + 1 >= len(sim["B"][rep]):
            return False, -1, v
        start = end + 1
    return False, -1, versions


# --------------------------------------------------------------------------------------------- the D57 learner
_ORIG_PF = cl.pool_features
_ORIG = dict(D=cl.D, W_TRUE=cl.W_TRUE.copy(), W_FLIP=cl.W_FLIP.copy())
EXTRA_P = np.array([.02, .03, .04, .05, .06, .08, .10, .12, .15, .02, .03, .05, .08, .10, .20, .30])


def _pf_d57(rng, R, N, iss, ids):
    D0 = _ORIG["D"]
    cl.D = D0
    try:
        X0, fam = _ORIG_PF(rng, R, N, iss, ids)
    finally:
        cl.D = D0 + EXTRA
    X = np.zeros((R, N, D0 + EXTRA))
    X[..., :D0] = X0
    X[..., D0:D0 + 16] = rng.random((R, N, 16)) < EXTRA_P
    X[..., D0 + 16] = rng.beta(0.6, 2.0, (R, N))          # dup_72h-like, in [0, 1]
    return X, fam


def set_d57(on: bool):
    if on:
        cl.D = _ORIG["D"] + EXTRA
        cl.W_TRUE = np.concatenate([_ORIG["W_TRUE"], np.zeros(EXTRA)])
        cl.W_FLIP = np.concatenate([_ORIG["W_FLIP"], np.zeros(EXTRA)])
        cl.pool_features = _pf_d57
    else:
        cl.D = _ORIG["D"]
        cl.W_TRUE = _ORIG["W_TRUE"].copy()
        cl.W_FLIP = _ORIG["W_FLIP"].copy()
        cl.pool_features = _ORIG_PF
    cl._UNORM.clear()


# --------------------------------------------------------------------------------------------- cells
W = cl.WORST
NT = dict(tau=0.0)


def grid(name):
    """(cell, d57, cost7) triples. Seeds follow run_final.sh's: null 81e6+1, power 82e6+1, null800 83e6+1, life 85e6+1."""
    C = cl.Cell
    if name == "null":
        cells = [C("F-N1-base-n300", nbar=300, **FINAL), C("F-N1-worst-n300", nbar=300, **(W | FINAL)),
                 C("F-N1-worst-notau-n300", nbar=300, **(W | NT | FINAL)),
                 C("F-N2-ic03-worst-n300", null="N2", ic=0.03, nbar=300, **(W | FINAL)),
                 C("F-N2-ic05-worst-n300", null="N2", ic=0.05, nbar=300, **(W | FINAL)),
                 C("F-N2-ic05-worst-notau-n300", null="N2", ic=0.05, nbar=300, **(W | NT | FINAL))]
        return [(c, False, False) for c in cells], 81_000_001
    if name == "null800":
        cells = [C("F-N1-worst-n800", nbar=800, **(W | FINAL)), C("F-N1-worst-notau-n800", nbar=800, **(W | NT | FINAL))]
        return [(c, False, False) for c in cells], 83_000_001
    if name == "life":
        cells = [C("F-N1-worst-notau-n300-T300", nbar=300, T=300, **(W | NT | FINAL)),
                 C("F-N2-ic05-worst-notau-n300-T300", null="N2", ic=0.05, nbar=300, T=300, **(W | NT | FINAL))]
        return [(c, False, False) for c in cells], 85_000_001
    if name == "power":
        cells = [C(f"F-A-ic{int(ic * 100):02d}-base-n800", null="A", ic=ic, mu_z=-0.04, nbar=800, T=120, **FINAL)
                 for ic in (0.03, 0.05, 0.08, 0.12)]
        cells += [C("F-A-ic05-worst-notau-n800", null="A", ic=0.05, mu_z=-0.04, nbar=800, T=120, **(W | NT | FINAL)),
                  C("F-A-ic05-base-n300", null="A", ic=0.05, mu_z=-0.04, nbar=300, T=120, **FINAL)]
        return [(c, False, True) for c in cells], 82_000_001
    if name == "stress":
        cells = [C("F-N1-rho30-notau-n300", nbar=300, **(W | dict(rho_day=0.30, tau=0.0) | FINAL)),
                 C("F-N1-drift30-notau-n300", nbar=300, **(W | dict(drift_sd=0.0030, tau=0.0) | FINAL)),
                 C("F-N1-mom40-notau-n300", nbar=300, **(W | dict(rho_day=0.30, phi_day=0.40, tau=0.0) | FINAL)),
                 C("F-N3-famdrift20-notau-n300", nbar=300, fam_drift_sd=0.0020, **(W | dict(tau=0.0) | FINAL)),
                 C("F-N4-loadcorr-fac25-notau-n300", nbar=300, load_corr=0.7, fac_rho=0.25, **(W | dict(tau=0.0) | FINAL))]
        return [(c, False, False) for c in cells], 84_000_001
    if name == "d57":
        cells = [(C("D57-N1-worst-notau-n300", nbar=300, **(W | NT | FINAL)), True, False),
                 (C("D57-A-ic05-base-n800", null="A", ic=0.05, mu_z=-0.04, nbar=800, T=120, **FINAL), True, True),
                 (C("D57-A-ic08-base-n800", null="A", ic=0.08, mu_z=-0.04, nbar=800, T=120, **FINAL), True, True)]
        return cells, 86_000_001
    raise SystemExit(f"unknown grid {name}")


def _delta(cell, seed, R, sim, d57):
    """COST7's per-pick shift from the replicate's own issuers (simulate draws them first from the same seed)."""
    set_d57(d57)
    iss = cl.issuers(np.random.default_rng(seed), R, cell)
    dc = iss["cost"] - C7                                     # (R, U): +0 liquid, +10 bp thin
    ids = np.where(sim["iss"] >= 0, sim["iss"], 0)            # (R, T, K)
    d = dc[np.arange(R)[:, None, None], ids]
    d = np.where(sim["iss"] >= 0, d, 0.0)
    return d, dc.mean(axis=1)


def _job(args):
    cell, d57, cost7, seed, R = args
    set_d57(d57)
    t0 = time.time()
    sim = cl.simulate(cell, seed, R)
    out = {"cell": cell.name, "seed": seed, "R": R, "T": cell.T}
    for rule in RULES:
        one = [screen_ev6(sim, i, rule) for i in range(R)]
        ch = [chain_ev6(sim, i, rule) for i in range(R)]
        out[rule] = dict(pass_=[int(x[0]) for x in one], when=[int(x[1]) for x in one],
                         ended=[x[2] or "" for x in one], cpass=[int(x[0]) for x in ch], cwhen=[int(x[1]) for x in ch],
                         cver=[int(x[2]) for x in ch])
        if cost7:
            d, dm = _delta(cell, seed, R, sim, d57)
            one = [screen_ev6(sim, i, rule, 0, d[i], float(dm[i])) for i in range(R)]
            ch = [chain_ev6(sim, i, rule, 3, d[i], float(dm[i])) for i in range(R)]
            out[rule + "_c7"] = dict(pass_=[int(x[0]) for x in one], when=[int(x[1]) for x in one],
                                     cpass=[int(x[0]) for x in ch], cwhen=[int(x[1]) for x in ch])
    with np.errstate(invalid="ignore"):
        out["mean_a_picks_bp"] = float(np.nanmean(sim["a"]) * 1e4)
        out["events_per_session"] = float(sim["n"].mean())
        ce = sim["curve_edge"]
        out["curve_edge_bp"] = {f"{lo + 1}-{lo + 10}": round(float(np.nanmean(ce[:, lo:lo + 10])) * 1e4, 2)
                                for lo in range(0, cell.T, 10) if not np.all(np.isnan(ce[:, lo:lo + 10]))}
    out["secs"] = round(time.time() - t0, 1)
    return out


def run(gridname, reps, chunk, workers):
    from multiprocessing import Pool
    cells, seed0 = grid(gridname)
    jobs = []
    for ci, (cell, d57, cost7) in enumerate(cells):
        for j in range(max(1, reps // chunk)):
            jobs.append((cell, d57, cost7, seed0 + 1000 * ci + j, chunk))
    path = os.path.join(HERE, f"calib_evl7.{gridname}.jsonl")
    t0 = time.time()
    with Pool(workers) as pool, open(path, "w") as fh:
        for k, res in enumerate(pool.imap_unordered(_job, jobs)):
            fh.write(json.dumps(res) + "\n")
            fh.flush()
            print(f"{gridname}: {k + 1}/{len(jobs)} {res['cell']} {res['secs']}s total {time.time() - t0:.0f}s", flush=True)


# --------------------------------------------------------------------------------------------- report
def _se(p, n):
    return math.sqrt(max(p * (1 - p), 1e-12) / max(n, 1))


def report():
    for path in sorted(glob.glob(os.path.join(HERE, "calib_evl7.*.jsonl"))):
        rows = [json.loads(x) for x in open(path)]
        by: dict = {}
        for r in rows:
            by.setdefault(r["cell"], []).append(r)
        print(f"== {os.path.basename(path)}")
        for name, parts in by.items():
            R = sum(p["R"] for p in parts)
            T = parts[0]["T"]
            ev = np.mean([p["events_per_session"] for p in parts])
            ma = np.mean([p["mean_a_picks_bp"] for p in parts])
            line = [f"{name:<34} R={R:<5} T={T:<4} ev/s={ev:.2f} mean_a_picks={ma:.1f}bp"]
            for rule in list(RULES) + [r + "_c7" for r in RULES]:
                if rule not in parts[0]:
                    continue
                ps = np.concatenate([p[rule]["pass_"] for p in parts])
                wh = np.concatenate([p[rule]["when"] for p in parts])
                cps = np.concatenate([p[rule]["cpass"] for p in parts])
                cwh = np.concatenate([p[rule]["cwhen"] for p in parts])
                one = ps.mean()
                ch = cps.mean()
                byh = " ".join(f"by{h}={((ps == 1) & (wh < h)).mean():.3f}" for h in (20, 40, 60, 120) if h <= T)
                cbyh = " ".join(f"by{h}={((cps == 1) & (cwh < h)).mean():.3f}" for h in (40, 60, 120, 300) if h <= T)
                ex = ""
                if "ended" in parts[0][rule]:
                    en = np.concatenate([p[rule]["ended"] for p in parts])
                    ex = f" retired={(en == 'retire').mean():.3f} exhausted={(en == 'exhaust').mean():.3f}"
                line.append(f"   {rule:<7} one version pass={one:.4f} (se {_se(one, R):.4f}) {byh}{ex}")
                line.append(f"   {rule:<7} chain of 3   pass={ch:.4f} (se {_se(ch, R):.4f}) {cbyh}")
            ce = parts[0].get("curve_edge_bp")
            if ce and any(v for v in ce.values()):
                agg = {k: round(float(np.mean([p["curve_edge_bp"][k] for p in parts if k in p["curve_edge_bp"]])), 1)
                       for k in ce}
                line.append("   picks' true edge (bp) " + " ".join(f"{k}:{v}" for k, v in agg.items()))
            print("\n".join(line))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("run", "report"))
    ap.add_argument("--grid", default="null")
    ap.add_argument("--reps", type=int, default=2000)
    ap.add_argument("--chunk", type=int, default=100)
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    if a.cmd == "report":
        report()
        sys.exit(0)
    run(a.grid, a.reps, a.chunk, min(4, a.workers))
