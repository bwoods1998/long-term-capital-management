"""The Gym store's fixed layout and the backfill's plan, standard library only.

The store (v1) is fixed by the options-swarm plan (`docs/goals/LTCM_OPTIONS_SWARM.md`, "The Gym").
This module holds everything about it that needs no third-party package: the windows, the trading
calendar arithmetic, the file paths, the backfill's stages and their order, the per-root strike
judgement, and the manifest journal. The Parquet writing lives in `frames.py` (polars and pyarrow)
and the ThetaData calls in `backfill.py`; both run on the data box.

Nothing here reads a key, a quote or a price. Dates appear only in paths and in the manifest.

THE 2020-21 EXTENSION (stages 9 and 10, Sept 27, 2026). Train can reach back to 2020-01-02 (`EARLY`; the
COVID crash and rebound, then 2021's low-volatility bull), but only once the owner's switch says so: the swarm's
`gym.train_from` (league/swarm/settings.py) and a Gym image built with `images.py build gym --train-from 2020-01-02`.
Until then `window_of` calls those days "pre", exactly as before: stages 9 and 10 fetch them onto the data box, the
journal labels them "pre", and every image built without `--train-from` prunes them, so no Gym or gate image changes.
Stage 9 also fetches the underlying alone for the `HISTORY_SESSIONS` (60) sessions before 2020-01-02 (job `under`): the
history a program may ask for (NEEDS `history`, at most 60) going into the March 2020 crash. An image built with
`--train-from` keeps the underlying of the 60 sessions before its first Train day as "history" (never Train: no chain, no
trade); every other image keeps none. `--early-roots` leaves a root out of stages 9 and 10 (and of an image's 2020-21).

BLOCKS (stages 11 and up, Sept 29, 2026). Longer history is fetched as "blocks": pre-2022 stretches of roots and days
read from a private file on the data box (`backfill.py run --blocks /data/work/blocks.json`). Which roots the vendor
serves from which day is account knowledge, so it never goes into this public module; the code stays generic and
refuses any block that could touch a file stages 1-10 own (`check_block_task`): a block never plans a day on or after
Train's first day (2022-01-03), nor the core roots' 2020-21 chains. Every block day is "pre" to every image built today.
A block's jobs keep an underlying series the journal already holds (the history under an adopted image never moves).

THE QUIET WINDOW. The nightly forward job (nightly.py) runs at 02:00 America/New_York and the account allows one
ThetaData session. A backfill started with `--nightly-quiet` holds no session inside `quiet_window` (05:30-07:30Z, and
02:00 ET - 30 min .. + 90 min, so 05:30-08:30Z in winter): it stops before it, and refuses to log in inside it.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence

STORE_VERSION = "store-v1"

#: Where the store lives on every box that holds one (the data box, the Gym image, the gate image).
STORE_ROOT = "/data/store"
#: The data box's working area: the manifest journal, per-day expiry lists, the progress file.
WORK_ROOT = "/data/work"
#: The one file that holds the ThetaData key, on the data box only (mode 0600).
KEY_PATH = "/data/secrets/thetadata.env"

CORE_FIVE: tuple[str, ...] = ("SPY", "QQQ", "IWM", "XSP", "SPXW")

#: The windows, by date (inclusive). Forward is every trading day after the holdout's last.
TRAIN = (dt.date(2022, 1, 3), dt.date(2024, 12, 31))
VALIDATION = (dt.date(2025, 1, 2), dt.date(2025, 12, 31))
HOLDOUT = (dt.date(2026, 1, 2), dt.date(2026, 9, 25))
#: The earliest day Train may reach: 2017-01-03 since Train from 2017 (Sept 29, 2026: 2017's calm, the February 2018
#: volatility shock and the fourth-quarter 2018 selloff, 2019); an image takes those years only when built with
#: `--train-from 2017-01-03`, and every day before an image's own first Train day is "pre" to it (`window_of`).
TRAIN_EARLIEST = dt.date(2017, 1, 3)
#: The stretch stages 9 and 10 fetch (the 2020-21 extension; the module docstring). A literal, never derived from
#: `TRAIN_EARLIEST`: stage 9's task list is planned from it and must not move when Train reaches further back.
EARLY = (dt.date(2020, 1, 2), dt.date(2021, 12, 31))
#: The sessions of underlying alone before Train's first day that give a program its history (NEEDS `history` is at most
#: 60 sessions): stage 9 fetches them before 2020-01-02, and an image with `--train-from` keeps them as "history".
HISTORY_SESSIONS = 60
#: The calendar years (ThetaData `calendar_year`) the backfill needs: stages 1-8 from 2022; stages 9 and 10 add 2020-21
#: and 2019 (the history sessions): their holidays and half days (without them a 2020 half day would be stored as a full
#: session).
CALENDAR_YEARS: tuple[int, ...] = (2022, 2023, 2024, 2025, 2026, 2027)
EARLY_STAGES = (9, 10)
EARLY_YEARS = (2019, 2020, 2021)

#: Strikes per side of the money that the one-minute NBBO keeps (ThetaData `strike_range`). The
#: index roots with $5 strikes near the money get more, so the band covers a similar distance.
DEFAULT_STRIKE_RANGE = 25
STRIKE_RANGE = {"SPXW": 40}
#: Days to expiry the NBBO keeps, and the back months for calendars (SPY, QQQ).
MAX_DTE = 14
SIP_SOURCE = "alpaca SIP completed-minute OHLCV v1"
SIP_COVERAGE_SCHEMA = 2


BACK_MONTH_DTE = 45
BACK_MONTH_ROOTS = ("SPY", "QQQ")
#: `expiries.parquet` lists every expiry listed on a day up to this many days out.
EXPIRY_LIST_DTE = 45
#: The fill-calibration sample (stage 5): Train days only, one in five, 0-7 DTE, 10 strikes.
TQ_EVERY = 5
TQ_MAX_DTE = 7
TQ_STRIKE_RANGE = 10

NORMAL_OPEN, NORMAL_CLOSE, HALF_CLOSE = 570, 960, 780

KINDS = ("nbbo", "underlying", "oi", "trade_quote")


def sip_coverage(minutes: Sequence[int], hours: tuple[int, int]) -> dict[str, Any]:
    """Completed-bar grid coverage, never a claim of first-publication/as-of availability."""
    expected = set(range(hours[0] + 1, hours[1] + 1))
    known = set(minutes)
    return {"schema": SIP_COVERAGE_SCHEMA, "expected": len(expected), "known": len(known & expected),
            "missing_minutes": sorted(expected - known), "complete": known == expected and len(minutes) == len(known),
            "provenance": "finalized_without_publication_receipts"}


def window_of(day: dt.date, train_from: dt.date | None = None) -> str:
    """The day's window. `train_from` is where Train starts (default `TRAIN[0]`, 2022-01-03: what every stage, journal
    record and image has used); an image built with `--train-from 2020-01-02` (or `2017-01-03`) passes it, so 2020-21
    (and 2017-19) count as Train there."""
    first = TRAIN[0] if train_from is None else train_from
    if not TRAIN_EARLIEST <= first <= TRAIN[0]:
        raise ValueError(f"Train starts between {TRAIN_EARLIEST} and {TRAIN[0]}, not {first}")
    if day < first:
        return "pre"
    if day <= TRAIN[1]:
        return "train"
    if VALIDATION[0] <= day <= VALIDATION[1]:
        return "validation"
    if HOLDOUT[0] <= day <= HOLDOUT[1]:
        return "holdout"
    if day > HOLDOUT[1]:
        return "forward"
    return "gap"  # 2025-01-01 and 2026-01-01 are holidays; nothing lands here


#: The nightly job's quiet window (module docstring): fixed UTC minutes, widened to cover 02:00 ET's own margins.
QUIET_UTC = (5 * 60 + 30, 7 * 60 + 30)
QUIET_ET_MARGINS = (30, 90)  # minutes before and after 02:00 America/New_York
#: Without a time-zone database the window is the winter one, which covers both.
QUIET_FALLBACK_END = 8 * 60 + 30
#: The exit code of a runner that stopped (or refused to start) for the quiet window.
QUIET_EXIT = 75


def quiet_window(day: dt.date) -> tuple[dt.datetime, dt.datetime]:
    """The quiet window of UTC date `day`, as aware UTC datetimes [start, end)."""
    utc = dt.timezone.utc
    start = dt.datetime.combine(day, dt.time(QUIET_UTC[0] // 60, QUIET_UTC[0] % 60), utc)
    end = dt.datetime.combine(day, dt.time(QUIET_UTC[1] // 60, QUIET_UTC[1] % 60), utc)
    try:
        from zoneinfo import ZoneInfo

        nightly = dt.datetime.combine(day, dt.time(2, 0), ZoneInfo("America/New_York")).astimezone(utc)
    except Exception:  # noqa: BLE001 - no tz database: the widest (winter) window
        return start, max(end, dt.datetime.combine(day, dt.time(QUIET_FALLBACK_END // 60, QUIET_FALLBACK_END % 60), utc))
    return (min(start, nightly - dt.timedelta(minutes=QUIET_ET_MARGINS[0])),
            max(end, nightly + dt.timedelta(minutes=QUIET_ET_MARGINS[1])))


def next_quiet(now: dt.datetime) -> tuple[dt.datetime, dt.datetime]:
    """The quiet window that contains `now` (aware), else the next one."""
    now = now.astimezone(dt.timezone.utc)
    for offset in (-1, 0, 1, 2):
        start, end = quiet_window(now.date() + dt.timedelta(days=offset))
        if now < end:
            return start, end
    raise AssertionError("unreachable: a window ends every day")  # pragma: no cover


def in_quiet(now: dt.datetime, margin_seconds: float = 0.0) -> bool:
    """Whether `now` is inside the quiet window, or less than `margin_seconds` before it."""
    start, end = next_quiet(now)
    return start - dt.timedelta(seconds=float(margin_seconds)) <= now.astimezone(dt.timezone.utc) < end


#: A root whose options were listed under another symbol before a date: (first day of the new
#: symbol, the older symbol). Facebook's options were FB until META took the ticker on 2022-06-09;
#: before that, the symbol META belonged to the Roundhill Ball Metaverse ETF (a different underlying).
ROOT_HISTORY: dict[str, tuple[tuple[dt.date, str], ...]] = {"META": ((dt.date(2022, 6, 9), "FB"),)}


def source_root(root: str, day: dt.date) -> str:
    """The ThetaData symbol that carried this root's options on `day` (the store keeps `root`)."""
    for first_day, older in ROOT_HISTORY.get(root, ()):
        if day < first_day:
            return older
    return root


