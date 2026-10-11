"""THE OUT-OF-FOLD ARITHMETIC of the equity memory (release E3, D15): what a hidden year's run and the seen runs say.

Owner: E (league/ops/E3_INTERFACES.md). Pure: results and bars in, numbers out; no store, no clock, no model. Called by
league/swarm/elane_memory.py `ingest` alone. Recorded, never judged: nothing here is a bar, a verdict or a view, and
no generator reads what it returns.

THE CONTRIBUTION (`contribution`) of a scored version with hidden year y, at k in (1.0, 1.5): `run` = the hidden run
at k (E1's `runner.Run`); `s = screen.series(run.result["lots"], run.bars, universe=symbols,
capital=run.result["capital"])` (its run sessions are y's); x = s.r - s.w * s.b; `n_days` = len(x); `n_lots` = its
lots; `exp_mean` = mean(s.w); e_ann = 252 * mean(x) / mean(w) (None when mean(w) < 1e-9); se_ann = 252 * nw_se(x, 5) /
mean(w); `t_x` = mean(x) / sd(x, ddof 1) * sqrt(n) (None when sd < 1e-12); `status` = the run's ("ok" or
"disqualified": a disqualified year is recorded as it traded). The series kept: `days` int32 little-endian ordinals,
`x` and `w` float32 little-endian; `series_sha` = sha256 of the three byte strings joined.

THE NEWEY-WEST STANDARD ERROR (`nw_se`): nw_se(x, L)^2 = (g_0 + 2 * sum_{l=1..L} (1 - l / (L + 1)) * g_l) / n, g_l =
(1/n) * sum_{t=l+1..n} (x_t - xbar)(x_{t-l} - xbar).

THE SEEN-YEAR COST FACTS (`costs`, `horizon`), from the seen runs summed at 1.0x and 1.5x: C = 2 * (pnl_10 - pnl_15),
G = pnl_10 + C, RT = closed lots at 1.0x, Nbar = their mean notional; `cost_bp = C / (RT * Nbar) * 1e4`, `gross_bp = G
/ (RT * Nbar) * 1e4`, `rt_per_year = RT / seen years` (None when RT = 0); `horizon` = "days_1_3" | "days_4_10" |
"days_11_plus" by the median `held_sessions` of those lots.

Every sum and mean goes through `math.fsum` (the built-in `sum` is not exact on Python 3.11, and CI runs 3.11 and
3.14). Standard library and numpy only (numpy inside functions).
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

#: The Newey-West lag of `se_ann`.
NW_LAG = 5
#: A version's measured horizon, by the median sessions its closed seen lots were held: 1-3, 4-10, 11 and more.
HORIZONS = ("days_1_3", "days_4_10", "days_11_plus")
#: A hidden run's statuses that are recorded (a run the House failed writes nothing).
STATUSES = ("ok", "disqualified")


def nw_se(x: Any, lag: int = NW_LAG) -> float | None:
    """The Newey-West standard error of the mean of `x` with Bartlett weights to `lag` (the module docstring); None
    for fewer than 2 values or a variance estimate at or under zero."""
    raise NotImplementedError("E: league/swarm/elane_effects.py nw_se")


def contribution(run: Any, *, k: float) -> dict[str, Any]:
    """D15 on one hidden run (a `runner.Run`: result and bars): {"year", "k", "status", "n_days", "n_lots",
    "exp_mean", "e_ann", "se_ann", "t_x", "days", "x", "w" (the three byte strings), "series_sha", "run_sha"}.
    ValueError as `screen.series` raises it, or for a run whose status is neither "ok" nor "disqualified"."""
    raise NotImplementedError("E: league/swarm/elane_effects.py contribution")


def horizon(lots: Sequence[Mapping[str, Any]]) -> str | None:
    """One of `HORIZONS` by the median `held_sessions` of the closed lots (those with an exit day); None with none."""
    raise NotImplementedError("E: league/swarm/elane_effects.py horizon")


def costs(seen10: Sequence[Mapping[str, Any]], seen15: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """The seen-year cost facts (the module docstring) from the seen runs' results at 1.0x (`seen10`) and 1.5x
    (`seen15`), one result a seen span: {"gross_bp", "cost_bp", "rt_per_year"}, each None when no lot closed."""
    raise NotImplementedError("E: league/swarm/elane_effects.py costs")


__all__ = ["NW_LAG", "HORIZONS", "STATUSES", "nw_se", "contribution", "horizon", "costs"]
