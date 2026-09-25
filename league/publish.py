"""The public tape: what the site's five sections are drawn from.

1. Live stream: agents' thoughts, research and trades, and the league's own news (births, replays,
   promotions, audits, deaths), as events.
2. Total profit and running time, 3. the balance chart: the REAL venue accounts (Kalshi and
   Alpaca), read through the gateway and marked every few minutes, against the owner's baseline
   with deposits and withdrawals taken out. Practice money is never added to it.
4. Open and closed positions with the agent's own reason for each.
5. One self-improvement series: after-cost return on the capital at work, by generation.
6. The capital board (Sept 23, 2026): each agent's band, real stake, evidence and last band move,
   and the board's summary (count and capital per band per venue, the last 50 moves, the throttle),
   read from the House's allocator (`house.allocator.board()`). Without an allocator, or when it
   fails, each agent's band follows its rung and nothing else is claimed.
7. The mechanism ledger (Sept 24, 2026): each agent's family state and settlements, and the proven
   and compounding families with their proof, stake and capacity beside the unproven count, from
   the allocator's board; and the lab's hourly line, from its own newest `lab.stats` row.

The site validates every byte (`personal-site/capital/schema.js`; the contract this file is
written against is `league/tests/fixtures/site_contract.md`). One bad event refuses its whole
batch, so everything is cleaned here first: no `<`, no control characters, no credential shapes,
no links the site does not allow, exact timestamp and money formats. Rows marked private on the
ledger, and private keys, never leave.
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
from collections import deque
from decimal import ROUND_HALF_UP, Decimal
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from .constitution import CONSTITUTION
from .ledger import HOUSE, Entry, canonical, now_iso, public_view

ZERO = Decimal(0)
MAX_BATCH = 100
MARK_EVERY_SECONDS = 300
# The site's `MAX_DESKS` (capital/schema.js): a checkpoint with more desk rows is refused whole.
# Found Sept 23, 2026: population 96 plus the last 8 dead made 104 rows, and every checkpoint from
# 05:30Z was refused until the roster was bounded here (at the site's 100 then). The site raised its
# limit to 160 (personal-site #4, deployed 06:54Z Sept 23, 2026, version 5772ac0c): the population
# bound is 128, plus the recent dead.
MAX_DESKS = 160
MAX_DEAD_SHOWN = 8
# The site's `MAX_CHECKPOINT_BYTES` (512 KiB since personal-site #4; 100 rows measured 139 KiB). A
# larger body is refused whole, so the least important rows are left out until it fits.
MAX_CHECKPOINT_BYTES = 512 * 1024
ALLOWED_LINK_HOSTS = ("sec.gov", "www.sec.gov", "efts.sec.gov", "blakewoods.us", "github.com", "kalshi.com", "finance.yahoo.com")
RESEARCH_TOOLS = ("web_search", "library_search", "library_read", "library_write", "replay", "request_tool", "playbook_read")

_LINK = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://\S+")
_SCHEME = re.compile(r"\b(javascript|vbscript|data|file|blob):(?=\S)", re.IGNORECASE)
_SECRET = re.compile(r"\b(sk-|apca-)|\bbearer[ :]", re.IGNORECASE)
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_ID = re.compile(r"[^A-Za-z0-9:_.-]")
_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$")


class PublishError(RuntimeError):
    def __init__(self, message: str, *, status: int | None = None):
        super().__init__(message)
        self.status = status


# ------------------------------------------------------------------------------- cleaning
def js_length(text: str) -> int:
    """A string's length as JavaScript counts it (UTF-16 code units), which is how every one of the
    site's validators measures text: a character outside the Basic Multilingual Plane, such as an
    emoji, is two there and one in Python."""
    return len(text.encode("utf-16-le", "surrogatepass")) // 2


def js_cut(text: str, limit: int) -> str:
    """The longest prefix of `text` at most `limit` long in JavaScript's count, never splitting a
    character. Cutting by Python's count would let 300 characters with one emoji in them reach the
    site as 301, and the site refuses the whole checkpoint for one field that is too long."""
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


def desk_family(family: str) -> str:
    return re.sub(r"[^a-z0-9-]+", "-", family.lower()).strip("-")[:40] or "league"


def hours_between(start: str | None, end: str) -> float | None:
    from ltcm.broker import instant

    a, b = instant(start) if start else None, instant(end)
    if a is None or b is None:
        return None
    return round(max((b - a).total_seconds(), 0.0) / 3600, 2)


# ------------------------------------------------------------------------- the capital board
# The allocator's bands, lowest first (Workstream A, Sept 23, 2026). The site's validators know these
# words and no others (capital/schema.js `BANDS`). "paper" is the House's word: the page says
# "Practice", and so does every sentence published here. "probe" (Sept 24, 2026, the close-the-gaps
# run's P1): a first real stake at pocket-change size for an agent whose family has not proven its
# edge; a member of a proven family is a "bunt". Both are rung 2 and the page's Level 2; the site has
# accepted the band since personal-site #6 (deployed 01:55Z Sept 24), before any board carried it.
BANDS = ("replay", "paper", "probe", "bunt", "swing", "star")
REAL_BANDS = ("probe", "bunt", "swing", "star")
BAND_LABELS = {"replay": "Replay", "paper": "Practice", "probe": "Probe", "bunt": "Bunt", "swing": "Swing", "star": "Star"}
RUNG_BANDS = ("replay", "paper", "bunt", "swing")  # before the allocator: rung 0..3
MAX_BOARD_MOVES = 50
MULTIPLE_PLACES = 6  # wealth multiples and E, as unsigned decimal strings: "1.034512"
_VENUE = re.compile(r"^[a-z0-9-]{1,24}$")
_DESK_ID = re.compile(r"^[a-z0-9-]{1,40}$")
_MAX_MULTIPLE = Decimal("999999999")


def rung_band(rung: Any) -> str | None:
    """The band a rung implies when the allocator names none: 0 replay, 1 paper, 2 bunt, 3 swing."""
    if isinstance(rung, bool):
        return None
    try:
        rung = int(rung)
    except (TypeError, ValueError):
        return None
    return RUNG_BANDS[rung] if 0 <= rung < len(RUNG_BANDS) else None


def site_instant(value: Any) -> str | None:
    """Any ISO-8601 stamp (or an aware datetime) in the site's exact form: UTC, milliseconds, Z."""
    from ltcm.broker import instant

    if isinstance(value, datetime):
        parsed = value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    else:
        parsed = instant(value)
    if parsed is None:
        return None
    return parsed.strftime("%Y-%m-%dT%H:%M:%S") + f".{parsed.microsecond // 1000:03d}Z"


def _not_after(at: str, published_at: str) -> bool:
    """The site refuses a move dated more than a minute after the checkpoint that carries it."""
    from ltcm.broker import instant

    a, b = instant(at), instant(published_at)
    return a is not None and b is not None and a <= b + timedelta(seconds=60)


def _number(value: Any) -> Decimal | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = Decimal(str(value))
    except (ArithmeticError, ValueError, TypeError):
        return None
    return number if number.is_finite() else None


def _count(value: Any) -> int | None:
    number = _number(value)
    if number is None or number < 0 or number != number.to_integral_value():
        return None
    return min(int(number), 1_000_000_000)


def site_multiple(value: Any) -> str | None:
    """A wealth multiple or E: unsigned, six places ("1.034512"), or None when it is not a number."""
    number = _number(value)
    return money(min(number, _MAX_MULTIPLE), MULTIPLE_PLACES) if number is not None and number >= 0 else None