def strike_range(root: str) -> int:
    return int(STRIKE_RANGE.get(root, DEFAULT_STRIKE_RANGE))


def calendar_years(stages: Sequence[int] = (), blocks: Mapping[int, "Block"] | None = None) -> tuple[int, ...]:
    """The calendar years a run of `stages` needs: 2019-2021 as well when it plans stage 9 or 10, and each planned
    block's years (its history sessions' year included)."""
    early = EARLY_YEARS if set(stages) & set(EARLY_STAGES) else ()
    extra: set[int] = set()
    for stage in stages:
        if blocks and stage in blocks:
            extra |= set(blocks[stage].years())
    return tuple(sorted(set(CALENDAR_YEARS) | set(early) | extra))


def history_days(calendar: "Calendar", first: dt.date, sessions: int = HISTORY_SESSIONS) -> list[dt.date]:
    """The `sessions` trading days just before `first` (a program's history going into Train's first day)."""
    return calendar.days(first - dt.timedelta(days=2 * sessions + 30), first - dt.timedelta(days=1))[-int(sessions):]


def early_roots(roots: Sequence[str] | None, core: Sequence[str] = CORE_FIVE) -> list[str]:
    """The roots stages 9 and 10 fetch: `roots` (the operator's `--early-roots`, e.g. without XSP) within the core five,
    else the core five."""
    if not roots:
        return list(core)
    wanted = {str(r).upper() for r in roots}
    unknown = wanted - set(core)
    if unknown:
        raise ValueError(f"--early-roots takes core roots only ({', '.join(core)}), not {', '.join(sorted(unknown))}")
    return [r for r in core if r in wanted]


