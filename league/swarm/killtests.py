"""THE TRAIN KILL TESTS (LTCM v3, Oct 2026): four pre-registered Train checks a version must pass to stand as a family's
best, as code.

WHY. The operator's agenda carried them as words for a day (v16c's item 7) and the researchers read words as advice: a
version that traded only in the latest Train years, that lived on a handful of lucky trades, or whose signal did no better
than the same structure entered without it could still become a family's best and reach Validation. Here each is a
deterministic check on Train figures (never a Validation or holdout figure), applied where Train eligibility is decided
(league/swarm/researcher.py): a TIGHTENING, so it ships as `researcher.kill_tests` (off unless JSON true).

THE TESTS (each failure is a named `why_not`, "kill test <name>: ..."):
- `coverage`: every Train year its roots have data in holds at least the Train score's yearly minimum
  (`evidence.TRAIN_YEAR_MIN_TRADES` trades on `evidence.TRAIN_YEAR_MIN_DAYS` days). The years are the Train score's own
  (`evidence.scored_years`: a year before 2022 counts only when every root the program needs had data, since a name has
  no 2020-21 chains and a mixed-root program cannot compute its signal there), each with data for its roots (the Gym's
  per-year `roots`; a row without them counts when it has days): a program that trades only in some of them is a regime,
  not a mechanism.
- `top_trades`: every such year is still positive after dropping its DROP_BEST best trades.
- `placebo`: the version's placebo run (its card's ablation: PARAMS[ablation.param] = ablation.off, the comparison it
  declared) is beaten in every covered year on the mean daily return on maximum loss (the validation line's unit). The
  placebo must be a comparison: in a covered year where the version traded it must trade too (an ablation that turns the
  program off compares the signal with nothing; mechanism.py found half of Sept 30's placebo rows made no trade), and its
  trades must be the signal's structure, tenor, strikes, width and hold (`mechanism.audit` on the two trade profiles: a
  deliberately weak off arm would make any signal pass). A flat card (its structure itself is the edge) has no placebo
  run: the comparison is not trading, so each year's mean must be above zero.
- `ablation`: the control ablation is worse over the whole of Train: the placebo run's P&L is below the version's (a flat
  card's: the version's P&L above zero). `placebo` asks whether the signal picks better days every year; `ablation`
  whether keeping it earns more in all.

WHERE. `own` (coverage, top_trades) reads the version's own Train result and decides its eligibility with the Train score
(`Researcher._robust_of`; the row's summary records `train_kill`, so a row scored before the switch is known and scored
again). The family's best is also judged as a robustness label "own" (`OWN`: from its kept Train result at once, else its
Train run made again), so a best chosen before the switch is held to them too. `against` (placebo, ablation) needs the
placebo run: the researcher queues it as a robustness run labelled "placebo" (a flat card's is computed at once, with no
run), compares it with the figures and trade profile the "own" verdict keeps (so the version's full result may be pruned
meanwhile), and a failure demotes the version as a loss at 1.5x does; the tournament validates a version only once both passed
(`researcher.kill_tests_passed`). The placebo run is kept as a small record (`compact`: no trade list or daily series),
its row's run_id scoped apart from Train rows (`scoped_id`). A family without a card has no declared placebo: its
`placebo` and `ablation` are not applicable (families born under THE MECHANISM LIBRARY all carry cards).

Standard library only.
"""

from __future__ import annotations

import math
from typing import Any, Mapping

from . import evidence, mechanism

#: The best trades a year may lose and still be positive.
DROP_BEST = 5
COVERAGE, TOP_TRADES, PLACEBO, ABLATION = "coverage", "top_trades", "placebo", "ablation"
NAMES = (COVERAGE, PLACEBO, TOP_TRADES, ABLATION)
#: The robustness label of the placebo run (league/swarm/researcher.py), and its store window and purpose.
LABEL = "placebo"
#: The robustness label of the version's own tests (coverage, top_trades) on the family's best.
OWN = "own"


def enabled(settings: Mapping[str, Any]) -> bool:
    """`researcher.kill_tests`: JSON true switches them on (a tightening; anything else is off)."""
    return (settings.get("researcher") or {}).get("kill_tests") is True


def _num(raw: Any) -> float | None:
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    return float(raw) if math.isfinite(float(raw)) else None


def covered(result: Mapping[str, Any], *, first_year: int | None) -> dict[str, dict[str, Any]]:
    """The Train years (from `first_year`) the Train score judges (`evidence.scored_years`: a pre-2022 year only when every
    root the program needs had data) in which the program's roots had data: the Gym's per-year rows whose `roots` name
    one, or (a row without `roots`) that hold days."""
    out = {}
    for year, row in sorted(evidence.scored_years(result, first_year=first_year).items()):
        if not year[:4].isdigit():
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


