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

THE LOOK (A9 D6): the one sealed look reads `LOOK` ("look"), a span rather than a window: from `config.LOOK_FIRST`
through min(the store's last close, `config.LOOK_CAP`), the holdout's days and, after 2026-09-25, the forward's. It
opens only with the capability, as the two sealed windows do.

AS-OF ADJUSTMENT (league/equity/ctx.py `as_of`): history at decision day t is all_s x raw_t / all_t, identical
whatever day the `all` series was fetched on (the factor of every event after t cancels), so a live fetch at t and
this store agree (I6).

INTEGRITY: every file a reader opens is checked against the manifest's sha256 (MissingData on a mismatch: a store
being rewritten under a reader refuses, never mixes days), and the npz files are written byte-for-byte reproducibly
(fixed zip timestamps), so the same data always has the same sha and the same `data_version`.

THE CALENDAR (`nyse_sessions`): `ltcm.data.us_equity_session` from 2022 on; the same rules computed here for
2016-2021 (no Juneteenth before 2022, the closure of 2018-12-05). Days before 2016 are refused: the store starts with
SIP history on 2016-01-04.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import io
import json
import os
import zipfile
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

from . import EQUITY_STORE_VERSION, config

GATE_MARK = "GATE"
STORE_DIR = "equity-daily"
RAW_COLUMNS = ("raw_o", "raw_h", "raw_l", "raw_c", "raw_v")
ALL_COLUMNS = ("all_o", "all_h", "all_l", "all_c")
#: The span of the one sealed look (A9 D6): `config.LOOK_FIRST` through min(the store's last close, `config.LOOK_CAP`).
LOOK = "look"
#: The first year the calendar answers for (SIP daily history starts 2016-01-04).
FIRST_YEAR = 2016
EPOCH = dt.date(1970, 1, 1)
#: Full closures no rule produces before 2022 (`ltcm.data.SPECIAL_CLOSURES` holds the later ones).
SPECIAL_CLOSURES_BEFORE_2022 = frozenset({dt.date(2018, 12, 5)})   # the National Day of Mourning (George H. W. Bush)
_ZIP_TIME = (1980, 1, 1, 0, 0, 0)


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

    def __repr__(self) -> str:
        return f"<EquityGateCapability {self.reason!r}>"


def mint_equity_gate_capability(store_root: str | Path, reason: str) -> EquityGateCapability:
    """The gate's capability for the store at `store_root` (which must carry the `GATE` mark; `reason` is required and
    recorded). StoreRefused otherwise. Mirrors `league.gym.store.mint_gate_capability`."""
    root = Path(store_root)
    if not (root / GATE_MARK).is_file():
        raise StoreRefused(f"{root} is not the House's equity store (no {GATE_MARK} mark): only the gate opens the "
                           "holdout and forward days")
    if not str(reason or "").strip():
        raise StoreRefused("the gate names why it opens the sealed days")
    cap = object.__new__(EquityGateCapability)
    object.__setattr__(cap, "reason", str(reason).strip())
    object.__setattr__(cap, "store_root", str(root.resolve()))
    return cap


def window_of(day: dt.date) -> str:
    """"train", "validation", "holdout", "forward", or "pre" / "gap" outside them (`config.WINDOWS`)."""
    if day < config.WINDOWS["train"][0]:
        return "pre"
    for name in ("train", "validation", "holdout"):
        start, end = config.WINDOWS[name]
        if start <= day <= end:  # type: ignore[operator]
            return name
    if day >= config.WINDOWS["forward"][0]:
        return "forward"
    return "gap"


def ordinal(day: dt.date) -> int:
    """Days since 1970-01-01 (the arrays' int32 day)."""
    return (day - EPOCH).days


def from_ordinal(value: int) -> dt.date:
    return EPOCH + dt.timedelta(days=int(value))


def as_date(value: Any) -> dt.date:
    """A date from a date, a datetime (its New York day) or an ISO string's first ten characters."""
    if isinstance(value, dt.datetime):
        from ltcm.data import NEW_YORK

        return (value if value.tzinfo is None else value.astimezone(NEW_YORK)).date()
    if isinstance(value, dt.date):
        return value
    if isinstance(value, str):
        return dt.date.fromisoformat(value[:10])
    raise ValueError(f"not a day: {value!r}")


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
        return int(self.days.shape[0])

    def day(self, index: int) -> dt.date:
        """The session day at `index`."""
        return from_ordinal(int(self.days[index]))


