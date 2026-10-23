"""PREREG-EVL-10: READER-2 (R2), a stronger reader of the news and 8-Ks the slots can trade, and its one consumer seat
EVL-R2-ON (docs/prereg/PREREG-EVL-10.md, frozen on the tag `prereg-evl-10`, sha256 ab7e587c...; REGISTERED_AT_10
2026-10-23T07:10:45Z, the captain's A144; THE FROZEN TEXT WINS wherever this module differs). Python's standard
library only. Nothing here runs while league/events/programs.py `REGISTERED_AT_10` is None.

THE REQUEST SPEC is the fix round's `evl10/fix1/r2_spec.py` (docs/prereg/evl-10/fix1/r2_spec.py, sha256
fd5c040e...), whose constants and functions from `MODEL` to `consumer_key` are copied below VERBATIM between the two
marker lines (league/tests/test_events_evl10.py compares the block byte for byte with the frozen file and recomputes
the two request shas: R2-NEWS a8239614..., R2-DOC 127c19f3...). THE PIN (section 1.5): the captain's smoke test
returned the response model "claude-sonnet-5-5" for both schemas (A144).

WHAT IT DOES (sections 1-2; the docstrings of each function say which clause):
- QUALIFICATION AND CHOICE (section 1.4, `scan`): each job of R2's own House lane ('reader', key 'reader:r2', one
  started on each House publish when R2's last has finished: league/events/house.py `EventLane.turn`) makes one
  QUALIFICATION SCAN of entry session D from 07:30:00 ET until tau - 30 s, stored in `r2_scan`; every event that
  qualifies as stored at the scan (NEWS-ON: a DAY(D) article of an eligible, liquid, BUYABLE issuer with a stored `ok`
  PROMPT-NEWS verdict of score >= 2; 8K-ON: an F8K(D) filing of an issuer not EXCLUDED on D, TEXT of 200 characters or
  more, a stored `ok` PROMPT-DOC verdict of score <= 1) is written once to `r2_qual` with the hash draw h, the share q
  (fixed at the session's first scan from the last 5 COMPLETE sessions) and whether it is CHOSEN (an issuer's first
  qualifying article when h < q, else its first of score 3; once more for a later one of a strictly higher score; at
  most 2 an issuer and 64 a session; an issuer's first qualifying filing, at most 8 a session).
- THE ASKS (section 1.5, `job`, `ask`): one call a job, in qualification order, streamed (`gw.post_stream`), only
  while (a) R2's own dollars of the UTC day plus the call's worst-case hold fit R2_LINE = max(0, min($0.75, L - 1.5 x
  V - $0.25)) (fixed at the day's first ask, rounded down to the cent), (b) no cap hold names the day, and (c) the
  lane's whole spend of the day plus the hold fits the lane's line L (the reading that asks less: R2's dollars are
  inside the lane's line); stopped for good by THE PIN (a response model other than the pin, stored `refused`), THE
  SCHEMA STOP and SPEND FOLLOWS THE SEAT; for the day by THE DAY STOP (three gateway 4xx). Every answer is stored once
  in `reads2` (ok, unparsed, refused, cut, lost), never asked again; a call refused before it was sent stores nothing.
- THE DECISION (section 2.4, `decide`): `decide-close-r2:<D>`, the LAST row of the scheduler's close table, a clock
  start at tau (D's close - 20 minutes), SQL over stored rows only, its intents of EVL-R2-ON and its control and two
  records (every one with decided_at = tau) and FEATURES-R2 v1 written in ONE transaction with its receipt `ok`.
- THE ONE READING (section 2.4, `one_reading`): the four rows' picks for real money and PREREG-EVL-8's EVL-META-ON are
  the live receipt's own intents, whatever the reading's time; empty with no such receipt.
- THE REPORT AND THE ALARMS (`report_lines`, `alarms`): counts only (reader_line, reader_pin, reader_schema,
  reader_stop, reader_missing, r2_starve, r2_cap).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import re
import urllib.error
from decimal import ROUND_FLOOR, Decimal
from typing import Any, Callable, Iterable, Mapping, Sequence

from . import calendar as C
from . import programs as P
from . import scheduler as X
from . import store as S
from . import verdicts as V

# ===================================== THE FROZEN REQUEST SPEC (docs/prereg/evl-10/fix1/r2_spec.py), VERBATIM: BEGIN
MODEL = "claude-sonnet-5-5"
EFFORT = "low"
MAX_TOKENS = {"news": 1200, "doc": 1600}     # thinking is output and counts inside max_tokens (gateway/lib/claude.mjs)
THINKING = {"type": "adaptive", "display": "omitted"}
STREAM = True
# The lane's streamed-call bounds (league/events/gw.py post_stream): a byte at least every GAP_S, the whole answer LIMIT_S.
GAP_S = 30.0
LIMIT_S = 90.0

SYSTEM_NEWS = ("You are an equity analyst reading one news item about one company the moment it is published. You are "
               "given no market data. Report only what the texts state, then judge.")
SYSTEM_DOC = ("You are an equity analyst reading a company's SEC Form 8-K the moment it is published. You are given no "
              "market data. Report only what the texts state, then judge.")

USER_NEWS = """Stock: {symbol} ({name}). Published {created_et} ET by {source}. Read on {read_day}.
Headline: {headline}
Summary: {summary}

Earlier news naming this stock in the 30 days before this item, newest first ("none" if none):
<earlier_news>
{prior_news}
</earlier_news>
This company's SEC 8-K filings in the same 30 days, newest first ("none" if none):
<earlier_filings>
{prior_filings}
</earlier_filings>

Answer from these texts alone:
type: what the item is mainly about.
new: 2 if its main fact appears in none of the earlier lines and is not described as previously announced; 1 if it adds material detail to an earlier line; 0 if it repeats an earlier line or reports something already public.
corroborated: 2 if one of the company's earlier filings or an earlier line from a different source reports the same main fact; 1 if the item itself is or quotes the company's own announcement; 0 otherwise.
price_story: true if its main subject is this stock's own price move, trading volume or options activity.
consensus: the reported results or outlook against analysts' consensus estimates, only as the item states it, else not_stated.
vs_own_guidance: the reported results or the new outlook against the company's own previous guidance, only as the item states it, else not_stated.
magnitude: the economic size of the news for this company: 0 none, 1 minor, 2 notable, 3 major.
specific: 0 vague, 1 some figures, 2 precise figures that can be checked.
surprise: from -3 (far worse) to 3 (far better) than what investors most likely expected before this item; 0 if neutral or unclear.
p_up: the probability, from 0 to 100 in steps of 5, that this stock outperforms the overall stock market from the closing auction of the trading day this item is read on to the opening auction of the next trading day."""

USER_DOC = """Company: {name} (ticker {ticker}). SEC Form 8-K, items {items}, accepted {acceptance_et} ET. Read on {read_day}.
Document (its first 16,000 characters):
<document>
{text}
</document>
News naming this stock in the 30 days before this filing and since it, newest first ("none" if none):
<news>
{prior_news}
</news>

Answer from these texts alone:
type: what the filing is mainly about.
routine: true if it is procedural or recurring with no economic news (for example an investor presentation, a regular dividend at the usual rate, a meeting's vote results).
material: how material the reported items are for this company: 0 procedural, 1 minor, 2 notable, 3 major (for example a transformative deal, a guidance change, a restatement or a going-concern doubt).
new: 2 if its main fact is new; 1 if it updates something announced before; 0 if it repeats something already announced or already in the news lines.
corroborated: 2 if a news line from an independent source reports the same main fact; 1 if only the company's own text states it; 0 if the news lines contradict it.
consensus: the results or outlook against analysts' consensus estimates, only as the document or the news lines state it, else not_stated.
vs_own_guidance: the results or the new outlook against the company's own previous guidance, only as the document states it, else not_stated.
guide_chg_pct: when the document gives the previous and the new outlook as a range or a point for the same measure and period, the new midpoint over the previous midpoint minus 1, in percent to one decimal; else null.
dilution: true if the filing issues or registers new shares or securities convertible into shares.
one_offs: true if one-time items explain most of the change in the headline profit measure.
magnitude: the economic size of the news for this company: 0 none, 1 minor, 2 notable, 3 major.
specific: 0 vague, 1 some figures, 2 precise figures that can be checked.
tone: management's language, from -2 (defensive) to 2 (confident).
surprise: from -3 (far worse) to 3 (far better) than what investors most likely expected before this filing; 0 if neutral or unclear.
p_up: the probability, from 0 to 100 in steps of 5, that this stock outperforms the overall stock market from the closing auction of the trading day this item is read on to the opening auction of the next trading day."""

NEWS_TYPES = ["earnings", "guidance", "analyst_rating", "analyst_target", "m_and_a", "contract_product",
              "regulatory_legal", "financing", "capital_return", "management", "price_move", "commentary", "other"]
DOC_TYPES = ["earnings", "guidance", "m_and_a_target", "m_and_a_acquirer", "asset_sale", "financing_equity",
             "financing_debt", "capital_return", "material_contract", "product_regulatory", "legal_adverse",
             "management", "restructuring", "investor_materials", "other"]
CONSENSUS = ["beat", "inline", "miss", "mixed", "not_stated"]
OWN_GUIDE = ["above", "raised", "maintained", "within", "below", "lowered", "withdrawn", "initiated", "not_stated"]


def _int(lo: int, hi: int, step: int = 1) -> dict:
    """An integer as an ENUM: the House sends raw bodies (no SDK strips unsupported keywords), so the range is the
    grammar's, never a minimum/maximum keyword."""
    return {"type": "integer", "enum": list(range(lo, hi + 1, step))}


def _num_or_null() -> dict:
    return {"anyOf": [{"type": "number"}, {"type": "null"}]}


def _enum(values: list[str]) -> dict:
    return {"type": "string", "enum": list(values)}


SCHEMA_NEWS = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "type": _enum(NEWS_TYPES), "new": _int(0, 2), "corroborated": _int(0, 2), "price_story": {"type": "boolean"},
        "consensus": _enum(CONSENSUS), "vs_own_guidance": _enum(OWN_GUIDE), "magnitude": _int(0, 3),
        "specific": _int(0, 2), "surprise": _int(-3, 3), "p_up": _int(0, 100, 5)},
    "required": ["type", "new", "corroborated", "price_story", "consensus", "vs_own_guidance", "magnitude", "specific",
                 "surprise", "p_up"]}

SCHEMA_DOC = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "type": _enum(DOC_TYPES), "routine": {"type": "boolean"}, "material": _int(0, 3), "new": _int(0, 2),
        "corroborated": _int(0, 2), "consensus": _enum(CONSENSUS), "vs_own_guidance": _enum(OWN_GUIDE),
        "guide_chg_pct": _num_or_null(), "dilution": {"type": "boolean"}, "one_offs": {"type": "boolean"},
        "magnitude": _int(0, 3), "specific": _int(0, 2), "tone": _int(-2, 2), "surprise": _int(-3, 3),
        "p_up": _int(0, 100, 5)},
    "required": ["type", "routine", "material", "new", "corroborated", "consensus", "vs_own_guidance", "guide_chg_pct",
                 "dilution", "one_offs", "magnitude", "specific", "tone", "surprise", "p_up"]}

