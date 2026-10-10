"""The equity daily store: per-symbol raw and adjustment=all daily bars, its windows, and the gate's capability.

Owner: core (league/equity/INTERFACES.md, "core"). The writer is `write_store` here; the House job that fills it is
`league/ops/equity_data.py` (ops), which fetches Alpaca SIP daily bars through the gateway and calls `write_store`;
`league/equity/synth.py` writes synthetic stores for tests through the same function. Data never leaves the House's
state directory (the vendor's terms; a public repository): no store is ever committed or shipped to a Gym box.

LAYOUT (`<state>/equity-daily/`, numpy only, written atomically: every file to a temporary name, then renamed; the
manifest last, so a reader never sees a half-written store):

    VERSION                 "equity-store-v1"
    calendar.npz            days (int32 ordinals since 1970-01-01, every NYSE session the store covers, oldest first),
                            early (bool: a 13:00 close)
    bars/<SYMBOL>.npz       days (int32, the sessions the symbol has a bar on), raw_o, raw_h, raw_l, raw_c, raw_v
                            (float64: adjustment=raw, volume in shares), all_o, all_h, all_l, all_c (float64:
                            adjustment=all, as of the fetch day `manifest.json` names)
    manifest.json           {"version", "fetched_through" (ISO day), "symbols": {SYMBOL: {"class", "sha256", "first",
                            "last", "rows"}}, "calendar_sha256", "source": "alpaca-sip-1Day" | "synthetic",
                            "audit": {...} (equity_data's audit, or null)}
    GATE                    present on the House's own store only (the store `mint_equity_gate_capability` accepts)

THE WINDOWS (`league.equity.config.WINDOWS`): Train 2016-01-04..2024-12-31, Validation 2025, holdout
2026-01-02..2026-09-25, forward after. Holdout and forward days open only for a store built with an
`EquityGateCapability`, minted by `mint_equity_gate_capability` on a store carrying the `GATE` mark, and held by the
gate's code alone (league/swarm/gate.py's equity look, league/swarm/elane.py): an object, not a flag, as the options
store's `GateCapability` (league/gym/store.py). A program never reaches the store: the parent slices `Bars` and the
decider child sees arrays only.

AS-OF ADJUSTMENT (league/equity/ctx.py `as_of`): history at decision day t is all_s x raw_t / all_t, identical
whatever day the `all` series was fetched on (the factor of every event after t cancels), so a live fetch at t and
this store agree (I6).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

GATE_MARK = "GATE"
STORE_DIR = "equity-daily"
RAW_COLUMNS = ("raw_o", "raw_h", "raw_l", "raw_c", "raw_v")
ALL_COLUMNS = ("all_o", "all_h", "all_l", "all_c")


class StoreRefused(PermissionError):
    """A sealed day was asked for without the gate's capability, or a window was misnamed."""


class MissingData(FileNotFoundError):
    """The store lacks what a run needs (the message names it)."""


class EquityGateCapability:
    """Proof that the caller is the gate. It cannot be constructed; `mint_equity_gate_capability` mints one on a store
    that carries the `GATE` mark. Holding one is what lets an `EquityStore` open holdout and forward days."""

    __slots__ = ("reason", "store_root")

    def __init__(self, *args: Any, **kwargs: Any):
        raise TypeError("an EquityGateCapability is minted by mint_equity_gate_capability(), never constructed")


def mint_equity_gate_capability(store_root: str | Path, reason: str) -> EquityGateCapability:
    """The gate's capability for the store at `store_root` (which must carry the `GATE` mark; `reason` is required and
    recorded). StoreRefused otherwise. Mirrors `league.gym.store.mint_gate_capability`."""
    raise NotImplementedError("core: league/equity/store.py mint_equity_gate_capability")


def window_of(day: dt.date) -> str:
    """"train", "validation", "holdout", "forward", or "pre" / "gap" outside them (`config.WINDOWS`)."""
    raise NotImplementedError("core: league/equity/store.py window_of")


