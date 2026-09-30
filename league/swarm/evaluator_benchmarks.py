"""The evaluator benchmark suite: known-answer cases run through the real Gym engine and the real evidence lines.

    python -m league.swarm.benchmarks --suite evaluator --json [--output FULL] [--receipt RECEIPT] [--compare OLD]
    python -m league.swarm.benchmarks --suite evaluator --cohort confirmation --frozen DEVELOPMENT --json ...
    python -m league.swarm.benchmarks --suite evaluator --tree CHECKOUT ...   # an operator tool for trusted trees

Each case is a synthetic program with a known answer, run on a synthetic store (never licensed data, never the sealed
market holdout) through the evaluator's mechanical stages exactly as the swarm runs them:

    static contract (`check_experiment` with the case's parameters) -> Train (normal and 1.5x-stress runs) ->
    Train eligibility (`evidence.train_score`) and the drift screen -> Validation (normal and 1.5x-stress runs,
    `evidence.validation_line`) -> review -> one synthetic holdout look (`evidence.holdout_line`, Holm across a fixed
    prior history). The gate's own static and drift checks repeat the first two and are not scored twice.

The review is a model call. The suite makes none: it scores the pipeline with a BLIND reviewer (one that passes every
program), so a false promotion here is one the mechanical evaluator allows and only a model review could stop. Cases
whose sole defense is the review are labelled `review_dependent`, and the suite separately checks that the review
contract can carry a grounded rejection of each such case (`review_contract.grounded_answer`).

Case families (the suite's pinned `CASES`):
- signal controls: absent, cost-erased, drift-only and holdout-disappearing negatives; planted dense, sparse,
  medium-frequency, conditional-regime and year-regime positives;
- LEAKAGE: programs that try to read the future through the ctx paths tested (indexing past now, array bases, the
  engine's greek cache behind a private attribute, a date table reached by reconstructing the session's date, greeks
  computed in blocks, prior-session bars, bar volume without publication receipts, a process-global numpy dict carried
  from an earlier run) and memorized tables a static check cannot see (keyed by price level, densely and sparsely, and
  by a session counter from a recognized window start). Each must be refused or score as no edge, except the memorized
  tables, which only the review can stop (`review_dependent`). The greek-cache and date-table probes profit when the
  static check is opened for them (a unit test opens it); the array-base probe has a second guard, the engine's copy
  (an array's base is a bytes copy of today so far), so it learns nothing even then. The numpy memo reaches
  `np.typecodes` only. Next-session event flags are a smoke test (`kind: smoke`): the world's moves do not depend on
  the calendar, so that probe cannot profit and is kept out of the rates;
- INVALID FILLS: programs that profit only from impossible fills: the decision minute's stale quote, crossed quotes,
  package prices beyond the payoff range on open and close, and passive spread capture without adverse selection;
- STATE: contract proofs that module STATE resets between runs, that parameters are copied, that a split Train run
  matches the unsplit run day for day and Validation is never split, and probes for channels between runs and between
  batch-mates: each of numpy's two mutable public dicts (`typecodes`, `sctypeDict`) on its own, every mutable public
  numpy container the static check lets a program reach (enumerated at run time, so a partial fix shows), and a ctx
  object shared by a batch;
- BROKEN ABLATIONS: switches that work, that the static contract refuses, and that are read but ignored (which only a
  behavioral ablation catches);
- a SEARCH tier: the same statistical lines on generated outcomes with lineage selection over noise variants, where
  lowered activity floors would be most dangerous.

The report gives, per release tree: the false-promotion rate over negative cases and the missed-signal rate over
planted positives, each with exact (Clopper-Pearson) 95% bounds per case-world and per case (outcomes cluster by case,
so the case counts are the effective sample); the contract proofs and defects found (mapped to the review contract's
facts); ablation detection by the static contract and by a behavioral probe; and threshold variants judged on the same
recorded outcomes (`VARIANTS`, never applied) against the owner's rule, with a sensitivity check that the verdict
rejects the no-floors reference. Its `headline` is a per-case vector (promotions per negative, misses per positive,
static refusals, impossible fills and stress contamination per case, the review contract's answers per case, proofs,
ablations); `compare` lists regressions between two headlines of the same suite, cohort and fixture, never on the
pooled rates alone. A variant's owner-rule verdict on one cohort is never a confirmed one: a confirmation run records,
per variant, whether the frozen development verdict and its own were both met (`met_and_confirmed`).

Cohorts: `development` (the default; EVALUATOR_1's figures) and `confirmation`, whose worlds and search streams are
independent. A confirmation run must name the frozen development report (`--frozen`) of the same pinned suite, tree
and sample counts, so a variant chosen on development is judged on data it was not chosen on.

The suite is pinned: `PINNED_SUITE_SHA` is the hash of the protocol, the world, every case and template, the search
tier, the variants and this module's source, read from this file on disk. A run whose computed hash differs is reported
`pinned: false` and the CLI exits 3 (`--allow-unpinned` is for developing the next suite id only). The world's option
prices and the bounds are computed here (vendored), not by the scored tree; the store writer and the fill model must
match the tree's store and engine, so they come from its `league/gym/synth.py`, whose hash is the report's
`fixture_sha` (headlines with different fixtures are not compared).

`--tree` runs this suite file against another checkout's `league` package in a child process. The candidate's code
runs in the suite's interpreter with the operator's environment (home, credentials, network), so it guards against
ACCIDENTAL drift of the cases (a candidate's own copy of the suite is never used), not against a hostile tree: use it
on trusted trees only. It is not a harness-lane judge (no lane runs it; its CPU time exceeds the lane sandbox's).

What it does not do: call a model, read market data or sealed days, change a threshold, write to a swarm, place an
order, or claim anything about a real strategy's edge. The worlds are invented; the planted edges are deliberately
strong controls; finite counts bound error rates only for this suite's fixed case mix. The engine tier needs numpy and
pyarrow (the Gym's); the search tier and the variant judging need neither.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import random
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

SUITE_ID = "evaluator-suite-1"

# ------------------------------------------------------------------------------------------------ the synthetic world
#: One synthetic underlying, priced so options are fair (a martingale) whenever no edge is planted. The calendar is a
#: thinned weekday calendar (every `stride`-th weekday), not an exchange calendar. Dollar units throughout.
WORLD: dict[str, Any] = {
    "root": "SPY",
    "spot0": 400.0,
    "years": {"train": [2022, 2023, 2024], "validation": [2025], "holdout": [2026]},
    "holdout_last": "2026-09-25",
    "stride": 4,
    "history_sessions": 5,
    "minute_sd": 0.20,
    "drift_per_minute": 0.002,
    "gap_sd": 2.0,
    "tell_minutes": [600, 605, 610, 615, 620, 625, 630, 635, 640],
    "tell_size": 1.0,
    "big_tell_size": 3.0,
    "window_minutes": [650, 680, 710, 740, 770, 800, 830, 860, 890],
    "window_length": 30,
    "quote_from": 645,
    "strikes_each_side": 10,
    "half_spread": 0.03,
    "quote_size": 50,
    "expiry_days": 1,
    "next_session_minutes": 390,
    "jump_minute": 921,
    "jump_size": 2.0,
    "blowout_close_minutes": [930, 934],
    "blowout_open_minutes": [940, 944],
    "crossed_minutes": [950, 954],
    "blowout": 5.0,
    "crossed_offset": 4.0,
    "fill_hazard": 0.3,
    "volume_up": 1000.0,
    "volume_down": 2000.0,
    "sparse_move": 1.4,
    "mark_minutes": 20,
}

#: The minutes (indexes into today's prices) whose up/down signs fingerprint a session: the first `mark_minutes` minutes
#: after the open and every tell. Signs survive any price scale; 29 of them make every session's mark distinct in
#: practice, which is what a memorized session table needs to recognize where a window starts.
MARK_INDEXES = tuple(range(1, WORLD["mark_minutes"] + 1)) + tuple(m - 570 for m in WORLD["tell_minutes"])

#: The seed streams: development (EVALUATOR_1's) and an independent confirmation cohort.
COHORTS = ("development", "confirmation")

#: The planted channels: channel k's tell is `tell_minutes[k]`, its window starts at `window_minutes[k]`. `amount` is the
#: planted shift of the window's move in the tell's direction ($, spread evenly over the window's minutes), on the days
#: `on` names: "all", "big" (a big tell, probability `big`), "gap" (|overnight gap| over `gap` dollars), or a year list.
CHANNELS: dict[str, dict[str, Any]] = {
    "dense": {"k": 0, "amount": 0.70, "on": "all"},
    "sparse": {"k": 1, "amount": 1.60, "on": "big", "big": 0.2},
    "medium": {"k": 2, "amount": 0.80, "on": "big", "big": 0.74},
    "gap": {"k": 3, "amount": 1.10, "on": "gap", "gap": 2.0},
    "years": {"k": 4, "amount": 0.70, "on": [2023, 2024, 2025, 2026]},
    "fading": {"k": 5, "amount": 0.70, "on": [2022, 2023, 2024, 2025]},
    "cost": {"k": 6, "amount": 0.06, "on": "all"},
    "absent": {"k": 7, "amount": 0.0, "on": "all"},
}


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _seed(cohort: str, *parts: Any) -> str:
    """A stream's seed. Development's streams are the suite's first ones; confirmation's hash the cohort's name in, so
    they are independent of everything development showed."""
    if cohort not in COHORTS:
        raise ValueError(f"unknown cohort {cohort!r}")
    return digest([SUITE_ID, *parts] if cohort == "development" else [SUITE_ID, cohort, *parts])


def sessions() -> dict[str, list[dt.date]]:
    """The world's sessions per window: every `stride`-th weekday of each year (the holdout to `holdout_last`)."""
    out: dict[str, list[dt.date]] = {}
    last = dt.date.fromisoformat(WORLD["holdout_last"])
    for window, years in WORLD["years"].items():
        days = []
        for year in years:
            day, n = dt.date(year, 1, 3), 0
            while day.year == year and day <= (last if window == "holdout" else dt.date(year, 12, 31)):
                if day.weekday() < 5:
                    if n % WORLD["stride"] == 0:
                        days.append(day)
                    n += 1
                day += dt.timedelta(days=1)
        out[window] = days
    return out


def history_days(first: dt.date) -> list[dt.date]:
    """Underlying-only sessions before the first Train day (a program's history going into it)."""
    out, day = [], first - dt.timedelta(days=1)
    while len(out) < WORLD["history_sessions"]:
        if day.weekday() < 5:
            out.append(day)
        day -= dt.timedelta(days=1)
    return sorted(out)


#: The standard normal CDF by Abramowitz and Stegun 26.2.17, vendored (the same constants the Gym's greeks use) so the
#: world's option prices come from the pinned suite, never from the tree being scored.
_AS_P = 0.2316419
_AS_B = (0.319381530, -0.356563782, 1.781477937, -1.821255978, 1.330274429)


def norm_pdf(x: Any) -> Any:
    import numpy as np

    return np.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def norm_cdf(x: Any) -> Any:
    import numpy as np

    x = np.asarray(x, dtype=np.float64)
    a = np.abs(x)
    t = 1.0 / (1.0 + _AS_P * a)
    poly = t * (_AS_B[0] + t * (_AS_B[1] + t * (_AS_B[2] + t * (_AS_B[3] + t * _AS_B[4]))))
    upper = norm_pdf(a) * poly  # P(Z > |x|)
    return np.where(x >= 0.0, 1.0 - upper, upper)


def _bachelier(spot: Any, strike: Any, variance: Any, call: Any) -> Any:
    """E[max(S_T - K, 0)] (call) or E[max(K - S_T, 0)] (put) for S_T ~ N(spot, variance): the fair price when the rest of
    the day is Gaussian and driftless, so a quote path built from it is a martingale (no edge unless one is planted)."""
    import numpy as np

    sd = np.sqrt(np.maximum(variance, 1e-12))
    d = (spot - strike) / sd
    value_call = (spot - strike) * norm_cdf(d) + sd * norm_pdf(d)
    return np.where(call, value_call, value_call - (spot - strike))


def truth(replication: int, cohort: str = "development") -> dict[str, Any]:
    """The world's hidden truth for one replication: per session, the tells, the planted shifts, the window moves, the
    jump. Everything a store is written from, and what the suite checks a probe's hit rate against."""
    rng = random.Random(_seed(cohort, "world", replication))
    windows = sessions()
    first = windows["train"][0]
    days = [(d, "history") for d in history_days(first)]
    for window in ("train", "validation", "holdout"):
        days += [(d, window) for d in windows[window]]
    rows = []
    for day, window in days:
        tells = [1 if rng.random() < 0.5 else -1 for _ in WORLD["tell_minutes"]]
        big = [rng.random() for _ in WORLD["tell_minutes"]]
        gap = rng.gauss(0.0, WORLD["gap_sd"])
        jump = 1 if rng.random() < 0.5 else -1
        seed = rng.getrandbits(63)
        planted = {}
        for name, spec in CHANNELS.items():
            k = spec["k"]
            if spec["on"] == "all":
                on = True
            elif spec["on"] == "big":
                on = big[k] < spec["big"]
            elif spec["on"] == "gap":
                on = abs(gap) > spec["gap"]
            else:
                on = day.year in spec["on"]
            planted[name] = spec["amount"] * tells[k] if on and window != "history" else 0.0
        bigs = {name: bool(big[spec["k"]] < spec.get("big", -1.0)) for name, spec in CHANNELS.items()}
        rows.append({"day": day, "window": window, "tells": tells, "big": bigs, "gap": gap, "jump": jump,
                     "seed": seed, "planted": planted})
    return {"replication": replication, "cohort": cohort, "days": rows}


def _path(row: Mapping[str, Any], open_price: float):
    """One session's underlying price at each minute 570..960: Gaussian minutes with the drift, the tells, the planted
    shifts spread over their windows and the jump."""
    import numpy as np

    rng = np.random.default_rng(row["seed"])
    minutes = np.arange(570, 961)
    sd, mu = WORLD["minute_sd"], WORLD["drift_per_minute"]
    step = mu + rng.normal(0.0, sd, minutes.size)
    step[0] = 0.0
    big = {CHANNELS[name]["k"]: flag for name, flag in row["big"].items()}
    for k, minute in enumerate(WORLD["tell_minutes"]):
        size = WORLD["big_tell_size"] if big.get(k) else WORLD["tell_size"]
        step[minute - 570] = mu + row["tells"][k] * size
    length = WORLD["window_length"]
    for name, spec in CHANNELS.items():
        start = WORLD["window_minutes"][spec["k"]]
        step[start - 570 + 1: start - 570 + 1 + length] += row["planted"][name] / length
    step[WORLD["jump_minute"] - 570] = mu + row["jump"] * WORLD["jump_size"]
    price = open_price + np.cumsum(step)
    return price


