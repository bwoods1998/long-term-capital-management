"""THE SHARE SCREEN S1 as adopted (sscreen-1010 with its review's fixes F1, D3, D5, D6; amendment A9): S1-R gates,
S1-X labels. Code only.

Owner: screen. This module implements the pinned pre-registration EXACTLY (its sections 2.2-2.5, 5, 6, 7 and 9 as they
bind a program) with A9's fixes, and states its one deviation (`DEVIATIONS`) beside every verdict. Its calibrated
constants are NOT here: they come from the receipt `docs/benchmarks/equity_screen_1.json` (the study's receipt, which
the integrator copies VERBATIM from the captain's scratch and pins), whose sha256 and figures the repository's
policy.json carries in `elane.screens.<lane>` (a test holds the sha to the file; docs/benchmarks/ never reaches the
House box). A screen with no pinned receipt refuses every program (`pinned_receipt` -> None; `verdict` raises
`ScreenRefused`). A later receipt (equity_screen_2.json, a follow-up study) would land as a new file and a settings
switch, never by editing receipt 1.

THE DAILY SERIES (pre-registration section 2.2; `series`). Constant weights on the program's equity E0 (the engine's
sleeve): a lot's weight omega = its entry notional / E0. Each position contributes one leg a session t:
- held from close t-1 through close t: omega (c_t / c_{t-1} - 1);
- entered at the open of t: omega (c_t / (o_t (1 + hs)) - 1);
- exited at the open of t: omega (o_t (1 - hs) / c_{t-1} - 1) - fee / E0;
- (A2 EXTENSION, the stated deviation) entered at the CLOSE of t: its half-spread paid at t (omega (1 / (1 + hs) - 1))
  and held from then on; exited at the CLOSE of t: omega (c_t (1 - hs) / c_{t-1} - 1) - fee / E0 (the
  pre-registration's forced close-exit leg); an exit at the next OPEN after a close entry is the open leg above;
- weights reset to omega at every close, uncharged.
Effective exposure w_t: omega of positions held through t, plus half omega for each open entry and each open exit of t
(a close exit counts as held through; how a close entry counts at t is part of the A2 extension, stated by this
package with its tests). Benchmark b_t: the equal-weight cost-free close-to-close return of the program's own
instruments (its NEEDS symbols with closes at t-1 and t). Excess over a window W: x_t = r_t - w_t m_W, m_W the mean of
b over W. Round trips RT_W: full exits in W; invested days ID_W: sessions of W with a position held at the close.
Prices o and c are the store's adjustment=all opens and closes (the engine's `Bars`).

S1-R, THE GATE (`verdict`):
- step 0, the program floor (`floor`, A9 D5 and F1): on the program's own Train-era series, 20,000 null worlds (N0:
  r0 = r - w kappa, kappa = sum r / sum w over the pool) per world set, V = 250 and H = L consecutive sessions, at
  L = 194 and 251; world sets IND22 (its 2022-01-03..2024-12-31 pool) and IND1622 (2016-01-04..2019-12-31 plus
  2022-24) where the program has that history; seeds `numpy.random.default_rng([20261010, 1010, set_id, L, 0])`,
  set_id 3 = IND22, 5 = IND1622 (the receipt's `floor.seed`). c_p = the smallest c on the 0.00..5.00 grid (0.01) with
  the pass rate <= fp_cap (0.12) at BOTH L; c_H = the smallest c with share(t_H >= c and sum_H > 0) <= fp_cap at both
  L (the holdout-only guard F1: 2025 is known to authors); each the maximum over the world sets. INELIGIBLE with no
  pool of >= 300 sessions, or c_p > 5.00 or c_H > 5.00. c_used = max(c_R, c_p). The same run gives the program's own
  FP at c_used and its drift-kept pass rate (null N1), computed on the House and never committed.
- step 1, the pre-check on Validation (`precheck`): (RT_V >= 20 or ID_V >= 120) and sum_V r > 1e-12.
- step 2, after the one look (`look`): the pooled t over the 250 + |H| daily r of V and H (mean / sd(ddof 1) x
  sqrt(n)) >= c_used, sum_H r > 1e-12, AND t_H (the holdout-only t) >= c_H; sd < 1e-12 fails.
- the holdout (A9 D6): 2026-01-02 .. min(the last close before the look, 2026-12-31).
S1-X, THE LABEL (`label`): steps 1-2 on x with c_X, no floor: "alpha" or "beta"; never a gate.
BESIDE EVERY LIVE TRADE (`beside_line`): the receipt's `stated_beside_every_live_trade` filled with the program's
c_used, c_H, own FP, drift-kept rate, S1-X label and FP, and its contamination sentence; every R4 flag that applies.
THE LINEAGE (A9 D3; the store-side ration is league/swarm/elane.py's, calling these): one holdout look per lineage;
a Validation-only retry (R3, `retry_permitted`) only when the receipt permits it and the first try FAILED its pre-check
(no look spent), the retry version's hash recorded at the first try; SAME LINEAGE (`same_lineage`): Train daily
returns correlating >= 0.7 with a program already looked at, or the same template. Look and Validation outcomes of
share programs are never fed back to generators or the diagnostician (the swarm's rule).

DEVIATION (stated beside every verdict): the A2 close-fill legs above (the pre-registration knew open fills only).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

SCREEN = "S1"
C_GRID_STEP = 0.01
C_GRID_MAX = 5.00
H_LENGTHS = (194, 251)
V_LENGTH = 250
WORLDS = 20_000
MIN_POOL = 300
#: World sets of the floor and their seed ids (the receipt's `floor.seed`).
WORLD_SETS = {"IND22": 3, "IND1622": 5}
ACTIVITY_ROUND_TRIPS = 20
ACTIVITY_INVESTED_DAYS = 120
SAME_LINEAGE_CORR = 0.7
ZERO = 1e-12
#: The receipt file (the integrator copies it verbatim; docs/benchmarks/ never reaches the House box).
RECEIPT_PATH = "docs/benchmarks/equity_screen_1.json"
DEVIATIONS = (
    "A2 close fills: an entry at the close of t pays its half-spread at t; an exit at the next open is the open leg; "
    "an exit at the close is the pre-registered close-exit leg",
)


class ScreenRefused(RuntimeError):
    """No pinned receipt (or a malformed one): the screen judges no program."""


@dataclass(frozen=True)
class Receipt:
    """The pinned receipt as policy.json carries it (copied from the receipt file's keys): `receipt_sha256` (the
    file's bytes, 64 hex), `c_R`, `c_X`, `fp_cap` (0.12), `owner_wall` (0.15), `retry` (`R3_retry_permitted`), `r4`
    (`R4_flags`: archetype -> flags), `beside` (`stated_beside_every_live_trade`, a template with {c_used}, {c_H},
    {own_fp}, {n1}, {alpha|beta}, {fpx}), `fp` (`fp_zero_edge_at_cR` and the other figures stated beside)."""

    receipt_sha256: str
    c_R: float
    c_X: float
    fp_cap: float
    owner_wall: float
    retry: bool
    r4: Mapping[str, tuple[str, ...]]
    beside: str
    fp: Mapping[str, Any]


@dataclass(frozen=True)
class Series:
    """A program's daily series over one window or segment (section 2.2): `days` int32 ordinals; `r` (daily P&L on
    E0), `w` (effective exposure), `b` (benchmark) float64; `exits` int (full exits that session); `invested` bool
    (a position held at the close). Equal lengths."""

    days: np.ndarray
    r: np.ndarray
    w: np.ndarray
    b: np.ndarray
    exits: np.ndarray
    invested: np.ndarray


def receipt_sha256(path: str | Path) -> str | None:
    """sha256 of the receipt file's bytes, None when it cannot be read."""
    raise NotImplementedError("screen: league/equity/screen.py receipt_sha256")


