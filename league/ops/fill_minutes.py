"""The `fill_minutes` job: the 1Min bars around each session's two send instants (release E3, D10).

Owner: D (league/ops/E3_INTERFACES.md). Protected. 45 minutes after each close (13:45 ET on a half day) and at the
House's start; in a pause too. It reads the gateway's bars route (the one `equity_data` pages; the free SIP route)
and writes one file a session under `<state>/equity-fill-minutes/`. Data never leaves the House's state directory
(the vendor's terms; a public repository): nothing here is committed, printed in full or sent anywhere.

THE FILE: `<state>/equity-fill-minutes/<YYYY>/<YYYY-MM-DD>.json` (directory 0700, file 0600, written to a temporary
name, then renamed): {"version": 1, "day", "fetched_at", "source": "alpaca-sip-1Min", "windows": [[start, end], [start,
end]], "bars": {SYM: [[t, o, h, l, c, v, vw, n], ...]}}, raw adjustment, time order. `t` is the minute's start, RFC
3339 UTC to the second; a field the venue did not give, or gave as something that is not a finite number, is null.

THE WINDOWS (`windows`): [open, open + `OPEN_MINUTES` min) and [close - `CLOSE_MINUTES` min, close), RFC 3339 UTC, by
`league.equity.schedule.moments` (a 13:00 close moves the second; both seasons). The venue's `end` is inclusive, so
the job keeps only the bars that start inside a window (`inside`).

THE LIVE-LIKE PRICE (`bar_start`, `livelike`, `livelike_of`). The send instants are `schedule.moments(day).open_send`
and `.close_send` (`schedule.DEFAULTS`; a test holds the constitution's `equity_money.order_path` equal to them).
`bar_start(day, at)` is the first whole minute at or after the send instant (09:31 for the 09:30:30 open send; 15:55
for the close send; 12:55 on a half day). `livelike(root, day, sym, at)` is that 1Min bar's `vw` when finite and > 0
(field "vw"), else `(h + l + c) / 3` (field "hlc3"), else None. It is the VWAP of the minute AFTER the send, not the
09:30 bar, whose opening cross would hide the gap.

THE JOB (`run`): skipped when the forward mode is "off" or `elane.forward.fill_minutes` is false. For each of the last
`BACKFILL_SESSIONS` forward days whose close is 40 minutes past and that has no file (`due_days`; the job does not read
the daily store, which is written later that evening: a forward day here is a session on or after
`forward_db.t0()`): both windows for `equity_data.universe()`, then the file. Nothing is fetched for a day before
`forward_db.t0()`. A gateway error is {"status": "failed"}; days already written stay (the next run's backfill fetches
a missing day). A DAY THAT IS NOT READY IS NOT WRITTEN: a file is written once and never fetched again, so an answer
that lacks the send-minute bar of `equity_data.CALENDAR_SYMBOL` in either window (the venue has not settled the day
yet) writes no file and fails the receipt; the runner starts the job again inside its grace and the next run's
backfill fetches the day. A symbol that has no bar in a minute is that symbol's alone: its live-like price is None.

Standard library only.
"""

from __future__ import annotations

import datetime as dt
import math
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

from .equity_data import BARS

DIR = "equity-fill-minutes"
#: The file's `version` and `source`.
VERSION = 1
SOURCE = "alpaca-sip-1Min"
#: Minutes fetched from the open, and before the close.
OPEN_MINUTES = 5
CLOSE_MINUTES = 10
#: A run fetches a missing file for this many of the last forward days.
BACKFILL_SESSIONS = 10
#: A day's file is fetched once its close is this many seconds past.
SETTLE_SECONDS = 40 * 60
#: A kept bar row is [t, *FIELDS] (`equity_data.fetch` drops `vw`, so this module pages for itself).
FIELDS = ("o", "h", "l", "c", "v", "vw", "n")
PAGE_LIMIT = 10000
MAX_PAGES = 20
#: `livelike`'s field names: the minute's VWAP, else the mean of its high, low and close.
LIVELIKE_FIELDS = ("vw", "hlc3")
#: The two fill points (the captain's A2), and the stamp every time in a file carries.
FILL_POINTS = ("open", "close")
STAMP = "%Y-%m-%dT%H:%M:%SZ"
#: How far back `due_days` walks the calendar for its `BACKFILL_SESSIONS` sessions (calendar days).
LOOKBACK_DAYS = 45


