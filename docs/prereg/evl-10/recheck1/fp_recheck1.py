#!/usr/bin/env python
"""fp_recheck1.py: ADVERSARIAL RE-CHECK 1 of PREREG-EVL-10 (statistics lens). The seat's false passes per run under
PREREG-EVL-6 AS FROZEN, rebuilt on FRESH seeds (381,000,001+ evaluation; 389,000,001+ centring pilots; 383,000,001+
power), with the READER-2 designer's consumer simulator UNCHANGED (../reader2/calib_r2.py, sha256 130de336..., which
imports PREREG-EVL-6's frozen calib_final.py e35e649d... and calib_v2.py d2991caa...).
SYNTHETIC ONLY: nothing here reads the lane's store, the House, the gateway, any price, return, look, band, mark or bar.

WHAT IS NEW AGAINST THE FIX ROUND'S fp_fix1.py:
  (1) CENTRING BY THE SIMULATOR ITSELF. calib_r2.knife_mu centres each null on a pilot that draws a candidate's sigma
      fresh and ignores the 5-session cooldown, the fixed issuer sigmas and the popularity draw that simulate() uses;
      under NV (the picks' day loadings follow sigma) that leaves the evaluation's realized pick mean a at -5.4 to
      +4.2 bp in the fix round's own cells. Here every null's mu is mu_knife less the realized money-weighted pick mean
      of a simulate() pilot of the same cell (12,000 programs, its own seeds): the pick set does not depend on mu, so
      one correction is exact up to the pilot's sampling error, which is printed.
  (2) A DENSER THIN-SUPPLY SURFACE for NV at the corner (t(3)-body crash days clustered in high volatility, left-skewed
      events, rho_day 0.15, phi_day 0.20, a 20 bp drift at AR 0.97, counts that follow the day): candidates 5-42 a
      session at the reader's own filter passing 10-60%, including the 42-candidate SET at strict filters (5-7 picks
      a session whose count follows the day below K = 8), which no earlier round ran.
  (3) NVK, THE KNIFE ON NV: the key prefers volatile names (NV's 0.6 z(log sigma)) AND carries information on a true
      news value alpha (sd_alpha x xi; key' = (key_NV + b xi) / sqrt(1 + b^2)), mu centred so the picks' money-weighted
      mean is zero. Under NV the picks' heavier day loadings make the SET's mean exceed the picks' at the knife, so the
      beat-the-control guard protects; PREREG-EVL-6's knife-edge null exists exactly so that guard never protects.
      NVK is NV with that protection removed by information the mean then offsets.
  (4) the other nulls (NI, N1, NK) and the other clustered/t(3) day shapes at the worst thin cell, re-centred.
  (5) the centring's sensitivity (the worst cell at mu +-3 bp) and power at strict filters (base model, 42
      candidates, counts that follow the day, sd of true news value 0.8%, c 0.5 / 0.7, filters 15% / 30% / 60%).
Usage: fp_recheck1.py surface|nulls|sens|power [workers<=3]
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
os.environ.setdefault("FINAL_ARR", "/dev/shm/evl10-recheck1/arr")
os.environ.setdefault("V2_ARR", "/dev/shm/evl10-recheck1/arr")
os.makedirs("/dev/shm/evl10-recheck1/arr", exist_ok=True)
sys.path.insert(0, R2DIR)

import numpy as np  # noqa: E402
import calib_r2 as CR  # noqa: E402

CHUNK = 500
R_PILOT = 12_000
SEEDS = {"eval": 381_000_000, "pilot": 389_000_000, "power": 383_000_000, "sens": 382_000_000}
_ORIG_DRAW = CR.draw_session
C20 = dict(CR.CORNER, drift_sd=0.0020)
C10 = dict(CR.CORNER, drift_sd=0.0010)


def make_draw(nvk):
    """calib_r2.draw_session unchanged; for NVK (nvk = (b, sd_alpha)) the NV key gains information on a true news
    value and the reader's own filter is re-applied to the new key (with the same cooldown rule)."""
    if nvk is None:
        return _ORIG_DRAW
    b, sda = nvk

    def draw(rng, cell, g, R, U, logw, sector, isig, upref, lvol_x, eps, Emult, hot_add, last=None, t=None):
        d = _ORIG_DRAW(rng, cell, g, R, U, logw, sector, isig, upref, lvol_x, eps, Emult, hot_add, last, t)
        if d is None:
            return None
        mask, idx, key, alpha, passf, big, nC = d
        xi = rng.standard_normal(key.shape)
        key = (key + b * xi) / math.sqrt(1.0 + b * b)
        alpha = sda * xi
        if cell.finf:
            passf = (key > CR.z_pass(cell.f_pass)) & mask
        else:
            passf = (rng.random(key.shape) < cell.f_pass) & mask
        if last is not None:
            rows = np.arange(R)[:, None]
            passf &= (t - last[rows, idx]) > CR.COOLDOWN
        return mask, idx, key, alpha, passf, big, nC
    return draw


