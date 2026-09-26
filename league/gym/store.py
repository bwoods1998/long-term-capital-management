"""The store-v1 reader: one day's chain for a root, loaded once into numpy arrays.

The layout is fixed by the main session (the run's briefs, "The Gym store, v1"): per-day Parquet
under `<root>/nbbo/<ROOT>/<YYYY-MM-DD>.parquet` (one-minute NBBO), `underlying/`, `oi/`,
`trade_quote/`, plus `calendar.parquet`, `expiries.parquet`, `manifest.parquet` and `VERSION`.
Dates appear only in paths and in the manifest; the engine turns them into day ordinals and days to
expiry, and a program never sees one.

THE WINDOWS. Every date belongs to one window: train 2022-01-03..2024-12-31, validation
2025-01-02..2025-12-31, holdout 2026-01-02..2026-09-25 (the last full trading day before T0), forward
every trading day after that. A holdout or forward day opens only for a `Store` built with a
`GateCapability`, and one is minted only on a store that carries the gate image's `GATE` mark (the
Gym image has neither the mark nor the days). It is an object the gate's code holds, not a flag: a
program runs inside `decide(ctx)`, imports only numpy and math, and never reaches the store at all.

A DayChain is the whole day of one root as dense [minute, contract] grids (NaN where there was no
quote that minute): minute index 0 is the open (09:30, 570) and the last is the close (16:00, 960;
13:00 on a half day). A row is the NBBO in force AT that minute's start, so a decision at minute m
sees row m and its order meets row m + 1 (`engine.py`).
"""

from __future__ import annotations

import datetime as dt
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from . import STORE_VERSION

EPOCH = dt.date(1970, 1, 1)
WINDOWS: dict[str, tuple[dt.date, dt.date | None]] = {
    "train": (dt.date(2022, 1, 3), dt.date(2024, 12, 31)),
    "validation": (dt.date(2025, 1, 2), dt.date(2025, 12, 31)),
    "holdout": (dt.date(2026, 1, 2), dt.date(2026, 9, 25)),
    "forward": (dt.date(2026, 9, 26), None),
}
#: Windows only the gate opens.
SEALED = ("holdout", "forward")
GATE_MARK = "GATE"
KINDS = ("nbbo", "underlying", "oi", "trade_quote")


class StoreRefused(PermissionError):
    """A sealed day was asked for without the gate's capability, or a window was misnamed."""


class MissingData(FileNotFoundError):
    """The store lacks what a run needs (the message names it): the box is missing data."""


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


class GateCapability:
    """Proof that the caller is the gate. It cannot be constructed; `mint_gate_capability` mints one
    on the gate image only. Holding one is what lets a `Store` open holdout and forward days."""

    __slots__ = ("reason", "store_root")

    def __init__(self, *args: Any, **kwargs: Any):
        raise TypeError("a GateCapability is minted by mint_gate_capability() on the gate image, never constructed")

    def __repr__(self) -> str:
        return f"<GateCapability {self.reason!r}>"


def mint_gate_capability(store_root: str | Path, reason: str) -> GateCapability:
    """The gate's capability for the store at `store_root`, which must carry the gate image's `GATE`
    mark (the image script writes it; the Gym image never has it). `reason` is recorded with it."""
    root = Path(store_root)
    if not (root / GATE_MARK).is_file():
        raise StoreRefused(f"{root} is not the gate's store (no {GATE_MARK} mark): a Gym box never opens the holdout or forward days")
    if not str(reason or "").strip():
        raise StoreRefused("the gate names why it opens the sealed days")
    cap = object.__new__(GateCapability)
    object.__setattr__(cap, "reason", str(reason).strip())
    object.__setattr__(cap, "store_root", str(root.resolve()))
    return cap


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


def _date_ordinals(column: pa.ChunkedArray | pa.Array) -> np.ndarray:
    return pc.cast(column, pa.int32()).to_numpy(zero_copy_only=False).astype(np.int32) if pa.types.is_date32(column.type) \
        else pc.cast(pc.cast(column, pa.date32()), pa.int32()).to_numpy(zero_copy_only=False).astype(np.int32)