# The free headline-line format of {prior_news} / {news} and {prior_filings} (renderers below), and their caps.
NEWS_LINES = {"news": 40, "doc": 25}
FILING_LINES = 10
HEADLINE_CHARS = 160
PRIOR_DAYS = 30


def spec(kind: str) -> dict:
    """The request spec whose canonical JSON's SHA-256 names the R2 prompt version (as verdicts.Prompt.sha does)."""
    system, user, schema = (SYSTEM_NEWS, USER_NEWS, SCHEMA_NEWS) if kind == "news" else (SYSTEM_DOC, USER_DOC,
                                                                                        SCHEMA_DOC)
    return {"model": MODEL, "effort": EFFORT, "thinking": THINKING, "stream": STREAM, "max_tokens": MAX_TOKENS[kind],
            "system": system, "user": user, "format": schema,
            "render": {"news_lines": NEWS_LINES[kind], "filing_lines": FILING_LINES, "headline_chars": HEADLINE_CHARS,
                       "prior_days": PRIOR_DAYS}}


def sha(kind: str) -> str:
    return hashlib.sha256(json.dumps(spec(kind), sort_keys=True).encode("utf-8")).hexdigest()


def body(kind: str, user_text: str) -> dict:
    """The gateway body (gateway/lib/claude.mjs admit(): model, max_tokens, system, messages, thinking adaptive with a
    display, output_config {effort, format json_schema}, stream; NO temperature: Sonnet 5.5 refuses sampling values;
    no tools, no cache markers)."""
    s = spec(kind)
    return {"model": s["model"], "max_tokens": s["max_tokens"], "system": s["system"],
            "messages": [{"role": "user", "content": user_text}], "thinking": dict(THINKING),
            "output_config": {"effort": EFFORT, "format": {"type": "json_schema", "schema": s["format"]}},
            "stream": STREAM}


def line_news(knowable_et: str, source: str, headline: str) -> str:
    h = " ".join(str(headline or "").split())[:HEADLINE_CHARS]
    return f"{knowable_et} | {source or 'unknown'} | {h}"


def line_filing(knowable_et: str, items: list[str]) -> str:
    return f"{knowable_et} | SEC 8-K items {', '.join(items) if items else 'none listed'}"


def render_news(*, symbol, name, created_et, source, headline, summary, prior_news, prior_filings, read_day) -> str:
    return USER_NEWS.format(symbol=symbol, name=name or symbol, created_et=created_et, source=source or "unknown",
                            read_day=read_day,
                            headline=headline or "", summary=summary or "",
                            prior_news="\n".join(prior_news[:NEWS_LINES["news"]]) or "none",
                            prior_filings="\n".join(prior_filings[:FILING_LINES]) or "none")


def render_doc(*, name, ticker, items, acceptance_et, text, prior_news, read_day) -> str:
    return USER_DOC.format(name=name or ticker, ticker=ticker, items=", ".join(items), acceptance_et=acceptance_et,
                           read_day=read_day,
                           text=text[:16000], prior_news="\n".join(prior_news[:NEWS_LINES["doc"]]) or "none")


def parse(text: str, kind: str) -> tuple[str, dict | None]:
    """('ok', fields) when the answer is ONE JSON object that validates the schema exactly; else ('unparsed', None).
    Structured outputs make an invalid answer rare; the check stays (fail closed: unparsed is a missing read)."""
    b = text.strip()
    m = re.match(r"^```(?:json)?\s*(.*?)\s*```$", b, re.S)
    if m:
        b = m.group(1)
    try:
        data = json.loads(b)
    except ValueError:
        return "unparsed", None
    schema = SCHEMA_NEWS if kind == "news" else SCHEMA_DOC
    if not isinstance(data, dict) or set(data) != set(schema["required"]):
        return "unparsed", None
    for key, rule in schema["properties"].items():
        v = data[key]
        t = rule.get("type", "anyOf")
        if t == "integer":
            if type(v) is not int or v not in rule["enum"]:
                return "unparsed", None
        elif t == "boolean":
            if type(v) is not bool:
                return "unparsed", None
        elif t == "string":
            if v not in rule["enum"]:
                return "unparsed", None
        else:
            if v is not None and (type(v) not in (int, float) or v != v or abs(v) > 1e6):
                return "unparsed", None
    return "ok", data


# ------------------------------------------------------------------------------------------- deterministic set rules
LIQUID_ADV = 10_000_000.0          # score.py LIQUID_ADV: the replay's 5 bp impact tier (10 bp below it)
N_NEWS = 40                        # target R2 news reads a session for EVL-R2-ON's NEWS-ON window
CAP_NEWS = 64                      # hard cap of news reads a window a session (cost safety), in ask order
CAP_8K_ON = 8                      # 8K-ON: F8K(D) filings whose v1 PROMPT-DOC verdict is ok with score <= 1
N_NEWS_O1, CAP_8K_O1 = 24, 10      # ONLY IF the optional EVL-R2-O1 seat is registered (not recommended now)
Q_SESSIONS = 5
Q_DEFAULT = 0.5
K = 8                              # each consumer's picks a decision, every band


def h(window: str, day: str, cik: str) -> float:
    """The issuer's sample draw for a window of a session: uniform on [0, 1), independent of everything stored."""
    return int.from_bytes(hashlib.sha256(f"R2|{window}|{day}|{cik}".encode()).digest()[:8], "big") / 2 ** 64


def share(prior_counts: list[int], n_target: int = N_NEWS) -> float:
    """q_w(D) = min(1, n_target / the mean qualifying-issuer count of the window over its last Q_SESSIONS complete
    sessions) (outcome-free counts); Q_DEFAULT with no complete session yet."""
    c = [x for x in prior_counts[-Q_SESSIONS:] if x is not None]
    if not c:
        return Q_DEFAULT
    m = sum(c) / len(c)
    return 1.0 if m <= n_target else n_target / m


def consumer_pass(kind: str, f: dict) -> bool:
    """THE CONSUMERS' FILTER over one ok read (both programs; section P of the draft)."""
    if f["price_story" if kind == "news" else "routine"]:
        return False
    if kind == "news" and f["type"] in ("price_move", "commentary"):
        return False
    if kind == "doc" and (f["dilution"] or f["type"] == "investor_materials"):
        return False
    if f["vs_own_guidance"] in ("below", "lowered", "withdrawn") or f["consensus"] == "miss":
        return False
    return f["new"] >= 1 and f["surprise"] >= 1 and f["p_up"] >= 60


def consumer_key(f: dict, hh: float) -> tuple:
    """Higher first: p_up, surprise, magnitude, specific, corroborated; then the lower sample draw h."""
    return (f["p_up"], f["surprise"], f["magnitude"], f["specific"], f["corroborated"], -hh)

# ===================================== THE FROZEN REQUEST SPEC (docs/prereg/evl-10/fix1/r2_spec.py), VERBATIM: END

UTC = dt.timezone.utc
#: THE PIN (section 1.5; the captain's A144): the response `model` string the smoke test of section 1.7 returned for
#: both schemas. An answer whose model string differs is stored `refused` and R2 asks nothing more for good.
PIN = "claude-sonnet-5-5"
#: Section 1.1's two request specs, named by the SHA-256 of their canonical spec (`sha(kind)`, recomputed by a test).
SHAS = {"news": "a82396145a28dd4d98d6878e515cc26c26fd70c6c29f2642d4e1c4241642d694",
        "doc": "127c19f36f3811afaf4401c35e7620618a27ca0eb32795d0b19ba45a87522c5b"}
#: The scheduler's file key and the ON window's name in the hash draw (`h(WINDOW, D, cik)`: sha256("R2|ON|" + D + "|"
#: + cik), section 1.4).
FILE = "evl10"
WINDOW = "ON"
KINDS = ("news", "doc")
#: Section 1.5: each call's WORST-CASE HOLD (evl10/fix1/cost_fix1.out `hold_worst_case`: the body's max size and its
#: max_tokens at Sonnet 5.5's prices with geo us 1.1), what a lost or unpriced call counts at.
HOLD_USD = {"news": 0.0552, "doc": 0.1036}
#: R2_LINE = max(0, min($0.75, L - 1.5 x V - $0.25)) (section 1.5 (a)): its cap, v1's head room over its heaviest recent
#: day, the births' night cap (league/events/births.py `NIGHT_USD`, held equal by a test) and V's trailing UTC days.
LINE_MAX = Decimal("0.75")
V1_HEAD = Decimal("1.5")
BIRTHS_NIGHT = Decimal("0.25")
V_DAYS = 7
#: A verdict whose cost the gateway did not state (league/events/house.py `VERDICT_USD_UNKNOWN`, held equal by a test).
VERDICT_USD_UNKNOWN = 0.01
#: Section 1.4's BUYABLE: 1.25 x D's previous close <= 0.05 x E_prev (a fixed constant of this file, never a money row).
BUYABLE_SHARE = 0.05
LIMIT_MULTIPLE = 1.25
#: Section 1.4's 8K-ON: the filing's TEXT has at least this many characters.
DOC_MIN_CHARS = 200
#: Section 2.2's TAU (D's close - 20 minutes) and section 1.5's asks: from 07:30:00 ET until 30 seconds before tau.
TAU_BEFORE_CLOSE = dt.timedelta(minutes=20)
ASK_STOP = dt.timedelta(seconds=30)
START_AT = dt.time(7, 30)
#: Section 1.4's COMPLETE: no gap over 5 minutes between consecutive stored scan times, counting 07:30:00 ET as the first
#: and tau - 30 s as the last; the sessions looked back over for the last `Q_SESSIONS` complete ones.
COMPLETE_GAP = dt.timedelta(minutes=5)
COMPLETE_LOOKBACK = 60
#: Section 1.5's SCHEMA STOP (two consecutive sessions each with at least 10 answered reads, unparsed + cut at least 10%
#: of them) and DAY STOP (three gateway 4xx answers in a UTC day); the alarm `reader_missing` (under 85% of chosen reads
#: answered by tau two sessions running, section 11).
SCHEMA_MIN, SCHEMA_SHARE, SCHEMA_SESSIONS = 10, 0.10, 2
DAY_4XX = 3
MISSING_SHARE, MISSING_SESSIONS = 0.85, 2
#: Section 3: at most three runs over the id's life; c10 = 0.13 a run (hundredths, PREREG-EVL-6's frozen charge).
RUNS_MAX = 3
CHARGE_HUNDREDTHS = 13
#: The statuses of a `reads2` row (section 1.3), the ones that are an answer, and the row ahead of a call (`ASKED`: its
#: answered_at the asking time and its usd the hold, so the day's spend counts it; a row a process left behind is
#: closed `lost` at its hold once no call can still be streaming, `STALE_ASKED`).
OK, UNPARSED, REFUSED, CUT, LOST, ASKED = "ok", "unparsed", "refused", "cut", "lost", "asked"
ANSWERED = (OK, UNPARSED, REFUSED, CUT)
STALE_ASKED = dt.timedelta(seconds=LIMIT_S + GAP_S)
#: The scheduler slot's receipt job (scheduler.TABLE's row `close-r2`): `decide-close-r2:<D>`.
JOB = "decide-close-r2"
#: The meta keys this file writes (the lane's store): the share q of D (fixed at D's first scan, which comes before its
#: first ask, from the same complete sessions), R2_LINE of a UTC day (fixed at its first ask), R2's stop for good,
#: the UTC day's gateway 4xx count, the asks R2's line refused, the days v1 spent over 1.5 V, a session that reached
#: the cap of 64 news reads, and a run of EVL-R2-ON refused for good (section 3).
Q_KEY = "evl10:q:{day}"
LINE_KEY = "evl10:line:{utc}"
STOP_KEY = "evl10:stop"
FOURXX_KEY = "evl10:4xx:{utc}"
LINE_REFUSED_KEY = "evl10:line-refused:{utc}"
V1_RESERVE_KEY = "evl10:v1-reserve:{utc}"
CAP_KEY = "evl10:cap:{day}"
NORUN_KEY = "evl10:norun:{program}:{version}:{n}"
#: An event whose read cannot be rendered from the store (its row or its TEXT document missing): skipped for the session
#: (meta, {day: [events]}), a missing read like any other (the reading that asks less), so it never holds the queue.
UNRENDERED_KEY = "evl10:unrendered:{day}"
#: FEATURES-R2 v1 (section 1.6): its version and its 21 columns' names, in their frozen order.
FEATURES_VERSION = 1
FEATURE_COLUMNS = ("kind_doc", "new", "corroborated", "magnitude", "specific", "surprise", "p_up", "price_story",
                   "routine", "material", "tone", "dilution", "one_offs", "consensus_beat", "consensus_miss",
                   "guide_up", "guide_down", "analyst", "earnings_guidance", "prior_n", "r2_missing")