def cells(phase):
    """(label, Cell, R_eval, nvk, mu_shift_bp, centre)"""
    out = []
    if phase == "surface":
        for nbar, f, R in ((5, 0.3, 8000), (5, 0.6, 4000), (6, 0.25, 4000), (8, 0.3, 4000), (8, 0.15, 4000),
                           (10, 0.15, 4000), (16, 0.1, 4000), (14, 0.6, 4000), (26, 0.2, 4000), (42, 0.15, 4000),
                           (42, 0.3, 4000), (42, 0.6, 4000)):
            out.append((f"RC|NV|corner|AR20|n{nbar}|cnt|finf|f{f}",
                        CR.Cell(null="NV", nbar=nbar, cnt=True, finf=True, f_pass=f, **C20), R, None, 0.0, True))
        out.append(("RC|NV|corner|AR10|n5|cnt|finf|f0.3",
                    CR.Cell(null="NV", nbar=5, cnt=True, finf=True, f_pass=0.3, **C10), 4000, None, 0.0, True))
        out.append(("RC|NV|corner|AR20|n42|finf|f0.15 (no cnt)",
                    CR.Cell(null="NV", nbar=42, cnt=False, finf=True, f_pass=0.15, **C20), 4000, None, 0.0, True))
        return out
    if phase == "nulls":
        for null in ("NI", "N1", "NK"):
            out.append((f"RC|{null}|corner|AR20|n5|cnt|finf|f0.3",
                        CR.Cell(null=null, nbar=5, cnt=True, finf=True, f_pass=0.3, **C20), 4000, None, 0.0, True))
        for (nbar, f), b, sda in (((5, 0.3), 0.5, 0.006), ((5, 0.3), 0.5, 0.010), ((8, 0.3), 0.5, 0.010),
                                  ((5, 0.6), 0.5, 0.010), ((42, 0.15), 0.5, 0.010)):
            out.append((f"RC|NVK b{b} sda{sda}|corner|AR20|n{nbar}|cnt|finf|f{f}",
                        CR.Cell(null="NV", nbar=nbar, cnt=True, finf=True, f_pass=f, **C20), 4000, (b, sda), 0.0, True))
        for day in ("crasht3", "crashcl"):
            out.append((f"RC|NV|{day}|skew|AR20|n5|cnt|finf|f0.3",
                        CR.Cell(null="NV", nbar=5, cnt=True, finf=True, f_pass=0.3, **{**C20, "day": day}), 4000, None,
                        0.0, True))
        return out
    if phase == "sens":
        for sh in (-3.0, 0.0, 3.0):
            out.append((f"SENS|NV|corner|AR20|n5|cnt|finf|f0.3|mu{sh:+.0f}bp",
                        CR.Cell(null="NV", nbar=5, cnt=True, finf=True, f_pass=0.3, **C20), 4000, None, sh, True))
        out.append(("SENS|NV|corner|AR20|n5|cnt|finf|f0.3|knife_mu (designer centring)",
                    CR.Cell(null="NV", nbar=5, cnt=True, finf=True, f_pass=0.3, **C20), 4000, None, 0.0, False))
        return out
    if phase == "power":
        for c in (0.5, 0.7):
            for f in (0.15, 0.3, 0.6):
                out.append((f"PW|alt|base|n42|cnt|finf|f{f}|sda0.008|c{c}",
                            CR.Cell(null="alt", nbar=42, cnt=True, finf=True, f_pass=f, c=c, sd_alpha=0.008,
                                    **CR.BASE), 2000, None, 0.0, False))
        return out
    raise ValueError(phase)


def _sim(args):
    kw, R, seed, mu, nvk = args
    cell = CR.Cell(**kw)
    CR.draw_session = make_draw(nvk)
    t0 = time.time()
    res = CR.simulate(cell, R, 120, seed, mu)
    CR.draw_session = _ORIG_DRAW
    return seed, R, res, time.time() - t0


def _knife(args):
    kw, = args
    return CR.knife_mu(CR.Cell(**kw))


