#!/usr/bin/env python
"""ev8_drive.py: expected value of PREREG-EVL-8 under stated scenarios (ev8_sim.py; SYNTHETIC ONLY).

Every config is the done-speed synthesis's adopted game (PREREG-EVL-6 new versions from session 1, A99's Probe room
14 and at-size buys, A85, the 150-order line, the loss budget), with PREREG-EVL-6's look schedule as drafted. 'base'
has no PREREG-EVL-8 rows; 'evl8' adds the three PX seats and the two METAs (real money from session 6, the release
carrying them; shadow from session 1, REGISTERED_AT_8). PX seats are judged at alpha (px_a1, px_a2).

Scenarios (after-cost edges per event, the judged a; 'rest' is every other program):
  Z0     every program 0 after cost
  Z15    every program -15 bp after cost (no edge before cost)
  PX40   PX-DROP-ON +40 bp, rest -15            PX60  PX-DROP-ON +60 bp, rest -15
  META   a +60 bp sub-rule inside the pool: META's picks reach +50 bp after ~40 sessions, rest -15
  E1     one news row (NEWS-READ-ON) +40 bp, rest -15 (META follows it to 0.85 x 40 bp)
  E3news the three news rows +40 bp, rest -15 (META follows)
  E1PX   E1 and PX-DROP-ON +40 bp
Usage: ev8_drive.py RUNS SEED0 [px_a1=0.016 px_a2=0.004 ...]
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ev8_sim as M  # noqa: E402

ALL = list(range(15))
SCEN = {
    "Z0": (0, 0.0, 0.0, ALL),
    "Z15": (0, 0.0, -0.0015, ALL),
    "PX40": (0, 0.0, -0.0015, ALL, {"fixed": {15: 0.0040}}),
    "PX60": (0, 0.0, -0.0015, ALL, {"fixed": {15: 0.0060}}),
    "META": (0, 0.0, -0.0015, ALL, {"meta": 0.0050}),
    "E1": (0, 0.0, -0.0015, ALL, {"fixed": {7: 0.0040}}),
    "E3news": (3, 0.0040, -0.0015, [3, 7, 8]),
    "E1PX": (0, 0.0, -0.0015, ALL, {"fixed": {7: 0.0040, 15: 0.0040}}),
}
GAME = {"screen": "evl6", "restart_at": 1, "probe_max": 14, "probe_round": "atsize_skip", "sized_round": "atsize_skip"}

if __name__ == "__main__":
    runs, seed0 = int(sys.argv[1]), int(sys.argv[2])
    extra = {}
    only = None
    for a in sys.argv[3:]:
        k, v = a.split("=", 1)
        if k == "only":
            only = v.split(",")
            continue
        extra[k] = json.loads(v)
    if "px_a1" in extra:
        extra["px_a"] = (extra.pop("px_a1"), extra.pop("px_a2"))
    res = {}
    for tag, ev8 in (("base", False), ("evl8", True)):
        cfg = dict(M.BASE)
        cfg.update(GAME)
        cfg.update(extra)
        cfg["evl8"] = ev8
        for sk, sc in SCEN.items():
            if only and sk not in only:
                continue
            t0 = time.time()
            out = M.batch(cfg, sc, runs, seed0, workers=4)
            r = M.summary(out, cfg["horizon"])
            res[f"{tag}|{sk}"] = r
            print(f"{tag:5s} {sk:7s} P40 {r['P_done_40']:.3f} P60 {r['P_done_60']:.3f} P120 {r['P_done_H']:.3f} "
                  f"E[min(T,121)] {r['mean_T_capped']:.1f} trueP {r['true_promo_mean']:.2f} falseP "
                  f"{r['false_promo_mean']:.2f} evl8P {r['evl8_promo_mean']:.2f} evl8cnt {r['evl8_counted_mean']:.0f} "
                  f"pnl {r['pnl_mean']:.0f} p05 {r['pnl_p05']:.0f} w20p5 {r['worst20_p5']:.0f} falseDone "
                  f"{r['P_false_done']:.3f} stops {r['stops']} ({time.time() - t0:.0f}s)", flush=True)
    name = "ev8" + "".join(f"_{k}={v}" for k, v in sorted(extra.items())).replace(" ", "")
    json.dump({"runs": runs, "seed0": seed0, "extra": {k: str(v) for k, v in extra.items()}, "res": res},
              open(os.path.join(HERE, name + f"_{runs}_{seed0}.json"), "w"), indent=1)
