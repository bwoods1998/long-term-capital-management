#!/usr/bin/env python
"""cal_capacity7.py: SYNTHETIC capacity and cost-scale figures for EXEC-7 (COST-7's fee and impact terms, CAP-7's
participation cap) at the account sizes the plan passes through: $1,898 (today), $5,000, $10,000 and the $30k plan.

SYNTHETIC ONLY. The universe below is a stated assumption, NOT the lane's universe (events.sqlite is never read):
ADV20 lognormal, median $20M, log-sd 1.9, truncated at the lane's $1M floor; events drawn with weight ADV^0.3 (news and
filings concentrate in larger names); sigma60 = 3% x (ADV / $20M)^-0.12 clipped to [0.8%, 12%]; price lognormal median
$30, log-sd 1.0, truncated at the lane's $3 floor. Auction notional priors: open = 1% of ADV, close = 5% of ADV (KAPPA;
replaced at run time by the measured 20-session median of the listing exchange's cross print, marks.qty x px).

Figures per account size E and band (Probe 3.5%, Sized 10%):
- fee bp a round trip, two ways: the per-fill penny ceiling (CAT $0.01 a fill both sides; SEC ceil-cent at $27.80 a
  million; TAF ceil-cent at $0.000166 a share) and the rate-based floor (no rounding: what a day-total-rounded venue
  charges in the limit of many fills);
- impact bp a side, COST-7's term: Y x sigma60 x sqrt(Q / ADV20), Y = 1 (the conservative end of the published
  square-root coefficients; Almgren et al. 2005, Toth et al. 2011);
- CAP-7: the share of events whose target exceeds 2% of the auction notional (open and close), and the mean share of
  the target the cap leaves;
- the cash ceiling of events a session: E / position, one-auction-span holds (each lot holds its cash at two auctions).
Usage: cal_capacity7.py [--n 200000]
"""
from __future__ import annotations

import argparse
import json
import math

import numpy as np

KAPPA = {"open": 0.01, "close": 0.05}
CAP_PART = 0.02
Y = 1.0
SEC = 27.80e-6
TAF = 0.000166
CAT = 0.01
LIMIT = 1.25


def ceil_cent(x):
    return np.ceil(np.round(x * 100.0, 9)) / 100.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=200_000)
    ap.add_argument("--out", default="cal_capacity7.out.json")
    a = ap.parse_args()
    rng = np.random.default_rng(7_500_001)
    pool = 4 * a.n
    adv = np.exp(math.log(20e6) + 1.9 * rng.standard_normal(pool))
    adv = adv[adv >= 1e6]
    w = adv ** 0.3
    pick = rng.choice(adv.size, size=a.n, p=w / w.sum())
    adv = adv[pick]
    sig = np.clip(0.03 * (adv / 20e6) ** -0.12, 0.008, 0.12)
    px = np.exp(math.log(30.0) + 1.0 * rng.standard_normal(a.n * 2))
    px = px[px >= 3.0][: a.n]
    out = {"assumptions": {"adv_median": 20e6, "adv_logsd": 1.9, "event_weight": "ADV^0.3", "kappa": KAPPA,
                           "cap_participation": CAP_PART, "Y": Y, "sec_per_dollar": SEC, "taf_per_share": TAF,
                           "cat_per_fill": CAT},
           "adv_quantiles_of_events": {q: float(np.quantile(adv, q)) for q in (0.1, 0.25, 0.5, 0.75, 0.9)},
           "rows": []}
    for E in (1898.0, 5000.0, 10000.0, 30000.0):
        for band, share in (("probe", 0.035), ("sized", 0.10)):
            q = share * E
            n_sh = np.floor(q / (LIMIT * px))
            fits = (LIMIT * px) <= 0.10 * E          # TRADABLE: one share under the name wall
            n_sh = np.where(n_sh < 1, 1, n_sh)
            one_ok = (n_sh * LIMIT * px) <= 0.05 * E if band == "probe" else np.ones_like(fits)
            ok = fits & one_ok
            N = n_sh * px
            fee_ceiling = (CAT + CAT + ceil_cent(SEC * N) + ceil_cent(np.minimum(TAF * n_sh, 8.30))) / N * 1e4
            fee_rate = (SEC * N + TAF * n_sh) / N * 1e4
            imp = Y * sig * np.sqrt(N / adv) * 1e4
            row = {"E": E, "band": band, "target_usd": q, "tradable_share": float(ok.mean()),
                   "notional_median": float(np.median(N[ok])),
                   "fee_rt_bp_ceiling_median": float(np.median(fee_ceiling[ok])),
                   "fee_rt_bp_ceiling_mean": float(np.mean(fee_ceiling[ok])),
                   "fee_rt_bp_rate_median": float(np.median(fee_rate[ok])),
                   "impact_side_bp_median": float(np.median(imp[ok])), "impact_side_bp_p90": float(np.quantile(imp[ok], 0.9)),
                   "cash_ceiling_events_per_session": E / q}
            for auc, k in KAPPA.items():
                V = k * adv
                capped = N > CAP_PART * V
                left = np.minimum(1.0, CAP_PART * V / N)
                row[f"capped_share_{auc}"] = float(capped[ok].mean())
                row[f"target_left_mean_{auc}"] = float(left[ok].mean())
            out["rows"].append(row)
    with open(a.out, "w") as fh:
        json.dump(out, fh, indent=1)
    for r in out["rows"]:
        print(f"E ${r['E']:>7,.0f} {r['band']:5s} target ${r['target_usd']:>6,.0f}: tradable {r['tradable_share']:.2f} "
              f"fee RT ceil {r['fee_rt_bp_ceiling_median']:.1f} bp (mean {r['fee_rt_bp_ceiling_mean']:.1f}) rate "
              f"{r['fee_rt_bp_rate_median']:.2f} bp | impact/side med {r['impact_side_bp_median']:.2f} p90 "
              f"{r['impact_side_bp_p90']:.2f} bp | capped open {r['capped_share_open']:.3f} close "
              f"{r['capped_share_close']:.3f} (left {r['target_left_mean_open']:.3f}/{r['target_left_mean_close']:.3f}) "
              f"| cash ceiling {r['cash_ceiling_events_per_session']:.0f} events/session")
    print(json.dumps(out["adv_quantiles_of_events"]))


if __name__ == "__main__":
    main()
