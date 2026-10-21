"""THE EVENT KIND'S PARENT SIDE (release R2): how the event lane's programs trade real money through E1's EquityBook.

Owner: R2. The book (league/equity/live.py) asks this module, and no other of league/events, for everything the event
kind needs: the rows of the constitution's `equity_money.event` (`settings`), which programs trade and at what band
(`bands`, read from the LANE's band table), the day's real-money picks of a program (`picks`), an entry's limit, size
target and open-risk weight (`limit_price`, `weight`, `sigma`), an exit's session (`exit_plan`), the eligible list the
gateway checks every event buy against (`eligible`, `publish`), the real fills it hands back to the lane
(`write_fills`), and its own tables in live.sqlite (`SCHEMA`). Plumbing: no identity hashes it. league/equity names no
module of league/events but through league/equity/kinds.py `BOOKS["event"]`.

THE RULES ARE THE FROZEN ONES: docs/prereg/PREREG-EVL-3.md section 2 (the owner's goal as re-set at 05:15Z Oct 19,
2026), with PREREG-EVL-1 sections 3, 5 and 8 and PREREG-EVL-2 for everything it does not change, and
docs/prereg/PREREG-EVL-4.md section 1.3 for that file's three programs:
- THE PROGRAMS are the lane's own `SEATING` rows of league/events/programs.py (`Program.can_seat`, the one gate:
  VERSION 2 of the nine seatable programs of PREREG-EVL-1 and -2, `REAL_VERSION`, and VERSION 1 of PREREG-EVL-4's three,
  their seating version; `seatable()`, `program_of()` by `BY_KEY`), in the tables' order (PREREG-EVL-1's four, then
  PREREG-EVL-2's five, then PREREG-EVL-4's three). Version 1 of PREREG-EVL-1's and -2's programs is a shadow record and
  NEVER trades, nor does any record or control: no real event order is ever for an intent of a version that cannot
  seat. A program is a pre-registered rule, never a swarm family and never code a program wrote.
- PREREG-EVL-4 (section 1.3): its rows' real-money events are the shadow rule over the rows STORED before the decision
  time, EXCLUDED on D and the F8K(D) skip read from those rows too (`rows_for`); and EVL-8K-REACT-ON and EVL-8K-READ-ON
  never buy for a filing knowable at or after 09:00 ET of D whose stored PROMPT-DOC verdict is `ok` with score >= 2, or
  not yet answered, at the decision time: EVL-8K-READ-O1's event at the next open (`NEXT_OPEN_GUARD`). The shadow keeps
  every such event.
- THE BANDS are the lane's, read by the lane's own reader (league/events/bands.py `bands(store)` over its store's
  `bands` table; the lane computes promotion at a passed look, Sized, demotion and retirement from its looks and the
  House's real fills, `write_fills` through `bands.record_fill`): LEARNING from birth (a seating version with no row
  is at learning), PROBE, SIZED, RETIRED (no real money). The book reads them at each session's first decision, and
  again at the close decision when the lane's `band_history` moved since (`band_mark`, release 1019f: a look the
  lane's screen wrote after the open trades from that session's close, PREREG-EVL-3's "the first decision after a
  passed look"); a store whose band table cannot be read trades nothing that decision (fail closed), one with no band
  table yet is every seating version at learning.
- A REAL-MONEY DECISION (PREREG-EVL-1 section 3) is the shadow rule over the same events and windows, which may in
  addition use only events STORED, and verdicts ANSWERED, before its decision time (`decided_at`, 09:15 ET or the
  close - 14 minutes): a filing or an article the recorder stored later, or a verdict answered later, is not read. It
  reads the lane's store READ-ONLY (`Lane`), never asks a verdict, never fetches a filing; the one thing it writes
  there is `real_fills`. Eligibility is the lane's universe row for the entry session made by the LIVE rule
  (`LIVE_ROWS`: release 1019b's second review; a row only the backfill rule made, at a re-decision, never trades); an
  issuer with no such row is not traded. One position per issuer per program: an issuer the program holds, or held
  within the last 5 sessions,
  real money's lots or the shadow's intents of earlier decisions alike, is skipped. Ranking when there is less room
  than events: by the program's own rank (verdict score; a reaction for the REACT rows; the purchase value for
  INS-BUY), higher first, then ADV.
- ROOM (PREREG-EVL-3 section 2): Sized programs first, then Probe, then learning; within a band the tables' order;
  within a program its own ranking. One name at one auction goes to the first program in that order that is GIVEN it:
  each program takes its own ranked picks whose name no earlier-given program was given, until its room is full
  (`allocate`, release 1019b's second review), passing over a pick the book's rules skip whatever the room (no whole
  share fits by price; the name is sold at the same auction: league/equity/live.py `_event_gate`). INSIDE SIZED AND
  INSIDE PROBE ROUND-ROBIN (the captain's A85, Oct 21, 2026): one pick given a program a pass, the tables' order inside
  a pass, at the decision (`allocate`) and at the send (`send_key`); learning keeps the tables' order.
- THE NEXT AUCTION'S RESERVATION (A85, recorded before the first Probe auction): ROOM's order holds inside one auction
  (A83 (2)(b)) and a lot sold in an auction still holds its cash there, so a LEARNING buy sizes on the cash, the
  invested room and the loss budget less what the other auction's live Probe and Sized programs will need,
  `reservation`: min(their room, the median of their real-money picks at their last `RESERVE_DECISIONS` decisions) x
  share(band) x E, and that x the median open-risk weight of their buys for the budget, less what this auction's event
  sales give back by then (league/equity/live.py `_event_reserve`). 0 while the other auction has no Probe or Sized
  program. No wall moves.
- SIZE: a target of the band's `position_share` x E (learning 0.02, Probe 0.05, Sized 0.10), E the account equity at
  the previous close, at the limit, `limit_ratio` x the previous SIP close (rounded down to the cent), in whole shares;
  when that rounds to none, one share when one share fits every wall (and, at learning, one share at the limit is at
  most `one_share_max.learning`, 5%, of E); else skipped (the shadow keeps the event). The book-wide 10% a name
  (`per_name_share`), the 100% book, the cash and the loss budget are `league.equity.sizing.size_entry`'s own caps (the
  book calls it; nothing here re-implements it). THE WALLS' EQUITY (release 1019f, the reading that trades less): the
  10% a name (the decision's skip and the send's caps) and the 100% book are judged on the LOWER of E and the
  account's current equity as the House last read it, since the gateway judges the current equity (a buy sized on a
  higher E met its final refusal there); the target and the one-share rule stay on E at the previous close. At most
  `max_open` positions a program (learning 8, Probe 6, Sized 8).
- THE DAY'S ORDERS (release 1019c): the kind's auction orders count against its own line, `max_orders_day` (150), never
  the old lanes' 60 (league/equity/live.py `_count_refusal`): an entry leaves room for its own exit and for the exit of
  every event lot not yet sold that day and of every event buy still working that is sold the same day, and at the
  House-wide line room for every equity exit beside the options book's; an exit is never stopped by a lane's line;
  both lines stay under the House-wide one.
- OPEN RISK (the goal's own rule, PREREG-EVL-1 section 8, PREREG-EVL-3 section 2): value x max(`open_risk.floor`,
  `open_risk.z` x sigma x sqrt(h)), sigma the daily return sd of the `sigma_sessions` sessions before entry (adjusted
  closes), h the sessions in the hold; `STRICT_WEIGHT` (the House's old 0.40) when sigma cannot be read, and for a lot
  held past its scheduled exit (an auction with no print).
- EXITS: every position exits at its program's scheduled auction (`exit_plan`): the CLOSE of its last session, or for
  PREREG-EVL-2's overnight rows the next session's OPEN, by a market-on-close (market-on-open) sale. THE FALLBACK
  LADDER when the auction printed none for it (PREREG-EVL-1 section 5): the next session's closing cross, again for up
  to `LADDER_CLOSES` sessions; then a day sale in the open window (the first SIP trade of the next session any venue
  prints) each session after; and once `ZERO_AFTER` sessions after the planned exit have closed with the lot still
  held, the loss budget counts it AT 0 (its whole value as lost) while its day sale goes on: every rung alarmed.

THE TABLES (`SCHEMA`, created in live.sqlite beside E1's by the book): `eq_event_programs`, the band of each seating
program as the book last read it from the lane (with since and why), one row each; `eq_event_intents`, ONE ROW PER
EVENT INTENT of the book (`eq_intents.iid`): which program and event, its band, the auction (`tif` opg | cls) and the
order type, the symbol and issuer, the rank, the previous close and the limit, sigma and the weight, the exit plan of a
buy, the ladder's rung of a sale, the lot it opened or sells; `eq_event_decisions`, one row a session and auction the
book decided (what it read and planned, counts only).

THE PROBE SIZE'S RECORD (release 1019f, the audit's capacity and probe lenses): a buy's side row keeps `target_usd`,
the dollars its band's target asked (`position_share` x E at the previous close, as `size_entry` was asked them), and
`binding`, which constraint cut it below that (`BINDINGS`: cash, budget, invested, name_wall, whole_shares; gateway
when the gateway's final refusal ended it; NULL when none did), written at each sizing of its send; the buy's row in
the lane's `real_fills` carries both (with venue when the venue filled less than the order asked), so the band label
"probe" is no longer the only record of a Probe event's size. Nothing here reads them; the band rules count as before.

Standard library only.
"""

