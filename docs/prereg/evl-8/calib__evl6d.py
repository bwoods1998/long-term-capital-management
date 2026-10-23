#!/usr/bin/env python
"""evl6d.py: PREREG-EVL-6's screen EXACTLY AS DRAFTED (goal-2026-10-19/evl6/PREREG-EVL-6.draft.md sections 1.2-3,
the judge's chosen rule ('mlist:6,7,8,9,10,11,12,13,14,15,16,18,20,22,25,30,35,40,50,60', 'step:0.016:20:0.004',
m0 0.001, 'full' guards, retirement), on a synthetic record. SYNTHETIC ONLY: it reads no lane data.

Written by the PREREG-EVL-8 judge because the PX and META designers calibrated against 'L12' (alpha 0.01, looks
7..30, a 30-block life: an earlier candidate described in evl7/learner/calib_learner.py), which is NOT the rule the
EVL-6 draft states. Every PREREG-EVL-8 figure under "EVL-6" is this function's.

THE RULE (a version's record: its TRADABLE settled events, one block per entry session holding >= 1 of them):
  B_s = mean a of block s; x_s = B_s - 0.0010; S = blocks so far.
  LOOKS: thresholds S_k = 6, 7, ..., 16, 18, 20, 22, 25, 30, 35, 40, 50, 60. Look k is at the first block-adding
    close at which S >= S_k AND the minimums hold (>= 6 blocks, >= 30 TRADABLE events, >= 30 distinct issuers);
    every threshold reached by then is consumed by that one look.
  alpha(S) = 0.016 for S <= 20, 0.004 for S >= 21.
  At a look: RETIRE first when mean a < 0 and q <= alpha(S) (q: the sign-flip p of mean(-B) > 0);
    PASS when p <= alpha(S) (p: the sign-flip p of mean(x) > 0), mean a > 0, mean r > 0, the mean block beats the
    control's mean over the same sessions (versions with a control), and the issuer-block p (issuer means of a, no
    margin) <= 0.10.
  EXHAUSTION: the 60th block covered with no pass (the version leaves learning: retired).
  Sign-flip p: exact over 2^S for S <= 16, else (1 + #) / 20,000 over 19,999 fixed vectors (calib_learner.flip_p,
  the EVL-6 judge's own shortcut); the issuer p over 999 vectors (the judge's); a p is computed only where
  z = sum x / sqrt(sum x^2) >= 1.0 (no alpha here needs z below about 2).

screen(sim, rep, start=0, control=True) -> (passed, pass_session, retired, end_session)
chain(sim, rep, versions=3, control=True) -> (passed, pass_session, versions_started)
The sim dict is calib_learner's: B, Rm, n, ctrl (R, T); iss, a (R, T, K) left-packed (n[t] valid entries).
"""
from __future__ import annotations

import os
import sys

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")
import numpy as np  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..", "evl7", "learner")))
import calib_learner as CL  # noqa: E402

TIE = 1e-12
LOOKS = (6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 18, 20, 22, 25, 30, 35, 40, 50, 60)
MARGIN = 0.0010
HORIZON = 60
PI_MAX = 0.10
B_ISS = 999


def alpha(S: int) -> float:
    return 0.016 if S <= 20 else 0.004


def screen(sim, rep, start=0, control=True, looks=LOOKS, alpha_fn=alpha, margin=MARGIN, horizon=HORIZON):
    B, Rm, n, ctrl = sim["B"][rep], sim["Rm"][rep], sim["n"][rep], sim["ctrl"][rep]
    iss, av = sim["iss"][rep], sim["a"][rep]
    T = len(B)
    blocks: list[float] = []
    bsess: list[int] = []
    ev_iss: list[int] = []
    ev_a: list[float] = []
    ev_r = 0.0
    seen: set = set()
    k = 0
    for t in range(start, T):
        kk = int(n[t])
        if kk == 0:
            continue
        blocks.append(float(B[t]))
        bsess.append(t)
        ev_iss.extend(int(x) for x in iss[t, :kk])
        ev_a.extend(float(x) for x in av[t, :kk])
        ev_r += float(Rm[t]) * kk
        seen.update(int(x) for x in iss[t, :kk])
        S = len(blocks)
        N = len(ev_a)
        if k < len(looks) and S >= looks[k] and S >= 6 and N >= 30 and len(seen) >= 30:
            while k < len(looks) and S >= looks[k]:
                k += 1
            al = alpha_fn(S)
            xb = np.array(blocks)
            mean_a = sum(ev_a) / N
            if mean_a < 0 and CL.zstat(-xb) >= 1.0 and CL.flip_p(-xb) <= al + TIE:
                return False, -1, True, t
            x = xb - margin
            if (CL.zstat(x) >= 1.0 and mean_a > 0 and ev_r / N > 0
                    and (not control or xb.mean() > float(np.mean(ctrl[bsess])))
                    and CL.flip_p(x) <= al + TIE
                    and CL.issuer_p(ev_iss, ev_a, B_ISS) <= PI_MAX + TIE):
                return True, t, False, t
        if S >= horizon:
            return False, -1, True, t          # exhausted
    return False, -1, False, -1


def chain(sim, rep, versions=3, control=True, **kw):
    """v1 from session 0; after a retirement or an exhaustion at session e, v n+1 starts at e + 1 (a fresh record);
    at most `versions`. Returns (passed, pass_session, versions_started)."""
    start = 0
    for v in range(1, versions + 1):
        ok, when, _, end = screen(sim, rep, start, control, **kw)
        if ok:
            return True, when, v
        if end < 0 or end + 1 >= len(sim["B"][rep]):
            return False, -1, v
        start = end + 1
    return False, -1, versions


def selftest():
    # six blocks all above the margin pass at S = 6 (p = 1/64 <= 0.016) given the guards
    R, T, K = 1, 10, 10
    sim = {"B": np.full((R, T), 0.02), "Rm": np.full((R, T), 0.02), "n": np.full((R, T), K),
           "ctrl": np.zeros((R, T)), "iss": np.arange(R * T * K).reshape(R, T, K),
           "a": np.full((R, T, K), 0.02)}
    sim["a"][0, :, ::2] = 0.03
    sim["a"][0, :, 1::2] = 0.01
    ok, when, _, _ = screen(sim, 0)
    assert ok and when == 5, (ok, when)
    # one block at -1% among six: no pass at S = 6
    sim["B"][0, 2] = -0.01
    sim["a"][0, 2, :] = -0.01
    ok, when, _, _ = screen(sim, 0)
    assert not ok or when > 5, (ok, when)
    print("evl6d selftest ok")


if __name__ == "__main__":
    selftest()
