"""taus_tree.py: re-check 1 of PREREG-EVL-9 (SYNTHETIC ONLY). How much of a PERSISTENT ISSUER EFFECT can section 5.1's
tree score g learn from 1,200 history sessions through the static issuer columns alone (ln adv20, ln prev_close,
ln sig20, the four SIC groups), under the registered shape (depth 3, learning rate 0.05, leaf sum(wr) / (sum(w) +
2,000), a split needs >= 2,000 rows and >= 200 distinct issuers a side (checked for the best split only), 32 row
quantile bins a continuous column), and how much of it the forward-chained out-of-fold score keeps?

The generator's issuers (evl7/learner/calib_learner.py `issuers`, unchanged): 3,000 issuers, static issuer columns,
tau_i ~ N(0, tau). History carries tau_h = rho_tau x tau_live + sqrt(1 - rho_tau^2) x tau_indep. An issuer's history rows
n_i come from the lens's Zipf pool draw (nbar a session) over 1,202 sessions in five eras (251, 250, 252, 250, 199);
its era-mean label is tau_h / sig_hat + noise of sd SD_Y / sqrt(n). Features are static per issuer, so a tree on rows
equals the tree on issuer sums (exact gains and leaf values).
Prints: the weighted correlation over pool rows between g (G_full, and g_oof of 2023-2026) and tau_live / sig_hat; the
history slope of the label on g_oof controlling for the static columns; the R*-like curve (25 .. 200 rounds)."""
import math, os, sys, json
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "evl7", "learner"))
import calib_learner as cl

ERAS = (251, 250, 252, 250, 199)
SD_Y = 1.15
LAM, LR, DEPTH, MINW, MINI, NB = 2000.0, 0.05, 3, 2000.0, 200, 32


def pool_counts(rng, iss, nbar, sessions):
    """(U,) expected rows per session of each issuer under the lens's pool law (Gumbel top-n, n ~ Poisson-gamma)."""
    U = cl.U
    cnt = np.zeros(U)
    for _ in range(sessions):
        n = min(int(rng.poisson(nbar * rng.gamma(3.0, 1.0 / 3.0))), U)
        if n == 0:
            continue
        keys = iss["logp"][0] - np.log(-np.log(rng.random(U)))
        ids = np.argpartition(-keys, n - 1)[:n]
        cnt[ids] += 1
    return cnt / sessions


def wquant_edges(v, w, nb):
    o = np.argsort(v)
    cw = np.cumsum(w[o]) / w.sum()
    qs = np.linspace(0, 1, nb + 1)[1:-1]
    e = v[o][np.minimum(np.searchsorted(cw, qs), len(v) - 1)]
    return np.unique(e)


def binize(F, w):
    B = np.zeros(F.shape, dtype=np.int64)
    nbins = []
    for j in range(F.shape[1]):
        col = F[:, j]
        if set(np.unique(col)) <= {0.0, 1.0}:
            B[:, j] = col.astype(np.int64)
            nbins.append(2)
        else:
            e = wquant_edges(col, w, NB)
            B[:, j] = np.searchsorted(e, col, side="right")
            nbins.append(len(e) + 1)
    return B, nbins


def fit_tree(B, nbins, G, W, idx, depth):
    """Returns a list of (indices, value) leaves for the issuers idx."""
    g, wsum = G[idx].sum(), W[idx].sum()
    if depth == 0:
        return [(idx, g / (wsum + LAM))]
    best = None
    base = g * g / (wsum + LAM)
    for j in range(B.shape[1]):
        nb = nbins[j]
        bj = B[idx, j]
        gb = np.bincount(bj, weights=G[idx], minlength=nb)
        wb = np.bincount(bj, weights=W[idx], minlength=nb)
        gl, wl = np.cumsum(gb)[:-1], np.cumsum(wb)[:-1]
        gr, wr = g - gl, wsum - wl
        ok = (wl >= MINW) & (wr >= MINW)
        if not ok.any():
            continue
        gain = np.where(ok, gl * gl / (wl + LAM) + gr * gr / (wr + LAM) - base, -np.inf)
        k = int(np.argmax(gain))
        if gain[k] > 0 and (best is None or gain[k] > best[0] + 1e-15):
            best = (float(gain[k]), j, k)
    if best is None:
        return [(idx, g / (wsum + LAM))]
    _, j, k = best
    L = idx[B[idx, j] <= k]
    Rr = idx[B[idx, j] > k]
    if len(L) < MINI or len(Rr) < MINI:
        return [(idx, g / (wsum + LAM))]
    return fit_tree(B, nbins, G, W, L, depth - 1) + fit_tree(B, nbins, G, W, Rr, depth - 1)


def boost(F, ybar, W, rounds, keep=(25, 50, 100, 150, 200)):
    """Fit on issuers with weights W (rows) and mean labels ybar; return {r: score over the issuers} at keep rounds and
    the scorer for other issuers (static features, so scoring = the same partition)."""
    B, nb = binize(F, W)
    Fh = np.zeros(len(ybar))
    out = {}
    idx = np.arange(len(ybar))
    trees = []
    for r in range(1, rounds + 1):
        G = W * (ybar - Fh)
        leaves = fit_tree(B, nb, G, W, idx, DEPTH)
        for li, v in leaves:
            Fh[li] += LR * v
        if r in keep:
            out[r] = Fh.copy()
    return out


