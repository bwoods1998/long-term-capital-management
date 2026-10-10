"""The equity book's clock: when bars are read, programs decide, and the open and close windows send.

Owner: book. New York time, the NYSE calendar of `ltcm.data.us_equity_session` (half days close at 13:00; every moment
is an offset from the session's own open or close, so a half day needs no rule of its own). Seconds since midnight ET:

    preopen       open - 300 s     (09:25)     read the account, positions and orders; reconcile; plan; write pending rows
    open_send     open + 30 s      (09:30:30)  the OPEN window's exits; entries once the exits filled or 120 s passed
    entry_until   open + 900 s     (09:45)     no open-window entry after it (a missed entry is recorded, never chased)
    exit_until    close - 300 s    (15:55)     open-window exits re-priced each minute until it, then sent at the bid
    close_send    close - 300 s    (15:55:00)  the CLOSE window (A2): exits first, then entries, marketable limits
    close_until   close - 30 s     (15:59:30)  re-priced every 30 s until it, then recorded missed
    bars_at       close + 1200 s   (16:20)     the 1Day bars of the universe, adjustment=raw and adjustment=all
    decide_at     close + 1800 s   (16:30)     each live equity instance decides (the decider's "equity" kind)
    audit_at      next open - 3600 s (08:30)   the morning re-fetch of the last decision's bars (A8.11)

The offsets come from the constitution's `equity_money.order_path` (league/live/money.py `EquityTable`), not from here;
`DEFAULTS` are the design's values, used by tests.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Mapping

#: The design's offsets in seconds (the constitution's `equity_money.order_path` carries the ones in force).
DEFAULTS: dict[str, int] = {"preopen_before_open_s": 300, "open_send_after_open_s": 30, "exit_wait_s": 120,
                            "entry_until_after_open_s": 900, "exit_until_before_close_s": 300,
                            "close_send_before_close_s": 300, "close_until_before_close_s": 30, "open_reprice_s": 60,
                            "close_reprice_s": 30, "bars_after_close_s": 1200, "decide_after_close_s": 1800,
                            "audit_before_open_s": 3600}
PHASES = ("closed", "audit", "preopen", "open_window", "session", "close_window", "after_close", "bars", "decide",
          "night")


@dataclass(frozen=True)
class Moments:
    """One session's moments as epoch seconds (UTC): preopen, open_send, entry_until, exit_until, close_send,
    close_until, bars_at, decide_at; `open_at` and `close_at` the session's own; `early` a 13:00 close."""

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


def moments(day: dt.date, offsets: Mapping[str, int] | None = None) -> Moments | None:
    """The session's moments, None when `day` is not a session."""
    raise NotImplementedError("book: league/equity/schedule.py moments")


def next_session(day: dt.date) -> dt.date:
    """The first session after `day` (the execution day of a decision taken at `day`'s close)."""
    raise NotImplementedError("book: league/equity/schedule.py next_session")


def phase(now: float, offsets: Mapping[str, int] | None = None) -> tuple[str, dt.date]:
    """(one of `PHASES`, the session day it belongs to) at epoch `now`."""
    raise NotImplementedError("book: league/equity/schedule.py phase")


__all__ = ["DEFAULTS", "PHASES", "Moments", "moments", "next_session", "phase"]

