"""mkplans.py: the re-check's cells (synthetic only). Seeds from 150,000,000 (none used by the judge 81-89M, the
checks 91-99M or the fixer 111-119M)."""
import json
N3 = dict(skill=0.006, mu_family=-0.006)
BOTH = dict(day="crash", ev_left=1.4, ev_right=0.6, jump_left=0.8)
DAYSKEW = dict(day="crash", jump_left=0.5)
EVSKEW = dict(ev_left=1.4, ev_right=0.6, jump_left=0.8)
CORNER = dict(rho_day=0.15, phi_day=0.20, drift_sd=0.0020, **BOTH, **N3)
seed = [150_000_000]


def cell(lab, R, variants=("w", "u", "j"), **gen):
    seed[0] += 10_000
    return {"lab": lab, "gen": gen, "R": R, "T": 120, "seed0": seed[0], "variants": list(variants)}


# PLAN A: the fresh worst plausible cells, the base, power
A = []
A.append(cell("corner n85", 8000, **CORNER, nbar=85))
A.append(cell("corner n30", 4000, **CORNER, nbar=30))
A.append(cell("corner n13", 4000, **CORNER, nbar=13))
A.append(cell("corner n8", 4000, **CORNER, nbar=8))
A.append(cell("corner n3", 4000, **CORNER, nbar=3))
A.append(cell("dayskew AR20 phi.20 rho.15 n85", 4000, rho_day=0.15, phi_day=0.20, drift_sd=0.0020, **DAYSKEW, **N3, nbar=85))
A.append(cell("both AR20 phi.15 rho.15 n85", 4000, rho_day=0.15, phi_day=0.15, drift_sd=0.0020, **BOTH, **N3, nbar=85))
A.append(cell("both nodrift phi.20 rho.15 n85", 4000, rho_day=0.15, phi_day=0.20, **BOTH, **N3, nbar=85))
A.append(cell("dayskew AR10 phi.20 rho.15 n85", 4000, rho_day=0.15, phi_day=0.20, drift_sd=0.0010, **DAYSKEW, **N3, nbar=85))
A.append(cell("both AR10 phi.20 rho.15 n85", 4000, rho_day=0.15, phi_day=0.20, drift_sd=0.0010, **BOTH, **N3, nbar=85))
for nb in (85, 30, 13, 8, 3):
    A.append(cell(f"base n{nb}", 2000, ("w",), rho_day=0.05, phi_day=0.10, **N3, nbar=nb))
for sk in (0.006, 0.010):
    for nb in (85, 30, 13, 8, 3):
        A.append(cell(f"P{int(sk*1e4)} rho.05 n{nb}", 2000, ("w",), rho_day=0.05, phi_day=0.10, skill=sk, nbar=nb))
json.dump({"cells": A}, open("planA.json", "w"), indent=1)

# PLAN B: tries to break <= 0.13 inside the plausible grid's bounds (rho <= .15, phi <= .20, drift sd <= 20 bp,
# 5% crash days at -3 sd, left-skewed events)
seed[0] = 152_000_000
B = []
B.append(cell("BREAK rate: corner n150", 4000, ("w",), **CORNER, nbar=150))
B.append(cell("BREAK rate: corner n50", 4000, ("w",), **CORNER, nbar=50))
B.append(cell("BREAK rate: corner n20", 4000, ("w",), **CORNER, nbar=20))
for ar in (0.90, 0.93, 0.95):
    kw = dict(CORNER); kw["drift_rho"] = ar
    B.append(cell(f"BREAK drift persistence: corner, drift AR{ar} sd20 n85", 4000, ("w",), **kw, nbar=85))
for vr, vs in ((0.97, 0.30), (0.98, 0.40)):
    B.append(cell(f"BREAK vol persistence: corner, vol AR{vr} sd{vs} n85", 4000, ("w",), **CORNER, vol_rho=vr, vol_sd=vs, nbar=85))
for cc in (0.3, 0.5):
    B.append(cell(f"BREAK drift-day corr {cc}: corner n85", 4000, ("w",), **CORNER, drift_day_corr=cc, nbar=85))
B.append(cell("BREAK issuer effects 1%: corner n85", 4000, ("w",), **CORNER, issuer_tau=0.010, nbar=85))
for nb in (3, 8, 13, 30):
    B.append(cell(f"BREAK counts follow |day| (kappa .3, money knife): corner n{nb}", 4000, ("w", "u"), **CORNER,
                  cnt_kappa=0.3, mw_knife=14, nbar=nb))
for nb in (3, 5, 8):
    for kp in (0.01, 0.02):
        B.append(cell(f"BREAK count-residual kappa {kp}: corner n{nb}", 4000, ("w", "u"), **CORNER, kappa=kp, nbar=nb))
json.dump({"cells": B}, open("planB.json", "w"), indent=1)
print(len(A), sum(c["R"] for c in A), len(B), sum(c["R"] for c in B))

# PLAN C: tail and persistence couplings of the day shock with the volatility regime, inside the grid's bounds
seed[0] = 156_000_000
C = []
C.append(cell("BREAK crash days cluster in high vol (gamma 2): corner n85", 4000, ("w",), **CORNER, crash_vol=2.0, nbar=85))
C.append(cell("BREAK vol spike after a crash day (+0.5 log): corner n85", 4000, ("w",), **CORNER, vol_fb=0.5, nbar=85))
C.append(cell("BREAK crash days with t(3) ordinary days: corner n85", 4000, ("w",), **CORNER, crash_t3=1, nbar=85))
C.append(cell("BREAK vol spike + vol AR.97: corner n85", 4000, ("w",), **CORNER, vol_fb=0.5, vol_rho=0.97, nbar=85))
json.dump({"cells": C}, open("planC.json", "w"), indent=1)