def against(signal: Mapping[str, Any], placebo: Mapping[str, Any] | None, *, years: Any,
            mismatch: str | None = None) -> dict[str, Any]:
    """`placebo` and `ablation` (the module docstring) from the version's `figures` and its placebo run's (None: a flat
    card, whose comparison is not trading, so every baseline is zero), over the covered `years`. `mismatch` (`comparison`)
    is why the placebo's trades are not the signal's comparison, which fails `placebo` outright; so does a placebo that
    makes no trade in a covered year the version traded in."""
    tests: dict[str, dict[str, Any]] = {}
    mine = signal.get("by_year") or {}
    theirs = (placebo or {}).get("by_year") or {}
    if placebo is not None and mismatch:
        tests[PLACEBO] = _test(False, f"its placebo is not the signal's comparison: {mismatch}")
    for y in sorted(years) if PLACEBO not in tests else ():
        s = (mine.get(y) or {}).get("mean")
        if placebo is not None and int((mine.get(y) or {}).get("trades") or 0) > 0 and \
                not int((theirs.get(y) or {}).get("trades") or 0) > 0:
            tests[PLACEBO] = _test(False, f"in {y} its placebo made no trade: the ablation turns the program off, so there is "
                                          "nothing to compare (the off arm must trade the same structure without the signal)")
            break
        p = (theirs.get(y) or {}).get("mean") if placebo is not None else 0.0
        p = 0.0 if p is None else p
        if s is None or not s > p:
            what = "zero (a flat card's comparison is not trading)" if placebo is None else f"its placebo's {round(p, 4):g}"
            tests[PLACEBO] = _test(False, f"in {y} its mean daily return on maximum loss "
                                          f"{'is missing' if s is None else f'{round(s, 4):g}'} does not beat {what}")
            break
    else:
        if PLACEBO not in tests:
            tests[PLACEBO] = _test(bool(years), None if years else "no covered Train year to compare")
    s_total = _num(signal.get("pnl"))
    p_total = _num((placebo or {}).get("pnl")) if placebo is not None else 0.0
    if s_total is None or p_total is None or not s_total > p_total:
        what = "zero (a flat card's comparison is not trading)" if placebo is None else f"the run without the signal's {p_total}"
        tests[ABLATION] = _test(False, f"its Train P&L {s_total} is not above {what}")
    else:
        tests[ABLATION] = _test(True)
    return verdict(tests)


def profile(result: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """A Train result's trade profile (`mechanism.profile`: structure types and the medians of tenor, moneyness, width,
    entry minute and hold), kept beside the placebo's figures; None without a trade list."""
    trades = (result or {}).get("trades")
    return mechanism.profile(trades) if isinstance(trades, list) and trades else None


def comparison(signal_profile: Mapping[str, Any] | None, placebo_profile: Mapping[str, Any] | None,
               card: Mapping[str, Any] | None) -> str | None:
    """Why the placebo's trades are not the signal's comparison (`mechanism.audit`: another structure, tenor, strike band,
    width, entry time or hold; a time-of-day card skips the clock checks, `mechanism.clock_skips`), or None. Both are
    `profile`s: the version's Train result's and the placebo run's."""
    if not signal_profile or not placebo_profile:
        return None
    return mechanism.audit(signal_profile, placebo_profile, skip=mechanism.clock_skips(card or {}))


#: What `compact` keeps of a placebo run: identity, status and the figures the tests read. Never its trades or daily series.
COMPACT_KEYS = ("run_id", "status", "reason", "trials", "gym_image", "gym_bundle", "fill_model", "train_from", "roots", "needs",
                "program")


def compact(result: Mapping[str, Any]) -> dict[str, Any]:
    """The placebo run as its store row's file keeps it: identity, status, summary and per-year rows (the figures are also
    in the family's robustness row). A full Train result is ~100-400 KB compressed; this is a few KB, and the store never
    prunes the placebo window."""
    out: dict[str, Any] = {k: result[k] for k in COMPACT_KEYS if k in result}
    out["summary"] = dict(result.get("summary") or {})
    years = evidence.years_of(result)
    if years:
        out["by_year"] = years
    return out


def scoped_id(run_id: Any) -> str | None:
    """The placebo row's run_id: the Gym's (a hash of code, params, roots and settings, shared with a Train row of the same
    program and params) scoped apart, so the store never answers a Train run with the placebo's row or the reverse."""
    return f"{str(run_id)[:40]}-{LABEL}" if run_id else None


def placebo_params(card: Mapping[str, Any] | None, params: Mapping[str, Any]) -> dict[str, Any] | None:
    """The placebo run's params: the version's with the card's ablation applied (`ablation.param` = `ablation.off`); None
    for a flat card (no placebo run) or no card."""
    if not card:
        return None
    ab = card.get("ablation") or {}
    if ab.get("flat") or not ab.get("param"):
        return None
    return {**dict(params or {}), str(ab["param"]): ab.get("off")}


__all__ = ["DROP_BEST", "NAMES", "COVERAGE", "TOP_TRADES", "PLACEBO", "ABLATION", "LABEL", "OWN", "enabled", "covered",
           "verdict", "own", "figures", "against", "profile", "comparison", "compact", "scoped_id", "placebo_params"]
