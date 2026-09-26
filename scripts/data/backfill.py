#!/usr/bin/env python3
"""The Gym store's backfill, run ON the data box (`/data/code/backfill.py`, Python 3.12 venv).

    backfill.py probe                          authenticate, one small request, print shapes (no key)
    backfill.py run [--stages 1,2,...] [--first SPY:2024-03-13,...] [--names-file F]
                                               work the plan's queue until it is empty; resumable
    backfill.py status                         the queue by stage, underlying-days, rate and ETAs
    backfill.py compile                        VERSION, calendar, expiries and manifest from the journal
    backfill.py prune --keep train,validation [--drop-key] [--drop-work]
                                               delete other windows' files (a Gym image fork)
    backfill.py adopt --records F              take files a nightly copy put in place (gate image)
    backfill.py verify                         every file's sha256 against the journal

Concurrency: ThetaData allows four requests at once, account-wide. `/data/work/slots` (a number,
re-read every few seconds) sets how many of them this process uses, so the universe screen can
borrow one without a restart. Every file is written atomically and journaled with its sha256
(`/data/work/journal.jsonl`); `manifest.parquet` is compiled from the journal. A task already in
the journal is never fetched again, so a restart continues where the last run stopped.

The key is read from `/data/secrets/thetadata.env` (mode 0600) and passed to the library as an
argument: it is never put in the environment, a log line or an exception.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import os
import queue
import shutil
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import storelib as sl  # noqa: E402

log = logging.getLogger("backfill")

RETRYABLE = ("UNAVAILABLE", "RESOURCE_EXHAUSTED", "DEADLINE_EXCEEDED", "INTERNAL", "UNKNOWN", "ABORTED", "CANCELLED")


# ------------------------------------------------------------------------------ the key and the client
def read_key(path: str = sl.KEY_PATH) -> str:
    """THETADATA_API_KEY from the box's env file. Refuses a file others can read."""
    target = Path(path)
    mode = target.stat().st_mode & 0o777
    if mode & 0o077:
        raise SystemExit(f"{path} is readable by others (mode {oct(mode)}); fix it to 0600")
    for line in target.read_text(encoding="utf-8").splitlines():
        name, _, value = line.partition("=")
        if name.strip() == "THETADATA_API_KEY" and value.strip():
            return value.strip()
    raise SystemExit(f"no THETADATA_API_KEY in {path}")


def open_client(key_path: str = sl.KEY_PATH) -> Any:
    logging.getLogger("thetadata").setLevel(logging.WARNING)  # its INFO line echoes the session
    from thetadata import ThetaClient

    return ThetaClient(api_key=read_key(key_path), dotenv_path="/nonexistent")


def raw_client(client: Any) -> Any:
    """A second client on the same session whose calls return the raw response chunks, so the
    slot is released as soon as the bytes are in and the decoding happens elsewhere."""
    from thetadata import ThetaClient

    class RawThetaClient(ThetaClient):
        def _convert_response_stream(self, response_stream: Any) -> Any:
            return [(int(r.compression_description.algo), bytes(r.compressed_data)) for r in response_stream]

    return RawThetaClient(existing_authorized_client=client)


def decode(chunks: Sequence[tuple[int, bytes]]) -> Any:
    """Raw chunks -> a polars frame, with the library's own conversion."""
    from types import SimpleNamespace

    from thetadata.client import ThetaClient

    stream = [SimpleNamespace(compression_description=SimpleNamespace(algo=algo), compressed_data=data)
              for algo, data in chunks]
    return ThetaClient._convert_response_stream(SimpleNamespace(dataframe_type="polars"), stream)


#: A process pool for decoding and writing the big frames (set by the runner; None = inline).
POOL: Any = None


