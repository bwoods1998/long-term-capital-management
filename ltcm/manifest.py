"""Desk manifests: the declarative description of one desk.

A manifest is JSON on disk under `ltcm/desks/`. It is loaded, validated and frozen at
service start. The evolution loop produces new manifests (new ids, same family, higher
generation) rather than editing existing ones. The playbook the desk edits lives at
`manifest.playbook` (a markdown file under `playbooks/`), versioned by the desk runtime.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

from .broker import ASSET_CLASSES, money

DESK_ID = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
#: The real venues a desk may name. There is no simulated venue here on purpose: a shadow
#: desk names the venue it *would* trade on, and the gateway routes it to the shadow book.
VENUES = ("alpaca", "kalshi", "coinbase", "kraken", "schwab", "tastytrade")
#: The routing key of the scoring book. Never a manifest venue.
SHADOW_VENUE = "shadow"
#: Capital modes. "paper" is read as "shadow" so manifests written before the rename load.
CAPITAL_MODES = ("shadow", "live")
LEGACY_VENUES = ("paper",)
TOOLS = (
    "quote",
    "bars",
    "news",
    "filing",
    "facts",
    "calendar",
    "chain",
    "event_markets",
    "memory_read",
    "memory_write",
    "memo",
    "propose_order",
    "cancel_order",
    "playbook_read",
    "playbook_write",
    "positions",
    "outcomes",
    # leap: lab -- a stated probability, scored at resolution; another desk's memos, read-only.
    "record_forecast",
    "memo_read",
    "run_code",  # leap: sandbox
    "weather_forecast",  # leap: weather
)
CADENCE_TRIGGERS = ("earnings_release", "filing", "market_open", "market_close", "event_resolution")
TIMEZONE = re.compile(r"^[A-Za-z_]+/[A-Za-z_]+$|^UTC$")
CLOCK = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")


class ManifestError(ValueError):
    """Invalid desk manifest."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ManifestError(message)


def _pct(value: Any, name: str, *, low: str = "0", high: str = "1") -> Decimal:
    try:
        number = money(value)
    except ValueError as exc:
        raise ManifestError(f"{name} must be a decimal string") from exc
    _require(Decimal(low) <= number <= Decimal(high), f"{name} must be within {low}..{high}")
    return number


@dataclass(frozen=True)
class InstrumentRules:
    asset_classes: tuple[str, ...]
    allow: tuple[str, ...] = ()  # symbol allowlist; empty means any symbol in the classes
    deny: tuple[str, ...] = ()
    min_price: Decimal = Decimal("5")
    min_adv_usd: Decimal = Decimal("5000000")
    allow_short: bool = False

    def permits_symbol(self, symbol: str) -> bool:
        if symbol in self.deny:
            return False
        return not self.allow or symbol in self.allow


@dataclass(frozen=True)
class Limits:
    max_position_pct: Decimal  # of desk equity, per instrument, after the trade
    max_gross_pct: Decimal  # sum of absolute position values over desk equity
    max_order_notional_pct: Decimal  # single order over desk equity
    max_daily_loss_pct: Decimal  # desk realized+unrealized loss today that halts the desk
    max_orders_per_day: int
    max_limit_deviation_pct: Decimal = Decimal("0.10")  # limit price vs reference


@dataclass(frozen=True)
class ModelSpec:
    profile: str  # provider profile name, e.g. "pro_flex"
    reasoning_effort: str = "medium"
    max_output_tokens: int = 8192
    max_turns: int = 24  # tool-calling turns per session


@dataclass(frozen=True)
class Cadence:
    sessions: tuple[str, ...]  # "HH:MM" local times
    timezone: str = "America/New_York"
    triggers: tuple[str, ...] = ()
    weekdays_only: bool = True


