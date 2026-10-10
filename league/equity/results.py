"""What an equity run returns, and what of it leaves each window: the options `league.gym.results` shapes, for lots.

Owner: core. Keys of a result (league/equity/engine.py `run`):

- identity: `run_id` (a hash of the program's code and PARAMS, the store files read, the engine's version and code,
  `config`'s tables, the window and the run's settings), `program`, `program_sha`, `run_sha`, `params`, `window`,
  `symbols`, `engine`, `data_version`, `capital` (Decimal string), `k`, `trials` (1);
- `status`: ok, disqualified (`runtime.disqualified` says why) or no_data;
- `summary`: trades (closed lots), days, days_traded (entry days), pnl (dollars, after fees, dividends included), fees,
  dividends, mean_net_return (per closed lot, on its entry notional), sd_net_return, t_trade, win_rate,
  sharpe_daily, t_daily (the daily P&L's one-sample t), max_drawdown, exposure_mean (mean long value / capital at the
  close), turnover, mte (mean per-trade excess over the time-matched same-exposure buy-and-hold);
- `by_year`: per calendar year: trades, days, days_traded, pnl, t_daily, exposure_mean, bh_pnl;
- `trades`: every closed lot (entry and exit day, at, px, qty, notional, fees, div, net, held_sessions, reason, tag);
- `entry_days`: ISO days with an entry fill;
- `exposure`: {"mean", "by_year"} long value / capital at each close;
- `bh`: THE SAME-EXPOSURE BUY-AND-HOLD beside (never a bar): the equal-weight basket of the program's own symbols held
  at the program's mean exposure over the same sessions, cost-free: {"pnl", "by_year"};
- `mte`: {"mean", "t", "n"} per-trade excess over the time-matched same-exposure buy-and-hold;
- `daily`: [day, pnl, equity, exposure] for every session of the run;
- `lots`: the screen's input (league/equity/engine.py's docstring);
- `runtime`: {calls, errors, timeouts, seconds, messages, disqualified};
- `actions`: the dividends and splits the engine booked on held lots (symbol, day, kind, value);
- `result_sha`: a hash of everything above but the timing (`seconds`, `runtime.decide_seconds` are added after it).

THE SAME-EXPOSURE BUY-AND-HOLD (`bh`, `mte`) reads `closes`: {symbol: the as-of (adjustment=all) closes of the
session before the run's first and then of every run session} (len(daily) + 1 values), and the basket's daily return
is the equal-weight mean of its members' close-to-close returns (a member with no close at t or t-1 is left out that
day). A lot's time-matched window runs from its entry's fill point to its exit's (the open or the close of each day):
the basket's buy-and-hold over it is the mean of its members' as-of price ratios between the two points (`opens`
alongside `closes`, the same layout); without `opens` the window is widened to closes (the close before an open
entry or exit).

`view(result, window)`: "train" everything; "validation" the identity, status, summary and the by-year rows' counts
only (no trades, no dates, no daily series, no lots); "holdout" and "forward" for the gate and the forward record only
(the summary and the daily series; "forward" also each trade's day and net); "gate" the status alone. The swarm shows a
researcher only a view; the gate and the screen (on the House) read the whole result in-process. "look" (the one
sealed look's span, `store.LOOK`) is viewed as "holdout".
"""

from __future__ import annotations

import hashlib
import json
import math
from decimal import Decimal
from typing import Any, Mapping, Sequence

from .. import stats

VIEWS = ("train", "validation", "holdout", "look", "forward", "gate")


def canonical(value: Any) -> str:
    """JSON with sorted keys, floats rounded to 6 places, NaN and infinities as null, Decimals as strings."""
    def fix(v: Any) -> Any:
        if isinstance(v, float):
            return None if not math.isfinite(v) else round(v, 6)
        if isinstance(v, Decimal):
            return str(v)
        if isinstance(v, Mapping):
            return {str(k): fix(x) for k, x in v.items()}
        if isinstance(v, (list, tuple)):
            return [fix(x) for x in v]
        return v
    return json.dumps(fix(value), sort_keys=True, separators=(",", ":"), default=str)


def sha(value: Any) -> str:
    """sha256 of the canonical JSON of `value` (sorted keys, no NaN)."""
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def _t(xs: Sequence[float]) -> tuple[float | None, float | None, float | None]:
    """(mean, one-sample t, sd) of xs; t is None under two points or with no variance."""
    xs = [float(x) for x in xs if x is not None and math.isfinite(float(x))]
    if not xs:
        return None, None, None
    mean = sum(xs) / len(xs)
    if len(xs) < 2:
        return mean, None, None
    sd = math.sqrt(sum((x - mean) ** 2 for x in xs) / (len(xs) - 1))
    return mean, (mean / sd * math.sqrt(len(xs)) if sd > 1e-15 else None), sd


def _r(value: float | None, places: int) -> float | None:
    return None if value is None or not math.isfinite(value) else round(value, places)