def _offload(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    if POOL is None:
        return fn(*args, **kwargs)
    return POOL.submit(fn, *args, **kwargs).result()


def build_nbbo(chunks: Sequence[tuple[int, bytes]], day: dt.date, target: str, *, open_min: int, close_min: int,
               max_dte: int, min_dte: int = 0, merge_with: str | None = None) -> dict[str, Any]:
    """Decode quote chunks, normalize, optionally merge into an existing day file, write. In a worker."""
    import frames as fr
    import polars as pl

    parts, stats = [], {"raw": 0, "kept": 0}
    for group in _split_groups(chunks):
        raw = decode(group)
        frame, part_stats = fr.nbbo(raw, day, open_min=open_min, close_min=close_min, max_dte=max_dte, min_dte=min_dte)
        for key, value in part_stats.items():
            stats[key] = stats.get(key, 0) + value
        if frame.height:
            parts.append(frame)
    if not parts:
        return {"rows": 0, "stats": stats}
    frame = pl.concat(parts) if len(parts) > 1 else parts[0]
    if merge_with:
        frame = fr.merge_nbbo(pl.read_parquet(merge_with), frame)
    elif len(parts) > 1:
        frame = frame.sort(fr.CONTRACT_KEY + ["minute"])
    rows, digest, size = fr.write(frame, target)
    return {"rows": rows, "sha256": digest, "bytes": size, "stats": stats}


def build_tq(chunks: Sequence[tuple[int, bytes]], day: dt.date, target: str, *, max_dte: int) -> dict[str, Any]:
    import frames as fr

    frame = fr.trade_quote(decode(chunks), day, max_dte=max_dte)
    if not frame.height:
        return {"rows": 0}
    rows, digest, size = fr.write(frame, target)
    return {"rows": rows, "sha256": digest, "bytes": size}


def _split_groups(chunks: Sequence[Any]) -> list[Sequence[Any]]:
    """Several responses (a list of chunk lists) or one response (a chunk list)."""
    if chunks and isinstance(chunks[0], list):
        return list(chunks)
    return [chunks]


class Limiter:
    """A semaphore whose size can change while it is held (`/data/work/slots`)."""

    def __init__(self, limit: int, slots_file: str | None = None):
        self.limit = max(0, int(limit))
        self.slots_file = slots_file
        self.used = 0
        self.cond = threading.Condition()
        self._checked = 0.0

    def _refresh(self) -> None:
        if not self.slots_file or time.monotonic() - self._checked < 5:
            return
        self._checked = time.monotonic()
        try:
            value = int(Path(self.slots_file).read_text().strip())
        except (OSError, ValueError):
            return
        self.limit = max(0, min(4, value))

    def __enter__(self) -> "Limiter":
        with self.cond:
            while True:
                self._refresh()
                if self.used < self.limit:
                    self.used += 1
                    return self
                self.cond.wait(timeout=5)

    def __exit__(self, *exc: Any) -> None:
        with self.cond:
            self.used -= 1
            self.cond.notify_all()


class Theta:
    """ThetaData calls through the limiter, with retries and one re-authentication on expiry."""

    def __init__(self, factory: Callable[[], Any], limiter: Limiter, *, attempts: int = 6,
                 sleep: Callable[[float], None] = time.sleep):
        self.factory = factory
        self.client = factory()
        self.raw = None
        self.limiter = limiter
        self.attempts = attempts
        self.sleep = sleep
        self.lock = threading.Lock()
        self.requests = 0
        self.seconds = 0.0
        self.by_method: dict[str, list[float]] = {}

    def call_raw(self, method: str, *args: Any, **kwargs: Any) -> Any:
        """The response's raw chunks (decode later with `decode`), or None for no data."""
        return self.call(method, *args, _raw=True, **kwargs)

    def _raw_client(self, client: Any) -> Any:
        with self.lock:
            if self.raw is None or self.raw[0] is not client:
                self.raw = (client, raw_client(client))
            return self.raw[1]

    def call(self, method: str, *args: Any, _raw: bool = False, **kwargs: Any) -> Any:
        """The frame, or None when ThetaData has no data for the request."""
        delay = 2.0
        for attempt in range(1, self.attempts + 1):
            client = self.client
            target = self._raw_client(client) if _raw else client
            try:
                with self.limiter:
                    started = time.monotonic()
                    try:
                        return getattr(target, method)(*args, **kwargs)
                    finally:
                        with self.lock:
                            took = time.monotonic() - started
                            self.requests += 1
                            self.seconds += took
                            cell = self.by_method.setdefault(method, [0, 0.0])
                            cell[0] += 1
                            cell[1] += took
            except Exception as error:  # noqa: BLE001 - classified below
                name = type(error).__name__
                if name == "NoDataFoundError":
                    return None
                code = _grpc_code(error)
                if code == "UNAUTHENTICATED" or name == "AuthenticationError":
                    with self.lock:
                        if self.client is client:
                            log.warning("re-authenticating after %s", code or name)
                            self.client = self.factory()
                elif code == "NOT_FOUND":
                    return None
                elif code == "INVALID_ARGUMENT" or (code and code not in RETRYABLE):
                    raise
                if attempt == self.attempts:
                    raise
                log.warning("%s attempt %d failed (%s %s); retrying in %.0fs", method, attempt, name, code, delay)
                self.sleep(delay)
                delay = min(delay * 2, 120.0)
        return None  # pragma: no cover


def _grpc_code(error: Exception) -> str | None:
    code = getattr(error, "code", None)
    if callable(code):
        try:
            value = code()
            return getattr(value, "name", str(value))
        except Exception:  # noqa: BLE001
            return None
    return None


# ------------------------------------------------------------------------------ the store
class Store:
    def __init__(self, root: str = sl.STORE_ROOT, work: str = sl.WORK_ROOT):
        self.root = Path(root)
        self.work = Path(work)
        self.journal = sl.Journal(self.work / "journal.jsonl")

    def path(self, kind: str, root: str, day: dt.date) -> Path:
        return self.root / sl.rel_path(kind, root, day)

    def expiries_path(self, root: str, day: dt.date) -> Path:
        return self.work / "expiries" / root / f"{day.isoformat()}.json"

    def save_expiries(self, root: str, day: dt.date, expiries: Sequence[dt.date]) -> None:
        target = self.expiries_path(root, day)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(target.name + ".tmp")
        tmp.write_text(json.dumps([d.isoformat() for d in expiries]))
        os.replace(tmp, target)

    def load_expiries(self, root: str, day: dt.date) -> list[dt.date] | None:
        try:
            return [dt.date.fromisoformat(x) for x in json.loads(self.expiries_path(root, day).read_text())]
        except (OSError, ValueError):
            return None

    def calendar(self, client: Any | None = None, years: Sequence[int] = (2022, 2023, 2024, 2025, 2026, 2027)) -> sl.Calendar:
        cache = self.work / "calendar.json"
        try:
            data = json.loads(cache.read_text())
            # A sealed box (no client) takes what is cached; the data box refreshes a short cache.
            if client is None or all(str(y) in data.get("years", []) for y in years):
                return sl.Calendar.from_json(data["exceptions"])
        except (OSError, ValueError, KeyError):
            pass
        if client is None:
            raise SystemExit("no calendar cached and no client to fetch it")
        rows: list[dict[str, Any]] = []
        for year in years:
            frame = client.call("calendar_year", str(year))
            if frame is not None:
                rows.extend(frame.to_dicts())
        calendar = sl.Calendar.from_rows(rows)
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps({"years": [str(y) for y in years], "exceptions": calendar.to_json()}))
        return calendar


# ------------------------------------------------------------------------------ the jobs
def _hms(minute: int) -> str:
    return f"{minute // 60:02d}:{minute % 60:02d}:00"


