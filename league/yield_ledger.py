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
`lab.sqlite`, not on the ledger, so they are not here; its graduations are.

Evidence. Candidates are research summaries that retained one (`agent.research` `tool: summary`,
`candidate: true`); replay passes are `eval.trial` rows with `passed`, credited to the line that wrote
the code (a card's line to the foundry, `lab:` founders to the lab, a merged repair's child to the
engineer, an architect's strategy to the architect, everything else to research); positive forward
blocks are active `eval.block` rows with positive log growth, credited the same way; cards and lessons
are counted for the foundry and the teacher. `usd_per` divides a line's spend by each unit it produced.
A lesson is a `playbook.entry` the teacher wrote (`source: teacher`): until Sept 25, 2026 every
post-mortem counted, 111 of the 117 "lessons" of the 24 hours to T0 (the teacher wrote 6).

The forward lift (Sept 25, 2026, the forward-first run, F4; `lift` on the row, `lifts()`). Pricing a
lane is not measuring it: in the 24 hours to T0 the consultant cost $28.72 for 51 answers and nothing
said whether one made an agent trade better. Over the last `merton.lift.days` (7):

- the teacher: forward growth per active block over `teacher_days` (3) after each lesson, of the agents
  the lesson names (desk, specialty or family), split by `research_gate.lesson_arm`: under the gate's
  `lesson_arm: parity` a lesson wakes the research of the even half only, so the odd half is a control
  that was not steered to it. Counted from `lesson_since`, when the gate first split the arms.
- the consultant: a `consult.outcome` row for each paid consult at two stages -- `sessions`, whether the
  agent retained a candidate or changed its strategy within two sessions (`merton.consult_verdict`; an
  unproductive one doubles its next consult's price, `Merton.consult_price_multiple`), and `blocks`,
  its next `consult_blocks` (6) active forward blocks against its previous ones (`merton.consult_blocks`)
  -- and their mean lift, dollars per positive block after, against research's over the last day.
- the engineer: repairs verified (`repair.status` `verified`, one per key) per dollar of its passes,
  over the window and lifetime (22 for $26.59 at T0).

Each lane's `verdict` is `lift` when the one-sided 80% lower bound of its lift is above zero (the
engineer: a verified repair in the window), `no_lift` when it is not on at least `min_blocks` (30)
blocks an arm (the consultant: 10 judged consults), and `insufficient` otherwise. A lane with no lift
at the end of the run goes into `merton.paused_until_profit` (the teacher and, since Sept 25, 2026, the
consultant are allowed there).
"""

from __future__ import annotations

import math
from collections import Counter
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


def fold(ledger: Any, *, since: str, until: str | None = None, repairs: Mapping[str, bool] | None = None) -> dict[str, Any]:
    """The spend and evidence of every line between two ledger stamps (ISO, inclusive of `since`).

    `by_profile` (Sept 24, 2026, L2): research by the model profile each session ran on (its summary
    row's `profile`: Sail's `pro_asap`, `flash_asap` ..., `openai_luna`): sessions, candidates,
    provider failures, the dollars its research tokens were charged (every turn of the session, even
    one charged before the window began) and candidates per dollar."""
    spend: Counter = Counter()
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
            "_var": var}


def _lower(lift: float | None, *variances_over_n: float | None) -> float | None:
    """The one-sided 80% lower bound of a difference of means (Welch's standard error)."""
    if lift is None or any(v is None for v in variances_over_n):
        return None
    return lift - Z80 * math.sqrt(sum(variances_over_n))


def teacher_lift(ledger: Any, *, now: float, since: str | None, days: float = 7, teacher_days: float = 3,
                 min_blocks: int = MIN_BLOCKS) -> dict[str, Any]:
    """F4: forward growth over `teacher_days` after each teacher's lesson written in the last `days`
    (and after `since`, when the gate first split the arms), of the agents it names, by
    `research_gate.lesson_arm`. A block counts once per arm however many lessons name its agent."""
    from .research_gate import lesson_arm, lesson_terms, lesson_words

    if not since:
        return {"verdict": "not_started", "note": "the research gate has not split the lesson arms (research.gate.lesson_arm)"}
    start = max(_epoch(since), now - days * 86400)
    lessons = [e for e in ledger.iter(kinds="playbook.entry") if e.payload.get("source") == "teacher" and _epoch(e.at) >= start]
    words: dict[str, set[str]] = {}
    born: dict[str, float] = {}
    for entry in ledger.iter(kinds="agent.born"):
        p = entry.payload
        words[entry.agent] = lesson_words(entry.agent, p.get("specialty"), p.get("niche"), p.get("family"))
        born[entry.agent] = _epoch(entry.at)
    died = {e.agent: _epoch(e.at) for e in ledger.iter(kinds="agent.died")}
    blocks: dict[str, list[tuple[int, float, float]]] = {}
    for entry in ledger.iter(kinds="eval.block"):
        if entry.payload.get("active"):
            blocks.setdefault(entry.agent, []).append((entry.seq, _epoch(entry.at), float(entry.payload.get("log_growth") or 0)))
    seen: dict[str, dict[tuple[str, int], float]] = {"lesson": {}, "control": {}}
    agents: dict[str, set[str]] = {"lesson": set(), "control": set()}
    complete = 0
    for lesson in lessons:
        at = _epoch(lesson.at)
        complete += at + teacher_days * 86400 <= now
        terms = lesson_terms(lesson)  # as the gate's `lesson_names` reads it
        for agent, named in words.items():
            if born[agent] > at or died.get(agent, float("inf")) < at or not any(word in terms for word in named):
                continue
            arm = lesson_arm(agent)
            agents[arm].add(agent)
            for seq, t, growth in blocks.get(agent, ()):
                if at < t <= at + teacher_days * 86400:
                    seen[arm][(agent, seq)] = growth
    treated, control = _arm(list(seen["lesson"].values())), _arm(list(seen["control"].values()))
    lift = (treated["mean_log_growth"] - control["mean_log_growth"]
            if treated["mean_log_growth"] is not None and control["mean_log_growth"] is not None else None)
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
    for consult in consults_of(ledger):
        age = now - _epoch(consult.at)
        if age > 2 * days * 86400:
            continue
        agent = str(consult.payload["agent"])
        base = {"consult_seq": consult.seq, "agent": agent, "consulted_at": consult.at,
                "cost_usd": str(consult.payload.get("cost_usd") or "0"), "wrote_code": bool(consult.payload.get("wrote_code"))}
        if (consult.seq, "sessions") not in judged:
            rows = list(ledger.iter(kinds=("agent.research", "agent.strategy"), agent=agent, after=consult.seq))
            verdict = consult_verdict(consult, rows, sessions=sessions)
            if verdict is None and age >= 3 * 86400:
                done = sum(1 for e in rows if e.payload.get("tool") == "summary")
                verdict = {"productive": False, "by": None, "sessions": done, "expired": True}
            if verdict is not None:
                out.append({"id": f"consult-outcome:{consult.seq}:sessions", "agent": agent,
                            "payload": {**base, "stage": "sessions", **verdict, "doubles_next_price": not verdict["productive"]}})
        if (consult.seq, "blocks") not in judged:
            before, after = consult_blocks(ledger, consult, n=n)
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
          recent: Iterable[Mapping[str, Any]] = ()) -> dict[str, Any]:
    """The `lift` section of the hourly yield row (F4): the teacher, the consultant and the engineer
    over the last `days`, and research's dollars per positive forward block over `recent` rows."""
    from .merton import LIFT

    s = {**LIFT, **dict(settings or {})}
    days = float(s["days"])
    research = research_usd_per_positive_block(recent)
    return {"days": days, "research_usd_per_positive_block_24h": research,
            "teacher": teacher_lift(ledger, now=now, since=lesson_since, days=days, teacher_days=float(s["teacher_days"])),
            "consultant": consultant_lift(ledger, now=now, days=days, research_usd_per_positive_block=research),
            "engineer": engineer_lift(ledger, now=now, days=days)}


class YieldLedger:
    """Writes one `ops.budget` yield row an hour (`every_seconds`), covering the hour before it, with its
    `lift` section, after the `consult.outcome` rows that became due (Sept 25, 2026, F4)."""

    def __init__(self, house: Any, *, every_seconds: float = 3600.0):
        self.house = house
        self.every_seconds = float(every_seconds)

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
        row = fold(self.house.ledger, since=since, until=now_iso(lambda: now), repairs=repairs)
        with self.house._state_lock:
            self._state()["last"] = now
        lift = self._lift(now, row)
        self.house.ledger.append("ops.budget", {**row, "hours": round(self.every_seconds / 3600, 3), **({"lift": lift} if lift else {})})
        return row

    def _lift(self, now: float, row: Mapping[str, Any]) -> dict[str, Any] | None:
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
            recent = [e.payload for e in ledger.read(kinds="ops.budget", limit=200, newest=True)
                      if e.payload.get("what") == WHAT and e.at >= now_iso(lambda: now - 86400 + 60)] + [row]
            state = getattr(getattr(getattr(self.house, "jev_floor", None), "state", None), "data", None) or {}
            return lifts(ledger, now=now, settings=settings, lesson_since=state.get("lesson_arm_since"), recent=recent)
        except Exception as exc:  # noqa: BLE001 - the measurement never costs the hour's row
            try:
                self.house.alert("warning", f"yield ledger: the lanes' lift could not be measured ({type(exc).__name__}: {str(exc)[:160]})")
            except Exception:  # noqa: BLE001
                pass
            return None