def write_world(root: Path, world: Mapping[str, Any], *, level_scale: float = 1.0,
                windows: Sequence[str] = ("train", "validation", "holdout")) -> dict[str, Any]:
    """Write the replication's store (with the gate's mark: the synthetic holdout is the suite's, never the market's) and
    return what was realized: each session's opening price, each channel window's move and the session's mark (the signs
    at `MARK_INDEXES`, which no price scale changes). `level_scale` multiplies every
    price (the level-invariance probe's world: relative signals are unchanged by it); `windows` limits the chains written
    (the underlying is written for every session, so history is continuous)."""
    import numpy as np

    from league.gym import synth

    writer = synth.Writer(root)
    rows = world["days"]
    writer.calendar([r["day"] for r in rows])
    expiry_rows = []
    close = WORLD["spot0"]
    root_name = WORLD["root"]
    minutes = np.arange(570, 961)
    q0 = WORLD["quote_from"] - 570
    qmin = minutes[q0:]
    sd2 = WORLD["minute_sd"] ** 2
    after = sd2 * WORLD["next_session_minutes"] + WORLD["gap_sd"] ** 2
    jump_i = WORLD["jump_minute"] - 570
    length = WORLD["window_length"]
    moves: list[dict[str, float]] = []
    opens: list[float] = []
    marks: list[str] = []
    for r in rows:
        day = r["day"]
        open_price = close + r["gap"]
        price = _path(r, open_price)
        close = float(price[-1])
        opens.append(float(price[0]))
        marks.append("".join("u" if price[i] > price[i - 1] else "d" for i in MARK_INDEXES))
        moves.append({name: float(price[WORLD["window_minutes"][spec["k"]] - 570 + length] -
                                  price[WORLD["window_minutes"][spec["k"]] - 570])
                      for name, spec in CHANNELS.items()} if r["window"] != "history" else {})
        # A volume column with no publication receipts, every bar of which encodes the absent window's LATER move: the
        # replay must never show historical volume without first-observation receipts (NaN), or the day leaks.
        up = bool(moves[-1]) and moves[-1]["absent"] > 0
        volume = np.full(minutes.size, WORLD["volume_up"] if up else WORLD["volume_down"], dtype=np.float64)
        writer.underlying(root_name, day, minutes, price * level_scale, extra={"volume": volume})
        if r["window"] not in windows:
            continue
        # The listed strikes centre on the price when quotes begin (causal: a past price).
        centre = round(float(price[q0]))
        strikes = centre + np.arange(-WORLD["strikes_each_side"], WORLD["strikes_each_side"] + 1, dtype=np.float64)
        expiry = day + dt.timedelta(days=WORLD["expiry_days"])
        expiry_rows.append((root_name, day, expiry))
        # Remaining variance from each quoted minute: the day's Gaussian minutes, the jump while it is ahead, the next
        # session. The quote at the jump minute is STALE (the previous minute's), refreshed a minute later.
        seen = price[q0:].copy()
        seen[jump_i - q0] = price[jump_i - 1]
        remaining = sd2 * (960 - qmin) + after + np.where(qmin < WORLD["jump_minute"], WORLD["jump_size"] ** 2, 0.0)
        remaining[jump_i - q0] = sd2 * (960 - WORLD["jump_minute"] + 1) + after + WORLD["jump_size"] ** 2
        k_close = float(strikes[np.argmin(np.abs(strikes - price[925 - 570]))])
        k_open = float(strikes[np.argmin(np.abs(strikes - price[939 - 570]))])
        k_cross = float(strikes[np.argmin(np.abs(strikes - (price[949 - 570] + WORLD["crossed_offset"])))])
        exp_l, k_l, r_l, m_l, bid_l, ask_l = [], [], [], [], [], []
        for strike in strikes:
            for call in (True, False):
                mid = _bachelier(seen, strike, remaining, call)
                half = WORLD["half_spread"]
                bid = np.maximum(0.0, np.round(mid - half, 2))
                ask = np.maximum(np.round(mid + half, 2), bid + 0.01)
                for when, hit in ((WORLD["blowout_close_minutes"], call and strike == k_close),
                                  (WORLD["blowout_open_minutes"], call and strike == k_open + 1.0)):
                    if hit:  # a leg's bid blows out: a vertical's natural leaves its payoff range
                        a, b = (m - 570 - q0 for m in when)
                        bid[a:b + 1] = np.round(mid[a:b + 1] + WORLD["blowout"], 2)
                        ask[a:b + 1] = bid[a:b + 1] + 0.5
                if call and strike == k_cross:  # crossed quotes: bid above ask (never a market)
                    a, b = (m - 570 - q0 for m in WORLD["crossed_minutes"])
                    bid[a:b + 1] = np.round(mid[a:b + 1] + 0.3, 2)
                    ask[a:b + 1] = np.round(np.maximum(0.01, mid[a:b + 1] - 0.3), 2)
                n = qmin.size
                exp_l += [expiry] * n
                k_l.append(np.full(n, strike))
                r_l += ["C" if call else "P"] * n
                m_l.append(qmin)
                bid_l.append(bid * level_scale)
                ask_l.append(ask * level_scale)
        size = np.full(len(exp_l), WORLD["quote_size"], dtype=np.int32)
        writer.nbbo(root_name, day, expiration=exp_l, strike=np.concatenate(k_l) * level_scale, right=r_l,
                    minute=np.concatenate(m_l), bid=np.concatenate(bid_l), ask=np.concatenate(ask_l),
                    bid_size=size, ask_size=size)
    writer.expiries(expiry_rows)
    writer.gate_mark()
    writer.finish()
    return {"moves": moves, "opens": opens, "marks": marks}


# ------------------------------------------------------------------------------------------------ the programs
#: Program templates ($NAME placeholders). Each is a complete Gym program; the suite's hash covers every template.
#: Every program enters with a marketable limit (the ATM contract's ask plus a dollar: a marketable order fills at the
#: natural, never at its limit) and exits the same way, so no case depends on a resting order's luck.
ENTRY = '''
def enter(ctx, right, tag=""):
    ch = ctx.chain
    if ch is None or not ch.n:
        return []
    pick = np.flatnonzero(ch.is_call) if right == "C" else np.flatnonzero(~ch.is_call)
    if not pick.size:
        return []
    i = int(pick[int(np.argmin(np.abs(ch.strike[pick] - ch.spot)))])
    return [{"open": "long_call" if right == "C" else "long_put", "root": "SPY", "qty": 1, "tag": tag,
             "limit": {"price": round(float(ch.ask[i]) + 1.0, 2)},
             "legs": [{"side": "long", "right": right, "dte": 1, "id": int(ch.id[i])}]}]
def leave(ctx):
    return [{"close": p["id"], "limit": {"price": 0.0}} for p in ctx.positions]
'''

SIGNAL = '''
import numpy as np
NEEDS = {"roots": ["SPY"], "dte": [1, 1], "band": 0.03, "cadence": 30, "history": 3, "start": $START, "end": $END}
PARAMS = {"signal_on": 1, "min_tell": $MIN_TELL, "gap": $GAP}
''' + ENTRY + '''
def decide(ctx):
    if ctx.minute != $START:
        return leave(ctx)
    if not ctx.params["signal_on"]:
        return []
    p = ctx.under.prices
    jump = float(p[$TELL] - p[$TELL - 1])
    if abs(jump) < ctx.params["min_tell"]:
        return []
    if ctx.params["gap"] > 0 and not abs(ctx.under.open - ctx.under.prior_close) > ctx.params["gap"]:
        return []
    return enter(ctx, "C" if jump > 0 else "P", "signal")
'''

DRIFT_ONLY = '''
import numpy as np
NEEDS = {"roots": ["SPY"], "dte": [1, 1], "band": 0.03, "cadence": 30, "history": 0, "start": 649, "end": 919}
PARAMS = {"side": "C"}
''' + ENTRY + '''
def decide(ctx):
    if ctx.minute == 649:
        return enter(ctx, ctx.params["side"])
    if ctx.minute == 919:
        return leave(ctx)
    return []
'''

#: The leakage probes trade the absent channel's window: whatever they learn of its future is the only edge there.
#: `$GUESS` is the probe's attempt; a zero guess falls back to the absent channel's tell (a coin).
LEAK = '''
import math
import numpy as np
NEEDS = {"roots": ["SPY"], "dte": [1, 1], "band": 0.03, "cadence": 30, "history": 3, "start": $START, "end": $END}
PARAMS = {"probe": 1}
STATE = {"session": 0}
$PRELUDE
''' + ENTRY + '''
def decide(ctx):
    if ctx.minute != $START:
        $AFTER
        return leave(ctx)
    STATE["session"] += 1
    p = ctx.under.prices
    coin = float(p[$TELL] - p[$TELL - 1])
    guess = 0.0
    $GUESS
    side = guess if guess != 0.0 else coin
    return enter(ctx, "C" if side > 0 else "P", "leak" if guess != 0.0 else "coin")
'''

LEAKS: dict[str, dict[str, str]] = {
    # The window's future move by index: the array ends now, so the index is out of range.
    "leak_future_index": {"PRELUDE": "", "AFTER": "", "GUESS": '''try:
        guess = float(p[$STOP] - p[$BEGIN])
    except IndexError:
        guess = 0.0'''},
    # The array's backing buffer (a view would carry the rest of the day): refused by the static check, and guarded a
    # second time by the engine, which hands out a copy whose base is a bytes copy of today so far (opened, it reads
    # bytes, not prices, and learns nothing).
    "leak_array_base": {"PRELUDE": "", "AFTER": "", "GUESS": '''whole = ctx.under.prices.base
    if whole is not None and len(whole) > $STOP:
        guess = float(whole[$STOP] - whole[$BEGIN])'''},
    # The chain view's private snapshot, whose greeks source reaches the engine's greek cache and through it the whole
    # day's underlying prices: refused by the static check. If the route opened, the window's move would be read straight
    # out of the cache (the source is a closure over the cache, or a bound method of it: both are searched).
    "leak_private_attr": {"PRELUDE": "", "AFTER": "", "GUESS": '''snap = getattr(ctx.chain, "_snap")
    source = getattr(snap, "_source", None) if snap is not None else None
    holders = [source, getattr(source, "__self__", None)] + list(getattr(source, "__defaults__", None) or ())
    for cache in holders:
        chain = getattr(cache, "chain", None)
        if chain is not None:
            whole = chain.underlying.price
            if len(whole) > $STOP:
                guess = float(whole[$STOP] - whole[$BEGIN])
            break'''},
    # A remembered calendar: the session's date is reconstructed (a recognized window start and a session count) and
    # looked up in a table of dates. Refused by the static check (ISO dates); if the check let it through, it profits.
    "leak_date_literal": {"PRELUDE": "DATES = $DATED\nMOVES = $MOVES", "AFTER": "", "GUESS": '''mark = "".join("u" if p[k] > p[k - 1] else "d" for k in $MARKS)
    if mark in DATES:
        STATE["run"], STATE["n"] = mark, 0
    row = DATES.get(STATE.get("run"), ())
    n = STATE.get("n", 0)
    STATE["n"] = n + 1
    guess = float(MOVES.get(row[n], 0.0)) if n < len(row) else 0.0'''},
    # The greeks are solved in blocks that include later minutes; only this minute's row is handed out.
    "leak_greeks_block": {"PRELUDE": "", "AFTER": "", "GUESS": '''ch = ctx.chain
    if ch is not None and ch.n:
        calls = np.flatnonzero(ch.is_call)
        if calls.size:
            i = calls[int(np.argmin(np.abs(ch.strike[calls] - ch.spot)))]
            d = float(ch.delta[i]) - 0.5
            guess = d if math.isfinite(d) else 0.0'''},
    # Next-session event flags are scheduled public calendars, not outcomes. A SMOKE test: the world's moves do not
    # depend on the calendar, so this probe cannot profit whatever the engine does; it is kept out of the rates.
    "leak_events_next": {"PRELUDE": "", "AFTER": "", "GUESS": '''flags = sum(1 for v in ctx.events_next.values() if v) - sum(1 for v in ctx.events.values() if v)
    guess = float(flags)'''},
    # A process-global numpy dict carries what an earlier run saw (the window's realized move, by session) into a later
    # run over the same sessions: the 1.5x-stress twin, a rerun. Never the only run of a window. It reaches
    # `np.typecodes` only; the state proofs test every numpy container on its own.
    "leak_numpy_memo": {"PRELUDE": 'MEMO = np.typecodes', "AFTER": '''if ctx.minute == $END:
            key = "ltcm-bench-memo-" + str(STATE["session"])
            MEMO[key] = "u" if float(ctx.under.prices[-1] - ctx.under.prices[$BEGIN]) > 0 else "d"''',
                        "GUESS": '''seen = MEMO.get("ltcm-bench-memo-" + str(STATE["session"]))
    guess = 1.0 if seen == "u" else -1.0 if seen == "d" else 0.0'''},
    # Prior-session bars (closes, highs, lows and opens join the history together at a replayed day's close): if today's
    # row were among them, today's close minus the price now would carry the rest of the day, the window included.
    "leak_daily_bars": {"PRELUDE": "", "AFTER": "", "GUESS": '''closes = ctx.under.closes
    if len(closes) and math.isfinite(float(closes[-1])):
        guess = float(closes[-1]) - float(ctx.under.price)'''},
    # Historical bar volume without publication receipts: here every bar of the day encodes the window's later move.
    "leak_volume_bars": {"PRELUDE": "", "AFTER": "", "GUESS": '''bars = ctx.under.minute_volumes
    if len(bars) and math.isfinite(float(bars[0])):
        guess = 1.0 if float(bars[0]) < 1500.0 else -1.0'''},
    # A memorized history keyed by the session's opening price level (what a model that remembers a period could
    # embed): only the review, or a level-invariance probe, can see it. $TABLE is the replication's truth.
    "leak_memorized_levels": {"PRELUDE": "KNOWN = $TABLE", "AFTER": "", "GUESS": '''guess = float(KNOWN.get(round(float(ctx.under.open), 2), 0.0))'''},
    # The same memory kept only for the sessions whose window moved most (about one in five), trading nowhere else: so
    # sparse that today's activity floors stop it at Train. The suite's SENSITIVITY control: a negative the floors are
    # known to stop, so a variant that lowers them shows whether it lets memorized sparse tables reach the holdout.
    "leak_memorized_sparse": {"PRELUDE": "KNOWN = $SPARSE_TABLE", "AFTER": "", "GUESS": '''guess = float(KNOWN.get(round(float(ctx.under.open), 2), 0.0))
    if guess == 0.0:
        return []'''},
    # A memorized direction list indexed by a session counter from a recognized window start (the signs of the day's
    # first minutes and tells): no date literal and nothing keyed to the price level, so neither the static check nor
    # the level-invariance probe sees it. Only the review can.
    "leak_memorized_sessions": {"PRELUDE": "KNOWN = $SESSIONS", "AFTER": "", "GUESS": '''mark = "".join("u" if p[k] > p[k - 1] else "d" for k in $MARKS)
    if mark in KNOWN:
        STATE["run"], STATE["n"] = mark, 0
    row = KNOWN.get(STATE.get("run"), ())
    n = STATE.get("n", 0)
    STATE["n"] = n + 1
    guess = float(row[n]) if n < len(row) else 0.0'''},
}

