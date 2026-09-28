"""The inner loop: one researcher per family, revise -> run -> read -> revise.

A CYCLE is at most one Gym run and a few model calls, bounded by `max_model_calls`, `max_tool_calls`
and `cycle_seconds` (the target is under three minutes). In the steady state a cycle is: run the program
the researcher asked for at the end of its last cycle (a `gym_run` carried over), show it the result, let
it read, write its notebook and revise, and carry its next `gym_run` to the next cycle. A family's very
first cycle runs its starter program without a model call (seeds only).

THE TOOLS (`TOOLS`): `gym_run` (a new version on Train; its compact diagnostic), `gym_sweep` (many PARAMS variants of
one program on Train at once; a table sorted by the Train score), `read_run` (a section of a past Train run), `notebook`
(append / read: its memory), `graveyard` (lessons of retired families), `submit` (make an eligible version its best: the
tournament validates it), `retire` (explicitly abandon the entire Gym family). The contract (`league/CONTRACT.md`) is the
shared, cached prefix of every call; each family's calls carry its own `prompt_cache_key`.

SWEEPS (R3, Sept 27: every Train edge of the sprint's weekend came from the operator's sweeps, many variants of one
program at once, never from one run a cycle). `gym_sweep` takes the place of the cycle's one `gym_run` (one run OR one
sweep a cycle; a second is queued for the next cycle like a second run). Its variants (2 to `max_sweep_variants`, each
key in the program's PARAMS and of its default's type) are queued on the pool together as one `group`, so they share
batches and never supersede one another, and waited for under gym_run's timeout. Each variant is a version of its own
(the tournament, the gate and the live path read a version's params; `SwarmStore.add_versions` stores the code once
and counts the whole sweep as ONE revision) and its own Train run (its params in the run's summary), and every variant
the Gym evaluates is a trial, exactly as a gym_run's. A variant that fails costs the others nothing. The table the
researcher reads is sorted by the Train score (a version demoted at 1.5x ranks with the ineligible ones): its best
eligible variant can become the family's best (robustness runs follow as for a gym_run), and any row's run_id can be
submitted or read (the sweep's rows keep their full results until the family's next run). `sweep_enabled` false takes
the tool away.

SWEEP LOAD (the review of PR #396: the pool had no spare boxes; a strict priority queue lets one family's group go
first and the lowest-weight families' variants time out). Two limits: `max_sweep_variants` (6) a sweep, and
`max_sweep_jobs_in_flight` (24) the variants of every sweep this process has in flight together; a sweep that would pass
it is refused (a plain refusal, no backoff) and the status says to use gym_run. The tool stays offered either way (the
tool list is part of the cached prefix). Repeats are dropped by the MERGED params (`{}` and a default spelled out are
one program). Each variant is recorded as it lands and only its compact row is kept. A sweep's group id is its content
(family, code, variants, roots, the Gym's image and engine), so the same sweep asked again (a queued sweep's quiet retry
after the Gym gave up) reads back the variants that landed late instead of running them twice.

NO DUPLICATE RUNS (R3, the harness audit of Sept 28: 44% of cycles were waste and 45% of trials identical re-runs, each
one still a trial, and every REVISE turn had to call a run). A run the family already evaluated (the same program, its
MERGED params, the stress, window and roots, the Gym's image and engine, and the Train split and capital: `eval_key`,
kept on its run's row) is answered from the store (`SwarmStore.evaluated`): the same compact view, marked `already_run:
"the stored result"`, with no Gym job, no trial, no version and no revision. So is every sweep variant already
evaluated. A stored result is no completed run: the cycle's REVISE turn goes on (the researcher changes something or
holds) and a real run may still follow in the same cycle. Only a completed ("ok") run is stored; a failed one runs again,
and so does one on another fill model than the Gym's latest, or one that can no longer be scored (`_reusable`). A run
that lands after the wait gave up is recorded with its Train score, so asked for again it is scored like any run.
`researcher.reuse_results` false turns this off. HOLD: a REVISE turn may call `gym_run` with `hold` true when the
researcher has nothing new: no job, no trial, a line in its notebook (its `note` only), and the cycle ends (a run call
after it in the same answer is refused). Code or params passed beside hold=true are ignored: it is still a hold.

DORMANCY (the audit's critique: stored results and holds would let a dead family hide forever, since the idle rule
counts Gym evaluations and the tournament's clocks count revisions and trials). A Gym family's cycle with stored
results, holds or runs refused for its own doing (`_refusal`) and no new evaluation adds one to its `dormant_cycles`
(its state). A new evaluation (a trial of its own Train run or sweep variant, in the cycle or landed late) sets it to
zero as soon as it is recorded, and so does a counted validation. A cycle that asked the Gym for a new evaluation the
Gym did not make (a Gym error; a run, or every new variant of a sweep, that did not land) leaves it, and so does any
other cycle (a sweep refused for room alone, a model error). Outside the Gym band the count is zero, and a family sent
back to the Gym starts afresh. A family whose last `researcher.dormant_cycles` (40) cycles were dormant is dead for the
idle rule (`idle_dead`: the same floor, gate exemption and graveyard wording), unless its best awaits validation
(`awaiting_validation`: holding while the tournament validates it is honest).

RETIRE (Sept 26: an unguarded `retire` on the REVISE turn took the population from 49 to 16 in 24 minutes). A REVISE
turn offers `gym_run` and `gym_sweep` alone: a REVISE always revises. A READ turn offers `retire` only while more
families live than `population.start` and the family has had at least two validations, or, by THE IDLE RULE (R3, Sept
27: with the population held at its start, dead families never qualified and looped on placeholder runs), while more
live than `population.floor` and the family is dead (`idle_dead`: `researcher.retire_idle_evaluations` Gym evaluations
since its birth or last validation without an eligible Train version, or three times as many with its best Train score
below zero, or `researcher.dormant_cycles` dormant cycles in a row; never while a validated version awaits the gate)
(`can_retire`). Never while the operator holds its validated version at the gate (`held_at_gate`): no rule retires
such a family. A retire that is refused anyway is a plain refusal, never a cycle error (an error backs the family off
for up to 30 minutes). The tournament retires a dead family that never calls retire by the same rule; the architect
refills below the start.

WHAT IT SEES. Train in full; of Validation only pass or fail and how many of the line's checks passed (the owner's
decision D2a, `diagnostics.validation_view`); of the holdout only the gate's pass or fail. Never a date in ctx (the
Gym enforces it; the safety check refuses date literals before a program reaches the Gym).

THE BEST (the robust Train objective, Sept 26): `evidence.train_score`, the worst Train year's daily t times the
share of Train quarters positive, and a version is eligible only with 40 trades on 20 days in every Train year. A new
best (and a submitted version) queues two ROBUSTNESS runs of it on Train (1.5x the half-spread and the mid) at the pool's
lowest priority; they come back into the family's status, count as trials, and a version that loses at 1.5x is never
the best again (`robust_failed`; the next eligible candidate takes its place; one already validated leaves the gate's
queue with the gate outcome "demoted"). The tournament validates a version only once its 1.5x run landed with a profit. `migrate_objective` chose every living family's best
anew under this score once, keeping the old selection in `legacy_best`.

ROOTS. A family holds one to five roots of the admitted list (`gym.roots`). A program whose NEEDS names other
admitted roots changes the family's roots (a Gym family only); its validation and holdout runs use the version's own
NEEDS roots (`needs_roots`).

THE TOP TEN. The bandit's top `top_families` by weight run their cycles on `top_profile` (V4-Pro asap) at
`top_reasoning_effort` (low); the others on `profile`. The swarm's hourly pace governs every cycle alike.

STALLS. Five revisions without a better Train score (`evidence.train_score`) buy ONE rewrite from a stronger
model (DeepSeek-V4-Pro balanced; Kimi-K3 balanced for the top ten families by the bandit's share), asked
in the background (a cycle never waits for it) and run as the family's next cycle's Gym run; at most
`rewrites_per_day` a family, `rewrite_min_hours` apart; then the counter starts again.

Every cycle is a `swarm.cycle` event; a notebook entry becomes a public `swarm.note` (the site's tape,
masked there for quotes) at most every `note_every_cycles` cycles. Standard library only.
"""

from __future__ import annotations

import ast
import hashlib
import json
import math
import re
import threading
import time
from pathlib import Path
from typing import Any, Callable, Mapping

from . import diagnostics, evidence, public
from .pool import ROBUSTNESS_PRIORITY, GymJob, PoolError
from .store import SwarmStore

CONTRACT = Path(__file__).resolve().parents[1] / "CONTRACT.md"

#: The tools that run the Gym: one of them a cycle (a second call opens the next cycle).
RUNS = ("gym_run", "gym_sweep")
#: A sweep's variants unless `researcher.max_sweep_variants` says otherwise.
MAX_SWEEP_VARIANTS = 6
#: The variants of every sweep in flight together unless `researcher.max_sweep_jobs_in_flight` says otherwise.
MAX_SWEEP_JOBS_IN_FLIGHT = 24


def sweep_tool(limit: int = MAX_SWEEP_VARIANTS) -> dict[str, Any]:
    """The `gym_sweep` tool, its limit in words (`researcher.max_sweep_variants`)."""
    return {
        "name": "gym_sweep",
        "description": "Run several PARAMS variants of ONE program on the Train window at once (the Gym batches them) and get a "
                       "compact table sorted by the Train score: per variant its params, trades, days, per-year daily t and "
                       "trades, P&L, fill rate, eligibility, Train score and run_id (submit a row's run_id, or read_run it before "
                       "your next run). It takes the place of gym_run: one run OR one sweep a cycle; when the Gym is full of "
                       "other sweeps it is refused (your status says so): run gym_run then. Every variant is a trial counted "
                       "against your lineage; the sweep is one revision. Sweep a small grid around your current program, include a placebo "
                       "row (your signal switched off or inverted), prefer a plateau of positive neighbours to a lone peak, then "
                       "submit the best robust row.",
        "parameters": {"type": "object", "properties": {
            "code": {"type": "string", "description": "the complete program: NEEDS, PARAMS, decide(ctx) (omit it to sweep your "
                                                      "latest version's code)"},
            "params": {"type": "object", "description": "optional: PARAMS overrides every variant starts from (a variant's own "
                                                        "keys win); nothing else carries over from an earlier version"},
            "variants": {"type": "array", "items": {"type": "object"},
                         "description": f"2 to {int(limit)} objects, one a variant: its PARAMS overrides (keys must exist in "
                                        "PARAMS and keep their default's type; {} is the program as written)"},
            "why": {"type": "string", "description": "one sentence: what the grid tests and why it should help"},
            "note": {"type": "string", "description": "optional: what you learned from your last run, appended to your notebook. "
                                                      "PUBLIC: it may appear on the public site, so describe the mechanism and "
                                                      "your reasoning only, never a threshold, level, delta, ratio or any other "
                                                      "fitted value (in digits or in words)"}},
            "required": ["variants"]}}


TOOLS: list[dict[str, Any]] = [
    {"name": "gym_run", "description": "Run a version of your program on the Train window in the Gym and get its compact "
                                       "diagnostic. `code` is the whole program file (omit it to rerun your latest version, e.g. "
                                       "with other params). One run (or one gym_sweep) per cycle: a second call runs at the start "
                                       "of your next cycle. A program and params your family already ran (same stress, roots and "
                                       "Gym) are not run again: you get the stored result (already_run), no trial; change "
                                       "something. With nothing new to run, call it with hold=true and no code or params: no run, "
                                       "no trial, your note goes to your notebook. Many cycles in a row of holds and stored "
                                       "results count against your family under the idle rule.",
     "parameters": {"type": "object", "properties": {
         "code": {"type": "string", "description": "the complete program: NEEDS, PARAMS, decide(ctx)"},
         "params": {"type": "object", "description": "PARAMS overrides for this run (keys must exist in PARAMS)"},
         "stress": {"type": "number", "description": "half-spread multiplier, 1.0 (default) or 1.5 (the gate's stress)"},
         "hold": {"type": "boolean", "description": "true, with no code and no params: skip this cycle honestly because you "
                                                    "have nothing new to run (say why in `note`)"},
         "why": {"type": "string", "description": "one sentence: what this version changes and why it should help"},
         "note": {"type": "string", "description": "optional: what you learned from your last run, appended to your notebook. "
                                                   "PUBLIC: it may appear on the public site, so describe the mechanism and "
                                                   "your reasoning only, never a threshold, level, delta, ratio or any other "
                                                   "fitted value (in digits or in words)"}}}},
    sweep_tool(),
    {"name": "read_run", "description": "Read one section of a past Train run of your family.",
     "parameters": {"type": "object", "properties": {
         "run_id": {"type": "string"},
         "section": {"type": "string", "description": "summary, fills, runtime, worst, trades, daily, or breakdown.<weekday|"
                                                      "time_of_day|dte|rv_tercile|iv_tercile|quarter|type|root|exit_reason>"},
         "page": {"type": "integer"}}, "required": ["run_id", "section"]}},
    {"name": "notebook", "description": "Your memory across cycles: append what you learned, or read your recent entries. "
                                        "PUBLIC: an entry may appear on the public site, so write the mechanism and your "
                                        "reasoning only, never a threshold, level, delta, ratio or other fitted value.",
     "parameters": {"type": "object", "properties": {
         "action": {"type": "string", "enum": ["append", "read"]},
         "text": {"type": "string", "description": "for append: a few plain sentences in your own words"}}, "required": ["action"]}},
    {"name": "graveyard", "description": "Search the lessons of retired families (what failed and why).",
     "parameters": {"type": "object", "properties": {"query": {"type": "string"}}}},
    {"name": "submit", "description": "Make the version behind one of your Train runs your family's best: the hourly tournament "
                                      "runs your best on Validation and, if it meets the line, sends it to the gate. Only a run "
                                      "eligible under the Train score (40 trades on 20 days in every Train year) at the normal "
                                      "spread qualifies, and never a version that lost money at 1.5x the half-spread.",
     "parameters": {"type": "object", "properties": {"run_id": {"type": "string"}, "note": {"type": "string"}},
                    "required": ["run_id"]}},
    {"name": "retire", "description": "End research on your entire Gym family when you abandon its mechanism, not merely "
                                     "its latest version. This is final: best programs, evidence and trial counts remain; "
                                     "no further runs or tools start. Offered only while the population is above its start "
                                     "and your family has had at least two validations, or once your family has spent many "
                                     "Gym evaluations since its birth or last validation without an eligible Train version "
                                     "(or far more with a best Train score below zero), or many cycles in a row with only "
                                     "holds and stored results.",
     "parameters": {"type": "object", "properties": {"reason": {"type": "string", "description": "Why the entire mechanism "
                    "is abandoned; retained in the private notebook and graveyard."}}, "required": ["reason"]}},
]

