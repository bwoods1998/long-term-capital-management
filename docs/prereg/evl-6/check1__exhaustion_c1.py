"""PREREG-EVL-6's chosen rule on the judge's POWER arrays (synthetic, a true edge): P(promoted), P(retired by the
lower tail) and P(EXHAUSTED: the 60th block covered in learning without a pass, retired for good) within the cell's
horizon. Synthetic only."""
import os, sys
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "judge"))
import search_judge as SJ
RULE = ("mlist:6,7,8,9,10,11,12,13,14,15,16,18,20,22,25,30,35,40,50,60", "step:0.016:20:0.004", 0.001, "full", True)
meta, data = SJ.load(phases=("power", "power120"))
print("edge rho  n   T | promoted  lower-tail retired  exhausted (60 blocks, no pass)  neither")
for m in sorted(meta, key=lambda m: (m["gen"]["skill"], m["gen"]["rho_day"], -m["gen"]["nbar"], m["T"])):
    g = m["gen"]; d = data[m["path"]]
    fp, fr = SJ.first_pass(d, 0, RULE)
    Sat = d["L0_Sat"].astype(int)
    T = Sat.shape[1]
    s60 = (Sat >= 60)
    ex_t = np.where(s60.any(axis=1), s60.argmax(axis=1) + 1, 10 ** 6)
    prom = fp < 10 ** 6
    ret = (fr < 10 ** 6) & ~prom
    exh = ~prom & ~ret & (ex_t < 10 ** 6)
    print(f"{g['skill']*1e4:4.0f} {g['rho_day']:.2f} {int(g['nbar']):3d} {m['T']:3d} | {prom.mean():.3f}     {ret.mean():.3f}               {exh.mean():.3f}                           {(~prom & ~ret & ~exh).mean():.3f}")
