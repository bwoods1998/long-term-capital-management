"""table_w7.py: section 5.3's table of the search stage (synthetic; reads w7.search.jsonl and, where a cell was re-run
on fresh seeds, w7.fresh.jsonl): the per-run false-pass rate within 120 sessions of every search cell, the corner's
full factorial (rho_day 0.15, left-skewed events, 1% issuer effects, pool 300) by day shape, phi_day, drift and lag,
and each other factor varied from the corner at phi_day 0.20 and a 20 bp drift (0.15 also for day-following counts).
Writes table_w7.md."""
import json, os, sys
sys.path.insert(0, ".")
import calib_w7 as w
w.grid("search")
by = {}
for l in open("w7.search.jsonl"):
    r = json.loads(l); by.setdefault(r["cell"], []).append(r)
S = {n: w.summarise(p) for n, p in by.items()}
F = {}
if os.path.exists("w7.fresh.jsonl"):
    fb = {}
    for l in open("w7.fresh.jsonl"):
        r = json.loads(l); fb.setdefault(r["cell"], []).append(r)
    F = {n: w.summarise(p) for n, p in fb.items()}
def name(**kw):
    c, _ = w.corner(**kw); return c.name
def v(n):
    s = S[n]; t = f"{s['run1']:.3f}"
    if n in F: t += f" (fresh {F[n]['run1']:.3f})"
    return t
L = []
L.append("| day shape | lag | phi 0.10: drift 0 / 10 / 20 bp | phi 0.15: drift 0 / 10 / 20 bp | phi 0.20: drift 0 / 10 / 20 bp |")
L.append("|---|---|---|---|---|")
lab = {"crash": "crash days, normal body", "crasht3": "crash days, t(3) body", "crashcl": "clustered crash days",
       "crasht3cl": "t(3)-body clustered crash days"}
for sh in w.SHAPES:
    for lag in (1, 2):
        cells = []
        for phi in (0.10, 0.15, 0.20):
            cells.append(" / ".join(v(name(shape=sh, phi=phi, drift=dr, lag=lag)) for dr in (0.0, 0.0010, 0.0020)))
        L.append(f"| {lab[sh]} | {lag} | " + " | ".join(cells) + " |")
L.append("")
L.append("| varied from the corner (phi_day 0.20, 20 bp drift unless stated) | normal-body crash | t(3)-body crash | clustered crash | t(3)-body clustered crash |")
L.append("|---|---|---|---|---|")
rowsv = [("symmetric events", dict(skew=False)), ("no issuer effect", dict(tau=0.0)),
         ("counts follow the day", dict(cnt=0.3)), ("counts follow the day, phi_day 0.15", dict(cnt=0.3, phi=0.15)),
         ("pool 800", dict(pool=800)), ("rho_day 0.05", dict(rho=0.05)),
         ("knife edge, ic 0.03", dict(null="N2", ic=0.03)), ("knife edge, ic 0.05", dict(null="N2", ic=0.05))]
for lab_, kw in rowsv:
    for lag in (1, 2):
        cells = []
        for sh in w.SHAPES:
            k = dict(shape=sh, phi=0.20, drift=0.0020, lag=lag); k.update(kw)
            cells.append(v(name(**k)))
        L.append(f"| {lab_}, lag {lag} | " + " | ".join(cells) + " |")
L.append("")
for lag in (1, 2):
    sym = " / ".join(v(name(shape="t3", phi=p, drift=0.0020, lag=lag)) for p in (0.10, 0.15, 0.20))
    base = v(name(shape="t3", phi=0.10, drift=0.0, lag=lag, rho=0.05, skew=False, tau=0.0))
    b20 = v(name(shape="t3", phi=0.20, drift=0.0, lag=lag, rho=0.05, skew=False, tau=0.0))
    L.append(f"- lag {lag}: symmetric t(3) days at the corner, phi_day 0.10 / 0.15 / 0.20: {sym}; BASE (symmetric days and "
             f"events, rho_day 0.05, phi_day 0.10, no drift, no issuer effect): {base}; the base at phi_day 0.20: {b20}")
allv = sorted(((s["run1"], n) for n, s in S.items()), reverse=True)
L.append(f"- {len(S)} cells; search maximum {allv[0][0]:.3f} ({allv[0][1]}); median {allv[len(allv) // 2][0]:.3f}; "
         f"programs a cell: 1,000 for grid cells 0-19, 500 for the rest")
open("table_w7.md", "w").write("\n".join(L) + "\n")
print("\n".join(L))
