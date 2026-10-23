#!/usr/bin/env python
"""fp_fix1.py: PREREG-EVL-10 FIX ROUND 1, the seat's false passes and power re-measured where the fixes touch them.
SYNTHETIC ONLY: nothing here reads the lane's store, the House, the gateway, any price, return, look, band, mark or bar.
Every number comes from the READER-2 designer's consumer simulator (../reader2/calib_r2.py, sha256 130de336..., which
imports PREREG-EVL-6's frozen files from ../reader2/evl6_frozen/: calib_final.py e35e649d..., calib_v2.py d2991caa...)
under PREREG-EVL-6's frozen screen, on FRESH seeds no designer, judge or check used (from 371,000,001).

WHY THESE CELLS (the changes that touch the calibration):
  worst   check 1's minor (the stated worst cell was not the worst) and check 2's minor 12 (p_up now asks about the
          seat's own overnight hold, which can pass FEWER reads through p_up >= 60, so the filter's pass share may sit
          well under the 0.6 the designer assumed): NV, NK and NS at thin supply (3, 5, 8 candidates) and strict filters
          (30%, 15%, 10% pass), the corner (t(3)-body crash days clustered in high volatility, left-skewed events,
          rho_day 0.15, phi_day 0.20, a 20 bp (and 10 bp) drift at AR 0.97), counts that follow the day.
                                                                                        seeds 371,000,001+
  starve  check 2's major 3, adopted: R2's dollars sit inside the lane's line, R2_LINE = max(0, min(0.75, L - 1.5 V -
          0.25)), V the heaviest day of v1's verdict dollars over the trailing 7 days. v1's dollars follow the news
          volume, and so (counts that follow the day, D14) the volatility regime: R2's supply is CUT on a session whose
          trailing week was heavy, and to ZERO when V >= 1.83. Modelled: V_t = V_med x TM_t / median(TM), TM_t the max of
          the day-count multiplier exp(0.3 min(|eps|, 4)) / E over the 7 sessions before t (the frozen generator's own
          D14 multiplier), L = $3; the session's R2 need = $0.50 x (its candidate count / Nbar) (the mid day between the
          designer's $0.41 and the caps' $0.60, cost_fix1.out); the session keeps the first floor(min(1, line / need) x
          N_t) candidates of its order (reads past the line are the session's latest; candidates are in an order
          independent of their values). V_med 1.42 (Oct 21's v1 volume, the line $0.62 at the median) and 1.60 (the line
          $0.35), at L = $3 (release 1019l's lane line) and, for reference, L = $3.75 (a lane line $0.75 higher, which a
          cost rule at goal V3's $10 could give). The knife's mu is recomputed under the SAME law, so every null's
          money-weighted pick mean is zero.
                                                                                        seeds 372,000,001+
  power   the cost of starvation in power: the designer's base consumer (42 candidates, the reader's own filter,
          sd of true news value 0.8%, c 0.5 and 0.7) with counts that follow the day, without and with the line.
                                                                                        seeds 373,000,001+
Usage: fp_fix1.py worst|starve|power [workers<=3]   (writes fp_fix1.<phase>.jsonl; stdout a line a cell)
"""
from __future__ import annotations

import dataclasses
import json
import math
import os
import sys
import time
from multiprocessing import get_context

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_v, "1")
HERE = os.path.dirname(os.path.abspath(__file__))
R2DIR = os.path.join(HERE, "..", "reader2")
os.environ.setdefault("FINAL_ARR", "/dev/shm/swing-fix10/arr")
os.environ.setdefault("V2_ARR", "/dev/shm/swing-fix10/arr")
os.makedirs("/dev/shm/swing-fix10/arr", exist_ok=True)
sys.path.insert(0, R2DIR)

import numpy as np  # noqa: E402
import calib_r2 as CR  # noqa: E402

V2 = CR.V2
CHUNK = 500
SEEDS = {"worst": 371_000_000, "starve": 372_000_000, "power": 373_000_000}
L_LINE, HEAD, BIRTHS, R2MAX, NEED_MEAN, WIN = 3.0, 1.5, 0.25, 0.75, 0.50, 7
_ORIG_DRAW = CR.draw_session


def _mult(eps, Emult):
    return np.exp(0.3 * np.minimum(np.abs(eps), 4.0)) / Emult


