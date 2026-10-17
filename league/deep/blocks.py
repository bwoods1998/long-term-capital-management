"""The deep store: per-symbol blocks of raw daily bars and their events, open and sealed, and the one reader.

Owner: R1. The writer is league/ops/equity_deep.py (the House's data job, from the gateway's Tiingo route), through
`write_store` here; tests write synthetic stores through the same function. NOTHING OF THIS STORE IS EVER COMMITTED
OR LEAVES THE HOUSE (Tiingo's licence: internal use only; a public repository).

LAYOUT (`<state>/equity-deep/`, 0700):

    VERSION                     "equity-deep-v1"
    manifest.json               {"version", "spans": {span: {SYMBOL: {"sha256", "rows", "first", "last"}}},
                                 "audit": the data job's verdicts and counts, "source", "written_at"}: counts, days and
                                 verdicts only, never a price
    open/history/<SYM>.npz      1999-01-04..2001-04-06 (look-back only)
    open/traind/<SYM>.npz       2009-01-02..2015-12-31 (2009 look-back + TRAIN-D)
    sealed/                     0700, carries the DEEP_GATE mark
    sealed/dval/<SYM>.npz       2001-04-09..2008-12-31 (THE DEEP KEY)
    sealed/.looks/deep-*/       a look's temporary stores (`looks_dir`), removed by the look, swept after a kill
    ledger.json, report.json    league/deep/gate.py's and report.py's (0600)

A BLOCK (`block_bytes`) is a deflated zip of numpy arrays with fixed timestamps (the same data, the same sha): days
(int32 ordinals since 1970-01-01, the symbol's own sessions, ascending), open, high, low, close, volume (raw, as printed
that day), div (divCash, dollars a share on the ex-day) and split (splitFactor on the ex-day, 2.0 for a 2-for-1). The
vendor's adjusted columns are never held: an adjusted series is adjusted as of its fetch day and carries every later
event (2025-2026 distributions among them). `as_of_closes` and league/deep/relabel.py rebuild `all` from the events.

THE SEAL. `DeepStore.block` opens a sealed span only for a `gate.DeepGateCapability` minted on this store's root;
every file read is checked against the manifest's sha256 (a store being rewritten refuses, never mixes).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import io
import json
import os
import shutil
import zipfile
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from . import DEEP_STORE_VERSION, config

COLUMNS = ("open", "high", "low", "close", "volume", "div", "split")
#: The vendor's field for each column (the gateway's answer rows).
VENDOR = {"open": "open", "high": "high", "low": "low", "close": "close", "volume": "volume", "div": "divCash",
          "split": "splitFactor"}
_ZIP_TIME = (1980, 1, 1, 0, 0, 0)
_EPOCH = dt.date(1970, 1, 1)
#: `all` is rounded to this many decimals (as league/equity/synth.py writes it).
ALL_PLACES = 4


class DeepRefused(PermissionError):
    """A sealed span was asked for without the deep gate's capability, or a capability of another store."""


class DeepMissing(FileNotFoundError):
    """The deep store lacks what was asked for, or a file does not match its manifest."""


def ordinal(day: dt.date) -> int:
    return (day - _EPOCH).days


def from_ordinal(value: int) -> dt.date:
    return _EPOCH + dt.timedelta(days=int(value))


# ----------------------------------------------------------------------------------------------------------- a block
def block_bytes(days: Sequence[dt.date], columns: Mapping[str, Sequence[float]]) -> bytes:
    """One block's bytes (deflated zip, fixed timestamps). ValueError for days that do not ascend, a missing column or
    one not aligned with the days, or a value that is not finite (a missing figure is no row)."""
    days = list(days)
    if any(b <= a for a, b in zip(days, days[1:])):
        raise ValueError("a block's days ascend strictly")
    arrays = {"days": np.array([ordinal(d) for d in days], dtype=np.int32)}
    for name in COLUMNS:
        if name not in columns:
            raise ValueError(f"a block needs its {name} column")
        values = np.asarray(columns[name], dtype=np.float64)
        if values.shape != (len(days),):
            raise ValueError(f"the {name} column is not aligned with the days")
        if not np.isfinite(values).all():
            raise ValueError(f"the {name} column holds a value that is not finite")
        arrays[name] = values
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, array in arrays.items():
            body = io.BytesIO()
            np.lib.format.write_array(body, np.ascontiguousarray(array), allow_pickle=False)
            info = zipfile.ZipInfo(f"{name}.npy", date_time=_ZIP_TIME)
            info.external_attr = 0o600 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, body.getvalue())
    return out.getvalue()