def _read_verified(path: Path, sha: str | None, what: str) -> bytes:
    if not path.is_file():
        raise MissingData(f"the equity store has no {what} ({path.name})")
    data = path.read_bytes()
    if sha is None or hashlib.sha256(data).hexdigest() != sha:
        raise MissingData(f"the equity store's {what} does not match its manifest (the store is being rewritten, or "
                          "was changed by hand): refused rather than mixed")
    return data


def _npz_arrays(data: bytes) -> dict[str, np.ndarray]:
    with np.load(io.BytesIO(data), allow_pickle=False) as npz:
        return {name: npz[name] for name in npz.files}


class EquityStore:
    """Read-only access to one equity store root. `gate`: the gate's capability, or None (Train and Validation only)."""

    def __init__(self, root: str | Path, *, gate: EquityGateCapability | None = None):
        self.root = Path(root)
        if gate is not None:
            if not isinstance(gate, EquityGateCapability):
                raise StoreRefused("gate must be an EquityGateCapability minted on the House's store")
            if gate.store_root != str(self.root.resolve()):
                raise StoreRefused("this capability was minted for another store")
        self._gate = gate
        version_file = self.root / "VERSION"
        if not version_file.is_file():
            raise MissingData(f"no equity store at {self.root} (no VERSION file)")
        version = version_file.read_text().strip()
        if version != EQUITY_STORE_VERSION:
            raise MissingData(f"{self.root} is {version!r}; this engine reads {EQUITY_STORE_VERSION}")
        manifest_path = self.root / "manifest.json"
        if not manifest_path.is_file():
            raise MissingData(f"no manifest.json in {self.root}")
        try:
            self._manifest = json.loads(manifest_path.read_text())
        except (OSError, ValueError) as exc:
            raise MissingData(f"the equity store's manifest is unreadable: {exc}") from None
        if self._manifest.get("version") != EQUITY_STORE_VERSION or not isinstance(self._manifest.get("symbols"), dict):
            raise MissingData("the equity store's manifest is not an equity-store-v1 manifest")
        calendar = _npz_arrays(_read_verified(self.root / "calendar.npz", self._manifest.get("calendar_sha256"),
                                              "calendar"))
        self._days = np.asarray(calendar["days"], dtype=np.int32)
        self._early = np.asarray(calendar["early"], dtype=bool)
        self._dates = [from_ordinal(int(d)) for d in self._days]
        try:
            self._through = dt.date.fromisoformat(str(self._manifest["fetched_through"]))
        except (KeyError, ValueError):
            raise MissingData("the equity store's manifest names no fetched_through day") from None
        self._cache: dict[str, dict[str, np.ndarray]] = {}

    @property
    def gate(self) -> bool:
        return self._gate is not None

    @property
    def fetched_through(self) -> dt.date:
        """The last session the store's fetch covered (its last close)."""
        return self._through

    def manifest(self) -> dict[str, Any]:
        """manifest.json as written (`write_store`)."""
        return json.loads(json.dumps(self._manifest))

    def symbols(self) -> dict[str, str]:
        """{symbol: class} the store holds."""
        return {sym: str(row.get("class")) for sym, row in sorted(self._manifest["symbols"].items())}

    # ------------------------------------------------------------------ windows
    def _span(self, window: str) -> tuple[dt.date, dt.date]:
        if window == LOOK:
            return config.LOOK_FIRST, min(self._through, config.LOOK_CAP)
        if window not in config.WINDOWS:
            raise StoreRefused(f"no window {window!r}; one of {', '.join((*config.WINDOWS, LOOK))}")
        first, last = config.WINDOWS[window]
        return first, min(last, self._through) if last is not None else self._through

    def _check(self, window: str) -> None:
        if (window in config.SEALED or window == LOOK) and self._gate is None:
            raise StoreRefused(f"the {window} days open only for the gate")

    def sessions(self, window: str | None = None) -> list[dt.date]:
        """Every session of the calendar (of `window` only when named; a sealed window lists nothing without the
        gate's capability: StoreRefused)."""
        if window is None:
            return list(self._dates)
        self._check(window)
        first, last = self._span(window)
        return [d for d in self._dates if first <= d <= last]

    # ------------------------------------------------------------------ reading
    def _series(self, symbol: str) -> dict[str, np.ndarray]:
        found = self._cache.get(symbol)
        if found is None:
            row = self._manifest["symbols"].get(symbol)
            if row is None:
                raise MissingData(f"the equity store holds no {symbol}")
            found = _npz_arrays(_read_verified(self.root / "bars" / f"{symbol}.npz", row.get("sha256"),
                                               f"{symbol} bars"))
            for name in ("days", *RAW_COLUMNS, *ALL_COLUMNS):
                if name not in found:
                    raise MissingData(f"the equity store's {symbol} bars lack {name}")
            self._cache[symbol] = found
        return found

    def _slice(self, symbols: Sequence[str], run: list[dt.date], history: int, window: str) -> Bars:
        names = tuple(dict.fromkeys(str(s).strip().upper() for s in symbols))
        if not names:
            raise ValueError("a slice names at least one symbol")
        history = int(history)
        if history < 0:
            raise ValueError("history is a count of sessions, at least 0")
        before: list[dt.date] = []
        if run:
            i = self._dates.index(run[0])
            before = self._dates[max(0, i - history):i]
            for day in before:
                if window_of(day) in config.SEALED and self._gate is None:
                    raise StoreRefused(f"a history session ({window_of(day)}) opens only for the gate")
        days = before + run
        ordinals = np.array([ordinal(d) for d in days], dtype=np.int32)
        index = {d: i for i, d in enumerate(self._dates)}
        early = np.array([bool(self._early[index[d]]) for d in days], dtype=bool)
        raw: dict[str, np.ndarray] = {}
        adj: dict[str, np.ndarray] = {}
        for sym in names:
            series = self._series(sym)
            own = np.asarray(series["days"], dtype=np.int32)
            at = np.searchsorted(own, ordinals)
            hit = (at < own.shape[0]) & (own[np.minimum(at, max(own.shape[0] - 1, 0))] == ordinals) if own.size else \
                np.zeros(ordinals.shape[0], dtype=bool)
            r = np.full((len(days), 5), np.nan)
            a = np.full((len(days), 4), np.nan)
            for k, name in enumerate(RAW_COLUMNS):
                r[hit, k] = np.asarray(series[name], dtype=np.float64)[at[hit]]
            for k, name in enumerate(ALL_COLUMNS):
                a[hit, k] = np.asarray(series[name], dtype=np.float64)[at[hit]]
            r.setflags(write=False)
            a.setflags(write=False)
            raw[sym], adj[sym] = r, a
        ordinals.setflags(write=False)
        early.setflags(write=False)
        return Bars(days=ordinals, early=early, first=len(before), symbols=names, raw=raw, adj=adj, window=window,
                    data_version=self.data_version(names, days))

    def bars(self, symbols: Sequence[str], window: str, *, history: int, start: dt.date | None = None,
             end: dt.date | None = None) -> Bars:
        """The slice a run reads: the window's sessions (cut to [start, end]) with `history` sessions before its first,
        never a sealed day without the capability (a history session inside a sealed window is refused too). `window`
        may also be `LOOK` (A9 D6), the one sealed look's span."""
        self._check(window)
        first, last = self._span(window)
        run = [d for d in self._dates
               if first <= d <= last and (start is None or d >= start) and (end is None or d <= end)]
        return self._slice(symbols, run, history, window)

    def span(self, symbols: Sequence[str], first: dt.date, last: dt.date, *, history: int) -> Bars:
        """The slice for an explicit span (the screen's Train-era segments, `config.TRAIN_ERA_SEGMENTS`): Train days
        only; StoreRefused for a span reaching outside Train."""
        lo, hi = config.WINDOWS["train"]
        if not (lo <= first <= last <= hi):  # type: ignore[operator]
            raise StoreRefused(f"a span is Train days only ({lo}..{hi}); {first}..{last} reaches outside")
        run = [d for d in self._dates if first <= d <= last and d <= self._through]
        return self._slice(symbols, run, history, "train")

    def data_version(self, symbols: Sequence[str], days: Iterable[dt.date]) -> str:
        """A hash of exactly the files a run reads (their manifest sha256 and the calendar's), 24 hex characters."""
        days = list(days)
        digest = hashlib.sha256(EQUITY_STORE_VERSION.encode())
        digest.update(b"calendar=" + str(self._manifest.get("calendar_sha256")).encode())
        for sym in sorted(set(str(s).strip().upper() for s in symbols)):
            row = self._manifest["symbols"].get(sym) or {}
            digest.update(f"{sym}={row.get('sha256') or 'absent'};".encode())
        span = f"{days[0].isoformat()}..{days[-1].isoformat()}" if days else "none"
        digest.update(f"days={len(days)}:{span}".encode())
        return digest.hexdigest()[:24]


