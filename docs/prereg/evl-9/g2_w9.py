#!/usr/bin/env python
"""g2_w9.py: SYNTHETIC check that PREREG-EVL-9's fixed G2 (section 6.1; the captain's W2, check 2's blocker) PASSES a
correct build and VOIDS a broken one. No lane data, no price: candidate sets, stated skews and feature values are drawn
at random at stated rates; nothing is calibrated to any real figure.

THE FIXED G2 (section 6.1), as simulated:
  - per pool program p, pooled over its overlap sessions (3-6 here): the live side is p's intents of each session as
    (session, CIK); the history side is the twin over the vault for the same sessions, with p's own registration floor,
    p's one-position state read from the export's intents and KEPT / TRADABLE at the House's E_prev (cause b, c);
  - THE STATED SKEWS ARE REMOVED FROM BOTH SIDES before comparing (each counted): a (session, CIK) any of whose in-window
    articles the vault marks edited (updated_at > created_at + 10 minutes); any of whose in-window events the House
    stored after tau; and any whose live eligibility and the twin's point-in-time eligibility differ;
  - SETS: per learner pooled over its programs, d (pairs in one side only) <= 0.10 x u (pairs in either) + 2, and per
    program with >= 50 pooled pairs d <= 0.15 x u + 2; for EVL-ERN-DROP-ON and EVL-CTRL-ERN-UNDER-ON (history reads no
    verdict, cause d) the live pairs outside history <= 0.05 x the live pairs + 2 pooled, <= 0.10 x + 2 per program;
  - FEATURES on matched pairs, per learner pooled over its programs, BOTH sides by features() with the history reading
    (stored = knowable; edited articles excluded), each raw column BEFORE within-session ranking (cause a): unequal
    (beyond 1e-9 relative) on at most 0.05 x the pairs + 2; primary events' knowable times more than 1 second apart on
    at most 0.01 x the pairs + 2.
A correct build differs from live only by the stated skews (removed) and by residual mapping differences (an article's
symbol mapped to another CIK, a co-registered 8-K's CIK) at a rate m. Broken builds: the window a session late; every
knowable time 4 hours late (S1's acceptanceDateTime's Eastern-as-Z error); the EVL-INS-BUY-O1 director test by comma
split instead of the substring rule (S2's 'DirectorOther'); n_art counting multi-symbol articles; KEPT at E_REF $2,000
instead of E_prev (cause b, the draft's G2); the draft's G2 (whole-kept-set rank columns compared) on a CORRECT build.
Usage: g2_w9.py   (writes g2_w9.out.json)
"""
import json
import math
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
PROGS = {   # program: (candidates a session before merging, share of article events, containment rule)
    "EVL-CTRL-NEWS-ALL-O1": (300, 1.0, False), "EVL-CTRL-8K-ALL-O1": (60, 0.0, False),
    "EVL-CTRL-ERN-ALL-O1": (20, 0.0, False), "EVL-INS-BUY-O1": (5, 0.0, False),
    "EVL-CTRL-NEWS-DAY-ON": (450, 1.0, False), "EVL-CTRL-NEWSPM-ON": (220, 1.0, False),
    "EVL-CTRL-8K-ON": (25, 0.0, False), "EVL-ERN-REACT-ON": (12, 0.0, False),
    "EVL-ERN-DROP-ON": (4, 0.0, True), "EVL-CTRL-ERN-UNDER-ON": (6, 0.0, True)}
NCOL = 40                    # raw columns compared (the rank columns' raw quantities included)


def rank(v):
    order = np.argsort(v, kind="mergesort")
    r = np.empty(len(v))
    r[order] = np.arange(1, len(v) + 1)
    vals, inv = np.unique(v, return_inverse=True)
    sums = np.bincount(inv, weights=r)
    cnt = np.bincount(inv)
    return ((sums / cnt)[inv] - 0.5) / len(v)


