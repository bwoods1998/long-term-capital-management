"""THE EVENT LANE'S OWN STALL CAUSES and its DAILY ONE-SCREEN REPORT (release R1, the owner's goal of Oct 19, 2026, item 7:
"alarms on stalls, missed events, fill gaps, cap breaches; a daily one-screen report"), judged for the `stall` job
(league/ops/stall.py), which raises them like any cause and mails the report in its daily notice.

THE FOUR CAUSES, each read from the lane's own receipts in `<state>/events/events.sqlite` (league/events/store.py; every
open `mode=ro`, inside `guard.readonly()`), on the House's NYSE calendar (`ltcm.data.us_equity_session`, so a lane whose
own calendar is empty is judged all the same), with no recursion into a judge (no program is run here, no verdict asked,
no outcome computed):

- `evl_record`: no record pass (a receipt `record`, finished `ok`) in the last `RECORD_MINUTES` (30). The recorder runs
  round the clock (PREREG-EVL-1 section 3: LIVE news is stored within 10 minutes of its creation), so this is judged at
  every hour. The numbers say how many passes of the last 30 minutes failed or carried a news error.
- `evl_decide`: a scheduled decision not done `DECIDE_GRACE_MINUTES` (10) after its time: the open decision (09:15 ET)
  and the close decision (the close - 14 minutes) of every session, for each entry kind a registered program uses
  (league/events/programs.py `PROGRAMS`, data rows: a new program needs no code here), over the last
  `DECIDE_LOOKBACK_HOURS` (24). Done = a receipt `decide-<open|close>:<day>` finished `ok`; one still `pending` (a
  reading program waits on a verdict) is not done, and is named so.
- `evl_verdicts`: more than `VERDICT_SHARE` (20%) of the verdicts the latest session's decisions needed got no answer,
  `DECIDE_GRACE_MINUTES` after the decision: the latest receipt of each of that session's decisions carries its tally
  (league/events/run.py `decide_open`: `verdicts: {needed, answered}`, the distinct verdicts the decision's reading
  programs need and how many are stored). PREREG-EVL-1 section 4 stores an answer only (ok, unparsed or refused), so
  a verdict asked and not answered by then is exactly one with nothing stored.
- `evl_score`: a session not scored by 23:00 ET (`SCORE_BY`): the latest session whose 23:00 ET has passed has no `score`
  receipt finished `ok` that started after its close + 16 minutes (the SIP tape's delay, league/events/score.py
  `TAPE_DELAY`), while an intent due by that session is still unsettled (planned or entered). A night with nothing due is
  no stall.

WHEN THEY ARE JUDGED: only while the lane runs on the House (league/config.json `events.enabled` true: release R1's
switch, league/service.py) and the owner has not switched them off (`<state>/ops.json` `stall.evl` false, as
`stall.elane` switches the equity lanes' four). A lane that is on and has no store yet has recorded nothing (`evl_record`
stands); a store that cannot be read is "Not judged" and an entry of the job's `errors`. None has an owner step: each is
the House's to fix (a release or the captain), told at the job's INFO pace and a House warning; a Claude meter that ran
dry is `runway_claude`'s step, the kill switch `kill_on`'s.

THE DAILY REPORT (`report_due`, `report_facts`): on each session day, at the first stall run from `REPORT_AFTER` (22:00
ET, after the lane's nightly score, screen and report), league/events/report.py's figures for the day, cut to counts and
figures (`report_facts`: events read by family, the day's verdicts and their cost, each program's intents, settled
events, shadow P&L at a $100 notional an event, real fills (none before release R2), its evidence status and next look,
the expected false passes, the day's metered costs from budget.json and the jobs missed or failed), ride the stall
notice (`report` beside its `causes`: one more section of the same mail; with no cause standing the notice carries the
report alone). The gateway composes the words (gateway/lib/email.mjs `stallReport`) and echoes only counts, dollar and
basis-point figures, dates and the programs' own ids: no headline, no document text, no symbol, no price. Told once a
day (`stall.json` `report`: the day told), kept out of the job's receipt and of stall.json (they carry the day and
whether it rode, never a figure), so the outcomes reach the owner's mail only.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import sqlite3
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from . import guard
from . import schedule as S

CAUSES = ("evl_record", "evl_decide", "evl_verdicts", "evl_score")
#: The stall job's key in `<state>/ops.json` that switches these four off: `{"stall": {"evl": false}}`.
SWITCH = "evl"
#: The lane's state under the House's state root (league/events/store.py `DB_NAME`).
STORE = Path("events") / "events.sqlite"
NY = ZoneInfo("America/New_York")
RECORD_MINUTES = 30
DECIDE_GRACE_MINUTES = 10
DECIDE_LOOKBACK_HOURS = 24.0
#: The decisions' times (league/events/calendar.py): 09:15 ET, and the close - 14 minutes.
OPEN_DECIDE = dt.time(9, 15)
CLOSE_DECIDE_BEFORE = dt.timedelta(minutes=14)
VERDICT_SHARE = 0.20
SCORE_BY = dt.time(23, 0)
#: The SIP tape's delay the score job waits out after a session's close (league/events/score.py `TAPE_DELAY`).
TAPE_DELAY = dt.timedelta(minutes=16)
#: The daily report rides the first stall run from this New York time of a session day, and no later than
#: `REPORT_STALE_HOURS` after it (08:00 ET the next morning: a House down all night tells it at its first run before then,
#: and after that the next session's report is the one told).
REPORT_AFTER = dt.time(22, 0)
REPORT_STALE_HOURS = 10.0
#: The shadow tally's notional an event (the site's `record.forward`, release R1 WP4: $100 an event).
NOTIONAL_USD = 100.0
#: At most this many programs ride the report (the gateway's own cap).
REPORT_PROGRAMS = 32
DOING = {
    "not_judged": "Nothing: the cause is not judged while it reads so.",
    "evl_record": ("The House's tick runs a record pass every 2 minutes (EDGAR's current 8-K and Form 4 feeds, Alpaca's "
                   "news through the gateway), each bounded; a filing the current feeds missed is read from EDGAR's daily "
                   "index by the backfill, and the shadow record decides every event by its knowable time whenever it was "
                   "stored (PREREG-EVL-1 section 3): an outage removes nothing from the shadow record, but live news "
                   "stored late is not LIVE, and real money can use only what was stored before its decision."),
    "evl_decide": ("The House's tick runs a due decision before any other task of the lane, and the lane's catch-up decides "
                   "a missed one at its scheduled time from what was knowable then (the shadow rule); a decision still "
                   "pending decides once its verdicts are stored. Real money (release R2) would miss its auction."),
    "evl_verdicts": ("The lane asks each verdict as soon as its event is recorded and eligible, and again before each "
                     "decision, at most 3 calls a pass; a call with no answer stores nothing and is asked again "
                     "(PREREG-EVL-1 section 4). Its reading programs wait (pending) until every verdict they need is "
                     "stored, then decide by the shadow rule. A Claude meter that ran dry is the runway_claude cause, "
                     "the kill switch kill_on."),
    "evl_score": ("The lane's nightly scores every due intent at the listing exchange's auction prints once the tape is "
                  "16 minutes old (league/events/score.py), and its screen and report follow; the next night's run "
                  "scores what this one missed. The screen's looks wait for every block they cover (PREREG-EVL-1 "
                  "section 7): late data delays a look's computation, never its as-of date."),
}


def _get(ctx: Any, name: str, default: Any = None) -> Any:
    if isinstance(ctx, Mapping):
        return ctx.get(name, default)
    return getattr(ctx, name, default)


def switched_off(ctx: Any) -> bool:
    """THE OWNER'S SWITCH (`<state>/ops.json` `stall.evl` false): the four are not judged; absent, they are."""
    settings = _get(ctx, "settings")
    block = settings.get("stall") if isinstance(settings, Mapping) else None
    return isinstance(block, Mapping) and block.get(SWITCH) is False


