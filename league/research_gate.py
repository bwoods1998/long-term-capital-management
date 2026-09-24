"""Research gating: wake an expensive researcher when something relevant changed, back off no-ops.

Measured on the production ledger, Sept 19-22, 2026 (7,370 research sessions, $160):

- 6,531 sessions (88.6%) ended with no candidate and no replay -- "no credits are worth spending
  now", "spend no credits", "the market is closed", "the feed remains not_supplied". 489 (6.6%)
  retained a candidate (most of them failing replay); 325 were provider failures; median session
  cost $0.016.
- Abstention predicts abstention. After one abstaining session the next retained a candidate 11%
  of the time; after two, 7%; after three, 6%; after five or more, 3.3% (147 of 4,513).
- Most abstentions rediscovered a blocker nothing had changed: a closed session, an empty Kalshi
  window, a data feed the House does not have, an open paper position waiting to settle.
- Replayed offline over those sessions on the v0 dials (scripts/jev_lab_eval/gate_replay.py),
  these rules would have skipped 4,978 sessions ($87 of $160); 146 of the skipped (2.9%) had
  retained a candidate, most of which fail replay.

So the gate sits in `House._gate` (the overnight v0 gate, whose dials it shares), AFTER every
existing check (budget, pause, credits, durable jobs, the refusal fast path) has run and the clock
says the session is due. It can only SKIP a clock-due session; it never makes research more
frequent than the clock already allows.

1. **Deterministic triggers since the agent's last research** always run: its own fills and
   settlements, new `book.refused`, a code or rung change, a material `eval.verdict` (not the
   routine `look`/`progress` reads, which arrive every mark), a `tool.fulfilled` for something its
   line asked for, new credits, a commons note in its niche by another agent, a change in market
   availability (open/closed; a Kalshi window became non-empty) and a blocker that lifted.
2. **Nothing changed and the last session did something**: run (the clock decides, as before).
3. **Nothing changed and it abstained**: back off on the overnight v0 dials (game.json
   `research.gate`): from `after` empty passes in a row the interval doubles per further empty
   pass, up to `max_factor`. A known blocker (missing data, a closed market) the latest pass ran
   into waits until the blocker changes. `max_skip_hours` is a heartbeat: no agent is frozen.
4. **Jev** answers exactly one semantic question before a skip: "does this new note or lesson from
   outside your niche matter to your strategy?" Cached by (note id, strategy sha), 16 notes a
   request, and anything above `relevance_run_threshold` (uncertain included) runs. If Jev is
   down or capped the decision is the deterministic one.
5. **Sampling.** `sample_percent` of would-be skips run anyway (`decision: sample`, `sampled: true`,
   chosen by a hash of agent, window and slot, so a restart does not re-roll it),
   so the gate's miss rate is measured, not assumed: a miss is a sampled session that retained a
   candidate or was adopted (`report`).

6. **The clock alone buys nothing** (Sept 23, 2026, the learn-and-unblock run). Measured on the
   production ledger 00:00Z Sept 22 to 16:28Z Sept 23: 90.3% of 7,532 sessions abstained (rung 0:
   95.5%), abstentions cost $112.80 of the $147.44 research spend (about $82 a day), and 41% of
   the gate's runs were `clock` or `backoff_elapsed` -- not new evidence. Half the hand-read
   abstentions said "nothing changed, waiting for settlements". So with `clock_runs` at
   `winners_and_idle` a session is due only on a trigger (a fill, settlement, refusal, active
   block, audit or repair verdict, code or rung change, a lesson or note for its desk, a fulfilled
   request, a lifted blocker), except for two records that still run on the clock: a winner (a
   positive earned record, already at `winner_share` of the interval) and an idle agent (barren or
   shut wakes, at the idle cadence). Everyone else waits for evidence, the `max_skip_hours`
   heartbeat and the `sample_percent` sample. `all` is the rule before this date.
7. **Abstention has a memory.** After `abstain_lock_after` (3) abstaining sessions in a row the
   agent researches only on a settlement, a fill or a refusal of its own order until a session
   produces a candidate (or runs a replay, which resets the streak as before); notes, lessons,
   credits and verdicts wait. The idle path is untouched: an idle agent keeps its cadence. Since
   Sept 24, 2026 a locked agent's NEW session runs on `abstain_lock_profile` (`lock_profile`), the
   cheapest profile: flash_asap cost $0.0027 a call against Luna's $0.0080 and pro_asap's $0.0299
   on the same frozen packets (league/routing_evidence.json, Sept 22).
8. **A session the provider broke is not a pass** (Sept 24, 2026). One that ended in a provider
   server error (`provider_fault`: HTTP 500, 502, 503, 504 or 529) is refunded by the researcher,
   and like every provider failure (`completed_pass`) it moves no streak, counts as no completed
   pass for displacement, and the House gives the agent its turn back. The refund and this rule
   read the same predicate, so no refunded session is ever counted as a pass.

Each decision writes one private `research.gate` row, with `trigger` (the class of evidence that
woke it, or the skip's reason) and `record` (winner, loser, unproven or idle) so the yield of each
trigger can be measured against the session it bought. Repeated skips for the same reason are
aggregated (`sessions` counts the skipped sessions a row covers) so a day of backoff is a handful
of rows, not one per tick.

Also here: `Inactivity`, which writes `agent.inactive` when an agent's explicit reason for not
trading changes (market_closed, missing_data, abstained, order_rejected, provider_failure,
failed_evaluation, paused), and which the gate reads so an agent never keeps paying to rediscover
the same blocker. A reason of None in a row means the agent is active again.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import re
import threading
import time
from collections import Counter
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Mapping

from .allocator import RESTATING_CONTROLS
from .jev import sha
from .ledger import now_iso

TRIGGER_KINDS = ("book.fill", "book.settle", "book.refused", "agent.strategy", "eval.verdict", "credit.grant",
                 "eval.block", "audit.verdict")
#: Under the abstention lock (rule 7) only these wake an agent: its own outcomes at the venue.
ABSTAIN_LOCK_TRIGGERS = frozenset(("book.fill", "book.settle", "book.refused"))
#: Which class of evidence a run is credited to when several arrived at once (`trigger` on the row):
#: the venue's own verdicts first, then the House's, then what other agents wrote.
TRIGGER_PRIORITY = ("book.settle", "book.fill", "book.refused", "audit.verdict", "eval.verdict", "repair.status", "eval.block",
                    "code", "rung", "lesson", "tool.fulfilled", "library.note", "window", "market", "unblocked",
                    "agent.strategy", "credit.grant", "jev")
#: Records that still research on the clock when `clock_runs` is `winners_and_idle`.
CLOCK_RECORDS = frozenset(("winner", "idle"))
#: Verdicts written on every mark while nothing is decided (1,071 `look` and 161 `progress` of
#: 1,321 verdicts on Sept 22). Counting them would wake every paper agent every five minutes.
ROUTINE_VERDICTS = frozenset(("look", "progress"))
#: Inactivity reasons that name a blocker the agent cannot research its way past alone.
BLOCKERS = frozenset(("missing_data", "market_closed"))
REASONS = ("market_closed", "missing_data", "abstained", "order_rejected", "provider_failure", "failed_evaluation", "paused")
#: The words researchers actually used for a missing input on the production ledger
#: ("the perpetual funding/OI feed remains not_supplied", "historical option-chain replay is
#: unavailable", "the underlying-value feed ... remains unimplemented").
MISSING = re.compile(r"not[_ ]supplied|not available|unavailable|unimplemented|missing|absent|no historical|"
                     r"lacks?\b|without (?:a|the|any) [a-z-]+ (?:feed|data|history)|no [a-z/ -]{0,30}(?:feed|data)\b", re.I)
DEFAULTS: dict[str, Any] = {
    # `after`, `max_factor` and `sample_percent` are read from game.json `research.gate` (the
    # overnight v0 gate's dials, one switch for both); these are the fallbacks and the extras.
    "enabled": True,
    "after": 2,
    "max_factor": 8,
    "sample_percent": 10,
    "blocker_after": 1,
    "max_skip_hours": 24,
    "relevance_run_threshold": 0.35,
    "relevance_notes_per_decision": 16,
    "aggregate_sessions": 12,
    "order_rejected_hours": 6,
    "active_fill_hours": 24,
    # Sept 23, 2026 (rules 6 and 7 above): who may run on the clock alone, and how many abstaining
    # sessions in a row lock research to fills, settlements and refusals. `all` / 0 restore the rule
    # of Sept 22.
    "clock_runs": "winners_and_idle",
    "abstain_lock_after": 3,
    # Sept 24, 2026 (rule 7): the profile a locked agent's new session runs on; "" leaves it alone.
    "abstain_lock_profile": "flash_asap",
}
#: Provider server errors (Sept 24, 2026): the vendor failed the session, so the researcher refunds
#: what its turns were charged. The brief's 502 and 504, and the rest of the family the researcher
#: already treats alike (it polls a response it holds on any of them).
PROVIDER_FAULTS = frozenset(("provider_http_500", "provider_http_502", "provider_http_503", "provider_http_504", "provider_http_529"))
RELEVANCE = ("Does this note report evidence, a lesson, a new tool or data, or a failure that bears directly on the "
             "strategy described in state (its market, mechanism or hypothesis), so that its owner should test or change "
             "something now? Generic advice, another market's result or a restatement of known limits does not count.")


def _epoch(iso: str) -> float:
    from datetime import datetime
    return datetime.fromisoformat(str(iso).replace("Z", "+00:00")).timestamp()


def provider_fault(reason: Any) -> bool:
    """Whether a research session ended because the provider failed it (`PROVIDER_FAULTS`): the
    session the researcher refunds. Every such session is also not a completed pass."""
    text = str(reason or "")
    return text.startswith("provider: ") and text[len("provider: "):].strip() in PROVIDER_FAULTS


def completed_pass(payload: Mapping[str, Any]) -> bool:
    """Whether a research summary row is a completed pass: not a provider failure of any kind and
    not a tool outcome a restart left unconfirmed. The gate's abstention streak, the House's
    empty-pass count and displacement's count of completed passes all read it this way, and a
    refunded session (`provider_fault`) is always one of the exceptions."""
    return session_outcome(payload) != "provider_failure"


def session_outcome(payload: Mapping[str, Any]) -> str:
    """What one research summary row says the session produced.

    candidate: it retained code (the House may adopt or fork it); failed_evaluation: it ran a
    replay that produced nothing usable; provider_failure: the model call failed; abstained:
    it spent turns and changed nothing (88.6% of production sessions)."""
    reason = str(payload.get("reason") or "")
    if reason.startswith("provider") or reason.startswith("tool outcome unconfirmed"):
        return "provider_failure"
    if payload.get("candidate"):
        return "candidate"
    if int(payload.get("trials") or 0) > 0:
        return "failed_evaluation"
    if reason in ("retired or changed", "credits"):
        return "other"
    return "abstained"


class GateState:
    """A small JSON file beside the ledger: per-agent baselines, streaks and skip episodes."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.lock = threading.RLock()
        try:
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.data = {}
        self.data.setdefault("agents", {})
        self.data.setdefault("inactive", {})

    def agent(self, agent_id: str) -> dict[str, Any]:
        return self.data["agents"].setdefault(agent_id, {})

    def save(self) -> None:
        with self.lock:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, sort_keys=True), encoding="utf-8")
            os.replace(tmp, self.path)


