"""READER-2 (R2) for PREREG-EVL-10: the frozen request specs, prompt texts, answer schemas, renderers, the parser and
the deterministic set rules a pre-registration would freeze (design-reader2 lens, workflow edge-swings). SYNTHETIC /
STDLIB ONLY: nothing here reads the lane's store, the House, the gateway or any outcome.

What is new against the EVL-7 reader lens's sketch (evl7/reader/reader2_spec.py, which is NOT registered):
  - ONE model, claude-sonnet-5-5, for every R2 read (no Haiku tier, no cascade): effort "low", no sampling parameter,
    adaptive thinking with its display omitted, structured outputs (output_config.format json_schema), STREAMED;
  - the reader sees the issuer's last 30 days of STORED articles (headline lines) and 8-Ks, not 72 hours;
  - fields named by the lens: surprise, consensus (as the texts state it), vs_own_guidance (against the company's own
    previous guidance, as the texts state it), magnitude, specific, material (8-K item materiality), new (novelty
    against the 30 days), corroborated (confirmation across sources), p_up (direction with its confidence);
  - fewer fields (10 news, 15 doc) so the answer is short: output tokens are 5x input tokens' price;
  - no item 2.02 filing is read (a pre-open earnings issuer is ERN(D), which an open-to-close row may not buy:
    PREREG-EVL-7's E8), so the EVL-7 lens's previous-release outlook fetch is not needed.
The House copies the constants below verbatim into league/events/reader2.py; a test compares them with the frozen file.
PROMPT-DOC and PROMPT-NEWS (PREREG-EVL-1 section 4) are never touched.

Run: .venv/bin/python r2_spec.py   (prints the four shas, byte sizes and the parser self-test)
"""
from __future__ import annotations

import hashlib
import json
import re

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

USER_NEWS = """Stock: {symbol} ({name}). Published {created_et} ET by {source}.
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
p_up: the probability, from 0 to 100 in steps of 5, that this stock outperforms the overall stock market over the next trading day."""

USER_DOC = """Company: {name} (ticker {ticker}). SEC Form 8-K, items {items}, accepted {acceptance_et} ET.
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
p_up: the probability, from 0 to 100 in steps of 5, that this stock outperforms the overall stock market over the next trading day."""

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


def render_news(*, symbol, name, created_et, source, headline, summary, prior_news, prior_filings) -> str:
    return USER_NEWS.format(symbol=symbol, name=name or symbol, created_et=created_et, source=source or "unknown",
                            headline=headline or "", summary=summary or "",
                            prior_news="\n".join(prior_news[:NEWS_LINES["news"]]) or "none",
                            prior_filings="\n".join(prior_filings[:FILING_LINES]) or "none")


def render_doc(*, name, ticker, items, acceptance_et, text, prior_news) -> str:
    return USER_DOC.format(name=name or ticker, ticker=ticker, items=", ".join(items), acceptance_et=acceptance_et,
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


if __name__ == "__main__":
    for kind in ("news", "doc"):
        s = spec(kind)
        print(kind, "sha", sha(kind), "system+user chars", len(s["system"]) + len(s["user"]), "schema bytes",
              len(json.dumps(s["format"])))
    ok = parse(json.dumps({"type": "analyst_rating", "new": 2, "corroborated": 0, "price_story": False,
                           "consensus": "not_stated", "vs_own_guidance": "not_stated", "magnitude": 2, "specific": 1,
                           "surprise": 2, "p_up": 65}), "news")
    bad = parse('{"type": "analyst_rating"}', "news")
    badint = parse(json.dumps({"type": "earnings", "new": 2, "corroborated": 0, "price_story": False,
                               "consensus": "beat", "vs_own_guidance": "raised", "magnitude": 2, "specific": 1,
                               "surprise": 2, "p_up": 63}), "news")
    print("parse self-test:", ok[0], bad[0], badint[0], "(expect ok unparsed unparsed)")
    print("consumer_pass on the ok sample:", consumer_pass("news", ok[1]))
    hs = [h("O1", "2026-10-26", str(c)) for c in range(20000)]
    print("h uniformity: mean %.4f, share < 0.25 %.4f" % (sum(hs) / len(hs), sum(x < 0.25 for x in hs) / len(hs)))
    print("share():", share([]), share([10, 12]), share([54, 88, 165]))
