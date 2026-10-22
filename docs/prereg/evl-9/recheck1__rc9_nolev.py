#!/usr/bin/env python
"""rc9_nolev.py: RE-CHECK 1 of PREREG-EVL-9 (SYNTHETIC ONLY): the worst live-pool cells with the two LEVELS deleted,
ln(adv20 / 1e7) and ln(prev_close / 20) (the lens's columns 28-29), as PREREG-EVL-7's newest text (sha256 2f2cff59...,
section 1.4 items 10-11) deletes them for its cold learners, so this file's W1 ('drop ... any feature built from the
issuer's own past returns or prices beyond what PREREG-EVL-7's frozen-or-final text keeps') reaches them. The columns
are set to 0 in every session the learner sees (the population covariance included), which is the same fit as removing
them; the truth, the costs and everything else are calib_w9's, imported unchanged. Cells with -SP20 also apply the
20-session issuer spacing of rc9_fix.py."""
import dataclasses, inspect, json, os, sys, textwrap, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "final"))
import numpy as np  # noqa: E402
import calib_w9 as w  # noqa: E402

src = textwrap.dedent(inspect.getsource(w.simulate))
src = src.replace("def simulate(", "def simulate_sp(").replace("< t - 5)", "< t - SPACING)")
w.SPACING = 5
exec(compile(src, "calib_w9_simulate_sp", "exec"), w.__dict__)
w.simulate = w.simulate_sp
_orig = w.Gen.session


def _session(self, wh_dir, P):
    s = _orig(self, wh_dir, P)
    s["X"][..., 28:30] = 0.0
    return s


w.Gen.session = _session
SP: dict = {}
BASE = dict(shape="crasht3cl", phi_day=0.20, rho_day=0.15, ev_skew=True, tau=0.01, drift_sd=0.0020)


def cells():
    out = []
    for c0, reps in ((w.mk(learner="ON", adv="lowvol", adv_k=0.30, nbar=600.0, **BASE), 600),
                     (w.mk(learner="O1", adv="lowvol", adv_k=0.30, nbar=600.0, **BASE), 400),
                     (w.mk(learner="ON", ic_h=0.0, nbar=600.0, **BASE), 400),
                     (w.mk(learner="O1", ic_h=0.0, **BASE), 400)):
        c = dataclasses.replace(c0, name=c0.name + "-NOLEV")
        SP[c.name] = 5
        out.append((c, reps))
    c0 = w.mk(learner="ON", adv="lowvol", adv_k=0.30, nbar=600.0, **BASE)
    c = dataclasses.replace(c0, name=c0.name + "-NOLEV-SP20")
    SP[c.name] = 20
    out.append((c, 400))
    return out, 798_000_001


def _job(args):
    cells()
    w.SPACING = SP[args[0].name]
    return w._job(args)


if __name__ == "__main__":
    from multiprocessing import Pool
    cs, seed0 = cells()
    for c, _ in cs:
        w.population(c.learner, c.tau, c.tau_mode)
    jobs = [(c, seed0 + 1000 * ci + j, 50) for ci, (c, reps) in enumerate(cs) for j in range(reps // 50)]
    jobs.sort(key=lambda x: ((x[1] - seed0) % 1000, (x[1] - seed0) // 1000))
    t0 = time.time()
    with Pool(8) as pool, open(os.path.join(HERE, "rc9.nolev.jsonl"), "w") as fh:
        for k, res in enumerate(pool.imap_unordered(_job, jobs)):
            fh.write(json.dumps(res) + "\n")
            fh.flush()
            print(f"nolev: {k + 1}/{len(jobs)} {res['cell']} {res['secs']}s total {time.time() - t0:.0f}s", flush=True)
