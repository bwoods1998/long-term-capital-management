#!/usr/bin/env python
"""ev_evl7.py: the expected value of PREREG-EVL-7's learners under STATED scenarios (synthetic; no lane data).

It reads calib_evl7.power.jsonl (the judge's runs: the learner lens's generator, the EVL-6 draft's screen ev6d, with
and without COST-7's shift) and turns each scenario's promotion curve and the picks' true edge into dollars and
Probe events, per learner, over 120 sessions. Every input below is an assumption stated here or a fact of SPEED-FACTS;
none is a lane outcome.

ASSUMPTIONS (outcome-free):
  E = $1,898 (SPEED-FACTS); a learning lot 2% of E; a Probe lot 0.9 x 3.5% of E (A99's at-size buys reach 0.8-1.0 of
  the target); 7.9 picks a session (the generator's mean at pool 800); real money buys a share F_L of a learner's picks
  at learning (ROOM last, cash binding: 0.25 crowded / 0.50 open) and F_P at Probe (0.75: A85's reservation and the
  Probe tier's round-robin, the venue's cancels netted); each real pick earns the picks' TRUE expected replay a of its
  session decile (the generator's curve) PLUS GAP bp, the replay's overcharge less the real cost (replay 14.2-24.2 bp a
  round trip against fees of about 3-6 bp at learning size: GAP = 8 bp, conservative); a promoted version stays at
  Probe (demotion of a true edge ignored: PREREG-EVL-6 section 3 measured 13-16% for a 60 bp edge); the abnormal return
  only (the raw return adds the benchmark's drift).
Usage: ev_evl7.py
"""
import json
import math
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
E = 1898.0
LOT_L = 0.02 * E
LOT_P = 0.9 * 0.035 * E
PICKS = 7.9
F_P = 0.75
GAP = 0.0008
T = 120


def load():
    rows = [json.loads(x) for x in open(os.path.join(HERE, "calib_evl7.power.jsonl"))]
    by = {}
    for r in rows:
        by.setdefault(r["cell"], []).append(r)
    return by


def curve(parts, key, chain):
    ps = np.concatenate([p[key]["cpass" if chain else "pass_"] for p in parts])
    wh = np.concatenate([p[key]["cwhen" if chain else "when"] for p in parts])
    return np.array([((ps == 1) & (wh < t)).mean() for t in range(T)])   # P(promoted before session t's decision)


def edge(parts):
    ce = parts[0]["curve_edge_bp"]
    out = np.zeros(T)
    for k in ce:
        lo, hi = (int(x) for x in k.split("-"))
        out[lo - 1:hi] = np.mean([p["curve_edge_bp"][k] for p in parts]) / 1e4
    return out


def main():
    by = load()
    print("per learner, 120 sessions; $ = abnormal after real cost; Probe events = real buys at Probe size (Done's kind)")
    print(f"{'scenario':<28} {'rule':<9} {'P(promo)':>8} {'by40':>6} {'by120':>6} {'$ F_L .25':>10} {'$ F_L .50':>10} "
          f"{'Probe ev':>9} {'E-cum 50':>9}")
    for cell, parts in by.items():
        e = edge(parts) + GAP
        for key in ("ev6d", "ev6d_c7"):
            for chain in (False, True):
                P = curve(parts, key, chain)
                usd = {}
                for fl in (0.25, 0.50):
                    usd[fl] = float(np.sum((1 - P) * fl * PICKS * LOT_L * e + P * F_P * PICKS * LOT_P * e))
                probe_ev = float(np.sum(P * F_P * PICKS))
                cum = np.cumsum(P * F_P * PICKS)
                to50 = int(np.argmax(cum >= 50)) + 1 if cum[-1] >= 50 else None
                tag = ("chain3 " if chain else "one ") + ("c7" if key.endswith("c7") else "")
                print(f"{cell:<28} {tag:<9} {P[-1]:>8.3f} {P[39]:>6.3f} {P[-1]:>6.3f} {usd[0.25]:>10.1f} "
                      f"{usd[0.50]:>10.1f} {probe_ev:>9.0f} {str(to50):>9}")
    print(f"E-cum 50 = the first session at which the EXPECTED cumulative Probe events (over paths) reach 50; a promoted "
          f"learner itself buys about {F_P * PICKS:.1f} Probe events a session, so 50 in about {math.ceil(50 / (F_P * PICKS))} "
          "sessions after its promotion (Done's >= 50 a program).")
    print("NULL (IC 0): the picks' true replay a is 0, so each real pick earns GAP: "
          f"${0.25 * PICKS * LOT_L * GAP * T:.1f} (F_L .25) to ${0.50 * PICKS * LOT_L * GAP * T:.1f} (F_L .50) over 120 "
          "sessions at learning, plus a false promotion's Probe lots at the same GAP; the loss budget bounds the variance.")


if __name__ == "__main__":
    main()
