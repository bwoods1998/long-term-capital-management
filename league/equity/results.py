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
- `result_sha`: a hash of everything above but the timing.

`view(result, window)`: "train" everything; "validation" the identity, status, summary and the by-year rows' counts
only (no trades, no dates, no daily series, no lots); "holdout" and "forward" for the gate and the forward record only
(the summary and the daily series; "forward" also each trade's day and net); "gate" the status alone. The swarm shows a
researcher only a view; the gate and the screen (on the House) read the whole result in-process.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence


def sha(value: Any) -> str:
    """sha256 of the canonical JSON of `value` (sorted keys, no NaN)."""
    raise NotImplementedError("core: league/equity/results.py sha")


def summarize(trades: Sequence[Mapping[str, Any]], daily: Sequence[Sequence[Any]], capital: Any) -> dict[str, Any]:
    """The `summary` block (the module docstring)."""
    raise NotImplementedError("core: league/equity/results.py summarize")


def by_year(trades: Sequence[Mapping[str, Any]], daily: Sequence[Sequence[Any]]) -> dict[str, dict[str, Any]]:
    """The `by_year` block."""
    raise NotImplementedError("core: league/equity/results.py by_year")


def buy_and_hold(daily: Sequence[Sequence[Any]], closes: Mapping[str, Sequence[float]], capital: Any) -> dict[str, Any]:
    """The `bh` block: the program's own symbols' equal-weight basket held at its mean exposure over the run's sessions
    (`closes`: each symbol's as-of closes over those sessions), cost-free."""
    raise NotImplementedError("core: league/equity/results.py buy_and_hold")


def mte(trades: Sequence[Mapping[str, Any]], closes: Mapping[str, Sequence[float]]) -> dict[str, Any]:
    """The `mte` block: each closed lot's net return minus the basket's return over its own holding sessions at the
    same notional."""
    raise NotImplementedError("core: league/equity/results.py mte")


def view(result: Mapping[str, Any], window: str) -> dict[str, Any]:
    """What leaves a run of `window` (the module docstring); ValueError for another window name."""
    raise NotImplementedError("core: league/equity/results.py view")


def failed(program: str, why: str) -> dict[str, Any]:
    """The result of a run that could not finish: status "error", its reason, no trial, no figures (the options
    `results.failed` shape)."""
    raise NotImplementedError("core: league/equity/results.py failed")


__all__ = ["sha", "summarize", "by_year", "buy_and_hold", "mte", "view", "failed"]