def tm_median(cell, L=L_LINE, seed=4747, R=20000, T=80):
    """The median of TM (the 7-session trailing max of the day-count multiplier) under the cell's day law, and the
    share of sessions the line starves to zero at V_med 1.42 / 1.60 (a report of the model, not an input)."""
    g = cell.gen()
    rng = np.random.default_rng(seed)
    Emult = V2.count_norm(g)
    lvol = rng.standard_normal(R) * g.vol_sd
    hist = []
    tms = []
    for t in range(T):
        lvol = g.vol_rho * lvol + math.sqrt(1 - g.vol_rho ** 2) * g.vol_sd * rng.standard_normal(R)
        eps, _ = V2.day_innov2(rng, g, R, lvol)
        if len(hist) >= WIN:
            tms.append(np.max(np.stack(hist[-WIN:]), axis=0))
        hist.append(_mult(eps, Emult))
    tm = np.concatenate(tms)
    med = float(np.median(tm))
    rep = {}
    for vmed in (1.42, 1.60):
        V = vmed * tm / med
        line = np.clip(L - HEAD * V - BIRTHS, 0.0, R2MAX)
        rep[f"V{vmed}"] = {"line_zero_share": round(float((line <= 1e-9).mean()), 4),
                           "line_mean": round(float(line.mean()), 4),
                           "line_q10_q50_q90": [round(float(np.quantile(line, q)), 3) for q in (0.1, 0.5, 0.9)]}
    return med, rep


def cut(mask, passf, nC, nbar, TM, tm_med, vmed, L=L_LINE):
    V = vmed * TM / tm_med
    line = np.clip(L - HEAD * V - BIRTHS, 0.0, R2MAX)
    need = NEED_MEAN * nC / nbar
    keep = np.where(need > 0, np.minimum(1.0, line / np.maximum(need, 1e-12)), 1.0)
    k = np.floor(keep * nC + 1e-9).astype(np.int64)
    cols = np.arange(mask.shape[1])[None, :] < k[:, None]
    return mask & cols, passf & cols


def make_draw(vmed, tm_med, L=L_LINE):
    """calib_r2.draw_session, unchanged, then the line's cut (the trailing week's multiplier kept per simulate call)."""
    state = {}

    def draw(rng, cell, g, R, U, logw, sector, isig, upref, lvol_x, eps, Emult, hot_add, last=None, t=None):
        key = id(rng)
        st = state.get(key)
        if st is None or t == 1:
            st = state[key] = {"hist": []}
        hist = st["hist"]
        TM = np.max(np.stack(hist[-WIN:]), axis=0) if hist else np.full(R, tm_med)
        hist.append(_mult(eps, Emult))
        del hist[:-WIN]
        d = _ORIG_DRAW(rng, cell, g, R, U, logw, sector, isig, upref, lvol_x, eps, Emult, hot_add, last, t)
        if d is None:
            return None
        mask, idx, key_, alpha, passf, big, nC = d
        mask, passf = cut(mask, passf, nC, cell.nbar, TM, tm_med, vmed, L)
        return mask, idx, key_, alpha, passf, big, nC
    return draw


def knife_mu_line(cell, vmed, tm_med, L=L_LINE, seed=4242, R=20000, T=60):
    """calib_r2.knife_mu's pilot with the SAME line cut applied before the picks (copied from calib_r2.py, the cut
    the only addition), so the null's money-weighted pick mean is zero under the starvation law too."""
    if cell.null in ("alt", "coarse"):
        return cell.mu_set
    g = cell.gen()
    rng = np.random.default_rng(seed)
    Emult = V2.count_norm(g) if cell.cnt else 1.0
    sd_c = g.sd_day()
    lvol = rng.standard_normal(R) * g.vol_sd
    lmean = (g.sig_hi - g.sig_lo) / math.log(g.sig_hi / g.sig_lo)
    num = den = 0.0
    hist = []
    for _ in range(T):
        lvol = g.vol_rho * lvol + math.sqrt(1 - g.vol_rho ** 2) * g.vol_sd * rng.standard_normal(R)
        h = np.exp(lvol - g.vol_sd ** 2)
        eps, _ = V2.day_innov2(rng, g, R, lvol)
        TM = np.max(np.stack(hist[-WIN:]), axis=0) if hist else np.full(R, tm_med)
        hist.append(_mult(eps, Emult))
        del hist[:-WIN]
        mult = np.exp(0.3 * np.minimum(np.abs(eps), 4.0)) / Emult if cell.cnt else 1.0
        nC = np.minimum(rng.poisson(cell.nbar * mult * rng.gamma(3.0, 1.0 / 3.0, R)), CR.NCAP)
        nmax = int(nC.max())
        if nmax == 0:
            continue
        mask = np.arange(nmax)[None, :] < nC[:, None]
        xi = rng.standard_normal((R, nmax)); noise = rng.standard_normal((R, nmax))
        sig = np.exp(rng.uniform(math.log(g.sig_lo), math.log(g.sig_hi), (R, nmax)))
        alpha = np.zeros((R, nmax))
        if cell.null == "NK":
            alpha = cell.sd_alpha * xi
            key = cell.c * xi + math.sqrt(1 - cell.c ** 2) * noise
        elif cell.null == "NV":
            zs = (np.log(sig) - math.log(math.sqrt(g.sig_lo * g.sig_hi))) / (math.log(g.sig_hi / g.sig_lo) / math.sqrt(12.0))
            key = 0.6 * zs + 0.8 * noise
        elif cell.null == "NS":
            key = 0.9 * (rng.random((R, nmax)) < 0.3) + 0.45 * noise
        else:
            key = noise
        if cell.finf:
            passf = (key > CR.z_pass(cell.f_pass)) & mask
        else:
            passf = (rng.random((R, nmax)) < cell.f_pass) & mask
        mask, passf = cut(mask, passf, nC, cell.nbar, TM, tm_med, vmed, L)
        sel = CR.pick(key, passf, cell.k)
        l = np.clip(sig / lmean, 0.3, 3.0) if cell.null == "NV" else 1.0
        term = alpha + (h * sd_c * math.sqrt(1 - g.phi_day ** 2) * eps)[:, None] * l
        num += float((term * sel).sum())
        den += float(sel.sum())
    return -num / max(den, 1.0)


