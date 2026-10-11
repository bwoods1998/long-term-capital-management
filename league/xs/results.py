"""What a panel run returns, and what of it leaves each window.

Owner: package D.

THE RESULT RECORD (a plain dict; in-House only: `view` decides what a researcher sees):

    run_id, program, program_sha, run_sha, params, window, panel, half (None | 0 | 1: the PARENT's fact, set by
                `runner.Isolated.train`; the child cannot tell a half run from a whole one, it reads `elig0`), engine
                (`XS_ENGINE_VERSION`), data_version, universe (24 hex over the slice's columns: ids, `elig0`, the
                half-spreads), capital, k, rung, trials (1), status ("ok" | "disqualified" | "no_data"; "error" from
                `failed`), needs
    summary     {days, invested_days, rebalances (called decisions with a non-empty target), calls, lots, closed,
                round_trips, pnl, realized, fees, dividends (cash-book dollars), sum_r, sum_x, sum_x15, sum_u,
                sum_bench, sum_w, t_x, t_x_nw5 (Newey-West, lag 5), t_r, basket ("basket-led" when sum bench >= sum
                x, else "selection-led"), exposure_mean, names_mean, turnover (entry notional over E0, a year), costs,
                gross, delta (the sums of the residual's cost series, gross residual and diluted exposure),
                cost_share (costs over the gross residual, when that is above zero), dilution (delta over sum_w),
                cells {small, under5}, vanished {deal, other}, refused {no_bar, ahead, last}, sum_x_h0, sum_x_h1
                (sum x at haircut 0 and 1), close_dates, sd_date_return (over the run's close dates, the sd, ddof 1,
                of that date's summed lot net over their summed entry notional; None under 2 dates)}
    by_year     {year: {days, sum_x, sumsq_x, sum_x15, sum_r, rebalances, closed}}
    daily       rows in `DAILY`'s order, one a run session: the day (ISO), then THE PRE-REGISTERED SERIES of
                `placebo.residual` (constant-weight on E0, never the cash book): r, x, x15, u, w, bench (B), exits (lots
                fully exited that session), invested (a lot held at the close), and the cash book's equity beside
    lots        [{lid, id, cell, weight, decided_day, entry_day, entry_at, exit_day, exit_at, net, fees, div, hs,
                reason, held_sessions}]: ids and cell ids, never an aid or a symbol
    picks       [{decided, exec, at, called (1 | 0: a standing-target day), targets [[id, w]], buys [[id, usd]], sells
                [[lid, id, entry_day]], dropped [[id, why]], budget, equity, ctx_sha}]: one a decision that planned a
                program order, plus every called decision
    picks_sha, factors [[day, mkt, mom, strev, beta]] (the House panel factors over the run's days: SPY's return;
                top-minus-bottom third equal-weight returns by 12-1 momentum, by the trailing 5-session return reversed
                and by beta, thirds re-formed at each month's first session: beside, never a bar)
    placebo     `placebo.run`'s block (only when placebos were asked for)
    style       `style.block`'s block (only with style=True: the captain's A22; counts and sums of ranks, no id)
    calls       only with calls=True, never stored: [{t, positions, closed, rejects, cash, equity, budget}] of every
                CALLED decision, no array: with the run's own `PanelBars` they rebuild the exact `Inputs` each call read
    actions     the dividends, splits and vanish events the cash book booked on held lots ({id, day, kind, ...})
    runtime, result_sha, start, end

`vanished` counts a run's vanish events by how the name's spell ended, as far as a run can tell them apart
(`store.PanelBars.exit`: 1 a deal, 0 every other way, an unknown one included): a membership fact counted beside, it
sets no price. `refused` counts the buys entry validity did not open: `no_bar` (no open or close at the fill session),
`ahead` (no valid close the session AFTER the fill: the one place the Gym reads a validity live cannot yet know) and
`last` (a buy due at the slice's last session, which has no session after it).

ONE OBSERVATION A SESSION: no statistic pools name-days. Every sum is taken with `math.fsum` (the CI runs Python 3.11
and 3.14 and the built-in `sum` is not the same sum on both); T is E1's own expression (`league.equity.screen
.holdout_t`: numpy's mean and std, the floor's, the look's and the placebos'). THERE IS NO `seen` FILTER: a version is
RUN once a seen span, each run starting flat, because a filtered whole-span run still carries the hidden year in its
cash and in every later decision.

Evidence module (in the xs identity).
"""

