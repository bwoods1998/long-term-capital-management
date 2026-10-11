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

import hashlib
import math
import statistics
from typing import Any, Mapping, Sequence

#: The Newey-West lag of `se_ann`.
NW_LAG = 5
#: A version's measured horizon, by the median sessions its closed seen lots were held: 1-3, 4-10, 11 and more.
HORIZONS = ("days_1_3", "days_4_10", "days_11_plus")
#: A hidden run's statuses that are recorded (a run the House failed writes nothing).
STATUSES = ("ok", "disqualified")
#: Sessions a year (the annualization of `e_ann` and `se_ann`).
YEAR_SESSIONS = 252
#: A mean exposure under this has no annualized excess (the program was never in the market that year).
MIN_EXPOSURE = 1e-9
#: A sample sd under this gives no t (D4's rule).
MIN_SD = 1e-12


def _values(x: Any) -> list[float]:
    return [float(v) for v in x]


def nw_se(x: Any, lag: int = NW_LAG) -> float | None:
    """The Newey-West standard error of the mean of `x` with Bartlett weights to `lag` (the module docstring); None
    for fewer than 2 values or a variance estimate at or under zero."""
    xs = _values(x)
    n = len(xs)
    if n < 2:
        return None
    mean = math.fsum(xs) / n
    d = [v - mean for v in xs]
    lag = max(0, int(lag))

    def gamma(step: int) -> float:
        return math.fsum(d[t] * d[t - step] for t in range(step, n)) / n

    total = gamma(0) + 2.0 * math.fsum((1.0 - step / (lag + 1.0)) * gamma(step) for step in range(1, lag + 1))
    variance = total / n
    return math.sqrt(variance) if variance > 0 else None  # a NaN is not above zero either


def t_stat(x: Any) -> float | None:
    """mean(x) / sd(x, ddof 1) * sqrt(n) (D4's t); None under two values or when the sd is under `MIN_SD`."""
    xs = _values(x)
    n = len(xs)
    if n < 2:
        return None
    mean = math.fsum(xs) / n
    sd = math.sqrt(math.fsum((v - mean) ** 2 for v in xs) / (n - 1))
    return mean / sd * math.sqrt(n) if sd >= MIN_SD else None


def _universe(result: Mapping[str, Any]) -> list[str]:
    """The program's instruments (NEEDS' symbols as the run carries them; `result["symbols"]` is the same list)."""
    needs = result.get("needs") if isinstance(result.get("needs"), Mapping) else {}
    return [str(s) for s in (needs.get("symbols") or result.get("symbols") or [])]


def contribution(run: Any, *, k: float) -> dict[str, Any]:
    """D15 on one hidden run (a `runner.Run`: result and bars): {"year", "k", "status", "n_days", "n_lots",
    "exp_mean", "e_ann", "se_ann", "t_x", "days", "x", "w" (the three byte strings), "series_sha", "run_sha"}.
    ValueError as `screen.series` raises it, or for a run whose status is neither "ok" nor "disqualified".

    Fail closed on what a hidden run is: its sessions all lie in ONE year and that year is a work year
    (`elane_folds.WORK_YEARS`), else ValueError: no reserve, Validation or holdout session is ever scored here.
    `run_sha` is the run's own (E1's `EquityProgram.run_sha`: the code with its merged PARAMS; never compared with
    the swarm's `gate.run_sha`)."""
    import numpy as np

    from ..equity import config, screen
    from ..equity.store import from_ordinal
    from . import elane_folds

    result = getattr(run, "result", None)
    bars = getattr(run, "bars", None)
    if not isinstance(result, Mapping) or bars is None:
        raise ValueError("a hidden run is a result and the bars it ran on")
    status = str(result.get("status"))
    if status not in STATUSES:
        raise ValueError(f"a hidden run that ended {status!r} is not recorded (the House's failure, not the program's)")
    lots = [lot for lot in (result.get("lots") or []) if isinstance(lot, Mapping)]
    capital = result.get("capital") if result.get("capital") not in (None, "") else config.SLEEVE_USD
    s = screen.series(lots, bars, universe=_universe(result), capital=capital)
    n = int(len(s.days))
    if not n:
        raise ValueError("a hidden run with no session")
    years = {from_ordinal(int(d)).year for d in s.days}
    if len(years) != 1:
        raise ValueError(f"a hidden run's sessions lie in one year, not in {sorted(years)}")
    year = years.pop()
    if year not in elane_folds.WORK_YEARS:
        raise ValueError(f"{year} is not a work year: its sessions are never scored out of fold")
    w = _values(s.w)
    x = [float(r) - weight * float(b) for r, weight, b in zip(s.r, w, s.b)]
    mean_x, mean_w = math.fsum(x) / n, math.fsum(w) / n
    invested = mean_w >= MIN_EXPOSURE
    se = nw_se(x, NW_LAG)
    days = np.asarray(s.days, dtype="<i4").tobytes()
    xb = np.asarray(x, dtype="<f4").tobytes()
    wb = np.asarray(w, dtype="<f4").tobytes()
    return {"year": int(year), "k": float(k), "status": status, "n_days": n, "n_lots": len(lots),
            "exp_mean": mean_w, "e_ann": YEAR_SESSIONS * mean_x / mean_w if invested else None,
            "se_ann": YEAR_SESSIONS * se / mean_w if invested and se is not None else None, "t_x": t_stat(x),
            "days": days, "x": xb, "w": wb, "series_sha": hashlib.sha256(days + xb + wb).hexdigest(),
            "run_sha": str(result.get("run_sha") or "")}