# ------------------------------------------------------------------------------------------------------------ times
def registered() -> dt.datetime | None:
    """REGISTERED_AT_10 as a time (None while unpinned: nothing of this file runs)."""
    return None if P.REGISTERED_AT_10 is None else S.parse_iso(P.REGISTERED_AT_10)


def pinned() -> bool:
    return P.REGISTERED_AT_10 is not None and bool(P.reader2_rows())


def tau(session: C.Session) -> dt.datetime:
    """Section 2.2's TAU: D's close - 20 minutes (15:40:00 ET on a full day; on an early close, the close - 20 minutes)."""
    return session.close_at - TAU_BEFORE_CLOSE


def ask_until(session: C.Session) -> dt.datetime:
    """The end of R2's asks and scans of D (section 1.5): 30 seconds before tau."""
    return tau(session) - ASK_STOP


def start_of(session: C.Session) -> dt.datetime:
    """The start of R2's asks and scans of D (section 1.5): 07:30:00 ET of D."""
    return session.at(START_AT)


def utc_day(now: dt.datetime) -> tuple[dt.date, str, str]:
    """The UTC day of `now` (the lane's line's day, every line's) and its [00:00, 24:00) UTC as the store's strings."""
    day = now.astimezone(UTC).date()
    start = dt.datetime.combine(day, dt.time(0, 0), tzinfo=UTC)
    return day, S.iso(start), S.iso(start + dt.timedelta(days=1))


def _et(moment: dt.datetime) -> str:
    return moment.astimezone(C.NY).strftime("%Y-%m-%d %H:%M")


def _iso(value: Any) -> dt.datetime | None:
    try:
        return S.parse_iso(str(value))
    except (TypeError, ValueError):
        return None


def _table(db: Any, name: str) -> bool:
    return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def _meta(store: Any, key: str) -> str | None:
    row = store.db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return None if row is None else str(row[0])


def _meta_json(store: Any, key: str) -> dict[str, Any] | None:
    raw = _meta(store, key)
    if raw is None:
        return None
    try:
        got = json.loads(raw)
    except ValueError:
        return {"unreadable": raw[:200]}
    return got if isinstance(got, dict) else {"value": got}


# ------------------------------------------------------------------------------------------------- what qualifies
def e_prev(store: Any, day: dt.date) -> float | None:
    """E_prev (section 1.4): the account equity at P's close as score.py reads it (`equity_on`), None when unread."""
    from . import score as SC

    prior = C.previous(store, day, 1)
    if not prior:
        return None
    got = SC.equity_on(store, prior[-1].day)
    return got if got is not None and math.isfinite(got) and got > 0 else None


def universe_at(store: Any, day: dt.date, at: dt.datetime, *, strict: bool = False) -> dict[str, dict[str, Any]]:
    """{cik: D's universe row} of every issuer whose LIVE-rule eligibility for D is decided and eligible AS STORED AT
    `at` (the eligibility row's decided_at at or before `at`; before it when `strict`, the decision's "stored before
    tau"), the highest ADV when a CIK has two (league/events/book.py `universe_rows`' reading)."""
    op = "<" if strict else "<="
    out: dict[str, dict[str, Any]] = {}
    for r in store.db.execute("SELECT u.* FROM universe u JOIN eligibility e ON e.day=u.day AND e.cik=u.cik AND "
                              f"e.symbol=u.symbol WHERE u.day=? AND e.rule='live' AND e.eligible=1 AND e.decided_at{op}?",
                              (day.isoformat(), S.iso(at))):
        row = dict(r)
        have = out.get(str(row["cik"]))
        if have is None or float(row.get("adv20") or 0) > float(have.get("adv20") or 0):
            out[str(row["cik"])] = row
    return out


def liquid(row: Mapping[str, Any]) -> bool:
    """LIQUID (section 1.4): D's universe row's adv20 >= $10,000,000 (score.py `LIQUID_ADV`)."""
    try:
        return float(row.get("adv20") or 0.0) >= LIQUID_ADV
    except (TypeError, ValueError):
        return False


def buyable(row: Mapping[str, Any], equity: float | None) -> bool:
    """BUYABLE (section 1.4): 1.25 x D's universe row's prev_close <= 0.05 x E_prev (one whole share at the limit fits
    goal V3's learning position); never with no E_prev or no previous close (fail closed)."""
    try:
        prev = float(row.get("prev_close"))
    except (TypeError, ValueError):
        return False
    if equity is None or not math.isfinite(prev) or prev <= 0:
        return False
    return LIMIT_MULTIPLE * prev <= BUYABLE_SHARE * float(equity)


def _stored_by(row: Mapping[str, Any], at: dt.datetime, store: Any) -> bool:
    """An event row stored at or before `at` (league/events/book.py `_stored_before`: an article when it was read, a
    filing when its documents were fetched)."""
    from .book import _stored_before

    return _stored_before(row, at, store)


def _answered_by(store: Any, event: str, kind: str, at: dt.datetime) -> Mapping[str, Any] | None:
    """The stored v1 verdict (PROMPT-NEWS or PROMPT-DOC) of `event` when it is `ok` and was answered at or before `at`."""
    got = V.stored(store, event, V.PROMPTS[kind])
    if not got or got.get("status") != "ok" or got.get("score") is None:
        return None
    when = _iso(got.get("answered_at"))
    return got if when is not None and when <= at else None


def _excluded_at(store: Any, day: dt.date, at: dt.datetime, uni: Mapping[str, Mapping[str, Any]],
                 all8k: Sequence[Mapping[str, Any]]) -> set[str]:
    """EXCLUDED on D as stored at `at` (PREREG-EVL-4 section 1.1): an issuer in ERN(D) (an 8-K of D's close window with
    item 2.02) or in DAY(D) (a day-news article naming its eligible ticker)."""
    by_symbol = {str(r["symbol"]).upper(): str(cik) for cik, r in uni.items()}
    day_articles = [dict(a) | {"cik": by_symbol.get(str(a.get("symbol") or "").upper())}
                    for a in P.news_rows(store, *P.day_news_window(store, day)) if _stored_by(a, at, store)]

    def symbol_of(cik: str) -> str | None:
        row = uni.get(str(cik))
        return None if row is None else str(row["symbol"]).upper()
    return P.excluded(all8k, day_articles, symbol_of)


def qualify(store: Any, day: dt.date, at: dt.datetime) -> list[dict[str, Any]]:
    """THE EVENTS OF D THAT QUALIFY AS STORED AT `at` (section 1.4), oldest knowable first: [{event, kind, cik, symbol,
    v1_score, knowable_at, row, uni}]. Each needs its issuer's live eligibility for D decided and eligible, LIQUID,
    BUYABLE and the event knowable after REGISTERED_AT_10, stored and knowable by `at`; NEWS-ON: a DAY(D) article
    (EVL-NEWS-READ-ON's family: single-symbol, the eligible ticker, knowable after 09:00 ET of D and at or before T29,
    PREREG-EVL-1 section 3's non-live exclusion) with a stored `ok` PROMPT-NEWS verdict of score >= 2; 8K-ON: an F8K(D)
    filing (form exactly 8-K; items 1.01, 2.01, 7.01 or 8.01 and no 2.02; knowable in D's close window) of an issuer
    not EXCLUDED on D, whose TEXT has at least 200 characters and whose stored PROMPT-DOC verdict is `ok` with score
    <= 1. Nothing with no E_prev (fail closed)."""
    reg = registered()
    if reg is None or C.session(store, day) is None or not C.previous(store, day, 1):
        return []
    equity = e_prev(store, day)
    if equity is None:
        return []
    uni = universe_at(store, day, at)
    fit = {cik for cik, row in uni.items() if liquid(row) and buyable(row, equity)}
    by_symbol = {str(r["symbol"]).upper(): str(cik) for cik, r in uni.items()}
    out: list[dict[str, Any]] = []
    for a in P.news_rows(store, *P.day_news_window(store, day)):
        knowable = _iso(a.get("knowable_at"))
        if knowable is None or knowable <= reg or knowable > at or not _stored_by(a, at, store):
            continue
        cik = by_symbol.get(str(a.get("symbol") or "").upper())
        if cik is None or cik not in fit:
            continue
        event = f"news:{a['id']}"
        got = _answered_by(store, event, "news", at)
        if got is None or int(got["score"]) < 2:
            continue
        out.append({"event": event, "kind": "news", "cik": cik, "symbol": str(uni[cik]["symbol"]).upper(),
                    "v1_score": int(got["score"]), "knowable_at": S.iso(knowable), "row": dict(a), "uni": uni[cik]})
    lo, hi = P.close_window(store, day)
    all8k = [r for r in P.filings_window(store, "8-K", lo, hi) if _stored_by(r, at, store)]
    skip = _excluded_at(store, day, at, uni, all8k)
    for r in P.family_8k(all8k):
        cik = str(r.get("cik") or "")
        knowable = _iso(r.get("knowable_at"))
        if str(r.get("form")) != "8-K" or cik not in fit or cik in skip or knowable is None or knowable <= reg or \
                knowable > at:
            continue
        if not r.get("text_sha") or int(r.get("text_len") or 0) < DOC_MIN_CHARS:
            continue
        event = f"8k:{r['accession']}"
        got = _answered_by(store, event, "doc", at)
        if got is None or int(got["score"]) > 1:
            continue
        out.append({"event": event, "kind": "doc", "cik": cik, "symbol": str(uni[cik]["symbol"]).upper(),
                    "v1_score": int(got["score"]), "knowable_at": S.iso(knowable), "row": dict(r), "uni": uni[cik]})
    return sorted(out, key=lambda c: (c["knowable_at"], c["event"]))


# ------------------------------------------------------------------------------------------- the share and COMPLETE
def complete(times: Sequence[dt.datetime], session: C.Session) -> bool:
    """Section 1.4's COMPLETE (the second fix round's F17): the session's stored scan times, with 07:30:00 ET counted as
    the first time and tau - 30 s as the last, have no gap over 5 minutes between consecutive times."""
    first, last = start_of(session), ask_until(session)
    inside = sorted(t for t in times if first <= t <= last)
    marks = [first, *inside, last]
    return all(b - a <= COMPLETE_GAP for a, b in zip(marks, marks[1:]))