def summarize(trades: Sequence[Mapping[str, Any]], daily: Sequence[Sequence[Any]], capital: Any) -> dict[str, Any]:
    """The `summary` block (the module docstring). `trades` are closed lots (each with `net`, `return`, `notional`,
    `fees`, `div`, `entry_day` and, when the engine computed it, `excess`); `daily` the [day, pnl, equity, exposure]
    rows."""
    capital = float(capital)
    pnl_days = [float(d[1]) for d in daily]
    returns = [float(t["return"]) for t in trades if t.get("return") is not None]
    mean_r, t_trade, sd_r = _t(returns)
    mean_d, t_daily, _ = _t(pnl_days)
    sharpe = stats.sharpe(pnl_days) if len(pnl_days) >= 2 else None
    peak, drawdown = capital, 0.0
    for d in daily:
        equity = float(d[2])
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    years = max(len(daily), 1) / 252.0
    notional = sum(float(t["notional"]) for t in trades)
    excess = [float(t["excess"]) for t in trades if t.get("excess") is not None]
    exposure = [float(d[3]) for d in daily]
    n = len(trades)
    return {
        "trades": n, "days": len(daily), "days_traded": len({t["entry_day"] for t in trades}),
        "pnl": round(sum(float(t["net"]) for t in trades), 2), "account_pnl": round(sum(pnl_days), 2),
        "fees": round(sum(float(t["fees"]) for t in trades), 2),
        "dividends": round(sum(float(t["div"]) for t in trades), 2),
        "mean_net_return": _r(mean_r, 6), "sd_net_return": _r(sd_r, 6), "t_trade": _r(t_trade, 4),
        "win_rate": round(sum(float(t["net"]) > 0 for t in trades) / n, 4) if n else None,
        "sharpe_daily": _r(sharpe, 5), "mean_pnl_daily": _r(mean_d, 4), "t_daily": _r(t_daily, 4),
        "max_drawdown": round(drawdown, 2), "max_drawdown_frac": round(drawdown / capital, 5) if capital else None,
        "exposure_mean": round(sum(exposure) / len(exposure), 4) if exposure else None,
        "turnover": round(notional / capital / years, 4) if capital else None,
        "mte": _r(sum(excess) / len(excess), 6) if excess else None,
    }


def _year(day: Any) -> str:
    return str(day)[:4]


def by_year(trades: Sequence[Mapping[str, Any]], daily: Sequence[Sequence[Any]]) -> dict[str, dict[str, Any]]:
    """The `by_year` block: one row per calendar year of the run's sessions (a year without a trade included): trades
    and days_traded (closed lots by their entry year, and the year's entry days), days, pnl (the year's daily P&L,
    marked to market), trade_pnl (the net of the lots entered that year), t_daily, exposure_mean. The engine adds
    `bh_pnl` from the `bh` block."""
    out: dict[str, dict[str, Any]] = {}
    for year in sorted({_year(d[0]) for d in daily}):
        days = [d for d in daily if _year(d[0]) == year]
        mine = [t for t in trades if _year(t["entry_day"]) == year]
        _, t_daily, _ = _t([float(d[1]) for d in days])
        out[year] = {"trades": len(mine), "days": len(days), "days_traded": len({t["entry_day"] for t in mine}),
                     "pnl": round(sum(float(d[1]) for d in days), 2),
                     "trade_pnl": round(sum(float(t["net"]) for t in mine), 2), "t_daily": _r(t_daily, 4),
                     "exposure_mean": round(sum(float(d[3]) for d in days) / len(days), 4)}
    return out


def basket_returns(closes: Mapping[str, Sequence[float]], n: int) -> list[float]:
    """The equal-weight basket's daily close-to-close return for each of `n` run sessions (`closes[sym]` holds n + 1
    closes: the session before the run's first, then each run session's); 0.0 on a day no member has two closes."""
    out = []
    for i in range(n):
        moves = []
        for series in closes.values():
            if len(series) < n + 1:
                raise ValueError("closes hold the session before the run and every run session")
            a, b = float(series[i]), float(series[i + 1])
            if math.isfinite(a) and math.isfinite(b) and a > 0 and b > 0:
                moves.append(b / a - 1.0)
        out.append(sum(moves) / len(moves) if moves else 0.0)
    return out


def buy_and_hold(daily: Sequence[Sequence[Any]], closes: Mapping[str, Sequence[float]], capital: Any) -> dict[str, Any]:
    """The `bh` block: the program's own symbols' equal-weight basket held at its mean exposure over the run's sessions
    (`closes`: each symbol's as-of closes over those sessions), cost-free."""
    capital = float(capital)
    exposure = sum(float(d[3]) for d in daily) / len(daily) if daily else 0.0
    moves = basket_returns(closes, len(daily))
    pnl = [capital * exposure * m for m in moves]
    years: dict[str, float] = {}
    for d, x in zip(daily, pnl):
        years[_year(d[0])] = years.get(_year(d[0]), 0.0) + x
    growth = 1.0
    for m in moves:
        growth *= 1.0 + m
    return {"pnl": round(sum(pnl), 2), "by_year": {y: round(v, 2) for y, v in sorted(years.items())},
            "exposure": round(exposure, 4), "basket_return": round(growth - 1.0, 6)}


