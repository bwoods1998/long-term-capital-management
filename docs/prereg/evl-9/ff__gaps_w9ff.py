#!/usr/bin/env python
"""gaps_w9ff.py: arithmetic on the final minimal fix's outputs (SYNTHETIC ONLY; reads only ff.*.jsonl).
(1) For each cell re-run fresh: the search-minus-fresh gap in standard errors of the difference (re-check 2's minor (e)).
(2) The binding cells pooled over EVERY fresh replicate: rounds 1 and 2 and the life cell's run 1 (a run 1 of a
    200-session program is a run 1 of a 120-session one: re-check 1's probe_rc9.py found no 60th block after session
    119), beside W9 (rounds 1 + 2 only, the registered protocol).
(3) The shape guard's effect at the low-volatility prior: guarded and unguarded cells side by side.
Usage: gaps_w9ff.py"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import calib_w9ff as f  # noqa: E402

w = f.w
S = w.summarise
srch, f1, f2, life, stress = (f.load(g) for g in ("search", "fresh1", "fresh2", "life", "stress"))

print("(1) search minus fresh, in SE of the difference")
for name in f1:
    fr = f1[name] + f2.get(name, [])
    a, b = S(srch[name]), S(fr)
    se = math.sqrt(a["run1"] * (1 - a["run1"]) / a["R"] + b["run1"] * (1 - b["run1"]) / b["R"])
    print(f"  {name:<72} search {a['run1']:.4f} (R {a['R']}) fresh {b['run1']:.4f} (R {b['R']}) gap "
          f"{a['run1'] - b['run1']:+.4f} = {(a['run1'] - b['run1']) / se:+.2f} SE")

print("(2) every fresh replicate pooled (rounds 1 + 2 + the life cell's run 1)")
for name in f1:
    lname = name + "-T200"
    fr = f1[name] + f2.get(name, [])
    b = S(fr)
    if lname in life:
        c = S(life[lname])
        n = b["R"] + c["R"]
        p = (b["run1"] * b["R"] + c["run1"] * c["R"]) / n
        print(f"  {name:<72} rounds 1+2 {b['run1']:.4f} (R {b['R']}) life run 1 {c['run1']:.4f} (R {c['R']}) pooled "
              f"{p:.4f} (se {math.sqrt(p * (1 - p) / n):.4f}, R {n})")

print("(3) the shape guard at the low-volatility prior and noise history (stress grid, 200 programs; beside the "
      "same cell with the guard on)")
pairs = [("O1-ADVlowvol30-crasht3cl-skew-rho15-phi20-dr20-tau1-n450-lag1", "fresh"),
         ("ON-ADVlowvol30-crasht3cl-skew-rho15-phi20-dr20-tau1-n600-lag2", "search"),
         ("O1-H0-crasht3cl-skew-rho15-phi20-dr20-tau1-n450-lag1", "fresh"),
         ("ON-H0-crasht3cl-skew-rho15-phi20-dr20-tau1-n600-lag2", "search")]
for name, src in pairs:
    on = f1[name] + f2.get(name, []) if src == "fresh" and name in f1 else srch[name]
    a = S(on)
    b = S(stress[name + "-noguard"])
    print(f"  {name:<64} guard on ({src}, R {a['R']}) {a['run1']:.4f} picks' issuer effect {a['tau_bp']:+.1f} bp sig "
          f"{a['sig']:.3f} | guard off (R {b['R']}) {b['run1']:.4f} {b['tau_bp']:+.1f} bp sig {b['sig']:.3f}")
