"""sim_g2_ranks.py -- SYNTHETIC: how often PREREG-EVL-9's G2 feature test ("every feature column equal within 1e-9
(relative) on at least 90% of rows" on matched candidates) can hold for its within-session RANK columns
((rank - 0.5) / n over the session's kept candidates, ties at mean rank), when the history kept set and the House's kept
set of a session differ by a few names (G2 itself admits Jaccard down to 0.90). No real data: candidate quantities are
drawn at random (integer headline lengths 20-200, article counts Poisson, so ties occur as in the real columns)."""
import json
import numpy as np

def ranks(v):
    order = np.argsort(v, kind="mergesort")
    r = np.empty(len(v)); r[order] = np.arange(1, len(v) + 1)
    # ties at their mean rank
    vals, inv = np.unique(v, return_inverse=True)
    sums = np.bincount(inv, weights=r); cnt = np.bincount(inv)
    return ((sums / cnt)[inv] - 0.5) / len(v)

def one(rng, n, jac, kind):
    # live set of n; history drops k and adds k others so Jaccard = (n-k)/(n+k)
    k = int(round(n * (1 - jac) / (1 + jac)))
    if kind == "hl":
        q = rng.integers(20, 200, size=n + k).astype(float)
    else:
        q = rng.poisson(2.0, size=n + k).astype(float)
    live = np.arange(n); drop = rng.choice(n, size=k, replace=False)
    hist = np.concatenate([np.setdiff1d(live, drop), np.arange(n, n + k)])
    rl = dict(zip(live, ranks(q[live]))); rh = dict(zip(hist, ranks(q[hist])))
    common = np.intersect1d(live, hist)
    eq = [abs(rl[i] - rh[i]) <= 1e-9 * max(1.0, abs(rl[i]), abs(rh[i])) for i in common]
    return float(np.mean(eq))

def main():
    rng = np.random.default_rng(20261022)
    out = {}
    for n in (300, 600):
        for jac in (1.0, 0.995, 0.99, 0.98, 0.95, 0.90):
            for kind in ("hl", "count"):
                vals = [one(rng, n, jac, kind) for _ in range(200)]
                out[f"n{n}|jaccard{jac}|{kind}"] = round(float(np.mean(vals)), 4)
    print(json.dumps(out, indent=1))
    json.dump(out, open(__file__.replace(".py", ".out.json"), "w"), indent=1)

main()