def scans_of(store: Any, day: dt.date) -> list[dt.datetime]:
    return [t for t in (_iso(r[0]) for r in store.db.execute("SELECT scanned_at FROM r2_scan WHERE day=? ORDER BY "
                                                             "scanned_at", (day.isoformat(),))) if t is not None]


def news_count(store: Any, day: dt.date) -> int:
    """The number of issuers with a qualifying NEWS-ON article of session `day` (`r2_qual`)."""
    row = store.db.execute("SELECT COUNT(DISTINCT cik) FROM r2_qual WHERE window=? AND day=? AND kind='news'",
                           (WINDOW, day.isoformat())).fetchone()
    return int(row[0] or 0)


def share_of(store: Any, day: dt.date) -> tuple[float, list[str]]:
    """q(D) (section 1.4): `share` over the counts of the last Q_SESSIONS sessions before D whose NEWS-ON window is
    COMPLETE in `r2_scan` (Q_DEFAULT with none); (q, the sessions read)."""
    days: list[tuple[str, int]] = []
    for s in reversed(C.previous(store, day, COMPLETE_LOOKBACK)):
        if complete(scans_of(store, s.day), s):
            days.append((s.day.isoformat(), news_count(store, s.day)))
            if len(days) >= Q_SESSIONS:
                break
    days.reverse()
    return share([n for _, n in days]), [d for d, _ in days]


# ---------------------------------------------------------------------------------------------------- the scans
def _qual_rows(store: Any, day: dt.date) -> list[dict[str, Any]]:
    return [dict(r) for r in store.db.execute("SELECT * FROM r2_qual WHERE window=? AND day=? ORDER BY qualified_at, "
                                              "rowid", (WINDOW, day.isoformat()))]


def choose(have: Sequence[Mapping[str, Any]], new: Sequence[Mapping[str, Any]], q: float, day: dt.date
           ) -> list[tuple[Mapping[str, Any], float, bool]]:
    """CHOSEN (section 1.4) for the events that qualify at this scan (`new`, in qualification order), after the rows of
    D already written (`have`): [(event, h, chosen)]. NEWS-ON: an issuer is read for (i) its first qualifying article
    when h < q, or else its first qualifying article with v1 score 3, and (ii) once more, for its first later
    qualifying article whose v1 score is strictly higher than the article read in (i); at most 2 news reads an issuer
    and 64 a session, in qualification order. 8K-ON: an issuer's first qualifying filing, at most 8 a session."""
    first: dict[str, bool] = {}            # issuer -> it has a qualifying article on record (any score)
    first3: dict[str, bool] = {}           # issuer -> it has a qualifying score-3 article on record
    read: dict[str, list[int]] = {}        # issuer -> the v1 scores of its chosen news reads, in order
    filed: set[str] = set()                # issuers with a qualifying filing on record
    news_n = doc_n = 0
    for r in have:
        cik = str(r["cik"])
        if r["kind"] == "news":
            first[cik] = True
            if int(r["v1_score"] or 0) == 3:
                first3[cik] = True
            if r["chosen"]:
                read.setdefault(cik, []).append(int(r["v1_score"] or 0))
                news_n += 1
        else:
            filed.add(cik)
            if r["chosen"]:
                doc_n += 1
    out = []
    for c in new:
        cik, score = str(c["cik"]), int(c["v1_score"])
        hh = h(WINDOW, day.isoformat(), cik)
        chosen = False
        if c["kind"] == "news":
            mine = read.get(cik, [])
            if news_n < CAP_NEWS:
                if not mine:
                    chosen = (hh < q and not first.get(cik)) or (score == 3 and not first3.get(cik))
                elif len(mine) == 1 and score > mine[0]:
                    chosen = True
            first[cik] = True
            if score == 3:
                first3[cik] = True
            if chosen:
                read.setdefault(cik, []).append(score)
                news_n += 1
        else:
            if cik not in filed and doc_n < CAP_8K_ON:
                chosen = True
                doc_n += 1
            filed.add(cik)
        out.append((c, hh, chosen))
    return out


def scan(store: S.Store, day: dt.date, now: dt.datetime) -> dict[str, Any]:
    """ONE QUALIFICATION SCAN of D at `now` (section 1.4), in one transaction: q fixed at D's first scan (meta `Q_KEY`),
    every event that qualifies now and is not yet in `r2_qual` written once with its h, q and CHOSEN, and the scan's
    time in `r2_scan`. Returns {qualified, chosen, q, capped}."""
    with store.tx() as db:
        raw = _meta(store, Q_KEY.format(day=day.isoformat()))
        if raw is None:
            q, read = share_of(store, day)
            db.execute("INSERT OR IGNORE INTO meta(key, value) VALUES(?, ?)",
                       (Q_KEY.format(day=day.isoformat()), json.dumps({"q": q, "sessions": read, "at": S.iso(now)},
                                                                     sort_keys=True)))
        else:
            q = float(json.loads(raw)["q"])
        have = _qual_rows(store, day)
        known = {str(r["event"]) for r in have}
        new = [c for c in qualify(store, day, now) if c["event"] not in known]
        picked = choose(have, new, q, day)
        for c, hh, chosen in picked:
            db.execute("INSERT OR IGNORE INTO r2_qual(window, day, cik, event, kind, qualified_at, v1_score, h, q, chosen) "
                       "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                       (WINDOW, day.isoformat(), c["cik"], c["event"], c["kind"], S.iso(now), c["v1_score"], hh, q,
                        int(chosen)))
        capped = False
        if any(c["kind"] == "news" and not chosen for c, _, chosen in picked):
            n = db.execute("SELECT COUNT(*) FROM r2_qual WHERE window=? AND day=? AND kind='news' AND chosen=1",
                           (WINDOW, day.isoformat())).fetchone()[0]
            if int(n) >= CAP_NEWS:
                capped = True
                db.execute("INSERT OR IGNORE INTO meta(key, value) VALUES(?, ?)",
                           (CAP_KEY.format(day=day.isoformat()), S.iso(now)))
        db.execute("INSERT OR IGNORE INTO r2_scan(day, scanned_at) VALUES(?, ?)", (day.isoformat(), S.iso(now)))
    return {"qualified": len(picked), "chosen": sum(1 for _, _, x in picked if x), "q": q, "capped": capped}


def next_due(store: Any, day: dt.date, session: C.Session) -> dict[str, Any] | None:
    """THE NEXT CALL DUE of D (section 1.5): the earliest chosen `r2_qual` row (8K-ON and NEWS-ON interleaved by
    qualified_at) with no `reads2` row for its request spec and the model, that qualified no later than 30 seconds
    before tau and whose read could be rendered (`UNRENDERED_KEY`); None when every chosen event is read."""
    last = S.iso(ask_until(session))
    raw = _meta(store, UNRENDERED_KEY.format(day=day.isoformat()))
    skip = set(json.loads(raw)) if raw else set()
    for r in store.db.execute("SELECT * FROM r2_qual WHERE window=? AND day=? AND chosen=1 AND qualified_at<=? ORDER BY "
                              "qualified_at, rowid", (WINDOW, day.isoformat(), last)):
        row = dict(r)
        if str(row["event"]) in skip:
            continue
        kind = str(row["kind"])
        if store.db.execute("SELECT 1 FROM reads2 WHERE event=? AND prompt_sha=? AND model=?",
                            (row["event"], sha(kind), MODEL)).fetchone() is None:
            return row
    return None


# ------------------------------------------------------------------------------------------------- what a read sees
def _news_lines(store: Any, symbol: str, lo: dt.datetime, hi: dt.datetime, asked: dt.datetime, *, skip: str | None,
                cap: int) -> tuple[list[str], list[str]]:
    """Stored articles whose symbols include `symbol` (any number of symbols), knowable in [lo, hi) and received by the
    ask, the item itself excluded, newest first, at most `cap`: (lines, ids)."""
    lines, ids = [], []
    for r in store.db.execute("SELECT id, knowable_at, received_at, source, headline, symbols FROM news WHERE "
                              "knowable_at>=? AND knowable_at<? ORDER BY knowable_at DESC, id DESC",
                              (S.iso(lo), S.iso(hi))):
        if skip is not None and str(r["id"]) == skip:
            continue
        received = _iso(r["received_at"])
        if received is None or received > asked:
            continue
        try:
            symbols = [str(x).upper() for x in json.loads(r["symbols"] or "[]")]
        except (TypeError, ValueError):
            continue
        if symbol.upper() not in symbols:
            continue
        lines.append(line_news(_et(S.parse_iso(str(r["knowable_at"]))) + " ET", r["source"], r["headline"]))
        ids.append(str(r["id"]))
        if len(lines) >= cap:
            break
    return lines, ids


def _filing_lines(store: Any, cik: str, lo: dt.datetime, hi: dt.datetime, asked: dt.datetime, *,
                  skip: str | None = None) -> tuple[list[str], list[str]]:
    """The issuer's stored form 8-K filings knowable in [lo, hi) and stored by the ask, newest first, at most 10."""
    lines, ids = [], []
    for r in store.db.execute("SELECT * FROM filings WHERE form='8-K' AND status='fetched' AND cik=? AND knowable_at>=? "
                              "AND knowable_at<? ORDER BY knowable_at DESC, accession DESC", (str(cik), S.iso(lo), S.iso(hi))):
        row = dict(r)
        if skip is not None and str(row["accession"]) == skip:
            continue
        if not _stored_by(row, asked, store):
            continue
        lines.append(line_filing(_et(S.parse_iso(str(row["knowable_at"]))) + " ET", sorted(P.items_of(row))))
        ids.append(str(row["accession"]))
        if len(lines) >= FILING_LINES:
            break
    return lines, ids


def render(store: Any, qual: Mapping[str, Any], day: dt.date, asked: dt.datetime) -> tuple[str, dict[str, Any]]:
    """THE USER TEXT OF ONE READ (section 1.2; `render_news` / `render_doc`) from rows stored before the ask, and its
    priors {news: [ids], filings: [accessions], n: prior_n (the earlier-news lines given)}."""
    event, kind, cik = str(qual["event"]), str(qual["kind"]), str(qual["cik"])
    uni = store.db.execute("SELECT * FROM universe WHERE day=? AND cik=? ORDER BY adv20 DESC LIMIT 1",
                           (day.isoformat(), cik)).fetchone()
    if uni is None:
        raise LookupError(f"no universe row of {cik} for {day}")
    uni = dict(uni)
    symbol = str(uni["symbol"]).upper()
    if kind == "news":
        ident = event.split(":", 1)[1]
        a = store.db.execute("SELECT * FROM news WHERE id=?", (ident,)).fetchone()
        if a is None:
            raise LookupError(event)
        a = dict(a)
        k = S.parse_iso(str(a["knowable_at"]))
        news, news_ids = _news_lines(store, symbol, k - dt.timedelta(days=PRIOR_DAYS), k, asked, skip=ident,
                                     cap=NEWS_LINES["news"])
        filings, filing_ids = _filing_lines(store, cik, k - dt.timedelta(days=PRIOR_DAYS), k, asked)
        text = render_news(symbol=symbol, name=uni.get("name"), created_et=_et(S.parse_iso(str(a["created_at"]))),
                           source=a.get("source"), headline=a.get("headline"), summary=a.get("summary"),
                           prior_news=news, prior_filings=filings, read_day=day.isoformat())
        return text, {"news": news_ids, "filings": filing_ids, "n": len(news)}
    accession = event.split(":", 1)[1]
    f = store.db.execute("SELECT * FROM filings WHERE accession=?", (accession,)).fetchone()
    if f is None:
        raise LookupError(event)
    f = dict(f)
    k = S.parse_iso(str(f["knowable_at"]))
    body_text = store.get_document(str(f["text_sha"])).decode("utf-8")
    news, news_ids = _news_lines(store, symbol, k - dt.timedelta(days=PRIOR_DAYS), asked, asked, skip=None,
                                 cap=NEWS_LINES["doc"])
    text = render_doc(name=uni.get("name") or f.get("company") or "", ticker=symbol, items=sorted(P.items_of(f)),
                      acceptance_et=_et(S.parse_iso(str(f["accepted_at"]))), text=body_text, prior_news=news,
                      read_day=day.isoformat())
    return text, {"news": news_ids, "filings": [], "n": len(news)}


