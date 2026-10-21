"""R3: BIRTHS, THE SWARM'S GENERATOR (goal-2026-10-19/R3-SPEC.md; the owner's goal V2 item 2: "Births come from your
architect agents and from you, using outcome-free facts, rationed by an expected-false-pass budget you state").

PREREG-EVL-1/2/3 are hand births (the captain's). R3 makes births continuous and cheap, with the judges untouched: a
birth is DATA, never code. It plugs into the lane through one loader (league/events/programs.py `load_births`, behind
league/ci.py's wall): each registered birth becomes a Program row with its own registration time, PREREG-EVL-3's
learning band, screen and minimums, AFTER every PREREG program, so the lane decides it, the screen judges it
(PREREG-EVL-3's looks: events counted, alpha 0.018, >= 40 issuers and >= 8 session blocks), the bands move it and the
House's event book trades it at learning size like any version 2 program. No PREREG program's selection, judge or
constant moves (league/tests/test_events_births.py holds every PREREG program's intents identical with and without
births).

THE GRAMMAR (R3-SPEC section 1, its fields and only those; `parse` refuses anything else, so a birth is never free
code). A spec is a JSON object of exactly `FIELDS`:
- `id`: "EVL-B-..." (upper-case letters, digits and dashes; never one registered, never ending "-CTRL");
- `version`: 1 (births are seatable at version 1; a change is a new birth);
- `family`: an event family the lane already reads (`FAMILIES`): ern (8-K item 2.02, open), ern-react (8-K 2.02 in the
  close window, with its reaction), 8k (8-Ks with an ITEM SET, never 2.02), ins (Form 4 cluster triggers), ins-buy
  (director or officer open-market buys >= $50,000, with value and ROLE filters), news (overnight single-symbol
  articles), news-day (the day's articles to T29), news-react (the day's articles with their reaction);
- `rule`: the selection rule, only the family's fields (`RULE_FIELDS`): `items` (the 8k family's item set: an 8-K
  qualifies when it carries one of them); `score_min` / `score_max` (thresholds on the STORED PROMPT-DOC or PROMPT-NEWS
  score, -3..3) and `guidance` (the stored PROMPT-DOC guidance, the ern and 8k families): never a new prompt;
  `react_min` / `react_max` (the reaction ratio, PREREG-EVL-1's C1 measure: the 15:29 minute's close over the last
  close before the event); `value_min` (dollars, >= the lane's own $50,000) and `roles` ("director" | "officer") for
  Form 4; `sources` and `hours` (the news windows: the article's source, and its knowable hour in New York);
- `entry`: the family's own ("open" for ern, 8k, ins, ins-buy, news; "close" for ern-react, news-day, news-react);
- `exit`: "close" (the close of session h) or "open" (a close entry's next open, PREREG-EVL-2's overnight rows); an
  open entry exits at a close;
- `hold`: h in 1..5 sessions; a SEATABLE birth holds one (the screen's blocks are one-session blocks, as every seatable
  PREREG program's; a longer hold is a record, as PREREG-EVL-1's ERN-READ-O3);
- `rank`: the ranking key when room is short: "score", "reaction", "value" or "none" (the family's own, `RANKS`);
- `seatable`: true (real money at learning size from its first event, judged by PREREG-EVL-3's screen) or false (a
  record: free, never seated, never screened).
A READ birth (a verdict threshold, a guidance filter or a score ranking) carries its CONTROL, derived from its spec
and registered with it (`control_spec`: the same rule with every verdict condition removed, a record with the id
"<id>-CTRL"): PREREG-EVL-1 section 7's "for a READ program, its mean block value exceeds its control's" holds for a
birth too (league/events/screen.py `control_of`). The canonical form (`canonical`) is the parsed spec as JSON with
sorted keys and no spaces; its sha256 (`sha`) names the birth.

THE FACTS (`Facts`): what the ARCHITECT reads, OUTCOME-FREE. Over the last `SESSIONS` (20) sessions: event counts by
family, 8-K item, form, news source and knowable hour; the stored verdict scores and guidance; which families and items
no program selects; every registered program's selection count; and a candidate rule's selection count (each run
through the lane's own `select` over the same windows). The facts NEVER read bars, marks, outcomes, looks, bands,
band_history, real_fills, the universe (its prices) or meta (the looks' details): a SQLite authorizer refuses those
tables for the whole build (`outcome_free`), so a price after an event, a return, a P&L, a look's p or a band cannot
reach the architect. Eligibility is the lane's kept result (`eligibility`: listed, operating, priced before the
session), the session's own or else the issuer's nearest. The reactions of the react families are prices after the
event: never read, so their counts are UPPER BOUNDS (every event passes the reaction) and say so.

THE VALIDATOR (`validate`, code, not a model): the grammar; a new id and sha; a minimum rate, >= `MIN_RATE` (3)
selected events a session over the last 20 sessions by selection count; no duplicate, the Jaccard of the last 20
sessions' selected events < `JACCARD_MAX` (0.8) against every registered program (records, controls and births too:
stricter than "every live program", and it reads no band) and every birth accepted before it the same night; and THE
FALSE-PASS BUDGET (R3-SPEC section 3 as the captain's A81 states it, 16:25Z Oct 21, 2026): each seatable birth adds
0.10 expected false passes (the measured zero-edge pass rate of PREREG-EVL-3's screen is at most 8.4%; 0.10 is the
stated charge, the screen's `FALSE_PASS_RATE`), at most A71's stated lifetime budget of the lane, 3.0
(league/events/screen.py `LANE_BUDGET`, PREREG-EVL-4 section 3), over every seatable version ever registered in the
lane, counted from SEATING's own sum as the report counts it (league/events/screen.py `expected_false_passes`:
PREREG-EVL-1 to -4's twelve seatable versions, 1.2, and every seatable birth once loaded; never a figure written
here), and at most `SEATABLE_A_NIGHT` (3) seatable births a night: so at most 18 seatable births before the budget is
spent. A retired program's past looks stay counted (a test that was run is never refunded). Records are free.

THE PROPOSER (`propose`): ONE gateway call a night to claude-haiku-4-5-20251001 at temperature 0 (the lane's
`/v1/claude/messages`, as the verdicts), its prompt's sha256 recorded and its answer stored like a verdict
(`birth_calls`: a night's stored answer is read again, never asked again), at most `K` specs a night, under a cost cap
of `NIGHT_USD` ($0.25) a night: the call's worst case (its input at about 3 characters a token and its max_tokens, at
Haiku 4.5's $1 and $5 a million tokens) must fit under what the night has left, or no call is made. On the House the
call is INSIDE THE LANE'S LINE (release 1019e's review): its worst case must also fit under what is left of the lane's
line today (league/events/house.py `line_left`), and its stored cost counts in that line, in the budget rule's measure
of the lane (league/ops/budget.py `lane_spend`) and in the site's bill (league/site_lane.py `verdict_usd`).

REGISTRATION (`register`): the accepted specs' canonical lines are appended to `docs/births/<night>.jsonl` on main
through the gateway's GitHub docs route (`POST /v1/github/docs`, gateway/lib/desk.mjs: that path pattern, appends of
JSON lines only, the runtime token, a size cap). The registration time is the LATER of GitHub's commit time (the
receipt's `committed_at`) and the House's receipt of the answer, stored in `births` (league/events/store.py): a birth
counts only events knowable after it. An answer that never came (a 5xx: the commit may stand) leaves the night's
lines `unknown`, posted again the next night (`reconcile`): the route answers `unchanged` with the latest commit of the
file when they stand already, whose time is later than the true one (the reading that counts fewer events).

The CAPTAIN's births go through the same validator and registration (`night(..., proposals=...)`, the CLI's
`python -m league.events --state DIR births --specs FILE`), with no model call. The House's lane runs `night` after
the night's report (league/events/house.py, `events.births` in league/config.json). Standard library only.
"""

from __future__ import annotations

import contextlib
import dataclasses
import datetime as dt
import functools
import hashlib
import json
import math
import re
import sqlite3
from typing import Any, Callable, Iterable, Mapping, Sequence

from . import calendar as C
from . import programs as P
from . import screen as SN
from . import store as S
from . import verdicts as V

GRAMMAR = 1
FIELDS = ("id", "version", "family", "rule", "entry", "exit", "hold", "rank", "seatable")
FAMILIES = ("ern", "ern-react", "8k", "ins", "ins-buy", "news", "news-day", "news-react")
#: Each family's entry, as the lane's decisions read it (league/events/run.py: the open decision's windows feed ern, 8k,
#: ins, ins-buy and news; the close decision's ern-react, news-day and news-react).
ENTRY = {"ern": "open", "8k": "open", "ins": "open", "ins-buy": "open", "news": "open",
         "ern-react": "close", "news-day": "close", "news-react": "close"}