def parse_root_first(value: str | Mapping[str, Any] | None, train_from: dt.date | None) -> dict[str, dt.date]:
    """Each root's own first Train day in a Gym image (`--root-first ROOT=DATE,...`, Train from 2017): a root listed
    here keeps no chain dated before its day, and the underlying of the `HISTORY_SESSIONS` sessions before it as its
    history, so one root's early years (XSP's 2017-19, if thin) go without dropping its later ones, and roots fetched
    only from 2020 (the names) start there whatever the image's `train_from`. Refused: a root that is not a symbol, a root
    named twice, a day before the image's `train_from` or after Train's core start (2022-01-03), and any day without
    `train_from`."""
    if not value:
        return {}
    pairs: list[tuple[str, str]] = []
    if isinstance(value, Mapping):
        pairs = [(str(k), str(v)) for k, v in value.items()]
    else:
        for part in str(value).split(","):
            if not part.strip():
                continue
            root, sep, day = part.partition("=")
            if not sep:
                raise ValueError(f"--root-first takes ROOT=YYYY-MM-DD, not {part.strip()!r}")
            pairs.append((root, day))
    if train_from is None:
        raise ValueError("--root-first goes with --train-from (a root's own day is inside an image's Train)")
    out: dict[str, dt.date] = {}
    for root, text in pairs:
        root = root.strip().upper()
        if not root.isalnum():
            raise ValueError(f"--root-first: not a root: {root!r}")
        if root in out:
            raise ValueError(f"--root-first names {root} twice")
        try:
            day = dt.date.fromisoformat(text.strip())
        except ValueError as error:
            raise ValueError(f"--root-first {root}: not a date: {text.strip()!r}") from error
        if not train_from <= day <= TRAIN[0]:
            raise ValueError(f"--root-first {root}: {day} is not between the image's first Train day {train_from} and "
                             f"{TRAIN[0]}")
        out[root] = day
    return out