# ------------------------------------------------------------------------------------------------------ small helpers
def _day(day: dt.date | str) -> dt.date:
    if isinstance(day, dt.datetime):
        raise ValueError(f"a session day is a date or an ISO day, not the moment {day!r}")
    if isinstance(day, dt.date):
        return day
    return dt.date.fromisoformat(str(day)[:10])


def _moments(day: dt.date | str) -> Any:
    """The session's `schedule.Moments` (the design's offsets: `schedule.DEFAULTS`); ValueError when `day` is not a
    session."""
    from ..equity import schedule

    found = schedule.moments(_day(day))
    if found is None:
        raise ValueError(f"{_day(day)} is not an NYSE session")
    return found


def _utc(epoch: float) -> dt.datetime:
    return dt.datetime.fromtimestamp(float(epoch), dt.timezone.utc)


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(float(value)) else None


def _stamp(value: Any) -> str:
    """A bar's time as the file keeps it (UTC, to the second). ValueError for a stamp that is not a moment with a
    zone."""
    moment = dt.datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    if moment.tzinfo is None:
        raise ValueError(f"the bar time {str(value)[:40]!r} has no zone")
    return moment.astimezone(dt.timezone.utc).strftime(STAMP)


def path_of(root: str | Path, day: dt.date | str) -> Path:
    """`<root>/equity-fill-minutes/<YYYY>/<YYYY-MM-DD>.json`."""
    day = _day(day)
    return Path(root) / DIR / f"{day.year:04d}" / f"{day.isoformat()}.json"


def days_on_disk(root: str | Path) -> list[str]:
    """The ISO days that have a file, oldest first ([] when the directory is absent)."""
    out = []
    for path in (Path(root) / DIR).glob("[0-9][0-9][0-9][0-9]/*.json"):
        try:
            day = dt.date.fromisoformat(path.stem)
        except ValueError:
            continue
        if path.parent.name == f"{day.year:04d}":
            out.append(day.isoformat())
    return sorted(out)


# ------------------------------------------------------------------------------------------------------------ windows
def windows(day: dt.date | str) -> tuple[tuple[str, str], tuple[str, str]]:
    """((start, end), (start, end)): RFC 3339 UTC of [open, open + `OPEN_MINUTES` min) and [close - `CLOSE_MINUTES`
    min, close) of the session `day` (ValueError when it is not a session)."""
    m = _moments(day)
    return ((_utc(m.open_at).strftime(STAMP), _utc(m.open_at + OPEN_MINUTES * 60).strftime(STAMP)),
            (_utc(m.close_at - CLOSE_MINUTES * 60).strftime(STAMP), _utc(m.close_at).strftime(STAMP)))


def bar_start(day: dt.date | str, at: str) -> dt.datetime:
    """The start (UTC, timezone-aware) of the first whole minute at or after `day`'s send instant for the fill point
    `at` ("open" | "close"); ValueError for another `at` or a day that is not a session."""
    if at not in FILL_POINTS:
        raise ValueError(f"'at' is open or close, not {at!r}")
    m = _moments(day)
    send = m.open_send if at == "open" else m.close_send
    return _utc(math.ceil(float(send) / 60.0) * 60.0)


def inside(rows: Sequence[Sequence[Any]], start: str, end: str) -> list[list[Any]]:
    """The bar rows that START inside [start, end) (the venue's `end` is inclusive: the bar at `end` is the next
    window's, or nobody's)."""
    return [list(row) for row in rows if start <= str(row[0]) < end]


