#!/usr/bin/env python
"""rc9.py: RE-CHECK 1 of PREREG-EVL-9 (statistics and leakage). SYNTHETIC ONLY: nothing here reads the lane, the
House, the gateway, a vault, a price, a return, a look, a band or a P&L.

It imports the fixer's calibration evl9/final/calib_w9.py UNCHANGED (sha256 23b62992...; the lens generator, the warm and
cold learners, the frozen PREREG-EVL-6 screen) and re-runs its cells on THIS RE-CHECK'S OWN FRESH SEEDS (761,000,001 +,
never used by any earlier EVL-6/7/8/9 stage), plus cells the fixer did not run:
  bind   the six selected cells' worst two on fresh seeds; the LIVE POOL SIZES (the lane's close pool is 420-850
         candidates a session before merging by issuer, the open pool 340-620: SPEED-FACTS via the draft's section 16),
         at nbar 600 and 800 for EVL-WL-ON and 600 for EVL-WL-O1.
  taus   (rc9_taus.py) history that carried the issuer's own persistent effect through the static issuer columns and g.
Usage: rc9.py run --grid bind [--workers 8]  |  rc9.py report [--tag bind]
"""
import argparse, dataclasses, json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "final"))
import numpy as np  # noqa: E402
import calib_w9 as w  # noqa: E402

BASE = dict(shape="crasht3cl", phi_day=0.20, rho_day=0.15, ev_skew=True, tau=0.01)


def grid(name):
    if name == "bind":
        cells = [
            (w.mk(learner="ON", adv="lowvol", adv_k=0.30, drift_sd=0.0020, **BASE), 2000),
            (w.mk(learner="ON", ic_h=0.0, drift_sd=0.0020, **BASE), 1000),
            (w.mk(learner="ON", ic_h=0.0, drift_sd=0.0020, nbar=600.0, **BASE), 1000),
            (w.mk(learner="ON", ic_h=0.0, drift_sd=0.0020, nbar=800.0, **BASE), 1000),
            (w.mk(learner="ON", adv="lowvol", adv_k=0.30, drift_sd=0.0020, nbar=600.0, **BASE), 1000),
            (w.mk(learner="ON", adv="lowvol", adv_k=0.30, drift_sd=0.0020, nbar=800.0, **BASE), 600),
            (w.mk(learner="O1", ic_h=0.0, drift_sd=0.0020, **dict(BASE, tau=0.0)), 600),
            (w.mk(learner="O1", ic_h=0.0, drift_sd=0.0020, nbar=600.0, **BASE), 600),
            (w.mk(learner="ON", ic_h=0.0, tauh=True, drift_sd=0.0020, nbar=800.0, **BASE), 600),
            (w.mk(learner="O1", adv="lowvol", adv_k=0.30, drift_sd=0.0020, nbar=600.0, **BASE), 600),
        ]
        return cells, 761_000_001
    if name == "hd":
        cells = [
            (w.mk(learner="ON", ic_h=0.08, drift_sd=0.0020, **BASE), 400),
            (w.mk(learner="ON", ic_h=0.08, drift_c=0.0010, drift_sd=0.0020, **dict(BASE, shape="crasht3")), 400),
            (w.mk(learner="ON", ic_h=0.08, drift_c=0.0010, drift_sd=0.0020, nbar=600.0, **BASE), 400),
            (w.mk(learner="O1", ic_h=0.05, drift_sd=0.0020, **dict(BASE, shape="crasht3")), 400),
        ]
        return cells, 791_000_001
    if name == "cold":
        cells = [
            (w.mk(learner="ON", hist="cold", drift_sd=0.0020, nbar=600.0, **BASE), 600),
            (w.mk(learner="O1", hist="cold", drift_sd=0.0020, nbar=600.0, **BASE), 400),
            (w.mk(learner="ON", hist="cold", drift_sd=0.0020, nbar=800.0, **BASE), 400),
        ]
        return cells, 795_000_001
    raise SystemExit(name)


def run(gname, workers, chunk=50):
    from multiprocessing import Pool
    cells, seed0 = grid(gname)
    for c, _ in cells:
        w.population(c.learner, c.tau, c.tau_mode)
    jobs = []
    for ci, (c, reps) in enumerate(cells):
        for j in range(reps // chunk):
            jobs.append((c, seed0 + 1000 * ci + j, chunk))
    jobs.sort(key=lambda x: ((x[1] - seed0) % 1000, (x[1] - seed0) // 1000))
    path = os.path.join(HERE, f"rc9.{gname}.jsonl")
    t0 = time.time()
    with Pool(min(8, workers)) as pool, open(path, "w") as fh:
        for k, res in enumerate(pool.imap_unordered(w._job, jobs)):
            fh.write(json.dumps(res) + "\n")
            fh.flush()
            print(f"{gname}: {k + 1}/{len(jobs)} {res['cell']} seed {res['seed']} {res['secs']}s total "
                  f"{time.time() - t0:.0f}s", flush=True)


def report(tag):
    by = {}
    for line in open(os.path.join(HERE, f"rc9.{tag}.jsonl")):
        r = json.loads(line)
        by.setdefault(r["cell"], []).append(r)
    for name, parts in sorted(by.items(), key=lambda kv: -w.summarise(kv[1])["run1"]):
        s = w.summarise(parts)
        print(f"{name:<70} R={s['R']:<5} RUN1 {s['run1']:.4f} (se {s['run1_se']:.4f}) cm<=0 {s['cm0']:.4f} "
              f"cm<=10bp {s['cm10']:.4f} | VERSION by120 {s['v120']:.4f} | ev/s {s['ev_s']:.2f} tau {s['tau_bp']:+.1f}bp "
              f"sig {s['sig']:.3f} guarded/s {s['guarded']:.1f} uhz {s['uhz']:.2f}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("run", "report"))
    ap.add_argument("--grid", default="bind")
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()
    if a.cmd == "run":
        run(a.grid, a.workers)
    else:
        report(a.grid)
