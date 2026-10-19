"""EVL-3 screen calibration (synthetic only, no market data): the per-look one-sided p threshold alpha_look such that a
zero-edge program passes at ANY of the pre-registered EVENT-COUNT looks with probability <= 0.10.
Look k happens at the first session close at which the program has >= N_k settled events AND >= MIN_BLOCKS session
blocks (sessions with at least one event). Test at a look: one-sided sign-flip p-value on the session means of
after-cost abnormal returns (session blocks), as PREREG-EVL-1 section 7. Null: session mean = residual common shock
(t, df 4, scale 0.4%) + idiosyncratic noise (t, df 4, 3% an event) / events in the session; events per session vary.
Run: python3 calibrate_events.py (seeded)."""
import numpy as np
NS = [60, 90, 135, 200, 300, 450, 675, 1000, 1500, 2250]  # the pinned schedule (calib_variants.py, seeds 11-13)
MIN_BLOCKS = 8
rng = np.random.default_rng(20261019 + 3)

def signflip_p(x, flips):
    t0 = x.mean()
    sims = (flips[:, :len(x)] * x).mean(axis=1)
    return (1 + np.sum(sims >= t0 - 1e-15)) / (1 + len(sims))

def run(alpha, reps=4000, rate_mu=6.0, B=999, df=4, edge=0.0, min_blocks=MIN_BLOCKS, ns=NS, seed=None):
    r = rng if seed is None else np.random.default_rng(seed)
    flips = r.choice([-1.0, 1.0], size=(B, 400))
    passed, first = 0, []
    for _ in range(reps):
        rate = max(0.3, r.gamma(2.0, rate_mu / 2.0))
        S_max = 400
        n_per = r.poisson(rate, S_max)
        common = r.standard_t(df, S_max) * 0.004
        idio = np.array([r.standard_t(df, k).sum() * 0.03 / max(k, 1) if k else 0.0 for k in n_per])
        means = np.where(n_per > 0, common + idio + edge, np.nan)
        cum_n = np.cumsum(n_per)
        blocks = np.cumsum(n_per > 0)
        for N_k in ns:
            idx = np.where((cum_n >= N_k) & (blocks >= min_blocks))[0]
            if not len(idx):
                break
            s = idx[0] + 1
            x = means[:s][~np.isnan(means[:s])]
            if x.mean() > 0 and signflip_p(x, flips) <= alpha:
                passed += 1
                first.append(s)
                break
    return passed / reps, (int(np.median(first)) if first else None)

if __name__ == "__main__":
    import json, sys
    lo, hi = 0.005, 0.06
    for _ in range(9):
        mid = (lo + hi) / 2
        fp = max(run(mid, reps=1500, rate_mu=mu)[0] for mu in (6.0, 40.0))
        lo, hi = (mid, hi) if fp <= 0.095 else (lo, mid)
    alpha = round(lo, 4)
    fps = {mu: run(alpha, reps=4000, rate_mu=mu)[0] for mu in (1.0, 6.0, 40.0, 150.0)}
    power = {f"{mu}@{e}": run(alpha, reps=1500, rate_mu=mu, edge=e) for mu in (6.0, 40.0) for e in (0.002, 0.004, 0.008)}
    print(json.dumps({"alpha_look": alpha, "family_fp_by_event_rate": fps, "power_and_median_session": power,
                      "looks": NS, "min_blocks": MIN_BLOCKS}))
