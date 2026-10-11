"""The "panel" kind inside the decider's isolated child: load, drop, decide and run panel programs.

Owner: package D. Called only by `league/live/decider.py`'s child through `league.equity.kinds.module_for("panel")`,
exactly as the "equity" kind's module is (league/equity/child.py). Every answer is JSON-safe (the child replies JSON,
never pickle); the payload arrives pickled from the House (the trusted side). `state` is this kind's own dict in the
child (its runners keyed by instance), kept across messages and lost with the child (the parent then reloads every
loaded instance before its next request).

THE CHILD NEVER HOLDS AN AID OR A SYMBOL: the parent computes the salted ids, puts the member columns in ascending id
and names the symbols; the child plans orders by id.

OPS:
- "load"   {key, code, params, name, timeout, max_errors} -> {ok, needs, sha, run_sha, params} (a
           `program.XsRunner` kept at state["runners"][key]; `params` the program's merged PARAMS, the live ctx's:
           I6); {ok: False, refused: True, error} when the program does not load;
- "drop"   {key} -> {ok};
- "decide" {jobs: [{key, inputs: league.xs.ctx.Inputs, called, standing}]} -> {ok, results: {key: {hold, target, at,
           orders, rejects, ineligible, stats, ctx_sha, failed, called, standing}}}. EVERY job, called or not, reads
           `ctx.derive(inputs)` and answers `ineligible`: the lids of the open lots whose name is not in U(t) (the
           House exit of the pre-registration's C6: the parent's `elig0` alone cannot say it).
           `called` True (a decision day): the ctx is `ctx.build(inputs)`, exactly the Gym's (I6), `ctx_sha` the sha256
           of its `ctx_bytes`, taken BEFORE the program sees it; the program's target becomes `orders` by THE KEEP RULE
           (`engine.plan_orders`, the Gym's own function, on `inputs.budget`); `hold` True when it planned no target
           (a hold, a None, a malformed answer, a failed decide, or a target the order cap refused whole: `target`
           is then None and the standing target stands). `failed` is E1's flag with E1's meanings, because E1's book
           reads it: the runner's `last_failed` (the program raised, ran past its limit or is disqualified: what the
           Gym counts toward the failed-decides exit), with `why`.
           `called` False (a hold day): NO PROGRAM CODE RUNS; `standing` {target {id: w}, at, exited [id], pending
           [id]} gives the standing target's buys (`plan_orders(..., standing=True)`: the ids eligible at this close
           with no open lot, no buy pending and no House exit since the target was set); absent: no order. Such a job
           is never `failed` for the program's sake, and needs no loaded runner.
           A called job whose key has no loaded runner answers {missing: True, failed: True}; inputs no ctx can be
           built from answer {error, failed: True} (that job only: the rest of the batch goes on): neither is the
           program's own failure.
           A target's keys come back as strings (the child answers JSON): the parent reads them with `int()`.
- "needs"  {code, params, name} -> {ok, needs, sha, run_sha, params} (load, read NEEDS, drop: the parent never
           executes a program to learn what to slice);
- "run"    {code, params, name, bars: league.xs.store.PanelBars, k, capital, placebos, seed, calls, style, nice} ->
           {ok, result} (`league.xs.runner.run_bars`: Train, Validation, the sealed look, the floor's segments and
           the forward runs). `nice`: the child raises its niceness to it ONCE (`os.nice`; research deciders only:
           the live decider's child is sent none).

Imports are made inside `handle`, per op, so the child imports only what a request needs (its runtime is
league/equity/kinds.py `RUNTIME`). Standard library only at the top level.
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Mapping

#: The ops this kind serves.
OPS: tuple[str, ...] = ("load", "drop", "decide", "needs", "run")


def _load(payload: Mapping[str, Any]) -> Any:
    from . import program as P

    return P.load_program(str(payload["code"]), name=str(payload.get("name") or "program"),
                          params=dict(payload.get("params") or {}))


def _identity(program: Any) -> dict[str, Any]:
    """The loaded program's answer: its NEEDS, shas and MERGED PARAMS (its declaration with the overrides): the House
    builds the live ctx with them, as the Gym's engine does (`program.params`), so a program reads the same
    `ctx.params` live and in replay (I6)."""
    return {"ok": True, "needs": program.needs.as_dict(), "sha": program.sha, "run_sha": program.run_sha,
            "params": json.loads(json.dumps(program.params))}


def _why_failed(stats: Mapping[str, Any]) -> str:
    """Why a runner's last decide failed, from its stats: its disqualification, else its latest error message."""
    messages = stats.get("messages") or []
    why = stats.get("disqualified") or (messages[-1] if messages else "")
    return str(why or "its decide raised or ran past its limit")[:300]


def _slot(ids: list[int], ref: int, col: Any) -> int:
    """The salted id of a held lot's column (a name that left the index keeps its column and its id); ValueError for
    a column that is no member column of the decision (the parent's fault: that job answers an error)."""
    at = int(col) - ref
    if not 0 <= at < len(ids):
        raise ValueError(f"a held lot's column {col!r} is no member column of the decision")
    return ids[at]


def _blank(called: bool) -> dict[str, Any]:
    return {"hold": True, "target": None, "at": None, "orders": [], "rejects": [], "ineligible": [], "stats": None,
            "ctx_sha": None, "failed": False, "called": bool(called), "standing": False}


