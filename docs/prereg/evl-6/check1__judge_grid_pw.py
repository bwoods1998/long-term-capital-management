"""Candidate fixes on the JUDGE's own synthetic arrays, streamed one cell at a time (search_judge.combined with the
judge's plausible / null / power definitions): worst plausible, base, stress, and power (P promoted by session h at
60 bp, mean over the five rates, rho 0.05; and at 100 bp by 20), lag 0 and 3. Synthetic only."""
import os, sys, json, gc
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "judge"))
import search_judge as SJ
import report_judge as RJ
import pw_alpha  # noqa: F401  (piecewise alpha)
SCHED = "mlist:6,7,8,9,10,11,12,13,14,15,16,18,20,22,25,30,35,40,50,60"
C = [("pw:6-8=0.016,9-20=0.012,21-60=0.003", 0.001), ("pw:6-7=0.016,8-20=0.012,21-60=0.003", 0.001),
     ("pw:6-10=0.016,11-20=0.010,21-60=0.003", 0.001), ("pw:6-9=0.016,10-20=0.012,21-60=0.003", 0.001)]
meta = RJ._meta()
res = {(a, m0, L): {"worst": (0, None), "stress": (0, None), "base": 0.0, "power": {}} for a, m0 in C for L in (0, 3)}
for m in meta:
    d = dict(np.load(m["path"]))
    for a, m0 in C:
        rule = (SCHED, a, m0, "full", True)
        for L in (0, 3):
            r = res[(a, m0, L)]
            f = SJ.combined(d, L, rule, "alone")
            if RJ.is_null(m):
                v = SJ.rate(f, min(120, m["T"]))
                if RJ.plausible(m):
                    if v > r["worst"][0]: r["worst"] = (v, RJ.lab(m))
                elif v > r["stress"][0]: r["stress"] = (v, RJ.lab(m))
                g = m["gen"]
                if m["cell"] == "N3|sym|nodrift" and abs(g["rho_day"] - 0.05) < 1e-9:
                    r["base"] = max(r["base"], v)
            elif m["phase"].startswith("power"):
                g = m["gen"]
                key = (round(g["skill"] * 1e4), g["rho_day"], int(g["nbar"]), m["T"])
                r["power"][key] = {h: SJ.rate(f, h) for h in (10, 20, 40, 60) if h <= m["T"]}
    del d; gc.collect()
def sc(r, sk=60, rho=0.05, h=20):
    v = [r["power"].get((sk, rho, n, 60), {}).get(h) for n in (85, 30, 13, 8, 3)]
    v = [x for x in v if x is not None]
    return float(np.mean(v))
for a, m0 in C:
    for L in (0, 3):
        r = res[(a, m0, L)]
        print(f"{a} m{m0} L{L}: worst {r['worst'][0]:.3f} [{r['worst'][1].strip()}] base {r['base']:.3f} stress {r['stress'][0]:.3f} | "
              f"60bp by 10/20/40: {sc(r, h=10):.3f} {sc(r, h=20):.3f} {sc(r, h=40):.3f} | 100bp by 20: {sc(r, 100, 0.05, 20):.3f}", flush=True)
