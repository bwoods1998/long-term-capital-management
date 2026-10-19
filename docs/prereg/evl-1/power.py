import numpy as np, calibrate_looks as C
def run_edge(alpha, edge, rate_mu, reps=2000, B=999, df=4):
    rng = np.random.default_rng(7)
    flips = rng.choice([-1.0, 1.0], size=(B, 200)); passed = 0; first = []
    for _ in range(reps):
        rate = max(0.3, rng.gamma(2.0, rate_mu / 2.0)); S_max = 200
        n_per = rng.poisson(rate, S_max)
        common = rng.standard_t(df, S_max) * 0.004
        idio = np.array([rng.standard_t(df, k).sum() * 0.03 / max(k, 1) if k else 0.0 for k in n_per])
        means = np.where(n_per > 0, common + idio + edge, np.nan); cum_n = np.cumsum(n_per)
        for S_k, N_k in C.LOOKS:
            idx = np.where((np.arange(1, S_max + 1) >= S_k) & (cum_n >= N_k))[0]
            if not len(idx): break
            s = idx[0] + 1; x = means[:s][~np.isnan(means[:s])]
            if len(x) >= 10 and x.mean() > 0 and C.signflip_p(x, flips) <= alpha:
                passed += 1; first.append(s); break
    return round(passed / reps, 3), (int(np.median(first)) if first else None)
for rate in (2.0, 40.0):
    print(rate, {e: run_edge(0.024, e, rate) for e in (0.001, 0.002, 0.004, 0.008)})
