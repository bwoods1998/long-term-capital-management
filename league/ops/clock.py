"""The `clock` job (daily 11:00Z): the venue's clock and calendar against the House's own session calendar.

Reads Alpaca's `/v2/clock` and `/v2/calendar` through the gateway (GET only) and compares the next `SESSIONS` sessions
the venue lists with `ltcm.data.us_equity_session` over the same days: a day one side trades and the other does not,
or an open or close that differs, is a mismatch and a House warning (the House would trade, or refuse to, by the wrong
hours: Nov 1 is a DST change, and the computed holiday rules need a review each year). Writes `<state>/calendar.json`.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Iterable, Mapping
from zoneinfo import ZoneInfo

from ltcm.data import DataError, us_equity_session

from . import schedule as S
from .context import write_json

SESSIONS = 10
NEW_YORK = ZoneInfo("America/New_York")


def _venue_sessions(rows: Iterable[Mapping[str, Any]]) -> dict[str, tuple[str, str]]:
    """{date: (open "HH:MM", close "HH:MM")} New York time, from Alpaca's calendar rows."""
    out = {}
    for row in rows or []:
        day = str(row.get("date") or "")[:10]
        if day:
            out[day] = (str(row.get("open") or "")[:5], str(row.get("close") or "")[:5])
    return out


def _house_session(day: date) -> tuple[str, str] | None:
    session = us_equity_session(day)
    if session is None:
        return None
    hhmm = lambda stamp: datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone(NEW_YORK).strftime("%H:%M")  # noqa: E731
    return hhmm(session.open_at), hhmm(session.close_at)


def compare(venue_rows: Iterable[Mapping[str, Any]], start: date, *, sessions: int = SESSIONS) -> dict[str, Any]:
    """The first `sessions` venue sessions from `start` against the House's calendar over the same days."""
    venue = _venue_sessions(venue_rows)
    days = sorted(d for d in venue if d >= start.isoformat())[:sessions]
    mismatches, compared = [], []
    if not days:
        return {"sessions": [], "mismatches": [{"day": start.isoformat(), "why": "the venue listed no session"}]}
    day, last = start, date.fromisoformat(days[-1])
    while day <= last:
        iso = day.isoformat()
        try:
            house = _house_session(day)
        except DataError as exc:
            mismatches.append({"day": iso, "why": f"the House's calendar cannot say: {exc}"})
            day += timedelta(days=1)
            continue
        theirs = venue.get(iso)
        row = {"day": iso, "house": list(house) if house else None, "venue": list(theirs) if theirs else None}
        compared.append(row)
        if (house is None) != (theirs is None):
            mismatches.append({**row, "why": "the venue trades and the House does not" if theirs else
                                             "the House trades and the venue does not"})
        elif house is not None and theirs is not None and tuple(house) != tuple(theirs):
            mismatches.append({**row, "why": "the session's hours differ"})
        day += timedelta(days=1)
    return {"sessions": compared, "mismatches": mismatches}


def run(ctx: Any) -> dict[str, Any]:
    now = ctx.now()
    today = datetime.fromtimestamp(now, NEW_YORK).date()
    clock = ctx.gateway.get("/v1/alpaca/v2/clock") or {}
    rows = ctx.gateway.get("/v1/alpaca/v2/calendar", {"start": today.isoformat(),
                                                       "end": (today + timedelta(days=30)).isoformat()}) or []
    result = compare(rows if isinstance(rows, list) else [], today)
    is_open = clock.get("is_open") if isinstance(clock, dict) else None
    house_open = S.in_session(now)
    if isinstance(is_open, bool) and is_open != house_open:
        result["mismatches"].append({"day": today.isoformat(), "why": f"the venue's clock says open={is_open}, "
                                                                      f"the House's calendar says {house_open}"})
    value = {"at": S.iso(now), "clock": {k: clock.get(k) for k in ("timestamp", "is_open", "next_open", "next_close")}
             if isinstance(clock, dict) else None, **result, "ok": not result["mismatches"]}
    write_json(ctx.root / "calendar.json", value)
    for row in result["mismatches"][:5]:
        ctx.alert("warning", f"the venue calendar and the House's disagree on {row['day']}: {row['why']}")
    return {"ok": value["ok"], "sessions": len(result["sessions"]), "mismatches": result["mismatches"][:10]}
