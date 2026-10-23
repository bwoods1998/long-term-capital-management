#!/usr/bin/env python
"""rt_done_beta.py (red team; SYNTHETIC ONLY: no lane data, no market data, no outcome of any event is read).

QUESTION: how much of Done's bootstrap item (DONE-RULE-EVL-2 item 4.5: the 95% two-sided issuer-block bootstrap lower
bound of the per-event RAW after-cost return > 0, with realized P&L > 0) is carried by MARKET DIRECTION on a long-only
book, when the issuer-block bootstrap treats a session's events as independent although they share the market's day?

MODEL (per replicate): Probe+ events, N_SESS a session (3 programs x 6 slots = 18), one-session holds; issuers drawn
Zipf(0.8) over 3,000 names (the same names recur). Per event:
    r = alpha + beta_i m_t + c_t + sigma_i e_i      (cost: real fills at the auction print, EXECUTION-FACTS; fees ~0)
    a = r - m_t                                     (benchmark-net, the shadow's a: beta assumed 1)
  m_t  the benchmark's session return: mu + 1.2% h_t eps_t, eps unit t(4), h_t = exp(x_t)/norm, x AR(0.95) sd 0.3
  beta_i ~ U(0.7, 1.7) (small/mid-cap event names), c_t the basket's residual day shock 0.5% unit t(3),
  sigma_i log-uniform 1.5%-6%, e unit t(3).
DONE ITEMS MODELLED: at checkpoints 300, 400, 500, 600 (the first c events): realized P&L > 0 AND the issuer-block LB of
mean r > 0 (cluster-robust normal approximation of the percentile bootstrap, checked against a 2,000-draw percentile
bootstrap on 300 replicates: printed). BESIDE: the same LB with SESSION blocks, and the issuer-block LB of a.
"Done" here = items 4.4 + 4.5 at the first checkpoint where both hold (the program counts, compute, fills and the
captain item are not modelled: every figure is an UPPER bound on Done's probability).
"""
import json, math, sys
import numpy as np

R = int(sys.argv[1]) if len(sys.argv) > 1 else 20000
N_SESS = 18
CHECKS = (300, 400, 500, 600)
T = math.ceil(max(CHECKS) / N_SESS)
G_ISS = 3000


def zipf_probs(n, s=0.8):
    w = 1.0 / np.arange(1, n + 1) ** s
    return w / w.sum()


PZ = zipf_probs(G_ISS)


def unit_t(rng, df, size):
    return rng.standard_t(df, size) / math.sqrt(df / (df - 2))


def lb_cluster(vals, groups, ngroups):
    """mean and the 2.5th-percentile normal approximation under cluster resampling (ratio of sums)."""
    n = vals.size
    mean = vals.mean()
    sums = np.bincount(groups, weights=vals, minlength=ngroups)
    cnts = np.bincount(groups, minlength=ngroups)
    used = cnts > 0
    G = used.sum()
    resid = sums[used] - cnts[used] * mean
    var = (resid ** 2).sum() / n ** 2 * G / max(G - 1, 1)
    return mean, mean - 1.96 * math.sqrt(var)


def lb_boot(vals, groups, draws, rng):
    keys, inv = np.unique(groups, return_inverse=True)
    sums = np.bincount(inv, weights=vals)
    cnts = np.bincount(inv)
    G = keys.size
    pick = rng.integers(0, G, size=(draws, G))
    stats = sums[pick].sum(1) / cnts[pick].sum(1)
    return np.quantile(stats, 0.025)


def one(rng, alpha, mu, check_boot=False):
    x = np.zeros(T)
    x[0] = rng.normal(0, 0.3)
    for t in range(1, T):
        x[t] = 0.95 * x[t - 1] + math.sqrt(1 - 0.95 ** 2) * rng.normal(0, 0.3)
    h = np.exp(x - 0.045)
    m = mu + 0.012 * h * unit_t(rng, 4, T)
    c = 0.005 * unit_t(rng, 3, T)
    n = T * N_SESS
    sess = np.repeat(np.arange(T), N_SESS)
    iss = rng.choice(G_ISS, size=n, p=PZ)
    beta = rng.uniform(0.7, 1.7, n)
    sig = np.exp(rng.uniform(math.log(0.015), math.log(0.06), n))
    r = alpha + beta * m[sess] + c[sess] + sig * unit_t(rng, 3, n)
    r = np.maximum(r, -1.0)
    a = r - m[sess]
    res = {}
    done_at = None
    for cpt in CHECKS:
        rr, ii, ss, aa = r[:cpt], iss[:cpt], sess[:cpt], a[:cpt]
        mean, lb_i = lb_cluster(rr, ii, G_ISS)
        _, lb_s = lb_cluster(rr, ss, T)
        _, lb_a = lb_cluster(aa, ii, G_ISS)
        res[cpt] = (rr.sum() > 0, lb_i > 0, lb_s > 0, lb_a > 0, mean)
        if done_at is None and rr.sum() > 0 and lb_i > 0:
            done_at = cpt
    mkt = float(np.prod(1 + m[:math.ceil(300 / N_SESS)]) - 1)
    out = dict(done_at=done_at, mkt300=mkt, res=res)
    if check_boot:
        rr, ii = r[:300], iss[:300]
        out["boot_vs_normal"] = (float(lb_boot(rr, ii, 2000, rng)), float(lb_cluster(rr, ii, G_ISS)[1]))
    return out


def cell(alpha, mu, seed, reps):
    rng = np.random.default_rng(seed)
    done = 0
    done_s = done_a = 0
    pnl_neg300 = 0
    up = dn = done_up = done_dn = 0
    first = {c: 0 for c in CHECKS}
    for k in range(reps):
        o = one(rng, alpha, mu)
        r300 = o["res"][300]
        pnl_neg300 += (not r300[0])
        if o["mkt300"] > 0:
            up += 1
        else:
            dn += 1
        if o["done_at"] is not None:
            done += 1
            first[o["done_at"]] += 1
            if o["mkt300"] > 0:
                done_up += 1
            else:
                done_dn += 1
            # would the guards have held at that same checkpoint?
            rc = o["res"][o["done_at"]]
            done_s += rc[2]
            done_a += rc[3]
    return dict(alpha_bp=alpha * 1e4, mu_bp=mu * 1e4, reps=reps, p_done_items=done / reps,
                p_done_and_session_lb=done_s / reps, p_done_and_abnormal_lb=done_a / reps,
                p_raw_pnl_negative_at_300=pnl_neg300 / reps,
                p_done_given_market_up=done_up / max(up, 1), p_done_given_market_down=done_dn / max(dn, 1),
                first_checkpoint=first)


if __name__ == "__main__":
    rng = np.random.default_rng(7)
    diffs = []
    for _ in range(300):
        o = one(rng, 0.0, 0.0, check_boot=True)
        b, nrm = o["boot_vs_normal"]
        diffs.append(b - nrm)
    d = np.array(diffs) * 1e4
    print(f"bootstrap(2000) minus normal-approx issuer LB at 300 events: mean {d.mean():+.2f} bp, sd {d.std():.2f} bp")
    rows = []
    seed = 1000
    for alpha in (0.0, 0.0020, 0.0040):
        for mu in (-0.0004, 0.0, 0.0004):
            seed += 1
            row = cell(alpha, mu, seed, R)
            rows.append(row)
            print(json.dumps(row))
    json.dump(dict(R=R, N_SESS=N_SESS, rows=rows, boot_check_bp=dict(mean=float(d.mean()), sd=float(d.std()))),
              open(__file__.replace(".py", ".out.json"), "w"), indent=1)
