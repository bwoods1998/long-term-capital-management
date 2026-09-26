"""The Gym store's fixed layout and the backfill's plan, standard library only.

The store (v1) is fixed by the options-swarm plan (`docs/goals/LTCM_OPTIONS_SWARM.md`, "The Gym").
This module holds everything about it that needs no third-party package: the windows, the trading
calendar arithmetic, the file paths, the backfill's stages and their order, the per-root strike
judgement, and the manifest journal. The Parquet writing lives in `frames.py` (polars and pyarrow)
and the ThetaData calls in `backfill.py`; both run on the data box.

Nothing here reads a key, a quote or a price. Dates appear only in paths and in the manifest.
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

#: Strikes per side of the money that the one-minute NBBO keeps (ThetaData `strike_range`). The
#: index roots with $5 strikes near the money get more, so the band covers a similar distance.
DEFAULT_STRIKE_RANGE = 25
STRIKE_RANGE = {"SPXW": 40}
#: Days to expiry the NBBO keeps, and the back months for calendars (SPY, QQQ).
MAX_DTE = 14
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


def window_of(day: dt.date) -> str:
    if day < TRAIN[0]:
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
#: `tq` = the trade_quote sample; `back` = the 15-45 DTE back months merged into the day's NBBO.
JOBS = ("day", "tq", "back", "chk", "chk1s")

STAGES: dict[int, str] = {
    1: "core five, 2023-2025 (Train's later part and Validation)",
    2: "core five holdout, 2026-01-02..2026-09-25 (gate image only)",
    3: "core five, 2022",
    4: "the 20 names over Train + Validation, then their holdout",
    5: "trade_quote calibration samples: core five, Train days, one in five, 0-7 DTE, 10 strikes",
    6: "back months to 45 DTE, SPY and QQQ",
    7: "forward: the previous trading day for the whole universe (the nightly job)",
    8: "forward: that day's back months to 45 DTE, SPY and QQQ (the nightly job, after stage 7)",
}


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
) -> list[Task]:
    """Every task in the plan's order. `checks` (stage 0, job `chk`) fetch root-days for the
    agreement check into a side directory, never the store. `first` puts some root-days at the head
    (the Gym builder's sample; each in the stage its date belongs to, if that stage is planned).
    Within stage 1: 2024, then 2025, then 2023, each day across the roots, so every root grows
    together and the Gym can start on any of them. `order` is the order the stages are worked in
    (the plan's is 1..6; on Sept 26 the main session moved 5, the fill-calibration samples, ahead of 4)."""

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
        stage = stage_of(root, day, core)
        if stage in stages and calendar.is_trading(day):
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
    front, rest = out[:head], out[head:]
    rest.sort(key=lambda t: rank.get(t.stage, len(rank)))  # stable: each stage keeps its own order
    return front + rest


def stage_of(root: str, day: dt.date, core: Sequence[str] = CORE_FIVE) -> int | None:
    """Which stage fetches this root-day's NBBO (None: no stage does)."""
    window = window_of(day)
    if root not in core:
        return 4 if window in ("train", "validation", "holdout") else None
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
