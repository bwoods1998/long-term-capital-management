#!/usr/bin/env python
"""rt_meta.py (red team; SYNTHETIC ONLY: no lane data, no market data, no outcome of any event is read).

Breaks a META-LEARNER (Hedge over F pre-registered record sub-rules, filling K = 8 real slots a session from the
best-weighted sub-rule) three ways the selection-from-noise argument ("its forward picks are forward, so the screen's
FP holds") does not cover:
  (1) INFORMATIVE CENSORING BY SETTLEMENT: a sub-rule's crash events (halts, missing prints: PREREG-EVL-1 section 5's
      fallback exits) settle 1-6 sessions late; a learner that consumes whatever has settled sees the crash-prone
      sub-rules' good blocks on time and their crashes late;
  (2) BETA SELECTION: a learner scoring RAW returns (or a = r - b with beta assumed 1) in a market with a persistent
      regime drift prefers high-beta sub-rules;
  (3) DILUTION: with F sub-rules and ONE that carries +30 bp an event (abnormal), how often the picks pass the screen
      within 30 pick blocks.
SUB-RULE f, session t (block of its events; the picks are K = 8 of them):
  B_ft = alpha_f + beta_f m_t + c_t + g_{fam(f),t} + s_f u_ft / sqrt(K) + jumps_ft
  m_t = D_t + 1.2% eps_t (t(4)), D_t AR(0.97) regime drift, stationary sd 15 bp; c_t 0.5% (t(3)) common residual;
  g: 8 families' day shocks 0.6% (t(3)); s_f log-uniform 2%-6%; beta_f U(0.6, 1.8);
  jumps: each of the K events crashes -30% with prob lam_f (lam_f 0 for 70% of sub-rules, else U(0.5%, 3%)); the crash
  part of a block settles 1 + Geom(0.4) (cap 6) sessions after the rest.
  WORLDS: NULL (alpha_f = -lam_f x 30% x 1 so every sub-rule's mean a is EXACTLY 0: jumps compensated);
          LOTTERY (crash-prone sub-rules' mean a is -15 bp: compensation 85%: the lottery-stock finding, e.g. Bali,
          Cakici and Whitelaw 2011, JFE, in sign only); POWER (NULL + one sub-rule at +30 bp).
LEARNERS (decision at t sees blocks of sessions <= t - 2): weights w_f ~ exp(eta sum_s z_fs), eta 0.15, z clipped
  to [-3, 3] in units of an assumed block sd 1%; warm-up 5 settled sessions; pick = argmax w (worst case for the
  winner's curse). Scores:
  RAWP  raw B_ft, PARTIAL consumption (each block's settled part when it settles);
  ABNP  a = B_ft - m_t demeaned by the session's mean over sub-rules, PARTIAL;
  ABNC  the same score, SESSION-COMPLETE consumption: session s enters only when every sub-rule's block of s has
        settled, or 3 sessions past due (an unsettled crash is then imputed at -30% each, pessimistic).
SCREEN (the pick record, on a = r - m_t, no control: the knife-edge reading): EVL-6's leading 10%-cap candidate as
calib_learner.py states it: looks at pick blocks S in {7,...,12,14,16,18,20,25,30}; RETIRE first when mean a < 0 and the
lower-tail sign-flip p <= 0.01; PASS when p(mean(B - 10 bp) > 0) <= 0.01, mean a > 0, mean r > 0 (the issuer guard
and the 30-issuer minimum are not modelled: they only lower a pass rate). Sign-flip p: 4,000 fixed vectors, computed
where z >= 1.5. MONEY: the pick record's mean a and raw r (bp), the picks' mean beta and crash rate.
"""
import json, math, sys, time
import numpy as np

T, LAG, WARM, K, ETA = 40, 2, 5, 8, 0.15
LOOKS = (7, 8, 9, 10, 11, 12, 14, 16, 18, 20, 25, 30)
NV = 4000
SIGNS = np.random.default_rng(99).choice([-1.0, 1.0], size=(NV, max(LOOKS)))


