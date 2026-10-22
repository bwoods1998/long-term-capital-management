#!/usr/bin/env python
"""fees_and_requests.py: OUTCOME-FREE arithmetic for the price-event lane (PX) design (lens: price).

Nothing here reads the House, the gateway, events.sqlite, live.sqlite or any market data: no price, bar, volume, return
or outcome of any symbol. Inputs are the stated fee schedule (EXECUTION-FACTS.md's SEC fee ~0.28 bp; the schedule
goal-2026-10-19/evl7/exec/cal_capacity7.py states: SEC $27.80 a million ceil-cent, FINRA TAF $0.000166 a share ceil-cent
capped at $8.30, CAT $0.01 a fill as the upper bound), the frozen replay cost of PREREG-EVL-1 section 5
(league/events/score.py cost_bp), the account equity of SPEED-FACTS.md ($1,898), the bands (learning 2%, Probe 3.5%,
one share up to 5%, Sized 10%), and the Basic data plan's stated limits (league/data_plan.py: 200 requests a minute;
league/events/universe.py: 200 symbols a bars request; 10,000 rows a page). Universe sizes are SCENARIOS (the only
measured bound is count_universe.py's 6,041 listed issuers); the House measures N_U on its first pass.

Usage: fees_and_requests.py
"""
import math

E = 1898.0
SEC = 27.80e-6
TAF = 0.000166
TAF_MAX = 8.30
CAT = 0.01


def ceil_cent(x):
    return math.ceil(round(x * 100.0, 9)) / 100.0


def shares_for(target, price, cap_share=0.05):
    n = math.floor(target / price)
    if n == 0 and price <= cap_share * E:
        n = 1
    return n


def fee_rt_bp(notional, n_sh):
    return (CAT + CAT + ceil_cent(SEC * notional) + ceil_cent(min(TAF * n_sh, TAF_MAX))) / notional * 1e4


def replay_rt_bp(adv_liquid=True, equity=E):
    probe_n = 0.05 * equity
    impact = 5.0 if adv_liquid else 10.0
    entry = 0.5 + impact + 0.01 / probe_n * 1e4
    exit_ = 0.5 + impact + 0.02 / probe_n * 1e4
    return entry, exit_, entry + exit_


print("== FEES A ROUND TRIP (bp of the lot), whole shares, E = $%.0f ==" % E)
print("%-26s %8s %8s %8s %8s %8s" % ("lot (band)", "$8", "$20", "$50", "$150", "rate-only"))
for label, target, cap in (("learning 2% ($38)", 0.02 * E, 0.05), ("Probe 3.5% ($66)", 0.035 * E, 0.05),
                           ("Probe 5% ($95)", 0.05 * E, 0.05), ("Sized 10% ($190)", 0.10 * E, 0.10),
                           ("$30k Probe 3.5% ($1,050)", 1050.0, 1.0), ("$30k Sized 10% ($3,000)", 3000.0, 1.0)):
    cells = []
    for px in (8.0, 20.0, 50.0, 150.0):
        n = shares_for(target, px, cap) if target < 1000 else math.floor(target / px)
        if n == 0:
            cells.append("   skip")
            continue
        cells.append("%8.1f" % fee_rt_bp(n * px, n))
    rate = (SEC * target + TAF * (target / 20.0)) / target * 1e4
    print("%-26s %s %8.2f" % (label, " ".join(cells), rate))
en, ex, rt = replay_rt_bp(True)
en2, ex2, rt2 = replay_rt_bp(False)
print("\nPREREG-EVL-1 s5 replay cost (score.py cost_bp), ADV20 >= $10M: entry %.2f + exit %.2f = %.2f bp RT" % (en, ex, rt))
print("PREREG-EVL-1 s5 replay cost, ADV20 < $10M:  entry %.2f + exit %.2f = %.2f bp RT" % (en2, ex2, rt2))
print("Auction fills: no spread inside a cross (EXECUTION-FACTS: 84 of 84 fills at the replay's print, 0.0 bp).")

print("\n== DATA REQUESTS A SESSION (SIP via the gateway's GET /v1/alpaca/v2/stocks/bars; Basic plan 200 a minute) ==")
print("%-58s %7s %7s %7s %7s" % ("read (when)", "N=2000", "N=3000", "N=4500", "N=6041"))
SCEN = (2000, 3000, 4500, 6041)


def row(label, f):
    vals = [f(n) for n in SCEN]
    print("%-58s %s" % (label, " ".join("%7d" % v for v in vals)))
    return vals


backfill = row("one-time backfill, 270 sessions, raw + all (once)",
               lambda n: 2 * math.ceil(n / 200) * math.ceil(200 * 270 / 10000))
daily = row("nightly 1Day bars of the session, raw + all (16:20 ET)", lambda n: 2 * math.ceil(n / 200))
morning = row("D's morning re-read of P's bar, adjustment=all (09:05 ET)", lambda n: math.ceil(n / 200))
pre = row("premarket 1Min 08:00-08:59, GAP universe ~N/2 (09:15 ET)", lambda n: math.ceil((n / 2) / 100))
m1530 = row("px1530 marks, 1Min 15:00-15:30, all N (15:46 ET)", lambda n: math.ceil(n / 100))
gapmin = row("OPENGAP records: D's 09:30 1Min bar, all N (10:00 ET)", lambda n: math.ceil(n / 200))
surge = row("SURGE volume, 1Min 09:30-15:30, <= 300 candidates (15:46 ET)", lambda n: 3 * 4)
prints = row("auction prints: 3 seats x K 40 + 2 control samples x 60, 2 prints, 1.5 pages", lambda n: int((120 + 120) * 2 * 1.5))
tot = [d + m + p + s + q + pr + g for d, m, p, s, q, pr, g in zip(daily, morning, pre, m1530, surge, prints, gapmin)]
print("%-58s %s" % ("TOTAL a session (excluding the one-time backfill)", " ".join("%7d" % v for v in tot)))
print("%-58s %s" % ("minutes of the plan's 200/min allowance", " ".join("%7.1f" % (v / 200.0) for v in tot)))
print("%-58s %s" % ("peak at the 15:46 ET close decision (requests)", " ".join("%7d" % (a + b) for a, b in zip(m1530, surge))))
print("%-58s %s" % ("peak at the 09:15 ET open decision (requests)", " ".join("%7d" % (a + b) for a, b in zip(morning, pre))))
print("\nSEC operating-company test (EDGAR company feed, cached 30 days, 1-3 reads a CIK):")
for n in SCEN:
    print("  N=%d: first fill %d-%d reads; then about %d a day" % (n, n, 3 * n, math.ceil(n / 30 * 1.5)))
print("\nMETERED COST: $0 (no model call; the Basic plan is free; the gateway's Worker requests are inside its plan).")
