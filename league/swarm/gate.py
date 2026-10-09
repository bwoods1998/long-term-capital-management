"""The gate and the nightly forward replays: the only code that opens sealed days, on gate boxes only.

THE GATE (when a family's validated best meets the validation line):
1. RATIONS: one holdout look per program version (code + parameters), at most three per LINEAGE (a fork
   inherits its parent's looks); the leakage alarm (>= 10 looks, > 30% passing; per lane since release D-1) stops the
   gate. THE DUPLICATE LOOK (H3a, Oct 1, 2026; `duplicate_look`) comes first: a look that would repeat an earlier one is
   refused. THE DRIFT SCREEN (Sept 27, `evidence.drift_screen`) again, in depth: a version whose Train drift-adjusted
   alpha fails it is refused (stage "drift screen": no review is paid, no look is spent); one whose figures are owed
   waits. THE LOOK HOLDS (L6, Oct 2, 2026; `look_hold`) come after the rations and before the review: a look the
   holdout cannot judge is held.
2. THE REVIEW: GPT-6 Sol through the gateway when OpenAI has room (`review_openai_model`; null skips it), else
   DeepSeek-V4-Pro balanced on Sail (Claude first once "review" is in `claude.roles`, Sept 29), reads the program for
   lookahead, leakage (calendar recognition, hard-coded regimes) and fill abuse. A failed review is a recorded refusal
   and costs no look. An unclear answer is asked again next round. THE AUDIT then reads it again on a second model:
   Claude (a default role), else GPT-6 Astra while the OpenAI month has room (`audit_openai_model`; null skips it), else
   a different Sail model; a failed audit is a refusal too.
3. ONE HOLDOUT LOOK on a gate box (a fork of the gate image; the Gym image has no holdout days), judged by
   the holdout line (`evidence.holdout_line`: since FAST LANE V2, Oct 7, 2026, at the flat one-sided level
   `evidence.LOOK_LEVEL` (0.10) per program, with no Holm escalation across looks). The researcher is told PASS or
   FAIL, never a number.
4. A pass makes the family a Candidate (live shadow). Candidate <-> Probe <-> Sized is the LIVE PATH's
   (the Money table), written through `SwarmStore.set_band`; the swarm never makes a Probe or a Sized.

THE DUPLICATE LOOK (H3a, Oct 1, 2026; the edge study's "a duplicate adds no signal"). Every look then raised the Holm
bar of every later one (since fast lane v2 a look is flat, and a program is still counted once), and the three looks
since the Sept 26 reset covered two programs: the two Sept 27 looks had identical
Train and Validation results under different run shas. So before anything else is asked of a version (the experiment
contract, the drift screen, the rations, a paid review, a sealed read), `duplicate_look` compares it with every look the
swarm has made, in any family and lineage. It repeats one when (1) it is the same program (`run_sha`: code and
parameters), or (2) its Validation run says the same as a Validation run of the looked version (`validation_identity`:
the Gym's own run sha, the code with its PARAMS merged over the defaults, so an override restating a default is no new
program; or the same evaluation, the engine, its code, tables, fill model, roots, window, stress and capital, with the
same outcome: summary, fills, breakdowns and the 1.5x twin). It reads the looks table, the families' in-flight markers
and stored Validation results, never a holdout file. A repeat is refused as every gate refusal is (`refuse`, stage
"duplicate look": the refusal row, the program's incubator bar, `gated_sha` with `gate_ready` cleared, so the tournament
never makes the version gate-ready again, and the outcome "refused"), plus one private `swarm.gate` event
(`duplicate_look`) naming the earlier look; no look row, no try, no review. The researcher hears the earlier look's
number and why, never a figure or that look's verdict (D2a). A version whose look of its own already landed is only
closed (`gated_sha`), and one that repeats a look still in flight in another family waits for it. A genuinely new
version compares with nothing and goes on as before. Tightening only: no threshold, no Holm or deflated-Sharpe rule,
no forward rule moves.

A PAID VERDICT BINDS (fast lane v2's review, Oct 7, 2026; `paid_verdict`). An evaluator adoption (a release that moves
the Gym's image or the execution fingerprint, `evaluator.adopt`) clears the gate's `review` and `gated_sha`, so a version
the gate refused at its review or audit, never looked at, would be validated again, reviewed again (the audit's request
id is new each time) and could pass on a second roll. Right after THE DUPLICATE LOOK, a version whose PROGRAM (`run_sha`:
in this family or any family holding the same code and parameters, `incubator.twins`) has a kept refusal at the stage
"review" or "audit", or a kept bar (`incubator_barred`) recording that the GATE's own review or audit failed it, is
closed as a version whose look already landed is (`gated_sha`, `gate_ready`
cleared), its outcome "refused", the researcher told so, and one private `swarm.gate` event (`paid_verdict`) names the
earlier verdict: no new review, no look. A refusal at a FREE stage (the experiment contract, the drift screen, the
rations, a duplicate look, a look hold) does not bind here: those are judged again by their own rules, which this
release changed (the drift screen and the holds are off). Nor do the incubator's own reads (its failed review or audit
bars the incubator route only, as before: the gate asks its own questions), nor a record that merely could not be read
(no verdict was given). Tightening only.

THE LOOK HOLDS (L6(b) and L6(c) of the edge study, approved by the owner on Oct 2, 2026 as a tightening; `look_hold`,
`evidence.drift_lean`, `evidence.holdout_power`). OFF SINCE FAST LANE V2 (Oct 7, 2026; the owner's goal item 4: direction
counts, and a look is flat at `evidence.LOOK_LEVEL`, so a look no longer raises any later one's bar): policy.json sets
`gate.look_holds` null, and `look_hold` returns None. As they stood, when switched on: after the experiment contract, the drift screen and
the rations (each of which REFUSES, and a refusal bars the program from the incubator: a hold never takes a refusal's
place) and before anything is paid (the review, the audit) or opened (the sealed read), the gate HOLDS the look at:
- (b) THE DRIFT HOLD (stage "look hold (drift)"): a long-delta version (pooled Train beta above zero) whose Train drift
  share, |drift_usd| / (|alpha_usd| + |drift_usd|) of its own drift fit over the years the drift screen counts
  (`researcher.version_drift`, `evidence.drift_lean`), is at least `gate.look_holds.drift_share` (0.25). A version with
  no drift fit is held too (fail-closed), and so is a long-delta one whose alpha and drift are both zero.
- (c) THE POWER HOLD (stage "look hold (power)"): a version whose expected holdout power is below
  `gate.look_holds.min_power` (0.30): the one-sided power of the holdout line's test of mean daily P&L above zero (a
  day-block bootstrap, taken in the normal approximation: P(Z >= z(level) - S sqrt(N))), with S the version's Validation
  all-days daily Sharpe (`validation_numbers.sharpe_daily`, the figure the look's Sharpe check uses), N the holdout
  window's NYSE sessions (`holdout_sessions`) and the level the look must reach, the flat `evidence.LOOK_LEVEL` (the
  looks before and in flight elsewhere are counted in the figures, no longer in the level). Missing figures hold
  (fail-closed). The approximation leaves out the line's other checks (which can only lower the pass chance); for
  independent daily P&L the bootstrap passes a little more often than it says near the line, so the hold errs toward holding,
  and for positively autocorrelated daily P&L (multi-day marks) toward looking (`evidence.holdout_power`).
A held version is closed at the gate (`gated_sha`, `gate_ready` cleared, so the tournament never readies it again;
`gate_outcome` "held"), with one `look_holds` row (`SwarmStore.hold_look`: its own table, never a `refusals` row) and
one private `swarm.gate` event (`look_hold`, its figures under `_figures`); no look row, no try, no review, no audit, no
sealed read. ON THE MONEY PATH A HOLD IS A FAILED LOOK (the owner approved the holds as a TIGHTENING, so a held program
gets no real order that the look it replaces would have stopped): "held" is one of `bands.BAD_OUTCOMES`, so it ends the
version's execution tuition (`bands.read`) and refuses its program the incubator (`bands.program_refusal`), and the hold
is recorded as the program's incubator bar for good first (THE VERDICT FIRST, `_incubator_bar`, right after its hold row
and before anything else, as a refusal's is). That matters because a hold can land after the review: a version reviewed
and audited (a pass) that waits for the gate image or a holdout gap is held when a look landing elsewhere lowers its
power, or when the holds are switched on; without the bar its tuition would never end (no look is coming). The
researcher hears that the look is held and why, in words with no figure (D2a). A new version of the family is looked at
once it clears both. `look()` checks again under the store's lock (a look landing meanwhile can lower the power). Each
hold is switched off by its setting set to null (`look_holds` null: both); a misread value is its default.

MISSING DATA IS THE GATE IMAGE'S, NOT THE PROGRAM'S (Oct 1, 2026). Before a look the gate checks that its image holds a
holdout for every root the program needs (`holdout_gap`: the gate boxes' file-name listing and the Gym's own "missing
data" answers, kept per image by the pool, and the nightly ready file's `holdout_roots`; metadata only, never a quote).
A look whose roots the image lacks is refused up front: no look is marked, no try is counted, `gate_ready` stays, and
one `swarm.status` alert (`gate_missing_data`) is raised for the program on that image. A look that ran and failed for
missing data all the same (the box's own check, or the Gym's "no holdout days for ...") is owed again likewise: no try,
no "gym" refusal, no incubator bar. Any other failure counts a try; the third writes the "gym" refusal, and the alert
(`look_failed_three_times`) fires at every count from three on, so a fourth failure (the same program in a revived
family: its tries are kept by program) is never a silent park. Sept 30: three looks failed on a five-root holdout and
the third barred the program from the incubator for good, although no verdict was made.

THE NIGHTLY FORWARD: once a day (after `forward.after_hour_utc`), every Candidate, Probe and Sized family's
banded version runs over the forward days the gate image holds; the trades are the family's `nightly`
forward record (the live path adds `shadow` and `real` through `SwarmStore.add_forward`). Forward records
move bands and never select among Gym programs: a CANDIDATE whose forward record (nightly + shadow + real)
is negative over 20 trades goes back to the Gym; a Probe or Sized family's record is kept in its state
(`forward`, flagged `negative`) for the live path, which alone moves those bands.

THE OPERATOR'S HOLD (R3): a family whose state has `gate_hold` true (`SwarmStore.hold_gate`, or
`python -m league.swarm hold-gate --family <id>`) is skipped: no review, audit or holdout look starts, a stage between
two others stops, and its `gate_ready` is left as it is, so the gate looks at it once the hold is cleared. A look
already in flight is still judged when it lands. The round's answer lists it under `held`; the researcher's status,
the tournament's board and `python -m league.swarm status` say "held by the operator"; the public progress shows the
site's `gate_paused` (the site's closed list of blockers has no key of its own for it).

THE INCUBATOR'S REVIEW AND AUDIT (release B2, Sept 30, 2026; `incubator_reviews`, `league/swarm/incubator.py`): the owner
kept the gate's review and audit required for the House's incubator route (one lot, never evidence, never a promotion).
At the end of every round, also when nothing is gate_ready, the same reviewer and auditor (the same prompt, routes and
models) read at most `gate.incubator_reviews` (2) of the versions `incubator.due_reviews` names, those read least
recently first, and the verdicts go to the family's `incubator_reviews`. Their attempt counts, their model-call keys and
their Sail fuse (desk `<family>:incubator`, `review_usd_day` a day) are their own, so the gate's own review, its three
tries and its daily fuse are exactly as they were; only the paid routes' shared budgets (Claude's funded total and a
`claude.role_usd_day` line for the review or the audit, when the operator sets one; the OpenAI month) are common to
both: a read they leave no room for falls to the role's next route, as any read does. The incubator's reads run after
the round's own D2 work, so a D2 read waits at most for this round's (up to 2 x 2) incubator reads before the next
round. They never touch the gate's own review state or its looks, and never spend a look.
The leakage alarm stops them with the rest of the gate. THE VERDICT FIRST (`_incubator_bar`, `incubator.record_bar`): a
verdict against a program (the gate's failed review or audit, a third unclear answer, a refusal, a bad outcome; the
incubator's own failed review or audit) is recorded in the family's `incubator_barred[sha]` at once, before anything
else is written, and the program's incubator mark goes in the same transaction. So neither the gate's compare-and-set on
`validation_version` (a newer validation landing during the model read), nor an operator's hold, nor an error after the
read can lose it, whatever the family's `gate_outcome` or `review` says later. A bar an error kept from the store is
owed (`bars_owed`): recorded again when the gate's own write-back fails, and at the start and the end of every round
until it lands, and no incubator read of its program starts meanwhile; it is kept beside the store too
(`incubator.save_owed`), so a restart reads it back, the evaluator adoption at the start records it and the reader
refuses its program meanwhile. A bar is for good: an evaluator adoption keeps `incubator_barred`, and first records there
every failure that only what it clears holds (`incubator.adoption_bars`). A bar is on the PROGRAM (its `run_sha`): a
verdict made in one family bars the same code and params in every other (`incubator.program_bar`, and the reader's own
belt). THE INCUBATOR'S SWEEP (`incubator.sweep`) still runs at the start and the end of every round (the leakage
alarm's too), and again after an incubator read that failed, and records what it finds. Both only remove marks and
passes and record bars, which nothing of the gate reads.

THE DIRECTION LANE (release D-1, Oct 9, 2026; PLAN D6 and D7, the operator's decisions 6, 7 and 9; `league/swarm/dlane.py`).
A family's lane (`dlane.lane_of`: "alpha" for every family while `dlane.mode` is "off") picks its screen
(`dlane.screen_effective`, `look_line`): the alpha lane keeps "S-B" (the line above, at `evidence.LOOK_LEVEL` and half
of Validation's Sharpe) byte for byte; the direction lane's look is "S-C", the same line at p <= 0.20 and a Sharpe share
of 0.25; "D2" (a Validation pre-check, `Tournament._verdict`, then a pooled test) only behind `dlane.screen` "D2" with a
receipt sha256 and its `c` pinned in the repository's policy.json, else refused (S-C). While the lane is on every look
records its `lane`, `screen` and `receipt`, in its `detail` and its `swarm.gate` event. THE LEAKAGE ALARM counts each
lane's looks alone (`alarms`, `evidence.leakage_alarms`): the alpha lane's at 10 looks and more than 30% passed, the
direction lane's at 10 and more than 60%, and a lane's alarm stops that lane's looks and incubator reads only (the
whole gate stops when both hold). THE LANE'S MODE (`lane_closed`): while the direction lane is in "shadow" (its setting,
or K5 holding a "gate" lane in shadow, `dlane.candidates_open`) a direction family waits after the free checks (no
review is paid, no look is spent, `gate_ready` stays), a direction look already out lands judged but makes no Candidate
(`candidate_withheld`), and the incubator reads no direction family. While the lane is off (THE ROLLBACK) every path
here is the release before it's, byte for byte, but for one thing on a store that holds direction looks: the one
leakage alarm counts the looks the alpha lane's line judged, never a direction look judged on S-C (the review of Oct 9:
correlated direction passes would otherwise stop every alpha look).

Every step is a `swarm.gate` event; band moves are `swarm.band` events (the site's news).
Standard library only.
"""