def unit_t(rng, df, size):
    return rng.standard_t(df, size) / math.sqrt(df / (df - 2))


def signflip_p(x):
    """one-sided p of mean(x) > 0 over fixed sign vectors (ties against)."""
    S = x.size
    obs = x.sum()
    sims = SIGNS[:, :S] @ x
    return (1 + np.count_nonzero(sims >= obs - 1e-12)) / (1 + NV)


def screen(a_blocks, r_blocks):
    """(passed, retired, at) over the look schedule."""
    for S in LOOKS:
        if a_blocks.size < S:
            break
        a, r = a_blocks[:S], r_blocks[:S]
        if a.mean() < 0:
            z = -a.sum() / math.sqrt((a * a).sum())
            if z >= 1.5 and signflip_p(-a) <= 0.01 + 1e-12:
                return False, True, S
        x = a - 0.0010
        z = x.sum() / math.sqrt((x * x).sum())
        if z >= 1.5 and a.mean() > 0 and r.mean() > 0 and signflip_p(x) <= 0.01 + 1e-12:
            return True, False, S
    return False, False, None


def replicate(rng, F, world, learners):
    fam = rng.integers(0, 8, F)
    beta = rng.uniform(0.6, 1.8, F)
    s = np.exp(rng.uniform(math.log(0.02), math.log(0.06), F))
    lam = np.where(rng.random(F) < 0.7, 0.0, rng.uniform(0.005, 0.03, F))
    comp = 0.85 if world == "LOTTERY" else 1.0
    alpha = lam * 0.30 * comp
    if world == "POWER":
        lam[0] = 0.0
        alpha[0] = 0.0030
    D = np.zeros(T)
    D[0] = rng.normal(0, 0.0015)
    for t in range(1, T):
        D[t] = 0.97 * D[t - 1] + math.sqrt(1 - 0.97 ** 2) * rng.normal(0, 0.0015)
    m = D + 0.012 * unit_t(rng, 4, T)
    c = 0.005 * unit_t(rng, 3, T)
    g = 0.006 * unit_t(rng, 3, (8, T))
    nj = rng.binomial(K, np.repeat(lam[:, None], T, 1))           # crashes in the K-event block
    jump = -0.30 * nj / K
    lagj = np.where(nj > 0, np.minimum(1 + rng.geometric(0.4, (F, T)), 7), 0)
    base = alpha[:, None] + beta[:, None] * m[None, :] + c[None, :] + g[fam] + \
        (s[:, None] / math.sqrt(K)) * unit_t(rng, 3, (F, T))
    B = base + jump                                               # the block's true raw value
    A = B - m[None, :]                                            # benchmark-net (beta assumed 1)
    out = {}
    for L in learners:
        score = np.zeros(F)
        picks = []
        added_base = np.zeros((F, T), bool)
        added_jump = np.zeros((F, T), bool)
        complete_upto = -1
        for d in range(T):
            ready = d - LAG                                       # sessions <= ready have settled their normal part
            if L in ("RAWP", "ABNP"):
                for sidx in range(max(0, ready - 8), ready + 1):
                    if sidx < 0:
                        continue
                    if not added_base[0, sidx]:
                        val = base[:, sidx] if L == "RAWP" else base[:, sidx] - m[sidx]
                        if L == "ABNP":
                            val = val - val.mean()
                        score += np.clip(val / 0.01, -3, 3)
                        added_base[:, sidx] = True
                    due = (~added_jump[:, sidx]) & (nj[:, sidx] > 0) & (sidx + lagj[:, sidx] <= ready)
                    if due.any():
                        jv = jump[:, sidx]
                        if L == "ABNP":
                            jv = jv - jv.mean() * 0          # the crash part enters when it settles (no re-demeaning)
                        score[due] += np.clip(jv[due] / 0.01, -3, 3)
                        added_jump[due, sidx] = True
            else:  # ABNC/ABNU: a session enters only when complete (or 3 sessions past due, crashes imputed at -30%)
                while complete_upto + 1 <= ready:
                    sidx = complete_upto + 1
                    pending = (nj[:, sidx] > 0) & (sidx + lagj[:, sidx] > ready)
                    if pending.any() and sidx + 3 > ready:
                        break
                    val = A[:, sidx].copy()                        # crashes settled, or imputed at -30% (= their value)
                    val = val - val.mean()
                    score += np.clip(val / 0.01, -3, 3) if L == "ABNC" else val / 0.01
                    complete_upto = sidx
            nseen = (ready + 1) if L in ("RAWP", "ABNP") else (complete_upto + 1)
            if nseen < WARM:
                continue
            w = ETA * score
            f = int(np.argmax(w))
            picks.append((d, f))
        a_bl = np.array([A[f, t] for t, f in picks])
        r_bl = np.array([B[f, t] for t, f in picks])
        passed, retired, at = screen(a_bl, r_bl)
        pf = np.array([f for _, f in picks])
        out[L] = dict(passed=passed, retired=retired, at=at, mean_a=float(a_bl[:30].mean()),
                      mean_r=float(r_bl[:30].mean()), beta=float(beta[pf].mean()), lam=float(lam[pf].mean()),
                      true_share=float((pf == 0).mean()) if world == "POWER" else None, n=int(a_bl.size))
    return out


