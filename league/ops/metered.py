"""MEASURED METERED SPEND (release 1019c; the review of r1/alarms, its majors 1 and 4; the owner's goal of Oct 19, 2026,
items 4 and 5: "metered compute <= $5 a day plus half the trailing week's realized net profit, never above $25", "alarms
on ... cap breaches", the daily report's "costs"): what the metered compute of each New York day COST, read from the meters
themselves, never from the budget's lines (budget.json says what may be spent, this says what was).

THE METERS, each read by the stall job at every run (:20 and :50, league/ops/stall.py) into `<state>/metered.json`:
- `sail`: THE SAIL GUARD'S OWN METER (league/swarm/guard.py `_metered`; the swarm store's kv `guard`: `last.metered_spent`,
  every fall of Sail's balance between two good readings since the guard first ran, as of `last_good.at`): every box and
  model call on the Sail account, the House box and the data box among them, booked or not;
- `claude`: THE GATEWAY'S CLAUDE METER (`GET /v1/health` `claude.settled_usd`, spent less the holds in flight): every
  settled Claude call through the gateway, the event lane's verdicts and every role alike;
- `openai`: the gateway's OpenAI meter (`frontier.settled_usd` of its month; a new month carries on from the old month's
  `previous.settled_usd`): closed by the budget (no room), counted whenever it moves;
- `cloudflare`: the Workers plan, a fixed fee (`budget.CLOUDFLARE_USD_DAY` for every day); `data`: `budget.DATA_USD_DAY`.

Each cumulative meter is kept as THE LEDGER'S OWN RUNNING TOTAL (`series`: [epoch, total] pairs, oldest first, the last
`KEEP_HOURS`), which only rises: a step between two readings is the meter's rise (a fall, a meter reset, counts nothing,
as the guard counts a top-up). A meter's spend over [a, b] is its total at b less its total at a, each read on the line
between the two readings around it; a span outside the readings is measured from the first reading or to the last one,
and says so (`covered`). Nothing here is ever an estimate of a line: a meter with no reading in a day is `None` for it.

A DAY (`day_figure`, a New York day, 00:00-24:00 ET): {day, sail, claude, openai, cloudflare, data, spent (their sum;
None while a cumulative meter has no reading in the day), from, to (what the readings cover), whole (the day covered from
its start to its end), cap (THE LOWEST cap budget.json gave during the day, `caps`; the rule's no-profit $5 when none
could be read: FAIL CLOSED), over (spent above the cap by more than a cent)}. The stall job's `cap_breach` reads today's
figure so far and yesterday's whole one; the daily report reads the report day's. Read-only on every store; it writes
`metered.json` only. Standard library only.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from . import budget as B
from . import guard

NY = ZoneInfo("America/New_York")
FILE = "metered.json"
SCHEMA = 1
METERS = ("sail", "claude", "openai")
#: The readings each meter keeps (hours): yesterday whole and today, with room for a House down a day.
KEEP_HOURS = 72
#: The New York days' caps kept (`caps`), and the finished days' figures (`days`).
KEEP_DAYS = 400
#: Spend above the cap by more than this is over it (a cent: the meters' own rounding never alarms).
OVER_EPSILON = 0.01


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _iso(epoch: float) -> str:
    return dt.datetime.fromtimestamp(float(epoch), dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ny_day(epoch: float) -> dt.date:
    return dt.datetime.fromtimestamp(float(epoch), NY).date()


def day_bounds(day: dt.date) -> tuple[float, float]:
    """00:00 and 24:00 New York of `day`, epochs (a day of 23 or 25 hours at a clock change)."""
    start = dt.datetime.combine(day, dt.time(0, 0), tzinfo=NY).timestamp()
    end = dt.datetime.combine(day + dt.timedelta(days=1), dt.time(0, 0), tzinfo=NY).timestamp()
    return start, end


# ---------------------------------------------------------------------------------------------- the readings
def sail_reading(root: str | Path) -> tuple[float, float] | None:
    """(when, the guard's cumulative meter) from the swarm store's kv `guard`, read-only; None with none."""
    path = Path(root) / "swarm.sqlite"
    if not path.exists():
        return None

    def read(db: Any) -> Any:
        row = db.execute("SELECT value FROM kv WHERE key='guard'").fetchone()
        return None if row is None else row[0]
    try:
        raw = guard.read(path, read)
        state = json.loads(raw) if isinstance(raw, str) else None
    except Exception:  # noqa: BLE001 - no reading this run
        return None
    if not isinstance(state, Mapping):
        return None
    last = state.get("last") if isinstance(state.get("last"), Mapping) else {}
    good = state.get("last_good") if isinstance(state.get("last_good"), Mapping) else {}
    value, at = _num(last.get("metered_spent")), _num(good.get("at"))
    if value is None or at is None or value < 0:
        return None
    return at, value


def claude_reading(health: Any) -> float | None:
    """The gateway's settled Claude dollars (`/v1/health` `claude`: `settled_usd`, else spent less in flight)."""
    block = health.get("claude") if isinstance(health, Mapping) else None
    if not isinstance(block, Mapping):
        return None
    settled = _num(block.get("settled_usd"))
    if settled is None:
        spent, inflight = _num(block.get("spent_usd")), _num(block.get("inflight_usd"))
        settled = None if spent is None else spent - (inflight or 0.0)
    return None if settled is None or settled < 0 else settled


def openai_reading(health: Any) -> dict[str, Any] | None:
    """The gateway's OpenAI month (`/v1/health` `frontier`): {month, settled, previous: {month, settled} | None}."""
    block = health.get("frontier") if isinstance(health, Mapping) else None
    if not isinstance(block, Mapping) or not isinstance(block.get("month"), str):
        return None
    settled = _num(block.get("settled_usd"))
    if settled is None:
        settled = _num(block.get("spent_usd"))
    if settled is None or settled < 0:
        return None
    prev = block.get("previous") if isinstance(block.get("previous"), Mapping) else None
    previous = None
    if prev is not None and isinstance(prev.get("month"), str):
        value = _num(prev.get("settled_usd"))
        value = _num(prev.get("spent_usd")) if value is None else value
        previous = None if value is None else {"month": prev["month"], "settled": value}
    return {"month": block["month"], "settled": settled, "previous": previous}


# ---------------------------------------------------------------------------------------------- the ledger
def empty() -> dict[str, Any]:
    return {"schema": SCHEMA, "series": {m: [] for m in METERS}, "raw": {m: None for m in METERS}, "caps": {},
            "days": {}}


def load(root: str | Path) -> dict[str, Any]:
    """`<root>/metered.json`, or an empty ledger (none, unreadable, another schema)."""
    try:
        data = json.loads((Path(root) / FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return empty()
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        return empty()
    out = empty()
    for m in METERS:
        rows = (data.get("series") or {}).get(m) if isinstance(data.get("series"), Mapping) else None
        out["series"][m] = [[float(t), float(v)] for t, v in (rows or [])
                            if _num(t) is not None and _num(v) is not None] if isinstance(rows, list) else []
        out["raw"][m] = (data.get("raw") or {}).get(m) if isinstance(data.get("raw"), Mapping) else None
    out["caps"] = {str(k): float(v) for k, v in (data.get("caps") or {}).items() if _num(v) is not None} \
        if isinstance(data.get("caps"), Mapping) else {}
    out["days"] = {str(k): dict(v) for k, v in (data.get("days") or {}).items() if isinstance(v, Mapping)} \
        if isinstance(data.get("days"), Mapping) else {}
    return out


def save(root: str | Path, ledger: Mapping[str, Any]) -> None:
    """`<root>/metered.json`, atomically, readable by the House's own user only (as stall.json)."""
    path = Path(root) / FILE
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(ledger, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def _step(meter: str, before: Any, now: Any) -> float:
    """The rise of a meter between two raw readings (never under 0: a fall or a reset is no spend)."""
    if meter == "openai":
        if not isinstance(before, Mapping) or not isinstance(now, Mapping):
            return 0.0
        if before.get("month") == now.get("month"):
            return max(0.0, float(now["settled"]) - float(before["settled"]))
        prev = now.get("previous")
        if isinstance(prev, Mapping) and prev.get("month") == before.get("month"):
            return max(0.0, float(prev["settled"]) - float(before["settled"])) + max(0.0, float(now["settled"]))
        return max(0.0, float(now["settled"]))  # a month the ledger never saw end: this month's alone
    a, b = _num(before), _num(now)
    return 0.0 if a is None or b is None else max(0.0, b - a)


def observe(ledger: dict[str, Any], *, now: float, sail: tuple[float, float] | None, claude: float | None,
            openai: Mapping[str, Any] | None, cap: float | None) -> dict[str, Any]:
    """One stall run's readings into the ledger (in place, and returned): each meter's rise since its last raw reading
    added to its running total at the reading's time (Sail's: the guard's own reading time; the gateway's: now), the
    day's cap kept at its lowest, old readings and days dropped."""
    readings = {"sail": None if sail is None else (sail[0], sail[1]), "claude": None if claude is None else (now, claude),
                "openai": None if openai is None else (now, dict(openai))}
    for meter, got in readings.items():
        if got is None:
            continue
        at, raw = got
        series = ledger["series"][meter]
        if series and at <= series[-1][0]:
            continue  # the same reading again (a guard that has not read since), or one out of order
        total = series[-1][1] + _step(meter, ledger["raw"].get(meter), raw) if series else 0.0
        series.append([float(at), round(total, 6)])
        ledger["raw"][meter] = raw
    horizon = now - KEEP_HOURS * 3600
    for meter in METERS:
        rows = ledger["series"][meter]
        keep = [r for r in rows if r[0] >= horizon]
        if len(keep) < len(rows):
            keep.insert(0, rows[len(rows) - len(keep) - 1])  # the reading before the horizon: the first day's edge
        ledger["series"][meter] = keep
    day = ny_day(now).isoformat()
    value = _num(cap)
    floor = B.BASE_USD_DAY  # FAIL CLOSED: no usable budget.json is the no-profit cap, the lowest the rule ever gives
    cap_now = floor if value is None or value <= 0 else value
    ledger["caps"][day] = round(min(cap_now, ledger["caps"].get(day, cap_now)), 4)
    for key in ("caps", "days"):
        ledger[key] = {k: ledger[key][k] for k in sorted(ledger[key])[-KEEP_DAYS:]}
    return ledger


def total_at(series: list[list[float]], at: float) -> tuple[float | None, str]:
    """A meter's running total at `at`: on the line between the readings around it; at the first reading when `at` is
    before it ('after', the span measured from that reading), at the last when `at` is after it ('before'); None with no
    reading at all."""
    if not series:
        return None, "none"
    if at <= series[0][0]:
        return series[0][1], "after" if at < series[0][0] else "at"
    if at >= series[-1][0]:
        return series[-1][1], "before" if at > series[-1][0] else "at"
    for (t0, v0), (t1, v1) in zip(series, series[1:]):
        if t0 <= at <= t1:
            return v0 + (v1 - v0) * ((at - t0) / (t1 - t0) if t1 > t0 else 1.0), "at"
    return series[-1][1], "before"


def spend(series: list[list[float]], a: float, b: float) -> dict[str, Any]:
    """A meter's spend over [a, b] as far as its readings cover it: {usd, from, to}, the span measured being [from, to]
    = [max(a, its first reading), min(b, its last)], each end on the line between the readings around it; None when no
    reading reaches into the span (a meter stopped before it, or started after it)."""
    if not series or b <= a:
        return {"usd": None, "from": None, "to": None}
    lo, hi = max(a, series[0][0]), min(b, series[-1][0])
    if hi < lo:
        return {"usd": None, "from": None, "to": None}
    start, _ = total_at(series, lo)
    end, _ = total_at(series, hi)
    return {"usd": round(max(0.0, (end or 0.0) - (start or 0.0)), 4), "from": lo, "to": hi}


def day_figure(ledger: Mapping[str, Any], day: dt.date, now: float) -> dict[str, Any]:
    """THE DAY's measured spend (the module docstring), so far when `day` is today."""
    start, end = day_bounds(day)
    end_at = min(end, now)
    parts: dict[str, Any] = {}
    covered_from, covered_to, whole = [], [], True
    for meter in METERS:
        got = spend(ledger["series"].get(meter) or [], start, end_at)
        parts[meter] = got["usd"]
        if meter == "openai":   # closed by the budget: a gateway that reports none of it is no spend of it
            continue
        if got["usd"] is None:
            whole = False
            continue
        covered_from.append(got["from"])
        covered_to.append(got["to"])
        if got["from"] > start + 1 or got["to"] < end - 1:
            whole = False
    fixed_share = (end_at - start) / (end - start) if end > start else 1.0
    parts["cloudflare"] = round(B.CLOUDFLARE_USD_DAY, 4)  # a fixed fee: the day's whole share
    parts["data"] = round(B.DATA_USD_DAY, 4)
    known = [parts[m] for m in ("sail", "claude")]
    spent = None if None in known else round(sum(v for v in parts.values() if v is not None), 4)
    least = round(sum(v for v in parts.values() if v is not None), 4)  # what the readings show at the least
    cap = ledger["caps"].get(day.isoformat())
    cap = B.BASE_USD_DAY if _num(cap) is None else float(cap)
    return {"day": day.isoformat(), **parts, "spent": spent, "at_least": least,
            "from": None if not covered_from else _iso(max(covered_from)),
            "to": None if not covered_to else _iso(min(covered_to)), "whole": whole and end <= now,
            "so_far": now < end, "share_of_day": round(min(1.0, fixed_share), 4), "cap": round(cap, 4),
            "over": least > cap + OVER_EPSILON}


def finish_days(ledger: dict[str, Any], now: float) -> None:
    """Every New York day the readings cover that has ended, kept in `days` with its figure (final once a reading after
    its end exists; a later run writes it again only while it is not)."""
    starts = [rows[0][0] for rows in ledger["series"].values() if rows]
    if not starts:
        return
    day, today = ny_day(min(starts)), ny_day(now)
    while day < today:
        kept = ledger["days"].get(day.isoformat())
        if not (isinstance(kept, Mapping) and kept.get("final")):
            figure = day_figure(ledger, day, now)
            _, end = day_bounds(day)
            figure["final"] = all(rows and rows[-1][0] >= end for m, rows in ledger["series"].items() if m != "openai")
            ledger["days"][day.isoformat()] = figure
        day += dt.timedelta(days=1)


def since(ledger: Mapping[str, Any], first: dt.date, now: float) -> dict[str, Any]:
    """Measured spend from 00:00 ET of `first` to `now`: the kept days' figures and today's so far; {usd (None when a
    day in the span has no figure or no spent), days, from (the first day measured), partial}."""
    today = ny_day(now)
    usd, days, missing, partial = 0.0, 0, [], False
    day = first
    while day <= today:
        figure = day_figure(ledger, day, now) if day >= today - dt.timedelta(days=1) else ledger["days"].get(day.isoformat())
        if not isinstance(figure, Mapping) or _num(figure.get("spent")) is None:
            missing.append(day.isoformat())
        else:
            usd += float(figure["spent"])
            days += 1
            partial = partial or not figure.get("whole", False) and day < today
        day += dt.timedelta(days=1)
    return {"usd": None if missing else round(usd, 4), "days": days, "missing": missing[:5], "partial": partial,
            "from": first.isoformat()}


CAUSE = "cap_breach"
DOING = ("The budget holds every line it can to the day's cap: the event lane's verdicts (the House's lane, its "
         "allowance), the old research roles (the router) and Sail research (the Sail guard); the fixed costs (the House "
         "box, Cloudflare) it measures and cannot hold. A breach is a fixed cost that rose or a line that leaked: the next "
         "budget run sizes the lines on the measured fixed cost, and metered.json holds every meter's readings.")


def cap_check(ledger: Mapping[str, Any], now: float) -> dict[str, Any]:
    """THE STALL JOB'S `cap_breach` (the goal of Oct 19, 2026, item 5: "alarms on ... cap breaches"): today's measured
    metered spend so far, or yesterday's whole day, over that day's cap (`day_figure` `over`: what the readings show at
    the least, above the lowest cap budget.json gave that day, its no-profit $5 when none could be read). INFO, no owner
    step. Not judged before any meter has a reading."""
    series = ledger.get("series") if isinstance(ledger.get("series"), Mapping) else {}
    if not any(series.get(m) for m in METERS):
        return {"stalled": False, "judged": False, "what": "Not judged: no meter has a reading yet (metered.json).",
                "numbers": {"judged": False}, "doing": "Nothing: the cause is not judged while it reads so.",
                "owner_step": None, "onset": None}
    today = ny_day(now)
    figures = [day_figure(ledger, today, now)]
    kept = (ledger.get("days") or {}).get((today - dt.timedelta(days=1)).isoformat())
    figures.append(dict(kept) if isinstance(kept, Mapping) else day_figure(ledger, today - dt.timedelta(days=1), now))
    over = [f for f in figures if f.get("over")]
    shown = over[0] if over else figures[0]

    def usd(value: Any) -> str:
        return "unknown" if _num(value) is None else f"${float(value):.2f}"
    parts = (f"Sail {usd(shown.get('sail'))}, Claude {usd(shown.get('claude'))}, Cloudflare {usd(shown.get('cloudflare'))}"
             + ("" if not _num(shown.get("openai")) else f", OpenAI {usd(shown.get('openai'))}"))
    unknown = [m for m in ("sail", "claude") if _num(shown.get(m)) is None]
    so_far = shown["day"] == today.isoformat()
    if over:
        what = (f"Metered compute on {shown['day']} {'is' if so_far else 'was'} {usd(shown.get('at_least'))}"
                f"{' so far' if so_far else ''}, over that day's cap of {usd(shown.get('cap'))} ({parts})"
                + (f"; at least: {' and '.join(unknown)} had no reading" if unknown else "") + ".")
    else:
        what = (f"Metered compute on {shown['day']} is {usd(shown.get('at_least'))} so far, under the day's cap of "
                f"{usd(shown.get('cap'))} ({parts})" + (f"; {' and '.join(unknown)} had no reading" if unknown else "")
                + ".")
    yesterday = figures[1]
    return {"stalled": bool(over), "judged": True, "what": what,
            "numbers": {"day": shown["day"], "spent_usd": _num(shown.get("at_least")), "cap_usd": _num(shown.get("cap")),
                        "sail_usd": _num(shown.get("sail")), "claude_usd": _num(shown.get("claude")),
                        "openai_usd": _num(shown.get("openai")), "cloudflare_usd": _num(shown.get("cloudflare")),
                        "whole_day": bool(shown.get("whole")), "so_far": so_far,
                        "yesterday_usd": _num(yesterday.get("at_least")), "yesterday_cap_usd": _num(yesterday.get("cap"))},
            "doing": DOING, "owner_step": None, "onset": None}


def update(root: str | Path, now: float, *, health: Any, budget: Mapping[str, Any] | None) -> dict[str, Any]:
    """THE STALL JOB'S CALL: this run's readings into `<root>/metered.json` (the ledger), the days that ended finished,
    and the ledger returned. `health` is the gateway's `/v1/health` (None unread); `budget` budget.json (None unusable:
    the day's cap is then the no-profit $5)."""
    ledger = load(root)
    cap = (budget or {}).get("cap_usd_day") if isinstance(budget, Mapping) else None
    observe(ledger, now=now, sail=sail_reading(root), claude=claude_reading(health), openai=openai_reading(health),
            cap=cap)
    finish_days(ledger, now)
    save(root, ledger)
    return ledger


__all__ = ["update", "cap_check", "CAUSE", "load", "save", "observe", "day_figure", "finish_days", "since", "spend", "total_at", "day_bounds",
           "ny_day", "sail_reading", "claude_reading", "openai_reading", "empty", "FILE", "METERS", "KEEP_HOURS",
           "KEEP_DAYS", "OVER_EPSILON"]
