"""Meriwether, the investment committee: capital follows evidence, not narrative.

Two things happen here and they are deliberately separated.

**Rules.** `gates()` and `allocate()` are ordinary arithmetic over the event log. Capital moves
only through the pre-registered gates in section 7 of the Floor proposal: days live, a minimum
number of independent decisions, a *cost-adjusted* excess return over a benchmark, drawdown inside
mandate, no circuit breakers, clean reconciliations. A desk that is bankrupt or has breached its
mandate goes to zero. The sum of every sleeve never exceeds the floor's own capital. No model is
consulted, and nothing here can be talked out of a number.

**Narrative.** `memo()` asks the provider for the committee memo, written every day the floor
runs (`memo_daily`, the default) or once a week when it is switched off. It is published, it is
read, and it cannot move a single dollar. The reader is the public, not the floor.

Allocations are published as `committee.allocation` events, which every desk sub-ledger folds as
external flows: a raise is a deposit, a cut is a withdrawal, and neither is mistaken for skill.

A **shadow** desk is never funded. Its allocation is a notional scoring budget -- the capital its
manifest asks for -- so that its hypothetical book is comparable with a live one; the event names
those desks under `shadow`, and nothing that carries that flag is ever counted as the floor's
money. A shadow desk earns a live sleeve by passing gate A, and only then does capital move.
"""

from __future__ import annotations
import hashlib
import random

import time
from datetime import timedelta
from decimal import ROUND_DOWN, Decimal
from typing import Any, Callable, Iterable, Mapping

from .broker import money, text
from .events import EventLog, now_iso
from .ledger import DeskLedger, iso_time, parse_iso
from .manifest import DeskManifest

ZERO = Decimal(0)
CENTS = Decimal("0.01")

#: The memo is signed, always, whether or not the model remembered to.
SIGNATURE = "\u2014 Meriwether"

DEFAULT_CONFIG: dict[str, Any] = {
    # Gate A, the gate a shadow desk passes to earn a live sleeve.
    "gate_min_days": 14,
    "gate_min_decisions": 20,
    "gate_min_excess_pct": "0",  # cost-adjusted excess must be strictly greater than this
    "gate_max_drawdown_pct": "0.15",
    "gate_max_breakers": 0,
    # Allocation.
    "floor_capital_usd": "5000",
    "resize_interval_days": 7,
    "min_multiple": "0.5",
    "max_multiple": "2",
    "back_to_shadow_drawdown_pct": "0.15",
    # leap: lab -- capital as a bandit. On a resize day each live desk's multiple is drawn from
    # a posterior over its cost-adjusted excess return (Thompson sampling) instead of read off
    # its score; see `Committee._bandit_multiple` for the arithmetic. False restores the ratio.
    "bandit_enabled": True,
    "bandit_prior_sd_pct": "5",
    "bandit_scale_pct": "10",
    "bandit_decisions_scale": 10,
    # Inference budget. The floor's daily model spend is a fixed base plus a share of the profit
    # the floor actually realized in the last week: the swarm earns its own compute, and a losing
    # week cannot quietly raise the bill.
    "floor_cap_usd_per_day": "15",
    "profit_share": "0.25",
    "profit_window_days": 7,
    "floor_cap_max_usd_per_day": "60",
    # The memo. Daily by default: the floor trades every day, so it reports every day.
    "memo_daily": True,
    "memo_profile": "pro_flex",
    "memo_budget_usd_per_day": "1.00",
    "memo_max_chars": 2000,
    "memo_reasoning_effort": "medium",
    "memo_max_output_tokens": 4096,
}


# --------------------------------------------------------------------------- lineage helpers

def retired_desks(log: EventLog) -> set[str]:
    """Desks the evolution loop has retired. Manifests are never edited, so the log is the truth."""
    return {
        event.payload["desk_id"]
        for event in log.read(kind="evolution.retired", limit=10_000, newest=True)
        if isinstance(event.payload.get("desk_id"), str)
    }