# ------------------------------------------------------------------------------ calendar
class Calendar:
    """Trading days and their hours from a table of exceptions (ThetaData's `calendar_year`).

    `exceptions` maps a date to (open_min, close_min), or None for a full close. Every other
    weekday is a normal 09:30-16:00 session. Minutes are since midnight ET.
    """

    def __init__(self, exceptions: Mapping[dt.date, tuple[int, int] | None]):
        self.exceptions = dict(exceptions)

    @classmethod
    def from_rows(cls, rows: Iterable[Mapping[str, Any]]) -> "Calendar":
        """Rows as ThetaData returns them: date, type (full_close|early_close), open, close."""
        out: dict[dt.date, tuple[int, int] | None] = {}
        for row in rows:
            day = as_date(row["date"])
            kind = str(row.get("type") or "")
            if kind == "full_close":
                out[day] = None
            elif kind == "early_close":
                out[day] = (hhmm(row.get("open") or "09:30:00"), hhmm(row.get("close") or "13:00:00"))
        return cls(out)

    def hours(self, day: dt.date) -> tuple[int, int] | None:
        if day.weekday() >= 5:
            return None
        if day in self.exceptions:
            return self.exceptions[day]
        return (NORMAL_OPEN, NORMAL_CLOSE)

    def is_trading(self, day: dt.date) -> bool:
        return self.hours(day) is not None

    def days(self, start: dt.date, end: dt.date) -> list[dt.date]:
        out, day = [], start
        while day <= end:
            if self.is_trading(day):
                out.append(day)
            day += dt.timedelta(days=1)
        return out

    def previous(self, day: dt.date) -> dt.date:
        """The last trading day strictly before `day`."""
        day -= dt.timedelta(days=1)
        while not self.is_trading(day):
            day -= dt.timedelta(days=1)
        return day

    def covers(self, year: int) -> bool:
        """Whether the exceptions hold the year (every NYSE year has full closes on weekdays): a calendar fetched
        without that year would call its holidays trading days and its half days full sessions."""
        return any(v is None and d.year == year and d.weekday() < 5 for d, v in self.exceptions.items())

    def to_json(self) -> dict[str, Any]:
        return {d.isoformat(): (list(v) if v else None) for d, v in sorted(self.exceptions.items())}

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> "Calendar":
        return cls({as_date(k): (tuple(v) if v else None) for k, v in data.items()})


def hhmm(text: Any) -> int:
    parts = str(text).split(":")
    return int(parts[0]) * 60 + int(parts[1])


def as_date(value: Any) -> dt.date:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    return dt.date.fromisoformat(str(value)[:10])


# ------------------------------------------------------------------------------ paths
def rel_path(kind: str, root: str, day: dt.date) -> str:
    if kind not in KINDS:
        raise ValueError(f"unknown kind {kind!r}")
    if not root.isalnum() or root.upper() != root:
        raise ValueError(f"not a root: {root!r}")
    return f"{kind}/{root}/{day.isoformat()}.parquet"


def parse_rel_path(rel: str) -> tuple[str, str, dt.date] | None:
    parts = rel.strip("/").split("/")
    if len(parts) != 3 or parts[0] not in KINDS or not parts[2].endswith(".parquet"):
        return None
    try:
        return parts[0], parts[1], dt.date.fromisoformat(parts[2][: -len(".parquet")])
    except ValueError:
        return None


# ------------------------------------------------------------------------------ the plan
class Task:
    """One unit of backfill work: a (stage, job, root, day). Its id is stable across restarts."""

    __slots__ = ("stage", "job", "root", "day")

    def __init__(self, stage: int, job: str, root: str, day: dt.date):
        self.stage, self.job, self.root, self.day = int(stage), job, root, day

    @property
    def id(self) -> str:
        return f"{self.job}:{self.root}:{self.day.isoformat()}"

    @property
    def window(self) -> str:
        return window_of(self.day)

    def __repr__(self) -> str:  # pragma: no cover - diagnostics
        return f"Task({self.stage}, {self.id})"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Task) and other.id == self.id and other.stage == self.stage

    def __hash__(self) -> int:
        return hash((self.stage, self.id))


#: The jobs: `day` = NBBO + underlying + OI + listed expiries for a root-day (0-14 DTE);
#: `tq` = the trade_quote sample; `back` = the 15-45 DTE back months merged into the day's NBBO; `under` = the
#: underlying alone (history sessions before Train's first day, stage 9).
JOBS = ("day", "tq", "back", "chk", "chk1s", "under")

STAGES: dict[int, str] = {
    1: "core five, 2023-2025 (Train's later part and Validation)",
    2: "core five holdout, 2026-01-02..2026-09-25 (gate image only)",
    3: "core five, 2022",
    4: "the 20 names over Train + Validation, then their holdout",
    5: "trade_quote calibration samples: core five, Train days, one in five, 0-7 DTE, 10 strikes",
    6: "back months to 45 DTE, SPY and QQQ",
    7: "forward: the previous trading day for the whole universe (the nightly job)",
    8: "forward: that day's back months to 45 DTE, SPY and QQQ (the nightly job, after stage 7)",
    9: "the 2020-21 extension: core five, 2020-01-02..2021-12-31, 0-14 DTE (window 'pre' until the switch)",
    10: "the 2020-21 extension: back months to 45 DTE, SPY and QQQ, 2020-01-02..2021-12-31 (after stage 9)",
}


#: Stages from here on are blocks (module docstring): read from the private blocks file, never written here.
FIRST_BLOCK_STAGE = 11
LAST_BLOCK_STAGE = 99
BLOCK_JOBS = ("day", "back")
#: A block's first day is never before this (a guard against a mistyped year; the vendor decides what it serves).
BLOCK_FLOOR = dt.date(2000, 1, 3)