class Listings:
    """One `option_list_contracts` request per (day, group of roots) instead of one per root-day.

    `peers(task)` names the roots fetched together with a task's root (the other roots of its stage
    on that day). The first task of a day fetches for the group; the others wait for it and read
    the cache. A root the group request did not return is fetched on its own, so nothing is lost.
    """

    def __init__(self, peers: Callable[[sl.Task], Sequence[str]] | None = None, keep_days: int = 64):
        self.peers = peers
        self.keep_days = keep_days
        self.cache: dict[tuple[dt.date, int], dict[str, list[dt.date]]] = {}
        self.locks: dict[tuple[dt.date, int], threading.Lock] = {}
        self.guard = threading.Lock()

    def expiries(self, task: sl.Task, theta: "Theta", max_dte: int) -> list[dt.date]:
        import frames as fr

        group = sorted(set(self.peers(task)) | {task.root}) if self.peers else [task.root]
        if len(group) == 1:
            listed = theta.call("option_list_contracts", "quote", task.day, task.root, max_dte=max_dte)
            return fr.expirations(listed, task.day, max_dte=max_dte) if listed is not None else []
        key = (task.day, task.stage)
        with self.guard:
            lock = self.locks.setdefault(key, threading.Lock())
        with lock:
            if key not in self.cache:
                listed = theta.call("option_list_contracts", "quote", task.day, group, max_dte=max_dte)
                by_root: dict[str, list[dt.date]] = {root: [] for root in group}
                if listed is not None and listed.height:
                    for (root,), part in listed.group_by(["symbol"]):
                        by_root[str(root)] = fr.expirations(part, task.day, max_dte=max_dte)
                with self.guard:
                    self.cache[key] = by_root
                    if len(self.cache) > self.keep_days:
                        for old in sorted(self.cache)[: len(self.cache) - self.keep_days]:
                            self.cache.pop(old, None)
                            self.locks.pop(old, None)
            found = self.cache.get(key, {}).get(task.root)
        if found:
            return found
        listed = theta.call("option_list_contracts", "quote", task.day, task.root, max_dte=max_dte)
        return fr.expirations(listed, task.day, max_dte=max_dte) if listed is not None else []


#: The runner's listing cache (set by `run`; None fetches per root).
LISTINGS: Listings | None = None


