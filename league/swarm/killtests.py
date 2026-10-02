"""THE TRAIN KILL TESTS (LTCM v3, Oct 2026): four pre-registered Train checks a version must pass to stand as a family's
best, as code.

WHY. The operator's agenda carried them as words for a day (v16c's item 7) and the researchers read words as advice: a
version that traded only in the latest Train years, that lived on a handful of lucky trades, or whose signal did no better
than the same structure entered without it could still become a family's best and reach Validation. Here each is a
deterministic check on Train figures (never a Validation or holdout figure), applied where Train eligibility is decided
(league/swarm/researcher.py): a TIGHTENING, so it ships as `researcher.kill_tests` (off unless JSON true).

THE TESTS (each failure is a named `why_not`, "kill test <name>: ..."):
- `coverage`: every Train year its roots have data in (the Gym's per-year `roots`; a row without them counts when it has
  days) holds at least the Train score's yearly minimum (`evidence.TRAIN_YEAR_MIN_TRADES` trades on
  `evidence.TRAIN_YEAR_MIN_DAYS` days). The Train score skips a year before 2022 in which only some of a program's roots had
  data; this does not: a program that trades only in some years is a regime, not a mechanism.
- `top_trades`: every such year is still positive after dropping its DROP_BEST best trades.
- `placebo`: the version's placebo run (its card's ablation: PARAMS[ablation.param] = ablation.off, the comparison it
  declared) is beaten in every covered year on the mean daily return on maximum loss (the validation line's unit). A flat
  card (its structure itself is the edge) has no placebo run: the comparison is not trading, so each year's mean must be
  above zero.
- `ablation`: the control ablation is worse over the whole of Train: the placebo run's P&L is below the version's (a flat
  card's: the version's P&L above zero). `placebo` asks whether the signal picks better days every year; `ablation`
  whether keeping it earns more in all.

WHERE. `own` (coverage, top_trades) reads the version's own Train result and decides its eligibility with the Train score
(`Researcher._robust_of`). `against` (placebo, ablation) needs the placebo run: the researcher queues it as a robustness run
labelled "placebo" (a flat card's is computed at once, with no run) and a failure demotes the version as a loss at 1.5x
does; the tournament validates a version only once its placebo tests passed. A family without a card has no declared
placebo: its `placebo` and `ablation` are not applicable (families born under THE MECHANISM LIBRARY all carry cards).

Standard library only.
"""

from __future__ import annotations

import math
from typing import Any, Mapping

from . import evidence

#: The best trades a year may lose and still be positive.
DROP_BEST = 5
COVERAGE, TOP_TRADES, PLACEBO, ABLATION = "coverage", "top_trades", "placebo", "ablation"
NAMES = (COVERAGE, PLACEBO, TOP_TRADES, ABLATION)
#: The robustness label of the placebo run (league/swarm/researcher.py), and its store window and purpose.
LABEL = "placebo"


def enabled(settings: Mapping[str, Any]) -> bool:
    """`researcher.kill_tests`: JSON true switches them on (a tightening; anything else is off)."""
    return (settings.get("researcher") or {}).get("kill_tests") is True


def _num(raw: Any) -> float | None:
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    return float(raw) if math.isfinite(float(raw)) else None


def covered(result: Mapping[str, Any], *, first_year: int | None) -> dict[str, dict[str, Any]]:
    """The Train years (from `first_year`) in which the program's roots had data: the Gym's per-year rows whose `roots`
    name one, or (a row without `roots`) that hold days."""
    out = {}
    for year, row in sorted(evidence.years_of(result).items()):
        if not year[:4].isdigit() or (first_year is not None and int(year[:4]) < int(first_year)):
            continue
        roots = row.get("roots")
        if (bool(roots) if isinstance(roots, list) else int(row.get("days") or 0) > 0):
            out[year] = row
    return out


def _test(ok: bool, why: str | None = None) -> dict[str, Any]:
    return {"ok": bool(ok), **({"why": why} if why else {})}


