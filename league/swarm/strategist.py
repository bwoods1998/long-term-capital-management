"""The strategist (Sept 29, 2026): Claude reads the whole graveyard and the swarm's recent history, and writes the WHERE TO
LOOK section of the architect's agenda.

WHY. Idea quality and learning from failure, not compute, held the swarm back: the architect saw the 20 newest of ~800
graveyard rows, and its agenda (`architect.agenda`) was hand-written by the operator and went stale between sessions.
The architect now reads the whole graveyard on the Claude route (league/swarm/architect.py `GraveyardDigest`); the
strategist keeps the agenda's direction current.

WHAT IT READS. The same sealed graveyard digest as the architect, first in the system prompt (one cached block serves
both: the strategist's call writes it and the architect's call right after reads it), then a packet: the operator's
locked preamble (`architect.agenda_locked`, binding), the current WHERE TO LOOK section and what became of the families
born under it, the board (alive families, their mechanisms, Train figures and D2a view of Validation), how many families
fail each Validation check (counts by check name only: never a family's checks, never a number measured in 2025), the
last 24 hours' births and retirements by mechanism class, the drift note and the operator lessons on drift and costs, and
the coverage and gaps. On the Sail fallback (no Claude) the packet carries the 20 newest graveyard rows and every
operator row instead of the digest.

WHAT IT WRITES. One JSON object: `where_to_look` (at most `strategist.max_chars`, 1,600; the code's ceiling is 2,000),
`evidence` (for the operator, never sent to the architect) and `cites` (graveyard or family ids). `check_section` must
accept the section: no money, real money or envelope talk, no word about the verifier beside a verb that would change it,
no numeric rule, no 2025 or holdout, no override of the preamble, no revival of a retired idea, and at least
`strategist.min_cites` real ids cited. An accepted section is kv `architect_agenda_section` (with the one before it); the
architect's agenda is then the locked preamble verbatim followed by it (`architect.compose`). A rejected answer, a failed
call, a skipped or disabled run leave the last accepted section in place. Nothing here writes swarm.json or the locked
preamble.

WHEN. Just before an architect pass that has room to add families (`loop.Swarm.architect_pass`), at most every
`strategist.every_seconds` (3 h), only while `architect.agenda_locked` is set and `strategist.enabled`. Its Claude line
is `claude.role_usd_day["strategist"]` ($4 a UTC day by default; the router's per-role line, #416): a run whose next call
could pass it is skipped, with no call. Each run is a private `swarm.strategist` event: the section, the
verdict and its reasons, the evidence and cites, the section it would replace, the route, model, cost, usage and digest.

Standard library only.
"""

from __future__ import annotations

import json
import re
import statistics
import time
from typing import Any, Callable, Mapping, NamedTuple, Sequence

from . import diagnostics
from . import settings as settings_mod
from .architect import (AGENDA_KEY, SECTION_MAX, USAGE_KEYS, Architect, GraveyardDigest, lesson_view, locked_text, tag_of,
                        to_ascii)
from .store import SwarmStore, iso

ROLE = "strategist"
SECTION_TITLE = "WHERE TO LOOK"
KV_AT = "strategist_at"
#: A Claude call's five-minute entry lives 300 s from the start of the call that wrote it; the architect's call must
#: start inside it to read it (`loop.Swarm.architect_pass`).
PAIR_SECONDS = 270.0

