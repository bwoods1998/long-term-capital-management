"""The House's one hook object for Jev's cheap sensing work (`league/config.json` "jev").

`House` calls four things and nothing else, so its own edits stay small:

- `research_due(agent, last=, due=, forced=)` from `House.research_due`, once every existing
  check has passed: the research gate (`league/research_gate.py`) may skip a clock-due session.
  A gate that raises never stops research: the clock decides, as it did before.
- `tick(open_for_business)` from `House.tick`: explicit inactivity reasons every
  `inactivity_seconds`, and -- only while the floor is open for business, since a maintenance
  pause stops paid work -- triage, hypothesis links and exposure groups as background jobs.
- `health()` for health.json: Jev spend and caps, gate totals, inactivity counts, triage groups,
  exposure groups.

Every switch defaults on and can be turned off in config without a code change; with "jev"
"enabled": false the House behaves exactly as before this module existed.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any, Mapping

from .exposure import Exposure
from .hypothesis_memory import HypothesisMemory
from .research_gate import GateState, Inactivity, ResearchGate
from .triage import Triage


class JevFloor:
    def __init__(self, house: Any, sensor: Any, settings: Mapping[str, Any] | None = None, *, rng: Any = None):
        self.house, self.sensor = house, sensor
        self.settings = dict(settings or {})
        root = Path(house.root)
        self.state = GateState(root / "research-gate.json")
        gate_settings = dict(self.settings.get("research_gate") or {})
        self.inactivity = Inactivity(house, self.state, settings=gate_settings)
        self.gate = ResearchGate(house, self.state, self.inactivity, sensor=sensor, settings=gate_settings, rng=rng) \
            if gate_settings.get("enabled", True) else None
        niche = lambda agent_id: getattr(house.registry.get(agent_id), "niche", None)  # noqa: E731
        family = lambda agent_id: getattr(house.registry.get(agent_id), "family", None)  # noqa: E731
        triage = dict(self.settings.get("triage") or {})
        self.triage = Triage(house.ledger, sensor, clock=house.clock, path=root / "triage.json", settings=triage,
                             lineage=house.registry.lineage, requests=lambda: house.commons._requests(),
                             niche_of=niche, family_of=family) if triage.get("enabled", True) else None
        links = dict(self.settings.get("hypothesis_links") or {})
        self.memory = HypothesisMemory(house.ledger, sensor, path=root / "hypothesis-memory.json", clock=house.clock,
                                       settings=links, niche_of=niche) if links.get("enabled", True) else None
        exposure = dict(self.settings.get("exposure") or {})
        self.exposure = Exposure(house, sensor, clock=house.clock, settings=exposure) if exposure.get("enabled", True) else None
        self.inactivity_seconds = float(self.settings.get("inactivity_seconds", 300))
        self._last_inactivity = 0.0

    def research_due(self, agent: Any, *, last: float, due: bool, forced: str = "") -> bool:
        if not due and not forced:
            return False
        if self.gate is None:
            return True
        try:
            return self.gate.allow(agent, last=last, forced=forced)
        except Exception as exc:  # noqa: BLE001 - the gate saves money; it must never cost research
            self.house.alert("warning", f"research gate failed open for {agent.id} ({type(exc).__name__}: {str(exc)[:160]})")
            return True

    def tick(self, open_for_business: bool) -> None:
        now = self.house.clock()
        if now - self._last_inactivity >= self.inactivity_seconds:
            self._last_inactivity = now
            try:
                self.inactivity.update(self.house.registry.living())
            except Exception as exc:  # noqa: BLE001
                self.house.alert("warning", f"inactivity sweep failed ({type(exc).__name__}: {str(exc)[:160]})")
        if not open_for_business:
            return
        for key, job in (("jev:triage", self.triage), ("jev:links", self.memory), ("jev:exposure", self.exposure)):
            if job is not None and job.due():
                self.house._background(key, job.run)

    def failure_history(self, ref: str, niche: str | None = None) -> dict[str, Any] | None:
        """A mechanism's failures and its linked mechanisms' failures, kept apart (hypothesis_memory)."""
        return self.memory.failure_history(ref, niche) if self.memory is not None else None

    def health(self) -> dict[str, Any]:
        reasons = Counter(str((row or {}).get("reason")) for row in self.state.data.get("inactive", {}).values())
        return {"sensor": self.sensor.stats() if self.sensor is not None else None,
                "gate": dict(self.state.data.get("totals") or {}) if self.gate is not None else None,
                "inactive": dict(reasons),
                "triage": self.triage.stats() if self.triage is not None else None,
                "hypothesis_memory": self.memory.stats() if self.memory is not None else None,
                "exposure": self.exposure.latest if self.exposure is not None else None}