C20 = dict(CR.CORNER, drift_sd=0.0020)
C10 = dict(CR.CORNER, drift_sd=0.0010)
BASE = dict(CR.BASE)


def cells(phase):
    """(label, Cell, R, line) with line None or (V_med, L)."""
    if phase == "worst":
        return [
            ("X|NV|corner|AR20|n5|cnt|finf|f0.3", CR.Cell(null="NV", nbar=5, cnt=True, finf=True, f_pass=0.3, **C20), 4000, None),
            ("X|NV|corner|AR20|n5|cnt|finf|f0.15", CR.Cell(null="NV", nbar=5, cnt=True, finf=True, f_pass=0.15, **C20), 4000, None),
            ("X|NV|corner|AR20|n8|cnt|finf|f0.1", CR.Cell(null="NV", nbar=8, cnt=True, finf=True, f_pass=0.10, **C20), 4000, None),
            ("X|NV|corner|AR20|n3|cnt|finf|f0.3", CR.Cell(null="NV", nbar=3, cnt=True, finf=True, f_pass=0.3, **C20), 2000, None),
            ("X|NV|corner|AR10|n5|cnt|finf|f0.3", CR.Cell(null="NV", nbar=5, cnt=True, finf=True, f_pass=0.3, **C10), 2000, None),
            ("X|NK|corner|AR20|n5|cnt|finf|f0.3", CR.Cell(null="NK", nbar=5, cnt=True, finf=True, f_pass=0.3, **C20), 2000, None),
            ("X|NS|corner|AR20|n5|cnt|finf|f0.3", CR.Cell(null="NS", nbar=5, cnt=True, finf=True, f_pass=0.3, **C20), 2000, None),
        ]
    if phase == "starve":
        out = []
        for vmed in (1.42, 1.60):
            out.append((f"S|NV|corner|AR20|n8|cnt|finf|f0.3|L3|V{vmed}",
                        CR.Cell(null="NV", nbar=8, cnt=True, finf=True, f_pass=0.3, **C20), 4000, (vmed, 3.0)))
            out.append((f"S|NV|corner|AR20|n14|cnt|finf|L3|V{vmed}",
                        CR.Cell(null="NV", nbar=14, cnt=True, finf=True, **C20), 2000, (vmed, 3.0)))
        out.append(("S|NV|corner|AR20|n5|cnt|finf|f0.3|L3|V1.6",
                    CR.Cell(null="NV", nbar=5, cnt=True, finf=True, f_pass=0.3, **C20), 4000, (1.60, 3.0)))
        out.append(("S|NK|corner|AR20|n8|cnt|finf|f0.3|L3|V1.6",
                    CR.Cell(null="NK", nbar=8, cnt=True, finf=True, f_pass=0.3, **C20), 2000, (1.60, 3.0)))
        out.append(("S|NS|corner|AR20|n8|cnt|finf|f0.3|L3|V1.6",
                    CR.Cell(null="NS", nbar=8, cnt=True, finf=True, f_pass=0.3, **C20), 2000, (1.60, 3.0)))
        out.append(("S|NV|corner|AR20|n8|cnt|finf|f0.3|L3.75|V1.6",
                    CR.Cell(null="NV", nbar=8, cnt=True, finf=True, f_pass=0.3, **C20), 2000, (1.60, 3.75)))
        out.append(("S|NV|corner|AR20|n8|cnt|finf|f0.3|noline(ref)",
                    CR.Cell(null="NV", nbar=8, cnt=True, finf=True, f_pass=0.3, **C20), 2000, None))
        return out
    if phase == "power":
        out = []
        for c in (0.5, 0.7):
            for line in (None, (1.42, 3.0), (1.60, 3.0), (1.60, 3.75)):
                tag = "noline" if line is None else f"L{line[1]}|V{line[0]}"
                out.append((f"P|alt|base|n42|cnt|finf|sda0.008|c{c}|{tag}",
                            CR.Cell(null="alt", nbar=42, cnt=True, finf=True, c=c, sd_alpha=0.008, **BASE), 2000, line))
        return out
    raise ValueError(phase)