SYSTEM = """You are the research strategist of a swarm of AI researchers that trade level-3 options (defined-risk structures
only) on one brokerage account. An architect proposes new research families; each family's researcher improves one
program in a Gym of recorded one-minute option quotes (Train 2022-2024) until the verifier accepts or refutes it. You
write ONLY the WHERE TO LOOK section of the architect's agenda: at most {max_chars} characters (about 1,500 is right)
naming the mechanism classes, market states, horizons, roots and structures where the evidence says new families are
most likely to earn in every Train year and pass the verifier. The operator's LOCKED PREAMBLE (in the request) binds you
and the architect. You cannot change it; your section is appended after it.

Ground every direction in THE GRAVEYARD (the system prompt's first blocks, or the request's sample of it: retired
families and every operator lesson) and in the board. Check each direction against the whole graveyard and cite the rows
it builds on or avoids. Say what to stop proposing when the families born under your last section died for one reason.
Idle-rule deaths (tag IDLE) are a time limit, not findings: say whether a class died untested (never reached a Train
score) or tested and failed. Prefer a few deep directions over many shallow ones, each with a reason to exist (a risk
premium, a flow, a behavioral bias, a venue rule) that the Gym's data can test and enough independent trades to measure.

A machine checks your section before the architect sees it. It is REJECTED, and the last section kept, if it:
- talks of money: dollars, cents, capital, budget, notional, margin, sizing, contracts per, allocation;
- talks of real money, live trading, the grant, the constitution, the envelope, the broker, the kill switch or bands;
- puts a word about the verifier (the line, a threshold, a bar, a check, a gate, a screen, DSR, Sharpe, quarters, the
  stress test, trials, looks, caps, limits, floors) in one sentence with a verb that would change it (loosen, relax,
  lower the, raise, reduce, increase, drop, remove, waive, skip, ignore, adjust, change, modify, revise, replace ...);
- states a numeric rule (a comparison sign next to a number, or "at least", "at most", "minimum" or "maximum" and a
  number): numeric rules live in the preamble; ranges of days to expiry or sessions ("1-7 DTE") are fine;
- mentions 2025, 2026, the holdout, sealed data or out-of-sample results;
- tells anyone to ignore, disregard, override or supersede anything, or speaks for the operator;
- advises re-proposing, reviving, revisiting, retrying or trying again a retired idea ("do not re-propose X" is fine);
- contains braces, code fences, URLs, markdown headings or numbered headings in capitals;
- cites fewer than {min_cites} real graveyard or family ids in "cites".

Reply with ONE JSON object and nothing else: {{"where_to_look": "<the section: plain prose, or lettered items (a), (b),
... one per line>", "evidence": "<at most 1,200 characters for the operator, never sent to the architect: the evidence
behind each direction>", "cites": ["<graveyard or family id>", "..."]}}"""


# ------------------------------------------------------------------------------------------------------------ the validator
class Verdict(NamedTuple):
    ok: bool
    reasons: list[str]
    text: str


_SPLIT = re.compile(r"(?<=[.!?;])\s+|\n+")
_URL = re.compile(r"https?://|www\.", re.I)
_HEADING = re.compile(r"^\s*(?:\d+\.\s+[A-Z]{3,}|#{1,6}\s)", re.M)
_MONEY = re.compile(r"\$|\b(?:usd|dollars?|cents?|notional|capital|budget\w*|buying power|margins?|position[- ]siz\w*|sizing|"
                    r"size up|contracts per|allocat\w*)\b", re.I)
_REAL = re.compile(r"\b(?:real[- ]money|live (?:trading|money|accounts?|orders?|path|book|tests?|grant)|grant\w*|constitution\w*|"
                   r"envelope|kill[- ]?switch\w*|broker\w*|(?:probe|sized|candidate) bands?)\b", re.I)
#: Everyday phrases that only look like the verifier's words (small caps, limit orders, minute bars, quarter-end flows).
_BENIGN = re.compile(r"\b(?:(?:small|large|mid|micro|mega)[- ]caps?|limit (?:orders?|prices?)|(?:one-|five-|\d+-)?minute bars?|"
                     r"daily bars?|quarter[- ](?:end|start)s?|quarterly|end of (?:the |a )?quarter|market stress|stress(?:ed)? "
                     r"(?:markets?|regimes?|days?|periods?|events?|sessions?))\b", re.I)
_PROTECTED = re.compile(r"\b(?:d2\w*|verifier\w*|validation|thresholds?|lines?|bars?|checks?|gates?|screens?|drift (?:rules?|"
                        r"screens?|tests?)|kill tests?|deflat\w*|dsr|sharpe\w*|t-stat\w*|p-values?|significan\w*|quarters?|"
                        r"stress\w*|half-spread|caps?|limits?|ceilings?|floors?|ration\w*|looks|trials?)\b|\b1\.5x\b", re.I)