class Block:
    """One pre-2022 stretch: `job` ("day": chains, underlying, OI and listed expiries; "back": the 15-45 DTE back
    months merged into a day block's files, after it) for `roots` on the trading days `first`..`last`. A root in
    `root_first` starts on its own later day, a root in `skip` is left out, and a day block may also take the underlying
    alone for `history_sessions` sessions before `first` (job `under`, like stage 9)."""

    __slots__ = ("stage", "what", "job", "roots", "first", "last", "root_first", "skip", "history_sessions", "after")

    def __init__(self, stage: int, *, job: str, roots: Sequence[str], first: dt.date, last: dt.date, what: str = "",
                 root_first: Mapping[str, dt.date] | None = None, skip: Sequence[str] = (), history_sessions: int = 0,
                 after: int | None = None):
        self.stage, self.what, self.job = int(stage), str(what), str(job)
        self.roots = tuple(roots)
        self.first, self.last = first, last
        self.root_first = dict(root_first or {})
        self.skip = frozenset(skip)
        self.history_sessions = int(history_sessions)
        self.after = None if after is None else int(after)

    def day_roots(self, day: dt.date) -> list[str]:
        """The roots this block fetches on `day`."""
        if not self.first <= day <= self.last:
            return []
        return [r for r in self.roots if r not in self.skip and day >= self.root_first.get(r, self.first)]

    def history(self, calendar: Calendar) -> list[dt.date]:
        return history_days(calendar, self.first, self.history_sessions) if self.history_sessions else []

    def history_roots(self) -> list[str]:
        """History goes to the roots that start on the block's first day."""
        return [r for r in self.roots if r not in self.skip and self.root_first.get(r, self.first) <= self.first]

    def years(self) -> list[int]:
        start = self.first - dt.timedelta(days=2 * self.history_sessions + 30) if self.history_sessions else self.first
        return list(range(start.year, self.last.year + 1))

    def tasks(self, calendar: Calendar) -> list[Task]:
        out = []
        if self.job == "day":
            for day in self.history(calendar):
                for root in self.history_roots():
                    out.append(Task(self.stage, "under", root, day))
        for day in calendar.days(self.first, self.last):
            for root in self.day_roots(day):
                out.append(Task(self.stage, self.job, root, day))
        return out


def _block_date(value: Any, what: str) -> dt.date:
    try:
        day = dt.date.fromisoformat(str(value))
    except ValueError as error:
        raise ValueError(f"{what}: not a date: {value!r}") from error
    if day < BLOCK_FLOOR:
        raise ValueError(f"{what}: {day} is before {BLOCK_FLOOR}")
    return day


def _block_root(value: Any, what: str) -> str:
    root = str(value)
    if not root.isalnum() or root.upper() != root:
        raise ValueError(f"{what}: not a root: {value!r}")
    return root


def parse_blocks(data: Mapping[str, Any], *, names: Sequence[str] = (), core: Sequence[str] = CORE_FIVE) -> dict[int, Block]:
    """The private blocks file (JSON: {"schema": 1, "<stage>": {...}}) as checked Blocks. Refuses anything malformed,
    any day on or after Train's first day, and any block that would re-plan a root-day stages 1-10 own
    (`check_block_task`, checked again per task when planned). `roots` is a list, "core" or "names" (the universe's)."""
    if not isinstance(data, Mapping) or data.get("schema") != 1:
        raise ValueError("the blocks file must be a JSON object with schema 1")
    known = {"what", "job", "roots", "first", "last", "root_first", "skip", "history_sessions", "after"}
    blocks: dict[int, Block] = {}
    for key, spec in data.items():
        if key == "schema":
            continue
        if not str(key).isdigit():
            raise ValueError(f"block key {key!r} is not a stage number")
        stage = int(key)
        what = f"block {stage}"
        if not FIRST_BLOCK_STAGE <= stage <= LAST_BLOCK_STAGE:
            raise ValueError(f"{what}: blocks are stages {FIRST_BLOCK_STAGE}-{LAST_BLOCK_STAGE}; 1-10 are fixed in code")
        if not isinstance(spec, Mapping):
            raise ValueError(f"{what}: not an object")
        unknown = set(spec) - known
        if unknown:
            raise ValueError(f"{what}: unknown fields {sorted(unknown)}")
        job = str(spec.get("job", ""))
        if job not in BLOCK_JOBS:
            raise ValueError(f"{what}: job must be one of {BLOCK_JOBS}, not {job!r}")
        spec_roots = spec.get("roots")
        if spec_roots == "core":
            roots = list(core)
        elif spec_roots == "names":
            roots = [str(r) for r in names]
            if not roots:
                raise ValueError(f"{what}: roots \"names\" but the universe lists no names")
        elif isinstance(spec_roots, list) and spec_roots:
            roots = [_block_root(r, what) for r in spec_roots]
        else:
            raise ValueError(f"{what}: roots must be \"core\", \"names\" or a non-empty list")
        if len(set(roots)) != len(roots):
            raise ValueError(f"{what}: a root is listed twice")
        first, last = _block_date(spec.get("first"), f"{what} first"), _block_date(spec.get("last"), f"{what} last")
        if last < first:
            raise ValueError(f"{what}: last {last} is before first {first}")
        if last >= TRAIN[0]:
            raise ValueError(f"{what}: a block ends before Train's first day {TRAIN[0]}, not {last}")
        root_first = {}
        for root, day in dict(spec.get("root_first") or {}).items():
            root = _block_root(root, f"{what} root_first")
            if root not in roots:
                raise ValueError(f"{what}: root_first names {root}, which is not one of its roots")
            root_first[root] = _block_date(day, f"{what} root_first {root}")
            if root_first[root] < first:
                raise ValueError(f"{what}: root_first {root} {root_first[root]} is before the block's first day")
        skip = [_block_root(r, f"{what} skip") for r in (spec.get("skip") or [])]
        if any(r not in roots for r in skip):
            raise ValueError(f"{what}: skip names a root the block does not have")
        history = spec.get("history_sessions", 0)
        if isinstance(history, bool) or not isinstance(history, int) or not 0 <= history <= HISTORY_SESSIONS:
            raise ValueError(f"{what}: history_sessions is 0-{HISTORY_SESSIONS}")
        after = spec.get("after")
        if job == "back":
            if history:
                raise ValueError(f"{what}: a back block has no history sessions")
            if isinstance(after, bool) or not isinstance(after, int):
                raise ValueError(f"{what}: a back block names the day block it follows (after)")
        elif after is not None:
            raise ValueError(f"{what}: only a back block has 'after'")
        blocks[stage] = Block(stage, what=str(spec.get("what") or ""), job=job, roots=roots, first=first, last=last,
                              root_first=root_first, skip=skip, history_sessions=history, after=after)
    for block in blocks.values():
        if block.job != "back":
            continue
        parent = blocks.get(block.after or -1)
        if parent is None or parent.job != "day":
            raise ValueError(f"block {block.stage}: after {block.after} is not a day block in the file")
        # every back root-day must be one of the parent's day root-days (checked on a weekday grid, calendar-free)
        day = block.first
        while day <= block.last:
            if day.weekday() < 5 and not set(block.day_roots(day)) <= set(parent.day_roots(day)):
                raise ValueError(f"block {block.stage}: {day} has back months for a root-day block {parent.stage} "
                                 "does not fetch")
            day += dt.timedelta(days=1)
    return blocks