def lane_on(ctx: Any) -> bool:
    """The lane runs on the House: league/config.json `events.enabled` true (release R1; default false)."""
    config = _get(ctx, "config")
    block = config.get("events") if isinstance(config, Mapping) else None
    return isinstance(block, Mapping) and block.get("enabled") is True


def _not_judged(why: str) -> dict[str, Any]:
    return {"stalled": False, "judged": False, "what": f"Not judged: {why}.", "numbers": {"judged": False},
            "doing": DOING["not_judged"], "owner_step": None, "onset": None}


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _loads(text: Any) -> Any:
    try:
        return json.loads(text) if isinstance(text, str) and text else None
    except ValueError:
        return None


# ---------------------------------------------------------------------------------------------- the calendar
def sessions(first: dt.date, last: dt.date) -> list[dict[str, Any]]:
    """The House's NYSE sessions from `first` to `last`: [{day, open_at, close_at}] (epochs), oldest first."""
    from ltcm.data import us_equity_session

    out, day = [], first
    while day <= last:
        try:
            session = us_equity_session(day)
        except Exception:  # noqa: BLE001 - a year the calendar does not hold has no session here
            session = None
        if session is not None:
            out.append({"day": day, "open_at": S.epoch(session.open_at), "close_at": S.epoch(session.close_at)})
        day += dt.timedelta(days=1)
    return out