def run_task(task: sl.Task, theta: Theta, store: Store, calendar: sl.Calendar) -> dict[str, Any]:
    """Do one task; journal its files; return the task record (not yet journaled)."""
    import frames as fr  # polars, on the box

    hours = calendar.hours(task.day)
    if hours is None:
        return {"status": "empty", "why": "not a trading day"}
    open_min, close_min = hours
    window = dict(start_time=_hms(open_min), end_time=_hms(close_min))
    fetched = sl.utc_now()
    written: list[dict[str, Any]] = []
    rng = sl.strike_range(task.root)

    def put(kind: str, frame: Any, source: str) -> None:
        rows, digest, size = fr.write(frame, store.path(kind, task.root, task.day))
        record = sl.file_record(kind, task.root, task.day, rows=rows, sha256=digest, size=size,
                                source=source, fetched_at=fetched)
        written.append(record)

    if task.job == "day":
        expiries = (LISTINGS or Listings()).expiries(task, theta, sl.EXPIRY_LIST_DTE)
        if not expiries:
            return {"status": "empty", "why": "no contracts quoted"}
        store.save_expiries(task.root, task.day, expiries)
        source = f"thetadata option_history_quote 1m exp=* max_dte={sl.MAX_DTE} strike_range={rng}"
        try:
            chunks = theta.call_raw("option_history_quote", task.root, "*", interval="1m", date=task.day,
                                    strike_range=rng, max_dte=sl.MAX_DTE, **window)
        except Exception as error:  # noqa: BLE001 - one server-side defect has been seen (XSP 2022-06-29)
            if _grpc_code(error) != "INVALID_ARGUMENT":
                raise
            # ThetaData answered the bulk request with "Wrong number of data fields": ask expiry by
            # expiry, and keep what each answers; an expiry that still fails is recorded, not faked.
            log.warning("%s: bulk quote refused (%s); fetching by expiry", task.id, str(error)[:120])
            chunks, refused = [], []
            for expiry in [e for e in expiries if (e - task.day).days <= sl.MAX_DTE]:
                try:
                    part = theta.call_raw("option_history_quote", task.root, expiry, interval="1m", date=task.day,
                                          strike_range=rng, **window)
                except Exception as inner:  # noqa: BLE001
                    if _grpc_code(inner) != "INVALID_ARGUMENT":
                        raise
                    refused.append(expiry.isoformat())
                    continue
                if part:
                    chunks.append(part)
            source = (f"thetadata option_history_quote 1m by expiry (bulk refused) max_dte={sl.MAX_DTE} strike_range={rng}"
                      + (f"; refused expiries {','.join(refused)}" if refused else ""))
        stats: dict[str, int] = {}
        if chunks:
            built = _offload(build_nbbo, chunks, task.day, str(store.path("nbbo", task.root, task.day)),
                             open_min=open_min, close_min=close_min, max_dte=sl.MAX_DTE)
            del chunks
            stats = built["stats"]
            if built["rows"]:
                written.append(sl.file_record("nbbo", task.root, task.day, rows=built["rows"], sha256=built["sha256"],
                                              size=built["bytes"], fetched_at=fetched, source=source))
        under = None
        for expiry in [e for e in expiries if e >= task.day][:3]:
            # Calls only: the same underlying series at half the request time (measured Sept 26).
            greeks = theta.call("option_history_greeks_first_order", task.root, expiry, interval="1m",
                                date=task.day, strike_range=1, right="call", **window)
            if greeks is not None:
                under = fr.underlying(greeks, open_min=open_min, close_min=close_min)
                if under.height:
                    put("underlying", under, f"thetadata option_history_greeks_first_order underlying_price exp={expiry.isoformat()} strike_range=1 calls")
                    break
        oi = theta.call("option_history_open_interest", task.root, "*", date=task.day, max_dte=sl.MAX_DTE, strike_range=rng)
        if oi is not None:
            oi_frame = fr.open_interest(oi, task.day, max_dte=sl.MAX_DTE)
            if oi_frame.height:
                put("oi", oi_frame, f"thetadata option_history_open_interest exp=* max_dte={sl.MAX_DTE} strike_range={rng}")
        for record in written:
            store.journal.append(record)
        kinds = [r["kind"] for r in written]
        return {"status": "ok" if "nbbo" in kinds else "empty", "files": kinds, "expiries": len(expiries),
                "nbbo": stats, "why": None if "nbbo" in kinds else "no NBBO rows"}

    if task.job == "chk":
        # The agreement check's contracts: the day's NBBO into a side directory, never the store.
        chunks = theta.call_raw("option_history_quote", task.root, "*", interval="1m", date=task.day,
                                strike_range=rng, max_dte=sl.MAX_DTE, **window)
        if not chunks:
            return {"status": "empty", "why": "no quotes"}
        target = store.work / "check-store" / sl.rel_path("nbbo", task.root, task.day)
        built = _offload(build_nbbo, chunks, task.day, str(target), open_min=open_min, close_min=close_min, max_dte=sl.MAX_DTE)
        return {"status": "ok" if built["rows"] else "empty", "rows": built["rows"], "side": str(target)}

    if task.job == "chk1s":
        # The sharper agreement check: one-second NBBO for the next three expiries, 12:25-16:00 ET,
        # 15 strikes a side, into a side directory (never the store).
        import frames as fr
        import polars as pl

        listed = theta.call("option_list_contracts", "quote", task.day, task.root, max_dte=10)
        expiries = [e for e in (fr.expirations(listed, task.day, max_dte=10) if listed is not None else []) if e > task.day][:3]
        parts = []
        for expiry in expiries:
            raw = theta.call("option_history_quote", task.root, expiry, interval="1s", date=task.day, strike_range=15,
                             start_time="12:25:00", end_time=_hms(close_min))
            if raw is None or not raw.height:
                continue
            ts = pl.col("timestamp")
            parts.append(raw.select(
                fr._expiration().alias("expiration"), pl.col("strike").cast(pl.Float64), fr._right().alias("right"),
                (ts.dt.hour().cast(pl.Int32) * 3600 + ts.dt.minute().cast(pl.Int32) * 60 + ts.dt.second().cast(pl.Int32)).alias("second_of_day"),
                pl.col("bid").cast(pl.Float64), pl.col("ask").cast(pl.Float64)))
        if not parts:
            return {"status": "empty", "why": "no one-second quotes"}
        target = store.work / "check-store-1s" / task.root / f"{task.day.isoformat()}.parquet"
        rows, _, _ = fr.write(pl.concat(parts), target)
        return {"status": "ok", "rows": rows, "expiries": [e.isoformat() for e in expiries], "side": str(target)}

    if task.job == "tq":
        chunks = theta.call_raw("option_history_trade_quote", task.root, "*", date=task.day, max_dte=sl.TQ_MAX_DTE,
                                strike_range=sl.TQ_STRIKE_RANGE, exclusive=True, **window)
        if not chunks:
            return {"status": "empty", "why": "no trades"}
        built = _offload(build_tq, chunks, task.day, str(store.path("trade_quote", task.root, task.day)), max_dte=sl.TQ_MAX_DTE)
        if not built["rows"]:
            return {"status": "empty", "why": "no trades in 0-7 DTE"}
        written.append(sl.file_record("trade_quote", task.root, task.day, rows=built["rows"], sha256=built["sha256"],
                                      size=built["bytes"], fetched_at=fetched,
                                      source=f"thetadata option_history_trade_quote exclusive max_dte={sl.TQ_MAX_DTE} strike_range={sl.TQ_STRIKE_RANGE}"))
        for record in written:
            store.journal.append(record)
        return {"status": "ok", "files": ["trade_quote"], "rows": built["rows"]}

    if task.job == "back":
        target = store.path("nbbo", task.root, task.day)
        expiries = store.load_expiries(task.root, task.day)
        if expiries is None or not target.exists():
            raise RuntimeError("the day's NBBO is not in the store yet (stage 1-3 first)")
        far = [e for e in expiries if sl.MAX_DTE < (e - task.day).days <= sl.BACK_MONTH_DTE]
        groups = []
        for expiry in far:
            chunks = theta.call_raw("option_history_quote", task.root, expiry, interval="1m", date=task.day,
                                    strike_range=rng, **window)
            if chunks:
                groups.append(chunks)
        if groups:
            built = _offload(build_nbbo, groups, task.day, str(target), open_min=open_min, close_min=close_min,
                             max_dte=sl.BACK_MONTH_DTE, min_dte=sl.MAX_DTE + 1, merge_with=str(target))
            if built["rows"]:
                written.append(sl.file_record("nbbo", task.root, task.day, rows=built["rows"], sha256=built["sha256"],
                                              size=built["bytes"], fetched_at=fetched,
                                              source=f"thetadata option_history_quote 1m max_dte={sl.MAX_DTE} strike_range={rng} + back months to {sl.BACK_MONTH_DTE} DTE by expiry"))
        oi = theta.call("option_history_open_interest", task.root, "*", date=task.day, max_dte=sl.BACK_MONTH_DTE, strike_range=rng)
        if oi is not None:
            oi_frame = fr.open_interest(oi, task.day, max_dte=sl.BACK_MONTH_DTE)
            if oi_frame.height:
                put("oi", oi_frame, f"thetadata option_history_open_interest exp=* max_dte={sl.BACK_MONTH_DTE} strike_range={rng}")
        for record in written:
            store.journal.append(record)
        return {"status": "ok", "files": [r["kind"] for r in written], "back_expiries": len(far)}

    raise ValueError(f"unknown job {task.job}")


