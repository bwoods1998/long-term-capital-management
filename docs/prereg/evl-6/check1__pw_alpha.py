"""A piecewise alpha for search_judge: 'pw:6-8=0.016,9-20=0.012,21-60=0.003' (S ranges inclusive)."""
import numpy as np
import search_judge as SJ
_orig = SJ.alpha_of
def alpha_of(Sat, spec):
    if not spec.startswith("pw:"):
        return _orig(Sat, spec)
    S = Sat.astype(float)
    out = np.zeros(Sat.shape)
    for part in spec[3:].split(","):
        rng, a = part.split("=")
        lo, hi = (float(x) for x in rng.split("-"))
        out = np.where((S >= lo) & (S <= hi), float(a), out)
    return out
SJ.alpha_of = alpha_of
