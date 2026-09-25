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
   Since Sept 25, 2026 the question is behind a switch, `jev_relevance`, which game.json turns off. Measured
   by the Jev run over Sept 22 00Z-Sept 25 14:35Z: it woke 169 sessions ($5.24) whose o1 was 8.3% and o2 (a
   candidate that passed replay within 2 h) 4.7% -- the rate of the gate's random 10% sample of would-be
   skips (6.6% and 4.5% over 1,481) and a fifth of the free triggers' (about 23% o2): $0.66 a replay pass
   against $0.10-0.19 for the deterministic triggers. J2's held-out AUC for o2: Jev's p 0.650, the trigger
   kind alone 0.790. Since the Jev run's 11:52Z deploy lifted its call cap it wakes about 30 more a day.
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

9. **Research runs on outcomes** (Sept 25, 2026, the forward-first run, F2; `clock_runs:
   real_positions`). Replayed on the T0 snapshot (the 24 hours to 04:23Z Sept 25; `scripts/gate_replay.py`):
   2,566 sessions, $87.65, 547 candidates, and the clock was the costliest trigger -- 387 `clock` runs
   ($27.72), 350 of them idle agents re-running every 12 minutes at the winners' pace (mcentee-hfadaea
   33 sessions in the day), and the clock's 201 retained candidates had 9 adoptions or forks; 122
   `heartbeat` runs, 121 of them a newborn's first session at age 0 (an unresearched agent's `last` is
   0); 275 samples of locked winners retained 4 candidates. So the clock (and the backoff it carries) runs only an agent ON
   REAL MONEY that holds a position or a working order there, or met a refusal since its last session
   (`House._holds_real_money`'s test). Everyone else waits for evidence: a fill, a settlement, a refusal
   (once, rule 11), an active forward block, a teacher's lesson naming it (rule 12), a code or rung
   change, a verdict, a repair, a fulfilled request, a desk note, a market that opened, a lifted blocker,
   and one outcome of an idle program: `barren_wakes` (10) more wakes with live markets and nothing done
   since its last session (`idle_runs: barren`; adopting new code resets the count, `House._commit_research`).
   A market that is only closed is the calendar, not an outcome: it waits for the open. The heartbeat is
   `max_skip_hours` (24) for a real agent and `practice_max_skip_hours` (72) for a practice agent, counted
   from the gate's first sight of an agent that never researched, so a newborn trades before it researches.
   An agent on rung 0 (replay only, no forward outcome possible until it passes) keeps its clock, with its
   backoff, and is neither paused (rule 10) nor locked (rule 7): research is its only way up and
   `replay_deadline_epochs` (72 hours) bounds it. Until the review of #311 the pause overrode that clock,
   and a replay-only agent, which cannot fill, waited on the 10% sample until it was killed as never
   qualified; its sessions after three empty ones still run on `abstain_lock_profile`.
10. **A practice agent's pause** (F2). After `practice_pause_after` (3) abstaining sessions in a row a
   practice agent (not on rung 0) researches only on news of its own program (`PAUSE_NEWS`: a code or
   rung change, a repair verdict about it, a teacher's lesson naming it, its idle program's barren
   outcome) and on its own trading (`PAUSE_DAILY`: a fill or an active forward block) at most once per
   UTC day -- no settlement, refusal, desk note, heartbeat or Jev question -- until a session produces a
   candidate or a replay. Review of #311, replayed on the T0 snapshot: the fill-only pause ran every
   fill-woken session (452, $5.36: 10 candidates, 1 adoption) and blocked the productive news; this rule
   runs 794 sessions instead of 1,038 (+44 samples), 259 candidates instead of 253 and 90 adoptions or
   forks instead of 85, for $34.58 instead of $33.71. A real agent keeps rule 7's lock. The
   sample still draws from both (rule 5), at most once per `sample_hours` (6) per agent under this rule,
   not once per research interval: a winner's interval is 12 minutes, and 10% of its skips was 272
   sessions a day. Paused and locked sessions run on `abstain_lock_profile`.
11. **A refusal triggers research once per agent, reason and day** (X2; `refusal_dedupe`). Measured on the
   T0 snapshot: 670 refusals in 24 hours from 86 distinct (agent, day, reason) triples, which bought 437
   prompt sessions (`House.research_due`'s refusal fast path, 23 candidates) and 107 gate runs (4). The
   reason is the refusal's first reason with its numbers and tickers taken out (`refusal_class`), on its
   book; any session that runs uses up the keys of the refusals it saw. The fast path asks
   `refusal_news` before it runs and writes a `research.gate` row (`reason: refusal`) when it does.
12. **Lessons are the teacher's, and half the floor is the control** (F2 and F4). A `playbook.entry` wakes
   an agent only when its source is in `lesson_sources` (the teacher's): 134 of the 204 lesson-triggered
   rows at T0 had no teacher lesson behind them, only a desk-mate's post-mortem. Under `lesson_arm:
   parity` a lesson wakes only agents whose id hashes even (`lesson_arm`); the odd half is the control
   the hourly yield row compares on forward growth over 3 days (`yield_ledger.teacher_lift`). A control
   agent is neither woken by, asked Jev about, nor shown by `playbook_read` a lesson that names it for
   those 3 days (`withheld`; review of #311: 413 `playbook_read` calls by 121 agents in the 24 hours to
   T0, so the control read the lesson whenever it researched for any other reason).
13. **A practice agent's own fills and settlements do not wake it** (Sept 25, 2026, the forward-first
   run's Y, from the Jev run's J2; `practice_skip_triggers`, under `real_positions` only). J2 joined 6,846
   finished sessions of Sept 22 00Z to Sept 25 06Z to the gate rows that bought them: on the sessions F2
   still runs, the trigger kind alone predicts a replay pass at AUC 0.856 held out, and sessions woken by
   the agent's own fills or settlements predict none (0.215). The kinds were chosen on Sept 22-23 alone:
   those with at least 20 practice sessions whose dollars per replay pass were over 3x the days' average
   ($0.138): `book.fill` (495 sessions, $0.62 a pass) and `book.settle` (62, $0.44); a refusal ($0.15),
   a lesson, a note, a block, a code change stay. Checked on the held-out Sept 24 00Z-Sept 25 06Z with
   each session's own gate triggers: of F2's 1,171 surviving sessions ($37.00, 257 replay passes) the
   rule skips 408 ($4.86, 13%) for 5 replay passes (2%) and 8 candidates of 301 (3%), $0.97 a pass
   skipped against $0.14 on average. The kinds are taken out of the triggers found; anything else found
   still runs the session (a lesson must still wake the lesson arm, rule 12), and the active forward
   block that sums a practice agent's fills is a trigger as before. The kinds are taken out before rule
   10's pause filter, so a paused practice agent's fill is not the once-a-UTC-day trade that wakes it
   (`pause_trade_day` is spent only by what remains, its active forward block): it is woken by news of
   its program, its own active block once a day, and the sample (the forward-first run's merge of Y into
   c/integration, Sept 25, 2026). The passed kinds move the baseline only when they were all that was
   found, so nothing a pause or a lock holds back is consumed. An agent on real money keeps every trigger: J2's 171
   held-out real sessions held 8 of their 11 replay passes in these kinds, and real outcomes are what
   its research is for. `[]` restores F2.
14. **Compute follows yield** (Sept 25, 2026, Y1; `league/yield_ledger.py`). While the hourly yield row
   has the `research` lane throttled (its dollars per positive forward block over the day above
   `economy.lane_throttle` times the best lane's), a practice agent's session waits twice its research
   interval, but never past a day since its last session (one session an agent a day is the floor); an
   agent on real money, and one on rung 0 (rule 9), keeps its pace. It holds Luna's and Sail's research alike: the lane is both, and
   Sail's is what remains when OpenAI's month reaches `audits`. Triggers found meanwhile wait, unconsumed,
   for the session the throttle allows; one skip row (`lane_throttle:research`) marks each held slot and
   is never sampled (a budget decision, not a guess at relevance). The refusal fast path is not held:
   rule 11 already allows it once per agent, reason and day.

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
from .worklist import FIT_MARK

TRIGGER_KINDS = ("book.fill", "book.settle", "book.refused", "agent.strategy", "eval.verdict", "credit.grant",
                 "eval.block", "audit.verdict")
#: Under the abstention lock (rule 7) only these wake an agent: its own outcomes at the venue.
ABSTAIN_LOCK_TRIGGERS = frozenset(("book.fill", "book.settle", "book.refused"))
#: Under a practice agent's pause (rule 10) news of its own program wakes it as ever (review of #311,
#: Sept 25, 2026: a code change, a rung change, a repair verdict about it, a lesson naming it, its idle
#: program's outcome) ...
PAUSE_NEWS = frozenset(("code", "rung", "repair.status", "lesson", "barren"))
#: ... and its own trading (a fill, an active forward block) at most once per UTC day.
PAUSE_DAILY = frozenset(("book.fill", "eval.block"))
PAUSE_TRIGGERS = PAUSE_NEWS | PAUSE_DAILY
#: Which class of evidence a run is credited to when several arrived at once (`trigger` on the row):
#: the venue's own verdicts first, then the House's, then what other agents wrote.
TRIGGER_PRIORITY = ("book.settle", "book.fill", "book.refused", "audit.verdict", "eval.verdict", "repair.status", "eval.block",
                    "code", "rung", "lesson", "tool.fulfilled", "library.note", "window", "market", "unblocked", "barren",
                    "agent.strategy", "credit.grant", "jev")
#: Records that still research on the clock when `clock_runs` is `winners_and_idle`.
CLOCK_RECORDS = frozenset(("winner", "idle"))
#: `clock_runs` values: the Sept 22 rule, the Sept 23 rule, and research on outcomes (F2, Sept 25, 2026).
CLOCK_RULES = ("all", "winners_and_idle", "real_positions")
#: `idle_runs` values (rule 9): an idle program's outcome wakes it, nothing does, or (the Sept 23 rule for
#: idle agents alone) its idle cadence does.
IDLE_RULES = ("barren", "off", "clock")
#: `lesson_arm` values (rule 12): every agent a lesson names, or the even half by `lesson_arm`.
LESSON_ARMS = ("all", "parity")
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
    # of Sept 22; `winners_and_idle` the rule of Sept 23; `real_positions` is F2 (rules 9 and 10).
    "clock_runs": "real_positions",
    "abstain_lock_after": 3,
    # Sept 24, 2026 (rule 7): the profile a locked agent's new session runs on; "" leaves it alone.
    "abstain_lock_profile": "flash_asap",
    # Sept 25, 2026 (F2, rules 9 and 10; read only under `clock_runs: real_positions`).
    "practice_max_skip_hours": 72,
    "practice_pause_after": 3,
    "idle_runs": "barren",
    "sample_hours": 6,
    "lesson_arm": "parity",
    # Sept 25, 2026 (X2 and F2, rules 11 and 12; read under every `clock_runs`).
    "refusal_dedupe": True,
    "lesson_sources": ["teacher"],
    # Sept 25, 2026 (Y, rule 13; under `real_positions` only): the trigger kinds that do not wake a
    # practice agent. game.json sets J2's ["book.fill", "book.settle"]; [] here keeps F2's rules alone.
    "practice_skip_triggers": [],
    # Sept 25, 2026 (rule 4's switch; the Jev run's measurement): whether Jev's relevance answer may wake a
    # session. game.json sets false; True here keeps the rule before it.
    "jev_relevance": True,
}
#: The trigger kinds `practice_skip_triggers` may name (game.json `research_bounds.gate` lists them).
SKIPPABLE_TRIGGERS = ("book.fill", "book.settle", "book.refused", "credit.grant", "window", "market")
#: Rule 14: a throttled research lane never holds an agent more than a day past its last session.
THROTTLE_FLOOR_SECONDS = 86400.0
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


_TICKER = re.compile(r"\b[A-Z][A-Z0-9]*(?:[-.][A-Z0-9.]+)+\b")
_NUMBER = re.compile(r"\d[\d,.]*")


def refusal_class(text: Any) -> str:
    """A refusal's reason without what varies between two refusals of the same rule: its numbers and
    its market tickers. "one event may hold at most 25% of the stake: KXBTCD-26SEP2501 would hold $3.80
    of this account's $13.27 ..." and the same refusal at $4.10 of $13.40 on another event are one class
    (rule 11; the 670 refusals of the 24 hours to T0 were 86 (agent, day, class) triples). The X3 note after
    `FIT_MARK` (the band, the cap and the room, whose words vary: "1 contract fits", "2 contracts fit") is not
    the rule's text and is left out (the review of Deploy C, Sept 25, 2026)."""
    text = _NUMBER.sub("#", _TICKER.sub("T", str(text or "").split(FIT_MARK, 1)[0]))
    return re.sub(r"\s+", " ", text).strip().lower()[:120]


def refusal_key(entry: Any) -> str:
    """The key rule 11 counts once per agent and day: the refusal's UTC day, its book and its class."""
    p = entry.payload
    reasons = p.get("reasons") or [""]
    return f"{str(entry.at)[:10]}|{p.get('book') or ''}|{refusal_class(reasons[0] if reasons else '')}"


def lesson_arm(agent_id: str) -> str:
    """Which arm of the teacher's comparison an agent is in (rule 12): `lesson` when the first byte of
    the sha256 of its id is even, else `control`. Stable across restarts and releases, and independent of
    the desk, the family and the order agents were born in."""
    return "lesson" if hashlib.sha256(str(agent_id).encode("utf-8")).digest()[0] % 2 == 0 else "control"


#: Desk names without their venue that are ordinary words in a lesson ("the market is open", "prices",
#: "its options"): a lesson names those desks only by their full id.
GENERIC_DESKS = frozenset(("open", "prices", "options", "attention"))


def lesson_words(agent_id: str, *names: Any) -> set[str]:
    """What a lesson may call an agent by (rule 12): its id, its family, its desk and specialty, and the
    desk without its venue ("crypto-15m" for kalshi-crypto-15m) unless that is an ordinary word. The
    teacher writes "crypto-15m" and "sports", almost never the desk's id: of the twelve teacher lessons
    of Sept 23-24, eight named no living agent by desk, specialty or family id and four named one; by
    these words ten name 1 to 32 each (T0 snapshot)."""
    words = {str(agent_id).lower()} | {str(n).lower() for n in names if n}
    for name in list(words):
        venue, _, short = name.partition("-")
        if venue in ("kalshi", "alpaca") and short and short not in GENERIC_DESKS:
            words.add(short)
    return {w for w in words if w}


def lesson_terms(entry: Any) -> set[str]:
    """Every run of up to six whole hyphenated words in a lesson's title and text ("kalshi-crypto-15m-lab"
    gives "crypto-15m", "kalshi-crypto" ...), so a name matches only on word boundaries and by set lookup.
    Desk, family and agent names run to four words."""
    text = f"{entry.payload.get('title') or ''} {entry.payload.get('text') or ''}".lower()
    terms: set[str] = set()
    for token in re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*", text):
        parts = token.split("-")[:12]
        terms.update("-".join(parts[i:j]) for i in range(len(parts)) for j in range(i + 1, min(len(parts), i + 6) + 1))
    return terms


def lesson_names(words: Any, entry: Any, sources: Any = ("teacher",), terms: set[str] | None = None) -> bool:
    """Whether a `playbook.entry` is a lesson (its source is one of `sources`) that names one of `words`
    (`lesson_words`) on word boundaries. A post-mortem (`source: graveyard`) is never a lesson: 134 of the
    204 lesson-triggered gate rows of the 24 hours to T0 had only one behind them."""
    if str(entry.payload.get("source") or "") not in set(sources or ()):
        return False
    terms = lesson_terms(entry) if terms is None else terms
    return any(word in terms for word in words)


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
        """First sight of an agent (a fresh deploy): its last research summary is the baseline.
        `since` (Sept 25, 2026) is when the gate first saw it: the heartbeat of an agent that never
        researched counts from here under rule 9, not from the epoch."""
        summary = self.inactivity.last_summary(agent.id)
        # Never researched: nothing to compare with, and the clock's first pass is the baseline.
        seq = summary.seq if summary is not None else self.ledger.head()[0]
        st.update(self._snapshot(agent), seq=seq, outcome_seq=0, streak=0, recheck_at=0.0, notes_seq=seq,
                  since=self.house.clock())

    # ------------------------------------------------------------------ F2 facts
    def _f2(self, settings: Mapping[str, Any]) -> bool:
        return str(settings.get("clock_runs") or "all") == "real_positions"

    def _money(self, agent: Any) -> tuple[bool, bool]:
        """(on real money, holds a position or a working order there): the book the House puts it on
        (`House.book_of`) is a real-money book, and it has holdings or open orders on it -- the test of
        `House._holds_real_money`. Unreadable is practice with nothing held."""
        try:
            book = self.house.book_of(agent)
        except Exception:  # noqa: BLE001 - a book that cannot be read is no real money
            return False, False
        if book is None or not getattr(book, "real_money", False):
            return False, False
        try:
            holds = agent.id in book.accounts and bool(book.account(agent.id).holdings or book.open_orders(agent.id))
        except Exception:  # noqa: BLE001 - unreadable holdings are no position
            holds = False
        return True, holds

    def _rung(self, agent: Any) -> int | None:
        try:
            return int(self.house.evaluator.rung(agent.id))
        except Exception:  # noqa: BLE001 - an unreadable rung is none
            return None

    def _paused(self, settings: Mapping[str, Any], real: bool, streak: int, agent: Any = None) -> bool:
        """Rule 10: a practice agent after `practice_pause_after` abstaining sessions in a row, unless it
        is on rung 0 (`agent` given): a replay-only agent cannot fill, and research is its only way up."""
        after = int(settings.get("practice_pause_after") or 0)
        if not (self._f2(settings) and not real and after > 0 and streak >= after):
            return False
        return agent is None or self._rung(agent) != 0

    def _pause_filter(self, st: dict[str, Any], found: list[str], now: float) -> list[str]:
        """What wakes a paused practice agent (rule 10): news of its program (`PAUSE_NEWS`) always, its own
        trading (`PAUSE_DAILY`) when it has not already bought a session this UTC day
        (`pause_trade_day`, which the run records)."""
        kept = [t for t in found if t.split(":", 1)[0] in PAUSE_NEWS]
        trading = [t for t in found if t.split(":", 1)[0] in PAUSE_DAILY]
        if trading and st.get("pause_trade_day") != now_iso(lambda: now)[:10]:
            kept += trading
        return kept

    def _used(self, st: dict[str, Any], day: str) -> set[str]:
        return set((st.get("refusals") or {}).get(day) or ())

    def _refusals_since(self, agent: Any, st: dict[str, Any], *, book: str | None = None) -> list[Any]:
        rows = self.ledger.read(kinds="book.refused", agent=agent.id, after=int(st.get("seq") or 0), limit=1000)
        return [e for e in rows if book is None or e.payload.get("book") == book]

    def _consume_refusals(self, agent: Any, st: dict[str, Any], also: Any = None) -> tuple[int, int]:
        """Rule 11: a session is running, so every refusal since the baseline has been seen: its key is
        used for its day. `also` is the refusal the House's fast path ran on, which is before the
        baseline when the gate first saw the agent at that refusal. Returns (new keys, refusals whose key
        was already used). Keeps the keys of the last two UTC days."""
        used = {day: set(keys) for day, keys in (st.get("refusals") or {}).items()}
        new = dup = 0
        rows = self._refusals_since(agent, st)
        if also is not None and all(e.seq != also.seq for e in rows):
            rows.insert(0, also)
        for entry in rows:
            key = refusal_key(entry)
            day = key[:10]
            if key in used.setdefault(day, set()):
                dup += 1
            else:
                used[day].add(key)
                new += 1
        keep = sorted(used)[-2:]
        st["refusals"] = {day: sorted(used[day])[-200:] for day in keep}
        return new, dup

    def refusal_news(self, agent: Any, refusal: Any, *, take: bool = False) -> bool:
        """The House's refusal fast path asks here first (rule 11): is there a refusal on `refusal`'s book
        since this agent's last session whose (day, book, class) has not already bought research today,
        and is the agent not paused (rule 10)? With `take` (the fast path is about to queue the session)
        the run is recorded like any other -- a `research.gate` row with `reason: refusal`, the baseline
        moved, the keys used -- and True returned. The gate switched off, or `refusal_dedupe` off, is the
        rule before Sept 25, 2026: every new refusal is news."""
        settings = self.settings
        if not settings.get("enabled", True):
            return True
        with self.state.lock:
            st = self.state.agent(agent.id)
            if "seq" not in st:
                self._bootstrap(agent, st)
            self._absorb_outcomes(agent, st)
            streak = int(st.get("streak") or 0)
            real = self._money(agent)[0] if self._f2(settings) else False
            if self._paused(settings, real, streak, agent):
                return False
            book = refusal.payload.get("book") if refusal is not None else None
            rows = self._refusals_since(agent, st, book=book)
            if refusal is not None and all(e.seq != refusal.seq for e in rows):
                rows.insert(0, refusal)  # first sight at this refusal: the bootstrap's baseline is past it
            if settings.get("refusal_dedupe", True):
                fresh = [e for e in rows if refusal_key(e) not in self._used(st, refusal_key(e)[:10])]
            else:
                fresh = rows
            if not fresh:
                return False
            if not take:
                return True
            extra = {"money": "real" if real else "practice"} if self._f2(settings) else {}
            return self._run(agent, st, "run", "refusal", [f"book.refused:{len(fresh)}"], sampled=False,
                             record=self.record_of(agent), _refusal=refusal, **extra)

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
        settings = self.settings
        dedupe = bool(settings.get("refusal_dedupe", True))
        counts: Counter = Counter()
        for entry in self.ledger.read(kinds=TRIGGER_KINDS, agent=agent.id, after=after, limit=1000):
            if entry.kind == "book.fill" and entry.payload.get("source") == "dust":
                continue
            if entry.kind == "book.refused" and dedupe and refusal_key(entry) in self._used(st, str(entry.at)[:10]):
                # Rule 11 (X2, Sept 25, 2026): this reason already bought this agent research today.
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
        barren = self._barren_outcome(agent, st, settings)
        if barren:
            found.append(barren)
        return found

    def _barren_outcome(self, agent: Any, st: dict[str, Any], settings: Mapping[str, Any]) -> str:
        """Rule 9's one outcome of an idle program (`idle_runs: barren`, under `real_positions` only):
        `barren_wakes` more wakes with live markets in front of it and nothing done since its last
        session (or since the gate first counted, `barren_seen`), as `barren:<n>`. "" otherwise."""
        if not self._f2(settings) or str(settings.get("idle_runs") or "off") != "barren":
            return ""
        try:
            barren = int(self.house.idle_run(agent).get("barren") or 0)
        except Exception:  # noqa: BLE001 - an unreadable idle run is no outcome
            return ""
        if "barren_seen" not in st:
            st["barren_seen"] = barren  # first count under this rule: no burst of runs at deploy
            return ""
        seen = int(st.get("barren_seen") or 0)
        if barren < seen:
            # Acting or new code reset the count: count from zero from now on (review of #311: seen 40,
            # then 45 after a reset, read as 5).
            st["barren_seen"] = seen = 0
        grown = barren - seen
        need = int((((getattr(self.house, "game", None) or {}).get("research") or {}).get("idle") or {}).get("barren_wakes") or 10)
        return f"barren:{grown}" if grown >= need else ""

    def _about_it(self, agent: Any, after: int) -> list[str]:
        """Rows without an agent column that are still about this agent: a repair verdict whose key
        names it (`strategy_defect:<agent>:<sha>`), and a teacher's lesson that names its desk or
        family (Sept 23, 2026: the study's "a new lesson relevant to its desk"). Since Sept 25, 2026 a
        lesson is a `playbook.entry` whose source is in `lesson_sources` (the teacher's; never a
        post-mortem, rule 12), and under `lesson_arm: parity` with `real_positions` it wakes only the
        lesson arm (`lesson_arm`)."""
        found = []
        states: Counter = Counter()
        for entry in self.ledger.read(kinds="repair.status", after=after, limit=500):
            if f":{agent.id}:" in str(entry.payload.get("key") or "") + ":":
                states[str(entry.payload.get("state") or "")] += 1
        found += [f"repair.status:{state}" for state in sorted(states) if state]
        settings = self.settings
        if self._f2(settings) and str(settings.get("lesson_arm") or "all") == "parity":
            # When the arms were first split: the hourly yield row compares them from here (F4).
            self.state.data.setdefault("lesson_arm_since", now_iso(self.house.clock))
            if lesson_arm(agent.id) != "lesson":
                return found  # the control arm: the teacher's lift is measured against it
        words = lesson_words(agent.id, getattr(agent, "niche", None), getattr(agent, "specialty", None), agent.family)
        sources = settings.get("lesson_sources") or ["teacher"]
        lessons = sum(1 for entry in self.ledger.read(kinds="playbook.entry", after=after, limit=200)
                      if lesson_names(words, entry, sources))
        if lessons:
            found.append(f"lesson:{lessons}")
        return found

    def withheld(self, agent: Any, entry: Any) -> bool:
        """Whether a `playbook.entry` is held back from this agent (rule 12; review of #311, Sept 25, 2026):
        under `lesson_arm: parity` with `real_positions`, a teacher's lesson (source in `lesson_sources`)
        written since the arms were split that names a control-arm agent, for `merton.lift.teacher_days`
        (3) after it was written -- the window `yield_ledger.teacher_lift` measures. Neither Jev's relevance
        question (`_relevant_notes`) nor the researcher's `playbook_read` (`Researcher.withheld`, wired by
        league/service.py) shows it to that agent meanwhile; every other entry, and every lesson after its
        window, is everyone's. Measured at T0: 413 `playbook_read` calls by 121 agents in 24 hours, so a
        control agent that researched for any other reason read the lesson that named it, and the lift
        compared two arms that had both read it. Anything unreadable holds nothing back."""
        try:
            settings = self.settings
            if not settings.get("enabled", True) or not self._f2(settings) or str(settings.get("lesson_arm") or "all") != "parity":
                return False
            if lesson_arm(agent.id) != "control":
                return False
            sources = settings.get("lesson_sources") or ["teacher"]
            if str(entry.payload.get("source") or "") not in set(sources):
                return False
            since = self.state.data.get("lesson_arm_since")
            at = _epoch(entry.at)
            if not since or at < _epoch(since):
                return False
            lift = ((getattr(self.house, "game", None) or {}).get("merton") or {}).get("lift") or {}
            if self.house.clock() - at > float(lift.get("teacher_days") or 3) * 86400:
                return False
            words = lesson_words(agent.id, getattr(agent, "niche", None), getattr(agent, "specialty", None), agent.family)
            return lesson_names(words, entry, sources)
        except Exception:  # noqa: BLE001 - the control arm must never cost an agent the playbook
            return False

    def lock_profile(self, agent: Any) -> str | None:
        """The profile a NEW session of this agent runs on while it is under the abstention lock
        (rule 7): `abstain_lock_profile`, the cheapest. None when it is not locked, the gate or the
        lock is off, or the agent is idle (an idle agent is never locked). Read from the streak the
        gate's last decision left (`allow` absorbs each summary before it decides)."""
        settings = self.settings
        profile = str(settings.get("abstain_lock_profile") or "")
        lock_after = int(settings.get("abstain_lock_after") or 0)
        if not settings.get("enabled", True) or not profile:
            return None
        with self.state.lock:
            streak = int(self.state.agent(agent.id).get("streak") or 0)
        if self._f2(settings):
            # Rule 10 (Sept 25, 2026): a paused practice agent's fill session, and a locked real agent's,
            # run on the cheapest profile; idleness buys no exemption once the clock runs nobody idle.
            # A rung-0 agent is neither paused nor locked (it keeps its clock), but after three empty
            # sessions its sessions run on the cheapest profile, as they did under rule 7.
            real = self._money(agent)[0]
            return profile if self._paused(settings, real, streak, agent) or (lock_after > 0 and streak >= lock_after) else None
        if lock_after <= 0 or streak < lock_after or self.record_of(agent) == "idle":
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
            if entry.kind == "playbook.entry" and self.withheld(agent, entry):
                continue  # rule 12: the control arm is not asked about the lesson that names it
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
            f2 = self._f2(settings)
            real, holding = self._money(agent) if f2 else (False, False)
            # Under rule 9 every row says which money the agent is on, so the watch can read that the
            # clock and the 24-hour heartbeat went only to real money.
            tags: dict[str, Any] = {"record": record, **({"money": "real" if real else "practice"} if f2 else {})}
            if forced:
                return self._run(agent, st, "run", forced, [forced], sampled=False, **tags)
            if f2 and not real:
                # Rule 14 (Y1): the research lane is throttled; triggers wait, unconsumed, for the slot. An agent
                # on rung 0 keeps its clock (rule 9): replay is its only way up, inside its deadline.
                hold = self._throttle_hold(agent, last, now) if self._rung(agent) != 0 else None
                if hold is not None:
                    if float(st.get("throttle_until") or 0) != hold:
                        st["throttle_until"] = hold
                        self._skip(agent, st, "lane_throttle:research", {}, **tags)
                        self.state.save()
                    return False
            head = int(self.ledger.head()[0])
            found = self.triggers(agent, st)
            lock_after = int(settings.get("abstain_lock_after") or 0)
            # Rule 9: an agent on rung 0 (replay only) keeps its clock; it is neither paused nor locked.
            rung0 = f2 and self._rung(agent) == 0
            paused = not rung0 and self._paused(settings, real, streak)
            # Rule 7's idle exemption kept an idle agent's cadence; under rule 9 no idle agent has one.
            locked = not paused and not rung0 and lock_after > 0 and streak >= lock_after and (f2 or record != "idle")
            # Rule 13: a practice agent's own fills and settlements do not wake it; anything else does. Taken
            # out first, so a paused agent's fill never spends rule 10's once-a-day trade (`pause_trade_day`).
            skip = self._skip_kinds(settings) if f2 and not real else frozenset()
            dropped = [t for t in found if t.split(":", 1)[0] in skip]
            only_dropped = bool(dropped) and len(dropped) == len(found)
            if dropped:
                found = [t for t in found if t.split(":", 1)[0] not in skip]
            if paused:
                # Rule 10: a practice agent after three empty sessions waits for news of its program, or
                # its own trading once a day.
                found = self._pause_filter(st, found, now)
                if any(t.split(":", 1)[0] in PAUSE_DAILY for t in found):
                    st["pause_trade_day"] = now_iso(lambda: now)[:10]
            elif locked:
                # Rule 7: after `abstain_lock_after` empty sessions only its own venue outcomes count.
                found = [t for t in found if t.split(":", 1)[0] in ABSTAIN_LOCK_TRIGGERS]
            if found:
                return self._run(agent, st, "run", "trigger", found, sampled=False, **tags)
            if only_dropped:
                # Seen and not bought: the baseline passes them, so they neither wake it later nor pile up
                # to be read again at every check. Only when nothing else was found up to `head`: a
                # trigger a pause or a lock holds back (a second active block the same UTC day) must wait.
                st["seq"] = max(int(st.get("seq") or 0), head)
            if now < float(st.get("recheck_at") or 0):
                return False  # inside a skipped slot: re-checked only for triggers until the next one
            after = int(settings["after"])
            current = st.get("blocker")
            blocked = bool(current) and streak >= int(settings["blocker_after"])
            if f2:
                # Rule 9: the clock runs an agent on real money that holds a position or a working order
                # there or met a refusal since its last session, and an agent on rung 0 (replay only).
                clock = not locked and not paused and ((real and (holding or bool(self._refusals_since(agent, st))))
                                                       or rung0
                                                       or (record == "idle" and settings.get("idle_runs") == "clock"))
            else:
                # Rule 6: the clock alone runs a winner and an idle agent; everyone else waits for evidence.
                clock = (str(settings.get("clock_runs") or "all") != "winners_and_idle" or record in CLOCK_RECORDS) and not locked
            receipt: dict[str, Any] = {}
            interval = float(self.house.research_interval_hours(agent)) * 3600
            if clock and streak < after and not blocked:
                return self._run(agent, st, "run", "clock", [], sampled=False, **tags)
            # Rule 4's switch (`jev_relevance`): off, Jev is not asked and wakes nothing.
            ask_jev = not (locked or paused) and bool(settings.get("jev_relevance", True))
            hits, answered = self._relevant_notes(agent, st, receipt) if ask_jev else ([], True)
            if hits:
                return self._run(agent, st, "run", "jev_relevant_note", hits, sampled=False, receipt=receipt, **tags)
            heartbeat = float(settings["practice_max_skip_hours"] if f2 and not real else settings["max_skip_hours"])
            # Rule 9: an agent that never researched (`last` 0) counts from the gate's first sight of it.
            since = float(st.get("since") or 0) if f2 and not last else last
            if not paused and now - since >= heartbeat * 3600:
                return self._run(agent, st, "run", "heartbeat", [], sampled=False, receipt=receipt, **tags)
            if paused:
                reason = f"practice_pause:{streak}"
            elif locked:
                reason = f"abstain_lock:{streak}"
            elif dropped and not clock:
                reason = f"trigger_skip:{_primary(dropped)}"
            elif not clock:
                reason = f"nothing_new:{record}"
            elif blocked:
                reason = f"blocked:{current}"
            else:
                factor = min(2 ** (streak - after + 1), float(settings["max_factor"]))
                if now - last >= interval * factor:
                    return self._run(agent, st, "run", "backoff_elapsed", [], sampled=False, receipt=receipt, **tags)
                reason = f"backoff:{streak}"
            if not answered:
                reason += ":jev_unavailable"
            st["recheck_at"] = now + interval
            st["slot"] = int(st.get("slot") or 0) + 1
            if self._draw(agent, st, last, now, settings):
                return self._run(agent, st, "sample", reason, [], sampled=True, receipt=receipt, **tags)
            self._skip(agent, st, reason, receipt, **tags)
            self.state.save()
            return False

    def _skip_kinds(self, settings: Mapping[str, Any]) -> frozenset[str]:
        """Rule 13: the trigger kinds that do not wake a practice agent (`practice_skip_triggers`)."""
        kinds = settings.get("practice_skip_triggers") or ()
        return frozenset(str(k) for k in (kinds if isinstance(kinds, (list, tuple)) else ()) if str(k) in SKIPPABLE_TRIGGERS)

    def _throttle_hold(self, agent: Any, last: float, now: float) -> float | None:
        """Rule 14: while the hourly yield row has the research lane throttled, the instant until which this
        practice agent's next session waits (twice its interval, never past a day since its last session),
        or None when it may run. An agent that never researched is not held: F2 counts it from first sight."""
        if not last:
            return None
        from .yield_ledger import throttled

        if not throttled(self.ledger, "research"):
            return None
        try:
            interval = float(self.house.research_interval_hours(agent)) * 3600
        except Exception:  # noqa: BLE001 - an interval that cannot be read holds nobody
            return None
        until = float(last) + min(2 * interval, max(interval, THROTTLE_FLOOR_SECONDS))
        return until if now < until else None

    def _draw(self, agent: Any, st: dict[str, Any], last: float, now: float, settings: Mapping[str, Any]) -> bool:
        """Whether this skip is sampled (rule 5). Under rule 10 an agent is drawn at most once per
        `sample_hours` window, whatever its research interval; otherwise once per skipped slot."""
        hours = float(settings.get("sample_hours") or 0)
        if not self._f2(settings) or hours <= 0:
            return self._sampled(agent, last, st["slot"])
        window = int(now // (hours * 3600))
        if st.get("sample_window") == window:
            return False
        st["sample_window"] = window
        return self._sampled(agent, float(window), 0)

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
                      record=episode.get("record"), **({"money": episode["money"]} if episode.get("money") else {}))
        st["episode"] = None

    def _skip(self, agent: Any, st: dict[str, Any], reason: str, receipt: Mapping[str, Any], *, record: str | None = None,
              money: str | None = None) -> None:
        episode = st.get("episode")
        tags = {"record": record, **({"money": money} if money else {})}
        if episode and episode.get("reason") != reason:
            self._flush(agent, st)
            episode = None
        if not episode:
            # The first skip of an episode is written at once; repeats are counted and flushed.
            self._row(agent, "skip", reason, [], sampled=False, receipt=receipt, **tags)
            st["episode"] = {"reason": reason, "pending": 0, "since": now_iso(self.house.clock), "cost": "0", **tags}
            return
        episode["pending"] = int(episode.get("pending") or 0) + 1
        episode["cost"] = format(Decimal(episode.get("cost") or "0") + Decimal(str(receipt.get("cost") or 0)), "f")
        if episode["pending"] >= int(self.settings["aggregate_sessions"]):
            self._flush(agent, st)
            st["episode"] = {"reason": reason, "pending": 0, "since": now_iso(self.house.clock), "cost": "0", **tags}

    def _run(self, agent: Any, st: dict[str, Any], decision: str, reason: str, triggers: list[str], *,
             sampled: bool, receipt: Mapping[str, Any] | None = None, **extra: Any) -> bool:
        self._flush(agent, st)
        # Rule 11: this session sees every refusal since the baseline, so their keys are used today.
        new, dup = self._consume_refusals(agent, st, extra.pop("_refusal", None))
        totals = self.state.data.setdefault("totals", {})
        totals["refusal_keys"] = int(totals.get("refusal_keys") or 0) + new
        if dup:
            totals["refusals_deduped"] = int(totals.get("refusals_deduped") or 0) + dup
            extra = {**extra, "refusals_deduped": dup}
        self._row(agent, decision, reason, triggers, sampled=sampled, receipt=receipt, **extra)
        # The baseline is the ledger head at dispatch: anything recorded during the session is
        # news for the next decision (conservative: it can only cause a run, never hide one).
        st.update(self._snapshot(agent), seq=self.ledger.head()[0], recheck_at=0.0, blocker=None)
        st["notes_seq"] = st["seq"]
        if "barren_seen" in st or self._f2(self.settings):
            try:
                st["barren_seen"] = int(self.house.idle_run(agent).get("barren") or 0)  # rule 9 counts from here
            except Exception:  # noqa: BLE001 - an unreadable idle run keeps the old count
                pass
        self.state.save()
        return True


def refusal_news(house: Any, agent: Any, refusal: Any, *, take: bool = False) -> bool:
    """`House.research_due`'s refusal fast path asks this before it runs (rule 11): the House's gate
    (`house.jev_floor.gate`) decides whether the refusal is news, and with `take` records the run. With
    no gate wired, or a gate that raises, every new refusal is news, as before Sept 25, 2026: the gate
    saves money and must never cost research."""
    gate = getattr(getattr(house, "jev_floor", None), "gate", None)
    if gate is None:
        return True
    try:
        return bool(gate.refusal_news(agent, refusal, take=take))
    except Exception as exc:  # noqa: BLE001 - fail open, as `JevFloor.research_due` does
        try:
            house.alert("warning", f"research gate's refusal check failed open for {agent.id} ({type(exc).__name__}: {str(exc)[:160]})")
        except Exception:  # noqa: BLE001
            pass
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
    # Sept 25, 2026 (rules 9 and 11): which money each run's agent was on, by reason, so the watch reads
    # that the clock and the 24-hour heartbeat went only to real money; and the refusals deduplicated.
    by_money: dict[str, Counter] = {}
    for e in decisions:
        if e.payload.get("decision") in ("run", "sample") and e.payload.get("money"):
            by_money.setdefault(str(e.payload["money"]), Counter())[str(e.payload.get("reason") or "").split(":")[0]] += 1
    return {
        "by_money": {money: dict(sorted(reasons.items(), key=lambda kv: -kv[1])) for money, reasons in sorted(by_money.items())},
        "refusals_deduped": sum(int(e.payload.get("refusals_deduped") or 0) for e in decisions),
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