@dataclass(frozen=True)
class Bars:
    """One run's slice of the store, numpy only, the same shape for the Gym and the live path (a live fetch at 16:20 is
    turned into one too: league/equity/ctx.py `inputs_from_fetch`). Pickled to the decider child; never a path.

    `days`: int32 ordinals of every session in the slice, oldest first (history sessions first, then the run's).
    `early`: bool per session (a 13:00 close). `first`: the index of the run's first session (before it: history
    only, never traded). `symbols`: the slice's symbols. `raw[sym]`: float64 (n, 5) open, high, low, close, volume
    (adjustment=raw; NaN where the symbol has no bar). `adj[sym]`: float64 (n, 4) open, high, low, close
    (adjustment=all, as of the store's fetch day). `window`: the run's window name. `data_version`: the hash of
    exactly the files read (`EquityStore.data_version`), part of every run's identity."""

    days: np.ndarray
    early: np.ndarray
    first: int
    symbols: tuple[str, ...]
    raw: Mapping[str, np.ndarray]
    adj: Mapping[str, np.ndarray]
    window: str
    data_version: str = ""

    @property
    def n(self) -> int:
        """Sessions in the slice (history included)."""
        raise NotImplementedError("core: league/equity/store.py Bars.n")


class EquityStore:
    """Read-only access to one equity store root. `gate`: the gate's capability, or None (Train and Validation only)."""

    def __init__(self, root: str | Path, *, gate: EquityGateCapability | None = None):
        raise NotImplementedError("core: league/equity/store.py EquityStore")

    @property
    def gate(self) -> bool:
        raise NotImplementedError("core: league/equity/store.py EquityStore.gate")

    def manifest(self) -> dict[str, Any]:
        """manifest.json as written (`write_store`)."""
        raise NotImplementedError("core: league/equity/store.py EquityStore.manifest")

    def symbols(self) -> dict[str, str]:
        """{symbol: class} the store holds."""
        raise NotImplementedError("core: league/equity/store.py EquityStore.symbols")

    def sessions(self, window: str | None = None) -> list[dt.date]:
        """Every session of the calendar (of `window` only when named; a sealed window lists nothing without the
        gate's capability: StoreRefused)."""
        raise NotImplementedError("core: league/equity/store.py EquityStore.sessions")

    def bars(self, symbols: Sequence[str], window: str, *, history: int, start: dt.date | None = None,
             end: dt.date | None = None) -> Bars:
        """The slice a run reads: the window's sessions (cut to [start, end]) with `history` sessions before its first,
        never a sealed day without the capability (a history session inside a sealed window is refused too)."""
        raise NotImplementedError("core: league/equity/store.py EquityStore.bars")

    def span(self, symbols: Sequence[str], first: dt.date, last: dt.date, *, history: int) -> Bars:
        """The slice for an explicit span (the screen's Train-era segments, `config.TRAIN_ERA_SEGMENTS`): Train days
        only; StoreRefused for a span reaching outside Train."""
        raise NotImplementedError("core: league/equity/store.py EquityStore.span")

    def data_version(self, symbols: Sequence[str], days: Iterable[dt.date]) -> str:
        """A hash of exactly the files a run reads (their manifest sha256 and the calendar's), 24 hex characters."""
        raise NotImplementedError("core: league/equity/store.py EquityStore.data_version")


def nyse_sessions(start: dt.date, end: dt.date) -> list[tuple[dt.date, bool]]:
    """Every NYSE regular session from `start` to `end` inclusive, with its early-close flag. From 2022 on it is
    `ltcm.data.us_equity_session` exactly (that calendar starts in 2022: `CALENDAR_MIN_YEAR`); for 2016-2021 the same
    holiday and early-close rules computed here (no Juneteenth before 2022) plus the 2018-12-05 closure. The store's
    calendar, the synthetic store's sessions and the data job's audit (league/ops/equity_data.py) all read this one."""
    raise NotImplementedError("core: league/equity/store.py nyse_sessions")


def write_store(root: str | Path, *, calendar: Sequence[tuple[dt.date, bool]],
                series: Mapping[str, Mapping[str, Any]], classes: Mapping[str, str], fetched_through: dt.date,
                source: str, gate: bool, audit: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Write a whole store at `root` atomically (the layout above) and return its manifest. `calendar`: (session,
    early close) pairs, oldest first. `series[symbol]`: {"days": [date...], "raw_o"...: [float...], "all_o"...:
    [float...]} aligned on its own days. `gate`: write the GATE mark (the House's store only). ValueError on a series
    that is not aligned, a day outside the calendar, or a symbol without a class."""
    raise NotImplementedError("core: league/equity/store.py write_store")


__all__ = ["GATE_MARK", "STORE_DIR", "RAW_COLUMNS", "ALL_COLUMNS", "StoreRefused", "MissingData", "EquityGateCapability",
           "mint_equity_gate_capability", "window_of", "Bars", "EquityStore", "nyse_sessions", "write_store"]
