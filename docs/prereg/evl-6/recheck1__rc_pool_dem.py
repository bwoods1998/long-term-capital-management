"""rc_pool_dem.py: pools P(a true 60 bp edge is demoted by its stay's 1,000th Probe+ event), the file's rule (reads at
0.20, 10% stop), over the fixer's runs (final/demotion_stop.json, demotion_rest.json; read only) and this re-check's
fresh-seed runs of the same code (out/demotion_rep.json, demotion_alt.json, demotion_long.json). Synthetic only."""
import json
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
FIN = os.path.join(os.path.dirname(HERE), "final")
O = os.path.join(HERE, "out")


def fx(fname, cell, nb):
    for r in json.load(open(os.path.join(FIN, fname)))["rows"]:
        if r["stop"] == "pct:0.10" and r["cell"] == cell and r["nbar"] == nb:
            return r["by1000"], r["R"]


def rc(fname, cell, key="by1000", **flt):
    for r in json.load(open(os.path.join(O, fname))):
        if r["cell"] == cell and all(r.get(k) == v for k, v in flt.items()):
            return r[key], r["R"]


def pool(name, parts):
    k = sum(p * n for p, n, _ in parts); n = sum(n for _, n, _ in parts)
    p = k / n
    print(f"{name:44s} pooled {p:.4f} +- {math.sqrt(p * (1 - p) / n):.4f} over {n} | " +
          "; ".join(f"{lab} {pp:.4f} ({nn})" for pp, nn, lab in parts))


pool("crash days, 20 bp, rho .15, phi .20, n85", [
    (*fx("demotion_rest.json", "60bp|dayskew, AR20, rho.15, phi.20", 85), "fixer"),
    (*rc("demotion_rep.json", "60bp dayskew AR20 rho.15 phi.20 n85"), "rep"),
    (*rc("demotion_alt.json", "60bp dayskew AR20 rho.15 phi.20 n85", read_p=0.2), "alt")])
pool("worst (crash+skew+20bp), n85", [
    (*fx("demotion_stop.json", "60bp|worst: both, AR20, rho.15, phi.20", 85), "fixer"),
    (*rc("demotion_rep.json", "60bp worst n85"), "rep"),
    (*rc("demotion_alt.json", "60bp worst n85", read_p=0.2), "alt"),
    (*rc("demotion_long.json", "60bp worst n85 long", stop="pct:0.10"), "long")])
pool("worst (crash+skew+20bp), n30", [
    (*fx("demotion_stop.json", "60bp|worst: both, AR20, rho.15, phi.20", 30), "fixer"),
    (*rc("demotion_rep.json", "60bp worst n30"), "rep"),
    (*rc("demotion_alt.json", "60bp worst n30", read_p=0.2), "alt"),
    (*rc("demotion_long.json", "60bp worst n30 long", stop="pct:0.10"), "long")])
pool("crash days, 20 bp, rho .15, phi .20, n30 (rep)", [(*rc("demotion_rep.json", "60bp dayskew AR20 rho.15 phi.20 n30"), "rep")])
print("by the 2,000th (alt, reads 0.20): crash days n85 %.4f, worst n85 %.4f, worst n30 %.4f" % (
    rc("demotion_alt.json", "60bp dayskew AR20 rho.15 phi.20 n85", "by2000", read_p=0.2)[0],
    rc("demotion_alt.json", "60bp worst n85", "by2000", read_p=0.2)[0], rc("demotion_alt.json", "60bp worst n30", "by2000", read_p=0.2)[0]))
print("by the 3,000th (long): worst n85 %.4f, worst n30 %.4f" % (
    rc("demotion_long.json", "60bp worst n85 long", "by3000", stop="pct:0.10")[0],
    rc("demotion_long.json", "60bp worst n30 long", "by3000", stop="pct:0.10")[0]))
print("reads at 0.15 instead (alt), by 1,000th / 2,000th: crash days n85 %.4f / %.4f; worst n85 %.4f / %.4f; worst n30 %.4f / %.4f" % (
    *[rc("demotion_alt.json", c, k, read_p=0.15)[0] for c in ("60bp dayskew AR20 rho.15 phi.20 n85",) for k in ("by1000", "by2000")],
    *[rc("demotion_alt.json", c, k, read_p=0.15)[0] for c in ("60bp worst n85",) for k in ("by1000", "by2000")],
    *[rc("demotion_alt.json", c, k, read_p=0.15)[0] for c in ("60bp worst n30",) for k in ("by1000", "by2000")]))
print("a false pass's stay (knife edge, worst, n85) demoted by 300th / 1,000th: reads 0.20 %.3f / %.3f; reads 0.15 %.3f / %.3f" % (
    rc("demotion_alt.json", "knife edge worst n85", "by300", read_p=0.2)[0], rc("demotion_alt.json", "knife edge worst n85", "by1000", read_p=0.2)[0],
    rc("demotion_alt.json", "knife edge worst n85", "by300", read_p=0.15)[0], rc("demotion_alt.json", "knife edge worst n85", "by1000", read_p=0.15)[0]))
print("t(3)-body crash days (rep): worst n85 %.4f, n30 %.4f" % (rc("demotion_rep.json", "T3BODY 60bp worst n85")[0], rc("demotion_rep.json", "T3BODY 60bp worst n30")[0]))