def read_block(data: bytes) -> dict[str, np.ndarray]:
    """A block's arrays (DeepMissing when one is missing)."""
    with np.load(io.BytesIO(data), allow_pickle=False) as npz:
        arrays = {name: npz[name] for name in npz.files}
    for name in ("days", *COLUMNS):
        if name not in arrays:
            raise DeepMissing(f"a deep block lacks its {name} array")
    return arrays


def rows_to_columns(rows: Sequence[Mapping[str, Any]]) -> tuple[list[dt.date], dict[str, list[float]]]:
    """(days, columns) of the gateway's answer rows ({date, open, high, low, close, volume, divCash, splitFactor}).
    ValueError for a row without a day or a figure, a figure that is not a finite number, or days that do not ascend
    (an empty answer is no rows: ([], {...}))."""
    days: list[dt.date] = []
    cols: dict[str, list[float]] = {name: [] for name in COLUMNS}
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("an answer row is an object")
        day = dt.date.fromisoformat(str(row.get("date", ""))[:10])
        if days and day <= days[-1]:
            raise ValueError("the answer's days do not ascend")
        days.append(day)
        for name, field in VENDOR.items():
            value = row.get(field)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not np.isfinite(float(value)):
                raise ValueError(f"the {field} of {day} is not a number")
            cols[name].append(float(value))
    return days, cols


def factors(close: np.ndarray, div: np.ndarray, split: np.ndarray) -> np.ndarray:
    """THE ADJUSTMENT FACTOR as of the last row: every price before an event's ex-day is multiplied by (1 - dividend /
    the previous raw close) / split factor (league/equity/synth.py's construction; the engine reads the same step back
    as a split and a dividend: league/equity/engine.py `_corporate_actions`)."""
    close, div, split = (np.asarray(x, dtype=np.float64) for x in (close, div, split))
    n = close.shape[0]
    out = np.ones(n)
    step = 1.0
    for i in range(n - 1, 0, -1):
        if div[i] or split[i] != 1.0:
            step *= (1.0 - div[i] / close[i - 1]) / split[i]
        out[i - 1] = step
    return out


def adjusted(arrays: Mapping[str, np.ndarray]) -> dict[str, np.ndarray]:
    """adjustment=all open, high, low, close as of the arrays' last row, rounded to `ALL_PLACES` decimals."""
    f = factors(arrays["close"], arrays["div"], arrays["split"])
    return {name: np.round(np.asarray(arrays[name], dtype=np.float64) * f, ALL_PLACES)
            for name in ("open", "high", "low", "close")}


def concat(parts: Sequence[Mapping[str, np.ndarray]]) -> dict[str, np.ndarray]:
    """Blocks of one symbol joined in order (days ascend across them; a day held twice is a ValueError)."""
    if not parts:
        raise ValueError("no block to join")
    out = {name: np.concatenate([np.asarray(p[name]) for p in parts]) for name in ("days", *COLUMNS)}
    days = out["days"]
    if days.size > 1 and not (np.diff(days) > 0).all():
        raise ValueError("the joined blocks' days do not ascend")
    return out


# ----------------------------------------------------------------------------------------------------------- the store
def _span_dir(span: str) -> Path:
    if span in config.OPEN_SPANS:
        return Path(config.OPEN_DIR) / span
    if span in config.SEALED_SPANS:
        return Path(config.SEALED_DIR) / span
    raise ValueError(f"no span {span!r}; one of {', '.join(config.SPANS)}")


