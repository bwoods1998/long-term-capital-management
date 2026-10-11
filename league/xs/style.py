"""THE STYLE READING (the captain's A22, item 1): a panel program's loadings on size, beta, 12-1 momentum and
volatility, read from its Train holdings, and the fixed rule that marks it STYLE-OPEN.

Owner: package E. STEP 0 STUB: the constants are the contract (package D's engine calls `block`, package G keeps the
verdict and holds the seat rule on it); every function raises NotImplementedError until E lands.

WHY. The study XSCREEN-1 measured that a program with NO selection skill that merely tilts to a style passes XS1 far
above the owner's wall when that style won the holdout (the receipt's `style_known_rate` and `style_known_max`): the
screen's cells match the sector, a beta third and a momentum third, and nothing matches size, volatility or the
extremes inside a third; and authors know which styles won in 2025 and 2026. The receipt's own flag, "style-open",
attaches by French's factors, which are not on the House, so there it would attach to every program and gate nothing.
So the captain's amendment A22 binds the House before any real money on an XS1 pass: A STYLE-OPEN PROGRAM TAKES NO
LIVE SEAT ON AN XS1 PASS ALONE. Its pass is recorded, the forward record shadows it, and it is never seated by the
look (`league.swarm.elane_xs.look`); the forward route is its way to a seat. Style-open is read from the House's OWN
loadings, by the rule below, never from a label the House cannot compute.

THE FOUR CHARACTERISTICS of a name at a decision close d, from data up to d only (the study's own definitions: its
pre-registration's 9.4 arm STYLE and 3.2; none is ever shown to a program, size least of all):
- "size": the median of raw close x raw volume over the `SIZE_SESSIONS` sessions through d, with at least
  `SIZE_MIN_VALID` valid;
- "beta": `ctx.Derived.beta`;
- "mom": `ctx.Derived.mom` (the 12-1 return);
- "vol": the standard deviation (ddof 1) of ln c(k) / c(k - 1) on total-return closes over the `VOL_SESSIONS`
  returns through d, with at least `VOL_MIN_VALID` valid.

A LOT'S RANK. For a lot decided at d and a characteristic c: among the names of U(d) with c defined (n of them),
ranked ascending by (value, column), the lot's name at rank q (0-based) has p = (q + 0.5) / n, and the lot's loading
on c is 2 p - 1: -1 the lowest name of the day, +1 the highest, 0 the middle. Read at the lot's DECISION close, as
its cell is, and never again.

A PROGRAM'S LOADING on c: L_c = sum over its Train lots of w x (2 p - 1) / sum of w, the lots whose c is undefined
left out (`math.fsum`). THE TRAIN LOTS are the lots of the version's seen-span runs of the full universe at k 1.0
(the Train bar's own runs: `engine.run(..., style=True)` puts each run's `block` in its result; `pooled` reads them as
one). A program that picks uniformly at random has L_c near 0 (its standard error is about 0.58 / sqrt(lots)).

THE RULE (`style_open`; fixed, direction-blind, and no threshold of it is a setting). A program is STYLE-OPEN when
1. fewer than `MIN_LOTS` of its Train lots carry a characteristic, or no reading exists at all ("unmeasured": the rule
   fails CLOSED, as the receipt's own flag does for an unmeasured label); or
2. |L_c| >= `TILT` for ANY of the four: the weighted mean rank of what it held sits in the top third or the bottom
   third of the day's eligible names by that characteristic, which is where the study's no-skill tilt programs hold.
Otherwise it is not. The verdict names the characteristics that opened it and their signs, so the report can say
which style a passer leans on. WHAT THIS COSTS, stated: a momentum or a low-volatility program is style-open by
construction and is seated only by the forward route, though the study measured one direction of one tilt (the
highest momentum) well under the wall; the rule is blind to direction on purpose (E4_INTERFACES.md's open points say
what a direction-aware rule would read from the receipt). Changing `TILT`, `MIN_LOTS` or a definition is a new xs
identity, never a setting.

Evidence module (in the xs identity: `engine` imports it; a fixed judge: league/ci.py holds league/xs/ out of every
role's reach). numpy and the standard library only.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

import numpy as np

#: The four, in the order every block, verdict and report line names them.
CHARACTERISTICS = ("size", "beta", "mom", "vol")
#: "size": the median dollar volume's window and the valid sessions it needs.
SIZE_SESSIONS = 63
SIZE_MIN_VALID = 55
#: "vol": the returns its standard deviation reads and the valid ones it needs.
VOL_SESSIONS = 60
VOL_MIN_VALID = 55
#: THE RULE's two figures: a loading at or past `TILT` in either direction opens the program; with fewer than
#: `MIN_LOTS` Train lots carrying a characteristic it is unmeasured, which opens it too.
TILT = 1.0 / 3.0
MIN_LOTS = 40
#: The verdict's words: the receipt's own flag name, and the reason of a program the rule could not read.
OPEN = "style-open"
UNMEASURED = "unmeasured"
#: What `block` returns, and what `pooled` adds to it.
BLOCK_KEYS = ("lots", "n", "weight", "sum")
POOLED_KEYS = ("lots", "n", "loadings")
VERDICT_KEYS = ("open", "why", "tilts", "loadings", "lots", "rule")

_STUB = "league.xs.style is a Step 0 stub: package E builds it (league/xs/E4_INTERFACES.md)"


def characteristics(raw: np.ndarray, adj: np.ndarray, derived: Any) -> dict[str, np.ndarray]:
    """The four characteristics at the close the two windows end on: {name of `CHARACTERISTICS`: float64 (m,)} by
    column, NaN where the name is not eligible (`derived.elig`), is a REF column, or the characteristic is undefined.
    `raw` (len, m, 5) and `adj` (len, m, 4) are a decision's own windows (`ctx.Inputs.raw`, `.adj`: the sessions
    through d, oldest first), `derived` its `ctx.Derived`. Never a row after d."""
    raise NotImplementedError(_STUB)


def ranks(values: np.ndarray) -> np.ndarray:
    """2 p - 1 by column for one characteristic's values (the module docstring's rank: ascending by (value, column)
    among the finite ones); NaN where the value is NaN."""
    raise NotImplementedError(_STUB)


def block(bars: Any, log: Any) -> dict[str, Any]:
    """One run's style block, from the bars (`store.PanelBars`) and the holdings log (`engine.Log`) alone: {"lots":
    the run's lots, "n": {c: the lots whose c is defined}, "weight": {c: the sum of their w}, "sum": {c: the sum of
    w x (2 p - 1)}} for c in `CHARACTERISTICS`, each lot read at its decision close. Computed in the child at the end
    of a run asked with `style=True`; no id, column or price is in it."""
    raise NotImplementedError(_STUB)


def pooled(blocks: Sequence[Mapping[str, Any] | None]) -> dict[str, Any]:
    """Several runs' blocks read as one (the seen spans of one version): {"lots", "n": {c}, "loadings": {c: L_c, or
    None when no lot carries c}}. A missing or malformed block makes the whole reading None-valued (the rule then
    reads "unmeasured")."""
    raise NotImplementedError(_STUB)


def style_open(reading: Mapping[str, Any] | None) -> dict[str, Any]:
    """THE RULE on a `pooled` reading: {"open": bool, "why": `OPEN` | `UNMEASURED` | None, "tilts": [[c, +1 | -1]]
    (the characteristics at or past `TILT`, in `CHARACTERISTICS`' order), "loadings": {c: L_c | None}, "lots",
    "rule": {"tilt": `TILT`, "min_lots": `MIN_LOTS`}}. Fails CLOSED: None, a malformed reading, a loading that is not
    finite or fewer than `MIN_LOTS` lots is open with why `UNMEASURED`."""
    raise NotImplementedError(_STUB)


def seat_refusal(verdict: Mapping[str, Any] | None) -> str | None:
    """Why a program with this `style_open` verdict takes no live seat on an XS1 pass alone, or None when it may: the
    words a report prints ("style-open: size +, vol -" / "style-open: unmeasured"). None ONLY for a well-formed
    verdict whose `open` is False under this module's own `TILT` and `MIN_LOTS` (a verdict made under other figures is
    refused: run the reading again)."""
    raise NotImplementedError(_STUB)


__all__ = ["CHARACTERISTICS", "SIZE_SESSIONS", "SIZE_MIN_VALID", "VOL_SESSIONS", "VOL_MIN_VALID", "TILT", "MIN_LOTS",
           "OPEN", "UNMEASURED", "BLOCK_KEYS", "POOLED_KEYS", "VERDICT_KEYS", "characteristics", "ranks", "block",
           "pooled", "style_open", "seat_refusal"]
