"""What a researcher sees of a run.

- TRAIN (`train_view`): a compact table of the Gym's result, trimmed to what helps a revision: the
  summary (trades, P&L per dollar of maximum loss, its t, Sharpe, drawdown, fees, quarters positive),
  the fills (rate, slippage, rejects and why), the breakdowns (weekday, time of day, DTE, realized and
  implied vol tercile, quarter, type, root, exit reason) as rows of [n, pnl, win rate, pnl per $ of max
  loss], the five worst trades with their context, and the program's errors. Train is the window the
  agents see in full; `read_run` pages through the rest (`section`).
- VALIDATION (`validation_view`): only the mean return on maximum loss, its t, the quarters positive,
  and whether the line was met (with the names of the checks that were not). Never trades, days or a
  daily series.
- HOLDOUT: pass or fail, from the gate; never here.

Standard library only.
"""

from __future__ import annotations

import json
import math
from typing import Any, Mapping

SUMMARY_KEYS = ("trades", "days", "days_traded", "pnl", "pnl_per_max_loss", "mean_return_on_max_loss", "t_stat", "win_rate",
                "profit_factor", "sharpe", "max_drawdown", "max_drawdown_frac", "fees", "quarters_positive", "avg_trade",
                "turnover", "max_loss_opened")
FILL_KEYS = ("orders", "opens", "closes", "filled", "partial", "cancelled", "expired", "rejected", "liquidated", "settled",
             "exercised", "fill_rate", "at_natural", "open_slip_half_spreads", "close_slip_half_spreads")
BREAKDOWNS = ("weekday", "time_of_day", "dte", "rv_tercile", "iv_tercile", "quarter", "type", "root", "exit_reason")
TRADE_KEYS = ("day", "root", "type", "legs", "entry_minute", "filled_minute", "exit_minute", "sessions_held", "exit_reason", "qty",
              "entry", "exit", "pnl", "max_loss", "fees", "return_on_max_loss", "tag", "note", "context")
MAX_CHARS = 9000


def _r(value: Any, places: int = 4) -> Any:
    if isinstance(value, float):
        return round(value, places) if math.isfinite(value) else None
    return value


def _rows(table: Mapping[str, Any] | None) -> dict[str, list]:
    out = {}
    for key, row in (table or {}).items():
        if isinstance(row, Mapping):
            out[str(key)] = [row.get("n"), _r(row.get("pnl"), 2), _r(row.get("win_rate"), 3), _r(row.get("pnl_per_max_loss"), 4)]
    return out


def _trade(t: Mapping[str, Any]) -> dict[str, Any]:
    out = {k: _r(t.get(k)) for k in TRADE_KEYS if t.get(k) is not None and k not in ("legs", "context")}
    if isinstance(t.get("legs"), list):
        out["legs"] = [f"{l.get('side')} {l.get('ratio', 1)}x {l.get('right')} dte{l.get('dte')} k{l.get('strike')}"
                       for l in t["legs"] if isinstance(l, Mapping)][:4]
    ctx = t.get("context")
    if isinstance(ctx, Mapping):
        out["context"] = {k: _r(v) for k, v in list(ctx.items())[:12] if not isinstance(v, (list, dict))}
    return out


def train_view(result: Mapping[str, Any], *, lineage_trials: int | None = None) -> dict[str, Any]:
    """The compact diagnostic of a train run (see the module docstring)."""
    if result.get("status") == "refused":
        return {"run_id": result.get("run_id"), "status": "refused", "reason": str(result.get("reason") or "")[:600],
                "hint": "the program was refused before it ran: fix the rule named (league/CONTRACT.md) and run again"}
    s = result.get("summary") or {}
    f = result.get("fills") or {}
    rt = result.get("runtime") or {}
    view: dict[str, Any] = {
        "run_id": result.get("run_id"), "status": result.get("status"), "window": result.get("window"),
        "roots": result.get("roots"), "stress": result.get("stress"), "params": result.get("params"),
        "summary": {k: _r(s.get(k)) for k in SUMMARY_KEYS if k in s},
        "fills": {k: _r(f.get(k)) for k in FILL_KEYS if k in f},
        "rejects": dict(sorted((f.get("reject_reasons") or {}).items(), key=lambda kv: -kv[1])[:6]),
        "by": {name: _rows((result.get("breakdown") or {}).get(name)) for name in BREAKDOWNS
               if (result.get("breakdown") or {}).get(name)},
        "by_columns": ["n", "pnl", "win_rate", "pnl_per_max_loss"],
        "worst": [_trade(t) for t in (result.get("worst") or [])[:5]],
        "runtime": {"calls": rt.get("calls"), "errors": rt.get("errors"), "timeouts": rt.get("timeouts"),
                    "disqualified": rt.get("disqualified"), "messages": list(rt.get("messages") or [])[:4]},
    }
    if lineage_trials is not None:
        view["lineage_trials"] = int(lineage_trials)
    text = json.dumps(view, default=str)
    if len(text) > MAX_CHARS:  # the long tables go first; read_run has them
        for name in ("rv_tercile", "iv_tercile", "quarter", "weekday"):
            view["by"].pop(name, None)
            if len(json.dumps(view, default=str)) <= MAX_CHARS:
                break
    return view


def section(result: Mapping[str, Any], name: str, *, page: int = 0, per_page: int = 25) -> dict[str, Any]:
    """One section of a past train run for `read_run`: summary, fills, runtime, worst, trades (paged),
    or breakdown.<name>."""
    name = str(name or "summary")
    if name == "trades":
        trades = result.get("trades") or []
        start = max(0, int(page)) * per_page
        return {"trades": [_trade(t) for t in trades[start:start + per_page]], "page": int(page), "per_page": per_page,
                "total": len(trades)}
    if name.startswith("breakdown"):
        key = name.split(".", 1)[1] if "." in name else ""
        table = (result.get("breakdown") or {}).get(key)
        if table is None:
            return {"error": f"breakdown sections: {', '.join('breakdown.' + b for b in BREAKDOWNS)}"}
        return {name: _rows(table), "columns": ["n", "pnl", "win_rate", "pnl_per_max_loss"]}
    if name in ("summary", "fills", "runtime"):
        return {name: result.get(name)}
    if name == "worst":
        return {"worst": [_trade(t) for t in (result.get("worst") or [])]}
    if name == "daily":
        return {"daily": [[d[0], _r(d[1], 2)] for d in (result.get("daily") or [])][-120:]}
    return {"error": "sections: summary, fills, runtime, worst, trades (with page), daily, breakdown.<weekday|time_of_day|dte|"
                     "rv_tercile|iv_tercile|quarter|type|root|exit_reason>"}


def validation_view(result: Mapping[str, Any], line: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """What a researcher may know of a validation run: mean, t, quarters positive, the line met or not."""
    s = result.get("summary") or {}
    mean = s.get("mean_return_on_max_loss_daily", s.get("mean_return_on_max_loss"))
    out = {"mean_return_on_max_loss": _r(mean), "t": _r(s.get("t_daily"), 3), "quarters_positive": s.get("quarters_positive")}
    if line is not None:
        out["line_met"] = bool(line.get("passed"))
        out["checks_not_met"] = sorted(k for k, ok in (line.get("checks") or {}).items() if not ok)
    return out


__all__ = ["train_view", "section", "validation_view"]
