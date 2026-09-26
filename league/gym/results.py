"""What a run returns: the record, the statistics, the breakdowns and the hash.

One result per program per run (one TRIAL: one run of one program version over one window). Keys:

- identity: `run_id` (a hash of the program's code and parameters, the store files read, the engine
  version, the window and the run's settings), `program`, `program_sha`, `run_sha`, `params`,
  `window`, `roots`, `engine`, `data_version`, `fill_model`, `stress`, `capital`, `trials` (1);
- `status`: ok, disqualified (the program erred or timed out too often: `runtime.messages` says
  how), or no_data;
- `summary`: trades, days, days_traded, pnl, pnl_per_max_loss, mean_return_on_max_loss and its
  t statistic, win_rate, profit_factor, sharpe (daily, annualized by sqrt 252) and sharpe_daily,
  max_drawdown (dollars and a fraction of capital), turnover (maximum loss opened a year over
  capital), fees, quarters_positive;
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

`view(result, "validation")` is what a researcher may see of a validation run: no trades, no dates,
no daily series. Standard library only.
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
          seconds: float) -> dict[str, Any]:
    """The result of one program's run (the module docstring)."""
    program = account.program
    trades = sorted(account.trades, key=lambda t: (t["day"], t.get("entry_minute") or 0, t["id"]))
    rv_cuts = _terciles([r.get("rv") for day in regimes.values() for r in day.values()])
    iv_cuts = _terciles([r.get("iv") for day in regimes.values() for r in day.values()])

    def regime(t: dict, name: str) -> float | None:
        return ((regimes.get(t["day"]) or {}).get(t["root"]) or {}).get(name)

    identity = {"program_sha": program.sha, "run_sha": program.run_sha, "params": program.params,
                "roots": list(account.roots), "data_version": data_version, **cfg.identity()}
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
    identity_keys = ("program_sha", "run_sha", "params", "roots", "data_version", "window", "capital", "stress",
                     "max_orders_day", "fill_model", "engine")
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


def view(result: Mapping[str, Any], level: str) -> dict[str, Any]:
    """What a researcher may see of a result: "train" everything; "validation" the statistics and
    breakdowns without trades, dates or the daily series; "gate" the status alone (the gate itself
    answers pass or fail)."""
    if level == "train":
        return dict(result)
    if level == "validation":
        keep = ("run_id", "program", "program_sha", "run_sha", "params", "window", "roots", "engine", "fill_model",
                "stress", "capital", "trials", "status", "needs", "summary", "fills")
        out = {k: result.get(k) for k in keep}
        breakdown = dict(result.get("breakdown") or {})
        quarters = breakdown.pop("quarter", {})
        breakdown["quarter"] = {f"q{i + 1}": v for i, (_, v) in enumerate(sorted(quarters.items()))}
        out["breakdown"] = breakdown
        out["runtime"] = {k: (result.get("runtime") or {}).get(k) for k in ("calls", "errors", "timeouts", "disqualified")}
        return out
    if level == "gate":
        return {"run_id": result.get("run_id"), "status": result.get("status"), "trials": result.get("trials", 1)}
    raise ValueError("level is train, validation or gate")


__all__ = ["build", "merge", "view", "summarize", "sha", "canonical", "ENGINE_VERSION"]
