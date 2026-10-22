#!/usr/bin/env python
"""rc9_stress.py: RE-CHECK 1 of PREREG-EVL-9, two named stresses beside the binding set (SYNTHETIC ONLY):
  LV60    the adversarial 'low-volatility names win' prior at twice the fixer's strength (k 0.60);
  LVSTY   the k 0.30 low-volatility prior with a zero-mean AR 0.97 STYLE DRIFT of 10 bp a unit ALONG THAT SAME
          DIRECTION (minus the issuer's ln sig20 column, unit pool sd, pool-demeaned): an own-direction drift for the
          adversarial prior, as CHAR10 is for the decayed-edge prior.
calib_w9 is imported unchanged; for LVSTY only, hist_dirs returns the low-volatility direction as the history index."""
import dataclasses, json, math, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "final"))
import numpy as np  # noqa: E402
import calib_w9 as w  # noqa: E402

LV = set()
_orig_hd = w.hist_dirs


def _hd(c, P):
    wg, bh = _orig_hd(c, P)
    if c.name in LV:
        d = np.zeros(w.D0)
        d[30] = -1.0 / 1.044                    # ln sig20 column: zs + 0.3 N(0,1), sd about 1.044
        return d, bh
    return wg, bh


w.hist_dirs = _hd
BASE = dict(shape="crasht3cl", phi_day=0.20, rho_day=0.15, ev_skew=True, tau=0.01, drift_sd=0.0020)


def cells():
    a = w.mk(learner="ON", adv="lowvol", adv_k=0.60, **BASE)
    b = w.mk(learner="ON", adv="lowvol", adv_k=0.30, drift_c=0.0010, **BASE)
    b = dataclasses.replace(b, name=b.name + "-LVSTY10")
    LV.add(b.name)
    return [(a, 400), (b, 400)], 781_000_001


def _job(args):
    cells()
    return w._job(args)


if __name__ == "__main__":
    from multiprocessing import Pool
    cs, seed0 = cells()
    for c, _ in cs:
        w.population(c.learner, c.tau, c.tau_mode)
    jobs = [(c, seed0 + 1000 * ci + j, 50) for ci, (c, reps) in enumerate(cs) for j in range(reps // 50)]
    t0 = time.time()
    with Pool(8) as pool, open(os.path.join(HERE, "rc9.stress.jsonl"), "w") as fh:
        for k, res in enumerate(pool.imap_unordered(_job, jobs)):
            fh.write(json.dumps(res) + "\n")
            fh.flush()
            print(f"stress: {k + 1}/{len(jobs)} {res['cell']} {res['secs']}s total {time.time() - t0:.0f}s", flush=True)