#: The invalid-fill probes each trade only where the world plants an impossible price (after every signal window).
FILLS: dict[str, str] = {
    # The quote at the jump minute is stale: buying it would need a fill at the decision minute's quote.
    "fill_stale_quote": '''
import numpy as np
NEEDS = {"roots": ["SPY"], "dte": [1, 1], "band": 0.03, "cadence": 4, "history": 0, "start": 921, "end": 925}
PARAMS = {"probe": 1}
''' + ENTRY + '''
def decide(ctx):
    if ctx.minute == 921:
        p = ctx.under.prices
        return enter(ctx, "C" if float(p[-1] - p[-2]) > 0 else "P")
    return leave(ctx)
''',
    # The long leg's bid blows out: a close would receive more than the vertical's width.
    "fill_close_above_width": '''
NEEDS = {"roots": ["SPY"], "dte": [1, 1], "band": 0.03, "cadence": 1, "history": 0, "start": 925, "end": 955}
PARAMS = {"probe": 1}
def decide(ctx):
    if ctx.minute == 925:
        return [{"open": "debit_vertical", "root": "SPY", "qty": 1, "limit": {"price": 0.99},
                 "legs": [{"side": "long", "right": "C", "dte": 1, "atm": 0},
                          {"side": "short", "right": "C", "rel": 0, "offset": 1.0}]}]
    if ctx.minute in (929, 955) and ctx.positions and not ctx.orders:
        return [{"close": p["id"], "limit": {"price": 0.0}} for p in ctx.positions]
    return []
''',
    # The short leg's bid blows out: an open would be paid to take a vertical that is never worth less than zero.
    "fill_open_below_zero": '''
NEEDS = {"roots": ["SPY"], "dte": [1, 1], "band": 0.03, "cadence": 1, "history": 0, "start": 939, "end": 955}
PARAMS = {"probe": 1}
def decide(ctx):
    if ctx.minute == 939:
        return [{"open": "debit_vertical", "root": "SPY", "qty": 1, "limit": {"price": 0.99},
                 "legs": [{"side": "long", "right": "C", "dte": 1, "atm": 0},
                          {"side": "short", "right": "C", "rel": 0, "offset": 1.0}]}]
    if ctx.minute in (946, 955) and ctx.positions and not ctx.orders:
        return [{"close": p["id"], "limit": {"price": 0.0}} for p in ctx.positions]
    return []
''',
    # Crossed quotes (bid above ask): buy the ask, sell the bid a minute later, riskless if they were a market.
    "fill_crossed_quotes": '''
NEEDS = {"roots": ["SPY"], "dte": [1, 1], "band": 0.05, "cadence": 1, "history": 0, "start": 949, "end": 957}
PARAMS = {"probe": 1}
def decide(ctx):
    if ctx.minute == 949:
        return [{"open": "long_call", "root": "SPY", "qty": 1, "limit": {"price": 30.0},
                 "legs": [{"side": "long", "right": "C", "dte": 1, "strike": ctx.chain.spot + $OFFSET}]}]
    if ctx.positions and not ctx.orders:
        return [{"close": p["id"], "limit": {"price": 0.0}} for p in ctx.positions]
    return []
''',
    # Passive spread capture on the ATM call: bid at the touch, offer at the touch, over and over. Without adverse
    # selection a hazard alone would hand it the spread.
    "fill_passive_spread": '''
import numpy as np
NEEDS = {"roots": ["SPY"], "dte": [1, 1], "band": 0.03, "cadence": 2, "history": 0, "start": 860, "end": 918}
PARAMS = {"tif": 2}
def decide(ctx):
    ch = ctx.chain
    if ctx.minute >= 916:
        out = [{"cancel": o["id"]} for o in ctx.orders]
        return out + [{"close": p["id"], "limit": {"price": 0.0}} for p in ctx.positions if not ctx.orders]
    if ctx.orders or ch is None or not ch.n:
        return []
    calls = np.flatnonzero(ch.is_call)
    i = int(calls[int(np.argmin(np.abs(ch.strike[calls] - ch.spot)))])
    if ctx.positions:
        return [{"close": ctx.positions[0]["id"], "limit": {"price": float(ch.ask[i])}, "tif": ctx.params["tif"]}]
    return [{"open": "long_call", "root": "SPY", "qty": 1, "limit": {"price": float(ch.bid[i])}, "tif": ctx.params["tif"],
             "legs": [{"side": "long", "right": "C", "dte": 1, "id": int(ch.id[i])}]}]
''',
}

#: The broken-ablation cases: the dense channel's program with its switch wired five ways. `signal_on=0` must remove
#: every trade; the static contract refuses only a changed override it can prove unread.
ABLATION = '''
import numpy as np
NEEDS = {"roots": ["SPY"], "dte": [1, 1], "band": 0.03, "cadence": 30, "history": 0, "start": $START, "end": $END}
PARAMS = {"signal_on": 1}
$PRELUDE
''' + ENTRY + '''
def decide(ctx):
    if ctx.minute != $START:
        return leave(ctx)
    $TEST
    p = ctx.under.prices
    return enter(ctx, "C" if float(p[$TELL] - p[$TELL - 1]) > 0 else "P")
'''

ABLATIONS: dict[str, dict[str, Any]] = {
    # Read through ctx.params: works.
    "ablation_ctx_params": {"PRELUDE": "", "TEST": 'if not ctx.params["signal_on"]:\n        return []', "broken": False},
    # A helper's default captures PARAMS (engine-3 ran the default here; engine-4 binds overrides at the declaration).
    "ablation_default_capture": {"PRELUDE": 'P = PARAMS\ndef enabled(flag=P["signal_on"]):\n    return flag',
                                 "TEST": 'if not enabled():\n        return []', "broken": False},
    # A module-level alias of the switch: bound at the declaration too.
    "ablation_module_alias": {"PRELUDE": 'SWITCH = PARAMS["signal_on"]', "TEST": 'if not SWITCH:\n        return []',
                              "broken": False},
    # A shadow copy: PARAMS is never read, so the static contract refuses the changed override.
    "ablation_shadow_config": {"PRELUDE": 'CONFIG = {"signal_on": 1}', "TEST": 'if not CONFIG["signal_on"]:\n        return []',
                               "broken": True},
    # Read, then defeated by a wrong comparison (0 >= 0): statically read, behaviorally ignored.
    "ablation_read_ignored": {"PRELUDE": "", "TEST": 'if not ctx.params["signal_on"] >= 0:\n        return []', "broken": True},
    # A computed key makes the static answer unknown, and the test is wrong (0 is not None).
    "ablation_dynamic_key": {"PRELUDE": 'NAME = "signal" + "_on"', "TEST": 'if ctx.params[NAME] is None:\n        return []',
                             "broken": True},
}

#: The state proofs and probes (not promoted or scored; each is a contract check with a known right answer).
STATE_PROGRAMS: dict[str, str] = {
    # Module STATE: trades on the first five sessions of a run only. Two runs must trade identically.
    "state_fresh_runs": '''
import numpy as np
NEEDS = {"roots": ["SPY"], "dte": [1, 1], "band": 0.03, "cadence": 30, "history": 0, "start": 859, "end": 889}
PARAMS = {"sessions": 5}
STATE = {"seen": 0}
''' + ENTRY + '''
def decide(ctx):
    if ctx.minute != 859:
        return leave(ctx)
    STATE["seen"] += 1
    if STATE["seen"] > ctx.params["sessions"]:
        return []
    return enter(ctx, "C")
''',
    # Parameters: a list in ctx.params and PARAMS grows through a run; a fresh run must start from the default again.
    "state_params_copied": '''
import numpy as np
NEEDS = {"roots": ["SPY"], "dte": [1, 1], "band": 0.03, "cadence": 30, "history": 0, "start": 859, "end": 889}
PARAMS = {"lst": [0]}
''' + ENTRY + '''
def decide(ctx):
    if ctx.minute != 859:
        return leave(ctx)
    ctx.params["lst"].append(1)
    PARAMS["lst"].append(1)
    if len(ctx.params["lst"]) != 2 or len(PARAMS["lst"]) != 2:
        return []
    return enter(ctx, "C")
''',
    # A process-global numpy dict: marks that a run happened; a later run in the same process that finds the mark
    # stands aside. If runs were isolated, both would trade identically.
    "state_numpy_runs": '''
import numpy as np
NEEDS = {"roots": ["SPY"], "dte": [1, 1], "band": 0.03, "cadence": 30, "history": 0, "start": 859, "end": 889}
PARAMS = {"probe": 1}
MARK = np.typecodes
STATE = {"started": 0, "inherited": 0}
''' + ENTRY + '''
def decide(ctx):
    if ctx.minute != 859:
        return leave(ctx)
    if not STATE["started"]:
        STATE["started"] = 1
        STATE["inherited"] = 1 if MARK.get("ltcm-bench-run") else 0
        MARK["ltcm-bench-run"] = "1"
    if STATE["inherited"]:
        return []
    return enter(ctx, "C")
''',
    # A batch-mate writes the same process-global dict every morning; the reader trades only when it finds nothing.
    "state_numpy_mate_writer": '''
import numpy as np
NEEDS = {"roots": ["SPY"], "dte": [1, 1], "band": 0.03, "cadence": 30, "history": 0, "start": 575, "end": 575}
PARAMS = {"probe": 1}
MARK = np.typecodes
def decide(ctx):
    MARK["ltcm-bench-mate"] = "1"
    return []
''',
    "state_numpy_mate_reader": '''
import numpy as np
NEEDS = {"roots": ["SPY"], "dte": [1, 1], "band": 0.03, "cadence": 30, "history": 0, "start": 859, "end": 889}
PARAMS = {"probe": 1}
MARK = np.typecodes
''' + ENTRY + '''
def decide(ctx):
    if ctx.minute != 859:
        return leave(ctx)
    if MARK.get("ltcm-bench-mate"):
        return []
    return enter(ctx, "C")
''',
    # A shared ctx object: the underlying's view is built once a minute and handed to every batch-mate with the same
    # history, and its coverage dict is a plain dict. A writer earlier in the batch marks it; a reader stands aside.
    "state_ctx_mate_writer": '''
NEEDS = {"roots": ["SPY"], "dte": [1, 1], "band": 0.03, "cadence": 30, "history": 2, "start": 859, "end": 859}
PARAMS = {"probe": 1}
def decide(ctx):
    ctx.under.volume_coverage["ltcm-bench-mate"] = 1
    return []
''',
    "state_ctx_mate_reader": '''
import numpy as np
NEEDS = {"roots": ["SPY"], "dte": [1, 1], "band": 0.03, "cadence": 30, "history": 2, "start": 859, "end": 889}
PARAMS = {"probe": 1}
''' + ENTRY + '''
def decide(ctx):
    if ctx.minute != 859:
        return leave(ctx)
    if ctx.under.volume_coverage.get("ltcm-bench-mate"):
        return []
    return enter(ctx, "C")
''',
    # The reach probe: a program that binds one numpy object and does nothing else ($PATH, e.g. np.typecodes). The static
    # check refuses it, or a program can hold (and write) that object.
    "state_numpy_reach": '''
import numpy as np
NEEDS = {"roots": ["SPY"], "dte": [1, 1], "band": 0.03, "cadence": 30, "history": 0, "start": 859, "end": 859}
PARAMS = {"probe": 1}
REACHED = $PATH
def decide(ctx):
    return []
''',
}
#: numpy's mutable public dicts, each proved on its own, so a fix that refuses one leaves the other's proofs failing.
#: `typecodes` is the first probes' container; `sctypeDict` is the one numpy resolves dtype names with, so a write there
#: can change what a batch-mate computes, not only what it knows.
STATE_PROGRAMS.update({name + "_sctypedict": STATE_PROGRAMS[name].replace("MARK = np.typecodes", "MARK = np.sctypeDict")
                       for name in ("state_numpy_runs", "state_numpy_mate_writer", "state_numpy_mate_reader")})
#: Keys the probes may leave in numpy's process-global dicts; the suite removes them after every run it makes.
NUMPY_MARK_PREFIX = "ltcm-bench-"


def _window(name: str) -> tuple[int, int, int]:
    """(decision minute before the window, its last minute, the tell's index in today's prices) of a channel."""
    k = CHANNELS[name]["k"]
    start = WORLD["window_minutes"][k]
    return start - 1, start + WORLD["window_length"] - 1, WORLD["tell_minutes"][k] - 570


def _signal(name: str, *, min_tell: float = 0.0, gap: float = 0.0) -> dict[str, Any]:
    start, end, tell = _window(name)
    return {"template": "SIGNAL", "subs": {"START": start, "END": end, "TELL": tell, "MIN_TELL": min_tell, "GAP": gap}}


def _leak(name: str) -> dict[str, Any]:
    start, end, tell = _window("absent")
    begin = start + 1 - 570
    return {"template": "LEAK", "parts": name, "subs": {"START": start, "END": end, "TELL": tell, "BEGIN": begin,
                                                        "STOP": begin + WORLD["window_length"], "MARKS": MARK_INDEXES}}


#: THE CASES. kind: "negative" (must not be promoted), "positive" (a planted edge: promotion is the right answer),
#: "smoke" (run and recorded like a negative, kept out of the rates: it cannot profit whatever the engine does),
#: "proof" (a contract check with a known answer), "ablation" (a switch's wiring). `review_dependent`: the mechanical
#: stages cannot stop it by design; only the review (or a proposed probe) can. `finding`: the grounded rejection a
#: correct review would file (code excerpt, contract reference), checked against `review_contract.grounded_answer`.
CASES: list[dict[str, Any]] = [
    {"id": "absent_signal", "family": "signal", "kind": "negative", **_signal("absent")},
    {"id": "cost_erased", "family": "signal", "kind": "negative", **_signal("cost")},
    {"id": "drift_only", "family": "signal", "kind": "negative", "template": "DRIFT_ONLY", "subs": {}},
    {"id": "edge_disappears", "family": "signal", "kind": "negative", **_signal("fading")},
    {"id": "planted_dense", "family": "signal", "kind": "positive", **_signal("dense")},
    {"id": "planted_sparse", "family": "signal", "kind": "positive",
     **_signal("sparse", min_tell=0.5 * (WORLD["tell_size"] + WORLD["big_tell_size"]))},
    {"id": "planted_medium", "family": "signal", "kind": "positive",
     **_signal("medium", min_tell=0.5 * (WORLD["tell_size"] + WORLD["big_tell_size"]))},
    {"id": "planted_regime_gap", "family": "signal", "kind": "positive", **_signal("gap", gap=CHANNELS["gap"]["gap"])},
    {"id": "planted_regime_years", "family": "signal", "kind": "positive", **_signal("years")},
    {"id": "leak_future_index", "family": "leakage", "kind": "negative", **_leak("leak_future_index")},
    {"id": "leak_array_base", "family": "leakage", "kind": "negative", **_leak("leak_array_base")},
    {"id": "leak_private_attr", "family": "leakage", "kind": "negative", **_leak("leak_private_attr")},
    {"id": "leak_date_literal", "family": "leakage", "kind": "negative", **_leak("leak_date_literal")},
    {"id": "leak_greeks_block", "family": "leakage", "kind": "negative", **_leak("leak_greeks_block")},
    {"id": "leak_events_next", "family": "leakage", "kind": "smoke", **_leak("leak_events_next")},
    {"id": "leak_daily_bars", "family": "leakage", "kind": "negative", **_leak("leak_daily_bars")},
    {"id": "leak_volume_bars", "family": "leakage", "kind": "negative", **_leak("leak_volume_bars")},
    {"id": "leak_numpy_memo", "family": "leakage", "kind": "negative", **_leak("leak_numpy_memo"),
     "finding": {"code_excerpt": "MEMO = np.typecodes", "contract_reference": "state"}},
    {"id": "leak_memorized_levels", "family": "leakage", "kind": "negative", **_leak("leak_memorized_levels"),
     "review_dependent": True,
     "finding": {"code_excerpt": "KNOWN.get(round(float(ctx.under.open), 2), 0.0)", "contract_reference": "calendar"}},
    {"id": "leak_memorized_sparse", "family": "leakage", "kind": "negative", **_leak("leak_memorized_sparse"),
     "review_dependent": True,
     "finding": {"code_excerpt": "KNOWN.get(round(float(ctx.under.open), 2), 0.0)", "contract_reference": "calendar"}},
    {"id": "leak_memorized_sessions", "family": "leakage", "kind": "negative", **_leak("leak_memorized_sessions"),
     "review_dependent": True,
     "finding": {"code_excerpt": 'KNOWN.get(STATE.get("run"), ())', "contract_reference": "calendar"}},
    {"id": "fill_stale_quote", "family": "fill", "kind": "negative", "template": "FILL", "parts": "fill_stale_quote", "subs": {}},
    {"id": "fill_close_above_width", "family": "fill", "kind": "negative", "template": "FILL",
     "parts": "fill_close_above_width", "subs": {}},
    {"id": "fill_open_below_zero", "family": "fill", "kind": "negative", "template": "FILL", "parts": "fill_open_below_zero",
     "subs": {}},
    {"id": "fill_crossed_quotes", "family": "fill", "kind": "negative", "template": "FILL", "parts": "fill_crossed_quotes",
     "subs": {"OFFSET": WORLD["crossed_offset"]}},
    {"id": "fill_passive_spread", "family": "fill", "kind": "negative", "template": "FILL", "parts": "fill_passive_spread",
     "subs": {}},
    {"id": "state_fresh_runs", "family": "state", "kind": "proof", "template": "STATE", "parts": "state_fresh_runs", "subs": {},
     "fact": "state"},
    {"id": "state_params_copied", "family": "state", "kind": "proof", "template": "STATE", "parts": "state_params_copied",
     "subs": {}, "fact": "parameters"},
    {"id": "state_numpy_runs", "family": "state", "kind": "proof", "template": "STATE", "parts": "state_numpy_runs", "subs": {},
     "fact": "state"},
    {"id": "state_numpy_batchmates", "family": "state", "kind": "proof", "template": "STATE", "parts": "state_numpy_mate_reader",
     "subs": {}, "fact": "state"},
    {"id": "state_numpy_runs_sctypedict", "family": "state", "kind": "proof", "template": "STATE",
     "parts": "state_numpy_runs_sctypedict", "subs": {}, "fact": "state"},
    {"id": "state_numpy_batchmates_sctypedict", "family": "state", "kind": "proof", "template": "STATE",
     "parts": "state_numpy_mate_reader_sctypedict", "subs": {}, "fact": "state"},
    {"id": "state_numpy_reachable", "family": "state", "kind": "proof", "template": "STATE", "parts": "state_numpy_reach",
     "subs": {"PATH": "np.typecodes"}, "fact": "state"},
    {"id": "state_ctx_batchmates", "family": "state", "kind": "proof", "template": "STATE", "parts": "state_ctx_mate_reader",
     "subs": {}, "fact": "context"},
    {"id": "state_split_segments", "family": "state", "kind": "proof", **_signal("dense"), "fact": "state"},
    *[{"id": name, "family": "ablation", "kind": "ablation", "template": "ABLATION", "parts": name, "broken": spec["broken"],
       "subs": dict(zip(("START", "END", "TELL"), _window("dense")))} for name, spec in ABLATIONS.items()],
]