def check_block_task(task: Task, core: Sequence[str] = CORE_FIVE) -> None:
    """Refuse a block task that could rewrite a file stages 1-10 own: any day on or after Train's first day (Train,
    Validation, the holdout and forward days), and the core roots' 2020-21 chains and back months (stages 9 and 10).
    An `under` task elsewhere keeps any underlying already journaled, so it may overlap a history session."""
    if task.stage < FIRST_BLOCK_STAGE:
        raise ValueError(f"{task}: stages 1-10 are not blocks")
    if task.job not in (*BLOCK_JOBS, "under"):
        raise ValueError(f"{task}: a block has day, back and under tasks only")
    if task.day >= TRAIN[0] or window_of(task.day) != "pre":
        raise ValueError(f"{task}: a block never reaches {TRAIN[0]} or later (Train, Validation, holdout, forward)")
    if task.job in BLOCK_JOBS and task.root in core and EARLY[0] <= task.day <= EARLY[1]:
        raise ValueError(f"{task}: stages 9 and 10 own the core roots' {EARLY[0]}..{EARLY[1]} chains")


def plan(
    calendar: Calendar,
    *,
    stages: Sequence[int] = (1, 2, 3, 4, 5, 6),
    names: Sequence[str] = (),
    first: Sequence[tuple[str, dt.date]] = (),
    core: Sequence[str] = CORE_FIVE,
    checks: Sequence[tuple[str, dt.date]] = (),
    forward: Sequence[dt.date] = (),
    order: Sequence[int] = (1, 2, 3, 4, 5, 6),
    early: Sequence[str] | None = None,
    blocks: Mapping[int, Block] | None = None,
) -> list[Task]:
    """Every task in the plan's order. `checks` (stage 0, job `chk`) fetch root-days for the
    agreement check into a side directory, never the store. `first` puts some root-days at the head
    (the Gym builder's sample; each in the stage its date belongs to, if that stage is planned).
    Within stage 1: 2024, then 2025, then 2023, each day across the roots, so every root grows
    together and the Gym can start on any of them. `order` is the order the stages are worked in
    (the plan's is 1..6; on Sept 26 the main session moved 5, the fill-calibration samples, ahead of 4). Stages 9 and
    10 (the 2020-21 extension) come after every stage `order` names unless it names them, 9 before 10 (a back-month
    task merges into its day's file); they need a calendar holding 2019-2021 (`calendar_years`). Stage 9 is the history
    sessions' underlying (job `under`), then the day chains; `early` (the operator's `--early-roots`) leaves roots out of
    both stages. A planned stage from 11 up is a block (`blocks`, the private file): its history sessions, then its days,
    each task checked by `check_block_task`; its years must be in the calendar, a back block must come after its day
    block, and no root-day's chain or back months is planned by two blocks."""

    def days(a: dt.date, b: dt.date) -> list[dt.date]:
        return calendar.days(a, b)

    out: list[Task] = []
    seen: set[tuple[int, str]] = set()

    def add(task: Task) -> None:
        key = (task.stage, task.id)
        if key not in seen:
            seen.add(key)
            out.append(task)

    rank = {stage: i for i, stage in enumerate([0, 7, 8, *order])}

    for item in checks:
        root, day = item[0], item[1]
        job = item[2] if len(item) > 2 else "chk"
        if calendar.is_trading(day):
            add(Task(0, job, root, day))
    if 7 in stages:  # the nightly forward day(s): every root of the universe, before anything else
        for day in forward:
            if window_of(day) != "forward":
                raise ValueError(f"{day} is not a forward day")
            if calendar.is_trading(day):
                for root in list(core) + list(names):
                    add(Task(7, "day", root, day))
    if 8 in stages:  # the forward day's back months (SPY, QQQ): a second run, once stage 7 is in
        for day in forward:
            if window_of(day) != "forward":
                raise ValueError(f"{day} is not a forward day")
            if calendar.is_trading(day):
                for root in BACK_MONTH_ROOTS:
                    add(Task(8, "back", root, day))
    for root, day in first:
        stage = stage_of(root, day, core, early, blocks)
        if stage in stages and calendar.is_trading(day):
            if stage >= FIRST_BLOCK_STAGE:
                check_block_task(Task(stage, "day", root, day), core)
            add(Task(stage, "day", root, day))
    head = len(out)  # the checks and the sample stay at the front, whatever the stage order
    if 1 in stages:
        for a, b in ((dt.date(2024, 1, 1), dt.date(2024, 12, 31)), VALIDATION, (dt.date(2023, 1, 1), dt.date(2023, 12, 31))):
            for day in days(a, b):
                for root in core:
                    add(Task(1, "day", root, day))
    if 2 in stages:
        for day in days(*HOLDOUT):
            for root in core:
                add(Task(2, "day", root, day))
    if 3 in stages:
        for day in days(TRAIN[0], dt.date(2022, 12, 31)):
            for root in core:
                add(Task(3, "day", root, day))
    if 4 in stages and names:
        for day in days(TRAIN[0], VALIDATION[1]):
            for root in names:
                add(Task(4, "day", root, day))
        for day in days(*HOLDOUT):
            for root in names:
                add(Task(4, "day", root, day))
    if 5 in stages:
        train_days = days(*TRAIN)
        for i, day in enumerate(train_days):
            if i % TQ_EVERY == 0:
                for root in core:
                    add(Task(5, "tq", root, day))
    if 6 in stages:
        for a, b in (TRAIN, VALIDATION, HOLDOUT):
            for day in days(a, b):
                for root in BACK_MONTH_ROOTS:
                    add(Task(6, "back", root, day))
    if set(stages) & set(EARLY_STAGES):
        missing = [year for year in EARLY_YEARS if not calendar.covers(year)]
        if missing:
            raise ValueError(f"the calendar lacks {', '.join(map(str, missing))} (holidays and half days): fetch it with "
                             f"calendar_years({sorted(set(stages) & set(EARLY_STAGES))}) before planning stages 9-10")
        fetched = early_roots(early, core)
    if 9 in stages:
        for day in history_days(calendar, EARLY[0]):
            for root in fetched:
                add(Task(9, "under", root, day))
        for day in days(*EARLY):
            for root in fetched:
                add(Task(9, "day", root, day))
    if 10 in stages:
        for day in days(*EARLY):
            for root in BACK_MONTH_ROOTS:
                if root in fetched:
                    add(Task(10, "back", root, day))
    wanted = sorted(s for s in set(stages) if s >= FIRST_BLOCK_STAGE)
    if wanted:
        blocks = dict(blocks or {})
        missing_blocks = [s for s in wanted if s not in blocks]
        if missing_blocks:
            raise ValueError(f"stages {missing_blocks} have no block in the blocks file")
        owners: dict[tuple[str, str, dt.date], int] = {}
        for stage in wanted:
            block = blocks[stage]
            lacking = [year for year in block.years() if not calendar.covers(year)]
            if lacking:
                raise ValueError(f"block {stage}: the calendar lacks {', '.join(map(str, lacking))}: fetch it with "
                                 "calendar_years(stages, blocks) first")
            worked = lambda s: (rank.get(s, len(rank)), s)  # noqa: E731 - unranked blocks keep stage order
            if block.job == "back" and block.after in stages and worked(block.after) >= worked(stage):
                raise ValueError(f"block {stage} (back months) must be worked after block {block.after}")
            for task in block.tasks(calendar):
                check_block_task(task, core)
                if task.job in BLOCK_JOBS:
                    owner = owners.setdefault((task.job, task.root, task.day), stage)
                    if owner != stage:
                        raise ValueError(f"{task}: blocks {owner} and {stage} both plan it")
                add(task)
    front, rest = out[:head], out[head:]
    rest.sort(key=lambda t: rank.get(t.stage, len(rank)))  # stable: each stage keeps its own order
    return front + rest