from __future__ import annotations

import ast
import datetime as dt
import functools
import hashlib
import json
import secrets
import time
from pathlib import Path
from typing import Any, Callable, Mapping

from ..gym.experiment import check_experiment
from ..gym.review_contract import grounded_answer, review_contract
from ..gym.safety import CodeRefused
from . import dlane, evidence
from . import settings as settings_mod
from .pool import GymJob, PoolError
from .researcher import drift_verdict, needs_roots, running_span, version_drift
from .store import SwarmStore, dumps, structure_text


@functools.lru_cache(maxsize=1)
def gate_contract() -> dict[str, Any]:
    """THE GATE'S CONTRACT (Oct 8, 2026): `review_contract()` plus the context's COMPUTED fields. The Gym's contract
    lists each context class's `__slots__` only, so the readers were told ChainView has no `iv`, `delta`, `gamma`,
    `theta` or `vega` ("only the supplied context fields exist"), and judged a program that reads them a contract
    defect (an unclear review or audit, refused after three). Those are public properties computed on first read
    from the chain's own quotes (league/gym/ctx.py), as real as the slots. This adds every public property of `Ctx`,
    `UnderlyingView` and `ChainView` to `context_fields`, with one fact saying so, and hashes the result: its sha is
    the contract every review, audit and band compares. Built here, not in league/gym, so the evaluator's execution
    fingerprint (every league/gym file) does not move."""
    base = review_contract()
    packet = {k: v for k, v in base.items() if k != "sha256"}
    fields = {name: list(cols) for name, cols in (packet.get("context_fields") or {}).items()}
    for name, props in _computed_context_fields().items():
        fields[name] = fields.get(name, []) + [p for p in props if p not in fields.get(name, [])]
    packet["context_fields"] = fields
    packet["facts"] = dict(packet.get("facts") or {}, computed=(
        "Besides each class's slots, its public properties exist too: ChainView's iv, delta, gamma, theta and vega are "
        "arrays computed on first read from the chain's own quotes (implied vol and Black-Scholes greeks at the snapshot's "
        "spot), read-only like every other field. Reading them is not a contract defect."))
    return {"sha256": hashlib.sha256(json.dumps(packet, sort_keys=True).encode()).hexdigest(), **packet}


def _computed_context_fields() -> dict[str, list[str]]:
    """The public `@property` names of the Gym's context classes, read from league/gym/ctx.py's own source."""
    out: dict[str, list[str]] = {}
    for node in ast.parse((Path(__file__).resolve().parents[1] / "gym" / "ctx.py").read_text()).body:
        if isinstance(node, ast.ClassDef) and node.name in ("Ctx", "UnderlyingView", "ChainView"):
            out[node.name] = [child.name for child in node.body
                              if isinstance(child, ast.FunctionDef) and not child.name.startswith("_")
                              and any(isinstance(d, ast.Name) and d.id == "property" for d in child.decorator_list)]
    return out


REVIEW = """You review option-trading programs before they meet sealed data. A program is one Python file (NEEDS, PARAMS,
decide(ctx)) that runs in a replay of recorded one-minute option quotes and then, unchanged, on live quotes and real
money. Refuse it (verdict "fail") for any of:
- LOOKAHEAD: anything that could know the future inside the replay (it only sees ctx; flag code that tries to reach
  outside ctx or infers future data). The runtime creates fresh module state per independent run; do not assume
  cross-run STATE leakage. Permitted causal state within one run can still be misused to reconstruct the calendar.
- LEAKAGE: recognizing the calendar or a specific period. Refuse ABSOLUTE PRICE-LEVEL CONSTANTS (an underlying or
  strike level, e.g. "SPY above 550", identifies the years), CALENDAR RECONSTRUCTION (counting sessions, weekdays or
  event flags across a run to work out the date or the year), regime switches keyed to values that identify periods,
  and any table of dates, levels or events. Relative measures (returns, ratios, vol, moneyness, z-scores) are fine.
- FILL ABUSE: relying on fills the live market will not give (limits far through the mid expected to fill, sizes beyond
  the quoted size, orders sent after the venue's cutoffs, churning cancels).
- DANGER on real money: naked short exposure, structures that cannot be closed in one order, unbounded order loops.
Use the supplied runtime facts, API fields and implementation excerpts as the execution contract. Do not invent
unavailable APIs. A claim that contradicts that contract needs a concrete route or counterexample. Distinguish a
verified defect from an unresolved concern; reply unclear when the evidence is insufficient. An inactive strategy
or a causal STATE dictionary alone is not a violation. A price sampled from ctx is not a hard-coded price constant.
For EACH failure provide a verbatim code excerpt present in the submitted file, a contract_reference from the supplied
facts (state, parameters, context, calendar, fills, risk), and a causal counterexample: exact input conditions and the
bad decision or data flow that follows. Do not claim you executed a test unless its result was supplied.
Otherwise pass it. Reply with ONE JSON object: {"verdict": "pass" or "fail" or "unclear", "reasons": ["..."],
"findings": [{"code_excerpt": "...", "contract_reference": "...", "counterexample": "..."}], "notes": "..."}."""


def run_sha(version: Mapping[str, Any]) -> str:
    return hashlib.sha256((str(version["sha"]) + dumps(version.get("params") or {})).encode()).hexdigest()


#: A PAID VERDICT BINDS (the module docstring): the refusal stages a paid reader wrote, and the words of a kept bar
#: (`incubator._audit_bar` with "the gate's") that the gate's own failing review or audit wrote. The incubator's own reads
#: ("the incubator's ...") bar the incubator route only.
PAID_STAGES = ("review", "audit")
PAID_BAR_WORDS = ("the gate's reviewer failed it", "the gate's audit failed it")
#: THE DUPLICATE LOOK's refusal stage (the module docstring).
DUPLICATE_STAGE = "duplicate look"
#: A Validation run's evaluation and outcome, as the Gym's validation view carries them: two runs that agree on all of
#: these made the same trades with the same results under the same engine, engine code, tables and fill model. Left out:
#: the program's own identity (`run_id`, `program`, `program_sha`, `run_sha`, `params`, `needs`), the swarm's labels
#: (`gym_image`, `gym_bundle`) and the runtime's counters (a wall-clock timeout that changed nothing is no new program).
VALIDATION_IDENTITY = ("window", "roots", "engine", "code", "tables", "fill_model", "stress", "capital", "status", "summary",
                       "fills", "breakdown", "stress_1.5")


def validation_identity(result: Mapping[str, Any] | None) -> frozenset[tuple[str, str]]:
    """What a stored Validation result says its run was, for THE DUPLICATE LOOK: ("program", the Gym's own `run_sha`, the
    code with its PARAMS merged over the declared defaults) when it carries one, and ("outcome", a hash of its
    `VALIDATION_IDENTITY`) for a finished run ("ok", at least one trade) that names its engine and the engine's code.
    Empty when it says neither. Hashes only: no figure leaves here."""
    if not isinstance(result, Mapping):
        return frozenset()
    out: set[tuple[str, str]] = set()
    program = result.get("run_sha")
    if isinstance(program, str) and program:
        out.add(("program", program))
    summary = result.get("summary")
    trades = summary.get("trades") if isinstance(summary, Mapping) else None
    if result.get("status") == "ok" and result.get("engine") and result.get("code") and isinstance(trades, int) \
            and not isinstance(trades, bool) and trades > 0:
        body = {key: result.get(key) for key in VALIDATION_IDENTITY}
        if isinstance(body["roots"], (list, tuple)):
            body["roots"] = sorted(str(r).upper() for r in body["roots"])
        out.add(("outcome", hashlib.sha256(dumps(body).encode()).hexdigest()))
    return frozenset(out)


def duplicate_words(duplicate: Mapping[str, Any]) -> str:
    """The refusal's reason, which the researcher reads (D2a): the earlier look's number and why it is a repeat; never a
    figure of Validation or the holdout, nor the earlier look's verdict."""
    what = {"run_sha": "the same program (its code and parameters)",
            "program": "the same program (its code, with parameters that resolve to the same values)"}.get(
        str(duplicate.get("match")), "a version whose Validation run this one repeats exactly")
    return (f"a duplicate of holdout look #{duplicate.get('seq')}, made on {what}: a second look adds no information and "
            "raises the bar for every later look, so only a genuinely different version can be looked at")


#: THE LOOK HOLDS' stages (the module docstring).
HOLD_DRIFT_STAGE = "look hold (drift)"
HOLD_POWER_STAGE = "look hold (power)"
#: What the researcher reads of a hold (D2a: never a figure, of Train, Validation or the holdout).
HOLD_WORDS = {
    HOLD_DRIFT_STAGE: ("the holdout look is held: the program's Train profit leans on market drift (it holds long market "
                       "exposure, and a large share of what it made is what that exposure earns on average days), so a "
                       "holdout pass would mostly measure the market, not the program. No look was spent; a new version "
                       "whose profit does not lean on drift can be looked at"),
    HOLD_POWER_STAGE: ("the holdout look is held: the program makes too few independent bets for the holdout to judge it, "
                       "so a look would most likely fail even if its edge were real, and every look raises the bar for "
                       "every later one. No look was spent; a new version can be looked at once the holdout can judge it"),
}
#: The outcome a hold writes (`Gate.outcome`): one of `bands.BAD_OUTCOMES` (`incubator.BAD_OUTCOMES`), so, as a failed look's
#: does, it ends the version's execution tuition and bars its program from the incubator.
HOLD_OUTCOME = "held"


def look_hold_settings(settings: Mapping[str, Any]) -> tuple[float | None, float | None]:
    """THE LOOK HOLDS' settings (`gate.look_holds`): (drift share, minimum power), each None when off. The key absent is the
    defaults; JSON null (the block, or one of its keys) turns them off; any other value that is not a finite number from 0
    to 1 is its default (a brake is never misread as off)."""
    defaults = (evidence.LOOK_HOLD_DRIFT_SHARE, evidence.LOOK_HOLD_MIN_POWER)
    cfg = settings.get("gate") or {}
    if not isinstance(cfg, Mapping) or "look_holds" not in cfg:
        return defaults
    block = cfg.get("look_holds")
    if block is None:
        return None, None
    if not isinstance(block, Mapping):
        return defaults

    def read(key: str, default: float) -> float | None:
        if key not in block:
            return default
        value = block[key]
        if value is None:
            return None
        number = evidence._num(value)
        return number if number is not None and 0.0 <= number <= 1.0 else default

    return read("drift_share", defaults[0]), read("min_power", defaults[1])


