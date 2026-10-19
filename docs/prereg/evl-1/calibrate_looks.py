"""EVL-1 screen calibration (synthetic only, no market data): the per-look one-sided p threshold alpha_look such that
a zero-edge program passes at ANY of the pre-registered looks with probability <= 0.10.
Look k happens at the first session close with S >= S_k sessions AND n >= N_k settled events.
Test at a look: one-sided sign-flip p-value on the session means of after-cost abnormal returns (session blocks).
Null model: session mean = common shock (t, df 4) + idiosyncratic noise / sqrt(events in session); events/session vary.
Run: python3 calibrate_looks.py  (seeded; prints the pinned alpha_look and the measured family FP)."""
import numpy as np
LOOKS = [(10, 60), (15, 90), (20, 120), (30, 180), (40, 240), (60, 360), (90, 540)]
rng = np.random.default_rng(20261019)

def signflip_p(x, flips):
    t0 = x.mean()
    sims = (flips[:, :len(x)] * x).mean(axis=1)
    return (1 + np.sum(sims >= t0 - 1e-15)) / (1 + len(sims))

def run(alpha, reps=4000, rate_mu=6.0, B=999, df=4):
    flips = rng.choice([-1.0, 1.0], size=(B, 200))
    passed = 0
    for _ in range(reps):
        rate = max(0.3, rng.gamma(2.0, rate_mu / 2.0))           # events per session for this program
        S_max = 200
        n_per = rng.poisson(rate, S_max)
        common = rng.standard_t(df, S_max) * 0.004                 # residual common shock per session
        idio = np.array([rng.standard_t(df, k).sum() * 0.03 / max(k, 1) if k else 0.0 for k in n_per])
        means = np.where(n_per > 0, common + idio, np.nan)
        cum_n = np.cumsum(n_per)
        hit = False
        for S_k, N_k in LOOKS:
            idx = np.where((np.arange(1, S_max + 1) >= S_k) & (cum_n >= N_k))[0]
            if not len(idx):
                break
            s = idx[0] + 1
            x = means[:s][~np.isnan(means[:s])]
            if len(x) >= 10 and x.mean() > 0 and signflip_p(x, flips) <= alpha:
                hit = True
                break
        passed += hit
    return passed / reps

if __name__ == "__main__":
    lo, hi = 0.005, 0.10
    for _ in range(9):
        mid = (lo + hi) / 2
        fp = run(mid, reps=1500)
        lo, hi = (mid, hi) if fp <= 0.10 else (lo, mid)
    alpha = round(lo, 4)
    fps = {mu: run(alpha, reps=4000, rate_mu=mu) for mu in (1.0, 6.0, 40.0)}
    print({"alpha_look": alpha, "family_fp_by_event_rate": fps, "looks": LOOKS})
