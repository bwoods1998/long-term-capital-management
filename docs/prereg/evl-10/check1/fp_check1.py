#!/usr/bin/env python
"""fp_check1.py (ADVERSARIAL CHECK #1 of PREREG-EVL-10 / -11 drafts; SYNTHETIC ONLY). Nothing here reads the lane's
store, the House, the gateway, any price, return, look, band, mark or bar. Every number comes from PREREG-EVL-6's own
frozen generator (../calib/evl6_frozen/calib_v2.py d2991caa..., calib_final.py e35e649d..., search_final.py 606c5407...)
and the READER-2 designer's consumer simulator (../reader2/calib_r2.py), on FRESH seeds no designer, red team or judge
used (from 261,000,001).

Phases (each writes fp_check1.<phase>.jsonl):
  sparse  EVL-IDN-READ below the frozen grid's lowest rate (3 a session): 2 and 1.5 a session, the corner (t(3)-body
          clustered crash days, skewed events, rho_day 0.15, phi_day 0.20, drift 20 / 10 bp AR 0.97, counts that follow
          the day, money-weighted knife).                                                        seeds 261,000,001+
  shift   the knife null plus a constant +delta bp on every event (an after-cost return that omits delta bp of real
          per-event cost, e.g. the CAT/TAF penny fees PREREG-EVL-1 charges and the -11 draft's replay does not), at 5
          a session at the corner.                                                               seeds 262,000,001+
  calm    the run starts in a CALM volatility state (the gate opens after spreads have been tight): the regime's log
          state at the start fixed at -1 and -2 stationary sd (x0 = -0.3, -0.6) instead of its stationary draw, at 5 a
          session at the corner and at the base model.                                           seeds 263,000,001+
  r2filter the same NV null at stricter reader filters (30%, 15% of candidates pass) at 8 and 14 candidates
                                                                                         seeds 266,000,001+
  r2sparse EVL-R2-ON's NV null (the worst R2 null) at thinner picks: Nbar 3 (f_pass 0.6) and Nbar 5 with a 30% filter,
          counts that follow the day, the corner, 20 bp.                                         seeds 264,000,001+
Usage: fp_check1.py PHASE [workers<=4]
"""
from __future__ import annotations

import dataclasses
import inspect
import json
import math
import os
import sys
import time
from multiprocessing import get_context

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_v, "1")
HERE = os.path.dirname(os.path.abspath(__file__))
FROZEN = os.path.join(HERE, "..", "calib", "evl6_frozen")
os.environ.setdefault("V2_ARR", "/dev/shm/swing-check1/arr")
os.environ.setdefault("FINAL_ARR", "/dev/shm/swing-check1/arr")
os.makedirs("/dev/shm/swing-check1/arr", exist_ok=True)
sys.path.insert(0, FROZEN)

import numpy as np  # noqa: E402
import calib_final as CF  # noqa: E402
import calib_v2 as C2  # noqa: E402
import search_final as SF  # noqa: E402

RULE = SF.Rule(22, ((30, 0.020), (40, 0.006), (60, 0.001)))
CHUNK = 500


def patched_simulate(x0=None, delta=0.0):
    """calib_v2.simulate with ONLY two lines changed: the regime's starting log state (x0, else the stationary draw)
    and a constant delta added to mu_family (every event's a). Every other line is the frozen file's, exec'd in its
    own module namespace."""
    src = inspect.getsource(C2.simulate)
    a = "    lvol = rng.standard_normal(R) * g.vol_sd\n"
    b = "    mu_family = knife_mu2(g)\n"
    assert src.count(a) == 1 and src.count(b) == 1
    if x0 is not None:
        src = src.replace(a, f"    lvol = np.full(R, {float(x0)!r}); rng.standard_normal(R)\n")
    src = src.replace(b, f"    mu_family = knife_mu2(g) + {float(delta)!r}\n")
    ns = dict(C2.__dict__)
    exec(compile(src, "patched_simulate", "exec"), ns)
    return ns["simulate"]


def corner(nb, drift=0.0020, **extra):
    tc = C2.shape_kw("TC", "skew")[1]
    return dict(nbar=nb, rho_day=0.15, phi_day=0.20, drift_sd=drift, cnt_kappa=0.3, mw_knife=14, **CF.N3, **tc,
                **extra)