from __future__ import annotations

import bisect
import json
import math
from typing import Any, Mapping, Sequence

import numpy as np

from ..equity import results as _e1
from ..equity.screen import holdout_t as _holdout_t

#: The columns of a `daily` row, in order.
DAILY = ("day", "r", "x", "x15", "u", "w", "bench", "exits", "invested", "equity")
VIEWS = ("train", "validation", "look", "forward")
STATUSES = ("ok", "disqualified", "no_data", "error")
#: What a "train" view carries (never daily, lots, picks' ids, calls, placebo or style); every other view is the status
#: alone.
TRAIN_VIEW = ("status", "summary", "by_year", "pick_counts", "runtime")
#: Sessions a year (the turnover's unit), and the lag of the Newey-West t reported beside the plain one.
YEAR_SESSIONS = 252.0
NW_LAG = 5
#: The sums `pooled` adds across runs (None when a run lacks one), the summary's counts it adds with them, and the
#: counts it adds key by key.
POOLED_SUMS = ("sum_r", "sum_x", "sum_x15", "sum_u", "sum_bench", "sum_w", "pnl", "realized", "fees", "dividends",
               "costs", "gross", "delta", "sum_x_h0", "sum_x_h1")
POOLED_COUNTS = ("days", "invested_days", "rebalances", "calls", "lots", "closed", "round_trips")
POOLED_TALLIES = ("cells", "vanished", "refused")
_ZERO = 1e-12


def canonical(value: Any) -> str:
    """The canonical JSON a sha is taken over (E1's `league.equity.results.canonical`, re-exported)."""
    return _e1.canonical(value)


def sha(value: Any) -> str:
    """sha256 of `canonical(value)`, hex."""
    return _e1.sha(value)


def t_stat(x: Sequence[float]) -> float | None:
    """D15: mean(x) / std(x, ddof=1) x sqrt(len(x)), by exactly `league.equity.screen.holdout_t`'s expression (the
    floor's, the look's and the placebos'); None when the std is below 1e-12 or the result is not finite."""
    return _holdout_t(np.ascontiguousarray(x, dtype=np.float64))


def nw_t(x: Sequence[float], lag: int = NW_LAG) -> float | None:
    """The Newey-West t of the mean of `x` (Bartlett weights, `lag` lags): mean / sqrt(S / n), S = g0 + 2 x the sum over
    l = 1..lag of (1 - l / (lag + 1)) x gl, gl the lag-l autocovariance over n. Beside the plain t, never a bar. None
    under two points, with a value that is not finite, or when S is not above zero."""
    values = [float(v) for v in x]
    n = len(values)
    if n < 2 or not all(math.isfinite(v) for v in values):
        return None
    mean = math.fsum(values) / n
    dev = [v - mean for v in values]
    total = math.fsum(d * d for d in dev) / n
    for step in range(1, min(int(lag), n - 1) + 1):
        cov = math.fsum(dev[i] * dev[i - step] for i in range(step, n)) / n
        total += 2.0 * (1.0 - step / (lag + 1.0)) * cov
    if not total > _ZERO * _ZERO:
        return None
    t = mean / math.sqrt(total / n)
    return t if math.isfinite(t) else None


def column(result: Mapping[str, Any], name: str) -> list[Any]:
    """One column of `result["daily"]` by its `DAILY` name (ValueError for another name)."""
    if name not in DAILY:
        raise ValueError(f"a daily row has {', '.join(DAILY)}, not {name!r}")
    at = DAILY.index(name)
    return [row[at] for row in result.get("daily") or ()]


def _column(daily: Sequence[Sequence[Any]], name: str) -> list[float]:
    at = DAILY.index(name)
    return [float(row[at]) for row in daily]


def _year(day: Any) -> str:
    return str(day)[:4]


def _r(value: float | None, places: int) -> float | None:
    return None if value is None or not math.isfinite(value) else round(value, places)


