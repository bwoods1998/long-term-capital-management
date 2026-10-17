"""THE RELABELED STORE: a deep segment written session for session onto Train-window pseudo-dates, so the unchanged
equity engine runs it.

Owner: R1. The plan's key finding (section 5.1): league/equity/runner.py `Isolated(decider, store_root)` runs Train on
ANY store root, `store.write_store` accepts any calendar and series, programs never see a date, and the engine reads
no early-close flag. So a segment's i-th session is written onto the i-th Train session from 2016-01-04
(`calendar.pseudo`), and a calendar-blind program's lots and summary are the same as on the true dates (the spike:
141 of 141 lots; `league/tests/test_deep_relabel.py` holds it for about twenty templates).

WHAT IS WRITTEN (`write_segment`): for each NEEDS symbol, its bars inside the segment (look-back + scored sessions)
from the deep store's blocks, raw open, high, low, close and volume as printed, and `all` REBUILT FROM THE RAW CLOSES
AND THE EVENTS AS OF THE SEGMENT'S OWN LAST SESSION (`blocks.adjusted`): no later distribution reaches its prices,
and there is no 2016 seam to splice. A symbol with no bar before its inception has none in the store (NaN there, as
on the true dates). The store carries no GATE mark: nothing of it is a sealed window of league/equity.

THE SEAL (`relabeled`): a DVAL segment (A, B) is written only from a store opened with the deep gate's capability,
into a temporary directory (0700) made for one look INSIDE THE SEALED TREE (`blocks.looks_dir`:
`<state>/equity-deep/sealed/.looks/deep-<segment>-p<pid>-*`, whatever `parent` says), and that directory is REMOVED
when the block ends, whether the look finished or failed. A process killed inside the block (the ops runner's wall
SIGKILL, a CPU or memory limit, a box restart) runs no `finally`: its directory is SWEPT (`blocks.sweep`: its process
is gone) before the next one is made here, and at the start of every deep_report, equity_deep and contamination-probe
run. TRAIN-D reads its open span alone: `SEGMENT_SPANS["traind"]` names no sealed span, so its code never opens
`sealed/`. Pseudo-dates reach into 2020-21: the run path has no reserve guard, and nothing of a
relabeled run is ever routed to swarm reporting (this package imports nothing of league.swarm).

`copy_onto` writes a true-date store's arrays onto other pseudo-dates (the behavioural test's second labeling and the
equivalence battery's).
"""

from __future__ import annotations

import datetime as dt
import os
import shutil
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

import numpy as np

from ..equity import config as econfig
from ..equity import store as estore
from . import blocks, calendar, config

#: The store directory inside a look's temporary directory (an equity store root).
STORE = "equity-daily"
SOURCE = "deep-relabel"


@dataclass(frozen=True)
class Relabeled:
    """One written segment: `root` (an equity store), `segment` (its name), `true_days` and `pseudo_days` (the
    segment's sessions, look-back first, and the Train sessions they were written onto), `lookback` (sessions before
    the first scored one) and `symbols` (what the store holds)."""

    root: Path
    segment: str
    true_days: tuple[dt.date, ...]
    pseudo_days: tuple[dt.date, ...]
    lookback: int
    symbols: tuple[str, ...]

    @property
    def scored_true(self) -> tuple[dt.date, ...]:
        return self.true_days[self.lookback:]

    @property
    def scored_pseudo(self) -> tuple[dt.date, ...]:
        return self.pseudo_days[self.lookback:]

    def pseudo_of(self, day: dt.date) -> dt.date:
        return self.pseudo_days[self.true_days.index(day)]


def segment_days(name: str) -> tuple[list[dt.date], int]:
    """(the segment's sessions, look-back first; the look-back count)."""
    back, scored = calendar.segment(name)
    return back + scored, len(back)


def segment_series(store: blocks.DeepStore, name: str, symbols: Sequence[str]) -> dict[str, dict[str, np.ndarray]]:
    """{SYMBOL: block arrays inside the segment} from the spans the segment reads (`config.SEGMENT_SPANS`); a symbol
    the store does not hold, or holds no bar of inside the segment, is left out. A sealed span needs the gate."""
    days, _ = segment_days(name)
    lo, hi = blocks.ordinal(days[0]), blocks.ordinal(days[-1])
    out: dict[str, dict[str, np.ndarray]] = {}
    for sym in symbols:
        parts = [store.block(span, sym) for span in config.SEGMENT_SPANS[name] if sym in store.symbols(span)]
        if not parts:
            continue
        joined = blocks.concat(parts)
        keep = (joined["days"] >= lo) & (joined["days"] <= hi)
        if keep.any():
            out[sym] = {key: np.asarray(value)[keep] for key, value in joined.items()}
    return out


