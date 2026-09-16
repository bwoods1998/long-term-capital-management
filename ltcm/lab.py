"""The lab: directed experiments on the floor's own architecture.

Evolution breeds by chance -- a shifted session, a persona trait, one child in three on another
model -- and selection reads the results. The lab is the deliberate half of the same loop. Once
a night, for each family with a live desk, it asks a model to read the evidence the floor has
written about itself (the results ledger, the last lab reports, the family's calibration and
its recent post-mortems) and to propose at most two *experiments*: a hypothesis in a sentence and
a change drawn from a fixed vocabulary (§3 of the floor contract): a model, an effort, a set of
session times, a memory budget, a tool, a symbol, a risk limit inside hard bounds, or a note for
the playbook. Nothing outside that vocabulary can be proposed, and every proposal is validated
against the hard limits in the floor's config before anything else happens.

A valid proposal is published as a `lab.experiment` and bred at once as a directed shadow
variant of the live desk, with the change applied. It trades a shadow book against real prices
like any variant. When it has had its days and its decisions, the verdict compares its gate
evidence with its parent's and is published as a `lab.verdict`: **adopted** means the change
joins the family's house genome, which every future child inherits (the live desk itself is
never edited -- promotion through the committee's gates is the only way a live sleeve changes
hands); **rejected** retires the variant. Invalid proposals are published as withdrawn, with
the reason, because a proposal the model made and the floor refused is evidence too.

Every model call goes through the provider with a deterministic request key, so a retried night
pays once. Standard library only.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Mapping

from .committee import capital_mode, promoted_desks
from .events import EventLog, canonical, now_iso
from .evolve import CHANGE_KEYS, EFFORTS, MODEL_PROFILES, Evolution
from .ledger import iso_time, parse_iso
from .manifest import CLOCK, TOOLS, DeskManifest

EXPERIMENT_KIND = "lab.experiment"
VERDICT_KIND = "lab.verdict"
STATUSES = ("proposed", "running", "adopted", "rejected", "withdrawn")
MAX_HYPOTHESIS = 600
SYMBOL = re.compile(r"^[A-Z0-9][A-Z0-9._:\-]{0,39}$")

DEFAULT_CONFIG: dict[str, Any] = {
    "profile": "pro_asap",
    "reasoning_effort": "high",
    "max_output_tokens": 6144,
    "budget_usd_per_day": "5.00",
    # How much the lab may propose: per family per night, per floor per day, and how many of a
    # family's experiments may run at once.
    "max_experiments_per_family": 2,
    "max_experiments_per_day": 4,
    "max_running_per_family": 2,
    # Days a variant runs before its verdict; None means the evolution loop's `min_days`. After
    # `grace_days` more, a variant that still lacks the decisions is rejected as unproven.
    "evaluate_days": None,
    "grace_days": 7,
    # leap: lab -- strategy changes: code size and cadence bounds, and how much house source the packet shows.
    "strategy_code_chars": 6000,
    "strategy_cadence_seconds": (300, 86400),
    "strategy_source_chars": 9000,
    # The bounds a proposed limit must stay inside. Anything outside is withdrawn, not clamped.
    "hard_limits": {
        "max_position_pct": ["0.01", "0.50"],
        "max_order_notional_pct": ["0.01", "0.50"],
        "max_daily_loss_pct": ["0.01", "0.15"],
        "max_orders_per_day": [1, 40],
    },
    "allowed_profiles": list(MODEL_PROFILES),
    "allowed_efforts": list(EFFORTS),
    "memory_limits": [20, 120],
    "max_sessions": 8,
    "playbook_note_chars": 1500,
    "window_days": 7,
}


STRATEGY_NAME = re.compile(r"^[a-z][a-z0-9_]{0,39}$")

#: What a strategy may call. Shown to the lab so the code it writes runs first time.
KIT_API = (
    "kit.context (dict: now, desk_id, live, learning_usd, positions[{symbol, market_id, right, asset_class, quantity, average_cost}], "
    "open_orders[{order_id, symbol, market_id, right, side, quantity, limit_price, submitted_at, strategy}], venues); "
    "kit.say(text); kit.bars(symbol, interval='1h', limit=60, asset_class='crypto', venue='coinbase') -> [{time, open, high, low, close, volume}]; "
    "kit.quote(symbol, asset_class='crypto', venue='coinbase') -> {bid, ask, last}; kit.products(limit=25) -> [{symbol, price, volume_usd}] (Coinbase USD spot by 24h volume); "
    "kit.kalshi_series(series, limit=1000) -> open markets [{ticker, yes_bid, yes_ask, no_bid, no_ask, close_time, floor_strike, cap_strike, title, ...}]; "
    "kit.kalshi_market(ticker) -> one market (strike_type greater|less|between, floor_strike, cap_strike); kit.kalshi_markets(max_close_hours=36, pages=5) -> every open single Kalshi market settling within the window, all categories; kit.futures(root=None) -> Coinbase futures [{symbol, root, expiry, price, volume_usd}] nearest expiry first (check the contract your market settles on: basis matters); "
    "kit.weather(city) -> {forecast..., hourly..., observation}; kit.weather_cities() -> [names] (20 Kalshi cities). "
    "decide(kit, params) returns a list of intents, or {'intents': [...], 'cancels': [order_id...], 'notes': str}. An intent: "
    "{'instrument': {'asset_class': 'event'|'crypto', 'symbol': ..., 'market_id': ticker (event), 'right': 'yes'|'no' (event)}, 'side': 'buy'|'sell', "
    "'quantity': str, 'order_type': 'limit', 'limit_price': str, 'rationale': str (name the setup, the edge and the exit), 'holding_period_hours': int, "
    "optional 'post_only': true, 'target_price', 'stop_price'}. Sizes are capped by the floor; the risk engine and the critic check every order."
)


class LabError(ValueError):
    """A proposal the floor refuses. The message is published as the reason."""


def _money(value: Any) -> Decimal:
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        raise LabError(f"{value!r} is not a number") from None
    if not number.is_finite():
        raise LabError(f"{value!r} is not a number")
    return number


# --------------------------------------------------------------------------- the vocabulary


def validate_change(
    change: Any, parent: DeskManifest, config: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """The proposal's change, normalized, or `LabError` saying exactly what was wrong.

    A change must say something the parent does not already do: a proposal to run on the
    parent's own model is not an experiment. Limits must sit inside the hard bounds -- they
    are refused, never clamped, so the record shows what the model asked for.
    """
    cfg = {**DEFAULT_CONFIG, **dict(config or {})}
    if not isinstance(change, Mapping) or not change:
        raise LabError("change must be a non-empty object")
    unknown = sorted(str(k) for k in change if k not in CHANGE_KEYS)
    if unknown:
        raise LabError(f"unknown change keys: {', '.join(unknown)}")
    out: dict[str, Any] = {}

    if "model.profile" in change:
        profile = str(change["model.profile"])
        if profile not in cfg["allowed_profiles"]:
            raise LabError(f"model.profile {profile!r} is not a priced profile")
        if profile == parent.model.profile:
            raise LabError("model.profile is the parent's own model")
        out["model.profile"] = profile

    if "model.reasoning_effort" in change:
        effort = str(change["model.reasoning_effort"])
        if effort not in cfg["allowed_efforts"]:
            raise LabError(f"model.reasoning_effort {effort!r} is not allowed")
        if effort == parent.model.reasoning_effort:
            raise LabError("model.reasoning_effort is the parent's own")
        out["model.reasoning_effort"] = effort

    if "cadence.sessions" in change:
        raw = change["cadence.sessions"]
        if not isinstance(raw, list) or not raw or len(raw) > int(cfg["max_sessions"]):
            raise LabError(f"cadence.sessions must list 1 to {cfg['max_sessions']} times")
        sessions = sorted({str(s) for s in raw})
        bad = [s for s in sessions if not CLOCK.match(s)]
        if bad:
            raise LabError(f"cadence.sessions has malformed times: {', '.join(bad)}")
        if sessions == sorted(set(parent.cadence.sessions)):
            raise LabError("cadence.sessions is the parent's own schedule")
        out["cadence.sessions"] = sessions

    if "memory_limit" in change:
        value = change["memory_limit"]
        low, high = (int(v) for v in cfg["memory_limits"])
        if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
            raise LabError(f"memory_limit must be an integer between {low} and {high}")
        if value == parent.memory_limit:
            raise LabError("memory_limit is the parent's own")
        out["memory_limit"] = value

    if "tools_add" in change:
        raw = change["tools_add"]
        if not isinstance(raw, list) or not raw:
            raise LabError("tools_add must be a non-empty list")
        names = sorted({str(t) for t in raw})
        bad = [t for t in names if t not in TOOLS]
        if bad:
            raise LabError(f"tools_add names unknown tools: {', '.join(bad)}")
        new = [t for t in names if t not in parent.tools]
        if not new:
            raise LabError("tools_add adds nothing the parent lacks")
        out["tools_add"] = new

    if "instruments.allow_add" in change:
        raw = change["instruments.allow_add"]
        if not isinstance(raw, list) or not raw:
            raise LabError("instruments.allow_add must be a non-empty list")
        if not parent.instruments.allow:
            raise LabError("the parent already allows every symbol in its classes")
        symbols = sorted({str(s).strip().upper() for s in raw})
        bad = [s for s in symbols if not SYMBOL.match(s)]
        if bad:
            raise LabError(f"instruments.allow_add has malformed symbols: {', '.join(bad)}")
        new = [s for s in symbols if s not in parent.instruments.allow]
        if not new:
            raise LabError("instruments.allow_add adds nothing the parent lacks")
        out["instruments.allow_add"] = new

    if "limits" in change:
        raw = change["limits"]
        hard = cfg["hard_limits"]
        if not isinstance(raw, Mapping) or not raw:
            raise LabError("limits must be a non-empty object")
        unknown = sorted(str(k) for k in raw if k not in hard)
        if unknown:
            raise LabError(f"limits outside the vocabulary: {', '.join(unknown)}")
        limits: dict[str, Any] = {}
        current = parent.limits
        for key, value in raw.items():
            low, high = hard[key]
            if key == "max_orders_per_day":
                if isinstance(value, bool) or not isinstance(value, int):
                    raise LabError("limits.max_orders_per_day must be an integer")
                if not int(low) <= value <= int(high):
                    raise LabError(f"limits.max_orders_per_day must be between {low} and {high}")
                if value == current.max_orders_per_day:
                    raise LabError("limits.max_orders_per_day is the parent's own")
                limits[key] = value
                continue
            number = _money(value)
            if not _money(low) <= number <= _money(high):
                raise LabError(f"limits.{key} must be between {low} and {high}")
            if number == getattr(current, key):
                raise LabError(f"limits.{key} is the parent's own")
            limits[key] = format(number, "f")
        out["limits"] = limits

    if "playbook_note" in change:
        note = change["playbook_note"]
        limit = int(cfg["playbook_note_chars"])
        if not isinstance(note, str) or not note.strip() or len(note) > limit:
            raise LabError(f"playbook_note must be 1 to {limit} characters")
        if "<" in note:
            raise LabError("playbook_note may not contain markup")
        out["playbook_note"] = note.strip()

    if "strategy" in change:  # leap: lab -- code the child trades with, judged like any change
        spec = change["strategy"]
        if not isinstance(spec, Mapping):
            raise LabError("strategy must be an object with name, cadence_seconds, params and code")
        name = str(spec.get("name") or "")
        if not STRATEGY_NAME.match(name):
            raise LabError("strategy.name is lowercase letters, digits and underscores, 40 at most")
        code = spec.get("code")
        limit = int(cfg["strategy_code_chars"])
        if not isinstance(code, str) or "def decide(" not in code:
            raise LabError("strategy.code must be Python that defines decide(kit, params)")
        if len(code) > limit:
            raise LabError(f"strategy.code must be at most {limit} characters")
        for banned in ("subprocess", "os.system", "socket", "urllib", "requests", "open(", "__import__"):
            if banned in code:
                raise LabError(f"strategy.code may not use {banned}: the kit is the only door to data")
        try:
            cadence = int(spec.get("cadence_seconds", 600))
        except (TypeError, ValueError):
            raise LabError("strategy.cadence_seconds must be an integer") from None
        low, high = (int(x) for x in cfg["strategy_cadence_seconds"])
        if not low <= cadence <= high:
            raise LabError(f"strategy.cadence_seconds must be between {low} and {high}")
        params = spec.get("params") or {}
        if not isinstance(params, Mapping) or len(params) > 24:
            raise LabError("strategy.params must be an object of at most 24 plain values")
        for key, value in params.items():
            if not isinstance(key, str) or not isinstance(value, (str, int, float, bool, list)):
                raise LabError(f"strategy.params.{key} must be a string, number, boolean or list")
        out["strategy"] = {"name": name, "cadence_seconds": cadence, "params": json.loads(json.dumps(dict(params))), "code": code}

    if not out:
        raise LabError("change must name at least one field")
    return out


def experiment_id(family: str, hypothesis: str, change: Mapping[str, Any], day: str) -> str:
    material = canonical({"family": family, "hypothesis": hypothesis, "change": change, "day": day})
    return "exp-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:12]


def parse_proposals(body: str) -> list[dict[str, Any]]:
    """The experiments in a model reply: the first JSON object in the text, `experiments` key.

    Tolerates prose around the object and a fenced code block; refuses anything that is not a
    list of objects with a hypothesis and a change.
    """
    text = str(body or "")
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return []
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return []
    rows = data.get("experiments") if isinstance(data, dict) else data
    if not isinstance(rows, list):
        return []
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        hypothesis = row.get("hypothesis")
        if not isinstance(hypothesis, str) or not hypothesis.strip():
            continue
        out.append({"hypothesis": hypothesis.strip()[:MAX_HYPOTHESIS], "change": row.get("change")})
    return out


# --------------------------------------------------------------------------- the lab


class Lab:
    """Propose, breed, judge and adopt. Reads the log; writes `lab.*` and breeds through
    `Evolution`; never edits a manifest that is trading."""

    def __init__(
        self,
        log: EventLog,
        evolution: Evolution,
        *,
        provider: Any = None,
        clock: Callable[[], float] = time.time,
        config: Mapping[str, Any] | None = None,
        results: Callable[[], Any] | None = None,
        calibration: Any = None,
        strategies: Any = None,
    ):
        self.log = log
        self.evolution = evolution
        self.provider = provider
        self.clock = clock
        self.config = {**DEFAULT_CONFIG, **dict(config or {})}
        self.results = results
        self.calibration = calibration
        self.strategies = strategies  # leap: lab -- the runner, for the family's records and sources
        #: The Firm Mind (`ltcm/mind.py`), set by the service: the family's rules ride the packet.
        self.mind: Any = None
        #: Work the night has asked for but not yet done, so a tick can do one unit at a time:
        #: (family, parent, best sibling, proposal). Families already asked today, by day.
        self._queue: list[tuple[str, DeskManifest, DeskManifest, dict[str, Any]]] = []
        self._asked: dict[str, set[str]] = {}

    def now(self) -> str:
        return now_iso(self.clock)

    # ------------------------------------------------------------------ the record
    def experiments(self) -> dict[str, dict[str, Any]]:
        """Every experiment the log knows, with its latest status. Verdicts are final."""
        out: dict[str, dict[str, Any]] = {}
        for event in self.log.read(kind=EXPERIMENT_KIND, limit=10_000, newest=True):
            p = event.payload
            exp_id = p.get("experiment_id")
            if not isinstance(exp_id, str):
                continue
            current = out.get(exp_id, {})
            out[exp_id] = {**current, **dict(p), "at": event.at}
        for event in self.log.read(kind=VERDICT_KIND, limit=10_000, newest=True):
            p = event.payload
            exp_id = p.get("experiment_id")
            if isinstance(exp_id, str) and exp_id in out:
                out[exp_id].update(
                    {"status": p.get("status"), "verdict_reason": p.get("reason"), "verdict_at": event.at}
                )
        return out

    def running(self, family: str | None = None) -> list[dict[str, Any]]:
        rows = [e for e in self.experiments().values() if e.get("status") == "running"]
        if family is not None:
            rows = [e for e in rows if e.get("family") == family]
        return sorted(rows, key=lambda e: str(e.get("proposed_at")))

    def proposed_on(self, day: str) -> int:
        return sum(1 for e in self.experiments().values() if str(e.get("proposed_at", ""))[:10] == day)

    def recent(self, limit: int = 12) -> list[dict[str, Any]]:
        """The newest experiments first, in the contract's checkpoint shape."""
        rows = sorted(self.experiments().values(), key=lambda e: str(e.get("proposed_at")), reverse=True)
        out = []
        for row in rows[: max(0, int(limit))]:
            entry = {
                key: row.get(key)
                for key in (
                    "experiment_id", "hypothesis", "family", "parent_id", "change",
                    "variant_desk_id", "status", "proposed_at", "evaluate_after",
                )
            }
            if row.get("verdict_reason") or row.get("reason"):
                entry["verdict_reason"] = row.get("verdict_reason") or row.get("reason")
            out.append(entry)
        return out

    # ------------------------------------------------------------------ proposing
    def run(self, now: Any = None, *, max_work: int | None = None) -> list[dict[str, Any]]:
        """One night's work: judge what is due, then propose what is new.

        `max_work` bounds the model calls made in this call (an ask of one family, or one
        spawn with its playbook rewrite, is one unit) so the floor's tick can spread a night's
        lab over consecutive ticks instead of blocking for the whole of it; `pending()` says
        whether more remains.
        """
        at = iso_time(now) if now is not None else self.now()
        return self.evaluate(at) + self.propose(at, max_work=max_work)

    def pending(self, at: str) -> bool:
        """True while tonight's lab still has an ask or a spawn to do. `at` is the instant the
        caller is working at; the night is keyed by its UTC date, the same key `propose` uses."""
        if self._queue:
            return True
        asked = self._asked.get(iso_time(parse_iso(at))[:10] if "T" in at else at, set())
        modes = promoted_desks(self.log)
        for family, variants in self.evolution.families().items():
            if family in asked:
                continue
            if any(capital_mode(m, modes) == "live" for m in variants):
                return True
        return False

    def propose(self, now: Any = None, *, max_work: int | None = None) -> list[dict[str, Any]]:
        at = iso_time(now) if now is not None else self.now()
        day = at[:10]
        actions: list[dict[str, Any]] = []
        modes = promoted_desks(self.log)
        per_family = int(self.config["max_experiments_per_family"])
        per_day = int(self.config["max_experiments_per_day"])
        max_running = int(self.config["max_running_per_family"])
        asked = self._asked.setdefault(day, set())
        work = 0

        def budget_left() -> bool:
            return max_work is None or work < max_work

        # Spawns already asked for come first: a proposal is paid for once and never dropped.
        while self._queue and budget_left():
            family, parent, best, proposal = self._queue.pop(0)
            work += 1
            actions.extend(self._process(family, parent, best, proposal, at, day, per_day, max_running))

        for family, variants in sorted(self.evolution.families().items()):
            if not budget_left():
                break
            if family in asked:
                continue
            live = [m for m in variants if capital_mode(m, modes) == "live"]
            if not live:
                asked.add(family)
                continue
            if self.proposed_on(day) >= per_day:
                break
            if len(self.running(family)) >= max_running:
                asked.add(family)
                continue
            parent = live[0]
            best = max(variants, key=lambda m: (self.evolution.score(m.id, at), -int(m.generation), m.id))
            asked.add(family)
            work += 1
            proposals = self._ask(family, parent, at)[:per_family]
            if max_work is None:
                for proposal in proposals:
                    actions.extend(self._process(family, parent, best, proposal, at, day, per_day, max_running))
            else:
                self._queue.extend((family, parent, best, proposal) for proposal in proposals)
        return actions

    def _process(
        self,
        family: str,
        parent: DeskManifest,
        best: DeskManifest,
        proposal: Mapping[str, Any],
        at: str,
        day: str,
        per_day: int,
        max_running: int,
    ) -> list[dict[str, Any]]:
        """Validate, publish and breed one proposal. The caps are checked again here because
        a queued proposal may have waited a tick while another family filled them."""
        actions: list[dict[str, Any]] = []
        if self.proposed_on(day) >= per_day or len(self.running(family)) >= max_running:
            return actions
        hypothesis = proposal["hypothesis"]
        raw_change = proposal.get("change")
        exp_id = experiment_id(family, hypothesis, raw_change if isinstance(raw_change, dict) else {}, day)
        if exp_id in self.experiments():
            return actions
        try:
            change = validate_change(raw_change, parent, self.config)
        except LabError as exc:
            actions.append(
                self._publish(exp_id, family, parent, hypothesis, raw_change, "withdrawn", at, reason=str(exc))
            )
            return actions
        self._publish(exp_id, family, parent, hypothesis, change, "proposed", at)
        spawned = self.evolution.spawn(parent, best, at, change=change, experiment_id=exp_id)
        if spawned is None:
            actions.append(
                self._publish(
                    exp_id, family, parent, hypothesis, change, "withdrawn", at,
                    reason="the family is at its variant ceiling",
                )
            )
            return actions
        actions.append(
            self._publish(
                exp_id, family, parent, hypothesis, change, "running", at,
                variant_desk_id=spawned["desk_id"],
            )
        )
        return actions

    def _publish(
        self,
        exp_id: str,
        family: str,
        parent: DeskManifest,
        hypothesis: str,
        change: Any,
        status: str,
        at: str,
        *,
        variant_desk_id: str | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        known = self.experiments().get(exp_id, {})
        proposed_at = known.get("proposed_at") or at
        payload: dict[str, Any] = {
            "experiment_id": exp_id,
            "hypothesis": hypothesis,
            "family": family,
            "parent_id": parent.id,
            "change": change if isinstance(change, dict) else {},
            "variant_desk_id": variant_desk_id or known.get("variant_desk_id"),
            "status": status,
            "proposed_at": proposed_at,
            "evaluate_after": self._evaluate_after(proposed_at),
        }
        if reason:
            payload["reason"] = reason[:600]
        self.log.append("lab", EXPERIMENT_KIND, payload, id=f"{exp_id}:{status}", at=at)
        return {"action": "experiment", **payload}

    def _evaluate_after(self, proposed_at: str) -> str:
        days = self.config.get("evaluate_days")
        if days is None:
            days = self.evolution.config.get("min_days", 21)
        from datetime import timedelta

        return iso_time(parse_iso(proposed_at) + timedelta(days=int(days)))

    def _ask(self, family: str, parent: DeskManifest, at: str) -> list[dict[str, Any]]:
        if self.provider is None:
            return []
        try:
            response = self.provider.respond(
                self.config["profile"],
                [
                    {"role": "system", "content": self.instructions()},
                    {"role": "user", "content": self.packet(family, parent, at)},
                ],
                tools=None,
                desk_id="lab",
                session_id=f"lab-{at[:10]}",
                request_key=f"lab:{family}:{at[:10]}",
                reasoning_effort=self.config["reasoning_effort"],
                max_output_tokens=int(self.config["max_output_tokens"]),
                desk_cap_usd_per_day=self.config["budget_usd_per_day"],
            )
        except Exception as exc:
            self.log.append(
                "ops",
                "ops.alert",
                {"level": "warning", "text": f"lab proposals for {family} not written: {exc}"},
                id=f"alert:lab:{family}:{at[:10]}",
                at=at,
            )
            return []
        return parse_proposals(getattr(response, "output_text", "") or "")

    def instructions(self) -> str:
        hard = self.config["hard_limits"]
        return (
            "You run the research lab of a public, fully automated trading floor. Each night you "
            "read the evidence the floor wrote about itself and propose at most two experiments "
            "for one family of desks. An experiment is a hypothesis in one sentence and a change "
            "from a fixed vocabulary. The change is applied to a new shadow variant of the live "
            "desk, which trades a hypothetical book against real prices; if its record beats its "
            "parent's, the change is adopted for every future child of the family.\n"
            "Reply with JSON only, in this shape: {\"experiments\": [{\"hypothesis\": \"...\", "
            "\"change\": {...}}]}. The change object may use only these keys:\n"
            f"- \"model.profile\": one of {', '.join(self.config['allowed_profiles'])}\n"
            f"- \"model.reasoning_effort\": one of {', '.join(self.config['allowed_efforts'])}\n"
            f"- \"cadence.sessions\": a list of 1 to {self.config['max_sessions']} HH:MM local times\n"
            f"- \"memory_limit\": an integer from {self.config['memory_limits'][0]} to {self.config['memory_limits'][1]}\n"
            f"- \"tools_add\": tool names from {', '.join(TOOLS)}\n"
            "- \"instruments.allow_add\": symbols or contract series on the desk's own venue\n"
            "- \"limits\": an object with any of "
            + ", ".join(f"{k} ({v[0]} to {v[1]})" for k, v in hard.items())
            + "\n"
            f"- \"playbook_note\": a house-view note of at most {self.config['playbook_note_chars']} characters\n"
            "- \"strategy\": {\"name\", \"cadence_seconds\", \"params\", \"code\"}: a Python module the variant runs "
            f"between sessions every cadence_seconds (code at most {self.config['strategy_code_chars']} characters). Use it to "
            "change how the family trades, not just how it is configured: a sharper pricing model, a new market, a "
            "different exit. It may reuse a house strategy's name to replace it on the variant. The kit it gets: "
            f"{KIT_API}\n"
            "A change must differ from the parent's current setting. Prefer one variable per "
            "experiment, so the verdict means something. Never propose anything outside the "
            "vocabulary: it is refused, and the refusal is published. Propose nothing when the "
            "evidence does not support a hypothesis: reply {\"experiments\": []}."
        )

    def packet(self, family: str, parent: DeskManifest, at: str) -> str:
        """Everything the model is allowed to know: numbers the floor wrote, nothing else."""
        parts = [f"# Family {family}, live desk {parent.name} ({parent.id}), now {at} UTC"]
        parts.append(
            "## The live desk today\n"
            f"- model: {parent.model.profile}, effort {parent.model.reasoning_effort}, "
            f"{parent.model.max_turns} turns, memory {parent.memory_limit}\n"
            f"- sessions: {', '.join(parent.cadence.sessions)} {parent.cadence.timezone}\n"
            f"- tools: {', '.join(parent.tools)}\n"
            f"- allowed symbols: {', '.join(parent.instruments.allow) or '(any in its classes)'}\n"
            f"- limits: position {parent.limits.max_position_pct}, order {parent.limits.max_order_notional_pct}, "
            f"daily loss {parent.limits.max_daily_loss_pct}, {parent.limits.max_orders_per_day} orders a day\n"
            f"- mandate: {parent.mandate[:600]}"
        )
        siblings = [m for m in self.evolution.families().get(family, []) if m.id != parent.id]
        if siblings:
            lines = []
            for m in siblings:
                lines.append(
                    f"- {m.id}: generation {m.generation}, {m.model.profile}/{m.model.reasoning_effort}, "
                    f"score {self.evolution.score(m.id, at)}"
                )
            parts.append("## Variants already running\n" + "\n".join(lines))
        genome = self.evolution.genome(family)
        if genome:
            parts.append(
                "## House genome (adopted changes)\n"
                + "\n".join(f"- {r.get('experiment_id')}: {json.dumps(r.get('change'), sort_keys=True)}" for r in genome)
            )
        parts.append("## Results, last " + str(self.config["window_days"]) + " days\n" + self._results_block(family, at))
        strategies = self._strategies_block(family, parent, siblings)
        if strategies:
            parts.append(strategies)
        learned = self.mind.block_for(family) if self.mind is not None else ""
        if learned:
            parts.append("## What the firm has learned\n" + learned)
        parts.append("## Last lab reports\n" + self._reports_block())
        if self.calibration is not None:
            try:
                brief = self.calibration.brief(parent.id, at)
            except Exception:
                brief = ""
            if brief:
                parts.append("## Calibration\n" + brief)
        postmortems = self.evolution.postmortems(parent.id, 3)
        if postmortems:
            parts.append("## Recent post-mortems\n" + "\n\n---\n\n".join(p[:1500] for p in postmortems))
        past = [
            e for e in self.experiments().values()
            if e.get("family") == family and e.get("status") in ("adopted", "rejected", "withdrawn")
        ]
        if past:
            lines = [
                f"- {e['experiment_id']} {e['status']}: {str(e.get('hypothesis'))[:160]}"
                + (f" ({e.get('verdict_reason') or e.get('reason')})" if e.get("verdict_reason") or e.get("reason") else "")
                for e in sorted(past, key=lambda e: str(e.get("proposed_at")))[-8:]
            ]
            parts.append("## Earlier experiments\n" + "\n".join(lines))
        return "\n\n".join(parts)

    def _strategies_block(self, family: str, parent: DeskManifest, siblings: list[DeskManifest]) -> str:
        """leap: lab -- what the family's strategies did, and the source of its house strategy,
        so a proposed strategy change starts from the code that runs today."""
        runner = self.strategies
        if runner is None:
            return ""
        lines = []
        for m in [parent, *siblings]:
            try:
                rows = runner.report(m).get("strategies") or []
            except Exception:
                rows = []
            for row in rows:
                lines.append(
                    f"- {m.id}/{row.get('name')}: params {json.dumps(row.get('params') or {}, sort_keys=True)}, "
                    f"{row.get('runs') or 0} runs, {row.get('intents') or 0} intents, {row.get('approved') or 0} approved, "
                    f"{row.get('fills') or 0} fills, {row.get('settled') or 0} settled, {row.get('wins') or 0} won, "
                    f"P&L {row.get('settled_pnl_usd') or '0'}" + (f", last error {str(row.get('last_error'))[:80]}" if row.get("last_error") else "")
                )
        parts = []
        if lines:
            parts.append("## Strategies running in the family\n" + "\n".join(lines))
        try:
            sources = runner.house_sources(family)
        except Exception:
            sources = {}
        budget = int(self.config["strategy_source_chars"])
        for name, code in list(sources.items())[:2]:
            clipped = code[:budget]
            parts.append(f"## House strategy `{name}` (source, {len(code)} chars{', clipped' if len(code) > budget else ''})\n```python\n{clipped}\n```")
        return "\n\n".join(parts)

    def _results_block(self, family: str, at: str) -> str:
        if self.results is None:
            return "(no results ledger)"
        try:
            ledger = self.results()
            report = ledger.report(int(self.config["window_days"]), at)
        except Exception:
            return "(results unavailable)"
        rows = []
        for desk_id, row in sorted(report.get("desks", {}).items()):
            if row.get("family") != family:
                continue
            rows.append(
                f"- {desk_id} ({row.get('mode')}, {row.get('profile')}): {row.get('decisions')} decisions, "
                f"{row.get('closed_trades')} closed, win rate {row.get('win_rate')}, "
                f"net {row.get('net_pnl_usd')} after {row.get('sail_cost_usd')} inference, "
                f"drawdown {row.get('max_drawdown_pct')}, Brier {row.get('brier')}"
            )
        fam = report.get("families", {}).get(family)
        if fam:
            rows.append(
                f"- family: {fam.get('decisions')} decisions, net {fam.get('net_pnl_usd')}, "
                f"P&L per inference dollar {fam.get('pnl_per_inference_dollar')}"
            )
        return "\n".join(rows) if rows else "(no activity in the window)"

    def _reports_block(self) -> str:
        events = self.log.read(kind="lab.result", limit=10_000, newest=True)[-3:]
        if not events:
            return "(none yet)"
        return "\n".join(f"- {e.at[:10]}: {str(e.payload.get('verdict'))[:400]}" for e in events)

    # ------------------------------------------------------------------ judging
    def evaluate(self, now: Any = None) -> list[dict[str, Any]]:
        at = iso_time(now) if now is not None else self.now()
        actions: list[dict[str, Any]] = []
        active = self.evolution.active()
        committee = self.evolution.committee(active)
        min_decisions = int(self.evolution.config.get("min_decisions", 20))
        grace = int(self.config["grace_days"])
        from datetime import timedelta

        for experiment in self.running():
            due = str(experiment.get("evaluate_after") or "")
            if not due or due > at:
                continue
            variant_id = experiment.get("variant_desk_id")
            parent_id = experiment.get("parent_id")
            variant = active.get(variant_id) if isinstance(variant_id, str) else None
            parent = active.get(parent_id) if isinstance(parent_id, str) else None
            if variant is None or parent is None:
                actions.append(self._verdict(experiment, "rejected", {}, "the variant or its parent is gone", at))
                continue
            report = committee.gates(variant.id, at)
            control = committee.gates(parent.id, at)
            evidence = {"variant": report["evidence"], "parent": control["evidence"]}
            decisions = int(report["evidence"].get("decisions") or 0)
            if decisions < min_decisions:
                deadline = iso_time(parse_iso(due) + timedelta(days=grace))
                if at < deadline:
                    continue  # not yet enough evidence; the grace period is still running
                actions.append(
                    self._verdict(
                        experiment, "rejected", evidence,
                        f"only {decisions} decisions after the grace period; {min_decisions} needed", at,
                        variant=variant,
                    )
                )
                continue
            excess_v = Decimal(str(report["evidence"].get("cost_adjusted_excess_pct") or "0"))
            excess_p = Decimal(str(control["evidence"].get("cost_adjusted_excess_pct") or "0"))
            dd_v = Decimal(str(report["evidence"].get("max_drawdown_pct") or "0"))
            dd_p = Decimal(str(control["evidence"].get("max_drawdown_pct") or "0"))
            cap = Decimal(str(committee.config.get("gate_max_drawdown_pct", "0.15")))
            better = excess_v > excess_p
            safe = dd_v <= max(dd_p, cap) and int(report["evidence"].get("breakers") or 0) == 0
            if better and safe:
                reason = (
                    f"cost-adjusted excess {excess_v} against the parent's {excess_p}, "
                    f"drawdown {dd_v} against {dd_p}"
                )
                self.evolution.adopt_change(
                    str(experiment.get("family")), experiment.get("change") or {}, experiment["experiment_id"], at
                )
                actions.append(self._verdict(experiment, "adopted", evidence, reason, at))
            else:
                reason = (
                    f"cost-adjusted excess {excess_v} against the parent's {excess_p}"
                    if not better
                    else f"drawdown {dd_v} or a breaker outside the mandate"
                )
                actions.append(self._verdict(experiment, "rejected", evidence, reason, at, variant=variant))
        return actions

    def _verdict(
        self,
        experiment: Mapping[str, Any],
        status: str,
        evidence: Mapping[str, Any],
        reason: str,
        at: str,
        *,
        variant: DeskManifest | None = None,
    ) -> dict[str, Any]:
        exp_id = str(experiment["experiment_id"])
        payload = {
            "experiment_id": exp_id,
            "status": status,
            "evidence": dict(evidence),
            "reason": reason[:600],
            "as_of": at,
        }
        self.log.append("lab", VERDICT_KIND, payload, id=f"{exp_id}:verdict", at=at)
        if status == "rejected" and variant is not None:
            try:
                median = self.evolution.score(str(experiment.get("parent_id")), at)
            except Exception:
                median = Decimal(0)
            self.evolution.retire(variant, at, median=median, reason=f"experiment {exp_id} rejected: {reason[:200]}")
        return {"action": "verdict", **payload}


__all__ = [
    "DEFAULT_CONFIG",
    "EXPERIMENT_KIND",
    "Lab",
    "LabError",
    "STATUSES",
    "VERDICT_KIND",
    "experiment_id",
    "parse_proposals",
    "validate_change",
]
