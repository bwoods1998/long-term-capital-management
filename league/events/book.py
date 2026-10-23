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
docs/prereg/PREREG-EVL-4.md and PREREG-EVL-5.md section 1.3 for those files' three programs each:
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
- PREREG-EVL-5 (section 1.3): its rows' real-money events are the shadow rule over the rows STORED, and the verdicts
  ANSWERED, before the decision time, TAKEN AT D'S CLOSE BY AN EARLIER ROW, the <= 0.96 skip and NO NEW INFORMATION
  read from those rows too, a DAY(D) article with no PROMPT-NEWS answer by then skipping its issuer (`rows_5`); the gap
  is the lane's stored 09:30 minute, else the book's own read (`gap_reader`); EVL-ERN-DROP-ON and EVL-ERN-UNDER-ON
  never buy for a filing knowable at or after 09:00 ET of D whose stored PROMPT-DOC verdict is `ok` with score >= 2, or
  `ok` with score >= 1 and guidance "raised", or not yet answered, at the decision time (`NEXT_OPEN_GUARD` with
  `RAISED_GUARD`). And THE EARLIER ROWS' DECISION COMES FIRST: a close whose lane decision finished without deciding this
  file's rows (its part failed or ran past its own bound) is never traded for them, so their buys wait for the lane's
  own close decision of D to name them and go only then, inside the auction's window (`part_hold`).
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
  a pass, at the decision (`allocate`) and at the send (`send_key`); learning keeps the tables' order. R3'S BIRTHS
  (R3-SPEC section 4 as the captain's A97 amends it, PL-2, release 1019h): a birth AT LEARNING comes after every PREREG
  program (`BIRTH_ROOM`); a PROMOTED birth takes its band's tier (Probe or Sized), after that band's PREREG rows and
  before every learning row, round-robins with them, is reserved for and leaves no reservation, as a PREREG program of
  its band (`room_key`, `reserved_for`, `leaves_room`; PREREG-EVL-5 section 1.3: "R3's births come after every file's
  rows" within a band).
- THE NEXT AUCTION'S RESERVATION (A85, recorded before the first Probe auction): ROOM's order holds inside one auction
  (A83 (2)(b)) and a lot sold in an auction still holds its cash there, so a LEARNING buy sizes on the cash, the
  invested room and the loss budget less what the other auction's live Probe and Sized programs will need,
  `reservation`: min(their room, the median of their real-money picks at their last `RESERVE_DECISIONS` decisions) x
  share(band) x E, and that x the median open-risk weight of their buys for the budget, less what this auction's event
  sales give back by then (league/equity/live.py `_event_reserve`). 0 while the other auction has no Probe or Sized
  program. No wall moves.
- SIZE: a target of the band's `position_share` x E (learning 0.02, Probe 0.035, Sized 0.10; Probe by the captain's
  A86 REVISED, PREREG-EVL-1 section 8's 0.05 before it, inside its bound 0-0.05), E the account equity at the previous
  close, at the limit, `limit_ratio` x the previous SIP close (rounded down to the cent), in whole shares; when that
  rounds to none, one share when one share fits every wall (and, at learning and at Probe, one share at the limit is at
  most the band's `one_share_max`, 5%, of E; A86 REVISED added Probe's, which went up to the name's wall before); else
  skipped (the shadow keeps the event). AT DONE'S SIZE (S2, the captain's A97 and A100, release 1019h): a Probe or Sized
  buy that flooring to whole shares took under Done's size bar (its band's `equity_money.event.reach_bar` row of its
  target, 0.8 in force: the judge's own `at_size`; 0 turns the round-up off) buys the fewest whole shares that reach it,
  when they are at most the band's frozen PREREG-EVL-1 section 8 target (the loose end of its `position_share` bounds
  row: Probe 5%, Sized 10%) of the walls' equity and `size_entry` asked again for them still gives them all (`round_up`;
  never when a cap, not rounding, left it under the bar); the target stays the band's (`target_usd` is never the rounded
  ask). Learning never rounds up. The book-wide 10% a name (`per_name_share`), the 100% book, the cash and the loss
  budget are `league.equity.sizing.size_entry`'s own caps (the book calls it; nothing here re-implements it). THE
  WALLS' EQUITY (release 1019f, the reading that trades less): the 10% a name (the decision's skip and the send's caps)
  and the 100% book are judged on the LOWER of E and the account's current equity as the House last read it, since the
  gateway judges the current equity (a buy sized on a higher E met its final refusal there); the target and the
  one-share rule stay on E at the previous close. At most `max_open` positions a program (learning 8, Probe 6, Sized 8).
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
from . import attempts as AT
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
NEXT_OPEN_GUARD = ("EVL-8K-REACT-ON", "EVL-8K-READ-ON", "EVL-ERN-DROP-ON", "EVL-ERN-UNDER-ON")
#: PREREG-EVL-5 section 1.3: its two earnings rows' guard bars, beside PREREG-EVL-4's, a filing whose stored PROMPT-DOC
#: verdict is `ok` with score >= 1 and guidance "raised" (EVL-ERN-GUIDE-O1's event at the next open). PREREG-EVL-4's rows
#: keep their guard exactly as it was (score >= 2, or not answered).
RAISED_GUARD = ("EVL-ERN-DROP-ON", "EVL-ERN-UNDER-ON")
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


#: R3-SPEC section 4 as the captain's A97 amends it (PL-2, release 1019h, recorded before any birth registered): "when
#: room is short, PREREG-EVL-3's order (Sized > Probe > learning; table order) holds; a birth AT LEARNING comes after
#: every PREREG program in registration order; a PROMOTED birth (Probe or Sized) takes its band's tier after that band's
#: PREREG rows": the ROOM tier of a birth at learning, after every PREREG band's (PREREG-EVL-5 section 1.3's frozen
#: ROOM text: "within a band the tables' order ... (R3's births come after every file's rows)").
BIRTH_ROOM = 10


def room_key(program: str, band: str | None) -> tuple[int, int]:
    """ROOM's order (PREREG-EVL-3 section 2): Sized, then Probe, then learning; then the tables' order. A registered
    birth (R3) AT LEARNING comes after every PREREG program, in registration order (`BIRTH_ROOM`, R3-SPEC section 4); a
    PROMOTED birth (A97, PL-2: at Probe or Sized) takes ITS BAND'S TIER, after that band's PREREG rows (the tables'
    order: PREREG-EVL-1's rows, ..., PREREG-EVL-5's, then the births in registration order: PREREG-EVL-5 section 1.3)
    and before every learning row."""
    found = next((p for p in seatable() if p.id == program), None)
    if found is not None and found.spec is not None and str(band) not in PROBE_UP:
        return (BIRTH_ROOM, order_of(program))
    return (PRIORITY.get(str(band), 9), order_of(program))


#: A85 WITH R3'S BIRTHS (release 1019f's integration; R3-SPEC section 4 as A97 amends it, `room_key`): the ROOM tiers
#: (`room_key`'s first figure) that go ROUND-ROBIN inside an auction (`allocate`, `send_key`) and that the next auction's
#: reservation holds room for (`reserved_for`): the Sized and Probe tiers. A birth AT LEARNING has the tier BIRTH_ROOM
#: (after every PREREG program), so it is never reserved for, never round-robins, and its buys leave the reservation as
#: a PREREG learning program's do (`leaves_room`); a PROMOTED birth (A97, PL-2) is in its band's tier, after that band's
#: PREREG rows: it round-robins with them (last in each pass, the tables' order), the reservation holds room for it, and
#: its buys never leave the reservation (they ARE what it holds room for), exactly as a PREREG program of its band.
ROUND_ROBIN_TIERS = (PRIORITY["sized"], PRIORITY["probe"])


