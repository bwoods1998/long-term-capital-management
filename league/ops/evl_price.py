"""PREREG-EVL-8's ALARMS (its section 10; league/ops/evl_health.py's cause `evl_price`), read-only from the lane's store and
px.sqlite beside it: the price lane and the meta-learners fail quietly (a run cut at its bound trades nothing, a recorder
that lags leaves no PX event at all), so the stall job says when

- A PART FAILED OR EXPIRED: an auction of the last `LOOK_HOURS` whose live window has passed (the open's 09:19:30 ET, the
  close's tau + 55 s for PX and the close - 11:20 for EVL-META-ON) with no LIVE decision of a PX run (a morning pass
  made PXU(D)) or of a meta-learner: never traded at that auction, decided later by a catch-up (the alarm says whether
  one has);
- A RECORDER LAGS: the morning pass of today's session not done by 09:13 ET, the 09:30 opens not read by 11:00 ET, or the
  last session's nightly bars not stored by 06:00 ET of the next weekday (league/events/pxdata.py `daily`), while the
  PX recorders run (the backfill done);
- THE PLACEBO AUDIT ALARMS (section 3.3): the latest screen's audit found 3 or more of a window's 8 placebos passed, or a
  PX control passed THE PX SCREEN without its control condition (THE CANARY): the pool carries an edge no selection made.

Counts and dates only: no record's, placebo's or sub-rule's figure is read into the alarm. Nothing is judged while
REGISTERED_AT_8 is None (this file registers nothing)."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from . import guard

CAUSE = "evl_price"
STORE = Path("events") / "events.sqlite"
PX_STORE = Path("events") / "px.sqlite"
NY = ZoneInfo("America/New_York")
LOOK_HOURS = 24.0
AM_BY = dt.time(9, 13)
MID_BY = dt.time(11, 0)
BARS_BY = dt.time(6, 0)
DOING = ("PREREG-EVL-8's runs go by themselves at section 4.6's times (the morning pass from 09:05 ET, PX-GAP-O1 and "
         "EVL-META-O1 on the lane's open receipt, PX-DROP-ON and PX-SURGE-ON from the close decision time, EVL-META-ON on "
         "the lane's close receipt), each under its own bound; one that fails or runs past it is never traded at that "
         "auction and is decided later by a catch-up (a reported shadow, never judged); the recorders' lag leaves no PX "
         "event; the placebo audit's alarm is a report line and moves no band. Each stall here is the captain's to read.")


def _ro(path: Path) -> sqlite3.Connection:
    db = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True, timeout=5.0)
    db.row_factory = sqlite3.Row
    return db


def _meta(db: sqlite3.Connection, table: str, key: str) -> str | None:
    try:
        row = db.execute(f"SELECT value FROM {table} WHERE key=?", (key,)).fetchone()
    except sqlite3.Error:
        return None
    return None if row is None else str(row[0])


def check(root: str | Path, now: float) -> dict[str, Any]:
    """The cause's check (league/ops/evl_health.py's shape). Not judged while REGISTERED_AT_8 is None or the lane holds
    no store."""
    from ..events import calendar as C
    from ..events import meta as MT
    from ..events import programs as P
    from ..events import px as PXL
    from ..events import store as S

    if not P.registers_8():
        return {"stalled": False, "judged": False, "what": "Nothing: PREREG-EVL-8 registers nothing (REGISTERED_AT_8 is "
                "None).", "numbers": {}, "doing": DOING, "owner_step": None, "onset": None}
    path = Path(root) / STORE
    if not path.exists():
        return {"stalled": False, "judged": False, "what": "Nothing: the event lane has no store yet.", "numbers": {},
                "doing": DOING, "owner_step": None, "onset": None}
    moment = dt.datetime.fromtimestamp(now, dt.timezone.utc)
    local = moment.astimezone(NY)
    problems: list[str] = []
    numbers: dict[str, Any] = {"failed": 0, "lag": 0, "audit": 0}
    with guard.readonly():
        db = _ro(path)
        pxpath = Path(root) / PX_STORE
        px = _ro(pxpath) if pxpath.exists() else None
        try:
            release = _meta(db, "meta", PXL.RELEASE_KEY)
            since = moment - dt.timedelta(hours=LOOK_HOURS)
            days = [str(r[0]) for r in db.execute("SELECT day FROM sessions WHERE day>=? AND day<=? ORDER BY day",
                                                 ((since - dt.timedelta(days=1)).astimezone(NY).date().isoformat(),
                                                  local.date().isoformat()))]
            for d in days:
                day = dt.date.fromisoformat(d)
                session = C.session(_View(db), day)
                if session is None:
                    continue
                for auction in ("o1", "on"):
                    tau = session.open_decide if auction == "o1" else session.close_decide
                    if release is None or tau < S.parse_iso(release) or tau < since:
                        continue
                    px_window = session.at(PXL.OPEN_UNTIL) if auction == "o1" else tau + PXL.CLOSE_DONE
                    if px is not None and moment >= px_window and \
                            _meta(px, "px_meta", PXL.AM_KEY.format(day=d)) is not None:
                        got = PXL.decided(px, day, auction)
                        if got is None or got.get("kind") != "live":
                            numbers["failed"] += 1
                            problems.append(f"the PX run of the {auction.upper()} auction of {d} was not decided live ("
                                            + ("decided since by its catch-up" if got is not None else "no catch-up yet")
                                            + ")")
                    meta_window = session.at(PXL.OPEN_UNTIL) if auction == "o1" else \
                        session.close_at - MT.META_CLOSE_UNTIL
                    prog = MT.learner(auction)
                    if prog is not None and moment >= meta_window:
                        got = MT.decided(db, prog, day) if MT.has_tables(db) else None
                        if got is None or got.get("kind") != "live":
                            numbers["failed"] += 1
                            problems.append(f"{prog.id}'s part of {d} was not decided live ("
                                            + ("decided since by its catch-up" if got is not None else "no catch-up yet")
                                            + ")")
            if px is not None and _meta(px, "px_meta", "px:backfill:done") is not None:
                today = local.date()
                session = C.session(_View(db), today)
                if session is not None and local.time() >= AM_BY and \
                        _meta(px, "px_meta", PXL.AM_KEY.format(day=today.isoformat())) is None:
                    numbers["lag"] += 1
                    problems.append(f"the morning pass of {today.isoformat()} is not done by 09:13 ET (no PX event of the "
                                    "session)")
                if session is not None and local.time() >= MID_BY and \
                        _meta(px, "px_meta", PXL.MID_KEY.format(day=today.isoformat())) is None:
                    numbers["lag"] += 1
                    problems.append(f"the 09:30 opens of {today.isoformat()} are not read by 11:00 ET")
                prev = db.execute("SELECT day FROM sessions WHERE day<? ORDER BY day DESC LIMIT 1",
                                  (today.isoformat(),)).fetchone()
                if prev is not None and local.time() >= BARS_BY and \
                        _meta(px, "px_meta", f"px:bars:{prev[0]}") is None:
                    numbers["lag"] += 1
                    problems.append(f"the nightly bars of {prev[0]} are not stored by 06:00 ET")
            row = db.execute("SELECT summary FROM receipts WHERE job='screen' AND finished_at IS NOT NULL ORDER BY id DESC "
                             "LIMIT 1").fetchone()
            if row is not None:
                try:
                    audit = (json.loads(row[0] or "{}") or {}).get("audit8")
                except ValueError:
                    audit = None
                if isinstance(audit, dict) and (int(audit.get("alarm") or 0) or int(audit.get("canary") or 0)):
                    numbers["audit"] = int(audit.get("alarm") or 0)
                    problems.append("the placebo audit alarms (section 3.3: placebos or a control passed THE PX SCREEN)")
        finally:
            db.close()
            if px is not None:
                px.close()
    if not problems:
        return {"stalled": False, "judged": True, "what": "PREREG-EVL-8's runs, recorders and placebo audit hold.",
                "numbers": numbers, "doing": DOING, "owner_step": None, "onset": None}
    return {"stalled": True, "judged": True, "what": "PREREG-EVL-8: " + "; ".join(problems[:6]) + ".",
            "numbers": numbers, "doing": DOING, "owner_step": None, "onset": None}


class _View:
    """A read-only connection in the shape league/events/calendar.py reads (`.db`)."""

    def __init__(self, db: sqlite3.Connection):
        self.db = db


__all__ = ["CAUSE", "DOING", "LOOK_HOURS", "check"]