def site_stake(value: Any) -> str | None:
    """Real money in dollars and cents ("10.00"); None when there is none or it is not a number."""
    number = _number(value)
    return money(number, 2) if number is not None and number >= 0 else None


def site_reason(value: Any) -> str:
    return clean_text(" ".join(str(value if value is not None else "").split()), 300)


def site_evidence(value: Any) -> dict[str, Any] | None:
    """{W_paper, W_real, E, trades[, real_trades]} in the site's formats, or None if any is missing."""
    if not isinstance(value, Mapping):
        return None
    out: dict[str, Any] = {key: site_multiple(value.get(key)) for key in ("W_paper", "W_real", "E")}
    trades = _count(value.get("trades"))
    if None in out.values() or trades is None:
        return None
    out["trades"] = trades
    real = _count(value.get("real_trades"))
    if real is not None:
        out["real_trades"] = real
    return out


def site_last_move(value: Any, published_at: str) -> dict[str, Any] | None:
    """{at, from_band, to_band, reason}, or None when the move names no band the site knows."""
    if not isinstance(value, Mapping):
        return None
    at, start, end = site_instant(value.get("at")), value.get("from_band"), value.get("to_band")
    if at is None or not _not_after(at, published_at) or end not in BANDS or (start is not None and start not in BANDS):
        return None
    return {"at": at, "from_band": start, "to_band": end, "reason": site_reason(value.get("reason"))}


def site_board_move(value: Any, published_at: str) -> dict[str, Any] | None:
    """One move on the board's trail: {id, at, agent, from_band, to_band, reason[, venue][, stake_usd]}."""
    if not isinstance(value, Mapping):
        return None
    agent = str(value.get("agent") or "")
    move = site_last_move(value, published_at)
    if move is None or not _DESK_ID.match(agent):
        return None
    raw = str(value.get("id") or "") or f"move:{agent}:{move['at']}:{move['to_band']}"
    out = {"id": event_id(raw), "agent": agent, **move}
    venue = value.get("venue")
    if isinstance(venue, str) and _VENUE.match(venue):
        out["venue"] = venue
    if "stake_usd" in value:
        out["stake_usd"] = site_stake(value.get("stake_usd"))
    return out


def site_board(board: Mapping[str, Any], published_at: str) -> dict[str, Any]:
    """The allocator's summary in the site's shape: per venue, count and capital per band; the last
    50 moves (oldest first, ids unique); the throttle; whether the allocator is running; and since
    Sept 24, 2026 the proven families (`site_families`), when the board carries its mechanism ledger."""
    bands: dict[str, dict[str, Any]] = {}
    raw = board.get("bands")
    for venue, per in (list(raw.items())[:8] if isinstance(raw, Mapping) else []):
        if not isinstance(venue, str) or not _VENUE.match(venue) or not isinstance(per, Mapping):
            continue
        rows = {}
        for band, row in per.items():
            count = _count(row.get("count")) if isinstance(row, Mapping) else None
            capital = site_stake(row.get("capital_usd")) if isinstance(row, Mapping) else None
            if band in BANDS and count is not None and capital is not None:
                rows[band] = {"count": min(count, 100_000), "capital_usd": capital}
        bands[venue] = rows
    moves: list[dict[str, Any]] = []
    seen: set[str] = set()
    raw_moves = board.get("moves")
    for value in (list(raw_moves) if isinstance(raw_moves, (list, tuple)) else []):
        move = site_board_move(value, published_at)
        if move is not None and move["id"] not in seen:
            seen.add(move["id"])
            moves.append(move)
    out: dict[str, Any] = {"enabled": board.get("enabled") is True, "bands": bands, "moves": moves[-MAX_BOARD_MOVES:]}
    throttle = board.get("throttle")
    if isinstance(throttle, Mapping) and isinstance(throttle.get("active"), bool):
        pnl, envelope = _number(throttle.get("floor_pnl_usd")), site_stake(throttle.get("envelope_usd"))
        if pnl is not None and envelope is not None:
            out["throttle"] = {"active": throttle["active"], "floor_pnl_usd": money(pnl, 2, signed=True), "envelope_usd": envelope}
    families = site_families(board.get("families"))
    if families is not None:
        out["families"] = families
    return out


# ------------------------------------------------------------------------- the mechanism ledger
# A family's states (C1 and C4, the close-the-gaps run, Sept 24, 2026; `league/families.py`) as the site
# knows them (capital/schema.js `FAMILY_STATES`): "unproven", "proven", and "swing", the House's word for a
# proven family whose stakes compound, which the page calls compounding and never shows.
FAMILY_STATES = ("unproven", "proven", "swing")
PROVEN_STATES = ("proven", "swing")
MAX_FAMILY_ROWS = 8  # the site's MAX_FAMILY_ROWS: the proven edges it lists, the strongest first
MAX_SETTLEMENTS = 1_000_000  # the site's MAX_SETTLEMENTS: a family's independent settlements
MAX_UNPROVEN = 100_000
MAX_TESTED = 1_000_000  # the site's bound on the strategies the lab tested in an hour
MAX_WAITING = 100_000
BOUND_PLACES = 6  # a lower bound on growth a settlement, as a signed decimal string: "0.142300"
_MAX_BOUND = Decimal("999999")
_MAX_USD = Decimal("999999999")
#: The lab's hourly reading (`lab.stats`, written by `Lab.publish` every `stats_every_minutes`, 10) is sent
#: while it is at most this old: an older one no longer says what the last hour was.
LAB_READING_MAX_AGE = 1800.0
_HOUR = Decimal(3600)


def _bounded(value: Any, limit: Decimal) -> Decimal | None:
    number = _number(value)
    return None if number is None else max(-limit, min(number, limit))


def site_family_fields(row: Mapping[str, Any]) -> dict[str, Any]:
    """A desk's family in the mechanism ledger: {family_state, family_n}, together or not at all (the site
    refuses one without the other). The family's bound and capacity are the family's numbers, not the
    member's: they ride the board's `families`, once a family."""
    state, n = row.get("family_state"), _count(row.get("family_n"))
    if state not in FAMILY_STATES or n is None:
        return {}
    return {"family_state": state, "family_n": min(n, MAX_SETTLEMENTS)}


def honest_bound(row: Mapping[str, Any]) -> Decimal | None:
    """The bound a family's proof rests on: its t bound, and for a lopsided record (favourites: many small
    wins and a rare whole loss) the House's loss-rate bound beside it, whichever is lower (`families.pool`'s
    `honest_bound`: the board's row carries the two apart). Weather favourites at T0 (Sept 24, 2026) read
    +0.0033 on the t bound and -0.21 on the loss-rate bound: unproven, and the lower number says why."""
    bound, gate = _number(row.get("bound")), _number(row.get("loss_gate"))
    if bound is None:
        return None
    return min(bound, gate) if gate is not None else bound


