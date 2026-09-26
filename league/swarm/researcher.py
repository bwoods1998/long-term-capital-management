"""The inner loop: one researcher per family, revise -> run -> read -> revise.

A CYCLE is at most one Gym run and a few model calls, bounded by `max_model_calls`, `max_tool_calls`
and `cycle_seconds` (the target is under three minutes). In the steady state a cycle is: run the program
the researcher asked for at the end of its last cycle (a `gym_run` carried over), show it the result, let
it read, write its notebook and revise, and carry its next `gym_run` to the next cycle. A family's very
first cycle runs its starter program without a model call (seeds only).

THE TOOLS (`TOOLS`): `gym_run` (a new version on Train; its compact diagnostic), `read_run` (a section of
a past Train run), `notebook` (append / read: its memory), `graveyard` (lessons of retired families),
`submit` (make a version its best: the tournament validates it). The contract (`league/CONTRACT.md`) is
the shared, cached prefix of every call; each family's calls carry its own `prompt_cache_key`.

WHAT IT SEES. Train in full; of Validation only the mean, t, quarters positive and the line (met or
not, and which checks were not); of the holdout only the gate's pass or fail. Never a date in ctx (the
Gym enforces it; the safety check refuses date literals before a program reaches the Gym).

STALLS. Five revisions without a better Train score (`evidence.score`) buy ONE rewrite from a stronger
model (DeepSeek-V4-Pro balanced; Kimi-K3 balanced for the top ten families by the bandit's share), then
the counter starts again.

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

from . import diagnostics, evidence
from .pool import GymJob, PoolError
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
         "why": {"type": "string", "description": "one sentence: what this version changes and why it should help"}}}},
    {"name": "read_run", "description": "Read one section of a past Train run of your family.",
     "parameters": {"type": "object", "properties": {
         "run_id": {"type": "string"},
         "section": {"type": "string", "description": "summary, fills, runtime, worst, trades, daily, or breakdown.<weekday|"
                                                      "time_of_day|dte|rv_tercile|iv_tercile|quarter|type|root|exit_reason>"},
         "page": {"type": "integer"}}, "required": ["run_id", "section"]}},
    {"name": "notebook", "description": "Your memory across cycles: append what you learned, or read your recent entries.",
     "parameters": {"type": "object", "properties": {
         "action": {"type": "string", "enum": ["append", "read"]},
         "text": {"type": "string", "description": "for append: a few plain sentences in your own words"}}, "required": ["action"]}},
    {"name": "graveyard", "description": "Search the lessons of retired families (what failed and why).",
     "parameters": {"type": "object", "properties": {"query": {"type": "string"}}}},
    {"name": "submit", "description": "Make the version behind one of your Train runs your family's best: the hourly tournament "
                                      "runs your best on Validation and, if it meets the line, sends it to the gate.",
     "parameters": {"type": "object", "properties": {"run_id": {"type": "string"}, "note": {"type": "string"}},
                    "required": ["run_id"]}},
]

ROLE = """You are a researcher in the LTCM options swarm. You own one family and improve its program in the Gym.
Work in short cycles: revise the program, call gym_run, read the diagnostic, write one or two sentences to your notebook,
submit a run when it is your best, and revise again. Keep every program inside the contract below; the Gym refuses
anything else. Reply with tool calls; keep prose short.

THE CONTRACT (league/CONTRACT.md)