RULE_FIELDS: dict[str, tuple[str, ...]] = {
    "ern": ("score_min", "score_max", "guidance"),
    "ern-react": ("score_min", "score_max", "react_min", "react_max"),
    "8k": ("items", "score_min", "score_max", "guidance"),
    "ins": ("value_min",),
    "ins-buy": ("value_min", "roles"),
    "news": ("score_min", "score_max", "sources", "hours"),
    "news-day": ("score_min", "score_max", "sources", "hours"),
    "news-react": ("react_min", "react_max", "sources", "hours"),
}
RANKS: dict[str, tuple[str, ...]] = {
    "ern": ("score", "none"), "ern-react": ("reaction", "score", "none"), "8k": ("score", "none"),
    "ins": ("value", "none"), "ins-buy": ("value", "none"), "news": ("score", "none"), "news-day": ("score", "none"),
    "news-react": ("reaction", "none"),
}
NEWS_FAMILIES = ("news", "news-day", "news-react")
REACT_FAMILIES = ("ern-react", "news-react")
#: The 8-K items a birth of the 8k family may name (EDGAR's list; 2.02 is the ern family's).
ITEMS_8K = ("1.01", "1.02", "1.03", "1.04", "1.05", "1.06", "2.01", "2.03", "2.04", "2.05", "2.06", "3.01", "3.02",
            "3.03", "4.01", "4.02", "5.01", "5.02", "5.03", "5.04", "5.05", "5.06", "5.07", "5.08", "6.01", "6.02",
            "6.03", "6.04", "6.05", "6.06", "6.10", "7.01", "8.01", "9.01")
#: The 8-K items whose PROMPT-DOC verdicts the lane asks (league/events/run.py `needs_verdict`, PREREG-EVL-1's 8K-READ):
#: a READ birth of the 8k family names only these, so its verdicts are stored (and waited for) before its decision.
READ_ITEMS_8K = tuple(sorted(P.OTHER_ITEMS))
SCORE_RANGE = (-3, 3)
REACT_MIN_RANGE = (1.01, 1.25)
REACT_MAX_RANGE = (0.75, 0.99)
VALUE_MAX = 10_000_000
ROLES = ("director", "officer")
SOURCE_RE = re.compile(r"[a-z0-9][a-z0-9._ -]{0,31}")
ID_RE = re.compile(r"EVL-B-[A-Z0-9]{1,12}(?:-[A-Z0-9]{1,12}){0,4}")
ID_MAX = 40
CONTROL_SUFFIX = "-CTRL"

#: THE VALIDATOR'S RULES (R3-SPEC sections 2 and 3).
SESSIONS = 20
MIN_RATE = 3
JACCARD_MAX = 0.8
#: The false-pass budget (A81), in tenths of an expected false pass (integers: no float drift): each seatable birth the
#: screen's FALSE_PASS_RATE, 1 (0.10); every seatable version ever registered at most the lane's stated lifetime budget,
#: LANE_BUDGET, 30 (3.0), read from the screen and never restated here; what is used is SEATING's own sum
#: (`budget_used_tenths`: PREREG-EVL-1 to -4's twelve, 12, before any birth); at most 3 seatable births a night.
CHARGE_TENTHS = int(round(SN.FALSE_PASS_RATE * 10))
BUDGET_TENTHS = int(round(SN.LANE_BUDGET * 10))
SEATABLE_A_NIGHT = 3

#: THE PROPOSER (R3-SPEC section 2).
MODEL = V.MODEL
TEMPERATURE = 0
MAX_TOKENS = 3000
K = 6
NIGHT_USD = 0.25
PRICE_IN = 1.0 / 1_000_000          # USD a token in: Claude Haiku 4.5
PRICE_OUT = 5.0 / 1_000_000         # USD a token out
CHARS_A_TOKEN = 3                   # the cap's worst case counts a token every 3 characters (JSON runs nearer 3.5)
WHY_MAX = 200
DOCS_ROUTE = "/v1/github/docs"
DOCS_DIR = "docs/births"
#: The births job's receipt (league/events/house.py runs it once a session night, after the report).
JOB = "births"
EPOCH = dt.datetime(2000, 1, 1, tzinfo=dt.timezone.utc)
#: What the facts may never read (R3-SPEC section 2): a price after an event, a return, a P&L, a look's p, a band.
FACTS_DENY = frozenset({"bars", "marks", "outcomes", "looks", "bands", "band_history", "real_fills", "universe", "meta"})


class SpecError(ValueError):
    """A spec the grammar refuses, with every reason."""

    def __init__(self, reasons: Sequence[str]):
        self.reasons = [str(r) for r in reasons] or ["refused"]
        super().__init__("; ".join(self.reasons))


# ----------------------------------------------------------------------------------------------------------- grammar
def _int(value: Any) -> bool:
    return type(value) is int


def _number(value: Any) -> bool:
    return type(value) in (int, float) and math.isfinite(float(value))


def parse(spec: Any) -> dict[str, Any]:
    """The spec in its normal form (lists sorted, sources lower-cased, ratios to 4 places), or SpecError with every
    reason: the GRAMMAR's fields and only those, each of its type and bounds, the family's rule fields and only those."""
    if isinstance(spec, (str, bytes, bytearray)):
        try:
            spec = json.loads(spec)
        except ValueError:
            raise SpecError(["a spec is a JSON object"]) from None
    if not isinstance(spec, Mapping):
        raise SpecError(["a spec is a JSON object"])
    why: list[str] = []
    extra = sorted(str(k) for k in spec if k not in FIELDS)
    missing = [f for f in FIELDS if f not in spec]
    if extra:
        why.append(f"fields outside the grammar: {', '.join(extra)}")
    if missing:
        why.append(f"missing fields: {', '.join(missing)}")
    if why:
        raise SpecError(why)
    out: dict[str, Any] = {}
    ident = spec["id"]
    if not isinstance(ident, str) or len(ident) > ID_MAX or not ID_RE.fullmatch(ident) or ident.endswith(CONTROL_SUFFIX):
        why.append(f"id must match EVL-B-<A-Z0-9 groups>, at most {ID_MAX} characters, never ending {CONTROL_SUFFIX}")
    out["id"] = ident
    if not _int(spec["version"]) or spec["version"] != 1:
        why.append("version must be 1 (a change is a new birth)")
    out["version"] = 1
    family = spec["family"]
    if family not in FAMILIES:
        raise SpecError(why + [f"family must be one of {', '.join(FAMILIES)}"])
    out["family"] = family
    if spec["entry"] != ENTRY[family]:
        why.append(f"the {family} family enters at the {ENTRY[family]}")
    out["entry"] = ENTRY[family]
    exit_ = spec["exit"]
    if exit_ not in ("close", "open"):
        why.append("exit must be close or open")
    elif ENTRY[family] == "open" and exit_ != "close":
        why.append("an open entry exits at a close")
    out["exit"] = exit_
    hold = spec["hold"]
    if not _int(hold) or not 1 <= hold <= 5:
        why.append("hold must be an integer 1..5")
    out["hold"] = hold
    seatable = spec["seatable"]
    if type(seatable) is not bool:
        why.append("seatable must be true or false")
    elif seatable and hold != 1:
        why.append("a seatable birth holds one session (the screen's blocks are one-session blocks); a longer hold is a "
                   "record")
    if seatable is True and spec.get("family") == "ins":
        # A89 (the captain's, release 1019e's last review): a Form 4 CLUSTER is judged over every Form 4 of the issuer in
        # its window, and real money may only read filings stored before its decision (A72); the House's book cannot
        # read a cluster that way yet, so an `ins` birth is a record (free, shadow only), never seatable.
        why.append("an ins (Form 4 cluster) birth is a record only: real money cannot read a cluster stored before its "
                   "decision (A89); register it seatable false")
    out["seatable"] = seatable
    rank = spec["rank"]
    if rank not in RANKS[family]:
        why.append(f"rank must be one of {', '.join(RANKS[family])} for the {family} family")
    out["rank"] = rank
    rule = spec["rule"]
    if not isinstance(rule, Mapping):
        raise SpecError(why + ["rule must be a JSON object"])
    allowed = RULE_FIELDS[family]
    odd = sorted(str(k) for k in rule if k not in allowed)
    if odd:
        why.append(f"rule fields outside the {family} family's ({', '.join(allowed)}): {', '.join(odd)}")
    norm: dict[str, Any] = {}
    for name in ("score_min", "score_max"):
        if name in rule:
            v = rule[name]
            if not _int(v) or not SCORE_RANGE[0] <= v <= SCORE_RANGE[1]:
                why.append(f"{name} must be an integer -3..3 (the stored verdict's score)")
            norm[name] = v
    if _int(norm.get("score_min")) and _int(norm.get("score_max")) and norm["score_min"] > norm["score_max"]:
        why.append("score_min is above score_max: the rule selects nothing")
    if "guidance" in rule:
        g = rule["guidance"]
        if not isinstance(g, list) or not g or any(x not in V.GUIDANCE for x in g) or len(set(g)) != len(g) or \
                len(g) == len(V.GUIDANCE):
            why.append(f"guidance must be a proper subset of {', '.join(V.GUIDANCE)}, without repeats")
        else:
            norm["guidance"] = sorted(g)
    if "items" in rule:
        items = rule["items"]
        if not isinstance(items, list) or not items or any(x not in ITEMS_8K for x in items) or len(set(items)) != len(items):
            why.append("items must be a list of 8-K items (EDGAR's, never 2.02: that is the ern family), without repeats")
        else:
            norm["items"] = sorted(items)
    for name, (lo, hi) in (("react_min", REACT_MIN_RANGE), ("react_max", REACT_MAX_RANGE)):
        if name in rule:
            v = rule[name]
            if not _number(v) or not lo <= float(v) <= hi or round(float(v), 4) != float(v):
                why.append(f"{name} must be a ratio in {lo}..{hi} with at most 4 decimals")
            else:
                norm[name] = round(float(v), 4)
    if "value_min" in rule:
        v = rule["value_min"]
        floor = P.INS_MIN_VALUE if family == "ins" else P.INS_BUY_MIN_VALUE
        if not _int(v) or not floor <= v <= VALUE_MAX:
            why.append(f"value_min must be whole dollars {int(floor)}..{VALUE_MAX} (the lane reads no smaller Form 4)")
        norm["value_min"] = v
    if "roles" in rule:
        if rule["roles"] not in ROLES:
            why.append("roles must be director or officer (no role filter: leave it out)")
        norm["roles"] = rule["roles"]
    if "sources" in rule:
        src = rule["sources"]
        if not isinstance(src, list) or not 1 <= len(src) <= 8 or any(not isinstance(x, str) for x in src):
            why.append("sources must be 1..8 news source names")
        else:
            low = [x.strip().lower() for x in src]
            if any(not SOURCE_RE.fullmatch(x) for x in low) or len(set(low)) != len(low):
                why.append("a source name is 1..32 of a-z, 0-9, '.', '_', '-' and spaces, without repeats")
            norm["sources"] = sorted(set(low))
    if "hours" in rule:
        hours = rule["hours"]
        if not isinstance(hours, list) or not 1 <= len(hours) <= 23 or any(not _int(h) or not 0 <= h <= 23 for h in hours) \
                or len(set(hours)) != len(hours):
            why.append("hours must be 1..23 distinct New York hours 0..23")
        else:
            norm["hours"] = sorted(hours)
    if family == "8k":
        if "items" not in rule:
            why.append("the 8k family names its item set (items)")
        elif "items" in norm and _reads(norm, rank) and not set(norm["items"]) <= set(READ_ITEMS_8K):
            why.append(f"a READ birth of the 8k family names only items whose verdicts the lane asks "
                       f"({', '.join(READ_ITEMS_8K)})")
    if family in REACT_FAMILIES and "react_min" not in rule and "react_max" not in rule:
        why.append("a react family names react_min or react_max")
    if "react_min" in norm and "react_max" in norm:
        why.append("react_min and react_max together select nothing (one is above 1, the other below)")
    if why:
        raise SpecError(why)
    out["rule"] = norm
    return out