def one_program(rng, name, sessions, edit, late, elig, m, bug):
    n0, art, contain = PROGS[name]
    d = u = live_out = live_n = 0
    feat_ok = np.zeros(NCOL)
    time_ok = 0
    npairs = 0
    removed = 0
    rank_ok = []
    for s in range(sessions):
        n = rng.poisson(n0 * rng.gamma(3.0, 1 / 3.0))
        if n == 0:
            continue
        cik = rng.choice(10**6, size=n, replace=False)
        live = set(cik.tolist())
        # the history side of a correct build: the same pairs, less residual mapping differences, plus as many others
        hist = set(cik.tolist())
        k = rng.binomial(n, m)
        if k:
            gone = rng.choice(cik, size=k, replace=False)
            hist -= set(gone.tolist())
            hist |= set((10**6 + rng.integers(0, 10**6, k) + s * 10**7).tolist())
        if contain:      # history reads no verdict: it holds every live pair and more
            hist |= set((2 * 10**7 + rng.integers(0, 10**6, rng.poisson(0.5 * n + 1))).tolist())
        if bug == "window":        # the twin reads the session before's window: a fresh draw of the pool
            hist = set((3 * 10**7 + s * 10**6 + rng.integers(0, 10**6, len(hist))).tolist()) | set(
                rng.choice(list(hist), size=max(0, int(0.05 * len(hist))), replace=False).tolist())
        if bug == "eref":          # KEPT at E_REF $2,000 against E_prev: names priced (151.84, 160] differ
            k2 = rng.binomial(n, 0.012)
            hist |= set((4 * 10**7 + rng.integers(0, 10**6, k2)).tolist())
        if bug == "tz4h" and art == 0.0:   # every knowable time 4 hours late: a filing knowable 4 h later leaves
            k3 = rng.binomial(n, 0.22)      # the window when its acceptance falls in its last 4 hours (about 22%)
            if k3:
                hist -= set(rng.choice(cik, size=k3, replace=False).tolist())
        if bug == "director" and name == "EVL-INS-BUY-O1":
            k4 = rng.binomial(n, 0.12)      # 'DirectorOther' and 'Director,TenPercentOwnerOther' owners
            if k4:
                hist -= set(rng.choice(cik, size=k4, replace=False).tolist())
        # the stated skews, removed from BOTH sides (counted)
        uni = np.array(sorted(live | hist))
        pr = 1 - (1 - (edit if art else 0.0)) * (1 - late) * (1 - elig)
        drop = set(uni[rng.random(len(uni)) < pr].tolist())
        removed += len(drop)
        L, H = live - drop, hist - drop
        if contain:
            live_out += len(L - H)
            live_n += len(L)
        else:
            d += len(L ^ H)
            u += len(L | H)
        both = L & H
        nb = len(both)
        npairs += nb
        if nb:
            # raw columns: equal on a correct build except residual per-value mapping noise at rate m / 4
            bad = rng.random((nb, NCOL)) < m / 4
            if bug == "nart":
                bad[:, 0] |= rng.random(nb) < (0.35 if art else 0.0)    # multi-symbol articles counted
            if bug == "tz4h":
                tbad = np.ones(nb, dtype=bool)
            else:
                tbad = rng.random(nb) < 0.002
            feat_ok += (~bad).sum(axis=0)
            time_ok += int((~tbad).sum())
            if bug is None:     # the draft's rank comparison: ranks over each side's whole kept set (correct build)
                allc = np.array(sorted(L | H))
                q = rng.integers(20, 200, size=len(allc)).astype(float)
                la = np.array(sorted(L))
                ha = np.array(sorted(H))
                rl = rank(q[np.searchsorted(allc, la)])
                rh = rank(q[np.searchsorted(allc, ha)])
                _, il, ih = np.intersect1d(la, ha, return_indices=True)
                a_, b_ = rl[il], rh[ih]
                rank_ok.append(float(np.mean(np.abs(a_ - b_) <= 1e-9 * np.maximum(1, np.maximum(np.abs(a_), np.abs(b_))))))
    draft_ok = (not rank_ok) or float(np.mean(rank_ok)) >= 0.90
    return dict(contain=contain, d=d, u=u, live_out=live_out, live_n=live_n, npairs=npairs,
                feat_bad=npairs - feat_ok, time_bad=npairs - time_ok, draft_ok=draft_ok, removed=removed)


