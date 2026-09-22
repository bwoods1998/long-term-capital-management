"""The hypothesis foundry: Merton writes falsifiable strategies for the desks where evidence says
they can work, replay admits them before they cost a paper seat, and exhausted ideas stop breeding.

Why this exists (measured on the production ledger, Sept 22, 2026): 94% of the previous day's births
were House-staked parameter mutations placed on the desk "with the most room" (`House._refill`), and
66% of them landed on six desks that had never produced a live agent -- crypto strikes, crypto
majors, attention, crypto alts, megacaps and props. Over the league's life those six had run 74,
52, 47, 81, 94 and 73 replays with NO pass between them, and the parent lines already carried a
median of fifteen failed trials each. The weather desk had passed 12 of its 32 replays and sent
every agent it had to paper, yet received four mutations. Replay passes 6.5% of trials and does
predict paper results, so it stays the admission test; what changes is what is sent to it.

One foundry pass:

1. **Allocate.** Every open, replayable desk is scored from its own evidence (`desk_scores`): its
   replay pass rate (shrunk toward the league's), the share of its traders earning forward, and
   how often its inputs were actually there. How EMPTY a desk is does not enter the score; a desk
   with no open seat is merely ineligible. A bounded share of passes (`exploration_share`, 20%)
   goes instead to the least-explored eligible desk, so an early winner cannot starve every new
   direction.
2. **Ask.** When a seat is actually open, the frontier tier still pays for code work, the day's
   OpenAI allowance and the foundry's own window budget have room, and the last call is at least
   `call_minutes` old, Merton (the frontier model, through the same metered gateway client every
   other pass uses) is shown the desk's definition, the data that really exists, the fee model,
   the replay gate, what failed there and what is retired, and asked for 3-4 distinct candidates.
   Each is a `hypothesis.card` (mechanism, data, edge after costs, horizon, rejection evidence)
   plus a whole strategy file. It is never shown a tape, a holdout or any replay's per-step data:
   only development-replay SUMMARIES that the researchers already see.
3. **Admit.** Each card's code is checked statically, then replayed through the House's own
   candidate replay (`House._candidate_replay`: the sealed NEEDS probe, the specialty's
   constraints, parameter validation, a counted `eval.trial`). A card is its own line -- a new
   hypothesis, like a founder or an architect's strategy -- so its trial is recorded under the id
   its child will carry, and the child's lineage includes it. Only a passer is born, through
   `House.spawn`, straight onto a paper seat; a failure is a counted trial on the card's line and
   no agent ever exists for it.
4. **Retire.** A family (the House's unit of "one idea on one kind of market") with
   `retire_after_failures` counted failures and no pass is retired: `disproven` when its replays
   ran on real data and failed the gates, `blocked_data` when most of them walked an empty tape.
   Card evaluations that could not run are `blocked_data` (missing inputs) or `blocked_infra`
   (sandbox errors, timeouts, crashes), and a desk that keeps hitting them becomes a
   `repair.reported` row rather than more births. Retired families get no House mutations; a
   retired or already-tested mechanism gets no new card. `hypothesis.link` rewordings share
   FAILURE HISTORY for this heuristic only; genealogy and trial counts never follow a link.

What routine refill does now (`refill`, from `House._refill` when `replace_mutation_refill` is on):
a replay-passing card first, by desk evidence; otherwise an evidence-driven mutation of a parent
that is earning forward, within `mutation_share` of recent births; otherwise nobody. The deliberate
exceptions are kept and labelled on the ledger (`route.decision`, one row per birth): founders start
on paper without a replay pass, earner forks are paid by a parent that earned, a research
candidate's child starts on paper because its own code passed replay, and the architect's
strategies still answer to replay from rung 0.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
from copy import deepcopy
from dataclasses import dataclass, asdict
from decimal import Decimal
from typing import Any, Mapping, Sequence

from .agents import Agent, niche_of
from .constitution import CONSTITUTION
from .ledger import now_iso

PROMPT_VERSION = "foundry-2026-09-22.2"
ROLE = "foundry"
TASK_CALL = "hypothesis.foundry"
TASK_EVALUATE = "hypothesis.evaluate"

#: The dials, overridden by `game.json` `hypotheses`. Kept here too so an older game file (or a test
#: game) still gets a sane, bounded foundry.
DEFAULTS: dict[str, Any] = {
    "enabled": True,
    "replace_mutation_refill": True,
    "call_minutes": 30,
    "candidates": 4,
    "max_output_tokens": 16000,
    "effort": "medium",
    "budget_usd": "20",
    "budget_window_hours": 24,
    "exploration_share": 0.2,
    "exploration_window": 10,
    "retire_after_failures": 15,
    "blocked_share": 0.5,
    "repair_after_blocked": 3,
    "infra_failures": 5,
    "blocked_hours": 24,
    "max_evaluation_attempts": 3,
    "mutation_share": 0.2,
    "mutation_min_per_day": 2,
    "card_ttl_hours": 24,
    "link_min_confidence": 0.8,
    "prior_weight": 10,
    "evidence_days": 14,
}

#: Words that say a candidate's replay could not run because an INPUT was missing, not because the
#: idea failed. (`House._run_replay` raises "unsupported input: ..." for missing observed bars.)
_DATA_WORDS = ("unsupported input", "missing", "no tape", "no data", "empty tape", "not recorded", "no recorded")
#: And the words of a harness failure: the box, the clock or the platform, not the strategy.
_INFRA_WORDS = ("sandbox", "timed out", "timeout", "killed", "could not be run", "exit 137", "no result line",
                "connection", "urlerror", "httperror", "oserror", "brokenpipe", "transporterror", ": http 5", ": http 429",
                "response is not an object")

#: What a strategy sees on the REPLAY tape, which is not everything a live wake sees (league/replay.py).
#: Measured in the Sept 22, 2026 dry run: three of four megacaps cards guarded against stale quotes by
#: their `t` stamp, which replay quotes do not carry, and so never traded at all -- a counted trial
#: that tested nothing. Merton is told this as a fact of the test, not a hint about edge.
REPLAY_VIEW = {
    "every_step": ["now", "venue", "rung (0)", "params", "memory", "cash", "equity", "limits", "fees",
                   "positions (symbol or market/leg, quantity, average_cost, mark, opened_at, reason)",
                   "open_orders (order_id, side, quantity, limit_price, filled, submitted_at)"],
    "alpaca": "bars: closed bars, oldest first, up to NEEDS.bars.limit; quotes: {bid, ask} ONLY, derived from the bar with the "
              "tape's half-spread -- there is NO quote timestamp `t` in replay, so a staleness check must treat a missing `t` as fresh",
    "kalshi": "markets: the rows the contract lists, with hours_to_close; watched symbols arrive as observed.bars only",
    "absent_in_replay": ["quotes[...].t", "recent_order_outcomes", "event_risk"],
    "rule": "Code that REQUIRES a field replay does not supply never trades on replay and cannot pass. Use such fields only when present.",
}

FOUNDRY_BRIEF = """You are Merton, the theorist of a small real-money trading league, writing NEW STRATEGY
HYPOTHESES for one desk. You do not pick trades. You write programs that the House replays on recorded
history; only a program that passes that replay is given a paper seat, and only a paper record earns
real money after an independent audit.

Why you are being asked: the House used to fill empty seats with random parameter mutations of the
programs already there. Most of them landed on desks that had never produced a live agent, on lines
that had already failed a dozen replays. Your job is to replace that with a few hypotheses that have
a REASON to work, each stated so that the evidence can reject it.

Rules.
- Write exactly `batch.candidates` candidates, each a DIFFERENT MECHANISM: a different reason the edge
  exists (who is on the other side, what structural fact pays you), not one rule with other numbers.
- Stay inside `desk`: NEEDS.venue is `desk.venue`, NEEDS.horizon is one of `desk.horizons`, and NEEDS
  names series (Kalshi) or symbols (Alpaca) from `desk.universe` only. A program whose NEEDS sit
  outside the desk is refused before it runs.
- Use only data that exists (`data`). Never assume an input listed in `data.not_supplied`. Watched
  inputs (NEEDS.observe) only where `data` says replay supplies them.
- Read `failed_on_this_desk` and `retired_on_this_desk`. Do not resubmit a failed or retired mechanism
  unless `mechanism` names the specific reason it failed and why yours is different in kind.
- Model the fees in `fees` explicitly, and state `edge_after_costs` with the arithmetic.
- It must TRADE on the replay tape: `replay_gate` needs at least min_trades closed trades and
  min_blocks blocks within `replay_window`, positive out-of-sample growth, and a deflated Sharpe at
  least min_deflated_sharpe. A program that never fires cannot pass; one that trades noise after fees
  will not either. Most replays fail: be specific rather than hopeful.
- Respect `horizon_rule` and `limits`. No shorts, no leverage; exits are always allowed.
- Read `replay_view`: replay does not supply everything a live wake does (quotes there have no
  timestamp). A program that requires a missing field never trades on replay and cannot pass.
