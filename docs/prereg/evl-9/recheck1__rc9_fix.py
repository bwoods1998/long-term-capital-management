#!/usr/bin/env python
"""rc9_fix.py: RE-CHECK 1 of PREREG-EVL-9, candidate pick-rule fixes at the worst live-pool cells (SYNTHETIC ONLY).
calib_w9 is imported unchanged; per cell, only (a) the shape guard's threshold (calib_w9.GUARD, read at run time) or
(b) the issuer spacing of section 2.3 (ii) (calib_w9.simulate's `last < t - 5`, rewritten here to `t - SPACING`) differ:
  G20   the shape guard at sigH20 >= 0.020 (registered: 0.015);
  SP20  an issuer is eligible to be picked only when the learner picked it in none of the 20 sessions before D
        (registered: 5)."""
import dataclasses, inspect, json, os, sys, textwrap, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "final"))
import numpy as np  # noqa: E402
import calib_w9 as w  # noqa: E402

src = textwrap.dedent(inspect.getsource(w.simulate))
assert src.count("< t - 5)") == 1
src = src.replace("def simulate(", "def simulate_sp(").replace("< t - 5)", "< t - SPACING)")
w.SPACING = 5
exec(compile(src, "calib_w9_simulate_sp", "exec"), w.__dict__)
w.simulate = w.simulate_sp
FIX: dict = {}
BASE = dict(shape="crasht3cl", phi_day=0.20, rho_day=0.15, ev_skew=True, tau=0.01, drift_sd=0.0020, nbar=600.0)


def cells():
    out = []
    for c0 in (w.mk(learner="ON", adv="lowvol", adv_k=0.30, **BASE), w.mk(learner="ON", ic_h=0.0, **BASE),
               w.mk(learner="O1", adv="lowvol", adv_k=0.30, **BASE)):
        for tag, guard, sp in (("G20", 0.020, 5), ("SP20", 0.015, 20)):
            c = dataclasses.replace(c0, name=c0.name + "-" + tag)
            FIX[c.name] = (guard, sp)
            out.append((c, 400))
    return out, 799_000_001


def cells2():
    """fix2: more programs for SP20 at the two worst cells (fresh seeds 799,100,001 +), and SP20's power price at the
    fixer's power cells (warm rho 1, ic 0.05, the base model; EVL-WL-O1 pool 300, EVL-WL-ON pool 600)."""
    out = []
    for c0 in (w.mk(learner="ON", adv="lowvol", adv_k=0.30, **BASE), w.mk(learner="O1", adv="lowvol", adv_k=0.30, **BASE)):
        c = dataclasses.replace(c0, name=c0.name + "-SP20")
        FIX[c.name] = (0.015, 20)
        out.append((c, 400))
    PB = dict(null="A", ic=0.05, ic_h=0.05, rho_h=1.0, shape="t3", rho_day=0.05, phi_day=0.10, ev_skew=False,
              drift_sd=0.0, tau=0.0)
    for L, pool in (("O1", 300.0), ("ON", 600.0)):
        c0 = w.mk(learner=L, nbar=pool, **PB)
        for tag, sp in (("SP05", 5), ("SP20", 20)):
            c = dataclasses.replace(c0, name=c0.name + "-" + tag)
            FIX[c.name] = (0.015, sp)
            out.append((c, 200))
    return out, 799_100_001


def _job(args):
    cells()
    cells2()
    c = args[0]
    w.GUARD, w.SPACING = FIX[c.name]
    return w._job(args)


if __name__ == "__main__":
    from multiprocessing import Pool
    two = len(sys.argv) > 1 and sys.argv[1] == "fix2"
    cs, seed0 = cells2() if two else cells()
    for c, _ in cs:
        w.population(c.learner, c.tau, c.tau_mode)
    jobs = [(c, seed0 + 1000 * ci + j, 50) for ci, (c, reps) in enumerate(cs) for j in range(reps // 50)]
    jobs.sort(key=lambda x: ((x[1] - seed0) % 1000, (x[1] - seed0) // 1000))
    t0 = time.time()
    with Pool(8) as pool, open(os.path.join(HERE, "rc9.fix2.jsonl" if two else "rc9.fix.jsonl"), "w") as fh:
        for k, res in enumerate(pool.imap_unordered(_job, jobs)):
            fh.write(json.dumps(res) + "\n")
            fh.flush()
            print(f"fix: {k + 1}/{len(jobs)} {res['cell']} {res['secs']}s total {time.time() - t0:.0f}s", flush=True)
