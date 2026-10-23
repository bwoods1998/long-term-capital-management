#!/usr/bin/env python
"""ev_fix1.py: PREREG-EVL-10 FIX ROUND 1, the seat's money and cost figures under the owner's goal V3 (04:40Z Oct 23,
2026) as release 1019l sizes real money (A138: learning 0.05 of E, Probe 0.05 of E at PREREG-EVL-6 clause 2's 0.8 bar
inside the 5% envelope, Sized 0.10, the name's wall 0.10). SYNTHETIC POWER + STATED PRIORS + STATED PRICE ASSUMPTIONS:
nothing here reads any price, return, look, band, mark or P&L of any event, symbol or program.

LOTS (the sizing code on origin/rel/1019l, league/equity/live.py `_size_event` and league/events/book.py
`at_size_count`): E = $1,906 (the owner's figure in goal V3's Done); a pick's limit is 1.25 x its previous close p.
  learning: n = floor(0.05 E / (1.25 p)) whole shares (BUYABLE, 1.25 p <= 0.05 E, makes n >= 1);
  Probe (a version PREREG-EVL-6 judges): the fewest n with n x 1.25 p >= 0.8 x 0.05 E, bought only when
  n x 1.25 p <= 0.05 E (the envelope), else the pick is skipped before it takes a slot (`under_bar`).
  The P&L basis is the dollars invested at the fill, taken at p (the replay's auction price is near the previous
  close on average; an assumption). The draft's $38 / $67.9 were lots AT THE LIMIT (2% of E and A99's Probe mean).
PRICES: BUYABLE names' previous closes are not in any outcome-free fact; two stated laws: log-uniform on [$3, 0.04 E]
($3 is PREREG-EVL-1 section 2's floor) and log-uniform on [$10, 0.04 E].
POWER: the designer's fresh-seed runs (../reader2/calib_r2.final.jsonl, base model), as the draft; THE LINE'S
STARVATION (fix1/fp_fix1.power.jsonl, when present): P(pass by 120) and picks a session scaled by the line cell over
its no-line twin at the same c (the twin carries counts that follow the day).
PRIORS: the judge's stated judgment, unchanged (none 0.40, c 0.3 0.25, c 0.5 0.20, c 0.7 0.08 at sd 0.8%, c 0.5 at
sd 1.5% 0.07).
COSTS a day: the designer's counts lo / mid ($0.140 / $0.411, fix1/cost_fix1.out), the caps' mid ($0.602) and
R2_LINE's most ($0.75).
Run: .venv/bin/python ev_fix1.py > ev_fix1.out
"""
from __future__ import annotations

import json
import math
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
E = 1906.0
T = 120
BUYS_L, BUYS_P = 6, 7
BINS = ((25, 24.0), (30, 28.0), (40, 35.0), (60, 50.0), (90, 75.0), (120, 105.0))
COST = {"lo": 0.140, "mid": 0.411, "caps_mid": 0.602, "line_max": 0.75}
PRIOR = {"c0": 0.40, "c0.3|sd0.8": 0.25, "c0.5|sd0.8": 0.20, "c0.7|sd0.8": 0.08, "c0.5|sd1.5": 0.07}
CELLS = {"c0.3|sd0.8": "P|alt|base|n42|finf|sda0.008|c0.3", "c0.5|sd0.8": "P|alt|base|n42|finf|sda0.008|c0.5",
         "c0.7|sd0.8": "P|alt|base|n42|finf|sda0.008|c0.7", "c0.5|sd1.5": "P|alt|base|n42|finf|sda0.015|c0.5"}


def lots(lo: float, n_draw: int = 400_000, seed: int = 20261023) -> dict:
    rng = np.random.default_rng(seed)
    hi = 0.04 * E
    p = np.exp(rng.uniform(math.log(lo), math.log(hi), n_draw))
    L = 1.25 * p
    nl = np.floor(0.05 * E / L)
    learn_fill = nl * p
    npb = np.ceil(0.8 * 0.05 * E / L - 1e-12)
    ok = npb * L <= 0.05 * E + 1e-9
    probe_fill = np.where(ok, npb * p, np.nan)
    return {"price_law": f"log-uniform [${lo:.0f}, ${hi:.2f}]",
            "learning_lot_fill_mean": round(float(learn_fill.mean()), 2),
            "learning_lot_limit_mean": round(float((nl * L).mean()), 2),
            "learning_lot_fill_q10_q90": [round(float(np.quantile(learn_fill, q)), 2) for q in (0.1, 0.9)],
            "probe_skip_share": round(float(1 - ok.mean()), 4),
            "probe_lot_fill_mean_when_bought": round(float(np.nanmean(probe_fill)), 2),
            "probe_skip_bands_prev_close": [[round(0.05 * E / 1.25 / (k + 1), 2), round(0.04 * E / 1.25 / k, 2)]
                                            for k in (1, 2, 3) if 0.05 * E / (k + 1) < 0.04 * E / k]}


