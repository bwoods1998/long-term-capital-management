#!/usr/bin/env python
"""g2_w9ff.py: SYNTHETIC check of G2 as the final minimal fix writes it (re-check 2's blocker and its major 5). No lane
data, no price: candidate sets, statuses, stated skews, bar revisions and feature values are drawn at random at stated
rates; nothing is calibrated to any real figure.

WHAT IS NEW AGAINST g2_w9.py (the fix round's, which drew the live side as the history side less a mapping noise):
  THE SHADOW'S ONE-POSITION MECHANICS (release 1019h programs.write_intents / _held_recently): each pool program draws
  its candidates of a session from 3,000 issuers by Zipf(0.8) popularity without replacement (the lens generator's
  issuer law, re-check 2's rc2_held.py), writes ONE intent per candidate, and marks `skipped:issuer-held` every
  candidate whose issuer has a non-skipped intent of the program entering in the 5 sessions before (a 1-session hold);
  the others are planned (later status moves, no-auction, excluded, taken, limit, keep their pair).
  THE FIXED LIVE SIDE (G2 (2)): p's intents of each overlap session EXCEPT those written at decision as
  `skipped:issuer-held` or `skipped:no-exit-session`. THE FIXED HISTORY SIDE (G2 (3)): the twin's candidates (the live
  candidates less a residual mapping difference m, plus as many others) with p's one-position rule applied from the
  EXPORT's NON-SKIPPED intents of p (programs._held_recently's reading).
  THE "EVERY STATUS" READING (the text the re-check found): the live side keeps every status.
  BAR VINTAGE (re-check 2's major 5): a share vc of name-days has a revised close in the vault (fetched days later)
  against the House's bars; a pair's bar-derived column (sig20 over 20 closes) differs when any of its 20 name-days
  does. THE OLD READING compares features from the vault's bars against the House's; THE FIXED READING computes both
  sides from the EXPORT's bars (G2 (6)), and tests the vault's bars against the export's separately (G2 (7): closes
  equal within 1e-9 on >= 99% of name-days, volumes within 1e-3 relative on >= 95%; a share vv of name-days has a
  revised volume), the differing name-days' pairs removed as a stated skew.
THE REST is g2_w9.py's: overlap sessions 3, 6 or 10 per program (B7's export now covers every lane session from
2026-10-19 decided before it); stated skews removed from both sides (edited articles, late storage, eligibility or
SYMBOL disagreements, e.g. multi-class names); SETS: per learner pooled over its programs d <= 0.10 u + 2, per program
with u >= 50 d <= 0.15 u + 2, CONTAINMENT for EVL-ERN-DROP-ON and EVL-CTRL-ERN-UNDER-ON (live pairs outside history
<= 0.05 x live + 2 pooled, <= 0.10 x + 2 per program with >= 50); FEATURES on matched pairs pooled per learner, each raw
column unequal on at most 0.05 x pairs + 2, knowable times more than 1 s apart on at most 0.01 x pairs + 2.
BROKEN BUILDS: the window a session late; knowable times 4 hours late; n_art counting multi-symbol articles; the twin
WITHOUT the one-position rule; the twin's gap 4 sessions instead of 5; the vault's volumes from another feed.
Usage: g2_w9ff.py   (writes g2_w9ff.out.json)
"""
import json
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
PROGS = {   # program: (candidates a session before merging, share of article events, containment rule)
    "EVL-CTRL-NEWS-ALL-O1": (300, 1.0, False), "EVL-CTRL-8K-ALL-O1": (60, 0.0, False),
    "EVL-CTRL-ERN-ALL-O1": (20, 0.0, False), "EVL-INS-BUY-O1": (5, 0.0, False),
    "EVL-CTRL-NEWS-DAY-ON": (450, 1.0, False), "EVL-CTRL-NEWSPM-ON": (220, 1.0, False),
    "EVL-CTRL-8K-ON": (25, 0.0, False), "EVL-ERN-REACT-ON": (12, 0.0, False),
    "EVL-ERN-DROP-ON": (4, 0.0, True), "EVL-CTRL-ERN-UNDER-ON": (6, 0.0, True)}
NCOL = 38                    # raw columns compared besides the bar-derived one
U = 3000
LW = np.log(1.0 / np.arange(1, U + 1) ** 0.8)
GAP = 5


def zipf_draw(rng, n, exclude=None):
    g = LW + rng.gumbel(size=U)
    if exclude is not None and len(exclude):
        g[list(exclude)] = -np.inf
    n = min(n, U - 1)
    return set(np.argpartition(-g, n)[:n].tolist())


