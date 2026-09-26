"""The Gym's day: dates, windows and one root-day's arrays, with numpy alone.

Split from `store.py` (which reads Parquet and so needs pyarrow) so the House's live path, which runs
on Python 3.11 with numpy only, can import the engine's accounts and build a `DayChain` from live
quotes without pyarrow (Sept 26, 2026, from W5's review of #358). `store.py` re-exports all of it.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

import numpy as np

EPOCH = dt.date(1970, 1, 1)
WINDOWS: dict[str, tuple[dt.date, dt.date | None]] = {
    "train": (dt.date(2022, 1, 3), dt.date(2024, 12, 31)),
    "validation": (dt.date(2025, 1, 2), dt.date(2025, 12, 31)),
    "holdout": (dt.date(2026, 1, 2), dt.date(2026, 9, 25)),
    "forward": (dt.date(2026, 9, 26), None),
}
#: Windows only the gate opens.
SEALED = ("holdout", "forward")


def window_of(day: dt.date) -> str:
    """The window a date belongs to: train, validation, holdout, forward (or pre / gap outside them)."""
    if day < WINDOWS["train"][0]:
        return "pre"
    for name in ("train", "validation", "holdout"):
        start, end = WINDOWS[name]
        if start <= day <= end:
            return name
    if day >= WINDOWS["forward"][0]:
        return "forward"
    return "gap"


def ordinal(day: dt.date) -> int:
    """Days since 1970-01-01 (pyarrow's date32)."""
    return (day - EPOCH).days


def from_ordinal(value: int) -> dt.date:
    return EPOCH + dt.timedelta(days=int(value))


@dataclass
class Underlying:
    """One root's underlying for one day: `price[i]` at minute index i (NaN where none), plus the
    optional one-minute bars (a bar stamped at index i closes at i + 1)."""

    price: np.ndarray
    open: np.ndarray | None = None
    high: np.ndarray | None = None
    low: np.ndarray | None = None
    close: np.ndarray | None = None
    volume: np.ndarray | None = None
    settle: np.ndarray | None = None     # a recorded settlement level (optional column `settle`)


@dataclass
class DayChain:
    """One root's day: contracts (sorted by expiry, strike, right) and [minute, contract] grids."""

    root: str
    day: dt.date
    open_min: int
    close_min: int
    expiration: np.ndarray      # int32 day ordinals, one per contract
    dte: np.ndarray             # int16 calendar days to expiry
    strike: np.ndarray          # float64 dollars
    is_call: np.ndarray         # bool
    bid: np.ndarray             # float64 [M, C] (minute-major), rounded to 1e-4, NaN = no quote
    ask: np.ndarray             # float64 [M, C]
    bid_size: np.ndarray        # int32 [M, C]
    ask_size: np.ndarray        # int32 [M, C]
    oi: np.ndarray              # int64 per contract (0 where unknown)
    underlying: Underlying
    key: np.ndarray = field(default=None)  # int64 contract identity key (expiration, strike, right)

    @property
    def minutes(self) -> int:
        return self.close_min - self.open_min + 1

    @property
    def contracts(self) -> int:
        return int(self.strike.shape[0])

    def index_of(self, keys: np.ndarray) -> np.ndarray:
        """Today's contract index for each identity key (-1 where the contract is not in today's chain)."""
        keys = np.asarray(keys, dtype=np.int64)
        pos = np.searchsorted(self.key, keys)
        pos = np.clip(pos, 0, max(0, self.key.shape[0] - 1))
        found = (self.key.shape[0] > 0) & (self.key[pos] == keys) if self.key.shape[0] else np.zeros(keys.shape, bool)
        return np.where(found, pos, -1)


def contract_key(expiration: Any, strike: Any, is_call: Any) -> np.ndarray:
    """An int64 identity for (expiration ordinal, strike to the tenth of a cent, right): sortable in the
    store's own order (expiry, strike, right with calls first)."""
    e = np.asarray(expiration, dtype=np.int64)
    k = np.rint(np.asarray(strike, dtype=np.float64) * 1000.0).astype(np.int64)
    c = np.where(np.asarray(is_call, dtype=bool), 0, 1).astype(np.int64)
    return (e * 100_000_000 + k) * 2 + c


__all__ = ["EPOCH", "WINDOWS", "SEALED", "window_of", "ordinal", "from_ordinal", "Underlying", "DayChain", "contract_key"]