# ------------------------------------------------------------------------------------------------- the lines
def usd_between(db: Any, lo: str, hi: str) -> float:
    """R2's dollars answered in [lo, hi) (`reads2`: each row at its stored cost; a row with none, or still in flight
    (`ASKED`), at its worst-case hold), 0 when the store has no such table. The lane's line (league/events/house.py
    `_spend_today`), the budget's measured lane spend, the site and the daily report count R2 through this."""
    if not _table(db, "reads2"):
        return 0.0
    row = db.execute("SELECT COALESCE(SUM(COALESCE(usd, CASE WHEN prompt_sha=? THEN ? ELSE ? END)), 0) FROM reads2 WHERE "
                     "answered_at>=? AND answered_at<?", (sha("news"), HOLD_USD["news"], HOLD_USD["doc"], lo, hi)
                     ).fetchone()
    return float(row[0] or 0.0)


def usd_all(db: Any) -> float:
    """Every R2 dollar on record (`usd_between` over all time)."""
    return usd_between(db, "0000", "9999")


def v1_heaviest(store: Any, now: dt.datetime) -> Decimal:
    """V (section 1.5 (a)): the heaviest UTC day of PROMPT-NEWS and PROMPT-DOC verdict dollars over the trailing
    `V_DAYS` UTC days to `now`'s, today's part included (verdicts only; an unstated cost at `VERDICT_USD_UNKNOWN`)."""
    day, _, hi = utc_day(now)
    lo = S.iso(dt.datetime.combine(day - dt.timedelta(days=V_DAYS - 1), dt.time(0, 0), tzinfo=UTC))
    rows = store.db.execute("SELECT substr(answered_at, 1, 10) AS d, COALESCE(SUM(COALESCE(usd, ?)), 0) AS usd FROM "
                            "verdicts WHERE answered_at>=? AND answered_at<? GROUP BY d", (VERDICT_USD_UNKNOWN, lo, hi))
    best = Decimal(0)
    for r in rows:
        best = max(best, Decimal(str(round(float(r["usd"] or 0.0), 6))))
    return best


def r2_line(L: Decimal | float | str, V_: Decimal | float | str) -> Decimal:
    """R2_LINE = max(0, min($0.75, L - 1.5 x V - $0.25)) (section 1.5 (a)), ROUNDED DOWN TO THE CENT (the reading that
    asks less: at V = $1.83 and L = $3 the formula leaves half a cent, read as $0, as the frozen text's table reads it)."""
    raw = Decimal(str(L)) - V1_HEAD * Decimal(str(V_)) - BIRTHS_NIGHT
    return max(Decimal(0), min(LINE_MAX, raw)).quantize(Decimal("0.01"), rounding=ROUND_FLOOR)


def lane_spend(store: Any, now: dt.datetime) -> float:
    """THE LANE'S WHOLE SPEND of `now`'s UTC day: its verdicts (an unstated cost at `VERDICT_USD_UNKNOWN`), R3's births
    call (league/events/house.py `birth_usd`) and R2's reads (`usd_between`), as the lane's line counts them."""
    from .house import birth_usd

    _, lo, hi = utc_day(now)
    row = store.db.execute("SELECT COALESCE(SUM(COALESCE(usd, ?)), 0) FROM verdicts WHERE answered_at>=? AND answered_at<?",
                           (VERDICT_USD_UNKNOWN, lo, hi)).fetchone()
    return float(row[0] or 0.0) + birth_usd(store.db, lo, hi) + usd_between(store.db, lo, hi)


def line_of_day(store: S.Store, now: dt.datetime, lane_line: Callable[[dt.datetime], Mapping[str, Any]]) -> dict[str, Any]:
    """R2_LINE of `now`'s UTC day, FIXED AT THE DAY'S FIRST ASK (meta `LINE_KEY`): {line, L, V, source, at}. `lane_line`
    is the lane's own line (league/events/house.py `verdict_line`: the lower of `events.verdict_usd_day` and the
    budget's `lane_allowance`); a line that cannot be read is 0 (FAIL CLOSED)."""
    day, _, _ = utc_day(now)
    key = LINE_KEY.format(utc=day.isoformat())
    have = _meta_json(store, key)
    if have is not None and "line" in have:
        return have
    try:
        got = lane_line(now)
        L = Decimal(str(round(float(got["usd_day"]), 6)))
        source = str(got.get("source") or "")
    except Exception as exc:  # noqa: BLE001 - no line read is no ask
        L, source = Decimal(0), f"the lane's line could not be read ({type(exc).__name__})"
    V_ = v1_heaviest(store, now)
    rec = {"line": str(r2_line(L, V_)), "L": str(L), "V": str(V_), "source": source[:200], "at": S.iso(now)}
    store.db.execute("INSERT OR IGNORE INTO meta(key, value) VALUES(?, ?)", (key, json.dumps(rec, sort_keys=True)))
    return _meta_json(store, key) or rec


def line_refusal(store: S.Store, now: dt.datetime, kind: str, line: Mapping[str, Any], root: Any) -> str | None:
    """Why the call is not sent now (section 1.5), None when it may be: (a) R2's dollars of the UTC day plus the call's
    hold over R2_LINE; (b) a cap hold (league/ops/budget.py `cap_hold`) names the day; (c) the lane's whole spend of
    the day plus the hold over the lane's line L (R2's dollars are inside the lane's line: the reading that asks less,
    so no R2 dollar can take the lane past its line on a day v1 spent more than 1.5 V)."""
    hold = HOLD_USD[kind]
    _, lo, hi = utc_day(now)
    mine = usd_between(store.db, lo, hi)
    cap = Decimal(str(line["line"]))
    if Decimal(str(round(mine + hold, 6))) > cap:
        return f"R2_LINE: ${mine:.4f} today + the call's ${hold:.4f} hold over the day's ${cap} (L ${line['L']}, V ${line['V']})"
    try:
        from ..ops import budget as B

        held = B.cap_hold(root, now.timestamp())
    except Exception as exc:  # noqa: BLE001 - an unreadable hold is a hold (fail closed)
        held = {"why": f"unreadable ({type(exc).__name__})"}
    if held is not None:
        return "the cap breach hold names the day (league/ops/budget.py cap_hold)"
    whole = lane_spend(store, now)
    if Decimal(str(round(whole + hold, 6))) > Decimal(str(line["L"])):
        return f"the lane's line: ${whole:.4f} spent today + the call's ${hold:.4f} hold over L ${line['L']}"
    return None


# --------------------------------------------------------------------------------------------------- the stops
def stopped(store: Any) -> dict[str, Any] | None:
    """R2'S STOP FOR GOOD (section 1.5), or None: THE PIN or THE SCHEMA STOP (meta `STOP_KEY`, written once), or SPEND
    FOLLOWS THE SEAT (EVL-R2-ON retired, the lane's pivot included, or a shadow record only because its run could not
    start: meta `NORUN_KEY`)."""
    got = _meta_json(store, STOP_KEY)
    if got is not None:
        return got
    from . import bands as BA

    try:
        band = BA.bands(store).get((P.R2_ON, 1), "learning")
    except Exception as exc:  # noqa: BLE001 - an unreadable band asks nothing (the reading that asks less)
        return {"kind": "seat", "why": f"EVL-R2-ON's band could not be read ({type(exc).__name__})", "for_good": False}
    if band == "retired":
        return {"kind": "seat", "why": "EVL-R2-ON is retired: R2 asks nothing more (SPEND FOLLOWS THE SEAT)"}
    row = store.db.execute("SELECT key FROM meta WHERE key LIKE ? LIMIT 1",
                           (NORUN_KEY.format(program=P.R2_ON, version=1, n="%"),)).fetchone()
    if row is not None:
        return {"kind": "seat", "why": f"EVL-R2-ON is a shadow record only: its run could not start ({row[0]})"}
    return None


def stop_for_good(store: S.Store, kind: str, why: str, now: dt.datetime) -> None:
    store.db.execute("INSERT OR IGNORE INTO meta(key, value) VALUES(?, ?)",
                     (STOP_KEY, json.dumps({"kind": kind, "why": why[:300], "at": S.iso(now)}, sort_keys=True)))


def fourxx(store: Any, now: dt.datetime) -> int:
    raw = _meta(store, FOURXX_KEY.format(utc=utc_day(now)[0].isoformat()))
    try:
        return int(raw or 0)
    except ValueError:
        return DAY_4XX


def schema_failing(store: Any) -> list[str]:
    """THE SCHEMA STOP's sessions (section 1.5): the last two consecutive sessions, each with at least 10 answered reads,
    in which unparsed + cut were at least 10% of the answered reads ([] when no such pair is on record)."""
    per: dict[str, list[int]] = {}
    for r in store.db.execute("SELECT day, status, COUNT(*) AS n FROM reads2 WHERE status IN (?, ?, ?, ?) GROUP BY day, "
                              "status", ANSWERED):
        got = per.setdefault(str(r["day"]), [0, 0])
        got[0] += int(r["n"])
        if r["status"] in (UNPARSED, CUT):
            got[1] += int(r["n"])

    def bad(day: str) -> bool:
        n, b = per.get(day, (0, 0))
        return n >= SCHEMA_MIN and b >= SCHEMA_SHARE * n
    for day in sorted(per, reverse=True):
        if not bad(day):
            continue
        prior = C.previous(store, dt.date.fromisoformat(day), 1)
        if prior and bad(prior[-1].day.isoformat()):
            return [prior[-1].day.isoformat(), day]
    return []


# --------------------------------------------------------------------------------------------------------- the ask
def _cost(gw: Any) -> tuple[float | None, bool]:
    from . import gw as G

    headers = getattr(gw, "last_headers", {}) or {}
    raw = headers.get(G.COST_HEADER)
    try:
        usd = float(raw) if raw not in (None, "") else None
    except (TypeError, ValueError):
        usd = None
    if usd is not None and not (math.isfinite(usd) and usd >= 0):
        usd = None
    known = usd is not None and str(headers.get(G.COST_KNOWN_HEADER, "true")).lower() != "false"
    return usd, known


