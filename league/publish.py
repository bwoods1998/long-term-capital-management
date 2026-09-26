"""The public record at blakewoods.us/capital: AI agents trading options (schema 2, Sept 26, 2026).

The site starts over for the options swarm. Its masthead shows the full real-options profit, including
marked open positions, and the running timer. The Brokerage Account's balance and funding/compute basis
remain separate. It also shows the swarm (each agent's family, its mechanism in a sentence, its band,
record and optional promotion checklist); the Gym's pace; the
open structures with their maximum loss and P&L; and the tape of the agents' decisions in their own
words. The site's validators are `personal-site/capital/schema.js`; the contract is
`docs/design.md`; `league/tests/fixtures/site_checkpoint.json` / `site_events.json` are
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
    compute      {sail_usd, openai_usd, thetadata_usd, market_data_usd, other_usd}  since the reset;
                 merged part by part over the defaults
    gym          {trials, market_years, families_alive, families_retired}
    agents       [{id, family, mechanism, structure, band, born_at, retired_at,
                   trials, revisions, forward: {trades, wins, pnl_usd} | None, real: {...} | None}]
    structures   [{id, agent, underlying, structure, legs, expiry, quantity, real, opened_at,
                   max_loss_usd, pnl_usd}]

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
MAX_CHECKPOINT_BYTES = 512 * 1024
#: A profit is only as good as its funding check: the site shows none on a check older than ten minutes.
FLOWS_EVERY_SECONDS = 300
FLOWS_FRESH_SECONDS = 600
#: What the subscriptions cost a month, prorated from the reset (the plan's "one number"): ThetaData
#: Options Standard at $80, and the market-data subscription at about $1,000 a year. `performance`
#: `subscriptions_monthly_usd` overrides either.
SUBSCRIPTIONS_MONTHLY_USD = {"thetadata_usd": Decimal("80"), "market_data_usd": Decimal("1000") / 12}
MONTH_SECONDS = Decimal(365.25 * 86400) / 12
COMPUTE_PARTS = ("sail_usd", "openai_usd", "thetadata_usd", "market_data_usd", "other_usd")

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
    """{as_of, sail_usd, openai_usd, thetadata_usd, market_data_usd, other_usd}, each dollars or None."""
    if not isinstance(value, Mapping):
        return None
    at = site_instant(value.get("as_of")) or published_at
    if not _not_after(at, published_at):
        at = published_at
    return {"as_of": at, **{part: _money(value.get(part)) for part in COMPUTE_PARTS}}


def site_trading(value: Any, published_at: str) -> dict[str, Any] | None:
    """Aggregate real-options P&L only, with its accounting snapshot timestamp."""
    if not isinstance(value, Mapping):
        return None
    at = site_instant(value.get("as_of"))
    if not _not_after(at, published_at):
        return None
    return {"as_of": at, "pnl_usd": _money(value.get("pnl_usd"), signed=True)}


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
    """One open structure, exactly the site's eleven fields. Never a strike, a leg's price, a mark or
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
    return {"id": event_id(raw) or "structure", "agent": agent, "underlying": under, "structure": kind, "legs": legs, "expiry": expiry,
            "quantity": quantity, "real": value.get("real") is True, "opened_at": opened, "max_loss_usd": loss,
            "pnl_usd": _money(value.get("pnl_usd"), signed=True)}


def build_checkpoint(inputs: "SiteInputs | Mapping[str, Any]", published_at: str) -> dict[str, Any]:
    """The checkpoint the site takes (schema 2), from explicit inputs, every block allowlisted. The agents
    are ordered for the page (Sized, Probe, Candidate, Gym, then the newest retired), at most 160 with at
    most 24 retired among them; structures real first, at most 100. Then it is fitted under 512 KiB."""
    given = SiteInputs.of(inputs)
    started = site_instant(given.started_at)
    agents, seen = [], set()
    for raw in given.agents or []:
        row = site_agent(raw, published_at)
        if row is not None and row["id"] not in seen:
            seen.add(row["id"])
            agents.append(row)
    living = sorted((a for a in agents if a["band"] != "retired"), key=lambda a: (BAND_RANK[a["band"]], a["id"]))
    dead = sorted((a for a in agents if a["band"] == "retired"), key=lambda a: a["retired_at"] or "", reverse=True)
    shown = living[:MAX_AGENTS]
    shown += dead[:max(0, min(MAX_DEAD_SHOWN, MAX_AGENTS - len(shown)))]
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
    return fit(body)


def fit(body: dict[str, Any]) -> dict[str, Any]:
    """The body inside the site's byte limit: the oldest retired agents, then the lowest band's, then the
    shadow book's smallest structures leave first. The totals the page shows are the House's, not a count."""
    size = lambda: len(canonical(body).encode("utf-8"))  # noqa: E731
    while size() > MAX_CHECKPOINT_BYTES and (body["agents"] or body["structures"]):
        if body["agents"]:
            body["agents"].pop()
        else:
            body["structures"].pop()
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
    account's own activity history (`league.performance.alpaca_flows`, which raises on any activity it
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
        from league.performance import alpaca_flows

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
        body = self.checkpoint(house)
        status, reply = self.post("/checkpoint", body)
        if status not in (200, 409):
            raise PublishError(f"the site refused the checkpoint: HTTP {status} {reply}", status=status)
        return {"events": sent, "checkpoint": status}

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
        from .trading_profit import snapshot as trading_snapshot

        inputs = SiteInputs(
            started_at=given["started_at"] if "started_at" in given else self._guard(lambda: self._started(house), None),
            account=given["account"] if "account" in given else self.account(house),
            performance=given["performance"] if "performance" in given else self._performance(),
            compute={**self._compute(folds, now), **{k: v for k, v in (given.get("compute") or {}).items() if k in COMPUTE_PARTS or k == "as_of"}},
            gym=given.get("gym"),
            agents=list(given["agents"]) if "agents" in given else [],
            structures=list(given["structures"]) if "structures" in given else [],
            trading=self._guard(lambda: trading_snapshot(
                self.state_path.parent, getattr(house, "options_live", None), at=now,
                never_traded=(folds is not None and not folds.real_options_seen
                              and not any(getattr(book, "real_money", False) for book in getattr(house, "books", {}).values()))),
                                {"as_of": now, "pnl_usd": None}),
        )
        swarm = getattr(house, "swarm", None)
        if getattr(swarm, "root", None) is not None:
            from .swarm.progress import attach as attach_progress

            inputs.agents = self._guard(lambda: attach_progress(inputs.agents, swarm.root,
                live=getattr(house, "options_live", None), account=inputs.account, now=self.clock()), inputs.agents)
        return inputs

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
        """Since the reset: Sail from its meter's rows on the ledger (None until it writes one), OpenAI from
        the House's hook only (None until then: the page shows no profit after compute rather than a
        flattering one), the subscriptions prorated from `performance.start_at`, and nothing else yet."""
        out: dict[str, Any] = {"as_of": now, "sail_usd": folds.sail if folds is not None else None, "openai_usd": None,
                               "thetadata_usd": None, "market_data_usd": None, "other_usd": ZERO}
        start, end = _epoch(self.performance.get("start_at")), _epoch(now)
        if start is not None and end is not None:
            months = Decimal(str(max(end - start, 0.0))) / MONTH_SECONDS
            rates = {**SUBSCRIPTIONS_MONTHLY_USD, **{k: Decimal(str(v)) for k, v in (self.performance.get("subscriptions_monthly_usd") or {}).items()
                                                      if k in SUBSCRIPTIONS_MONTHLY_USD}}
            for part, rate in rates.items():
                out[part] = rate * months
        return out
