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
#: Train's reach. Its first day is 2017-01-03 (Train from 2017, Sept 29, 2026: 2017's calm, the February 2018 volatility
#: shock and the fourth-quarter 2018 selloff, 2019; before it the 2020-21 extension of Sept 27 reached 2020-01-02).
#: What a run covers is the image's data from the swarm's `gym.train_from` on (league/swarm/settings.py): an image
#: holds a Train day only from the first Train day it was built with (`Store.train_first`: the first Train day with a
#: chain, so an image built from 2020 keeps its 2019 history sessions out of Train), and every image built before this
#: change starts at 2020-01-02 or `TRAIN_CORE_START`. Ordinals count from EPOCH, never from a window, so extending a
#: window moves none of them.
TRAIN_CORE_START = dt.date(2022, 1, 3)
WINDOWS: dict[str, tuple[dt.date, dt.date | None]] = {
    "train": (dt.date(2017, 1, 3), dt.date(2024, 12, 31)),
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
    optional completed one-minute bars. SIP ingestion places a bar at its availability minute: the bar beginning
    at 09:30 occupies index 1 (09:31). Index 0 has no completed regular-session bar. Missing volume stays NaN."""

    price: np.ndarray
    open: np.ndarray | None = None
    high: np.ndarray | None = None
    low: np.ndarray | None = None
    close: np.ndarray | None = None
    volume: np.ndarray | None = None
    settle: np.ndarray | None = None     # a recorded settlement level (optional column `settle`)
    volume_available_at: np.ndarray | None = None  # live first-observed minute; historical grids use their own index

    def completed_volumes(self, mi: int) -> np.ndarray:
        """Completed regular-session bars visible by minute `mi`, aligned from the open; never forward filled.
        Live bars observed late remain unavailable to an earlier decision, including a delayed shadow decision."""
        n = max(0, min(int(mi), len(self.price) - 1))
        out = np.full(n, np.nan)
        if self.volume is None:
            return out
        count = min(n, max(0, len(self.volume) - 1))
        values = np.asarray(self.volume[1:count + 1], dtype=np.float64)
        known = np.isfinite(values) & (values >= 0)
        if self.volume_available_at is not None:
            available = np.asarray(self.volume_available_at[1:count + 1], dtype=np.float64)
            if len(available) != count:
                return out
            known &= np.isfinite(available) & (available <= mi)
        out[:count] = np.where(known, values, np.nan)
        return out

    def session_volume(self) -> float:
        """A complete regular session's total only; a partial or absent series is unknown, including missing zeros."""
        values = self.completed_volumes(len(self.price) - 1)
        return float(values.sum()) if values.size and np.isfinite(values).all() else float("nan")


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


__all__ = ["EPOCH", "TRAIN_CORE_START", "WINDOWS", "SEALED", "window_of", "ordinal", "from_ordinal", "Underlying", "DayChain", "contract_key"]
