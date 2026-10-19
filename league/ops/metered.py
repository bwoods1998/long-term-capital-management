"""MEASURED METERED SPEND (release 1019c; the review of r1/alarms, its majors 1 and 4; the owner's goal of Oct 19, 2026,
items 4 and 5: "metered compute <= $5 a day plus half the trailing week's realized net profit, never above $25", "alarms
on ... cap breaches", the daily report's "costs"): what the metered compute of each UTC day COST, read from the meters
themselves, never from the budget's lines (budget.json says what may be spent, this says what was).

ONE DAY FOR EVERY LINE (the review of r2/alarms, its major 1). THE DAY is the UTC day, 00:00-24:00 UTC: the day budget
rule 3 holds every line on. The Sail guard's research and account caps count from 00:00 UTC (league/swarm/guard.py), the
router's Claude roles too (league/swarm/models.py), and so do the House's event lane's verdict line
(league/events/house.py `_spend_today`), budget.json's day's figure and the lane's measured heaviest day
(league/ops/budget.py `lane_spend`). Judged on any other day, lines each held on their own day add up past the cap on the
day judged: a New York day saw one UTC day's research after 04:00 UTC and the next one's before it, and a lane held on New
York days spent one day's line after 20:00 ET and the next day's from 00:00 ET, both in one UTC day.

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
`began` keeps when each cumulative meter was first read: the ledger measures nothing before it.

A DAY (`day_figure`, a UTC day): {day, sail, claude, openai, cloudflare, data, spent (their sum; None while a cumulative
meter has no reading in the day), at_least (what the readings show, a meter with none left out), certain (what they put
inside the day for certain: below), from, to (what the readings cover), whole (the day covered from its start to its
end), cap, over (at_least above the cap by more than a cent), certainly_over (certain above it)}. THE DAY'S CAP is THE
CAP THE RULE SET FOR IT (`caps`; the review of r2/alarms, its major 1): the highest `cap_usd_day` of the usable
budget.json the stall job read while the day ran, or that the rule computed on that day. The rule sets a day's lines at its first run and only raises them within it (the top-up
raise, a close whose profit lifted the cap: league/ops/budget.py), so every line of the day was held under that cap at
the most; judged against the lowest cap seen, a day spent within its raised lines read as a breach. Never above the
owner's $25; the rule's no-profit $5 when no usable budget.json was read for the day (FAIL CLOSED). The stall job's
`cap_breach` reads today's figure so far and yesterday's whole one; the daily report reads its day's.

THE CAP BREACH HOLD (the review of r2/alarms, its major 1: a breach only raised an alarm, and a leak went on spending
all day). While what the readings put inside TODAY for certain is over today's cap (`certainly_over`: each meter's rise
between its first and its last reading of the day, and the fixed fees; never the share of a rise the line between a
reading before 00:00 UTC and one after it gives the day, so yesterday's late spend never holds today), every stall run
writes `<state>/cap-hold.json` (`budget.HOLD_FILE`: {schema, day, at, since, spent_usd, cap_usd}), and every line the
budget holds reads it (league/ops/budget.py `cap_hold`): the event lane's verdict line (`lane_allowance`), Sail research
(`sail_caps`) and the Claude roles (`effective`, the settings' `budget` block every swarm step loads) are 0 for the rest
of that UTC day, so the cap holds after a leak instead of only raising an alarm. The fixed costs go on: nothing here
stops a box. The file names its day, so a new day has no hold; a day whose cap rose above what it spent (a close's
profit) has its hold lifted at the next run, and a day back under its cap removes the file.

COSTS TO DATE (`since`; the review of r2/alarms, its major 2): the measured spend from a day (the event lane's first real
fill's) to now, over the days the ledger covers: from the LATER of that day and the first day both Sail's and Claude's
meters were read, so a ledger begun after the first fill (a release that started it later, a lost metered.json) measures
what it can and says from when (`from`, `partial`, `missing`), never nothing for good.

Read-only on every store; it writes `metered.json` and `cap-hold.json` only. Standard library only.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
from pathlib import Path
from typing import Any, Mapping

from . import budget as B
from . import guard

UTC = dt.timezone.utc
FILE = "metered.json"
#: 2 from the review of r2/alarms: UTC days, the day's cap the highest the rule set, `began`. A ledger of another schema
#: (r1's New York days) reads as none: its days and caps meant other spans.
SCHEMA = 2
METERS = ("sail", "claude", "openai")
#: The cumulative meters a day's whole spend needs (OpenAI is closed by the budget: a gateway that reports none of it is
#: no spend of it).
NEEDED = ("sail", "claude")
#: The readings each meter keeps (hours): yesterday whole and today, with room for a House down a day.
KEEP_HOURS = 72
#: The UTC days' caps kept (`caps`), and the finished days' figures (`days`).
KEEP_DAYS = 400
#: Spend above the cap by more than this is over it (a cent: the meters' own rounding never alarms).
OVER_EPSILON = 0.01
#: A cumulative meter (Sail's, Claude's) with no reading for this long, on a ledger at least this old, is BLIND: the cap
#: cannot be judged, and `cap_breach` stands for that too (a meter that stopped never hides a breach: it fails closed).
BLIND_HOURS = 6.0
#: THE CAP BREACH HOLD's file (league/ops/budget.py reads it: `HOLD_FILE`, `cap_hold`).
HOLD_FILE = B.HOLD_FILE
HOLD_SCHEMA = B.HOLD_SCHEMA


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _iso(epoch: float) -> str:
    return dt.datetime.fromtimestamp(float(epoch), UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def utc_day(epoch: float) -> dt.date:
    """THE DAY of `epoch`: its UTC day (the day budget rule 3 holds every line on)."""
    return dt.datetime.fromtimestamp(float(epoch), UTC).date()


def day_bounds(day: dt.date) -> tuple[float, float]:
    """00:00 and 24:00 UTC of `day`, epochs: the Sail guard's and the router's `now - now % 86400`, the lane's
    `_spend_today`."""
    start = dt.datetime.combine(day, dt.time(0, 0), tzinfo=UTC).timestamp()
    return start, start + 86400.0


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
            "days": {}, "began": {m: None for m in METERS}}


def load(root: str | Path) -> dict[str, Any]:
    """`<root>/metered.json`, or an empty ledger (none, unreadable, another schema)."""
    try:
        data = json.loads((Path(root) / FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return empty()
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        return empty()
    out = empty()
    began = data.get("began") if isinstance(data.get("began"), Mapping) else {}
    for m in METERS:
        rows = (data.get("series") or {}).get(m) if isinstance(data.get("series"), Mapping) else None
        out["series"][m] = [[float(t), float(v)] for t, v in (rows or [])
                            if _num(t) is not None and _num(v) is not None] if isinstance(rows, list) else []
        out["raw"][m] = (data.get("raw") or {}).get(m) if isinstance(data.get("raw"), Mapping) else None
        # When the meter was first read (a ledger written without it: its oldest reading kept).
        first = _num(began.get(m))
        out["began"][m] = first if first is not None else (out["series"][m][0][0] if out["series"][m] else None)
    out["caps"] = {str(k): float(v) for k, v in (data.get("caps") or {}).items() if _num(v) is not None} \
        if isinstance(data.get("caps"), Mapping) else {}
    out["days"] = {str(k): dict(v) for k, v in (data.get("days") or {}).items() if isinstance(v, Mapping)} \
        if isinstance(data.get("days"), Mapping) else {}
    return out


def _write_private(path: Path, data: Any) -> None:
    """`data` as JSON at `path`, atomically, readable by the House's own user only (as stall.json)."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def save(root: str | Path, ledger: Mapping[str, Any]) -> None:
    """`<root>/metered.json`, atomically, readable by the House's own user only (as stall.json)."""
    _write_private(Path(root) / FILE, ledger)


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
            openai: Mapping[str, Any] | None, cap: float | None, cap_at: float | None = None) -> dict[str, Any]:
    """One stall run's readings into the ledger (in place, and returned): each meter's rise since its last raw reading
    added to its running total at the reading's time (Sail's: the guard's own reading time; the gateway's: now), the
    budget's cap kept for the days it was in force at its highest (`cap`: a usable budget.json's `cap_usd_day`, computed
    at `cap_at`; None, nothing: the day then keeps what it had, the no-profit $5 when it had nothing), old readings and
    days dropped."""
    readings = {"sail": None if sail is None else (sail[0], sail[1]), "claude": None if claude is None else (now, claude),
                "openai": None if openai is None else (now, dict(openai))}
    began = ledger.setdefault("began", {m: None for m in METERS})
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
        if _num(began.get(meter)) is None:
            began[meter] = float(at)   # the meter's first reading: the ledger measures nothing of it before
    horizon = now - KEEP_HOURS * 3600
    for meter in METERS:
        rows = ledger["series"][meter]
        keep = [r for r in rows if r[0] >= horizon]
        if len(keep) < len(rows):
            keep.insert(0, rows[len(rows) - len(keep) - 1])  # the reading before the horizon: the first day's edge
        ledger["series"][meter] = keep
    # THE CAP THE RULE SET FOR THE DAY: a usable budget.json's cap counts, at its highest, for the day this run read it in
    # (its lines were in force then) and for the day the rule computed it on; never above the owner's $25. A run with no
    # usable budget.json lowers nothing: the holders then run on the floor's no-profit lines, under any cap of the day.
    value, computed = _num(cap), _num(cap_at)
    if value is not None and value > 0 and (computed is None or computed <= now + 300):   # never one dated ahead
        value = min(value, B.CEILING_USD_DAY)
        days = {utc_day(now).isoformat()}
        if computed is not None:
            days.add(utc_day(computed).isoformat())
        for key in days:
            ledger["caps"][key] = round(max(value, _num(ledger["caps"].get(key)) or value), 4)
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