@dataclass(frozen=True)
class DeskManifest:
    schema_version: int
    id: str
    family: str
    generation: int
    parent_id: str | None
    name: str
    persona: str
    mandate: str
    venues: tuple[str, ...]
    instruments: InstrumentRules
    limits: Limits
    model: ModelSpec
    cadence: Cadence
    tools: tuple[str, ...]
    budget_usd_per_day: Decimal
    capital_mode: str  # "shadow" | "live"
    capital_usd: Decimal
    playbook: str  # path relative to the repository root
    memory_limit: int = 40  # memory entries carried into each session
    tags: tuple[str, ...] = field(default_factory=tuple)

    @property
    def live(self) -> bool:
        return self.capital_mode == "live"

    @property
    def shadow(self) -> bool:
        """True when this desk's orders are scored rather than sent. No money is at risk."""
        return self.capital_mode != "live"

    @property
    def market_venue(self) -> str:
        """The venue this desk trades on, or would trade on once it is promoted."""
        return self.venues[0]

    @property
    def stream(self) -> str:
        return f"desk:{self.id}"

    @property
    def ledger_stream(self) -> str:
        return f"ledger:{self.id}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "family": self.family,
            "generation": self.generation,
            "parent_id": self.parent_id,
            "name": self.name,
            "persona": self.persona,
            "mandate": self.mandate,
            "venues": list(self.venues),
            "instruments": {
                "asset_classes": list(self.instruments.asset_classes),
                "allow": list(self.instruments.allow),
                "deny": list(self.instruments.deny),
                "min_price": format(self.instruments.min_price, "f"),
                "min_adv_usd": format(self.instruments.min_adv_usd, "f"),
                "allow_short": self.instruments.allow_short,
            },
            "limits": {
                "max_position_pct": format(self.limits.max_position_pct, "f"),
                "max_gross_pct": format(self.limits.max_gross_pct, "f"),
                "max_order_notional_pct": format(self.limits.max_order_notional_pct, "f"),
                "max_daily_loss_pct": format(self.limits.max_daily_loss_pct, "f"),
                "max_orders_per_day": self.limits.max_orders_per_day,
                "max_limit_deviation_pct": format(self.limits.max_limit_deviation_pct, "f"),
            },
            "model": {
                "profile": self.model.profile,
                "reasoning_effort": self.model.reasoning_effort,
                "max_output_tokens": self.model.max_output_tokens,
                "max_turns": self.model.max_turns,
            },
            "cadence": {
                "sessions": list(self.cadence.sessions),
                "timezone": self.cadence.timezone,
                "triggers": list(self.cadence.triggers),
                "weekdays_only": self.cadence.weekdays_only,
            },
            "tools": list(self.tools),
            "budget": {"usd_per_day": format(self.budget_usd_per_day, "f")},
            "capital": {"mode": self.capital_mode, "usd": format(self.capital_usd, "f")},
            "playbook": self.playbook,
            "memory_limit": self.memory_limit,
            "tags": list(self.tags),
        }

    def public_dict(self) -> dict[str, Any]:
        """What the site shows about a desk. Identical to to_dict today; kept separate so
        private fields can be added later without leaking."""
        return self.to_dict()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DeskManifest":
        _require(isinstance(data, dict), "manifest must be an object")
        _require(data.get("schema_version") == 1, "schema_version must be 1")
        desk_id = data.get("id")
        _require(isinstance(desk_id, str) and bool(DESK_ID.match(desk_id)) and len(desk_id) <= 40,
                 "id must be lowercase letters, digits and hyphens")
        family = data.get("family")
        _require(isinstance(family, str) and bool(DESK_ID.match(family)), "family invalid")
        generation = data.get("generation")
        _require(isinstance(generation, int) and not isinstance(generation, bool) and generation >= 1,
                 "generation must be a positive integer")
        parent_id = data.get("parent_id")
        _require(parent_id is None or (isinstance(parent_id, str) and bool(DESK_ID.match(parent_id))),
                 "parent_id invalid")
        _require(generation == 1 or parent_id is not None, "generation > 1 needs a parent_id")
        for key, limit in (("name", 60), ("persona", 2000), ("mandate", 6000)):
            value = data.get(key)
            _require(isinstance(value, str) and 1 <= len(value.strip()) <= limit,
                     f"{key} must be 1-{limit} characters")
        venues = data.get("venues")
        _require(isinstance(venues, list) and venues and len(set(venues)) == len(venues),
                 "venues must be a non-empty list of known venues")
        _require(SHADOW_VENUE not in venues,
                 "venues name real venues; a shadow desk is routed by its capital mode")
        # Manifests written before the rename listed the simulator as a venue. It is not one.
        venues = [v for v in venues if v not in LEGACY_VENUES]
        _require(bool(venues) and all(v in VENUES for v in venues),
                 "venues must be a non-empty list of known venues")

        inst = data.get("instruments")
        _require(isinstance(inst, dict), "instruments must be an object")
        classes = inst.get("asset_classes")
        _require(isinstance(classes, list) and classes and all(c in ASSET_CLASSES for c in classes),
                 "instruments.asset_classes invalid")
        allow = inst.get("allow", [])
        deny = inst.get("deny", [])
        for name, symbols in (("allow", allow), ("deny", deny)):
            _require(isinstance(symbols, list) and all(isinstance(s, str) and 1 <= len(s) <= 40 for s in symbols)
                     and len(symbols) <= 2000, f"instruments.{name} invalid")
        instruments = InstrumentRules(
            asset_classes=tuple(classes),
            allow=tuple(allow),
            deny=tuple(deny),
            min_price=_pct(inst.get("min_price", "5"), "instruments.min_price", high="1000000"),
            min_adv_usd=_pct(inst.get("min_adv_usd", "5000000"), "instruments.min_adv_usd", high="1000000000000"),
            allow_short=bool(inst.get("allow_short", False)),
        )

        lim = data.get("limits")
        _require(isinstance(lim, dict), "limits must be an object")
        orders_per_day = lim.get("max_orders_per_day")
        _require(isinstance(orders_per_day, int) and not isinstance(orders_per_day, bool)
                 and 1 <= orders_per_day <= 1000, "limits.max_orders_per_day must be 1..1000")
        limits = Limits(
            max_position_pct=_pct(lim.get("max_position_pct"), "limits.max_position_pct", high="1"),
            max_gross_pct=_pct(lim.get("max_gross_pct"), "limits.max_gross_pct", high="4"),
            max_order_notional_pct=_pct(lim.get("max_order_notional_pct"), "limits.max_order_notional_pct", high="1"),
            max_daily_loss_pct=_pct(lim.get("max_daily_loss_pct"), "limits.max_daily_loss_pct", high="1"),
            max_orders_per_day=orders_per_day,
            max_limit_deviation_pct=_pct(lim.get("max_limit_deviation_pct", "0.10"), "limits.max_limit_deviation_pct", high="1"),
        )
        _require(limits.max_position_pct > 0 and limits.max_gross_pct > 0 and limits.max_order_notional_pct > 0
                 and limits.max_daily_loss_pct > 0, "limits must be positive")

        mdl = data.get("model")
        _require(isinstance(mdl, dict) and isinstance(mdl.get("profile"), str) and mdl["profile"],
                 "model.profile required")
        effort = mdl.get("reasoning_effort", "medium")
        _require(effort in ("none", "minimal", "low", "medium", "high", "xhigh", "max"), "model.reasoning_effort invalid")
        max_output = mdl.get("max_output_tokens", 8192)
        _require(isinstance(max_output, int) and 256 <= max_output <= 32768, "model.max_output_tokens must be 256..32768")
        max_turns = mdl.get("max_turns", 24)
        _require(isinstance(max_turns, int) and 1 <= max_turns <= 200, "model.max_turns must be 1..200")
        model = ModelSpec(profile=mdl["profile"], reasoning_effort=effort,
                          max_output_tokens=max_output, max_turns=max_turns)

        cad = data.get("cadence")
        _require(isinstance(cad, dict), "cadence must be an object")
        sessions = cad.get("sessions", [])
        _require(isinstance(sessions, list) and all(isinstance(s, str) and CLOCK.match(s) for s in sessions)
                 and len(sessions) <= 48, "cadence.sessions must be HH:MM strings")
        triggers = cad.get("triggers", [])
        _require(isinstance(triggers, list) and all(t in CADENCE_TRIGGERS for t in triggers), "cadence.triggers invalid")
        _require(sessions or triggers, "cadence needs sessions or triggers")
        tz = cad.get("timezone", "America/New_York")
        _require(isinstance(tz, str) and bool(TIMEZONE.match(tz)), "cadence.timezone invalid")
        cadence = Cadence(sessions=tuple(sessions), timezone=tz, triggers=tuple(triggers),
                          weekdays_only=bool(cad.get("weekdays_only", True)))

        tools = data.get("tools")
        _require(isinstance(tools, list) and tools and all(t in TOOLS for t in tools)
                 and len(set(tools)) == len(tools), "tools must be a non-empty list of known tools")

        budget = data.get("budget")
        _require(isinstance(budget, dict), "budget must be an object")
        usd_per_day = _pct(budget.get("usd_per_day"), "budget.usd_per_day", high="10000")
        _require(usd_per_day > 0, "budget.usd_per_day must be positive")

        capital = data.get("capital")
        _require(isinstance(capital, dict) and capital.get("mode") in CAPITAL_MODES + ("paper",),
                 "capital.mode must be shadow or live")
        # "paper" is the old name for the same thing and loads as "shadow".
        capital_mode = "shadow" if capital["mode"] == "paper" else capital["mode"]
        capital_usd = _pct(capital.get("usd"), "capital.usd", high="100000000")
        _require(capital_usd > 0, "capital.usd must be positive")

        playbook = data.get("playbook")
        _require(isinstance(playbook, str) and playbook.startswith("playbooks/") and playbook.endswith(".md")
                 and ".." not in playbook, "playbook must be a markdown path under playbooks/")
        memory_limit = data.get("memory_limit", 40)
        _require(isinstance(memory_limit, int) and 0 <= memory_limit <= 500, "memory_limit must be 0..500")
        tags = data.get("tags", [])
        _require(isinstance(tags, list) and all(isinstance(t, str) and 1 <= len(t) <= 30 for t in tags)
                 and len(tags) <= 20, "tags invalid")

        return cls(
            schema_version=1,
            id=desk_id,
            family=family,
            generation=generation,
            parent_id=parent_id,
            name=data["name"].strip(),
            persona=data["persona"].strip(),
            mandate=data["mandate"].strip(),
            venues=tuple(venues),
            instruments=instruments,
            limits=limits,
            model=model,
            cadence=cadence,
            tools=tuple(tools),
            budget_usd_per_day=usd_per_day,
            capital_mode=capital_mode,
            capital_usd=capital_usd,
            playbook=playbook,
            memory_limit=memory_limit,
            tags=tuple(tags),
        )


