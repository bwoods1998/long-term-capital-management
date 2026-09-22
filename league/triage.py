"""Shared triage: turn the swarm's writing into deduplicated, evidence-backed repair reports.

The floor writes a great deal that is really a work order: 130 tool requests in three days
(leahy-27 and leahy-30 asked for the same point-in-time underlying-value feed in separate
requests, 33 seconds apart on Sept 22), 2,902 journal notes, research abstentions naming the missing
input ("the perpetual funding/OI feed remains not_supplied", session after session), post-mortems. Until now a human
or Merton had to notice. Triage reads them on a cadence and writes `repair.reported` rows
(`source: triage`) that the repair queue folds by `key`:

1. **Deterministic first.** A tool request is keyed by its exact normalized name, as the repair
   worklist keys it (both reporters fold into one job, and identical evidence counts once); a post-mortem
   by family and defect cause; an abstention by the unresolved requests of the agent's line. The
   original evidence (`seq`, `at`, `agent`, excerpt) and every affected agent are kept.
2. **Jev only for meaning.** "Do these two requests describe the same missing feed?" merges an
   alias into the older key only at high confidence (a duplicate is cheaper than losing a distinct
   request); "does this text report a bug?" turns a journal note or thought into a `bug_report`.
   Pairs are pre-filtered by word overlap, answers cached, batched 16 to a request, and capped
   (`max_questions_per_run`, the Sensor's daily dollars and calls).

Repair reports are evidence, not authority: triage never closes, merges code or spends.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Mapping

from .jev import jaccard, sha, words
from .ledger import LedgerConflict, now_iso
from .research_gate import MISSING, session_outcome

SOURCES = ("tool.request", "agent.postmortem", "agent.research", "agent.thought")
#: Post-mortem causes that point at code rather than the game: `displaced` (251 of 260 deaths on
#: Sept 22) and `evidence` are the league working as designed.
DEFECT_CAUSES = frozenset(("stuck", "crashed", "crash", "error", "invalid", "timeout", "broken"))
BUG_HINT = re.compile(r"\bbug\b|error|exception|traceback|crash|incorrect|wrong|broken|mismatch|stale|not (?:reflect|update|record)|"
                      r"never (?:fill|fire|arrive|record)|double|duplicate|phantom|miscount|inconsistent|reconcil", re.I)
BUG = ("Does this text report a defect in the trading House's own software, data, replay, accounting or order handling "
       "(something engineering should fix), rather than a trading loss, a market condition, a strategy idea or a missing feature?")
SAME_DEFECT = ("Does this item describe the same defect (the same broken behaviour in the same component or file) as the "
               "new report in state, so that one fix would resolve both?")
SAME_FEED = ("Does this item describe the same missing data feed or input (same data, same markets) as the reference request "
             "in state, so that building one would satisfy both?")
DEFAULTS: dict[str, Any] = {
    "enabled": True,
    "interval_seconds": 1800,
    "batch_rows": 10000,
    "max_questions_per_run": 64,
    "max_merge_questions_per_run": 32,
    "bug_threshold": 0.7,
    "same_feed_threshold": 0.8,
    "same_defect_threshold": 0.75,
    "pair_overlap": 0.15,
    "evidence_per_row": 50,
    "pending_limit": 400,
}


def _severity(agents: int) -> str:
    return "high" if agents >= 4 else "medium" if agents >= 2 else "low"


def _normal(text: str) -> str:
    """Wording with numbers and identifiers of the moment removed, for exact grouping."""
    text = re.sub(r"\d+(?:\.\d+)?", "#", str(text).lower())
    return re.sub(r"\s+", " ", re.sub(r"[^a-z# ]+", " ", text)).strip()


def _name(value: Any) -> str:
    """A tool name as the repair worklist keys it (league/worklist.py `_name`)."""
    return re.sub(r"[^a-z0-9_]+", "_", str(value or "").lower()).strip("_")[:60]


def _excerpt(entry: Any, text: str) -> dict[str, Any]:
    """Evidence exactly as the worklist's deterministic reporters quote the same row (the text,
    unstripped), so the fold's (seq, agent, excerpt) mark counts a row once whoever reports it."""
    return {"seq": entry.seq, "at": entry.at, "agent": entry.agent, "excerpt": str(text)[:300]}


