"""The public record at blakewoods.us/capital: AI agents trading options (schema 2, Sept 26, 2026).

The site starts over for the options swarm. Its masthead shows the full real-options profit, including
marked open positions, and the running timer. The Brokerage Account's balance and funding/compute basis
remain separate. It also shows the swarm (each agent's family, its mechanism in a sentence, its band,
record and optional promotion checklist); the Gym's pace; the
open structures with their maximum loss and P&L; and the tape of the agents' decisions in their own
words. The site's validators are `personal-site/capital/schema.js`; the contract is
`league/tests/fixtures/site_contract.md`, and `site_checkpoint.json` / `site_events.json` beside it are
this module's own output, which the site's tests publish and draw.

**The data licenses forbid publishing quotes.** ThetaData's and the market-data subscription's terms
forbid republishing quotes, bids, asks, spreads, implied vols, greeks, surfaces, or parameters fitted
from them, and the repository and the site are public. So every block here is an ALLOWLIST: each output
dict is built key by key from the fields named below and nothing else is ever copied through, and every
sentence (an agent's note, a trade's reason, the swarm's news, a mechanism) is masked by
`scrub_quotes` (no decimal number, no dollar or cent amount, no number beside a quote word) and
`scrub_venues` (the account is "the Brokerage Account"; a venue is "the broker"). The site refuses the
same patterns, so a masked sentence always passes and an unmasked one never shows.

**Inputs.** `build_checkpoint(inputs, published_at)` is pure: it takes explicit inputs and returns the
checkpoint. `Publisher.checkpoint(house)` gathers them: its own reads (the Brokerage Account through the
broker, the owner's funding flows since `performance.start_at`, the Sail meter's rows on the ledger, the
subscriptions prorated from the reset, the roster, the books' open structures), overlaid by
`house.site_inputs()` when the House defines it. That hook is how the swarm (the Gym's pace, bands,
mechanisms, records, OpenAI spend) and the live path (open structures) feed the page: return a mapping
with any of these keys, and anything not yet available as None or an empty list.

    started_at   ISO time the House first started on its new ledger (default: the first `ops.started`)
    account      {equity, cash, as_of, stale}                       the Brokerage Account
    performance  {start_at, start_equity, net_flows, verified_at}   the profit basis
    compute      {sail_usd, claude_usd, openai_usd, thetadata_usd, market_data_usd, other_usd}  since the reset;
                 merged part by part over the defaults (Sail as Sail billed it, Claude its own part: below)
    gym          {trials, market_years, families_alive, families_retired}
    agents       [{id, family, mechanism, structure, band, born_at, retired_at,
                   trials, revisions, forward: {trades, wins, pnl_usd} | None, real: {...} | None}]
    structures   [{id, agent, underlying, structure, legs, expiry, quantity, real, opened_at,
                   max_loss_usd, pnl_usd}]
    practice     {as_of, sessions, capital_usd, rows: [{family, lineage, structure, tier, sessions, trades, wins,
                   pnl_usd, return_on_risk, last_day, live}]}      the practice league (the live path's; `site_practice`)

The swarm window (`levels`, `rationale`) is the publisher's own read (`league/site_window.py`), never the hook's.

**The practice league** (Sept 29, 2026). `practice {as_of, sessions, capital_usd, totals, rows}`: every family that
practised on live quotes in the shadow book under the Gym's fill rules (never real money), one row each: its tier
(validated or Train), sessions, closed trades, wins, realized P&L and return on maximum loss. It is never part of
`trading`, `positions`, `performance` or Profit, and never carries a price, strike, leg, expiry, minute, trade date,
version or code. A site that refuses a checkpoint carrying it (the site accepts exact shapes: an older site) gets the
checkpoint again without it and is offered it again half an hour later, with a warning that quotes the site's reply.

**Every input cost, by service** (the owner, Sept 30, 2026: the public site must stop understating cost and show Net).
`compute` is the bill since the reset, part by part: Sail as Sail billed it (the swarm's `sitefeed.sail_billed`: the
guard's balance meter, never the Gym's booked box estimate, which ran about 70% above the provider's bill), Claude
(`claude_usd`, the research roles' model calls), OpenAI, the two data subscriptions prorated from the reset, and
`other_usd`. The site derives Net from it and the positions table (realized options P&L less every input cost). A site
older than Sept 30, 2026 knows five parts, so it gets Claude back inside `other_usd` (`legacy_compute`, #431's shape),
together with the practice block's fallback below: either repository may deploy first.

**Profit and the positions table** (the owner, Sept 28, 2026). `trading {as_of, pnl_usd}` is the complete
real-options P&L of the Brokerage Account since `performance.start_at`, and `positions {as_of, rows, earlier, other,
unreconciled_usd}` lists what it is made of: one row per real position of the live book, open or closed, the agents'
and the House's calibration round trips alike (`league/trading_profit.py`); `earlier`, the positions not listed (the
oldest closed past the table's length, and any row the table's fields cannot describe, alerted) as one line; an
"Other account activity" line from the account's own activity record (`league/account_activity.py`: fees no position
carries, crypto fees, interest, other returns); and `unreconciled_usd`, what the account shows that the book cannot
account for (alerted, never hidden). The lines add up to Profit to the cent; `unreconciled_usd` is "0.00" when the book
and the broker agree. A row says what a position is (root, structure kind, call/put, legs, contracts, expiry, when it
opened and closed, to the minute) and its dollar P&L after fees, never a strike, a fill price or a mark. A site that
refuses a checkpoint carrying the block (an older site, or a row it rejects) gets it again without the block, and is
offered it again half an hour later, with a warning that quotes the site's reply; so the House may deploy before the
site.

**The swarm window** (Oct 1, 2026: the owner asked that anyone can see why an agent traded, every trade's result, and the
agents' progress through the game's levels). Two blocks, sent together or not at all, each an allowlist
(`site_levels`, `site_rationale`) over what `league/site_window.py` reads, read-only, from the swarm's store, the live
book and the practice record:

    levels     {as_of, agents: [{id, level}], funnel: {since, born, practice, validation, tuition, incubator, looks,
                looks_passed, candidate, probe, sized, retired, calibration, live_test}}
    rationale  {as_of, agents: [{id, thesis}], trades: [{id, route, open_why, close_why, exit, max_loss_usd}]}

A level is where an agent stands now (Train, Validation, Practice, Incubator, Tuition, Candidate, Probe, Sized, Retired),
never one its band rules out; the funnel counts the families that reached each level since the reset (unions, so each
chain only narrows; a count it cannot read is null). A thesis is the family's own mechanism in whole sentences with no
digit, no number word, no colon, bracket or code mark and no parameter name (`swarm/public.py` `thesis_text`, then
`thesis_words` here); a trade's reasons are its orders' tags under the same rules (`tag_text`), none on the House's rows;
`exit` is "agent", "house" or "expiry", never text; `max_loss_usd` is its maximum loss at open. Never a price, a strike,
a mark, a parameter's value, a threshold, code, a sketch or a private note. Entries name only agents the page shows and
rows the table lists. Every agent a real position names is pinned to the roster (alive or retired: `Publisher._pinned`),
outside the retired list's 24. A site that refuses a checkpoint carrying the window gets it again without it (tried
first) and is offered it again half an hour later (`WINDOW_RETRY_SECONDS`), with a warning that quotes the site's reply.

The tape is made from ledger rows (`to_events`): `agent.thought` (and a research summary) is an agent's
note; a `book.fill` of an option or a structure held as one instrument is a trade (a buy opens it, a sale
with `realized` closes it; `book.settle` closes one at expiry); `floor.mark` rows this publisher writes
(`brokerage_equity`) are the balance marks; births, band moves, deaths and audits are the swarm's news.
Rows marked private on the ledger, and private keys, never leave.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any, Callable, Mapping

from .ledger import HOUSE, Entry, canonical, now_iso, public_view

SCHEMA_VERSION = 2
ZERO = Decimal(0)
MAX_BATCH = 100
MARK_EVERY_SECONDS = 300
# The site's bounds (capital/schema.js): a checkpoint over any of them is refused whole.
MAX_AGENTS = 160
MAX_DEAD_SHOWN = 24
MAX_STRUCTURES = 100
#: The positions table's rows; older closed positions fold into one line (`site_positions`).
MAX_POSITIONS = 300
#: `incubator` (release B, Oct 1, 2026): an agent's position on the incubator route (real money at tuition size, never
#: evidence), with the agent's id as an agent's.
POSITION_SOURCES = ("agent", "calibration", "house", "incubator")
AGENT_SOURCES = ("agent", "incubator")
#: A real structure's optional route (the site's `STRUCTURE_ROUTES`): only the incubator's so far.
STRUCTURE_ROUTES = ("incubator",)
RIGHTS = ("call", "put", "both")
#: Which side each structure can be on (the site's `STRUCTURE_RIGHTS`, `capital/schema.js`): a vertical, a butterfly,
#: a calendar or a diagonal is all calls or all puts; a condor, an iron butterfly, a straddle and a strangle are both.
STRUCTURE_RIGHTS = {"long_call": ("call",), "long_put": ("put",), "debit_vertical": ("call", "put"), "credit_vertical": ("call", "put"),
                    "iron_condor": ("both",), "iron_butterfly": ("both",), "long_butterfly": ("call", "put"),
                    "long_straddle": ("both",), "long_strangle": ("both",), "calendar": ("call", "put"), "diagonal": ("call", "put")}
OTHER_KEYS = ("fees_usd", "crypto_usd", "interest_usd", "misc_usd")
#: A site that refused the positions table (or the practice block) is asked again after this long (`Publisher.publish`).
POSITIONS_RETRY_SECONDS = 1800
PRACTICE_RETRY_SECONDS = POSITIONS_RETRY_SECONDS
#: The practice league's rows on the page (`site_practice`).
MAX_PRACTICE_ROWS = 48
#: The swarm window (Oct 1, 2026; `site_levels`, `site_rationale`): the site's `LEVELS`, `LEVELS_BY_BAND`, `ROUTES`,
#: `ROUTES_BY_SOURCE`, `EXITS`, `FUNNEL_KEYS` and the funnel's chains (`capital/schema.js`).
LEVELS = ("train", "practice", "validation", "incubator", "tuition", "candidate", "probe", "sized", "retired")
LEVELS_BY_BAND = {"gym": ("train", "practice", "validation", "incubator", "tuition"), "candidate": ("candidate",),
                  "probe": ("probe",), "sized": ("sized",), "retired": ("retired", "tuition", "incubator", "probe", "sized")}
ROUTES = ("tuition", "incubator", "probe", "sized", "calibration", "house")
ROUTES_BY_SOURCE = {"calibration": ("calibration",), "house": ("house",), "incubator": ("incubator",),
                    "agent": ("tuition", "probe", "sized")}
EXITS = ("agent", "house", "expiry")
FUNNEL_KEYS = ("since", "born", "practice", "validation", "tuition", "incubator", "looks", "looks_passed", "candidate", "probe",
               "sized", "retired", "calibration", "live_test")
#: Each chain only narrows, lowest count first (a family counts at a level when it reached it or any higher one).
FUNNEL_CHAINS = (("sized", "probe", "candidate", "tuition", "validation", "born"), ("incubator", "practice", "born"),
                 ("retired", "born"), ("looks_passed", "looks"))
#: A thesis (whole sentences) and an order's reason, at most (`site_rationale`).
THESIS_CHARS = 280
WHY_CHARS = 80
#: A site that refused the swarm window is offered it again after this long (`Publisher.publish`).
WINDOW_RETRY_SECONDS = 1800
MAX_CHECKPOINT_BYTES = 512 * 1024
#: A profit is only as good as its funding check: the site shows none on a check older than ten minutes.
FLOWS_EVERY_SECONDS = 300
FLOWS_FRESH_SECONDS = 600
#: What the subscriptions cost a month, prorated from the reset (the plan's "one number"): ThetaData
#: Options Standard at $80, and the market-data subscription at about $1,000 a year. `performance`
#: `subscriptions_monthly_usd` overrides either.
SUBSCRIPTIONS_MONTHLY_USD = {"thetadata_usd": Decimal("80"), "market_data_usd": Decimal("1000") / 12}
MONTH_SECONDS = Decimal(365.25 * 86400) / 12
COMPUTE_PARTS = ("sail_usd", "claude_usd", "openai_usd", "thetadata_usd", "market_data_usd", "other_usd")

BANDS = ("gym", "candidate", "probe", "sized", "retired")
REAL_BANDS = ("probe", "sized")
BAND_WORDS = {"gym": "Gym", "candidate": "Candidate", "probe": "Probe", "sized": "Sized", "retired": "Retired"}
BAND_RANK = {"sized": 0, "probe": 1, "candidate": 2, "gym": 3, "retired": 4}
STRUCTURE_TYPES = ("long_call", "long_put", "debit_vertical", "credit_vertical", "iron_condor", "iron_butterfly",
                   "long_butterfly", "long_straddle", "long_strangle", "calendar", "diagonal")
ALLOWED_LINK_HOSTS = ("sec.gov", "www.sec.gov", "efts.sec.gov", "blakewoods.us", "github.com", "finance.yahoo.com")

_LINK = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://\S+")
_SCHEME = re.compile(r"\b(javascript|vbscript|data|file|blob):(?=\S)", re.IGNORECASE)
_SECRET = re.compile(r"\b(sk-|apca-)|\bbearer[ :]", re.IGNORECASE)
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_ID = re.compile(r"[^A-Za-z0-9:_.-]")
_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$")
_SLUG = re.compile(r"^[a-z0-9-]{1,40}$")
_UNDERLYING = re.compile(r"^[A-Z][A-Z0-9.]{0,9}$")
_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class PublishError(RuntimeError):
    def __init__(self, message: str, *, status: int | None = None):
        super().__init__(message)
        self.status = status


# ------------------------------------------------------------------------------- cleaning
def js_length(text: str) -> int:
    """A string's length as JavaScript counts it (UTF-16 code units), which is how every one of the
    site's validators measures text: an emoji is two there and one in Python."""
    return len(text.encode("utf-16-le", "surrogatepass")) // 2


