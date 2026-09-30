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
strategy: the same structure, schedule, sizing and exits with only the signal's condition removed). A card whose
structure is not directional may declare a FLAT comparison instead (`{"flat": true}`: the structure itself is the edge, so
the comparison is not trading); the signal arm alone then runs and must earn more than nothing after the Gym's costs.

THE SAMPLE (`WINDOWS`, pre-registered: fixed here, the same for every family, never chosen per family or after a result).
Four windows of three calendar months, about 62 sessions each and 250 in all, inside 2022-2024, the Train years every Gym
image holds for every admitted root (a window where a root has no data would fail its whole batch: the Gym refuses a batch
with a root that has no day in its range). Together they cover every calendar month once, all four quarter-ends with
their quarterly expiries, a year-end and the Russell reconstitution, in three regimes: February-April 2022 (the first
hikes and the war shock), May-July 2023, November 2023-January 2024 (year-end) and August-October 2024 (the August
volatility spike). Each window is one unsplit `window="train"` job per arm with its own start and end, so every family's
arms of one window share a batch. An entry is COUNTED only when its expected hold fits inside its window (`TAIL_DAYS`:
the card's holding bucket's calendar days before the window's end: 0 intraday, 5, 14 and 30 for longer holds), so a hold
the window's end cuts short never enters the statistic; the sample is about 250 counted sessions, about 165 for holds of
more than ten sessions.

STAGES. The first window runs first. When its signal arm errs the test is untestable; when its ablation arm errs, or makes
no trade while the signal arm trades (a comparison enters wherever the signal would), the ablation is invalid; either way
the other three windows never run (half of Sept 30's placebo rows never traded).

THE STATISTIC. Each arm's per-entry-day return on maximum loss (the validation line's own unit: a day's P&L over the
day's maximum loss, trades grouped by entry day). The question is whether conditioning on the signal selects better
entries than the comparison does, not whether trading less loses less, so per-day totals are never compared:
- WELCH (the usual case): the signal arm's entry days against the ablation arm's entry days on which the signal arm did
  not enter (disjoint samples: the comparison strategy's own days). t = (mean_on - mean_off) / sqrt(var_on/n_on +
  var_off/n_off).
- PAIRED (when the ablation enters only on the signal's days: the signal changes what is bought, not when): the mean of
  the per-day differences over the shared days, over its standard error. Identical arms (every difference zero) are an
  invalid ablation, never a finding: the switch changed nothing.
- FLAT: the signal arm's entry days against zero (one-sample t).
PASSED needs a positive difference with t >= the bound.

THE ABLATION AUDIT (`audit`). The comparison is written by the researcher being tested, so a deliberately weak one would
make any signal pass. Before the statistic, both arms' trades are profiled (structure types, median days to expiry, median
moneyness, median width, median entry minute, median sessions held) and an ablation whose trades are another structure,
tenor, strike band, width, entry time or hold than the signal's is invalid. The tolerances are loose on purpose: a signal
may shift its strikes or timing a little; the audit catches a comparison that trades something else. Both profiles are
recorded with the verdict.

THE NOISE BOUND. `min_t` (0.75) on a hypothesis's first test, rising by `step_t` (0.25) for each failed test of the same
hypothesis before it: failed tests of every family of the lineage set (`store.lineages`: forks, parent-named revisions and
rebirths that join or count the lineage) whose card sits in the same cell (mechanism class, structure family, holding). A
retry is another look at the same question, so a signal with no information cannot walk through on retries, and a fork
or rebirth never resets the count; an unrelated idea in the lineage (another cell) does not raise it. Set by a fixed-seed
simulation (league/tests/test_swarm_mechanism.py, `Benchmark`) at the eligibility floor's frequency with no cost drag (the
hardest case for a real signal), against this module's first design (125 sample days, bounds 0.5, 1.0 and 1.5):

    passes (share of tests)                        first design   this sample (250 days)   holds > 10 sessions (165)
    no information, first test                     32%            25%                      24%
    no information, within three tries             48%            47%                      44%
    t 2 a year (the validation line), first test   79%            87%                      79%
    t 2 a year as a third version, after two       43%            73%                      60%
      failed versions of the same hypothesis

Fewer false passes and fewer missed signals in every case. The owner's thresholds bind eligibility and scoring; this
is a screen before Train, and it ships in SHADOW mode (below) until measured House evidence says it may gate.

MODES (`researcher.mechanism_test.mode`). "shadow" (the default): a carded family's first broad replay is preceded by one
test; its verdict is recorded on the card, charged to the lineage and told to the researcher, and the broad run goes ahead
whatever it says, so the verdict can be checked against the family's Train outcome (`calibration` of
`calibration_rows(store)`) before it is allowed to stop anything. "gate": a carded family's broad replay (at any stress) and its sweeps wait until its hypothesis has
passed (any family of its lineage with the same card, or broad Train runs of such a family: the test gates the first
broad replay only, never a re-test after a Gym change); `max_failures` tests of the hypothesis that failed below the BASE
bound (`min_t`: a test failed only by a raised bound is never a finding) retire the family with the MECHANISM verdict,
and `max_untestable` untestable versions retire it with the idle rule's words. `enabled` false (or `mechanism_test:
false`) switches it off. The gate is switched on only when `calibration` over shadow verdicts shows that the families it
would have stopped rarely reached an eligible Train version (the missed-signal rate), and that a test costs well under
the broad replay it would save (the cycle events' `box_seconds` against `gym_box_seconds`).

VERDICTS. `passed`; `failed` (the signal did not beat its comparison beyond the bound: an economic finding about this
program); `thin` (the signal arm entered on fewer than `min_on_days` counted days); `invalid_ablation` (the ablation arm
did not trade the comparison: it erred, made no trade, changed nothing or failed the audit); `untestable` (the program
erred, had no data or could not take the test). Every Gym evaluation is a trial of the lineage, recorded as a
`window="mechanism"` run row (never read by the Train score, the best or the drift screen), stored trimmed (`trim`: the
fields the test reads, not the full result). The researcher (league/swarm/researcher.py) runs it, answers from the store
when the same test was made, records the verdict on the card (`cards.add_evidence`) and in the family's state.

THE CARD'S COST HURDLE is the architect's estimate, shown to the researcher and recorded beside each verdict
(`hurdle`, and `net_positive`: whether the signal's entries earned more than nothing): the Gym's fills already charge the
spread and fees, so the test never subtracts it again.

Standard library only.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import re
import statistics
from typing import Any, Iterable, Mapping, Sequence

#: The settings' defaults (`researcher.mechanism_test`).
DEFAULTS: dict[str, Any] = {
    "enabled": True,
    "mode": "shadow",
    "min_t": 0.75,
    "step_t": 0.25,
    "min_on_days": 10,
    "min_off_days": 10,
    "max_failures": 3,
    "max_untestable": 4,
    "timeout_seconds": 900,
}
MODES = ("shadow", "gate")
#: The pre-registered sample (the module docstring): four windows of three calendar months inside 2022-2024.
WINDOWS: tuple[tuple[str, str], ...] = (("2022-02-01", "2022-04-30"), ("2023-05-01", "2023-07-31"),
                                        ("2023-11-01", "2024-01-31"), ("2024-08-01", "2024-10-31"))
#: Calendar days before a window's end after which an entry is not counted, by the card's holding bucket.
TAIL_DAYS = {"intraday": 0, "days_1_3": 5, "days_4_10": 14, "days_11_plus": 30}
#: A retirement reason's mark for a failed mechanism (architect.tag_of reads it as MECHANISM).
MARK = "Mechanism verdict MECHANISM"
#: Its first sentence (no figure, no colon) is the one the site may publish (`public.note_text`); the mark and the count follow.
MECHANISM_CAUSE = ("Retired after its signal failed the pre-registered mechanism tests against the comparison its card declared. "
                   f"{MARK}, a tested finding: {{n}} tests of its hypothesis did not beat that comparison beyond the noise "
                   "bound; this does not establish that every related mechanism lacks an edge")
#: A family whose programs never made a testable comparison: untested, so it keeps the idle rule's words (IDLE).
UNTESTABLE_CAUSE = ("Retired because its mechanism tests could not compare its signal with the comparison its card declared. "
                    "It made {n} such tests (an ablation that did not trade, too few signal days, errors or no data); it is a "
                    "time limit, not a finding that the mechanism has no edge")
VERDICTS = ("passed", "failed", "thin", "invalid_ablation", "untestable")
#: The state key the researcher keeps a family's test record under.
STATE_KEY = "mechanism"
#: A pool failure that says the Gym holds no data for the job's roots and range: that window has no data (never a Gym
#: error asked again every cycle).
MISSING_DATA = re.compile(r"missing data|has no \w+ data", re.I)
#: The audit's tolerances (the module docstring): an ablation is invalid past any of them.
AUDIT = {"dte_days": 3, "dte_share": 0.5, "moneyness": 0.02, "width": 0.02, "minutes": 60, "sessions": 2, "sessions_share": 1.0}


def config(settings: Mapping[str, Any] | None) -> dict[str, Any]:
    """`researcher.mechanism_test` over DEFAULTS; a bad value falls back to its default."""
    raw = ((settings or {}).get("researcher") or {}).get("mechanism_test")
    out = dict(DEFAULTS)
    if isinstance(raw, Mapping):
        for k, default in DEFAULTS.items():
            v = raw.get(k, default)
            if isinstance(default, bool):
                out[k] = v if isinstance(v, bool) else default
            elif isinstance(default, str):
                out[k] = str(v).lower() if str(v).lower() in MODES else default
            elif isinstance(v, bool) or not isinstance(v, (int, float)) or v != v or abs(v) == float("inf"):
                out[k] = default
            else:
                out[k] = type(default)(v) if not isinstance(default, float) else float(v)
    elif raw is False:
        out["enabled"] = False
    return out


def sample_windows() -> list[tuple[str, str]]:
    """The pre-registered sample (`WINDOWS`)."""
    return [tuple(w) for w in WINDOWS]  # type: ignore[misc]


def counted_until(end: str, holding: Any) -> str:
    """The last entry day a window counts for a card's holding bucket (`TAIL_DAYS`)."""
    tail = TAIL_DAYS.get(str(holding), TAIL_DAYS["days_11_plus"])
    return (dt.date.fromisoformat(end) - dt.timedelta(days=tail)).isoformat()


def counted(trades: Iterable[Mapping[str, Any]], start: str, end: str, holding: Any) -> list[Mapping[str, Any]]:
    """The trades of one window whose entry day it counts (inside the window, a hold that fits)."""
    last = counted_until(end, holding)
    return [t for t in trades or () if isinstance(t, Mapping) and start <= str(t.get("day") or "") <= last]


def bound(cfg: Mapping[str, Any], failed: int) -> float:
    """The noise bound after `failed` failed tests of the same hypothesis: `min_t` + `step_t` x failed."""
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


def _t(diff: float, se: float) -> float:
    return diff / se if se > 0 else (math.inf if diff > 0 else -math.inf if diff < 0 else 0.0)


def _finish(out: dict[str, Any], *, diff: float, t: float, min_t: float, method: str, what: str) -> dict[str, Any]:
    passed = diff > 0 and t >= float(min_t)
    out.update(verdict="passed" if passed else "failed", method=method, diff=round(diff, 6),
               t=round(t, 3) if math.isfinite(t) else (99.0 if t > 0 else -99.0))
    if not passed:
        out["why"] = (f"the signal's entries returned {out['mean_on']:+.4f} of maximum loss a day against {what} "
                      f"{out['mean_off']:+.4f} ({method}, t {out['t']:+.2f}; passing needs a positive difference with t >= "
                      f"{float(min_t):g})")
    return out


def compare(on: Mapping[str, float], off: Mapping[str, float], *, min_t: float = 0.75, min_on_days: int = 10,
            min_off_days: int = 10) -> dict[str, Any]:
    """The verdict of two arms' per-entry-day returns (the module docstring's statistic): {verdict, method, t, diff,
    mean_on, mean_off, n_on, n_off, ...}."""
    n_on = len(on)
    out: dict[str, Any] = {"n_on": n_on, "n_off_all": len(off), "min_t": float(min_t)}
    if n_on < int(min_on_days):
        return {**out, "verdict": "thin", "why": f"the signal arm entered on {n_on} counted sample days (at least {min_on_days} needed)"}
    rest = [r for d, r in off.items() if d not in on]
    shared = [d for d in on if d in off]
    if len(rest) >= int(min_off_days):
        a, b = list(on.values()), rest
        ma, va = _moments(a)
        mb, vb = _moments(b)
        out.update(mean_on=round(ma, 6), mean_off=round(mb, 6), n_off=len(b))
        return _finish(out, diff=ma - mb, t=_t(ma - mb, math.sqrt(va / len(a) + vb / len(b))), min_t=min_t, method="welch",
                       what="the comparison's")
    if len(shared) >= int(min_off_days):
        diffs = [on[d] - off[d] for d in shared]
        if all(abs(x) < 1e-12 for x in diffs):
            return {**out, "verdict": "invalid_ablation",
                    "why": ("the ablation arm made the signal arm's trades exactly: the switch changed nothing, so nothing was "
                            "compared (a card whose structure is the edge declares a flat comparison)")}
        diff, var = _moments(diffs)
        out.update(mean_on=round(sum(on[d] for d in shared) / len(shared), 6),
                   mean_off=round(sum(off[d] for d in shared) / len(shared), 6), n_off=len(diffs))
        return _finish(out, diff=diff, t=_t(diff, math.sqrt(var / len(diffs))), min_t=min_t, method="paired",
                       what="the comparison's")
    return {**out, "verdict": "invalid_ablation",
            "why": (f"the ablation arm entered on {len(rest)} counted days outside the signal's and on {len(shared)} of its "
                    "days: it did not trade the comparison strategy, so nothing was compared")}


def compare_flat(on: Mapping[str, float], *, min_t: float = 0.75, min_on_days: int = 10) -> dict[str, Any]:
    """A FLAT comparison's verdict: the signal arm's per-entry-day returns against zero (one-sample t)."""
    n_on = len(on)
    out: dict[str, Any] = {"n_on": n_on, "n_off_all": 0, "min_t": float(min_t)}
    if n_on < int(min_on_days):
        return {**out, "verdict": "thin", "why": f"the signal arm entered on {n_on} counted sample days (at least {min_on_days} needed)"}
    mean, var = _moments(list(on.values()))
    out.update(mean_on=round(mean, 6), mean_off=0.0, n_off=0)
    return _finish(out, diff=mean, t=_t(mean, math.sqrt(var / n_on)), min_t=min_t, method="flat", what="not trading's")


def _median(xs: Sequence[float]) -> float | None:
    xs = [x for x in xs if x is not None and math.isfinite(x)]
    return float(statistics.median(xs)) if xs else None


def profile(trades: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """An arm's trade profile for the audit: its structure types and the medians of days to expiry, moneyness, width
    (the legs' strike span over the spot), entry minute and sessions held. Reads a full or a trimmed trade."""
    rows = [t for t in trades or () if isinstance(t, Mapping)]

    def ctx(t: Mapping[str, Any], name: str) -> Any:
        return t.get(name) if name in t else (t.get("context") or {}).get(name)

    def width(t: Mapping[str, Any]) -> float | None:
        if "width" in t:
            return _num(t.get("width"))
        strikes = [_num(leg.get("strike")) for leg in t.get("legs") or [] if isinstance(leg, Mapping)]
        spot = _num(ctx(t, "spot"))
        strikes = [s for s in strikes if s is not None]
        return (max(strikes) - min(strikes)) / spot if strikes and spot else None

    out = {"trades": len(rows), "types": sorted({str(t.get("type")) for t in rows if t.get("type")}),
           "dte": _median([_num(ctx(t, "dte")) for t in rows]), "moneyness": _median([_num(ctx(t, "moneyness")) for t in rows]),
           "width": _median([width(t) for t in rows]), "minute": _median([_num(t.get("entry_minute")) for t in rows]),
           "sessions": _median([_num(t.get("sessions_held")) for t in rows])}
    return {k: (round(v, 5) if isinstance(v, float) else v) for k, v in out.items()}


def audit(on: Mapping[str, Any], off: Mapping[str, Any]) -> str | None:
    """Why the ablation arm's profile is not the signal's comparison (another structure, tenor, strike band, width, entry
    time or hold: `AUDIT`'s tolerances), or None. Figures missing on either side are not judged."""
    if not on.get("trades") or not off.get("trades"):
        return None
    extra = sorted(set(on.get("types") or []) - set(off.get("types") or []))
    if extra:
        return f"it never traded the signal's structure ({', '.join(extra)}; it traded {', '.join(off.get('types') or [])})"

    def far(name: str, limit: float) -> bool:
        a, b = on.get(name), off.get(name)
        return a is not None and b is not None and abs(float(a) - float(b)) > limit

    dte_on = on.get("dte")
    if dte_on is not None and far("dte", max(AUDIT["dte_days"], AUDIT["dte_share"] * abs(float(dte_on)))):
        return f"its median days to expiry {off['dte']:g} is not the signal's {dte_on:g}"
    if far("moneyness", AUDIT["moneyness"]):
        return f"its median moneyness {off['moneyness']:+.3f} is not the signal's {on['moneyness']:+.3f}"
    if far("width", AUDIT["width"]):
        return f"its median width {off['width']:.3f} of spot is not the signal's {on['width']:.3f}"
    if far("minute", AUDIT["minutes"]):
        return f"its median entry minute {off['minute']:g} is not the signal's {on['minute']:g}"
    held = on.get("sessions")
    if held is not None and far("sessions", AUDIT["sessions"] + AUDIT["sessions_share"] * abs(float(held))):
        return f"its median hold of {off['sessions']:g} sessions is not the signal's {held:g}"
    return None


def trim(result: Mapping[str, Any]) -> dict[str, Any]:
    """The part of an arm's result the test keeps (its run row's file): identity, status, trials, summary, the runtime's
    first messages, and each trade's day, P&L, maximum loss, fees and profile fields. The full result is never stored."""
    keep = ("run_id", "status", "reason", "trials", "gym_image", "gym_bundle", "fill_model", "train_from", "roots", "program")
    out: dict[str, Any] = {k: result[k] for k in keep if k in result}
    out["summary"] = dict(result.get("summary") or {})
    messages = ((result.get("runtime") or {}).get("messages") or [])[:4]
    if messages:
        out["runtime"] = {"messages": [str(m)[:300] for m in messages]}
    rows = []
    for t in result.get("trades") or []:
        if not isinstance(t, Mapping):
            continue
        p = profile([t])
        rows.append({"day": t.get("day"), "pnl": t.get("pnl"), "max_loss": t.get("max_loss"), "fees": t.get("fees"),
                     "type": t.get("type"), "entry_minute": t.get("entry_minute"), "sessions_held": t.get("sessions_held"),
                     "dte": p["dte"], "moneyness": p["moneyness"], "width": p["width"]})
    out["trades"] = rows
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


def calibration(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """The shadow evidence the gate is switched on by (the module docstring's MODES): `rows` of {verdict, eligible} (a
    family's first test and whether any of its Train runs was eligible). Per verdict: families and how many reached an
    eligible Train version; `missed` = the eligible families whose test failed (what the gate would have stopped), over
    all eligible tested families; `blocked` = the families the gate would have stopped, over all tested."""
    by: dict[str, dict[str, int]] = {}
    for r in rows:
        v = str(r.get("verdict"))
        cell = by.setdefault(v, {"families": 0, "eligible": 0})
        cell["families"] += 1
        cell["eligible"] += bool(r.get("eligible"))
    tested = sum(c["families"] for c in by.values())
    eligible = sum(c["eligible"] for c in by.values())
    stopped = {k: c for k, c in by.items() if k != "passed"}
    return {"by_verdict": by, "tested": tested, "eligible": eligible,
            "missed": round(sum(c["eligible"] for c in stopped.values()) / eligible, 4) if eligible else None,
            "blocked": round(sum(c["families"] for c in stopped.values()) / tested, 4) if tested else None}


def calibration_rows(store: Any) -> list[dict[str, Any]]:
    """`calibration`'s rows from a store (read-only): each tested family's FIRST mechanism verdict and whether any of its
    broad Train runs was eligible, for the families whose outcome is known (retired, or already eligible): a family still
    researching could yet become eligible."""
    try:
        first = store._all("SELECT family, verdict, MIN(seq) AS seq FROM card_evidence WHERE kind='mechanism_test' GROUP BY family")
    except Exception:  # noqa: BLE001 - no card tables yet
        return []
    eligible = {r["family"] for r in store._all("SELECT DISTINCT family FROM runs WHERE window='train' AND purpose='train' "
                                                "AND json_extract(summary, '$.train_eligible') = 1")}
    retired = {r["id"] for r in store._all("SELECT id FROM families WHERE retired_at IS NOT NULL")}
    return [{"family": r["family"], "verdict": r["verdict"], "eligible": r["family"] in eligible} for r in first
            if r["family"] in retired or r["family"] in eligible]


def view(verdict: Mapping[str, Any], *, version: int, windows: Sequence[Sequence[str]], ablation: Mapping[str, Any],
         arms: Mapping[str, Any], stored: bool = False) -> dict[str, Any]:
    """The researcher's answer to a run whose mechanism test did not pass (the broad Train run was not made: gate mode)."""
    name = verdict.get("verdict")
    status = {"failed": "mechanism_failed", "thin": "mechanism_thin", "invalid_ablation": "mechanism_invalid",
              "untestable": "mechanism_untestable"}.get(str(name), "mechanism_failed")
    switch = "your flat comparison" if ablation.get("flat") else f"PARAMS[{ablation.get('param')!r}] = {ablation.get('off')!r}"
    nxt = {"failed": "the broad Train run was skipped: your signal did not select better entries than your card's comparison "
                     "on the sample. Change the signal (not its structure, roots or horizon) and run again, or retire the "
                     "family if its mechanism is refuted",
           "thin": "the broad Train run was skipped: the signal entered too rarely to test (Train needs 20 entry days in every "
                   "year). Make it trade more often, or pool roots",
           "invalid_ablation": f"the broad Train run was skipped: with {switch} your program must trade the comparison "
                               "strategy (skip only the signal's condition: the same structure, tenor, strikes, entry time and "
                               "exits), so the two can be compared. Fix the switch and run again",
           "untestable": "the broad Train run was skipped: the test could not run your program on the sample (see why). Fix "
                         "it and run again"}.get(str(name), "")
    out = {"status": status, "version": version, "window": "mechanism", "mechanism_test": view_block(verdict, windows, ablation, arms),
           "next": nxt}
    if stored:
        out["already_run"] = "the stored result"
        out["next"] = "this program and params already took the mechanism test: no new run, no trial. " + nxt
    return out


def view_block(verdict: Mapping[str, Any], windows: Sequence[Sequence[str]], ablation: Mapping[str, Any],
               arms: Mapping[str, Any]) -> dict[str, Any]:
    """The verdict as the researcher reads it (a gate's refusal, or beside a shadow run's broad result)."""
    return {"verdict": verdict.get("verdict"), "why": verdict.get("why"), "method": verdict.get("method"), "t": verdict.get("t"),
            "min_t": verdict.get("min_t"), "signal_days": verdict.get("n_on"), "comparison_days": verdict.get("n_off"),
            "mean_on": verdict.get("mean_on"), "mean_off": verdict.get("mean_off"), "hurdle": verdict.get("hurdle"),
            "net_positive": verdict.get("net_positive"), "audit": verdict.get("audit"), "arms": dict(arms),
            "windows": [list(w) for w in windows], "ablation": dict(ablation)}


__all__ = ["DEFAULTS", "MODES", "WINDOWS", "TAIL_DAYS", "MARK", "MECHANISM_CAUSE", "UNTESTABLE_CAUSE", "VERDICTS", "STATE_KEY",
           "MISSING_DATA", "AUDIT", "config", "bound", "sample_windows", "counted_until", "counted", "windows_id", "day_returns",
           "compare", "compare_flat", "profile", "audit", "trim", "arm_summary", "calibration", "calibration_rows", "view",
           "view_block"]
