"""The repair worklist: every useful criticism of the floor, as a durable, deduplicated job.

Audit vetoes, repeated order refusals, failed pull requests, missing-data requests and research
sessions that name a missing input were, until Sept 22, 2026, rows nobody picked up: 5 of 7
audits vetoed with a named defect, 132 refusals of six agents said the same thing about the
horizon rule, 54 tool requests were marked blocked and then sat, and 12 of Merton's 66 pull
requests were refused by CI and never looked at again. Each is now reported here and worked
by the repair engineer (`league/engineer.py`).

Two ledger kinds hold all of it, and this module is their only reader:

- `repair.reported` `{key, kind, summary, evidence, agents, source, severity}`: the same `key`
  reported again appends a row, and the fold merges them -- evidence and affected agents are
  unioned, the ORIGINAL evidence is always kept, and recurrence is counted. Optional
  `through_seq` (every signal row of that source up to this ledger seq is accounted for) and
  `occurrences` (how many signal rows this report stands for, when the evidence is capped).
- `repair.status` `{key, state, note, pr, commit, cost_usd, attempt}`: one transition.
  `cost_usd` is what THAT step spent (the fold adds them up), so a rejected or dormant job keeps
  every dollar it cost. Keys starting `_` are private working state (the engineer's last files).

Priority is distinct agents affected x recurrence x severity. A job is complete only when its
fix is running and the triggering signal has stopped: `verified` is written after an
observation window with no recurrence following deployment of the fix, never when a PR merges.

The sources below are code: exact kinds, exact fields, fixed thresholds, no model. Jev triage
(another component) writes `repair.reported` with `source: "triage"` and is folded like any other.
"""

from __future__ import annotations

import hashlib
import re
import threading
import time
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Iterable, Mapping

STATES = ("proposed", "admitted", "reproducing", "patching", "testing", "revising", "canary", "observing",
          "verified", "rejected", "dormant")
#: States a job can still move out of by itself.
OPEN = STATES[:8]
TERMINAL = ("verified", "rejected", "dormant")
#: States the engineer is actively carrying (admitted and later, not yet finished).
WORKING = ("admitted", "reproducing", "patching", "testing", "revising", "canary", "observing")
KINDS = ("strategy_defect", "shared_defect", "missing_data", "order_refusal", "ci_failure", "audit_veto", "bug_report")
SOURCES = ("audit", "refusals", "ci", "triage", "consult", "operator", "synthetic", "research", "tools")
#: Severity words to weights. A number in [0.1, 5] is taken as it is.
SEVERITY = {"blocker": 3.0, "critical": 3.0, "high": 2.0, "major": 2.0, "medium": 1.0, "moderate": 1.0,
            "low": 0.5, "minor": 0.5, "note": 0.25}
#: Working state a status row may carry that later rows need (`Job.carry`).
CARRIED = ("_failure", "_files", "failed_pr", "_proposal", "digests")
#: Evidence kept in memory per job: the first rows (the original evidence) and the latest.
KEEP_FIRST, KEEP_LAST = 8, 24
EXCERPT_CHARS = 1200


def severity_weight(value: Any) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return max(0.1, min(float(value), 5.0))
    return SEVERITY.get(str(value or "").strip().lower(), 1.0)


def _usd(value: Any) -> Decimal:
    try:
        amount = Decimal(str(value if value is not None else "0"))
    except (InvalidOperation, ValueError):
        return Decimal(0)
    return amount if amount.is_finite() and amount > 0 else Decimal(0)


def digest(text: str, n: int = 12) -> str:
    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()[:n]