def load_manifest(path: str | Path) -> DeskManifest:
    with open(path, "r", encoding="utf-8") as handle:
        try:
            data = json.load(handle)
        except json.JSONDecodeError as exc:
            raise ManifestError(f"{path}: invalid JSON: {exc}") from exc
    try:
        return DeskManifest.from_dict(data)
    except ManifestError as exc:
        raise ManifestError(f"{path}: {exc}") from exc


def load_all(directory: str | Path) -> list[DeskManifest]:
    manifests = [load_manifest(p) for p in sorted(Path(directory).glob("*.json"))]
    ids = [m.id for m in manifests]
    if len(ids) != len(set(ids)):
        raise ManifestError("duplicate desk ids")
    return inherit_family_tools(manifests)


def inherit_family_tools(manifests: list[DeskManifest]) -> list[DeskManifest]:
    """A bred desk carries every tool its founder carries.

    Children copy their parent's tools at birth, so a tool given to the live desk afterwards
    (a forecast record, a sandbox) would never reach the variants that are supposed to be
    testing the same mandate. The union is taken at load, along the parent chain to the
    founder, and only for tools the runtime knows; nothing is ever taken away from a child.
    """
    by_id = {m.id: m for m in manifests}
    out: list[DeskManifest] = []
    for manifest in manifests:
        tools = list(manifest.tools)
        seen = {manifest.id}
        parent_id = manifest.parent_id
        while parent_id and parent_id in by_id and parent_id not in seen:
            seen.add(parent_id)
            parent = by_id[parent_id]
            if parent.family == manifest.family:
                for tool in parent.tools:
                    if tool in TOOLS and tool not in tools:
                        tools.append(tool)
            parent_id = parent.parent_id
        if tools != list(manifest.tools):
            data = manifest.to_dict()
            data["tools"] = tools
            manifest = DeskManifest.from_dict(data)
        out.append(manifest)
    return out