def site_families(raw: Any) -> dict[str, Any] | None:
    """The board's `families` (per venue, per family: `families.row_of`) in the site's shape: the proven and
    compounding families, compounding first and then by settlements, at most `MAX_FAMILY_ROWS`, one a family
    and venue, each named as a desk's family is (`desk_family`); and how many of the families followed are
    unproven. A row the site would refuse is left out; None when the House sent no block."""
    if not isinstance(raw, Mapping):
        return None
    rows: list[dict[str, Any]] = []
    unproven = 0
    for venue, per in list(raw.items())[:8]:
        if not isinstance(venue, str) or not _VENUE.match(venue) or not isinstance(per, Mapping):
            continue
        for name, row in per.items():
            if not isinstance(row, Mapping):
                continue
            state = row.get("state")
            if state == "unproven":
                unproven += 1
                continue
            n, bound = _count(row.get("n")), _bounded(honest_bound(row), _MAX_BOUND)
            if state not in PROVEN_STATES or n is None or bound is None:
                continue  # a family proven on no bound is not a proof the page can show
            n = min(n, MAX_SETTLEMENTS)
            real, capacity = row.get("real"), row.get("capacity")
            real_n = _count(real.get("n")) if isinstance(real, Mapping) else None
            usd = _bounded(capacity.get("usd_per_day"), _MAX_USD) if isinstance(capacity, Mapping) else None
            rows.append({"family": desk_family(str(name)), "venue": venue, "state": state, "n": n, "real_n": min(real_n or 0, n),
                         "bound": money(bound, BOUND_PLACES, signed=True), "stake_usd": site_stake(_bounded(row.get("stake_usd"), _MAX_USD)),
                         "members_real": min(_count(row.get("members_real")) or 0, MAX_DESKS),
                         "capacity_usd_per_day": None if usd is None else money(usd, 2, signed=True)})
    rows.sort(key=lambda r: (r["state"] != "swing", -r["n"], r["venue"], r["family"]))
    shown: list[dict[str, Any]] = []
    for row in rows:
        if len(shown) < MAX_FAMILY_ROWS and all((row["venue"], row["family"]) != (r["venue"], r["family"]) for r in shown):
            shown.append(row)
    return {"unproven": min(unproven, MAX_UNPROVEN), "rows": shown}


def site_lab(entry: Any, now: float) -> dict[str, Any] | None:
    """The lab's hourly reading in the site's shape ({at, tested_last_hour, graduates_waiting}), from its newest
    `lab.stats` row (`Lab.stats` over the last hour: the candidates its batches evaluated, and its graduates
    waiting for a seat). None with no row, one older than `LAB_READING_MAX_AGE`, one not over an hour, or a
    count the site would refuse: the newest reading decides, and the site is never sent an older one."""
    if entry is None:
        return None
    p = entry.payload if isinstance(entry.payload, Mapping) else {}
    at, waiting = site_instant(entry.at), p.get("waiting_seat")
    tested = _count(p.get("evaluated"))
    graduates = _count(waiting.get("count")) if isinstance(waiting, Mapping) else None
    if at is None or _number(p.get("window_seconds")) != _HOUR or tested is None or graduates is None:
        return None
    if now - _epoch(at) > LAB_READING_MAX_AGE:
        return None
    return {"at": at, "tested_last_hour": min(tested, MAX_TESTED), "graduates_waiting": min(graduates, MAX_WAITING)}


def ledger_board_move(entry: Entry, agent: Any) -> dict[str, Any] | None:
    """A promote or demote verdict on the ledger as a move on the board's trail (the allocator's
    rows carry `band_from` and `band_to`; older rows only their rungs)."""
    p = entry.payload
    start = p.get("band_from") if p.get("band_from") in BANDS else rung_band(p.get("from_rung"))
    end = p.get("band_to") if p.get("band_to") in BANDS else rung_band(p.get("to_rung"))
    if start is None or end is None or start == end or not _DESK_ID.match(str(agent.id)):
        return None
    move = {"id": event_id(entry.id), "at": entry.at, "agent": agent.id, "venue": "kalshi" if agent.venue == "kalshi" else "alpaca",
            "from_band": start, "to_band": end, "reason": site_reason(p.get("reason"))}
    if p.get("stake_usd") is not None:
        move["stake_usd"] = site_stake(p.get("stake_usd"))
    return move


# --------------------------------------------------------------------------------- events
def league_real_pnl(house: Any) -> Decimal:
    """What the league has made or lost with real money: over every real-money book, each account's
    equity less what it was lent (a closed account's is what it kept or lost), the House row's
    fees and dust included. Zero while no real book exists."""
    total = ZERO
    for book in house.books.values():
        if not book.real_money:
            continue
        for name, account in book.accounts.items():
            total += book.equity(name) - account.staked
    return total

def option_label(instrument: Mapping[str, Any]) -> str:
    """`F 10-09 13C`: the underlying, the expiry's month and day, the strike and C or P."""
    try:
        strike = f"{float(instrument.get('strike')):g}"
    except (TypeError, ValueError):
        strike = str(instrument.get("strike"))
    return f"{instrument.get('symbol')} {str(instrument.get('expiry') or '')[5:]} {strike}{str(instrument.get('right') or '?')[:1].upper()}"


# The site's bound on an instrument's strings (capital/schema.js `validInstrument`: `symbol` is text(80), and
# `market_id`, `right`, `expiry`, ... at most 80 characters each). A desk row whose position names a longer
# one is refused, and the site refuses the whole checkpoint with it.
MAX_INSTRUMENT_TEXT = 80
_STRUCTURE_LEG = re.compile(r"^([+-])([12])([A-Z]{1,6})([0-9]{6})([CP])([0-9]{8})$")


def site_market_id(instrument: Mapping[str, Any]) -> str:
    """A position's `market_id` inside the site's 80 characters (`MAX_INSTRUMENT_TEXT`).

    Unchanged when it fits: a Kalshi ticker, a coin pair, a two-leg structure (`debit_vertical|-1AAL261002P00013500|
    +1AAL261002P00014000` is 56). A level-3 structure is held as one instrument whose id is its type and every leg's
    21-character OCC code (`league/structure_core.py` `CODE`), and four legs do not fit: Sept 25, 2026, krasker-22's
    CCL iron condor (filled 15:48:59Z on options-shadow) was 95 characters, and the site refused every checkpoint
    from 15:50:21Z (HTTP 400 "Invalid checkpoint.", 197 refusals by 20:21Z, about 43 an hour) while it was held.
    Such an id is sent with each leg's underlying and expiry left out when they are the instrument's own (a leg
    that differs keeps them after an `@`), and the strike written plainly: `iron_condor|-1C22.5|+1C23|+1P21.5|-1P22`.
    Anything still too long is cut to the bound. Only the published copy is shortened; the ledger keeps the code."""
    raw = str(instrument.get("market_id") or "")
    if js_length(raw) <= MAX_INSTRUMENT_TEXT:
        return raw
    kind, _, rest = raw.partition("|")
    legs = rest.split("|") if rest else []
    home = str(instrument.get("symbol") or "").upper() + str(instrument.get("expiry") or "").replace("-", "")[2:]
    compact = []
    for part in legs:
        found = _STRUCTURE_LEG.match(part)
        if found is None:
            compact = []
            break
        sign, ratio, root, day, right, strike = found.groups()
        where = "" if root + day == home else f"@{root}{day}"
        compact.append(f"{sign}{ratio}{right}{format((Decimal(int(strike)) / 1000).normalize(), 'f')}{where}")
    shown = "|".join([kind, *compact]) if compact else raw
    return js_cut(shown, MAX_INSTRUMENT_TEXT)


def _shown(instrument: Mapping[str, Any]) -> dict[str, Any]:
    shown = {k: instrument.get(k) for k in ("symbol", "asset_class", "market_id", "right") if instrument.get(k) is not None}
    if instrument.get("asset_class") == "option":
        shown["symbol"] = option_label(instrument)
    return shown