def pinned_receipt(block: Mapping[str, Any] | None) -> Receipt | None:
    """The receipt a lane's screen block pins (the REPOSITORY's policy.json `elane.screens.<lane>`, never swarm.json):
    None unless it carries a 64-hex `receipt_sha256`, finite `c_R` and `c_X` in [0, 5], `fp_cap` and the beside
    template."""
    raise NotImplementedError("screen: league/equity/screen.py pinned_receipt")


def load_receipt(path: str | Path, *, pinned_sha256: str) -> Receipt:
    """Read a receipt file and check its sha256 against the pinned one (ScreenRefused on a mismatch or a malformed
    file): CI's and the tests' reader (a fake receipt under league/tests/fixtures only)."""
    raise NotImplementedError("screen: league/equity/screen.py load_receipt")


def series(lots: Sequence[Mapping[str, Any]], bars: Any, *, universe: Sequence[str], capital: float,
           first: int | None = None, last: int | None = None) -> Series:
    """Section 2.2's accounting (with the A2 extension) of a run's `lots` (league/equity/engine.py result["lots"])
    over the sessions [first, last] of `bars` (a `store.Bars`; default its run sessions), on E0 = `capital`."""
    raise NotImplementedError("screen: league/equity/screen.py series")


def excess(s: Series) -> np.ndarray:
    """x_t = r_t - w_t m_W over the series' own window W."""
    raise NotImplementedError("screen: league/equity/screen.py excess")


