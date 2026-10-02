"""When the House's jobs are due: triggers over the House's own session calendar, never a hard-coded session hour.

A trigger turns a window of time into the instants a job is due in it (`occurrences(trigger, start, end)`, epoch
seconds, sorted, in `(start, end]`). The session triggers read `ltcm.data.us_equity_session` (the NYSE calendar the
House trades by, holidays and early closes included, computed in New York time): "an hour before the open" is 12:30Z
in summer and 13:30Z in winter, and an early close moves "ten minutes after the close" with it. The fixed triggers are
fixed in UTC on purpose (the scoreboard's 23:30Z, hygiene's 02:00Z): they are chosen outside every session in both
seasons. Two triggers are not about the clock and are answered by the runner (`league/ops/runner.py`): `after(job)`
(due when `job` last finished `ok`) and `at_start()` (due once each time the House starts).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time as clock_time, timedelta, timezone

from ltcm.data import DataError, to_datetime, us_equity_session

UTC = timezone.utc


@dataclass(frozen=True)
class Trigger:
    """One way a job becomes due. `kind`: `daily` (every UTC day at `at`), `hourly` (every hour at minute `minute`),
    `weekly` (UTC `weekday` 0=Monday at `at`), `monthly` (the first UTC `weekday` of each month at `at`), `open`/`close`
    (each trading day's session open/close plus `offset_minutes`), `after` (when job `job` finished ok), `start` (at
    each House start)."""
    kind: str
    at: clock_time = clock_time(0, 0)
    minute: int = 0
    weekday: int = 0
    offset_minutes: int = 0
    job: str = ""

    def describe(self) -> str:
        hhmm = self.at.strftime("%H:%MZ")
        sign = "+" if self.offset_minutes >= 0 else "-"
        return {"daily": f"daily {hhmm}", "hourly": f"hourly at :{self.minute:02d}",
                "weekly": f"weekly {('Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun')[self.weekday]} {hhmm}",
                "monthly": f"monthly, first {('Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun')[self.weekday]} {hhmm}",
                "open": f"trading days, open {sign} {abs(self.offset_minutes)} min",
                "close": f"trading days, close {sign} {abs(self.offset_minutes)} min",
                "after": f"after {self.job} finishes ok", "start": "at each House start"}.get(self.kind, self.kind)


def daily(hour: int, minute: int = 0) -> Trigger:
    return Trigger("daily", at=clock_time(hour, minute))


def hourly(minute: int = 0) -> Trigger:
    return Trigger("hourly", minute=int(minute))


def weekly(weekday: int, hour: int, minute: int = 0) -> Trigger:
    return Trigger("weekly", at=clock_time(hour, minute), weekday=int(weekday))


def monthly_first(weekday: int, hour: int, minute: int = 0) -> Trigger:
    return Trigger("monthly", at=clock_time(hour, minute), weekday=int(weekday))


def session_open(offset_minutes: int = 0) -> Trigger:
    return Trigger("open", offset_minutes=int(offset_minutes))


def session_close(offset_minutes: int = 0) -> Trigger:
    return Trigger("close", offset_minutes=int(offset_minutes))


def after(job: str) -> Trigger:
    return Trigger("after", job=str(job))


def at_start() -> Trigger:
    return Trigger("start")


@dataclass
class CalendarGaps:
    """The days a session trigger could not be computed for (a year outside the computed calendar)."""
    days: list[str] = field(default_factory=list)


def _utc_days(start: float, end: float) -> list[date]:
    first = datetime.fromtimestamp(start, UTC).date() - timedelta(days=1)
    last = datetime.fromtimestamp(end, UTC).date() + timedelta(days=1)
    out, day = [], first
    while day <= last:
        out.append(day)
        day += timedelta(days=1)
    return out


def occurrences(trigger: Trigger, start: float, end: float, *, gaps: CalendarGaps | None = None) -> list[float]:
    """The instants in `(start, end]` at which `trigger` makes its job due, sorted. `after`/`start` have none here
    (the runner answers them). A day the session calendar cannot compute is skipped and named in `gaps`."""
    if end <= start:
        return []
    out: list[float] = []
    kind = trigger.kind
    if kind == "hourly":
        hour = int(start // 3600) * 3600
        while hour <= end + 3600:
            out.append(hour + 60 * trigger.minute)
            hour += 3600
    elif kind in ("daily", "weekly", "monthly"):
        for day in _utc_days(start, end):
            if kind == "weekly" and day.weekday() != trigger.weekday:
                continue
            if kind == "monthly" and (day.weekday() != trigger.weekday or day.day > 7):
                continue
            out.append(datetime.combine(day, trigger.at, UTC).timestamp())
    elif kind in ("open", "close"):
        # New York's dates: a session's open and close fall on its own New York day, which is never more than one
        # UTC day away from the window's edges.
        for day in _utc_days(start, end):
            try:
                session = us_equity_session(day)
            except DataError:
                if gaps is not None:
                    gaps.days.append(day.isoformat())
                continue
            if session is None:
                continue
            edge = to_datetime(session.open_at if kind == "open" else session.close_at).timestamp()
            out.append(edge + 60 * trigger.offset_minutes)
    return sorted({t for t in out if start < t <= end})


def trading_day(moment: float) -> bool:
    """New York's date at `moment` has a regular session (False outside the computed calendar)."""
    try:
        return us_equity_session(datetime.fromtimestamp(moment, UTC)) is not None
    except DataError:
        return False


def in_session(moment: float, *, pad_minutes: int = 0) -> bool:
    """`moment` is inside a regular session, widened by `pad_minutes` each side (False outside the calendar)."""
    try:
        session = us_equity_session(datetime.fromtimestamp(moment, UTC))
    except DataError:
        return False
    if session is None:
        return False
    opened = to_datetime(session.open_at).timestamp() - 60 * pad_minutes
    closed = to_datetime(session.close_at).timestamp() + 60 * pad_minutes
    return opened <= moment < closed


def iso(moment: float) -> str:
    """`2026-10-02T20:10:00Z` (whole seconds, UTC)."""
    return datetime.fromtimestamp(float(moment), UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def epoch(text: str | float | int | None) -> float | None:
    if text is None or text == "":
        return None
    if isinstance(text, (int, float)) and not isinstance(text, bool):
        return float(text)
    try:
        return datetime.fromisoformat(str(text).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None