def ask(store: S.Store, gw: Any, qual: Mapping[str, Any], day: dt.date, *, now: Callable[[], dt.datetime]
        ) -> dict[str, Any]:
    """ONE STREAMED R2 CALL (sections 1.1, 1.3, 1.5): the read's user text rendered from rows stored before the ask, its
    row stored AHEAD of the call (`ASKED` at its hold), the call made once through the gateway's `/v1/claude/messages`
    (`gw.post_stream`, a byte at least every 30 s, the whole answer within 90 s), and the row finished as one of
    section 1.3's statuses: `ok` (one JSON object that validates its schema exactly), `unparsed`, `refused` (an API
    refusal, or a response model that is not THE PIN, which stops R2 for good), `cut` (stop_reason max_tokens) or
    `lost` (it went out and no whole answer came back), at the gateway's stated cost, an unpriced one at its hold.
    THE FIRST STORED ROW IS FINAL: no event is asked again. A call the gateway refused before sending, that never went
    out, or that was settled at nothing with a 4xx or a 429, STORES NOTHING (a 4xx counts toward the day stop)."""
    from . import gw as G

    kind = str(qual["kind"])
    event = str(qual["event"])
    psha = sha(kind)
    asked = now()
    user, prior = render(store, qual, day, asked)
    request_id = f"evl10:{event}:{psha[:12]}"[:160]
    key = (event, psha, MODEL)
    hold = HOLD_USD[kind]
    with store.tx() as db:
        if db.execute("SELECT 1 FROM reads2 WHERE event=? AND prompt_sha=? AND model=?", key).fetchone() is not None:
            return {"status": "known", "event": event}
        db.execute("INSERT INTO reads2(event, prompt_sha, model, window, day, request_id, asked_at, answered_at, status, "
                   "answer, fields, usd, in_tokens, out_tokens, response_model, user_sha, prior_ids) VALUES(?, ?, ?, ?, "
                   "?, ?, ?, ?, ?, NULL, NULL, ?, NULL, NULL, NULL, ?, ?)",
                   (*key, WINDOW, day.isoformat(), request_id, S.iso(asked), S.iso(asked), ASKED, hold,
                    hashlib.sha256(user.encode("utf-8")).hexdigest(), json.dumps(prior, sort_keys=True)))

    def finish(status: str, *, usd: float, text: str | None = None, fields: Mapping[str, Any] | None = None,
               usage: Mapping[str, Any] | None = None, model: str | None = None) -> dict[str, Any]:
        with store.tx() as db:
            answered = now()        # (inside the write lock: a decision that read before this commit read before it)
            db.execute("UPDATE reads2 SET answered_at=?, status=?, answer=?, fields=?, usd=?, in_tokens=?, out_tokens=?, "
                       "response_model=? WHERE event=? AND prompt_sha=? AND model=?",
                       (S.iso(answered), status, text, None if fields is None else json.dumps(fields, sort_keys=True),
                        usd, _tokens(usage, "input_tokens"), _tokens(usage, "output_tokens"), model, *key))
        return {"status": status, "event": event, "usd": usd,
                "seconds": round(max(0.0, (answered - asked).total_seconds()), 3)}

    def drop(why: str, code: int | None = None) -> dict[str, Any]:
        with store.tx() as db:
            db.execute("DELETE FROM reads2 WHERE event=? AND prompt_sha=? AND model=? AND status=?", (*key, ASKED))
            if code is not None and 400 <= code < 500 and code != 429:
                k = FOURXX_KEY.format(utc=utc_day(asked)[0].isoformat())
                db.execute("INSERT INTO meta(key, value) VALUES(?, '1') ON CONFLICT(key) DO UPDATE SET "
                           "value=CAST(value AS INTEGER) + 1", (k,))
        return {"status": "not sent", "event": event, "why": why[:200], "code": code}

    try:
        code, payload = gw.post_stream(V.PATH, body(kind, user), headers={V.REQUEST_HEADER: request_id}, limit=LIMIT_S,
                                       gap=GAP_S)
    except G.NotSent as exc:                    # (the lane refused it: it never went out)
        return drop(f"{type(exc).__name__}: {str(exc)[:120]}")
    except urllib.error.URLError as exc:        # (sending failed: the gateway never had the whole request)
        return drop(f"{type(exc).__name__}: {str(exc)[:120]}")
    except OSError as exc:                      # (it went out: lost while waiting, or its stream lost)
        told = exc.cost if isinstance(exc, G.StreamLost) and exc.known else None
        return finish(LOST, usd=hold if told is None else float(told))
    except Exception:  # noqa: BLE001 - any failure after the send: lost at its hold
        return finish(LOST, usd=hold)
    stated, known = _cost(gw)
    if not 200 <= int(code) < 300:
        refusal = isinstance(payload, Mapping) and payload.get("cap") is not None
        if stated is not None and stated > 0:
            return finish(LOST, usd=stated)     # (an error the gateway settled at a cost: billed, no answer)
        if int(code) >= 500 and stated is None and not refusal:
            return finish(LOST, usd=hold)       # (a 5xx the gateway did not settle: it may have run; unknown is not free)
        return drop(f"HTTP {code}", int(code))
    if not isinstance(payload, Mapping):
        return finish(LOST, usd=hold if stated is None or not known else stated)
    text = "".join(str(b.get("text") or "") for b in payload.get("content") or []
                   if isinstance(b, Mapping) and b.get("type") == "text")
    stop = payload.get("stop_reason")
    model = payload.get("model")
    usd = stated if stated is not None and known else hold
    fields = None
    if model != PIN:
        status = REFUSED
    elif stop == "refusal":
        status = REFUSED
    elif stop == "max_tokens":
        status = CUT
    else:
        status, fields = parse(text, kind)
    got = finish(status, usd=usd, text=text, fields=fields, usage=payload.get("usage"),
                 model=None if model is None else str(model)[:120])
    if model != PIN:
        stop_for_good(store, "pin", f"the response model {str(model)[:80]!r} is not the pin {PIN!r} ({event})", now())
        got["pin"] = False
    return got


def _tokens(usage: Mapping[str, Any] | None, key: str) -> int | None:
    try:
        value = (usage or {}).get(key)
        return None if value is None else int(value)
    except (TypeError, ValueError):
        return None


def close_stale(store: S.Store, now: dt.datetime) -> int:
    """A row stored ahead of a call that no call can still be streaming (`STALE_ASKED` after its ask: a process that
    ended inside the call) is closed `lost` at its hold (section 1.3: a lost or unpriced call counts at its hold)."""
    with store.tx() as db:
        cur = db.execute("UPDATE reads2 SET status=? WHERE status=? AND asked_at<?",
                         (LOST, ASKED, S.iso(now - STALE_ASKED)))
    return int(cur.rowcount or 0)


# ---------------------------------------------------------------------------------------------------- the House job
def job(lane: Any) -> dict[str, Any]:
    """ONE JOB OF R2'S OWN HOUSE LANE ('reader', key 'reader:r2': league/house.py `_lanes`, `_background`), started on a
    House publish when R2's last job has finished (league/events/house.py `EventLane.turn`): from 07:30:00 ET of D until
    tau - 30 s, a qualification scan (`scan`), then the next due call (`next_due`, `ask`) while no stop and no line
    refuses it. Never on 'feeds:' (no record pass, verdict pass or decision waits for R2) nor on 'ops:'. Returns what it
    did; its warnings are the lane's (once an hour each: `reader_line`, `reader_pin`, `reader_schema`, `reader_stop`,
    `r2_cap`)."""
    if not pinned():
        return {"skipped": "PREREG-EVL-10 is not pinned"}
    if not lane.ready():
        return {"skipped": "the lane's store is not ready"}
    now = lane.now()
    out: dict[str, Any] = {}
    with S.Store(lane.root) as st:
        day = now.astimezone(C.NY).date()
        session = C.session(st, day)
        if session is None or now < start_of(session) or now >= ask_until(session):
            return {"skipped": "outside R2's window"}
        out["stale"] = close_stale(st, now)
        out["scan"] = scan(st, day, now)
        if out["scan"].get("capped"):
            lane.warn("r2_cap", f"READER-2 reached its cap of {CAP_NEWS} news reads on {day.isoformat()}: the later "
                                "qualifying articles are not read (section 1.4)")
        stop = stopped(st)
        if stop is None and schema_failing(st):
            days = schema_failing(st)
            stop_for_good(st, "schema", f"unparsed + cut at least {SCHEMA_SHARE:.0%} of the answered reads on the "
                                        f"sessions {', '.join(days)}", now)
            stop = stopped(st)
        if stop is not None:
            if stop.get("kind") in ("pin", "schema"):
                lane.warn(f"reader_{stop['kind']}", f"READER-2 asks nothing more for good: {stop.get('why')}")
            return out | {"stopped": stop}
        if getattr(lane, "_paused", False):
            return out | {"skipped": "the House is paused: no paid call"}
        if fourxx(st, now) >= DAY_4XX:
            lane.warn("reader_stop", f"three gateway 4xx answers to READER-2 today: its asks stop for the UTC day "
                                     f"{utc_day(now)[0].isoformat()}; its scans go on")
            return out | {"skipped": "the day stop"}
        due = next_due(st, day, session)
        if due is None:
            return out | {"due": None}
        line = line_of_day(st, now, lane.verdict_line)
        why = line_refusal(st, now, str(due["kind"]), line, lane.root.parent)
        v1_today = v1_spend(st, now)
        if Decimal(str(round(v1_today, 6))) > V1_HEAD * Decimal(str(line["V"])):
            st.db.execute("INSERT OR IGNORE INTO meta(key, value) VALUES(?, ?)",
                          (V1_RESERVE_KEY.format(utc=utc_day(now)[0].isoformat()), S.iso(now)))
        if why is not None:
            with st.tx() as db:
                k = LINE_REFUSED_KEY.format(utc=utc_day(now)[0].isoformat())
                db.execute("INSERT INTO meta(key, value) VALUES(?, '1') ON CONFLICT(key) DO UPDATE SET "
                           "value=CAST(value AS INTEGER) + 1", (k,))
            lane.warn("reader_line", f"READER-2 asks nothing over its line today ({why})")
            return out | {"refused": why}
        gw = _own_gateway(lane)
        try:
            out["ask"] = ask(st, gw, due, day, now=lane.now)
        except (LookupError, KeyError, OSError, RuntimeError, UnicodeDecodeError) as exc:
            # (its read cannot be rendered from the store: nothing was sent or stored; the event is a missing read and
            # the next one is asked at the next job)
            key = UNRENDERED_KEY.format(day=day.isoformat())
            have = json.loads(_meta(st, key) or "[]")
            st.set_meta(key, json.dumps(sorted(set(have) | {str(due["event"])})))
            lane.warn("reader", f"READER-2 could not render the read of {due['event']} ({type(exc).__name__}): missing")
            out["ask"] = {"status": "unrendered", "event": str(due["event"])}
        if out["ask"].get("pin") is False:
            lane.warn("reader_pin", f"READER-2's answer carried another model than the pin {PIN!r}: R2 asks nothing more "
                                    "for good (a new reader version is a later file's)")
    return out


def v1_spend(store: Any, now: dt.datetime) -> float:
    """v1's verdict dollars of `now`'s UTC day (an unstated cost at `VERDICT_USD_UNKNOWN`)."""
    _, lo, hi = utc_day(now)
    row = store.db.execute("SELECT COALESCE(SUM(COALESCE(usd, ?)), 0) FROM verdicts WHERE answered_at>=? AND answered_at<?",
                           (VERDICT_USD_UNKNOWN, lo, hi)).fetchone()
    return float(row[0] or 0.0)