def _decide(payload: Mapping[str, Any], runners: Mapping[str, Any]) -> dict[str, Any]:
    from . import ctx as C
    from . import engine as E

    results: dict[str, Any] = {}
    for job in payload.get("jobs") or ():
        key = str(job["key"])
        called = bool(job.get("called", True))
        runner = runners.get(key)
        row = _blank(called)
        if runner is not None:
            row["stats"] = runner.stats()
        if called and runner is None:
            results[key] = {**row, "missing": True, "failed": True}
            continue
        try:
            inputs = job["inputs"]
            derived = C.derive(inputs)
            row["ineligible"] = [int(lid) for lid in C.ineligible(inputs, derived)]
            ids, ref = [int(i) for i in inputs.ids], int(inputs.ref)
            lots = [{"lid": int(p["lid"]), "id": _slot(ids, ref, p["col"]), "pending": False}
                    for p in inputs.positions]
            budget = float(inputs.budget)
            ctx = ctx_sha = None
            if called:
                ctx = E.build_ctx(inputs, derived)
                ctx_sha = hashlib.sha256(C.ctx_bytes(ctx)).hexdigest()
        except Exception as exc:  # noqa: BLE001 - one job's inputs never cost the batch
            results[key] = {**row, "failed": True, "error": f"ctx: {type(exc).__name__}: {str(exc)[:300]}"}
            continue
        if called:
            answer = runner.decide(ctx)
            stats = runner.stats()
            # The failed-decides rule's flag, as the Gym engine counts it (`runner.last_failed`): the House reads it,
            # so a program that raises, times out or is disqualified live leaves its lots by the same rule as in
            # its replay.
            failed = bool(runner.last_failed)
            row.update(stats=stats, ctx_sha=ctx_sha, failed=failed)
            if failed:
                row["why"] = _why_failed(stats)
            target = answer.get("target") if isinstance(answer, Mapping) and not answer.get("hold") else None
            if target is not None:
                at = str(answer.get("at") or E.OPEN)
                orders, rejects = E.plan_orders(target, at, lots, budget)
                row["rejects"] = rejects
                if not E.refused_whole(rejects):
                    row.update(hold=False, target={int(slot): float(w) for slot, w in dict(target).items()}, at=at,
                               orders=orders)
        else:
            standing = job.get("standing")
            if isinstance(standing, Mapping) and standing.get("target"):
                at = str(standing.get("at") or E.OPEN)
                elig = derived.elig
                eligible = [ids[col - ref] for col in range(ref, ref + len(ids)) if bool(elig[col])]
                working = [{"lid": None, "id": int(slot), "pending": True} for slot in standing.get("pending") or ()]
                orders, rejects = E.plan_orders(standing["target"], at, [*lots, *working], budget, standing=True,
                                                exited=[int(slot) for slot in standing.get("exited") or ()],
                                                eligible=eligible)
                row.update(at=at, orders=orders, rejects=rejects, standing=bool(orders))
        results[key] = row
    return {"ok": True, "results": results}


def _nice(payload: Mapping[str, Any], state: dict[str, Any]) -> None:
    """Raise the child's niceness to the payload's `nice`, once a child (a research decider's runs; raising it is
    always allowed, and a child that cannot is no reason to refuse a run)."""
    wanted = payload.get("nice")
    if wanted is None or state.get("niced"):
        return
    state["niced"] = True
    try:
        os.nice(max(0, int(wanted) - os.nice(0)))
    except (OSError, ValueError, TypeError):
        pass


def handle(op: str, payload: Mapping[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    """One request of the "panel" kind (the module docstring); {ok: False, error} for an unknown op. Never raises for
    a program's fault: a refused program is {ok: False, refused: True, error}."""
    from ..gym.safety import CodeRefused

    runners: dict[str, Any] = state.setdefault("runners", {})
    payload = payload if isinstance(payload, Mapping) else {}
    try:
        if op == "load":
            program = _load(payload)
            runners[str(payload["key"])] = program.start(timeout=float(payload.get("timeout", 1.0)),
                                                         max_errors=int(payload.get("max_errors", 25)),
                                                         budget_seconds=payload.get("budget_seconds"))
            return _identity(program)
        if op == "drop":
            runners.pop(str(payload.get("key")), None)
            return {"ok": True}
        if op == "decide":
            return _decide(payload, runners)
        if op == "needs":
            return _identity(_load(payload))
        if op == "run":
            from . import runner as RN

            _nice(payload, state)
            result = RN.run_bars(str(payload["code"]), dict(payload.get("params") or {}), payload["bars"],
                                 name=str(payload.get("name") or "program"), k=float(payload.get("k", 1.0)),
                                 capital=payload.get("capital"), placebos=int(payload.get("placebos") or 0),
                                 seed=payload.get("seed"), calls=bool(payload.get("calls")),
                                 style=bool(payload.get("style")))
            return {"ok": True, "result": result}
    except CodeRefused as exc:
        return {"ok": False, "refused": True, "error": str(exc)[:500]}
    return {"ok": False, "error": f"unknown panel op {op!r} (known: {', '.join(OPS)})"}


__all__ = ["OPS", "handle"]
