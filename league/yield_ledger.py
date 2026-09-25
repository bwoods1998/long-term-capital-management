"""The hourly yield ledger: what each paid line spent and what evidence it produced.

Sept 23, 2026 (the learn-and-unblock run, S3/C3: compute follows yield). The study priced the loop
by hand from six ledger kinds -- research abstentions $112.80 of $147.44, the foundry $0.26 a replay
pass, the engineer $0.70 a born child with no forward block, the architect $45.53 for one positive
forward record -- and nothing on the floor could show those numbers while they moved. This module
folds the rows that already exist into one `ops.budget` row an hour (`what: "yield"`), so
`scripts/floor_watch.py` and the operator can read dollars per unit of evidence by line without a
snapshot. It writes nothing else and asks no model anything.

Lines. `research` is every agent's research tokens (`credit.charge` "research tokens": Luna and Sail
together; the summary rows say which provider ran a session). Each of Merton's roles is its
`merton.pass` rows (`role`: architect, engineer, consultant, teacher, foundry, toolsmith, operator,
designer). `audits` are `audit.verdict` rows with a `cost_usd`. The lab's LLM calls live in
`lab.sqlite`, not on the ledger; since Sept 25, 2026 (Y1) the row reads them from there (`lab`).

Evidence. Candidates are research summaries that retained one (`agent.research` `tool: summary`,
`candidate: true`); replay passes are `eval.trial` rows with `passed`, credited to the line that wrote
the code (a card's line to the foundry, `lab:` founders to the lab, a merged repair's child to the
engineer, an architect's strategy to the architect, everything else to research); positive forward
blocks are active `eval.block` rows with positive log growth, credited the same way; cards and lessons
are counted for the foundry and the teacher. `usd_per` divides a line's spend by each unit it produced.
A lesson is a `playbook.entry` the teacher wrote (`source: teacher`): until Sept 25, 2026 every
post-mortem counted, 111 of the 117 "lessons" of the 24 hours to T0 (the teacher wrote 6).

The forward lift (Sept 25, 2026, the forward-first run, F4; `lift` on the row, `lifts()`). Pricing a
lane is not measuring it: in the 24 hours to T0 (04:23Z) the consultant cost $35.44 for 62 answers and
nothing said whether one made an agent trade better. Replayed on the T0 snapshot with the functions
below: 50 of 110 judged consults were followed by no candidate and no strategy change; the 31 with six
forward blocks after them grew 0.0091 a block LESS than in the six before (one-sided 80% lower bound
-0.0129; 12 of 31 better), at $0.45 a positive block after against research's $0.29 over the same day.
Over the last `merton.lift.days` (7):

- the teacher: forward growth per active block over `teacher_days` (3) after each lesson, of the agents
  the lesson names (desk, specialty or family), split by `research_gate.lesson_arm`: under the gate's
  `lesson_arm: parity` a lesson wakes the research of the even half only, so the odd half is a control
  that was not steered to it; since the review of #311 the control is also neither asked Jev about nor
  shown by `playbook_read` the lesson that names it for `teacher_days` (`ResearchGate.withheld`), so the
  arms are agents that read the lesson and agents that did not. Counted from `lesson_since`, when the
  gate first split the arms.
- the consultant: a `consult.outcome` row for each paid consult at two stages -- `sessions`, whether the
  agent retained a candidate or changed its strategy within two sessions (`merton.consult_verdict`; an
  unproductive one doubles its next consult's price, `Merton.consult_price_multiple`), and `blocks`,
  its next `consult_blocks` (6) active forward blocks against its previous ones (`merton.consult_blocks`)
  -- and their mean lift, dollars per positive block after, against research's over the last day.
- the engineer: repairs verified (`repair.status` `verified`, one per key) per dollar of its passes,
  over the window and lifetime (22 for $27.54 at T0, $1.25 a repair).

Each lane's `verdict` is `lift` when the one-sided 80% lower bound of its lift is above zero (the
engineer: a verified repair in the window), `no_lift` when it is not on at least `min_blocks` (30)
blocks an arm (the consultant: 10 judged consults), and `insufficient` otherwise. A lane with no lift
at the end of the run goes into `merton.paused_until_profit` (the teacher and, since Sept 25, 2026, the
consultant are allowed there).

Compute follows yield (Sept 25, 2026, the forward-first run, Y1; `throttle` on the row, `plan_throttle`).
In the 24 hours to T0 (04:23Z) the floor spent $118.88 of compute against $21.35 of real settled profit,
and the 24 yield rows priced each lane's positive forward blocks: the lab $4.50 of its own calls for 115
($0.039 a block), the foundry $2.53 for 49 ($0.052), the engineer $10.09 for 56 ($0.18), research $51.33
for 178 ($0.29), the consultant $35.44 for none on the day (F4's replay: $0.45 a positive block after its
consults), the architect $7.38 and the teacher $2.50 for none. So at each hourly row a lane whose dollars
per positive block over the last day exceed `economy.lane_throttle` (3, bounds 2-5) times the best lane's
(the cheapest with at least `REFERENCE_MIN_BLOCKS` positive blocks) is halved, and one that bought no
positive block at all is halved too, once it spent `THROTTLE_MIN_USD` in the day: research's cadence
(league/research_gate.py: a practice agent's interval doubles, never past one session a day; an agent on
real money keeps its pace; Luna and Sail alike, since the research line is both), the consultant's price
(league/merton.py), each scheduled role's cadence (league/merton.py) and the engineer's pace except for a
job about an agent on real money (league/engineer.py). Audits are never throttled; the lab and the foundry
are measured (the lab's calls from its own store) but their dials are league/lab.py's and
league/hypotheses.py's. A lane measured by its lift rather than by blocks (the teacher) or by blocks days
after its spend (the consultant) is judged on F4's reading, and not throttled while that reads
`insufficient`. The halving holds while the lane stays over the line and lifts at the first row under it;
each change is one `ops.budget` row (`what: "lane throttle"`) naming the lane, its price, the best lane's
and the ratio, and `throttled()` is what the lanes read.

Unit economics (Y2; `unit_economics` on the row, and health.json's `unit_economics`, which the site's
flywheel strip reads): compute a day against real settled profit a day over the last 24 hours, counted
as the scoreboard's `unit_economics` counts them (scripts/gap_scoreboard.py `compute_per_day` and
`real_settled`): Luna's gateway-verified requests, Merton's and the auditor's metered passes, research
grants, the Sail meter, Jev and web-search charges and the lab's own calls; the real books' settlements
and closing sales (`merton.RealPnl`).
"""