def certain(series: list[list[float]], a: float, b: float) -> float:
    """A meter's rise between its first and its last reading INSIDE [a, b] (0 with fewer than two): spend the readings put
    inside the span for certain, whatever the readings around its edges say (the line between a reading before 00:00 UTC
    and one after it shares their rise across the two days; this never does)."""
    inside = [row for row in series if a <= row[0] <= b]
    return round(max(0.0, inside[-1][1] - inside[0][1]), 4) if len(inside) >= 2 else 0.0


def day_cap(ledger: Mapping[str, Any], day: dt.date) -> float:
    """THE DAY'S CAP (the module docstring): the highest the rule set for `day`, the no-profit $5 when none was read."""
    cap = _num((ledger.get("caps") or {}).get(day.isoformat()))
    return B.BASE_USD_DAY if cap is None or cap <= 0 else min(cap, B.CEILING_USD_DAY)


def day_figure(ledger: Mapping[str, Any], day: dt.date, now: float) -> dict[str, Any]:
    """THE DAY's measured spend (the module docstring), so far when `day` is today."""
    start, end = day_bounds(day)
    end_at = min(end, now)
    parts: dict[str, Any] = {}
    covered_from, covered_to, whole = [], [], True
    for meter in METERS:
        got = spend(ledger["series"].get(meter) or [], start, end_at)
        parts[meter] = got["usd"]
        if meter not in NEEDED:   # closed by the budget: a gateway that reports none of it is no spend of it
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
    known = [parts[m] for m in NEEDED]
    spent = None if None in known else round(sum(v for v in parts.values() if v is not None), 4)
    least = round(sum(v for v in parts.values() if v is not None), 4)  # what the readings show at the least
    # What the readings put inside the day FOR CERTAIN (`certain`, each meter's rise between its first and its last
    # reading of the day, and the fixed fees): THE CAP BREACH HOLD acts on it alone, so a rise the line between two
    # readings shares across 00:00 UTC never holds a day's lines.
    sure = round(sum(certain(ledger["series"].get(m) or [], start, end_at) for m in METERS)
                 + parts["cloudflare"] + parts["data"], 4)
    cap = day_cap(ledger, day)
    return {"day": day.isoformat(), **parts, "spent": spent, "at_least": least, "certain": sure,
            "from": None if not covered_from else _iso(max(covered_from)),
            "to": None if not covered_to else _iso(min(covered_to)), "whole": whole and end <= now,
            "so_far": now < end, "share_of_day": round(min(1.0, fixed_share), 4), "cap": round(cap, 4),
            "over": least > cap + OVER_EPSILON, "certainly_over": sure > cap + OVER_EPSILON}


