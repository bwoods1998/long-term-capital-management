"""THE MECHANISM TEST (release B, Oct 2026): before a carded family's first broad Train replay, does its signal beat its
own declared comparison on a small pre-registered sample of Train days?

WHY. A broad Train replay is five years on every root of the family (about 20 box-seconds on the Sept 30 image; the
families that died on that image made 22 each on average, and 91% of them never reached an eligible Train version). On
Sept 30, 788 House sweeps had a `signal_on` placebo row: half of those placebo rows made no
trade at all (the switch turned the program off, so nothing was compared), and where both rows traded, only 22% of
signals beat their placebo by half a standard error even on the whole of Train. Most families were replaying programs
whose signal carried no information beyond the structure it traded.

THE TEST. The program is run twice through the Gym's existing batch API (no Gym code changes): as asked (signal on), and
with the card's ablation (`card.ablation`: PARAMS[param] = off, which must turn the signal into the card's comparison
strategy: the same structure, schedule, sizing and exits with only the signal's condition removed). Each arm runs over
the same PRE-REGISTERED windows of Train (`sample_windows`: one window of `window_days` calendar days a Train year, about
25 sessions, starting on the 15th of January, April, July and October in turn; at most `max_windows` years, evenly
spaced; fixed here, never chosen per family or after a result), unsplit, as `window="train"` jobs with their own start
and end, so every family's test jobs of one window share batches.

THE STATISTIC. Each arm's per-entry-day return on maximum loss (the validation line's own unit: a day's P&L over the
day's maximum loss, trades grouped by entry day). The question is whether conditioning on the signal selects better
entries than the comparison does, not whether trading less loses less, so per-day totals are never compared:
- WELCH (the usual case): the signal arm's entry days against the ablation arm's entry days on which the signal arm did
  not enter (disjoint samples: the comparison strategy's own days). t = (mean_on - mean_off) / sqrt(var_on/n_on +
  var_off/n_off).
- PAIRED (when the ablation enters only on the signal's days: the signal changes what is bought, not when): the mean of
  the per-day differences over the shared days, over its standard error.
PASSED needs a positive difference with t >= the bound. The NOISE BOUND is `min_t` (0.5, half a standard error) for a
family's first test, and rises by `step_t` (0.5) for each version of the family that already failed (`bound`): a family
that fails may revise and try again, and each try is another look at the same question, so a signal with no information
cannot walk through on retries. Set by a fixed-seed simulation of ~125 sample days (league/tests/test_swarm_mechanism.py,
`Benchmark`): on its first test a signal with no information beyond its comparison passes about 32% of the time (so broad
replay of such families falls by about two thirds), while a signal just strong enough for the validation line (t 2 a year)
passes about 80% of the time and one at t 3 about 93%, at the eligibility floor's frequency with no cost drag (the hardest
case; any cost drag the comparison pays makes a real signal easier to see). Over three independent tries at the rising
bound (0.5, 1.0, 1.5) the null passes about 48% of the time and the t 2 signal about 96%; with a flat bound the null would
pass about 68%.

VERDICTS. `passed` (broad replay proceeds); `failed` (the signal did not beat its comparison beyond the bound: an
economic finding); `thin` (the signal arm entered on fewer than `min_on_days` sample days: too sparse to test, and too
sparse for Train's 20 days a year); `invalid_ablation` (the ablation arm did not trade the comparison, so nothing was
compared: fix the switch); `untestable` (the program erred or had no data on the sample). Every Gym evaluation is a
trial of the lineage, recorded as a `window="mechanism"` run row (never read by the Train score, the best or the
drift screen). The researcher (league/swarm/researcher.py) runs it, answers from the store when the same test was made,
records the verdict on the card (`cards.add_evidence`) and in the family's state, and retires the family after
`max_failures` failed versions with the MECHANISM verdict (a mechanism verdict: the card-based rebirth refusal reads it).

Standard library only.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
from typing import Any, Iterable, Mapping, Sequence

#: The settings' defaults (`researcher.mechanism_test`).
DEFAULTS: dict[str, Any] = {
    "enabled": True,
    "min_t": 0.5,
    "step_t": 0.5,
    "max_windows": 5,
    "window_days": 35,
    "min_on_days": 5,
    "min_off_days": 5,
    "max_failures": 3,
    "max_untestable": 4,
    "timeout_seconds": 900,
}
#: A retirement reason's mark for a failed mechanism (architect.tag_of reads it as MECHANISM).
MARK = "Mechanism verdict MECHANISM"
#: Its first sentence (no figure, no colon) is the one the site may publish (`public.note_text`); the mark and the count follow.
MECHANISM_CAUSE = ("Retired after its signal failed the pre-registered mechanism tests against the comparison its card declared. "
                   f"{MARK}, a tested finding: {{n}} versions did not beat that comparison beyond the noise bound; this does "
                   "not establish that every related mechanism lacks an edge")
#: A family whose programs never made a testable comparison: untested, so it keeps the idle rule's words (IDLE).
UNTESTABLE_CAUSE = ("Retired because its mechanism tests could not compare its signal with the comparison its card declared. "
                    "It made {n} such tests (an ablation that did not trade, too few signal days, errors or no data); it is a "
                    "time limit, not a finding that the mechanism has no edge")
VERDICTS = ("passed", "failed", "thin", "invalid_ablation", "untestable")
#: The state key the researcher keeps a family's test record under.
STATE_KEY = "mechanism"


def config(settings: Mapping[str, Any] | None) -> dict[str, Any]:
    """`researcher.mechanism_test` over DEFAULTS; a bad value falls back to its default."""
    raw = ((settings or {}).get("researcher") or {}).get("mechanism_test")
    out = dict(DEFAULTS)
    if isinstance(raw, Mapping):
        for k, default in DEFAULTS.items():
            v = raw.get(k, default)
            if isinstance(default, bool):
                out[k] = v if isinstance(v, bool) else default
            elif isinstance(v, bool) or not isinstance(v, (int, float)) or v != v or abs(v) == float("inf"):
                out[k] = default
            else:
                out[k] = type(default)(v) if not isinstance(default, float) else float(v)
    elif raw is False:
        out["enabled"] = False
    out["max_windows"] = max(1, int(out["max_windows"]))
    out["window_days"] = max(7, min(int(out["window_days"]), 120))
    return out


def sample_windows(first_year: int, last_year: int, *, max_windows: int = 5, window_days: int = 35) -> list[tuple[str, str]]:
    """The pre-registered sample (the module docstring): one window a Train year from `first_year` to `last_year`, at most
    `max_windows` evenly spaced years (the first and the last always), the i-th starting on the 15th of January, April,
    July or October in turn."""
    years = list(range(int(first_year), int(last_year) + 1))
    k = max(1, int(max_windows))
    if len(years) > k:
        years = [years[round(i * (len(years) - 1) / (k - 1))] for i in range(k)] if k > 1 else [years[-1]]
    out = []
    for i, year in enumerate(years):
        start = dt.date(year, 1 + 3 * (i % 4), 15)
        end = min(start + dt.timedelta(days=int(window_days) - 1), dt.date(year, 12, 31))
        out.append((start.isoformat(), end.isoformat()))
    return out


def bound(cfg: Mapping[str, Any], failed: int) -> float:
    """The noise bound for a family that has `failed` failed versions: `min_t` + `step_t` x failed."""
    return float(cfg["min_t"]) + max(0.0, float(cfg.get("step_t", 0.0))) * max(0, int(failed))


def windows_id(windows: Sequence[Sequence[str]]) -> str:
    return hashlib.sha256(json.dumps([list(w) for w in windows]).encode()).hexdigest()[:12]


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(float(value)) else None


def day_returns(trades: Iterable[Mapping[str, Any]]) -> dict[str, float]:
    """Per entry day: the day's P&L over the day's maximum loss (the Gym's `results.daily_returns`, keyed by day)."""
    pnl: dict[str, float] = {}
    risk: dict[str, float] = {}
    for t in trades or ():
        if not isinstance(t, Mapping):
            continue
        day, p, m = t.get("day"), _num(t.get("pnl")), _num(t.get("max_loss"))
        if not day or p is None or m is None:
            continue
        pnl[str(day)] = pnl.get(str(day), 0.0) + p
        risk[str(day)] = risk.get(str(day), 0.0) + m
    return {d: pnl[d] / risk[d] for d in sorted(pnl) if risk[d] > 0}


def _moments(xs: Sequence[float]) -> tuple[float, float]:
    n = len(xs)
    mean = sum(xs) / n
    var = sum((x - mean) ** 2 for x in xs) / (n - 1) if n > 1 else 0.0
    return mean, var


def compare(on: Mapping[str, float], off: Mapping[str, float], *, min_t: float = 0.5, min_on_days: int = 5,
            min_off_days: int = 5) -> dict[str, Any]:
    """The verdict of two arms' per-entry-day returns (the module docstring's statistic): {verdict, method, t, diff,
    mean_on, mean_off, n_on, n_off, ...}."""
    n_on = len(on)
    out: dict[str, Any] = {"n_on": n_on, "n_off_all": len(off), "min_t": float(min_t)}
    if n_on < int(min_on_days):
        return {**out, "verdict": "thin", "why": f"the signal arm entered on {n_on} sample days (at least {min_on_days} needed)"}
    rest = [r for d, r in off.items() if d not in on]
    shared = [d for d in on if d in off]
    if len(rest) >= int(min_off_days):
        a, b = list(on.values()), rest
        ma, va = _moments(a)
        mb, vb = _moments(b)
        se = math.sqrt(va / len(a) + vb / len(b))
        method, diff, n_off = "welch", ma - mb, len(b)
        out.update(mean_on=round(ma, 6), mean_off=round(mb, 6))
    elif len(shared) >= int(min_off_days):
        diffs = [on[d] - off[d] for d in shared]
        diff, var = _moments(diffs)
        se = math.sqrt(var / len(diffs))
        method, n_off = "paired", len(diffs)
        out.update(mean_on=round(sum(on[d] for d in shared) / len(shared), 6),
                   mean_off=round(sum(off[d] for d in shared) / len(shared), 6))
    else:
        return {**out, "verdict": "invalid_ablation",
                "why": (f"the ablation arm entered on {len(rest)} days outside the signal's and on {len(shared)} of its days: it "
                        "did not trade the comparison strategy, so nothing was compared")}
    t = diff / se if se > 0 else (math.inf if diff > 0 else -math.inf if diff < 0 else 0.0)
    passed = diff > 0 and t >= float(min_t)
    out.update(verdict="passed" if passed else "failed", method=method, n_off=n_off, diff=round(diff, 6),
               t=round(t, 3) if math.isfinite(t) else (99.0 if t > 0 else -99.0))
    if not passed:
        out["why"] = (f"the signal's entries returned {out['mean_on']:+.4f} of maximum loss a day against the comparison's "
                      f"{out['mean_off']:+.4f} ({method}, t {out['t']:+.2f}; passing needs a positive difference with t >= "
                      f"{float(min_t):g})")
    return out


def arm_summary(results: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """An arm's figures over its windows: trades, entry days, P&L, fees, statuses."""
    trades = [t for r in results for t in (r.get("trades") or []) if isinstance(t, Mapping)]
    pnl = sum(_num(t.get("pnl")) or 0.0 for t in trades)
    fees = sum(_num(t.get("fees")) or 0.0 for t in trades)
    risk = sum(_num(t.get("max_loss")) or 0.0 for t in trades)
    return {"trades": len(trades), "days_traded": len({t.get("day") for t in trades}), "pnl": round(pnl, 2),
            "fees": round(fees, 2), "pnl_per_max_loss": round(pnl / risk, 5) if risk > 0 else None,
            "statuses": sorted({str(r.get("status")) for r in results})}


def view(verdict: Mapping[str, Any], *, version: int, windows: Sequence[Sequence[str]], ablation: Mapping[str, Any],
         arms: Mapping[str, Any], stored: bool = False) -> dict[str, Any]:
    """The researcher's answer to a run whose mechanism test did not pass (the broad Train run was not made)."""
    name = verdict.get("verdict")
    status = {"failed": "mechanism_failed", "thin": "mechanism_thin", "invalid_ablation": "mechanism_invalid",
              "untestable": "mechanism_untestable"}.get(str(name), "mechanism_failed")
    nxt = {"failed": "the broad Train run was skipped: your signal did not select better entries than your card's comparison "
                     "on the sample. Change the signal (not its structure, roots or horizon) and run again, or retire the "
                     "family if its mechanism is refuted",
           "thin": "the broad Train run was skipped: the signal entered too rarely to test (Train needs 20 entry days in every "
                   "year). Make it trade more often, or pool roots",
           "invalid_ablation": f"the broad Train run was skipped: with PARAMS[{ablation.get('param')!r}] = {ablation.get('off')!r} "
                               "your program must trade the comparison strategy (skip only the signal's condition), so the "
                               "two can be compared. Fix the switch and run again",
           "untestable": "the broad Train run was skipped: the test could not run your program on the sample (see why). Fix "
                         "it and run again"}.get(str(name), "")
    out = {"status": status, "version": version, "window": "mechanism",
           "mechanism_test": {"verdict": name, "why": verdict.get("why"), "method": verdict.get("method"), "t": verdict.get("t"),
                              "min_t": verdict.get("min_t"), "signal_days": verdict.get("n_on"),
                              "comparison_days": verdict.get("n_off"), "mean_on": verdict.get("mean_on"),
                              "mean_off": verdict.get("mean_off"), "arms": dict(arms), "windows": [list(w) for w in windows],
                              "ablation": dict(ablation)},
           "next": nxt}
    if stored:
        out["already_run"] = "the stored result"
        out["next"] = "this program and params already took the mechanism test: no new run, no trial. " + nxt
    return out


__all__ = ["DEFAULTS", "MARK", "MECHANISM_CAUSE", "UNTESTABLE_CAUSE", "VERDICTS", "STATE_KEY", "config", "bound", "sample_windows",
           "windows_id", "day_returns", "compare", "arm_summary", "view"]