def _ny(day: dt.date, wall: dt.time) -> float:
    return dt.datetime.combine(day, wall, tzinfo=NY).timestamp()


def decisions(now: float, kinds: tuple[str, ...]) -> list[dict[str, Any]]:
    """The scheduled decisions whose time is in the last `DECIDE_LOOKBACK_HOURS` and `DECIDE_GRACE_MINUTES` past:
    [{kind, day, at}] (`at` epoch), oldest first."""
    today = dt.datetime.fromtimestamp(now, NY).date()
    out = []
    for s in sessions(today - dt.timedelta(days=4), today):
        for kind in kinds:
            if kind == "open":
                at = _ny(s["day"], OPEN_DECIDE)
            elif s["close_at"] is not None:
                at = s["close_at"] - CLOSE_DECIDE_BEFORE.total_seconds()
            else:
                continue
            if now - DECIDE_LOOKBACK_HOURS * 3600 <= at <= now - DECIDE_GRACE_MINUTES * 60:
                out.append({"kind": kind, "day": s["day"].isoformat(), "at": at})
    return sorted(out, key=lambda d: d["at"])


def entry_kinds() -> tuple[str, ...]:
    """The decisions the registered programs need (league/events/programs.py `PROGRAMS`: each row's `entry_at`)."""
    try:
        from ..events import programs as P

        kinds = {str(p.entry_at) for p in P.PROGRAMS}
    except Exception:  # noqa: BLE001 - both, when the table cannot be read
        kinds = {"open", "close"}
    return tuple(k for k in ("open", "close") if k in kinds)


# ---------------------------------------------------------------------------------------------- the reads
def facts(root: str | Path, now: float) -> dict[str, Any]:
    """Every receipt the four causes read and the unsettled due intents, in one read-only transaction:
    {record: [...], decide: {job: [...]}, score: [...], due: [(exit_day, n)]}."""
    since = S.iso(now - 5 * 86400)

    def read(db: sqlite3.Connection) -> dict[str, Any]:
        rows = guard.rows(db, "SELECT id, job, started_at, finished_at, status, summary FROM receipts WHERE started_at>=? "
                              "AND (job='record' OR job LIKE 'record:%' OR job LIKE 'decide-%' OR job='score' OR job LIKE "
                              "'score:%') ORDER BY id", (since,))
        due = guard.rows(db, "SELECT exit_day, COUNT(*) AS n FROM intents WHERE status IN ('planned', 'entered') GROUP BY "
                             "exit_day", ())
        out: dict[str, Any] = {"record": [], "decide": {}, "score": [], "due": [(r["exit_day"], int(r["n"])) for r in due]}
        for r in rows:
            job = str(r["job"])
            if job == "record" or job.startswith("record:"):
                out["record"].append(r)
            elif job == "score" or job.startswith("score:"):
                out["score"].append(r)
            else:
                out["decide"].setdefault(job, []).append(r)
        return out
    return guard.read(Path(root) / STORE, read)


# ---------------------------------------------------------------------------------------------- the causes
def _record(now: float, f: Mapping[str, Any]) -> dict[str, Any]:
    window = now - RECORD_MINUTES * 60
    ok = [r for r in f["record"] if r["status"] == "ok" and S.epoch(r["finished_at"]) is not None]
    last = max((S.epoch(r["finished_at"]) for r in ok), default=None)
    recent = [r for r in f["record"] if (S.epoch(r["started_at"]) or 0.0) >= window]
    failed = [r for r in recent if r["finished_at"] is not None and r["status"] != "ok"]
    news = sum(1 for r in recent if r["status"] == "ok" and isinstance((_loads(r["summary"]) or {}).get("news"), Mapping)
               and (_loads(r["summary"]) or {})["news"].get("error"))
    stalled = last is None or last < window
    if last is None:
        what = "The event lane has finished no record pass on record (none in the last 5 days)."
    elif stalled:
        what = (f"The event lane finished no record pass in the last {RECORD_MINUTES} minutes: its last ended "
                f"{S.iso(last)}, {round((now - last) / 60)} minutes ago.")
    else:
        what = f"The event lane's last record pass ended {S.iso(last)}."
    if news:
        what += f" {news} of the last {RECORD_MINUTES} minutes' passes could not read the news."
    return {"stalled": stalled, "judged": True, "what": what,
            "numbers": {"last_record_at": None if last is None else S.iso(last),
                        "minutes_since_record": None if last is None else round((now - last) / 60.0, 1),
                        f"passes_{RECORD_MINUTES}m": sum(1 for r in recent if r["status"] == "ok"),
                        f"failed_passes_{RECORD_MINUTES}m": len(failed), f"news_errors_{RECORD_MINUTES}m": news},
            "doing": DOING["evl_record"], "owner_step": None, "onset": last}


