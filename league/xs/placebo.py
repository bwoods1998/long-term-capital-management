"""The residual, the stress residual, the universe excess and the matched placebos: from the holdings log and the bars.

Owner: package D. STEP 0 STUB: the constants are the contract; every function raises NotImplementedError until D lands.

THIS MODULE IS THE PINNED PRE-REGISTRATION'S SECTION 3, to the letter (XSCREEN-1 revision 2; where E4-SPEC D13 and D14
differ, the pre-registration wins). THE STUDY'S CONFORMANCE VECTORS ARE COMMITTED (synthetic inputs, no market data):
league/tests/fixtures/xs1_conformance.json (the study's file, byte for byte) and
league/tests/fixtures/xs1_conformance_inputs.npz (for V1-V6: the prices O and C, the eligible set U, entry validity,
every lot of the holdings log with its cell, members and each member's leaving session, and the study's plain
reference's series r, B, x, x15, s, f, w, exits, invested, u, the 999 placebo t's on the holdout and the counterpart
positions of draws 0 and 998; the file's "manifest" says which vector reads which world). `test_xs_placebo
.TheStudyVectors` reproduces them: every integer exactly (the vectors' lot, member and counterpart-position counts
and sums, exits, invested), x, x15 and u to 1e-12, the placebo t's to 1e-9, the hand vector H, and CH (through
`ctx.derive`'s arithmetic). THE COLUMN ORDER STANDS FOR THE STUDY'S ASSET ID: a fixture hands its names 0..23 as
columns in that order, so "ascending asset id" is ascending column, as it is ascending salted id on the House.
Neither implementation is rewritten to fit the other after the receipt exists. One thing the reference does that a
reader may not expect, and the vectors hold: on a session where a lot's OWN leg is invalid, r itself carries the
cell's mean (so x is 0 there), so r is not the same number under one cell (u) as under the lot's cell.

THE ACCOUNTING is E1's constant-weight accounting on E0 (`league.equity.screen.series`'s leg expressions): a lot of
weight w (its entry notional over the run's capital) earns w times each leg's simple return on total-return
(adjustment=all) prices; nothing compounds; the cash book is the engine's and is not read here.

THE COST-FREE LEG RETURN of a name j at session t, for a lot l (decision close d, entry session e = d + 1 at point
a_e, exit session q at point a_q or none yet):

    entry at the open    t = e                 c_j(e) / o_j(e) - 1            exposure w / 2
    entry at the close   t = e                 0                              0
    held                 e < t < q             c_j(t) / c_j(t-1) - 1          w
    exit at the open     t = q                 o_j(q) / c_j(q-1) - 1          w / 2
    exit at the close    t = q                 c_j(q) / c_j(q-1) - 1          w

THE DAILY SERIES, summed over the lots with a leg at t (hs = k x the lot's half-spread at the fill point):
- r_t: the program's P&L, each leg with its costs: an open entry w (c / (o (1 + hs)) - 1), a close entry w (1 / (1 +
  hs) - 1), an open exit w (o (1 - hs) / c_prev - 1) - fee, a close exit w (c (1 - hs) / c_prev - 1) - fee, with fee =
  `league.equity.config.sell_fees`(proceeds = w E0, shares = w E0 / (P_e (1 + hs))) / E0;
- B_t = the sum over lots of w x m_l(t), m_l(t) = the mean of the leg return over the members j of the lot's cell C_l
  whose leg return is valid at t (0 if none): the cost-free P&L of the lot's matched cell;
- x_t = r_t - B_t, THE RESIDUAL (0 on a session with no lot leg);
- s_t: the spread part of the costs; f_t: the sell fees booked at t; x15_t = x_t - `config.STRESS_SPREAD` x s_t -
  `config.STRESS_FEES` x f_t, THE STRESS RESIDUAL (1.5 times the half-spread, every sell fee charged twice);
- c_t (the cost series), g_t = x_t + c_t (the gross residual), delta_t (the diluted exposure), w_t (the exposure),
  exits_t (lots fully exited at t), invested_t (a lot held at the close);
- u_t, THE UNIVERSE EXCESS (the pre-registration's 4.6): the same residual with ONE cell, every name of U(d_l) (rung
  R3). u keeps what two variants of one rule share (their sector, beta and momentum tilts), which x removes: the
  lineage rule reads both.
An invalid leg return of the lot's own name is replaced by m_l(t): the lot's residual is 0 that session and it pays no
cost.

A LOT'S CELL C_l is the member list of its name's cell at the decision close (`ctx.derive`, `Derived.cell`), less the
members that fail entry validity at e, FIXED for the lot's life. ONE EXIT LAW for the lot's name, its counterparts and
its cell's members: a member j that is not in U(d') at the first close d' after the decision LEAVES at the open of d'
+ 1 while the lot is still open: its leg there is the open exit's, and from the next session on its leg is invalid
(out of the mean; as a counterpart, replaced by m_l). A name whose bars end takes the vanish haircut the same way,
lot, counterpart and member alike.

THE PLACEBOS. A draw gives every lot a COUNTERPART in its cell; its series is cost-free: P^m_t = the sum over lots of
w x (the counterpart's leg return), x^m_t = P^m_t - B_t. THE LAW OF A DRAW (sequential, distinct names): decisions in
time order (a standing-target day is a decision); at a decision the counterparts of the lots that exit at the next
fill are released; the lots opened at this decision are grouped by cell, cells in ascending id, and within a cell
ordered by (w descending, id ascending); for a cell with member list C (ascending id) and k new lots, ONE call
`rng.random((draws, len(C)))` gives one uniform key a member and a draw, the keys of the members the draw currently
holds as a counterpart are raised by 2, and the k members with the smallest keys (a stable sort) are the counterparts,
in that order. One `numpy.random.default_rng(seed)` a run, the calls in that order and no other call (no `choice`,
`shuffle` or `permutation`: their streams are not promised across numpy versions; `random` is).

THE RANK: p_plac = (1 + #{m : T(x^m) >= T(x)}) / (draws + 1), T by `results.t_stat` on the SAME sessions; an undefined
placebo T counts as not above. Under the sharp null (new names are a uniform draw from their cells) the gross residual
is one more draw of the same law, so the rank is exact for any dependence; the gate ranks the NET residual against
cost-free placebos, which is harder to pass.

Evidence module (in the xs identity; a fixed judge: league/ci.py holds league/xs/ out of every role's reach).
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

import numpy as np

#: The House look's draws (the pre-registration's M): the receipt names the figure in force and `screen` refuses a
#: block drawn with another.
DRAWS = 999
#: The seed labels: the one sealed look's (fixed by the receipt and the program's code before the look) and a Train
#: run's (the Train bar's rank, never evidence).
LOOK_SEED = "XS1|{receipt}|{code}|placebo"
TRAIN_SEED = "XS1|train|{run_sha}|{window}|placebo"
#: The arrays `residual` returns, each one value a session.
SERIES = ("r", "bench", "x", "x15", "u", "w", "s", "f", "c", "g", "delta", "exits", "invested")

_STUB = "league.xs.placebo is a Step 0 stub: package D builds it (league/xs/E4_INTERFACES.md)"


def look_seed(receipt_sha256: str, code_sha256: str) -> int:
    """The sealed look's seed: int.from_bytes(sha256(`LOOK_SEED` filled).digest()[:16], "big"). Fixed before the look."""
    raise NotImplementedError(_STUB)


