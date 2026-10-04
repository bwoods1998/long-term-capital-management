"""THE FORWARD LADDER: evidence v3, the route from practice to real money (the owner's D2 of Oct 2, 2026: "forward
ladder YES"; the plan's Phase 3).

    Train (the Gym, 2020-2024) -> Validation (2025; its line unchanged) -> PRACTICE (shadow on live quotes, an immutable
    version, every session recorded) -> PRE-FILTER (the 2026 holdout read once on a gate box as a FREE read, asked for
    only once a checkpoint of the practice record has met every other line: no look row, no Holm, no look budget; its
    own line, L6) -> PROBE (real, the money table's sizes) -> SIZED (real, Kelly on the real fills' lower bound:
    `league/live/money.py`)

ENTRANTS. Every practice cohort frozen from this release on (`ObserveStore.freeze`: the validated tier and the Train
tier, as the practice league takes them) is a ladder cohort and an ENTRANT: one `entrants` row of its own with its
admission, a trial of its lineage and of the desk. Its program and parameters are its snapshot's, for good. THE
RE-ENTRY RULE (`league/live/observe.py`): a program is frozen again, as a NEW cohort and a NEW entrant with its own
window, record and p-value, only when a release changed the practice evaluator while its cohort was still inside its
window and had no final verdict (not judged at its last checkpoint, not latched). A cohort whose window ended, that
failed, was promoted or demoted, or ended without an answer never practises again under its version; the earlier
entrant keeps its p-value and its place in the trailing window.

THE PROBE LINE (the constitution's `options_money.ladder`, `Rules`) reads the cohort's own practice record alone (its
immutable version, its own practice evaluator, its PROGRAM closes from its own first day on its own practice accounts:
the House's wind-down closes and every close of an earlier cohort's account are left out).

THE CHECKPOINTS (`checkpoint_due`), the table's rule for when a record is judged for promotion, each at most once:
`checkpoints` names them by sessions practised, each with its own nominal level in `alphas`. The last is the practice
window (`max_sessions`): it falls due at the session's end at which the cohort's calendar sessions from its first day
reach it, with whatever the cohort has practised, and no earlier one is judged after it. An earlier one falls due at the
first session's end at which the cohort has practised that many sessions. A checkpoint is judged at the first session's
end at or after it is due, on the record through that session; a cohort whose first checkpoint falls due only when its
window ends is judged once, at the last alpha. At a checkpoint with alpha `a` (`judge`):

  L1 RECORD    at least `min_sessions` sessions practised (its practice row's sessions) and `min_closes` program
               closes (a close is counted on its exit day: the per-session counts are in the receipt);
  L2 BOUND     THE TILTED TEST (`tilted_p`) of the mean return per dollar of maximum loss: its p-value at or under `a`;
               AND THE PERCENTILE TEST (`percentile_p`): the share of its resampled means at or below zero at or under
               1 - `confidence` (its one-sided `confidence` lower bound above zero);
  L3 WINDOWS   the cohort's calendar sessions from its first day split in `windows` equal contiguous sub-windows: the
               returns of the closes in at least `windows_positive` of them sum above zero;
  L4 DRIFT     THE DRIFT CONTROL: each close's P&L net of its ENTRY DELTA times the underlying's move over its holding
               period (the position's dollar delta at the decision, from the engine's own context: each leg's delta x
               side x ratio x 100 x quantity; times the underlying at its exit, recorded with the trade, less the
               underlying at its entry), per dollar of maximum loss: THE TILTED TEST on those drift-adjusted returns,
               its p-value at or under `a`. It runs on the closes whose figures are known when they are at least
               `drift_known_share` of its closes; under that share its p-value is 1. A program whose P&L is its delta
               riding the market's move (drift) fails it; one whose edge does not come from its delta (premium,
               volatility, timing of the option's price rather than the underlying's) keeps it. It is deliberately
               strict: a directional timing edge, whose P&L IS its delta times the move it timed, fails it too (the
               benchmark's planted directional world measures what this costs).

THE TWO TESTS, day-block bootstraps over the session days that closed a trade (`day_sums`: `s_d` the day's summed
returns, `c_d` its closes, days ascending; the mean is `m = sum(s) / sum(c)`), `draws` resamples of as many days,
deterministic for a seed. Either is p = 1 with fewer than two such days or `m` at or below zero.

  TILTED       the days are resampled with weights `w_d` proportional to `exp(L (s_d - max s))`, where `L < 0` solves
               `sum(s_d exp(L (s_d - max s))) = 0` (bisection from -1, doubling, 100 steps, the lower bracket kept): the
               record reweighted to a mean of zero. Its p-value is the share of resampled means at or above `m`, at
               least 1 / (`draws` + 1). A record with no losing day (no `s_d` below zero) cannot be tilted: p = 1. A
               tilt whose weights are not finite (every losing day tiny against the largest day) is p = 1 too, said in
               the figures (`tilt`: "weights").
  PERCENTILE   the days are resampled uniformly. Its p-value is the share of resampled means at or below zero, at
               least 1 / (`draws` + 1).

The alphas are nominal: the tilted test is not studentized (its measured size under a null is above its alpha), and the
no-losing-day rule is a cliff (a premium record whose losing days are all tiny gets a small p-value). Recorded limits.
The House seeds the three resamples from the record's inputs hash (`inputs_hash`, the checkpoint in it) with ":r" (the
returns), ":adj" (the drift-adjusted returns) and ":perc" (the percentile test); `judge(seed=)` takes another base (the
benchmark's).

THE SESSION END (`end_of_day`, from `OptionsLive._end_of_day`) judges a cohort ONLY at a checkpoint that is due, once.
A session's end the House missed, a judgement that raised, or a record that is not whole yet (closes of the cohort's
own account that the practice record could not take at the close, `OptionsLive.practice_unexported`: they are offered
again) leaves the checkpoint due: it is judged at the first session's end that judges it, on the record through that
session. On every other night the cohort gets no judgement and its entrant's p-value stands. Then, on the night's
figures:

  L5 FDR       Benjamini-Hochberg at `fdr_q` over every entrant of the trailing `fdr_days` days, each at the tilted
               p-value on the returns of its LATEST judged checkpoint (1 before its first checkpoint, and without a
               full record, L1; never rewritten between checkpoints or after its cohort ends), the cohorts judged that
               night at that night's: its p-value is one the procedure rejects. A judged cohort is always in its own
               family.

A checkpoint's judgement is ONE receipt naming it (`ladder_decisions`: its inputs' hash, its figures, the reason a tilted
p-value is 1 among them, its BH rank and family size, its verdict), written with the entrant's p-value and the cohort's
state in one transaction (`ObserveStore.add_decision`): "ineligible" (its practice record began before its cohort),
"short" (L1), "fail" (the lines it missed), "blocked" (it met L1-L5 and its snapshot names no run sha: nothing can be
asked of the gate on it, so that verdict is final and the cohort ends `failed`, for good), or one of the latch's below.
A cohort that does not meet the lines practises on to its next checkpoint; after its last, it ends at its window.

THE LATCH. A checkpoint that meets L1-L5 is FINAL: the cohort is LATCHED on it (`cohorts.ladder_state`), no line is
judged again and nothing it practises afterwards is evidence. Then, in this order:

  L0 VALIDATION the Validation line, unchanged (the ladder's second rung): the version's latest validation ON THE GYM
               IN FORCE met the line (`bands.validation_passed`: the tournament's record of each version's latest
               verdict, else the family's own line). It is Gym evidence: the same Gym image and bundle answer the
               same, whatever the live path's code, so a verdict judged under an earlier execution fingerprint on
               that Gym is the version's verdict. A release that changes league/live alone therefore leaves L0 as it
               was (the swarm keeps the line, and gives back one such a release cleared before:
               `league/swarm/evaluator.py`); what it does restart is this file's own evidence, the practice cohort
               under the new practice evaluator, with its own record, receipt and pre-filter answer. A release that
               changes the Gym clears the line, and L0 waits for a validation on the new Gym. A validation that did
               not meet the line ends the cohort `failed` ("validation_failed"), for good. None yet (a Train-tier
               entrant the tournament has not validated, or no swarm store to ask): the latch waits for it
               ("await_validation"). Every entrant, validated or not, is a trial of the desk's false-discovery
               control (L5);
  L6 PRE-FILTER the gate's free read of the 2026 holdout (`league/swarm/gate.py`, `Gate.prefilter_round`), requested
               once L0 is met ("await_prefilter"; kv `ladder_prefilter_requests`, the House's) and written by the gate
               (kv `ladder_prefilter:<run_sha>`, the gate's), on the Gym bundle the House runs. It PASSES when the
               holdout's net P&L after fees is not negative AND the moving-block bootstrap of its daily P&L (block 5,
               2,000 draws, the gate's seed "prefilter:<run_sha>"; the share of resampled means at or below zero) has a
               p-value at or under `prefilter_p` (`prefilter_answer`: both are read from the record's own figures, at
               the stricter of the level the gate judged at and the table's; a record without that level, written
               before the line, is no answer, and the read is asked for again).

THE ANSWER SESSION (`_answer`). A latch is read at a LATER session's end than its checkpoint's, and no line is judged: its
Validation verdict while it waits for one, then the pre-filter's record. A read that passes: PROMOTED when `binding` is
true (THE LADDER'S BELT first), else "would_promote", written ONCE, with the belt's reading recorded in it (it refuses
nothing); the cohort then practises on to its window with no further judgement and ends `complete`. A read that does
not pass ends the cohort `failed` ("prefilter_negative"), for good. THE WAIT is at most `answer_sessions` sessions after
the checkpoint's, for both waits together: the session's end at which that many have passed without an answer ends the
cohort `complete`, unpromoted ("unanswered"); so does a read the gate could not make (its tries spent: its record
"failed") and a latch that no session's end read inside the wait. The House alerts once when a latch has waited more
than one session. The gate reads only while the swarm's budget guard lets it run: the pre-filter is not exempt from
that brake, nor from the gate's own leakage alarm (`league/swarm/gate.py`: ten sealed looks or more with over 30% of
them passing stop the whole gate, this read with it; the sealed look is retired, so that count no longer grows). A
latch whose read is stopped either way ends unanswered at the wait's limit. An answer's receipt names no checkpoint: it
carries its checkpoint's inputs, figures, p-value and BH figures, names that receipt (`latch`) and says what was read
(`answer`), and is written with the latch and the cohort's ending in one transaction (`ObserveStore.add_answer`).

THE WINDOW (`max_sessions`; `ObserveStore.cohort_candidates`, `observe.ladder_window`). A cohort runs until it is
promoted, failed, or its practice window ends; the old observation target (3 sessions, 10 closes) never ends a ladder
cohort. Past its window the House keeps, in its slot: a cohort whose latch still waits, until its answer or the wait's
limit (the last checkpoint's answer is read one session past the window at the earliest); and a cohort whose last
checkpoint is not judged yet (a missed session's end), for at most `answer_sessions` sessions. The swarm's cohort keep
counts the same window (`league/swarm/practice.py`).

A PROMOTION (only while `binding` is true) goes through the swarm's store (`SwarmStore.set_band(family, "probe")`, the
receipt's id in its reason and in the family's `banded_evaluator` proof, `route` "ladder"): its banded version is the
cohort's version, whose code and parameters in the store must be the snapshot's (`run_sha` too), so the real instance
runs exactly the practised program, and it trades real money from the session after its promotion
(`OptionsLive._real_eligible`). Its typical maximum loss must be known (the median one-lot unit of its practice closes,
else the store's own for that version): the money table's Probe screen needs it to show the cap fits, so without one
the promotion is refused. The live path takes a ladder proof only with its receipt: a `promote` row of this file
naming the same family, version and program (`bands.ladder_receipt`, read by `bands.read` and
`SwarmFamilies.confirm_band`). THE LADDER'S BELT comes first (`bands.ladder_refusal`: the family alive in the Gym band,
the version's Validation line met, the version undemoted (by the Gym or by the ladder), no review, audit, refusal,
failed holdout look or bar against the program): a refusal ends the cohort `failed` ("blocked"). A belt that could not
be READ (`bands.BELT_UNREAD`: the swarm's store, the gate's owed bars) refuses nothing and fails nothing: the answer is
read again at the next session's end, inside the wait. THE RECEIPT NEVER STANDS WITHOUT ITS BAND: it is written PENDING
(`promote_pending`: a promotion to no reader), the swarm's band is written naming it, and only then is it settled
`promote`, with the cohort `promoted` and its latch answered, in one transaction (`ObserveStore.settle_answer`); the
`live.band` record follows. A band the store refused (the family holds another band, say) settles it "blocked" and the
cohort `failed`. A band move that raised leaves the answer to be read again at the next session's end, its receipt void
(`promote_void`) once the store shows no band of it (pending while the store cannot be read). NO RECEIPT STAYS PENDING:
each session's end first sets every pending receipt against the swarm's store (`_settle_pending`), whatever its cohort's
evaluator or status (a release may have changed the evaluator since, and the pins ended its cohort). A family that holds
the band the ladder gave that very program by that receipt settles it `promote`: its cohort ends `promoted` when it is
still active, and its move is recorded. A store that shows no band of it makes it void; a store that cannot be read
leaves it pending for the next session's end. Until its receipt is settled the live path refuses the band, and the
budget rule counts no promotion (`league/ops/budget.py` counts a band's move only as its settled receipt's). `binding`
false: the ladder judges and records everything and promotes nothing.

A cohort whose family retired ends `failed` at the next session's end (`_reconcile`): no promotion can come of it (the
swarm's COHORT KEEP spares a family whose ladder cohort's version met the Validation line from the idle, revision and
evaluation rules, `league/swarm/tournament.py`). Each cohort is handled apart: one cohort's error (a read, a write) is
alerted, its checkpoint or its answer is taken again at the next session's end, and it stops neither another's nor the
demotions. The pre-filter's requests are swept at each session's end: only those of the cohorts whose latch waits for
the gate stay.

THE DAILY LINES (`judge_daily`, with `bootstrap` and `drift_line`) are the rule from before the checkpoints, judged every
session: L1 and L3 as above, L2 the percentile test's bound alone, L4 the mean of the drift-adjusted returns above zero
with those figures known for at least `drift_known_share` of its closes. Nothing judges by them now: the House's
session end and the benchmark's desk (`league/swarm/forward_benchmarks.py`, which plays this module's checkpoints, latch
and answer session through `checkpoint_due`, `judge` and `benjamini_hochberg`) both judge at the checkpoints.

DEMOTION (at each session's end): a ladder Probe or Sized family (and a Candidate the money table moved down) goes back
to the GYM, its cohort "demoted", when its forward record since its promotion (`money.one_record`: its own version,
one source a day, real first) is negative over 20 trades, or the one-sided `demote_confidence` lower bound of the
mean of its trailing `demote_sessions` session days is below zero (`money.session_bound`). A demoted program never
returns to Probe but through a new version's new cohort.

NEVER EVIDENCE: the incubator's trades (`:i`), tuition, the calibration round trips and the House live test are never
in a practice record (`observe.sqlite`'s trades are the shadow book's alone), so none of them is ladder evidence.

THE SEALED-LOOK FAST LANE (`fast_lane_band`): a program qualified by Validation and its sealed unseen pass enters
Probe immediately. The practice ladder records alongside it. This separate binding authority decides only later
size increases and demotion using the existing real-fill, Probe-tenure and post-selection requirements. Each change
first writes `fast_lane_proposed`, an exact-snapshot decision, then the swarm atomically confirms and records its band
event. A proposal alone never proves the band moved. Existing current qualified Sized bands need no retrospective
receipt migration; every later transition uses this authority.

Every write here is the House's: the practice record and its receipts in `<state>/observe.sqlite`, the band and the
pre-filter request in `<state>/swarm.sqlite` (through the House's own connection, `SwarmFamilies`).
"""