def pass_session(by):
    prev_p, num = 0.0, 0.0
    for s, mid in BINS:
        p = by.get(str(s), by.get(s, 0.0))
        num += (p - prev_p) * mid
        prev_p = p
    return (num / prev_p if prev_p > 0 else float("nan")), prev_p


def load(path):
    if not os.path.exists(path):
        return []
    with open(path) as fh:
        return [json.loads(x) for x in fh if x.strip()]


fin = {r["cell"]: r for r in load(os.path.join(HERE, "..", "reader2", "calib_r2.final.jsonl"))}
pw = {r["cell"]: r for r in load(os.path.join(HERE, "fp_fix1.power.jsonl"))}
fp_base = fin["F|N1|base|n42|finf"]["pass_run1_120"]


def starve_factor(c: float, tag: str):
    """(P(pass) ratio, picks-a-session ratio) of the line cell over its no-line twin, from fp_fix1.power.jsonl."""
    a = pw.get(f"P|alt|base|n42|cnt|finf|sda0.008|c{c}|noline")
    b = pw.get(f"P|alt|base|n42|cnt|finf|sda0.008|c{c}|{tag}")
    if not a or not b or a["pass_run1_120"] <= 0:
        return None
    return b["pass_run1_120"] / a["pass_run1_120"], b["picks_per_session"] / a["picks_per_session"]


out = {"E": E, "lots": {}, "per_traded_event_bp": {}, "break_even_pick_edge_bp": {}, "ev": {}}
for lo in (3.0, 10.0):
    out["lots"][f"from ${lo:.0f}"] = lots(lo)
lot = out["lots"]["from $3"]
LOT_L = lot["learning_lot_fill_mean"]
LOT_P = lot["probe_lot_fill_mean_when_bought"]
SKIP = lot["probe_skip_share"]
for k, u in COST.items():
    out["per_traded_event_bp"][k] = {"learning_6_buys": round(1e4 * u / (BUYS_L * LOT_L), 1),
                                     "probe_7_buys_less_skips": round(1e4 * u / (BUYS_P * (1 - SKIP) * LOT_P), 1)}
    out["break_even_pick_edge_bp"][k] = {f"{b}_buys": round(1e4 * u / (b * LOT_L), 1) for b in (5, 6, 7)}

for scen in ("no starvation", "L3.0|V1.42", "L3.0|V1.6", "L3.75|V1.6"):
    rows = {}
    for name in PRIOR:
        if name == "c0":
            edge, p, tp, buy_scale = 0.0, fp_base, 30.0, 1.0
            if scen != "no starvation":
                f = starve_factor(0.5, scen)
                buy_scale = f[1] if f is not None else 1.0     # (R2's reads, and so its dollars, fall with its supply)
        else:
            r = fin[CELLS[name]]
            edge = r["realized_mean_a_bp"]
            tp, p = pass_session(r["by_session"])
            buy_scale = 1.0
            if scen != "no starvation":
                c = float(name.split("|")[0][1:])
                f = starve_factor(0.5 if c == 0.3 else c, scen)
                if f is not None:
                    p, buy_scale = p * f[0], f[1]
        e = edge * 1e-4
        learn = e * LOT_L * BUYS_L * buy_scale * ((1 - p) * T + p * tp)
        probe = p * e * LOT_P * BUYS_P * (1 - SKIP) * buy_scale * (T - tp)
        pnl = learn + probe
        rows[name] = {"pick_mean_a_bp": round(edge, 1), "P_pass_by120": round(p, 4), "pnl_120_usd": round(pnl, 1)}
        for k, u in COST.items():
            spend = u * T * (buy_scale if scen != "no starvation" else 1.0)
            rows[name][f"net_{k}_usd"] = round(pnl - spend, 1)
    ev = {"pnl_120_usd": round(sum(PRIOR[c] * rows[c]["pnl_120_usd"] for c in PRIOR), 2)}
    for k in COST:
        ev[f"net_{k}_usd"] = round(sum(PRIOR[c] * rows[c][f"net_{k}_usd"] for c in PRIOR), 2)
    ev["pnl_per_metered_usd_mid"] = round(ev["pnl_120_usd"] / (COST["mid"] * T), 2)
    ev["true_promotions_per_charge"] = round(sum(PRIOR[c] * rows[c]["P_pass_by120"] for c in PRIOR if c != "c0"), 3)
    out["ev"][scen] = {"cells": rows, "expected": ev}
out["note"] = ("At V3's rows a Probe lot of this seat is about a learning lot (both 5% targets; Probe takes only the "
               "counts inside [0.8, 1.0] x 5% at the limit and skips the rest), so promotion adds slots (14 open) "
               "this seat's 8 picks a decision cannot use and skips some names: P&L is mostly learning P&L. Sized "
               "(10%) is not reached within 120 sessions in this model. The cost line's share: R2's $0.411 mid day is "
               "4.1% of goal V3's $10 and 8.2% of release 1019l's $5 rule.")
print(json.dumps(out, indent=1))
