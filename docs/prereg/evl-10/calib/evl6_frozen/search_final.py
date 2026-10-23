#!/usr/bin/env python
"""search_final.py: PREREG-EVL-6's final rule evaluation and search on calib_final.py's arrays (SYNTHETIC ONLY).

A RULE = (start, pieces): looks at the first close at which the run's record holds >= S_k blocks and the minimums
(30 TRADABLE events, 30 issuers, 6 blocks), S_k in LOOKS from `start` on (thresholds reached together are one look;
no look after the 60th block); alpha(S) = the alpha of the first piece (s_upper, alpha) with S <= s_upper.
PASS at a look: p <= alpha(S) (no tolerance: D9), the guards (mean a > 0, mean r > 0, the top-14 means a > 0 and
r > 0, beats its control) and the issuer guard p_I <= 0.10. RETIRE first: mean a < 0 and q <= alpha(S) + 1e-12.
A run ENDS at its 60th block (D2): the version stays in learning and RUN 2 starts with block 61.

Usage:
  search_final.py grid  --null PHASES --power PHASES --out FILE      every candidate on those arrays
  search_final.py show  --rule JSON --null PHASES [--power PHASES]   every cell for one rule
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
TIE = 1e-12
LOOKS = (6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 18, 20, 22, 25, 30, 35, 40, 50, 60)
S_RUN = 60
NONE = 10 ** 6


@dataclasses.dataclass(frozen=True)
class Rule:
    start: int
    pieces: tuple            # ((s_upper, alpha), ...), increasing s_upper, the last 60

    def alpha(self, Sat):
        S = Sat.astype(np.int64)
        out = np.zeros(S.shape)
        lo = 0
        for s_up, a in self.pieces:
            out = np.where((S > lo) & (S <= s_up), a, out)
            lo = s_up
        return np.where(S >= self.start, out, 0.0)

    def label(self):
        parts, lo = [], self.start
        for s_up, a in self.pieces:
            parts.append(f"{a:g} S{lo}-{s_up}")
            lo = s_up + 1
        return "looks from " + str(self.start) + ": " + ", ".join(parts)

    def key(self):
        return json.dumps([self.start, [list(p) for p in self.pieces]])

    @staticmethod
    def of(text):
        s, pcs = json.loads(text) if isinstance(text, str) else text
        return Rule(int(s), tuple((int(a), float(b)) for a, b in pcs))


def look_mask(d, sfx, start):
    """PREREG-EVL-6 section 2: look k at the first close adding a block at which S >= S_k and the minimums hold; every
    threshold reached by then is consumed by that look; no look after the run's 60th block."""
    Sat = d[f"Sat{sfx}"].astype(np.int64)
    ok = d[f"has{sfx}"] & d[f"mn{sfx}"] & (Sat <= S_RUN)
    sl = np.array([s for s in LOOKS if s >= start])
    R, T = Sat.shape
    out = np.zeros((R, T), bool)
    nxt = np.zeros(R, np.int64)
    for t in range(T):
        live = nxt < sl.size
        thr = sl[np.minimum(nxt, sl.size - 1)]
        hit = ok[:, t] & live & (Sat[:, t] >= thr)
        if hit.any():
            out[hit, t] = True
            nxt[hit] = (Sat[hit, t][:, None] >= sl[None, :]).sum(axis=1)
    return out


_LM: dict = {}


def _lm(d, sfx, start, tag):
    k = (tag, sfx, start)
    if k not in _LM:
        _LM[k] = look_mask(d, sfx, start)
    return _LM[k]


