"""THE EQUITY BOOK: every lot real money holds for an equity program, its order path, reconciliation and exports.

Owner: book. The House's live equity path, outside the options fingerprint. `league/live/step.py` calls `tick` exactly
once a minute (league/live/equity_hook.py builds the book; a CI string test holds that call site to one); everything
else the book does follows its own clock (league/equity/schedule.py).

TABLES in `<state>/live.sqlite` (`SCHEMA`; money and share quantities are Decimal strings, never floats): `eq_lots`,
`eq_orders`, `eq_fills`, `eq_intents` (decisions recorded at 16:30 ET, executed next session), `eq_bars` (the bars each
decision used, A8.11), `eq_activities` (dividends, splits and corporate actions booked, A8.10), `eq_exports` (lots
exported to the forward record), `eq_instances` (the program each equity instance runs; never the options
`instances` table, which the options path restores and loads).

THE ORDER PATH (the options path's discipline): a row is written `pending` BEFORE the POST, client id
`lq-<nonce>-<eid>-<family>` (`client_id`: the process nonce of `LiveState`, as the options book's ids, so a rolled-back
state never sends an id the venue has seen); a lost answer is `unknown` and is looked up by its client id, never
re-sent blind (an order the venue still does not show by its client id after `LOST_AFTER_S` is `lost`: an entry is then
missed, never re-sent; an exit may go again, the reconciliation being the backstop); one working order per symbol
across BOTH books (wash-trade protection: the options book's `busy()` symbols, the venue's working orders that are not
this book's, e.g. the House's assignment-share closes, and the equity book's). CANCEL THEN RESEND (A8.4): a
replacement goes only once the old order is terminal (filled, canceled, expired, rejected), sized target minus filled;
the old order's remaining quantity stays in exposure until then. A cancel is followed by one lookup of the order, so a
replacement can go in the same minute. ONE DAY ORDER COUNT (A8.3): at most `order_path.max_orders_day` (60) equity
orders a day (cancels counted, as the options book counts its own), entries leaving room for every open lot's exit and
one cancel of it, and none while the House-wide count would leave less than the options book's `exit_reserve()`.

THE WINDOWS (`schedule`): OPEN: exits first at open+30 s (09:30:30 ET), entries after the exits filled or 2 minutes,
sized on cash after the exit fills (no entry is funded by an exit that has not filled: the account is read again before
the entries are sized, and an unfilled sale adds nothing to its cash); collar `entry_collar_bp` (10 ETF / 25 stock) on
the first send, widening by the same step each re-price to `max_collar_bp` (50 / 100), and at the widest collar
re-priced only when the quote has moved through the limit (`_reprice_due`: the day's order count is shared); entries stop at open+15 min
(09:45); exits continue to close-5 min (15:55), then go at the bid at the widest collar in the close window. CLOSE (A2):
at close-5 min (15:55:00) exits first then entries, marketable limits re-priced every 30 s to close-30 s (15:59:30),
then recorded missed. PRE-OPEN (09:25): the day's first reconciliation reading and an activities read (a split or a
dividend posted overnight); the windows' orders are the decide's intents (`eq_intents`), each written `pending` at its
own send with that minute's quote, never at 09:25 with a pre-open price. A missed entry is recorded, never chased; an exit the windows could not fill is recorded missed
and carried to the next session's open (a "house_exit" intent of the same reason). MIN HOLD: a lot never sells in the
session it was bought (kill switch and stops included; the gateway's kill blocks sells too). NO STUCK LOTS (A8.5): a
lot held its program's `max_hold_sessions` exits at the next open; a demoted, retired or band-dropped program's lots
exit at the next open; 2 sessions of failed decides exit the program's lots at the next open; on a restart a catch-up
decide runs for the last close if it was missed (until the next session's close window). Limits: a buy rounds UP and a
sell DOWN to the cent ($1 and above; to 0.0001 under it: the venue's sub-penny rule); quantities are floored to
`config.QTY_PLACES` for a buy and sent whole (nine places at most) for a sale.

SIZING: `league.equity.sizing.size_entry` (money's; never re-implemented here), with the House-wide available cash of
`league.live.money.available_cash` (A8.1: `working_buys_worst` the equity book's working buys, `reserved` the options
book's working reservations, which cover its open orders' worst cost). Every real open asks `real_block(opening=True)`
first (grant, kill switch, stops, both books' reconciliation, the assignment latch, the House pause, the account read),
then its own gates: `equity_money.enabled`, the stock paper proof passed (`paper_proof_stock`, A8.7), its own freeze,
the program's band, the shared loss budget's room (the lower of the window's and the total's, from
`league.live.real.probe_figures`, which unions the equity rows through the hook), applied to every equity open, Probe
or Sized (A5: "sizing always fits the remaining loss budget").

ATTRIBUTION: lots are per instance; the venue nets per symbol. A sale is FIFO within the instance's own lots, never
another program's. DIVIDENDS and SPLITS and the other corporate actions (A8.10): league/equity/actions.py.
RECONCILIATION: every minute from the pre-open to the close, the account's us_equity quantity per symbol against
`expected_shares()` plus the share-event ledger (assignment and exercise shares, A8.2), as Decimal with a 1e-9 share
tolerance; a symbol with a working equity order, or one that filled in the last `FLUX_S` seconds, is not judged that
minute (its fills and the account's reading race each other). Two mismatched readings freeze equity entries (exits go
on); two clean readings lift it. The freeze also blocks options opens (league/live/step.py `real_block`).
EXPORTS: a closed lot goes to the forward record (league/equity/families.py `add_forward`) with net cash, fees,
dividends, notional, hold and its twin key `eq:<lid>`. A dividend paid after a lot was exported reaches `eq_lots` (which
the Done meter and the band rules read) but not that forward row.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import re
import time
import traceback
from dataclasses import dataclass, field
from decimal import ROUND_CEILING, ROUND_DOWN, ROUND_FLOOR, Decimal
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .. import equity as _pkg
from ..live import money as M
from ..live.state import dumps, loads
from ..live.venue import TERMINAL as VENUE_TERMINAL
from ..live.venue import WORKING as VENUE_WORKING
from ..live.venue import parse_time
from . import actions as A
from . import bands as B
from . import config
from . import ctx as C
from . import program as P
from . import schedule as S
from . import sizing as Z

#: The book's tables (created by `EquityBook.__init__`, one statement at a time through `LiveState.execute`).
SCHEMA = """
CREATE TABLE IF NOT EXISTS eq_lots (
    lid INTEGER PRIMARY KEY, instance TEXT NOT NULL, family TEXT NOT NULL, version INTEGER NOT NULL, lane TEXT NOT NULL,
    symbol TEXT NOT NULL, class TEXT NOT NULL, qty TEXT NOT NULL, opened_qty TEXT NOT NULL, entry_px TEXT NOT NULL,
    entry_notional TEXT NOT NULL, entry_at TEXT NOT NULL, fees TEXT NOT NULL DEFAULT '0', div TEXT NOT NULL DEFAULT '0',
    mark TEXT, marked_at REAL, opened_at REAL NOT NULL, opened_day TEXT NOT NULL, status TEXT NOT NULL,
    exit_px TEXT, exit_at TEXT, exit_day TEXT, closed_at REAL, cash TEXT NOT NULL DEFAULT '0', reason TEXT,
    probe INTEGER NOT NULL DEFAULT 0, tag TEXT, iid INTEGER, info TEXT NOT NULL DEFAULT '{}');
CREATE INDEX IF NOT EXISTS eq_lots_status ON eq_lots(status);
CREATE TABLE IF NOT EXISTS eq_orders (
    eid INTEGER PRIMARY KEY, client_id TEXT UNIQUE NOT NULL, venue_id TEXT, instance TEXT NOT NULL, family TEXT NOT NULL,
    lid INTEGER, iid INTEGER, side TEXT NOT NULL, symbol TEXT NOT NULL, class TEXT NOT NULL, at TEXT NOT NULL,
    qty TEXT NOT NULL, limit_px TEXT NOT NULL, collar_bp INTEGER NOT NULL, status TEXT NOT NULL, placed_at REAL NOT NULL,
    day TEXT NOT NULL, filled_qty TEXT NOT NULL DEFAULT '0', avg_px TEXT, fees_est TEXT NOT NULL DEFAULT '0',
    replaces INTEGER, probe INTEGER NOT NULL DEFAULT 0, why TEXT, answer TEXT, updated_at REAL NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0);