class Triage:
    def __init__(self, ledger: Any, sensor: Any = None, *, clock: Callable[[], float] = time.time, path: str | Path,
                 settings: Mapping[str, Any] | None = None, lineage: Callable[[str], list[str]] | None = None,
                 requests: Callable[[], list[dict[str, Any]]] | None = None, niche_of: Callable[[str], str | None] | None = None,
                 family_of: Callable[[str], str | None] | None = None):
        self.ledger, self.sensor, self.clock = ledger, sensor, clock
        self.path = Path(path)
        self.settings = {**DEFAULTS, **dict(settings or {})}
        self.lineage = lineage or (lambda agent: [agent])
        self.requests = requests or (lambda: [])
        self.niche_of = niche_of or (lambda agent: None)
        self.family_of = family_of or (lambda agent: None)
        self.lock = threading.Lock()
        try:
            self.state = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.state = {}
        self.state.setdefault("seq", 0)
        self.state.setdefault("last_run", 0.0)
        self.state.setdefault("groups", {})
        self.state.setdefault("aliases", {})
        self.state.setdefault("names", {})  # request name -> its group key, so one name has one kind

    def due(self) -> bool:
        return bool(self.settings.get("enabled", True)) and self.clock() - float(self.state["last_run"]) >= float(self.settings["interval_seconds"])

    def _save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.state, sort_keys=True), encoding="utf-8")
        os.replace(tmp, self.path)

    # ---------------------------------------------------------------- grouping
    def _canonical(self, key: str) -> str:
        seen = set()
        while key in self.state["aliases"] and key not in seen:
            seen.add(key)
            key = self.state["aliases"][key]
        return key

    def _add(self, found: dict[str, dict[str, Any]], key: str, kind: str, summary: str, evidence: dict[str, Any],
             text: str = "") -> None:
        key = self._canonical(key)
        group = found.setdefault(key, {"kind": kind, "summary": summary[:300], "evidence": [], "agents": set()})
        group["evidence"].append(evidence)
        group["agents"].add(evidence["agent"])
        known = self.state["groups"].setdefault(key, {"kind": kind, "summary": summary[:300], "text": text[:600] or summary[:600],
                                                       "agents": [], "last_seq": 0})
        known["agents"] = sorted(set(known["agents"]) | {evidence["agent"]})

    def run(self) -> dict[str, Any]:
        with self.lock:
            return self._run()

    def _run(self) -> dict[str, Any]:
        self.state["last_run"] = self.clock()
        rows = self.ledger.read(kinds=SOURCES, after=int(self.state["seq"]), limit=int(self.settings["batch_rows"]))
        if not rows and not self.state.get("pending_bugs"):
            self._save()
            return {"rows": 0, "reported": 0}
        unresolved: dict[str, list[str]] = {}
        try:
            for row in self.requests():
                if row.get("status") in ("open", "blocked"):
                    unresolved.setdefault(row["by"], []).append(str(row.get("name") or ""))
        except Exception:  # noqa: BLE001
            unresolved = {}
        found: dict[str, dict[str, Any]] = {}
        new_requests: list[tuple[str, str]] = []  # (key, text) of request groups first seen in this run
        loose_missing: list[tuple[Any, str]] = []  # abstentions naming missing data with no request behind them
        bug_candidates: list[tuple[Any, str]] = []
        questions = {"asked": 0}
        for entry in rows:
            p = entry.payload
            if entry.kind == "tool.request":
                name = str(p.get("name") or "").strip()
                if not name:
                    continue
                text = f"{name}: {p.get('description') or ''}"
                # The worklist's key for the same request (league/worklist.py Sources), so both
                # reporters fold into one job; Jev's contribution is merging differently named ones.
                key = self.state["names"].setdefault(name, f"missing_data:{_name(name)}")
                if self._canonical(key) not in self.state["groups"] and key not in found:
                    new_requests.append((key, text))
                self._add(found, key, "missing_data", f"requested: {text}", _excerpt(entry, p.get("description") or ""), text)
            elif entry.kind == "agent.postmortem":
                cause = str(p.get("cause") or "")
                if cause in DEFECT_CAUSES:
                    family = self.family_of(entry.agent) or entry.agent.rsplit("-", 1)[0]
                    self._add(found, f"strategy_defect:{family}:{cause}", "strategy_defect",
                              f"agents of {family} died of {cause}", _excerpt(entry, p.get("text") or cause))
            elif entry.kind == "agent.research" and p.get("tool") == "summary":
                text = str(p.get("summary") or "")
                if session_outcome(p) != "abstained" or not text:
                    continue
                line = self.lineage(entry.agent) or [entry.agent]
                names = sorted({n for member in line for n in unresolved.get(member, []) if n})
                if names:
                    # The abstention is evidence for the requests the line is still waiting on: how
                    # many paid sessions each missing input has cost.
                    for name in names:
                        key = self.state["names"].get(name) or f"missing_data:{_name(name)}"
                        self._add(found, key, "missing_data", f"requested: {name}", _excerpt(entry, text))
                elif MISSING.search(text):
                    loose_missing.append((entry, text))
            elif (entry.kind == "agent.research" and p.get("tool") == "journal") or entry.kind == "agent.thought":
                text = str(p.get("text") or "")
                if len(text) >= 40 and BUG_HINT.search(text):
                    bug_candidates.append((entry, text))
        self._merge_requests(found, new_requests, questions)
        self._place_missing(found, loose_missing, questions)
        self._bugs(found, bug_candidates, questions)
        reported = self._report(found)
        if rows:
            self.state["seq"] = rows[-1].seq
        self._save()
        return {"rows": len(rows), "reported": reported, "questions": questions["asked"], "merge_questions": questions.get("merge", 0),
                "groups": len(self.state["groups"])}

    # --------------------------------------------------------------------- Jev
    def _budget(self, questions: dict[str, int], n: int, pool: str = "asked") -> bool:
        """Per-run question caps. Deduplication ("same defect?") has its own pool, so a backfill
        full of new texts to classify cannot starve the merging of what was already found."""
        cap = int(self.settings["max_questions_per_run" if pool == "asked" else "max_merge_questions_per_run"])
        if self.sensor is None or questions.get(pool, 0) + n > cap:
            return False
        questions[pool] = questions.get(pool, 0) + n
        return True

    def _same_feed(self, pairs: list[tuple[str, str, str, str]], questions: dict[str, int]) -> dict[tuple[str, str], float | None]:
        """pairs: (candidate key, candidate text, reference key, reference text). One shared
        reference per request, so a batch is one reference against up to 16 candidates."""
        out: dict[tuple[str, str], float | None] = {}
        by_ref: dict[str, list[tuple[str, str, str, str]]] = {}
        for pair in pairs:
            by_ref.setdefault(pair[2], []).append(pair)
        for ref, group in by_ref.items():
            if not self._budget(questions, len(group)):
                break
            items = {"samefeed:" + sha(sorted((c, ref)), _normal(ct)[:400]): (ct[:800], SAME_FEED) for c, ct, _, _ in group}
            answers = self.sensor.ask("triage", {"reference_request": group[0][3][:800]}, items)
            for (c, ct, r, _), key in zip(group, items):
                out[(c, r)] = answers.get(key)
                self._item("same_feed", c, r, answers.get(key))
        return out

    def _item(self, question: str, subject: str, reference: str | None, p: float | None) -> None:
        if p is None:
            return
        try:
            self.ledger.append("triage.item", {"question": question, "subject": subject, "reference": reference,
                                               "p": round(p, 4), "method": "jev"},
                               id=f"triage-item:{question}:{sha(subject, reference)[:24]}")
        except LedgerConflict:
            pass  # the same pair classified before: the cached answer is the first one

    def _candidates(self, text: str, exclude: str) -> list[tuple[str, str]]:
        """Existing missing-data groups this text plausibly overlaps, best three."""
        scored = []
        for key, group in self.state["groups"].items():
            if key == exclude or group.get("kind") != "missing_data" or key in self.state["aliases"]:
                continue
            score = jaccard(text, group.get("text") or group.get("summary") or "")
            if score >= float(self.settings["pair_overlap"]):
                scored.append((score, key, group.get("text") or ""))
        scored.sort(reverse=True)
        return [(key, ref) for _, key, ref in scored[:3]]

    def _merge_requests(self, found, new_requests, questions) -> None:
        threshold = float(self.settings["same_feed_threshold"])
        pairs = []
        for key, text in new_requests:
            if not key.startswith("missing_data:"):
                continue
            pairs += [(key, text, ref, rtext) for ref, rtext in self._candidates(text, key)]
        if not pairs:
            return
        answers = self._same_feed(pairs, questions)
        for (key, ref), p in answers.items():
            if p is None or p < threshold or key in self.state["aliases"] or self._canonical(ref) == key:
                continue
            # Merge the newer name into the older key; the evidence and agents move with it.
            self.state["aliases"][key] = self._canonical(ref)
            moved = found.pop(key, None)
            old = self.state["groups"].pop(key, None) or {}
            target = self._canonical(ref)
            group = self.state["groups"].setdefault(target, {"kind": "missing_data", "summary": old.get("summary", ""), "text": "", "agents": [], "last_seq": 0})
            group.setdefault("aliases", []).append(key.split(":", 1)[1])
            group["agents"] = sorted(set(group["agents"]) | set(old.get("agents") or []))
            if moved:
                merged = found.setdefault(target, {"kind": "missing_data", "summary": group.get("summary", ""), "evidence": [], "agents": set()})
                merged["evidence"] += moved["evidence"]
                merged["agents"] |= moved["agents"]
                merged.setdefault("aliases", set()).add(key.split(":", 1)[1])

    def _place_missing(self, found, loose, questions) -> None:
        """Abstentions that name missing data without a request behind them. Jev may attach one
        to the closest request group; otherwise it joins its niche's single group, keyed as the
        worklist keys research that stops at a missing input (`missing_data:research:<niche>`).
        A key per sentence made 897 groups from one production backfill: every abstention is
        worded differently, so exact sentence grouping only multiplied the queue."""
        threshold = float(self.settings["same_feed_threshold"])
        pending = []
        for entry, text in loose:
            sentence = next((s for s in re.split(r"(?<=[.;])\s+", text) if MISSING.search(s)), text)
            niche = self.niche_of(entry.agent) or "floor"
            pending.append((entry, text, sentence, f"missing_data:research:{niche}"))
        subjects = {id(item): "abstain:" + sha(_normal(item[2]))[:16] for item in pending}
        pairs = [(subjects[id(item)], item[2], ref, rtext) for item in pending
                 for ref, rtext in self._candidates(item[2], item[3])[:1]]
        answers = self._same_feed(pairs, questions) if pairs else {}
        for item in pending:
            entry, text, sentence, fallback = item
            best = max(((p, ref) for (c, ref), p in answers.items() if c == subjects[id(item)] and p is not None and p >= threshold), default=None)
            key = best[1] if best else fallback
            summary = f"abstained on missing data: {sentence}" if best else "abstained on missing data without filing a request"
            self._add(found, key, "missing_data", summary, _excerpt(entry, text), sentence)

    def _bugs(self, found, candidates, questions) -> None:
        """Texts that may report a defect: exact duplicates (numbers normalized) are one question.
        What the per-run cap or an outage leaves unasked waits in `pending_bugs` for the next run,
        oldest first, rather than being passed by the cursor unread."""
        threshold = float(self.settings["bug_threshold"])
        waiting = [(SimpleNamespace(seq=r["seq"], at=r["at"], agent=r["agent"]), r["text"]) for r in self.state.get("pending_bugs") or []]
        unique: dict[str, list[tuple[Any, str]]] = {}
        for entry, text in waiting + list(candidates):
            unique.setdefault("bug:" + sha(_normal(text)[:600]), []).append((entry, text))
        keys = list(unique)
        answers: dict[str, float | None] = {}
        for start in range(0, len(keys), 16):
            chunk = keys[start:start + 16]
            if not self._budget(questions, len(chunk)):
                break
            answers.update(self.sensor.ask("triage", {}, {k: (unique[k][0][1][:900], BUG) for k in chunk}))
        left = [key for key in keys if answers.get(key) is None]
        self.state["pending_bugs"] = [{"seq": e.seq, "at": e.at, "agent": e.agent, "text": t[:900]}
                                      for key in left for e, t in unique[key]][-int(self.settings["pending_limit"]):]
        for key, p in answers.items():
            self._item("bug_report", key, None, p)
            if p is None or p < threshold:
                continue
            entry, text = unique[key][0]
            niche = self.niche_of(entry.agent) or "floor"
            group = self._same_defect(f"bug_report:{niche}:{key[4:14]}", niche, text, questions)
            for entry, text in unique[key]:
                self._add(found, group, "bug_report", f"reported: {text[:240]}", _excerpt(entry, text), text)

    def _same_defect(self, key: str, niche: str, text: str, questions: dict[str, int]) -> str:
        """An agent restates a defect pass after pass in new words (the options desk described one
        OCC exit-routing bug in seven journal notes on Sept 21). Jev compares a new report with
        the two most similar reports already grouped on its desk; only a confident match joins."""
        if key in self.state["groups"]:
            return key
        prefix = f"bug_report:{niche}:"
        scored = sorted(((jaccard(text, g.get("text") or ""), k) for k, g in self.state["groups"].items()
                         if k.startswith(prefix) and k not in self.state["aliases"]), reverse=True)
        candidates = [k for score, k in scored[:2] if score >= float(self.settings["pair_overlap"])]
        if not candidates or not self._budget(questions, len(candidates), "merge"):
            return key
        items = {"samedefect:" + sha(sorted((key, k))): (str(self.state["groups"][k].get("text") or "")[:900], SAME_DEFECT)
                 for k in candidates}
        answers = self.sensor.ask("triage", {"new_report": text[:900]}, items)
        best = max(((p, k) for k, (ck, p) in zip(candidates, answers.items()) if p is not None), default=None)
        for k, ck in zip(candidates, items):
            self._item("same_defect", key, k, answers.get(ck))
        threshold = float(self.settings["same_defect_threshold"])
        return best[1] if best and best[0] >= threshold else key

    # ------------------------------------------------------------------ output
    def _report(self, found: dict[str, dict[str, Any]]) -> int:
        written = 0
        limit = int(self.settings["evidence_per_row"])
        for key, group in found.items():
            known = self.state["groups"].get(key) or {}
            evidence = sorted((e for e in group["evidence"] if e["seq"] > int(known.get("last_seq") or 0)), key=lambda e: e["seq"])
            for start in range(0, len(evidence), limit):
                part = evidence[start:start + limit]
                agents = sorted({e["agent"] for e in part})
                payload = {"key": key, "kind": group["kind"], "summary": group["summary"], "evidence": part,
                           "agents": agents, "source": "triage",
                           "severity": _severity(len(set(known.get("agents") or []) | set(agents))),
                           "all_agents": len(set(known.get("agents") or []) | set(agents))}
                if group.get("aliases") or known.get("aliases"):
                    payload["aliases"] = sorted(set(group.get("aliases") or ()) | set(known.get("aliases") or ()))
                try:
                    self.ledger.append("repair.reported", payload, id=f"repair-triage:{sha(key)[:24]}:{part[-1]['seq']}")
                except LedgerConflict:
                    continue  # reported before a restart with other context: the first report stands
                written += 1
            if evidence and key in self.state["groups"]:
                self.state["groups"][key]["last_seq"] = evidence[-1]["seq"]
        return written

    def stats(self) -> dict[str, Any]:
        groups = self.state["groups"]
        kinds: dict[str, int] = {}
        for group in groups.values():
            kinds[group.get("kind", "?")] = kinds.get(group.get("kind", "?"), 0) + 1
        top = sorted(groups.items(), key=lambda kv: -len(kv[1].get("agents") or []))[:8]
        return {"cursor": self.state["seq"], "groups": len(groups), "by_kind": kinds, "aliases": len(self.state["aliases"]),
                "last_run": now_iso(lambda: float(self.state["last_run"])) if self.state["last_run"] else None,
                "most_shared": [{"key": k, "agents": len(g.get("agents") or [])} for k, g in top]}


__all__ = ["Triage", "words"]