"""

CODE_BLOCK = re.compile(r"```(?:python)?\s*\n(.*?)```", re.S)


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


class Researcher:
    """Runs cycles for any family (one call per cycle; the loop's workers call it concurrently)."""

    def __init__(self, store: SwarmStore, router: Any, pool: Any, settings: Mapping[str, Any], *, contract: str | None = None,
                 clock: Callable[[], float] = time.time, starter: Callable[[Mapping[str, Any]], tuple[str, dict]] | None = None):
        self.store = store
        self.router = router
        self.pool = pool
        self.settings = settings
        self.clock = clock
        self.contract = contract if contract is not None else CONTRACT.read_text(encoding="utf-8")
        self.system = ROLE + self.contract
        self.starter = starter

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
            lines += [f"- {x}" for x in lessons[:3]]
        return "\n".join(lines)

    def status(self, fam: Mapping[str, Any]) -> str:
        best = self.store.version(fam["id"], fam.get("best_version"))
        state = fam.get("state") or {}
        val = state.get("validation_view")
        gate = state.get("gate")
        notes = self.store.notebook(fam["id"], limit=5)
        parts = [f"Cycle {int(fam['cycles']) + 1}. Versions so far: {fam['revisions']}. Lineage trials: "
                 f"{self.store.lineage_trials(fam['id'])}. Revisions since a better Train score: {fam['stall']} "
                 f"(a rewrite from a stronger model comes at {self.cfg.get('stall_revisions', 5)})."]
        if best:
            parts.append(f"Your best: version {best['n']} (Train score {fam.get('best_train')}).")
        else:
            parts.append("No best submitted yet: submit your best Train run.")
        if val:
            parts.append(f"Your best on Validation: {json.dumps(val)}.")
        if gate:
            parts.append(f"The gate's last answer: {gate}.")
        if notes:
            parts.append("Your notebook (latest):\n" + "\n".join(f"- {n['text'][:300]}" for n in notes))
        parts.append("Now: revise and call gym_run (one run per cycle), then read the result, note what you learned, submit "
                     "when a run is your best.")
        return "\n".join(parts)

    # ------------------------------------------------------------------ tools
    def _gym_run(self, fam: Mapping[str, Any], args: Mapping[str, Any], out: dict[str, Any], *, author: str) -> dict[str, Any]:
        code = args.get("code")
        if not code:
            latest = self.store.latest_version(fam["id"])
            if latest is None or not latest.get("code"):
                return {"error": "you have no version yet: pass `code`"}
            code = latest["code"]
        code = str(code)
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
        roots = needs.get("roots") or []
        roots = [roots] if isinstance(roots, str) else roots
        extra = sorted({str(r).upper() for r in roots} - set(fam["roots"]))
        if extra:
            return {"status": "refused", "reason": f"your family trades {', '.join(fam['roots'])}; NEEDS names {', '.join(extra)} "
                                                   "(another root is another family: say so in your notebook)"}
        version = self.store.add_version(fam["id"], code, params, author=author, note=str(args.get("why") or "")[:300])
        job = GymJob(family=fam["id"], version=version["n"], code=code, params=params, window="train", roots=tuple(fam["roots"]),
                     stress=stress, purpose="train", priority=float(fam.get("weight") or 0.0))
        began = self.clock()
        try:
            result = self.pool.run(job, timeout=float(self.settings.get("gym", {}).get("run_timeout_seconds", 900)) + 120)
        except PoolError as exc:
            out["gym_error"] = str(exc)[:300]
            return {"status": "gym_error", "version": version["n"], "error": str(exc)[:500],
                    "hint": "the Gym could not run it now; your version is saved: rerun it next cycle"}
        out["gym_seconds"] = round(self.clock() - began, 2)
        years = float((result.get("summary") or {}).get("days") or 0) / 252.0 * max(1, len(fam["roots"]))
        run = self.store.add_run(fam["id"], version["n"], result, window="train", stress=stress, purpose="train",
                                 program_years=years)
        out["run_id"] = run["run_id"]
        out["trials"] = out.get("trials", 0) + int(run["trials"])
        view = diagnostics.train_view(result, lineage_trials=self.store.lineage_trials(fam["id"]))
        view["version"] = version["n"]
        view["run_id"] = run["run_id"]
        score = evidence.score(result.get("summary")) if stress == 1.0 and result.get("status") == "ok" else None
        current = self.store.family(fam["id"]) or {}
        if score is not None and (current.get("best_train") is None or score > float(current["best_train"])):
            self.store.update_family(fam["id"], best_train=score, stall=0)
            self.store.set_state(fam["id"], best_train_run=run["run_id"], best_train_version=version["n"])
            view["new_best_train_score"] = round(score, 3)
            out["improved"] = True
        view["train_score"] = None if score is None else round(score, 3)
        out["score"] = view["train_score"]
        return view

    def _execute(self, fam: Mapping[str, Any], name: str, args: Mapping[str, Any], out: dict[str, Any], *, author: str) -> Any:
        if name == "gym_run":
            return self._gym_run(fam, args, out, author=author)
        if name == "read_run":
            run = self.store.run(str(args.get("run_id") or ""))
            if run is None or run["family"] != fam["id"] or run["window"] != "train":
                return {"error": "no such Train run of your family"}
            result = self.store.run_result(run["run_id"]) or {}
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
                                 "roots": r["roots"], "lesson": r["lesson"][:600]} for r in rows]}
        if name == "submit":
            run = self.store.run(str(args.get("run_id") or ""))
            if run is None or run["family"] != fam["id"] or run["window"] != "train" or run["version"] is None:
                return {"error": "no such Train run of your family"}
            if run["status"] != "ok":
                return {"error": f"that run's status is {run['status']}: only a run that completed can be your best"}
            self.store.update_family(fam["id"], best_version=int(run["version"]))
            self.store.set_state(fam["id"], submitted_run=run["run_id"], submitted_note=str(args.get("note") or "")[:300])
            out["submitted"] = int(run["version"])
            return {"ok": True, "best_version": int(run["version"]), "next": "the tournament validates it within the hour"}
        return {"error": f"unknown tool {name}"}

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
        if view.get("status") == "ok" and view.get("run_id"):
            self.store.update_family(fam["id"], best_version=int(view["version"]))
        out["starter"] = True

    def _profile(self, history_chars: int) -> str:
        if history_chars > int(self.cfg.get("long_history_chars", 60000)):
            return str(self.cfg.get("long_profile", "flash41_asap"))
        return str(self.cfg.get("profile", "flash_asap"))

    def _model_cycle(self, fam: dict[str, Any], out: dict[str, Any]) -> None:
        fid = fam["id"]
        cycles, pending = self.store.convo(fid)
        keep = int(self.cfg.get("history_cycles", 4))
        cycles = [c for c in cycles if isinstance(c, dict)][-keep:]
        n = int(fam["cycles"]) + 1
        current: list[dict[str, Any]] = []
        deadline = self.clock() + float(self.cfg.get("cycle_seconds", 170))
        gym_done = False
        author = "model"
        if pending:  # the run asked for at the end of the last cycle (its call was answered "queued" then)
            result = self._execute(fam, "gym_run", pending.get("arguments") or {}, out, author=pending.get("author") or "model")
            current.append({"role": "user", "content": f"The gym_run you queued last cycle ran:\n{json.dumps(result, default=str)[:12000]}"})
            out["tool_calls"] += 1
            gym_done = True
            pending = None
            fam = self.store.family(fid) or fam
        if int(fam.get("stall") or 0) >= int(self.cfg.get("stall_revisions", 5)) and not gym_done:
            if self._rewrite(fam, out, current):
                gym_done = True
                fam = self.store.family(fid) or fam
        current.append({"role": "user", "content": self.status(fam)})
        max_calls = int(self.cfg.get("max_model_calls", 3))
        max_tools = int(self.cfg.get("max_tool_calls", 8))
        # A model call that writes a program took 60-80 s on Sept 26 (DeepSeek-V4-Flash asap): after the first, a call
        # starts only with `min_call_seconds` of the cycle's budget left, so a cycle stays under three minutes.
        min_call = float(self.cfg.get("min_call_seconds", 75))
        while out["model_calls"] < max_calls and (out["model_calls"] == 0 or deadline - self.clock() >= min_call):
            history = [i for c in cycles for i in c.get("items", [])]
            items = [{"role": "system", "content": self.system}, {"role": "user", "content": self.brief(fam)}]
            items += sanitize(history + current)
            chars = sum(len(json.dumps(i, default=str)) for i in items)
            profile = self._profile(chars)
            key = f"swarm:{fid}:c{n}:m{out['model_calls']}:{int(fam.get('revisions') or 0)}"
            response = self.router.sail(profile, items, family=fid, key=key, tools=TOOLS,
                                        effort=str(self.cfg.get("reasoning_effort", "low")),
                                        max_output=int(self.cfg.get("max_output_tokens", 8000)), cache_key=f"swarm-{fid}",
                                        cap_usd_day=float(self.cfg.get("family_usd_day", 2.0)))
            out["model_calls"] += 1
            out["cost_usd"] = round(out["cost_usd"] + float(response.cost_usd or 0), 6)
            out["profile"] = profile
            produced = [i for i in (response.output_items or []) if i.get("type") in ("message", "function_call")]
            current.extend(produced)
            calls = list(response.function_calls or [])
            if not calls:
                if response.output_text:
                    out["text"] = response.output_text[:600]
                break
            stop = False
            for call in calls:
                if call.name == "gym_run" and (gym_done or self.clock() > deadline - 30 or out["tool_calls"] >= max_tools) \
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
                if out["tool_calls"] >= max_tools:
                    result: Any = {"error": "this cycle's tool budget is spent; continue next cycle"}
                elif call.error:
                    result = {"error": call.error}
                else:
                    result = self._execute(fam, call.name, call.arguments, out, author=profile)
                    out["tool_calls"] += 1
                    if call.name == "gym_run":
                        gym_done = True
                current.append({"type": "function_call_output", "call_id": call.call_id,
                                "output": json.dumps(result, default=str)[:12000]})
                fam = self.store.family(fid) or fam
            if stop or pending:
                break
        cycles.append({"cycle": n, "items": [i for i in current if i.get("type") != "reasoning"]})
        self.store.save_convo(fid, cycles[-keep:], pending)
        out["pending_run"] = bool(pending)

    def _rewrite(self, fam: Mapping[str, Any], out: dict[str, Any], current: list[dict[str, Any]]) -> bool:
        """The stall's one rewrite from a stronger model: a new program from the mechanism, the notebook and the
        latest diagnostic, run as this cycle's Gym run."""
        weight_rank = sorted((f.get("weight") or 0.0 for f in self.store.families(alive=True)), reverse=True)
        top = int(self.cfg.get("top_rewrite_families", 10))
        is_top = bool(weight_rank) and (fam.get("weight") or 0.0) >= weight_rank[min(top, len(weight_rank)) - 1] > 0
        profile = str(self.cfg.get("top_rewrite_profile" if is_top else "rewrite_profile", "pro_balanced"))
        latest = self.store.latest_version(fam["id"])
        best = self.store.version(fam["id"], fam.get("best_version")) or latest
        runs = self.store.runs(fam["id"], window="train", limit=1)
        last_view = diagnostics.train_view(self.store.run_result(runs[0]["run_id"]) or {}) if runs else {}
        notes = "\n".join(f"- {n['text'][:400]}" for n in self.store.notebook(fam["id"], limit=10))
        user = (f"{self.brief(fam)}\n\nThis family has gone {fam['stall']} revisions without a better Train score. Write a NEW "
                f"program for the same mechanism, structure and roots that fixes what the diagnostics show. Reply with the "
                f"whole file in one ```python block, then one sentence on what changed.\n\nIts notebook:\n{notes or '(empty)'}\n\n"
                f"Its best version so far:\n```python\n{(best or {}).get('code') or ''}\n```\n\nThe latest Train diagnostic:\n"
                f"{json.dumps(last_view, default=str)[:8000]}")
        try:
            answer = self.router.ask(role="rewrite", system=self.system, user=user, family=fam["id"],
                                     key=f"swarm:{fam['id']}:rewrite:{int(fam.get('rewrites') or 0)}:{int(fam.get('revisions') or 0)}",
                                     openai_model=None, sail_profile=profile, max_output=12000, effort="medium")
        except Exception as exc:  # noqa: BLE001
            out["rewrite_error"] = str(exc)[:200]
            self.store.bump(fam["id"], rewrites=1)
            self.store.update_family(fam["id"], stall=0)
            return False
        out["cost_usd"] = round(out["cost_usd"] + float(answer.get("cost_usd") or 0), 6)
        self.store.bump(fam["id"], rewrites=1)
        self.store.update_family(fam["id"], stall=0)
        match = CODE_BLOCK.search(answer.get("text") or "")
        if not match:
            out["rewrite_error"] = "the rewrite carried no program"
            return False
        view = self._gym_run(fam, {"code": match.group(1), "why": f"a rewrite by {profile} after a stall"}, out, author=profile)
        out["rewrite"] = profile
        current.append({"role": "user", "content": f"After {fam['stall']} revisions without progress, a stronger model ({profile}) "
                                                   f"rewrote your program:\n```python\n{match.group(1)}\n```\nIts Train diagnostic:\n"
                                                   f"{json.dumps(view, default=str)[:9000]}"})
        return True

    def _public_note(self, fid: str, out: Mapping[str, Any]) -> None:
        """A notebook entry to the site's tape (as `swarm.note`), at most every `note_every_cycles` cycles."""
        text = str(out.get("note") or "").strip()
        if not text:
            return
        state = (self.store.family(fid) or {}).get("state") or {}
        last = int(state.get("public_note_cycle") or -10**6)
        if int(out.get("cycle") or 0) - last < int(self.cfg.get("note_every_cycles", 6)) and not out.get("improved"):
            return
        self.store.set_state(fid, public_note_cycle=int(out.get("cycle") or 0))
        self.store.event("swarm.note", fid, {"text": text[:1000]})


__all__ = ["Researcher", "TOOLS", "needs_of", "check_code", "sanitize"]
