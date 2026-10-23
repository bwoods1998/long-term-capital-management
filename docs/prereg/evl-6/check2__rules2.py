"""Extra candidate rules for check #2 (synthetic only)."""
import numpy as np
import search_judge as SJ
_orig = SJ.alpha_of
def alpha_of(Sat, spec):
    kind, _, arg = spec.partition(":")
    if kind == "tri":
        a1, s1, a2, s2, a3 = (float(x) for x in arg.split(":"))
        S = Sat.astype(float)
        return np.where(S <= s1, a1, np.where(S <= s2, a2, a3))
    return _orig(Sat, spec)
SJ.alpha_of = alpha_of
D6S = "mlist:6,7,8,9,10,11,12,13,14,15,16,18,20,22,25,30,35,40,50,60"
D7S = "mlist:7,8,9,10,11,12,13,14,15,16,18,20,22,25,30,35,40,50,60"
RULES2 = {
    "R0": (D6S, "step:0.016:20:0.004", 0.001, "full", True),
    "R4_strict": (D6S, "step:0.012:20:0.003", 0.001, "full", True),
    "R8_012_004": (D6S, "step:0.012:20:0.004", 0.001, "full", True),
    "R9_tri": (D7S, "tri:0.016:10:0.010:20:0.003", 0.001, "full", True),
    "R10_tri6": (D6S, "tri:0.012:12:0.010:20:0.004", 0.001, "full", True),
    "R11_014": (D6S, "step:0.014:20:0.0035", 0.001, "full", True),
    "R12_012m15": (D6S, "step:0.012:20:0.004", 0.0015, "full", True),
}
RULES3 = {
    "R0": RULES2["R0"], "R4_strict": RULES2["R4_strict"], "R9_tri": RULES2["R9_tri"],
    "R9b": (D7S, "tri:0.016:10:0.008:20:0.003", 0.001, "full", True),
    "R9c": (D7S, "tri:0.016:10:0.008:20:0.0025", 0.001, "full", True),
    "R9d": (D7S, "tri:0.014:10:0.008:20:0.003", 0.001, "full", True),
}

RULES4 = {"R0": RULES2["R0"], "R4_strict": RULES2["R4_strict"], "R5_m15": (D6S, "step:0.016:20:0.004", 0.0015, "full", True),
          "R9_tri": RULES2["R9_tri"]}