#: A REVISE turn requires a run or a sweep (a REVISE always revises: `retire` is never offered there); a missing call
#: fails and uses the normal backoff.
TOOLS_REVISE: list[dict[str, Any]] = [t for t in TOOLS if t["name"] in RUNS]
#: A READ turn without `retire` (the family may not retire now: `Researcher.can_retire`).
TOOLS_READ: list[dict[str, Any]] = TOOLS[:-1]

ROLE = """You are a researcher in the LTCM options swarm. You own one family and improve its program in the Gym.
Work in short cycles. REVISE: call gym_run with your revised program (the whole file in `code`, or only `params` to
change parameters) and put what you learned from the last run in its `note`, or call gym_sweep to run a small grid of
PARAMS variants of one program at once (one run OR one sweep a cycle). A REVISE always revises: never repeat an
empty or unchanged program. A program and params your family already ran are never run again: you get the stored
result, marked already_run, and no trial. When you have nothing new to try, call gym_run with hold=true (no code, no
params) and say why in its note: an honest skip, better than a placeholder run. A family whose cycles only hold or
repeat for many cycles in a row is dead under the idle rule. READ: when the result comes back, read it; submit the run
if it is your best; queue your next gym_run or gym_sweep (it opens your next cycle); use read_run, graveyard or the
notebook only when the diagnostic leaves you unsure. Keep every program inside the contract below; the Gym refuses anything else. Reply with tool calls;
keep prose short.
SWEEPS found every Train edge so far. Sweep a small grid around your current program (the program as written, {}, and a
step either side of the parameters that matter), include a placebo row (your signal switched off or inverted: it should
lose; if it earns as much, the edge is not your signal), and read the table as a surface: prefer a plateau, where most
neighbours are positive and eligible, to a lone peak, which is luck. Then submit the best robust row's run_id. Every
variant is a trial counted against your lineage: sweep to test one idea's robustness, never to grind for a lucky cell.
THE TRAIN SCORE you climb is your WORST Train year's daily t, times the share of Train quarters that were positive. A
version counts only with at least 40 trades on at least 20 days in EVERY Train year, and never if it loses money at 1.5x
the half-spread (the Gym re-runs each new best at 1.5x and at the mid; the results come back in your status). Seek a
mechanism that earns in every year, not a filter that shines in one.
Your family trades one to five of the Gym's roots; to change them, name the new roots in your program's NEEDS.
The retire tool appears only while the population is above its start and your family has had at least two
validations, or once your family has spent many Gym evaluations since its birth or last validation without an eligible
Train version (or far more with a best Train score below zero), or many cycles in a row with only holds and stored
results. Call it only when you abandon the entire mechanism, not one rejected version; a dead mechanism is better
retired than kept on holds, since its slot goes to a new idea. Retirement is final for the family and preserves its best
program and all evidence.
Your notes (the notebook and gym_run's note) are PUBLIC: they may appear on the public site. Write the mechanism and your
reasoning there, never a threshold, level, delta, ratio, date or any other fitted value, in digits or in words; the
numbers belong in your program and in the diagnostics, which stay private.

THE CONTRACT (league/CONTRACT.md)

"""

CODE_BLOCK = re.compile(r"```(?:python)?\s*\n(.*?)```", re.S)
_YEAR_TEXT = re.compile(r"(?<![0-9])(?:19|20)[0-9]{2}[-/.][01]?[0-9][-/.][0-3]?[0-9](?![0-9])|(?<![0-9])20(?:19|2[0-9]|30)(?![0-9])")


def date_like(value: Any) -> bool:
    """The Gym's date rule (league/gym/safety.py) applied to a parameter override: a number from 2019 to 2030 (a year), a
    YYYYMMDD integer, or a string holding a year or an ISO date; lists are checked element by element."""
    if isinstance(value, bool) or value is None:
        return False
    if isinstance(value, (list, tuple)):
        return any(date_like(v) for v in value)
    if isinstance(value, str):
        return bool(_YEAR_TEXT.search(value))
    if isinstance(value, (int, float)):
        if 2019 <= value <= 2030:
            return True
        if float(value).is_integer() and 19_000_101 <= value <= 20_301_231:
            v = int(value)
            return 1 <= (v // 100) % 100 <= 12 and 1 <= v % 100 <= 31
    return False


def _round(value: Any, places: int) -> Any:
    """A finite number rounded (None for anything else): a sweep's table stays compact and valid JSON."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return round(float(value), places) if math.isfinite(float(value)) else None


def needs_of(code: str) -> dict[str, Any] | None:
    """The program's NEEDS literal, without running it (None when absent or not a literal)."""
    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError):
        return None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "NEEDS" for t in node.targets):
            try:
                value = ast.literal_eval(node.value)
            except (ValueError, SyntaxError):
                return None
            return value if isinstance(value, dict) else None
    return None


def needs_roots(code: Any, fallback: Any = ()) -> tuple[str, ...]:
    """The roots a program's NEEDS names (upper case, in order, once each), else `fallback`: the universe its validation
    and holdout runs use (the Gym trades a program's NEEDS roots within the run's roots)."""
    needs = needs_of(str(code or "")) or {}
    roots = needs.get("roots")
    roots = [roots] if isinstance(roots, str) else roots
    if isinstance(roots, (list, tuple)):
        out = tuple(dict.fromkeys(str(r).strip().upper() for r in roots if str(r).strip()))
        if out:
            return out
    return tuple(fallback or ())


def with_roots(code: str, roots: list[str]) -> str | None:
    """`code` with its NEEDS literal's roots set to `roots` (a fork's first version on the parent's roots plus one);
    None when NEEDS is not a literal dict at the top level."""
    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError):
        return None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "NEEDS" for t in node.targets):
            try:
                value = ast.literal_eval(node.value)
            except (ValueError, SyntaxError):
                return None
            if not isinstance(value, dict) or node.value.end_lineno is None or node.value.end_col_offset is None:
                return None
            value["roots"] = list(roots)
            lines = code.splitlines(keepends=True)
            start = sum(len(x) for x in lines[:node.value.lineno - 1]) + len(lines[node.value.lineno - 1].encode("utf-8")[:node.value.col_offset].decode("utf-8"))
            end = sum(len(x) for x in lines[:node.value.end_lineno - 1]) + len(lines[node.value.end_lineno - 1].encode("utf-8")[:node.value.end_col_offset].decode("utf-8"))
            return code[:start] + repr(value) + code[end:]
    return None


def check_code(code: str) -> str | None:
    """Why the Gym would refuse `code` before running it (None when admissible). The Gym's own check when it
    is importable here; the box checks again either way."""
    try:
        from ..gym.safety import check_program
    except ImportError:  # the Gym not on this tree yet: the box's check is the wall
        try:
            ast.parse(code)
        except SyntaxError as exc:
            return f"the program does not compile: {exc}"
        return None
    try:
        check_program(code)
    except Exception as exc:  # noqa: BLE001 - CodeRefused and friends
        return str(exc)
    return None


def params_of(code: str) -> dict[str, Any] | None:
    """The program's PARAMS literal, without running it (None when absent or not a literal dict)."""
    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError):
        return None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "PARAMS" for t in node.targets):
            try:
                value = ast.literal_eval(node.value)
            except (ValueError, SyntaxError):
                return None
            return value if isinstance(value, dict) else None
    return None


def check_params(defaults: Mapping[str, Any], overrides: Mapping[str, Any]) -> str | None:
    """Why the Gym would refuse these PARAMS overrides (None when it would not): the Gym's own rule when it is importable
    here (every key in PARAMS, a value of its default's type), else the keys alone."""
    try:
        from ..gym.runtime import merge_params
    except ImportError:  # the Gym not on this tree: the box checks the types
        unknown = [k for k in overrides if k not in defaults]
        return f"parameter {unknown[0]!r} is not in the program's PARAMS" if unknown else None
    try:
        merge_params(defaults, overrides)
    except Exception as exc:  # noqa: BLE001 - NeedsRefused and friends
        return str(exc)[:300]
    return None


def merged_key(defaults: Mapping[str, Any], overrides: Mapping[str, Any]) -> str:
    """The program's whole PARAMS under these overrides, canonical: what the Gym runs (its run_id hashes the merged params),
    so `{}` and a default spelled out are one program. Call it after `check_params` accepted the overrides."""
    try:
        from ..gym.runtime import merge_params
        merged = merge_params(defaults, overrides)
    except Exception:  # noqa: BLE001 - the Gym not on this tree (the keys were checked): a plain merge
        merged = {**defaults, **overrides}
    return json.dumps(merged, sort_keys=True, separators=(",", ":"), default=str)


def sweep_variants(code: str, variants: Any, base: Any = None, *, limit: int = MAX_SWEEP_VARIANTS
                   ) -> tuple[list[dict[str, Any]], int, str | None]:
    """A sweep's variants as whole PARAMS overrides (`base`, then each variant's own keys), in order, a repeat (the same
    merged PARAMS: `merged_key`) dropped: (variants, how many were dropped, why the sweep is refused or None). 2 to
    `limit` variants; every key in the program's PARAMS literal with its default's type (`check_params`); never a date
    or a year (`date_like`)."""
    if base is None:
        base = {}
    if not isinstance(base, dict):
        return [], 0, "`params` must be an object of PARAMS overrides"
    if not isinstance(variants, list) or not all(isinstance(v, dict) for v in variants):
        return [], 0, "`variants` must be a list of objects, each one variant's PARAMS overrides"
    if len(variants) < 2:
        return [], 0, "a sweep needs at least 2 variants (one variant is a gym_run)"
    if len(variants) > limit:
        return [], 0, f"a sweep runs at most {limit} variants; this one has {len(variants)}"
    defaults = params_of(code)
    if defaults is None:
        return [], 0, "gym_sweep needs the program's PARAMS as a literal dict at the top level (its keys are what a variant sets)"
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    dropped = 0
    for i, variant in enumerate(variants, 1):
        params = {**base, **variant}
        dated = [k for k, v in params.items() if date_like(v)]
        if dated:
            return [], 0, (f"variant {i}: a date or a year in the parameter overrides ({', '.join(map(str, dated))}): no program "
                           "may see the calendar")
        why = check_params(defaults, params)
        if why:
            return [], 0, f"variant {i}: {why}"
        key = merged_key(defaults, params)  # a repeat is the same PROGRAM (merged PARAMS), not the same overrides
        if key in seen:
            dropped += 1
            continue
        seen.add(key)
        out.append(params)
    if len(out) < 2:
        return [], dropped, "fewer than 2 distinct variants: a sweep needs at least two different programs (one is a gym_run)"
    return out, dropped, None


