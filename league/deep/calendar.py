"""The deep calendar: NYSE sessions 1999-2015 from the repo's own pre-2022 rules, the plan's closures, the two date
fixtures, the mask and the pseudo-dates a segment is written onto.

Owner: R1. THE RULES are league/equity/store.py `_year_before_2022` (the same holiday and early-close helpers as
`ltcm.data`, so the two calendars cannot drift apart), called unchanged, minus `config.CLOSURES` (2001-09-11..14,
2004-06-11, 2007-01-02, 2012-10-29..30). The store itself refuses years before 2016 (`store.FIRST_YEAR`); this module
is the only reader of the rules for those years, and it never changes the store. From 2016 on `sessions` is
`store.nyse_sessions` exactly.

THE FIXTURES (`fixture`, `mask_fixture`): dates only, one ISO day a line, byte-identical to the copies pinned in the
history-1017 PINS.log (`config.CALENDAR_SHA256`, `config.MASK_SHA256`). The House's data audit checks the vendor's
sessions against the fixture (league/ops/equity_deep.py), and a test holds the rules to it.

THE PSEUDO-DATES (`pseudo`): the first N sessions of the Train window from 2016-01-04, with their own early-close
flags. A segment's i-th session is written onto the i-th of them (`relabel`).
"""

from __future__ import annotations

import datetime as dt
import hashlib
from functools import lru_cache
from pathlib import Path

from ..equity import store as _store
from . import config

HERE = Path(__file__).resolve().parent


@lru_cache(maxsize=32)
def _deep_year(year: int) -> tuple[tuple[dt.date, bool], ...]:
    if not config.FIRST_DAY.year <= year < _store.FIRST_YEAR:
        raise ValueError(f"the deep calendar covers {config.FIRST_DAY.year}-{_store.FIRST_YEAR - 1}, not {year}")
    return tuple((day, early) for day, early in _store._year_before_2022(year) if day not in config.CLOSURES)


def sessions_with_flags(start: dt.date, end: dt.date) -> list[tuple[dt.date, bool]]:
    """(session, early close) from `start` to `end` inclusive: the deep rules before 2016, `store.nyse_sessions` from
    2016 on. ValueError before 1999-01-04 (`config.FIRST_DAY`'s year)."""
    if start < dt.date(config.FIRST_DAY.year, 1, 1):
        raise ValueError(f"the deep calendar starts in {config.FIRST_DAY.year}; {start} is before it")
    out: list[tuple[dt.date, bool]] = []
    for year in range(start.year, min(end.year, _store.FIRST_YEAR - 1) + 1):
        out.extend(row for row in _deep_year(year) if start <= row[0] <= end)
    if end.year >= _store.FIRST_YEAR:
        out.extend(_store.nyse_sessions(max(start, dt.date(_store.FIRST_YEAR, 1, 1)), end))
    return out


def sessions(start: dt.date, end: dt.date) -> list[dt.date]:
    """The sessions from `start` to `end` inclusive (`sessions_with_flags` without the flags)."""
    return [day for day, _ in sessions_with_flags(start, end)]


def deep_sessions() -> list[dt.date]:
    """Every session 1999-01-04..2015-12-31 (4,277)."""
    return sessions(config.FIRST_DAY, config.LAST_DAY)


def era(name: str) -> list[dt.date]:
    """The sessions of one of `config.ERAS`."""
    first, last = config.ERAS[name]
    return sessions(first, last)


def segment(name: str) -> tuple[list[dt.date], list[dt.date]]:
    """(look-back sessions, scored sessions) of one of `config.SEGMENTS`."""
    (b0, b1), (s0, s1) = config.SEGMENTS[name]
    return sessions(b0, b1), sessions(s0, s1)


def mask() -> list[dt.date]:
    """The mask's sessions from PREREG-H's nine windows on this calendar (235)."""
    return [day for first, last in config.MASK_WINDOWS for day in sessions(first, last)]


def _dates_file(name: str, sha256: str) -> list[dt.date]:
    data = (HERE / name).read_bytes()
    if hashlib.sha256(data).hexdigest() != sha256:
        raise ValueError(f"league/deep/{name} is not the pinned fixture")
    text = data.decode("ascii")
    if not text.endswith("\n"):
        raise ValueError(f"league/deep/{name} does not end with a newline")
    days = [dt.date.fromisoformat(line) for line in text[:-1].split("\n")]
    if [d.isoformat() for d in days] != text[:-1].split("\n") or days != sorted(set(days)):
        raise ValueError(f"league/deep/{name} is not one ascending ISO day a line")
    return days


@lru_cache(maxsize=1)
def fixture() -> tuple[dt.date, ...]:
    """The calendar fixture's sessions (sha-checked: ValueError for any other bytes)."""
    return tuple(_dates_file(config.CALENDAR_FIXTURE, config.CALENDAR_SHA256))


@lru_cache(maxsize=1)
def mask_fixture() -> tuple[dt.date, ...]:
    """The mask fixture's sessions (sha-checked)."""
    return tuple(_dates_file(config.MASK_FIXTURE, config.MASK_SHA256))


def pseudo(n: int) -> list[tuple[dt.date, bool]]:
    """The first `n` Train-window sessions from `config.PSEUDO_FIRST` with their early flags; ValueError past the
    window (2,264 sessions through 2024-12-31)."""
    from ..equity import config as econfig

    first, last = econfig.WINDOWS["train"]
    rows = _store.nyse_sessions(config.PSEUDO_FIRST, last)  # type: ignore[arg-type]
    if not 0 < int(n) <= len(rows):
        raise ValueError(f"a segment of {n} sessions does not fit the Train window's {len(rows)}")
    return rows[:int(n)]


__all__ = ["sessions_with_flags", "sessions", "deep_sessions", "era", "segment", "mask", "fixture", "mask_fixture",
           "pseudo"]
