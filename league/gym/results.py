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
  median_max_loss_per_structure (one structure's maximum loss, USD: for sizing), skew_traded and
  kurt_traded (the moments of the daily returns on maximum loss the t is about: the deflated Sharpe on
  traded days, the owner's decision D2 of Sept 26);
- `fills`: orders, opens, closes, filled, partial, cancelled, expired, rejected with their reasons,
  liquidated, settled, exercised, fill_rate, the share of fills at the natural, the mean slippage
  from the mid a share and in half-spreads;
- `breakdown`: n, pnl, win_rate and pnl_per_max_loss by weekday, time_of_day, dte, rv and iv terciles
  (the day's realized and implied vol, cut within the run), quarter, type, root and exit_reason;
- `by_year`: per calendar year of the days the program's OWN roots had data (a year without a trade
  included; a year only its batch company had data for is absent): trades, days, days_traded, pnl, the
  daily mean and `t_daily` on maximum loss, quarters_positive and quarter_pnl (the swarm's robust Train
  objective, Sept 26: the worst Train year, not the whole window, scores a version);
- `drift` (Train only; the swarm's drift screen, Sept 27): per calendar year of the program's own days and pooled:
  `beta`, the slope of the day's P&L on the move of the roots it held over the hours it held them, over HELD days only,
  each weighted by 1 / its realized variance (its exposure, dollars per unit return); `drift_usd`, beta x the roots' unconditional drift over those hours summed
  over held days (what that exposure earns on average days); `alpha_usd` = pnl - drift_usd (what its timing added, after
  costs), `alpha` a day, `t` (the one-sample t of the drift-adjusted daily P&L over all days), `days`, `held_days`. Each
  year carries its sufficient `stats`, so a split run merges exactly (`drift`, `drift_fit`, `merge_drift`);
- `daily`: [day, P&L, equity] for every trading day of the run (zero days included);
- `trades`: every trade (entry, exit, legs, fees, maximum loss, P&L, the context at entry);
- `worst`: the five worst trades with their context;
- `runtime`: the program's calls, errors, timeouts, seconds and first error messages;
- `result_sha`: a hash of everything above but the timing, so two runs of the same inputs agree.

`view(result, window)` is what leaves a run of each window (validation: no trades, no dates, no daily
series and no drift block; holdout and forward: the gate's inputs only). Standard library only.
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
    skew_traded = stats.skewness(by_day)
    kurt_traded = stats.kurtosis(by_day)
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
        "skew_traded": None if skew_traded is None else round(skew_traded, 5),
        "kurt_traded": None if kurt_traded is None else round(kurt_traded, 5),
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


#: A root "had data" in a year when it had a chain on at least this share of the year's days (the program's own days): a
#: root with a few stray sessions in 2020 is not a 2020 root (the Train extension, Sept 27; `by_year`, `drift`).
ROOT_YEAR_SHARE = 0.5


def roots_in_year(root_days: Mapping[str, Any], days: int, share: float = ROOT_YEAR_SHARE) -> list[str]:
    """The roots with data on at least `share` of a year's `days` ({root: days with a chain})."""
    return sorted(str(r) for r, n in (root_days or {}).items() if days > 0 and int(n) >= share * days)


def by_year(trades: Sequence[dict], daily: Sequence[Sequence[Any]], own_days: Any = None,
            roots_by_day: Any = None) -> dict[str, dict[str, Any]]:
    """One row per calendar year of the run's days (a year the program never traded included): trades, days,
    days_traded, pnl, the mean and t of that year's daily returns on maximum loss (`daily_returns`), its quarters
    positive and its P&L by quarter. `own_days` (ISO days), when given, keeps only the days the program's own roots had
    data: a batch mixes roots, and a day only another program's root had data for says nothing of this one. The swarm
    scores a Train version on its WORST year (Sept 26). `roots_by_day` ({ISO day: the program's roots with data that day})
    adds each year's `root_days` ({root: days with a chain}) and `roots` (those with data on `ROOT_YEAR_SHARE` of the
    year's days): the swarm counts a 2020-21 year only when every one of the program's roots had data in it (the Train
    extension of Sept 27: a name has no 2020-21 chains)."""
    days = [d for d in daily if own_days is None or str(d[0]) in own_days]
    out: dict[str, dict[str, Any]] = {}
    for year in sorted({str(d[0])[:4] for d in days}):
        mine = [t for t in trades if str(t["day"]).startswith(year)]
        mean, t = _t(daily_returns(mine))
        quarters: dict[str, float] = {}
        for d in days:
            if str(d[0]).startswith(year):
                quarters[_quarter(d[0])] = quarters.get(_quarter(d[0]), 0.0) + float(d[1])
        out[year] = {"trades": len(mine), "days": sum(1 for d in days if str(d[0]).startswith(year)),
                     "days_traded": len({x["day"] for x in mine}), "pnl": round(sum(x["pnl"] for x in mine), 2),
                     "mean_return_on_max_loss_daily": None if mean is None else round(mean, 6),
                     "t_daily": None if t is None else round(t, 4),
                     "quarters_positive": f"{sum(v > 0 for v in quarters.values())}/{len(quarters)}",
                     "quarter_pnl": {q: round(v, 2) for q, v in sorted(quarters.items())}}
        if roots_by_day is not None:
            counts: dict[str, int] = {}
            for d in days:
                if str(d[0]).startswith(year):
                    for r in roots_by_day.get(str(d[0]), ()):
                        counts[str(r)] = counts.get(str(r), 0) + 1
            out[year]["root_days"] = dict(sorted(counts.items()))
            out[year]["roots"] = roots_in_year(counts, out[year]["days"])
    return out


def merge_years(parts: Sequence[Mapping[str, Any]], trades: Sequence[dict], daily: Sequence[Sequence[Any]]) -> dict[str, dict[str, Any]]:
    """`by_year` of a split run from its segments' own rows (each kept to the days its roots had data): the years and
    their days and quarter P&L summed, the trade statistics recomputed on the whole year's trades."""
    if not all(isinstance(p.get("by_year"), Mapping) for p in parts):
        return by_year(trades, daily)
    days: dict[str, int] = {}
    quarters: dict[str, dict[str, float]] = {}
    root_days: dict[str, dict[str, int]] = {}
    for p in parts:
        for year, row in p["by_year"].items():
            days[year] = days.get(year, 0) + int(row.get("days") or 0)
            if isinstance(row.get("root_days"), Mapping):
                into_roots = root_days.setdefault(year, {})
                for r, n in row["root_days"].items():
                    into_roots[str(r)] = into_roots.get(str(r), 0) + int(n)
            into = quarters.setdefault(year, {})
            for q, v in (row.get("quarter_pnl") or {}).items():
                into[q] = into.get(q, 0.0) + float(v)
    out = {}
    for year in sorted(days):
        mine = [t for t in trades if str(t["day"]).startswith(year)]
        mean, t = _t(daily_returns(mine))
        qs = quarters.get(year, {})
        out[year] = {"trades": len(mine), "days": days[year], "days_traded": len({x["day"] for x in mine}),
                     "pnl": round(sum(x["pnl"] for x in mine), 2),
                     "mean_return_on_max_loss_daily": None if mean is None else round(mean, 6),
                     "t_daily": None if t is None else round(t, 4),
                     "quarters_positive": f"{sum(v > 0 for v in qs.values())}/{len(qs)}",
                     "quarter_pnl": {q: round(v, 2) for q, v in sorted(qs.items())}}
        if year in root_days:
            out[year]["root_days"] = dict(sorted(root_days[year].items()))
            out[year]["roots"] = roots_in_year(root_days[year], days[year])
    return out


# --------------------------------------------------------------------------- drift (Sept 27)
#: What a drift block's charge rests on: on each HELD day (a position open at any time of it), the program's exposure was
#: measured against the move of the roots it held over the hours it held them (`Account.exposure`), and it is charged the
#: root's UNCONDITIONAL drift over those hours: the year's mean overnight return if it held from the prior close, plus the
#: year's mean intraday return a minute for each minute held.
DRIFT_BASIS = "held-hours"
#: A variance of the drift-adjusted daily P&L at or below this share of the P&L's mean square is rounding, not noise (the
#: drift charge took all of it): its t is None.
_NO_VARIANCE = 1e-12


#: The lowest daily variance a held day's weight uses (a flat or missing day never weighs without bound).
RV_FLOOR = 1e-8


def drift_moments(pairs: Sequence[tuple[float, float]], weights: Sequence[float] | None = None) -> list[float]:
    """[n, W, mean x, mean P, S_xx, S_pp, S_xp] of (x, P) pairs under `weights` (W their sum; all 1 when None), the sums
    centered on the weighted means (two passes): what `merge` combines."""
    n = len(pairs)
    if not n:
        return [0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    w = [1.0] * n if weights is None else [float(v) for v in weights]
    total = sum(w)
    mx = sum(wi * x for wi, (x, _) in zip(w, pairs)) / total
    mp = sum(wi * p for wi, (_, p) in zip(w, pairs)) / total
    return [n, total, mx, mp, sum(wi * (x - mx) ** 2 for wi, (x, _) in zip(w, pairs)),
            sum(wi * (p - mp) ** 2 for wi, (_, p) in zip(w, pairs)), sum(wi * (x - mx) * (p - mp) for wi, (x, p) in zip(w, pairs))]


def combine_moments(a: Sequence[float], b: Sequence[float]) -> list[float]:
    """The weighted moments of two sets of days together (Chan's pairwise update): exactly the moments of their union."""
    na, nb = int(a[0]), int(b[0])
    if not na or not nb:
        return [float(x) if i else int(x) for i, x in enumerate(b if not na else a)]
    wa, wb = float(a[1]), float(b[1])
    total = wa + wb
    dx, dp, f = float(b[2]) - float(a[2]), float(b[3]) - float(a[3]), wa * wb / total
    return [na + nb, total, float(a[2]) + dx * wb / total, float(a[3]) + dp * wb / total, float(a[4]) + float(b[4]) + dx * dx * f,
            float(a[5]) + float(b[5]) + dp * dp * f, float(a[6]) + float(b[6]) + dx * dp * f]


def drift_rows(daily: Sequence[Sequence[Any]], returns: Mapping[str, Mapping[str, Any]], exposure: Mapping[str, Mapping[str, Any]],
               roots: Sequence[str], own_days: Any = None) -> list[tuple[str, float, dict, dict]]:
    """(day, P&L, base, held) for every day of the run (zero days included) on which one of its own `roots` had a full day's
    return: `base` {root: (overnight return, intraday return, session minutes, the day's realized variance or None)} from
    the engine's regimes (`returns`: {day: {root: {"ret_on", "ret_in", "session", "rv_day"}}}); `held` {root: (carried
    from the prior close 0/1, minutes held, the root's return over the hours held)} from the account's `exposure` ({} on a
    flat day). `own_days`, as in `by_year`, keeps the days its roots had data."""
    def finite(*xs: Any) -> bool:
        return all(isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) for x in xs)

    out = []
    for d in daily:
        day = str(d[0])
        if own_days is not None and day not in own_days:
            continue
        today = returns.get(day) or {}
        base = {}
        for root in roots:
            row = today.get(root) or {}
            on, intra, session, rv = row.get("ret_on"), row.get("ret_in"), row.get("session"), row.get("rv_day")
            if finite(on, intra, session):
                base[root] = (float(on), float(intra), float(session), float(rv) if finite(rv) and rv > 0 else None)
        if not base:
            continue
        held = {}
        for root, span in sorted((exposure.get(day) or {}).items()):
            if isinstance(span, (list, tuple)) and len(span) == 3 and finite(*span):
                held[str(root)] = (int(span[0]), float(span[1]), float(span[2]))
        out.append((day, float(d[1]), base, held))
    return out


def _add(into: dict[str, float], key: str, value: float) -> None:
    into[key] = into.get(key, 0.0) + value


def drift_stats(rows: Sequence[tuple[str, float, Mapping[str, Any], Mapping[str, Any]]]) -> dict[str, dict[str, Any]]:
    """Each year's sufficient statistics of `drift_rows`, every one a sum but `held` (centered moments), so segments add up
    exactly (`combine_stats`):

    - `n`, `p`, `pp`: the days, and the sum and sum of squares of P, over ALL days;
    - `held`: the moments of (x, P) over HELD days, x the day's mean return of the roots held over their hours held, each
      day weighted by 1 / its realized variance (the held roots' mean `rv_day`, at least `RV_FLOOR`; 1 when a row has
      none): a program that sizes to a premium budget holds less on a volatile day, and an unweighted slope would weigh
      those days by their variance and take part of the drift for alpha;
    - `v`: over held days, the weights on each root's overnight and intraday drift ({"SPY:on": days held from the prior
      close, "SPY:in": minutes held}, a day's weights averaged over the roots it held);
    - `roots`: {root: [days, sum of overnight returns, sum of intraday returns, sum of session minutes]} over ALL days;
    - `rp`, `rr`: over ALL days, the sums of P times each root's overnight and intraday return ("SPY:on", "SPY:in"), and of
      their pairwise products: what the t of the drift-adjusted daily P&L needs (`drift_fit`)."""
    years: dict[str, dict[str, Any]] = {}
    pairs: dict[str, list[tuple[float, float]]] = {}
    weights: dict[str, list[float]] = {}
    for day, pnl, base, held in rows:
        st = years.setdefault(day[:4], {"n": 0, "p": 0.0, "pp": 0.0, "held": [0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], "v": {},
                                          "roots": {}, "rp": {}, "rr": {}})
        st["n"] += 1
        st["p"] += pnl
        st["pp"] += pnl * pnl
        comp: dict[str, float] = {}
        for root, (on, intra, session, *_rv) in base.items():
            acc = st["roots"].setdefault(root, [0, 0.0, 0.0, 0.0])
            acc[0] += 1
            acc[1] += on
            acc[2] += intra
            acc[3] += session
            comp[f"{root}:on"], comp[f"{root}:in"] = on, intra
        for a, xa in comp.items():
            _add(st["rp"], a, pnl * xa)
            for b, xb in comp.items():
                if a <= b:
                    _add(st["rr"], f"{a}|{b}", xa * xb)
        if held:
            w = 1.0 / len(held)
            pairs.setdefault(day[:4], []).append((sum(span[2] for span in held.values()) * w, pnl))
            rvs = [base[r][3] for r in held if r in base and len(base[r]) > 3 and base[r][3] is not None]
            weights.setdefault(day[:4], []).append(1.0 / max(sum(rvs) / len(rvs), RV_FLOOR) if rvs else 1.0)
            for root, (carried, minutes, _) in held.items():
                _add(st["v"], f"{root}:on", w * carried)
                _add(st["v"], f"{root}:in", w * minutes)
    for year, rows_ in pairs.items():
        years[year]["held"] = drift_moments(rows_, weights[year])
    return years


def combine_stats(a: Mapping[str, Any], b: Mapping[str, Any]) -> dict[str, Any]:
    """Two sets of days' statistics together: sums added, the held moments combined (`combine_moments`). Exact."""
    out: dict[str, Any] = {"n": int(a["n"]) + int(b["n"]), "p": float(a["p"]) + float(b["p"]), "pp": float(a["pp"]) + float(b["pp"]),
                           "held": combine_moments(a["held"], b["held"]), "roots": {}}
    for name in ("v", "rp", "rr"):
        merged: dict[str, float] = {}
        for side in (a, b):
            for key, value in (side.get(name) or {}).items():
                _add(merged, str(key), float(value))
        out[name] = merged
    for side in (a, b):
        for root, acc in (side.get("roots") or {}).items():
            into = out["roots"].setdefault(str(root), [0, 0.0, 0.0, 0.0])
            into[0] += int(acc[0])
            for i in (1, 2, 3):
                into[i] += float(acc[i])
    return out


def drift_fit(st: Mapping[str, Any]) -> dict[str, Any]:
    """One year's drift-adjusted alpha from its statistics (`drift_stats`):

    - beta: the slope of P on x over HELD days only, weighted by 1 / each day's realized variance (dollars per unit
      return): the exposure it held, whatever those days' variance. A slope over every day weighs held days by their
      variance (a calm-day holder's drift passed for alpha, a volatile rebound edge for a loss), and an unweighted one
      over held days still does when the exposure itself moves with the volatility (a premium budget);
    - drift_usd: beta x the roots' unconditional drift over the hours held: for each held day, the year's mean overnight
      return if it was held from the prior close, plus the year's mean intraday return a minute for each minute held.
      What that exposure over those hours earns on average days;
    - alpha_usd = pnl - drift_usd; alpha = alpha_usd over the year's days;
    - t: the one-sample t, over ALL the year's days, of the drift-adjusted daily P&L z_d = P_d - beta x (the day's share of
      the drift charge). The charge rests on the year's mean returns, estimated from every day, so each day carries its
      share: C/N of its overnight return and K/S of its intraday return (C the held days from the prior close, K the
      minutes held, N the days, S the session minutes, per root). The z_d sum to alpha_usd exactly, and their variance
      holds both the P&L's noise and the drift estimate's (a charge per held day at a fixed mean would leave the latter out:
      a calm-day holder's t came out too high, a volatile-day holder's and an always-held carry's too low). None under two
      days or with no variance (P a line in the return: pure drift)."""
    n = int(st["n"])
    n_h, _, _, _, sxx, _, sxp = st["held"]
    beta = float(sxp) / float(sxx) if int(n_h) >= 3 and float(sxx) > 0 else 0.0
    v = st.get("v") or {}
    coef: dict[str, float] = {}
    for root, (days, _on, _intra, session) in (st.get("roots") or {}).items():
        coef[f"{root}:on"] = float(v.get(f"{root}:on", 0.0)) / int(days) if int(days) else 0.0
        coef[f"{root}:in"] = float(v.get(f"{root}:in", 0.0)) / float(session) if float(session) > 0 else 0.0
    sums = {}
    for root, (_days, on, intra, _session) in (st.get("roots") or {}).items():
        sums[f"{root}:on"], sums[f"{root}:in"] = float(on), float(intra)
    pnl = float(st["p"])
    drift_usd = beta * sum(coef[k] * sums[k] for k in coef)
    alpha_usd = pnl - drift_usd
    cross = sum(coef.get(k, 0.0) * float(x) for k, x in (st.get("rp") or {}).items())
    square = 0.0
    for key, x in (st.get("rr") or {}).items():
        a, b = key.split("|")
        square += (1.0 if a == b else 2.0) * coef.get(a, 0.0) * coef.get(b, 0.0) * float(x)
    sq = float(st["pp"]) - 2.0 * beta * cross + beta * beta * square   # the sum of z_d squared
    t = _t_of(alpha_usd, sq, n, float(st["pp"]))
    return {"days": n, "held_days": int(n_h), "pnl": pnl, "alpha": alpha_usd / n if n else 0.0, "alpha_usd": alpha_usd,
            "beta": beta, "drift_usd": drift_usd, "t": t, "sum_sq": sq, "sum_pp": float(st["pp"])}


def _t_of(total: float, sq: float, n: int, pp: float) -> float | None:
    """The one-sample t of n daily values from their sum and sum of squares; None under two days, or when their variance is
    no more than rounding against the P&L's own mean square `pp`/n (the drift charge took all of it: pure drift)."""
    if n < 2:
        return None
    var = (sq - total * total / n) / (n - 1)
    if var <= _NO_VARIANCE * max(pp / n, 1e-300):
        return None
    return (total / n) / math.sqrt(var / n)


def _drift_row(f: Mapping[str, Any]) -> dict[str, Any]:
    def r(x: Any, places: int) -> Any:
        return None if x is None else round(float(x), places)
    return {"days": f["days"], "held_days": f["held_days"], "pnl": r(f["pnl"], 2), "alpha": r(f["alpha"], 4),
            "alpha_usd": r(f["alpha_usd"], 2), "t": r(f["t"], 4), "beta": r(f["beta"], 2), "drift_usd": r(f["drift_usd"], 2)}


def drift_from_stats(stats: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """The `drift` block from each year's statistics: per year its fit (`drift_fit`, with its `stats` for `merge`), and the
    POOLED line over Train: each year keeps its own beta and drift, alpha_usd and drift_usd are the years' sums, and t is
    the one-sample t of the whole Train window's drift-adjusted daily P&L."""
    fits = {y: drift_fit(st) for y, st in sorted(stats.items()) if int(st.get("n") or 0) > 0}
    days = sum(f["days"] for f in fits.values())
    total = sum(f["alpha_usd"] for f in fits.values())
    t = _t_of(total, sum(f["sum_sq"] for f in fits.values()), days, sum(f["sum_pp"] for f in fits.values()))
    held = sum(f["held_days"] for f in fits.values())
    pooled = {"days": days, "held_days": held, "pnl": sum(f["pnl"] for f in fits.values()), "alpha": total / days if days else 0.0,
              "alpha_usd": total, "beta": sum(f["beta"] * f["held_days"] for f in fits.values()) / held if held else 0.0,
              "drift_usd": sum(f["drift_usd"] for f in fits.values()), "t": t}
    return {"basis": DRIFT_BASIS, "years": {y: {**_drift_row(f), **_drift_extent(f, stats[y]), "stats": stats[y]}
                                            for y, f in fits.items()},
            "pooled": _drift_row(pooled)}


def _drift_extent(f: Mapping[str, Any], st: Mapping[str, Any]) -> dict[str, Any]:
    """What lets the swarm pool a SUBSET of the years again (the Train extension, Sept 27: a 2020-21 year some root of the
    program had no data in is left out): the year's sums of the drift-adjusted P&L's squares and of the P&L's, and each
    root's days with data (the statistics themselves are dropped where rows are kept)."""
    return {"sum_sq": float(f["sum_sq"]), "sum_pp": float(f["sum_pp"]),
            "root_days": {str(r): int(acc[0]) for r, acc in sorted((st.get("roots") or {}).items())}}


def drift(daily: Sequence[Sequence[Any]], returns: Mapping[str, Mapping[str, Any]], exposure: Mapping[str, Mapping[str, Any]],
          roots: Sequence[str], own_days: Any = None) -> dict[str, Any]:
    """The run's drift-adjusted alpha (the swarm's drift screen, Sept 27): a long call in a bull year earns whatever its
    signal says, so what a program's timing adds is measured net of the market's own drift over the hours it held
    exposure, a calendar year at a time (`drift_rows`, `drift_stats`, `drift_fit`, `drift_from_stats`)."""
    return {**drift_from_stats(drift_stats(drift_rows(daily, returns, exposure, roots, own_days))), "roots": sorted(roots)}


def merge_drift(parts: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
    """The drift block of a split run: each year's statistics from every segment that has the year, combined
    (`combine_stats`: sums added, held moments combined exactly), then fitted once, so the result equals the fit of the
    whole window's days. None when a segment has no block (a result from before it)."""
    stats: dict[str, dict[str, Any]] = {}
    roots = next((list(p["drift"]["roots"]) for p in parts if isinstance(p.get("drift"), Mapping)
                  and isinstance(p["drift"].get("roots"), list)), None)
    for p in parts:
        block = p.get("drift")
        if not isinstance(block, Mapping) or not isinstance(block.get("years"), Mapping):
            return None
        for year, row in block["years"].items():
            st = row.get("stats") if isinstance(row, Mapping) else None
            if not isinstance(st, Mapping) or not isinstance(st.get("held"), (list, tuple)) or len(st["held"]) != 7:
                return None
            stats[year] = combine_stats(stats[year], st) if year in stats else combine_stats(
                {"n": 0, "p": 0.0, "pp": 0.0, "held": [0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]}, st)
    out = drift_from_stats(stats)
    if roots is not None:
        out["roots"] = roots
    return out


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
    own = {d for d, rows in regimes.items() if any(r in rows for r in account.roots)}
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
        "by_year": by_year(trades, account.daily, own, {d: [r for r in account.roots if r in rows] for d, rows in regimes.items()}),
        "daily": [list(d) for d in account.daily],
        "trades": trades,
        "worst": sorted(trades, key=lambda t: t["pnl"])[:5],
        "runtime": {k: v for k, v in account.runner.stats().items() if k != "seconds"},
    }
    if getattr(cfg, "window", "train") == "train":  # Train only: no other window's figures are ever computed for it
        result["drift"] = drift(account.daily, regimes, getattr(account, "exposure", {}) or {}, account.roots, own)
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
              "by_year": merge_years(parts, trades, daily), "daily": daily, "trades": trades, "worst": sorted(trades, key=lambda t: t["pnl"])[:5],
              "runtime": {"calls": sum(p["runtime"]["calls"] for p in parts), "errors": sum(p["runtime"]["errors"] for p in parts),
                          "timeouts": sum(p["runtime"]["timeouts"] for p in parts),
                          "messages": [m for p in parts for m in p["runtime"]["messages"]][:10],
                          "disqualified": next((p["runtime"]["disqualified"] for p in parts if p["runtime"]["disqualified"]), None)}}
    merged_drift = merge_drift(parts)
    if merged_drift is not None:
        result["drift"] = merged_drift
    result["result_sha"] = sha(result)
    result["seconds"] = round(sum(p.get("seconds", 0.0) for p in parts), 3)
    return result


STRESS_KEYS = ("trades", "days_traded", "pnl", "pnl_per_max_loss", "mean_return_on_max_loss_daily", "t_daily", "sharpe_daily")
_HIDDEN_FROM_VALIDATION = ("trades", "daily", "worst", "start", "end", "segments", "seconds", "drift")


def view(result: Mapping[str, Any], window: str) -> dict[str, Any]:
    """What leaves a run of `window`, the one place these rules live:

    - "train": everything (a researcher sees all of Train), the drift block included;
    - "validation": the statistics a line needs and the breakdowns, with NO trades, NO dates, NO
      daily series and NO drift block (quarters become q1..q4): summary (sharpe_daily, days, skew_daily, kurt_daily,
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


__all__ = ["build", "merge", "view", "stress_block", "summarize", "daily_returns", "by_year", "merge_years", "drift", "merge_drift",
           "drift_fit", "drift_moments", "combine_moments", "drift_stats", "combine_stats", "drift_from_stats", "drift_rows", "sha",
           "canonical", "ENGINE_VERSION"]