# PLAN D: confirmations on further fresh seeds (160,000,000+) of every cell that read near or above 0.13
seed[0] = 160_000_000
D = []
D.append(cell("CONF t3-body crash days: corner n85", 8000, ("w",), **CORNER, crash_t3=1, nbar=85))
D.append(cell("CONF t3-body crash days: corner n30", 4000, ("w",), **CORNER, crash_t3=1, nbar=30))
D.append(cell("CONF t3-body crash days: corner n3", 4000, ("w", "u"), **CORNER, crash_t3=1, nbar=3))
D.append(cell("CONF t3-body crash days: base shape (rho.05 phi.10 none) n85", 2000, ("w",), rho_day=0.05, phi_day=0.10, **BOTH, **N3, crash_t3=1, nbar=85))
D.append(cell("CONF t3-body crash days: judge's grid corner (phi.10) n85", 4000, ("w",), **{**CORNER, "phi_day": 0.10}, crash_t3=1, nbar=85))
D.append(cell("CONF crash days cluster in high vol (gamma 2): corner n85", 4000, ("w",), **CORNER, crash_vol=2.0, nbar=85))
D.append(cell("CONF crash days cluster in high vol (gamma 2): corner n30", 4000, ("w",), **CORNER, crash_vol=2.0, nbar=30))
D.append(cell("CONF counts follow |day| (kappa .3, money knife): corner n3", 8000, ("w", "u"), **CORNER, cnt_kappa=0.3, mw_knife=14, nbar=3))
D.append(cell("CONF counts follow |day| (kappa .3, money knife): corner n5", 4000, ("w", "u"), **CORNER, cnt_kappa=0.3, mw_knife=14, nbar=5))
D.append(cell("CONF counts follow |day| (kappa .3, money knife): phi.10 n3", 4000, ("w", "u"), **{**CORNER, "phi_day": 0.10}, cnt_kappa=0.3, mw_knife=14, nbar=3))
D.append(cell("CONF drift-day corr 0.3: corner n85", 4000, ("w",), **CORNER, drift_day_corr=0.3, nbar=85))
D.append(cell("CONF drift-day corr 0.3: corner n30", 4000, ("w",), **CORNER, drift_day_corr=0.3, nbar=30))
D.append(cell("CONF vol AR.97: corner n85", 4000, ("w",), **CORNER, vol_rho=0.97, nbar=85))
D.append(cell("CONF rate: corner n150", 4000, ("w",), **CORNER, nbar=150))
D.append(cell("CONF rate: corner n110", 4000, ("w",), **CORNER, nbar=110))
D.append(cell("CONF drift AR.95: corner n85", 4000, ("w",), **{**CORNER, "drift_rho": 0.95}, nbar=85))
for nb in (5, 8):
    for kp in (0.01, 0.02):
        D.append(cell(f"CONF count-residual kappa {kp} (money knife): corner n{nb}", 4000, ("w", "u"), **CORNER, kappa=kp, kappa_knife=1, nbar=nb))
json.dump({"cells": D}, open("planD.json", "w"), indent=1)
print("D", len(D), sum(c["R"] for c in D))

# PLAN E: the slower shortlisted schedule (first look at block 12; 0.012 / 0.006 / 0.0025) beside this file's, on the
# structures that broke 0.13 (seeds 165,000,000+)
seed[0] = 165_000_000
E = []
E.append(cell("E t3-body crash days: corner n85", 6000, ("w", "r12"), **CORNER, crash_t3=1, nbar=85))
E.append(cell("E t3-body crash days: dayskew AR20 rho.15 phi.20 n85", 4000, ("w", "r12"), rho_day=0.15, phi_day=0.20, drift_sd=0.0020, **DAYSKEW, **N3, crash_t3=1, nbar=85))
E.append(cell("E t3-body crash days: corner n30", 4000, ("w", "r12"), **CORNER, crash_t3=1, nbar=30))
E.append(cell("E crash days cluster in high vol (gamma 2): corner n85", 4000, ("w", "r12"), **CORNER, crash_vol=2.0, nbar=85))
E.append(cell("E t3-body + crash clustering: corner n85", 4000, ("w", "r12"), **CORNER, crash_t3=1, crash_vol=2.0, nbar=85))
E.append(cell("E drift-day corr 0.3: corner n85", 4000, ("w", "r12"), **CORNER, drift_day_corr=0.3, nbar=85))
E.append(cell("E counts follow |day| (money knife): corner n3", 4000, ("w", "r12"), **CORNER, cnt_kappa=0.3, mw_knife=14, nbar=3))
E.append(cell("E t3-body + counts follow |day|: corner n3", 4000, ("w", "r12"), **CORNER, crash_t3=1, cnt_kappa=0.3, mw_knife=14, nbar=3))
E.append(cell("E plain corner n85 (control)", 4000, ("w", "r12"), **CORNER, nbar=85))
json.dump({"cells": E}, open("planE.json", "w"), indent=1)
print("E", len(E), sum(c["R"] for c in E))
