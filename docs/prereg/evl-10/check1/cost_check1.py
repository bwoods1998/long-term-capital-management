#!/usr/bin/env python
"""cost_check1.py (ADVERSARIAL CHECK #1, PREREG-EVL-11's cost and fill rules; SYNTHETIC ONLY: no store, House,
gateway, price, return, look, band, mark or bar is read). Three things, each on synthetic fill gaps only:

  M  THE MARGIN RATCHET (draft section 3): m = max(5 bp, the largest value EVER reached by mean + 1.645 sd / sqrt(n)
     of the lane's last 50 real gaps on that side), recomputed at each nightly settlement. Reading A: from n >= 2 gaps
     (the text sets no minimum); reading B: only once n >= 30. Gaps i.i.d. mean mu, sd sigma, unit t(3) or normal.
     Reported: the margin after 5 / 20 / 60 / 120 sessions (median, p90) against the true mean gap mu.
  H  THE EXECUTION HOLD (draft section 4.5): after every real fill on a side, the last 30 fills' signed mean gap above
     +10 bp or below -10 bp stops new entries for the rest of the session and the next; a third hold within 20
     sessions stops real entries for good (until a House release). 6 entries a session at learning, exits of the lots
     bought; exit gaps mean 0, sd 5 bp. Reported: P(entries stopped for good by session 60 / 120) and the share of
     sessions with entries allowed.
  F  THE FEES (draft section 3's f and PREREG-EVL-1 section 5's fee term): penny fees per order (CAT $0.01 a side,
     TAF $0.01 and the SEC fee rounded up to $0.01 on a sale, as league/fees.py and score.py describe them), on the
     learning lots (whole shares of a 2% target, one share when that rounds to none) and on PREREG-EVL-1's Probe
     notional N = 5% of equity, at E = $1,900 (BUYABLE: 1.25 x price <= 5% E, so price <= $76), prices $5-$76.
Usage: cost_check1.py  (single process; writes cost_check1.out)
"""
import json
import math
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
rng = np.random.default_rng(265_000_001)
OUT = []


def say(s=""):
    print(s)
    OUT.append(s)


def gaps(n, mu, sd, fat):
    if fat:
        x = rng.standard_t(3, n) / math.sqrt(3.0)
    else:
        x = rng.standard_normal(n)
    return mu + sd * x


# ---------------------------------------------------------------------------------------------- M: margin ratchet
say("M  THE MARGIN RATCHET: margin (bp) after k sessions, 6 real gaps a session on the side, 2,000 lanes a cell")
say("   cell (mu, sd, tails)       | reading A (n >= 2): k=5 / 20 / 60 / 120 median [p90] | reading B (n >= 30): 20 / 120")
L, PER, T = 2000, 6, 120
for mu in (0.0, 3.0):
    for sd in (5.0, 10.0, 20.0, 30.0):
        for fat in (False, True):
            mA = np.full(L, 5.0)
            mB = np.full(L, 5.0)
            snapA, snapB = {}, {}
            hist = np.zeros((L, 0))
            for t in range(1, T + 1):
                hist = np.concatenate([hist, gaps(L * PER, mu, sd, fat).reshape(L, PER)], axis=1)[:, -50:]
                n = hist.shape[1]
                if n >= 2:
                    ub = hist.mean(axis=1) + 1.645 * hist.std(axis=1, ddof=1) / math.sqrt(n)
                    mA = np.maximum(mA, ub)
                    if (t * PER) >= 30:
                        mB = np.maximum(mB, ub)
                if t in (5, 20, 60, 120):
                    snapA[t] = (float(np.median(mA)), float(np.quantile(mA, 0.9)))
                    snapB[t] = (float(np.median(mB)), float(np.quantile(mB, 0.9)))
            a = " / ".join(f"{snapA[k][0]:.1f} [{snapA[k][1]:.1f}]" for k in (5, 20, 60, 120))
            b = " / ".join(f"{snapB[k][0]:.1f}" for k in (20, 120))
            say(f"   mu {mu:+.0f} sd {sd:>4.0f} {'t3 ' if fat else 'nrm'}            | {a} | {b}")
say("   (the margin a lane should charge is about mu; every bp above it is charged to every later event of the seat")
say("    and of its control, for good)")

# ---------------------------------------------------------------------------------------------- H: execution hold
say("")
say("H  THE EXECUTION HOLD: P(real entries stopped for good) by session 60 / 120, share of sessions with entries")
say("   allowed over 120; 6 entries a session; 2,000 lanes a cell; entry gaps mean mu sd sigma (t(3)); exit gaps 0, 5 bp")
L = 2000
for mu in (0.0, 3.0, 6.0):
    for sd in (10.0, 20.0, 30.0, 40.0):
        stop60 = stop120 = 0
        allowed = 0
        for lane in range(L):
            ent, ex = [], []
            held_until = -1
            holds = []
            stopped_at = None
            for t in range(1, 121):
                if stopped_at is not None or t <= held_until:
                    continue
                allowed += 1
                bought = 0
                for _ in range(6):
                    if t <= held_until:
                        break
                    ent.append(mu + sd * rng.standard_t(3) / math.sqrt(3.0))
                    bought += 1
                    w = ent[-30:]
                    if len(w) == 30 and abs(sum(w) / 30.0) > 10.0:
                        holds.append(t); held_until = t + 1
                for _ in range(bought):
                    ex.append(5.0 * rng.standard_t(3) / math.sqrt(3.0))
                    w = ex[-30:]
                    if len(w) == 30 and abs(sum(w) / 30.0) > 10.0 and held_until < t + 1:
                        holds.append(t); held_until = t + 1
                recent = [h for h in holds if h > t - 20]
                if len(recent) >= 3 and stopped_at is None:
                    stopped_at = t
            if stopped_at is not None and stopped_at <= 60:
                stop60 += 1
            if stopped_at is not None:
                stop120 += 1
        say(f"   mu {mu:+.0f} sd {sd:>3.0f}: stopped for good by 60 {stop60 / L:.3f}, by 120 {stop120 / L:.3f}; "
            f"sessions with entries {allowed / (L * 120):.3f}")