@dataclass
class Job:
    key: str
    kind: str
    summary: str
    source: str
    severity: float = 1.0
    sources: set[str] = field(default_factory=set)
    agents: set[str] = field(default_factory=set)
    first: list[dict[str, Any]] = field(default_factory=list)
    recent: list[dict[str, Any]] = field(default_factory=list)
    #: (at, agent, seq) of every evidence row, for recurrence after a deployment.
    seen: list[tuple[str, str, int | None]] = field(default_factory=list)
    marks: set[tuple[Any, ...]] = field(default_factory=set)
    occurrences: int = 0
    reports: int = 0
    first_at: str = ""
    last_at: str = ""
    through: dict[str, int] = field(default_factory=dict)
    details: dict[str, Any] = field(default_factory=dict)
    state: str = "proposed"
    state_at: str = ""
    note: str = ""
    pr: int | None = None
    commit: str | None = None
    cost_usd: Decimal = Decimal(0)
    attempt: int = 0
    history: list[dict[str, Any]] = field(default_factory=list)
    last_status: dict[str, Any] = field(default_factory=dict)
    #: The latest value of each piece of working state any status row carried (the last CI
    #: failure text, the files it judged, the paid proposal waiting for the forge, the digests).
    carry: dict[str, Any] = field(default_factory=dict)

    @property
    def recurrence(self) -> int:
        return max(1, self.occurrences)

    def priority(self) -> float:
        """Distinct agents affected x recurrence x severity. A House-level defect with no agent
        attached counts as one agent."""
        return round(max(1, len(self.agents)) * self.recurrence * self.severity, 4)

    @property
    def evidence(self) -> list[dict[str, Any]]:
        """The original evidence first, then the latest, without repeats."""
        out, marks = [], set()
        for row in self.first + self.recent:
            mark = (row.get("seq"), row.get("at"), row.get("agent"), row.get("excerpt"))
            if mark not in marks:
                marks.add(mark)
                out.append(row)
        return out

    def evidence_after(self, at: str, *, excluding: Iterable[str] = ()) -> list[tuple[str, str, int | None]]:
        """Evidence rows stamped after `at` (ISO, comparable as text), except from `excluding`."""
        skip = set(excluding)
        return [row for row in self.seen if row[0] > at and row[1] not in skip]

    def view(self) -> dict[str, Any]:
        return {"key": self.key, "kind": self.kind, "summary": self.summary, "source": self.source,
                "sources": sorted(self.sources), "severity": self.severity, "agents": sorted(self.agents),
                "recurrence": self.recurrence, "reports": self.reports, "priority": self.priority(),
                "first_at": self.first_at, "last_at": self.last_at, "state": self.state, "state_at": self.state_at,
                "note": self.note, "pr": self.pr, "commit": self.commit, "cost_usd": format(self.cost_usd, "f"),
                "attempt": self.attempt, "evidence": self.evidence[:12]}


def _clean_evidence(rows: Any, agent_default: str) -> list[dict[str, Any]]:
    out = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        seq = row.get("seq")
        out.append({"seq": int(seq) if isinstance(seq, int) and not isinstance(seq, bool) else None,
                    "at": str(row.get("at") or "")[:40], "agent": str(row.get("agent") or agent_default)[:120],
                    "excerpt": str(row.get("excerpt") or "")[:EXCERPT_CHARS]})
    return out