def main(phase, workers):
    cl = cells(phase)
    ctx = get_context("fork")
    with ctx.Pool(workers) as pool:
        mu0 = pool.map(_knife, [(dataclasses.asdict(c),) for _, c, _, _, _, _ in cl])
    print(f"{phase}: knife mu for {len(cl)} cells", flush=True)
    # centring pilots
    pilot_jobs, seed = [], SEEDS["pilot"] + {"surface": 0, "nulls": 100_000, "sens": 200_000, "power": 300_000}[phase]
    for i, (lab, c, R, nvk, sh, centre) in enumerate(cl):
        if not centre:
            continue
        for c0 in range(0, R_PILOT, CHUNK):
            seed += 1
            pilot_jobs.append((i, (dataclasses.asdict(c), CHUNK, seed, mu0[i], nvk)))
    pil = {}
    t0 = time.time()
    with ctx.Pool(workers) as pool:
        for k, (out_, (i, _)) in enumerate(zip(pool.imap(_sim, [j for _, j in pilot_jobs]), pilot_jobs), 1):
            sd_, Rj, res, _s = out_
            pil.setdefault(i, []).append((res["picks_per_session"] * Rj * 120, res["realized_mean_a_bp"]))
            if k % 24 == 0 or k == len(pilot_jobs):
                print(f"{phase}: pilot {k}/{len(pilot_jobs)} {time.time() - t0:.0f}s", flush=True)
    mus, pinfo = [], []
    for i, (lab, c, R, nvk, sh, centre) in enumerate(cl):
        if centre:
            w = np.array([a for a, _ in pil[i]]); m = np.array([b for _, b in pil[i]])
            pm = float((w * m).sum() / w.sum())
            se = float(np.std(m, ddof=1) / math.sqrt(len(m)))
            mu = mu0[i] - pm / 1e4 + sh / 1e4
            pinfo.append({"pilot_mean_a_bp_at_knife_mu": round(pm, 3), "pilot_se_bp": round(se, 3),
                          "pilot_R": R_PILOT})
        else:
            mu = mu0[i] + sh / 1e4
            pinfo.append(None)
        mus.append(mu)
    jobs, seed = [], SEEDS["power" if phase == "power" else "eval"] + {"surface": 0, "nulls": 100_000, "sens": 200_000,
                                                                       "power": 0}[phase]
    for i, (lab, c, R, nvk, sh, centre) in enumerate(cl):
        for c0 in range(0, R, CHUNK):
            seed += 1
            jobs.append((i, (dataclasses.asdict(c), min(CHUNK, R - c0), seed, mus[i], nvk)))
    agg = {}
    t0 = time.time()
    with ctx.Pool(workers) as pool:
        for k, (out_, (i, _)) in enumerate(zip(pool.imap(_sim, [j for _, j in jobs]), jobs), 1):
            sd_, Rj, res, _s = out_
            a = agg.setdefault(i, {"p1": [], "ret1": [], "end1": [], "p2": [], "pps": 0.0, "rma": 0.0, "seeds": [],
                                   "chunk_ma": []})
            for key in ("p1", "ret1", "end1", "p2"):
                a[key] += res[key]
            a["pps"] += res["picks_per_session"] * Rj
            a["rma"] += res["realized_mean_a_bp"] * res["picks_per_session"] * Rj
            a["chunk_ma"].append(res["realized_mean_a_bp"])
            a["seeds"].append(sd_)
            if k % 24 == 0 or k == len(jobs):
                print(f"{phase}: eval {k}/{len(jobs)} {time.time() - t0:.0f}s", flush=True)
    rows = []
    for i, (lab, c, R, nvk, sh, centre) in enumerate(cl):
        a = agg[i]
        n = len(a["p1"])
        res = {"p1": a["p1"], "ret1": a["ret1"], "end1": a["end1"], "p2": a["p2"],
               "picks_per_session": a["pps"] / n, "realized_mean_a_bp": a["rma"] / max(a["pps"], 1e-12)}
        s = CR.summarize(lab, c, res, 120)
        s["mu_bp"] = round(1e4 * mus[i], 3)
        s["mu_knife_bp"] = round(1e4 * mu0[i], 3)
        s["realized_mean_a_se_bp"] = round(float(np.std(a["chunk_ma"], ddof=1) / math.sqrt(len(a["chunk_ma"]))), 3)
        s["centring"] = pinfo[i]
        s["nvk"] = nvk
        s["mu_shift_bp"] = sh
        s["seeds"] = [min(a["seeds"]), max(a["seeds"])]
        rows.append(s)
    with open(os.path.join(HERE, f"fp_recheck1.{phase}.jsonl"), "w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    for r in rows:
        cen = r["centring"]
        print(f"{r['cell']:<58} R {r['R']:>5} run1 {r['pass_run1_120']:.4f} (+-{r['se']:.4f}) ver {r['per_version_120']:.4f}"
              f" pps {r['picks_per_session']:.2f} ma {r['realized_mean_a_bp']:+.2f}+-{r['realized_mean_a_se_bp']:.2f}"
              f" mu {r['mu_bp']:+.2f} (knife {r['mu_knife_bp']:+.2f}"
              + (f", pilot {cen['pilot_mean_a_bp_at_knife_mu']:+.2f}+-{cen['pilot_se_bp']:.2f})" if cen else ")"),
              flush=True)


if __name__ == "__main__":
    ph = sys.argv[1]
    w = min(int(sys.argv[2]) if len(sys.argv) > 2 else 3, 3)
    main(ph, w)
