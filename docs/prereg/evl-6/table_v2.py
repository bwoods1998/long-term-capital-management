#!/usr/bin/env python
"""table_v2.py: section 4.4's table for the chosen rule (synthetic only): P(promotion at any look of the first run
within 120 sessions) at zero edge, the maximum over the rates of each row (85, 30, 13, 8, 3; counts that follow the day:
8, 5, 3), the selection seeds' rate (w2, w2x) where the cell was re-run, else the search seeds' (s1null, w1). The rows of the
earlier grid keep their drifts; the rows D14 added show the maximum over the three drifts (the drift at the maximum
in brackets: 0, 10 or 20 bp). Writes markdown to stdout.

Usage: table_v2.py > table_v2.md
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import search_v2 as SV  # noqa: E402
import search_final as SF  # noqa: E402

DNAME = {"nodrift": "0", "AR10": "10", "AR20": "20"}


def main():
    rule = SF.Rule.of(json.load(open(os.path.join(HERE, "chosen_v2.json")))["chosen"]["rule"])
    vals = {}
    for phases, src in ((["s1null", "w1"], "s"), (["w2", "w2x"], "w2")):
        for c in SF._load(phases, []):
            if not SV.plausible(c["cell"], c["gen"]):
                continue
            fp, _, _ = SF.first_pass(c["d"], "", rule, c["tag"])
            k = (c["cell"], json.dumps(c["gen"], sort_keys=True))
            if src == "w2" or k not in vals or vals[k][2] != "w2":
                vals[k] = (SF.rate(fp, 120), c, src)
    cols = [(0.0, 0.10), (0.05, 0.10), (0.05, 0.15), (0.05, 0.20), (0.15, 0.10), (0.15, 0.15), (0.15, 0.20)]
    rows = {}
    for (cell, gk), (v, c, src) in vals.items():
        parts = cell.split("|")
        null, shape, drift = parts[0], parts[1], parts[2]
        cnt = cell.endswith("|cnt")
        g = c["gen"]
        col = (round(g["rho_day"], 2), round(g.get("phi_day", 0.10), 2) if g["rho_day"] > 0 else 0.10)
        new = shape.endswith(("T", "C", "TC")) or cnt
        rk = (null, shape, "all" if new else drift, cnt)
        cur = rows.setdefault(rk, {})
        best = cur.get(col)
        if best is None or v > best[0]:
            cur[col] = (v, DNAME.get(drift, drift), g["nbar"], src)
    order = []
    for null in ("N3", "N1"):
        for cnt in (False, True):
            for shape in ("sym", "evskew", "dayskew", "both", "dayskewT", "bothT", "dayskewC", "bothC", "dayskewTC",
                          "bothTC"):
                for drift in ("nodrift", "AR10", "AR20", "issuer1%", "all"):
                    if (null, shape, drift, cnt) in rows:
                        order.append((null, shape, drift, cnt))
    names = {"sym": "symmetric", "evskew": "skewed events", "dayskew": "crash days", "both": "crash days + skewed events",
             "dayskewT": "t(3)-body crash days", "bothT": "t(3)-body crash days + skewed events",
             "dayskewC": "clustered crash days", "bothC": "clustered crash days + skewed events",
             "dayskewTC": "t(3)-body clustered crash days", "bothTC": "t(3)-body clustered crash days + skewed events"}
    print("| null, shape, drift | rho_day 0 | rho_day 0.05: phi 0.10 / 0.15 / 0.20 | rho_day 0.15: phi 0.10 / 0.15 / 0.20 |")
    print("|---|---|---|---|")
    worst = (0.0, None)
    for rk in order:
        null, shape, drift, cnt = rk
        r = rows[rk]

        def f(col):
            if col not in r:
                return ""
            v, d, nb, src = r[col]
            return f"{v:.3f}" + (f" [{d}]" if drift == "all" else "")
        for col, x in r.items():
            if x[0] > worst[0]:
                worst = (x[0], rk, col, x)
        dlab = {"nodrift": "none", "AR10": "10 bp", "AR20": "20 bp", "issuer1%": "issuer effects 1%",
                "all": "every drift"}[drift]
        lab = f"{null} {names[shape]}" + (", counts follow the day (8, 5, 3 a session)" if cnt else "") + f", {dlab}"
        c0 = f((0.0, 0.10))
        c1 = " / ".join(f(cc) for cc in cols[1:4]) if any(cc in r for cc in cols[1:4]) else ""
        c2 = " / ".join(f(cc) for cc in cols[4:]) if any(cc in r for cc in cols[4:]) else ""
        print(f"| {lab} | {c0} | {c1} | {c2} |")
    print()
    print(f"WORST: {worst[0]:.4f} at {worst[1]} {worst[2]} (drift {worst[3][1]}, {worst[3][2]} a session, {worst[3][3]})")


if __name__ == "__main__":
    main()
