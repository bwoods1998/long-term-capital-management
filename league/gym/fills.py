"""The fill model: natural by default, better than natural only by a calibrated chance.

A structure order meets each leg's recorded NBBO on the minute after its decision. If its limit is
at or through the natural price (every long leg at the ask, every short leg at the bid) it fills
there, at the natural (a marketable limit gets the touch). Otherwise it works: each later minute
it fills AT ITS LIMIT if the natural has come through it, and otherwise only with the probability
the fill model gives, a per-minute hazard looked up by

- q: where the limit sits between the mid (0) and the natural (1), in quarter-spread buckets
  (negative is better than the mid);
- legs: one leg or a multi-leg package;
- days to expiry (0, 1-2, 3-7, 8+), moneyness of the structure's centre (|K/S - 1|: under 0.5%,
  0.5-1.5%, 1.5-3%, over 3%) and the time of day (to 10:30, to 15:00, after).

The draw is keyed by (the contracts, the day, the minute, the side) with a fixed seed, never by the
program: a trivial edit to a program cannot re-roll its luck, and two programs that send the same
order at the same minute fill or miss together. The table is fitted from Train's `trade_quote`
samples by `calibrate.py` and read from a gitignored file (`/data/calibration/fill_model.json` on a
box, `.data/gym/fill_model.json` on the laptop, or GYM_FILL_MODEL); absent, every hazard is zero:
natural fills only, the conservative default.

Size is capped by the quoted size at the natural. Stress mode widens every leg's half-spread
(1.5x for the gate's stress test) before the natural is taken.

numpy is not needed; Python 3.11+.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

#: Part of every fill's key: changing it re-rolls every draw, so it changes only with the engine version.
SEED = "ltcm-gym-fills-v1"
Q_EDGES = (-0.25, 0.0, 0.25, 0.5, 0.75, 1.0)
DTE_EDGES = (0, 1, 3, 8)
MONEY_EDGES = (0.005, 0.015, 0.03)
TOD_EDGES = (630, 900)
DEFAULT_PATHS = ("/data/calibration/fill_model.json",)


def _bucket(value: float, edges: Sequence[float]) -> int:
    i = 0
    for edge in edges:
        if value >= edge:
            i += 1
    return i


def q_bucket(q: float) -> int:
    """0: better than a quarter-spread through the mid ... 5: at or past the natural."""
    return _bucket(q, Q_EDGES)


def dte_bucket(dte: int) -> int:
    return max(0, _bucket(dte, DTE_EDGES) - 1)


def money_bucket(moneyness: float) -> int:
    return _bucket(abs(moneyness), MONEY_EDGES)


def tod_bucket(minute: int) -> int:
    return _bucket(minute, TOD_EDGES)


def cell(q: float, legs: int, dte: int, moneyness: float, minute: int) -> str:
    """The table key of one working order's minute."""
    return f"q{q_bucket(q)}|{'m' if legs > 1 else 's'}|d{dte_bucket(dte)}|k{money_bucket(moneyness)}|t{tod_bucket(minute)}"


@dataclass
class FillModel:
    """A hazard table (cell -> per-minute probability). Empty: natural fills only."""

    hazard: dict[str, float] = field(default_factory=dict)
    source: str = "default: natural only"
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def version(self) -> str:
        body = json.dumps(self.hazard, sort_keys=True).encode()
        return "natural-only" if not self.hazard else "fm-" + hashlib.sha256(body).hexdigest()[:16]

    def p(self, q: float, legs: int, dte: int, moneyness: float, minute: int) -> float:
        if q >= 1.0 - 1e-12 or not self.hazard:
            return 0.0 if q < 1.0 - 1e-12 else 1.0
        return float(self.hazard.get(cell(q, legs, dte, moneyness, minute), 0.0))

    @classmethod
    def from_json(cls, data: Mapping[str, Any], source: str = "") -> "FillModel":
        hazard = {str(k): float(v) for k, v in dict(data.get("hazard") or {}).items() if 0.0 <= float(v) <= 1.0}
        return cls(hazard=hazard, source=source or str(data.get("source") or "file"), meta=dict(data.get("meta") or {}))

    @classmethod
    def load(cls, path: str | os.PathLike | None = None) -> "FillModel":
        """The fitted table from `path`, GYM_FILL_MODEL, the box's calibration path or the laptop's
        `.data/gym/fill_model.json`; the natural-only default when none exists."""
        candidates = [path] if path else [os.environ.get("GYM_FILL_MODEL"), *DEFAULT_PATHS,
                                         str(Path(__file__).resolve().parents[2] / ".data" / "gym" / "fill_model.json")]
        for candidate in candidates:
            if candidate and Path(candidate).is_file():
                return cls.from_json(json.loads(Path(candidate).read_text()), source=str(candidate))
        if path:
            raise FileNotFoundError(f"no fill model at {path}")
        return cls()


def draw(keys: Sequence[int], day: int, minute: int, side: str) -> float:
    """A uniform number in [0, 1) keyed by the contracts, the day, the minute and the side."""
    text = f"{SEED}|{int(day)}|{int(minute)}|{side}|{','.join(str(int(k)) for k in sorted(keys))}"
    return int.from_bytes(hashlib.blake2b(text.encode(), digest_size=8).digest(), "big") / 18446744073709551616.0


__all__ = ["FillModel", "draw", "cell", "q_bucket", "dte_bucket", "money_bucket", "tod_bucket", "SEED"]