class Inactivity:
    """An agent's explicit reason for not trading, from exact House facts, written when it changes."""

    def __init__(self, house: Any, state: GateState, *, settings: Mapping[str, Any] | None = None):
        self.house, self.state = house, state
        self.settings = {**DEFAULTS, **dict(settings or {})}
        self._requests: tuple[float, dict[str, list[str]]] = (0.0, {})

    def _unresolved_requests(self) -> dict[str, list[str]]:
        """Open or blocked tool requests by requesting agent, folded once a minute at most."""
        at, rows = self._requests
        if self.house.clock() - at < 60:
            return rows
        by: dict[str, list[str]] = {}
        commons = getattr(self.house, "commons", None)
        try:
            for row in (commons._requests() if commons is not None else []):
                if row.get("status") in ("open", "blocked"):
                    by.setdefault(row["by"], []).append(str(row.get("name") or ""))
        except Exception:  # noqa: BLE001 - a fold that fails is no evidence either way
            by = {}
        self._requests = (self.house.clock(), by)
        return by

    def last_summary(self, agent_id: str) -> Any:
        for entry in reversed(self.house.ledger.read(kinds="agent.research", agent=agent_id, limit=80, newest=True)):
            if entry.payload.get("tool") == "summary":
                return entry
        return None

    def compute(self, agent: Any) -> tuple[str | None, str, dict[str, Any]]:
        """(reason or None, detail, extra) for one living agent, highest priority first."""
        house, ledger, now = self.house, self.house.ledger, self.house.clock()
        pause = house.paused()
        if pause:
            return "paused", str(pause.get("reason") or "maintenance pause")[:200], {}
        refused = ledger.last("book.refused", agent=agent.id)
        order = ledger.last("book.order", agent=agent.id)
        fill = ledger.last("book.fill", agent=agent.id)
        if (refused is not None and (order is None or refused.seq > order.seq) and (fill is None or refused.seq > fill.seq)
                and now - _epoch(refused.at) < float(self.settings["order_rejected_hours"]) * 3600):
            reasons = refused.payload.get("reasons") or []
            return "order_rejected", str(reasons[0] if reasons else "refused")[:200], {"seq": refused.seq}
        if fill is not None and now - _epoch(fill.at) < float(self.settings["active_fill_hours"]) * 3600:
            return None, "filled recently", {}
        book = house.book_of(agent)
        account = getattr(book, "accounts", {}).get(agent.id) if book is not None else None
        if account is not None and any(h.quantity != 0 for h in account.holdings.values()):
            return None, "holds a position", {}
        idle = house.idle_run(agent)
        if idle.get("shut", 0) >= 1 and idle.get("barren", 0) == 0:
            return "market_closed", f"{idle['shut']} wakes in a row with nothing open", {}
        summary = self.last_summary(agent.id)
        outcome = session_outcome(summary.payload) if summary is not None else None
        text = str(summary.payload.get("summary") or "") if summary is not None else ""
        if outcome == "provider_failure":
            return "provider_failure", str(summary.payload.get("reason"))[:200], {"seq": summary.seq}
        if outcome == "failed_evaluation":
            return "failed_evaluation", text[:200], {"seq": summary.seq}
        if outcome == "abstained":
            lineage = house.registry.lineage(agent.id) if hasattr(house.registry, "lineage") else [agent.id]
            unresolved = self._unresolved_requests()
            requests = sorted({name for member in (lineage or [agent.id]) for name in unresolved.get(member, []) if name})
            if requests or MISSING.search(text):
                return "missing_data", text[:200], {"seq": summary.seq, "requests": requests}
        barren = int((((house.game.get("research") or {}).get("idle") or {}).get("barren_wakes")) or 10)
        if idle.get("barren", 0) >= barren:
            # Live markets in front of it and its rules did not fire: the strategy is abstaining.
            return "abstained", f"{idle['barren']} wakes in a row with {idle.get('offered', 0)} live markets and nothing done", {}
        if outcome == "abstained":
            return "abstained", text[:200], {"seq": summary.seq}
        return None, outcome or "no research yet", {}

    def current(self, agent_id: str) -> str | None:
        return (self.state.data["inactive"].get(agent_id) or {}).get("reason")

    def update(self, agents) -> list[dict[str, Any]]:
        """Recompute every agent; write a row for each whose reason changed."""
        written = []
        for agent in agents:
            try:
                reason, detail, extra = self.compute(agent)
            except Exception:  # noqa: BLE001 - one agent's unreadable state must not stop the rest
                continue
            with self.state.lock:
                previous = self.state.data["inactive"].get(agent.id)
                if previous is not None and previous.get("reason") == reason:
                    continue
                if previous is None and reason is None:
                    self.state.data["inactive"][agent.id] = {"reason": None, "since": now_iso(self.house.clock)}
                    continue
                since = now_iso(self.house.clock)
                self.state.data["inactive"][agent.id] = {"reason": reason, "since": since}
            payload = {"agent": agent.id, "reason": reason, "detail": detail, "since": since,
                       "was": (previous or {}).get("reason"), **extra}
            self.house.ledger.append("agent.inactive", payload, agent=agent.id,
                                     id=f"agent-inactive:{agent.id}:{reason}:{since}")
            written.append(payload)
        if written:
            self.state.save()
        return written


