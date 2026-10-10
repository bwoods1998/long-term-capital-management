"""A synthetic equity store for tests: geometric Brownian motion on the true NYSE calendar, never market data.

Owner: core. Every package's tests that need a store build one here (the engine's golden P&L, the screen's floor on a
synthetic store, the I6 test, the book's bar reads, ops' audit), through `store.write_store`, so the layout is one.
Splits and dividends are injected where asked, so the as-of adjustment, the dividend booking and the audit's split
detection have something to find. A synthetic store is marked `"source": "synthetic"` in its manifest.

Standard library and numpy only.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Mapping, Sequence


def synthetic_store(root: str | Path, *, symbols: Sequence[str] = ("SPY", "QQQ", "IWM", "DIA"),
                    start: dt.date = dt.date(2016, 1, 4), end: dt.date = dt.date(2026, 10, 9), seed: int = 7,
                    drift: float = 0.0, vol: float = 0.18,
                    splits: Mapping[str, Sequence[tuple[dt.date, float]]] | None = None,
                    dividends: Mapping[str, Sequence[tuple[dt.date, float]]] | None = None, gate: bool = False,
                    gaps: Mapping[str, Sequence[dt.date]] | None = None) -> Path:
    """Write a synthetic store at `root` (the sessions of `store.nyse_sessions(start, end)`) and
    return its path. `splits[sym]`: (ex-day, factor) pairs (2.0 = a 2-for-1). `dividends[sym]`: (ex-day, dollars a
    share). `gaps[sym]`: sessions the symbol has no bar on (an audit failure to find). Deterministic in `seed`."""
    raise NotImplementedError("core: league/equity/synth.py synthetic_store")


def constant_store(root: str | Path, *, symbol: str = "SPY", start: dt.date = dt.date(2025, 1, 2), sessions: int = 20,
                   price: float = 100.0, step: float = 0.0, gate: bool = False) -> Path:
    """A store whose one symbol opens and closes at `price` + i x `step` on session i (open = close of the same day,
    high = low = close): hand-checkable golden P&L."""
    raise NotImplementedError("core: league/equity/synth.py constant_store")


__all__ = ["synthetic_store", "constant_store"]

