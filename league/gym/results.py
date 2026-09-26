"""What a run returns: the record, the statistics, the breakdowns and the hash.

One result per program per run (one TRIAL: one run of one program version over one window). Keys:

- identity: `run_id` (a hash of the program's code and parameters, the store files read and the
  calendar, the engine's code (`code`), its event, rate, fee and tick tables (`tables`), the window
  and the run's settings), `program`, `program_sha`, `run_sha`, `params`, `window`, `roots`,
  `engine`, `data_version`, `fill_model`, `stress`, `capital`, `trials` (1);
- `status`: ok, disqualified (the program erred or timed out too often: `runtime.messages` says
  how), or no_data;
- `summary`: trades, days, days_traded, pnl, pnl_per_max_loss; `t_daily` and
  `mean_return_on_max_loss_daily`, the one-sample t and mean of the DAILY return on maximum loss
  (each entry day's P&L over its maximum loss: THE statistic of the validation line, so splitting a
  position into lots cannot raise it); `t_stat` and `mean_return_on_max_loss` per trade (for
  diagnosis only); win_rate, profit_factor, sharpe (daily P&L, annualized by sqrt 252), sharpe_daily,
  skew_daily and kurt_daily (the deflated Sharpe's inputs), max_drawdown (dollars and a fraction of
  capital), turnover (maximum loss opened a year over capital), fees, quarters_positive,
  median_max_loss_per_structure (one structure's maximum loss, USD: for sizing);
- `fills`: orders, opens, closes, filled, partial, cancelled, expired, rejected with their reasons,
  liquidated, settled, exercised, fill_rate, the share of fills at the natural, the mean slippage
  from the mid a share and in half-spreads;
- `breakdown`: n, pnl, win_rate and pnl_per_max_loss by weekday, time_of_day, dte, rv and iv terciles
  (the day's realized and implied vol, cut within the run), quarter, type, root and exit_reason;
- `daily`: [day, P&L, equity] for every trading day of the run (zero days included);
- `trades`: every trade (entry, exit, legs, fees, maximum loss, P&L, the context at entry);
- `worst`: the five worst trades with their context;
- `runtime`: the program's calls, errors, timeouts, seconds and first error messages;
- `result_sha`: a hash of everything above but the timing, so two runs of the same inputs agree.

`view(result, window)` is what leaves a run of each window (validation: no trades, no dates, no daily
series; holdout and forward: the gate's inputs only). Standard library only.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
from typing import Any, Iterable, Mapping, Sequence

from .. import stats
from . import ENGINE_VERSION

WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def canonical(value: Any) -> str:
    def fix(v: Any) -> Any:
        if isinstance(v, float):
            return None if not math.isfinite(v) else round(v, 6)
        if isinstance(v, Mapping):
            return {str(k): fix(x) for k, x in v.items()}
        if isinstance(v, (list, tuple)):
            return [fix(x) for x in v]
        return v
    return json.dumps(fix(value), sort_keys=True, separators=(",", ":"), default=str)


def sha(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def _group(trades: Iterable[dict], key: Any) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[dict]] = {}
    for t in trades:
        groups.setdefault(str(key(t)), []).append(t)
    out = {}
    for name in sorted(groups):
        rows = groups[name]
        pnl = sum(t["pnl"] for t in rows)
        risk = sum(t["max_loss"] for t in rows)
        out[name] = {"n": len(rows), "pnl": round(pnl, 2), "win_rate": round(sum(t["pnl"] > 0 for t in rows) / len(rows), 4),
                     "pnl_per_max_loss": round(pnl / risk, 4) if risk > 0 else None}
    return out


def _tod(minute: Any) -> str:
    if not isinstance(minute, int):
        return "unknown"
    if minute < 600:
        return "09:30-10:00"
    hour = minute // 60
    return f"{hour:02d}:00-{hour + 1:02d}:00"


def _dte(t: dict) -> str:
    d = (t.get("context") or {}).get("dte")
    if d is None:
        return "unknown"
    return "0" if d == 0 else "1" if d == 1 else "2" if d == 2 else "3-5" if d <= 5 else "6-14" if d <= 14 else "15+"


def _quarter(day: str) -> str:
    d = dt.date.fromisoformat(day)
    return f"{d.year}Q{(d.month - 1) // 3 + 1}"


def _terciles(values: Sequence[float]) -> tuple[float, float] | None:
    xs = sorted(v for v in values if isinstance(v, float) and math.isfinite(v))
    if len(xs) < 3:
        return None
    return xs[len(xs) // 3], xs[(2 * len(xs)) // 3]


def _tercile(value: float | None, cuts: tuple[float, float] | None) -> str:
    if cuts is None or value is None or not math.isfinite(value):
        return "unknown"
    return "low" if value < cuts[0] else "mid" if value < cuts[1] else "high"


def _t(xs: Sequence[float]) -> tuple[float | None, float | None]:
    """(mean, one-sample t) of xs; t is None under two points or with no variance."""
    if not xs:
        return None, None
    mean = sum(xs) / len(xs)
    if len(xs) < 2:
        return mean, None
    sd = math.sqrt(sum((x - mean) ** 2 for x in xs) / (len(xs) - 1))
    return mean, (mean / sd * math.sqrt(len(xs)) if sd > 0 else None)


def daily_returns(trades: Sequence[dict]) -> list[float]:
    """One return a trading day with entries: that day's P&L over that day's maximum loss (trades
    grouped by entry day). The evidence lines are tested on these, not on trades: five trades on one
    day are one day's evidence, and splitting a position into lots must not raise its t."""
    pnl: dict[str, float] = {}
    risk: dict[str, float] = {}
    for t in trades:
        pnl[t["day"]] = pnl.get(t["day"], 0.0) + float(t["pnl"])
        risk[t["day"]] = risk.get(t["day"], 0.0) + float(t["max_loss"])
    return [pnl[d] / risk[d] for d in sorted(pnl) if risk[d] > 0]


