"""Who is in the league: every agent's identity, strategy, lineage and fate, folded from the ledger.

An agent is a strategy program with a bank account of compute credits. Its record belongs to its
code, so an agent above replay never edits itself: an improvement is a child (a fork) that carries
the new code, starts from its own replay, and is endowed by its parent. An agent still on rung 0
has no record to protect and may adopt new code directly; every attempt is a counted trial.

Strategy source is kept on the ledger under a private key: the public record shows its hash, its
parameters, its family and its results, not the code.
"""

from __future__ import annotations

import hashlib
import re
import threading
from dataclasses import dataclass, field
from typing import Any, Mapping

from .ledger import Ledger
from .parameters import require_valid

NAME = re.compile(r"^[a-z][a-z0-9-]{1,33}$")  # the site takes ids up to 40 characters, and a fork appends -N


def code_sha(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


@dataclass
class Agent:
    id: str
    name: str
    family: str
    venue: str  # alpaca | kalshi
    horizon: str  # hour | day
    style: str
    generation: int
    parent: str | None
    code: str
    params: dict[str, Any]
    wake_minutes: int
    born_at: str
    alive: bool = True
    died_at: str | None = None
    cause: str | None = None
    needs: dict[str, Any] = field(default_factory=dict)
    specialty: str | None = None  # its niche in league/niches.json, for life; None for an agent born before niches
    #: The name its line is numbered from. Six agents of one desk are `meriwether`, `meriwether-2`
    #: ..., and a child of any of them is the next free number in that line, as the first run's
    #: desks were Mullins VI and VIII. Defaults to the id, for an agent born before lines.
    line: str = ""
    founder: str | None = None  # which founder of its specialty it was born from (`league/niches.json`)

    @property
    def niche(self) -> str:
        return self.specialty or f"{self.venue}/{self.horizon}/{self.style}"

    @property
    def code_sha256(self) -> str:
        return code_sha(self.code)


def niche_of(needs: Mapping[str, Any]) -> tuple[str, str, str]:
    venue = str(needs.get("venue") or "").lower()
    horizon = str(needs.get("horizon") or "").lower()
    style = re.sub(r"[^a-z0-9-]+", "-", str(needs.get("style") or "general").lower()).strip("-")[:24] or "general"
    if venue not in ("alpaca", "kalshi"):
        raise ValueError("NEEDS['venue'] must be 'alpaca' or 'kalshi'")
    if horizon not in ("hour", "day"):
        raise ValueError("NEEDS['horizon'] must be 'hour' or 'day'")
    return venue, horizon, style


def wake_minutes_of(needs: Mapping[str, Any]) -> int:
    try:
        return max(5, min(int(needs.get("wake_minutes") or 15), 1440))
    except (TypeError, ValueError):
        return 15


class Registry:
    def __init__(self, ledger: Ledger):
        self.ledger = ledger
        self.agents: dict[str, Agent] = {}
        #: agent id -> {"since", "note", "session"} while its entries are paused (`entries_paused`).
        self.paused: dict[str, dict[str, Any]] = {}
        self._cursor = 0
        self._lock = threading.RLock()
        self.refresh()

    def refresh(self) -> None:
        with self._lock:
            while True:
                batch = self.ledger.read(kinds=("agent.born", "agent.strategy", "agent.family", "agent.died"), after=self._cursor, limit=5000)
                if not batch:
                    return
                for entry in batch:
                    self._apply(entry.kind, entry.agent, entry.payload, entry.at)
                    self._cursor = entry.seq

    def _apply(self, kind: str, agent_id: str, p: Mapping[str, Any], at: str) -> None:
        if kind == "agent.born":
            self.agents[agent_id] = Agent(
                id=agent_id, name=p["name"], family=p["family"], venue=p["venue"], horizon=p["horizon"],
                style=p["style"], generation=int(p["generation"]), parent=p.get("parent"), code=p["_code"],
                params=dict(p.get("params") or {}), wake_minutes=int(p.get("wake_minutes") or 15), born_at=at,
                needs=dict(p.get("needs") or {}), specialty=p.get("specialty"),
                line=str(p.get("line") or p["name"]), founder=p.get("founder"),
            )
        elif kind == "agent.strategy" and agent_id in self.agents:
            agent = self.agents[agent_id]
            agent.code = p["_code"]
            agent.params = dict(p.get("params") or {})
            agent.needs = dict(p.get("needs") or agent.needs)
            agent.wake_minutes = int(p.get("wake_minutes") or agent.wake_minutes)
            # X1 (Sept 24, 2026): an agent's own pause and resume of its entries are `agent.strategy`
            # rows too (`House._apply_controls`), restating the strategy in force with `control`.
            if p.get("control") == "pause_entries":
                self.paused[agent_id] = {"since": at, "note": p.get("note"), "session": p.get("session")}
            elif p.get("control") == "resume_entries":
                self.paused.pop(agent_id, None)
        elif kind == "agent.family" and agent_id in self.agents and p.get("family"):
            # C8 (Sept 25, 2026; `league/families.py`): the family of the agent's program from `since_seq` on -- a birth
            # or a rewrite filed under its mechanism's family. The birth row keeps the label it was born with.
            self.agents[agent_id].family = str(p["family"])
        elif kind == "agent.died" and agent_id in self.agents:
            agent = self.agents[agent_id]
            agent.alive = False
            agent.died_at = at
            agent.cause = p.get("cause")

    # ------------------------------------------------------------------ reads
    def get(self, agent_id: str) -> Agent | None:
        return self.agents.get(agent_id)

    def entries_paused(self, agent_id: str) -> dict[str, Any] | None:
        """{"since", "note", "session"} while the agent has paused its entries (`pause_entries`),
        else None. Folded from the ledger like everything else here, so a restart keeps it."""
        with self._lock:
            found = self.paused.get(agent_id)
            return dict(found) if found else None

    def living(self) -> list[Agent]:
        with self._lock:
            return sorted((a for a in self.agents.values() if a.alive), key=lambda a: a.born_at + a.id)

    def dead(self) -> list[Agent]:
        with self._lock:
            return sorted((a for a in self.agents.values() if not a.alive), key=lambda a: a.died_at or "")

    def lineage(self, agent_id: str) -> list[str]:
        out, seen = [], set()
        current = self.agents.get(agent_id)
        while current is not None and current.id not in seen:
            out.append(current.id)
            seen.add(current.id)
            current = self.agents.get(current.parent) if current.parent else None
        return out

    # ----------------------------------------------------------------- writes
    def born(self, *, name: str, family: str, code: str, needs: Mapping[str, Any], params: Mapping[str, Any] | None = None,
             parent: str | None = None, reason: str = "", specialty: str | None = None, founder: str | None = None) -> Agent:
        if not NAME.match(name):
            raise ValueError(f"agent name {name!r} must be lowercase letters, digits and dashes")
        venue, horizon, style = niche_of(needs)
        require_valid(params or {}, needs)
        with self._lock:
            return self._born(name, family, code, needs, params, parent, reason, venue, horizon, style, specialty, founder)

    def _born(self, name, family, code, needs, params, parent, reason, venue, horizon, style, specialty=None, founder=None) -> Agent:
        generation = (self.agents[parent].generation + 1) if parent and parent in self.agents else 1
        taken = {a.id for a in self.agents.values()}
        agent_id, n = name, 1
        while agent_id in taken:
            n += 1
            agent_id = f"{name}-{n}"
        self.ledger.append(
            "agent.born",
            {
                "name": agent_id, "family": family, "venue": venue, "horizon": horizon, "style": style,
                "generation": generation, "parent": parent, "code_sha256": code_sha(code), "params": dict(params or {}),
                "needs": dict(needs), "wake_minutes": wake_minutes_of(needs), "reason": reason, "specialty": specialty,
                "line": name, "founder": founder, "_code": code,
            },
            agent=agent_id,
            id=f"born:{agent_id}",
        )
        self.refresh()
        return self.agents[agent_id]

    def adopt(self, agent_id: str, *, code: str, needs: Mapping[str, Any], params: Mapping[str, Any], reason: str) -> Agent:
        """A rung-0 agent takes new code. (Above rung 0 the House forks instead.)"""
        agent = self.agents[agent_id]
        venue, horizon, style = niche_of(needs)
        if (venue, horizon) != (agent.venue, agent.horizon):
            raise ValueError("a strategy change may not move the agent to another venue or horizon")
        require_valid(params, needs)
        self.ledger.append(
            "agent.strategy",
            {"code_sha256": code_sha(code), "params": dict(params), "needs": dict(needs),
             "wake_minutes": wake_minutes_of(needs), "reason": reason, "_code": code},
            agent=agent_id,
        )
        self.refresh()
        return self.agents[agent_id]

    def died(self, agent_id: str, cause: str, detail: str = "") -> None:
        if agent_id in self.agents and self.agents[agent_id].alive:
            self.ledger.append("agent.died", {"cause": cause, "detail": detail}, agent=agent_id, id=f"died:{agent_id}")
            self.refresh()
