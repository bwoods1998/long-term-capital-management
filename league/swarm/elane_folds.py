"""THE HIDDEN YEAR of an equity family (release E3, D14): one Train year a family, assigned at birth, never shown to it.

Owner: E (league/ops/E3_INTERFACES.md). A family born while `elane.memory.mode` is "record" gets one of the seven Train
years as its HIDDEN YEAR. Its Train bar, its record, its brief and the Train map read the other six, and the hidden
year's own results go to the memory's sealed tables alone (league/swarm/elane_memory.py): an out-of-fold reading of
every scored version that no generator, the family's own researcher included, has seen.

THE ASSIGNMENT (`assign`, `birth_fields`). `WORK_YEARS = (2016, 2017, 2018, 2019, 2022, 2023, 2024)`, held equal to
`elane_train.TRAIN_YEARS` by a test; `RESERVE_YEARS = (2020, 2021)` is never one of them (A15). `hidden_year =
WORK_YEARS[(k_c + h(cell)) % 7]`: cell = `elane_train.cell_of(lane, agenda, symbols)`; k_c = the equity families
already born in that cell with a `hidden_year`; `h(cell) = int(sha256(("fold-1|" + "/".join(cell)).encode())
.hexdigest()[:8], 16)` (`cell_hash`): a cell's seven births spread over the seven years. It sits in the family's
spec, immutable, and is honoured whatever the mode is later (a family's bar must not move under it). `gid` is `GID0`
and `expected_oof` is reserved (None) in E3.

THE LISTING RULE (`bar_years`, `runnable`; AS BUILT: D14 is silent on a symbol listed after 2016). E1's engine ends a
run "no_data" when one of the program's symbols has no bar in it, and E2 reads that as the House's failure: the
version is never scored. A whole Train span always holds a bar of such a symbol (XLC's first is in 2018), but a
stretch the cut leaves may hold none (2016-17 once 2018 is hidden), and the family could then never be scored. So a
year is RUNNABLE for a family's symbols only when every seen span of it AND its own span hold a bar of every symbol,
on the House's equity store (read one Train span at a time, never a reserve session), and `birth_fields` takes
`WORK_YEARS[(k_c + h(cell) + j) % 7]` for the smallest j of 0..6 whose year is runnable: j is 0, the formula above
exactly, for every symbol with a bar in each work year. A family with no runnable year gets no hidden year (seven
Train years, no out-of-fold row). On a House with no equity store yet there is no listing to read and the formula
stands alone; a store that is there and cannot be read raises, and the birth's guard stamps `FALLBACK` and says so.

THE SEEN SPANS (`seen_spans`). `seen_spans(None)` = `elane_train.TRAIN_SPANS`. `seen_spans(y)`: each Train span (first,
last) that does not contain y as it is; the one that does, cut into the stretch before y, `(first, date(y - 1, 12,
31))` when y > first.year, and the stretch after it, `(date(y + 1, 1, 1), last)` when y < last.year (two or three
spans, in date order). `hidden_span(y) = (date(y, 1, 1), date(y, 12, 31))`. A version of a hidden-year family is run
ONCE A SEEN SPAN (E1's `Isolated.train(start, end)` at each k, each run flat with fresh STATE, exactly as A15 runs its
two spans), and E2's `outside_years`, `combine`, `train_score`, `restart_check` and `add_run` read those runs and
nothing else. No session of y is a run session of any of them, so no row, figure, lot, STATE or cash of y exists in
what the bar, the record, the brief, the map or the stored runs hold.

WHY RUNS AND NOT A FILTERED VIEW (measured on E1's engine, two synthetic stores that differ only in the hidden year's
opens): in a whole-span run the sleeve's cash carries the hidden year's P&L into every later decision, so the later
seen years' own lots, P&L, t and exposure move with it, and no rebasing of a filtered result removes that. With one
run a seen span the same two stores gave byte-identical seen results.

WHAT STILL REACHES A SEEN RUN, stated as A15 states it for the reserve: the hidden year's BARS as look-back in the
stretch that follows it (a program with NEEDS history h reads the year's last h sessions at most, as it would have
live), and the store-file hashes of a stored run (they move with a refetch of any year and carry no figure). STATED
COST: a hidden year inside a span starts the following stretch flat (no lot is carried across it), and a version
costs up to 3 seen runs and 1 hidden run a k. THE LOOSENING, reported: such a family is judged on six seen years,
not seven; more zero-edge versions pass Train, and the screen's false-positive rate per program is untouched (Train
is in-sample).

`league.swarm.elane_train` and `elane_seal` are imported INSIDE FUNCTIONS only (`elane_train` and `elane_births`
import this module at the top), and so is `league.equity.store`. Standard library only.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import math
from pathlib import Path
from typing import Any, Collection, Mapping, Sequence

#: The seven Train years a hidden year is drawn from (a test holds this equal to `elane_train.TRAIN_YEARS`).
WORK_YEARS = (2016, 2017, 2018, 2019, 2022, 2023, 2024)
#: THE RESERVE (A15): never a hidden year, never a session of any run here.
RESERVE_YEARS = (2020, 2021)
#: The one genome id of E3 (a later release adds more).
GID0 = "g0"
#: `elane.memory.mode`: "record" is the only mode above "off" in E3.
MODES = ("off", "record")
#: What a birth is stamped with when `birth_fields` could not run: seven Train years, no out-of-fold row.
FALLBACK: dict[str, Any] = {"hidden_year": None, "gid": "g0", "expected_oof": None}
#: The one sentence a hidden-year family's brief gains (no year is named).
BRIEF_NOTE = ("One of the seven Train years is held out from you: the bar reads the other six, each stretch of them its "
              "own run starting flat, and the held-out year's results are never shown.")


def _block(settings: Mapping[str, Any] | None) -> Mapping[str, Any]:
    """The raw `elane.memory` block ({} for none, or for one that is not an object)."""
    lane = settings.get("elane") if isinstance(settings, Mapping) else None
    block = lane.get("memory") if isinstance(lane, Mapping) else None
    return block if isinstance(block, Mapping) else {}


def mode(settings: Mapping[str, Any] | None) -> str:
    """`elane.memory.mode` in the swarm's settings: "off" | "record" (a malformed value or an unreadable block is
    "off")."""
    value = _block(settings).get("mode")
    return value if isinstance(value, str) and value in MODES else "off"


def cell_hash(cell: Sequence[str]) -> int:
    """`int(sha256(("fold-1|" + "/".join(cell)).encode()).hexdigest()[:8], 16)` of a Train map cell (lane, agenda
    mechanism, universe group)."""
    return int(hashlib.sha256(("fold-1|" + "/".join(str(part) for part in cell)).encode()).hexdigest()[:8], 16)


def rotation(store: Any, cell: Sequence[str]) -> tuple[int, ...]:
    """The seven work years in the order the next family born in `cell` takes them: `WORK_YEARS[(k_c + cell_hash(cell)
    + j) % 7]` for j = 0..6, k_c the equity families already born in that cell with a `hidden_year` in their spec
    (alive or retired)."""
    from . import elane_seal, elane_train

    cell = tuple(str(part) for part in cell)
    born = 0
    for fam in elane_seal.equity_families(store):
        if hidden_year(fam) is None:
            continue
        facts = elane_seal.train_facts(fam, elane_train.STATE_KEY)
        born += int(elane_train.cell_of(facts["lane"], facts["agenda"], facts["symbols"]) == cell)
    start = born + cell_hash(cell)
    return tuple(WORK_YEARS[(start + j) % len(WORK_YEARS)] for j in range(len(WORK_YEARS)))


def assign(store: Any, cell: Sequence[str]) -> int:
    """The hidden year of the next family born in `cell`: `WORK_YEARS[(k_c + cell_hash(cell)) % 7]`, k_c the equity
    families already born in that cell with a `hidden_year` in their spec (alive or retired). D14's formula alone:
    `birth_fields` holds it to the years the family's symbols can run (THE LISTING RULE)."""
    return rotation(store, cell)[0]