from __future__ import annotations

import contextlib
import dataclasses
import datetime as dt
import gzip
import hashlib
import json
import math
import sqlite3
import statistics
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from ..equity import schedule as ES
from . import bands as BA
from . import calendar as C
from . import programs as P
from . import store as S
from . import verdicts as V

KIND = "event"
#: An event lot's `lane` (eq_lots.lane, eq_instances.lane): the event lane's, never "beta" or "equity".
LANE = "event"
#: An event BUY intent's tag starts so: "evl:<event id>" (the lot keeps it).
TAG = "evl"
#: The House's exit of an event lot at its scheduled auction (a house_exit intent's tag; the closed lot's reason).
EXIT_TAG = "evl_exit"
#: The fallback ladder's last rung: a day sale in the open window (no side row: the book's normal exit path sends it).
LATE_TAG = "evl_late"
#: PREREG-EVL-3 section 1: the version of PREREG-EVL-1's and -2's seatable programs that trades real money (their version
#: 1 never does). Not a gate since PREREG-EVL-4 (whose new ids seat at version 1): `Program.can_seat` is the one gate.
REAL_VERSION = 2
#: PREREG-EVL-4 section 1.3, NO REAL-MONEY TAKING FROM AN EARLIER ROW: in real money only, these programs never buy for a
#: filing knowable at or after 09:00 ET of D whose stored PROMPT-DOC verdict is `ok` with score >= 2, or is not yet
#: answered, at D's close decision time (EVL-8K-READ-O1's event at the next open, whose buy this row's sale there would
#: take by the sale gate).
NEXT_OPEN_GUARD = ("EVL-8K-REACT-ON", "EVL-8K-READ-ON")
#: PREREG-EVL-3 section 2's bands, and the ones that trade.
BANDS = ("learning", "probe", "sized", "retired")
LIVE_BANDS = ("learning", "probe", "sized")
DEFAULT_BAND = "learning"
#: ROOM: Sized programs first, then Probe, then learning.
PRIORITY = {"sized": 0, "probe": 1, "learning": 2}
#: THE BANDS AHEAD OF LEARNING (the captain's A85, Oct 21, 2026): inside each of them the auction's picks and its sends
#: go ROUND-ROBIN (one a program a pass, the tables' order inside a pass: `allocate`, `send_key`), and a learning buy
#: leaves the NEXT auction's programs of these bands their cash, invested room and loss budget (`reservation`).
PROBE_UP = ("sized", "probe")
#: A85: the decisions of its own entry auction whose real-money picks a Probe or Sized program's reservation reads (the
#: median of their counts), the latest first.
RESERVE_DECISIONS = 5
#: The weight of a lot whose sigma cannot be read, or held past its exit: the House's stock floor before this release.
STRICT_WEIGHT = Decimal("0.40")
#: THE FALLBACK LADDER (PREREG-EVL-1 section 5): a sale the scheduled auction did not fill goes at the closing cross of
#: each next session, this many in all; then a day sale in each next session's open window.
LADDER_CLOSES = 5
#: ... and a lot still held when this many sessions after its planned exit have closed is AT 0 for the loss budget
#: (PREREG-EVL-1 section 5; league/events/score.py `ZERO_AFTER`, the shadow's, held equal by a test).
ZERO_AFTER = 20
#: The sessions an issuer stays "held" after its lot closed (PREREG-EVL-1 section 5: one position per issuer per program).
ISSUER_GAP_SESSIONS = 5
#: The lane's store under the House's state root (release R1 keeps it there).
LANE_DIR = "events"
#: The lane's table of the House's real fills (PREREG-EVL-3: the lane computes Sized and demotion from it), one row per
#: (program, version, event, side), and its columns.
FILLS_TABLE = "real_fills"
FILL_COLUMNS = ("program", "version", "event", "side", "qty", "price", "fee", "filled_at", "band")
ZERO = Decimal(0)
CENT = Decimal("0.01")


def seatable() -> tuple[P.Program, ...]:
    """The programs real money trades (PREREG-EVL-3 section 1, PREREG-EVL-4 section 2): the lane's `programs.SEATING`
    (the versions that may ever trade, `Program.can_seat`: version 2 of the nine, version 1 of PREREG-EVL-4's three), in
    the tables' order; then (R3) the registered seatable births the lane's loader added after them, each at its own
    version 1 (league/events/programs.py `load_births`), in registration order. Read at each call."""
    return tuple(p for p in P.SEATING if p.can_seat)


def program_of(program: str, version: int) -> P.Program | None:
    """The seating version `version` of `program` (the lane's `programs.BY_KEY` row when it may seat,
    `Program.can_seat`); None for any version that cannot: version 1 of PREREG-EVL-1's and -2's programs, every record
    and control. A registered seatable birth (R3) seats at its version 1."""
    p = P.BY_KEY.get((str(program), int(version)))
    return p if p is not None and p.can_seat else None


def order_of(program: str) -> int:
    """The tables' order of a seatable program (PREREG-EVL-1's rows, then PREREG-EVL-2's, then PREREG-EVL-4's; then
    the births in registration order)."""
    for i, p in enumerate(seatable()):
        if p.id == program:
            return i
    return 10 ** 6


#: R3-SPEC section 4: "when room is short, PREREG-EVL-3's order (Sized > Probe > learning; table order) holds for the
#: PREREG programs; births come after them in registration order": a birth's ROOM tier, after every PREREG band's.
BIRTH_ROOM = 10


def room_key(program: str, band: str | None) -> tuple[int, int]:
    """ROOM's order (PREREG-EVL-3 section 2): Sized, then Probe, then learning; then the tables' order. A registered
    birth (R3) comes after every PREREG program, whatever the bands, in registration order (R3-SPEC section 4)."""
    found = next((p for p in seatable() if p.id == program), None)
    if found is not None and found.spec is not None:
        return (BIRTH_ROOM, order_of(program))
    return (PRIORITY.get(str(band), 9), order_of(program))


#: A85 WITH R3'S BIRTHS (release 1019f's integration; R3-SPEC section 4, `BIRTH_ROOM`): the ROOM tiers (`room_key`'s
#: first figure) that go ROUND-ROBIN inside an auction (`allocate`, `send_key`) and that the next auction's reservation
#: holds room for (`reserved_for`): the PREREG programs' Sized and Probe tiers only. A birth's tier is BIRTH_ROOM
#: whatever its band (it comes after every PREREG program), so a birth is never reserved for, never round-robins with a
#: PREREG program, and its buys leave the reservation as a PREREG learning program's do (`leaves_room`).
ROUND_ROBIN_TIERS = (PRIORITY["sized"], PRIORITY["probe"])


def reserved_for(program: str, band: str | None) -> bool:
    """A85: whether the next auction's reservation holds room for `program` at `band`: a PREREG program at Sized or
    Probe (its ROOM tier one of `ROUND_ROBIN_TIERS`); never a birth, whatever its band."""
    return room_key(program, band)[0] in ROUND_ROBIN_TIERS


