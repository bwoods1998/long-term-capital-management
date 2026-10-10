"""The `equity_data` job: the equity lane's daily store, Alpaca SIP daily bars through the gateway, raw and adjustment=all.

Owner: ops. Protected (league/ops/ is FORBIDDEN to every role). Registered in league/ops/registry.py the way `direction`
is (at the House's start and daily after the close, 22:30Z: past the close and its settling in both seasons; in a pause
too: it only reads the gateway and writes its own directory).

THE JOB (`run`): for the universe (league/equity/config.py `UNIVERSE`, the constitution's `equity_money.universe`
bounding it: `universe`), page `GET /v1/alpaca/v2/stocks/bars` (the route the gateway already allows; `direction.fetch`'s
paging) with timeframe 1Day, feed sip, `adjustment=raw` and again `adjustment=all`, from 2016-01-04 (`FIRST_DAY`) to the
last CLOSED session (`last_closed`: `ltcm.data.previous_session` with `direction.CLOSE_SETTLE_SECONDS` to settle; never a
partial day, and a row after it is dropped). The whole history is fetched each run: `all` is adjusted as of the fetch
day, so a new split or dividend restates every earlier row. Then the AUDIT (`audit`), then
`league.equity.store.write_store(<state>/equity-daily, ..., gate=True, source="alpaca-sip-1Day", audit=...)`
atomically. A gateway error or a failed audit writes nothing new: {"status": "failed", "error"} (a failed receipt, a
House warning, a retry inside its grace); the last good store stays.

THE AUDIT (`audit`; each a named check, all must pass; each lists at most `PROBLEMS_LISTED` problems and counts them all):
- calendar: every session of `league.equity.store.nyse_sessions(FIRST_DAY, last)` has a SPY bar and no bar falls on a
  non-session (no gap, no extra day); every other symbol has a bar on every session from its first bar (a listing after
  2016, XLC's for one) to the last session; no day twice; the raw and the all series on the same days;
- OHLC sane: every price finite and 0 < low <= min(open, close) <= max(open, close) <= high, for raw and all;
- splits visible: every raw/all close-ratio jump over `SPLIT_JUMP` between two of the symbol's sessions lines up with a
  split the raw close shows (a move of the raw close by the jump's factor, within `SPLIT_RAW_TOLERANCE`: the day's own
  move), and no raw close moves by more than `RAW_JUMP` with no ratio jump (a split the all series did not adjust);
  the splits found are listed per symbol (`found`);
- volumes present: every raw bar has a finite volume > 0;
- THE REGULAR SESSION (the design's fact 1; `regular_session_check`): on `REGULAR_DAYS` (20) sessions of SPY, the 1Day
  bar's open, high, low, close and volume against its 1Min bars of 09:30-16:00 (13:00 on a half day) aggregated, and
  against the whole 04:00-20:00 day's: "regular" when every field of every day matches the session's within
  `REGULAR_TOLERANCE` (relative); "extended" when some day's bar matches only the extended day (its open or close is the
  extended day's and not the session's, or its range reaches outside the session's); "unverified" otherwise (fewer days
  compared, or a field that matches neither: an auction print, a condition the two aggregations treat apart). The
  verdict and every mismatch are in the manifest's audit. "extended" FAILS the audit: the store must then be built from
  1Min bars, a stop for E1, reported, never patched. "unverified" passes, recorded, and the job raises a House warning.

Data never leaves the House's state directory (the vendor's terms; a public repository): nothing here is committed,
printed in full, or sent anywhere but the store. The receipt carries counts and verdicts, never a price.
"""

from __future__ import annotations

import datetime as dt
import math
from pathlib import Path
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo

FIRST_DAY = "2016-01-04"
STORE_DIR = "equity-daily"
BARS = "/v1/alpaca/v2/stocks/bars"
MAX_PAGES = 400
#: A raw/all ratio move larger than this between two sessions is a corporate action the audit must explain.
SPLIT_JUMP = 0.05
REGULAR_DAYS = 20
REGULAR_TOLERANCE = 1e-6
#: The receipt's source and the manifest's.
SOURCE = "alpaca-sip-1Day"
#: The symbol whose bars the calendar and the regular-session check read (the most liquid ETF; it has every session).
CALENDAR_SYMBOL = "SPY"
#: A split's raw close move may differ from the ratio jump by the day's own move: at most this much (relative).
SPLIT_RAW_TOLERANCE = 0.25
#: A raw close move larger than this between two sessions with no ratio jump is a split the all series did not adjust.
RAW_JUMP = 0.30
#: Each check lists at most this many problems (it counts them all).
PROBLEMS_LISTED = 20
#: Bars a page (the venue's maximum).
PAGE_LIMIT = 10000
NEW_YORK = ZoneInfo("America/New_York")
CHECKS = ("calendar", "ohlc", "splits", "volume", "regular")
FIELDS = ("o", "h", "l", "c", "v")


# ------------------------------------------------------------------------------------------------- small helpers
def _num(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(float(value)) else None


def ny_day(stamp: Any) -> dt.date:
    """The New York session day of a bar's `t` (RFC 3339; a daily bar is stamped at New York midnight). ValueError on a
    stamp that is not one."""
    text = str(stamp or "")
    if len(text) == 10:
        return dt.date.fromisoformat(text)
    moment = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    if moment.tzinfo is None:
        raise ValueError(f"the bar time {text[:40]!r} has no zone")
    return moment.astimezone(NEW_YORK).date()


def ny_moment(stamp: Any) -> dt.datetime:
    moment = dt.datetime.fromisoformat(str(stamp or "").replace("Z", "+00:00"))
    if moment.tzinfo is None:
        raise ValueError(f"the bar time {str(stamp)[:40]!r} has no zone")
    return moment.astimezone(NEW_YORK)


def _utc(day: dt.date, hour: int, minute: int = 0) -> str:
    moment = dt.datetime.combine(day, dt.time(hour, minute), NEW_YORK).astimezone(dt.timezone.utc)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _same(a: float | None, b: float | None) -> bool:
    if a is None or b is None:
        return False
    return abs(a - b) <= REGULAR_TOLERANCE * max(abs(b), 1.0)


class _Check:
    """One named check: its problems (the first `PROBLEMS_LISTED`) and their count."""

    def __init__(self) -> None:
        self.problems: list[str] = []
        self.count = 0
        self.extra: dict[str, Any] = {}

    def add(self, text: str) -> None:
        self.count += 1
        if len(self.problems) < PROBLEMS_LISTED:
            self.problems.append(text)

    def out(self, passed: bool | None = None) -> dict[str, Any]:
        return {"passed": self.count == 0 if passed is None else passed, "problems": list(self.problems),
                "count": self.count, **self.extra}


# ------------------------------------------------------------------------------------------------- the gateway
def fetch(gateway: Any, symbols: Sequence[str], start: str, end: str, *, adjustment: str,
          timeframe: str = "1Day") -> dict[str, list[dict[str, Any]]]:
    """{symbol: [bar rows {t, o, h, l, c, v} in time order]} of every page; ValueError on a malformed answer (no `bars`
    object, a row that is not an object or has no time, a time twice) or a cursor that does not end within
    `MAX_PAGES`. Every symbol asked for is a key (an empty list when the venue has no bar of it)."""
    out: dict[str, dict[str, dict[str, Any]]] = {str(s): {} for s in symbols}
    token = None
    for _ in range(MAX_PAGES):
        params = {"symbols": ",".join(symbols), "timeframe": timeframe, "start": start, "end": end,
                  "adjustment": adjustment, "feed": "sip", "limit": PAGE_LIMIT}
        if token:
            params["page_token"] = token
        answer = gateway.get(BARS, params) or {}
        bars = answer.get("bars") if isinstance(answer, Mapping) else None
        if bars is None and isinstance(answer, Mapping) and "bars" in answer:
            bars = {}  # the venue's answer for a span with no bar at all
        if not isinstance(bars, Mapping):
            raise ValueError("the bars answer has no bars")
        for symbol, rows in bars.items():
            seen = out.setdefault(str(symbol), {})
            if rows is None:
                continue
            if not isinstance(rows, list):
                raise ValueError(f"the bars of {str(symbol)[:12]} are not a list")
            for row in rows:
                if not isinstance(row, Mapping) or not row.get("t"):
                    raise ValueError(f"a bar of {str(symbol)[:12]} is not an object with a time")
                stamp = str(row["t"])
                if stamp in seen:
                    raise ValueError(f"the bar of {str(symbol)[:12]} at {stamp[:25]} came twice")
                seen[stamp] = {"t": stamp, **{k: row.get(k) for k in FIELDS}}
        token = answer.get("next_page_token") if isinstance(answer, Mapping) else None
        if not token:
            return {s: [rows[k] for k in sorted(rows, key=_order)] for s, rows in out.items()}
    raise ValueError(f"the bars did not end within {MAX_PAGES} pages")


def _order(stamp: str) -> dt.datetime:
    """A bar time as a UTC moment, for ordering (a bare day is its New York midnight). ValueError when it is not one."""
    if len(stamp) == 10:
        return dt.datetime.combine(dt.date.fromisoformat(stamp), dt.time(0), NEW_YORK).astimezone(dt.timezone.utc)
    return ny_moment(stamp).astimezone(dt.timezone.utc)


def _aggregate(rows: Sequence[Mapping[str, Any]]) -> dict[str, float | None]:
    """open, high, low, close and volume of minute bars in time order (None each when there are none)."""
    if not rows:
        return {k: None for k in FIELDS}
    highs = [_num(r.get("h")) for r in rows]
    lows = [_num(r.get("l")) for r in rows]
    vols = [_num(r.get("v")) for r in rows]
    return {"o": _num(rows[0].get("o")), "c": _num(rows[-1].get("c")),
            "h": max(highs) if all(x is not None for x in highs) else None,
            "l": min(lows) if all(x is not None for x in lows) else None,
            "v": sum(vols) if all(x is not None for x in vols) else None}


def regular_session_check(gateway: Any, symbol: str, days: Sequence[dt.date]) -> dict[str, Any]:
    """The design's fact 1 on `days`: {verdict "regular" | "extended" | "unverified", days, mismatches: [...]}.

    Per day: the symbol's 1Day bar (raw) against its 1Min bars (raw) of the regular session, 09:30 to the close (16:00,
    13:00 on a half day: `league.equity.store.nyse_sessions`), aggregated (first open, highest high, lowest low, last
    close, summed volume), and of the whole 04:00-20:00 day. Each field of each day is "regular" (it matches the
    session's within `REGULAR_TOLERANCE`), "extended" (it matches only the whole day's; or, for the high and the low,
    it lies outside the session's range), or "neither"; a mismatch row {day, field, daily, regular, extended, matches}
    is kept for every field that is not "regular". The verdict is the module docstring's. A day whose bars cannot be
    read is a mismatch {day, field: "bars", why} and is not compared. Never raises for the venue's answers: a gateway
    error is the "unverified" verdict with its `error`."""
    from ..equity import store as eq_store

    days = sorted({d if isinstance(d, dt.date) else dt.date.fromisoformat(str(d)) for d in days})
    out: dict[str, Any] = {"verdict": "unverified", "symbol": symbol, "days": [d.isoformat() for d in days],
                           "compared": 0, "mismatches": [], "tolerance": REGULAR_TOLERANCE}
    if not days:
        out["why"] = "no days to compare"
        return out
    try:
        early = {d: e for d, e in eq_store.nyse_sessions(days[0], days[-1])}
        daily = {ny_day(r["t"]): r for r in fetch(gateway, [symbol], days[0].isoformat(), days[-1].isoformat(),
                                                  adjustment="raw").get(symbol, [])}
    except Exception as exc:  # noqa: BLE001 - unverified, said why
        out["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
        return out
    extended_days = 0
    for day in days:
        if day not in early:
            out["mismatches"].append({"day": day.isoformat(), "field": "bars", "why": "not an NYSE session"})
            continue
        bar = daily.get(day)
        try:
            minutes = fetch(gateway, [symbol], _utc(day, 4), _utc(day, 20), adjustment="raw",
                            timeframe="1Min").get(symbol, [])
        except Exception as exc:  # noqa: BLE001 - this day is not compared
            out["mismatches"].append({"day": day.isoformat(), "field": "bars",
                                      "why": f"the minute bars: {type(exc).__name__}: {str(exc)[:160]}"})
            continue
        if bar is None or not minutes:
            out["mismatches"].append({"day": day.isoformat(), "field": "bars",
                                      "why": "no daily bar" if bar is None else "no minute bars"})
            continue
        open_at = dt.time(9, 30)
        close_at = dt.time(13, 0) if early[day] else dt.time(16, 0)
        session = [r for r in minutes if open_at <= ny_moment(r["t"]).time() < close_at
                   and ny_moment(r["t"]).date() == day]
        whole = [r for r in minutes if ny_moment(r["t"]).date() == day]
        reg, ext = _aggregate(session), _aggregate(whole)
        if not session:
            out["mismatches"].append({"day": day.isoformat(), "field": "bars", "why": "no minute bar in the session"})
            continue
        out["compared"] += 1
        extended = False
        for field in FIELDS:
            value = _num(bar.get(field))
            if _same(value, reg[field]):
                continue
            if field == "h" and value is not None and reg["h"] is not None:
                beyond = value > reg["h"] * (1 + REGULAR_TOLERANCE)
            elif field == "l" and value is not None and reg["l"] is not None:
                beyond = value < reg["l"] * (1 - REGULAR_TOLERANCE)
            else:
                beyond = False
            only_extended = _same(value, ext[field]) and field in ("o", "c", "h", "l")
            matches = "extended" if (only_extended or beyond) else "neither"
            extended = extended or matches == "extended"
            out["mismatches"].append({"day": day.isoformat(), "field": field, "daily": value, "regular": reg[field],
                                      "extended": ext[field], "matches": matches})
        extended_days += 1 if extended else 0
    if extended_days:
        out["verdict"] = "extended"
        out["why"] = (f"on {extended_days} of {out['compared']} days the 1Day bar holds prices from outside the regular "
                      "session: the store must be built from 1Min bars (a stop for E1)")
    elif out["compared"] == len(days) and not out["mismatches"]:
        out["verdict"] = "regular"
    else:
        out["why"] = (f"{out['compared']} of {len(days)} days compared; {len(out['mismatches'])} fields or days do not "
                      "match the regular session's minutes, none of them only the extended day's")
    return out


def regular_days(calendar: Sequence[tuple[dt.date, bool]], n: int = REGULAR_DAYS) -> list[dt.date]:
    """The days the regular-session check reads: the last `n` sessions of `calendar`, the latest half day in it standing
    in for the oldest of them when none of the `n` is one (so the 13:00 close is checked too)."""
    sessions = [d for d, _ in calendar]
    days = sessions[-n:]
    halves = [d for d, early in calendar if early]
    if days and halves and not any(early for d, early in calendar[-n:]):
        days = sorted([halves[-1], *days[1:]])
    return days


# ------------------------------------------------------------------------------------------------- the audit
def _rows_by_day(rows: Sequence[Mapping[str, Any]], check: _Check, symbol: str, label: str
                 ) -> dict[dt.date, Mapping[str, Any]]:
    out: dict[dt.date, Mapping[str, Any]] = {}
    for row in rows:
        try:
            day = ny_day(row.get("t"))
        except (TypeError, ValueError):
            check.add(f"{symbol} {label}: a bar time that is not a day ({str(row.get('t'))[:30]})")
            continue
        if day in out:
            check.add(f"{symbol} {label}: {day} twice")
        out[day] = row
    return out


def audit(calendar: Sequence[tuple[dt.date, bool]], raw: Mapping[str, Sequence[Mapping[str, Any]]],
          adj: Mapping[str, Sequence[Mapping[str, Any]]], *, regular: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """{passed, checks: {calendar, ohlc, splits, volume, regular}: each {passed, problems: [...] (at most 20), count}}
    (the module docstring). `calendar`: (session, early close) pairs, oldest first (`store.nyse_sessions`). `raw` and
    `adj`: `fetch`'s answers for adjustment=raw and adjustment=all. `regular`: `regular_session_check`'s answer (None:
    not run, "unverified"). Pure."""
    checks = {name: _Check() for name in CHECKS}
    sessions = [d for d, _ in calendar]
    known = set(sessions)
    last = sessions[-1] if sessions else None
    index = {d: i for i, d in enumerate(sessions)}
    cal, ohlc, splits, volume = checks["calendar"], checks["ohlc"], checks["splits"], checks["volume"]
    splits.extra["found"] = {}
    if not sessions:
        cal.add("the calendar has no session")
    if CALENDAR_SYMBOL not in raw:
        cal.add(f"no {CALENDAR_SYMBOL} bars: the calendar cannot be checked")
    for symbol in sorted(set(raw) | set(adj)):
        r_rows = _rows_by_day(raw.get(symbol) or [], cal, symbol, "raw")
        a_rows = _rows_by_day(adj.get(symbol) or [], cal, symbol, "all")
        if not r_rows:
            cal.add(f"{symbol}: no bars")
            continue
        if set(r_rows) != set(a_rows):
            only = sorted(set(r_rows) ^ set(a_rows))
            cal.add(f"{symbol}: the raw and all series disagree on {len(only)} days (first {only[0]})")
        extra = sorted(d for d in r_rows if d not in known)
        if extra:
            cal.add(f"{symbol}: {len(extra)} bars on days that are not sessions (first {extra[0]})")
        days = sorted(d for d in r_rows if d in known)
        if days and last is not None:
            first = sessions[0] if symbol == CALENDAR_SYMBOL else days[0]
            want = sessions[index[first]:]
            missing = sorted(set(want) - set(days))
            if missing:
                cal.add(f"{symbol}: {len(missing)} sessions with no bar from {first} (first {missing[0]})")
        for label, rows in (("raw", r_rows), ("all", a_rows)):
            for day in sorted(rows):
                bar = rows[day]
                o, h, l, c = (_num(bar.get(k)) for k in ("o", "h", "l", "c"))
                if None in (o, h, l, c):
                    ohlc.add(f"{symbol} {label} {day}: a price is missing or not a finite number")
                elif not (0 < l <= min(o, c) <= max(o, c) <= h):
                    ohlc.add(f"{symbol} {label} {day}: not 0 < low <= open, close <= high")
        for day in sorted(r_rows):
            v = _num(r_rows[day].get("v"))
            if v is None or v <= 0:
                volume.add(f"{symbol} raw {day}: no volume")
        # Splits: the raw/all close ratio's jumps against the raw close's own moves, on the symbol's own sessions.
        common = [d for d in days if d in a_rows]
        found = []
        prev = None
        for day in common:
            rc, ac = _num(r_rows[day].get("c")), _num(a_rows[day].get("c"))
            if rc is None or ac is None or rc <= 0 or ac <= 0:
                prev = None
                continue
            if prev is not None:
                p_day, p_rc, p_ratio = prev
                jump = p_ratio / (rc / ac)
                move = p_rc / rc
                if abs(jump - 1.0) > SPLIT_JUMP:
                    if abs(move / jump - 1.0) <= SPLIT_RAW_TOLERANCE:
                        found.append([day.isoformat(), round(jump, 4)])
                    else:
                        splits.add(f"{symbol} {day}: the raw/all ratio jumps by {jump:.4f} and the raw close does not "
                                   "show it (an adjustment no split explains)")
                elif abs(move - 1.0) > RAW_JUMP and abs(1.0 / move - 1.0) > RAW_JUMP:
                    splits.add(f"{symbol} {day}: the raw close moves by a factor {move:.4f} with no ratio jump (a split "
                               "the all series did not adjust)")
            prev = (day, rc, rc / ac)
        if found:
            splits.extra["found"][symbol] = found
    reg = dict(regular or {"verdict": "unverified", "why": "the regular-session check was not run"})
    verdict = reg.get("verdict") if reg.get("verdict") in ("regular", "extended", "unverified") else "unverified"
    rc = checks["regular"]
    for row in reg.get("mismatches") or []:
        if isinstance(row, Mapping):
            rc.add(f"{row.get('day')} {row.get('field')}: {row.get('matches') or row.get('why') or 'differs'}")
    if verdict == "unverified" and not rc.count:
        rc.add(str(reg.get("why") or reg.get("error") or "unverified"))
    rc.extra.update(verdict=verdict, days=list(reg.get("days") or []), compared=reg.get("compared"),
                    mismatches=list(reg.get("mismatches") or [])[:PROBLEMS_LISTED * 5], why=reg.get("why"),
                    error=reg.get("error"))
    out = {name: check.out() for name, check in checks.items() if name != "regular"}
    out["regular"] = rc.out(passed=verdict != "extended")
    return {"passed": all(c["passed"] for c in out.values()), "checks": out, "sessions": len(sessions),
            "symbols": len(raw)}


# ------------------------------------------------------------------------------------------------- the job
def universe(constitution: Mapping[str, Any] | None = None) -> dict[str, str]:
    """{symbol: class} the job fetches: `config.UNIVERSE`, bounded by the constitution's `equity_money.universe` when the
    constitution carries one (a symbol both name, with the same class), in `config.UNIVERSE`'s order."""
    from ..equity import config

    if constitution is None:
        from ..constitution import CONSTITUTION as constitution  # noqa: N811
    block = (constitution or {}).get("equity_money") if isinstance(constitution, Mapping) else None
    named = (block or {}).get("universe") if isinstance(block, Mapping) else None
    if not isinstance(named, Mapping):
        return dict(config.UNIVERSE)
    allowed = {(str(s), str(k)) for k, rows in named.items() for s in rows or ()}
    return {s: k for s, k in config.UNIVERSE.items() if (s, k) in allowed}


def last_closed(now: float) -> dt.date:
    """The last NYSE session closed (and settled, `direction.CLOSE_SETTLE_SECONDS`) at `now`."""
    from ltcm.data import previous_session

    from .direction import CLOSE_SETTLE_SECONDS

    moment = dt.datetime.fromtimestamp(float(now) - CLOSE_SETTLE_SECONDS, dt.timezone.utc)
    session = previous_session(moment)
    if session is None:
        raise ValueError("no closed session in the calendar's horizon")
    return dt.date.fromisoformat(str(session.date))


def series_of(raw_rows: Sequence[Mapping[str, Any]], all_rows: Sequence[Mapping[str, Any]], *, last: dt.date
              ) -> dict[str, Any]:
    """One symbol's `write_store` series from its audited rows: its sessions through `last`, raw and all aligned."""
    raw = {ny_day(r["t"]): r for r in raw_rows}
    adj = {ny_day(r["t"]): r for r in all_rows}
    days = sorted(d for d in raw if d in adj and d <= last)
    out: dict[str, Any] = {"days": days}
    for field in FIELDS:
        out[f"raw_{field}"] = [float(raw[d][field]) for d in days]
    for field in ("o", "h", "l", "c"):
        out[f"all_{field}"] = [float(adj[d][field]) for d in days]
    return out


def _cut(rows: Mapping[str, Sequence[Mapping[str, Any]]], last: dt.date) -> dict[str, list[Mapping[str, Any]]]:
    """Every symbol's rows through `last` (a bar after it is a session not closed: dropped)."""
    return {s: [r for r in v if ny_day(r["t"]) <= last] for s, v in rows.items()}


def run(ctx: Any) -> dict[str, Any]:
    """The job (the module docstring): {"ok": True, "symbols", "sessions", "fetched_through", "audit", "regular"} or
    {"status": "failed", "ok": False, "error"}."""
    from ..equity import store as eq_store

    root = Path(ctx.root)
    now = ctx.now()
    classes = universe()
    symbols = list(classes)
    if not symbols:
        return {"status": "failed", "ok": False, "error": "the universe is empty"}
    try:
        last = last_closed(now)
        first = dt.date.fromisoformat(FIRST_DAY)
        raw = _cut(fetch(ctx.gateway, symbols, FIRST_DAY, last.isoformat(), adjustment="raw"), last)
        adj = _cut(fetch(ctx.gateway, symbols, FIRST_DAY, last.isoformat(), adjustment="all"), last)
        calendar = list(eq_store.nyse_sessions(first, last))
    except Exception as exc:  # noqa: BLE001 - a gateway error writes nothing: a failed receipt, retried in its grace
        return {"status": "failed", "ok": False, "error": f"{type(exc).__name__}: {str(exc)[:200]}"}
    regular = regular_session_check(ctx.gateway, CALENDAR_SYMBOL, regular_days(calendar))
    result = audit(calendar, raw, adj, regular=regular)
    counts = {name: {"passed": c["passed"], "count": c["count"]} for name, c in result["checks"].items()}
    verdict = result["checks"]["regular"]["verdict"]
    if not result["passed"]:
        failed = [name for name, c in result["checks"].items() if not c["passed"]]
        return {"status": "failed", "ok": False, "audit": counts, "regular": verdict,
                "error": f"the audit failed ({', '.join(failed)}): nothing written, the last good store stays"}
    try:
        series = {s: series_of(raw[s], adj[s], last=last) for s in symbols if raw.get(s)}
        manifest = eq_store.write_store(root / STORE_DIR, calendar=calendar, series=series,
                                        classes={s: classes[s] for s in series}, fetched_through=last, source=SOURCE,
                                        gate=True, audit=result)
    except Exception as exc:  # noqa: BLE001 - nothing written (the writer is atomic): the last good store stays
        return {"status": "failed", "ok": False, "audit": counts, "regular": verdict,
                "error": f"the store could not be written: {type(exc).__name__}: {str(exc)[:200]}"}
    if verdict != "regular":
        ctx.alert("warning", f"equity_data: the 1Day bars' regular session is {verdict} (the design's fact 1): "
                             "the store is written and the verdict is in its manifest's audit")
    return {"ok": True, "symbols": len(series), "sessions": len(calendar), "fetched_through": last.isoformat(),
            "audit": counts, "regular": verdict, "splits": sum(len(v) for v in result["checks"]["splits"]["found"].values()),
            "version": (manifest or {}).get("version") if isinstance(manifest, Mapping) else None}


__all__ = ["FIRST_DAY", "STORE_DIR", "BARS", "MAX_PAGES", "SPLIT_JUMP", "REGULAR_DAYS", "REGULAR_TOLERANCE", "fetch",
           "regular_session_check", "audit", "run", "universe", "last_closed", "regular_days", "series_of", "ny_day",
           "SOURCE", "CALENDAR_SYMBOL", "SPLIT_RAW_TOLERANCE", "RAW_JUMP", "CHECKS"]