def promoted_desks(log: EventLog) -> dict[str, str]:
    """desk_id -> capital mode, for desks promoted or demoted after their manifest was written.

    "paper" is the old name for "shadow" and is read as such, so a promotion recorded before the
    rename still says the same thing years later.
    """
    modes: dict[str, str] = {}
    for event in log.read(kind="evolution.promoted", limit=10_000, newest=True):
        desk_id = event.payload.get("desk_id")
        to = event.payload.get("to")
        if to == "paper":
            to = "shadow"
        if isinstance(desk_id, str) and to in ("shadow", "live"):
            modes[desk_id] = to
    return modes


def capital_mode(manifest: DeskManifest, modes: Mapping[str, str]) -> str:
    """"shadow" or "live". The log wins over the manifest: promotion is an event, not an edit."""
    return modes.get(manifest.id, manifest.capital_mode)


def live_desks(manifests: Mapping[str, DeskManifest], modes: Mapping[str, str]) -> set[str]:
    """The desks trading real money. Everything else is scored, not funded."""
    return {
        desk_id
        for desk_id, manifest in manifests.items()
        if capital_mode(manifest, modes) == "live"
    }


def iso_week(at: str) -> str:
    year, week, _ = parse_iso(at).isocalendar()
    return f"{year}-W{week:02d}"


def _as_manifests(manifests: Any) -> dict[str, DeskManifest]:
    if manifests is None:
        return {}
    if isinstance(manifests, Mapping):
        return dict(manifests)
    return {m.id: m for m in manifests}


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(CENTS, rounding=ROUND_DOWN)


def signed(body: str, limit: int) -> str:
    """The memo as it is published: inside the character limit and signed by the chair."""
    body = body.strip()
    if SIGNATURE.lower() in body[-80:].lower() or "meriwether" in body[-80:].lower():
        return body[:limit]
    tail = "\n\n" + SIGNATURE
    return body[: max(0, limit - len(tail))].rstrip() + tail