def _own_gateway(lane: Any) -> Any:
    """A gateway client of R2's own (the lane's token source and url): its `last_headers` are R2's call's alone, never
    a verdict's the feeds lane made meanwhile on the lane's shared client."""
    from . import gw as G

    base = lane.gateway()
    token = getattr(base, "_token", None)
    if token is None:
        return base
    return G.Gateway(token, url=getattr(base, "url", G.GATEWAY_URL))


# ------------------------------------------------------------------------------------------------- FEATURES-R2 v1
def features(kind: str, f: Mapping[str, Any], prior_n: int) -> list[float]:
    """FEATURES-R2 v1 (section 1.6), the 21 columns in their frozen order, of one `ok` read."""
    doc = kind == "doc"
    guide = str(f.get("vs_own_guidance"))
    return [1.0 if doc else 0.0, f["new"] / 2, f["corroborated"] / 2, f["magnitude"] / 3, f["specific"] / 2,
            f["surprise"] / 3, (f["p_up"] - 50) / 50,
            0.0 if doc else float(bool(f.get("price_story"))),
            float(bool(f.get("routine"))) if doc else 0.0,
            f["material"] / 3 if doc else 0.0,
            f["tone"] / 2 if doc else 0.0,
            float(bool(f.get("dilution"))) if doc else 0.0,
            float(bool(f.get("one_offs"))) if doc else 0.0,
            float(f.get("consensus") == "beat"), float(f.get("consensus") == "miss"),
            float(guide in ("above", "raised")), float(guide in ("below", "lowered", "withdrawn")),
            0.0 if doc else float(f.get("type") in ("analyst_rating", "analyst_target")),
            float(f.get("type") in ("earnings", "guidance")),
            math.log(1 + max(0, int(prior_n))) / math.log(41),
            0.0]


MISSING_ROW = [0.0] * 20 + [1.0]       # (an event a later learner meets with no such row: r2_missing 1, all else 0)


# --------------------------------------------------------------------------------------------------- the decision
def _barred(store: Any, cik: str, session: C.Session, at: dt.datetime) -> bool:
    """THE E10 BAR (section 2.1, PREREG-EVL-7 section 1.9's reading applied to the record as well as to money): any 8-K
    of the issuer (form exactly 8-K) knowable at or after 09:00 ET of D and stored before tau with a stored PROMPT-DOC
    verdict `ok` with score >= 2, or `ok` with score >= 1 and guidance "raised", or no answer by tau (league/events/
    book.py `issuer_8k_guard`, the same reading; unreadable inputs bar)."""
    from .book import issuer_8k_guard

    return issuer_8k_guard(store, cik, session, at)


def candidates(store: Any, day: dt.date, at: dt.datetime) -> list[dict[str, Any]]:
    """SECTION 2.2's CANDIDATES at tau `at`, in KEY order (higher first): one per issuer of D's ON SET (its chosen
    `r2_qual` events) with an `ok` R2 read answered before `at`, its READ the highest KEY, then the earliest answered;
    each, as stored before `at`, eligible, BUYABLE, not BARRED, for an 8K-ON issuer not EXCLUDED on D (an issuer with an
    8K-ON read that is EXCLUDED at tau is dropped: the reading that trades less), its event knowable after
    REGISTERED_AT_10. [{cik, event, kind, fields, h, answered_at, prior_n, symbol, passes, key}]."""
    reg = registered()
    session = C.session(store, day)
    if reg is None or session is None:
        return []
    equity = e_prev(store, day)
    if equity is None:
        return []
    reads: dict[str, list[dict[str, Any]]] = {}
    for r in store.db.execute("SELECT q.cik, q.event, q.kind, q.h, r.fields, r.answered_at, r.prior_ids FROM r2_qual q "
                              "JOIN reads2 r ON r.event=q.event AND r.model=? AND r.prompt_sha=(CASE q.kind WHEN 'news' "
                              "THEN ? ELSE ? END) WHERE q.window=? AND q.day=? AND q.chosen=1 AND r.status=? AND "
                              "r.answered_at<? ORDER BY r.answered_at, q.event",
                              (MODEL, sha("news"), sha("doc"), WINDOW, day.isoformat(), OK, S.iso(at))):
        try:
            fields = json.loads(r["fields"] or "null")
            prior = json.loads(r["prior_ids"] or "{}")
        except ValueError:
            continue
        if not isinstance(fields, dict) or parse(json.dumps(fields), str(r["kind"]))[0] != OK:
            continue
        knowable = P.knowable_of(store, str(r["event"]))
        if knowable is None or knowable <= reg:
            continue
        reads.setdefault(str(r["cik"]), []).append({"cik": str(r["cik"]), "event": str(r["event"]),
                                                    "kind": str(r["kind"]), "fields": fields, "h": float(r["h"]),
                                                    "answered_at": str(r["answered_at"]),
                                                    "prior_n": int((prior or {}).get("n") or 0)})
    if not reads:
        return []
    uni = universe_at(store, day, at, strict=True)
    lo, hi = P.close_window(store, day)
    all8k = [r for r in P.filings_window(store, "8-K", lo, hi) if _stored_by(r, at, store)]
    skip = _excluded_at(store, day, at, uni, all8k)
    out = []
    for cik, mine in reads.items():
        row = uni.get(cik)
        if row is None or not buyable(row, equity):
            continue
        if any(x["kind"] == "doc" for x in mine) and cik in skip:
            continue
        if _barred(store, cik, session, at):
            continue
        best = sorted(mine, key=lambda x: (tuple(-v for v in consumer_key(x["fields"], x["h"])), x["answered_at"]))[0]
        out.append(best | {"symbol": str(row["symbol"]).upper(), "passes": consumer_pass(best["kind"], best["fields"]),
                           "key": consumer_key(best["fields"], best["h"])})
    return sorted(out, key=lambda x: (tuple(-v for v in x["key"]), x["cik"]))


def decide(store: S.Store, day: dt.date, *, now: dt.datetime, rid: int | None = None) -> dict[str, Any]:
    """THE DECISION RUN `decide-close-r2:<D>` (section 2.4), SQL over stored rows only, ONE TRANSACTION committed only
    when the run completes (its receipt `ok` in the same transaction when `rid` is given): the candidates at tau
    (`candidates`); EVL-R2-ON's PICKS, the first 8 passing candidates in key order it holds no position in within 5
    sessions (programs.py `_held_recently`, A72's reading), `rank_key` 9 - position; EVL-R2-ON-SET every candidate,
    REC-R2-ON-PASS every passing one (no cut at 8), REC-R2-ON-AVOID every failing one, each with its own one position
    per issuer, `rank_key` its count less its place (its key order); every intent with decided_at = tau, entering at
    D's close and exiting at the next session's open; and FEATURES-R2 v1 of every candidate (`r2_features`, once per
    (event, decision)). The run starts at tau or later and its picks are fixed by stored times, so they do not depend
    on when in its window it ran."""
    session = C.session(store, day)
    if session is None:
        raise LookupError(f"no session {day}")
    T = tau(session)
    if now < T:
        raise RuntimeError(f"the decision of {day} runs at tau {S.iso(T)} or later, not at {S.iso(now)}")
    if not pinned():
        raise RuntimeError("PREREG-EVL-10 is not pinned")
    rows = {p.id: p for p in P.reader2_rows()}
    exit_session = C.nth(store, day, 2)
    if exit_session is None:
        raise LookupError(f"no session after {day}")
    decision = f"{JOB}:{day.isoformat()}"
    summary: dict[str, Any] = {"tau": S.iso(T)}
    with store.tx() as db:
        cands = candidates(store, day, T)
        passing = [c for c in cands if c["passes"]]
        failing = [c for c in cands if not c["passes"]]

        def free(pid: str, group: Sequence[Mapping[str, Any]], cap: int | None = None) -> list[Mapping[str, Any]]:
            got = []
            for c in group:
                if cap is not None and len(got) >= cap:
                    break
                if P._held_recently(store, rows[pid], str(c["cik"]), day):
                    continue
                got.append(c)
            return got
        chosen = {P.R2_ON: free(P.R2_ON, passing, K), P.R2_SET: free(P.R2_SET, cands),
                  P.R2_PASS: free(P.R2_PASS, passing), P.R2_AVOID: free(P.R2_AVOID, failing)}
        for pid, picks in chosen.items():
            prog = rows[pid]
            for i, c in enumerate(picks):
                rank = float(K + 1 - (i + 1)) if pid == P.R2_ON else float(len(picks) - i)
                db.execute("INSERT OR IGNORE INTO intents(program, version, event, symbol, cik, decided_at, entry_day, "
                           "entry_at, exit_day, exit_at, rank_key, mode, status, why) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
                           "?, 'shadow', 'planned', NULL)",
                           (prog.id, prog.version, c["event"], c["symbol"], c["cik"], S.iso(T), day.isoformat(),
                            prog.entry_at, exit_session.day.isoformat(), prog.exit_at, rank))
            summary[prog.id if int(prog.version) == 1 else f"{prog.id}@v{prog.version}"] = {"planned": len(picks)}
        for c in cands:
            db.execute("INSERT OR IGNORE INTO r2_features(event, decision, columns, written_at) VALUES(?, ?, ?, ?)",
                       (c["event"], decision, json.dumps({"v": FEATURES_VERSION,
                                                          "x": features(c["kind"], c["fields"], c["prior_n"])}),
                        S.iso(now)))
        summary["candidates"] = len(cands)
        summary["passing"] = len(passing)
        if rid is not None:
            db.execute("UPDATE receipts SET finished_at=?, status='ok', summary=? WHERE id=?",
                       (S.iso(now), json.dumps(summary, sort_keys=True, default=str), int(rid)))
    return summary


def live_part(ctx: Any, day: dt.date, auction: str, slot: Any, rid: int) -> dict[str, Any]:
    """THIS FILE'S PART OF THE SCHEDULER (league/events/scheduler.py `Part.run`): the live decision of `day`'s close
    under its slot's bound (10 s from its own start, never started past 15:44:20 ET)."""
    if auction != "close":
        raise ValueError("PREREG-EVL-10 decides at the close only")
    return decide(ctx.store, day, now=ctx.now(), rid=rid)


# ----------------------------------------------------------------------------------------------- THE ONE READING
def decided(store: Any, day: dt.date) -> str | None:
    """The status of the latest live receipt `decide-close-r2:<D>` (None with none)."""
    row = store.db.execute("SELECT status FROM receipts WHERE job=? ORDER BY id DESC LIMIT 1",
                           (f"{JOB}:{day.isoformat()}",)).fetchone()
    return None if row is None else str(row["status"] or "")