# --------------------------------------------------------------------------- the NYSE calendar
def _year_before_2022(year: int) -> list[tuple[dt.date, bool]]:
    """`ltcm.data`'s holiday and early-close rules as they stood before 2022 (no Juneteenth), plus the closure of
    2018-12-05: the same helpers (`easter`, `nth_weekday`, `observed`), so the two calendars cannot drift apart."""
    from ltcm.data import easter, nth_weekday, observed

    holidays: set[dt.date] = set()

    def add(day: dt.date) -> None:
        if day.weekday() < 5 and day.year == year:
            holidays.add(day)

    add(observed(dt.date(year, 1, 1)))      # a Saturday New Year's Day is not observed on the Friday before
    add(nth_weekday(year, 1, 0, 3))
    add(nth_weekday(year, 2, 0, 3))
    add(easter(year) - dt.timedelta(days=2))
    add(nth_weekday(year, 5, 0, -1))
    add(observed(dt.date(year, 7, 4)))
    add(nth_weekday(year, 9, 0, 1))
    add(nth_weekday(year, 11, 3, 4))
    add(observed(dt.date(year, 12, 25)))
    holidays.update(d for d in SPECIAL_CLOSURES_BEFORE_2022 if d.year == year)
    early: set[dt.date] = set()

    def half(day: dt.date) -> None:
        if day.weekday() < 5 and day.year == year and day not in holidays:
            early.add(day)

    half(nth_weekday(year, 11, 3, 4) + dt.timedelta(days=1))
    if dt.date(year, 7, 4).weekday() < 5:
        half(dt.date(year, 7, 3))
    if dt.date(year, 12, 25).weekday() < 5:
        half(dt.date(year, 12, 24))
    out = []
    day = dt.date(year, 1, 1)
    while day.year == year:
        if day.weekday() < 5 and day not in holidays:
            out.append((day, day in early))
        day += dt.timedelta(days=1)
    return out


