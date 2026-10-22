#!/usr/bin/env python
"""check1_adaptive.py (EVL-9 adversarial check #1): the session-block sign-flip is EXACT for a fixed program whose block
values are independent and symmetric (PREREG-EVL-6 section 2), but NOT for an adaptive one, even when every block value
is conditionally symmetric about 0 given the past. A learner's next picks depend on its past outcomes (forward refits),
so the SIZE of block s+1 can depend on the SIGN of block s; then the signs are not independent of the magnitudes the
test conditions on. Exact enumeration (no simulation, no data):

  block s value = eps_s x m_s, eps_s iid +-1 (every block symmetric about 0 given the past: the strict null),
  m_1 = 1, m_s = HI if eps_{s-1} = -1 else 1 ("after a loss the learner moves to more volatile names"), or the reverse.
The test: one-sided exact sign-flip p of sum(values) (PREREG-EVL-6 section 1.3, S <= 16), reject at p <= alpha(S).
Output: P(reject) over all 2^S sequences, against alpha.
"""
import itertools
import json
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))


def exact_p(vals):
    S = len(vals)
    obs = sum(vals)
    mags = [abs(v) for v in vals]
    cnt = 0
    for signs in itertools.product((1, -1), repeat=S):
        if sum(s * m for s, m in zip(signs, mags)) >= obs - S * 1e-12:
            cnt += 1
    return cnt / 2 ** S


def rate(S, alpha, hi, after="loss"):
    E = np.array(list(itertools.product((1.0, -1.0), repeat=S)))     # every sign sequence (also the flip set)
    prev = np.concatenate([np.ones((len(E), 1)), E[:, :-1]], axis=1)
    big = (prev == -1) if after == "loss" else (prev == 1)
    M = np.where(big, hi, 1.0)                                          # predictable magnitudes
    V = E * M
    obs = V.sum(axis=1)
    flips = E @ M.T                                                     # flips[j, i] = sum_s E[j, s] M[i, s]
    p = (flips >= obs[None, :] - S * 1e-12).mean(axis=0)
    return float((p <= alpha).mean())


def main():
    rows = []
    for S, alpha in ((2, 0.5), (9, 0.012), (10, 0.012), (12, 0.012)):
        for hi in (1.0, 2.0, 3.0, 5.0):
            for after in ("loss", "win"):
                if hi == 1.0 and after == "win":
                    continue
                r = rate(S, alpha, hi, after)
                rows.append(dict(S=S, alpha=alpha, hi=hi, bigger_after=after, p_reject=round(r, 5),
                                 ratio=round(r / alpha, 3)))
                print(json.dumps(rows[-1]), flush=True)
    with open(os.path.join(HERE, "check1_adaptive.out.json"), "w") as fh:
        json.dump(rows, fh, indent=1)


if __name__ == "__main__":
    main()
