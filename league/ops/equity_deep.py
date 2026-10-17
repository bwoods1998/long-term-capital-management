"""The `equity_deep` job: the deep store (league/deep/blocks.py) from the gateway's Tiingo route, audited, on the House.

Owner: R1 (history-expansion plan, A58). Protected (league/ops/). Run once, then on demand: daily at 06:40Z while
the store is not complete (no at-start trigger: a fetch of up to 55 minutes at a House start before an open would hold
the one ops child past the pre-open's grace, release E4's live-9); a complete store is a `skipped` receipt (job
setting `refetch` true in `<state>/ops.json` fetches it again). With `elane.deep.mode` "off" (the code's default) nothing runs.

THE SEAL. DVAL (2001-04-09..2008-12-31) is fetched BY THE HOUSE, through `GET /v1/tiingo/daily/<SYM>/prices` (the
gateway holds the owner's token; its allowlist is the 16 ETFs and 1999-01-04..2019-12-31, never 2020 on), straight
into `<state>/equity-deep/.staging/` (0700) and from there into `sealed/` (0700, the `DEEP_GATE` mark). It never
touches the desktop: no desktop copy exists for a snapshot to catch.

WHAT IS FETCHED (`plan`): per ETF of `config.FETCH_UNIVERSE`, one request a span: "history" (1999-01-04..2001-04-06),
"dval", "traind" (2009-01-02..2015-12-31), and "overlap" (2016-01-04..2019-12-31, for the SIP audit only: counted,
never kept). A span that ends before a fund's launch (`config.INCEPTION`) is not asked. The vendor's adjusted
columns never reach the House: the gateway answers raw OHLCV, divCash, splitFactor and `factorStep` (whether the
vendor's own adjustment factor changed that day), nothing else. Requests are paced (`PAUSE_S`: Tiingo Starter's 50
an hour) and a run stops at `MAX_REQUESTS` or `WALL_S`; the next run goes on from what is staged.

THE AUDIT (`audit`, once everything is staged). A FAILED AUDIT WRITES NOTHING: the staging is removed and the store is
left as it was. It checks:
- the calendar: league/deep/calendar.py's rules equal the pinned fixture; SPY's sessions in each span are the
  calendar's exactly; no fund has a bar off the calendar, or more than `GAP_MAX` missing sessions after its first;
- OHLC sanity: 0 < low <= min(open, close) <= max(open, close) <= high, volume >= 0, dividends >= 0, a split factor
  inside (0, 50];
- events: every day the vendor's factor stepped carries a listed event (divCash or splitFactor); unexplained steps
  fail; events with no step are counted;
- Tiingo against SIP on 2016-19 (the House's own store, `<state>/equity-daily`): closes agreeing (1 cent or 1 bp) on
  at least `CLOSE_AGREE` of the common sessions of every fund, else FAIL; opens counted, and an open agreement under
  `OPEN_AGREE` is reported as "disagree" (the owner's D3: a second vendor for the sealed opens), not a failure;
- stale closes (a close equal to the one before) and zero-volume sessions, by fund and year: a late sector SPDR is
  "clean" for 2005-08 when every year of it holds at most `STALE_MAX_A_YEAR` stale closes and no zero-volume day.

THE RECEIPT carries counts, days and verdicts only: integers, booleans and words, never a decimal (no price, return
or dividend amount; `test_deep_store.TheReceiptHasNoDecimals`).
"""

from __future__ import annotations

import datetime as dt
import shutil
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

ROUTE = "/v1/tiingo/daily/{symbol}/prices"
#: Tiingo Starter: 50 requests an hour. One every 75 seconds, with margin.
PAUSE_S = 75
MAX_REQUESTS = 40
WALL_S = 3300
GAP_MAX = 5
CLOSE_AGREE = 0.99
OPEN_AGREE = 0.95
STALE_MAX_A_YEAR = 3
LATE_YEARS = (2005, 2006, 2007, 2008)
SOURCE = "tiingo-eod"


def _spans() -> dict[str, tuple[dt.date, dt.date]]:
    from ..deep import config

    name, first, last = config.AUDIT_SPAN
    return {**config.SPANS, name: (first, last)}


