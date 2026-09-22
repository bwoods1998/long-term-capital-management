"""Versioned research and repair traces, collected for eventual fine-tuning. Collection only.

The goal document (section 3, Sept 22, 2026): capture what a model was given, what it produced,
what it cost and what came of it, so that successful work can one day train a cheaper model.
Training waits for enough validated data and a credible evaluation set; this module only makes
sure the data exists and is joined to its outcome.

Bodies (whole transcripts, strategy source) are private: they go to a 0700 directory under the
House root as gzip JSON, never to the ledger or a commit. The ledger gets a `trace.record`
pointer: `{task, id, version, model, inputs_sha256, outcome, cost_usd, useful}`. An outcome
learned later (a candidate adopted, a repair verified) is a NEW `trace.record` row with the same
id and a higher version: append-only, like every other correction on the ledger.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping

from .ledger import canonical, now_iso

SCHEMA = 1
TASKS = ("research", "repair")


def inputs_sha256(inputs: Any) -> str:
    return hashlib.sha256(canonical(inputs).encode("utf-8")).hexdigest()


class TraceStore:
    def __init__(self, root: str | Path, ledger: Any, *, clock=None):
        self.dir = Path(root) / "traces"
        self.ledger = ledger
        self.clock = clock
        self.dir.mkdir(parents=True, exist_ok=True)
        os.chmod(self.dir, 0o700)

    def path(self, trace_id: str) -> Path:
        return self.dir / f"{trace_id}.json.gz"

    def capture(self, task: str, *, key: str, model: str, inputs: Any, outputs: Any, cost_usd: Any,
                outcome: str, useful: bool | None, agent: str = "house", extra: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """Write the body privately, then the ledger pointer (version 1). Idempotent on `key`."""
        if task not in TASKS:
            raise ValueError(f"unknown trace task {task!r}")
        ident = trace_id(task, key)
        digest = inputs_sha256(inputs)
        body = {"schema": SCHEMA, "task": task, "id": ident, "key": key, "model": model, "agent": agent,
                "at": now_iso(self.clock) if self.clock else now_iso(), "inputs_sha256": digest,
                "inputs": inputs, "outputs": outputs, "cost_usd": str(cost_usd), "outcome": outcome,
                "useful": useful, **dict(extra or {})}
        target = self.path(ident)
        if not target.exists():
            tmp = target.with_suffix(".tmp")
            with gzip.open(tmp, "wt", encoding="utf-8") as handle:
                json.dump(body, handle, default=str, sort_keys=True)
            os.chmod(tmp, 0o600)
            os.replace(tmp, target)
        pointer = {"task": task, "id": ident, "version": 1, "model": model, "inputs_sha256": digest,
                   "outcome": outcome, "cost_usd": str(Decimal(str(cost_usd))), "useful": useful}
        self.ledger.append("trace.record", pointer, agent=agent, id=f"trace:{ident}:1")
        return pointer

    def outcome(self, trace_id: str, *, outcome: str, useful: bool | None, agent: str = "house") -> dict[str, Any] | None:
        """Join a later outcome (adopted, replay passed or failed, repair verified) as the next version."""
        rows = [e for e in self.ledger.iter(kinds="trace.record", agent=agent) if e.payload.get("id") == trace_id]
        if not rows:
            return None
        last = max(rows, key=lambda e: int(e.payload.get("version") or 0)).payload
        if last.get("outcome") == outcome and last.get("useful") == useful:
            return last  # nothing new: no row
        version = int(last.get("version") or 0) + 1
        pointer = {**{k: last.get(k) for k in ("task", "id", "model", "inputs_sha256", "cost_usd")},
                   "version": version, "outcome": outcome, "useful": useful}
        self.ledger.append("trace.record", pointer, agent=agent, id=f"trace:{trace_id}:{version}")
        return pointer

    def read(self, trace_id: str) -> dict[str, Any]:
        with gzip.open(self.path(trace_id), "rt", encoding="utf-8") as handle:
            return json.load(handle)


def trace_id(task: str, key: str) -> str:
    return hashlib.sha256(f"{task}:{key}".encode()).hexdigest()[:32]


def adoption_outcome(ledger: Any, registry: Any, agent_id: str, session: str, candidate: Mapping[str, Any]) -> tuple[str, bool]:
    """What the House did with a pass's candidate, from its own records: adopted in place (the
    agent now runs this code), a child seated on paper, a fork still waiting, or not adopted.
    Useful means installed AND replay-passing: a barren agent's failed-but-trading rewrite is
    adopted on purpose, but it is not a validated artifact to learn from."""
    passed = bool(candidate.get("passed"))
    agent = registry.get(agent_id) if registry is not None else None
    if agent is not None and getattr(agent, "code", None) == candidate.get("code"):
        return "adopted", passed
    admissions = [e.payload for e in ledger.read(kinds="agent.research", agent=agent_id, limit=400, newest=True)
                  if e.payload.get("tool") == "candidate_admission" and e.payload.get("session") == session]
    status = admissions[-1].get("status") if admissions else None
    if status == "admitted":
        return "forked", passed
    if status in ("queued", "deferred", "admitting"):
        return "fork_" + status, False
    return "not_adopted", False


def research_outcome(out: Any) -> tuple[str, bool | None]:
    """What a finished research pass produced, from its Pass: the replay verdict of its kept
    candidate, or why it ended without one. Useful means a replay-passing strategy file."""
    candidate = getattr(out, "candidate", None)
    if candidate:
        passed = bool(candidate.get("passed"))
        return ("candidate_passed" if passed else "candidate_failed"), passed
    reason = str(getattr(out, "reason", "") or "")
    if reason == "finished":
        return "abstained", None  # an abstention is judged later (was a candidate missed?), not now
    return f"ended: {reason[:80]}", False