def leaves_room(program: str, band: str | None) -> bool:
    """A85: whether a buy of `program` at `band` sizes less the next auction's reservation: a live band whose ROOM tier
    comes after the PREREG Probe tier, so a PREREG learning program's buy (A85's "a learning buy") and a birth's at any
    band (R3: after every PREREG program); never a PREREG Probe or Sized buy."""
    return str(band) in LIVE_BANDS and room_key(program, band)[0] > max(ROUND_ROBIN_TIERS)


def send_key(program: str, band: str | None, n: int) -> tuple[int, int, int]:
    """THE ORDER OF AN AUCTION'S BUYS AT THEIR SEND (league/equity/live.py `_event_send`), `n` the buy's place among its
    program's buys of the auction (0 its first): ROOM's tiers (`room_key`: Sized, then Probe, then learning, then the
    births whatever their bands, R3); inside the PREREG Sized tier and inside the PREREG Probe tier ROUND-ROBIN
    (`ROUND_ROBIN_TIERS`), every program's first buy before any program's second, the tables' order inside a pass (A85:
    the cash an auction's sends take goes one buy a program a pass, so the last Probe row in the tables is not left the
    cash the earlier rows did not take); learning, and the births, in the tables' order, each program's buys in its
    ranking (release 1019e's `room_key` order)."""
    tier, order = room_key(program, band)
    return (tier, max(0, int(n)) if tier in ROUND_ROBIN_TIERS else 0, order)


SCHEMA = """
CREATE TABLE IF NOT EXISTS eq_event_programs (
    program TEXT NOT NULL, version INTEGER NOT NULL, band TEXT NOT NULL, since TEXT, why TEXT, updated_at REAL NOT NULL,
    PRIMARY KEY (program, version));
CREATE TABLE IF NOT EXISTS eq_event_intents (
    iid INTEGER PRIMARY KEY, program TEXT NOT NULL, version INTEGER NOT NULL, event TEXT NOT NULL,
    side TEXT NOT NULL,                 -- buy | sell
    band TEXT,                          -- the program's band when the intent was made
    tif TEXT NOT NULL,                  -- opg | cls (an auction order); a sale's last rung has no row here
    otype TEXT NOT NULL,                -- limit (a buy) | market (a sale)
    symbol TEXT NOT NULL, cik TEXT, day TEXT NOT NULL, at TEXT NOT NULL,       -- the auction's session and point
    rank_key REAL, adv20 REAL, prev_close TEXT, limit_px TEXT, sigma REAL, hold INTEGER, weight TEXT NOT NULL,
    exit_day TEXT, exit_at TEXT,        -- a buy's exit plan
    lid INTEGER, rung INTEGER NOT NULL DEFAULT 0,                              -- a sale's lot and its ladder rung
    decided_at TEXT NOT NULL, why TEXT, created_at REAL NOT NULL,
    target_usd TEXT, binding TEXT,      -- a buy's band target (Decimal dollars) and what cut it (release 1019f)
    sized_usd TEXT);                    -- ... and the dollars its send asked: the shares sent x the limit (release 1019f)
CREATE INDEX IF NOT EXISTS eq_event_intents_lid ON eq_event_intents(lid);
CREATE TABLE IF NOT EXISTS eq_event_decisions (
    day TEXT NOT NULL, at TEXT NOT NULL, decided_at TEXT NOT NULL, status TEXT NOT NULL, summary TEXT NOT NULL,
    created_at REAL NOT NULL, PRIMARY KEY (day, at));
"""
#: THE COLUMNS ADDED TO THE BOOK'S TABLES AFTER THEIR FIRST RELEASE, each by its own statement, run by
#: league/equity/live.py `EquityBook._adapter` after `SCHEMA` where the table lacks the column (PRAGMA table_info, read
#: afresh; another process's first open adding it between the look and the ALTER is read as done), so a state from
#: before them gains them in place and every older row reads NULL. Release 1019f: an event buy's band target in Decimal
#: dollars (`target_usd`) and the constraint that cut it below that (`binding`, `BINDINGS`), written at its sizing and,
#: for the gateway's final refusal, at its end (the module docstring, "THE PROBE SIZE'S RECORD").
SCHEMA_COLUMNS = {"eq_event_intents": {"target_usd": "ALTER TABLE eq_event_intents ADD COLUMN target_usd TEXT",
                                       "binding": "ALTER TABLE eq_event_intents ADD COLUMN binding TEXT",
                                       "sized_usd": "ALTER TABLE eq_event_intents ADD COLUMN sized_usd TEXT"}}
#: What may cut a real event buy below its band's target (league/events/bands.py `BINDINGS`, the lane's own list).
BINDINGS = BA.BINDINGS
#: `league.equity.sizing.size_entry`'s binding rule (`Sized.binding`) as the record names it (`binding_of`): the
#: name's book-wide 10% (`instrument`) and the program's own share of it (`sleeve_cap`) are the NAME WALL; the program's
#: free cash (`sleeve_cash`, the House-wide figure for an event program) and the House-wide cash, or cash below zero, are
#: CASH; the 100% book is INVESTED; the loss budget at the lot's weight is BUDGET.
SIZING_BINDINGS = {"instrument": "name_wall", "sleeve_cap": "name_wall", "sleeve_cash": "cash", "cash": "cash",
                   "cash_negative": "cash", "invested": "invested", "budget": "budget"}


def binding_of(sized: str | None) -> str | None:
    """The record's name (`BINDINGS`) for `size_entry`'s binding rule `sized`; None for one that is no cap of the
    list (`intent`: no cap cut the dollars; `short_held`, `min_order`: refusals the intent's why names)."""
    return SIZING_BINDINGS.get(str(sized or ""))


# ----------------------------------------------------------------------------------------------------------- settings
@dataclasses.dataclass(frozen=True)
class Settings:
    """`equity_money.event` as the book reads it (the constitution's comment under the table)."""

    enabled: bool
    shares: Mapping[str, Decimal]
    max_opens: Mapping[str, int]
    one_share_max: Mapping[str, Decimal]
    per_name: Decimal
    limit_ratio: Decimal
    risk_floor: Decimal
    risk_z: Decimal
    sigma_sessions: int
    offsets: Mapping[str, int]
    #: THE EVENT KIND'S OWN DAY ORDER COUNT (`event.max_orders_day`, release 1019c): its auction orders of a day count
    #: against this line, never the old lanes' 60 (league/equity/live.py `_count_refusal`). 0 when unread: no entry.
    max_orders_day: int = 0

    def share(self, band: str) -> Decimal:
        return Decimal(self.shares.get(str(band), ZERO))

    def max_open(self, band: str) -> int:
        return int(self.max_opens.get(str(band), 0))

    def one_share_cap(self, band: str) -> Decimal | None:
        """The band's one-share rule's own cap (a share of E: one share at the limit at most this), None for none."""
        cap = self.one_share_max.get(str(band))
        return None if cap is None else Decimal(cap)


#: What a table with no readable event block is read as: OFF, no share (fail closed: nothing opens on rows nobody reads).
FALLBACK = Settings(False, {}, {}, {}, ZERO, Decimal(1), Decimal(1), Decimal("1.65"), 60, dict(ES.EVENT_DEFAULTS))


def settings(constitution: Mapping[str, Any] | None = None) -> Settings:
    """THE EVENT ROW, `equity_money.event` of `constitution` (None: the one in force), read here so that
    league/live/money.py (inside the options execution fingerprint) never has to learn it. `FALLBACK` when the block is
    absent, a row cannot be read, or the table is outside its bounds (`equity_money_problems`)."""
    from ..constitution import CONSTITUTION, EVENT_ORDER_OFFSETS, equity_money_problems

    rules = CONSTITUTION if constitution is None else constitution
    try:
        if equity_money_problems(dict(rules)):
            return FALLBACK
        e = rules["equity_money"]["event"]
        return Settings(
            enabled=e["enabled"] is True,
            shares={band: Decimal(str(e["position_share"][band])) for band in LIVE_BANDS},
            max_opens={band: int(e["max_open"][band]) for band in LIVE_BANDS},
            one_share_max={band: Decimal(str(v)) for band, v in dict(e["one_share_max"]).items()},
            per_name=Decimal(str(e["per_name_share"])), limit_ratio=Decimal(str(e["limit_ratio"])),
            risk_floor=Decimal(str(e["open_risk"]["floor"])), risk_z=Decimal(str(e["open_risk"]["z"])),
            sigma_sessions=int(e["open_risk"]["sigma_sessions"]),
            offsets={name: int(e["order_path"][name]) for name in EVENT_ORDER_OFFSETS},
            max_orders_day=int(e["max_orders_day"]))
    except (KeyError, TypeError, ValueError, InvalidOperation):
        return FALLBACK


