#!/usr/bin/env python
"""judge_fp.py (the edge-swings JUDGE, PREREG-EVL-10 / -11): independent false-pass replications of the two seats
under PREREG-EVL-6's FROZEN screen, on FRESH seeds that no designer, red team or judge used to choose anything.
SYNTHETIC ONLY: nothing here reads the lane's store, the House, the gateway, any price, return, look, band or mark.

Phase "idn"  (PREREG-EVL-11's gated seat EVL-IDN-READ): PREREG-EVL-6's own generator (evl6_frozen/calib_v2.py, sha256
             d2991caa...) and its rule (evl6_frozen/search_final.py first_pass / two_runs, sha256 606c5407...: looks at
             blocks 22, 25, 30, 35, 40, 50, 60; alpha 0.020 / 0.006 / 0.001; values min(n, 14) x (B - 10 bp); top-14,
             issuer and control guards; RETIRE; run 2 after block 60), the knife null N3 (skill 0.6%, family mean -0.6%),
             at the seat's supply after its cost filter (3, 5, 8 a session) at the widened grid's worst corner
             (t(3)-body crash days clustered in high volatility, left-skewed events, rho_day 0.15, phi_day 0.20, drift
             10 / 20 bp at AR 0.97) with counts that follow the day (kappa 0.3, the money-weighted knife), plus the
             base model. Seeds from 244,000,001.
Phase "r2"   (PREREG-EVL-10's seat EVL-R2-ON): the READER-2 designer's consumer simulator (../reader2/calib_r2.py,
             sha256 130de336..., which imports the same frozen files) at its worst cells AND at the thinner supply the
             judge's BUYABLE condition makes (8 a session with counts that follow the day), each null of that file
             (NV volatile key, NK the knife, NS big news, NI persistent issuers). Seeds from 243,000,001.
Usage: judge_fp.py idn|r2 [workers]   (at most 4 workers; outputs judge_fp.<phase>.jsonl and stdout)
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
os.environ.setdefault("V2_ARR", "/dev/shm/swing-judge/arr")
os.environ.setdefault("FINAL_ARR", "/dev/shm/swing-judge/arr")

import numpy as np  # noqa: E402

CHUNK = 1000


# ------------------------------------------------------------------------------------------------------ phase idn
def idn_cells():
    sys.path.insert(0, os.path.join(HERE, "evl6_frozen"))
    import calib_final as CF
    import calib_v2 as C2
    tc_skew = C2.shape_kw("TC", "skew")[1]
    out = []
    for dname, dsd in (("AR20", 0.0020), ("AR10", 0.0010)):
        for nb in (3, 5, 8):
            if dname == "AR10" and nb != 5:
                continue
            out.append((f"idn|TC-skew|{dname}|cnt|n{nb}", dict(nbar=nb, rho_day=0.15, phi_day=0.20, drift_sd=dsd,
                        cnt_kappa=0.3, mw_knife=14, **CF.N3, **tc_skew), 4000))
    t_skew = C2.shape_kw("T", "skew")[1]
    out.append(("idn|T-skew|AR20|cnt|n5", dict(nbar=5, rho_day=0.15, phi_day=0.20, drift_sd=0.0020, cnt_kappa=0.3,
                mw_knife=14, **CF.N3, **t_skew), 2000))
    out.append(("idn|base|n8", dict(nbar=8, rho_day=0.05, phi_day=0.10, day="t3", jump_left=0.5, **CF.N3), 2000))
    return out


def idn_job(args):
    lab, gk, R, seed = args
    sys.path.insert(0, os.path.join(HERE, "evl6_frozen"))
    import calib_v2 as C2
    import search_final as SF
    rule = SF.Rule(22, ((30, 0.020), (40, 0.006), (60, 0.001)))
    t0 = time.time()
    d, info = C2.simulate(C2.Gen2(**gk), R, 120, seed, run2=True)
    fp, fr, _ = SF.first_pass(d, "", rule)
    _, any_ = SF.two_runs(d, rule)
    return dict(lab=lab, R=R, seed=seed, p1=[float(x) for x in fp], any2=[float(x) for x in any_],
                ret=[float(x) for x in fr], mw=info["mw_mean_a_bp"], n=info["mean_read_n"], secs=time.time() - t0)


def run_idn(workers):
    jobs, seed = [], 244_000_000
    for lab, gk, R in idn_cells():
        for c0 in range(0, R, CHUNK):
            seed += 1
            jobs.append((lab, gk, min(CHUNK, R - c0), seed))
    agg = {}
    t0 = time.time()
    with get_context("fork").Pool(workers) as pool:
        for k, r in enumerate(pool.imap_unordered(idn_job, jobs), 1):
            a = agg.setdefault(r["lab"], dict(p1=[], any2=[], ret=[], mw=[], n=[], seeds=[]))
            a["p1"] += r["p1"]; a["any2"] += r["any2"]; a["ret"] += r["ret"]
            a["mw"].append(r["mw"] * r["R"]); a["n"].append(r["n"] * r["R"]); a["seeds"].append(r["seed"])
            print(f"idn: {k}/{len(jobs)} jobs {time.time() - t0:.0f}s", flush=True)
    rows = []
    for lab, a in sorted(agg.items()):
        p1 = np.array(a["p1"]); a2 = np.array(a["any2"]); R = p1.size
        f = float((p1 <= 120).mean()); se = math.sqrt(f * (1 - f) / R)
        rows.append(dict(cell=lab, R=R, run1_120=round(f, 4), se=round(se, 4), by30=round(float((p1 <= 30).mean()), 4),
                         by60=round(float((p1 <= 60).mean()), 4), two_runs_120=round(float((a2 <= 120).mean()), 4),
                         retire_120=round(float((np.array(a["ret"]) <= 120).mean()), 4),
                         mw_mean_a_bp=round(sum(a["mw"]) / R, 2), mean_n=round(sum(a["n"]) / R, 2),
                         seeds=sorted(a["seeds"])))
    return rows


# ------------------------------------------------------------------------------------------------------- phase r2
def r2_mod():
    sys.path.insert(0, os.path.join(HERE, "..", "reader2"))
    import calib_r2 as CR
    return CR


def r2_cells():
    CR = r2_mod()
    corner = dict(CR.CORNER, drift_sd=0.0020)
    out = [
        ("J|NV|corner|AR20|n5|cnt|finf", CR.Cell(null="NV", nbar=5, cnt=True, finf=True, **corner), 6000),
        ("J|NK|corner|AR20|n5|cnt|finf", CR.Cell(null="NK", nbar=5, cnt=True, finf=True, **corner), 4000),
        ("J|NV|corner|AR20|n8|cnt|finf", CR.Cell(null="NV", nbar=8, cnt=True, finf=True, **corner), 4000),
        ("J|NI|corner|AR20|n8|cnt|finf", CR.Cell(null="NI", nbar=8, cnt=True, finf=True, **corner), 4000),
        ("J|NS|corner|AR20|n8|cnt|finf", CR.Cell(null="NS", nbar=8, cnt=True, finf=True, **corner), 4000),
        ("J|NV|corner|AR20|n14|finf", CR.Cell(null="NV", nbar=14, finf=True, **corner), 4000),
        ("J|NV|base|n14|finf", CR.Cell(null="NV", nbar=14, finf=True, **CR.BASE), 2000),
    ]
    return out


def r2_knife(cell_kw):
    CR = r2_mod()
    return CR.knife_mu(CR.Cell(**cell_kw))


def r2_job(args):
    lab, cell_kw, R, seed, mu = args
    CR = r2_mod()
    t0 = time.time()
    res = CR.simulate(CR.Cell(**cell_kw), R, 120, seed, mu)
    return lab, cell_kw, R, seed, mu, res, time.time() - t0


def run_r2(workers):
    CR = r2_mod()
    cl = r2_cells()
    with get_context("fork").Pool(workers) as pool:
        mus = dict(zip([lab for lab, _, _ in cl], pool.map(r2_knife, [dataclasses.asdict(c) for _, c, _ in cl])))
    print("r2: knife mu done", {k: round(1e4 * v, 2) for k, v in mus.items()}, flush=True)
    jobs, seed = [], 243_000_000
    for lab, cell, Rc in cl:
        for c0 in range(0, Rc, 500):
            seed += 1
            jobs.append((lab, dataclasses.asdict(cell), min(500, Rc - c0), seed, mus[lab]))
    agg = {}
    t0 = time.time()
    with get_context("fork").Pool(workers) as pool:
        for k, (lab, kw, Rj, sd, mu, res, secs) in enumerate(pool.imap_unordered(r2_job, jobs), 1):
            a = agg.setdefault(lab, {"p1": [], "ret1": [], "end1": [], "p2": [], "pps": [], "rma": [], "kw": kw,
                                     "mu": mu, "seeds": []})
            for key in ("p1", "ret1", "end1", "p2"):
                a[key] += res[key]
            a["pps"].append(res["picks_per_session"] * Rj); a["rma"].append(res["realized_mean_a_bp"] * Rj)
            a["seeds"].append(sd)
            if k % 8 == 0 or k == len(jobs):
                print(f"r2: {k}/{len(jobs)} jobs {time.time() - t0:.0f}s", flush=True)
    rows = []
    for lab, a in sorted(agg.items()):
        n = len(a["p1"])
        res = {"p1": a["p1"], "ret1": a["ret1"], "end1": a["end1"], "p2": a["p2"],
               "picks_per_session": sum(a["pps"]) / n, "realized_mean_a_bp": sum(a["rma"]) / n}
        s = CR.summarize(lab, CR.Cell(**a["kw"]), res, 120)
        s["mu_bp"] = round(1e4 * a["mu"], 2)
        s["seeds"] = sorted(a["seeds"])
        rows.append(s)
    return rows


if __name__ == "__main__":
    phase = sys.argv[1]
    workers = min(int(sys.argv[2]) if len(sys.argv) > 2 else 4, 4)
    rows = run_idn(workers) if phase == "idn" else run_r2(workers)
    with open(os.path.join(HERE, f"judge_fp.{phase}.jsonl"), "w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    for r in rows:
        if phase == "idn":
            print(f"{r['cell']:<28} R {r['R']:>5} n {r['mean_n']:4.1f} | run1 by120 {r['run1_120']:.4f} (+-{r['se']:.4f}) "
                  f"by30 {r['by30']:.3f} by60 {r['by60']:.3f} | two runs {r['two_runs_120']:.4f} | retire "
                  f"{r['retire_120']:.3f} | mw a {r['mw_mean_a_bp']:+.1f} bp")
        else:
            print(f"{r['cell']:<32} R {r['R']:>5} run1 {r['pass_run1_120']:.4f} (+-{r['se']:.4f}) version "
                  f"{r['per_version_120']:.4f} by40 {r['by_session'][40]:.3f} picks/s {r['picks_per_session']:.2f} "
                  f"mean a {r['realized_mean_a_bp']:+.1f} bp mu {r['mu_bp']:+.1f}")
