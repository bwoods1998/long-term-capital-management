#!/usr/bin/env python
"""table_w9.py: the tables of PREREG-EVL-9 sections 10-11 from calib_w9.py's own outputs (synthetic; reads only
w9.*.jsonl). Writes w9.tables.md and prints it.
Usage: table_w9.py
"""
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import calib_w9 as w  # noqa: E402


def load(tag):
    p = os.path.join(HERE, f"w9.{tag}.jsonl")
    return w.load(tag) if os.path.exists(p) and os.path.getsize(p) else {}


def f(x, d=3):
    return f"{x:.{d}f}"


def main():
    S, F, P, X, L = load("search"), load("fresh"), load("power"), load("stress"), load("life")
    F.update(load("freshref"))
    out = []
    ss = {n: w.summarise(p) for n, p in S.items()}
    fs = {n: w.summarise(p) for n, p in F.items()}
    out.append("SEARCH SEEDS (401,000,001 +; 200 programs a cell): per-run rate within 120 sessions, by learner and history")
    out.append("")
    out.append("| learner (lag) | history | cells | worst run 1 (cell) | median | version by 120 at the worst | picks a session | picks' mean tau (bp) |")
    out.append("|---|---|---|---|---|---|---|---|")
    groups = {}
    for n, s in ss.items():
        L_ = n.split("-")[0]
        parts = n.split("-")
        h = parts[1]
        if h.startswith("CHAR"):
            h = parts[1] + "-" + parts[2]
        if h.startswith("N2"):
            h = "N2 knife edge"
        if "tauh" in n:
            h = "H0-TAUH"
        if "-tau0-" in n:
            h += " (no issuer effect)"
        if "-cnt" in n:
            h += " (counts follow the day)"
        if "-n600-" in n:
            h += " (pool 600)"
        if "-rho05-" in n and "-t3-" not in n:
            h += " (rho_day 0.05)"
        if "-sym-" in n and "-t3-" not in n:
            h += " (symmetric events)"
        if "-t3-sym-rho05-phi10-dr00-tau0" in n:
            h = ("BASE " + parts[1])
        groups.setdefault((L_, h), []).append((s["run1"], n, s))
    for (L_, h), rows in sorted(groups.items()):
        rows.sort(key=lambda x: -x[0])
        top = rows[0]
        med = float(np.median([r[0] for r in rows]))
        cell = top[1].split("-", 2)[2] if h != "cold" else top[1].split("-", 2)[2]
        out.append(f"| {L_} ({'1' if L_ == 'O1' else '2'}) | {h} | {len(rows)} | {f(top[0])} ({cell}) | {f(med)} | "
                   f"{f(top[2]['v120'])} | {top[2]['ev_s']:.2f} | {top[2]['tau_bp']:+.1f} |")
    out.append("")
    if fs:
        out.append("FRESH SEEDS (402,000,001 +): the selected worst cells")
        out.append("")
        out.append("| cell | fresh run 1 (se, programs) | search run 1 | pooled | version by 120 (fresh) | true mean a <= 0 at the pass | picks a session |")
        out.append("|---|---|---|---|---|---|---|")
        for n, s in sorted(fs.items(), key=lambda x: -x[1]["run1"]):
            sa = ss.get(n)
            pooled = (s["run1"] * s["R"] + (sa["run1"] * sa["R"] if sa else 0)) / (s["R"] + (sa["R"] if sa else 0))
            out.append(f"| {n} | {f(s['run1'], 4)} ({f(s['run1_se'], 4)}, {s['R']}) | {f(sa['run1']) if sa else '-'} | "
                       f"{f(pooled, 4)} | {f(s['v120'], 4)} | {f(s['cm0'], 4)} | {s['ev_s']:.2f} |")
        out.append("")
    if L:
        out.append("LIFE (404,000,001 +; 200 sessions, at most three runs)")
        out.append("")
        for n, p in L.items():
            s = w.summarise(p)
            out.append(f"- {n}: R {s['R']}; run 1 {f(s['run1'], 4)}; any of at most three runs within 200 sessions "
                       f"{f(s.get('life3', float('nan')), 4)} (by 60 / 120 / 180: {f(s.get('life3_by60', float('nan')))} / "
                       f"{f(s.get('life3_by120', float('nan')))} / {f(s.get('life3_by180', float('nan')))}), runs "
                       f"{s.get('life3_runs', float('nan')):.2f}")
        out.append("")
    if X:
        out.append("STRESSES (405,000,001 +; 200 programs a cell; named, not binding)")
        out.append("")
        out.append("| cell | run 1 | version by 120 | picks a session | picks' mean tau (bp) |")
        out.append("|---|---|---|---|---|")
        for n, p in sorted(X.items(), key=lambda x: -w.summarise(x[1])["run1"]):
            s = w.summarise(p)
            out.append(f"| {n} | {f(s['run1'])} | {f(s['v120'])} | {s['ev_s']:.2f} | {s['tau_bp']:+.1f} |")
        out.append("")
    if P:
        out.append("POWER (403,000,001 +; 200 programs a cell): P(promoted) by session 20 / 25 / 40 / 60 / 120 (any run), "
                   "the picks' true after-cost edge in sessions 1-10 and 51-60 (bp)")
        out.append("")
        out.append("| cell | by 20 / 25 / 40 / 60 / 120 | edge 1-10 -> 51-60 |")
        out.append("|---|---|---|")
        for n, p in sorted(P.items()):
            s = w.summarise(p)
            e = s["edge_bp"]
            out.append(f"| {n} | {f(s['vby20'])} / {f(s['vby25'])} / {f(s['vby40'])} / {f(s['vby60'])} / {f(s['vby120'])} | "
                       f"{e.get('1-10', float('nan')):+.1f} -> {e.get('51-60', float('nan')):+.1f} |")
        out.append("")
    txt = "\n".join(out)
    print(txt)
    open(os.path.join(HERE, "w9.tables.md"), "w").write(txt + "\n")


if __name__ == "__main__":
    main()