def reserved_for(program: str, band: str | None) -> bool:
    """A85: whether the next auction's reservation holds room for `program` at `band`: a program at Sized or Probe (its
    ROOM tier one of `ROUND_ROBIN_TIERS`), a promoted birth's included (A97, PL-2); never one at learning, a birth's
    neither."""
    return room_key(program, band)[0] in ROUND_ROBIN_TIERS


def leaves_room(program: str, band: str | None) -> bool:
    """A85: whether a buy of `program` at `band` sizes less the next auction's reservation: a live band whose ROOM tier
    comes after the Probe tier, so a PREREG learning program's buy (A85's "a learning buy") and a birth's at learning
    (R3: after every PREREG program); never a Probe or Sized buy, a promoted birth's included (A97, PL-2: its band's
    tier)."""
    return str(band) in LIVE_BANDS and room_key(program, band)[0] > max(ROUND_ROBIN_TIERS)


# ------------------------------------------------------------------------------------------------- Done's size bar
def envelope_share(band: str | None) -> Decimal | None:
    """S2 (A97, release 1019h): THE FROZEN ENVELOPE of a Probe+ buy, as a share of the walls' equity: the LOOSE END of
    the band's `event.position_share` bounds row (league/constitution.py `EQUITY_MONEY_BOUNDS`, never a literal here):
    Probe 0.05 (PREREG-EVL-1 section 8's frozen 5% Probe target, which A86 REVISED's 0.035 sits inside) and Sized 0.10
    (PREREG-EVL-1 section 8's Sized target, the name's wall); None at learning, which never rounds up."""
    if str(band) not in PROBE_UP:
        return None
    from ..constitution import EQUITY_MONEY_BOUNDS

    return Decimal(EQUITY_MONEY_BOUNDS[f"event.position_share.{band}"][1])


def at_size(target: Decimal | float | str, usd: Decimal | float | str, bar: Decimal | float | str | None = None) -> bool:
    """Whether a buy of `usd` dollars at the limit reaches `bar` x the band target `target` (`bar` None: the Done
    reader's own `PROBE_SIZE_SHARE`). At the judge's line (None, or a row equal to it: the row in force is 0.8, a test
    pins them equal) this IS the Done reader's own test (league/events/done.py `at_size`, the judge, read and never
    edited: `sized_usd` >= `PROBE_SIZE_SHARE` x `target_usd` on the floats the lane's `real_fills` hold), so the House's
    buys are judged by the very comparison that counts them (an exact-equality case is never lost to a rounding the
    judge does not make); at a lower row (the tighten-only `event.reach_bar` rows, release 1019h) the same float
    comparison at that share. False when the target is not above 0."""
    from . import done as DN

    t, u = float(Decimal(str(target))), float(Decimal(str(usd)))
    share = DN.PROBE_SIZE_SHARE if bar is None else float(Decimal(str(bar)))
    if share == DN.PROBE_SIZE_SHARE:
        return DN.at_size(t, u)
    return t > 0 and u >= share * t


def round_up(band: str | None, target: Decimal, limit: Decimal, whole: Decimal, walls: Decimal, *,
             bar: Decimal | str | None = None) -> Decimal | None:
    """S2 (= SUP-1's sizing; the captain's A97 and A100, release 1019h, inside A86 REVISED's doctrine): THE WHOLE SHARES
    THAT REACH DONE'S SIZE BAR, or None (the buy goes as today). `bar`: the band's `equity_money.event.reach_bar` row
    (None: the row in force, `settings().reach_bar(band)`); 0 is release 1019f's floor rounding, NO ROUND-UP (the
    tighten-only switch). Only at Probe or Sized (`PROBE_UP`; learning has no row), only for a buy that flooring to
    `whole` (>= 1) shares at the limit took UNDER the bar (`at_size`: whole x limit under `bar` x `target`, the band's
    target, position_share x E at the previous close; at the row in force, 0.8, the Done reader's own test): the fewest
    whole shares n > whole whose dollars n x limit reach it, provided n x limit is at most `envelope_share(band)` x
    `walls` (the walls' equity, the lower of E and the account's current equity: the reading that trades less). So n is
    never above floor(envelope x E / limit), PREREG-EVL-1 section 8's own count at its frozen target (Probe 5%, Sized
    10%): inside the frozen envelope. At Sized the envelope is the target itself (whole shares of 10% are already that
    count), so no Sized buy rounds up today; the rule is one rule for both bands. The caller (league/equity/live.py
    `_size_event`) rounds up only when ROUNDING caused the shortfall (`size_entry`'s fractional dollars reach the bar; a
    cap that cut them under it is never rounded past) and only when `size_entry` asked again at n x limit still gives
    n shares (the name wall, the 100% book, cash and the loss budget at the lot's weight all judge the round-up)."""
    if str(band) not in PROBE_UP:
        return None
    share = settings().reach_bar(str(band)) if bar is None else Decimal(str(bar))
    if not share > 0:
        return None
    target, limit, whole, walls = (Decimal(str(v)) for v in (target, limit, whole, walls))
    if not (target > 0 and limit > 0 and whole >= 1) or at_size(target, whole * limit, share):
        return None
    cap = envelope_share(band)
    if cap is None:
        return None
    top = cap * walls
    # (the bar's own ceiling, less one so the judge's float comparison decides the edge; at most two steps)
    n = max(whole + 1, (share * target / limit).to_integral_value(rounding=ROUND_CEILING) - 1)
    while n * limit <= top:
        if at_size(target, n * limit, share):
            return n
        n += 1
    return None


def under_bar(band: str | None, target: Decimal, limit: Decimal, walls: Decimal, *,
              bar: Decimal | str | None = None) -> bool:
    """PREREG-EVL-6 SECTION 6, CLAUSE 2 (A99): "A Probe or Sized buy takes the fewest whole shares whose value at the
    limit reaches 0.8 of its band's target ... It is never above 5% of equity at Probe, nor above the name's 10% wall at
    Sized ... A pick that no such count reaches is skipped before it takes a slot; the shadow keeps it." True when NO
    whole-share count reaches the bar inside the band's frozen envelope: the fewest whole shares n >= 1 whose dollars
    at the limit reach `bar` x `target` (the Done reader's own `at_size` at the row in force) cost more than
    `envelope_share(band)` x `walls` (Probe 5%, Sized 10%, the walls' equity). False at learning, with the round-up's
    row at 0 (S2's switch off: no at-size buy), or when the figures are not positive (the caller's other rules judge
    them). The caller (league/equity/live.py `_event_gate`) skips such a pick at the decision as `under_bar`, for the
    versions PREREG-EVL-6 judges (`Program.evl6`) alone: release 1019h's S2 (`round_up`) buys a floored buy under the
    bar as it is when no round-up fits, and skips nothing before a slot."""
    if str(band) not in PROBE_UP:
        return False
    share = settings().reach_bar(str(band)) if bar is None else Decimal(str(bar))
    if not share > 0:
        return False
    target, limit, walls = (Decimal(str(v)) for v in (target, limit, walls))
    if not (target > 0 and limit > 0 and walls > 0):
        return False
    cap = envelope_share(band)
    if cap is None:
        return False
    return _fewest(target, limit, share) * limit > cap * walls