# -------------------------------------------------------------------------------------------------------- the gateway
def fetch_minutes(gateway: Any, symbols: Sequence[str], start: str, end: str) -> dict[str, list[list[Any]]]:
    """{symbol: [[t, o, h, l, c, v, vw, n], ...] in time order} of every page of `gateway.get(BARS, {"symbols",
    "timeframe": "1Min", "start", "end", "adjustment": "raw", "feed": "sip", "limit", "page_token"})`, paged as
    `equity_data.fetch` pages. Every symbol asked for is a key. ValueError on a malformed answer or a cursor that
    does not end within `MAX_PAGES`."""
    out: dict[str, dict[str, list[Any]]] = {str(s): {} for s in symbols}
    token = None
    for _ in range(MAX_PAGES):
        params = {"symbols": ",".join(str(s) for s in symbols), "timeframe": "1Min", "start": start, "end": end,
                  "adjustment": "raw", "feed": "sip", "limit": PAGE_LIMIT}
        if token:
            params["page_token"] = token
        answer = gateway.get(BARS, params) or {}
        bars = answer.get("bars") if isinstance(answer, Mapping) else None
        if bars is None and isinstance(answer, Mapping) and "bars" in answer:
            bars = {}  # the venue's answer for a span with no bar at all
        if not isinstance(bars, Mapping):
            raise ValueError("the minute bars answer has no bars")
        for symbol, rows in bars.items():
            seen = out.setdefault(str(symbol), {})
            if rows is None:
                continue
            if not isinstance(rows, list):
                raise ValueError(f"the minute bars of {str(symbol)[:12]} are not a list")
            for row in rows:
                if not isinstance(row, Mapping) or not row.get("t"):
                    raise ValueError(f"a minute bar of {str(symbol)[:12]} is not an object with a time")
                try:
                    stamp = _stamp(row["t"])
                except (TypeError, ValueError):
                    raise ValueError(f"a minute bar of {str(symbol)[:12]} has a time that is not one "
                                     f"({str(row['t'])[:30]})") from None
                if stamp in seen:
                    raise ValueError(f"the minute bar of {str(symbol)[:12]} at {stamp} came twice")
                count = _num(row.get("n"))
                seen[stamp] = [stamp, *(_num(row.get(k)) for k in FIELDS[:-1]), None if count is None else int(count)]
        token = answer.get("next_page_token") if isinstance(answer, Mapping) else None
        if not token:
            return {s: [rows[k] for k in sorted(rows)] for s, rows in out.items()}
    raise ValueError(f"the minute bars did not end within {MAX_PAGES} pages")


# ----------------------------------------------------------------------------------------------------------- the file
def write_day(root: str | Path, day: dt.date | str, bars: Mapping[str, Sequence[Sequence[Any]]], *,
              fetched_at: float) -> Path:
    """The day's file (the module docstring), atomically, directory 0700 and file 0600; its path."""
    from .context import write_json

    day = _day(day)
    path = path_of(root, day)
    for folder in (path.parent.parent, path.parent):
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(folder, 0o700)
    rows = {}
    for symbol in sorted(bars):
        kept = []
        for row in bars[symbol] or ():
            row = list(row)
            if len(row) != len(FIELDS) + 1 or not isinstance(row[0], str):
                raise ValueError(f"a minute bar of {str(symbol)[:12]} is not [t, {', '.join(FIELDS)}]")
            count = _num(row[-1])
            kept.append([row[0], *(_num(x) for x in row[1:-1]), None if count is None else int(count)])
        rows[str(symbol)] = sorted(kept, key=lambda r: r[0])
    doc = {"version": VERSION, "day": day.isoformat(), "fetched_at": float(fetched_at), "source": SOURCE,
           "windows": [list(w) for w in windows(day)], "bars": rows}
    return write_json(path, doc, mode=0o600, indent=None)


def read_day(root: str | Path, day: dt.date | str) -> dict[str, Any] | None:
    """The day's file as written; None when absent or unreadable."""
    from .context import read_json

    try:
        day = _day(day)
    except ValueError:
        return None
    doc = read_json(path_of(root, day))
    if not isinstance(doc, dict) or doc.get("version") != VERSION or doc.get("day") != day.isoformat() \
            or not isinstance(doc.get("bars"), dict):
        return None
    return doc


# ------------------------------------------------------------------------------------------------ the live-like price
def livelike_of(doc: Mapping[str, Any] | None, day: dt.date | str, symbol: str, at: str) -> tuple[float, str] | None:
    """`livelike` on a day's file already read (`read_day`'s answer; None: no file)."""
    start = bar_start(day, at).strftime(STAMP)
    rows = ((doc or {}).get("bars") or {}).get(str(symbol)) if isinstance(doc, Mapping) else None
    if not isinstance(rows, list):
        return None
    for row in rows:
        if not isinstance(row, list) or len(row) != len(FIELDS) + 1 or row[0] != start:
            continue
        bar = dict(zip(FIELDS, (_num(x) for x in row[1:])))
        if bar["vw"] is not None and bar["vw"] > 0:
            return bar["vw"], LIVELIKE_FIELDS[0]
        parts = [bar["h"], bar["l"], bar["c"]]
        if all(x is not None and x > 0 for x in parts):
            return math.fsum(parts) / 3.0, LIVELIKE_FIELDS[1]
        return None
    return None