from __future__ import annotations

import math
import threading
import weakref
from collections import Counter, deque
from decimal import Decimal
from typing import Any, Iterable, Mapping

from .ledger import now_iso

WHAT = "yield"
ROLES = ("architect", "engineer", "consultant", "teacher", "foundry", "toolsmith", "operator", "designer")
#: The one-sided 80% normal quantile: a lift's lower bound is lift - Z80 x its standard error.
Z80 = 0.8416
#: Blocks an arm needs before the teacher's lift can say `no_lift`; judged consults, the consultant's.
MIN_BLOCKS = 30
MIN_CONSULTS = 10


def _money(value: Any) -> Decimal:
    try:
        out = Decimal(str(value or 0))
    except ArithmeticError:
        return Decimal(0)
    return out if out.is_finite() else Decimal(0)


def line_of(founder: Any, born_reason: Any = "", repair: bool = False) -> str:
    """Which paid line an agent's code came from, by how it was born."""
    founder = str(founder or "")
    if founder.startswith("card:"):
        return "foundry"
    if founder.startswith("lab:"):
        return "lab"
    if repair:
        return "engineer"
    if founder and str(born_reason or "").startswith("Merton, as architect"):
        return "architect"
    return "research"


def fold(ledger: Any, *, since: str, until: str | None = None, repairs: Mapping[str, bool] | None = None,
         lab_usd: Decimal | None = None) -> dict[str, Any]:
    """The spend and evidence of every line between two ledger stamps (ISO, inclusive of `since`).

    `by_profile` (Sept 24, 2026, L2): research by the model profile each session ran on (its summary
    row's `profile`: Sail's `pro_asap`, `flash_asap` ..., `openai_luna`): sessions, candidates,
    provider failures, the dollars its research tokens were charged (every turn of the session, even
    one charged before the window began) and candidates per dollar.

    `lab_usd` (Sept 25, 2026, Y1): the Alpha Lab's own model calls in the window (`lab.sqlite` `calls`,
    never on the ledger), so the lab's positive blocks have a price: $4.50 of calls and 115 positive
    blocks in the 24 hours to T0."""
    spend: Counter = Counter()
    if lab_usd is not None:
        spend["lab"] += _money(lab_usd)
    evidence: dict[str, Counter] = {}
    tokens: dict[str, Decimal] = {}  # session -> its research-token charges, wherever they fall
    profiles: dict[str, Counter] = {}

    def count(line: str, unit: str, n: int = 1) -> None:
        evidence.setdefault(line, Counter())[unit] += n

    lines_by_agent: dict[str, str] = {}
    for entry in ledger.iter(kinds="agent.born"):
        p = entry.payload
        lines_by_agent[entry.agent] = line_of(p.get("founder"), p.get("reason"), bool((repairs or {}).get(str(p.get("founder") or ""))))

    def window(entry: Any) -> bool:
        return entry.at >= since and (until is None or entry.at < until)

    for entry in ledger.iter(kinds=("credit.charge", "merton.pass", "audit.verdict", "agent.research", "eval.trial", "eval.block",
                                    "hypothesis.card", "playbook.entry", "lab.graduate")):
        p = entry.payload
        if entry.kind == "credit.charge" and p.get("what") == "research tokens" and isinstance(p.get("detail"), Mapping):
            session = str(p["detail"].get("session") or "")
            if session:
                tokens[session] = tokens.get(session, Decimal(0)) + _money(p.get("usd"))
        if not window(entry):
            continue
        kind = entry.kind
        if kind == "credit.charge":
            if p.get("what") == "research tokens":
                spend["research"] += _money(p.get("usd"))
        elif kind == "merton.pass":
            role = str(p.get("role") or "")
            if role in ROLES:
                spend[role] += _money(p.get("cost_usd"))
                if p.get("error"):
                    count(role, "errors")
                if int(p.get("files") or 0) > 0:
                    count(role, "proposals")
        elif kind == "audit.verdict":
            spend["audits"] += _money(p.get("cost_usd"))
            count("audits", "verdicts")
            if p.get("approve"):
                count("audits", "approvals")
        elif kind == "agent.research":
            if p.get("tool") == "summary":
                count("research", "sessions")
                if p.get("candidate"):
                    count("research", "candidates")
                elif int(p.get("trials") or 0) == 0 and not str(p.get("reason") or "").startswith("provider"):
                    count("research", "abstentions")
                row = profiles.setdefault(str(p.get("profile") or "unknown"), Counter())
                row["sessions"] += 1
                row["candidates"] += bool(p.get("candidate"))
                row["provider_failures"] += str(p.get("reason") or "").startswith("provider")
                row["micro_usd"] += int(tokens.get(str(p.get("session") or ""), Decimal(0)) * 1_000_000)
            elif p.get("tool") == "merton":
                count("consultant", "answers" if not p.get("error") else "failed")
        elif kind == "eval.trial":
            if p.get("passed"):
                count(lines_by_agent.get(entry.agent, "research"), "replay_passes")
        elif kind == "eval.block":
            if p.get("active"):
                line = lines_by_agent.get(entry.agent, "research")
                count(line, "active_blocks")
                if float(p.get("log_growth") or 0) > 0:
                    count(line, "positive_blocks")
        elif kind == "hypothesis.card":
            count("foundry", "cards")
        elif kind == "playbook.entry":
            if p.get("source") == "teacher":  # a post-mortem is the graveyard's, not a lesson (Sept 25, 2026)
                count("teacher", "lessons")
        elif kind == "lab.graduate":
            count("lab", "graduates")
    usd_per: dict[str, dict[str, str]] = {}
    for line, dollars in spend.items():
        units = evidence.get(line) or {}
        usd_per[line] = {unit: format(dollars / n, ".4f") for unit, n in sorted(units.items())
                         if n > 0 and unit in ("candidates", "replay_passes", "positive_blocks", "cards", "proposals", "answers", "approvals", "lessons")}
    by_profile = {}
    for name, row in sorted(profiles.items()):
        dollars = Decimal(row["micro_usd"]) / 1_000_000
        by_profile[name] = {"sessions": row["sessions"], "candidates": row["candidates"], "provider_failures": row["provider_failures"],
                            "usd": format(dollars, ".4f"),
                            "candidates_per_usd": round(float(row["candidates"] / dollars), 2) if dollars > 0 else None}
    return {"what": WHAT, "since": since, "until": until, "by_profile": by_profile,
            "spend_usd": {line: format(dollars, ".4f") for line, dollars in sorted(spend.items())},
            "evidence": {line: dict(sorted(units.items())) for line, units in sorted(evidence.items())},
            "usd_per": usd_per, "total_usd": format(sum(spend.values(), Decimal(0)), ".4f")}


