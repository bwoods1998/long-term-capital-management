#!/usr/bin/env python
"""search_v2.py: the D14 search on the WIDENED plausible grid (synthetic only).

The rule evaluation is search_final.py's, unchanged (looks, alpha(S), PASS with no tolerance, RETIRE at
q <= alpha + 1e-12, the end of a run at its 60th block, run 2). This file adds:
  - the arrays of calib_v2.py (index files calib_v2.<phase>.index.jsonl) beside calib_final.py's;
  - THE WORST PLAUSIBLE SET of D14: section 4.3's grid (calib_final's plausible cells) plus calib_v2's widened cells:
    t(3)-body crash days, crash days clustered in high-volatility regimes, both together, and counts that follow the
    size of the day shock (knife on money weights) at 3, 5 and 8 events a session, every drift, rho_day <= 0.15,
    phi_day <= 0.20;
  - a wider candidate set: first looks at the 9th to the 16th block, alpha in three pieces a1 (0.006-0.016) to
    S = s1, a2 (0.003-0.012) to S = 20, a3 (0.001-0.004) to S = 60, beside the earlier search's rules.

Usage:
  search_v2.py grid --null s1null,w1 --power s1power --out search_v2.jsonl
  search_v2.py grid --null s1null,w1 --power s1power --out search_v2b.jsonl --set b   (the second pass)
  search_v2.py grid --null s1null,w1 --power s1power --out search_v2c.jsonl --set c   (the edge check)
  search_v2.py show --rule JSON --null PHASES [--power PHASES]
"""
from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import search_final as SF  # noqa: E402

OLD_PHASES = {"s1null", "s1power", "s2null", "s2power", "s3null", "stress", "s2extra", "pilot"}
NEW_DAYS = ("crasht3", "crashcl", "crasht3cl")


def index_path(ph):
    return os.path.join(HERE, f"calib_final.{ph}.index.jsonl" if ph in OLD_PHASES else f"calib_v2.{ph}.index.jsonl")


def load_index(phases):
    rows = []
    for ph in phases:
        rows += [json.loads(l) for l in open(index_path(ph))]
    groups: dict = {}
    for r in rows:
        key = (r["cell"], json.dumps(r["gen"], sort_keys=True), r["T"])
        groups.setdefault(key, []).append(r)
    return groups


def plausible(cell, gen):
    """D14's WORST PLAUSIBLE SET: rho_day <= 0.15, phi_day <= 0.20, a drift of <= 20 bp at AR 0.97, the volatility
    regime at AR 0.90; days symmetric t(3), crash days (normal body), t(3)-body crash days, clustered crash days, or
    both; any event shape; issuer effects; counts independent of the day, or following the day shock's size (kappa
    0.3, money knife) at 3, 5 or 8 events a session; the N3 and N1 nulls; no stress or other structure."""
    if cell.startswith(("S|", "X|", "P")):
        return False
    if gen.get("rho_day", 0) > 0.15 + 1e-9 or gen.get("phi_day", 0.10) > 0.20 + 1e-9:
        return False
    if gen.get("drift_sd", 0) > 0.0020 + 1e-9 or abs(gen.get("drift_rho", 0.97) - 0.97) > 1e-9:
        return False
    if abs(gen.get("vol_rho", 0.90) - 0.90) > 1e-9 or gen.get("vol_sd", 0.30) > 0.30 + 1e-9:
        return False
    if gen.get("day", "t3") not in ("t3", "crash") + NEW_DAYS:
        return False
    if gen.get("kappa", 0) or gen.get("lam", 0) or gen.get("drift_day_corr", 0):
        return False
    if gen.get("cnt_kappa", 0):
        if abs(gen["cnt_kappa"] - 0.3) > 1e-9 or not gen.get("mw_knife") or gen["nbar"] not in (3, 5, 8):
            return False
    return True


# the evaluation reads these through search_final's module globals
SF.plausible = plausible
SF.load_index = load_index

RECHECK1 = SF.Rule(12, ((14, 0.012), (20, 0.006), (60, 0.0025)))       # re-check 1's candidate (D14's start)
PREV = SF.Rule(9, ((14, 0.012), (20, 0.010), (60, 0.004)))             # the previous round's chosen rule
STRICTEST = SF.Rule(12, ((12, 0.010), (20, 0.005), (60, 0.0015)))      # the previous shortlist's strictest


def candidates2():
    out = []
    for start in (9, 10, 11, 12, 13, 14, 16):
        for a1 in (0.006, 0.008, 0.010, 0.012, 0.014, 0.016):
            for s1 in sorted({start, 12, 14, 16}):
                if s1 < start:
                    continue
                for a2 in (0.003, 0.004, 0.005, 0.006, 0.007, 0.008, 0.010, 0.012):
                    if a2 > a1:
                        continue
                    for a3 in (0.001, 0.0015, 0.002, 0.0025, 0.003, 0.004):
                        if a3 > a2:
                            continue
                        out.append(SF.Rule(start, ((s1, a1), (20, a2), (60, a3))))
    old = json.load(open(os.path.join(HERE, "shortlist.json")))      # the previous round's shortlist, for the record
    out += [SF.Rule.of(k) for k in old] + [RECHECK1, PREV, STRICTEST]
    seen, uniq = set(), []
    for r in out:
        if r.key() not in seen:
            seen.add(r.key())
            uniq.append(r)
    return uniq