def _closed(lots: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return [lot for lot in lots or () if isinstance(lot, Mapping) and lot.get("exit_day") not in (None, "")]


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) else None


def horizon(lots: Sequence[Mapping[str, Any]]) -> str | None:
    """One of `HORIZONS` by the median `held_sessions` of the closed lots (those with an exit day); None with none."""
    held = [h for h in (_number(lot.get("held_sessions")) for lot in _closed(lots)) if h is not None]
    if not held:
        return None
    median = statistics.median(held)
    return HORIZONS[0] if median <= 3 else HORIZONS[1] if median <= 10 else HORIZONS[2]


def costs(seen10: Sequence[Mapping[str, Any]], seen15: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """The seen-year cost facts (the module docstring) from the seen runs' results at 1.0x (`seen10`) and 1.5x
    (`seen15`), one result a seen span: {"gross_bp", "cost_bp", "rt_per_year"}, each None when no lot closed.

    A closed lot's notional is its `weight` x the run's `capital` (the engine's entry notional); the seen years are
    the runs' own `by_year` rows. A run without a P&L, or runs with no year, give None throughout."""
    from ..equity import config

    out: dict[str, Any] = {"gross_bp": None, "cost_bp": None, "rt_per_year": None}
    base = [r for r in seen10 or () if isinstance(r, Mapping)]
    stress = [r for r in seen15 or () if isinstance(r, Mapping)]

    def pnl(rows: Sequence[Mapping[str, Any]]) -> float | None:
        values = [_number((r.get("summary") or {}).get("pnl")) if isinstance(r.get("summary"), Mapping) else None
                  for r in rows]
        return math.fsum(values) if values and all(v is not None for v in values) else None  # type: ignore[arg-type]

    notionals: list[float] = []
    years: set[str] = set()
    for result in base:
        capital = _number(result.get("capital"))
        if capital is None:
            try:
                capital = float(str(result.get("capital") if result.get("capital") not in (None, "")
                                    else config.SLEEVE_USD))
            except ValueError:
                capital = float(config.SLEEVE_USD)
        for lot in _closed(result.get("lots") or ()):
            weight = _number(lot.get("weight"))
            if weight is not None and weight > 0:
                notionals.append(weight * capital)
        rows = result.get("by_year")
        years.update(str(y)[:4] for y in (rows if isinstance(rows, Mapping) else {}))
    pnl_10, pnl_15 = pnl(base), pnl(stress)
    trips = len(notionals)
    if not trips or not years:
        return out
    out["rt_per_year"] = trips / len(years)
    traded = math.fsum(notionals)  # RT x Nbar
    if pnl_10 is None or pnl_15 is None or traded <= 0:
        return out
    cost = 2.0 * (pnl_10 - pnl_15)
    out["cost_bp"] = cost / traded * 1e4
    out["gross_bp"] = (pnl_10 + cost) / traded * 1e4
    return out


__all__ = ["NW_LAG", "HORIZONS", "STATUSES", "YEAR_SESSIONS", "MIN_EXPOSURE", "MIN_SD", "nw_se", "t_stat",
           "contribution", "horizon", "costs"]
