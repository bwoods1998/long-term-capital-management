"""Task-aware model routing: which kind of intelligence a task is worth, and why.

The goal document (section 3, Sept 22, 2026): deterministic work goes to code, cheap semantic
decisions to Jev, routine research to the strongest economical option by MEASURED evidence, and
difficult synthesis or engineering to Astra. This module is the table that says so, the one
evidence-driven choice it makes (the Sail profile a new research session runs on), and the
record of every decision on the ledger as `route.decision`.

Decisions are aggregated: one row per (hour, task, route, model, reason) with a count, written
when the hour rolls over, because a row per research session would be ~2,000 rows a day of the
same fact. A restart loses at most the current hour's counts, never a decision's effect.

What the evidence may change is deliberately small. Only a Sail profile for a NEW session, only
among profiles measured on the same frozen research packets, only when the challenger produced at
least as many useful artifacts as the baseline with enough samples, and only when its useful
artifacts cost less per dollar. It never touches spending caps, agent credits or trading.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping

from .ledger import now_iso

EVIDENCE_PATH = Path(__file__).with_name("routing_evidence.json")


@dataclass(frozen=True)
class Route:
    route: str  # code | jev | research | astra
    model: str
    reason: str


#: The table. `research` rows are resolved by `TaskRouter.research_profile` from evidence.
TABLE: dict[str, Route] = {
    # Deterministic work: exact facts are never a model's job (numbers, dates, ids, budgets).
    "market_availability": Route("code", "none", "venue calendars and listings are exact facts"),
    "data_freshness": Route("code", "none", "tape timestamps and coverage are counted, not judged"),
    "fills_and_refusals": Route("code", "none", "fills, refusals and their counts are ledger rows"),
    "budget_and_admission": Route("code", "none", "money and admission rules are code by constitution"),
    # Cheap semantic decisions: Jev, typed and cached ($0.042/M input; ~$5 of lifetime cap left).
    "research_gate_semantic": Route("jev", "jev-1.13.0", "does a new note matter to this hypothesis: a yes/no on meaning"),
    "triage_classify": Route("jev", "jev-1.13.0", "which requests describe the same missing feed or bug"),
    "hypothesis_rewording": Route("jev", "jev-1.13.0", "is a new mechanism a rewording of a tested one"),
    "agent_classify": Route("jev", "jev-1.13.0", "an agent's yes/no question over many records, charged at cost"),
    # Routine research: the strongest economical option by measured evidence (see research_profile).
    "research_routine": Route("research", "evidence", "routine research is bought where useful artifacts are cheapest"),
    # Difficult synthesis and engineering: Astra. Sept 20-22 evidence: the teacher and auditor
    # earn their keep; the code roles mostly fail CI, so they are routed here but still judged by CI.
    "strategy_synthesis": Route("astra", "gpt-6-astra", "coherent new mechanisms from evidence: frontier reasoning"),
    "repair_patch": Route("astra", "gpt-6-astra", "a structural blocker needs engineering, not a parameter"),
    "audit": Route("astra", "gpt-6-astra", "real-money admission needs the independent strongest reviewer"),
    "consult": Route("astra", "gpt-6-astra", "an earned consultation buys the frontier model"),
}


def load_evidence(path: Path | None = None) -> dict[str, Any]:
    try:
        return json.loads((path or EVIDENCE_PATH).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def best_profile(evidence: Mapping[str, Any], baseline: str, candidates: list[str], *, min_samples: int = 10,
                 max_median_seconds: float | None = None) -> tuple[str, str]:
    """(profile, reason). A challenger replaces the baseline only if, on the same packets, its
    useful-artifact RATE is at least the baseline's, with at least `min_samples` measured, and its
    useful artifacts cost less per dollar. Token prices alone never decide it."""
    arms = (evidence or {}).get("arms") or {}
    base = arms.get(baseline)
    if not base or int(base.get("samples") or 0) < min_samples:
        return baseline, f"baseline {baseline} kept: fewer than {min_samples} measured samples"
    best, best_rate, why = baseline, _per_dollar(base), f"baseline {baseline} kept: no challenger beat it on useful artifacts per dollar"
    for name in candidates:
        arm = arms.get(name)
        if not arm or name == baseline or int(arm.get("samples") or 0) < min_samples:
            continue
        if _rate(arm) < _rate(base):
            continue  # cheaper but less useful is not economical
        if max_median_seconds is not None and float(arm.get("median_seconds") or 0) > max_median_seconds:
            continue
        rate = _per_dollar(arm)
        if rate is not None and (best_rate is None or rate > best_rate):
            best, best_rate = name, rate
            why = (f"{name}: {arm['useful']}/{arm['samples']} useful vs {baseline} {base['useful']}/{base['samples']}, "
                   f"{rate:.0f} useful per $ ({evidence.get('source', 'routing evidence')})")
    return best, why


def _cheaper(profile: str, than: str) -> bool:
    """Whether a Sail profile is priced below another (output rate, then input): a session already
    on a cheaper one than the abstention lock's is left where it is. Luna is not a Sail profile."""
    from ltcm.provider import PROFILES, rates

    if profile not in PROFILES or than not in PROFILES:
        return False
    (inp, _, out), (inp2, _, out2) = rates(profile), rates(than)
    return (out, inp) < (out2, inp2)


