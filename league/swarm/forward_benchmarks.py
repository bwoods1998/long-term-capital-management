"""THE FORWARD LADDER'S BENCHMARK (evidence v3; the plan's Phase 3.3): the ladder's rule and the sealed-look design it
replaces, played on the SAME synthetic worlds before the ladder binds.

    python -m league.swarm.forward_benchmarks [--seed-id ID] [--replications R] [--world W ...] [--output PART.json] [--json]
    python -m league.swarm.forward_benchmarks --demotion [--seed-id ID] [--world W ...] [--programs N] [--output PART.json]
    python -m league.swarm.forward_benchmarks --combine PART.json ... [--output FULL.json] [--report REPORT.md]
    python scripts/ladder_judge.py PART.json ...        (THE VERDICT, below: the judge's, never this module's)

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

THE SEED ID (`seed_id`, `--seed-id`; `SEED_ID`, the development desks', when none is given): every random stream of the
generator (each market path, each entrant's closes, the mixed desk's draw of worlds, the demotion rule's programs) is
seeded from it and the stream's own name, and nothing else is. The designs' resamples are seeded from the desk (below),
never from it: the data they resample carry it. Another seed id is another set of desks; a part names its own, and
parts of two seed ids never combine.

THE TWO DESIGNS, on the same entrants in the same order:

- THE LADDER, as the House runs it (`league/live/ladder.py`'s own functions: `checkpoint_due`, `judge`,
  `benjamini_hochberg`, `Rules` from the constitution, on rows in the practice ledger's shape; and the gate's line,
  `evidence.prefilter_line`): `slots` cohorts practise at once. A cohort is judged ONLY AT ITS CHECKPOINTS, each once
  (the table's `checkpoints`, each at its own level in `alphas`; a desk misses no session, so each falls at the
  session's end at which the cohort has practised that many sessions), on its forward record through that session, its
  three resamples seeded "<the desk's world>:<replication>:<entrant>:<sessions practised>" + ":r", ":adj", ":perc".
  That night Benjamini-Hochberg runs over the entrants admitted in the trailing `fdr_days` days, each at the p-value
  of its latest judged checkpoint (1 before its first; an ended entrant's stands), the cohorts judged that night among
  them. A checkpoint that meets L1-L5 is FINAL. THE VALIDATION LINE (L0, the same `evidence.validation_line` verdict
  the sealed look starts from) not met: the cohort ends there (`validation_failed`). Met: it is LATCHED, no line is
  judged again, and its answer is read at the NEXT session's end: THE PRE-FILTER'S LINE on its holdout (the table's
  `prefilter_p`; the gate's seed, "prefilter:" and the run sha, here "bench-<entrant>") met, it is `promoted` (the
  benchmark plays the ladder as binding); not met, it ends `prefilter_negative`. A latched cohort keeps its slot until
  its answer, past its window too (one latched at its last checkpoint lives one session past it). A cohort that did
  not meet the lines at its last checkpoint ends at its window (`window`). A slot freed at a session's end takes the
  next entrant at the next session's start. A cohort still practising, or still latched, when the desk ends is
  `running`. (Suite 3. Suite 2's ladder arm judged every session by the daily lines and read only the sign of the
  pre-filter's P&L; suite 1's had no Validation line. The worlds and their random streams are suite 1's, `SEED_ID`.)
- THE SEALED LOOK (the design the ladder replaces): the entrant's Validation year through `evidence.validation_line`
  (with its 1.5x stress twin), then THE LOOK HOLDS as the gate runs them (the drift hold on the Validation year's own
  drift fit; the power hold at the Holm level), then one holdout look through `evidence.holdout_line` with Holm across
  every look of the desk after a fixed prior history, and the leakage alarm (10 looks, more than 30% passing, stops the
  gate). `sealed_bare` is the same without the holds.

The moving-block bootstrap of the holdout line, and of the pre-filter's line, is replaced, for speed, by a numpy port
of `evidence.block_bootstrap` (the same blocks and draws; another random stream: its p differs from the original's only
by Monte Carlo error, `bootstrap_agreement`).

A FALSE PROMOTION is a negative entrant promoted; a MISSED SIGNAL a positive entrant not promoted. Rates carry exact
(Clopper-Pearson) 95% bounds. THE COUNT (`COUNTED`, `counted`): the first 32 entrants of each desk in admission order
(two whole generations of the 16 slots), whatever their outcome, for both designs alike. No entrant is counted or left
out on its own outcome. A desk without its first 32 entrants, or with one of them still `running` when it ended, is not
the protocol's and is not counted: `aggregate` raises.

THE VERDICT IS NOT THIS MODULE'S. Whether the ladder may bind (the constitution's `options_money.ladder.binding`) is
judged by `scripts/ladder_judge.py` alone, on a run's parts (`--output`), by its own rule on that same count. This
module reports the counts (`aggregate`, `markdown`, `--json`) and says so (`VERDICT`); it names no verdict. READING THE
JUDGE: the verdict is its printed `VERDICT:` line (exit 0 with "met": the ladder may bind; exit 1 with "NOT met": it
records). An input it refuses also exits 1, with a message and NO `VERDICT:` line (its own docstring says 2, which
only a call without arguments returns): that is never "not met". The input is put right and the judge is run again on
the same desks.

THE DEMOTION RULE (`demotions`, after the WP6 review): a program promoted at the first forward session trades its
world's forward stream as real fills for `DEMOTION["horizon"]` sessions, judged at each session's end by the ladder's
demotion through the money table's own functions (`money.forward_stats`: negative over 20 trades; `money.session_bound`:
the trailing `demote_sessions` closing days' one-sided `demote_confidence` lower bound below zero), and by other
readings of the same words (`DEMOTION_READINGS`, never applied): the share demoted within 20, 40 and 60 sessions, per
world. A planted edge demoted is a real edge lost; a negative one demoted is the rule working.

What it is not: a market simulation. Returns are not bounded by the maximum loss, trades close the session they open,
Train is not simulated (both designs start from the same Train-eligible programs), the Gym's drift screen upstream of
both is not modelled, a session's end is never missed, the gate's answer is always there by the next session's end, and
the House's re-entry of a program under a new practice evaluator has no part in it. It never reads market data, places
an order or writes outside its output files.
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

SUITE_ID = "forward-suite-3"
#: THE SEED ID when none is given (the module docstring): the development desks'. The worlds' random streams under it
#: are suite 1's (the same entrants, markets and closes; only the designs' rules changed).
SEED_ID = "forward-suite-1"
#: THE COUNT (the module docstring): the entrants of a desk that are counted, its first in admission order: two whole
#: generations of the protocol's 16 slots. The judge's own (`scripts/ladder_judge.py`).
COUNTED = 32
#: THE VERDICT IS NOT THIS MODULE'S (the module docstring): what its report and its headline say in its place.
VERDICT = "none here: whether the ladder may bind is judged by scripts/ladder_judge.py alone, on the run's parts"

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
#: THE DEMOTION RULE's measurement (the module docstring): programs a world, sessions after the promotion.
DEMOTION: dict[str, Any] = {"programs": 300, "horizon": 60, "marks": [20, 40, 60]}
#: Readings of "a forward record negative over 20 trades, or a 20-session lower bound below zero": the rule as built
#: (`as_built`: both, the bound re-read at every session's end at the constitution's `demote_confidence`), the bound at a
#: higher confidence (`confidence`), the bound read only at the end of each non-overlapping block of `demote_sessions`
#: sessions (`blocks`), and the negative record alone (`bound` False).
DEMOTION_READINGS: dict[str, dict[str, Any]] = {
    "as_built": {},
    "bound_95": {"confidence": 0.95},
    "blocks_of_20": {"blocks": True},
    "negative_only": {"bound": False},
}


# ------------------------------------------------------------------------------------------------ the generator
def _seed(*parts: Any, seed_id: str = SEED_ID) -> int:
    """A generator stream's seed: THE SEED ID and the stream's own name (`parts`), hashed."""
    if not isinstance(seed_id, str) or not seed_id:
        raise ValueError("the seed id is a string that is not empty")
    return int(hashlib.sha256("|".join(str(p) for p in (seed_id,) + parts).encode("utf-8")).hexdigest()[:16], 16)


def _rng(*parts: Any, seed_id: str = SEED_ID) -> Any:
    import numpy as np

    return np.random.default_rng(_seed(*parts, seed_id=seed_id))


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


def market(days: Sequence[str], *, drift: float, replication: int, period: str, world: str,
           seed_id: str = SEED_ID) -> dict[str, tuple[float, float]]:
    """{day: (the underlying at the session's open, its move over the session)}: one path a replication and period."""
    rng = _rng("market", world, replication, period, seed_id=seed_id)
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
           path: Mapping[str, tuple[float, float]], *, seed_id: str = SEED_ID) -> list[dict[str, Any]]:
    """One entrant's closes over `days` (Gym periods "validation" and "holdout", or "forward"): [{day, pnl, delta, spot,
    exit_spot}], in order."""
    spec = WORLDS[world]
    rng = _rng("trades", world, replication, entrant, period, seed_id=seed_id)
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
def _entrant(world: str, i: int, replication: int, paths: Mapping[str, Any], days: Mapping[str, list[str]], *,
             seed_id: str = SEED_ID) -> dict[str, Any]:
    from league.swarm import evidence

    vtrades = trades(world, i, replication, "validation", days["validation"], paths["validation"], seed_id=seed_id)
    htrades = trades(world, i, replication, "holdout", days["holdout"], paths["holdout"], seed_id=seed_id)
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


def prefilter(holdout: Mapping[str, Any], run_sha: str, level: float) -> dict[str, Any]:
    """THE PRE-FILTER'S LINE on an entrant's holdout as the gate reads it (`evidence.prefilter_line` at `level`, the
    gate's seed for `run_sha`), its bootstrap through the numpy port: {passed, pnl, p, level}."""
    from league.swarm import evidence
    from league.swarm.gate import PREFILTER_SEED

    with fast_bootstrap():
        return evidence.prefilter_line(holdout, level=level, seed=PREFILTER_SEED + str(run_sha))


def desk(world: str, replication: int, *, slots: int | None = None, sessions: int | None = None,
         rules: Any = None, seed_id: str = SEED_ID) -> dict[str, Any]:
    """One desk of `world` (or `MIXED`) under THE SEED ID `seed_id`: THE LADDER's run over the forward sessions (the
    module docstring), then the sealed look on the same admitted entrants. {world, replication, entrants, rows}: every
    admitted entrant's row, in admission order: {id, world, kind, ladder (promoted), ladder_outcome, start (the session
    index of its admission), at (the checkpoint that decided it; None for `window` and `running`), sealed, sealed_bare,
    validation_passed, drift_hold, holdout_p and holdout_ok (the pre-filter's two figures: its bootstrap's p-value,
    its net P&L not negative), last (the lines at its last judged checkpoint; None before one)}."""
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
                                               period="validation", world=f"{world}:{key}", seed_id=seed_id),
                          "holdout": market(days["holdout"], drift=drift, replication=replication, period="holdout",
                                            world=f"{world}:{key}", seed_id=seed_id),
                          "forward": market(forward_days, drift=drift, replication=replication, period="forward",
                                            world=f"{world}:{key}", seed_id=seed_id)}
    pick = _rng("mix", world, replication, seed_id=seed_id)

    def world_of(i: int) -> str:
        return worlds[int(pick.integers(0, len(worlds)))] if world == MIXED else world

    def path_of(w: str) -> dict[str, Any]:
        return paths[f"drift{float(WORLDS[w].get('drift', PROTOCOL['market_drift']))}"]

    entrants: list[dict[str, Any]] = []
    active: dict[int, dict[str, Any]] = {}
    p_latest: dict[int, float] = {}
    entered: dict[int, str] = {}
    starts: dict[int, int] = {}
    outcome: dict[int, dict[str, Any]] = {}
    last: dict[int, dict[str, Any]] = {}
    for t, day in enumerate(forward_days):
        while len(active) < slots:
            i = len(entrants)
            w = world_of(i)
            e = _entrant(w, i, replication, path_of(w), days, seed_id=seed_id)
            window = forward_days[t:t + rules.max_sessions]
            closes = trades(w, i, replication, "forward", window, path_of(w)["forward"], seed_id=seed_id)
            e["rows_all"] = ledger_rows(closes)
            e["run_sha"] = f"bench-{i}"
            # The gate's read of its holdout: the same whenever it is made, so made here once (the row's two figures);
            # the ladder consults it only at the cohort's answer.
            e["prefilter"] = prefilter(e["holdout"], e["run_sha"], rules.prefilter_p)
            entrants.append(e)
            active[i] = {"start": t, "first_day": day, "judged": [], "latch": None}
            starts[i] = t
            entered[i] = day
            p_latest[i] = 1.0
        due = []
        for i, st in active.items():
            if st["latch"] is not None:
                continue  # latched: its checkpoint's verdict is final, no line is judged again
            practised = t - st["start"] + 1
            point = L.checkpoint_due(practised, practised, st["judged"], rules)
            if point is None:
                continue  # no checkpoint tonight: no judgement, and its p-value stands
            e = entrants[i]
            rows = [r for r in e["rows_all"] if r["exit_day"] <= day]
            cohort = {"family": f"{e['world']}-{i}", "version": 1, "first_day": st["first_day"],
                      "snapshot": {"run_sha": e["run_sha"], "practice_evaluator": "bench"}}
            practice = {"first_day": st["first_day"], "sessions": practised}
            figures = L.judge(cohort, practice, rows, through=day, rules=rules, checkpoint=point,
                              seed=f"{world}:{replication}:{i}:{practised}")
            st["judged"].append(point)
            due.append((i, point, figures))
        since = (dt.date.fromisoformat(day) - dt.timedelta(days=rules.fdr_days)).isoformat()
        family = {i: p for i, p in p_latest.items() if entered[i] >= since}
        for i, _, figures in due:  # tonight's checkpoint is its latest; a judged cohort is always in its own family
            family[i] = p_latest[i] = figures["p"]
        cut, _ = L.benjamini_hochberg(family.values(), rules.fdr_q)
        ended = []
        for i, st in active.items():
            latch = st["latch"]
            if latch is None or not latch["t"] < t:
                continue
            # THE ANSWER SESSION: the gate's read, asked for at an earlier session's end, is there. No line is judged.
            passed = entrants[i]["prefilter"]["passed"]
            outcome[i] = {"ladder": "promoted" if passed else "prefilter_negative", "at": latch["at"]}
            ended.append(i)
        for i, point, figures in due:
            lines = figures["lines"]
            fdr = bool(figures["full"] and cut is not None and figures["p"] <= cut)
            last[i] = {"checkpoint": point, "full": figures["full"], "bound": lines["bound"], "windows": lines["windows"],
                       "drift": lines["drift"], "fdr": fdr}
            if not (lines["record"] and lines["bound"] and lines["windows"] and lines["drift"] and fdr):
                continue  # it practises on to its next checkpoint, or ends at its window below
            if not entrants[i]["validation_line"]["passed"]:
                # L0, THE VALIDATION LINE: read once L1-L5 are met, before the pre-filter is asked for.
                outcome[i] = {"ladder": "validation_failed", "at": point}
                ended.append(i)
            else:
                active[i]["latch"] = {"t": t, "at": point}  # the House asks tonight; read at the next session's end
        for i, st in active.items():
            if i not in outcome and st["latch"] is None and t - st["start"] + 1 >= rules.max_sessions:
                outcome[i] = {"ladder": "window", "at": None}
                ended.append(i)
        for i in ended:
            active.pop(i, None)
    for i in active:
        outcome[i] = {"ladder": "running", "at": None}
    sealed_holds = sealed(entrants, holds=True, holdout_sessions=PROTOCOL["holdout_sessions"])
    sealed_bare = sealed(entrants, holds=False, holdout_sessions=PROTOCOL["holdout_sessions"])
    rows = []
    for e in entrants:
        i, read = e["id"], e["prefilter"]
        rows.append({"id": i, "world": e["world"], "kind": e["kind"], "ladder": outcome[i]["ladder"] == "promoted",
                     "ladder_outcome": outcome[i]["ladder"], "start": starts[i], "at": outcome[i]["at"],
                     "sealed": sealed_holds[i], "sealed_bare": sealed_bare[i],
                     "validation_passed": e["validation_line"]["passed"], "drift_hold": e["drift_hold"],
                     "holdout_p": read["p"], "holdout_ok": read["pnl"] is not None and read["pnl"] >= 0,
                     "last": last.get(i)})
    return {"world": world, "replication": replication, "entrants": len(entrants), "rows": rows}