def _decide(now: float, f: Mapping[str, Any], kinds: tuple[str, ...]) -> dict[str, Any]:
    due = decisions(now, kinds)
    missed, waiting = [], []
    for d in due:
        rows = f["decide"].get(f"decide-{d['kind']}:{d['day']}", [])
        if any(r["status"] == "ok" for r in rows):
            continue
        missed.append(d)
        if rows and rows[-1]["status"] == "pending":
            waiting.append(d)
    first = missed[0] if missed else None
    if first is None:
        what = (f"Every scheduled decision of the last {DECIDE_LOOKBACK_HOURS:g} h is done ({len(due)})." if due else
                f"No decision was due in the last {DECIDE_LOOKBACK_HOURS:g} h.")
    else:
        when = dt.datetime.fromtimestamp(first["at"], NY).strftime("%H:%M")
        what = (f"The event lane's {first['kind']} decision of {first['day']} ({when} ET) is not done "
                f"{DECIDE_GRACE_MINUTES} minutes after its time"
                + (" (it waits on verdicts)" if first in waiting else " (no receipt of it finished)")
                + (f"; {len(missed)} decisions of the last {DECIDE_LOOKBACK_HOURS:g} h are missed in all." if len(missed) > 1
                   else "."))
    return {"stalled": bool(missed), "judged": True, "what": what,
            "numbers": {"decisions_due": len(due), "missed": len(missed), "waiting_on_verdicts": len(waiting),
                        "first_missed": None if first is None else f"{first['kind']}:{first['day']}",
                        "first_missed_at": None if first is None else S.iso(first["at"])},
            "doing": DOING["evl_decide"], "owner_step": None, "onset": None if first is None else first["at"]}


def _verdicts(now: float, f: Mapping[str, Any], kinds: tuple[str, ...]) -> dict[str, Any]:
    due = decisions(now, kinds)
    day = due[-1]["day"] if due else None
    needed = answered = 0
    read = []
    for d in due:
        if d["day"] != day:
            continue
        rows = f["decide"].get(f"decide-{d['kind']}:{d['day']}", [])
        tally = (_loads(rows[-1]["summary"]) or {}).get("verdicts") if rows else None
        if not isinstance(tally, Mapping):
            continue
        n, a = _num(tally.get("needed")), _num(tally.get("answered"))
        if n is None or a is None or n < 0 or not 0 <= a <= n:
            continue
        needed, answered = needed + int(n), answered + int(a)
        read.append(d["kind"])
    missing = needed - answered
    share = missing / needed if needed else None
    stalled = share is not None and share > VERDICT_SHARE
    if day is None:
        what = f"No decision was due in the last {DECIDE_LOOKBACK_HOURS:g} h: no verdict to judge."
    elif not read:
        what = f"No decision of {day} carries a verdict tally yet (a decision not done is evl_decide's)."
    elif needed == 0:
        what = f"The decisions of {day} needed no verdict."
    else:
        what = (f"{missing} of the {needed} verdicts the event lane's decisions of {day} needed have no answer "
                f"({share:.0%}{', over ' + format(VERDICT_SHARE, '.0%') if stalled else ''}).")
    return {"stalled": stalled, "judged": True, "what": what,
            "numbers": {"day": day, "needed": needed, "answered": answered, "unanswered": missing,
                        "unanswered_share": None if share is None else round(share, 3),
                        "decisions_read": ",".join(read) or "none"},
            "doing": DOING["evl_verdicts"], "owner_step": None, "onset": None}


