#!/usr/bin/env python
"""demotion_px_c1b.py: ADVERSARIAL CHECK #1 of PREREG-EVL-8: the PX seats' demotion FIX measured beside the inherited
fixed reads. SYNTHETIC ONLY (the PX designer's generator, unchanged). A promoted seat buys its first m = 14 events a
session in rank order; r = a + m_t. At the stay's 100th, 200th, ... Probe event:
  DRAFT  demote when the cumulative mean r < 0 (PREREG-EVL-6 draft section 3, item 3, copied by THE PX SCREEN);
  FIX    demote when the one-sided session-block sign-flip p for a mean BELOW zero of the blocks' mean r over ALL the
         stay's Probe events so far is <= 0.20 (EVL-6 check 1's proposal; exact <= 16 blocks, else 19,999 vectors).
Edges 0 (no edge after cost), 40, 60, 100 bp at base / mid / worst. Seeds 65,000,001 on. Usage: demotion_px_c1b.py
"""
import json, os, sys
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "price")))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..", "evl7", "learner")))
import px_calib as PX
import calib_learner as CL
M = 14
def run(noise, mu, R, seed):
    rng = np.random.default_rng(seed)
    dd = df = 0
    done = 0
    while done < R:
        b = min(200, R - done)
        g = PX.generate(rng, b, 40, PX.NOISE[noise], mu, 0.0, 40)
        for i in range(b):
            ev, blk = [], []
            hit_d = hit_f = False
            for t in range(PX.T):
                rv = g["r"][i, t][g["valid"][i, t]][:M]
                if len(rv) == 0:
                    continue
                before = len(ev)
                ev.extend(rv.tolist()); blk.append(float(rv.mean()))
                for k in range((before // 100 + 1) * 100, len(ev) + 1, 100):
                    if k > 1000:
                        break
                    if not hit_d and sum(ev[:k]) / k < 0:
                        hit_d = True
                    if not hit_f:
                        x = -np.array(blk)
                        if CL.zstat(x) >= 0.5 and CL.flip_p(x) <= 0.20:
                            hit_f = True
                if len(ev) >= 1000:
                    break
            dd += hit_d; df += hit_f
        done += b
    return round(dd / R, 3), round(df / R, 3)
seed = 65_000_001
for noise in ("base", "mid", "worst"):
    for mu in (0.0, 0.0040, 0.0060, 0.0100):
        d, f = run(noise, mu, 2000, seed); seed += 1
        print(json.dumps({"noise": noise, "edge_bp": mu * 1e4, "probe_events_a_session": M, "R": 2000,
                          "P_demoted_by_1000th_event_DRAFT_fixed_reads": d, "P_demoted_by_1000th_event_FIX_signflip_p020": f}), flush=True)