def one_program(rng, name, sessions, edit, late, elig, m, vc, vv, live_rule, feat_rule, bug):
    n0, art, contain = PROGS[name]
    last_live = {}           # issuer -> last session of a NON-SKIPPED live intent (the export's state)
    last_twin_own = {}       # the broken twin's own state (gap 4 / none)
    d = u = live_out = live_n = 0
    feat_bad = np.zeros(NCOL)
    bar_bad = time_bad = npairs = removed = 0
    nd_close_ok = nd_vol_ok = nd = 0
    for s in range(sessions):
        n = int(rng.poisson(n0 * rng.gamma(3.0, 1 / 3.0)))
        if n == 0:
            continue
        C = zipf_draw(rng, n)
        held = {i for i in C if i in last_live and s - last_live[i] <= GAP}
        planned = C - held
        for i in planned:
            last_live[i] = s
        live = set(C) if live_rule == "every" else set(planned)
        # the twin's candidates: the live candidates less a residual mapping difference, plus as many others
        H0 = set(C)
        k = int(rng.binomial(n, m))
        if k:
            gone = set(rng.choice(sorted(C), size=k, replace=False).tolist())
            H0 = (H0 - gone) | zipf_draw(rng, k, exclude=C)
        if contain:          # history reads no verdict: more candidates
            H0 |= zipf_draw(rng, int(rng.poisson(0.5 * n + 1)), exclude=H0)
        if bug == "window":  # the twin reads the session before's window: another draw of the pool
            H0 = zipf_draw(rng, len(H0)) | set(rng.choice(sorted(H0), size=max(0, int(0.05 * len(H0))), replace=False).tolist())
        if bug == "tz4h" and art == 0.0:
            k3 = int(rng.binomial(n, 0.22))
            if k3:
                H0 -= set(rng.choice(sorted(H0), size=min(k3, len(H0)), replace=False).tolist())
        # the twin's one-position rule
        if bug == "noheld":
            H = set(H0)
        elif bug == "gap4":
            H = {i for i in H0 if not (i in last_live and last_live[i] < s and s - last_live[i] <= 4)}
        else:                # the export's non-skipped intents (planned before this session)
            H = {i for i in H0 if not (i in last_live and last_live[i] < s and s - last_live[i] <= GAP)}
        # the stated skews, removed from both sides (counted)
        uni = sorted(live | H)
        pr = 1 - (1 - (edit if art else 0.0)) * (1 - late) * (1 - elig)
        ua = np.array(uni, dtype=np.int64)
        drop = set(ua[rng.random(len(ua)) < pr].tolist())
        # G2 (7): the vault's bars against the export's, per name-day; pairs with a differing name-day removed
        bars_close = rng.random((len(uni), 20)) < vc
        bars_vol = rng.random((len(uni), 20)) < (0.5 if bug == "feed" else vv)
        nd += bars_close.size
        nd_close_ok += int((~bars_close).sum())
        nd_vol_ok += int((~bars_vol).sum())
        if feat_rule == "export":
            rev = set(ua[bars_close.any(axis=1) | bars_vol.any(axis=1)].tolist())
            drop |= rev
        removed += len(drop)
        L, Hs = live - drop, H - drop
        if contain:
            live_out += len(L - Hs)
            live_n += len(L)
        else:
            d += len(L ^ Hs)
            u += len(L | Hs)
        both = sorted(L & Hs)
        nb = len(both)
        npairs += nb
        if nb:
            bad = rng.random((nb, NCOL)) < m / 4
            if bug == "nart":
                bad[:, 0] |= rng.random(nb) < (0.35 if art else 0.0)
            feat_bad += bad.sum(axis=0)
            idx = np.searchsorted(ua, np.array(both))
            if feat_rule == "vault":     # the old reading: the history side's bars are the vault's
                bar_bad += int(bars_close[idx].any(axis=1).sum())
            else:                        # both sides from the export's bars: the same numbers
                bar_bad += int((rng.random(nb) < m / 4).sum())
            time_bad += int((np.ones(nb, bool) if bug == "tz4h" else rng.random(nb) < 0.002).sum())
    return dict(contain=contain, d=d, u=u, live_out=live_out, live_n=live_n, npairs=npairs, feat_bad=feat_bad,
                bar_bad=bar_bad, time_bad=time_bad, removed=removed, nd=nd, nd_close_ok=nd_close_ok,
                nd_vol_ok=nd_vol_ok)