def plan() -> list[tuple[str, str, dt.date, dt.date]]:
    """Every request of a full fetch: (symbol, span, first, last), in a fixed order."""
    from ..deep import config

    out = []
    for sym in config.FETCH_UNIVERSE:
        launch = config.INCEPTION.get(sym, config.FIRST_DAY)
        for span, (first, last) in _spans().items():
            if last >= launch:
                out.append((sym, span, first, last))
    return out


def _staged(staging: Path, span: str, sym: str) -> Path:
    return staging / span / f"{sym}.npz"


def complete(root: Path) -> bool:
    """A deep store whose manifest names every span of `plan` and a passed audit."""
    from ..deep import blocks

    try:
        store = blocks.DeepStore(root)
    except blocks.DeepMissing:
        return False
    if not store.audit().get("ok"):
        return False
    wanted = {(sym, span) for sym, span, _, _ in plan() if span in ("history", "dval", "traind")}
    return all(sym in store.symbols(span) for sym, span in wanted)


def fetch(ctx: Any, sym: str, first: dt.date, last: dt.date) -> tuple[list[dt.date], dict[str, list[float]], list[bool]]:
    """One request's (days, columns, factor steps). ValueError for an answer of another shape, a day outside the
    request, or a figure that is not a number."""
    from ..deep import blocks

    answer = ctx.gateway.get(ROUTE.format(symbol=sym), {"startDate": first.isoformat(), "endDate": last.isoformat()})
    rows = answer.get("rows") if isinstance(answer, Mapping) else None
    if not isinstance(rows, list):
        raise ValueError(f"the gateway's answer for {sym} {first}..{last} holds no rows")
    days, cols = blocks.rows_to_columns(rows)
    if days and not (first <= days[0] and days[-1] <= last):
        raise ValueError(f"the gateway answered {sym} with a day outside {first}..{last}")
    steps = [bool(row.get("factorStep")) for row in rows]
    return days, cols, steps