def first_pass(d, sfx, rule, tag=None, variant="w"):
    """(first pass session, first retirement session, the session the run ended at its 60th block), 1-based, NONE when
    it never happens within the arrays. variant 'w' = this file's test; 'u' = the judge's (unweighted, no top guard)."""
    lm = _lm(d, sfx, rule.start, tag) if tag is not None else look_mask(d, sfx, rule.start)
    Sat = d[f"Sat{sfx}"]
    al = rule.alpha(Sat)
    if variant == "w":
        P, g, iss = d[f"P{sfx}"], d[f"g{sfx}"], d[f"iss{sfx}"]
    else:
        P, g, iss = d[f"Pu{sfx}"], d[f"gu{sfx}"], d[f"issu{sfx}"]
    P = np.where(np.isnan(P), 9.0, P)
    pm = lm & g & iss & (P <= al)
    fp = np.where(pm.any(axis=1), pm.argmax(axis=1) + 1, NONE)
    Q = d[f"Q{sfx}"]
    Q = np.where(np.isnan(Q), 9.0, Q)
    rm = lm & d[f"neg{sfx}"] & (Q <= al + TIE)
    fr = np.where(rm.any(axis=1), rm.argmax(axis=1) + 1, NONE)
    fp = np.where(fp < fr, fp, NONE)
    fr = np.where(fr < fp, fr, NONE)
    s60 = Sat.astype(np.int64) >= S_RUN
    fe = np.where(s60.any(axis=1), s60.argmax(axis=1) + 1, NONE)
    fe = np.where((fp == NONE) & (fr == NONE), fe, NONE)
    return fp, fr, fe


def two_runs(d, rule, tag=None, variant="w"):
    """Run 1 and, where it ended unpassed, run 2: the first pass of either (NONE if neither)."""
    fp, fr, fe = first_pass(d, "", rule, tag, variant)
    if "Sat_2" not in d:
        return fp, None
    fp2, fr2, _ = first_pass(d, "_2", rule, tag, variant)
    any_ = np.where(fp < NONE, fp, np.where(fe < NONE, fp2, NONE))
    return fp, any_


# ------------------------------------------------------------------------------------------------ cells
def load_index(phases):
    rows = []
    for ph in phases:
        rows += [json.loads(l) for l in open(os.path.join(HERE, f"calib_final.{ph}.index.jsonl"))]
    groups: dict = {}
    for r in rows:
        key = (r["cell"], json.dumps(r["gen"], sort_keys=True), r["T"])
        groups.setdefault(key, []).append(r)
    return groups


def load_cell(rs):
    arrs: dict = {}
    for r in sorted(rs, key=lambda r: r["seed"]):
        with np.load(r["path"]) as z:
            for k in z.files:
                arrs.setdefault(k, []).append(z[k])
    return {k: np.concatenate(v) for k, v in arrs.items()}


def plausible(cell, gen):
    """THE WORST PLAUSIBLE SET (D1): rho_day <= 0.15, phi_day <= 0.20, drift <= 20 bp at AR <= 0.97, symmetric days or
    5% crash days, any event shape, issuer effects; the N3 and N1 nulls; no stress or other structure."""
    if cell.startswith(("S|", "X|", "P")):
        return False
    if gen.get("rho_day", 0) > 0.15 + 1e-9 or gen.get("phi_day", 0.10) > 0.20 + 1e-9:
        return False
    if gen.get("drift_sd", 0) > 0.0020 + 1e-9 or gen.get("drift_rho", 0.97) > 0.97 + 1e-9:
        return False
    if gen.get("day", "t3") not in ("t3", "crash"):
        return False
    return True


def is_null(cell):
    return cell.startswith(("N3", "N1", "S|", "X|")) and "N2+" not in cell


def lab(cell, gen, T):
    return f"{cell} n{gen['nbar']:g} rho{gen['rho_day']:.2f} T{T}"


def rate(f, H):
    return float(np.mean(f <= H))


def power_row(fp, fr, fe, T):
    out = {h: rate(fp, h) for h in (6, 7, 8, 10, 12, 15, 20, 30, 40, 60, 120) if h <= T}
    out["E60"] = float(np.mean(np.minimum(fp, 60)))          # E[min(first promotion, 60)] (NONE -> 60)
    out["end"] = float(np.mean(fe < NONE))                   # run 1 ended at its 60th block unpassed (D2)
    out["ret"] = float(np.mean(fr < NONE))                   # retired by the lower tail
    out["med"] = None if np.median(np.where(fp < NONE, fp, 1e9)) >= 1e9 else float(np.median(np.where(fp < NONE, fp, 1e9)))
    return out