def _score(now: float, f: Mapping[str, Any]) -> dict[str, Any]:
    today = dt.datetime.fromtimestamp(now, NY).date()
    latest = None
    for s in reversed(sessions(today - dt.timedelta(days=10), today)):
        if _ny(s["day"], SCORE_BY) <= now:
            latest = s
            break
    if latest is None:
        return _not_judged("no session in the last 10 days has passed its 23:00 ET")
    after = latest["close_at"] + TAPE_DELAY.total_seconds()
    runs = [r for r in f["score"] if (S.epoch(r["started_at"]) or 0.0) >= after]
    scored = any(r["status"] == "ok" for r in runs)
    day = latest["day"].isoformat()
    unsettled = sum(n for exit_day, n in f["due"] if exit_day is not None and str(exit_day) <= day)
    last = f["score"][-1] if f["score"] else None
    stalled = not scored and unsettled > 0
    if scored:
        what = f"The session of {day} was scored after its close."
    elif unsettled:
        what = (f"The session of {day} was not scored by 23:00 ET: no score pass finished ok after its close, and "
                f"{unsettled} intents due by it are unsettled.")
    else:
        what = f"No intent was due by the session of {day}: nothing to score."
    return {"stalled": stalled, "judged": True, "what": what,
            "numbers": {"day": day, "scored": scored, "unsettled_due": unsettled,
                        "last_score_at": None if last is None else last["started_at"],
                        "last_score_status": None if last is None else str(last["status"] or "running")[:20]},
            "doing": DOING["evl_score"], "owner_step": None,
            "onset": _ny(latest["day"], SCORE_BY) if stalled else None}


def checks(ctx: Any, root: str | Path, now: float, *, errors: list[str] | None = None) -> dict[str, dict[str, Any]]:
    """THE STALL JOB'S CALL (league/ops/stall.py `run`): the four causes' checks (the module docstring). Never raises: a
    store that cannot be read is "Not judged" and an entry of `errors`."""
    try:
        if switched_off(ctx):
            return {c: _not_judged(f"switched off (ops.json stall.{SWITCH} is false)") for c in CAUSES}
        if not lane_on(ctx):
            return {c: _not_judged("the event lane does not run on the House (league/config.json events.enabled)")
                    for c in CAUSES}
        if not (Path(root) / STORE).exists():
            f: dict[str, Any] = {"record": [], "decide": {}, "score": [], "due": []}
        else:
            with guard.readonly():
                f = facts(root, now)
        kinds = entry_kinds()
        return {"evl_record": _record(now, f), "evl_decide": _decide(now, f, kinds),
                "evl_verdicts": _verdicts(now, f, kinds), "evl_score": _score(now, f)}
    except Exception as exc:  # noqa: BLE001 - an alarm that cannot see says so, and the rest of the job goes on
        if errors is not None:
            errors.append(f"the event lane's store could not be read ({type(exc).__name__}): its four causes are not judged")
        return {c: _not_judged(f"the event lane's store could not be read ({type(exc).__name__})") for c in CAUSES}