def finish_days(ledger: dict[str, Any], now: float) -> None:
    """Every UTC day the readings cover that has ended, kept in `days` with its figure (final once a reading after its
    end exists; a later run writes it again only while it is not)."""
    starts = [rows[0][0] for rows in ledger["series"].values() if rows]
    if not starts:
        return
    day, today = utc_day(min(starts)), utc_day(now)
    while day < today:
        kept = ledger["days"].get(day.isoformat())
        if not (isinstance(kept, Mapping) and kept.get("final")):
            figure = day_figure(ledger, day, now)
            _, end = day_bounds(day)
            figure["final"] = all(rows and rows[-1][0] >= end for m, rows in ledger["series"].items() if m in NEEDED)
            ledger["days"][day.isoformat()] = figure
        day += dt.timedelta(days=1)


def measured_from(ledger: Mapping[str, Any]) -> dt.date | None:
    """The first UTC day the ledger measures a whole spend on: the day both Sail's and Claude's meters had been read
    (`began`; a ledger that kept no `began`: their oldest readings). None before both were read."""
    began = ledger.get("began") if isinstance(ledger.get("began"), Mapping) else {}
    series = ledger.get("series") if isinstance(ledger.get("series"), Mapping) else {}
    starts = []
    for m in NEEDED:
        first = _num(began.get(m))
        if first is None and series.get(m):
            first = _num(series[m][0][0])
        if first is None:
            return None
        starts.append(first)
    return utc_day(max(starts))