CREATE INDEX IF NOT EXISTS eq_orders_status ON eq_orders(status);
CREATE TABLE IF NOT EXISTS eq_fills (
    fid INTEGER PRIMARY KEY AUTOINCREMENT, eid INTEGER NOT NULL, lid INTEGER, venue_fill_id TEXT, qty TEXT NOT NULL,
    px TEXT NOT NULL, fees TEXT NOT NULL DEFAULT '0', at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS eq_intents (
    iid INTEGER PRIMARY KEY, instance TEXT NOT NULL, family TEXT NOT NULL, version INTEGER NOT NULL,
    decided_day TEXT NOT NULL, exec_day TEXT NOT NULL, at TEXT NOT NULL, kind TEXT NOT NULL, symbol TEXT, lid INTEGER,
    share TEXT, usd TEXT, tag TEXT, status TEXT NOT NULL, why TEXT, ctx_sha TEXT, bars_sha TEXT,
    created_at REAL NOT NULL, updated_at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS eq_intents_exec ON eq_intents(exec_day, status);
CREATE TABLE IF NOT EXISTS eq_bars (
    day TEXT NOT NULL, symbol TEXT NOT NULL, adjustment TEXT NOT NULL, o TEXT, h TEXT, l TEXT, c TEXT, v TEXT,
    fetched_at REAL NOT NULL, sha TEXT NOT NULL, audit TEXT, PRIMARY KEY (day, symbol, adjustment));
CREATE TABLE IF NOT EXISTS eq_activities (
    id TEXT PRIMARY KEY, type TEXT NOT NULL, symbol TEXT, day TEXT, qty TEXT, net TEXT, booked TEXT NOT NULL,
    at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS eq_exports (lid INTEGER PRIMARY KEY, exported_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS eq_instances (
    id TEXT PRIMARY KEY, family TEXT NOT NULL, version INTEGER NOT NULL, lane TEXT NOT NULL, run_sha TEXT NOT NULL,
    code TEXT NOT NULL, params TEXT NOT NULL, band TEXT NOT NULL, seeded INTEGER NOT NULL DEFAULT 0,
    max_hold INTEGER NOT NULL, failed_decides INTEGER NOT NULL DEFAULT 0, last_decided_day TEXT, created_at REAL NOT NULL,
    retired_at REAL, why TEXT);
"""

#: Order statuses that still hold quantity or may yet fill.
WORKING = ("pending", "working", "unknown")
#: Terminal order statuses (a replacement may go only after one of these: A8.4).
TERMINAL = ("filled", "canceled", "expired", "rejected", "lost", "missed", "refused")
#: Lot statuses.
LOT_OPEN, LOT_CLOSING, LOT_CLOSED = "open", "closing", "closed"
#: The real (evidence) route's instance suffix, as the options book's (`league.live.real.REAL_SUFFIX`).
REAL_SUFFIX = ":r"
#: The share tolerance of every equity reconciliation (fractional shares, nine places at the venue).
SHARE_TOLERANCE = Decimal("1e-9")
CLIENT_PREFIX = _pkg.CLIENT_PREFIX

ZERO = Decimal(0)
CENT = Decimal("0.01")
SUBPENNY = Decimal("0.0001")
SHARE_PLACES = Decimal("1e-9")
PRICE_PLACES = Decimal("1e-6")
BP = Decimal(10000)
#: An intent's statuses still to execute, and the kinds that sell a lot.
INTENT_LIVE = ("planned", "sent")
EXIT_KINDS = ("sell", "house_exit")
#: The bands a live equity instance runs in.
LIVE_BANDS = ("probe", "sized")
#: Why the House itself exits a lot (`eq_lots.reason`, a house_exit intent's tag); "program" is the program's own sale.
HOUSE_REASONS = ("max_hold", "house", "demoted", "retired", "flatten", "forced", "carried")
#: The collars when the equity table cannot be read (exits only then): the design's.
DEFAULT_COLLARS = {"entry": {"etf": 10, "stock": 25}, "max": {"etf": 50, "stock": 100}}
#: Seconds between two reads of the activities (`actions.TYPES`), and of the watched types (`actions.WATCH`).
ACTIVITIES_EVERY = 900.0
WATCH_EVERY = 3600.0
#: An unknown order is lost when the venue still does not show it by its client id after this many lookups or seconds.
LOST_AFTER_TRIES = 4
LOST_AFTER_S = 600.0
#: A pending row younger than this is being sent right now (never looked up yet).
PENDING_GRACE_S = 30.0
#: Lookups by client id a minute, at most.
LOOKUP_LIMIT = 6
#: A cancel is not sent again for the same order within this many seconds.
CANCEL_AGAIN_S = 50.0
#: A symbol whose equity order is working, or ended this recently, is not reconciled that minute.
FLUX_S = 120.0
#: An exit the gateway or the venue refused this many times in a session is carried to the next one (and alarmed).
MAX_EXIT_REFUSALS = 3
#: The widest quoted spread an entry is sized on (a wider quote waits a minute): a fraction of the mid.
MAX_ENTRY_SPREAD = Decimal("0.02")
#: Seconds after `decide_at` the decide waits for a missing bar before deciding without it (those instances fail).
BARS_GRACE_S = 1800.0
#: A program's decide: its per-call limit and error budget (the Gym runner's).
DECIDE_TIMEOUT = 1.0
DECIDE_MAX_ERRORS = 25
#: How many sessions before a dividend's date the book looks for the holding its quantity names.
DIVIDEND_LOOKBACK_SESSIONS = 70
#: Closed lots exported a minute, at most.
EXPORT_LIMIT = 50
_SLUG = re.compile(r"[^a-z0-9-]+")


def D(value: Any, default: Decimal | None = None) -> Decimal:
    """A Decimal from a row's string (or an int); `default` (else ValueError) when it is absent or not finite."""
    if value is None or value == "":
        if default is not None:
            return default
        raise ValueError("no number")
    out = A.dec(value)
    if out is None:
        if default is not None:
            return default
        raise ValueError(f"not a number: {value!r}")
    return out


def text(value: Decimal) -> str:
    """A Decimal as the plain string the tables and the venue take (never an exponent)."""
    return format(value, "f")


def qty_text(qty: Decimal) -> str:
    """A share quantity as the venue takes it: plain, at most nine places, no trailing zeros."""
    s = format(qty.quantize(SHARE_PLACES, rounding=ROUND_DOWN), "f")
    return s.rstrip("0").rstrip(".") if "." in s else s


def client_id(eid: int, family: str, *, nonce: str = "") -> str:
    """`lq-<eid>-<family slug>`, at most 48 characters (the venue's limit), unique by `eid`. With `nonce` (the
    process's, `LiveState.nonce`): `lq-<nonce>-<eid>-<slug>`, so a new or rolled-back state never repeats an id."""
    head = f"{CLIENT_PREFIX}{nonce}-" if nonce else CLIENT_PREFIX
    stem = f"{head}{int(eid):07d}-"
    slug = _SLUG.sub("-", str(family).lower()).strip("-")
    return (stem + slug[:max(0, 48 - len(stem))]).rstrip("-")


def limit_for(side: str, reference: Decimal, collar_bp: int) -> Decimal:
    """A marketable limit: a buy at the ask x (1 + collar), rounded UP; a sale at the bid x (1 - collar), rounded DOWN;
    to the cent at $1 and above, to 0.0001 under it (the venue's sub-penny rule)."""
    collar = Decimal(int(collar_bp)) / BP
    if side == "buy":
        raw = reference * (1 + collar)
        return raw.quantize(CENT if raw >= 1 else SUBPENNY, rounding=ROUND_CEILING)
    raw = reference * (1 - collar)
    out = raw.quantize(CENT if reference >= 1 else SUBPENNY, rounding=ROUND_FLOOR)
    return out if out > 0 else SUBPENNY


def collar_for(attempt: int, entry_bp: int, max_bp: int) -> int:
    """The collar of a window's `attempt`-th send (0 first): the entry collar, widened by the same step each re-price,
    never past the maximum."""
    return int(min(int(entry_bp) * (int(attempt) + 1), int(max_bp)))


def _has_table(rows: Callable[..., list], name: str) -> bool:
    try:
        return bool(rows("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)))
    except Exception:  # noqa: BLE001
        return False


def _weight(weights: Mapping[str, Decimal], klass: Any) -> Decimal:
    """The class's open-risk weight; an unknown class weighs a whole dollar (fail closed)."""
    try:
        return Decimal(str(weights[str(klass)]))
    except (KeyError, TypeError, ValueError, ArithmeticError):
        return Decimal(1)


def _price(row: Mapping[str, Any]) -> Decimal:
    """A lot's mark a share, its entry price while it was never marked."""
    mark = A.dec(row.get("mark"))
    return mark if mark is not None and mark > 0 else D(row.get("entry_px"), ZERO)


@dataclass(frozen=True)
class ProbeFigures:
    """The equity rows' part of THE PROBE LOSS BUDGET (league/live/real.py `probe_tally`, `probe_realized`,
    `probe_figures` union them; A8.6): `programs` open (ONE slot a program with any open ":r" lot or working ":r" buy,
    never one a lot); `closes`: ((NY close day ISO or None, net cash Decimal), ...) of every closed ":r" lot with
    `probe` 1; `open_risk`: sum of open_risk_weight[class] x mark value of every open ":r" lot (entry price when never
    marked) plus weight x remaining qty x limit of every working ":r" buy."""

    programs: int
    closes: tuple[tuple[str | None, Decimal], ...]
    open_risk: Decimal


def probe_figures(rows: Callable[..., list], *, weights: Mapping[str, Decimal]) -> ProbeFigures:
    """The equity rows' Probe figures from the live state's own rows (`rows(sql, params)` returns dicts, as
    `league.live.real.probe_tally`'s), so a restart reads the same numbers. `weights`: {"etf": Decimal("0.20"), "stock":
    Decimal("0.40")}. No eq_lots table (a state from before E1) is all zeros. A program is a family (its versions'
    lots share its one slot). A LOST buy is not counted: had it filled, its shares would be unattributed at the next
    reading (the reconciliation freezes, and the House sells an unattributed long after two readings)."""
    if not _has_table(rows, "eq_lots"):
        return ProbeFigures(0, (), ZERO)
    programs: set[str] = set()
    closes: list[tuple[float, str | None, Decimal]] = []
    risk = ZERO
    for r in rows("SELECT family, class, qty, entry_px, mark, status, cash, exit_day, closed_at, probe FROM eq_lots "
                  "WHERE substr(instance, -2)=?", (REAL_SUFFIX,)):
        if r["status"] == LOT_CLOSED:
            if int(r["probe"] or 0) == 1:
                closes.append((float(r["closed_at"] or 0.0), r["exit_day"] or None, D(r["cash"], ZERO)))
            continue
        qty = D(r["qty"], ZERO)
        if qty <= 0:
            continue
        risk += _weight(weights, r["class"]) * qty * _price(r)
        programs.add(str(r["family"]))
    if _has_table(rows, "eq_orders"):
        for r in rows("SELECT family, class, qty, filled_qty, limit_px FROM eq_orders WHERE side='buy' "
                      "AND substr(instance, -2)=? AND status IN ('pending', 'working', 'unknown')", (REAL_SUFFIX,)):
            remaining = max(ZERO, D(r["qty"], ZERO) - D(r["filled_qty"], ZERO))
            risk += _weight(weights, r["class"]) * remaining * D(r["limit_px"], ZERO)
            programs.add(str(r["family"]))
    closes.sort(key=lambda c: c[0])
    return ProbeFigures(len(programs), tuple((day, cash) for _, day, cash in closes), risk)


def expected_shares_rows(rows: Callable[..., list]) -> dict[str, Decimal]:
    """{symbol: shares} the equity book owns, from the rows alone: its open lots' qty plus the filled part of its working
    buys, less the filled part of its working sells not yet booked. What `_close_shares` and both reconciliations read
    (A8.2: "read in the same pass"). The book books each fill to its lot in the same transaction as the order's
    `filled_qty`, so the unbooked part is normally nothing."""
    out: dict[str, Decimal] = {}
    if not _has_table(rows, "eq_lots"):
        return out
    for r in rows("SELECT symbol, qty FROM eq_lots WHERE status IN ('open', 'closing')"):
        qty = D(r["qty"], ZERO)
        if qty:
            out[str(r["symbol"])] = out.get(str(r["symbol"]), ZERO) + qty
    if _has_table(rows, "eq_orders") and _has_table(rows, "eq_fills"):
        for r in rows("SELECT eid, side, symbol, filled_qty FROM eq_orders WHERE status IN ('pending', 'working', 'unknown')"):
            filled = D(r["filled_qty"], ZERO)
            if filled <= 0:
                continue
            booked = sum((D(f["qty"], ZERO) for f in rows("SELECT qty FROM eq_fills WHERE eid=?", (r["eid"],))), ZERO)
            unbooked = filled - booked
            if unbooked > 0:
                sign = 1 if r["side"] == "buy" else -1
                out[str(r["symbol"])] = out.get(str(r["symbol"]), ZERO) + sign * unbooked
    return {k: v for k, v in out.items() if v != 0}


def working_buys_worst(rows: Callable[..., list]) -> Decimal:
    """Every working equity buy's worst cost: remaining qty x limit (dollars), for the House-wide available cash (A8.1)."""
    if not _has_table(rows, "eq_orders"):
        return ZERO
    total = ZERO
    for r in rows("SELECT qty, filled_qty, limit_px FROM eq_orders WHERE side='buy' "
                  "AND status IN ('pending', 'working', 'unknown')"):
        total += max(ZERO, D(r["qty"], ZERO) - D(r["filled_qty"], ZERO)) * D(r["limit_px"], ZERO)
    return total


def orders_today(rows: Callable[..., list], day: str) -> int:
    """Equity orders sent (or pending) on the New York `day` (ISO), cancels counted as the options book counts its own:
    the shared day order count (A8.3). An order refused before it reached the venue (the House's rate, a gateway cap)
    is not counted."""
    if not _has_table(rows, "eq_orders"):
        return 0
    n = 0
    for r in rows("SELECT status, day, answer FROM eq_orders WHERE day=? OR answer LIKE ?", (day, '%"cancel_day":%')):
        answer = loads(r["answer"], {}) or {}
        if r["day"] == day and r["status"] != "refused":
            n += 1
        if answer.get("cancel_day") == day:
            n += 1
    return n


def invested(rows: Callable[..., list]) -> Decimal:
    """Equity long value (open lots at their mark, entry price when never marked) plus working buys' worst cost
    (dollars): `league.live.money.Exposure.equity_invested`."""
    if not _has_table(rows, "eq_lots"):
        return ZERO
    total = ZERO
    for r in rows("SELECT qty, entry_px, mark FROM eq_lots WHERE status IN ('open', 'closing')"):
        total += max(ZERO, D(r["qty"], ZERO)) * _price(r)
    return total + working_buys_worst(rows)


# ----------------------------------------------------------------------------------------------- the rows as objects
@dataclass
class Lot:
    lid: int
    instance: str
    family: str
    version: int
    lane: str
    symbol: str
    klass: str
    qty: Decimal
    opened_qty: Decimal
    entry_px: Decimal
    entry_notional: Decimal
    entry_at: str
    fees: Decimal = ZERO
    div: Decimal = ZERO
    mark: Decimal | None = None
    marked_at: float | None = None
    opened_at: float = 0.0
    opened_day: str = ""
    status: str = LOT_OPEN
    exit_px: Decimal | None = None
    exit_at: str | None = None
    exit_day: str | None = None
    closed_at: float | None = None
    cash: Decimal = ZERO
    reason: str | None = None
    probe: bool = False
    tag: str = ""
    iid: int | None = None
    info: dict = field(default_factory=dict)

    @property
    def value(self) -> Decimal:
        """Its value at its mark (its entry price while never marked)."""
        px = self.mark if self.mark is not None and self.mark > 0 else self.entry_px
        return max(ZERO, self.qty) * px

    def row(self) -> dict:
        return {"lid": self.lid, "instance": self.instance, "family": self.family, "version": self.version,
                "lane": self.lane, "symbol": self.symbol, "class": self.klass, "qty": text(self.qty),
                "opened_qty": text(self.opened_qty), "entry_px": text(self.entry_px),
                "entry_notional": text(self.entry_notional), "entry_at": self.entry_at, "fees": text(self.fees),
                "div": text(self.div), "mark": None if self.mark is None else text(self.mark), "marked_at": self.marked_at,
                "opened_at": self.opened_at, "opened_day": self.opened_day, "status": self.status,
                "exit_px": None if self.exit_px is None else text(self.exit_px), "exit_at": self.exit_at,
                "exit_day": self.exit_day, "closed_at": self.closed_at, "cash": text(self.cash), "reason": self.reason,
                "probe": int(self.probe), "tag": self.tag, "iid": self.iid, "info": dumps(self.info)}

    @classmethod
    def of(cls, r: Mapping[str, Any]) -> "Lot":
        return cls(int(r["lid"]), r["instance"], r["family"], int(r["version"]), r["lane"], r["symbol"], r["class"],
                   D(r["qty"], ZERO), D(r["opened_qty"], ZERO), D(r["entry_px"], ZERO), D(r["entry_notional"], ZERO),
                   r["entry_at"], D(r["fees"], ZERO), D(r["div"], ZERO), A.dec(r["mark"]), r["marked_at"],
                   float(r["opened_at"]), r["opened_day"], r["status"], A.dec(r["exit_px"]), r["exit_at"], r["exit_day"],
                   r["closed_at"], D(r["cash"], ZERO), r["reason"], bool(r["probe"]), r["tag"] or "", r["iid"],
                   loads(r["info"], {}) or {})


@dataclass
class Order:
    eid: int
    client_id: str
    instance: str
    family: str
    side: str
    symbol: str
    klass: str
    at: str
    qty: Decimal
    limit_px: Decimal
    collar_bp: int
    status: str
    placed_at: float
    day: str
    venue_id: str | None = None
    lid: int | None = None
    iid: int | None = None
    filled_qty: Decimal = ZERO
    avg_px: Decimal | None = None
    fees_est: Decimal = ZERO
    replaces: int | None = None
    probe: bool = False
    why: str = ""
    answer: dict = field(default_factory=dict)
    updated_at: float = 0.0
    attempts: int = 0

    @property
    def working(self) -> bool:
        return self.status in WORKING

    @property
    def remaining(self) -> Decimal:
        return max(ZERO, self.qty - self.filled_qty)

    @property
    def filled_value(self) -> Decimal:
        return self.filled_qty * (self.avg_px or ZERO)

    def row(self) -> dict:
        return {"eid": self.eid, "client_id": self.client_id, "venue_id": self.venue_id, "instance": self.instance,
                "family": self.family, "lid": self.lid, "iid": self.iid, "side": self.side, "symbol": self.symbol,
                "class": self.klass, "at": self.at, "qty": text(self.qty), "limit_px": text(self.limit_px),
                "collar_bp": int(self.collar_bp), "status": self.status, "placed_at": self.placed_at, "day": self.day,
                "filled_qty": text(self.filled_qty), "avg_px": None if self.avg_px is None else text(self.avg_px),
                "fees_est": text(self.fees_est), "replaces": self.replaces, "probe": int(self.probe),
                "why": self.why, "answer": dumps(self.answer), "updated_at": self.updated_at, "attempts": self.attempts}

    @classmethod
    def of(cls, r: Mapping[str, Any]) -> "Order":
        return cls(int(r["eid"]), r["client_id"], r["instance"], r["family"], r["side"], r["symbol"], r["class"],
                   r["at"], D(r["qty"], ZERO), D(r["limit_px"], ZERO), int(r["collar_bp"]), r["status"],
                   float(r["placed_at"]), r["day"], r["venue_id"], r["lid"], r["iid"], D(r["filled_qty"], ZERO),
                   A.dec(r["avg_px"]), D(r["fees_est"], ZERO), r["replaces"], bool(r["probe"]), r["why"] or "",
                   loads(r["answer"], {}) or {}, float(r["updated_at"]), int(r["attempts"] or 0))


@dataclass
class Intent:
    iid: int
    instance: str
    family: str
    version: int
    decided_day: str
    exec_day: str
    at: str
    kind: str
    status: str
    symbol: str | None = None
    lid: int | None = None
    share: Decimal | None = None
    usd: Decimal | None = None
    tag: str = ""
    why: str = ""
    ctx_sha: str | None = None
    bars_sha: str | None = None
    created_at: float = 0.0
    updated_at: float = 0.0

    def row(self) -> dict:
        return {"iid": self.iid, "instance": self.instance, "family": self.family, "version": self.version,
                "decided_day": self.decided_day, "exec_day": self.exec_day, "at": self.at, "kind": self.kind,
                "symbol": self.symbol, "lid": self.lid, "share": None if self.share is None else text(self.share),
                "usd": None if self.usd is None else text(self.usd), "tag": self.tag, "status": self.status,
                "why": self.why[:400], "ctx_sha": self.ctx_sha, "bars_sha": self.bars_sha,
                "created_at": self.created_at, "updated_at": self.updated_at}

    @classmethod
    def of(cls, r: Mapping[str, Any]) -> "Intent":
        return cls(int(r["iid"]), r["instance"], r["family"], int(r["version"]), r["decided_day"], r["exec_day"],
                   r["at"], r["kind"], r["status"], r["symbol"], r["lid"], A.dec(r["share"]), A.dec(r["usd"]),
                   r["tag"] or "", r["why"] or "", r["ctx_sha"], r["bars_sha"], float(r["created_at"]),
                   float(r["updated_at"]))


@dataclass
class Instance:
    id: str
    family: str
    version: int
    lane: str
    run_sha: str
    code: str
    params: dict
    band: str
    seeded: bool
    max_hold: int
    failed_decides: int = 0
    last_decided_day: str | None = None
    created_at: float = 0.0
    retired_at: float | None = None
    why: str = ""

    @property
    def live(self) -> bool:
        return self.retired_at is None and self.band in LIVE_BANDS

    def row(self) -> dict:
        return {"id": self.id, "family": self.family, "version": self.version, "lane": self.lane,
                "run_sha": self.run_sha, "code": self.code, "params": dumps(self.params), "band": self.band,
                "seeded": int(self.seeded), "max_hold": int(self.max_hold), "failed_decides": int(self.failed_decides),
                "last_decided_day": self.last_decided_day, "created_at": self.created_at, "retired_at": self.retired_at,
                "why": self.why[:400]}

    @classmethod
    def of(cls, r: Mapping[str, Any]) -> "Instance":
        return cls(r["id"], r["family"], int(r["version"]), r["lane"], r["run_sha"], r["code"],
                   loads(r["params"], {}) or {}, r["band"], bool(r["seeded"]), int(r["max_hold"]),
                   int(r["failed_decides"] or 0), r["last_decided_day"], float(r["created_at"]), r["retired_at"],
                   r["why"] or "")


def instance_key(family: str, version: int) -> str:
    """`<family>@<version>:r`: the real evidence route's instance, as the options book's."""
    return f"{family}@{int(version)}{REAL_SUFFIX}"


def order_body(order: Order) -> dict[str, Any]:
    """The venue's body: a simple limit day order in shares, never notional, never extended hours (the gateway's
    `stockBuyOrder` and `realStockClose` read exactly these fields)."""
    return {"symbol": order.symbol, "qty": qty_text(order.qty), "side": order.side, "type": "limit",
            "limit_price": text(order.limit_px), "time_in_force": "day", "client_order_id": order.client_id}


def _sha(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _bar_day(row: Mapping[str, Any]) -> str | None:
    stamp = parse_time(row.get("t"))
    return None if stamp is None else S.ny_day(stamp).isoformat()


def _iso(t: float) -> str:
    return dt.datetime.fromtimestamp(float(t), dt.timezone.utc).isoformat()


class EquityBook:
    """The equity book and its order path (the module docstring).

    `state`: the House's `LiveState` (live.sqlite). `account`: the real `Account` (None: a House without real money;
    the book then only keeps its tables). `market`: `MarketData` (snapshots for limits; 1Day bars at 16:20).
    `table`: the money `Table` in force (`table.equity`: the parsed `equity_money`; the shared loss budget's rows).
    `families`: league/equity/families.py `EquityFamilies` (or `MemoryEquityFamilies`). `decider`: the live decider
    (its "equity" kind runs decide). `stock_proof`: `league.live.paper.StockPaperProof` (None: no paper account; then
    no real equity open, ever). `sizing_equity`: the House's `OptionsLive.sizing_equity`. `options_book`: the options
    `RealBook` (its `busy()` symbols, `exit_reserve()`, `count_today()`; None in tests). `clock`, `record`, `alert` as
    the options book's."""

    def __init__(self, state: Any, account: Any, market: Any, table: Any, families: Any, *, decider: Any,
                 stock_proof: Any = None, sizing_equity: Callable[[], Decimal | None] | None = None,
                 options_book: Any = None, root: str | Path | None = None, clock: Callable[[], float] | None = None,
                 record: Callable[..., Any] | None = None, alert: Callable[[str, str], Any] | None = None):
        self.state, self.account, self.market, self.table, self.families = state, account, market, table, families
        self.decider, self.stock_proof, self.options_book = decider, stock_proof, options_book
        self.sizing_equity = sizing_equity or (lambda: None)
        self.root = Path(root) if root is not None else None
        self.clock = clock or time.time
        self._record, self._alert = record, alert
        with self.state.lock:
            for statement in SCHEMA.split(";"):
                if statement.strip():
                    self.state.execute(statement)
        #: instance -> (code sha, params) loaded in the decider child this process; its NEEDS as the child read them.
        self._loaded: dict[str, tuple[str, str]] = {}
        self._needs: dict[str, dict[str, Any]] = {}
        #: The 16:20 bars kept for the 16:30 decide: {"day", "symbols", "raw", "all", "start", "fetched_at"}.
        self._bars: dict[str, Any] | None = None
        self._activities_at = float("-inf")
        self._watch_at = float("-inf")
        self._phase = "closed"
        self._last: dict[str, Any] = {}
        # Per minute: the readings the book made itself (`_tick_reset`).
        self._account_now: Mapping[str, Any] | None = None
        self._positions_now: list[dict] | None = None
        self._open_now: list[dict] | None = None
        self._quotes: dict[str, dict] = {}
        self._minute_positions: Sequence[Mapping[str, Any]] | None = None
        self._minute_open: Sequence[Mapping[str, Any]] | None = None
        recon = self.state.get("eq_recon", {}) or {}
        self._streak = {"bad": int(recon.get("bad") or 0), "good": int(recon.get("good") or 0)}

    # ------------------------------------------------------------------ plumbing
    def record(self, kind: str, payload: Mapping[str, Any], agent: str | None = None) -> None:
        if self._record is None:
            try:
                self.state.event(kind, payload)
            except Exception:  # noqa: BLE001
                pass
            return
        try:
            self._record(kind, dict(payload), agent)
        except Exception:  # noqa: BLE001 - the ledger's trouble never stops trading
            pass

    def alert(self, level: str, message: str) -> None:
        if self._alert is not None:
            try:
                self._alert(level, message)
            except Exception:  # noqa: BLE001
                pass

    def _error(self, where: str, exc: BaseException, out: dict) -> None:
        out.setdefault("errors", []).append(f"{where}: {type(exc).__name__}: {str(exc)[:160]}")
        try:
            self.state.event("equity.error", {"where": where, "error": f"{type(exc).__name__}: {exc}",
                                              "trace": traceback.format_exc()[-2000:]})
        except Exception:  # noqa: BLE001
            pass

    def _et(self) -> Any:
        return getattr(self.table, "equity", None)

    def _offsets(self) -> dict[str, int]:
        et = self._et()
        return S.offsets_of(getattr(et, "offsets", None) if et is not None else None)

    def _holds(self) -> tuple[int, int, int, int]:
        """(min hold, default max hold, the lane's max hold cap, failed decides that exit) in force."""
        et = self._et()
        if et is None:
            return (config.MIN_HOLD_SESSIONS, config.DEFAULT_MAX_HOLD, config.MAX_HOLD_CAP, config.FAILED_DECIDES_EXIT)
        return (max(1, int(et.min_hold_sessions)), int(et.default_max_hold_sessions),
                min(config.MAX_HOLD_CAP, int(et.max_hold_sessions)), max(1, int(et.failed_decides_exit)))

    def _collars(self, klass: str) -> tuple[int, int]:
        et = self._et()
        entry = getattr(et, "entry_collar_bp", None) or DEFAULT_COLLARS["entry"]
        top = getattr(et, "max_collar_bp", None) or DEFAULT_COLLARS["max"]
        return (int(entry.get(klass, DEFAULT_COLLARS["entry"].get(klass, 25))),
                int(top.get(klass, DEFAULT_COLLARS["max"].get(klass, 100))))

    def _class_of(self, symbol: str) -> str | None:
        et = self._et()
        universe = getattr(et, "universe", None) if et is not None else None
        if universe:
            return universe.get(symbol)
        return config.UNIVERSE.get(symbol)

    def _next(self, table: str, column: str) -> int:
        row = self.state.rows(f"SELECT COALESCE(MAX({column}), 0) AS top FROM {table}")
        return int(row[0]["top"]) + 1

    # ------------------------------------------------------------------ rows
    def _save_lot(self, lot: Lot) -> None:
        self.state.upsert("eq_lots", lot.row(), "lid")

    def _save_order(self, order: Order) -> None:
        order.updated_at = self.clock()
        self.state.upsert("eq_orders", order.row(), "eid")

    def _save_intent(self, intent: Intent) -> None:
        intent.updated_at = self.clock()
        self.state.upsert("eq_intents", intent.row(), "iid")

    def _save_instance(self, inst: Instance) -> None:
        self.state.upsert("eq_instances", inst.row(), "id")

    def _lot(self, lid: Any) -> Lot | None:
        if lid is None:
            return None
        rows = self.state.rows("SELECT * FROM eq_lots WHERE lid=?", (int(lid),))
        return Lot.of(rows[0]) if rows else None

    def _lots(self, *, instance: str | None = None, symbol: str | None = None, open_only: bool = True) -> list[Lot]:
        sql, args = "SELECT * FROM eq_lots WHERE 1=1", []
        if open_only:
            sql += " AND status IN ('open', 'closing')"
        if instance is not None:
            sql += " AND instance=?"
            args.append(instance)
        if symbol is not None:
            sql += " AND symbol=?"
            args.append(symbol)
        return [Lot.of(r) for r in self.state.rows(sql + " ORDER BY lid", args)]

    def _orders(self, statuses: Sequence[str] = WORKING) -> list[Order]:
        names = list(statuses)
        return [Order.of(r) for r in self.state.rows(
            f"SELECT * FROM eq_orders WHERE status IN ({','.join('?' * len(names))}) ORDER BY eid", names)]

    def _intent_orders(self, iid: int) -> list[Order]:
        return [Order.of(r) for r in self.state.rows("SELECT * FROM eq_orders WHERE iid=? ORDER BY eid", (int(iid),))]

    def _intent(self, iid: Any) -> Intent | None:
        if iid is None:
            return None
        rows = self.state.rows("SELECT * FROM eq_intents WHERE iid=?", (int(iid),))
        return Intent.of(rows[0]) if rows else None

    def _instance(self, key: str) -> Instance | None:
        rows = self.state.rows("SELECT * FROM eq_instances WHERE id=?", (key,))
        return Instance.of(rows[0]) if rows else None

    def _instances(self, *, alive: bool | None = None) -> list[Instance]:
        out = [Instance.of(r) for r in self.state.rows("SELECT * FROM eq_instances ORDER BY id")]
        if alive is None:
            return out
        return [i for i in out if (i.retired_at is None) == alive]

    # ------------------------------------------------------------------ what the hooks read
    @property
    def frozen(self) -> str:
        """Why equity entries are frozen by reconciliation or an unexplained corporate action ("" none)."""
        recon = str((self.state.get("eq_recon", {}) or {}).get("frozen") or "")
        action = str((self.state.get("eq_freeze", {}) or {}).get("why") or "")
        return "; ".join(x for x in (recon, action) if x)

    def expected_shares(self) -> dict[str, Decimal]:
        """{symbol: shares} this book owns now (`expected_shares_rows` over its state)."""
        return expected_shares_rows(self.state.rows)

    def busy(self) -> set[str]:
        """Symbols with a working equity order (one working order a symbol across both books)."""
        return {str(r["symbol"]) for r in self.state.rows(
            "SELECT DISTINCT symbol FROM eq_orders WHERE status IN ('pending', 'working', 'unknown')")}

    def health(self) -> dict[str, Any]:
        """The book's line for health.json and the site: {enabled, frozen, lots, working, orders_today, phase,
        proof, programs: [...], last_decide, last_bars}."""
        et = self._et()
        lots = self.state.rows("SELECT instance, COUNT(*) AS n FROM eq_lots WHERE status IN ('open', 'closing') "
                               "GROUP BY instance")
        held = {r["instance"]: int(r["n"]) for r in lots}
        proof = None
        if self.stock_proof is not None:
            try:
                proof = self.stock_proof.status()
            except Exception as exc:  # noqa: BLE001
                proof = {"error": type(exc).__name__}
        return {"enabled": bool(getattr(et, "enabled", False)), "table": et is not None, "frozen": self.frozen,
                "lots": sum(held.values()), "working": len(self._orders()),
                "orders_today": orders_today(self.state.rows, S.ny_day(self.clock()).isoformat()), "phase": self._phase,
                "proof": proof,
                "programs": [{"instance": i.id, "family": i.family, "version": i.version, "lane": i.lane,
                              "band": i.band, "seeded": i.seeded, "failed_decides": i.failed_decides,
                              "last_decided_day": i.last_decided_day, "lots": held.get(i.id, 0),
                              "retired": i.retired_at is not None, "why": i.why or None}
                             for i in self._instances() if i.retired_at is None or held.get(i.id)],
                "last_decide": self.state.get("eq_decide"), "last_bars": (self.state.get("eq_decision") or {}).get("day"),
                "recon": {k: v for k, v in (self.state.get("eq_recon", {}) or {}).items() if k != "problems"},
                "freeze": self.state.get("eq_freeze")}

    def flatten(self, why: str) -> int:
        """The rollback's first step (docs/operations.md): every open lot queued to exit at the next window through the
        normal path; returns the lots queued. Never a market order."""
        now = self.clock()
        today = S.ny_day(now)
        m = S.moments(today, self._offsets())
        if m is not None and now < m.close_until:
            exec_day, at = today, ("open" if now < m.close_send else "close")
        else:
            exec_day, at = S.next_session(today), "open"
        n = 0
        with self.state.transaction():
            for lot in self._lots():
                if self._exit_pending(lot.lid):
                    continue
                self._plan_exit(lot, exec_day=exec_day.isoformat(), at=at, reason="flatten",
                                why=f"flatten: {why}"[:300], decided_day=today.isoformat())
                n += 1
        self.record("equity.flatten", {"why": why[:300], "lots": n})
        return n

    # ------------------------------------------------------------------ the minute
    def tick(self, now: float, *, account_row: Mapping[str, Any] | None, positions: Sequence[Mapping[str, Any]] | None,
             open_orders: Sequence[Mapping[str, Any]] | None, real_block: Callable[..., str | None],
             killed: Callable[[], bool]) -> dict[str, Any]:
        """THE ONE ENTRY a minute (league/live/step.py): whatever `schedule.phase(now)` says is due (bars, decide,
        pre-open, the open window, the close window, the morning audit, reconciliation, activities, exports). The
        minute's own reads are passed when the options path made them (None: not read this minute; the book reads
        what it needs itself, within the Account's rate). `real_block(opening=True)`: why no real open may go now
        (None: it may); `killed()`: the gateway's kill switch (exits wait only on it: the gateway's kill blocks sells
        too). Never raises: an error is recorded and the next minute tries again. Returns a summary for the minute's
        `out["equity"]`."""
        out: dict[str, Any] = {}
        if self.account is None:
            return {"state": "no real account"}
        try:
            now = float(now)
            self._tick_reset(account_row, positions, open_orders)
            try:
                self._phase, _ = S.phase(now, self._offsets())
            except Exception:  # noqa: BLE001
                self._phase = "closed"
            out["phase"] = self._phase
            today = S.ny_day(now)
            m = S.moments(today, self._offsets())
            steps: list[tuple[str, Callable[[], Any]]] = [
                ("orders", lambda: self._sync_orders(now, out)),
                ("activities", lambda: self._activities(now, m, out)),
                ("reconcile", lambda: self._reconcile_step(now, m, out)),
                ("audit", lambda: self._audit(now, m, out)),
                ("decide", lambda: self._decide_step(now, out)),
                ("windows", lambda: self._windows(now, m, out, real_block, killed)),
                ("exports", lambda: self._export(out)),
                ("proof", lambda: self._proof_step(now, out)),
            ]
            for name, work in steps:
                try:
                    work()
                except Exception as exc:  # noqa: BLE001 - never the minute's end
                    self._error(name, exc, out)
            out["frozen"] = self.frozen or None
            out["working"] = len(self._orders())
        except Exception as exc:  # noqa: BLE001
            self._error("tick", exc, out)
        self._last = out
        return out

    def _tick_reset(self, account_row: Mapping[str, Any] | None, positions: Sequence[Mapping[str, Any]] | None,
                    open_orders: Sequence[Mapping[str, Any]] | None) -> None:
        self._account_now = None
        self._positions_now = None
        self._open_now = None
        self._quotes = {}
        self._minute_positions = positions
        self._minute_open = open_orders

    def _read_positions(self) -> list[dict] | None:
        """The account's positions this minute (the options path's reading, else one of the book's own); None when
        they cannot be read."""
        if self._positions_now is None:
            if self._minute_positions is not None:
                self._positions_now = [dict(r) for r in self._minute_positions]
            else:
                try:
                    self._positions_now = [dict(r) for r in self.account.positions()]
                except Exception:  # noqa: BLE001
                    return None
        return self._positions_now

    def _read_account(self) -> Mapping[str, Any] | None:
        """A fresh account reading (once a minute): what the entries are sized on."""
        if self._account_now is None:
            try:
                self._account_now = self.account.account()
            except Exception:  # noqa: BLE001
                return None
        return self._account_now

    def _venue_open(self) -> list[dict] | None:
        """The venue's working orders this minute; None when they cannot be read."""
        if self._open_now is None:
            if self._minute_open is not None:
                self._open_now = [dict(r) for r in self._minute_open]
            else:
                try:
                    self._open_now = [dict(r) for r in self.account.orders(status="open")]
                except Exception:  # noqa: BLE001
                    return None
        return self._open_now

    # ------------------------------------------------------------------ the venue's orders
    def _sync_orders(self, now: float, out: dict) -> None:
        """Bring every working order up to the venue's row (fills booked to lots), revive a lost order the venue shows
        after all, and look up the unknown ones by client id."""
        working = self._orders(WORKING)
        lost = self._orders(("lost",))
        lost = [o for o in lost if o.day >= (S.ny_day(now) - dt.timedelta(days=3)).isoformat()]
        if not working and not lost:
            return
        shown: set[str] = set()
        try:
            after = min(o.placed_at for o in working + lost) - 120.0
            rows = self.account.orders(status="all", after=_iso(after))
        except Exception as exc:  # noqa: BLE001 - looked up by client id below
            rows = None
            out.setdefault("venue_errors", []).append(f"orders: {type(exc).__name__}: {str(exc)[:120]}")
        if rows is not None:
            by_client = {str(r.get("client_order_id") or ""): r for r in rows
                         if str(r.get("client_order_id") or "").startswith(CLIENT_PREFIX)}
            shown = set(by_client)
            for order in working:
                row = by_client.get(order.client_id)
                if row is not None:
                    self._absorb(order, row)
            for order in lost:
                row = by_client.get(order.client_id)
                if row is not None:
                    order.status = "working"
                    order.answer = {**order.answer, "found": self.clock()}
                    self.record("equity.order", {"eid": order.eid, "family": order.family, "status": "found"},
                                agent=order.family)
                    self.alert("warning", f"equity: order {order.client_id}, given up as lost, is at the venue after all")
                    self._absorb(order, row)
        self._look_up(now, shown)

    def _look_up(self, now: float, shown: set[str]) -> None:
        candidates = [o for o in self._orders(WORKING) if o.status in ("unknown", "pending")]
        candidates += [o for o in self._orders(("working",)) if o.client_id not in shown and now - o.placed_at > 60]
        for order in candidates[:LOOKUP_LIMIT]:
            if order.status == "pending" and now - order.placed_at < PENDING_GRACE_S:
                continue
            try:
                row = self.account.order_by_client_id(order.client_id)
            except Exception as exc:  # noqa: BLE001 - asked again next minute
                order.answer = {**order.answer, "lookup_error": str(exc)[:200]}
                self._save_order(order)
                continue
            if row is None:
                order.attempts += 1
                if order.attempts >= LOST_AFTER_TRIES or now - order.placed_at > LOST_AFTER_S:
                    order.status = "lost"
                    order.answer = {**order.answer, "lookup": "not found at the venue by its client id"}
                    self.record("equity.order", {"eid": order.eid, "family": order.family, "status": "lost"},
                                agent=order.family)
                    self.alert("warning", f"equity: order {order.client_id} is not at the venue by its client id: lost")
                self._save_order(order)
            else:
                self._absorb(order, row)

    def _absorb(self, order: Order, row: Mapping[str, Any]) -> None:
        """One order brought up to the venue's row: its new fills booked to the lot (in one transaction with its
        progress, so a crash cannot book a fill twice), its status carried."""
        order.venue_id = str(row.get("id") or order.venue_id or "") or order.venue_id
        status = str(row.get("status") or "")
        filled = A.dec(row.get("filled_qty")) or ZERO
        avg = A.dec(row.get("filled_avg_price"))
        stamps = {k: row.get(k) for k in ("submitted_at", "filled_at", "canceled_at", "expired_at", "failed_at")
                  if isinstance(row.get(k), str) and row.get(k) and order.answer.get(k) != row.get(k)}
        if stamps:
            order.answer = {**order.answer, **stamps}
        if filled > order.filled_qty:
            if avg is None or avg <= 0:
                order.status = "working"   # filled at the venue, its price not readable yet: booked next reading
                self._save_order(order)
                return
            dq = filled - order.filled_qty
            px = ((avg * filled - order.filled_value) / dq).quantize(PRICE_PLACES)
            if px <= 0:
                px = avg
            with self.state.transaction():
                self._book_fill(order, dq, px)
                order.filled_qty, order.avg_px = filled, avg
                self._save_order(order)
        if status in VENUE_TERMINAL:
            final = {"filled": "filled", "canceled": "canceled", "replaced": "canceled", "stopped": "canceled",
                     "suspended": "canceled", "expired": "expired", "done_for_day": "expired",
                     "rejected": "rejected"}[status]
            if final == "filled" and order.filled_qty < order.qty:
                order.status = "working"   # the venue says filled; its quantity has not said so yet
            else:
                order.status = final
                order.answer = {**order.answer, "final": status,
                                "reject_reason": str(row.get("reject_reason") or "")[:200] if status == "rejected" else None}
        elif status:
            order.status = "working"
        self._save_order(order)

    def _book_fill(self, order: Order, dq: Decimal, px: Decimal) -> None:
        now = self.clock()
        intent = self._intent(order.iid)
        if order.side == "buy":
            lid = order.lid if order.lid is not None else (intent.lid if intent is not None else None)
            lot = self._lot(lid)
            if lot is None:
                inst = self._instance(order.instance)
                lot = Lot(self._next("eq_lots", "lid"), order.instance, order.family,
                          inst.version if inst else _version_of(order.instance), inst.lane if inst else "",
                          order.symbol, order.klass, qty=dq, opened_qty=dq, entry_px=px, entry_notional=dq * px,
                          entry_at=order.at, opened_at=now, opened_day=order.day, status=LOT_OPEN, cash=-(dq * px),
                          probe=order.probe, tag=(intent.tag if intent else "")[:120], iid=order.iid)
                if intent is not None:
                    intent.lid = lot.lid
                    self._save_intent(intent)
            else:
                lot.qty += dq
                lot.opened_qty += dq
                lot.entry_notional += dq * px
                lot.entry_px = (lot.entry_notional / lot.opened_qty).quantize(PRICE_PLACES)
                lot.cash -= dq * px
            order.lid = lot.lid
            self._save_lot(lot)
            fees = ZERO
        else:
            lot = self._lot(order.lid)
            if lot is None:
                self.record("equity.alert", {"what": "a sale filled for a lot the book does not hold", "eid": order.eid},
                            agent=order.family)
                self.alert("error", f"equity: order {order.client_id} sold {dq} {order.symbol} for no lot of the book")
                return
            dq = min(dq, lot.qty)
            proceeds = dq * px
            fees = config.sell_fees(proceeds, dq)
            lot.qty -= dq
            lot.cash += proceeds - fees
            lot.fees += fees
            lot.info["exit_qty"] = text(D(lot.info.get("exit_qty"), ZERO) + dq)
            lot.info["exit_notional"] = text(D(lot.info.get("exit_notional"), ZERO) + proceeds)
            order.fees_est += fees
            if lot.qty <= SHARE_TOLERANCE:
                lot.qty = ZERO
                exit_qty = D(lot.info["exit_qty"])
                lot.status, lot.closed_at = LOT_CLOSED, now
                lot.exit_px = (D(lot.info["exit_notional"]) / exit_qty).quantize(PRICE_PLACES) if exit_qty > 0 else px
                lot.exit_at, lot.exit_day = order.at, order.day
                lot.reason = "program" if intent is None or intent.kind == "sell" else (intent.tag or "house")
                if intent is not None and intent.status in INTENT_LIVE:
                    intent.status, intent.why = "done", "the lot is sold"
                    self._save_intent(intent)
            else:
                lot.status = LOT_CLOSING
            self._save_lot(lot)
        self.state.execute("INSERT INTO eq_fills(eid, lid, venue_fill_id, qty, px, fees, at) VALUES(?,?,?,?,?,?,?)",
                           (order.eid, order.lid, None, text(dq), text(px), text(fees), now))
        self.record("equity.fill", {"eid": order.eid, "lid": order.lid, "family": order.family, "side": order.side,
                                    "symbol": order.symbol, "qty": text(dq), "_px": text(px), "fees": text(fees),
                                    "at": order.at, "real_money": True}, agent=order.family)
        if order.side == "sell" and lot.status == LOT_CLOSED:
            self.record("equity.close", {"lid": lot.lid, "family": lot.family, "instance": lot.instance,
                                         "symbol": lot.symbol, "cash": text(lot.cash), "reason": lot.reason},
                        agent=lot.family)

    # ------------------------------------------------------------------ sending
    def _send(self, intent: Intent, *, side: str, symbol: str, klass: str, qty: Decimal, limit: Decimal, collar: int,
              day: str, lid: int | None, replaces: int | None, probe: bool, why: str) -> Order:
        """Write the order `pending` (the intent `sent`, a sold lot `closing`) BEFORE the POST; then POST it once."""
        now = self.clock()
        exit_ = side == "sell"
        with self.state.transaction():
            eid = self._next("eq_orders", "eid")
            order = Order(eid, client_id(eid, intent.family, nonce=getattr(self.state, "nonce", "")), intent.instance,
                          intent.family, side, symbol, klass, intent.at, qty, limit, int(collar), "pending", now, day,
                          lid=lid, iid=intent.iid, replaces=replaces, probe=probe, why=why[:300])
            if exit_:
                try:
                    order.fees_est = config.sell_fees(qty * limit, qty)
                except Exception:  # noqa: BLE001 - an estimate only: the fill books the fees
                    order.fees_est = ZERO
            self._save_order(order)
            intent.status = "sent"
            self._save_intent(intent)
            if exit_ and lid is not None:
                lot = self._lot(lid)
                if lot is not None and lot.status == LOT_OPEN:
                    lot.status = LOT_CLOSING
                    self._save_lot(lot)
        try:
            result = self.account.submit(order_body(order), exit=exit_)
        except Exception as exc:  # noqa: BLE001 - it may have reached the venue: unknown, looked up by its client id
            result = None
            order.status, order.answer = "unknown", {"error": f"{type(exc).__name__}: {str(exc)[:200]}"}
        order.attempts += 1
        if result is not None:
            if result.ok:
                order.venue_id = str(result.order.get("id"))
                order.status = "working"
                order.answer = {"status": result.order.get("status"), "at": self.clock()}
            elif result.unknown:
                order.status, order.answer = "unknown", {"error": result.error}
            elif not result.sent:
                order.status, order.answer = "refused", {"error": result.error, "house": True}
            else:
                # A gateway refusal says {"error": ...} and never reached the venue; the venue's own answer carries its
                # "message" (and "code"): that one did.
                payload = result.order or {}
                gateway = "error" in payload and "code" not in payload
                order.status = "refused" if gateway else "rejected"
                order.answer = {"error": result.error, "status": result.status, "gateway": gateway,
                                "cap": payload.get("cap")}
        self._save_order(order)
        if result is not None and result.ok:
            self._absorb(order, result.order)
        self.record("equity.order", {"eid": order.eid, "client_id": order.client_id, "family": order.family,
                                     "instance": order.instance, "side": side, "symbol": symbol, "at": order.at,
                                     "qty": qty_text(qty), "_limit": text(limit), "collar_bp": collar,
                                     "status": order.status, "replaces": replaces, "why": why[:200],
                                     "_answer": order.answer, "real_money": True}, agent=order.family)
        return order

    def _cancel(self, order: Order, why: str, now: float) -> None:
        """Cancel a working order (always sent: a cancel takes risk off), then look it up once, so its replacement can
        go this minute when it is already terminal."""
        if not order.working or not order.venue_id:
            return
        sent = order.answer.get("cancel_sent")
        if sent is not None and now - float(sent) < CANCEL_AGAIN_S:
            return
        with self.state.transaction():
            order.answer = {**order.answer, "cancel_sent": now, "cancel_day": S.ny_day(now).isoformat(),
                            "cancel": why[:200]}
            self._save_order(order)
        try:
            done, error = self.account.cancel(order.venue_id)
        except Exception as exc:  # noqa: BLE001
            done, error = False, f"{type(exc).__name__}: {str(exc)[:160]}"
        order.answer = {**order.answer, "cancel_error": error or None}
        self._save_order(order)
        self.record("equity.cancel", {"eid": order.eid, "family": order.family, "why": why[:200], "ok": done,
                                      "_error": error}, agent=order.family)
        try:
            row = self.account.order_by_client_id(order.client_id)
        except Exception:  # noqa: BLE001 - the next minute's reading says
            row = None
        if row is not None:
            self._absorb(order, row)

    # ------------------------------------------------------------------ the rules of a send
    def _symbol_busy(self, symbol: str) -> str | None:
        """Why no new order may go on `symbol` now (one working order a symbol across both books), or None."""
        if symbol in self.busy():
            return f"one order a symbol: an equity order on {symbol} is working"
        if self.options_book is not None:
            try:
                if symbol in set(self.options_book.busy()):
                    return f"one order a symbol: the options book has a working order on {symbol}"
            except Exception:  # noqa: BLE001
                return "the options book's working orders could not be read"
        rows = self._venue_open()
        if rows is None:
            return "the venue's working orders could not be read"
        mine = {str(r["client_id"]) for r in self.state.rows("SELECT client_id FROM eq_orders")}
        for r in rows:
            if str(r.get("symbol") or "").upper() == symbol and str(r.get("client_order_id") or "") not in mine \
                    and str(r.get("status") or "") in VENUE_WORKING:
                return f"one order a symbol: a working order on {symbol} that is not the equity book's"
        return None

    def _count_refusal(self, day: str, *, exit_: bool) -> str | None:
        """THE ONE DAY ORDER COUNT (A8.3): None when one more order (and its cancel) fits."""
        et = self._et()
        cap = int(getattr(et, "max_orders_day", 60) if et is not None else 60)
        mine = orders_today(self.state.rows, day)
        reserve = 0 if exit_ else 2 * len(self._lots())
        if mine + 1 + reserve > cap:
            return (f"the equity day's order count: {mine} of {cap} sent" +
                    ("" if exit_ else f", {reserve} kept for exiting the lots held"))
        if self.options_book is not None:
            try:
                house = int(self.options_book.count_today(day)) + mine
                room = int(self.table.max_orders_day) - house - int(self.options_book.exit_reserve())
            except Exception:  # noqa: BLE001
                return "the House's day order count could not be read"
            if room < 1:
                return (f"the House's day order count: {house} sent of {self.table.max_orders_day}, the rest kept for "
                        "the options book's exits")
        return None

    def _open_block(self, real_block: Callable[..., str | None], inst: Instance | None,
                    killed: Callable[[], bool] | None = None) -> str | None:
        """Why no real equity OPEN may go now (the module docstring's gates), or None."""
        try:
            why = real_block(opening=True)
        except Exception as exc:  # noqa: BLE001 - fail closed
            why = f"the House's real-money block could not be read ({type(exc).__name__})"
        if why:
            return why
        try:
            if killed is not None and killed():
                return "the gateway's kill switch is engaged"
        except Exception:  # noqa: BLE001 - unreadable counts as engaged
            return "the gateway's kill switch could not be read"
        et = self._et()
        if et is None:
            return "the equity money table (equity_money) cannot be read"
        if not et.enabled:
            return "equity_money.enabled is false: exits only"
        if self.stock_proof is None:
            return "no stock paper proof: no paper account"
        try:
            if not self.stock_proof.passed():
                return "the stock paper proof (paper_proof_stock) has not passed"
        except Exception as exc:  # noqa: BLE001
            return f"the stock paper proof could not be read ({type(exc).__name__})"
        frozen = self.frozen
        if frozen:
            return f"equity reconciliation: {frozen}"
        if inst is None or not inst.live:
            return "the program is not at Probe or Sized"
        return None

    def _quote(self, symbol: str) -> dict[str, Any]:
        if symbol not in self._quotes:
            try:
                rows = self.market.stocks([symbol]) or {}
            except Exception as exc:  # noqa: BLE001
                rows = {}
                self._quotes[symbol] = {"error": f"{type(exc).__name__}"}
                return self._quotes[symbol]
            row = rows.get(symbol) or {}
            quote = row.get("latestQuote") or {}
            trade = row.get("latestTrade") or {}
            self._quotes[symbol] = {"bid": A.dec(quote.get("bp")), "ask": A.dec(quote.get("ap")),
                                    "t": parse_time(quote.get("t")), "trade": A.dec(trade.get("p")),
                                    "trade_t": parse_time(trade.get("t"))}
        return self._quotes[symbol]

    # ------------------------------------------------------------------ the windows
    def _windows(self, now: float, m: S.Moments | None, out: dict, real_block: Callable[..., str | None],
                 killed: Callable[[], bool]) -> None:
        if m is None or now < m.open_send:
            return
        today = m.day.isoformat()
        rows = self.state.rows("SELECT * FROM eq_intents WHERE status IN ('planned', 'sent') AND exec_day<=? "
                               "ORDER BY iid", (today,))
        intents = [Intent.of(r) for r in rows]
        for intent in intents:
            if intent.kind == "buy" and intent.exec_day < today:
                orders = self._intent_orders(intent.iid)
                if any(o.working for o in orders):
                    continue    # the venue ended it at its session's close; the next reading says how
                filled = sum((o.filled_qty for o in orders), ZERO)
                self._finish(intent, "done" if filled > 0 else "missed",
                             f"filled {qty_text(filled)} shares in its session" if filled > 0
                             else "its session passed before the House could send it")
        exits = [i for i in intents if i.kind in EXIT_KINDS]
        for intent in sorted(exits, key=lambda i: (i.at != "open", i.iid)):
            if intent.at == "close" and now < m.close_send:
                continue
            try:
                self._work_exit(intent, now, m, killed, out)
            except Exception as exc:  # noqa: BLE001
                self._error(f"exit {intent.iid}", exc, out)
        off = self._offsets()
        open_exits = self.state.rows("SELECT iid FROM eq_intents WHERE status IN ('planned', 'sent') AND exec_day<=? "
                                     "AND at='open' AND kind IN ('sell', 'house_exit') AND lid IN "
                                     "(SELECT lid FROM eq_lots WHERE opened_day<?)", (today, today))
        entries = [i for i in intents if i.kind == "buy" and i.exec_day == today]
        if entries:
            out["entries"] = len(entries)
        if not open_exits or now >= m.open_send + off["exit_wait_s"]:
            for intent in entries:
                if intent.at != "open":
                    continue
                try:
                    self._work_entry(intent, now, m, deadline=m.entry_until, reprice=off["open_reprice_s"],
                                     real_block=real_block, killed=killed, out=out)
                except Exception as exc:  # noqa: BLE001
                    self._error(f"entry {intent.iid}", exc, out)
        if now >= m.close_send:
            for intent in entries:
                if intent.at != "close":
                    continue
                try:
                    self._work_entry(intent, now, m, deadline=m.close_until, reprice=off["close_reprice_s"],
                                     real_block=real_block, killed=killed, out=out)
                except Exception as exc:  # noqa: BLE001
                    self._error(f"entry {intent.iid}", exc, out)

    def _finish(self, intent: Intent, status: str, why: str) -> None:
        intent.status, intent.why = status, why[:400]
        self._save_intent(intent)
        self.record("equity.intent", {"iid": intent.iid, "instance": intent.instance, "kind": intent.kind,
                                      "symbol": intent.symbol, "at": intent.at, "status": status, "why": why[:300]},
                    agent=intent.family)

    def _work_exit(self, intent: Intent, now: float, m: S.Moments, killed: Callable[[], bool], out: dict) -> None:
        today = m.day.isoformat()
        lot = self._lot(intent.lid)
        if lot is None or lot.status == LOT_CLOSED or lot.qty <= 0:
            self._finish(intent, "done", "the lot is sold")
            return
        off = self._offsets()
        orders = self._intent_orders(intent.iid)
        current = orders[-1] if orders else None
        in_close = now >= m.close_send
        reprice = off["close_reprice_s"] if in_close else off["open_reprice_s"]
        if current is not None and current.working:
            if now >= m.close_until:
                self._cancel(current, "the close window ended", now)
            elif self._reprice_due(current, now, reprice, m):
                self._cancel(current, "re-priced: cancel, then resend once it is terminal", now)
            current = Order.of(self.state.rows("SELECT * FROM eq_orders WHERE eid=?", (current.eid,))[0])
            if current.working:
                return
            lot = self._lot(intent.lid)
            if lot is None or lot.status == LOT_CLOSED or lot.qty <= 0:
                self._finish(intent, "done", "the lot is sold")
                return
        if now >= m.close_until:
            self._carry(intent, lot, today, "the session's windows ended with the lot still held")
            return
        if lot.opened_day >= today:
            if intent.why != "min hold":
                intent.why = "min hold"
                self._save_intent(intent)
            return
        try:
            stopped = bool(killed())
        except Exception:  # noqa: BLE001 - unreadable counts as engaged
            stopped = True
        if stopped:
            intent.why = "the gateway's kill switch is engaged (it blocks sells too)"
            self._save_intent(intent)
            return
        refused = [o for o in orders if o.day == today and o.status in ("rejected", "refused")
                   and not o.answer.get("house")]
        if len(refused) >= MAX_EXIT_REFUSALS:
            self.alert("error", f"equity: the exit of lot {lot.lid} ({lot.symbol}) was refused {len(refused)} times today; "
                                "carried to the next session")
            self._carry(intent, lot, today, f"refused {len(refused)} times: {refused[-1].answer.get('error')}")
            return
        why = self._symbol_busy(lot.symbol) or self._count_refusal(today, exit_=True)
        if why:
            intent.why = why
            self._save_intent(intent)
            return
        quote = self._quote(lot.symbol)
        bid = quote.get("bid")
        fresh = quote.get("t") is not None and quote["t"] >= m.open_at
        if bid is None or bid <= 0 or not fresh:
            trade = quote.get("trade")
            if trade is not None and trade > 0 and (quote.get("trade_t") or 0) >= m.open_at:
                bid = trade
            else:
                intent.why = f"no usable bid for {lot.symbol} this minute"
                self._save_intent(intent)
                return
        entry_bp, max_bp = self._collars(lot.klass)
        attempt = sum(1 for o in orders if o.day == today)
        late = intent.at == "open" and now >= m.exit_until
        collar = max_bp if late else collar_for(attempt, entry_bp, max_bp)
        limit = limit_for("sell", bid, collar)
        reason = "program" if intent.kind == "sell" else (intent.tag or "house")
        self._send(intent, side="sell", symbol=lot.symbol, klass=lot.klass, qty=lot.qty, limit=limit, collar=collar,
                   day=today, lid=lot.lid, replaces=current.eid if current is not None else None, probe=lot.probe,
                   why=f"exit ({reason}){' at the bid, late' if late else ''}")

    def _reprice_due(self, order: Order, now: float, reprice: float, m: S.Moments) -> bool:
        """Whether a working order is re-priced now: once it is `reprice` seconds old, while its collar can still widen;
        at the widest collar only when the quote has moved through its limit (a marketable order that does not fill is
        not helped by another, and each re-price costs two of the day's orders, A8.3)."""
        if order.status != "working" or now - order.placed_at < reprice:
            return False
        if order.collar_bp < self._collars(order.klass)[1]:
            return True
        quote = self._quote(order.symbol)
        if quote.get("t") is None or quote["t"] < m.open_at:
            return False
        if order.side == "buy":
            return quote.get("ask") is not None and quote["ask"] > order.limit_px
        return quote.get("bid") is not None and quote["bid"] < order.limit_px

    def _carry(self, intent: Intent, lot: Lot, today: str, why: str) -> None:
        """An exit the session could not fill: recorded missed, and planned again at the next session's open."""
        nxt = S.next_session(today).isoformat()
        reason = "program" if intent.kind == "sell" else (intent.tag or "house")
        with self.state.transaction():
            self._finish(intent, "missed", why)
            self._plan_exit(lot, exec_day=nxt, at="open", reason=reason, why=f"carried from {today}: {why}"[:300],
                            decided_day=intent.decided_day, instance=intent.instance, family=intent.family,
                            version=intent.version)
        self.record("equity.carried", {"lid": lot.lid, "family": lot.family, "to": nxt, "why": why[:200]},
                    agent=lot.family)

    def _work_entry(self, intent: Intent, now: float, m: S.Moments, *, deadline: float, reprice: float,
                    real_block: Callable[..., str | None], killed: Callable[[], bool], out: dict) -> None:
        today = m.day.isoformat()
        orders = self._intent_orders(intent.iid)
        current = orders[-1] if orders else None
        if current is not None and current.working:
            if now >= deadline:
                self._cancel(current, "the entry cut-off", now)
            elif self._reprice_due(current, now, reprice, m):
                self._cancel(current, "re-priced: cancel, then resend once it is terminal", now)
            orders = self._intent_orders(intent.iid)
            current = orders[-1]
            if current.working:
                return
        et = self._et()
        min_order = Decimal(str(getattr(et, "min_order_usd", "10"))) if et is not None else Decimal("10")
        filled_qty = sum((o.filled_qty for o in orders), ZERO)
        filled_usd = sum((o.filled_value for o in orders), ZERO)
        target = orders[0].qty * orders[0].limit_px if orders else None
        if current is not None:
            final = current.status in ("rejected", "lost") or (current.status == "refused" and not current.answer.get("house"))
            if final:
                cause = current.answer.get("reject_reason") or current.answer.get("error") or current.answer.get("lookup")
                self._finish(intent, "done" if filled_qty > 0 else ("refused" if current.status == "refused" else "missed"),
                             f"the {current.status} {current.side}: {cause}")
                return
            if current.status == "filled" or (target is not None and target - filled_usd < min_order):
                self._finish(intent, "done", f"filled {qty_text(filled_qty)} shares")
                return
        if now >= deadline:
            self._finish(intent, "done" if filled_qty > 0 else "missed",
                         f"the entry cut-off passed{f' with {qty_text(filled_qty)} shares filled' if filled_qty > 0 else ''}"
                         + (f" (last: {intent.why})" if intent.why and filled_qty <= 0 else ""))
            return
        inst = self._instance(intent.instance)
        why = self._open_block(real_block, inst, killed)
        if why:
            if intent.why != why:
                intent.why = why
                self._save_intent(intent)
            return
        symbol = str(intent.symbol or "")
        klass = self._class_of(symbol)
        if klass is None:
            self._finish(intent, "refused", f"{symbol} is not in the equity universe")
            return
        why = self._symbol_busy(symbol) or self._count_refusal(today, exit_=False)
        if why:
            intent.why = why
            self._save_intent(intent)
            return
        quote = self._quote(symbol)
        bid, ask = quote.get("bid"), quote.get("ask")
        fresh = quote.get("t") is not None and quote["t"] >= m.open_at
        if ask is None or bid is None or ask <= 0 or bid <= 0 or ask < bid or not fresh \
                or (ask - bid) / ((ask + bid) / 2) > MAX_ENTRY_SPREAD:
            intent.why = f"no usable quote for {symbol} this minute"
            self._save_intent(intent)
            return
        entry_bp, max_bp = self._collars(klass)
        collar = collar_for(len(orders), entry_bp, max_bp)
        limit = limit_for("buy", ask, collar)
        usd = None if target is None else target - filled_usd
        sized = self._size(intent, inst, symbol, klass, limit, usd, today)
        if sized is None:
            return
        if sized.qty <= 0:
            self._finish(intent, "done" if filled_qty > 0 else "refused", f"sizing ({sized.binding}): {sized.reason}")
            return
        self._send(intent, side="buy", symbol=symbol, klass=klass, qty=sized.qty, limit=limit, collar=collar, day=today,
                   lid=intent.lid, replaces=current.eid if current is not None else None, probe=inst.band == "probe",
                   why=f"entry ({sized.binding}: {sized.reason})"[:300])

    # ------------------------------------------------------------------ sizing
    def _size(self, intent: Intent, inst: Instance, symbol: str, klass: str, limit: Decimal, usd: Decimal | None,
              day: str) -> Z.Sized | None:
        """`sizing.size_entry` on the live figures (the module docstring); None (and the intent's why) when a figure
        cannot be read this minute (retried next minute until the cut-off)."""
        et = self._et()

        def wait(why: str) -> None:
            intent.why = why
            self._save_intent(intent)

        E = self.sizing_equity()
        if E is None or E <= 0:
            wait("no sizing equity (the grant or the account)")
            return None
        account = self._read_account()
        positions = self._read_positions()
        if account is None or positions is None:
            wait("the account or its positions could not be read this minute")
            return None
        try:
            cash = D(account.get("cash"))
        except ValueError:
            wait("the account's cash could not be read")
            return None
        rows = self.state.rows
        try:
            options_loss = self._options_open_loss(day)
            reserved = Decimal(str(self.options_book.reserved())) if self.options_book is not None else ZERO
            available = M.available_cash(account, working_buys_worst=working_buys_worst(rows), reserved=reserved,
                                         reserve_usd=et.cash_reserve)
            budget_room = self._budget_room(day)
        except Exception as exc:  # noqa: BLE001 - fail closed
            wait(f"a sizing figure could not be read ({type(exc).__name__}: {str(exc)[:120]})")
            return None
        any_short = False
        account_symbol = ZERO
        for r in positions:
            if str(r.get("asset_class") or "") != "us_equity":
                continue
            qty = A.dec(r.get("qty")) or ZERO
            if str(r.get("side") or "") == "short" or qty < 0:
                any_short = True
            if str(r.get("symbol") or "").upper() == symbol:
                account_symbol = abs(A.dec(r.get("market_value")) or qty * limit)
        book_symbol = sum((lot.value for lot in self._lots(symbol=symbol)), ZERO)
        buys = [o for o in self._orders(WORKING) if o.side == "buy"]
        all_buys_symbol = sum((o.remaining * o.limit_px for o in buys if o.symbol == symbol), ZERO)
        own_lots = self._lots(instance=inst.id)
        own_buys = [o for o in buys if o.instance == inst.id]
        own_value = sum((lot.value for lot in own_lots), ZERO) + sum((o.remaining * o.limit_px for o in own_buys), ZERO)
        own_symbol = (sum((lot.value for lot in own_lots if lot.symbol == symbol), ZERO)
                      + sum((o.remaining * o.limit_px for o in own_buys if o.symbol == symbol), ZERO))
        sleeve = self._sleeve_share(inst) * E
        x = Z.SizingInputs(symbol=symbol, klass=klass, share=intent.share if usd is None else None,
                           usd=intent.usd if usd is None else usd, limit_price=limit, E=E, sleeve_equity=sleeve,
                           sleeve_free_cash=max(ZERO, sleeve - own_value), sleeve_symbol_value=own_symbol,
                           position_share=Decimal(str(et.position_share[klass])),
                           account_symbol_value=max(book_symbol, account_symbol) + all_buys_symbol,
                           invested_now=invested(rows) + options_loss, invested_share=Decimal(str(et.invested_share)),
                           available_cash=available, cash=cash, any_short=any_short, budget_room=budget_room,
                           weight=Decimal(str(et.open_risk_weight[klass])), min_order_usd=Decimal(str(et.min_order_usd)))
        return Z.size_entry(x)

    def _sleeve_share(self, inst: Instance) -> Decimal:
        """The program's share of E: the Probe sleeve, or a Sized program's (money's `sized_sleeve_share`)."""
        et = self._et()
        probe = Decimal(str(et.probe_sleeve_share))
        if inst.band != "sized":
            return probe
        try:
            return Decimal(str(B.sized_sleeve_share(self._record_of(inst.family, inst.version, None), et)))
        except Exception:  # noqa: BLE001 - never larger than a Probe's when it cannot be read
            return probe

    def _options_open_loss(self, day: str) -> Decimal:
        """The options book's open maximum loss (held and working opens): part of the invested cap (A1)."""
        if self.options_book is None:
            return ZERO
        return Decimal(str(self.options_book.exposure("", day=day, week_start=day).book_loss))

    def _budget_room(self, day: str) -> Decimal:
        """THE PROBE LOSS BUDGET's room: the lower of the window's and the total's, both lanes (`real.probe_figures`)."""
        from ..live import real as R

        _, window, total, at_risk, _ = R.probe_figures(self.state.rows, day=day, table=self.table)
        return min(Decimal(str(self.table.probe_loss_budget)) - window - at_risk,
                   Decimal(str(self.table.probe_loss_total)) - total - at_risk)

    # ------------------------------------------------------------------ intents
    def _exit_pending(self, lid: int) -> bool:
        return bool(self.state.rows("SELECT iid FROM eq_intents WHERE lid=? AND kind IN ('sell', 'house_exit') "
                                    "AND status IN ('planned', 'sent') LIMIT 1", (int(lid),)))

    def _plan_exit(self, lot: Lot, *, exec_day: str, at: str, reason: str, why: str, decided_day: str,
                   instance: str | None = None, family: str | None = None, version: int | None = None) -> Intent:
        now = self.clock()
        iid = self._next("eq_intents", "iid")
        intent = Intent(iid, instance or lot.instance, family or lot.family, int(version if version is not None else lot.version),
                        decided_day, exec_day, at, "house_exit", "planned", symbol=lot.symbol, lid=lot.lid, tag=reason,
                        why=why[:400], created_at=now, updated_at=now)
        self._save_intent(intent)
        return intent

    # ------------------------------------------------------------------ the decide
    def _last_closed(self, now: float) -> dt.date | None:
        """The latest session whose 16:20 bars moment has passed (the decision day that is due or done)."""
        d = S.ny_day(now)
        off = self._offsets()
        for _ in range(S.HORIZON_DAYS):
            mm = S.moments(d, off)
            if mm is not None and mm.bars_at <= now:
                return d
            d -= dt.timedelta(days=1)
        return None

    def _decide_step(self, now: float, out: dict) -> None:
        """The decision of the last session: the instances synced (bands, retirements), its bars read (16:20), its
        programs decided (16:30) and the House's exit rules applied; a catch-up after a restart, until the next
        session's close window."""
        t = self._last_closed(now)
        if t is None:
            return
        day = t.isoformat()
        done = self.state.get("eq_decide", {}) or {}
        if str(done.get("day") or "") >= day:
            return
        off = self._offsets()
        mt, nxt = S.moments(t, off), S.next_session(t)
        mn = S.moments(nxt, off)
        if mn is not None and now >= mn.close_send - 60:
            self._decide_failed(t, now, "no decide ran before the next session's close window")
            return
        et = self._et()
        if et is None:
            return
        if not et.enabled and not self._lots():
            self.state.put("eq_decide", {"day": day, "status": "idle", "at": now, "why": "the lane is off and holds nothing"})
            return
        if (self.state.get("eq_synced") or "") != day and self._sync_instances(now, t, out):
            self.state.put("eq_synced", day)
        live = [i for i in self._instances(alive=True) if i.live]
        if not live:
            self._house_exits(t, now)
            self.state.put("eq_decide", {"day": day, "status": "done", "at": now, "why": "no live program"})
            return
        for inst in live:
            self._ensure_loaded(inst)
        symbols = sorted({s for i in live for s in (self._needs.get(i.id) or {}).get("symbols", [])})
        history = max([int((self._needs.get(i.id) or {}).get("history", 0)) for i in live] + [1])
        bars = self._bars if self._bars is not None and self._bars.get("day") == day else None
        if symbols and (bars is None or set(symbols) - set(bars.get("present") or ())):
            try:
                self._fetch_bars(t, symbols, history, now)
            except Exception as exc:  # noqa: BLE001 - read again next minute (the decide waits for its grace)
                self._error("bars", exc, out)
            bars = self._bars if self._bars is not None and self._bars.get("day") == day else None
        if now < mt.decide_at:
            return
        missing = set(symbols) - set((bars or {}).get("present") or ())
        if missing and now < mt.decide_at + BARS_GRACE_S:
            out["decide"] = f"waiting for the bars of {', '.join(sorted(missing))}"
            return
        self._decide(t, live, bars or {"day": day, "symbols": [], "present": [], "raw": {}, "all": {}}, now, out)
        self._house_exits(t, now)
        self.state.put("eq_decide", {"day": day, "status": "done", "at": now})

    def _sync_instances(self, now: float, t: dt.date, out: dict) -> bool:
        """The equity families' rows against the book's instances: band moves (`bands.next_band`, the book alone moves
        candidate <-> probe <-> sized, while the lane is enabled), a Probe or Sized row's instance created or updated, and
        every instance whose family no longer runs it retired (its lots exit at the next open, planned in
        `_house_exits`). An unreadable store changes nothing."""
        et = self._et()
        rows = [dict(r) for r in self.families.read() if str(r.get("lane") or "") in _pkg.LANES]
        if getattr(self.families, "last_error", ""):
            out["families"] = f"unreadable: {self.families.last_error}"
            return False
        sticky = dict(self.state.get("eq_sticky", {}) or {})
        since = dict(self.state.get("eq_band_since", {}) or {})
        day = t.isoformat()
        if et is not None and et.enabled:
            live_n = sum(1 for r in rows if r.get("band") in LIVE_BANDS)
            for row in rows:
                if row.get("band") not in ("candidate",) + LIVE_BANDS:
                    continue
                key = instance_key(row["family"], int(row["version"]))
                try:
                    record = self._record_of(row["family"], int(row["version"]), row)
                    band, why = B.next_band(row, record, et, seat_free=live_n < int(et.probe_max_programs)
                                            or row.get("band") in LIVE_BANDS, sticky=sticky.get(key))
                except Exception as exc:  # noqa: BLE001 - no move on a rule that cannot be read
                    self._error(f"band {row['family']}", exc, out)
                    continue
                if band == row.get("band"):
                    continue
                if not self.families.confirm_band(row, band, why):
                    out.setdefault("bands", []).append(f"{row['family']}: the row changed; no move")
                    continue
                self.record("equity.band", {"family": row["family"], "version": row["version"], "from": row["band"],
                                            "to": band, "why": why[:300]}, agent=row["family"])
                if band == "candidate" and row.get("band") in LIVE_BANDS:
                    sticky[key] = why[:300]
                    live_n -= 1
                elif row.get("band") == "candidate" and band in LIVE_BANDS:
                    live_n += 1
                row["band"] = band
                since[key] = {"band": band, "day": day}
        self.state.put("eq_sticky", sticky)
        holds = self._holds()
        wanted: dict[str, dict] = {}
        for row in rows:
            if row.get("band") in LIVE_BANDS:
                wanted[instance_key(row["family"], int(row["version"]))] = row
        for key, row in wanted.items():
            inst = self._instance(key)
            params = dict(row.get("params") or {})
            if inst is None:
                inst = Instance(key, str(row["family"]), int(row["version"]), str(row.get("lane") or ""),
                                str(row.get("run_sha") or ""), str(row.get("code") or ""), params, str(row["band"]),
                                bool(row.get("seeded")), holds[1], created_at=now)
                since.setdefault(key, {"band": inst.band, "day": day})
                self.record("equity.instance", {"instance": key, "band": inst.band, "lane": inst.lane}, agent=inst.family)
            elif inst.retired_at is not None:
                continue   # a retired version never runs again (its family runs a new version under a new key)
            else:
                inst.band, inst.code, inst.params, inst.run_sha = str(row["band"]), str(row.get("code") or ""), params, \
                    str(row.get("run_sha") or "")
                inst.seeded = bool(row.get("seeded"))
            self._save_instance(inst)
        by_family = {str(r["family"]): r for r in rows}
        for inst in self._instances(alive=True):
            if inst.id in wanted:
                continue
            row = by_family.get(inst.family)
            if row is None:
                code, why = "retired", "its family is no longer an equity-lane family the House may run"
            elif int(row.get("version") or 0) != inst.version:
                code, why = "retired", f"superseded by version {row.get('version')}"
            else:
                code, why = "demoted", f"its band is {row.get('band')}"
            inst.retired_at, inst.why, inst.band = now, f"{code}: {why}", ("candidate" if code == "demoted" else inst.band)
            self._save_instance(inst)
            self._drop(inst)
            self.record("equity.instance", {"instance": inst.id, "retired": True, "why": inst.why}, agent=inst.family)
        self.state.put("eq_band_since", since)
        return True

    def _drop(self, inst: Instance) -> None:
        self._loaded.pop(inst.id, None)
        self._needs.pop(inst.id, None)
        try:
            self.decider.kind_drop("equity", inst.id)
        except Exception:  # noqa: BLE001 - a dropped program is never asked again either way
            pass

    def _ensure_loaded(self, inst: Instance) -> bool:
        """The instance's program loaded in the decider child (its NEEDS read there: the House never executes it)."""
        sig = (hashlib.sha256(inst.code.encode()).hexdigest(), dumps(inst.params))
        if self._loaded.get(inst.id) == sig:
            return True
        try:
            answer = self.decider.kind_load("equity", inst.id, {"code": inst.code, "params": inst.params,
                                                                 "name": inst.family, "timeout": DECIDE_TIMEOUT,
                                                                 "max_errors": DECIDE_MAX_ERRORS})
        except Exception as exc:  # noqa: BLE001 - refused or the child failed: this decide fails
            self._needs.pop(inst.id, None)
            inst.why = f"load: {type(exc).__name__}: {str(exc)[:200]}"
            self._save_instance(inst)
            return False
        if not answer or not answer.get("ok"):
            self._needs.pop(inst.id, None)
            inst.why = f"load: {str((answer or {}).get('error') or 'refused')[:200]}"
            self._save_instance(inst)
            return False
        needs = dict(answer.get("needs") or {})
        _, default_hold, cap, _ = self._holds()
        inst.max_hold = max(1, min(cap, int(needs.get("max_hold_sessions") or default_hold)))
        if answer.get("params") is not None:
            needs["_params"] = answer.get("params")
        self._needs[inst.id] = needs
        self._loaded[inst.id] = sig
        self._save_instance(inst)
        return True

    def _fetch_bars(self, t: dt.date, symbols: Sequence[str], history: int, now: float) -> None:
        """The 1Day bars of `symbols` through session t, adjustment=raw and adjustment=all, kept for the decide and
        written to `eq_bars` (the rows and each series' sha: A8.11's provenance)."""
        start = (t - dt.timedelta(days=int(history * 1.5) + 14)).isoformat()
        end = (t + dt.timedelta(days=1)).isoformat()
        raw = self.market.bars(list(symbols), timeframe="1Day", start=start, end=end, adjustment="raw")
        adj = self.market.bars(list(symbols), timeframe="1Day", start=start, end=end, adjustment="all")
        day = t.isoformat()
        keep: dict[str, dict[str, list[dict]]] = {"raw": {}, "all": {}}
        for name, fetched in (("raw", raw), ("all", adj)):
            for symbol in symbols:
                rows = [dict(r) for r in (fetched or {}).get(symbol) or [] if (_bar_day(r) or "9999") <= day]
                rows.sort(key=lambda r: _bar_day(r) or "")
                keep[name][symbol] = rows
        present = [s for s in symbols if keep["raw"][s] and _bar_day(keep["raw"][s][-1]) == day
                   and keep["all"][s] and _bar_day(keep["all"][s][-1]) == day]
        shas = {}
        with self.state.transaction():
            for name in ("raw", "all"):
                for symbol in present:
                    series = [[_bar_day(r), r.get("o"), r.get("h"), r.get("l"), r.get("c"), r.get("v")]
                              for r in keep[name][symbol]]
                    sha = _sha(series)
                    shas.setdefault(symbol, {})[name] = sha
                    for d, o, h, l, c, v in series:
                        self.state.execute(
                            "INSERT INTO eq_bars(day, symbol, adjustment, o, h, l, c, v, fetched_at, sha, audit) "
                            "VALUES(?,?,?,?,?,?,?,?,?,?,NULL) ON CONFLICT(day, symbol, adjustment) DO UPDATE SET "
                            "o=excluded.o, h=excluded.h, l=excluded.l, c=excluded.c, v=excluded.v, "
                            "fetched_at=excluded.fetched_at, sha=excluded.sha, audit=NULL",
                            (d, symbol, name, *(None if x is None else str(x) for x in (o, h, l, c, v)), now, sha))
            self.state.put("eq_decision", {"day": day, "start": start, "end": end, "symbols": sorted(present),
                                           "shas": shas, "audit": None, "fetched_at": now})
        self._bars = {"day": day, "symbols": list(symbols), "present": present, "raw": keep["raw"], "all": keep["all"],
                      "shas": shas, "start": start, "end": end, "fetched_at": now}
        self.record("equity.bars", {"day": day, "symbols": list(symbols), "present": present})

    def _decide(self, t: dt.date, live: Sequence[Instance], bars: Mapping[str, Any], now: float, out: dict) -> None:
        """One "decide" request for every live instance whose bars and program are ready; its intents recorded."""
        day = t.isoformat()
        jobs, failed, meta = [], {}, {}
        for inst in live:
            if not self._ensure_loaded(inst):
                failed[inst.id] = inst.why or "the program did not load"
                continue
            needs = self._needs[inst.id]
            symbols = [str(s).upper() for s in needs.get("symbols") or []]
            missing = [s for s in symbols if s not in set(bars.get("present") or ())]
            if missing:
                failed[inst.id] = f"no bar of {', '.join(missing)} for {day}"
                continue
            try:
                inputs, bars_sha = self._inputs(inst, t, needs, bars)
            except Exception as exc:  # noqa: BLE001 - the bars or the book cannot make its ctx: a failed decide
                failed[inst.id] = f"ctx: {type(exc).__name__}: {str(exc)[:200]}"
                continue
            jobs.append({"key": inst.id, "inputs": inputs})
            meta[inst.id] = bars_sha
        results: dict[str, Any] = {}
        if jobs:
            try:
                answer = self.decider.kind("equity", "decide", {"jobs": jobs})
                if answer.get("ok"):
                    results = dict(answer.get("results") or {})
                else:
                    for job in jobs:
                        failed[job["key"]] = f"the decider: {str(answer.get('error') or 'failed')[:200]}"
            except Exception as exc:  # noqa: BLE001
                for job in jobs:
                    failed[job["key"]] = f"the decider: {type(exc).__name__}: {str(exc)[:200]}"
        decided = []
        for inst in live:
            result = results.get(inst.id)
            if inst.id not in failed and (not isinstance(result, Mapping) or result.get("ok") is False):
                failed[inst.id] = f"no answer: {str((result or {}).get('error') if isinstance(result, Mapping) else '')[:200]}"
            if inst.id in failed:
                inst.failed_decides += 1
                inst.why = f"decide {day}: {failed[inst.id]}"[:400]
                self._save_instance(inst)
                continue
            with self.state.transaction():
                n = self._record_intents(inst, t, list(result.get("intents") or []), result.get("ctx_sha"),
                                         meta.get(inst.id))
                inst.failed_decides, inst.last_decided_day, inst.why = 0, day, ""
                self._save_instance(inst)
            decided.append(f"{inst.id}: {n}")
        out["decided"] = decided
        if failed:
            out["decide_failed"] = dict(failed)
            self.alert("warning", f"equity: the decide of {day} failed for {', '.join(sorted(failed))}")
        self.record("equity.decide", {"day": day, "decided": decided, "failed": failed})

    def _inputs(self, inst: Instance, t: dt.date, needs: Mapping[str, Any], bars: Mapping[str, Any]) -> tuple[Any, str]:
        """The instance's ctx inputs (`ctx.inputs_from_fetch`, the Gym's own constructor's live twin, I6) and the sha of
        the bars it reads."""
        day = t.isoformat()
        symbols = [str(s).upper() for s in needs.get("symbols") or []]
        raw = {s: bars["raw"][s] for s in symbols}
        adj = {s: bars["all"][s] for s in symbols}
        closes = {s: A.dec(raw[s][-1].get("c")) for s in symbols if raw[s]}
        now = self.clock()
        with self.state.transaction():
            for lot in self._lots():
                close = closes.get(lot.symbol) or (A.dec(bars["raw"].get(lot.symbol, [{}])[-1].get("c"))
                                                   if bars["raw"].get(lot.symbol) else None)
                if close is not None and close > 0:
                    lot.mark, lot.marked_at = close, now
                    self._save_lot(lot)
        lots = self._lots(instance=inst.id)
        positions = [C.lot_row(lid=lot.lid, symbol=lot.symbol, klass=lot.klass, qty=float(lot.qty),
                               entry=float(lot.entry_px), mark=float(lot.mark or lot.entry_px),
                               held_sessions=S.sessions_between(lot.opened_day, day), at=lot.entry_at, tag=lot.tag)
                     for lot in lots]
        last = inst.last_decided_day or ""
        closed = [C.closed_row(lid=lot.lid, symbol=lot.symbol, qty=float(lot.opened_qty), entry=float(lot.entry_px),
                               exit=float(lot.exit_px or 0), net=float(lot.cash),
                               held_sessions=S.sessions_between(lot.opened_day, lot.exit_day or day),
                               reason=_ctx_reason(lot.reason), tag=lot.tag)
                  for lot in self._lots(instance=inst.id, open_only=False)
                  if lot.status == LOT_CLOSED and (lot.exit_day or "") > last]
        rejects = [r["why"] for r in self.state.rows(
            "SELECT why FROM eq_intents WHERE instance=? AND status IN ('refused', 'missed') AND decided_day=? "
            "ORDER BY iid", (inst.id, last)) if r["why"]][:20] if last else []
        orders = [{"id": int(r["iid"]), "side": "buy" if r["kind"] == "buy" else "sell", "symbol": r["symbol"],
                   "at": r["at"], "usd": float(r["usd"]) if r["usd"] else None, "tag": r["tag"] or ""}
                  for r in self.state.rows("SELECT * FROM eq_intents WHERE instance=? AND status='planned' AND exec_day>? "
                                           "AND kind IN ('buy', 'sell')", (inst.id, day))]
        E = self.sizing_equity() or ZERO
        et = self._et()
        budget = self._sleeve_share(inst) * E if et is not None else ZERO
        own_value = sum((lot.value for lot in lots), ZERO)
        cash = max(ZERO, budget - own_value)
        caps = {}
        for symbol in symbols:
            klass = self._class_of(symbol) or "stock"
            share = Decimal(str(et.position_share.get(klass, "0"))) if et is not None else ZERO
            account_symbol = sum((lot.value for lot in self._lots(symbol=symbol)), ZERO)
            own_symbol = sum((lot.value for lot in lots if lot.symbol == symbol), ZERO)
            caps[symbol] = float(max(ZERO, min(share * E - account_symbol, share * budget - own_symbol, cash)))
        params = needs.get("_params") if needs.get("_params") is not None else inst.params
        program_needs = P.Needs(tuple(symbols), int(needs.get("history", 0)), int(inst.max_hold))
        inputs = C.inputs_from_fetch(raw, adj, day=t, needs=program_needs, positions=positions, orders=orders,
                                     closed=closed, rejects=rejects, cash=float(cash), equity=float(cash + own_value),
                                     budget=float(budget), caps=caps, params=params)
        shas = (bars.get("shas") or {})
        return inputs, _sha({s: shas.get(s) for s in symbols})

    def _record_intents(self, inst: Instance, t: dt.date, intents: Sequence[Any], ctx_sha: Any, bars_sha: Any) -> int:
        """The program's intents as `eq_intents` rows for the next session (each checked here again: a malformed one
        is recorded refused, the program reads why in its next ctx's rejects)."""
        day, exec_day, now = t.isoformat(), S.next_session(t).isoformat(), self.clock()
        needs = [str(s).upper() for s in (self._needs.get(inst.id) or {}).get("symbols") or []]
        lots = {lot.lid: lot for lot in self._lots(instance=inst.id)}
        selling: set[int] = set()
        n = 0

        def add(kind: str, status: str, why: str = "", **values: Any) -> None:
            nonlocal n
            iid = self._next("eq_intents", "iid")
            at = values.pop("at", "open")
            self._save_intent(Intent(iid, inst.id, inst.family, inst.version, day, exec_day,
                                     at if at in ("open", "close") else "open", kind, status, why=why, ctx_sha=ctx_sha,
                                     bars_sha=bars_sha, created_at=now, updated_at=now, **values))
            n += 1

        for raw in list(intents)[:config.MAX_INTENTS]:
            if not isinstance(raw, Mapping):
                add("buy", "refused", "an intent that is not a dict")
                continue
            at = raw.get("at", "open")
            tag = str(raw.get("tag") or "")[:120]
            if at not in ("open", "close"):
                add("buy", "refused", f"at {at!r}: an intent fills at the open or the close", tag=tag)
                continue
            if "buy" in raw:
                symbol = str(raw.get("buy") or "").upper()
                share, usd = A.dec(raw.get("share")), A.dec(raw.get("usd"))
                if symbol not in needs or self._class_of(symbol) is None:
                    add("buy", "refused", f"{symbol}: not one of the program's NEEDS symbols in the universe", at=at,
                        symbol=symbol or None, tag=tag)
                elif (share is None) == (usd is None) or (share is not None and not 0 < share <= 1) \
                        or (usd is not None and usd <= 0):
                    add("buy", "refused", "a buy names a share in (0, 1] or dollars above 0, exactly one", at=at,
                        symbol=symbol, tag=tag)
                else:
                    add("buy", "planned", at=at, symbol=symbol, share=share, usd=usd, tag=tag)
            elif "sell" in raw:
                try:
                    lid = int(raw.get("sell"))
                except (TypeError, ValueError):
                    lid = -1
                lot = lots.get(lid)
                if lot is None:
                    add("sell", "refused", f"lot {raw.get('sell')!r} is not an open lot of this program", at=at, tag=tag)
                elif lid in selling or self._exit_pending(lid):
                    add("sell", "refused", f"lot {lid} already has an exit planned", at=at, symbol=lot.symbol, lid=lid,
                        tag=tag)
                else:
                    selling.add(lid)
                    add("sell", "planned", at=at, symbol=lot.symbol, lid=lid, tag=tag)
            elif "cancel" in raw:
                target = self._intent(raw.get("cancel")) if str(raw.get("cancel")).lstrip("-").isdigit() else None
                if target is None or target.instance != inst.id or target.status != "planned" \
                        or target.kind not in ("buy", "sell"):
                    add("cancel", "refused", f"intent {raw.get('cancel')!r} is not a planned buy or sell of this program "
                                             "(the House's own exits cannot be canceled)")
                else:
                    self._finish(target, "canceled", "canceled by its program")
                    add("cancel", "done", f"canceled intent {target.iid}", lid=target.lid, symbol=target.symbol)
            else:
                add("buy", "refused", "an intent is a buy, a sell or a cancel", tag=tag)
        return n

    def _house_exits(self, t: dt.date, now: float) -> int:
        """THE HOUSE'S EXIT RULES (A8.5, identical in the Gym engine), planned at the decision of session t for the
        next open: a retired or demoted program's lots; a program with `failed_decides_exit` failed decides in a row;
        a lot held its program's `max_hold_sessions` by the next open."""
        day, nxt = t.isoformat(), S.next_session(t).isoformat()
        _, default_hold, cap, failed_exit = self._holds()
        n = 0
        with self.state.transaction():
            for lot in self._lots():
                if self._exit_pending(lot.lid):
                    continue
                inst = self._instance(lot.instance)
                reason, why = None, ""
                if inst is None or inst.retired_at is not None or inst.band not in LIVE_BANDS:
                    code = "demoted" if inst is not None and str(inst.why).startswith("demoted") else "retired"
                    reason, why = code, f"its program is {code}: {inst.why if inst else 'unknown to the book'}"
                elif inst.failed_decides >= failed_exit:
                    reason, why = "house", f"{inst.failed_decides} failed decides in a row"
                else:
                    hold = max(1, min(cap, int(inst.max_hold or default_hold)))
                    held = S.sessions_between(lot.opened_day, day)
                    if held + 1 >= hold:
                        reason, why = "max_hold", f"held {held + 1} sessions by the next open (its maximum {hold})"
                if reason:
                    self._plan_exit(lot, exec_day=nxt, at="open", reason=reason, why=why, decided_day=day)
                    n += 1
        if n:
            self.record("equity.house_exits", {"day": day, "lots": n})
        return n

    def _decide_failed(self, t: dt.date, now: float, why: str) -> None:
        day = t.isoformat()
        for inst in self._instances(alive=True):
            if inst.live and inst.last_decided_day != day:
                inst.failed_decides += 1
                inst.why = f"decide {day}: {why}"[:400]
                self._save_instance(inst)
        self._house_exits(t, now)
        self.state.put("eq_decide", {"day": day, "status": "failed", "at": now, "why": why})
        self.alert("warning", f"equity: the decide of {day} failed: {why}")

    # ------------------------------------------------------------------ the morning audit (A8.11)
    def _audit(self, now: float, m: S.Moments | None, out: dict) -> None:
        """The last decision's bars fetched again before the next open and compared: raw rows exactly, adjustment=all
        rows as the as-of prices a program saw (all_s x raw_t / all_t, within a millionth: an event after t rescales the
        series without changing them). A mismatch is an alarm and a twin note; that decision's planned buys of the
        affected programs are canceled and it counts as a failed decide (A8.5)."""
        if m is None or not (m.audit_at <= now < m.open_send):
            return
        decision = dict(self.state.get("eq_decision") or {})
        if not decision or decision.get("audit") or decision.get("day") != S.previous_session(m.day).isoformat():
            return
        symbols = list(decision.get("symbols") or [])
        if not symbols:
            decision["audit"] = "ok"
            self.state.put("eq_decision", decision)
            return
        day = decision["day"]
        try:
            raw = self.market.bars(symbols, timeframe="1Day", start=decision["start"], end=decision["end"],
                                   adjustment="raw")
            adj = self.market.bars(symbols, timeframe="1Day", start=decision["start"], end=decision["end"],
                                   adjustment="all")
        except Exception as exc:  # noqa: BLE001 - again next minute; unread at the open is an alarm only
            if now >= m.preopen:
                decision["audit"] = "unread"
                self.state.put("eq_decision", decision)
                self.alert("warning", f"equity: the bars of {day} could not be read again ({type(exc).__name__})")
            return
        stored: dict[tuple[str, str], dict[str, tuple]] = {}
        for r in self.state.rows("SELECT * FROM eq_bars WHERE symbol IN (%s) AND day>=? AND day<=?"
                                 % ",".join("?" * len(symbols)), (*symbols, decision["start"], day)):
            stored.setdefault((r["symbol"], r["adjustment"]), {})[r["day"]] = (r["o"], r["h"], r["l"], r["c"], r["v"])
        bad = []
        for symbol in symbols:
            start = decision["start"]
            fresh_raw = {_bar_day(r): r for r in (raw or {}).get(symbol) or [] if start <= (_bar_day(r) or "9999") <= day}
            fresh_all = {_bar_day(r): r for r in (adj or {}).get(symbol) or [] if start <= (_bar_day(r) or "9999") <= day}
            old_raw, old_all = stored.get((symbol, "raw"), {}), stored.get((symbol, "all"), {})
            if set(fresh_raw) != set(old_raw) or set(fresh_all) != set(old_all) or day not in old_raw:
                bad.append(symbol)
                continue
            if any(A.dec(fresh_raw[d].get(k)) != A.dec(old_raw[d][i]) for d in old_raw
                   for i, k in enumerate(("o", "h", "l", "c", "v"))):
                bad.append(symbol)
                continue
            if not _as_of_equal(old_raw, old_all, fresh_raw, fresh_all, day):
                bad.append(symbol)
        verdict = "mismatch" if bad else "ok"
        with self.state.transaction():
            self.state.execute("UPDATE eq_bars SET audit=? WHERE day=?", (verdict, day))
            if bad:
                self.state.execute(f"UPDATE eq_bars SET audit='mismatch' WHERE day=? AND symbol IN "
                                   f"({','.join('?' * len(bad))})", (day, *bad))
            decision["audit"], decision["mismatch"] = verdict, bad
            self.state.put("eq_decision", decision)
        if not bad:
            return
        notes = dict(self.state.get("eq_bars_audit", {}) or {})
        notes[day] = {"symbols": bad, "at": now}
        self.state.put("eq_bars_audit", dict(sorted(notes.items())[-30:]))
        self.alert("error", f"equity: the bars of {day} read again differ for {', '.join(bad)}: that decision's buys "
                            "are canceled")
        hit = []
        for inst in self._instances(alive=True):
            if inst.last_decided_day != day:
                continue
            symbols_of = {str(s).upper() for s in (self._needs.get(inst.id) or {}).get("symbols") or []}
            planned = [Intent.of(r) for r in self.state.rows(
                "SELECT * FROM eq_intents WHERE instance=? AND decided_day=? AND kind='buy' AND status='planned'",
                (inst.id, day))]
            # A program whose NEEDS are not known in this process (a restart) counts as affected when it plans a buy.
            if not (symbols_of & set(bad) if symbols_of else planned):
                continue
            for intent in planned:
                self._finish(intent, "canceled", f"the bars of {day} read again differ ({', '.join(bad)})")
            inst.failed_decides += 1
            inst.why = f"bars audit {day}: {', '.join(bad)}"
            self._save_instance(inst)
            hit.append(inst.id)
        self.record("equity.bars_audit", {"day": day, "mismatch": bad, "programs": hit})

    # ------------------------------------------------------------------ reconciliation
    def _reconcile_step(self, now: float, m: S.Moments | None, out: dict) -> None:
        if m is None or not (m.preopen <= now < m.close_at):
            return
        positions = self._read_positions()
        if positions is None:
            out["reconcile"] = "the positions could not be read"
            return
        out["reconcile"] = self.reconcile(positions, now) or "clean"

    def reconcile(self, positions: Sequence[Mapping[str, Any]], now: float | None = None) -> list[str]:
        """The account's us_equity quantity per symbol against the book (the module docstring). Returns the mismatches
        of THIS reading; the freeze follows two readings in a row."""
        now = self.clock() if now is None else float(now)
        expected = self.expected_shares()
        ledger: dict[str, Decimal] = {}
        for symbol, value in (self.state.get("shares", {}) or {}).items():
            amount = A.dec(value)
            if amount:
                ledger[str(symbol).upper()] = amount
        held: dict[str, Decimal] = {}
        for row in positions:
            if str(row.get("asset_class") or "") != "us_equity":
                continue
            symbol = str(row.get("symbol") or "").upper()
            qty = A.dec(row.get("qty")) or ZERO
            held[symbol] = held.get(symbol, ZERO) + (-abs(qty) if str(row.get("side") or "") == "short" else qty)
        flux = self.busy() | {str(r["symbol"]) for r in self.state.rows(
            "SELECT DISTINCT symbol FROM eq_orders WHERE updated_at>=?", (now - FLUX_S,))}
        problems = []
        for symbol in sorted(set(expected) | set(held) | set(ledger)):
            if symbol in flux:
                continue
            want = expected.get(symbol, ZERO) + ledger.get(symbol, ZERO)
            have = held.get(symbol, ZERO)
            if abs(have - want) > SHARE_TOLERANCE:
                problems.append(f"{symbol}: the account holds {text(have)}, the equity book expects {text(want)}"
                                + (f" ({text(ledger[symbol])} of them an assignment's)" if symbol in ledger else ""))
        rows = self._venue_open()
        if rows is not None:
            mine = {str(r["client_id"]) for r in self.state.rows("SELECT client_id FROM eq_orders")}
            for r in rows:
                cid = str(r.get("client_order_id") or "")
                if cid.startswith(CLIENT_PREFIX) and cid not in mine and str(r.get("status") or "") in VENUE_WORKING:
                    problems.append(f"a working equity order the book does not know: {cid[:60]}")
        self._streak["bad" if problems else "good"] += 1
        self._streak["good" if problems else "bad"] = 0
        recon = self.state.get("eq_recon", {}) or {}
        was = str(recon.get("frozen") or "")
        frozen = was
        if problems and self._streak["bad"] >= 2:
            frozen = "; ".join(problems[:6])
        elif not problems and self._streak["good"] >= 2:
            frozen = ""
        self.state.put("eq_recon", {"frozen": frozen, "bad": self._streak["bad"], "good": self._streak["good"],
                                    "problems": problems[:20], "at": now})
        if frozen != was:
            self.record("equity.freeze", {"frozen": bool(frozen), "why": frozen or f"cleared (was: {was[:300]})"})
            if frozen and not was:
                self.alert("error", f"equity: entries frozen by reconciliation: {frozen}")
        return problems

    # ------------------------------------------------------------------ activities (A8.10)
    def _activities(self, now: float, m: S.Moments | None, out: dict) -> None:
        """Dividends, splits and corporate actions of held symbols, every `ACTIVITIES_EVERY` (and at the pre-open),
        while the book holds a lot or closed one in the last 70 days (a dividend is paid weeks after its ex-date)."""
        preopen_due = m is not None and m.preopen <= now < m.open_at and \
            (self.state.get("eq_preopen_activities") or "") != m.day.isoformat()
        if now - self._activities_at < ACTIVITIES_EVERY and not preopen_due:
            return
        recent = (S.ny_day(now) - dt.timedelta(days=100)).isoformat()
        if not self.state.rows("SELECT lid FROM eq_lots WHERE status!='closed' OR exit_day>=? LIMIT 1", (recent,)):
            return
        self._activities_at = now
        if preopen_due:
            self.state.put("eq_preopen_activities", m.day.isoformat())
        cursor = str(self.state.get("eq_activities_cursor") or "")
        first = self.state.rows("SELECT MIN(opened_day) AS d FROM eq_lots")[0]["d"]
        after = (dt.date.fromisoformat(cursor) - dt.timedelta(days=3)).isoformat() if cursor else \
            (dt.date.fromisoformat(first) - dt.timedelta(days=1)).isoformat() if first else None
        rows = list(self.account.activities(list(A.TYPES), after=after))
        if now - self._watch_at >= WATCH_EVERY:
            self._watch_at = now
            refused = set(self.state.get("eq_activity_refused", []) or [])
            for kind in A.WATCH:
                if kind in refused:
                    continue
                try:
                    rows.extend(self.account.activities([kind], after=after))
                except Exception as exc:  # noqa: BLE001 - best effort; a type the venue refuses is skipped from now on
                    if "422" in str(exc):
                        refused.add(kind)
                        self.state.put("eq_activity_refused", sorted(refused))
        seen = {r["id"] for r in self.state.rows("SELECT id FROM eq_activities")}
        latest = cursor
        for row in sorted(rows, key=lambda r: (A.activity_day(r) or "", str(r.get("id")))):
            key = str(row.get("id") or "")
            day = A.activity_day(row) or ""
            if day > latest:
                latest = day
            if not key or key in seen:
                continue
            seen.add(key)
            try:
                self._book_activity(row, now, out)
            except Exception as exc:  # noqa: BLE001 - not booked: read again (and booked) next time
                seen.discard(key)
                self._error(f"activity {key}", exc, out)
        if latest and latest != cursor:
            self.state.put("eq_activities_cursor", latest)

    def _book_activity(self, row: Mapping[str, Any], now: float, out: dict) -> None:
        kind = str(row.get("activity_type") or "").upper()
        symbol = str(row.get("symbol") or "").upper()
        activity = dict(row)
        if kind in A.DIVIDENDS:
            lots = self._dividend_lots(activity, symbol)
        else:
            lots = [{**lot.row(), "lid": lot.lid} for lot in self._lots(symbol=symbol)]
            if kind in ("SSP", "REORG", "MA") and A.ratio_of(activity) is None and lots:
                ratio = self._inferred_ratio(symbol)
                if ratio is not None:
                    activity["ratio"] = str(ratio)
        booking = A.book_activity(activity, lots)
        with self.state.transaction():
            for lid, changes in booking.per_lot.items():
                lot = self._lot(lid)
                if lot is None:
                    continue
                if "div" in changes:
                    lot.div += changes["div"]
                if "cash" in changes:
                    lot.cash += changes["cash"]
                if "opened_qty" in changes:
                    lot.opened_qty = changes["opened_qty"]
                if "entry_px" in changes:
                    lot.entry_px = changes["entry_px"]
                if "qty" in changes and lot.status != LOT_CLOSED:
                    lot.qty = changes["qty"]
                    if lot.qty <= 0:
                        lot.qty, lot.status, lot.closed_at, lot.reason = ZERO, LOT_CLOSED, now, "forced"
                        lot.exit_day, lot.exit_at = booking.day or S.ny_day(now).isoformat(), "open"
                        lot.exit_px = ((lot.cash + lot.entry_notional - lot.div) / lot.opened_qty).quantize(PRICE_PLACES) \
                            if lot.opened_qty > 0 else ZERO
                lot.info.setdefault("activities", []).append(str(row.get("id")))
                self._save_lot(lot)
            if booking.kind == "rename" and booking.new_symbol:
                for lot in self._lots(symbol=symbol):
                    lot.info["renamed_from"] = lot.symbol
                    lot.symbol = booking.new_symbol
                    self._save_lot(lot)
            self.state.execute("INSERT OR IGNORE INTO eq_activities(id, type, symbol, day, qty, net, booked, at) "
                               "VALUES(?,?,?,?,?,?,?,?)",
                               (str(row.get("id")), kind, symbol or None, booking.day,
                                None if row.get("qty") is None else str(row.get("qty")),
                                None if row.get("net_amount") is None else str(row.get("net_amount")),
                                dumps(booking.as_dict()), now))
        self.record("equity.activity", {"id": str(row.get("id")), "type": kind, "symbol": symbol, "kind": booking.kind,
                                        "why": booking.why[:300], "lots": sorted(booking.per_lot)})
        out.setdefault("activities", []).append(f"{kind} {symbol}: {booking.kind}")
        if booking.kind in ("freeze", "rename"):
            self.state.put("eq_freeze", {"why": booking.why[:400], "at": now, "activity": str(row.get("id"))})
            self.alert("error", f"equity: {booking.why}")
        elif booking.kind == "dividend" and not booking.per_lot:
            self.alert("warning", f"equity: {booking.why}")
        elif booking.kind == "spinoff":
            self.alert("warning", f"equity: {booking.why}")

    def _dividend_lots(self, activity: Mapping[str, Any], symbol: str) -> list[dict]:
        """The lots a dividend belongs to, each with the quantity it held on the ex-date as "qty": the row's ex-date
        when it states one, else the latest session (in the `DIVIDEND_LOOKBACK_SESSIONS` before the row's date) whose
        held quantity equals the row's `qty`; [] when neither finds them (booked to nobody, alarmed)."""
        lots = self._lots(symbol=symbol, open_only=False)

        def held_on(ex: str) -> list[dict]:
            return [{**lot.row(), "lid": lot.lid, "qty": text(lot.opened_qty)} for lot in lots
                    if lot.opened_day < ex and (lot.status != LOT_CLOSED or (lot.exit_day or "") >= ex)]

        ex = A.ex_date(activity)
        if ex:
            return held_on(ex)
        want = A.dec(activity.get("qty"))
        day = A.activity_day(activity)
        if want is None or want <= 0 or not day:
            return []
        d = dt.date.fromisoformat(day)
        for _ in range(DIVIDEND_LOOKBACK_SESSIONS):
            if S.is_session(d):
                found = held_on(d.isoformat())
                total = sum((D(x["qty"], ZERO) for x in found), ZERO)
                if found and abs(total - abs(want)) <= Decimal("1e-6"):
                    return found
            d -= dt.timedelta(days=1)
        return []

    def _inferred_ratio(self, symbol: str) -> Decimal | None:
        """A split's ratio from the account's own quantity now over the book's (when the account holds nothing else
        of the symbol: no assignment shares in the ledger)."""
        if A.dec((self.state.get("shares", {}) or {}).get(symbol)):
            return None
        positions = self._read_positions()
        if positions is None:
            return None
        have = sum((A.dec(r.get("qty")) or ZERO for r in positions
                    if str(r.get("symbol") or "").upper() == symbol and str(r.get("asset_class")) == "us_equity"), ZERO)
        book = sum((lot.qty for lot in self._lots(symbol=symbol)), ZERO)
        if have <= 0 or book <= 0 or abs(have - book) <= SHARE_TOLERANCE:
            return None
        return have / book

    # ------------------------------------------------------------------ exports
    def _export(self, out: dict) -> None:
        rows = self.state.rows("SELECT * FROM eq_lots WHERE status='closed' AND substr(instance, -2)=? AND lid NOT IN "
                               "(SELECT lid FROM eq_exports) ORDER BY lid LIMIT ?", (REAL_SUFFIX, EXPORT_LIMIT))
        n = 0
        for r in rows:
            lot = Lot.of(r)
            trade = export_row(lot)
            try:
                self.families.add_forward(lot.family, "real", [trade])
            except Exception as exc:  # noqa: BLE001 - again next minute
                self.alert("warning", f"equity: a closed lot could not reach the forward record ({type(exc).__name__})")
                return
            self.state.execute("INSERT OR IGNORE INTO eq_exports(lid, exported_at) VALUES(?,?)", (lot.lid, self.clock()))
            n += 1
        if n:
            out["exported"] = n

    # ------------------------------------------------------------------ the stock paper proof (A8.7)
    def _proof_step(self, now: float, out: dict) -> None:
        if self.stock_proof is None:
            return
        try:
            if self.stock_proof.passed():
                return
        except Exception:  # noqa: BLE001
            return
        answer = self.stock_proof.step(now, market=self.market)
        if isinstance(answer, Mapping) and answer.get("status"):
            out["paper_proof_stock"] = answer.get("status")

    # ------------------------------------------------------------------ the band rules' record
    def _record_of(self, family: str, version: int, row: Mapping[str, Any] | None) -> Any:
        """The version's real record for the band rules (money's `bands.EquityRecord`): its closed ":r" lots in close
        order (net return on notional each), their net cash, the same-risk buy-and-hold over the same sessions
        (`_bh_pnl`), its whole sessions at Probe, its realized Probe net, its priced twins' gaps and EDM1's sigma."""
        key = instance_key(family, version)
        lots = [Lot.of(r) for r in self.state.rows(
            "SELECT * FROM eq_lots WHERE instance=? AND status='closed' ORDER BY closed_at, lid", (key,))]
        returns = tuple(float(lot.cash / lot.entry_notional) for lot in lots if lot.entry_notional > 0)
        pnl = sum((lot.cash for lot in lots), ZERO)
        since = (self.state.get("eq_band_since", {}) or {}).get(key) or {}
        probe_sessions = 0
        if since.get("band") in LIVE_BANDS and since.get("day"):
            probe_sessions = S.sessions_between(since["day"], S.ny_day(self.clock()).isoformat())
        twins = {}
        try:
            twins = self.families.twins() if hasattr(self.families, "twins") else {}
        except Exception:  # noqa: BLE001
            twins = {}
        gaps = []
        for lot in lots:
            twin = twins.get(f"eq:{lot.lid}") or {}
            if twin.get("status") == "priced" and isinstance(twin.get("gap_bp"), (int, float)) \
                    and math.isfinite(float(twin["gap_bp"])):
                gaps.append(float(twin["gap_bp"]))
        return B.EquityRecord(n=len(returns), returns=returns, pnl=pnl, bh_pnl=self._bh_pnl(lots),
                              probe_sessions=probe_sessions,
                              realized_net=sum((lot.cash for lot in lots if lot.probe), ZERO),
                              twin_gaps_bp=tuple(gaps),
                              validation_r_sd=(row or {}).get("validation_r_sd"))

    def _bh_pnl(self, lots: Sequence[Lot]) -> Decimal | None:
        """THE SAME-RISK BUY-AND-HOLD OVER THE SAME SESSIONS (goal item 4's scaling rule): per symbol, its lots' average
        exposure over their span (entry notional x sessions held, over the span's sessions) held from the close before
        the first entry to the close of the last exit, at the adjustment=all closes the book stored (`eq_bars`; total
        return). None when a close is missing (the rule then fails `beat_bh`)."""
        if not lots:
            return ZERO
        total = ZERO
        for symbol in sorted({lot.symbol for lot in lots}):
            mine = [lot for lot in lots if lot.symbol == symbol and lot.exit_day]
            if not mine:
                continue
            first = min(lot.opened_day for lot in mine)
            last = max(str(lot.exit_day) for lot in mine)
            try:
                before = S.previous_session(first).isoformat()
            except ValueError:
                return None
            span = max(1, S.sessions_between(before, last))
            exposure = sum((lot.entry_notional * max(1, S.sessions_between(lot.opened_day, str(lot.exit_day)))
                            for lot in mine), ZERO) / span
            closes = {r["day"]: A.dec(r["c"]) for r in self.state.rows(
                "SELECT day, c FROM eq_bars WHERE symbol=? AND adjustment='all' AND day IN (?, ?)", (symbol, before, last))}
            start, end = closes.get(before), closes.get(last)
            if not start or not end or start <= 0:
                return None
            total += exposure * (end / start - 1)
        return total


def export_row(lot: Lot) -> dict[str, Any]:
    """A closed lot as its forward-record row (league/equity/INTERFACES.md 5.2 "Exports"): `pnl` its net cash and
    `max_loss` its entry notional, so a generic reader's pnl / max_loss is the net return on notional."""
    notional = lot.entry_notional
    return {"id": f"eq-{lot.lid}", "version": lot.version, "day": lot.exit_day, "opened_day": lot.opened_day,
            "symbol": lot.symbol, "class": lot.klass, "lane": lot.lane, "pnl": float(lot.cash),
            "max_loss": float(notional), "notional": float(notional), "fees": float(lot.fees), "div": float(lot.div),
            "return": float(lot.cash / notional) if notional > 0 else 0.0,
            "hold_sessions": S.sessions_between(lot.opened_day, lot.exit_day) if lot.exit_day else 0,
            "entry_at": lot.entry_at, "exit_at": lot.exit_at, "probe": bool(lot.probe), "reason": lot.reason,
            "twin_key": f"eq:{lot.lid}"}


def _ctx_reason(reason: Any) -> str:
    """A lot's close reason as a program sees it: "program", "max_hold" or "house" (every other House reason)."""
    return reason if reason in ("program", "max_hold") else "house"


def _version_of(instance: str) -> int:
    try:
        return int(str(instance).rsplit("@", 1)[1].split(":", 1)[0])
    except (IndexError, ValueError):
        return 0


def _as_of_equal(old_raw: Mapping[str, tuple], old_all: Mapping[str, tuple], fresh_raw: Mapping[str, Mapping],
                 fresh_all: Mapping[str, Mapping], day: str) -> bool:
    """Whether two readings of the adjustment=all series give the same as-of prices at `day` (within a millionth)."""
    try:
        old_t = float(old_raw[day][3]) / float(old_all[day][3])
        new_t = float(fresh_raw[day]["c"]) / float(fresh_all[day]["c"])
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        return False
    for d, values in old_all.items():
        row = fresh_all.get(d)
        if row is None:
            return False
        for i, k in enumerate(("o", "h", "l", "c")):
            try:
                a, b = float(values[i]) * old_t, float(row[k]) * new_t
            except (TypeError, ValueError):
                return False
            if not math.isfinite(a) or not math.isfinite(b) or abs(a - b) > 1e-6 * max(abs(a), abs(b), 1.0):
                return False
    return True


__all__ = ["SCHEMA", "WORKING", "TERMINAL", "LOT_OPEN", "LOT_CLOSING", "LOT_CLOSED", "REAL_SUFFIX", "SHARE_TOLERANCE",
           "CLIENT_PREFIX", "client_id", "ProbeFigures", "probe_figures", "expected_shares_rows", "working_buys_worst",
           "orders_today", "invested", "EquityBook", "Lot", "Order", "Intent", "Instance", "instance_key", "order_body",
           "limit_for", "collar_for", "export_row", "qty_text", "HOUSE_REASONS", "EXIT_KINDS"]