def bar_years(root: Any, symbols: Sequence[str]) -> dict[str, frozenset[int]] | None:
    """THE LISTING RULE's reading (the module docstring): each symbol's work years that hold at least one of its bars
    in the House's equity store (`<root>/equity-daily`), read one Train span at a time, so never a reserve session.
    None when there is nothing to read: no root, no symbol, or no equity store there yet. A store that is there and
    cannot be read, or that holds no such symbol, raises (`league.equity.store.MissingData`)."""
    from ..equity.store import STORE_DIR, EquityStore
    from . import elane_train

    names = tuple(dict.fromkeys(str(s).strip().upper() for s in symbols or () if str(s).strip()))
    if root is None or not names:
        return None
    path = Path(root) / STORE_DIR
    if not (path / "VERSION").is_file():
        return None
    equity = EquityStore(path)
    held: dict[str, set[int]] = {name: set() for name in names}
    for first, last in elane_train.TRAIN_SPANS:
        bars = equity.bars(names, "train", history=0, start=first, end=last)
        years = [bars.day(i).year for i in range(bars.n)]
        for name in names:
            close = bars.raw[name][:, 3]
            held[name].update(year for year, there in zip(years, (close == close).tolist()) if there)  # NaN: no bar
    return {name: frozenset(year for year in found if year in WORK_YEARS) for name, found in held.items()}


