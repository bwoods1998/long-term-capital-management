"""Sessions and Eastern time for the event lane (PREREG-EVL-1 section 5).

Sessions come from Alpaca's `v2/calendar` through the gateway and are stored in `sessions` (day, open and close in UTC,
early). The lane's moments, all on a session's own clock:
- OPEN decision at 09:15 ET from events knowable by 09:00 ET; the market-on-open order by 09:27 ET;
- CLOSE decision at the session's close - 14 minutes (15:46 ET on a full day); the market-on-close order by close - 11
  minutes (15:49 ET), inside Alpaca's cls cut-off of close - 10 minutes.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from . import store as S

NY = ZoneInfo("America/New_York")
OPEN_KNOWABLE_BY = dt.time(9, 0)
OPEN_DECIDE_AT = dt.time(9, 15)
OPEN_SEND_BY = dt.time(9, 27)
CLOSE_DECIDE_BEFORE = dt.timedelta(minutes=14)
CLOSE_SEND_BEFORE = dt.timedelta(minutes=11)


@dataclasses.dataclass(frozen=True)
class Session:
    day: dt.date
    open_at: dt.datetime   # UTC
    close_at: dt.datetime  # UTC
    early: bool

    def at(self, wall: dt.time) -> dt.datetime:
        """This session's Eastern wall time `wall`, in UTC."""
        return dt.datetime.combine(self.day, wall, tzinfo=NY).astimezone(dt.timezone.utc)

    @property
    def open_cutoff(self) -> dt.datetime:  # events knowable before this enter at this session's open
        return self.at(OPEN_KNOWABLE_BY)

    @property
    def open_decide(self) -> dt.datetime:
        return self.at(OPEN_DECIDE_AT)

    @property
    def open_send_by(self) -> dt.datetime:
        return self.at(OPEN_SEND_BY)

    @property
    def close_decide(self) -> dt.datetime:
        return self.close_at - CLOSE_DECIDE_BEFORE

    @property
    def close_send_by(self) -> dt.datetime:
        return self.close_at - CLOSE_SEND_BEFORE


def _wall(day: dt.date, hhmm: str) -> dt.datetime:
    h, m = (int(x) for x in hhmm.split(":"))
    return dt.datetime.combine(day, dt.time(h, m), tzinfo=NY).astimezone(dt.timezone.utc)


def refresh(store: S.Store, gw: Any, start: dt.date, end: dt.date) -> int:
    """Store Alpaca's sessions from `start` to `end` (inclusive). Returns how many rows were written."""
    rows = gw.get_json("/v1/alpaca/v2/calendar", {"start": start.isoformat(), "end": end.isoformat()})
    n = 0
    with store.tx() as db:
        for row in rows or []:
            day = dt.date.fromisoformat(str(row["date"]))
            open_at, close_at = _wall(day, str(row["open"])), _wall(day, str(row["close"]))
            early = int(str(row["close"]) != "16:00")
            db.execute("INSERT INTO sessions(day, open_at, close_at, early) VALUES(?, ?, ?, ?) ON CONFLICT(day) DO UPDATE "
                       "SET open_at=excluded.open_at, close_at=excluded.close_at, early=excluded.early",
                       (day.isoformat(), S.iso(open_at), S.iso(close_at), early))
            n += 1
    return n


def _row(row: Any) -> Session:
    return Session(dt.date.fromisoformat(row["day"]), S.parse_iso(row["open_at"]), S.parse_iso(row["close_at"]),
                   bool(row["early"]))


def sessions(store: S.Store, start: dt.date, end: dt.date) -> list[Session]:
    return [_row(r) for r in store.db.execute("SELECT * FROM sessions WHERE day BETWEEN ? AND ? ORDER BY day",
                                              (start.isoformat(), end.isoformat()))]


def session(store: S.Store, day: dt.date) -> Session | None:
    row = store.db.execute("SELECT * FROM sessions WHERE day=?", (day.isoformat(),)).fetchone()
    return None if row is None else _row(row)


def _after(store: S.Store, day: dt.date, limit: int = 40) -> Iterable[Session]:
    for r in store.db.execute("SELECT * FROM sessions WHERE day>=? ORDER BY day LIMIT ?", (day.isoformat(), limit)):
        yield _row(r)


def first_open_entry(store: S.Store, knowable_at: dt.datetime) -> Session | None:
    """The first session whose 09:00 ET is after `knowable_at` (O1, O3, 8K-READ, INS-CLUSTER entries)."""
    start = knowable_at.astimezone(NY).date()
    for s in _after(store, start):
        if s.open_cutoff > knowable_at:
            return s
    return None


def first_close_decision(store: S.Store, knowable_at: dt.datetime) -> Session | None:
    """The first session whose CLOSE decision time is after `knowable_at` (C1's day 0)."""
    start = knowable_at.astimezone(NY).date()
    for s in _after(store, start):
        if s.close_decide > knowable_at:
            return s
    return None


def nth(store: S.Store, first: dt.date, n: int) -> Session | None:
    """The n-th session counting `first` as session 1."""
    if n < 1:
        raise ValueError("n counts from 1")
    rows = list(_after(store, first, limit=n + 1))
    if not rows or rows[0].day != first or len(rows) < n:
        return None
    return rows[n - 1]


def previous(store: S.Store, day: dt.date, n: int = 1) -> list[Session]:
    """The n completed sessions before `day`, oldest first."""
    rows = [_row(r) for r in store.db.execute("SELECT * FROM sessions WHERE day<? ORDER BY day DESC LIMIT ?",
                                              (day.isoformat(), n))]
    return list(reversed(rows))


__all__ = ["Session", "NY", "refresh", "sessions", "session", "first_open_entry", "first_close_decision", "nth",
           "previous"]