def write_series(root: str | Path, true_days: Sequence[dt.date], series: Mapping[str, Mapping[str, Any]], *,
                 lookback: int, segment: str) -> Relabeled:
    """Write `series` ({SYMBOL: {"days": [date | ordinal...] on `true_days`, open, high, low, close, volume, div,
    split}}) onto the first len(`true_days`) Train sessions as an equity store at `root`, `all` rebuilt as of each
    symbol's last bar inside the segment. ValueError for a bar on a day outside `true_days`."""
    true_days = list(true_days)
    pseudo = calendar.pseudo(len(true_days))
    where = {day: i for i, day in enumerate(true_days)}
    out: dict[str, dict[str, Any]] = {}
    for sym, arrays in sorted(series.items()):
        days = [d if isinstance(d, dt.date) else blocks.from_ordinal(int(d)) for d in arrays["days"]]
        missing = [d for d in days if d not in where]
        if missing:
            raise ValueError(f"{sym} has a bar on {missing[0]}, not a session of the segment")
        adj = blocks.adjusted(arrays)
        out[sym] = {"days": [pseudo[where[d]][0] for d in days],
                    **{raw: [float(x) for x in np.asarray(arrays[col], dtype=np.float64)]
                       for raw, col in zip(estore.RAW_COLUMNS, ("open", "high", "low", "close", "volume"))},
                    **{name: [float(x) for x in adj[col]]
                       for name, col in zip(estore.ALL_COLUMNS, ("open", "high", "low", "close"))}}
    estore.write_store(root, calendar=pseudo, series=out, classes={s: econfig.ETF for s in out},
                       fetched_through=pseudo[-1][0], source=SOURCE, gate=False)
    return Relabeled(root=Path(root), segment=segment, true_days=tuple(true_days),
                     pseudo_days=tuple(d for d, _ in pseudo), lookback=int(lookback), symbols=tuple(sorted(out)))


def write_segment(root: str | Path, store: blocks.DeepStore, name: str, symbols: Sequence[str]) -> Relabeled:
    """The segment `name` of the deep store for `symbols`, written at `root` (`write_series`)."""
    if name in config.DVAL_SEGMENTS and not store.gate:
        raise blocks.DeepRefused(f"segment {name} is the sealed era: it is written only inside a look")
    days, back = segment_days(name)
    return write_series(root, days, segment_series(store, name, symbols), lookback=back, segment=name)


@contextmanager
def relabeled(store: blocks.DeepStore, name: str, symbols: Sequence[str], *,
              parent: str | Path | None = None) -> Iterator[Relabeled]:
    """THE ONE WAY A SEGMENT IS RUN: written into a fresh temporary directory (0700) and that directory removed when
    the block ends, on success and on failure alike. A DVAL segment's directory is always in the deep store's looks
    directory (`blocks.looks_dir`, inside `sealed/`); an open segment's under `parent` (default: the same). Before the
    directory is made, what a killed process left there is swept (`blocks.sweep`)."""
    if name in config.DVAL_SEGMENTS and not store.gate:
        raise blocks.DeepRefused(f"segment {name} is the sealed era: it is written only inside a look")
    where = blocks.looks_dir(store.root, make=True) if (name in config.DVAL_SEGMENTS or parent is None) \
        else Path(parent)
    blocks.sweep(where)
    tmp = Path(tempfile.mkdtemp(prefix=blocks.temp_prefix(name), dir=str(where)))
    try:
        os.chmod(tmp, 0o700)
        yield write_segment(tmp / STORE, store, name, symbols)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def copy_onto(src_root: str | Path, dst_root: str | Path, first: dt.date, *,
              symbols: Sequence[str] | None = None, price: float = 1.0, volume: float = 1.0) -> Relabeled:
    """A true-date equity store's Train sessions (synthetic: league/equity/synth.py) written session for session onto
    the NYSE sessions from `first` (`store.nyse_sessions`), raw and `all` arrays exactly as they are (`price`, `volume`:
    every price, raw and `all`, and every volume times these: the level test's store, league/deep/blind.py). Returns
    the mapping as a `Relabeled` (`lookback` 0)."""
    src = estore.EquityStore(src_root)
    classes = src.symbols()
    names = sorted(symbols or classes)
    bars = src.bars(names, "train", history=0)
    true_days = [estore.from_ordinal(int(d)) for d in bars.days]
    rows = estore.nyse_sessions(first, first + dt.timedelta(days=2 * len(true_days) + 30))[:len(true_days)]
    if len(rows) < len(true_days) or rows[-1][0] > econfig.WINDOWS["train"][1]:  # type: ignore[operator]
        raise ValueError("the pseudo-dates from that day do not fit the Train window")
    series: dict[str, dict[str, Any]] = {}
    for sym in names:
        raw, adj = bars.raw[sym], bars.adj[sym]
        ok = np.isfinite(raw[:, 3])
        scale = [float(volume) if name == estore.RAW_COLUMNS[4] else float(price) for name in estore.RAW_COLUMNS]
        series[sym] = {"days": [rows[i][0] for i in np.flatnonzero(ok)],
                       **{name: [float(x) * scale[k] if scale[k] != 1.0 else float(x) for x in raw[ok, k]]
                          for k, name in enumerate(estore.RAW_COLUMNS)},
                       **{name: [float(x) * float(price) if price != 1.0 else float(x) for x in adj[ok, k]]
                          for k, name in enumerate(estore.ALL_COLUMNS)}}
    estore.write_store(dst_root, calendar=rows, series=series, classes={s: classes[s] for s in series},
                       fetched_through=rows[-1][0], source=SOURCE, gate=False)
    return Relabeled(root=Path(dst_root), segment="copy", true_days=tuple(true_days),
                     pseudo_days=tuple(d for d, _ in rows), lookback=0, symbols=tuple(names))


__all__ = ["STORE", "SOURCE", "Relabeled", "segment_days", "segment_series", "write_series", "write_segment",
           "relabeled", "copy_onto"]
