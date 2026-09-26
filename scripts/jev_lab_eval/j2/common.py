"""Shared loaders for the J2 offline analysis (read-only extracts in data/)."""
import glob, json, os, re, hashlib
from collections import defaultdict
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
WINDOW_START = "2026-09-22T00:00:00"
TRAIN_END = "2026-09-24T00:00:00"      # train: Sept 22-23; held-out: Sept 24 00:00Z - Sept 25 06:00Z
WINDOW_END = "2026-09-25T06:00:00"
RESTATING = ("pause_entries", "resume_entries")
ROUTINE = ("look", "progress")
TRIGGER_PRIORITY = ("book.settle", "book.fill", "book.refused", "audit.verdict", "eval.verdict", "repair.status", "eval.block",
                    "code", "rung", "lesson", "tool.fulfilled", "library.note", "window", "market", "unblocked",
                    "agent.strategy", "credit.grant", "jev")


def epoch(iso):
    return datetime.fromisoformat(str(iso).replace("Z", "+00:00")).timestamp()


def iso(ep):
    return datetime.fromtimestamp(ep, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def load(prefix):
    rows = []
    for f in sorted(glob.glob(os.path.join(DATA, prefix + "_*.jsonl"))):
        with open(f) as fh:
            rows += [json.loads(l) for l in fh if l.strip()]
    for r in rows:
        r["t"] = epoch(r["at"])
    rows.sort(key=lambda r: r["seq"])
    return rows


def primary(triggers):
    classes = [str(t).split(":", 1)[0] for t in triggers or [] if t]
    if not classes:
        return ""
    return min(classes, key=lambda c: TRIGGER_PRIORITY.index(c) if c in TRIGGER_PRIORITY else len(TRIGGER_PRIORITY))


def outcome(p):
    reason = str(p.get("reason") or "")
    if reason.startswith("provider") or reason.startswith("tool outcome unconfirmed"):
        return "provider_failure"
    if p.get("candidate"):
        return "candidate"
    if int(p.get("trials") or 0) > 0:
        return "failed_evaluation"
    if reason in ("retired or changed", "credits"):
        return "other"
    return "abstained"


# ---- F2 helpers, copied read-only from ~/Work/ltcm-f-research league/research_gate.py (commit 7abb77e)
_TICKER = re.compile(r"\b[A-Z][A-Z0-9]*(?:[-.][A-Z0-9.]+)+\b")
_NUMBER = re.compile(r"\d[\d,.]*")
GENERIC_DESKS = frozenset(("open", "prices", "options", "attention"))


def refusal_class(text):
    text = _NUMBER.sub("#", _TICKER.sub("T", str(text or "")))
    return re.sub(r"\s+", " ", text).strip().lower()[:120]


def lesson_arm(agent_id):
    return "lesson" if hashlib.sha256(str(agent_id).encode("utf-8")).digest()[0] % 2 == 0 else "control"


def lesson_words(agent_id, *names):
    words = {str(agent_id).lower()} | {str(n).lower() for n in names if n}
    for name in list(words):
        venue, _, short = name.partition("-")
        if venue in ("kalshi", "alpaca") and short and short not in GENERIC_DESKS:
            words.add(short)
    return {w for w in words if w}


_TERMS = {}


def lesson_terms(p):
    key = id(p)
    if key in _TERMS:
        return _TERMS[key]
    _TERMS[key] = _lesson_terms(p)
    return _TERMS[key]


def _lesson_terms(p):
    text = f"{p.get('title') or ''} {p.get('text') or ''}".lower()
    terms = set()
    for token in re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*", text):
        parts = token.split("-")[:12]
        terms.update("-".join(parts[i:j]) for i in range(len(parts)) for j in range(i + 1, len(parts) + 1))
    return terms