def cell(F, world, reps, seed, learners=("RAWP", "ABNP", "ABNC", "ABNU")):
    rng = np.random.default_rng(seed)
    agg = {L: dict(passed=0, retired=0, mean_a=0.0, mean_r=0.0, beta=0.0, lam=0.0, true_share=0.0) for L in learners}
    for _ in range(reps):
        o = replicate(rng, F, world, learners)
        for L in learners:
            for k in ("passed", "retired"):
                agg[L][k] += o[L][k]
            for k in ("mean_a", "mean_r", "beta", "lam"):
                agg[L][k] += o[L][k]
            if o[L]["true_share"] is not None:
                agg[L]["true_share"] += o[L]["true_share"]
    res = {}
    for L in learners:
        a = agg[L]
        res[L] = dict(pass_rate=a["passed"] / reps, retire_rate=a["retired"] / reps,
                      picks_mean_a_bp=1e4 * a["mean_a"] / reps, picks_mean_r_bp=1e4 * a["mean_r"] / reps,
                      picks_beta=a["beta"] / reps, picks_crash_rate=a["lam"] / reps,
                      true_rule_share=(a["true_share"] / reps) if world == "POWER" else None)
    return res


if __name__ == "__main__":
    reps = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
    cells = [(F, w) for w in ("NULL", "LOTTERY", "POWER") for F in (50, 200, 800)]
    if len(sys.argv) > 2:
        cells = [c for c in cells if f"{c[1]}-{c[0]}" in sys.argv[2].split(",")]
    from multiprocessing import Pool
    t0 = time.time()
    args = [(F, w, reps, 7000 + i) for i, (F, w) in enumerate(cells)]
    with Pool(4) as pool:
        results = pool.starmap(cell, args)
    rows = []
    for (F, w), res in zip(cells, results):
        row = dict(F=F, world=w, reps=reps, **res)
        rows.append(row)
        for L, v in res.items():
            ts = "" if v["true_rule_share"] is None else f" true-rule share {v['true_rule_share']:.3f}"
            print(f"{w:8s} F={F:4d} {L}: pass {v['pass_rate']:.3f} retire {v['retire_rate']:.3f} | picks a "
                  f"{v['picks_mean_a_bp']:+6.1f} bp r {v['picks_mean_r_bp']:+6.1f} bp beta {v['picks_beta']:.2f} "
                  f"crash {v['picks_crash_rate']*100:.2f}%{ts}")
    print(f"{time.time() - t0:.0f}s")
    json.dump(rows, open(__file__.replace(".py", ".out.json"), "w"), indent=1)