def _point(series: Mapping[str, Sequence[float]], i: int, sym: str) -> float | None:
    value = float(series[sym][i])
    return value if math.isfinite(value) and value > 0 else None


def excess_returns(trades: Sequence[Mapping[str, Any]], closes: Mapping[str, Sequence[float]],
                   days: Sequence[str], opens: Mapping[str, Sequence[float]] | None = None) -> list[float | None]:
    """Each closed lot's net return minus the basket's buy-and-hold over its own time-matched window (the module
    docstring); None for a lot whose window is not inside the run or that no member prices (`days`: the closes' days,
    the session before the run first)."""
    index = {str(d): i for i, d in enumerate(days)}
    out: list[float | None] = []
    for t in trades:
        a = index.get(str(t.get("entry_day")))
        b = index.get(str(t.get("exit_day")))
        if a is None or b is None or t.get("return") is None:
            out.append(None)
            continue
        legs = []
        for sym in closes:
            if opens is not None:
                start = _point(opens if t.get("entry_at") == "open" else closes, a, sym)
                end = _point(opens if t.get("exit_at") == "open" else closes, b, sym)
            else:
                start = _point(closes, a - (1 if t.get("entry_at") == "open" else 0), sym)
                end = _point(closes, b - (1 if t.get("exit_at") == "open" else 0), sym)
            if start is not None and end is not None:
                legs.append(end / start - 1.0)
        out.append(float(t["return"]) - sum(legs) / len(legs) if legs else None)
    return out


def mte(trades: Sequence[Mapping[str, Any]], closes: Mapping[str, Sequence[float]], *, days: Sequence[str] = (),
        opens: Mapping[str, Sequence[float]] | None = None) -> dict[str, Any]:
    """The `mte` block: each closed lot's net return minus the basket's return over its own holding window at the
    same notional ({"mean", "t", "n"}; `days` and `opens` as `excess_returns`)."""
    values = [x for x in excess_returns(trades, closes, days, opens) if x is not None] if days else []
    mean, t, _ = _t(values)
    return {"mean": _r(mean, 6), "t": _r(t, 4), "n": len(values)}


_IDENTITY = ("run_id", "program", "program_sha", "run_sha", "params", "window", "symbols", "engine", "code", "tables",
             "capital", "k", "trials", "status", "reason", "needs")


def view(result: Mapping[str, Any], window: str) -> dict[str, Any]:
    """What leaves a run of `window` (the module docstring); ValueError for another window name."""
    if window not in VIEWS:
        raise ValueError(f"window is one of {', '.join(VIEWS)}")
    if window == "train":
        return json.loads(json.dumps(result, default=str))
    if window == "gate":
        return {"run_id": result.get("run_id"), "status": result.get("status"), "trials": result.get("trials", 1)}
    out = {k: result.get(k) for k in _IDENTITY if k in result}
    out["summary"] = dict(result.get("summary") or {})
    out["mte"] = dict(result.get("mte") or {})
    out["bh"] = {"pnl": (result.get("bh") or {}).get("pnl"), "exposure": (result.get("bh") or {}).get("exposure")}
    runtime = dict(result.get("runtime") or {})
    if window == "validation":
        out["by_year"] = {f"y{i + 1}": {k: row.get(k) for k in ("trades", "days", "days_traded")}
                          for i, (_, row) in enumerate(sorted((result.get("by_year") or {}).items()))}
        out["runtime"] = {k: runtime.get(k) for k in ("calls", "errors", "timeouts", "disqualified")}
        return out
    out["daily"] = [list(d) for d in result.get("daily") or []]
    out["runtime"] = runtime
    if window == "forward":
        out["trades"] = [{"day": t.get("exit_day"), "net": t.get("net"), "notional": t.get("notional")}
                         for t in result.get("trades") or []]
    return out


def failed(program: str, why: str) -> dict[str, Any]:
    """The result of a run that could not finish: status "error", its reason, no trial, no figures (the options
    `results.failed` shape)."""
    return {"program": program, "status": "error", "reason": str(why)[:500], "trials": 0, "summary": {}, "daily": [],
            "trades": [], "lots": [], "entry_days": [], "data_version": "",
            "runtime": {"calls": 0, "errors": 0, "timeouts": 0, "messages": [str(why)[:200]], "disqualified": None}}


__all__ = ["VIEWS", "canonical", "sha", "summarize", "by_year", "basket_returns", "buy_and_hold", "excess_returns",
           "mte", "view", "failed"]
