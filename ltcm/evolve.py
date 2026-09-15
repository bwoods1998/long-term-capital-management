"""Variant populations: breed desks, score them forward, retire the ones that do not earn.

A *family* (`earnings`, `filings`, `kalshi`) is a mandate. A *variant* is one manifest inside that
family: same mandate, different persona, cadence, reasoning effort and memory budget, plus its own
playbook. Variants are compared only on forward results recorded in the event log; no backtest
survives contact with this module.

Three operations, all of them additive:

* `select()` retires the worst shadow variant in a family when it sits below the family median by
  a published margin, then spawns a replacement whose parent is the retired variant and whose
  playbook is rewritten from the parent's post-mortems and the best sibling's playbook.
* `promote()` moves a shadow variant to live capital, and only when `Committee.gates` pass *and*
  the venue it would trade on is enabled. A desk that has earned a sleeve on a venue the floor
  has not opened yet is deferred, in public, with the reason: the evidence is not thrown away,
  and the next run after the venue opens promotes it.
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
from .provider import PROFILES

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
#: leap: lab -- a family's house genome: the changes its experiments proved, kept beside the
#: manifests in a subdirectory so `load_all()` never mistakes one for a desk.
GENOME_DIR = "genomes"
#: The keys a directed change may carry. The lab validates values; this module applies them.
CHANGE_KEYS = (
    "model.profile",
    "model.reasoning_effort",
    "cadence.sessions",
    "memory_limit",
    "tools_add",
    "instruments.allow_add",
    "limits",
    "playbook_note",
)
MEMORY_LIMITS = (20, 40, 60, 80)
SESSION_SHIFTS = (-45, -20, 20, 45)
#: The model is part of the genome. A child may be born on a different model from its parent,
#: and `evolution.spawned` says which, so the lab report can compare a family's variants on the
#: one axis nobody can argue about: what the desk costs per decision and what it earned. Only
#: profiles the provider actually prices can be inherited -- a manifest naming an unknown profile
#: would fail its first request, not its validation.
MODEL_PROFILES = tuple(
    profile
    for profile in ("pro_flex", "kimi_flex", "glm_flex", "oss_asap", "flash_flex")
    if profile in PROFILES
)
#: One child in three changes model. Any more and a family has no control group left; any fewer
#: and the evidence takes a season to arrive.
PROFILE_MUTATION_ODDS = 3

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
    #: How many variants each family is kept at. `seed()` breeds shadow children from the live
    #: desk until a family has this many, so the forward race that promotion reads is always
    #: running. 1 means no seeding: a family is only ever the desks the owner wrote.
    "target_variants": 1,
    "margin": "2.0",  # percentage points below the family median
    "playbook_profile": "pro_flex",
    "playbook_budget_usd_per_day": "1.00",
    "playbook_reasoning_effort": "medium",
    "playbook_max_output_tokens": 6144,
    "playbook_max_chars": 12_000,
    #: Venues the floor can actually send an order to. A promotion onto anything else is deferred.
    "live_venues": (),
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


def apply_change(data: dict[str, Any], change: Mapping[str, Any] | None) -> tuple[dict[str, Any], str | None]:
    """leap: lab -- apply one directed change to a manifest dict. Returns the new dict and the
    playbook note the change carries, if any. Unknown keys are ignored: validation is the lab's
    job (`ltcm.lab.validate_change`), application is this function's, and a genome record
    written by an older lab must still apply cleanly."""
    out = json.loads(json.dumps(data))
    note: str | None = None
    if not change:
        return out, note
    if "model.profile" in change:
        out["model"] = {**out.get("model", {}), "profile": str(change["model.profile"])}
    if "model.reasoning_effort" in change:
        out["model"] = {**out.get("model", {}), "reasoning_effort": str(change["model.reasoning_effort"])}
    if "cadence.sessions" in change:
        sessions = [str(s) for s in change["cadence.sessions"]]
        out["cadence"] = {**out.get("cadence", {}), "sessions": sorted(set(sessions))}
    if "memory_limit" in change:
        out["memory_limit"] = int(change["memory_limit"])
    if "tools_add" in change:
        tools = list(out.get("tools") or [])
        for name in change["tools_add"]:
            if name not in tools:
                tools.append(str(name))
        out["tools"] = tools
    if "instruments.allow_add" in change:
        instruments = dict(out.get("instruments") or {})
        allow = list(instruments.get("allow") or [])
        for symbol in change["instruments.allow_add"]:
            if symbol not in allow:
                allow.append(str(symbol))
        instruments["allow"] = allow
        out["instruments"] = instruments
    if "limits" in change and isinstance(change["limits"], Mapping):
        limits = dict(out.get("limits") or {})
        for key, value in change["limits"].items():
            limits[str(key)] = int(value) if key == "max_orders_per_day" else str(value)
        out["limits"] = limits
    if change.get("playbook_note"):
        note = str(change["playbook_note"])
    return out, note


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

    # ------------------------------------------------------------------ seeding
    def seed(self, now: Any = None, *, limit: int | None = None) -> list[dict[str, Any]]:
        """Bring every family up to `target_variants` by breeding shadow children.

        Selection can only replace a variant that lost a race, so a family that is one desk
        wide never races at all. Seeding is what starts the race: each family with fewer active
        variants than the target gets children of its live desk (its best-scoring variant when
        no desk is live), one generation at a time, each born shadow with a rewritten playbook.
        Nothing is retired here and nothing inherits money. Idempotent once a family is full.
        `limit` bounds the children bred in one call, across families, so a caller can keep a
        pass short and come back for the rest.
        """
        at = iso_time(now) if now is not None else self.now()
        target = int(self.config["target_variants"])
        ceiling = int(self.config["max_variants"])
        if target <= 1:
            return []
        modes = promoted_desks(self.log)
        actions: list[dict[str, Any]] = []
        # Round-robin across families, one child per family per round, so a bounded pass
        # gives every family its first sibling before any family gets its third.
        while limit is None or len(actions) < limit:
            bred = False
            for family, variants in sorted(self.families().items()):
                if limit is not None and len(actions) >= limit:
                    break
                if min(target, ceiling) - len(variants) <= 0:
                    continue
                live = [m for m in variants if capital_mode(m, modes) == "live"]
                # The live desk is the parent. With none live, the best-scoring variant is, and
                # on a tie the founder rather than a child, so a young family breeds siblings,
                # not a chain of grandchildren.
                rank = lambda m: (self.score(m.id, at), -int(m.generation), m.id)  # noqa: E731
                parent = live[0] if live else max(variants, key=rank)
                best = max(variants, key=rank)
                spawned = self.spawn(parent, best, at)
                if spawned is None:
                    continue
                spawned["reason"] = "seed"
                actions.append(spawned)
                bred = True
            if not bred:
                break
        return actions

    # ------------------------------------------------------------------ selection
    def select(self, now: Any = None) -> list[dict[str, Any]]:
        """Retire underperforming shadow variants and spawn their replacements."""
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
                if capital_mode(m, modes) != "live"
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

    # leap: lab ------------------------------------------------------- genome
    def genome_path(self, family: str) -> Path:
        return self.manifests_dir / GENOME_DIR / f"{family}.json"

    def genome(self, family: str) -> list[dict[str, Any]]:
        """The changes a family's experiments proved, oldest first. Empty when none have."""
        try:
            data = json.loads(self.genome_path(family).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        changes = data.get("changes") if isinstance(data, dict) else None
        return [c for c in changes if isinstance(c, dict)] if isinstance(changes, list) else []

    def adopt_change(
        self, family: str, change: Mapping[str, Any], experiment_id: str, at: str
    ) -> dict[str, Any]:
        """Add a proven change to the family's house genome. Every future child inherits it;
        no living desk's manifest is touched."""
        records = self.genome(family)
        record = {"experiment_id": experiment_id, "change": dict(change), "adopted_at": at}
        if any(r.get("experiment_id") == experiment_id for r in records):
            return record
        records.append(record)
        _atomic_write(
            self.genome_path(family),
            json.dumps({"family": family, "changes": records}, indent=2, ensure_ascii=False) + "\n",
        )
        return record

    def mutate(
        self,
        parent: DeskManifest,
        desk_id: str,
        generation: int | None = None,
        *,
        change: Mapping[str, Any] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Derive the child's manifest from the parent. Deterministic in the child's id.

        Reasoning effort, memory budget, session times and one persona trait always move. The
        **model profile** moves for one child in three, to another priced profile that is never
        the parent's, because "which model should a desk run on" is an architectural question and
        the only honest way to answer it is to run two variants of the same mandate side by side
        and read the lab report a month later. Every mutation is recorded in `evolution.spawned`.
        """
        generation = int(generation if generation is not None else parent.generation + 1)
        seed = _hash_int(desk_id)
        effort = EFFORTS[seed % len(EFFORTS)]
        memory_limit = MEMORY_LIMITS[(seed >> 8) % len(MEMORY_LIMITS)]
        shift = SESSION_SHIFTS[(seed >> 16) % len(SESSION_SHIFTS)]
        trait = PERSONA_TRAITS[(seed >> 24) % len(PERSONA_TRAITS)]
        alternatives = [p for p in MODEL_PROFILES if p != parent.model.profile]
        profile = (
            alternatives[(seed >> 40) % len(alternatives)]
            if alternatives and (seed >> 32) % PROFILE_MUTATION_ODDS == 0
            else parent.model.profile
        )

        data = parent.to_dict()
        data["id"] = desk_id
        data["generation"] = generation
        data["parent_id"] = parent.id
        data["family"] = parent.family
        data["name"] = f"{base_name(parent.name)} {roman(generation)}"[:60]
        persona = f"{parent.persona} {trait}".strip()
        data["persona"] = persona[:2000]
        data["model"] = {**data["model"], "reasoning_effort": effort, "profile": profile}
        data["memory_limit"] = memory_limit
        sessions = [_shift_clock(s, shift) for s in parent.cadence.sessions]
        data["cadence"] = {**data["cadence"], "sessions": sorted(set(sessions))}
        # Every child is born shadow, whatever its parent earned. Nothing inherits real money.
        data["capital"] = {"mode": "shadow", "usd": data["capital"]["usd"]}
        data["playbook"] = f"playbooks/{desk_id}.md"
        mutation = {
            "reasoning_effort": effort,
            "memory_limit": memory_limit,
            "session_shift_minutes": shift,
            "persona_trait": trait,
            "model_profile": profile,
            "parent_model_profile": parent.model.profile,
            "model_changed": profile != parent.model.profile,
        }
        # leap: lab -- the house genome first, then the directed change, which is why a lab
        # experiment can override anything the random draw or an earlier adoption decided.
        notes: list[str] = []
        genome = self.genome(parent.family)
        for record in genome:
            data, note = apply_change(data, record.get("change") or {})
            if note:
                notes.append(note)
        if change:
            data, note = apply_change(data, change)
            if note:
                notes.append(note)
            mutation["change"] = dict(change)
        if genome or change:
            mutation["reasoning_effort"] = data["model"]["reasoning_effort"]
            mutation["memory_limit"] = data["memory_limit"]
            mutation["model_profile"] = data["model"]["profile"]
            mutation["model_changed"] = data["model"]["profile"] != parent.model.profile
        mutation["genome"] = [str(r.get("experiment_id")) for r in genome]
        mutation["playbook_notes"] = notes
        return data, mutation

    def spawn(
        self,
        parent: DeskManifest,
        best_sibling: DeskManifest | None,
        now: Any = None,
        *,
        change: Mapping[str, Any] | None = None,
        experiment_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Write a new manifest and playbook for a child of `parent`. Never edits the parent.

        leap: lab -- `change` is a validated directed change (see `apply_change`) and
        `experiment_id` names the lab experiment it belongs to; both are published in the
        spawn record so the lineage says why a child differs from its parent.
        """
        at = iso_time(now) if now is not None else self.now()
        family = parent.family
        if len(self.families().get(family, [])) >= int(self.config["max_variants"]):
            return None
        desk_id, generation = self.next_id(parent)
        data, mutation = self.mutate(parent, desk_id, generation, change=change)
        notes = mutation.pop("playbook_notes", [])
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
        if notes:  # leap: lab -- the house view, appended verbatim below the rewritten playbook
            playbook = playbook.rstrip("\n") + "\n\n## House view\n\n" + "\n\n".join(
                f"- {note}" for note in notes
            ) + "\n"
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
        if experiment_id:  # leap: lab
            payload["experiment_id"] = experiment_id
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
    def live_venues(self) -> set[str]:
        """The venues the floor can send a real order to today."""
        configured = self.config.get("live_venues") or ()
        return {str(v) for v in configured}

    def promote(self, now: Any = None) -> list[dict[str, Any]]:
        """Promote the best shadow variant of each family whose gates pass.

        Two conditions, both published. The gate is the evidence: days live, decisions, a
        cost-adjusted excess return, drawdown inside mandate, no breakers, clean reconciliations.
        The second is plumbing: the venue the desk would trade on has to be enabled. A desk that
        passes the gate onto a venue the floor has not opened is **deferred**, not failed -- a
        `committee.gate` says "venue not enabled" in public, and the next run after the venue
        opens promotes it on the same evidence. Live desks stay live.
        """
        at = iso_time(now) if now is not None else self.now()
        modes = promoted_desks(self.log)
        active = self.active()
        committee = self.committee(active)
        enabled = self.live_venues()
        promoted: list[dict[str, Any]] = []
        for family, variants in sorted(self.families().items()):
            candidates = [m for m in variants if capital_mode(m, modes) != "live"]
            if not candidates:
                continue
            best = max(candidates, key=lambda m: (self.score(m.id, at), m.id))
            report = committee.gates(best.id, at)
            if not report["passed"]:
                continue
            venue = best.market_venue
            if venue not in enabled:
                self.defer(best, venue, report, at)
                continue
            payload = {
                "desk_id": best.id,
                "family": family,
                "from": "shadow",
                "to": "live",
                "venue": venue,
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

    def defer(
        self, manifest: DeskManifest, venue: str, report: Mapping[str, Any], at: str
    ) -> dict[str, Any]:
        """Say in public that a desk earned a sleeve the floor cannot open yet."""
        payload = {
            "desk_id": manifest.id,
            "gate": report["gate"],
            "passed": False,
            "reason": "venue not enabled",
            "evidence": {
                **dict(report.get("evidence") or {}),
                "venue": venue,
                "venue_enabled": False,
                "gate_evidence_passed": True,
            },
            "failed": ["venue"],
            "as_of": at,
        }
        self.log.append(
            "committee",
            "committee.gate",
            payload,
            id=f"gate:{manifest.id}:{at}:venue",
            at=at,
        )
        return {"action": "deferred", **payload}


def lineage(manifests: Iterable[DeskManifest]) -> dict[str, list[str]]:
    """family -> variant ids, oldest generation first. Used by the site's lineage view."""
    grouped: dict[str, list[DeskManifest]] = {}
    for manifest in manifests:
        grouped.setdefault(manifest.family, []).append(manifest)
    return {
        family: [m.id for m in sorted(variants, key=lambda m: (m.generation, m.id))]
        for family, variants in sorted(grouped.items())
    }