def trial(rng, sessions, edit=0.20, late=0.01, elig=0.01, m=0.02, vc=0.0, vv=0.0, live_rule="fixed",
          feat_rule="export", bug=None):
    ok = True
    held_share = []
    for learner in ("O1", "ON"):
        rows = [one_program(rng, nm, sessions, edit, late, elig, m, vc, vv, live_rule, feat_rule, bug)
                for nm in PROGS if nm.endswith(learner)]
        for r in rows:
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
            ok &= sum(r["bar_bad"] for r in rows) <= 0.05 * npairs + 2
            ok &= sum(r["time_bad"] for r in rows) <= 0.01 * npairs + 2
        if feat_rule == "export":
            nd = sum(r["nd"] for r in rows)
            ok &= sum(r["nd_close_ok"] for r in rows) >= 0.99 * nd
            ok &= sum(r["nd_vol_ok"] for r in rows) >= 0.95 * nd
        held_share.append(D_ / max(U_, 1))
    return ok, float(np.mean(held_share))


def main():
    import sys
    rng = np.random.default_rng(20261022_91)
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    out = {}
    for sess in (3, 6, 10):
        for edit in (0.05, 0.20, 0.40):
            for late, elig in ((0.01, 0.01), (0.05, 0.05)):
                for m in (0.0, 0.02, 0.04):
                    for rule in ("fixed", "every"):
                        if rule == "every" and not (edit == 0.20 and late == 0.01):
                            continue
                        res = [trial(rng, sess, edit, late, elig, m, live_rule=rule) for _ in range(N)]
                        out[f"correct|{rule}|edit{edit}|late{late}|elig{elig}|map{m}|sessions{sess}"] = {
                            "pass": float(np.mean([r[0] for r in res])), "d_over_u": round(float(np.mean([r[1] for r in res])), 4)}
    for sess in (3, 6, 10):
        for vc in (0.001, 0.005, 0.01):
            for feat in ("vault", "export"):
                res = [trial(rng, sess, vc=vc, vv=0.02, feat_rule=feat) for _ in range(N)]
                out[f"vintage|{feat}|close_rev{vc}|vol_rev0.02|sessions{sess}"] = {"pass": float(np.mean([r[0] for r in res]))}
    for bug in ("window", "tz4h", "nart", "noheld", "gap4", "feed"):
        for sess in (3, 6, 10):
            res = [trial(rng, sess, bug=bug) for _ in range(N)]
            out[f"broken:{bug}|sessions{sess}"] = {"pass": float(np.mean([r[0] for r in res])),
                                                   "d_over_u": round(float(np.mean([r[1] for r in res])), 4)}
    fixed = [v["pass"] for k, v in out.items() if k.startswith("correct|fixed")]
    fixed02 = [v["pass"] for k, v in out.items() if k.startswith("correct|fixed") and "map0.04" not in k]
    every = [v["pass"] for k, v in out.items() if k.startswith("correct|every")]
    out["SUMMARY"] = {
        "correct build, fixed live side: pass min over every cell": min(fixed),
        "correct build, fixed live side: pass min at mapping differences 0-2%": min(fixed02),
        "correct build, 'every status' live side: pass max": max(every),
        "'every status' d/u (the held share) range": [min(v["d_over_u"] for k, v in out.items() if k.startswith("correct|every")),
                                                       max(v["d_over_u"] for k, v in out.items() if k.startswith("correct|every"))],
        "vintage: features from the vault's bars (old reading), pass at close revisions 0.1/0.5/1%":
            [min(v["pass"] for k, v in out.items() if k.startswith(f"vintage|vault|close_rev{x}|")) for x in (0.001, 0.005, 0.01)],
        "vintage: features from the export's bars (fixed reading), pass at close revisions 0.1/0.5/1%":
            [min(v["pass"] for k, v in out.items() if k.startswith(f"vintage|export|close_rev{x}|")) for x in (0.001, 0.005, 0.01)],
        "broken builds, pass max by bug": {b: max(v["pass"] for k, v in out.items() if k.startswith(f"broken:{b}|"))
                                           for b in ("window", "tz4h", "nart", "noheld", "gap4", "feed")},
        "trials_a_cell": N}
    print(json.dumps(out["SUMMARY"], indent=1))
    if N >= 200:
        json.dump(out, open(os.path.join(HERE, "g2_w9ff.out.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