class ResearchGate:
    def __init__(self, house: Any, state: GateState, inactivity: Inactivity, *, sensor: Any = None,
                 settings: Mapping[str, Any] | None = None, rng: random.Random | None = None):
        self.house, self.state, self.inactivity, self.sensor = house, state, inactivity, sensor
        self._settings = dict(settings or {})
        self.rng = rng  # tests only; production samples by hash

    @property
    def settings(self) -> dict[str, Any]:
        """Defaults, then game.json `research.gate` (the owner's dials), then config overrides."""
        game = dict(((getattr(self.house, "game", None) or {}).get("research") or {}).get("gate") or {})
        return {**DEFAULTS, **{k: v for k, v in game.items() if not k.startswith("_")}, **self._settings}

    def _sampled(self, agent: Any, last: float, slot: int) -> bool:
        percent = float(self.settings["sample_percent"])
        if self.rng is not None:
            return self.rng.random() * 100 < percent
        digest = hashlib.sha256(f"{agent.id}:{int(last)}:{slot}".encode()).digest()
        return int.from_bytes(digest[:4], "big") / 2 ** 32 * 100 < percent

    @property
    def ledger(self):
        return self.house.ledger

    # --------------------------------------------------------------- baselines
    def _snapshot(self, agent: Any) -> dict[str, Any]:
        idle = self.house.idle_run(agent)
        return {"code": agent.code_sha256, "rung": int(self.house.evaluator.rung(agent.id)),
                "market": "closed" if idle.get("shut", 0) > 0 else "open", "window": int(idle.get("offered", 0)) > 0}

    def _bootstrap(self, agent: Any, st: dict[str, Any]) -> None:
        """First sight of an agent (a fresh deploy): its last research summary is the baseline."""
        summary = self.inactivity.last_summary(agent.id)
        # Never researched: nothing to compare with, and the clock's first pass is the baseline.
        seq = summary.seq if summary is not None else self.ledger.head()[0]
        st.update(self._snapshot(agent), seq=seq, outcome_seq=0, streak=0, recheck_at=0.0, notes_seq=seq)

    def _absorb_outcomes(self, agent: Any, st: dict[str, Any]) -> None:
        """Fold research summaries since the last look into the abstention streak."""
        consulted: set[str] = set()
        rows = []
        for entry in self.ledger.iter(kinds="agent.research", agent=agent.id, after=int(st.get("outcome_seq") or 0)):
            p = entry.payload
            if p.get("tool") == "merton" and p.get("wrote_code"):
                consulted.add(str(p.get("session")))  # a strategy Merton wrote is not an empty pass (as v0)
            if p.get("tool") == "summary":
                rows.append(entry)
        for entry in rows:
            outcome = session_outcome(entry.payload)
            if outcome == "abstained" and str(entry.payload.get("session")) not in consulted:
                st["streak"] = int(st.get("streak") or 0) + 1
            elif outcome in ("candidate", "failed_evaluation", "abstained"):
                st["streak"] = 0
            st["outcome_seq"] = entry.seq
        if rows:
            # The blocker the latest session ran into, read now rather than at the next
            # inactivity sweep: it is what must change before research is worth buying again.
            st["blocker"] = self._blocker_now(agent)

    def _blocker_now(self, agent: Any) -> str | None:
        try:
            reason = self.inactivity.compute(agent)[0]
        except Exception:  # noqa: BLE001 - unreadable is not a blocker: the clock decides
            return None
        return reason if reason in BLOCKERS else None

    # ---------------------------------------------------------------- triggers
    def triggers(self, agent: Any, st: dict[str, Any]) -> list[str]:
        after = int(st.get("seq") or 0)
        counts: Counter = Counter()
        for entry in self.ledger.read(kinds=TRIGGER_KINDS, agent=agent.id, after=after, limit=1000):
            if entry.kind == "book.fill" and entry.payload.get("source") == "dust":
                continue
            if entry.kind == "credit.grant" and str(entry.payload.get("reason") or "").startswith("epoch payout"):
                # The hourly payout says nothing new about the agent. Measured Sept 23, 2026: during
                # the burst every working paper agent was paid each hour, so each researched at
                # least hourly however long it had been abstaining, and the gate could not back off.
                continue
            if entry.kind == "eval.verdict":
                decision = str(entry.payload.get("decision") or "")
                if decision in ROUTINE_VERDICTS:
                    continue
                counts[f"eval.verdict:{decision}"] += 1
                continue
            if entry.kind == "eval.block":
                # A finished forward block with a position in it is the evidence the researcher is
                # waiting for; an inactive block (nothing held) is a mark, not news.
                if not entry.payload.get("active"):
                    continue
                counts["eval.block"] += 1
                continue
            if entry.kind == "audit.verdict":
                counts[f"audit.verdict:{'approve' if entry.payload.get('approve') else 'refuse'}"] += 1
                continue
            if entry.kind == "agent.strategy" and entry.payload.get("control") in RESTATING_CONTROLS:
                # Its own pause or resume of its entries (X1) restates its strategy: no code change,
                # no news, and it must not buy the next paid session (review of #249). An in-place
                # edit is a new strategy, as an in-place rewrite is.
                continue
            counts[entry.kind] += 1
        found = [f"{kind}:{n}" for kind, n in sorted(counts.items())]
        found += self._about_it(agent, after)
        now = self._snapshot(agent)
        if st.get("code") and now["code"] != st["code"]:
            found.append("code")
        if "rung" in st and now["rung"] != st["rung"]:
            found.append(f"rung:{st['rung']}->{now['rung']}")
        if st.get("market") and now["market"] != st["market"]:
            found.append(f"market:{st['market']}->{now['market']}")
        if agent.venue.startswith("kalshi") and now["window"] and st.get("window") is False:
            found.append("window:nonempty")
        answered = [e for e in self.ledger.read(kinds="tool.fulfilled", after=after, limit=1000)
                    if not str(e.payload.get("outcome") or "").lower().startswith("cannot be a pure tool")]
        if answered:
            # Only when something was answered: a line's own requests are a query per ancestor.
            line = set(self.house.registry.lineage(agent.id) or [agent.id]) | {agent.id}
            mine = {e.id for member in line for e in self.ledger.read(kinds="tool.request", agent=member, limit=200, newest=True)}
            found += [f"tool.fulfilled:{e.payload['request']}" for e in answered if e.payload.get("request") in mine]
        niche = getattr(agent, "niche", None)
        if niche:
            notes = [e for e in self.ledger.read(kinds="library.note", after=after, limit=1000)
                     if e.payload.get("niche") == niche and e.agent != agent.id]
            if notes:
                found.append(f"library.note:niche:{len(notes)}")
        blocker = st.get("blocker")
        if blocker:
            current = self._blocker_now(agent)
            if current != blocker:
                found.append(f"unblocked:{blocker}->{current}")
        return found

    def _about_it(self, agent: Any, after: int) -> list[str]:
        """Rows without an agent column that are still about this agent: a repair verdict whose key
        names it (`strategy_defect:<agent>:<sha>`), and a teacher's lesson that names its desk or
        family (Sept 23, 2026: the study's "a new lesson relevant to its desk")."""
        found = []
        states: Counter = Counter()
        for entry in self.ledger.read(kinds="repair.status", after=after, limit=500):
            if f":{agent.id}:" in str(entry.payload.get("key") or "") + ":":
                states[str(entry.payload.get("state") or "")] += 1
        found += [f"repair.status:{state}" for state in sorted(states) if state]
        words = {str(w).lower() for w in (getattr(agent, "niche", None), getattr(agent, "specialty", None), agent.family) if w}
        lessons = 0
        for entry in self.ledger.read(kinds="playbook.entry", after=after, limit=200):
            text = f"{entry.payload.get('title') or ''} {entry.payload.get('text') or ''}".lower()
            if any(word in text for word in words):
                lessons += 1
        if lessons:
            found.append(f"lesson:{lessons}")
        return found

    def lock_profile(self, agent: Any) -> str | None:
        """The profile a NEW session of this agent runs on while it is under the abstention lock
        (rule 7): `abstain_lock_profile`, the cheapest. None when it is not locked, the gate or the
        lock is off, or the agent is idle (an idle agent is never locked). Read from the streak the
        gate's last decision left (`allow` absorbs each summary before it decides)."""
        settings = self.settings
        profile = str(settings.get("abstain_lock_profile") or "")
        lock_after = int(settings.get("abstain_lock_after") or 0)
        if not settings.get("enabled", True) or not profile or lock_after <= 0:
            return None
        with self.state.lock:
            streak = int(self.state.agent(agent.id).get("streak") or 0)
        if streak < lock_after or self.record_of(agent) == "idle":
            return None
        return profile

    def record_of(self, agent: Any) -> str:
        """idle (its rules are not meeting the market: the House pulls its research forward), winner
        (a positive earned record), loser (an earned record that loses) or unproven (no record)."""
        try:
            if self.house.idle_reason(agent):
                return "idle"
        except Exception:  # noqa: BLE001 - an unreadable idle run is not idleness
            pass
        try:
            row = self.house.standing_of(agent.id)
            growth, seen = float(row.get("earned_growth") or 0.0), int(row.get("earned_observations") or 0)
        except Exception:  # noqa: BLE001 - a record that cannot be read is no record
            return "unproven"
        if seen <= 0:
            return "unproven"
        return "winner" if growth > 0 else "loser"

    # ---------------------------------------------------------------- semantic
    def _relevant_notes(self, agent: Any, st: dict[str, Any], receipt: dict[str, Any]) -> tuple[list[str], bool]:
        """Jev's one question: do new notes or lessons from outside this niche matter to it?

        Returns (triggers, answered). Unanswered (no client, capped, breaker) is the
        deterministic decision: these notes do not wake it."""
        after = int(st.get("notes_seq") or st.get("seq") or 0)
        venue = str(agent.venue).split("-")[0]
        niche = getattr(agent, "niche", None) or ""
        rows = []
        for entry in self.ledger.read(kinds=("library.note", "playbook.entry"), after=after, limit=1000):
            if entry.agent == agent.id or (entry.kind == "library.note" and entry.payload.get("niche") == niche):
                continue
            other = str(entry.payload.get("niche") or "")
            if other and not other.startswith(venue):
                continue  # a note from the other venue's desks is not this strategy's business
            rows.append(entry)
        rows = rows[-int(self.settings["relevance_notes_per_decision"]):]
        if not rows:
            return [], True
        if self.sensor is None:
            return [], False
        strategy = {"family": agent.family, "niche": niche, "venue": agent.venue, "horizon": agent.horizon,
                    "style": getattr(agent, "style", ""), "markets": list((agent.needs or {}).get("series") or (agent.needs or {}).get("symbols") or [])[:12],
                    "docstring": _docstring(agent.code)[:600]}
        summary = self.inactivity.last_summary(agent.id)
        if summary is not None:
            strategy["latest_conclusion"] = str(summary.payload.get("summary") or "")[:600]
        items = {f"relevance:{e.id}:{agent.code_sha256}": (f"{e.payload.get('title', '')}: {str(e.payload.get('text') or '')[:900]}", RELEVANCE)
                 for e in rows}
        answers = self.sensor.ask("gate", {"strategy": strategy}, items, receipt=receipt)
        answered = all(p is not None for p in answers.values())
        threshold = float(self.settings["relevance_run_threshold"])
        hits = [f"jev:note:{key.split(':')[1]}:p={p:.2f}" for key, p in answers.items() if p is not None and p >= threshold]
        if answered:
            st["notes_seq"] = rows[-1].seq
        return hits, answered

    # ---------------------------------------------------------------- decision
    def allow(self, agent: Any, *, last: float, forced: str = "") -> bool:
        """Called from `House._gate` once the clock says due; `forced` records a run it may not skip."""
        if not self.settings.get("enabled", True):
            return True
        now = self.house.clock()
        with self.state.lock:
            st = self.state.agent(agent.id)
            if "seq" not in st:
                self._bootstrap(agent, st)
            self._absorb_outcomes(agent, st)
            settings = self.settings
            streak = int(st.get("streak") or 0)
            record = self.record_of(agent)
            if forced:
                return self._run(agent, st, "run", forced, [forced], sampled=False, record=record)
            found = self.triggers(agent, st)
            lock_after = int(settings.get("abstain_lock_after") or 0)
            locked = lock_after > 0 and streak >= lock_after and record != "idle"
            if locked:
                # Rule 7: after `abstain_lock_after` empty sessions only its own venue outcomes count.
                found = [t for t in found if t.split(":", 1)[0] in ABSTAIN_LOCK_TRIGGERS]
            if found:
                return self._run(agent, st, "run", "trigger", found, sampled=False, record=record)
            if now < float(st.get("recheck_at") or 0):
                return False  # inside a skipped slot: re-checked only for triggers until the next one
            after = int(settings["after"])
            current = st.get("blocker")
            blocked = bool(current) and streak >= int(settings["blocker_after"])
            # Rule 6: the clock alone runs a winner and an idle agent; everyone else waits for evidence.
            clock = (str(settings.get("clock_runs") or "all") != "winners_and_idle" or record in CLOCK_RECORDS) and not locked
            receipt: dict[str, Any] = {}
            interval = float(self.house.research_interval_hours(agent)) * 3600
            if clock and streak < after and not blocked:
                return self._run(agent, st, "run", "clock", [], sampled=False, record=record)
            hits, answered = ([], True) if locked else self._relevant_notes(agent, st, receipt)
            if hits:
                return self._run(agent, st, "run", "jev_relevant_note", hits, sampled=False, receipt=receipt, record=record)
            if now - last >= float(settings["max_skip_hours"]) * 3600:
                return self._run(agent, st, "run", "heartbeat", [], sampled=False, receipt=receipt, record=record)
            if locked:
                reason = f"abstain_lock:{streak}"
            elif not clock:
                reason = f"nothing_new:{record}"
            elif blocked:
                reason = f"blocked:{current}"
            else:
                factor = min(2 ** (streak - after + 1), float(settings["max_factor"]))
                if now - last >= interval * factor:
                    return self._run(agent, st, "run", "backoff_elapsed", [], sampled=False, receipt=receipt, record=record)
                reason = f"backoff:{streak}"
            if not answered:
                reason += ":jev_unavailable"
            st["recheck_at"] = now + interval
            st["slot"] = int(st.get("slot") or 0) + 1
            if self._sampled(agent, last, st["slot"]):
                return self._run(agent, st, "sample", reason, [], sampled=True, receipt=receipt, record=record)
            self._skip(agent, st, reason, receipt, record=record)
            self.state.save()
            return False

    def _row(self, agent: Any, decision: str, reason: str, triggers: list[str], *, sampled: bool,
             sessions: int = 1, receipt: Mapping[str, Any] | None = None, **extra) -> None:
        cost = Decimal(str((receipt or {}).get("cost") or 0))
        payload = {"agent": agent.id, "decision": decision, "reason": reason, "triggers": triggers[:20],
                   "sampled": sampled, "cost_usd": format(cost, "f"), "sessions": sessions,
                   "empty_streak": int(self.state.agent(agent.id).get("streak") or 0),
                   "inactive": self.inactivity.current(agent.id),
                   # What the session (if any) is credited to, so `report()` can price each kind of evidence.
                   "trigger": _primary(triggers) if triggers else reason.split(":", 1)[0], **extra}
        stamp = now_iso(self.house.clock)
        st = self.state.agent(agent.id)
        st["n"] = int(st.get("n") or 0) + 1
        totals = self.state.data.setdefault("totals", {})
        totals[decision] = int(totals.get(decision) or 0) + sessions
        totals["jev_cost_usd"] = format(Decimal(str(totals.get("jev_cost_usd") or 0)) + cost, "f")
        self.ledger.append("research.gate", payload, agent=agent.id,
                           id=f"research-gate:{agent.id}:{st['n']}:{decision}:{stamp}")

    def _flush(self, agent: Any, st: dict[str, Any]) -> None:
        episode = st.get("episode") or {}
        if int(episode.get("pending") or 0) > 0:
            self._row(agent, "skip", episode["reason"], [], sampled=False, sessions=int(episode["pending"]),
                      aggregated=True, since=episode.get("since"), cost_usd_total=episode.get("cost", "0"),
                      record=episode.get("record"))
        st["episode"] = None

    def _skip(self, agent: Any, st: dict[str, Any], reason: str, receipt: Mapping[str, Any], *, record: str | None = None) -> None:
        episode = st.get("episode")
        if episode and episode.get("reason") != reason:
            self._flush(agent, st)
            episode = None
        if not episode:
            # The first skip of an episode is written at once; repeats are counted and flushed.
            self._row(agent, "skip", reason, [], sampled=False, receipt=receipt, record=record)
            st["episode"] = {"reason": reason, "pending": 0, "since": now_iso(self.house.clock), "cost": "0", "record": record}
            return
        episode["pending"] = int(episode.get("pending") or 0) + 1
        episode["cost"] = format(Decimal(episode.get("cost") or "0") + Decimal(str(receipt.get("cost") or 0)), "f")
        if episode["pending"] >= int(self.settings["aggregate_sessions"]):
            self._flush(agent, st)
            st["episode"] = {"reason": reason, "pending": 0, "since": now_iso(self.house.clock), "cost": "0", "record": record}

    def _run(self, agent: Any, st: dict[str, Any], decision: str, reason: str, triggers: list[str], *,
             sampled: bool, receipt: Mapping[str, Any] | None = None, **extra: Any) -> bool:
        self._flush(agent, st)
        self._row(agent, decision, reason, triggers, sampled=sampled, receipt=receipt, **extra)
        # The baseline is the ledger head at dispatch: anything recorded during the session is
        # news for the next decision (conservative: it can only cause a run, never hide one).
        st.update(self._snapshot(agent), seq=self.ledger.head()[0], recheck_at=0.0, blocker=None)
        st["notes_seq"] = st["seq"]
        self.state.save()
        return True