def _reads(rule: Mapping[str, Any], rank: Any) -> bool:
    return any(k in rule for k in ("score_min", "score_max", "guidance")) or rank == "score"


def reads(spec: Mapping[str, Any]) -> bool:
    """A READ birth: it reads a stored verdict (a threshold, a guidance filter or a score ranking)."""
    return _reads(spec.get("rule") or {}, spec.get("rank"))


def canonical(spec: Any) -> str:
    """The canonical form: the parsed spec as JSON, keys sorted, no spaces, ASCII."""
    return json.dumps(parse(spec), sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha(spec: Any) -> str:
    return hashlib.sha256(canonical(spec).encode("ascii")).hexdigest()


def control_id(birth_id: str) -> str:
    return f"{birth_id}{CONTROL_SUFFIX}"


def control_spec(spec: Mapping[str, Any]) -> dict[str, Any]:
    """A READ birth's CONTROL (PREREG-EVL-1 section 7's beat-the-control rule): the same rule with every verdict
    condition removed (thresholds, guidance, a score ranking), a record with the id "<id>-CTRL". Derived, so it is
    registered with its birth, at the same time."""
    rule = {k: v for k, v in (spec.get("rule") or {}).items() if k not in ("score_min", "score_max", "guidance")}
    rank = "none" if spec.get("rank") == "score" else spec.get("rank")
    return dict(spec) | {"id": control_id(str(spec["id"])), "rule": rule, "rank": rank, "seatable": False}


@functools.lru_cache(maxsize=512)
def _spec_of(text: str) -> dict[str, Any]:
    """A Program's spec (its canonical JSON, or a control's derived JSON), parsed once."""
    data = json.loads(text)
    if str(data.get("id", "")).endswith(CONTROL_SUFFIX):
        return data
    return parse(data)


def program(spec: Mapping[str, Any], *, born_at: str) -> P.Program:
    """The Program row of a parsed spec (a birth or a derived control), registered at `born_at` (ISO UTC):
    PREREG-EVL-3's learning band, screen and limit at entry (prereg 3), its own rule (`spec`)."""
    text = json.dumps(dict(spec), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return P.Program(str(spec["id"]), int(spec["version"]), bool(spec["seatable"]), str(spec["family"]),
                     str(spec["entry"]), int(spec["hold"]), reads(spec), exit_at=str(spec["exit"]), rule="birth",
                     prereg=3, born_at=S.iso(S.parse_iso(born_at)), spec=text)


def _tables(db: Any) -> set[str]:
    return {str(r[0]) for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def registered_programs(store: Any) -> list[P.Program]:
    """Every registered birth of `store`'s `births` table as Program rows, in registration order (its time, then its
    line in the night's file), a READ birth followed by its control. A row whose spec this grammar no longer parses, or
    whose sha is not its spec's, is left out (it seats nothing). No table: none."""
    if "births" not in _tables(store.db):
        return []
    out: list[P.Program] = []
    for row in store.db.execute("SELECT id, sha, spec, registered_at FROM births ORDER BY registered_at, night, seq, id"):
        try:
            spec = parse(str(row["spec"]))
            if sha(spec) != str(row["sha"]):
                continue
            prog = program(spec, born_at=str(row["registered_at"]))
        except (SpecError, ValueError, TypeError, KeyError):
            continue
        out.append(prog)
        if prog.reads:
            out.append(program(control_spec(spec), born_at=str(row["registered_at"])))
    return out


# ----------------------------------------------------------------------------------------------------------- the rule
def unread_reaction(row: Mapping[str, Any], uni: Mapping[str, Any]) -> float:
    """The facts' reaction: never read (a price after the event). Every event passes it, so a react rule's count is an
    upper bound (PREREG's own REACT rule, ratio >= 1.04, passes infinity too)."""
    return math.inf


def select(program: P.Program, rows: Iterable[Mapping[str, Any]], *,
           eligible: Callable[[str], Mapping[str, Any] | None], verdict: Callable[[Mapping[str, Any]], int | None],
           reaction: Callable[[Mapping[str, Any], Mapping[str, Any]], float | None] | None = None,
           guidance: Callable[[Mapping[str, Any]], str | None] | None = None) -> list[P.Candidate]:
    """A birth's candidates from already-windowed event rows (league/events/programs.py `select` hands a birth here,
    with the same callables): the family's events knowable after the birth's own registration time, its rule's filters,
    an eligible issuer (a news article's symbol the eligible one), the stored verdict's score and guidance when it reads
    them (an event with none is not taken, as a PREREG READ program's), the reaction when its family has one (an event
    with no reading is not taken; `unread_reaction`: the facts' upper bound, never a price); ranked by its rank key; a
    news family one article an issuer (the highest score, then the earliest, when it ranks by score; else the
    earliest)."""
    spec = _spec_of(str(program.spec))
    family, rule, rank_by = str(spec["family"]), dict(spec["rule"]), str(spec["rank"])
    wants_score = any(k in rule for k in ("score_min", "score_max")) or rank_by == "score"
    unread = reaction is unread_reaction
    since = program.registered_at
    out: list[P.Candidate] = []
    for row in rows:
        knowable = S.parse_iso(row.get("knowable_at"))
        if knowable <= since:
            continue
        value = None
        if family in ("ern", "ern-react", "8k"):
            items = P.items_of(row)
            if family == "8k":
                if items & P.ERN_ITEMS or not items & set(rule["items"]):
                    continue
            elif not items & P.ERN_ITEMS:
                continue
            event = f"8k:{row['accession']}"
        elif family in ("ins", "ins-buy"):
            event = f"f4:{row['accession']}"
            value = float(row.get("cluster_value" if family == "ins" else "purchase_value") or 0.0)
            if value < float(rule.get("value_min", 0)):
                continue
            if family == "ins-buy" and rule.get("roles") and not row.get(f"by_{rule['roles']}"):
                continue
        else:
            event = f"news:{row['id']}"
            if "sources" in rule and str(row.get("source") or "").strip().lower() not in rule["sources"]:
                continue
            if "hours" in rule and knowable.astimezone(C.NY).hour not in rule["hours"]:
                continue
        cik = row.get("cik") or row.get("issuer_cik")
        uni = eligible(cik) if cik else None
        if uni is None:
            continue
        if family in NEWS_FAMILIES and uni["symbol"] != row.get("symbol"):
            continue
        score = None
        if wants_score:
            score = verdict(row)
            if score is None:
                continue
            if "score_min" in rule and score < rule["score_min"]:
                continue
            if "score_max" in rule and score > rule["score_max"]:
                continue
        if "guidance" in rule and (guidance is None or guidance(row) not in rule["guidance"]):
            continue
        rank: float | None = float(score) if rank_by == "score" and score is not None else None
        if family in REACT_FAMILIES and not unread:
            ratio = reaction(row, uni) if reaction is not None else None
            if ratio is None:
                continue
            if "react_min" in rule and ratio < rule["react_min"]:
                continue
            if "react_max" in rule and ratio > rule["react_max"]:
                continue
            if rank_by == "reaction":
                rank = float(ratio)
        if rank_by == "value":
            rank = value
        out.append(P.Candidate(event, str(cik), uni["symbol"], knowable, rank, score, row))
    if family in NEWS_FAMILIES:
        best: dict[str, P.Candidate] = {}
        for c in out:
            have = best.get(c.cik)
            if have is None or _news_order(c, rank_by) > _news_order(have, rank_by):
                best[c.cik] = c
        out = list(best.values())
    return out


def _news_order(c: P.Candidate, rank_by: str) -> tuple[float, float]:
    """A news family's one article an issuer, as PREREG's `select` keeps it: the highest score (when the birth ranks by
    score), then the earliest; on a tie the first in the rows' order stays."""
    score = float(c.verdict_score) if (rank_by == "score" and c.verdict_score is not None) else -9.0
    return (score, -c.knowable_at.timestamp())


# ----------------------------------------------------------------------------------------------------------- the facts
_WALLED: dict[int, int] = {}


@contextlib.contextmanager
def outcome_free(db: sqlite3.Connection, deny: Iterable[str] = FACTS_DENY) -> Any:
    """Every statement on `db` inside this block is refused a read of the tables `deny` (a SQLite authorizer: a price
    after an event, a return, a P&L, a look's p or a band never reaches the facts). Nested blocks keep the outermost
    wall up until it ends; the connection reads as before after it."""
    refused = frozenset(deny)

    def authorize(action: int, arg1: Any, arg2: Any, dbname: Any, source: Any) -> int:
        if action == sqlite3.SQLITE_READ and str(arg1) in refused:
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK
    key = id(db)
    if not _WALLED.get(key):
        db.set_authorizer(authorize)
    _WALLED[key] = _WALLED.get(key, 0) + 1
    try:
        yield db
    finally:
        _WALLED[key] -= 1
        if not _WALLED[key]:
            _WALLED.pop(key, None)
            db.set_authorizer(None)


class _Eligible:
    """The lane's kept eligibility results (`eligibility`: no price), by session: the session's own (eligible only when
    no result of it is ineligible, the backfill reading), else the issuer's nearest result (the latest before, else the
    earliest after); an issuer never judged is not eligible."""

    def __init__(self, store: Any):
        self.by_day: dict[tuple[str, str], list[tuple[int, str | None]]] = {}
        self.by_cik: dict[str, list[tuple[str, int, str | None]]] = {}
        for r in store.db.execute("SELECT day, cik, eligible, symbol FROM eligibility ORDER BY day, cik, rule"):
            day, cik = str(r["day"]), str(r["cik"])
            self.by_day.setdefault((day, cik), []).append((int(r["eligible"]), r["symbol"]))
        for (day, cik), results in sorted(self.by_day.items()):
            ok = all(e for e, _ in results)
            symbol = next((s for e, s in results if e and s), None)
            self.by_cik.setdefault(cik, []).append((day, int(ok), symbol))

    def row(self, day: dt.date, cik: Any) -> dict[str, Any] | None:
        if not cik:
            return None
        cik = str(cik)
        found = self.by_cik.get(cik)
        if not found:
            return None
        text = day.isoformat()
        exact = [x for x in found if x[0] == text]
        before = [x for x in found if x[0] < text]
        pick = exact[0] if exact else (before[-1] if before else found[0])
        return {"cik": cik, "symbol": pick[2]} if pick[1] and pick[2] else None

    def symbols(self, day: dt.date) -> dict[str, str]:
        """{symbol: cik} for news rows: each issuer's symbol as of `day` (its nearest eligible result)."""
        out: dict[str, str] = {}
        for cik in self.by_cik:
            row = self.row(day, cik)
            if row is not None:
                out.setdefault(str(row["symbol"]).upper(), cik)
        return out


class Facts:
    """THE OUTCOME-FREE FACTS of the last `sessions` sessions through `today` (the module docstring): the event rows of
    each session's windows as the lane's decisions read them (registration aside: a rule's count is what it WOULD have
    selected), the kept eligibility, the stored verdicts. Built and read inside `outcome_free`: a read of a refused
    table raises. `facts()` is the architect's JSON; `selected(program)` a program's selected events by session."""

    def __init__(self, store: Any, today: dt.date, *, sessions: int = SESSIONS):
        self.store = store
        self.today = today
        with outcome_free(store.db):
            self.days = [s.day for s in C.previous(store, today + dt.timedelta(days=1), sessions)]
            self.elig = _Eligible(store)
            self.scores: dict[str, tuple[int, str | None]] = {}
            doc, news = V.PROMPTS["doc"].sha, V.PROMPTS["news"].sha
            for r in store.db.execute("SELECT event, prompt_sha, score, guidance FROM verdicts WHERE model=? AND "
                                      "status='ok' AND prompt_sha IN (?, ?)", (V.MODEL, doc, news)):
                kind = "doc" if r["prompt_sha"] == doc else "news"
                self.scores[f"{kind}|{r['event']}"] = (int(r["score"]), r["guidance"] if kind == "doc" else None)
            self.rows = {day: self._windows(day) for day in self.days}
        self._selected: dict[str, dict[dt.date, list[str]]] = {}

    @property
    def complete(self) -> bool:
        return len(self.days) >= SESSIONS

    def _windows(self, day: dt.date) -> dict[str, list[Mapping[str, Any]]]:
        st = self.store
        try:
            lo, hi = P.open_window(st, day)
            clo, chi = P.close_window(st, day)
            nlo, nhi = P.news_window(st, day)
            dlo, dhi = P.day_news_window(st, day)
        except LookupError:
            return {f: [] for f in FAMILIES}
        e8k = P.filings_in(st, "8-K", lo, hi, since=EPOCH)
        ern_close = [r for r in P.filings_in(st, "8-K", clo, chi, since=EPOCH) if P.ERN_ITEMS & P.items_of(r)]
        by_symbol = self.elig.symbols(day)
        news = [dict(a) | {"cik": by_symbol.get(a["symbol"])} for a in P.news_in(st, nlo, nhi, since=EPOCH)]
        day_news = [dict(a) | {"cik": by_symbol.get(a["symbol"])} for a in P.news_in(st, dlo, dhi, since=EPOCH)]
        return {"ern": e8k, "8k": e8k, "ins": P.ins_triggers(st, lo, hi, since=EPOCH),
                "ins-buy": P.ins_buys(st, lo, hi, since=EPOCH), "news": news, "ern-react": ern_close,
                "news-day": day_news, "news-react": day_news}

    def _verdict(self, row: Mapping[str, Any]) -> int | None:
        key = f"doc|8k:{row['accession']}" if row.get("accession") else f"news|news:{row.get('id')}"
        got = self.scores.get(key)
        return None if got is None else got[0]

    def _guidance(self, row: Mapping[str, Any]) -> str | None:
        got = self.scores.get(f"doc|8k:{row['accession']}") if row.get("accession") else None
        return None if got is None else got[1]

    def selected(self, prog: P.Program) -> dict[dt.date, list[str]]:
        """{session: the events `prog`'s rule selects in it} over the facts' sessions: the lane's own `select` with its
        registration time set aside, one event an issuer a decision (the earliest knowable, as `write_intents`), the
        reaction unread (`unread_reaction`)."""
        key = f"{prog.id}|{prog.spec or ''}"     # (a PREREG program's version 2 selects as its version 1)
        if key in self._selected:
            return self._selected[key]
        unbounded = dataclasses.replace(prog, born_at=S.iso(EPOCH))
        out: dict[dt.date, list[str]] = {}
        with outcome_free(self.store.db):
            for day in self.days:
                rows = self.rows[day].get(prog.family, [])
                got = P.select(unbounded, rows, eligible=lambda cik, day=day: self.elig.row(day, cik),
                               verdict=self._verdict, reaction=unread_reaction, guidance=self._guidance)
                taken: set[str] = set()
                events = []
                for c in sorted(got, key=lambda c: (c.knowable_at, c.event)):
                    if c.cik in taken:
                        continue
                    taken.add(c.cik)
                    events.append(c.event)
                out[day] = events
        self._selected[key] = out
        return out

    def count(self, prog: P.Program) -> int:
        return sum(len(v) for v in self.selected(prog).values())

    def candidates(self, specs: Iterable[Any]) -> dict[str, dict[str, Any]]:
        """PER-CANDIDATE SELECTION COUNTS (outcome-free): {id: {selected, per_session, by_session (one count a session,
        oldest first), upper_bound (a react family: the reaction is never read)}} of each spec the grammar parses, or
        {id or "?": {refused: reasons}}."""
        out: dict[str, dict[str, Any]] = {}
        for raw in specs:
            try:
                sp = parse(raw)
            except SpecError as exc:
                ident = raw.get("id") if isinstance(raw, Mapping) and isinstance(raw.get("id"), str) else "?"
                out[ident] = {"refused": exc.reasons}
                continue
            by = self.selected(program(sp, born_at=S.iso(EPOCH)))
            total = sum(len(v) for v in by.values())
            out[sp["id"]] = {"selected": total, "per_session": round(total / len(self.days), 2) if self.days else 0.0,
                             "by_session": [len(by[d]) for d in self.days],
                             "upper_bound": sp["family"] in REACT_FAMILIES}
        return out

    def facts(self, programs: Sequence[P.Program] | None = None) -> dict[str, Any]:
        """The architect's facts (JSON-ready; counts only): the module docstring's list."""
        progs = list(P.PROGRAMS if programs is None else programs)
        n = len(self.days)
        fam: dict[str, dict[str, Any]] = {}
        items: dict[str, int] = {}
        sources: dict[str, int] = {}
        hours: dict[str, dict[str, int]] = {"8k": {}, "news": {}, "news-day": {}}
        scores: dict[str, dict[str, int]] = {}
        guidance: dict[str, int] = {}
        values = {"50k-100k": 0, "100k-250k": 0, "250k-1m": 0, "1m+": 0}
        roles = {"director": 0, "officer": 0, "both": 0}
        seen: set[tuple[str, str]] = set()
        forms: dict[str, set[str]] = {"8-K": set(), "4": set()}
        with outcome_free(self.store.db):
            for day in self.days:
                for family in ("ern", "ern-react", "ins", "ins-buy"):
                    for row in self.rows[day].get(family, []):
                        forms["8-K" if family.startswith("ern") else "4"].add(str(row.get("accession")))
                for row in self.rows[day].get("8k", []):
                    forms["8-K"].add(str(row.get("accession")))
            for day in self.days:
                for family, rows in self.rows[day].items():
                    slot = fam.setdefault(family, {"events": 0, "eligible": 0})
                    for row in rows:
                        items_ = P.items_of(row) if row.get("accession") and family in ("ern", "8k", "ern-react") else set()
                        if family == "ern" and not items_ & P.ERN_ITEMS:
                            continue
                        if family == "8k" and (items_ & P.ERN_ITEMS or not items_):
                            continue
                        slot["events"] += 1
                        uni = self.elig.row(day, row.get("cik"))
                        if uni is None or (family in NEWS_FAMILIES and uni["symbol"] != row.get("symbol")):
                            continue
                        slot["eligible"] += 1
                        ident = str(row.get("accession") or row.get("id"))
                        first = (family, ident) not in seen
                        seen.add((family, ident))
                        knowable_hour = str(S.parse_iso(row["knowable_at"]).astimezone(C.NY).hour)
                        if family == "8k" and first:
                            for item in sorted(items_):
                                items[item] = items.get(item, 0) + 1
                            hours["8k"][knowable_hour] = hours["8k"].get(knowable_hour, 0) + 1
                        if family in ("news", "news-day") and first:
                            src = str(row.get("source") or "").strip().lower() or "(none)"
                            sources[src] = sources.get(src, 0) + 1
                            hours[family][knowable_hour] = hours[family].get(knowable_hour, 0) + 1
                        if family in ("ern", "8k", "news", "news-day", "ern-react") and first:
                            v = self._verdict(row)
                            if v is not None:
                                book = scores.setdefault(family, {})
                                book[str(v)] = book.get(str(v), 0) + 1
                            if family == "ern":
                                g = self._guidance(row)
                                if g is not None:
                                    guidance[g] = guidance.get(g, 0) + 1
                        if family == "ins-buy" and first:
                            value = float(row.get("purchase_value") or 0.0)
                            band = "50k-100k" if value < 100_000 else "100k-250k" if value < 250_000 else \
                                "250k-1m" if value < 1_000_000 else "1m+"
                            values[band] += 1
                            d, o = bool(row.get("by_director")), bool(row.get("by_officer"))
                            roles["both" if d and o else "director" if d else "officer"] += 1
            for slot in fam.values():
                slot["per_session"] = round(slot["eligible"] / n, 2) if n else 0.0
            covered_items: set[str] = set(P.OTHER_ITEMS)
            for p in progs:
                if p.spec is not None and p.family == "8k":
                    covered_items |= set(_spec_of(p.spec)["rule"].get("items") or [])
            listed: list[dict[str, Any]] = []
            done: set[tuple[str, str]] = set()
            for p in progs:
                ident = (p.id, p.spec or "")
                if ident in done:
                    continue     # (a PREREG program's version 2 selects as its version 1 does)
                done.add(ident)
                total = self.count(p)
                listed.append({"id": p.id, "family": p.family, "seatable": bool(p.can_seat or p.seatable),
                               "birth": p.spec is not None, "selected": total,
                               "per_session": round(total / n, 2) if n else 0.0})
        busy = {p.family for p in progs}
        return {
            "as_of": self.today.isoformat(), "sessions": n,
            "first": self.days[0].isoformat() if self.days else None,
            "last": self.days[-1].isoformat() if self.days else None,
            "families": {f: fam.get(f, {"events": 0, "eligible": 0, "per_session": 0.0}) for f in FAMILIES},
            "forms": {"8-K": len(forms["8-K"]), "4-buys": len(forms["4"])},
            "items_8k": dict(sorted(items.items())),
            "news_sources": dict(sorted(sources.items(), key=lambda kv: (-kv[1], kv[0]))[:15]),
            "hours": {k: dict(sorted(v.items(), key=lambda kv: int(kv[0]))) for k, v in hours.items()},
            "scores": {k: dict(sorted(v.items(), key=lambda kv: int(kv[0]))) for k, v in sorted(scores.items())},
            "guidance_ern": dict(sorted(guidance.items())),
            "ins_buy": {"value": values, "roles": roles},
            "programs": listed,
            "unprogrammed": {"families": [f for f in FAMILIES if f not in busy],
                             "items_8k": sorted(i for i in items if i not in covered_items)},
            "react_counts": "upper bounds: a reaction is a price after the event, never read here",
        }


def jaccard(a: set[str], b: set[str]) -> float:
    """|a & b| / |a | b|; 0 when either is empty (a rule that selects nothing is the rate's to refuse, no duplicate)."""
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _events(selected: Mapping[dt.date, Sequence[str]]) -> set[str]:
    return {e for events in selected.values() for e in events}


# ----------------------------------------------------------------------------------------------------------- the budget
def budget_used_tenths(store: Any) -> int:
    """Tenths of an expected false pass already charged (A81): SEATING's own sum as the report counts it
    (league/events/screen.py `expected_false_passes`, after `load_births`: 0.10 for every seatable version ever
    registered in the lane, PREREG-EVL-1 to -4's twelve and every seatable birth, retired ones included, and any later
    version of a seatable program the store has seen). Never a figure written here."""
    return int(round(float(SN.expected_false_passes(store)["expected"]) * 10))


def _tonight(store: Any, night: dt.date | None) -> int:
    """The seatable births already registered for `night` (a second run of the night, the captain's beside the
    architect's, shares its three)."""
    if night is None or "births" not in _tables(store.db):
        return 0
    return int(store.db.execute("SELECT COUNT(*) FROM births WHERE night=? AND seatable=1",
                                (night.isoformat(),)).fetchone()[0])


def budget(store: Any, night: dt.date | None = None) -> dict[str, Any]:
    """The stated budget as it stands: tenths used (every seatable version ever registered), the limit, what is left,
    and the seatable births `night` may still register."""
    used = budget_used_tenths(store)
    tonight = _tonight(store, night)
    return {"used": used / 10, "limit": BUDGET_TENTHS / 10, "left": (BUDGET_TENTHS - used) / 10,
            "seatable_left_tonight": max(0, min(SEATABLE_A_NIGHT - tonight, (BUDGET_TENTHS - used) // CHARGE_TENTHS)),
            "charge": CHARGE_TENTHS / 10}


# ----------------------------------------------------------------------------------------------------------- validator
def _why(text: Any) -> str:
    line = re.sub(r"[\x00-\x1f\x7f]+", " ", str(text or "")).strip()
    return line[:WHY_MAX]


def validate(store: Any, facts: Facts, proposals: Sequence[Mapping[str, Any]], *,
             night: dt.date | None = None) -> list[dict[str, Any]]:
    """THE VALIDATOR (the module docstring), in order: each proposal {spec, why, by} gets {seq, id, sha, spec (canonical,
    or the raw text when the grammar refused it), why, by, ok, reasons, selected, per_session, jaccard (the highest, and
    with whom), charge (tenths)}; an accepted seatable birth is charged before the next is judged. `store` must have its
    births loaded (programs.load_births) so the registered ids and the budget are current."""
    known_ids = {p.id for p in P.PROGRAMS}
    known_sha: set[str] = set()
    if "births" in _tables(store.db):
        for r in store.db.execute("SELECT id, sha FROM births"):
            known_ids.add(str(r["id"]))
            known_ids.add(control_id(str(r["id"])))
            known_sha.add(str(r["sha"]))
    used = budget_used_tenths(store)
    tonight_used = _tonight(store, night)
    registered = [(p.id, _events(facts.selected(p))) for p in P.PROGRAMS]
    accepted: list[tuple[str, set[str]]] = []
    out: list[dict[str, Any]] = []
    for seq, proposal in enumerate(proposals):
        raw = proposal.get("spec") if isinstance(proposal, Mapping) else None
        entry: dict[str, Any] = {"seq": seq, "id": None, "sha": None, "why": _why((proposal or {}).get("why")),
                                 "by": _why((proposal or {}).get("by")) or "architect", "ok": False, "reasons": [],
                                 "selected": None, "per_session": None, "jaccard": None, "charge": 0}
        try:
            spec = parse(raw)
        except SpecError as exc:
            entry["spec"] = json.dumps(raw, sort_keys=True, default=str)[:4000]
            entry["reasons"] = exc.reasons
            out.append(entry)
            continue
        text = canonical(spec)
        digest = hashlib.sha256(text.encode("ascii")).hexdigest()
        entry |= {"spec": text, "id": spec["id"], "sha": digest}
        why: list[str] = []
        if spec["id"] in known_ids or control_id(spec["id"]) in known_ids:
            why.append(f"{spec['id']} is registered already (a change is a new birth with a new id)")
        if digest in known_sha:
            why.append("this very spec is registered already")
        prog = program(spec, born_at=S.iso(EPOCH))
        mine = _events(facts.selected(prog))
        entry["selected"] = len(mine)
        entry["per_session"] = round(len(mine) / len(facts.days), 2) if facts.days else 0.0
        if not facts.complete:
            why.append(f"the store holds {len(facts.days)} sessions, not the {SESSIONS} the rate is read over")
        elif len(mine) < MIN_RATE * SESSIONS:
            why.append(f"{len(mine)} selected events over the last {SESSIONS} sessions: under {MIN_RATE} a session"
                       + (" (an upper bound: the reaction is never read)" if spec["family"] in REACT_FAMILIES else ""))
        worst = (0.0, None)
        for other, events in registered + accepted:
            j = jaccard(mine, events)
            if j > worst[0] or worst[1] is None:
                worst = (j, other)
        entry["jaccard"] = {"max": round(worst[0], 4), "with": worst[1]}
        if worst[1] is not None and worst[0] >= JACCARD_MAX:
            why.append(f"a duplicate of {worst[1]}: Jaccard {worst[0]:.2f} >= {JACCARD_MAX} over the last {SESSIONS} "
                       "sessions' selected events")
        if spec["seatable"] and not why:
            if tonight_used + 1 > SEATABLE_A_NIGHT:
                why.append(f"{SEATABLE_A_NIGHT} seatable births a night at most")
            elif used + CHARGE_TENTHS > BUDGET_TENTHS:
                why.append(f"the false-pass budget: {used / 10:.1f} of {BUDGET_TENTHS / 10:.1f} used, a seatable birth "
                           f"adds {CHARGE_TENTHS / 10:.1f}")
        if why:
            entry["reasons"] = why
            out.append(entry)
            continue
        entry["ok"] = True
        if spec["seatable"]:
            entry["charge"] = CHARGE_TENTHS
            used += CHARGE_TENTHS
            tonight_used += 1
        known_ids |= {spec["id"], control_id(spec["id"])}
        known_sha.add(digest)
        accepted.append((spec["id"], mine))
        out.append(entry)
    return out


# ----------------------------------------------------------------------------------------------------------- proposer
SYSTEM = ("You are the architect of LTCM's event lane. You design pre-registered rules over public US-stock events "
          "(SEC 8-K filings, Form 4 insider buys, single-company news) that buy whole shares long-only and hold them "
          "for a session. You see only outcome-free facts: event counts and the stored verdicts of a fixed reading "
          "prompt. You never see a price after an event, a return, a profit or a test result. Answer with JSON only.")

USER = """THE GRAMMAR. A spec is a JSON object with exactly these fields:
- "id": "EVL-B-" then upper-case letters/digits groups joined by "-" (at most 40 characters), new.
- "version": 1.
- "family": one of ern (8-K item 2.02, buy at the next open), ern-react (8-K 2.02 knowable during the session, buy at
  the close after its reaction), 8k (8-Ks carrying one of an item set, never 2.02, next open), ins (Form 4 cluster of
  2+ insiders buying, next open), ins-buy (one director or officer buying >= $50,000 in the open market, next open),
  news (single-company articles overnight, next open), news-day (the day's articles to 15:29 ET, buy at the close),
  news-react (the day's articles with the stock's reaction, buy at the close).
- "rule": only these fields, by family:
  ern: score_min, score_max (integers -3..3: the stored verdict of the filing), guidance (a list of raised, maintained,
  lowered, none, unclear); ern-react: score_min, score_max, react_min (1.01..1.25) or react_max (0.75..0.99), the
  reaction being the 15:29 price over the last close before the event; 8k: items (a list of 8-K items such as 1.01,
  5.02, 8.01), score_min, score_max, guidance (with a verdict field, items only among <<READ_ITEMS>>); ins: value_min
  (dollars >= 50000); ins-buy: value_min (>= 50000), roles ("director" or "officer"); news and news-day: score_min,
  score_max, sources (news source names), hours (New York hours 0..23 of the article); news-react: react_min or
  react_max, sources, hours.
- "entry": "open" for ern, 8k, ins, ins-buy, news; "close" for ern-react, news-day, news-react.
- "exit": "close" (the close of session h; the only exit after an open entry) or "open" (the next open, after a close
  entry).
- "hold": h, 1..5 sessions; 1 when seatable.
- "rank": "score", "reaction" (react families), "value" (Form 4) or "none".
- "seatable": true (trades real money at learning size from its first event and is judged by the screen) or false (a
  record, free).
THE VALIDATOR refuses a spec that selects fewer than <<MIN_RATE>> events a session over the last <<SESSIONS>>
sessions, or whose selected events overlap any existing program's with a Jaccard of <<JACCARD>> or more. Each seatable
spec costs 0.10 of the false-pass budget: <<BUDGET>>. Propose at most <<K>> specs, at most <<SEATABLE>> of them
seatable. Prefer rules a reader could explain in one line, over events and items no program covers yet.

THE FACTS (counts over the last <<SESSIONS>> sessions; "eligible" are the events of listed, liquid operating
companies the lane can trade; react counts are upper bounds):
<<FACTS>>

Answer with JSON only: {"specs": [{"spec": {...}, "why": "one line"}]}"""


def prompt_sha() -> str:
    """The proposer's prompt version: model, temperature, max_tokens, the system text and the user template."""
    spec = {"model": MODEL, "temperature": TEMPERATURE, "max_tokens": MAX_TOKENS, "system": SYSTEM, "user": USER}
    return hashlib.sha256(json.dumps(spec, sort_keys=True).encode("utf-8")).hexdigest()


def render(facts: Mapping[str, Any], budget_: Mapping[str, Any], *, k: int = K) -> str:
    text = json.dumps(facts, sort_keys=True, separators=(",", ":"))
    left = int(budget_.get("seatable_left_tonight", 0))
    return (USER.replace("<<READ_ITEMS>>", ", ".join(READ_ITEMS_8K)).replace("<<MIN_RATE>>", str(MIN_RATE))
            .replace("<<SESSIONS>>", str(SESSIONS)).replace("<<JACCARD>>", str(JACCARD_MAX))
            .replace("<<BUDGET>>", f"{budget_['used']:.1f} of {budget_['limit']:.1f} used")
            .replace("<<K>>", str(k)).replace("<<SEATABLE>>", str(left)).replace("<<FACTS>>", text))


def worst_usd(user_text: str) -> float:
    """The call's worst case: its input at a token every CHARS_A_TOKEN characters and its whole max_tokens out."""
    tokens_in = math.ceil((len(SYSTEM) + len(user_text)) / CHARS_A_TOKEN)
    return tokens_in * PRICE_IN + MAX_TOKENS * PRICE_OUT


def spent(store: Any, night: dt.date) -> float:
    row = store.db.execute("SELECT COALESCE(SUM(usd), 0) FROM birth_calls WHERE night=?", (night.isoformat(),)).fetchone()
    return float(row[0] or 0.0)


def parse_answer(text: str, *, k: int = K) -> tuple[list[dict[str, Any]], int]:
    """([{spec, why}] the first `k` of the answer's specs, how many it held), from {"specs": [...]} or a bare list
    (a fenced block is read as its content). Anything else: ([], 0)."""
    body = (text or "").strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", body, re.S)
    if fence:
        body = fence.group(1)
    try:
        data = json.loads(body)
    except ValueError:
        return [], 0
    items = data.get("specs") if isinstance(data, Mapping) else data
    if not isinstance(items, list):
        return [], 0
    out = []
    for item in items[: max(0, int(k))]:
        if isinstance(item, Mapping) and "spec" in item:
            out.append({"spec": item.get("spec"), "why": item.get("why"), "by": f"architect:{MODEL}"})
        else:
            out.append({"spec": item, "why": None, "by": f"architect:{MODEL}"})
    return out, len(items)


def propose(store: Any, gw: Any, facts: Mapping[str, Any], *, night: dt.date, now: Callable[[], dt.datetime],
            k: int = K, cap: float = NIGHT_USD, line_left: float | None = None) -> dict[str, Any]:
    """THE ARCHITECT'S ONE CALL A NIGHT (the module docstring): {status, proposals, offered, usd, prompt_sha,
    facts_sha}. A night's stored answer is read again (never asked again); no answer is stored for a call that got none
    (a refusal by the gateway or the lane, a transport failure, a 5xx): the night proposes nothing. `line_left` (the
    House's lane, league/events/house.py `line_left`): what is left of the lane's line today; the call's worst case must
    fit under it too (release 1019e's review: the call is inside the lane's line), or no call is made."""
    psha = prompt_sha()
    facts_text = json.dumps(facts, sort_keys=True, separators=(",", ":"))
    fsha = hashlib.sha256(facts_text.encode("utf-8")).hexdigest()
    have = store.db.execute("SELECT * FROM birth_calls WHERE night=? AND prompt_sha=? AND model=?",
                            (night.isoformat(), psha, MODEL)).fetchone()
    base = {"prompt_sha": psha, "facts_sha": fsha}
    if have is not None:
        props, offered = parse_answer(str(have["answer"] or ""), k=k) if have["status"] == "ok" else ([], 0)
        return base | {"status": f"stored:{have['status']}", "proposals": props, "offered": offered,
                       "usd": float(have["usd"] or 0.0), "facts_sha": have["facts_sha"] or fsha}
    user = render(facts, budget(store, night), k=k)
    worst = worst_usd(user)
    already = spent(store, night)
    if already + worst > cap:
        return base | {"status": "cap", "proposals": [], "offered": 0, "usd": 0.0,
                       "why": f"the call's worst case ${worst:.4f} over the night's ${cap - already:.4f} left"}
    if line_left is not None and worst > line_left:
        return base | {"status": "cap", "proposals": [], "offered": 0, "usd": 0.0,
                       "why": f"the call's worst case ${worst:.4f} over the ${max(0.0, line_left):.4f} left of the lane's "
                              "line today"}
    request_id = f"evl-births:{night.isoformat()}:{psha[:12]}"
    body = {"model": MODEL, "max_tokens": MAX_TOKENS, "temperature": TEMPERATURE, "system": SYSTEM,
            "messages": [{"role": "user", "content": user}]}
    asked = now()
    for _ in range(2):
        try:
            code, payload = gw.post_json(V.PATH, body, headers={V.REQUEST_HEADER: request_id})
        except OSError as exc:
            last = f"{type(exc).__name__}: {str(exc)[:120]}"
            continue
        if not (200 <= code < 300 and isinstance(payload, Mapping)):
            last = f"HTTP {code}"
            if 400 <= code < 500 and code != 429:
                break
            continue
        try:
            usd = float((gw.last_headers or {}).get(V.COST_HEADER))
        except (TypeError, ValueError):
            usd = worst      # (no stated cost: the night counts the worst case)
        text = "".join(b.get("text") or "" for b in payload.get("content") or []
                       if isinstance(b, Mapping) and b.get("type") == "text")
        status = "refused" if payload.get("stop_reason") == "refusal" else "ok"
        with store.tx() as db:
            db.execute("INSERT OR IGNORE INTO birth_calls(night, prompt_sha, model, request_id, asked_at, answered_at, "
                       "status, user_sha, facts_sha, answer, usd) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                       (night.isoformat(), psha, MODEL, request_id, S.iso(asked), S.iso(now()), status,
                        hashlib.sha256(user.encode("utf-8")).hexdigest(), fsha, text, usd))
        props, offered = parse_answer(text, k=k) if status == "ok" else ([], 0)
        return base | {"status": status, "proposals": props, "offered": offered, "usd": usd}
    return base | {"status": "no answer", "proposals": [], "offered": 0, "usd": 0.0, "why": last}


# ----------------------------------------------------------------------------------------------------------- register
def path_of(night: dt.date) -> str:
    return f"{DOCS_DIR}/{night.isoformat()}.jsonl"


def line_of(entry: Mapping[str, Any], *, night: dt.date, facts_sha: str | None, prompt: str | None) -> str:
    """The registered line: one JSON object (canonical: keys sorted, no spaces) carrying the canonical spec, its sha,
    the one-line rationale, who proposed it, the night, the facts' sha and the prompt's sha."""
    data = {"grammar": GRAMMAR, "spec": json.loads(entry["spec"]), "sha": entry["sha"], "why": entry.get("why") or "",
            "by": entry.get("by") or "architect", "night": night.isoformat(), "facts_sha": facts_sha,
            "prompt_sha": prompt}
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def register(store: Any, gw: Any, entries: Sequence[Mapping[str, Any]], *, night: dt.date,
             now: Callable[[], dt.datetime]) -> dict[str, Any]:
    """Append the accepted entries' lines (`line`) to docs/births/<night>.jsonl through the gateway's docs route; with
    GitHub's receipt, write each as a REGISTERED birth (`births`) at the later of GitHub's commit time and the House's
    receipt of the answer. {status: registered | unchanged | refused | unknown, ...}: `unknown` (no answer, or an answer
    without GitHub's commit time) is posted again by `reconcile`; `refused` was GitHub's or the gateway's no."""
    if not entries:
        return {"status": "nothing"}
    path = path_of(night)
    lines = [str(e["line"]) for e in entries]
    body = {"path": path, "lines": lines, "message": f"{len(lines)} birth(s) of {night.isoformat()}"}
    try:
        code, answer = gw.post_json(DOCS_ROUTE, body)
    except OSError as exc:
        return {"status": "unknown", "error": f"{type(exc).__name__}: {str(exc)[:160]}"}
    received = now()
    answer = answer if isinstance(answer, Mapping) else {}
    if not 200 <= int(code) < 300 or answer.get("ok") is not True:
        unknown = int(code) >= 500 or int(code) == 429 or answer.get("refused") == "no_answer"
        return {"status": "unknown" if unknown else "refused", "code": int(code),
                "error": str(answer.get("error") or "")[:200], "refused": answer.get("refused")}
    committed = answer.get("committed_at")
    try:
        at = S.parse_iso(str(committed))
    except (TypeError, ValueError):
        return {"status": "unknown", "error": "the answer carries no GitHub commit time", "code": int(code)}
    registered_at = max(at, received)
    commit = str(answer.get("commit") or "")[:64] or None
    with store.tx() as db:
        for seq, e in enumerate(entries):
            spec = json.loads(str(e["spec"]))
            db.execute("INSERT OR IGNORE INTO births(id, version, sha, spec, seatable, registered_at, committed_at, "
                       "received_at, path, commit_sha, seq, line, why, by, night) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
                       "?, ?, ?, ?, ?)",
                       (spec["id"], int(spec["version"]), e["sha"], e["spec"], int(bool(spec["seatable"])),
                        S.iso(registered_at), S.iso(at), S.iso(received), path, commit, seq, e["line"],
                        e.get("why") or "", e.get("by") or "", night.isoformat()))
    return {"status": "unchanged" if answer.get("committed") is False else "registered", "commit": commit,
            "committed_at": S.iso(at), "received_at": S.iso(received), "registered_at": S.iso(registered_at),
            "path": path, "lines": len(lines)}


def _set_status(store: Any, night: str, seqs: Iterable[int], status: str) -> None:
    with store.tx() as db:
        for seq in seqs:
            db.execute("UPDATE birth_candidates SET status=? WHERE night=? AND seq=?", (status, night, int(seq)))


def reconcile(store: Any, gw: Any, *, now: Callable[[], dt.datetime]) -> list[dict[str, Any]]:
    """Every night whose registration got no answer (`unknown`) posted again with the very same lines; registered when
    the route commits them now or answers that they stand already (its latest commit's time: later than the true one,
    the reading that counts fewer events)."""
    out = []
    nights = [str(r[0]) for r in store.db.execute("SELECT DISTINCT night FROM birth_candidates WHERE status='unknown' "
                                                  "ORDER BY night")]
    for night in nights:
        rows = [dict(r) for r in store.db.execute("SELECT * FROM birth_candidates WHERE night=? AND status='unknown' "
                                                  "ORDER BY seq", (night,))]
        entries = [{"spec": r["spec"], "sha": r["sha"], "line": r["line"], "why": r["why"], "by": r["by"]} for r in rows]
        got = register(store, gw, entries, night=dt.date.fromisoformat(night), now=now)
        if got["status"] in ("registered", "unchanged"):
            _set_status(store, night, [r["seq"] for r in rows], "registered")
        elif got["status"] == "refused":
            _set_status(store, night, [r["seq"] for r in rows], "refused")
        out.append({"night": night} | got)
    return out


# ----------------------------------------------------------------------------------------------------------- the night
def night(store: Any, gw: Any, *, today: dt.date, now: Callable[[], dt.datetime],
          proposals: Sequence[Mapping[str, Any]] | None = None, k: int = K, cap: float = NIGHT_USD,
          dry_run: bool = False, line_left: float | None = None) -> dict[str, Any]:
    """THE BIRTHS JOB of the night of `today` (receipt `births`): the unknown registrations of earlier nights posted
    again; the outcome-free facts; the architect's one call (or `proposals`, the captain's own {spec, why}: no call),
    held to the night's cap and to `line_left` (`propose`); the validator; the accepted lines registered (`dry_run`:
    validated and recorded, never registered); the births loaded again. Returns its summary."""
    P.load_births(store)
    rid = store.start_receipt(JOB, now=now())
    out: dict[str, Any] = {"night": today.isoformat()}
    status = "ok"
    try:
        if not dry_run:
            out["reconciled"] = reconcile(store, gw, now=now)
            P.load_births(store)
        facts = Facts(store, today)
        sheet = facts.facts()
        fsha = hashlib.sha256(json.dumps(sheet, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        call = None
        if proposals is None:
            call = propose(store, gw, sheet, night=today, now=now, k=k, cap=cap, line_left=line_left)
            proposals = call["proposals"]
            out["call"] = {key: call.get(key) for key in ("status", "offered", "usd", "why")}
            psha = call.get("prompt_sha")
        else:
            proposals = [dict(p) | {"by": (p.get("by") or "captain")} for p in proposals]
            psha = None
        checked = validate(store, facts, proposals, night=today)
        out["counts"] = {c["id"] or f"#{c['seq']}": {"selected": c["selected"], "per_session": c["per_session"],
                                                      "jaccard": c["jaccard"]} for c in checked}
        first = int(store.db.execute("SELECT COALESCE(MAX(seq) + 1, 0) FROM birth_candidates WHERE night=?",
                                     (today.isoformat(),)).fetchone()[0])
        for c in checked:
            c["seq"] = first + int(c["seq"])
            c["line"] = line_of(c, night=today, facts_sha=fsha, prompt=psha) if c["ok"] else None
        with store.tx() as db:
            for c in checked:
                figures = {"selected": c["selected"], "per_session": c["per_session"], "jaccard": c["jaccard"],
                           "charge": c["charge"]}
                db.execute("INSERT INTO birth_candidates(night, seq, sha, id, spec, why, by, status, reasons, figures, line, "
                           "at) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                           (today.isoformat(), c["seq"], c["sha"], c["id"], c["spec"], c["why"], c["by"],
                            "accepted" if c["ok"] else "refused", json.dumps(c["reasons"]),
                            json.dumps(figures, sort_keys=True), c["line"], S.iso(now())))
        accepted = [c for c in checked if c["ok"]]
        out["proposed"] = len(checked)
        out["accepted"] = [c["id"] for c in accepted]
        out["refused"] = [{"id": c["id"], "why": c["reasons"][:3]} for c in checked if not c["ok"]][:K * 2]
        if accepted and not dry_run:
            # (`unknown` first: a job that dies between GitHub's commit and the births rows is posted again next night)
            _set_status(store, today.isoformat(), [c["seq"] for c in accepted], "unknown")
            reg = register(store, gw, accepted, night=today, now=now)
            out["registration"] = reg
            final = {"registered": "registered", "unchanged": "registered", "refused": "refused",
                     "unknown": "unknown"}.get(reg["status"], "refused")
            _set_status(store, today.isoformat(), [c["seq"] for c in accepted], final)
            if final != "registered":
                status = "partial"
        P.load_births(store)
        out["budget"] = budget(store, today)
    except Exception as exc:  # noqa: BLE001 - the night's failure is its receipt's; the lane goes on
        status = "failed"
        out["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
    store.finish_receipt(rid, status, out, now=now())
    return out | {"_status": status}


def summary(store: Any) -> dict[str, Any]:
    """The report's line: births registered (seatable, records), the last night's candidates and its model cost."""
    if "births" not in _tables(store.db):
        return {"registered": 0, "seatable": 0, "records": 0, "last_night": None}
    reg = store.db.execute("SELECT COUNT(*), COALESCE(SUM(seatable), 0) FROM births").fetchone()
    last = store.db.execute("SELECT night FROM birth_candidates ORDER BY night DESC LIMIT 1").fetchone()
    night_ = None
    if last is not None:
        counts = {str(r[0]): int(r[1]) for r in store.db.execute(
            "SELECT status, COUNT(*) FROM birth_candidates WHERE night=? GROUP BY status", (last[0],))}
        night_ = {"night": str(last[0]), **counts, "usd": round(spent(store, dt.date.fromisoformat(str(last[0]))), 4)}
    return {"registered": int(reg[0]), "seatable": int(reg[1]), "records": int(reg[0]) - int(reg[1]),
            "last_night": night_}


__all__ = ["GRAMMAR", "FIELDS", "FAMILIES", "ENTRY", "RULE_FIELDS", "RANKS", "ITEMS_8K", "READ_ITEMS_8K", "SpecError",
           "parse", "canonical", "sha", "reads", "control_spec", "control_id", "program", "registered_programs",
           "select", "unread_reaction", "outcome_free", "Facts", "jaccard", "budget", "budget_used_tenths", "validate",
           "SYSTEM", "USER", "prompt_sha", "render", "worst_usd", "parse_answer", "propose", "path_of", "line_of",
           "register", "reconcile", "night", "summary", "SESSIONS", "MIN_RATE", "JACCARD_MAX", "CHARGE_TENTHS",
           "BUDGET_TENTHS", "SEATABLE_A_NIGHT", "K", "NIGHT_USD", "MODEL", "FACTS_DENY", "DOCS_ROUTE", "JOB"]