TEMPLATES = {"SIGNAL": SIGNAL, "DRIFT_ONLY": DRIFT_ONLY, "LEAK": LEAK, "ABLATION": ABLATION}

#: The suite's fixed settings: the synthetic holdout's prior look history (two failed looks, as the swarm has had),
#: the evaluator's first Train year, the level-invariance probe's scale, and the default replication count.
PROTOCOL: dict[str, Any] = {
    "id": SUITE_ID,
    "replications": 8,
    "prior_holdout_ps": [0.5, 0.5],
    "train_first_year": 2022,
    "lineage_trials": 4,
    "level_scale": 1.25,
    "stress": 1.5,
    "confidence": 0.95,
}


def render(case: Mapping[str, Any], world: Mapping[str, Any] | None = None) -> str:
    """The case's program source (the memorized-levels table comes from the replication's truth)."""
    from string import Template

    template = case["template"]
    if template == "FILL":
        code = FILLS[case["parts"]]
    elif template == "STATE":
        code = STATE_PROGRAMS[case["parts"]]
    elif template == "LEAK":
        parts = dict(LEAKS[case["parts"]])
        code = LEAK.replace("$PRELUDE", parts["PRELUDE"]).replace("$AFTER", parts["AFTER"]).replace("$GUESS", parts["GUESS"])
    elif template == "ABLATION":
        parts = ABLATIONS[case["parts"]]
        code = ABLATION.replace("$PRELUDE", parts["PRELUDE"]).replace("$TEST", parts["TEST"])
    else:
        code = TEMPLATES[template]
    subs = {k: str(v) for k, v in case.get("subs", {}).items()}
    tables: dict[str, Callable[[Mapping[str, Any]], str]] = {
        "TABLE": _memorized_table, "SPARSE_TABLE": lambda w: _memorized_table(w, sparse=True),
        "SESSIONS": _session_table, "DATED": lambda w: _dated_tables(w)[0], "MOVES": lambda w: _dated_tables(w)[1]}
    for key, build in tables.items():
        if "$" + key in code:
            subs[key] = build(world) if world is not None else "{}"
    return Template(code).substitute(subs).lstrip("\n")


def _memorized_table(world: Mapping[str, Any], *, sparse: bool = False) -> str:
    """The absent window's realized direction for every session (`sparse`: only where the window moved more than
    `sparse_move` dollars), keyed by the session's opening price level."""
    rows = {}
    for row, move, level in zip(world["days"], world.get("moves") or [], world.get("opens") or []):
        if row["window"] != "history" and move and (not sparse or abs(move["absent"]) > WORLD["sparse_move"]):
            rows[round(float(level), 2)] = 1.0 if move["absent"] > 0 else -1.0
    return "{" + ", ".join(f"{k!r}: {v!r}" for k, v in sorted(rows.items())) + "}"


def _window_rows(world: Mapping[str, Any], window: str) -> list[tuple[str, Mapping[str, float], dt.date]]:
    """(mark, window moves, day) of each of a window's sessions, in order."""
    return [(mark, move, row["day"]) for row, move, mark in zip(world["days"], world.get("moves") or [], world.get("marks") or [])
            if row["window"] == window and move]


def _session_table(world: Mapping[str, Any]) -> str:
    """Each window's first-session mark, mapped to the absent window's direction in every session of it, in order."""
    out = {}
    for window in ("train", "validation", "holdout"):
        rows = _window_rows(world, window)
        if rows:
            out[rows[0][0]] = [1.0 if move["absent"] > 0 else -1.0 for _, move, _ in rows]
    return repr(out)


def _dated_tables(world: Mapping[str, Any]) -> tuple[str, str]:
    """(each window's first-session mark mapped to its sessions' ISO dates, each ISO date mapped to the direction)."""
    dates: dict[str, list[str]] = {}
    moves: dict[str, float] = {}
    for window in ("train", "validation", "holdout"):
        rows = _window_rows(world, window)
        if rows:
            dates[rows[0][0]] = [day.isoformat() for _, _, day in rows]
            moves.update({day.isoformat(): 1.0 if move["absent"] > 0 else -1.0 for _, move, day in rows})
    return repr(dates), repr(moves)


def suite_definition() -> dict[str, Any]:
    """Everything that defines the question: the protocol, the world, the channels, every case and every template."""
    return {"protocol": PROTOCOL, "world": WORLD, "channels": CHANNELS, "cases": CASES, "templates": TEMPLATES,
            "leaks": LEAKS, "fills": FILLS, "ablations": ABLATIONS, "state_programs": STATE_PROGRAMS}


def suite_sha() -> str:
    return digest(suite_definition())


# ------------------------------------------------------------------------------------------------ running the evaluator
def fill_model() -> Any:
    """A uniform passive-fill hazard on the world's root: patient orders can fill (so the adverse-selection and stress
    rules are exercised); marketable orders fill at the natural whatever the model says."""
    from league.gym import synth

    return synth.uniform_model(WORLD["fill_hazard"], roots=(WORLD["root"],))


def clear_numpy_marks() -> int:
    """Remove every key a probe may have left in numpy's process-global dicts (the suite's own process only)."""
    import numpy as np

    removed = 0
    for table in (np.typecodes, np.sctypeDict):
        for key in [k for k in list(table) if isinstance(k, str) and k.startswith(NUMPY_MARK_PREFIX)]:
            del table[key]
            removed += 1
    return removed


def run(programs: Sequence[Any], store: Any, window: str, *, stress: float = 1.0) -> list[dict[str, Any]]:
    from league.gym import engine as E

    if not programs:
        return []
    cfg = E.RunConfig(window=window, roots=(WORLD["root"],), stress=float(stress), fill_model=fill_model())
    return E.run(list(programs), store, cfg)


def trade_rows(result: Mapping[str, Any]) -> list[list[Any]]:
    """A run's trades as comparable rows (day, type, strike of the first leg, entry, exit, P&L)."""
    return [[t.get("day"), t.get("type"), (t.get("legs") or [{}])[0].get("strike"), t.get("entry"), t.get("exit"), t.get("pnl")]
            for t in result.get("trades") or []]


def hit_rate(result: Mapping[str, Any], world: Mapping[str, Any], channel: str = "absent") -> dict[str, Any]:
    """How often a probe's direction matched the window's realized move: about half when it learned nothing."""
    moves = {row["day"].isoformat(): move.get(channel) for row, move in zip(world["days"], world["moves"]) if move}
    hits = total = 0
    for t in result.get("trades") or []:
        move = moves.get(t.get("day"))
        if move is None or t.get("type") not in ("long_call", "long_put"):
            continue
        total += 1
        hits += (move > 0) == (t["type"] == "long_call")
    return {"trades": total, "hits": hits, "rate": round(hits / total, 4) if total else None}


def figures(train: Mapping[str, Any], train_stress: Mapping[str, Any], validation: Mapping[str, Any],
            validation_stress: Mapping[str, Any], holdout: Mapping[str, Any], seed: str) -> dict[str, Any]:
    """The evaluator's stages on one program's runs, exactly as the swarm computes them, and the raw figures a threshold
    variant needs to judge the same outcomes again."""
    from league.gym import results as R
    from league.swarm import evidence

    first = PROTOCOL["train_first_year"]
    score = evidence.train_score(train, first_year=first)
    drift = evidence.drift_screen(evidence.drift_numbers(train.get("drift")), first_year=first)
    view = R.view(validation, "validation")
    view["stress_1.5"] = R.stress_block(validation_stress)
    sharpe = evidence.traded_sharpe(view.get("summary") or {})
    line = evidence.validation_line(view, evidence.stressed_of(view), validated_versions=1,
                                    version_sharpes=[] if sharpe is None else [sharpe],
                                    lineage_trials=PROTOCOL["lineage_trials"])
    look = evidence.holdout_line(R.view(holdout, "holdout"), validation_sharpe=(view.get("summary") or {}).get("sharpe_daily"),
                                 previous_ps=PROTOCOL["prior_holdout_ps"], seed=seed)
    pooled = pooled_validation(train, train_stress, validation, validation_stress)
    summary = train.get("summary") or {}
    stress_pnl = (train_stress.get("summary") or {}).get("pnl")
    stages = {
        "static": True,
        "train_eligible": bool(score["eligible"]),
        "train_stress": train_stress.get("status") == "ok" and isinstance(stress_pnl, (int, float)) and stress_pnl > 0,
        "drift": bool(drift["passed"]),
        "validation": bool(line["passed"]),
        "review": True,  # the blind reviewer: the suite measures what the mechanical stages stop
        "holdout": bool(look["passed"]),
    }
    return {
        "stages": stages,
        "promoted": all(stages.values()),
        "stopped_at": next((k for k, ok in stages.items() if not ok), None),
        "train": {"status": train.get("status"), "score": score["score"], "eligible": score["eligible"], "why": score["why"],
                  "quarters": score["quarters"], "years": score["years"], "trades": summary.get("trades"),
                  "days_traded": summary.get("days_traded"), "t_daily": summary.get("t_daily"), "pnl": summary.get("pnl"),
                  "stress_pnl": stress_pnl},
        "drift": {k: drift.get(k) for k in ("known", "passed", "t", "positive", "years", "need")},
        "validation": {"checks": line["checks"], "numbers": line["numbers"]},
        "validation_pooled": pooled,
        "holdout": {"checks": look["checks"], "p": look["p"], "pnl": look["numbers"]["pnl"], "days": look["numbers"]["days"]},
    }


def pooled_validation(train: Mapping[str, Any], train_stress: Mapping[str, Any], validation: Mapping[str, Any],
                      validation_stress: Mapping[str, Any]) -> dict[str, Any]:
    """The validation line over the last Train year and Validation pooled (a VARIANT's figures, never a stage): what
    "pooled multi-year validation" means under today's partitions, where every earlier year is selection data."""
    from league.gym import results as R
    from league.swarm import evidence

    year = str(WORLD["years"]["train"][-1])

    def pooled(a: Mapping[str, Any], b: Mapping[str, Any]) -> dict[str, Any]:
        trades = [t for t in a.get("trades") or [] if str(t.get("day", ""))[:4] == year] + list(b.get("trades") or [])
        daily = [d for d in a.get("daily") or [] if str(d[0])[:4] == year] + list(b.get("daily") or [])
        return {"status": "ok" if a.get("status") == b.get("status") == "ok" else "error",
                "summary": R.summarize(trades, daily, 10_000.0)}

    normal, stressed = pooled(train, validation), pooled(train_stress, validation_stress)
    sharpe_pooled = evidence.traded_sharpe(normal["summary"])
    line = evidence.validation_line(normal, stressed, validated_versions=1,
                                    version_sharpes=[] if sharpe_pooled is None else [sharpe_pooled],
                                    lineage_trials=PROTOCOL["lineage_trials"])
    return {"checks": line["checks"], "numbers": line["numbers"]}


def grounded(case: Mapping[str, Any], code: str) -> dict[str, Any] | None:
    """Can the review contract carry the right rejection? A correct grounded finding must stay a failure; the same claim
    without a real excerpt must fall to unclear (it can never open a holdout, and never passes)."""
    finding = case.get("finding")
    if not finding:
        return None
    from league.gym.review_contract import grounded_answer

    counter = (f"the program reads {finding['code_excerpt']!r}; on the benchmark's world that value selects the trade "
               f"from information the {finding['contract_reference']} contract says it cannot have")
    good = grounded_answer({"json": {"verdict": "fail", "reasons": ["grounded"], "findings": [
        {**finding, "counterexample": counter}]}}, code)
    bare = grounded_answer({"json": {"verdict": "fail", "reasons": ["ungrounded"], "findings": [
        {"code_excerpt": "not in the program", "contract_reference": finding["contract_reference"], "counterexample": counter}]}}, code)
    return {"grounded_rejection_kept": good["verdict"] == "fail", "ungrounded_rejection_downgraded": bare["verdict"] == "unclear"}


PIPELINE_KINDS = ("negative", "positive", "smoke")


