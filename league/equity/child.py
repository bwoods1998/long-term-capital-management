"""The "equity" kind inside the decider's isolated child: load, drop, decide and run equity programs.

Owner: hooks. Called only by `league/live/decider.py`'s child through `league.equity.kinds.module_for("equity")`. Every
answer is JSON-safe (the child replies JSON, never pickle); the payload arrives pickled from the House (the trusted
side). `state` is this kind's own dict in the child (its runners keyed by instance), kept across messages and lost
with the child (the parent then reloads every loaded instance before its next request, as for options programs).

OPS:
- "load"   {key, code, params, name, timeout, max_errors} -> {ok, needs, sha, run_sha} (an `EquityRunner` kept at
           state["runners"][key]); {ok: False, refused: True, error} when the program does not load;
- "drop"   {key} -> {ok};
- "decide" {jobs: [{key, inputs: league.equity.ctx.Inputs}]} -> {ok, results: {key: {intents, stats, ctx_sha}}}: the
           ctx is `league.equity.ctx.build(inputs)`, exactly the Gym's (I6), and `ctx_sha` the sha256 of its
           `ctx_bytes` (the decision's provenance);
- "needs"  {code, params, name} -> {ok, needs, sha, run_sha} (load, read NEEDS, drop: the parent never executes a
           program to learn what to slice);
- "run"    {code, params, name, bars: league.equity.store.Bars, k, capital} -> {ok, result}
           (`league.equity.runner.run_bars`: Train, Validation, the sealed look and the screen's Train-era runs).
"""

from __future__ import annotations

from typing import Any, Mapping

OPS = ("load", "drop", "decide", "needs", "run")


def handle(op: str, payload: Mapping[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    """One request of the "equity" kind (the module docstring); {ok: False, error} for an unknown op. Never raises for
    a program's fault: a refused program is {ok: False, refused: True, error}."""
    raise NotImplementedError("hooks: league/equity/child.py handle")


__all__ = ["OPS", "handle"]
