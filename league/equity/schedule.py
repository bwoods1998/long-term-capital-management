"""The equity book's clock: when bars are read, programs decide, and the open and close windows send.

Owner: book. New York time, the NYSE calendar of `ltcm.data.us_equity_session` (half days close at 13:00; every moment
is an offset from the session's own open or close, so a half day needs no rule of its own). Seconds since midnight ET:

    audit_at      open - 3600 s    (08:30)     the morning re-fetch of the last decision's bars (A8.11)
    preopen       open - 300 s     (09:25)     read the account, positions and orders; reconcile; plan
    open_send     open + 30 s      (09:30:30)  the OPEN window's exits; entries once the exits filled or 120 s passed
    entry_until   open + 900 s     (09:45)     no open-window entry after it (a missed entry is recorded, never chased)
    exit_until    close - 300 s    (15:55)     open-window exits re-priced each minute until it, then go at the bid
                                               (a marketable limit at the widest collar, in the close window)
    close_send    close - 300 s    (15:55:00)  the CLOSE window (A2): exits first, then entries, marketable limits
    close_until   close - 30 s     (15:59:30)  re-priced every 30 s until it, then recorded missed
    bars_at       close + 1200 s   (16:20)     the 1Day bars of the universe, adjustment=raw and adjustment=all
    decide_at     close + 1800 s   (16:30)     each live equity instance decides (the decider's "equity" kind)

The offsets come from the constitution's `equity_money.order_path` (league/live/money.py `EquityTable.offsets`), not
from here; `DEFAULTS` are the design's values, used by tests and by a House whose equity table cannot be read. A key the
table does not carry keeps its default. The House's minute sets the pace: a moment is "due" at the first minute at or
after it, so a 30-second re-price runs at most once a minute.

THE PHASES of a session day (`phase`), in order: "closed" (midnight to the audit), "audit", "preopen", "open_window"
(the open's sends to the entry cut-off), "session", "close_window" (the close's sends to the close), "after_close",
"bars", "decide" (the hour after `decide_at`), "night" (to midnight). A day without a session is "closed" throughout.
"""

from __future__ import annotations

import datetime as dt
import functools
from dataclasses import dataclass
from typing import Mapping
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")

#: The design's offsets in seconds (the constitution's `equity_money.order_path` carries the ones in force).
DEFAULTS: dict[str, int] = {"preopen_before_open_s": 300, "open_send_after_open_s": 30, "exit_wait_s": 120,
                            "entry_until_after_open_s": 900, "exit_until_before_close_s": 300,
                            "close_send_before_close_s": 300, "close_until_before_close_s": 30, "open_reprice_s": 60,
                            "close_reprice_s": 30, "bars_after_close_s": 1200, "decide_after_close_s": 1800,
                            "audit_before_open_s": 3600}
PHASES = ("closed", "audit", "preopen", "open_window", "session", "close_window", "after_close", "bars", "decide",
          "night")
#: How long after `decide_at` the phase reads "decide" (a decide that could not run yet is retried meanwhile).
DECIDE_PHASE_S = 3600
#: The calendar's search horizon for the next or previous session (the longest NYSE closure is a few days).
HORIZON_DAYS = 15


@dataclass(frozen=True)
class Moments:
    """One session's moments as epoch seconds (UTC): preopen, open_send, entry_until, exit_until, close_send,
    close_until, bars_at, decide_at; `open_at` and `close_at` the session's own; `early` a 13:00 close; `audit_at` the
    morning audit of the previous decision's bars (before this session's open)."""

    day: dt.date
    open_at: float
    close_at: float
    early: bool
    preopen: float
    open_send: float
    entry_until: float
    exit_until: float
    close_send: float
    close_until: float
    bars_at: float
    decide_at: float
    audit_at: float = 0.0


def offsets_of(offsets: Mapping[str, int] | None = None) -> dict[str, int]:
    """`DEFAULTS` with the given offsets over them (only `DEFAULTS`' keys; each an integer number of seconds)."""
    out = dict(DEFAULTS)
    for key, value in (offsets or {}).items():
        if key in out:
            out[key] = int(value)
    return out