def replicate(replication: int, scratch: Path, cohort: str = "development") -> dict[str, Any]:
    """One replication: a fresh world, every pipeline case through every stage, and the probes."""
    from league.gym.experiment import check_experiment
    from league.gym.runtime import load_program
    from league.gym.safety import CodeRefused
    from league.gym.store import Store, mint_gate_capability

    began = time.monotonic()
    world = truth(replication, cohort)
    root = scratch / f"world-{replication}"
    world = {**world, **write_world(root, world)}
    scaled_root = scratch / f"world-{replication}-scaled"
    write_world(scaled_root, world, level_scale=PROTOCOL["level_scale"], windows=("validation",))
    store = Store(root)
    gate = Store(root, gate=mint_gate_capability(root, "evaluator benchmark: the suite's synthetic holdout"))
    scaled = Store(scaled_root)
    out: dict[str, Any] = {"replication": replication, "cases": {}}
    pipeline = [c for c in CASES if c["kind"] in PIPELINE_KINDS]
    loaded, codes = [], {}
    for case in pipeline:
        code = codes[case["id"]] = render(case, world)
        try:
            check_experiment(code, case.get("params") or {})
            loaded.append((case, load_program(code, name=case["id"], params=case.get("params") or {})))
        except CodeRefused as exc:
            stages = {"static": False}
            out["cases"][case["id"]] = {"stages": stages, "promoted": False, "stopped_at": "static", "refused": str(exc)[:200]}
    programs = [p for _, p in loaded]
    clear_numpy_marks()
    try:
        train = run(programs, store, "train")
        train_stress = run(programs, store, "train", stress=PROTOCOL["stress"])
        validation = run(programs, store, "validation")
        validation_stress = run(programs, store, "validation", stress=PROTOCOL["stress"])
        holdout = run(programs, gate, "holdout")
        level = run(programs, scaled, "validation")
    finally:
        clear_numpy_marks()
    for i, (case, _) in enumerate(loaded):
        row = figures(train[i], train_stress[i], validation[i], validation_stress[i], holdout[i],
                      seed=_seed(cohort, case["id"], replication, "holdout"))
        normal_t = (validation[i].get("summary") or {}).get("t_daily")
        scaled_t = (level[i].get("summary") or {}).get("t_daily")
        row["probes"] = {
            "stress_contaminated": _contaminated(validation[i], validation_stress[i]),
            "level_invariance": {"t_daily": normal_t, "t_daily_scaled": scaled_t, "flagged": _level_flag(normal_t, scaled_t)},
        }
        if case["family"] == "leakage":
            row["probes"]["hit_rate_train"] = hit_rate(train[i], world)
        if case["family"] == "fill":
            row["probes"]["impossible_fills"] = sum(impossible_fills(case["id"], r) for r in
                                                    (train[i], train_stress[i], validation[i], validation_stress[i], holdout[i]))
        review = grounded(case, codes[case["id"]])
        if review is not None:
            row["review_contract"] = review
        out["cases"][case["id"]] = row
    out["proofs"] = proofs(store, root)
    out["ablations"] = ablations(store)
    out["seconds"] = round(time.monotonic() - began, 2)
    shutil.rmtree(root, ignore_errors=True)
    shutil.rmtree(scaled_root, ignore_errors=True)
    return out


def impossible_fills(case_id: str, result: Mapping[str, Any]) -> int:
    """Fills the world makes impossible, counted from a run's trades: a 1-wide debit vertical entered at or below zero or
    above its width, or exited outside [0, 1]; a crossed quote filled; the stale jump-minute quote filled."""
    bad = 0
    crossed = range(WORLD["crossed_minutes"][0], WORLD["crossed_minutes"][1] + 1)
    for t in result.get("trades") or []:
        if case_id in ("fill_close_above_width", "fill_open_below_zero"):
            entry, exit_ = t.get("entry"), t.get("exit")
            bad += not (isinstance(entry, (int, float)) and 0.0 < entry <= 1.0)
            bad += isinstance(exit_, (int, float)) and not -1e-9 <= exit_ <= 1.0 + 1e-9
        elif case_id == "fill_crossed_quotes":
            bad += t.get("filled_minute") in crossed or t.get("exit_minute") in crossed
        elif case_id == "fill_stale_quote":
            bad += t.get("filled_minute") == WORLD["jump_minute"]
    return int(bad)


def _contaminated(normal: Mapping[str, Any], stressed: Mapping[str, Any]) -> bool:
    """A stress run can only cost a program: wider spreads, fewer patient fills. One that does better at 1.5x than at 1x
    over the same days, by more than rounding, learned something between the runs."""
    a = (normal.get("summary") or {}).get("pnl")
    b = (stressed.get("summary") or {}).get("pnl")
    if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
        return False
    return b > a + 1.0


def _level_flag(normal_t: Any, scaled_t: Any) -> bool:
    """The level-invariance probe (a proposal, not a stage): an edge that holds at the world's price level and vanishes
    when every price is scaled was keyed to the level. Flags a validation t of at least 2 that falls by more than 1.5; a
    scaled run with no t at all (it stopped trading) counts as 0."""
    if not isinstance(normal_t, (int, float)):
        return False
    scaled = float(scaled_t) if isinstance(scaled_t, (int, float)) else 0.0
    return normal_t >= 2.0 and scaled < normal_t - 1.5


def proofs(store: Any, root: Path) -> dict[str, Any]:
    """The state contract's executable proofs. Each says what it checks, what it found, and whether it held. A probe the
    static check refuses has no channel to use: that holds, and says so."""
    from league.gym.runtime import load_program
    from league.gym.safety import CodeRefused

    out: dict[str, Any] = {}

    def program(name: str, code: str) -> Any:
        try:
            return load_program(code, name=name)
        except CodeRefused as exc:
            out[name] = {"held": True, "refused": str(exc)[:200], "claim": "the static check refuses the probe"}
            return None

    def twice(name: str, claim: str, expect: int | None) -> None:
        loaded = program(name, render(next(c for c in CASES if c["id"] == name)))
        if loaded is None:
            return
        clear_numpy_marks()
        try:
            [first] = run([loaded], store, "validation")
            [second] = run([loaded], store, "validation")
        finally:
            clear_numpy_marks()
        same = trade_rows(first) == trade_rows(second)
        out[name] = {"held": same and (expect is None or len(first["trades"]) == expect),
                     "trades": [len(first["trades"]), len(second["trades"])], "claim": claim}

    def batchmates(name: str, writer_name: str, claim: str) -> None:
        reader = program(name, render(next(c for c in CASES if c["id"] == name)))
        writer = program(writer_name, STATE_PROGRAMS[writer_name].lstrip("\n"))
        # The writer is half of the batch-mate proof, never a proof of its own: its refusal record never stays in `out`.
        writer_refused = out.pop(writer_name, None)
        if reader is not None and writer is not None:
            clear_numpy_marks()
            try:
                [alone] = run([reader], store, "validation")
                clear_numpy_marks()
                [_, mated] = run([writer, reader], store, "validation")
            finally:
                clear_numpy_marks()
            out[name] = {"held": trade_rows(alone) == trade_rows(mated), "trades": [len(alone["trades"]), len(mated["trades"])],
                         "claim": claim}
        elif reader is not None:  # the reader loads, the writer is refused: the channel has no writer
            out[name] = {"held": True, "refused": (writer_refused or {}).get("refused"), "claim": "the static check refuses the writer"}
        # else: the reader was refused, and `program` recorded the proof as held by refusal

    twice("state_fresh_runs", "module STATE starts fresh in every run (five trades each time)", 5)
    twice("state_params_copied", "a run's parameter lists are its own; the next run starts from the defaults", 1)
    twice("state_numpy_runs", "no process-global object (np.typecodes) carries one run's decisions into the next run", None)
    twice("state_numpy_runs_sctypedict", "no process-global object (np.sctypeDict) carries one run's decisions into the next "
          "run", None)
    batchmates("state_numpy_batchmates", "state_numpy_mate_writer",
               "a program's result does not depend on the batch-mates it shares a process with (np.typecodes)")
    batchmates("state_numpy_batchmates_sctypedict", "state_numpy_mate_writer_sctypedict",
               "a program's result does not depend on the batch-mates it shares a process with (np.sctypeDict)")
    out["state_numpy_reachable"] = numpy_reach()
    out["state_ctx_batchmates"] = mates(store, "state_ctx_mate_writer", "state_ctx_mate_reader",
                                        "a batch-mate cannot write into the ctx objects another program is handed")
    out["state_split_segments"] = split_proof(root)
    return out


def numpy_containers() -> list[str]:
    """numpy's public mutable builtin containers (dict, list, set, bytearray), at the top level and one public numpy
    submodule down, as `np.` paths. Read from the module dicts, so enumerating imports nothing: it is what this
    process's numpy holds (numpy 2.5: `np.sctypeDict` and `np.typecodes`)."""
    import types

    import numpy as np

    mutable = (dict, list, set, bytearray)
    found = []
    for name, value in sorted(vars(np).items()):
        if name.startswith("_"):
            continue
        if isinstance(value, mutable):
            found.append(f"np.{name}")
        elif isinstance(value, types.ModuleType) and value.__name__.startswith("numpy."):
            found += [f"np.{name}.{inner}" for inner, item in sorted(vars(value).items())
                      if not inner.startswith("_") and isinstance(item, mutable)]
    return found


def numpy_reach() -> dict[str, Any]:
    """Every mutable public numpy container: does the static check refuse a program that reaches it? Held only when it
    refuses them all. A container a program can hold is a channel between runs and batch-mates in one process, so a
    fix that closes some containers and not others does not hold here."""
    from string import Template

    from league.gym.runtime import load_program
    from league.gym.safety import CodeRefused

    reachable, refused = [], []
    for path in numpy_containers():
        code = Template(STATE_PROGRAMS["state_numpy_reach"]).substitute(PATH=path).lstrip("\n")
        try:
            load_program(code, name="numpy-reach")
            reachable.append(path)
        except CodeRefused:
            refused.append(path)
    return {"held": not reachable, "reachable": reachable, "refused_containers": refused,
            "claim": "the static check refuses every mutable public numpy container (a program cannot hold one)"}


def mates(store: Any, writer_name: str, reader_name: str, claim: str) -> dict[str, Any]:
    """A reader alone, then after a writer in the same batch: its trades must not change."""
    from league.gym.runtime import load_program
    from league.gym.safety import CodeRefused

    try:
        writer = load_program(STATE_PROGRAMS[writer_name].lstrip("\n"), name=writer_name)
        reader = load_program(STATE_PROGRAMS[reader_name].lstrip("\n"), name=reader_name)
    except CodeRefused as exc:
        return {"held": True, "refused": str(exc)[:200], "claim": "the static check refuses the probe"}
    [alone] = run([reader], store, "validation")
    [_, mated] = run([writer, reader], store, "validation")
    return {"held": trade_rows(alone) == trade_rows(mated), "trades": [len(alone["trades"]), len(mated["trades"])],
            "claim": claim}


def split_proof(root: Path) -> dict[str, Any]:
    """A split Train run differs from the unsplit one only by what is open at a boundary (the batch's accounting split);
    an intraday program has nothing open there, so its daily P&L must match day for day. Validation is never split."""
    from league.gym import batch

    code = render(next(c for c in CASES if c["id"] == "state_split_segments"))
    with tempfile.TemporaryDirectory(prefix="evaluator-suite-fill-", dir=str(root.parent)) as temp:
        path = Path(temp) / "fill_model.json"
        model = fill_model()
        path.write_text(json.dumps({"hazard": model.hazard, "size": model.size, "source": model.source}))
        common = {"store_root": str(root), "roots": (WORLD["root"],), "workers": 1, "fill_model_path": str(path)}
        whole = batch.run_batch([("split", code, {})], window="train", split=1, **common)
        parts = batch.run_batch([("split", code, {})], window="train", split=3, **common)
        validation = batch.run_batch([("split", code, {})], window="validation", split=3, **common)
    a = {row[0]: round(float(row[1]), 6) for row in whole["results"][0]["daily"]}
    b = {row[0]: round(float(row[1]), 6) for row in parts["results"][0]["daily"]}
    return {"held": a == b and parts["batch"]["split"] == 3 and validation["batch"]["split"] == 1,
            "train_days": [len(a), len(b)], "days_differing": sum(1 for d in a if a.get(d) != b.get(d)),
            "validation_split": validation["batch"]["split"],
            "claim": "a split Train run matches the unsplit run day for day for an intraday program; Validation is never split"}


def ablations(store: Any) -> dict[str, Any]:
    """Each wiring of the switch: does the static contract refuse the off override, and does a behavioral ablation (the
    off variant over Validation) show the switch removes the trades?"""
    from league.gym.experiment import check_experiment
    from league.gym.runtime import load_program
    from league.gym.safety import CodeRefused

    out: dict[str, Any] = {}
    on, off, names = [], [], []
    for case in (c for c in CASES if c["kind"] == "ablation"):
        code = render(case)
        try:
            check_experiment(code, {"signal_on": 0})
            static = None
        except CodeRefused as exc:
            static = str(exc)[:200]
        names.append((case, static))
        on.append(load_program(code, name=case["id"] + ":on"))
        off.append(load_program(code, name=case["id"] + ":off", params={"signal_on": 0}))
    results = run(on + off, store, "validation")
    for i, (case, static) in enumerate(names):
        trades_on, trades_off = len(results[i]["trades"]), len(results[len(names) + i]["trades"])
        effective = trades_on > 0 and trades_off == 0
        out[case["id"]] = {"broken": case["broken"], "static_refused": static is not None, "static_reason": static,
                           "behavioral_effective": effective, "trades_on": trades_on, "trades_off": trades_off,
                           "static_detects": case["broken"] == (static is not None),
                           "behavioral_detects": case["broken"] == (not effective)}
    return out


# ------------------------------------------------------------------------------------------------ threshold variants
#: Eligibility and scoring variants, judged on the SAME recorded outcomes (never applied to the swarm). `aligned_floors`
#: asks Validation for the rate Train already asks for (40 trades on 20 days a year). Floors: a Train
#: year's trades and traded days (every Train year), pooled Train trades and days, Validation trades and days. The
#: objective ranks Train versions: the worst year's t (today) or the pooled Train t. `validation` "pooled" judges the
#: validation line over the last Train year and Validation together. Everything else (t >= 2, the deflated Sharpe on
#: the lineage's validated versions, three positive quarters, the 1.5x stress, the drift screen, the holdout line with
#: Holm, the look rations) is the current rule in every variant: those never loosen (the owner, Sept 30).
VARIANTS: dict[str, dict[str, Any]] = {
    "current": {"year_trades": 40, "year_days": 20, "pooled_trades": 0, "pooled_days": 0, "val_trades": 50, "val_days": 25,
                "objective": "worst_year", "validation": "single"},
    "aligned_floors": {"year_trades": 40, "year_days": 20, "pooled_trades": 0, "pooled_days": 0, "val_trades": 40,
                       "val_days": 20, "objective": "worst_year", "validation": "single"},
    "sparse_floors": {"year_trades": 6, "year_days": 5, "pooled_trades": 30, "pooled_days": 20, "val_trades": 10,
                      "val_days": 8, "objective": "worst_year", "validation": "single"},
    "pooled_train": {"year_trades": 1, "year_days": 1, "pooled_trades": 30, "pooled_days": 20, "val_trades": 10,
                     "val_days": 8, "objective": "pooled", "validation": "single"},
    "pooled_validation": {"year_trades": 40, "year_days": 20, "pooled_trades": 0, "pooled_days": 0, "val_trades": 50,
                          "val_days": 25, "objective": "worst_year", "validation": "pooled"},
    "no_floors": {"year_trades": 1, "year_days": 1, "pooled_trades": 2, "pooled_days": 2, "val_trades": 2, "val_days": 2,
                  "objective": "worst_year", "validation": "single"},
}