def stage_of(root: str, day: dt.date, core: Sequence[str] = CORE_FIVE, early: Sequence[str] | None = None,
             blocks: Mapping[int, Block] | None = None) -> int | None:
    """Which stage fetches this root-day's NBBO (None: no stage does). A 2020-21 day is stage 9's only for a root the
    operator's `--early-roots` (`early`) keeps. A pre-2022 root-day no fixed stage fetches goes to the first day block
    (`blocks`) that has it; a day on or after Train's first day never goes to a block."""
    fixed = _fixed_stage_of(root, day, core, early)
    if fixed is not None or day >= TRAIN[0] or not blocks:
        return fixed
    for stage in sorted(blocks):
        block = blocks[stage]
        if block.job == "day" and root in block.day_roots(day):
            return stage
    return None


def _fixed_stage_of(root: str, day: dt.date, core: Sequence[str], early: Sequence[str] | None) -> int | None:
    window = window_of(day)
    if root not in core:
        return 4 if window in ("train", "validation", "holdout") else None
    if EARLY[0] <= day <= EARLY[1]:
        return 9 if root in early_roots(early, core) else None
    if window == "holdout":
        return 2
    if window == "train" and day.year == 2022:
        return 3
    if window in ("train", "validation") and day.year >= 2023:
        return 1
    return None