# ------------------------------------------------------------------------------------------------ candidates
def candidates(starts=(6, 7, 8)):
    out = []
    for start in starts:
        for a1 in (0.010, 0.012, 0.014, 0.016):
            if start == 6 and a1 < 1 / 64:
                continue                       # an S=6 look that can never pass is a start at 7
            for s1 in (8, 9, 10, 11, 12, 14, 16):
                if s1 < start and not (start > 8 and s1 == 16):
                    continue
                for a2 in (0.005, 0.006, 0.007, 0.008, 0.009, 0.010, 0.011, 0.012):
                    if a2 > a1:
                        continue
                    for a3 in (0.0015, 0.002, 0.0025, 0.003, 0.0035, 0.004):
                        if a3 > a2:
                            continue
                        out.append(Rule(start, ((s1, a1), (20, a2), (60, a3))))
    # the checks' named candidates and the draft's rule, exactly
    out += [Rule(6, ((9, 0.016), (20, 0.012), (60, 0.003))),          # check 1
            Rule(7, ((10, 0.016), (20, 0.010), (60, 0.003))),         # check 2 (a)
            Rule(6, ((20, 0.012), (60, 0.003))),                      # check 2 (b), the draft's 4.4 fallback
            Rule(6, ((20, 0.016), (60, 0.004)))]                      # the judge's draft
    seen, uniq = set(), []
    for r in out:
        if r.key() not in seen:
            seen.add(r.key())
            uniq.append(r)
    return uniq


_DATA: dict = {}


def _load(null_phases, power_phases):
    nulls = load_index(null_phases) if null_phases else {}
    powers = load_index(power_phases) if power_phases else {}
    cells = []
    for key, rs in list(nulls.items()) + list(powers.items()):
        cell, gen, T = key[0], json.loads(key[1]), key[2]
        cells.append({"cell": cell, "gen": gen, "T": T, "R": sum(r["R"] for r in rs), "d": load_cell(rs),
                      "tag": (rs[0]["phase"],) + key, "info": [r["info"] for r in rs]})   # the look-mask cache key
    return cells


def evaluate(rule, cells, variant="w", H=120):
    worst = (0.0, None)
    stress = (0.0, None)
    base = []
    nulls, power = [], {}
    for c in cells:
        g, d = c["gen"], c["d"]
        if c["cell"].startswith("P"):
            fp, fr, fe = first_pass(d, "", rule, c["tag"], variant)
            key = (round(g["skill"] * 1e4), g["rho_day"], g["nbar"], c["T"])
            power[key] = power_row(fp, fr, fe, c["T"])
            continue
        if not is_null(c["cell"]):
            fp, fr, fe = first_pass(d, "", rule, c["tag"], variant)
            nulls.append({"lab": lab(c["cell"], g, c["T"]), "fp": rate(fp, min(H, c["T"])), "R": c["R"],
                          "plaus": False, "nonnull": True})
            continue
        fp, fr, fe = first_pass(d, "", rule, c["tag"], variant)
        v = rate(fp, min(H, c["T"]))
        row = {"lab": lab(c["cell"], g, c["T"]), "fp": v, "R": c["R"], "plaus": plausible(c["cell"], g),
               "ret": float(np.mean(fr < NONE)), "end": float(np.mean(fe < NONE))}
        if "Sat_2" in d:
            _, any_ = two_runs(d, rule, c["tag"], variant)
            row["fp_two_runs"] = rate(any_, min(H, c["T"]))
        nulls.append(row)
        if row["plaus"]:
            if v > worst[0]:
                worst = (v, row["lab"])
        elif v > stress[0]:
            stress = (v, row["lab"])
        if c["cell"].startswith("N3|sym|nodrift|phi0.10") and abs(g["rho_day"] - 0.05) < 1e-9:
            base.append((g["nbar"], v))
    return {"worst": worst, "stress": stress, "base": sorted(base, reverse=True), "nulls": nulls, "power": power}


