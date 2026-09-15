"""Variant populations: breed desks, score them forward, retire the ones that do not earn.

A *family* (`earnings`, `filings`, `kalshi`) is a mandate. A *variant* is one manifest inside that
family: same mandate, different persona, cadence, reasoning effort and memory budget, plus its own
playbook. Variants are compared only on forward results recorded in the event log; no backtest
survives contact with this module.

Three operations, all of them additive:

* `select()` retires the worst paper variant in a family when it sits below the family median by
  a published margin, then spawns a replacement whose parent is the retired variant and whose
  playbook is rewritten from the parent's post-mortems and the best sibling's playbook.
* `promote()` moves a paper variant to live capital, and only when `Committee.gates` pass.
* `score()` is the same return-over-pain number the committee uses, so a desk cannot be good by
  one measure and bad by another depending on who is asking.

Manifests are **never edited**. Retirement and promotion are events; a new variant is a new file.
That is what makes the lineage auditable years later.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from .broker import text
from .committee import Committee, capital_mode, promoted_desks, retired_desks
from .events import EventLog, now_iso
from .ledger import DeskLedger, iso_time
from .manifest import DeskManifest, ManifestError, load_manifest

ZERO = Decimal(0)

#: A child's id is its parent's id and the child's generation: `rosenfeld` -> `rosenfeld-2` ->
#: `rosenfeld-2-3`. The lineage is legible in the id itself, which is the point.
ROMAN = (
    (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"),
    (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
)
ROMAN_SUFFIX = re.compile(r"\s+[IVXLCDM]+$")

#: Mutations are drawn from these fixed menus. Anything not listed cannot be invented at runtime.
EFFORTS = ("low", "medium", "high")
MEMORY_LIMITS = (20, 40, 60, 80)
SESSION_SHIFTS = (-45, -20, 20, 45)
PERSONA_TRAITS = (
    "Prefers fewer, larger decisions and says so when the evidence is thin.",
    "Reads the cash flow statement before the income statement, always.",
    "Writes the counter-argument to every thesis before proposing an order.",
    "Sizes into a position over two sessions rather than one.",
    "Treats an unexplained price move as evidence against the thesis, not for it.",
    "Names the exit condition in the same sentence as the entry.",
)

DEFAULT_CONFIG: dict[str, Any] = {
    "min_days": 21,
    "min_decisions": 20,
    "min_variants": 2,
    "max_variants": 6,
    "margin": "2.0",  # percentage points below the family median
    "playbook_profile": "pro_flex",
    "playbook_budget_usd_per_day": "1.00",
    "playbook_reasoning_effort": "medium",
    "playbook_max_output_tokens": 6144,
    "playbook_max_chars": 12_000,
}


def roman(number: int) -> str:
    """`2` -> `II`. Generations are counted in the old way, like the partners themselves."""
    number = int(number)
    if not 1 <= number <= 3999:
        return str(number)
    out = []
    for value, glyph in ROMAN:
        while number >= value:
            out.append(glyph)
            number -= value
    return "".join(out)


def base_name(name: str) -> str:
    """A desk name without its generation suffix, so `Rosenfeld II` breeds `Rosenfeld III`."""
    stripped = ROMAN_SUFFIX.sub("", str(name).strip())
    return stripped.strip() or str(name).strip()


def _hash_int(value: str) -> int:
    return int(hashlib.sha256(value.encode("utf-8")).hexdigest(), 16)


def _median(values: list[Decimal]) -> Decimal:
    if not values:
        return ZERO
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def _shift_clock(value: str, minutes: int) -> str:
    hour, minute = int(value[:2]), int(value[3:5])
    total = (hour * 60 + minute + minutes) % (24 * 60)
    return f"{total // 60:02d}:{total % 60:02d}"


def _atomic_write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp-{os.getpid()}")
    tmp.write_text(body, encoding="utf-8")
    tmp.replace(path)


class Evolution:
    """Spawn, retire and promote desk variants on forward evidence alone."""

    def __init__(
        self,
        log: EventLog,
        manifests_dir: str | Path,
        playbooks_dir: str | Path,
        provider: Any = None,
        clock: Callable[[], float] = time.time,
        config: Mapping[str, Any] | None = None,
    ):
        self.log = log
        self.manifests_dir = Path(manifests_dir)
        self.playbooks_dir = Path(playbooks_dir)
        self.provider = provider
        self.clock = clock
        self.config = {**DEFAULT_CONFIG, **dict(config or {})}
        self._ledgers: dict[str, DeskLedger] = {}

    # ------------------------------------------------------------------ helpers
    def now(self) -> str:
        return now_iso(self.clock)

    def ledger(self, desk_id: str) -> DeskLedger:
        ledger = self._ledgers.get(desk_id)
        if ledger is None:
            ledger = self._ledgers[desk_id] = DeskLedger(self.log, desk_id)
        return ledger

    def manifests(self) -> dict[str, DeskManifest]:
        out: dict[str, DeskManifest] = {}
        for path in sorted(self.manifests_dir.glob("*.json")):
            try:
                manifest = load_manifest(path)
            except ManifestError:
                continue
            out[manifest.id] = manifest
        return out

    def active(self) -> dict[str, DeskManifest]:
        retired = retired_desks(self.log)
        return {k: v for k, v in self.manifests().items() if k not in retired}

    def families(self) -> dict[str, list[DeskManifest]]:
        grouped: dict[str, list[DeskManifest]] = {}
        for manifest in self.active().values():
            grouped.setdefault(manifest.family, []).append(manifest)
        for variants in grouped.values():
            variants.sort(key=lambda m: m.id)
        return grouped

    def committee(self, manifests: Mapping[str, DeskManifest] | None = None) -> Committee:
        roster = dict(manifests or self.active())
        return Committee(
            self.log,
            roster,
            {desk_id: self.ledger(desk_id) for desk_id in roster},
            provider=self.provider,
            clock=self.clock,
            config=self.config.get("committee") or {},
        )

    # ------------------------------------------------------------------ scoring
    def score(self, desk: DeskManifest | str, now: Any = None) -> Decimal:
        """Return per unit of pain: `return_pct / (1 + 0.5 * max_drawdown)`."""
        desk_id = desk if isinstance(desk, str) else desk.id
        at = iso_time(now) if now is not None else self.now()
        state = self.ledger(desk_id).state(at)
        divisor = Decimal(1) + Decimal("0.5") * state.max_drawdown_pct
        if divisor <= 0:
            return ZERO
        return (state.time_weighted_return_pct / divisor).quantize(Decimal("0.000001"))

    def evidence(self, desk_id: str, at: str) -> dict[str, Any]:
        state = self.ledger(desk_id).state(at)
        return {
            "score": text(self.score(desk_id, at)),
            "return_pct": text(state.time_weighted_return_pct),
            "max_drawdown_pct": text(state.max_drawdown_pct),
            "decisions": state.decisions,
            "days_live": state.days_live,
            "equity": text(state.equity),
        }

    # ------------------------------------------------------------------ selection
    def select(self, now: Any = None) -> list[dict[str, Any]]:
        """Retire underperforming paper variants and spawn their replacements."""
        at = iso_time(now) if now is not None else self.now()
        actions: list[dict[str, Any]] = []
        modes = promoted_desks(self.log)
        min_days = int(self.config["min_days"])
        min_decisions = int(self.config["min_decisions"])
        min_variants = int(self.config["min_variants"])
        margin = Decimal(str(self.config["margin"]))

        for family, variants in sorted(self.families().items()):
            if len(variants) < min_variants:
                continue
            states = {m.id: self.ledger(m.id).state(at) for m in variants}
            mature = [m for m in variants if states[m.id].days_live >= min_days]
            if len(mature) < min_variants:
                continue
            scores = {m.id: self.score(m.id, at) for m in mature}
            median = _median(list(scores.values()))
            candidates = [
                m
                for m in mature
                if capital_mode(m, modes) == "paper"
                and states[m.id].decisions >= min_decisions
                and scores[m.id] < median - margin
            ]
            if not candidates:
                continue
            worst = min(candidates, key=lambda m: (scores[m.id], m.id))
            best = max(variants, key=lambda m: (self.score(m.id, at), m.id))
            actions.append(self.retire(worst, at, median=median, reason="below family median"))
            spawned = self.spawn(worst, best, at)
            if spawned is not None:
                actions.append(spawned)
        return actions

    def retire(
        self, manifest: DeskManifest, at: str, *, median: Decimal, reason: str
    ) -> dict[str, Any]:
        payload = {
            "desk_id": manifest.id,
            "family": manifest.family,
            "reason": reason,
            "score": {
                **self.evidence(manifest.id, at),
                "family_median": text(median),
                "margin": str(self.config["margin"]),
            },
            "as_of": at,
        }
        self.log.append(
            "evolution", "evolution.retired", payload, id=f"retired:{manifest.id}", at=at
        )
        return {"action": "retired", **payload}

    # ------------------------------------------------------------------ spawning
    def next_id(self, parent: DeskManifest) -> tuple[str, int]:
        """`(id, generation)` for the next child of `parent`: `rosenfeld` -> `rosenfeld-2`.

        An id is never reused, not even for a retired variant, so a lineage read years later is
        unambiguous. When `rosenfeld-2` already exists the generation counts on until one is free.
        """
        taken = set(self.manifests())
        generation = max(2, int(parent.generation) + 1)
        while f"{parent.id}-{generation}" in taken:
            generation += 1
        return f"{parent.id}-{generation}", generation

    def mutate(
        self, parent: DeskManifest, desk_id: str, generation: int | None = None
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Derive the child's manifest from the parent. Deterministic in the child's id."""
        generation = int(generation if generation is not None else parent.generation + 1)
        seed = _hash_int(desk_id)
        effort = EFFORTS[seed % len(EFFORTS)]
        memory_limit = MEMORY_LIMITS[(seed >> 8) % len(MEMORY_LIMITS)]
        shift = SESSION_SHIFTS[(seed >> 16) % len(SESSION_SHIFTS)]
        trait = PERSONA_TRAITS[(seed >> 24) % len(PERSONA_TRAITS)]

        data = parent.to_dict()
        data["id"] = desk_id
        data["generation"] = generation
        data["parent_id"] = parent.id
        data["family"] = parent.family
        data["name"] = f"{base_name(parent.name)} {roman(generation)}"[:60]
        persona = f"{parent.persona} {trait}".strip()
        data["persona"] = persona[:2000]
        data["model"] = {**data["model"], "reasoning_effort": effort}
        data["memory_limit"] = memory_limit
        sessions = [_shift_clock(s, shift) for s in parent.cadence.sessions]
        data["cadence"] = {**data["cadence"], "sessions": sorted(set(sessions))}
        data["capital"] = {"mode": "paper", "usd": data["capital"]["usd"]}
        data["playbook"] = f"playbooks/{desk_id}.md"
        mutation = {
            "reasoning_effort": effort,
            "memory_limit": memory_limit,
            "session_shift_minutes": shift,
            "persona_trait": trait,
        }
        return data, mutation

    def spawn(
        self, parent: DeskManifest, best_sibling: DeskManifest | None, now: Any = None
    ) -> dict[str, Any] | None:
        """Write a new manifest and playbook for a child of `parent`. Never edits the parent."""
        at = iso_time(now) if now is not None else self.now()
        family = parent.family
        if len(self.families().get(family, [])) >= int(self.config["max_variants"]):
            return None
        desk_id, generation = self.next_id(parent)
        data, mutation = self.mutate(parent, desk_id, generation)
        try:
            DeskManifest.from_dict(data)
        except ManifestError as exc:
            self.log.append(
                "ops",
                "ops.alert",
                {"level": "warning", "text": f"could not spawn {desk_id}: {exc}"},
                id=f"alert:spawn:{desk_id}",
                at=at,
            )
            return None

        playbook_path = self.playbooks_dir / f"{desk_id}.md"
        playbook = self.write_playbook(parent, best_sibling, desk_id, at)
        _atomic_write(playbook_path, playbook)
        manifest_path = self.manifests_dir / f"{desk_id}.json"
        _atomic_write(manifest_path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")
        try:
            load_manifest(manifest_path)
        except ManifestError as exc:  # pragma: no cover - guarded by the check above
            manifest_path.unlink(missing_ok=True)
            raise ManifestError(f"spawned manifest {desk_id} is invalid: {exc}") from exc

        payload = {
            "desk_id": desk_id,
            "family": family,
            "parent_id": parent.id,
            "generation": data["generation"],
            "mutation": mutation,
            "playbook": data["playbook"],
            "as_of": at,
        }
        self.log.append("evolution", "evolution.spawned", payload, id=f"spawned:{desk_id}", at=at)
        return {"action": "spawned", **payload}

    # ------------------------------------------------------------------ playbooks
    def read_playbook(self, manifest: DeskManifest) -> str:
        path = self.playbooks_dir / Path(manifest.playbook).name
        try:
            return path.read_text(encoding="utf-8")
        except OSError:
            return ""

    def postmortems(self, desk_id: str, limit: int = 6) -> list[str]:
        out: list[str] = []
        for event in self.log.read(stream=f"desk:{desk_id}", kind="desk.postmortem", limit=1000):
            body = event.payload.get("text")
            if isinstance(body, str):
                out.append(body)
        return out[-limit:]

    def write_playbook(
        self,
        parent: DeskManifest,
        best_sibling: DeskManifest | None,
        desk_id: str,
        at: str,
    ) -> str:
        """Ask the provider to rewrite the parent's playbook. Falls back to copying it."""
        parent_text = self.read_playbook(parent)
        fallback = parent_text or (
            f"# {desk_id} playbook\n\nInherited from {parent.id}. The desk may edit this file "
            "through the `playbook_write` tool.\n"
        )
        if self.provider is None:
            return fallback
        sibling_text = (
            self.read_playbook(best_sibling)
            if best_sibling is not None and best_sibling.id != parent.id
            else ""
        )
        lessons = self.postmortems(parent.id)
        instructions = (
            "You rewrite trading playbooks for a public automated trading floor. Produce the "
            f"complete markdown playbook for a new desk variant, {desk_id}, in the "
            f"{parent.family} family. Keep the parent's structure. Fold in the lessons from the "
            "post-mortems and anything the better-performing sibling does differently. Do not "
            "restate the mandate or the risk limits: those live in the manifest and are not "
            "editable. Output only the markdown."
        )
        packet = [
            f"## Parent playbook ({parent.id})\n\n{parent_text}",
            f"## Best sibling playbook ({best_sibling.id})\n\n{sibling_text}"
            if sibling_text
            else "## Best sibling playbook\n\n(none)",
            "## Parent post-mortems\n\n" + ("\n\n---\n\n".join(lessons) if lessons else "(none)"),
        ]
        try:
            response = self.provider.respond(
                self.config["playbook_profile"],
                [
                    {"role": "system", "content": instructions},
                    {"role": "user", "content": "\n\n".join(packet)},
                ],
                tools=None,
                desk_id=desk_id,
                session_id=f"spawn-{desk_id}",
                request_key=f"playbook:{desk_id}",
                reasoning_effort=self.config["playbook_reasoning_effort"],
                max_output_tokens=int(self.config["playbook_max_output_tokens"]),
                desk_cap_usd_per_day=self.config["playbook_budget_usd_per_day"],
            )
        except Exception as exc:
            self.log.append(
                "ops",
                "ops.alert",
                {
                    "level": "warning",
                    "text": f"playbook for {desk_id} copied from {parent.id}: {exc}",
                },
                id=f"alert:playbook:{desk_id}",
                at=at,
            )
            return fallback
        body = (response.output_text or "").strip()
        if not body:
            return fallback
        return body[: int(self.config["playbook_max_chars"])] + "\n"

    # ------------------------------------------------------------------ promotion
    def promote(self, now: Any = None) -> list[dict[str, Any]]:
        """Promote the best paper variant of each family whose gates pass. Live desks stay live."""
        at = iso_time(now) if now is not None else self.now()
        modes = promoted_desks(self.log)
        active = self.active()
        committee = self.committee(active)
        promoted: list[dict[str, Any]] = []
        for family, variants in sorted(self.families().items()):
            papers = [m for m in variants if capital_mode(m, modes) == "paper"]
            if not papers:
                continue
            best = max(papers, key=lambda m: (self.score(m.id, at), m.id))
            report = committee.gates(best.id, at)
            if not report["passed"]:
                continue
            payload = {
                "desk_id": best.id,
                "family": family,
                "from": "paper",
                "to": "live",
                "score": self.evidence(best.id, at),
                "gate": report["gate"],
                "evidence": report["evidence"],
                "as_of": at,
            }
            self.log.append(
                "evolution", "evolution.promoted", payload, id=f"promoted:{best.id}", at=at
            )
            promoted.append({"action": "promoted", **payload})
        return promoted


def lineage(manifests: Iterable[DeskManifest]) -> dict[str, list[str]]:
    """family -> variant ids, oldest generation first. Used by the site's lineage view."""
    grouped: dict[str, list[DeskManifest]] = {}
    for manifest in manifests:
        grouped.setdefault(manifest.family, []).append(manifest)
    return {
        family: [m.id for m in sorted(variants, key=lambda m: (m.generation, m.id))]
        for family, variants in sorted(grouped.items())
    }
