"""SYNTHETIC ONLY. Does training on the BAR-BASIS label (SIP daily open/close) instead of the PRINT-BASIS target
(listing-exchange auction prints, what the judge settles) cost the learner pick quality? A ridge learner (within-
session demeaned, standardized, lambda in weighted rows, as PREREG-EVL-7's draft) is trained on a synthetic history
whose labels carry a basis gap g = bar - print with sd sigma_g (scaled up for illiquid names) and an optional
feature-correlated bias kappa x z_liq; it is scored forward on the print-basis truth: the mean true expected
abnormal return of its top-8 picks a session, and the rank IC of its score with the truth. No real data is read."""
import json, sys
import numpy as np
rng = np.random.default_rng(20261022)
S_TR, S_FW, N, D, K = 1454, 300, 450, 60, 8
SIG_EV, SIG_MU = 0.030, 0.0006          # per-event idio sd 300 bp; sd of the true expected return 6 bp (realistic: R2 ~ 0.04%)
def make(S):
    X = rng.standard_normal((S, N, D))
    return X
beta = rng.standard_normal(D) * (np.arange(D) < 10); beta *= SIG_MU / np.sqrt((beta ** 2).sum())
def returns(X):
    S = X.shape[0]
    mu = X @ beta
    day = 0.006 * rng.standard_normal((S, 1))
    eps = SIG_EV * rng.standard_t(4, size=(S, N)) / np.sqrt(2.0)       # t(4) has variance 2
    return mu, mu + day + eps
def fit(X, y, lam=8000.0):
    Xd = X - X.mean(axis=1, keepdims=True); yd = y - y.mean(axis=1, keepdims=True)
    A = np.einsum("snd,sne->de", Xd, Xd); b = np.einsum("snd,sn->d", Xd, yd)
    d = np.sqrt(np.diag(A) / (X.shape[0] * X.shape[1]))
    M = A / np.outer(d, d) + lam * np.eye(D)
    return np.linalg.solve(M, b / d) / d
def score(Xf, muf, bh):
    s = Xf @ bh
    top = np.argsort(-s, axis=1)[:, :K]
    picked = np.take_along_axis(muf, top, axis=1).mean()
    ic = np.mean([np.corrcoef(s[i], muf[i])[0, 1] for i in range(len(s))])
    return picked * 1e4, ic
Xtr, Xfw = make(S_TR), make(S_FW)
mutr, rtr = returns(Xtr); mufw, _ = returns(Xfw)
zliq = Xtr[:, :, 0]                      # feature 0 plays ln(ADV20): illiquid names (low z) have larger gaps
out = []
oracle = (np.take_along_axis(mufw, np.argsort(-mufw, axis=1)[:, :K], axis=1).mean() * 1e4)
base = score(Xfw, mufw, fit(Xtr, rtr))
out.append({"label": "print", "sigma_g_bp": 0, "kappa_bp": 0, "top8_bp": round(base[0], 2), "ic": round(base[1], 4)})
for sg in (25, 100, 200):
    for kap in (0, 2, 5, 10):
        g = (sg / 1e4) * np.exp(-0.5 * zliq) / np.exp(0.125) * rng.standard_normal(rtr.shape) + (kap / 1e4) * (-zliq)
        res = score(Xfw, mufw, fit(Xtr, rtr + g))
        out.append({"label": "bar", "sigma_g_bp": sg, "kappa_bp": kap, "top8_bp": round(res[0], 2), "ic": round(res[1], 4)})
summary = {"oracle_top8_bp": round(oracle, 2), "sessions_train": S_TR, "events_a_session": N, "features": D,
           "sd_true_mu_bp": SIG_MU * 1e4, "sd_event_bp": SIG_EV * 1e4, "rows": out}
json.dump(summary, open("sim_basis.out.json", "w"), indent=1)
for r in out: print(r)
print("oracle top-8 mean true mu (bp):", round(oracle, 2))