# ------------------------------------------------------------------------------ the runner
class Runner:
    def __init__(self, tasks: Sequence[sl.Task], theta: Theta, store: Store, calendar: sl.Calendar, *,
                 threads: int = 4, max_failures: int = 3, progress_every: float = 20.0,
                 task_fn: Callable[..., dict[str, Any]] = run_task):
        self.tasks = list(tasks)
        self.theta = theta
        self.store = store
        self.calendar = calendar
        self.threads = threads
        self.max_failures = max_failures
        self.progress_every = progress_every
        self.task_fn = task_fn
        self.started = time.time()
        self.finished: list[tuple[float, sl.Task, str]] = []
        self.failures: dict[str, int] = {}
        self.in_flight: dict[str, float] = {}
        self.last_error: str | None = None
        self.lock = threading.Lock()
        self.stop = threading.Event()

    def _work(self, jobs: "queue.Queue[sl.Task | None]", retry: list[sl.Task]) -> None:
        while not self.stop.is_set():
            task = jobs.get()
            if task is None:
                return
            key = f"{task.stage}:{task.id}"
            with self.lock:
                self.in_flight[key] = time.time()
            began = time.time()
            try:
                record = self.task_fn(task, self.theta, self.store, self.calendar)
                status = record.get("status", "ok")
            except Exception as error:  # noqa: BLE001 - journaled and retried
                status, record = "error", {"error": f"{type(error).__name__}: {str(error)[:300]}"}
                with self.lock:
                    self.failures[key] = self.failures.get(key, 0) + 1
                    self.last_error = f"{key} {record['error']}"
                    if self.failures[key] < self.max_failures:
                        retry.append(task)
                log.error("task %s failed: %s\n%s", key, record["error"], traceback.format_exc(limit=3))
            self.store.journal.append({"type": "task", "stage": task.stage, "task": task.id, "status": status,
                                       "window": task.window, "seconds": round(time.time() - began, 2),
                                       "at": sl.utc_now(), **{k: v for k, v in record.items() if k != "status"}})
            with self.lock:
                self.in_flight.pop(key, None)
                self.finished.append((time.time(), task, status))

    def progress(self) -> dict[str, Any]:
        now = time.time()
        with self.lock:
            recent = [f for f in self.finished if now - f[0] <= 1800]
            finished = list(self.finished)
            in_flight = sorted(self.in_flight)
        span = min(1800.0, max(60.0, now - self.started))
        day_recent = [f for f in recent if f[1].job == "day" and f[2] in ("ok", "empty")]
        rate = len([f for f in recent if f[2] in ("ok", "empty")]) * 3600.0 / span
        day_rate = len(day_recent) * 3600.0 / span
        summary = sl.summarize(self.tasks, self.store.journal)
        etas, cumulative = {}, 0
        worked: list[str] = []
        for task in self.tasks:  # the order the stages are worked in
            if str(task.stage) not in worked:
                worked.append(str(task.stage))
        for stage in worked:
            row = summary["stages"][stage]
            cumulative += row["planned"] - row["done"]
            etas[stage] = {"remaining": row["planned"] - row["done"],
                           "hours_to_finish": sl.eta_hours(cumulative, rate)}
        return {
            "at": sl.utc_now(), "pid": os.getpid(), "started_at": dt.datetime.fromtimestamp(self.started, dt.timezone.utc).isoformat(),
            "finished_this_run": len(finished), "tasks_per_hour": round(rate, 1), "underlying_days_per_hour": round(day_rate, 1),
            "slots": self.theta.limiter.limit, "requests": self.theta.requests,
            "request_seconds": round(self.theta.seconds, 1),
            "by_method": {m: {"n": int(v[0]), "mean_s": round(v[1] / max(1, v[0]), 2)} for m, v in self.theta.by_method.items()},
            "in_flight": in_flight, "last_error": self.last_error,
            "stages": summary["stages"], "eta": etas, "underlying_days": summary["underlying_days"],
        }

    def write_progress(self) -> None:
        target = self.store.work / "progress.json"
        tmp = target.with_name("progress.json.tmp")
        tmp.write_text(json.dumps(self.progress(), indent=1, default=str))
        os.replace(tmp, target)

    def run(self) -> int:
        # Temporary files a killed run left behind (a rename that never happened) are deleted.
        for stale in self.store.root.glob("*/*/.*.tmp-*"):
            try:
                stale.unlink()
            except OSError:
                pass
        todo = sl.pending(self.tasks, self.store.journal)
        log.info("plan: %d tasks, %d pending", len(self.tasks), len(todo))
        rounds = 0
        while todo and not self.stop.is_set():
            rounds += 1
            jobs: "queue.Queue[sl.Task | None]" = queue.Queue()
            for task in todo:
                jobs.put(task)
            for _ in range(self.threads):
                jobs.put(None)
            retry: list[sl.Task] = []
            workers = [threading.Thread(target=self._work, args=(jobs, retry), daemon=True) for _ in range(self.threads)]
            for worker in workers:
                worker.start()
            while any(w.is_alive() for w in workers):
                for worker in workers:
                    worker.join(timeout=self.progress_every / max(1, len(workers)))
                try:
                    self.write_progress()
                except Exception as error:  # noqa: BLE001 - progress is informative
                    log.warning("progress not written: %s", error)
            todo = sorted(retry, key=lambda t: (t.stage, self.tasks.index(t)))
            if todo:
                log.info("round %d done; %d tasks to retry", rounds, len(todo))
        compile_store(self.store, self.calendar)
        self.write_progress()
        log.info("queue empty after %d rounds", rounds)
        return 0