def _stage(staging: Path, span: str, sym: str, days: list[dt.date], cols: Mapping[str, Sequence[float]],
           steps: Sequence[bool]) -> None:
    import io
    import os

    from ..deep import blocks

    folder = staging / span
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(folder, 0o700)
    data = blocks.block_bytes(days, cols)
    buf = io.BytesIO()
    np.save(buf, np.array(steps, dtype=bool), allow_pickle=False)
    for path, body in ((_staged(staging, span, sym), data), (folder / f"{sym}.steps.npy", buf.getvalue())):
        tmp = path.with_name(f".{path.name}.tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(body)
        os.replace(tmp, path)


def _load(staging: Path, span: str, sym: str) -> tuple[dict[str, np.ndarray], np.ndarray]:
    from ..deep import blocks

    arrays = blocks.read_block(_staged(staging, span, sym).read_bytes())
    steps = np.load(staging / span / f"{sym}.steps.npy", allow_pickle=False)
    return arrays, steps


# ------------------------------------------------------------------------------------------------------------ the audit
def _ohlc_bad(a: Mapping[str, np.ndarray]) -> int:
    o, h, lo, c, v = (np.asarray(a[k], dtype=np.float64) for k in ("open", "high", "low", "close", "volume"))
    ok = (lo > 0) & (lo <= np.minimum(o, c)) & (np.maximum(o, c) <= h) & (v >= 0)
    ok &= (np.asarray(a["div"]) >= 0) & (np.asarray(a["split"]) > 0) & (np.asarray(a["split"]) <= 50)
    return int(np.count_nonzero(~ok))


def _sip(equity_root: Path, sym: str, a: Mapping[str, np.ndarray]) -> dict[str, Any]:
    """Tiingo against the House's SIP store on 2016-19: counts only."""
    from ..deep import blocks
    from ..equity.store import EquityStore

    store = EquityStore(equity_root)
    if sym not in store.symbols():
        return {"compared": 0, "close_agree": 0, "open_agree": 0, "close_ok": False, "open_ok": False}
    name, first, last = ("overlap", *_spans()["overlap"])
    bars = store.bars([sym], "train", history=0, start=first, end=last)
    sip = {int(d): (float(r[0]), float(r[3])) for d, r in zip(bars.days, bars.raw[sym]) if np.isfinite(r[3])}
    compared = close_ok = open_ok = 0
    for d, o, c in zip(a["days"], a["open"], a["close"]):
        hit = sip.get(int(d))
        if hit is None:
            continue
        compared += 1
        close_ok += int(abs(float(c) - hit[1]) <= max(0.011, 1e-4 * hit[1]))
        open_ok += int(abs(float(o) - hit[0]) <= max(0.011, 1e-4 * hit[0]))
    return {"compared": int(compared), "close_agree": int(close_ok), "open_agree": int(open_ok),
            "close_ok": bool(compared and close_ok >= CLOSE_AGREE * compared),
            "open_ok": bool(compared and open_ok >= OPEN_AGREE * compared)}


def audit(staging: Path, equity_root: Path) -> dict[str, Any]:
    """THE AUDIT of everything staged (the module docstring): {"ok", "failures": [...], and counts}. Counts, days
    and verdicts only."""
    from ..deep import blocks, calendar, config

    failures: list[str] = []
    out: dict[str, Any] = {"rows": {}, "gaps": {}, "off_calendar": {}, "ohlc_bad": {}, "unexplained": {},
                           "missed": {}, "events": {"dividends": 0, "splits": 0}, "sip": {}, "stale": {}}
    fixture_ok = tuple(calendar.deep_sessions()) == calendar.fixture()
    out["calendar_fixture"] = fixture_ok
    if not fixture_ok:
        failures.append("the deep calendar's rules differ from the pinned fixture")
    stale: dict[str, dict[str, dict[str, int]]] = {}
    for sym, span, first, last in plan():
        path = _staged(staging, span, sym)
        if not path.is_file():
            failures.append(f"{sym} {span} was not staged")
            continue
        a, steps = _load(staging, span, sym)
        days = [blocks.from_ordinal(int(d)) for d in a["days"]]
        out["rows"].setdefault(span, {})[sym] = len(days)
        sessions = calendar.sessions(first, last)
        allowed = set(sessions)
        off = sum(1 for d in days if d not in allowed)
        if off:
            out["off_calendar"].setdefault(span, {})[sym] = off
            failures.append(f"{sym} {span}: {off} bars off the calendar")
        if days:
            held = set(days)
            gaps = sum(1 for d in sessions if days[0] <= d <= days[-1] and d not in held)
            if gaps:
                out["gaps"].setdefault(span, {})[sym] = gaps
            if gaps > GAP_MAX:
                failures.append(f"{sym} {span}: {gaps} sessions missing after its first bar")
        if sym == "SPY" and days != sessions:
            failures.append(f"SPY's {span} sessions are not the calendar's")
        bad = _ohlc_bad(a)
        if bad:
            out["ohlc_bad"].setdefault(span, {})[sym] = bad
            failures.append(f"{sym} {span}: {bad} bars fail the OHLC sanity check")
        event = (np.asarray(a["div"]) > 0) | (np.asarray(a["split"]) != 1.0)
        steps = np.asarray(steps, dtype=bool)
        if steps.shape != event.shape:
            failures.append(f"{sym} {span}: the factor steps are not one a bar")
            continue
        unexplained = int(np.count_nonzero(steps & ~event))
        missed = int(np.count_nonzero(event & ~steps))
        if unexplained:
            out["unexplained"].setdefault(span, {})[sym] = unexplained
            failures.append(f"{sym} {span}: {unexplained} factor steps with no listed event")
        if missed:
            out["missed"].setdefault(span, {})[sym] = missed
        if span != "overlap":
            out["events"]["dividends"] += int(np.count_nonzero(np.asarray(a["div"]) > 0))
            out["events"]["splits"] += int(np.count_nonzero(np.asarray(a["split"]) != 1.0))
            c = np.asarray(a["close"], dtype=np.float64)
            v = np.asarray(a["volume"], dtype=np.float64)
            years = np.array([d.year for d in days])
            mine = stale.setdefault(sym, {"stale": {}, "zero_volume": {}})
            for year in sorted(set(years.tolist())):
                at = np.flatnonzero(years == year)
                same = int(np.count_nonzero(c[at[at > 0]] == c[at[at > 0] - 1]))
                mine["stale"][str(year)] = mine["stale"].get(str(year), 0) + same
                mine["zero_volume"][str(year)] = mine["zero_volume"].get(str(year), 0) + int(np.count_nonzero(v[at] == 0))
        else:
            try:
                out["sip"][sym] = _sip(equity_root, sym, a)
            except Exception as exc:  # noqa: BLE001 - no SIP store to audit against: fail closed
                out["sip"][sym] = {"error": type(exc).__name__}
            if not out["sip"][sym].get("close_ok"):
                failures.append(f"{sym}: Tiingo's 2016-19 closes do not agree with the House's SIP store")
    for sym, row in stale.items():
        late = [str(y) for y in LATE_YEARS]
        clean = all(row["stale"].get(y, 0) <= STALE_MAX_A_YEAR and row["zero_volume"].get(y, 0) == 0 for y in late)
        out["stale"][sym] = {**row, "clean": bool(clean)}
    opens = [row.get("open_ok") for row in out["sip"].values() if "open_ok" in row]
    out["open_audit"] = "agree" if opens and all(opens) else "disagree"
    out["failures"] = failures
    out["ok"] = not failures
    return out


# -------------------------------------------------------------------------------------------------------------- the job
def run(ctx: Any) -> dict[str, Any]:
    """THE JOB (the module docstring): {"status": "skipped", "why"} | {"ok", "fetched", "left"} while fetching |
    {"ok": True, "written": True, "audit"} | {"status": "failed", "ok": False, "error", "audit"} (nothing written)."""
    from ..deep import blocks, config
    from ..swarm import settings as settings_mod

    root = Path(ctx.root)
    if config.cfg(settings_mod.load(root, config=ctx.config))["mode"] == "off":
        return {"status": "skipped", "why": "elane.deep.mode is off"}
    deep = root / config.STORE_DIR
    own = ctx.job_settings()
    if complete(deep) and not own.get("refetch"):
        return {"status": "skipped", "why": "the deep store is complete (job setting refetch fetches it again)"}
    deep.mkdir(parents=True, exist_ok=True, mode=0o700)
    staging = deep / config.STAGING_DIR
    staging.mkdir(exist_ok=True, mode=0o700)
    pause = float(own.get("pause_s", PAUSE_S))
    began = time.monotonic()
    fetched, problems = 0, []
    todo = [row for row in plan() if not _staged(staging, row[1], row[0]).is_file()]
    for sym, span, first, last in todo:
        if fetched >= int(own.get("max_requests", MAX_REQUESTS)) or time.monotonic() - began > WALL_S - pause - 120:
            break
        if fetched:
            time.sleep(pause)
        try:
            days, cols, steps = fetch(ctx, sym, first, last)
            _stage(staging, span, sym, days, cols, steps)
        except Exception as exc:  # noqa: BLE001 - this request is asked again next run; the others go on
            problems.append(f"{sym} {span}: {type(exc).__name__}: {str(exc)[:160]}")
        fetched += 1
    left = sum(1 for sym, span, _, _ in plan() if not _staged(staging, span, sym).is_file())
    if left:
        out: dict[str, Any] = {"ok": not problems, "fetched": fetched, "left": left}
        if problems:
            out.update(status="failed", error="; ".join(problems)[:600])
        return out
    receipt = audit(staging, root / "equity-daily")
    if not receipt["ok"]:
        shutil.rmtree(staging, ignore_errors=True)   # A FAILED AUDIT WRITES NOTHING
        return {"status": "failed", "ok": False, "error": "the deep store's audit failed: " +
                "; ".join(receipt["failures"])[:500], "audit": receipt}
    keep = {}
    for sym, span, _, _ in plan():
        if span in config.SPANS:
            keep.setdefault(span, {})[sym] = _staged(staging, span, sym).read_bytes()
    from . import schedule

    blocks.write_store(deep, keep, audit=receipt, source=SOURCE, written_at=schedule.iso(ctx.now()))
    shutil.rmtree(staging, ignore_errors=True)
    return {"ok": True, "written": True, "fetched": fetched, "audit": receipt}


__all__ = ["ROUTE", "PAUSE_S", "MAX_REQUESTS", "WALL_S", "GAP_MAX", "CLOSE_AGREE", "OPEN_AGREE", "STALE_MAX_A_YEAR",
           "LATE_YEARS", "SOURCE", "plan", "complete", "fetch", "audit", "run"]
