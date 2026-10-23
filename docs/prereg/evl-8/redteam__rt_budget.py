#!/usr/bin/env python
"""rt_budget.py (red team; SYNTHETIC ONLY: no lane data, no market data, no outcome or P&L of any event is read).

QUESTION: how often does the owner's loss budget ($400 net in any 20 sessions as its WORST NET STRETCH, $800 net in
total from the ledger's inception; realized plus every open position at the open-risk weight, league/live/money.py and
constitution.py) cut Probe entries in the six weeks (30 sessions) ahead, when the event book is long-only and nearly
fully invested in learning lots whose real-money P&L carries market beta (and maybe an attention penalty) but counts for
nothing in Done; and what does thinning the learning book buy?

BOOK (per replicate, per session t = 1..30; one-session holds, the House's mix of open and close entries collapsed to
one book a session): E0 = $1,898 (SPEED-FACTS). Probe from session P0 = 9 (first possible promotions ~Oct 29-Nov 2):
3 programs x 6 slots x $67 (3.5% of E, rounded up as SUP-1); learning lots of $38 (2% of E) fill the rest of the cash up to
LEARN_SHARE x E (usable cash 0.95 E; A85: Probe first). Open-risk weight 0.10 a lot (max(0.10, 1.65 sigma sqrt(h)) with
sigma ~3-4%: the floor binds). An entry needs window room 400 - W_t - open risk and total room (800 - U0) - Tot_t -
open risk; the book shrinks (Probe last) to fit; no room: no entry.
P&L of a lot: v (alpha_band + beta m_t + c_t + sigma e), beta 1.2, c_t 0.5% unit t(3), sigma 4% (idiosyncratic sum
taken normal over the lots); m_t = mu + 1.2% h_t eps_t (t(4), vol regime AR(0.95) sd 0.3).
Measured: P(any Probe entry cut by the budget), Probe lots lost (share of 18 x 22 sessions), P(the $800 total binds:
'stop all spend'), the realized P&L of the 30 sessions (mean, 5th pct), and Net after compute (metered compute
$3.36 a day, reader cost_model.out 'with_house_fixed', over 42 calendar days = $141).
"""
import json, math, sys
import numpy as np

R = int(sys.argv[1]) if len(sys.argv) > 1 else 20000
T, P0, WIN = 30, 9, 20
E0, LOT_L, LOT_P, N_P = 1898.0, 38.0, 67.0, 18
W_OPEN = 0.10
COMPUTE = 3.36 * 42


def unit_t(rng, df, size):
    return rng.standard_t(df, size) / math.sqrt(df / (df - 2))