def _rate(arm: Mapping[str, Any]) -> float:
    """Useful artifacts per ATTEMPT: a provider error (a 503, a 25-minute timeout) is a turn the
    House waited for and got nothing from, so it counts against the route like a useless answer."""
    return int(arm.get("useful") or 0) / max(1, int(arm.get("samples") or 0) + int(arm.get("provider_errors") or 0))


def _per_dollar(arm: Mapping[str, Any]) -> float | None:
    cost = float(Decimal(str(arm.get("cost_usd") or 0)))
    return (int(arm.get("useful") or 0) / cost) if cost > 0 else None


class TaskRouter:
    def __init__(self, ledger: Any, *, clock=time.time, evidence: Mapping[str, Any] | None = None,
                 config: Mapping[str, Any] | None = None):
        self.ledger, self.clock = ledger, clock
        self.evidence = dict(evidence if evidence is not None else load_evidence())
        #: research_routes.json "routing": {"record": bool, "sail_by_evidence": bool, "candidates": [...]}
        self.config = dict(config or {})
        self._lock = threading.Lock()
        self._counts: dict[tuple[str, str, str, str, str], int] = {}
        self._evidence_note: dict[tuple[str, str, str, str], Any] = {}
        #: (agent) -> the profile an agent under the abstention lock must research on, or None
        #: (`research_gate.ResearchGate.lock_profile`, wired by the service). None: no lock.
        self.lock: Any = None

    def route(self, task: str, *, model: str | None = None, reason: str | None = None, evidence: Any = None) -> Route:
        """The table's route for a task, recorded. Unknown tasks are code: nothing is bought by default."""
        row = TABLE.get(task) or Route("code", "none", "unknown task: nothing is bought by default")
        decided = Route(row.route, model or row.model, reason or row.reason)
        self._note(task, decided, evidence)
        return decided

    def research_settings(self, agent: Any, settings: Mapping[str, Any]) -> dict[str, Any]:
        """The settings a NEW research session starts with. Luna-cohort sessions keep Luna (its
        cohort is the owner's split); a Sail session may move to the profile the evidence favours
        when `sail_by_evidence` is on. Every outcome is recorded with its reason."""
        out = dict(settings)
        profile = str(out.get("profile") or "")
        locked = self._locked(agent)
        if locked and locked != profile and not _cheaper(profile, locked):
            # Sept 24, 2026 (L2): an agent under the abstention lock has abstained three times in a
            # row; its next session is bought on the cheapest profile, whatever cohort it is in.
            out.update(profile=locked, fast_profile="")
            self._note("research_routine", Route("research", locked, "abstention lock: the cheapest profile"), None)
            return out
        if profile == "openai_luna":
            from .fast_research import MODEL as LUNA
            self._note("research_routine", Route("research", LUNA, "owner cohort: Luna share of new sessions"), None)
            return out
        chosen, why = profile, "configured Sail profile"
        if self.config.get("sail_by_evidence"):
            chosen, why = best_profile(self.evidence, profile, list(self.config.get("candidates") or []),
                                       min_samples=int(self.config.get("min_samples") or 10),
                                       max_median_seconds=self.config.get("max_median_seconds"))
        if chosen != profile:
            out["profile"] = chosen
        self._note("research_routine", Route("research", chosen, why), (self.evidence or {}).get("source"))
        return out

    def _locked(self, agent: Any) -> str | None:
        if self.lock is None:
            return None
        try:
            return self.lock(agent) or None
        except Exception:  # noqa: BLE001 - a lock that cannot be read changes no route
            return None

    # ----------------------------------------------------------------- record
    def _note(self, task: str, decided: Route, evidence: Any) -> None:
        if self.ledger is None or self.config.get("record") is False:
            return
        hour = now_iso(self.clock)[:13]
        rows = []
        with self._lock:
            key = (hour, task, decided.route, decided.model, decided.reason[:200])
            self._counts[key] = self._counts.get(key, 0) + 1
            self._evidence_note[key[1:]] = evidence
            for old in [k for k in self._counts if k[0] < hour]:
                rows.append((old, self._counts.pop(old)))
        for (at, t, route, model, reason), count in rows:
            self._write(at, t, route, model, reason, count)

    def flush(self) -> int:
        """Write every pending count, including the current hour's (on shutdown or in tests)."""
        with self._lock:
            rows, self._counts = list(self._counts.items()), {}
        for (at, t, route, model, reason), count in rows:
            self._write(at, t, route, model, reason, count, partial=True)
        return len(rows)

    def _write(self, hour, task, route, model, reason, count, partial=False) -> None:
        payload = {"task": task, "route": route, "model": model, "reason": reason,
                   "evidence": self._evidence_note.get((task, route, model, reason)),
                   "hour": hour, "count": count, "partial": partial}
        ident = "route:" + hashlib.sha256(f"{hour}|{task}|{route}|{model}|{reason}|{now_iso(self.clock)}|{count}|{partial}".encode()).hexdigest()[:40]
        try:
            self.ledger.append("route.decision", payload, id=ident)
        except Exception:  # noqa: BLE001 - a record that cannot be written never blocks the route
            pass


def table() -> list[dict[str, Any]]:
    return [{"task": task, **asdict(route)} for task, route in TABLE.items()]