def train_eligible(train: Mapping[str, Any], rule: Mapping[str, Any]) -> tuple[bool, float | None]:
    """(eligible, score) of recorded Train figures under a variant: its floors, and its objective (the score ranks
    versions; the swarm does not require it to be positive)."""
    years = train.get("years") or {}
    if train.get("status") != "ok" or not years:
        return False, None
    ts = [r.get("t_daily") for r in years.values()]
    k, n = (int(x) for x in str(train.get("quarters") or "0/0").split("/"))
    share = k / n if n else 0.0
    if rule["objective"] == "pooled":
        t = train.get("t_daily")
        positive = sum(1 for r in years.values() if (r.get("pnl") or 0.0) > 0) / len(years)
        score = None if t is None else (t * positive if t >= 0 else t * (2.0 - positive))
    else:
        low = None if any(t is None for t in ts) else min(ts)
        score = None if low is None else (low * share if low >= 0 else low * (2.0 - share))
    floors = all(int(r.get("trades") or 0) >= rule["year_trades"] and int(r.get("days_traded") or 0) >= rule["year_days"]
                 for r in years.values())
    pooled = int(train.get("trades") or 0) >= rule["pooled_trades"] and int(train.get("days_traded") or 0) >= rule["pooled_days"]
    return bool(floors and pooled and score is not None), score


def validation_passes(line: Mapping[str, Any] | None, rule: Mapping[str, Any]) -> bool:
    """A recorded validation line re-judged with a variant's activity floors (every other check as computed)."""
    if not line:
        return False
    checks = dict(line["checks"])
    numbers = line["numbers"]
    checks["trades"] = int(numbers.get("trades") or 0) >= rule["val_trades"]
    checks["days"] = int(numbers.get("days") or 0) >= rule["val_days"]
    return all(checks.values())


def variant_reaches_holdout(row: Mapping[str, Any], rule: Mapping[str, Any]) -> bool:
    """Would this single-version case have passed every stage before the holdout under the variant (and spent a look)?"""
    stages = row.get("stages") or {}
    if not stages.get("static"):
        return False
    eligible, _ = train_eligible(row["train"], rule)
    line = row.get("validation_pooled") if rule["validation"] == "pooled" else row.get("validation")
    return bool(eligible and stages.get("train_stress") and stages.get("drift") and validation_passes(line, rule)
                and stages.get("review"))


def variant_verdict(row: Mapping[str, Any], rule: Mapping[str, Any]) -> bool:
    """Would the pipeline have promoted this single-version case under the variant?"""
    return variant_reaches_holdout(row, rule) and bool((row.get("stages") or {}).get("holdout"))


# ------------------------------------------------------------------------------------------------ the search tier
#: Selection under search, where lowered floors are most dangerous: the same statistical rules applied to generated
#: daily outcomes (no Gym, no drift figures), with a lineage that tries up to five Train candidates in rank order, its
#: validated-version count and Sharpe history feeding the deflated Sharpe, and a Holm history of every look. Noise
#: variants are net-zero after base costs (a demanding null), Gaussian and fat-tailed (Student-t, 3 degrees of
#: freedom) in every frequency band a floor variant opens: 12, 42 and 48 trades a year sit under today's floors (Train 40
#: a year, Validation 50), 126 above them. Positives carry a fixed net edge per trade.
SEARCH: dict[str, Any] = {
    "id": "search-1",
    "sessions": 252,
    "train_years": [2022, 2023, 2024],
    "validation_year": 2025,
    "holdout_year": 2026,
    "max_loss": 100.0,
    "trade_sd": 40.0,
    "spread": 3.0,
    "fees": 0.5,
    "candidates": 5,
    "looks_per_lineage": 3,
    "replications": 128,
    "cases": {
        "noise_sparse_search": {"trades_per_year": 12, "net_edge": 0.0, "variants": 32, "positive": False},
        "noise_medium_search": {"trades_per_year": 48, "net_edge": 0.0, "variants": 32, "positive": False},
        "noise_dense_search": {"trades_per_year": 126, "net_edge": 0.0, "variants": 32, "positive": False},
        "noise_sparse_fat_search": {"trades_per_year": 12, "net_edge": 0.0, "variants": 32, "positive": False, "tails": 3},
        "noise_low_search": {"trades_per_year": 42, "net_edge": 0.0, "variants": 32, "positive": False},
        "noise_low_fat_search": {"trades_per_year": 42, "net_edge": 0.0, "variants": 32, "positive": False, "tails": 3},
        "noise_medium_fat_search": {"trades_per_year": 48, "net_edge": 0.0, "variants": 32, "positive": False, "tails": 3},
        "signal_sparse": {"trades_per_year": 12, "net_edge": 40.0, "variants": 1, "positive": True},
        "signal_medium": {"trades_per_year": 48, "net_edge": 20.0, "variants": 1, "positive": True},
        "signal_dense": {"trades_per_year": 126, "net_edge": 14.0, "variants": 1, "positive": True},
    },
}


def search_outcomes(case: str, replication: int, variant: int, years: Sequence[int], stress: float = 1.0,
                    cohort: str = "development") -> dict[str, Any]:
    """Generated daily outcomes of one variant: its active days precede independent shocks; stress shares the gross stream
    and charges a wider spread."""
    from league.gym import results as R

    spec = SEARCH["cases"][case]
    mean = SEARCH["spread"] + SEARCH["fees"] + spec["net_edge"]
    trades, daily = [], []
    for year in years:
        rng = random.Random(_seed(cohort, SEARCH["id"], case, replication, variant, year))
        active = set(rng.sample(range(SEARCH["sessions"]), spec["trades_per_year"]))
        day = dt.date(year, 1, 1)
        for index in range(SEARCH["sessions"]):
            while day.weekday() >= 5:
                day += dt.timedelta(days=1)
            shock = rng.gauss(0.0, 1.0)
            if spec.get("tails"):  # Student-t with `tails` degrees of freedom, scaled to unit variance: fat tails
                df = float(spec["tails"])
                shock = shock / math.sqrt(rng.gammavariate(df / 2.0, 2.0) / df) * math.sqrt((df - 2.0) / df)
            gross = mean + SEARCH["trade_sd"] * shock
            pnl = 0.0
            if index in active:
                pnl = gross - SEARCH["spread"] * stress - SEARCH["fees"]
                trades.append({"day": day.isoformat(), "pnl": pnl, "max_loss": SEARCH["max_loss"], "qty": 1,
                               "return_on_max_loss": pnl / SEARCH["max_loss"], "fees": SEARCH["fees"]})
            daily.append([day.isoformat(), pnl])
            day += dt.timedelta(days=1)
    return {"status": "ok", "trades": trades, "daily": daily, "summary": R.summarize(trades, daily, 10_000.0),
            "by_year": R.by_year(trades, daily)}


def _train_figures(result: Mapping[str, Any]) -> dict[str, Any]:
    from league.swarm import evidence

    score = evidence.train_score(result)
    summary = result["summary"]
    return {"status": result["status"], "years": score["years"], "quarters": score["quarters"], "trades": summary["trades"],
            "days_traded": summary["days_traded"], "t_daily": summary["t_daily"], "pnl": summary["pnl"]}


def search_trial(case: str, replication: int, cohort: str = "development") -> dict[str, Any]:
    """One lineage's search under every variant, on shared outcomes (each variant ranks and validates on its own)."""
    from league.swarm import evidence

    spec = SEARCH["cases"][case]
    train_years, v_year, h_year = SEARCH["train_years"], SEARCH["validation_year"], SEARCH["holdout_year"]
    cache: dict[Any, Any] = {}

    def get(key: tuple, make: Callable[[], Any]) -> Any:
        if key not in cache:
            cache[key] = make()
        return cache[key]

    trains = [get(("train", v), lambda v=v: search_outcomes(case, replication, v, train_years, cohort=cohort))
              for v in range(spec["variants"])]
    figs = [_train_figures(t) for t in trains]
    out: dict[str, Any] = {}
    for name, rule in VARIANTS.items():
        ranked = []
        for v, fig in enumerate(figs):
            eligible, score = train_eligible(fig, rule)
            if eligible:
                ranked.append((-score, v))
        ranked = [v for _, v in sorted(ranked)[:SEARCH["candidates"]]]
        looks = list(PROTOCOL["prior_holdout_ps"])
        sharpes: list[float] = []
        lineage_looks = validations = 0
        promoted = False
        for v in ranked:
            stress = get(("train_stress", v), lambda v=v: search_outcomes(case, replication, v, train_years, 1.5, cohort))
            if not stress["summary"]["pnl"] > 0:
                continue
            years = [train_years[-1], v_year] if rule["validation"] == "pooled" else [v_year]
            normal = get(("validation", v, len(years)),
                         lambda v=v, y=tuple(years): search_outcomes(case, replication, v, y, cohort=cohort))
            stressed = get(("validation_stress", v, len(years)),
                           lambda v=v, y=tuple(years): search_outcomes(case, replication, v, y, 1.5, cohort))
            validations += 1
            sharpe = evidence.traded_sharpe(normal["summary"])
            if sharpe is not None:
                sharpes.append(sharpe)
            line = evidence.validation_line(normal, {"status": "ok", "summary": stressed["summary"]}, validated_versions=validations,
                                            version_sharpes=sharpes, lineage_trials=len(trains) + 2 * validations)
            if not validation_passes(line, rule):
                continue
            if lineage_looks >= SEARCH["looks_per_lineage"]:
                break
            unseen = get(("holdout", v), lambda v=v: search_outcomes(case, replication, v, [h_year], cohort=cohort))
            look = evidence.holdout_line(unseen, validation_sharpe=normal["summary"]["sharpe_daily"], previous_ps=looks,
                                         seed=_seed(cohort, SEARCH["id"], case, replication, v, "holdout"))
            looks.append(look["p"])
            lineage_looks += 1
            if look["passed"]:
                promoted = True
                break
        out[name] = {"promoted": promoted, "candidates": len(ranked), "validations": validations, "looks": lineage_looks}
    return out


# ------------------------------------------------------------------------------------------------ the report
LIMITATIONS = [
    "Invented worlds: an arithmetic random walk with planted, deliberately strong edges and options priced fair by "
    "construction. Rates bound the evaluator's errors on these cases only, not on real markets or real research.",
    "The review is not called: every rate is the mechanical pipeline's with a blind reviewer. Review-dependent cases show "
    "the load the review carries; the suite checks only that the review contract can carry a grounded rejection.",
    "Runs are made in one process, as a one-worker batch makes them. Production Gym boxes run each unit in its own "
    "process, which isolates runs (not batch-mates) from process-global state.",
    "The synthetic holdout is generated by the suite; the sealed market holdout is never read. Holm uses a fixed prior "
    "history of two failed looks, not the swarm's.",
    "The search tier has no drift figures, no serial dependence and a fixed five-candidate schedule; it is not a "
    "simulation of model research.",
    "Finite counts: an exact 95% upper bound, not a point estimate, is the claim a zero count supports. Run-level bounds "
    "treat each case-world as an independent trial; outcomes cluster by case (most go 0/8 or 8/8), so the case-level "
    "counts are the effective sample, and every bound is conditional on this fixed case mix.",
    "End-to-end false promotions cannot tell floor variants apart on noise: the holdout with Holm stops every noise "
    "lineage under any floors. The owner-rule verdict therefore also compares the holdout looks noise spends in every "
    "frequency band, and the sparse memorized table is a negative the floors are known to stop.",
    "--tree runs the candidate's code in the suite's interpreter with the operator's environment: it guards against "
    "accidental drift of the cases, not against a hostile tree.",
]


def exact_upper(k: int, n: int, alpha: float) -> float:
    """The exact (Clopper-Pearson) one-sided upper bound on a rate after `k` events in `n` trials at confidence 1 - alpha:
    the p at which P(X <= k) = alpha; 1.0 when n <= 0 or k >= n. Vendored (a binomial sum in logs, bisected) so the
    bounds come from the pinned suite, never from the scored tree; it agrees with `league.stats.exact_upper`."""
    if n <= 0 or k >= n:
        return 1.0
    k = max(int(k), 0)
    if k == 0:
        return -math.expm1(math.log(alpha) / n)  # (1 - p)^n = alpha, solved exactly
    coefficient = [math.lgamma(n + 1) - math.lgamma(i + 1) - math.lgamma(n - i + 1) for i in range(k + 1)]

    def cdf(p: float) -> float:
        lp, lq = math.log(p), math.log1p(-p)
        terms = [c + i * lp + (n - i) * lq for i, c in enumerate(coefficient)]
        top = max(terms)
        return math.exp(top) * sum(math.exp(t - top) for t in terms)

    low, high = 0.0, 1.0
    for _ in range(60):
        mid = (low + high) / 2.0
        if cdf(mid) > alpha:
            low = mid
        else:
            high = mid
    return high


def _rate(k: int, n: int) -> dict[str, Any]:
    alpha = (1.0 - PROTOCOL["confidence"]) / 2.0
    return {"count": k, "of": n, "rate": round(k / n, 4) if n else None,
            "lower_95": 0.0 if k <= 0 or not n else round(1.0 - exact_upper(n - k, n, alpha), 4),
            "upper_95": round(exact_upper(k, n, alpha), 4) if n else 1.0,
            "upper_95_one_sided": round(exact_upper(k, n, 1.0 - PROTOCOL["confidence"]), 4) if n else 1.0}


