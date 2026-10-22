#!/usr/bin/env python
"""report_judge.py: tables from calib_judge.py's runs (synthetic only; reads no lane data).

    report_judge.py agg                 # concatenate the jobs of each cell -> /dev/shm/calib-judge/agg/*.npz
    report_judge.py variants [--H 120]  # the worst union / new-alone FP per variant over the plausible and stress cells
    report_judge.py show VARIANT        # every cell for one variant: old alone, new alone, union; power
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SHM = os.environ.get("CALIB_SHM", "/dev/shm/calib-judge")
AGG = os.path.join(SHM, "agg")
PHASES = ("main", "stress", "noskill", "life", "power", "power120")


def agg():
    os.makedirs(AGG, exist_ok=True)
    meta = []
    for ph in PHASES:
        idx = os.path.join(HERE, f"calib_judge.{ph}.index.jsonl")
        if not os.path.exists(idx):
            continue
        groups: dict = {}
        for line in open(idx):
            r = json.loads(line)
            key = (r["cell"], json.dumps(r["gen"], sort_keys=True), r["T"])
            groups.setdefault(key, []).append(r)
        for i, ((cell, gen, T), rs) in enumerate(sorted(groups.items())):
            arrs: dict = {}
            for r in sorted(rs, key=lambda r: r["seed"]):
                with np.load(r["path"]) as z:
                    for k in z.files:
                        arrs.setdefault(k, []).append(z[k])
            out = {k: np.concatenate(v) for k, v in arrs.items()}
            path = os.path.join(AGG, f"{ph}_{i:03d}.npz")
            np.savez_compressed(path, **out)
            meta.append({"phase": ph, "cell": cell, "gen": json.loads(gen), "T": T, "R": int(out["old"].size),
                         "path": path, "secs": sum(r["secs"] for r in rs)})
    json.dump(meta, open(os.path.join(AGG, "meta.json"), "w"), indent=0)
    print(f"{len(meta)} cells aggregated")


def _meta():
    return json.load(open(os.path.join(AGG, "meta.json")))


def rate(first, H):
    return float(np.mean((first >= 1) & (first <= H)))


def union(a, b):
    both = (a >= 1) & (b >= 1)
    return np.where(both, np.minimum(a, b), np.maximum(a, b))


def plausible(m):
    """The worst PLAUSIBLE set (section 4 of the prereg): residual day-shock share up to 0.15 of event variance with any
    shape (symmetric, crash days, left-skewed events, both), factor momentum AR 0.10, persistent family drift up to
    20 bp a session (AR 0.97), issuer effects; every N3 / N1 null."""
    g = m["gen"]
    if m["phase"] not in ("main", "stress", "noskill", "life"):
        return False
    if g.get("rho_day", 0) > 0.15 + 1e-9:
        return False
    if g.get("drift_sd", 0) > 0.0020 + 1e-9 or g.get("drift_rho", 0.97) > 0.97 + 1e-9:
        return False
    if g.get("phi_day", 0.10) > 0.10 + 1e-9 or g.get("day", "t3") == "crashx":
        return False
    if m["cell"].startswith("N2+"):
        return False
    return True


def is_null(m):
    return m["phase"] in ("main", "stress", "noskill", "life") and not m["cell"].startswith("N2+")


def lab(m):
    g = m["gen"]
    return f"{m['cell']:22s} n{int(g['nbar']):3d} rho{g['rho_day']:.2f} T{m['T']}"


def variants(H=120, lag=None, top=40):
    meta = _meta()
    nulls = [m for m in meta if is_null(m)]
    data = {m["path"]: dict(np.load(m["path"])) for m in nulls}
    keys = [k for k in next(iter(data.values())) if k != "old"]
    rows = []
    for k in keys:
        L = int(k.split("|")[0][1:])
        if lag is not None and L != lag:
            continue
        smax = int(k.split("|x")[1])
        wp = ws = wpn = wsn = (0.0, None)
        for m in nulls:
            d = data[m["path"]]
            if k not in d:
                continue
            h = min(H, m["T"])
            u = rate(union(d["old"], d[k]), h)
            n = rate(d[k], h)
            if plausible(m):
                wp = max(wp, (u, lab(m)), key=lambda x: x[0])
                wpn = max(wpn, (n, lab(m)), key=lambda x: x[0])
            else:
                ws = max(ws, (u, lab(m)), key=lambda x: x[0])
                wsn = max(wsn, (n, lab(m)), key=lambda x: x[0])
        rows.append((k, wp, wpn, ws, wsn))
    rows.sort(key=lambda r: r[1][0])
    print(f"worst union FP over plausible nulls (horizon {H}), then new alone; stress worst")
    for k, wp, wpn, ws, wsn in rows[:top] if top else rows:
        print(f"{k:34s} union {wp[0]:.4f} [{wp[1]}] new {wpn[0]:.4f} | stress union {ws[0]:.4f} [{ws[1]}]")
    return rows


def old_table(H=120):
    meta = _meta()
    print(f"PREREG-EVL-3 alone (its skew check on), FP within {H} sessions")
    for m in meta:
        if not is_null(m):
            continue
        d = np.load(m["path"])
        print(f"  {lab(m)}  old {rate(d['old'], min(H, m['T'])):.4f}  plausible={plausible(m)}")


def power(keys, Hs=(10, 15, 20, 30, 40, 60)):
    meta = _meta()
    for m in meta:
        if not m["phase"].startswith("power"):
            continue
        d = np.load(m["path"])
        old = d["old"]
        line = [f"{lab(m)} old " + " ".join(f"{rate(old, h):.2f}" for h in Hs) + f" med {med(old)}"]
        for k in keys:
            u = union(old, d[k])
            line.append(f"   {k}: new " + " ".join(f"{rate(d[k], h):.2f}" for h in Hs) + f" med {med(d[k])} | union "
                        + " ".join(f"{rate(u, h):.2f}" for h in Hs) + f" med {med(u)}")
        print("\n".join(line))


def med(first):
    x = np.where(first >= 1, first, 10_000).astype(float)
    v = float(np.median(x))
    return None if v >= 10_000 else v


def show(k, H=120):
    meta = _meta()
    for m in meta:
        d = np.load(m["path"])
        if k not in d.files:
            continue
        h = min(H, m["T"])
        u = union(d["old"], d[k])
        print(f"{m['phase']:8s} {lab(m)} R{m['R']:5d} | old {rate(d['old'], h):.4f} new {rate(d[k], h):.4f} union "
              f"{rate(u, h):.4f} | @40 old {rate(d['old'], 40):.4f} new {rate(d[k], 40):.4f} union {rate(u, 40):.4f}"
              f" | med new {med(d[k])} union {med(u)} {'P' if plausible(m) else ''}")


# ------------------------------------------------------------------------------------------- run 2: with retirement
def _inf(x):
    return np.where(x >= 1, x, 1_000_000).astype(np.int64)


def alone(d, k, ret=True):
    """EVL-6 alone (a version registered under PREREG-EVL-6): its first pass before its own retirement."""
    f = _inf(d[k])
    if ret:
        L, m0, g, c, smin, smax = k.split("|")
        rk = f"R|{L}|{c}|{smin}|{smax}"
        f = np.where(f < _inf(d[rk]), f, 1_000_000)
    return np.where(f < 1_000_000, f, -1)


def union2(d, k, ret=True):
    """PREREG-EVL-3's screen (with its retirement) OR the EVL-6 path (with its retirement): the first pass before the
    first retirement of either (a retired version never moves again)."""
    stop = _inf(d["old_ret"])
    fn = _inf(d[k])
    if ret:
        L, m0, g, c, smin, smax = k.split("|")
        stop = np.minimum(stop, _inf(d[f"R|{L}|{c}|{smin}|{smax}"]))
    fo = _inf(d["old"])
    u = np.minimum(np.where(fo < stop, fo, 1_000_000), np.where(fn < stop, fn, 1_000_000))
    return np.where(u < 1_000_000, u, -1)


def worst2(H=120, mode="alone", lag=None, filt=None, top=60, ret=True):
    meta = _meta()
    nulls = [m for m in meta if is_null(m)]
    data = {m["path"]: dict(np.load(m["path"])) for m in nulls}
    keys = [k for k in next(iter(data.values())) if not k.startswith(("old", "R|"))]
    rows = []
    for k in keys:
        if lag is not None and not k.startswith(f"L{lag}|"):
            continue
        if filt and not re.search(filt, k):
            continue
        wp = (0.0, None)
        ws = (0.0, None)
        base = []
        for m in nulls:
            d = data[m["path"]]
            if k not in d:
                continue
            f = alone(d, k, ret) if mode == "alone" else union2(d, k, ret)
            v = rate(f, min(H, m["T"]))
            if plausible(m):
                if v > wp[0]:
                    wp = (v, lab(m))
            elif v > ws[0]:
                ws = (v, lab(m))
            g = m["gen"]
            if m["cell"] == "N3|sym|nodrift" and abs(g["rho_day"] - 0.05) < 1e-9:
                base.append(v)
        rows.append((k, wp, ws, max(base) if base else float("nan")))
    rows.sort(key=lambda r: r[1][0])
    print(f"mode={mode} ret={ret} horizon {H}: worst plausible | base (N3 sym rho .05, max over rates) | stress worst")
    for k, wp, ws, b in (rows if not top else rows[:top]):
        print(f"{k:34s} {wp[0]:.4f} [{wp[1]}] base {b:.4f} | stress {ws[0]:.4f} [{ws[1]}]")
    return rows


def old2(H=120):
    meta = _meta()
    out = []
    for m in meta:
        if not is_null(m):
            continue
        d = np.load(m["path"])
        out.append((rate(d["old"], min(H, m["T"])), rate(d["old_ret"], min(H, m["T"])), lab(m), plausible(m)))
    out.sort()
    for v, r, l, p in out:
        print(f"{v:.4f} (retired {r:.3f}) {l} {'P' if p else 'stress'}")


def power2(keys, lag_for_old=0, Hs=(6, 7, 8, 10, 12, 15, 20, 30, 40, 60), mode="alone"):
    meta = _meta()
    for m in sorted([m for m in meta if m["phase"].startswith("power")],
                    key=lambda m: (m["cell"], m["gen"]["rho_day"], -m["gen"]["nbar"])):
        d = np.load(m["path"])
        old = d["old"]
        print(f"{lab(m)} | old    " + " ".join(f"{rate(old, h):.2f}" for h in Hs) + f" | med {med(old)}")
        for k in keys:
            f = alone(d, k) if mode == "alone" else union2(d, k)
            print(f"{'':38s} | {k.split('|')[0]} {mode[:5]} " + " ".join(f"{rate(f, h):.2f}" for h in Hs)
                  + f" | med {med(f)}  [{k}]")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd")
    ap.add_argument("arg", nargs="*")
    ap.add_argument("--H", type=int, default=120)
    ap.add_argument("--lag", type=int)
    ap.add_argument("--top", type=int, default=40)
    a = ap.parse_args()
    if a.cmd == "agg":
        agg()
    elif a.cmd == "variants":
        variants(a.H, a.lag, a.top)
    elif a.cmd == "old":
        old_table(a.H)
    elif a.cmd == "show":
        show(a.arg[0], a.H)
    elif a.cmd == "power":
        power(a.arg)
    elif a.cmd == "worst2":
        worst2(a.H, a.arg[0] if a.arg else "alone", a.lag, a.arg[1] if len(a.arg) > 1 else None, a.top)
    elif a.cmd == "old2":
        old2(a.H)
    elif a.cmd == "power2":
        power2(a.arg[1:], mode=a.arg[0])


