"""The diagnostician: Claude (`claude.model`, or `claude.role_model["diagnostician"]`) reads a family that is stuck or
nearly there, and rewrites its mechanism or writes its lesson (the swarm sprint, Sept 26, 2026;
docs/goals/LTCM_SWARM_SPRINT.md, "The loops").

WHEN. A living Gym family is ELIGIBLE when its latest validation did not pass the line and either it has had at least
`min_validations` (2) validations, or that validation met at least `near_miss_checks` (6) of the line's checks. At most
once a family every `family_hours` (6), and again only after a new validation (new evidence); within `usd_day` ($15) of
the diagnostician's Claude spend over the last 24 hours, and within the role's `claude.role_usd_day` line when one is
set; only while Claude has room above its reserve. (The numbers are the defaults; swarm.json may set others.)
Near-misses go first (most checks met), then the most validated; `per_round` families a round.

WHAT IT SEES. The family's mechanism, structure, roots, days to expiry, rejection test and sketch; its best program
and parameters; the full Train diagnostic of that program (every breakdown, the P&L by Train year from the daily
series, and every robustness result that exists: other Train runs of the same version and any `robustness` block);
the graveyard's relevant lessons; every free text (the mechanism, the sketch, the rejection test, the lessons and
their notes) with any validation figure cut, every number masked and the line's check names withheld. Of VALIDATION only: passed
or not, and "N of 8 checks passed" (decision D2a). Never a validation number, never a check's name, never the
family's notebook (researchers once saw validation numbers and may have written them down).

WHAT IT ANSWERS (one JSON object, a structured output): `decision` "rewrite" or "retire", `diagnosis`, `note`,
`program`, `lesson`.
- A REWRITE must change the mechanism: the program with its PARAMS literal and docstrings set aside must differ from
  the best version's. It must pass the Gym's safety check and name only the family's roots. It is then queued as the
  family's next Train run (`rewrite_ready`, profile "diagnostician"), so the researcher's next cycle runs it through
  the same safety check and Gym run as any revision, as a new version authored "diagnostician".
- A RETIRE is honored only while more families live than `population.floor` (`retire_gym` with that as its floor,
  checked in its own transaction; `population.start` is the architect's refill target, never a second floor); otherwise
  it is written to the family's notebook as a recommendation. Never while independent evidence is pending (a version
  at the gate, a look out, the extension hold or, from Oct 1, a best Train version that awaits validation:
  researcher.py's THE VALIDATION WAIT): the recommendation goes to the notebook, to be read after it.
- A call BILLED WITHOUT AN ANSWER (a refusal, a truncation) counts as a diagnosis: the family waits for new evidence. A
  truncation is asked once more at medium effort with a tighter brief when the day's budget holds it. A call that cost
  nothing is asked again after half an hour.

Every call is a `swarm.diagnostician` event (outcome, cost, route, stop reason) and its money is `spend` rows of kind
`claude` with role "diagnostician" (the router's durable hold, then its settlement). Standard library only.
"""

from __future__ import annotations

import ast
import json
import re
import time
from typing import Any, Callable, Mapping

from . import diagnostics, game
from . import settings as settings_mod
from .researcher import CODE_BLOCK, CONTRACT, check_code, needs_of
from .store import SwarmStore, structure_query, structure_text

ROLE = "diagnostician"

SCHEMA: dict[str, Any] = {
    "type": "object", "additionalProperties": False,
    "required": ["decision", "diagnosis", "note", "program", "lesson"],
    "properties": {
        "decision": {"type": "string", "enum": ["rewrite", "retire"]},
        "diagnosis": {"type": "string"},
        "note": {"type": "string"},
        "program": {"type": "string"},
        "lesson": {"type": "string"},
    },
}

