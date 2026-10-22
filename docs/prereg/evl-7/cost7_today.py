#!/usr/bin/env python
"""cost7_today.py: COST-7's round trip (PREREG-EVL-7 section 2.1, at its warm-up: M = 2.5 bp a side, G = 0, fees at the
penny ceiling) against the replay's (league/events/score.py cost_bp), on a grid of prices, ADVs and volatilities, at
three equities. Arithmetic only: no lane data, no price of any event.

The replay a side: 0.5 bp + 5 bp (ADV >= $10M) or 10 bp + fees $0.01 / N (CAT) and, on the sale, $0.01 / N more (TAF),
N = 5% of equity. COST-7 a side: M 2.5 + IMP + FEE, IMP = 1e4 x sigma x sqrt(0.10 E / ADV), FEE at n_ref =
max(1, floor(0.035 E / (1.25 p))) shares: entry $0.01 / N_in, exit ($0.01 + ceilcent(27.80e-6 N_out) +
ceilcent(min(0.000166 n_ref, 8.30))) / N_out, N = n_ref x p (the entry and exit print taken equal to p).
"""
import math

PRICES = (5, 10, 20, 40, 80, 150)
ADVS = (1.5e6, 3e6, 6e6, 1.2e7, 3e7, 1e8, 5e8)
SIGMAS = (0.02, 0.04)


def ceilcent(x):
    return math.ceil(round(x * 100, 9)) / 100.0


def replay_rt(adv, E):
    n = 0.05 * E
    imp = 5.0 if adv >= 1e7 else 10.0
    return 2 * (0.5 + imp) + (0.01 / n + 0.02 / n) * 1e4


def cost7_rt(p, adv, sigma, E):
    nref = max(1, math.floor(0.035 * E / (1.25 * p)))
    N = nref * p
    fee_in = 0.01 / N * 1e4
    fee_out = (0.01 + ceilcent(27.80e-6 * N) + ceilcent(min(0.000166 * nref, 8.30))) / N * 1e4
    imp = 1e4 * sigma * math.sqrt(0.10 * E / adv)
    return 2 * 2.5 + 2 * imp + fee_in + fee_out


def main():
    for E in (1898.0, 5000.0, 30000.0):
        print(f"E = ${E:,.0f}: replay round trip {replay_rt(2e7, E):.1f} bp (ADV >= $10M), {replay_rt(5e6, E):.1f} bp (thinner)")
        print("   price  " + " ".join(f"ADV {a / 1e6:>5.1f}M" for a in ADVS) + "   (COST-7 round trip, bp, sigma 2% / 4%)")
        tradable = [p for p in PRICES if 1.25 * p <= 0.10 * E]
        for p in tradable:
            cells = []
            for a in ADVS:
                cells.append(f"{cost7_rt(p, a, 0.02, E):>4.1f}/{cost7_rt(p, a, 0.04, E):<4.1f}")
            print(f"   ${p:<5} " + " ".join(f"{c:>10}" for c in cells))
        for label, sel in (("ADV >= $10M", [a for a in ADVS if a >= 1e7]), ("ADV < $10M", [a for a in ADVS if a < 1e7])):
            d = [replay_rt(a, E) - cost7_rt(p, a, s, E) for p in tradable for a in sel for s in SIGMAS]
            print(f"   replay minus COST-7, {label}: mean {sum(d) / len(d):+.1f} bp, range {min(d):+.1f} to {max(d):+.1f}")


if __name__ == "__main__":
    main()