def wcorr(a, b, w):
    am, bm = np.average(a, weights=w), np.average(b, weights=w)
    return float(np.average((a - am) * (b - bm), weights=w) / math.sqrt(np.average((a - am) ** 2, weights=w) *
                                                                         np.average((b - bm) ** 2, weights=w)))


def one(seed, tau, rho_tau, nbar, rounds=200):
    rng = np.random.default_rng(seed)
    iss = cl.issuers(rng, 1, cl.Cell("x", tau=tau, nbar=nbar))
    F = iss["ilev"][0]                       # (U, 7): ln_adv, ln_px, ln_sig, sic0..3
    tl = iss["tau"][0]
    th = rho_tau * tl + math.sqrt(max(0.0, 1 - rho_tau ** 2)) * rng.normal(0, tau, cl.U)
    sh = iss["sig_hat"][0]
    rate = pool_counts(rng, iss, nbar, 300)  # rows a session
    sig_y_l = tl / sh                        # the live issuer effect in label units
    # era rows and era-mean labels
    n_e = np.array([rate * s for s in ERAS])                          # (5, U) expected rows
    n_e = rng.poisson(n_e).astype(float)
    ym = np.where(n_e > 0, th[None] / sh[None] + rng.normal(0, 1, n_e.shape) * SD_Y / np.sqrt(np.maximum(n_e, 1)), 0.0)
    res = {}
    # G_full on all eras
    Wt = n_e.sum(0)
    yt = np.where(Wt > 0, (n_e * ym).sum(0) / np.maximum(Wt, 1), 0.0)
    m = Wt > 0
    full = boost(F[m], yt[m], Wt[m], rounds)
    w_live = rate                            # live pool weight
    for r, sc in full.items():
        g = np.zeros(cl.U)
        g[m] = sc
        res[f"full_r{r}_corr_live"] = wcorr(g, sig_y_l, w_live)
        res[f"full_r{r}_corr_hist"] = wcorr(g, th / sh, w_live)
    # forward-chained g_oof: era k scored by trees on eras < k
    goof = np.zeros((5, cl.U))
    for k in range(1, 5):
        Wk = n_e[:k].sum(0)
        yk = np.where(Wk > 0, (n_e[:k] * ym[:k]).sum(0) / np.maximum(Wk, 1), 0.0)
        mk_ = Wk > 0
        sc = boost(F[mk_], yk[mk_], Wk[mk_], rounds, keep=(rounds,))[rounds]
        goof[k, mk_] = sc
    # the prior's slope of the era label on [static, g_oof] (rows of 2023-2026, weighted), session-demeaned ~ centred
    Xs, ys, ws = [], [], []
    for k in range(1, 5):
        mm = n_e[k] > 0
        Xs.append(np.column_stack([F[mm], goof[k, mm]]))
        ys.append(ym[k, mm])
        ws.append(n_e[k, mm])
    X = np.vstack(Xs); y = np.concatenate(ys); w = np.concatenate(ws)
    sd_oof = math.sqrt(np.average((X[:, -1] - np.average(X[:, -1], weights=w)) ** 2, weights=w))
    X[:, -1] = (X[:, -1] - np.average(X[:, -1], weights=w)) / sd_oof
    Xc = X - np.average(X, axis=0, weights=w)
    yc = y - np.average(y, weights=w)
    A = (Xc * w[:, None]).T @ Xc
    b = (Xc * w[:, None]).T @ yc
    beta = np.linalg.solve(A, b)
    gl = np.zeros(cl.U); gl[m] = full[rounds]
    sd_full = math.sqrt(np.average((gl - np.average(gl, weights=w_live)) ** 2, weights=w_live))
    res.update(dict(beta_g=float(beta[-1]), beta_static=[round(float(x), 4) for x in beta[:-1]],
                    sd_full_over_sd_oof=float(np.std(gl[m]) / sd_oof),
                    oof_corr_live=wcorr(np.concatenate([goof[k] for k in range(1, 5)]),
                                        np.tile(sig_y_l, 4), np.concatenate([n_e[k] for k in range(1, 5)]) + 1e-12),
                    sd_tau_label=float(math.sqrt(np.average(sig_y_l ** 2, weights=w_live))),
                    rows=float(n_e.sum())))
    # the linear static projection's share (in-sample OLS of th/sh on the static columns)
    Fc = F - np.average(F, axis=0, weights=Wt + 1e-12)
    bs = np.linalg.lstsq(Fc * np.sqrt(Wt + 1e-12)[:, None], (th / sh - np.average(th / sh, weights=Wt + 1e-12)) *
                         np.sqrt(Wt + 1e-12), rcond=None)[0]
    res["lin_static_corr_live"] = wcorr(Fc @ bs, sig_y_l, w_live)
    return res


if __name__ == "__main__":
    out = []
    for rho in (1.0, 0.5):
        for s in range(3):
            r = one(762_000_001 + s, 0.01, rho, 450.0)
            r.update(seed=762_000_001 + s, rho_tau=rho)
            out.append(r)
            print(json.dumps({k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()}), flush=True)