# ------------------------------------------------------------------------------ compile, prune, adopt
def compile_store(store: Store, calendar: sl.Calendar, *, windows: Sequence[str] | None = None) -> dict[str, int]:
    """VERSION, calendar.parquet, expiries.parquet and manifest.parquet, from the journal."""
    import frames as fr

    store.root.mkdir(parents=True, exist_ok=True)
    (store.root / "VERSION").write_text(sl.STORE_VERSION + "\n")
    files = [r for r in store.journal.files().values() if windows is None or r.get("window") in windows]
    files = [r for r in files if (store.root / r["path"]).exists()]
    days = sorted({sl.as_date(r["date"]) for r in files})
    cal_rows = []
    if days:
        for day in calendar.days(min(sl.TRAIN[0], days[0]), days[-1]):
            if windows is None or sl.window_of(day) in windows:
                hours = calendar.hours(day)
                cal_rows.append((day, hours[0], hours[1]))
    fr.write(fr.calendar_frame(cal_rows), store.root / "calendar.parquet")
    exp_rows = []
    base = store.work / "expiries"
    if base.exists():
        for root_dir in sorted(p for p in base.iterdir() if p.is_dir()):
            for path in sorted(root_dir.glob("*.json")):
                day = dt.date.fromisoformat(path.stem)
                if windows is not None and sl.window_of(day) not in windows:
                    continue
                for expiry in json.loads(path.read_text()):
                    exp_rows.append((root_dir.name, day, dt.date.fromisoformat(expiry)))
    fr.write(fr.expiries_frame(exp_rows), store.root / "expiries.parquet")
    fr.write(fr.manifest_frame(files), store.root / "manifest.parquet")
    return {"files": len(files), "calendar_days": len(cal_rows), "expiry_rows": len(exp_rows)}


def export_subset(store: Store, out_root: Path, roots: Sequence[str], days: Sequence[dt.date],
                  calendar: sl.Calendar, kinds: Sequence[str] = ("nbbo", "underlying", "oi")) -> dict[str, Any]:
    """Copy some root-days into a new store-layout directory with their own calendar, expiries and
    manifest (the Gym builder's laptop sample). Only Train/Validation days may leave this way."""
    import frames as fr

    for day in days:
        if sl.window_of(day) not in ("train", "validation"):
            raise SystemExit(f"{day} is not Train or Validation; a sample never carries the holdout")
    files = [r for r in store.journal.files().values()
             if r["root"] in roots and sl.as_date(r["date"]) in set(days) and r["kind"] in kinds]
    out_root.mkdir(parents=True, exist_ok=True)
    (out_root / "VERSION").write_text(sl.STORE_VERSION + "\n")
    for record in files:
        target = out_root / record["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(store.root / record["path"], target)
    present = sorted({sl.as_date(r["date"]) for r in files})
    fr.write(fr.calendar_frame([(d, *calendar.hours(d)) for d in present]), out_root / "calendar.parquet")
    exp_rows = []
    for root in roots:
        for day in present:
            for expiry in store.load_expiries(root, day) or []:
                exp_rows.append((root, day, expiry))
    fr.write(fr.expiries_frame(exp_rows), out_root / "expiries.parquet")
    fr.write(fr.manifest_frame(files), out_root / "manifest.parquet")
    return {"files": len(files), "days": [d.isoformat() for d in present], "expiry_rows": len(exp_rows)}


#: What a gate image keeps of the working area: enough to adopt nightly files and recompile.
GATE_WORK_KEEP = ("journal.jsonl", "expiries", "calendar.json")


def prune(store: Store, keep: Sequence[str], *, drop_key: bool, drop_work: bool, calendar: sl.Calendar,
          keep_journal: bool = False) -> dict[str, Any]:
    """Delete every store file outside `keep` (by the date in its path) and every file the journal
    does not know (a rename a killed run never journaled), recompile, then optionally delete the
    key and the working area. Used on a fork that becomes the Gym image or the gate image."""
    removed, orphans = 0, 0
    known = set(store.journal.files())
    for kind in sl.KINDS:
        base = store.root / kind
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file():
                continue
            rel = str(path.relative_to(store.root))
            parsed = sl.parse_rel_path(rel)
            if parsed is None or sl.window_of(parsed[2]) not in keep:
                path.unlink()
                removed += 1
            elif rel not in known:
                path.unlink()
                orphans += 1
    report = compile_store(store, calendar, windows=keep)
    if drop_work:
        shutil.rmtree(store.work, ignore_errors=True)
        shutil.rmtree("/data/run", ignore_errors=True)
    elif keep_journal:
        # The journal keeps only the kept windows' records, so the image never lists a file it lacks.
        records = [r for r in store.journal.records()
                   if r.get("type") != "file" or r.get("window") in keep]
        for child in store.work.iterdir():
            if child.name not in GATE_WORK_KEEP:
                shutil.rmtree(child) if child.is_dir() else child.unlink()
        tmp = store.work / "journal.jsonl.tmp"
        tmp.write_text("".join(json.dumps(r, sort_keys=True, default=str) + "\n" for r in records))
        os.replace(tmp, store.work / "journal.jsonl")
    if drop_key:
        shutil.rmtree(Path(sl.KEY_PATH).parent, ignore_errors=True)
    return {"removed": removed, "orphans": orphans, **report}


def day_records(store: Store, day: dt.date, roots: Sequence[str] | None = None) -> list[dict[str, Any]]:
    """Everything a copy of one day needs: its file records, its expiry lists, the calendar."""
    out: list[dict[str, Any]] = []
    for record in store.journal.files().values():
        if sl.as_date(record["date"]) == day and (roots is None or record["root"] in roots):
            out.append(record)
    for record in list(out):
        if record["kind"] == "nbbo":
            expiries = store.load_expiries(record["root"], day)
            if expiries is not None:
                out.append({"type": "expiries", "root": record["root"], "date": day.isoformat(),
                            "expiries": [e.isoformat() for e in expiries]})
    try:
        out.append({"type": "calendar", "calendar": json.loads((store.work / "calendar.json").read_text())})
    except (OSError, ValueError):
        pass
    return out


def adopt(store: Store, records_path: str, calendar: sl.Calendar) -> dict[str, Any]:
    """Journal files that a nightly copy placed in this store, after checking each sha256."""
    records = [json.loads(line) for line in Path(records_path).read_text().splitlines() if line.strip()]
    ok = 0
    for record in records:
        if record.get("type") == "file":
            digest, size = sl.sha256_file(store.root / record["path"])
            if digest != record["sha256"] or size != int(record["bytes"]):
                raise SystemExit(f"checksum mismatch for {record['path']}")
            store.journal.append(record)
            ok += 1
        elif record.get("type") == "expiries":
            store.save_expiries(record["root"], dt.date.fromisoformat(record["date"]),
                                [dt.date.fromisoformat(x) for x in record["expiries"]])
        elif record.get("type") == "calendar":
            cache = store.work / "calendar.json"
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(record["calendar"]))
            calendar = sl.Calendar.from_json(record["calendar"]["exceptions"])
    return {"adopted": ok, **compile_store(store, calendar)}