@lru_cache(maxsize=64)
def _year(year: int) -> tuple[tuple[dt.date, bool], ...]:
    from ltcm.data import CALENDAR_MIN_YEAR, us_equity_session

    if year < FIRST_YEAR:
        raise ValueError(f"the equity calendar starts in {FIRST_YEAR} (SIP daily history); {year} is before it")
    if year < CALENDAR_MIN_YEAR:
        return tuple(_year_before_2022(year))
    out = []
    day = dt.date(year, 1, 1)
    while day.year == year:
        session = us_equity_session(day)
        if session is not None:
            out.append((day, bool(session.early_close)))
        day += dt.timedelta(days=1)
    return tuple(out)


def nyse_sessions(start: dt.date, end: dt.date) -> list[tuple[dt.date, bool]]:
    """Every NYSE regular session from `start` to `end` inclusive, with its early-close flag. From 2022 on it is
    `ltcm.data.us_equity_session` exactly (that calendar starts in 2022: `CALENDAR_MIN_YEAR`); for 2016-2021 the same
    holiday and early-close rules computed here (no Juneteenth before 2022) plus the 2018-12-05 closure. The store's
    calendar, the synthetic store's sessions and the data job's audit (league/ops/equity_data.py) all read this one."""
    start, end = as_date(start), as_date(end)
    out: list[tuple[dt.date, bool]] = []
    for year in range(start.year, end.year + 1):
        out.extend(row for row in _year(year) if start <= row[0] <= end)
    return out


# --------------------------------------------------------------------------- writing
def _npz_bytes(arrays: Mapping[str, np.ndarray]) -> bytes:
    """An .npz archive of `arrays` that is the same bytes for the same arrays (fixed timestamps, no compression), so a
    file's sha256 names its content."""
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, array in arrays.items():
            body = io.BytesIO()
            np.lib.format.write_array(body, np.ascontiguousarray(array), allow_pickle=False)
            info = zipfile.ZipInfo(f"{name}.npy", date_time=_ZIP_TIME)
            info.external_attr = 0o644 << 16
            archive.writestr(info, body.getvalue())
    return out.getvalue()


