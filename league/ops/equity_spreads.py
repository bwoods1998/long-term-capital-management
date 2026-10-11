"""The `equity_spreads` job: each panel name's half-spread at the instants the book trades (D20).

Owner: package B of release E4. Protected (league/ops/). The registry row is package A's patch (E4-SPEC 13).

A sample is the median over the quotes of one `WINDOW_S`-second window of (ask - bid) / (ask + bid), quotes with bid >
0 and ask > bid, from `GET /v1/alpaca/v2/stocks/quotes` (one symbol, one window, `sort=asc`, `feed=sip`, `asof`
inside the name's spell). Samples come from the six `league.xs.config.TRAIN_YEARS` only (a cost table must not read a
sealed year), `SESSIONS_YEAR` sessions a year, at `TIMES_ET`: 09:32:00, when the book sends its entries (at 09:30:30
many NYSE names have not had their opening print), and 15:55:00. A sample above `league.xs.config.HS_MAX_BP` is
DROPPED and counted (the book sends no entry on a quote wider than 2% of the mid). Resumable from spreads.json, at
most `CALLS_RUN` calls a run (about 49,000 in all); then monthly, new assets only. Package A's next run turns the
table into panel/hs.npy.

The receipt carries counts and shares, never a quote, a price or a ticker.

D20, AS THIS MODULE HOLDS IT (each a formula `test_equity_spreads.py` checks on invented quotes):
- a name's figure at a fill point is the 75th percentile of its KEPT samples there (`percentile`: the sorted samples
  read at position 0.75 x (n - 1), a straight line between the two it falls between), in basis points of the mid;
- the universe's figure at a fill point (`default`) is the 75th percentile, over the names with at least
  `MIN_SAMPLES` kept samples there, of max(`HS_FLOOR_BP`, the name's figure); with no such name, `HS_FALLBACK_BP`;
- what a fill is charged (`name_bp`): max(`HS_FLOOR_BP`, the name's figure) with at least `MIN_SAMPLES` kept samples
  at that point, else the universe's figure, else (no spreads file) `HS_FALLBACK_BP`. Package A's
  `equity_panel.hs_table` writes that reading into panel/hs.npy.

THE FILE, `<state>/equity-daily/spreads.json` (600, atomic; House only): the layout's keys {"version", "sampled":
{year: [day...]}, "names": {aid: {"open_bp", "close_bp", "n_open", "n_close"}}, "default": {"open_bp", "close_bp"},
"dropped": {exchange: {"open": share, "close": share}}, "calls", "done"} and, beside them, what makes the job
resumable and its report: "samples" {aid: {"exchange", "open": {day: bp | null}, "close": {day: bp | null}}} (null:
the window held no valid quote, or the venue refused the request: an answer, not asked again), "early" (the first
week's 09:30:30 samples of `EARLY_NAMES` fixed names) with "early_names" and "early_report" (the two medians over
the pairs sampled at both instants: report only), "dropped_all", "counts", "full", "warnings", "runs", "checked_at".

A RUN: `league.xs.config.quiet` first; then the work still owed (every member of a sampled day, at both instants,
with no answer yet: the fixed names' and their early samples first), a call at a time, `PAUSE_S` before each, until
`CALLS_RUN` calls, `BUDGET_S` seconds or `ERRORS_STOP` errors in a row (the venue or the gateway is down: what was
answered is kept, the receipt is a failed one and the next run goes on). The file is rewritten every `SAVE_EVERY`
calls, so a killed run loses little. A request the venue REFUSES (HTTP 400, 404 or 422) is an answer of no sample;
a run in which more than `REFUSED_MAX` of at least `REFUSED_MIN` calls were refused keeps none of those refusals
and fails (the request itself is then wrong, and a table of nulls would silently price every name at the default).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import math
import statistics
import time
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from zoneinfo import ZoneInfo

QUOTES = "/v1/alpaca/v2/stocks/quotes"
TIMES_ET = ("09:32:00", "15:55:00")
#: The first week's report-only comparison instant (fact 3: how much the instant matters).
EARLY_ET = "09:30:30"
EARLY_NAMES = 20
WINDOW_S = 2
SESSIONS_YEAR = 8
LIMIT = 50
CALLS_RUN = 6000
MIN_SAMPLES = 8
DROPPED_WARNING = 0.10
VERSION = "xs-spreads-v1"
FILE = "spreads.json"
#: The job's own wall (seconds): what `league.xs.config.quiet` is asked with (held equal to its registry row).
WALL_S = 3000
#: The equity lane's state directory (`league.ops.equity_data.STORE_DIR`; spelled here, a test holds them equal).
STORE_DIR = "equity-daily"
#: The fill points, in `TIMES_ET`'s order and panel/hs.npy's column order.
POINTS = ("open", "close")
#: Seconds waited before every request, and the seconds after which a run asks no more (inside `WALL_S`, with room
#: for one last request and the file).
PAUSE_S = 0.1
BUDGET_S = 2400.0
#: The file is rewritten after this many calls of a run (a killed run loses at most these).
SAVE_EVERY = 500
#: This many errors in a row end a run (the venue or the gateway is down).
ERRORS_STOP = 10
#: A request the venue answers with one of these is refused for good: an answer of no sample.
REFUSED_STATUS = (400, 404, 422)
#: A run with at least `REFUSED_MIN` calls of which more than this share were refused keeps none of the refusals.
REFUSED_MAX = 0.20
REFUSED_MIN = 50
#: Once every sample is taken, new assets are looked for this often (seconds: four weeks).
MONTHLY_S = 28 * 86400.0
#: The dropped share is a warning only on at least this many samples at a fill point.
DROPPED_MIN = 200
NEW_YORK = ZoneInfo("America/New_York")
UNKNOWN_EXCHANGE = "unknown"


# ------------------------------------------------------------------------------------------------- small helpers
def _figure(value: Any) -> float | None:
    """A positive finite number, or None."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(float(value)) and float(value) > 0 else None