def prep(args):
    lab, kw, line = args
    cell = CR.Cell(**kw)
    if line is None:
        return lab, CR.knife_mu(cell), None, None
    med, rep = tm_median(cell, line[1])
    return lab, knife_mu_line(cell, line[0], med, line[1]), med, rep


def job(args):
    lab, kw, R, seed, mu, line, med = args
    cell = CR.Cell(**kw)
    if line is not None:
        CR.draw_session = make_draw(line[0], med, line[1])
    else:
        CR.draw_session = _ORIG_DRAW
    t0 = time.time()
    res = CR.simulate(cell, R, 120, seed, mu)
    CR.draw_session = _ORIG_DRAW
    return lab, kw, R, seed, mu, res, time.time() - t0


def main(phase, workers):
    cl = cells(phase)
    with get_context("fork").Pool(workers) as pool:
        preps = pool.map(prep, [(lab, dataclasses.asdict(c), line) for lab, c, _, line in cl])
    pinfo = {lab: (mu, med, rep) for lab, mu, med, rep in preps}
    print(f"{phase}: knife mu / line pilots done for {len(cl)} cells", flush=True)
    jobs, seed = [], SEEDS[phase]
    for lab, c, R, line in cl:
        mu, med, _ = pinfo[lab]
        for c0 in range(0, R, CHUNK):
            seed += 1
            jobs.append((lab, dataclasses.asdict(c), min(CHUNK, R - c0), seed, mu, line, med))
    agg = {}
    t0 = time.time()
    with get_context("fork").Pool(workers) as pool:
        for k, (lab, kw, R, sd, mu, res, secs) in enumerate(pool.imap_unordered(job, jobs), 1):
            a = agg.setdefault(lab, {"p1": [], "ret1": [], "end1": [], "p2": [], "pps": 0.0, "rma": 0.0, "kw": kw,
                                     "mu": mu, "seeds": []})
            for key in ("p1", "ret1", "end1", "p2"):
                a[key] += res[key]
            a["pps"] += res["picks_per_session"] * R
            a["rma"] += res["realized_mean_a_bp"] * R
            a["seeds"].append(sd)
            if k % 8 == 0 or k == len(jobs):
                print(f"{phase}: {k}/{len(jobs)} {time.time() - t0:.0f}s", flush=True)
    rows = []
    for lab, c, R, line in cl:
        a = agg[lab]
        n = len(a["p1"])
        res = {"p1": a["p1"], "ret1": a["ret1"], "end1": a["end1"], "p2": a["p2"],
               "picks_per_session": a["pps"] / n, "realized_mean_a_bp": a["rma"] / n}
        s = CR.summarize(lab, CR.Cell(**a["kw"]), res, 120)
        s["mu_bp"] = round(1e4 * a["mu"], 2)
        s["seeds"] = sorted(a["seeds"])
        mu, med, rep = pinfo[lab]
        if line is not None:
            s["line"] = {"V_med": line[0], "TM_median": round(med, 4), "need_mean_usd": NEED_MEAN, "L": line[1],
                         "model": rep}
        rows.append(s)
    with open(os.path.join(HERE, f"fp_fix1.{phase}.jsonl"), "w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    for r in rows:
        print(f"{r['cell']:<48} R {r['R']:>5} run1 {r['pass_run1_120']:.4f} (+-{r['se']:.4f}) version "
              f"{r['per_version_120']:.4f} picks/s {r['picks_per_session']:.2f} mean a {r['realized_mean_a_bp']:+.2f} bp "
              f"mu {r['mu_bp']:+.2f}" + (f" line0 {r['line']['model'].get('V' + str(r['line']['V_med']), {}).get('line_zero_share')}"
                                         if r.get('line') else ""), flush=True)


if __name__ == "__main__":
    ph = sys.argv[1]
    w = min(int(sys.argv[2]) if len(sys.argv) > 2 else 3, 3)
    main(ph, w)
