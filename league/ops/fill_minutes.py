"""The `fill_minutes` job: the 1Min bars around each session's two send instants (release E3, D10).

Owner: D (league/ops/E3_INTERFACES.md). Protected. 45 minutes after each close (13:45 ET on a half day) and at the
House's start; in a pause too. It reads the gateway's bars route (the one `equity_data` pages; the free SIP route)
and writes one file a session under `<state>/equity-fill-minutes/`. Data never leaves the House's state directory
(the vendor's terms; a public repository): nothing here is committed, printed in full or sent anywhere.

THE FILE: `<state>/equity-fill-minutes/<YYYY>/<YYYY-MM-DD>.json` (directory 0700, file 0600, written to a temporary
name, then renamed): {"version": 1, "day", "fetched_at", "source": "alpaca-sip-1Min", "windows": [[start, end], [start,
end]], "bars": {SYM: [[t, o, h, l, c, v, vw, n], ...]}}, raw adjustment, time order.

THE WINDOWS (`windows`): [open, open + `OPEN_MINUTES` min) and [close - `CLOSE_MINUTES` min, close), RFC 3339 UTC, by
`league.equity.schedule.moments` (a 13:00 close moves the second; both seasons).

THE LIVE-LIKE PRICE (`bar_start`, `livelike`). The send instants are `schedule.moments(day).open_send` and
`.close_send` (`schedule.DEFAULTS`; a test holds the constitution's `equity_money.order_path` equal to them).
`bar_start(day, at)` is the first whole minute at or after the send instant (09:31 for the 09:30:30 open send; 15:55
for the close send; 12:55 on a half day). `livelike(root, day, sym, at)` is that 1Min bar's `vw` when finite and > 0
(field "vw"), else `(h + l + c) / 3` (field "hlc3"), else None. It is the VWAP of the minute AFTER the send, not the
09:30 bar, whose opening cross would hide the gap.

THE JOB (`run`): skipped when the forward mode is "off" or `elane.forward.fill_minutes` is false. For each of the last
`BACKFILL_SESSIONS` forward days whose close is 40 minutes past and that has no file: both windows for
`equity_data.universe()`, then the file. Nothing is fetched for a day before `forward_db.t0()`. A gateway error is
{"status": "failed"}; days already written stay (the next run's backfill fetches a missing day).

Standard library only.
"""

from __future__ import annotations

import datetime as dt
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


def windows(day: dt.date | str) -> tuple[tuple[str, str], tuple[str, str]]:
    """((start, end), (start, end)): RFC 3339 UTC of [open, open + `OPEN_MINUTES` min) and [close - `CLOSE_MINUTES`
    min, close) of the session `day` (ValueError when it is not a session)."""
    raise NotImplementedError("D: league/ops/fill_minutes.py windows")


def fetch_minutes(gateway: Any, symbols: Sequence[str], start: str, end: str) -> dict[str, list[list[Any]]]:
    """{symbol: [[t, o, h, l, c, v, vw, n], ...] in time order} of every page of `gateway.get(BARS, {"symbols",
    "timeframe": "1Min", "start", "end", "adjustment": "raw", "feed": "sip", "limit", "page_token"})`, paged as
    `equity_data.fetch` pages. Every symbol asked for is a key. ValueError on a malformed answer or a cursor that
    does not end within `MAX_PAGES`."""
    raise NotImplementedError("D: league/ops/fill_minutes.py fetch_minutes")


def write_day(root: str | Path, day: dt.date | str, bars: Mapping[str, Sequence[Sequence[Any]]], *,
              fetched_at: float) -> Path:
    """The day's file (the module docstring), atomically, directory 0700 and file 0600; its path."""
    raise NotImplementedError("D: league/ops/fill_minutes.py write_day")


def read_day(root: str | Path, day: dt.date | str) -> dict[str, Any] | None:
    """The day's file as written; None when absent or unreadable."""
    raise NotImplementedError("D: league/ops/fill_minutes.py read_day")


def bar_start(day: dt.date | str, at: str) -> dt.datetime:
    """The start (UTC, timezone-aware) of the first whole minute at or after `day`'s send instant for the fill point
    `at` ("open" | "close"); ValueError for another `at` or a day that is not a session."""
    raise NotImplementedError("D: league/ops/fill_minutes.py bar_start")


def livelike(root: str | Path, day: dt.date | str, symbol: str, at: str) -> tuple[float, str] | None:
    """D10's live-like price of `symbol` at `day`'s fill point `at`: (the price, its field: "vw" | "hlc3"); None when
    the day has no file, the symbol no bar at `bar_start(day, at)`, or the bar no usable price."""
    raise NotImplementedError("D: league/ops/fill_minutes.py livelike")


def run(ctx: Any) -> dict[str, Any]:
    """THE JOB (the module docstring; league/ops/registry.py). The receipt: {"days": [the days written], "symbols",
    "bars" (counts)}, never a price."""
    raise NotImplementedError("D: league/ops/fill_minutes.py run")


__all__ = ["DIR", "VERSION", "SOURCE", "BARS", "OPEN_MINUTES", "CLOSE_MINUTES", "BACKFILL_SESSIONS", "SETTLE_SECONDS",
           "FIELDS", "PAGE_LIMIT", "MAX_PAGES", "LIVELIKE_FIELDS", "windows", "fetch_minutes", "write_day", "read_day",
           "bar_start", "livelike", "run"]