SYSTEM = """You are the diagnostician of a swarm of AI researchers that trade level-3 options (defined-risk structures only)
on one brokerage account. Each researcher owns one family: a mechanism, a structure type and a set of roots, and it improves
one Python program in a Gym that replays recorded one-minute option quotes. Train (2022-2024) is seen in full. Validation
(2025) is the selection set: of it you are told only whether the family passed the validation line and how many of the
line's checks it met, because fitting to it would destroy it. A sealed holdout and then the live market judge what passes.

You are asked about a family that is stuck (validated at least twice without passing) or nearly there (most checks met).
You see its mechanism, its best program, its full Train diagnostics (summary, fills, breakdowns, the worst trades, P&L by
Train year, and robustness runs when they exist) and lessons of retired families. Decide one of two things:

1. REWRITE: write a new, complete program for the same family (the same structure type and roots, inside the contract
   below) that changes the MECHANISM: what the program conditions on, when it enters, which strikes and expiries it
   picks, how and when it exits. Base the change on what the Train diagnostics show (where the losses concentrate, which
   years, quarters, times of day, volatility terciles or exit reasons carry the result, what the fills cost). Retuning
   PARAMS values or renaming them is not a rewrite: the researcher already does that. Prefer changes that hold in every
   Train year and quarter and survive a wider spread over changes that raise the Train total. Never use a date, a year,
   an absolute price or strike level, a table of events, or calendar reconstruction: the gate refuses them.
2. RETIRE: when the diagnostics show that the mechanism has no edge a program could capture after the spread and fees,
   write the lesson the swarm should keep: why it failed, and what a future family should do differently.

Reply with ONE JSON object: "decision" ("rewrite" or "retire"); "diagnosis" (what the diagnostics show, a few
sentences); "note" (one or two sentences on the mechanism change, in plain words and with no numbers: it may appear on
the public site); "program" (the whole program file when rewriting, else ""); "lesson" (when retiring, else "").

THE CONTRACT (league/CONTRACT.md)

"""

_NUMBER = re.compile(r"(?<![A-Za-z_])[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")
_MARKER = "best validation "
#: The validation line's distinctive check and field names (evidence.validation_line, diagnostics.validation_view).
_CHECK_NAMES = re.compile(r"\b(?:status_ok|mean_positive|dsr|checks_not_met|line_met|validation_(?:line|view|numbers))\b", re.I)
#: The tighter brief of the one retry after a truncation (at medium effort).
RETRY_BRIEF = ("\n\nYOUR LAST ANSWER RAN OUT OF ROOM BEFORE IT FINISHED. Think briefly. Keep the diagnosis to three sentences "
               "and the program compact (about 250 lines at most), and answer with the JSON object only.")


def withheld(text: Any) -> str:
    """A lesson with every validation figure cut and every number masked: whatever format a retirement wrote it in,
    no validation number reaches the diagnostician (D2a)."""
    out = str(text or "")
    decoder = json.JSONDecoder()
    at = out.find(_MARKER)
    while at >= 0:
        begin = at + len(_MARKER)
        try:
            _, end = decoder.raw_decode(out[begin:])
        except ValueError:
            end = len(re.match(r"\S*", out[begin:]).group(0))
        out = out[:begin] + "[withheld]" + out[begin + end:]
        at = out.find(_MARKER, begin)
    return _CHECK_NAMES.sub("[withheld]", _NUMBER.sub("#", out))


def _shape(code: Any) -> str | None:
    """The program's syntax with its PARAMS literal and docstrings set aside, and its NEEDS literal in a canonical
    order: two programs with the same shape differ only in parameters (or comments). None when it does not parse."""
    try:
        tree = ast.parse(str(code or ""))
    except (SyntaxError, ValueError):
        return None

    class Strip(ast.NodeTransformer):
        def visit_Assign(self, node: ast.Assign) -> Any:
            names = {t.id for t in node.targets if isinstance(t, ast.Name)}
            if "PARAMS" in names:
                return None
            if "NEEDS" in names:
                try:
                    node.value = ast.Constant(json.dumps(ast.literal_eval(node.value), sort_keys=True, default=str))
                except (ValueError, TypeError, SyntaxError):
                    pass
            return self.generic_visit(node)

        def visit_Expr(self, node: ast.Expr) -> Any:
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                return None
            return self.generic_visit(node)

    return ast.dump(Strip().visit(tree), annotate_fields=False, include_attributes=False)


def standing(fam: Mapping[str, Any]) -> dict[str, Any] | None:
    """What the diagnostician may know of Validation: passed or not, and how many of the line's checks were met."""
    line = (fam.get("state") or {}).get("validation_line") or {}
    checks = line.get("checks") if isinstance(line, Mapping) else None
    if not isinstance(checks, Mapping) or not checks:
        return None
    return {"passed": bool(line.get("passed")), "met": sum(1 for ok in checks.values() if ok), "total": len(checks)}


