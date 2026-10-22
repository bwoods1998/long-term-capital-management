#!/usr/bin/env python
"""table_w9ff.py: the final minimal fix's tables for sections 11.2-11.4 (markdown), from the ff.*.jsonl outputs of
calib_w9ff.py. SYNTHETIC ONLY. Usage: table_w9ff.py  (prints; chain or hand writes ff.tables.md)"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import calib_w9ff as f  # noqa: E402

w = f.w
S = w.summarise


def hist_label(spec, name):
    if spec["hist"] == "cold":
        return "COLD (PREREG-EVL-7's learner on this file's columns, no prior, no g)"
    if "TAUS05" in name:
        return "TAUS 0.5: history carried the issuers' own effects (rho_tau 0.5) through ln sig20, the SIC groups and g"
    if spec["adv"]:
        k = {"leak": "ADV leak: all prior weight on one event column", "rand": "ADV rand: a strong random prior (k 0.60)",
             "lowvol": "ADV lowvol: \"low-volatility names win\" (k 0.30)"}[spec["adv"]]
        return k + ("; no issuer effect" if spec["tau"] == 0 else "")
    if spec["null"] == "N2":
        return f"N2, the knife edge, ic {spec['ic']:.2f}"
    if spec["drift_c"]:
        return "CHAR10: HD08 with a drift of 10 bp a unit along its own history direction"
    if spec["tauh"]:
        return "TAUH: EVL-WL-ON's history carried the issuer slope through dmove"
    if spec["ic_h"]:
        return f"HD{int(round(spec['ic_h'] * 100)):02d}: a decayed history edge of {spec['ic_h']:.2f}"
    extra = []
    if spec["tau"] == 0:
        extra.append("no issuer effect")
    if spec["shape"] != "crasht3cl":
        extra.append("crash days not clustered")
    if spec["drift_sd"] != 0.002:
        extra.append(f"drift {int(round(spec['drift_sd'] * 1e4))} bp")
    if spec["cnt"]:
        extra.append("counts that follow the day")
    return "H0, noise history" + ("; " + ", ".join(extra) if extra else "")


def search_table():
    by = f.load("search")
    cells = {}
    for name, parts in by.items():
        sp = parts[0]["spec"]
        key = hist_label(sp, name)
        cells.setdefault(key, {})[(sp["learner"], int(sp["nbar"]))] = S(parts)
    cols = [("ON", 300), ("ON", 600), ("ON", 800), ("O1", 300), ("O1", 450), ("O1", 600)]
    out = ["| history (t(3)-body clustered crash days, left-skewed events, rho_day 0.15, phi_day 0.20, a 20 bp drift, 1% "
           "issuer effects unless named) | EVL-WL-ON pool 300 | 600 | 800 | EVL-WL-O1 pool 300 | 450 | 600 |",
           "|---|---|---|---|---|---|---|"]
    order = sorted(cells, key=lambda k: (k.startswith("COLD"), k))
    for k in order:
        row = [k]
        for c in cols:
            s = cells[k].get(c)
            row.append(f"{s['run1']:.3f}" if s else "-")
        out.append("| " + " | ".join(row) + " |")
    return "\n".join(out)


def picks_line():
    by = f.load("search")
    lines = []
    for L in ("ON", "O1"):
        for n in f.POOLS[L]:
            ss = [(S(p), p[0]["spec"]) for nm, p in by.items() if p[0]["spec"]["learner"] == L and
                  int(p[0]["spec"]["nbar"]) == int(n) and p[0]["spec"]["hist"] == "warm"]
            if not ss:
                continue
            tau = [s["tau_bp"] for s, sp in ss if sp["tau"] > 0]
            lines.append(f"{L} pool {int(n)}: warm cells {len(ss)}, run 1 max {max(s['run1'] for s, _ in ss):.3f} median "
                         f"{sorted(s['run1'] for s, _ in ss)[len(ss) // 2]:.3f}; picks a session "
                         f"{min(s['ev_s'] for s, _ in ss):.1f}-{max(s['ev_s'] for s, _ in ss):.1f}; picks' issuer effect "
                         f"{min(tau):+.1f} to {max(tau):+.1f} bp (1% cells); version within 120 sessions max "
                         f"{max(s['v120'] for s, _ in ss):.3f}")
    return "\n".join(lines)


def fresh_table():
    b1, b2, bs = f.load("fresh1"), f.load("fresh2"), f.load("search")
    rows = []
    for name in b1:
        parts = b1[name] + b2.get(name, [])
        s = S(parts)
        rows.append((s["run1"], name, s, S(bs[name]), parts[0]["spec"], name in b2))
    rows.sort(key=lambda r: -r[0])
    out = ["| cell | learner, pool | fresh run 1 (SE, programs) | search run 1 (200) | version within 120 sessions | "
           "record's true mean a <= 0 / <= 10 bp at the pass | picks a session | picks' issuer effect (bp) |",
           "|---|---|---|---|---|---|---|---|"]
    for r1, name, s, ss, sp, two in rows:
        out.append(f"| {hist_label(sp, name)} | {sp['learner']}, {int(sp['nbar'])} | {'**' if r1 == rows[0][0] else ''}"
                   f"{r1:.4f}{'**' if r1 == rows[0][0] else ''} ({s['run1_se']:.4f}, {s['R']:,}) | {ss['run1']:.3f} | "
                   f"{s['v120']:.3f} | {s['cm0']:.4f} / {s['cm10']:.4f} | {s['ev_s']:.1f} | {s['tau_bp']:+.1f} |")
    return "\n".join(out)


def simple(tag):
    by = f.load(tag)
    out = []
    for name, parts in sorted(by.items(), key=lambda kv: -S(kv[1])["run1"]):
        s = S(parts)
        x = (f"{name}: R {s['R']} run1 {s['run1']:.4f} (se {s['run1_se']:.4f}) v120 {s['v120']:.3f} cm<=0 {s['cm0']:.4f} "
             f"cm<=10 {s['cm10']:.4f} ev/s {s['ev_s']:.2f} tau {s['tau_bp']:+.1f} uhz {s['uhz']:.2f} guarded {s['guarded']:.1f}")
        if "life3" in s:
            x += (f" | life3 {s['life3']:.4f} by60/120/200 {s['life3_by60']:.3f}/{s['life3_by120']:.3f}/"
                  f"{s['life3_by200']:.3f} runs {s['life3_runs']:.2f} | run1 by60/120 {s['by60']:.3f}/{s['by120']:.3f}")
        out.append(x)
    return "\n".join(out)


def power_table():
    by = f.load("power")
    rows = {}
    for name, parts in by.items():
        s = S(parts)
        sp = parts[0]["spec"]
        rows[name] = (s, sp)
    out = ["| ic | history | EVL-WL-O1 (lag 1, pool 300): by 25 / 40 / 60 / 120 | edge 1-10 -> 51-60 | EVL-WL-ON (lag 2, "
           "pool 600): by 25 / 40 / 60 / 120 | edge 1-10 -> 51-60 |", "|---|---|---|---|---|---|"]

    def cell(L, ic, hist, rho):
        for name, (s, sp) in rows.items():
            if (sp["learner"] == L and abs(sp["ic"] - ic) < 1e-9 and sp["hist"] == hist and sp["shape"] == "t3"
                    and (hist == "cold" or abs(sp["rho_h"] - rho) < 1e-9) and "-SP05" not in name):
                e = s["edge_bp"]
                return (f"{s['by25']:.3f} / {s['by40']:.3f} / {s['by60']:.3f} / {s['by120']:.3f}",
                        f"{e.get('1-10', float('nan')):+.1f} -> {e.get('51-60', float('nan')):+.1f}")
        return ("-", "-")
    for ic in (0.03, 0.05, 0.08):
        for hist, rho, lab in (("cold", 1.0, "cold"), ("warm", 1.0, "warm, rho 1"), ("warm", 0.7, "warm, rho 0.7"),
                               ("warm", 0.0, "warm, rho 0")):
            a, b = cell("O1", ic, hist, rho), cell("ON", ic, hist, rho)
            out.append(f"| {ic:.2f} | {lab} | {a[0]} | {a[1]} | {b[0]} | {b[1]} |")
    extra = []
    for name, (s, sp) in sorted(rows.items()):
        if sp["shape"] != "t3" or "-SP05" in name:
            e = s["edge_bp"]
            extra.append(f"{name}: by25/40/60/120 {s['by25']:.3f}/{s['by40']:.3f}/{s['by60']:.3f}/{s['by120']:.3f} edge "
                         f"{e.get('1-10', float('nan')):+.1f} -> {e.get('51-60', float('nan')):+.1f}")
    return "\n".join(out) + "\n\n" + "\n".join(extra)


if __name__ == "__main__":
    print("## SEARCH (ff.search.jsonl, 200 programs a cell, seeds 861e6 +)\n")
    print(search_table())
    print("\n" + picks_line())
    for tag, fn in (("FRESH (ff.fresh1 + ff.fresh2)", fresh_table), ("POWER (ff.power.jsonl)", power_table)):
        try:
            print(f"\n## {tag}\n")
            print(fn())
        except Exception as e:  # noqa: BLE001
            print("(not yet)", e)
    for tag in ("life", "coldref", "stress"):
        try:
            print(f"\n## {tag.upper()} (ff.{tag}.jsonl)\n")
            print(simple(tag))
        except Exception as e:  # noqa: BLE001
            print("(not yet)", e)
