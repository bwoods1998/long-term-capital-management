"""Compute credits: the metabolism of the league.

The owner funds a fixed research budget (it is venture funding, and is called that). An agent's
share of it is decided by performance; its absolute size is decided by the owner. Every agent has
an account of compute credits, denominated in dollars of compute:

- **Income.** Once an epoch the House pays out the pool. A fixed share is the niche floor: split
  evenly across occupied niches (venue x horizon x style), then evenly inside each, so the
  population cannot collapse onto whichever niche got lucky last week. The rest is paid in
  proportion to evidence-weighted performance, and deliberately steeply: mean after-cost block
  growth on the current rung RAISED TO A POWER (two), times the square root of the number of active
  blocks behind it, times the rung's weight (replay earns nothing, paper a little, real money much
  more) -- so a desk twice as profitable earns four times the share, not twice. If nobody has
  performed the share is still spent, but never split evenly: it goes to the least-bad TRADER,
  ranked by how far above the worst it is among agents that have actually traded, and an agent with
  no active block earns none of it. Paying one that has never placed an order what it pays the best
  trader on the floor is how the firm's intelligence reaches agents that have shown nothing.
- **Costs.** Metered model tokens at Sail's prices, sandbox seconds, and frontier audits at cost.
- **Death.** An account at or below zero is dead: the House stops waking the agent.
- **Birth.** An agent above the fork threshold may fork, and must endow the child from its own
  credits.

Credits cannot be created by agents: every grant is a House row on the ledger, and the sum of all
grants is bounded by the pool, so the Sail bill for the whole population is bounded too.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from decimal import ROUND_DOWN, ROUND_UP, Decimal
from pathlib import Path
from typing import Any, Mapping, Sequence

from .ledger import HOUSE, Ledger

ZERO = Decimal(0)
PLACES = Decimal("0.00000001")
GAME_PATH = Path(__file__).resolve().parent / "game.json"


def load_game(path: Path | None = None) -> dict[str, Any]:
    game = json.loads((path or GAME_PATH).read_text(encoding="utf-8"))
    check_bounds(game)
    return game


def check_bounds(game: Mapping[str, Any]) -> None:
    """The game designer may move the dials only inside their bounds."""
    economy = game["economy"]
    for key, (low, high) in game.get("bounds", {}).items():
        value = Decimal(str(economy[key]))
        if not Decimal(str(low)) <= value <= Decimal(str(high)):
            raise ValueError(f"game.json: economy.{key} = {value} is outside [{low}, {high}]")
    for key, (low, high) in game.get("horizon_bounds", {}).items():
        value = float(game["horizon"][key])
        if not float(low) <= value <= float(high):
            raise ValueError(f"game.json: horizon.{key} = {value:g} is outside [{low}, {high}]")
    # M1 of the forward-first run (Sept 25, 2026): the audit's dials inside `audit_bounds` (`audit.pre_pack`, 5-9).
    for key, bound in (game.get("audit_bounds") or {}).items():
        if str(key).startswith("_") or key not in (game.get("audit") or {}):
            continue
        value = float(game["audit"][key])
        if not float(bound[0]) <= value <= float(bound[1]):
            raise ValueError(f"game.json: audit.{key} = {value:g} is outside [{bound[0]}, {bound[1]}]")
    if int(economy["min_population"]) > int(economy["max_population"]):
        raise ValueError("game.json: min_population is above max_population")
    # The Alpha Lab's dials the close-the-gaps plan bounds (Sept 24, 2026): `lab_bounds`, each checked
    # where the lab section sets it (league/lab.py holds `reserved_share` to its bounds as it reads it).
    lab = game.get("lab") or {}
    for key, bound in (game.get("lab_bounds") or {}).items():
        if str(key).startswith("_") or key not in lab:
            continue
        low, high = bound
        value = float(lab[key])
        if not float(low) <= value <= float(high):
            raise ValueError(f"game.json: lab.{key} = {value:g} is outside [{low}, {high}]")
    # Merton's dials (Sept 24, 2026): the scheduled hours `merton_bounds` bounds, and
    # `paused_until_profit` any subset of the roles it lists.
    merton, limits = game.get("merton") or {}, game.get("merton_bounds") or {}
    for role, (low, high) in (limits.get("schedule_hours") or {}).items():
        value = float((merton.get("schedule_hours") or {}).get(role, low))
        if not float(low) <= value <= float(high):
            raise ValueError(f"game.json: merton.schedule_hours.{role} = {value:g} is outside [{low}, {high}]")
    allowed = set(limits.get("paused_until_profit") or ())
    paused = merton.get("paused_until_profit") or []
    if not isinstance(paused, list) or any(role not in allowed for role in paused):
        raise ValueError(f"game.json: merton.paused_until_profit must be a subset of {sorted(allowed)}")
    # F4 (Sept 25, 2026): the lanes' lift dials inside `merton_bounds.lift`.
    lift = merton.get("lift") or {}
    for key, (low, high) in (limits.get("lift") or {}).items():
        if key in lift and not float(low) <= float(lift[key]) <= float(high):
            raise ValueError(f"game.json: merton.lift.{key} = {lift[key]} is outside [{low}, {high}]")
    # F2 (Sept 25, 2026): each research.gate dial `research_bounds.gate` names is inside its range, or
    # one of the values it lists; a list dial (Y's `practice_skip_triggers`) a subset of them.
    gate = (game.get("research") or {}).get("gate") or {}
    for key, bound in ((game.get("research_bounds") or {}).get("gate") or {}).items():
        if key not in gate:
            continue
        if isinstance(gate[key], list):
            if any(item not in bound for item in gate[key]):
                raise ValueError(f"game.json: research.gate.{key} = {gate[key]!r} is not a subset of {bound}")
        elif all(isinstance(v, (str, bool)) for v in bound):
            # A switch (`jev_relevance`, Sept 25, 2026) lists true and false: it must be one of them, a bool.
            if gate[key] not in bound or isinstance(gate[key], bool) != isinstance(bound[0], bool):
                raise ValueError(f"game.json: research.gate.{key} = {gate[key]!r} is not one of {bound}")
        elif not float(bound[0]) <= float(gate[key]) <= float(bound[1]):
            raise ValueError(f"game.json: research.gate.{key} = {gate[key]} is outside [{bound[0]}, {bound[1]}]")
    # The foundry's dials (Sept 25, 2026, the forward-first run's S1): `hypotheses_bounds`, each checked where the
    # hypotheses section sets it (a range a key for a dict dial), and the five route shares at most the whole window.
    foundry, bounds = game.get("hypotheses") or {}, game.get("hypotheses_bounds") or {}
    for key, bound in bounds.items():
        if str(key).startswith("_") or key not in foundry:
            continue
        if isinstance(bound, list) and all(isinstance(v, str) for v in bound):
            # A list dial (`capacity_floor_venues`, the review of Deploy C): a subset of the values it lists.
            if not isinstance(foundry[key], list) or any(item not in bound for item in foundry[key]):
                raise ValueError(f"game.json: hypotheses.{key} = {foundry[key]!r} is not a subset of {bound}")
            continue
        for sub, (low, high) in (bound.items() if isinstance(bound, Mapping) else [(None, bound)]):
            value = float(foundry[key] if sub is None else (foundry[key] or {}).get(sub, low))
            if not float(low) <= value <= float(high):
                name = key if sub is None else f"{key}.{sub}"
                raise ValueError(f"game.json: hypotheses.{name} = {value:g} is outside [{low}, {high}]")
    if bounds:
        shares = sum(float(foundry.get(f"{route}_share") or 0) for route in ("capacity", "model", "transfer", "fast", "exploration"))
        if shares > 1 + 1e-9:
            raise ValueError(f"game.json: the foundry's route shares add up to {shares:g}, more than the whole call window")
    lock = ((game.get("research") or {}).get("gate") or {}).get("abstain_lock_profile")
    if lock is not None:
        from ltcm.provider import PROFILES

        if lock not in PROFILES:
            raise ValueError(f"game.json: research.gate.abstain_lock_profile {lock!r} is not a Sail profile ltcm/provider.py prices")


def usd(value: Any) -> Decimal:
    return Decimal(str(value))


@dataclass(frozen=True)
class Standing:
    """What the payout needs to know about one living agent."""

    agent: str
    niche: str
    rung: int
    mean_growth: float  # mean after-cost log growth per block on the current rung
    active_blocks: int
    #: Whether it has traded lately, or is new enough not to have had the chance. An agent that has
    #: done neither earns no floor: it is not holding a seat in a specialty, it is sitting in one.
    working: bool = True
    reward_growth: float | None = None
    reward_observations: int | None = None
    reward_rung: int | None = None

    @property
    def score_growth(self):
        return self.mean_growth if self.reward_growth is None else self.reward_growth

    @property
    def score_observations(self):
        return self.active_blocks if self.reward_observations is None else self.reward_observations

    @property
    def score_rung(self):
        return self.rung if self.reward_rung is None else self.reward_rung


class Economy:
    def __init__(self, ledger: Ledger, game: Mapping[str, Any] | None = None, *, clock=time.time):
        self.ledger = ledger
        self.game = dict(game or load_game())
        self.rules = self.game["economy"]
        self.clock = clock
        self._lock = threading.RLock()  # agents are woken side by side, and each wake ends in a charge
        self._balances: dict[str, Decimal] = {}
        self._cursor = 0
        self._fold()

    # ------------------------------------------------------------------ state
    def _fold(self) -> None:
        while True:
            batch = self.ledger.read(kinds=("credit.grant", "credit.charge", "credit.transfer"), after=self._cursor, limit=10_000)
            if not batch:
                break
            for entry in batch:
                self._apply(entry.kind, entry.agent, entry.payload)
                self._cursor = entry.seq

    def _record(self, kind: str, payload: Mapping[str, Any], agent: str, id: str | None) -> None:
        """Append one credit row and apply it, once, whatever other thread got there first."""
        with self._lock:
            entry = self.ledger.append(kind, dict(payload), agent=agent, id=id)
            if entry.seq > self._cursor:
                self._fold()

    def _apply(self, kind: str, agent: str, p: Mapping[str, Any]) -> None:
        amount = usd(p["usd"])
        if kind == "credit.grant":
            self._balances[agent] = self._balances.get(agent, ZERO) + amount
        elif kind == "credit.charge":
            self._balances[agent] = self._balances.get(agent, ZERO) - amount
        elif kind == "credit.transfer":
            self._balances[agent] = self._balances.get(agent, ZERO) - amount
            to = str(p["to"])
            self._balances[to] = self._balances.get(to, ZERO) + amount

    def balance(self, agent: str) -> Decimal:
        with self._lock:
            return self._balances.get(agent, ZERO)

    def alive(self, agent: str) -> bool:
        return self.balance(agent) > 0

    # ------------------------------------------------------------------ moves
    def grant(self, agent: str, amount: Any, reason: str, *, id: str | None = None) -> Decimal:
        amount = usd(amount).quantize(PLACES, rounding=ROUND_DOWN)
        if amount <= 0:
            return ZERO
        self._record("credit.grant", {"usd": format(amount, "f"), "reason": reason}, agent, id)
        return amount

    def charge(self, agent: str, amount: Any, what: str, *, detail: Mapping[str, Any] | None = None, id: str | None = None) -> Decimal:
        """Take the cost of something the agent used. A charge is never refused: the compute was
        already spent. An account it takes to zero or below is a dead agent."""
        amount = usd(amount).quantize(PLACES, rounding=ROUND_UP)
        if amount <= 0:
            return ZERO
        payload = {"usd": format(amount, "f"), "what": what, **({"detail": dict(detail)} if detail else {})}
        self._record("credit.charge", payload, agent, id)
        return amount

    def transfer(self, source: str, to: str, amount: Any, reason: str) -> Decimal:
        amount = usd(amount).quantize(PLACES, rounding=ROUND_DOWN)
        if amount <= 0:
            raise ValueError("a transfer moves a positive amount")
        with self._lock:
            if self.balance(source) - amount <= 0:
                raise ValueError(f"{source} cannot give {amount} and stay alive")
            self._record("credit.transfer", {"usd": format(amount, "f"), "to": to, "reason": reason}, source, None)
        return amount

    def can_fork(self, agent: str) -> bool:
        return self.balance(agent) >= usd(self.rules["fork_threshold_usd"])

    def box_cost(self, seconds: float, *, created: bool = False) -> Decimal:
        cost = usd(self.rules["box_usd_per_hour"]) * Decimal(str(max(seconds, 0.0))) / Decimal(3600)
        if created:
            cost += usd(self.rules["box_creation_usd"])
        return cost.quantize(PLACES, rounding=ROUND_UP)

    # ------------------------------------------------------------------ payout
    def shares(self, standings: Sequence[Standing], pool: Any | None = None) -> dict[str, Decimal]:
        """How one epoch's pool divides. Pure: `payout` records what this returns."""
        pool = usd(self.rules["daily_pool_usd"] if pool is None else pool)
        if not standings or pool <= 0:
            return {}
        floor_pool = pool * usd(self.rules["niche_floor_share"])
        performance_pool = pool - floor_pool
        out: dict[str, Decimal] = {s.agent: ZERO for s in standings}
        # A niche is occupied by agents that have qualified for forward testing AND are working.
        # An agent still in replay lives on its endowment, and one that has not traded in an epoch
        # lives on what it has left: a floor for doing nothing would pay for squatting, and an
        # agent that cannot be starved cannot be killed by the game.
        niches: dict[str, list[Standing]] = {}
        for s in standings:
            if s.rung >= 1 and s.working:
                niches.setdefault(s.niche, []).append(s)
        for members in niches.values():
            for s in members:
                out[s.agent] += floor_pool / len(niches) / len(members)
        weights = self.rules["rung_weights"]
        steep = int(self.rules.get("performance_exponent", 1))
        minimum = int(self.rules.get('performance_min_blocks', 0))
        evidenced = [s for s in standings if s.score_observations >= minimum]
        scores = {
            s.agent: Decimal(str(max(s.score_growth, 0.0))) ** steep * Decimal(str(max(s.score_observations, 0))).sqrt() * usd(weights.get(str(s.score_rung), "0"))
            for s in evidenced
        }
        total = sum(scores.values(), ZERO)
        if total <= 0:
            # Nobody evidenced is profitable. A profitable record shorter than the minimum comes
            # before the least-bad LOSER, shrunk by how much of the minimum it has; it never
            # competes with an evidenced winner, where one lucky block would dominate a cubic curve.
            # Measured Sept 21, 2026: a daily-horizon desk earns one block a day, so mullins-2 was
            # up 1.6% a day on two blocks and earned nothing, while the 17:00 payout went to
            # hilibrand-2 and three huang agents, all under water, as the least bad.
            scores = {s.agent: (Decimal(str(s.score_growth)) ** steep * Decimal(s.score_observations).sqrt()
                                * usd(weights.get(str(s.score_rung), "0")) * Decimal(s.score_observations) / Decimal(minimum))
                      for s in standings if 0 < s.score_observations < minimum and s.score_growth > 0}
            total = sum(scores.values(), ZERO)
        if total <= 0:
            scores = self._least_bad(evidenced, weights)
            total = sum(scores.values(), ZERO)
        if total > 0:
            for agent, score in scores.items():
                out[agent] += performance_pool * score / total
        elif self.rules.get("unearned_share_to_floors") and niches:
            # Not one agent has an active block yet -- the first hours of a league, and nothing to
            # rank. The owner wants the budget USED, so it follows the floors rather than going
            # unspent; the moment anybody trades at all, `_least_bad` has something to rank.
            for members in niches.values():
                for s in members:
                    out[s.agent] += performance_pool / len(niches) / len(members)
        return {agent: amount.quantize(PLACES, rounding=ROUND_DOWN) for agent, amount in out.items()}

    def _least_bad(self, standings: Sequence[Standing], weights: Mapping[str, Any]) -> dict[str, Decimal]:
        """Who earns the performance share on a day when nobody is profitable yet.

        Splitting it evenly, which is what the league did at first, paid an agent that had never
        placed an order exactly what it paid the best trader on the floor -- and with credits
        buying research and Merton's time, that is frontier intelligence handed to agents that have
        shown nothing. Ranked instead by how far above the WORST an agent is, among those that have
        actually traded this rung. The worst earns nothing, an agent with no active block earns
        nothing, and the ranking is by the same rung weights as profit, so the day somebody is
        profitable this vanishes and the real scores take over."""
        traded = [s for s in standings if s.score_observations > 0 and usd(weights.get(str(s.score_rung), "0")) > 0]
        if len(traded) < 2:
            return {}
        worst = min(s.score_growth for s in traded)
        return {s.agent: Decimal(str(s.score_growth - worst)) * Decimal(str(s.score_observations)).sqrt() * usd(weights.get(str(s.score_rung), "0"))
                for s in traded}

    def last_payout_at(self) -> float | None:
        rows = [e for e in self.ledger.read(kinds="ops.budget", limit=200, newest=True) if e.payload.get("what") == "payout"]
        if not rows:
            return None
        return float(rows[-1].payload["epoch_at"])

    def payout_due(self) -> bool:
        last = self.last_payout_at()
        return last is None or self.clock() - last >= float(self.rules["epoch_seconds"])

    def payout(self, standings: Sequence[Standing], *, pool: Any | None = None) -> dict[str, Decimal]:
        """Pay one epoch. The pool is scaled to the time since the last payout (capped at two
        epochs, so downtime is not back-paid as a windfall)."""
        now = self.clock()
        last = self.last_payout_at()
        epoch = float(self.rules["epoch_seconds"])
        scale = Decimal(1) if last is None else Decimal(str(min(max((now - last) / epoch, 0.0), 2.0)))
        base = usd(self.rules["daily_pool_usd"] if pool is None else pool) * scale
        shares = self.shares(standings, base)
        stamp = f"{now:.3f}"
        for agent, amount in sorted(shares.items()):
            self.grant(agent, amount, "epoch payout", id=f"payout:{stamp}:{agent}")
        self.ledger.append(
            "ops.budget",
            {
                "what": "payout",
                "epoch_at": now,
                "pool_usd": format(base.quantize(PLACES), "f"),
                "paid_usd": format(sum(shares.values(), ZERO), "f"),
                "agents": len(shares),
            },
            id=f"payout:{stamp}",
        )
        return shares