def apply(jobs: dict[str, Job], kind: str, payload: Mapping[str, Any], *, at: str, seq: int, agent: str = "house") -> None:
    """Fold one ledger row into `jobs` (in place)."""
    key = payload.get("key")
    if not isinstance(key, str) or not 1 <= len(key) <= 200:
        return
    if kind == "repair.reported":
        job = jobs.get(key)
        if job is None:
            job = jobs[key] = Job(key=key, kind=str(payload.get("kind") if payload.get("kind") in KINDS else "bug_report"),
                                  summary=str(payload.get("summary") or "")[:2000], source=str(payload.get("source") or "operator")[:40],
                                  first_at=at, state_at=at)
        job.reports += 1
        job.last_at = at
        job.sources.add(str(payload.get("source") or "operator")[:40])
        job.severity = max(job.severity if job.reports > 1 else 0.0, severity_weight(payload.get("severity")))
        job.agents.update(str(a)[:120] for a in (payload.get("agents") or []) if isinstance(a, str) and a and a != "house")
        new = 0
        for row in _clean_evidence(payload.get("evidence"), agent):
            mark = (row["seq"], row["agent"], row["excerpt"][:200]) if row["seq"] is not None else (row["at"], row["agent"], row["excerpt"][:200])
            if mark in job.marks:
                continue
            job.marks.add(mark)
            new += 1
            job.seen.append((row["at"] or at, row["agent"], row["seq"]))
            if row["agent"] and row["agent"] != "house":
                job.agents.add(row["agent"])
            if len(job.first) < KEEP_FIRST:
                job.first.append(row)
            else:
                job.recent = (job.recent + [row])[-KEEP_LAST:]
        counted = payload.get("occurrences")
        job.occurrences += int(counted) if isinstance(counted, int) and not isinstance(counted, bool) and counted > 0 else max(new, 1 if not payload.get("evidence") else 0)
        through = payload.get("through_seq")
        if isinstance(through, int) and not isinstance(through, bool):
            source = str(payload.get("source") or "")
            job.through[source] = max(job.through.get(source, 0), through)
        if isinstance(payload.get("details"), dict):
            job.details.update(payload["details"])
        return
    if kind == "repair.status":
        state = payload.get("state")
        job = jobs.get(key)
        if job is None or state not in STATES:
            return
        job.state, job.state_at = str(state), at
        job.note = str(payload.get("note") or "")[:2000]
        if "pr" in payload:
            # Every row says which pull request is in play: a new attempt starts with none, so a
            # revision never goes on following the refused PR of the attempt before it.
            job.pr = payload["pr"] if isinstance(payload["pr"], int) and not isinstance(payload["pr"], bool) else None
        if isinstance(payload.get("commit"), str) and payload["commit"]:
            job.commit = payload["commit"][:80]
        job.cost_usd += _usd(payload.get("cost_usd"))
        attempt = payload.get("attempt")
        if isinstance(attempt, int) and not isinstance(attempt, bool):
            # The latest row says how many attempts count: a call the frontier refused before
            # anything was bought is written back with the count it had.
            job.attempt = attempt
        for name in CARRIED:
            if payload.get(name) is not None:
                job.carry[name] = payload[name]
        job.last_status = {**dict(payload), "at": at, "seq": seq}
        job.history.append({k: payload.get(k) for k in ("state", "note", "pr", "commit", "cost_usd", "attempt")} | {"at": at, "seq": seq})


def fold(rows: Iterable[Any]) -> dict[str, Job]:
    jobs: dict[str, Job] = {}
    for entry in rows:
        apply(jobs, entry.kind, entry.payload, at=entry.at, seq=entry.seq, agent=entry.agent)
    return jobs


class Worklist:
    """The fold over the ledger, kept current incrementally, and the only writer of repair rows."""

    def __init__(self, ledger: Any, *, clock: Callable[[], float] = time.time):
        self.ledger = ledger
        self.clock = clock
        self._jobs: dict[str, Job] = {}
        self._after = 0
        self._lock = threading.RLock()

    def jobs(self) -> dict[str, Job]:
        with self._lock:
            for entry in self.ledger.iter(kinds=("repair.reported", "repair.status"), after=self._after):
                apply(self._jobs, entry.kind, entry.payload, at=entry.at, seq=entry.seq, agent=entry.agent)
                self._after = entry.seq
            return self._jobs

    def get(self, key: str) -> Job | None:
        return self.jobs().get(key)

    def queue(self, states: Iterable[str] = OPEN) -> list[Job]:
        """Jobs in these states, highest priority first; ties go to the oldest report."""
        wanted = set(states)
        return sorted((j for j in self.jobs().values() if j.state in wanted), key=lambda j: (-j.priority(), j.first_at, j.key))

    def report(self, *, key: str, kind: str, summary: str, evidence: list[dict[str, Any]], agents: Iterable[str],
               source: str, severity: Any, through_seq: int | None = None, occurrences: int | None = None,
               details: Mapping[str, Any] | None = None, id: str | None = None) -> Any:
        payload: dict[str, Any] = {"key": key, "kind": kind if kind in KINDS else "bug_report", "summary": str(summary)[:2000],
                                   "evidence": _clean_evidence(evidence, "house")[:16], "agents": sorted({a for a in agents if a})[:200],
                                   "source": source, "severity": severity}
        if through_seq is not None:
            payload["through_seq"] = int(through_seq)
        if occurrences is not None:
            payload["occurrences"] = int(occurrences)
        if details:
            payload["details"] = dict(details)
        return self.ledger.append("repair.reported", payload, id=id or f"repair:{digest(key, 16)}:{source}:{through_seq or digest(repr(payload), 12)}")

    def transition(self, key: str, state: str, *, note: str = "", pr: int | None = None, commit: str | None = None,
                   cost_usd: Any = "0", attempt: int = 0, extra: Mapping[str, Any] | None = None, id: str | None = None) -> Any:
        if state not in STATES:
            raise ValueError(f"no such repair state {state!r}")
        payload = {"key": key, "state": state, "note": str(note)[:2000], "pr": pr, "commit": commit,
                   "cost_usd": format(_usd(cost_usd), "f"), "attempt": int(attempt), **dict(extra or {})}
        return self.ledger.append("repair.status", payload, id=id)

    def admit(self, *, threshold: float, limit: int = 10) -> list[str]:
        """Proposed jobs whose priority has reached the line become admitted, highest first.
        Operator and synthetic reports are admitted whatever their priority: someone asked."""
        admitted = []
        for job in self.queue(("proposed",)):
            if len(admitted) >= limit:
                break
            if job.priority() >= threshold or job.sources & {"operator", "synthetic"}:
                self.transition(job.key, "admitted", note=f"priority {job.priority()} (agents {max(1, len(job.agents))} x "
                                f"recurrence {job.recurrence} x severity {job.severity})")
                admitted.append(job.key)
        return admitted

    def summary(self, limit: int = 20) -> dict[str, Any]:
        jobs = self.jobs().values()
        counts: dict[str, int] = {}
        for job in jobs:
            counts[job.state] = counts.get(job.state, 0) + 1
        return {"counts": counts, "cost_usd": format(sum((j.cost_usd for j in jobs), Decimal(0)), "f"),
                "top": [j.view() for j in self.queue()[:limit]]}