def _fewest(target: Decimal, limit: Decimal, share: Decimal) -> Decimal:
    """The fewest whole shares n >= 1 whose dollars n x `limit` reach `share` x `target` by the Done reader's own float
    comparison (`at_size`), for positive figures and a share above 0."""
    n = max(Decimal(1), (share * target / limit).to_integral_value(rounding=ROUND_CEILING) - 1)
    while not at_size(target, n * limit, share):
        n += 1
    return n


def at_size_count(band: str | None, target: Decimal, limit: Decimal, walls: Decimal, *,
                  bar: Decimal | str | None = None) -> Decimal | None:
    """PREREG-EVL-6 SECTION 6, CLAUSE 2 (A99), THE COUNT OF A PROBE OR SIZED BUY of a version it judges: "a Probe or
    Sized buy takes the FEWEST whole shares whose value at the limit reaches 0.8 of its band's target ... never above 5%
    of equity at Probe, nor above the name's 10% wall at Sized, and that ask is judged again by every cap". The fewest
    whole shares n >= 1 whose dollars at `limit` reach `bar` x `target` (the Done reader's own `at_size` at the row in
    force; `bar` None: the band's `reach_bar` row), when n x limit is at most `envelope_share(band)` x `walls` (Probe 5%,
    Sized 10%, the walls' equity: so n <= floor(5% E / limit) at Probe, PREREG-EVL-1 section 8's own count); None when
    no such count fits (`under_bar`: the pick is skipped before it takes a slot), at learning, with the band's row at 0
    (S2's switch off: no at-size buy), or when the figures are not positive. It is never release 1019h's floor of the
    target: a buy the floor would take to 13 shares at $5.00 of a $66.43 target takes 11 ($55.00 reaches $53.144), the
    reading of the text's words, which trades less. The caller (league/equity/live.py `_size_event`) asks `size_entry`
    for n x limit and buys n only when every cap gives all n; a cap that cuts the ask under the bar skips the buy (the
    reading that trades less, section 7)."""
    if str(band) not in PROBE_UP:
        return None
    share = settings().reach_bar(str(band)) if bar is None else Decimal(str(bar))
    if not share > 0:
        return None
    target, limit, walls = (Decimal(str(v)) for v in (target, limit, walls))
    if not (target > 0 and limit > 0 and walls > 0):
        return None
    cap = envelope_share(band)
    if cap is None:
        return None
    n = _fewest(target, limit, share)
    return None if n * limit > cap * walls else n


def most_ask(s: "Settings", band: str | None, E: Decimal) -> Decimal:
    """THE MOST A BUY OF `band` MAY ASK at equity `E` before its figures are read (league/equity/live.py
    `_event_keep_room`'s keep when a sizing figure cannot be read this minute: the reading that keeps more): its target,
    `share(band)` x E, or, while S2's round-up is on for the band (`reach_bar` above 0, release 1019h), the band's frozen
    envelope, `envelope_share(band)` x E, when that is more (a round-up asks at most the envelope of the walls' equity,
    which is never above E)."""
    E = Decimal(str(E))
    usd = s.share(str(band)) * E
    cap = envelope_share(band)
    if cap is not None and s.reach_bar(str(band)) > 0:
        usd = max(usd, cap * E)
    return usd


def send_key(program: str, band: str | None, n: int) -> tuple[int, int, int]:
    """THE ORDER OF AN AUCTION'S BUYS AT THEIR SEND (league/equity/live.py `_event_send`), `n` the buy's place among its
    program's buys of the auction (0 its first): ROOM's tiers (`room_key`: Sized, then Probe, then learning, then the
    births at learning, R3; a promoted birth in its band's tier after that band's PREREG rows, A97 PL-2); inside the
    Sized tier and inside the Probe tier ROUND-ROBIN (`ROUND_ROBIN_TIERS`), every program's first buy before any
    program's second, the tables' order inside a pass (A85: the cash an auction's sends take goes one buy a program a
    pass, so the last Probe row in the tables is not left the cash the earlier rows did not take); learning, and the
    births at learning, in the tables' order, each program's buys in its ranking (release 1019e's `room_key` order)."""
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
    #: DONE'S SIZE BAR a Probe or Sized buy rounds up to (`event.reach_bar`, release 1019h, the captain's A97 S2 and
    #: A100; `round_up`): a share of the band target, 0.8 in force (the Done reader's `PROBE_SIZE_SHARE`). Empty (0 for
    #: every band) when unread: no round-up, release 1019f's floor rounding.
    reach_bars: Mapping[str, Decimal] = dataclasses.field(default_factory=dict)
    #: PREREG-EVL-6 SECTION 6's PROBE SLOTS (`event.max_open_v6`, release 1019i, the captain's A99 and A100): read only
    #: for the versions registered at or after REGISTERED_AT_6 (`max_open`'s `program`, league/events/programs.py
    #: `Program.evl6`). Empty when unread (the table's FALLBACK: nothing opens anyway).
    max_opens_v6: Mapping[str, int] = dataclasses.field(default_factory=dict)

    def share(self, band: str) -> Decimal:
        return Decimal(self.shares.get(str(band), ZERO))

    def max_open(self, band: str, program: Any = None) -> int:
        """The open positions a program may hold at `band`: `event.max_open` (learning 8, Probe 6, Sized 8), and for a
        version registered at or after REGISTERED_AT_6 (`program.evl6`: PREREG-EVL-6 section 6, A100's row read by the
        version's registration time) at Probe `event.max_open_v6.probe` (14)."""
        if program is not None and getattr(program, "evl6", False) and str(band) in self.max_opens_v6:
            return int(self.max_opens_v6[str(band)])
        return int(self.max_opens.get(str(band), 0))

    def reach_bar(self, band: str) -> Decimal:
        """The band's Done size bar for S2's round-up (`reach_bars`), 0 (no round-up) at learning and when unread."""
        return Decimal(self.reach_bars.get(str(band), ZERO))

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
            max_orders_day=int(e["max_orders_day"]),
            reach_bars={band: Decimal(str(e["reach_bar"][band])) for band in PROBE_UP},
            max_opens_v6={band: int(n) for band, n in dict(e["max_open_v6"]).items()})
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
        self.cache: dict[str, Any] = {}     # (PREREG-EVL-5's reads of one decision, and the parsed tickers copies)

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
    two). PREREG-EVL-7's E5 (league/events/learner.py `AsOf`): a view carrying `eligible_by` reads only the live results
    DECIDED AT OR BEFORE that time; every other caller's reading is unchanged."""
    out: dict[str, dict[str, Any]] = {}
    bound = getattr(lane, "eligible_by", None)
    sql, args = (LIVE_ROWS, (day.isoformat(),)) if bound is None else \
        (LIVE_ROWS + " AND e.decided_at<=?", (day.isoformat(), S.iso(bound)))
    for r in lane.db.execute(sql, args):
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