from __future__ import annotations

import bisect
import datetime as dt
import hashlib
import json
import math
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo

from .observe import LATCH_WAITS, PROMOTE_PENDING

NEW_YORK = ZoneInfo("America/New_York")
#: The snapshot marker of a ladder cohort (`ObserveStore.freeze`).
LADDER_VERSION = 1
#: The sealed-look fast lane uses its own band decisions, never a practice checkpoint or another unseen read.
FAST_LANE_AUTHORITY = "sealed-look-sizing-v1"
FAST_LANE_PROPOSED = "fast_lane_proposed"
#: Contracts a structure is quoted for (the venue's multiplier).
MULTIPLIER = 100.0
#: An exit's underlying is the last price read at most this many minutes before its fill (`exit_spot`).
EXIT_SPOT_STALE_MINUTES = 5
#: The swarm store's key-values of the pre-filter (`league/swarm/gate.py`): the House's requests, the gate's results.
PREFILTER_REQUESTS = "ladder_prefilter_requests"
PREFILTER_KEY = "ladder_prefilter:"
#: A promotion's receipt whose band move raised and whose band the swarm's store does not hold: never a promotion.
PROMOTE_VOID = "promote_void"
#: The verdicts a receipt can carry: a checkpoint's judgement, a latched cohort's answer, a promotion's receipt (pending,
#: void, or `promote` once its band landed), a demotion, or a fast-lane sizing proposal (application is the swarm event).
VERDICTS = ("ineligible", "short", "fail", "blocked", "await_validation", "await_prefilter", "validation_failed",
            "prefilter_negative", "unanswered", "would_promote", PROMOTE_PENDING, PROMOTE_VOID, "promote", "demote",
            FAST_LANE_PROPOSED)
#: A checkpoint's figures (`judge`) that its receipt's `stats` carry (its inputs' hash and its p-value have their own
#: columns).
RECEIPT_STATS = ("checkpoint", "alpha", "sessions", "calendar_sessions", "closes", "per_session", "mean", "days", "draws",
                 "p_adj", "perc_p", "lcb", "tilt", "windows", "windows_positive", "drift", "typical", "lines")


# ------------------------------------------------------------------------------------------------------- the rules
@dataclass(frozen=True)
class Rules:
    """The constitution's `options_money.ladder`, read (the module docstring)."""

    binding: bool
    min_sessions: int
    min_closes: int
    confidence: float
    draws: int
    windows: int
    windows_positive: int
    fdr_q: float
    fdr_days: int
    max_sessions: int
    checkpoints: tuple[int, ...]
    alphas: tuple[float, ...]
    prefilter_p: float
    answer_sessions: int
    drift_known_share: float
    demote_sessions: int
    demote_confidence: float

    @classmethod
    def from_constitution(cls, constitution: Mapping[str, Any] | None = None) -> "Rules":
        """The ladder in force; ValueError when the money table is refused (nothing is promoted on a bad table)."""
        from ..constitution import CONSTITUTION, options_money_problems

        rules = dict(constitution or CONSTITUTION)
        problems = options_money_problems(rules)
        if problems:
            raise ValueError("the forward ladder's table is refused: " + "; ".join(problems))
        t = rules["options_money"]["ladder"]
        return cls(binding=t["binding"] is True, min_sessions=int(t["min_sessions"]), min_closes=int(t["min_closes"]),
                   confidence=float(t["confidence"]), draws=int(t["draws"]), windows=int(t["windows"]),
                   windows_positive=int(t["windows_positive"]), fdr_q=float(t["fdr_q"]), fdr_days=int(t["fdr_days"]),
                   max_sessions=int(t["max_sessions"]), checkpoints=tuple(int(x) for x in t["checkpoints"]),
                   alphas=tuple(float(x) for x in t["alphas"]), prefilter_p=float(t["prefilter_p"]),
                   answer_sessions=int(t["answer_sessions"]), drift_known_share=float(t["drift_known_share"]),
                   demote_sessions=int(t["demote_sessions"]), demote_confidence=float(t["demote_confidence"]))

    def alpha(self, checkpoint: int) -> float:
        """The nominal level of the checkpoint named by its sessions; ValueError when the table names no such one."""
        if isinstance(checkpoint, bool) or checkpoint not in self.checkpoints:
            raise ValueError(f"the ladder has no checkpoint at {checkpoint!r} sessions: {list(self.checkpoints)}")
        return self.alphas[self.checkpoints.index(checkpoint)]


