#!/usr/bin/env python
"""rt_skew_final.py (the EVL-9 judge): the red team's skew cells (evl9/redteam/rt_skew.py, its generator imported
unchanged) screened by PREREG-EVL-6's FINAL rule (calib_evl9_final.run_f: looks from the 9th block, alpha 0.012 / 0.010
/ 0.004, money-weighted values, RETIRE, the guards; run 1 within 120 sessions). SYNTHETIC ONLY: every event's mean a is
exactly 0. Answers: is R12's shape guard (no pick below sigma20 = 1.5%) still needed under the final rule?"""
import json, math, os, sys
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "redteam"))
sys.path.insert(0, HERE)
import rt_skew as rs  # noqa: E402
import calib_evl9_final as cf  # noqa: E402

CELLS = [c for c in rs.CELLS + rs.CELLS2 + rs.CELLS3 if "steamroller" in c["name"] or c["name"] in ("SYM",)]


def gen(c, reps, seed):
    rng = np.random.default_rng(seed)
    m1, s1 = rs.moments(c["left"], c["right"])
    T, K, NI = rs.T, rs.K, rs.NI
    out = dict(B=np.zeros((reps, T)), Rm=np.zeros((reps, T)), n=np.zeros((reps, T), dtype=np.int16),
               ctrl=np.zeros((reps, T)), iss=np.full((reps, T, K), -1, dtype=np.int32), a=np.full((reps, T, K), np.nan))
    logp = -0.8 * np.log(np.arange(1, NI + 1, dtype=float))
    p = np.exp(logp) / np.exp(logp).sum()
    for rep in range(reps):
        lo, hi = c.get("sig", (0.03, 0.08))
        sig = np.exp(rng.uniform(math.log(lo), math.log(hi), NI))
        sig_sym = np.exp(rng.uniform(math.log(0.03), math.log(0.08), NI))
        sd_c = math.sqrt(0.05 / 0.95) * math.sqrt(lo * hi)
        for t in range(T):
            n = int(rng.integers(3, K + 1))
            ids = rng.choice(NI, size=n, replace=False, p=p)
            e = (rs.two_piece(rng, n, c["left"], c["right"]) - m1) / s1
            jmp = np.where(rng.random(n) < c["pj"], np.where(rng.random(n) < c["q"], c["J"], -c["J"]), 0.0)
            jmp = jmp - c["pj"] * c["J"] * (2 * c["q"] - 1)
            ct = sd_c * rs.cl.unit_t3(rng, 1)[0]
            sg = sig[ids]
            if c.get("mix") is not None:
                steam = rng.random(n) < c["mix"]
                sg = np.where(steam, sg, sig_sym[ids])
                jmp = np.where(steam, jmp, 0.0)
            a = np.maximum(sg * e + ct + jmp, -1.0)
            bt = rng.normal(0.0004, 0.01)
            out["B"][rep, t] = a.mean()
            out["Rm"][rep, t] = (a + bt).mean()
            out["n"][rep, t] = n
            out["ctrl"][rep, t] = ct + 0.05 * rng.standard_normal() / math.sqrt(300)
            out["iss"][rep, t, :n] = ids
            out["a"][rep, t, :n] = a
    return out


def main():
    reps = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
    rows = []
    for i, c in enumerate(CELLS):
        sim = gen(c, reps, 196_000_001 + i)
        ps = [cf.run_f(sim, r, 0)[0] == "pass" for r in range(reps)]
        p = float(np.mean(ps))
        row = dict(cell=c["name"], reps=reps, ev6f_run1_pass=round(p, 4), se=round(math.sqrt(p * (1 - p) / reps), 4))
        rows.append(row)
        print(json.dumps(row), flush=True)
    with open(os.path.join(HERE, "rt_skew_final.out.jsonl"), "w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


if __name__ == "__main__":
    main()