def _as_date(day: dt.date | str) -> dt.date:
    if isinstance(day, dt.datetime):
        return day.astimezone(NY).date()
    if isinstance(day, dt.date):
        return day
    return dt.date.fromisoformat(str(day)[:10])


@functools.lru_cache(maxsize=4096)
def _session(day: dt.date) -> tuple[bool, bool] | None:
    """(is a session, early close) of `day`; None when the calendar does not cover it (`ltcm.data.CALENDAR_MIN_YEAR`)."""
    from ltcm.data import us_equity_session

    try:
        session = us_equity_session(day)
    except ValueError:                      # `DataError`: outside the computed calendar's years
        return None
    return (False, False) if session is None else (True, bool(session.early_close))


def is_session(day: dt.date | str) -> bool:
    """Whether `day` is an NYSE session (False outside the calendar's years)."""
    found = _session(_as_date(day))
    return bool(found and found[0])


def moments(day: dt.date | str, offsets: Mapping[str, int] | None = None) -> Moments | None:
    """The session's moments, None when `day` is not a session."""
    day = _as_date(day)
    found = _session(day)
    if not found or not found[0]:
        return None
    early = found[1]
    off = offsets_of(offsets)
    open_at = dt.datetime.combine(day, dt.time(9, 30), NY).timestamp()
    close_at = dt.datetime.combine(day, dt.time(13 if early else 16), NY).timestamp()
    return Moments(day=day, open_at=open_at, close_at=close_at, early=early,
                   preopen=open_at - off["preopen_before_open_s"], open_send=open_at + off["open_send_after_open_s"],
                   entry_until=open_at + off["entry_until_after_open_s"],
                   exit_until=close_at - off["exit_until_before_close_s"],
                   close_send=close_at - off["close_send_before_close_s"],
                   close_until=close_at - off["close_until_before_close_s"],
                   bars_at=close_at + off["bars_after_close_s"], decide_at=close_at + off["decide_after_close_s"],
                   audit_at=open_at - off["audit_before_open_s"])


def next_session(day: dt.date | str) -> dt.date:
    """The first session after `day` (the execution day of a decision taken at `day`'s close). ValueError when the
    calendar does not reach one."""
    d = _as_date(day)
    for _ in range(HORIZON_DAYS):
        d += dt.timedelta(days=1)
        if is_session(d):
            return d
    raise ValueError(f"no NYSE session within {HORIZON_DAYS} days after {_as_date(day)}")


def previous_session(day: dt.date | str) -> dt.date:
    """The last session before `day`. ValueError when the calendar does not reach one."""
    d = _as_date(day)
    for _ in range(HORIZON_DAYS):
        d -= dt.timedelta(days=1)
        if is_session(d):
            return d
    raise ValueError(f"no NYSE session within {HORIZON_DAYS} days before {_as_date(day)}")


def sessions_between(first: dt.date | str, last: dt.date | str) -> int:
    """The number of sessions in (first, last]: how many session closes a lot opened on `first` has been held through
    at `last` (0 on its own day; a lot bought at one session's close and sold at the next open was held 1)."""
    a, b = _as_date(first), _as_date(last)
    n, d = 0, a
    while d < b:
        d += dt.timedelta(days=1)
        if is_session(d):
            n += 1
    return n


def ny_day(now: float) -> dt.date:
    """The New York calendar day of epoch `now`."""
    return dt.datetime.fromtimestamp(float(now), NY).date()


def phase(now: float, offsets: Mapping[str, int] | None = None) -> tuple[str, dt.date]:
    """(one of `PHASES`, the session day it belongs to) at epoch `now`."""
    day = ny_day(now)
    m = moments(day, offsets)
    if m is None:
        return "closed", day
    for name, until in (("closed", m.audit_at), ("audit", m.preopen), ("preopen", m.open_send),
                        ("open_window", m.entry_until), ("session", m.close_send), ("close_window", m.close_at),
                        ("after_close", m.bars_at), ("bars", m.decide_at), ("decide", m.decide_at + DECIDE_PHASE_S)):
        if now < until:
            return name, day
    return "night", day


__all__ = ["DEFAULTS", "PHASES", "DECIDE_PHASE_S", "Moments", "offsets_of", "is_session", "moments", "next_session",
           "previous_session", "sessions_between", "ny_day", "phase"]