# ------------------------------------------------------------------------------------------------------ the record
@dataclass(frozen=True)
class Close:
    """One program close of a practice record: its exit day, its return on maximum loss, the same net of its entry
    delta times the underlying's move (None when a figure is unknown), and its one-lot unit (maximum loss a lot plus
    twice the fees a lot; None without a quantity)."""

    day: str
    r: float
    r_adj: float | None
    unit: float | None
    key: str = ""


def _num(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _body(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    try:
        out = json.loads(value or "{}")
    except (TypeError, ValueError):
        return {}
    return out if isinstance(out, dict) else {}


def entry_delta(body: Mapping[str, Any]) -> float | None:
    """The position's dollar delta at its decision (per dollar of the underlying): each leg's delta (the engine's
    context, in the legs' order) x its side (+1 long, -1 short) x its ratio, x 100 x the quantity. None when a figure is
    missing or not finite."""
    context = body.get("context") if isinstance(body.get("context"), Mapping) else {}
    legs, deltas = body.get("legs"), context.get("delta")
    qty = _num(body.get("qty"))
    if not isinstance(legs, list) or not isinstance(deltas, list) or not legs or len(legs) != len(deltas) or not qty:
        return None
    total = 0.0
    for leg, delta in zip(legs, deltas):
        d = _num(delta)
        side = {"long": 1.0, "short": -1.0}.get(str((leg or {}).get("side"))) if isinstance(leg, Mapping) else None
        ratio = _num(leg.get("ratio") if isinstance(leg, Mapping) else None)
        if d is None or side is None or ratio is None:
            return None
        total += side * ratio * d
    return total * MULTIPLIER * qty


def drift_usd(body: Mapping[str, Any]) -> float | None:
    """THE DRIFT CONTROL's charge on one close: its entry delta times the underlying's move from its entry (the
    decision's spot) to its exit (`exit_spot`, recorded with the trade). None when a figure is unknown."""
    delta = entry_delta(body)
    context = body.get("context") if isinstance(body.get("context"), Mapping) else {}
    entry, exit_ = _num(context.get("spot")), _num(body.get("exit_spot"))
    if delta is None or entry is None or exit_ is None or entry <= 0 or exit_ <= 0:
        return None
    return delta * (exit_ - entry)


def close_of(row: Mapping[str, Any]) -> Close | None:
    """A ledger row (`ObserveStore.ladder_rows`: pnl, max_loss, exit_day, body) as a `Close`; None when it has no
    positive maximum loss (no return)."""
    pnl, max_loss = _num(row.get("pnl")), _num(row.get("max_loss"))
    day = str(row.get("exit_day") or "")
    if pnl is None or max_loss is None or max_loss <= 0 or not day:
        return None
    body = _body(row.get("body"))
    drift = drift_usd(body)
    qty, fees = _num(body.get("qty")), _num(body.get("fees")) or 0.0
    unit = max_loss / qty + 2.0 * fees / qty if qty and qty >= 1 else None
    return Close(day=day[:10], r=pnl / max_loss, r_adj=None if drift is None else (pnl - drift) / max_loss,
                 unit=unit if unit is not None and math.isfinite(unit) and unit > 0 else None,
                 key=str(row.get("seq") if row.get("seq") is not None else row.get("trade_id") or ""))


def sessions_between(first: str, last: str) -> list[str]:
    """The NYSE session days from `first` to `last`, both included (the live path's own calendar)."""
    from .chains import session_minutes

    out, day, end = [], dt.date.fromisoformat(first), dt.date.fromisoformat(last)
    while day <= end:
        if session_minutes(day) is not None:
            out.append(day.isoformat())
        day += dt.timedelta(days=1)
    return out


# ------------------------------------------------------------------------------------------------------ the lines
#: Why a tilted p-value is 1 without a resample (the receipt's `tilt`; the module docstring's THE TWO TESTS): fewer than
#: two session days with a close, a mean at or below zero, no losing day, the tilt's weights not finite; and, from
#: `judge`, a record that is not full (L1) or drift figures known for too few closes (L4).
TILT_DAYS, TILT_MEAN, TILT_NO_LOSS, TILT_WEIGHTS = "days", "mean", "no_losing_day", "weights"
TILT_RECORD, TILT_UNKNOWN = "record", "unknown"


def day_sums(closes: Sequence[Close], *, adjusted: bool = False) -> tuple[Any, Any]:
    """THE TWO TESTS' blocks: (`s`, `c`), numpy arrays over the session days that closed a trade, days ascending: each
    day's summed returns (in close order) and its closes. `adjusted`: the drift-adjusted returns, over the closes whose
    figure is known (a day with none is no block)."""
    import numpy as np

    by_day: dict[str, list[float]] = {}
    for close in closes:
        x = close.r_adj if adjusted else close.r
        if x is None:
            continue
        acc = by_day.setdefault(close.day, [0.0, 0.0])
        acc[0] += x
        acc[1] += 1.0
    keys = sorted(by_day)
    return np.array([by_day[k][0] for k in keys]), np.array([by_day[k][1] for k in keys])


def _rng(seed: str) -> Any:
    import numpy as np

    return np.random.default_rng(int(hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16], 16))


def tilted(s: Any, c: Any, *, draws: int, seed: str) -> tuple[float, str | None]:
    """THE TILTED TEST on the blocks of `day_sums` (the module docstring): (its p-value, why it is 1 without a resample:
    one of `TILT_DAYS`, `TILT_MEAN`, `TILT_NO_LOSS`, `TILT_WEIGHTS`; None when the days were resampled). Deterministic
    for a seed."""
    import numpy as np

    days = len(s)
    if days < 2:
        return 1.0, TILT_DAYS
    m = s.sum() / c.sum()
    if not m > 0:
        return 1.0, TILT_MEAN
    if not (s < 0).any():
        return 1.0, TILT_NO_LOSS
    top = s.max()

    def f(lam: float) -> float:
        return float((s * np.exp(lam * (s - top))).sum())

    with np.errstate(over="ignore", invalid="ignore"):  # a tilt that overflows is read below, never raised
        lo, hi = -1.0, 0.0
        while f(lo) > 0:
            lo *= 2.0
        for _ in range(100):
            mid = 0.5 * (lo + hi)
            if f(mid) > 0:
                hi = mid
            else:
                lo = mid
        w = np.exp(lo * (s - top))
        total = w.sum()
    if not np.isfinite(total):
        return 1.0, TILT_WEIGHTS
    w /= total
    idx = _rng(seed).choice(days, size=(int(draws), days), p=w)
    means = s[idx].sum(1) / c[idx].sum(1)
    return max(float((means >= m).mean()), 1.0 / (int(draws) + 1)), None


def tilted_p(s: Any, c: Any, *, draws: int, seed: str) -> float:
    """THE TILTED TEST's p-value (`tilted`)."""
    return tilted(s, c, draws=draws, seed=seed)[0]


def percentile(s: Any, c: Any, *, draws: int, seed: str, confidence: float | None = None) -> tuple[float, float | None]:
    """THE PERCENTILE TEST on the blocks of `day_sums` (the module docstring): (its p-value, the one-sided `confidence`
    lower bound of its resampled means; None without a `confidence` or a resample). Deterministic for a seed."""
    import numpy as np

    days = len(s)
    if days < 2:
        return 1.0, None
    m = s.sum() / c.sum()
    if not m > 0:
        return 1.0, None
    idx = _rng(seed).integers(0, days, size=(int(draws), days))
    means = s[idx].sum(1) / c[idx].sum(1)
    p = max(float((means <= 0).mean()), 1.0 / (int(draws) + 1))
    if confidence is None:
        return p, None
    return p, float(np.sort(means)[int((1.0 - float(confidence)) * len(means))])


def percentile_p(s: Any, c: Any, *, draws: int, seed: str) -> float:
    """THE PERCENTILE TEST's p-value (`percentile`)."""
    return percentile(s, c, draws=draws, seed=seed)[0]


def percentile_line(confidence: float) -> float:
    """The level the percentile test's p-value is held to: 1 - `confidence` (0.05 at the plan's 95%)."""
    return round(1.0 - float(confidence), 12)


def bootstrap(closes: Sequence[Close], *, confidence: float, draws: int, seed: str) -> dict[str, Any]:
    """THE PERCENTILE TEST of a record's closes (the module docstring): {mean, lcb, p, days, draws}. Deterministic for a
    seed. A mean at or below zero, or fewer than two session days with a close, gives p = 1 and no bound (the resampled
    means could not be above zero at the line's confidence, or have no spread)."""
    s, c = day_sums(closes)
    p, lcb = percentile(s, c, draws=draws, seed=seed, confidence=confidence)
    return {"mean": float(s.sum() / c.sum()) if len(s) else None, "lcb": lcb, "p": p, "days": len(s),
            "draws": int(draws) if lcb is not None else 0}


def checkpoint_due(sessions: int | None, calendar_sessions: int, judged: Iterable[int], rules: Rules) -> int | None:
    """THE CHECKPOINTS (the module docstring): the checkpoint (named by its sessions) a session's end is for a cohort
    that has practised `sessions` sessions over `calendar_sessions` calendar sessions from its first day and has been
    judged at the checkpoints `judged`; None when none is due. The last one falls due when the window ends, whatever
    was practised, and no earlier one is judged after it; an earlier one when its sessions are practised."""
    done = {int(k) for k in judged}
    last = rules.checkpoints[-1]
    if calendar_sessions >= rules.max_sessions:
        return None if last in done else last
    practised, after = int(sessions or 0), max(done, default=0)
    for point in rules.checkpoints[:-1]:
        if point > after and practised >= point:
            return point
    return None


def windows(closes: Sequence[Close], sessions: Sequence[str], k: int) -> list[float]:
    """L3: the returns of the closes in each of `k` equal contiguous sub-windows of `sessions` (sizes differ by at most
    one session), summed. A close outside the sessions is placed by its day."""
    sessions = sorted(sessions)
    n = len(sessions)
    if n == 0 or k < 1:
        return [0.0] * max(0, k)
    starts = [sessions[(i * n) // k] for i in range(k)]
    sums = [0.0] * k
    for c in closes:
        i = min(k - 1, max(0, bisect.bisect_right(starts, c.day) - 1))
        sums[i] += c.r
    return sums


def drift_line(closes: Sequence[Close], known_share: float) -> dict[str, Any]:
    """THE DRIFT CONTROL's figures (the module docstring): {known, share, mean, passed}: the closes whose drift figure
    is known, their share, the mean of their drift-adjusted returns, and THE DAILY LINES' verdict (that mean above zero
    at a share of at least `known_share`)."""
    known = [c.r_adj for c in closes if c.r_adj is not None]
    share = len(known) / len(closes) if closes else 0.0
    mean = sum(known) / len(known) if known else None
    return {"known": len(known), "share": round(share, 6), "mean": mean,
            "passed": bool(closes) and share >= float(known_share) and mean is not None and mean > 0}


def benjamini_hochberg(ps: Iterable[float], q: float) -> tuple[float | None, int]:
    """L5: (the largest p-value Benjamini-Hochberg rejects at level `q` over `ps`, every p at or under it rejected;
    None when it rejects none) and the family size m."""
    ordered = sorted(float(p) for p in ps)
    m = len(ordered)
    cut = None
    for k, p in enumerate(ordered, 1):
        if p <= k * float(q) / m:
            cut = p
    return cut, m


def inputs_hash(cohort: Mapping[str, Any], through: str, sessions: Any, closes: Sequence[Close], rules: Rules,
                checkpoint: int | None = None) -> str:
    """The receipt's inputs: the cohort, the day, its sessions, every close's figures, the rules and the checkpoint
    judged (None: THE DAILY LINES), hashed."""
    snap = cohort.get("snapshot") or {}
    body = {"family": cohort["family"], "version": int(cohort["version"]), "run_sha": snap.get("run_sha"),
            "evaluator": snap.get("practice_evaluator"), "first_day": cohort["first_day"], "through": through,
            "sessions": sessions, "closes": [[c.key, c.day, round(c.r, 10), None if c.r_adj is None else round(c.r_adj, 10)]
                                             for c in closes], "rules": asdict(rules), "checkpoint": checkpoint}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def practised(cohort: Mapping[str, Any], practice: Mapping[str, Any] | None, through: str) -> tuple[int | None, list[str]]:
    """What THE CHECKPOINTS count of a cohort through the session day `through`: (its sessions practised, its practice
    row's, None when that row began before the cohort did; its calendar sessions from its first day)."""
    first = str(cohort["first_day"])
    if practice is None:
        sessions: int | None = 0
    elif str(practice.get("first_day") or "") < first:
        sessions = None
    else:
        sessions = int(practice.get("sessions") or 0)
    return sessions, (sessions_between(first, through) if first <= through else [])


def _record(cohort: Mapping[str, Any], practice: Mapping[str, Any] | None, rows: Sequence[Mapping[str, Any]],
            through: str) -> tuple[int | None, list[Close], dict[str, int], list[str]]:
    """A cohort's record through the session day `through`: (its sessions practised, None when its practice row began
    before the cohort did; its closes; their count per exit day; its calendar sessions from its first day)."""
    sessions, calendar = practised(cohort, practice, through)
    closes = [c for c in (close_of(r) for r in rows) if c is not None]
    per_session: dict[str, int] = {}
    for c in closes:
        per_session[c.day] = per_session.get(c.day, 0) + 1
    return sessions, closes, dict(sorted(per_session.items())), calendar


def _typical(closes: Sequence[Close]) -> float | None:
    units = sorted(c.unit for c in closes if c.unit is not None)
    return round(units[len(units) // 2], 2) if units else None


def judge(cohort: Mapping[str, Any], practice: Mapping[str, Any] | None, rows: Sequence[Mapping[str, Any]], *,
          through: str, rules: Rules, checkpoint: int, seed: str | None = None) -> dict[str, Any]:
    """Lines L1-L4 of one cohort's record through the session day `through`, AT THE CHECKPOINT named by its sessions
    (`checkpoint`, one of `rules.checkpoints`; ValueError otherwise), at that checkpoint's alpha: {inputs, checkpoint,
    alpha, sessions, calendar_sessions, closes, per_session, mean, days, draws, p (the tilted p-value on the returns:
    the entrant's, L5's input), p_adj (the same on the drift-adjusted returns), perc_p and lcb (the percentile test's
    p-value and bound), tilt {raw, adjusted: why that tilted p-value is 1 without a resample, None when it was
    resampled}, windows, windows_positive, drift {known, share, mean, p}, typical, lines {record, bound, windows,
    drift}, full, eligible}. A record that is not full (L1) has every p-value at 1 and nothing resampled. `practice` is
    its practice row (`sessions` None, ineligible, when that row began before the cohort did). `seed`: the base of the
    three resamples' seeds (the module docstring); None: the record's inputs hash."""
    alpha = rules.alpha(checkpoint)
    sessions, closes, per_session, calendar = _record(cohort, practice, rows, through)
    inputs = inputs_hash(cohort, through, sessions, closes, rules, int(checkpoint))
    base = inputs if seed is None else str(seed)
    full = sessions is not None and sessions >= rules.min_sessions and len(closes) >= rules.min_closes
    s, c = day_sums(closes)
    known = drift_line(closes, rules.drift_known_share)
    p, p_adj, perc_p, lcb = 1.0, 1.0, 1.0, None
    tilt: dict[str, str | None] = {"raw": TILT_RECORD, "adjusted": TILT_RECORD}
    if full:
        p, tilt["raw"] = tilted(s, c, draws=rules.draws, seed=base + ":r")
        if known["known"] / len(closes) >= rules.drift_known_share:
            p_adj, tilt["adjusted"] = tilted(*day_sums(closes, adjusted=True), draws=rules.draws, seed=base + ":adj")
        else:
            tilt["adjusted"] = TILT_UNKNOWN
        perc_p, lcb = percentile(s, c, draws=rules.draws, seed=base + ":perc", confidence=rules.confidence)
    sums = windows(closes, calendar, rules.windows)
    positive = sum(1 for x in sums if x > 0)
    lines = {"record": full, "bound": full and p <= alpha and perc_p <= percentile_line(rules.confidence),
             "windows": positive >= rules.windows_positive, "drift": full and p_adj <= alpha}
    return {"inputs": inputs, "checkpoint": int(checkpoint), "alpha": alpha, "sessions": sessions,
            "calendar_sessions": len(calendar), "closes": len(closes), "per_session": per_session,
            "mean": float(s.sum() / c.sum()) if len(s) else None, "days": len(s), "draws": rules.draws if full else 0,
            "p": p, "p_adj": p_adj, "perc_p": perc_p, "lcb": lcb, "tilt": tilt,
            "windows": [round(x, 6) for x in sums], "windows_positive": positive,
            "drift": {"known": known["known"], "share": known["share"], "mean": known["mean"], "p": p_adj},
            "typical": _typical(closes), "lines": lines, "full": full, "eligible": sessions is not None}


def judge_daily(cohort: Mapping[str, Any], practice: Mapping[str, Any] | None, rows: Sequence[Mapping[str, Any]], *,
                through: str, rules: Rules) -> dict[str, Any]:
    """THE DAILY LINES (the module docstring: the rule before the checkpoints, which nothing judges by now) of one
    cohort's record through the session day `through`, and the percentile test's p-value: {inputs, sessions, closes,
    per_session, mean, lcb, p, days, windows, windows_positive, drift, typical, lines {record, bound, windows, drift},
    full, eligible}. `practice` is its practice row (`sessions` None, ineligible, when that row began before the cohort
    did)."""
    sessions, closes, per_session, calendar = _record(cohort, practice, rows, through)
    inputs = inputs_hash(cohort, through, sessions, closes, rules)
    full = sessions is not None and sessions >= rules.min_sessions and len(closes) >= rules.min_closes
    boot = bootstrap(closes, confidence=rules.confidence, draws=rules.draws, seed=inputs) if full else \
        {"mean": (sum(c.r for c in closes) / len(closes)) if closes else None, "lcb": None, "p": 1.0,
         "days": len(per_session), "draws": 0}
    sums = windows(closes, calendar, rules.windows)
    positive = sum(1 for s in sums if s > 0)
    drift = drift_line(closes, rules.drift_known_share)
    lines = {"record": full, "bound": boot["lcb"] is not None and boot["lcb"] > 0,
             "windows": positive >= rules.windows_positive, "drift": drift["passed"]}
    return {"inputs": inputs, "sessions": sessions, "calendar_sessions": len(calendar), "closes": len(closes),
            "per_session": per_session, "mean": boot["mean"], "lcb": boot["lcb"],
            "p": float(boot["p"]) if full else 1.0, "days": boot["days"], "draws": boot["draws"],
            "windows": [round(s, 6) for s in sums], "windows_positive": positive, "drift": drift,
            "typical": _typical(closes), "lines": lines, "full": full, "eligible": sessions is not None}


# ---------------------------------------------------------------------------------------------- the gate's answer
def prefilter_answer(record: Any, *, bundle: str | None, level: float) -> dict[str, Any] | None:
    """THE PRE-FILTER's answer in the gate's record (L6, the module docstring): {passed, pnl, p, level}; None when the
    record holds no answer on `bundle` (the Gym bundle the House runs): no record, a read not done, one asked for or
    run on another bundle, or one written before the line (it names no `level`: only the sign of its P&L was read).
    `passed` is read from the record's own figures, never from its flag alone: the gate's verdict AND a net P&L that
    is not negative AND a p-value at or under the stricter of the level the gate judged at and `level` (the table's
    `prefilter_p`)."""
    if not isinstance(record, Mapping) or bundle is None or record.get("status") != "done" \
            or record.get("bundle") != bundle or record.get("ran_bundle") != bundle:
        return None
    judged = _num(record.get("level"))
    if judged is None:
        return None
    pnl, p = _num(record.get("pnl")), _num(record.get("p"))
    line = min(judged, float(level))
    return {"passed": record.get("passed") is True and pnl is not None and pnl >= 0 and p is not None and p <= line,
            "pnl": pnl, "p": p, "level": line}


def banded_receipt(status: Mapping[str, Any] | None, version: int, run_sha: str) -> int | None:
    """The receipt the swarm's store names for the band the ladder gave this very program (`SwarmBridge.family_status`:
    a live band, the route "ladder", the banded version and the proof's run sha this cohort's); None without one."""
    if status is None or status.get("retired") or status.get("band") not in ("candidate", "probe", "sized"):
        return None
    proof = status.get("proof") or {}
    receipt = proof.get("receipt")
    if (proof.get("route") != "ladder" or not run_sha or status.get("version") != version
            or proof.get("run_sha") != run_sha or not isinstance(receipt, int) or isinstance(receipt, bool)):
        return None
    return receipt


# ---------------------------------------------------------------------------------------------- the exit's spot
def exit_spot(trade: Mapping[str, Any], day: Any) -> float | None:
    """The underlying at a practice close's exit (THE DRIFT CONTROL's figure), read from the session's own grids while the
    trade is exported (`OptionsLive._export_one`): the last price at or at most `EXIT_SPOT_STALE_MINUTES` minutes before
    its exit minute, or the settlement level for a close without one (an expiry). None when that is not today's session,
    the root was not read or no price is known."""
    if day is None or str(trade.get("exit_day") or "")[:10] != day.day.isoformat():
        return None
    chain = getattr(day, "chains", {}).get(str(trade.get("root") or "").upper())
    if chain is None:
        return None
    under = chain.underlying
    minute = trade.get("exit_minute")
    try:
        if minute is None:
            from ..gym.engine import settlement_level

            level = float(settlement_level(under))
        else:
            mi = int(minute) - int(day.open_min)
            prices = under.price
            level = float("nan")
            for i in range(min(mi, len(prices) - 1), max(-1, mi - EXIT_SPOT_STALE_MINUTES - 1), -1):
                if math.isfinite(float(prices[i])):
                    level = float(prices[i])
                    break
    except (TypeError, ValueError, IndexError, AttributeError):
        return None
    return round(level, 4) if math.isfinite(level) and level > 0 else None


# ------------------------------------------------------------------------------------------------ the swarm's side
class SwarmBridge:
    """The ladder's reads and writes in the swarm's store (`<state>/swarm.sqlite`), through the House's own connection
    and lock (`league.live.families.SwarmFamilies`)."""

    def __init__(self, families: Any):
        self.families = families

    def _store(self) -> Any:
        return self.families._db()

    def prefilter(self, run_sha: str) -> dict[str, Any] | None:
        with self.families.lock:
            value = self._store().get(PREFILTER_KEY + str(run_sha))
        return dict(value) if isinstance(value, Mapping) else None

    def request_prefilter(self, run_sha: str, *, family: str, version: int, bundle: str | None, day: str) -> None:
        """The House's request (only the House writes `PREFILTER_REQUESTS`; the gate reads it and writes the result)."""
        with self.families.lock:
            store = self._store()
            with store.atomic():
                requests = dict(store.get(PREFILTER_REQUESTS) or {})
                old = requests.get(run_sha) or {}
                if old.get("bundle") == bundle and old.get("family") == family and old.get("version") == int(version):
                    return
                requests[str(run_sha)] = {"family": str(family), "version": int(version), "bundle": bundle, "day": day}
                store.put(PREFILTER_REQUESTS, requests)

    def sweep_prefilter(self, waiting: Iterable[str]) -> int:
        """Every request whose program is not one of `waiting` (the run shas of the cohorts whose latch waits for the
        gate) leaves the requests: its answer was read, its wait ended, its cohort ended, its family retired. How many
        left."""
        keep = {str(sha) for sha in waiting}
        with self.families.lock:
            store = self._store()
            with store.atomic():
                requests = dict(store.get(PREFILTER_REQUESTS) or {})
                gone = [sha for sha in requests if sha not in keep]
                for sha in gone:
                    requests.pop(sha)
                if gone:
                    store.put(PREFILTER_REQUESTS, requests)
        return len(gone)

    def family_status(self, family: str) -> dict[str, Any] | None:
        """The family as the swarm's store holds it: {retired, band, version (its banded version), proof (its
        `banded_evaluator`)}; None when the store has no such family."""
        with self.families.lock:
            fam = self._store().family(str(family))
        if fam is None:
            return None
        state = fam.get("state") or {}
        return {"retired": bool(fam.get("retired_at")), "band": fam.get("band"), "version": state.get("banded_version"),
                "proof": dict(state.get("banded_evaluator") or {})}

    def validation(self, family: str, version: int) -> bool | None:
        """L0, THE VALIDATION LINE (`bands.validation_passed`): True when the version's latest validation on the Gym in
        force (the image and bundle of the store's research evaluator, whatever execution fingerprint it was judged
        under) met the line, False when it did not, None when it has none on it (or the store has no such family).
        Raises when the store cannot be read."""
        from ..swarm.bands import validation_passed
        from ..swarm.evaluator import KEY

        with self.families.lock:
            store = self._store()
            fam = store.family(str(family))
            current = store.get(KEY)
        if fam is None:
            return None
        return validation_passed(fam.get("state") or {}, int(version), current)

    def refusal(self, family: str, version: int, run_sha: str) -> str | None:
        from ..swarm.bands import ladder_refusal

        return ladder_refusal(self.families.root, family=family, version=version, run_sha=run_sha)

    def promote(self, *, family: str, version: int, snapshot: Mapping[str, Any], receipt: int,
                typical: float | None, at: float) -> str | None:
        """The promotion (the module docstring), in one transaction of the swarm's store: None when it landed, else why
        not (nothing written)."""
        from ..gym import ENGINE_VERSION
        from ..gym.experiment import CONTRACT_VERSION
        from ..swarm.evaluator import execution_fingerprint
        from ..swarm.gate import run_sha

        class _Refused(Exception):
            pass

        try:
            with self.families.lock:
                store = self._store()
                with store.atomic():
                    fam = store.family(str(family))
                    if fam is None or fam.get("retired_at"):
                        raise _Refused("the family retired: it has no band to promote")
                    if fam["band"] != "gym":
                        raise _Refused(f"the family is at {fam['band']}, not in the Gym band")
                    row = store.version(str(family), int(version))
                    if row is None or row.get("code") != snapshot.get("code") or \
                            (row.get("params") or {}) != (snapshot.get("params") or {}):
                        raise _Refused("the store's version is not the practised program")
                    sha = run_sha(row)
                    if sha != snapshot.get("run_sha"):
                        raise _Refused("the store's version is not the practised program (its run sha)")
                    state = fam.get("state") or {}
                    typical_by = dict(state.get("typical_by_version") or {})
                    if typical is not None:
                        typical_by[str(int(version))] = typical
                    # The money table's Probe screen holds only a CANDIDATE whose typical unit is unknown, and the
                    # ladder bands at Probe: unknown here (as `bands.read` would give it), nothing is promoted.
                    unit = _num(typical_by.get(str(int(version)), state.get("typical_max_loss_usd")
                                               if state.get("validation_version") == int(version) else None))
                    if unit is None or unit <= 0:
                        raise _Refused("its typical maximum loss is unknown: it cannot be shown to fit the Probe's cap")
                    store.set_state(str(family), banded_version=int(version), banded_sha=row["sha"], banded_at=float(at),
                                    live_promoted_at=float(at), typical_by_version=typical_by, forward=None,
                                    ladder_receipt=int(receipt),
                                    banded_evaluator={"route": "ladder", "engine": ENGINE_VERSION,
                                                      "parameter_contract": CONTRACT_VERSION,
                                                      "execution_sha256": execution_fingerprint(), "run_sha": sha,
                                                      "practice_evaluator": snapshot.get("practice_evaluator"),
                                                      "receipt": int(receipt), "at": float(at)})
                    if store.set_band(str(family), "probe", reason=f"the forward ladder promoted it (practice receipt "
                                                                   f"{int(receipt)})") != "gym":
                        raise _Refused("its band could not be moved")
        except _Refused as exc:
            return str(exc)
        return None

    def ladder_families(self) -> list[dict[str, Any]]:
        """The alive families on a band the ladder gave (`banded_evaluator.route` "ladder"), at candidate, probe or
        sized: [{family, band, version, promoted_at}]. `promoted_at` is the LADDER's promotion (its proof's `at`), never
        the money table's `live_promoted_at`, which a later candidate -> probe move of its own rewrites (that only when
        the proof names no time)."""
        with self.families.lock:
            fams = self._store().families(alive=True)
        out = []
        for fam in fams:
            state = fam.get("state") or {}
            proof = state.get("banded_evaluator") or {}
            if fam["band"] in ("candidate", "probe", "sized") and proof.get("route") == "ladder":
                at = _num(proof.get("at"))
                out.append({"family": fam["id"], "band": fam["band"], "version": state.get("banded_version"),
                            "promoted_at": at if at is not None else _num(state.get("live_promoted_at"))})
        return out

    def forward_rows(self, family: str) -> list[dict[str, Any]]:
        with self.families.lock:
            return [dict(r) for r in self._store().forward(str(family))]

    def demote(self, family: str, *, why: str, receipt: int, at: float) -> bool:
        with self.families.lock:
            store = self._store()
            with store.atomic():
                fam = store.family(str(family))
                if fam is None or fam.get("retired_at") or fam["band"] not in ("candidate", "probe", "sized"):
                    return False
                store.set_state(str(family), ladder_demoted={"receipt": int(receipt), "why": why, "at": float(at),
                                                             "version": (fam.get("state") or {}).get("banded_version")},
                                dormant_cycles=0)
                return store.set_band(str(family), "gym", reason=f"the forward ladder demoted it: {why} (receipt "
                                                                 f"{int(receipt)})") is not None


def default_bridge(live: Any) -> Any:
    """The swarm's store when the House runs the swarm (`SwarmFamilies`), else None: the ladder then judges and records,
    and promotes nothing."""
    families = getattr(live, "families", None)
    if families is not None and callable(getattr(families, "_db", None)) and getattr(families, "root", None) is not None:
        return SwarmBridge(families)
    return None


# ------------------------------------------------------------------------------------------------------- the ladder
def fast_lane_inputs(row: Mapping[str, Any], forward: Sequence[Mapping[str, Any]]) -> str:
    """The exact qualified row and raw forward snapshot a fast-lane band decision used."""
    return hashlib.sha256(json.dumps({"row": dict(row), "forward": list(forward)},
                                    sort_keys=True, default=str).encode()).hexdigest()


def fast_lane_receipt(root: str | Path, receipt: Any, row: Mapping[str, Any], band: str,
                      forward: Sequence[Mapping[str, Any]]) -> bool:
    """A sizing proposal for this exact snapshot; a missing, copied or stale receipt confers no authority."""
    if isinstance(receipt, bool) or not isinstance(receipt, int) or receipt <= 0:
        return False
    try:
        db = sqlite3.connect(f"file:{Path(root) / 'observe.sqlite'}?mode=ro", uri=True, timeout=1.0)
        try:
            decision = db.execute("SELECT family, version, run_sha, inputs, stats, verdict, binding "
                                  "FROM ladder_decisions WHERE id=?", (receipt,)).fetchone()
        finally:
            db.close()
        if decision is None:
            return False
        figures = json.loads(decision[4])
        return bool(isinstance(figures, Mapping) and decision[6] == 1 and decision[5] == FAST_LANE_PROPOSED
                    and decision[0] == row.get("family") and decision[1] == row.get("version")
                    and decision[2] == row.get("run_sha") and decision[3] == fast_lane_inputs(row, forward)
                    and figures.get("authority") == FAST_LANE_AUTHORITY
                    and figures.get("from") == row.get("band") and figures.get("to") == band)
    except (OSError, sqlite3.Error, ValueError, TypeError):
        return False


class Ladder:
    """The forward ladder's session end (the module docstring). `live` is the House's `OptionsLive`."""

    def __init__(self, live: Any, *, bridge: Any = None):
        self.live = live
        self.bridge = bridge if bridge is not None else default_bridge(live)

    def fast_lane_band(self, row: Mapping[str, Any], equity: Any, forward: Sequence[Mapping[str, Any]],
                       fwd: Any, *, probe_sessions: int, embargo: str | None) -> tuple[str, str, int | None]:
        """Size or demote an already qualified Probe/Sized; never qualify a program or read unseen data.

        The money table's risk gates and real-fill requirements remain in force. Practice checkpoints record
        alongside this route: they impose no wait on the first Probe. A changed band has an immutable decision
        receipt BEFORE the swarm's atomic confirmation; the receipt proposes a move, not proof it was applied.
        """
        from . import money as M

        band, table = str(row["band"]), self.live.table
        if band not in ("probe", "sized"):
            raise ValueError("fast-lane sizing only judges a qualified Probe or Sized")
        risk, risk_why = M.band_for(table, row, equity, fwd, probe_sessions=0)
        if risk == "candidate":
            new, why = risk, risk_why
        elif fwd.real_bad:
            new, why = "probe", risk_why
        elif M.sized_ok(table, fwd) and (band == "sized" or (
                fwd.real_n >= table.min_probe_real_trades and probe_sessions >= table.min_probe_sessions)):
            if embargo:
                new, why = "probe", embargo
            else:
                new = "sized"
                why = (f"{fwd.real_n} real trades, mean {fwd.real_mean:.4f} a dollar of maximum loss, "
                       f"{table.sized_confidence:.0%} lower bound {fwd.real_lcb:.4f}" +
                       (f", after {probe_sessions} whole sessions at Probe" if band == "probe" else ""))
        else:
            new, why = "probe", "the real forward record does not yet meet Sized: held at Probe"
        if new == band:
            return new, why, None
        receipt = self.live.observe_store.add_decision({
            "day": dt.datetime.fromtimestamp(self.live.clock(), NEW_YORK).date().isoformat(),
            "family": row["family"], "version": row["version"], "run_sha": row["run_sha"],
            "inputs": fast_lane_inputs(row, forward),
            "stats": {"authority": FAST_LANE_AUTHORITY, "from": band, "to": new,
                      "forward": asdict(fwd), "probe_sessions": probe_sessions,
                      "version_created_at": row.get("version_created_at"),
                      "version_selected_at": row.get("version_selected_at"), "embargo": embargo,
                      "equity": str(equity), "money_table": asdict(table)},
            "verdict": FAST_LANE_PROPOSED, "reasons": [why], "binding": True})
        return new, why, receipt

    def _bundle(self) -> str | None:
        try:
            from .observe import evaluator_bundle

            return evaluator_bundle()
        except Exception:  # noqa: BLE001 - no bundle: no pre-filter read can be matched (fail-closed)
            return None

    def _alert(self, text: str) -> None:
        alert = getattr(self.live, "alert", None)
        if callable(alert):
            alert("warning", text)

    def end_of_day(self, day: str) -> dict[str, Any]:
        """THE SESSION END through the session day `day` (the module docstring): every pending promotion is first set
        against the swarm's store (`_settle_pending`), then every active ladder cohort under the running evaluator
        (`_reconcile`); one with a checkpoint due is judged at it (`_decide`); one whose latch waits has its answer
        read (`_answer`); then the requests' sweep, then the demotions. Each receipt, each cohort, the sweep and each
        demotion apart. {day, binding, settled (the pending promotions: {promoted, void}), judged (the checkpoints
        judged, an error among them), verdicts (by the receipts written, and "error"), ended (the cohorts
        `_settle_pending` and `_reconcile` ended), practising (no checkpoint due), deferred (a checkpoint left due: its
        record is not whole yet), waiting (a latch read with no answer yet), recorded (answered, practising on to its
        window), entrants, bh_size, swept, demoted}."""
        rules = Rules.from_constitution()
        store = self.live.observe_store
        evaluator = store.evaluator
        out: dict[str, Any] = {"day": day, "binding": rules.binding, "judged": 0, "verdicts": {}, "ended": {},
                               "practising": 0, "deferred": 0, "waiting": 0, "recorded": 0}
        # The programs whose own practice account still holds closes the record could not take at the close.
        unexported = getattr(self.live, "practice_unexported", None)
        unexported = {(str(f), int(n)) for f, n in unexported()} if callable(unexported) else set()

        def count(key: str, verdict: str) -> None:
            out[key][verdict] = out[key].get(verdict, 0) + 1

        settled = self._settle_pending(day)
        for _ in range(settled.pop("cohorts")):
            count("ended", "promoted")
        out["settled"] = settled
        due, latched = [], []
        for cohort in store.ladder_cohorts():
            snap = cohort["snapshot"]
            if snap.get("practice_evaluator") != evaluator:
                continue  # completed at the next session's pins ("evaluator changed")
            try:
                ended = self._reconcile(cohort, day=day)
                if ended:
                    count("ended", ended)
                    continue
                latch = cohort["state"]["latch"]
                if latch is not None:   # its checkpoint's verdict is final: never judged again
                    if latch.get("waits") in LATCH_WAITS:
                        latched.append(cohort)
                    else:
                        out["recorded"] += 1
                    continue
                practice, rows = store.ladder_rows(cohort["family"], cohort["version"], evaluator=evaluator,
                                                   first_day=cohort["first_day"], through=day)
                sessions, calendar = practised(cohort, practice, day)
                point = checkpoint_due(sessions, len(calendar), cohort["state"]["judged"], rules)
                if point is None:
                    out["practising"] += 1
                    continue
                if (cohort["family"], int(cohort["version"])) in unexported:
                    # A checkpoint is judged once, on the record through its session: never on one known to lack closes.
                    out["deferred"] += 1
                    self._alert(f"live: the forward ladder left {cohort['family']}@{cohort['version']}'s {point}-session "
                                "checkpoint due: closes of its practice account are not in the record yet; judged at "
                                "the next session's end")
                    continue
                figures = judge(cohort, practice, rows, through=day, rules=rules, checkpoint=point)
            except Exception as exc:  # noqa: BLE001 - one cohort's error stops no other's judgement
                out["judged"] += 1
                count("verdicts", "error")
                self._alert(f"live: the forward ladder could not read {cohort['family']}@{cohort['version']}'s record "
                            f"({type(exc).__name__}: {str(exc)[:160]}); judged again at the next session's end")
                continue
            due.append((cohort, figures))
        since = (dt.date.fromisoformat(day) - dt.timedelta(days=rules.fdr_days)).isoformat()
        entrants: dict[Any, float] = {int(e["id"]): (1.0 if e["p_checkpoint"] is None or e["p_value"] is None
                                                     else float(e["p_value"])) for e in store.entrants(since=since)}
        for cohort, figures in due:  # tonight's checkpoint is its latest; a judged cohort is always in its own family
            own = cohort.get("entrant")
            entrants[own if own is not None else (cohort["family"], int(cohort["version"]))] = figures["p"]
        cut, m = benjamini_hochberg(entrants.values(), rules.fdr_q)
        ordered = sorted(entrants.values())
        for cohort, figures in due:
            try:
                verdict = self._decide(cohort, figures, day=day, rules=rules, cut=cut, m=m,
                                       rank=bisect.bisect_left(ordered, figures["p"]) + 1)
            except Exception as exc:  # noqa: BLE001 - one cohort's error promotes nothing and stops no other's judgement
                verdict = "error"
                self._alert(f"live: the forward ladder could not judge {cohort['family']}@{cohort['version']} "
                            f"({type(exc).__name__}: {str(exc)[:160]}); judged again at the next session's end")
            out["judged"] += 1
            count("verdicts", verdict)
        for cohort in latched:
            try:
                verdict = self._answer(cohort, day=day, rules=rules)
            except Exception as exc:  # noqa: BLE001 - one cohort's error promotes nothing and stops no other's answer
                verdict = "error"
                self._alert(f"live: the forward ladder could not read {cohort['family']}@{cohort['version']}'s answer "
                            f"({type(exc).__name__}: {str(exc)[:160]}); read again at the next session's end")
            if verdict is None:
                out["waiting"] += 1
            else:
                count("verdicts", verdict)
        out["entrants"], out["bh_size"] = len(entrants), m
        if self.bridge is not None:
            try:
                out["swept"] = self.bridge.sweep_prefilter(
                    str(c["snapshot"].get("run_sha")) for c in store.ladder_cohorts()
                    if c["snapshot"].get("practice_evaluator") == evaluator and c["snapshot"].get("run_sha")
                    and (c["state"]["latch"] or {}).get("waits") == "prefilter")
            except Exception as exc:  # noqa: BLE001 - swept again at the next session's end
                self._alert(f"live: the forward ladder could not sweep the pre-filter requests ({type(exc).__name__})")
        try:
            out["demoted"] = self.demotions(day, rules)
        except Exception as exc:  # noqa: BLE001 - read again at the next session's end
            out["demoted"] = []
            self._alert(f"live: the forward ladder could not read the families it banded for demotion "
                        f"({type(exc).__name__}: {str(exc)[:160]}); read again at the next session's end")
        return out

    def _record_band(self, family: str, version: int, receipt: int) -> None:
        """The House's ledger record of a promotion; never failing the session's end (the swarm's own band event names
        the receipt)."""
        try:
            self.live.record("live.band", {"family": family, "from": "gym", "to": "probe", "version": version,
                                           "receipt": receipt, "why": "the forward ladder promoted it"}, agent=family)
        except Exception as exc:  # noqa: BLE001
            self._alert(f"live: {family}'s ladder promotion could not be recorded in the ledger ({type(exc).__name__})")

    def _made_good(self, family: str, version: int, receipt: int, *, day: str, pending: bool) -> bool:
        """A promotion whose band the swarm's store holds, made good in the House's own record at a later session's end:
        its receipt settled `promote` (when it was `pending`), its cohort ended `promoted` when it is still active, and
        its move recorded (once: when the receipt is settled here, or its cohort moved). True when its cohort moved."""
        why = f"ladder: promoted to Probe (receipt {receipt}; recorded at a later session's end)"
        reasons = ["every line met and the pre-filter passed: promoted to Probe (settled at a later session's end)"]
        moved = self.live.observe_store.settle_answer(
            receipt, "promote", reasons if pending else None, day=day, close="promoted", reason=why,
            was=(PROMOTE_PENDING,) if pending else ("promote",))
        if moved or pending:
            self._record_band(family, version, receipt)
        return moved

    def _settle_pending(self, day: str) -> dict[str, int]:
        """NO RECEIPT STAYS PENDING (the module docstring): every `promote_pending` receipt, whatever its cohort's
        evaluator or status, set against the swarm's store before anything else is done. {promoted (settled `promote`:
        its family holds the band the ladder gave that very program by that receipt), void (the store shows no band of
        it), cohorts (those that ended `promoted` with their receipt)}. One whose store cannot be read stays pending,
        alerted, for the next session's end; so do all of them without a swarm store to ask."""
        out = {"promoted": 0, "void": 0, "cohorts": 0}
        if self.bridge is None:
            return out
        store = self.live.observe_store
        for row in store.pending_promotions():
            f, n, receipt = str(row["family"]), int(row["version"]), int(row["id"])
            try:
                if banded_receipt(self.bridge.family_status(f), n, str(row["run_sha"] or "")) == receipt:
                    out["cohorts"] += int(self._made_good(f, n, receipt, day=day, pending=True))
                    out["promoted"] += 1
                elif store.set_verdict(receipt, PROMOTE_VOID, ["the swarm's store holds no band of it"],
                                       was=(PROMOTE_PENDING,)):
                    out["void"] += 1
            except Exception as exc:  # noqa: BLE001 - one receipt's error stops no other's, nor the session's end
                self._alert(f"live: the forward ladder could not settle {f}@{n}'s pending promotion (receipt {receipt}: "
                            f"{type(exc).__name__}: {str(exc)[:160]}); read again at the next session's end")
        return out

    def _reconcile(self, cohort: Mapping[str, Any], *, day: str) -> str | None:
        """What the swarm's store already says of an active cohort, before anything else is done with it (the module
        docstring): its family retired (or gone), it ends `failed` ("family_retired"); its family already holds the
        band the ladder gave this very program by a pending or `promote` receipt of this file (one `_settle_pending`
        could not settle), the receipt is settled, the cohort ends `promoted` and its move is recorded ("promoted").
        None: neither."""
        if self.bridge is None:
            return None
        store = self.live.observe_store
        snap = cohort["snapshot"]
        f, n, sha = cohort["family"], int(cohort["version"]), str(snap.get("run_sha") or "")
        status = self.bridge.family_status(f)
        if status is None or status["retired"]:
            why = "its family retired" if status is not None else "its family is not in the swarm's store"
            store.close_cohort(f, n, status="failed", day=day, reason=f"ladder: {why}")
            return "family_retired"
        receipt = banded_receipt(status, n, sha)
        if receipt is not None:
            row = store.decision(receipt)
            if (row is not None and row["verdict"] in ("promote", PROMOTE_PENDING) and row["family"] == f
                    and int(row["version"]) == n and row["run_sha"] == sha):
                self._made_good(f, n, receipt, day=day, pending=row["verdict"] == PROMOTE_PENDING)
                return "promoted"
        return None

    def _decide(self, cohort: Mapping[str, Any], figures: Mapping[str, Any], *, day: str, rules: Rules,
                cut: float | None, m: int, rank: int) -> str:
        """A CHECKPOINT's verdict on its figures and the night's Benjamini-Hochberg cut (the module docstring), its one
        receipt written: the verdict. A cohort that meets L1-L5 is latched (L0 not met, or a snapshot with no run sha,
        ends it instead)."""
        snap = cohort["snapshot"]
        f, n, sha = cohort["family"], int(cohort["version"]), str(snap.get("run_sha") or "")
        lines = figures["lines"]
        bh = figures["full"] and cut is not None and figures["p"] <= cut

        def receipt(verdict: str, reasons: list[str], *, latch: str | None = None, close: str | None = None,
                    reason: str = "") -> str:
            self.live.observe_store.add_decision({
                "day": day, "family": f, "version": n, "run_sha": snap.get("run_sha"), "inputs": figures["inputs"],
                "stats": {k: figures[k] for k in RECEIPT_STATS}, "p_value": figures["p"], "bh_rank": rank, "bh_size": m,
                "bh_threshold": cut, "verdict": verdict, "reasons": reasons, "binding": rules.binding,
                "checkpoint": figures["checkpoint"], "latch": latch}, close=close, reason=reason)
            return verdict

        if not figures["eligible"]:
            return receipt("ineligible", ["its practice record began before its cohort"])
        if not lines["record"]:
            return receipt("short", [f"{figures['sessions']} sessions and {figures['closes']} program closes; the line is "
                                     f"{rules.min_sessions} and {rules.min_closes}"])
        failed = [name for name, ok in (("bound", lines["bound"]), ("windows", lines["windows"]), ("drift", lines["drift"]),
                                        ("fdr", bh)) if not ok]
        if failed:
            return receipt("fail", [f"the {name} line" for name in failed])
        if not sha:  # it met the lines, so this verdict is final too: no answer can ever be asked for
            return receipt("blocked", ["its snapshot names no run sha"], close="failed",
                           reason="ladder: its snapshot names no run sha")
        validated = self.bridge.validation(f, n) if self.bridge is not None else None
        if validated is False:
            return receipt("validation_failed", ["its version's latest validation on the Gym in force did not meet the "
                                                 "Validation line"],
                           close="failed", reason="ladder: its version did not meet the Validation line")
        if validated is not True:
            return receipt("await_validation", ["no swarm store to ask" if self.bridge is None else
                                                "its version has no validation on the Gym in force yet"],
                           latch="validation")
        bundle = self._bundle()
        if bundle is not None:
            self.bridge.request_prefilter(sha, family=f, version=n, bundle=bundle, day=day)
        return receipt("await_prefilter", ["the pre-filter read is requested from the gate" if bundle is not None else
                                           "no Gym bundle to ask the gate's pre-filter read on"], latch="prefilter")

    def _answer(self, cohort: Mapping[str, Any], *, day: str, rules: Rules) -> str | None:
        """THE ANSWER SESSION of a cohort whose latch waits (the module docstring): the verdict of the receipt its
        answer wrote ("promoted" for a promotion), or None while the latch still waits (nothing written; the
        checkpoint's own session included). No line is judged and no record is read."""
        store = self.live.observe_store
        snap, latch = cohort["snapshot"], cohort["state"]["latch"]
        f, n, sha = cohort["family"], int(cohort["version"]), str(snap.get("run_sha") or "")
        waited = max(0, len(sessions_between(str(latch["day"]), day)) - 1)  # the sessions after its checkpoint's
        if waited < 1:
            return None
        base = store.decision(int(latch["receipt"]))
        if base is None:
            raise ValueError("its checkpoint's receipt cannot be read")
        limit = rules.answer_sessions

        def row(verdict: str, reasons: list[str], **read: Any) -> dict[str, Any]:
            stats = {**base["stats"], "latch": {k: latch.get(k) for k in ("checkpoint", "day", "receipt")},
                     "answer": {"waited": waited, **read}}
            return {"day": day, "family": f, "version": n, "run_sha": base["run_sha"], "inputs": base["inputs"],
                    "stats": stats, "p_value": base["p_value"], "bh_rank": base["bh_rank"], "bh_size": base["bh_size"],
                    "bh_threshold": base["bh_threshold"], "verdict": verdict, "reasons": reasons, "binding": rules.binding}

        def unanswered(why: str) -> str:
            store.add_answer(row("unanswered", [why]), close="complete", reason=f"ladder: {why}")
            return "unanswered"

        def waiting(what: str) -> None:
            if waited > 1 and store.latch_told(f, n, day=day):
                self._alert(f"live: {f}@{n} met the forward ladder's lines at its {latch.get('checkpoint')}-session "
                            f"checkpoint and has waited {waited} sessions for {what}; without it, it ends unpromoted "
                            f"after {limit}")

        if waited > limit:
            return unanswered(f"no session's end read its answer within {limit} sessions of its checkpoint")
        if latch["waits"] == "validation":
            validated = self.bridge.validation(f, n) if self.bridge is not None else None
            if validated is False:
                store.add_answer(row("validation_failed", ["its version's latest validation on the Gym in force did not "
                                                           "meet the Validation line"]),
                                 close="failed", reason="ladder: its version did not meet the Validation line")
                return "validation_failed"
            if validated is not True:
                if waited >= limit:
                    return unanswered(f"no Validation verdict within {limit} sessions of its checkpoint")
                waiting("its Validation verdict")
                return None
            store.move_latch(f, n, waits="prefilter")
        bundle = self._bundle()
        record = self.bridge.prefilter(sha)
        read = prefilter_answer(record, bundle=bundle, level=rules.prefilter_p)
        if read is None:
            if isinstance(record, Mapping) and record.get("status") == "failed" and bundle is not None \
                    and record.get("bundle") == bundle:
                return unanswered("the gate could not make its pre-filter read")
            if waited >= limit:
                return unanswered(f"no pre-filter answer within {limit} sessions of its checkpoint")
            if bundle is not None:
                self.bridge.request_prefilter(sha, family=f, version=n, bundle=bundle, day=day)
            waiting("the pre-filter's answer")
            return None
        if not read["passed"]:
            store.add_answer(row("prefilter_negative", ["the 2026 holdout read (the pre-filter) did not pass its line"],
                                 prefilter=read),
                             close="failed", reason="ladder: the pre-filter read did not pass its line")
            return "prefilter_negative"
        from ..swarm.bands import BELT_UNREAD

        if not rules.binding:
            try:
                why = self.bridge.refusal(f, n, sha)
            except Exception:  # noqa: BLE001 - a reading only: it refuses nothing
                why = BELT_UNREAD[0]
            belt = {"read": why not in BELT_UNREAD, "refusal": None if why in BELT_UNREAD else why}
            store.add_answer(row("would_promote", ["every line met and the pre-filter passed; the ladder does not bind "
                                                   "(options_money.ladder.binding)"], prefilter=read, belt=belt))
            return "would_promote"
        why = self.bridge.refusal(f, n, sha)
        if why in BELT_UNREAD:  # a failed read is no refusal: nothing is promoted on it and no cohort fails for it
            raise RuntimeError(f"the ladder's belt: {why}")
        if why:
            store.add_answer(row("blocked", [f"the ladder's belt: {why}"], prefilter=read), close="failed",
                             reason=f"ladder: {why}")
            return "blocked"
        # THE RECEIPT NEVER STANDS WITHOUT ITS BAND (the module docstring): pending, the band, then settled.
        receipt = store.add_decision(row(PROMOTE_PENDING, ["every line met and the pre-filter passed: its band move is "
                                                           "pending"], prefilter=read))
        try:
            why = self.bridge.promote(family=f, version=n, snapshot=snap, receipt=receipt,
                                      typical=base["stats"].get("typical"), at=float(self.live.clock()))
        except Exception:
            landed = self._landed(f, n, sha, receipt)
            if landed is not True:
                if landed is False:
                    store.set_verdict(receipt, PROMOTE_VOID, ["its band move raised and the swarm's store holds no band of "
                                                              "it"], was=(PROMOTE_PENDING,))
                raise
            why = None
        if why:
            store.settle_answer(receipt, "blocked", [why], day=day, close="failed", reason=f"ladder: {why}")
            return "blocked"
        # The swarm's band is written: the receipt and the House's own records are settled in one transaction, made
        # good at a later session's end when that fails (`_reconcile`).
        if store.settle_answer(receipt, "promote", ["every line met and the pre-filter passed: promoted to Probe"],
                               day=day, close="promoted", reason=f"ladder: promoted to Probe (receipt {receipt})"):
            self._record_band(f, n, receipt)
        return "promoted"

    def _landed(self, family: str, version: int, run_sha: str, receipt: int) -> bool | None:
        """Whether the swarm's store holds the band the ladder gave this very program by `receipt`; None when it cannot
        be read."""
        try:
            return banded_receipt(self.bridge.family_status(family), version, run_sha) == receipt
        except Exception:  # noqa: BLE001 - not known: the receipt stays pending
            return None

    def demotions(self, day: str, rules: Rules) -> list[dict[str, Any]]:
        """DEMOTION (the module docstring) of the families the ladder banded, each apart: [{family, why, receipt}]."""
        if self.bridge is None:
            return []
        out = []
        for fam in self.bridge.ladder_families():
            try:
                moved = self._demote(fam, day, rules)
            except Exception as exc:  # noqa: BLE001 - one family's error stops no other's demotion
                self._alert(f"live: the forward ladder could not judge {fam.get('family')}'s demotion "
                            f"({type(exc).__name__}: {str(exc)[:160]}); judged again at the next session's end")
                continue
            if moved is not None:
                out.append(moved)
        return out

    def _demote(self, fam: Mapping[str, Any], day: str, rules: Rules) -> dict[str, Any] | None:
        """One family's DEMOTION: {family, why, receipt} when it went back to the Gym, else None."""
        from . import money as M

        version = fam.get("version")
        since = None
        if fam.get("promoted_at") is not None:
            since = dt.datetime.fromtimestamp(float(fam["promoted_at"]), NEW_YORK).date().isoformat()
        rows = [r for r in self.bridge.forward_rows(fam["family"]) if since is None or str(r.get("day") or "") > since]
        fwd = M.forward_stats(rows, rules.demote_confidence, version=version)
        days, lcb = M.session_bound(rows, sessions=rules.demote_sessions, confidence=rules.demote_confidence,
                                    version=version)
        if fwd.negative:
            why = f"its forward record is negative over {fwd.n} trades"
        elif lcb is not None and lcb < 0:
            why = f"the lower bound of its trailing {days} sessions is below zero"
        else:
            return None
        receipt = self.live.observe_store.add_decision({
            "day": day, "family": fam["family"], "version": int(version or 0), "run_sha": None,
            "inputs": hashlib.sha256(json.dumps(rows, sort_keys=True, default=str).encode()).hexdigest(),
            "stats": {"trades": fwd.n, "mean": fwd.mean, "session_days": days, "session_lcb": lcb, "band": fam["band"]},
            "p_value": None, "verdict": "demote", "reasons": [why], "binding": rules.binding})
        if not self.bridge.demote(fam["family"], why=why, receipt=receipt, at=float(self.live.clock())):
            return None
        self.live.observe_store.close_cohort(fam["family"], int(version or 0), status="demoted", day=day,
                                             reason=f"ladder: {why}", was=("promoted",))
        self.live.record("live.band", {"family": fam["family"], "from": fam["band"], "to": "gym", "version": version,
                                       "receipt": receipt, "why": f"the forward ladder demoted it: {why}"},
                         agent=fam["family"])
        return {"family": fam["family"], "why": why, "receipt": receipt}


def end_of_day(live: Any, day: str) -> dict[str, Any]:
    """`OptionsLive._end_of_day`'s hook: the House's ladder (made once, `live.ladder`), judged through `day`."""
    ladder = getattr(live, "ladder", None)
    if ladder is None:
        ladder = Ladder(live)
        live.ladder = ladder
    return ladder.end_of_day(day)


# ------------------------------------------------------------------------------------------------- the scoreboard
def counts(root: str | Path, *, day: str | None = None) -> dict[str, Any] | None:
    """The ladder's PUBLIC-SAFE counts (the daily scoreboard's, `league/ops/scoreboard.py`): {binding (the table's),
    entrants (the trailing `fdr_days` window's, one a cohort: the BH family size), in_practice (the ladder's active
    cohorts), would_promote (the programs with such a receipt, written once at its answer, in that window),
    promoted (the `promote` receipts: every promotion the ladder made, a later demotion included; a pending or void
    receipt is none, as the live path and the budget rule read them), demoted and failed (the ladder's cohorts that
    ended so)}: counts only, never a figure, a family or a program. The window ends on `day` (default: the last day a
    receipt was written). Read-only (`mode=ro`), never raising: None when the record cannot be read; zeros without
    one."""
    try:
        rules = Rules.from_constitution()
        path = Path(root) / "observe.sqlite"
        out = {"binding": rules.binding, "entrants": 0, "in_practice": 0, "promoted": 0, "demoted": 0, "failed": 0,
               "would_promote": 0}
        if not path.exists():
            return out
        db = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=1.0)
        try:
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if "entrants" not in tables:
                return out
            last = day or (db.execute("SELECT MAX(day) FROM ladder_decisions").fetchone()[0] or
                           dt.date.today().isoformat())
            since = (dt.date.fromisoformat(str(last)) - dt.timedelta(days=rules.fdr_days)).isoformat()
            out["entrants"] = int(db.execute("SELECT COUNT(*) FROM entrants WHERE entered_day>=?", (since,)).fetchone()[0])
            for status, key in (("active", "in_practice"), ("demoted", "demoted"), ("failed", "failed")):
                out[key] = int(db.execute("SELECT COUNT(*) FROM cohorts c JOIN entrants e ON e.id=c.entrant "
                                          "WHERE c.status=?", (status,)).fetchone()[0])
            out["promoted"] = int(db.execute("SELECT COUNT(*) FROM ladder_decisions WHERE verdict='promote'").fetchone()[0])
            out["would_promote"] = int(db.execute("SELECT COUNT(DISTINCT family || '@' || version) FROM ladder_decisions "
                                                  "WHERE day>=? AND day<=? AND verdict='would_promote'",
                                                  (since, str(last))).fetchone()[0])
            return out
        finally:
            db.close()
    except Exception:  # noqa: BLE001 - the scoreboard says "n/a"
        return None


__all__ = ["Rules", "Close", "Ladder", "SwarmBridge", "LADDER_VERSION", "PREFILTER_REQUESTS", "PREFILTER_KEY", "VERDICTS",
           "FAST_LANE_AUTHORITY", "FAST_LANE_PROPOSED", "fast_lane_inputs", "fast_lane_receipt",
           "PROMOTE_PENDING", "PROMOTE_VOID", "RECEIPT_STATS", "TILT_DAYS", "TILT_MEAN", "TILT_NO_LOSS", "TILT_WEIGHTS",
           "TILT_RECORD", "TILT_UNKNOWN", "day_sums", "tilted", "tilted_p", "percentile", "percentile_p",
           "percentile_line", "bootstrap", "checkpoint_due", "practised", "windows", "drift_line", "benjamini_hochberg",
           "inputs_hash", "judge", "judge_daily", "prefilter_answer", "banded_receipt", "close_of", "entry_delta",
           "drift_usd", "exit_spot", "sessions_between", "end_of_day", "counts", "default_bridge"]