_CHANGE = re.compile(r"\b(?:loosen\w*|relax\w*|lower(?:s|ed|ing)?\s+(?:the|its|their|a|an|our|this|that|these|those)\b|"
                     r"reduc\w*|rais(?:e|es|ed|ing)|increas\w*|drop\w*|remov\w*|waiv\w*|skip\w*|bypass\w*|exempt\w*|"
                     r"ignor\w*|overrid\w*|disabl\w*|turn(?:s|ed|ing)? off|suspend\w*|soften\w*|eas(?:e|es|ed|ing)|weaken\w*|"
                     r"chang\w*|adjust\w*|modif\w*|revis(?:e|es|ed|ing)|redefin\w*|replac\w*)\b", re.I)
_COMPARE = re.compile(r"(?:>=|<=|=>|=<|[<>])\s*[-+]?\$?\.?\d|\d\s*(?:>=|<=|[<>])")
_BOUND = re.compile(r"\b(?:at least|at most|no more than|no fewer than|no less than|(?:a )?minimum(?: of)?|(?:a )?maximum(?: of)?)"
                    r"\s+[-+]?\$?\d", re.I)
_D2 = re.compile(r"\b(?:2025|2026|hold[- ]?outs?|sealed|out[- ]of[- ]sample|oos)\b", re.I)
_OVERRIDE = re.compile(r"\b(?:ignor\w*|disregard\w*|supersed\w*|overrid\w*|new rules?|system prompt|you are now|as the operator|"
                       r"operator (?:says|said|wants|wanted|decided|decides|asks|asked|approved|allows))\b", re.I)
_VOID_WHAT = re.compile(r"\bthe (?:preamble|rules?|graveyard|locked \w+)\b", re.I)
_VOID_HOW = re.compile(r"\b(?:no longer|does not apply|do not apply|doesn'?t apply|don'?t apply|is wrong|are wrong|is outdated|"
                       r"is stale)\b", re.I)
_REVIVE = re.compile(r"\b(?:re-?propos\w*|reviv\w*|resurrect\w*|reopen\w*|revisit\w*|retr(?:y|ies|ied|ying)|again)\b", re.I)
_NEGATION = re.compile(r"\b(?:not|never|no|nor|avoid\w*|stop\w*|don'?t|without)\b", re.I)


def normalize(text: Any) -> str:
    """The section as it is kept and composed: ASCII, spaces collapsed within each line, blank lines dropped."""
    lines = (" ".join(to_ascii(line).split()) for line in str(text or "").splitlines())
    return "\n".join(line for line in lines if line).strip()


def check_section(text: Any, *, max_chars: int, cites: Any, known_ids: set[str] | frozenset[str], min_cites: int) -> Verdict:
    """The validator (a pure function): `Verdict(ok, reasons, text)` for a WHERE TO LOOK section, `text` normalized. Each
    reason starts with its rule's name (shape, money, real_money, threshold, numeric_rule, d2, override, revival,
    grounding) and quotes the sentence that broke it. Mentioning a check without a changing verb is allowed ("most
    families fail t and DSR, so look where trades are plentiful"); "do not re-propose X" is allowed."""
    reasons: list[str] = []
    raw = text if isinstance(text, str) else ""
    clean = normalize(raw)
    cap = max(1, min(int(max_chars), SECTION_MAX))

    def say(rule: str, what: str) -> None:
        reasons.append(f"{rule}: {what[:160]}")

    if not clean:
        say("shape", "the section is empty")
    if len(clean) > cap:
        say("shape", f"{len(clean)} characters, over the cap of {cap}")
    if "```" in raw or "{" in raw or "}" in raw:
        say("shape", "braces or a code fence")
    if _URL.search(raw):
        say("shape", "a URL")
    if _HEADING.search(raw):
        say("shape", "a heading that could pass for an item of the locked preamble")
    for sentence in (x.strip() for x in _SPLIT.split(clean) if x.strip()):
        if _MONEY.search(sentence):
            say("money", sentence)
        if _REAL.search(sentence):
            say("real_money", sentence)
        plain = _BENIGN.sub(" ", sentence)
        if _PROTECTED.search(plain) and _CHANGE.search(plain):
            say("threshold", sentence)
        if _COMPARE.search(sentence) or _BOUND.search(sentence):
            say("numeric_rule", sentence)
        if _D2.search(sentence):
            say("d2", sentence)
        if _OVERRIDE.search(sentence) or (_VOID_WHAT.search(sentence) and _VOID_HOW.search(sentence)):
            say("override", sentence)
        if _REVIVE.search(sentence) and not _NEGATION.search(sentence):
            say("revival", sentence)
    named = {str(c) for c in cites if isinstance(c, str)} if isinstance(cites, list) else set()
    real = named & set(known_ids)
    if len(real) < int(min_cites):
        say("grounding", f"{len(real)} real graveyard or family ids cited, fewer than {int(min_cites)}")
    return Verdict(not reasons, reasons, clean)