def summarize(trades: Sequence[dict], daily: Sequence[Sequence[Any]], capital: float) -> dict[str, Any]:
    """The run's statistics (the module docstring lists them)."""
    pnl_days = [float(d[1]) for d in daily]
    n = len(trades)
    total = sum(t["pnl"] for t in trades)
    risk = sum(t["max_loss"] for t in trades)
    roms = [t["return_on_max_loss"] for t in trades if t.get("return_on_max_loss") is not None]
    wins = sum(t["pnl"] for t in trades if t["pnl"] > 0)
    losses = -sum(t["pnl"] for t in trades if t["pnl"] < 0)
    mean_rom = sum(roms) / len(roms) if roms else None
    t_stat = None
    if len(roms) >= 2:
        sd = math.sqrt(sum((r - mean_rom) ** 2 for r in roms) / (len(roms) - 1))
        t_stat = mean_rom / sd * math.sqrt(len(roms)) if sd > 0 else None
    daily_sharpe = stats.sharpe(pnl_days) if len(pnl_days) >= 2 else None
    by_day = daily_returns(trades)
    mean_daily, t_daily = _t(by_day)
    per_structure = sorted(t["max_loss"] / max(1, int(t.get("qty") or 1)) for t in trades)
    median_structure = None
    if per_structure:
        k = len(per_structure)
        median_structure = per_structure[k // 2] if k % 2 else 0.5 * (per_structure[k // 2 - 1] + per_structure[k // 2])
    skew = stats.skewness(pnl_days)
    kurt = stats.kurtosis(pnl_days)
    curve, peak, drawdown = 0.0, 0.0, 0.0
    for x in pnl_days:
        curve += x
        peak = max(peak, curve)
        drawdown = max(drawdown, peak - curve)
    years = max(len(pnl_days), 1) / 252.0
    quarters: dict[str, float] = {}
    for d in daily:
        quarters[_quarter(d[0])] = quarters.get(_quarter(d[0]), 0.0) + float(d[1])
    return {
        "trades": n, "days": len(pnl_days), "days_traded": len({t["day"] for t in trades}),
        "pnl": round(total, 2), "account_pnl": round(sum(pnl_days), 2),
        "pnl_per_max_loss": round(total / risk, 5) if risk > 0 else None,
        "mean_return_on_max_loss": None if mean_rom is None else round(mean_rom, 5),
        "t_stat": None if t_stat is None else round(t_stat, 4),
        "mean_return_on_max_loss_daily": None if mean_daily is None else round(mean_daily, 6),
        "t_daily": None if t_daily is None else round(t_daily, 4),
        "skew_daily": None if skew is None else round(skew, 5),
        "kurt_daily": None if kurt is None else round(kurt, 5),
        "median_max_loss_per_structure": None if median_structure is None else round(median_structure, 2),
        "win_rate": round(sum(t["pnl"] > 0 for t in trades) / n, 4) if n else None,
        "profit_factor": round(wins / losses, 4) if losses > 0 else (None if wins == 0 else float("inf")),
        "sharpe_daily": None if daily_sharpe is None else round(daily_sharpe, 5),
        "sharpe": None if daily_sharpe is None else round(daily_sharpe * math.sqrt(252.0), 4),
        "max_drawdown": round(drawdown, 2), "max_drawdown_frac": round(drawdown / capital, 5) if capital else None,
        "max_loss_opened": round(risk, 2), "turnover": round(risk / capital / years, 4) if capital else None,
        "fees": round(sum(t["fees"] for t in trades), 2),
        "quarters_positive": f"{sum(v > 0 for v in quarters.values())}/{len(quarters)}",
        "avg_trade": round(total / n, 2) if n else None,
    }


def fill_stats(account: Any) -> dict[str, Any]:
    counts = dict(account.counts)
    rows = account.fill_rows
    sent = counts["opens"] + counts["closes"]
    out = {**counts, "reject_reasons": dict(sorted(account.reject_reasons.items())),
           "fill_rate": round(counts["filled"] / sent, 4) if sent else None,
           "at_natural": round(sum(r[3] for r in rows) / len(rows), 4) if rows else None}
    for action in ("open", "close"):
        mine = [r for r in rows if r[0] == action]
        out[f"{action}_slip_share"] = round(sum(r[1] for r in mine) / len(mine), 5) if mine else None
        out[f"{action}_slip_half_spreads"] = round(sum(r[2] for r in mine) / len(mine), 4) if mine else None
    return out


def build(account: Any, cfg: Any, days: Sequence[dt.date], data_version: str, regimes: Mapping[str, Mapping[str, Mapping[str, float]]],
          seconds: float, *, code: str = "", tables: str = "") -> dict[str, Any]:
    """The result of one program's run (the module docstring)."""
    program = account.program
    trades = sorted(account.trades, key=lambda t: (t["day"], t.get("entry_minute") or 0, t["id"]))
    rv_cuts = _terciles([r.get("rv") for day in regimes.values() for r in day.values()])
    iv_cuts = _terciles([r.get("iv") for day in regimes.values() for r in day.values()])

    def regime(t: dict, name: str) -> float | None:
        return ((regimes.get(t["day"]) or {}).get(t["root"]) or {}).get(name)

    identity = {"program_sha": program.sha, "run_sha": program.run_sha, "params": program.params,
                "roots": list(account.roots), "data_version": data_version, "code": code, "tables": tables, **cfg.identity()}
    status = "ok"
    if account.runner.disqualified:
        status = "disqualified"
    elif not days or not account.roots:
        status = "no_data"
    result = {
        "run_id": sha(identity)[:24], "program": program.name, **identity, "trials": 1, "status": status,
        "needs": program.needs.as_dict(),
        "summary": summarize(trades, account.daily, cfg.capital),
        "fills": fill_stats(account),
        "breakdown": {
            "weekday": _group(trades, lambda t: WEEKDAYS[dt.date.fromisoformat(t["day"]).weekday()]),
            "time_of_day": _group(trades, lambda t: _tod(t.get("entry_minute"))),
            "dte": _group(trades, _dte),
            "rv_tercile": _group(trades, lambda t: _tercile(regime(t, "rv"), rv_cuts)),
            "iv_tercile": _group(trades, lambda t: _tercile(regime(t, "iv"), iv_cuts)),
            "quarter": _group(trades, lambda t: _quarter(t["day"])),
            "type": _group(trades, lambda t: t["type"]),
            "root": _group(trades, lambda t: t["root"]),
            "exit_reason": _group(trades, lambda t: t["exit_reason"]),
        },
        "daily": [list(d) for d in account.daily],
        "trades": trades,
        "worst": sorted(trades, key=lambda t: t["pnl"])[:5],
        "runtime": {k: v for k, v in account.runner.stats().items() if k != "seconds"},
    }
    result["result_sha"] = sha(result)
    result["seconds"] = round(seconds, 3)
    result["runtime"]["decide_seconds"] = account.runner.stats()["seconds"]
    return result


def merge(parts: Sequence[dict]) -> dict[str, Any]:
    """One result from a program's consecutive segments of one window (the inner loop's split run):
    trades and days concatenated, statistics recomputed, one trial."""
    if len(parts) == 1:
        return parts[0]
    first = parts[0]
    trades = [t for p in parts for t in p["trades"]]
    daily = [d for p in parts for d in p["daily"]]
    fills: dict[str, Any] = {}
    for p in parts:
        for k, v in p["fills"].items():
            if isinstance(v, (int, float)) and not isinstance(v, bool) and k in ("orders", "opens", "closes", "filled", "partial_fills",
                                                                                   "cancelled", "expired", "rejected", "liquidated",
                                                                                   "settled", "exercised", "fills"):
                fills[k] = fills.get(k, 0) + v
    reasons: dict[str, int] = {}
    for p in parts:
        for k, v in p["fills"].get("reject_reasons", {}).items():
            reasons[k] = reasons.get(k, 0) + v
    fills["reject_reasons"] = dict(sorted(reasons.items()))
    sent = fills.get("opens", 0) + fills.get("closes", 0)
    fills["fill_rate"] = round(fills.get("filled", 0) / sent, 4) if sent else None
    identity_keys = ("program_sha", "run_sha", "params", "roots", "data_version", "code", "tables", "window", "capital",
                     "stress", "max_orders_day", "fill_model", "engine")
    identity = {k: first.get(k) for k in identity_keys}
    identity["data_version"] = sha([p["data_version"] for p in parts])[:24]
    identity["segments"] = [[p.get("start"), p.get("end")] for p in parts]
    status = "disqualified" if any(p["status"] == "disqualified" for p in parts) else \
        "ok" if any(p["status"] == "ok" for p in parts) else "no_data"
    breakdown = {}
    for name, key in (("weekday", lambda t: WEEKDAYS[dt.date.fromisoformat(t["day"]).weekday()]),
                      ("time_of_day", lambda t: _tod(t.get("entry_minute"))), ("dte", _dte),
                      ("quarter", lambda t: _quarter(t["day"])), ("type", lambda t: t["type"]), ("root", lambda t: t["root"]),
                      ("exit_reason", lambda t: t["exit_reason"])):
        breakdown[name] = _group(trades, key)
    result = {"run_id": sha(identity)[:24], "program": first["program"], **identity, "start": parts[0].get("start"),
              "end": parts[-1].get("end"), "trials": 1, "status": status, "needs": first["needs"],
              "summary": summarize(trades, daily, first["capital"]), "fills": fills, "breakdown": breakdown,
              "daily": daily, "trades": trades, "worst": sorted(trades, key=lambda t: t["pnl"])[:5],
              "runtime": {"calls": sum(p["runtime"]["calls"] for p in parts), "errors": sum(p["runtime"]["errors"] for p in parts),
                          "timeouts": sum(p["runtime"]["timeouts"] for p in parts),
                          "messages": [m for p in parts for m in p["runtime"]["messages"]][:10],
                          "disqualified": next((p["runtime"]["disqualified"] for p in parts if p["runtime"]["disqualified"]), None)}}
    result["result_sha"] = sha(result)
    result["seconds"] = round(sum(p.get("seconds", 0.0) for p in parts), 3)
    return result


STRESS_KEYS = ("trades", "days_traded", "pnl", "pnl_per_max_loss", "mean_return_on_max_loss_daily", "t_daily", "sharpe_daily")
_HIDDEN_FROM_VALIDATION = ("trades", "daily", "worst", "start", "end", "segments", "seconds")


def view(result: Mapping[str, Any], window: str) -> dict[str, Any]:
    """What leaves a run of `window`, the one place these rules live:

    - "train": everything (a researcher sees all of Train);
    - "validation": the statistics a line needs and the breakdowns, with NO trades, NO dates and NO
      daily series (quarters become q1..q4): summary (sharpe_daily, days, skew_daily, kurt_daily,
      t_daily, days_traded, trades, quarters_positive, median_max_loss_per_structure, ...), fills,
      runtime counts, and `stress_1.5` when the batch ran the stress twin;
    - "holdout": for the gate only (a researcher hears pass or fail): the summary and the daily P&L
      series (the day-block bootstrap), no trades;
    - "forward": for the gate and the forward record only: the summary, the daily series and each
      trade's day, P&L and maximum loss;
    - "gate": the status alone."""
    if window == "train":
        return dict(result)
    keep_always = ("run_id", "program", "program_sha", "run_sha", "params", "window", "roots", "engine", "code", "tables",
                   "fill_model", "stress", "capital", "trials", "status", "reason", "needs", "summary", "fills")
    if window == "validation":
        out = {k: result.get(k) for k in keep_always if k in result}
        breakdown = dict(result.get("breakdown") or {})
        quarters = breakdown.pop("quarter", {})
        breakdown["quarter"] = {f"q{i + 1}": v for i, (_, v) in enumerate(sorted(quarters.items()))}
        out["breakdown"] = breakdown
        out["runtime"] = {k: (result.get("runtime") or {}).get(k) for k in ("calls", "errors", "timeouts", "disqualified")}
        if "stress_1.5" in result:
            out["stress_1.5"] = dict(result["stress_1.5"])
        for hidden in _HIDDEN_FROM_VALIDATION:
            out.pop(hidden, None)
        return out
    if window == "holdout":
        out = {k: result.get(k) for k in keep_always if k in result}
        out["daily"] = [list(d) for d in result.get("daily") or []]
        out["runtime"] = dict(result.get("runtime") or {})
        if "stress_1.5" in result:
            out["stress_1.5"] = dict(result["stress_1.5"])
        return out
    if window == "forward":
        out = view(result, "holdout")
        out["trades"] = [{"day": t.get("day"), "pnl": t.get("pnl"), "max_loss": t.get("max_loss")} for t in result.get("trades") or []]
        return out
    if window == "gate":
        return {"run_id": result.get("run_id"), "status": result.get("status"), "trials": result.get("trials", 1)}
    raise ValueError("window is train, validation, holdout, forward or gate")


def stress_block(result: Mapping[str, Any]) -> dict[str, Any]:
    """The stress twin's figures a validation view carries (`stress_1.5`)."""
    summary = result.get("summary") or {}
    return {"stress": result.get("stress"), "status": result.get("status"), **{k: summary.get(k) for k in STRESS_KEYS}}


__all__ = ["build", "merge", "view", "stress_block", "summarize", "daily_returns", "sha", "canonical", "ENGINE_VERSION"]