class Diagnostician:
    def __init__(self, store: SwarmStore, router: Any, settings: Mapping[str, Any], *, pool: Any = None, researcher: Any = None,
                 contract: str | None = None, clock: Callable[[], float] = time.time):
        self.store = store
        self.router = router
        self.settings = settings
        self.pool = pool
        self.researcher = researcher
        self.clock = clock
        self.system = SYSTEM + (contract if contract is not None else CONTRACT.read_text(encoding="utf-8"))

    @property
    def cfg(self) -> Mapping[str, Any]:
        return self.settings.get("diagnostician", {})

    @property
    def schema(self) -> dict[str, Any] | None:
        """The structured-output schema, or None (`diagnostician.structured` false): the answer's JSON is then read from
        its text, as the system prompt asks for one object either way."""
        return SCHEMA if self.cfg.get("structured", True) else None

    def due(self) -> bool:
        if not self.cfg.get("enabled"):
            return False
        return self.clock() - float(self.store.get("diagnostician_at", 0.0) or 0.0) >= float(self.cfg.get("every_seconds", 300))

    # ------------------------------------------------------------------ who
    def eligible(self, fam: Mapping[str, Any]) -> dict[str, Any] | None:
        """The family's standing when it is eligible now (the module docstring), else None."""
        if fam.get("retired_at") or fam.get("band") != "gym":
            return None
        seen = standing(fam)
        if seen is None or seen["passed"]:
            return None
        validations = int(fam.get("validations") or 0)
        if validations < int(self.cfg.get("min_validations", 2)) and seen["met"] < int(self.cfg.get("near_miss_checks", 6)):
            return None
        state = fam.get("state") or {}
        now = self.clock()
        if now - float(state.get("diagnosed_at") or 0) < 3600 * float(self.cfg.get("family_hours", 6.0)):
            return None
        if state.get("diagnosed_at") and int(state.get("diagnosed_validations") or 0) >= validations:
            return None  # no new evidence since the last diagnosis
        if now - float(state.get("diagnosis_error_at") or 0) < 1800:
            return None
        if state.get("rewrite_ready") or fam["id"] in (getattr(self.researcher, "_rewriting", None) or {}):
            return None  # a rewrite is queued or being written: its run comes first
        return {**seen, "validations": validations}

    def candidates(self) -> list[tuple[dict[str, Any], dict[str, Any]]]:
        rows = [(fam, seen) for fam in self.store.families(alive=True) if (seen := self.eligible(fam)) is not None]
        return sorted(rows, key=lambda r: (-r[1]["met"] / max(1, r[1]["total"]), -r[1]["validations"], r[0]["id"]))

    # ------------------------------------------------------------------ what it sees
    def _train(self, fid: str, version: int) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
        """The full result of the version's latest Train run at the normal spread, and its other Train runs (robustness)."""
        runs = [r for r in self.store.runs(fid, window="train", limit=200) if r.get("version") == version]  # newest first
        main = next((r for r in runs if float(r.get("stress") or 1.0) == 1.0 and r.get("purpose") == "train"
                     and r.get("status") == "ok" and self.store.run_result(r["run_id"]) is not None), None)
        result = self.store.run_result(main["run_id"]) if main else None
        others = []
        for r in runs:
            if main is not None and r["run_id"] == main["run_id"]:
                continue
            summary = json.loads(r["summary"]) if isinstance(r.get("summary"), str) else (r.get("summary") or {})
            others.append({"purpose": r.get("purpose"), "stress": r.get("stress"), "status": r.get("status"),
                           "summary": {k: summary.get(k) for k in diagnostics.SUMMARY_KEYS if k in (summary or {})}})
        return result, others[:12]

    def packet(self, fam: Mapping[str, Any], seen: Mapping[str, Any]) -> str:
        """The user message: everything the diagnostician may see (the module docstring), nothing of Validation but its
        verdict and count."""
        fid = fam["id"]
        spec = fam.get("spec") or {}
        best = self.store.version(fid, fam.get("best_version")) or self.store.latest_version(fid) or {}
        result, others = self._train(fid, int(best.get("n") or 0))
        view: dict[str, Any] = {}
        if result is not None:
            view = diagnostics.train_view(result, lineage_trials=self.store.lineage_trials(fid))
            view["by"] = {name: diagnostics.section(result, f"breakdown.{name}").get(f"breakdown.{name}")
                          for name in diagnostics.BREAKDOWNS if (result.get("breakdown") or {}).get(name)}
            years: dict[str, dict[str, Any]] = {}
            for row in result.get("daily") or []:
                if isinstance(row, (list, tuple)) and len(row) >= 2 and isinstance(row[1], (int, float)):
                    year = years.setdefault(str(row[0])[:4], {"days": 0, "pnl": 0.0, "positive_days": 0})
                    year["days"] += 1
                    year["pnl"] = round(year["pnl"] + float(row[1]), 2)
                    year["positive_days"] += int(row[1] > 0)
            if years:
                view["by_train_year"] = years
            if result.get("robustness") is not None:
                view["robustness"] = result["robustness"]
        robustness = (fam.get("state") or {}).get("robustness")
        # THE LEARNING GAME: the rows every reader reads (`game.visible_graveyard`; the store's own read with the game off).
        lessons = [{"mechanism": withheld(g["mechanism"])[:300], "structure": g["structure"], "roots": g["roots"],
                    "lesson": withheld(g["lesson"])[:700]}
                   for g in game.visible_graveyard(self.store, f"{structure_query(fam['structure'])} {' '.join(fam['roots'])} "
                                                   f"{fam['mechanism']}", limit=6, settings=self.settings)
                   if g["family"] != fid]
        dte = spec.get("dte") or ["?", "?"]
        parts = [
            f"FAMILY {fid} ({fam.get('origin')}). Mechanism: {withheld(fam['mechanism'])}",
            f"Structure {structure_text(fam['structure'])}; roots {', '.join(fam['roots'])}; days to expiry {dte[0]}-{dte[-1]}.",
            f"Rejection test: {withheld(spec.get('rejection')) or '(none stated)'}",
        ]
        if spec.get("sketch"):
            parts.append(f"The architect's sketch: {withheld(spec['sketch'])}")
        parts += [
            f"Versions so far: {fam.get('revisions')}; lineage trials {self.store.lineage_trials(fid)}; best Train score "
            f"{fam.get('best_train')}.",
            f"VALIDATION: {'passed' if seen['passed'] else 'not passed'}; {seen['met']} of {seen['total']} checks passed on the "
            f"latest; {seen['validations']} validations so far.",
            f"ITS BEST PROGRAM (version {best.get('n')}), PARAMS overrides {json.dumps(best.get('params') or {})}:\n"
            f"```python\n{best.get('code') or ''}\n```",
            "ITS TRAIN DIAGNOSTIC (by: rows of [n, pnl, win rate, pnl per $ of max loss]):\n"
            + (json.dumps(view, default=str)[:30000] if view else "(no complete Train run of this version is kept)"),
        ]
        if others or robustness is not None:
            parts.append("ROBUSTNESS (other Train runs of this version, and the robustness block):\n"
                         + json.dumps({"runs": others, "block": robustness}, default=str)[:12000])
        parts.append("LESSONS OF RETIRED FAMILIES (numbers masked):\n" + (json.dumps(lessons)[:8000] if lessons else "(none)"))
        return "\n\n".join(parts)

    # ------------------------------------------------------------------ one family
    def check_rewrite(self, fam: Mapping[str, Any], best_code: Any, program: Any) -> tuple[str | None, str]:
        """(why the rewrite is refused or None, the program). The Gym's safety check, the family's roots, and a real
        change of mechanism."""
        code = str(program or "")
        match = CODE_BLOCK.search(code)
        if match:
            code = match.group(1).rstrip("\n") + "\n"
        if not code.strip():
            return "the rewrite carried no program", code
        why = check_code(code)
        if why:
            return f"the safety check refused it: {why[:300]}", code
        needs = needs_of(code)
        if needs is None:
            return "NEEDS is not a literal dict", code
        roots = needs.get("roots") or []
        roots = [roots] if isinstance(roots, str) else roots
        extra = sorted({str(r).upper() for r in roots} - set(fam["roots"]))
        if extra:
            return f"it names roots outside the family ({', '.join(extra)})", code
        shape = _shape(code)
        if shape is not None and shape == _shape(best_code):
            return "only parameters changed: a rewrite must change the mechanism", code
        return None, code

    def diagnose(self, fam: Mapping[str, Any], seen: Mapping[str, Any]) -> dict[str, Any]:
        """One family: ask, check, act. While the call is out the family is marked in the researcher's map of rewrites in
        flight, so no stall rewrite starts meanwhile and lands on top of this one; one already in flight skips it."""
        rewriting = getattr(self.researcher, "_rewriting", None)
        if isinstance(rewriting, dict) and rewriting.setdefault(fam["id"], ROLE) != ROLE:
            return {"family": fam["id"], "outcome": "skipped", "reason": "a stall rewrite is in flight"}
        try:
            return self._diagnose(fam, seen)
        finally:
            if isinstance(rewriting, dict) and rewriting.get(fam["id"]) == ROLE:
                rewriting.pop(fam["id"], None)

    def _diagnose(self, fam: Mapping[str, Any], seen: Mapping[str, Any]) -> dict[str, Any]:
        fid = fam["id"]
        began = self.clock()
        best = self.store.version(fid, fam.get("best_version")) or self.store.latest_version(fid) or {}
        user = self.packet(fam, seen)
        out: dict[str, Any] = {"family": fid, "validations": seen["validations"], "checks_met": f"{seen['met']}/{seen['total']}",
                               "version": best.get("n")}
        answer, billed, error = self._ask(fid, user, seen, began)
        if answer is None and any(b.get("stop_reason") == "max_tokens" for b in billed) and self.cfg.get("retry_truncated", True):
            # Cut off at max_tokens: once more at medium effort with a tighter brief, if the day's budget holds it.
            tighter = user + RETRY_BRIEF
            if self.affordable(tighter, effort="medium") is None:
                answer, more, error = self._ask(fid, tighter, seen, began, effort="medium")
                billed += more
                out["retried"] = "medium"
        if answer is None:
            if billed:
                # Billed without an answer (a refusal, a truncation): no new call until new evidence, like a diagnosis.
                with self.store.atomic():
                    self.store.set_state(fid, diagnosed_at=self.clock(), diagnosed_validations=seen["validations"])
                out.update(outcome="billed_failure", cost_usd=round(sum(float(b.get("cost_usd") or 0) for b in billed), 6),
                           stop_reason=",".join(str(b.get("stop_reason")) for b in billed), error=error)
            else:
                self.store.set_state(fid, diagnosis_error_at=self.clock())  # nothing billed: asked again after half an hour
                out.update(outcome="error", error=error)
            return self._record(out, began)
        out.update(route=answer.get("route"), model=answer.get("model"), cost_usd=answer.get("cost_usd"),
                   held_usd=answer.get("held_usd"), stop_reason=answer.get("stop_reason"))
        reply = answer.get("json") if isinstance(answer.get("json"), dict) else {}
        decision = reply.get("decision")
        with self.store.atomic():
            self.store.set_state(fid, diagnosed_at=self.clock(), diagnosed_validations=seen["validations"])
        diagnosis = str(reply.get("diagnosis") or "").strip()[:1500]
        if decision == "rewrite":
            why, code = self.check_rewrite(fam, best.get("code"), reply.get("program"))
            note = " ".join(str(reply.get("note") or "").split())[:600]
            if why:
                out.update(outcome="rejected", reason=why)
                self.store.note(fid, f"The diagnostician's rewrite was not run ({why}). Its diagnosis: {diagnosis}")
                return self._record(out, began)
            with self.store.atomic():
                current = self.store.family(fid) or {}
                if current.get("retired_at") or (current.get("state") or {}).get("rewrite_ready"):
                    out.update(outcome="superseded")
                    return self._record(out, began)
                self.store.set_state(fid, rewrite_ready={"code": code, "profile": ROLE, "at": self.clock(), "note": note})
                self.store.note(fid, f"The diagnostician (Claude) rewrote the mechanism: {note} Diagnosis: {diagnosis}")
            out.update(outcome="rewrite", note=note)
            return self._record(out, began)
        if decision == "retire":
            lesson = " ".join(str(reply.get("lesson") or diagnosis or "the diagnostician found no capturable edge").split())[:1500]
            population = self.settings.get("population", {})
            # Start is the architect's refill target, not a second floor (start == ceiling otherwise makes this
            # decision unreachable). The store serializes concurrent retirements against the actual floor.
            floor = int(population.get("floor", 16))
            from .researcher import awaiting_validation, extension_held
            with self.store.atomic():
                current = self.store.family(fid) or fam
                state = current.get("state") or {}
                # THE VALIDATION WAIT (researcher.py): a best the tournament owes a verdict is pending evidence too.
                if (extension_held(current) or state.get("gate_ready") or state.get("look_inflight")
                        or awaiting_validation(current)):
                    out.update(outcome="retire_refused", reason="independent evidence is pending or held")
                    self.store.note(fid, f"The diagnostician recommends retiring this family after its pending evidence: {lesson}")
                    return self._record(out, began)
                result = self.store.retire_gym(fid, f"the diagnostician: {lesson}", floor=floor, source=ROLE)
            if result.get("status") == "retired" and not result.get("already_retired"):
                try:
                    if self.pool is not None:
                        self.pool.cancel_family(fid)
                except Exception:  # noqa: BLE001 - queued work is refused by the retired state anyway
                    pass
                out.update(outcome="retired", lesson=lesson[:300])
                return self._record(out, began)
            if result.get("deferred") == "population_floor":
                out.update(outcome="retire_noted", reason="not above the population floor")
            else:
                out.update(outcome="retire_refused", reason=str(result.get("reason") or result.get("status"))[:200])
            self.store.note(fid, f"The diagnostician recommends retiring this family: {lesson}")
            return self._record(out, began)
        out.update(outcome="unclear")
        return self._record(out, began)

    def _ask(self, fid: str, user: str, seen: Mapping[str, Any], began: float,
             effort: str | None = None) -> tuple[dict[str, Any] | None, list[dict[str, Any]], str | None]:
        """(the answer or None, the paid attempts billed without one, the error)."""
        try:
            answer = self.router.ask(role=ROLE, system=settings_mod.train_span_text(self.system, settings_mod.objective_span(self.store.get("train_objective"))), user=user, family=fid,
                                     key=f"swarm:{fid}:diagnose:{seen['validations']}:{int(began)}{':' + effort if effort else ''}",
                                     openai_model=None, sail_profile=None, max_output=16000, effort="high", need_usd=0.0,
                                     claude=True, schema=self.schema, claude_effort=effort)
            return answer, [], None
        except Exception as exc:  # noqa: BLE001 - the caller decides when to ask again
            return None, list(getattr(exc, "billed", []) or []), str(exc)[:300]

    def affordable(self, user: str, *, effort: str | None = None) -> str | None:
        """Why a call with this packet cannot be made now (the day's budget, Claude's room), or None."""
        try:
            _, ceiling = self.router.claude_request(settings_mod.train_span_text(self.system, settings_mod.objective_span(self.store.get("train_objective"))), user, schema=self.schema,
                                                    effort=effort, role=ROLE)
        except Exception as exc:  # noqa: BLE001
            return f"the request could not be priced: {exc}"[:300]
        # A call counts at the hour its hold was booked (`claude_spent`): a hold booked 25 hours ago and trued up an hour
        # ago gives back nothing to this window.
        spent = self.router.claude_spent(role=ROLE, since=self.clock() - 86400)
        if spent + ceiling > float(self.cfg.get("usd_day", 15.0)):
            return f"the day's diagnostician budget: ${spent:.2f} spent, the next call may cost ${ceiling:.2f}"
        line = getattr(self.router, "claude_role_room", lambda role: None)(ROLE)
        if line is not None and line < ceiling:
            return (f"the diagnostician's Claude line for today (claude.role_usd_day): ${line:.2f} left, the next call may "
                    f"cost ${ceiling:.2f}")
        if self.router.claude_room() < ceiling:
            return "Claude has no room above its reserve"
        return None

    def _record(self, out: dict[str, Any], began: float) -> dict[str, Any]:
        out["seconds"] = round(self.clock() - began, 1)
        self.store.event("swarm.diagnostician", out.get("family"), out)
        return out

    # ------------------------------------------------------------------ one round
    def run(self) -> dict[str, Any]:
        self.store.put("diagnostician_at", self.clock())
        if not getattr(self.router, "claude_enabled", lambda role: False)(ROLE):
            return {"skipped": "Claude is not configured for the diagnostician"}
        rows = self.candidates()
        if not rows:
            return {"eligible": 0}
        done = []
        for fam, seen in rows[: max(0, int(self.cfg.get("per_round", 2)))]:
            why = self.affordable(self.packet(fam, seen))
            if why:
                return {"eligible": len(rows), "diagnosed": [{k: d.get(k) for k in ("family", "outcome", "cost_usd")} for d in done],
                        "skipped": why}
            done.append(self.diagnose(fam, seen))
        return {"eligible": len(rows), "diagnosed": [{k: d.get(k) for k in ("family", "outcome", "cost_usd")} for d in done]}


__all__ = ["Diagnostician", "SCHEMA", "SYSTEM", "withheld", "standing"]