def holdout_sessions() -> int | None:
    """The holdout window's sessions (`pool.HOLDOUT_FIRST` to `HOLDOUT_LAST`, the Gym's window) by the NYSE calendar the
    House trades on (`ltcm.data.us_equity_session`): the N of THE POWER HOLD. None when the calendar cannot say (the hold
    then fails closed)."""
    from . import pool

    return sessions_between(pool.HOLDOUT_FIRST, pool.HOLDOUT_LAST)


def sessions_between(first: str, last: str) -> int | None:
    """The NYSE sessions from `first` to `last` (ISO days, both included); None when the calendar cannot say. A count is
    kept for the process; a failure is not (a hold is for good, so a calendar that failed once is asked again)."""
    try:
        return _sessions_between(str(first), str(last)) or None
    except Exception:  # noqa: BLE001 - no calendar, no figure: the caller holds
        return None


@functools.lru_cache(maxsize=8)
def _sessions_between(first: str, last: str) -> int:
    from ltcm.data import us_equity_session

    day, end = dt.date.fromisoformat(first), dt.date.fromisoformat(last)
    sessions = 0
    while day <= end:
        sessions += us_equity_session(day) is not None
        day += dt.timedelta(days=1)
    return sessions


def reader(answer: Mapping[str, Any]) -> str | None:
    """The model that read a program: for a Sail answer the model its profile dispatches to (`ltcm.provider.model_of`:
    pro_balanced and pro_asap are one reader, DeepSeek-V4-Pro), else the answer's model; None when it names none."""
    model = answer.get("model")
    if model is None:
        return None
    if answer.get("route") == "sail":
        try:
            from ltcm.provider import model_of

            return model_of(str(model))
        except Exception:  # noqa: BLE001 - an unknown profile is its own name
            return str(model)
    return str(model)


def same_reader(review: Mapping[str, Any], audit: Mapping[str, Any]) -> bool:
    """Whether one model read the program twice: the review's reader is the audit's (`reader`, so a review on a Sail
    profile and an audit on another profile of the same model, e.g. the window fallback's, are one reader)."""
    first = reader(review)
    return first is not None and first == reader(audit)


def incubator_stage(stage: str, fid: str, *, incubator: bool = False) -> tuple[str, str]:
    """(the stage's name in its attempt count and model-call key, the Sail desk its fuse is on): the gate's own
    ("review" or "audit", desk "<family>:review"), or the incubator's ("incubator_review" or "incubator_audit", desk
    "<family>:incubator"), so that neither read's tries, cached answers or daily fuse are the other's."""
    return (f"incubator_{stage}", f"{fid}:incubator") if incubator else (stage, f"{fid}:review")