- Follow the strategy contract below EXACTLY (imports, NEEDS, PARAMS, decide(ctx), the return shape).
  Declare custom numeric knobs in NEEDS.parameter_rules so they are valid.
- `rejection` is your public commitment: the replay or paper result that would show you were wrong.

Answer with ONE JSON object and nothing else:
{"summary": "two or three plain sentences: what you saw on this desk and what you are testing",
 "candidates": [{"name": "lowercase-words-with-dashes, under 24 characters",
                 "mechanism": "why the edge exists and who pays it",
                 "data": ["each input it requires, as NEEDS names it"],
                 "edge_after_costs": "expected edge per trade after fees and spread, with the arithmetic",
                 "horizon": "how long a position is held, and the block it is judged on",
                 "rejection": "what evidence would reject it",
                 "code": "the WHOLE strategy file"}]}"""


def normalize(text: Any) -> str:
    """The mechanism text an exact-duplicate check compares: case, spacing and punctuation removed."""
    return re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).strip()


def card_id(mechanism: Any, niche: str) -> str:
    """`hypothesis.card` id: a sha256 prefix of the normalized mechanism plus the niche (shared schema)."""
    return hashlib.sha256((normalize(mechanism) + "\n" + str(niche)).encode("utf-8")).hexdigest()[:16]


def static_needs(code: str) -> dict[str, Any] | None:
    """NEEDS read WITHOUT running the module: a literal assignment only. The House still reads the
    real NEEDS in its sealed probe box; this only picks which horizon a candidate says it trades."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "NEEDS" for t in node.targets):
            try:
                value = ast.literal_eval(node.value)
            except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
                return None
            return value if isinstance(value, dict) else None
    return None


def classify_error(error: Any) -> str:
    """`blocked_data`, `blocked_infra` or `invalid` for a candidate replay that was not a trial."""
    text = str(error or "").lower()
    if any(word in text for word in _INFRA_WORDS):
        return "blocked_infra"
    if any(word in text for word in _DATA_WORDS):
        return "blocked_data"
    return "invalid"


@dataclass(frozen=True)
class DeskScore:
    niche: str
    score: float
    replay_rate: float
    forward_rate: float
    availability: float
    trials: int
    passes: int
    earning: int
    with_record: int
    cards: int
    open_seats: int
    eligible: bool
    why: str