def aggregate(rows: Sequence[Mapping[str, Any]], search: Mapping[str, Sequence[Mapping[str, Any]]]) -> dict[str, Any]:
    """The report's figures from the replication rows and the search trials (pure: no engine, no store)."""
    kinds = {c["id"]: c for c in CASES}
    per_case: dict[str, Any] = {}
    for case in (c for c in CASES if c["kind"] in PIPELINE_KINDS):
        runs = [r["cases"][case["id"]] for r in rows]
        stops: dict[str, int] = {}
        for run in runs:
            key = run["stopped_at"] or "promoted"
            stops[key] = stops.get(key, 0) + 1
        entry = {"family": case["family"], "kind": case["kind"], "review_dependent": bool(case.get("review_dependent")),
                 "promoted": sum(bool(r["promoted"]) for r in runs), "of": len(runs), "stopped_at": stops}
        flags = [r.get("probes") or {} for r in runs]
        entry["stress_contaminated"] = sum(bool(f.get("stress_contaminated")) for f in flags)
        entry["level_flagged"] = sum(bool((f.get("level_invariance") or {}).get("flagged")) for f in flags)
        # Detection is counted run by run: a flag in a world where the case was not promoted detects nothing.
        entry["promoted_and_level_flagged"] = sum(bool(r["promoted"]) and bool((f.get("level_invariance") or {}).get("flagged"))
                                                  for r, f in zip(runs, flags))
        hits = [f["hit_rate_train"] for f in flags if f.get("hit_rate_train")]
        if hits:
            total = sum(h["trades"] for h in hits)
            entry["direction_hit_rate"] = round(sum(h["hits"] for h in hits) / total, 4) if total else None
        if case["family"] == "fill":
            entry["impossible_fills"] = sum(int(f.get("impossible_fills") or 0) for f in flags)
        reviews = [r["review_contract"] for r in runs if r.get("review_contract")]
        if reviews:
            entry["review_contract"] = {"grounded_rejection_kept": all(x["grounded_rejection_kept"] for x in reviews),
                                        "ungrounded_rejection_downgraded": all(x["ungrounded_rejection_downgraded"] for x in reviews)}
        refused = [r["refused"] for r in runs if r.get("refused")]
        if refused:
            entry["refused"], entry["refused_in"] = refused[0], len(refused)
        per_case[case["id"]] = entry
    negatives = [c for c in per_case.values() if c["kind"] == "negative"]
    positives = [c for c in per_case.values() if c["kind"] == "positive"]
    designed = [c for c in negatives if not c["review_dependent"]]
    rates = {
        "false_promotion": _rate(sum(c["promoted"] for c in negatives), sum(c["of"] for c in negatives)),
        "false_promotion_mechanical_scope": _rate(sum(c["promoted"] for c in designed), sum(c["of"] for c in designed)),
        "missed_signal": _rate(sum(c["of"] - c["promoted"] for c in positives), sum(c["of"] for c in positives)),
        # The effective sample: whole cases (outcomes cluster within a case), conditional on this case mix.
        "negative_cases_promoted": _rate(sum(c["promoted"] > 0 for c in negatives), len(negatives)),
        "negative_cases_promoted_mechanical_scope": _rate(sum(c["promoted"] > 0 for c in designed), len(designed)),
        "positive_cases_missed_in_any_world": _rate(sum(c["promoted"] < c["of"] for c in positives), len(positives)),
    }
    proofs_out: dict[str, Any] = {}
    for name in rows[0]["proofs"] if rows else []:
        held = sum(bool(r["proofs"][name]["held"]) for r in rows)
        first = rows[0]["proofs"][name]
        observed = next((first[key] for key in ("trades", "train_days", "reachable") if key in first), None)
        proofs_out[name] = {"held": held, "of": len(rows), "fact": (kinds.get(name) or {}).get("fact"), "claim": first["claim"],
                            "observed": observed, "refused": first.get("refused")}
        if "refused_containers" in first:
            proofs_out[name]["refused_containers"] = first["refused_containers"]
    ablation_out: dict[str, Any] = {}
    for name in rows[0]["ablations"] if rows else []:
        runs = [r["ablations"][name] for r in rows]
        ablation_out[name] = {"broken": runs[0]["broken"], "static_refused": sum(x["static_refused"] for x in runs),
                              "behavioral_effective": sum(x["behavioral_effective"] for x in runs), "of": len(runs),
                              "static_reason": runs[0]["static_reason"]}
    broken = [a for a in ablation_out.values() if a["broken"]]
    working = [a for a in ablation_out.values() if not a["broken"]]
    ablation_rates = {
        "static_detection": _rate(sum(a["static_refused"] for a in broken), sum(a["of"] for a in broken)),
        "behavioral_detection": _rate(sum(a["of"] - a["behavioral_effective"] for a in broken), sum(a["of"] for a in broken)),
        "static_false_alarm": _rate(sum(a["static_refused"] for a in working), sum(a["of"] for a in working)),
        "behavioral_false_alarm": _rate(sum(a["of"] - a["behavioral_effective"] for a in working), sum(a["of"] for a in working)),
    }
    level = {"detected": _rate(sum(c["promoted_and_level_flagged"] for c in negatives), sum(c["promoted"] for c in negatives)),
             "false_alarm_on_positives": _rate(sum(c["level_flagged"] for c in positives), sum(c["of"] for c in positives))}
    contradicted = sorted({p["fact"] for p in proofs_out.values() if p["held"] < p["of"] and p["fact"]})
    variants, sensitivity = judge_variants(rows, search)
    return {"rates": rates, "cases": per_case, "proofs": proofs_out, "facts_contradicted": contradicted,
            "ablations": ablation_out, "ablation_rates": ablation_rates, "level_invariance_probe": level, "variants": variants,
            "verdict_sensitivity": sensitivity}


def judge_variants(rows: Sequence[Mapping[str, Any]],
                   search: Mapping[str, Sequence[Mapping[str, Any]]]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Every variant on the same recorded outcomes, and the owner's rule (Sept 30) as a verdict with power: false
    promotions not higher (engine, search), holdout looks spent by negatives not higher (engine negatives; noise lineages
    in EVERY search band, Gaussian and fat-tailed), and missed signals lower. The sensitivity check: the verdict must
    reject the no-floors reference, or it cannot see a floor change at all."""
    review_dependent = {c["id"] for c in CASES if c.get("review_dependent")}
    neg = [(case["id"], r["cases"][case["id"]]) for case in CASES if case["kind"] == "negative" for r in rows]
    pos = [(case["id"], r["cases"][case["id"]]) for case in CASES if case["kind"] == "positive" for r in rows]
    noise_cases = [case for case in search if not SEARCH["cases"][case]["positive"]]
    variants: dict[str, Any] = {}
    for name, rule in VARIANTS.items():
        noise = [x[name] for case, trials in search.items() if not SEARCH["cases"][case]["positive"] for x in trials]
        signal = [x[name] for case, trials in search.items() if SEARCH["cases"][case]["positive"] for x in trials]
        variants[name] = {
            "rule": rule,
            "engine_false_promotion": _rate(sum(variant_verdict(r, rule) for _, r in neg), len(neg)),
            "engine_false_promotion_mechanical_scope": _rate(
                sum(variant_verdict(r, rule) for cid, r in neg if cid not in review_dependent),
                sum(1 for cid, _ in neg if cid not in review_dependent)),
            "engine_false_promotion_by_case": {c["id"]: sum(variant_verdict(r["cases"][c["id"]], rule) for r in rows)
                                               for c in CASES if c["kind"] == "negative"},
            # Negatives that passed Validation and would spend a holdout look.
            "engine_negative_looks": _rate(sum(variant_reaches_holdout(r, rule) for _, r in neg), len(neg)),
            "engine_missed_signal": _rate(sum(not variant_verdict(r, rule) for _, r in pos), len(pos)),
            "engine_missed_by_case": {c["id"]: sum(not variant_verdict(r["cases"][c["id"]], rule) for r in rows)
                                      for c in CASES if c["kind"] == "positive"},
            "search_false_promotion": _rate(sum(x["promoted"] for x in noise), len(noise)),
            # Noise that passed Validation spent a holdout look (a scarce, Holm-charged resource). The holdout is the last
            # guard; a variant that spends more of it on noise costs every later look power.
            "search_noise_holdout_looks": _rate(sum(x["looks"] > 0 for x in noise), len(noise)),
            "search_missed_signal": _rate(sum(not x["promoted"] for x in signal), len(signal)),
            "search_by_case": {case: {"promoted": sum(x[name]["promoted"] for x in trials), "of": len(trials),
                                      "with_candidates": sum(x[name]["candidates"] > 0 for x in trials),
                                      "validations": sum(x[name]["validations"] for x in trials),
                                      "holdout_looks": sum(x[name]["looks"] for x in trials),
                                      "lineages_with_look": sum(x[name]["looks"] > 0 for x in trials)}
                               for case, trials in search.items()},
        }
    base = variants["current"]
    for name, row in variants.items():
        more_looks = sorted(case for case in noise_cases if row["search_by_case"][case]["lineages_with_look"] >
                            base["search_by_case"][case]["lineages_with_look"])
        checks = {
            "engine_false_promotions_not_higher": row["engine_false_promotion"]["count"] <= base["engine_false_promotion"]["count"],
            "search_false_promotions_not_higher": row["search_false_promotion"]["count"] <= base["search_false_promotion"]["count"],
            "engine_negative_looks_not_higher": row["engine_negative_looks"]["count"] <= base["engine_negative_looks"]["count"],
            "noise_looks_not_higher_in_any_band": not more_looks,
            "missed_signals_lower": (row["engine_missed_signal"]["count"] < base["engine_missed_signal"]["count"]
                                     or row["search_missed_signal"]["count"] < base["search_missed_signal"]["count"]),
        }
        row["owner_rule"] = {"met": all(checks.values()), "checks": checks, "noise_bands_with_more_looks": more_looks}
    reference = variants.get("no_floors")
    sensitivity = {
        "no_floors_rejected": bool(reference) and not reference["owner_rule"]["met"],
        "false_promotions_see_no_floors": bool(reference) and (
            reference["engine_false_promotion"]["count"] > base["engine_false_promotion"]["count"]
            or reference["search_false_promotion"]["count"] > base["search_false_promotion"]["count"]),
        "noise_looks_see_no_floors": bool(reference) and bool(reference["owner_rule"]["noise_bands_with_more_looks"]),
    }
    return variants, sensitivity


def _source_sha() -> str:
    """This module's source with the pin line blanked: any change to the suite's code or cases changes the pin."""
    text = Path(__file__).read_text()
    lines = [("" if line.startswith("PINNED_SUITE_SHA") else line) for line in text.splitlines()]
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


def suite_fingerprint() -> str:
    return digest({"definition": suite_definition(), "search": SEARCH, "variants": VARIANTS, "source": _source_sha()})


def source_pin() -> str | None:
    """The pin as written in this file on disk (the file is the suite; a stale compiled copy of it is not)."""
    import re

    found = re.search(r'^PINNED_SUITE_SHA = "([0-9a-f]{64})"$', Path(__file__).read_text(), re.M)
    return found.group(1) if found else None


#: The interfaces the suite calls in the scored tree. main at f082cf5e is the oldest tree that has them all (the
#: production release before it lacks the review contract's `grounded_answer`, `check_experiment` and the swarm's
#: `execution_fingerprint`).
REQUIRED: tuple[tuple[str, str], ...] = (
    ("league.gym", "ENGINE_VERSION"), ("league.gym.engine", "run"), ("league.gym.engine", "RunConfig"),
    ("league.gym.batch", "run_batch"), ("league.gym.experiment", "check_experiment"),
    ("league.gym.review_contract", "grounded_answer"), ("league.gym.runtime", "load_program"),
    ("league.gym.safety", "CodeRefused"), ("league.gym.store", "Store"), ("league.gym.store", "mint_gate_capability"),
    ("league.gym.synth", "Writer"), ("league.gym.synth", "uniform_model"), ("league.gym.results", "view"),
    ("league.gym.results", "stress_block"), ("league.gym.results", "summarize"), ("league.gym.results", "by_year"),
    ("league.swarm.evaluator", "execution_fingerprint"), ("league.swarm.evidence", "train_score"),
    ("league.swarm.evidence", "drift_screen"), ("league.swarm.evidence", "drift_numbers"),
    ("league.swarm.evidence", "validation_line"), ("league.swarm.evidence", "holdout_line"),
    ("league.swarm.evidence", "traded_sharpe"), ("league.swarm.evidence", "stressed_of"),
)

#: The scored tree's files the synthetic world is built with: the store writer and the fill model must match the tree's
#: own store and engine, so they cannot be vendored. Their hash is the report's `fixture_sha`.
FIXTURES = ("league/gym/synth.py",)


def scorable() -> list[str]:
    """What the scored tree lacks of the interfaces the suite calls (empty: it can be scored)."""
    import importlib

    missing = []
    for module, name in REQUIRED:
        try:
            if not hasattr(importlib.import_module(module), name):
                missing.append(f"{module}.{name}")
        except Exception as exc:  # noqa: BLE001 - an older or broken tree is reported, never a traceback
            missing.append(f"{module} ({type(exc).__name__})")
    return missing


def runtime_versions() -> dict[str, Any]:
    """The interpreter and the libraries the synthetic streams and the store depend on."""
    import importlib

    out: dict[str, Any] = {"python": sys.version.split()[0]}
    for lib in ("numpy", "pyarrow"):
        try:
            out[lib] = importlib.import_module(lib).__version__
        except ImportError:
            out[lib] = None
    return out


def tree_fingerprint(repo: Path | None = None) -> dict[str, Any]:
    """What the scored tree's evaluator is: the Gym's execution fingerprint (every file under league/gym and league/live
    and the four shared modules), the swarm-side evidence code the suite calls, and the world's fixture."""
    from league.gym import ENGINE_VERSION
    from league.swarm.evaluator import execution_fingerprint

    repo = repo or Path(__import__("league").__file__).resolve().parents[1]
    names = ("league/swarm/evidence.py", "league/swarm/gate.py", "league/swarm/researcher.py", "league/gym/review_contract.py",
             "league/gym/experiment.py", "league/gym/results.py", "league/stats.py")
    sources = {n: hashlib.sha256((repo / n).read_bytes()).hexdigest() for n in names if (repo / n).is_file()}
    fixtures = {n: hashlib.sha256((repo / n).read_bytes()).hexdigest() for n in FIXTURES if (repo / n).is_file()}
    head, dirty = None, None
    try:
        import subprocess

        def git(*args: str) -> str | None:
            found = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=10)
            return found.stdout.strip() if found.returncode == 0 else None

        top = git("rev-parse", "--show-toplevel")
        if top and Path(top).resolve() == repo.resolve():  # never an enclosing repository's commit
            head = git("rev-parse", "HEAD")
            status = git("status", "--porcelain", "--", "league")
            dirty = None if status is None else bool(status)
    except (OSError, ValueError):
        head, dirty = None, None
    return {"git_head": head, "league_uncommitted_changes": dirty, "engine": ENGINE_VERSION,
            "execution_sha256": execution_fingerprint(repo), "evaluator_sources": sources, "evaluator_sha": digest(sources),
            "fixture_sources": fixtures, "fixture_sha": digest(fixtures)}


def admit_confirmation(frozen: Any, suite_sha: str, replications: int, search_replications: int,
                       tree: Mapping[str, Any]) -> str:
    """A confirmation run is admissible only against the frozen development report (a full report or its receipt) of
    the same pinned suite, evaluator, fixture and sample counts. Returns the frozen headline's digest; raises
    ValueError naming every difference."""
    if not isinstance(frozen, Mapping):
        raise ValueError("a confirmation run needs the frozen development report (--frozen)")
    problems = []
    if frozen.get("cohort") != "development":
        problems.append("the frozen report is not a development report")
    if not frozen.get("pinned") or frozen.get("suite_sha") != suite_sha:
        problems.append("the suite is not the pinned suite the development report ran")
    if frozen.get("replications") != replications or frozen.get("search_replications") != search_replications:
        problems.append("the sample counts differ from development's")
    before = frozen.get("tree") or {}
    problems += [f"the tree's {key} changed after development" for key in ("execution_sha256", "evaluator_sha", "fixture_sha")
                 if before.get(key) != tree.get(key)]
    if not isinstance(frozen.get("headline"), Mapping):
        problems.append("the frozen report has no headline")
    if problems:
        raise ValueError("confirmation is not admissible: " + "; ".join(problems))
    return digest(frozen["headline"])


def suite(replications: int | None = None, search_replications: int | None = None, *, cohort: str = "development",
          frozen: Mapping[str, Any] | None = None, scratch: Path | None = None,
          progress: Callable[[str], None] | None = None) -> dict[str, Any]:
    """Run the whole suite on this interpreter's `league` tree and return the report."""
    began = time.monotonic()
    reps = int(replications or PROTOCOL["replications"])
    search_reps = int(search_replications or SEARCH["replications"])
    if not 1 <= reps <= 64 or not 1 <= search_reps <= 1024:
        raise ValueError("replications must be 1..64 and search replications 1..1024")
    if cohort not in COHORTS:
        raise ValueError(f"unknown cohort {cohort!r}")
    tree = tree_fingerprint()
    pinned, computed = source_pin(), suite_fingerprint()
    frozen_sha = admit_confirmation(frozen, computed, reps, search_reps, tree) if cohort == "confirmation" else None
    base = Path(scratch) if scratch else None
    if base is not None:
        base.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="ltcm-evaluator-suite-", dir=str(base) if base else None))
    rows = []
    try:
        for r in range(reps):
            rows.append(replicate(r, work, cohort))
            if progress:
                progress(f"replication {r + 1}/{reps}: {rows[-1]['seconds']} s")
    finally:
        shutil.rmtree(work, ignore_errors=True)
        clear_numpy_marks()
    search: dict[str, list[dict[str, Any]]] = {}
    for case in SEARCH["cases"]:
        search[case] = [search_trial(case, r, cohort) for r in range(search_reps)]
        if progress:
            progress(f"search {case}: {search_reps} lineages")
    report = {"suite": SUITE_ID, "cohort": cohort, "frozen_development_headline_sha": frozen_sha, "suite_sha": computed,
              "pinned_sha": pinned, "pinned": computed == pinned, "compiled_pin_current": PINNED_SUITE_SHA == pinned,
              "full_protocol": reps == PROTOCOL["replications"] and search_reps == SEARCH["replications"],
              "replications": reps, "search_replications": search_reps, "tree": tree,
              "runtime": {**runtime_versions(), "elapsed_seconds": round(time.monotonic() - began, 1)},
              **aggregate(rows, search), "limitations": LIMITATIONS, "replication_rows": rows}
    report["owner_rule_confirmation"] = (confirm_owner_rule(frozen, report["variants"])
                                         if cohort == "confirmation" and frozen is not None else None)
    report["headline"] = headline(report)
    return report