def base(nb):
    return dict(nbar=nb, rho_day=0.05, phi_day=0.10, day="t3", jump_left=0.5, **CF.N3)


def cells(phase):
    if phase == "sparse":
        return [("idn|TC-skew|AR20|cnt|n2", corner(2), {}, 4000),
                ("idn|TC-skew|AR20|cnt|n1.5", corner(1.5), {}, 4000),
                ("idn|TC-skew|AR10|cnt|n2", corner(2, 0.0010), {}, 2000),
                ("idn|TC-skew|AR20|cnt|n3(ref)", corner(3), {}, 2000)]
    if phase == "shift":
        return [(f"idn|TC-skew|AR20|cnt|n5|delta{d}", corner(5), {"delta": d * 1e-4}, 4000) for d in (3, 5, 8)] + \
               [(f"idn|base|n8|delta{d}", base(8), {"delta": d * 1e-4}, 2000) for d in (5,)]
    if phase == "calm":
        return [(f"idn|TC-skew|AR20|cnt|n5|x0{x0}", corner(5), {"x0": x0}, 4000) for x0 in (-0.3, -0.6)] + \
               [("idn|TC-skew|AR20|cnt|n5|x0stat(ref)", corner(5), {}, 2000)] + \
               [(f"idn|TC-skew|AR20|n14|x0{x0}", dict(corner(14), cnt_kappa=0.0, mw_knife=0), {"x0": x0}, 2000)
                for x0 in (-0.6,)]
    raise ValueError(phase)


def job(args):
    lab, gk, opts, R, seed = args
    t0 = time.time()
    sim = patched_simulate(**opts) if opts else C2.simulate
    d, info = sim(C2.Gen2(**gk), R, 120, seed, run2=True)
    fp, fr, _ = SF.first_pass(d, "", RULE)
    _, any_ = SF.two_runs(d, RULE)
    return dict(lab=lab, R=R, seed=seed, p1=[int(x) for x in fp], any2=[int(x) for x in any_],
                ret=[int(x) for x in fr], mw=info["mw_mean_a_bp"], n=info["mean_read_n"], secs=time.time() - t0)


def run_gen(phase, workers, seed0):
    jobs, seed = [], seed0
    for lab, gk, opts, R in cells(phase):
        for c0 in range(0, R, CHUNK):
            seed += 1
            jobs.append((lab, gk, opts, min(CHUNK, R - c0), seed))
    agg = {}
    t0 = time.time()
    with get_context("fork").Pool(workers) as pool:
        for k, r in enumerate(pool.imap_unordered(job, jobs), 1):
            a = agg.setdefault(r["lab"], dict(p1=[], any2=[], ret=[], mw=0.0, n=0.0, seeds=[]))
            a["p1"] += r["p1"]; a["any2"] += r["any2"]; a["ret"] += r["ret"]
            a["mw"] += r["mw"] * r["R"]; a["n"] += r["n"] * r["R"]; a["seeds"].append(r["seed"])
            print(f"{phase}: {k}/{len(jobs)} {time.time() - t0:.0f}s", flush=True)
    rows = []
    for lab, a in sorted(agg.items()):
        p1 = np.array(a["p1"]); R = p1.size
        f = float((p1 <= 120).mean())
        rows.append(dict(cell=lab, R=R, run1_120=round(f, 4), se=round(math.sqrt(f * (1 - f) / R), 4),
                         by30=round(float((p1 <= 30).mean()), 4), by60=round(float((p1 <= 60).mean()), 4),
                         two_runs_120=round(float((np.array(a["any2"]) <= 120).mean()), 4),
                         retire_120=round(float((np.array(a["ret"]) <= 120).mean()), 4),
                         mw_mean_a_bp=round(a["mw"] / R, 2), mean_n=round(a["n"] / R, 2), seeds=sorted(a["seeds"])))
    return rows


# ------------------------------------------------------------------------------------------------- READER-2 sparse
def r2_mod():
    sys.path.insert(0, os.path.join(HERE, "..", "reader2"))
    import calib_r2 as CR
    return CR