def _epoch(iso: str) -> float:
    from datetime import datetime

    return datetime.fromisoformat(str(iso).replace("Z", "+00:00")).timestamp()


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _arm(values: list[float]) -> dict[str, Any]:
    mean = _mean(values)
    var = sum((v - mean) ** 2 for v in values) / (len(values) - 1) if len(values) > 1 and mean is not None else None
    return {"blocks": len(values), "mean_log_growth": round(mean, 6) if mean is not None else None,
            "_mean": mean, "_var": var}


def _lower(lift: float | None, *variances_over_n: float | None) -> float | None:
    """The one-sided 80% lower bound of a difference of means (Welch's standard error)."""
    if lift is None or any(v is None for v in variances_over_n):
        return None
    return lift - Z80 * math.sqrt(sum(variances_over_n))


def _teacher_tape(ledger: Any, cache: dict[str, Any], keep_after: float) -> dict[str, Any]:
    """What the teacher's lift reads, folded incrementally into `cache` (the `YieldLedger` keeps one,
    so an hourly row reads only the rows since the last): each agent's lesson words, birth and death,
    its active forward blocks since `keep_after`, and each teacher's lesson with its terms. The first
    fold reads the whole history (about 4 s on the T0 snapshot, most of it agent.born's code)."""
    from .research_gate import lesson_terms, lesson_words

    for key in ("words", "born", "died", "blocks"):
        cache.setdefault(key, {})
    cache.setdefault("lessons", [])
    for entry in ledger.iter(kinds=("agent.born", "agent.died", "eval.block", "playbook.entry"), after=int(cache.get("seq") or 0)):
        cache["seq"] = entry.seq
        p = entry.payload
        if entry.kind == "agent.born":
            cache["words"][entry.agent] = lesson_words(entry.agent, p.get("specialty"), p.get("niche"), p.get("family"))
            cache["born"][entry.agent] = _epoch(entry.at)
        elif entry.kind == "agent.died":
            cache["died"][entry.agent] = _epoch(entry.at)
        elif entry.kind == "eval.block":
            if p.get("active") and _epoch(entry.at) >= keep_after:
                cache["blocks"].setdefault(entry.agent, []).append((entry.seq, _epoch(entry.at), float(p.get("log_growth") or 0)))
        elif p.get("source") == "teacher":
            cache["lessons"].append((_epoch(entry.at), lesson_terms(entry)))
    for agent, rows in list(cache["blocks"].items()):
        kept = [row for row in rows if row[1] >= keep_after]
        if kept:
            cache["blocks"][agent] = kept
        else:
            del cache["blocks"][agent]
    return cache


def teacher_lift(ledger: Any, *, now: float, since: str | None, days: float = 7, teacher_days: float = 3,
                 min_blocks: int = MIN_BLOCKS, cache: dict[str, Any] | None = None) -> dict[str, Any]:
    """F4: forward growth over `teacher_days` after each teacher's lesson written in the last `days`
    (and after `since`, when the gate first split the arms), of the agents it names, by
    `research_gate.lesson_arm`. A block counts once per arm however many lessons name its agent."""
    from .research_gate import lesson_arm

    if not since:
        return {"verdict": "not_started", "note": "the research gate has not split the lesson arms (research.gate.lesson_arm)"}
    start = max(_epoch(since), now - days * 86400)
    tape = _teacher_tape(ledger, cache if cache is not None else {}, now - (days + teacher_days + 1) * 86400)
    words, born, died, blocks = tape["words"], tape["born"], tape["died"], tape["blocks"]
    lessons = [(at, terms) for at, terms in tape["lessons"] if at >= start]
    seen: dict[str, dict[tuple[str, int], float]] = {"lesson": {}, "control": {}}
    agents: dict[str, set[str]] = {"lesson": set(), "control": set()}
    complete = 0
    for at, terms in lessons:
        complete += at + teacher_days * 86400 <= now
        for agent, named in words.items():  # a lesson names an agent as the gate's `lesson_names` reads it
            if born[agent] > at or died.get(agent, float("inf")) < at or not any(word in terms for word in named):
                continue
            arm = lesson_arm(agent)
            agents[arm].add(agent)
            for seq, t, growth in blocks.get(agent, ()):
                if at < t <= at + teacher_days * 86400:
                    seen[arm][(agent, seq)] = growth
    treated, control = _arm(list(seen["lesson"].values())), _arm(list(seen["control"].values()))
    lift = treated["_mean"] - control["_mean"] if treated["_mean"] is not None and control["_mean"] is not None else None
    lower = _lower(lift, *(a["_var"] / a["blocks"] if a["_var"] is not None else None for a in (treated, control)))
    enough = min(treated["blocks"], control["blocks"]) >= min_blocks
    verdict = "lift" if lower is not None and lower > 0 else "no_lift" if enough else "insufficient"
    return {"since": since, "lessons": len(lessons), "complete_windows": complete,
            "lesson_arm": {**{k: v for k, v in treated.items() if not k.startswith("_")}, "agents": len(agents["lesson"])},
            "control_arm": {**{k: v for k, v in control.items() if not k.startswith("_")}, "agents": len(agents["control"])},
            "lift": round(lift, 6) if lift is not None else None, "lower_80": round(lower, 6) if lower is not None else None,
            "verdict": verdict}


