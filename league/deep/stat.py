"""x2, THE DEEP KEY'S STATISTIC: the per-symbol drift-free timing excess.

Owner: R1. PREREG-H: x2_t = r_t - sum_s w_{s,t} mu_s, where r_t is the program's daily P&L on E0 and w_{s,t} its
effective exposure to symbol s, both from league/equity/screen.py `series` (the pre-registration's constant-weight
accounting with the A2 close legs, reused by import and run once per symbol), and mu_s is s's mean cost-free
close-to-close return (adjustment=all closes) over the series being scored (`config.READINGS`: the full DVAL series
for the full t, its unmasked sessions for the masked t).

A constant-weight hold scores zero: over the sessions it holds, sum_t w (ret_t - mu) is w x (sum ret - n mu) = 0. So
a static tilt gets no credit (long GLD, XLE and TLT over XLK in 2001-08), which is stricter than S1-X's `excess`
(that removes the equal-weight universe's drift only). What is left is timing: being in a symbol when it does better
than its own average over the window.

COSTS. A part's lots are re-costed at k x hs (`costed`): the series charges each lot's half-spread at its entry and
its exit, so the judged x2 (k 2.0) and the stress sum (k 3.0) come from the same lots.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import numpy as np

from ..equity import config as econfig
from ..equity import screen


@dataclass(frozen=True)
class Part:
    """One run's scored sessions: its `lots` (league/equity/engine.py result["lots"]), the `bars` it ran on (a
    `store.Bars`), the program's NEEDS `symbols`, its `capital` (E0), the scored window [first, last] (indices into the
    bars) and `keep` (bool per scored session: False on a masked one; None: none is masked)."""

    lots: Sequence[Mapping[str, Any]]
    bars: Any
    symbols: tuple[str, ...]
    capital: float
    first: int
    last: int
    keep: np.ndarray | None = None

    @property
    def n(self) -> int:
        return self.last - self.first + 1


def costed(lots: Sequence[Mapping[str, Any]], k: float) -> list[dict[str, Any]]:
    """The lots with their half-spread at k x hs (hs the lot's own, else `config.half_spread`)."""
    out = []
    for lot in lots:
        row = dict(lot)
        hs = row.get("hs")
        hs = econfig.half_spread(str(row.get("symbol"))) if hs is None else float(hs)
        row["hs"] = hs * float(k)
        out.append(row)
    return out


def legs(part: Part, k: float) -> dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]]:
    """{symbol: (r, w, ret)} over the part's scored sessions: its own P&L and exposure (`screen.series` of its lots
    alone, at k x hs) and its cost-free close-to-close return (NaN where it has no two closes)."""
    lots = costed(part.lots, k)
    out = {}
    for sym in part.symbols:
        mine = [lot for lot in lots if lot.get("symbol") == sym]
        s = screen.series(mine, part.bars, universe=[sym], capital=part.capital, first=part.first, last=part.last)
        c = np.asarray(part.bars.adj[sym], dtype=np.float64)[:, 3]
        lo = part.first
        now = c[lo:part.last + 1]
        prev = c[lo - 1:part.last] if lo > 0 else np.concatenate([[np.nan], c[lo:part.last]])
        with np.errstate(divide="ignore", invalid="ignore"):
            ret = np.where(np.isfinite(now) & np.isfinite(prev) & (prev > 0), now / prev - 1.0, np.nan)
        out[sym] = (np.asarray(s.r, dtype=np.float64), np.asarray(s.w, dtype=np.float64), ret)
    return out


def x2(parts: Sequence[Part], *, k: float, masked: bool = False) -> np.ndarray:
    """x2 over the parts' scored sessions, in order (`masked`: their kept sessions only, mu_s over those), on the
    symbols the parts name. An empty series is an empty array."""
    per: dict[str, list[tuple[np.ndarray, np.ndarray, np.ndarray]]] = {}
    keeps = []
    for part in parts:
        keep = np.ones(part.n, dtype=bool) if (part.keep is None or not masked) else np.asarray(part.keep, dtype=bool)
        if keep.shape != (part.n,):
            raise ValueError("a part's mask is not one flag a scored session")
        keeps.append(keep)
        for sym, (r, w, ret) in legs(part, k).items():
            per.setdefault(sym, []).append((r[keep], w[keep], ret[keep]))
    total = int(sum(int(keep.sum()) for keep in keeps))
    out = np.zeros(total)
    for sym, rows in per.items():
        if len(rows) != len(parts):
            raise ValueError(f"{sym} is not in every part")
        r = np.concatenate([row[0] for row in rows])
        w = np.concatenate([row[1] for row in rows])
        ret = np.concatenate([row[2] for row in rows])
        finite = np.isfinite(ret)
        mu = float(ret[finite].mean()) if finite.any() else 0.0
        out += r - w * mu
    return out


def piece(part: Part, *, skip: int = 2) -> dict[str, np.ndarray]:
    """One own-floor pool piece of a Train-era (or TRAIN-D) run (the receipt's `floor.series`), from its first
    decision + `skip` sessions: per session "r2" (r at k 2.0, the deep key's cost), "r1" (r at k 1.0, the recent
    key's), "w" (the total exposure), "W" and "RET" (symbols x sessions: each symbol's exposure and cost-free
    close-to-close return, NaN where it has no two closes) and "b" (the equal-weight cost-free return of the
    program's symbols, 0 where none has one)."""
    deep, recent = legs(part, 2.0), legs(part, 1.0)
    names = list(part.symbols)
    W = np.vstack([deep[s][1] for s in names])
    RET = np.vstack([deep[s][2] for s in names])
    r2 = np.sum([deep[s][0] for s in names], axis=0)
    r1 = np.sum([recent[s][0] for s in names], axis=0)
    ok = np.isfinite(RET)
    count = ok.sum(0)
    b = np.where(count > 0, np.where(ok, RET, 0.0).sum(0) / np.maximum(count, 1), 0.0)
    cut = slice(min(int(skip), part.n), None)
    return {"r2": r2[cut], "r1": r1[cut], "w": W.sum(0)[cut], "W": W[:, cut], "RET": RET[:, cut], "b": b[cut]}


def t(x: np.ndarray) -> float | None:
    """mean / sd(ddof 1) x sqrt(n) (league/equity/screen.py's t); None when sd < 1e-12 or fewer than 2 values."""
    return screen.holdout_t(np.asarray(x, dtype=np.float64))


__all__ = ["Part", "costed", "legs", "x2", "piece", "t"]