def extract_where(agenda: Any) -> str | None:
    """The hand-written agenda's own WHERE TO LOOK item, up to the next numbered item: the strategist's "current section"
    before it has written one. None when the agenda has none."""
    text = str(agenda or "")
    found = re.search(r"WHERE TO LOOK", text, re.I)
    if not found:
        return None
    rest = text[found.start():]
    later = re.search(r"\n\s*\d+\.\s+\S", rest[1:])
    part = rest[: later.start() + 1] if later else rest
    return part.strip() or None


# ------------------------------------------------------------------------------------------------------ the packet's parts
INDEX_ROOTS = frozenset({"XSP", "SPXW", "SPX", "NDX", "RUT", "VIX", "XND", "MRUT"})
ETF_ROOTS = frozenset({"SPY", "QQQ", "IWM", "DIA", "TLT", "IEF", "SHY", "LQD", "HYG", "GLD", "SLV", "GDX", "USO", "UNG", "SMH",
                       "SOXL", "SOXS", "TQQQ", "SQQQ", "SPXL", "UPRO", "TNA", "VXX", "UVXY", "SVXY", "KRE", "XBI", "XOP", "EEM",
                       "EFA", "FXI", "ARKK", "IBIT", "KWEB", "MSOS", "TSLL", "NVDL"})


def root_group(root: str) -> str:
    root = str(root or "").upper()
    if root in INDEX_ROOTS:
        return "index"
    if root in ETF_ROOTS or re.fullmatch(r"XL[A-Z]{1,2}", root):
        return "etf"
    return "names"


def mechanism_class(structure: Any, roots: Sequence[str]) -> str:
    """A family's mechanism class for the day's counts: its structure by its roots' group (index, etf, names, or a mix)."""
    groups = sorted({root_group(r) for r in roots or []}) or ["none"]
    return f"{structure} x {'+'.join(groups)}"


def _val(fam: Mapping[str, Any]) -> str:
    line = (fam.get("state") or {}).get("validation_line")
    if not line:
        return "never"
    view = diagnostics.validation_view({}, line)
    return "MET" if view["line_met"] else f"no {view['checks_passed']}/{view['checks']}"


def _hours(a: Any, b: Any) -> float | None:
    import datetime as dt

    try:
        t0 = dt.datetime.fromisoformat(str(a).replace("Z", "+00:00"))
        t1 = dt.datetime.fromisoformat(str(b).replace("Z", "+00:00"))
    except ValueError:
        return None
    return (t1 - t0).total_seconds() / 3600.0


def _tag(fam: Mapping[str, Any]) -> str:
    return tag_of({"family": fam["id"], "lesson": ""}, fam)