# ------------------------------------------------------------------------------ journal
def sha256_file(path: str | os.PathLike[str]) -> tuple[str, int]:
    digest, size = hashlib.sha256(), 0
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
            size += len(block)
    return digest.hexdigest(), size


class Journal:
    """The backfill's append-only record: one JSON line per finished task and per file written.

    `manifest.parquet` is compiled from it (the last row per file wins). A task is done when its
    line is here; a crash between a file's rename and its line redoes the task, which rewrites
    the same file. Lines are flushed and fsynced one at a time.
    """

    def __init__(self, path: str | os.PathLike[str]):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, record: Mapping[str, Any]) -> None:
        line = json.dumps(dict(record), sort_keys=True, default=str)
        with open(self.path, "a+b") as handle:
            # A torn last line (a crash mid-write) is closed off first, so it costs only itself.
            if handle.tell() > 0:
                handle.seek(-1, os.SEEK_END)
                if handle.read(1) != b"\n":
                    handle.write(b"\n")
            handle.write(line.encode("utf-8") + b"\n")
            handle.flush()
            os.fsync(handle.fileno())

    def records(self) -> Iterator[dict[str, Any]]:
        try:
            handle = open(self.path, encoding="utf-8")
        except FileNotFoundError:
            return
        with handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except ValueError:
                    continue  # a torn last line from a crash
                if isinstance(row, dict):
                    yield row

    def done(self) -> dict[str, dict[str, Any]]:
        """Finished tasks by `stage:id`, the last record winning; an `invalidated` record (a task whose
        result was wrong, e.g. fetched under the wrong root) makes it pending again."""
        out: dict[str, dict[str, Any]] = {}
        for row in self.records():
            if row.get("type") != "task":
                continue
            key = f"{row.get('stage')}:{row.get('task')}"
            if row.get("status") in ("ok", "empty"):
                out[key] = row
            elif row.get("status") == "invalidated":
                out.pop(key, None)
        return out

    def files(self) -> dict[str, dict[str, Any]]:
        """The manifest: the last record for each file path, dropping files later removed."""
        out: dict[str, dict[str, Any]] = {}
        for row in self.records():
            if row.get("type") == "file":
                out[str(row["path"])] = row
            elif row.get("type") == "removed":
                out.pop(str(row.get("path")), None)
        return out


def pending(tasks: Sequence[Task], journal: Journal) -> list[Task]:
    done = journal.done()
    return [t for t in tasks if f"{t.stage}:{t.id}" not in done]


def file_record(kind: str, root: str, day: dt.date, *, rows: int, sha256: str, size: int,
                source: str, fetched_at: str) -> dict[str, Any]:
    return {
        "type": "file",
        "path": rel_path(kind, root, day),
        "kind": kind,
        "root": root,
        "date": day.isoformat(),
        "rows": int(rows),
        "sha256": sha256,
        "bytes": int(size),
        "window": window_of(day),
        "fetched_at": fetched_at,
        "source": source,
    }


# ------------------------------------------------------------------------------ progress
def summarize(tasks: Sequence[Task], journal: Journal) -> dict[str, Any]:
    """Counts by stage (planned, done, empty, failed) and underlying-days by window and root."""
    done = journal.done()
    failed: dict[str, int] = {}
    for row in journal.records():
        if row.get("type") == "task" and row.get("status") == "error":
            failed[f"{row.get('stage')}:{row.get('task')}"] = failed.get(f"{row.get('stage')}:{row.get('task')}", 0) + 1
    stages: dict[int, dict[str, int]] = {}
    for task in tasks:
        row = stages.setdefault(task.stage, {"planned": 0, "done": 0, "empty": 0, "failing": 0})
        row["planned"] += 1
        record = done.get(f"{task.stage}:{task.id}")
        if record:
            row["done"] += 1
            if record.get("status") == "empty":
                row["empty"] += 1
        elif f"{task.stage}:{task.id}" in failed:
            row["failing"] += 1
    by_window: dict[str, dict[str, int]] = {}
    for path, row in journal.files().items():
        if row.get("kind") != "nbbo":
            continue
        cell = by_window.setdefault(str(row.get("window")), {})
        cell[str(row.get("root"))] = cell.get(str(row.get("root")), 0) + 1
    return {"stages": {str(k): v for k, v in sorted(stages.items())}, "underlying_days": by_window}


def eta_hours(remaining: int, rate_per_hour: float) -> float | None:
    if rate_per_hour <= 0:
        return None
    return round(remaining / rate_per_hour, 2)


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