def _atomic(path: Path, data: bytes, mode: int = 0o600) -> None:
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def write_store(root: str | Path, blocks: Mapping[str, Mapping[str, bytes]], *, audit: Mapping[str, Any],
                source: str, written_at: str) -> dict[str, Any]:
    """Write the deep store's data at `root` (`<state>/equity-deep`) and return its manifest. `blocks[span][SYMBOL]`:
    `block_bytes`. The open and sealed trees are written beside the old ones and swapped in, the manifest last, so a
    reader never sees a half-written store (it refuses one: the manifest's sha256 of every file). `sealed/` is 0700
    and carries the `DEEP_GATE` mark; every file 0600. ValueError for an unknown span. The ledger and the report are
    left alone."""
    root = Path(root)
    for span in blocks:
        _span_dir(span)
    root.mkdir(parents=True, exist_ok=True)
    os.chmod(root, 0o700)
    tag = f".new-{os.getpid()}"
    spans: dict[str, dict[str, Any]] = {}
    fresh = {top: root / f"{top}{tag}" for top in (config.OPEN_DIR, config.SEALED_DIR)}
    for path in fresh.values():
        shutil.rmtree(path, ignore_errors=True)
        path.mkdir(mode=0o700)
    _atomic(fresh[config.SEALED_DIR] / config.GATE_MARK, b"the House's sealed deep era: only the deep gate opens it\n")
    for span, by_symbol in sorted(blocks.items()):
        top, name = _span_dir(span).parts
        folder = fresh[top] / name
        folder.mkdir(mode=0o700)
        spans[span] = {}
        for sym, data in sorted(by_symbol.items()):
            arrays = read_block(data)
            _atomic(folder / f"{sym}.npz", data)
            days = arrays["days"]
            spans[span][sym] = {"sha256": hashlib.sha256(data).hexdigest(), "rows": int(days.size),
                                "first": from_ordinal(int(days[0])).isoformat() if days.size else None,
                                "last": from_ordinal(int(days[-1])).isoformat() if days.size else None}
    for top, path in fresh.items():
        old = root / f"{top}.old{tag}"
        if (root / top).exists():
            os.replace(root / top, old)
        os.replace(path, root / top)
        shutil.rmtree(old, ignore_errors=True)
    os.chmod(root / config.SEALED_DIR, 0o700)
    _atomic(root / "VERSION", (DEEP_STORE_VERSION + "\n").encode())
    manifest = {"version": DEEP_STORE_VERSION, "spans": spans, "audit": json.loads(json.dumps(audit)),
                "source": str(source), "written_at": str(written_at)}
    _atomic(root / config.MANIFEST, json.dumps(manifest, sort_keys=True, indent=1).encode())
    return manifest


class DeepStore:
    """Read access to the deep store at `root`. `gate`: a `gate.DeepGateCapability` minted on this root, or None (the
    open spans only)."""

    def __init__(self, root: str | Path, *, gate: Any = None):
        from .gate import DeepGateCapability

        self.root = Path(root)
        if gate is not None:
            if not isinstance(gate, DeepGateCapability):
                raise DeepRefused("gate must be a DeepGateCapability minted on the House's deep store")
            if gate.store_root != str(self.root.resolve()):
                raise DeepRefused("this capability was minted for another deep store")
        self._gate = gate
        version = self.root / "VERSION"
        if not version.is_file() or version.read_text().strip() != DEEP_STORE_VERSION:
            raise DeepMissing(f"no {DEEP_STORE_VERSION} deep store at {self.root}")
        try:
            self._manifest = json.loads((self.root / config.MANIFEST).read_text())
        except (OSError, ValueError) as exc:
            raise DeepMissing(f"the deep store's manifest is unreadable: {type(exc).__name__}") from None
        if self._manifest.get("version") != DEEP_STORE_VERSION or \
                not isinstance(self._manifest.get("spans"), dict):
            raise DeepMissing("the deep store's manifest is not an equity-deep-v1 manifest")

    @property
    def gate(self) -> bool:
        return self._gate is not None

    def audit(self) -> dict[str, Any]:
        """The data job's audit as the manifest keeps it (verdicts and counts)."""
        found = self._manifest.get("audit")
        return json.loads(json.dumps(found)) if isinstance(found, dict) else {}

    def symbols(self, span: str) -> list[str]:
        """The symbols a span holds (open or sealed: a name and a count are no market row)."""
        _span_dir(span)
        return sorted((self._manifest["spans"].get(span) or {}))

    def first_day(self, span: str, symbol: str) -> dt.date | None:
        """A symbol's first session in a span (its inception there), None when it holds none."""
        row = (self._manifest["spans"].get(span) or {}).get(symbol)
        return dt.date.fromisoformat(row["first"]) if isinstance(row, Mapping) and row.get("first") else None

    def block(self, span: str, symbol: str) -> dict[str, np.ndarray]:
        """One block's arrays. A SEALED SPAN OPENS ONLY FOR THE GATE (DeepRefused); DeepMissing for a block the
        manifest does not name or a file that does not match it."""
        where = _span_dir(span)
        if span in config.SEALED_SPANS:
            if self._gate is None:
                raise DeepRefused(f"the {span} span opens only for the deep gate")
            if not (self.root / config.SEALED_DIR / config.GATE_MARK).is_file():
                raise DeepRefused("the sealed tree carries no DEEP_GATE mark")
        row = (self._manifest["spans"].get(span) or {}).get(symbol)
        if not isinstance(row, Mapping):
            raise DeepMissing(f"the deep store holds no {symbol} in {span}")
        path = self.root / where / f"{symbol}.npz"
        try:
            data = path.read_bytes()
        except OSError:
            raise DeepMissing(f"the deep store has no {span}/{symbol} block") from None
        if hashlib.sha256(data).hexdigest() != row.get("sha256"):
            raise DeepMissing(f"the {span}/{symbol} block does not match the manifest: refused rather than mixed")
        return read_block(data)