class Committee:
    """Rules-based capital allocation across the floor, plus the published committee memo."""

    def __init__(
        self,
        log: EventLog,
        manifests: Mapping[str, DeskManifest] | Iterable[DeskManifest],
        ledgers: Mapping[str, DeskLedger],
        provider: Any = None,
        clock: Callable[[], float] = time.time,
        config: Mapping[str, Any] | None = None,
        venue_equity: Callable[[], Mapping[str, Any]] | None = None,
    ):
        self.log = log
        self.manifests = _as_manifests(manifests)
        self.ledgers = dict(ledgers)
        self.provider = provider
        self.clock = clock
        self.config = {**DEFAULT_CONFIG, **dict(config or {})}
        #: The venues' own equity, read live by the service: a live sleeve can only be as big as
        #: the account it trades from, however the floor's capital is counted.
        self.venue_equity = venue_equity
        #: `benchmark(start_iso, end_iso) -> Decimal` in percentage points; flat when absent.
        self.benchmark: Callable[[str, str], Decimal] | None = self.config.get("benchmark")

    # ------------------------------------------------------------------ helpers
    def now(self) -> str:
        return now_iso(self.clock)

    def ledger(self, desk_id: str) -> DeskLedger:
        ledger = self.ledgers.get(desk_id)
        if ledger is None:
            ledger = self.ledgers[desk_id] = DeskLedger(self.log, desk_id)
        return ledger

    def modes(self) -> dict[str, str]:
        return promoted_desks(self.log)

    def active(self) -> dict[str, DeskManifest]:
        retired = retired_desks(self.log)
        return {k: v for k, v in self.manifests.items() if k not in retired}

    def cost_usd(self, desk_id: str) -> Decimal:
        """Everything the floor has paid the model provider on this desk's behalf."""
        total = ZERO
        for event in self.log.read(kind="provider.request", limit=10_000, newest=True):
            if event.payload.get("desk_id") != desk_id:
                continue
            value = event.payload.get("cost_usd")
            if value is None:
                continue
            try:
                total += money(value)
            except (TypeError, ValueError):
                continue
        return total

    def breaker_count(self, desk_id: str) -> int:
        scope = f"desk:{desk_id}"
        return sum(
            1
            for event in self.log.read(kind="risk.breaker", limit=10_000, newest=True)
            if event.payload.get("scope") == scope
        )

    def paused(self, desk_id: str) -> bool:
        scope = f"desk:{desk_id}"
        return any(
            event.payload.get("scope") == scope and event.payload.get("action") == "pause_desk"
            for event in self.log.read(kind="risk.breaker", limit=10_000, newest=True)
        )

    def reconciliation_clean(self, desk_id: str) -> bool:
        manifest = self.manifests.get(desk_id)
        venues = set(manifest.venues) if manifest else set()
        for event in self.log.read(kind="broker.reconciled", limit=10_000, newest=True):
            if venues and event.payload.get("venue") not in venues:
                continue
            if event.payload.get("mismatches"):
                return False
        return True

    def benchmark_pct(self, start: str | None, end: str) -> Decimal:
        if self.benchmark is None or not start:
            return ZERO
        try:
            return money(self.benchmark(start, end))
        except Exception:
            return ZERO

    # ------------------------------------------------------------------ inference budget
    def realized_since(self, cutoff: str, at: str) -> Decimal:
        """Net realized profit across every sleeve between `cutoff` and `at`, fees included.

        Realized only: an unrealized mark is not money the floor can spend on compute.
        """
        total = ZERO
        for desk_id in sorted(self.ledgers):
            now_state = self.ledger(desk_id).state(at)
            then = DeskLedger(self.log, desk_id, until=cutoff).state(cutoff)
            total += (now_state.realized_pnl - now_state.fees) - (then.realized_pnl - then.fees)
        return total

    def compute_budget(self, now: Any = None) -> dict[str, Any]:
        """The floor's daily inference cap: a base, plus a share of last week's realized profit.

        `cap = min(base + share * max(0, trailing realized profit), ceiling)`. The floor never
        spends more on thinking because of a gain it has not banked, and never less than the base.
        """
        at = iso_time(now) if now is not None else self.now()
        window = int(self.config["profit_window_days"])
        cutoff = iso_time(parse_iso(at) - timedelta(days=window))
        base = money(self.config["floor_cap_usd_per_day"])
        share = money(self.config["profit_share"])
        ceiling = money(self.config["floor_cap_max_usd_per_day"])
        realized = self.realized_since(cutoff, at)
        bonus = (share * realized) if realized > 0 else ZERO
        cap = min(ceiling, base + bonus).quantize(CENTS, rounding=ROUND_DOWN)
        return {
            "scope": "floor",
            "cap_usd": cap,
            "base_usd": base,
            "profit_share": share,
            "profit_window_days": window,
            "trailing_realized_usd": realized.quantize(CENTS, rounding=ROUND_DOWN),
            "ceiling_usd": ceiling,
            "since": cutoff,
            "as_of": at,
        }

    # ------------------------------------------------------------------ gates
    def gates(self, desk_id: str, now: Any = None) -> dict[str, Any]:
        """Evidence and verdict for the desk's next gate. Pure arithmetic, published verbatim."""
        at = iso_time(now) if now is not None else self.now()
        manifest = self.manifests.get(desk_id)
        state = self.ledger(desk_id).state(at)
        mode = capital_mode(manifest, self.modes()) if manifest else "shadow"
        gate = "B" if mode == "live" else "A"

        capital = state.net_deposits if state.net_deposits > 0 else (
            manifest.capital_usd if manifest else ZERO
        )
        cost = self.cost_usd(desk_id)
        cost_pct = (cost / capital * 100) if capital > 0 else ZERO
        bench = self.benchmark_pct(state.started_at, at)
        excess = state.time_weighted_return_pct - bench - cost_pct
        breakers = self.breaker_count(desk_id)
        clean = self.reconciliation_clean(desk_id)

        evidence = {
            "mode": mode,
            "days_live": state.days_live,
            "decisions": state.decisions,
            "equity": text(state.equity),
            "capital_usd": text(capital),
            "return_pct": text(state.time_weighted_return_pct),
            "benchmark_pct": text(bench),
            "cost_usd": text(cost),
            "cost_pct": text(cost_pct.quantize(Decimal("0.0001"))),
            "cost_adjusted_excess_pct": text(excess.quantize(Decimal("0.0001"))),
            "max_drawdown_pct": text(state.max_drawdown_pct),
            "breakers": breakers,
            "reconciliation_clean": clean,
            "as_of": at,
        }
        checks = {
            "days_live": state.days_live >= int(self.config["gate_min_days"]),
            "decisions": state.decisions >= int(self.config["gate_min_decisions"]),
            "cost_adjusted_return": excess > money(self.config["gate_min_excess_pct"]),
            "drawdown": state.max_drawdown_pct <= money(self.config["gate_max_drawdown_pct"]),
            "breakers": breakers <= int(self.config["gate_max_breakers"]),
            "reconciliation": clean,
        }
        return {
            "desk_id": desk_id,
            "gate": gate,
            "passed": all(checks.values()),
            "checks": checks,
            "evidence": evidence,
            "failed": sorted(name for name, ok in checks.items() if not ok),
        }

    def score(self, desk_id: str, now: Any = None) -> Decimal:
        """Return per unit of pain: `return_pct / (1 + 0.5 * max_drawdown)`."""
        state = self.ledger(desk_id).state(iso_time(now) if now is not None else self.now())
        divisor = Decimal(1) + Decimal("0.5") * state.max_drawdown_pct
        if divisor <= 0:
            return ZERO
        return (state.time_weighted_return_pct / divisor).quantize(Decimal("0.000001"))

    # ------------------------------------------------------------------ allocation
    def last_allocation(self) -> tuple[dict[str, Decimal], str | None]:
        event = self.log.last("committee", "committee.allocation")
        if event is None:
            return {}, None
        allocations = event.payload.get("allocations") or {}
        out: dict[str, Decimal] = {}
        for desk_id, value in allocations.items():
            try:
                out[desk_id] = money(value)
            except (TypeError, ValueError):
                continue
        return out, event.at

    def _resize_due(self, last_at: str | None, at: str) -> bool:
        if last_at is None:
            return True
        days = (parse_iso(at) - parse_iso(last_at)).days
        return days >= int(self.config["resize_interval_days"])

    def allocate(self, now: Any = None, *, resize: bool | None = None) -> dict[str, Decimal]:
        """Set each desk's capital target and publish it. Returns `{desk_id: usd}`.

        `resize=True` moves capital by track record now; None decides from the last allocation's
        age. The service passes True on its resize schedule: evolution changes the roster most
        nights, and every roster change writes an allocation, so an age measured from the last
        allocation of any kind would push a daily resize back forever."""
        at = iso_time(now) if now is not None else self.now()
        previous, last_at = self.last_allocation()
        if resize is None:
            resize = self._resize_due(last_at, at)
        modes = self.modes()
        active = self.active()
        breach_limit = money(
            self.config.get("back_to_shadow_drawdown_pct")
            or self.config.get("back_to_paper_drawdown_pct")
        )
        low = money(self.config["min_multiple"])
        high = money(self.config["max_multiple"])

        states = {desk_id: self.ledger(desk_id).state(at) for desk_id in active}
        live_scores: dict[str, Decimal] = {}
        for desk_id, manifest in active.items():
            if capital_mode(manifest, modes) == "live":
                live_scores[desk_id] = self.score(desk_id, at)
        best = max(live_scores.values()) if live_scores else ZERO

        targets: dict[str, Decimal] = {}
        reasons: dict[str, str] = {}
        #: desk_id -> True for every target that is a notional scoring budget, not money.
        shadow: dict[str, bool] = {}
        for desk_id, manifest in sorted(active.items()):
            state = states[desk_id]
            base = manifest.capital_usd
            bankrupt = state.net_deposits > 0 and state.equity <= 0
            breached = state.max_drawdown_pct >= breach_limit or self.paused(desk_id)
            if bankrupt:
                targets[desk_id] = ZERO
                reasons[desk_id] = "bankrupt: equity at or below zero"
                continue
            if breached:
                targets[desk_id] = ZERO
                reasons[desk_id] = (
                    f"mandate breach: drawdown {state.max_drawdown_pct} >= {breach_limit}"
                    if not self.paused(desk_id)
                    else "mandate breach: desk paused by a circuit breaker"
                )
                continue
            if capital_mode(manifest, modes) != "live":
                # A shadow desk is never funded. Its "allocation" is the notional book its
                # proposals are scored against, so the scoreboard compares like with like.
                targets[desk_id] = _quantize(base)
                shadow[desk_id] = True
                reasons[desk_id] = "shadow sleeve: notional scoring budget at manifest capital"
                continue
            if not resize:
                held = previous.get(desk_id, base)
                targets[desk_id] = _quantize(held)
                reasons[desk_id] = "held between weekly resizes"
                continue
            if bool(self.config.get("bandit_enabled", True)):  # leap: lab
                multiple, why = self._bandit_multiple(desk_id, at, low, high)
                targets[desk_id] = _quantize(base * multiple)
                reasons[desk_id] = why
                continue
            score = live_scores.get(desk_id, ZERO)
            if best > 0 and score > 0:
                multiple = (high * score / best)
            else:
                multiple = Decimal(1) if score >= 0 else low
            multiple = min(high, max(low, multiple))
            targets[desk_id] = _quantize(base * multiple)
            reasons[desk_id] = f"score {score} -> {multiple.quantize(Decimal('0.01'))}x manifest capital"

        # Desks that have left the roster are wound down to zero rather than forgotten.
        for desk_id, amount in previous.items():
            if desk_id not in targets and amount != ZERO:
                targets[desk_id] = ZERO
                reasons[desk_id] = "desk retired or removed from the roster"

        # The floor's real capital is what the venues hold today, so profit compounds into the
        # next allocation and a loss shrinks it; the configured number is the fallback for a
        # day the venues do not answer. (Until Sept 16, 2026 the cap was the configured number
        # alone, so the sleeves could never grow past the day-one deposit.)
        equity_by_venue: dict[str, Decimal] = {}
        if self.venue_equity is not None:
            try:
                for venue, amount in dict(self.venue_equity() or {}).items():
                    equity_by_venue[str(venue)] = money(amount)
            except Exception:
                equity_by_venue = {}
        held_total = sum(equity_by_venue.values(), ZERO)
        cap = held_total if held_total > ZERO else money(self.config["floor_capital_usd"])
        # Only real sleeves compete for the floor's real capital; a notional budget costs nothing.
        funded = {k: v for k, v in targets.items() if not shadow.get(k)}
        total = sum(funded.values(), ZERO)
        if cap > 0 and total > cap:
            factor = cap / total
            for desk_id in funded:
                targets[desk_id] = _quantize(targets[desk_id] * factor)
            reasons = {
                k: f"{v}; scaled to the floor's {text(cap)} of capital" for k, v in reasons.items()
            }

        # And no venue's live sleeves may add up to more than that venue actually holds: three
        # desks sharing one Kalshi account cannot each be told they have the whole account.
        for venue, held in equity_by_venue.items():
            sleeves = [
                desk_id for desk_id in funded
                if desk_id in active and active[desk_id].market_venue == venue and targets.get(desk_id, ZERO) > ZERO
            ]
            total_on_venue = sum((targets[d] for d in sleeves), ZERO)
            if held > ZERO and total_on_venue > held:
                factor = held / total_on_venue
                for desk_id in sleeves:
                    targets[desk_id] = _quantize(targets[desk_id] * factor)
                    reasons[desk_id] = f"{reasons.get(desk_id, '')}; scaled to {venue}'s {text(_quantize(held))} of equity".lstrip("; ")

        self._publish_gates(active, at)
        if previous != targets:
            self.log.append(
                "committee",
                "committee.allocation",
                {
                    "allocations": {k: text(v) for k, v in sorted(targets.items())},
                    # Which of those targets are notional. A desk named here is never funded:
                    # its book is a score and the floor's equity never counts it.
                    "shadow": {k: True for k in sorted(shadow)},
                    "reasons": reasons,
                    "floor_capital_usd": text(cap),
                    "as_of": at,
                },
                id=f"alloc:{at}",
                at=at,
            )
        return targets

    # leap: lab ------------------------------------------------------- the bandit
    def bandit_sigma(self, decisions: int) -> Decimal:
        """The posterior's spread, in percentage points, after `decisions` fills.

        `sigma = prior_sd / sqrt(1 + decisions / decisions_scale)`: a desk with no record is
        as uncertain as the prior says, and the uncertainty shrinks with the square root of
        the evidence, the way a sample mean's does.
        """
        prior = money(self.config["bandit_prior_sd_pct"])
        scale = Decimal(int(self.config["bandit_decisions_scale"]))
        return (prior / (Decimal(1) + Decimal(int(decisions)) / scale).sqrt()).quantize(Decimal("0.0001"))

    def _bandit_multiple(
        self, desk_id: str, at: str, low: Decimal, high: Decimal
    ) -> tuple[Decimal, str]:
        """Thompson sampling over one live desk's cost-adjusted excess return.

        The posterior is normal: its mean is the desk's cost-adjusted excess return in
        percentage points (the same number the published gate carries), its spread is
        `bandit_sigma(decisions)`. One draw is taken from it with a generator seeded by the
        allocation date and the desk id, so the draw is reproducible from the public record
        and identical however many times the day's allocation is recomputed. The draw maps
        to a multiple of manifest capital linearly, `1 + draw / bandit_scale_pct`, clamped to
        the committee's floor and ceiling: a draw of +10 points doubles the sleeve at the
        default scale, a draw of -5 halves it. Over weeks the desks that keep earning are
        sampled high more often than not and compound; the ones that do not are starved, but
        never to zero by the bandit alone -- the gates and the breach rules do that.
        """
        evidence = self.gates(desk_id, at)["evidence"]
        mean = money(evidence.get("cost_adjusted_excess_pct") or "0")
        decisions = int(evidence.get("decisions") or 0)
        sigma = self.bandit_sigma(decisions)
        seed = int(hashlib.sha256(f"alloc:{at[:10]}:{desk_id}".encode("utf-8")).hexdigest(), 16)
        draw = Decimal(str(round(random.Random(seed).gauss(float(mean), float(sigma)), 4)))
        scale = money(self.config["bandit_scale_pct"])
        multiple = min(high, max(low, Decimal(1) + draw / scale))
        why = (
            f"thompson: drew {draw:+.2f}pp from N({mean:.2f}, {sigma:.2f}) over {decisions} "
            f"decisions -> {multiple.quantize(Decimal('0.01'))}x manifest capital"
        )
        return multiple, why

    def _publish_gates(self, active: Mapping[str, DeskManifest], at: str) -> None:
        for desk_id in sorted(active):
            report = self.gates(desk_id, at)
            self.log.append(
                "committee",
                "committee.gate",
                {
                    "desk_id": desk_id,
                    "gate": report["gate"],
                    "passed": report["passed"],
                    "evidence": report["evidence"],
                    "failed": report["failed"],
                },
                id=f"gate:{desk_id}:{at}",
                at=at,
            )

    # ------------------------------------------------------------------ the memo
    def brief(self, at: str) -> str:
        """The factual packet the memo is written from. No prices, no prompts, no secrets."""
        lines = [f"Floor review as of {at[:10]}.", ""]
        modes = self.modes()
        for desk_id, manifest in sorted(self.active().items()):
            state = self.ledger(desk_id).state(at)
            report = self.gates(desk_id, at)
            lines.append(
                f"- {manifest.name} [{desk_id}] ({capital_mode(manifest, modes)}, "
                f"{manifest.family} gen "
                f"{manifest.generation}): equity {text(state.equity)}, return "
                f"{text(state.time_weighted_return_pct)}%, max drawdown "
                f"{text(state.max_drawdown_pct)}, {state.decisions} decisions over "
                f"{state.days_live} days, cost {report['evidence']['cost_usd']} USD, gate "
                f"{report['gate']} {'passed' if report['passed'] else 'failed: ' + ', '.join(report['failed'])}."
            )
        allocations, _ = self.last_allocation()
        if allocations:
            lines.append("")
            lines.append(
                "Current allocations: "
                + ", ".join(f"{k} {text(v)}" for k, v in sorted(allocations.items()))
            )
        return "\n".join(lines)

    def period(self, at: str) -> str:
        """The memo's identity: one a day by default, one a week when `memo_daily` is off."""
        return at[:10] if self.config.get("memo_daily", True) else iso_week(at)

    def memo(self, now: Any = None) -> str | None:
        """Write and publish the committee memo. Returns the text, or None on failure.

        One memo per period, keyed by the period, so however many times a tick comes round the
        floor pays for it once. `memo_daily` (the default) makes the period a day.
        """
        at = iso_time(now) if now is not None else self.now()
        period = self.period(at)
        existing = self.log.get(f"memo:{period}")
        if existing is not None:
            return existing.payload.get("text")
        if self.provider is None:
            return None
        limit = int(self.config["memo_max_chars"])
        daily = bool(self.config.get("memo_daily", True))
        instructions = (
            "You are Meriwether, who chairs the investment committee of a public, fully "
            "automated trading floor. Write "
            + ("today's" if daily else "this week's")
            + " committee memo for the floor's public site.\n"
            "You are writing for the public: people who do not work here, hold none of these "
            "positions and did not see the trades. Address them directly, explain in plain "
            "English what the floor did and what it means, and define any term a reader would "
            "not know.\n"
            "Name each desk by its partner name -- the name before the bracketed id below -- and "
            "not by its id.\n"
            f"Be specific and concrete, cite the numbers you are given, and stay under {limit} "
            "characters. State what the evidence supports and what it does not. You do not "
            "allocate capital: the published gates do that, mechanically. Never invent a number "
            "that is not below. Sign the memo \"Meriwether\"."
        )
        items = [
            {"role": "system", "content": instructions},
            {"role": "user", "content": self.brief(at)},
        ]
        try:
            response = self.provider.respond(
                self.config["memo_profile"],
                items,
                tools=None,
                desk_id="committee",
                session_id=f"committee-{period}",
                request_key=f"committee-memo:{period}",
                reasoning_effort=self.config["memo_reasoning_effort"],
                max_output_tokens=int(self.config["memo_max_output_tokens"]),
                desk_cap_usd_per_day=self.config["memo_budget_usd_per_day"],
            )
        except Exception as exc:  # BudgetExceeded and every transport failure look the same here
            self.log.append(
                "ops",
                "ops.alert",
                {"level": "warning", "text": f"committee memo for {period} not written: {exc}"},
                id=f"alert:memo:{period}",
                at=at,
            )
            return None
        body = (response.output_text or "").strip()
        if not body:
            return None
        body = signed(body, limit)
        self.log.append(
            "committee",
            "committee.memo",
            {"period": period, "text": body, "as_of": at},
            id=f"memo:{period}",
            at=at,
        )
        return body
