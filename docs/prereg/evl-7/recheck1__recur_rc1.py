"""recur_rc1.py: how often a pool candidate's own earlier pool legs sit inside its r20 (SYNTHETIC ONLY; the learner
lens's pool draw, nbar 300, 200 sessions, 4 replicates). Output: recur_rc1.out."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "learner"))
import numpy as np
import calib_learner as cl
rng = np.random.default_rng(258_900_001)
R, T, nbar = 4, 200, 300
cell = cl.Cell("recur", nbar=nbar)
iss = cl.issuers(rng, R, cell)
Nmax = int(nbar * 3.2) + 20
inpool = np.zeros((T, R, cl.U), bool)
cnt = []
for t in range(T):
    n_t = np.minimum(rng.poisson(nbar * rng.gamma(3.0, 1.0 / 3.0, R)), Nmax)
    g = -np.log(-np.log(rng.random((R, cl.U))))
    keys = iss["logp"] + g
    ids = np.argpartition(-keys, Nmax - 1, axis=1)[:, :Nmax]
    order = np.argsort(-np.take_along_axis(keys, ids, axis=1), axis=1)
    ids = np.take_along_axis(ids, order, axis=1)
    for r in range(R):
        inpool[t, r, ids[r, :n_t[r]]] = True
        if t >= 20:
            cnt.extend(inpool[t - 19:t, r, ids[r, :n_t[r]]].sum(axis=0).tolist())
cnt = np.array(cnt)
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "recur_rc1.out"), "w") as fh:
    msg = (f"pool candidates (nbar {nbar}): own earlier pool sessions inside r20's 19 changes: mean {cnt.mean():.2f}, "
           f"median {np.median(cnt):.0f}, share with >= 1: {np.mean(cnt >= 1):.3f}, >= 5: {np.mean(cnt >= 5):.3f}, "
           f">= 10: {np.mean(cnt >= 10):.3f} (n = {cnt.size})")
    print(msg)
    fh.write(msg + "\n")
