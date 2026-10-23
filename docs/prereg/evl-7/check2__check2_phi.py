#!/usr/bin/env python
"""check2_phi.py: adversarial check #2 of PREREG-EVL-7's draft (SYNTHETIC ONLY; no lane data, no outcome of any event).

Question: the draft's per-version worst plausible false pass (11.8%) was measured with day-shock persistence
phi_day 0.10 and PREREG-EVL-6's DRAFT screen (looks from block 6, alpha 0.016 / 0.004, unweighted block values,
exhaustion retires). PREREG-EVL-6's fix round (workflows/evl6_fix.js D1, D2, D4) puts phi_day 0.15 and 0.20 into the
PLAUSIBLE grid, makes the block values money-weighted (min(n_s, 14) x (B_s - 10 bp)), and ends a RUN (not the version)
at block 60. This script re-measures the draft's learner (evl7/learner/calib_learner.py, imported unchanged, the
final design) at phi_day 0.15 / 0.20 inside the draft's own worst-plausible corner, under:
  ev6d    the EVL-6 DRAFT screen exactly as calib_evl7.py applies it (one version, exhaustion ends it);
  f6r1    one EVL-6 FINAL-ROUND candidate from evl6/final/shortlist.json ("[8, [[11, 0.016], [20, 0.012], [60, 0.004]]]"),
          money-weighted values, run 1 only;
  f6r12   the same, with D2's run 2 starting at block 61 (the version's false pass within 120 sessions, both runs).
Fresh seeds (91,000,001+). 4 workers.
"""
from __future__ import annotations

import os

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import json  # noqa: E402
import math  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402

import numpy as np  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "learner"))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "calib"))
import calib_learner as cl  # noqa: E402
import calib_evl7 as ce  # noqa: E402

CAP = 14
LOOKS = (6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 18, 20, 22, 25, 30, 35, 40, 50, 60)
F6 = dict(start=8, pieces=((11, 0.016), (20, 0.012), (60, 0.004)), m0=0.0010)


def alpha_of(S):
    lo = 0
    for s_up, a in F6["pieces"]:
        if lo < S <= s_up:
            return a
        lo = s_up
    return 0.0


def screen_f6(sim, rep, start=0):
    """One RUN under the EVL-6 final-round candidate: (passed, session, ended_session or -1)."""
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
        S, N = len(blocks), len(ev_a)
        look = False
        if k < len(LOOKS) and S >= LOOKS[k] and N >= 30 and len(seen) >= 30:
            look = True
            while k < len(LOOKS) and S >= LOOKS[k]:
                k += 1
        if look and S >= F6["start"]:
            alpha = alpha_of(S)
            xb = np.array(blocks)
            ww = np.array(w, float)
            mean_a = sum(ev_a) / N
            neg = -ww * xb
            if mean_a < 0 and cl.zstat(neg) >= cl.Z_PRE and cl.flip_p(neg) <= alpha + cl.TIE:
                return False, -1, t
            x = ww * (xb - F6["m0"])
            if cl.zstat(x) >= cl.Z_PRE and cl.flip_p(x) <= alpha and mean_a > 0 and ev_r_sum / N > 0:
                cm = float(np.mean(ctrl[bsess]))
                if xb.mean() > cm and cl.issuer_p(ev_iss, ev_a, cl.B_ISS6) <= 0.10 + cl.TIE:
                    return True, t, t
        if S >= 60:
            return False, -1, t
    return False, -1, -1


def job(args):
    name, kw, seed, R = args
    t0 = time.time()
    cell = cl.Cell(name, nbar=300, **(cl.WORST | kw | ce.FINAL))
    sim = cl.simulate(cell, seed, R)
    out = {"cell": name, "seed": seed, "R": R, "ev6d": [], "f6r1": [], "f6r12": []}
    for i in range(R):
        ok, _, _ = ce.screen_ev6(sim, i, "ev6d")[:3]
        out["ev6d"].append(int(ok))
        ok1, _, end = screen_f6(sim, i, 0)
        out["f6r1"].append(int(ok1))
        ok2 = ok1
        if not ok1 and end >= 0 and end + 1 < len(sim["B"][i]):
            ok2, _, _ = screen_f6(sim, i, end + 1)
        out["f6r12"].append(int(ok2))
    out["ev_per_session"] = float(sim["n"].mean())
    out["secs"] = round(time.time() - t0, 1)
    return out


def main():
    from multiprocessing import Pool
    reps, chunk = int(sys.argv[1]) if len(sys.argv) > 1 else 800, 100
    cells = [("C2-N1-worst-notau-phi10", dict(tau=0.0, phi_day=0.10)),
             ("C2-N1-worst-notau-phi15", dict(tau=0.0, phi_day=0.15)),
             ("C2-N1-worst-notau-phi20", dict(tau=0.0, phi_day=0.20)),
             ("C2-N1-worst-tau-phi20", dict(phi_day=0.20))]
    jobs = []
    for ci, (name, kw) in enumerate(cells):
        for j in range(reps // chunk):
            jobs.append((name, kw, 91_000_001 + 1000 * ci + j, chunk))
    path = os.path.join(HERE, "check2_phi.jsonl")
    t0 = time.time()
    with Pool(4) as pool, open(path, "w") as fh:
        for k, res in enumerate(pool.imap_unordered(job, jobs)):
            fh.write(json.dumps(res) + "\n")
            fh.flush()
            print(f"{k + 1}/{len(jobs)} {res['cell']} {res['secs']}s total {time.time() - t0:.0f}s", flush=True)
    rows = [json.loads(x) for x in open(path)]
    for name, _ in cells:
        parts = [r for r in rows if r["cell"] == name]
        R = sum(p["R"] for p in parts)
        line = [f"{name:<28} R={R}"]
        for key in ("ev6d", "f6r1", "f6r12"):
            v = np.concatenate([p[key] for p in parts]).mean()
            line.append(f"{key}={v:.4f} (se {math.sqrt(v * (1 - v) / R):.4f})")
        print("  ".join(line))


if __name__ == "__main__":
    main()