def to_events(entry: Entry) -> list[dict[str, Any]]:
    """The site events one ledger row becomes (usually one, sometimes none, a closing fill two)."""
    if not entry.public:
        return []
    p = public_view(entry.payload)
    agent = entry.agent
    desk = f"desk:{agent}"
    out: list[tuple[str, str, str, dict[str, Any]]] = []  # (id suffix, stream, kind, payload)
    kind = entry.kind
    if kind == "agent.thought":
        out.append(("", desk, "desk.thought", {"text": p.get("text"), "session_id": p.get("session") or p.get("phase") or "decide"}))
    elif kind == "agent.research":
        if p.get("tool") in RESEARCH_TOOLS:
            out.append(("", desk, "desk.tool_call", {"tool": p["tool"], "arguments": p.get("arguments") or {}, "session_id": p.get("session") or "research"}))
        elif p.get("tool") == "summary" and str(p.get("summary") or "").strip():
            out.append(("", desk, "desk.thought", {"text": "Research: " + str(p["summary"]), "session_id": p.get("session") or "research"}))
    elif kind == "book.fill" and agent != HOUSE and p.get("source") in ("venue", "cross"):
        instrument = p.get("instrument") or {}
        venue = re.sub(r"[^a-z0-9-]", "-", str(p.get("book") or "book"))[:40]
        shown = _shown(instrument)
        out.append(("", f"broker:{venue}", "broker.fill", {
            "desk_id": agent, "instrument": shown, "side": p.get("side"), "quantity": p.get("quantity"),
            "price": money(p.get("price") or 0, 8).rstrip("0").rstrip(".") or "0", "real_money": bool(p.get("real_money")),
            "rationale_excerpt": str(p.get("reason") or "")[:240],
        }))
        if p.get("side") == "sell" and p.get("realized") is not None:
            out.append(("outcome:", desk, "desk.outcome", {
                "market_id": instrument.get("market_id") or instrument.get("symbol"), "instrument": shown, "result": "sold",
                "pnl": money(p["realized"], 4, signed=True), "rationale_excerpt": str(p.get("entry_reason") or p.get("reason") or "")[:240],
                "real_money": bool(p.get("real_money")), "held_for_hours": hours_between(p.get("opened_at"), entry.at),
                "quantity": p.get("quantity"), "exit_price": p.get("price"),
            }))
    elif kind == "book.settle" and agent != HOUSE:
        instrument = p.get("instrument") or {}
        shown = _shown(instrument)
        out.append(("", desk, "desk.outcome", {
            "market_id": instrument.get("market_id") or instrument.get("symbol"), "instrument": shown, "result": p.get("result"),
            "pnl": money(p.get("pnl") or 0, 4, signed=True), "rationale_excerpt": str(p.get("reason") or "")[:240],
            "real_money": bool(p.get("real_money")), "held_for_hours": hours_between(p.get("opened_at"), entry.at), "quantity": p.get("quantity"),
        }))
    elif kind == "floor.mark" and "real_account_equity" in p:
        # Only marks on the league's basis are published. The first production hour (Sept 19, 2026)
        # recorded the raw account balance, which the first run's leftover contracts were moving;
        # those rows stay on the ledger and off the chart.
        out.append(("", "ops", "floor.mark", {k: p[k] for k in ("account_equity", "account_cash", "as_of", "venues") if k in p}))
    else:
        message = league_news(entry.kind, agent, p)
        if message:
            out.append(("", "lab", "lab.progress", {"message": message, "stage": "learn" if kind.startswith(("eval.", "audit.", "merton.")) else "test", "component": "league"}))
    events = []
    for prefix, stream, site_kind, payload in out:
        payload = payload if site_kind == "floor.mark" else clean({k: v for k, v in payload.items() if v is not None})
        if site_kind == "desk.thought" and not str(payload.get("text") or "").strip():
            continue
        events.append({
            "id": event_id(prefix + entry.id), "stream": stream, "kind": site_kind, "at": entry.at, "payload": payload,
            "digest": hashlib.sha256(canonical(payload).encode("utf-8")).hexdigest(),
        })
    return events


def league_news(kind: str, agent: str, p: Mapping[str, Any]) -> str | None:
    """One plain sentence for the league's own events."""
    if kind == 'book.fill_correction':
        return (f"{agent}'s execution accounting was corrected from a venue receipt "
                f"({money(p.get('cash_delta') or 0, 4, signed=True)} USD). "
                "The affected performance history is excluded from scoring.")
    if kind == "agent.born":
        origin = f"a child of {p['parent']}" if p.get("parent") else "a founding seed"
        return f"{agent} is born ({origin}, generation {p.get('generation')}, niche {p.get('venue')}/{p.get('horizon')}/{p.get('style')}). {p.get('reason') or ''}".strip()
    if kind == "agent.forked":
        return f"{agent} forked {p.get('child')} and endowed it with ${p.get('endowment_usd')} of its own compute credits."
    if kind == "agent.died":
        return f"{agent} died of {p.get('cause')}. {p.get('detail') or ''}".strip()
    if kind == "eval.trial":
        verdict = "passed" if p.get("passed") else "failed"
        why = "" if p.get("passed") else " " + "; ".join(str(r) for r in (p.get("reasons") or [])[:2]) + "."
        return f"{agent} {verdict} replay: trial {p.get('trials')} for the {p.get('family')} family, {p.get('trades')} trades, deflated Sharpe {_short(p.get('deflated_sharpe'))}.{why}"
    if kind == "eval.verdict" and p.get("decision") in ("promote", "demote", "die"):
        if p["decision"] == "die":
            return f"The evidence ended {agent}: {p.get('reason')}."
        banded = band_news(agent, p)
        if banded:
            return banded
        verb = "climbs" if p["decision"] == "promote" else "drops"
        return f"{agent} {verb} from rung {p.get('from_rung')} to rung {p.get('to_rung')}: {p.get('reason')}."
    if kind == "eval.verdict" and p.get("decision") == "size":
        return stake_news(agent, p)
    if kind == "audit.verdict":
        return f"The auditor {'approved' if p.get('approve') else 'vetoed'} {agent} for real money. {p.get('summary') or p.get('error') or ''}".strip()
    if kind == "merton.pass":
        return f"Merton ({p.get('role')}): {p.get('summary') or ''}".strip()
    if kind == "merton.change":
        return f"Merton's change {p.get('branch')}: {p.get('status')}. {p.get('title') or ''}".strip()
    if kind == "ops.alert" and p.get("level") == "error":
        return f"House alert: {p.get('text')}"
    if kind == "ops.deploy":
        if p.get("action") == "deploying":
            return f"New code on main: release {p.get('release')} is on the canary. The watchdog promotes it only if it stays healthy."
        if p.get("action") in ("blocked", "waiting"):
            return (f"New code on main ({str(p.get('sha') or '')[:12]}) is not deployed: the House deploys only a commit whose "
                    f"checks GitHub confirms passed on that exact commit. {'; '.join(str(r) for r in (p.get('reasons') or [])[:1])}").strip()
        if p.get("action") == "held":
            # The release train (league/updater.py, Sept 25, 2026): not a refusal, a wait.
            reasons = [str(r) for r in p.get("reasons") or []]
            shown = "; ".join(reasons[:1] + (reasons[-1:] if len(reasons) > 1 else []))  # the first hold, and when it may go
            return (f"New code on main ({str(p.get('sha') or '')[:12]}) waits for the release train: the House takes new code at most "
                    f"every few hours, never in the US stock session or just after a restart. {shown[:1].upper()}{shown[1:]}").strip()
        return f"New code on main was refused before the canary: {'; '.join(str(r) for r in (p.get('reasons') or [])[:2])}"
    if kind == "ops.recommendation":
        return f"Capital recommendation: {p.get('summary')}"
    return None