def js_cut(text: str, limit: int) -> str:
    """The longest prefix of `text` at most `limit` long in JavaScript's count, never splitting a character."""
    if js_length(text) <= limit:
        return text
    units = 0
    for index, char in enumerate(text):
        units += 2 if ord(char) > 0xFFFF else 1
        if units > limit:
            return text[:index]
    return text


def clean_text(value: Any, limit: int = 8000) -> str:
    text = str(value if value is not None else "")
    text = _CONTROL.sub(" ", text).replace("<", "‹")

    def link(match: re.Match) -> str:
        url = match.group(0)
        host = re.sub(r"^https://", "", url).split("/")[0].lower()
        return url if url.startswith("https://") and host in ALLOWED_LINK_HOSTS else "[link removed]"

    text = _LINK.sub(link, text)
    text = _SCHEME.sub(lambda m: m.group(1) + ": ", text)
    text = _SECRET.sub("[removed] ", text)
    return js_cut(text, limit)


def clean(value: Any, depth: int = 0) -> Any:
    """A payload the site will accept: strings cleaned, keys legal, nothing too deep or too long."""
    if depth > 6:
        return None
    if isinstance(value, dict):
        out = {}
        for key, item in list(value.items())[:90]:
            key = str(key)
            if key.startswith("_") or not _KEY.match(key):
                continue
            out[key] = clean(item, depth + 1)
        return out
    if isinstance(value, (list, tuple)):
        return [clean(item, depth + 1) for item in list(value)[:200]]
    if isinstance(value, str):
        return clean_text(value)
    if isinstance(value, bool) or value is None or isinstance(value, int):
        return value
    if isinstance(value, float):
        return value if value == value and value not in (float("inf"), float("-inf")) else None
    return clean_text(value)


def money(value: Any, places: int = 2, *, signed: bool = False) -> str:
    """The site's money format: plain digits, at most eight decimals, no exponent."""
    number = Decimal(str(value if value is not None else 0))
    number = number.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
    if number == 0 or (not signed and number < 0):
        number = ZERO.quantize(Decimal(1).scaleb(-places))  # never "-0.00", never a negative where none is allowed
    return format(number, "f")


def event_id(raw: str) -> str:
    return _ID.sub("_", raw)[:200]


def slug(value: Any) -> str:
    return re.sub(r"[^a-z0-9-]+", "-", str(value or "").lower()).strip("-")[:40]


# ------------------------------------------------------------------ quote-free, venue-free
# The site's `quoteFree` (capital/schema.js), mirrored: JavaScript's \d is [0-9], its \b and \w are ASCII,
# and its \s is the Unicode space set, so these use re.ASCII and spell that set out.
QUOTE_WORDS = ("bids?", "asks?", "offers?", "mids?", "midpoints?", "nbbo", "spreads?", "wide", "width", "ivs?", "implied",
               "vols?", "volatility", "skew", "deltas?", "gammas?", "thetas?", "vegas?", "greeks?", "premiums?", "quotes?", "quoted",
               "prices?", "priced", "pricing", "marks?", "cents?")
_WORD = "(?:" + "|".join(QUOTE_WORDS) + ")"
_JS_SPACE = "[\\t\\n\\v\\f\\r \\u00a0\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000\\ufeff]"
_FLAGS = re.ASCII | re.IGNORECASE
_Q_DECIMAL = re.compile(r"[0-9]\.[0-9]", _FLAGS)
_Q_DOLLARS = re.compile(rf"\${_JS_SPACE}?[0-9]", _FLAGS)
_Q_CENTS = re.compile(rf"[0-9]{_JS_SPACE}?¢", _FLAGS)
_Q_WORD_NUMBER = re.compile(rf"\b{_WORD}\b[^0-9\n.;]{{0,16}}[0-9]", _FLAGS)
_Q_NUMBER_WORD = re.compile(rf"[0-9][%¢]?(?:{_JS_SPACE}|-){{0,2}}{_WORD}\b", _FLAGS)
_M_NUMBER = r"[0-9](?:[0-9,]*[0-9])?(?:\.[0-9]+)?"  # "1,250.50"; never the comma after a number
_M_DOLLARS = re.compile(rf"\${_JS_SPACE}?{_M_NUMBER}", _FLAGS)
_M_CENTS = re.compile(rf"{_M_NUMBER}{_JS_SPACE}?¢", _FLAGS)
_M_DECIMAL = re.compile(r"[0-9][0-9,]*\.[0-9]+", _FLAGS)
_M_WORD_NUMBER = re.compile(rf"(\b{_WORD}\b[^0-9\n.;]{{0,16}}){_M_NUMBER}%?", _FLAGS)
_M_NUMBER_WORD = re.compile(rf"{_M_NUMBER}(?=[%¢]?(?:{_JS_SPACE}|-){{0,2}}{_WORD}\b)", _FLAGS)
_VENUE = re.compile(r"alpaca|kalshi|coinbase", re.IGNORECASE)
MASK = "…"


def quote_free(text: str) -> bool:
    """True when the site's `quoteFree` would take `text`: no decimal, no dollar or cent amount, no number
    beside a quote word."""
    return not any(pattern.search(text) for pattern in (_Q_DECIMAL, _Q_DOLLARS, _Q_CENTS, _Q_WORD_NUMBER, _Q_NUMBER_WORD))


def scrub_quotes(text: str) -> str:
    """`text` with every number that could be a quote masked as "…": "bid 1.25" -> "bid …", "30 delta" ->
    "… delta", "$120" -> "$…". Whole numbers away from quote words stay ("3 contracts", "45 DTE"). Should
    a pass leave anything the site would refuse, every digit is masked: a sentence is never published with
    a quote in it, and never shortened into a new one (the mask is one character for at least one)."""
    for _ in range(4):
        if quote_free(text):
            return text
        text = _M_DOLLARS.sub("$" + MASK, text)
        text = _M_CENTS.sub(MASK, text)
        text = _M_DECIMAL.sub(MASK, text)
        text = _M_WORD_NUMBER.sub(lambda m: m.group(1) + MASK, text)
        text = _M_NUMBER_WORD.sub(MASK, text)
    return text if quote_free(text) else re.sub(r"[0-9]", MASK, text)


def scrub_venues(text: str) -> str:
    """The page names no venue: the account is the Brokerage Account, and the venue is "the broker"."""
    return _VENUE.sub("the broker", text)


def words(value: Any, limit: int) -> str:
    """A sentence the site will show: cleaned, venue-free, cut to `limit` (JavaScript's count), then
    quote-free. Cut first: a cut can end a word early and turn "30 deltaforce" into "30 delta"."""
    text = " ".join(clean_text(value, 8000).split())
    return scrub_quotes(js_cut(scrub_venues(text), limit)).strip()


# --------------------------------------------------------------------------- the scalars
def _number(value: Any) -> Decimal | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = Decimal(str(value))
    except (ArithmeticError, ValueError, TypeError):
        return None
    return number if number.is_finite() else None


def _count(value: Any, limit: int = 1_000_000_000) -> int | None:
    number = _number(value)
    if number is None or number < 0 or number != number.to_integral_value():
        return None
    return min(int(number), limit)