# ------------------------------------------------------------------------------------------------ the demotion rule
def demotions(world: str, *, programs: int | None = None, horizon: int | None = None, rules: Any = None,
              seed_id: str = SEED_ID) -> dict[str, Any]:
    """THE DEMOTION RULE on `world` (the module docstring): {world, kind, programs, readings: {reading: {mark: demoted
    within that many sessions}}}. Each program's forward stream (its world's forward edge, one market path a program,
    under THE SEED ID `seed_id`) is its real record from the session after its promotion."""
    from league.live import ladder as L
    from league.live import money as M

    rules = rules or L.Rules.from_constitution()
    programs = int(programs or DEMOTION["programs"])
    horizon = int(horizon or DEMOTION["horizon"])
    days = nyse_sessions(PROTOCOL["first_session"], horizon)
    drift = float(WORLDS[world].get("drift", PROTOCOL["market_drift"]))
    marks = [m for m in DEMOTION["marks"] if m <= horizon]
    out = {name: {str(m): 0 for m in marks} for name in DEMOTION_READINGS}
    for k in range(programs):
        path = market(days, drift=drift, replication=k, period="probe", world=f"demotion:{world}", seed_id=seed_id)
        rows = [{"day": c["day"], "source": "real", "pnl": c["pnl"], "max_loss": PROTOCOL["max_loss"], "version": 1}
                for c in trades(world, k, -1, "forward", days, path, seed_id=seed_id)]
        demoted_at: dict[str, int] = {}
        for t, day in enumerate(days, 1):
            seen = [r for r in rows if r["day"] <= day]
            negative = M.forward_stats(seen, rules.demote_confidence, version=1).negative
            bounds: dict[float, float | None] = {}
            for name, reading in DEMOTION_READINGS.items():
                if name in demoted_at:
                    continue
                hit = negative
                if not hit and reading.get("bound", True) and (not reading.get("blocks") or t % rules.demote_sessions == 0):
                    confidence = float(reading.get("confidence", rules.demote_confidence))
                    if confidence not in bounds:
                        bounds[confidence] = M.session_bound(seen, sessions=rules.demote_sessions, confidence=confidence,
                                                             version=1)[1]
                    hit = bounds[confidence] is not None and bounds[confidence] < 0
                if hit:
                    demoted_at[name] = t
            if len(demoted_at) == len(DEMOTION_READINGS):
                break
        for name, t in demoted_at.items():
            for m in marks:
                out[name][str(m)] += int(t <= m)
    return {"world": world, "kind": WORLDS[world]["kind"], "programs": programs, "horizon": horizon,
            "readings": {name: {m: rate(c, programs) for m, c in by.items()} for name, by in out.items()}}


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