def verdict(tests: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """{passed, tests, why_not}: `why_not` names the first failed test in NAMES order ("kill test <name>: <why>")."""
    failed = [name for name in NAMES if name in tests and not tests[name].get("ok")]
    first = failed[0] if failed else None
    return {"passed": not failed, "tests": dict(tests),
            "why_not": f"kill test {first}: {tests[first].get('why') or 'failed'}" if first else None}


def own(result: Mapping[str, Any], *, first_year: int | None) -> dict[str, Any]:
    """`coverage` and `top_trades` on the version's own Train result (the module docstring)."""
    years = covered(result, first_year=first_year)
    tests: dict[str, dict[str, Any]] = {}
    if not years:
        tests[COVERAGE] = _test(False, "no Train year with data for its roots")
    else:
        short = [(y, r) for y, r in years.items() if int(r.get("trades") or 0) < evidence.TRAIN_YEAR_MIN_TRADES
                 or int(r.get("days_traded") or 0) < evidence.TRAIN_YEAR_MIN_DAYS]
        if short:
            y, r = short[0]
            tests[COVERAGE] = _test(False, f"its roots had data in {y} and it made {int(r.get('trades') or 0)} trades on "
                                           f"{int(r.get('days_traded') or 0)} days there: every Train year with data needs "
                                           f"{evidence.TRAIN_YEAR_MIN_TRADES} trades on {evidence.TRAIN_YEAR_MIN_DAYS} days")
        else:
            tests[COVERAGE] = _test(True)
    trades = [t for t in (result.get("trades") or []) if isinstance(t, Mapping) and t.get("day") and _num(t.get("pnl")) is not None]
    if not trades:
        tests[TOP_TRADES] = _test(False, "the run carries no trade list to drop the best trades from")
    else:
        for y in years:
            mine = sorted(float(t["pnl"]) for t in trades if str(t["day"]).startswith(y[:4]))
            rest = sum(mine[:-DROP_BEST]) if len(mine) > DROP_BEST else 0.0
            if rest <= 0:
                tests[TOP_TRADES] = _test(False, f"{y} is not positive without its {DROP_BEST} best trades "
                                                 f"({round(rest, 2):g} on the rest)")
                break
        else:
            tests[TOP_TRADES] = _test(True)
    return verdict(tests)


def figures(result: Mapping[str, Any], *, first_year: int | None) -> dict[str, Any]:
    """A Train result's figures the placebo tests read (Train only): each year's mean daily return on maximum loss, P&L
    and trades, and the whole P&L. Small enough to keep in a family's robustness row."""
    years = {}
    for y, r in sorted(evidence.years_of(result).items()):
        if y[:4].isdigit() and (first_year is None or int(y[:4]) >= int(first_year)):
            years[y] = {"mean": _num(r.get("mean_return_on_max_loss_daily")), "pnl": _num(r.get("pnl")),
                        "trades": int(r.get("trades") or 0)}
    total = _num((result.get("summary") or {}).get("pnl"))
    if total is None and years:
        total = round(sum(v["pnl"] or 0.0 for v in years.values()), 2)
    return {"by_year": years, "pnl": total}


def against(signal: Mapping[str, Any], placebo: Mapping[str, Any] | None, *, years: Any) -> dict[str, Any]:
    """`placebo` and `ablation` (the module docstring) from the version's `figures` and its placebo run's (None: a flat
    card, whose comparison is not trading, so every baseline is zero), over the covered `years`."""
    tests: dict[str, dict[str, Any]] = {}
    mine = signal.get("by_year") or {}
    theirs = (placebo or {}).get("by_year") or {}
    for y in sorted(years):
        s = (mine.get(y) or {}).get("mean")
        p = (theirs.get(y) or {}).get("mean") if placebo is not None else 0.0
        p = 0.0 if p is None else p  # a placebo with no trade in a year earned nothing there
        if s is None or not s > p:
            what = "zero (a flat card's comparison is not trading)" if placebo is None else f"its placebo's {round(p, 4):g}"
            tests[PLACEBO] = _test(False, f"in {y} its mean daily return on maximum loss "
                                          f"{'is missing' if s is None else f'{round(s, 4):g}'} does not beat {what}")
            break
    else:
        tests[PLACEBO] = _test(bool(years), None if years else "no covered Train year to compare")
    s_total = _num(signal.get("pnl"))
    p_total = _num((placebo or {}).get("pnl")) if placebo is not None else 0.0
    if s_total is None or p_total is None or not s_total > p_total:
        what = "zero (a flat card's comparison is not trading)" if placebo is None else f"the run without the signal's {p_total}"
        tests[ABLATION] = _test(False, f"its Train P&L {s_total} is not above {what}")
    else:
        tests[ABLATION] = _test(True)
    return verdict(tests)


def placebo_params(card: Mapping[str, Any] | None, params: Mapping[str, Any]) -> dict[str, Any] | None:
    """The placebo run's params: the version's with the card's ablation applied (`ablation.param` = `ablation.off`); None
    for a flat card (no placebo run) or no card."""
    if not card:
        return None
    ab = card.get("ablation") or {}
    if ab.get("flat") or not ab.get("param"):
        return None
    return {**dict(params or {}), str(ab["param"]): ab.get("off")}


__all__ = ["DROP_BEST", "NAMES", "COVERAGE", "TOP_TRADES", "PLACEBO", "ABLATION", "LABEL", "enabled", "covered", "verdict",
           "own", "figures", "against", "placebo_params"]