def site_instant(value: Any) -> str | None:
    """Any ISO-8601 stamp (or an aware datetime, or epoch seconds) in the site's exact form: UTC, milliseconds, Z."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        parsed = datetime.fromtimestamp(float(value), tz=timezone.utc)
    elif isinstance(value, datetime):
        parsed = value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    else:
        try:
            parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
        except ValueError:
            return None
        parsed = parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return parsed.strftime("%Y-%m-%dT%H:%M:%S") + f".{parsed.microsecond // 1000:03d}Z"


def _epoch(iso: Any) -> float | None:
    at = site_instant(iso)
    return datetime.fromisoformat(at.replace("Z", "+00:00")).timestamp() if at else None


def _not_after(at: str | None, published_at: str) -> bool:
    """The site refuses a time more than a minute after the checkpoint that carries it."""
    a, b = _epoch(at), _epoch(published_at)
    return a is not None and b is not None and a <= b + 60


def _money(value: Any, *, signed: bool = False) -> str | None:
    number = _number(value)
    if number is None or (not signed and number < 0) or abs(number) >= Decimal("1e15"):
        return None
    return money(number, 2, signed=signed)


def _day(value: Any) -> str | None:
    text = str(value or "")[:10]
    if not _DAY.match(text):
        return None
    try:
        datetime.strptime(text, "%Y-%m-%d")
    except ValueError:
        return None
    return text


# ------------------------------------------------------------------------ the checkpoint
@dataclass
class SiteInputs:
    """Everything the page draws, as explicit inputs; `build_checkpoint` makes them schema 2. Anything
    not yet available stays None (a block) or empty (a list), and the page says so."""

    started_at: Any = None
    account: Mapping[str, Any] | None = None
    performance: Mapping[str, Any] | None = None
    compute: Mapping[str, Any] | None = None
    gym: Mapping[str, Any] | None = None
    agents: list[Mapping[str, Any]] = field(default_factory=list)
    structures: list[Mapping[str, Any]] = field(default_factory=list)
    trading: Mapping[str, Any] | None = None
    positions: Mapping[str, Any] | None = None
    practice: Mapping[str, Any] | None = None
    levels: Mapping[str, Any] | None = None
    rationale: Mapping[str, Any] | None = None

    @classmethod
    def of(cls, value: "SiteInputs | Mapping[str, Any]") -> "SiteInputs":
        if isinstance(value, SiteInputs):
            return value
        known = {name: value[name] for name in cls.__dataclass_fields__ if name in value}
        return cls(**known)


def site_account(value: Any, published_at: str) -> dict[str, Any] | None:
    """{equity, cash, as_of, stale}: the Brokerage Account as the broker reported it."""
    if not isinstance(value, Mapping):
        return None
    equity, cash, at = _money(value.get("equity")), _money(value.get("cash")), site_instant(value.get("as_of"))
    if equity is None or cash is None or not _not_after(at, published_at):
        return None
    return {"equity": equity, "cash": cash, "as_of": at, "stale": value.get("stale") is True}


def site_performance(value: Any, published_at: str) -> dict[str, Any] | None:
    """{start_at, start_equity, net_flows, verified_at}: the profit basis. The flows and their check travel
    together, or neither does, and a check stamped outside [start_at, published_at] is no check."""
    if not isinstance(value, Mapping):
        return None
    start, equity = site_instant(value.get("start_at")), _number(value.get("start_equity"))
    if start is None or equity is None or equity <= 0 or not _not_after(start, published_at) or _epoch(start) > _epoch(published_at):
        return None
    flows, verified = _money(value.get("net_flows"), signed=True), site_instant(value.get("verified_at"))
    if flows is None or verified is None or not (_epoch(start) <= _epoch(verified) <= _epoch(published_at)):
        flows = verified = None
    return {"start_at": start, "start_equity": money(equity, 2), "net_flows": flows, "verified_at": verified}


def site_compute(value: Any, published_at: str) -> dict[str, Any] | None:
    """{as_of, sail_usd, claude_usd, openai_usd, thetadata_usd, market_data_usd, other_usd}, each dollars or None."""
    if not isinstance(value, Mapping):
        return None
    at = site_instant(value.get("as_of")) or published_at
    if not _not_after(at, published_at):
        at = published_at
    return {"as_of": at, **{part: _money(value.get(part)) for part in COMPUTE_PARTS}}


def legacy_compute(body: dict[str, Any]) -> dict[str, Any]:
    """The checkpoint for a site older than Sept 30, 2026, which knows five compute parts: Claude back inside `other_usd`
    (#431's shape), unknown when either is. Anything without a Claude part is returned as it is."""
    compute = body.get("compute")
    if not isinstance(compute, Mapping) or "claude_usd" not in compute:
        return body
    parts = {key: value for key, value in compute.items() if key != "claude_usd"}
    claude, other = compute.get("claude_usd"), compute.get("other_usd")
    parts["other_usd"] = None if claude is None or other is None else money(Decimal(claude) + Decimal(other), 2)
    return {**body, "compute": parts}


def site_trading(value: Any, published_at: str) -> dict[str, Any] | None:
    """Profit: the complete real-options P&L (`league/trading_profit.py` `complete`), with its snapshot timestamp."""
    if not isinstance(value, Mapping):
        return None
    at = site_instant(value.get("as_of"))
    if not _not_after(at, published_at):
        return None
    return {"as_of": at, "pnl_usd": _money(value.get("pnl_usd"), signed=True)}


def _cents(value: str) -> int:
    """A published money string in whole cents (exact: the strings are made by `money`)."""
    return int((Decimal(value) * 100).to_integral_value())


def _usd(total_cents: int) -> str:
    return money(Decimal(total_cents) / 100, 2, signed=True)


def _minute(at: str | None) -> str | None:
    """A published instant down to the minute (the table shows minutes; a fill time to the millisecond is a lookup key
    into the public time and sales)."""
    return None if at is None else at[:16] + ":00.000Z"


def site_position(value: Any, published_at: str) -> dict[str, Any] | None:
    """One row of the positions table, exactly the site's fourteen fields and the site's own rules for them
    (`validPosition`, `capital/schema.js`): which position (`real:<pid>`), whose (`source`, and the agent's id when an
    agent's), what it is (its right fits its structure), how many (an open one holds at least one contract), when (to
    the minute; a closed one closed no earlier than it opened), and its P&L after fees. None when it cannot be described
    in them (it then folds into the table's `earlier` line, alerted, so the sum still holds and nothing is hidden)."""
    if not isinstance(value, Mapping):
        return None
    source, agent = value.get("source"), str(value.get("family") or value.get("agent") or "")
    under, kind, right = str(value.get("underlying") or "").upper(), value.get("structure"), value.get("right")
    legs, quantity = _count(value.get("legs")), _count(value.get("quantity"))
    held = _count(value.get("open_quantity"))
    status, expiry = value.get("status"), _day(value.get("expiry"))
    opened, closed = _minute(site_instant(value.get("opened_at"))), _minute(site_instant(value.get("closed_at")))
    pid = _count(value.get("pid"))
    pnl = value.get("pnl_usd")
    pnl = None if pnl is None else _money(pnl, signed=True)
    if (source not in POSITION_SOURCES or (source in AGENT_SOURCES and not _SLUG.match(agent)) or kind not in STRUCTURE_TYPES
            or right not in STRUCTURE_RIGHTS.get(kind, ()) or not _UNDERLYING.match(under) or legs is None or not 1 <= legs <= 4
            or quantity is None or not 1 <= quantity <= 10_000 or held is None or held > quantity or status not in ("open", "closed")
            or expiry is None or pid is None or opened is None or not _not_after(opened, published_at)
            or (value.get("pnl_usd") is not None and pnl is None)):
        return None
    if status == "closed":
        if held or closed is None or not _not_after(closed, published_at) or closed < opened:
            return None
    else:
        if held < 1:
            return None
        closed = None
    return {"id": f"real:{pid}", "source": source, "agent": agent if source in AGENT_SOURCES else None, "underlying": under,
            "structure": kind, "right": right, "legs": legs, "quantity": quantity, "open_quantity": held, "status": status,
            "expiry": expiry, "opened_at": opened, "closed_at": closed, "pnl_usd": pnl}


def _row_id(value: Any) -> str | None:
    pid = _count(value.get("pid")) if isinstance(value, Mapping) else None
    return None if pid is None else f"real:{pid}"


def site_positions(value: Any, trading: Mapping[str, Any] | None, published_at: str) -> dict[str, Any] | None:
    """{as_of, rows, earlier, other, unreconciled_usd} (the site's `validPositions`): the positions table, beside
    `trading` only.

    Rows: open positions first (newest first), then closed ones (the most recently closed first), at most
    `MAX_POSITIONS`. The oldest closed rows beyond them, and any row the schema cannot describe (of any status: the
    publisher alerts on those), fold into `earlier` {positions, pnl_usd}; only when more positions are open than the
    table holds does an open one fold (alerted too). `other` is the "Other account activity" line. `unreconciled_usd`:
    while Profit is known, Profit less every other line (the account's unreconciled figure when the book and the
    reading agree, which they do by construction), so the lines always add up; while it is unknown, the reading's own
    figure, or None. Every amount is a whole number of cents, so the sum is exact."""
    if not isinstance(value, Mapping) or not isinstance(trading, Mapping) or not isinstance(value.get("rows"), (list, tuple)):
        return None
    shown, folded, ids = [], [], set()
    for raw in value["rows"]:
        row = site_position(raw, published_at)
        if row is None or row["id"] in ids:
            folded.append(_money(raw.get("pnl_usd"), signed=True) if isinstance(raw, Mapping) else None)
            continue
        ids.add(row["id"])
        shown.append(row)
    live = sorted((r for r in shown if r["status"] == "open"), key=lambda r: (r["opened_at"], _pid_of(r)), reverse=True)
    done = sorted((r for r in shown if r["status"] == "closed"), key=lambda r: (r["closed_at"], r["opened_at"], _pid_of(r)), reverse=True)
    rows = live + done
    while len(rows) > MAX_POSITIONS and rows[-1]["status"] == "closed":
        folded.append(rows.pop()["pnl_usd"])
    if len(rows) > MAX_POSITIONS:  # more open positions than the table holds: the newest show, the rest fold (alerted)
        folded += [row["pnl_usd"] for row in rows[MAX_POSITIONS:]]
        rows = rows[:MAX_POSITIONS]
    other = value.get("other")
    if isinstance(other, Mapping):
        at = site_instant(other.get("as_of"))
        parts = {part: _money(other.get(part), signed=True) for part in OTHER_KEYS}
        other = ({"as_of": at, **parts} if at is not None and _not_after(at, published_at) and None not in parts.values() else None)
    else:
        other = None
    reading = value.get("unreconciled_usd")
    block = {"as_of": trading["as_of"], "rows": rows, "earlier": None, "other": other,
             "unreconciled_usd": None if reading is None else _money(reading, signed=True)}
    _fold(block, folded, trading.get("pnl_usd"))
    if trading.get("pnl_usd") is not None and block["unreconciled_usd"] is None:
        return None  # a Profit the lines cannot be set beside (never expected): no table, rather than one the site refuses
    return block


def _pid_of(row: Mapping[str, Any]) -> int:
    return int(str(row["id"]).split(":", 1)[1])


def _fold(block: dict[str, Any], amounts: list[str | None], profit: str | None) -> None:
    """Add rows' P&L (money strings, or None when unpriced) to `earlier`, and set `unreconciled_usd` again: while Profit
    is known, Profit less every other line (None if a line is unknown, which a known Profit rules out)."""
    if amounts:
        before = block["earlier"] or {"positions": 0, "pnl_usd": "0.00"}
        known = before["pnl_usd"] is not None and None not in amounts
        block["earlier"] = {"positions": before["positions"] + len(amounts),
                            "pnl_usd": _usd(_cents(before["pnl_usd"]) + sum(_cents(a) for a in amounts)) if known else None}
    if profit is None:
        return
    lines = [row["pnl_usd"] for row in block["rows"]] + ([block["earlier"]["pnl_usd"]] if block["earlier"] else [])
    other = block["other"]
    if other is None or None in lines:
        block["unreconciled_usd"] = None
        return
    lines += [other[part] for part in OTHER_KEYS]
    block["unreconciled_usd"] = _usd(_cents(profit) - sum(_cents(line) for line in lines))


def site_gym(value: Any, published_at: str) -> dict[str, Any] | None:
    """{as_of, trials, market_years, families_alive, families_retired}: the Gym's pace, never a result."""
    if not isinstance(value, Mapping):
        return None
    at = site_instant(value.get("as_of")) or published_at
    years = _number(value.get("market_years"))
    return {
        "as_of": at if _not_after(at, published_at) else published_at,
        "trials": _count(value.get("trials")),
        "market_years": money(years, 1) if years is not None and 0 <= years <= 100_000_000 else None,
        "families_alive": _count(value.get("families_alive"), 100_000),
        "families_retired": _count(value.get("families_retired"), 1_000_000),
    }


def site_tally(value: Any) -> dict[str, Any] | None:
    """{trades, wins, pnl_usd}: a record of closed trades, or None."""
    if not isinstance(value, Mapping):
        return None
    trades, wins, pnl = _count(value.get("trades")), _count(value.get("wins")), _money(value.get("pnl_usd"), signed=True)
    if trades is None or wins is None or pnl is None:
        return None
    return {"trades": trades, "wins": min(wins, trades), "pnl_usd": pnl}


def title(agent_id: str) -> str:
    return " ".join(part[:1].upper() + part[1:] for part in agent_id.split("-") if part)


def site_agent(value: Any, published_at: str) -> dict[str, Any] | None:
    """One agent, exactly the site's eight fields: id, family, mechanism (a sentence), structure, band, born_at,
    retired_at, and record {trials, revisions, forward, real}. The page names an agent by its id (a name in
    words would lose its number to the quote rule: "Skew Revert 2"). Its program, parameters and anything its
    program reads are never among them. None when the row cannot be shown honestly."""
    if not isinstance(value, Mapping):
        return None
    agent_id = str(value.get("id") or "")
    band = value.get("band")
    if not _SLUG.match(agent_id) or band not in BANDS:
        return None
    family = slug(value.get("family")) or agent_id
    # Only the site's eleven order types (its schema's STRUCTURE_TYPES). A family's DECLARED `long_single` (one program
    # that sends long calls and long puts, Sept 29, 2026) is none of them: it publishes as null until the site's schema
    # names it, and each of its positions and trades still shows its own type (`long_call` or `long_put`).
    structure = value.get("structure") if value.get("structure") in STRUCTURE_TYPES else None
    born, retired = site_instant(value.get("born_at")), site_instant(value.get("retired_at"))
    record = value.get("record") if isinstance(value.get("record"), Mapping) else value
    out = {
        "id": agent_id, "family": family, "mechanism": words(value.get("mechanism"), 240), "structure": structure, "band": band,
        "born_at": born if born is not None and _not_after(born, published_at) else None,
        "retired_at": retired if retired is not None and _not_after(retired, published_at) else None,
        "record": {"trials": _count(record.get("trials")) or 0, "revisions": _count(record.get("revisions"), 1_000_000) or 0,
                   "forward": site_tally(record.get("forward")), "real": site_tally(record.get("real"))},
    }
    if "progress" in value:
        from .swarm.progress import clean as clean_progress

        out["progress"] = clean_progress(value["progress"], band=band)
    return out


def site_structure(value: Any, published_at: str) -> dict[str, Any] | None:
    """One open structure, exactly the site's eleven fields (and a real one's `route` when it has one: "incubator", from
    Oct 1, 2026). Never a strike, a leg's price, a mark or
    anything else the quote feed said: what it is, whose, its maximum loss and its P&L."""
    if not isinstance(value, Mapping):
        return None
    agent = str(value.get("agent") or "")
    legs = value.get("legs")
    legs = len(legs) if isinstance(legs, (list, tuple)) else _count(legs)
    quantity, opened, expiry = _count(value.get("quantity")), site_instant(value.get("opened_at")), _day(value.get("expiry"))
    under, kind, loss = str(value.get("underlying") or "").upper(), value.get("structure"), _money(value.get("max_loss_usd"))
    if (not _SLUG.match(agent) or kind not in STRUCTURE_TYPES or not _UNDERLYING.match(under) or legs is None or not 1 <= legs <= 4
            or quantity is None or not 1 <= quantity <= 10_000 or expiry is None or loss is None):
        return None
    if opened is None or not _not_after(opened, published_at):
        opened = published_at  # an open structure is never hidden for want of a time: unknown or ahead reads as now
    raw = str(value.get("id") or f"{agent}:{under}:{kind}:{expiry}:{opened}")
    out = {"id": event_id(raw) or "structure", "agent": agent, "underlying": under, "structure": kind, "legs": legs,
           "expiry": expiry, "quantity": quantity, "real": value.get("real") is True, "opened_at": opened,
           "max_loss_usd": loss, "pnl_usd": _money(value.get("pnl_usd"), signed=True)}
    if value.get("route") in STRUCTURE_ROUTES and out["real"]:
        out["route"] = value["route"]      # a real structure's route (the incubator's: real money, never evidence)
    return out


PRACTICE_TIERS = ("validated", "train")


def site_practice(value: Any, agents: list[Mapping[str, Any]], published_at: str) -> dict[str, Any] | None:
    """{as_of, sessions, capital_usd, totals {families, trades, wins, pnl_usd}, rows}: THE PRACTICE LEAGUE (Sept 29, 2026),
    shadow trades on live quotes under the Gym's fill rules, never real money: never Profit, never `trading`,
    `positions` or `performance`, never a forward record. One row per family, exactly: agent, family (its lineage), structure
    (a site type or null), tier ("validated" | "train"), status ("alive" while the agent is alive on the page, else
    "retired"), sessions, trades, wins, pnl_usd (realized, cents) and return_on_risk (P&L over maximum loss, 2 places, or
    null). Never a price, strike, leg, expiry, minute, trade date, version, code, parameter, Validation figure or mechanism
    (the mechanism is the agent's). At most `MAX_PRACTICE_ROWS` rows: the alive first by trades, then the retired by their
    last session; the totals are over every row. None when there is nothing to show honestly."""
    if not isinstance(value, Mapping):
        return None
    at = site_instant(value.get("as_of"))
    if at is None or not _not_after(at, published_at):
        return None
    alive = {a["id"] for a in agents if a.get("band") != "retired"}
    rows, seen = [], set()
    for raw in value.get("rows") or []:
        if not isinstance(raw, Mapping):
            continue
        agent = str(raw.get("family") or "")
        tier = raw.get("tier")
        trades, wins, sessions = _count(raw.get("trades")), _count(raw.get("wins")), _count(raw.get("sessions"), 10_000)
        pnl = _money(raw.get("pnl_usd"), signed=True)
        if (not _SLUG.match(agent) or agent in seen or tier not in PRACTICE_TIERS or trades is None or wins is None
                or sessions is None or pnl is None):
            continue
        seen.add(agent)
        ror = _number(raw.get("return_on_risk"))
        last = _day(raw.get("last_day")) or ""
        rows.append((agent in alive, last, {
            "agent": agent, "family": slug(raw.get("lineage")) or agent,
            "structure": raw.get("structure") if raw.get("structure") in STRUCTURE_TYPES else None,
            "tier": tier, "status": "alive" if agent in alive else "retired", "sessions": sessions, "trades": trades,
            "wins": min(wins, trades), "pnl_usd": pnl,
            "return_on_risk": money(ror, 2, signed=True) if ror is not None and abs(ror) < 1000 else None}))
    if not rows:
        return None
    living = sorted((r for ok, _, r in rows if ok), key=lambda r: (-r["trades"], r["agent"]))
    retired = sorted(((last, r) for ok, last, r in rows if not ok), key=lambda x: (x[0], x[1]["agent"]), reverse=True)
    shown = (living + [r for _, r in retired])[:MAX_PRACTICE_ROWS]
    every = [r for _, _, r in rows]
    capital = _money(value.get("capital_usd"))
    return {"as_of": at, "sessions": _count(value.get("sessions"), 10_000) or 0, "capital_usd": capital or "10000.00",
            "totals": {"families": len(every), "trades": sum(r["trades"] for r in every),
                       "wins": sum(r["wins"] for r in every),
                       "pnl_usd": _usd(sum(_cents(r["pnl_usd"]) for r in every))},
            "rows": shown}


# --------------------------------------------------------------------------- the swarm window
_THESIS_MARKS = re.compile(r"[:()\[\]{}<>=_`#|\\]")
_DIGIT = re.compile(r"[0-9]")


def thesis_words(value: Any, limit: int) -> str | None:
    """`value` as the site's `thesisWords(value, limit)` takes it, or None, never a partial string: the publisher's `words`
    (no markup, no venue, quote-free, not blank), then no digit, no colon, no bracket and no mark only code or a formula
    uses, at most `limit` long as JavaScript counts it, and (the swarm's rule, `public.thesis_text`) no number written as a
    word but the pronoun "one". The swarm filtered it first, against the program's parameter names too."""
    from .swarm.public import SENTENCE, numbered

    if not isinstance(value, str) or any(ch.isdigit() for ch in value) or _THESIS_MARKS.search(value):
        return None  # refused before `words` could mask it into a partial string
    text = words(value, 8000)
    if (not text or js_length(text) > limit or _DIGIT.search(text) or _THESIS_MARKS.search(text) or not quote_free(text)
            or _VENUE.search(text) or any(numbered(sentence) for sentence in SENTENCE.split(text))):
        return None
    return text


def _counter(value: Any, limit: int = 1_000_000_000) -> int | None:
    """A JSON counter (a whole number from 0 to `limit`), never clamped: anything else is unknown."""
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= limit:
        return None
    return value


def site_funnel(value: Any, published_at: str) -> dict[str, Any] | None:
    """{since, born, practice, validation, tuition, incubator, looks, looks_passed, candidate, probe, sized, retired,
    calibration, live_test}: how many families reached each level since the reset (`since`), each a counter or None
    (unknown). A chain that does not narrow (`FUNNEL_CHAINS`; never expected: the House counts unions) is unknown whole,
    never shown wrong. None without a `since`."""
    if not isinstance(value, Mapping):
        return None
    since = site_instant(value.get("since"))
    if since is None or not _not_after(since, published_at):
        return None
    out: dict[str, Any] = {"since": since, **{key: _counter(value.get(key)) for key in FUNNEL_KEYS if key != "since"}}
    for chain in FUNNEL_CHAINS:
        known = [out[key] for key in chain if out[key] is not None]
        if any(a > b for a, b in zip(known, known[1:])):
            for key in chain:
                out[key] = None
    return out


def site_levels(value: Any, agents: list[Mapping[str, Any]], published_at: str) -> dict[str, Any] | None:
    """{as_of, agents: [{id, level}], funnel}: where each agent on the page stands in the game (the swarm window, Oct 1,
    2026; `league/site_window.py`). An entry names an agent the page shows, once, at a level its band allows
    (`LEVELS_BY_BAND`); any other entry is left out, never sent. None when the block cannot be shown honestly."""
    if not isinstance(value, Mapping):
        return None
    at = site_instant(value.get("as_of"))
    if at is None or not _not_after(at, published_at):
        return None
    bands = {a["id"]: a["band"] for a in agents}
    rows, seen = [], set()
    for raw in value.get("agents") or []:
        if not isinstance(raw, Mapping):
            continue
        agent_id, level = str(raw.get("id") or ""), raw.get("level")
        if agent_id in bands and agent_id not in seen and level in LEVELS_BY_BAND.get(bands[agent_id], ()):
            seen.add(agent_id)
            rows.append({"id": agent_id, "level": level})
    funnel = site_funnel(value.get("funnel"), published_at)
    if funnel is None:
        return None
    return {"as_of": at, "agents": rows[:MAX_AGENTS], "funnel": funnel}


def site_rationale(value: Any, agents: list[Mapping[str, Any]], positions: Mapping[str, Any] | None,
                   published_at: str) -> dict[str, Any] | None:
    """{as_of, agents: [{id, thesis}], trades: [{id, route, open_why, close_why, exit, max_loss_usd}]}: why each agent
    trades, in its family's own whole sentences, and why each real position in the table opened and closed (the swarm
    window, Oct 1, 2026). A thesis is `thesis_words` at most 280, a reason at most 80, else None; a route fits the row's
    source (`ROUTES_BY_SOURCE`); the House's rows carry no reason, an open row no close reason and no exit; `exit` is one
    of `EXITS`; `max_loss_usd` whole cents. An entry for an agent the page does not show, or a row the table does not
    list (it folded into `earlier`), is left out; `trades` is [] without a table. None when the block cannot be shown."""
    if not isinstance(value, Mapping):
        return None
    at = site_instant(value.get("as_of"))
    if at is None or not _not_after(at, published_at):
        return None
    roster = {a["id"] for a in agents}
    theses, seen = [], set()
    for raw in value.get("agents") or []:
        if not isinstance(raw, Mapping):
            continue
        agent_id = str(raw.get("id") or "")
        if agent_id in roster and agent_id not in seen:
            seen.add(agent_id)
            theses.append({"id": agent_id, "thesis": thesis_words(raw.get("thesis"), THESIS_CHARS)})
    listed = {row["id"]: row for row in (positions or {}).get("rows") or []} if isinstance(positions, Mapping) else {}
    given = {str(raw.get("id")): raw for raw in value.get("trades") or [] if isinstance(raw, Mapping)}
    trades = []
    for row_id, row in listed.items():  # the table's own order: open first, then the most recently closed
        raw = given.get(row_id)
        if raw is None:
            continue
        house = row["source"] not in AGENT_SOURCES
        is_open = row["status"] == "open"
        route = raw.get("route") if raw.get("route") in ROUTES_BY_SOURCE.get(row["source"], ()) else None
        loss = _money(raw.get("max_loss_usd"))
        trades.append({"id": row_id, "route": route,
                       "open_why": None if house else thesis_words(raw.get("open_why"), WHY_CHARS),
                       "close_why": None if house or is_open else thesis_words(raw.get("close_why"), WHY_CHARS),
                       "exit": None if is_open or raw.get("exit") not in EXITS else raw.get("exit"),
                       "max_loss_usd": loss})
    return {"as_of": at, "agents": theses[:MAX_AGENTS], "trades": trades[:MAX_POSITIONS]}


def _prune_window(body: dict[str, Any]) -> None:
    """The window's entries for agents the page still shows and rows the table still lists, only."""
    roster = {a["id"] for a in body["agents"]}
    listed = {row["id"] for row in ((body.get("positions") or {}).get("rows") or [])}
    if isinstance(body.get("levels"), dict):
        body["levels"]["agents"] = [row for row in body["levels"]["agents"] if row["id"] in roster]
    if isinstance(body.get("rationale"), dict):
        body["rationale"]["agents"] = [row for row in body["rationale"]["agents"] if row["id"] in roster]
        body["rationale"]["trades"] = [row for row in body["rationale"]["trades"] if row["id"] in listed]


def windowless(body: Mapping[str, Any]) -> dict[str, Any]:
    """The checkpoint without the swarm window (a site before Oct 1, 2026 refuses it)."""
    return {key: item for key, item in body.items() if key not in ("levels", "rationale")}


def build_checkpoint(inputs: "SiteInputs | Mapping[str, Any]", published_at: str) -> dict[str, Any]:
    """The checkpoint the site takes (schema 2), from explicit inputs, every block allowlisted. The agents
    are ordered for the page (Sized, Probe, Candidate, Gym, then the retired an open or closed real position names, then
    the newest other retired), at most 160 with at most 24 other retired among them; structures real first, at most
    100. The swarm window (`levels` and `rationale`, together or neither) is checked against the agents and the table
    the page gets. Then it is fitted under 512 KiB."""
    given = SiteInputs.of(inputs)
    started = site_instant(given.started_at)
    agents, seen, pinned = [], set(), set()
    for raw in given.agents or []:
        row = site_agent(raw, published_at)
        if row is not None and row["id"] not in seen:
            seen.add(row["id"])
            agents.append(row)
            if raw.get("pinned") is True:
                pinned.add(row["id"])  # a real position names it: its card keeps a name and a record (never the 24 cap)
    living = sorted((a for a in agents if a["band"] != "retired"), key=lambda a: (BAND_RANK[a["band"]], a["id"]))
    dead = sorted((a for a in agents if a["band"] == "retired"), key=lambda a: a["retired_at"] or "", reverse=True)
    shown = living[:MAX_AGENTS]
    shown += [a for a in dead if a["id"] in pinned][:max(0, MAX_AGENTS - len(shown))]
    shown += [a for a in dead if a["id"] not in pinned][:max(0, min(MAX_DEAD_SHOWN, MAX_AGENTS - len(shown)))]
    structures, ids = [], set()
    for raw in given.structures or []:
        row = site_structure(raw, published_at)
        if row is not None and row["id"] not in ids:
            ids.add(row["id"])
            structures.append(row)
    structures.sort(key=lambda s: (not s["real"], -Decimal(s["max_loss_usd"]), s["id"]))
    body = {
        "schema_version": SCHEMA_VERSION,
        "published_at": published_at,
        "run": {"started_at": started if started is not None and _not_after(started, published_at) else None},
        "account": site_account(given.account, published_at),
        "performance": site_performance(given.performance, published_at),
        "compute": site_compute(given.compute, published_at),
        "gym": site_gym(given.gym, published_at),
        "agents": shown,
        "structures": structures[:MAX_STRUCTURES],
    }
    if given.trading is not None:
        body["trading"] = site_trading(given.trading, published_at)
        positions = site_positions(given.positions, body["trading"], published_at) if given.positions is not None else None
        if positions is not None:
            body["positions"] = positions
    practice = site_practice(given.practice, shown, published_at) if given.practice is not None else None
    if practice is not None:
        body["practice"] = practice
    if given.levels is not None and given.rationale is not None:
        levels = site_levels(given.levels, shown, published_at)
        rationale = site_rationale(given.rationale, shown, body.get("positions"), published_at)
        if levels is not None and rationale is not None:
            body["levels"], body["rationale"] = levels, rationale
    return fit(body, pinned)


def fit(body: dict[str, Any], pinned: Any = ()) -> dict[str, Any]:
    """The body inside the site's byte limit: the oldest retired agents, then the lowest band's, then the
    shadow book's smallest structures leave first, then the positions table's oldest rows fold into its
    `earlier` line, the oldest closed first (a row never simply leaves: the table must still add up to Profit;
    the publisher alerts on an open one folded). An agent a real position names (`pinned`) leaves only after every
    other. The swarm window keeps entries only for the agents and rows that stay. The totals the page shows are the
    House's, not a count."""
    size = lambda: len(canonical(body).encode("utf-8"))  # noqa: E731
    positions = body.get("positions")
    pinned = set(pinned or ())
    while size() > MAX_CHECKPOINT_BYTES and (body["agents"] or body["structures"] or (positions and positions["rows"])):
        if body["agents"]:
            spare = [i for i, agent in enumerate(body["agents"]) if agent["id"] not in pinned]
            body["agents"].pop(spare[-1] if spare else -1)
        elif body["structures"]:
            body["structures"].pop()
        else:
            _fold(positions, [positions["rows"].pop()["pnl_usd"] for _ in range(min(10, len(positions["rows"])))],
                  (body.get("trading") or {}).get("pnl_usd"))
        _prune_window(body)
    if "levels" in body and size() > MAX_CHECKPOINT_BYTES:
        body.pop("levels"), body.pop("rationale")
    _prune_window(body)
    return body


# --------------------------------------------------------------------------------- the tape
def _stream_agent(agent: Any) -> str | None:
    agent = str(agent or "")
    return agent if agent != HOUSE and _SLUG.match(agent) else None


def trade_of(p: Mapping[str, Any], *, close: bool, pnl: Any = None) -> dict[str, Any] | None:
    """An `agent.trade` payload from a fill or a settlement of an option or a structure held as one
    instrument, or None for anything else. Never its price, its strikes or its legs' codes: which
    underlying, which structure, how many legs and contracts, its (nearest) expiry, and what it can
    lose (an open) or what it made (a close)."""
    from . import structure_core

    instrument = p.get("instrument") if isinstance(p.get("instrument"), Mapping) else {}
    quantity = _count(p.get("quantity"))
    if not quantity or not 1 <= quantity <= 10_000:
        return None
    code = str(instrument.get("market_id") or "")
    try:
        spec = structure_core.spec_of_code(code) if structure_core.is_code(code) else None
    except ValueError:
        return None
    if spec is not None:
        under, kind, legs, expiry = spec.underlying, spec.type, len(spec.legs), spec.expiry
    elif instrument.get("asset_class") == "option" and str(instrument.get("right") or "").lower()[:1] in ("c", "p"):
        under, legs, expiry = str(instrument.get("symbol") or "").split(" ")[0].upper(), 1, instrument.get("expiry")
        kind = "long_call" if str(instrument.get("right")).lower().startswith("c") else "long_put"
    else:
        return None
    if kind not in STRUCTURE_TYPES or not _UNDERLYING.match(under) or _day(expiry) is None:
        return None
    multiplier = _number(instrument.get("multiplier")) or Decimal(100)
    price = _number(p.get("price"))
    loss = _number(p.get("max_loss_usd"))
    if loss is None and not close and price is not None:
        loss = price * multiplier * quantity  # a held structure's price is what it can lose a share
    out = {"action": "close" if close else "open", "real": p.get("real_money") is True, "underlying": under, "structure": kind, "legs": legs,
           "expiry": _day(expiry), "quantity": quantity, "max_loss_usd": _money(loss), "pnl_usd": _money(pnl, signed=True) if close else None,
           "why": words(p.get("entry_reason") if close and p.get("entry_reason") else p.get("reason"), 240)}
    if not close and out["max_loss_usd"] is None:
        return None
    if close and out["pnl_usd"] is None:
        return None
    return out


def to_events(entry: Entry) -> list[dict[str, Any]]:
    """The site events one ledger row becomes: none, or one."""
    if not entry.public:
        return []
    p = public_view(entry.payload)
    kind = entry.kind
    agent = _stream_agent(entry.agent)
    out: tuple[str, str, dict[str, Any]] | None = None  # (stream, kind, payload)
    if kind == "agent.thought" and agent:
        text = words(p.get("text"), 2000)
        out = (f"agent:{agent}", "agent.note", {"text": text}) if text else None
    elif kind == "swarm.note" and agent:  # a swarm researcher's notebook entry (league/swarm/), in its own words
        text = words(p.get("text"), 2000)
        out = (f"agent:{agent}", "agent.note", {"text": text}) if text else None
    elif kind == "agent.research" and agent and p.get("tool") == "summary":
        text = words("Research: " + str(p.get("summary") or ""), 2000) if str(p.get("summary") or "").strip() else ""
        out = (f"agent:{agent}", "agent.note", {"text": text}) if text else None
    elif kind == "book.fill" and agent and p.get("source") in ("venue", "cross"):
        closing = p.get("side") == "sell" and p.get("realized") is not None
        trade = trade_of(p, close=closing, pnl=p.get("realized")) if closing or p.get("side") == "buy" else None
        out = (f"agent:{agent}", "agent.trade", trade) if trade else None
    elif kind == "book.settle" and agent:
        trade = trade_of(p, close=True, pnl=p.get("pnl"))
        out = (f"agent:{agent}", "agent.trade", trade) if trade else None
    elif kind == "floor.mark" and "brokerage_equity" in p:
        equity, cash, at = _money(p.get("brokerage_equity")), _money(p.get("brokerage_cash")), site_instant(p.get("as_of"))
        out = ("account", "account.mark", {"equity": equity, "cash": cash, "as_of": at}) if None not in (equity, cash, at) else None
    else:
        message = league_news(kind, entry.agent, p)
        text = words(message, 300) if message else ""
        out = ("swarm", "swarm.news", {"agent": agent, "text": text}) if text else None
    if out is None:
        return []
    stream, site_kind, payload = out
    return [{
        "id": event_id(entry.id), "stream": stream, "kind": site_kind, "at": site_instant(entry.at) or entry.at, "payload": payload,
        "digest": hashlib.sha256(canonical(payload).encode("utf-8")).hexdigest(),
    }]


def league_news(kind: str, agent: str, p: Mapping[str, Any]) -> str | None:
    """One plain sentence for the swarm's own events (births, band moves, retirements, audits, new code),
    before `words` masks it. A sentence about an agent starts with its verb: the agent rides the event's own
    `agent` field, and the page puts its name in front. Anything else says nothing."""
    if kind in ("agent.born", "swarm.born"):  # swarm.*: the options swarm's own rows (league/swarm/hook.py mirrors them)
        origin = "forked from its parent" if p.get("parent") else "a new family"
        mechanism = str(p.get("mechanism") or "").strip()
        return f"is born, {origin}{': ' + mechanism if mechanism else '.'}"
    if kind in ("agent.died", "swarm.retired"):
        return f"retired: {str(p.get('cause') or 'no reason given')}.".replace("..", ".")
    if kind in ("eval.verdict", "swarm.band"):
        start, end = p.get("band_from"), p.get("band_to")
        if start in BANDS and end in BANDS and start != end:
            reason = " ".join(str(p.get("reason") or "").split()).rstrip(". ")
            return f"moves from {BAND_WORDS[start]} to {BAND_WORDS[end]}{': ' + reason if reason else ''}."
        return None
    if kind == "audit.verdict":
        return f"{'approved' if p.get('approve') else 'refused'} for real money by the auditor. {p.get('summary') or ''}".strip()
    if kind == "ops.deploy":
        if p.get("action") == "deploying":
            return f"New code on main: release {p.get('release')} is on the canary. The watchdog promotes it only if it stays healthy."
        if p.get("action") == "held":
            reasons = [str(r) for r in p.get("reasons") or []]
            shown = "; ".join(reasons[:1] + (reasons[-1:] if len(reasons) > 1 else []))
            return (f"New code on main ({str(p.get('sha') or '')[:12]}) waits for the release train: the House takes new code at most "
                    f"every few hours, never in the US stock session or just after a restart. {shown[:1].upper()}{shown[1:]}").strip()
        return None
    return None


# ------------------------------------------------------------------------ the owner's money
class Flows:
    """The owner's deposits less withdrawals on the Brokerage Account since `start_at`, read from the
    account's own activity history (`ltcm.performance.alpaca_flows`, which raises on any activity it
    cannot classify rather than count it as profit). Read off the publishing path, every five minutes;
    a failed read clears the figure at once, and a figure older than ten minutes is no figure."""

    def __init__(self, broker: Any, start_at: str, *, clock: Callable[[], float] = time.time,
                 reader: Callable[[], Decimal] | None = None, threaded: bool = True):
        self.start_at, self.clock, self.threaded = start_at, clock, threaded
        self.reader = reader or (lambda: self._alpaca(broker))
        self.lock = threading.Lock()
        self.busy, self.attempted = False, float("-inf")
        self.net: Decimal | None = None
        self.verified: float | None = None

    def _alpaca(self, broker: Any) -> Decimal:
        from ltcm.performance import alpaca_flows

        return sum((value for _venue, _when, value in alpaca_flows(broker, _epoch(self.start_at))), ZERO)

    def _refresh(self) -> None:
        try:
            net, verified = Decimal(str(self.reader())), self.clock()
        except Exception:  # noqa: BLE001 - an unreadable history is no profit figure, never zero flows
            net, verified = None, None
        with self.lock:
            self.net, self.verified, self.busy = net, verified, False

    def read(self) -> tuple[Decimal | None, float | None]:
        now = self.clock()
        with self.lock:
            due = not self.busy and now - self.attempted >= FLOWS_EVERY_SECONDS
            if due:
                self.busy, self.attempted = True, now
        if due:
            if self.threaded:
                threading.Thread(target=self._refresh, daemon=True, name="brokerage-flows").start()
            else:
                self._refresh()
        with self.lock:
            fresh = self.verified is not None and 0 <= self.clock() - self.verified <= FLOWS_FRESH_SECONDS
            return (self.net, self.verified) if fresh else (None, None)


# ------------------------------------------------------------------------------- publisher
class _Folds:
    """What the checkpoint reads from the whole ledger, folded once and then from the new rows only
    (the ledger is append-only and every fold is in sequence order)."""

    KINDS = ("ops.budget", "eval.trial", "agent.strategy", "agent.born", "book.fill", "book.settle")

    def __init__(self, ledger: Any) -> None:
        self.ledger = ledger
        self.lock = threading.Lock()
        self.seq = 0
        self.sail: Decimal | None = None  # the Sail meter's falls (`ops.budget` "sail" with `spent_usd`); None: never metered
        self.trials: dict[str, int] = {}
        self.revisions: dict[str, int] = {}
        self.mechanism: dict[str, str] = {}
        self.tallies: dict[tuple[str, bool], list[Any]] = {}  # (agent, real) -> [trades, wins, pnl]
        self.real_options_seen = False

    def advance(self) -> "_Folds":
        with self.lock:
            for entry in self.ledger.iter(kinds=self.KINDS, after=self.seq):
                self._fold(entry)
                self.seq = entry.seq
        return self

    def _close(self, agent: str, real: bool, pnl: Any) -> None:
        amount = _number(pnl)
        if amount is None:
            return
        row = self.tallies.setdefault((agent, real), [0, 0, ZERO])
        row[0] += 1
        row[1] += 1 if amount > 0 else 0
        row[2] += amount

    def _fold(self, entry: Entry) -> None:
        kind, p, agent = entry.kind, entry.payload, entry.agent
        if (kind in ("book.fill", "book.settle") and p.get("real_money") is True
                and (p.get("instrument") or {}).get("asset_class") == "option"):
            self.real_options_seen = True
        if kind == "ops.budget":
            if p.get("what") == "sail" and p.get("spent_usd") is not None:
                self.sail = (ZERO if self.sail is None else self.sail) + Decimal(str(p["spent_usd"]))
        elif kind == "eval.trial":
            self.trials[agent] = self.trials.get(agent, 0) + 1
        elif kind == "agent.strategy":
            self.revisions[agent] = self.revisions.get(agent, 0) + 1
        elif kind == "agent.born":
            if p.get("mechanism"):
                self.mechanism[agent] = str(p["mechanism"])
        elif kind == "book.fill":
            if p.get("side") == "sell" and p.get("realized") is not None and p.get("source") in ("venue", "cross"):
                self._close(agent, p.get("real_money") is True, p.get("realized"))
        elif kind == "book.settle":
            self._close(agent, p.get("real_money") is True, p.get("pnl"))

    def tally(self, agent: str, real: bool) -> dict[str, Any] | None:
        row = self.tallies.get((agent, real))
        return None if row is None else {"trades": row[0], "wins": row[1], "pnl_usd": row[2]}


class Publisher:
    def __init__(
        self,
        site_url: str,
        token_source: Callable[[], str],
        state_path: str | Path,
        *,
        tape: str | None = None,
        performance: Mapping[str, Any] | None = None,
        real_brokers: Mapping[str, Any] | None = None,
        opener: Any = None,
        clock: Callable[[], float] = time.time,
        gateway_url: str | None = None,
        gateway_token: Callable[[], str] | None = None,
    ):
        base = site_url.rstrip("/") + "/api/capital"
        self.base = base + (f"/t/{tape}" if tape else "")
        self.token_source = token_source
        self.state_path = Path(state_path)
        self.performance = dict(performance or {})
        # The Brokerage Account is the one real account. It is read for its balance and its funding only.
        brokers = dict(real_brokers or {})
        self.broker = brokers.get("brokerage") or brokers.get("alpaca")
        self.opener = opener or urllib.request.urlopen
        self.clock = clock
        self._state = self._load()
        self._last_account: dict[str, Any] | None = None
        self._folds: _Folds | None = None
        start = site_instant(self.performance.get("start_at"))
        self.flows = Flows(self.broker, start, clock=clock) if self.broker is not None and start else None
        # The positions table's account side (`league/account_activity.py`): Profit is unknown without a fresh reading.
        from .account_activity import ActivityLedger

        self.activity = ActivityLedger(self.broker, start, self.state_path.parent, clock=clock) if self.broker is not None and start else None
        self._activity_saved: float | None = None
        if self.activity is not None and self._state.get("activity") and self.activity.restore(self._state["activity"]):
            self._activity_saved = self.activity.read_at  # a restart keeps Profit: the last reading, while it is fresh
        self._positions_refused: float | None = None
        self._positions_refusal: str | None = None
        self._practice_refused: float | None = None
        self._practice_refusal: str | None = None
        self._window_refused: float | None = None
        self._window_refusal: str | None = None
        self._activity_error: str | None = None
        self._inputs_positions: Mapping[str, Any] | None = None

    def _load(self) -> dict[str, Any]:
        try:
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            state = {}
        state.setdefault("cursor", 0)
        state.setdefault("last_mark", 0.0)
        return state

    def _save(self) -> None:
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._state), encoding="utf-8")
        os.chmod(tmp, 0o600)
        os.replace(tmp, self.state_path)

    def _folded(self, house: Any) -> _Folds:
        if self._folds is None or self._folds.ledger is not house.ledger:
            self._folds = _Folds(house.ledger)
        return self._folds.advance()

    # --------------------------------------------------------------- transport
    def post(self, path: str, body: Mapping[str, Any]) -> tuple[int, Any]:
        request = urllib.request.Request(
            self.base + path, data=canonical(body).encode("utf-8"), method="POST",
            headers={"Authorization": "Bearer " + self.token_source(), "Content-Type": "application/json", "Accept": "application/json", "User-Agent": "ltcm-floor/2.0"},
        )
        try:
            with self.opener(request, timeout=30) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read()[:300].decode("utf-8", "replace")
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise PublishError(f"the site did not answer: {type(exc).__name__}") from None

    def _send(self, events: list[dict[str, Any]]) -> int:
        """Send a batch; when the site refuses it, halve it until the one bad event is alone, and drop that one."""
        if not events:
            return 0
        status, reply = self.post("/events", {"schema_version": SCHEMA_VERSION, "events": events})
        if status == 200:
            return len(events)
        if status in (400, 409) and len(events) > 1:
            half = len(events) // 2
            return self._send(events[:half]) + self._send(events[half:])
        if status in (400, 409):
            return 0  # one event the site will never take: skipped, so it cannot block the tape
        raise PublishError(f"the site refused the events: HTTP {status} {reply}", status=status)

    # ------------------------------------------------------------------ publish
    def publish(self, house: Any) -> dict[str, Any]:
        self.mark_floor(house)
        sent = 0
        while True:
            batch = house.ledger.read(after=int(self._state["cursor"]), limit=400, public_only=False)
            if not batch:
                break
            events: list[dict[str, Any]] = []
            for entry in batch:
                events.extend(to_events(entry))
            for start in range(0, len(events), MAX_BATCH):
                sent += self._send(events[start:start + MAX_BATCH])
            self._state["cursor"] = batch[-1].seq
            self._save()
        body = checkpoint = self.checkpoint(house)
        # Three older shapes a site may need, each offered again half an hour after the site refused it; either repository
        # may deploy first. `windowless`: without the swarm window (`levels` and `rationale`, a site before Oct 1, 2026),
        # tried first on any refusal: a site that then takes it refused the window. `older`: without the practice league
        # and with Claude inside `other_usd` (a site before Sept 30, 2026: `legacy_compute`). `tableless`: without the
        # positions table (a site before Sept 28, or a row or a sum it rejects; the window then names no trade). When the
        # site refuses the windowless checkpoint too, the ladder goes on without the window: each older shape alone (the
        # table first, so a bad row never costs the newer shape), then both; only the shapes the site then took are marked
        # refused (the window is offered again next time), and the warning quotes the site's reply.
        newer = lambda value: "practice" in value or "claude_usd" in (value.get("compute") or {})  # noqa: E731
        older = lambda value: legacy_compute({key: item for key, item in value.items() if key != "practice"})  # noqa: E731
        tableless = lambda value: {key: ({**item, "trades": []} if key == "rationale" and isinstance(item, Mapping) else item)  # noqa: E731
                                   for key, item in value.items() if key != "positions"}
        windowed = lambda value: "levels" in value or "rationale" in value  # noqa: E731
        refused = self._window_refused
        if windowed(body) and refused is not None and self.clock() - refused < WINDOW_RETRY_SECONDS:
            body = windowless(body)
        refused = self._practice_refused
        if newer(body) and refused is not None and self.clock() - refused < PRACTICE_RETRY_SECONDS:
            body = older(body)
        refused = self._positions_refused
        if "positions" in body and refused is not None and self.clock() - refused < POSITIONS_RETRY_SECONDS:
            body = tableless(body)
        status, reply = self.post("/checkpoint", body)
        dropped = (False, False)
        window_dropped = False
        if status == 400 and windowed(body):
            plain = windowless(body)
            retried, again = self.post("/checkpoint", plain)
            if retried in (200, 409):
                why = " ".join(str(reply).split())[:200]
                if why != self._window_refusal:
                    self._warn(house, f"the site refused the swarm window (levels and rationale: old site, or an entry it "
                                      f"rejects): the checkpoint went without it, and it is offered again in half an hour "
                                      f"(the site said: {why})")
                self._window_refused, self._window_refusal = self.clock(), why
                window_dropped = True
            body, status, reply = plain, retried, again
        if status == 400:
            tries = [(False, True)] if "positions" in body else []
            tries += [(True, False)] if newer(body) else []
            tries += [(True, True)] if "positions" in body and newer(body) else []
            for drop_newer, drop_table in tries:
                plain = tableless(body) if drop_table else body
                plain = older(plain) if drop_newer else plain
                retried, again = self.post("/checkpoint", plain)
                if retried not in (200, 409):
                    continue
                why = " ".join(str(reply).split())[:200]
                if drop_newer:
                    if why != self._practice_refusal:
                        self._warn(house, f"the site refused the practice league block or Claude's own compute part (old "
                                          f"site, or a row it rejects): the checkpoint went without the block and with Claude "
                                          f"inside other_usd, and both are offered again in half an hour (the site said: {why})")
                    self._practice_refused, self._practice_refusal = self.clock(), why
                if drop_table:
                    if why != self._positions_refusal:
                        self._alert(house, f"the site refused the positions table (old site, or a row it rejects): the "
                                           f"checkpoint went without it and the table is offered again in half an hour (the "
                                           f"site said: {why})")
                    self._positions_refused, self._positions_refusal = self.clock(), why
                dropped, body, status, reply = (drop_newer, drop_table), plain, retried, again
                break
        if status in (200, 409):
            # Taken with a shape: it is offered every publish again.
            if not window_dropped and windowed(body):
                self._window_refused = self._window_refusal = None
            if not dropped[0] and newer(body):
                self._practice_refused = self._practice_refusal = None
            if not dropped[1] and "positions" in body:
                self._positions_refused = self._positions_refusal = None
        if status not in (200, 409):
            raise PublishError(f"the site refused the checkpoint: HTTP {status} {reply}", status=status)
        self._alert_positions(house, checkpoint)
        return {"events": sent, "checkpoint": status}

    def _warn(self, house: Any, text: str) -> None:
        alert = getattr(house, "alert", None)
        if callable(alert):
            try:
                alert("warning", text)
            except Exception:  # noqa: BLE001 - an alert that cannot be written never stops a publish
                pass

    def _alert(self, house: Any, text: str) -> None:
        alert = getattr(house, "alert", None)
        if callable(alert):
            try:
                alert("warning", f"positions table: {text}")
            except Exception:  # noqa: BLE001 - an alert that cannot be written never stops a publish
                pass

    def _alert_positions(self, house: Any, body: Mapping[str, Any]) -> None:
        """Each new reason the positions table does not reconcile or Profit is unknown, once (remembered in
        publish.json): the account's activity problems and what keeps Profit unknown (`ActivityLedger.problems`), each
        new unreconciled line, and each position the table does not list for a reason other than its age (a row its
        fields cannot describe, or an open one past the table's length or its byte limit). A failed read of the account
        is said when it starts or changes (Profit is unknown once the last reading ages out). The last reading is kept
        in publish.json, so a restart keeps Profit."""
        if self.activity is None:
            return
        problems = self.activity.problems()
        block = body.get("positions") or {}
        difference = block.get("unreconciled_usd")
        if difference not in (None, "0.00"):
            problems.append(f"the table carries an unreconciled {difference} beside the positions")
        problems += self._unlisted(block, body.get("published_at"))
        said = list(self._state.get("positions_alerted") or [])
        fresh = [problem for problem in dict.fromkeys(problems) if problem not in said]
        for problem in fresh:
            self._alert(house, problem)
        if fresh:
            self._state["positions_alerted"] = (said + fresh)[-500:]
        saved = self.activity.saved()
        renewed = saved is not None and saved["read_at"] != self._activity_saved
        if renewed:
            self._state["activity"], self._activity_saved = saved, saved["read_at"]
        if fresh or renewed:
            self._save()
        error = self.activity.error
        if error and error != self._activity_error:
            self._alert(house, f"the account's activity could not be read, so Profit is unknown once the last reading ages out ({error})")
        self._activity_error = error

    def _unlisted(self, block: Mapping[str, Any], published_at: Any) -> list[str]:
        """The positions the table folded into its `earlier` line for a reason other than being old and closed."""
        given = self._inputs_positions
        if not block or not given or not isinstance(given.get("rows"), (list, tuple)) or not published_at:
            return []  # no table published at all: nothing was folded
        listed = {row.get("id") for row in block.get("rows") or []}
        out = []
        for raw in given["rows"]:
            row_id = _row_id(raw) or "a position with no id"
            if row_id in listed:
                continue
            if site_position(raw, str(published_at)) is None:
                out.append(f"position {row_id} cannot be described in the table's fields: it is counted in the "
                           "not-listed line")
            elif isinstance(raw, Mapping) and raw.get("status") == "open":
                out.append(f"open position {row_id} is not listed (the table is full): it is counted in the not-listed line")
        return out

    # -------------------------------------------------------------- the account
    def account(self, house: Any = None) -> dict[str, Any] | None:
        """The Brokerage Account, read now: {equity, cash, as_of, stale}. A read that fails republishes
        the last good one marked stale (the page then shows no profit); with none, None."""
        if self.broker is None:
            return None
        try:
            balance = self.broker.balance()
            row = {"equity": money(balance.equity, 4), "cash": money(balance.cash, 4), "as_of": now_iso(self.clock), "stale": False}
            self._last_account = row
            return row
        except Exception:  # noqa: BLE001 - a missed read is a stale balance, never a missing checkpoint
            return {**self._last_account, "stale": True} if self._last_account else None

    def mark_floor(self, house: Any) -> None:
        """Every five minutes, the Brokerage Account's balance as a `floor.mark` row: the page's balance history."""
        now = self.clock()
        if now - float(self._state["last_mark"]) < MARK_EVERY_SECONDS:
            return
        account = self.account(house)
        if account is None or account["stale"]:
            return
        self._state["last_mark"] = now
        house.ledger.append("floor.mark", {"brokerage_equity": account["equity"], "brokerage_cash": account["cash"], "as_of": account["as_of"]})

    # ---------------------------------------------------------------- checkpoint
    def checkpoint(self, house: Any) -> dict[str, Any]:
        """The checkpoint for `house`: `inputs` built into schema 2. The account is read before the stamp:
        the site refuses a reading dated after the checkpoint that carries it."""
        inputs = self.inputs(house)
        return build_checkpoint(inputs, now_iso(self.clock))

    def inputs(self, house: Any) -> SiteInputs:
        """The page's inputs: the House's own `site_inputs()` where it gives them, this publisher's reads
        for the rest. A read that fails costs its block, never the checkpoint."""
        given: Mapping[str, Any] = {}
        hook = getattr(house, "site_inputs", None)
        if callable(hook):
            try:
                given = hook() or {}
            except Exception:  # noqa: BLE001 - the House's hook is a courtesy; the checkpoint is not
                given = {}
        folds = self._guard(lambda: self._folded(house), None)
        now = now_iso(self.clock)
        from .trading_profit import complete, ledger as trading_ledger

        # Profit and the positions table: the live book's rows (read now) and the account's activity (read off this path).
        record = self._guard(lambda: trading_ledger(
            self.state_path.parent, getattr(house, "options_live", None), at=now,
            never_traded=(folds is not None and not folds.real_options_seen
                          and not any(getattr(book, "real_money", False) for book in getattr(house, "books", {}).values())),
            start_at=self.performance.get("start_at")), None)
        reading = self._guard(self.activity.read, None) if self.activity is not None else None
        trading, positions = self._guard(lambda: complete(record, reading, at=now), ({"as_of": now, "pnl_usd": None}, None))
        self._inputs_positions = positions

        inputs = SiteInputs(
            started_at=given["started_at"] if "started_at" in given else self._guard(lambda: self._started(house), None),
            account=given["account"] if "account" in given else self.account(house),
            performance=given["performance"] if "performance" in given else self._performance(),
            compute={**self._compute(folds, now), **{k: v for k, v in (given.get("compute") or {}).items() if k in COMPUTE_PARTS or k == "as_of"}},
            gym=given.get("gym"),
            agents=list(given["agents"]) if "agents" in given else self._guard(lambda: self._agents(house, folds), []),
            structures=list(given["structures"]) if "structures" in given else self._guard(lambda: self._structures(house), []),
            trading=trading, positions=positions, practice=given.get("practice"),
        )
        swarm = getattr(house, "swarm", None)
        if getattr(swarm, "root", None) is not None:
            from .site_window import site_window
            from .swarm.progress import attach as attach_progress

            inputs.agents = self._guard(lambda: self._pinned(inputs.agents, swarm.root, positions, inputs.structures), inputs.agents)
            inputs.agents = self._guard(lambda: attach_progress(inputs.agents, swarm.root,
                live=getattr(house, "options_live", None), account=inputs.account, now=self.clock()), inputs.agents)
            practice = inputs.practice.get("rows") if isinstance(inputs.practice, Mapping) else None
            window = self._guard(lambda: site_window(swarm.root, self.state_path.parent, agents=inputs.agents,
                                                     positions_rows=(positions or {}).get("rows"), practice_rows=practice,
                                                     start_at=self.performance.get("start_at"), at=now), None)
            if window:
                inputs.levels, inputs.rationale = window.get("levels"), window.get("rationale")
        return inputs

    @staticmethod
    def _pinned(agents: list[Mapping[str, Any]], root: Any, positions: Mapping[str, Any] | None,
                structures: list[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
        """The roster with every agent a real position names pinned (`pinned=True`: never the retired list's 24, and the
        last to leave the byte limit), so its card always has a name, a mechanism and a record: the families of the table's
        rows (an agent's or the incubator's; the newest the table can list) and of the open real structures, alive or
        retired. One the roster does not hold is read from the swarm's store (`sitefeed.agent_rows`)."""
        from .swarm.sitefeed import agent_rows

        rows = [r for r in (positions or {}).get("rows") or [] if isinstance(r, Mapping)]
        listed = [r for r in rows if r.get("status") == "open"]
        listed += sorted((r for r in rows if r.get("status") != "open"), key=lambda r: str(r.get("closed_at") or ""), reverse=True)
        named = {str(r.get("family") or "") for r in listed[:MAX_POSITIONS] if r.get("source") in AGENT_SOURCES}
        named |= {str(s.get("agent") or "") for s in structures or [] if isinstance(s, Mapping) and s.get("real") is True}
        named = {name for name in named if _SLUG.match(name)}
        have = {str(a.get("id") or "") for a in agents}
        extra = agent_rows(root, sorted(named - have)) if named - have else []
        return [dict(a, pinned=True) if str(a.get("id") or "") in named else a for a in agents] + [dict(a, pinned=True) for a in extra]

    @staticmethod
    def _guard(read: Callable[[], Any], fallback: Any) -> Any:
        try:
            return read()
        except Exception:  # noqa: BLE001 - one unreadable block, never a missing checkpoint
            return fallback

    @staticmethod
    def _started(house: Any) -> str | None:
        started = next(iter(house.ledger.read(kinds="ops.started", limit=1)), None)
        return started.at if started else None

    def _performance(self) -> dict[str, Any] | None:
        start, equity = site_instant(self.performance.get("start_at")), self.performance.get("start_equity")
        if start is None or equity is None:
            return None
        net, verified = self.flows.read() if self.flows is not None else (None, None)
        return {"start_at": start, "start_equity": equity, "net_flows": net, "verified_at": site_instant(verified) if verified is not None else None}

    def _compute(self, folds: _Folds | None, now: str) -> dict[str, Any]:
        """Since the reset: Sail from its meter's rows on the ledger (None until it writes one), Claude and OpenAI from
        the House's hook only (None until then: the page shows no Net rather than a flattering one), the subscriptions
        prorated from `performance.start_at`, and nothing else yet. The swarm's hook replaces Sail with the bill."""
        out: dict[str, Any] = {"as_of": now, "sail_usd": folds.sail if folds is not None else None, "claude_usd": None,
                               "openai_usd": None, "thetadata_usd": None, "market_data_usd": None, "other_usd": ZERO}
        start, end = _epoch(self.performance.get("start_at")), _epoch(now)
        if start is not None and end is not None:
            months = Decimal(str(max(end - start, 0.0))) / MONTH_SECONDS
            rates = {**SUBSCRIPTIONS_MONTHLY_USD, **{k: Decimal(str(v)) for k, v in (self.performance.get("subscriptions_monthly_usd") or {}).items()
                                                      if k in SUBSCRIPTIONS_MONTHLY_USD}}
            for part, rate in rates.items():
                out[part] = rate * months
        return out

    @staticmethod
    def _band(house: Any, agent: Any) -> str:
        """Before the swarm names its bands through `site_inputs`: retired when dead, else the band its rung implies."""
        if not getattr(agent, "alive", True):
            return "retired"
        try:
            rung = int(house.evaluator.rung(agent.id))
        except Exception:  # noqa: BLE001
            rung = 0
        return "gym" if rung <= 0 else "candidate" if rung == 1 else "probe" if rung == 2 else "sized"

    def _agents(self, house: Any, folds: _Folds | None) -> list[dict[str, Any]]:
        living, dead = list(house.registry.living()), list(house.registry.dead())
        rows = []
        for agent in living + dead[-MAX_DEAD_SHOWN:]:
            rows.append({
                "id": agent.id, "family": getattr(agent, "family", None),
                "mechanism": folds.mechanism.get(agent.id) if folds else None, "structure": None, "band": self._band(house, agent),
                "born_at": getattr(agent, "born_at", None), "retired_at": None if getattr(agent, "alive", True) else getattr(agent, "died_at", None),
                "trials": folds.trials.get(agent.id, 0) if folds else 0, "revisions": folds.revisions.get(agent.id, 0) if folds else 0,
                "forward": folds.tally(agent.id, False) if folds else None, "real": folds.tally(agent.id, True) if folds else None,
            })
        return rows

    @staticmethod
    def _structures(house: Any) -> list[dict[str, Any]]:
        """Every open option or structure held as one instrument on any book: what it is, whose, its cost
        to hold (what it can lose: a held structure's price is its maximum loss a share) and its P&L at
        the book's mark. Nothing else of the book leaves."""
        from . import structure_core

        rows = []
        for book in house.books.values():
            for name, account in book.accounts.items():
                for holding in list(account.holdings.values()):
                    inst = holding.instrument
                    code = str(inst.market_id or "")
                    try:
                        if structure_core.is_code(code):
                            spec = structure_core.spec_of_code(code)
                            under, kind, legs, expiry = spec.underlying, spec.type, len(spec.legs), spec.expiry
                        elif inst.asset_class == "option" and str(inst.right or "").lower()[:1] in ("c", "p"):
                            under, legs, expiry = str(inst.symbol).split(" ")[0], 1, inst.expiry
                            kind = "long_call" if str(inst.right).lower().startswith("c") else "long_put"
                        else:
                            continue
                    except (ValueError, AttributeError):
                        continue
                    mark = book.marks.get(inst.key)
                    value = holding.quantity * mark * inst.multiplier if mark is not None else None
                    rows.append({"id": f"{name}:{code or inst.key}", "agent": name, "underlying": under, "structure": kind, "legs": legs,
                                 "expiry": expiry, "quantity": holding.quantity, "real": bool(book.real_money), "opened_at": holding.opened_at,
                                 "max_loss_usd": holding.cost, "pnl_usd": value - holding.cost if value is not None else None})
        return rows
