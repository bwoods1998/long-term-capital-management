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
import this module at the top). Standard library only.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import math
from typing import Any, Mapping, Sequence

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


def assign(store: Any, cell: Sequence[str]) -> int:
    """The hidden year of the next family born in `cell`: `WORK_YEARS[(k_c + cell_hash(cell)) % 7]`, k_c the equity
    families already born in that cell with a `hidden_year` in their spec (alive or retired)."""
    from . import elane_seal, elane_train

    cell = tuple(str(part) for part in cell)
    born = 0
    for fam in elane_seal.equity_families(store):
        if hidden_year(fam) is None:
            continue
        facts = elane_seal.train_facts(fam, elane_train.STATE_KEY)
        born += int(elane_train.cell_of(facts["lane"], facts["agenda"], facts["symbols"]) == cell)
    return WORK_YEARS[(born + cell_hash(cell)) % len(WORK_YEARS)]


def birth_fields(store: Any, settings: Mapping[str, Any] | None, *, lane: str, agenda: str, symbols: Sequence[str],
                 expected_oof: Any = None) -> dict[str, Any]:
    """What a birth's spec gains: {"hidden_year": int | None, "gid": "g0", "expected_oof": float | None}. The hidden
    year is None when the mode is "off", else `assign(store, elane_train.cell_of(lane, agenda, symbols))`;
    `expected_oof` is kept only when it is a finite number in [-1, 1] (no prompt asks for it in E3)."""
    from . import elane_train

    year = None
    if mode(settings) == "record":
        year = assign(store, elane_train.cell_of(lane, agenda, symbols))
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


__all__ = ["WORK_YEARS", "RESERVE_YEARS", "GID0", "MODES", "FALLBACK", "BRIEF_NOTE", "mode", "cell_hash", "assign",
           "birth_fields", "hidden_year", "seen_spans", "hidden_span"]