def precheck(v: Series, *, variant: str = "R") -> dict[str, Any]:
    """Step 1 on Validation: {passed, round_trips, invested_days, sum, checks}; `variant` "R" on r, "X" on x."""
    raise NotImplementedError("screen: league/equity/screen.py precheck")


def pooled_t(v: np.ndarray, h: np.ndarray) -> float | None:
    """The pooled t over the concatenated daily values (mean / sd(ddof 1) x sqrt(n)); None when sd < 1e-12."""
    raise NotImplementedError("screen: league/equity/screen.py pooled_t")


def holdout_t(h: np.ndarray) -> float | None:
    """The holdout-only t (F1's t_H); None when sd < 1e-12."""
    raise NotImplementedError("screen: league/equity/screen.py holdout_t")


def look(v: Series, h: Series, *, c: float, c_H: float | None, variant: str = "R") -> dict[str, Any]:
    """Step 2 after the one look: {passed, t, t_H, sum_h, n, checks}; `c_H` None (S1-X) skips the holdout guard."""
    raise NotImplementedError("screen: league/equity/screen.py look")


def floor(segments: Sequence[Series], *, fp_cap: float) -> dict[str, Any]:
    """Step 0 from the program's Train-era series (one `Series` per `config.TRAIN_ERA_SEGMENTS` entry, on true
    history): {eligible, why, c_p, c_H, sets {"IND22": {pool, c_p, c_H}, "IND1622": {...}}, own_fp (at c_p),
    drift_kept (N1 at c_p), worlds, seeds}. Deterministic (the receipt's seeds)."""
    raise NotImplementedError("screen: league/equity/screen.py floor")


def label(v: Series, h: Series, *, c_X: float) -> str:
    """S1-X: "alpha" when steps 1-2 pass on x with c_X (no floor, no holdout guard), else "beta"."""
    raise NotImplementedError("screen: league/equity/screen.py label")


def verdict(v: Series, h: Series, *, receipt: Receipt | None, program_floor: Mapping[str, Any]) -> dict[str, Any]:
    """The whole S1 after the look: {screen "S1", passed (S1-R), c_R, c_p, c_H, c_used, t, t_H, sum_h, precheck, label
    (S1-X), own_fp (the program's FP at c_used), drift_kept, fp_x, r4, deviations, receipt}. ScreenRefused when
    `receipt` is None; a floor that is not eligible fails the program (no look should have been spent: the swarm runs
    the floor before the look)."""
    raise NotImplementedError("screen: league/equity/screen.py verdict")


def beside_line(result: Mapping[str, Any], receipt: Receipt) -> str:
    """The receipt's `beside` template filled from a `verdict` (stated beside every live trade of the program), R4
    flags appended."""
    raise NotImplementedError("screen: league/equity/screen.py beside_line")


def retry_permitted(receipt: Receipt | None, *, first_precheck_failed: bool) -> bool:
    """R3: a second, Validation-only try of a lineage only when the receipt permits it AND the first try FAILED its
    pre-check (no look spent). Never a second look."""
    raise NotImplementedError("screen: league/equity/screen.py retry_permitted")


def same_lineage(train_r: np.ndarray, other_train_r: np.ndarray, *, same_template: bool = False) -> bool:
    """A9 D3: True when the two programs' Train daily returns (aligned on common sessions) correlate >= 0.7, or they
    use the same template."""
    raise NotImplementedError("screen: league/equity/screen.py same_lineage")


def r4_flags(receipt: Receipt | None, archetype: str | None = None) -> list[str]:
    """R4's wall flags that apply (the receipt's, for the program's nearest archetype or every archetype when None)."""
    raise NotImplementedError("screen: league/equity/screen.py r4_flags")


__all__ = ["SCREEN", "C_GRID_STEP", "C_GRID_MAX", "H_LENGTHS", "V_LENGTH", "WORLDS", "MIN_POOL", "WORLD_SETS",
           "ACTIVITY_ROUND_TRIPS", "ACTIVITY_INVESTED_DAYS", "SAME_LINEAGE_CORR", "RECEIPT_PATH", "DEVIATIONS",
           "ScreenRefused", "Receipt", "Series", "receipt_sha256", "pinned_receipt", "load_receipt", "series", "excess",
           "precheck", "pooled_t", "holdout_t", "look", "floor", "label", "verdict", "beside_line", "retry_permitted",
           "same_lineage", "r4_flags"]