# ----------------------------------------------------------------------------------------------------------- the lane
class Lane:
    """THE LANE'S STORE, READ-ONLY (`<root>/events/events.sqlite`, opened `mode=ro`): the `store` every function of
    league/events/programs.py, calendar.py and verdicts.py reads through `.db`, and the documents. Never written here
    (the real fills go through `write_fills`, a connection of their own)."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.root = self.path.parent
        self.db = sqlite3.connect(f"{self.path.resolve().as_uri()}?mode=ro", uri=True, timeout=5.0)
        self.db.row_factory = sqlite3.Row

    def close(self) -> None:
        self.db.close()

    def __enter__(self) -> "Lane":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def meta(self, key: str) -> str | None:
        row = self.db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return None if row is None else str(row[0])

    def get_document(self, digest: str) -> bytes:
        row = self.db.execute("SELECT path FROM documents WHERE sha=?", (digest,)).fetchone()
        if row is None:
            raise KeyError(digest)
        with gzip.open(self.root / row["path"], "rb") as src:
            data = src.read()
        if hashlib.sha256(data).hexdigest() != digest:
            raise RuntimeError(f"document {digest} does not match its digest")
        return data


def lane_path(root: str | Path) -> Path:
    return Path(root) / LANE_DIR / S.DB_NAME


def open_lane(root: str | Path | None) -> Lane | None:
    """The lane's store under `root`, read-only, or None when there is none (no lane on this House: nothing to decide)."""
    if root is None:
        return None
    path = lane_path(root)
    if not path.is_file():
        return None
    try:
        lane = Lane(path)
        lane.db.execute("SELECT 1 FROM sessions LIMIT 1")
    except sqlite3.Error:
        return None
    P.load_births(lane)     # (R3: the registered births, after every PREREG program; none when the store has none)
    return lane


def decided(lane: Lane, day: dt.date, at: str) -> bool:
    """Whether the lane's own (shadow) decision of `day` at `at` ("open" | "close") has run: its receipt is finished
    `ok` or `pending` (on verdicts). A decision CUT by the lane's own time bound is finished but not whole (its universe
    rows are part written; release 1019b's review): the book goes on waiting for it. The book's real-money decision
    waits a few minutes (its universe rows are then written), never longer."""
    job = f"decide-{at}:{day.isoformat()}"
    return lane.db.execute("SELECT 1 FROM receipts WHERE job=? AND finished_at IS NOT NULL AND status IN ('ok', 'pending') "
                           "LIMIT 1", (job,)).fetchone() is not None


#: THE LIVE RULE'S ELIGIBLE ROWS of an entry session (PREREG-EVL-1 section 2: a live decision reads Alpaca's
#: `status=active` and `tradable: true`): the universe rows whose result in the lane's `eligibility` is the live rule's
#: and eligible (league/events/store.py; release 1019b's second review). A row only the backfill rule made (the hourly
#: re-decision of a session, a backfill) is never real money's: no pick, no name on the gateway's list.
LIVE_ROWS = ("SELECT u.* FROM universe u JOIN eligibility e ON e.day=u.day AND e.cik=u.cik AND e.symbol=u.symbol "
             "WHERE u.day=? AND e.rule='live' AND e.eligible=1")


def eligible(lane: Lane, day: dt.date) -> list[str]:
    """THE ELIGIBLE LIST of entry session `day`: the symbols of the live rule's eligible universe rows the lane wrote for
    it (`LIVE_ROWS`; PREREG-EVL-1 section 2, the issuers with events), sorted. The gateway admits an event buy only for
    a name on it."""
    return sorted({str(r["symbol"]).upper() for r in lane.db.execute(LIVE_ROWS, (day.isoformat(),))})


def universe_rows(lane: Lane, day: dt.date) -> dict[str, dict[str, Any]]:
    """{cik: the live rule's eligible universe row of entry session `day`} (`LIVE_ROWS`; the highest ADV when a CIK has
    two)."""
    out: dict[str, dict[str, Any]] = {}
    for r in lane.db.execute(LIVE_ROWS, (day.isoformat(),)):
        row = dict(r)
        have = out.get(str(row["cik"]))
        if have is None or float(row.get("adv20") or 0) > float(have.get("adv20") or 0):
            out[str(row["cik"])] = row
    return out


# ----------------------------------------------------------------------------------------------------------- the bands
@dataclasses.dataclass(frozen=True)
class Band:
    """One seating version's band as the lane's table says it (PREREG-EVL-3 section 2): `band` (one of `BANDS`),
    `since` (the lane's), why."""

    program: str
    version: int
    band: str
    since: str | None = None
    why: str = ""

    @property
    def live(self) -> bool:
        return self.band in LIVE_BANDS


