"""The inner loop: one researcher per family, revise -> run -> read -> revise.

A CYCLE is at most one Gym run and a few model calls, bounded by `max_model_calls`, `max_tool_calls`
and `cycle_seconds` (the target is under three minutes). In the steady state a cycle is: run the program
the researcher asked for at the end of its last cycle (a `gym_run` carried over), show it the result, let
it read, write its notebook and revise, and carry its next `gym_run` to the next cycle. A family's very
first cycle runs its starter program without a model call (seeds only).

THE TOOLS (`TOOLS`): `gym_run` (a new version on Train; its compact diagnostic), `read_run` (a section of
a past Train run), `notebook` (append / read: its memory), `graveyard` (lessons of retired families),
`submit` (make an eligible version its best: the tournament validates it), `retire` (explicitly abandon the entire
Gym family). The contract (`league/CONTRACT.md`) is the shared, cached prefix of every call; each family's calls carry
its own `prompt_cache_key`.

RETIRE (Sept 26: an unguarded `retire` on the REVISE turn took the population from 49 to 16 in 24 minutes). A REVISE
turn offers `gym_run` alone: a REVISE always revises. A READ turn offers `retire` only while more families live than
`population.start` and the family has had at least two validations (`can_retire`); a retire that is refused anyway
is a plain refusal, never a cycle error (an error backs the family off for up to 30 minutes). The tournament's own
retirements are unchanged.

WHAT IT SEES. Train in full; of Validation only pass or fail and how many of the line's checks passed (the owner's
decision D2a, `diagnostics.validation_view`); of the holdout only the gate's pass or fail. Never a date in ctx (the
Gym enforces it; the safety check refuses date literals before a program reaches the Gym).

THE BEST (the robust Train objective, Sept 26): `evidence.train_score`, the worst Train year's daily t times the
share of Train quarters positive, and a version is eligible only with 40 trades on 20 days in every Train year. A new
best queues two ROBUSTNESS runs of it on Train (1.5x the half-spread and the mid) at the pool's lowest priority; they
come back into the family's status, count as trials, and a version that loses at 1.5x is never the best again
(`robust_failed`; the next eligible candidate takes its place). `migrate_objective` chose every living family's best
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
import json
import re
import time
from pathlib import Path
from typing import Any, Callable, Mapping

from . import diagnostics, evidence, public
from .pool import ROBUSTNESS_PRIORITY, GymJob, PoolError
from .store import SwarmStore

CONTRACT = Path(__file__).resolve().parents[1] / "CONTRACT.md"

TOOLS: list[dict[str, Any]] = [
    {"name": "gym_run", "description": "Run a version of your program on the Train window in the Gym and get its compact "
                                       "diagnostic. `code` is the whole program file (omit it to rerun your latest version, e.g. "
                                       "with other params). One run per cycle: a second call runs at the start of your next cycle.",
     "parameters": {"type": "object", "properties": {
         "code": {"type": "string", "description": "the complete program: NEEDS, PARAMS, decide(ctx)"},
         "params": {"type": "object", "description": "PARAMS overrides for this run (keys must exist in PARAMS)"},
         "stress": {"type": "number", "description": "half-spread multiplier, 1.0 (default) or 1.5 (the gate's stress)"},
         "why": {"type": "string", "description": "one sentence: what this version changes and why it should help"},
         "note": {"type": "string", "description": "optional: what you learned from your last run, appended to your notebook. "
                                                   "PUBLIC: it may appear on the public site, so describe the mechanism and "
                                                   "your reasoning only, never a threshold, level, delta, ratio or any other "
                                                   "fitted value (in digits or in words)"}}}},
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
                                     "and your family has had at least two validations.",
     "parameters": {"type": "object", "properties": {"reason": {"type": "string", "description": "Why the entire mechanism "
                    "is abandoned; retained in the private notebook and graveyard."}}, "required": ["reason"]}},
]

#: A REVISE turn requires a run (a REVISE always revises: `retire` is never offered there); a missing call fails and
#: uses the normal backoff.
TOOLS_REVISE: list[dict[str, Any]] = [TOOLS[0]]
#: A READ turn without `retire` (the family may not retire now: `Researcher.can_retire`).
TOOLS_READ: list[dict[str, Any]] = TOOLS[:-1]

ROLE = """You are a researcher in the LTCM options swarm. You own one family and improve its program in the Gym.
Work in short cycles. REVISE: call gym_run with your revised program (the whole file in `code`, or only `params` to
change parameters) and put what you learned from the last run in its `note`. A REVISE always revises: never repeat an
empty or unchanged program. READ: when the result comes back, read it; submit the run if it is your best; queue your
next gym_run (it opens your next cycle); use read_run, graveyard or the notebook only when the diagnostic leaves you
unsure. Keep every program inside the contract below; the Gym refuses anything else. Reply with tool calls; keep prose
short.
THE TRAIN SCORE you climb is your WORST Train year's daily t, times the share of Train quarters that were positive. A
version counts only with at least 40 trades on at least 20 days in EVERY Train year, and never if it loses money at 1.5x
the half-spread (the Gym re-runs each new best at 1.5x and at the mid; the results come back in your status). Seek a
mechanism that earns in every year, not a filter that shines in one.
Your family trades one to five of the Gym's roots; to change them, name the new roots in your program's NEEDS.
The retire tool appears only while the population is above its start and your family has had at least two
validations. Call it only when you abandon the entire mechanism, not one rejected version. Retirement is final for
the family and preserves its best program and all evidence.
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
        #: (family, version) whose robustness runs this process queued (a restart loses queued jobs: they are queued again).
        self._robust: set[tuple[str, int]] = set()
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
        parts = [f"Cycle {int(fam['cycles']) + 1}. Versions so far: {fam['revisions']}. Lineage trials: "
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
        if notes:
            parts.append("Your notebook (latest):\n" + "\n".join(f"- {n['text'][:300]}" for n in notes))
        parts.append("Now: if a run just came back, read it (submit it if it is your best) and queue your next gym_run; "
                     "otherwise revise and call gym_run, with what you learned in its note."
                     + (" If you abandon the entire mechanism, call retire with your reason." if self.can_retire(fam) else ""))
        return "\n".join(parts)

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
            out.append(f"Versions that lost money on Train at 1.5x the half-spread and can never be your best: "
                       f"{', '.join(str(v) for v in failed[-8:])}.")
        return " ".join(out)

    # ------------------------------------------------------------------ retirement, the top ten
    def can_retire(self, fam: Mapping[str, Any]) -> bool:
        """`retire` is offered (and accepted) only for a Gym family with at least two validations while more families live
        than `population.start` (the sprint, Sept 26)."""
        if fam.get("band") != "gym" or int(fam.get("validations") or 0) < 2:
            return False
        return len(self.store.families(alive=True)) > int(self.settings.get("population", {}).get("start", 48))

    def is_top(self, fam: Mapping[str, Any], *, top: int) -> bool:
        """Among the bandit's `top` families by weight (a weight of zero or none never is)."""
        weight_rank = sorted((f.get("weight") or 0.0 for f in self.store.families(alive=True)), reverse=True)
        return bool(weight_rank) and top > 0 and (fam.get("weight") or 0.0) >= weight_rank[min(top, len(weight_rank)) - 1] > 0

    # ------------------------------------------------------------------ tools
    def _gym_run(self, fam: Mapping[str, Any], args: Mapping[str, Any], out: dict[str, Any], *, author: str) -> dict[str, Any]:
        if self._terminal(fam["id"], out):
            return {"status": "retired", "reason": "the family is retired; no run started"}
        code = args.get("code")
        if not code:
            latest = self.store.latest_version(fam["id"])
            if latest is None or not latest.get("code"):
                return {"error": "you have no version yet: pass `code`"}
            code = latest["code"]
        code = str(code)
        dated = [k for k, v in (args.get("params") or {}).items()] if isinstance(args.get("params"), dict) else []
        dated = [k for k in dated if date_like(args["params"][k])]
        if dated:
            return {"status": "refused", "reason": f"a date or a year in the parameter overrides ({', '.join(dated)}): no program may "
                                                   "see the calendar", "hint": "use relative measures, never a date, a year or a level"}
        note = str(args.get("note") or "").strip()
        if note:
            self.store.note(fam["id"], note)
            out["note"] = note
        params = args.get("params") if isinstance(args.get("params"), dict) else {}
        stress = float(args.get("stress") or 1.0)
        if stress not in (1.0, 1.5):
            stress = 1.0
        why = check_code(code)
        if why:
            out["refused"] = out.get("refused", 0) + 1
            return {"status": "refused", "reason": why[:600], "hint": "fix the rule named (the contract) and run again"}
        needs = needs_of(code)
        if needs is None:
            return {"status": "refused", "reason": "NEEDS must be a literal dict at the top level"}
        roots = list(needs_roots(code))
        admitted = [str(r).upper() for r in self.settings.get("gym", {}).get("roots", [])]
        change = bool(roots) and set(roots) != set(fam["roots"])
        if change:
            outside = [r for r in roots if r not in admitted]
            if outside:
                return {"status": "refused", "reason": f"NEEDS names {', '.join(outside)}, not in the Gym's roots ({', '.join(admitted)})"}
            if len(roots) > MAX_ROOTS:
                return {"status": "refused", "reason": f"a family holds at most {MAX_ROOTS} roots; NEEDS names {len(roots)}"}
            if fam.get("band") != "gym":
                return {"status": "refused", "reason": f"your family trades {', '.join(fam['roots'])} in its band; only a Gym family "
                                                       "changes its roots"}
        with self.store.atomic():
            if self._terminal(fam["id"], out):
                return {"status": "retired", "reason": "the family is retired; no run started"}
            if change:  # a new version on other roots of the admitted list: the family's slice follows it
                self.store.update_family(fam["id"], roots=roots)
                self.store.note(fam["id"], f"Roots changed from {', '.join(fam['roots'])} to {', '.join(roots)}.")
                out["roots"] = roots
                fam = {**fam, "roots": roots}
            version = self.store.add_version(fam["id"], code, params, author=author, note=str(args.get("why") or "")[:300])
        job = GymJob(family=fam["id"], version=version["n"], code=code, params=params, window="train", roots=tuple(fam["roots"]),
                     stress=stress, purpose="train", priority=float(fam.get("weight") or 0.0))
        began = self.clock()
        try:
            def late(result: Mapping[str, Any], fid: str = fam["id"], n: int = version["n"], stress: float = stress) -> None:
                days = float((result.get("summary") or {}).get("days") or 0)
                self.store.add_run(fid, n, result, window="train", stress=stress, purpose="train",
                                   program_years=days / 252.0 * max(1, len(fam["roots"])))

            if self._terminal(fam["id"], out):
                return {"status": "retired", "reason": "the family is retired; no run started"}
            result = self.pool.run(job, timeout=float(self.settings.get("gym", {}).get("run_timeout_seconds", 900)) + 120, late=late)
        except PoolError as exc:
            out["gym_error"] = str(exc)[:300]
            return {"status": "gym_error", "version": version["n"], "error": str(exc)[:500],
                    "hint": "the Gym could not run it now; your version is saved: rerun it next cycle"}
        out["gym_seconds"] = round(self.clock() - began, 2)
        years = float((result.get("summary") or {}).get("days") or 0) / 252.0 * max(1, len(fam["roots"]))
        robust = evidence.train_score(result) if stress == 1.0 else None
        recorded = result
        if robust is not None and isinstance(result.get("summary"), Mapping):  # the run's row keeps its score (`submit` reads it)
            recorded = {**result, "summary": {**result["summary"], "train_score": robust["score"], "train_eligible": robust["eligible"]}}
        run = self.store.add_run(fam["id"], version["n"], recorded, window="train", stress=stress, purpose="train",
                                 program_years=years)
        out["run_id"] = run["run_id"]
        out["trials"] = out.get("trials", 0) + int(run["trials"])
        view = diagnostics.train_view(result, lineage_trials=self.store.lineage_trials(fam["id"]))
        view["version"] = version["n"]
        view["run_id"] = run["run_id"]
        score = robust["score"] if robust is not None and robust["eligible"] else None
        best = False
        with self.store.atomic():
            current = self.store.family(fam["id"]) or {}
            state = current.get("state") or {}
            failed = version["n"] in (state.get("robust_failed") or [])
            if not current.get("retired_at") and score is not None and not failed:
                self.store.set_state(fam["id"], train_candidates=candidates_with(state.get("train_candidates"), score, version["n"],
                                                                                 run["run_id"]))
                if current.get("best_train") is None or score > float(current["best_train"]):
                    self.store.update_family(fam["id"], best_train=score, stall=0)
                    self.store.set_state(fam["id"], best_train_run=run["run_id"], best_train_version=version["n"])
                    view["new_best_train_score"] = round(score, 3)
                    out["improved"] = True
                    best = True
        if robust is not None:
            view["train_score"] = {"score": robust["score"], "eligible": robust["eligible"] and not failed,
                                   "worst_year": robust["worst_year"], "quarters_positive": robust["quarters"], "by_year": robust["years"]}
            if not robust["eligible"]:
                view["train_score"]["why_not_eligible"] = robust["why"]
            elif failed:
                view["train_score"]["why_not_eligible"] = "this version lost money on Train at 1.5x the half-spread"
        out["score"] = None if score is None else round(score, 3)
        if best:
            self.queue_robustness(fam["id"], version["n"], code, params, needs_roots(code, fam["roots"]))
        return view

    def _execute(self, fam: Mapping[str, Any], name: str, args: Mapping[str, Any], out: dict[str, Any], *, author: str) -> Any:
        if name == "retire":
            # Refused unless offered (`can_retire`); a refusal is a tool answer, never a cycle error (no backoff).
            if not self.can_retire(self.store.family(fam["id"]) or fam):
                out["retire_refused"] = True
                return {"status": "refused", "reason": "retire is not available to your family now (it needs at least two "
                                                       "validations and a population above its start): keep researching"}
            result = self.store.retire_gym(fam["id"], args.get("reason"),
                                           floor=int(self.settings.get("population", {}).get("floor", 16)), source="researcher")
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
        with self.store.atomic():  # local tools cannot change the best or notebook after another connection retires it
            if self._terminal(fam["id"], out):
                return {"status": "refused", "reason": "the family is retired; no further tools run"}
            return self._local_tool(fam, name, args, out)

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
            return {"notebook": [n["text"] for n in self.store.notebook(fam["id"], limit=12)]}
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
            return {"ok": True, "best_version": int(run["version"]), "next": "the tournament validates it within the hour"}
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
        """Two Train runs of a new best version, at 1.5x the half-spread and at the mid, at the pool's lowest priority (they
        fill idle boxes and never delay a researcher's run or a validation). Each counts as a trial when it lands; its
        compact figures go to the family's state (`robustness`), and a loss at 1.5x demotes the version (`robust_landed`).
        Not waited for; once per version per process."""
        submit = getattr(self.pool, "submit", None)
        if submit is None or (fid, int(n)) in self._robust:
            return False
        self._robust.add((fid, int(n)))
        with self.store.atomic():
            fam = self.store.family(fid) or {}
            if fam.get("retired_at"):
                return False
            rows = dict((fam.get("state") or {}).get("robustness") or {})
            rows[str(n)] = {"stress_1.5": None, "mid": None, "queued_at": self.clock()}
            for old in sorted(rows, key=lambda k: float((rows[k] or {}).get("queued_at") or 0))[:-4]:
                rows.pop(old, None)  # the last four versions' figures are kept
            self.store.set_state(fid, robustness=rows)
        for label, stress in (("stress_1.5", evidence.STRESS), ("mid", 0.0)):
            job = GymJob(family=fid, version=int(n), code=code, params=dict(params or {}), window="train", roots=tuple(roots),
                         stress=stress, purpose="robustness", priority=ROBUSTNESS_PRIORITY)
            job.late = lambda result, label=label, stress=stress: self.robust_landed(fid, int(n), label, stress, result)
            job.late_fail = lambda why, label=label: self.robust_landed(fid, int(n), label, None, {"status": "failed", "reason": why})
            submit(job)
        return True

    def ensure_robustness(self, fam: Mapping[str, Any]) -> None:
        """The best version's robustness runs, when they were never queued or a restart lost them."""
        state = fam.get("state") or {}
        n = state.get("best_train_version")
        if n is None or (fam["id"], int(n)) in self._robust:
            return
        rows = (state.get("robustness") or {}).get(str(n)) or {}
        if rows.get("stress_1.5") and rows.get("mid"):
            return
        version = self.store.version(fam["id"], int(n))
        if version and version.get("code"):
            self.queue_robustness(fam["id"], int(n), version["code"], version.get("params") or {},
                                  needs_roots(version["code"], fam["roots"]))

    def robust_landed(self, fid: str, n: int, label: str, stress: float | None, result: Mapping[str, Any]) -> None:
        """A robustness run's result (on the pool's dispatcher thread): recorded as a trial, its compact figures kept,
        and a loss at 1.5x the half-spread takes the version out of the family's best (the next candidate takes its place)."""
        try:
            fam = self.store.family(fid)
            if fam is None:
                return
            if stress is not None:
                years = float((result.get("summary") or {}).get("days") or 0) / 252.0 * max(1, len(fam["roots"]))
                self.store.add_run(fid, n, result, window="train", stress=stress, purpose="robustness", program_years=years)
            view = evidence.robustness_view(result) if stress is not None else {"status": "failed",
                                                                                "reason": str(result.get("reason") or "")[:200]}
            demoted = None
            with self.store.atomic():
                fam = self.store.family(fid) or fam
                state = fam.get("state") or {}
                rows = dict(state.get("robustness") or {})
                rows[str(n)] = {**(rows.get(str(n)) or {}), label: view}
                self.store.set_state(fid, robustness=rows)
                pnl = view.get("pnl")
                if label == "stress_1.5" and result.get("status") == "ok" and isinstance(pnl, (int, float)) and pnl <= 0 \
                        and not fam.get("retired_at"):
                    demoted = self._demote(fam, n)
            if demoted is not None:
                self.store.event("swarm.robustness", fid, {"version": n, "action": "demoted", "next": demoted.get("version")})
                if demoted.get("version") is not None:
                    version = self.store.version(fid, int(demoted["version"]))
                    if version and version.get("code"):
                        self.queue_robustness(fid, int(demoted["version"]), version["code"], version.get("params") or {},
                                              needs_roots(version["code"], fam["roots"]))
        except Exception:  # noqa: BLE001 - on the dispatcher's thread: a robustness record never breaks the pool
            pass

    def _demote(self, fam: Mapping[str, Any], n: int) -> dict[str, Any]:
        """Version `n` lost at 1.5x: never the best again; the family's next eligible candidate becomes its best (under
        the store's transaction)."""
        fid = fam["id"]
        state = fam.get("state") or {}
        failed = list(state.get("robust_failed") or [])
        if n not in failed:
            failed.append(int(n))
        rest = [c for c in (state.get("train_candidates") or []) if int(c[1]) not in failed]
        fields: dict[str, Any] = {}
        values: dict[str, Any] = {"robust_failed": failed[-50:], "train_candidates": rest}
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
        self.store.event("swarm.cycle", fid, out)
        self._public_note(fid, out)
        return out

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
            gym_done = completed_run(view)
            pending = None  # the rewrite supersedes the queued input, including when the rewrite needs repair
            fam = self.store.family(fid) or fam
        if pending and not gym_done:  # the run asked for at the end of the last cycle (its call was answered "queued" then)
            result = self._execute(fam, "gym_run", pending.get("arguments") or {}, out, author=pending.get("author") or "model")
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
                current.append({"role": "user", "content": "The gym_run you queued last cycle could not run: "
                                                           f"{str(result.get('error') or '')[:600]}. {result.get('hint') or ''}"})
            elif completed_run(result):
                current.append({"role": "user", "content": f"The gym_run you queued last cycle ran:\n{json.dumps(result, default=str)[:12000]}"})
                gym_done = True
            else:
                current.append({"role": "user", "content": "The gym_run you queued last cycle did not complete a Gym run:\n"
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
            # REVISE requires a run (never retire); READ follows a completed run and offers every tool, retire only when
            # the family may retire (`can_retire`).
            revise = not gym_done
            tools = TOOLS_REVISE if revise else (TOOLS if self.can_retire(fam) else TOOLS_READ)
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
                if call.name == "gym_run" and (out.get("run_id") or "gym_error" in out or
                                              self.clock() > deadline - 30 or out["tool_calls"] >= max_tools) \
                        and pending is None and not call.error:
                    # One run a cycle: this one opens the next cycle. Its call is answered now (every call keeps its output
                    # beside it in the history); its result arrives as a message when it has run.
                    pending = {"call_id": call.call_id, "arguments": call.arguments, "author": profile}
                    stop = True
                    current.append({"type": "function_call_output", "call_id": call.call_id,
                                    "output": json.dumps({"status": "queued", "note": "this run opens your next cycle; its result "
                                                          "comes then"})})
                    continue
                if call.name == "gym_run" and pending is not None:
                    current.append({"type": "function_call_output", "call_id": call.call_id,
                                    "output": json.dumps({"error": "one run is already queued for your next cycle"})})
                    continue
                if call.name == "retire" and tools is not TOOLS:  # not offered (a REVISE turn, or `can_retire` said no)
                    result: Any = {"status": "refused", "reason": "retire is not offered on this turn: revise and run"}
                    out["retire_refused"] = True  # a plain refusal, never a cycle error (no backoff)
                elif out["tool_calls"] >= max_tools:
                    result = {"error": "this cycle's tool budget is spent; continue next cycle"}
                elif call.error:
                    result = {"error": call.error}
                else:
                    result = self._execute(fam, call.name, call.arguments, out, author=profile)
                    out["tool_calls"] += 1
                    if call.name == "gym_run":
                        gym_done = completed_run(result)
                        if isinstance(result, dict) and result.get("status") == "gym_error":
                            out["error"] = f"gym: {str(result.get('error') or '')[:200]}"  # no further model call this cycle
                            stop = True
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
        notes = "\n".join(f"- {n['text'][:400]}" for n in self.store.notebook(fid, limit=10))
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


def migrate_objective(store: SwarmStore) -> dict[str, Any]:
    """Once per store (the swarm's start): every living family's best chosen ANEW under `evidence.train_score`, so an old
    score (the full-Train t with a 30-trade floor) is never compared with a new one. Its kept full Train runs at the
    normal spread are rescored; the eligible best becomes both its best by Train score and its submitted best (none: both
    empty until an eligible run comes). The old selection stays in the family's state as `legacy_best`. The stall
    counter restarts. Returns {"migrated", "with_best"} (zeros when it already ran)."""
    if store.get("train_objective") == OBJECTIVE:
        return {"migrated": 0, "with_best": 0}
    migrated = with_best = 0
    for fam in store.families(alive=True):
        fid = fam["id"]
        state = fam.get("state") or {}
        rows: list[list[Any]] = []
        for run in store.runs(fid, window="train", limit=1000):
            if run["status"] != "ok" or float(run["stress"] or 1.0) != 1.0 or run.get("purpose") == "robustness" or not run.get("path"):
                continue
            result = store.run_result(run["run_id"])
            robust = evidence.train_score(result) if result is not None else None
            if robust is not None and robust["eligible"] and run.get("version") is not None:
                rows = candidates_with(rows, float(robust["score"]), int(run["version"]), run["run_id"])
        legacy = {"best_train": fam.get("best_train"), "best_version": fam.get("best_version"),
                  "best_train_version": state.get("best_train_version"), "best_train_run": state.get("best_train_run"),
                  "objective": "full-Train t_daily, 30-trade floor", "replaced_by": OBJECTIVE}
        best = rows[0] if rows else None
        with store.atomic():
            if (store.family(fid) or {}).get("retired_at"):
                continue
            store.update_family(fid, best_train=float(best[0]) if best else None, best_version=int(best[1]) if best else None, stall=0)
            store.set_state(fid, legacy_best=legacy, best_train_version=int(best[1]) if best else None,
                            best_train_run=best[2] if best else None, train_candidates=rows, robust_failed=[], robustness={})
        migrated += 1
        with_best += bool(best)
    store.put("train_objective", OBJECTIVE)
    out = {"migrated": migrated, "with_best": with_best}
    store.event("swarm.status", None, {"action": "train_objective", "objective": OBJECTIVE, **out})
    return out


__all__ = ["Researcher", "TOOLS", "TOOLS_READ", "TOOLS_REVISE", "needs_of", "needs_roots", "with_roots", "check_code", "sanitize",
           "date_like", "candidates_with", "migrate_objective", "OBJECTIVE"]