# --------------------------------------------------------------------------------------------------------- F: fees
say("")
say("F  THE FEES at E = $1,900 (penny fees: CAT $0.01 a side; TAF $0.01 and the SEC fee rounded up to $0.01 on a sale)")
E = 1900.0
prices = np.round(np.arange(5.0, 76.01, 0.01), 2)
target = 0.02 * E
sh = np.floor(target / prices)
sh = np.where(sh < 1, 1, sh)
proc = sh * prices
rt = 0.04 / proc * 1e4
sale = 0.03 / proc * 1e4
N = 0.05 * E
say(f"   learning lots (2% target ${target:.0f}, whole shares): proceeds ${proc.min():.2f}-${proc.max():.2f}; "
    f"round-trip penny fees {rt.min():.1f}-{rt.max():.1f} bp (median {np.median(rt):.1f}); sale-side fees over "
    f"proceeds up to {sale.max():.1f} bp (the draft's f ratchets to this maximum)")
say(f"   PREREG-EVL-1's convention at the Probe notional N = ${N:.0f}: entry {0.01 / N * 1e4:.2f} bp, exit "
    f"{0.02 / N * 1e4:.2f} bp (+0.5 bp a side): {0.03 / N * 1e4 + 1.0:.2f} bp a round trip; with the SEC cent "
    f"{0.04 / N * 1e4 + 1.0:.2f} bp")
say(f"   the draft's replay before any posted sale: entry 0 bp of fees, exit f = 0.30 bp -> under-charged by "
    f"{0.03 / N * 1e4 + 1.0 - 0.30:.1f}-{0.04 / N * 1e4 + 1.0 - 0.30:.1f} bp a round trip against PREREG-EVL-1's "
    f"basis; after the first small learning sale f locks at up to {sale.max():.1f} bp, over-charged by about "
    f"{sale.max() - 0.02 / N * 1e4:.1f} bp on every later event")
with open(os.path.join(HERE, "cost_check1.out"), "w") as fh:
    fh.write("\n".join(OUT) + "\n")


# ------------------------------------------------------------------------- H2: the hold, three readings, entry side
def hold_lane(mu, sd, variant, T=120, per=6):
    ent, held_until, holds, stopped, first_hold, allowed = [], -1, [], None, None, 0
    for t in range(1, T + 1):
        if stopped is not None or t <= held_until:
            continue
        allowed += 1
        for _ in range(per):
            if t <= held_until:
                break
            ent.append(mu + sd * rng.standard_t(3) / math.sqrt(3.0))
            if variant == "fill":
                w = ent[-30:]
                if len(w) == 30 and abs(sum(w) / 30.0) > 10.0:
                    holds.append(t); held_until = t + 1
                    first_hold = first_hold or t
        if variant in ("close", "close_t") and len(ent) >= 30:
            w = np.array(ent[-30:])
            m = w.mean(); s = w.std(ddof=1)
            hit = abs(m) > 10.0 and (variant == "close" or abs(m) / (s / math.sqrt(30)) >= 2.5)
            if hit:
                holds.append(t); held_until = t + 1
                first_hold = first_hold or t
        if len([h for h in holds if h > t - 20]) >= 3 and stopped is None:
            stopped = t
    return stopped, first_hold, allowed


say("")
say("H2 THE HOLD, entry side only, three readings: 'fill' = the draft (after every fill), 'close' = once at each")
say("   session's close, 'close_t' = once at each close and also |t| >= 2.5; 1,000 lanes a cell, 6 entries a session")
for mu, sd in ((0.0, 5.0), (0.0, 10.0), (0.0, 20.0), (3.0, 20.0), (0.0, 30.0), (15.0, 20.0), (20.0, 20.0)):
    row = []
    for variant in ("fill", "close", "close_t"):
        res = [hold_lane(mu, sd, variant) for _ in range(1000)]
        st = sum(1 for s, _, _ in res if s is not None and s <= 120) / 1000.0
        h20 = sum(1 for _, f, _ in res if f is not None and f <= 20) / 1000.0
        row.append(f"{variant}: stop-for-good by 120 {st:.3f}, a hold by 20 {h20:.3f}")
    say(f"   mu {mu:+.0f} sd {sd:>3.0f} | " + " | ".join(row))
with open(os.path.join(HERE, "cost_check1.out"), "w") as fh:
    fh.write("\n".join(OUT) + "\n")
