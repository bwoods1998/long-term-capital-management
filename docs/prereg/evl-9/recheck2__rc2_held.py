#!/usr/bin/env python
"""rc2_held.py (re-check 2, synthetic only): under the lens generator's issuer law (3,000 issuers, Zipf(0.8) popularity,
a Zipf draw without replacement of n names a session), the share of a control's (session, CIK) pairs that the shadow
writes as `skipped:issuer-held` (the issuer had a non-skipped intent of the same program entering in the 5 sessions
before; 1-session hold), i.e. pairs in G2's LIVE SIDE "every status" that a history side applying the one-position rule
never holds. No lane data."""
import numpy as np
rng = np.random.default_rng(91022)
U = 3000
w = 1.0 / np.arange(1, U + 1) ** 0.8
lw = np.log(w)
for n in (25, 60, 135, 250, 300, 515):
    S = 40
    last = np.full(U, -100)
    held = tot = 0
    for s in range(S):
        g = lw + rng.gumbel(size=U)
        ids = np.argpartition(-g, n)[:n]
        h = (s - last[ids]) <= 5
        if s >= 10:
            held += int(h.sum()); tot += n
        last[ids[~h]] = s        # a held issuer writes a skipped intent; only planned intents hold
    print(f"n={n:4d} a session: share of pairs skipped:issuer-held = {held / tot:.3f}")
