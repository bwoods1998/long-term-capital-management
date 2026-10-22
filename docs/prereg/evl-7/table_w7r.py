#!/usr/bin/env python
"""table_w7r.py: section 5.3's search table for the final fix round (synthetic; reads calib_w7r.py's outputs only).
Per learner and lag: the four crash-day shapes at the corner (pools 300 / 800) and the corner's other factors; the
fresh figure in parentheses where the cell was re-run. Usage: table_w7r.py > table_w7r.md"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import calib_w7r as w  # noqa: E402


def main():
    a = w.load("search")
    f = w.load("fresh") if os.path.exists(os.path.join(HERE, "w7r.fresh.jsonl")) else {}
    S = {n: w.summarise(p) for n, p in a.items()}
    F = {n: w.summarise(p) for n, p in f.items()}

    def v(n):
        if n not in S:
            return "-"
        t = f"{S[n]['run1']:.3f}"
        if n in F:
            t += f" (fresh {F[n]['run1']:.4f})"
        return t

    def name(L, **kw):
        c, _, _ = w.cellr(L, **kw)
        return c.name

    print("| learner, lag | pool | crash days, normal body | t(3) body | clustered | t(3)-body clustered |  (- : not searched)")
    print("|---|---|---|---|---|---|")
    for L in ("o1", "on"):
        for lag in (1, 2):
            for pool in (300, 800):
                cells = [v(name(L, shape=sh, lag=lag, pool=pool)) for sh in w.w7.SHAPES]
                print(f"| {L.upper()}, lag {lag} | {pool} | " + " | ".join(cells) + " |")
    print()
    print("| varied from the corner (t(3)-body clustered crash days, phi_day 0.20, 20 bp drift, 1% issuer effects, "
          "rho_day 0.15, left-skewed events, pool 300 unless stated) | O1 lag 1 | O1 lag 2 | ON lag 1 | ON lag 2 |")
    print("|---|---|---|---|---|")
    rows = [("no issuer effect", dict(tau=0.0)), ("no issuer effect, pool 800", dict(tau=0.0, pool=800)),
            ("counts follow the day", dict(cnt=0.3)),
            ("phi_day 0.15", dict(phi=0.15)), ("no drift", dict(drift=0.0)),
            ("symmetric events", dict(skew=False)), ("rho_day 0.05", dict(rho=0.05)),
            ("the knife edge, ic 0.05", dict(null="N2", ic=0.05))]
    for lab, kw in rows:
        cells = [v(name(L, lag=lag, **kw)) for L in ("o1", "on") for lag in (1, 2)]
        print(f"| {lab} | " + " | ".join(cells) + " |")
    vals = sorted(((s["run1"], n) for n, s in S.items()), reverse=True)
    v = sorted(x for x, _ in vals)
    med = (v[(len(v) - 1) // 2] + v[len(v) // 2]) / 2   # the median (the final round's first table took the 21st highest)
    print()
    print(f"- {len(vals)} cells, 400 programs each (seeds 501,000,001 +); search maximum {vals[0][0]:.3f} ({vals[0][1]}); "
          f"median {med:.4f}")


if __name__ == "__main__":
    main()