class Strategist:
    """The strategist (the module docstring). `run()` never raises."""

    def __init__(self, store: SwarmStore, router: Any, settings: Mapping[str, Any], *, digest: GraveyardDigest | None = None,
                 clock: Callable[[], float] = time.time, architect: Architect | None = None):
        self.store = store
        self.router = router
        self.settings = settings
        self.digest = digest
        self.clock = clock
        self.architect = architect or Architect(store, router, settings, clock=clock)

    @property
    def cfg(self) -> Mapping[str, Any]:
        return self.settings.get("strategist", {}) or {}

    def enabled(self) -> bool:
        return self.cfg.get("enabled", True) is True

    def due(self) -> bool:
        """Enabled, the operator's locked preamble set, and `every_seconds` since the last run."""
        if not self.enabled() or not locked_text(self.settings):
            return False
        every = float(self.cfg.get("every_seconds", 10800) or 0)
        return self.clock() - float(self.store.get(KV_AT, 0.0) or 0.0) >= every

    def max_chars(self) -> int:
        try:
            return max(200, min(int(self.cfg.get("max_chars", 1600)), SECTION_MAX))
        except (TypeError, ValueError):
            return 1600

    def min_cites(self) -> int:
        try:
            return max(0, int(self.cfg.get("min_cites", 3)))
        except (TypeError, ValueError):
            return 3

    def system(self) -> str:
        text = SYSTEM.format(max_chars=self.max_chars(), min_cites=self.min_cites())
        return settings_mod.train_span_text(text, settings_mod.objective_span(self.store.get("train_objective")))

    def current(self) -> dict[str, Any]:
        """The section the architect reads now: the latest accepted one, else the hand-written agenda's WHERE TO LOOK
        item (`extract_where`), else none."""
        section = self.store.get(AGENDA_KEY)
        if isinstance(section, dict) and str(section.get("text") or "").strip():
            return {"text": str(section["text"]), "at": section.get("at"), "run": section.get("run"), "accepted": True}
        legacy = extract_where((self.settings.get("architect") or {}).get("agenda"))
        return {"text": legacy or "", "at": None, "run": None, "accepted": False}

    def known_ids(self) -> set[str]:
        return ({r["family"] for r in self.store._all("SELECT family FROM graveyard")}
                | {r["id"] for r in self.store._all("SELECT id FROM families")})

    # ------------------------------------------------------------------ the packet
    def _since_section(self, current: Mapping[str, Any], fams: list[dict[str, Any]]) -> dict[str, Any]:
        at = current.get("at") if current.get("accepted") else None
        born = [f for f in fams if f["origin"] == "architect" and (at is None or f["born_at"] >= str(at))]
        if at is None:
            born = [f for f in born if f["born_at"] >= iso(self.clock() - 86400)]
        rows, classes = [], {}
        for f in born:
            cls = mechanism_class(f["structure"], f["roots"])
            classes[cls] = classes.get(cls, 0) + 1
            best = f.get("best_train")
            rows.append({"family": f["id"], "class": cls,
                         "outcome": f"retired {_tag(f)}" if f["retired_at"] else "alive",
                         "eligible_train_version": best is not None,
                         "train_sign": None if best is None else ("+" if float(best) > 0 else "-"), "val": _val(f)})
        return {"since": at or "the last 24 hours (no accepted section yet)", "births": len(born),
                "by_class": dict(sorted(classes.items(), key=lambda kv: -kv[1])), "families": rows[-80:]}

    def _board(self, fams: list[dict[str, Any]]) -> list[dict[str, Any]]:
        alive = {f["id"]: f for f in fams if not f["retired_at"]}
        board = (self.store.get("leaderboard") or {}).get("board") or []
        order = [r["family"] for r in board if r.get("family") in alive] or list(alive)
        shares = {r["family"]: r.get("share") for r in board if isinstance(r, dict) and "family" in r}
        out = []
        for fid in order[:60]:
            f = alive[fid]
            out.append({"family": fid, "band": f["band"], "structure": f["structure"], "roots": f["roots"], "val": _val(f),
                        "share": shares.get(fid), "best_train": f.get("best_train"), "trials": f.get("trials"),
                        "mechanism": lesson_view(f["mechanism"])[:300]})
        return out

    @staticmethod
    def _checks(fams: list[dict[str, Any]]) -> dict[str, Any]:
        """Across every family with a validation line: how many fail each check (by name), how many were validated and
        passed, and how many checks they passed (a histogram). Counts only."""
        failing: dict[str, int] = {}
        passed_hist: dict[str, int] = {}
        validated = passed = 0
        for f in fams:
            line = (f.get("state") or {}).get("validation_line")
            if not isinstance(line, Mapping) or not isinstance(line.get("checks"), Mapping):
                continue
            validated += 1
            passed += int(bool(line.get("passed")))
            checks = line["checks"]
            for name, ok in checks.items():
                if not ok:
                    failing[str(name)] = failing.get(str(name), 0) + 1
            k = f"{sum(1 for ok in checks.values() if ok)}/{len(checks)}"
            passed_hist[k] = passed_hist.get(k, 0) + 1
        return {"families_validated": validated, "families_passed": passed,
                "failing_by_check": dict(sorted(failing.items(), key=lambda kv: -kv[1])),
                "checks_passed_histogram": dict(sorted(passed_hist.items(), key=lambda kv: kv[0], reverse=True))}

    def _day(self, fams: list[dict[str, Any]]) -> dict[str, Any]:
        since = iso(self.clock() - 86400)
        born = [f for f in fams if f["born_at"] >= since]
        gone = [f for f in fams if f["retired_at"] and f["retired_at"] >= since]
        births: dict[str, list[str]] = {}
        for f in born:
            births.setdefault(mechanism_class(f["structure"], f["roots"]), []).append(f["id"])
        deaths: dict[str, int] = {}
        tags: dict[str, int] = {}
        lives = []
        for f in gone:
            cls = mechanism_class(f["structure"], f["roots"])
            deaths[cls] = deaths.get(cls, 0) + 1
            tag = _tag(f)
            tags[tag] = tags.get(tag, 0) + 1
            hours = _hours(f["born_at"], f["retired_at"])
            if hours is not None:
                lives.append(hours)
        return {"births": len(born), "retirements": len(gone),
                "births_by_class": {k: {"n": len(v), "families": v[-25:]} for k, v in sorted(births.items(), key=lambda kv: -len(kv[1]))},
                "retirements_by_class": dict(sorted(deaths.items(), key=lambda kv: -kv[1])),
                "retirements_by_tag": dict(sorted(tags.items(), key=lambda kv: -kv[1])),
                "median_life_hours_of_the_retired": round(statistics.median(lives), 2) if lives else None,
                "retired_with_a_train_score": sum(1 for f in gone if f.get("best_train") is not None)}

    def _drift_and_costs(self) -> dict[str, Any]:
        ops = [r for r in self.store._all("SELECT family, lesson FROM graveyard WHERE family LIKE 'op-%' ORDER BY at, family")
               if re.search(r"\b(?:drift|costs?|fees?|spreads?|natural|mid)\b", str(r["lesson"]), re.I)]
        return {"drift_note": diagnostics.DRIFT_NOTE, "operator_rows_on_drift_and_costs": [r["family"] for r in ops]}

    def _sample(self) -> list[dict[str, Any]]:
        """The graveyard for a call without the digest: the 20 newest rows and every operator row, through `lesson_view`."""
        rows = self.store.graveyard(limit=20)
        seen = {r["family"] for r in rows}
        rows += [r for r in self.store.graveyard(limit=10 ** 9) if r["family"].startswith("op-") and r["family"] not in seen]
        return [{"family": r["family"], "structure": r["structure"], "roots": r["roots"], "lesson": lesson_view(r["lesson"])[:700]}
                for r in rows]

    def packet(self, current: Mapping[str, Any] | None = None, *, sample: bool = False) -> str:
        """The request (the module docstring). `sample` adds the graveyard's 20 newest rows and every operator row, for a
        call that has no digest (the Sail fallback)."""
        current = current or self.current()
        fams = self.store.families()
        age = None
        if current.get("at"):
            age = _hours(current["at"], iso(self.clock()))
        whose = (f"accepted {round(age, 1)} h ago" if age is not None else
                 "from the operator" if current.get("text") else "none yet")
        parts = [
            "THE LOCKED PREAMBLE (the operator's; binding on you and the architect; you cannot change it):\n"
            + locked_text(self.settings),
            f"THE CURRENT {SECTION_TITLE} SECTION ({whose}):\n" + (str(current.get("text") or "") or "(none)"),
            "WHAT BECAME OF THE FAMILIES THE ARCHITECT BORE UNDER IT (outcome; whether it reached an eligible Train version; "
            "the sign of its best Train score; val as D2a allows):\n" + json.dumps(self._since_section(current, fams)),
            "THE BOARD (alive families):\n" + json.dumps(self._board(fams)),
            "VALIDATION CHECKS FAILED, BY CHECK (counts across every validated family; never a number):\n"
            + json.dumps(self._checks(fams)),
            "THE LAST 24 HOURS (mechanism class = structure x root group: index, etf, names):\n" + json.dumps(self._day(fams)),
            "DRIFT AND COSTS (the drift note every researcher reads; the operator rows about drift and costs are in the "
            "graveyard):\n" + json.dumps(self._drift_and_costs()),
            "RESEARCH COVERAGE (effort, not profitability):\n" + json.dumps(self.architect.coverage(), separators=(",", ":")),
            "GAPS (uncovered structure types by root):\n" + json.dumps(self.architect.gaps()),
        ]
        if sample:
            parts.append("THE GRAVEYARD (the 20 newest rows and every operator row; the rest is not shown):\n"
                         + json.dumps(self._sample()))
        parts.append(f"Write the {SECTION_TITLE} section now: ONE JSON object with where_to_look, evidence and cites.")
        return "\n\n".join(parts)

    # ------------------------------------------------------------------ money
    def affordable(self, system: str, user: str, prefix: Sequence[Mapping[str, Any]] | None) -> str | None:
        """Why a Claude call with this request cannot be made now, or None: the strategist's own line today
        (`claude.role_usd_day["strategist"]`, the router's `claude_role_room`: holds count until they settle) is short of
        the call's worst case. The router checks the same line again when it books the hold; this skips the run first,
        so a run it cannot afford never falls to Sail instead."""
        try:
            _, ceiling = self.router.claude_request(system, user, prefix=prefix, role=ROLE)
        except Exception as exc:  # noqa: BLE001
            return f"the request could not be priced: {exc}"[:300]
        room = getattr(self.router, "claude_role_room", lambda role: None)(ROLE)
        if room is not None and float(room) < float(ceiling):
            return (f"the strategist's Claude line for today (claude.role_usd_day): ${float(room):.2f} left, the next call "
                    f"may cost ${float(ceiling):.2f}")
        return None

    def digest_ttl(self) -> str | None:
        """The strategist's call writes the sealed digest for the architect's call right after it: "5m", or "1h" once the
        gateway admits it (`claude.cache_1h`); none with `architect.graveyard_digest_ttl` "off"."""
        mode = str((self.settings.get("architect") or {}).get("graveyard_digest_ttl") or "5m")
        if mode == "off":
            return None
        return "1h" if mode == "1h" and (self.settings.get("claude") or {}).get("cache_1h") is True else "5m"

    # ------------------------------------------------------------------ one run
    def run(self) -> dict[str, Any]:
        """One run: never raises. A disabled strategist returns at once (no event); every other outcome is a
        `swarm.strategist` event, and only an accepted section changes the agenda."""
        began = self.clock()
        if not self.enabled():
            return {"skipped": "the strategist is disabled"}
        self.store.put(KV_AT, began)
        try:
            out = self._run(began)
        except Exception as exc:  # noqa: BLE001 - the agenda stays as it was
            out = {"accepted": False, "error": f"{type(exc).__name__}: {str(exc)[:300]}",
                   "billed": list(getattr(exc, "billed", []) or [])}
        out["seconds"] = round(self.clock() - began, 1)
        self.store.event("swarm.strategist", None, out)
        return out

    def _run(self, began: float) -> dict[str, Any]:
        if not locked_text(self.settings):
            return {"accepted": False, "skipped": "architect.agenda_locked is empty: the agenda is the operator's own"}
        current = self.current()
        system = self.system()
        compact = self.packet(current, sample=True)
        extra: dict[str, Any] = {}
        info: dict[str, Any] | None = None
        claude = bool(getattr(self.router, "claude_enabled", lambda role: False)(ROLE))
        if claude:
            prefix: list[dict[str, Any]] = []
            full = (self.settings.get("architect") or {}).get("full_graveyard", True) is True
            if self.digest is not None and full:
                try:
                    snap = self.digest.snapshot()
                    ttl = self.digest_ttl()
                    prefix = self.digest.blocks(ttl, snap)
                    info = {"rows": snap.rows, "sealed_rows": snap.sealed_rows, "level": snap.level, "sha": snap.sha, "ttl": ttl,
                            "chars": len(snap.sealed) + len(snap.tail), "resealed": snap.resealed}
                except Exception as exc:  # noqa: BLE001 - asked without the digest (the sample, as on Sail)
                    prefix, info = [], {"error": f"{type(exc).__name__}: {str(exc)[:200]}"}
            user = self.packet(current) if prefix else compact
            why = self.affordable(system, user, prefix or None)
            if why:
                return {"accepted": False, "skipped": why}
            extra = {"claude_prefix": prefix or None, "claude_system": system, "claude_user": user}
        answer = self.router.ask(role=ROLE, system=system, user=compact, family=None, key=f"swarm:strategist:{int(began)}",
                                 openai_model=None, sail_profile=str(self.cfg.get("sail_profile") or "") or None,
                                 max_output=int(self.cfg.get("max_output_tokens", 12000)), effort="high", need_usd=0.0,
                                 desk="strategist", cap_usd_day=float(self.cfg.get("sail_usd_day", 1.0)), claude=True, **extra)
        route = answer.get("route")
        out: dict[str, Any] = {"route": route, "model": answer.get("model"), "cost_usd": answer.get("cost_usd"),
                               "previous": {"text": current.get("text"), "at": current.get("at"), "run": current.get("run")}}
        if answer.get("fallback_reasons"):
            out["fallback_reasons"] = [str(r)[:200] for r in answer["fallback_reasons"]][:4]
        if route == "claude":
            usage = answer.get("usage") or {}
            out["usage"] = {k: usage[k] for k in USAGE_KEYS if k in usage}
        on_digest = route == "claude" and bool(extra.get("claude_prefix")) and info is not None and "sha" in info
        if info is not None:
            out["digest"] = {**info, "used": on_digest}
        if on_digest and self.digest is not None:
            usage = answer.get("usage") or {}
            self.digest.record_call(info["sha"], info["ttl"], began)
            sent = sum(len(b["text"]) for b in extra["claude_prefix"]) + len(extra["claude_system"]) + len(extra["claude_user"])
            self.digest.calibrate(usage, sent)
        # Primed: the architect's call right after this one reads the sealed digest this call just marked (caches are per
        # model: `claude.role_model` giving the two roles different models would leave nothing to read).
        same = getattr(self.router, "claude_model", None)
        same_model = not callable(same) or answer.get("model") == same("architect")
        out["primed"] = bool(on_digest and info.get("ttl") and same_model)
        data = answer.get("json")
        where = data.get("where_to_look") if isinstance(data, dict) else None
        cites = data.get("cites") if isinstance(data, dict) else None
        evidence = data.get("evidence") if isinstance(data, dict) else None
        if not isinstance(where, str) or not isinstance(cites, list) or (evidence is not None and not isinstance(evidence, str)):
            out.update(accepted=False, reasons=["shape: the answer was not one JSON object with where_to_look, evidence and cites"],
                       text=str(answer.get("text") or "")[:600])
            return out
        verdict = check_section(where, max_chars=self.max_chars(), cites=cites, known_ids=self.known_ids(),
                                min_cites=self.min_cites())
        out.update(accepted=verdict.ok, reasons=verdict.reasons, text=verdict.text[: SECTION_MAX * 2],
                   evidence=str(evidence or "")[:1200], cites=[str(c)[:80] for c in cites if isinstance(c, str)][:40])
        if verdict.ok:
            self.store.put(AGENDA_KEY, {"text": verdict.text, "at": iso(began), "run": int(began), "route": route,
                                        "model": answer.get("model"), "cost_usd": answer.get("cost_usd"),
                                        "cites": out["cites"], "previous": out["previous"]})
        return out


__all__ = ["Strategist", "check_section", "extract_where", "normalize", "Verdict", "ROLE", "SYSTEM", "SECTION_TITLE",
           "PAIR_SECONDS", "mechanism_class", "root_group"]