def since(ledger: Mapping[str, Any], first: dt.date, now: float) -> dict[str, Any]:
    """COSTS TO DATE (the module docstring): the measured spend from 00:00 UTC of `first` to `now`, over the days the
    ledger covers: from the later of `first` and `measured_from` (the first day both Sail's and Claude's meters were read),
    each day its kept figure (today's and yesterday's as they read now). A day missing a meter's figure counts what the
    others show at the least and is named in `missing`. {usd (None only when the ledger has measured no day at all yet),
    days, first, from (the first day measured), partial (the span starts after `first`, a day before today is not wholly
    measured, or a day is missing a meter), missing (the first 5 such days), missing_n}."""
    today = utc_day(now)
    begun = measured_from(ledger)
    out: dict[str, Any] = {"usd": None, "days": 0, "first": first.isoformat(), "from": None, "partial": True,
                           "missing": [], "missing_n": 0}
    if begun is None or begun > today:
        return out
    start = max(first, begun)
    usd, days, missing, partial = 0.0, 0, [], start > first
    day = start
    while day <= today:
        figure = day_figure(ledger, day, now) if day >= today - dt.timedelta(days=1) else \
            (ledger.get("days") or {}).get(day.isoformat())
        if not isinstance(figure, Mapping):
            missing.append(day.isoformat())   # no figure kept: a day the ledger never finished
        elif _num(figure.get("spent")) is not None:
            usd += float(figure["spent"])
            days += 1
            partial = partial or (not figure.get("whole", False) and day < today)
        else:   # a meter had no reading in the day: what the others show, at the least
            usd += _num(figure.get("at_least")) or 0.0
            days += 1
            missing.append(day.isoformat())
        day += dt.timedelta(days=1)
    return {**out, "usd": round(usd, 4), "days": days, "from": start.isoformat(), "partial": bool(partial or missing),
            "missing": missing[:5], "missing_n": len(missing)}