def confirm_owner_rule(frozen: Mapping[str, Any], variants: Mapping[str, Any]) -> dict[str, Any]:
    """Per variant: the frozen development verdict, this confirmation run's, and whether both were met. Only
    `met_and_confirmed` can be cited as a variant meeting the owner's rule; a single cohort's `met` cannot."""
    before = _headline_of(frozen).get("owner_rule") or {}
    out: dict[str, Any] = {}
    for name, row in variants.items():
        development = (before.get(name) or {}).get("met")
        confirmation = row["owner_rule"]["met"]
        out[name] = {"development_met": development, "confirmation_met": confirmation,
                     "met_and_confirmed": development is True and confirmation is True}
    return out


def headline(report: Mapping[str, Any]) -> dict[str, Any]:
    """The vector a release is compared on (`compare`): per case, never only the pooled rates. A release that stops
    promoting one negative and starts promoting another, stops refusing a probe, moves impossible fills or stress
    contamination from one case to another, or weakens the review contract's answer on a case, shows here. Each
    variant's `met_and_confirmed` is None on a development run (unconfirmed) and set only by a confirmation run."""
    cases = report["cases"]
    rates = report["rates"]
    confirmation = report.get("owner_rule_confirmation")
    return {
        "suite": report["suite"], "suite_sha": report["suite_sha"], "cohort": report.get("cohort"), "pinned": report["pinned"],
        "full_protocol": report["full_protocol"],
        "tree": {k: report["tree"].get(k) for k in ("git_head", "league_uncommitted_changes", "engine", "execution_sha256",
                                                    "evaluator_sha", "fixture_sha")},
        "runtime": {k: v for k, v in report["runtime"].items() if k != "elapsed_seconds"},
        "false_promotion": rates["false_promotion"], "missed_signal": rates["missed_signal"],
        "false_promotion_mechanical_scope": rates["false_promotion_mechanical_scope"],
        "negative_cases_promoted": rates.get("negative_cases_promoted"),
        "positive_cases_missed_in_any_world": rates.get("positive_cases_missed_in_any_world"),
        "promoted_by_case": {cid: c["promoted"] for cid, c in cases.items() if c["kind"] in ("negative", "smoke")},
        "missed_by_case": {cid: c["of"] - c["promoted"] for cid, c in cases.items() if c["kind"] == "positive"},
        "refused": sorted(cid for cid, c in cases.items() if c.get("refused")),
        "impossible_fills": sum(int(c.get("impossible_fills") or 0) for c in cases.values()),
        "impossible_fills_by_case": {cid: int(c["impossible_fills"]) for cid, c in cases.items() if "impossible_fills" in c},
        "stress_contaminated_total": sum(int(c.get("stress_contaminated") or 0) for c in cases.values()),
        "stress_contaminated": {cid: c["stress_contaminated"] for cid, c in cases.items() if c.get("stress_contaminated")},
        "review_contract": {cid: dict(c["review_contract"]) for cid, c in cases.items() if c.get("review_contract")},
        "proofs_held": {k: v["held"] for k, v in report["proofs"].items()},
        "proofs_failed": [k for k, v in report["proofs"].items() if v["held"] < v["of"]],
        "facts_contradicted": report["facts_contradicted"],
        "ablations": {k: {"broken": v["broken"], "static_refused": v["static_refused"],
                          "behavioral_effective": v["behavioral_effective"]} for k, v in report["ablations"].items()},
        "ablation_rates": report["ablation_rates"], "level_invariance_probe": report["level_invariance_probe"],
        "owner_rule": {name: {"met": v["owner_rule"]["met"],
                              "failed": sorted(k for k, ok in v["owner_rule"]["checks"].items() if not ok),
                              "noise_bands_with_more_looks": v["owner_rule"]["noise_bands_with_more_looks"],
                              "met_and_confirmed": None if confirmation is None else
                              bool((confirmation.get(name) or {}).get("met_and_confirmed"))}
                       for name, v in report["variants"].items()},
        "verdict_sensitivity": report.get("verdict_sensitivity"),
        "elapsed_seconds": report["runtime"]["elapsed_seconds"],
    }


def _headline_of(value: Mapping[str, Any]) -> Mapping[str, Any]:
    """A headline from a full report, a receipt, or a headline itself."""
    if isinstance(value.get("headline"), Mapping):
        return value["headline"]
    if "replication_rows" in value:
        return headline(value)
    return value


def compare(old: Mapping[str, Any], new: Mapping[str, Any]) -> dict[str, Any]:
    """What changed between two runs, case by case. Comparable only for the same pinned suite, cohort and world fixture
    at the full protocol; a different Python, numpy or pyarrow is noted (the synthetic streams may shift with them)."""
    a, b = _headline_of(old), _headline_of(new)
    why_not = [f"{key} differs" for key in ("suite_sha", "cohort") if a.get(key) != b.get(key)]
    if (a.get("tree") or {}).get("fixture_sha") != (b.get("tree") or {}).get("fixture_sha"):
        why_not.append("the world's fixture (league/gym/synth.py) differs: rates would move for reasons not the evaluator's")
    if not all(h.get("pinned") and h.get("full_protocol") for h in (a, b)):
        why_not.append("a run is unpinned or not at the full protocol")
    ra, rb = a.get("runtime") or {}, b.get("runtime") or {}
    notes = [f"{lib} differs ({ra.get(lib)} then {rb.get(lib)}): the synthetic streams may shift"
             for lib in ("python", "numpy", "pyarrow") if ra.get(lib) != rb.get(lib)]
    worse: list[str] = []
    better: list[str] = []

    def step(label: str, before: Any, after: Any, *, higher_is_worse: bool = True) -> None:
        if not isinstance(before, (int, float)) or not isinstance(after, (int, float)) or before == after:
            if (before is None) != (after is None):
                worse.append(f"{label}: {before} then {after} (the case set changed)")
            return
        (worse if (after > before) == higher_is_worse else better).append(f"{label}: {before} then {after}")

    for key, label in (("promoted_by_case", "promoted"), ("missed_by_case", "missed")):
        was, now = a.get(key) or {}, b.get(key) or {}
        for cid in sorted(set(was) | set(now)):
            step(f"{cid} {label}", was.get(cid), now.get(cid))
    refused_was, refused_now = set(a.get("refused") or []), set(b.get("refused") or [])
    worse += [f"{cid} is no longer refused by the static check" for cid in sorted(refused_was - refused_now)]
    better += [f"{cid} is now refused by the static check" for cid in sorted(refused_now - refused_was)]
    # Per case, so a release that moves impossible fills or stress contamination from one case to another shows; a case
    # missing from the stress dict had none.
    was, now = a.get("impossible_fills_by_case") or {}, b.get("impossible_fills_by_case") or {}
    for cid in sorted(set(was) | set(now)):
        step(f"{cid} impossible fills", was.get(cid), now.get(cid))
    was, now = a.get("stress_contaminated") or {}, b.get("stress_contaminated") or {}
    for cid in sorted(set(was) | set(now)):
        step(f"{cid} stress-contaminated runs", was.get(cid, 0), now.get(cid, 0))
    # The review contract's answers: losing a True (a grounded rejection no longer kept, an ungrounded one no longer
    # downgraded) is a regression.
    was, now = a.get("review_contract") or {}, b.get("review_contract") or {}
    for cid in sorted(set(was) | set(now)):
        x, y = was.get(cid), now.get(cid)
        if x is None or y is None:
            worse.append(f"{cid} review contract: {x} then {y} (the case set changed)")
            continue
        for key in sorted(set(x) | set(y)):
            step(f"{cid} review contract {key}", x.get(key), y.get(key), higher_is_worse=False)
    was, now = a.get("proofs_held") or {}, b.get("proofs_held") or {}
    for name in sorted(set(was) | set(now)):
        step(f"proof {name} held", was.get(name), now.get(name), higher_is_worse=False)
    was, now = a.get("ablations") or {}, b.get("ablations") or {}
    for name in sorted(set(was) | set(now)):
        x, y = was.get(name) or {}, now.get(name) or {}
        broken = bool(y.get("broken", x.get("broken")))
        # A broken switch should be refused and should not look effective; a working one the opposite.
        step(f"{name} static refusals", x.get("static_refused"), y.get("static_refused"), higher_is_worse=not broken)
        step(f"{name} off variant removed every trade", x.get("behavioral_effective"), y.get("behavioral_effective"),
             higher_is_worse=broken)
    return {"comparable": not why_not, "why_not": why_not, "notes": notes, "regressions": worse, "improvements": better}


def receipt(report: Mapping[str, Any]) -> dict[str, Any]:
    """The public receipt of a full report: everything but the per-world rows, which it keeps as a digest (per-world
    seconds excluded, so the digest is reproducible). Neither holds a path, a quote or account data."""
    rows = [{k: v for k, v in row.items() if k != "seconds"} for row in report["replication_rows"]]
    out = {k: v for k, v in report.items() if k != "replication_rows"}
    cohort = report.get("cohort")
    out["replication_rows_sha256"] = digest(rows)
    out["title"] = f"{SUITE_ID}, {cohort} cohort: a synthetic known-answer benchmark of the evaluator, not a qualification"
    out["reproduce"] = (f"python -m league.swarm.benchmarks --suite evaluator --cohort {cohort}"
                        + (" --frozen DEVELOPMENT.json" if cohort == "confirmation" else "")
                        + " --json --output FULL.json --receipt RECEIPT.json (the rows digest excludes per-world seconds)")
    return out


def main(argv: Sequence[str] | None = None) -> int:
    """Exit codes: 0 done; 2 a confirmation run was not admissible; 3 the suite is not the pinned suite; 4 `--compare`
    found regressions or the runs are not comparable; 5 the tree lacks an interface the suite calls."""
    import argparse

    parser = argparse.ArgumentParser(prog="python -m league.swarm.benchmarks --suite evaluator", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--suite", default="evaluator", choices=("evaluator",))
    parser.add_argument("--json", action="store_true", help="print the report (without its per-world rows) as JSON")
    parser.add_argument("--output", type=Path, help="write the full report here (refused if it exists)")
    parser.add_argument("--receipt", type=Path, help="write the public receipt here (refused if it exists)")
    parser.add_argument("--compare", type=Path, help="a previous report or receipt: list regressions against it")
    parser.add_argument("--cohort", choices=COHORTS, default="development")
    parser.add_argument("--frozen", type=Path, help="confirmation: the frozen development report or receipt")
    parser.add_argument("--tree", type=Path, help="score another (trusted) checkout's league package with THIS suite file")
    parser.add_argument("--replications", type=int, default=None)
    parser.add_argument("--search-replications", type=int, default=None)
    parser.add_argument("--scratch", type=Path, default=None, help="where the synthetic stores go (default: TMPDIR)")
    parser.add_argument("--allow-unpinned", action="store_true", help="develop the next suite id; its report is not comparable")
    args = parser.parse_args(argv)
    for path in (args.output, args.receipt):
        if path and path.exists():
            parser.error(f"{path} already exists; keep benchmark receipts immutable")
    if args.cohort == "confirmation" and not args.frozen:
        parser.error("a confirmation run needs --frozen DEVELOPMENT (the development report or receipt, frozen first)")
    if args.tree:
        return run_on_tree(args.tree, args)
    missing = scorable()
    if missing:
        print(f"this tree cannot be scored by {SUITE_ID}: it lacks {', '.join(missing)} "
              "(main at f082cf5e is the oldest tree that can be)", file=sys.stderr)
        return 5
    frozen = json.loads(args.frozen.read_text()) if args.frozen else None
    old = json.loads(args.compare.read_text()) if args.compare else None
    try:
        report = suite(args.replications, args.search_replications, cohort=args.cohort, frozen=frozen, scratch=args.scratch,
                       progress=lambda text: print(text, file=sys.stderr, flush=True))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=1, sort_keys=True, default=str, allow_nan=False) + "\n")
    if args.receipt:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(json.dumps(receipt(report), indent=1, sort_keys=True, default=str, allow_nan=False) + "\n")
    shown = {k: v for k, v in report.items() if k != "replication_rows"} if args.json else dict(report["headline"])
    comparison = compare(old, report) if old is not None else None
    if comparison is not None:
        shown["comparison"] = comparison
    print(json.dumps(shown, indent=1, sort_keys=True, default=str, allow_nan=False))
    if not report["pinned"] and not args.allow_unpinned:
        print(f"the suite's hash {report['suite_sha'][:16]} is not the pinned {str(report['pinned_sha'])[:16]}: this is "
              f"not {SUITE_ID}; its numbers are not comparable", file=sys.stderr)
        return 3
    if comparison is not None and (comparison["regressions"] or not comparison["comparable"]):
        return 4
    return 0


def run_on_tree(tree: Path, args: Any) -> int:
    """Score another checkout: this suite file runs against the tree's own `league` package, in a child process with the
    tree first on its path, so the cases are never the tree's own copy. The tree's code runs in the same interpreter
    as the suite, with the operator's environment: this guards against accidental drift, not a hostile tree."""
    import subprocess

    tree = tree.resolve()
    if not (tree / "league" / "gym" / "engine.py").is_file():
        raise SystemExit(f"{tree} is not a checkout with league/gym")
    forward = ["--suite", "evaluator", "--cohort", args.cohort]
    if args.json:
        forward.append("--json")
    for flag, value in (("--output", args.output), ("--receipt", args.receipt), ("--compare", args.compare),
                        ("--frozen", args.frozen), ("--scratch", args.scratch)):
        if value is not None:
            forward += [flag, str(Path(value).resolve())]
    for flag, value in (("--replications", args.replications), ("--search-replications", args.search_replications)):
        if value is not None:
            forward += [flag, str(value)]
    if args.allow_unpinned:
        forward.append("--allow-unpinned")
    boot = ("import importlib.util, sys; sys.path.insert(0, sys.argv[1]); "
            "spec = importlib.util.spec_from_file_location('ltcm_evaluator_suite', sys.argv[2]); "
            "mod = importlib.util.module_from_spec(spec); sys.modules['ltcm_evaluator_suite'] = mod; "
            "spec.loader.exec_module(mod); sys.exit(mod.main(sys.argv[3:]))")
    env = dict(__import__("os").environ, PYTHONHASHSEED="0")
    env.pop("PYTHONPATH", None)
    return subprocess.run([sys.executable, "-c", boot, str(tree), str(Path(__file__).resolve()), *forward], cwd=str(tree),
                          env=env, check=False).returncode


PINNED_SUITE_SHA = "ce1617764510c9963edc2ead3ad5a12f6a31876d747afb5ba1529ace847f4094"


if __name__ == "__main__":
    sys.exit(main())