def verify(store: Store) -> dict[str, Any]:
    bad, checked = [], 0
    for rel, record in store.journal.files().items():
        path = store.root / rel
        if not path.exists():
            bad.append({"path": rel, "problem": "missing"})
            continue
        digest, size = sl.sha256_file(path)
        checked += 1
        if digest != record["sha256"]:
            bad.append({"path": rel, "problem": "sha256"})
    return {"checked": checked, "bad": bad[:50], "bad_count": len(bad)}


# ------------------------------------------------------------------------------ CLI
def _names(path: str | None) -> list[str]:
    if not path:
        return []
    data = json.loads(Path(path).read_text())
    return [str(x) for x in (data.get("names") if isinstance(data, dict) else data)]


def _first(text: str | None) -> list[tuple[Any, ...]]:
    """ROOT:DAY[:JOB],... -> [(root, day[, job])]."""
    out: list[tuple[Any, ...]] = []
    for item in (text or "").split(","):
        parts = [p.strip() for p in item.split(":")]
        if len(parts) >= 2 and parts[0]:
            out.append((parts[0], dt.date.fromisoformat(parts[1]), *parts[2:3]))
    return out


def _setup_logging(work: Path) -> None:
    work.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(work / "backfill.log")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%Y-%m-%dT%H:%M:%SZ"))
    logging.Formatter.converter = time.gmtime
    log.addHandler(handler)
    log.setLevel(logging.INFO)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--store", default=sl.STORE_ROOT)
    parser.add_argument("--work", default=sl.WORK_ROOT)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("probe")
    run = sub.add_parser("run")
    run.add_argument("--stages", default="1,2,3,4,5,6")
    run.add_argument("--first", default="")
    run.add_argument("--names-file", default=None)
    run.add_argument("--checks", default="", help="ROOT:DAY,... fetched first into /data/work/check-store")
    run.add_argument("--forward-days", default="", help="stage 7: these forward days for the whole universe")
    run.add_argument("--order", default="1,2,3,4,5,6", help="the order the stages are worked in")
    run.add_argument("--threads", type=int, default=8, help="task threads; more than the slots, so decoding overlaps fetching")
    run.add_argument("--decoders", type=int, default=6, help="processes that decode and write the big frames")
    run.add_argument("--passes", type=int, default=12, help="passes over the queue before giving up on failing tasks")
    run.add_argument("--pause", type=int, default=600, help="seconds between passes")
    run.add_argument("--slots", type=int, default=None, help="write this to the slots file first")
    sub.add_parser("status")
    sub.add_parser("compile")
    pr = sub.add_parser("prune")
    pr.add_argument("--keep", required=True)
    pr.add_argument("--drop-key", action="store_true")
    pr.add_argument("--drop-work", action="store_true")
    pr.add_argument("--keep-journal", action="store_true", help="keep the journal, expiries and calendar (gate image)")
    rc = sub.add_parser("records", help="one day's file records (JSON lines) for a nightly copy")
    rc.add_argument("--date", required=True)
    ad = sub.add_parser("adopt")
    ad.add_argument("--records", required=True)
    sub.add_parser("verify")
    sm = sub.add_parser("sample", help="export some Train root-days as a store-layout tarball")
    sm.add_argument("--roots", required=True)
    sm.add_argument("--days", required=True)
    sm.add_argument("--out", default=f"{sl.WORK_ROOT}/sample.tar")
    one = sub.add_parser("one", help="run one task now and print its record (a smoke test)")
    one.add_argument("task", help="JOB:ROOT:YYYY-MM-DD, e.g. day:SPY:2024-03-13")
    one.add_argument("--stage", type=int, default=0)
    args = parser.parse_args(argv)
    store = Store(args.store, args.work)

    if args.cmd == "probe":
        started = time.monotonic()
        theta = Theta(open_client, Limiter(1))
        print(json.dumps({"auth_seconds": round(time.monotonic() - started, 2)}))
        day = dt.date(2024, 3, 13)
        started = time.monotonic()
        frame = theta.call("option_history_quote", "SPY", day, interval="1m", date=day, strike_range=2,
                           start_time="09:30:00", end_time="16:00:00")
        print(json.dumps({"request": "option_history_quote SPY 0DTE 2024-03-13 strike_range=2",
                          "rows": None if frame is None else frame.height,
                          "columns": None if frame is None else frame.columns,
                          "seconds": round(time.monotonic() - started, 2)}))
        return 0

    if args.cmd == "run":
        _setup_logging(store.work)
        slots_file = str(store.work / "slots")
        if args.slots is not None:
            Path(slots_file).write_text(str(args.slots))
        elif not Path(slots_file).exists():
            Path(slots_file).write_text("4")
        pid_file = store.work / "backfill.pid"
        if pid_file.exists():
            try:
                other = int(pid_file.read_text().strip())
                os.kill(other, 0)
                raise SystemExit(f"a backfill is already running (pid {other})")
            except (ValueError, ProcessLookupError):
                pass
        pid_file.write_text(str(os.getpid()))
        try:
            limiter = Limiter(4, slots_file)
            theta = Theta(open_client, limiter)
            calendar = store.calendar(theta)
            stages = [int(s) for s in args.stages.split(",") if s.strip()]
            names_file = args.names_file or (str(store.work / "universe.json") if (store.work / "universe.json").exists() else None)
            forward = [dt.date.fromisoformat(d) for d in args.forward_days.split(",") if d.strip()]
            order = [int(x) for x in args.order.split(",") if x.strip()]
            tasks = sl.plan(calendar, stages=stages, names=_names(names_file), first=_first(args.first),
                            checks=_first(args.checks), forward=forward, order=order)
            (store.work / "plan.json").write_text(json.dumps({"stages": stages, "tasks": len(tasks), "first": args.first,
                                                              "names": _names(names_file), "at": sl.utc_now()}))
            log.info("run: stages %s, %d tasks, threads %d, decoders %d", stages, len(tasks), args.threads, args.decoders)
            import multiprocessing
            from concurrent.futures import ProcessPoolExecutor

            global POOL, LISTINGS
            POOL = ProcessPoolExecutor(max_workers=args.decoders, mp_context=multiprocessing.get_context("spawn"))
            groups: dict[tuple[dt.date, int], set[str]] = {}
            for task in tasks:
                if task.job == "day":
                    groups.setdefault((task.day, task.stage), set()).add(task.root)
            LISTINGS = Listings(lambda t: sorted(groups.get((t.day, t.stage), {t.root})))
            try:
                # Passes until the queue is empty: a task that failed three times in a pass (a vendor
                # outage, a bad hour) is tried again in the next pass, ten minutes later.
                for passes in range(1, args.passes + 1):
                    Runner(tasks, theta, store, calendar, threads=args.threads).run()
                    left = sl.pending(tasks, store.journal)
                    if not left:
                        break
                    log.warning("pass %d ended with %d tasks not done; next pass in %ds", passes, len(left), args.pause)
                    time.sleep(args.pause)
                return 0
            finally:
                POOL.shutdown(wait=False, cancel_futures=True)
        finally:
            try:
                pid_file.unlink()
            except OSError:
                pass

    if args.cmd == "one":
        job, root, day = args.task.split(":")
        task = sl.Task(args.stage, job, root, dt.date.fromisoformat(day))
        theta = Theta(open_client, Limiter(1))
        calendar = store.calendar(theta)
        started = time.monotonic()
        record = run_task(task, theta, store, calendar)
        store.journal.append({"type": "task", "stage": task.stage, "task": task.id, "status": record.get("status", "ok"),
                              "window": task.window, "at": sl.utc_now(), **{k: v for k, v in record.items() if k != "status"}})
        print(json.dumps({"task": task.id, "seconds": round(time.monotonic() - started, 1), "requests": theta.requests,
                          "request_seconds": round(theta.seconds, 1), **record}, default=str))
        return 0

    if args.cmd == "status":
        try:
            progress = json.loads((store.work / "progress.json").read_text())
        except (OSError, ValueError):
            progress = None
        pid = None
        try:
            pid = int((store.work / "backfill.pid").read_text().strip())
            os.kill(pid, 0)
            alive = True
        except (OSError, ValueError):
            alive = False
        print(json.dumps({"running": alive, "pid": pid, "progress": progress}, indent=1, default=str))
        return 0

    calendar = store.calendar(None)
    if args.cmd == "compile":
        print(json.dumps(compile_store(store, calendar)))
    elif args.cmd == "prune":
        keep = [w.strip() for w in args.keep.split(",") if w.strip()]
        print(json.dumps(prune(store, keep, drop_key=args.drop_key, drop_work=args.drop_work, calendar=calendar,
                               keep_journal=args.keep_journal)))
    elif args.cmd == "records":
        for record in day_records(store, dt.date.fromisoformat(args.date)):
            print(json.dumps(record, sort_keys=True, default=str))
    elif args.cmd == "adopt":
        print(json.dumps(adopt(store, args.records, calendar)))
    elif args.cmd == "verify":
        print(json.dumps(verify(store)))
    elif args.cmd == "sample":
        import tarfile

        staging = store.work / "sample-staging"
        shutil.rmtree(staging, ignore_errors=True)
        result = export_subset(store, staging / "store", [r.strip() for r in args.roots.split(",") if r.strip()],
                               [dt.date.fromisoformat(d.strip()) for d in args.days.split(",") if d.strip()], calendar)
        with tarfile.open(args.out, "w") as tar:
            tar.add(staging / "store", arcname="store")
        shutil.rmtree(staging, ignore_errors=True)
        digest, size = sl.sha256_file(args.out)
        print(json.dumps({**result, "tar": args.out, "sha256": digest, "bytes": size}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
