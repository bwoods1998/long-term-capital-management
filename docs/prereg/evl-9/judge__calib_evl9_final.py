#!/usr/bin/env python
"""calib_evl9_final.py (the EVL-9 judge): the warm learners re-measured under PREREG-EVL-6's FINAL rule.

SYNTHETIC ONLY. Nothing here reads the lane, the House, the gateway, events.sqlite, live.sqlite, SEC or Alpaca data:
no price, return, look, band, bar or P&L of any real event, symbol or program. The paths are the learners lens's
generator and warm learner (evl9/learners/calib_evl9.py `simulate`, imported unchanged, which imports the EVL-7 learner
lens's calib_learner.py unchanged). Only the SCREEN is new: PREREG-EVL-6 as its final text states it
(evl6/final/PREREG-EVL-6.work.md sections 1.2-3, the rule chosen in evl6/final/chosen.json):

  ev6f  looks at S_k = 9, 10, ..., 16, 18, 20, 22, 25, 30, 35, 40, 50, 60 blocks with >= 30 events and >= 30 issuers;
        alpha 0.012 (S 9-14), 0.010 (15-20), 0.004 (21-60); values y_s = min(n_s, 14) x (B_s - 0.0010);
        RETIRE first (mean a < 0 and q <= alpha, q the sign-flip p of -min(n_s, 14) x B_s); PASS: p <= alpha, mean a > 0,
        mean r > 0, the top-14 events' mean a > 0 and mean r > 0 (every event here: a learner picks <= 8), the mean
        (unweighted) block value above the POOL control's over the same sessions, issuer-block p_I <= 0.10.
        A RUN ends at its 60th block unpassed and RUN 2 starts at the next block (D2); RETIRE ends the version.
  ev6d  PREREG-EVL-6's DRAFT (the learners lens's figures), on the same paths, for reference.

Reported per cell: run 1's pass rate within T sessions, the version's (all runs) within T, and P(promoted by s).
Usage: calib_evl9_final.py run --grid NAME [--reps R] [--chunk C] [--workers 4] | report
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
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "learners"))
import calib_evl9 as cw  # noqa: E402

cl = cw.cl
WCell = cw.WCell
LOOKS_F = (9, 10, 11, 12, 13, 14, 15, 16, 18, 20, 22, 25, 30, 35, 40, 50, 60)
CAP = 14
M0 = 0.0010


def alpha_f(S: int) -> float:
    if S <= 14:
        return 0.012
    if S <= 20:
        return 0.010
    return 0.004


def run_f(sim, rep, start):
    """One RUN of ev6f from session `start`: ('pass', t) | ('retire', t) | ('end', t) at the 60th block | (None, -1)."""
    B, Rm, n, ctrl = sim["B"][rep], sim["Rm"][rep], sim["n"][rep], sim["ctrl"][rep]
    iss, av = sim["iss"][rep], sim["a"][rep]
    T = len(B)
    blocks, w, bsess, ev_iss, ev_a = [], [], [], [], []
    ev_r_sum = 0.0
    seen: set = set()
    k = 0
    for t in range(start, T):
        kk = int(n[t])
        if kk == 0:
            continue
        a_t = av[t, :kk].astype(float)
        blocks.append(float(a_t.mean()))
        w.append(min(kk, CAP))
        bsess.append(t)
        ev_iss.extend(int(x) for x in iss[t, :kk])
        ev_a.extend(float(x) for x in a_t)
        ev_r_sum += float(Rm[t]) * kk
        seen.update(int(x) for x in iss[t, :kk])
        S = len(blocks)
        N = len(ev_a)
        look = False
        if k < len(LOOKS_F) and S >= LOOKS_F[k] and N >= cw.MIN_N and len(seen) >= cw.MIN_ISS:
            look = True
            while k < len(LOOKS_F) and S >= LOOKS_F[k]:
                k += 1
        if look:
            alpha = alpha_f(S)
            xb = np.array(blocks)
            wb = np.array(w, float)
            mean_a = sum(ev_a) / N
            q_x = -wb * xb
            if mean_a < 0 and cl.zstat(q_x) >= cl.Z_PRE and cl.flip_p(q_x) <= alpha + cl.TIE:
                return "retire", t
            y = wb * (xb - M0)
            if cl.zstat(y) >= cl.Z_PRE and cl.flip_p(y) <= alpha and mean_a > 0 and ev_r_sum / N > 0:
                cm = float(np.mean(ctrl[bsess]))
                if xb.mean() > cm and cl.issuer_p(ev_iss, ev_a, cl.B_ISS6) <= cw.ISS_ALPHA + cl.TIE:
                    return "pass", t
        if S >= cw.HORIZON:
            return "end", t
    return None, -1


def version_f(sim, rep, max_runs=10):
    """(run 1 passed, its session | -1, version passed (any run), its session | -1, runs started)."""
    start, runs = 0, 0
    r1 = None
    T = len(sim["B"][rep])
    while runs < max_runs and start < T:
        runs += 1
        how, t = run_f(sim, rep, start)
        if runs == 1:
            r1 = (how == "pass", t if how == "pass" else -1)
        if how == "pass":
            return r1[0], r1[1], True, t, runs
        if how != "end":
            break
        start = t + 1
    return r1[0], r1[1], False, -1, runs


W, WN = cw.WORST, cw.WORST_NT


def grid(name):
    C = lambda *a, **k: WCell(*a, **({"nbar": 300.0} | k))  # noqa: E731
    if name == "null":
        cells = [
            C("N1-HD08-worst", ic_h=0.08, **W),
            C("N1-HD08-worst-notau", ic_h=0.08, **WN),
            C("N1-HD05-worst", ic_h=0.05, **W),
            C("N1-H0-worst", ic_h=0.0, **W),
            C("N1-cold-worst", hist="cold", **W),
            C("N2-H08-worst", null="N2", ic=0.08, ic_h=0.08, **W),
            C("N1-HD08-worst-phi20", ic_h=0.08, **(W | dict(phi_day=0.20))),
            C("N1-HD08-worst-notau-phi20", ic_h=0.08, **(WN | dict(phi_day=0.20))),
            C("N1-cold-worst-notau-phi20", hist="cold", **(WN | dict(phi_day=0.20))),
            C("N1-HD08-base", ic_h=0.08),
            C("N1-H0-base", ic_h=0.0),
            C("N1-HD08-worst-notau-n600", ic_h=0.08, nbar=600.0, **WN),
        ]
        return cells, 191_000_001
    if name == "char":
        cells = [
            C("CHAR10-HD08-worst", ic_h=0.08, drift_c=0.0010, **W),
            C("CHAR20-HD08-worst", ic_h=0.08, drift_c=0.0020, **W),
            C("CHAR10-HD08-worst-notau-phi20", ic_h=0.08, drift_c=0.0010, **(WN | dict(phi_day=0.20))),
            C("CHAR20-HD08-worst-notau-phi20", ic_h=0.08, drift_c=0.0020, **(WN | dict(phi_day=0.20))),
            C("CHAR10-cold-worst-notau-phi20", hist="cold", drift_c=0.0010, **(WN | dict(phi_day=0.20))),
        ]
        return cells, 192_000_001
    if name == "life":
        cells = [C("N1-HD08-worst-notau-phi20-T300", ic_h=0.08, T=300, **(WN | dict(phi_day=0.20))),
                 C("CHAR10-HD08-worst-notau-phi20-T300", ic_h=0.08, drift_c=0.0010, T=300, **(WN | dict(phi_day=0.20)))]
        return cells, 193_000_001
    if name == "power":
        P = lambda *a, **k: WCell(*a, **({"T": 120} | k))  # noqa: E731
        cells = []
        for ic in (0.03, 0.05, 0.08):
            tag = f"ic{int(ic * 100):02d}"
            cells.append(P(f"A-{tag}-cold", null="A", ic=ic, mu_z=-0.04, hist="cold"))
            cells.append(P(f"A-{tag}-warm-rho10", null="A", ic=ic, mu_z=-0.04, ic_h=ic, rho_h=1.0))
            cells.append(P(f"A-{tag}-warm-rho07", null="A", ic=ic, mu_z=-0.04, ic_h=ic, rho_h=0.7))
            cells.append(P(f"A-{tag}-warm-rho00", null="A", ic=ic, mu_z=-0.04, ic_h=ic, rho_h=0.0))
        for ic in (0.05, 0.08):
            tag = f"ic{int(ic * 100):02d}"
            cells.append(P(f"A-{tag}-cold-worst", null="A", ic=ic, mu_z=-0.04, hist="cold", **WN))
            cells.append(P(f"A-{tag}-warm-rho10-worst", null="A", ic=ic, mu_z=-0.04, ic_h=ic, rho_h=1.0, **WN))
            cells.append(P(f"A-{tag}-warm-rho07-worst", null="A", ic=ic, mu_z=-0.04, ic_h=ic, rho_h=0.7, **WN))
        return cells, 194_000_001
    if name == "stress":
        S30 = dict(rho_day=0.30, day="crash", ev_skew=True, drift_sd=0.0020, tau=0.0)
        cells = [
            C("N1-HD08-stress-rho30-phi20", ic_h=0.08, **(S30 | dict(phi_day=0.20))),
            C("N1-HD08-stress-rho30-phi40", ic_h=0.08, **(S30 | dict(phi_day=0.40))),
            C("N1-cold-stress-rho30-phi40", hist="cold", **(S30 | dict(phi_day=0.40))),
            C("N1-HD08-worst-notau-phi25", ic_h=0.08, **(WN | dict(phi_day=0.25))),
            C("CHAR30-HD08-worst-notau-phi20", ic_h=0.08, drift_c=0.0030, **(WN | dict(phi_day=0.20))),
        ]
        return cells, 195_000_001
    if name == "smoke":
        return [C("smoke-N1-HD08", ic_h=0.08, T=40)], 190_000_001
    raise SystemExit(f"unknown grid {name}")


def _job(args):
    cell, seed, R = args
    t0 = time.time()
    sim = cw.simulate(cell, seed, R)
    out = {"cell": cell.name, "params": dataclasses.asdict(cell), "seed": seed, "R": R, "T": cell.T}
    v = [version_f(sim, i) for i in range(R)]
    out["ev6f"] = dict(p1=[int(x[0]) for x in v], w1=[int(x[1]) for x in v], pv=[int(x[2]) for x in v],
                       wv=[int(x[3]) for x in v], runs=[int(x[4]) for x in v])
    d = [cw.screen(sim, i, "ev6d") for i in range(R)]
    out["ev6d"] = dict(p1=[int(x[0]) for x in d], w1=[int(x[1]) for x in d])
    with np.errstate(invalid="ignore"):
        out["events_per_session"] = float(sim["n"].mean())
        arr = sim["curve_edge"]
        if not np.all(np.isnan(arr)):
            out["edge_bp"] = {f"{lo + 1}-{lo + 10}": round(float(np.nanmean(arr[:, lo:lo + 10])) * 1e4, 2)
                              for lo in range(0, cell.T, 10) if not np.all(np.isnan(arr[:, lo:lo + 10]))}
    out["secs"] = round(time.time() - t0, 1)
    return out


def run(gridname, reps, chunk, workers):
    from multiprocessing import Pool
    cells, seed0 = grid(gridname)
    jobs = [(cell, seed0 + 1000 * ci + j, chunk) for ci, cell in enumerate(cells) for j in range(max(1, reps // chunk))]
    path = os.path.join(HERE, f"calib_evl9_final.{gridname}.jsonl")
    cw.population()
    t0 = time.time()
    with Pool(workers) as pool, open(path, "w") as fh:
        for k, res in enumerate(pool.imap_unordered(_job, jobs)):
            fh.write(json.dumps(res) + "\n")
            fh.flush()
            print(f"{gridname}: {k + 1}/{len(jobs)} {res['cell']} {res['secs']}s total {time.time() - t0:.0f}s", flush=True)


def report():
    out = []
    for path in sorted(glob.glob(os.path.join(HERE, "calib_evl9_final.*.jsonl"))):
        rows = [json.loads(x) for x in open(path)]
        out.append(f"=== {os.path.basename(path)}")
        by: dict = {}
        for r in rows:
            by.setdefault(r["cell"], []).append(r)
        for cell, rs in by.items():
            T = rs[0]["T"]
            p1 = sum((sum(r["ev6f"]["p1"]) for r in rs), 0)
            pv = sum((sum(r["ev6f"]["pv"]) for r in rs), 0)
            n = sum(r["R"] for r in rs)
            w1 = [w for r in rs for w in r["ev6f"]["w1"]]
            wv = [w for r in rs for w in r["ev6f"]["wv"]]
            runs = [x for r in rs for x in r["ev6f"]["runs"]]
            d1 = sum((sum(r["ev6d"]["p1"]) for r in rs), 0)
            by_s = {s: sum(1 for w in wv if 0 <= w < s) / n for s in (20, 40, 60, 120) if s <= T}
            if T > 120:
                by_s[T] = sum(1 for w in wv if w >= 0) / n
            eps = np.mean([r["events_per_session"] for r in rs])
            edge = rs[0].get("edge_bp")
            se = math.sqrt(max(p1 / n * (1 - p1 / n), 1e-12) / n)
            line = (f"{cell:34s} R={n:5d} T={T} | ev6f run1 {p1 / n:.4f} (se {se:.4f}) version(all runs) {pv / n:.4f} "
                    f"by-session {json.dumps({k: round(v, 4) for k, v in by_s.items()})} runs {np.mean(runs):.2f} | "
                    f"ev6d run1 {d1 / n:.4f} | ev/s {eps:.2f}")
            if edge:
                es = {}
                for r in rs:
                    for k, v in (r.get("edge_bp") or {}).items():
                        es.setdefault(k, []).append(v)
                keys = [k for k in ("1-10", "31-40", "51-60", "111-120") if k in es]
                line += " | edge " + " ".join(f"{k}:{np.mean(es[k]):+.1f}" for k in keys)
            out.append(line)
    text = "\n".join(out)
    print(text)
    with open(os.path.join(HERE, "calib_evl9_final.report.txt"), "w") as fh:
        fh.write(text + "\n")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--grid", required=True)
    r.add_argument("--reps", type=int, default=1000)
    r.add_argument("--chunk", type=int, default=50)
    r.add_argument("--workers", type=int, default=4)
    sub.add_parser("report")
    a = ap.parse_args()
    if a.cmd == "run":
        run(a.grid, a.reps, a.chunk, min(4, a.workers))
    else:
        report()


if __name__ == "__main__":
    main()