def close_dates(lots: Sequence[Mapping[str, Any]], capital: Any) -> dict[str, float]:
    """One observation a close DATE (E4-SPEC 10.5): {exit day: that date's summed lot net over their summed entry
    notional}, in date order. A lot's notional is its weight x `capital`; a date whose notional is not above zero is
    left out."""
    capital = float(capital)
    net: dict[str, list[float]] = {}
    notional: dict[str, list[float]] = {}
    for lot in lots:
        day = lot.get("exit_day")
        if day in (None, ""):
            continue
        net.setdefault(str(day), []).append(float(lot.get("net") or 0.0))
        notional.setdefault(str(day), []).append(float(lot.get("weight") or 0.0) * capital)
    out: dict[str, float] = {}
    for day in sorted(net):
        base = math.fsum(notional[day])
        if base > 0:
            out[day] = math.fsum(net[day]) / base
    return out


def _sd(values: Sequence[float]) -> float | None:
    """The sd (ddof 1) of `values`; None under two."""
    n = len(values)
    if n < 2:
        return None
    mean = math.fsum(values) / n
    return math.sqrt(math.fsum((v - mean) ** 2 for v in values) / (n - 1))


def _held(daily: Sequence[Sequence[Any]], lots: Sequence[Mapping[str, Any]]) -> list[int]:
    """The lots held at each session's close (bought on or before it, not yet sold by it)."""
    days = [str(row[0]) for row in daily]
    steps = [0] * (len(days) + 1)
    for lot in lots:
        entry, leave = str(lot.get("entry_day")), lot.get("exit_day")
        first = bisect.bisect_left(days, entry)
        last = len(days) if leave in (None, "") else bisect.bisect_left(days, str(leave))
        if first < last:
            steps[first] += 1
            steps[last] -= 1
    out, now = [], 0
    for step in steps[:-1]:
        now += step
        out.append(now)
    return out


def _shares(costs: Any, gross: Any, delta: Any, sum_w: Any) -> dict[str, float | None]:
    """{cost_share, dilution}: the costs over the gross residual (None unless that is above zero), and the diluted
    exposure over the exposure (None with no exposure)."""
    known = all(v is not None for v in (costs, gross))
    return {"cost_share": _r(float(costs) / float(gross), 6) if known and float(gross) > _ZERO else None,
            "dilution": _r(float(delta) / float(sum_w), 6) if delta is not None and sum_w is not None
            and float(sum_w) > _ZERO else None}


def _turnover(weights: Sequence[float], days: int) -> float | None:
    """The entry notional over E0, a year of `YEAR_SESSIONS` sessions."""
    return _r(math.fsum(weights) / (max(int(days), 1) / YEAR_SESSIONS), 4)