def lane_bands(lane: Lane | None) -> dict[tuple[str, int], dict[str, Any]] | None:
    """THE LANE'S BANDS AS THE LANE READS THEM: league/events/bands.py `bands(store)` ({(program, version): band} for
    every seating version, no row = learning), each with its row's since and why beside ({band, since, why, row}, `row`
    whether the lane's table holds one); {} when there is no lane or its store holds no band table yet (a store from
    before PREREG-EVL-3: every seating version is then at learning); None when the table is there and cannot be read
    (no real event money this decision)."""
    if lane is None:
        return {}
    try:
        tables = {r[0] for r in lane.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "bands" not in tables:
            return {}
        rows = {(str(r["program"]), int(r["version"])): dict(r) for r in lane.db.execute("SELECT * FROM bands")}
        out: dict[tuple[str, int], dict[str, Any]] = {}
        for (program, version), band in dict(BA.bands(lane)).items():
            key = (str(program), int(version))
            row = rows.get(key)
            out[key] = {"band": str(band), "since": None if row is None else row.get("since"),
                        "why": None if row is None else row.get("why"), "row": row is not None}
        return out
    except (sqlite3.Error, KeyError, TypeError, ValueError):
        return None


def bands(lane: Lane | None, s: Settings | None = None) -> list[Band] | None:
    """Every seating version's band at a decision, in the tables' order (`lane_bands`; a program with no row is at
    learning, `DEFAULT_BAND`; a band the rules do not name trades nothing, read as retired and said so). None when the
    lane's band table cannot be read."""
    if lane is not None:
        P.load_births(lane)     # (R3: a birth registered since the last decision seats from this one, at learning)
    table = lane_bands(lane)
    if table is None:
        return None
    out = []
    for program in seatable():
        row = table.get((program.id, int(program.version)))
        if row is None or not row.get("row"):
            out.append(Band(program.id, int(program.version), str((row or {}).get("band") or DEFAULT_BAND), None,
                            "no row in the lane's band table: learning from birth (PREREG-EVL-3 section 2)"))
            continue
        band = str(row.get("band") or "")
        why = str(row.get("why") or f"the lane's band table says {band}")
        if band not in BANDS:
            band, why = "retired", f"the lane's band table names {row.get('band')!r}, no band of PREREG-EVL-3: no real money"
        out.append(Band(program.id, int(program.version), band, row.get("since"), why[:400]))
    return out


def band_mark(lane: Lane | None) -> int | None:
    """THE LANE'S BAND MARK (release 1019f): the newest `band_history` id. Every band move the lane writes raises it
    (league/events/bands.py `set_band`: a look's Probe or retirement, written by the screen whenever it runs, the night's
    review), so the book reads the bands again at a close decision when it differs from the mark of the morning's sync
    (league/equity/live.py `_event_decide`). 0 with no lane, no such table or no row; None when the table is there and
    cannot be read (the book then reads the bands again, and `bands` says whether they can be read)."""
    if lane is None:
        return 0
    try:
        tables = {r[0] for r in lane.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "band_history" not in tables:
            return 0
        row = lane.db.execute("SELECT max(id) FROM band_history").fetchone()
        return int(row[0] or 0)
    except (sqlite3.Error, TypeError, ValueError):
        return None


def sessions_back(day: dt.date, n: int) -> dt.date:
    """The session `n` sessions before `day` (the book's NYSE calendar)."""
    d = day
    for _ in range(int(n)):
        d = ES.previous_session(d)
    return d


# ----------------------------------------------------------------------------------------------------------- the fills
class FillWriter:
    """The lane's store opened for the book's one write, `real_fills`, in the shape league/events/bands.py
    `record_fill` takes a store (`.db`, `.tx()`): an EXISTING file only (never created here, nor any table: the lane's
    store is made by the lane or its migration; `write_fills` runs the lane's own `store.migrate_fills` on it, which
    only adds release 1019f's nullable columns to an existing table), with a short busy timeout (the House's minute
    never waits long on the lane's own writer)."""

    def __init__(self, path: str | Path, *, timeout: float = 5.0):
        self.path = Path(path)
        self.db = sqlite3.connect(f"{self.path.resolve().as_uri()}?mode=rw", uri=True, timeout=timeout,
                                  isolation_level=None)
        self.db.row_factory = sqlite3.Row

    def close(self) -> None:
        self.db.close()

    @contextlib.contextmanager
    def tx(self) -> Any:
        """One transaction (BEGIN IMMEDIATE ... COMMIT, rolled back on any exception), as league/events/store.py's."""
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield self.db
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        self.db.execute("COMMIT")


def write_fills(root: str | Path | None, rows: Sequence[Mapping[str, Any]]) -> int | None:
    """THE REAL FILLS HANDED BACK TO THE LANE (PREREG-EVL-3: the lane computes Sized and demotion from them): each of
    `rows` ({program, version, event, side, qty, price, fee, filled_at, band}, and release 1019f's `target_usd`,
    `binding` and `sized_usd` for a buy) written into the lane's `real_fills` by the lane's own league/events/bands.py
    `record_fill`: ONE ROW PER (program, version, event, side), idempotent; a write again changes only its fee (the
    broker's posted fee). A store whose `real_fills` predates release 1019f's columns gains them first (league/events/store.py
    `migrate_fills`, the lane's own additive migration), so no buy row is written without its target. Returns how many
    rows were new or changed; None when there is no lane store or it holds no `real_fills` table yet (nothing written:
    the book writes them once it does). Raises `sqlite3.Error` when the store cannot be written (asked again next
    minute)."""
    if root is None:
        return None
    path = lane_path(root)
    if not path.is_file():
        return None
    store = FillWriter(path)
    try:
        columns = {r[1] for r in store.db.execute(f"PRAGMA table_info({FILLS_TABLE})")}
        if not columns:
            return None
        missing = [c for c in FILL_COLUMNS if c not in columns]
        if missing:
            raise sqlite3.OperationalError(f"{FILLS_TABLE} lacks {', '.join(missing)}")
        if any(c not in columns for c in S.FILL_COLUMNS_DDL):
            S.migrate_fills(store.db)
        changed = 0
        for row in rows:
            target, sent = row.get("target_usd"), row.get("sized_usd")
            changed += bool(BA.record_fill(store, program=str(row["program"]), version=int(row["version"]),
                                           event=str(row["event"]), side=str(row["side"]), qty=float(row["qty"]),
                                           price=float(row["price"]), fee=float(row["fee"] or 0),
                                           filled_at=str(row["filled_at"]), band=str(row["band"]),
                                           target_usd=None if target is None else float(target),
                                           binding=row.get("binding"),
                                           sized_usd=None if sent is None else float(sent)))
        return changed
    finally:
        store.close()


# ----------------------------------------------------------------------------------------------------------- the picks
@dataclasses.dataclass(frozen=True)
class Pick:
    """One real-money pick of a program at one auction: its event, symbol, issuer, rank, ADV and previous close (the
    universe row of the entry session)."""

    program: str
    version: int
    event: str
    symbol: str
    cik: str
    rank: float | None
    adv20: float
    prev_close: Decimal
    knowable_at: str


def _stored_before(row: Mapping[str, Any], decided_at: dt.datetime, lane: Any = None) -> bool:
    """PREREG-EVL-1 section 3: a real-money decision reads only an event STORED before its decision time. A news article
    is stored whole when it is read (`received_at`); a FILING is stored when its documents are fetched (the latest
    `documents.stored_at` of its `raw_sha` and `text_sha`, never before its listing time `received_at`), as
    run.py `_first_fetched` reads it (release 1019b's third review: `received_at` is a filing's LISTING time, and its
    content (the Form 4's transactions, the 8-K's items and text) comes only at the fetch). Fail closed: a filing that
    names a document whose time cannot be read is not stored before; a filing row naming no document at all (none the
    House's record pass writes: every fetched filing keeps its raw document) is read by its `received_at`."""
    try:
        when = S.parse_iso(row["received_at"])
    except (KeyError, TypeError, ValueError):
        return False
    shas = [str(row[k]) for k in ("raw_sha", "text_sha") if row.get(k)] if row.get("accession") else []
    if shas:
        if lane is None:
            return False
        try:
            for sha in shas:
                doc = lane.db.execute("SELECT stored_at FROM documents WHERE sha=?", (sha,)).fetchone()
                if doc is None or not doc["stored_at"]:
                    return False
                when = max(when, S.parse_iso(str(doc["stored_at"])))
        except (sqlite3.Error, TypeError, ValueError, KeyError, IndexError):
            return False
    return when <= decided_at


def _answered(lane: Lane, event: str, prompt: Any, decided_at: dt.datetime) -> Mapping[str, Any] | None:
    """The stored verdict of `event` when it is `ok` and was ANSWERED before the decision time (PREREG-EVL-1 section 3),
    else None."""
    got = V.stored(lane, event, prompt)
    if not got or got.get("status") != "ok" or not got.get("answered_at"):
        return None
    try:
        return got if S.parse_iso(got["answered_at"]) <= decided_at else None
    except ValueError:
        return None


def rows_4(lane: Lane, day: dt.date, decided_at: dt.datetime) -> dict[str, list[Mapping[str, Any]]]:
    """PREREG-EVL-4's rows for a real-money decision of entry session `day` (its section 1.3: "the shadow rule over the
    events STORED ... before D's close decision time. It applies EXCLUDED and the F8K(D) skip to the filings and
    articles stored before that time"): every fetched 8-K of D's close window, PREREG-EVL-2's day-news window and PM(D),
    each STORED before `decided_at` (`_stored_before`: a filing when its documents were fetched, an article when it was
    read), each article with the CIK of the live rule's eligible universe row whose symbol it names, read with NO
    registration floor; then EXCLUDED on D and the F8K(D) skip applied (`programs.close_rows_4`). {"8k-react", "8k-day",
    "news-pm": rows}; `rows_for` keeps a program's events (knowable after its registration)."""
    lo, hi = P.close_window(lane, day)
    all8k = [r for r in P.filings_window(lane, "8-K", lo, hi) if _stored_before(r, decided_at, lane)]
    uni = universe_rows(lane, day)
    by_symbol = {str(r["symbol"]).upper(): str(cik) for cik, r in uni.items()}

    def with_cik(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
        return [dict(r) | {"cik": by_symbol.get(str(r.get("symbol") or "").upper())} for r in rows
                if _stored_before(r, decided_at, lane)]

    def symbol_of(cik: str) -> str | None:
        row = uni.get(str(cik))
        return None if row is None else row["symbol"]
    return P.close_rows_4(all8k, with_cik(P.news_rows(lane, *P.day_news_window(lane, day))),
                          with_cik(P.news_rows(lane, *P.news_window(lane, day))), symbol_of)


def rows_for(lane: Lane, program: P.Program, day: dt.date, decided_at: dt.datetime) -> list[Mapping[str, Any]]:
    """The events `program`'s decision of entry session `day` reads (league/events/run.py's windows), STORED before
    `decided_at` and knowable after the program's own registration time. News rows carry their eligible issuer's CIK
    (the universe row whose symbol is the article's). PREREG-EVL-4's rows: `rows_4`. Every family a seatable program can
    have reads its rows here as the lane's decision reads them (release 1019e's review: R3's `ins` family, Form 4
    cluster triggers, is a record only (A89): its cluster reads Form 4s that may be stored after the decision, so the
    book reads no rows for it and a seatable `ins` birth is refused by the births' grammar)."""
    family = program.family
    if program.entry_at == "close" and family in P.CLOSE_FAMILIES_4:
        since = program.registered_at
        return [r for r in rows_4(lane, day, decided_at)[family] if S.parse_iso(r["knowable_at"]) > since]
    if program.entry_at == "open":
        lo, hi = P.open_window(lane, day)
        if family in ("ern", "8k"):
            rows = P.filings_in(lane, "8-K", lo, hi)
        elif family == "ins-buy":
            rows = P.ins_buys(lane, lo, hi)
        elif family == "news":
            rows = P.news_in(lane, *P.news_window(lane, day))
        else:       # (never silent: that program plans nothing this auction, and the book records why)
            raise LookupError(f"the book reads no rows for the {family} family at the open")
    else:
        if family == "ern-react":
            rows = [r for r in P.filings_in(lane, "8-K", *P.close_window(lane, day)) if "2.02" in P.items_of(r)]
        elif family in ("news-day", "news-react"):
            rows = P.news_in(lane, *P.day_news_window(lane, day))
        else:
            raise LookupError(f"the book reads no rows for the {family} family at the close")
    if family in P.NEWS_FAMILIES:
        by_symbol = {str(r["symbol"]).upper(): str(r["cik"]) for r in universe_rows(lane, day).values()}
        rows = [dict(r) | {"cik": by_symbol.get(str(r.get("symbol") or "").upper())} for r in rows]
    since = program.registered_at
    return [r for r in rows if _stored_before(r, decided_at, lane) and S.parse_iso(r["knowable_at"]) > since]


def held_recently(lane: Lane, program: P.Program, cik: str, day: dt.date) -> bool:
    """PREREG-EVL-1 section 5's ONE POSITION PER ISSUER PER PROGRAM as the shadow keeps it, for a real-money decision of
    session `day`: an intent of the program on the issuer from an EARLIER decision (entered before `day`, not skipped)
    that exits within the last `ISSUER_GAP_SESSIONS` sessions or later. The lane's own decision of `day`, which the
    book waits for, has already written today's intents: they are this same decision's picks, never a holding (the
    shadow's `programs._held_recently` reads them as one, rightly for the shadow, which asks before it writes)."""
    back = C.previous(lane, day, ISSUER_GAP_SESSIONS)
    since = back[0].day if back else day
    row = lane.db.execute("SELECT 1 FROM intents WHERE program=? AND version=? AND cik=? AND status NOT LIKE 'skipped%' "
                          "AND exit_day>=? AND entry_day<? LIMIT 1",
                          (program.id, program.version, str(cik), since.isoformat(), day.isoformat())).fetchone()
    return row is not None


def next_open_event(lane: Lane, row: Mapping[str, Any], session: C.Session | None, decided_at: dt.datetime) -> bool:
    """PREREG-EVL-4 section 1.3 (NO REAL-MONEY TAKING FROM AN EARLIER ROW), for `NEXT_OPEN_GUARD`'s programs: True when
    real money does NOT buy for this filing, being EVL-8K-READ-O1's event at the next open: knowable at or after 09:00 ET
    of D (`session`, D) and its stored PROMPT-DOC verdict `ok` with score >= 2, or not yet answered at `decided_at` (no
    stored answer, or one answered after it; a filing whose TEXT gets no verdict is never answered: the reading that
    trades less). A filing knowable before 09:00 ET of D is EVL-8K-READ-O1's at D's open, whose sale at D's close the
    sale gate already keeps this buy out of; an answer that is not `ok` (unparsed, refused) or scores under 2 leaves the
    buy. Unreadable inputs read as barred (fail closed)."""
    if session is None:
        return True
    try:
        knowable = S.parse_iso(str(row["knowable_at"]))
        accession = str(row["accession"])
    except (KeyError, TypeError, ValueError):
        return True
    if knowable < session.open_cutoff:
        return False
    got = V.stored(lane, f"8k:{accession}", V.PROMPTS["doc"])
    if not got or not got.get("answered_at"):
        return True
    try:
        if S.parse_iso(str(got["answered_at"])) > decided_at:
            return True
        score = None if got.get("score") is None else int(got["score"])
    except (TypeError, ValueError):
        return True
    return got.get("status") == "ok" and score is not None and score >= P.READ_MIN_SCORE


def picks(lane: Lane, program: P.Program, day: dt.date, *, decided_at: dt.datetime,
          reaction: Callable[[Mapping[str, Any], Mapping[str, Any]], float | None] | None = None,
          held: Callable[[str], bool] | None = None) -> list[Pick]:
    """THE REAL-MONEY PICKS of `program` for entry session `day` (the module docstring): the shadow rule
    (league/events/programs.py `select`) over the events stored before `decided_at`, with the verdicts answered before
    it; one per issuer (the earliest knowable, after `select`'s own order for the news rows); an issuer the program holds
    or held within `ISSUER_GAP_SESSIONS` sessions (the shadow's intents of earlier decisions in the lane,
    `held_recently`, and `held(cik)` for real money's own lots and buys) skipped; ranked higher first, then ADV.
    `reaction(row, universe_row)`: the REACT rows' ratio (the book's reading of the SIP bars), None when a price is
    missing. For `NEXT_OPEN_GUARD`'s programs (PREREG-EVL-4 section 1.3) the issuer's one event is not bought when it is
    EVL-8K-READ-O1's at the next open (`next_open_event`); no later filing of the issuer stands in for it."""
    uni = universe_rows(lane, day)
    news = program.family in P.NEWS_FAMILIES
    guard = program.id in NEXT_OPEN_GUARD
    session = C.session(lane, day) if guard else None

    def verdict(row: Mapping[str, Any]) -> int | None:
        if news:
            got = _answered(lane, f"news:{row['id']}", V.PROMPTS["news"], decided_at)
        else:
            got = _answered(lane, f"8k:{row['accession']}", V.PROMPTS["doc"], decided_at)
        return None if got is None else got.get("score")

    def guidance(row: Mapping[str, Any]) -> str | None:
        got = _answered(lane, f"8k:{row['accession']}", V.PROMPTS["doc"], decided_at) if row.get("accession") else None
        return None if got is None else got.get("guidance")

    chosen = P.select(program, rows_for(lane, program, day, decided_at), eligible=lambda cik: uni.get(str(cik)),
                      verdict=verdict, reaction=reaction, guidance=guidance)
    out: list[Pick] = []
    taken: set[str] = set()
    for c in sorted(chosen, key=lambda c: (c.knowable_at, c.event)):
        if c.cik in taken:
            continue
        taken.add(c.cik)
        if guard and next_open_event(lane, c.row, session, decided_at):
            continue        # (PREREG-EVL-4 section 1.3: the shadow keeps the event)
        if held_recently(lane, program, c.cik, day) or (held is not None and held(str(c.cik))):
            continue
        row = uni[str(c.cik)]
        try:
            prev = Decimal(str(row["prev_close"]))
        except (InvalidOperation, ValueError, TypeError):
            continue
        if not prev.is_finite() or prev <= 0:
            continue
        out.append(Pick(program.id, program.version, c.event, str(c.symbol).upper(), str(c.cik), c.rank_key,
                        float(row.get("adv20") or 0.0), prev, S.iso(c.knowable_at)))
    return sorted(out, key=lambda p: (-(p.rank if p.rank is not None else float("-inf")), -p.adv20, p.event))


def allocate(picks_by_program: Mapping[str, Sequence[Pick]], rooms: Mapping[str, int],
             band_of: Mapping[str, str] | None = None, skip: Callable[[str, Pick], str | None] | None = None
             ) -> tuple[dict[str, list[Pick]], dict[str, dict[str, int]]]:
    """ROOM AT ONE AUCTION (PREREG-EVL-3 section 2) WITH ONE NAME AT ONE AUCTION (PREREG-EVL-1 section 8, PREREG-EVL-2
    section 3), release 1019b's second review: the bands in ROOM's order (Sized, then Probe, then learning, `band_of`
    {program: band}), and each program takes ITS OWN ranked picks, in its order, until its room (`rooms` {program: open
    positions it may still take}) is full, passing over a name an EARLIER-GIVEN program was given at this auction and a
    pick `skip(program, pick)` names a reason for (the real-money rules that skip an event whatever the room:
    `EquityBook._event_gate`). Inside a band the programs go in the tables' order; inside the PREREG Sized tier and the
    PREREG Probe tier (`ROUND_ROBIN_TIERS`, `room_key`'s first figure) ROUND-ROBIN (the captain's A85): one pick GIVEN a
    program a pass, the tables' order inside a pass, pass after pass until every one of them is full or out of picks, so
    no Probe row is given a second name before every later Probe row has had its first; learning as before, each
    program in turn to its room; then the births (R3's `BIRTH_ROOM`, after every PREREG program whatever their bands), in
    registration order, each in turn to its room, as release 1019e gave them. Only a name GIVEN to a
    program is taken: a name a program wanted but had no room for (or skipped) goes on to the next program that wants
    it, which then moves on to its next picks. Returns ({program: the picks given, in its order}, {program: {why passed
    over: how many}}), both in ROOM's order."""
    bands_ = dict(band_of or {})
    taken: set[str] = set()
    order = sorted(picks_by_program, key=lambda p: room_key(p, bands_.get(p, DEFAULT_BAND)))
    given: dict[str, list[Pick]] = {program: [] for program in order}
    passed: dict[str, dict[str, int]] = {program: {} for program in order}
    cursor = {program: 0 for program in order}
    room = {program: max(0, int(rooms.get(program, 0))) for program in order}

    def open_(program: str) -> bool:
        return len(given[program]) < room[program] and cursor[program] < len(picks_by_program[program])

    def give_one(program: str) -> None:
        """The program's next pick GIVEN (its passed-over picks counted on the way), or its list run out."""
        picks_, why = picks_by_program[program], passed[program]
        while cursor[program] < len(picks_):
            pick = picks_[cursor[program]]
            cursor[program] += 1
            reason = "name_given" if pick.symbol in taken else (skip(program, pick) if skip is not None else None)
            if reason:
                why[reason] = why.get(reason, 0) + 1
                continue
            given[program].append(pick)
            taken.add(pick.symbol)
            return

    def tier(program: str) -> int:
        return room_key(program, bands_.get(program, DEFAULT_BAND))[0]

    i = 0
    while i < len(order):
        rank = tier(order[i])
        group = []
        while i < len(order) and tier(order[i]) == rank:   # (one ROOM tier: a birth's is BIRTH_ROOM, whatever its band)
            group.append(order[i])
            i += 1
        if rank in ROUND_ROBIN_TIERS:
            live = [program for program in group if open_(program)]
            while live:                     # (one pass: each program in the tables' order is given at most one pick)
                for program in live:
                    give_one(program)
                live = [program for program in live if open_(program)]
        else:
            for program in group:
                while open_(program):
                    give_one(program)
    return given, passed


def one_name_an_auction(picks_by_program: Mapping[str, Sequence[Pick]],
                        band_of: Mapping[str, str] | None = None) -> dict[str, list[Pick]]:
    """ONE NAME AT ONE AUCTION (PREREG-EVL-1 section 8; PREREG-EVL-3 section 2's ROOM) with no room limit: when two
    programs want the same name at one auction, the first in ROOM's order takes it (Sized, then Probe, then learning,
    `band_of` {program: band}; within a band the earlier row of the tables); the later program's pick of that name is
    skipped (one order a symbol). `allocate` with every program's room its whole list."""
    rooms = {program: len(picks) for program, picks in picks_by_program.items()}
    return allocate(picks_by_program, rooms, band_of)[0]


def reservation(programs: Iterable[Mapping[str, Any]], s: Settings, E: Decimal) -> tuple[Decimal, Decimal]:
    """THE NEXT AUCTION'S RESERVATION (the captain's A85, recorded before the first Probe auction): what a LEARNING buy
    leaves for the Probe and Sized programs whose entry is the OTHER auction (league/equity/live.py `_event_reserve`
    reads them from the House's rows). The book is 1x cash and a lot sold in an auction still holds its cash in that
    auction, so learning lots bought at one auction (the overnight rows' close buys) would take the next auction's cash
    from those programs, and ROOM's order holds only inside one auction (A83 (2)(b)). `programs`: one row each, {band,
    room: max_open(band) less what it holds and has on order at that next auction, picks: the counts of its real-money
    picks at its last `RESERVE_DECISIONS` decisions (the latest first), weights: the open-risk weights of its buys at
    those decisions}. Each reserves n = min(room, the median of `picks`) buys (its whole room when it has no decision
    yet) of share(band) x E at the limit, and that times the median of `weights` (`STRICT_WEIGHT` when it has none) of
    the loss budget. Returns (dollars of cash and of invested room, dollars of loss budget), never below 0."""
    cash = risk = ZERO
    for row in programs:
        band = str(row.get("band"))
        if band not in PROBE_UP:
            continue
        room = Decimal(max(0, int(row.get("room") or 0)))
        counts = [int(n) for n in list(row.get("picks") or ())[:RESERVE_DECISIONS]]
        n = min(room, Decimal(str(statistics.median(counts)))) if counts else room
        usd = n * s.share(band) * Decimal(E)
        weights = [Decimal(str(w)) for w in row.get("weights") or ()]
        weight = Decimal(statistics.median(weights)) if weights else STRICT_WEIGHT
        cash += max(ZERO, usd)
        risk += max(ZERO, usd * weight)
    return cash, risk


# ----------------------------------------------------------------------------------------------------------- reaction
def t29(session: C.Session) -> dt.datetime:
    """PREREG-EVL-2's T29: the start of the regular-session SIP 1-minute bar 31 minutes before the close."""
    return session.close_at - P.T29_BEFORE_CLOSE


def minute_close(rows: Iterable[Mapping[str, Any]], session: C.Session) -> float | None:
    """The close of the regular-session SIP 1-minute bar starting at T29 of `session`, or, when that minute had no
    trade, the last earlier regular-session minute bar of the session (PREREG-EVL-1 C1, PREREG-EVL-2 section 2); None
    when there is none."""
    best = None
    for bar in rows:
        try:
            start = S.parse_iso(str(bar["t"]))
            close = float(bar["c"])
        except (KeyError, TypeError, ValueError):
            continue
        if session.open_at <= start <= t29(session) and math.isfinite(close) and close > 0:
            if best is None or start > best[0]:
                best = (start, close)
    return None if best is None else best[1]


def last_session_before(lane: Lane, moment: dt.datetime) -> dt.date | None:
    """The last session whose close came before `moment` (the lane's calendar)."""
    row = lane.db.execute("SELECT day FROM sessions WHERE close_at<? ORDER BY day DESC LIMIT 1", (S.iso(moment),)).fetchone()
    return None if row is None else dt.date.fromisoformat(row["day"])


def reaction_reader(lane: Lane, day: dt.date, *, daily: Callable[[str, dt.date], float | None],
                    minutes: Callable[[str, C.Session], float | None],
                    minutes_many: Callable[[Sequence[str], C.Session], Mapping[str, float | None]] | None = None
                    ) -> Callable[[Mapping[str, Any], Mapping[str, Any]], float | None]:
    """The REACT rows' ratio for decisions of `day`: the T29 minute close of `day` (the lane's own mark when it stored
    one, else the book's own reading) over the raw SIP daily close of the last session that closed before the event
    (an 8-K's acceptance, an article's knowable time; the lane's bars, else `daily(symbol, that day)`).

    ONE READ A NAME, NEVER ONE A ROW (release 1019b's review: PREREG-EVL-2's day news brings hundreds of articles to a
    close decision, a read each would spend the market-data plan the House's own book shares, at 15:47 on the minute
    thread). Each name's T29 close and each (name, day) base is read once a reader (a decision). With `minutes_many`
    (`minutes_many(symbols, session) -> {symbol: close or None}`, the book's batched reading), the first row with no mark
    reads EVERY name of the day's universe that has none, together; `minutes(symbol, session)` is then asked only for a
    name outside that universe."""
    session = C.session(lane, day)
    closes: dict[str, float | None] = {}
    bases: dict[tuple[str, dt.date], float | None] = {}
    batched: list[bool] = []

    def mark_of(symbol: str) -> float | None:
        mark = lane.db.execute("SELECT px FROM marks WHERE symbol=? AND day=? AND label='1530'", (symbol, day.isoformat())
                               ).fetchone()
        return float(mark["px"]) if mark is not None and mark["px"] else None

    def t29_close(symbol: str) -> float | None:
        if symbol in closes:
            return closes[symbol]
        have = mark_of(symbol)
        if have is not None:
            closes[symbol] = have
            return have
        if minutes_many is not None and not batched:
            batched.append(True)
            names = sorted({str(r["symbol"]).upper() for r in lane.db.execute(LIVE_ROWS, (day.isoformat(),))} - {
                str(r["symbol"]).upper() for r in lane.db.execute(
                    "SELECT symbol FROM marks WHERE day=? AND label='1530' AND px>0", (day.isoformat(),))})
            if names:
                got = dict(minutes_many(names, session) or {})
                for name in names:
                    closes[name] = got.get(name)
        if symbol not in closes:
            closes[symbol] = minutes(symbol, session)
        return closes[symbol]

    def ratio(row: Mapping[str, Any], uni: Mapping[str, Any]) -> float | None:
        if session is None:
            return None
        symbol = str(uni["symbol"]).upper()
        since = row.get("accepted_at") if row.get("accession") else row.get("knowable_at")
        try:
            before = last_session_before(lane, S.parse_iso(str(since)))
        except (TypeError, ValueError):
            return None
        if before is None:
            return None
        if (symbol, before) not in bases:
            got = lane.db.execute("SELECT c FROM bars WHERE symbol=? AND day=? AND adj='raw'",
                                  (symbol, before.isoformat())).fetchone()
            bases[(symbol, before)] = float(got["c"]) if got is not None and got["c"] else daily(symbol, before)
        base = bases[(symbol, before)]
        now = t29_close(symbol)
        if not base or not now or base <= 0:
            return None
        return float(now) / float(base)

    return ratio


# ----------------------------------------------------------------------------------------------------------- sizes
def limit_price(prev_close: Decimal, ratio: Decimal) -> Decimal:
    """The entry's limit: `ratio` x the previous SIP close, ROUNDED DOWN to the cent (never above the pre-registered
    limit, never above what the gateway admits)."""
    return (Decimal(prev_close) * Decimal(ratio)).quantize(CENT, rounding=ROUND_FLOOR)


def sigma(closes: Sequence[float], sessions: int = 60) -> float | None:
    """The daily return sd (sample) of the last `sessions` returns of `closes` (adjusted, oldest first), or None when
    there are fewer than `sessions` + 1 positive closes."""
    xs = [float(c) for c in closes if c is not None and math.isfinite(float(c)) and float(c) > 0]
    if len(xs) < sessions + 1:
        return None
    xs = xs[-(sessions + 1):]
    returns = [xs[i] / xs[i - 1] - 1.0 for i in range(1, len(xs))]
    return statistics.stdev(returns)


def weight(sd: float | None, hold: int, s: Settings) -> Decimal:
    """THE GOAL'S OPEN-RISK RULE for an event lot: max(floor, z x sigma x sqrt(h)), as a Decimal to six places, rounded
    up; `STRICT_WEIGHT` when sigma is unknown. Never below the floor, never above 1."""
    if sd is None or not math.isfinite(sd) or sd < 0:
        return STRICT_WEIGHT
    raw = Decimal(repr(float(s.risk_z) * sd * math.sqrt(max(1, int(hold)))))
    out = max(s.risk_floor, raw.quantize(Decimal("0.000001"), rounding=ROUND_CEILING))
    return min(out, Decimal(1))


def exit_plan(program: P.Program, day: dt.date) -> tuple[str, str]:
    """(exit day, "open" | "close") of `program`'s entry on session `day` (the book's NYSE calendar): an OPEN entry
    exits at its `hold`-th session's CLOSE (the entry session is the first); a CLOSE entry at the session `hold` after
    it, at its `exit_at` (PREREG-EVL-2's overnight rows: the next session's OPEN)."""
    d = day
    steps = program.hold - 1 if program.entry_at == "open" else program.hold
    for _ in range(max(0, steps)):
        d = ES.next_session(d)
    return d.isoformat(), (program.exit_at if program.entry_at == "close" else "close")


# ----------------------------------------------------------------------------------------------------------- the gateway
def publish(client: Any, day: dt.date, symbols: Sequence[str], *, timeout: float = 20.0) -> dict[str, Any]:
    """THE ELIGIBLE LIST published to the gateway (`POST /v1/stock/eligible`, the House's runtime token through the real
    account's gateway client): {ok, day, count, sha, at} as the gateway answers, its sha checked against our own of
    what was sent, or {ok: False, error}. Never raises."""
    names = sorted({str(s).upper() for s in symbols})
    want = hashlib.sha256(f"{day.isoformat()}:{','.join(names)}".encode()).hexdigest()
    try:
        url = str(client.gateway_url).rstrip("/") + "/v1/stock/eligible"
        headers = {"Accept": "application/json", "Content-Type": "application/json", **dict(client.gateway.headers())}
        body = json.dumps({"day": day.isoformat(), "symbols": names}).encode("utf-8")
        status, _, raw = client.transport.request("POST", url, headers=headers, body=body, timeout=timeout)
        answer = json.loads(raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else str(raw or "{}"))
    except Exception as exc:  # noqa: BLE001 - the book tries again next minute
        return {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:160]}"}
    if not 200 <= int(status) < 300 or not isinstance(answer, Mapping) or answer.get("ok") is not True:
        why = answer.get("error") if isinstance(answer, Mapping) else None
        return {"ok": False, "error": f"HTTP {status}: {str(why or answer)[:200]}"}
    if answer.get("sha") != want or int(answer.get("count") or -1) != len(names) or answer.get("day") != day.isoformat():
        return {"ok": False, "error": "the gateway holds another list than the one sent (sha, count or day differ)"}
    return dict(answer)


__all__ = ["KIND", "LANE", "TAG", "EXIT_TAG", "LATE_TAG", "REAL_VERSION", "BANDS", "LIVE_BANDS", "DEFAULT_BAND",
           "PRIORITY", "STRICT_WEIGHT", "LADDER_CLOSES", "ZERO_AFTER", "ISSUER_GAP_SESSIONS", "LANE_DIR", "FILLS_TABLE",
           "FILL_COLUMNS", "seatable", "program_of", "order_of", "room_key", "BIRTH_ROOM", "SCHEMA", "Settings", "FALLBACK",
           "settings", "Lane", "lane_path", "open_lane", "decided", "LIVE_ROWS", "eligible", "universe_rows", "Band",
           "lane_bands", "bands", "sessions_back", "FillWriter", "write_fills", "Pick", "rows_for", "rows_4",
           "held_recently", "picks", "next_open_event", "NEXT_OPEN_GUARD", "allocate", "one_name_an_auction", "t29",
           "minute_close", "last_session_before", "reaction_reader", "limit_price", "sigma", "weight", "exit_plan",
           "publish", "band_mark"]
#: (release 1019f: the probe size's record)
__all__ += ["SCHEMA_COLUMNS", "BINDINGS", "SIZING_BINDINGS", "binding_of"]
#: (release 1019f: A85's reservation and round-robin, with R3's births' tier)
__all__ += ["PROBE_UP", "RESERVE_DECISIONS", "reservation", "send_key", "ROUND_ROBIN_TIERS", "reserved_for",
            "leaves_room"]