def _is_call(column: pa.ChunkedArray | pa.Array) -> np.ndarray:
    if pa.types.is_dictionary(column.type):
        column = pc.cast(column, pa.string())
    return pc.equal(pc.utf8_upper(column), "C").to_numpy(zero_copy_only=False).astype(bool)


def _numpy(table: pa.Table, name: str, dtype: Any) -> np.ndarray:
    return table.column(name).to_numpy(zero_copy_only=False).astype(dtype, copy=False)


class Store:
    """Read-only access to one store root. `gate` is the gate's capability or None (a Gym box)."""

    def __init__(self, root: str | Path, *, gate: GateCapability | None = None):
        self.root = Path(root)
        if gate is not None and not isinstance(gate, GateCapability):
            raise StoreRefused("gate must be a GateCapability minted on the gate image")
        self._gate = gate
        version_file = self.root / "VERSION"
        if not version_file.is_file():
            raise MissingData(f"no store at {self.root} (no VERSION file)")
        version = version_file.read_text().strip()
        if version != STORE_VERSION:
            raise MissingData(f"{self.root} is {version!r}; this engine reads {STORE_VERSION}")
        self._calendar = self._read_calendar()
        self._trading = sorted(self._calendar)
        self._ordinals = np.array([ordinal(d) for d in self._trading], dtype=np.int64)
        self._manifest: dict[tuple[str, str, int], str] | None = None

    # ------------------------------------------------------------------ calendar and windows
    def _read_calendar(self) -> dict[dt.date, tuple[int, int]]:
        path = self.root / "calendar.parquet"
        if not path.is_file():
            raise MissingData(f"no calendar.parquet in {self.root}")
        table = pq.read_table(path)
        days = _date_ordinals(table.column("date"))
        opens = _numpy(table, "open_min", np.int32)
        closes = _numpy(table, "close_min", np.int32)
        return {from_ordinal(int(d)): (int(o), int(c)) for d, o, c in zip(days, opens, closes)}

    @property
    def gate(self) -> bool:
        return self._gate is not None

    def session(self, day: dt.date) -> tuple[int, int]:
        """(open_min, close_min) of a trading day."""
        found = self._calendar.get(day)
        if found is None:
            raise MissingData(f"{day} is not a trading day in this store's calendar")
        return found

    def trading_days(self) -> list[dt.date]:
        """Every trading day the calendar lists (dates only: no data is opened)."""
        return list(self._trading)

    def next_trading_day(self, day: dt.date) -> dt.date | None:
        i = int(np.searchsorted(self._ordinals, ordinal(day), side="right"))
        return self._trading[i] if i < len(self._trading) else None

    def check(self, day: dt.date) -> None:
        """Refuse a sealed day unless this store holds the gate's capability."""
        window = window_of(day)
        if window in SEALED and self._gate is None:
            raise StoreRefused(f"{window} days open only for the gate")

    def path(self, kind: str, root: str, day: dt.date) -> Path:
        if kind not in KINDS:
            raise ValueError(f"no such kind {kind!r}")
        return self.root / kind / root.upper() / f"{day.isoformat()}.parquet"

    def has(self, kind: str, root: str, day: dt.date) -> bool:
        return self.path(kind, root, day).is_file()

    def days(self, window: str, roots: Sequence[str], *, start: dt.date | None = None, end: dt.date | None = None,
             kind: str = "nbbo") -> list[dt.date]:
        """The window's trading days (optionally cut to [start, end]) on which every one of `roots`
        has a `kind` file. A sealed window lists nothing without the gate's capability."""
        if window not in WINDOWS:
            raise StoreRefused(f"no window {window!r}; one of {', '.join(WINDOWS)}")
        if window in SEALED and self._gate is None:
            raise StoreRefused(f"the {window} window opens only for the gate")
        out = []
        for day in self._trading:
            if window_of(day) != window or (start and day < start) or (end and day > end):
                continue
            if all(self.has(kind, r, day) for r in roots):
                out.append(day)
        return out

    def history_days(self, before: dt.date, count: int) -> list[dt.date]:
        """Up to `count` trading days strictly before `before` (for the underlying's history), never a
        sealed day this store may not open."""
        out = []
        for day in reversed(self._trading):
            if day >= before:
                continue
            if window_of(day) in SEALED and self._gate is None:
                continue
            out.append(day)
            if len(out) >= count:
                break
        return list(reversed(out))

    # ------------------------------------------------------------------ versions
    def manifest(self) -> dict[tuple[str, str, int], str]:
        """{(kind, root, day ordinal): sha256} from manifest.parquet ({} when there is none)."""
        if self._manifest is None:
            self._manifest = {}
            path = self.root / "manifest.parquet"
            if path.is_file():
                table = pq.read_table(path, columns=["kind", "root", "date", "sha256"])
                kinds = table.column("kind").to_pylist()
                roots = table.column("root").to_pylist()
                days = _date_ordinals(table.column("date"))
                shas = table.column("sha256").to_pylist()
                self._manifest = {(k, r, int(d)): s for k, r, d, s in zip(kinds, roots, days, shas)}
        return self._manifest

    def data_version(self, roots: Sequence[str], days: Iterable[dt.date]) -> str:
        """A hash of exactly the files a run reads (their manifest sha256, or their size where the
        manifest has none): part of every run's identity."""
        manifest = self.manifest()
        digest = hashlib.sha256(STORE_VERSION.encode())
        for day in days:
            for root in sorted(set(r.upper() for r in roots)):
                for kind in ("nbbo", "underlying", "oi"):
                    path = self.path(kind, root, day)
                    sha = manifest.get((kind, root, ordinal(day)))
                    if sha is None:
                        sha = f"size:{path.stat().st_size}" if path.is_file() else "absent"
                    digest.update(f"{kind}/{root}/{day.isoformat()}={sha};".encode())
        return digest.hexdigest()[:24]

    # ------------------------------------------------------------------ reading
    def underlying(self, root: str, day: dt.date) -> Underlying:
        """One day of the underlying, on the session's minute grid."""
        self.check(day)
        path = self.path("underlying", root, day)
        if not path.is_file():
            raise MissingData(f"no underlying for {root} on {day}")
        open_min, close_min = self.session(day)
        m = close_min - open_min + 1
        table = pq.read_table(path, memory_map=True)
        mi = _numpy(table, "minute", np.int32) - open_min
        keep = (mi >= 0) & (mi < m)
        mi = mi[keep]

        def grid(name: str, dtype: Any = np.float64) -> np.ndarray | None:
            if name not in table.column_names:
                return None
            values = _numpy(table, name, np.float64)[keep]
            out = np.full(m, np.nan)
            out[mi] = values
            return out.astype(dtype) if dtype is not np.float64 else out

        price = grid("price")
        if price is None:
            raise MissingData(f"the underlying file for {root} on {day} has no price column")
        price[~(price > 0)] = np.nan
        # A missing minute holds the price in force before it (never a later one).
        valid = ~np.isnan(price)
        if valid.any() and not valid.all():
            idx = np.where(valid, np.arange(m), -1)
            np.maximum.accumulate(idx, out=idx)
            price = np.where(idx >= 0, price[np.maximum(idx, 0)], np.nan)
        return Underlying(price=price, open=grid("open"), high=grid("high"), low=grid("low"), close=grid("close"),
                          volume=grid("volume"))

    def chain(self, root: str, day: dt.date) -> DayChain:
        """One root's day of one-minute NBBO as [minute, contract] grids, with the underlying and OI."""
        self.check(day)
        root = root.upper()
        path = self.path("nbbo", root, day)
        if not path.is_file():
            raise MissingData(f"no NBBO for {root} on {day}")
        open_min, close_min = self.session(day)
        m = close_min - open_min + 1
        table = pq.read_table(path, memory_map=True)
        exp = _date_ordinals(table.column("expiration"))
        strike = _numpy(table, "strike", np.float64)
        calls = _is_call(table.column("right"))
        minute = _numpy(table, "minute", np.int32)
        bid = _numpy(table, "bid", np.float32)
        ask = _numpy(table, "ask", np.float32)
        bsz = _numpy(table, "bid_size", np.int32)
        asz = _numpy(table, "ask_size", np.int32)
        key = contract_key(exp, strike, calls)
        n = key.shape[0]
        if n and np.any(key[1:] < key[:-1]):
            order = np.lexsort((minute, key))
            exp, strike, calls, minute, bid, ask, bsz, asz, key = (a[order] for a in (exp, strike, calls, minute, bid, ask, bsz, asz, key))
        if n:
            new = np.empty(n, dtype=bool)
            new[0] = True
            np.not_equal(key[1:], key[:-1], out=new[1:])
            cid = np.cumsum(new) - 1
            starts = np.flatnonzero(new)
        else:
            cid = np.zeros(0, dtype=np.int64)
            starts = np.zeros(0, dtype=np.int64)
        c = int(starts.shape[0])
        mi = minute - open_min
        keep = (mi >= 0) & (mi < m) & (ask > 0) & (bid >= 0) & (ask >= bid) & np.isfinite(bid) & np.isfinite(ask)
        grid_bid = np.full((m, c), np.nan, dtype=np.float32)
        grid_ask = np.full((m, c), np.nan, dtype=np.float32)
        grid_bsz = np.zeros((m, c), dtype=np.int32)
        grid_asz = np.zeros((m, c), dtype=np.int32)
        rows, cols = mi[keep], cid[keep]
        grid_bid[rows, cols] = bid[keep]
        grid_ask[rows, cols] = ask[keep]
        grid_bsz[rows, cols] = bsz[keep]
        grid_asz[rows, cols] = asz[keep]
        # Quotes are whole cents (sub-penny at most): rounded once here, the float32 file's noise gone.
        grid_bid = np.round(grid_bid.astype(np.float64), 4)
        grid_ask = np.round(grid_ask.astype(np.float64), 4)
        expiration = exp[starts].astype(np.int32)
        chain = DayChain(
            root=root, day=day, open_min=open_min, close_min=close_min,
            expiration=expiration, dte=(expiration - ordinal(day)).astype(np.int16), strike=strike[starts].copy(),
            is_call=calls[starts].copy(), bid=grid_bid, ask=grid_ask, bid_size=grid_bsz, ask_size=grid_asz,
            oi=np.zeros(c, dtype=np.int64), underlying=self.underlying(root, day), key=key[starts].copy(),
        )
        oi_path = self.path("oi", root, day)
        if oi_path.is_file() and c:
            oi = pq.read_table(oi_path)
            okey = contract_key(_date_ordinals(oi.column("expiration")), _numpy(oi, "strike", np.float64), _is_call(oi.column("right")))
            idx = chain.index_of(okey)
            hit = idx >= 0
            chain.oi[idx[hit]] = _numpy(oi, "open_interest", np.int64)[hit]
        return chain

    def trade_quote(self, root: str, day: dt.date) -> pa.Table:
        """The trade prints with the NBBO at each (fill calibration). Train days only, whoever asks."""
        if window_of(day) != "train":
            raise StoreRefused("trade_quote samples are read on Train days only (calibration never sees a later window)")
        path = self.path("trade_quote", root, day)
        if not path.is_file():
            raise MissingData(f"no trade_quote for {root} on {day}")
        return pq.read_table(path, memory_map=True)


def describe(store: Store, window: str, roots: Sequence[str]) -> dict[str, Any]:
    """What a box holds for a window: days per root and kind (the driver's data check)."""
    out: dict[str, Any] = {"store": str(store.root), "window": window, "gate": store.gate, "roots": {}}
    for root in roots:
        row = {}
        for kind in ("nbbo", "underlying", "oi"):
            row[kind] = len(store.days(window, [root], kind=kind))
        out["roots"][root.upper()] = row
    return out


__all__ = ["Store", "DayChain", "Underlying", "GateCapability", "mint_gate_capability", "StoreRefused", "MissingData",
           "WINDOWS", "SEALED", "window_of", "ordinal", "from_ordinal", "contract_key", "describe"]