def summarize(daily: Sequence[Sequence[Any]], lots: Sequence[Mapping[str, Any]],
              picks: Sequence[Mapping[str, Any]], capital: Any, *,
              beside: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """The `summary` of the module docstring. `beside`: what the daily rows do not carry and the engine hands over
    ({"costs", "gross", "delta" (the sums of the residual's cost, gross and diluted-exposure series), "cells",
    "vanished", "refused", "sum_x_h0", "sum_x_h1"}); without it those figures are None or empty."""
    capital = float(capital)
    beside = dict(beside or {})
    days = len(daily)
    r, x, x15, u = (_column(daily, name) for name in ("r", "x", "x15", "u"))
    w, bench = _column(daily, "w"), _column(daily, "bench")
    exits = [int(row[DAILY.index("exits")]) for row in daily]
    invested = [bool(row[DAILY.index("invested")]) for row in daily]
    equity = _column(daily, "equity")
    sum_x, sum_bench, sum_w = math.fsum(x), math.fsum(bench), math.fsum(w)
    closed = [lot for lot in lots if lot.get("exit_day") not in (None, "")]
    by_date = close_dates(lots, capital)
    held = _held(daily, lots)
    called = [p for p in picks if p.get("called")]
    costs, gross, delta = beside.get("costs"), beside.get("gross"), beside.get("delta")
    sd_dates = _sd(list(by_date.values()))
    return {
        "days": days, "invested_days": sum(invested), "rebalances": sum(1 for p in called if p.get("targets")),
        "calls": len(called), "lots": len(lots), "closed": len(closed), "round_trips": sum(exits),
        "pnl": round(equity[-1] - capital, 2) if equity else 0.0,
        "realized": round(math.fsum(float(lot.get("net") or 0.0) for lot in closed), 2),
        "fees": round(math.fsum(float(lot.get("fees") or 0.0) for lot in lots), 2),
        "dividends": round(math.fsum(float(lot.get("div") or 0.0) for lot in lots), 2),
        "sum_r": math.fsum(r), "sum_x": sum_x, "sum_x15": math.fsum(x15), "sum_u": math.fsum(u),
        "sum_bench": sum_bench, "sum_w": sum_w, "t_x": t_stat(x) if days >= 2 else None, "t_x_nw5": nw_t(x),
        "t_r": t_stat(r) if days >= 2 else None,
        "basket": "basket-led" if sum_bench >= sum_x else "selection-led",
        "exposure_mean": _r(sum_w / days, 6) if days else None,
        "names_mean": _r(math.fsum(held) / days, 4) if days else None,
        "turnover": _turnover([float(lot.get("weight") or 0.0) for lot in lots], days),
        "costs": None if costs is None else float(costs), "gross": None if gross is None else float(gross),
        "delta": None if delta is None else float(delta), **_shares(costs, gross, delta, sum_w),
        "cells": dict(beside.get("cells") or {}), "vanished": dict(beside.get("vanished") or {}),
        "refused": dict(beside.get("refused") or {}),
        "sum_x_h0": beside.get("sum_x_h0"), "sum_x_h1": beside.get("sum_x_h1"),
        "close_dates": len(by_date), "sd_date_return": sd_dates,
    }


def by_year(daily: Sequence[Sequence[Any]], lots: Sequence[Mapping[str, Any]],
            picks: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """The `by_year` rows of the module docstring: one a calendar year of the run's sessions. `rebalances`: the called
    decisions with a non-empty target that EXECUTE that year; `closed`: the lots fully exited that year."""
    out: dict[str, dict[str, Any]] = {}
    for year in sorted({_year(row[0]) for row in daily}):
        rows = [row for row in daily if _year(row[0]) == year]
        x = _column(rows, "x")
        out[year] = {
            "days": len(rows), "sum_x": math.fsum(x), "sumsq_x": math.fsum(v * v for v in x),
            "sum_x15": math.fsum(_column(rows, "x15")), "sum_r": math.fsum(_column(rows, "r")),
            "rebalances": sum(1 for p in picks if p.get("called") and p.get("targets")
                              and _year(p.get("exec")) == year),
            "closed": sum(1 for lot in lots if lot.get("exit_day") not in (None, "")
                          and _year(lot.get("exit_day")) == year),
        }
    return out


def pick_counts(picks: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    """What of a run's picks a "train" view carries: counts only, never an id ({decisions, called, standing, buys,
    sells, dropped})."""
    return {"decisions": len(picks), "called": sum(1 for p in picks if p.get("called")),
            "standing": sum(1 for p in picks if not p.get("called")),
            "buys": sum(len(p.get("buys") or ()) for p in picks),
            "sells": sum(len(p.get("sells") or ()) for p in picks),
            "dropped": sum(len(p.get("dropped") or ()) for p in picks)}


def failed(program: str, why: str) -> dict[str, Any]:
    """The record of a run the engine could not make: status "error" and its reason, no trial, no figures (E1's
    `results.failed` shape)."""
    return {"program": program, "status": "error", "reason": str(why)[:500], "trials": 0, "summary": {},
            "by_year": {}, "daily": [], "lots": [], "picks": [], "data_version": "",
            "runtime": {"calls": 0, "errors": 0, "timeouts": 0, "messages": [str(why)[:200]], "disqualified": None}}


def view(result: Mapping[str, Any], window: str) -> dict[str, Any]:
    """What leaves the House's own records for `window` (one of `VIEWS`): "train": `TRAIN_VIEW`; "validation", "look",
    "forward": the status only. Never a daily row, a lot, an id, a call or a placebo figure."""
    if window not in VIEWS:
        raise ValueError(f"window is one of {', '.join(VIEWS)}")
    if window != "train":
        return {"status": result.get("status")}
    runtime = dict(result.get("runtime") or {})
    out = {"status": result.get("status"), "summary": dict(result.get("summary") or {}),
           "by_year": {str(year): dict(row) for year, row in (result.get("by_year") or {}).items()},
           "pick_counts": pick_counts(result.get("picks") or ()),
           "runtime": {k: runtime.get(k) for k in ("calls", "errors", "timeouts", "disqualified")}}
    return json.loads(json.dumps(out, default=str))


def pooled(results: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Several runs of one version at one k read as one (the seen spans of the Train bar): the summary's sums and
    counts added (the vanish, cell and refusal counts key by key; the haircut sensitivities too), T (D15) and the
    year rows from the concatenated daily x, the turnover, cost share, dilution and mean exposure over all their
    sessions, `sd_date_return` over all their close dates. -> {"runs", "status" ("ok" only when every run is),
    "summary", "by_year"}. The runs are read in the order given (span order); a year two runs share has its rows
    added. A sum one of the runs does not carry is None."""
    results = list(results)
    daily = [row for result in results for row in result.get("daily") or ()]
    x, r = _column(daily, "x"), _column(daily, "r")
    statuses = [str(result.get("status")) for result in results]
    summaries = [result.get("summary") or {} for result in results]
    summary: dict[str, Any] = {key: sum(int(s.get(key) or 0) for s in summaries) for key in POOLED_COUNTS}
    for key in POOLED_SUMS:
        values = [s.get(key) for s in summaries]
        summary[key] = math.fsum(float(v) for v in values) if values and all(v is not None for v in values) else None
    for key in POOLED_TALLIES:
        tally: dict[str, int] = {}
        for s in summaries:
            for name, count in (s.get(key) or {}).items():
                tally[str(name)] = tally.get(str(name), 0) + int(count)
        summary[key] = tally
    days = len(daily)
    dates: list[float] = []
    for result in results:
        dates.extend(close_dates(result.get("lots") or (), result.get("capital") or 0).values())
    by_days = [(int(s.get("days") or 0), s) for s in summaries]

    def mean_of(key: str) -> float | None:
        parts = [(n, float(s[key])) for n, s in by_days if s.get(key) is not None and n > 0]
        total = sum(n for n, _ in parts)
        return math.fsum(n * v for n, v in parts) / total if total else None

    weights = [float(lot.get("weight") or 0.0) for result in results for lot in result.get("lots") or ()]
    summary.update({
        "t_x": t_stat(x) if days >= 2 else None, "t_x_nw5": nw_t(x), "t_r": t_stat(r) if days >= 2 else None,
        "basket": "basket-led" if (summary["sum_bench"] or 0.0) >= (summary["sum_x"] or 0.0) else "selection-led",
        "exposure_mean": _r(summary["sum_w"] / days, 6) if days and summary["sum_w"] is not None else None,
        "names_mean": _r(mean_of("names_mean"), 4), "turnover": _turnover(weights, days) if days else None,
        **_shares(summary["costs"], summary["gross"], summary["delta"], summary["sum_w"]),
        "close_dates": len(dates), "sd_date_return": _sd(dates),
    })
    years: dict[str, dict[str, Any]] = {}
    for result in results:
        for year, row in (result.get("by_year") or {}).items():
            into = years.setdefault(str(year), {})
            for key, value in row.items():
                if value is None:
                    continue
                if key in ("days", "rebalances", "closed"):
                    into[key] = int(into.get(key, 0)) + int(value)
                else:
                    into[key] = math.fsum([float(into.get(key, 0.0)), float(value)])
    return {"runs": len(results), "status": "ok" if statuses and all(s == "ok" for s in statuses) else
            next((s for s in statuses if s != "ok"), "no_data"),
            "summary": summary, "by_year": {year: years[year] for year in sorted(years)}}


__all__ = ["DAILY", "VIEWS", "STATUSES", "TRAIN_VIEW", "canonical", "sha", "t_stat", "nw_t", "column", "close_dates",
           "summarize", "by_year", "pick_counts", "failed", "view", "pooled"]