def counted(desk: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """THE COUNT's rows of one desk (the module docstring): its first `COUNTED` entrants in admission order, whatever
    their outcome. ValueError when the desk has not them all, or one of them was still running when it ended."""
    name = f"{desk.get('world')} replication {desk.get('replication')}"
    rows = sorted((r for r in desk["rows"] if int(r["id"]) < COUNTED), key=lambda r: int(r["id"]))
    if [int(r["id"]) for r in rows] != list(range(COUNTED)):
        raise ValueError(f"{name} has not its first {COUNTED} entrants")
    running = [int(r["id"]) for r in rows if r.get("ladder_outcome") == "running"]
    if running:
        raise ValueError(f"{name}: counted entrants {running} are still running")
    return rows


def aggregate(desks: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """THE COUNT (the module docstring), per world and pooled: false promotions (negatives) and missed signals
    (positives) under each design, and the drift control's pass shares, over the first `COUNTED` entrants of each desk.
    Counts only: it names no verdict (`VERDICT`). ValueError on a desk THE COUNT cannot take (`counted`)."""
    by: dict[str, list[Mapping[str, Any]]] = {}
    held: dict[str, int] = {}
    for d in desks:
        by.setdefault(d["world"], []).extend(counted(d))
        held[d["world"]] = held.get(d["world"], 0) + 1

    def block(mine: Sequence[Mapping[str, Any]], kind: str) -> dict[str, Any]:
        return {design: rate(sum(1 for r in mine if (r[design] if kind == "negative" else not r[design])), len(mine))
                for design in DESIGNS}

    worlds = {}
    for name, rows in sorted(by.items()):
        out: dict[str, Any] = {"desks": held[name], "entrants": len(rows)}
        for kind, label in (("negative", "false_promotions"), ("positive", "missed_signals")):
            mine = [r for r in rows if r["kind"] == kind]
            if mine:
                out[label] = block(mine, kind)
        full = [r for r in rows if (r.get("last") or {}).get("full")]
        out["drift_line_passed_share"] = round(sum(1 for r in full if r["last"].get("drift")) / len(full), 4) if full else None
        out["validation_passed_share"] = round(sum(1 for r in rows if r["validation_passed"]) / len(rows), 4)
        out["drift_held_share"] = round(sum(1 for r in rows if r["drift_hold"]) / len(rows), 4)
        worlds[name] = out
    pure = [r for name, rows in by.items() if name != MIXED for r in rows if r["kind"] == "negative"]
    mixed = by.get(MIXED, [])
    return {"counted": COUNTED, "verdict": VERDICT, "worlds": worlds, "pooled_negatives": block(pure, "negative"),
            "mixed_negatives": block([r for r in mixed if r["kind"] == "negative"], "negative"),
            "mixed_positives": block([r for r in mixed if r["kind"] == "positive"], "positive")}


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
    """The pinned definition: the protocol, the worlds and this module's source."""
    body = json.dumps({"protocol": PROTOCOL, "worlds": WORLDS, "cost": COST}, sort_keys=True)
    source = Path(__file__).read_bytes()
    return hashlib.sha256(body.encode("utf-8") + source).hexdigest()


def run(worlds: Sequence[str], replications: int, *, slots: int | None = None, sessions: int | None = None,
        seed_id: str = SEED_ID, log: Any = None) -> dict[str, Any]:
    """A PART: the desks of `worlds`, replications 0 to `replications` - 1 of each, under THE SEED ID `seed_id` (the
    judge's input: {desks: [{world, replication, rows}]}, and what `combine` takes)."""
    from dataclasses import asdict

    from league.live import ladder as L

    rules = L.Rules.from_constitution()
    started = time.time()
    desks = []
    for world in worlds:
        for r in range(int(replications)):
            desks.append(desk(world, r, slots=slots, sessions=sessions, rules=rules, seed_id=seed_id))
            if log is not None:
                print(f"{world} {r + 1}/{replications} ({time.time() - started:.0f}s)", file=log, flush=True)
    return {"suite": SUITE_ID, "suite_sha": suite_sha(), "seed_id": seed_id, "protocol": PROTOCOL, "rules": asdict(rules),
            "replications": int(replications), "worlds": list(worlds),
            "slots": int(slots or PROTOCOL["slots"]), "sessions": int(sessions or PROTOCOL["sessions"]),
            "seconds": round(time.time() - started, 1), "desks": desks}


def run_demotions(worlds: Sequence[str], *, programs: int | None = None, horizon: int | None = None,
                  seed_id: str = SEED_ID, log: Any = None) -> dict[str, Any]:
    """THE DEMOTION RULE's part (`demotions` for each world, under THE SEED ID `seed_id`), for `--combine`."""
    from dataclasses import asdict

    from league.live import ladder as L

    rules = L.Rules.from_constitution()
    started = time.time()
    out = []
    for world in worlds:
        if world == MIXED:
            continue
        out.append(demotions(world, programs=programs, horizon=horizon, rules=rules, seed_id=seed_id))
        if log is not None:
            print(f"demotion {world} ({time.time() - started:.0f}s)", file=log, flush=True)
    return {"suite": SUITE_ID, "suite_sha": suite_sha(), "seed_id": seed_id, "rules": asdict(rules),
            "seconds": round(time.time() - started, 1), "demotion": out}


def combine(parts: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Several parts as one report: the runs' desks counted (`aggregate`) and the demotion rule's parts. The same suite
    and seed id only, the runs of the same slots, sessions and replications, and no desk held twice (ValueError
    otherwise, and on a desk THE COUNT cannot take). Demotion parts alone make a report of the demotion rule: no desk,
    no count."""
    if not parts:
        raise ValueError("no part to combine")
    for key in ("suite_sha", "seed_id"):
        if len({p.get(key) for p in parts}) != 1:
            raise ValueError(f"the parts differ in {key}")
    report = {k: parts[0].get(k) for k in ("suite", "suite_sha", "seed_id", "rules")}
    report["seconds"] = round(sum(float(p.get("seconds") or 0) for p in parts), 1)
    runs = [p for p in parts if "desks" in p]
    if runs:
        first = runs[0]
        for p in runs[1:]:
            for key in ("slots", "sessions", "replications"):
                if p.get(key) != first.get(key):
                    raise ValueError(f"the parts differ in {key}")
        desks = [d for p in runs for d in p["desks"]]
        seen: set[tuple[str, int]] = set()
        for d in desks:
            key = (str(d["world"]), int(d["replication"]))
            if key in seen:
                raise ValueError(f"the parts hold {key[0]} replication {key[1]} twice")
            seen.add(key)
        report.update({k: first[k] for k in ("protocol", "replications", "slots", "sessions")})
        report["worlds"] = sorted({d["world"] for d in desks})
        report["aggregate"] = aggregate(desks)
        report["bootstrap_agreement"] = bootstrap_agreement()
    report["demotion"] = sorted((w for p in parts for w in p.get("demotion") or []), key=lambda w: w["world"])
    return report


def markdown(report: Mapping[str, Any]) -> str:
    """The private report's text: THE COUNT's figures and the demotion rule's, and no verdict (`VERDICT`)."""
    lines = [f"# Forward ladder benchmark ({report['suite']})", "",
             f"suite sha `{str(report['suite_sha'])[:16]}`; seed id `{report.get('seed_id')}`; {report['seconds']} s.", ""]

    def cell(r: Mapping[str, Any]) -> str:
        if not r["of"]:
            return "n/a"
        return f"{r['count']}/{r['of']} ({r['rate']:.4f}; 95% {r['lower_95']:.4f}-{r['upper_95']:.4f})"

    agg = report.get("aggregate")
    if agg is not None:
        lines += [f"{report['replications']} replications a world; desks of {report['slots']} practice slots over "
                  f"{report['sessions']} forward sessions. Counted: the first {agg['counted']} entrants of each desk in "
                  "admission order, whatever their outcome, for every design.", "",
                  f"**Verdict: {agg['verdict']}.**", "",
                  "## Pooled negatives (false promotions)", "", "| design | single-world desks | mixed desks |",
                  "|---|---|---|"]
        for design in DESIGNS:
            lines.append(f"| {design} | {cell(agg['pooled_negatives'][design])} | {cell(agg['mixed_negatives'][design])} |")
        lines += ["", "## The mixed desks' positives (missed signals)", "", "| design | mixed desks |", "|---|---|"]
        for design in DESIGNS:
            lines.append(f"| {design} | {cell(agg['mixed_positives'][design])} |")
        lines += ["", "## Per world", "",
                  "| world | desks | entrants | ladder | sealed (holds) | sealed (bare) | validation passed | drift hold | "
                  "drift line passed |", "|---|---|---|---|---|---|---|---|---|"]
        for name, w in agg["worlds"].items():
            for label, what in (("false_promotions", "FP"), ("missed_signals", "missed")):
                block = w.get(label)
                if block is None:
                    continue
                lines.append(f"| {name} ({what}) | {w['desks']} | {block['ladder']['of']} | {cell(block['ladder'])} | "
                             f"{cell(block['sealed'])} | {cell(block['sealed_bare'])} | {w['validation_passed_share']} | "
                             f"{w['drift_held_share']} | {w['drift_line_passed_share']} |")
        lines += ["", f"Bootstrap port agreement (max p gap): {report['bootstrap_agreement']['max_p_gap']}.", ""]
    if report.get("demotion"):
        marks = [str(m) for m in DEMOTION["marks"]]
        lines += ["## The demotion rule (a program promoted at session 0, its world's forward stream as real fills)", "",
                  "Demoted within " + ", ".join(marks) + " sessions (count/programs). A planted edge demoted is a real "
                  "edge lost; a negative one demoted is the rule working.", "",
                  "| world | " + " | ".join(DEMOTION_READINGS) + " |", "|---|" + "---|" * len(DEMOTION_READINGS)]
        for w in report["demotion"]:
            cells = []
            for name in DEMOTION_READINGS:
                by = w["readings"][name]
                cells.append(" / ".join(f"{by[m]['count']}" for m in marks if m in by) + f" of {w['programs']}")
            lines.append(f"| {w['world']} ({w['kind']}) | " + " | ".join(cells) + " |")
        lines.append("")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    """Run worlds (a part: `--output` keeps its desks for the judge and for `--combine`), or combine parts into the
    report. 2 when the desks are not ones THE COUNT can take (the part is written first)."""
    parser = argparse.ArgumentParser(prog="python -m league.swarm.forward_benchmarks")
    parser.add_argument("--world", action="append", choices=sorted(WORLDS) + [MIXED])
    parser.add_argument("--replications", type=int, default=PROTOCOL["replications"])
    parser.add_argument("--seed-id", default=SEED_ID, help="THE SEED ID of the generator's streams (default: the "
                                                           "development desks')")
    parser.add_argument("--slots", type=int)
    parser.add_argument("--sessions", type=int)
    parser.add_argument("--combine", nargs="+", help="parts written by --output, combined into one report")
    parser.add_argument("--output", help="a run: its desks (a part); --combine: the combined report")
    parser.add_argument("--report", help="the markdown report")
    parser.add_argument("--json", action="store_true", help="print the headline")
    parser.add_argument("--demotion", action="store_true", help="the demotion rule's part (`demotions`), not the desks")
    parser.add_argument("--programs", type=int, help="--demotion: programs a world")
    args = parser.parse_args(argv)
    if args.demotion:
        part = run_demotions(args.world or sorted(WORLDS), programs=args.programs, seed_id=args.seed_id, log=sys.stderr)
        if args.output:
            Path(args.output).write_text(json.dumps(part, sort_keys=True, default=str))
        if args.json:
            print(json.dumps({w["world"]: {n: {m: r["count"] for m, r in by.items()} for n, by in w["readings"].items()}
                              for w in part["demotion"]}, indent=1))
        return 0
    if args.combine:
        parts = [json.loads(Path(p).read_text()) for p in args.combine]
    else:
        part = run(args.world or sorted(WORLDS) + [MIXED], args.replications, slots=args.slots, sessions=args.sessions,
                   seed_id=args.seed_id, log=sys.stderr)
        if args.output:
            Path(args.output).write_text(json.dumps(part, sort_keys=True, default=str))
        parts = [part] if (args.report or args.json) else []
    report = None
    if parts:
        try:
            report = combine(parts)
        except ValueError as exc:
            print(f"forward_benchmarks: no report: {exc}", file=sys.stderr)
            return 2
        if args.combine and args.output:
            Path(args.output).write_text(json.dumps(report, sort_keys=True, default=str))
    if args.report and report is not None:
        Path(args.report).write_text(markdown(report))
    if args.json and report is not None:
        agg = report.get("aggregate") or {}
        print(json.dumps({k: report.get(k) for k in ("suite", "suite_sha", "seed_id", "replications", "slots", "sessions",
                                                     "seconds")}
                         | {"counted": agg.get("counted"), "pooled": agg.get("pooled_negatives"),
                            "mixed": agg.get("mixed_negatives"), "mixed_positives": agg.get("mixed_positives"),
                            "verdict": VERDICT}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