def train_seed(run_sha: str, window: str) -> int:
    """A Train run's seed, the same expression on `TRAIN_SEED`."""
    raise NotImplementedError(_STUB)


def residual(bars: Any, log: Any, *, capital: Any = None, k: float = 1.0, rung: str | None = None,
             haircut: float | None = None) -> dict[str, Any]:
    """The daily series of the module docstring over the run's sessions of `bars` (a `store.PanelBars`), from the
    run's `engine.Log`: {"days": int32 ordinals, each name of `SERIES`: an array, "cells": {small, under5}} (the lots
    in the pooled small cell, and in a cell left with fewer than `config.MIN_CELL` members). `capital` None is
    `config.XS_SLEEVE_USD`; `rung` None is `config.RUNG`; `haircut` None is `config.VANISH_HAIRCUT`. ValueError (fail
    closed: no series, no verdict) on a lot that names a session or column the bars lack, a sale in the entry session,
    a weight or price that is not finite."""
    raise NotImplementedError(_STUB)


def run(bars: Any, log: Any, *, n: int, seed: int, spans: Mapping[str, tuple[int, int]] | None = None,
        capital: Any = None, k: float = 1.0, rung: str | None = None,
        haircut: float | None = None) -> dict[str, Any]:
    """`n` matched placebos of the run (the module docstring's law, one `default_rng(seed)`), drawn over the WHOLE run
    and read on each of `spans` ({name: (first session index, last)}; None: {"run": the run's sessions}; a sealed
    look's are "V" and "H"). -> {"n", "rung", "seed", "spans": {name: {"days", "t" [n] (None where undefined), "sum"
    [n], "sumsq" [n]}}, "reused" (how many (draw, lot) pairs took a member the draw already held), "identity_share"
    (the share of draws that returned the program's own name: the power the cells cost)}. The x^m arithmetic is
    vectorized over the draws; every t is `results.t_stat`'s expression on that span's sessions."""
    raise NotImplementedError(_STUB)


def p_value(t: float | None, placebo_t: Sequence[float | None]) -> float | None:
    """(1 + #{m : placebo_t[m] >= t}) / (len(placebo_t) + 1); an undefined placebo t counts as not above; None when
    `t` itself is undefined (the look then fails on its t)."""
    raise NotImplementedError(_STUB)


def count_above(t: float | None, placebo_t: Sequence[float | None]) -> int | None:
    """#{m : placebo_t[m] >= t}: the integer the gate's bar is held on (the pre-registration: count <= 119 of 999)."""
    raise NotImplementedError(_STUB)


def stat(blocks: Sequence[Mapping[str, Any]], span: str = "run") -> np.ndarray:
    """T per placebo index over SEVERAL runs' blocks pooled from their sums (the seen-span runs of one version, for
    the Train bar's rank): placebo m of one run pairs with placebo m of the next, each an independent draw. NaN where
    undefined. Never the sealed look's statistic (that is `run`'s own `t`)."""
    raise NotImplementedError(_STUB)


__all__ = ["DRAWS", "LOOK_SEED", "TRAIN_SEED", "SERIES", "look_seed", "train_seed", "residual", "run", "p_value",
           "count_above", "stat"]
