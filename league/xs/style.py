"""THE STYLE READING (the captain's A22, item 1): a panel program's loadings on size, beta, 12-1 momentum and
volatility, read from its Train holdings, and the fixed rule that marks it STYLE-OPEN.

Owner: package E. Package D's engine calls `block`; package G keeps the verdict and holds the seat rule on it.

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
  `SIZE_MIN_VALID` valid (a valid session has a raw close and a raw volume above zero);
- "beta": `ctx.Derived.beta`;
- "mom": `ctx.Derived.mom` (the 12-1 return);
- "vol": the standard deviation (ddof 1) of ln c(k) / c(k - 1) on total-return closes over the `VOL_SESSIONS`
  returns through d, with at least `VOL_MIN_VALID` valid (a valid return has both closes above zero).

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

THE BAR IS HELD AT ITS EDGE: a loading within `EDGE` of `TILT` is at it (open), so a tilt of exactly one third never
hangs on the last bit of a float. A LOT THE READING CANNOT READ (no decision row, a column outside the bars, a weight
that is no positive number) is counted among the run's lots and carries no characteristic: it can only bring the
reading under `MIN_LOTS`, which opens the program.

Evidence module (in the xs identity: `engine` imports it; a fixed judge: league/ci.py holds league/xs/ out of every
role's reach). numpy and the standard library only; of this package, `config`'s constants.
"""

from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

import numpy as np

from . import config

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
#: A loading this close under `TILT` is at it (the bar never hangs on a float's last bit).
EDGE = 1e-12
#: The verdict's words: the receipt's own flag name, and the reason of a program the rule could not read.
OPEN = "style-open"
UNMEASURED = "unmeasured"
#: What `block` returns, and what `pooled` adds to it.
BLOCK_KEYS = ("lots", "n", "weight", "sum")
POOLED_KEYS = ("lots", "n", "loadings")
VERDICT_KEYS = ("open", "why", "tilts", "loadings", "lots", "rule")
#: The columns of a raw bar (o h l c v) and of an adjusted one (o h l c) the characteristics read.
_RAW_CLOSE, _RAW_VOLUME, _ADJ_CLOSE = 3, 4, 3