# ------------------------------------------------------------------------------------------- the looks' temporary stores
def looks_dir(root: str | Path, *, make: bool = False) -> Path:
    """`<root>/sealed/.looks/` (`config.LOOKS_DIR`): where every look's temporary stores are written, inside the sealed
    tree (0700, the DEEP_GATE mark). `make`: created (0700) when the sealed tree is there (DeepMissing otherwise)."""
    path = Path(root) / config.SEALED_DIR / config.LOOKS_DIR
    if make:
        if not (Path(root) / config.SEALED_DIR).is_dir():
            raise DeepMissing(f"no sealed tree at {root}: a look's stores are written inside it")
        path.mkdir(mode=0o700, exist_ok=True)
        os.chmod(path, 0o700)
    return path


def temp_prefix(name: str) -> str:
    """The prefix of a look's temporary directory: `deep-<name>-p<pid>-` (`sweep` reads the pid back)."""
    return f"{config.TEMP_PREFIX}{name}-p{os.getpid()}-"


def _alive(pid: int) -> bool:
    """Whether process `pid` is running (a zombie is not; one of another user is)."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    try:
        with open(f"/proc/{pid}/stat", "rb") as handle:
            state = handle.read().rsplit(b")", 1)[-1].split()[:1]
        return state != [b"Z"]
    except OSError:
        return True


def sweep(parent: str | Path, *, now: float | None = None, nameless: bool = False) -> int:
    """THE SWEEP: remove every `deep-*` directory under `parent` that a process left behind (`config.LOOKS_DIR`): one
    whose process (`-p<pid>-` in its name) is gone, or that is older than `config.TEMP_STALE_S`; with `nameless` (a
    directory that is the deep store's own: its looks directory and its top) also one whose name names no process (the
    first R1 build's). A look's own block removes its directory; this is for the look whose process was killed (the
    wall's SIGKILL, a CPU or memory limit, a box restart) before its `finally` ran, so no relabeled DVAL store outlives
    its look. The number removed (0 when `parent` is not a directory)."""
    import re
    import time

    parent = Path(parent)
    if not parent.is_dir():
        return 0
    clock = time.time() if now is None else float(now)
    removed = 0
    for entry in sorted(parent.iterdir()):
        if not entry.name.startswith(config.TEMP_PREFIX) or entry.is_symlink() or not entry.is_dir():
            continue
        found = re.search(r"-p(\d+)-", entry.name)
        try:
            age = clock - entry.stat().st_mtime
        except OSError:
            continue
        if found is None and not nameless:
            continue   # not the deep store's own directory: only what names its process is ours to judge
        if found is None or not _alive(int(found.group(1))) or age > config.TEMP_STALE_S:
            shutil.rmtree(entry, ignore_errors=True)
            removed += int(not entry.exists())
    return removed


def sweep_store(root: str | Path) -> int:
    """`sweep` of the deep store at `root`: its looks' directory, and its own top (where the first R1 build wrote
    them). Nothing is created; a root that is not there sweeps nothing."""
    return sweep(looks_dir(root), nameless=True) + sweep(root, nameless=True)


def as_of_closes(store: DeepStore, symbol: str, spans: Sequence[str]) -> dict[str, float]:
    """{ISO day: adjustment=all close} of `symbol` over `spans` joined (one as-of chain: a ratio of two of these is
    the total return between them). A sealed span needs the gate (DeepRefused)."""
    parts = [store.block(span, symbol) for span in spans if symbol in store.symbols(span)]
    if not parts:
        return {}
    joined = concat(parts)
    closes = adjusted(joined)["close"]
    return {from_ordinal(int(d)).isoformat(): float(c) for d, c in zip(joined["days"], closes) if c > 0}


__all__ = ["COLUMNS", "VENDOR", "ALL_PLACES", "DeepRefused", "DeepMissing", "ordinal", "from_ordinal", "block_bytes",
           "read_block", "rows_to_columns", "factors", "adjusted", "concat", "write_store", "DeepStore", "looks_dir",
           "temp_prefix", "sweep", "sweep_store", "as_of_closes"]