def _because(p: Mapping[str, Any]) -> str:
    reason = " ".join(str(p.get("reason") or "").split()).rstrip(". ")
    return reason or "the allocator's evidence"


def band_news(agent: str, p: Mapping[str, Any]) -> str | None:
    """An allocator move (`band_from`, `band_to` on the verdict) in the site's band template:
    "mullins-7 climbs from Practice to Bunt with a $10.00 real stake: E 1.041 after 6 trades." """
    start, end = p.get("band_from"), p.get("band_to")
    if start not in BANDS or end not in BANDS or start == end:
        return None
    verb = "climbs" if BANDS.index(end) > BANDS.index(start) else "drops"
    stake = site_stake(p.get("stake_usd")) if end in REAL_BANDS else None
    staked = f" with a ${stake} real stake" if stake and Decimal(stake) > 0 else ""
    return f"{agent} {verb} from {BAND_LABELS[start]} to {BAND_LABELS[end]}{staked}: {_because(p)}."


def stake_news(agent: str, p: Mapping[str, Any]) -> str | None:
    """A stake change inside a band: "mullins-7's real stake is now $14.20 (Bunt): E 1.42." """
    stake = site_stake(p.get("stake_usd"))
    if not stake or Decimal(stake) <= 0:
        return None
    band = next((b for b in (p.get("band_to"), p.get("band"), rung_band(p.get("rung"))) if b in REAL_BANDS), None)
    label = f" ({BAND_LABELS[band]})" if band else ""
    return f"{agent}'s real stake is now ${stake}{label}: {_because(p)}."


def _short(value: Any) -> str:
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "n/a"


# ------------------------------------------------------------------------------ publisher
#: The spend buckets of the checkpoint's `run`, and the bucket of a `credit.charge` by what it bought.
BUCKETS = ("tokens", "boxes", "search", "other")


def _bucket(what: str) -> str:
    return "tokens" if "token" in what else ("boxes" if "sandbox" in what else ("search" if what == "web search" else "other"))