def candidates2b():
    """THE SECOND PASS on the same search seeds: the first pass's frontier sat on its grid's edge (a first look at the
    16th block with a1 = 0.016 and a2 = 0.012, the largest values searched), so the search widens there: first looks at
    the 14th, 15th, 16th, 18th and 20th block, a1 up to 0.020 (the largest alpha the arrays' issuer guard covers), the
    middle piece to S = 20, 25 or 30 with a2 up to 0.016, a3 0.001-0.004."""
    out = []
    for start in (14, 15, 16, 18, 20):
        for a1 in (0.012, 0.014, 0.016, 0.018, 0.020):
            for s1 in sorted({start, 16, 18, 20}):
                if s1 < start:
                    continue
                for mid in (20, 25, 30):
                    if mid <= s1:
                        continue
                    for a2 in (0.004, 0.006, 0.008, 0.010, 0.012, 0.014, 0.016):
                        if a2 > a1:
                            continue
                        for a3 in (0.001, 0.0015, 0.002, 0.0025, 0.003, 0.004):
                            if a3 > a2:
                                continue
                            out.append(SF.Rule(start, ((s1, a1), (mid, a2), (60, a3))))
    done = {json.loads(l)["rule"] for l in open(os.path.join(HERE, "search_v2.jsonl"))}
    seen, uniq = set(done), []
    for r in out:
        if r.key() not in seen:
            seen.add(r.key())
            uniq.append(r)
    return uniq


def candidates2c():
    """THE EDGE CHECK on the same search seeds: the selection chose a first look at the 20th block, the largest the
    second pass searched, so first looks at the 22nd and 25th block are measured too: a1 0.014-0.020 to S = s1 (22, 25
    or 30), the middle piece to S = 30, 35 or 40 with a2 0.004-0.016, a3 0.001-0.004."""
    out = []
    for start in (22, 25):
        for a1 in (0.014, 0.016, 0.018, 0.020):
            for s1 in (22, 25, 30):
                if s1 < start:
                    continue
                for mid in (30, 35, 40):
                    if mid <= s1:
                        continue
                    for a2 in (0.004, 0.006, 0.008, 0.010, 0.012, 0.014, 0.016):
                        if a2 > a1:
                            continue
                        for a3 in (0.001, 0.0015, 0.002, 0.0025, 0.003, 0.004):
                            if a3 > a2:
                                continue
                            out.append(SF.Rule(start, ((s1, a1), (mid, a2), (60, a3))))
    done = set()
    for f in ("search_v2.jsonl", "search_v2b.jsonl"):
        done |= {json.loads(l)["rule"] for l in open(os.path.join(HERE, f))}
    seen, uniq = set(done), []
    for r in out:
        if r.key() not in seen:
            seen.add(r.key())
            uniq.append(r)
    return uniq


def grid(null_phases, power_phases, out_path, workers, which="a"):
    from multiprocessing import get_context
    SF._DATA["cells"] = SF._load(null_phases, power_phases)
    rules = {"a": candidates2, "b": candidates2b, "c": candidates2c}[which]()
    starts = sorted({r.start for r in rules})
    for c in SF._DATA["cells"]:          # the look masks once, in the parent (shared by the forked workers)
        for start in starts:
            SF._lm(c["d"], "", start, c["tag"])
    print(f"{len(rules)} rules on {len(SF._DATA['cells'])} cells "
          f"({sum(1 for c in SF._DATA['cells'] if plausible(c['cell'], c['gen']))} plausible)", flush=True)
    with get_context("fork").Pool(workers) as pool, open(out_path, "w") as fh:
        for i, row in enumerate(pool.imap_unordered(SF._one, rules, chunksize=8)):
            fh.write(json.dumps(row) + "\n")
            if i % 500 == 0:
                print(f"{i}/{len(rules)}", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["grid", "show"])
    ap.add_argument("--null", default="")
    ap.add_argument("--power", default="")
    ap.add_argument("--out", default=None)
    ap.add_argument("--rule", default=None)
    ap.add_argument("--variant", default="w")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--set", default="a")
    a = ap.parse_args()
    nph = [p for p in a.null.split(",") if p]
    pph = [p for p in a.power.split(",") if p]
    if a.cmd == "grid":
        grid(nph, pph, a.out, min(a.workers, 8), a.set)
    else:
        SF.show(SF.Rule.of(a.rule), nph, pph, a.variant)