#: THE ATTEMPTS LEDGER (release 1019i, PREREG-EVL-7's H3; league/events/attempts.py): the book's kv mark of the newest
#: row the lane's store took, and the slack it reads again before it (league/equity/live.py `_event_attempts`).
ATTEMPTS_MARK = AT.MARK_KEY
ATTEMPTS_SLACK_S = AT.MARK_SLACK_S


def attempt_rows(rows: Callable[..., list], *, since: float = 0.0) -> tuple[list[dict[str, Any]], float | None]:
    """THE ATTEMPTS LEDGER'S ROWS from the book's own live.sqlite (`rows`, read only: league/events/attempts.py
    `book_rows`): every order of a real event instance, and every planned real buy that ended unsent, changed at or after
    `since`; and the newest change read. Nothing here sends, changes or cancels an order."""
    return AT.book_rows(rows, since=since)


def write_attempts(root: str | Path | None, rows: Sequence[Mapping[str, Any]]) -> int | None:
    """THE ATTEMPTS HANDED TO THE LANE (release 1019i): `rows` (`attempt_rows`) into the lane's `real_attempts`
    (league/events/attempts.py `record`, one transaction), through the same existing-file opener as the real fills
    (`FillWriter`: never a new store or table). Returns how many rows were new or changed; None when there is no lane
    store or it holds no `real_attempts` table yet (a lane not yet opened by release 1019i: the book writes them once
    it does). Raises `sqlite3.Error` when the store cannot be written (asked again next minute)."""
    if root is None:
        return None
    path = lane_path(root)
    if not path.is_file():
        return None
    store = FillWriter(path)
    try:
        if not AT.has_table(store.db):
            return None
        return AT.record(store, rows)
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


def pick_record(pick: Pick) -> dict[str, Any]:
    """A pick as JSON (PREREG-EVL-7 section 1.9: the picks the auction's own decision read for the programs whose names
    wait for the learners, kept in its summary until the learners' decision gives them: league/equity/live.py
    `_event_decide_lrn`); `pick_of` reads it back exactly (the previous close as its decimal text)."""
    return {"program": pick.program, "version": int(pick.version), "event": pick.event, "symbol": pick.symbol,
            "cik": pick.cik, "rank": pick.rank, "adv20": float(pick.adv20), "prev_close": str(pick.prev_close),
            "knowable_at": pick.knowable_at}


def pick_of(record: Mapping[str, Any]) -> Pick:
    rank = record.get("rank")
    return Pick(str(record["program"]), int(record["version"]), str(record["event"]), str(record["symbol"]),
                str(record["cik"]), None if rank is None else float(rank), float(record.get("adv20") or 0.0),
                Decimal(str(record["prev_close"])), str(record.get("knowable_at") or ""))


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


def _answer_before(lane: Lane, event: str, prompt: Any, decided_at: dt.datetime) -> Mapping[str, Any] | None:
    """The stored verdict of `event` when it was ANSWERED (any status) at or before the decision time (PREREG-EVL-1
    section 3), else None (none stored, or answered after it)."""
    got = V.stored(lane, event, prompt)
    if not got or not got.get("answered_at"):
        return None
    try:
        return got if S.parse_iso(str(got["answered_at"])) <= decided_at else None
    except ValueError:
        return None


def lane_tickers(lane: Lane, day: dt.date) -> dict[str, list[tuple[str, str]]]:
    """SEC's company_tickers.json as the lane's decision of entry session `day` reads it (league/events/run.py
    `Context.tickers_for`: the latest copy fetched before 07:30 ET of `day`, or, with none that early, the earliest),
    parsed once a copy; {} when the lane holds none."""
    from . import universe as U

    snaps = [(S.parse_iso(str(r["key"]).split("@", 1)[1]), str(r["value"])) for r in
             lane.db.execute("SELECT key, value FROM meta WHERE key LIKE 'tickers@%' ORDER BY key")]
    if not snaps:
        return {}
    cutoff = dt.datetime.combine(day, dt.time(7, 30), tzinfo=C.NY).astimezone(dt.timezone.utc)
    before = [sha for at, sha in snaps if at < cutoff]
    sha = before[-1] if before else snaps[0][1]
    key = f"tickers:{sha}"
    if key not in lane.cache:
        data = lane.get_document(sha)
        for old in [k for k in lane.cache if k.startswith("tickers:")]:
            lane.cache.pop(old)     # (one parsed copy kept: the House's book holds its lane open for days)
        lane.cache[key] = U.sec_tickers(lambda url: data)
    return lane.cache[key]