# ---------------------------------------------------------------------------------------------- the daily report
class ReadOnlyStore:
    """league/events/store.py's `Store` as league/events/report.py reads it (`db`, `meta`, `root`), over a read-only
    connection: the stall job opens nothing for writing."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.db = guard.connect_ro(self.root / "events.sqlite")

    def meta(self, key: str) -> str | None:
        row = self.db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return None if row is None else str(row[0])

    def close(self) -> None:
        self.db.close()


def report_day(now: float) -> str | None:
    """The session day whose report is due at `now`: the latest session whose `REPORT_AFTER` has passed, at most
    `REPORT_STALE_HOURS` ago; None when none is."""
    today = dt.datetime.fromtimestamp(now, NY).date()
    for s in reversed(sessions(today - dt.timedelta(days=4), today)):
        at = _ny(s["day"], REPORT_AFTER)
        if at <= now:
            return s["day"].isoformat() if now - at <= REPORT_STALE_HOURS * 3600 else None
    return None


def _round(value: Any, places: int) -> float | None:
    number = _num(value)
    return None if number is None else round(number, places)


def report_facts(report: Mapping[str, Any], budget: Mapping[str, Any] | None) -> dict[str, Any]:
    """The report block of the stall notice from league/events/report.py `build` (and budget.json, rule 3's): counts
    and figures only, each in the shape the gateway echoes (gateway/lib/email.mjs `stallReport`)."""
    ev, vd = report.get("events") or {}, report.get("verdicts") or {}

    def total(name: str, key: str = "total") -> int:
        return int((ev.get(name) or {}).get(key) or 0)
    programs = []
    for p in (report.get("programs") or [])[:REPORT_PROGRAMS]:
        st, today = p.get("settled") or {}, p.get("intents_today") or {}
        nl, ll = p.get("next_look") or {}, p.get("last_look")
        n, mean_r = int(st.get("n") or 0), _num(st.get("mean_r"))
        last = "none" if not ll else ("pass" if ll.get("passed") else ("fail" if ll.get("held") else "skipped"))
        programs.append({
            "id": str(p.get("program")), "version": int(p.get("version") or 1), "seatable": bool(p.get("seatable")),
            "intents": int(sum(int(v or 0) for v in today.values())), "skipped": int(today.get("skipped") or 0),
            "settled": n, "settled_today": int(p.get("settled_today") or 0), "tradable": int(st.get("n_tradable") or 0),
            "shadow_pnl_usd": None if mean_r is None else round(NOTIONAL_USD * mean_r * n, 2),
            "mean_r_bp": _round(None if mean_r is None else mean_r * 1e4, 1),
            "mean_a_bp": _round(None if _num(st.get("mean_a")) is None else _num(st.get("mean_a")) * 1e4, 1),
            "real_n": None, "real_pnl_usd": None,
            "next_look": nl.get("k"), "next_look_session": nl.get("at_sessions"), "sessions": nl.get("sessions"),
            "last_look": last, "held_looks": int(p.get("held_looks") or 0)})
    meters = (budget or {}).get("meters") if isinstance((budget or {}).get("meters"), Mapping) else {}
    cap = (budget or {}).get("cap") if isinstance((budget or {}).get("cap"), Mapping) else {}
    burns = [_num((meters.get(m) or {}).get("burn_usd_day")) for m in ("sail", "claude")]
    usd = sum(_num(v.get("usd")) or 0.0 for v in vd.values() if isinstance(v, Mapping))
    efp = report.get("expected_false_passes") or {}
    jobs = report.get("jobs") or {}
    return {
        "day": str(report.get("day")),
        "events": {"8k_202": total("8-K 2.02"), "8k_other": total("8-K other"), "form4": total("Form 4"),
                   "news": total("news"), "failed": sum(total(f, "failed") for f in ("8-K 2.02", "8-K other", "Form 4"))},
        "verdicts": {s: int((vd.get(s) or {}).get("n") or 0) for s in ("ok", "unparsed", "refused")}
                    | {"usd": round(usd, 2)},
        "programs": programs,
        "costs": {"cap_usd_day": _round(cap.get("cap_usd_day"), 2), "fixed_usd_day": _round(cap.get("fixed_usd_day"), 2),
                  "lane_usd_day": _round(cap.get("lane_usd_day"), 2),
                  "research_usd_day": _round((budget or {}).get("research_usd_day"), 2),
                  "metered_usd_day": None if None in burns else round(sum(burns), 2)},
        "expected_false_passes": _round(efp.get("expected"), 2), "seatable_versions": int(efp.get("versions") or 0),
        "jobs": {"missed": len(jobs.get("missed") or []), "failed": len(jobs.get("failed") or [])},
    }


def report_due(ctx: Any, root: str | Path, now: float, *, told: Any = None, budget: Mapping[str, Any] | None = None,
               errors: list[str] | None = None) -> dict[str, Any] | None:
    """The day's report block when one is due at `now` and the stall job has not told that day (`told`: stall.json
    `report`), else None. Only while the lane runs on the House and its store is there; a report that cannot be built
    is an entry of `errors` and no report (the notice goes on without it)."""
    if switched_off(ctx) or not lane_on(ctx) or not (Path(root) / STORE).exists():
        return None
    day = report_day(now)
    if day is None or (isinstance(told, Mapping) and told.get("day") == day):
        return None
    try:
        from ..events import report as RP

        with guard.readonly():
            store = ReadOnlyStore(Path(root) / STORE.parent)
            try:
                built = RP.build(store, dt.date.fromisoformat(day),
                                 now=dt.datetime.fromtimestamp(now, dt.timezone.utc))
            finally:
                store.close()
        return report_facts(built, budget)
    except Exception as exc:  # noqa: BLE001 - the notice goes on without the report
        if errors is not None:
            errors.append(f"the event lane's daily report could not be built ({type(exc).__name__})")
        return None


__all__ = ["CAUSES", "SWITCH", "STORE", "checks", "facts", "switched_off", "lane_on", "decisions", "entry_kinds",
           "sessions", "report_due", "report_facts", "report_day", "ReadOnlyStore", "RECORD_MINUTES",
           "DECIDE_GRACE_MINUTES", "DECIDE_LOOKBACK_HOURS", "VERDICT_SHARE", "SCORE_BY", "REPORT_AFTER", "NOTIONAL_USD"]