def one_reading(store: Any, program: Any, day: dt.date) -> list[dict[str, Any]]:
    """SECTION 2.4'S ONE READING of this file's rows (EVL-R2-ON, its control and its two records): the intents of `program`
    the live `decide-close-r2:<D>` receipt with status `ok` wrote (decided_at = tau of D), in rank_key order, then
    adv20 descending, then event id, each with D's universe row's adv20 and previous close and its event's knowable
    time; EMPTY with no such receipt. Every input is cut at tau of D whatever the time it is read at, so real money,
    PREREG-EVL-8's members of EVL-META-ON and the shadow read the same picks (no read answered, and no 8-K or article
    stored, after tau reaches any of them). Real money's held-lot skip is the caller's (league/events/book.py
    `r2_picks`)."""
    pid = str(getattr(program, "id", program))
    version = int(getattr(program, "version", 1) or 1)
    session = C.session(store, day)
    if session is None or not P.is_reader2(pid) or decided(store, day) != OK:
        return []
    rows = []
    for r in store.db.execute("SELECT i.event, i.symbol, i.cik, i.rank_key, u.adv20, u.prev_close FROM intents i LEFT JOIN "
                              "universe u ON u.day=i.entry_day AND u.symbol=i.symbol WHERE i.program=? AND i.version=? "
                              "AND i.entry_day=? AND i.decided_at=?",
                              (pid, version, day.isoformat(), S.iso(tau(session)))):
        knowable = P.knowable_of(store, str(r["event"]))
        rows.append({"event": str(r["event"]), "symbol": str(r["symbol"]).upper(), "cik": str(r["cik"]),
                     "rank": float(r["rank_key"]) if r["rank_key"] is not None else None,
                     "adv20": float(r["adv20"] or 0.0), "prev_close": r["prev_close"],
                     "knowable_at": None if knowable is None else S.iso(knowable)})
    return sorted(rows, key=lambda x: (-(x["rank"] if x["rank"] is not None else float("-inf")), -x["adv20"], x["event"]))


#: THE NARROW INTERFACE FOR PREREG-EVL-8's EVL-META-ON AND EVL-META-ON-POOL (its section 7.2, frozen: they take this
#: file's four rows as SOURCES, read ONLY through section 2.4's one reading, never `reads2`, `r2_qual` or
#: `r2_features`). PREREG-EVL-8's code (feat/evl-8, PR 609) is not on main at this release: when it lands, its source
#: reader calls `meta_sources()` for the ids and `one_reading(lane, id, day)` (or league/events/book.py `picks`, which
#: routes these rows to it) for their members; nothing else of this file is its input.
def meta_sources() -> tuple[str, ...]:
    """This file's hold-1 close-to-open rows, PREREG-EVL-8 section 7.2's SOURCES (none while REGISTERED_AT_10 is None)."""
    return tuple(p.id for p in P.reader2_rows())


# ------------------------------------------------------------------------------------------ the report and the alarms
def session_counts(store: Any, day: dt.date) -> dict[str, Any]:
    """THE READER LINE of session `day` (counts only, no field, figure or text of any read): scans and whether the
    session is COMPLETE, the share q, the events that qualified and were chosen by kind, the reads by status and their
    dollars, the chosen reads answered before tau, the decision's receipt and its rows' intents."""
    session = C.session(store, day)
    out: dict[str, Any] = {"day": day.isoformat(), "session": session is not None}
    if session is None or not _table(store.db, "r2_qual"):
        return out
    scans = scans_of(store, day)
    out["scans"] = len(scans)
    out["complete"] = complete(scans, session)
    q = _meta_json(store, Q_KEY.format(day=day.isoformat())) or {}
    out["q"] = q.get("q")
    qual = {(str(r["kind"]), int(r["chosen"])): int(r["n"]) for r in store.db.execute(
        "SELECT kind, chosen, COUNT(*) AS n FROM r2_qual WHERE window=? AND day=? GROUP BY kind, chosen",
        (WINDOW, day.isoformat()))}
    out["qualified"] = {k: qual.get((k, 0), 0) + qual.get((k, 1), 0) for k in KINDS}
    out["chosen"] = {k: qual.get((k, 1), 0) for k in KINDS}
    out["reads"] = {str(r["status"]): int(r["n"]) for r in store.db.execute(
        "SELECT status, COUNT(*) AS n FROM reads2 WHERE day=? GROUP BY status", (day.isoformat(),))}
    out["usd"] = round(float(store.db.execute("SELECT COALESCE(SUM(usd), 0) FROM reads2 WHERE day=?",
                                              (day.isoformat(),)).fetchone()[0] or 0.0), 4)
    T = tau(session)
    chosen = sum(out["chosen"].values())
    answered = int(store.db.execute(
        f"SELECT COUNT(*) FROM r2_qual q JOIN reads2 r ON r.event=q.event AND r.model=? WHERE q.window=? AND q.day=? AND "
        f"q.chosen=1 AND r.status IN ({', '.join('?' * len(ANSWERED))}) AND r.answered_at<?",
        (MODEL, WINDOW, day.isoformat(), *ANSWERED, S.iso(T))).fetchone()[0] or 0)
    out["answered_by_tau"] = answered
    out["missing_share"] = None if chosen == 0 else round(1.0 - answered / chosen, 4)
    out["decision"] = decided(store, day)
    out["intents"] = {p.id: int(store.db.execute("SELECT COUNT(*) FROM intents WHERE program=? AND version=? AND "
                                                 "entry_day=?", (p.id, p.version, day.isoformat())).fetchone()[0] or 0)
                      for p in P.reader2_rows()}
    out["capped"] = _meta(store, CAP_KEY.format(day=day.isoformat())) is not None
    return out


def alarms(store: Any, now: dt.datetime) -> list[dict[str, Any]]:
    """THE ALARMS OF SECTION 11 as of `now` ([{kind, what}], counts and dates only): `reader_pin` and `reader_schema`
    (R2's stop for good), `reader_stop` (today's day stop), `reader_line` (today R2's line refused an ask, or v1 spent
    over 1.5 V: binding `v1_reserve`), `reader_missing` (under 85% of chosen reads answered by tau two sessions
    running), `r2_starve` (the last closed session's slot did not run live, failed, was cut or was missed: no decision
    of this file), `r2_cap` (the last session reached 64 news reads). Nothing while REGISTERED_AT_10 is None."""
    if not pinned() or not _table(store.db, "reads2"):
        return []
    out: list[dict[str, Any]] = []
    stop = _meta_json(store, STOP_KEY)
    if stop is not None and stop.get("kind") in ("pin", "schema"):
        out.append({"kind": f"reader_{stop['kind']}", "what": f"READER-2 stopped for good: {stop.get('why')}"})
    utc = utc_day(now)[0].isoformat()
    if fourxx(store, now) >= DAY_4XX:
        out.append({"kind": "reader_stop", "what": f"three gateway 4xx answers to READER-2 on {utc}: no ask that day"})
    refused = _meta(store, LINE_REFUSED_KEY.format(utc=utc))
    if refused:
        out.append({"kind": "reader_line", "what": f"READER-2's line refused {refused} ask(s) on {utc}"})
    if _meta(store, V1_RESERVE_KEY.format(utc=utc)) is not None:
        out.append({"kind": "reader_line", "what": f"v1 spent over 1.5 V on {utc} (binding v1_reserve)"})
    today = now.astimezone(C.NY).date()
    closed = [s for s in C.previous(store, today + dt.timedelta(days=1), 3) if s.close_at <= now]
    reg = registered()
    shares = []
    for s in closed[-MISSING_SESSIONS:]:
        got = session_counts(store, s.day)
        if got.get("missing_share") is not None:
            shares.append(got["missing_share"])
    if len(shares) == MISSING_SESSIONS and all(x > 1.0 - MISSING_SHARE for x in shares):
        out.append({"kind": "reader_missing", "what": f"under {MISSING_SHARE:.0%} of READER-2's chosen reads were "
                                                      f"answered by tau on {MISSING_SESSIONS} sessions running"})
    if closed:
        last = closed[-1]
        never = X.slot(FILE, "close").never_past.at(last) if X.slot(FILE, "close") is not None else tau(last)
        if reg is not None and tau(last) > reg and now > never and decided(store, last.day) != OK:
            out.append({"kind": "r2_starve", "what": f"no live decision of PREREG-EVL-10's rows on {last.day.isoformat()} "
                                                     f"(its slot's receipt: {decided(store, last.day) or 'none'}): no "
                                                     "intent, block, record or real money that session"})
        if _meta(store, CAP_KEY.format(day=last.day.isoformat())) is not None:
            out.append({"kind": "r2_cap", "what": f"READER-2 reached {CAP_NEWS} news reads on {last.day.isoformat()}"})
    return out


def report_lines(store: Any, day: dt.date, now: dt.datetime) -> list[str]:
    """The daily report's READER block (counts only)."""
    if not pinned():
        return []
    got = session_counts(store, day)
    if not got.get("session"):
        return [f"Reader-2: no session {day.isoformat()}"]
    reads = got.get("reads") or {}
    line = (f"Reader-2 {day.isoformat()}: scans {got.get('scans', 0)} ({'complete' if got.get('complete') else 'not complete'}),"
            f" q {got.get('q')}; qualified news {got['qualified']['news']} / 8-K {got['qualified']['doc']}, chosen "
            f"{got['chosen']['news']} / {got['chosen']['doc']}; reads " +
            (", ".join(f"{k} {v}" for k, v in sorted(reads.items())) or "none") +
            f" (${got.get('usd', 0.0):.2f}); answered by tau {got.get('answered_by_tau', 0)}; decision "
            f"{got.get('decision') or 'none'}; intents " + ", ".join(f"{k} {v}" for k, v in got["intents"].items()))
    lines = [line]
    for a in alarms(store, now):
        lines.append(f"Reader-2 alarm {a['kind']}: {a['what']}")
    return lines


# ------------------------------------------------------------------------------------------- the scheduler's part
def _since() -> dt.datetime | None:
    return registered()


X.register(X.Part(FILE, run=live_part, catchup=None, programs=lambda: [p.id for p in P.reader2_rows()], since=_since))


__all__ = ["MODEL", "EFFORT", "MAX_TOKENS", "THINKING", "STREAM", "GAP_S", "LIMIT_S", "SYSTEM_NEWS", "SYSTEM_DOC",
           "USER_NEWS", "USER_DOC", "SCHEMA_NEWS", "SCHEMA_DOC", "spec", "sha", "body", "line_news", "line_filing",
           "render_news", "render_doc", "parse", "LIQUID_ADV", "N_NEWS", "CAP_NEWS", "CAP_8K_ON", "Q_SESSIONS",
           "Q_DEFAULT", "K", "h", "share", "consumer_pass", "consumer_key", "PIN", "SHAS", "FILE", "WINDOW", "HOLD_USD",
           "LINE_MAX", "V1_HEAD", "BIRTHS_NIGHT", "BUYABLE_SHARE", "TAU_BEFORE_CLOSE", "ASK_STOP", "START_AT", "JOB",
           "OK", "UNPARSED", "REFUSED", "CUT", "LOST", "ASKED", "registered", "pinned", "tau", "ask_until",
           "start_of", "e_prev", "universe_at", "liquid", "buyable", "qualify", "complete", "share_of", "choose",
           "scan", "next_due", "render", "usd_between", "usd_all", "v1_heaviest", "r2_line", "lane_spend",
           "line_of_day", "line_refusal", "stopped", "schema_failing", "ask", "close_stale", "job", "features",
           "MISSING_ROW", "FEATURE_COLUMNS", "candidates", "decide", "live_part", "decided", "one_reading",
           "meta_sources", "session_counts", "alarms", "report_lines", "NORUN_KEY", "RUNS_MAX", "CHARGE_HUNDREDTHS"]