def runnable(hidden: int, held: Mapping[str, Collection[int]]) -> bool:
    """Whether E1's engine can run every stretch a family is run on with `hidden` as its hidden year: each seen span
    and the hidden span hold a bar of every symbol (`held`: `bar_years`' answer; a run with no bar of a symbol ends
    "no_data"). ValueError for a year outside `WORK_YEARS`."""
    spans = (*seen_spans(hidden), hidden_span(hidden))
    return all(any(year in found for year in range(first.year, last.year + 1))
               for first, last in spans for found in held.values())


def birth_fields(store: Any, settings: Mapping[str, Any] | None, *, lane: str, agenda: str, symbols: Sequence[str],
                 expected_oof: Any = None) -> dict[str, Any]:
    """What a birth's spec gains: {"hidden_year": int | None, "gid": "g0", "expected_oof": float | None}. The hidden
    year is None when the mode is "off"; else the first year of `rotation(store, elane_train.cell_of(lane, agenda,
    symbols))` the family's symbols can run (`runnable` on `bar_years(store.root, symbols)`: `assign`'s year whenever
    every symbol has a bar in each work year, and on a House with no equity store yet), None when none can.
    `expected_oof` is kept only when it is a finite number in [-1, 1] (no prompt asks for it in E3)."""
    from . import elane_train

    year = None
    if mode(settings) == "record":
        held = bar_years(getattr(store, "root", None), symbols)
        year = next((y for y in rotation(store, elane_train.cell_of(lane, agenda, symbols))
                     if held is None or runnable(y, held)), None)
    kept = None
    if isinstance(expected_oof, (int, float)) and not isinstance(expected_oof, bool) \
            and math.isfinite(expected_oof) and -1.0 <= float(expected_oof) <= 1.0:
        kept = float(expected_oof)
    return {"hidden_year": year, "gid": GID0, "expected_oof": kept}


def _work_year(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value in WORK_YEARS


def hidden_year(fam: Mapping[str, Any] | None) -> int | None:
    """A family's hidden year: its spec's `hidden_year`, only when it is one of `WORK_YEARS`. NEVER RAISES: anything
    unreadable is None (the family then reads the seven Train years)."""
    try:
        spec = fam.get("spec") if isinstance(fam, Mapping) else None
        value = spec.get("hidden_year") if isinstance(spec, Mapping) else None
        return int(value) if _work_year(value) else None
    except Exception:  # noqa: BLE001 - unreadable: no hidden year
        return None


def seen_spans(hidden: int | None) -> tuple[tuple[dt.date, dt.date], ...]:
    """THE SEEN SPANS (the module docstring): `elane_train.TRAIN_SPANS` for None; for a year of `WORK_YEARS`, the
    Train spans with that year cut out (two or three spans, in date order); ValueError for any other year."""
    from . import elane_train

    if hidden is None:
        return tuple(elane_train.TRAIN_SPANS)
    if not _work_year(hidden):
        raise ValueError(f"a hidden year is one of {', '.join(str(y) for y in WORK_YEARS)}, not {hidden!r}")
    out: list[tuple[dt.date, dt.date]] = []
    for first, last in elane_train.TRAIN_SPANS:
        if not first.year <= hidden <= last.year:
            out.append((first, last))
            continue
        if hidden > first.year:
            out.append((first, dt.date(hidden - 1, 12, 31)))
        if hidden < last.year:
            out.append((dt.date(hidden + 1, 1, 1), last))
    if tuple(out) == tuple(elane_train.TRAIN_SPANS):  # fail closed: never seven years for a family told of six
        raise ValueError(f"the hidden year {hidden} lies in no Train span")
    return tuple(out)


def hidden_span(hidden: int) -> tuple[dt.date, dt.date]:
    """`(date(hidden, 1, 1), date(hidden, 12, 31))`; ValueError for a year outside `WORK_YEARS`."""
    if not _work_year(hidden):
        raise ValueError(f"a hidden year is one of {', '.join(str(y) for y in WORK_YEARS)}, not {hidden!r}")
    return dt.date(hidden, 1, 1), dt.date(hidden, 12, 31)


__all__ = ["WORK_YEARS", "RESERVE_YEARS", "GID0", "MODES", "FALLBACK", "BRIEF_NOTE", "mode", "cell_hash", "rotation",
           "assign", "bar_years", "runnable", "birth_fields", "hidden_year", "seen_spans", "hidden_span"]