def characteristics(raw: np.ndarray, adj: np.ndarray, derived: Any) -> dict[str, np.ndarray]:
    """The four characteristics at the close the two windows end on: {name of `CHARACTERISTICS`: float64 (m,)} by
    column, NaN where the name is not eligible (`derived.elig`), is a REF column, or the characteristic is undefined.
    `raw` (len, m, 5) and `adj` (len, m, 4) are a decision's own windows (`ctx.Inputs.raw`, `.adj`: the sessions
    through d, oldest first), `derived` its `ctx.Derived`. Never a row after d.

    A window shorter than a characteristic needs leaves it undefined (NaN) for every name. ValueError when the
    arrays do not agree on their columns."""
    raw = np.asarray(raw, dtype=np.float64)
    adj = np.asarray(adj, dtype=np.float64)
    elig = np.asarray(derived.elig, dtype=bool)
    if raw.ndim != 3 or adj.ndim != 3 or raw.shape[2] < 5 or adj.shape[2] < 4 or raw.shape[:2] != adj.shape[:2]:
        raise ValueError(f"the windows are not (sessions, columns, 5) and (sessions, columns, 4): {raw.shape}, "
                         f"{adj.shape}")
    m = raw.shape[1]
    beta, mom = np.asarray(derived.beta, dtype=np.float64), np.asarray(derived.mom, dtype=np.float64)
    if not (elig.shape == beta.shape == mom.shape == (m,)):
        raise ValueError(f"the decision's characteristics are not one a column ({m})")
    size, vol = np.full(m, np.nan), np.full(m, np.nan)
    with np.errstate(divide="ignore", invalid="ignore"):
        if raw.shape[0] >= SIZE_SESSIONS:
            close, volume = raw[-SIZE_SESSIONS:, :, _RAW_CLOSE], raw[-SIZE_SESSIONS:, :, _RAW_VOLUME]
            valid = np.isfinite(close) & np.isfinite(volume) & (close > 0) & (volume > 0)
            dollars = np.where(valid, close * volume, np.nan)
            enough = valid.sum(0) >= SIZE_MIN_VALID
            # the median of each column's valid sessions: its sorted values, NaN last, read at the middle
            ordered = np.sort(dollars, axis=0)
            count = valid.sum(0)
            lower = np.take_along_axis(ordered, np.maximum((count - 1) // 2, 0)[None, :], axis=0)[0]
            upper = np.take_along_axis(ordered, np.maximum(count // 2, 0)[None, :], axis=0)[0]
            size = np.where(enough, 0.5 * (lower + upper), np.nan)
        if adj.shape[0] >= VOL_SESSIONS + 1:
            close = adj[-(VOL_SESSIONS + 1):, :, _ADJ_CLOSE]
            good = np.isfinite(close) & (close > 0)
            valid = good[1:] & good[:-1]
            step = np.where(valid, np.log(np.where(valid, close[1:] / np.where(good[:-1], close[:-1], 1.0), 1.0)), 0.0)
            count = valid.sum(0)
            enough = count >= VOL_MIN_VALID
            mean = step.sum(0) / np.maximum(count, 1)
            spread = np.where(valid, step - mean[None, :], 0.0)
            vol = np.where(enough, np.sqrt((spread * spread).sum(0) / np.maximum(count - 1, 1)), np.nan)
    out = {"size": size, "beta": beta, "mom": mom, "vol": vol}
    return {name: np.where(elig & np.isfinite(out[name]), out[name], np.nan) for name in CHARACTERISTICS}


def ranks(values: np.ndarray) -> np.ndarray:
    """2 p - 1 by column for one characteristic's values (the module docstring's rank: ascending by (value, column)
    among the finite ones); NaN where the value is NaN."""
    values = np.asarray(values, dtype=np.float64).ravel()
    out = np.full(len(values), np.nan)
    finite = np.flatnonzero(np.isfinite(values))
    n = len(finite)
    if n:
        order = finite[np.argsort(values[finite], kind="stable")]      # a stable sort: ties stay in column order
        out[order] = 2.0 * (np.arange(n) + 0.5) / n - 1.0
    return out


def _ranks_at(bars: Any, t: int, derived: Any) -> dict[str, np.ndarray]:
    """Every column's rank on the four characteristics at the close of session index `t`: the bars' rows through t
    (at most `config.DERIVE_SESSIONS` of them: a decision's own window), never one after."""
    lo = max(0, t + 1 - config.DERIVE_SESSIONS)
    got = characteristics(np.asarray(bars.raw)[lo:t + 1], np.asarray(bars.adj)[lo:t + 1], derived)
    return {name: ranks(got[name]) for name in CHARACTERISTICS}


def block(bars: Any, log: Any) -> dict[str, Any]:
    """One run's style block, from the bars (`store.PanelBars`) and the holdings log (`engine.Log`) alone: {"lots":
    the run's lots, "n": {c: the lots whose c is defined}, "weight": {c: the sum of their w}, "sum": {c: the sum of
    w x (2 p - 1)}} for c in `CHARACTERISTICS`, each lot read at its decision close. Computed in the child at the end
    of a run asked with `style=True`; no id, column or price is in it.

    It never fails a run: a lot it cannot read (the module docstring) is counted in "lots" and nowhere else."""
    decided: dict[int, Any] = {}
    for row in getattr(log, "decisions", None) or ():
        try:
            decided[int(row["t"])] = row["derived"]
        except (KeyError, TypeError, ValueError):
            continue
    lots = list(getattr(log, "lots", None) or ())
    sessions = len(np.asarray(bars.raw)) if hasattr(bars, "raw") else 0
    at: dict[int, dict[str, np.ndarray] | None] = {}
    weights: dict[str, list[float]] = {name: [] for name in CHARACTERISTICS}
    products: dict[str, list[float]] = {name: [] for name in CHARACTERISTICS}
    for lot in lots:
        try:
            t, col, w = int(lot["decided"]), int(lot["col"]), float(lot["weight"])
            if not (math.isfinite(w) and w > 0 and 0 <= t < sessions and t in decided):
                continue
            if t not in at:
                try:
                    at[t] = _ranks_at(bars, t, decided[t])
                except (AttributeError, IndexError, TypeError, ValueError):
                    at[t] = None
            read = at[t]
            if read is None or not 0 <= col < len(read[CHARACTERISTICS[0]]):
                continue
            for name in CHARACTERISTICS:
                rank = float(read[name][col])
                if math.isfinite(rank):
                    weights[name].append(w)
                    products[name].append(w * rank)
        except (KeyError, TypeError, ValueError):
            continue
    return {"lots": len(lots), "n": {name: len(weights[name]) for name in CHARACTERISTICS},
            "weight": {name: math.fsum(weights[name]) for name in CHARACTERISTICS},
            "sum": {name: math.fsum(products[name]) for name in CHARACTERISTICS}}


def _count(value: Any) -> int | None:
    """A count (an int, never a bool, never negative), else None."""
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)) or int(value) < 0:
        return None
    return int(value)


def _real(value: Any) -> float | None:
    """A finite real number (never a bool), else None."""
    if isinstance(value, bool) or not isinstance(value, (int, float, np.integer, np.floating)):
        return None
    v = float(value)
    return v if math.isfinite(v) else None


def _block_ok(block_: Any) -> bool:
    """Whether a block is one `block` could have written: its keys, counts no larger than its lots, weights that are
    no negative number, and sums no larger than their weights (a rank lies inside -1..+1)."""
    if not isinstance(block_, Mapping) or any(key not in block_ for key in BLOCK_KEYS):
        return False
    lots = _count(block_["lots"])
    if lots is None or not all(isinstance(block_[key], Mapping) for key in ("n", "weight", "sum")):
        return False
    for name in CHARACTERISTICS:
        n = _count(block_["n"].get(name))
        weight, total = _real(block_["weight"].get(name)), _real(block_["sum"].get(name))
        if n is None or n > lots or weight is None or total is None or weight < 0:
            return False
        if abs(total) > weight + EDGE or (n == 0) != (weight == 0):
            return False
    return True


def pooled(blocks: Sequence[Mapping[str, Any] | None]) -> dict[str, Any]:
    """Several runs' blocks read as one (the seen spans of one version): {"lots", "n": {c}, "loadings": {c: L_c, or
    None when no lot carries c}}. A missing or malformed block makes the whole reading None-valued (the rule then
    reads "unmeasured")."""
    unread = {"lots": None, "n": {name: None for name in CHARACTERISTICS},
              "loadings": {name: None for name in CHARACTERISTICS}}
    if isinstance(blocks, (str, bytes, Mapping)) or not isinstance(blocks, Sequence) or len(blocks) == 0:
        return unread
    if not all(_block_ok(block_) for block_ in blocks):
        return unread
    out: dict[str, Any] = {"lots": sum(int(b["lots"]) for b in blocks), "n": {}, "loadings": {}}
    for name in CHARACTERISTICS:
        out["n"][name] = sum(int(b["n"][name]) for b in blocks)
        weight = math.fsum(float(b["weight"][name]) for b in blocks)
        total = math.fsum(float(b["sum"][name]) for b in blocks)
        out["loadings"][name] = total / weight if out["n"][name] > 0 and weight > 0 else None
    return out


def style_open(reading: Mapping[str, Any] | None) -> dict[str, Any]:
    """THE RULE on a `pooled` reading: {"open": bool, "why": `OPEN` | `UNMEASURED` | None, "tilts": [[c, +1 | -1]]
    (the characteristics at or past `TILT`, in `CHARACTERISTICS`' order), "loadings": {c: L_c | None}, "lots",
    "rule": {"tilt": `TILT`, "min_lots": `MIN_LOTS`}}. Fails CLOSED: None, a malformed reading, a loading that is not
    finite or fewer than `MIN_LOTS` lots is open with why `UNMEASURED`.

    `why` is `UNMEASURED` whenever ANY of the four was read on fewer than `MIN_LOTS` lots or has no finite loading
    inside -1..+1 (the reading is not whole), whatever the others say; `tilts` still names the tilts of the
    characteristics that were read."""
    rule = {"tilt": TILT, "min_lots": MIN_LOTS}
    shape = isinstance(reading, Mapping) and all(isinstance(reading.get(key), Mapping) for key in ("n", "loadings"))
    lots = _count(reading.get("lots")) if shape else None
    loadings: dict[str, float | None] = {name: None for name in CHARACTERISTICS}
    tilts: list[list[Any]] = []
    whole = shape and lots is not None
    for name in CHARACTERISTICS:
        n = _count(reading["n"].get(name)) if shape else None
        value = _real(reading["loadings"].get(name)) if shape else None
        if value is not None and abs(value) > 1.0 + EDGE:
            value = None                                   # no weighted mean of ranks lies outside -1..+1
        read = n is not None and lots is not None and MIN_LOTS <= n <= lots and value is not None
        loadings[name] = value
        whole = whole and read
        if read and abs(value) >= TILT - EDGE:
            tilts.append([name, 1 if value > 0 else -1])
    why = UNMEASURED if not whole else OPEN if tilts else None
    return {"open": why is not None, "why": why, "tilts": tilts, "loadings": loadings, "lots": lots, "rule": rule}


def _words(tilts: Any) -> str:
    """A verdict's tilts as a report prints them ("size +, vol -"); "" when it names none it can read."""
    parts = []
    if isinstance(tilts, Sequence) and not isinstance(tilts, (str, bytes)):
        for item in tilts:
            if isinstance(item, Sequence) and not isinstance(item, (str, bytes)) and len(item) == 2 \
                    and item[0] in CHARACTERISTICS and item[1] in (1, -1) and not isinstance(item[1], bool):
                parts.append(f"{item[0]} {'+' if item[1] > 0 else '-'}")
    return ", ".join(parts)


def seat_refusal(verdict: Mapping[str, Any] | None) -> str | None:
    """Why a program with this `style_open` verdict takes no live seat on an XS1 pass alone, or None when it may: the
    words a report prints ("style-open: size +, vol -" / "style-open: unmeasured"). None ONLY for a well-formed
    verdict whose `open` is False under this module's own `TILT` and `MIN_LOTS` (a verdict made under other figures is
    refused: run the reading again).

    The verdict is not taken at its word: its loadings are held to the bar AGAIN (a stored verdict that says "not
    open" beside a loading at or past `TILT`, a loading it lacks, or fewer than `MIN_LOTS` lots is refused as
    unmeasured)."""
    unmeasured = f"{OPEN}: {UNMEASURED}"
    if not isinstance(verdict, Mapping) or any(key not in verdict for key in VERDICT_KEYS):
        return unmeasured
    words = _words(verdict.get("tilts"))
    rule = verdict.get("rule")
    if not isinstance(rule, Mapping) or _real(rule.get("tilt")) != TILT or _count(rule.get("min_lots")) != MIN_LOTS:
        return f"{unmeasured} (a verdict under other figures: run the reading again)"
    if verdict.get("open") is not False:
        if verdict.get("why") == OPEN and words:
            return f"{OPEN}: {words}"
        return f"{unmeasured}, {words}" if words else unmeasured
    loadings, lots = verdict.get("loadings"), _count(verdict.get("lots"))
    if verdict.get("why") is not None or words or verdict.get("tilts") not in ([], ()) \
            or not isinstance(loadings, Mapping) or lots is None or lots < MIN_LOTS:
        return unmeasured
    for name in CHARACTERISTICS:
        value = _real(loadings.get(name))
        if value is None or abs(value) >= TILT - EDGE:
            return unmeasured
    return None


__all__ = ["CHARACTERISTICS", "SIZE_SESSIONS", "SIZE_MIN_VALID", "VOL_SESSIONS", "VOL_MIN_VALID", "TILT", "MIN_LOTS",
           "EDGE", "OPEN", "UNMEASURED", "BLOCK_KEYS", "POOLED_KEYS", "VERDICT_KEYS", "characteristics", "ranks", "block", "pooled", "style_open", "seat_refusal"]