def percentile(values: Sequence[float], q: float = 75.0) -> float | None:
    """The `q`th percentile of `values` (None for none): the sorted values read at position q / 100 x (n - 1), a
    straight line between the two it falls between."""
    ordered = sorted(float(v) for v in values)
    if not ordered:
        return None
    position = (len(ordered) - 1) * float(q) / 100.0
    low = int(math.floor(position))
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (position - low) * (ordered[high] - ordered[low])


def _utc(moment: dt.datetime) -> str:
    return moment.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _moment(stamp: Any) -> dt.datetime | None:
    """A quote's time as a moment, or None when it is not one with a zone."""
    try:
        moment = dt.datetime.fromisoformat(str(stamp or "").replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo is not None else None


# ------------------------------------------------------------------------------------------------- the days
def sample_days(calendar: Sequence[tuple[dt.date, bool]]) -> dict[int, list[dt.date]]:
    """{year: [day]} for the six Train years: session index round((j + 0.5) x n / 8), j = 0..7; a half day moves to
    the next full session.

    `calendar`: (session, early close) pairs (`league.equity.store.nyse_sessions`); n = the year's sessions in it; the
    rounding is half up. A half day at the year's end with no full session after it moves to the last full session
    before it. A year of `league.xs.config.TRAIN_YEARS` with fewer than `SESSIONS_YEAR` sessions in the calendar has
    no day; a session of any other year is never one."""
    from ..xs import config as xs_config

    by_year: dict[int, list[tuple[dt.date, bool]]] = {}
    for day, early in calendar:
        by_year.setdefault(day.year, []).append((day, bool(early)))
    out: dict[int, list[dt.date]] = {}
    for year in xs_config.TRAIN_YEARS:
        rows = sorted(by_year.get(year) or [])
        n = len(rows)
        if n < SESSIONS_YEAR:
            continue
        picked: list[dt.date] = []
        for j in range(SESSIONS_YEAR):
            index = min(n - 1, ((2 * j + 1) * n + SESSIONS_YEAR) // (2 * SESSIONS_YEAR))
            k = index
            while k < n and rows[k][1]:
                k += 1
            if k >= n:
                k = index
                while k >= 0 and rows[k][1]:
                    k -= 1
            if k >= 0 and rows[k][0] not in picked:
                picked.append(rows[k][0])
        out[year] = sorted(picked)
    return out


# ------------------------------------------------------------------------------------------------- one sample
def sample(gateway: Any, symbol: str, day: dt.date, time_et: str, *, asof: str | None) -> float | None:
    """One sample (a half-spread fraction) of `symbol` at `time_et` of `day`, or None when the window holds no valid
    quote.

    ONE request: the first `LIMIT` quotes of the `WINDOW_S` seconds from `time_et` (New York time), oldest first. A
    quote counts when its bid is above 0, its ask above its bid and its time inside the window; the sample is the
    median of (ask - bid) / (ask + bid) over them. ValueError, and no request, for a day outside
    `league.xs.config.TRAIN_YEARS` (the cost table reads no other year); ValueError for an answer that is not the
    venue's shape. A gateway error is the caller's to read."""
    from ..xs import config as xs_config

    if day.year not in xs_config.TRAIN_YEARS:
        raise ValueError(f"a spread sample of {day.year}: the cost table reads the Train years only")
    start = dt.datetime.combine(day, dt.time.fromisoformat(time_et), NEW_YORK)
    end = start + dt.timedelta(seconds=WINDOW_S)
    params: dict[str, Any] = {"symbols": symbol, "start": _utc(start), "end": _utc(end), "limit": LIMIT,
                              "feed": "sip", "sort": "asc"}
    if asof:
        params["asof"] = asof
    answer = gateway.get(QUOTES, params)
    if not isinstance(answer, Mapping) or "quotes" not in answer:
        raise ValueError("the quotes answer has no quotes")
    quotes = answer["quotes"]
    if quotes is None:
        return None
    if not isinstance(quotes, Mapping):
        raise ValueError("the quotes are not an object by symbol")
    rows = quotes.get(symbol)
    if rows is None:
        return None
    if not isinstance(rows, list):
        raise ValueError("a symbol's quotes are not a list")
    ratios = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("a quote is not an object")
        bid, ask, at = _figure(row.get("bp")), _figure(row.get("ap")), _moment(row.get("t"))
        if bid is None or ask is None or at is None or not ask > bid or not start <= at <= end:
            continue
        ratios.append((ask - bid) / (ask + bid))
    return statistics.median(ratios) if ratios else None


# ------------------------------------------------------------------------------------------------- the table
def summarize(samples: Mapping[Any, Any]) -> dict[str, Any]:
    """spreads.json's `names`, `default` and `dropped` from the samples (D20): per name and fill point the 75th
    percentile of its kept samples and their count; the universe's 75th percentile; the dropped share by listing
    exchange and fill point (a share above `DROPPED_WARNING` at either is a warning).

    `samples`: {aid: {"exchange": str | None, "open": {day: bp | None}, "close": {day: bp | None}}}, a sample in
    basis points of half-spread (None: an answer with no sample). KEPT: a positive finite sample at or under
    `league.xs.config.HS_MAX_BP`; DROPPED: one above it. {"names": {aid: {"open_bp", "close_bp" (None with no kept
    sample), "n_open", "n_close"}}, "default": {"open_bp", "close_bp"}, "dropped": {exchange: {"open", "close"}}
    (shares of the samples with a quote; None with none), "dropped_all": the same over every exchange, "counts":
    {exchange: {point: {"kept", "dropped", "empty"}}}, "full": the names with at least `MIN_SAMPLES` kept samples at
    BOTH points, "warnings": [text...]}. Pure."""
    from ..xs import config as xs_config

    names: dict[str, dict[str, Any]] = {}
    counts: dict[str, dict[str, dict[str, int]]] = {}
    figures: dict[str, list[float]] = {point: [] for point in POINTS}
    full = 0
    for aid in sorted(samples, key=str):
        row = samples[aid] if isinstance(samples[aid], Mapping) else {}
        exchange = str(row.get("exchange") or UNKNOWN_EXCHANGE)
        tally = counts.setdefault(exchange, {point: {"kept": 0, "dropped": 0, "empty": 0} for point in POINTS})
        out: dict[str, Any] = {}
        for point in POINTS:
            kept = []
            taken = row.get(point) if isinstance(row.get(point), Mapping) else {}
            for value in taken.values():
                value = _figure(value)
                if value is None:
                    tally[point]["empty"] += 1
                elif value > xs_config.HS_MAX_BP:
                    tally[point]["dropped"] += 1
                else:
                    tally[point]["kept"] += 1
                    kept.append(value)
            figure = percentile(kept)
            out[f"{point}_bp"] = None if figure is None else round(figure, 4)
            out[f"n_{point}"] = len(kept)
            if figure is not None and len(kept) >= MIN_SAMPLES:
                figures[point].append(max(xs_config.HS_FLOOR_BP, figure))
        full += 1 if all(out[f"n_{point}"] >= MIN_SAMPLES for point in POINTS) else 0
        names[str(aid)] = {key: out[key] for key in ("open_bp", "close_bp", "n_open", "n_close")}
    default = {}
    for i, point in enumerate(POINTS):
        figure = percentile(figures[point])
        default[f"{point}_bp"] = round(xs_config.HS_FALLBACK_BP[i] if figure is None else figure, 4)

    def share(rows: Sequence[Mapping[str, int]]) -> float | None:
        dropped = sum(r["dropped"] for r in rows)
        quoted = dropped + sum(r["kept"] for r in rows)
        return round(dropped / quoted, 4) if quoted else None

    dropped = {exchange: {point: share([tally[point]]) for point in POINTS} for exchange, tally in sorted(counts.items())}
    dropped_all = {point: share([tally[point] for tally in counts.values()]) for point in POINTS}
    warnings = []
    for point in POINTS:
        quoted = sum(tally[point]["kept"] + tally[point]["dropped"] for tally in counts.values())
        if quoted >= DROPPED_MIN and (dropped_all[point] or 0.0) > DROPPED_WARNING:
            above = [f"{exchange} {dropped[exchange][point]:.0%}" for exchange in dropped
                     if (dropped[exchange][point] or 0.0) > DROPPED_WARNING]
            warnings.append(f"{dropped_all[point]:.0%} of the {quoted} spread samples at the {point} are wider than "
                            f"{xs_config.HS_MAX_BP:g} bp and were dropped (by listing exchange: {', '.join(above)})")
    return {"names": names, "default": default, "dropped": dropped, "dropped_all": dropped_all, "counts": counts,
            "full": full, "warnings": warnings}


def name_bp(table: Mapping[str, Any] | None, aid: Any) -> tuple[float, float]:
    """D20, WHAT A FILL IS CHARGED: (the half-spread at the open, at the close) of `aid`, in basis points, from a
    spreads table (spreads.json as read; None: there is no file): max(`HS_FLOOR_BP`, the name's 75th percentile) with
    at least `MIN_SAMPLES` kept samples at that point, else the universe's figure, else `HS_FALLBACK_BP`; never under
    the floor."""
    from ..xs import config as xs_config

    names = table.get("names") if isinstance(table, Mapping) else None
    row = names.get(str(aid)) if isinstance(names, Mapping) else None
    default = table.get("default") if isinstance(table, Mapping) else None
    out = []
    for i, point in enumerate(POINTS):
        value = None
        if isinstance(row, Mapping) and isinstance(row.get(f"n_{point}"), int) and row[f"n_{point}"] >= MIN_SAMPLES:
            value = _figure(row.get(f"{point}_bp"))
        if value is None and isinstance(default, Mapping):
            value = _figure(default.get(f"{point}_bp"))
        if value is None:
            value = xs_config.HS_FALLBACK_BP[i]
        out.append(max(xs_config.HS_FLOOR_BP, value))
    return out[0], out[1]


def read(root: str | Path) -> dict[str, Any] | None:
    """spreads.json under `root` (`<state>/equity-daily`) as written, or None when there is none of this version."""
    from .context import read_json

    held = read_json(Path(root) / FILE)
    return held if isinstance(held, dict) and held.get("version") == VERSION else None


# ------------------------------------------------------------------------------------------------- the work owed
def exchanges(root: str | Path) -> dict[str, str]:
    """{aid: its listing exchange} from universe/assets.json (`alpaca.exchange`); an asset the venue no longer lists
    has none. {} when the file cannot be read: a label of the dropped counts, never a rule."""
    from ..xs import store as xs_store
    from .context import read_json

    assets = read_json(Path(root) / xs_store.UNIVERSE_DIR / "assets.json", {})
    out: dict[str, str] = {}
    for aid, row in (assets.items() if isinstance(assets, Mapping) else ()):
        venue = row.get("alpaca") if isinstance(row, Mapping) else None
        name = venue.get("exchange") if isinstance(venue, Mapping) else None
        if isinstance(name, str) and name.strip():
            out[str(aid)] = name.strip().upper()[:16]
    return out


def early_names(first: Sequence[int]) -> list[int]:
    """The `EARLY_NAMES` fixed names of the first week's comparison: the first sampled day's members, by aid, taken
    at even steps (so they are not one corner of the index)."""
    ordered = sorted({int(aid) for aid in first})
    step = max(1, len(ordered) // EARLY_NAMES)
    return ordered[::step][:EARLY_NAMES]


def plan(members: Callable[[dt.date], Sequence[tuple[int, str]]], days: Mapping[int, Sequence[dt.date]],
         state: Mapping[str, Any]) -> dict[str, Any]:
    """The work a run still owes: {"items": [(kind, aid, symbol, day)...], "total", "early_names"}. `members(day)`:
    (aid, symbol) of every member of `day` (`league.xs.store.Universe.members`). An item's kind is "open", "close" or
    "early" (the fixed names' 09:30:30 sample); an item with an answer in `state` is not owed. The fixed names' items
    come first, each day's early sample before its two others, so the first night's report has its pairs."""
    samples = state.get("samples") if isinstance(state.get("samples"), Mapping) else {}
    early = state.get("early") if isinstance(state.get("early"), Mapping) else {}
    rows: list[tuple[int, str, dt.date]] = []
    for year in sorted(days):
        for day in sorted(days[year]):
            rows.extend((int(aid), str(symbol), day) for aid, symbol in sorted(members(day)))
    fixed = [int(aid) for aid in state.get("early_names") or []]
    if not fixed and rows:
        fixed = early_names([aid for aid, _, day in rows if day == rows[0][2]])
    chosen = set(fixed)
    first, rest, total = [], [], 0
    for aid, symbol, day in rows:
        key, queue = day.isoformat(), (first if aid in chosen else rest)
        if aid in chosen:
            total += 1
            if key not in (early.get(str(aid)) or {}):
                queue.append(("early", aid, symbol, day))
        held = samples.get(str(aid)) if isinstance(samples.get(str(aid)), Mapping) else {}
        for point in POINTS:
            total += 1
            if key not in (held.get(point) or {}):
                queue.append((point, aid, symbol, day))
    return {"items": first + rest, "total": total, "early_names": fixed}


def early_report(state: Mapping[str, Any]) -> dict[str, Any]:
    """Fact 3, report only: over the (name, day) pairs sampled at both instants, the median half-spread at `EARLY_ET`
    and at the open's own instant, in basis points (no sample is dropped here: the comparison is of the instants)."""
    early = state.get("early") if isinstance(state.get("early"), Mapping) else {}
    samples = state.get("samples") if isinstance(state.get("samples"), Mapping) else {}
    before, at = [], []
    for aid, taken in early.items():
        opens = (samples.get(aid) or {}).get(POINTS[0]) or {}
        for day, value in (taken.items() if isinstance(taken, Mapping) else ()):
            a, b = _figure(value), _figure(opens.get(day))
            if a is not None and b is not None:
                before.append(a)
                at.append(b)
    return {"names": len(state.get("early_names") or []), "pairs": len(at), "early_et": EARLY_ET, "open_et": TIMES_ET[0],
            "median_early_bp": round(statistics.median(before), 4) if before else None,
            "median_open_bp": round(statistics.median(at), 4) if at else None}


# ------------------------------------------------------------------------------------------------- the job
def _blank() -> dict[str, Any]:
    return {"version": VERSION, "sampled": {}, "names": {}, "default": {}, "dropped": {}, "calls": 0, "done": False,
            "samples": {}, "early": {}, "early_names": [], "runs": 0, "checked_at": None}


def _state(root: Path) -> dict[str, Any]:
    """The file as a run goes on from it; a fresh state with no file. ValueError for a file that is not this version
    (nights of samples are never silently thrown away: an operator moves the file aside)."""
    from .context import read_json

    path = root / FILE
    if not path.exists():
        return _blank()
    held = read_json(path)
    if not isinstance(held, dict) or held.get("version") != VERSION or not isinstance(held.get("samples"), dict):
        raise ValueError(f"{FILE} is not a {VERSION} file: move it aside to start again")
    return {**_blank(), **held}


def _save(root: Path, state: dict[str, Any], exchange: Mapping[str, str], *, now: float, remaining: int) -> dict[str, Any]:
    from . import schedule as S
    from .context import write_json

    for aid, row in state["samples"].items():
        row["exchange"] = exchange.get(str(aid)) or row.get("exchange") or UNKNOWN_EXCHANGE
    summary = summarize(state["samples"])
    state.update({key: summary[key] for key in ("names", "default", "dropped", "dropped_all", "counts", "full",
                                                "warnings")})
    state.update(done=remaining == 0, remaining=remaining, early_report=early_report(state), updated_at=S.iso(now))
    write_json(root / FILE, state, indent=None)
    return summary


def run(ctx: Any, *, sleep: Callable[[float], None] = time.sleep) -> dict[str, Any]:
    """The job. Its first statement is `league.xs.config.quiet(ctx.now(), WALL_S)`. {"ok": True, "calls", "sampled",
    "empty", "refused", "errors", "remaining", "done", "calls_total", "names", "full", "dropped", "early"} (counts,
    shares and the report's two medians: never a quote, a price or a ticker); {"status": "skipped", "why"} inside a
    quiet window, before the universe exists, and between the monthly looks once every sample is taken; {"status":
    "failed", "ok": False, "error", ...the same counts} when the run was ended by errors or its refusals were not
    kept (the module docstring). `sleep`: the wait before each request (the tests pass a no-op)."""
    from ..xs import config as xs_config

    try:
        why = xs_config.quiet(ctx.now(), WALL_S)
    except Exception as exc:  # noqa: BLE001 - a job that cannot learn whether it stands at a wall does not start
        why = f"the quiet windows could not be read ({type(exc).__name__}: {str(exc)[:160]})"
        ctx.alert("warning", f"equity_spreads: {why}; the job did not run")
    if why is not None:
        return {"status": "skipped", "why": why}
    from ..equity import store as eq_store
    from ..xs import store as xs_store
    from . import schedule as S

    began = ctx.now()
    root = Path(ctx.root) / STORE_DIR
    try:
        state = _state(root)
    except ValueError as exc:
        return {"status": "failed", "ok": False, "error": str(exc)}
    checked = S.epoch(state.get("checked_at"))
    if state.get("done") and checked is not None and began - checked < MONTHLY_S:
        return {"status": "skipped", "why": "every sample is taken; new assets are looked for monthly"}
    if not (root / xs_store.UNIVERSE_DIR / "UNIVERSE_MANIFEST.json").exists():
        return {"status": "skipped", "why": "no universe yet"}
    try:
        universe = xs_store.Universe(root)
        years = xs_config.TRAIN_YEARS
        days = sample_days(eq_store.nyse_sessions(dt.date(min(years), 1, 1), dt.date(max(years), 12, 31)))
        owed = plan(universe.members, days, state)
        exchange = exchanges(root)
    except Exception as exc:  # noqa: BLE001 - nothing asked, nothing written
        return {"status": "failed", "ok": False, "error": f"the universe cannot be read: {type(exc).__name__}: "
                                                          f"{str(exc)[:200]}"}
    state["sampled"] = {str(year): [day.isoformat() for day in picked] for year, picked in sorted(days.items())}
    state["early_names"] = owed["early_names"]
    state["checked_at"] = S.iso(began)
    state["runs"] = int(state.get("runs") or 0) + 1
    items = owed["items"]
    before = int(state.get("calls") or 0)
    counts = {"calls": 0, "sampled": 0, "empty": 0, "refused": 0, "errors": 0}
    refusals: list[tuple[str, int, str]] = []
    streak, answered, error = 0, 0, None
    for kind, aid, symbol, day in items:
        if counts["calls"] >= CALLS_RUN or ctx.now() - began >= BUDGET_S:
            break
        sleep(PAUSE_S)
        counts["calls"] += 1
        key = day.isoformat()
        try:
            value = sample(ctx.gateway, symbol, day, EARLY_ET if kind == "early" else TIMES_ET[POINTS.index(kind)],
                           asof=key)
        except Exception as exc:  # noqa: BLE001 - a refusal is an answer; anything else leaves the item owed
            if getattr(exc, "status", None) not in REFUSED_STATUS:
                counts["errors"] += 1
                streak += 1
                if streak >= ERRORS_STOP:
                    error = (f"the run was ended: {streak} requests in a row failed, the last: {type(exc).__name__}: "
                             f"{str(exc)[:160]}")
                    break
                continue
            value = None
            counts["refused"] += 1
            refusals.append((kind, aid, key))
        else:
            counts["sampled" if value is not None else "empty"] += 1
        streak = 0
        bp = None if value is None else round(value * 1e4, 4)
        if kind == "early":
            state["early"].setdefault(str(aid), {})[key] = bp
        else:
            row = state["samples"].setdefault(str(aid), {"exchange": None, POINTS[0]: {}, POINTS[1]: {}})
            row.setdefault(kind, {})[key] = bp
        answered += 1
        if counts["calls"] >= REFUSED_MIN and counts["refused"] > REFUSED_MAX * counts["calls"]:
            error = (f"the venue refused {counts['refused']} of {counts['calls']} requests: the request is wrong, "
                     "none of those refusals is kept")
            for kind_, aid_, key_ in refusals:
                if kind_ == "early":
                    state["early"].get(str(aid_), {}).pop(key_, None)
                else:
                    state["samples"].get(str(aid_), {}).get(kind_, {}).pop(key_, None)
            answered -= len(refusals)
            break
        if counts["calls"] % SAVE_EVERY == 0:
            state["calls"] = before + counts["calls"]
            _save(root, state, exchange, now=ctx.now(), remaining=len(items) - answered)
    state["calls"] = before + counts["calls"]
    remaining = len(items) - answered
    summary = _save(root, state, exchange, now=ctx.now(), remaining=remaining)
    for text in summary["warnings"]:
        ctx.alert("warning", f"equity_spreads: {text}")
    report = state["early_report"]
    out: dict[str, Any] = {"ok": error is None, **counts, "remaining": remaining, "done": remaining == 0,
                           "calls_total": state["calls"], "names": len(summary["names"]), "full": summary["full"],
                           "dropped": summary["dropped_all"], "early": report if report["pairs"] else None}
    if error is not None:
        out.update(status="failed", error=error)
    return out


# ------------------------------------------------------------------------------------------------- the twins' reader
def panel_half_spread(root: str | Path) -> Callable[[str, str], tuple[float, float] | None] | None:
    """A PANEL LOT'S HALF-SPREAD for its replay twin (package B's patch 11 has `league.ops.twins.equity_twin` ask it
    when a lot's symbol is outside E1's universe): a reader `(symbol, ISO day) -> (half-spread fraction at the open,
    at the close) | None`, from panel/hs.npy through `league.xs.store.Universe.aid`; None when the panel store under
    `root` (`<state>/equity-daily`) has no half-spreads to read (no store, a file that does not match its manifest's
    sha256, arrays that do not agree, no universe). The reader answers None for a symbol that named no panel asset on
    that day, and for a row that is not two positive finite fractions: the twin then stays unpriceable."""
    import numpy as np

    from ..xs import store as xs_store
    from .context import read_json

    root = Path(root)
    folder = root / xs_store.PANEL_DIR
    try:
        shas = (read_json(folder / "PANEL_MANIFEST.json") or {}).get("sha256") or {}
        arrays = {}
        for name in ("aids.npy", "hs.npy"):
            raw = (folder / name).read_bytes()
            if hashlib.sha256(raw).hexdigest() != shas.get(name):
                return None
            arrays[name] = np.load(folder / name, allow_pickle=False)
        aids, hs = arrays["aids.npy"], np.asarray(arrays["hs.npy"], dtype=np.float64)
        if aids.ndim != 1 or hs.shape != (aids.shape[0], len(POINTS)):
            return None
        universe = xs_store.Universe(root)
    except Exception:  # noqa: BLE001 - no half-spreads to read: every panel twin stays unpriceable
        return None
    index = {int(aid): i for i, aid in enumerate(aids.tolist())}

    def reader(symbol: str, day: str) -> tuple[float, float] | None:
        try:
            row = index.get(int(universe.aid(str(symbol), dt.date.fromisoformat(str(day)))))
        except Exception:  # noqa: BLE001 - no such asset that day (KeyError), or a day that is not one
            return None
        if row is None:
            return None
        at_open, at_close = _figure(float(hs[row, 0])), _figure(float(hs[row, 1]))
        return None if at_open is None or at_close is None else (at_open, at_close)

    return reader


__all__ = ["QUOTES", "TIMES_ET", "EARLY_ET", "EARLY_NAMES", "WINDOW_S", "SESSIONS_YEAR", "LIMIT", "CALLS_RUN",
           "MIN_SAMPLES", "DROPPED_WARNING", "VERSION", "FILE", "WALL_S", "STORE_DIR", "POINTS", "PAUSE_S", "BUDGET_S",
           "SAVE_EVERY", "ERRORS_STOP", "REFUSED_STATUS", "REFUSED_MAX", "REFUSED_MIN", "MONTHLY_S", "DROPPED_MIN",
           "sample_days", "sample", "summarize", "run", "percentile", "name_bp", "read", "exchanges", "early_names",
           "plan", "early_report", "panel_half_spread"]