def speed(res, skill=60, rho=0.05, rates=(85, 30, 13, 8, 3)):
    """THE SPEED (D1): E[min(first promotion, 60 sessions)] at a true edge, the mean over the five rates (lower is
    faster); and P(promoted by session h), the mean over the five rates."""
    rows = [v for (sk, r, n, T), v in res["power"].items() if sk == skill and abs(r - rho) < 1e-9 and n in rates]
    if not rows:
        return {}
    out = {"E60": float(np.mean([r["E60"] for r in rows]))}
    for h in (8, 10, 15, 20, 40, 60):
        out[h] = float(np.mean([r[h] for r in rows if h in r]))
    out["end"] = float(np.mean([r["end"] for r in rows]))
    return out


def _one(rule):
    res = evaluate(rule, _DATA["cells"])
    sp60, sp100 = speed(res, 60), speed(res, 100)
    top = sorted([n for n in res["nulls"] if n["plaus"]], key=lambda n: -n["fp"])[:12]
    return {"rule": rule.key(), "label": rule.label(), "worst": res["worst"], "stress": res["stress"],
            "base": res["base"], "speed60": sp60, "speed100": sp100, "top": [(n["lab"], n["fp"]) for n in top]}


def grid(null_phases, power_phases, out_path, workers, starts=(6, 7, 8)):
    from multiprocessing import get_context
    _DATA["cells"] = _load(null_phases, power_phases)
    for c in _DATA["cells"]:            # the look masks once, in the parent (shared by the forked workers)
        for start in starts:
            _lm(c["d"], "", start, c["tag"])
    rules = candidates(starts)
    if starts != (6, 7, 8):
        named = {r.key() for r in candidates((6, 7, 8))[-4:]}
        rules = [r for r in rules if r.key() not in named]
    print(f"{len(rules)} rules on {len(_DATA['cells'])} cells", flush=True)
    with get_context("fork").Pool(workers) as pool, open(out_path, "w") as fh:
        for i, row in enumerate(pool.imap_unordered(_one, rules, chunksize=4)):
            fh.write(json.dumps(row) + "\n")
            if i % 200 == 0:
                print(f"{i}/{len(rules)}", flush=True)


def show(rule, null_phases, power_phases, variant="w", out=sys.stdout):
    cells = _load(null_phases, power_phases)
    res = evaluate(rule, cells, variant)
    print(f"RULE {rule.label()} ({variant})", file=out)
    print(f"worst plausible {res['worst'][0]:.4f} [{res['worst'][1]}]; stress worst {res['stress'][0]:.4f} "
          f"[{res['stress'][1]}]; base {res['base']}", file=out)
    for n in sorted(res["nulls"], key=lambda n: n["lab"]):
        se = math.sqrt(max(n["fp"] * (1 - n["fp"]), 1e-12) / n["R"])
        extra = f" two-runs {n['fp_two_runs']:.4f}" if "fp_two_runs" in n else ""
        tag = "P" if n["plaus"] else ("-" if n.get("nonnull") else "S")
        print(f"  {tag} {n['lab']:58s} R{n['R']:5d} fp {n['fp']:.4f} (se {se:.4f}){extra} "
              f"ret {n.get('ret', float('nan')):.3f} end {n.get('end', float('nan')):.3f}", file=out)
    for k, v in sorted(res["power"].items()):
        print(f"  POWER {k}: " + " ".join(f"{h}:{x:.3f}" if isinstance(x, float) else f"{h}:{x}" for h, x in v.items()),
              file=out)
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["grid", "show"])
    ap.add_argument("--null", default="")
    ap.add_argument("--power", default="")
    ap.add_argument("--out", default=None)
    ap.add_argument("--rule", default=None)
    ap.add_argument("--variant", default="w")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--starts", default="6,7,8")
    a = ap.parse_args()
    nph = [p for p in a.null.split(",") if p]
    pph = [p for p in a.power.split(",") if p]
    if a.cmd == "grid":
        grid(nph, pph, a.out, min(a.workers, 8), tuple(int(x) for x in a.starts.split(",")))
    else:
        show(Rule.of(a.rule), nph, pph, a.variant)
