"""Hypothesis memory: a new name must not erase a mechanism's failure history.

The swarm re-proposes the same ideas in new words. On Sept 22 huang-26's journal told its
descendants "do not re-run close favorite/maker/taker/spot-reversal/alt variants", and 94% of
births were parameter mutations of existing mechanisms. Nothing linked a reworded mechanism to the
trials its earlier wording had already failed, so each rewording started with a clean slate in
every reader's eyes (the evaluator's own lineage counts were always right; the READERS lacked it).

This module reads the stated mechanisms the floor already writes -- `hypothesis.card` rows, the
`purpose` of every retained research candidate, and strategy docstrings from `agent.born` and
`agent.strategy` -- and writes `hypothesis.link {a, b, relation, confidence, method}`:

- **exact**: the same words with only numbers changed, in the same niche, is a `rewording` (a
  parameter variant of one mechanism); identical words in another niche are `related`, never a
  rewording: the same idea on other markets has other evidence.
- **jev**: pairs in the same venue with word overlap are asked "same mechanism, reworded?" At or
  above `rewording_threshold` the link is `rewording`; in the uncertain band it is `related`;
  below `distinct_threshold` it is `distinct`. An uncertain label is never a rewording.

A link is a READING AID. It never alters genealogy, lineage trial counts, deflated-Sharpe
denominators or any evaluator input; `failure_history` reports a mechanism's own failures and its
linked mechanisms' failures separately, and never sums them.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Any, Callable, Mapping

from .jev import jaccard, sha
from .ledger import LedgerConflict

SAME = ("Do the item and the reference mechanism in state describe the same trading mechanism -- the same signal, "
        "the same kind of market and the same claimed source of edge -- differing only in wording or parameter values?")
DEFAULTS: dict[str, Any] = {
    "enabled": True,
    "interval_seconds": 3600,
    "rewording_threshold": 0.9,
    "distinct_threshold": 0.3,
    "pair_overlap": 0.3,
    "candidates_per_mechanism": 3,
    "max_questions_per_run": 48,
    "min_chars": 40,
}


def normalize(text: str) -> str:
    """Case, spacing and punctuation removed: the text a `hypothesis.card` id is computed from."""
    return re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).strip()


def wording(text: str) -> str:
    """The words alone, numbers removed: equal wordings differ only in parameter values."""
    return re.sub(r"\s+", " ", re.sub(r"[0-9]+", " ", normalize(text))).strip()


def mechanism_id(text: str, niche: str | None) -> str:
    """The `hypothesis.card` id rule (league/hypotheses.py `card_id`): a sha256 prefix of the
    normalized mechanism plus the niche, so a docstring and a card stating the same mechanism
    on the same desk are one mechanism here."""
    return hashlib.sha256((normalize(text) + "\n" + str(niche or "")).encode("utf-8")).hexdigest()[:16]


def docstring(code: str) -> str:
    try:
        return ast.get_docstring(ast.parse(code)) or ""
    except (SyntaxError, ValueError):
        return ""


class HypothesisMemory:
    def __init__(self, ledger: Any, sensor: Any = None, *, path: str | Path, clock: Callable[[], float] = time.time,
                 settings: Mapping[str, Any] | None = None, niche_of: Callable[[str], str | None] | None = None):
        self.ledger, self.sensor, self.clock = ledger, sensor, clock
        self.path = Path(path)
        self.settings = {**DEFAULTS, **dict(settings or {})}
        self.niche_of = niche_of or (lambda agent: None)
        self.lock = threading.Lock()
        try:
            self.state = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.state = {}
        self.state.setdefault("seq", 0)
        self.state.setdefault("last_run", 0.0)
        self.state.setdefault("mechanisms", {})  # id -> {text, niche, sources: [{agent, code, seq, kind}]}

    def due(self) -> bool:
        return bool(self.settings.get("enabled", True)) and self.clock() - float(self.state["last_run"]) >= float(self.settings["interval_seconds"])

    def _save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.state, sort_keys=True), encoding="utf-8")
        os.replace(tmp, self.path)

    # --------------------------------------------------------------- collection
    def _mechanisms_in(self, entry: Any) -> list[tuple[str, str | None, str | None, str | None]]:
        """(id, text, niche, code sha) stated by one ledger row."""
        p = entry.payload
        if entry.kind == "hypothesis.card":
            text = str(p.get("mechanism") or "")
            return [(str(p.get("id") or mechanism_id(text, p.get("niche"))), text, p.get("niche"), p.get("code_sha256"))] if text else []
        if entry.kind in ("agent.born", "agent.strategy"):
            text = docstring(str(p.get("_code") or ""))
            niche = p.get("specialty") or self.niche_of(entry.agent)
            return [(mechanism_id(text, niche), text, niche, p.get("code_sha256"))] if len(text) >= int(self.settings["min_chars"]) else []
        if entry.kind == "agent.research" and p.get("tool") == "candidate" and isinstance(p.get("_candidate"), dict):
            candidate = p["_candidate"]
            text = str(candidate.get("purpose") or "")
            niche = self.niche_of(entry.agent)
            code = (candidate.get("numbers") or {}).get("code_sha256")
            return [(mechanism_id(text, niche), text, niche, code)] if len(text) >= int(self.settings["min_chars"]) else []
        return []

    def collect(self) -> list[str]:
        """Fold new stated mechanisms into the index. Returns the ids seen for the first time."""
        new: list[str] = []
        after = int(self.state["seq"])
        while True:
            rows = self.ledger.read(kinds=("hypothesis.card", "agent.born", "agent.strategy", "agent.research"), after=after, limit=5000)
            if not rows:
                break
            for entry in rows:
                for ident, text, niche, code in self._mechanisms_in(entry):
                    row = self.state["mechanisms"].get(ident)
                    if row is None:
                        row = self.state["mechanisms"][ident] = {"text": text[:1200], "niche": niche, "sources": []}
                        new.append(ident)
                    if len(row["sources"]) < 200:
                        # A card is written by the House for the line it founds (`line_id`).
                        agent = str(entry.payload.get("line_id") or entry.agent) if entry.kind == "hypothesis.card" else entry.agent
                        row["sources"].append({"agent": agent, "code": code, "seq": entry.seq, "kind": entry.kind})
            after = rows[-1].seq
        self.state["seq"] = after
        return new

    # ------------------------------------------------------------------- links
    def _link(self, a: str, b: str, relation: str, confidence: float, method: str) -> bool:
        a, b = sorted((a, b))
        try:
            self.ledger.append("hypothesis.link", {"a": a, "b": b, "relation": relation, "confidence": round(float(confidence), 4),
                                                   "method": method}, id=f"hypothesis-link:{a}:{b}:{method}")
            return True
        except LedgerConflict:
            return False  # the first reading of a pair stands; a re-ask with a changed model is a new method

    def run(self) -> dict[str, Any]:
        with self.lock:
            self.state["last_run"] = self.clock()
            new = self.collect()
            links = self._exact(new)
            # Jev reads a bounded number of pairs a run; the rest wait their turn instead of being
            # forgotten once they are no longer new (the first run on production indexes ~800).
            pending = list(dict.fromkeys([*self.state.get("pending", []), *new]))
            done, written = self._semantic(pending)
            self.state["pending"] = [ident for ident in pending if ident not in done]
            self._save()
            return {"new_mechanisms": len(new), "links": links + written, "pending": len(self.state["pending"]),
                    "mechanisms": len(self.state["mechanisms"])}

    def _exact(self, new: list[str]) -> int:
        """Equal wordings: a rewording in the same niche (only numbers differ), related across niches."""
        mechanisms = self.state["mechanisms"]
        by_text: dict[str, list[str]] = {}
        for ident, row in mechanisms.items():
            by_text.setdefault(wording(row["text"]), []).append(ident)
        written = 0
        fresh = set(new)
        for idents in by_text.values():
            if len(idents) < 2:
                continue
            for ident in idents:
                if ident not in fresh:
                    continue
                for other in idents:
                    if other != ident and (other not in fresh or other < ident):
                        same_niche = mechanisms[ident].get("niche") == mechanisms[other].get("niche")
                        written += self._link(ident, other, "rewording" if same_niche else "related", 1.0, "exact")
        return written

    def _semantic(self, pending: list[str]) -> tuple[set[str], int]:
        """(ids fully answered or with nothing to ask, links written)."""
        if self.sensor is None or not pending:
            return set(), 0
        mechanisms = self.state["mechanisms"]
        asked, written, done = 0, 0, set()
        cap = int(self.settings["max_questions_per_run"])
        for ident in pending:
            if ident not in mechanisms:
                done.add(ident)
                continue
            row = mechanisms[ident]
            venue = str(row.get("niche") or "").split("-")[0]
            scored = []
            for other, orow in mechanisms.items():
                if other == ident or wording(orow["text"]) == wording(row["text"]):
                    continue  # already linked exactly
                if venue and str(orow.get("niche") or "").split("-")[0] != venue:
                    continue
                score = jaccard(row["text"], orow["text"])
                if score >= float(self.settings["pair_overlap"]):
                    scored.append((score, other))
            scored.sort(reverse=True)
            pairs = [other for _, other in scored[:int(self.settings["candidates_per_mechanism"])]]
            if not pairs:
                done.add(ident)
                continue
            if asked + len(pairs) > cap:
                if asked or cap <= 0:
                    break
                pairs = pairs[:cap]  # a cap below one mechanism's candidates still makes progress
            asked += len(pairs)
            items = {"hyplink:" + sha(sorted((ident, other))): (mechanisms[other]["text"][:900], SAME) for other in pairs}
            answers = self.sensor.ask("links", {"reference_mechanism": row["text"][:900], "reference_niche": row.get("niche")}, items)
            if all(answers.get(key) is not None for key in items):
                done.add(ident)
            for other, key in zip(pairs, items):
                p = answers.get(key)
                if p is None:
                    continue  # no answer is no link: silence never becomes a rewording
                if p >= float(self.settings["rewording_threshold"]):
                    relation = "rewording"
                elif p < float(self.settings["distinct_threshold"]):
                    relation = "distinct"
                else:
                    relation = "related"
                written += self._link(ident, other, relation, p, "jev")
        return done, written

    # ---------------------------------------------------------------- readers
    def resolve(self, ref: str, niche: str | None = None) -> str | None:
        if ref in self.state["mechanisms"]:
            return ref
        ident = mechanism_id(ref, niche)
        return ident if ident in self.state["mechanisms"] else None

    def links_of(self, ident: str) -> list[dict[str, Any]]:
        out = []
        for entry in self.ledger.iter(kinds="hypothesis.link"):
            p = entry.payload
            if ident in (p.get("a"), p.get("b")):
                out.append({"other": p["b"] if p["a"] == ident else p["a"], "relation": p.get("relation"),
                            "confidence": p.get("confidence"), "method": p.get("method"), "seq": entry.seq})
        return out

    def _failures(self, ident: str) -> dict[str, Any]:
        row = self.state["mechanisms"].get(ident) or {}
        codes = {s["code"] for s in row.get("sources") or [] if s.get("code")}
        agents = {s["agent"] for s in row.get("sources") or []}
        trials = [e for agent in sorted(agents) for e in self.ledger.iter(kinds="eval.trial", agent=agent)
                  if not codes or e.payload.get("code_sha256") in codes]
        failed = [e for e in trials if not e.payload.get("passed")]
        retired = [e.payload for e in self.ledger.iter(kinds="hypothesis.retired") if e.payload.get("id") == ident]
        return {"id": ident, "text": row.get("text"), "niche": row.get("niche"), "agents": sorted(agents),
                "trials": len(trials), "failed_trials": len(failed),
                "recent_failures": [{"seq": e.seq, "agent": e.agent, "reasons": (e.payload.get("reasons") or [])[:3]} for e in failed[-5:]],
                "retired": retired}

    def failure_history(self, ref: str, niche: str | None = None) -> dict[str, Any]:
        """A mechanism's own failure record, and its linked mechanisms' records beside it.

        `ref` is a mechanism id or its text. The linked records are labelled with the link's
        relation, confidence and method and are never added to the mechanism's own counts:
        semantic similarity is not genealogy."""
        ident = self.resolve(ref, niche)
        if ident is None:
            return {"id": mechanism_id(ref, niche), "known": False, "own": None, "linked": []}
        linked = []
        for link in self.links_of(ident):
            if link["relation"] == "distinct":
                continue
            linked.append({**link, "record": self._failures(link["other"])})
        return {"id": ident, "known": True, "own": self._failures(ident), "linked": linked,
                "note": "Linked records are similar mechanisms, not ancestors: they never change this mechanism's trial count."}

    def stats(self) -> dict[str, Any]:
        return {"mechanisms": len(self.state["mechanisms"]), "cursor": self.state["seq"]}
