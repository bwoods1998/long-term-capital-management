"""mech_t3body.py: a minimal model of why a t(3) body raises the false-positive rate of a session-block sign-flip
under crash-compensated day shocks (synthetic only). Block value = 2.2% x eps + 0.56% x N(0,1) - 10 bp, eps a
unit-variance mean-zero crash mixture (5% at -3 sd) with a normal or t(3) ordinary-day body; i.i.d. blocks, one look
at S blocks, exact sign-flip p <= alpha."""
import itertools
import math
import sys

import numpy as np

sys.dont_write_bytecode = True


def eps(rng, n, t3):
    p, k = 0.05, 3.0
    m = p * k / (1 - p)
    s = math.sqrt((1 - p * (k * k + 1)) / (1 - p) - m * m)
    body = rng.standard_t(3, n) / math.sqrt(3) if t3 else rng.standard_normal(n)
    return np.where(rng.random(n) < p, rng.normal(-k, 1, n), m + s * body)


def fp(S, alpha, t3, R=40000, seed=1):
    rng = np.random.default_rng(seed)
    y = 0.022 * eps(rng, R * S, t3).reshape(R, S) + 0.0056 * rng.standard_normal((R, S)) - 0.0010
    P = np.array(list(itertools.product((-1.0, 1.0), repeat=S)))
    out = 0
    for lo in range(0, R, 2000):
        Y = y[lo:lo + 2000]
        M = P @ Y.T
        p = np.count_nonzero(M >= Y.sum(axis=1)[None, :] - S * 1e-12, axis=0) / float(1 << S)
        out += int(np.count_nonzero(p <= alpha))
    return out / R


for S, a in ((9, 0.012), (12, 0.012), (16, 0.010)):
    print(f"S={S} alpha={a}: normal body {fp(S, a, False):.4f}, t(3) body {fp(S, a, True):.4f}  (nominal {a})", flush=True)
