"""What a panel run returns, and what of it leaves each window.

Owner: package D. STEP 0 STUB: the constants are the contract; every function raises NotImplementedError until D lands.

THE RESULT RECORD (a plain dict; in-House only: `view` decides what a researcher sees):

    run_id, program, program_sha, run_sha, params, window, panel, half (None | 0 | 1), engine (`XS_ENGINE_VERSION`),
    data_version, capital, k, rung, trials (1), status ("ok" | "disqualified" | "no_data"; "error" from `failed`), needs
    summary     {days, invested_days, rebalances (called decisions with a non-empty target), calls, lots, closed,
                round_trips, pnl, fees, dividends (cash-book dollars), sum_r, sum_x, sum_x15, sum_u, sum_bench, t_x,
                t_x_nw5 (Newey-West, lag 5), t_r, basket ("basket-led" when sum bench >= sum x, else "selection-led"),
                exposure_mean, names_mean, turnover, cost_share, dilution, cells {small, under5},
                vanished {deal, other, unknown}, sum_x_h0, sum_x_h1 (sum x at haircut 0 and 1),
                close_dates, sd_date_return (over the run's close dates, the sd, ddof 1, of that date's summed lot net
                over their summed entry notional; None under 2 dates)}
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
    calls       only with calls=True, never stored: [{t, positions, closed, rejects, cash, equity, budget}] of every
                CALLED decision, no array: with the run's own `PanelBars` they rebuild the exact `Inputs` each call read
    runtime, result_sha, start, end

ONE OBSERVATION A SESSION: no statistic pools name-days. Every sum and every t is taken with `math.fsum` (the CI runs
Python 3.11 and 3.14 and the built-in `sum` is not the same sum on both). THERE IS NO `seen` FILTER: a version is RUN
once a seen span, each run starting flat, because a filtered whole-span run still carries the hidden year in its cash
and in every later decision.

Evidence module (in the xs identity).
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

#: The columns of a `daily` row, in order.
DAILY = ("day", "r", "x", "x15", "u", "w", "bench", "exits", "invested", "equity")
VIEWS = ("train", "validation", "look", "forward")
STATUSES = ("ok", "disqualified", "no_data", "error")
#: What a "train" view carries (never daily, lots, picks' ids, calls or placebo); every other view is the status alone.
TRAIN_VIEW = ("status", "summary", "by_year", "pick_counts", "runtime")

_STUB = "league.xs.results is a Step 0 stub: package D builds it (league/xs/E4_INTERFACES.md)"


def canonical(value: Any) -> str:
    """The canonical JSON a sha is taken over (E1's `league.equity.results.canonical`, re-exported)."""
    raise NotImplementedError(_STUB)


def sha(value: Any) -> str:
    """sha256 of `canonical(value)`, hex."""
    raise NotImplementedError(_STUB)


def t_stat(x: Sequence[float]) -> float | None:
    """D15: mean(x) / std(x, ddof=1) x sqrt(len(x)), by exactly `league.equity.screen.holdout_t`'s expression (the
    floor's, the look's and the placebos'); None when the std is below 1e-12 or the result is not finite."""
    raise NotImplementedError(_STUB)


def column(result: Mapping[str, Any], name: str) -> list[Any]:
    """One column of `result["daily"]` by its `DAILY` name (ValueError for another name)."""
    raise NotImplementedError(_STUB)


def summarize(daily: Sequence[Sequence[Any]], lots: Sequence[Mapping[str, Any]],
              picks: Sequence[Mapping[str, Any]], capital: Any) -> dict[str, Any]:
    """The `summary` of the module docstring."""
    raise NotImplementedError(_STUB)


def by_year(daily: Sequence[Sequence[Any]], lots: Sequence[Mapping[str, Any]],
            picks: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """The `by_year` rows of the module docstring."""
    raise NotImplementedError(_STUB)


def failed(program: str, why: str) -> dict[str, Any]:
    """The record of a run the engine could not make: status "error" and its reason."""
    raise NotImplementedError(_STUB)


def view(result: Mapping[str, Any], window: str) -> dict[str, Any]:
    """What leaves the House's own records for `window` (one of `VIEWS`): "train": `TRAIN_VIEW`; "validation", "look",
    "forward": the status only. Never a daily row, a lot, an id, a call or a placebo figure."""
    raise NotImplementedError(_STUB)


def pooled(results: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Several runs of one version at one k read as one (the seen spans of the Train bar): the summary's sums added,
    T (D15) and the year rows from the concatenated daily x, `sd_date_return` over all their close dates."""
    raise NotImplementedError(_STUB)


__all__ = ["DAILY", "VIEWS", "STATUSES", "TRAIN_VIEW", "canonical", "sha", "t_stat", "column", "summarize", "by_year",
           "failed", "view", "pooled"]