def _docstring(code: str) -> str:
    import ast
    try:
        return ast.get_docstring(ast.parse(code)) or ""
    except (SyntaxError, ValueError):
        return ""


def _primary(triggers: list[str]) -> str:
    """The class of evidence a run is credited to: the highest in `TRIGGER_PRIORITY` among those found."""
    classes = [str(t).split(":", 1)[0] for t in triggers if t]
    if not classes:
        return ""
    return min(classes, key=lambda c: TRIGGER_PRIORITY.index(c) if c in TRIGGER_PRIORITY else len(TRIGGER_PRIORITY))


# --------------------------------------------------------------------- measurement
def report(ledger: Any, *, sensor: Any = None, after: int = 0) -> dict[str, Any]:
    """What the gate saved and what it missed, from the ledger alone (read-only).

    skipped_sessions: sessions the clock would have run and the gate did not. estimated savings
    = skipped x the median cost of recent research sessions. A miss is a sampled would-be skip
    whose session retained a candidate (or whose agent adopted new code during it)."""
    decisions = list(ledger.iter(kinds="research.gate", after=after))
    summaries: dict[str, list[Any]] = {}
    costs = []
    for entry in ledger.iter(kinds="agent.research", after=max(0, after)):
        if entry.payload.get("tool") == "summary":
            summaries.setdefault(entry.agent, []).append(entry)
            try:
                costs.append(Decimal(str(entry.payload.get("cost_usd") or 0)))
            except ArithmeticError:
                pass
    recent = sorted(costs[-2000:])
    median = recent[len(recent) // 2] if recent else Decimal(0)
    skipped = sum(int(e.payload.get("sessions") or 1) for e in decisions if e.payload.get("decision") == "skip")
    reasons: Counter = Counter()
    for e in decisions:
        reasons[(e.payload.get("decision"), str(e.payload.get("reason") or "").split(":")[0])] += int(e.payload.get("sessions") or 1)
    samples = [e for e in decisions if e.payload.get("decision") == "sample"]
    finished = misses = 0
    for sample in samples:
        after_rows = [s for s in summaries.get(sample.agent, []) if s.seq > sample.seq]
        if not after_rows:
            continue
        finished += 1
        outcome = session_outcome(after_rows[0].payload)
        adopted = any(e.seq > sample.seq and e.seq <= after_rows[0].seq and e.payload.get("control") not in RESTATING_CONTROLS
                      for e in ledger.read(kinds="agent.strategy", agent=sample.agent, after=sample.seq, limit=5))
        if outcome == "candidate" or adopted:
            misses += 1
    jev_gate = sum((Decimal(str(e.payload.get("cost_usd") or 0)) + Decimal(str(e.payload.get("cost_usd_total") or 0))
                    for e in decisions), Decimal(0))
    # Sept 23, 2026: what each kind of evidence bought. A run is credited to its `trigger`; the
    # session it bought is the agent's next summary; a candidate (or a replay trial) is the yield.
    by_trigger: dict[str, dict[str, Any]] = {}
    for e in decisions:
        if e.payload.get("decision") not in ("run", "sample"):
            continue
        key = str(e.payload.get("trigger") or e.payload.get("reason") or "").split(":")[0] or "unknown"
        row = by_trigger.setdefault(key, {"runs": 0, "sessions": 0, "candidates": 0, "trials": 0, "cost_usd": Decimal(0)})
        row["runs"] += 1
        after_rows = [s for s in summaries.get(e.agent, []) if s.seq > e.seq]
        if not after_rows:
            continue
        outcome = session_outcome(after_rows[0].payload)
        row["sessions"] += 1
        row["candidates"] += outcome == "candidate"
        row["trials"] += outcome in ("candidate", "failed_evaluation")
        try:
            row["cost_usd"] += Decimal(str(after_rows[0].payload.get("cost_usd") or 0))
        except ArithmeticError:
            pass
    for row in by_trigger.values():
        row["usd_per_candidate"] = format(row["cost_usd"] / row["candidates"], ".4f") if row["candidates"] else None
        row["cost_usd"] = format(row["cost_usd"], "f")
    return {
        "by_trigger": dict(sorted(by_trigger.items(), key=lambda kv: -kv[1]["runs"])),
        "decisions": len(decisions), "runs": sum(1 for e in decisions if e.payload.get("decision") == "run"),
        "skipped_sessions": skipped, "sampled": len(samples), "sampled_finished": finished, "sampled_misses": misses,
        "sampled_miss_rate": round(misses / finished, 4) if finished else None,
        "median_session_cost_usd": format(median, "f"),
        "estimated_savings_usd": format(median * skipped, "f"),
        "by_decision_reason": {f"{d}:{r}": n for (d, r), n in sorted(reasons.items(), key=lambda kv: -kv[1])},
        "jev_gate_cost_usd": format(jev_gate, "f"),
        "jev": sensor.stats() if sensor is not None else None,
        "note": "Savings are an estimate at the median session cost; a miss is a sampled skip that retained a candidate or adopted code.",
    }


def main(argv: list[str] | None = None) -> int:
    """python -m league.research_gate LEDGER [--sensor jev.sqlite]: print the gate report, read-only."""
    import argparse
    import sqlite3

    from .ledger import Entry

    parser = argparse.ArgumentParser(description=main.__doc__)
    parser.add_argument("ledger")
    parser.add_argument("--sensor")
    parser.add_argument("--after", type=int, default=0)
    args = parser.parse_args(argv)

    class ReadOnly:
        def __init__(self, path):
            self.db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            self.db.row_factory = sqlite3.Row

        def _rows(self, sql, params):
            return [Entry(r["seq"], r["id"], r["kind"], r["agent"], r["at"], bool(r["public"]), json.loads(r["payload"]),
                          r["previous_hash"], r["digest"]) for r in self.db.execute(sql, params)]

        def iter(self, *, kinds, after=0, agent=None):
            kinds = [kinds] if isinstance(kinds, str) else list(kinds)
            return iter(self._rows(f"SELECT * FROM ledger WHERE seq>? AND kind IN ({','.join('?' * len(kinds))}) ORDER BY seq",
                                   [after, *kinds]))

        def read(self, *, kinds, agent=None, after=0, limit=1000, newest=False):
            kinds = [kinds] if isinstance(kinds, str) else list(kinds)
            sql = f"SELECT * FROM ledger WHERE seq>? AND kind IN ({','.join('?' * len(kinds))})" + (" AND agent=?" if agent else "")
            return self._rows(sql + " ORDER BY seq LIMIT ?", [after, *kinds, *([agent] if agent else []), limit])

    sensor = None
    if args.sensor:
        from .jev import Sensor
        sensor = Sensor(args.sensor, None, readonly=True)
    print(json.dumps(report(ReadOnly(args.ledger), sensor=sensor, after=args.after), indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