# ---------------------------------------------------------------------------------------------- the hold
def write_hold(root: str | Path, figure: Mapping[str, Any], now: float, *,
               since: str | None = None) -> dict[str, Any] | None:
    """THE CAP BREACH HOLD (the module docstring): `<root>/cap-hold.json` while today's figure (`figure`, today's
    `day_figure`) is over its cap for certain (`certainly_over`), removed when it is not. Returns the hold written, or
    None."""
    path = Path(root) / HOLD_FILE
    if not figure.get("certainly_over") or figure.get("day") != utc_day(now).isoformat():
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        return None
    hold = {"schema": HOLD_SCHEMA, "day": figure["day"], "at": _iso(now), "since": since or _iso(now),
            "spent_usd": _num(figure.get("certain")), "cap_usd": _num(figure.get("cap"))}
    _write_private(path, hold)
    return hold


def _hold_since(root: Path, day: str) -> str | None:
    """When today's hold began (its file's `since`), so a run that keeps it says the same onset."""
    try:
        kept = json.loads((root / HOLD_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return kept.get("since") if isinstance(kept, Mapping) and kept.get("day") == day else None


CAUSE = "cap_breach"
DOING = ("The budget holds every line it can to the day's cap on the UTC day (the event lane's verdicts, the old research "
         "roles, Sail research); the fixed costs (the House box, Cloudflare) it measures and cannot hold. A breach is a "
         "fixed cost that rose or a line that leaked: while today is over its cap the House HOLDS the lane's verdict line, "
         "Sail research and the Claude roles at 0 until 00:00 UTC (cap-hold.json), the next budget run sizes the lines on "
         "the measured fixed cost, and metered.json holds every meter's readings.")


def cap_check(ledger: Mapping[str, Any], now: float, *, hold: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """THE STALL JOB'S `cap_breach` (the goal of Oct 19, 2026, item 5: "alarms on ... cap breaches"): today's measured
    metered spend so far, or yesterday's whole day, over that day's cap (`day_figure` `over`: what the readings show at
    the least, above the cap the rule set for that UTC day, its no-profit $5 when none could be read); or a meter BLIND
    (`BLIND_HOURS` with no reading of Sail's or Claude's meter, the ledger older than that): the cap cannot be judged,
    which never passes for under it. INFO, no owner step; `hold` (THE CAP BREACH HOLD this run wrote) is said. Not
    judged before any meter has a reading."""
    series = ledger.get("series") if isinstance(ledger.get("series"), Mapping) else {}
    if not any(series.get(m) for m in METERS):
        return {"stalled": False, "judged": False, "what": "Not judged: no meter has a reading yet (metered.json).",
                "numbers": {"judged": False}, "doing": "Nothing: the cause is not judged while it reads so.",
                "owner_step": None, "onset": None}
    today = utc_day(now)
    figures = [day_figure(ledger, today, now)]
    kept = (ledger.get("days") or {}).get((today - dt.timedelta(days=1)).isoformat())
    figures.append(dict(kept) if isinstance(kept, Mapping) else day_figure(ledger, today - dt.timedelta(days=1), now))
    over = [f for f in figures if f.get("over")]
    shown = over[0] if over else figures[0]
    began = min(rows[0][0] for rows in series.values() if rows)
    blind = [m for m in NEEDED if now - began >= BLIND_HOURS * 3600
             and (not series.get(m) or now - series[m][-1][0] > BLIND_HOURS * 3600)]

    def usd(value: Any) -> str:
        return "unknown" if _num(value) is None else f"${float(value):.2f}"
    parts = (f"Sail {usd(shown.get('sail'))}, Claude {usd(shown.get('claude'))}, Cloudflare {usd(shown.get('cloudflare'))}"
             + ("" if not _num(shown.get("openai")) else f", OpenAI {usd(shown.get('openai'))}"))
    unknown = [m for m in NEEDED if _num(shown.get(m)) is None]
    so_far = shown["day"] == today.isoformat()
    if over:
        what = (f"Metered compute on the UTC day {shown['day']} {'is' if so_far else 'was'} {usd(shown.get('at_least'))}"
                f"{' so far' if so_far else ''}, over that day's cap of {usd(shown.get('cap'))} ({parts})"
                + (f"; at least: {' and '.join(unknown)} had no reading" if unknown else "") + ".")
    else:
        what = (f"Metered compute on the UTC day {shown['day']} is {usd(shown.get('at_least'))} so far, under the day's "
                f"cap of {usd(shown.get('cap'))} ({parts})"
                + (f"; {' and '.join(unknown)} had no reading" if unknown else "") + ".")
    if hold:
        what += (f" The House holds the lane's verdict line, Sail research and the Claude roles at 0 until 00:00 UTC "
                 f"(cap-hold.json, since {hold.get('since')}).")
    if blind:
        what += (f" The cap cannot be judged: {' and '.join(blind)}'s meter has had no reading for {BLIND_HOURS:g} hours "
                 "or more (the Sail guard's, or the gateway's /v1/health).")
    yesterday = figures[1]
    last = {m: (series.get(m) or [[None]])[-1][0] for m in NEEDED}
    return {"stalled": bool(over or blind), "judged": True, "what": what,
            "numbers": {"day": shown["day"], "spent_usd": _num(shown.get("at_least")), "cap_usd": _num(shown.get("cap")),
                        "sail_usd": _num(shown.get("sail")), "claude_usd": _num(shown.get("claude")),
                        "openai_usd": _num(shown.get("openai")), "cloudflare_usd": _num(shown.get("cloudflare")),
                        "whole_day": bool(shown.get("whole")), "so_far": so_far,
                        "yesterday_usd": _num(yesterday.get("at_least")), "yesterday_cap_usd": _num(yesterday.get("cap")),
                        "sail_read_at": None if last["sail"] is None else _iso(last["sail"]),
                        "claude_read_at": None if last["claude"] is None else _iso(last["claude"]),
                        "held": bool(hold), "blind": ",".join(blind) or "none"},
            "doing": DOING, "owner_step": None, "onset": None}


def update(root: str | Path, now: float, *, health: Any, budget: Mapping[str, Any] | None) -> dict[str, Any]:
    """THE STALL JOB'S CALL: this run's readings into `<root>/metered.json` (the ledger), the days that ended finished,
    THE CAP BREACH HOLD written or removed (`<root>/cap-hold.json`), and the ledger returned with the hold this run
    keeps under its `hold` key (not saved). `health` is the gateway's `/v1/health` (None unread); `budget` budget.json as
    the stall job read it (None unusable: nothing is recorded of the day's cap)."""
    root = Path(root)
    ledger = load(root)
    cap = (budget or {}).get("cap_usd_day") if isinstance(budget, Mapping) else None
    cap_at = (budget or {}).get("at") if isinstance(budget, Mapping) else None
    observe(ledger, now=now, sail=sail_reading(root), claude=claude_reading(health), openai=openai_reading(health),
            cap=cap, cap_at=cap_at)
    finish_days(ledger, now)
    save(root, ledger)
    today = day_figure(ledger, utc_day(now), now)
    hold = write_hold(root, today, now, since=_hold_since(root, today["day"]))
    return {**ledger, "hold": hold}


__all__ = ["update", "cap_check", "CAUSE", "BLIND_HOURS", "load", "save", "observe", "day_figure", "day_cap", "finish_days",
           "since", "measured_from", "spend", "total_at", "day_bounds", "utc_day", "sail_reading", "claude_reading",
           "openai_reading", "empty", "write_hold", "FILE", "HOLD_FILE", "METERS", "NEEDED", "KEEP_HOURS", "KEEP_DAYS",
           "OVER_EPSILON", "SCHEMA"]
