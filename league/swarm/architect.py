"""The architect: every `every_seconds` (four hours by default), 3-6 new families from the leaderboard, the graveyard
and the gaps.

The population (plan: 48 at the start, a ceiling of 96, a floor of 16; `population` in swarm.json may set others): while
fewer families live than the start (retirements drained it), it REFILLS: every `refill_seconds` (an hour by default), up
to the gap to the start (at most `max_refill` a pass). At or above the start it grows toward the ceiling at the plan's
pace, and the loop runs that growth only while the swarm's hourly spend is under its pace (money allows). A birth spends
nothing by itself: the hourly pace caps every researcher's cycles together.

Claude first (`claude.model`, or `claude.role_model["architect"]`; "architect" is a default `claude.roles` entry) while
its funded total has room; every other pass asks GPT-6 Astra first only while `architect.openai_model` names it (null
makes the architect Claude-only); else Kimi-K3 balanced on Sail. It reads the leaderboard (families, bands, shares, and
of Validation only whether the line was met and how many of its checks passed: the owner's decision D2a), the
graveyard's lessons, and the GAPS (roots x structure types no living family covers), and answers with new families: a
mechanism (why it should make money), a structure, a universe slice (one to five pooled roots of the admitted list, days
to expiry) and a rejection test. The swarm admits those that are well-formed, distinct from the living families and
inside the population ceiling; each new family's researcher writes its first program (no starter). The operator steers
it without a deploy through `architect.agenda` (swarm.json): a non-empty agenda closes the request as "THE OPERATOR'S
RESEARCH AGENDA".

THE FULL GRAVEYARD (Sept 29, 2026). On the Claude route the architect reads EVERY graveyard row, as a digest
(`GraveyardDigest`) placed first in the system prompt, before its own instructions and the request: one line of id,
structure, roots, tag and Train figures per row, its mechanism and its lesson verdict first, lineages grouped. The
digest is SEALED: the rows up to a point are rendered once and stay byte-identical (the cached block), and rows buried
since ride after it uncached, until they pass `graveyard_digest_tail_share` of the budget and it is sealed again. When
the graveyard outgrows `graveyard_digest_tokens`, a ladder shortens rows (idle rows to one line, then to id lists) and
never drops one. Every proposal names the rows it differs from (`differs_from`); each pass reports how many cited a
real row. OpenAI and Sail keep the 20 newest rows (their contexts are small). Of Validation the digest says only what
D2a allows (met, or not met with k of 8 checks, or never), and every lesson a model reads here passes `lesson_view`,
which drops any sentence about Validation, the holdout, out-of-sample results or 2025.

THE AGENDA. `architect.agenda_locked` (the operator's preamble) set, and a WHERE TO LOOK section accepted from the
strategist (league/swarm/strategist.py, kv `architect_agenda_section`): the agenda is the locked text verbatim, then the
section. Otherwise it is `architect.agenda` exactly as before.

Each pass is a `swarm.architect` event; each birth a `swarm.born` event (the site's news).
Standard library only.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import unicodedata
from dataclasses import dataclass, replace
from typing import Any, Callable, Mapping, Sequence

from . import diagnostics
from . import settings as settings_mod
from .researcher import MAX_ROOTS
from .store import STRUCTURES, SwarmStore, iso

#: Two mechanisms are the same idea when their content words overlap this much (Jaccard).
SAME_IDEA = 0.5
_STOP = frozenset("a an and are as at be by for from in into is it its of on or than that the their then this to when with "
                  "options option sell buy".split())


def words(text: str) -> frozenset[str]:
    return frozenset(w for w in "".join(c if c.isalnum() else " " for c in str(text).lower()).split()
                     if len(w) > 2 and w not in _STOP)


def same_idea(a: str, b: str) -> bool:
    x, y = words(a), words(b)
    return bool(x and y) and len(x & y) / len(x | y) >= SAME_IDEA

SYSTEM = """You are the architect of a swarm of AI researchers that trade level-3 options (defined-risk structures only) on one
brokerage account. Each researcher owns one family: a mechanism, a structure type and a universe slice, and improves a
program for it in a Gym of real recorded one-minute option quotes (Train 2022-2024; Validation 2025 by summary only; a
sealed holdout at the gate). Propose NEW families that are likely to clear the validation line (>= 50 trades on >= 25
days a year, mean P&L per dollar of max loss > 0 with t >= 2 after fees and the spread, a deflated Sharpe on traded days
that survives the lineage's validated versions, 3 of 4 quarters positive, positive at 1.5x the half-spread). A family's
Train score is its WORST Train year, so a mechanism must earn in 2022, 2023 and 2024 alike, with at least 40 trades on
20 days in each. Prefer mechanisms with a reason to exist
(a risk premium, a flow, a behavioral bias, a venue rule), horizons supported by the available data, and slices the
swarm does not cover. The strategy still needs enough independent trades to be evaluated. Learn from the graveyard:
do not re-propose what failed unless you say what is different.

Use only the available roots listed in the current request; that configured list is the Gym's data universe. A
family may pool one to five of them: the same mechanism on several roots trades more often and is measured sooner
(days traded on several roots count once a day, so pool roots that trade on different days).
XSP and SPXW are cash-settled index options with no calendars or diagonals. XSP costs $0.50 a contract, which makes a
narrow XSP structure uneconomic: use XSP only for structures wide enough to carry that fee. The other available roots
are physically settled equity or ETF options. Structure types: long_call, long_put, debit_vertical, credit_vertical, iron_condor, iron_butterfly,
long_butterfly, long_straddle, long_strangle, calendar, diagonal. All listed types compete on the same evidence:
complexity earns no preference. Single calls and puts are first-class research choices. Consider the simplest
expression of each mechanism before adding legs; use additional legs when they serve the hypothesis. Use the coverage
counts and gaps to explore neglected types and roots, while retaining the lessons and trial history of failed ideas.
Research support does not imply brokerage execution support; the House checks that separately. Do not invent a data
source, a supported strategy type, or evidence to fill a coverage gap.

Reply with ONE JSON object: {"families": [{"slug": "short-kebab-name", "mechanism": "one or two sentences: why it should
make money", "structure": "<type>", "roots": ["SPY", "QQQ"], "dte": [0, 2], "rejection": "the result that would prove it
wrong", "sketch": "how the program should decide, in plain words", "parent": "retired family id, if revising its idea"}]}.
A renamed or revised version of a retired mechanism must name its parent; it inherits the entire lineage's trials
and three-look holdout ration. Only a different economic mechanism starts a new lineage."""


# ---------------------------------------------------------------------------------------------------------------- the digest
#: The digest's format: a change here reseals it (a new cache entry once).
DIGEST_FORMAT = 1
#: kv: the strategist's latest accepted WHERE TO LOOK section, the digest's seal, and the measured characters per token.
AGENDA_KEY = "architect_agenda_section"
SEAL_KEY = "graveyard_digest_seal"
CPT_KEY = "graveyard_digest_cpt"
LAST_KEY = "graveyard_digest_last"
#: What an event keeps of a Claude call's usage: the standing proof that the cache is read.
USAGE_KEYS = ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens", "output_tokens", "cache_creation")
#: The locked preamble's and the strategist's section's caps (the section's whatever `strategist.max_chars` says).
AGENDA_LOCKED_MAX = 4000
SECTION_MAX = 2000
#: The digest's hard size cap: the gateway takes a body of at most 1 MiB (claude.mjs MAX_REQUEST_BYTES), and the role's
#: own text, the request and the JSON framing ride with it.
MAX_DIGEST_BYTES = 600_000
#: Characters per token before any call has measured it (`GraveyardDigest.calibrate`), and its bounds.
DEFAULT_CPT = 3.0
CPT_BOUNDS = (2.5, 4.5)
#: The agenda's titles: the operator's own (as before), and the locked preamble with the strategist's section.
LEGACY_AGENDA_TITLE = "THE OPERATOR'S RESEARCH AGENDA"
COMPOSED_AGENDA_TITLE = "THE RESEARCH AGENDA (the operator's locked preamble, then the strategist's WHERE TO LOOK)"
WHERE_HEADER = "WHERE TO LOOK (written by the strategist at {at}; the preamble above binds it):"

#: The digest's header, role-neutral: the architect and the strategist send the same bytes, so one cache entry serves both.
DIGEST_HEADER = (
    "THE GRAVEYARD: every retired family and every operator lesson ({rows} rows, sealed {at}). Binding: an idea here is "
    "not proposed again unless the proposal names the rows it differs from and the mechanism-level change.\n"
    "Row: <id> [<structure> <ROOTS>] <TAG> v<versions>/<trials>t train <worst Train year score|None> val <MET|no k/8|never>\n"
    "  M: the mechanism   L: the lesson, its verdict first\n"
    "\" + <id> ...\" lines are later families of the same lineage. \"<TAG>, <structure> (n): id, id, ...\" lines list rows "
    "shortened to their ids (the graveyard outgrew the digest's budget).\n"
    "val: the validation line met (MET), not met with k of 8 checks passed (no k/8), or never validated (never).\n"
    "TAGS: OPERATOR = the operator's pre-registered test (binding) | REFUTED = refuted on its own evidence | DIAGNOSED = "
    "retired on the diagnostician's reading | TRIALS = trial-adjusted evidence fell short | STALL = no improvement over "
    "many revisions | OPERATOR-RETIRED = the operator's housekeeping | IDLE = retired by the idle rule: a time limit, NOT a "
    "finding (the idea may be untested).\n\n")
TAIL_HEADER = "ROWS BURIED SINCE THE SEAL ({rows} rows; {total} in the graveyard in all), oldest first:\n"

#: Every sentence a model reads of a lesson that names Validation, the holdout, out-of-sample results, 2025, the deflated
#: Sharpe (a Validation check) or a figure `diagnostics.scrub` withheld is dropped (D2a): scrub takes figures out after
#: "validation", but ~10% of the lessons (Sept 29) still said "Validation stands at mean ... -0.019, t -0.67". Only the
#: D2a words themselves (`_SAFE`) may stay.
_VAL = re.compile(r"\b(?:validat\w*|val|out[- ]of[- ]sample|oos|hold[- ]?outs?|sealed|2025|dsr|deflated)\b|\(withheld\)", re.I)
_SAFE = re.compile(r"best validation: (?:line (?:not )?met|not recorded|never validated|(?:did not meet|met) the validation line"
                   r"(?: \(\d+ of \d+ checks passed\))?)|(?:did not meet|met) the validation line(?: \(\d+ of \d+ checks "
                   r"passed\))?|no validation improvement|never validated", re.I)
_SENTENCE = re.compile(r"(?<=[.!?;|])\s+")
_ASCII = {"\u2014": "-", "\u2013": "-", "\u2019": "'", "\u2018": "'", "\u201c": '"', "\u201d": '"', "\u2265": ">=",
          "\u2264": "<=", "\u00d7": "x", "\u2192": "->", "\u2026": "...", "\u2248": "~", "\u2212": "-", "\u00a0": " "}
#: A lesson's parts (store.retire_gym): "<structure> on <roots>: <reason>. Tried N versions over M lineage trials; best
#: Train score X; best validation: V. Last notes: a | b | c".
_HEAD = re.compile(r"^[a-z_]+ on [A-Z0-9., ]{1,120}: ")
_STATS = re.compile(r"Tried (\S+) versions? over (\S+) lineage trials?; best Train score ([^;]+); best validation: (.*?)\.(?=\s|$)")
_IDLE = re.compile(r"It (?:made|kept)\b.*?not a finding that the mechanism has no edge\.?", re.S)
#: The tournament's own retirement reasons: the tag already says them (STALL, TRIALS).
_RULE = re.compile(r"^(?:no validation improvement in \d+ (?:revisions|Gym evaluations)|its trial-adjusted evidence fell below "
                   r"the line(?: \(the deflated Sharpe probability\))?)\.?$", re.I)
IDLE_MARK = "not a finding that the mechanism has no edge"
_HOLD = re.compile(r"^(?:Held a cycle \(no run\):\s*)?(?:(?:First|Second|Third|Fourth|Fifth|Sixth|Seventh|Eighth|Ninth|Tenth|"
                   r"Eleventh|Twelfth|\w+)(?: consecutive)? hold\.?\s*)?", re.I)
_KEY = re.compile(r"(do not re-propose|never re-propose|refuted|did not replicate|no edge|no capturable|fails?|failed|lottery|"
                  r"drift)", re.I)
#: Tags in the order the id lists print them.
TAGS = ("OPERATOR", "REFUTED", "DIAGNOSED", "TRIALS", "STALL", "OPERATOR-RETIRED", "IDLE")
#: Characters of mechanism and lesson a row gets at scale 1.0, by tier ("VAL": a Train-scored or validated row).
TIER_CHARS = {"OPERATOR": (420, 900), "VAL": (300, 520), "DIAGNOSED": (260, 420), "REFUTED": (240, 380), "TRIALS": (240, 360),
              "STALL": (240, 360), "OPERATOR-RETIRED": (200, 260), "IDLE": (180, 220)}
FOLLOWER_CHARS = 160
#: The collapse ladder (`_render`): 0 every row at its tier; 1 idle rows never Train-scored to one line; 2 those to id lists;
#: 3 every row but the operator's, the refuted, the diagnosed and the Train-scored or validated to id lists, and lineage
#: followers to their ids; 4 (only past ~8,000 rows at the default budget) every row to id lists.
LEVELS = (0, 1, 2, 3)
MIN_SCALE, GOOD_SCALE, MAX_SCALE = 0.1, 0.3, 1.5


def to_ascii(text: Any) -> str:
    """Text as the digest sends it: common punctuation mapped to ASCII, the rest decomposed and kept if ASCII (the body
    is JSON with `ensure_ascii`, where an em dash costs six bytes)."""
    out = "".join(_ASCII.get(c, c) for c in str(text or ""))
    return unicodedata.normalize("NFKD", out).encode("ascii", "ignore").decode()


def _sentences(text: str) -> list[str]:
    return [x.strip() for x in _SENTENCE.split(" ".join(str(text or "").split())) if x.strip()]


def _clean(text: Any) -> str:
    """`diagnostics.scrub`, ASCII, and every sentence naming Validation, the holdout, out-of-sample results or 2025 dropped
    (the D2a words in `_SAFE` excepted)."""
    kept = [x for x in _sentences(to_ascii(diagnostics.scrub(text))) if not _VAL.search(_SAFE.sub(" ", x))]
    return " ".join(kept)


def lesson_view(text: Any) -> str:
    """A graveyard lesson as a model may read it (the digest, the architect's 20 newest rows, the lessons a new family is
    born with): `diagnostics.scrub`, then every sentence that names Validation (beyond D2a's met, not met and k of 8
    checks), the holdout, out-of-sample results or 2025 dropped. Train figures stay."""
    return _clean(text)


def _num(raw: Any) -> float | None:
    try:
        x = float(str(raw).strip())
    except (TypeError, ValueError):
        return None
    return x if x == x and abs(x) != float("inf") else None


def val_word(raw: Any) -> str:
    """The D2a view of a lesson's "best validation: ..." as the digest prints it: MET, no k/8, no, or never."""
    text = str(raw or "").lower()
    if not text or "never" in text:
        return "never"
    met = ("line met" in text and "not met" not in text) or ("met the validation line" in text and "did not" not in text)
    if met:
        return "MET"
    counted = re.search(r"\((\d+) of (\d+) checks", text)
    return f"no {counted.group(1)}/{counted.group(2)}" if counted else "no"


def tag_of(row: Mapping[str, Any], family: Mapping[str, Any] | None) -> str:
    """A row's tag, from its family's retirement reason (the lesson's own when the family is gone)."""
    fid = str(row.get("family") or "")
    lesson = str(row.get("lesson") or "")
    reason = str((family or {}).get("retire_reason") or (_HEAD.sub("", lesson) if not family else ""))
    if fid.startswith("op-"):
        return "OPERATOR"
    if IDLE_MARK in reason or IDLE_MARK in lesson:
        return "IDLE"
    if reason.startswith("the diagnostician"):
        return "DIAGNOSED"
    if "trial-adjusted" in reason:
        return "TRIALS"
    if reason.startswith("no validation improvement"):
        return "STALL"
    if reason.lower().startswith("operator"):
        return "OPERATOR-RETIRED"
    return "REFUTED"


def parse_lesson(row: Mapping[str, Any], family: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """A graveyard row as the digest reads it: `{id, at, structure, roots, lineage, tag, mech, verdict, notes, stats, val,
    scored}`. The lesson's head, its "Tried ..." sentence (parsed into `stats`) and the idle rule's boilerplate come out;
    notes lose the researchers' repeated hold prefixes and repeats; sentences with a verdict (refuted, do not re-propose,
    no edge, fails, drift ...) come first. Everything passes `lesson_view`'s filter."""
    fid = str(row.get("family") or "")
    op = fid.startswith("op-")
    text = to_ascii(diagnostics.scrub(row.get("lesson")))
    notes_raw = ""
    if not op:
        text = _HEAD.sub("", text, count=1)
        if "Last notes:" in text:
            text, _, notes_raw = text.partition("Last notes:")
    stats = None
    found = _STATS.search(text) if not op else None
    if found:
        stats = {"versions": found.group(1), "trials": found.group(2), "train": found.group(3).strip(), "val": found.group(4).strip()}
        text = text[:found.start()] + " " + text[found.end():]
    text = _IDLE.sub(" ", text)
    ordered = [x for x in _sentences(_clean(text)) if not _RULE.match(x)]
    verdict = " ".join([x for x in ordered if _KEY.search(x)] + [x for x in ordered if not _KEY.search(x)])
    notes, seen = [], set()
    for raw in reversed(notes_raw.split(" | ")):  # the newest note first
        note = _clean(_HOLD.sub("", raw.strip()).strip())
        key = note[:60].lower()
        if note and note.strip("-. ") and key not in seen:
            seen.add(key)
            notes.append(note)
    notes = [n for n in notes if _KEY.search(n)] + [n for n in notes if not _KEY.search(n)]  # a verdict first
    roots = row.get("roots")
    if isinstance(roots, str):
        try:
            roots = json.loads(roots)
        except ValueError:
            roots = [roots]
    train = _num(stats["train"]) if stats else None
    val = val_word(stats["val"]) if stats else None
    return {"id": fid, "at": str(row.get("at") or ""), "structure": to_ascii(row.get("structure"))[:40],
            "roots": [to_ascii(r) for r in (roots or [])][:6], "lineage": str((family or {}).get("lineage") or fid),
            "tag": tag_of(row, family), "mech": _clean(row.get("mechanism")), "verdict": verdict, "notes": notes,
            "stats": stats, "train": train, "val": val,
            "scored": train is not None or val not in (None, "never")}


def _cut(text: str, n: int) -> str:
    text = " ".join(str(text or "").split())
    if n <= 0:
        return ""
    if len(text) <= n:
        return text
    part = text[:n]
    k = max(part.rfind(". "), part.rfind("; "))
    return part[:k + 1] if k > n * 0.6 else part.rstrip() + "~"


def _stat(p: Mapping[str, Any]) -> str:
    st = p.get("stats")
    if not st:
        return ""
    train = "None" if p.get("train") is None else f"{round(float(p['train']), 4):g}"
    return f" v{st['versions']}/{st['trials']}t train {train} val {p.get('val')}"


def _label(p: Mapping[str, Any]) -> str:
    return f"{p['id']} [{p['structure']} {','.join(p['roots'])}] {p['tag']}{_stat(p)}"


def _idle_untested(p: Mapping[str, Any]) -> bool:
    return p["tag"] == "IDLE" and p.get("train") is None


def _kept_at_3(p: Mapping[str, Any]) -> bool:
    return p["tag"] in ("OPERATOR", "REFUTED", "DIAGNOSED") or bool(p.get("scored"))


def _full(p: Mapping[str, Any], scale: float) -> str:
    tier = "VAL" if p["tag"] != "OPERATOR" and p.get("scored") else p["tag"]
    m, l = (int(x * scale) for x in TIER_CHARS[tier])
    lesson = p["verdict"]
    if p["notes"] and len(lesson) < l * 0.7:
        lesson = (lesson + " Notes: " + p["notes"][0]).strip()
    out = f"{_label(p)}\n M: {_cut(p['mech'], m)}\n"
    return out + (f" L: {_cut(lesson, l)}\n" if lesson else "")


def _one_line(p: Mapping[str, Any], scale: float) -> str:
    return f"{_label(p)}: {_cut(p['mech'], min(150, int(110 * scale) + 40))}\n"


def _follower(p: Mapping[str, Any], scale: float, level: int) -> str:
    if level >= 3:
        return f" + {_label(p)}\n"
    said = p["verdict"] or (p["notes"][0] if p["notes"] else "")
    said = _cut(said, int(FOLLOWER_CHARS * scale))
    return f" + {_label(p)}" + (f": {said}\n" if said else "\n")


def _lists(rows: Sequence[Mapping[str, Any]], *, idle_only: bool) -> str:
    groups: dict[tuple[int, str], list[str]] = {}
    for p in rows:
        groups.setdefault((TAGS.index(p["tag"]), p["structure"]), []).append(p["id"])
    out = []
    for (tag, structure), ids in sorted(groups.items()):
        name = "IDLE, never an eligible Train version" if idle_only else TAGS[tag]
        out.append(f"{name}, {structure} ({len(ids)}): {', '.join(ids)}\n")
    return "".join(out)


def _render(rows: Sequence[Mapping[str, Any]], level: int, scale: float) -> str:
    """The sealed digest's body at a ladder level (`LEVELS`) and scale: lineages grouped, ordered by their first row's
    (at, id), each oldest first; rows shortened to id lists after them. Deterministic for the same rows."""
    if level >= 4:
        return _lists(rows, idle_only=False)
    listed = [p for p in rows if (level >= 2 and _idle_untested(p)) or (level >= 3 and not _kept_at_3(p))]
    gone = {p["id"] for p in listed}
    lineages: dict[str, list[Mapping[str, Any]]] = {}
    for p in rows:
        if p["id"] not in gone:
            lineages.setdefault(p["lineage"], []).append(p)
    out = []
    for group in sorted(lineages.values(), key=lambda g: (g[0]["at"], g[0]["id"])):
        head = group[0]
        out.append(_one_line(head, scale) if level >= 1 and _idle_untested(head) else _full(head, scale))
        out.extend(_follower(p, scale, level) for p in group[1:])
    if level == 2:
        out.append(_lists(listed, idle_only=True))
    elif level >= 3:
        out.append(_lists(listed, idle_only=False))
    return "".join(out)


def _render_tail(rows: Sequence[Mapping[str, Any]], level: int, scale: float) -> str:
    """Rows buried since the seal, in (at, id) order, each on its own at the seal's level and scale."""
    out = []
    for p in rows:
        if level >= 4 or (level >= 3 and not _kept_at_3(p)):
            out.append(f"{_label(p)}\n")
        elif level >= 1 and _idle_untested(p):
            out.append(_one_line(p, scale))
        else:
            out.append(_full(p, scale))
    return "".join(out)


def fit(rows: Sequence[Mapping[str, Any]], budget: int) -> tuple[int, float, str]:
    """(level, scale, body): the first ladder level where some scale of at least GOOD_SCALE fits `budget` characters (the
    largest such scale, to 3 places, up to MAX_SCALE); else the last level at whatever scale fits; else every row as id
    lists (level 4), cut with a stated count only if even those overflow."""

    def search(level: int, lo: float, hi: float) -> tuple[float, str] | None:
        text = _render(rows, level, lo)
        if len(text) > budget:
            return None
        best = (lo, text)
        for _ in range(12):
            mid = round((lo + hi) / 2, 3)
            if mid <= best[0] or mid >= hi:
                break
            text = _render(rows, level, mid)
            if len(text) <= budget:
                best, lo = (mid, text), mid
            else:
                hi = mid
        top = _render(rows, level, hi)
        return (hi, top) if len(top) <= budget else best

    for level in LEVELS:
        found = search(level, GOOD_SCALE, MAX_SCALE)
        if found:
            return level, found[0], found[1]
    found = search(LEVELS[-1], MIN_SCALE, GOOD_SCALE)
    if found:
        return LEVELS[-1], found[0], found[1]
    text = _render(rows, 4, MIN_SCALE)
    if len(text) > budget:  # only past ~8,000 rows at the default budget: never silent, the count is stated
        note = "\n... {n} more rows are not listed: raise architect.graveyard_digest_tokens.\n"
        cut = text[: max(0, budget - len(note) - 8)]
        cut = cut[: cut.rfind(", ")] if ", " in cut else ""
        named = sum(len(line.split("): ", 1)[1].split(", ")) for line in cut.split("\n") if "): " in line)
        text = cut + note.format(n=len(rows) - named)
    return 4, MIN_SCALE, text


@dataclass(frozen=True)
class Digest:
    sealed: str        # the header and the sealed rows: the one cached block
    tail: str          # rows buried since the seal ("" when none): never marked
    rows: int
    sealed_rows: int
    level: int
    scale: float
    sha: str
    resealed: str | None = None   # why this snapshot sealed the digest anew, or None


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


class GraveyardDigest:
    """The whole graveyard as the Claude route's first system blocks (the module docstring). `snapshot()` is the sealed
    digest now (resealing when it must); `blocks(ttl)` the system blocks a call sends, the sealed one marked with `ttl`."""

    def __init__(self, store: SwarmStore, settings: Mapping[str, Any], *, clock: Callable[[], float] = time.time):
        self.store = store
        self.settings = settings
        self.clock = clock
        self._memo: tuple[Any, Digest] | None = None

    @property
    def cfg(self) -> Mapping[str, Any]:
        return self.settings.get("architect", {})

    def tokens(self) -> int:
        try:
            value = int(self.cfg.get("graveyard_digest_tokens", 100000))
        except (TypeError, ValueError):
            value = 100000
        return max(5000, min(value, 300000))

    def tail_share(self) -> float:
        try:
            value = float(self.cfg.get("graveyard_digest_tail_share", 0.15))
        except (TypeError, ValueError):
            value = 0.15
        return max(0.05, min(value if value == value else 0.15, 0.5))

    def chars_per_token(self) -> float:
        value = _num(self.store.get(CPT_KEY))
        return max(CPT_BOUNDS[0], min(value, CPT_BOUNDS[1])) if value is not None else DEFAULT_CPT

    def budget_chars(self) -> int:
        """The digest's characters: `graveyard_digest_tokens` x the measured characters per token, at most MAX_DIGEST_BYTES."""
        return min(int(self.tokens() * self.chars_per_token()), MAX_DIGEST_BYTES)

    def rows(self) -> list[dict[str, Any]]:
        """Every graveyard row parsed (`parse_lesson`), in (at, id) order whatever order the store returns them in."""
        families = {f["id"]: f for f in self.store._all("SELECT id, lineage, retire_reason FROM families")}
        raw = self.store.graveyard(limit=10 ** 9)
        return sorted((parse_lesson(r, families.get(r["family"])) for r in raw), key=lambda p: (p["at"], p["id"]))

    @staticmethod
    def header(rows: int, at: str) -> str:
        return DIGEST_HEADER.format(rows=rows, at=at)

    def _seal_valid(self, seal: Any) -> bool:
        return (isinstance(seal, dict) and seal.get("format") == DIGEST_FORMAT and seal.get("tokens") == self.tokens()
                and seal.get("tail_share") == self.tail_share() and isinstance(seal.get("through"), list)
                and len(seal["through"]) == 2 and isinstance(seal.get("sha"), str) and seal.get("level") in (*LEVELS, 4))

    def reseal(self, rows: Sequence[Mapping[str, Any]], why: str) -> tuple[dict[str, Any], str]:
        """Seal every row now: the ladder level and scale that fit the budget less the tail's share (`fit`). Returns the
        seal (kv SEAL_KEY: never the text, which is rendered again from the rows) and the sealed text."""
        budget = self.budget_chars()
        at = iso(self.clock())
        head = self.header(len(rows), at)
        room = int(budget * (1 - self.tail_share())) - len(head)
        level, scale, body = fit(rows, room)
        text = head + body
        last = rows[-1] if rows else {"at": "", "id": ""}
        seal = {"format": DIGEST_FORMAT, "tokens": self.tokens(), "tail_share": self.tail_share(), "budget": budget,
                "room": room, "cpt": self.chars_per_token(), "through": [last["at"], last["id"]], "level": level,
                "scale": scale, "rows": len(rows), "chars": len(text), "sha": _sha(text), "at": at, "why": why}
        self.store.put(SEAL_KEY, seal)
        return seal, text

    def _sealed_text(self, rows: Sequence[Mapping[str, Any]], seal: Mapping[str, Any]) -> str:
        level = int(seal["level"])
        body = fit(rows, int(seal.get("room") or 0))[2] if level == 4 else _render(rows, level, float(seal["scale"]))
        return self.header(len(rows), str(seal["at"])) + body

    def snapshot(self) -> Digest:
        """The digest now: the sealed block (byte-identical until the next reseal) and the tail. It reseals when there is no
        seal, the format or the budget setting changed, the sealed rows no longer render to the sealed bytes (a row was
        buried again or rewritten), or the tail passed its share. The same graveyard gives the same snapshot (memoized),
        so one pass's strategist and architect calls send identical bytes."""
        seal = self.store.get(SEAL_KEY)
        newest = self.store._one("SELECT COUNT(*) AS n, MAX(at || ' ' || family) AS last FROM graveyard") or {}
        key = (newest.get("n"), newest.get("last"), self.tokens(), self.tail_share(),
               json.dumps(seal, sort_keys=True, default=str))
        if self._memo is not None and self._memo[0] == key:
            return replace(self._memo[1], resealed=None)  # the same bytes: sealed before, not by this call
        rows = self.rows()
        why = None
        text, tail, sealed = "", "", rows
        if not self._seal_valid(seal):
            why = "no seal" if not seal else "the format or the budget changed"
        else:
            through = tuple(seal["through"])
            sealed = [p for p in rows if (p["at"], p["id"]) <= through]
            later = [p for p in rows if (p["at"], p["id"]) > through]
            text = self._sealed_text(sealed, seal)
            if _sha(text) != seal["sha"]:
                why = "the sealed rows changed"
            else:
                tail = (TAIL_HEADER.format(rows=len(later), total=len(rows))
                        + _render_tail(later, int(seal["level"]), float(seal["scale"]))) if later else ""
                if len(tail) > self.tail_share() * float(seal.get("budget") or self.budget_chars()):
                    why = "the tail passed its share"
        if why is not None:
            seal, text = self.reseal(rows, why)
            sealed, tail = rows, ""
        digest = Digest(sealed=text, tail=tail, rows=len(rows), sealed_rows=len(sealed), level=int(seal["level"]),
                        scale=float(seal["scale"]), sha=str(seal["sha"]), resealed=why)
        # The memo is keyed on the seal as it is stored after this snapshot, so the next call finds it.
        key = key[:4] + (json.dumps(self.store.get(SEAL_KEY), sort_keys=True, default=str),)
        self._memo = (key, digest)
        return digest

    def blocks(self, ttl: str | None, digest: Digest | None = None) -> list[dict[str, Any]]:
        """The system blocks a digest-route call puts first: the sealed block (marked `ttl`: None, "5m" or "1h"), then the
        tail, never marked (it changes with every burial). [] when the graveyard is empty."""
        digest = digest or self.snapshot()
        if not digest.rows:
            return []
        out: list[dict[str, Any]] = [{"text": digest.sealed, "cache": ttl if ttl in ("5m", "1h") else None}]
        if digest.tail:
            out.append({"text": digest.tail, "cache": None})
        return out

    def expected_read(self, sha: str, ttl: str | None, began: float) -> bool:
        """Should a call marked `ttl` for these sealed bytes read them from the cache: the last marked call sent the same
        bytes and started within the entry's life (the TTL runs from a request's start; 270 s of the five minutes, 55 of
        the sixty)? A miss then is the silent-invalidator alarm (`cache_miss` in the event)."""
        last = self.store.get(LAST_KEY)
        if ttl is None or not isinstance(last, dict) or last.get("sha") != sha or last.get("ttl") not in ("5m", "1h"):
            return False
        life = 3300.0 if last["ttl"] == "1h" else 270.0
        return 0.0 <= float(began) - float(last.get("at") or 0.0) < life

    def record_call(self, sha: str, ttl: str | None, began: float) -> None:
        """A Claude call that marked the sealed block wrote or refreshed its entry (only a marked block is looked up)."""
        if ttl in ("5m", "1h"):
            self.store.put(LAST_KEY, {"sha": sha, "ttl": ttl, "at": float(began)})

    def calibrate(self, usage: Mapping[str, Any] | None, chars: int) -> float | None:
        """Learn the characters per token from a Claude call's usage (every input token: uncached, read and written) and
        the characters it sent; an average that moves a third of the way each call, within CPT_BOUNDS. Used at the next
        reseal only, so it never moves the sealed bytes between reseals."""
        usage = usage or {}
        total = 0
        for name in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"):
            value = usage.get(name)
            total += int(value) if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 0
        if total <= 0 or chars <= 0:
            return None
        measured = max(CPT_BOUNDS[0], min(chars / total, CPT_BOUNDS[1]))
        old = _num(self.store.get(CPT_KEY))
        value = round(measured if old is None else old + (measured - old) / 3, 4)
        self.store.put(CPT_KEY, value)
        return value


def locked_text(settings: Mapping[str, Any]) -> str:
    """The operator's locked preamble (`architect.agenda_locked`), as the agenda carries it: stripped, at most
    AGENDA_LOCKED_MAX characters. No code path writes it: it is read from the settings on every pass."""
    return str((settings.get("architect", {}) or {}).get("agenda_locked") or "").strip()[:AGENDA_LOCKED_MAX]


def compose(locked: str, section: str, at: Any) -> str:
    """The agenda the architect reads: the locked preamble byte for byte, then the strategist's section under its own
    header. The section is only ever appended, and its cap (SECTION_MAX) never touches the locked text."""
    when = at if isinstance(at, str) else (iso(float(at)) if isinstance(at, (int, float)) and not isinstance(at, bool) else "?")
    return f"{locked}\n\n{WHERE_HEADER.format(at=when)}\n{str(section or '').strip()[:SECTION_MAX]}"


FULL_GRAVEYARD_RULE = """

THE FULL GRAVEYARD. The system prompt's first blocks hold THE GRAVEYARD: every retired family and every operator lesson.
Check every proposal against the full graveyard, not only the newest rows. For each family add "differs_from": [{"row":
"<graveyard id>", "how": "<the mechanism-level difference>"}], naming the one to three closest rows and how your
mechanism differs from each. A re-tune, a new root, a new structure or a new horizon of a refuted mechanism is not a
difference; name its parent instead. If no row is close, say [] and why in the family's "sketch"."""

GRAVEYARD_POINTER = "THE GRAVEYARD: every row is in the system prompt's graveyard blocks above; check every proposal against it."


class Architect:
    def __init__(self, store: SwarmStore, router: Any, settings: Mapping[str, Any], *, clock: Callable[[], float] = time.time,
                 digest: GraveyardDigest | None = None):
        self.store = store
        self.router = router
        self.settings = settings
        self.clock = clock
        self.digest = digest

    @property
    def cfg(self) -> Mapping[str, Any]:
        return self.settings.get("architect", {})

    def refilling(self) -> bool:
        """Fewer families live than the swarm starts with."""
        return len(self.store.families(alive=True)) < int(self.settings.get("population", {}).get("start", 48))

    def due(self) -> bool:
        every = float(self.cfg.get("refill_seconds", 3600)) if self.refilling() else float(self.cfg.get("every_seconds", 14400))
        return self.clock() - float(self.store.get("architect_at", 0.0) or 0.0) >= every

    def want(self) -> int:
        """How many families this pass may admit: the gap to the start while refilling (at most `max_refill`), else
        `max_new`; never past the ceiling."""
        pop = self.settings.get("population", {})
        alive = len(self.store.families(alive=True))
        start, ceiling = int(pop.get("start", 48)), int(pop.get("ceiling", 96))
        n = min(int(self.cfg.get("max_refill", 12)), start - alive) if alive < start else int(self.cfg.get("max_new", 6))
        return max(0, min(n, ceiling - alive))

    def _gaps_by_root(self) -> dict[str, list[str]]:
        roots = list(self.settings.get("gym", {}).get("roots", ["SPY", "QQQ", "IWM", "XSP", "SPXW"]))
        covered = {(r, f["structure"]) for f in self.store.families(alive=True) for r in f["roots"]}
        out = {}
        for root in roots:
            out[root] = []
            for structure in STRUCTURES:
                if root in ("XSP", "SPXW") and structure in ("calendar", "diagonal"):
                    continue
                if (root, structure) not in covered:
                    out[root].append(structure)
        return out

    def gaps(self) -> list[str]:
        return [f"{structure} on {root}" for root, structures in self._gaps_by_root().items() for structure in structures]

    def coverage(self) -> dict[str, dict[str, int]]:
        """Research effort by supported type, including retired ideas; never a claim about returns or fills.

        Count each family's own evaluations once. Inherited lineage counts remain the gate's evidence adjustment,
        not extra work to add again to this coverage table. Families outside this image's root list are excluded.
        """
        roots = set(self.settings.get("gym", {}).get("roots", ["SPY", "QQQ", "IWM", "XSP", "SPXW"]))
        rows = {kind: {"active_families": 0, "retired_families": 0, "trials": 0, "validated_families": 0}
                for kind in STRUCTURES}
        for family in self.store.families():
            if not roots.intersection(family["roots"]):
                continue
            row = rows[family["structure"]]
            row["retired_families" if family["retired_at"] else "active_families"] += 1
            row["trials"] += int(family.get("trials") or 0)
            row["validated_families"] += int(int(family.get("validations") or 0) > 0)
        return rows

    def agenda(self) -> tuple[str, str]:
        """(its title, the agenda): the operator's locked preamble then the strategist's latest accepted WHERE TO LOOK
        section (`compose`) when both exist; else `architect.agenda` exactly as before ("" when there is none)."""
        locked = locked_text(self.settings)
        section = self.store.get(AGENDA_KEY)
        if locked and isinstance(section, dict) and str(section.get("text") or "").strip():
            return COMPOSED_AGENDA_TITLE, compose(locked, str(section["text"]), section.get("at"))
        return LEGACY_AGENDA_TITLE, str(self.cfg.get("agenda") or "").strip()[:4000]

    def use_digest(self) -> bool:
        """The whole graveyard on the Claude route: `architect.full_graveyard` and Claude serves the architect."""
        return (self.digest is not None and self.cfg.get("full_graveyard", True) is True
                and bool(getattr(self.router, "claude_enabled", lambda role: False)("architect")))

    def digest_ttl(self, paired: bool) -> str | None:
        """The sealed digest's cache marker for this call (`architect.graveyard_digest_ttl`): "1h" on every call once the
        gateway admits it (`claude.cache_1h`); "5m" only right after the strategist's call wrote it (`paired`: a lone call
        every twenty minutes would find its five-minute entry gone and pay the write premium for nothing); "off" none."""
        mode = str(self.cfg.get("graveyard_digest_ttl") or "5m")
        if mode == "off":
            return None
        if mode == "1h" and (self.settings.get("claude") or {}).get("cache_1h") is True:
            return "1h"
        return "5m" if paired else None

    def graveyard_ids(self) -> set[str]:
        return {r["family"] for r in self.store._all("SELECT family FROM graveyard")}

    @staticmethod
    def differs(row: Any, known: set[str]) -> list[dict[str, str]]:
        """The graveyard rows a proposal says it differs from, and how: only rows that exist, at most three."""
        items = row.get("differs_from") if isinstance(row, dict) else None
        out = []
        for item in items if isinstance(items, list) else []:
            if isinstance(item, dict) and str(item.get("row") or "") in known:
                out.append({"row": str(item["row"]), "how": " ".join(str(item.get("how") or "").split())[:300]})
        return out[:3]

    def prompt(self, *, full_graveyard: bool = False) -> str:
        """The request. `full_graveyard` (the Claude route with the digest): THE GRAVEYARD is a pointer to the digest in
        the system prompt; else the 20 newest rows, each lesson as `lesson_view` gives it."""
        alive = self.store.families(alive=True)
        living_ids = {f["id"] for f in alive}
        board = (self.store.get("leaderboard") or {}).get("board") or []
        # Of Validation the architect sees what a researcher sees (D2a): the line met or not and the checks passed.
        lines = {f["id"]: (f.get("state") or {}).get("validation_line") for f in alive}
        living = [{"family": r["family"], "band": r["band"], "structure": r["structure"], "roots": r["roots"],
                   "validation": diagnostics.validation_view({}, lines.get(r["family"])) if lines.get(r["family"]) else None,
                   "share": r.get("share")} for r in board if r["family"] in living_ids][:60]
        if not living:
            living = [{"family": f["id"], "structure": f["structure"], "roots": f["roots"], "mechanism": f["mechanism"][:160]}
                      for f in alive][:60]
        if full_graveyard:
            graveyard = GRAVEYARD_POINTER
        else:
            graves = [{"family": g["family"], "structure": g["structure"], "roots": g["roots"], "lesson": lesson_view(g["lesson"])[:400]}
                      for g in self.store.graveyard(limit=20)]
            graveyard = f"THE GRAVEYARD:\n{json.dumps(graves)}"
        want = self.want()
        roots = ", ".join(self.settings.get("gym", {}).get("roots", ["SPY", "QQQ", "IWM", "XSP", "SPXW"]))
        gaps = json.dumps(self._gaps_by_root(), separators=(",", ":"))
        coverage = json.dumps(self.coverage(), separators=(",", ":"))
        # During a burst refill, ask for the whole bounded gap. Asking for "3 to 12" repeatedly underfilled a
        # population losing families faster than three births per hour. The admission and spending caps still bind.
        number = str(want) if self.refilling() and want > 0 else f"{min(max(int(self.cfg.get('min_new', 3)), 1), max(want, 1))} to {max(want, 1)}"
        title, agenda = self.agenda()
        return (f"Propose {number} new families, on these roots only (the Gym "
                f"holds their data): {roots}.\n\nLIVING FAMILIES "
                f"(leaderboard):\n{json.dumps(living)}\n\n{graveyard}\n\n"
                f"RESEARCH COVERAGE (effort, not profitability; validated means evaluated, not passed):\n{coverage}\n\n"
                f"GAPS (uncovered structure types by root; [] means all covered):\n{gaps}"
                + (f"\n\n{title}:\n{agenda}" if agenda else ""))

    def admit(self, rows: Any, *, digest: bool = False) -> list[str]:
        """Birth the well-formed proposals (the module docstring). Each birth's `differs_from` rows (the digest route's
        answer) go into its notebook; with `digest` and `architect.require_differs`, a proposal that names no real
        graveyard row is refused."""
        cap = self.want()
        known = self.graveyard_ids()
        strict = digest and self.cfg.get("require_differs") is True
        living = {(f["mechanism"].lower()[:80], tuple(f["roots"]), f["structure"]) for f in self.store.families(alive=True)}
        allowed_roots = set(self.settings.get("gym", {}).get("roots", ["SPY", "QQQ", "IWM", "XSP", "SPXW"]))
        born = []
        for row in rows if isinstance(rows, list) else []:
            if len(born) >= cap or not isinstance(row, dict):
                break
            structure = row.get("structure")
            named = [row["roots"]] if isinstance(row.get("roots"), str) else (row.get("roots") or [])
            roots = list(dict.fromkeys(str(r).upper() for r in named if str(r).upper() in allowed_roots))[:MAX_ROOTS]
            dte = row.get("dte") if isinstance(row.get("dte"), list) and len(row.get("dte")) == 2 else [0, 5]
            mechanism = " ".join(str(row.get("mechanism") or "").split())[:600]
            if structure not in STRUCTURES or not roots or len(mechanism) < 30:
                continue
            if any(r in ("XSP", "SPXW") for r in roots) and structure in ("calendar", "diagonal"):
                continue
            if (mechanism.lower()[:80], tuple(roots), structure) in living:
                continue
            cited = self.differs(row, known)
            if strict and not cited:
                continue
            try:
                lo, hi = sorted((max(0, min(45, int(dte[0]))), max(0, min(45, int(dte[1])))))
            except (TypeError, ValueError):
                lo, hi = 0, 5
            # Three distinct lessons: many open with the same wording (the idle rule's), and 300 characters is all a
            # family is born with, so a repeat would only crowd out another lesson. Each as `lesson_view` gives it (D2a).
            lessons = list(dict.fromkeys(lesson_view(g["lesson"])[:300]
                                         for g in self.store.graveyard(f"{structure} {' '.join(roots)} {mechanism}", limit=12)))[:3]
            spec = {"id": row.get("slug") or mechanism, "mechanism": mechanism, "structure": structure, "roots": roots, "dte": [lo, hi],
                    "rejection": str(row.get("rejection") or "")[:400], "sketch": str(row.get("sketch") or "")[:800],
                    "lessons": lessons}
            # A slice a retired family searched (same structure and roots): the same idea again continues its lineage
            # (its trials and holdout looks, so re-proposing never resets the count its evidence is deflated by); another
            # idea is a new lineage that still counts the slice's trials (`prior_lineage`) but not its look ration.
            dead = [f for f in self.store.families(alive=False) if f["structure"] == structure and sorted(f["roots"]) == sorted(roots)]
            same = [f for f in dead if f["id"] in (row.get("parent"), row.get("slug")) or same_idea(f["mechanism"], mechanism)]
            declared = self.store.family(str(row.get("parent"))) if row.get("parent") else None
            parent = declared["id"] if declared and declared["structure"] == structure else (same[-1]["id"] if same else None)
            prior = dead[-1]["lineage"] if dead and not parent else None
            with self.store.lock:
                if len(self.store.families(alive=True)) >= int(self.settings.get("population", {}).get("ceiling", 96)):
                    break
                fam = self.store.add_family(spec, origin="architect", parent=parent, prior_lineage=prior)
                living.add((mechanism.lower()[:80], tuple(roots), structure))
            if spec["sketch"]:
                self.store.note(fam["id"], f"The architect's sketch: {spec['sketch']}")
            for item in cited:
                self.store.note(fam["id"], f"The architect: differs from {item['row']}: {item['how']}")
            self.store.event("swarm.born", fam["id"], {"parent": parent, "mechanism": mechanism, "structure": structure,
                                                        "roots": roots, "origin": "architect"})
            born.append(fam["id"])
        return born

    def _digest_call(self, system: str, paired: bool) -> tuple[dict[str, Any], dict[str, Any] | None]:
        """The Claude-only arguments of a digest-route call (`claude_prefix`, `claude_system`, `claude_user`) and what the
        pass's event says of the digest; ({}, None) off the digest route. A digest that cannot be built is reported and the
        call goes without it (the 20 newest rows, as before)."""
        if not self.use_digest():
            return {}, None
        try:
            snap = self.digest.snapshot()  # type: ignore[union-attr]
            ttl = self.digest_ttl(paired)
            blocks = self.digest.blocks(ttl, snap)  # type: ignore[union-attr]
        except Exception as exc:  # noqa: BLE001 - the pass goes on with the 20 newest rows
            return {}, {"error": f"{type(exc).__name__}: {str(exc)[:200]}"}
        if not blocks:
            return {}, None
        info = {"rows": snap.rows, "sealed_rows": snap.sealed_rows, "level": snap.level, "scale": snap.scale, "sha": snap.sha,
                "ttl": ttl, "ttl_mode": str(self.cfg.get("graveyard_digest_ttl") or "5m"), "paired": paired,
                "chars": len(snap.sealed) + len(snap.tail), "resealed": snap.resealed}
        return {"claude_prefix": blocks, "claude_system": system + FULL_GRAVEYARD_RULE,
                "claude_user": self.prompt(full_graveyard=True)}, info

    def run(self, *, paired: bool = False) -> dict[str, Any]:
        """One pass. `paired`: the strategist's Claude call just sent (and marked) the same sealed digest, so this call
        marks it too and reads it from the cache (`digest_ttl`)."""
        began = self.clock()
        self.store.put("architect_at", began)
        room = int(self.settings.get("population", {}).get("ceiling", 96)) - len(self.store.families(alive=True))
        if room <= 0:
            out = {"born": [], "why": "the population is at its ceiling"}
            self.store.event("swarm.architect", None, out)
            return out
        info: dict[str, Any] | None = None
        try:
            # SYSTEM itself while Train is 2022-2024; else the running swarm's span (its store's migrated objective)
            system = settings_mod.train_span_text(SYSTEM, settings_mod.objective_span(self.store.get("train_objective")))
            extra, info = self._digest_call(system, paired)
            answer = self.router.ask(role="architect", system=system, user=self.prompt(), family=None,
                                     key=f"swarm:architect:{int(began)}", openai_model=self.cfg.get("openai_model"),
                                     sail_profile=str(self.cfg.get("sail_profile", "k3_balanced")),
                                     max_output=int(self.cfg.get("max_output_tokens", 12000)), effort="high", need_usd=2.0,
                                     claude=True, rotate=True, **extra)  # Claude first; Astra every other pass if openai_model
        except Exception as exc:  # noqa: BLE001
            out = {"born": [], "error": str(exc)[:300]}
            if info is not None:
                out["digest"] = info
            self.store.event("swarm.architect", None, out)
            return out
        rows = (answer.get("json") or {}).get("families")
        on_digest = bool(extra) and answer.get("route") == "claude"
        born = self.admit(rows, digest=on_digest)
        out = {"born": born, "proposed": len(rows) if isinstance(rows, list) else 0, "route": answer.get("route"),
               "model": answer.get("model"), "cost_usd": answer.get("cost_usd"), "seconds": round(self.clock() - began, 1)}
        if answer.get("route") == "claude":
            usage = answer.get("usage") or {}
            out["usage"] = {k: usage[k] for k in USAGE_KEYS if k in usage}
        if info is not None:
            out["digest"] = {**info, "used": on_digest}
        if on_digest and self.digest is not None:
            usage = answer.get("usage") or {}
            if self.digest.expected_read(info["sha"], info["ttl"], began) and not usage.get("cache_read_input_tokens"):
                out["digest"]["cache_miss"] = True  # the silent invalidator's alarm: the same sealed bytes were not read
            self.digest.record_call(info["sha"], info["ttl"], began)
            sent = sum(len(b["text"]) for b in extra["claude_prefix"]) + len(extra["claude_system"]) + len(extra["claude_user"])
            self.digest.calibrate(usage, sent)
            known = self.graveyard_ids()
            out["cited"] = sum(1 for r in rows if self.differs(r, known)) if isinstance(rows, list) else 0
        self.store.event("swarm.architect", None, out)
        return out


__all__ = ["Architect", "SYSTEM", "GraveyardDigest", "Digest", "lesson_view", "parse_lesson", "tag_of", "compose",
           "locked_text", "fit", "AGENDA_KEY", "SEAL_KEY", "CPT_KEY", "LAST_KEY", "DIGEST_HEADER", "FULL_GRAVEYARD_RULE",
           "GRAVEYARD_POINTER", "SECTION_MAX", "AGENDA_LOCKED_MAX", "MAX_DIGEST_BYTES", "COMPOSED_AGENDA_TITLE",
           "LEGACY_AGENDA_TITLE", "USAGE_KEYS"]