# ------------------------------------------------------------------------------ the sources
@dataclass(frozen=True)
class Signal:
    key: str
    kind: str
    summary: str
    source: str
    severity: Any
    agent: str
    seq: int
    at: str
    excerpt: str
    wake: str = ""
    details: tuple[tuple[str, Any], ...] = ()


_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_TICKER = re.compile(r"\b[A-Z][A-Z0-9#]*#[A-Z0-9#-]*\b")


def normalize_reason(reason: str, agent: str = "") -> str:
    """A refusal's reason with the parts that differ between identical refusals taken out: the
    agent's own name, numbers and market tickers."""
    text = str(reason or "")
    if agent:
        # As a whole name only: agent "a" must not turn "market" into "m<agent>rket".
        text = re.sub(rf"(?<![\w-]){re.escape(agent)}(?![\w-])", "<agent>", text)
    text = _NUMBER.sub("#", text)
    text = _TICKER.sub("<market>", text)
    return re.sub(r"\s+", " ", text).strip()[:160]


def _name(value: Any) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", str(value or "").lower()).strip("_")[:60]


#: A research summary that names a missing input, and the phrasings that say the opposite.
MISSING = re.compile(r"\b(missing (?:feed|input|inputs|data|history)|unsupported inputs?|not recorded on (?:the |equity )?tapes?|"
                     r"no (?:historical|point-in-time|recorded) [a-z-]+(?: [a-z-]+)? (?:feed|data|history|panel))\b", re.I)
NEGATED = re.compile(r"\b(not (?:the|a) blocker|is not missing|was wrong|withdrawn|is resolved|no unsupported)\b", re.I)