def consult_outcomes(ledger: Any, *, now: float, settings: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The `consult.outcome` rows not yet on the ledger (F4), as (id, agent, payload) dicts. A consult is
    judged at `sessions` once the agent has run `consult_sessions` sessions after it (or three days have
    passed: an agent that died or stopped researching did nothing with it), and at `blocks` once it has
    `consult_blocks` active forward blocks after it (or twice `days` have passed, `partial`)."""
    from .merton import consult_blocks, consult_verdict, consults_of

    sessions, n, days = int(settings["consult_sessions"]), int(settings["consult_blocks"]), float(settings["days"])
    judged = {(int(e.payload.get("consult_seq") or 0), str(e.payload.get("stage")))
              for e in ledger.read(kinds="consult.outcome", limit=5000, newest=True)}
    out: list[dict[str, Any]] = []
    by_agent: dict[str, list[Any]] = {}
    for consult in consults_of(ledger):
        if now - _epoch(consult.at) <= 2 * days * 86400:
            by_agent.setdefault(str(consult.payload["agent"]), []).append(consult)
    for agent, consults in by_agent.items():
        # One read of the agent's rows for all its consults: at 64 consults a day, a fortnight of
        # consults waiting for their blocks is hundreds of consults over far fewer agents.
        waiting = [c for c in consults if (c.seq, "sessions") not in judged]
        rows = list(ledger.iter(kinds=("agent.research", "agent.strategy"), agent=agent, after=waiting[0].seq)) if waiting else []
        blocks = list(ledger.iter(kinds="eval.block", agent=agent)) if any((c.seq, "blocks") not in judged for c in consults) else []
        for consult in consults:
            age = now - _epoch(consult.at)
            base = {"consult_seq": consult.seq, "agent": agent, "consulted_at": consult.at,
                    "cost_usd": str(consult.payload.get("cost_usd") or "0"), "wrote_code": bool(consult.payload.get("wrote_code"))}
            if (consult.seq, "sessions") not in judged:
                verdict = consult_verdict(consult, rows, sessions=sessions)
                if verdict is None and age >= 3 * 86400:
                    done = sum(1 for e in rows if e.seq > consult.seq and e.payload.get("tool") == "summary")
                    verdict = {"productive": False, "by": None, "sessions": done, "expired": True}
                if verdict is not None:
                    out.append({"id": f"consult-outcome:{consult.seq}:sessions", "agent": agent,
                                # An expired consult is not judged by `Merton.consult_price_multiple`: it doubles nothing.
                                "payload": {**base, "stage": "sessions", **verdict,
                                            "doubles_next_price": not verdict["productive"] and not verdict.get("expired")}})
            if (consult.seq, "blocks") not in judged:
                before, after = consult_blocks(ledger, consult, n=n, rows=blocks)
                partial = len(after) < n
                if not partial or age >= 2 * days * 86400:
                    b, a = _mean(before), _mean(after)
                    out.append({"id": f"consult-outcome:{consult.seq}:blocks", "agent": agent,
                                "payload": {**base, "stage": "blocks", "partial": partial,
                                            "before": {"blocks": len(before), "mean_log_growth": round(b, 6) if b is not None else None},
                                            "after": {"blocks": len(after), "mean_log_growth": round(a, 6) if a is not None else None,
                                                      "positive": sum(1 for g in after if g > 0)},
                                            "lift": round(a - b, 6) if a is not None and b is not None else None}})
    return out


def consultant_lift(ledger: Any, *, now: float, days: float = 7, min_consults: int = MIN_CONSULTS,
                    research_usd_per_positive_block: str | None = None) -> dict[str, Any]:
    """F4: the consultant over the last `days` from its `consult.outcome` rows and `merton.pass` costs."""
    start = now - days * 86400
    rows = [e.payload for e in ledger.read(kinds="consult.outcome", limit=5000, newest=True) if _epoch(e.at) >= start]
    judged = [r for r in rows if r.get("stage") == "sessions"]
    lifted = [r for r in rows if r.get("stage") == "blocks" and r.get("lift") is not None]
    spend = sum((_money(e.payload.get("cost_usd")) for e in ledger.read(kinds="merton.pass", limit=3000, newest=True)
                 if e.payload.get("role") == "consultant" and _epoch(e.at) >= start), Decimal(0))
    positive = sum(int((r.get("after") or {}).get("positive") or 0) for r in rows if r.get("stage") == "blocks")
    lifts = [float(r["lift"]) for r in lifted]
    mean = _mean(lifts)
    var = sum((v - mean) ** 2 for v in lifts) / (len(lifts) - 1) if len(lifts) > 1 and mean is not None else None
    lower = _lower(mean, var / len(lifts) if var is not None else None)
    verdict = "lift" if lower is not None and lower > 0 else "no_lift" if len(lifts) >= min_consults else "insufficient"
    return {"judged": len(judged), "productive": sum(1 for r in judged if r.get("productive")),
            "judged_blocks": len(lifted), "lift": round(mean, 6) if mean is not None else None,
            "lower_80": round(lower, 6) if lower is not None else None, "usd": format(spend, ".4f"),
            "positive_blocks_after": positive, "usd_per_positive_block": format(spend / positive, ".4f") if positive else None,
            "research_usd_per_positive_block_24h": research_usd_per_positive_block, "verdict": verdict}


def engineer_lift(ledger: Any, *, now: float, days: float = 7) -> dict[str, Any]:
    """F4: repairs verified (one per `repair.status` key) per dollar of the engineer's passes, over the
    last `days` and lifetime."""
    start = now - days * 86400
    verified: dict[str, float] = {}
    for entry in ledger.iter(kinds="repair.status"):
        if entry.payload.get("state") == "verified":
            verified.setdefault(str(entry.payload.get("key")), _epoch(entry.at))
    spend_all = spend = Decimal(0)
    for entry in ledger.iter(kinds="merton.pass"):
        if entry.payload.get("role") == "engineer":
            cost = _money(entry.payload.get("cost_usd"))
            spend_all += cost
            spend += cost if _epoch(entry.at) >= start else 0
    window = sum(1 for t in verified.values() if t >= start)
    return {"repairs_verified": window, "usd": format(spend, ".4f"),
            "usd_per_repair": format(spend / window, ".4f") if window else None,
            "lifetime": {"repairs_verified": len(verified), "usd": format(spend_all, ".4f"),
                         "usd_per_repair": format(spend_all / len(verified), ".4f") if verified else None},
            "verdict": "lift" if window else "no_lift" if spend > 0 else "insufficient"}


def research_usd_per_positive_block(rows: Iterable[Mapping[str, Any]]) -> str | None:
    """Research's dollars per positive forward block over some hourly yield rows (the F2 acceptance)."""
    spend, positive = Decimal(0), 0
    for row in rows:
        spend += _money((row.get("spend_usd") or {}).get("research"))
        positive += int(((row.get("evidence") or {}).get("research") or {}).get("positive_blocks") or 0)
    return format(spend / positive, ".4f") if positive else None


def lifts(ledger: Any, *, now: float, settings: Mapping[str, Any] | None = None, lesson_since: str | None = None,
          recent: Iterable[Mapping[str, Any]] = (), cache: dict[str, Any] | None = None) -> dict[str, Any]:
    """The `lift` section of the hourly yield row (F4): the teacher, the consultant and the engineer
    over the last `days`, and research's dollars per positive forward block over `recent` rows."""
    from .merton import LIFT

    s = {**LIFT, **dict(settings or {})}
    days = float(s["days"])
    research = research_usd_per_positive_block(recent)
    return {"days": days, "research_usd_per_positive_block_24h": research,
            "teacher": teacher_lift(ledger, now=now, since=lesson_since, days=days, teacher_days=float(s["teacher_days"]), cache=cache),
            "consultant": consultant_lift(ledger, now=now, days=days, research_usd_per_positive_block=research),
            "engineer": engineer_lift(ledger, now=now, days=days)}


# ------------------------------------------------------------------ Y1: the lane throttle
THROTTLE_WHAT = "lane throttle"
#: The lanes the throttle halves, and how (the `how` of each `ops.budget` "lane throttle" row). Audits are
#: never throttled; the lab and the foundry are priced (the best lane is usually one of them) but their
#: dials are league/lab.py's (protected) and league/hypotheses.py's.
THROTTLE_HOW: dict[str, str] = {
    "research": "cadence: a practice agent's research interval doubles, never past one session a day since its last "
                "(league/research_gate.py); an agent on real money keeps its pace; Luna and Sail alike",
    "consultant": "budget: a consult costs the agent twice its price (league/merton.py consult_price_multiple)",
    "engineer": "cadence: one paid patch per two intervals, except a job about an agent on real money (league/engineer.py)",
    **{role: "cadence: its schedule doubles (league/merton.py Merton.due)"
       for role in ("architect", "toolsmith", "operator", "designer", "teacher")},
}
NEVER_THROTTLED = frozenset(("audits",))
#: The best lane is the cheapest with at least this many positive forward blocks in the day: a lane that
#: bought two blocks for a few cents is luck, not a price (the lab had 115 and the foundry 49 at T0).
REFERENCE_MIN_BLOCKS = 10
#: A lane is throttled only once it spent this much in the day: halving $0.47 of toolsmith saves nothing.
THROTTLE_MIN_USD = Decimal("1.00")
#: The newest `ops.budget` rows read for the day's yield rows (filtered to `WHAT` and the last 24 hours). The review of
#: Deploy C (Sept 25, 2026): 200 covered 18.1 hours at T0 (246 ops.budget rows a day: Sail 107, holds absorbed 67,
#: yield 24; 210 on Sept 23, 241 on Sept 24), so the day's price was taken over 18-20 yield rows. 2,000 is eight
#: days of today's volume, read once an hour.
DAY_ROWS = 2000


def lane_prices(rows: Iterable[Mapping[str, Any]], lift: Mapping[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    """Each lane's dollars and positive forward blocks over some hourly yield rows (the last day's), and
    its dollars per positive block. The consultant's blocks come days after its consults, so it is priced
    on F4's `consult.outcome` reading over `lift.days` (dollars of consults against the positive blocks
    after them); the teacher is judged by its lift (a lesson arm against a control), never by blocks.
    Either is `unmeasured` while F4 has nothing judged, and an unmeasured lane is never throttled."""
    spend: dict[str, Decimal] = {}
    blocks: Counter = Counter()
    for row in rows:
        for line, usd in (row.get("spend_usd") or {}).items():
            spend[line] = spend.get(line, Decimal(0)) + _money(usd)
        for line, units in (row.get("evidence") or {}).items():
            blocks[line] += int((units or {}).get("positive_blocks") or 0)
    out: dict[str, dict[str, Any]] = {}
    for line in sorted(set(spend) | set(blocks)):
        usd, n = spend.get(line, Decimal(0)), int(blocks[line])
        out[line] = {"usd": format(usd, ".4f"), "positive_blocks": n,
                     "usd_per_positive_block": format(usd / n, ".4f") if n else None, "basis": "the day's yield rows"}
    lift = lift or {}
    consultant = lift.get("consultant") or {}
    if "consultant" in out or consultant.get("usd"):
        if int(consultant.get("judged_blocks") or 0) > 0:
            n = int(consultant.get("positive_blocks_after") or 0)
            out["consultant"] = {"usd": consultant.get("usd"), "positive_blocks": n, "usd_per_positive_block": consultant.get("usd_per_positive_block"),
                                 "basis": f"consult.outcome over {lift.get('days', 7)} days (F4): its blocks come days after its consults",
                                 "day_usd": (out.get("consultant") or {}).get("usd")}
        else:
            out.setdefault("consultant", {"usd": "0.0000", "positive_blocks": 0, "usd_per_positive_block": None})
            out["consultant"]["unmeasured"] = "no consult has its forward blocks judged yet (F4)"
    teacher = lift.get("teacher") or {}
    if "teacher" in out:
        verdict = teacher.get("verdict")
        if verdict == "lift":
            out["teacher"]["unmeasured"] = "measured by its lift, which is positive (F4)"
        elif verdict != "no_lift":
            out["teacher"]["unmeasured"] = f"measured by its lift, which reads {verdict or 'nothing yet'} (F4)"
    return out


def plan_throttle(prices: Mapping[str, Mapping[str, Any]], multiple: float) -> dict[str, Any]:
    """Which lanes the throttle halves: over `multiple` times the best lane's dollars per positive block,
    or no positive block at all, having spent `THROTTLE_MIN_USD`. No lane is throttled while no lane has
    `REFERENCE_MIN_BLOCKS` positive blocks to be the reference."""
    reference = [(Decimal(p["usd_per_positive_block"]), lane) for lane, p in prices.items()
                 if lane not in NEVER_THROTTLED and p.get("usd_per_positive_block") is not None and not p.get("unmeasured")
                 and int(p.get("positive_blocks") or 0) >= REFERENCE_MIN_BLOCKS and Decimal(p["usd_per_positive_block"]) > 0]
    best = min(reference) if reference else None
    lanes: dict[str, dict[str, Any]] = {}
    for lane in sorted(THROTTLE_HOW):
        p = prices.get(lane)
        row: dict[str, Any] = {"throttled": False}
        if p is None:
            row["why"] = "spent nothing in the day"
        else:
            row.update({k: p.get(k) for k in ("usd", "positive_blocks", "usd_per_positive_block")})
            spent = max(_money(p.get("usd")), _money(p.get("day_usd")))
            price = p.get("usd_per_positive_block")
            if p.get("unmeasured"):
                row["why"] = p["unmeasured"]
            elif spent < THROTTLE_MIN_USD:
                row["why"] = f"spent ${spent:.2f}, under ${THROTTLE_MIN_USD}"
            elif best is None:
                row["why"] = f"no lane has {REFERENCE_MIN_BLOCKS} positive blocks to be the reference"
            elif price is None:
                row.update(throttled=True, ratio=None, why="bought no positive forward block")
            else:
                ratio = Decimal(price) / best[0]
                row.update(ratio=round(float(ratio), 2), throttled=ratio > Decimal(str(multiple)),
                           why=f"{float(ratio):.2f}x the best lane's price")
        lanes[lane] = row
    return {"multiple": multiple, "best": {"lane": best[1], "usd_per_positive_block": format(best[0], ".4f")} if best else None,
            "lanes": lanes, "prices": {lane: dict(p) for lane, p in prices.items()}}


class _ThrottleFold:
    """The newest `ops.budget` "lane throttle" row of each lane, folded incrementally."""

    def __init__(self) -> None:
        self.seq = 0
        self.lanes: dict[str, dict[str, Any]] = {}
        self.lock = threading.Lock()


_FOLDS: "weakref.WeakKeyDictionary[Any, _ThrottleFold]" = weakref.WeakKeyDictionary()
_FOLDS_LOCK = threading.Lock()


def throttle_state(ledger: Any) -> dict[str, dict[str, Any]]:
    """lane -> its newest "lane throttle" row. Asked by every due agent's research gate and every step of the
    engineer, so it reads only the `ops.budget` rows written since the last call (one indexed query when none)."""
    try:
        with _FOLDS_LOCK:
            fold_ = _FOLDS.get(ledger)
            if fold_ is None:
                fold_ = _FOLDS[ledger] = _ThrottleFold()
    except TypeError:  # a ledger that cannot be weakly referenced: fold it afresh
        fold_ = _ThrottleFold()
    with fold_.lock:
        newest = ledger.read(kinds="ops.budget", limit=1, newest=True)
        if newest and newest[-1].seq > fold_.seq:
            for entry in ledger.iter(kinds="ops.budget", after=fold_.seq):
                fold_.seq = entry.seq
                if entry.payload.get("what") == THROTTLE_WHAT and entry.payload.get("lane"):
                    fold_.lanes[str(entry.payload["lane"])] = dict(entry.payload)
        return dict(fold_.lanes)


def throttled(ledger: Any, lane: str) -> bool:
    """Whether `lane` is halved now (Y1). Never raises: an unreadable state throttles nothing."""
    try:
        return bool((throttle_state(ledger).get(lane) or {}).get("throttled"))
    except Exception:  # noqa: BLE001 - the throttle saves money; it must never stop work by failing
        return False


# ------------------------------------------------------------------ Y2: unit economics
#: The kinds the compute line reads (scripts/economics.py `spend`, as scripts/gap_scoreboard.py counts it).
SPEND_KINDS = ("provider.request", "merton.pass", "audit.verdict", "agent.research", "ops.budget", "credit.charge")


def spend_of(kind: str, p: Mapping[str, Any]) -> tuple[str, Decimal] | None:
    """(provider, dollars) one ledger row adds to the compute line, or None. `sail-estimate` rows (research
    tokens and sandbox seconds at Sail's prices) count only where no Sail meter reading covers the window,
    as scripts/economics.py counts them."""
    if kind == "provider.request":
        if p.get("cost_verified") is True and p.get("cost_usd") is not None:
            return "openai-luna", _money(p.get("cost_usd"))
    elif kind in ("merton.pass", "audit.verdict"):
        return "openai-astra", _money(p.get("cost_usd"))
    elif kind == "agent.research":
        if (p.get("tool") == "research_grant" and p.get("status") == "completed") or p.get("tool") == "semantic_question_experiment":
            return "openai-astra", _money(p.get("cost_usd"))
    elif kind == "ops.budget":
        if p.get("what") == "sail" and p.get("spent_usd") is not None:
            return "sail", _money(p.get("spent_usd"))
        if p.get("what") not in ("sail", "payout") and p.get("cost_usd") is not None:
            return "openai-astra", _money(p.get("cost_usd"))  # the frontier probes
    elif kind == "credit.charge":
        what = str(p.get("what") or "")
        if what == "jev classification":
            return "jev", _money(p.get("usd"))
        if what == "web search":
            return "web-search", _money(p.get("usd"))
        if what in ("research tokens", "sandbox seconds"):
            return "sail-estimate", _money(p.get("usd"))
    return None


def seq_at(ledger: Any, stamp: str) -> int:
    """The last sequence number written before `stamp` (a binary search over the ledger's rows)."""
    head = int(ledger.head()[0])
    lo, hi = 0, head
    while lo < hi:
        mid = (lo + hi + 1) // 2
        rows = ledger.read(after=mid - 1, limit=1)
        if rows and rows[0].at < stamp:
            lo = mid
        else:
            hi = mid - 1
    return lo


class UnitEconomics:
    """Compute a day against real settled profit a day over the last `hours` (Y2), folded incrementally: the
    first reading scans the day's rows of `SPEND_KINDS` (about 57,000 at T0), later ones only the new rows.
    `lab_usd(since_epoch, until_epoch)` gives the Alpha Lab's own calls; `real_pnl` the real books' result."""

    def __init__(self, ledger: Any, clock: Any, *, real_pnl: Any = None, lab_usd: Any = None, hours: float = 24.0):
        from .merton import RealPnl

        self.ledger, self.clock, self.hours = ledger, clock, float(hours)
        self.real_pnl = real_pnl or RealPnl(ledger, clock, hours=hours, every_seconds=0)
        self.lab_usd = lab_usd
        self._rows: deque = deque()
        self._seq: int | None = None
        self._lock = threading.Lock()

    def reading(self) -> dict[str, Any]:
        with self._lock:
            now = self.clock()
            since = now_iso(lambda: now - self.hours * 3600)
            if self._seq is None:
                self._seq = seq_at(self.ledger, since)
            for entry in self.ledger.iter(kinds=SPEND_KINDS, after=self._seq):
                self._seq = entry.seq
                found = spend_of(entry.kind, entry.payload)
                if found is not None and found[1]:
                    self._rows.append((entry.at, found[0], found[1]))
            while self._rows and self._rows[0][0] < since:
                self._rows.popleft()
            providers: dict[str, Decimal] = {}
            for _, provider, usd in self._rows:
                providers[provider] = providers.get(provider, Decimal(0)) + usd
        estimate = providers.pop("sail-estimate", Decimal(0))
        if "sail" not in providers and estimate:
            providers["sail"] = estimate  # no meter reading in the day: Sail's own prices, an estimate
        lab = None
        if self.lab_usd is not None:
            try:
                lab = self.lab_usd(now - self.hours * 3600, now)
            except Exception:  # noqa: BLE001 - a lab store that cannot be read is left out
                lab = None
        if lab is not None:
            providers["openai-lab"] = _money(lab)
        compute = sum(providers.values(), Decimal(0))
        pnl, closes = self.real_pnl()
        days = Decimal(str(self.hours / 24))
        per_day, profit = compute / days, Decimal(pnl) / days
        return {"at": now_iso(lambda: now), "hours": self.hours,
                "compute_per_day_usd": round(float(per_day), 2), "profit_per_day_usd": round(float(profit), 2),
                "compute_over_profit": round(float(per_day / profit), 2) if profit > 0 else None,
                "providers_usd": {k: round(float(v), 4) for k, v in sorted(providers.items())}, "real_closes": closes,
                "measure": "compute: Luna's verified requests, Merton's and the auditor's metered passes, grants, the Sail meter, "
                           "Jev and web search, the lab's calls; profit: the real books' settlements and closing sales, net of fees"}


class YieldLedger:
    """Writes one `ops.budget` yield row an hour (`every_seconds`), covering the hour before it, with its
    `lift` section, after the `consult.outcome` rows that became due (Sept 25, 2026, F4); since Y1 and Y2
    also its `throttle` (the lanes it halves, with an `ops.budget` "lane throttle" row for each change)
    and `unit_economics`, which the House keeps for health.json."""

    def __init__(self, house: Any, *, every_seconds: float = 3600.0):
        self.house = house
        self.every_seconds = float(every_seconds)
        self._teacher: dict[str, Any] = {}  # `teacher_lift`'s incremental fold, for this process's life
        self._economics: UnitEconomics | None = None  # Y2's incremental fold, built at the first row

    def _state(self) -> dict[str, Any]:
        with self.house._state_lock:
            return self.house._state.setdefault("yield_ledger", {})

    def due(self) -> bool:
        return self.house.clock() - float(self._state().get("last") or 0) >= self.every_seconds

    def tick(self) -> dict[str, Any] | None:
        if not self.due():
            return None
        now = self.house.clock()
        since = now_iso(lambda: now - self.every_seconds)
        try:
            from . import strategies

            repairs = {row["name"]: isinstance(row.get("repair"), Mapping) for row in strategies.all_strategies()}
        except Exception:  # noqa: BLE001 - the strategy files are a refinement of the credit, never a reason to skip the row
            repairs = {}
        row = fold(self.house.ledger, since=since, until=now_iso(lambda: now), repairs=repairs,
                   lab_usd=self._lab_usd(now - self.every_seconds, now))
        with self.house._state_lock:
            self._state()["last"] = now
        recent = [e.payload for e in self.house.ledger.read(kinds="ops.budget", limit=DAY_ROWS, newest=True)
                  if e.payload.get("what") == WHAT and e.at >= now_iso(lambda: now - 86400 + 60)] + [row]
        lift = self._lift(now, row, recent)
        throttle = self._throttle(recent, lift)
        unit = self._unit_economics()
        self.house.ledger.append("ops.budget", {**row, "hours": round(self.every_seconds / 3600, 3), **({"lift": lift} if lift else {}),
                                                **({"throttle": {k: v for k, v in throttle.items() if k != "prices"}} if throttle else {}),
                                                **({"unit_economics": unit} if unit else {})})
        if throttle:
            self._apply(throttle)
        elif self._throttle_off():
            self._release()
        return row

    def _lab_usd(self, start: float, end: float) -> Decimal | None:
        """The Alpha Lab's own model calls between two instants (`lab.sqlite` `calls`, what the lab's
        positive blocks cost), or None where no lab runs or its store cannot be read."""
        lab = getattr(self.house, "lab", None)
        if lab is None or not hasattr(lab, "_q"):
            return None
        try:
            rows = lab._q("SELECT COALESCE(SUM(cost_usd), 0) AS usd FROM calls WHERE at >= ? AND at < ?", (start, end))
            return _money(rows[0]["usd"]) if rows else Decimal(0)
        except Exception:  # noqa: BLE001 - the lab's price is a refinement, never a reason to skip the row
            return None

    def _lift(self, now: float, row: Mapping[str, Any], recent: list[Mapping[str, Any]] | None = None) -> dict[str, Any] | None:
        """F4: write the consult outcomes that became due, then measure every lane. A failure here is an
        alert and a row without `lift`, never a missing yield row."""
        ledger = self.house.ledger
        try:
            from .ledger import KINDS
            from .merton import LIFT

            settings = {**LIFT, **{k: v for k, v in dict(((getattr(self.house, "game", None) or {}).get("merton") or {}).get("lift") or {}).items()
                                   if not str(k).startswith("_")}}
            if "consult.outcome" in KINDS:  # the kind ships with the owner's deploy (league/ledger.py)
                for item in consult_outcomes(ledger, now=now, settings=settings):
                    ledger.append("consult.outcome", item["payload"], agent=item["agent"], id=item["id"])
            if recent is None:
                recent = [e.payload for e in ledger.read(kinds="ops.budget", limit=DAY_ROWS, newest=True)
                          if e.payload.get("what") == WHAT and e.at >= now_iso(lambda: now - 86400 + 60)] + [row]
            state = getattr(getattr(getattr(self.house, "jev_floor", None), "state", None), "data", None) or {}
            return lifts(ledger, now=now, settings=settings, lesson_since=state.get("lesson_arm_since"), recent=recent, cache=self._teacher)
        except Exception as exc:  # noqa: BLE001 - the measurement never costs the hour's row
            try:
                self.house.alert("warning", f"yield ledger: the lanes' lift could not be measured ({type(exc).__name__}: {str(exc)[:160]})")
            except Exception:  # noqa: BLE001
                pass
            return None

    def _throttle(self, recent: list[Mapping[str, Any]], lift: Mapping[str, Any] | None) -> dict[str, Any] | None:
        """Y1: the lanes over `economy.lane_throttle` times the best lane's price. None when the dial is not
        set (the rule is off) or the measurement failed (an alert; the lanes keep their state)."""
        multiple = ((getattr(self.house, "game", None) or {}).get("economy") or {}).get("lane_throttle")
        if multiple in (None, "", 0):
            return None
        try:
            return plan_throttle(lane_prices(recent, lift), float(multiple))
        except Exception as exc:  # noqa: BLE001 - the throttle saves money; it never costs the hour's row
            try:
                self.house.alert("warning", f"yield ledger: the lane throttle could not be measured ({type(exc).__name__}: {str(exc)[:160]})")
            except Exception:  # noqa: BLE001
                pass
            return None

    def _throttle_off(self) -> bool:
        """Whether Y1 is switched off: `economy.lane_throttle` removed (the operator's off switch) or 0."""
        return ((getattr(self.house, "game", None) or {}).get("economy") or {}).get("lane_throttle") in (None, "", 0)

    def _release(self) -> list[dict[str, Any]]:
        """Y1 switched off: one "lane throttle" row putting back every lane the rows still hold halved. The review of
        Deploy C (Sept 25, 2026): `throttled()` reads each lane's newest row, and with the dial removed no plan was made,
        so nothing ever wrote the rows that lift a throttle -- research, the engineer, the consultant and the architect
        (all four halved on the T0 replay) stayed halved until a deploy or a ledger write."""
        written = []
        try:
            for lane, row in sorted(throttle_state(self.house.ledger).items()):
                if not row.get("throttled"):
                    continue
                payload = {"what": THROTTLE_WHAT, "lane": lane, "throttled": False, "multiple": None, "best": None,
                           "why": "economy.lane_throttle is off", "how": "back to its usual cadence and price"}
                self.house.ledger.append("ops.budget", payload)
                written.append(payload)
        except Exception as exc:  # noqa: BLE001 - tried again at the next hourly row
            try:
                self.house.alert("warning", f"yield ledger: the lane throttles could not be lifted ({type(exc).__name__}: {str(exc)[:160]})")
            except Exception:  # noqa: BLE001
                pass
        return written

    def _apply(self, plan: Mapping[str, Any]) -> list[dict[str, Any]]:
        """One `ops.budget` "lane throttle" row for each lane whose state changes, naming its price, the best
        lane's and the ratio. `throttled()` reads them; nothing else is written."""
        ledger = self.house.ledger
        current = throttle_state(ledger)
        written = []
        for lane, row in sorted((plan.get("lanes") or {}).items()):
            now = bool(row.get("throttled"))
            if bool((current.get(lane) or {}).get("throttled")) == now:
                continue
            payload = {"what": THROTTLE_WHAT, "lane": lane, "throttled": now, "multiple": plan.get("multiple"), "best": plan.get("best"),
                       **{k: row.get(k) for k in ("usd", "positive_blocks", "usd_per_positive_block", "ratio", "why")},
                       "how": THROTTLE_HOW[lane] if now else "back to its usual cadence and price"}
            ledger.append("ops.budget", payload)
            written.append(payload)
        return written

    def _unit_economics(self) -> dict[str, Any] | None:
        """Y2: compute a day against real settled profit a day, kept in the House's state for health.json."""
        try:
            if self._economics is None:
                self._economics = UnitEconomics(self.house.ledger, self.house.clock, lab_usd=self._lab_usd)
            unit = self._economics.reading()
        except Exception as exc:  # noqa: BLE001 - a reading that fails is said once an hour, never a missing row
            try:
                self.house.alert("warning", f"yield ledger: the unit economics could not be read ({type(exc).__name__}: {str(exc)[:160]})")
            except Exception:  # noqa: BLE001
                pass
            return None
        with self.house._state_lock:
            self._state()["unit_economics"] = unit
        return unit
