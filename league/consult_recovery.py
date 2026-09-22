"""Recover the work that past consultations named and nobody did.

By Sept 22, 2026 agents had hired Merton (`ask_merton`) forty times and written some 7,400
research-session summaries. Those texts hold concrete engineering work: a named defect in the
agent's own file ("your file currently cancels only by age"), a tool Merton asked the House to
build for the agent, and missing-data claims repeated pass after pass ("the point-in-time
earnings panel is still unavailable"). None of it reached a queue unless the agent itself filed a
`request_tool`, and even then only as a line in the toolsmith's list. This module turns those
texts into `repair.reported` rows (`source: consult`) with the original excerpts, so the repair
queue sees them beside audit vetoes and refusals. It never changes an agent, a trial or a
promotion statistic, and it asks no model anything: every rule below is a regular expression or
an exact ledger lookup, chosen for precision over recall. A sentence that names no known topic is
dropped rather than given an invented key.

Three kinds of work, and what "never acted on" means for each:

- **a tool Merton requested** (`merton.pass` `tool`): acted on when a `tool.request` by that agent
  under the same normalized name was answered by a real `tool.fulfilled` (the toolsmith's legacy
  "cannot be a pure tool" answers are blocks, as `Commons._requests` reads them);
- **a code fix** (a defect named in the answer, or a replacement file Merton wrote): acted on when
  the agent adopted a strategy afterwards (`agent.strategy`), or replayed or submitted a candidate
  later in the same research session. Merton's file text is not on the ledger (`merton.pass`
  keeps only `wrote_code`), so a report says so: the fix must be re-asked or rebuilt from the
  answer;
- **a missing-data claim** (consult answers and research summaries): acted on when a tool on the
  same topic was fulfilled after the claim.

"Never" needs a later ledger to look at. A tool request or code fix is decided only once it is
`settle_hours` old (24 by default) on the ledger the scan covered, a missing-data claim once it is
`claim_settle_hours` old (1); until then it is pending, and the cursor stays before the oldest
pending row so the next run looks again. Every row has a stable ledger id
(`consult:<sha256(key)[:16]>:<source>`), so re-running the backfill, overlapping runs and a
restart all append nothing twice. Research summaries repeat themselves every pass, so they count
once per key, agent and UTC day.

    python -m league.consult_recovery --ledger /workspace/state/ledger.sqlite --dry-run

prints what a backfill would emit, as JSON lines, through a read-only connection.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

STATE_KEY = "consult_recovery"
SOURCE_KINDS = ("merton.pass", "agent.research")
CONTEXT_KINDS = ("agent.strategy", "agent.died")
TOOL_KINDS = ("tool.request", "tool.fulfilled", "tool.blocked")
#: Research-session tools that mean the agent tested a candidate after the consult.
TESTED_TOOLS = ("replay", "candidate", "candidate_admission")
#: How far behind the cursor each incremental run re-reads, so a consult's two rows (`merton.pass`
#: and the agent's `agent.research`, a few seqs apart) are never split across two runs.
OVERLAP_SEQ = 500
DEFAULTS = {"enabled": True, "every_seconds": 3600, "batch_rows": 20000, "settle_hours": 24.0, "claim_settle_hours": 1.0}

#: Topic -> what names it. A missing-data sentence must name one of these to count.
TOPICS: tuple[tuple[str, re.Pattern[str]], ...] = tuple((name, re.compile(pattern, re.I)) for name, pattern in (
    ("earnings", r"\bearnings\b|\bPEAD\b"),
    ("funding_rates", r"\bfunding(?:[ -]rates?|/open[- ]interest)\b|\bperp(?:etual)?s?\b(?:[ -]positioning)?|\bperp(?:etual)? positioning\b"),
    ("open_interest", r"\bopen[- ]interest\b"),
    ("order_book_depth", r"\border[- ]?books?\b|\bbook depth\b|\bmarket depth\b|\bqueue position\b|\blevel[- ]?2\b"),
    ("options_history", r"\boption[- ]chains?\b|\boptions?[- ](?:history|replay)\b|\bOPRA\b"),
    ("options_iv", r"\bimplied vol(?:atility)?\b|\bvolatility skew\b|\bgreeks\b"),
    ("settlement_source", r"\bsettlement[- ]source\b|\bunderlying[- ]values?\b|\bauthoritative (?:counts?|values?|published)\b"
                          r"|\bobserved (?:counts?|values?)\b|\bpublished values?\b|\bRT scores?\b"),
    ("underlying_price", r"\bunderlying[- ]price\b|\bspot(?:[- ]price)? feed\b"),
    ("sports_live_data", r"\blive[- ]scores?\b|\blineups?\b|\binjury (?:reports?|data)\b|\binactives?(?: lists?| feeds?| reports?)?\b(?=.*\b(?:lineup|score|sport))"),
    ("intrabar_ticks", r"\btick[- ](?:data|level|by[- ]tick)\b|\bintra[- ]?bar\b|\b\d+[- ]?(?:second|sec)\b|\bsub[- ]minute\b|\btrade prints\b"),
    ("news", r"\bnews (?:feeds?|data|history|archives?|sentiment)\b"),
    ("weather_forecasts", r"\bforecast (?:data|feeds?|models?)\b|\bNWS\b|\bensemble forecasts?\b|\bweather (?:models?|data|feeds?)\b"),
    ("replay_universe", r"\btape lacks\b|\bnot (?:in|on) the tape\b|\bno (?:bars|tape) for\b"),
))
#: A sentence that says an input is not there.
MISSING = re.compile(
    r"\b(?:un|not[ _])available\b|\bnot[ _]supplied\b|\bmissing\b|\babsent\b|\black(?:s|ing)?\b"
    r"|\bnot (?:yet )?(?:exposed|provided|recorded|supplied|in (?:the )?(?:ctx|view|runtime|inputs))\b"
    r"|\bcannot be (?:reconstructed|replayed|observed)\b|\b(?:input|data)[- ]blocked\b"
    r"|\bno (?:historical |point[- ]in[- ]time |live |authoritative )?(?:data|feed|panel|chains?|history|snapshots?)\b"
    r"|\bdoes(?:n't| not) (?:supply|provide|expose|include)\b|\bremains? (?:stale|unavailable|absent|missing)\b", re.I)
#: ...unless it says the opposite in the same breath.
NOW_THERE = re.compile(r"\b(?:is|are) now (?:available|supplied|exposed|live)\b|\bnow (?:supplies|provides|exposes)\b"
                       r"|\b(?:needs|requires|required) no\b|\bno longer\b|\bresolved\b", re.I)
#: A narrower topic named in the same sentence as a broader one is the same request: perpetual
#: funding and open interest are one feed in every claim on the ledger (Sept 22, 2026).
SUBSUMED = {"open_interest": "funding_rates"}
#: A defect named in the agent's CURRENT code.
DEFECT = re.compile(
    r"\bbugs?\b|\bdefects?\b|\boff[- ]by[- ]one\b|\blook[- ]?ahead\b|\bwrong sign\b|\bsign error\b|\binverted\b"
    r"|\b(?:code|file|strategy) rounds\b|\bcent rounding\b|\brounding (?:defeats|flips|turns|breaks|inverts)\b"
    r"|\bnever (?:fires|triggers|trades|enters|exits|cancels|fills)\b"
    r"|\byour (?:file|code|strategy|seed) (?:currently|only|never|rounds|cancels|ignores|treats|sells|buys)\b"
    r"|\b(?:does not|doesn't|never) (?:recheck|revalidate|re-validate|cancel)\b", re.I)
DATA_WORDS = re.compile(r"\b(?:data|feeds?|history|historical|panel|snapshots?|point[- ]in[- ]time|observations?|timestamps?"
                        r"|replay|coverage|quotes?|bars|values?|counts?|prices?|chains?)\b", re.I)
ERROR_ANSWER = re.compile(r"^\s*Merton (?:could not be reached|returned an unreadable answer)", re.I)
SENTENCE = re.compile(r"(?<=[.;!?])\s+|\n+")


# ---------------------------------------------------------------------------------- helpers
def _epoch(at: Any) -> float | None:
    if not isinstance(at, str) or len(at) < 19:
        return None
    raw = at.strip()
    if raw[-1] in "Zz":
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return (parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)).timestamp()


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(float(ts), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def tool_name(name: Any) -> str:
    """The name as `Commons.request_tool` stores it."""
    return re.sub(r"[^a-z0-9_]+", "_", str(name or "").lower()).strip("_")[:40]


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _clip(text: Any, limit: int = 400) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def sentences(text: Any) -> list[str]:
    return [s.strip() for s in SENTENCE.split(str(text or "")) if s.strip()]


def missing_topics(text: Any) -> dict[str, str]:
    """{topic: the first sentence that says that input is missing}."""
    found: dict[str, str] = {}
    for sentence in sentences(text):
        if not MISSING.search(sentence) or NOW_THERE.search(sentence):
            continue
        named = {topic for topic, pattern in TOPICS if pattern.search(sentence)}
        for topic, pattern in TOPICS:
            if topic in named and topic not in found and SUBSUMED.get(topic) not in named:
                found[topic] = sentence
    return found


def topics_of(text: Any) -> set[str]:
    return {topic for topic, pattern in TOPICS if pattern.search(str(text or ""))}


def defect_sentence(text: Any) -> str | None:
    for sentence in sentences(text):
        if DEFECT.search(sentence):
            return sentence
    return None


def _row(entry: Any) -> dict[str, Any]:
    """A ledger `Entry`, or a row already shaped like one."""
    if isinstance(entry, Mapping):
        return {"seq": int(entry["seq"]), "id": entry.get("id"), "at": entry.get("at"), "kind": entry.get("kind"),
                "agent": entry.get("agent") or "house", "payload": entry.get("payload") or {}}
    return {"seq": entry.seq, "id": entry.id, "at": entry.at, "kind": entry.kind, "agent": entry.agent, "payload": entry.payload}


# ---------------------------------------------------------------------------------- extraction
def _report(key: str, kind: str, summary: str, evidence: list[dict[str, Any]], agents: Iterable[str], severity: str,
            *, source_id: str, agent: str) -> dict[str, Any]:
    return {"key": key, "kind": kind, "summary": _clip(summary, 600), "evidence": evidence,
            "agents": sorted({a for a in agents if a and a != "house"}), "source": "consult", "severity": severity,
            "_id": f"consult:{_hash(key)}:{source_id}", "_agent": agent if agent and len(agent) <= 120 else "house"}


def scan(rows: Iterable[Mapping[str, Any]], *, now: float | None = None, settle_hours: float = DEFAULTS["settle_hours"],
         claim_settle_hours: float = DEFAULTS["claim_settle_hours"]) -> tuple[list[dict[str, Any]], int | None]:
    """(reports, the seq of the oldest source row still too young to decide, or None).

    `now` None decides everything (a backfill over a finished dump). Otherwise a tool request or a
    code fix younger than `settle_hours` at `now` is pending -- nothing later on the ledger has had
    time to act on it -- and so is a missing-data claim younger than `claim_settle_hours`. A claim
    says what the runtime lacks NOW, so it waits only long enough for a tool fulfilled in the same
    hour to count; a day's wait would only deliver it a day late."""
    rows = sorted((_row(r) for r in rows), key=lambda r: r["seq"])
    settle, claim_settle = float(settle_hours) * 3600, float(claim_settle_hours) * 3600

    strategies: dict[str, list[int]] = {}
    died: dict[str, int] = {}
    tested: dict[str, list[int]] = {}
    requests: dict[str, dict[str, Any]] = {}
    for row in rows:
        kind, p, agent = row["kind"], row["payload"], row["agent"]
        if kind == "agent.strategy":
            strategies.setdefault(agent, []).append(row["seq"])
        elif kind == "agent.died":
            died.setdefault(agent, row["seq"])
        elif kind == "agent.research" and p.get("tool") in TESTED_TOOLS and p.get("session"):
            tested.setdefault(str(p["session"]), []).append(row["seq"])
        elif kind == "tool.request":
            requests[str(row["id"] or f"seq:{row['seq']}")] = {"agent": agent, "name": tool_name(p.get("name")), "status": "open",
                                                               "text": f"{p.get('name')} {p.get('description')}", "fulfilled_seq": None}
        elif kind in ("tool.fulfilled", "tool.blocked"):
            request = requests.get(str(p.get("request")))
            if request is None:
                continue
            legacy = kind == "tool.fulfilled" and p.get("status") == "answered" and str(p.get("outcome") or "").lower().startswith("cannot be a pure tool")
            if kind == "tool.blocked" or legacy:
                request["status"] = "blocked"
            else:
                request["status"], request["fulfilled_seq"] = "fulfilled", row["seq"]
    fulfilled_topics = [(r["fulfilled_seq"], topics_of(r["text"])) for r in requests.values() if r["status"] == "fulfilled"]

    def data_arrived(topic: str, after: int) -> bool:
        return any(seq > after and topic in topics for seq, topics in fulfilled_topics)

    pending: list[int] = []

    def young(row: Mapping[str, Any], seconds: float) -> bool:
        """Too young to decide; the cursor must come back for it."""
        if now is None:
            return False
        at = _epoch(row["at"])
        if at is not None and now - at < seconds:
            pending.append(int(row["seq"]))
            return True
        return False

    # One consult is two rows: Merton's `merton.pass` (4,000 characters, the tool) and the agent's
    # `agent.research` (the first 2,000, the session). Group them; the earliest seq names it.
    consults: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        p = row["payload"]
        if row["kind"] == "merton.pass" and p.get("role") == "consultant":
            agent = str(p.get("agent") or "house")
        elif row["kind"] == "agent.research" and p.get("tool") == "merton":
            agent = row["agent"]
        else:
            continue
        answer = str(p.get("answer") or "")
        if p.get("error") or ERROR_ANSWER.match(answer) or not answer.strip():
            continue
        group = consults.setdefault((agent, answer[:2000].strip()), {"agent": agent, "rows": []})
        group["rows"].append(row)
    reports: list[dict[str, Any]] = []
    for group in consults.values():
        first = min(group["rows"], key=lambda r: r["seq"])
        agent, seq, at = group["agent"], first["seq"], first["at"]
        settled = not young(first, settle)
        if not settled and young(first, claim_settle):
            continue
        answer = max((str(r["payload"].get("answer") or "") for r in group["rows"]), key=len)
        tool = next((r["payload"]["tool"] for r in group["rows"] if isinstance(r["payload"].get("tool"), dict) and r["payload"]["tool"].get("name")), None)
        wrote = any(r["payload"].get("wrote_code") for r in group["rows"])
        session = next((str(r["payload"]["session"]) for r in group["rows"] if r["payload"].get("session")), None)
        dead = f" {agent} has since died, so the fix belongs to its line." if died.get(agent, 0) > seq else ""

        def evidence(excerpt: str) -> list[dict[str, Any]]:
            return [{"seq": seq, "at": at, "agent": agent, "excerpt": _clip(excerpt)}]

        if settled and tool is not None:
            name = tool_name(tool.get("name"))
            matching = [r for r in requests.values() if r["agent"] == agent and r["name"] == name]
            if name and not any(r["status"] == "fulfilled" for r in matching):
                description = str(tool.get("description") or "")
                kind = "missing_data" if DATA_WORDS.search(description) else "bug_report"
                state = "was never filed" if not matching else f"is still {matching[-1]['status']}"
                reports.append(_report(f"{kind}:tool:{name}", kind,
                                       f"Merton asked the House to build `{name}` for {agent} in a paid consult; the request {state}.{dead}",
                                       evidence(f"{name}: {description}"), [agent], "medium", source_id=str(seq), agent=agent))
        named = defect_sentence(answer)
        if settled and (named or wrote):
            later = [s for s in strategies.get(agent, []) if s > seq] + ([s for s in tested.get(session, []) if s > seq] if session else [])
            if not later:
                what = "named a defect in its code" if named else "wrote a replacement strategy file"
                file_note = (" He also wrote a whole file, which is not on the ledger (merton.pass keeps only wrote_code): "
                             "rebuild it from the answer or ask again.") if wrote else ""
                reports.append(_report(f"strategy_defect:{agent}:consult:{seq}", "strategy_defect",
                                       f"In a paid consult Merton {what} for {agent}; the agent never adopted a strategy or tested a candidate after it.{file_note}{dead}",
                                       evidence(named or answer), [agent], "low" if dead else ("high" if named else "medium"),
                                       source_id=str(seq), agent=agent))
        for topic, sentence in missing_topics(answer).items():
            if data_arrived(topic, seq):
                continue
            reports.append(_report(f"missing_data:{topic}", "missing_data",
                                   f"Merton told {agent} its work is blocked by missing {topic.replace('_', ' ')} data.",
                                   evidence(sentence), [agent], "medium", source_id=str(seq), agent=agent))

    # Research summaries: the agent's own account of why it did nothing. Once per key, agent and day.
    seen: set[tuple[str, str, str]] = set()
    for row in rows:
        p = row["payload"]
        if row["kind"] != "agent.research" or p.get("tool") != "summary":
            continue
        claims = missing_topics(p.get("summary"))
        if not claims or young(row, claim_settle):
            continue
        agent, day = row["agent"], str(row["at"] or "")[:10]
        for topic, sentence in claims.items():
            key = f"missing_data:{topic}"
            if (key, agent, day) in seen or data_arrived(topic, row["seq"]):
                continue
            seen.add((key, agent, day))
            reports.append(_report(key, "missing_data",
                                   f"{agent}'s research session reported its work blocked by missing {topic.replace('_', ' ')} data.",
                                   [{"seq": row["seq"], "at": row["at"], "agent": agent, "excerpt": _clip(sentence)}], [agent], "medium",
                                   source_id=f"{agent}:{day}", agent=agent))
    return reports, (min(pending) if pending else None)


