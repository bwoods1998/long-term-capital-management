#!/usr/bin/env python
"""oof_w9.py: SYNTHETIC measure of the captain's W6 (check 2's major 5): the ridge prior's weight on the tree score g
when g's out-of-fold values come from FIVE CONTIGUOUS FOLDS (the judge's draft: a 2022 row scored by a model fitted on
2023-2026) against FORWARD-CHAINED folds (a row of era k scored by a model fitted on eras before k only; 2022 rows g = 0),
and what each delivers on a later live era. No lane data: eras, features and labels are drawn here.

Model: 5 history eras (2022-2026) and one live era, ROWS rows each, D features x ~ N(0, I); the label y = x . b_k +
f(x) . c_k + noise, b_k and c_k (a linear part and an interaction part f(x) = x_i x_j of 6 fixed pairs) drift across
eras as an AR(1) in era steps with innovation share a (a = 0: a fixed structure; a = 0.6: most of it renewed each
era); signal-to-noise set so the in-era information coefficient is about 0.08. THE TREE STAND-IN: a ridge on x and f(x)
(a tree's job here: the interactions), fitted per fold. THE PRIOR: a ridge of y on (x, g_oof) over every history row (the
registered prior's role), its coefficient on g reported; LIVE: g = the full-history fit's score on the live era, the
prediction x . beta_x + g . beta_g, its correlation with the live label (the live IC) reported, and the live IC of the
past-only score itself.
Usage: oof_w9.py   (writes oof_w9.out.json)
"""
import json
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROWS, D, ERAS, REPS = 20_000, 10, 5, 40
PAIRS = [(0, 1), (2, 3), (4, 5), (1, 6), (7, 8), (3, 9)]


def basis(x):
    f = np.stack([x[:, i] * x[:, j] for i, j in PAIRS], axis=1)
    return np.concatenate([x, f], axis=1)


def ridge(X, y, lam):
    return np.linalg.solve(X.T @ X + lam * np.eye(X.shape[1]), X.T @ y)


def one(rng, a):
    b = rng.normal(0, 1, D)
    c = rng.normal(0, 1, len(PAIRS))
    eras = []
    for k in range(ERAS + 1):
        if k:
            b = np.sqrt(1 - a * a) * b + a * rng.normal(0, 1, D)
            c = np.sqrt(1 - a * a) * c + a * rng.normal(0, 1, len(PAIRS))
        x = rng.normal(0, 1, (ROWS, D))
        sig = basis(x) @ np.concatenate([b, c])
        sig = sig / sig.std() * 0.08
        y = sig + rng.normal(0, 1, ROWS) * np.sqrt(1 - 0.08 ** 2)
        eras.append((x, y, sig))
    hist, (xl, yl, sl) = eras[:ERAS], eras[ERAS]
    out = {}
    lam = 2000.0
    for scheme in ("contiguous", "forward"):
        goof = []
        for k in range(ERAS):
            if scheme == "contiguous":
                tr = [j for j in range(ERAS) if j != k]
            else:
                tr = list(range(k))
            if not tr:
                goof.append(np.zeros(ROWS))
                continue
            Xt = np.concatenate([basis(hist[j][0]) for j in tr])
            yt = np.concatenate([hist[j][1] for j in tr])
            w = ridge(Xt, yt, lam)
            goof.append(basis(hist[k][0]) @ w)
        g = np.concatenate(goof)
        X = np.concatenate([h[0] for h in hist])
        y = np.concatenate([h[1] for h in hist])
        mask = np.ones(len(g), bool) if scheme == "contiguous" else np.concatenate(
            [np.zeros(ROWS, bool)] + [np.ones(ROWS, bool)] * (ERAS - 1))
        gm, gs = g[mask].mean(), g[mask].std()
        gz = np.where(mask, (g - gm) / gs, 0.0)
        beta = ridge(np.concatenate([X, gz[:, None]], axis=1), y, 8000.0)
        wfull = ridge(np.concatenate([basis(h[0]) for h in hist]), y, lam)
        gl = (basis(xl) @ wfull - gm) / gs
        pred = xl @ beta[:D] + gl * beta[D]
        out[scheme] = dict(beta_g=float(beta[D]), live_ic=float(np.corrcoef(pred, yl)[0, 1]),
                           g_hist_ic=float(np.corrcoef(g[mask], y[mask])[0, 1]))
    out["score_live_ic"] = float(np.corrcoef(basis(xl) @ wfull, yl)[0, 1])
    return out


def main():
    rng = np.random.default_rng(20261022_6)
    res = {}
    for a in (0.0, 0.3, 0.6):
        runs = [one(rng, a) for _ in range(REPS)]
        res[f"a{a}"] = {s: {k: round(float(np.mean([r[s][k] for r in runs])), 5) for k in runs[0][s]}
                        for s in ("contiguous", "forward")}
        res[f"a{a}"]["full_score_live_ic"] = round(float(np.mean([r["score_live_ic"] for r in runs])), 5)
        res[f"a{a}"]["reps"] = REPS
    print(json.dumps(res, indent=1))
    json.dump(res, open(os.path.join(HERE, "oof_w9.out.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