def livelike(root: str | Path, day: dt.date | str, symbol: str, at: str) -> tuple[float, str] | None:
    """D10's live-like price of `symbol` at `day`'s fill point `at`: (the price, its field: "vw" | "hlc3"); None when
    the day has no file, the symbol no bar at `bar_start(day, at)`, or the bar no usable price."""
    if at not in FILL_POINTS:
        raise ValueError(f"'at' is open or close, not {at!r}")
    doc = read_day(root, day)
    return None if doc is None else livelike_of(doc, day, symbol, at)


# ------------------------------------------------------------------------------------------------------------ the job
def due_days(now: float, *, first: dt.date) -> list[dt.date]:
    """The last `BACKFILL_SESSIONS` sessions on or after `first` (`forward_db.t0()`) whose close is `SETTLE_SECONDS`
    past at epoch `now`, oldest first."""
    from ..equity import schedule

    out: list[dt.date] = []
    day = schedule.ny_day(now)
    for _ in range(LOOKBACK_DAYS):
        if day < first or len(out) >= BACKFILL_SESSIONS:
            break
        m = schedule.moments(day)
        if m is not None and m.close_at + SETTLE_SECONDS <= now:
            out.append(day)
        day -= dt.timedelta(days=1)
    return sorted(out)


def _cfg(settings: Mapping[str, Any] | None) -> dict[str, Any]:
    """`forward_db.cfg`, and the code defaults (mode "off") when the settings cannot be read."""
    from . import forward_db

    try:
        return dict(forward_db.cfg(settings))
    except Exception:  # noqa: BLE001 - an unreadable block is "off"
        return dict(forward_db.DEFAULTS)


def run(ctx: Any) -> dict[str, Any]:
    """THE JOB (the module docstring; league/ops/registry.py). The receipt: {"days": [the days written], "symbols",
    "bars" (counts)}, never a price."""
    from ..swarm import settings as settings_mod
    from . import forward_db
    from .equity_data import CALENDAR_SYMBOL, universe

    root = Path(ctx.root)
    cfg = _cfg(settings_mod.load(root, config=getattr(ctx, "config", None)))
    if cfg.get("mode") == "off":
        return {"status": "skipped", "why": "elane.forward.mode is off"}
    if not cfg.get("fill_minutes"):
        return {"status": "skipped", "why": "elane.forward.fill_minutes is false"}
    now = ctx.now()
    symbols = list(universe())
    if not symbols:
        return {"status": "failed", "ok": False, "error": "the universe is empty"}
    marker = CALENDAR_SYMBOL if CALENDAR_SYMBOL in symbols else symbols[0]
    todo = [day for day in due_days(now, first=forward_db.t0()) if not path_of(root, day).exists()]
    written: list[str] = []
    count = 0

    def receipt(**more: Any) -> dict[str, Any]:
        return {"days": list(written), "symbols": len(symbols), "bars": count, **more}

    for day in todo:
        try:
            bars: dict[str, list[list[Any]]] = {s: [] for s in symbols}
            for start, end in windows(day):
                for symbol, rows in fetch_minutes(ctx.gateway, symbols, start, end).items():
                    if symbol in bars:
                        bars[symbol].extend(inside(rows, start, end))
        except Exception as exc:  # noqa: BLE001 - a gateway error writes no file for that day: retried in its grace
            return receipt(status="failed", ok=False, day=day.isoformat(),
                           error=f"{type(exc).__name__}: {str(exc)[:200]}")
        doc = {"bars": bars}
        if any(livelike_of(doc, day, marker, at) is None for at in FILL_POINTS):
            return receipt(status="failed", ok=False, day=day.isoformat(),
                           error=f"the minute bars of {day.isoformat()} are not ready: no send-minute bar of {marker} "
                                 "in a window; nothing written for that day")
        write_day(root, day, bars, fetched_at=now)
        written.append(day.isoformat())
        count += sum(len(rows) for rows in bars.values())
    return receipt(ok=True)


__all__ = ["DIR", "VERSION", "SOURCE", "BARS", "OPEN_MINUTES", "CLOSE_MINUTES", "BACKFILL_SESSIONS", "SETTLE_SECONDS",
           "FIELDS", "PAGE_LIMIT", "MAX_PAGES", "LIVELIKE_FIELDS", "FILL_POINTS", "windows", "fetch_minutes",
           "write_day", "read_day", "bar_start", "livelike", "livelike_of", "inside", "path_of", "days_on_disk",
           "due_days", "run"]
