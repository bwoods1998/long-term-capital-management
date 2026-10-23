"""ev_r2.py: READER-2's expected value per metered dollar for the REGISTERED shape, EVL-R2-ON alone (design-reader2).
SYNTHETIC: it reads only calib_r2.final.jsonl (the consumer's synthetic power under PREREG-EVL-6's frozen screen, its
P|... cells) and cost_r2.out (the cost model, on_only).

For each alternative cell: the picks' realized mean a (after the replay's ~14 bp), P(run 1 passes by session 40 / 60 /
120); the expected real-money P&L of the ONE seat over 120 sessions: learning lots (2% of E = $37.96) until the pass,
Probe lots at Done's size (S2 / A99: the mean at-size lot $67.9) after it, BUYS of its 8 picks bought (earlier rows, cash
and A85's reservation take the rest), against READER-2's metered dollars (cost_r2.out on_only lo / mid / hi, the hi
capped by R2's $0.75 line). The Done events it adds (Probe-size buys after the pass) are printed beside. A102's price
(about 6 sessions of time-to-Done in the best scenario per metered dollar a session) is printed, not modelled.
Run: .venv/bin/python ev_r2.py > ev_r2.out
"""
import json

EQUITY = 1898.0
LEARN_LOT = 0.02 * EQUITY
PROBE_LOT = 67.9
BUYS = (5, 7)
T = 120
LINE = 0.75


def main():
    cost = json.load(open("cost_r2.out"))["on_only"]
    usd_day = {lab: min(LINE, cost[lab]["sonnet55_usd_day"]) for lab in ("lo", "mid", "hi")}
    rows = [json.loads(l) for l in open("calib_r2.final.jsonl")]
    out = []
    for r in rows:
        if not r["cell"].startswith("P|"):
            continue
        e = r["realized_mean_a_bp"] / 1e4
        by = r["by_session"]
        cdf = [(s_, by.get(str(s_), by.get(s_))) for s_ in (25, 30, 40, 60, 90, 120)]
        probe_sessions, prev_s, prev_p = 0.0, 0, 0.0
        for s, p in cdf:
            probe_sessions += (p - prev_p) * (T - (prev_s + s) / 2.0)
            prev_s, prev_p = s, p
        res = {"cell": r["cell"], "pick_mean_a_bp": round(r["realized_mean_a_bp"], 1), "P_by40": round(cdf[2][1], 3),
               "P_by60": round(cdf[3][1], 3), "P_by120": round(cdf[5][1], 3), "per_version_120": r["per_version_120"],
               "E_probe_sessions_of_120": round(probe_sessions, 1)}
        for b in BUYS:
            pnl = b * e * (LEARN_LOT * (T - probe_sessions) + PROBE_LOT * probe_sessions)
            res[f"pnl_{b}buys_usd"] = round(pnl, 1)
            res[f"done_events_{b}buys"] = round(b * probe_sessions, 0)
            res[f"net_{b}buys_mid_usd"] = round(pnl - usd_day["mid"] * T, 1)
        out.append(res)
    be = {f"break_even_bp_learning_{b}buys_{lab}": round(1e4 * usd_day[lab] / (b * LEARN_LOT), 1)
          for b in BUYS for lab in ("lo", "mid", "hi")}
    be.update({f"break_even_bp_probe_{b}buys_{lab}": round(1e4 * usd_day[lab] / (b * PROBE_LOT), 1)
               for b in BUYS for lab in ("lo", "mid", "hi")})
    print(json.dumps({"usd_day": usd_day, "r2_cost_120_usd": {k: round(v * T, 1) for k, v in usd_day.items()},
                      "a102_sessions_of_done_time_per_day_of_r2_best_scenario": {k: round(6 * v, 1) for k, v in usd_day.items()},
                      "break_even": be, "cells": out}, indent=1))


if __name__ == "__main__":
    main()