class Sources:
    """The deterministic reporters. `scan()` reads only ledger rows it has not read in this
    process, keeps the running totals the thresholds need, and writes one `repair.reported` per
    key with what is new. A restart reads everything once more; what was already reported is
    known from the fold (`through_seq`) and the ledger ids repeat, so nothing is reported twice.

    Thresholds (Sept 22, 2026, from the production ledger): a refusal reason is a repair only
    once it has refused three agents or three wakes (238 rows of one reason from two agents is
    one broken thing, not noise); a research citation of a missing input only after two sessions
    of the same specialty; one audit veto is enough -- the auditor already names the defect."""

    #: Kinds each scan reads. `merton.change` is read whole (it is small) to know the latest state.
    READS = ("audit.verdict", "book.refused", "merton.change", "tool.request", "tool.blocked", "tool.fulfilled", "agent.research",
             "merton.pass")
    REFUSAL_MIN = 3
    RESEARCH_MIN = 2
    MAX_EVIDENCE = 12

    def __init__(self, ledger: Any, worklist: Worklist, *, niche_of: Callable[[str], str | None] | None = None):
        self.ledger = ledger
        self.worklist = worklist
        self.niche_of = niche_of or (lambda agent: None)
        self._after = 0
        self._refusals: dict[str, dict[str, Any]] = {}
        self._research: dict[str, dict[str, Any]] = {}
        self._requests: dict[str, str] = {}  # tool.request id -> key
        self._changes: dict[int, dict[str, Any]] = {}
        self._pending: dict[str, list[Signal]] = {}
        self._lock = threading.Lock()

    # -------------------------------------------------------------------------- reading
    def _read(self) -> None:
        for entry in self.ledger.iter(kinds=self.READS, after=self._after):
            self._after = entry.seq
            try:
                self._one(entry)
            except (TypeError, ValueError, KeyError, AttributeError):
                continue  # one odd row must not stop the scan

    def _emit(self, signal: Signal) -> None:
        self._pending.setdefault(signal.key, []).append(signal)

    def _one(self, entry: Any) -> None:
        p, kind = entry.payload, entry.kind
        if kind == "audit.verdict":
            if p.get("approve") is not False or p.get("error"):
                return
            findings = [f for f in p.get("findings") or [] if isinstance(f, dict)]
            blockers = [f for f in findings if str(f.get("severity") or "").lower() == "blocker"]
            issues = "; ".join(str(f.get("issue") or "")[:200] for f in (blockers or findings)[:4])
            self._emit(Signal(key=f"audit_veto:{entry.agent}", kind="audit_veto",
                              summary=f"The auditor vetoed {entry.agent} ({p.get('book')}): {str(p.get('summary') or '')[:600]}",
                              source="audit", severity="blocker" if blockers else "high", agent=entry.agent, seq=entry.seq,
                              at=entry.at, excerpt=f"{str(p.get('summary') or '')[:500]} Findings: {issues}"[:EXCERPT_CHARS],
                              details=(("book", p.get("book")),)))
        elif kind == "book.refused":
            for reason in p.get("reasons") or []:
                normal = normalize_reason(str(reason), entry.agent)
                key = f"order_refusal:{p.get('book')}:{normal[:100]}"
                total = self._refusals.setdefault(key, {"agents": set(), "wakes": set()})
                total["agents"].add(entry.agent)
                total["wakes"].add((entry.agent, entry.at[:16]))
                symbol = (p.get("instrument") or {}).get("symbol") if isinstance(p.get("instrument"), dict) else None
                self._emit(Signal(key=key, kind="order_refusal", summary=f"The {p.get('book')} book refuses: {normal}",
                                  source="refusals", severity="medium", agent=entry.agent, seq=entry.seq, at=entry.at,
                                  excerpt=f"{str(reason)[:400]} ({symbol})", wake=entry.at[:16]))
        elif kind == "merton.change":
            number = p.get("number")
            if not isinstance(number, int):
                return
            self._changes[number] = {**dict(p), "_seq": entry.seq, "_at": entry.at}
        elif kind == "tool.request":
            key = f"missing_data:{_name(p.get('name'))}"
            self._requests[entry.id] = key
            self._emit(Signal(key=key, kind="missing_data", summary=f"Agents ask for {_name(p.get('name'))}: {str(p.get('description') or '')[:600]}",
                              source="tools", severity="medium", agent=entry.agent, seq=entry.seq, at=entry.at,
                              excerpt=str(p.get("description") or "")[:EXCERPT_CHARS], details=(("requests", entry.id),)))
        elif kind in ("tool.blocked", "tool.fulfilled"):
            key = self._requests.get(str(p.get("request")))
            outcome = str(p.get("outcome") or "")
            blocked = kind == "tool.blocked" or (p.get("status") == "answered" and outcome.lower().startswith("cannot be a pure tool"))
            if key is None or not blocked:
                return
            self._emit(Signal(key=key, kind="missing_data", summary="", source="tools", severity="medium", agent="house",
                              seq=entry.seq, at=entry.at, excerpt=("The toolsmith found it cannot be a pure tool: " + outcome)[:EXCERPT_CHARS],
                              details=(("blocked", True),)))
        elif kind == "merton.pass":
            # A consultation that named a missing tool: the same key as an agent's own request for
            # it, so the paid advice and the requests become one job (4 of 40 consults by Sept 22).
            tool = p.get("tool") if isinstance(p.get("tool"), dict) else None
            if p.get("role") != "consultant" or not tool or not _name(tool.get("name")):
                return
            agent = str(p.get("agent") or entry.agent)
            self._emit(Signal(key=f"missing_data:{_name(tool.get('name'))}", kind="missing_data",
                              summary=f"Merton, consulted by {agent}, names a missing tool {_name(tool.get('name'))}: {str(tool.get('description') or '')[:600]}",
                              source="consult", severity="medium", agent=agent, seq=entry.seq, at=entry.at,
                              excerpt=f"{str(tool.get('description') or '')[:700]} (answer: {str(p.get('answer') or '')[:400]})"))
        elif kind == "agent.research":
            if p.get("tool") != "summary":
                return
            text = str(p.get("summary") or "")
            found = [m for m in MISSING.finditer(text)]
            if not found or NEGATED.search(text):
                return
            niche = self.niche_of(entry.agent) or re.sub(r"-\d+$", "", entry.agent)
            key = f"missing_data:research:{niche}"
            total = self._research.setdefault(key, {"sessions": set()})
            total["sessions"].add(str(p.get("session") or entry.id))
            self._emit(Signal(key=key, kind="missing_data", summary=f"Research in {niche} keeps stopping at a missing input",
                              source="research", severity="low", agent=entry.agent, seq=entry.seq, at=entry.at,
                              excerpt=text[:EXCERPT_CHARS]))

    def _ci_signals(self) -> None:
        for number, row in self._changes.items():
            if row.get("status") != "refused by CI" or row.get("repair"):
                continue  # a repair's own PR is followed by its job, not reported again
            self._emit(Signal(key=f"ci_failure:pr-{number}", kind="ci_failure",
                              summary=f"CI refused Merton's {row.get('role')} change #{number}: {str(row.get('title') or '')[:200]}",
                              source="ci", severity="medium", agent="house", seq=int(row["_seq"]), at=str(row["_at"]),
                              excerpt=f"{row.get('branch')} changed {', '.join(str(x) for x in (row.get('paths') or [])[:8])}",
                              details=(("pr", number), ("role", row.get("role")), ("paths", list(row.get("paths") or [])[:12]))))

    # -------------------------------------------------------------------------- writing
    def _ready(self, key: str) -> bool:
        if key.startswith("order_refusal:"):
            total = self._refusals.get(key) or {}
            return len(total.get("agents") or ()) >= self.REFUSAL_MIN or len(total.get("wakes") or ()) >= self.REFUSAL_MIN
        if key.startswith("missing_data:research:"):
            return len((self._research.get(key) or {}).get("sessions") or ()) >= self.RESEARCH_MIN
        return True

    def scan(self) -> list[str]:
        """Read what is new and report it. Returns the keys reported."""
        with self._lock:
            self._read()
            self._ci_signals()
            jobs = self.worklist.jobs()
            reported = []
            for key in sorted(self._pending):
                if not self._ready(key):
                    continue  # kept, and reported with everything once the threshold is met
                signals = self._pending.pop(key)
                by_source: dict[str, list[Signal]] = {}
                for signal in signals:
                    by_source.setdefault(signal.source, []).append(signal)
                job = jobs.get(key)
                for source, rows in sorted(by_source.items()):
                    done = job.through.get(source, 0) if job else 0
                    fresh = sorted({s.seq: s for s in rows if s.seq > done}.values(), key=lambda s: s.seq)
                    if not fresh:
                        continue
                    head = next((s for s in fresh if s.summary), fresh[0])
                    details: dict[str, Any] = {}
                    for s in fresh:
                        for name, value in s.details:
                            if name == "requests":
                                details.setdefault("requests", []).append(value)
                            else:
                                details[name] = value
                    if "requests" in details:
                        details["requests"] = details["requests"][-40:]
                    evidence = [{"seq": s.seq, "at": s.at, "agent": s.agent, "excerpt": s.excerpt} for s in fresh]
                    if len(evidence) > self.MAX_EVIDENCE:
                        evidence = evidence[:4] + evidence[-(self.MAX_EVIDENCE - 4):]
                    self.worklist.report(key=key, kind=head.kind, summary=head.summary or (job.summary if job else key), evidence=evidence,
                                         agents={s.agent for s in fresh if s.agent != "house"}, source=source, severity=head.severity,
                                         through_seq=fresh[-1].seq, occurrences=len(fresh), details=details or None)
                    reported.append(key)
            return reported