def rows_5(lane: Lane, day: dt.date, decided_at: dt.datetime, *,
           reaction: Callable[[Mapping[str, Any], Mapping[str, Any]], float | None]) -> dict[str, list[Mapping[str, Any]]]:
    """PREREG-EVL-5's rows for a real-money decision of entry session `day` (its section 1.3: "the shadow rule over the
    events STORED, and the verdicts ANSWERED, before D's close decision time. It applies TAKEN AT D'S CLOSE BY AN EARLIER
    ROW and NO NEW INFORMATION to the filings and articles stored before that time, and a DAY(D) article with no
    PROMPT-NEWS answer before that time skips its issuer"): ERN(D)'s fetched filings, DAY(D)'s and the attention
    articles of P (each with the CIK of the live rule's eligible universe row whose symbol it names), and NO NEW
    INFORMATION's articles (any symbols, mapped by the lane's tickers copy of D), 8-Ks and insider buys, each STORED
    before `decided_at` (`_stored_before`) and read with NO registration floor; the reactions are the book's
    (`reaction(row, universe_row)`: the T29 close over the last close before the filing's acceptance, or the article's
    knowable time, which for a DAY(D) article is P's close, the universe row's previous close); then
    `programs.close_rows_5`. {"ern-drop", "ern-under", "news-night2": rows}; `rows_for` keeps a program's events. One
    decision's reads are made once (the lane's `cache`)."""
    key = (day.isoformat(), S.iso(decided_at))
    have = lane.cache.get("rows5")
    if have is not None and have[0] == key and have[1] is reaction:
        return have[2]
    lo, hi = P.close_window(lane, day)
    uni = universe_rows(lane, day)
    by_symbol = {str(r["symbol"]).upper(): str(cik) for cik, r in uni.items()}

    def stored(rows: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
        return [r for r in rows if _stored_before(r, decided_at, lane)]

    def with_cik(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
        return [dict(r) | {"cik": by_symbol.get(str(r.get("symbol") or "").upper())} for r in stored(rows)]

    def symbol_of(cik: str) -> str | None:
        row = uni.get(str(cik))
        return None if row is None else row["symbol"]
    ern = [r for r in stored(P.filings_window(lane, "8-K", lo, hi)) if P.items_of(r) & P.ERN_ITEMS and r.get("cik")]
    day_all = with_cik(P.news_rows(lane, *P.day_news_window(lane, day)))
    ratios: dict[str, float | None] = {}

    def react(row: Mapping[str, Any]) -> float | None:
        cik = str(row.get("cik"))
        if cik not in uni:
            return None
        if str(row["accession"]) not in ratios:
            ratios[str(row["accession"])] = reaction(row, uni[cik])
        return ratios[str(row["accession"])]
    firsts: dict[str, Mapping[str, Any]] = {}
    for a in day_all:
        if a.get("cik") and symbol_of(str(a["cik"])) == a.get("symbol"):
            firsts.setdefault(str(a["cik"]), a)
    day_ratios: dict[str, float | None] = {}

    def day_reaction(cik: str) -> float | None:
        if cik not in day_ratios:
            day_ratios[cik] = reaction(firsts[cik], uni[cik]) if cik in firsts and cik in uni else None
        return day_ratios[cik]
    ern_of = {str(r["cik"]) for r in ern if str(r["cik"]) in uni}
    day5 = [a for a in day_all if a.get("cik") and str(a["cik"]) in ern_of]
    taken, waiting = P.taken_close_5(ern, day5, symbol_of=symbol_of, reaction=react, day_reaction=day_reaction,
                                     news_answer=lambda a: _answer_before(lane, f"news:{a['id']}", V.PROMPTS["news"],
                                                                          decided_at))
    dropped = P.dropped_ciks(ern, react)
    windows = P.night2_windows(lane, day)
    named = P.named_ciks(stored(P.news_named(lane, *windows["named"])), P.ciks_by_ticker(lane_tickers(lane, day)))
    filed = P.filed_ciks(stored(P.filings_window(lane, "8-K", *windows["filed"])))
    bought = P.bought_ciks(stored(P.ins_buys_window(lane, *windows["bought"])))
    attention = with_cik(P.news_rows(lane, *P.attention_window(lane, day)))
    out = P.close_rows_5(ern, P.no_new_info(attention, named, filed, bought, symbol_of), taken=taken, waiting=waiting,
                         dropped=dropped)
    lane.cache["rows5"] = (key, reaction, out)
    return out


def rows_for(lane: Lane, program: P.Program, day: dt.date, decided_at: dt.datetime, *,
             reaction: Callable[[Mapping[str, Any], Mapping[str, Any]], float | None] | None = None
             ) -> list[Mapping[str, Any]]:
    """The events `program`'s decision of entry session `day` reads (league/events/run.py's windows), STORED before
    `decided_at` and knowable after the program's own registration time. News rows carry their eligible issuer's CIK
    (the universe row whose symbol is the article's). PREREG-EVL-4's rows: `rows_4`. Every family a seatable program can
    have reads its rows here as the lane's decision reads them (release 1019e's review: R3's `ins` family, Form 4
    cluster triggers, is a record only (A89): its cluster reads Form 4s that may be stored after the decision, so the
    book reads no rows for it and a seatable `ins` birth is refused by the births' grammar). PREREG-EVL-5's rows:
    `rows_5`, which needs the book's `reaction` (without one it reads no rows: LookupError, that program plans nothing)."""
    family = program.family
    if program.entry_at == "close" and family in P.CLOSE_FAMILIES_4:
        since = program.registered_at
        return [r for r in rows_4(lane, day, decided_at)[family] if S.parse_iso(r["knowable_at"]) > since]
    if program.entry_at == "close" and family in P.CLOSE_FAMILIES_5:
        if reaction is None:
            raise LookupError("PREREG-EVL-5's rows are read with the book's reaction reader (TAKEN AT D'S CLOSE)")
        since = program.registered_at
        return [r for r in rows_5(lane, day, decided_at, reaction=reaction)[family]
                if S.parse_iso(r["knowable_at"]) > since]
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
    if row is None:
        # PREREG-EVL-6 section 1.1 (D12): a new version's one position per issuer counts the superseded version's
        # intents of every session decided BEFORE THE RELEASE too (league/events/programs.py `superseded_held`), as
        # its shadow does; never one the superseded version writes from the release on
        row = P.superseded_held(lane, program, str(cik), since.isoformat(),
                                (day - dt.timedelta(days=1)).isoformat())
    return row is not None


def next_open_event(lane: Lane, row: Mapping[str, Any], session: C.Session | None, decided_at: dt.datetime, *,
                    raised: bool = False) -> bool:
    """PREREG-EVL-4 section 1.3 (NO REAL-MONEY TAKING FROM AN EARLIER ROW), for `NEXT_OPEN_GUARD`'s programs: True when
    real money does NOT buy for this filing, being EVL-8K-READ-O1's event at the next open: knowable at or after 09:00 ET
    of D (`session`, D) and its stored PROMPT-DOC verdict `ok` with score >= 2, or not yet answered at `decided_at` (no
    stored answer, or one answered after it; a filing whose TEXT gets no verdict is never answered: the reading that
    trades less). A filing knowable before 09:00 ET of D is EVL-8K-READ-O1's at D's open, whose sale at D's close the
    sale gate already keeps this buy out of; an answer that is not `ok` (unparsed, refused) or scores under 2 leaves the
    buy. Unreadable inputs read as barred (fail closed). `raised` (PREREG-EVL-5 section 1.3, `RAISED_GUARD`'s programs):
    an `ok` answer with score >= 1 and guidance "raised" bars it too (EVL-ERN-GUIDE-O1's event at the next open); without
    it the guard is PREREG-EVL-4's, unchanged."""
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
    if raised and got.get("status") == "ok" and score is not None and score >= P.GUIDE_MIN_SCORE and \
            got.get("guidance") == "raised":
        return True
    return got.get("status") == "ok" and score is not None and score >= P.READ_MIN_SCORE


def picks(lane: Lane, program: P.Program, day: dt.date, *, decided_at: dt.datetime,
          reaction: Callable[[Mapping[str, Any], Mapping[str, Any]], float | None] | None = None,
          held: Callable[[str], bool] | None = None,
          gap: Callable[[Mapping[str, Any], Mapping[str, Any]], float | None] | None = None) -> list[Pick]:
    """THE REAL-MONEY PICKS of `program` for entry session `day` (the module docstring): the shadow rule
    (league/events/programs.py `select`) over the events stored before `decided_at`, with the verdicts answered before
    it; one per issuer (the earliest knowable, after `select`'s own order for the news rows); an issuer the program holds
    or held within `ISSUER_GAP_SESSIONS` sessions (the shadow's intents of earlier decisions in the lane,
    `held_recently`, and `held(cik)` for real money's own lots and buys) skipped; ranked higher first, then ADV.
    `reaction(row, universe_row)`: the REACT rows' ratio (the book's reading of the SIP bars), None when a price is
    missing. For `NEXT_OPEN_GUARD`'s programs (PREREG-EVL-4 section 1.3) the issuer's one event is not bought when it is
    EVL-8K-READ-O1's at the next open (`next_open_event`); no later filing of the issuer stands in for it. PREREG-EVL-5's
    rows (section 1.3) read `rows_5` with `reaction`, EVL-NEWS-NIGHT2-ON its `gap(row, universe_row)` (`gap_reader`; a
    price it cannot read is not bought), and its two earnings rows the guard with `raised` (`RAISED_GUARD`).
    PREREG-EVL-7's learners: their own written live decision, `learner_picks` (never `select`)."""
    if P.is_learner(program):
        return learner_picks(lane, program, day, decided_at=decided_at, held=held)
    uni = universe_rows(lane, day)
    news = program.family in P.NEWS_FAMILIES
    guard = program.id in NEXT_OPEN_GUARD
    raised = program.id in RAISED_GUARD
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

    chosen = P.select(program, rows_for(lane, program, day, decided_at, reaction=reaction),
                      eligible=lambda cik: uni.get(str(cik)), verdict=verdict, reaction=reaction, guidance=guidance,
                      gap=gap)
    out: list[Pick] = []
    taken: set[str] = set()
    for c in sorted(chosen, key=lambda c: (c.knowable_at, c.event)):
        if c.cik in taken:
            continue
        taken.add(c.cik)
        if guard and next_open_event(lane, c.row, session, decided_at, raised=raised):
            continue        # (PREREG-EVL-4 and -5 section 1.3: the shadow keeps the event)
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
    program in turn to its room; then the births AT LEARNING (R3's `BIRTH_ROOM`, after every PREREG program), in
    registration order, each in turn to its room, as release 1019e gave them; a PROMOTED birth (A97, PL-2) is in its
    band's round-robin tier, after that band's PREREG rows (`room_key`). Only a name GIVEN to a
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
        while i < len(order) and tier(order[i]) == rank:   # (one ROOM tier: a birth's at learning is BIRTH_ROOM)
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


def opening_minute(rows: Iterable[Mapping[str, Any]], session: C.Session) -> float | None:
    """PREREG-EVL-5's gap minute: the OPEN of the regular-session SIP 1-minute bar starting at the session's open
    (09:30:00 ET), None when that minute had no trade (no such bar)."""
    for bar in rows:
        try:
            start = S.parse_iso(str(bar["t"]))
            px = float(bar["o"])
        except (KeyError, TypeError, ValueError):
            continue
        if start == session.open_at and math.isfinite(px) and px > 0:
            return px
    return None


def gap_reader(lane: Lane, day: dt.date, *, opens: Callable[[str, C.Session], float | None],
               opens_many: Callable[[Sequence[str], C.Session], Mapping[str, float | None]] | None = None
               ) -> Callable[[Mapping[str, Any], Mapping[str, Any]], float | None]:
    """EVL-NEWS-NIGHT2-ON's gap for real-money decisions of `day` (PREREG-EVL-5 sections 1.1 and 1.3): the open of D's
    09:30 minute bar over the universe row's previous close (the raw SIP close of P). The minute is the lane's stored
    mark when it holds one (league/events/run.py `GAP_LABEL`, made by the session's pre-passes and its decisions; a
    stored row with no price is the tape's word that the minute had no trade, which only a decision's read of the name
    alone writes: no gap, not bought), else the book's own reading: with `opens_many(symbols, session)`, the
    first name with no mark reads EVERY name of the day's live universe that has none, together (one read a name, never
    one a row, as `reaction_reader`); `opens(symbol, session)` is asked only for a name outside it. None when a price is
    missing (not bought)."""
    session = C.session(lane, day)
    got: dict[str, float | None] = {}
    batched: list[bool] = []

    def open_of(symbol: str) -> float | None:
        if symbol in got:
            return got[symbol]
        row = lane.db.execute("SELECT px FROM marks WHERE symbol=? AND day=? AND label='0930'",
                              (symbol, day.isoformat())).fetchone()
        if row is not None:
            got[symbol] = float(row["px"]) if row["px"] is not None and float(row["px"]) > 0 else None
            return got[symbol]
        if opens_many is not None and not batched:
            batched.append(True)
            names = sorted({str(r["symbol"]).upper() for r in lane.db.execute(LIVE_ROWS, (day.isoformat(),))} - {
                str(r["symbol"]).upper() for r in lane.db.execute(
                    "SELECT symbol FROM marks WHERE day=? AND label='0930'", (day.isoformat(),))})
            if names:
                read = dict(opens_many(names, session) or {})
                for name in names:
                    got[name] = read.get(name)
        if symbol not in got:
            got[symbol] = opens(symbol, session)
        return got[symbol]

    def gap(row: Mapping[str, Any], uni: Mapping[str, Any]) -> float | None:
        if session is None:
            return None
        try:
            prev = float(uni["prev_close"])
        except (KeyError, TypeError, ValueError):
            return None
        px = open_of(str(uni["symbol"]).upper())
        if px is None or not prev > 0:
            return None
        return float(px) / prev
    return gap


# ----------------------------------------------------------------------------------------------------- PREREG-EVL-7
#: PREREG-EVL-7 section 1.9's DAY ORDER LINE ("refuses this file's entries after every earlier PREREG row's; an exit is
#: never stopped by it"): a learner's entry keeps, on the event kind's line of its day, every order the earlier PREREG
#: rows may still send that day after it (league/equity/live.py `_event_line_keep`, passed to `_count_refusal` as
#: `keep`; the money review of release 1019i replaced a fixed keep of 32 slots). LINE_ACROSS_AUCTIONS True (section
#: 1.11 (10), the reading that trades less): ACROSS THE DAY'S AUCTIONS, so an EVL-LRN-O1 open entry also keeps, for
#: every earlier close-entry row, a send and an A80 re-send of each position its band may still open at that close.
#: STATED EFFECT, for the captain's amendment: with release 1019h's ten close-entry rows at learning (8 positions each),
#: that keep is 1 + 10 x 2 x 8 = 161 of the line's 150 on an empty day, so EVL-LRN-O1 BUYS NOTHING IN REAL MONEY while
#: they hold room (its shadow, the record that alone promotes, is unchanged). False (an amendment): the keep holds
#: inside the learner's own auction only (that auction's earlier buys not yet sent and their re-sends), and an O1 entry
#: with its exit at the close can take a slot an earlier close entry needs once the day's line is nearly full.
LINE_ACROSS_AUCTIONS = True


def is_learner(program: Any) -> bool:
    """Whether a Program row (or an id) is one of PREREG-EVL-7's learners (league/events/programs.py `is_learner`)."""
    return P.is_learner(program)


def ern_issuer(lane: Lane, cik: str, day: dt.date, decided_at: dt.datetime) -> bool:
    """EVL-LRN-O1'S ERN GUARD (PREREG-EVL-7 section 1.9, E8), IN REAL MONEY ONLY: True when the issuer has an 8-K with
    item 2.02 knowable in D's close window (programs.py `close_window`) and stored by the decision time (`_stored_before`,
    the reading that trades less): an ERN(D) issuer, which earlier rows buy at D's close and which this learner's sale
    there would take. Unreadable inputs read as barred (fail closed). The shadow keeps the pick."""
    try:
        lo, hi = P.close_window(lane, day)
        for row in P.filings_window(lane, "8-K", lo, hi):
            if str(row.get("cik")) == str(cik) and P.items_of(row) & P.ERN_ITEMS and _stored_before(row, decided_at, lane):
                return True
    except (LookupError, sqlite3.Error, TypeError, ValueError):
        return True
    return False


def issuer_8k_guard(lane: Lane, cik: str, session: C.Session | None, decided_at: dt.datetime) -> bool:
    """EVL-LRN-ON'S 8-K GUARD (PREREG-EVL-7 section 1.9, E10), IN REAL MONEY ONLY: True when the issuer is NOT bought.
    It reads EVERY 8-K of the issuer (form exactly '8-K') knowable at or after 09:00 ET of D and stored by the decision
    time, whatever the learner's primary event (never the primary event's accession): barred when any of them has a
    stored PROMPT-DOC verdict `ok` with score >= 2, or `ok` with score >= 1 and guidance "raised", or no answer by the
    decision time (PREREG-EVL-4 and -5 section 1.3 with A75 (1)'s readings): such a filing is an earlier row's event at
    the next open, which this learner's sale there would take. An issuer with no such 8-K is not barred. Unreadable
    inputs read as barred (fail closed). The shadow keeps every pick."""
    if session is None:
        return True
    try:
        # (section 1.9's words: knowable at or after 09:00 ET of D and stored before the decision; NO upper bound on
        # the knowable time (release 1019i's money re-review): a filing listed and stored before tau whose knowable
        # time falls after it is read like any other)
        rows = lane.db.execute("SELECT * FROM filings WHERE form='8-K' AND status='fetched' AND cik=? AND knowable_at>=? "
                               "ORDER BY knowable_at, accession", (str(cik), S.iso(session.open_cutoff))).fetchall()
        for r in rows:
            row = dict(r)
            if not _stored_before(row, decided_at, lane):
                continue
            got = V.stored(lane, f"8k:{row['accession']}", V.PROMPTS["doc"])
            if not got or not got.get("answered_at") or S.parse_iso(str(got["answered_at"])) > decided_at:
                return True
            score = None if got.get("score") is None else int(got["score"])
            if got.get("status") != "ok" or score is None:
                continue
            if score >= P.READ_MIN_SCORE or (score >= P.GUIDE_MIN_SCORE and got.get("guidance") == "raised"):
                return True
    except (sqlite3.Error, TypeError, ValueError, KeyError):
        return True
    return False


def learner_gate(lane: Lane, program: P.Program) -> str | None:
    """Why a PREREG-EVL-7 learner's real money buys nothing now (league/events/judge7.py `gate`: retired; at Probe or
    Sized with no stay judge for COST-7's versions; its run ended, refused or its three runs spent; a look due and not
    written, failing closed), None when it may buy. Unreadable reads as a reason (fail closed)."""
    from . import judge7 as J7

    try:
        return J7.gate(lane, program)
    except Exception as exc:  # noqa: BLE001 - fail closed
        return f"the learner's gate could not be read ({type(exc).__name__})"


def learner_cut(learners: Iterable[tuple[str, str]]) -> tuple[int, int] | None:
    """PREREG-EVL-7 SECTION 1.9's ROOM WITH ITS LEARNERS AT ONE AUCTION ((family, band) of each learner there that may
    take a name): the earliest learner's ROOM key (`room_key`), None with no learner. Every PREREG-EVL-1 to -6 row is
    given its names by the auction's own decision WHATEVER ITS BAND (the learner's pick waits for its own live receipt
    and keeps no room from any earlier row: the final text's section 1.9); only R3's BIRTHS AFTER THAT KEY in ROOM
    (`after_learners`: at learning every birth at learning; with a Probe learner its band's births, last of each pass
    after it, and every birth at learning) wait for the learners' decision of the auction (league/equity/live.py
    `_event_decide_lrn`), as a birth waits behind a waiting PREREG-EVL-5 buy (A113)."""
    keys = [tuple(room_key(family, band)) for family, band in learners]
    return min(keys) if keys else None


def after_learners(program: str, band: str | None, cut: Sequence[int] | None) -> bool:
    """Whether `program` at `band` waits for the learners' decision of the auction (`learner_cut`): an R3 birth whose
    ROOM key comes after the cut; never a PREREG row (they never wait on a learner) nor a learner."""
    if cut is None or P.is_learner(program):
        return False
    found = next((p for p in seatable() if p.id == program), None)
    return found is not None and found.spec is not None and tuple(room_key(program, band)) > tuple(cut)


def learner_pending(lane: Lane, program: P.Program, day: dt.date) -> bool:
    """Whether the learner's LIVE RECEIPT of `day`'s auction may still name it (PREREG-EVL-7 section 1.9): none of
    `learner.live_job` has finished, no other decision of the session is on record and no part failure is recorded
    (league/events/learner.py `live_state`, `PART_KEY`). The learners' decision of the auction waits on it each minute
    of the window, with no other bound (league/equity/live.py `_event_decide_lrn`)."""
    from . import learner as LR

    if LR.live_state(lane, program, day)["state"] != "waiting":
        return False
    rec = LR.decided(lane, program, day)
    if rec is not None and str(rec.get("kind")) != "live":
        return False
    return lane.meta(LR.PART_KEY.format(program=program.id, version=program.version, day=day.isoformat())) is None


def learner_picks(lane: Lane, program: P.Program, day: dt.date, *, decided_at: dt.datetime,
                  held: Callable[[str], bool] | None = None) -> list[Pick]:
    """THE REAL-MONEY PICKS OF A PREREG-EVL-7 LEARNER (section 1.9): its intents of its LIVE decision of `day`, only once
    its own live receipt of the auction has finished `ok` naming it (league/events/learner.py `live_picks`,
    `live_state`; none for an auction its part did not decide live, a receipt still running or not naming it, nor
    before the release), only while its gate is open (`learner_gate`)
    in its rank order, less the book's own skips: EVL-LRN-O1's ERN guard (E8, `ern_issuer`), EVL-LRN-ON's 8-K guard
    (E10, `issuer_8k_guard`), one position per issuer on the learner's earlier intents (`held_recently`) and on real
    lots (`held`). Each pick's `rank` is its place counted down from K (the first pick K), so the list's order is the
    learner's: no fitted figure goes to the book."""
    from . import learner as LR

    if learner_gate(lane, program) is not None:
        return []       # (PREREG-EVL-7 sections 1.9-1.10 and 3.1: no run, a look overdue, retired: `judge7.blocked`)
    got = LR.live_picks(lane, program, day)
    if not got:
        return []
    session = C.session(lane, day)
    out: list[Pick] = []
    for r in got:
        cik = str(r["cik"])
        if program.id == "EVL-LRN-O1" and ern_issuer(lane, cik, day, decided_at):
            continue
        if program.id == "EVL-LRN-ON" and issuer_8k_guard(lane, cik, session, decided_at):
            continue
        if held_recently(lane, program, cik, day) or (held is not None and held(cik)):
            continue
        try:
            prev = Decimal(str(r["prev_close"]))
        except (InvalidOperation, ValueError, TypeError):
            continue
        if not prev.is_finite() or prev <= 0:
            continue
        out.append(Pick(program.id, program.version, str(r["event"]), str(r["symbol"]).upper(), cik,
                        float(LR.K + 1 - int(r["rank"])), float(r["adv20"] or 0.0), prev, str(r["knowable_at"])))
    return out


# ----------------------------------------------------------------------------------- the decision scheduler (1019i)
def slot_of(program: Any) -> str:
    """Which file's slot of the timing table decides `program` (a Program or an id; league/events/scheduler.py
    `file_of`): "main" for every row of PREREG-EVL-1 to -6 and the births, a later file's key once its part is
    registered. The book's main pass plans buys only of main programs; a file's buys are planned by its own pass
    (league/equity/live.py `_event_decide_slot`), once its live receipt is made, inside its own send window."""
    from . import scheduler as X

    return X.file_of(program)


def slot_files(at: str) -> list[str]:
    """The files with a live slot at auction `at` whose part is registered (table order): the book's per-file passes."""
    from . import scheduler as X

    return [s.file for s in X.live_files(at)]


def send_window(file: str, at: str, open_at: float, close_at: float) -> tuple[float, float] | None:
    """The file's send window at auction `at` of a session (epoch seconds: [from, until)), from the timing table;
    None for a file with no slot there (the book sends nothing of it at that auction)."""
    from . import scheduler as X

    s = X.slot(file, at)
    return None if s is None else X.send_window(s, open_at, close_at)


def slot_catchup(file: str, at: str) -> bool:
    """Whether the file's slot at auction `at` has a catch-up (its rows of a session with no live run decided later by
    themselves, shadow only), False for a file with none (PREREG-EVL-10: such a session has no decision of its rows)."""
    from . import scheduler as X

    s = X.slot(file, at)
    return s is not None and s.catchup is not None


def slot_receipt(lane: Lane | None, file: str, at: str, day: dt.date) -> str | None:
    """The status of the file's LATEST live receipt of (`at`, `day`) (`decide-<kind>:<day>` of its slot): "ok" or
    "pending" (made: the book plans its buys), "failed" / "cut" / "missed" (final, never traded at that auction),
    "running", or None while there is none (the book waits inside the file's window). Unreadable reads as None."""
    from . import scheduler as X

    s = X.slot(file, at)
    if s is None or lane is None:
        return None
    try:
        row = lane.db.execute("SELECT status FROM receipts WHERE job=? ORDER BY id DESC LIMIT 1",
                              (s.receipt(day),)).fetchone()
    except sqlite3.Error:
        return None
    return None if row is None else str(row["status"] or "")


#: The words of `part_hold`'s wait for the lane's close decision, which every such buy's why carries to its end: the
#: book counts the buys that end unsent so (league/equity/live.py `_event_held_said`), and so does the lane's report
#: (league/events/report.py `HELD_UNSENT`, the same words).
PART_WAIT = "waits for the lane's own close decision"


def part_hold(lane: Lane | None, program: str, version: int, day: dt.date) -> tuple[str, str] | None:
    """PREREG-EVL-5 section 1.3, THE EARLIER ROWS' DECISION COMES FIRST, read by real money: a close whose lane decision
    finished without deciding this file's rows (its part failed or ran past its own bound: the receipt names none of
    them) is decided later by themselves and is NEVER TRADED for them. So a real-money buy of a PREREG-EVL-5 program at
    D's close goes only once the lane's FIRST finished close decision of D (`decide-close:<day>`, `ok` or `pending`)
    names the program (league/events/screen.py `names`): None (it may go). ("wait", why) while no such receipt exists
    (the buy waits, sent again each minute of its window: the reading that trades less); ("never", why) when that first
    finished receipt does not name it (the buy is refused; the shadow keeps the events). Every other program: None."""
    from . import screen as SN

    prog = P.BY_KEY.get((str(program), int(version)))
    if prog is None or prog.prereg != 5 or prog.spec is not None:
        return None
    if lane is None:
        return ("wait", f"{PART_WAIT}: no lane store to read it from")
    try:
        row = lane.db.execute("SELECT summary FROM receipts WHERE job=? AND finished_at IS NOT NULL AND status IN ('ok', "
                              "'pending') ORDER BY id LIMIT 1", (f"decide-close:{day.isoformat()}",)).fetchone()
    except sqlite3.Error as exc:
        return ("wait", f"{PART_WAIT}, which cannot be read ({type(exc).__name__})")
    if row is None:
        return ("wait", f"{PART_WAIT} of {day.isoformat()} to decide PREREG-EVL-5's rows (section 1.3: a close whose "
                        "part for them failed is never traded)")
    if SN.names(row["summary"], SN.program_key(prog.id, prog.version)):
        return None
    return ("never", f"the lane's close decision of {day.isoformat()} finished without PREREG-EVL-5's rows (their part "
                     "failed or ran past its own bound): decided later by themselves, never traded (section 1.3)")


def prereg_row(program: str, version: int) -> bool:
    """Whether (program, version) is a PREREG ROW: a program of PREREG-EVL-1 to -5 as this process knows it, not one of
    R3's births (whose rule is a registered spec) and not a program it does not know. Release 1019h (the captain's
    decision on PREREG-EVL-5's money re-review, option 1): the book's post-close alert (league/equity/live.py
    `_event_held_said`) is a warning when a later buy that ended unsent waiting for the room kept for PREREG-EVL-5's
    waiting buys is one."""
    prog = P.BY_KEY.get((str(program), int(version)))
    return prog is not None and prog.spec is None


def room_free_overdue(program: str, version: int) -> bool:
    """PREREG-EVL-5 section 1.3's WAITING ROOM ONCE THE LANE'S CLOSE RECEIPT IS OVERDUE (THE CAPTAIN'S DECISION on the
    money re-review of PREREG-EVL-5, its option 1; release 1019h; league/equity/live.py `HELD_OVERDUE_S`, `HeldAhead`):
    True for a row of PREREG-EVL-1 to -4 (any version of the earlier files' programs and of PREREG-EVL-4's rows: their
    PREREG-EVL-6 versions keep their file, `Program.prereg`), whose buy
    a waiting PREREG-EVL-5 buy no longer keeps its room from once the lane's close receipt is still unfinished one book
    minute before the close window's cut-off; False for PREREG-EVL-5's own rows, R3's births (the room is still kept
    from them) and a program this process does not know (the reading that keeps the room)."""
    prog = P.BY_KEY.get((str(program), int(version)))
    return prog is not None and prog.spec is None and prog.prereg in (1, 2, 3, 4)


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
           "lane_bands", "bands", "sessions_back", "FillWriter", "write_fills", "attempt_rows", "write_attempts",
           "ATTEMPTS_MARK", "ATTEMPTS_SLACK_S", "Pick", "rows_for", "rows_4",
           "held_recently", "picks", "next_open_event", "NEXT_OPEN_GUARD", "allocate", "one_name_an_auction", "t29",
           "minute_close", "last_session_before", "reaction_reader", "limit_price", "sigma", "weight", "exit_plan",
           "publish", "band_mark", "RAISED_GUARD", "rows_5", "lane_tickers", "opening_minute", "gap_reader",
           "part_hold", "PART_WAIT", "prereg_row", "room_free_overdue"]
#: (PREREG-EVL-7, release 1019i: the learners' real money, their gate and their place in ROOM's order; listed here, not
#: last, so release 1019i's other branches append below without touching these lines)
__all__ += ["is_learner", "ern_issuer", "issuer_8k_guard", "learner_gate", "learner_cut", "after_learners",
            "learner_pending", "learner_picks", "pick_record", "pick_of", "LINE_ACROSS_AUCTIONS"]
__all__ += ["slot_of", "slot_files", "send_window", "slot_receipt", "slot_catchup"]
#: (release 1019f: the probe size's record)
__all__ += ["SCHEMA_COLUMNS", "BINDINGS", "SIZING_BINDINGS", "binding_of"]
#: (release 1019f: A85's reservation and round-robin, with R3's births' tier)
__all__ += ["PROBE_UP", "RESERVE_DECISIONS", "reservation", "send_key", "ROUND_ROBIN_TIERS", "reserved_for",
            "leaves_room"]
#: (release 1019h, the captain's A97: S2's round-up to Done's size bar inside PREREG-EVL-1 section 8's envelope)
__all__ += ["envelope_share", "at_size", "round_up", "most_ask"]
#: (release 1019i: PREREG-EVL-6 section 6's skip of a pick no whole-share count brings to Done's size bar)
__all__ += ["under_bar", "at_size_count"]
