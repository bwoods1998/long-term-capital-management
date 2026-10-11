"""The "equity" kind inside the decider's isolated child: load, drop, decide and run equity programs.

Owner: hooks. Called only by `league/live/decider.py`'s child through `league.equity.kinds.module_for("equity")`. Every
answer is JSON-safe (the child replies JSON, never pickle); the payload arrives pickled from the House (the trusted
side). `state` is this kind's own dict in the child (its runners keyed by instance), kept across messages and lost
with the child (the parent then reloads every loaded instance before its next request, as for options programs).

OPS:
- "load"   {key, code, params, name, timeout, max_errors} -> {ok, needs, sha, run_sha, params} (an `EquityRunner`
           kept at state["runners"][key]; `params` the program's merged PARAMS, the live ctx's: I6); {ok: False,
           refused: True, error} when the program does not load;
- "drop"   {key} -> {ok};
- "decide" {jobs: [{key, inputs: league.equity.ctx.Inputs}]} -> {ok, results: {key: {intents, stats, ctx_sha,
           failed}}}: the ctx is `league.equity.ctx.build(inputs)`, exactly the Gym's (I6), and `ctx_sha` the sha256 of
           its `ctx_bytes` (the decision's provenance), taken BEFORE the program sees the ctx; `failed` is the runner's
           `last_failed` (the program raised, ran past its limit or is disqualified: the Gym engine counts exactly this
           toward A8.5's two failed decides, league/equity/engine.py `decide`, and the House counts the same answer),
           with `why` when it did; a key with no loaded runner answers {intents: [], stats: None, missing: True,
           failed: True}, and inputs the ctx cannot be built from {intents: [], stats, error, failed: True} (that job
           only: the rest of the batch goes on): neither is the program's own failure, and both are failed decides;
- "needs"  {code, params, name} -> {ok, needs, sha, run_sha, params} (load, read NEEDS, drop: the parent never
           executes a program to learn what to slice);
- "run"    {code, params, name, bars: league.equity.store.Bars, k, capital} -> {ok, result}
           (`league.equity.runner.run_bars`: Train, Validation, the sealed look and the screen's Train-era runs).

Imports are made inside `handle`, per op, so the child imports only what a request needs (its runtime is
league/equity/kinds.py `RUNTIME`).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

OPS = ("load", "drop", "decide", "needs", "run")


def _load(payload: Mapping[str, Any]) -> Any:
    from . import program as P

    return P.load_program(str(payload["code"]), name=str(payload.get("name") or "program"),
                          params=dict(payload.get("params") or {}))


def _identity(program: Any) -> dict[str, Any]:
    """The loaded program's answer: its NEEDS, shas and MERGED PARAMS (its declaration with the overrides): the House
    builds the live ctx with them (league/equity/live.py `_inputs`), as the Gym's engine does (`program.params`), so a
    program reads the same `ctx.params` live and in replay (I6)."""
    return {"ok": True, "needs": program.needs.as_dict(), "sha": program.sha, "run_sha": program.run_sha,
            "params": json.loads(json.dumps(program.params))}


def _why_failed(stats: Mapping[str, Any]) -> str:
    """Why a runner's last decide failed, from its stats: its disqualification, else its latest error message."""
    messages = stats.get("messages") or []
    why = stats.get("disqualified") or (messages[-1] if messages else "")
    return str(why or "its decide raised or ran past its limit")[:300]


def _decide(payload: Mapping[str, Any], runners: Mapping[str, Any]) -> dict[str, Any]:
    from . import ctx as C

    results: dict[str, Any] = {}
    for job in payload.get("jobs") or ():
        key = str(job["key"])
        runner = runners.get(key)
        if runner is None:
            results[key] = {"intents": [], "stats": None, "missing": True, "failed": True}
            continue
        try:
            ctx = C.build(job["inputs"])
            ctx_sha = hashlib.sha256(C.ctx_bytes(ctx)).hexdigest()
        except Exception as exc:  # noqa: BLE001 - one job's inputs never cost the batch
            results[key] = {"intents": [], "stats": runner.stats(), "failed": True,
                            "error": f"ctx: {type(exc).__name__}: {str(exc)[:300]}"}
            continue
        intents = runner.decide(ctx)
        stats = runner.stats()
        # A8.5's FAILED DECIDE, as the Gym engine counts it (`runner.last_failed`): the House reads this flag, so a
        # program that raises, times out or is disqualified live leaves its lots by the same rule as in its replay.
        failed = bool(runner.last_failed)
        results[key] = {"intents": intents, "stats": stats, "ctx_sha": ctx_sha, "failed": failed}
        if failed:
            results[key]["why"] = _why_failed(stats)
    return {"ok": True, "results": results}


def handle(op: str, payload: Mapping[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    """One request of the "equity" kind (the module docstring); {ok: False, error} for an unknown op. Never raises for
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

            result = RN.run_bars(str(payload["code"]), dict(payload.get("params") or {}), payload["bars"],
                                 name=str(payload.get("name") or "program"), k=float(payload.get("k", 1.0)),
                                 capital=payload.get("capital"))
            return {"ok": True, "result": result}
    except CodeRefused as exc:
        return {"ok": False, "refused": True, "error": str(exc)[:500]}
    return {"ok": False, "error": f"unknown equity op {op!r} (known: {', '.join(OPS)})"}


__all__ = ["OPS", "handle"]