def extract(rows: Iterable[Mapping[str, Any]], *, now: float | None = None, settle_hours: float = DEFAULTS["settle_hours"],
            claim_settle_hours: float = DEFAULTS["claim_settle_hours"]) -> list[dict[str, Any]]:
    """The `repair.reported` payloads these rows justify, each with its ledger `_id` and row `_agent`.
    Pure: rows are `{seq, at, kind, agent, payload}` (plus `id` for tool requests), from the ledger or a dump."""
    return scan(rows, now=now, settle_hours=settle_hours, claim_settle_hours=claim_settle_hours)[0]


# ---------------------------------------------------------------------------------- the House job
class ConsultRecovery:
    """The backfill and the incremental scan, run by the House beside its tick."""

    def __init__(self, ledger: Any, *, clock=time.time, settings: Mapping[str, Any] | None = None):
        self.ledger = ledger
        self.clock = clock
        self.settings = {**DEFAULTS, **dict(settings or {})}
        self._last = 0.0

    def due(self) -> bool:
        return bool(self.settings.get("enabled", True)) and self.clock() - self._last >= float(self.settings["every_seconds"])

    def run(self, state: dict[str, Any]) -> dict[str, Any]:
        """Scan from `state["seq"]` (0: the whole history), append what is new, move the cursor."""
        self._last = self.clock()
        cursor = int(state.get("seq") or 0)
        start = max(0, cursor - OVERLAP_SEQ) if cursor else 0
        limit = max(1, int(self.settings["batch_rows"]))
        sources, truncated = [], False
        for entry in self.ledger.iter(kinds=SOURCE_KINDS, after=start):
            if len(sources) >= limit:
                truncated = True
                break
            sources.append(_row(entry))
        # Small kinds, read whole from the window's start (tool requests from the beginning: a
        # consult can re-open a request filed long before it).
        context = [_row(e) for e in self.ledger.iter(kinds=CONTEXT_KINDS, after=start)]
        tools = [_row(e) for e in self.ledger.iter(kinds=TOOL_KINDS)]
        now = self.clock()
        if truncated and sources:
            # What lies beyond the batch has not been read, so nothing the batch ends on is settled.
            now = min(now, _epoch(sources[-1]["at"]) or now)
        rows = sources + context + tools
        reports, pending = scan(rows, now=now, settle_hours=float(self.settings["settle_hours"]),
                                claim_settle_hours=float(self.settings["claim_settle_hours"]))
        emitted = self._append(reports)
        last = sources[-1]["seq"] if sources else cursor
        seq = max(cursor, min(last, pending - 1) if pending is not None else last)
        stuck = 0
        if truncated and seq <= cursor:
            # More rows landed within a day of an undecided consult than one batch holds, so the
            # cursor did not move. Twice in a row means it never will (found in review, Sept 22,
            # 2026): decide what the batch holds by the real clock and move past it. The cost is
            # that a consult near the batch's end may be reported although a row beyond the batch
            # shows it acted on -- an extra report, never a lost one.
            stuck = int(state.get("stuck") or 0) + 1
            if stuck >= 2:
                decided, _ = scan(rows, now=self.clock(), settle_hours=float(self.settings["settle_hours"]),
                                  claim_settle_hours=float(self.settings["claim_settle_hours"]))
                emitted += self._append(decided)
                seq, stuck = last, 0
        state.update(seq=seq, at=_iso(self.clock()), emitted=int(state.get("emitted") or 0) + emitted, stuck=stuck)
        return {"scanned": len(sources), "emitted": emitted, "seq": seq}

    def _append(self, reports: list[dict[str, Any]]) -> int:
        from .ledger import LedgerConflict

        emitted = 0
        for report in reports:
            entry_id, agent = report["_id"], report["_agent"]
            if self.ledger.get(entry_id) is not None:
                continue
            payload = {k: v for k, v in report.items() if not k.startswith("_")}
            try:
                self.ledger.append("repair.reported", payload, agent=agent, id=entry_id)
            except LedgerConflict:
                continue
            emitted += 1
        return emitted


