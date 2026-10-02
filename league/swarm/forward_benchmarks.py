"""THE FORWARD LADDER'S BENCHMARK (evidence v3; the plan's Phase 3.3): the ladder's rules and the sealed-look design they
replace, judged on the SAME synthetic worlds before the ladder binds.

    python -m league.swarm.forward_benchmarks --json [--replications R] [--world W ...] [--output FULL.json]
    python -m league.swarm.forward_benchmarks --combine PART.json ... [--output FULL.json] [--report REPORT.md]

THE WORLDS (`WORLDS`, pinned before the first run): each is one kind of program, played as a whole desk of entrants.
A program's trades are generated per session from its world: a Poisson number of closes a session, each closed the day
it opened, its P&L = the maximum loss x (its world's net edge + its noise) + its entry delta x the underlying's move
that session (one market path per replication and period, common to every program of the desk). Negatives:

- `absent`, `absent_sparse`, `absent_fat`: no edge after costs (Gaussian; sparse; Student-t with 3 degrees of freedom);
- `skewed_null`: a premium seller with no edge: 90% small wins, 10% large losses, mean zero (the steamroller);
- `cost_erased`: an edge in the Gym's cost model (Validation and the holdout) that live costs erase (forward);
- `drift_only`: no edge but a long delta in a drifting (bull) market: its P&L is the market's drift, in every period;
- `fading`: an edge in Validation and the holdout that is gone forward (decayed, or the holdout memorized).

Positives (planted, deliberately strong controls): `planted_dense`, `planted_sparse`, `planted_premium` (a skewed premium
seller with a real edge), and `planted_directional` (a TIMING edge: its delta's side matches the session's move more
often than not; THE DRIFT CONTROL removes it by design, so this world measures what that control costs). `mixed`: a
desk drawing every world with equal weight.

THE TWO DESIGNS, on the same entrants in the same order:

- THE LADDER (`league/live/ladder.py`, the exact functions the House runs: `judge`, `benjamini_hochberg`, `Rules` from
  the constitution, rows in the practice ledger's shape): `slots` cohorts practise at once; each judged at every
  session's end on its forward record; a cohort that first meets L1-L5 asks for the pre-filter, which answers by the
  next session's end, when it is promoted if every line still holds and its holdout P&L is not negative (a negative
  read fails it); a cohort ends promoted, failed or at its window; a freed slot takes the next entrant.
- THE SEALED LOOK (the design the ladder replaces): the entrant's Validation year through `evidence.validation_line`
  (with its 1.5x stress twin), then THE LOOK HOLDS as the gate runs them (the drift hold on the Validation year's own
  drift fit; the power hold at the Holm level), then one holdout look through `evidence.holdout_line` with Holm across
  every look of the desk after a fixed prior history, and the leakage alarm (10 looks, more than 30% passing, stops the
  gate). `sealed_bare` is the same without the holds. The holdout line's moving-block bootstrap is replaced, for speed,
  by a numpy port of `evidence.block_bootstrap` (the same blocks and draws; another random stream: its p differs from the
  original's only by Monte Carlo error, `bootstrap_agreement`).

A FALSE PROMOTION is a negative entrant promoted; a MISSED SIGNAL a positive entrant not promoted. Rates carry exact
(Clopper-Pearson) 95% bounds. Only the entrants whose ladder judgement ended within the desk's sessions (promoted,
failed, or at the end of their window) are counted, for both designs. THE BINDING RULE (pre-registered): `binding` is true only when the ladder's false promotions are at or below the
sealed design's (with its holds, the stricter of the two) both over every negative entrant of the single-world desks
and over the negative entrants of the mixed desks. Per-world counts are reported beside them.

What it is not: a market simulation. Returns are not bounded by the maximum loss, trades close the session they open,
Train is not simulated (both designs start from the same Train-eligible programs), the Gym's drift screen upstream of
both is not modelled, and the variants (`VARIANTS`) are judged on the primary rule's desk (their promotions do not free
slots). It never reads market data, places an order or writes outside its output files.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import hashlib
import json
import math
import sys
import time
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

SUITE_ID = "forward-suite-1"

PROTOCOL: dict[str, Any] = {
    "id": SUITE_ID,
    "replications": 30,
    "slots": 16,                     # cohorts practising at once (the practice league's width)
    "sessions": 160,                 # forward sessions a desk runs
    "first_session": "2026-10-05",   # the forward period's first session (real NYSE sessions from it)
    "validation_year": 2025,
    "holdout_first": "2026-01-02",
    "holdout_sessions": 185,
    "prior_holdout_ps": [0.5, 0.5],  # the evaluator suite's fixed prior history of two failed looks
    "max_loss": 100.0,
    "spot": 500.0,
    "annual_vol": 0.16,
    "market_drift": 0.08,
    "capital": 10_000.0,
    "confidence": 0.95,
}

#: Each world's program (fractions of the maximum loss a trade; `delta` dollars a dollar of the underlying).
#: edge: net edge a trade in the Gym's periods (Validation, holdout) after the Gym's costs; edge_forward: forward (live);
#: cost: the Gym's cost a trade (the 1.5x stress twin pays half of it again); noise/tails: Gaussian or Student-t noise;
#: skew: (p_win, win, lose) noise in place of it, centred; delta: the entry delta; timing: the share of sessions its
#: delta's side matches the move (a directional timing edge); drift: the market's annual drift in its desk.
WORLDS: dict[str, dict[str, Any]] = {
    "absent": {"kind": "negative", "rate": 3.0, "edge": 0.0, "noise": 0.5},
    "absent_sparse": {"kind": "negative", "rate": 0.7, "edge": 0.0, "noise": 0.5},
    "absent_fat": {"kind": "negative", "rate": 3.0, "edge": 0.0, "noise": 0.5, "tails": 3},
    "skewed_null": {"kind": "negative", "rate": 2.0, "edge": 0.0, "skew": [0.90, 0.10, -0.90]},
    "cost_erased": {"kind": "negative", "rate": 3.0, "edge": 0.06, "edge_forward": -0.02, "noise": 0.5},
    "drift_only": {"kind": "negative", "rate": 3.0, "edge": -0.03, "noise": 0.3, "delta": 20.0, "drift": 0.25},
    "fading": {"kind": "negative", "rate": 3.0, "edge": 0.08, "edge_forward": -0.01, "noise": 0.5},
    "planted_dense": {"kind": "positive", "rate": 3.0, "edge": 0.10, "noise": 0.5},
    "planted_sparse": {"kind": "positive", "rate": 0.7, "edge": 0.20, "noise": 0.5},
    "planted_premium": {"kind": "positive", "rate": 2.0, "edge": 0.06, "skew": [0.94, 0.12, -0.90]},
    "planted_directional": {"kind": "positive", "rate": 3.0, "edge": -0.03, "noise": 0.3, "delta": 20.0,
                            "timing": 0.56, "drift": 0.25},
}
COST = 0.03
MIXED = "mixed"
#: Variants judged on the primary desk's own daily figures (never applied; their promotions do not free slots).
VARIANTS: dict[str, dict[str, Any]] = {
    "no_drift_control": {"drift": False},
    "no_prefilter": {"prefilter": False},
    "no_fdr": {"fdr": False},
    "fdr_q_0.05": {"fdr_q": 0.05},
    "fdr_q_0.02": {"fdr_q": 0.02},
}


# ------------------------------------------------------------------------------------------------ the generator
def _seed(*parts: Any) -> int:
    return int(hashlib.sha256("|".join(str(p) for p in (SUITE_ID,) + parts).encode("utf-8")).hexdigest()[:16], 16)


def _rng(*parts: Any) -> Any:
    import numpy as np

    return np.random.default_rng(_seed(*parts))


def weekdays(first: dt.date, n: int) -> list[str]:
    out, day = [], first
    while len(out) < n:
        if day.weekday() < 5:
            out.append(day.isoformat())
        day += dt.timedelta(days=1)
    return out


def nyse_sessions(first: str, n: int) -> list[str]:
    """`n` NYSE sessions from `first` (the live path's calendar, as the ladder counts them)."""
    from league.live.chains import session_minutes

    out, day = [], dt.date.fromisoformat(first)
    while len(out) < n:
        if session_minutes(day) is not None:
            out.append(day.isoformat())
        day += dt.timedelta(days=1)
    return out


def market(days: Sequence[str], *, drift: float, replication: int, period: str, world: str) -> dict[str, tuple[float, float]]:
    """{day: (the underlying at the session's open, its move over the session)}: one path a replication and period."""
    rng = _rng("market", world, replication, period)
    spot, sd, mu = PROTOCOL["spot"], PROTOCOL["annual_vol"] / math.sqrt(252.0), drift / 252.0
    out = {}
    for day in days:
        move = spot * (mu + sd * float(rng.standard_normal()))
        out[day] = (spot, move)
        spot = max(1.0, spot + move)
    return out


def _noise(spec: Mapping[str, Any], rng: Any) -> float:
    if spec.get("skew"):
        p, win, lose = spec["skew"]
        mean = p * win + (1.0 - p) * lose
        return (win if rng.random() < p else lose) - mean
    z = float(rng.standard_normal())
    if spec.get("tails"):
        df = float(spec["tails"])
        z = z / math.sqrt(float(rng.chisquare(df)) / df) * math.sqrt((df - 2.0) / df)
    return float(spec.get("noise", 0.5)) * z


def trades(world: str, entrant: int, replication: int, period: str, days: Sequence[str],
           path: Mapping[str, tuple[float, float]]) -> list[dict[str, Any]]:
    """One entrant's closes over `days` (Gym periods "validation" and "holdout", or "forward"): [{day, pnl, delta, spot,
    exit_spot}], in order."""
    spec = WORLDS[world]
    rng = _rng("trades", world, replication, entrant, period)
    edge = float(spec.get("edge_forward", spec["edge"]) if period == "forward" else spec["edge"])
    loss = PROTOCOL["max_loss"]
    out = []
    for day in days:
        spot, move = path[day]
        for _ in range(int(rng.poisson(float(spec["rate"])))):
            delta = float(spec.get("delta", 0.0))
            if spec.get("timing"):
                side = 1.0 if move > 0 else -1.0
                delta *= side if rng.random() < float(spec["timing"]) else -side
            pnl = loss * (edge + _noise(spec, rng)) + delta * move
            out.append({"day": day, "pnl": pnl, "delta": delta, "spot": spot, "exit_spot": spot + move})
    return out


def ledger_rows(closes: Sequence[Mapping[str, Any]], *, start: int = 0) -> list[dict[str, Any]]:
    """Closes in the practice ledger's shape (`ObserveStore.ladder_rows`): {seq, trade_id, pnl, max_loss, exit_day,
    body} whose body is an engine trade row's (qty, fees, two legs with their context deltas, the entry spot, and the
    exit spot the live path records)."""
    rows = []
    for i, c in enumerate(closes, start):
        diff = float(c["delta"]) / 100.0                     # one lot: the legs' deltas differ by delta / 100
        legs = [{"dte": 1, "strike": 0.0, "right": "C", "side": "long", "ratio": 1},
                {"dte": 1, "strike": 0.0, "right": "C", "side": "short", "ratio": 1}]
        body = {"id": i, "qty": 1, "fees": 1.3, "legs": legs, "type": "debit_vertical",
                "context": {"spot": round(float(c["spot"]), 6), "delta": [0.3 + diff, 0.3]},
                "exit_spot": round(float(c["exit_spot"]), 6), "pnl": round(float(c["pnl"]), 6),
                "max_loss": PROTOCOL["max_loss"], "exit_day": c["day"]}
        rows.append({"seq": i, "trade_id": str(i), "pnl": round(float(c["pnl"]), 6), "max_loss": PROTOCOL["max_loss"],
                     "exit_day": c["day"], "body": body})
    return rows


def gym_result(closes: Sequence[Mapping[str, Any]], days: Sequence[str], *, stress: float = 1.0) -> dict[str, Any]:
    """A Gym-shaped result (trades, daily, summary) of closes over `days`; `stress` 1.5 pays half the cost again."""
    from league.gym import results as R

    loss = PROTOCOL["max_loss"]
    extra = (stress - 1.0) * COST * loss
    rows, daily = [], {d: 0.0 for d in days}
    for c in closes:
        pnl = float(c["pnl"]) - extra
        rows.append({"day": c["day"], "pnl": pnl, "max_loss": loss, "qty": 1, "return_on_max_loss": pnl / loss,
                     "fees": 1.3})
        daily[c["day"]] += pnl
    series = [[d, daily[d]] for d in days]
    return {"status": "ok", "trades": rows, "daily": series, "summary": R.summarize(rows, series, PROTOCOL["capital"])}


# ------------------------------------------------------------------------------------------------ the sealed look
def np_block_bootstrap(xs: Sequence[float], *, block: int = 5, draws: int = 2000, seed: str = "") -> dict[str, float] | None:
    """`evidence.block_bootstrap` in numpy: the same moving blocks and draws, another random stream."""
    import numpy as np

    values = np.array([float(x) for x in xs if x is not None and math.isfinite(float(x))])
    n = len(values)
    if n < 2:
        return None
    b = max(1, min(int(block), n))
    starts = n - b + 1
    blocks = -(-n // b)
    rng = np.random.default_rng(int(hashlib.sha256((seed or str(n)).encode()).hexdigest()[:16], 16))
    first = rng.integers(0, starts, size=(int(draws), blocks))
    idx = (first[:, :, None] + np.arange(b)[None, None, :]).reshape(int(draws), -1)[:, :n]
    means = np.sort(values[idx].mean(axis=1))
    lcb = float(means[int(0.05 * len(means))])
    p = float((means <= 0).sum()) / len(means)
    return {"mean": float(values.mean()), "lcb95": lcb, "p": max(p, 1.0 / (len(means) + 1))}


@contextlib.contextmanager
def fast_bootstrap():
    """`evidence.holdout_line` with `np_block_bootstrap` in place of the pure-Python one, for this block only."""
    from league.swarm import evidence

    original = evidence.block_bootstrap
    evidence.block_bootstrap = np_block_bootstrap
    try:
        yield
    finally:
        evidence.block_bootstrap = original


def drift_hold(result: Mapping[str, Any], path: Mapping[str, tuple[float, float]], closes: Sequence[Mapping[str, Any]],
               share: float = 0.25) -> bool:
    """THE DRIFT HOLD on the Validation year's own drift fit (the Gym's: the slope of the held days' P&L on the market's
    move, charged the period's unconditional drift): held when long-delta with a drift share at or above `share`."""
    held = sorted({c["day"] for c in closes})
    if not held:
        return False
    daily = {d: 0.0 for d in held}
    for c in closes:
        daily[c["day"]] += float(c["pnl"])
    moves = [path[d][1] for d in held]
    sxx = sum(m * m for m in moves)
    if sxx <= 0:
        return False
    beta = sum(daily[d] * path[d][1] for d in held) / sxx
    unconditional = sum(m for _, m in path.values()) / len(path)
    drift_usd = beta * unconditional * len(held)
    alpha = sum(daily.values()) - drift_usd
    whole = abs(alpha) + abs(drift_usd)
    return beta > 0 and whole > 0 and abs(drift_usd) / whole >= share


def sealed(entrants: Sequence[Mapping[str, Any]], *, holds: bool, holdout_sessions: int) -> dict[int, bool]:
    """THE SEALED LOOK over the entrants in their order (the module docstring): {entrant: promoted}."""
    from league.swarm import evidence

    looks = list(PROTOCOL["prior_holdout_ps"])
    made = passes = 0
    out: dict[int, bool] = {}
    with fast_bootstrap():
        for e in entrants:
            out[e["id"]] = False
            line = e["validation_line"]
            if not line["passed"]:
                continue
            if evidence.leakage_alarm(made, passes):
                continue  # the alarm stops the gate
            if holds:
                if e["drift_hold"]:
                    continue
                power = evidence.holdout_power(e["validation"]["summary"].get("sharpe_daily"), holdout_sessions,
                                               evidence.holm_level(looks))
                if power is None or power < evidence.LOOK_HOLD_MIN_POWER:
                    continue
            look = evidence.holdout_line(e["holdout"], validation_sharpe=e["validation"]["summary"].get("sharpe_daily"),
                                         previous_ps=looks, seed=f"{e['world']}:{e['id']}")
            looks.append(look["p"])
            made += 1
            passes += int(bool(look["passed"]))
            out[e["id"]] = bool(look["passed"])
    return out


# ------------------------------------------------------------------------------------------------ the ladder's desk
def _entrant(world: str, i: int, replication: int, paths: Mapping[str, Any], days: Mapping[str, list[str]]) -> dict[str, Any]:
    from league.swarm import evidence

    vtrades = trades(world, i, replication, "validation", days["validation"], paths["validation"])
    htrades = trades(world, i, replication, "holdout", days["holdout"], paths["holdout"])
    validation = gym_result(vtrades, days["validation"])
    stressed = gym_result(vtrades, days["validation"], stress=1.5)
    sharpe = evidence.traded_sharpe(validation["summary"])
    line = evidence.validation_line(validation, {"status": "ok", "summary": stressed["summary"]}, validated_versions=1,
                                    version_sharpes=[sharpe] if sharpe is not None else [])
    holdout = gym_result(htrades, days["holdout"])
    return {"id": i, "world": world, "kind": WORLDS[world]["kind"], "validation": {"summary": validation["summary"]},
            "validation_line": {"passed": bool(line["passed"])}, "drift_hold": drift_hold(validation, paths["validation"],
                                                                                           vtrades),
            "holdout": holdout, "holdout_pnl": float(holdout["summary"]["pnl"])}


def desk(world: str, replication: int, *, slots: int | None = None, sessions: int | None = None,
         rules: Any = None) -> dict[str, Any]:
    """One desk of `world` (or `MIXED`): the ladder's run over the forward sessions, then the sealed look on the same
    admitted entrants. Returns every admitted entrant's outcome under each design and variant."""
    from league.live import ladder as L

    rules = rules or L.Rules.from_constitution()
    slots = int(slots or PROTOCOL["slots"])
    sessions = int(sessions or PROTOCOL["sessions"])
    forward_days = nyse_sessions(PROTOCOL["first_session"], sessions)
    days = {"validation": weekdays(dt.date(PROTOCOL["validation_year"], 1, 2), 252),
            "holdout": weekdays(dt.date.fromisoformat(PROTOCOL["holdout_first"]), PROTOCOL["holdout_sessions"])}
    worlds = sorted(WORLDS) if world == MIXED else [world]
    paths: dict[str, dict[str, Any]] = {}
    for w in worlds:
        drift = float(WORLDS[w].get("drift", PROTOCOL["market_drift"]))
        key = f"drift{drift}"
        if key not in paths:
            paths[key] = {"validation": market(days["validation"], drift=drift, replication=replication,
                                               period="validation", world=f"{world}:{key}"),
                          "holdout": market(days["holdout"], drift=drift, replication=replication, period="holdout",
                                            world=f"{world}:{key}"),
                          "forward": market(forward_days, drift=drift, replication=replication, period="forward",
                                            world=f"{world}:{key}")}
    pick = _rng("mix", world, replication)

    def world_of(i: int) -> str:
        return worlds[int(pick.integers(0, len(worlds)))] if world == MIXED else world

    def path_of(w: str) -> dict[str, Any]:
        return paths[f"drift{float(WORLDS[w].get('drift', PROTOCOL['market_drift']))}"]

    entrants: list[dict[str, Any]] = []
    active: dict[int, dict[str, Any]] = {}
    p_latest: dict[int, float] = {}
    entered: dict[int, str] = {}
    outcome: dict[int, dict[str, Any]] = {}
    variants = {name: {} for name in VARIANTS}
    figures_last: dict[int, dict[str, Any]] = {}
    for t, day in enumerate(forward_days):
        while len(active) < slots:
            i = len(entrants)
            w = world_of(i)
            e = _entrant(w, i, replication, path_of(w), days)
            window = forward_days[t:t + rules.max_sessions]
            closes = trades(w, i, replication, "forward", window, path_of(w)["forward"])
            e["rows_all"] = ledger_rows(closes)
            entrants.append(e)
            active[i] = {"start": t, "first_day": day, "asked": None}
            entered[i] = day
            p_latest[i] = 1.0
        judged = []
        for i, st in active.items():
            e = entrants[i]
            rows = [r for r in e["rows_all"] if r["exit_day"] <= day]
            cohort = {"family": f"{e['world']}-{i}", "version": 1, "first_day": st["first_day"],
                      "snapshot": {"run_sha": f"bench-{i}", "practice_evaluator": "bench"}}
            practice = {"first_day": st["first_day"], "sessions": t - st["start"] + 1}
            figures = L.judge(cohort, practice, rows, through=day, rules=rules)
            p_latest[i] = figures["p"]
            figures_last[i] = figures
            judged.append((i, figures))
        since = (dt.date.fromisoformat(day) - dt.timedelta(days=rules.fdr_days)).isoformat()
        window_ps = [p_latest[i] for i in p_latest if entered[i] >= since]
        cut, _ = L.benjamini_hochberg(window_ps, rules.fdr_q)
        cuts = {name: L.benjamini_hochberg(window_ps, float(v.get("fdr_q", rules.fdr_q)))[0] for name, v in VARIANTS.items()}
        ended = []
        for i, figures in judged:
            st, e = active[i], entrants[i]
            lines = figures["lines"]
            base = lines["record"] and lines["bound"] and lines["windows"]
            for name, v in VARIANTS.items():
                if i in variants[name]:
                    continue
                ok = base and (lines["drift"] or v.get("drift") is False)
                ok = ok and (v.get("fdr") is False or (cuts[name] is not None and figures["p"] <= cuts[name]))
                ok = ok and (v.get("prefilter") is False or e["holdout_pnl"] >= 0)
                if ok:
                    variants[name][i] = day
            met = base and lines["drift"] and cut is not None and figures["p"] <= cut
            if met and st["asked"] is not None and st["asked"] < day:
                # Asked at an earlier session's end and read by the gate since: decided now, every line holding again.
                if e["holdout_pnl"] >= 0:
                    outcome[i] = {"ladder": "promoted", "day": day, "sessions": t - st["start"] + 1}
                else:
                    outcome[i] = {"ladder": "prefilter_negative", "day": day}
                ended.append(i)
                continue
            if met and st["asked"] is None:
                st["asked"] = day   # the House asks tonight; the gate's answer is there by the next session's end
            if t - st["start"] + 1 >= rules.max_sessions:
                outcome[i] = {"ladder": "window", "day": day}
                ended.append(i)
        for i in ended:
            active.pop(i, None)
    for i in active:
        outcome[i] = {"ladder": "running", "day": forward_days[-1]}
    sealed_holds = sealed(entrants, holds=True, holdout_sessions=PROTOCOL["holdout_sessions"])
    sealed_bare = sealed(entrants, holds=False, holdout_sessions=PROTOCOL["holdout_sessions"])
    rows = []
    for e in entrants:
        i = e["id"]
        last = figures_last.get(i) or {}
        rows.append({"id": i, "world": e["world"], "kind": e["kind"], "ladder": outcome[i]["ladder"] == "promoted",
                     "ladder_outcome": outcome[i]["ladder"], "sealed": sealed_holds[i], "sealed_bare": sealed_bare[i],
                     "validation_passed": e["validation_line"]["passed"], "drift_hold": e["drift_hold"],
                     "holdout_nonnegative": e["holdout_pnl"] >= 0,
                     "variants": {name: i in variants[name] for name in VARIANTS},
                     "last": {"full": last.get("full"), "drift": (last.get("lines") or {}).get("drift"),
                              "bound": (last.get("lines") or {}).get("bound"),
                              "windows": (last.get("lines") or {}).get("windows")}})
    return {"world": world, "replication": replication, "entrants": len(entrants), "rows": rows}


# ------------------------------------------------------------------------------------------------ the report
def exact_upper(k: int, n: int, alpha: float) -> float:
    """The exact (Clopper-Pearson) one-sided upper bound on a rate after `k` events in `n` trials (vendored, as the
    evaluator suite's)."""
    from league.swarm.evaluator_benchmarks import exact_upper as upper

    return upper(k, n, alpha)


def rate(k: int, n: int, confidence: float = 0.95) -> dict[str, Any]:
    alpha = (1.0 - confidence) / 2.0
    return {"count": int(k), "of": int(n), "rate": round(k / n, 5) if n else None,
            "lower_95": 0.0 if k <= 0 or not n else round(1.0 - exact_upper(n - k, n, alpha), 5),
            "upper_95": round(exact_upper(k, n, alpha), 5) if n else 1.0}


DESIGNS = ("ladder", "sealed", "sealed_bare")


def aggregate(desks: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Per world and pooled: false promotions (negatives) and missed signals (positives) under each design and
    variant, the drift control's pass shares, and THE BINDING RULE's verdict."""
    by: dict[str, list[Mapping[str, Any]]] = {}
    for d in desks:
        # An entrant still practising when its desk ended had fewer chances on the ladder: counted by neither design.
        by.setdefault(d["world"], []).extend(r for r in d["rows"] if r.get("ladder_outcome") != "running")
    worlds = {}
    for name, rows in sorted(by.items()):
        if not rows:
            continue
        out: dict[str, Any] = {"entrants": len(rows)}
        for kind, label in (("negative", "false_promotions"), ("positive", "missed_signals")):
            mine = [r for r in rows if r["kind"] == kind]
            if not mine:
                continue
            block = {}
            for design in DESIGNS:
                k = sum(1 for r in mine if (r[design] if kind == "negative" else not r[design]))
                block[design] = rate(k, len(mine))
            for variant in VARIANTS:
                k = sum(1 for r in mine if (r["variants"][variant] if kind == "negative" else not r["variants"][variant]))
                block[f"ladder:{variant}"] = rate(k, len(mine))
            out[label] = block
        full = [r for r in rows if r["last"].get("full")]
        out["drift_line_passed_share"] = round(sum(1 for r in full if r["last"].get("drift")) / len(full), 4) if full else None
        out["validation_passed_share"] = round(sum(1 for r in rows if r["validation_passed"]) / len(rows), 4)
        out["drift_held_share"] = round(sum(1 for r in rows if r["drift_hold"]) / len(rows), 4)
        worlds[name] = out
    pure = [r for name, rows in by.items() if name != MIXED for r in rows if r["kind"] == "negative"]
    mixed = [r for r in by.get(MIXED, []) if r["kind"] == "negative"]
    pooled = {design: rate(sum(1 for r in pure if r[design]), len(pure)) for design in DESIGNS}
    pooled_mixed = {design: rate(sum(1 for r in mixed if r[design]), len(mixed)) for design in DESIGNS}
    binding = (bool(pure) and pooled["ladder"]["count"] <= pooled["sealed"]["count"]
               and pooled["ladder"]["count"] <= pooled["sealed_bare"]["count"]
               and (not mixed or (pooled_mixed["ladder"]["count"] <= pooled_mixed["sealed"]["count"]
                                  and pooled_mixed["ladder"]["count"] <= pooled_mixed["sealed_bare"]["count"])))
    exceeds = sorted(name for name, w in worlds.items() if "false_promotions" in w
                     and w["false_promotions"]["ladder"]["count"] > w["false_promotions"]["sealed"]["count"])
    return {"worlds": worlds, "pooled_negatives": pooled, "mixed_negatives": pooled_mixed, "binding": binding,
            "worlds_where_ladder_exceeds_sealed": exceeds}


def bootstrap_agreement() -> dict[str, Any]:
    """The numpy port against `evidence.block_bootstrap` on fixed series: their p-values and bounds agree to Monte
    Carlo error."""
    import random

    from league.swarm import evidence

    out = []
    for k, mean in enumerate((0.0, 0.05, 0.12)):
        rng = random.Random(k)
        xs = [mean + rng.gauss(0.0, 1.0) for _ in range(185)]
        a = evidence.block_bootstrap(xs, seed=f"agree{k}", draws=4000)
        b = np_block_bootstrap(xs, seed=f"agree{k}", draws=4000)
        out.append({"mean": mean, "p_original": round(a["p"], 4), "p_numpy": round(b["p"], 4),
                    "lcb_original": round(a["lcb95"], 4), "lcb_numpy": round(b["lcb95"], 4)})
    return {"cases": out, "max_p_gap": max(abs(c["p_original"] - c["p_numpy"]) for c in out)}


def suite_sha() -> str:
    """The pinned definition: the protocol, the worlds, the variants and this module's source."""
    body = json.dumps({"protocol": PROTOCOL, "worlds": WORLDS, "variants": VARIANTS, "cost": COST}, sort_keys=True)
    source = Path(__file__).read_bytes()
    return hashlib.sha256(body.encode("utf-8") + source).hexdigest()


def run(worlds: Sequence[str], replications: int, *, slots: int | None = None, sessions: int | None = None,
        log: Any = None) -> dict[str, Any]:
    from league.live import ladder as L

    rules = L.Rules.from_constitution()
    started = time.time()
    desks = []
    for world in worlds:
        for r in range(int(replications)):
            desks.append(desk(world, r, slots=slots, sessions=sessions, rules=rules))
            if log is not None:
                print(f"{world} {r + 1}/{replications} ({time.time() - started:.0f}s)", file=log, flush=True)
    from dataclasses import asdict

    return {"suite": SUITE_ID, "suite_sha": suite_sha(), "protocol": PROTOCOL, "rules": asdict(rules),
            "replications": int(replications), "worlds": list(worlds),
            "slots": int(slots or PROTOCOL["slots"]), "sessions": int(sessions or PROTOCOL["sessions"]),
            "seconds": round(time.time() - started, 1), "desks": desks}


def combine(parts: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Several runs' desks as one report (the same suite, slots and sessions only)."""
    first = parts[0]
    for p in parts[1:]:
        for key in ("suite_sha", "slots", "sessions", "replications"):
            if p.get(key) != first.get(key):
                raise ValueError(f"the parts differ in {key}")
    desks = [d for p in parts for d in p["desks"]]
    report = {k: first[k] for k in ("suite", "suite_sha", "protocol", "rules", "replications", "slots", "sessions")}
    report["worlds"] = sorted({d["world"] for d in desks})
    report["seconds"] = round(sum(float(p.get("seconds") or 0) for p in parts), 1)
    report["aggregate"] = aggregate(desks)
    report["bootstrap_agreement"] = bootstrap_agreement()
    return report


def markdown(report: Mapping[str, Any]) -> str:
    """The private report's text."""
    agg = report["aggregate"]
    lines = [f"# Forward ladder benchmark ({report['suite']})", "",
             f"suite sha `{report['suite_sha'][:16]}`; {report['replications']} replications a world; desks of "
             f"{report['slots']} practice slots over {report['sessions']} forward sessions; {report['seconds']} s.", "",
             f"**Binding rule: {'MET' if agg['binding'] else 'NOT MET'}** (the ladder's false promotions at or below the "
             "sealed look's, with and without its holds, over the single-world desks' negatives and over the mixed "
             "desks' negatives).", ""]

    def cell(r: Mapping[str, Any]) -> str:
        if not r["of"]:
            return "n/a"
        return f"{r['count']}/{r['of']} ({r['rate']:.4f}; 95% {r['lower_95']:.4f}-{r['upper_95']:.4f})"

    lines += ["## Pooled negatives", "", "| design | single-world desks | mixed desks |", "|---|---|---|"]
    for design in DESIGNS:
        lines.append(f"| {design} | {cell(agg['pooled_negatives'][design])} | {cell(agg['mixed_negatives'][design])} |")
    lines += ["", "## Per world", "",
              "| world | entrants | ladder | sealed (holds) | sealed (bare) | validation passed | drift hold | "
              "drift line passed |", "|---|---|---|---|---|---|---|---|"]
    for name, w in agg["worlds"].items():
        block = w.get("false_promotions") or w.get("missed_signals")
        what = "FP" if "false_promotions" in w else "missed"
        lines.append(f"| {name} ({what}) | {w['entrants']} | {cell(block['ladder'])} | {cell(block['sealed'])} | "
                     f"{cell(block['sealed_bare'])} | {w['validation_passed_share']} | {w['drift_held_share']} | "
                     f"{w['drift_line_passed_share']} |")
    lines += ["", "## Variants (ladder; never applied)", "", "| world | " + " | ".join(VARIANTS) + " |",
              "|---|" + "---|" * len(VARIANTS)]
    for name, w in agg["worlds"].items():
        block = w.get("false_promotions") or w.get("missed_signals")
        lines.append(f"| {name} | " + " | ".join(f"{block[f'ladder:{v}']['count']}/{block[f'ladder:{v}']['of']}"
                                                 for v in VARIANTS) + " |")
    lines += ["", f"Worlds where the ladder's false promotions exceed the sealed look's (with holds): "
                  f"{', '.join(agg['worlds_where_ladder_exceeds_sealed']) or 'none'}.", "",
              f"Bootstrap port agreement (max p gap): {report['bootstrap_agreement']['max_p_gap']}.", ""]
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    """Run worlds (a part: `--output` keeps its desks for `--combine`), or combine parts into the report."""
    parser = argparse.ArgumentParser(prog="python -m league.swarm.forward_benchmarks")
    parser.add_argument("--world", action="append", choices=sorted(WORLDS) + [MIXED])
    parser.add_argument("--replications", type=int, default=PROTOCOL["replications"])
    parser.add_argument("--slots", type=int)
    parser.add_argument("--sessions", type=int)
    parser.add_argument("--combine", nargs="+", help="parts written by --output, combined into one report")
    parser.add_argument("--output", help="a run: its desks (a part); --combine: the combined report")
    parser.add_argument("--report", help="the markdown report")
    parser.add_argument("--json", action="store_true", help="print the headline")
    args = parser.parse_args(argv)
    if args.combine:
        report = combine([json.loads(Path(p).read_text()) for p in args.combine])
        if args.output:
            Path(args.output).write_text(json.dumps(report, sort_keys=True, default=str))
    else:
        part = run(args.world or sorted(WORLDS) + [MIXED], args.replications, slots=args.slots, sessions=args.sessions,
                   log=sys.stderr)
        if args.output:
            Path(args.output).write_text(json.dumps(part, sort_keys=True, default=str))
        report = combine([part]) if (args.report or args.json) else None
    if args.report and report is not None:
        Path(args.report).write_text(markdown(report))
    if args.json and report is not None:
        agg = report["aggregate"]
        print(json.dumps({k: report[k] for k in ("suite", "suite_sha", "replications", "slots", "sessions", "seconds")}
                         | {"binding": agg["binding"], "pooled": agg["pooled_negatives"], "mixed": agg["mixed_negatives"],
                            "exceeds": agg["worlds_where_ladder_exceeds_sealed"]}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