def r2_cells(phase="r2sparse"):
    CR = r2_mod()
    c = dict(CR.CORNER, drift_sd=0.0020)
    if phase == "r2filter":
        return [("r2|NV|corner|AR20|n8|cnt|finf|f0.3", CR.Cell(null="NV", nbar=8, cnt=True, finf=True, f_pass=0.3, **c),
                 4000),
                ("r2|NV|corner|AR20|n8|cnt|finf|f0.15", CR.Cell(null="NV", nbar=8, cnt=True, finf=True, f_pass=0.15,
                                                              **c), 4000),
                ("r2|NV|corner|AR20|n14|finf|f0.3", CR.Cell(null="NV", nbar=14, finf=True, f_pass=0.3, **c), 2000),
                ("r2|NV|corner|AR20|n5|cnt|finf|f0.3|rep", CR.Cell(null="NV", nbar=5, cnt=True, finf=True, f_pass=0.3,
                                                                 **c), 2000)]
    return [("r2|NV|corner|AR20|n3|cnt|finf", CR.Cell(null="NV", nbar=3, cnt=True, finf=True, **c), 4000),
            ("r2|NV|corner|AR20|n5|cnt|finf|f0.3", CR.Cell(null="NV", nbar=5, cnt=True, finf=True, f_pass=0.3, **c),
             4000),
            ("r2|NK|corner|AR20|n3|cnt|finf", CR.Cell(null="NK", nbar=3, cnt=True, finf=True, **c), 2000)]


def r2_knife(kw):
    CR = r2_mod()
    return CR.knife_mu(CR.Cell(**kw))


def r2_job(args):
    lab, kw, R, seed, mu = args
    CR = r2_mod()
    return lab, kw, R, seed, mu, CR.simulate(CR.Cell(**kw), R, 120, seed, mu)


def run_r2(workers, phase="r2sparse"):
    CR = r2_mod()
    cl = r2_cells(phase)
    with get_context("fork").Pool(workers) as pool:
        mus = pool.map(r2_knife, [dataclasses.asdict(c) for _, c, _ in cl])
    jobs, seed = [], (264_000_000 if phase == "r2sparse" else 266_000_000)
    for (lab, c, R), mu in zip(cl, mus):
        for c0 in range(0, R, CHUNK):
            seed += 1
            jobs.append((lab, dataclasses.asdict(c), min(CHUNK, R - c0), seed, mu))
    agg = {}
    t0 = time.time()
    with get_context("fork").Pool(workers) as pool:
        for k, (lab, kw, R, sd, mu, res) in enumerate(pool.imap_unordered(r2_job, jobs), 1):
            a = agg.setdefault(lab, {"p1": [], "ret1": [], "end1": [], "p2": [], "pps": 0.0, "rma": 0.0, "kw": kw,
                                     "mu": mu, "seeds": []})
            for key in ("p1", "ret1", "end1", "p2"):
                a[key] += res[key]
            a["pps"] += res["picks_per_session"] * R; a["rma"] += res["realized_mean_a_bp"] * R
            a["seeds"].append(sd)
            print(f"{phase}: {k}/{len(jobs)} {time.time() - t0:.0f}s", flush=True)
    rows = []
    for lab, a in sorted(agg.items()):
        n = len(a["p1"])
        res = {"p1": a["p1"], "ret1": a["ret1"], "end1": a["end1"], "p2": a["p2"],
               "picks_per_session": a["pps"] / n, "realized_mean_a_bp": a["rma"] / n}
        s = CR.summarize(lab, CR.Cell(**a["kw"]), res, 120)
        s["mu_bp"] = round(1e4 * a["mu"], 2); s["seeds"] = sorted(a["seeds"])
        rows.append(s)
    return rows


if __name__ == "__main__":
    phase = sys.argv[1]
    workers = min(int(sys.argv[2]) if len(sys.argv) > 2 else 4, 4)
    seeds = {"sparse": 261_000_000, "shift": 262_000_000, "calm": 263_000_000}
    rows = run_r2(workers, phase) if phase.startswith("r2") else run_gen(phase, workers, seeds[phase])
    with open(os.path.join(HERE, f"fp_check1.{phase}.jsonl"), "w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    for r in rows:
        print(json.dumps({k: v for k, v in r.items() if k not in ("seeds", "gen")}))