class Gate:
    def __init__(self, store: SwarmStore, pool: Any, router: Any, settings: Mapping[str, Any], *,
                 clock: Callable[[], float] = time.time):
        self.store = store
        self.pool = pool
        self.router = router
        self.settings = settings
        self.clock = clock
        #: The incubator's reads that came back without a final verdict this process, by program: when, so that the
        #: next round reads the others first (one version's repeated error never holds a round's places).
        self.incubator_tried: dict[str, float] = {}
        #: THE VERDICT FIRST's bars not yet recorded (an error, such as a lock held past the store's busy timeout), by
        #: (family, program): (version, why). Recorded again when the gate's own write-back of the verdict fails, and at
        #: the start and the end of every round, before any incubator read, until one lands (`_incubator_owed`). Kept
        #: beside the store too (`incubator.save_owed`), so a restart reads them back here, the evaluator adoption at
        #: its start records them, and the reader refuses their programs meanwhile.
        self.bars_owed: dict[tuple[str, str], tuple[int | None, str]] = {}
        self._owed_saved: dict[tuple[str, str], tuple[int | None, str]] = {}
        try:
            from . import incubator

            self.bars_owed = incubator.load_owed(store.root)
            self._owed_saved = dict(self.bars_owed)
        except Exception:  # noqa: BLE001 - nothing owed is read back; the file stays until the next write
            pass
        #: No Gym job survives its process: a look marked in flight before this moment is owed again.
        self.started_at = clock()
        #: THE DUPLICATE LOOK: each stored Validation result's identity (`validation_identity`), by run id, once read (a
        #: run's stored result never changes).
        self._identities: dict[str, frozenset[tuple[str, str]]] = {}

    @property
    def cfg(self) -> Mapping[str, Any]:
        return self.settings.get("gate", {})

    def due(self) -> bool:
        return self.clock() - float(self.store.get("gate_at", 0.0) or 0.0) >= float(self.cfg.get("every_seconds", 300))

    def alarms(self) -> dict[str, bool]:
        """THE LEAKAGE ALARM PER LANE (release D-1, Oct 9, 2026; `evidence.leakage_alarms`): {"alpha", "direction"}, each
        lane's holdout looks counted alone. While `dlane.mode` is "off" both are the one count, as before, over the looks
        the alpha lane's line judged (every look on a store with no direction look)."""
        return evidence.leakage_alarms(self.store.looks(), self.settings)

    def alarm(self) -> bool:
        """The whole gate stops: every lane's leakage alarm holds. While the direction lane is off that is the one alarm
        (10 looks, more than 30% passed), as before release D-1, over the looks the alpha lane's line judged."""
        return all(self.alarms().values())

    def stopped_lanes(self) -> frozenset[str]:
        """The lanes whose leakage alarm holds (PLAN K6: that lane's looks and incubator reads stop, the other lane's go
        on). While the direction lane is off: none, or both."""
        return frozenset(lane for lane, held in self.alarms().items() if held)

    def lane_alarms(self, out: dict[str, Any]) -> frozenset[str]:
        """The lanes whose alarm holds while the other's does not (the direction lane on; `stopped_lanes`), recorded
        (`_record_alarms`) and named in the round's answer (`alarm_lanes`). Empty while the lane is off: the gate then
        stops whole or not at all (`alarm`), as before."""
        if not dlane.on(self.settings):
            return frozenset()
        stopped = self.stopped_lanes()
        if stopped:
            self._record_alarms(stopped)
            out["alarm_lanes"] = sorted(stopped)
        return stopped

    def _record_alarms(self, stopped: frozenset[str] | None) -> None:
        """Each alarm that holds, recorded once: the store's kv and one `swarm.gate` event (`leakage_alarm`). `stopped`
        None (the direction lane off): the one alarm as before release D-1 (kv `leakage_alarm`, the count over the looks
        the alpha lane's line judged: every look on a store with no direction look, `evidence.leakage_alarms`); else one
        record a lane in `stopped` (the alpha lane's under the same kv, the direction lane's under
        `leakage_alarm_direction`), each with its lane and its own looks and passes."""
        if stopped is None:
            if not self.store.get("leakage_alarm"):
                judged = [x for x in self.store.looks() if evidence.look_lane(x) != dlane.DIRECTION]
                self.store.put("leakage_alarm", {"at": self.clock(), "looks": len(judged)})
                self.store.event("swarm.gate", None, {"action": "leakage_alarm", "looks": len(judged),
                                                      "passes": sum(1 for x in judged if x["passed"])})
            return
        looks = self.store.looks()
        for lane in sorted(stopped):
            key = "leakage_alarm" if lane == dlane.ALPHA else f"leakage_alarm_{lane}"
            if self.store.get(key):
                continue
            mine = [x for x in looks if evidence.look_lane(x) == lane]
            self.store.put(key, {"at": self.clock(), "looks": len(mine), "lane": lane})
            self.store.event("swarm.gate", None, {"action": "leakage_alarm", "lane": lane, "looks": len(mine),
                                                  "passes": sum(1 for x in mine if x["passed"])})

    def lane_closed(self, fam: Mapping[str, Any], state: Mapping[str, Any]) -> str | None:
        """Why the gate takes a DIRECTION family no further now (no review is paid, no look is spent, `gate_ready` stays),
        or None (every alpha family, and every family while the lane is off):
        - THE MODE (`dlane.candidates_open`): in "shadow", or while K5 holds a "gate" lane in shadow, no direction family
          becomes a Candidate, so its look waits rather than being spent on a band it could not take;
        - THE SCREEN'S ENTRY: under "S-C" a direction look follows the Validation line as coded; a version that entered
          the gate by D2's Validation pre-check (`Tournament._verdict`) waits while the screen in force is not D2."""
        if dlane.lane_of(self.store, fam, self.settings) != dlane.DIRECTION:
            return None
        if not dlane.candidates_open(self.store, self.settings):
            return "the direction lane is in shadow: no direction program becomes a Candidate until it opens"
        if dlane.screen_effective(self.settings, dlane.DIRECTION)["validation"] == "line" \
                and not (state.get("validation_line") or {}).get("passed"):
            return "it entered the gate by D2's Validation pre-check, and the screen in force needs the Validation line"
        return None

    def tell(self, fid: str, answer: str, *, verdict: bool = False) -> None:
        """What the researcher hears (its status line): pass or fail, and for a refusal before the look, why. A VERDICT
        (a refusal, a look's pass or fail) is news (R4): the family's dormant count restarts, as a counted validation's
        does, so a researcher waiting out a hold (the scheduler's HOLD BACKOFF) is taken at once to read it, and the idle
        rule's dormancy clause cannot retire the family before it has."""
        self.store.set_state(fid, gate=answer, **({"dormant_cycles": 0} if verdict else {}))

    # ------------------------------------------------------------------ the review
    def review(self, fam: Mapping[str, Any], version: Mapping[str, Any], *, incubator: bool = False) -> dict[str, Any]:
        """The program review: GPT-6 Sol while the OpenAI month has room, else `review_sail_profile` (DeepSeek-V4-Pro).
        Claude answers it first only once the operator adds "review" to `claude.roles` (Sept 29, 2026). With "audit" there
        too (a default role), both reads of a program would be `claude.model` and the audit no longer a second, different
        model: give the review its own model in `claude.role_model` (e.g. {"review": "claude-sonnet-5-5"}). A program
        one model read twice is reported to the owner (`not_the_plans_reviewer`, `same_reader`). `incubator` (the
        incubator's read, `incubator_reviews`): the same question on the same routes, under its own attempt count, its own
        model-call key and its own Sail fuse (`incubator_stage`); without it, everything is the gate's own, as before."""
        user = (f"Family {fam['id']}: {fam['mechanism']}\nStructure {structure_text(fam['structure'])}, roots {', '.join(fam['roots'])}.\n\n"
                f"Runtime contract (actual deployed source): {json.dumps(gate_contract(), sort_keys=True)}\n\n"
                f"```python\n{version['code']}\n```\nPARAMS overrides: {json.dumps(version.get('params') or {})}")
        contract = gate_contract()["sha256"][:12]
        stage, desk = incubator_stage("review", fam["id"], incubator=incubator)
        attempt_key = f"{stage}_attempt:{contract}:{fam['id']}:{version['n']}"
        answer = self.router.ask(role="review", system=REVIEW, user=user, family=fam["id"],
                                 key=f"swarm:{contract}:{fam['id']}:{stage}:{version['n']}:{self.store.get(attempt_key, 0)}",
                                 openai_model=self.cfg.get("review_openai_model"), sail_profile=str(self.cfg.get("review_sail_profile",
                                                                                                                   "pro_balanced")),
                                 max_output=int(self.cfg.get("review_max_output_tokens", 6000)), effort="medium", need_usd=0.5,
                                 desk=desk, cap_usd_day=float(self.cfg.get("review_usd_day", 1.0)), claude=True)
        return dict(grounded_answer(answer, version["code"]), contract_sha=gate_contract()["sha256"])

    # ------------------------------------------------------------------ the audit
    def audit(self, fam: Mapping[str, Any], version: Mapping[str, Any], *, attempt: int = 0,
              incubator: bool = False) -> dict[str, Any]:
        """The gate's audit: Claude (`claude.model`, or `claude.role_model["audit"]`) at high effort through the gateway
        while its funded total has room (the swarm sprint, Sept 26, 2026); else GPT-6 Astra (high, standard) when the
        OpenAI month has room; else a SECOND, DIFFERENT model on Sail (`audit_sail_profile`, Kimi-K3 balanced: the
        reviewer is DeepSeek-V4-Pro), never a pass-through. `incubator`: as `review`'s (its own key and Sail fuse)."""
        stage, desk = incubator_stage("audit", fam["id"], incubator=incubator)
        model = self.cfg.get("audit_openai_model", "gpt-6-astra")
        need = float(self.cfg.get("audit_need_usd", 1.0))
        use_openai = bool(model) and self.router.openai_room() >= need
        user = (f"AUDIT. Family {fam['id']}: {fam['mechanism']}\nStructure {structure_text(fam['structure'])}, roots {', '.join(fam['roots'])}.\n\n"
                f"Runtime contract (actual deployed source): {json.dumps(gate_contract(), sort_keys=True)}\n\n"
                f"```python\n{version['code']}\n```\nPARAMS overrides: {json.dumps(version.get('params') or {})}")
        answer = self.router.ask(role="audit", system=REVIEW, user=user, family=fam["id"],
                                 key=f"swarm:{gate_contract()['sha256'][:12]}:{fam['id']}:{stage}:{version['n']}:{attempt}",
                                 openai_model=model if use_openai else None,
                                 sail_profile=str(self.cfg.get("audit_sail_profile", "k3_balanced")),
                                 max_output=int(self.cfg.get("review_max_output_tokens", 6000)), effort="high", need_usd=need,
                                 desk=desk, cap_usd_day=float(self.cfg.get("review_usd_day", 1.0)), claude=True)
        return dict(grounded_answer(answer, version["code"]), contract_sha=gate_contract()["sha256"])

    def outcome(self, fid: str, sha: str, result: str) -> None:
        """What the gate did with a version (refused, failed, passed, waiting, demoted): the live path runs a Gym-band
        family's validated version as tuition only while this says nothing worse than waiting (`bands.read`). A bad
        outcome is the program's incubator bar first (THE VERDICT FIRST: it outlives `gate_outcome` moving on)."""
        from .incubator import BAD_OUTCOMES

        if result in BAD_OUTCOMES:
            self._incubator_bar(fid, None, sha, why=f"the gate's outcome for it was {result}")
        self.store.set_state(fid, gate_outcome={"sha": sha, "result": result, "at": self.clock()})

    def refuse(self, fam: Mapping[str, Any], n: int, sha: str, stage: str, reasons: list[str], out: dict[str, Any]) -> None:
        """A refusal, recorded (the row, then the program's incubator bar: THE VERDICT FIRST); the version's gate place is
        cleared only if it is still the one validated."""
        self.store.refuse(fam["id"], n, stage, "; ".join(reasons) or f"refused by the {stage}")
        self._incubator_bar(fam["id"], n, sha, why=f"the gate refused it (the {stage})")
        # Its gate place and its dormant count go together (a verdict is news, `tell`): never gate_ready cleared with the
        # count of the cycles it held at the gate still standing.
        if not self.store.compare_and_set_state(fam["id"], {"validation_version": n}, gated_sha=sha, gate_ready=False,
                                                dormant_cycles=0):
            return
        self.outcome(fam["id"], sha, "refused")
        self.tell(fam["id"], f"fail (the {stage}: " + "; ".join(reasons)[:400] + ")", verdict=True)
        out["refused"].append(fam["id"])

    # ------------------------------------------------------------------ THE DUPLICATE LOOK (H3a)
    def duplicate_look(self, fam: Mapping[str, Any], n: Any, sha: str) -> dict[str, Any] | None:
        """The earlier holdout look that a look at version `n` of `fam` (program `sha`) would repeat, or None (the module
        docstring): {"seq" (None for a look still in flight), "family", "version", "match" ("run_sha", "program" or
        "validation"), "inflight"}. Every look the swarm has made counts, in any family and lineage, and so does a look in
        flight in ANOTHER family (`inflight` True: the caller waits for it). Reads the looks table, the in-flight markers and
        stored Validation results (`validation_identity`), never a holdout file. A version's own earlier look is found by
        its run sha alone (the caller closes it); the Validation comparison is with the other looked versions."""
        fid, n = str(fam["id"]), int(n)
        looks = self.store.looks()
        inflight = [(other, marker) for other, marker in self.store.looks_inflight() if other != fid]

        def found(seq: Any, other: str, m: Any, match: str, flying: bool) -> dict[str, Any]:
            return {"seq": None if flying else int(seq), "family": str(other), "version": int(m) if m is not None else None,
                    "match": match, "inflight": flying}

        for look in looks:
            if look["run_sha"] == sha:
                return found(look["seq"], look["family"], look["version"], "run_sha", False)
        for other, marker in inflight:
            if marker.get("sha") == sha:
                return found(None, other, marker.get("n"), "run_sha", True)
        mine = self._validation_identities(fid, n)
        if not mine:
            return None
        earlier = [(look["seq"], look["family"], look["version"], False) for look in looks]
        earlier += [(None, other, marker.get("n"), True) for other, marker in inflight]
        for seq, other, m, flying in earlier:
            if m is None or (str(other) == fid and int(m) == n):
                continue
            common = mine & self._validation_identities(str(other), m)
            if common:
                match = "program" if any(kind == "program" for kind, _ in common) else "validation"
                return found(seq, other, m, match, flying)
        return None

    def _validation_identities(self, fid: str, n: Any) -> frozenset[tuple[str, str]]:
        """Every identity (`validation_identity`) of the stored Validation runs of version `n` of family `fid` at the normal
        spread (finished ones; the Validation results are never pruned). Each result is read once a process."""
        try:
            n = int(n)
        except (TypeError, ValueError):
            return frozenset()
        out: set[tuple[str, str]] = set()
        for row in self.store.version_runs(fid, n, window="validation", stress=1.0, limit=50):
            if row.get("status") != "ok" or not row.get("path"):
                continue
            run_id = str(row["run_id"])
            if run_id not in self._identities:
                result = self.store.run_result(run_id)
                if result is None:
                    continue  # unreadable now: read again next time, never remembered as saying nothing
                self._identities[run_id] = validation_identity(result)
            out |= self._identities[run_id]
        return frozenset(out)

    def refuse_duplicate(self, fam: Mapping[str, Any], n: int, sha: str, duplicate: Mapping[str, Any],
                         out: dict[str, Any]) -> None:
        """THE DUPLICATE LOOK's refusal, recorded as every gate refusal is (`refuse`, stage "duplicate look"), then one
        private `swarm.gate` event naming the earlier look. No look row, no try, no review, no sealed read."""
        self.refuse(fam, n, sha, DUPLICATE_STAGE, [duplicate_words(duplicate)], out)
        self.store.event("swarm.gate", fam["id"], {"action": "duplicate_look", "version": n, "sha": sha[:12],
                                                   "of_look": duplicate.get("seq"), "of_family": duplicate.get("family"),
                                                   "of_version": duplicate.get("version"), "match": duplicate.get("match")})

    # ------------------------------------------------------------------ A PAID VERDICT BINDS (fast lane v2's review)
    def paid_verdict(self, fam: Mapping[str, Any], n: Any, sha: str) -> str | None:
        """Why an earlier paid review or audit binds version `n` of `fam` (program `sha`), or None (the module
        docstring): a kept refusal of the program's version, in this family or a twin's, at the stage "review" or
        "audit", or a kept bar of the program (`incubator_barred[sha]`) whose words are the gate's own failing review or
        audit (`PAID_BAR_WORDS`). Reads the refusal rows and the families' states, never a model."""
        from . import incubator

        fid, n = str(fam["id"]), int(n)
        programs = [(fid, n)] + [(f, m) for f, m in incubator.twins(self.store, fid, n) if (f, m) != (fid, n)]
        for other, m in programs:
            for row in self.store.refusals(other):
                if row.get("version") == m and str(row.get("stage")) in PAID_STAGES:
                    where = "" if other == fid else f" (the same program in {other}, version {m})"
                    return f"the {row['stage']} refused it on {row['at']}{where}: {str(row.get('reason') or '')[:300]}"
        for other in dict.fromkeys(f for f, _ in programs):
            state = ((fam if other == fid else self.store.family(other)) or {}).get("state") or {}
            recorded = state.get("incubator_barred")
            entry = recorded.get(sha) if isinstance(recorded, Mapping) else None
            why = str(entry.get("why") or "") if isinstance(entry, Mapping) else ""
            if why.startswith(PAID_BAR_WORDS):
                where = "" if other == fid else f" (the same program in {other})"
                return f"{why}{where}"
        return None

    def close_paid(self, fam: Mapping[str, Any], n: int, sha: str, why: str, out: dict[str, Any]) -> None:
        """A PAID VERDICT BINDS: the version is closed as one whose look landed (`gated_sha`, `gate_ready` cleared), its
        outcome "refused", the researcher told, and one private `swarm.gate` event. No refusal row is added: the earlier
        verdict's row or bar is the record, and it is kept."""
        if not self.store.compare_and_set_state(fam["id"], {"validation_version": n}, gated_sha=sha, gate_ready=False,
                                                dormant_cycles=0):
            return
        self.outcome(fam["id"], sha, "refused")
        self.store.event("swarm.gate", fam["id"], {"action": "paid_verdict", "version": n, "sha": sha[:12], "earlier": why[:400]})
        self.tell(fam["id"], "fail (an earlier paid review or audit of this program failed it; it is not reviewed again: "
                             f"{why[:300]})", verdict=True)
        out["refused"].append(fam["id"])

    # ------------------------------------------------------------------ THE LOOK HOLDS (L6)
    def look_hold(self, fam: Mapping[str, Any], n: Any) -> dict[str, Any] | None:
        """THE LOOK HOLDS (the module docstring) on version `n` of `fam` (its state as read: `validation_numbers` must be
        version `n`'s): {"stage", "holds" (every hold that fired, the drift hold first), "figures"} when a look at it is
        held, else None. "figures" are operator-only: the drift fit's beta, alpha, drift and share, and the power with
        its Sharpe, sessions, the flat look level and looks counted. Each hold is skipped while its setting is null."""
        drift_share, min_power = look_hold_settings(self.settings)
        if drift_share is None and min_power is None:
            return None
        n = int(n)
        holds: list[str] = []
        figures: dict[str, Any] = {}
        if drift_share is not None:
            lean = evidence.drift_lean(version_drift(self.store, fam, n), first_year=int(running_span(self.store)[:4]))
            held = not lean["known"] or (lean["long_delta"] and (lean["share"] is None or lean["share"] >= drift_share))
            figures["drift"] = {**{k: lean[k] for k in ("known", "beta", "alpha_usd", "drift_usd", "share", "long_delta",
                                                         "years", "why")}, "line": drift_share, "held": bool(held)}
            if held:
                holds.append(HOLD_DRIFT_STAGE)
        if min_power is not None:
            state = fam.get("state") or {}
            sharpe = (state.get("validation_numbers") or {}).get("sharpe_daily") if state.get("validation_version") == n \
                else None
            previous = [x["p_value"] for x in self.store.looks() if x["p_value"] is not None]
            flying = [other for other, _ in self.store.looks_inflight() if other != str(fam["id"])]
            level = evidence.LOOK_LEVEL  # FAST LANE V2: the flat look; the looks before and in flight are figures only
            sessions = holdout_sessions()
            power = evidence.holdout_power(sharpe, sessions, level)
            held = power is None or power < min_power
            figures["power"] = {"power": power, "sharpe_daily": evidence._num(sharpe), "sessions": sessions, "level": level,
                                "looks_before": len(previous), "inflight_elsewhere": len(flying), "line": min_power,
                                "held": bool(held)}
            if held:
                holds.append(HOLD_POWER_STAGE)
        if not holds:
            return None
        return {"stage": holds[0], "holds": holds, "figures": figures}

    def hold_look(self, fam: Mapping[str, Any], n: int, sha: str, hold: Mapping[str, Any], out: dict[str, Any]) -> None:
        """THE LOOK HOLDS' record, as a refusal's is ordered (`refuse`): one `look_holds` row (the researcher's words), the
        program's incubator bar (THE VERDICT FIRST: whatever happens next, a held program never trades the incubator),
        one private `swarm.gate` event with the figures, then, only if the version is still the one validated, its gate
        place closed (`gated_sha`, `gate_ready` cleared, the dormant count restarted: a verdict is news), the outcome
        "held" (one of `bands.BAD_OUTCOMES`: its execution tuition ends) and the researcher's status line. No look row,
        no try, no review, no audit, no sealed read."""
        fid, stage = str(fam["id"]), str(hold["stage"])
        words = HOLD_WORDS[stage]
        self.store.hold_look(fid, n, sha, stage, words)
        self._incubator_bar(fid, n, sha, why=f"the gate held its holdout look ({stage})")
        self.store.event("swarm.gate", fid, {"action": "look_hold", "version": n, "sha": sha[:12], "stage": stage,
                                             "holds": list(hold.get("holds") or [stage]),
                                             "_figures": hold.get("figures")})  # the figures stay private (underscore)
        if not self.store.compare_and_set_state(fid, {"validation_version": n}, gated_sha=sha, gate_ready=False,
                                                dormant_cycles=0):
            return
        self.outcome(fid, sha, HOLD_OUTCOME)
        self.tell(fid, words, verdict=True)
        out["look_held"].append(fid)

    # ------------------------------------------------------------------ one round
    def run(self) -> dict[str, Any]:
        self.store.put("gate_at", self.clock())
        out: dict[str, Any] = {"looked": [], "refused": [], "waiting": [], "held": [], "look_held": []}
        self._incubator_owed()  # a verdict an error kept from its bar last round: recorded first
        self._incubator_sweep()  # a look that landed, or a demotion, since the last round: its mark goes first
        if self.alarm():  # every lane's alarm (the lane off: the one alarm, alpha-line looks): the whole gate stops
            self._record_alarms(self.stopped_lanes() if dlane.on(self.settings) else None)
            out["alarm"] = True
            return out
        stopped = self.lane_alarms(out)  # THE LEAKAGE ALARM PER LANE: that lane's looks stop, the other's go on
        limit = settings_mod.run_timeout(self.settings) + 1200
        for fam in self.store.families():
            state = fam.get("state") or {}
            inflight = state.get("look_inflight") or {}
            if inflight.get("sha"):
                at = float(inflight.get("at") or 0)
                if at < self.started_at or self.clock() - at > limit:
                    # Its job died with a process (no Gym job survives one), or never came back: the look is owed again,
                    # if its version is still the one validated (`owe`); a superseded version's marker is just dropped.
                    self.owe(fam["id"], int(inflight.get("n") or 0), str(inflight["sha"]), marker=inflight)
                    fam = self.store.family(fam["id"]) or fam
                    state = fam.get("state") or {}
            if state.get("look_inflight"):
                continue  # one look per family in flight; its reservation must survive until it resolves
            if fam.get("retired_at") or fam["band"] != "gym" or not state.get("gate_ready"):
                continue
            if state.get("gate_hold"):
                # THE OPERATOR'S HOLD (`SwarmStore.hold_gate`): nothing of it is looked at (no review, audit or look), and
                # its gate_ready stays, so it is looked at once the hold is cleared.
                out["held"].append(fam["id"])
                continue
            if stopped and dlane.lane_of(self.store, fam, self.settings) in stopped:
                # THE LEAKAGE ALARM of its lane (release D-1): nothing of it is looked at, and its gate_ready stays.
                out.setdefault("alarm_held", []).append(fam["id"])
                continue
            image = self.pool.image("gym") if callable(getattr(self.pool, "image", None)) else None
            bundle = self.pool.bundle() if callable(getattr(self.pool, "bundle", None)) else None
            if state.get("validation_image") != image or state.get("validation_bundle") != bundle:
                continue  # the tournament owes validation on the current data before any holdout is opened
            n = state.get("validation_version")
            version = self.store.version(fam["id"], n)
            if version is None or not version.get("code"):
                continue
            sha = run_sha(version)
            if state.get("gated_sha") == sha:
                continue  # the gate is done with it (its look landed, or it was refused)
            if (state.get("look_inflight") or {}).get("sha") == sha:
                continue  # its look is in flight
            duplicate = self.duplicate_look(fam, n, sha)
            if duplicate is not None:  # THE DUPLICATE LOOK, before anything is asked of the version
                if duplicate["inflight"]:
                    out["waiting"].append(fam["id"])  # the same program's look is out in another family: judged once it lands
                elif duplicate["family"] == fam["id"] and duplicate["version"] == int(n):
                    # This version's own look (its mark lost to a newer validation meanwhile): the gate is done with it.
                    self.store.compare_and_set_state(fam["id"], {"validation_version": n}, gated_sha=sha, gate_ready=False)
                else:
                    self.refuse_duplicate(fam, n, sha, duplicate, out)
                continue
            earlier = self.paid_verdict(fam, n, sha)
            if earlier is not None:  # A PAID VERDICT BINDS: a failed review or audit outlives an evaluator adoption
                self.close_paid(fam, int(n), sha, earlier, out)
                continue
            try:
                check_experiment(version["code"], version.get("params") or {})
            except CodeRefused as exc:
                self.refuse(fam, n, sha, "experiment contract", [str(exc)], out)
                continue  # a known invalid variant pays for neither model review nor a holdout look
            screen = drift_verdict(self.store, fam, n, self.settings)
            if screen is not None and not screen["passed"]:  # defense in depth: the tournament validates none of these
                if screen["known"]:
                    self.refuse(fam, n, sha, "drift screen", [screen["why"]], out)
                else:
                    out["waiting"].append(fam["id"])  # figures owed (a Train run from before them): no look, no refusal
                continue
            if self.store.lineage_looks(fam["id"], include_inflight=True) >= evidence.LOOKS_PER_LINEAGE:
                if self.store.lineage_looks(fam["id"]) >= evidence.LOOKS_PER_LINEAGE:
                    self.refuse(fam, n, sha, "rations", ["the lineage's three holdout looks are spent"], out)
                else:
                    out["waiting"].append(fam["id"])
                continue
            hold = self.look_hold(fam, n)
            if hold is not None:  # THE LOOK HOLDS: after every free check that refuses, before anything is paid or opened
                self.hold_look(fam, int(n), sha, hold, out)
                continue
            closed = self.lane_closed(fam, state)
            if closed is not None:  # THE DIRECTION LANE (release D-1): after every free check, before anything is paid
                out["waiting"].append(fam["id"])
                self.outcome(fam["id"], sha, "waiting")
                self.tell(fam["id"], f"waiting ({closed})")
                continue
            cached = state.get("review") or {}
            review = cached if cached.get("sha") == sha and cached.get("contract_sha") == gate_contract()["sha256"] else None
            if review is None:  # the review, once a version (kept, so an audit asked again does not redo it)
                if not self._review_current(fam["id"], n, image, bundle):
                    continue
                try:
                    review = self.review(fam, version)
                except Exception as exc:  # noqa: BLE001 - no reviewer, no look
                    self.store.event("swarm.gate", fam["id"], {"action": "review_error", "version": n, "error": str(exc)[:300]})
                    continue
                self._incubator_bar(fam["id"], n, sha, record=review)  # THE VERDICT FIRST: a failed review, before all else
                self.store.event("swarm.gate", fam["id"], {"action": "review", "version": n, **review,
                                                           "not_the_plans_reviewer": review.get("route") not in ("openai", "claude")})
                if review["verdict"] == "unclear":
                    attempt_key = f"review_attempt:{gate_contract()['sha256'][:12]}:{fam['id']}:{n}"
                    attempts = int(self.store.get(attempt_key, 0)) + 1
                    self.store.put(attempt_key, attempts)
                    if attempts < 3:
                        continue
                    review = {**review, "verdict": "fail", "reasons": ["the reviewer could not reach a verdict three times"]}
                    self._incubator_bar(fam["id"], n, sha, record=review)
                review = {**review, "sha": sha, "version": n}
                if not self.store.compare_and_set_state(fam["id"], {"validation_version": n}, review=review):
                    # The tournament validated a newer version meanwhile: this one is not the gate's. A failed review is
                    # the program's incubator bar already (THE VERDICT FIRST), so the fail outlives this write-back; a
                    # bar an error kept from the store is tried again now, since nothing else holds this fail.
                    self._record_owed(fam["id"], sha)
                    continue
            if review["verdict"] == "pass" and "audit" not in review:  # the audit: a second reader, before any look
                if not self._review_current(fam["id"], n, image, bundle):
                    continue  # the paid review remains evidence; a terminal family starts no new paid stage
                attempt_key = f"audit_attempt:{gate_contract()['sha256'][:12]}:{sha}"
                attempts = int(self.store.get(attempt_key, 0))
                try:
                    audit = self.audit(fam, version, attempt=attempts)
                except Exception as exc:  # noqa: BLE001
                    self.store.event("swarm.gate", fam["id"], {"action": "audit_error", "version": n, "error": str(exc)[:300]})
                    continue
                self._incubator_bar(fam["id"], n, sha, record={**review, "audit": audit})  # THE VERDICT FIRST: a failed audit
                self.store.event("swarm.gate", fam["id"], {"action": "audit", "version": n, **audit})
                if audit["verdict"] == "unclear":
                    self.store.put(attempt_key, attempts + 1)
                    if attempts + 1 < 3:
                        continue  # asked again next round, like an unclear review
                    audit = {**audit, "verdict": "fail", "reasons": ["the audit could not reach a verdict three times"]}
                    self._incubator_bar(fam["id"], n, sha, record={**review, "audit": audit})
                review = {**review, "audit": audit}
                if audit["verdict"] != "pass":
                    review = {**review, "verdict": "fail", "stage": "audit",
                              "reasons": audit.get("reasons") or ["the audit could not reach a verdict"]}
                # The plan: two different paid models read the program (GPT-6 Sol or Claude reviews, Claude or GPT-6 Astra
                # audits). Either read on Sail, or one model reading it twice (the review and the audit on the same Claude
                # model once "review" is in `claude.roles`; `claude.role_model` gives them different ones), is the owner's.
                same = same_reader(review, audit)
                if same or review.get("route") not in ("openai", "claude") or audit.get("route") not in ("claude", "openai"):
                    self.store.event("swarm.status", fam["id"], {
                        "action": "not_the_plans_reviewer", "alert": True, "version": n, "same_reader": same,
                        "review": review.get("model"), "audit": audit.get("model"),
                        "text": (f"the review and the audit were both {reader(audit)}: one model read the program "
                                 f"twice ({self._one_reader_hint(audit)})") if same else
                                "a holdout look was reviewed without the plan's models (GPT-6 Sol or Claude reviews; Claude or "
                                "GPT-6 Astra audits): their budgets had no room, so Sail models stood in"})
                if not self.store.compare_and_set_state(fam["id"], {"validation_version": n}, review=review):
                    self._record_owed(fam["id"], sha)  # as the review's: a failed audit is the program's bar already
                    continue
            if not self._review_current(fam["id"], n, image, bundle):
                continue
            if review["verdict"] != "pass":
                self.refuse(fam, n, sha, review.get("stage") or "review", review.get("reasons") or [], out)
                continue
            if not self.settings.get("gym", {}).get("gate_checkpoint"):
                out["waiting"].append(fam["id"])
                self.outcome(fam["id"], sha, "waiting")
                self.tell(fam["id"], "waiting (reviewed; the gate image is not ready yet)")
                continue
            if self.holdout_gap(fam, version, sha):
                out["waiting"].append(fam["id"])  # the image lacks a root's holdout: no look, no try (and one alert)
                self.outcome(fam["id"], sha, "waiting")
                self.tell(fam["id"], "waiting (reviewed; the gate image does not hold every root's holdout yet)")
                continue
            look = self.look(fam, version, sha)
            if look is not None:
                out["looked"].append({"family": fam["id"], "passed": look})
            if self.alarm():
                break
            stopped = self.lane_alarms(out)
        self._incubator_owed()  # before any incubator read: a program owed a bar is never read or passed meanwhile
        if not self.alarm():  # the alarm stops the gate: no review of any kind starts (a lane's alone stops its reads)
            incubated = self._incubator_round(self.lane_alarms(out))
            if incubated:
                out["incubator"] = incubated
        else:
            self._incubator_sweep()  # never a read: the round's verdicts still take their marks by its end
        return out

    # ------------------------------------------------------------------ the incubator's review and audit
    def _incubator_bar(self, fid: str, n: int | None, sha: str, *, why: str | None = None,
                       record: Mapping[str, Any] | None = None, whose: str = "the gate's") -> None:
        """THE VERDICT FIRST (`incubator.record_bar`): a verdict against program `sha` is its incubator bar at once, before
        the gate writes anything else, and its incubator mark goes in the same transaction; so no compare-and-set that a
        newer validation beat, no operator's hold and no error after it can lose it. `why` names a refusal or an
        outcome; `record` is a review (with its audit) as its reader returned it (`incubator.verdict_bar`: a pass, and
        an unclear answer still to be asked again, bar nothing; a record it cannot read bars, fail-closed), `whose` its
        reader. Never failing the gate: an error is one private event and the bar is OWED (`bars_owed`), recorded again
        when the gate's write-back of the verdict fails and at the start and the end of every round until it lands."""
        from . import incubator

        if record is not None:
            try:
                why = incubator.verdict_bar(record, whose)
            except Exception:  # noqa: BLE001 - a verdict that cannot be read bars its program (fail-closed)
                why = f"{whose} review of it cannot be read"
        if why is None:
            return
        self.bars_owed[(str(fid), str(sha))] = (n, str(why))
        self._record_owed(str(fid), str(sha))

    def _record_owed(self, fid: str, sha: str) -> bool:
        """Record the bar owed for program `sha` of family `fid` (`bars_owed`), if any: True once nothing is owed for it.
        `incubator.record_bar` keeps a program's first entry, so a second recording changes nothing. An error is one
        private event (`incubator_bar_error`) and the bar stays owed."""
        from . import incubator

        owed = self.bars_owed.get((str(fid), str(sha)))
        if owed is None:
            return True
        n, why = owed
        try:
            incubator.record_bar(self.store, str(fid), str(sha), why, version=n, clock=self.clock)
        except Exception as exc:  # noqa: BLE001
            self._save_owed()  # kept beside the store before anything else can fail
            try:
                self.store.event("swarm.gate", str(fid), {"action": "incubator_bar_error", "version": n, "sha": str(sha)[:12],
                                                          "bar": why, "error": f"{type(exc).__name__}: {str(exc)[:300]}"})
            except Exception:  # noqa: BLE001 - the store itself erring: the bar stays owed all the same
                pass
            return False
        self.bars_owed.pop((str(fid), str(sha)), None)
        self._save_owed()
        return True

    def _save_owed(self) -> None:
        """The bars owed, kept beside the store when they changed since last kept (`incubator.save_owed`); an error is
        one private event (the bars stay owed in this process all the same)."""
        from . import incubator

        if self.bars_owed == self._owed_saved:
            return
        try:
            incubator.save_owed(self.store.root, self.bars_owed)
            self._owed_saved = dict(self.bars_owed)
        except Exception as exc:  # noqa: BLE001
            try:
                self.store.event("swarm.gate", None, {"action": "incubator_owed_error", "owed": len(self.bars_owed),
                                                      "error": f"{type(exc).__name__}: {str(exc)[:300]}"})
            except Exception:  # noqa: BLE001
                pass

    def _incubator_owed(self) -> None:
        """Every bar still owed (`bars_owed`), recorded again; never failing the gate's round."""
        for fid, sha in list(self.bars_owed):
            self._record_owed(fid, sha)

    def _incubator_sweep(self) -> dict[str, Any]:
        """`incubator.sweep`, never failing the gate's round (an error is one private event; the next round sweeps again)."""
        from . import incubator

        try:
            return incubator.sweep(self.store, self.settings, clock=self.clock)
        except Exception as exc:  # noqa: BLE001
            self.store.event("swarm.gate", None, {"action": "incubator_sweep_error", "error": f"{type(exc).__name__}: {str(exc)[:300]}"})
            return {"error": type(exc).__name__}

    def _incubator_round(self, stopped: frozenset[str] = frozenset()) -> dict[str, Any]:
        """The sweep (this round's refusals, looks and reviews), then `incubator_reviews` (none for a family of a lane in
        `stopped`, whose leakage alarm holds), then the sweep again when one of them failed (its mark goes within the
        round); never failing the gate's round (an error is one private event)."""
        self._incubator_sweep()
        try:
            out = self.incubator_reviews(stopped=stopped)
        except Exception as exc:  # noqa: BLE001 - the gate's own work is done; the incubator waits for the next round
            self.store.event("swarm.gate", None, {"action": "incubator_error", "error": f"{type(exc).__name__}: {str(exc)[:300]}"})
            return {"error": type(exc).__name__}
        if out.get("failed"):
            self._incubator_sweep()
        return out

    def incubator_reviews(self, *, stopped: frozenset[str] = frozenset()) -> dict[str, Any]:
        """THE INCUBATOR'S REVIEW AND AUDIT (`league/swarm/incubator.py`; release B2, Sept 30, 2026). The owner kept the
        gate's review and audit required for the incubator route. At most `gate.incubator_reviews` (2) of the versions
        `incubator.due_reviews` names are read a round, also when nothing is gate_ready, those this process read least
        recently first (`incubator_tried`: a version whose read keeps erring never holds the round's places): by the same
        `review` and `audit` (the same prompt, routing and models) and the same attempt rules (an unclear answer is asked
        again next round, and a third is a failure), under the incubator's OWN attempt counts, model-call keys and Sail
        fuse (`incubator_stage`), so the gate's own tries and fuse for the same version are untouched; and the same
        `not_the_plans_reviewer` alert. The result is `incubator_reviews[sha]` in the family's state, the review kept while
        its audit is owed. A failed review or audit is final for that program. It never touches `review`, `gate_ready`,
        `gated_sha`, `gate_outcome` or the looks, spends no look, and tells the researcher nothing: the incubator is never
        evidence and never a promotion. Returns {"reviewed", "failed", "waiting"} (family@version), empty when nothing
        was due. THE LANES (release D-1): no read of a family whose lane is in `stopped` (its leakage alarm holds), nor of
        a direction family while the direction lane takes no incubator mark (`dlane.candidates_open`: "shadow", or K5);
        while the lane is off nothing is left out."""
        from . import incubator

        limit = incubator.reviews_per_round(self.settings)
        if limit <= 0:
            return {}
        due = incubator.due_reviews(self.store, self.settings, self.store.root, clock=self.clock)
        due = [r for r in due if (str(r["family"]), str(r["sha"])) not in self.bars_owed]  # a verdict against it is owed
        closed = set(stopped)
        if dlane.on(self.settings) and not dlane.candidates_open(self.store, self.settings):
            closed.add(dlane.DIRECTION)
        if closed:
            due = [r for r in due if dlane.lane_of(self.store, self.store.family(str(r["family"])), self.settings) not in closed]
        due = sorted(due, key=lambda r: self.incubator_tried.get(str(r["sha"]), 0.0))[:limit]  # stable: oldest cohort next
        if not due:
            return {}
        out: dict[str, Any] = {"reviewed": [], "failed": [], "waiting": []}
        for item in due:
            fid, n, sha = str(item["family"]), int(item["version"]), str(item["sha"])
            try:
                verdict = self._incubator_review(fid, n, sha)
            except Exception as exc:  # noqa: BLE001 - one version never stops the others
                self.store.event("swarm.gate", fid, {"action": "incubator_error", "version": n,
                                                     "error": f"{type(exc).__name__}: {str(exc)[:300]}"})
                verdict = None
            key = {"pass": "reviewed", "fail": "failed"}.get(str(verdict), "waiting")
            out[key].append(f"{fid}@{n}")
            if key == "waiting":
                self.incubator_tried[sha] = self.clock()
            else:
                self.incubator_tried.pop(sha, None)
        return out

    def _incubator_review(self, fid: str, n: int, sha: str) -> str | None:
        """One version's incubator review, then its audit: "pass" or "fail" once final, else None (asked again next
        round, or no longer reviewable)."""
        from . import incubator

        if not incubator.reviewable(self.store, fid, n, sha):
            return None
        fam = self.store.family(fid) or {}
        version = self.store.version(fid, n) or {}
        contract = gate_contract()["sha256"]
        record = ((fam.get("state") or {}).get("incubator_reviews") or {}).get(sha)
        if not (isinstance(record, Mapping) and record.get("sha") == sha and record.get("contract_sha") == contract
                and record.get("verdict") == "pass"):
            try:
                check_experiment(version["code"], version.get("params") or {})
            except CodeRefused as exc:  # a known invalid variant pays for no model read
                incubator.put_review(self.store, fid, sha, {
                    "sha": sha, "version": n, "verdict": "fail", "stage": "experiment contract", "reasons": [str(exc)[:500]],
                    "model": None, "route": None, "contract_sha": contract, "at": self.clock()}, clock=self.clock)
                self.store.event("swarm.gate", fid, {"action": "incubator_review", "version": n, "verdict": "fail",
                                                     "stage": "experiment contract", "reasons": [str(exc)[:300]]})
                return "fail"
            try:
                review = self.review(fam, version, incubator=True)
            except Exception as exc:  # noqa: BLE001 - no reviewer: asked again next round
                self.store.event("swarm.gate", fid, {"action": "incubator_review_error", "version": n, "error": str(exc)[:300]})
                return None
            self._incubator_bar(fid, n, sha, record=review, whose="the incubator's")  # THE VERDICT FIRST: a failed review
            self.store.event("swarm.gate", fid, {"action": "incubator_review", "version": n, **review,
                                                 "not_the_plans_reviewer": review.get("route") not in ("openai", "claude")})
            if review["verdict"] == "unclear":
                # The incubator's own count (`review`'s key reads the same one): the gate's three tries are its own.
                attempt_key = f"incubator_review_attempt:{contract[:12]}:{fid}:{n}"
                attempts = int(self.store.get(attempt_key, 0)) + 1
                self.store.put(attempt_key, attempts)
                if attempts < 3:
                    return None
                review = {**review, "verdict": "fail", "reasons": ["the reviewer could not reach a verdict three times"]}
            record = {"sha": sha, "version": n, "verdict": review["verdict"], "reasons": list(review.get("reasons") or [])[:6],
                      "model": review.get("model"), "route": review.get("route"), "contract_sha": review.get("contract_sha") or contract,
                      "at": self.clock()}
            # Kept, so an audit asked again does not redo the review; a fail (a third unclear answer too) is the program's
            # incubator bar in the same transaction.
            record = incubator.put_review(self.store, fid, sha, record, clock=self.clock)  # as kept (a barred pass: revoked)
            if record["verdict"] != "pass":
                return "fail"
            if not incubator.reviewable(self.store, fid, n, sha):
                return None  # the paid review stays recorded; a version no longer eligible starts no new paid stage
        attempt_key = f"incubator_audit_attempt:{contract[:12]}:{sha}"  # the incubator's own count, as the review's
        attempts = int(self.store.get(attempt_key, 0))
        try:
            audit = self.audit(fam, version, attempt=attempts, incubator=True)
        except Exception as exc:  # noqa: BLE001
            self.store.event("swarm.gate", fid, {"action": "incubator_audit_error", "version": n, "error": str(exc)[:300]})
            return None
        self._incubator_bar(fid, n, sha, record={**record, "audit": audit}, whose="the incubator's")  # THE VERDICT FIRST
        self.store.event("swarm.gate", fid, {"action": "incubator_audit", "version": n, **audit})
        if audit["verdict"] == "unclear":
            self.store.put(attempt_key, attempts + 1)
            if attempts + 1 < 3:
                return None
            audit = {**audit, "verdict": "fail", "reasons": ["the audit could not reach a verdict three times"]}
        kept = {"verdict": audit["verdict"], "reasons": list(audit.get("reasons") or [])[:6], "model": audit.get("model"),
                "route": audit.get("route"), "contract_sha": audit.get("contract_sha") or contract}
        record = {**record, "audit": kept, "at": self.clock()}
        if audit["verdict"] != "pass":
            record.update(verdict="fail", stage="audit", reasons=kept["reasons"] or ["the audit could not reach a verdict"])
        record = incubator.put_review(self.store, fid, sha, record, clock=self.clock)  # the verdict first, the alert after
        # The plan's two different paid readers (`run`): either read on Sail, or one model reading the program twice, is the
        # owner's to know, for an incubator review as for a holdout look.
        same = same_reader(record, audit)
        if same or record.get("route") not in ("openai", "claude") or audit.get("route") not in ("claude", "openai"):
            self.store.event("swarm.status", fid, {
                "action": "not_the_plans_reviewer", "alert": True, "version": n, "same_reader": same, "incubator": True,
                "review": record.get("model"), "audit": audit.get("model"),
                "text": (f"an incubator review and its audit were both {reader(audit)}: one model read the program twice "
                         f"({self._one_reader_hint(audit)})") if same else
                        "an incubator review was made without the plan's models (GPT-6 Sol or Claude reviews; Claude or GPT-6 "
                        "Astra audits): their budgets had no room, so Sail models stood in"})
        return str(record["verdict"])

    @staticmethod
    def _one_reader_hint(audit: Mapping[str, Any]) -> str:
        """What gives the two reads different models, for the owner's one-reader alert."""
        if audit.get("route") == "sail":
            return ("gate.review_sail_profile and gate.audit_sail_profile name different models; sail_fallback_same_model "
                    "keeps the audit's on a stalled window")
        return "claude.role_model can give the review its own Claude model"

    def _review_current(self, fid: str, n: int, image: Any, bundle: Any) -> bool:
        fam = self.store.family(fid) or {}
        state = fam.get("state") or {}
        return bool(not fam.get("retired_at") and fam.get("band") == "gym" and state.get("gate_ready")
                    and not state.get("gate_hold")  # held by the operator between two stages: no further paid stage
                    and state.get("validation_version") == n and state.get("validation_image") == image
                    and state.get("validation_bundle") == bundle)

    def look(self, fam: Mapping[str, Any], version: Mapping[str, Any], sha: str) -> bool | None:
        """The one holdout look. None when the gate box did not run it (no look is spent). The version is marked as
        looked at BEFORE the box runs it, so a slow look is never started twice; one that lands after the gate stopped
        waiting is recorded and judged when it lands (`finish`), against the validation it was sent for."""
        n = int(version["n"])
        if self.holdout_gap(fam, version, sha):
            return None  # the gate image lacks a root's holdout: refused up front, no try counted
        state = fam.get("state") or {}
        vsharpe = (state.get("validation_numbers") or {}).get("sharpe_daily")
        image = self.pool.image("gym") if callable(getattr(self.pool, "image", None)) else None
        bundle = self.pool.bundle() if callable(getattr(self.pool, "bundle", None)) else None
        marker = {"sha": sha, "n": n, "at": self.clock(), "token": secrets.token_hex(8)}
        # Compare-and-set under the store's lock: only the version still validated is looked at; the marker says a look
        # is in flight (not `gated_sha`: a look cut off by a restart must be owed, not forgotten).
        with self.store.atomic():
            current = self.store.family(fam["id"]) or {}
            if current.get("retired_at") or (current.get("state") or {}).get("gate_hold") or self.store.looked(sha) or \
                    self.store.lineage_looks(fam["id"], include_inflight=True) >= evidence.LOOKS_PER_LINEAGE or \
                    self.duplicate_look(current, n, sha) is not None or self.look_hold(current, n) is not None or \
                    self.lane_closed(current, current.get("state") or {}) is not None:
                # (held by the operator meanwhile: no look is spent, gate_ready stays; a look it would repeat landed or went
                # out meanwhile: THE DUPLICATE LOOK refuses it next round, or waits for it; a hold switched on meanwhile:
                # THE LOOK HOLDS hold it next round. Since fast lane v2 the level is flat, so a look elsewhere moves no power.
                # The direction lane closed meanwhile (K5): its look waits, release D-1)
                return None
            if not self.store.compare_and_set_state(fam["id"], {"validation_version": n, "validation_image": image, "validation_bundle": bundle,
                                                               "look_inflight": None}, gate_ready=False, look_inflight=marker):
                return None
        job = GymJob(family=fam["id"], version=n, code=version["code"], params=version.get("params") or {}, window="holdout",
                     roots=needs_roots(version["code"], fam["roots"]), gate=f"holdout look {fam['id']} v{n}", purpose="holdout",
                     priority=10.0)  # the version's own NEEDS roots, as its validation ran (a family's roots may move)
        try:
            result = self.pool.run(job, timeout=settings_mod.run_timeout(self.settings) + 600,
                                   late=lambda r: self.finish(fam["id"], version, sha, r, validation_sharpe=vsharpe,
                                                              validation_image=image, validation_bundle=bundle, marker=marker),
                                   late_fail=lambda why: self.owe(fam["id"], n, sha, marker=marker,
                                                                  missing=getattr(job, "missing", None)))
        except PoolError as exc:
            missing = getattr(job, "missing", None)
            self.store.event("swarm.gate", fam["id"], {"action": "look_failed", "version": n, "error": str(exc)[:300],
                                                       **({"missing_data": list(missing)} if missing else {})})
            if job.result is None and job.late is None:  # it never ran (or the Gym failed it): the look is still owed
                self.owe(fam["id"], n, sha, marker=marker, missing=missing)
            return None
        return self.finish(fam["id"], version, sha, result, validation_sharpe=vsharpe, validation_image=image,
                           validation_bundle=bundle, marker=marker)

    def clear_marker(self, fid: str, sha: str) -> bool:
        """Drop the in-flight marker only if it is this look's (a newer version's look may be out meanwhile)."""
        marker = ((self.store.family(fid) or {}).get("state") or {}).get("look_inflight")
        if not marker or marker.get("sha") != sha:
            return False
        return self.store.compare_and_set_state(fid, {"look_inflight": marker}, look_inflight=None)

    def owe(self, fid: str, n: int, sha: str, *, marker: Mapping[str, Any] | None = None,
            missing: Any = None) -> None:
        """The look did not happen. Its marker goes; if the version is still the one validated it is owed one again, three
        tries, and after the third it is refused as the Gym could not look (one refusal, never forgotten, and an alert at
        that try and every one after it). A failure for MISSING DATA (`missing`: the roots the gate image lacked) counts no
        try and is never refused: the image's fault, not the program's (one alert, `holdout_gap`'s). A superseded version
        is owed nothing: no try is counted, nothing is refused."""
        with self.store.atomic():
            state = (self.store.family(fid) or {}).get("state") or {}
            if marker is not None and state.get("look_inflight") != marker:
                return  # an old attempt's callback cannot cancel or count a newer attempt
            self._owe(fid, n, sha, missing=missing)

    def _owe(self, fid: str, n: int, sha: str, *, missing: Any = None) -> None:
        self.clear_marker(fid, sha)
        if self.store.looked(sha):
            return
        fam = self.store.family(fid) or {}
        if fam.get("retired_at") or (fam.get("state") or {}).get("validation_version") != n:
            return
        if missing:
            self.store.compare_and_set_state(fid, {"validation_version": n}, gated_sha=None, gate_ready=True)
            self._missing_alert(fid, n, sha, list(missing), "a look failed for missing data")
            return
        tries = int(self.store.get(f"look_tries:{sha}", 0)) + 1
        self.store.put(f"look_tries:{sha}", tries)
        parked = (fam.get("state") or {}).get("gated_sha") == sha  # already parked on this program: no new failure
        if tries < 3:
            self.store.compare_and_set_state(fid, {"validation_version": n}, gated_sha=None, gate_ready=True)
        elif self.store.compare_and_set_state(fid, {"validation_version": n}, gated_sha=sha, gate_ready=False,
                                              dormant_cycles=0) and not parked:
            if tries == 3:  # a refusal: news, like `refuse`
                self.store.refuse(fid, n, "gym", "the gate box could not make this holdout look three times")
                self._incubator_bar(fid, n, sha, why="the gate refused it (the gym)")
            # From three on, every failure that parks the family is an alert: a fourth (the same program in a revived
            # family, whose tries are kept by program) is never silent.
            self.store.event("swarm.status", fid, {
                "action": "look_failed_three_times", "alert": True, "version": n, "tries": tries,
                "text": "the gate box could not make a holdout look three times" if tries == 3 else
                        (f"the gate box could not make this program's holdout look ({tries} tries): the version is parked; "
                         "its program was refused at the third try. Fix the gate, then reset look_tries for it")})

    def holdout_gap(self, fam: Mapping[str, Any], version: Mapping[str, Any], sha: str) -> list[str]:
        """The roots program `version` needs (its NEEDS, as its look would run) that the gate image is known to lack a
        holdout for, from metadata only: the pool's record of the image (a gate box's file-name listing, and the roots a
        Gym "missing data" answer named) and the nightly ready file's `holdout_roots` while that chain is the gate. Empty
        when nothing says a root is missing (a first look on a new image: its box lists at start, and a miss then is
        owed with no try). A gap raises one alert per program, image and gap (`_missing_alert`)."""
        roots = sorted({str(r).upper() for r in needs_roots(version["code"], fam["roots"])})
        image = str(self.settings.get("gym", {}).get("gate_checkpoint") or "")
        lacking: set[str] = set()
        reader = getattr(self.pool, "holdout_coverage", None)
        record = reader(image) if callable(reader) and image else None
        if isinstance(record, Mapping):
            if isinstance(record.get("roots"), list):
                lacking |= set(roots) - {str(r).upper() for r in record["roots"]}
            lacking |= set(roots) & {str(r).upper() for r in (record.get("missing") or ())}
        ready = self.settings.get("forward", {}).get("ready") or {}
        if ready.get("gate_checkpoint") == image and isinstance(ready.get("holdout_roots"), list):
            lacking |= set(roots) - {str(r).upper() for r in ready["holdout_roots"]}
        gap = sorted(lacking)
        if gap:
            self._missing_alert(fam["id"], int(version["n"]), sha, gap, "the look was refused before it started")
        return gap

    def _missing_alert(self, fid: str, n: int, sha: str, missing: list[str], what: str) -> None:
        """One `swarm.gate` event and one `swarm.status` alert per program, gate image and missing roots (kv
        `gate_missing:<sha>`), never one a round."""
        image = str(self.settings.get("gym", {}).get("gate_checkpoint") or "")
        seen = f"{image}|{','.join(sorted(missing))}"
        if self.store.get(f"gate_missing:{sha}") == seen:
            return
        self.store.put(f"gate_missing:{sha}", seen)
        self.store.event("swarm.gate", fid, {"action": "look_missing_data", "version": n, "missing": sorted(missing),
                                             "image": image})
        self.store.event("swarm.status", fid, {
            "action": "gate_missing_data", "alert": True, "version": n, "missing": sorted(missing), "image": image,
            "text": (f"{what}: the gate image {image} holds no holdout for {', '.join(sorted(missing))}. No try was counted "
                     "and nothing was refused; the look waits until gym.gate_checkpoint names an image that holds them")})

    def finish(self, fid: str, version: Mapping[str, Any], sha: str, result: Mapping[str, Any], *,
               validation_sharpe: Any = None, validation_image: Any = None, validation_bundle: Any = None,
               marker: Mapping[str, Any] | None = None) -> bool | None:
        """Record a holdout result as the look it is (once: a second result for the same version is ignored) and answer.
        A result the Gym could not produce (an engine error, no data) is no look: it stays owed. Nothing here undoes a
        newer validation the tournament wrote while the look ran."""
        with self.store.atomic():
            return self._finish(fid, version, sha, result, validation_sharpe=validation_sharpe, validation_image=validation_image,
                                validation_bundle=validation_bundle, marker=marker)

    def _finish(self, fid: str, version: Mapping[str, Any], sha: str, result: Mapping[str, Any], *,
                validation_sharpe: Any, validation_image: Any, validation_bundle: Any, marker: Mapping[str, Any] | None) -> bool | None:
        fam = self.store.family(fid)
        if fam is None or self.store.looked(sha):
            return None
        n = int(version["n"])
        if result.get("status") in ("error", "no_data"):
            self.store.event("swarm.gate", fid, {"action": "look_failed", "version": n, "status": result.get("status")})
            self.owe(fid, n, sha, marker=marker)
            return None
        years = float((result.get("summary") or {}).get("days") or 0) / 252.0 * max(1, len(fam["roots"]))
        self.store.add_run(fid, n, result, window="holdout", stress=1.0, purpose="holdout", program_years=years)
        previous = [x["p_value"] for x in self.store.looks() if x["p_value"] is not None]
        lane = dlane.lane_of(self.store, fam, self.settings)
        screen = dlane.screen_effective(self.settings, lane)
        line = self.look_line(fid, n, result, screen, validation_sharpe=validation_sharpe, previous=previous, seed=sha)
        self.store.add_look(fid, n, sha, passed=line["passed"], p_value=line["p"], detail=line)
        self.clear_marker(fid, sha)  # only its own: a newer version's look may be in flight
        self.store.compare_and_set_state(fid, {"validation_version": n}, gated_sha=sha)
        recorded = {k: line[k] for k in ("lane", "screen", "receipt") if k in line}  # release D-1: none while the lane is off
        self.store.event("swarm.gate", fid, {"action": "look", "version": n, "passed": line["passed"], **recorded,
                                             "_line": line})  # the numbers stay private (underscore)
        self.tell(fid, "pass" if line["passed"] else "fail", verdict=True)
        self.outcome(fid, sha, "passed" if line["passed"] else "failed")
        has_image = callable(getattr(self.pool, "image", None))
        has_bundle = callable(getattr(self.pool, "bundle", None))
        image = self.pool.image("gym") if has_image else None
        gate_image = self.pool.image("gate") if has_image else None
        bundle = self.pool.bundle() if has_bundle else None
        # Opening sealed data consumes the look even when its image was replaced while the job ran. Only a result
        # actually produced by the current gate data and engine can promote. Identity-less pools exist in tests only.
        current_holdout = ((not has_image or (gate_image is not None and result.get("gym_image") == gate_image))
                           and (not has_bundle or (bundle is not None and result.get("gym_bundle") == bundle)))
        if line["passed"] and fam["band"] == "gym" and not fam.get("retired_at") and validation_image == image \
                and validation_bundle == bundle and current_holdout:
            if lane == dlane.DIRECTION and not dlane.candidates_open(self.store, self.settings):
                # THE DIRECTION LANE'S MODE (release D-1): a look that was out when the lane went to "shadow" (K5) lands
                # recorded and judged, and no direction family becomes a Candidate meanwhile.
                self.store.event("swarm.gate", fid, {"action": "candidate_withheld", "version": n, "lane": lane,
                                                     "why": "the direction lane is in shadow (dlane.mode, or K5)"})
                return True
            from ..gym import ENGINE_VERSION
            from ..gym.experiment import CONTRACT_VERSION
            from .evaluator import execution_fingerprint

            self.store.set_state(fid, banded_version=n, banded_sha=version["sha"], banded_at=self.clock(),
                                 banded_evaluator={"engine": ENGINE_VERSION, "parameter_contract": CONTRACT_VERSION,
                                                   "execution_sha256": execution_fingerprint(),
                                                   "run_sha": sha, "validation_bundle": bundle,
                                                   "holdout_bundle": result.get("gym_bundle"), "holdout_image": result.get("gym_image")})
            self.store.set_band(fid, "candidate", reason="passed its holdout look")
        return bool(line["passed"])

    def look_line(self, fid: str, n: int, result: Mapping[str, Any], screen: Mapping[str, Any], *,
                  validation_sharpe: Any, previous: list[Any], seed: str) -> dict[str, Any]:
        """THE LOOK'S LINE BY LANE (release D-1, Oct 9, 2026; PLAN D6, the operator's decision 6), from the family's
        screen (`dlane.screen_effective`):
        - "S-B", the alpha lane's (and every look while `dlane.mode` is "off"): `evidence.holdout_line` as before, byte
          for byte (while the lane is off the line carries nothing more);
        - "S-C", the direction lane's: the same line at the lane's level (p <= 0.20) and Sharpe share (0.25 of
          Validation's);
        - "D2" (only behind `dlane.screen` "D2" with a receipt pinned in the repository's policy.json): P&L after fees above
          zero and D2's pooled entry-day t over Validation and the holdout (`dlane.d2_pooled_t`) at least the receipt's
          calibrated `c`; the bootstrap p and the tail are still reported.
        While the lane is on, every look's line records its `lane`, `screen` and `receipt` (also in its `detail`: the
        leakage alarm counts each lane's looks from it)."""
        if not dlane.on(self.settings):  # THE ROLLBACK: the release before it's line and record
            return evidence.holdout_line(result, validation_sharpe=validation_sharpe, previous_ps=previous, seed=seed)
        if screen.get("screen") == "S-C":
            line = evidence.holdout_line(result, validation_sharpe=validation_sharpe, previous_ps=previous, seed=seed,
                                         level=float(screen["look_level"]), sharpe_share=float(screen["sharpe_share"]))
        elif screen.get("screen") == "D2":
            base = evidence.holdout_line(result, validation_sharpe=validation_sharpe, previous_ps=previous, seed=seed)
            rows = self.store.version_runs(fid, int(n), window="validation", stress=1.0, limit=1)
            pooled = dlane.d2_pooled_t((rows[0].get("summary") or {}) if rows else None, result.get("summary"))
            c = screen.get("c")
            checks = {"status_ok": base["checks"]["status_ok"], "pnl": base["checks"]["pnl"],
                      "pooled": pooled is not None and c is not None and pooled >= float(c)}
            line = {**base, "passed": all(checks.values()), "checks": checks,
                    "numbers": {**base["numbers"], "rule": "D2", "pooled_t": pooled, "c": c}}
        else:
            line = evidence.holdout_line(result, validation_sharpe=validation_sharpe, previous_ps=previous, seed=seed)
        return {**line, "lane": screen.get("lane"), "screen": screen.get("screen"), "receipt": screen.get("receipt")}

    # ------------------------------------------------------------------ the nightly forward
    def _current_forward_version(self, fam: Mapping[str, Any]) -> bool:
        """Never mix a pre-upgrade band's forward record with decisions under new semantics."""
        if not callable(getattr(self.pool, "bundle", None)):
            return True  # identity-less synthetic pools; production always ships a named bundle
        from .bands import current_banded_evaluator

        state = fam.get("state") or {}
        version = self.store.version(fam["id"], state.get("banded_version"))
        return version is not None and current_banded_evaluator(state, run_sha(version))

    def forward_target(self) -> dict[str, str] | None:
        ready = self.settings.get("forward", {}).get("ready") or {}
        if ready.get("day") and ready.get("gate_checkpoint") == self.settings.get("gym", {}).get("gate_checkpoint"):
            target = {"day": ready["day"], "checkpoint": ready["gate_checkpoint"]}
            bundle = self.pool.bundle() if callable(getattr(self.pool, "bundle", None)) else None
            if bundle is not None:
                target["bundle"] = bundle
            return target
        return None

    def forward_pending(self, target: Mapping[str, Any]) -> list[dict[str, Any]]:
        return [f for f in self.store.families(alive=True) if f["band"] in ("candidate", "probe", "sized")
                and self._current_forward_version(f)
                and (f.get("state") or {}).get("forward_replay") !=
                {"target": target, "version": (f.get("state") or {}).get("banded_version") or f.get("best_version")}]

    def forward_due(self) -> bool:
        now = self.clock()
        target = self.forward_target()
        if target is not None:
            attempt = self.store.get("forward_attempt") or {}
            return bool(self.forward_pending(target)) and (attempt.get("target") != target or
                   now - float(attempt.get("at") or 0) >= float(self.settings.get("forward", {}).get("every_seconds", 3600)))
        today = dt.datetime.fromtimestamp(now, dt.timezone.utc)
        after = int(self.settings.get("forward", {}).get("after_hour_utc", 7))
        attempted = self.store.get("forward_legacy_attempt") or {}
        banded = any(f["band"] in ("candidate", "probe", "sized") and self._current_forward_version(f)
                     for f in self.store.families(alive=True))
        return bool(banded and self.settings.get("gym", {}).get("gate_checkpoint")) and today.hour >= after and \
            self.store.get("forward_day") != today.date().isoformat() and (attempted.get("day") != today.date().isoformat() or
            now - float(attempted.get("at") or 0) >= float(self.settings.get("forward", {}).get("every_seconds", 3600)))

    def forward(self) -> dict[str, Any]:
        target = self.forward_target()
        if target is not None:
            return self.forward_ready(target)
        now = self.clock()
        today = dt.datetime.fromtimestamp(now, dt.timezone.utc).date().isoformat()
        self.store.put("forward_legacy_attempt", {"day": today, "at": now})
        banded = [f for f in self.store.families(alive=True) if f["band"] in ("candidate", "probe", "sized")
                  and self._current_forward_version(f)]
        out: dict[str, Any] = {"families": len(banded), "trades": 0, "moves": []}
        if not banded or not self.settings.get("gym", {}).get("gate_checkpoint"):
            return out
        jobs = []
        for fam in banded:
            n = (fam.get("state") or {}).get("banded_version") or fam.get("best_version")
            version = self.store.version(fam["id"], n)
            if version is None or not version.get("code"):
                out.setdefault("failed", []).append(fam["id"])
                continue
            job = GymJob(family=fam["id"], version=int(n), code=version["code"], params=version.get("params") or {}, window="forward",
                         roots=tuple(fam["roots"]), gate="nightly forward replay", purpose="forward", priority=5.0)
            jobs.append((fam, int(n), self.pool.submit(job)))
        for fam, n, job in jobs:
            try:
                result = self.pool.wait(job, settings_mod.run_timeout(self.settings) + 600,
                                        late=lambda r, fid=fam["id"], n=n: self.record_forward(fid, n, r))
            except PoolError as exc:
                out.setdefault("errors", {})[fam["id"]] = str(exc)[:200]
                continue
            added = self.record_forward(fam["id"], n, result)
            if added is None:
                out.setdefault("failed", []).append(fam["id"])
            else:
                out["trades"] += added
        for fam in banded:
            move = self.judge_forward(fam["id"])
            if move:
                out["moves"].append(move)
        if jobs and not out.get("failed") and not out.get("errors"):
            self.store.put("forward_day", today)
        self.store.event("swarm.gate", None, {"action": "forward", **out})
        return out

    def forward_ready(self, target: Mapping[str, Any]) -> dict[str, Any]:
        """Replay a delivered checkpoint, retrying only families whose version has not finished it successfully."""
        self.store.put("forward_attempt", {"target": target, "at": self.clock()})
        families = self.forward_pending(target)
        out: dict[str, Any] = {"families": len(families), "trades": 0, "moves": [], "target": target}
        roots = set((self.settings.get("forward", {}).get("ready") or {}).get("roots") or [])
        jobs = []
        for fam in families:
            n = (fam.get("state") or {}).get("banded_version") or fam.get("best_version")
            version = self.store.version(fam["id"], n)
            if version is None or not version.get("code") or not set(fam["roots"]).issubset(roots):
                out.setdefault("failed", []).append(fam["id"])
                continue
            job = GymJob(family=fam["id"], version=int(n), code=version["code"], params=version.get("params") or {},
                         window="forward", roots=tuple(fam["roots"]), end=target["day"], gate="nightly forward replay",
                         purpose="forward", priority=5.0)
            jobs.append((fam["id"], int(n), self.pool.submit(job)))
        for fid, n, job in jobs:
            try:
                result = self.pool.wait(job, settings_mod.run_timeout(self.settings) + 600,
                                        late=lambda r, fid=fid, n=n: self.record_ready_forward(fid, n, r, target))
            except PoolError as exc:
                out.setdefault("errors", {})[fid] = str(exc)[:200]
                continue
            added = self.record_ready_forward(fid, n, result, target, judge=False)
            if added is None:
                out.setdefault("failed", []).append(fid)
            else:
                out["trades"] += added
            move = self.judge_forward(fid)
            if move:
                out["moves"].append(move)
        self.store.event("swarm.gate", None, {"action": "forward", **out})
        return out

    def record_ready_forward(self, fid: str, n: int, result: Mapping[str, Any], target: Mapping[str, Any], *,
                             judge: bool = True) -> int | None:
        self.store.add_run(fid, n, result, window="forward", stress=1.0, purpose="forward")
        days = {str(row[0]) for row in result.get("daily") or [] if row}
        if target != self.forward_target() or result.get("gym_image") != target["checkpoint"] or \
                result.get("gym_bundle") != target.get("bundle") or target["day"] not in days:
            self.store.event("swarm.gate", fid, {"action": "forward_failed", "version": n,
                                                 "why": "the replay does not cover the ready checkpoint and day"})
            return None
        added = self.record_forward(fid, n, result, record=False)
        if added is not None:
            self.store.set_state(fid, forward_replay={"target": target, "version": n})
            if not self.forward_pending(target):
                self.store.put("forward_day", target["day"])
                self.store.put("forward_completed", {"target": target, "at": self.clock()})
            if judge:
                self.judge_forward(fid)
        return added

    def record_forward(self, fid: str, n: int, result: Mapping[str, Any], *, record: bool = True) -> int | None:
        """A nightly replay's run (a trial) and, ONLY when it ran cleanly, its trades as version n's nightly record (the
        latest good run replaces that version's nightly record: every forward day is rerun each night). A replay that
        erred, found no data or was disqualified leaves the record as it was (None, and a `forward_failed` event)."""
        if record:
            self.store.add_run(fid, n, result, window="forward", stress=1.0, purpose="forward")
        fam = self.store.family(fid)
        has_bundle = callable(getattr(self.pool, "bundle", None))
        if has_bundle and (fam is None or (fam.get("state") or {}).get("banded_version") != n or
                           not self._current_forward_version(fam) or result.get("gym_bundle") != self.pool.bundle()):
            self.store.event("swarm.gate", fid, {"action": "forward_failed", "version": n,
                                                 "why": "the replay or qualified band uses another evaluator"})
            return None
        if result.get("status") != "ok":
            self.store.event("swarm.gate", fid, {"action": "forward_failed", "version": n, "status": result.get("status")})
            return None
        # The forward view carries each trade's day, P&L and maximum loss (no ids): a trade is (version, day, its place
        # that day).
        trades, seen = [], {}
        for t in result.get("trades") or []:
            if t.get("pnl") is None:
                continue
            k = seen[t.get("day")] = seen.get(t.get("day"), -1) + 1
            trades.append({"id": f"v{n}:{t.get('day')}:{k}", "day": t.get("day"), "pnl": t.get("pnl"), "max_loss": t.get("max_loss")})
        return self.store.replace_forward(fid, "nightly", trades, version=n)

    def judge_forward(self, fid: str) -> dict[str, Any] | None:
        """The banded version's forward record (`evidence.forward_record`: its own rows, one source a day); a Candidate
        whose record is negative goes back to the Gym, and its version is never tuition again."""
        with self.store.atomic():
            return self._judge_forward(fid)

    def _judge_forward(self, fid: str) -> dict[str, Any] | None:
        fam = self.store.family(fid)
        if fam is None or fam["band"] not in ("candidate", "probe", "sized"):
            return None
        state = fam.get("state") or {}
        n = state.get("banded_version")
        record = evidence.forward_record(self.store.forward(fid), version=n)
        self.store.set_state(fid, forward=record)
        if record["negative"] and fam["band"] == "candidate":
            if self.store.set_band(fid, "gym", reason=f"its forward record turned negative over {record['trades']} trades") is None:
                return None
            # Back in the Gym, its dormancy clause starts afresh (`researcher.dormant_count`): holding while its forward
            # record was measured was honest, and must not count against it now.
            self.store.set_state(fid, dormant_cycles=0)
            if state.get("banded_sha"):
                version = self.store.version(fid, n)
                if version is not None:
                    self.outcome(fid, run_sha(version), "demoted")
            return {"family": fid, "to": "gym"}
        return None


__all__ = ["Gate", "run_sha", "incubator_stage", "REVIEW", "DUPLICATE_STAGE", "VALIDATION_IDENTITY", "validation_identity",
           "duplicate_words", "HOLD_DRIFT_STAGE", "HOLD_POWER_STAGE", "HOLD_WORDS", "HOLD_OUTCOME", "look_hold_settings",
           "holdout_sessions", "sessions_between", "reader", "same_reader"]