class _Folds:
    """What a checkpoint reads from the whole ledger, folded once and then from the new rows only.

    Sept 24, 2026 (R6-perf): `checkpoint` read every `credit.charge` row twice a tick (the spend buckets,
    then each desk's cost agent by agent), every `provider.request` row for the models used, each agent's
    every verdict and the newest 10,000 wakes. Traced on a copy of the 17:27Z snapshot: about 250,000
    rows parsed a tick, 3.5 s of the tick's CPU on the developer machine; the box's `publish` step took
    11.6-87.7 s a tick that hour (with the site's own answer inside it). The ledger is append-only and
    every fold is in sequence order, from zero as the full read summed, so the new rows folded onto the
    old sums ARE the sums read afresh. A row a fold cannot read stops it there, as it stopped the full
    read, and the next checkpoint tries the same row again."""

    KINDS = ("credit.charge", "ops.budget", "provider.request", "merton.pass", "audit.verdict", "agent.woke",
             "agent.intent", "eval.verdict")
    #: `run.sessions_today` counts today's wakes among the newest this many, as it always has.
    NEWEST_WAKES = 10_000

    def __init__(self, ledger: Any) -> None:
        self.ledger = ledger
        self.lock = threading.Lock()
        self.seq = 0
        self.spend = {bucket: ZERO for bucket in BUCKETS}
        self.spend_days: dict[str, dict[str, Decimal]] = {}  # UTC day -> bucket -> charges that day
        self.cost: dict[str, Decimal] = {}  # agent -> its charges
        self.sail: Decimal | None = None  # the Sail meter's falls (`ops.budget` "sail" with `spent_usd`); None: never metered
        self.sail_days: dict[str, Decimal] = {}
        self.profiles: set[str] = set()  # the model profiles `provider.request` rows name
        self.frontier_paid = False  # a Merton pass or an audit that cost something
        self.wake_days: deque[str] = deque(maxlen=self.NEWEST_WAKES)  # the day of each of the newest wakes
        self.intents: dict[str, int] = {}  # agent -> its `agent.intent` rows
        self.looks: dict[str, Mapping[str, Any]] = {}  # agent -> its latest look's payload
        self.moves: dict[str, list[Entry]] = {}  # agent -> its promotions and demotions, oldest first

    def advance(self) -> "_Folds":
        with self.lock:
            for entry in self.ledger.iter(kinds=self.KINDS, after=self.seq):
                self._fold(entry)
                self.seq = entry.seq
        return self

    def _fold(self, entry: Entry) -> None:
        kind, p, day = entry.kind, entry.payload, entry.at[:10]
        if kind == "credit.charge":
            amount, bucket = Decimal(p["usd"]), _bucket(p.get("what", ""))
            self.spend[bucket] += amount
            self.spend_days.setdefault(day, {b: ZERO for b in BUCKETS})[bucket] += amount
            self.cost[entry.agent] = self.cost.get(entry.agent, ZERO) + amount
        elif kind == "ops.budget":
            if p.get("what") == "sail" and p.get("spent_usd") is not None:
                amount = Decimal(p["spent_usd"])
                self.sail = (ZERO if self.sail is None else self.sail) + amount
                self.sail_days[day] = self.sail_days.get(day, ZERO) + amount
        elif kind == "provider.request":
            if p.get("profile"):
                self.profiles.add(str(p["profile"]))
        elif kind in ("merton.pass", "audit.verdict"):
            if not self.frontier_paid and Decimal(str(p.get("cost_usd") or 0)) > 0:
                self.frontier_paid = True
        elif kind == "agent.woke":
            self.wake_days.append(day)
        elif kind == "agent.intent":
            self.intents[entry.agent] = self.intents.get(entry.agent, 0) + 1
        elif kind == "eval.verdict":
            decision = p.get("decision")
            if decision == "look":
                self.looks[entry.agent] = p
            elif decision in ("promote", "demote"):
                self.moves.setdefault(entry.agent, []).append(entry)


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
        self.real_brokers = dict(real_brokers or {})
        self.opener = opener or urllib.request.urlopen
        self.clock = clock
        self._state = self._load()
        self._flows = None
        if self.real_brokers and self.performance:
            from ltcm.performance import AccountPerformance

            self._flows = AccountPerformance({**self.performance, "venues": sorted(self.real_brokers)}, self.real_brokers, clock=clock)
        self._venue_rows: dict[str, dict[str, Any]] = {}
        self._folds: _Folds | None = None  # what the checkpoint sums over the whole ledger (`_folded`)

    def _folded(self, house: Any) -> _Folds:
        """The checkpoint's folds of `house`'s ledger, brought up to its newest row (`_Folds`)."""
        if self._folds is None or self._folds.ledger is not house.ledger:
            self._folds = _Folds(house.ledger)
        return self._folds.advance()

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

    # --------------------------------------------------------------- transport
    def post(self, path: str, body: Mapping[str, Any]) -> tuple[int, Any]:
        request = urllib.request.Request(
            self.base + path, data=canonical(body).encode("utf-8"), method="POST",
            headers={"Authorization": "Bearer " + self.token_source(), "Content-Type": "application/json", "Accept": "application/json", "User-Agent": "ltcm-floor/1.0"},
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
        status, reply = self.post("/events", {"schema_version": 1, "events": events})
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

    # -------------------------------------------------------------- real accounts
    def account(self, house: Any = None) -> dict[str, Any] | None:
        """The real venue accounts, read now. A venue that does not answer keeps its last good row,
        marked stale, and a floor with a stale row publishes no profit figure.

        `account_equity`, the number the public chart draws, is on the LEAGUE'S BASIS: the balance
        the accounts held when the record began (`performance.start_equity`) plus what the league's
        own real-money trading has made since. The owner's decision of Sept 19, 2026: the chart is
        flat until the league trades real money. The raw balance also moves for reasons that are
        not the league's (the owner's transfers; the contracts the first run left behind, marked to
        market until they settle), and it is published beside it as `real_account_equity`."""
        if not self.real_brokers:
            return None
        rows = []
        for venue in sorted(self.real_brokers):
            try:
                balance = self.real_brokers[venue].balance()
                row = {"venue": venue, "equity": money(balance.equity, 4), "cash": money(balance.cash, 4), "as_of": now_iso(self.clock)}
                self._venue_rows[venue] = row
            except Exception:  # noqa: BLE001
                row = self._venue_rows.get(venue)
                if row is None:
                    return None
                row = {**row, "stale": True}
            rows.append(row)
        real = sum(Decimal(r["equity"]) for r in rows)
        start = self.performance.get("start_equity")
        shown = Decimal(str(start)) + league_real_pnl(house) if start is not None and house is not None else real
        return {
            "account_equity": money(shown, 4),
            "real_account_equity": money(real, 4),
            "account_cash": money(sum(Decimal(r["cash"]) for r in rows), 4),
            "venues": rows,
        }

    def mark_floor(self, house: Any) -> None:
        now = self.clock()
        if now - float(self._state["last_mark"]) < MARK_EVERY_SECONDS:
            return
        account = self.account(house)
        if account is None or any(row.get("stale") for row in account["venues"]):
            return
        self._state["last_mark"] = now
        self._account = account
        house.ledger.append("floor.mark", {**account, "as_of": now_iso(self.clock)})

    # ---------------------------------------------------------------- checkpoint
    def checkpoint(self, house: Any) -> dict[str, Any]:
        # The board, the lab's reading and the accounts are read first: the site refuses a checkpoint
        # whose venue readings (found on the first live publish), band moves or lab reading are stamped
        # later than itself.
        board = self.allocator_board(house)
        lab = self.lab_reading(house)
        account = self.account(house)
        at = now_iso(self.clock)
        ledger = house.ledger
        desks, curve_rows = [], {}
        folds = self._folded(house)  # every whole-ledger sum below, from the new rows only (R6-perf)
        spend = dict(folds.spend)
        spend_today = dict(folds.spend_days.get(at[:10]) or {bucket: ZERO for bucket in BUCKETS})
        living, dead = list(house.registry.living()), list(house.registry.dead())
        rungs = {agent.id: self._rung(house, agent) for agent in living + dead}
        bands = {agent.id: self._band(board, agent.id, rungs[agent.id]) for agent in living + dead}
        order = self.ranked(house, living, dead, bands=bands)
        displayed = set(order)
        living_rows, ledger_moves = [], []
        # The roster is bounded for the site, but the experiment includes every agent ever born.
        # Removing an old loser from the display must never remove its loss or research cost.
        for agent in living + dead:
            row, generation = self._desk(house, agent, at, board=board, rung=rungs[agent.id])
            if agent.id in displayed:
                desks.append(row)
            if agent.alive:
                living_rows.append(row)
            ledger_moves.extend(generation.pop("moves", []))
            g = curve_rows.setdefault(agent.generation, {"desks": 0, "decisions": 0, "cost": ZERO, "pnl": ZERO, "capital": ZERO})
            g["desks"] += 1
            g["decisions"] += generation["decisions"]
            g["cost"] += generation["cost"]
            g["pnl"] += generation["pnl"]
            g["capital"] += generation["capital"]
        curve = []
        for generation in sorted(curve_rows)[:40]:
            g = curve_rows[generation]
            excess = ((g["pnl"] - g["cost"]) / g["capital"] * 100) if g["capital"] > 0 else ZERO
            curve.append({
                "generation": int(generation), "desks": min(g["desks"], MAX_DESKS), "decisions": g["decisions"], "cost_usd": money(g["cost"], 4),
                "pnl_usd": money(g["pnl"], 4, signed=True), "cost_adjusted_excess_pct": money(excess, 4, signed=True), "brier": None,
                "pnl_per_inference_usd": money(g["pnl"] / g["cost"], 4, signed=True) if g["cost"] > 0 else "0",
            })
        started = next(iter(ledger.read(kinds="ops.started", limit=1)), None)
        started_at = started.at if started else at
        practice_equity = sum((book.total_equity() for book in house.books.values() if not book.real_money), ZERO)
        floor: dict[str, Any] = {
            "equity": money(Decimal(account["account_equity"]) if account else practice_equity, 4),
            "cash": money(Decimal(account["account_cash"]) if account else ZERO, 4),
            "daily_pnl": "0", "capital_usd": money(self.performance.get("start_equity") or 0, 4), "since_inception_pct": "0", "benchmark": None,
            "live_desks": sum(1 for d in desks if d["mode"] == "live" and d["status"] == "active"),
            "shadow_desks": sum(1 for d in desks if d["mode"] == "shadow" and d["status"] == "active"),
        }
        pnl_total = ZERO
        if account:
            # The site's schema is exact: the raw balance stays on the ledger's floor.mark rows.
            floor.update({k: v for k, v in account.items() if k != "real_account_equity"})
            if self._flows is not None:
                performance = self._flows.read({"venues": account["venues"]}, at)
                # `account_equity` is already on the league's basis (see `account`): start + the league's
                # own real-money result. Nothing else moves it, so there is nothing to subtract.
                if performance.get("net_flows") is not None:
                    performance["net_flows"] = "0"
                floor["performance"] = performance
                if performance.get("net_flows") is not None:
                    pnl_total = Decimal(account["account_equity"]) - Decimal(str(performance["start_equity"])) - Decimal(str(performance["net_flows"]))
                    floor["since_inception_pct"] = money(pnl_total / Decimal(str(performance["start_equity"])) * 100, 4, signed=True)
        # Frontier consultations and audits are charged to agent credits too, but are not Sail
        # expenses. Prefer the actual Sail balance-debit meter, which also sees the House box and
        # unassigned infrastructure. Without it, publish only the attributed Sail estimate.
        sail_total = spend["tokens"] + spend["boxes"] + spend["search"]
        sail_today = spend_today["tokens"] + spend_today["boxes"] + spend_today["search"]
        if folds.sail is not None:  # metered
            sail_total = folds.sail
            sail_today = folds.sail_days.get(at[:10], ZERO)
        pacer = getattr(house, "pacer", None)
        daily_cap = pacer.allowance("sail") if pacer is not None else Decimal(house.game["economy"]["daily_pool_usd"])
        wakes = ledger.count(kinds="agent.woke")
        body = {
            "schema_version": 1,
            "published_at": at,
            "floor": floor,
            "desks": desks,
            "committee": {"last_memo_at": None, "allocations": {d["id"]: d["capital_usd"] for d in desks if d["status"] == "active"}},
            "budget": {"spent_today_usd": money(sail_today, 4), "cap_usd": money(daily_cap, 2),
                       "mode": "stopped" if (house.budget is not None and house.budget.mode == "stopped") else "open"},
            "infra": {"host": "sailbox" if os.environ.get("SAILBOX_ID") or Path("/workspace").exists() else "local"},
            "run": {
                "started_at": started_at, "uptime_seconds": int(max(self.clock() - _epoch(started_at), 0)), "availability_7d_pct": None,
                "sessions_total": wakes, "sessions_today": min(wakes, sum(1 for day in folds.wake_days if day == at[:10])),
                "decisions_total": ledger.count(kinds="agent.intent"),
                "sail_model_spend_today_usd": money(spend_today["tokens"], 4), "sail_model_spend_total_usd": money(spend["tokens"], 4),
                "sail_infra_spend_total_usd": money(spend["boxes"], 4), "sail_spend_total_usd": money(sail_total, 4),
                "pnl_total_usd": money(pnl_total, 4, signed=True),
                "pnl_per_sail_dollar": money(pnl_total / sail_total, 4, signed=True) if sail_total > 0 else None,
                "models_used": self._models_used(house, spend["tokens"]),
            },
            "lab": {"experiments": [], "curve": curve, "calibration": {"n": 0, "brier": None}},
        }
        body["board"] = self._board_block(board, at, living_rows, ledger_moves)
        if lab is not None:
            body["board"]["lab"] = lab  # with or without the allocator: the lab's line is its own
        return self.fit(body, order)

    # ----------------------------------------------------------------- the capital board
    @staticmethod
    def allocator_board(house: Any) -> Mapping[str, Any] | None:
        """`house.allocator.board()`, or None when there is no allocator, it fails, or it has not
        drawn a board yet: the board is what the page draws, and it never costs the floor its
        checkpoint. The allocator holds an empty placeholder (no agents, no bands, no moves) until
        its first rebalance, which is every House restart until the first mark pass and forever
        while the constitution switches it off; publishing that would empty the page's lanes and
        its trail, so the roster's bands and the ledger's moves stand in for it instead."""
        allocator = getattr(house, "allocator", None)
        if allocator is None:
            return None
        try:
            board = allocator.board()
        except Exception:  # noqa: BLE001 - a broken board falls back to the rungs, never to no checkpoint
            return None
        if not isinstance(board, Mapping):
            return None
        agents = board.get("agents")
        return board if isinstance(agents, Mapping) and agents else None

    def lab_reading(self, house: Any) -> dict[str, Any] | None:
        """The lab's hourly reading for the board's `lab` (`site_lab`, from the newest `lab.stats` row), or
        None: none written, none fresh, or none that can be read. A display line never costs the floor its
        checkpoint."""
        try:
            return site_lab(house.ledger.last("lab.stats"), self.clock())
        except Exception:  # noqa: BLE001 - the lab's line is a courtesy; the checkpoint is not
            return None

    @staticmethod
    def _rung(house: Any, agent: Any) -> int | None:
        try:
            return int(house.evaluator.rung(agent.id))
        except Exception:  # noqa: BLE001 - a display field, never a reason to skip publishing
            return None

    @staticmethod
    def _allocated(board: Mapping[str, Any] | None, agent_id: str) -> Mapping[str, Any] | None:
        agents = board.get("agents") if board is not None else None
        row = agents.get(agent_id) if isinstance(agents, Mapping) else None
        return row if isinstance(row, Mapping) else None

    @classmethod
    def _band(cls, board: Mapping[str, Any] | None, agent_id: str, rung: int | None) -> str | None:
        row = cls._allocated(board, agent_id)
        return row["band"] if row is not None and row.get("band") in BANDS else rung_band(rung)

    @classmethod
    def band_fields(cls, board: Mapping[str, Any] | None, agent_id: str, rung: int | None, at: str) -> dict[str, Any]:
        """A desk row's board fields. With the allocator: `band`, `stake_usd` (real bands only, else
        null), `evidence` and `last_move` (null when there is none), and since Sept 24, 2026 its family's
        `family_state` and `family_n` when the board carries them (`site_family_fields`). Without it, or
        for an agent the allocator does not list: the band the rung implies, and nothing else."""
        fields: dict[str, Any] = {}
        band = cls._band(board, agent_id, rung)
        if band is not None:
            fields["band"] = band
        row = cls._allocated(board, agent_id)
        if row is None:
            return fields
        try:
            fields.update({
                "stake_usd": site_stake(row.get("stake_usd")) if band in REAL_BANDS else None,
                "evidence": site_evidence(row.get("evidence")),
                "last_move": site_last_move(row.get("last_move"), at),
            })
            fields.update(site_family_fields(row))
        except Exception:  # noqa: BLE001 - odd allocator data costs the row its evidence, not the checkpoint
            fields = {"band": band} if band is not None else {}
        return fields

    @staticmethod
    def _board_block(board: Mapping[str, Any] | None, at: str, living_rows: list[dict[str, Any]], ledger_moves: list[dict[str, Any]]) -> dict[str, Any]:
        """The checkpoint's `board`: the allocator's own summary, or, without one, the roster's bands
        (count, and real capital on the real bands) and the ledger's last 50 promotions and demotions."""
        if board is not None:
            try:
                return site_board(board, at)
            except Exception:  # noqa: BLE001 - fall through to what the roster itself says
                pass
        bands: dict[str, dict[str, dict[str, Any]]] = {}
        for row in living_rows:
            band = row.get("band")
            if band not in BANDS:
                continue
            entry = bands.setdefault(row["venues"][0], {}).setdefault(band, {"count": 0, "capital": ZERO})
            entry["count"] += 1
            if band in REAL_BANDS:
                entry["capital"] += Decimal(row["capital_usd"])
        moves = sorted((m for m in ledger_moves if _not_after(m["at"], at)), key=lambda m: (m["at"], m["id"]))[-MAX_BOARD_MOVES:]
        return {"enabled": False, "moves": moves,
                "bands": {venue: {band: {"count": e["count"], "capital_usd": money(e["capital"], 2)} for band, e in per.items()} for venue, per in bands.items()}}

    @staticmethod
    def _seat_rows(body: dict[str, Any], desks: list[dict[str, Any]]) -> None:
        body["desks"] = desks
        body["floor"]["live_desks"] = sum(1 for d in desks if d["mode"] == "live" and d["status"] == "active")
        body["floor"]["shadow_desks"] = sum(1 for d in desks if d["mode"] == "shadow" and d["status"] == "active")
        body["committee"]["allocations"] = {d["id"]: d["capital_usd"] for d in desks if d["status"] == "active"}

    @classmethod
    def fit(cls, body: dict[str, Any], order: list[str]) -> dict[str, Any]:
        """The body inside the site's byte limit: the least important rows (the oldest dead, then the
        youngest of the lowest band) are left out until it fits. The totals keep every agent."""
        size = lambda: len(canonical(body).encode("utf-8"))  # noqa: E731
        excess = size() - MAX_CHECKPOINT_BYTES
        if excess <= 0:
            return body
        rows = {d["id"]: d for d in body["desks"]}
        ranked = [agent_id for agent_id in order if agent_id in rows] + [d["id"] for d in body["desks"] if d["id"] not in set(order)]
        dropped: set[str] = set()
        for agent_id in reversed(ranked):
            if excess <= 0:
                break
            dropped.add(agent_id)
            excess -= len(canonical(rows[agent_id]).encode("utf-8")) + 2 * len(agent_id) + 24
        cls._seat_rows(body, [d for d in body["desks"] if d["id"] not in dropped])
        for agent_id in reversed(ranked):  # the estimate is close; the exact size decides
            if size() <= MAX_CHECKPOINT_BYTES or not body["desks"]:
                break
            if agent_id not in dropped:
                dropped.add(agent_id)
                cls._seat_rows(body, [d for d in body["desks"] if d["id"] not in dropped])
        return body

    @staticmethod
    def ranked(house: Any, living: list[Any], dead: list[Any], *, bands: Mapping[str, str | None] | None = None) -> list[str]:
        """The agents the site shows, most important first, at most `MAX_DESKS`: every agent on real
        money first (the highest band, or rung, first), then the rest of the living, then the most
        recent dead to fill what is left (at most `MAX_DEAD_SHOWN`, the newest first). The totals
        still count every agent ever born."""
        def rank(agent: Any) -> tuple[int, str]:
            band = (bands or {}).get(agent.id)
            if band in BANDS:
                level = BANDS.index(band)
            else:
                try:
                    level = int(house.evaluator.rung(agent.id))
                except Exception:  # noqa: BLE001 - a display order, never a reason to skip publishing
                    level = 0
            return (-level, str(agent.born_at or ""))

        shown = [a.id for a in sorted(living, key=rank)][:MAX_DESKS]
        room = max(0, min(MAX_DEAD_SHOWN, MAX_DESKS - len(shown)))
        if room:
            shown += [a.id for a in reversed(dead[-room:])]
        return shown

    @classmethod
    def displayed(cls, house: Any, living: list[Any], dead: list[Any], *, bands: Mapping[str, str | None] | None = None) -> set[str]:
        return set(cls.ranked(house, living, dead, bands=bands))

    def _models_used(self, house: Any, token_spend: Decimal) -> list[str]:
        from ltcm.provider import DISPLAY_NAMES, PROFILES
        from .frontier import MODEL

        folds = self._folded(house)
        profiles = set(folds.profiles)
        if not profiles and token_spend > 0:
            # Older research charges did not carry a profile. The configured profile is the best
            # available attribution for those rows, rather than a hardcoded model from launch day.
            profiles.add(str((house.game.get("research") or {}).get("profile", "flash_flex")))
        models = set()
        for profile in profiles:
            model = PROFILES[profile][0] if profile in PROFILES else profile
            models.add(DISPLAY_NAMES.get(model, model))
        if folds.frontier_paid:
            frontier = getattr(getattr(house, "merton", None), "frontier", None)
            models.add(str(getattr(frontier, "model", MODEL)))
        return [clean_text(model, 40) for model in sorted(models)[:8]]

    def _desk(self, house: Any, agent: Any, at: str, *, board: Mapping[str, Any] | None = None, rung: int | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
        rung = house.evaluator.rung(agent.id) if rung is None else rung
        book = house.book_of(agent) if agent.alive else next((b for b in house.books.values() if agent.id in b.accounts), None)
        account = book.account(agent.id) if book is not None and agent.id in book.accounts else None
        staked = account.staked if account else ZERO
        capital = staked if staked > 0 else Decimal(CONSTITUTION["rungs"]["1"]["stake_usd"]) if account else ZERO
        equity = book.equity(agent.id) if account else ZERO
        pnl = (equity - staked) if account and staked > 0 else (account.realized if account else ZERO)
        folds = self._folds if self._folds is not None and self._folds.ledger is house.ledger else self._folded(house)
        cost = folds.cost.get(agent.id, ZERO)
        intents = folds.intents.get(agent.id, 0)
        look = folds.looks.get(agent.id)  # its latest look
        moves = folds.moves.get(agent.id, [])
        lifecycle = {"born_at": agent.born_at, "died_at": agent.died_at, "cause": agent.cause,
                     "last_move": {"id": moves[-1].id, "at": moves[-1].at,
                                   **{k: moves[-1].payload.get(k) for k in ("decision", "from_rung", "to_rung", "reason")}} if moves else None}
        accounting_ok = book.evidence_integrity(agent.id)["ok"] if book is not None else True
        positions = []
        if account and book is not None:
            for holding in list(account.holdings.values())[:50]:
                inst = holding.instrument
                mark = book.marks.get(inst.key) or holding.average_cost
                value = holding.quantity * mark * inst.multiplier
                positions.append({
                    # Every string inside the site's 80 (`site_market_id`): one long id refused the whole checkpoint (Sept 25, 2026).
                    "instrument": {"symbol": js_cut(option_label(inst.to_dict()) if inst.asset_class == "option" else (inst.market_id or inst.symbol), MAX_INSTRUMENT_TEXT),
                                   "asset_class": inst.asset_class, "venue": "kalshi" if agent.venue == "kalshi" else "alpaca",
                                   **({"market_id": site_market_id(inst.to_dict())} if inst.market_id else {}), **({"right": inst.right} if inst.right else {})},
                    "side": (inst.right or "yes") if inst.asset_class == "event" else "long",
                    "quantity": money(holding.quantity, 8), "entry_price": money(holding.average_cost, 6), "mark_price": money(mark, 6),
                    "market_value": money(value, 4), "unrealized_pnl": money(value - holding.cost, 4, signed=True),
                    "opened_at": min(holding.opened_at or at, at), "thesis": clean_text(holding.reason, 240),
                    "target_price": None, "stop_price": None, "time_stop_at": None, "exit_orders": [],
                })
        next_wake = house._state["next_wake"].get(agent.id)
        born = _epoch(agent.born_at)
        row = {
            "id": agent.id, "name": agent.id, "family": desk_family(agent.family), "generation": int(agent.generation),
            "parent_id": agent.parent if agent.parent != agent.id else None,
            "mode": "live" if (book is not None and book.real_money) else "shadow",
            "venues": ["kalshi" if agent.venue == "kalshi" else "alpaca"],
            "capital_usd": money(capital, 2), "cost_usd": money(cost, 4), "max_drawdown_pct": money(Decimal(str(look.get("drawdown") or 0)) * 100 if look is not None else 0, 4),
            "equity": money(equity, 4, signed=True), "cash": money(account.cash if account else 0, 4, signed=True), "daily_pnl": "0",
            "return_pct": money((pnl / capital * 100) if capital > 0 else 0, 4, signed=True),
            "days_live": int(max(self.clock() - born, 0) // 86400), "orders": intents,
            "status": "active" if agent.alive else "retired",
            "gate": {"name": f"rung {rung}", "passed": rung >= 2, "evidence": clean({"decisions": intents, "rung": rung, "credits_usd": money(house.economy.balance(agent.id), 4, signed=True),
                     "niche": agent.niche, "accounting_ok": accounting_ok, "lifecycle": lifecycle,
                     "last_look": {k: look.get(k) for k in ("look", "active_blocks", "mean", "lcb", "ucb", "alpha_spent")} if look is not None else None})},
            "updated_at": at, "pnl_usd": money(pnl, 4, signed=True), "positions": positions,
        }
        if agent.alive and next_wake:
            row["next_session_at"] = now_iso(lambda: float(next_wake))
        row.update(self.band_fields(board, agent.id, rung, at))
        trail = [m for m in (ledger_board_move(entry, agent) for entry in moves[-MAX_BOARD_MOVES:]) if m is not None]
        return row, {"decisions": intents, "cost": cost, "pnl": pnl, "capital": capital, "moves": trail}


def _epoch(iso: str) -> float:
    from ltcm.broker import instant

    parsed = instant(iso)
    return parsed.timestamp() if parsed else 0.0