# ---------------------------------------------------------------------------------- dry run
def read_only_rows(path: str) -> list[dict[str, Any]]:
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        db.execute("PRAGMA query_only=ON")
        kinds = SOURCE_KINDS + CONTEXT_KINDS + TOOL_KINDS
        marks = ",".join("?" for _ in kinds)
        return [{"seq": s, "id": i, "at": a, "kind": k, "agent": g, "payload": json.loads(p)}
                for s, i, a, k, g, p in db.execute(f"SELECT seq, id, at, kind, agent, payload FROM ledger WHERE kind IN ({marks}) ORDER BY seq", kinds)]
    finally:
        db.close()


def existing_ids(path: str, ids: Iterable[str]) -> set[str]:
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        wanted = list(ids)
        found: set[str] = set()
        for i in range(0, len(wanted), 500):
            chunk = wanted[i:i + 500]
            found |= {row[0] for row in db.execute(f"SELECT id FROM ledger WHERE id IN ({','.join('?' for _ in chunk)})", chunk)}
        return found
    finally:
        db.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="league.consult_recovery", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ledger", required=True, help="the ledger's sqlite file, opened read-only")
    parser.add_argument("--dry-run", action="store_true", help="print what a backfill would emit (the only mode: this command never writes)")
    parser.add_argument("--settle-hours", type=float, default=DEFAULTS["settle_hours"])
    parser.add_argument("--claim-settle-hours", type=float, default=DEFAULTS["claim_settle_hours"])
    parser.add_argument("--all", action="store_true", help="decide every row, however young (a finished dump)")
    args = parser.parse_args(argv)
    rows = read_only_rows(args.ledger)
    reports = extract(rows, now=None if args.all else time.time(), settle_hours=args.settle_hours, claim_settle_hours=args.claim_settle_hours)
    have = existing_ids(args.ledger, [r["_id"] for r in reports])
    for report in reports:
        print(json.dumps({"id": report["_id"], "agent": report["_agent"], "exists": report["_id"] in have,
                          **{k: v for k, v in report.items() if not k.startswith("_")}}, sort_keys=True))
    print(json.dumps({"reports": len(reports), "new": sum(r["_id"] not in have for r in reports)}), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