def _atomic_write(path: Path, data: bytes) -> None:
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with open(tmp, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def write_store(root: str | Path, *, calendar: Sequence[tuple[dt.date, bool]],
                series: Mapping[str, Mapping[str, Any]], classes: Mapping[str, str], fetched_through: dt.date,
                source: str, gate: bool, audit: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Write a whole store at `root` atomically (the layout above) and return its manifest. `calendar`: (session,
    early close) pairs, oldest first. `series[symbol]`: {"days": [date...], "raw_o"...: [float...], "all_o"...:
    [float...]} aligned on its own days. `gate`: write the GATE mark (the House's store only). ValueError on a series
    that is not aligned, a day outside the calendar, or a symbol without a class."""
    root = Path(root)
    through = as_date(fetched_through)
    cal_days = [as_date(d) for d, _ in calendar]
    if any(b <= a for a, b in zip(cal_days, cal_days[1:])):
        raise ValueError("the calendar's sessions are strictly increasing")
    in_calendar = set(cal_days)
    upper_classes = {str(k).strip().upper(): v for k, v in classes.items()}
    prepared: dict[str, dict[str, np.ndarray]] = {}
    for symbol in sorted(series):
        sym = str(symbol).strip().upper()
        klass = upper_classes.get(sym)
        if klass not in config.CLASSES:
            raise ValueError(f"{sym} has no class (one of {', '.join(config.CLASSES)})")
        row = series[symbol]
        days = [as_date(d) for d in row.get("days") or []]
        if any(b <= a for a, b in zip(days, days[1:])):
            raise ValueError(f"{sym}'s days are strictly increasing")
        outside = [d for d in days if d not in in_calendar or d > through]
        if outside:
            raise ValueError(f"{sym} has a bar on {outside[0]}, not a calendar session through {through}")
        arrays = {"days": np.array([ordinal(d) for d in days], dtype=np.int32)}
        for name in (*RAW_COLUMNS, *ALL_COLUMNS):
            values = np.asarray(row.get(name, ()), dtype=np.float64)
            if values.shape != (len(days),):
                raise ValueError(f"{sym}'s {name} is not aligned with its days")
            arrays[name] = values
        prepared[sym] = arrays
    root.mkdir(parents=True, exist_ok=True)
    (root / "bars").mkdir(exist_ok=True)
    symbols: dict[str, Any] = {}
    for sym, arrays in prepared.items():
        data = _npz_bytes(arrays)
        _atomic_write(root / "bars" / f"{sym}.npz", data)
        days = arrays["days"]
        symbols[sym] = {"class": upper_classes[sym], "sha256": hashlib.sha256(data).hexdigest(),
                        "first": from_ordinal(int(days[0])).isoformat() if days.size else None,
                        "last": from_ordinal(int(days[-1])).isoformat() if days.size else None, "rows": int(days.size)}
    cal = _npz_bytes({"days": np.array([ordinal(d) for d in cal_days], dtype=np.int32),
                      "early": np.array([bool(e) for _, e in calendar], dtype=bool)})
    _atomic_write(root / "calendar.npz", cal)
    _atomic_write(root / "VERSION", (EQUITY_STORE_VERSION + "\n").encode())
    if gate:
        _atomic_write(root / GATE_MARK, b"the House's equity store: the gate may open its sealed days\n")
    else:
        (root / GATE_MARK).unlink(missing_ok=True)
    manifest = {"version": EQUITY_STORE_VERSION, "fetched_through": through.isoformat(), "symbols": symbols,
                "calendar_sha256": hashlib.sha256(cal).hexdigest(), "source": str(source),
                "audit": None if audit is None else json.loads(json.dumps(audit, default=str))}
    _atomic_write(root / "manifest.json", json.dumps(manifest, sort_keys=True, indent=1).encode())
    for stale in (root / "bars").glob("*.npz"):
        if stale.stem not in symbols:
            stale.unlink(missing_ok=True)
    return manifest


__all__ = ["GATE_MARK", "STORE_DIR", "RAW_COLUMNS", "ALL_COLUMNS", "LOOK", "FIRST_YEAR", "StoreRefused", "MissingData",
           "EquityGateCapability", "mint_equity_gate_capability", "window_of", "ordinal", "from_ordinal", "as_date",
           "Bars", "EquityStore", "nyse_sessions", "write_store"]