def sanitize(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """History items the API accepts: messages, function calls with their outputs (no orphans), no reasoning."""
    calls = {i.get("call_id") for i in items if i.get("type") == "function_call"}
    outputs = {i.get("call_id") for i in items if i.get("type") == "function_call_output"}
    out = []
    for item in items:
        kind = item.get("type")
        if kind == "reasoning":
            continue
        if kind == "function_call" and item.get("call_id") not in outputs:
            continue
        if kind == "function_call_output" and item.get("call_id") not in calls:
            continue
        if kind == "function_call":
            item = {k: item[k] for k in ("type", "call_id", "name", "arguments") if k in item}
        out.append(item)
    return out


#: A family holds one to five roots of the admitted list (the Gym's NEEDS allows five).
MAX_ROOTS = 5
#: Eligible versions a family keeps as candidates for its best: the next takes the place of one that loses at 1.5x.
CANDIDATES = 5
#: Runs of one robustness label the Gym may execute and fail (an error, a timeout, a result that is not "ok") before it
#: is given up; a 1.5x run given up demotes its version like a loss. A job that never ran (superseded, cancelled) is no try.
ROBUSTNESS_ATTEMPTS = 3
#: Pool failures that mean the job never ran on a box (no attempt is charged for them).
NOT_RUN = ("superseded", "retired", "abandoned", "cancelled")


def landed(row: Any) -> bool:
    """A robustness figure the Gym completed ("ok"); a failed or unfinished run is retried (`queue_robustness`)."""
    return isinstance(row, Mapping) and row.get("status") == "ok"


def robust_at_stress(state: Mapping[str, Any], n: Any) -> bool | None:
    """Did version `n`'s 1.5x Train robustness run land with a profit? None while it has not landed."""
    if n is None:
        return None
    if int(n) in (state.get("robust_failed") or []):
        return False
    row = ((state.get("robustness") or {}).get(str(n)) or {}).get("stress_1.5")
    if not landed(row):
        return None
    pnl = row.get("pnl")
    return row.get("status") == "ok" and isinstance(pnl, (int, float)) and pnl > 0


def candidates_with(rows: Any, score: float, version: int, run_id: str) -> list[list[Any]]:
    """The family's candidates ([score, version, run_id], best first, at most `CANDIDATES`) with this eligible run: a
    version keeps its highest score."""
    rows = [list(r) for r in (rows or []) if isinstance(r, (list, tuple)) and len(r) == 3]
    same = [r for r in rows if int(r[1]) == int(version)]
    if same and float(same[0][0]) >= float(score):
        return rows
    rows = [r for r in rows if int(r[1]) != int(version)] + [[float(score), int(version), str(run_id)]]
    return sorted(rows, key=lambda r: (-float(r[0]), int(r[1])))[:CANDIDATES]


#: A queued run the Gym could not run for a passing reason (busy, restarting, superseded) is retried this many times
#: before the model hears why; any other Gym error goes to the model at once.
PENDING_RETRIES = 2
TRANSIENT = ("did not answer", "abandoned before it ran", "superseded")


def transient(error: str) -> bool:
    return any(t in error for t in TRANSIENT)


def completed_run(result: Mapping[str, Any]) -> bool:
    """A diagnostic worth a READ turn: the Gym completed and the store recorded its run."""
    return result.get("status") == "ok" and bool(result.get("run_id"))


def new_run(result: Any) -> bool:
    """A completed run the Gym made now: a stored result (`already_run`, NO DUPLICATE RUNS) is none, so the cycle's REVISE
    turn goes on after it."""
    return isinstance(result, Mapping) and completed_run(result) and not result.get("already_run")


#: The idle rule's default (`researcher.retire_idle_evaluations`): Gym evaluations (trials, `add_run`) since a family's birth
#: or last validation without an eligible Train version. Calibrated on the run's history (Sept 27): every family that
#: ever made an eligible version made its first within about a hundred Train runs of its birth, and a family makes
#: about seventeen runs an hour, so a newborn gets about nine hours.
RETIRE_IDLE_EVALUATIONS = 150

#: A best Train score below zero only says every eligible version so far lost in its worst Train year: a normal stage of
#: a family's ramp (Sept 27: families that later validated with the run's best results spent up to about 170 Train runs
#: there first). It counts as dead only after this many times the limit.
NEGATIVE_FACTOR = 3


#: The dormancy clause's default (`researcher.dormant_cycles`): cycles in a row with only stored results or holds and no new
#: Gym evaluation (DORMANCY in the module docstring). A holding cycle is one model call and no Gym run, so forty of them
#: pass in well under an hour of a family's cycles.
DORMANT_CYCLES = 40

#: What a stored result says (NO DUPLICATE RUNS): its view's `already_run`, and a sweep row's.
ALREADY_RUN = "the stored result"


def _count_setting(settings: Mapping[str, Any], name: str, default: int) -> int:
    """`researcher.<name>` as a count; 0 (off) when it is 0, null, negative, a boolean or not a finite number (a misread
    setting never retires anyone)."""
    raw = (settings.get("researcher") or {}).get(name, default)
    if raw is None or isinstance(raw, bool):
        return 0
    try:
        return max(0, int(raw))
    except (TypeError, ValueError, OverflowError):
        return 0


def idle_limit(settings: Mapping[str, Any]) -> int:
    """`researcher.retire_idle_evaluations`; 0 (off) when it is 0, null, negative, a boolean or not a number (a misread
    setting never retires anyone)."""
    return _count_setting(settings, "retire_idle_evaluations", RETIRE_IDLE_EVALUATIONS)


def dormant_limit(settings: Mapping[str, Any]) -> int:
    """`researcher.dormant_cycles`; 0 (off) when it is 0, null, negative, a boolean or not a number."""
    return _count_setting(settings, "dormant_cycles", DORMANT_CYCLES)


def dormant_count(fam: Mapping[str, Any]) -> int:
    """The family's dormant cycles in a row (its state's `dormant_cycles`; 0 when absent or not a count)."""
    raw = (fam.get("state") or {}).get("dormant_cycles")
    return max(0, int(raw)) if isinstance(raw, int) and not isinstance(raw, bool) else 0


def awaiting_validation(fam: Mapping[str, Any]) -> bool:
    """The family's best (submitted, else by Train score: the version the tournament validates next) has not been
    validated and has not lost at 1.5x the half-spread: the tournament validates it once its 1.5x robustness run lands with
    a profit. A researcher with nothing new may hold meanwhile without the dormancy clause counting it dead."""
    state = fam.get("state") or {}
    n = fam.get("best_version") or state.get("best_train_version")
    if not n or isinstance(n, bool):
        return False
    if fam.get("validated_version") is not None and int(fam["validated_version"]) == int(n):
        return False
    return robust_at_stress(state, n) is not False


def held_at_gate(fam: Mapping[str, Any]) -> bool:
    """The operator holds the family's validated version at the gate (`gate_hold` with `gate_ready`: `SwarmStore.hold_gate`).
    Such a family is never retired, by its researcher, the tournament's rules or the diagnostician (`SwarmStore.retire_gym`
    refuses it), so the look the operator is holding still happens once the hold is cleared."""
    state = fam.get("state") or {}
    return bool(state.get("gate_hold") and state.get("gate_ready"))


def holding(args: Any) -> bool:
    """A `gym_run` call that holds (`hold` true: NO DUPLICATE RUNS' HOLD)."""
    value = args.get("hold") if isinstance(args, Mapping) else None
    return value is True or (isinstance(value, str) and value.strip().lower() == "true")


def idle_evaluations(fam: Mapping[str, Any]) -> int:
    """Gym evaluations since the family's birth or last validation: its trials less those it had at its last counted
    validation (`validated_trials`, which the tournament's verdict records from R3 on), and never more than
    `since_val_trials` (evaluations since its validation last improved, or since its birth when it never validated: the
    only count a family validated before R3 has). Every evaluation counts (the store keeps one version for identical code
    and parameters, so revisions miss a family that loops a placeholder); an unchanged re-run is no evaluation since NO
    DUPLICATE RUNS answers it from the store, and the dormancy clause (`idle_dead`) counts those cycles instead."""
    since = int(fam.get("since_val_trials") or 0)
    mark = (fam.get("state") or {}).get("validated_trials")
    if isinstance(mark, int) and not isinstance(mark, bool):
        return max(0, min(since, int(fam.get("trials") or 0) - mark))
    return since


def idle_dead(fam: Mapping[str, Any], settings: Mapping[str, Any]) -> str | None:
    """THE IDLE RULE (R3, Sept 27). A living Gym family is dead when it has spent `researcher.retire_idle_evaluations`
    Gym evaluations since its birth or last validation (`idle_evaluations`) without an eligible Train version (no
    `best_train`: none met 40 trades on 20 days in every Train year, or every one lost at 1.5x), or `NEGATIVE_FACTOR`
    times as many with its best Train score below zero. Never while a validated version awaits the gate (`gate_ready`)
    or a holdout look is out (`look_inflight`). Returns a clause saying which ("made no eligible Train version in 157 Gym
    evaluations since its birth"), or None. A dead family may retire at `population.start` (only `population.floor`
    holds it); the tournament retires one that does not. Train figures only: nothing Validation or the holdout measured
    (D2). It is a time limit, not a finding that the mechanism has no edge.

    DORMANCY (R3, NO DUPLICATE RUNS): a family is dead too, whatever its best, when its last `researcher.dormant_cycles`
    cycles in a row made no new Gym evaluation, only stored results, holds and refused runs (`dormant_count`, counted in
    the Gym band only), unless its best awaits validation (`awaiting_validation`). The same exemptions, floor and wording
    as above."""
    limit, dormant = idle_limit(settings), dormant_limit(settings)
    if (limit <= 0 and dormant <= 0) or fam.get("band") != "gym" or fam.get("retired_at"):
        return None
    state = fam.get("state") or {}
    if state.get("gate_ready") or state.get("look_inflight"):
        return None
    if limit > 0:
        idle = idle_evaluations(fam)
        since = "its last validation" if int(fam.get("validations") or 0) else "its birth"
        best = fam.get("best_train")
        if best is None and idle >= limit:
            return f"made no eligible Train version in {idle} Gym evaluations since {since}"
        if best is not None and float(best) < 0 and idle >= NEGATIVE_FACTOR * limit:
            return f"kept its best Train score below zero over {idle} Gym evaluations since {since}"
    cycles = dormant_count(fam)
    if dormant > 0 and cycles >= dormant and not awaiting_validation(fam):
        return f"made no new Gym evaluation in its last {cycles} cycles (only stored results, holds and refused runs)"
    return None


class Researcher:
    """Runs cycles for any family (one call per cycle; the loop's workers call it concurrently)."""

    def __init__(self, store: SwarmStore, router: Any, pool: Any, settings: Mapping[str, Any], *, contract: str | None = None,
                 clock: Callable[[], float] = time.time, starter: Callable[[Mapping[str, Any]], tuple[str, dict]] | None = None,
                 background: bool = True):
        self.store = store
        self.router = router
        self.pool = pool
        self.settings = settings
        self.clock = clock
        self.contract = contract if contract is not None else CONTRACT.read_text(encoding="utf-8")
        self.system = ROLE + self.contract
        self.starter = starter
        self.background = background
        self._rewriting: dict[str, Any] = {}
        #: (family, version, label) robustness runs this process has in flight (a restart loses queued jobs: they are
        #: queued again; a run that failed leaves the set, so a later cycle queues it again).
        self._robust: set[tuple[str, int, str]] = set()
        #: family -> the variants its sweep has in flight; every worker shares this Researcher, so their sum is the load
        #: sweeps add to the pool (`max_sweep_jobs_in_flight`, the module docstring's SWEEP LOAD).
        self._sweeping: dict[str, int] = {}
        self._sweep_lock = threading.Lock()
        #: The fill model version of the latest result the Gym returned (`_result_key`); a stored result on another one is
        #: not reused (`_reusable`). None until a result lands.
        self._fill_model: str | None = None
        self.pace: Callable[[], bool] = lambda: False  # the swarm's hourly spend at its pace: no rewrite starts

    @property
    def cfg(self) -> Mapping[str, Any]:
        return self.settings.get("researcher", {})

    # ------------------------------------------------------------------ the prompt
    def brief(self, fam: Mapping[str, Any]) -> str:
        spec = fam.get("spec") or {}
        lines = [f"YOUR FAMILY: {fam['id']} ({fam['origin']}{', forked from ' + fam['parent'] if fam.get('parent') else ''})",
                 f"Mechanism: {fam['mechanism']}",
                 f"Structure: {fam['structure']}. Roots: {', '.join(fam['roots'])}. Days to expiry: "
                 f"{(spec.get('dte') or ['?', '?'])[0]}-{(spec.get('dte') or ['?', '?'])[1]}.",
                 f"Rejection test: {spec.get('rejection') or 'state one in your notebook'}"]
        lessons = spec.get("lessons") or []
        if lessons:
            lines.append("Lessons from the graveyard when you were born:")
            lines += [f"- {diagnostics.scrub(x)}" for x in lessons[:3]]
        return "\n".join(lines)

    def status(self, fam: Mapping[str, Any]) -> str:
        best = self.store.version(fam["id"], fam.get("best_version"))
        state = fam.get("state") or {}
        line = state.get("validation_line")
        gate = state.get("gate")
        notes = self.store.notebook(fam["id"], limit=5)
        parts = [f"Cycle {int(fam['cycles']) + 1}. Revisions so far (a sweep is one): {fam['revisions']}. Lineage trials: "
                 f"{self.store.lineage_trials(fam['id'])}. Revisions since a better Train score: {fam['stall']} "
                 f"(a rewrite from a stronger model comes at {self.cfg.get('stall_revisions', 5)})."]
        if state.get("best_train_version") is not None:
            parts.append(f"Your best Train score: {fam.get('best_train')} (version {state['best_train_version']}).")
        if best:
            parts.append(f"Your submitted best: version {best['n']}.")
        else:
            parts.append("No best submitted yet: submit your best eligible Train run.")
        if line and state.get("validation_version") is not None:
            # D2a: pass or fail and a count, never a number Validation measured nor which checks failed.
            parts.append(f"Validation of version {state['validation_version']}: it {diagnostics.validation_words(line)}.")
        robust = self.robustness_text(fam)
        if robust:
            parts.append(robust)
        parts.append(f"The validation line requires at least {evidence.MIN_TRADES} trades on at least {evidence.MIN_DAYS} days, "
                     "daily t >= 2, a deflated Sharpe probability >= 0.95 on traded days, 3 of 4 quarters positive, and positive "
                     "P&L at 1.5x spread. Seek mechanisms that produce enough independent opportunities to measure; never force "
                     "trades or weaken the evidence requirements.")
        if gate:
            parts.append(f"The gate's last answer: {gate}.")
        if state.get("gate_hold") and state.get("gate_ready"):
            parts.append("Your validated version is held by the operator before the gate: it is looked at once the hold is "
                         "cleared.")
        dormant = dormant_count(fam)
        if dormant:
            parts.append(f"Cycles in a row without a new Gym evaluation (only stored results, holds and refused runs): {dormant}.")
        if notes:
            parts.append("Your notebook (latest):\n" + "\n".join(f"- {diagnostics.scrub(n['text'])[:300]}" for n in notes))
        may_retire = self.can_retire(fam)
        dead = idle_dead(fam, self.settings) if may_retire else None
        if dead:
            parts.append(f"Your family {dead}. If its mechanism is dead, call retire with your reason when the tool is offered "
                         "rather than re-running a placeholder: its slot goes to a new idea.")
        retire_hint = " If you abandon the entire mechanism, call retire with your reason." if may_retire else ""
        hold_hint = " With nothing new to run, call gym_run with hold=true and say why in its note."
        fit = min(self.sweep_room(), self.max_variants)
        if self.sweeps and fit >= 2:
            parts.append("Now: if a run just came back, read it (submit it if it is your best) and queue your next gym_run or "
                         "gym_sweep; otherwise revise and call gym_run or gym_sweep, with what you learned in its note. A sweep of "
                         f"up to {fit} variants fits in the Gym now." + hold_hint + retire_hint)
        elif self.sweeps:
            parts.append("Now: if a run just came back, read it (submit it if it is your best) and queue your next gym_run or "
                         "gym_sweep; otherwise revise and call gym_run, with what you learned in its note. The Gym is full of other "
                         "families' sweeps now: a gym_sweep this cycle would be refused." + hold_hint + retire_hint)
        else:
            parts.append("Now: if a run just came back, read it (submit it if it is your best) and queue your next gym_run; "
                         "otherwise revise and call gym_run, with what you learned in its note. gym_sweep is switched off now."
                         + hold_hint + retire_hint)
        return "\n".join(parts)

    # ------------------------------------------------------------------ the tools a turn offers
    @property
    def sweeps(self) -> bool:
        """`gym_sweep` is offered (and accepted) only while `researcher.sweep_enabled` is true (the default)."""
        return bool(self.cfg.get("sweep_enabled", True))

    @property
    def reuse(self) -> bool:
        """A run the family already evaluated is answered from the store (NO DUPLICATE RUNS) unless
        `researcher.reuse_results` is false."""
        return self.cfg.get("reuse_results", True) is not False

    def _gym_identity(self) -> tuple[Any, Any]:
        """(the Gym image, its engine bundle) the pool runs now; (None, None) for a pool that does not say."""
        image = bundle = None
        try:
            image = self.pool.image("gym") if callable(getattr(self.pool, "image", None)) else None
            bundle = self.pool.bundle() if callable(getattr(self.pool, "bundle", None)) else None
        except Exception:  # noqa: BLE001 - no image or engine known: the content alone
            pass
        return image, bundle

    def eval_key(self, code: str, params: Mapping[str, Any] | None, *, stress: float, window: str, roots: Any,
                 image: Any = None, bundle: Any = None, current: bool = True) -> str:
        """One evaluation's identity (NO DUPLICATE RUNS): the code, its MERGED params (`merged_key`: `{}` and a default
        spelled out are one program), the stress, window and roots (sorted, as the Gym sorts them), the Gym's image and
        engine (the pool's now when `current`, else `image` and `bundle`: the ones a result was stamped with) and the Train
        split and capital (the run's settings the Gym hashes too).

        Two limits, both on purpose. (1) It is coarser than the Gym's own run_id: the Gym runs a batch over the trading
        days of the union of its programs' roots (`league/gym/batch.py`), and that day list enters the Gym's data version
        and run_id, so a stored result is the sample of the batch it ran in; another batch would differ only in that
        sampling, never as new evidence, so it is not run again. (2) Data and the fill model are the image's: a new data
        set or calibration comes as a new image checkpoint, which is in the key. A fill model changed on a box in place
        (`/data/calibration/fill_model.json`) is caught when the results land: a stored result whose `fill_model` differs
        from the latest one the Gym returned is not reused (`_reusable`)."""
        if current:
            image, bundle = self._gym_identity()
        gym = self.settings.get("gym", {})
        body = {"code": hashlib.sha256(str(code).encode("utf-8")).hexdigest(),
                "params": merged_key(params_of(str(code)) or {}, dict(params or {})), "stress": float(stress),
                "window": str(window), "roots": sorted(str(r).upper() for r in roots or ()), "image": image, "bundle": bundle,
                "split": gym.get("train_split", gym.get("split", 8)) if window == "train" else gym.get("validation_split", 1),
                "capital": gym.get("capital", 10000.0)}
        return hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:32]

    def _result_key(self, job: GymJob, result: Mapping[str, Any]) -> str:
        """The key a landed result is recorded under: its job's evaluation on the image and engine the pool stamped it
        with (`gym_image`, `gym_bundle`), else the pool's now. The result's fill model becomes the one the Gym runs now."""
        if result.get("fill_model"):
            self._fill_model = str(result["fill_model"])
        image, bundle = self._gym_identity()
        return self.eval_key(job.code, job.params, stress=job.stress, window=job.window, roots=job.roots, current=False,
                             image=result.get("gym_image", image), bundle=result.get("gym_bundle", bundle))

    def _reusable(self, run: Mapping[str, Any] | None, *, stress: float) -> Mapping[str, Any] | None:
        """A stored run (`SwarmStore.evaluated`) that may answer a request, or None (the request runs): not one whose fill
        model differs from the one the Gym last returned (calibrated anew on the box), and at the normal spread not one
        that can no longer be scored (neither its full result nor a Train score on its row)."""
        if run is None:
            return None
        summary = run.get("summary") or {}
        if summary.get("fill_model") and self._fill_model and str(summary["fill_model"]) != self._fill_model:
            return None
        if stress == 1.0 and "train_score" not in summary and self.store.run_result(run["run_id"]) is None:
            return None
        return run

    def _restart_dormancy(self, fid: str, result: Mapping[str, Any]) -> None:
        """DORMANCY: a new Gym evaluation of the family's own (its Train run or sweep variant, in its cycle or landed late)
        sets `dormant_cycles` to zero as soon as it is recorded, so the READ turn after it and the tournament meanwhile no
        longer find the family dead by the dormancy clause."""
        if int(result.get("trials", 0) or 0) <= 0:
            return
        with self.store.atomic():
            fam = self.store.family(fid)
            if fam is not None and dormant_count(fam):
                self.store.set_state(fid, dormant_cycles=0)

    @staticmethod
    def _with_score(result: Mapping[str, Any], stress: float) -> tuple[Mapping[str, Any], dict[str, Any] | None]:
        """(the result as its run's row records it, its Train score): at the normal spread the row keeps the score and
        eligibility (`submit` reads them, and a stored result whose full result was pruned is scored from them)."""
        robust = evidence.train_score(result) if stress == 1.0 else None
        if robust is not None and isinstance(result.get("summary"), Mapping):
            return {**result, "summary": {**result["summary"], "train_score": robust["score"],
                                          "train_eligible": robust["eligible"]}}, robust
        return result, robust

    @property
    def max_variants(self) -> int:
        return max(2, int(self.cfg.get("max_sweep_variants", MAX_SWEEP_VARIANTS)))

    @property
    def max_sweep_jobs(self) -> int:
        return max(2, int(self.cfg.get("max_sweep_jobs_in_flight", MAX_SWEEP_JOBS_IN_FLIGHT)))

    def sweep_room(self) -> int:
        """Variants a new sweep may put on the pool now: `max_sweep_jobs_in_flight` less every sweep in flight."""
        with self._sweep_lock:
            return max(0, self.max_sweep_jobs - sum(self._sweeping.values()))

    def _reserve_sweep(self, fid: str, n: int) -> bool:
        """Take `n` of the in-flight variants for a family's sweep (False, nothing taken, when they do not fit)."""
        with self._sweep_lock:
            if sum(self._sweeping.values()) + n > self.max_sweep_jobs:
                return False
            self._sweeping[fid] = self._sweeping.get(fid, 0) + n
            return True

    def _release_sweep(self, fid: str, n: int) -> None:
        with self._sweep_lock:
            left = self._sweeping.get(fid, 0) - n
            if left > 0:
                self._sweeping[fid] = left
            else:
                self._sweeping.pop(fid, None)

    def tools(self, *, revise: bool, retire: bool) -> list[dict[str, Any]]:
        """A turn's tools: REVISE a run or a sweep (the call is required), READ every tool, `retire` only when the family
        may retire (`can_retire`); `gym_sweep` only while sweeps are on, its limit from the settings."""
        base = TOOLS_REVISE if revise else (TOOLS if retire else TOOLS_READ)
        if not self.sweeps:
            return [t for t in base if t["name"] != "gym_sweep"]
        return [sweep_tool(self.max_variants) if t["name"] == "gym_sweep" else t for t in base]

    def robustness_text(self, fam: Mapping[str, Any]) -> str:
        """The "Robustness" block of the family's status: its best version's Train runs at 1.5x the half-spread and at the
        mid, compact, once they are back; and the versions that lost at 1.5x."""
        state = fam.get("state") or {}
        out = []
        n = state.get("best_train_version")
        rows = (state.get("robustness") or {}).get(str(n)) if n is not None else None
        if rows:
            parts = [f"{label}: {json.dumps(rows[label], default=str)}" for label in ("stress_1.5", "mid") if rows.get(label)]
            if parts:
                out.append(f"Robustness of your best (version {n}, the same Train window): " + "; ".join(parts) + ".")
        failed = state.get("robust_failed") or []
        if failed:
            whys = state.get("robust_why") or {}
            out.append("Versions that can never be your best (the next eligible one took their place): " + "; ".join(
                f"version {v} {whys.get(str(v), 'lost money on Train at 1.5x the half-spread')}" for v in failed[-8:]) + ".")
        elif rows and not landed(rows.get("stress_1.5")):
            out.append(f"Your best (version {n}) is validated once its 1.5x robustness run comes back with a profit.")
        return " ".join(out)

    # ------------------------------------------------------------------ retirement, the top ten
    def can_retire(self, fam: Mapping[str, Any]) -> bool:
        """`retire` is offered (and accepted) for a Gym family with at least two validations while more families live
        than `population.start` (the sprint, Sept 26), and for a dead family (`idle_dead`, R3) while more live than
        `population.floor`, whatever the start. Never while the operator holds its validated version at the gate
        (`held_at_gate`: `SwarmStore.retire_gym` refuses it too)."""
        if fam.get("band") != "gym" or held_at_gate(fam):
            return False
        pop = self.settings.get("population", {})
        alive = len(self.store.families(alive=True))
        if idle_dead(fam, self.settings) and alive > int(pop.get("floor", 16)):
            return True
        return int(fam.get("validations") or 0) >= 2 and alive > int(pop.get("start", 48))

    def retire_floor(self, fam: Mapping[str, Any]) -> int:
        """The population a researcher's retirement may not take the swarm to (`retire_gym` checks it atomically):
        `population.floor` for a dead family (`idle_dead`), else the start (never below the floor)."""
        pop = self.settings.get("population", {})
        floor = int(pop.get("floor", 16))
        return floor if idle_dead(fam, self.settings) else max(floor, int(pop.get("start", 48)))

    def is_top(self, fam: Mapping[str, Any], *, top: int) -> bool:
        """Among the bandit's `top` families by weight (a weight of zero or none never is)."""
        weight_rank = sorted((f.get("weight") or 0.0 for f in self.store.families(alive=True)), reverse=True)
        return bool(weight_rank) and top > 0 and (fam.get("weight") or 0.0) >= weight_rank[min(top, len(weight_rank)) - 1] > 0

    # ------------------------------------------------------------------ tools
    @staticmethod
    def _refusal(out: dict[str, Any], answer: dict[str, Any]) -> dict[str, Any]:
        """A run or sweep refused for the researcher's own doing (its program, NEEDS, params or variants, no version, a
        sweep while sweeps are off): no Gym job. A cycle of only such calls, holds and stored results is dormant
        (DORMANCY). A sweep refused for room is not one (the Gym's load, not the researcher's doing)."""
        out["run_refused"] = int(out.get("run_refused") or 0) + 1
        return answer

    def _admit(self, fam: Mapping[str, Any], code: str, out: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str], bool]:
        """(a refusal or None, the roots its NEEDS names, whether they change the family's): the Gym's safety check, NEEDS a
        literal, and roots only from the admitted list, at most `MAX_ROOTS`, changed only by a Gym family."""
        why = check_code(code)
        if why:
            out["refused"] = out.get("refused", 0) + 1
            return {"status": "refused", "reason": why[:600], "hint": "fix the rule named (the contract) and run again"}, [], False
        needs = needs_of(code)
        if needs is None:
            return {"status": "refused", "reason": "NEEDS must be a literal dict at the top level"}, [], False
        roots = list(needs_roots(code))
        admitted = [str(r).upper() for r in self.settings.get("gym", {}).get("roots", [])]
        change = bool(roots) and set(roots) != set(fam["roots"])
        if change:
            outside = [r for r in roots if r not in admitted]
            if outside:
                return {"status": "refused", "reason": f"NEEDS names {', '.join(outside)}, not in the Gym's roots "
                                                       f"({', '.join(admitted)})"}, roots, change
            if len(roots) > MAX_ROOTS:
                return {"status": "refused", "reason": f"a family holds at most {MAX_ROOTS} roots; NEEDS names {len(roots)}"}, roots, change
            if fam.get("band") != "gym":
                return {"status": "refused", "reason": f"your family trades {', '.join(fam['roots'])} in its band; only a Gym family "
                                                       "changes its roots"}, roots, change
        return None, roots, change

    def _gym_run(self, fam: Mapping[str, Any], args: Mapping[str, Any], out: dict[str, Any], *, author: str) -> dict[str, Any]:
        if self._terminal(fam["id"], out):
            return {"status": "retired", "reason": "the family is retired; no run started"}
        if holding(args):
            return self._hold(fam, args, out)
        code = args.get("code")
        if not code:
            latest = self.store.latest_version(fam["id"])
            if latest is None or not latest.get("code"):
                return self._refusal(out, {"error": "you have no version yet: pass `code`"})
            code = latest["code"]
        code = str(code)
        dated = [k for k, v in (args.get("params") or {}).items()] if isinstance(args.get("params"), dict) else []
        dated = [k for k in dated if date_like(args["params"][k])]
        if dated:
            return self._refusal(out, {"status": "refused", "reason": f"a date or a year in the parameter overrides "
                                                                      f"({', '.join(dated)}): no program may see the calendar",
                                       "hint": "use relative measures, never a date, a year or a level"})
        note = str(args.get("note") or "").strip()
        if note:
            self.store.note(fam["id"], note)
            out["note"] = note
        params = args.get("params") if isinstance(args.get("params"), dict) else {}
        stress = float(args.get("stress") or 1.0)
        if stress not in (1.0, 1.5):
            stress = 1.0
        refused, roots, change = self._admit(fam, code, out)
        if refused is not None:
            return self._refusal(out, refused)
        # NO DUPLICATE RUNS: the evaluation this run would be, on the roots it would run on.
        key = self.eval_key(code, params, stress=stress, window="train", roots=roots if change else fam["roots"])
        stored = None
        with self.store.atomic():
            if self._terminal(fam["id"], out):
                return {"status": "retired", "reason": "the family is retired; no run started"}
            if change:  # a new version on other roots of the admitted list: the family's slice follows it
                self.store.update_family(fam["id"], roots=roots)
                self.store.note(fam["id"], f"Roots changed from {', '.join(fam['roots'])} to {', '.join(roots)}.")
                out["roots"] = roots
                fam = {**fam, "roots": roots}
            stored = self._reusable(self.store.evaluated(fam["id"], key), stress=stress) if self.reuse else None
            if stored is None:
                version = self.store.add_version(fam["id"], code, params, author=author, note=str(args.get("why") or "")[:300])
        if stored is not None:
            return self._stored_run(fam, stored, out, code=code, stress=stress)
        job = GymJob(family=fam["id"], version=version["n"], code=code, params=params, window="train", roots=tuple(fam["roots"]),
                     stress=stress, purpose="train", priority=float(fam.get("weight") or 0.0))
        began = self.clock()
        try:
            def late(result: Mapping[str, Any], fid: str = fam["id"], n: int = version["n"], stress: float = stress) -> None:
                # Landed after the wait gave up: a trial, its row scored as a run's (asked for again, it is scored from the
                # row even once its full result is pruned), and a new evaluation for the dormancy clause.
                days = float((result.get("summary") or {}).get("days") or 0)
                self.store.add_run(fid, n, self._with_score(result, stress)[0], window="train", stress=stress, purpose="train",
                                   program_years=days / 252.0 * max(1, len(fam["roots"])), key=self._result_key(job, result))
                self._restart_dormancy(fid, result)

            if self._terminal(fam["id"], out):
                return {"status": "retired", "reason": "the family is retired; no run started"}
            out["gym_asked"] = True  # a new evaluation asked of the Gym: a cycle it does not land in is not dormant (DORMANCY)
            result = self.pool.run(job, timeout=float(self.settings.get("gym", {}).get("run_timeout_seconds", 900)) + 120, late=late)
        except PoolError as exc:
            out["gym_error"] = str(exc)[:300]
            return {"status": "gym_error", "version": version["n"], "error": str(exc)[:500],
                    "hint": "the Gym could not run it now; your version is saved: rerun it next cycle"}
        out["gym_seconds"] = round(self.clock() - began, 2)
        years = float((result.get("summary") or {}).get("days") or 0) / 252.0 * max(1, len(fam["roots"]))
        recorded, robust = self._with_score(result, stress)  # the run's row keeps its score (`submit` reads it)
        run = self.store.add_run(fam["id"], version["n"], recorded, window="train", stress=stress, purpose="train",
                                 program_years=years, key=self._result_key(job, result))
        self._restart_dormancy(fam["id"], result)  # before the READ turn: a family that ran something new is not dead
        out["run_id"] = run["run_id"]
        # This evaluation's trials (the row's own count also holds earlier identical evaluations of a row recorded before keys).
        out["trials"] = out.get("trials", 0) + int(result.get("trials", 0) or 0)
        view = diagnostics.train_view(result, lineage_trials=self.store.lineage_trials(fam["id"]))
        view["version"] = version["n"]
        view["run_id"] = run["run_id"]
        score = self._scored(fam, version["n"], run["run_id"], robust, view, out, code=code, params=params)
        out["score"] = None if score is None else round(score, 3)
        return view

    def _scored(self, fam: Mapping[str, Any], n: int, run_id: str, robust: Mapping[str, Any] | None, view: dict[str, Any],
                out: dict[str, Any], *, code: str, params: Mapping[str, Any]) -> float | None:
        """A Train run's score into the family's candidates and best (a new best queues its robustness runs) and into its
        view; returns the score when it is eligible (None otherwise). Idempotent: a stored result read again changes
        nothing its run already changed."""
        score = robust["score"] if robust is not None and robust["eligible"] and robust["score"] is not None else None
        best = failed = False
        with self.store.atomic():
            current = self.store.family(fam["id"]) or {}
            state = current.get("state") or {}
            failed = n in (state.get("robust_failed") or [])
            if not current.get("retired_at") and score is not None and not failed:
                candidates = candidates_with(state.get("train_candidates"), score, n, run_id)
                if candidates != state.get("train_candidates"):
                    self.store.set_state(fam["id"], train_candidates=candidates)
                if current.get("best_train") is None or score > float(current["best_train"]):
                    self.store.update_family(fam["id"], best_train=score, stall=0)
                    self.store.set_state(fam["id"], best_train_run=run_id, best_train_version=n)
                    view["new_best_train_score"] = round(score, 3)
                    out["improved"] = True
                    best = True
        if robust is not None:
            view["train_score"] = {"score": robust["score"], "eligible": bool(robust["eligible"]) and not failed,
                                   "worst_year": robust.get("worst_year"), "quarters_positive": robust.get("quarters"),
                                   "by_year": robust.get("years")}
            if not robust["eligible"]:
                view["train_score"]["why_not_eligible"] = robust.get("why") or ("not eligible under the Train score (40 trades "
                                                                                 "on 20 days in every Train year)")
            elif failed:
                view["train_score"]["why_not_eligible"] = "this version lost money on Train at 1.5x the half-spread"
        if best:
            self.queue_robustness(fam["id"], n, code, params, needs_roots(code, fam["roots"]))
        return score

    def _stored_run(self, fam: Mapping[str, Any], run: Mapping[str, Any], out: dict[str, Any], *, code: str,
                    stress: float) -> dict[str, Any]:
        """NO DUPLICATE RUNS: a run the family already evaluated, answered from the store: the same compact view (from its
        full result while it is kept, else from its row's summary), marked `already_run`, with no Gym job, no trial, no
        version and no revision. Its score goes into the family's candidates and best as any run's (it changes nothing a
        run already changed; a run that landed after the Gym gave up on it was recorded with its score but never scored
        into the best). A run whose full result was pruned is scored from its row's Train score."""
        fid, n = fam["id"], int(run["version"])
        full = self.store.run_result(run["run_id"])
        summary = run.get("summary") or {}
        if full is not None:
            view = diagnostics.train_view(full, lineage_trials=self.store.lineage_trials(fid))
            robust = evidence.train_score(full) if stress == 1.0 else None
        else:
            view = {"run_id": run["run_id"], "status": run.get("status"), "window": "train", "stress": run.get("stress"),
                    "summary": {k: summary[k] for k in diagnostics.SUMMARY_KEYS if k in summary},
                    "lineage_trials": self.store.lineage_trials(fid),
                    "kept": "its full result is no longer kept (your newest six runs and your best are): its summary only"}
            robust = None
            if stress == 1.0 and summary.get("train_score") is not None:
                robust = {"score": summary["train_score"], "eligible": bool(summary.get("train_eligible")), "why": None}
        view["version"] = n
        view["run_id"] = run["run_id"]
        view["already_run"] = ALREADY_RUN
        view["next"] = ("this program and params already ran on this window, stress, roots and Gym: no new run, no trial. "
                        "Change the program or its params, or call gym_run with hold=true if you have nothing new")
        out["stored"] = out.get("stored", 0) + 1
        params = (self.store.version(fid, n) or {}).get("params") or {}
        self._scored(fam, n, run["run_id"], robust, view, out, code=code, params=params)
        return view

    def _hold(self, fam: Mapping[str, Any], args: Mapping[str, Any], out: dict[str, Any]) -> dict[str, Any]:
        """HOLD (NO DUPLICATE RUNS): an honest skip of the cycle: no Gym job, no trial, no version; a line in the notebook.
        The loop ends the cycle (a run call after it in the same answer is refused), which is dormant unless it also made a
        new evaluation (DORMANCY). A hold that also carries code or params is still a hold: they are ignored (a model
        passing its current program beside hold=true must not escape the dormancy count by a refusal). Only `note`, the
        field marked PUBLIC, reaches the notebook and the cycle's note (never `why`)."""
        ignored = [k for k in ("code", "params") if args.get(k)]
        why = str(args.get("note") or "").strip()
        with self.store.atomic():
            if self._terminal(fam["id"], out):
                return {"status": "retired", "reason": "the family is retired; nothing to hold"}
            self.store.note(fam["id"], f"Held a cycle (no run): {why or 'nothing new to run'}")
        if why:
            out["note"] = why
        out["hold"] = True
        answer = {"status": "held", "note": "no run this cycle: no Gym job, no trial, no revision; your reason is in your notebook. "
                                            "Cycles in a row of holds and stored results count against your family under the "
                                            "idle rule: run something new when you have it."}
        if ignored:
            answer["ignored"] = (f"a hold runs nothing, so its {' and '.join(ignored)} were ignored: to run a program, call "
                                 "gym_run without hold next cycle")
        return answer

    def _record_variant(self, job: GymJob, result: Mapping[str, Any], robust: Mapping[str, Any] | None = None, *,
                        sweep: str, prune: bool = True) -> dict[str, Any]:
        """One sweep variant's Train result, recorded as its own run of its own version (a trial, as every Gym evaluation
        is): its row keeps its Train score and eligibility (`submit` reads them), its params and its sweep. A sweep records
        its variants unpruned (`prune=False`) and prunes once at its end, keeping all its rows for `read_run`."""
        robust = robust if robust is not None else evidence.train_score(result)
        recorded = dict(result)
        if isinstance(result.get("summary"), Mapping):
            recorded["summary"] = {**result["summary"], "train_score": robust["score"], "train_eligible": robust["eligible"],
                                   "params": dict(job.params or {}), "sweep": sweep}
        days = float((result.get("summary") or {}).get("days") or 0)
        run = self.store.add_run(job.family, job.version, recorded, window="train", stress=1.0, purpose="train",
                                 program_years=days / 252.0 * max(1, len(job.roots)), prune=prune,
                                 key=self._result_key(job, result))
        self._restart_dormancy(job.family, result)  # landed in the sweep or late: a new evaluation (DORMANCY)
        return run

    @staticmethod
    def _variant_row(job: GymJob, run_id: str, status: Any, summary: Mapping[str, Any], *, robust: Mapping[str, Any] | None,
                     fill_rate: Any = None, reason: Any = None, trials: int = 0, reused: bool = False) -> dict[str, Any]:
        """A landed variant, compact: all a sweep keeps of it while it waits for the others (its full result is on disk).
        `robust` None: only the run row's summary is left (its full result was pruned), so no per-year figures."""
        if robust is not None:
            score, eligible, why = robust["score"], bool(robust["eligible"]), robust.get("why")
            years = {y: {"t": _round(r.get("t_daily"), 2), "trades": r.get("trades")} for y, r in (robust.get("years") or {}).items()}
        else:
            score, eligible, why, years = summary.get("train_score"), bool(summary.get("train_eligible")), None, {}
        return {"job": job, "run_id": str(run_id), "status": status, "reason": reason, "score": score, "eligible": eligible,
                "why": why, "years": years, "trades": summary.get("trades"), "days": summary.get("days_traded"),
                "pnl": _round(summary.get("pnl"), 2), "fill_rate": _round(fill_rate, 3), "trials": int(trials), "reused": reused}

    def _sweep_group(self, fid: str, code: str, variants: list[dict[str, Any]], roots: Any) -> str:
        """A sweep's group id is its content (the family, the code, the variants, the roots, the Gym's image and engine): the
        same sweep asked again (a queued sweep's quiet retry after the Gym gave up) shares its group."""
        image, bundle = self._gym_identity()
        body = json.dumps({"code": code, "variants": variants, "roots": list(roots), "image": image, "bundle": bundle},
                          sort_keys=True, default=str)
        return f"{fid}:sweep:{hashlib.sha256(body.encode('utf-8')).hexdigest()[:16]}"

    def _gym_sweep(self, fam: Mapping[str, Any], args: Mapping[str, Any], out: dict[str, Any], *, author: str) -> dict[str, Any]:
        """`gym_sweep` (the module docstring, SWEEPS and SWEEP LOAD): the variants of one program on Train at once, each its
        own version and its own run and trial; a table sorted by the Train score."""
        fid = fam["id"]
        if self._terminal(fid, out):
            return {"status": "retired", "reason": "the family is retired; no run started"}
        if not self.sweeps:
            return self._refusal(out, {"status": "refused", "reason": "gym_sweep is switched off now: use gym_run"})
        code = args.get("code")
        if not code:
            latest = self.store.latest_version(fid)
            if latest is None or not latest.get("code"):
                return self._refusal(out, {"error": "you have no version yet: pass `code`"})
            code = latest["code"]
        code = str(code)
        refused, roots, change = self._admit(fam, code, out)
        if refused is not None:
            return self._refusal(out, refused)
        base = args.get("params") if isinstance(args.get("params"), dict) else {}
        variants, dropped, why = sweep_variants(code, args.get("variants"), args.get("params"), limit=self.max_variants)
        if why:
            return self._refusal(out, {"status": "refused", "reason": why[:600],
                                       "hint": "fix the variants (each key in your PARAMS, of its type) and sweep again"})
        # NO DUPLICATE RUNS: a variant the family already evaluated (any earlier run or sweep, or this very sweep's variant
        # that landed after the Gym gave up on it) is read back from the store, never run again, and needs no room.
        run_roots = roots if change else fam["roots"]
        stored: dict[int, dict[str, Any]] = {}
        if self.reuse:
            for i, params in enumerate(variants):
                run = self._reusable(self.store.evaluated(fid, self.eval_key(code, params, stress=1.0, window="train",
                                                                             roots=run_roots)), stress=1.0)
                if run is not None:
                    stored[i] = run
        fresh = len(variants) - len(stored)
        if fresh and not self._reserve_sweep(fid, fresh):  # the pool's room for sweeps (SWEEP LOAD): a plain refusal, no backoff
            room = self.sweep_room()
            out["sweep_busy"] = True
            return {"status": "refused", "reason": "the Gym is full of other families' sweeps now"
                                                   + (f": a sweep of at most {room} variants fits" if room >= 2 else ""),
                    "hint": "call gym_run this cycle, with your note (a sweep can come in a later cycle)"}
        try:
            # The note once the sweep is taken: a refused sweep's note comes again with the call that follows it.
            note = str(args.get("note") or "").strip()
            if note:
                self.store.note(fid, note)
                out["note"] = note
            return self._run_sweep(fam, args, out, code=code, base=base, variants=variants, dropped=dropped, roots=roots,
                                   change=change, author=author, stored=stored)
        finally:
            if fresh:
                self._release_sweep(fid, fresh)

    def _run_sweep(self, fam: Mapping[str, Any], args: Mapping[str, Any], out: dict[str, Any], *, code: str,
                   base: Mapping[str, Any], variants: list[dict[str, Any]], dropped: int, roots: list[str], change: bool,
                   author: str, stored: Mapping[int, Mapping[str, Any]]) -> dict[str, Any]:
        fid = fam["id"]
        fresh = [p for i, p in enumerate(variants) if i not in stored]
        with self.store.atomic():
            if self._terminal(fid, out):
                return {"status": "retired", "reason": "the family is retired; no run started"}
            if change:  # as a gym_run: the family's slice follows the program's NEEDS
                self.store.update_family(fid, roots=roots)
                self.store.note(fid, f"Roots changed from {', '.join(fam['roots'])} to {', '.join(roots)}.")
                out["roots"] = roots
                fam = {**fam, "roots": roots}
            # Only the variants that run are added: a sweep read wholly from the store adds no version and no revision.
            versions = self.store.add_versions(fid, code, fresh, author=author, note=str(args.get("why") or "")[:300]) if fresh else []
        group = self._sweep_group(fid, code, variants, fam["roots"])
        todo = [GymJob(family=fid, version=int(v["n"]), code=code, params=dict(p), window="train", roots=tuple(fam["roots"]),
                       stress=1.0, purpose="train", priority=float(fam.get("weight") or 0.0), group=group)
                for p, v in zip(fresh, versions)]
        timeout = float(self.settings.get("gym", {}).get("run_timeout_seconds", 900)) + 120

        def late(job: GymJob) -> Callable[[Mapping[str, Any]], None]:
            return lambda result: self._record_variant(job, result, sweep=group)  # a trial whenever it lands

        if self._terminal(fid, out):
            return {"status": "retired", "reason": "the family is retired; no run started"}
        rows: list[dict[str, Any]] = []
        failed: list[tuple[GymJob, str]] = []
        for i, run in sorted(stored.items()):  # read back: each was a trial when it ran
            job = GymJob(family=fid, version=int(run["version"]), code=code, params=dict(variants[i]), window="train",
                         roots=tuple(fam["roots"]), stress=1.0, purpose="train", group=group)
            full = self.store.run_result(run["run_id"])
            if full is not None:
                rows.append(self._variant_row(job, run["run_id"], full.get("status"), full.get("summary") or {},
                                              robust=evidence.train_score(full), fill_rate=(full.get("fills") or {}).get("fill_rate"),
                                              reused=True))
            else:
                rows.append(self._variant_row(job, run["run_id"], run.get("status"), run.get("summary") or {}, robust=None,
                                              reused=True))

        def land(job: GymJob, result: Mapping[str, Any]) -> None:
            # Recorded as it lands; only its compact row stays in memory (many sweeps in flight must not hold every trade).
            robust = evidence.train_score(result)
            run = self._record_variant(job, result, robust, sweep=group, prune=False)
            rows.append(self._variant_row(job, run["run_id"], result.get("status"), result.get("summary") or {}, robust=robust,
                                          fill_rate=(result.get("fills") or {}).get("fill_rate"), reason=result.get("reason"),
                                          trials=int(result.get("trials", 0) or 0)))
            job.result = None

        began = self.clock()
        if todo:
            out["gym_asked"] = True  # new evaluations asked of the Gym: a cycle none lands in is not dormant (DORMANCY)
        submit, wait = getattr(self.pool, "submit", None), getattr(self.pool, "wait", None)
        if callable(submit) and callable(wait):
            for job in todo:  # queued together: the pool batches them (one group: none supersedes another)
                submit(job)
            deadline = began + timeout  # gym_run's timeout, for every variant, from the moment all were queued
            for job in todo:
                try:
                    result = wait(job, max(0.0, deadline - self.clock()), late=late(job))
                except PoolError as exc:
                    failed.append((job, str(exc)))
                    continue
                land(job, result)
        else:  # a pool that only runs one job at a time
            for job in todo:
                try:
                    result = self.pool.run(job, timeout=timeout, late=late(job))
                except PoolError as exc:
                    failed.append((job, str(exc)))
                    continue
                land(job, result)
        out["gym_seconds"] = round(self.clock() - began, 2)
        numbers = [int(v["n"]) for v in versions]
        if todo and not any(not r["reused"] for r in rows):
            # Not one new variant landed (every one failed, or landed only after the wait: it is still recorded, a trial,
            # through `late`): a Gym error, whatever the store read back. No run for the cycle (the loop stops and backs
            # off) and no dormant cycle: the Gym could not make what was asked (DORMANCY).
            error = failed[0][1] if failed else "the Gym returned nothing"
            out["gym_error"] = error[:300]
            answer = {"status": "gym_error", "versions": numbers, "error": error[:500],
                      "hint": "the Gym could not run the sweep now; its versions are saved: sweep again next cycle"}
            if rows:
                answer["already_run"] = (f"{len(rows)} of its variants already ran and are read back from the store when you "
                                         "sweep again (no trial)")
            return answer
        demoted = {int(v) for v in (((self.store.family(fid) or {}).get("state") or {}).get("robust_failed") or [])}

        def counts(row: Mapping[str, Any]) -> bool:
            """Completed, eligible and not demoted at 1.5x: only such a row may be the best or head the table."""
            return row["status"] == "ok" and row["eligible"] and row["score"] is not None and int(row["job"].version or 0) not in demoted

        rows.sort(key=lambda r: (r["status"] != "ok", not counts(r), -(r["score"] if r["score"] is not None else -math.inf),
                                 r["job"].id))
        out["trials"] = out.get("trials", 0) + sum(r["trials"] for r in rows)
        new_best, best_score = None, None
        with self.store.atomic():
            current = self.store.family(fid) or {}
            state = current.get("state") or {}
            demoted.update(int(v) for v in (state.get("robust_failed") or []))  # `counts` reads the set
            if not current.get("retired_at"):
                candidates = state.get("train_candidates")
                best_score = current.get("best_train")
                for r in rows:
                    if not counts(r):
                        continue
                    candidates = candidates_with(candidates, float(r["score"]), int(r["job"].version or 0), r["run_id"])
                    if best_score is None or float(r["score"]) > float(best_score):
                        best_score, new_best = float(r["score"]), r
                if candidates != state.get("train_candidates"):
                    self.store.set_state(fid, train_candidates=candidates)
                if new_best is not None:
                    self.store.update_family(fid, best_train=best_score, stall=0)
                    self.store.set_state(fid, best_train_run=new_best["run_id"], best_train_version=int(new_best["job"].version or 0))
                    out["improved"] = True
        # Every row of the sweep stays readable (`read_run`) until the family's next run prunes by age, as ever.
        self.store.prune_runs(fid, keep={r["run_id"] for r in rows})
        table, eligible, positive = [], 0, 0
        for r in rows:
            job = r["job"]
            ok = counts(r)
            eligible += ok
            positive += r["score"] is not None and r["score"] > 0
            row: dict[str, Any] = {
                "params": {k: v for k, v in job.params.items() if k not in base or base[k] != v},
                "run_id": r["run_id"], "version": job.version, "status": r["status"],
                "score": None if r["score"] is None else round(float(r["score"]), 3), "eligible": ok,
                "trades": r["trades"], "days": r["days"], "pnl": r["pnl"], "fill_rate": r["fill_rate"], "years": r["years"]}
            if r["eligible"] and r["status"] == "ok" and not ok:
                row["why_not"] = "this version lost money on Train at 1.5x the half-spread"
            elif not ok:
                row["why_not"] = str(r["why"] or "")[:160]
            if r["status"] != "ok":
                row["reason"] = str(r["reason"] or "")[:200]
            if r["reused"]:
                row["already_run"] = ALREADY_RUN  # evaluated before (NO DUPLICATE RUNS): read back, no new trial
            table.append(row)
        top = rows[0]
        top_score = next((float(r["score"]) for r in rows if counts(r)), None)
        reused = sum(1 for r in rows if r["reused"])
        if todo:  # a sweep read wholly from the store is no run: the cycle's REVISE goes on (NO DUPLICATE RUNS)
            out["run_id"] = top["run_id"]
            out["score"] = None if top_score is None else round(top_score, 3)
        out["sweep"] = {"variants": len(variants), "completed": sum(1 for r in rows if r["status"] == "ok"), "eligible": eligible,
                        "failed": len(failed)}
        if reused:
            out["sweep"]["reused"] = reused
            out["stored"] = out.get("stored", 0) + reused
        view: dict[str, Any] = {
            "status": "ok" if any(r["status"] == "ok" for r in rows) else str(top["status"] or "failed"),
            "run_id": top["run_id"], "version": top["job"].version, "base_params": dict(base),
            "variants": len(variants), "completed": out["sweep"]["completed"], "eligible": eligible, "positive_score": positive,
            "table": table, "lineage_trials": self.store.lineage_trials(fid),
            "next": "submit the best ROBUST row's run_id (a plateau of positive neighbours beats a lone peak), or read_run it"}
        if not todo:
            view["already_run"] = ALREADY_RUN
            view["next"] = ("every variant already ran on this window, roots and Gym: no new run, no trial. Submit a row, sweep "
                            "other variants, or call gym_run with hold=true if you have nothing new")
        if dropped:
            view["repeats_dropped"] = dropped
        if failed:
            view["failed"] = [{"params": {k: v for k, v in job.params.items() if k not in base or base[k] != v}, "version": job.version,
                               "error": why[:200]} for job, why in failed]
        if new_best is not None:
            view["new_best_train_score"] = round(float(best_score or 0.0), 3)
            job = new_best["job"]
            self.queue_robustness(fid, int(job.version or 0), code, dict(job.params), needs_roots(code, fam["roots"]))
        return view

    def _execute(self, fam: Mapping[str, Any], name: str, args: Mapping[str, Any], out: dict[str, Any], *, author: str) -> Any:
        if name == "retire":
            # Refused unless offered (`can_retire`); a refusal is a tool answer, never a cycle error (no backoff). The
            # family is read, judged and retired in one transaction, so its floor follows the state it retires in.
            with self.store.atomic():
                current = self.store.family(fam["id"]) or fam
                if not self.can_retire(current):
                    out["retire_refused"] = True
                    return {"status": "refused", "reason": "retire is not available to your family now (it needs at least two "
                                                           "validations and a population above its start, or many Gym "
                                                           "evaluations without an eligible Train version, or many cycles "
                                                           "of only holds and stored results): keep researching"}
                # The store checks the population atomically: a researcher's retirement never takes it to its start or
                # below, a dead family's (`idle_dead`) never to its floor or below.
                result = self.store.retire_gym(fam["id"], args.get("reason"), floor=self.retire_floor(current),
                                               source="researcher")
            if result["status"] == "retired":
                out["retired"] = True
                try:
                    self.pool.cancel_family(fam["id"])
                except Exception:  # queued work is also rejected by durable-state checks on the next cycle
                    pass
            else:
                out["retire_refused"] = True
            return result
        if name == "gym_run":
            return self._gym_run(fam, args, out, author=author)
        if name == "gym_sweep":
            return self._gym_sweep(fam, args, out, author=author)
        with self.store.atomic():  # local tools cannot change the best or notebook after another connection retires it
            if self._terminal(fam["id"], out):
                return {"status": "refused", "reason": "the family is retired; no further tools run"}
            result = self._local_tool(fam, name, args, out)
        if name == "submit" and isinstance(result, dict) and result.get("ok"):
            # A submitted version is validated next: its robustness runs are queued like a new best's (outside the store's
            # transaction, since the pool takes its own lock before the store's).
            version = self.store.version(fam["id"], int(result["best_version"]))
            if version and version.get("code"):
                self.queue_robustness(fam["id"], int(version["n"]), version["code"], version.get("params") or {},
                                      needs_roots(version["code"], fam["roots"]))
        return result

    def _local_tool(self, fam: Mapping[str, Any], name: str, args: Mapping[str, Any], out: dict[str, Any]) -> Any:
        if name == "read_run":
            run = self.store.run(str(args.get("run_id") or ""))
            if run is None or run["family"] != fam["id"] or run["window"] != "train":
                return {"error": "no such Train run of your family"}
            result = self.store.run_result(run["run_id"])
            if result is None:
                return {"error": "that run's full result is no longer kept (your newest six and your best are)",
                        "summary": run.get("summary")}
            return diagnostics.section(result, str(args.get("section") or "summary"), page=int(args.get("page") or 0))
        if name == "notebook":
            if args.get("action") == "append":
                text = str(args.get("text") or "").strip()
                if not text:
                    return {"error": "append needs text"}
                self.store.note(fam["id"], text)
                out["note"] = text
                return {"ok": True}
            return {"notebook": [diagnostics.scrub(n["text"]) for n in self.store.notebook(fam["id"], limit=12)]}
        if name == "graveyard":
            rows = self.store.graveyard(str(args.get("query") or ""), limit=5)
            return {"lessons": [{"family": r["family"], "mechanism": r["mechanism"][:200], "structure": r["structure"],
                                 "roots": r["roots"], "lesson": diagnostics.scrub(r["lesson"])[:600]} for r in rows]}
        if name == "submit":
            run = self.store.run(str(args.get("run_id") or ""))
            if run is None or run["family"] != fam["id"] or run["window"] != "train" or run["version"] is None:
                return {"error": "no such Train run of your family"}
            if run["status"] != "ok":
                return {"error": f"that run's status is {run['status']}: only a run that completed can be your best"}
            eligible, why = self.eligible_run(fam, run)
            if not eligible:
                return {"error": f"that run cannot be your best: {why}"}
            self.store.update_family(fam["id"], best_version=int(run["version"]))
            self.store.set_state(fam["id"], submitted_run=run["run_id"], submitted_note=str(args.get("note") or "")[:300])
            out["submitted"] = int(run["version"])
            return {"ok": True, "best_version": int(run["version"]),
                    "next": "the tournament validates it once its 1.5x robustness run on Train comes back with a profit"}
        return {"error": f"unknown tool {name}"}

    def eligible_run(self, fam: Mapping[str, Any], run: Mapping[str, Any]) -> tuple[bool, str]:
        """Can this Train run's version be the family's best? A run at the normal spread that the Train score finds
        eligible (its row's score, else its kept full result), of a version that has not lost at 1.5x the half-spread."""
        if float(run.get("stress") or 1.0) != 1.0 or run.get("purpose") not in (None, "train"):
            return False, "only a Train run of yours at the normal spread counts"
        state = (self.store.family(fam["id"]) or fam).get("state") or {}
        if int(run["version"]) in (state.get("robust_failed") or []):
            return False, "its version lost money on Train at 1.5x the half-spread"
        summary = run.get("summary") or {}
        if "train_eligible" in summary:
            return (True, "") if summary["train_eligible"] else (False, "it is not eligible under the Train score (40 trades on "
                                                                         "20 days in every Train year)")
        result = self.store.run_result(run["run_id"])
        if result is None:
            return False, "its full result is no longer kept, so its Train score cannot be checked: run it again"
        robust = evidence.train_score(result)
        return (True, "") if robust["eligible"] else (False, str(robust["why"]))

    # ------------------------------------------------------------------ robustness runs
    def queue_robustness(self, fid: str, n: int, code: str, params: Mapping[str, Any], roots: tuple[str, ...]) -> bool:
        """The Train runs of a best version (a new best by score, or a submitted one) at 1.5x the half-spread and at the
        mid that it does not have yet, at the pool's lowest priority (they fill idle boxes and never delay a researcher's
        run or a validation). Each counts as a trial when it lands; its compact figures go to the family's state
        (`robustness`), and a loss at 1.5x demotes the version (`robust_landed`). Not waited for; once per version in
        flight per process; a run the Gym executed and failed is queued again, up to `ROBUSTNESS_ATTEMPTS` failures a label
        (only executed runs count: a restart or a supersession charges nothing)."""
        submit = getattr(self.pool, "submit", None)
        if submit is None:
            return False
        with self.store.atomic():
            fam = self.store.family(fid) or {}
            if fam.get("retired_at"):
                return False
            rows = dict((fam.get("state") or {}).get("robustness") or {})
            row = dict(rows.get(str(n)) or {})
            tries = dict(row.get("failures") or {})
            need = [label for label in ("stress_1.5", "mid") if (fid, int(n), label) not in self._robust
                    and not landed(row.get(label)) and int(tries.get(label) or 0) < ROBUSTNESS_ATTEMPTS]
            if not need:
                return False
            row.update(queued_at=self.clock())
            rows[str(n)] = row
            for old in sorted(rows, key=lambda k: float((rows[k] or {}).get("queued_at") or 0))[:-6]:
                rows.pop(old, None)  # the last six versions' figures are kept
            self.store.set_state(fid, robustness=rows)
            self._robust.update((fid, int(n), label) for label in need)
        for label, stress in (("stress_1.5", evidence.STRESS), ("mid", 0.0)):
            if label not in need:
                continue
            job = GymJob(family=fid, version=int(n), code=code, params=dict(params or {}), window="train", roots=tuple(roots),
                         stress=stress, purpose="robustness", priority=ROBUSTNESS_PRIORITY)
            # Keyed like a researcher's run (NO DUPLICATE RUNS): a gym_run of this version at 1.5x reads it back.
            job.late = lambda result, label=label, stress=stress, job=job: self.robust_landed(
                fid, int(n), label, stress, result, key=self._result_key(job, result))
            job.late_fail = lambda why, label=label: self.robust_landed(fid, int(n), label, None, {"status": "failed", "reason": why})
            submit(job)
        return True

    def ensure_robustness(self, fam: Mapping[str, Any]) -> None:
        """The robustness runs of the family's best by Train score and of its submitted best, when they were never queued,
        a restart lost them, or one failed (`queue_robustness` caps the attempts)."""
        state = fam.get("state") or {}
        for n in {state.get("best_train_version"), fam.get("best_version")} - {None}:
            if int(n) in (state.get("robust_failed") or []):
                continue
            row = (state.get("robustness") or {}).get(str(n)) or {}
            tries = row.get("failures") or {}
            if all((fam["id"], int(n), label) in self._robust or landed(row.get(label)) or int(tries.get(label) or 0) >= ROBUSTNESS_ATTEMPTS
                   for label in ("stress_1.5", "mid")):
                continue
            version = self.store.version(fam["id"], int(n))
            if version and version.get("code"):
                self.queue_robustness(fam["id"], int(n), version["code"], version.get("params") or {},
                                      needs_roots(version["code"], fam["roots"]))

    def robust_landed(self, fid: str, n: int, label: str, stress: float | None, result: Mapping[str, Any], *,
                      key: str | None = None) -> None:
        """A robustness run's result (on the pool's dispatcher thread): recorded as a trial (under its evaluation `key`),
        its compact figures kept, and a loss at 1.5x the half-spread takes the version out of the family's best (the next
        candidate takes its place)."""
        try:
            fam = self.store.family(fid)
            if fam is None:
                return
            reason = str(result.get("reason") or "")
            ran = stress is not None or not any(word in reason for word in NOT_RUN)
            if stress is not None:
                years = float((result.get("summary") or {}).get("days") or 0) / 252.0 * max(1, len(fam["roots"]))
                self.store.add_run(fid, n, result, window="train", stress=stress, purpose="robustness", program_years=years,
                                   key=key)
            view = evidence.robustness_view(result) if stress is not None else {"status": "failed", "reason": reason[:200]}
            ok = result.get("status") == "ok"
            self._robust.discard((fid, int(n), label))  # landed or failed: a failure is queued again later, up to the attempts
            demoted = None
            with self.store.atomic():
                fam = self.store.family(fid) or fam
                state = fam.get("state") or {}
                rows = dict(state.get("robustness") or {})
                row = dict(rows.get(str(n)) or {})
                tries = dict(row.get("failures") or {})
                if not ok and ran:  # the Gym executed it and it failed, erred or did not finish: one attempt spent
                    tries[label] = int(tries.get(label) or 0) + 1
                row.update({label: view if ran else None, "failures": tries})
                rows[str(n)] = row
                self.store.set_state(fid, robustness=rows)
                pnl = view.get("pnl")
                why = None
                if label == "stress_1.5" and ok and isinstance(pnl, (int, float)) and pnl <= 0:
                    why = "lost money on Train at 1.5x the half-spread"
                elif label == "stress_1.5" and int(tries.get(label) or 0) >= ROBUSTNESS_ATTEMPTS:
                    why = f"its 1.5x run failed {ROBUSTNESS_ATTEMPTS} times"
                if why and not fam.get("retired_at"):
                    demoted = self._demote(fam, n, why=why)
            if demoted is not None:
                self.store.event("swarm.robustness", fid, {"version": n, "action": "demoted", "why": why, "next": demoted.get("version")})
                if demoted.get("version") is not None:
                    version = self.store.version(fid, int(demoted["version"]))
                    if version and version.get("code"):
                        self.queue_robustness(fid, int(demoted["version"]), version["code"], version.get("params") or {},
                                              needs_roots(version["code"], fam["roots"]))
        except Exception:  # noqa: BLE001 - on the dispatcher's thread: a robustness record never breaks the pool
            pass

    def _demote(self, fam: Mapping[str, Any], n: int, *, why: str = "lost money on Train at 1.5x the half-spread") -> dict[str, Any]:
        """Version `n` lost at 1.5x (or its 1.5x run failed every attempt): never the best again; the family's next
        eligible candidate becomes its best (under the store's transaction). `robust_why` keeps the reason for the status."""
        fid = fam["id"]
        state = fam.get("state") or {}
        failed = list(state.get("robust_failed") or [])
        if n not in failed:
            failed.append(int(n))
        whys = {**(state.get("robust_why") or {}), str(n): why}
        rest = [c for c in (state.get("train_candidates") or []) if int(c[1]) not in failed]
        fields: dict[str, Any] = {}
        values: dict[str, Any] = {"robust_failed": failed[-50:], "robust_why": {k: v for k, v in whys.items() if int(k) in failed[-50:]},
                                  "train_candidates": rest}
        nxt: dict[str, Any] = {"version": None}
        if state.get("best_train_version") == n:
            if rest:
                score, version, run_id = rest[0]
                fields.update(best_train=float(score), stall=0)
                values.update(best_train_version=int(version), best_train_run=run_id)
                nxt = {"version": int(version), "score": float(score)}
            else:
                fields.update(best_train=None)
                values.update(best_train_version=None, best_train_run=None)
        if fam.get("best_version") == n:
            fields.update(best_version=None)  # the tournament validates the best by Train score instead
        if state.get("validation_version") == n:
            # Validated before its 1.5x robustness run landed: it leaves the gate's queue, and live tuition (`bands.read`)
            # refuses a version whose gate outcome is "demoted".
            from .gate import run_sha

            version = self.store.version(fid, n)
            values.update(gate_ready=False)
            if version is not None:
                values.update(gate_outcome={"sha": run_sha(version), "result": "demoted", "at": self.clock()})
        if fields:
            self.store.update_family(fid, **fields)
        self.store.set_state(fid, **values)
        return nxt

    def _terminal(self, fid: str, out: dict[str, Any]) -> bool:
        fam = self.store.family(fid)
        retired = fam is None or bool(fam.get("retired_at"))
        if retired:
            out["retired"] = True
        return retired

    # ------------------------------------------------------------------ one cycle
    def cycle(self, fid: str) -> dict[str, Any]:
        began = self.clock()
        fam = self.store.family(fid)
        if fam is None or fam.get("retired_at"):
            return {"family": fid, "skipped": "retired"}
        n = int(fam["cycles"]) + 1
        out: dict[str, Any] = {"family": fid, "cycle": n, "model_calls": 0, "tool_calls": 0, "cost_usd": 0.0}
        try:
            if n == 1 and not self.store.versions(fid) and self.starter is not None and (fam.get("spec") or {}).get("signal"):
                self._first_cycle(fam, out)
            else:
                self._model_cycle(fam, out)
        except Exception as exc:  # noqa: BLE001 - a failed cycle is recorded, never raised into the loop
            out["error"] = f"{type(exc).__name__}: {getattr(exc, 'code', '') or str(exc)[:300]}"
        out["seconds"] = round(self.clock() - began, 2)
        self.store.bump(fid, cycles=1)
        self._count_dormancy(fid, out)
        self.store.event("swarm.cycle", fid, out)
        self._public_note(fid, out)
        return out

    def _count_dormancy(self, fid: str, out: dict[str, Any]) -> None:
        """DORMANCY, at the end of a Gym family's cycle. A new Gym evaluation (a trial) sets `dormant_cycles` to zero (it
        was already, as the evaluation was recorded: `_restart_dormancy`). A cycle that asked the Gym for a new evaluation
        the Gym did not make (a Gym error; a run, or every new variant of a sweep, that did not land in the cycle) leaves
        it: not the researcher's doing. Any other cycle with a stored result, a hold or a run call refused for its own
        doing (`_refusal`) adds one. A cycle with none of these (a sweep refused for room alone, a model error) leaves it.
        Outside the Gym band the count is zero: a Candidate holding while its forward record is measured is honest, and a
        family sent back to the Gym starts afresh."""
        evaluated = int(out.get("trials") or 0) > 0
        asked = "gym_error" in out or bool(out.get("gym_asked"))
        idle = bool(out.get("stored") or out.get("hold") or out.get("run_refused"))
        with self.store.atomic():
            fam = self.store.family(fid)
            if fam is None or fam.get("retired_at"):
                return
            count = dormant_count(fam)
            if fam.get("band") != "gym" or evaluated:
                new = 0
            elif idle and not asked:
                new = count + 1
            else:
                return
            if new != count:
                self.store.set_state(fid, dormant_cycles=new)
        if new:
            out["dormant_cycles"] = new

    def _first_cycle(self, fam: Mapping[str, Any], out: dict[str, Any]) -> None:
        code, params = self.starter({**(fam.get("spec") or {}), "id": fam["id"], "mechanism": fam["mechanism"],  # type: ignore[misc]
                                     "structure": fam["structure"], "roots": fam["roots"]})
        view = self._gym_run(fam, {"code": code, "params": params, "why": "the starter program"}, out, author="seed")
        items = [{"role": "user", "content": f"Cycle 1: your family's starter program (version 1) ran on Train.\n\n```python\n{code}\n```"
                                             f"\n\nIts diagnostic:\n{json.dumps(view, default=str)}"}]
        self.store.save_convo(fam["id"], [{"cycle": 1, "items": items}])
        with self.store.atomic():
            eligible = bool((view.get("train_score") or {}).get("eligible"))
            if view.get("status") == "ok" and view.get("run_id") and eligible and not self._terminal(fam["id"], out):
                self.store.update_family(fam["id"], best_version=int(view["version"]))
        out["starter"] = True

    def _profile(self, history_chars: int, fam: Mapping[str, Any] | None = None) -> tuple[str, str, int]:
        """(profile, reasoning effort, max output tokens) of a cycle's model call: the bandit's top `top_families` on
        `top_profile` at `top_reasoning_effort` (unless the swarm is at its hourly pace); the rest as before."""
        top = self.cfg.get("top_profile")
        if top and fam is not None and not self.pace() and self.is_top(fam, top=int(self.cfg.get("top_families", 10))):
            return (str(top), str(self.cfg.get("top_reasoning_effort", "low")),
                    int(self.cfg.get("top_max_output_tokens", self.cfg.get("max_output_tokens", 8000))))
        effort, most = str(self.cfg.get("reasoning_effort", "minimal")), int(self.cfg.get("max_output_tokens", 8000))
        if history_chars > int(self.cfg.get("long_history_chars", 60000)):
            return str(self.cfg.get("long_profile", "flash41_asap")), effort, most
        return str(self.cfg.get("profile", "flash_asap")), effort, most

    def _model_cycle(self, fam: dict[str, Any], out: dict[str, Any]) -> None:
        fid = fam["id"]
        self.ensure_robustness(fam)
        cycles, pending = self.store.convo(fid)
        cycles = self.trim([c for c in cycles if isinstance(c, dict)])
        n = int(fam["cycles"]) + 1
        current: list[dict[str, Any]] = []
        deadline = self.clock() + float(self.cfg.get("cycle_seconds", 170))
        gym_done = False
        ready = (fam.get("state") or {}).get("rewrite_ready")
        if ready and ready.get("code"):  # a stronger model's rewrite came back: it is this cycle's run
            self.store.set_state(fid, rewrite_ready=None)
            view = self._gym_run(fam, {"code": ready["code"], "why": f"a rewrite by {ready.get('profile')} after a stall"}, out,
                                 author=str(ready.get("profile") or "rewrite"))
            current.append({"role": "user", "content": f"After revisions without progress a stronger model ({ready.get('profile')}) "
                                                       f"rewrote your program:\n```python\n{ready['code']}\n```\nIts Train diagnostic:\n"
                                                       f"{json.dumps(view, default=str)[:9000]}"})
            out["rewrite"] = ready.get("profile")
            gym_done = new_run(view)
            pending = None  # the rewrite supersedes the queued input, including when the rewrite needs repair
            fam = self.store.family(fid) or fam
        if pending and not gym_done:  # the run asked for at the end of the last cycle (its call was answered "queued" then)
            # A queued sweep carries its tool's name; a run queued before sweeps existed carries none.
            tool = pending.get("name") if pending.get("name") in RUNS else "gym_run"
            result = self._execute(fam, tool, pending.get("arguments") or {}, out, author=pending.get("author") or "model")
            out["tool_calls"] += 1
            if result.get("status") == "gym_error":
                out["error"] = f"gym: {str(result.get('error') or '')[:200]}"
                tries = int(pending.get("tries") or 0) + 1
                if transient(str(result.get("error") or "")) and tries <= PENDING_RETRIES:
                    # A busy or restarting Gym: no model is paid to read that. The run stays queued for the next cycle
                    # and the family backs off (the scheduler's cooldown on an error).
                    self.store.save_convo(fid, cycles, {**pending, "tries": tries})
                    if int(fam.get("stall") or 0) >= int(self.cfg.get("stall_revisions", 5)):
                        self.request_rewrite(fam, out)
                    return
                # The Gym will not run it (or failed it three times): the model hears why and revises.
                current.append({"role": "user", "content": f"The {tool} you queued last cycle could not run: "
                                                           f"{str(result.get('error') or '')[:600]}. {result.get('hint') or ''}"})
            elif result.get("already_run"):  # NO DUPLICATE RUNS: no new run, so this cycle's REVISE turn follows
                current.append({"role": "user", "content": f"The {tool} you queued last cycle had already run: its stored "
                                                           f"result (no new Gym run, no trial):\n"
                                                           f"{json.dumps(result, default=str)[:12000]}"})
            elif completed_run(result):
                current.append({"role": "user", "content": f"The {tool} you queued last cycle ran:\n"
                                                           f"{json.dumps(result, default=str)[:12000]}"})
                gym_done = True
            else:
                current.append({"role": "user", "content": f"The {tool} you queued last cycle did not complete a Gym run:\n"
                                                           f"{json.dumps(result, default=str)[:12000]}"})
            fam = self.store.family(fid) or fam
        pending = None  # run, or superseded by the rewrite (its call was answered "queued" last cycle)
        if int(fam.get("stall") or 0) >= int(self.cfg.get("stall_revisions", 5)):
            self.request_rewrite(fam, out)
        current.append({"role": "user", "content": self.status(fam)})
        max_calls = int(self.cfg.get("max_model_calls", 3))
        max_tools = int(self.cfg.get("max_tool_calls", 8))
        # A model call that writes a program took 60-80 s on Sept 26 (DeepSeek-V4-Flash asap): after the first, a call
        # starts only with `min_call_seconds` of the cycle's budget left, so a cycle stays under three minutes.
        min_call = float(self.cfg.get("min_call_seconds", 75))
        while out["model_calls"] < max_calls and (out["model_calls"] == 0 or deadline - self.clock() >= min_call):
            if self._terminal(fid, out):
                break
            history = [i for c in cycles for i in c.get("items", [])]
            items = [{"role": "system", "content": self.system}, {"role": "user", "content": self.brief(fam)}]
            items += sanitize(history + current)
            chars = sum(len(json.dumps(i, default=str)) for i in items)
            profile, effort, most = self._profile(chars, fam)
            key = f"swarm:{fid}:c{n}:m{out['model_calls']}:{int(fam.get('revisions') or 0)}"
            # REVISE requires a run or a sweep (never retire); READ follows a completed run and offers every tool, retire
            # only when the family may retire (`can_retire`).
            revise = not gym_done
            tools = self.tools(revise=revise, retire=not revise and self.can_retire(fam))
            response = self.router.sail(profile, items, family=fid, key=key, tools=tools, effort=effort, max_output=most,
                                        cache_key=f"swarm-{fid}", cap_usd_day=float(self.cfg.get("family_usd_day", 2.0)),
                                        tool_choice="required" if revise else "auto")
            out["model_calls"] += 1
            out["cost_usd"] = round(out["cost_usd"] + float(response.cost_usd or 0), 6)
            out["profile"] = profile
            produced = [i for i in (response.output_items or []) if i.get("type") in ("message", "function_call")]
            current.extend(produced)
            calls = list(response.function_calls or [])
            if not calls:
                if response.output_text:
                    out["text"] = response.output_text[:600]
                if revise:
                    out["protocol_error"] = "required research action returned no tool call"
                    out.setdefault("error", f"model protocol: {out['protocol_error']}")
                break
            stop = False
            for call in calls:
                if self._terminal(fid, out):
                    current.append({"type": "function_call_output", "call_id": call.call_id,
                                    "output": json.dumps({"status": "refused", "reason": "the family is retired; no further tools run"})})
                    stop = True
                    continue
                hold = call.name == "gym_run" and holding(call.arguments)
                if call.name in RUNS and out.get("hold"):
                    # A hold ends the cycle: a run call after it in the same answer is neither run nor queued.
                    current.append({"type": "function_call_output", "call_id": call.call_id,
                                    "output": json.dumps({"status": "refused", "reason": "you held this cycle: nothing runs "
                                                          "after a hold; run it next cycle"})})
                    continue
                if call.name in RUNS and not hold and (out.get("run_id") or "gym_error" in out or
                                                       self.clock() > deadline - 30 or out["tool_calls"] >= max_tools) \
                        and pending is None and not call.error:
                    # One run (or one sweep) a cycle: this one opens the next cycle. Its call is answered now (every call keeps
                    # its output beside it in the history); its result arrives as a message when it has run.
                    pending = {"call_id": call.call_id, "name": call.name, "arguments": call.arguments, "author": profile}
                    stop = True
                    current.append({"type": "function_call_output", "call_id": call.call_id,
                                    "output": json.dumps({"status": "queued", "note": "this run opens your next cycle; its result "
                                                          "comes then"})})
                    continue
                if call.name in RUNS and pending is not None:
                    current.append({"type": "function_call_output", "call_id": call.call_id,
                                    "output": json.dumps({"error": "one run is already queued for your next cycle"})})
                    continue
                if call.name == "retire" and not any(t["name"] == "retire" for t in tools):  # not offered (REVISE, or `can_retire`)
                    result: Any = {"status": "refused", "reason": "retire is not offered on this turn: revise and run"}
                    out["retire_refused"] = True  # a plain refusal, never a cycle error (no backoff)
                elif out["tool_calls"] >= max_tools:
                    result = {"error": "this cycle's tool budget is spent; continue next cycle"}
                elif call.error:
                    result = {"error": call.error}
                else:
                    result = self._execute(fam, call.name, call.arguments, out, author=profile)
                    out["tool_calls"] += 1
                    if call.name in RUNS:
                        # A stored result is no new run: the REVISE turn goes on (NO DUPLICATE RUNS).
                        gym_done = gym_done or new_run(result)
                        if isinstance(result, dict) and result.get("status") == "gym_error":
                            out["error"] = f"gym: {str(result.get('error') or '')[:200]}"  # no further model call this cycle
                            stop = True
                        if isinstance(result, dict) and result.get("status") == "held":
                            stop = True  # a hold ends the cycle: nothing new to run
                current.append({"type": "function_call_output", "call_id": call.call_id,
                                "output": json.dumps(result, default=str)[:12000]})
                fam = self.store.family(fid) or fam
                if self._terminal(fid, out):
                    stop = True
            if stop or pending:
                break
        if self._terminal(fid, out):
            if pending:
                for item in current:
                    if item.get("type") == "function_call_output" and item.get("call_id") == pending.get("call_id"):
                        item["output"] = json.dumps({"status": "cancelled", "reason": "the family retired before the queued run started"})
            pending = None
        cycles.append({"cycle": n, "items": [i for i in current if i.get("type") != "reasoning"]})
        self.store.save_convo(fid, cycles, pending)
        out["pending_run"] = bool(self.store.convo(fid)[1])

    def trim(self, cycles: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """The history a call carries. Cut in CHUNKS (beyond `history_cycles`, back to `history_trim_to`) so the cached
        prefix stays the same for several cycles in a row (measured Sept 26: trimming one cycle every cycle held the
        cache share near 44%); tool outputs older than the last cycle shortened to `old_output_chars`."""
        keep = int(self.cfg.get("history_cycles", 4))
        if len(cycles) > keep:
            cycles = cycles[-int(self.cfg.get("history_trim_to", 2)):]
        limit = int(self.cfg.get("old_output_chars", 2500))
        out = []
        for i, cycle in enumerate(cycles):
            if i < len(cycles) - 1:
                items = []
                for item in cycle.get("items", []):
                    if item.get("type") == "function_call_output" and len(str(item.get("output") or "")) > limit:
                        item = {**item, "output": str(item["output"])[:limit] + " ...(shortened; read_run has it)"}
                    elif item.get("role") == "user" and len(str(item.get("content") or "")) > 2 * limit:
                        item = {**item, "content": str(item["content"])[:2 * limit] + " ...(shortened)"}
                    items.append(item)
                cycle = {**cycle, "items": items}
            out.append(cycle)
        return out

    def request_rewrite(self, fam: Mapping[str, Any], out: dict[str, Any]) -> bool:
        """A stall buys ONE rewrite from a stronger model, asked in the background (V4-Pro's balanced window took minutes
        on Sept 26; a cycle never waits for it): the program comes back into the family's state and is the run of its
        next cycle. At most `rewrites_per_day` a family a day, `rewrite_min_hours` apart; the stall counter restarts."""
        fid = fam["id"]
        fam = self.store.family(fid) or fam
        if self._terminal(fid, out):
            return False
        state = fam.get("state") or {}
        now = self.clock()
        today = [t for t in (state.get("rewrite_times") or []) if now - float(t) < 86400]
        if self.pace():
            return False
        if fid in self._rewriting or state.get("rewrite_ready") or len(today) >= int(self.cfg.get("rewrites_per_day", 4)) \
                or (today and now - max(float(t) for t in today) < 3600 * float(self.cfg.get("rewrite_min_hours", 1.0))):
            return False
        is_top = self.is_top(fam, top=int(self.cfg.get("top_rewrite_families", 10)))
        profile = str(self.cfg.get("top_rewrite_profile" if is_top else "rewrite_profile", "pro_balanced"))
        latest = self.store.latest_version(fid)
        best = self.store.version(fid, fam.get("best_version")) or latest
        runs = [r for r in self.store.runs(fid, window="train", limit=8) if r.get("purpose") != "robustness"][:1]
        last_view = diagnostics.train_view(self.store.run_result(runs[0]["run_id"]) or {}) if runs else {}
        notes = "\n".join(f"- {diagnostics.scrub(n['text'])[:400]}" for n in self.store.notebook(fid, limit=10))
        user = (f"{self.brief(fam)}\n\nThis family has gone {fam['stall']} revisions without a better Train score. Write a NEW "
                f"program for the same mechanism, structure and roots that fixes what the diagnostics show. Reply with the "
                f"whole file in one ```python block, then one sentence on what changed.\n\nIts notebook:\n{notes or '(empty)'}\n\n"
                f"Its best version so far:\n```python\n{(best or {}).get('code') or ''}\n```\n\nThe latest Train diagnostic:\n"
                f"{json.dumps(last_view, default=str)[:8000]}")
        key = f"swarm:{fid}:rewrite:{int(fam.get('rewrites') or 0)}:{int(fam.get('revisions') or 0)}"
        with self.store.atomic():
            if self._terminal(fid, out):
                return False
            self.store.bump(fid, rewrites=1)
            self.store.update_family(fid, stall=0)
            self.store.set_state(fid, rewrite_times=today + [now])
        out["rewrite_asked"] = profile

        def job() -> None:
            try:
                if (self.store.family(fid) or {}).get("retired_at"):
                    return
                answer = self.router.ask(role="rewrite", system=self.system, user=user, family=fid, key=key, openai_model=None,
                                         sail_profile=profile, max_output=12000, effort="medium", desk=f"{fid}:rewrite",
                                         cap_usd_day=float(self.cfg.get("rewrite_usd_day", 1.0)))
                match = CODE_BLOCK.search(answer.get("text") or "")
                if match:
                    value = {"code": match.group(1), "profile": profile, "at": self.clock()}
                    with self.store.atomic():
                        if (self.store.family(fid) or {}).get("retired_at"):
                            self.store.set_state(fid, rewrite_after_retirement=value)
                        else:
                            self.store.set_state(fid, rewrite_ready=value)
                else:
                    self.store.set_state(fid, rewrite_error="the rewrite carried no program")
            except Exception as exc:  # noqa: BLE001 - a failed rewrite is recorded; the family goes on
                self.store.set_state(fid, rewrite_error=f"{type(exc).__name__}: {str(exc)[:200]}")
            finally:
                self._rewriting.pop(fid, None)

        if self.background:
            import threading

            thread = threading.Thread(target=job, name=f"rewrite-{fid}", daemon=True)
            self._rewriting[fid] = thread
            thread.start()
        else:
            job()
        return True

    def _public_note(self, fid: str, out: Mapping[str, Any]) -> None:
        """A notebook entry to the site's tape (as `swarm.note`), at most every `note_every_cycles` cycles, and only its
        plain-word sentences: no digit, no code, no parameter name of the program (`public.note_text`; the notebook
        keeps everything, privately)."""
        if (self.store.family(fid) or {}).get("retired_at"):
            return
        latest = self.store.latest_version(fid) or {}
        names = public.param_names_of(latest.get("code")) + list((latest.get("params") or {}).keys())
        text = public.note_text(out.get("note"), param_names=names)
        if not text:
            return
        with self.store.atomic():
            fam = self.store.family(fid) or {}
            if fam.get("retired_at"):
                return
            state = fam.get("state") or {}
            last = int(state.get("public_note_cycle") or -10**6)
            if int(out.get("cycle") or 0) - last < int(self.cfg.get("note_every_cycles", 6)):
                return
            self.store.set_state(fid, public_note_cycle=int(out.get("cycle") or 0))
            self.store.event("swarm.note", fid, {"text": text})


#: The Train objective the families' bests are chosen by (`store.get("train_objective")`).
OBJECTIVE = "worst-train-year-v1"


def migrate_objective(store: SwarmStore, *, beat: Callable[[], None] | None = None, beat_seconds: float = 10.0) -> dict[str, Any]:
    """Once per store (the swarm's start): every living family's best chosen ANEW under `evidence.train_score`, so an old
    score (the full-Train t with a 30-trade floor) is never compared with a new one. Its kept full Train runs at the
    normal spread are rescored; the eligible best becomes both its best by Train score and its submitted best (none: both
    empty until an eligible run comes). The old selection stays in the family's state as `legacy_best`. The stall
    counter restarts. Returns {"migrated", "with_best", "failed"} (zeros when it already ran).

    Restart-safe (the House restarts a swarm whose heartbeat is 240 s old): `beat` is called at least every `beat_seconds`
    (the heartbeat); a family already carrying `legacy_best` was done by an earlier, interrupted pass and is skipped (its
    record is never overwritten); an unreadable result is skipped, and a family whose rescoring fails anyway has its
    best emptied (never an old score beside new ones) and is named in the `swarm.status` event."""
    if store.get("train_objective") == OBJECTIVE:
        return {"migrated": 0, "with_best": 0, "failed": 0}
    migrated = with_best = 0
    failed: list[str] = []
    last = time.monotonic()
    for fam in store.families(alive=True):
        fid = fam["id"]
        state = fam.get("state") or {}
        if "legacy_best" in state:
            continue
        legacy = {"best_train": fam.get("best_train"), "best_version": fam.get("best_version"),
                  "best_train_version": state.get("best_train_version"), "best_train_run": state.get("best_train_run"),
                  "objective": "full-Train t_daily, 30-trade floor", "replaced_by": OBJECTIVE}
        try:
            rows: list[list[Any]] = []
            for run in store.runs(fid, window="train", limit=1000):
                if run["status"] != "ok" or float(run["stress"] or 1.0) != 1.0 or run.get("purpose") == "robustness" or not run.get("path"):
                    continue
                if beat is not None and time.monotonic() - last >= beat_seconds:
                    beat()
                    last = time.monotonic()
                result = store.run_result(run["run_id"])
                try:
                    robust = evidence.train_score(result) if result is not None else None
                except Exception:  # noqa: BLE001 - a malformed result is no candidate
                    robust = None
                if robust is not None and robust["eligible"] and run.get("version") is not None:
                    rows = candidates_with(rows, float(robust["score"]), int(run["version"]), run["run_id"])
            best = rows[0] if rows else None
            with store.atomic():
                if (store.family(fid) or {}).get("retired_at"):
                    continue
                store.update_family(fid, best_train=float(best[0]) if best else None, best_version=int(best[1]) if best else None,
                                    stall=0)
                store.set_state(fid, legacy_best=legacy, best_train_version=int(best[1]) if best else None,
                                best_train_run=best[2] if best else None, train_candidates=rows, robust_failed=[], robustness={})
            migrated += 1
            with_best += bool(best)
        except Exception as exc:  # noqa: BLE001 - one family never stops the swarm's start
            failed.append(fid)
            try:
                with store.atomic():
                    store.update_family(fid, best_train=None, best_version=None, stall=0)
                    store.set_state(fid, legacy_best={**legacy, "error": f"{type(exc).__name__}: {str(exc)[:200]}"},
                                    best_train_version=None, best_train_run=None, train_candidates=[], robust_failed=[], robustness={})
            except Exception:  # noqa: BLE001
                pass
    store.put("train_objective", OBJECTIVE)
    out = {"migrated": migrated, "with_best": with_best, "failed": len(failed)}
    store.event("swarm.status", None, {"action": "train_objective", "objective": OBJECTIVE, **out, "failed_families": failed[:50]})
    return out


__all__ = ["Researcher", "TOOLS", "TOOLS_READ", "TOOLS_REVISE", "RUNS", "needs_of", "needs_roots", "with_roots", "check_code",
           "sanitize", "date_like", "candidates_with", "migrate_objective", "OBJECTIVE", "params_of", "check_params",
           "sweep_variants", "sweep_tool", "merged_key", "MAX_SWEEP_VARIANTS", "MAX_SWEEP_JOBS_IN_FLIGHT", "idle_dead",
           "idle_evaluations", "idle_limit", "RETIRE_IDLE_EVALUATIONS", "NEGATIVE_FACTOR", "DORMANT_CYCLES", "ALREADY_RUN",
           "dormant_limit", "dormant_count", "awaiting_validation", "holding", "held_at_gate", "new_run"]
