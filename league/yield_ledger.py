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
"""

from __future__ import annotations

from collections import Counter
from decimal import Decimal
from typing import Any, Mapping

from .ledger import now_iso

WHAT = "yield"
ROLES = ("architect", "engineer", "consultant", "teacher", "foundry", "toolsmith", "operator", "designer")


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


class YieldLedger:
    """Writes one `ops.budget` yield row an hour (`every_seconds`), covering the hour before it."""

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
        self.house.ledger.append("ops.budget", {**row, "hours": round(self.every_seconds / 3600, 3)})
        return row