class Foundry:
    """Merton's hypothesis work for the House. Every decision is a ledger row; the cadence and the
    in-flight evaluations are folded from the ledger, so a restart neither repeats a paid call nor
    loses a card (`house.json` holds only throttles)."""

    def __init__(self, house: Any, frontier: Any = None):
        self.house = house
        self._frontier = frontier
        self.refusal = ""
        self._scores: tuple[float, list[DeskScore]] | None = None
        self._allocation: tuple[float, Any] | None = None
        self._memo: dict[str, tuple[int, Any]] = {}
        state = self._state()
        if "birth_cursor" not in state:
            # Label births from the moment the foundry is switched on. The earlier ones happened
            # under the old refill; relabelling them now would stamp hundreds of rows with today's
            # time and make the day's birth count (the mutation share's base) meaningless.
            with house._state_lock:
                state["birth_cursor"] = house.ledger.head()[0]

    def _folded(self, name: str, build: Any) -> Any:
        """A fold of the ledger, rebuilt only when the ledger has grown (several are read per tick)."""
        head = self.house.ledger.head()[0]
        hit = self._memo.get(name)
        if hit is not None and hit[0] == head:
            return hit[1]
        value = build()
        self._memo[name] = (head, value)
        return value

    # ------------------------------------------------------------------ dials
    @property
    def settings(self) -> dict[str, Any]:
        own = (self.house.game.get("hypotheses") or {}) if isinstance(self.house.game, Mapping) else {}
        return {**DEFAULTS, **{k: v for k, v in own.items() if not k.startswith("_")}}

    @property
    def frontier(self) -> Any:
        return self._frontier if self._frontier is not None else getattr(self.house, "frontier", None)

    def enabled(self) -> bool:
        return bool(self.settings.get("enabled"))

    def replaces_refill(self) -> bool:
        return bool(self.settings.get("enabled")) and bool(self.settings.get("replace_mutation_refill"))

    def _state(self) -> dict[str, Any]:
        with self.house._state_lock:
            return self.house._state.setdefault("hypotheses", {})

    def _now(self) -> float:
        return float(self.house.clock())

    # ------------------------------------------------------------------ folds
    def cards(self) -> dict[str, dict[str, Any]]:
        """Every card, by id, as first written (a card is written once). Code stays on the ledger
        row (`_code`, private) and is read back only when a card is replayed or born."""
        def build():
            out: dict[str, dict[str, Any]] = {}
            for entry in self.house.ledger.iter(kinds="hypothesis.card"):
                p = entry.payload
                if p.get("id") and p["id"] not in out:
                    out[p["id"]] = {**{k: v for k, v in p.items() if k != "_code"}, "_seq": entry.seq, "_at": entry.at}
            return out
        return self._folded("cards", build)

    def evaluations(self) -> dict[str, dict[str, Any]]:
        """The latest evaluation outcome of each card (`trace.record` task hypothesis.evaluate)."""
        def build():
            out: dict[str, dict[str, Any]] = {}
            for entry in self.house.ledger.iter(kinds="trace.record"):
                p = entry.payload
                if p.get("task") == TASK_EVALUATE and p.get("id"):
                    out[p["id"]] = {**p, "_seq": entry.seq, "_at": entry.at}
            return out
        return self._folded("evaluations", build)

    def born(self) -> dict[str, Agent]:
        """Card id -> the agent born from it (its `founder` is `card:<id>`)."""
        return {a.founder[5:]: a for a in self.house.registry.agents.values() if (a.founder or "").startswith("card:")}

    def calls(self) -> list[dict[str, Any]]:
        return self._folded("calls", lambda: [dict(e.payload, _at=e.at) for e in self.house.ledger.iter(kinds="merton.pass")
                                              if e.payload.get("role") == ROLE])

    def links(self) -> dict[str, set[str]]:
        """Rewording groups from `hypothesis.link` (Jev or exact), above the confidence dial. Used
        ONLY to share failure history for retirement; never for genealogy or trial counts."""
        floor = float(self.settings["link_min_confidence"])
        parent: dict[str, str] = {}

        def find(x: str) -> str:
            while parent.setdefault(x, x) != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        for entry in self.house.ledger.iter(kinds="hypothesis.link"):
            p = entry.payload
            try:
                confident = p.get("method") == "exact" or float(p.get("confidence") or 0) >= floor
            except (TypeError, ValueError):
                confident = False
            if p.get("relation") == "rewording" and confident and p.get("a") and p.get("b"):
                parent[find(str(p["a"]))] = find(str(p["b"]))
        groups: dict[str, set[str]] = {}
        for key in list(parent):
            groups.setdefault(find(key), set()).add(key)
        return {member: group for group in groups.values() for member in group}

    def retired(self) -> dict[str, dict[str, Any]]:
        """Retired ids (`family:<family>`, `line:<line>` or a card id) that still stand. A later
        pass in that family lifts any retirement; a verified repair of its key lifts a blocked one."""
        return self._folded("retired", self._retired)

    def _retired(self) -> dict[str, dict[str, Any]]:
        rows: dict[str, dict[str, Any]] = {}
        for entry in self.house.ledger.iter(kinds="hypothesis.retired"):
            rows[str(entry.payload.get("id"))] = {**entry.payload, "_seq": entry.seq}
        if not rows:
            return {}
        verified = {}
        for entry in self.house.ledger.iter(kinds="repair.status"):
            if entry.payload.get("state") == "verified":
                verified[str(entry.payload.get("key"))] = entry.seq
        passes: dict[str, int] = {}
        for entry in self.house.ledger.iter(kinds="eval.trial"):
            if entry.payload.get("passed"):
                passes[str(entry.payload.get("family"))] = entry.seq
        out = {}
        for key, row in rows.items():
            family = key[7:] if key.startswith("family:") else None
            if family is not None and passes.get(family, 0) > row["_seq"]:
                continue
            repair = ((row.get("evidence") or {}).get("repair_key") if isinstance(row.get("evidence"), dict) else None)
            if row.get("reason") != "disproven" and repair and verified.get(repair, 0) > row["_seq"]:
                continue
            out[key] = row
        return out

    def _retired_niche(self, key: str, row: Mapping[str, Any]) -> str | None:
        """The desk a retirement belongs to, whoever wrote it. The v0 refill guard writes
        `line:<line>` with a text `evidence`; this module writes `family:<family>` or a card id with
        a dict that names the niche."""
        evidence = row.get("evidence")
        if isinstance(evidence, dict) and evidence.get("niche"):
            return str(evidence["niche"])
        kind, _, name = key.partition(":")
        for agent in self.house.registry.agents.values():
            if (kind == "line" and (agent.line or agent.name) == name) or (kind == "family" and agent.family == name):
                return agent.specialty
        return (self.cards().get(key) or {}).get("niche")

    def _is_retired(self, agent: Agent, retired: Mapping[str, Any]) -> bool:
        """A family retired here, or a line retired by the House's own refill guard."""
        return f"family:{agent.family}" in retired or f"line:{agent.line or agent.name}" in retired

    def _retired_mechanisms(self, retired: Mapping[str, Any]) -> set[str]:
        """Mechanism ids the Jev hypothesis memory would give the strategies of retired families and
        lines (`league/hypothesis_memory.py`, when it is installed), so that a card linked to one of
        them as a rewording is not replayed. Without that module this is empty: exact card ids and
        card-to-card links still apply."""
        try:
            from .hypothesis_memory import docstring, mechanism_id  # type: ignore[attr-defined]
        except ImportError:
            return set()
        out = set()
        for agent in self.house.registry.agents.values():
            if self._is_retired(agent, retired):
                text = docstring(agent.code)
                if text:
                    out.add(mechanism_id(text, agent.specialty))
        return out

    # --------------------------------------------------------------- evidence
    def _niche_of_agent(self, agent_id: str, cards_by_line: Mapping[str, str]) -> str | None:
        agent = self.house.registry.get(agent_id)
        if agent is not None:
            return agent.specialty
        return cards_by_line.get(agent_id)

    def desk_scores(self, *, fresh: bool = False) -> list[DeskScore]:
        """Opportunity by evidence, best first. Cached for five minutes (standings are not free)."""
        now = self._now()
        if not fresh and self._scores is not None and now - self._scores[0] < 300:
            return self._scores[1]
        house = self.house
        settings = self.settings
        since = now_iso(lambda: now - float(settings["evidence_days"]) * 86400)
        cards = self.cards()
        by_line = {c.get("line_id"): c.get("niche") for c in cards.values() if c.get("line_id")}
        trials: dict[str, list[int]] = {}
        empty: dict[str, int] = {}
        for entry in house.ledger.iter(kinds="eval.trial"):
            if entry.at < since:
                continue
            niche = self._niche_of_agent(entry.agent, by_line)
            if not niche:
                continue
            row = trials.setdefault(niche, [0, 0])
            row[0] += 1
            row[1] += bool(entry.payload.get("passed"))
            if not entry.payload.get("passed") and int(entry.payload.get("blocks") or 0) == 0:
                empty[niche] = empty.get(niche, 0) + 1
        blocked: dict[str, int] = {}
        attempts: dict[str, int] = {}
        for card, outcome in self.evaluations().items():
            niche = (cards.get(card) or {}).get("niche")
            if not niche or outcome.get("_at", "") < since:
                continue
            attempts[niche] = attempts.get(niche, 0) + 1
            if outcome.get("outcome") in ("blocked_data", "blocked_infra"):
                blocked[niche] = blocked.get(niche, 0) + 1
        total_trials = sum(t[0] for t in trials.values())
        total_passes = sum(t[1] for t in trials.values())
        league_rate = (total_passes + 1) / (total_trials + 15)  # 6.5% measured; a fresh ledger starts near it
        standings = [s for s in house.standings()]
        earning: dict[str, int] = {}
        record: dict[str, int] = {}
        for s in standings:
            agent = house.registry.get(s.agent)
            if agent is None or not agent.specialty:
                continue
            if s.score_observations > 0:
                record[agent.specialty] = record.get(agent.specialty, 0) + 1
                if s.score_growth > 0:
                    earning[agent.specialty] = earning.get(agent.specialty, 0) + 1
        league_forward = (sum(earning.values()) + 1) / (sum(record.values()) + 2)
        living = house.registry.living()
        members: dict[str, int] = {}
        for a in living:
            if a.specialty:
                members[a.specialty] = members.get(a.specialty, 0) + 1
        cards_per_desk: dict[str, int] = {}
        for c in cards.values():
            if c.get("_at", "") >= since:
                cards_per_desk[c.get("niche")] = cards_per_desk.get(c.get("niche"), 0) + 1
        weight = float(settings["prior_weight"])
        out = []
        for niche in house.niches.values():
            t, p = trials.get(niche.id, [0, 0])
            replay_rate = (p + weight * league_rate) / (t + weight)
            n, e = record.get(niche.id, 0), earning.get(niche.id, 0)
            forward = (e + 3 * league_forward) / (n + 3)
            tried = t + attempts.get(niche.id, 0)
            bad = empty.get(niche.id, 0) + blocked.get(niche.id, 0)
            availability = (tried - bad + 1) / (tried + 1)
            seats = max(niche.max_members - members.get(niche.id, 0), 0)
            eligible = not niche.dormant and bool(niche.replay)
            score = availability * replay_rate * (0.5 + forward) if eligible else 0.0
            why = (f"replay {p}/{t} (shrunk {replay_rate:.3f}), forward earning {e}/{n} (shrunk {forward:.2f}), "
                   f"inputs present {availability:.2f}")
            if niche.dormant:
                why = "dormant: " + (niche.dormant_reason or "closed")
            elif not niche.replay:
                why = "no historical replay: the foundry cannot admit by replay here (paper is its test)"
            out.append(DeskScore(niche.id, round(score, 6), round(replay_rate, 6), round(forward, 6), round(availability, 6),
                                 t, p, e, n, cards_per_desk.get(niche.id, 0), seats, eligible, why))
        out.sort(key=lambda d: (d.eligible, d.score, -d.cards), reverse=True)
        self._scores = (now, out)
        return out

    def _seat_available(self, desk: DeskScore, weakest: dict[str | None, bool]) -> bool:
        rules = self.house.game["economy"]
        if desk.open_seats > 0 and len(self.house.registry.living()) < int(rules["max_population"]):
            return True
        # A full desk or league seats a replay passer only over its weakest eligible resident.
        # (`weakest` memoizes `_weakest` per specialty within one allocation: it reads standings.)
        key = None if desk.open_seats > 0 else desk.niche
        if key not in weakest:
            weakest[key] = self.house._weakest(rules, specialty=key) is not None
        return weakest[key]

    def allocate(self, *, fresh: bool = False) -> tuple[DeskScore, str, str] | None:
        """(desk, route, reason) for the next foundry call, or None when no desk can take a newcomer.

        route is `evidence` (the best-scored desk with a seat) or `exploration` (the eligible desk
        with the fewest recent cards, then the fewest trials), taken for at most
        `exploration_share` of the last `exploration_window` calls."""
        now = self._now()
        if not fresh and self._allocation is not None and now - self._allocation[0] < 300:
            return self._allocation[1]
        picked = self._allocate()
        self._allocation = (now, picked)
        return picked

    def _waiting_with_a_seat(self) -> bool:
        """Is a replay-passing card waiting for a seat its desk could give it now? Then the next
        refill seats it, and no new card is bought meanwhile. A card whose desk has no seat -- full
        of agents that have earned theirs -- does not hold up calls for other desks. Measured Sept
        22, 2026: one weather card passed replay at 15:50Z, the weather desk filled with young
        research candidates, and the foundry refused every call, for every desk, for two hours."""
        waiting = self.inventory()
        if not waiting:
            return False
        scores = {d.niche: d for d in self.desk_scores()}
        weakest: dict[str | None, bool] = {}
        return any(card.get("niche") in scores and self._seat_available(scores[card["niche"]], weakest) for card in waiting)

    def _allocate(self) -> tuple[DeskScore, str, str] | None:
        blocked = self._blocked_desks()
        # A desk that already has a replay-passing card waiting gets no more cards until it is seated.
        waiting = {card.get("niche") for card in self.inventory()}
        weakest: dict[str | None, bool] = {}
        desks = [d for d in self.desk_scores() if d.eligible and d.niche not in blocked and d.niche not in waiting
                 and self._seat_available(d, weakest)]
        if not desks:
            return None
        settings = self.settings
        window = [c.get("allocation") or {} for c in self.calls()[-int(settings["exploration_window"]):]]
        explored = sum(1 for a in window if a.get("route") == "exploration")
        share = float(settings["exploration_share"])
        best = desks[0]
        if share > 0 and (explored + 1) / (len(window) + 1) <= share + 1e-9:
            others = [d for d in desks if d.niche != best.niche] or desks
            pick = min(others, key=lambda d: (d.cards, d.trials, d.niche))
            return pick, "exploration", (f"exploration share: {explored} of the last {len(window)} calls explored; "
                                         f"{pick.niche} has {pick.cards} recent cards and {pick.trials} trials")
        return best, "evidence", f"highest evidence score {best.score:.4f}: {best.why}"

    def _blocked_desks(self) -> set[str]:
        """Desks with an open foundry repair report: no more cards until it is verified."""
        return self._folded("blocked", self._blocked)

    def _blocked(self) -> set[str]:
        reported = {}
        for entry in self.house.ledger.iter(kinds="repair.reported"):
            key = str(entry.payload.get("key") or "")
            if key.startswith("shared_defect:hypothesis-replay:") or key.startswith("missing_data:hypothesis-replay:"):
                reported[key] = entry.seq
        if not reported:
            return set()
        verified = {str(e.payload.get("key")): e.seq for e in self.house.ledger.iter(kinds="repair.status")
                    if e.payload.get("state") in ("verified", "rejected")}
        # A report nobody works on must not close a desk for good: after `blocked_hours` the
        # foundry may try it again, and a fresh failure reports it again.
        since = now_iso(lambda: self._now() - float(self.settings["blocked_hours"]) * 3600)
        fresh = {str(e.payload.get("key")) for e in self.house.ledger.iter(kinds="repair.reported") if e.at >= since}
        return {key.rsplit(":", 1)[1] for key, seq in reported.items() if verified.get(key, 0) < seq and key in fresh}

    # ----------------------------------------------------------------- cadence
    def spent(self) -> Decimal:
        """What the foundry has spent in its budget window (its own `merton.pass` rows)."""
        hours = float(self.settings["budget_window_hours"])
        since = now_iso(lambda: self._now() - hours * 3600)
        total = Decimal(0)
        for call in self.calls():
            if call["_at"] >= since:
                try:
                    total += Decimal(str(call.get("cost_usd") or 0))
                except ArithmeticError:
                    continue
        return total

    def last_call(self) -> float:
        """The last call's time, from the ledger and the state file (whichever is later), so neither
        a lost `house.json` nor a restart can start a paid call early."""
        calls = self.calls()
        return max(float(self._state().get("last_call") or 0), float(calls[-1].get("at_epoch") or 0) if calls else 0.0)

    def inventory(self) -> list[dict[str, Any]]:
        """Replay-passing cards waiting for a seat."""
        born = self.born()
        cards = self.cards()
        return [cards[c] for c, row in self.evaluations().items()
                if row.get("outcome") == "passed" and c in cards and c not in born]

    def pending(self) -> list[dict[str, Any]]:
        """Cards written but not yet evaluated (a restart re-queues them), inside their TTL."""
        done = self.evaluations()
        ttl = float(self.settings["card_ttl_hours"]) * 3600
        now = self._now()
        out = []
        for card in self.cards().values():
            if card["id"] in done:
                continue
            if now - float(card.get("created_epoch") or 0) > ttl:
                continue
            out.append(card)
        return out

    def _expire(self) -> None:
        """A card never evaluated within its TTL is closed as `expired`, not silently dropped."""
        done = self.evaluations()
        ttl = float(self.settings["card_ttl_hours"]) * 3600
        for card in self.cards().values():
            if card["id"] not in done and self._now() - float(card.get("created_epoch") or 0) > ttl:
                self._outcome(card, "expired", "not evaluated within its time to live")

    def due(self) -> bool:
        """Whether a paid foundry call may start now. `refusal` says why not."""
        house = self.house
        settings = self.settings
        reason = ""
        if not settings.get("enabled"):
            reason = "disabled in game.json"
        elif self.frontier is None:
            reason = "no frontier client"
        elif house.paused():
            reason = "maintenance pause"
        elif house.deploying():
            reason = "a release is being staged"
        elif self._now() - self.last_call() < float(settings["call_minutes"]) * 60:
            reason = "cadence: the last call is too recent"
        elif house.frontier_tier() not in ("all", "earned"):
            reason = f"frontier tier {house.frontier_tier()!r} pays for no code work"
        elif not house.pacer.may_spend("openai"):
            reason = "the day's OpenAI allowance is spent"
        elif self.spent() >= Decimal(str(settings["budget_usd"])):
            reason = f"the foundry's ${settings['budget_usd']} window budget is spent"
        elif self._waiting_with_a_seat():
            reason = "a replay-passing card is already waiting for a seat"
        elif self.pending() or any(k.startswith("replay:hypothesis:") and j.is_alive() for k, j in list(house._jobs.items())):
            reason = "earlier cards are still being evaluated"
        elif any(k.startswith("merton:") and k != "merton:follow" and j.is_alive() for k, j in list(house._jobs.items())):
            reason = "another Merton pass is running"
        elif self.allocate() is None:
            reason = "no seat is open on any eligible desk"
        self.refusal = reason
        return not reason

    def tick(self, *, open_for_business: bool) -> None:
        """Called from `House.tick`. Unpaid bookkeeping always; paid work only when open."""
        state = self._state()
        now = self._now()
        try:
            self.annotate_births()
            self._expire()
            if now - float(state.get("last_retire") or 0) >= 600:
                self.retire_exhausted()
                with self.house._state_lock:
                    state["last_retire"] = now
        except Exception as exc:  # noqa: BLE001 - bookkeeping must never stop a tick
            self.house.alert("warning", f"hypothesis bookkeeping failed ({type(exc).__name__}: {str(exc)[:160]})")
        if not open_for_business or not self.enabled():
            return
        if not getattr(self.house, "campaigns", None) or self.house.pacer.may_spend("sail"):
            attempts = state.setdefault("attempts", {})
            ready = []
            busy = any(k.startswith("replay:hypothesis:") and j.is_alive() for k, j in list(self.house._jobs.items()))
            for card in [] if busy else self.pending():
                count, last = attempts.get(card["id"], [0, 0])
                if now - float(last) < 600:
                    continue  # a card whose replay could not start waits ten minutes, not one tick
                if int(count) >= int(self.settings["max_evaluation_attempts"]):
                    self._outcome(card, "blocked_infra", f"its replay did not complete in {count} attempts")
                    continue
                ready.append((card["id"], int(count)))
            if ready and self.house._background("replay:hypothesis:pending", self.evaluate_all, [c for c, _ in ready]):
                with self.house._state_lock:
                    for ident, count in ready:
                        attempts[ident] = [count + 1, now]
        if self.due():
            picked = self.allocate()
            if picked is not None:
                with self.house._state_lock:
                    state["last_call"] = self._now()  # stamped at dispatch: a crash mid-call does not re-buy it at once
                self.house._background("merton:foundry", self.run, picked[0].niche, picked[1], picked[2])

    # ------------------------------------------------------------------ packet
    def packet(self, niche_id: str) -> dict[str, Any]:
        """What Merton is shown for one desk. Summaries of development replays only: no tape, no
        holdout, no other agent's code."""
        house = self.house
        niche = house.niches[niche_id]
        horizon = niche.horizons[0]
        probe = self._virtual(niche, "probe", {"venue": niche.venue, "horizon": horizon, "style": "probe",
                                              niche.key: list(niche.universe[:4])}, "", {}, family="probe")
        try:
            capabilities = house.research_capabilities(probe)
        except Exception as exc:  # noqa: BLE001 - the packet is still worth sending without it
            capabilities = {"error": f"{type(exc).__name__}: {str(exc)[:160]}"}
        coverage = self._coverage(niche)
        retired = self.retired()
        cards = self.cards()
        evaluations = self.evaluations()
        families: dict[str, dict[str, Any]] = {}
        by_line = {c.get("line_id"): c.get("niche") for c in cards.values() if c.get("line_id")}
        for entry in house.ledger.iter(kinds="eval.trial"):
            if self._niche_of_agent(entry.agent, by_line) != niche_id:
                continue
            p = entry.payload
            row = families.setdefault(str(p.get("family")), {"family": p.get("family"), "trials": 0, "passes": 0, "reasons": {}})
            row["trials"] += 1
            row["passes"] += bool(p.get("passed"))
            for reason in (p.get("reasons") or [])[:3]:
                key = re.sub(r"[-+]?\d[\d.,]*", "#", str(reason))[:90]
                row["reasons"][key] = row["reasons"].get(key, 0) + 1
        seeds = {}
        for founder in niche.founders:
            seeds[founder.get("seed")] = founder.get("why") or ""
        failed = []
        for row in sorted(families.values(), key=lambda r: -r["trials"]):
            if row["passes"]:
                continue
            failed.append({"family": row["family"], "trials": row["trials"],
                           "top_reasons": [k for k, _ in sorted(row["reasons"].items(), key=lambda kv: -kv[1])[:3]],
                           "retired": f"family:{row['family']}" in retired})
        for card in cards.values():
            outcome = evaluations.get(card["id"]) or {}
            if card.get("niche") == niche_id and outcome.get("outcome") not in (None, "passed"):
                failed.append({"card": card["id"], "name": card.get("name"), "mechanism": str(card.get("mechanism") or "")[:400],
                               "outcome": outcome.get("outcome"), "detail": str(outcome.get("detail") or "")[:240]})
        passed = [{"family": r["family"], "trials": r["trials"], "passes": r["passes"]} for r in families.values() if r["passes"]]
        deaths = [str(e.payload.get("text") or "")[:300] for e in house.ledger.read(kinds="agent.postmortem", limit=200, newest=True)
                  if (house.registry.get(e.agent) and house.registry.get(e.agent).specialty == niche_id)][-5:]
        desk_score = next((asdict(d) for d in self.desk_scores() if d.niche == niche_id), None)
        replay_days = (house.settings.kalshi_replay_days * 7 if horizon == "day" else house.settings.kalshi_replay_days) \
            if niche.venue == "kalshi" else (house.settings.replay_days * (6 if horizon == "day" else 1))
        row = CONSTITUTION["rungs"]["1"]
        return {
            "batch": {"candidates": max(3, min(int(self.settings["candidates"]), 4)), "prompt_version": PROMPT_VERSION},
            "desk": {"id": niche.id, "title": niche.title, "venue": niche.venue, "horizons": list(niche.horizons),
                     "asset_class": niche.asset_class, "universe": list(niche.universe[:24]), "brief": niche.brief[:3000],
                     "maker_fee_series": list(niche.maker_fee_series), "evidence": desk_score},
            "data": {"replay": (capabilities.get("replay") if isinstance(capabilities, dict) else None),
                     "observations": (capabilities.get("observations") if isinstance(capabilities, dict) else None),
                     "not_supplied": ((capabilities.get("observations") or {}).get("not_supplied") if isinstance(capabilities, dict) else None),
                     "recorded_coverage": coverage},
            "fees": {"kalshi_taker": "0.07 x contracts x price x (1 - price), rounded up to the cent per order",
                     "kalshi_maker": "nothing, except on the series in desk.maker_fee_series, which pay the same formula",
                     "alpaca_crypto": {"taker": 0.0025, "maker": 0.0015},
                     "alpaca_equities_and_options": "no commission; you cross the spread (replay fills market orders at the touch)",
                     "replay_fills": "market orders at the touch; resting limits fill only when a later step trades strictly through them"},
            "replay_gate": dict(CONSTITUTION["ladder"]["replay"]),
            "replay_view": REPLAY_VIEW,
            "replay_window": {"days": replay_days, "step": "Kalshi day tapes step every 30 minutes; hour tapes every 5 minutes; Alpaca at NEEDS.bars.timeframe"},
            "limits": {"stake_usd": float(row["stake_usd"]), "max_position_usd": float(row["max_position_usd"]), "max_order_usd": float(row["max_order_usd"])},
            "horizon_rule": dict(house.game.get("horizon") or {}),
            "failed_on_this_desk": failed[:16],
            "retired_on_this_desk": [{"id": k, "reason": v.get("reason"), "failures": v.get("failures")} for k, v in retired.items()
                                     if self._retired_niche(k, v) == niche_id][:16],
            "passed_on_this_desk": passed[:8],
            "founder_ideas": seeds,
            "recent_postmortems": deaths,
        }

    def _coverage(self, niche: Any) -> dict[str, Any] | None:
        """What the newest `data.coverage` row (the history ingestion) says it holds for this desk's
        universe: counts and date ranges only, never the data."""
        rows = self.house.ledger.read(kinds="data.coverage", limit=3, newest=True)
        if not rows:
            return None
        latest = rows[-1].payload
        universe = {str(x).upper() for x in niche.universe}
        series = [{k: item.get(k) for k in ("kind", "symbol", "timeframe", "feed", "rows", "first_day", "last_day", "empty", "done")}
                  for item in (latest.get("series") or []) if isinstance(item, dict) and str(item.get("symbol") or "").upper() in universe]
        return {"source": latest.get("source"), "status": latest.get("status"), "finished_at": latest.get("finished_at"),
                "series": series[:24], "limitations": list(latest.get("limitations") or [])[:8], "states": latest.get("states"),
                "note": "Ingested history in the House's store. The replay window in `data.replay` is what a candidate is judged on."}

    # -------------------------------------------------------------------- call
    def run(self, niche_id: str, route: str = "evidence", reason: str = "") -> dict[str, Any]:
        """One paid foundry call for one desk. Never raises: a failed call is a row that says why."""
        from .frontier import FrontierError
        from .house import CONTRACT_PATH

        house = self.house
        settings = self.settings
        packet = self.packet(niche_id)
        system = FOUNDRY_BRIEF + "\n\nTHE STRATEGY CONTRACT\n\n" + CONTRACT_PATH.read_text(encoding="utf-8")
        user = json.dumps(packet, default=str, sort_keys=True)
        inputs = hashlib.sha256((system + "\n" + user).encode("utf-8")).hexdigest()
        call = f"foundry:{inputs[:12]}:{int(self._now())}"
        allocation = {"desk": niche_id, "route": route, "reason": reason[:500]}
        answer = None
        try:
            answer = self.frontier.ask(system=system, user=user, agent="merton-foundry",
                                       max_output_tokens=int(settings["max_output_tokens"]), effort=str(settings["effort"]))
            parsed = answer.json()
        except FrontierError as exc:
            cost = format(answer.cost_usd, "f") if answer is not None else "0"
            house.ledger.append("merton.pass", {"role": ROLE, "at_epoch": self._now(), "summary": f"the foundry call failed: {str(exc)[:200]}",
                                                "cost_usd": cost, "files": 0, "error": True, "call": call, "allocation": allocation})
            house.ledger.append("trace.record", {"task": TASK_CALL, "id": call, "version": PROMPT_VERSION, "model": getattr(self.frontier, "model", None),
                                                 "inputs_sha256": inputs, "outcome": "error", "cost_usd": cost, "useful": False})
            return {"call": call, "error": str(exc)}
        listed = parsed.get("candidates") if isinstance(parsed.get("candidates"), list) else []
        written, refused = [], []
        known = self.cards()
        retired = self.retired()
        links = self.links()
        for index, raw in enumerate(listed[:4]):
            card, problem = self._card(raw, niche_id, call, answer, known, retired, links)
            if card is None:
                refused.append(problem)
                continue
            written.append(card)
        cost = format(answer.cost_usd, "f")
        summary = (f"{len(written)} hypothesis cards for {niche_id} ({route}); "
                   + (f"{len(refused)} refused before replay; " if refused else "") + str(parsed.get("summary") or "")[:600])
        house.ledger.append("merton.pass", {"role": ROLE, "at_epoch": self._now(), "summary": summary[:1500], "cost_usd": cost,
                                            "files": 0, "cards": [c["id"] for c in written], "refused": [str(r)[:200] for r in refused][:6],
                                            "call": call, "allocation": allocation, "cost_verified": bool(getattr(answer, "cost_verified", True))})
        house.ledger.append("trace.record", {"task": TASK_CALL, "id": call, "version": PROMPT_VERSION, "model": answer.model,
                                             "inputs_sha256": inputs, "outcome": f"{len(written)} cards, {len(refused)} refused",
                                             "cost_usd": cost, "useful": bool(written)})
        # One card after another, in one replay-lane job: the batch must not take every replay slot
        # from the agents, and the sealed probe box reads one module at a time.
        house._background(f"replay:hypothesis:{call}", self.evaluate_all, [c["id"] for c in written])
        return {"call": call, "cards": [c["id"] for c in written], "refused": refused, "cost_usd": cost}

    def _card(self, raw: Any, niche_id: str, call: str, answer: Any, known: Mapping[str, Any],
              retired: Mapping[str, Any], links: Mapping[str, set[str]]) -> tuple[dict[str, Any] | None, str]:
        """Record one candidate as a card, or say why it was refused before any replay."""
        from .safety import CodeRefused, check_code

        if not isinstance(raw, dict):
            return None, "a candidate that was not an object"
        mechanism = str(raw.get("mechanism") or "").strip()
        code = str(raw.get("code") or "")
        if not mechanism or not code.strip():
            return None, "a candidate without a mechanism or code"
        ident = card_id(mechanism, niche_id)
        if ident in known:
            return None, f"{ident}: this exact mechanism already has a card on this desk"
        group = links.get(ident, {ident})
        if any(member in retired for member in group) or group & self._retired_mechanisms(retired):
            return None, f"{ident}: a retired mechanism (or a rewording of one)"
        name = re.sub(r"[^a-z0-9-]+", "-", str(raw.get("name") or "hypothesis").lower()).strip("-")[:20] or "hypothesis"
        niche = self.house.niches[niche_id]
        desk = niche.desk or niche_id.split("-", 1)[-1]
        line = f"{desk}-h{ident[:6]}"[:34]
        family = f"{niche_id.split('-', 1)[-1]}-{name}"[:40]
        if family in self._families():
            family = f"{family[:34]}-{ident[:5]}"  # a card is its own line: never pooled with an older family by a name clash
        payload = {
            "id": ident, "mechanism": mechanism[:2000], "data": [str(x)[:120] for x in (raw.get("data") or [])][:12]
            if isinstance(raw.get("data"), list) else [str(raw.get("data") or "")[:400]],
            "edge_after_costs": str(raw.get("edge_after_costs") or "")[:800], "horizon": str(raw.get("horizon") or "")[:300],
            "rejection": str(raw.get("rejection") or "")[:800], "niche": niche_id, "venue": niche.venue,
            "author": "merton", "lineage": [line], "parent_card": None, "created_for": call,
            "name": name, "line_id": line, "family": family, "created_epoch": self._now(),
            "model": getattr(answer, "model", None), "prompt_version": PROMPT_VERSION,
            "code_sha256": hashlib.sha256(code.encode("utf-8")).hexdigest(), "_code": code,
        }
        self.house.ledger.append("hypothesis.card", payload, id=f"hypothesis.card:{ident}")
        try:
            check_code(code)
        except (CodeRefused, SyntaxError) as exc:
            self._outcome(payload, "invalid", f"the strategy check refused it: {str(exc)[:200]}")
        return payload, ""

    # --------------------------------------------------------------- evaluate
    def _virtual(self, niche: Any, line: str, needs: Mapping[str, Any], code: str, params: Mapping[str, Any], *, family: str) -> Agent:
        """The card's line as the House's candidate replay needs to see it: the id its child will
        carry (so the counted trial is in that child's lineage), the desk's specialty, no parent."""
        try:
            venue, horizon, style = niche_of(needs)
        except ValueError:
            venue, horizon, style = niche.venue, niche.horizons[0], "hypothesis"
        return Agent(id=line, name=line, family=family, venue=venue, horizon=horizon, style=style, generation=1, parent=None,
                     code=code, params=dict(params or {}), wake_minutes=15, born_at=now_iso(self.house.clock),
                     needs=dict(needs), specialty=niche.id, line=line, founder=None)

    def _outcome(self, card: Mapping[str, Any], outcome: str, detail: str, **extra: Any) -> None:
        """A card's one evaluation outcome. The first one written stands: a replay that finishes
        after its card was given up on (or the reverse) must not fight over the row."""
        from .ledger import LedgerConflict

        key = f"hypothesis.evaluate:{card['id']}"
        if self.house.ledger.get(key) is not None:
            return
        try:
            self._append_outcome(card, outcome, detail, key, **extra)
        except LedgerConflict:
            pass

    def _append_outcome(self, card: Mapping[str, Any], outcome: str, detail: str, key: str, **extra: Any) -> None:
        self.house.ledger.append("trace.record", {"task": TASK_EVALUATE, "id": card["id"], "version": PROMPT_VERSION,
                                                  "model": card.get("model"), "inputs_sha256": card.get("code_sha256"),
                                                  "outcome": outcome, "cost_usd": "0", "useful": outcome == "passed",
                                                  "detail": str(detail)[:600], "niche": card.get("niche"), "line_id": card.get("line_id"),
                                                  **extra}, id=key)

    def evaluate_all(self, idents: Sequence[str]) -> None:
        for ident in idents:
            if self.house._closing.is_set():
                return
            self.evaluate(ident)

    def evaluate(self, ident: str) -> dict[str, Any] | None:
        """Replay one card through the House's candidate replay. Passed, failed (a counted trial),
        invalid, blocked_data or blocked_infra; a closed allowance leaves it pending."""
        house = self.house
        card = self.cards().get(ident)
        if card is None or ident in self.evaluations():
            return None
        niche = house.niches.get(card["niche"])
        if niche is None or niche.dormant or not niche.replay:
            self._outcome(card, "invalid", "its desk is closed or has no replay")
            return None
        retired = self.retired()
        group = self.links().get(ident, {ident})
        closed = set(retired) | self._retired_mechanisms(retired)
        if closed & group:
            self._outcome(card, "retired_mechanism", "linked as a rewording of a retired mechanism before its replay: "
                          + ", ".join(sorted(closed & group))[:300])
            return None
        code = self._code(card)
        needs = static_needs(code) or {"venue": niche.venue, "horizon": niche.horizons[0]}
        agent = self._virtual(niche, card["line_id"], needs, code, {}, family=card["family"])
        if agent.venue != niche.venue or agent.horizon not in niche.horizons:
            self._outcome(card, "invalid", f"its NEEDS say {agent.venue}/{agent.horizon}, outside the {niche.id} desk")
            return None
        declared = static_needs(code)
        if declared is not None:
            # The House would show a strategy that names nothing on its desk the head of the desk's
            # universe instead (`niches.constrain`), and replay a program that was never about those
            # markets: a counted trial that tests nothing. Refuse it before the replay instead.
            from . import niches as niches_module
            try:
                home = niches_module.match(declared, house.niches)
            except Exception:  # noqa: BLE001 - an odd literal is the probe's to judge
                home = niche
            if home is None or home.id != niche.id:
                where = f"the {home.id} desk" if home is not None else f"nothing in the {niche.id} universe"
                self._outcome(card, "invalid", f"its NEEDS name {where}; a card must trade its own desk's markets")
                return None
        result = house._candidate_replay(agent, code)
        if not result.get("passed"):
            try:
                house.sandbox.retire(agent.id)  # its replay box: only a passer's child will use it
            except Exception:  # noqa: BLE001 - a box already gone is a box gone
                pass
        numbers = result.get("numbers") or {}
        if result.get("counted_as_trial"):
            outcome = "passed" if result.get("passed") else "failed"
            detail = "; ".join(str(r) for r in (numbers.get("reasons") or [])[:3]) or "passed every replay gate"
            self._outcome(card, outcome, detail, trial={k: numbers.get(k) for k in ("trades", "blocks", "sharpe", "deflated_sharpe", "trials", "passed")},
                          needs=result.get("needs"), params=result.get("params"))
            return result
        error = str(result.get("error") or "")
        if "allowance is closed" in error or "allowance" in error and "unavailable" in error:
            with house._state_lock:  # not the card's fault: it stays pending, and this try is not counted
                row = self._state().setdefault("attempts", {}).get(ident)
                if row:
                    row[0] = max(int(row[0]) - 1, 0)
            return result
        self._outcome(card, classify_error(error), error or "the replay did not run")
        return result

    def _families(self) -> set[str]:
        return self._folded("families", lambda: {a.family for a in self.house.registry.agents.values()}
                            | {str(e.payload.get("family")) for e in self.house.ledger.iter(kinds="eval.trial")}
                            | {str(c.get("family")) for c in self.cards().values()})

    def _code(self, card: Mapping[str, Any]) -> str:
        entry = self.house.ledger.get(f"hypothesis.card:{card['id']}")
        return str((entry.payload if entry else card).get("_code") or "")

    # ------------------------------------------------------------------ refill
    def refill(self, rules: Mapping[str, Any], *, living: Sequence[Agent], loser: Agent | None) -> Agent | None:
        """The newcomer, when routine refill is the foundry's: a replay-passing card first (best desk
        evidence first), else an evidence-driven mutation inside its share, else nobody."""
        child = self._admit(rules, living=living, loser=loser)
        if child is None:
            child = self._evidence_mutation(rules, living=living, loser=loser)
        if child is not None:
            with self.house._state_lock:
                self.house._state.setdefault("last_newcomer", {})["at"] = self._now()
        return child

    def _admit(self, rules: Mapping[str, Any], *, living: Sequence[Agent], loser: Agent | None) -> Agent | None:
        house = self.house
        waiting = self.inventory()
        if not waiting:
            return None
        rank = {d.niche: (d.score, d) for d in self.desk_scores()}
        retired = self.retired()
        waiting.sort(key=lambda c: (-(rank.get(c["niche"], (0.0, None))[0]), c["_seq"]))
        members = {}
        for a in living:
            members[a.specialty] = members.get(a.specialty, 0) + 1
        for card in waiting:
            niche = house.niches.get(card["niche"])
            if niche is None or niche.dormant or f"family:{card['family']}" in retired or f"line:{card['line_id']}" in retired:
                continue
            evaluation = self.evaluations()[card["id"]]
            displaced = loser
            if members.get(niche.id, 0) >= niche.max_members:
                # A full desk makes room from its own weakest (which also frees a full league's seat).
                displaced = house._weakest(rules, specialty=niche.id)
                if displaced is None:
                    continue  # this desk is full of agents that have earned their seats
            code = self._code(card)
            desk = rank.get(niche.id, (0.0, None))[1]
            why = (f"hypothesis card {card['id']} (Merton, foundry {card.get('created_for')}): {str(card.get('mechanism'))[:220]} "
                   f"-- passed replay before birth ({evaluation.get('detail')}); desk evidence {desk.why if desk else 'unscored'}")
            try:
                child = house.spawn(card["line_id"], card["family"], code, reason=why[:1500], params=evaluation.get("params") or {},
                                    endowment=rules["endowment_usd"], specialty=niche.id, founder=f"card:{card['id']}")
            except ValueError as exc:
                self._outcome_admission(card, "refused_at_birth", str(exc))
                continue
            seated = child.id == card["line_id"] and child.code_sha256 == card.get("code_sha256") \
                and (evaluation.get("needs") is None or child.needs == evaluation.get("needs"))
            if seated:
                house.evaluator.seat(child.id, 1, f"its hypothesis card {card['id']} passed replay before birth, on its own line")
                with house._state_lock:
                    house._state["tried"][child.id] = child.code_sha256
                house.seat(child)
            if displaced is not None and displaced.alive:
                house.kill(displaced, "displaced", house.postmortem(displaced, "displaced",
                           "a replay-passing hypothesis card takes the seat of the weakest eligible agent"))
            self.record_birth(child, "hypothesis", f"a replay-passing hypothesis card for {niche.id}", {
                "card": card["id"], "desk_score": desk.score if desk else None, "desk_evidence": desk.why if desk else None,
                "replay_passed": True, "seated_on_paper": seated, "displaced": displaced.id if displaced else None,
                "allocation": self._allocation_of(card)})
            return child
        return None

    def _outcome_admission(self, card: Mapping[str, Any], status: str, detail: str) -> None:
        self.house.ledger.append("route.decision", {"task": f"admission:{card['id']}", "route": status, "model": None,
                                                    "reason": str(detail)[:400], "evidence": {"card": card["id"], "niche": card.get("niche")}},
                                 id=f"hypothesis.admission:{card['id']}:{status}")

    def _allocation_of(self, card: Mapping[str, Any]) -> dict[str, Any] | None:
        for call in self.calls():
            if call.get("call") == card.get("created_for"):
                return call.get("allocation")
        return None

    def _mutations_allowed(self) -> bool:
        """Evidence-driven mutations stay a bounded share of the day's births."""
        since = now_iso(lambda: self._now() - 86400)
        births = mutations = 0
        for entry in self.house.ledger.iter(kinds="agent.born"):
            if entry.at < since:
                continue
            births += 1
            route = self.house.ledger.get(f"birth-route:{entry.agent}")
            mutations += bool(route is not None and route.payload.get("route") == "evidence_mutation")
        cap = max(int(self.settings["mutation_min_per_day"]), int(float(self.settings["mutation_share"]) * births))
        return mutations < cap

    def _evidence_mutation(self, rules: Mapping[str, Any], *, living: Sequence[Agent], loser: Agent | None) -> Agent | None:
        house = self.house
        state = self._state()
        now = self._now()
        if now - float(state.get("last_mutation_look") or 0) < 600:
            return None  # standings are not free; a refill that found nobody waits ten minutes
        with house._state_lock:
            state["last_mutation_look"] = now
        if not self._mutations_allowed():
            return None
        retired = self.retired()
        rank = {d.niche: d for d in self.desk_scores()}
        members = {}
        for a in living:
            members[a.specialty] = members.get(a.specialty, 0) + 1
        candidates = []
        for s in house.standings():
            agent = house.registry.get(s.agent)
            if agent is None or not agent.alive or (loser is not None and agent.id == loser.id):
                continue
            if not (s.score_observations > 0 and s.score_growth > 0):
                continue  # positive forward evidence, or no House-staked child
            if self._is_retired(agent, retired):
                continue  # an exhausted mechanism is not bred, however well one of its members trades
            niche = house.niche_of(agent)
            if niche is None or niche.dormant or members.get(niche.id, 0) >= niche.max_members:
                continue
            desk = rank.get(niche.id)
            candidates.append(((desk.score if desk else 0.0), s.score_growth, agent, s, desk))
        candidates.sort(key=lambda row: (row[0], row[1]), reverse=True)
        for _, growth, parent, standing, desk in candidates:
            params = house._mutated_params(parent, seed=f"newcomer:{len(house.registry.agents)}")
            if params is None:
                continue
            child = house.spawn(parent.line or parent.name, parent.family, parent.code, parent=parent.id, endowment=rules["endowment_usd"], params=params,
                                reason=(f"an evidence-driven House mutation of {parent.id}: it is earning forward "
                                        f"(growth {growth:+.5f} over {standing.score_observations} observations) on {parent.specialty}"))
            house.ledger.append("agent.forked", {"child": child.id, "endowment_usd": rules["endowment_usd"], "box_forked": False,
                                                 "reason": "evidence", "new_code": False}, agent=parent.id)
            if loser is not None and loser.alive:
                house.kill(loser, "displaced", house.postmortem(loser, "displaced",
                           "the league was full and an evidence-driven newcomer replaces its weakest eligible agent"))
            self.record_birth(child, "evidence_mutation", f"a House mutation of {parent.id}, which is earning forward", {
                "parent": parent.id, "parent_growth": growth, "parent_observations": standing.score_observations,
                "desk_score": desk.score if desk else None, "replay_passed": False, "starts_on_rung": 0,
                "displaced": loser.id if loser else None})
            return child
        return None

    # --------------------------------------------------------- birth reasons
    def record_birth(self, child: Agent, route: str, reason: str, evidence: Mapping[str, Any]) -> None:
        """The allocation reason and evidence status of one birth (`route.decision`, once each)."""
        key = f"birth-route:{child.id}"
        if self.house.ledger.get(key) is None:
            self.house.ledger.append("route.decision", {"task": f"birth:{child.id}", "route": route, "model": None,
                                                        "reason": reason[:600], "evidence": dict(evidence)}, id=key)

    def annotate_births(self) -> int:
        """Label every birth the foundry did not make itself with why it happened and what evidence
        stood behind it, so the deliberate exceptions stay explicit on the ledger."""
        house = self.house
        state = self._state()
        cursor = int(state.get("birth_cursor") or 0)
        added = 0
        founder_keys = {f.get("key") for n in house.niches.values() for f in n.founders}
        last = cursor
        for entry in house.ledger.iter(kinds="agent.born", after=cursor):
            last = entry.seq
            if house.ledger.get(f"birth-route:{entry.agent}") is not None:
                continue
            p = entry.payload
            reason = str(p.get("reason") or "")
            parent = p.get("parent")
            if str(p.get("founder") or "").startswith("card:"):
                route, why, evidence = "hypothesis", "a hypothesis card's child (its admission row was not written)", {"card": p["founder"][5:]}
            elif parent is None and p.get("founder") in founder_keys:
                route, why, evidence = "founder", "a founding seed: starts on paper without a replay pass (deliberate exception); its replay still runs and counts", \
                    {"exception": "founder_paper_start", "replay_passed": False}
            elif parent is None:
                route, why, evidence = "architect", "an architect's merged strategy: born on rung 0 and must pass replay", {"replay_passed": False, "starts_on_rung": 0}
            elif reason.startswith("a House-staked valid mutation"):
                route, why, evidence = "legacy_mutation", "a House-staked parameter mutation placed by open seats (the refill the foundry replaces)", \
                    {"replay_passed": False, "starts_on_rung": 0}
            elif reason.startswith("an evidence-driven House mutation"):
                route, why, evidence = "evidence_mutation", reason[:300], {"parent": parent, "replay_passed": False, "starts_on_rung": 0}
            else:
                forked = next((e.payload for e in house.ledger.iter(kinds="agent.forked", agent=parent) if e.payload.get("child") == entry.agent), {})
                if forked.get("new_code"):
                    route, why = "candidate", "a research candidate whose code passed replay as its parent's candidate: a versioned child on its own record"
                    evidence = {"replay_passed": True, "staked_by": forked.get("staked_by"), "parent": parent}
                else:
                    route, why = "earner_fork", "a parameter fork paid for by a parent that earned its credits (deliberate exception); the child must pass replay"
                    evidence = {"replay_passed": False, "starts_on_rung": 0, "parent": parent,
                                "parent_rung": house.evaluator.rung(parent) if parent else None}
            house.ledger.append("route.decision", {"task": f"birth:{entry.agent}", "route": route, "model": None,
                                                   "reason": why, "evidence": evidence}, id=f"birth-route:{entry.agent}")
            added += 1
        with house._state_lock:
            state["birth_cursor"] = last
        return added

    # ------------------------------------------------------------ retirement
    def retire_exhausted(self) -> list[dict[str, Any]]:
        """Stop breeding what the evidence has closed. Returns the rows written this pass."""
        house = self.house
        settings = self.settings
        limit = int(settings["retire_after_failures"])
        already = self.retired()
        cards = self.cards()
        by_line = {c.get("line_id"): c.get("niche") for c in cards.values() if c.get("line_id")}
        families: dict[str, dict[str, Any]] = {}
        for entry in house.ledger.iter(kinds="eval.trial"):
            p = entry.payload
            family = str(p.get("family") or "")
            if not family:
                continue
            row = families.setdefault(family, {"failures": 0, "passes": 0, "empty": 0, "agents": set(), "niche": None, "evidence": []})
            row["agents"].add(entry.agent)
            row["niche"] = row["niche"] or self._niche_of_agent(entry.agent, by_line)
            if p.get("passed"):
                row["passes"] += 1
                continue
            row["failures"] += 1
            if int(p.get("blocks") or 0) == 0:
                row["empty"] += 1
            row["evidence"] = (row["evidence"] + [{"seq": entry.seq, "at": entry.at, "agent": entry.agent,
                                                   "excerpt": "; ".join(str(r) for r in (p.get("reasons") or [])[:2])[:240]}])[-5:]
        written = []
        for family, row in families.items():
            key = f"family:{family}"
            if key in already or row["passes"] or row["failures"] < limit:
                continue
            blocked = row["empty"] / row["failures"] >= float(settings["blocked_share"])
            reason = "blocked_data" if blocked else "disproven"
            repair_key = f"missing_data:replay-tape:{row['niche']}:{family}" if blocked else None
            payload = {"id": key, "reason": reason, "failures": row["failures"],
                       "evidence": {"family": family, "niche": row["niche"], "passes": 0, "empty_tape_failures": row["empty"],
                                    "agents": sorted(row["agents"])[:24], "last": row["evidence"], "repair_key": repair_key,
                                    "rule": f"{limit} counted replay failures with no pass"}}
            house.ledger.append("hypothesis.retired", payload, id=f"hypothesis.retired:{key}:{row['failures']}")
            written.append(payload)
            if blocked:
                self._report(repair_key, "missing_data",
                             f"the {family} family on {row['niche']} failed {row['empty']} of {row['failures']} replays on an empty tape: "
                             "its inputs are missing, so it is retired from breeding until the data exists",
                             row["evidence"], sorted(row["agents"]), "medium")
        written.extend(self._retire_unrunnable(families, already))
        written.extend(self._retire_cards(cards, already, limit))
        written.extend(self._report_blocked_cards(cards))
        return written

    def _retire_unrunnable(self, families: Mapping[str, Mapping[str, Any]], already: Mapping[str, Any]) -> list[dict[str, Any]]:
        """Lines whose replays mostly cannot RUN. Those are not trials, so the failure count above
        never sees them, and a mutation of such a line buys another replay that will not run. The
        House says so in its alerts (`<agent>: replay could not run (...)`, `... was not run (...)`);
        a family with `infra_failures` of them in distinct hours, at least as many as its counted
        trials and no pass, is retired `blocked_data` (a missing input) or `blocked_infra` (the box,
        a timeout, a crash), and reported for repair instead of being bred."""
        house = self.house
        since = now_iso(lambda: self._now() - float(self.settings["evidence_days"]) * 86400)
        pattern = re.compile(r"^([a-z][a-z0-9-]{1,40}): (?:replay could not run|its replay was not run|a candidate's replay was not run) \((.*)")
        seen: dict[str, dict[str, Any]] = {}
        for entry in house.ledger.iter(kinds="ops.alert"):
            if entry.at < since:
                continue
            match = pattern.match(str(entry.payload.get("text") or ""))
            if not match:
                continue
            agent = house.registry.get(match.group(1))
            detail = match.group(2)
            if agent is None or "allowance" in detail:
                continue  # a closed budget is the owner's line, not the strategy's
            kind = "blocked_data" if classify_error(detail) == "blocked_data" or "unsupported input" in detail.lower() else "blocked_infra"
            row = seen.setdefault(agent.family, {"hours": {"blocked_data": set(), "blocked_infra": set()}, "niche": agent.specialty,
                                                 "agents": set(), "evidence": []})
            key = (agent.id, entry.at[:13])
            if key in row["hours"][kind]:
                continue
            row["hours"][kind].add(key)
            row["agents"].add(agent.id)
            row["evidence"] = (row["evidence"] + [{"seq": entry.seq, "at": entry.at, "agent": agent.id, "excerpt": detail[:240]}])[-5:]
        written = []
        floor = int(self.settings["infra_failures"])
        for family, row in seen.items():
            counted = families.get(family) or {}
            if f"family:{family}" in already or counted.get("passes"):
                continue
            kind = max(row["hours"], key=lambda k: len(row["hours"][k]))
            failures = len(row["hours"][kind])
            if failures < floor or failures < int(counted.get("failures") or 0):
                continue
            repair_key = (f"missing_data:replay-input:{row['niche']}:{family}" if kind == "blocked_data"
                          else f"shared_defect:replay-harness:{row['niche']}:{family}")
            payload = {"id": f"family:{family}", "reason": kind, "failures": failures,
                       "evidence": {"family": family, "niche": row["niche"], "counted_failures": int(counted.get("failures") or 0),
                                    "agents": sorted(row["agents"])[:24], "last": row["evidence"], "repair_key": repair_key,
                                    "rule": f"{floor} replays that could not run, in distinct hours, and no pass"}}
            house.ledger.append("hypothesis.retired", payload, id=f"hypothesis.retired:family:{family}:{kind}:{failures}")
            written.append(payload)
            self._report(repair_key, "missing_data" if kind == "blocked_data" else "shared_defect",
                         f"the {family} family on {row['niche']} could not replay {failures} times "
                         + ("for a missing input" if kind == "blocked_data" else "because the replay harness failed")
                         + "; it is retired from breeding until the repair is verified",
                         row["evidence"], sorted(row["agents"]), "medium")
        return written

    def _retire_cards(self, cards: Mapping[str, Any], already: Mapping[str, Any], limit: int) -> list[dict[str, Any]]:
        """Rewordings share failure history: a group of linked cards with `limit` failures and no pass
        is retired as one mechanism. The trial counts themselves are untouched."""
        links = self.links()
        evaluations = self.evaluations()
        done, written = set(), []
        for ident in cards:
            group = links.get(ident)
            if not group or ident in done:
                continue
            done |= group
            outcomes = [evaluations.get(m, {}).get("outcome") for m in group]
            failures = sum(o == "failed" for o in outcomes)
            if "passed" in outcomes or failures < limit:
                continue
            for member in sorted(group):
                if member in already or member not in cards:
                    continue
                payload = {"id": member, "reason": "disproven", "failures": failures,
                           "evidence": {"niche": cards[member].get("niche"), "group": sorted(group), "method": "hypothesis.link rewording",
                                        "note": "failure history shared across rewordings; genealogy and trial counts are unchanged"}}
                self.house.ledger.append("hypothesis.retired", payload, id=f"hypothesis.retired:{member}:{failures}")
                written.append(payload)
        return written

    def _report_blocked_cards(self, cards: Mapping[str, Any]) -> list[dict[str, Any]]:
        """A desk whose cards keep failing to RUN is a repair, not a reason to write more cards."""
        threshold = int(self.settings["repair_after_blocked"])
        rows: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for ident, outcome in self.evaluations().items():
            kind = outcome.get("outcome")
            if kind not in ("blocked_data", "blocked_infra"):
                continue
            niche = (cards.get(ident) or {}).get("niche") or outcome.get("niche")
            rows.setdefault((str(kind), str(niche)), []).append(
                {"seq": outcome["_seq"], "at": outcome["_at"], "agent": outcome.get("line_id") or ident,
                 "excerpt": str(outcome.get("detail") or "")[:240]})
        written = []
        for (kind, niche), evidence in rows.items():
            if len(evidence) < threshold:
                continue
            key = f"{'missing_data' if kind == 'blocked_data' else 'shared_defect'}:hypothesis-replay:{niche}"
            summary = (f"{len(evidence)} hypothesis cards for {niche} could not be replayed "
                       + ("because inputs were missing" if kind == "blocked_data" else "because the replay harness failed")
                       + "; the foundry writes no more cards for this desk until the repair is verified")
            if self._report(key, "missing_data" if kind == "blocked_data" else "shared_defect", summary, evidence[-5:],
                            [e["agent"] for e in evidence][-12:], "high", bucket=len(evidence) // threshold):
                written.append({"key": key})
        return written

    def _report(self, key: str, kind: str, summary: str, evidence: Sequence[Mapping[str, Any]], agents: Sequence[str],
                severity: str, *, bucket: int = 1) -> bool:
        ident = f"repair.reported:{key}:{bucket}"
        if self.house.ledger.get(ident) is not None:
            return False
        self.house.ledger.append("repair.reported", {"key": key, "kind": kind, "summary": summary[:800], "evidence": list(evidence),
                                                     "agents": list(agents), "source": "triage", "severity": severity}, id=ident)
        return True

    # ------------------------------------------------------------------ health
    def stats(self) -> dict[str, Any]:
        try:
            return self._stats()
        except Exception as exc:  # noqa: BLE001 - health must be written whatever this says
            return {"error": f"{type(exc).__name__}: {str(exc)[:160]}"}

    def _stats(self) -> dict[str, Any]:
        evaluations = self.evaluations()
        outcomes: dict[str, int] = {}
        for row in evaluations.values():
            outcomes[str(row.get("outcome"))] = outcomes.get(str(row.get("outcome")), 0) + 1
        return {"enabled": self.enabled(), "replaces_refill": self.replaces_refill(), "refusal": self.refusal,
                "cards": len(self.cards()), "outcomes": outcomes, "waiting_for_seat": len(self.inventory()),
                "pending": len(self.pending()), "spent_window_usd": format(self.spent(), "f"),
                "budget_usd": str(self.settings["budget_usd"]), "retired": len(self.retired())}