def run(learn_share, aL, aP, mu, U0, seed, reps=R, sm=0.012, auto=False):
    rng = np.random.default_rng(seed)
    x = np.zeros((reps, T))
    x[:, 0] = rng.normal(0, 0.3, reps)
    for t in range(1, T):
        x[:, t] = 0.95 * x[:, t - 1] + math.sqrt(1 - 0.95 ** 2) * rng.normal(0, 0.3, reps)
    m = mu + sm * np.exp(x - 0.045) * unit_t(rng, 4, (reps, T))
    c = 0.005 * unit_t(rng, 3, (reps, T))
    E = np.full(reps, E0)
    cum = np.zeros(reps)
    closes = np.zeros((reps, T))
    cut = np.zeros(reps, bool)
    lost = np.zeros(reps)
    stopped = np.zeros(reps, bool)
    for t in range(T):
        lo = max(0, t - WIN + 1)
        # worst net stretch of the window's closes before t: max over s of -(sum of closes s..t-1)
        if t > lo:
            seg = closes[:, lo:t][:, ::-1].cumsum(1)
            W = np.maximum(0.0, -seg.min(1))
        else:
            W = np.zeros(reps)
        Tot = np.maximum(0.0, -cum)
        stopped |= Tot >= (800.0 - U0) - 1e-9
        room = np.minimum(400.0 - W, (800.0 - U0) - Tot)
        room = np.where(stopped, 0.0, room)
        max_value = np.maximum(0.0, room) / W_OPEN
        want_p = N_P * LOT_P if t >= P0 else 0.0
        cash = 0.95 * E
        vp = np.minimum(want_p, np.minimum(cash, max_value))
        if t >= P0:
            short = want_p - vp
            cut |= short > 1e-9
            lost += short / LOT_P
        share_t = np.where(W > 200.0, 0.10, learn_share) if auto else learn_share   # AUTO: tighten-only at half the window
        vl_want = np.maximum(0.0, np.minimum(share_t * E, cash - vp))
        vl = np.minimum(vl_want, np.maximum(0.0, max_value - vp))
        nL = vl / LOT_L
        nP = vp / LOT_P
        common = np.clip(1.2 * m[:, t] + c[:, t], -0.3, 0.3)   # a 30% basket day caps the t tails
        idio = 0.04 * np.sqrt(nL * LOT_L ** 2 + nP * LOT_P ** 2) * rng.standard_normal(reps)
        pnl = vl * (aL + common) + vp * (aP + common) + idio
        closes[:, t] = pnl
        cum += pnl
        E = E0 + cum
    probe_total = N_P * (T - P0)
    return dict(auto=auto, learn_share=learn_share, alpha_learn_bp=aL * 1e4, alpha_probe_bp=aP * 1e4, mu_bp=mu * 1e4, U0=U0,
                sigma_m=sm, p_probe_cut=float(cut.mean()), probe_lost_share=float(lost.mean() / probe_total),
                p_total_stop=float(stopped.mean()), pnl_mean=float(cum.mean()), pnl_p05=float(np.quantile(cum, 0.05)),
                net_mean=float(cum.mean() - COMPUTE), p_net_negative=float((cum - COMPUTE < 0).mean()),
                p_pnl_negative=float((cum < 0).mean()))


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[2] == "auto":
        rows = []
        print("AUTO = learning share 0.25, tightened to 0.10 while the window's worst stretch exceeds $200")
        for mu in (0.0, -0.0033):
            for aL in (0.0, -0.0020):
                for share, auto in ((0.95, False), (0.25, False), (0.25, True)):
                    r = run(share, aL, 0.0, mu, 0.0, 900 + int(auto) + int(share * 100) + int(-mu * 1e5) + int(-aL * 1e5), auto=auto)
                    rows.append(r)
                    print(f"mu {mu*1e4:+4.0f} aL {aL*1e4:+4.0f} share {share:.2f} auto {auto!s:5s} | P(probe cut) {r['p_probe_cut']:.3f} "
                          f"lost {r['probe_lost_share']:.3f} | P&L mean {r['pnl_mean']:+7.1f} p05 {r['pnl_p05']:+7.1f}")
        json.dump(dict(R=R, rows=rows), open(__file__.replace(".py", ".auto.out.json"), "w"), indent=1)
        sys.exit(0)
    rows = []
    seed = 500
    print("share aL  aP   mu   U0  sm  | P(probe cut) lost  P(stop) | P&L mean  p05 | Net mean P(Net<0) P(P&L<0)")
    for U0 in (0.0, 300.0):
        for mu in (0.0, -0.0033):
            for aL, aP in ((0.0, 0.0), (-0.0010, 0.0), (-0.0020, 0.0), (0.0, 0.0020), (-0.0010, 0.0020)):
                for share in (0.95, 0.5, 0.25, 0.10):
                    seed += 1
                    for sm in ((0.012, 0.016) if (U0 == 0 and mu == 0 and aL == 0 and aP == 0) else (0.012,)):
                        r = run(share, aL, aP, mu, U0, seed, sm=sm)
                        rows.append(r)
                        print(f"{share:.2f} {aL*1e4:+4.0f} {aP*1e4:+3.0f} {mu*1e4:+4.0f} {U0:4.0f} {sm:.3f} | "
                              f"{r['p_probe_cut']:.3f} {r['probe_lost_share']:.3f} {r['p_total_stop']:.3f} | "
                              f"{r['pnl_mean']:+7.1f} {r['pnl_p05']:+7.1f} | {r['net_mean']:+7.1f} "
                              f"{r['p_net_negative']:.3f} {r['p_pnl_negative']:.3f}")
    json.dump(dict(R=R, rows=rows), open(__file__.replace(".py", ".out.json"), "w"), indent=1)