def trial(rng, edit, late, elig, m, bug, sessions):
    """THE FIXED G2's decision on one simulated build: per program with >= 50 pooled pairs the set test (d <= 0.10 u + 2;
    0.15 per program, containment for the two verdict-reading members); per learner pooled over its programs the set
    test at 0.10, every column's
    feature test (at most 0.05 x pairs + 2 unequal) and the knowable-time test (at most 0.01 x pairs + 2 apart)."""
    ok = True
    draft = True
    for learner in ("O1", "ON"):
        rows = [one_program(rng, name, sessions, edit, late, elig, m, bug) for name in PROGS if name.endswith(learner)]
        for r in rows:
            draft &= r["draft_ok"]
            if r["contain"]:
                if r["live_n"] >= 50:
                    ok &= r["live_out"] <= 0.10 * r["live_n"] + 2
            elif r["u"] >= 50:
                ok &= r["d"] <= 0.15 * r["u"] + 2
        D_ = sum(r["d"] for r in rows if not r["contain"])
        U_ = sum(r["u"] for r in rows if not r["contain"])
        ok &= D_ <= 0.10 * U_ + 2
        lo = sum(r["live_out"] for r in rows if r["contain"])
        ln = sum(r["live_n"] for r in rows if r["contain"])
        ok &= lo <= 0.05 * ln + 2
        npairs = sum(r["npairs"] for r in rows)
        if npairs:
            fb = sum(r["feat_bad"] for r in rows)
            ok &= bool((fb <= 0.05 * npairs + 2).all())
            ok &= sum(r["time_bad"] for r in rows) <= 0.01 * npairs + 2
    return ok, draft


def main():
    rng = np.random.default_rng(20261022_9)
    out = {}
    N = 200
    for edit in (0.05, 0.20, 0.40):
        for late, elig in ((0.01, 0.01), (0.05, 0.05)):
            for m in (0.0, 0.02, 0.04):
                for sess in (3, 6):
                    res = [trial(rng, edit, late, elig, m, None, sess) for _ in range(N)]
                    out[f"correct|edit{edit}|late{late}|elig{elig}|map{m}|sessions{sess}"] = {
                        "pass": float(np.mean([r[0] for r in res])), "draft_rank_rule_pass": float(np.mean([r[1] for r in res]))}
    for bug in ("window", "tz4h", "director", "nart", "eref"):
        for sess in (3, 6):
            res = [trial(rng, 0.20, 0.01, 0.01, 0.02, bug, sess) for _ in range(N)]
            out[f"broken:{bug}|sessions{sess}"] = {"pass": float(np.mean([r[0] for r in res]))}
    worst = min(v["pass"] for k, v in out.items() if k.startswith("correct"))
    g2bugs = ("window", "tz4h", "nart")
    out["SUMMARY"] = {"correct_build_pass_min": worst,
                      "correct_build_draft_rule_pass_max": max(v["draft_rank_rule_pass"] for k, v in out.items()
                                                               if k.startswith("correct")),
                      "broken_build_pass_max (window, tz4h, nart: G2's to catch)": max(
                          v["pass"] for k, v in out.items() if k.startswith("broken") and k.split(":")[1].split("|")[0] in g2bugs),
                      "director (INS-BUY's few events: G2b's to catch, not G2's)": max(
                          v["pass"] for k, v in out.items() if k.startswith("broken:director")),
                      "eref (a 1.2% set difference G2's tolerance absorbs: E_prev is used by rule)": max(
                          v["pass"] for k, v in out.items() if k.startswith("broken:eref")),
                      "trials_a_cell": N}
    print(json.dumps(out, indent=1))
    json.dump(out, open(os.path.join(HERE, "g2_w9.out.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
