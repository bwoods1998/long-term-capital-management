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
missed, never re-sent, A80's one exception below reading only a cancel the venue itself stamped; an exit goes again only
while the account still holds what the book expects of the symbol, `_lost_sale_check`); one working order per symbol
across BOTH books (wash-trade protection: the options book's `busy()` symbols, the venue's working orders that are not
this book's, e.g. the House's assignment-share closes, and the equity book's). CANCEL THEN RESEND (A8.4): a
replacement goes only once the old order is terminal (filled, canceled, expired, rejected), sized target minus filled;
the old order's remaining quantity stays in exposure until then. A cancel is followed by one lookup of the order, so a
replacement can go in the same minute. ONE DAY ORDER COUNT (A8.3): the equity book's orders of a day (sends and
cancels, as the options book counts its own, exits' included) are counted against their lane's line: the old lanes'
against `order_path.max_orders_day` (60), THE EVENT KIND'S against its own, `equity_money.event.max_orders_day` (150,
release 1019c; `event_orders_today`): an ENTRY goes only while one more order leaves room for the exit of every open lot
of its lane (and one cancel of an old lane's), an event entry for its own exit and the exit of every event buy still
working that is sold the same day too; AN EXIT IS NEVER STOPPED BY A LANE'S COUNT (A28: an exit must never be blocked);
no order of any kind goes while the House-wide count (every lane's orders and the options book's) would leave less than
the options book's `exit_reserve()`, and no ENTRY while it would leave less than that and every equity exit's room
(`_exit_reserve`, both lanes; release 1019c's money review).

THE HOUSE'S MINUTE (the clock every window runs on): `tick(now)` is handed the minute's start, three seconds past the
wall minute, and runs AFTER the whole options minute, so its sends go later by however long that took (up to most of a
minute). A moment is due at the first minute at or after it: the open window's first send is the 09:31 minute's (09:30:30
is its earliest moment, never its send time), the close window's the 15:55 minute's, and a re-price goes at most once a
minute, its age counted in whole House minutes (`house_minute`) from the minute an order was sent in (`answer.tick`),
never in seconds between two minute starts (they are 60 seconds apart give or take milliseconds) and never from
`placed_at` (the wall clock at its POST). EVERY CUT-OFF IS JUDGED AGAIN ON THE WALL CLOCK at the send (`_send`):
nothing is written or POSTed at or
after its window's cut-off (09:45:00 an open entry, 15:59:30 every exit and every close entry), since a day order POSTed
at or after the close would rest for the next session; no order is cancelled for a re-price its replacement could
not follow; and one the venue still shows working on a later day than its own is cancelled wherever the minute finds
it (`_end_stale`). THE GATEWAY'S UNREAD READINGS (`RETRY_CAPS`: 424 positions, 424 orders, 503 equity, 409 stock_close; nothing
was sent and nothing judged) go again next minute like the House's own rate refusal: never an entry's end, never one of
the `MAX_EXIT_REFUSALS` that carry an exit to the next session; an order refused before the venue widens no collar.
ONE INTENT, ONE LOT: every fill of a buy intent's orders joins the lot its first fill opened (`_intent_lot`).
THE OWNER'S COMMANDS (`OWNER_FLATTEN`, `OWNER_CLEAR_FREEZE`: `python3 -m league.live --flatten-equity "<why>"`,
`--clear-equity-freeze "<why>"`) are key-values read first every minute and done once, in the House's own thread.

THE WINDOWS (`schedule`): OPEN: exits first at open+30 s (09:30:30 ET), entries after the exits filled or 2 minutes,
sized on cash after the exit fills (no entry is funded by an exit that has not filled: the account is read again before
the entries are sized, and an unfilled sale adds nothing to its cash); collar `entry_collar_bp` (10 ETF / 25 stock) on
the first send, widening by the same step each re-price to `max_collar_bp` (50 / 100), and at the widest collar
re-priced only when the quote has moved through the limit (`_reprice_due`: the day's order count is shared); entries stop at open+15 min
(09:45); exits continue to close-5 min (15:55), then go at the bid at the widest collar in the close window. CLOSE (A2):
at close-5 min (15:55:00) exits first, then entries once those exits filled or a minute passed (`CLOSE_EXIT_WAIT_S`: as
at the open, sized on the cash after the exits), marketable limits re-priced every 30 s to close-30 s (15:59:30), then
recorded missed. In either window an entry sized to nothing is not final while an exit may still fill (`_exits_due`): it
is sized again each minute, and its cut-off records it missed with the reason. PRE-OPEN (09:25): the day's first reconciliation reading and an activities read (a split or a
dividend posted overnight); the windows' orders are the decide's intents (`eq_intents`), each written `pending` at its
own send with that minute's quote, never at 09:25 with a pre-open price. A missed entry is recorded, never chased, with
ONE exception, the event kind's (the captain's A80, Oct 21, 2026: the venue cancelled about a quarter of the event
lane's auction buys milliseconds after it accepted them, with no reason): an event ENTRY whose last order THE VENUE
cancelled within `VENUE_CANCEL_RETRY_S` (60 s) of that order's own submission, nothing filled, is sent again ONCE, the
same symbol, side, size rule, limit, time in force and type under a new client id, through every gate, the sizing and
the cut-off again, while its auction's window is open (`_event_last`, `venue_cancel_ms`); a second such cancel, or one
later than 60 s (the auction's own end of an unfilled order), leaves it missed, and an exit is never re-sent so. An exit
the windows could not fill is recorded missed and carried to the next session's open (a "house_exit" intent of the same
reason). MIN HOLD: a lot never sells in the
session it was bought (kill switch and stops included; the gateway's kill blocks sells too). REAL SALES WAIT for the
stock paper proof's SELL stage (A10.1; the practice sale goes first in its window), AND THAT WAIT HAS AN END (A28): the
session's entry cut-off (`schedule.Moments.entry_until`, 09:45), the minute the book stops trying the open entries. From
it on every exit goes through the normal path whatever the stage says, and the owner is told once a session that the
sale path is unproven (`_sell_unproven`). NO STUCK LOTS (A8.5): a
lot held its program's `max_hold_sessions` exits at the next open; a demoted, retired or band-dropped program's lots
exit at the next open; 2 sessions of failed decides exit the program's lots at the next open; on a restart a catch-up
decide runs for the last close if it was missed (until the next session's close window). Limits: a buy rounds UP and a
sell DOWN to the cent ($1 and above; to 0.0001 under it: the venue's sub-penny rule); quantities are floored to
`config.QTY_PLACES` for a buy and sent whole (nine places at most) for a sale.

SIZING: `league.equity.sizing.size_entry` (money's; never re-implemented here), with the House-wide available cash of
`league.live.money.available_cash` (A8.1: `working_buys_worst` the equity book's working buys, `reserved` the options
book's working reservations, which cover its open orders' worst cost). Every real open asks `real_block(opening=True)`
first (grant, kill switch, stops, both books' reconciliation, the assignment latch, the House pause, the account read),
then its own gates: `equity_money.enabled`, the stock paper proof's BUY stage passed and its SELL stage not failed
(`paper_proof_stock_buy`, `paper_proof_stock_sell`: A8.7 as staged by A10.1), its own freeze,
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

THE PANEL KIND (release E4, package H; plumbing: no identity moves). An instance's `kind` (`eq_instances.kind`, from its
family's structure through `kinds.kind_of`) names the decider kind that runs it and, for a kind that is not the book's
own, the parent-side adapter the book asks (`kinds.BOOKS`: "panel" -> league/xs/book.py, `_adapter`). A panel program
trades through EVERY rule above (the windows, the sizing, the budget, the day count, reconciliation, the exports); what
differs is how its decision is made, in the `_panel_*` methods: its columns and ONE chunked fetch for every live panel
instance from 16:20, read again while a bar is missing (`_panel_bars`); its job, the lots marked first (`_panel_job`);
its answer recorded as intents with one `eq_rebalances` row a session, a rebalance recorded after the open window's
entry cut-off planning nothing at the open (`_panel_record`); the lots its child names ineligible exited at the next
open (`_panel_ineligible`); the bars it read kept and read again at 08:30 (`_panel_audit`); and its record for the band
rules read one observation a close DATE (`_panel_record_of`). The captain's A17: a HOLD day the House could not ask is
an alarm and counts toward no exit (`_decide_counts`), nor does a hold day that was asked reset the count. With no
instance of such a kind none of it runs: no fetch, no file, no call of the adapter but its import and its table.

THE SEAT RULE (release E5-A; the captain's A24 as amended by A30 before it went live; `equity_money.probe.seat`,
league/equity/bands.py `seat_settings`).
THE BOOK IS THE ONE SOURCE of who holds a seat and who waits: its plan is the kv `eq_seat` (`SEAT_KEY`), which
`health()["seats"]`, the swarm's `bands.roster(root, lanes=LANES)` and the dlane report all read; nobody else ranks.
- "first-come" (the rollback): `_sync_instances` is release E5-S's, to the line: the swarm's reader shows the
  Candidates that hold a seat by pass time, and the book moves them while its own count has room.
- "activity-1-free" (in force; `_seat_bands`): the reader shows every passed Candidate; a FREE seat goes to the
  best-ranked one (`bands.seat_order`: not idle-flagged first, the higher K, the earlier pass, the id), in the day's
  decision and in the seating pass alike, and a seating that does not take (the row changed, the band rule says no)
  FALLS THROUGH to the next in the same sync. EDM1 covers a waiting program that has a real record (it is marked
  sticky and never returns, with the same record and alert whether the day's pass or its own seating names it).
  THE IDLE SEAT, at the day's decision only: a seated program that is FLAT (`_flat`: no lot open or closing, no
  order that may still fill, no planned or sent intent) and has had no ASKED buy (`_last_ask`: a buy
  that reached the venue, or one the LOSS BUDGET cut or refused; a buy refused by the instrument cap, the invested
  cap or cash is not asked) for `idle_sessions` sessions of its seat is idle. It keeps its seat while no unflagged
  program is left waiting once every free seat is filled (FREE SEATS FIRST: A30 (1)); when one is, ONE idle
  program a decision day yields (`_yield`): its band goes back to Candidate,
  NOT sticky, its instance is retired with the reason "yielded", and it waits flagged idle, behind every unflagged
  program, until a seat is free (no new look; the same instance key, so its record goes on).
- THE IDLE CLOCK DOES NOT RUN WHILE THE HOUSE REFUSES EVERY OPEN (A30 (2); `_open_note`, `OPEN_NOTE_KEY`): a
  session with an entry window in which the House looked and never once would have opened, for a reason that is
  the House's and no program's, is left out of every program's seated sessions and of its sessions since its
  last asked buy.
- A LOST BUY IS NOT FLAT (A30 (3); `_flat`, `LOST_TAKE_BACK_DAYS`): an order the book gave up as lost may still be
  taken back when the venue shows it after all, and until it cannot be, and a day more, its program is not flat.
  More widely: a program is flat only when the order path has no order of its own left to read the venue for, so
  no lot can be booked to a program after it yielded.
- THE RULE ONLY DECIDES WHO MAY OPEN NEXT. It retires an instance only inside the one state transaction that found
  it flat, so `_house_exits` has nothing of it to sell; it plans no exit, cancels no order and makes no trading
  program exit-only. Outranking is not built here.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import re
import sqlite3
import time
import traceback
from dataclasses import dataclass, field, replace
from decimal import ROUND_CEILING, ROUND_DOWN, ROUND_FLOOR, Decimal
from pathlib import Path
from typing import Any, Callable, Collection, Iterable, Mapping, Sequence

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
from . import kinds as K
from . import program as P
from . import schedule as S
from . import sizing as Z
from .store import STORE_DIR

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
#: "ineligible" (release E4): a panel lot whose name left the eligible set at a close (league/xs/book.py `INELIGIBLE`).
HOUSE_REASONS = ("max_hold", "house", "demoted", "retired", "flatten", "forced", "carried", "ineligible")
#: The collars when the equity table cannot be read (exits only then): the design's.
DEFAULT_COLLARS = {"entry": {"etf": 10, "stock": 25}, "max": {"etf": 50, "stock": 100}}
#: Seconds between two reads of the activities (`actions.TYPES`), and of the watched types (`actions.WATCH`).
ACTIVITIES_EVERY = 900.0
WATCH_EVERY = 3600.0
#: An unknown order is lost when the venue still does not show it by its client id after this many lookups or seconds.
LOST_AFTER_TRIES = 4
LOST_AFTER_S = 600.0
#: A LOST ORDER'S TAKE-BACK (`EquityBook._sync_orders`): an order given up as lost is still looked for in the venue's
#: orders while its session's day is within this many calendar days of the New York day of the minute; one the venue
#: shows after all is working again and its fills are booked to its instance's lot. After it the order path never
#: books a fill of that order (shares nobody owns are the reconciliation's to find).
LOST_TAKE_BACK_DAYS = 3
#: ... and THE SEAT RULE reads a lost order as one that MAY STILL FILL for one day longer (`EquityBook._flat`; the
#: captain's A30 (3)): the order path reads the day off the minute's `now` and the seat rule off the wall clock, which
#: may already be the next New York day when the equity minute runs late, so the seat rule's window is the wider one
#: by a whole day. A program is never read flat, and so never yields its seat, while the order path could still
#: book a lot to it.
LOST_HOLDS_SEAT_DAYS = LOST_TAKE_BACK_DAYS + 1
#: A pending row younger than this is being sent right now (never looked up yet).
PENDING_GRACE_S = 30.0
#: Lookups by client id a minute, at most.
LOOKUP_LIMIT = 6
#: A cancel is not sent again for the same order within this many seconds.
CANCEL_AGAIN_S = 50.0
#: THE OWNER'S COMMANDS (`python3 -m league.live --root <state> --flatten-equity "<why>"` and `--clear-equity-freeze
#: "<why>"`, league/live/__main__.py): key-values only the owner's command writes ({why, at, by}). The tick reads them
#: every minute, acts once in the House's own thread and deletes them (`EquityBook._owner`), as the options path reads
#: `owner_clear_assignment`.
OWNER_FLATTEN = "owner_equity_flatten"
OWNER_CLEAR_FREEZE = "owner_equity_clear_freeze"
#: A symbol whose equity order is working, or ended this recently, is not reconciled that minute.
FLUX_S = 120.0
#: An exit the gateway or the venue refused this many times in a session is carried to the next one (and alarmed).
MAX_EXIT_REFUSALS = 3
#: THE GATEWAY'S "NOTHING WAS SENT, SEND IT AGAIN" ANSWERS, by their `cap` (gateway/lib/router.mjs and gate.mjs: 424
#: `positions` and `orders`, the account's book could not be read; 503 `equity`, the account could not be read; 409
#: `stock_close`, an earlier close of the same shares is still held in flight, a minute at most): a reading that could
#: not be made, never a verdict on the order. Like the House's own rate refusal the order goes again next minute until
#: its window's cut-off: never an entry's end, never one of the `MAX_EXIT_REFUSALS` that carry an exit to the next
#: session (the owner is told once a day a lot when an exit met `MAX_EXIT_REFUSALS` of them).
RETRY_CAPS = ("positions", "orders", "equity", "stock_close")
#: ... and an EVENT buy's own (release R2, gateway G2): its asset or its bars could not be read (424 `asset`, `bars`),
#: or the gateway holds no eligible list of the day yet (403 `stock_eligible`: the book publishes it again). Nothing was
#: sent; it goes again next minute until its auction's cut-off.
EVENT_RETRY_CAPS = RETRY_CAPS + ("asset", "bars", "stock_eligible")
#: THE CLOSE WINDOW's wait (A2: close exits, then close entries, sized on the cash after the exits): its entries wait
#: this long after `close_send` for the window's exits to fill, then go on the cash there is (the open window's
#: `exit_wait_s` is 120 s of fifteen minutes; this is one House minute of the close's four and a half).
CLOSE_EXIT_WAIT_S = 60.0
#: The widest quoted spread an entry is sized on (a wider quote waits a minute): a fraction of the mid.
MAX_ENTRY_SPREAD = Decimal("0.02")
#: Seconds after `decide_at` the decide waits for a missing bar before deciding without it (those instances fail).
BARS_GRACE_S = 1800.0
#: THE SEATING PASS (`EquityBook._seat_step`): seconds before an instance the House could not ask is asked again for
#: the same close (a program seated since the day's decision is asked at once).
SEAT_RETRY_S = 600.0
#: A program's decide: its per-call limit and error budget (the Gym runner's).
DECIDE_TIMEOUT = 1.0
DECIDE_MAX_ERRORS = 25
#: RELEASE E4. The book's own decider kind (league/equity/child.py); an instance of another kind is asked through its
#: parent-side adapter (`kinds.BOOKS`).
EQUITY_KIND = "equity"
#: The panel kind (release E4: league/xs/book.py) and THE EVENT KIND (release R2: league/events/book.py). Every dispatch
#: that once read "not the book's own kind" as the panel names its kind now (the map of R2: `_decide`, `_seat_step`,
#: `_sleeve_share`, the pools, `_cut_waits`, `_decide_counts`, `_seat_block`): an event instance is never the panel's.
PANEL_KIND = "panel"
EVENT_KIND = "event"
#: An event lot's lane (league/events/book.py `LANE`; a test holds them equal, so this module names it without importing
#: league/events) and the weight a lot of it counts at when its own cannot be read or it is held past its scheduled exit
#: (`book.STRICT_WEIGHT`: the House's stock floor before release R2).
EVENT_LANE = "event"
EVENT_STRICT_WEIGHT = Decimal("0.40")
#: The bands an event program trades in (league/events/book.py `LIVE_BANDS`, PREREG-EVL-3 section 2; a test holds them
#: equal): learning from birth, Probe, Sized.
EVENT_LIVE_BANDS = ("learning", "probe", "sized")
#: THE CAPTAIN'S A80 (16:10Z Oct 21, 2026: the venue cancelled about a quarter of the event lane's auction buys 5-6 ms
#: after it accepted them, with no reason and nothing filled; the cause is the venue's and unknown). An event ENTRY
#: whose last order THE VENUE cancelled within this many seconds of that order's own submission (`venue_cancel_ms`: the
#: venue's `canceled_at` less its `submitted_at`), nothing filled, is sent again ONCE (`EquityBook._event_last`). The
#: venue ends every unfilled auction order at its cross, minutes after it was sent: such a cancel is past this, and the
#: buy stays missed.
VENUE_CANCEL_RETRY_S = 60
#: ... the venue writes `submitted_at` to the nanosecond and `canceled_at` to the millisecond, so a cancel inside the
#: order's own millisecond can read up to this much BEFORE its submission (and is read as 0 ms).
VENUE_STAMP_SLACK_S = 0.001
#: kv: the New York day of A80's one alert of a session (`EquityBook._venue_cancel_said`), written only on a day it
#: said one.
VENUE_CANCEL_SAID = "eq_venue_cancel_said"
#: What an A80 re-send held by a gate says on its intent (`_event_work_entry`); the auction's end reads it back.
A80_HELD = "A80's one re-send held: "
#: kv: the lane's band mark (league/events/book.py `band_mark`) the session's last band sync read (release 1019f): the
#: close decision reads the bands again when the lane's mark differs (`_event_bands_due`).
EVENT_BAND_MARK = "eq_event_band_mark"
#: `eq_orders.tif` and `eq_orders.otype` (release R2: an auction order's time in force, `opg` or `cls`, and a market
#: sale's type), added to a state from before it by these statements, guarded by PRAGMA table_info as `kind` is.
ORDER_COLUMNS_DDL = {"tif": "ALTER TABLE eq_orders ADD COLUMN tif TEXT NOT NULL DEFAULT 'day'",
                     "otype": "ALTER TABLE eq_orders ADD COLUMN otype TEXT NOT NULL DEFAULT 'limit'"}
#: `eq_instances.kind`, added to a state from before release E4 by this statement, guarded by PRAGMA table_info and
#: by reading another first open's "duplicate column name" as done (league/xs/book.py `INSTANCE_KIND_DDL` says the same
#: words; a test holds the two equal).
INSTANCE_KIND = "kind"
INSTANCE_KIND_DDL = "ALTER TABLE eq_instances ADD COLUMN kind TEXT NOT NULL DEFAULT 'equity'"
#: A panel decide first ready this many seconds after `decide_at` is said (a warning: 16:40 ET).
PANEL_LATE_S = 600.0
#: A hold day's buys from the standing target that have gone on for this many sessions are said (a warning).
STANDING_WARN_SESSIONS = 5
#: A rebalance with more than this share of its orders skipped is said (a warning).
SKIPPED_WARN_SHARE = 0.10
_SQL_COMMENT = re.compile(r"--[^\n]*")
#: How many sessions before a dividend's date the book looks for the holding its quantity names.
DIVIDEND_LOOKBACK_SESSIONS = 70
#: Closed lots exported a minute, at most.
EXPORT_LIMIT = 50
#: THE BROKER'S FEES (`_fees`): the venue's daily regulatory fee rows on equity sales (`FEE` activities with no order id,
#: their description starting "REG" or "TAF"; an option's read "OPT REG", "OPT TAF", "ORF", "CAT", as
#: league/ops/economics.py reads them), and the sales' proceeds a row states ("... of $1234.56 ...").
FEE_LABEL = re.compile(r"^(REG|TAF)\b")
FEE_PROCEEDS = re.compile(r"of \$(\d+(?:\.\d+)?)")
#: Sessions after a lot's exit day without a fee row for that day before the owner is told (once a lot).
FEES_LATE_SESSIONS = 5
#: THE SEAT RULE (the module docstring): the kv of the book's seat plan and memory ({rule, seats, day, holders, waiting,
#: idle {family: {day, why}}, yield_day, passed {family: day}, left_out [{day, why}], last}: rank positions, never K);
#: how a yielded instance's `why` starts; and the words `league.equity.sizing.size_entry` names the loss budget's cap
#: by (its `why["budget"]`), which is how a buy cut under the minimum order says that the budget cut it (a test holds
#: them).
SEAT_KEY = "eq_seat"
#: THE TWO POOLS OF SEATS (release E4 step two; `equity_money.panel`, league/equity/bands.py `panel_settings`): the
#: ETF pool (`probe.max_programs`, the book's own kind: what main's seat rule always meant) and the PANEL pool
#: (`panel.seats`, every instance of another kind). Each pool's rule runs over its own rows only, so a panel program
#: never takes, holds or yields an ETF seat. The ETF pool's plan is `SEAT_KEY` as before, to the key; the panel
#: pool's is kept under the key `SEAT_PANEL` inside it, written only once a panel row was ever seen.
POOL_ETF, POOL_PANEL = "etf", "panel"
SEAT_PANEL = "panel"
YIELDED = "yielded"
BUDGET_WORDS = "the shared loss budget has"
#: THE OPEN NOTE (the captain's A30 (2); `EquityBook._open_note`, `_refused_days`): the kv in which the book keeps, a
#: session and an entry window ("open": the minutes the open's entries are worked, from 09:30:30 or the two minutes
#: its exits are given, to 09:45; "close": 15:55 or the minute its exits are given, to 15:59:30), whether the House
#: would have let a real equity open go at ANY minute it looked there: {day: {window: {"clear": bool, "why": the
#: House-wide refusal it last met while never clear}}}. A session with a window the House looked in and never once
#: would have opened in is A SESSION IN WHICH THE HOUSE REFUSED EVERY OPEN: it is left out of every program's seated
#: and quiet sessions for the idle test. The answer is `_open_block`'s for ANY program (asked with `OPEN_PROBE`, an
#: instance that is live by construction), so it is exactly what `_open_block` says before it looks at the instance;
#: the book writes the note from that answer alone, at every minute the window's entries are worked, whether or not
#: any program planned a buy. Nothing a program writes reaches it: not an intent, not a tag, not a reason. Kept only
#: while the seat rule is in force (under "first-come" nothing is idle and the book asks nothing extra).
OPEN_NOTE_KEY = "eq_open_note"
#: Calendar days a refused session's note is kept; an older one counts for the idle clock again (it could matter only
#: to a seat with fewer than `idle_sessions` counted sessions in all that time). A session every window of which was
#: clear is dropped the day after: only a refusal is ever read.
OPEN_NOTE_KEEP_DAYS = 400
#: C1 (A45, the scaling plan's span buy-and-hold; `span_bh`, `b10_bh`, read by the `dlane` report): the one basis every
#: span close is read on, as `_bh_pnl` reads its two (total return: adjusted for every event to the day of its fetch).
SPAN_BASIS = "adjustment=all"
#: B10's market symbol (league/xs/config.py `REF[MARKET_COLUMN]`, which `date_record`'s SPY closes are fetched for; a
#: test holds the two equal, so this module names it without importing league/xs).
B10_SYMBOL = "SPY"
_SLUG = re.compile(r"[^a-z0-9-]+")
_DAY = re.compile(r"\d{4}-\d{2}-\d{2}")


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


def house_minute(t: float) -> int:
    """THE HOUSE MINUTE a pass's `now` is in: the wall minute it started in (league/live/step.py starts each pass
    `MINUTE_OFFSET` seconds into its minute, plus the wait's own lateness, so a start is never near a minute's edge)."""
    return int(float(t) // 60)


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


def _side(value: Any) -> Decimal | None:
    """One side of a venue quote (or a trade's price) as a price: a finite Decimal above zero, else None (no side)."""
    price = A.dec(value)
    return price if price is not None and price > 0 else None


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
    for r in rows("SELECT family, class, qty, entry_px, mark, status, cash, exit_day, closed_at, probe, lane, info FROM "
                  "eq_lots WHERE substr(instance, -2)=?", (REAL_SUFFIX,)):
        if r["status"] == LOT_CLOSED:
            # (Release R2: an EVENT lot's close counts whatever its band was, Probe or Sized: the goal's loss budget is
            # every real event's, PREREG-EVL-1 section 8.)
            if int(r["probe"] or 0) == 1 or r["lane"] == EVENT_LANE:
                closes.append((float(r["closed_at"] or 0.0), r["exit_day"] or None, D(r["cash"], ZERO)))
            continue
        qty = D(r["qty"], ZERO)
        if qty <= 0:
            continue
        weight = event_lot_weight(r) if r["lane"] == EVENT_LANE else _weight(weights, r["class"])
        risk += weight * qty * _price(r)
        programs.add(str(r["family"]))
    if _has_table(rows, "eq_orders"):
        events = _has_table(rows, "eq_event_intents")
        for r in rows("SELECT family, class, qty, filled_qty, limit_px, iid FROM eq_orders WHERE side='buy' "
                      "AND substr(instance, -2)=? AND status IN ('pending', 'working', 'unknown')", (REAL_SUFFIX,)):
            remaining = max(ZERO, D(r["qty"], ZERO) - D(r["filled_qty"], ZERO))
            weight = _weight(weights, r["class"])
            if events and r["iid"] is not None:
                side = rows("SELECT weight FROM eq_event_intents WHERE iid=?", (int(r["iid"]),))
                if side:
                    weight = _event_weight_of(side[0]["weight"])
            risk += weight * remaining * D(r["limit_px"], ZERO)
            programs.add(str(r["family"]))
    closes.sort(key=lambda c: c[0])
    return ProbeFigures(len(programs), tuple((day, cash) for _, day, cash in closes), risk)


def _timed_out(exc: BaseException | None) -> bool:
    """Whether a read failed by running into a timeout: the exception, or one it wraps (`reason`, `__cause__`,
    `__context__`), is a TimeoutError (socket.timeout included) or says "timed out" or "timeout" (a gateway's 504 too)
    (release 1019b's third review: a T29 request that timed out is never sent again in the same minute)."""
    seen: set[int] = set()
    while exc is not None and id(exc) not in seen and len(seen) < 8:
        seen.add(id(exc))
        text = str(exc).lower()
        if isinstance(exc, TimeoutError) or "timed out" in text or "timeout" in text:
            return True
        reason = getattr(exc, "reason", None)
        exc = reason if isinstance(reason, BaseException) else (exc.__cause__ or exc.__context__)
    return False


def _event_weight_of(value: Any) -> Decimal:
    """An event lot's or buy's own open-risk weight (league/events/book.py `weight`): a Decimal in (0, 1], else the
    stricter `EVENT_STRICT_WEIGHT` (fail closed: a weight that cannot be read never counts less)."""
    weight = A.dec(value)
    return weight if weight is not None and Decimal(0) < weight <= 1 else EVENT_STRICT_WEIGHT


def event_lot_weight(row: Mapping[str, Any]) -> Decimal:
    """THE GOAL'S OPEN-RISK RULE for an open EVENT lot (release R2; PREREG-EVL-1 section 8): its own weight, max(0.10,
    1.65 x sigma60 x sqrt(h)) as its buy recorded it (`info.evl.weight`), or `EVENT_STRICT_WEIGHT` when it cannot be read
    or the lot is held past its scheduled exit (`info.evl_exit.rung` >= 1: an auction printed nothing for its sale, so
    its hold is no longer the one its weight was computed for); its WHOLE value (1) once the ladder's 20th session after
    its planned exit closed with the lot still held (`info.evl_exit.zero`: PREREG-EVL-1 section 5's "at 0 after 20
    sessions", read by the loss budget as a total loss while the shares are still offered for sale)."""
    info = loads(row.get("info"), {}) if not isinstance(row.get("info"), Mapping) else row.get("info")
    info = info if isinstance(info, Mapping) else {}
    plan = info.get("evl_exit") if isinstance(info.get("evl_exit"), Mapping) else {}
    if plan.get("zero"):
        return Decimal(1)
    if int(plan.get("rung") or 0) >= 1:
        return EVENT_STRICT_WEIGHT
    evl = info.get("evl") if isinstance(info.get("evl"), Mapping) else {}
    return _event_weight_of(evl.get("weight"))


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
    is not counted. Every lane's together: the House-wide count's equity part (league/live/real.py `house_count`); the
    event kind's own part is `event_orders_today`, the old lanes' the rest (release 1019c)."""
    if not _has_table(rows, "eq_orders"):
        return 0
    return _count_orders(rows("SELECT status, day, answer FROM eq_orders WHERE day=? OR answer LIKE ?",
                              (day, '%"cancel_day":%')), day)


def event_orders_today(rows: Callable[..., list], day: str) -> int:
    """THE EVENT KIND'S OWN DAY ORDER COUNT (release 1019c): `orders_today` of the orders of an event instance
    (`eq_instances.lane` "event": the kind's auction buys and sales, and its fallback ladder's day sales with their
    cancels), counted against `equity_money.event.max_orders_day`; the old lanes' orders (`orders_today` less these)
    count against `order_path.max_orders_day`."""
    if not _has_table(rows, "eq_orders") or not _has_table(rows, "eq_instances"):
        return 0
    return _count_orders(rows("SELECT o.status, o.day, o.answer FROM eq_orders o JOIN eq_instances i ON i.id=o.instance "
                              "WHERE i.lane=? AND (o.day=? OR o.answer LIKE ?)", (EVENT_LANE, day, '%"cancel_day":%')), day)


def _count_orders(found: Iterable[Mapping[str, Any]], day: str) -> int:
    """The day order count of these order rows: each sent (or pending) on `day`, and each cancel made on `day`."""
    n = 0
    for r in found:
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
    #: Release R2: the order's time in force ("day"; an event order's auction, "opg" or "cls") and type ("limit"; an
    #: event sale's "market").
    tif: str = "day"
    otype: str = "limit"

    @property
    def working(self) -> bool:
        return self.status in WORKING

    @property
    def auction(self) -> bool:
        """An order of the opening or the closing auction (an event order): never re-priced, never cancelled for a
        re-price, never ended by `_end_stale` on its own session."""
        return self.tif in ("opg", "cls")

    @property
    def remaining(self) -> Decimal:
        return max(ZERO, self.qty - self.filled_qty)

    @property
    def filled_value(self) -> Decimal:
        return self.filled_qty * (self.avg_px or ZERO)

    @property
    def again(self) -> bool:
        """A refusal that says nothing of the order itself (the House's own rate, or a reading the gateway could not
        make: `RETRY_CAPS`): nothing was sent, and it is sent again next minute."""
        return self.status == "refused" and bool(self.answer.get("house") or self.answer.get("retry"))

    def row(self) -> dict:
        return {"eid": self.eid, "client_id": self.client_id, "venue_id": self.venue_id, "instance": self.instance,
                "family": self.family, "lid": self.lid, "iid": self.iid, "side": self.side, "symbol": self.symbol,
                "class": self.klass, "at": self.at, "qty": text(self.qty), "limit_px": text(self.limit_px),
                "collar_bp": int(self.collar_bp), "status": self.status, "placed_at": self.placed_at, "day": self.day,
                "filled_qty": text(self.filled_qty), "avg_px": None if self.avg_px is None else text(self.avg_px),
                "fees_est": text(self.fees_est), "replaces": self.replaces, "probe": int(self.probe),
                "why": self.why, "answer": dumps(self.answer), "updated_at": self.updated_at, "attempts": self.attempts,
                "tif": self.tif, "otype": self.otype}

    @classmethod
    def of(cls, r: Mapping[str, Any]) -> "Order":
        return cls(int(r["eid"]), r["client_id"], r["instance"], r["family"], r["side"], r["symbol"], r["class"],
                   r["at"], D(r["qty"], ZERO), D(r["limit_px"], ZERO), int(r["collar_bp"]), r["status"],
                   float(r["placed_at"]), r["day"], r["venue_id"], r["lid"], r["iid"], D(r["filled_qty"], ZERO),
                   A.dec(r["avg_px"]), D(r["fees_est"], ZERO), r["replaces"], bool(r["probe"]), r["why"] or "",
                   loads(r["answer"], {}) or {}, float(r["updated_at"]), int(r["attempts"] or 0),
                   str(r.get("tif") or "day"), str(r.get("otype") or "limit"))


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
    kind: str = EQUITY_KIND

    @property
    def live(self) -> bool:
        if self.kind == EVENT_KIND:     # (release R2: an event program trades from learning, PREREG-EVL-3 section 2)
            return self.retired_at is None and self.band in EVENT_LIVE_BANDS
        return self.retired_at is None and self.band in LIVE_BANDS

    def row(self) -> dict:
        return {"id": self.id, "family": self.family, "version": self.version, "lane": self.lane,
                "run_sha": self.run_sha, "code": self.code, "params": dumps(self.params), "band": self.band,
                "seeded": int(self.seeded), "max_hold": int(self.max_hold), "failed_decides": int(self.failed_decides),
                "last_decided_day": self.last_decided_day, "created_at": self.created_at, "retired_at": self.retired_at,
                "why": self.why[:400], "kind": self.kind}

    @classmethod
    def of(cls, r: Mapping[str, Any]) -> "Instance":
        return cls(r["id"], r["family"], int(r["version"]), r["lane"], r["run_sha"], r["code"],
                   loads(r["params"], {}) or {}, r["band"], bool(r["seeded"]), int(r["max_hold"]),
                   int(r["failed_decides"] or 0), r["last_decided_day"], float(r["created_at"]), r["retired_at"],
                   r["why"] or "", str(r.get("kind") or EQUITY_KIND))


#: ANY PROGRAM, for the open note (`OPEN_NOTE_KEY`): an instance that is live whatever the book holds, so that
#: `EquityBook._open_block` answers for the House alone.
OPEN_PROBE = Instance("", "", 0, "", "", "", {}, LIVE_BANDS[0], False, 0)


def instance_key(family: str, version: int) -> str:
    """`<family>@<version>:r`: the real evidence route's instance, as the options book's."""
    return f"{family}@{int(version)}{REAL_SUFFIX}"


def order_body(order: Order) -> dict[str, Any]:
    """The venue's body: a simple limit day order in shares, never notional, never extended hours (the gateway's
    `stockBuyOrder` and `realStockClose` read exactly these fields). RELEASE R2: an event order carries its own type
    and time in force (`order.tif`, `order.otype`): a whole-share limit-on-open or limit-on-close buy (the gateway's
    `eventBuyOrder`), a market-on-open or market-on-close sale (no limit price; `realStockClose`)."""
    body = {"symbol": order.symbol, "qty": qty_text(order.qty), "side": order.side, "type": order.otype or "limit",
            "limit_price": text(order.limit_px), "time_in_force": order.tif or "day", "client_order_id": order.client_id}
    if body["type"] == "market":
        del body["limit_price"]
    return body


def venue_cancel_ms(order: Order) -> int | None:
    """A80: the milliseconds THE VENUE took to cancel this order after its own submission, read off the venue's own
    stamps (`answer.submitted_at`, `answer.canceled_at`, RFC 3339, `league.live.venue.parse_time`), when it is an
    AUCTION BUY (an event entry's) the venue ended `canceled` within `VENUE_CANCEL_RETRY_S` of its submission with
    nothing filled and no cancel of the House's own sent (`cancel_sent`). None otherwise: a sale, a fill, an order the
    House cancelled, one the venue replaced or ended otherwise, a stamp missing or unreadable, a cancel later than that
    (the auction's own end of an unfilled order) or one stamped before its submission (beyond `VENUE_STAMP_SLACK_S`)."""
    answer = order.answer
    if order.side != "buy" or not order.auction or order.status != "canceled" or answer.get("final") != "canceled":
        return None
    if order.filled_qty > 0 or "cancel_sent" in answer:
        return None
    submitted, canceled = parse_time(answer.get("submitted_at")), parse_time(answer.get("canceled_at"))
    if submitted is None or canceled is None:
        return None
    took = canceled - submitted
    if not -VENUE_STAMP_SLACK_S <= took <= VENUE_CANCEL_RETRY_S:
        return None
    return max(0, int(round(took * 1000)))


def venue_cancels(orders: Sequence[Order]) -> list[tuple[Order, int]]:
    """A80: the orders of one event buy (in send order) the venue cancelled at once (`venue_cancel_ms`), each with the
    milliseconds it took."""
    return [(o, n) for o in orders for n in (venue_cancel_ms(o),) if n is not None]


def venue_cancel_note(orders: Sequence[Order], why: str = "") -> str:
    """A80's words for the end of an event buy whose orders the venue cancelled at once ("" when it did not): both
    cancels; the one, and why its re-send did not go (`why`, the intent's, when a gate held it: `A80_HELD`); or the
    one re-send that went."""
    cancels = venue_cancels(orders)
    if not cancels:
        return ""
    first, took = cancels[0]
    if len(cancels) > 1:
        return (f"the venue cancelled the first buy {took} ms after its submission and A80's one re-send "
                f"{cancels[1][1]} ms after its own, nothing filled")
    if orders[-1].eid == first.eid:
        held = why if why.startswith(A80_HELD) else "A80's one re-send did not go before the window's cut-off"
        return f"the venue cancelled it {took} ms after its submission, nothing filled; {held}"
    return f"A80's one re-send of the buy the venue cancelled {took} ms after its submission"


def _sha(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _bar_day(row: Mapping[str, Any]) -> str | None:
    stamp = parse_time(row.get("t"))
    return None if stamp is None else S.ny_day(stamp).isoformat()


def _iso(t: float) -> str:
    return dt.datetime.fromtimestamp(float(t), dt.timezone.utc).isoformat()


def _lane_iso(t: float) -> str:
    """An instant as the event lane's store writes one (league/events/store.py `iso`: UTC to the second, a `Z`)."""
    return dt.datetime.fromtimestamp(float(t), dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def wall_equity(E: Decimal, account: Mapping[str, Any] | None) -> Decimal:
    """RELEASE 1019f, THE WALLS' EQUITY (the audit's capacity lens; the reading that trades less): the lower of `E`, the
    event kind's sizing equity (the House's sizing equity, never above the account's `last_equity`), and the account's
    CURRENT equity as the House last read it (`equity`, the minute's reading), the figure the gateway judges an event
    buy's 10% a name and the whole book against: a buy sized near 10% of the previous close's equity on a day the
    account is down otherwise meets the gateway's final refusal (`stock_position`). An `equity` that is absent or cannot
    be read leaves `E` as it is (as an unreadable `last_equity` does: the gateway, which reads the account itself,
    refuses a buy it cannot judge); one at or below zero is read as it is (no buy fits)."""
    now = A.dec((account or {}).get("equity"))
    return E if now is None else min(E, now)


class _NoYield(Exception):
    """Raised inside `EquityBook._yield`'s transaction to roll it back: the swarm's store did not take the band."""


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
            # B1 (release E4): an instance's decider kind. A state from before it gains the column; every row reads
            # "equity".
            if not self._has_instance_kind():
                try:
                    self.state.execute(INSTANCE_KIND_DDL)
                except sqlite3.OperationalError as exc:
                    # Another process's first open of the same state added it between the look and the ALTER (two
                    # builders of the book at once): the column is there, which is all this asks (as
                    # league/ops/forward_db.py `_migrate` since release E3.1). Anything else is raised.
                    if "duplicate column name" not in str(exc).lower() or not self._has_instance_kind():
                        raise
            # RELEASE R2: an order's time in force and type (an event order's auction). A state from before it gains
            # the two columns; every row reads a day limit order, as it was.
            for column, ddl in ORDER_COLUMNS_DDL.items():
                if column in self._order_columns():
                    continue
                try:
                    self.state.execute(ddl)
                except sqlite3.OperationalError as exc:
                    if "duplicate column name" not in str(exc).lower() or column not in self._order_columns():
                        raise
        #: RELEASE E4: the parent-side adapters by kind (`_adapter`: None for one that cannot be imported), and the
        #: panel's own memory in this process: the day's columns and fetch (`_panel_bars`), the morning's re-read
        #: (`_panel_audit`).
        self._adapters: dict[str, Any] = {}
        self._panel: dict[str, Any] = {}
        self._panel_again: dict[str, Any] = {}
        for kind in K.BOOKS:
            self._adapter(kind)
        #: RELEASE R2: the event kind's memory in this process (the auction proof, built on first use), and whether the
        #: event adapter's table is in this state (the windows of the old lanes leave its intents to `_event_step`).
        self._auction: Any = None
        self._event_lane: Any = None
        #: A80: the New York day whose venue cancels this process has read for the session's one alert
        #: (`_venue_cancel_said`).
        self._venue_said: str | None = None
        #: instance -> (code sha, params) loaded in the decider child this process; its NEEDS as the child read them.
        self._loaded: dict[str, tuple[str, str]] = {}
        self._needs: dict[str, dict[str, Any]] = {}
        #: The 16:20 bars kept for the 16:30 decide: {"day", "symbols", "raw", "all", "start", "fetched_at"}.
        self._bars: dict[str, Any] | None = None
        self._activities_at = float("-inf")
        self._watch_at = float("-inf")
        self._fees_at = float("-inf")
        self._phase = "closed"
        self._last: dict[str, Any] = {}
        # Per minute: the readings the book made itself (`_tick_reset`).
        self._account_now: Mapping[str, Any] | None = None
        self._positions_now: list[dict] | None = None
        self._open_now: list[dict] | None = None
        self._quotes: dict[str, dict] = {}
        #: RELEASE E4: {instance: why it may open nothing | None} of this pass (`_seat_block`).
        self._seats: dict[str, str | None] = {}
        self._minute_positions: Sequence[Mapping[str, Any]] | None = None
        self._minute_open: Sequence[Mapping[str, Any]] | None = None
        recon = self.state.get("eq_recon", {}) or {}
        self._streak = {"bad": int(recon.get("bad") or 0), "good": int(recon.get("good") or 0)}

    # ------------------------------------------------------------------ plumbing
    def _has_instance_kind(self) -> bool:
        """Whether the state's `eq_instances` holds the column `kind` (PRAGMA table_info, read afresh each call)."""
        return INSTANCE_KIND in {str(r["name"]) for r in self.state.rows("PRAGMA table_info(eq_instances)")}

    def _order_columns(self) -> set[str]:
        """The columns of the state's `eq_orders` (PRAGMA table_info, read afresh each call)."""
        return {str(r["name"]) for r in self.state.rows("PRAGMA table_info(eq_orders)")}

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

    # ------------------------------------------------------------------ shares an assignment took (A8.2)
    def shares_taken(self, symbol: str, qty: Decimal, px: Decimal | None, *, why: str) -> Decimal:
        """SHARES AN ASSIGNMENT TOOK (league/live/step.py `_lots_taken`, through league/live/equity_hook.py): `qty`
        shares of `symbol` that this book's lots held are no longer on the account. An option's assignment or exercise
        delivered them (the account went short while the book owned them); the gateway admits no buy that both covers
        and opens, so they are never bought back. The symbol's open lots are closed for that many shares, oldest
        first, as "forced" at `px`, the price the House's cover of that short filled at (a lot's last mark, else its
        entry price, when `px` is None: the cover's price is unreadable, or the short was closed outside the House):
        no fee (the book sold nothing), the exit at "open" on this New York day, each take kept in the lot's
        `info["taken"]`. An exit intent still planned for a lot closed here ends at the next window (`_work_exit`: "the
        lot is sold"), and the lot is exported like any closed one. Returns the shares closed (less than `qty` when the
        book holds less). Never an order."""
        symbol = str(symbol).upper()
        left = D(qty, ZERO)
        price = D(px, ZERO)
        now = self.clock()
        today = S.ny_day(now).isoformat()
        taken = ZERO
        closed: list[Lot] = []
        with self.state.transaction():
            for lot in self._lots(symbol=symbol):
                if left <= SHARE_TOLERANCE:
                    break
                dq = min(lot.qty, left)
                if dq <= 0:
                    continue
                at_px = price if price > 0 else (lot.mark if lot.mark is not None and lot.mark > 0 else lot.entry_px)
                proceeds = dq * at_px
                lot.qty -= dq
                lot.cash += proceeds
                lot.info["exit_qty"] = text(D(lot.info.get("exit_qty"), ZERO) + dq)
                lot.info["exit_notional"] = text(D(lot.info.get("exit_notional"), ZERO) + proceeds)
                lot.info.setdefault("taken", []).append({"qty": text(dq), "px": text(at_px), "at": now,
                                                         "priced": "cover" if price > 0 else "mark", "why": why[:200]})
                if lot.qty <= SHARE_TOLERANCE:
                    lot.qty = ZERO
                    exit_qty = D(lot.info["exit_qty"])
                    lot.status, lot.closed_at, lot.reason = LOT_CLOSED, now, "forced"
                    lot.exit_px = ((D(lot.info["exit_notional"]) / exit_qty).quantize(PRICE_PLACES) if exit_qty > 0
                                   else at_px)
                    lot.exit_at, lot.exit_day = "open", today
                    closed.append(lot)
                else:
                    lot.status = LOT_CLOSING
                self._save_lot(lot)
                taken += dq
                left -= dq
        for lot in closed:
            self.record("equity.close", {"lid": lot.lid, "family": lot.family, "instance": lot.instance,
                                         "symbol": lot.symbol, "cash": text(lot.cash), "reason": lot.reason},
                        agent=lot.family)
        if taken > 0:
            self.record("equity.alert", {"what": f"{text(taken)} {symbol} of the book's lots left the account in an "
                                                 f"option assignment or exercise: closed as forced ({why[:200]})",
                                         "lots": [lot.lid for lot in closed]})
        return taken

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
                "freeze": self.state.get("eq_freeze"), "seats": self.seats(), "events": self._event_health()}

    def _event_health(self) -> dict[str, Any] | None:
        """THE EVENT KIND'S LINE (release R2): its switch and the bands' target shares, each seating version's band as
        the book last read it from the lane (`eq_event_programs`),
        the auction paper proof's stages, the eligible list at the gateway, the last decisions (counts only). None when
        the event adapter cannot be imported."""
        adapter = self._event_adapter()
        if adapter is None:
            return None
        try:
            s = adapter.settings()
            proof = self._auction_proof()
            stages = proof.status().get("stages") if proof is not None else None
            return {"enabled": bool(s.enabled),
                    "shares": {band: text(s.share(band)) for band in EVENT_LIVE_BANDS},
                    "programs": [{k: r[k] for k in ("program", "version", "band", "since", "why")}
                                 for r in self.state.rows("SELECT * FROM eq_event_programs ORDER BY program")],
                    "proof": {name: (stage or {}).get("status") for name, stage in (stages or {}).items()} or None,
                    "list": self.state.get("eq_event_list"),
                    "decisions": [{"day": r["day"], "at": r["at"], "status": r["status"],
                                   **(loads(r["summary"], {}) or {})} for r in
                                  self.state.rows("SELECT * FROM eq_event_decisions ORDER BY day DESC, at LIMIT 4")]}
        except Exception as exc:  # noqa: BLE001 - a health line, never the health page's end
            return {"error": f"{type(exc).__name__}: {str(exc)[:160]}"}

    def seats(self) -> dict[str, Any] | None:
        """THE SEAT PLAN as the last band sync wrote it (`SEAT_KEY`; THE SEAT RULE, the module docstring): {rule, seats,
        day, holders [{family, version, band, seeded, since, seated_sessions, quiet_sessions, left_out, flat, idle}],
        waiting [{family, version, rank, seeded, flagged, why}] (None under "first-come": the swarm's roster orders
        them, by pass time), idle (the programs that yielded an idle seat and wait flagged), left_out (the sessions
        in which the House refused every open, left out of the idle clock), last (the last change of hands and
        why)}. Rank positions only: K is never in it. None before the first sync."""
        plan = self.state.get(SEAT_KEY)
        return dict(plan) if isinstance(plan, Mapping) else None

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

    def _owner(self, now: float, out: dict) -> None:
        """THE OWNER'S COMMANDS (`OWNER_FLATTEN`, `OWNER_CLEAR_FREEZE`), read first every minute, whatever the phase:
        `flatten` run in the House's own thread (a second process on live.sqlite would race the book's row ids), and
        the corporate-action freeze `eq_freeze` lifted (the reconciliation's own freeze is never the owner's to lift:
        two clean readings lift it). Each is done once and its key deleted; one that fails keeps its key and is tried
        again the next minute (a flatten queues each lot once), and never stops the other."""
        for key, act in ((OWNER_FLATTEN, self._owner_flatten), (OWNER_CLEAR_FREEZE, self._owner_clear_freeze)):
            ask = self.state.get(key)
            if not ask:
                continue
            ask = ask if isinstance(ask, Mapping) else {}
            try:
                act(f"{ask.get('by') or 'the owner'}: {ask.get('why') or 'no reason given'}", out)
            except Exception as exc:  # noqa: BLE001 - again next minute
                self._error(key, exc, out)

    def _owner_flatten(self, why: str, out: dict) -> None:
        n = self.flatten(why)
        self.state.execute("DELETE FROM kv WHERE key=?", (OWNER_FLATTEN,))
        out["flatten"] = n
        self.alert("warning", f"equity: flatten, {n} lots queued to exit through the normal path ({why[:200]})")

    def _owner_clear_freeze(self, why: str, out: dict) -> None:
        was = self.state.get("eq_freeze")
        with self.state.transaction():
            self.state.execute("DELETE FROM kv WHERE key IN ('eq_freeze', ?)", (OWNER_CLEAR_FREEZE,))
        out["freeze_cleared"] = bool(was)
        if not was:
            return
        old = str(was.get("why") if isinstance(was, Mapping) else was)[:300]
        self.record("equity.freeze", {"frozen": bool(self.frozen), "cleared": "eq_freeze", "by": why[:300],
                                      "why": f"cleared (was: {old})",
                                      "activity": was.get("activity") if isinstance(was, Mapping) else None})
        self.alert("warning", f"equity: the corporate-action freeze is cleared ({why[:200]}); it was: {old[:200]}")

    # ------------------------------------------------------------------ the minute
    def tick(self, now: float, *, account_row: Mapping[str, Any] | None, positions: Sequence[Mapping[str, Any]] | None,
             open_orders: Sequence[Mapping[str, Any]] | None, real_block: Callable[..., str | None],
             killed: Callable[[], bool]) -> dict[str, Any]:
        """THE ONE ENTRY a minute (league/live/step.py): whatever `schedule.phase(now)` says is due (bars, decide,
        pre-open, the open window, the close window, the morning audit, reconciliation, activities, exports). The
        minute's own reads are passed when the options path made them (None: not read this minute; the book reads
        what it needs itself, within the Account's rate). `real_block(opening=True)`: why no real open may go now
        (None: it may); `killed()`: the gateway's kill switch (exits wait on it, the min hold and, until the entry
        cut-off, the stock proof's SELL stage: the gateway's kill blocks sells too). Never raises: an error is recorded and the next minute tries again. Returns a summary for the minute's
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
                ("owner", lambda: self._owner(now, out)),
                ("orders", lambda: self._sync_orders(now, out)),
                ("activities", lambda: self._activities(now, m, out)),
                ("reconcile", lambda: self._reconcile_step(now, m, out)),
                ("audit", lambda: self._audit(now, m, out)),
                ("decide", lambda: self._decide_step(now, out)),
                # RELEASE R2: the event kind's auctions (09:15-09:27 ET and the close - 14 to - 11 minutes), and its
                # auction paper proof.
                ("events", lambda: self._event_step(now, m, out, real_block, killed)),
                # The stock proof before the windows (A10.1): in its SELL stage's window the practice sale goes first.
                ("proof", lambda: self._proof_step(now, m, out)),
                ("windows", lambda: self._windows(now, m, out, real_block, killed)),
                ("exports", lambda: self._export(out)),
                ("fees", lambda: self._fees(now, out)),
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
        self._seats = {}
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
        after all (for `LOST_TAKE_BACK_DAYS`; the seat rule's `_flat` reads the same window, and a day more), and look
        up the unknown ones by client id."""
        working = self._orders(WORKING)
        lost = self._orders(("lost",))
        lost = [o for o in lost if o.day >= (S.ny_day(now) - dt.timedelta(days=LOST_TAKE_BACK_DAYS)).isoformat()]
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
        self._end_stale(now)

    def _end_stale(self, now: float) -> None:
        """A DAY ORDER NEVER OUTLIVES ITS SESSION: one the venue still shows working on a later New York day than its
        own (`day`) reached the venue after its session's close and rests for the next one (`_send` posts nothing at or
        after a cut-off by the wall clock, so this takes a slow gateway and a House that was down at the cut-off's own
        cancel). It is cancelled wherever the minute finds it, the quiet hours included, before the next open can fill
        it as a lot of a session it never traded in; its intent then ends as any other (an entry missed, an exit sent
        again in today's window)."""
        today = S.ny_day(now).isoformat()
        for order in self._orders(("working",)):
            # (RELEASE R2: an auction order, `opg` or `cls`, is queued for its own session's auction; one of today, sent
            # before the open, is never ended here. Its auction ends it at the venue; one still working a day later is
            # cancelled like any other.)
            if order.day >= today or not order.venue_id:
                continue
            if "cancel_sent" not in order.answer:
                self.alert("warning", f"equity: order {order.client_id} of {order.day} is still working at the venue: "
                                      "cancelled (a day order ends with its session)")
            self._cancel(order, "left working past its own session", now)

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
            # A simple order's status and quantity come in one row: "filled" ends it whatever its quantity says (a short
            # fill is noted, never left working: a working row would hold its symbol busy for good).
            order.status = final
            order.answer = {**order.answer, "final": status,
                            "reject_reason": str(row.get("reject_reason") or "")[:200] if status == "rejected" else None}
            if final == "filled" and order.filled_qty < order.qty:
                order.answer["short_fill"] = text(order.qty - order.filled_qty)
        elif status:
            order.status = "working"
        self._save_order(order)

    def _book_fill(self, order: Order, dq: Decimal, px: Decimal) -> None:
        now = self.clock()
        intent = self._intent(order.iid)
        if order.side == "buy":
            lid = order.lid if order.lid is not None else (intent.lid if intent is not None else None)
            if lid is None:
                lid = self._intent_lot(order)
            lot = self._lot(lid)
            if lot is None:
                inst = self._instance(order.instance)
                lot = Lot(self._next("eq_lots", "lid"), order.instance, order.family,
                          inst.version if inst else _version_of(order.instance), inst.lane if inst else "",
                          order.symbol, order.klass, qty=dq, opened_qty=dq, entry_px=px, entry_notional=dq * px,
                          entry_at=order.at, opened_at=now, opened_day=order.day, status=LOT_OPEN, cash=-(dq * px),
                          probe=order.probe, tag=(intent.tag if intent else "")[:120], iid=order.iid)
                side = self._event_row(order.iid) if order.auction else None
                if side is not None:
                    # RELEASE R2: an event lot keeps its program's plan from its buy (league/events/book.py's side row):
                    # the event, the issuer, its open-risk weight and its scheduled exit (rung 0 of the ladder).
                    lot.lane = EVENT_LANE
                    lot.info["evl"] = {"program": side["program"], "version": int(side["version"]), "event": side["event"],
                                       "cik": side["cik"], "weight": side["weight"], "sigma": side["sigma"],
                                       "prev_close": side["prev_close"], "limit": side["limit_px"],
                                       "band": side.get("band")}
                    lot.info["evl_exit"] = {"day": side["exit_day"], "at": side["exit_at"], "rung": 0}
                if intent is not None:
                    intent.lid = lot.lid
                    self._save_intent(intent)
            else:
                lot.qty += dq
                lot.opened_qty += dq
                lot.entry_notional += dq * px
                lot.entry_px = (lot.entry_notional / lot.opened_qty).quantize(PRICE_PLACES)
                lot.cash -= dq * px
                if intent is not None and intent.lid != lot.lid:
                    intent.lid = lot.lid
                    self._save_intent(intent)
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

    def _intent_lot(self, order: Order) -> int | None:
        """The open lot an earlier order of this buy's intent already opened (`eq_lots.iid`), when neither the order nor
        the intent's row names it: ONE INTENT, ONE LOT, as the Gym has one lot a buy, whatever a row lost."""
        if order.iid is None:
            return None
        rows = self.state.rows("SELECT lid FROM eq_lots WHERE iid=? AND instance=? AND symbol=? AND status IN "
                               "('open', 'closing') ORDER BY lid LIMIT 1", (int(order.iid), order.instance, order.symbol))
        return int(rows[0]["lid"]) if rows else None

    # ------------------------------------------------------------------ sending
    def _send(self, intent: Intent, *, side: str, symbol: str, klass: str, qty: Decimal, limit: Decimal, collar: int,
              day: str, lid: int | None, replaces: int | None, probe: bool, why: str, at: str | None = None,
              tick: float | None = None, until: float | None = None, tif: str = "day",
              otype: str = "limit") -> Order | None:
        """Write the order `pending` (the intent `sent`, a sold lot `closing`) BEFORE the POST; then POST it once. `at`
        is the window it goes in (the fill point a lot's `entry_at` / `exit_at` and its twin read), the intent's by
        default. `tick` is the minute's `now` the send belongs to, kept as the order's `answer.tick` (a re-price is due
        on the House's minute clock, `_reprice_due`; `placed_at` stays the wall clock at the POST). `until` is the
        window's cut-off, judged here on the WALL clock: the minute's `now` passed it at the minute's start, but the
        equity minute runs after the whole options minute, and a day order POSTed at or after the close would rest for
        the next session. At or after `until` nothing is written or sent (None); the next minute ends the intent (an
        entry missed, an exit carried)."""
        now = self.clock()
        if until is not None and now >= until:
            late = "not sent: the window's cut-off passed on the wall clock before the order could go"
            if intent.why != late:
                intent.why = late
                self._save_intent(intent)
            return None
        exit_ = side == "sell"
        stamp = {} if tick is None else {"tick": float(tick)}
        with self.state.transaction():
            eid = self._next("eq_orders", "eid")
            order = Order(eid, client_id(eid, intent.family, nonce=getattr(self.state, "nonce", "")), intent.instance,
                          intent.family, side, symbol, klass, at or intent.at, qty, limit, int(collar), "pending", now, day,
                          lid=lid, iid=intent.iid, replaces=replaces, probe=probe, why=why[:300], answer=dict(stamp),
                          tif=tif, otype=otype)
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
                if gateway and payload.get("cap") in (EVENT_RETRY_CAPS if order.auction else RETRY_CAPS):
                    order.answer["retry"] = True     # nothing was sent, and nothing judged: again next minute
        order.answer = {**stamp, **order.answer}
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
    def _symbol_busy(self, symbol: str, *, auction_sale: tuple[str, str] | None = None) -> str | None:
        """Why no new order may go on `symbol` now (one working order a symbol across both books), or None.

        `auction_sale` (day, tif "opg" | "cls"): the order is an event lot's SALE at that auction (release 1019b's review).
        This book's own working sales of the symbol at that same auction do not stop it: two programs may hold one name
        (one position per issuer is a per-program rule), and each lot exits at its own scheduled auction (PREREG-EVL-1
        sections 5 and 6), so both sales go in the one cross. The account sells no more than it holds (the gateway
        reserves the closes of the same shares together, `gate.reserveStockClose`). Any other working order on the symbol
        (a buy, a day order, another auction's, the options book's, one that is not this book's) stops it as always."""
        if auction_sale is None:
            mine = symbol in self.busy()
        else:
            sale_day, sale_tif = auction_sale
            mine = bool(self.state.rows(
                "SELECT 1 AS x FROM eq_orders WHERE symbol=? AND status IN ('pending', 'working', 'unknown') AND NOT "
                "(side='sell' AND tif=? AND day=?) LIMIT 1", (symbol, sale_tif, sale_day)))
        if mine:
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

    def _count_refusal(self, day: str, *, exit_: bool, event_line: int | None = None) -> str | None:
        """THE ONE DAY ORDER COUNT (A8.3): None when one more order (and its cancel) fits. AN ENTRY must fit ITS LANE'S
        own count with room left for the exits of that lane's lots held (`_exit_reserve`: an old lane's lot's exit and
        one cancel of it; an event lot's one auction sale, none once sent): an old lane's entry the old lanes' orders
        against `order_path.max_orders_day` (60); AN EVENT ENTRY (`event_line`, release 1019c) the event kind's orders
        (`event_orders_today`) against its own line, `equity_money.event.max_orders_day` (150; league/events/book.py
        `Settings.max_orders_day`), with room for ITS OWN EXIT too (an open-entry buy's sale is the same day's close),
        so the line bounds the kind's whole day: its sends and cancels, the exits it keeps, and the entry's own exit.
        AN EXIT IS NEVER STOPPED BY A LANE'S COUNT (A28: an exit must never be blocked): it meets the House-wide count
        alone (every lane's orders together, the options book's included), which keeps the options book's exits their
        room (`exit_reserve`) under the gateway's day lines. EVERY ENTRY meets the House-wide count too, with room left
        for the options book's exits AND EVERY EQUITY EXIT (`_exit_reserve`, both lanes: the lots held and the event buys
        still working that are sold the same day) and, for an event entry, its own exit (release 1019c's money review:
        a lane's line bounds that lane's day only, so without its exits' room at the House-wide line about 2 x 150
        event orders could reach the line together and the close's sales be refused there). (Under the equity count an
        exit was stopped once a held basket's re-priced sales had used it up: each sale that climbs the collar ladder
        costs a send and a cancel a rung, and every lot climbs at once, so at 8 to 12 basket lots and a fast open the ETF
        lots' sales stopped below the rung that fills and were carried to the next session; the review of step two,
        review-live, measured it.) A lane's count still bounds its NEW risk: its entries stop once its day's sends and
        cancels, exits' included, leave too little room. (Under release 1019b's one count of 60 for both, the event
        kind's entries stopped at about 30 open-entry lots sold the same day.)"""
        mine = orders_today(self.state.rows, day)
        own = 0
        if not exit_:
            events = event_orders_today(self.state.rows, day)
            if event_line is not None:
                own = 1     # the event entry's own exit (one auction sale; an open-entry buy's is the same day's close)
                cap, reserve = int(event_line), self._exit_reserve(day, event=True)
                if events + 1 + own + reserve > cap:
                    return (f"the event kind's day order count: {events} of {cap} sent, {reserve + own} kept for "
                            "exiting its lots and buys held and this one")
            else:
                et = self._et()
                cap = int(getattr(et, "max_orders_day", 60) if et is not None else 60)
                reserve, old = self._exit_reserve(day, event=False), mine - events
                if old + 1 + reserve > cap:
                    return f"the equity day's order count: {old} of {cap} sent, {reserve} kept for exiting the lots held"
        if self.options_book is not None:
            try:
                house = int(self.options_book.count_today(day)) + mine
                room = int(self.table.max_orders_day) - house - int(self.options_book.exit_reserve())
                kept = 0 if exit_ else self._exit_reserve(day) + own
            except Exception:  # noqa: BLE001
                return "the House's day order count could not be read"
            if room - kept < 1:
                return (f"the House's day order count: {house} sent of {self.table.max_orders_day}, the rest kept for "
                        "the options book's exits" + (f"; {kept} kept for the equity book's exits, this entry's own "
                                                      "included" if own else ""))
        return None

    def _exit_reserve(self, day: str, *, event: bool | None = None) -> int:
        """The part of the day's order count an ENTRY leaves for the exits of the lots held (`_count_refusal`): two for a
        lot of the old lanes (its sale and one cancel of it: a day sale climbs the collar ladder); ONE for an event lot
        (release 1019b's review: its exit is one auction order, a market-on-open or market-on-close sale, never
        re-priced or cancelled); NONE for an event lot whose sale this book has already sent on `day` (that order is in
        the count already: counted twice, a day's open-entry lots sold at the close left the close's own entries no
        room); and ONE for each EVENT BUY STILL WORKING whose planned exit is on `day` (release 1019c's money review: an
        auction buy is no lot until its cross, so an open-entry program's buys of the open window, sold at that day's
        close, had no exit kept; a close entry's exit is on a later day, where it is kept as a lot held). `event` True:
        the event kind's part alone (its own line, release 1019c); False: the old lanes' part alone (theirs); None:
        both (the House-wide count's equity exits)."""
        sent = {int(r["lid"]) for r in self.state.rows(
            "SELECT DISTINCT lid FROM eq_orders WHERE side='sell' AND day=? AND lid IS NOT NULL AND status!='refused'",
            (day,))}
        reserve = 0
        for lot in self._lots():
            if lot.lane != EVENT_LANE:
                reserve += 2 if event is not True else 0
            elif lot.lid not in sent:
                reserve += 1 if event is not False else 0
        if event is not False and _has_table(self.state.rows, "eq_event_intents"):
            reserve += int(self.state.rows(
                "SELECT COUNT(*) AS n FROM eq_orders o JOIN eq_event_intents e ON e.iid=o.iid WHERE o.side='buy' AND "
                f"e.side='buy' AND e.exit_day=? AND o.status IN ({', '.join('?' * len(WORKING))})",
                (day, *WORKING))[0]["n"])
        return reserve

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
        event = inst is not None and inst.kind == EVENT_KIND
        if event:
            # RELEASE R2: THE EVENT KIND'S OWN SWITCH (`equity_money.event.enabled`; `equity_money.enabled` stays the
            # old lanes', False) and THE AUCTION PAPER PROOF (league/events/proof.py: a practice limit-on-open buy and a
            # market-on-close sale) in place of the SPY day-order proof, whose route an event order never takes.
            why = self._event_open_block()
            if why:
                return why
        elif not et.enabled:
            return "equity_money.enabled is false: exits only"
        if self.stock_proof is None:
            return "no stock paper proof: no paper account"
        if not event:
            try:
                if not self.stock_proof.buy_passed():
                    return "the stock paper proof's BUY stage (paper_proof_stock_buy) has not passed"
                failed = self.stock_proof.sell_failed()
                if failed:
                    return f"{failed}: new real equity buys stop until it passes"
            except Exception as exc:  # noqa: BLE001
                return f"the stock paper proof could not be read ({type(exc).__name__})"
        frozen = self.frozen
        if frozen:
            return f"equity reconciliation: {frozen}"
        if inst is None or not inst.live:
            return "the program is not at Probe or Sized"
        if inst.kind == PANEL_KIND:
            return self._seat_block(inst)
        if event:
            return self._event_seat_block(inst)
        return None

    def _seat_block(self, inst: Instance) -> str | None:
        """RELEASE E4, THE SEAT AT THE SEND: why a program of another kind than the book's own (a panel program) may
        open no position this pass, or None. The swarm's reader gives its family a row in a running band on this
        version only while its LANE may trade (league/swarm/bands.py `read`: a panel family has none unless the panel
        lane's effective mode is "live": its switch, the universe deploy, the nightly I6, its shadow twin's marker).
        The band sync asks once a day, at the decide, and an entry planned then is sent the next morning: what stopped
        the lane overnight must stop that entry too. Read once a pass (`_seats`); a store that cannot be read opens
        nothing. Exits never ask it. An entry it holds is tried again each minute of its window and is missed at the
        cut-off, with this reason."""
        if inst.id not in self._seats:
            why: str | None = None
            try:
                rows = [dict(r) for r in self.families.read(inst.family)]
                unread = str(getattr(self.families, "last_error", "") or "")
                row = next((r for r in rows if str(r.get("family")) == inst.family), None)
                if unread:
                    why = f"its family's seat could not be read ({unread[:120]})"
                elif row is None or row.get("band") not in LIVE_BANDS or int(row.get("version") or 0) != inst.version:
                    why = ("its family holds no seat now (the swarm gives this version no row in a running band: its "
                           "lane is not live): exits only")
            except Exception as exc:  # noqa: BLE001 - fail closed
                why = f"its family's seat could not be read ({type(exc).__name__})"
            self._seats[inst.id] = why
        return self._seats[inst.id]

    def _open_note(self, window: str, m: S.Moments, real_block: Callable[..., str | None],
                   killed: Callable[[], bool] | None, out: dict) -> None:
        """THE OPEN NOTE (`OPEN_NOTE_KEY`; the captain's A30 (2)), written by `_windows` at every minute in which the
        entries of an entry window are worked (`window`: "open" from the first minute the open's entries may go,
        which is after the open's exits or their two minutes, to 09:45; "close" likewise to 15:59:30), entries or
        none, while the seat rule is in force: whether the House would let a real equity open of ANY program go this
        minute (`_open_block` asked with `OPEN_PROBE`: the House's `real_block`, the kill switch,
        `equity_money.enabled`, the stock proof's BUY stage, a failed SELL stage, the freezes). It is the answer
        this minute's entries are given, asked once more for nobody in particular. A window is CLEAR from the first
        minute it would, and stays clear; until then it carries the refusal's words. The kv is written only when a
        window's answer changes (a handful of writes a session). Never the windows' end: its own trouble is an
        `equity.error` and the entries go on."""
        try:
            if B.seat_settings().first_come:
                return
            why = self._open_block(real_block, OPEN_PROBE, killed)
            held = self.state.get(OPEN_NOTE_KEY, {})
            note = {str(k): dict(v) for k, v in held.items() if isinstance(v, Mapping)} if isinstance(held, Mapping) else {}
            day = m.day.isoformat()
            was = note.get(day, {}).get(window)
            was = dict(was) if isinstance(was, Mapping) else None
            if was is not None and was.get("clear"):
                return
            now_is = {"clear": True} if why is None else {"clear": False, "why": str(why)[:200]}
            if was == now_is:
                return
            note.setdefault(day, {})[window] = now_is
            floor = (m.day - dt.timedelta(days=OPEN_NOTE_KEEP_DAYS)).isoformat()
            self.state.put(OPEN_NOTE_KEY, {d: w for d, w in sorted(note.items())
                                           if d == day or (d > floor and _refused(w))})
        except Exception as exc:  # noqa: BLE001 - a note, never the windows' end
            self._error("open_note", exc, out)

    def _refused_days(self) -> dict[str, str]:
        """THE SESSIONS IN WHICH THE HOUSE REFUSED EVERY OPEN (`OPEN_NOTE_KEY`): {day: why}, a session with an entry
        window the House looked in and never once would have opened in. A session it did not look at at all (the
        House did not run in its windows, or ran under "first-come") is not one: nothing is known of it, and it
        counts as any other. The rule is `refused_days`' (the `dlane` report reads the same kv through it)."""
        return refused_days(self.state.get(OPEN_NOTE_KEY, {}))

    def _quote(self, symbol: str) -> dict[str, Any]:
        """The symbol's touch this pass, read once (`market.stocks`: IEX's snapshot since release R0, Oct 19, 2026,
        league/data_plan.py): the latest quote's bid and ask and its time, the latest trade's price and time. A SIDE
        AT ZERO OR BELOW IS NO SIDE (None): IEX quotes a side it has no order on as 0, and a 0 must never become a limit
        nor read as a quote moved through one (`_reprice_due`). An entry needs both sides, uncrossed, from this session
        and inside `MAX_ENTRY_SPREAD`; an exit needs the bid from this session, else this session's trade."""
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
            self._quotes[symbol] = {"bid": _side(quote.get("bp")), "ask": _side(quote.get("ap")),
                                    "t": parse_time(quote.get("t")), "trade": _side(trade.get("p")),
                                    "trade_t": parse_time(trade.get("t"))}
        return self._quotes[symbol]

    # ------------------------------------------------------------------ the windows
    def _not_event(self) -> str:
        """The SQL that leaves an event intent out of the old lanes' windows (release R2: `_event_step` works an event
        intent, at its own auction); "" in a state without the event adapter's table."""
        return " AND iid NOT IN (SELECT iid FROM eq_event_intents)" if _has_table(self.state.rows, "eq_event_intents") else ""

    def _windows(self, now: float, m: S.Moments | None, out: dict, real_block: Callable[..., str | None],
                 killed: Callable[[], bool]) -> None:
        if m is None or now < m.open_send:
            return
        today = m.day.isoformat()
        rows = self.state.rows("SELECT * FROM eq_intents WHERE status IN ('planned', 'sent') AND exec_day<=?"
                               + self._not_event() + " ORDER BY iid", (today,))
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
            if intent.at == "close" and intent.exec_day == today and now < m.close_send:
                continue    # today's close exit waits for the close; one left from a past session goes now
            try:
                self._work_exit(intent, now, m, killed, out)
            except Exception as exc:  # noqa: BLE001
                self._error(f"exit {intent.iid}", exc, out)
        off = self._offsets()
        open_exits = self.state.rows("SELECT iid FROM eq_intents WHERE status IN ('planned', 'sent') AND exec_day<=? "
                                     "AND at='open' AND kind IN ('sell', 'house_exit') AND lid IN "
                                     "(SELECT lid FROM eq_lots WHERE opened_day<?)" + self._not_event(), (today, today))
        entries = [i for i in intents if i.kind == "buy" and i.exec_day == today]
        if entries:
            out["entries"] = len(entries)
        if not open_exits or now >= m.open_send + off["exit_wait_s"]:
            if now < m.entry_until:
                self._open_note("open", m, real_block, killed, out)
            for intent in entries:
                if intent.at != "open":
                    continue
                try:
                    self._work_entry(intent, now, m, deadline=m.entry_until, reprice=off["open_reprice_s"],
                                     real_block=real_block, killed=killed, out=out)
                except Exception as exc:  # noqa: BLE001
                    self._error(f"entry {intent.iid}", exc, out)
        # THE CLOSE WINDOW keeps the session's order too (A2: close exits, then close entries): its entries wait for the
        # window's exits (today's close exits, and an open exit still going late) to fill, or `CLOSE_EXIT_WAIT_S`.
        if now >= m.close_send and (now >= m.close_send + CLOSE_EXIT_WAIT_S or not self._exits_due(today, now, m)):
            if now < m.close_until:
                self._open_note("close", m, real_block, killed, out)
            for intent in entries:
                if intent.at != "close":
                    continue
                try:
                    self._work_entry(intent, now, m, deadline=m.close_until, reprice=off["close_reprice_s"],
                                     real_block=real_block, killed=killed, out=out)
                except Exception as exc:  # noqa: BLE001
                    self._error(f"entry {intent.iid}", exc, out)

    def _exits_due(self, today: str, now: float, m: S.Moments) -> list[dict]:
        """The exits that may still fill in the window open now ([{iid, instance}]): planned or sent, of a lot that may
        sell today (the min hold), today's close exits only from `close_send` (before it they wait for the close). An
        entry is sized on the cash AFTER them (A2, as the Gym's session: exits, then entries): each one that fills frees
        its program's sleeve, the House-wide cash, the invested cap and the loss budget's room."""
        rows = self.state.rows("SELECT iid, instance, at, exec_day FROM eq_intents WHERE status IN ('planned', 'sent') "
                               "AND exec_day<=? AND kind IN ('sell', 'house_exit') AND lid IN "
                               "(SELECT lid FROM eq_lots WHERE opened_day<? AND status IN ('open', 'closing'))"
                               + self._not_event(), (today, today))
        return [r for r in rows if not (r["at"] == "close" and r["exec_day"] == today and now < m.close_send)]

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
            elif self.clock() < m.close_until and self._reprice_due(current, now, reprice, m):
                # (Never cancelled for a re-price its replacement could not follow: `_send`'s wall-clock cut-off.)
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
        if lot.opened_day >= today and lot.lane != EVENT_LANE:
            # (Release R2: an EVENT lot sells in its own session when its rule says so: PREREG-EVL-1's open entries
            # exit at that session's close, and the owner's flatten or the ladder's day sale may come the same day.)
            if intent.why != "min hold":
                intent.why = "min hold"
                self._save_intent(intent)
            return
        why = self._sell_proof()
        if why and now < m.entry_until:
            # A10.1: the practice sale goes first in its window. A28: THAT WAIT ENDS AT THE ENTRY CUT-OFF, the minute
            # the book stops trying this session's open entries (`_work_entry`: `now >= deadline`, this `entry_until`).
            if intent.why != why:
                intent.why = why
                self._save_intent(intent)
            return
        if why:
            self._sell_unproven(today)
        try:
            stopped = bool(killed())
        except Exception:  # noqa: BLE001 - unreadable counts as engaged
            stopped = True
        if stopped:
            intent.why = "the gateway's kill switch is engaged (it blocks sells too)"
            self._save_intent(intent)
            return
        refused = [o for o in orders if o.day == today and o.status in ("rejected", "refused") and not o.again]
        if len(refused) >= MAX_EXIT_REFUSALS:
            self.alert("error", f"equity: the exit of lot {lot.lid} ({lot.symbol}) was refused {len(refused)} times today; "
                                "carried to the next session")
            self._carry(intent, lot, today, f"refused {len(refused)} times: {refused[-1].answer.get('error')}")
            return
        unread = [o for o in orders if o.day == today and o.again and o.answer.get("retry")]
        if len(unread) >= MAX_EXIT_REFUSALS and lot.info.get("exit_unread_told") != today:
            # `RETRY_CAPS`: nothing was sent and nothing judged, so the exit is never carried for them; said once a day.
            lot.info["exit_unread_told"] = today
            self._save_lot(lot)
            self.alert("error", f"equity: the gateway could not check the exit of lot {lot.lid} ({lot.symbol}) "
                                f"{len(unread)} times today ({unread[-1].answer.get('cap')}: nothing was sent); it is "
                                "sent again each minute until the session's windows end")
        why = self._symbol_busy(lot.symbol) or self._count_refusal(today, exit_=True)
        if why is None and any(o.status == "lost" for o in orders):
            why = self._lost_sale_check(lot)
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
        # The collar widens with each order that reached the venue; one refused before it (the House's rate, a gateway
        # cap or an unread reading) priced nothing.
        attempt = sum(1 for o in orders if o.day == today and o.status != "refused")
        late = intent.at == "open" and now >= m.exit_until
        collar = max_bp if late else collar_for(attempt, entry_bp, max_bp)
        limit = limit_for("sell", bid, collar)
        reason = "program" if intent.kind == "sell" else (intent.tag or "house")
        self._send(intent, side="sell", symbol=lot.symbol, klass=lot.klass, qty=lot.qty, limit=limit, collar=collar,
                   day=today, lid=lot.lid, replaces=current.eid if current is not None else None, probe=lot.probe,
                   why=f"exit ({reason}){' at the bid, late' if late else ''}", at="close" if in_close else "open",
                   tick=now, until=m.close_until)

    def _sell_proof(self) -> str | None:
        """Why a real equity SALE waits (A10.1: the stock paper proof's SELL stage gates every one; the practice sale
        goes first in its window), or None. A House with no paper account at all (no proof object) opens nothing, and
        its exits go: no stage can ever pass there, and a lot is never held on a proof that cannot run. THE WAIT HAS AN
        END (A28): `_work_exit` holds an exit on this only before the session's entry cut-off (`_sell_unproven`)."""
        if self.stock_proof is None:
            return None
        try:
            if self.stock_proof.sell_passed():
                return None
        except Exception as exc:  # noqa: BLE001 - unreadable: the sale waits, to the entry cut-off at the latest
            return f"the stock paper proof could not be read ({type(exc).__name__}): real exits wait"
        return "real exits wait for the stock paper proof's SELL stage (paper_proof_stock_sell, A10)"

    def _sell_stage_says(self) -> str:
        """The SELL stage's OWN reason for not having passed, in the proof's words: its failure when it has failed
        (`sell_failed`: "... SELL stage failed on <day>: the round trip ended without activity_witness"), else where
        its attempt stands (`status`: the attempt row's status and why, e.g. "sold: sold; waiting for
        activity_witness", "sell_sent: the order was accepted; awaiting its fill"); a proof that cannot be read says
        that."""
        try:
            failed = self.stock_proof.sell_failed()
            row = None if failed else self.stock_proof.status()
        except Exception as exc:  # noqa: BLE001
            return f"the stock paper proof could not be read ({type(exc).__name__})"
        if failed:
            return str(failed)
        row = row if isinstance(row, Mapping) else {}
        stands = ": ".join(str(row[k]) for k in ("status", "why") if row.get(k))
        return f"not passed yet; its attempt stands at {stands}" if stands else "not passed yet"

    def _sell_unproven(self, today: str) -> None:
        """AN EXIT'S WAIT FOR THE PRACTICE PROOF HAS AN END (the captain's A28, amending A10.1; registered before the
        first real share order). The SELL stage's practice sale goes first in its window: sent in the open window's
        first minute, normally witnessed in its second, and real exits wait for it. Until this rule that wait had no
        end: a stage that could not pass (a practice sale that rests, FILL activities the practice account does not
        list, a practice position off its baseline) held every real lot for as long as it could not, the maximum-hold
        exit and the owner's flatten among them, while it also stopped every new buy; the only way out was by hand at
        the broker. THE WAIT ENDS AT THE SESSION'S ENTRY CUT-OFF (`schedule.Moments.entry_until`, the open + 900 s: the
        very minute the book stops trying open entries). From it on EVERY exit goes through the normal path whatever
        the stage says: a program's own sale, the House's maximum hold, a demoted or retired program's lots, a carried
        exit, the owner's flatten, and a close-window sale (15:55 is past the cut-off by construction, so it never
        waits on the stage at all). The normal path is unchanged: the collar, one working order a symbol, the day's
        count, the gateway's kill switch, the minimum hold. UNCHANGED TOO: stage BUY gates every real buy with no end,
        and a FAILED SELL stage stops new real buys until it passes (`_open_block`); the proof's own alarm goes on
        (league/live/paper.py `_fail_sell`, inside the options fingerprint: its words "real equity lots stay held"
        are from before this rule). THE COST, as the captain stated it: a real sale can go through a path the practice
        account did not prove that day. So the owner is told: ONE error alert and one `equity.alert` record a session
        (kv `eq_sell_unproven` {day, why, at}), whatever the number of exits, naming the stage's own reason
        (`_sell_stage_says`). THE TELLING NEVER HOLDS AN EXIT: when the note cannot be read or kept this minute nothing
        is said and nothing is raised; the exit goes, and the next minute that can keep the note says it."""
        try:
            if (self.state.get("eq_sell_unproven") or {}).get("day") == today:
                return
            said = self._sell_stage_says()[:300]
            self.state.put("eq_sell_unproven", {"day": today, "why": said, "at": self.clock()})
        except Exception:  # noqa: BLE001 - an exit is never held on its own notice
            return
        what = ("the sale path is unproven today: the stock paper proof's SELL stage had not passed by the entry "
                f"cut-off ({said}); real equity exits no longer wait for it this session and go through the normal "
                "path")
        self.record("equity.alert", {"what": what, "day": today})
        self.alert("error", f"equity: {what} (A28). New real equity buys stay stopped while the stage is failed. Owner "
                            "step: look at the practice account (alpaca-paper), its SPY position and orders")

    def _lost_sale_check(self, lot: Lot) -> str | None:
        """After a sale of this lot was given up as lost, it goes again only while the account still holds what the
        book expects of the symbol (had the lost sale filled, the account would hold less, and another sale could
        sell another program's shares): None, or why it waits (the owner is told once)."""
        positions = self._read_positions()
        if positions is None:
            return "a sale of this lot was lost: the positions could not be read to see whether it filled"
        held = sum((A.dec(r.get("qty")) or ZERO for r in positions if str(r.get("asset_class") or "") == "us_equity"
                    and str(r.get("symbol") or "").upper() == lot.symbol), ZERO)
        want = self.expected_shares().get(lot.symbol, ZERO)
        if held + SHARE_TOLERANCE >= want:
            return None
        why = (f"a sale of lot {lot.lid} was lost and the account holds {text(held)} {lot.symbol}, less than the book's "
               f"{text(want)}: it may have filled; the owner looks before another sale")
        if not lot.info.get("lost_sale_told"):
            lot.info["lost_sale_told"] = True
            self._save_lot(lot)
            self.alert("error", f"equity: {why}")
        return why

    def _reprice_due(self, order: Order, now: float, reprice: float, m: S.Moments) -> bool:
        """Whether a working order is re-priced now: once it is `reprice` seconds old, while its collar can still widen;
        at the widest collar only when the quote has moved through its limit (a marketable order that does not fill is
        not helped by another, and each re-price costs two of the day's orders, A8.3). Its age is counted on the
        House's minute clock, from the `now` of the minute it was sent in (`answer.tick`) to this minute's `now`:
        `placed_at` is the wall clock at the POST, later than its minute's `now` by however long the options minute
        ran, and an age counted from it is always under a minute at the next minute (a 60-second re-price then went
        every second minute). THE AGE IS IN WHOLE HOUSE MINUTES (`house_minute`): two minute starts are 60 seconds
        apart give or take the milliseconds each pass started late, so their difference in seconds is under 60 as
        often as over it, and an age compared in seconds skipped every minute that started a hair earlier in its
        minute than the last. An order without the stamp (written by a process that stopped before its answer) is
        aged from `placed_at`, in seconds, exactly."""
        if order.status != "working":
            return False
        sent = order.answer.get("tick")
        if isinstance(sent, (int, float)) and not isinstance(sent, bool):
            if (house_minute(now) - house_minute(float(sent))) * 60 < reprice:
                return False
        elif now - order.placed_at < reprice:
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
            elif self.clock() < deadline and self._reprice_due(current, now, reprice, m):
                # (Never cancelled for a re-price its replacement could not follow: `_send`'s wall-clock cut-off.)
                self._cancel(current, "re-priced: cancel, then resend once it is terminal", now)
            orders = self._intent_orders(intent.iid)
            current = orders[-1]
            if current.working:
                return
            # The cancel's own lookup may have booked a fill, and with it the intent's lot (`_book_fill` saves the lot's
            # id on the row): read the row again, so nothing below saves or sends from the row as it was before.
            intent = self._intent(intent.iid) or intent
        et = self._et()
        min_order = Decimal(str(getattr(et, "min_order_usd", "10"))) if et is not None else Decimal("10")
        filled_qty = sum((o.filled_qty for o in orders), ZERO)
        filled_usd = sum((o.filled_value for o in orders), ZERO)
        target = orders[0].qty * orders[0].limit_px if orders else None
        if current is not None:
            final = current.status in ("rejected", "lost") or (current.status == "refused" and not current.again)
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
        # The collar widens with each order that reached the venue; one refused before it priced nothing.
        collar = collar_for(sum(1 for o in orders if o.status != "refused"), entry_bp, max_bp)
        limit = limit_for("buy", ask, collar)
        usd = None if target is None else target - filled_usd
        sized = self._size(intent, inst, symbol, klass, limit, usd, today)
        if sized is None:
            return
        if sized.qty <= 0:
            due = self._exits_due(today, now, m)
            if due:
                # Not final while an exit may still fill (A2: entries are sized on the cash after the exits; the Gym
                # fills a session's exits before it sizes its entries): sized again next minute, and the cut-off
                # records it missed with this reason when no exit filled in time.
                own = sum(1 for r in due if r["instance"] == intent.instance)
                why = (f"sizing ({sized.binding}): {sized.reason}; sized again when the exits still working fill "
                       f"({own} of its own program, {len(due)} in all)")
                if intent.why != why:
                    intent.why = why
                    self._save_intent(intent)
                return
            self._finish(intent, "done" if filled_qty > 0 else "refused", f"sizing ({sized.binding}): {sized.reason}")
            return
        if sized.binding != "intent" and self._cut_waits(inst):
            # B8 (release E4; A PANEL INSTANCE ONLY, `_cut_waits`): A CUT SIZE IS NOT FINAL WHILE AN EXIT OF ITS OWN
            # PROGRAM MAY STILL FILL. Sent now, the cut size would be the intent's whole target (a re-price sends target
            # minus filled of the FIRST order): with $40 idle in the sleeve and a $111 sale still working, a $111 buy
            # would go for $40 and stay there. Any binding but "intent": the sleeve's cash, the House-wide cash, the
            # invested cap and the budget's room all free up on the same sale. It is sized again each minute and goes
            # whole once its own program's exits have filled; its cut-off records it missed with this reason.
            own = [r for r in self._exits_due(today, now, m) if r["instance"] == intent.instance]
            if own:
                why = (f"sizing cut ({sized.binding}): {sized.reason}; it waits for {len(own)} exit(s) of its own "
                       "program still working and is sized again when they fill")
                if intent.why != why:
                    intent.why = why
                    self._save_intent(intent)
                return
        self._send(intent, side="buy", symbol=symbol, klass=klass, qty=sized.qty, limit=limit, collar=collar, day=today,
                   lid=intent.lid, replaces=current.eid if current is not None else None, probe=inst.band == "probe",
                   why=f"entry ({sized.binding}: {sized.reason})"[:300], tick=now, until=deadline)

    @staticmethod
    def _cut_waits(inst: Instance) -> bool:
        """Whether a buy of `inst` that a cap CUT waits while an exit of its own program is working (B8): a panel
        instance's, and NEVER one of the book's own kind. The spec's decision 27 wrote B8 for every instance; the
        captain's ruling at the ship check (Oct 11, 2026) keeps it to the panel kind, because the seated share
        programs trade real money under release E1's entry rule, on which their replay twins and their forward record
        are read: a share program's cut buy goes at the cut size, as on main, order for order
        (league/tests/test_equity_etf_orders.py holds it to weeks recorded on main). Whether E1's rule should change
        for share programs too is a decision of its own, with a rehearsal of its own."""
        return inst.kind == PANEL_KIND

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
        book = self._adapter(inst.kind) if inst.kind != EQUITY_KIND else None
        if book is not None and hasattr(book, "committed"):
            # A PANEL PROGRAM'S SLEEVE IS READ ON ENTRY NOTIONALS (the pre-registered contract's constant-weight
            # book, C3 and C8, as the Gym engine sizes its twin): a held name that rose takes no room from the next
            # lot, and a loss gives none back. Every wall of the account below is read at its marks, as before: a
            # stock's share of equity, the invested cap, the House's cash, the shared loss budget.
            own_value = book.committed(own_lots, working=[o.remaining * o.limit_px for o in own_buys])
            own_symbol = book.committed(own_lots, symbol=symbol,
                                        working=[o.remaining * o.limit_px for o in own_buys if o.symbol == symbol])
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
        """The program's share of E: the Probe sleeve, or a Sized program's (money's `sized_sleeve_share`). A PANEL
        program's (an instance of another kind than the book's own) is the panel row's (`equity_money.panel
        .sleeve_share`, league/equity/bands.py `panel_settings`) in every band: it never sizes from the Probe sleeve
        and is never sized up (the step is parked, A21; a row that cannot be read is no sleeve: it opens nothing)."""
        et = self._et()
        if inst.kind == PANEL_KIND:
            return Decimal(str(B.panel_settings().sleeve_share))
        if inst.kind == EVENT_KIND:
            # (release R2: an event position's own target share of E, Probe 0.05, Sized 0.10; the event kind sizes
            # one position at a time, `_size_event`, and holds no sleeve of its own)
            return self._event_settings().share(inst.band)
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
    #: The daily step's own memory in this process (kept on the class: the constructor is the whole book's): when the
    #: seating pass last asked an instance again, and the decision day whose unconfirmed instances were alerted.
    _seat_tried: float = float("-inf")
    _unconfirmed_day: str = ""
    _held_day: str = ""

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
        session's close window. Once the day's decision is recorded, THE SEATING PASS (`_seat_step`) runs every minute
        until that same cut-off: a program that passes its look after the decision (A10.4: the looks of a Sunday
        deploy) is seated and decided for the same close, so its first order goes in the next session and not the one
        after.

        `eq_decide` {day, status, at, instances, why}: `instances` names every instance asked for the day (decided, or
        its own decide failed): the seating pass asks the live ones it does not name. A record without the list (an idle
        or failed day, or one written by hand) is closed."""
        t = self._last_closed(now)
        if t is None:
            return
        day = t.isoformat()
        done = self.state.get("eq_decide", {}) or {}
        last = str(done.get("day") or "")
        if last > day:
            return
        off = self._offsets()
        mt, nxt = S.moments(t, off), S.next_session(t)
        mn = S.moments(nxt, off)
        cut = mn is not None and now >= mn.close_send - 60
        if last == day:
            if not cut:
                self._seat_step(now, t, mt, mn, done, out)
            return
        if cut:
            self._decide_failed(t, now, "no decide ran before the next session's close window")
            return
        et = self._et()
        if et is None:
            return
        # (Release R2: the event kind's lots and instances are the event step's, `_event_step`: they never wake, wait
        # or join the 16:30 decide, so with the old lanes off and only event lots held the day is idle as before.)
        if not et.enabled and not [lot for lot in self._lots() if lot.lane != EVENT_LANE]:
            self.state.put("eq_decide", {"day": day, "status": "idle", "at": now, "why": "the lane is off and holds nothing"})
            return
        if (self.state.get("eq_synced") or "") != day and self._sync_instances(now, t, out):
            self.state.put("eq_synced", day)
        live = [i for i in self._instances(alive=True) if i.live and i.kind != EVENT_KIND]
        bars = self._day_bars(now, t, mt, live, live, out)
        # B3 (release E4): the panel instances' own bars, read beside the book's from 16:20. While their fetch is
        # being read, or read again for a missing bar inside the grace, they are not asked in this pass (the seating
        # pass asks them for the same close once it is whole); the book's own programs do not wait for it.
        panel = self._panel_bars(now, t, mt, mn, [i for i in live if i.kind == PANEL_KIND], out)
        if bars is None:
            return
        if (self.state.get("eq_synced") or "") != day and self._unconfirmed_day != day:
            # The day's band sync never completed (the store could not be read): said once, never silent.
            self._unconfirmed_day = day
            self.alert("warning", f"equity: the families could not be read for the band sync of {day} "
                                  f"({out.get('families') or 'no reading'}): no band moved and nobody was retired; the "
                                  "programs the book holds decide as they are")
        if (panel or {}).get("wait") and not et.enabled:
            return      # (exits only: no seating pass will ask them later, so the day's decision waits for their bars)
        ask = [i for i in live if i.kind == EQUITY_KIND or not (panel or {}).get("wait")]
        if ask:
            self._decide(t, ask, bars, now, out, panel=panel)
        self._house_exits(t, now)
        record = {"day": day, "status": "done", "at": now,
                  "instances": sorted(i.id for i in live if i.last_decided_day == day)}
        if not live:
            record["why"] = "no live program"
        self.state.put("eq_decide", record)

    def _seat_step(self, now: float, t: dt.date, mt: S.Moments, mn: S.Moments | None, done: Mapping[str, Any],
                   out: dict) -> None:
        """THE SEATING PASS, between a recorded decision and the next session's close window (`_decide_step`): the
        families read again (`_sync_instances(late=True)`: a Candidate holding a seat goes to Probe and gets its
        instance; nothing else moves, nobody is retired), then every live instance the day's record does not name is
        asked for the same close on the same bars (`_decide` skips one already asked). An instance the House could
        not ask (no bar, the decider) is asked again every `SEAT_RETRY_S` until the next session's pre-open (after it
        the book it holds is no longer the close's); its failed decide is counted once a session. The House's exit
        rules are the day's decision's own and are not run again here (a program seated now holds no lot), BUT FOR
        ONE: an instance of another kind than the book's own (a panel program, which the day's decision leaves to
        this pass while its bars are read) whose failed decide THIS pass counted, and whose count reached the exit
        rule, has its lots' exits planned now, for the next open."""
        handled = done.get("instances")
        if done.get("status") != "done" or not isinstance(handled, list):
            return
        et = self._et()
        if et is None or not et.enabled:
            return
        self._sync_instances(now, t, out, late=True)
        live = [i for i in self._instances(alive=True) if i.live and i.kind != EVENT_KIND]
        day = t.isoformat()
        counted = self.state.get("eq_failed", {}) or {}
        # (A17: a hold day the House could not ask is tried again on the same clock, though it is counted nowhere.)
        tried = {**{k: (v or {}).get("day") for k, v in (self.state.get("eq_hold_failed", {}) or {}).items()}, **counted}
        again = mn is None or now < mn.preopen
        fresh = [i for i in live if i.id not in handled and (again or tried.get(i.id) != day)]
        if not fresh:
            return
        if all(tried.get(i.id) == day for i in fresh) and now - self._seat_tried < SEAT_RETRY_S:
            return
        bars = self._day_bars(now, t, mt, live, fresh, out, held=False)
        # THE PANEL'S FETCH IS NEVER MADE INSIDE A SESSION (the review's live-6): from the next session's pre-open on,
        # a panel instance is asked only on the day's KEPT fetch; with none (the first panel program seated after the
        # decision, a catch-up after a restart) it waits for the next close's own 16:20 read. Its 28 calls for 500
        # columns ran here ahead of that minute's exits and entries, the open and close windows' minutes included,
        # for a decision that could not be executed that session anyway.
        panel = self._panel_bars(now, t, mt, mn, [i for i in fresh if i.kind == PANEL_KIND], out, fetch=again)
        if bars is None:
            return
        if (panel or {}).get("wait"):
            fresh = [i for i in fresh if i.kind == EQUITY_KIND]
            if not fresh:
                return
        self._seat_tried = now
        self._decide(t, fresh, bars, now, out, panel=panel)
        # A FAILED DECIDE COUNTED HERE THAT REACHES THE EXIT RULE (the review's live-7): a panel decide whose bars are
        # not whole is always recorded by this pass (the day's decision went ahead without it while it waited), and the
        # House's exit rules ran with that decision, before the count. Its lots exit AT THE NEXT OPEN, as the alert
        # says and as the Gym does, not a session late: the rules are run again for the instances just counted.
        others = [i for i in fresh if i.kind == PANEL_KIND]        # (none: nothing more is read or planned)
        if others:
            counted_now = self.state.get("eq_failed", {}) or {}
            failed_exit = self._holds()[3]
            due = set()
            for i in others:
                if counted_now.get(i.id) == day and counted.get(i.id) != day:
                    again_inst = self._instance(i.id)
                    if again_inst is not None and again_inst.failed_decides >= failed_exit:
                        due.add(i.id)
            if due and (mn is None or now < mn.open_send):
                self._house_exits(t, now, only=due)
        asked = sorted(set(handled) | {i.id for i in fresh if i.last_decided_day == day})
        if asked != sorted(handled):
            record = {k: v for k, v in done.items() if k != "why"}
            self.state.put("eq_decide", {**record, "instances": asked, "seated_at": now})

    def _lot_symbols(self, day: str) -> set[str]:
        """The symbols of the lots open now, or opened or closed in session `day`: their bars are read whether or not a
        live program still needs them (a retired or demoted program's last lot is priced on its exit day's bar: its
        twin, league/ops/twins.py, and the buy-and-hold beside it)."""
        return {str(r["symbol"]) for r in self.state.rows(
            "SELECT DISTINCT symbol FROM eq_lots WHERE (status IN ('open', 'closing') OR opened_day=? OR exit_day=?) "
            "AND lane!=?", (day, day, EVENT_LANE))}

    def _day_bars(self, now: float, t: dt.date, mt: S.Moments, live: Sequence[Instance], asked: Sequence[Instance],
                  out: dict, *, held: bool = True) -> Mapping[str, Any] | None:
        """Session t's bars for a decide of `asked`, read (`_fetch_bars`) when the ones held lack a symbol: the NEEDS of
        every live program and the lots' own symbols (`_lot_symbols`), one fetch for them all. None while the decide
        must wait: before 16:30 (`decide_at`) with a program to ask, or within `BARS_GRACE_S` of it while a bar is
        still missing (after it the decide goes without: a program that needs the bar fails, a lot without it has no
        priced twin). `held` False (the seating pass): only the asked programs' bars are waited for or cause a read."""
        day = t.isoformat()
        for inst in live:
            self._ensure_loaded(inst)
        lots = self._lot_symbols(day)
        need = {s for i in asked for s in (self._needs.get(i.id) or {}).get("symbols", [])} | (lots if held else set())
        symbols = sorted({s for i in live for s in (self._needs.get(i.id) or {}).get("symbols", [])} | lots)
        history = max([int((self._needs.get(i.id) or {}).get("history", 0)) for i in live] + [1])
        bars = self._bars if self._bars is not None and self._bars.get("day") == day else None
        if need - set((bars or {}).get("present") or ()):
            try:
                self._fetch_bars(t, symbols, history, now)
            except Exception as exc:  # noqa: BLE001 - read again next minute (the decide waits for its grace)
                self._error("bars", exc, out)
            bars = self._bars if self._bars is not None and self._bars.get("day") == day else None
        if asked and now < mt.decide_at:
            return None
        missing = need - set((bars or {}).get("present") or ())
        if missing and now < mt.decide_at + BARS_GRACE_S:
            out["decide"] = f"waiting for the bars of {', '.join(sorted(missing))}"
            return None
        return bars or {"day": day, "symbols": [], "present": [], "raw": {}, "all": {}}

    def _sync_instances(self, now: float, t: dt.date, out: dict, *, late: bool = False) -> bool:
        """The equity families' rows against the book's instances: band moves (`bands.next_band`, the book alone moves
        candidate <-> probe <-> sized, while the lane is enabled), a Probe or Sized row's instance created or updated, and
        every instance whose family no longer runs it retired (its lots exit at the next open, planned in
        `_house_exits`). An unreadable store changes nothing.

        RETIRED ONLY ON POSITIVE EVIDENCE (A8.5; INTERFACES 5.5): a row of the read that names another version or a
        band that does not run, or, for a family with no row at all, the store's own word on it (`families.standing`:
        retired, another version, a band that does not run, a proof that is not the current equity identity). A family
        that is merely absent from one read, or whose standing cannot be read, keeps its instance: nothing changes, the
        owner is told once a decision day, and the sync is not recorded done (False: it runs again next minute). A
        retirement is an alert. A retired instance whose row is back in a running band on the same version and program
        runs again, unless its version's demotion is sticky (EDM1).

        HELD (release E4; E4-SPEC 17): a family the store says runs while a store-side leg of its LANE failed
        (`families.HELD`: a panel family with the lane's switch at "live" and the nightly I6, the twin marker, the
        store's freshness or the universe not holding) keeps its instance and its lots. ITS OPENS STOP (it has no row:
        `_seat_block` holds every entry at the send) AND ITS EXITS GO ON (it is still asked at every close: its
        program's sells, its ineligible lots, max hold and the failed-decides rule). Nothing is retired and nothing is
        sold on a failed leg: only the captain's switch demotes. The owner is told once a decision day, critically,
        with the leg named, and the sync is done.

        `late` (THE SEATING PASS, `_seat_step`): only a Candidate moves (to Probe, when it holds a free seat) and only a
        new instance is made, of a family none of whose versions runs. No demotion, no sizing up, no update of a
        running instance, no retirement, no revival: those are the decision's own, once a day."""
        et = self._et()
        rows = [dict(r) for r in self.families.read() if str(r.get("lane") or "") in _pkg.LANES]
        if getattr(self.families, "last_error", ""):
            out["families"] = f"unreadable: {self.families.last_error}"
            return False
        sticky = dict(self.state.get("eq_sticky", {}) or {})
        since = dict(self.state.get("eq_band_since", {}) or {})
        before = (dumps(sticky), dumps(since))
        day = t.isoformat()
        rule = B.seat_settings()
        #: {instance key: the session a seat taken in this sync counts from, when it is not the next one}, filled by
        #: `_seat_bands`.
        counts_from: dict[str, str] = {}
        pools = self._pools(rows)
        if et is not None and et.enabled and not rule.first_come:
            # THE SEAT RULE in force (the module docstring): the book ranks the waiting programs itself, A POOL AT A
            # TIME (`_pools`: the ETF pool's rows, then the panel pool's). Its own trouble (a row or a day it cannot
            # read) moves no further seat and NEVER stops the day's decision: the programs the book holds decide as
            # they are, and the error is recorded each time.
            for pool, part in pools:
                try:
                    self._seat_bands(part, et, rule, sticky, since, day, now, out, late=late, counts_from=counts_from,
                                     pool=pool)
                except Exception as exc:  # noqa: BLE001
                    self._error("seats" if pool == POOL_ETF else "panel seats", exc, out)
        elif et is not None and et.enabled:
            # "first-come" (the rollback): release E5-S's band sync, to the line, a pool at a time: the ETF pool's
            # count is `probe.max_programs` as it was, the panel pool's `_panel_seat_count`.
            for pool, part in pools:
                cap = int(et.probe_max_programs) if pool == POOL_ETF else self._panel_seat_count()
                live_n = sum(1 for r in part if r.get("band") in LIVE_BANDS) + len(self._held_seats(pool, part))
                for row in part:
                    if row.get("band") not in ("candidate",) + LIVE_BANDS:
                        continue
                    if late and row.get("band") != "candidate":
                        continue
                    key = instance_key(row["family"], int(row["version"]))
                    try:
                        record = self._record_of(row["family"], int(row["version"]), row, refetch=not late)
                        band, why = B.next_band(row, record, et, seat_free=live_n < cap
                                                or row.get("band") in LIVE_BANDS, sticky=sticky.get(key))
                    except Exception as exc:  # noqa: BLE001 - no move on a rule that cannot be read
                        self._error(f"band {row['family']}", exc, out)
                        continue
                    if band == row.get("band"):
                        continue
                    if not self.families.confirm_band(row, band, why):
                        out.setdefault("bands", []).append(f"{row['family']}: the row changed; no move")
                        continue
                    self.record("equity.band", {"family": row["family"], "version": row["version"],
                                                "from": row["band"], "to": band, "why": why[:300]}, agent=row["family"])
                    if band == "candidate" and row.get("band") in LIVE_BANDS:
                        sticky[key] = why[:300]
                        live_n -= 1
                    elif row.get("band") == "candidate" and band in LIVE_BANDS:
                        live_n += 1
                    row["band"] = band
                    since[key] = {"band": band, "day": day}
        if et is not None and rule.first_come:
            for pool, part in pools:
                try:
                    self._seat_note_first_come(part, et, since, day, pool=pool)
                except Exception as exc:  # noqa: BLE001 - a note for the health page: never the band sync's end
                    self._error("seats" if pool == POOL_ETF else "panel seats", exc, out)
        if not late or dumps(sticky) != before[0]:
            self.state.put("eq_sticky", sticky)
        holds = self._holds()
        wanted: dict[str, dict] = {}
        for row in rows:
            if row.get("band") in LIVE_BANDS:
                wanted[instance_key(row["family"], int(row["version"]))] = row
        running = {i.family for i in self._instances(alive=True)} if late else set()
        for key, row in wanted.items():
            inst = self._instance(key)
            params = dict(row.get("params") or {})
            if inst is None and str(row["family"]) in running:
                continue   # another version of it still runs: the decision retires that one and starts this one
            if inst is None:
                inst = Instance(key, str(row["family"]), int(row["version"]), str(row.get("lane") or ""),
                                str(row.get("run_sha") or ""), str(row.get("code") or ""), params, str(row["band"]),
                                bool(row.get("seeded")), holds[1], created_at=now,
                                kind=K.kind_of(row.get("structure")))
                since.setdefault(key, {"band": inst.band, "day": day})
                self.record("equity.instance", {"instance": key, "band": inst.band, "lane": inst.lane}, agent=inst.family)
            elif late and not (inst.retired_at is not None and str(inst.why).startswith(YIELDED)):
                # A running instance is the decision's own to update; a retired one its own to bring back. But a
                # program that yielded an idle seat (THE SEAT RULE) holds nothing, and a seat it returns into in the
                # seating pass is its own again at once: it falls through to the revival below. Under "first-come"
                # too (a rollback with a yielded program waiting): its band moved in this pass, and it is asked for
                # the same close, not a decision later.
                continue
            elif inst.retired_at is not None:
                # The family runs this version again (the swarm banded it again; an instance retired on a read that
                # proved wrong): the same key runs again. Never a sticky demotion (EDM1 holds for the version), and
                # never another program under the same version.
                if key in sticky or inst.run_sha != str(row.get("run_sha") or ""):
                    continue
                inst.retired_at, inst.why, inst.band = None, "", str(row["band"])
                inst.code, inst.params, inst.seeded = str(row.get("code") or ""), params, bool(row.get("seeded"))
                since[key] = {"band": inst.band, "day": day}
                self.record("equity.instance", {"instance": key, "band": inst.band, "lane": inst.lane, "revived": True},
                            agent=inst.family)
                self.alert("warning", f"equity: {key} runs again (its family's row is back in the {inst.band} band)")
            else:
                inst.band, inst.code, inst.params, inst.run_sha = str(row["band"]), str(row.get("code") or ""), params, \
                    str(row.get("run_sha") or "")
                inst.seeded = bool(row.get("seeded"))
            self._save_instance(inst)
        for key, first in counts_from.items():
            # (The revival above writes the mark again: a seat taken after its session's open keeps the session it
            # counts from, `_seat_bands`.)
            if isinstance(since.get(key), dict) and since[key].get("day") == day and since[key].get("band") in LIVE_BANDS:
                since[key]["seat"] = first
        if not late or dumps(since) != before[1]:
            self.state.put("eq_band_since", since)
        if late:
            return True
        from .families import GONE, HELD

        by_family = {str(r["family"]): r for r in rows}
        unconfirmed, held = [], []
        for inst in self._instances(alive=True):
            if inst.id in wanted or inst.kind == EVENT_KIND:     # (an event program is no swarm family: `_event_sync`)
                continue
            row = by_family.get(inst.family)
            if row is None:
                code, why = self._standing(inst)
                if code == HELD:
                    held.append(f"{inst.id} ({why})")
                    continue
                if code not in GONE:
                    unconfirmed.append(f"{inst.id} ({why})")
                    continue
            elif int(row.get("version") or 0) != inst.version:
                code, why = "retired", f"superseded by version {row.get('version')}"
            else:
                code, why = "demoted", f"its band is {row.get('band')}"
            inst.retired_at, inst.why, inst.band = now, f"{code}: {why}", ("candidate" if code == "demoted" else inst.band)
            self._save_instance(inst)
            self._drop(inst)
            self.record("equity.instance", {"instance": inst.id, "retired": True, "why": inst.why}, agent=inst.family)
            self.alert("warning", f"equity: {inst.id} is {inst.why}: it decides no more and its lots exit at the next "
                                  "open")
        if held:
            out["seats_held"] = f"{'; '.join(held)}: opens stop, exits go on, nothing retired"
            if self._held_day != day:
                self._held_day = day
                self.alert("error", f"equity: {'; '.join(held)}: its lane is not ready, so it OPENS NOTHING; it keeps "
                                    "its lots, its exits and the House's exit rules go on, and nothing was retired or "
                                    "sold on it (only the captain's switch demotes)")
        if unconfirmed:
            out["families"] = f"no row and no word of the store on {'; '.join(unconfirmed)}: nothing retired"
            if self._unconfirmed_day != day:
                self._unconfirmed_day = day
                self.alert("warning", f"equity: the families read has no row for {'; '.join(unconfirmed)} and the "
                                      "swarm store does not say it stopped: it keeps running. Look at its family in "
                                      "swarm.sqlite (its band, banded_version and code file)")
            return False
        return True

    # ------------------------------------------------------------------ the seat rule (A24)
    def _seat_count(self, et: Any) -> int:
        """The seats there are: `equity_money.probe.max_programs`, or fewer when the swarm's roster says fewer
        (`families.seats()`: `elane.roster`, failing closed to 0, so an unreadable roster seats nobody new; a reader
        that has no word of it, None, leaves the table's count)."""
        table = int(et.probe_max_programs)
        read = getattr(self.families, "seats", None)
        if read is None:
            return table
        try:
            roster = read()
        except Exception:  # noqa: BLE001 - fail closed: no new seat
            return 0
        return table if roster is None else max(0, min(table, int(roster)))

    def _panel_seat_count(self) -> int:
        """The PANEL POOL's seats: `equity_money.panel.seats` (league/equity/bands.py `panel_settings`; a row that
        cannot be read seats nobody), or fewer when the swarm says fewer (`families.panel_seats()`:
        `elane.panel.seats`, which may only lower the row, failing closed to 0; a reader that has no word of it, None,
        leaves the row's count)."""
        table = int(B.panel_settings().seats)
        read = getattr(self.families, "panel_seats", None)
        if read is None:
            return table
        try:
            said = read()
        except Exception:  # noqa: BLE001 - fail closed: no new seat
            return 0
        return table if said is None else max(0, min(table, int(said)))

    def _held_seats(self, pool: str, rows: Sequence[Mapping[str, Any]]) -> list[str]:
        """THE SEAT OF A PANEL PROGRAM HELD ON A FAILED LEG (release E4 step two): the panel pool's alive instances
        whose family has no row in this read (its lane holds its opens: `families.HELD`, or a read that showed it
        nothing). Each keeps its seat, so nobody is seated into it, before or after the leg recovers (every leg of the
        panel lane is the lane's: while one fails no panel row exists at all, and when it recovers the holder's row is
        back). The ETF pool counts its rows alone, as main's rule did: []."""
        if pool == POOL_ETF:
            return []
        shown = {str(r["family"]) for r in rows}
        return sorted({i.family for i in self._instances(alive=True) if i.kind == PANEL_KIND and i.family not in shown})

    def _pool_of_key(self, key: str) -> str:
        """The pool of an instance key: the panel pool's when its instance is of another kind than the book's own,
        else the ETF pool's; a family the band sync's rows hold of the panel's kind is the panel pool's (an instance
        the book never made, of no such row, is read as an ETF program's, as main read every one)."""
        if str(key).split("@", 1)[0] in getattr(self, "_panel_families", ()):
            return POOL_PANEL
        try:
            inst = self._instance(key)
        except Exception:  # noqa: BLE001 - a row that cannot be read is main's
            return POOL_ETF
        return POOL_PANEL if inst is not None and inst.kind == PANEL_KIND else POOL_ETF

    def _pool_seats(self, et: Any, pool: str) -> int:
        """A pool's seats: the ETF pool's `_seat_count`, the panel pool's `_panel_seat_count`."""
        return self._seat_count(et) if pool == POOL_ETF else self._panel_seat_count()

    def _pools(self, rows: list[dict]) -> list[tuple[str, list[dict]]]:
        """THE TWO POOLS of a band sync's rows (`POOL_ETF`, `POOL_PANEL`): a row of the book's own kind (an ETF
        program) is the ETF pool's, a row of any other kind (a panel program) the panel pool's. The same dicts in the
        reader's order, so a move the rule makes in a pool is the sync's own. The panel pool is left out while it has
        no row and no plan was ever written for it: a book of ETF programs alone runs main's rule, to the line."""
        etf = [r for r in rows if K.kind_of(r.get("structure")) == EQUITY_KIND]
        panel = [r for r in rows if K.kind_of(r.get("structure")) == PANEL_KIND]
        self._panel_families = {str(r["family"]) for r in panel}
        out = [(POOL_ETF, etf)]
        if panel or self._pool_plan(POOL_PANEL) is not None:
            out.append((POOL_PANEL, panel))
        return out

    def _pool_plan(self, pool: str) -> dict[str, Any] | None:
        """A pool's plan as the last sync wrote it: the ETF pool's is `SEAT_KEY` itself, the panel pool's
        `SEAT_KEY`'s `SEAT_PANEL`. None when there is none."""
        plan = self.state.get(SEAT_KEY)
        if pool != POOL_ETF:
            plan = plan.get(SEAT_PANEL) if isinstance(plan, Mapping) else None
        return dict(plan) if isinstance(plan, Mapping) else None

    def _put_plan(self, pool: str, plan: Mapping[str, Any]) -> None:
        """Write a pool's plan: the ETF pool's is `SEAT_KEY` itself (the panel pool's kept inside it as it stands),
        the panel pool's goes under `SEAT_PANEL` and touches nothing of the ETF pool's."""
        held = self.state.get(SEAT_KEY)
        held = dict(held) if isinstance(held, Mapping) else {}
        if pool == POOL_ETF:
            plan = {k: v for k, v in plan.items() if k != SEAT_PANEL}
            if isinstance(held.get(SEAT_PANEL), Mapping):
                plan[SEAT_PANEL] = held[SEAT_PANEL]
            self.state.put(SEAT_KEY, plan)
        else:
            self.state.put(SEAT_KEY, {**held, SEAT_PANEL: {k: v for k, v in plan.items() if k != SEAT_PANEL}})

    def _flat(self, key: str) -> bool:
        """FLAT, structurally: the instance has no lot open or closing, NO ORDER THAT MAY STILL FILL, and no intent
        planned or sent. Read from the book's own rows, every time it is asked.

        AN ORDER THAT MAY STILL FILL is one the order path may still bring up to a venue row (`_absorb`, the only way
        a fill is booked, and a buy's fill the only way a lot is made): every order of `WORKING` (pending, working,
        unknown), whatever its age, and an order GIVEN UP AS LOST for as long as `_sync_orders` may take it back and
        a day more (`LOST_HOLDS_SEAT_DAYS`; the captain's A30 (3): a lost buy is not flat). Every other status is
        the order's end: the order path never reads the venue for it again. So a program that yields its seat (THE
        SEAT RULE: only a flat one can) has no order through which a lot could be booked to it afterwards
        (league/tests/test_equity_seats_a30.py asks the order path itself, status by status)."""
        rows = self.state.rows
        marks = ", ".join("?" for _ in WORKING)
        horizon = (S.ny_day(self.clock()) - dt.timedelta(days=LOST_HOLDS_SEAT_DAYS)).isoformat()
        return not (rows("SELECT 1 AS x FROM eq_lots WHERE instance=? AND status IN ('open', 'closing') LIMIT 1", (key,))
                    or rows(f"SELECT 1 AS x FROM eq_orders WHERE instance=? AND status IN ({marks}) LIMIT 1",
                            (key, *WORKING))
                    or rows("SELECT 1 AS x FROM eq_orders WHERE instance=? AND status='lost' AND day>=? LIMIT 1",
                            (key, horizon))
                    or rows("SELECT 1 AS x FROM eq_intents WHERE instance=? AND status IN ('planned', 'sent') LIMIT 1",
                            (key,)))

    def _last_ask(self, key: str) -> str | None:
        """The last session day on which the instance ASKED for a buy (A24 item 3), from the book's own rows, or None:
        (a) a buy order that REACHED THE VENUE (the venue gave it an id, answered it with its own rejection, or its
        answer is still unknown or pending; one the House or the gateway refused before the venue, or the venue never
        showed, did not); (b) a buy the LOSS BUDGET cut (its order's reason names the budget, sent or not); (c) a buy
        the loss budget refused, or cut under the minimum order (its intent's reason: `_budget_asked`). A buy refused
        by the instrument cap, the invested cap, cash or the program's own sleeve is NOT asked: it is in none of them."""
        rows = self.state.rows
        days = [r["day"] for r in rows(
            "SELECT MAX(day) AS day FROM eq_orders WHERE instance=? AND side='buy' AND (venue_id IS NOT NULL OR status IN "
            "('pending', 'unknown', 'rejected') OR why LIKE 'entry (budget:%')", (key,)) if r["day"]]
        for r in rows("SELECT exec_day, why FROM eq_intents WHERE instance=? AND kind='buy' AND why LIKE '%sizing (%' "
                      "ORDER BY exec_day DESC, iid DESC", (key,)):
            if _budget_asked(r["why"]):
                days.append(r["exec_day"])
                break
        return max(days) if days else None

    def _seat_facts(self, row: Mapping[str, Any], since: dict, flags: Mapping[str, Any], day: str,
                    refused: Mapping[str, Any] | None = None) -> B.SeatFacts:
        """One passed program as the seat rule reads it (`bands.SeatFacts`): K from the row's two counts, its pass
        time, its idle flag, and for a seated one its seat's day (`eq_band_since`: the decision day it was seated, or
        its mark's `seat`, the session a seat taken after that session's open counts from; a holder with no mark gets
        today's), the sessions since, the sessions since its last asked buy, and `_flat`. BOTH COUNTS LEAVE OUT THE
        SESSIONS IN WHICH THE HOUSE REFUSED EVERY OPEN (`refused`: `_refused_days`; A30 (2), `_counted`)."""
        family = str(row["family"])
        key = instance_key(family, int(row["version"]))
        passed = row.get("passed_at")
        passed = float(passed) if isinstance(passed, (int, float)) and not isinstance(passed, bool) \
            and math.isfinite(float(passed)) else None
        facts = B.SeatFacts(family=family, k=B.seat_k(row.get("seat_activity")), passed_at=passed,
                            flagged=family in flags and row.get("band") not in LIVE_BANDS, seeded=bool(row.get("seeded")))
        if row.get("band") not in LIVE_BANDS:
            return facts
        mark = since.get(key) if isinstance(since.get(key), Mapping) else None
        if not mark or mark.get("band") not in LIVE_BANDS or not mark.get("day"):
            mark = since[key] = {"band": str(row["band"]), "day": day}
        last = self._last_ask(key)
        first = str(mark.get("seat") or mark["day"])
        refused = refused or {}
        return replace(facts, seat_day=first, seated_sessions=_counted(first, day, refused)[0],
                       quiet_sessions=None if last is None else _counted(last, day, refused)[0], flat=self._flat(key))

    def _seat_bands(self, rows: list[dict], et: Any, rule: B.SeatSettings, sticky: dict, since: dict, day: str,
                    now: float, out: dict, *, late: bool, counts_from: dict | None = None, pool: str = POOL_ETF) -> None:
        """THE SEAT RULE "activity-1-free" AT A BAND SYNC (A24; the module docstring), on rows that hold every passed
        Candidate. In order: (1) the holders judged as before the rule (EDM1, sticky; the sizing-up step); (2) EDM1
        over the waiting programs that have a real record; (3) the plan (`bands.seat_plan`: the idle test, and who
        would still wait once every free seat is filled); (4) one idle seat yields when an unflagged program would
        still wait, and none yielded today (`_yield`); (5) the seats now free, best-ranked first, falling through a
        seating that does not take. `late` (the seating pass): (5) only. `rows`, `sticky` and `since` are updated in
        place; the plan is written to `SEAT_KEY`. (The study's simulator ran the idle test before filling a free
        seat; `bands.seat_plan` says what that changes and why A24's words, as A30 (1) reads them, decide it.)

        THE IDLE CLOCK (A30 (2)): a holder's seated sessions and its sessions since its last asked buy leave out
        every session in which the House refused every open (`_refused_days`). A SEAT'S FIRST SESSION: a seat taken
        before the next session's open (at the day's decision, or in the seating pass that evening or morning) counts
        from that next session; one taken once that session's open has begun (09:30:30: its open entries can no
        longer all go; the seating pass during the session, or a decision caught up after a restart) counts from the
        session after it (`eq_band_since`'s `seat`, kept beside the mark's own `day`, which stays the decision day
        every other reader of the mark knows), so the idle test never names a program before it sat through
        `idle_sessions` whole sessions. A STALE FLAG: a program whose band is live holds a seat, however it came by
        it (a rollback seats by pass time), and its idle flag is dropped.

        ONE POOL (`pool`; release E4 step two): `rows` are that pool's alone (`_pools`), its seats are the pool's
        (`_pool_seats`) and its plan and memory are the pool's (`_pool_plan`, `_put_plan`): the ETF pool's are
        main's, to the key, and a panel program never takes, holds or yields an ETF seat."""
        memory = {k: v for k, v in (self._pool_plan(pool) or {}).items() if k != SEAT_PANEL}
        flags = {str(k): v for k, v in (memory.get("idle") or {}).items()} if isinstance(memory.get("idle"), Mapping) else {}
        for row in rows:
            if row.get("band") in LIVE_BANDS:
                flags.pop(str(row["family"]), None)
        passed = dict(memory.get("passed") or {}) if isinstance(memory.get("passed"), Mapping) else {}
        last = memory.get("last")
        refused = self._refused_days()
        # (The day's own decision runs before the next open, but for a catch-up after a restart: the same rule then.)
        nxt = S.next_session(day)
        mn = S.moments(nxt, self._offsets())
        first_session = nxt.isoformat() if mn is not None and now >= mn.open_send else day

        def key_of(row: Mapping[str, Any]) -> str:
            return instance_key(row["family"], int(row["version"]))

        def move(row: dict, band: str, why: str) -> bool:
            if not self.families.confirm_band(row, band, why):
                out.setdefault("bands", []).append(f"{row['family']}: the row changed; no move")
                return False
            self.record("equity.band", {"family": row["family"], "version": row["version"], "from": row["band"],
                                        "to": band, "why": why[:300]}, agent=row["family"])
            row["band"] = band
            since[key_of(row)] = {"band": band, "day": day}
            return True

        if not late:
            for row in rows:                                   # (1) the holders: EDM1 (sticky) and the sizing-up step
                if row.get("band") not in LIVE_BANDS:
                    continue
                key = key_of(row)
                try:
                    record = self._record_of(row["family"], int(row["version"]), row, refetch=True)
                    band, why = B.next_band(row, record, et, seat_free=True, sticky=sticky.get(key))
                except Exception as exc:  # noqa: BLE001 - no move on a rule that cannot be read
                    self._error(f"band {row['family']}", exc, out)
                    continue
                if band != row.get("band") and move(row, band, why) and band == "candidate":
                    sticky[key] = why[:300]
            for row in rows:                                   # (2) EDM1 covers a waiting program too
                key = key_of(row)
                if row.get("band") != "candidate" or key in sticky or not row.get("holdout_passed"):
                    continue
                try:
                    record = self._record_of(row["family"], int(row["version"]), row, refetch=False)
                    why = B.edm1(record, et) if record.n else None
                except Exception as exc:  # noqa: BLE001 - a record that cannot be read demotes nobody
                    self._error(f"band {row['family']}", exc, out)
                    continue
                if why:
                    sticky[key] = f"EDM1: {why}"[:300]
                    flags.pop(str(row["family"]), None)
                    self.record("equity.seat", {"action": "waiting_demoted", "family": row["family"],
                                                "version": row["version"], "day": day, "rule": rule.rule,
                                                "why": sticky[key], **_pooled(pool)}, agent=row["family"])
                    self.alert("warning", f"equity: {key} waited for a seat and is demoted ({sticky[key][:200]}): it "
                                          "takes no seat again under this version")
        holders = [r for r in rows if r.get("band") in LIVE_BANDS]
        waiting = [r for r in rows if r.get("band") == "candidate" and r.get("holdout_passed") and key_of(r) not in sticky]
        held = self._held_seats(pool, rows)
        seats = max(0, self._pool_seats(et, pool) - len(held))
        facts = {str(r["family"]): self._seat_facts(r, since, flags, day, refused) for r in holders + waiting}

        def plan_now(yielded: bool) -> dict[str, Any]:
            return B.seat_plan([facts[str(r["family"])] for r in holders], [facts[str(r["family"])] for r in waiting],
                               seats=seats, settings=rule, late=late, yielded_today=yielded)

        plan = plan_now(memory.get("yield_day") == day)                                              # (3) the idle test
        if plan["yields"]:                                                                           # (4) one yield
            goes = facts[plan["yields"]]
            row = next(r for r in holders if str(r["family"]) == goes.family)
            why = (f"it yields its idle seat: flat, and no buy of its own reached the venue or was cut or refused by "
                   f"the loss budget in its last {rule.idle_sessions} seated sessions (seated {goes.seated_sessions}); "
                   f"{plan['for']} waits unflagged (seat rule {rule.rule})")
            if self._yield(row, why, str(plan["for"]), rule, since, memory, flags, day, now, out, pool=pool):
                holders.remove(row)
                waiting.append(row)
                facts[goes.family] = self._seat_facts(row, since, flags, day, refused)
                last = memory.get("last")
            plan = plan_now(True)           # the queue as it stands: with the yielded program flagged, or without a yield
        free = max(0, seats - len(holders))
        by_family = {str(r["family"]): r for r in waiting}
        for position, family in enumerate(plan["queue"], 1):                                         # (5) the free seats
            if free <= 0:
                break
            f = facts[family]
            row = by_family[f.family]
            key = key_of(row)
            try:
                record = self._record_of(row["family"], int(row["version"]), row, refetch=not late)
                band, why = B.next_band(row, record, et, seat_free=True, sticky=sticky.get(key))
            except Exception as exc:  # noqa: BLE001 - no move on a rule that cannot be read: the next one is asked
                self._error(f"band {row['family']}", exc, out)
                band, why = "candidate", "its band rule could not be read"
            if band in LIVE_BANDS and move(row, band, why):
                free -= 1
                waiting.remove(row)
                holders.append(row)
                returned = flags.pop(f.family, None) is not None
                passed.pop(f.family, None)
                if first_session != day:
                    since[key]["seat"] = first_session
                    if counts_from is not None:
                        counts_from[key] = first_session
                facts[f.family] = self._seat_facts(row, since, flags, day, refused)
                last = {"day": day, "action": "returned" if returned else "seated", "family": f.family, "rank": position,
                        "why": ("it returns into a free seat by rank, with no new look" if returned else
                                "a free seat goes to the best-ranked waiting program") + f" (seat rule {rule.rule})"}
                self.record("equity.seat", {**last, "version": row["version"], "seeded": bool(row.get("seeded")),
                                            "rule": rule.rule, **_pooled(pool)}, agent=f.family)
                continue
            if band not in LIVE_BANDS and record_edm1(why):
                # EDM1 named a waiting program at its seating (its twins were priced since the last sync): sticky, so
                # the seat is not offered to it again; the same record and the same alert as the day's own pass (2),
                # its idle flag dropped, and it is out of the plan's waiting list at once (the plan is true).
                sticky[key] = why[:300]
                flags.pop(f.family, None)
                passed.pop(f.family, None)
                waiting.remove(row)
                self.record("equity.seat", {"action": "waiting_demoted", "family": f.family, "version": row["version"],
                                            "day": day, "rank": position, "rule": rule.rule, "why": sticky[key],
                                            **_pooled(pool)}, agent=f.family)
                self.alert("warning", f"equity: {key} waited for a seat and is demoted ({sticky[key][:200]}): it "
                                      "takes no seat again under this version")
                continue
            if passed.get(f.family) != day:                    # said once a decision day a family, never each minute
                passed[f.family] = day
                self.record("equity.seat", {"action": "passed_over", "family": f.family, "version": row["version"],
                                            "day": day, "rank": position, "rule": rule.rule,
                                            "why": f"its seating did not take ({why[:200]}): the seat goes to the next "
                                                   "waiting program", **_pooled(pool)}, agent=f.family)
        memory.update(idle=flags, passed={k: v for k, v in passed.items() if v == day}, last=last)
        # What the plan SHOWS as idle is the test itself on each holder, in the seating pass too (which never acts on
        # it): a seated program that is idle and keeps its seat because nobody unflagged waits is said so.
        idle = [f for f in (str(r["family"]) for r in holders) if B.seat_idle(facts[f], rule)]
        if held:
            memory["held_seats"] = held
        else:
            memory.pop("held_seats", None)
        self._seat_note(memory, rule, seats + len(held), day, holders, waiting, facts, idle, sticky, out, late=late,
                        refused=refused, pool=pool)

    def _yield(self, row: dict, why: str, taker: str, rule: B.SeatSettings, since: dict, memory: dict, flags: dict,
               day: str, now: float, out: dict, *, pool: str = POOL_ETF) -> bool:
        """ONE IDLE SEAT YIELDS (THE SEAT RULE). Everything in ONE state transaction that first finds the instance
        FLAT again (`_flat`: no lot, no order that may still fill, no intent to execute): the instance is retired
        with the reason "yielded", the program is flagged idle, the plan's memory and the seat mark are written, and
        LAST, still inside the transaction, the band goes back to Candidate through the families reader (never
        sticky). A program that is not flat, or whose row changed, yields nothing and keeps its seat. Nothing is
        sold, planned or cancelled: there is nothing of it to sell.

        TWO DATABASES, ONE OUTCOME. The band lives in the swarm's store and everything else in the live state. The
        swarm's write is the last statement before the commit, so a live write that fails (or a row that changed)
        rolls the whole yield back with the band untouched; and should the commit itself fail after the swarm took
        the band, the band is moved back to the seat's own (`_unyield`) before the error goes on. `row`, `since`,
        `flags` and `memory` are changed only once the transaction has committed: a yield that did not happen leaves
        the sync's own picture as it was. (A process that dies between the two commits leaves a Candidate whose
        instance still runs and is flat: the next decision's band sync, which runs before any program is asked,
        seats it again by rank or retires it with nothing to sell.)"""
        family = str(row["family"])
        key = instance_key(family, int(row["version"]))
        was = str(row.get("band"))
        mark = {"band": "candidate", "day": day}
        flag = {"day": day, "why": "it yielded an idle seat and waits for a free one"}
        last = {"day": day, "action": "yielded", "family": family, "for": taker, "why": why}
        if getattr(self.state, "_depth", 0):
            # The rollback below is the outermost transaction's: inside another the yield could be half written.
            out.setdefault("bands", []).append(f"{family}: no yield inside another transaction")
            return False
        inst, moved = None, False
        try:
            with self.state.transaction():
                if not self._flat(key):
                    out.setdefault("bands", []).append(f"{family}: not flat; no yield")
                    return False
                inst = self._instance(key)
                if inst is not None and inst.retired_at is None:
                    inst.retired_at, inst.why, inst.band = now, f"{YIELDED}: {why}"[:400], "candidate"
                    self._save_instance(inst)
                self._put_plan(pool, {**memory, "idle": {**flags, family: flag}, "yield_day": day, "last": last})
                self.state.put("eq_band_since", {**since, key: mark})
                moved = bool(self.families.confirm_band(row, "candidate", why))
                if not moved:
                    raise _NoYield
        except _NoYield:
            out.setdefault("bands", []).append(f"{family}: the row changed; no yield")
            return False
        except BaseException:
            if moved:
                self._unyield(row, was, key)
            raise
        row["band"] = "candidate"
        since[key] = mark
        flags[family] = flag
        memory.update(idle=flags, yield_day=day, last=last)
        if inst is not None:
            self._drop(inst)
        self.record("equity.band", {"family": family, "version": row["version"], "from": was, "to": "candidate",
                                    "why": why[:300]}, agent=family)
        self.record("equity.instance", {"instance": key, "retired": True, "why": f"{YIELDED}: {why}"[:400],
                                        "seat": YIELDED}, agent=family)
        self.record("equity.seat", {"action": "yielded", "family": family, "version": row["version"], "day": day,
                                    "for": taker, "seeded": bool(row.get("seeded")), "rule": rule.rule, "why": why,
                                    **_pooled(pool)}, agent=family)
        self.alert("warning", f"equity: {key} yields its idle seat to the waiting programs ({taker} is next by rank): it "
                              f"holds no lot, so nothing is sold; it waits flagged idle and returns only into a free "
                              f"seat ({why[:200]})")
        return True

    def _unyield(self, row: Mapping[str, Any], band: str, key: str) -> None:
        """The live state did not take a yield the swarm's store already had (`_yield`: the commit failed): the band
        goes back to the seat's own, so the store and the book say the same again. Never raises; when it cannot be
        moved back the owner is told (the next decision's band sync then settles it: seated again by rank, or
        retired with nothing to sell)."""
        try:
            back = bool(self.families.confirm_band({**row, "band": "candidate"}, band,
                                                   "its yield could not be written: it keeps its seat"))
        except Exception:  # noqa: BLE001 - said below
            back = False
        if not back:
            self.alert("error", f"equity: {key} could not be written as yielded and its band could not be moved back "
                                f"to {band}: the swarm shows it a Candidate while the book still runs it (it is flat). "
                                "The next band sync seats it again by rank or retires it")

    def _seat_note(self, memory: dict, rule: B.SeatSettings, seats: int, day: str, holders: Sequence[Mapping[str, Any]],
                   waiting: Sequence[Mapping[str, Any]], facts: Mapping[str, B.SeatFacts], idle: Sequence[str],
                   sticky: Mapping[str, Any], out: dict, *, late: bool, refused: Mapping[str, Any] | None = None,
                   pool: str = POOL_ETF) -> None:
        """THE PLAN as the sync leaves it, written to `SEAT_KEY` when it changed: who holds each seat (since when, how
        many sessions that count, how many left out because the House refused every open, flat, quiet, idle, seeded),
        who waits and in what order (a rank POSITION, never K), who is flagged idle, the sessions left out of the
        idle clock since the oldest seat (`left_out`: [{day, why}], the newest thirty; `why` is the head of the
        House's words, `_reason_head`), and the last change of hands with its reason. The day's decision also says
        it in one line of the minute's summary (`out["seats"]`)."""
        refused = refused or {}

        def held(row: Mapping[str, Any]) -> dict[str, Any]:
            f = facts[str(row["family"])]
            return {"family": f.family, "version": int(row["version"]), "band": str(row["band"]), "seeded": f.seeded,
                    "since": f.seat_day, "seated_sessions": f.seated_sessions, "quiet_sessions": f.quiet_sessions,
                    "left_out": _counted(f.seat_day, day, refused)[1], "flat": f.flat, "idle": f.family in idle}

        rows = {str(r["family"]): r for r in waiting}
        queue = [{"family": f.family, "version": int(rows[f.family]["version"]), "rank": i, "seeded": f.seeded,
                  "flagged": f.flagged, "ranked": f.k is not None}
                 for i, f in enumerate(B.seat_order(facts[x] for x in rows), 1)]
        plan = {**memory, "rule": rule.rule, "seats": seats, "idle_sessions": int(rule.idle_sessions),
                "holders": sorted((held(r) for r in holders), key=lambda h: (h["since"], h["family"])), "waiting": queue,
                "sticky": sorted(str(k).split("@", 1)[0] for k in sticky), "order": "the book's plan (equity_money.probe.seat)"}
        if any(self._pool_of_key(str(k)) != POOL_ETF for k in sticky):
            # (each pool's plan names its own sticky versions: a panel version's instance is of the panel's kind)
            plan["sticky"] = sorted(str(k).split("@", 1)[0] for k in sticky if self._pool_of_key(str(k)) == pool)
        if pool != POOL_ETF:
            plan["order"] = "the book's plan of the panel seats (equity_money.panel; ranked by equity_money.probe.seat)"
        oldest = min((h["since"] for h in plan["holders"]), default=day)
        plan["left_out"] = [{"day": d, "why": _reason_head(refused[d])} for d in sorted(refused) if oldest < d <= day][-30:]
        was = self._pool_plan(pool)
        if not isinstance(was, Mapping) or {k: v for k, v in was.items() if k not in ("day", SEAT_PANEL)} != \
                {k: v for k, v in plan.items() if k != "day"} or not late:
            self._put_plan(pool, {**plan, "day": day})
        if pool != POOL_ETF:
            if not late:
                seated = "; ".join(f"{h['family']} seated {h['seated_sessions']} sessions" for h in plan["holders"])
                line = ", ".join(f"{w['family']} ({w['rank']})" for w in queue)
                out["panel_seats"] = (f"panel seats ({rule.rule}, {len(plan['holders'])} of {seats}): "
                                      f"{seated or 'nobody seated'}; waiting: {line or 'nobody'}")
            return
        if not late:
            seated = "; ".join(f"{h['family']}{' (seeded)' if h['seeded'] else ''} seated {h['seated_sessions']} sessions"
                               + (f" ({h['left_out']} more left out: the House refused every open)" if h["left_out"] else "")
                               + (" IDLE" if h["idle"] else "") for h in plan["holders"]) or "nobody seated"
            line = ", ".join(f"{w['family']} ({w['rank']}{', idle-flagged' if w['flagged'] else ''})" for w in queue)
            out["seats"] = f"equity seats ({rule.rule}, {len(plan['holders'])} of {seats}): {seated}; waiting: {line or 'nobody'}"

    def _seat_note_first_come(self, rows: Sequence[Mapping[str, Any]], et: Any, since: Mapping[str, Any], day: str, *,
                              pool: str = POOL_ETF) -> None:
        """Under "first-come" the plan says only who holds a seat: the swarm's roster orders the waiting, by pass time
        (`league.swarm.bands.roster(root, lanes=LANES)`), and the book ranks nobody. A pool's plan, of its own rows
        (`_pools`)."""
        holders = sorted(({"family": str(r["family"]), "version": int(r["version"]), "band": str(r["band"]),
                           "seeded": bool(r.get("seeded")),
                           "since": str((since.get(instance_key(r["family"], int(r["version"]))) or {}).get("day") or "")}
                          for r in rows if r.get("band") in LIVE_BANDS), key=lambda h: (h["since"], h["family"]))
        was = self._pool_plan(pool) or {}
        kept = {k: v for k, v in was.items() if k in ("idle", "last", "yield_day")}
        if isinstance(kept.get("idle"), Mapping) and kept["idle"]:
            # A STALE FLAG: a program that yielded under the rule and is seated again here (first come, by pass time)
            # waits no more, and the plan (the report's `idle_flagged`) never names a seated program.
            seated = {h["family"] for h in holders}
            kept["idle"] = {k: v for k, v in kept["idle"].items() if str(k) not in seated}
        plan = {**kept, "rule": B.FIRST_COME,
                "seats": int(et.probe_max_programs) if pool == POOL_ETF else self._panel_seat_count(),
                "holders": holders, "waiting": None, "order": "by pass time: the swarm's roster (first come)"}
        if {k: v for k, v in was.items() if k not in ("day", SEAT_PANEL)} != plan:
            self._put_plan(pool, {**plan, "day": day})

    def _standing(self, inst: Instance) -> tuple[str, str]:
        """The swarm store's own word on an instance whose family has no row in a good read (`families.standing`):
        ("retired" | "demoted", why) is positive evidence it no longer runs; anything else ("live", "unknown", a reader
        that cannot say, an error) is none."""
        read = getattr(self.families, "standing", None)
        if read is None:
            return "unknown", "its families reader cannot say why"
        try:
            code, why = read(inst.family, inst.version)
        except Exception as exc:  # noqa: BLE001 - no evidence
            return "unknown", f"{type(exc).__name__}: {str(exc)[:160]}"
        return str(code), str(why)

    def _drop(self, inst: Instance) -> None:
        self._loaded.pop(inst.id, None)
        self._needs.pop(inst.id, None)
        try:
            self.decider.kind_drop(inst.kind, inst.id)
        except Exception:  # noqa: BLE001 - a dropped program is never asked again either way
            pass

    def _ensure_loaded(self, inst: Instance) -> bool:
        """The instance's program loaded in the decider child (its NEEDS read there: the House never executes it). An
        event instance has no program code to load (release R2): False, and nothing is asked of the decider."""
        if inst.kind == EVENT_KIND:
            return False
        sig = (hashlib.sha256(inst.code.encode()).hexdigest(), dumps(inst.params))
        if self._loaded.get(inst.id) == sig:
            return True
        try:
            answer = self.decider.kind_load(inst.kind, inst.id, {"code": inst.code, "params": inst.params,
                                                                  "name": inst.family, "timeout": DECIDE_TIMEOUT,
                                                                  "max_errors": DECIDE_MAX_ERRORS})
        except Exception as exc:  # noqa: BLE001 - refused or the child failed: this decide fails
            self._needs.pop(inst.id, None)
            inst.why = f"load: {type(exc).__name__}: {str(exc)[:200]}"
            self._save_instance(inst)
            return False
        # `decider.kind_load` answers the child's load less its "ok" and raises for a refused program (above); an
        # answer that says otherwise, or none, is a refusal.
        if not isinstance(answer, Mapping) or answer.get("ok") is False or not isinstance(answer.get("needs"), Mapping):
            self._needs.pop(inst.id, None)
            inst.why = f"load: {str((answer or {}).get('error') if isinstance(answer, Mapping) else 'no answer')[:200]}"
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
        written to `eq_bars` (the rows and each series' sha: A8.11's provenance).

        A READ AFTER A DECISION OF THE SAME DAY (the seating pass reads again when a program seated since needs a bar
        the day's fetch did not hold) writes the day's rows again, so the rows an earlier decision used are first
        compared with it, as the morning audit would have compared them (`_bars_verdict`): a price that differs costs
        the programs that already decided on it what a morning mismatch costs (`_mismatch`)."""
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
        earlier = self.state.get("eq_decision") or {}
        changed = []
        if earlier.get("day") == day and any(i.last_decided_day == day for i in self._instances(alive=True)):
            since = max(str(earlier.get("start") or ""), start)
            again = sorted(set(earlier.get("symbols") or ()) & set(present))
            stored = self._stored_bars(again, since, day)
            for symbol in again:
                fresh = [{_bar_day(r): r for r in keep[name][symbol] if since <= (_bar_day(r) or "")}
                         for name in ("raw", "all")]
                if _bars_verdict(stored.get((symbol, "raw"), {}), stored.get((symbol, "all"), {}), fresh[0], fresh[1],
                                 day) == "mismatch":
                    changed.append(symbol)
        shas = {}
        with self.state.transaction():
            for name in ("raw", "all"):
                for symbol in present:
                    series = [[_bar_day(r), r.get("o"), r.get("h"), r.get("l"), r.get("c"), r.get("v")]
                              for r in keep[name][symbol]]
                    sha = _sha(series)
                    shas.setdefault(symbol, {})[name] = sha
                    for d, o, h, l, c, v in series:
                        # A day fetched again keeps its morning audit while its PRICES are unchanged (the twins judge
                        # a lot on its entry and exit days' audited bars); a changed price is unaudited again. The
                        # volume is not part of it, as it is not part of the audit: the next day's fetch reads a
                        # session's final volume, which is never the 16:20 figure, and would unmark every day.
                        self.state.execute(
                            "INSERT INTO eq_bars(day, symbol, adjustment, o, h, l, c, v, fetched_at, sha, audit) "
                            "VALUES(?,?,?,?,?,?,?,?,?,?,NULL) ON CONFLICT(day, symbol, adjustment) DO UPDATE SET "
                            "o=excluded.o, h=excluded.h, l=excluded.l, c=excluded.c, v=excluded.v, "
                            "fetched_at=excluded.fetched_at, sha=excluded.sha, audit=CASE WHEN eq_bars.o IS excluded.o "
                            "AND eq_bars.h IS excluded.h AND eq_bars.l IS excluded.l AND eq_bars.c IS excluded.c "
                            "THEN eq_bars.audit ELSE NULL END",
                            (d, symbol, name, *(None if x is None else str(x) for x in (o, h, l, c, v)), now, sha))
            self.state.put("eq_decision", {"day": day, "start": start, "end": end, "symbols": sorted(present),
                                           "shas": shas, "audit": None, "fetched_at": now})
        self._bars = {"day": day, "symbols": list(symbols), "present": present, "raw": keep["raw"], "all": keep["all"],
                      "shas": shas, "start": start, "end": end, "fetched_at": now}
        self.record("equity.bars", {"day": day, "symbols": list(symbols), "present": present})
        if changed:
            self._mismatch(day, changed, now, where="read again for a later decide")

    def _decide(self, t: dt.date, live: Sequence[Instance], bars: Mapping[str, Any], now: float, out: dict, *,
                panel: Mapping[str, Any] | None = None) -> None:
        """One "decide" request a kind for every live instance whose bars and program are ready; its intents recorded.
        `panel`: the day's panel bars (`_panel_bars`), for the instances of a kind that is not the book's own.

        ONCE A SESSION: an instance already asked for the day (`last_decided_day`, written in its intents' own
        transaction) is skipped, so a decide that runs again (an error or a restart after one instance's commit and
        before `eq_decide`'s, the seating pass) never records a program's intents twice.

        A FAILED DECIDE (A8.5: `failed_decides_exit` in a row exit the program's lots at the next open, `_house_exits`)
        is counted once a session (kv `eq_failed` {instance: the last day counted}), in two kinds. THE HOUSE COULD NOT
        ASK: no program loaded, no bar, no ctx, the decider or its answer failed, the child holds no runner for it
        (`missing`) or could not build the ctx (`error`): the instance may be asked again for the same close
        (`_seat_step`). THE PROGRAM FAILED: its answer says `failed` (league/equity/child.py: the runner's
        `last_failed`: it raised, ran past its limit or is disqualified), which is exactly what the Gym engine counts
        (league/equity/engine.py `decide`); the session is spent as in the Gym (`last_decided_day` moves, no intent).

        A PANEL INSTANCE (release E4) is asked through its own kind with the job its adapter builds (`_panel_job`), and
        its answer's `failed`, `missing` and `error` are read exactly as the equity kind's. The captain's A17: on a HOLD
        day (its program is not called) a decide the House could not make is an alarm and counts toward no exit
        (`_decide_counts`, `_hold_failed`), and a hold day that was asked does not reset the count either: as in the
        Gym, only CALLED decides are counted, failed or not."""
        day = t.isoformat()
        jobs, failed, meta = [], {}, {}
        asked = [inst for inst in live if inst.last_decided_day != day]
        for inst in asked:
            if not self._ensure_loaded(inst):
                failed[inst.id] = inst.why or "the program did not load"
                continue
            needs = self._needs[inst.id]
            if inst.kind == PANEL_KIND:
                try:
                    job, meta[inst.id] = self._panel_job(inst, t, needs, panel, now)
                except Exception as exc:  # noqa: BLE001 - its bars, its columns or its ctx: the House could not ask
                    failed[inst.id] = f"ctx: {type(exc).__name__}: {str(exc)[:200]}"
                    continue
                jobs.append((inst.kind, job))
                continue
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
            jobs.append((EQUITY_KIND, {"key": inst.id, "inputs": inputs}))
            meta[inst.id] = bars_sha
        results: dict[str, Any] = {}
        for kind in sorted({k for k, _ in jobs}):
            batch = [job for k, job in jobs if k == kind]
            try:
                answer = self.decider.kind(kind, "decide", {"jobs": batch})
                if answer.get("ok"):
                    results.update(answer.get("results") or {})
                else:
                    for job in batch:
                        failed[job["key"]] = f"the decider: {str(answer.get('error') or 'failed')[:200]}"
            except Exception as exc:  # noqa: BLE001
                for job in batch:
                    failed[job["key"]] = f"the decider: {type(exc).__name__}: {str(exc)[:200]}"
        counted = dict(self.state.get("eq_failed", {}) or {})
        decided, spent, fresh = [], {}, []
        for inst in asked:
            result = results.get(inst.id)
            if inst.id not in failed:
                if not isinstance(result, Mapping) or result.get("ok") is False:
                    error = result.get("error") if isinstance(result, Mapping) else ""
                    failed[inst.id] = f"no answer: {str(error or '')[:200]}"
                elif result.get("missing"):
                    self._loaded.pop(inst.id, None)    # the child lost its runner: loaded again before the next decide
                    failed[inst.id] = "the decider holds no loaded program for it"
                elif result.get("error"):
                    failed[inst.id] = f"the decider: {str(result.get('error'))[:200]}"
                elif result.get("failed"):
                    said = result.get("why") or "it raised, ran past its limit or is disqualified"
                    spent[inst.id] = f"its own decide failed: {str(said)[:200]}"
            why = failed.get(inst.id) or spent.get(inst.id)
            other = inst.kind == PANEL_KIND
            if why is not None:
                counts = self._decide_counts(inst, t)
                with self.state.transaction():
                    if counts and counted.get(inst.id) != day:
                        inst.failed_decides += 1
                        counted[inst.id] = day
                        fresh.append(inst.id)
                        self.state.put("eq_failed", counted)
                    if inst.id in spent:
                        inst.last_decided_day = day
                    inst.why = f"decide {day}: {why}"[:400]
                    self._save_instance(inst)
                    if other:
                        self._panel_failed(inst, t, why, result if inst.id in spent else None, meta.get(inst.id), now,
                                           counts=counts)
                failed[inst.id] = why
                continue
            late = None
            with self.state.transaction():
                if other:
                    n, late = self._panel_record(inst, t, result, meta[inst.id], now)
                else:
                    n = self._record_intents(inst, t, list(result.get("intents") or []), result.get("ctx_sha"),
                                             meta.get(inst.id))
                if late is not None:
                    # B9: a called rebalance recorded after the open window's entry cut-off planned nothing: one failed
                    # decide, and the session is spent.
                    if counted.get(inst.id) != day:
                        inst.failed_decides += 1
                        counted[inst.id] = day
                        fresh.append(inst.id)
                        self.state.put("eq_failed", counted)
                    inst.last_decided_day, inst.why = day, f"decide {day}: {late}"[:400]
                elif other and not meta[inst.id]["called"]:
                    inst.last_decided_day, inst.why = day, ""      # a hold day neither counts nor resets (A17)
                else:
                    inst.failed_decides, inst.last_decided_day, inst.why = 0, day, ""
                self._save_instance(inst)
            if late is not None:
                failed[inst.id] = late
                continue
            decided.append(f"{inst.id}: {n}")
        out["decided"] = decided
        if failed:
            out["decide_failed"] = dict(failed)
        if fresh:
            self.alert("warning", f"equity: the decide of {day} failed for {', '.join(sorted(fresh))}")
        if decided or fresh:
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
                # Session t's close marks a lot held at it (a decide that runs late, after the next open, never
                # marks a lot bought since with a price from before it was bought).
                if close is not None and close > 0 and lot.opened_day <= day:
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

    def _record_intents(self, inst: Instance, t: dt.date, intents: Sequence[Any], ctx_sha: Any, bars_sha: Any, *,
                        symbols: Sequence[str] | None = None, cap: int | None = None) -> int:
        """The program's intents as `eq_intents` rows for the next session (each checked here again: a malformed one
        is recorded refused, the program reads why in its next ctx's rejects). `symbols` and `cap` (B5, release E4): what
        a panel instance may buy that day (its columns' candidates, where an equity program's are its NEEDS symbols) and
        its adapter's cap on a session's intents."""
        day, exec_day, now = t.isoformat(), S.next_session(t).isoformat(), self.clock()
        needs = [str(s).upper() for s in (self._needs.get(inst.id) or {}).get("symbols") or []]
        if symbols is not None:
            needs = [str(s).upper() for s in symbols]
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

        for raw in list(intents)[:config.MAX_INTENTS if cap is None else int(cap)]:
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

    def _house_exits(self, t: dt.date, now: float, *, only: Collection[str] | None = None) -> int:
        """THE HOUSE'S EXIT RULES (A8.5, identical in the Gym engine), planned at the decision of session t for the
        next open: a retired or demoted program's lots; a program with `failed_decides_exit` failed decides in a row;
        a lot held its program's `max_hold_sessions` by the next open. `only`: the instances whose lots are judged
        (None: every lot; the seating pass hands the ones whose failed decide it has just counted).

        A rule that is due goes AT THE OPEN whatever its program planned for the close: the Gym sells a lot the House
        exits at the next open and then rejects the program's own close sell of it (league/equity/engine.py `_exits`),
        so a program's planned `at: close` sell of that lot is refused here (the program reads why in its next ctx's
        rejects) and the House's exit takes its place. A program's own sell at the open goes first in the Gym too, and
        an exit of the House's already planned (carried, flatten) stands."""
        day, nxt = t.isoformat(), S.next_session(t).isoformat()
        _, default_hold, cap, failed_exit = self._holds()
        n = 0
        told: list[str] = []
        with self.state.transaction():
            for lot in self._lots():
                if only is not None and lot.instance not in only:
                    continue
                if lot.lane == EVENT_LANE:
                    continue        # (release R2: an event lot exits at its scheduled auction, `_event_exits`)
                pending = [Intent.of(r) for r in self.state.rows(
                    "SELECT * FROM eq_intents WHERE lid=? AND kind IN ('sell', 'house_exit') AND status IN "
                    "('planned', 'sent') ORDER BY iid", (int(lot.lid),))]
                yields = [i for i in pending if i.kind == "sell" and i.status == "planned" and i.at == "close"]
                if len(yields) != len(pending):
                    continue
                inst = self._instance(lot.instance)
                reason, why = None, ""
                if inst is None or inst.retired_at is not None or inst.band not in LIVE_BANDS:
                    code = "demoted" if inst is not None and str(inst.why).startswith("demoted") else "retired"
                    reason, why = code, f"its program is {code}: {inst.why if inst else 'unknown to the book'}"
                    if inst is not None and str(inst.why).startswith(YIELDED):
                        # THE SEAT RULE NEVER ENDS IN A SALE (A24; A30 (3)): a program yields only while flat, and
                        # `_flat` holds its seat for as long as an order of its own could still book a lot. A lot of
                        # a program that yielded is therefore a fault of the book's, never the rule's doing: the lot
                        # leaves by the House's own rule for a program that no longer runs (no stuck lot, A8.5), and
                        # it is never silent.
                        told.append(f"lot {lot.lid} ({lot.symbol}) of {lot.instance}")
                elif inst.failed_decides >= failed_exit:
                    reason, why = "house", f"{inst.failed_decides} failed decides in a row"
                else:
                    hold = max(1, min(cap, int(inst.max_hold or default_hold)))
                    held = S.sessions_between(lot.opened_day, day)
                    if config.max_hold_due(held, hold):
                        reason, why = "max_hold", f"held {held + 1} sessions by the next open (its maximum {hold})"
                if reason:
                    for intent in yields:
                        self._finish(intent, "refused", f"lot {lot.lid} leaves at the open by the House's rule "
                                                        f"({reason}: {why})"[:300])
                    self._plan_exit(lot, exec_day=nxt, at="open", reason=reason, why=why, decided_day=day)
                    n += 1
        if n:
            self.record("equity.house_exits", {"day": day, "lots": n})
        if told:
            self.record("equity.alert", {"what": "a lot of a program that had yielded its seat", "lots": told, "day": day})
            self.alert("error", f"equity: {'; '.join(told)}: the program had YIELDED its idle seat and a lot was booked to "
                                "it afterwards. The seat rule must never end in a sale: this is a fault of the book's "
                                "order path. The lot exits at the next open by the House's rule for a program that no "
                                "longer runs; tell the captain")
        return n

    def _decide_failed(self, t: dt.date, now: float, why: str) -> None:
        day = t.isoformat()
        counted = dict(self.state.get("eq_failed", {}) or {})
        for inst in self._instances(alive=True):
            if inst.live and inst.last_decided_day != day and counted.get(inst.id) != day \
                    and self._decide_counts(inst, t):
                inst.failed_decides += 1
                counted[inst.id] = day
                inst.why = f"decide {day}: {why}"[:400]
                self._save_instance(inst)
        self.state.put("eq_failed", counted)
        self._house_exits(t, now)
        self.state.put("eq_decide", {"day": day, "status": "failed", "at": now, "why": why})
        self.alert("warning", f"equity: the decide of {day} failed: {why}")

    # ------------------------------------------------------------------ the panel kind (release E4, package H)
    def _adapter(self, kind: str) -> Any:
        """The parent-side adapter of a decider kind that is not the book's own (`kinds.BOOKS`: "panel" ->
        league/xs/book.py), imported once and its table made beside the book's (`adapter.SCHEMA`: `eq_rebalances`).
        None for a kind that has none, or whose adapter cannot be imported: its instances then fail their decides (the
        House could not ask) and nothing else of the book is touched."""
        if kind not in self._adapters:
            adapter = None
            try:
                adapter = K.book_for(kind)
                if adapter is not None:
                    with self.state.lock:
                        for statement in _SQL_COMMENT.sub("", adapter.SCHEMA).split(";"):
                            if statement.strip():
                                self.state.execute(statement)
                        self._add_columns(getattr(adapter, "SCHEMA_COLUMNS", None) or {})
            except Exception as exc:  # noqa: BLE001 - that kind stays off; the book itself goes on
                adapter = None
                self._error(f"adapter {kind}", exc, {})
            self._adapters[kind] = adapter
        return self._adapters[kind]

    def _add_columns(self, columns: Mapping[str, Mapping[str, str]]) -> None:
        """RELEASE 1019f: an adapter's columns added to its tables after their first release (`adapter.SCHEMA_COLUMNS`:
        {table: {column: its ALTER statement}}; league/events/book.py's `eq_event_intents.target_usd` and `binding`), each
        where the table lacks it (PRAGMA table_info, read afresh), as `eq_orders.tif` is: a state from before them gains
        them in place, every older row reading NULL; another process's first open adding one between the look and the
        ALTER is read as done. Anything else is raised (the adapter is then off, `_adapter`)."""
        for table, wanted in columns.items():
            for column, ddl in wanted.items():
                have = {str(r["name"]) for r in self.state.rows(f"PRAGMA table_info({table})")}
                if column in have:
                    continue
                try:
                    self.state.execute(ddl)
                except sqlite3.OperationalError as exc:
                    have = {str(r["name"]) for r in self.state.rows(f"PRAGMA table_info({table})")}
                    if "duplicate column name" not in str(exc).lower() or column not in have:
                        raise

    def _rebalances(self, instance: str) -> list[dict]:
        return self.state.rows("SELECT * FROM eq_rebalances WHERE instance=? ORDER BY decided_day, rid", (instance,))

    def _decide_counts(self, inst: Instance, t: dt.date) -> bool:
        """THE CAPTAIN'S A17: whether a decide of session t that failed counts toward A8.5's exit for this instance.
        Always for the book's own kind. For a panel program only a CALLED decide counts (a failed decide on a rebalance
        day); a HOLD day the House could not ask is an alarm (`_hold_failed`) and counts toward no exit. A program
        whose schedule cannot be read (it did not load) counts, as before."""
        if inst.kind == EQUITY_KIND:
            return True
        adapter = self._adapter(inst.kind)
        if adapter is None or getattr(adapter, "HOLD_DAY_FAILS_EXIT", True):
            return True
        if inst.id not in self._needs:
            self._ensure_loaded(inst)
        needs = self._needs.get(inst.id)
        if not needs:
            return True
        try:
            return bool(adapter.called(t, needs))
        except Exception:  # noqa: BLE001 - a schedule that cannot be read is read as a called day
            return True

    def _hold_failed(self, inst: Instance, day: str, why: str) -> None:
        """A hold day the House could not ask (A17): said once a day, critical on the second session in a row, and kept
        (kv `eq_hold_failed` {instance: {day, run}}) so the seating pass asks again on its own clock. Its lots stay:
        the max-hold exits still run, and nothing else is sold."""
        notes = dict(self.state.get("eq_hold_failed", {}) or {})
        last = notes.get(inst.id) or {}
        if last.get("day") == day:
            return
        try:
            row = last.get("day") == S.previous_session(day).isoformat()
        except ValueError:
            row = False
        run = int(last.get("run") or 0) + 1 if row else 1
        notes[inst.id] = {"day": day, "run": run}
        self.state.put("eq_hold_failed", notes)
        self.alert("error" if run >= 2 else "warning",
                   f"equity: {inst.id} could not be asked on the hold day {day} ({why[:200]}): its lots stay as they are "
                   f"and no failed decide is counted (A17){'; the second session in a row' if run >= 2 else ''}")

    def _panel_held(self, inst: Instance, adapter: Any, day: str) -> dict[str, str]:
        """{symbol: the day its lot was opened} of the instance's lots open now, or closed since its last called
        decision: the names that keep a column whatever the index says of them today."""
        last = adapter.last_called(self._rebalances(inst.id), before=day)
        return {lot.symbol: lot.opened_day for lot in self._lots(instance=inst.id, open_only=False)
                if lot.status != LOT_CLOSED or (lot.exit_day or "") > last}

    def _panel_renamed(self, inst: Instance) -> dict[str, str]:
        """{a lot's symbol now: the symbol it was bought under} for the instance's lots a ticker change was booked on
        (`_book_activity`'s rename: `info.renamed_from`): the adapter finds such a lot's column by the old ticker
        while the membership job has not read the new one."""
        out: dict[str, str] = {}
        for lot in self._lots(instance=inst.id, open_only=False):
            old = (lot.info or {}).get("renamed_from") if isinstance(lot.info, Mapping) else None
            if old and str(old).upper() != str(lot.symbol).upper():
                out[lot.symbol] = str(old)
        return out

    def _panel_bars(self, now: float, t: dt.date, mt: S.Moments, mn: S.Moments | None, asked: Sequence[Instance],
                    out: dict, *, fetch: bool = True) -> dict[str, Any] | None:
        """THE PANEL'S BARS OF SESSION t (B3, B11, B13), for a decide of `asked` (None when it asks no panel instance:
        nothing is read). Each asked instance's columns (`adapter.columns`: the day's members and the names its lots
        hold), then ONE chunked fetch for the union of every panel instance's columns seen that day, a few chunks a
        minute (`adapter.fetch`); the day's kept file is used instead when it holds them (a restart, a program seated
        since). The answer: {adapter, cols {instance: Columns}, union, fetched, sha, failed {instance: why}} and
        - `ready`: the fetch may be decided on (`adapter.complete`); it is KEPT then (`adapter.keep`: the bytes a
          decision read; the morning re-read and the nightly I6 compare it). With `fetch` False (the seating pass from
          the next session's pre-open on) NOTHING IS ASKED OF THE VENUE: the day's kept file or a wait;
        - `wait`: it is still being read (the fetch RETURNED unfinished), or, inside `BARS_GRACE_S` of `decide_at`, a
          bar is missing or the fetch RAISED: read again each minute, the panel instances are not asked this pass;
        - else `why`: past the grace the instances fail (the House could not ask) and the seating pass asks again every
          `SEAT_RETRY_S` until the next pre-open. FROM THE LAST ASK BEFORE IT (`SEAT_RETRY_S` before the pre-open) a
          held name may be among the adapter's few missing names: it is then read as the Gym reads a store with no bar.
          A FETCH THAT RAISES IS NEVER "STILL BEING READ": `adapter.fetch` fills its `progress` before its first call,
          so a route that answers 5xx, or a chunk it refuses, once read as a fetch in progress for ever: no failed
          decide was counted, nothing was said, and the fetch was tried every minute through the next session. Past
          the grace it is `why` like a fetch that is not whole: one failed decide on a called day (A8.5), the hold
          day's alarm on a hold day (A17), asked again every `SEAT_RETRY_S` and not after the pre-open."""
        if not asked:
            return None
        day = t.isoformat()
        if self._panel.get("day") != day:
            self._panel = {"day": day, "cols": {}, "failed": {}, "progress": {}, "union": None, "fetched": None,
                           "ok": False, "missing": [], "kept": False, "sha": None, "told": set()}
        state = self._panel
        state.update(wait=False, ready=False, why=None)
        adapter = state["adapter"] = self._adapter(asked[0].kind)
        if adapter is None or self.root is None:
            state["why"] = ("the panel adapter cannot be imported" if adapter is None
                            else "the book has no state root: the panel's universe cannot be read")
            return state
        root = self.root / STORE_DIR
        for inst in asked:
            if inst.id in state["cols"] or not self._ensure_loaded(inst):
                continue
            try:
                state["cols"][inst.id] = adapter.columns(root, inst.id, t, held=self._panel_held(inst, adapter, day),
                                                         renamed=self._panel_renamed(inst))
                state["failed"].pop(inst.id, None)
            except Exception as exc:  # noqa: BLE001 - that instance's decide fails; the others go on
                state["failed"][inst.id] = f"columns: {type(exc).__name__}: {str(exc)[:200]}"
        if not state["cols"]:
            state["why"] = "no panel instance's columns could be built"
            return state
        union = adapter.union(list(state["cols"].values()))
        if state["union"] is None or state["union"].symbols != union.symbols:
            state.update(union=union, fetched=None, ok=False, kept=False, sha=None, progress={})
            kept = adapter.kept(root, t)
            if kept is not None and set(union.symbols) <= set(kept[0]):
                state.update(fetched=adapter.view(kept[1], kept[0], union), kept=True)
        state["union"] = union
        held = [lot for lot in self._lots() if lot.instance in state["cols"]]
        last_ask = mn is not None and now >= mn.preopen - SEAT_RETRY_S
        if state["fetched"] is not None:
            state["ok"], state["missing"] = adapter.complete(state["fetched"], union, held, last_ask=last_ask)
        reading, raised = False, None
        if not state["ok"] and not fetch:
            state["wait"] = True
            out["panel_bars"] = (f"no whole kept fetch of {day}, and the panel's bars are not asked for inside a "
                                 "session: its instances are asked at the next close")
            return state
        if not state["ok"]:
            try:
                got = adapter.fetch(self.market, union, t, progress=state["progress"], now=self.clock)
            except Exception as exc:  # noqa: BLE001 - read again from the chunk it stopped at (the docstring)
                got = None
                raised = f"{type(exc).__name__}: {str(exc)[:160]}"
                self._error("panel bars", exc, out)
            if got is None:
                reading = raised is None      # it RETURNED unfinished: a fetch that raised is not being read
            else:
                state.update(fetched=got, kept=False, sha=None, progress={})
                state["ok"], state["missing"] = adapter.complete(got, union, held, last_ask=last_ask)
        if not state["ok"]:
            missing = list(state["missing"])
            if reading or now < mt.decide_at + BARS_GRACE_S:
                state["wait"] = True
                out["panel_bars"] = ("reading the panel's bars" if reading or state["fetched"] is None else
                                     f"waiting for {len(missing)} of the panel's bars")
            elif raised is not None:
                state["why"] = f"the panel's bars of {day} could not be read: {raised}"
            else:
                state["why"] = (f"the panel's bars of {day} are not whole: {len(missing)} missing"
                                f" ({', '.join(missing[:5])}{', ...' if len(missing) > 5 else ''})")
            return state
        fetched, missing = state["fetched"], list(state["missing"])
        late = bool(last_ask and missing)
        fetched = adapter.Fetched(fetched.days, fetched.raw, fetched.all,
                                  {**dict(fetched.meta), "missing": len(missing), "late": late})
        state["fetched"] = fetched
        if not state["kept"]:
            try:
                adapter.keep(root, t, fetched, union.symbols)
                state["kept"] = True
            except Exception as exc:  # noqa: BLE001 - a decision whose bars cannot be kept is not made
                state["why"] = f"the panel's bars of {day} could not be kept: {type(exc).__name__}: {str(exc)[:160]}"
                return state
            state["sha"] = None
        if state["sha"] is None:
            state["sha"] = adapter.bars_sha(fetched, union)
        state["ready"] = True
        if int((fetched.meta or {}).get("dropped") or 0) and "dropped" not in state["told"]:
            state["told"].add("dropped")
            self.alert("warning", f"equity: the panel's fetch of {day} dropped {int(fetched.meta['dropped'])} rows the "
                                  "venue served on a day that is no session or with a field that is no number (each "
                                  "is read as no bar, as the nightly job reads it)")
        if late and "late" not in state["told"]:
            state["told"].add("late")
            self.alert("warning", f"equity: the panel's bars of {day} were decided on late and incomplete at the last ask: "
                                  f"{len(missing)} names had no bar and are read as not eligible")
        if now >= mt.decide_at + PANEL_LATE_S and "slow" not in state["told"]:
            state["told"].add("slow")
            if any(i.last_decided_day != day for i in asked):
                self.alert("warning", f"equity: the panel's bars of {day} were ready more than "
                                      f"{int(PANEL_LATE_S // 60)} minutes after the decide's moment")
        return state

    def _panel_budget(self, inst: Instance, day: str, lots: Sequence[Lot]) -> tuple[Decimal, Decimal]:
        """A PANEL PROGRAM'S BUDGET FOR ONE DECISION, and its whole sleeve beside it: (budget, sleeve). THE WHOLE BASKET
        IS SCALED TO THE ROOM (the review's spec-2). A basket's lots are `weight x budget` a name, and E1's sizing
        holds the account's walls a name at a time, at the send: where a full basket does not fit the shared loss
        window it buys the first names whole and cuts the last, every rebalance, while its Gym twin buys them all. (It
        was found at A20's design, a sleeve of 0.50 x E: a full basket of stocks was 0.40 x 0.50 x E of open risk,
        above the $400 window from E = $2,000, so at $2,229 a five-name target bought four names of $222.90 and the
        fifth cut to $108.40.) So the budget the decision is handed is the smaller of
        - the sleeve (`sleeve_share` x E), and
        - what the account's walls leave a FULL basket now: the program's own lots at their marks plus the shared
          loss budget's room over the class's open-risk weight, and plus the invested cap's room.
        Every name of the target then scales alike, each its weight of the budget its twin's weights are read
        against. AT THE DESIGN IN FORCE since release E5-S (six seats, 0.25 x E; `set_design` may move it) a basket
        alone is its whole sleeve, five lots of $111.45 at $2,229 and $222.90 of open risk, and it is scaled once
        the lane's other lots and the window's losses leave less than that (five of $60.68 beside five invested
        one-ETF programs); at A20's it was five of $200.00 with the window untouched. NOTHING IS LOOSENED: the
        send's own sizing still holds every wall a name at a time (a budget that has moved since cuts the last name,
        as before), held lots are never resized and a budget that fell sells nothing (KEEP), and a figure that cannot
        be read leaves the sleeve as the budget. WHAT IT DOES NOT DO: it sizes a basket bought from flat or rotated
        whole. Once the room is under what the basket holds, a PARTIAL rotation's new name is planned at its weight
        of the smaller budget and then refused for budget at the send (one sale frees less room than is short): the
        program holds a name fewer than its twin (`TheWholeBasketIsScaledToTheRoom`'s send tests pin it as built, on
        a table of their own at A20's design). THE COST, stated in docs/operations.md: the window is one and
        shared, first come, and a basket weighs four one-ETF lots of it. A panel sleeve of its own is a money row
        and the owner's decision, open."""
        et = self._et()
        E = self.sizing_equity() or ZERO
        sleeve = self._sleeve_share(inst) * E if et is not None else ZERO
        if et is None or sleeve <= 0:
            return sleeve, sleeve
        own = sum((lot.value for lot in lots), ZERO)
        try:
            weight = _weight(et.open_risk_weight, "stock")     # (a panel lot's class; an unread weight is a whole dollar)
            # (a room below zero shrinks it too: what a FULL rotation of the basket could buy back)
            by_budget = own + self._budget_room(day) / weight
            by_invested = own + (Decimal(str(et.invested_share)) * E - invested(self.state.rows)
                                 - self._options_open_loss(day))
        except Exception:  # noqa: BLE001 - unread: the sleeve, and the send's sizing holds the walls as ever
            return sleeve, sleeve
        return max(ZERO, min(sleeve, by_budget, by_invested)).quantize(CENT, rounding=ROUND_DOWN), sleeve

    def _panel_job(self, inst: Instance, t: dt.date, needs: Mapping[str, Any], panel: Mapping[str, Any] | None,
                   now: float) -> tuple[dict[str, Any], dict[str, Any]]:
        """A panel instance's decide job (B4) and what its record needs: {"key", "inputs", "called", "standing"}. EVERY
        OPEN LOT OF THE INSTANCE IS MARKED FIRST at session t's raw close (B15: on a day only panel programs decide
        nothing else would mark it, and the sleeve's free cash, the invested cap and the loss budget's open risk read
        the mark; as the book's own, a late decide never marks a lot bought since the close). `called`: its program is
        asked today (D9); on every other close no program code runs and `standing` carries the last planned target's
        names still to buy (absent: a hold). Raises when the panel's bars are not ready or its columns are not built."""
        if panel is None or not panel.get("ready"):
            raise RuntimeError((panel or {}).get("why") or "the panel's bars are not ready")
        adapter, cols = panel["adapter"], panel["cols"].get(inst.id)
        if cols is None:
            raise RuntimeError(panel["failed"].get(inst.id) or "its columns were not built")
        day = t.isoformat()
        fetched = adapter.view(panel["fetched"], panel["union"].symbols, cols)
        clock = self.clock()
        with self.state.transaction():
            lots = {lot.lid: lot for lot in self._lots(instance=inst.id)}
            for lid, close in adapter.marks(fetched, cols, list(lots.values()), t).items():
                lots[lid].mark, lots[lid].marked_at = close, clock
                self._save_lot(lots[lid])
        lots = self._lots(instance=inst.id)
        every = self._lots(instance=inst.id, open_only=False)
        rows = self._rebalances(inst.id)
        last = adapter.last_called(rows, before=day)
        closed = [lot for lot in every if lot.status == LOT_CLOSED and (lot.exit_day or "") > last]
        rejects: list[str] = []
        if last:
            for r in rows:
                if last <= str(r["decided_day"]) < day:
                    rejects.extend(str(why) for _, why in (loads(r["skipped"], []) or []) if why)
            rejects.extend(r["why"] for r in self.state.rows(
                "SELECT why FROM eq_intents WHERE instance=? AND status IN ('refused', 'missed') AND decided_day>=? "
                "AND decided_day<? ORDER BY iid", (inst.id, last, day)) if r["why"])
        budget, sleeve = self._panel_budget(inst, day, lots)
        own_value = sum((lot.value for lot in lots), ZERO)
        # THE CONSTANT-WEIGHT BOOK (the pre-registration's C3, C8; the Gym engine's own): the sleeve's free room is its
        # budget less the open lots' ENTRY notionals, and its equity that room plus the lots at their marks.
        cash = adapter.sleeve_room(budget, lots)
        is_called = bool(adapter.called(t, needs))
        standing = None
        if not is_called:
            pending = [r["symbol"] for r in self.state.rows(
                "SELECT symbol FROM eq_intents WHERE instance=? AND kind='buy' AND status IN ('planned', 'sent')",
                (inst.id,)) if r["symbol"]]
            standing = adapter.standing(rows, cols, every, t, pending=pending)
        params = needs.get("_params") if needs.get("_params") is not None else inst.params
        job = {"key": inst.id, "called": is_called,
               "inputs": adapter.inputs(cols, fetched, day=t, needs=needs, lots=lots, closed=closed,
                                        rejects=rejects[:20], cash=cash, equity=cash + own_value, budget=budget,
                                        params=params)}
        if standing is not None:
            job["standing"] = standing
        info = {"cols": cols, "called": is_called, "standing": standing, "equity": cash + own_value, "budget": budget,
                "sleeve": sleeve, "bars_sha": adapter.bars_sha(fetched, cols),
                "fetch": {**dict(fetched.meta), "sha": panel.get("sha")}, "lots": {lot.lid: lot for lot in lots}}
        return job, info

    def _panel_ineligible(self, inst: Instance, t: dt.date, answer: Mapping[str, Any] | None, adapter: Any) -> int:
        """B6, B14: the open lots of the instance its child's answer names `ineligible` (their name is not in the
        eligible set at session t's close: it left the index, lost its bar, or cannot be traded; `league.xs.ctx
        .ineligible`, read at EVERY close, called or not, exactly as the Gym's engine reads it) exit at the next open,
        tagged `adapter.INELIGIBLE`. `_house_exits`' own rule applies as it stands: an exit of the House at the open
        displaces the program's planned close sell of the lot, and the program's own open sell or an exit already
        planned stands."""
        day, nxt = t.isoformat(), S.next_session(t).isoformat()
        n = 0
        for lid in (answer or {}).get("ineligible") or []:
            try:
                lot = self._lot(int(lid))
            except (TypeError, ValueError):
                continue
            if lot is None or lot.instance != inst.id or lot.status == LOT_CLOSED:
                continue
            pending = [Intent.of(r) for r in self.state.rows(
                "SELECT * FROM eq_intents WHERE lid=? AND kind IN ('sell', 'house_exit') AND status IN "
                "('planned', 'sent') ORDER BY iid", (int(lot.lid),))]
            yields = [i for i in pending if i.kind == "sell" and i.status == "planned" and i.at == "close"]
            if len(yields) != len(pending):
                continue
            why = f"its name is not eligible at the close of {day} (it left the index, lost its bar or cannot be traded)"
            for intent in yields:
                self._finish(intent, "refused", f"lot {lot.lid} leaves at the open by the House's rule "
                                                f"({adapter.INELIGIBLE}: {why})"[:300])
            self._plan_exit(lot, exec_day=nxt, at="open", reason=adapter.INELIGIBLE, why=why, decided_day=day)
            n += 1
        return n

    def _panel_record(self, inst: Instance, t: dt.date, answer: Mapping[str, Any], info: Mapping[str, Any],
                      now: float) -> tuple[int, str | None]:
        """A panel instance's answer recorded (B5): its child's orders as intents (`adapter.intents`, at most
        `adapter.MAX_INTENTS`, a buy only of one of the day's candidates), the lots it names ineligible exited at the
        next open (`_panel_ineligible`), and ONE `eq_rebalances` row for the session, its `equity.rebalance` event
        counts only. Returns (the intents recorded, why it is a failed decide or None).

        B9, A REBALANCE RECORDED LATE: when session t's decide is recorded after `entry_until` (09:45 ET) of its exec
        day (the House was down overnight), a target for the OPEN, called or standing, plans no sell and no buy: its
        sells would go all day and every buy would be missed at a cut-off already past, leaving the sleeve in cash for
        a week or a month. The row's status is "late", the owner is told, it is one failed decide when it was a called
        day, and the standing target is the one before (a late row never stands). A target for the CLOSE is planned as
        usual, and the House's own exits are planned as ever."""
        adapter = self._adapter(inst.kind)
        cols, lots = info["cols"], list(info["lots"].values())
        day, nxt = t.isoformat(), S.next_session(t)
        called, standing = bool(info["called"]), info.get("standing")
        hold = bool(answer.get("hold")) or not isinstance(answer.get("target"), Mapping)
        at = str(answer.get("at") or (standing or {}).get("at") or "open")
        orders = adapter.intents(answer, cols, lots)
        skipped = adapter.skipped(answer, cols, lots)
        status = "planned" if called and not hold else "hold"
        target = answer.get("target") if called and not hold else (None if called else (standing or {}).get("target"))
        mn = S.moments(nxt, self._offsets())
        why, failed = None, None
        if mn is not None and self.clock() >= mn.entry_until and at == "open" and (status == "planned" or orders):
            status = "late"
            why = (f"recorded after the open window's entry cut-off of {nxt.isoformat()}: a target for the open plans "
                   "nothing, and the standing target is the one before")
            failed = why if called else None
            skipped = skipped + [["", "the rebalance was recorded late: nothing planned at the open"]] * bool(orders)
            orders = []
            self.alert("warning", f"equity: {inst.id}'s {'rebalance' if called else 'standing target'} of {day} was {why}")
        n = 0
        if orders:
            ref = len(cols.symbols) - len(cols.ids)
            candidates = [s for s in cols.symbols[ref:] if s not in cols.extra]
            n = self._record_intents(inst, t, orders, answer.get("ctx_sha"), info.get("bars_sha"), symbols=candidates,
                                     cap=adapter.MAX_INTENTS)
        n += self._panel_ineligible(inst, t, answer, adapter)
        row = adapter.rebalance_row(
            instance=inst.id, family=inst.family, version=inst.version, decided_day=day, exec_day=nxt.isoformat(), at=at,
            called=called, targets=adapter.target_pairs(target, cols), standing=bool(not called and orders),
            intents=orders, skipped=skipped, equity=info.get("equity"), budget=info.get("budget"), cols=cols,
            ctx_sha=answer.get("ctx_sha"), bars_sha=info.get("bars_sha"), fetch=info.get("fetch") or {}, status=status,
            why=why, now=now)
        self.state.upsert("eq_rebalances", row, "instance, decided_day")
        # (`scaled`: the decision's budget was under the sleeve, the whole basket scaled to the account's room:
        # `_panel_budget`. A verdict, never a dollar figure; absent when the budget is the sleeve.)
        scaled = (A.dec(info.get("budget")) or ZERO) < (A.dec(info.get("sleeve")) or ZERO)
        self.record("equity.rebalance", {**adapter.event(row), **({"scaled": True} if scaled else {})}, agent=inst.family)
        notes = dict(self.state.get("eq_hold_failed", {}) or {})
        if notes.pop(inst.id, None) is not None:
            self.state.put("eq_hold_failed", notes)
        planned = row["n_sells"] + row["n_buys"]
        if row["n_skipped"] and row["n_skipped"] > SKIPPED_WARN_SHARE * (planned + row["n_skipped"]) and status != "late":
            self.alert("warning", f"equity: {inst.id}'s decision of {day} skipped {row['n_skipped']} of "
                                  f"{planned + row['n_skipped']} orders")
        if row["standing"]:
            run = 0
            for r in reversed(self._rebalances(inst.id)):
                if not int(r["standing"] or 0):
                    break
                run += 1
            if run == STANDING_WARN_SESSIONS:
                self.alert("warning", f"equity: {inst.id}'s standing target has had a buy still to make for {run} "
                                      "sessions in a row")
        return n, failed

    def _panel_failed(self, inst: Instance, t: dt.date, why: str, answer: Mapping[str, Any] | None,
                      info: Mapping[str, Any] | None, now: float, *, counts: bool) -> None:
        """A panel decide that failed, for the record: its `eq_rebalances` row ("failed"; a later ask of the same close
        that succeeds writes over it), the lots its child still named ineligible exited (a program whose own decide
        failed was asked: the House's exits do not wait on it), the hold day's alarm when it counts toward no exit
        (A17), and the critical word when its failed called decides reach the exit rule."""
        adapter = self._adapter(inst.kind)
        if adapter is None:
            return
        day = t.isoformat()
        info = info or {}
        try:
            if answer is not None:
                self._panel_ineligible(inst, t, answer, adapter)
            row = adapter.rebalance_row(
                instance=inst.id, family=inst.family, version=inst.version, decided_day=day,
                exec_day=S.next_session(t).isoformat(), at="open", called=bool(info.get("called", counts)), targets=[],
                standing=False, intents=[], skipped=[], equity=info.get("equity"), budget=info.get("budget"),
                cols=info.get("cols"), ctx_sha=(answer or {}).get("ctx_sha"), bars_sha=info.get("bars_sha"),
                fetch=info.get("fetch") or {}, status="failed", why=why, now=now)
            self.state.upsert("eq_rebalances", row, "instance, decided_day")
        except Exception as exc:  # noqa: BLE001 - the record's trouble never undoes the count
            self._error(f"panel failed {inst.id}", exc, {})
        if not counts:
            self._hold_failed(inst, day, why)
        elif inst.failed_decides >= self._holds()[3]:
            self.alert("error", f"equity: {inst.id} has failed {inst.failed_decides} called decides in a row: its lots "
                                "exit at the next open")

    def _panel_audit(self, now: float, m: S.Moments, out: dict) -> None:
        """B11, THE BARS A PANEL DECISION READ ARE READ AGAIN before the next open, beside the book's own audit: for
        the last session's `eq_rebalances` rows that read bars and have no verdict, the day's kept symbols are fetched
        again (ONE chunked fetch for every instance, a few chunks a minute) and compared with the kept file
        (`adapter.same`, by `_bars_verdict`: the book's own rule and tolerance). No price differs: "ok" (a volume that
        went on counting and a bar served late are notes). A PRICE DIFFERS in a symbol among a row's columns:
        "mismatch", and that decision pays what the book's own pays and is void whole (`_panel_mismatch`: its buys
        AND its program's sells). Not read by the pre-open, no
        kept file, or a kept file that is not the one a row read: "unread", a warning. A decision recorded after the
        audit's moment (a late ask) has no morning re-read: its `audit` stays NULL, and the report counts it."""
        if not _has_table(self.state.rows, "eq_rebalances"):
            return
        t = S.previous_session(m.day)
        day = t.isoformat()
        rows = self.state.rows("SELECT * FROM eq_rebalances WHERE decided_day=? AND audit IS NULL AND bars_sha IS NOT NULL "
                               "AND created_at<? ORDER BY rid", (day, m.audit_at))
        if not rows:
            self._panel_again = {}
            return
        inst = self._instance(rows[0]["instance"])
        adapter = self._adapter(PANEL_KIND)

        def unread(some: Sequence[Mapping[str, Any]], why: str) -> None:
            for r in some:
                self.state.execute("UPDATE eq_rebalances SET audit='unread' WHERE rid=?", (r["rid"],))
            self.alert("warning", f"equity: the panel's bars of {day} were not read again for {len(some)} decisions ({why})")

        kept = adapter.kept(self.root / STORE_DIR, t) if adapter is not None and self.root is not None else None
        if kept is None:
            unread(rows, "no kept fetch can be read")
            return
        symbols, old = kept
        if self._panel_again.get("day") != day:
            self._panel_again = {"day": day, "progress": {}}
        try:
            again = adapter.fetch(self.market, symbols, t, progress=self._panel_again["progress"], now=self.clock)
        except Exception as exc:  # noqa: BLE001 - again next minute; unread at the pre-open is a warning only
            again = None
            out["panel_audit"] = f"{type(exc).__name__}: {str(exc)[:120]}"
        if again is None:
            if now >= m.preopen:
                unread(rows, out.get("panel_audit") or "the read was not finished by the pre-open")
                self._panel_again = {}
            return
        self._panel_again = {}
        sha = adapter.bars_sha(old, symbols)
        diff = adapter.same(old, again, symbols, verdict=_bars_verdict)
        bad, drift, late = list(diff.get("mismatch") or []), list(diff.get("volume") or []), list(diff.get("late") or [])
        extras = {r["rid"]: set(loads(r["extra"], []) or []) for r in rows}
        every_extra = set().union(*extras.values()) if extras else set()
        stale, hit, clean = [], [], 0
        for r in rows:
            if (loads(r["fetch"], {}) or {}).get("sha") != sha:
                stale.append(r)
                continue
            mine = [s for s in bad if s not in every_extra or s in extras[r["rid"]]]
            if mine:
                hit.append(r["instance"])
                self._panel_mismatch(r, mine, now)
            else:
                clean += 1
                self.state.execute("UPDATE eq_rebalances SET audit='ok' WHERE rid=?", (r["rid"],))
        if stale:
            unread(stale, "the kept fetch is not the one they read")
        if drift or late:
            out["panel_bars_volume"] = f"{len(drift)} volumes and {len(late)} late bars differ (notes: the prices agree)"
        # (Counts only, under the book's own kind: a panel event names no symbol.)
        self.record("equity.bars_audit", {"day": day, "panel": True, "symbols": len(symbols), "mismatch": len(bad),
                                          "volume": len(drift), "late": len(late), "ok": clean, "hit": len(hit),
                                          "unread": len(stale)})

    def _panel_mismatch(self, row: Mapping[str, Any], bad: Sequence[str], now: float) -> None:
        """What it costs when the bars a panel decision read differ, in a price, from the morning's reading: the book's
        own cost of a mismatch (A8.11, A8.5: the alarm, that decision's planned buys cancelled, one failed decide a
        session) and two things of the panel's. Its planned `ineligible` exits of the differing symbols are cancelled
        too (the lot stays; the next close judges it again). AND THE DECISION IS VOID, WHOLE: its program's own
        planned SELLS are cancelled with its buys, as a rebalance recorded late plans neither (B9). A row marked so
        never stands as the standing target (`adapter.standing`), so the target that stands is the one before, which
        names the very lots the program wanted to sell: with the buys cancelled and the sells left to go, the book
        sold a name at one open and the old standing target bought it back at the next (a round trip of costs on a
        decision the House itself had thrown out). The House's own exits stand (max hold, a retired program, an
        ineligible name whose own bars agree). A17: on a hold day's row it is the hold day's alarm and counts toward
        no exit."""
        day, key = str(row["decided_day"]), str(row["instance"])
        inst = self._instance(key)
        adapter = self._adapter(PANEL_KIND)
        names = f"{', '.join(list(bad)[:5])}{', ...' if len(bad) > 5 else ''}"
        with self.state.transaction():
            self.state.execute("UPDATE eq_rebalances SET audit='mismatch' WHERE rid=?", (row["rid"],))
            for r in self.state.rows("SELECT * FROM eq_intents WHERE instance=? AND decided_day=? AND status='planned' "
                                     "AND (kind IN ('buy', 'sell') OR (kind='house_exit' AND tag=?))",
                                     (key, day, getattr(adapter, "INELIGIBLE", "ineligible"))):
                intent = Intent.of(r)
                if intent.kind in ("buy", "sell") or intent.symbol in set(bad):
                    self._finish(intent, "canceled", f"the bars of {day} read again differ ({len(bad)} symbols)")
            if inst is not None and inst.retired_at is None:
                counts = bool(int(row["called"] or 0)) or getattr(adapter, "HOLD_DAY_FAILS_EXIT", True)
                counted = dict(self.state.get("eq_failed", {}) or {})
                if counts and counted.get(key) != day:
                    inst.failed_decides += 1
                    counted[key] = day
                    self.state.put("eq_failed", counted)
                inst.why = f"bars audit {day}: {len(bad)} symbols differ"
                self._save_instance(inst)
        self.alert("error", f"equity: the bars {key}'s decision of {day} read differ when read again for {len(bad)} "
                            f"symbols ({names}): that decision's buys are canceled, and its program's own sells with "
                            "them (the decision is void; the House's exits stand)")

    def _panel_record_of(self, kind: str, key: str, lots: Sequence[Lot], row: Mapping[str, Any] | None,
                         refetch: bool) -> Any:
        """B10, THE LIVE RULES READ A PANEL PROGRAM BY CLOSE DATE (league/xs/book.py `date_record`; pre-registered in
        docs/operations.md before any panel program trades): `bands.edm1` and `bands.sized_up` are unchanged, as
        functions and as numbers; what they are fed is one return and one twin gap a close DATE (five lots bought on
        one date and sold on another share one market move and one fill minute), EDM1's sigma the Validation run's sd
        per close date, and the same-risk buy-and-hold the lots' dollars held in SPY, every close from ONE fetch, read
        only by the daily band sync (`refetch`) and only once the record holds the close dates sizing up needs. Raises
        when the adapter cannot be imported (no band moves on a record that cannot be read)."""
        adapter = self._adapter(kind)
        if adapter is None:
            raise RuntimeError(f"the {kind} adapter cannot be imported: its record cannot be read")
        et = self._et()
        since = (self.state.get("eq_band_since", {}) or {}).get(key) or {}
        probe_sessions = 0
        if since.get("band") in LIVE_BANDS and since.get("day"):
            probe_sessions = S.sessions_between(since["day"], S.ny_day(self.clock()).isoformat())
        try:
            twins = self.families.twins() if hasattr(self.families, "twins") else {}
        except Exception:  # noqa: BLE001
            twins = {}
        spy = None
        dates = {lot.exit_day for lot in lots if lot.exit_day and lot.entry_notional > 0}
        if refetch and et is not None and len(dates) >= int(et.sized_min_trades):
            span = adapter.spy_span(lots)
            if span is not None:
                spy = adapter.spy_closes(self.market, *span)
        rec = adapter.date_record(lots, twins or {}, spy)
        return B.EquityRecord(n=int(rec["n"]), returns=tuple(rec["returns"]), pnl=rec["pnl"], bh_pnl=rec["bh_pnl"],
                              probe_sessions=probe_sessions, realized_net=rec["realized_net"],
                              twin_gaps_bp=tuple(rec["twin_gaps_bp"]),
                              validation_r_sd=(row or {}).get("validation_r_sd"))

    # ------------------------------------------------------------------ the morning audit (A8.11)
    def _audit(self, now: float, m: S.Moments | None, out: dict) -> None:
        """The last decision's bars fetched again before the next open and compared (`_bars_verdict`): the raw open,
        high, low and close of every day exactly, and the adjustment=all rows as the as-of prices a program saw (all_s x
        raw_t / all_t, within the vendor's rounding: an event after t rescales the series without changing them). A
        PRICE mismatch is an alarm and a twin note; that decision's planned buys of the affected programs are canceled
        and it counts as a failed decide (A8.5): `_mismatch`. A VOLUME-only difference is a note and nothing else (the
        decision's `volume`, the `equity.bars_audit` record): a session's consolidated volume is not final at 16:20
        (the vendor's 1Day bar goes on counting late and after-hours prints), so judging it would cancel every
        morning's buys; a program that reads `volume[-1]` live reads the 16:20 figure. Each audited symbol's rows of the
        day are marked on its own verdict ("ok" on its prices, "mismatch"); a symbol the decision did not read is not
        marked."""
        if m is None or not (m.audit_at <= now < m.open_send):
            return
        try:
            self._panel_audit(now, m, out)      # B11 (release E4): the bars the panel decisions read, beside the book's
        except Exception as exc:  # noqa: BLE001 - the book's own audit goes on
            self._error("panel audit", exc, out)
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
        stored = self._stored_bars(symbols, decision["start"], day)
        bad, drift = [], []
        for symbol in symbols:
            start = decision["start"]
            fresh_raw = {_bar_day(r): r for r in (raw or {}).get(symbol) or [] if start <= (_bar_day(r) or "9999") <= day}
            fresh_all = {_bar_day(r): r for r in (adj or {}).get(symbol) or [] if start <= (_bar_day(r) or "9999") <= day}
            verdict = _bars_verdict(stored.get((symbol, "raw"), {}), stored.get((symbol, "all"), {}), fresh_raw,
                                    fresh_all, day)
            if verdict == "mismatch":
                bad.append(symbol)
            elif verdict == "volume":
                drift.append(symbol)
        verdict = "mismatch" if bad else "ok"
        with self.state.transaction():
            self.state.execute(f"UPDATE eq_bars SET audit='ok' WHERE day=? AND symbol IN "
                               f"({','.join('?' * len(symbols))})", (day, *symbols))
            if bad:
                self.state.execute(f"UPDATE eq_bars SET audit='mismatch' WHERE day=? AND symbol IN "
                                   f"({','.join('?' * len(bad))})", (day, *bad))
            decision["audit"], decision["mismatch"], decision["volume"] = verdict, bad, drift
            self.state.put("eq_decision", decision)
        if drift:
            out["bars_volume"] = f"the volume of {', '.join(drift)} read again differs (a note: its prices agree)"
        if bad:
            self._mismatch(day, bad, now, volume=drift)
        elif drift:
            self._audit_note(day, [], drift, now)
            self.record("equity.bars_audit", {"day": day, "mismatch": [], "volume": drift, "programs": []})

    def _stored_bars(self, symbols: Sequence[str], start: str, day: str) -> dict[tuple[str, str], dict[str, tuple]]:
        """{(symbol, adjustment): {day: (o, h, l, c, v)}}: the rows `eq_bars` keeps of `symbols` from `start` through
        `day` (the bars a decision of `day` used)."""
        stored: dict[tuple[str, str], dict[str, tuple]] = {}
        if not symbols:
            return stored
        for r in self.state.rows("SELECT * FROM eq_bars WHERE symbol IN (%s) AND day>=? AND day<=?"
                                 % ",".join("?" * len(symbols)), (*symbols, start, day)):
            stored.setdefault((r["symbol"], r["adjustment"]), {})[r["day"]] = (r["o"], r["h"], r["l"], r["c"], r["v"])
        return stored

    def _audit_note(self, day: str, bad: Sequence[str], volume: Sequence[str], now: float) -> None:
        """The twin note of a decision day (kv `eq_bars_audit` {day: {symbols, volume, at}}, the last 30): `symbols` the
        ones whose prices read again differ, `volume` the ones whose volume alone does."""
        notes = dict(self.state.get("eq_bars_audit", {}) or {})
        notes[day] = {"symbols": list(bad), "volume": list(volume), "at": now}
        self.state.put("eq_bars_audit", dict(sorted(notes.items())[-30:]))

    def _mismatch(self, day: str, bad: Sequence[str], now: float, *, volume: Sequence[str] = (),
                  where: str = "read again") -> list[str]:
        """What it costs when the bars a decision of `day` used differ, in a price, from a later reading (A8.11, A8.5):
        the twin note (kv `eq_bars_audit`), the alarm, and for each program that decided on one of `bad`: its planned
        buys of that decision canceled and one failed decide (one a session, `eq_failed`: a program whose own decide
        of that day already failed is not counted again). Returns the programs hit."""
        bad = list(bad)
        counted = dict(self.state.get("eq_failed", {}) or {})
        self._audit_note(day, bad, volume, now)
        self.alert("error", f"equity: the bars of {day} {where} differ for {', '.join(bad)}: that decision's buys "
                            "are canceled")
        hit = []
        for inst in self._instances(alive=True):
            # (A panel instance read none of these bars: its own are judged by `_panel_audit`.)
            if inst.last_decided_day != day or inst.kind != EQUITY_KIND:
                continue
            symbols_of = {str(s).upper() for s in (self._needs.get(inst.id) or {}).get("symbols") or []}
            planned = [Intent.of(r) for r in self.state.rows(
                "SELECT * FROM eq_intents WHERE instance=? AND decided_day=? AND kind='buy' AND status='planned'",
                (inst.id, day))]
            # A program whose NEEDS are not known in this process (a restart) counts as affected when it plans a buy.
            if not (symbols_of & set(bad) if symbols_of else planned):
                continue
            for intent in planned:
                self._finish(intent, "canceled", f"the bars of {day} {where} differ ({', '.join(bad)})")
            if counted.get(inst.id) != day:
                inst.failed_decides += 1
                counted[inst.id] = day
            inst.why = f"bars audit {day}: {', '.join(bad)}"
            self._save_instance(inst)
            hit.append(inst.id)
        if hit:
            self.state.put("eq_failed", counted)
        self.record("equity.bars_audit", {"day": day, "mismatch": bad, "volume": list(volume), "programs": hit})
        return hit

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
        while the book holds a lot or closed one in the last 100 days (a dividend is paid weeks after its ex-date).
        Read from a cursor (the latest activity day booked, less three days; each activity is booked once by its id);
        a row whose booking failed holds the cursor back, so it is read and booked again. A type the venue refuses
        (HTTP 422 fails a whole request) is read no more, each other type then alone (`_read_types`)."""
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
        rows = self._read_types(A.TYPES, after, together=True)
        if now - self._watch_at >= WATCH_EVERY:
            self._watch_at = now
            rows += self._read_types(A.WATCH, after, together=False)
        seen = {r["id"] for r in self.state.rows("SELECT id FROM eq_activities")}
        latest, held_back = cursor, None
        for row in sorted(rows, key=lambda r: (A.activity_day(r) or "", str(r.get("id")))):
            key = str(row.get("id") or "")
            day = A.activity_day(row) or ""
            if not key or key in seen:
                latest = max(latest, day)
                continue
            seen.add(key)
            try:
                self._book_activity(row, now, out)
                latest = max(latest, day)
            except Exception as exc:  # noqa: BLE001 - not booked: read again (and booked) next time
                held_back = day if held_back is None else min(held_back, day)
                self._error(f"activity {key}", exc, out)
        if held_back:
            latest = min(latest, held_back) if latest else held_back
        if latest and latest != cursor and (not cursor or latest > cursor):
            self.state.put("eq_activities_cursor", latest)

    def _read_types(self, types: Sequence[str], after: str | None, *, together: bool) -> list[dict]:
        """The activities of `types` after `after`: in one request when `together` (falling back to one request a
        type when the venue refuses the list with HTTP 422), else one a type, best effort; a type the venue refused is
        remembered (`eq_activity_refused`) and never asked again."""
        refused = set(self.state.get("eq_activity_refused", []) or [])
        wanted = [t for t in types if t not in refused]
        if not wanted:
            return []
        if together:
            try:
                return list(self.account.activities(wanted, after=after))
            except Exception as exc:  # noqa: BLE001
                if "422" not in str(exc):
                    raise
        rows: list[dict] = []
        for kind in wanted:
            try:
                rows.extend(self.account.activities([kind], after=after))
            except Exception as exc:  # noqa: BLE001 - best effort; a type the venue refuses is skipped from now on
                if "422" in str(exc):
                    refused.add(kind)
                    self.state.put("eq_activity_refused", sorted(refused))
                    self.alert("warning", f"equity: the venue refuses the activity type {kind}; it is read no more")
                elif together:
                    raise
        return rows

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

    def _fees(self, now: float, out: dict) -> None:
        """THE BROKER'S FEES (the Done meter's finality, league/ops/dlane_report.py: a checkpoint holding an equity close
        stays provisional until its lot's `info.fee_basis` is "broker"). A closed lot carries the book's estimate of its
        sale's SEC and TAF fees (`config.sell_fees`, booked at each fill); once the venue's regulatory fee rows of the
        lot's exit day are read (`FEE_LABEL`, every `ACTIVITIES_EVERY`), each row's dollars go to that day's equity-book
        sales pro rata by proceeds (over the proceeds the row states when they are at least the book's own, so another
        sale of the day, an assignment share's, keeps its part), the lot's `fees` and `cash` are set to the broker's
        figure and `info.fee_basis` to "broker" (the estimate kept as `info.fees_estimate`). A lot with no sale (a
        cash-out by a corporate action) owes no fee: "broker" at 0. A day still without a fee row `FEES_LATE_SESSIONS`
        later is told to the owner once a lot (the row's shape is a fact to verify on the first round trip). Like a late
        dividend, the posted fees reach `eq_lots` (which the Done meter and the band rules read), not the forward row
        already exported."""
        if now - self._fees_at < ACTIVITIES_EVERY:
            return
        today = S.ny_day(now).isoformat()
        lots = [lot for lot in (Lot.of(r) for r in self.state.rows(
            "SELECT * FROM eq_lots WHERE status='closed' AND exit_day IS NOT NULL AND exit_day<? ORDER BY exit_day, lid",
            (today,))) if lot.info.get("fee_basis") != "broker"]
        if not lots:
            return
        self._fees_at = now
        sold = {lot.lid: sum((D(r["qty"]) * D(r["px"]) for r in self.state.rows(
            "SELECT f.qty, f.px FROM eq_fills f JOIN eq_orders o ON o.eid=f.eid WHERE f.lid=? AND o.side='sell'",
            (lot.lid,))), ZERO) for lot in lots}
        unsold = [lot for lot in lots if sold[lot.lid] <= 0]
        rows = self._read_types(("FEE",), (dt.date.fromisoformat(min(str(x.exit_day) for x in lots))
                                           - dt.timedelta(days=1)).isoformat(), together=False) if len(unsold) < len(lots) else []
        by_day: dict[str, list[tuple[Decimal, Decimal | None]]] = {}
        for r in rows:
            words = str(r.get("description") or "").strip()
            amount, day = A.dec(r.get("net_amount")), A.activity_day(r)
            if r.get("order_id") or not FEE_LABEL.match(words) or amount is None or day is None:
                continue
            stated = FEE_PROCEEDS.search(words)
            by_day.setdefault(day, []).append((abs(amount), A.dec(stated.group(1)) if stated else None))
        posted = 0
        with self.state.transaction():
            for lot in lots:
                day = str(lot.exit_day)
                if sold[lot.lid] > 0 and day not in by_day:
                    if S.sessions_between(day, today) >= FEES_LATE_SESSIONS and not lot.info.get("fees_late_told"):
                        lot.info["fees_late_told"] = True
                        self._save_lot(lot)
                        self.alert("warning", f"equity: no REG or TAF fee row of {day} on the account after "
                                              f"{FEES_LATE_SESSIONS} sessions: lot {lot.lid}'s fees stay the book's "
                                              "estimate and the Done meter's checkpoints holding it stay provisional")
                    continue
                book_total = sum((sold[x.lid] for x in lots if str(x.exit_day) == day), ZERO)
                fee = ZERO
                for amount, stated in by_day.get(day, ()):
                    base = stated if stated is not None and stated >= book_total else book_total
                    if base > 0:
                        fee += amount * sold[lot.lid] / base
                fee = fee.quantize(SUBPENNY, rounding=ROUND_CEILING) if fee > 0 else ZERO
                lot.info.update(fee_basis="broker", fees_estimate=text(lot.fees), fees_day=day)
                lot.cash += lot.fees - fee
                lot.fees = fee
                self._save_lot(lot)
                posted += 1
        if posted:
            self.record("equity.fees_posted", {"lots": posted})
            out["fees_posted"] = posted

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
        # (Release R2: an event lot is no swarm family's: it reaches no forward record; the lane's own record, the twins
        # and the Done reader read it in eq_lots.)
        rows = self.state.rows("SELECT * FROM eq_lots WHERE status='closed' AND substr(instance, -2)=? AND lane!=? AND "
                               "lid NOT IN (SELECT lid FROM eq_exports) ORDER BY lid LIMIT ?",
                               (REAL_SUFFIX, EVENT_LANE, EXPORT_LIMIT))
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
    def _proof_step(self, now: float, m: S.Moments | None, out: dict) -> None:
        """The stock paper proof's minute (A10.1) until both its stages have passed, in this book's OPEN window (`m`)."""
        if self.stock_proof is None:
            return
        try:
            if self.stock_proof.passed():
                return
        except Exception:  # noqa: BLE001
            return
        answer = self.stock_proof.step(now, market=self.market, window=m)
        if isinstance(answer, Mapping) and answer.get("status"):
            out["paper_proof_stock"] = answer.get("status")

    # ------------------------------------------------------------------ the band rules' record
    def _record_of(self, family: str, version: int, row: Mapping[str, Any] | None, *, refetch: bool = False) -> Any:
        """The version's real record for the band rules (money's `bands.EquityRecord`): its closed ":r" lots in close
        order (net return on notional each), their net cash, the same-risk buy-and-hold over the same sessions
        (`_bh_pnl`), its whole sessions at Probe, its realized Probe net, its priced twins' gaps and EDM1's sigma.
        `refetch`: the buy-and-hold may read the vendor (the daily band sync asks so; a sizing at send time never
        does), and only once the record holds the closes the sizing-up rule needs before it reads the figure at all
        (`sized.min_trades`): the sync runs before the day's own bars are read, so the last exit day's close is not
        stored yet for a program that closed a lot that day."""
        key = instance_key(family, version)
        lots = [Lot.of(r) for r in self.state.rows(
            "SELECT * FROM eq_lots WHERE instance=? AND status='closed' ORDER BY closed_at, lid", (key,))]
        inst = self._instance(key)
        kind = inst.kind if inst is not None else K.kind_of((row or {}).get("structure"))
        if kind == PANEL_KIND:
            # B10 (release E4): a panel program's record is read ONE OBSERVATION A CLOSE DATE.
            return self._panel_record_of(kind, key, lots, row, refetch)
        returns = tuple(float(lot.cash / lot.entry_notional) for lot in lots if lot.entry_notional > 0)
        et = self._et()
        refetch = bool(refetch and et is not None and len(returns) >= int(et.sized_min_trades))
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
        return B.EquityRecord(n=len(returns), returns=returns, pnl=pnl, bh_pnl=self._bh_pnl(lots, refetch=refetch),
                              probe_sessions=probe_sessions,
                              realized_net=sum((lot.cash for lot in lots if lot.probe), ZERO),
                              twin_gaps_bp=tuple(gaps),
                              validation_r_sd=(row or {}).get("validation_r_sd"))

    def _bh_pnl(self, lots: Sequence[Lot], *, refetch: bool = False) -> Decimal | None:
        """THE SAME-RISK BUY-AND-HOLD OVER THE SAME SESSIONS (goal item 4's scaling rule): per symbol, its lots' average
        exposure over their span (entry notional x sessions held, over the span's sessions) held from the close before
        the first entry to the close of the last exit, at adjustment=all closes (total return). None when a close is
        missing (the rule then fails `beat_bh`).

        ONE BASIS: an adjustment=all close is adjusted for every event up to the day it was fetched, so two closes of
        two fetches straddling an ex-date or a split are not one series (their ratio would lose the dividend, or be off
        by the split). The two closes are read from `eq_bars` only when one fetch wrote both (the same series `sha`);
        otherwise both are read again in ONE fetch (`refetch`: the daily band sync), else the figure is None."""
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
            rows = {r["day"]: r for r in self.state.rows(
                "SELECT day, c, sha FROM eq_bars WHERE symbol=? AND adjustment='all' AND day IN (?, ?)",
                (symbol, before, last))}
            closes = {}
            if before in rows and last in rows and rows[before]["sha"] == rows[last]["sha"]:
                closes = {d: A.dec(r["c"]) for d, r in rows.items()}
            elif refetch:
                closes = self._closes_again(symbol, before, last)
            start, end = closes.get(before), closes.get(last)
            if not start or not end or start <= 0:
                return None
            total += exposure * (end / start - 1)
        return total

    def _closes_again(self, symbol: str, first: str, last: str) -> dict[str, Decimal | None]:
        """{day: adjustment=all close} of `symbol` on the days `first` and `last`, read in ONE fetch (one basis); {}
        when it cannot be read."""
        try:
            end = (dt.date.fromisoformat(last) + dt.timedelta(days=1)).isoformat()
            fetched = self.market.bars([symbol], timeframe="1Day", start=first, end=end, adjustment="all")
        except Exception:  # noqa: BLE001 - unpriced: the rule fails `beat_bh` and reads again at the next sync
            return {}
        return {d: A.dec(r.get("c")) for r in (fetched or {}).get(symbol) or []
                for d in (_bar_day(r),) if d in (first, last)}
    # ------------------------------------------------------------------ THE EVENT KIND (release R2)
    # PREREG-EVL-1 section 8 (with PREREG-EVL-2): a program whose held look passed trades real money from the next
    # session, its entries whole-share limit-on-open / limit-on-close orders at 1.25 x the previous SIP close, its exits
    # market sales at its scheduled auction. The rules are league/events/book.py's (the adapter, `BOOKS["event"]`); here
    # they meet E1's order path: the windows of the auctions (`schedule.event_moments`), the write-before-POST and
    # client-id discipline (`_send`), one working order a symbol, the day's order count, `size_entry`, the walls.
    #: Seconds after a decision's moment the book waits for the lane's own (shadow) decision of the same auction before
    #: it decides on the store as it stands (the universe rows of the day's issuers are written by it, and by the
    #: verdicts asked ahead of it). At the close the book never depends on the lane's own decision (release 1019b's
    #: review): on the House that decision starts a minute after its time (league/events/house.py `CLOSE_GRACE`) and
    #: after the book's minute, so the wait ends at 15:47 ET with the lane's universe rows as the passes ahead of it
    #: wrote them, and the book reads each name's T29 minute itself (`_event_minute_closes`, all the day's names
    #: together), the T29 bar then a minute inside the plan's SIP window.
    EVENT_DECIDE_WAIT_S = {"open": 240.0, "close": 60.0}
    #: Seconds after an auction its orders' end is waited for before an unfilled one is judged (the venue ends an
    #: auction order at its auction; its last status takes a reading or two to arrive).
    EVENT_SETTLE_S = 120.0

    def _event_adapter(self) -> Any:
        return self._adapter(EVENT_KIND)

    def _event_settings(self) -> Any:
        adapter = self._event_adapter()
        if adapter is None:
            raise RuntimeError("the event adapter (league/events/book.py) cannot be imported")
        return adapter.settings()

    def _event_row(self, iid: Any) -> dict | None:
        """The event side row of an intent (`eq_event_intents`), or None (no such row, or no such table)."""
        if iid is None or not _has_table(self.state.rows, "eq_event_intents"):
            return None
        rows = self.state.rows("SELECT * FROM eq_event_intents WHERE iid=?", (int(iid),))
        return dict(rows[0]) if rows else None

    def _event_lane_store(self) -> Any:
        """The lane's store, read-only (`<root>/events/events.sqlite`), opened once it exists; None without it."""
        if self._event_lane is None:
            adapter = self._event_adapter()
            self._event_lane = adapter.open_lane(self.root) if adapter is not None else None
        return self._event_lane

    def _auction_proof(self) -> Any:
        """THE AUCTION PAPER PROOF (league/events/proof.py) on the practice account the stock proof holds; None with no
        paper account (then no event buy, ever)."""
        if self._auction is None and self.stock_proof is not None and getattr(self.stock_proof, "account", None) is not None:
            from ..events.proof import AuctionProof

            self._auction = AuctionProof(self.state, self.stock_proof.account, self.market, clock=self.clock,
                                         record=lambda kind, payload: self.record(kind, payload), alert=self.alert)
        return self._auction

    def _event_open_block(self) -> str | None:
        """Why no EVENT buy may go now beside the House's own gates (`_open_block`): the event kind's switch and the
        auction paper proof's BUY stage (its SELL stage failed stops new buys too), or None."""
        try:
            s = self._event_settings()
        except Exception as exc:  # noqa: BLE001 - fail closed
            return f"the event kind's settings cannot be read ({type(exc).__name__})"
        if not s.enabled:
            return "equity_money.event.enabled is false: no event buy"
        proof = self._auction_proof()
        if proof is None:
            return "no auction paper proof: no paper account"
        try:
            if not proof.buy_passed():
                return "the auction paper proof's BUY stage (paper_proof_auction_buy) has not passed"
            failed = proof.sell_failed()
            if failed:
                return f"{failed}: new event buys stop until it passes"
        except Exception as exc:  # noqa: BLE001
            return f"the auction paper proof could not be read ({type(exc).__name__})"
        return None

    def _event_seat_block(self, inst: Instance) -> str | None:
        """Why this event program may open nothing now: its band in the book's own table (`eq_event_programs`, written by
        the day's band sync), read at every send: a demotion or retirement stops its next buy at once."""
        rows = self.state.rows("SELECT band, why FROM eq_event_programs WHERE program=? AND version=?",
                               (inst.family, int(inst.version)))
        band = rows[0]["band"] if rows else None
        if band not in EVENT_LIVE_BANDS:
            return f"its band is {band or 'unknown'}: exits only ({(rows[0]['why'] if rows else '') or ''})"[:300]
        return None

    def _event_step(self, now: float, m: S.Moments | None, out: dict, real_block: Callable[..., str | None],
                    killed: Callable[[], bool]) -> None:
        """THE EVENT KIND'S MINUTE (release R2): the auction paper proof; the ends of the auctions passed (fills are
        booked by `_sync_orders`; an unfilled buy is missed, an unfilled sale climbs the fallback ladder); then each
        auction in its window: its exits planned, its SALES sent, its decision (the passing programs' picks), its
        BUYS sent."""
        adapter = self._event_adapter()
        if adapter is None:
            return
        s = adapter.settings()
        em = S.event_moments(S.ny_day(now), s.offsets)
        try:
            proof = self._auction_proof()
            if proof is not None:
                proof.step(now, em)     # (its row is kv `paper_proof_auction` and the health page's `events.proof`)
        except Exception as exc:  # noqa: BLE001 - never the event step's end
            self._error("auction proof", exc, out)
        if em is not None:
            # (Release 1019b's review: a failure of the auctions' ends or of a decision, a lane store that cannot be read
            # included, never stops the minute's sends.)
            try:
                self._event_finish(now, em, adapter, out)
            except Exception as exc:  # noqa: BLE001 - finished again next minute
                self._error("event finish", exc, out)
            # THE SALES BEFORE THE DECISION (release 1019b's third review: AN EXIT NEVER WAITS ON AN ENTRY'S DECISION).
            # The decision reads (the lane, the close's T29 minutes) for as long as its reads take, and `_send` judges the
            # window's cut-off on the wall clock: a sale sent after it could miss its cross. So, for each auction inside
            # its window: the exits due at it planned (from the decision's first minute, `_event_due_exits`), its sales
            # sent (inside its send window), then its decision, then its buys.
            for at, decide, send, until in (("open", em.open_decide, em.open_send, em.open_until),
                                            ("close", em.close_decide, em.close_send, em.close_until)):
                if not decide <= now < until:
                    continue
                sending = send <= now
                try:
                    self._event_due_exits(em, at, adapter)
                except Exception as exc:  # noqa: BLE001 - the decision plans them again
                    self._error(f"event exits {at}", exc, out)
                if sending:
                    self._event_send(now, em, at, s, adapter, real_block, killed, out, sides=("sell",))
                try:
                    self._event_decide(now, em, at, s, adapter, out)
                except Exception as exc:  # noqa: BLE001 - its exits were planned first; decided again next minute
                    self._error(f"event decide {at}", exc, out)
                if sending:
                    self._event_send(now, em, at, s, adapter, real_block, killed, out, sides=("buy",))
        try:
            self._event_fills(adapter, out)     # (the real fills handed back to the lane, PREREG-EVL-3; any day)
        except Exception as exc:  # noqa: BLE001 - written again next minute
            self._error("event fills", exc, out)

    # ---------------------------------------------------------------- the band sync
    def _event_sync(self, now: float, day: dt.date, s: Any, adapter: Any, lane: Any) -> list[Any] | None:
        """THE EVENT KIND'S BAND SYNC, once a session, at its first decision, and again at its close decision when the
        lane's band history moved since (`_event_bands_due`, release 1019f): each seating version's band AS THE LANE'S
        STORE SAYS IT (league/events/book.py `bands`: learning from birth, Probe, Sized, retired; PREREG-EVL-3 section
        2) written to `eq_event_programs`, and its instance (`<program>@<version>:r`, kind "event", lane "event") made,
        updated or retired. A program that leaves the live bands decides no more; its open lots exit at their own
        scheduled auctions (nothing is sold by a band move). None when the lane's band table cannot be read: nothing is
        written, no buy is planned this decision, and the next decision reads it again. The lane's band mark
        (`book.band_mark`) is read BEFORE the bands and kept with the sync (kv `eq_event_band_mark`), so a move the lane
        writes between the two reads is read at the next decision."""
        try:
            mark = adapter.band_mark(lane)
        except Exception:  # noqa: BLE001 - an unread mark makes the close decision read the bands again
            mark = None
        bands = adapter.bands(lane, s)
        if bands is None:
            return None
        held = {(r["program"], int(r["version"])): dict(r) for r in self.state.rows("SELECT * FROM eq_event_programs")}
        born: list[str] = []
        with self.state.transaction():
            for b in bands:
                was = held.get((b.program, b.version)) or {}
                self.state.upsert("eq_event_programs", {"program": b.program, "version": b.version, "band": b.band,
                                                        "since": b.since, "why": b.why[:400], "updated_at": now},
                                  "program, version")
                key = instance_key(b.program, b.version)
                inst = self._instance(key)
                program = adapter.program_of(b.program, b.version)
                if b.live and program is not None:
                    if inst is None:
                        inst = Instance(key, b.program, b.version, EVENT_LANE, "", "", {}, b.band, False, program.hold,
                                        created_at=now, kind=EVENT_KIND)
                        self.record("equity.instance", {"instance": key, "band": b.band, "lane": EVENT_LANE},
                                    agent=b.program)
                        born.append(b.program)
                    inst.band, inst.retired_at, inst.why = b.band, None, ""
                    self._save_instance(inst)
                elif inst is not None and inst.retired_at is None:
                    inst.retired_at, inst.why, inst.band = now, f"{b.band}: {b.why}"[:400], b.band
                    self._save_instance(inst)
                    self.record("equity.instance", {"instance": key, "retired": True, "why": inst.why}, agent=b.program)
                if was.get("band") != b.band:
                    self.record("equity.band", {"family": b.program, "version": b.version, "from": was.get("band"),
                                                "to": b.band, "why": b.why[:300], "lane": EVENT_LANE}, agent=b.program)
                    if was.get("band") is not None:
                        self.alert("warning", f"equity: event program {b.program} v{b.version} is now {b.band}: "
                                              f"{b.why[:200]}")
            self.state.put("eq_event_synced", day.isoformat())
            self.state.put(EVENT_BAND_MARK, mark)
        if born:
            self.alert("warning", f"equity: {len(born)} event program(s) trade real money from {day.isoformat()} at "
                                  f"their lane's bands ({', '.join(born)[:300]}); every buy waits on the gateway's "
                                  "STOCK_EVENT_BUYS and the auction paper proof's BUY stage")
        return bands

    def _event_bands_due(self, day: str, at: str, adapter: Any, lane: Any) -> str | None:
        """Why the band sync runs at this decision, or None: "first", the session's first decision (`eq_event_synced`
        is another day); "moved", THE CLOSE DECISION when the lane's band mark (`book.band_mark`: the newest
        `band_history` id) is not the one the session's sync kept, or cannot be read (release 1019f: the lane's screen
        runs its looks after the open, so a look written that morning moves its program's band before the close, and
        PREREG-EVL-3 section 2 gives Probe "from the first decision after a passed look"). The open decision is always
        a session's first; a band moved after the close decision is read at the next session's first."""
        if (self.state.get("eq_event_synced") or "") != day:
            return "first"
        if at != "close":
            return None
        try:
            mark = adapter.band_mark(lane)
        except Exception:  # noqa: BLE001 - read the bands again: `_event_sync` says whether they can be read
            mark = None
        return "moved" if mark is None or mark != self.state.get(EVENT_BAND_MARK) else None

    # ---------------------------------------------------------------- the decision
    def _event_decide(self, now: float, em: S.EventMoments, at: str, s: Any, adapter: Any, out: dict) -> None:
        """ONE DECISION A SESSION AND AUCTION (`eq_event_decisions`, status `done`): the lots due to exit at this auction
        planned first (`_event_exits`, whatever the switch says: an exit never waits on it), then, while the event kind
        is on, each live program of this auction's entries asked for its real-money picks (`book.picks`, ranked), and
        the auction's slots given out IN ROOM'S ORDER (`book.allocate`, release 1019b's second review: Sized, then
        Probe, then learning, then the tables' order, round-robin inside Sized and inside Probe since the captain's A85;
        each program takes its own ranked picks, passing over a name an
        earlier program was given and a pick `_event_gate` skips whatever the room (no whole share fits by price, or the
        name is sold at this auction), until its room, `max_open` less what it holds and has on order, is full), and
        recorded as buy intents with their side rows (the limit, sigma, the weight, the exit plan). It waits a few
        minutes for the lane's own decision of the same auction (`EVENT_DECIDE_WAIT_S`), then decides on the store as it
        stands; with no lane on this House it plans the exits alone. A decision that cannot read E is written `failed`
        with its errors and made again the next minute of its window; a T29 minute it cannot read (`_event_minute_closes`,
        bounded by the window) drops only the REACT rows of that name (release 1019b's third review: every other pick
        goes, and the summary says why)."""
        day = em.day.isoformat()
        if self._event_decided(day, at):
            return
        decided_at = em.open_decide if at == "open" else em.close_decide
        until = em.open_until if at == "open" else em.close_until
        # THE EXITS FIRST, before anything of the lane is read (release 1019b's review: an exit never waits on the lane):
        # planned at the decision's first minute and again each minute until the decision is made (a lot whose sale is
        # planned or working is passed over, so this plans each sale once; `_event_step` plans them before it too).
        self._event_exits(em, at, adapter)
        lane = self._event_lane_store()
        if lane is not None and not adapter.decided(lane, em.day, at) and now < decided_at + self.EVENT_DECIDE_WAIT_S[at]:
            out["event_decide"] = f"waiting for the lane's own {at} decision of {day}"
            return
        exits = self._event_sales(day, at)
        readable = True
        synced = self._event_bands_due(day, at, adapter, lane) if lane is not None else None
        if synced is not None:
            readable = self._event_sync(now, em.day, s, adapter, lane) is not None
        summary: dict[str, Any] = {"exits": exits, "lane": lane is not None, "enabled": bool(s.enabled), "programs": {},
                                   "bands": readable}
        if synced is not None:
            summary["band_sync"] = synced
        planned: list[tuple[Any, Any, Any]] = []
        sigmas: dict[str, float | None] = {}
        if not readable:
            out["event_bands"] = "the lane's band table cannot be read: no event buy is planned this decision"
        if lane is not None and s.enabled and readable:
            moment = dt.datetime.fromtimestamp(decided_at, dt.timezone.utc)
            unread: list[str] = []
            # (The T29 reads end before the window's last minute: release 1019b's third review, `EVENT_MINUTE_STOP_S`.)
            reaction = adapter.reaction_reader(
                lane, em.day, daily=self._event_daily_close,
                minutes=lambda symbol, session: self._event_minute_close(symbol, session, until=until),
                minutes_many=lambda names, session: self._event_minute_closes(names, session, failed=unread, until=until))
            wanted: dict[str, list[Any]] = {}
            rooms: dict[str, int] = {}
            insts = {}
            for inst in self._instances(alive=True):
                program = adapter.program_of(inst.family, inst.version) if inst.kind == EVENT_KIND else None
                if program is None or not inst.live or program.entry_at != at:
                    continue
                room = s.max_open(inst.band) - self._event_open_count(inst.id)
                if room <= 0:
                    # (A program with no room reads nothing: release 1019b's review; its picks would all be dropped.)
                    wanted[inst.family], rooms[inst.family] = [], 0
                    insts[inst.family] = (inst, program)
                    summary["programs"][inst.family] = {"picks": None, "room": 0}
                    continue
                held = self._event_held(inst, em.day, adapter)
                try:
                    got = adapter.picks(lane, program, em.day, decided_at=moment, reaction=reaction,
                                        held=lambda cik, held=held: cik in held)
                except Exception as exc:  # noqa: BLE001 - that program plans nothing this auction; the others go on
                    self._error(f"event picks {inst.family}", exc, out)
                    summary["programs"][inst.family] = {"error": f"{type(exc).__name__}: {str(exc)[:120]}"}
                    continue
                wanted[inst.family], rooms[inst.family] = list(got), room
                insts[inst.family] = (inst, program)
                summary["programs"][inst.family] = {"picks": len(got), "room": room}
            gate, unreadable = self._event_gate(day, at, s, adapter) if any(wanted.values()) else (None, "")
            if unread:
                # (Release 1019b's third review: A T29 BATCH FAILURE DROPS ONLY THE REACT ROWS' PICKS. A name whose T29
                # minute could not be read has no reaction, so a REACT row of it is not taken (programs.select); every
                # other close-entry program's picks go, NEWS-READ-ON's included, and the decision is made with what was
                # read, its errors in the summary and the minute's `errors`. A lane mark (its own 15:30 minute) still
                # serves its name.)
                summary["errors"] = unread[:5]
                summary["t29"] = "unread: a REACT row of a name whose T29 minute was not read is not taken"
                for why in summary["errors"]:
                    out.setdefault("errors", []).append(f"event decide {at}: {why}"[:300])
            if unreadable:
                # (Release 1019b's second review: E could not be read: no pick is decided on a reading that is missing.
                # The decision is written `failed` with why, and made again the next minute of its window; its exits
                # are planned already. None is made at or after the cut-off: that auction's events are not entered.)
                summary["errors"] = (unread + [unreadable])[:5]
                out.setdefault("errors", []).append(f"event decide {at}: {unreadable}"[:300])
                with self.state.transaction():
                    self.state.upsert("eq_event_decisions", {"day": day, "at": at, "decided_at": _iso(decided_at),
                                                             "status": "failed", "summary": dumps(summary),
                                                             "created_at": now}, "day, at")
                out["event_decide"] = f"{at} {day}: not decided ({unreadable[:160]}); decided again next minute"
                return
            lost: list[tuple[str, str]] = []

            def skip(family: str, pick: Any) -> str | None:
                why = gate(insts[family][0].band, pick)
                if why == "sale":
                    lost.append((family, str(pick.symbol).upper()))
                return why
            given, passed = adapter.allocate(wanted, rooms, {family: insts[family][0].band for family in wanted},
                                             skip if gate else None)
            symbols = sorted({p.symbol for picks in given.values() for p in picks})
            sigmas = self._event_sigmas(symbols, em.day, s) if symbols else {}
            for family, picks in given.items():     # (ROOM's order: the sends go in it)
                inst, program = insts[family]
                for pick in picks:
                    planned.append((inst, program, pick))
                summary["programs"][family]["planned"] = len(picks)
                if passed.get(family):
                    summary["programs"][family]["skipped"] = dict(passed[family])
            taken = self._event_sale_takers(day, at, lost, adapter) if lost else {}
            if taken:
                summary["sale_to_later"] = taken
        with self.state.transaction():
            for inst, program, pick in planned:
                self._event_plan_buy(inst, program, pick, em, at, s, adapter, sigmas.get(pick.symbol), now)
            self.state.upsert("eq_event_decisions", {"day": day, "at": at, "decided_at": _iso(decided_at),
                                                     "status": "done", "summary": dumps(summary), "created_at": now},
                              "day, at")
        if lane is None and not exits:
            return      # (no lane on this House and no event lot: nothing was read or planned, and nothing is said)
        out["event_decide"] = f"{at} {day}: {exits} exits, {len(planned)} buys planned"
        if lane is not None and planned:
            # (The day's eligible list goes to the gateway when a buy is planned, and again before each buy is sent if
            # the lane's universe grew since: with every program in shadow the gateway is never asked.)
            self._event_publish(em.day, adapter, lane, out)
        self.record("equity.event_decide", {"day": day, "at": at, "exits": exits, "buys": len(planned),
                                            "programs": {k: v.get("planned", 0) for k, v in summary["programs"].items()},
                                            **({"sale_to_later": summary["sale_to_later"]}
                                               if summary.get("sale_to_later") else {})})

    def _event_plan_buy(self, inst: Instance, program: Any, pick: Any, em: S.EventMoments, at: str, s: Any,
                        adapter: Any, sd: float | None, now: float) -> None:
        """One buy intent of an event pick and its side row (inside the decision's transaction)."""
        iid = self._next("eq_intents", "iid")
        day = em.day.isoformat()
        limit = adapter.limit_price(pick.prev_close, s.limit_ratio)
        exit_day, exit_at = adapter.exit_plan(program, em.day)
        weight = adapter.weight(sd, program.hold, s)
        intent = Intent(iid, inst.id, inst.family, inst.version, day, day, at, "buy", "planned", symbol=pick.symbol,
                        share=s.share(inst.band), tag=f"{adapter.TAG}:{pick.event}"[:120],
                        why=f"event {pick.event}: rank {pick.rank}, limit {limit}"[:400], created_at=now, updated_at=now)
        self._save_intent(intent)
        self.state.upsert("eq_event_intents", {
            "iid": iid, "program": program.id, "version": program.version, "event": pick.event, "side": "buy",
            "band": inst.band, "tif": "opg" if at == "open" else "cls", "otype": "limit", "symbol": pick.symbol,
            "cik": pick.cik,
            "day": day, "at": at, "rank_key": pick.rank, "adv20": pick.adv20, "prev_close": text(pick.prev_close),
            "limit_px": text(limit), "sigma": sd, "hold": program.hold, "weight": text(weight), "exit_day": exit_day,
            "exit_at": exit_at, "lid": None, "rung": 0,
            "decided_at": _iso(em.open_decide if at == "open" else em.close_decide), "why": None, "created_at": now},
            "iid")

    def _event_decided(self, day: str, at: str) -> bool:
        """Whether the decision of this session and auction is made (`eq_event_decisions` status `done`)."""
        return bool(self.state.rows("SELECT 1 AS x FROM eq_event_decisions WHERE day=? AND at=? AND status='done'",
                                    (day, at)))

    def _event_due_exits(self, em: S.EventMoments, at: str, adapter: Any) -> int:
        """THE EXITS DUE AT THIS AUCTION planned (`_event_exits`) while its decision is not made, from the decision's
        first minute: `_event_step` plans them before it sends the auction's sales, and sends those before the decision
        reads anything (release 1019b's third review). Returns how many were planned now."""
        if self._event_decided(em.day.isoformat(), at):
            return 0
        return self._event_exits(em, at, adapter)

    def _event_sales(self, day: str, at: str) -> int:
        """The event lots' sales planned at this auction (its exits, `_event_exits`)."""
        return int(self.state.rows("SELECT COUNT(*) AS n FROM eq_event_intents WHERE side='sell' AND day=? AND at=?",
                                   (day, at))[0]["n"])

    def _event_open_count(self, key: str) -> int:
        """What an event program holds and has on order: its open lots, and its buy intents still to execute."""
        lots = self.state.rows("SELECT COUNT(*) AS n FROM eq_lots WHERE instance=? AND status IN ('open', 'closing')",
                               (key,))[0]["n"]
        buys = self.state.rows("SELECT COUNT(*) AS n FROM eq_intents WHERE instance=? AND kind='buy' AND status IN "
                               "('planned', 'sent')", (key,))[0]["n"]
        return int(lots) + int(buys)

    def _event_held(self, inst: Instance, day: dt.date, adapter: Any) -> set[str]:
        """THE ISSUERS real money holds for this program (PREREG-EVL-1 section 5: one position per issuer per program):
        its lots open, or closed within the last `ISSUER_GAP_SESSIONS` sessions, and its buys still to execute."""
        since = adapter.sessions_back(day, adapter.ISSUER_GAP_SESSIONS).isoformat()
        out: set[str] = set()
        for r in self.state.rows("SELECT status, exit_day, info FROM eq_lots WHERE instance=?", (inst.id,)):
            info = loads(r["info"], {}) or {}
            cik = str(((info.get("evl") or {}) if isinstance(info, Mapping) else {}).get("cik") or "")
            if cik and (r["status"] != LOT_CLOSED or str(r["exit_day"] or "") >= since):
                out.add(cik)
        for r in self.state.rows("SELECT e.cik FROM eq_event_intents e JOIN eq_intents i ON i.iid=e.iid WHERE "
                                 "i.instance=? AND e.side='buy' AND i.status IN ('planned', 'sent')", (inst.id,)):
            if r["cik"]:
                out.add(str(r["cik"]))
        return out

    def _event_gate(self, day: str, at: str, s: Any, adapter: Any) -> tuple[Callable[[str, Any], str | None] | None, str]:
        """THE RULES THAT SKIP A REAL-MONEY EVENT WHATEVER THE ROOM, applied at the decision BEFORE a pick takes a slot of
        its program's room (release 1019b's second review: PREREG-EVL-3 section 2 skips such an event, "the shadow keeps
        the event", and its program's limit of open positions is on positions, never on slots), on the figures
        `_size_event` sizes the buy on at its send: E the account equity at the previous close (`last_equity`, never
        above the House's sizing equity), the limit (`book.limit_price`), and the name's book-wide value (the larger of
        the book's lots and the account's position, plus the working buys of the name). A pick is skipped when:
        - "name_wall": one share at the limit does not fit under the book-wide 10% a name (`per_name_share` x E less the
          name's book-wide value), so above 10% of E for a name held nowhere (not TRADABLE, PREREG-EVL-1 section 5);
        - "one_share": the band's target (`position_share` x E) buys no whole share at the limit and its one-share rule
          refuses one (learning: one share at the limit above `one_share_max.learning` x E, 5%);
        - "sale": a sale of the name is planned or working at this same auction (an event lot's exit, planned by this
          decision before its picks): no buy of the name goes in it (`_event_sales_at`; an exit never waits on an
          entry, the reading that trades less).
        The walls that depend on the whole book (the 100% book, the cash, the loss budget) are `_size_event`'s at the
        send, as before. RELEASE 1019f: the 10% a name is judged on `wall_equity` (the lower of E and the account's
        current equity, the gateway's figure: the reading that trades less), as `_size_event`'s caps are; the band's
        target and its one-share rule stay on E. Returns (skip(band, pick) -> one of those keys or None, "") or (None,
        why E cannot be read)."""
        E = self.sizing_equity()
        if E is None or E <= 0:
            return None, "no sizing equity (the grant or the account)"
        account = self._read_account()
        if account is None:
            return None, "the account could not be read this minute"
        last = A.dec(account.get("last_equity"))
        if last is not None and last > 0:
            E = min(E, last)     # (the equity at the previous close, as `_size_event` reads it)
        walls = wall_equity(E, account)     # (release 1019f: the name wall's equity, as the gateway judges it)
        held: dict[str, tuple[Decimal | None, Decimal]] = {}
        for r in self._read_positions() or []:
            if str(r.get("asset_class") or "") == "us_equity":
                held[str(r.get("symbol") or "").upper()] = (A.dec(r.get("market_value")), A.dec(r.get("qty")) or ZERO)
        buying: dict[str, Decimal] = {}
        for o in self._orders(WORKING):
            if o.side == "buy":
                buying[o.symbol] = buying.get(o.symbol, ZERO) + o.remaining * o.limit_px
        selling = self._event_sales_at(day, at)
        wall = s.per_name * walls

        def skip(band: str, pick: Any) -> str | None:
            symbol = str(pick.symbol).upper()
            if symbol in selling:
                return "sale"
            limit = adapter.limit_price(pick.prev_close, s.limit_ratio)
            if limit <= 0:
                return "name_wall"
            market_value, qty = held.get(symbol, (None, ZERO))
            account_value = abs(market_value or qty * limit)
            book_value = sum((lot.value for lot in self._lots(symbol=symbol)), ZERO)
            if limit > wall - (max(book_value, account_value) + buying.get(symbol, ZERO)):
                return "name_wall"
            cap = s.one_share_cap(band)
            if s.share(band) * E < limit and cap is not None and limit > cap * E:
                return "one_share"
            return None
        return skip, ""

    def _event_sale_takers(self, day: str, at: str, lost: Sequence[tuple[str, str]], adapter: Any
                           ) -> dict[str, dict[str, int]]:
        """THE CASES PREREG-EVL-4 SECTION 1.3 STATES AND COUNTS (it never prevents them): of the picks the sale gate
        skipped at this auction (`lost`: (program, symbol)), those whose name a LATER row's lot sells there, in the
        tables' order (`book.order_of`: an earlier row's real-money buy lost to a later row's sale, for instance
        EVL-8K-READ-O1 at the next open after an overnight row of PREREG-EVL-4 bought the name at the close): {skipped
        program: {selling program: n}}, in the decision's summary (`sale_to_later`) and its ledger record."""
        sellers: dict[str, set[str]] = {}
        for r in self.state.rows("SELECT DISTINCT e.symbol, e.program FROM eq_event_intents e JOIN eq_intents i ON "
                                 "i.iid=e.iid WHERE e.side='sell' AND e.day=? AND e.at=? AND i.status IN ('planned', "
                                 "'sent')", (day, at)):
            sellers.setdefault(str(r["symbol"]).upper(), set()).add(str(r["program"]))
        out: dict[str, dict[str, int]] = {}
        for family, symbol in lost:
            for seller in sorted(sellers.get(symbol, ())):
                if seller != family and adapter.order_of(seller) > adapter.order_of(family):
                    row = out.setdefault(family, {})
                    row[seller] = row.get(seller, 0) + 1
        return out

    def _event_sales_at(self, day: str, at: str, symbol: str | None = None) -> set[str]:
        """The symbols an event lot's SALE is planned or working for at this auction (its intent not finished)."""
        sql = ("SELECT DISTINCT e.symbol FROM eq_event_intents e JOIN eq_intents i ON i.iid=e.iid WHERE e.side='sell' "
               "AND e.day=? AND e.at=? AND i.status IN ('planned', 'sent')")
        args: list[Any] = [day, at]
        if symbol is not None:
            sql += " AND e.symbol=?"
            args.append(symbol)
        return {str(r["symbol"]).upper() for r in self.state.rows(sql, args)}

    def _event_sigmas(self, symbols: Sequence[str], day: dt.date, s: Any) -> dict[str, float | None]:
        """{symbol: the daily return sd of the `sigma_sessions` sessions before `day`} from the adjusted SIP daily bars
        (one read for every pick of an auction); None for a symbol whose bars cannot be read (its lot then weighs the
        stricter `EVENT_STRICT_WEIGHT`)."""
        adapter = self._event_adapter()
        start = (day - dt.timedelta(days=int(s.sigma_sessions * 2) + 14)).isoformat()
        try:
            got = self.market.bars(list(symbols), timeframe="1Day", start=start, adjustment="all") or {}
        except Exception:  # noqa: BLE001 - unread: the stricter weight
            return {symbol: None for symbol in symbols}
        out = {}
        for symbol in symbols:
            rows = sorted((r for r in got.get(symbol) or [] if (_bar_day(r) or "9999") < day.isoformat()),
                          key=lambda r: _bar_day(r) or "")
            closes = [float(A.dec(r.get("c")) or 0) for r in rows]
            out[symbol] = adapter.sigma(closes, s.sigma_sessions)
        return out

    def _event_daily_close(self, symbol: str, day: dt.date) -> float | None:
        """The raw SIP daily close of `symbol` on session `day` (a REACT row's base, when the lane holds no bar of it)."""
        try:
            got = self.market.bars([symbol], timeframe="1Day", start=day.isoformat(),
                                   end=(day + dt.timedelta(days=1)).isoformat(), adjustment="raw") or {}
        except Exception:  # noqa: BLE001
            return None
        for r in got.get(symbol) or []:
            if _bar_day(r) == day.isoformat():
                close = A.dec(r.get("c"))
                return float(close) if close is not None and close > 0 else None
        return None

    def _event_minute_close(self, symbol: str, session: Any, *, until: float | None = None) -> float | None:
        """The T29 minute close of `symbol` in `session` (a REACT row's reaction, when the lane stored no mark): the SIP
        1-minute bars of the session to T29's end, read through the plan's SIP window; None, unread, at or after the
        window's last minute (`until` less `EVENT_MINUTE_STOP_S`, release 1019b's third review)."""
        if self._event_minute_late(until):
            return None
        adapter = self._event_adapter()
        start = session.open_at.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        end = (adapter.t29(session) + dt.timedelta(minutes=1)).astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        try:
            got = self.market.bars([symbol], timeframe="1Min", start=start, end=end, adjustment="raw") or {}
        except Exception:  # noqa: BLE001
            return None
        return adapter.minute_close(got.get(symbol) or [], session)

    #: THE T29 MINUTES OF A CLOSE DECISION, read together (release 1019b's review): this many names a request, over the
    #: last `EVENT_MINUTE_SPAN_S` seconds to T29's end (one page of 1-minute bars); a name with no trade in that span is
    #: read again over its whole session, together too. Its close is the same as one read of its whole session gives.
    EVENT_MINUTE_BATCH = 200
    EVENT_MINUTE_SPAN_S = 1800
    #: THE T29 READS END BEFORE THE WINDOW'S LAST MINUTE (release 1019b's third review): no T29 request is started, and
    #: none is sent again, once the wall clock is within this many seconds of the window's cut-off (`until`, 15:49 ET
    #: at a full day's close), and a request that ran into its timeout is never sent again; what is not read by then is
    #: unread (a REACT row of it is not taken). The decision, then the auction's buys, keep the last minute.
    EVENT_MINUTE_STOP_S = 60.0

    def _event_minute_late(self, until: float | None) -> bool:
        """Whether the T29 reads of a decision whose window ends at `until` are over (`EVENT_MINUTE_STOP_S`)."""
        return until is not None and self.clock() >= float(until) - self.EVENT_MINUTE_STOP_S

    def _event_minute_closes(self, symbols: Sequence[str], session: Any, *, failed: list[str] | None = None,
                             until: float | None = None) -> dict[str, float | None]:
        """{symbol: the T29 minute close in `session`} for many names at once (`book.reaction_reader`'s
        `minutes_many`): SIP 1-minute bars, `EVENT_MINUTE_BATCH` names a request; None for a name with no bar, or whose
        read failed (nothing is read again name by name). A request that fails is sent again once (release 1019b's
        second review), never after a timeout and never in the window's last minute; no request starts in that minute
        (`until`, release 1019b's third review). A chunk not read says why in `failed`: the decision that asked then
        takes no REACT row of those names (`_event_decide`: every other pick goes)."""
        adapter = self._event_adapter()
        names = sorted({str(x).upper() for x in symbols if x})
        t29 = adapter.t29(session)
        stamp = lambda t: t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")  # noqa: E731
        end = stamp(t29 + dt.timedelta(minutes=1))
        narrow = max(session.open_at, t29 - dt.timedelta(seconds=self.EVENT_MINUTE_SPAN_S))
        out: dict[str, float | None] = {}

        def read(chunk: list[str], start: dt.datetime) -> Mapping[str, Any] | None:
            if self._event_minute_late(until):
                if failed is not None:
                    failed.append(f"the T29 minutes of {len(chunk)} names were not read: the close window's last "
                                  f"minute had begun")
                return None
            error: BaseException | None = None
            for attempt in range(2):
                if attempt and (_timed_out(error) or self._event_minute_late(until)):
                    break   # (never again after a timeout, nor in the window's last minute)
                try:
                    return self.market.bars(chunk, timeframe="1Min", start=stamp(start), end=end, adjustment="raw") or {}
                except Exception as exc:  # noqa: BLE001 - read again once, then unread (said in `failed`)
                    error = exc
            if failed is not None:
                failed.append(f"the T29 minutes of {len(chunk)} names could not be read: {type(error).__name__}: "
                              f"{str(error)[:120]}")
            return None

        quiet: list[str] = []
        for i in range(0, len(names), self.EVENT_MINUTE_BATCH):
            chunk = names[i:i + self.EVENT_MINUTE_BATCH]
            got = read(chunk, narrow)
            for name in chunk:
                px = None if got is None else adapter.minute_close(got.get(name) or [], session)
                out[name] = px
                if px is None and got is not None and narrow > session.open_at:
                    quiet.append(name)
        for i in range(0, len(quiet), self.EVENT_MINUTE_BATCH):
            chunk = quiet[i:i + self.EVENT_MINUTE_BATCH]
            got = read(chunk, session.open_at)
            if got is not None:
                for name in chunk:
                    out[name] = adapter.minute_close(got.get(name) or [], session)
        return out

    def _event_publish(self, day: dt.date, adapter: Any, lane: Any, out: dict) -> bool:
        """THE ELIGIBLE LIST of `day` at the gateway (`book.publish`), sent when the gateway's copy is not today's or the
        lane's universe of the day has grown since; kept in kv `eq_event_list` {day, sha, count, at}. False when it
        could not be sent (the buys wait; the next minute sends it again)."""
        symbols = adapter.eligible(lane, day)
        sha = hashlib.sha256(f"{day.isoformat()}:{','.join(symbols)}".encode()).hexdigest()
        held = self.state.get("eq_event_list") or {}
        if held.get("day") == day.isoformat() and held.get("sha") == sha:
            return True
        client = getattr(self.account, "client", None)
        answer = adapter.publish(client, day, symbols) if client is not None else {"ok": False, "error": "no client"}
        if answer.get("ok"):
            self.state.put("eq_event_list", {"day": day.isoformat(), "sha": sha, "count": len(symbols),
                                             "at": self.clock()})
            return True
        out["event_list"] = str(answer.get("error"))[:200]
        return False

    # ---------------------------------------------------------------- the exits and their ladder
    def _event_exits(self, em: S.EventMoments, at: str, adapter: Any) -> int:
        """THE EXITS DUE AT THIS AUCTION: every open event lot whose plan (`info.evl_exit`: day, at, rung) names it, and
        that has no exit planned or working, gets a sale intent (a house_exit tagged `book.EXIT_TAG`) with its side row:
        a market-on-open or market-on-close sale of what it holds. Returns how many."""
        day = em.day.isoformat()
        n = 0
        with self.state.transaction():
            for lot in self._lots():
                if lot.lane != EVENT_LANE or self._exit_pending(lot.lid):
                    continue
                plan = lot.info.get("evl_exit") if isinstance(lot.info.get("evl_exit"), Mapping) else None
                if plan is None:
                    plan = {"day": day, "at": "close", "rung": 0}   # a lot with no plan of its own: out at this close
                    lot.info["evl_exit"] = plan
                    self._save_lot(lot)
                if plan.get("day") != day or plan.get("at") != at:
                    continue
                evl = lot.info.get("evl") if isinstance(lot.info.get("evl"), Mapping) else {}
                iid = self._next("eq_intents", "iid")
                now = self.clock()
                rung = int(plan.get("rung") or 0)
                intent = Intent(iid, lot.instance, lot.family, lot.version, day, day, at, "house_exit", "planned",
                                symbol=lot.symbol, lid=lot.lid, tag=adapter.EXIT_TAG,
                                why=f"the event lot's scheduled exit at the {at} (rung {rung} of the ladder)",
                                created_at=now, updated_at=now)
                self._save_intent(intent)
                self.state.upsert("eq_event_intents", {
                    "iid": iid, "program": lot.family, "version": lot.version, "event": str(evl.get("event") or ""),
                    "side": "sell", "band": evl.get("band"), "tif": "opg" if at == "open" else "cls", "otype": "market",
                    "symbol": lot.symbol,
                    "cik": evl.get("cik"), "day": day, "at": at, "rank_key": None, "adv20": None, "prev_close": None,
                    "limit_px": "0", "sigma": None, "hold": None, "weight": str(evl.get("weight") or EVENT_STRICT_WEIGHT),
                    "exit_day": None, "exit_at": None, "lid": lot.lid, "rung": rung,
                    "decided_at": _iso(em.open_decide if at == "open" else em.close_decide), "why": None,
                    "created_at": now}, "iid")
                n += 1
        return n

    def _event_ladder(self, lot: Lot, why: str, adapter: Any) -> None:
        """THE FALLBACK LADDER (PREREG-EVL-1 section 5, PREREG-EVL-2's open exits alike): a sale its auction did not
        fill (no print, a halt, a refusal, or no sale sent at all) goes at the closing cross of the next session, and of
        each next one, `book.LADDER_CLOSES` in all; then at the first trade of the next session: a day sale in the open
        window by the normal exit path (`LATE_TAG`, carried each session after until it fills). Never written down:
        alarmed (a warning on the first rung, an error on the late one)."""
        plan = dict(lot.info.get("evl_exit") or {})
        rung = int(plan.get("rung") or 0) + 1
        base = dt.date.fromisoformat(str(plan.get("day") or S.ny_day(self.clock()).isoformat()))
        first = str(plan.get("first") or base.isoformat())      # (the planned exit's session: the ladder counts from it)
        nxt = S.next_session(base)
        if rung <= adapter.LADDER_CLOSES:
            lot.info["evl_exit"] = {"day": nxt.isoformat(), "at": "close", "rung": rung, "first": first, "why": why[:200]}
            self._save_lot(lot)
            self.alert("warning", f"equity: event lot {lot.lid} ({lot.symbol}) was not sold at its auction ({why[:160]}): "
                                  f"it goes at the closing cross of {nxt.isoformat()} (rung {rung} of the ladder)")
            return
        lot.info["evl_exit"] = {"day": nxt.isoformat(), "at": "late", "rung": rung, "first": first, "why": why[:200]}
        self._save_lot(lot)
        self._plan_exit(lot, exec_day=nxt.isoformat(), at="open", reason=adapter.LATE_TAG,
                        why=f"no closing cross sold it in {adapter.LADDER_CLOSES} sessions: a day sale in the open window "
                            f"(PREREG-EVL-1 section 5: the first trade of the next session)", decided_day=base.isoformat())
        self.alert("error", f"equity: event lot {lot.lid} ({lot.symbol}) found no closing cross in "
                            f"{adapter.LADDER_CLOSES} sessions: it is sold by a day order in the open window of "
                            f"{nxt.isoformat()} and each session after until it fills; look at the name")

    def _event_finish(self, now: float, em: S.EventMoments, adapter: Any, out: dict) -> None:
        """THE AUCTIONS' ENDS: every event intent of an auction that has passed (and `EVENT_SETTLE_S` more), its orders
        no longer working, is finished: a buy "done" when it filled, "missed" when not (an auction order does not fill
        above its limit, nor with no print); a sale "done" when its lot is sold, else "missed" and the lot climbs the
        ladder (`_event_ladder`). A lot whose planned auction passed with no sale planned at all climbs it too. A buy
        whose order the venue cancelled at once (A80) says so on its end, with its one re-send's outcome or why that
        re-send did not go (`venue_cancel_note`); once the session's close has ended, A80's one alert of the session
        (`_venue_cancel_said`)."""
        today = em.day.isoformat()

        def passed(day: str, at: str) -> bool:
            if day < today:
                return True
            if day > today:
                return False
            return now >= (em.open_at if at == "open" else em.close_at) + self.EVENT_SETTLE_S

        if not _has_table(self.state.rows, "eq_event_intents"):
            return
        rows = self.state.rows("SELECT i.*, e.side AS e_side, e.day AS e_day, e.at AS e_at, e.lid AS e_lid FROM "
                               "eq_intents i JOIN eq_event_intents e ON e.iid=i.iid WHERE i.status IN ('planned', 'sent') "
                               "ORDER BY i.iid")
        for r in rows:
            if not passed(str(r["e_day"]), str(r["e_at"])):
                continue
            intent = Intent.of(r)
            orders = self._intent_orders(intent.iid)
            if any(o.working for o in orders):
                continue    # the venue ends an auction order at its auction: its last status is a reading away
            filled = sum((o.filled_qty for o in orders), ZERO)
            if r["e_side"] == "buy":
                last = orders[-1] if orders else None
                cause = (last.answer.get("reject_reason") or last.answer.get("error") or "") if last is not None else ""
                note = venue_cancel_note(orders, intent.why)     # (A80: "" unless the venue cancelled one at once)
                self._finish(intent, "done" if filled > 0 else "missed",
                             f"filled {qty_text(filled)} shares at the {r['e_at']}{' (' + note + ')' if note else ''}"
                             if filled > 0 else
                             f"not filled at the {r['e_at']} auction ({last.status if last is not None else 'never sent'}"
                             f"{': ' + str(cause)[:160] if cause else ''}"
                             f"{': ' + intent.why if intent.why and last is None else ''}"
                             f"{'; ' + note if note else ''})")
                continue
            lot = self._lot(r["e_lid"])
            if lot is None or lot.status == LOT_CLOSED or lot.qty <= 0:
                self._finish(intent, "done", "the lot is sold")
                continue
            why = (f"the {r['e_at']} auction sold {qty_text(filled)} of it" if orders else
                   f"no sale was sent ({intent.why or 'the window passed'})")
            with self.state.transaction():
                self._finish(intent, "missed", why)
                self._event_ladder(lot, why, adapter)
        for lot in self._lots():
            if lot.lane != EVENT_LANE:
                continue
            plan = lot.info.get("evl_exit") if isinstance(lot.info.get("evl_exit"), Mapping) else None
            if plan is not None and plan.get("at") == "late":
                self._event_zero(lot, plan, now, em, adapter)
                continue
            # A lot whose planned auction passed with no sale planned at all (the House was down at its decision).
            if plan is None or self._exit_pending(lot.lid) or not passed(str(plan.get("day")), str(plan.get("at"))):
                continue
            with self.state.transaction():
                self._event_ladder(lot, "no sale was planned at its auction (the House missed its decision)", adapter)
        if passed(today, "close") and self._venue_said != today:
            self._venue_cancel_said(today)

    def _venue_cancel_said(self, day: str) -> None:
        """A80'S ONE ALERT OF A SESSION (info), once the session's close has ended (`_event_finish`): how many of the
        day's event buys the venue cancelled at once (an intent counted once), how many went again and how many of
        those filled; with an `equity.alert` record of the counts. Said only on a day with such a cancel (kv
        `VENUE_CANCEL_SAID`, written only then); a day with none is read once a process (`_venue_said`) and leaves no
        trace."""
        self._venue_said = day
        if self.state.get(VENUE_CANCEL_SAID) == day:
            return
        by_intent: dict[int, list[Order]] = {}
        for r in self.state.rows("SELECT * FROM eq_orders WHERE day=? AND side='buy' AND tif IN ('opg', 'cls') AND "
                                 "iid IS NOT NULL ORDER BY eid", (day,)):
            o = Order.of(r)
            by_intent.setdefault(int(o.iid), []).append(o)
        cut = went = filled = 0
        for orders in by_intent.values():
            cancels = venue_cancels(orders)
            if not cancels:
                continue
            cut += 1
            first = cancels[0][0].eid
            if any(o.eid > first and o.status != "refused" for o in orders):
                went += 1
                filled += int(sum((o.filled_qty for o in orders), ZERO) > 0)
        if not cut:
            return
        self.state.put(VENUE_CANCEL_SAID, day)
        what = (f"A80: the venue cancelled {cut} event buy{'' if cut == 1 else 's'} of {day} at once (within "
                f"{VENUE_CANCEL_RETRY_S} s of {'its' if cut == 1 else 'their'} submission, nothing filled); "
                f"{went} went again once ({filled} filled), {cut - went} did not (the window's cut-off or a gate)")
        self.record("equity.alert", {"what": what, "day": day, "venue_cancels": cut, "resent": went, "filled": filled})
        self.alert("info", f"equity: {what}")

    def _event_zero(self, lot: Lot, plan: Mapping[str, Any], now: float, em: S.EventMoments, adapter: Any) -> None:
        """PREREG-EVL-1 section 5's LAST RUNG: a lot still held when the `book.ZERO_AFTER`th session after its planned
        exit has closed is AT 0 for the loss budget (`event_lot_weight` 1: its whole value counts as lost), once, with an
        error alert; its day sale goes on each session (real shares are never written off the account)."""
        if plan.get("zero"):
            return
        try:
            gone = S.sessions_between(str(plan.get("first") or plan.get("day")), em.day)
        except (TypeError, ValueError):
            return
        if gone < adapter.ZERO_AFTER or (gone == adapter.ZERO_AFTER and now < em.close_at):
            return
        with self.state.transaction():
            lot.info["evl_exit"] = {**dict(plan), "zero": em.day.isoformat()}
            self._save_lot(lot)
        self.record("equity.alert", {"what": f"event lot {lot.lid} is at 0 for the loss budget: unsold "
                                             f"{adapter.ZERO_AFTER} sessions after its planned exit", "lots": [lot.lid]})
        self.alert("error", f"equity: event lot {lot.lid} ({lot.symbol}) is still held {adapter.ZERO_AFTER} sessions after "
                            "its planned exit: the loss budget now counts its whole value as lost (PREREG-EVL-1 section "
                            "5, at 0 after 20 sessions); its day sale goes on each session. Look at the name.")

    # ---------------------------------------------------------------- the sends
    def _event_send(self, now: float, em: S.EventMoments, at: str, s: Any, adapter: Any,
                    real_block: Callable[..., str | None], killed: Callable[[], bool], out: dict,
                    sides: Sequence[str] = ("sell", "buy")) -> None:
        """THE AUCTION'S SENDS, every minute of its window: the sales first, then the buys in the tables' order and
        each program's rank; a send refused by a reading the gateway could not make goes again next minute; nothing goes
        at or after the window's cut-off (`_send`'s wall clock). `sides`: the sales alone (sent before the auction's
        decision, `_event_step`), the buys alone (after it), or both."""
        day = em.day.isoformat()
        rows = self.state.rows("SELECT i.*, e.side AS e_side, e.band AS e_band FROM eq_intents i JOIN eq_event_intents e "
                               "ON e.iid=i.iid WHERE i.status IN ('planned', 'sent') AND e.day=? AND e.at=? ORDER BY i.iid",
                               (day, at))
        sells = [r for r in rows if r["e_side"] == "sell"] if "sell" in sides else []
        # ROOM (PREREG-EVL-3 section 2): Sized programs' buys first, then Probe's, then learning's; within Sized and
        # within Probe ROUND-ROBIN (A85, `book.send_key`: every program's first buy, in the tables' order, before any
        # program's second); learning in the tables' order; within a program its own ranking (the decision planned
        # them in it, so its iids are in it).
        buys = []
        if "buy" in sides:
            nth: dict[str, int] = {}
            ranked = []
            for r in sorted((r for r in rows if r["e_side"] == "buy"), key=lambda r: int(r["iid"])):
                n = nth.get(str(r["family"]), 0)
                nth[str(r["family"])] = n + 1
                ranked.append(((*adapter.send_key(r["family"], r["e_band"], n), int(r["iid"])), r))
            buys = [r for _, r in sorted(ranked, key=lambda pair: pair[0])]
        until = em.open_until if at == "open" else em.close_until
        for r in sells + buys:
            try:
                side = self._event_row(r["iid"])
                if r["e_side"] == "sell":
                    self._event_work_exit(Intent.of(r), side, now, day, at, until, killed)
                else:
                    self._event_work_entry(Intent.of(r), side, now, day, at, until, s, adapter, real_block, killed, out)
            except Exception as exc:  # noqa: BLE001 - the next intent goes on
                self._error(f"event {r['e_side']} {r['iid']}", exc, out)

    def _event_last(self, intent: Intent, *, entry: bool = False) -> tuple[Order | None, bool]:
        """(the intent's last order, whether a new one may go now): none yet, or the last one refused with nothing sent
        (`again`); never while one may still fill or after a final answer. THE CAPTAIN'S A80 (`entry`: an event BUY's
        orders; `_event_work_entry` alone asks it): a last order THE VENUE cancelled at once (`venue_cancel_ms`: within
        `VENUE_CANCEL_RETRY_S` of its own submission, nothing filled) may go again, ONCE: only when no earlier order of
        the intent was cancelled so, so at most two orders of an intent come from venue cancels (a re-send the gateway
        refused with nothing sent goes again by `again`, as any refusal of a reading, and stays the one re-send). An
        exit's last order is read as before: a sale the venue cancelled is never sent again here (the ladder carries
        it)."""
        orders = self._intent_orders(intent.iid)
        current = orders[-1] if orders else None
        if current is None:
            return None, True
        if entry and current.status == "canceled":
            cancels = venue_cancels(orders)
            return current, len(cancels) == 1 and cancels[0][0].eid == current.eid
        if current.working or current.status in ("filled", "canceled", "expired"):
            return current, False
        return current, current.again

    def _event_work_exit(self, intent: Intent, side: Mapping[str, Any] | None, now: float, day: str, at: str,
                         until: float, killed: Callable[[], bool]) -> None:
        """One event SALE at its auction: a market-on-open or market-on-close sale of what the lot holds. Exits wait on
        the kill switch alone (the gateway stops sales too), one working order a symbol and the House-wide order count;
        never on the switch of the kind, a seat, a proof or the minimum hold."""
        lot = self._lot((side or {}).get("lid") or intent.lid)
        if lot is None or lot.status == LOT_CLOSED or lot.qty <= 0:
            self._finish(intent, "done", "the lot is sold")
            return
        current, may = self._event_last(intent)
        if not may:
            return
        try:
            stopped = bool(killed())
        except Exception:  # noqa: BLE001 - unreadable counts as engaged
            stopped = True
        if stopped:
            intent.why = "the gateway's kill switch is engaged (it blocks sells too)"
            self._save_intent(intent)
            return
        tif = "opg" if at == "open" else "cls"
        why = self._symbol_busy(lot.symbol, auction_sale=(day, tif)) or self._count_refusal(day, exit_=True)
        if why:
            intent.why = why
            self._save_intent(intent)
            return
        qty = lot.qty.to_integral_value(rounding=ROUND_DOWN) if lot.qty >= 1 else lot.qty
        self._send(intent, side="sell", symbol=lot.symbol, klass=lot.klass, qty=qty, limit=ZERO, collar=0, day=day,
                   lid=lot.lid, replaces=current.eid if current is not None else None, probe=lot.probe,
                   why=f"event exit at the {at} (market-on-{at}, rung {int((side or {}).get('rung') or 0)})",
                   at=at, tick=now, until=until, tif=tif, otype="market")

    def _event_work_entry(self, intent: Intent, side: Mapping[str, Any] | None, now: float, day: str, at: str,
                          until: float, s: Any, adapter: Any, real_block: Callable[..., str | None],
                          killed: Callable[[], bool], out: dict) -> None:
        """One event BUY at its auction: every gate of a real equity open (`_open_block`: the House's, the kind's switch,
        the auction proof, the freezes, the program's band), the day's eligible list at the gateway, no sale of the name
        at this auction (an exit never waits on an entry: release 1019b's second review; a sale whose send the gateway
        refused for a reading it could not make, a 424 or 409, goes again next minute, and a buy of the name sent in
        between would hold it to the cut-off), one working order a symbol, the day's order count, the program's room,
        then `_size_event`'s whole shares at the limit. THE CAPTAIN'S A80: a buy whose order the venue cancelled at once
        (`_event_last`) goes again ONCE through all of it, the same symbol, side, size rule, limit, time in force and
        type under a new client id, while its window is open (`_send`'s wall clock); the re-sent order's why says so and
        how many ms the venue took, the minute counts it (`out["venue_cancel_resends"]`), and a gate that holds it
        says so on the intent (`A80_HELD`), which the auction's end reads back."""
        if side is None:
            self._finish(intent, "refused", "an event buy with no side row")
            return
        current, may = self._event_last(intent, entry=True)
        if not may:
            self._event_final(intent, current)
            return
        # A80: an order of this buy the venue cancelled at once makes this send its one re-send (or that re-send again,
        # after a gateway refusal of a reading with nothing sent).
        cancels = venue_cancels(self._intent_orders(intent.iid)) if current is not None else []
        resend = cancels[0] if cancels else None
        held = A80_HELD if resend is not None else ""
        inst = self._instance(intent.instance)
        why = self._open_block(real_block, inst, killed)
        if why is None:
            lane = self._event_lane_store()
            if lane is None or not self._event_publish(dt.date.fromisoformat(day), adapter, lane, out):
                why = "the day's eligible list is not at the gateway yet"
        if why is None and self._event_sales_at(day, at, str(intent.symbol).upper()):
            why = f"a sale of {intent.symbol} is planned or working at this {at} auction: no buy of it goes in the same cross"
        if why is None:
            why = self._symbol_busy(str(intent.symbol)) or \
                self._count_refusal(day, exit_=False, event_line=int(s.max_orders_day))
        if why is None and self._event_open_count(intent.instance) > s.max_open(inst.band):
            why = f"the program holds and has on order more than its {s.max_open(inst.band)} positions"
        if why:
            why = held + why
            if intent.why != why:
                intent.why = why
                self._save_intent(intent)
            return
        limit = D(side["limit_px"], ZERO)
        if limit <= 0:
            self._finish(intent, "refused", "no limit price")
            return
        sized = self._size_event(intent, inst, side, limit, day, s)
        if sized is None:
            self._resend_held(intent, held)
            return
        qty, why = sized
        if qty < 1:
            self._finish(intent, "refused", f"sizing: {why}" + (
                f" (A80's one re-send of the buy the venue cancelled {resend[1]} ms after its submission)"
                if resend is not None else ""))
            return
        lead = "" if resend is None else (f"A80's one re-send (the venue cancelled the first buy {resend[1]} ms after "
                                          "its submission, nothing filled): ")
        order = self._send(intent, side="buy", symbol=str(intent.symbol), klass=config.STOCK, qty=qty, limit=limit,
                           collar=0, day=day, lid=None, replaces=current.eid if current is not None else None,
                           probe=inst.band != "sized", why=f"{lead}event entry at the {at} ({why})"[:300], at=at,
                           tick=now, until=until, tif="opg" if at == "open" else "cls", otype="limit")
        if order is None:
            self._resend_held(intent, held)     # (the window's cut-off passed on the wall clock: nothing was written)
        elif resend is not None:
            out["venue_cancel_resends"] = int(out.get("venue_cancel_resends") or 0) + 1
        if order is not None and order.status == "refused" and order.answer.get("cap") == "stock_eligible":
            # The gateway holds no eligible list of the day (lost or replaced): the list is published again before the
            # buy goes again next minute (kv `eq_event_list` said it was there).
            self.state.put("eq_event_list", {})
        self._event_final(intent, order)

    def _resend_held(self, intent: Intent, held: str) -> None:
        """A80: the why a wait wrote on the intent (`_size_event`'s, `_send`'s cut-off), marked as holding the buy's one
        re-send (`held`, `A80_HELD`; nothing when this send is no re-send)."""
        if held and not intent.why.startswith(held):
            intent.why = held + intent.why
            self._save_intent(intent)

    def _event_final(self, intent: Intent, current: Order | None) -> bool:
        """Whether an event buy's last order has its FINAL answer short of a fill (the venue rejected it, it was lost,
        or the gateway refused it for a cap that is no reading it could not make): the intent ends at once in the
        answer's words, as `_work_entry`'s does, not at the auction's end (an A80 re-send's end names the venue's cancel
        it followed: `venue_cancel_note`)."""
        if current is None:
            return False
        if not (current.status in ("rejected", "lost") or (current.status == "refused" and not current.again)):
            return False
        self._event_refused_at_gateway(intent, current)     # (release 1019f: the record's binding "gateway")
        cause = current.answer.get("reject_reason") or current.answer.get("error") or current.answer.get("lookup")
        note = venue_cancel_note(self._intent_orders(intent.iid))
        self._finish(intent, "refused" if current.status == "refused" else "missed",
                     f"the {current.status} buy: {cause}" + (f" ({note})" if note else ""))
        if current.answer.get("cap") == "stock_event_buys" and self.state.get("eq_event_off_said") != intent.exec_day:
            # The gateway's own switch is the owner's step at the first Probe (operations.md): said once a session.
            self.state.put("eq_event_off_said", intent.exec_day)
            self.alert("error", f"equity: the gateway refused the real event buy of {intent.family} ({intent.symbol}): "
                                "STOCK_EVENT_BUYS is off. Owner step: set it on in gateway/wrangler.jsonc and deploy the "
                                "gateway, or set equity_money.event.enabled False to stop the House asking")
        return True

    def _event_refused_at_gateway(self, intent: Intent, current: Order) -> None:
        """RELEASE 1019f, THE PROBE SIZE'S RECORD: an event buy whose last order the GATEWAY refused with its final answer
        (a cap that is no reading it could not make: nothing reached the venue) is recorded as cut by it, `binding`
        "gateway" on its side row, whatever its sizing named; its `target_usd` stays the sizing's. The House's own
        refusals (nothing sent) and the venue's rejections are not the gateway's."""
        if current.status != "refused" or current.again or not current.answer.get("gateway"):
            return
        side = self._event_row(intent.iid)
        if side is None or "binding" not in side or side.get("binding") == "gateway":
            return
        self.state.execute("UPDATE eq_event_intents SET binding='gateway' WHERE iid=?", (int(intent.iid),))

    def _size_event(self, intent: Intent, inst: Instance, side: Mapping[str, Any], limit: Decimal, day: str,
                    s: Any) -> tuple[Decimal, str] | None:
        """THE EVENT ENTRY'S SIZE (PREREG-EVL-3 section 2, PREREG-EVL-1 section 8), by `sizing.size_entry` (the one
        sizing function): a target of the band's `position_share` x E at the limit (learning 0.02, Probe 0.05, Sized
        0.10), E the account equity at the previous close (`last_equity`, never above the House's sizing equity), every
        wall a cap (the name's book-wide 10%, `per_name_share`; the 100% book; the House-wide cash; the loss budget at
        the lot's own weight), then WHOLE shares (floored); when that rounds to none, ONE share when one share passes
        every cap and, at learning, one share at the limit is at most `one_share_max.learning` x E; (0, why) otherwise
        (skipped: the shadow keeps the event). A LEARNING buy, and any buy of a lower ROOM tier (a birth's, R3: after
        every PREREG program whatever its band), sizes on the cash, the invested room and the loss budget less THE NEXT
        AUCTION'S RESERVATION (the captain's A85, `_event_reserve`: what the other auction's PREREG Probe and Sized
        programs will need, less what this auction's event sales give back; no wall moves, the reservation only makes
        such a buy smaller); 0 while no PREREG program of the other auction is at Probe or Sized, so learning sizes as
        before. None (the intent's why) when a figure cannot be read this minute (asked again next minute until the
        cut-off). RELEASE 1019f: the name's 10% (`instrument`), the program's own share of it (`sleeve_cap`) and the 100%
        book are judged on `wall_equity` (the lower of E and the account's current equity, the gateway's figure: the
        reading that trades less); the target and the one-share rule stay on E. Every answer is RECORDED on the buy's
        side row (`_event_sized`): the target's dollars, the constraint that cut it (a cut by A85's reservation reads as
        the cap it lowered: cash, invested or budget) and the dollars the send asks."""
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
        last = A.dec(account.get("last_equity"))
        if last is not None and last > 0:
            E = min(E, last)      # the equity at the previous close (PREREG-EVL-3 section 2); never above the House's
        walls = wall_equity(E, account)     # (release 1019f: the walls' equity, the gateway's current one when lower)
        try:
            cash = D(account.get("cash"))
            options_loss = self._options_open_loss(day)
            reserved = Decimal(str(self.options_book.reserved())) if self.options_book is not None else ZERO
            available = M.available_cash(account, working_buys_worst=working_buys_worst(self.state.rows), reserved=reserved,
                                         reserve_usd=et.cash_reserve)
            budget_room = self._budget_room(day)
            # (A85: a learning buy leaves the next auction's Probe and Sized programs their cash, invested room and loss
            # budget; zero for a Probe or Sized buy, and while no program of the other auction is at either band.)
            held_cash, held_risk, held_note = self._event_reserve(inst, day, str(side.get("at") or intent.at), s, E)
            available -= held_cash
            budget_room -= held_risk
        except Exception as exc:  # noqa: BLE001 - fail closed
            wait(f"a sizing figure could not be read ({type(exc).__name__}: {str(exc)[:120]})")
            return None
        symbol = str(intent.symbol)
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
        own_symbol = sum((lot.value for lot in self._lots(instance=inst.id, symbol=symbol)), ZERO)
        weight = _event_weight_of(side.get("weight"))
        target = s.share(inst.band) * E
        x = Z.SizingInputs(symbol=symbol, klass=config.STOCK, share=None, usd=target, limit_price=limit,
                           E=walls, sleeve_equity=walls, sleeve_free_cash=max(ZERO, available),
                           sleeve_symbol_value=own_symbol,
                           position_share=s.per_name, account_symbol_value=max(book_symbol, account_symbol) + all_buys_symbol,
                           invested_now=invested(self.state.rows) + options_loss + held_cash,
                           invested_share=Decimal(str(et.invested_share)), available_cash=available, cash=cash,
                           any_short=any_short, budget_room=budget_room, weight=weight,
                           min_order_usd=Decimal(str(et.min_order_usd)))
        sized = Z.size_entry(x)
        whole = sized.qty.to_integral_value(rounding=ROUND_DOWN)
        if whole >= 1:
            self._event_sized(intent, side, target, self._event_cut(x, sized, whole * limit < target), whole * limit)
            return whole, f"{whole} shares at {inst.band} ({sized.binding}): {sized.reason}{held_note}"
        cap = s.one_share_cap(inst.band)
        if cap is not None and limit > cap * E:
            self._event_sized(intent, side, target, None, ZERO)
            return ZERO, (f"no whole share fits: the {inst.band} target rounds to none and one share at ${limit} is above "
                          f"{cap} x E (${(cap * E).quantize(Decimal('0.01'))})")
        one = Z.size_entry(replace(x, usd=limit))
        if one.qty >= 1:
            self._event_sized(intent, side, target, None, limit)
            return Decimal(1), (f"one share at {inst.band}: the target's whole shares round to none and one share fits "
                                f"every wall ({one.reason}){held_note}")
        self._event_sized(intent, side, target, self._event_cut(replace(x, usd=limit), one, False), ZERO)
        return ZERO, f"no whole share fits ({one.binding}): {one.reason}{held_note}"

    def _event_reserve(self, inst: Instance, day: str, at: str, s: Any, E: Decimal) -> tuple[Decimal, Decimal, str]:
        """THE NEXT AUCTION'S RESERVATION FOR A LEARNING BUY (the captain's A85, recorded before the first Probe auction;
        PREREG-EVL-3 section 2's ROOM, which A83 (2)(b) read as holding inside one auction only): (cash, loss budget,
        the note its sizing reason carries). The book is 1x cash and every buy holds its limit; a lot sold in an auction
        still holds its cash in that auction; so a learning lot bought at this auction (`at` of `day`) holds cash at
        the NEXT one, the other auction. For every live program at Probe or Sized whose entry is that other auction
        (`book.reservation`): its room there, `max_open(band)` less what it holds and has on order, its lots whose sale
        is planned or working at THIS auction not counted (they are sold before it; `_event_open_count` less
        `_event_selling`); the counts of its real-money picks at its last `book.RESERVE_DECISIONS` decisions of that
        auction (`eq_event_decisions` summaries, `picks`; a decision that did not read them, its room full, is passed
        over) and the weights of its buys there. The reservation is n = min(room, median picks) x share(band) x E for
        cash and invested room, and that x the median weight for the loss budget, LESS what this auction's event sales
        give back by the next one (each lot sold here: its value, and its value x its own weight for the budget), never
        below 0. (0, 0, "") for a Probe or Sized buy, a kind that is not the event kind, and while no program of the
        other auction is at Probe or Sized: learning sizes exactly as it did. WITH R3'S BIRTHS (release 1019f's
        integration; `book.BIRTH_ROOM`: a birth comes after every PREREG program whatever its band): the programs
        reserved for are the PREREG programs at Sized or Probe only (`book.reserved_for`; a birth is learning at birth,
        and a promoted birth keeps its own ROOM tier, after them all), and the buys that leave the reservation are a
        PREREG learning program's and a birth's at any band (`book.leaves_room`: every tier after the PREREG Probe
        tier)."""
        if inst.kind != EVENT_KIND or inst.band not in EVENT_LIVE_BANDS:
            return ZERO, ZERO, ""
        adapter = self._event_adapter()
        if adapter is None:
            raise RuntimeError("the event adapter (league/events/book.py) cannot be imported")
        if not adapter.leaves_room(inst.family, inst.band):
            return ZERO, ZERO, ""
        other = "close" if at == "open" else "open"
        rows: list[dict[str, Any]] = []
        names: list[str] = []
        for o in self._instances(alive=True):
            if o.kind != EVENT_KIND or not o.live or o.band not in adapter.PROBE_UP or \
                    not adapter.reserved_for(o.family, o.band):
                continue
            program = adapter.program_of(o.family, o.version)
            if program is None or program.entry_at != other:
                continue
            holds = self._event_open_count(o.id) - self._event_selling(o.id, day, at)
            picks, weights = self._event_recent(o, other, adapter.RESERVE_DECISIONS)
            rows.append({"program": o.family, "band": o.band, "room": s.max_open(o.band) - holds, "picks": picks,
                         "weights": weights})
            names.append(o.family)
        if not rows:
            return ZERO, ZERO, ""
        cash, risk = adapter.reservation(rows, s, E)
        back_cash, back_risk = self._event_given_back(day, at)
        held_cash, held_risk = max(ZERO, cash - back_cash), max(ZERO, risk - back_risk)
        if held_cash <= 0 and held_risk <= 0:
            return ZERO, ZERO, ""
        cent = Decimal("0.01")
        note = (f"; A85 holds ${held_cash.quantize(cent)} of cash and invested room and ${held_risk.quantize(cent)} of "
                f"the loss budget for the {other}'s Probe and Sized programs ({', '.join(names)[:160]}): their "
                f"${cash.quantize(cent)} less ${back_cash.quantize(cent)} this auction's sales give back")
        return held_cash, held_risk, note

    def _event_selling(self, key: str, day: str, at: str) -> int:
        """An event program's open lots whose sale is planned or working at this auction (`day`, `at`)."""
        return int(self.state.rows(
            "SELECT COUNT(DISTINCT l.lid) AS n FROM eq_lots l JOIN eq_event_intents e ON e.lid=l.lid JOIN eq_intents i ON "
            "i.iid=e.iid WHERE l.instance=? AND l.status IN ('open', 'closing') AND e.side='sell' AND e.day=? AND e.at=? "
            "AND i.status IN ('planned', 'sent')", (key, day, at))[0]["n"])

    def _event_recent(self, inst: Instance, at: str, n: int) -> tuple[list[int], list[Decimal]]:
        """(the counts of the program's real-money picks at its last `n` decisions of auction `at` that read them, the
        latest first; the open-risk weights of its buys planned at those decisions), from `eq_event_decisions`' summaries
        (`programs.<program>.picks`, written by `_event_decide`) and `eq_event_intents`."""
        counts: list[int] = []
        days: list[str] = []
        for r in self.state.rows("SELECT day, summary FROM eq_event_decisions WHERE at=? AND status='done' ORDER BY day "
                                 "DESC LIMIT 60", (at,)):
            summary = loads(r["summary"], {})
            programs = summary.get("programs") if isinstance(summary, Mapping) else None
            mine = programs.get(inst.family) if isinstance(programs, Mapping) else None
            got = mine.get("picks") if isinstance(mine, Mapping) else None
            if isinstance(got, bool) or not isinstance(got, int):
                continue
            counts.append(int(got))
            days.append(str(r["day"]))
            if len(counts) >= n:
                break
        weights: list[Decimal] = []
        if days:
            marks = ", ".join("?" for _ in days)
            for r in self.state.rows(f"SELECT weight FROM eq_event_intents WHERE program=? AND version=? AND side='buy' "
                                     f"AND at=? AND day IN ({marks})", (inst.family, int(inst.version), at, *days)):
                w = _event_weight_of(r["weight"])
                if w > 0:
                    weights.append(w)
        return counts, weights

    def _event_given_back(self, day: str, at: str) -> tuple[Decimal, Decimal]:
        """What this auction's EVENT SALES give back by the next auction: (the value of every open event lot whose sale is
        planned or working at `day`'s `at`, its open risk at its own weight), the cash and the loss budget the next
        auction gets back from them (an auction-held lot holds its cash only until its own auction)."""
        value = risk = ZERO
        seen: set[int] = set()
        for r in self.state.rows("SELECT DISTINCT e.lid FROM eq_event_intents e JOIN eq_intents i ON i.iid=e.iid WHERE "
                                 "e.side='sell' AND e.day=? AND e.at=? AND i.status IN ('planned', 'sent') AND e.lid IS NOT "
                                 "NULL", (day, at)):
            lot = self._lot(int(r["lid"]))
            if lot is None or lot.lid in seen or lot.status == LOT_CLOSED or lot.lane != EVENT_LANE:
                continue
            seen.add(lot.lid)
            value += lot.value
            risk += lot.value * event_lot_weight(lot.row())
        return value, risk

    def _event_cut(self, x: Any, sized: Any, short: bool) -> str | None:
        """RELEASE 1019f: the constraint that cut an event buy below its target, in the record's words
        (league/events/book.py `binding_of`, `BINDINGS`), from `size_entry`'s answer `sized` for the facts `x`: its cap;
        for a size under the minimum order (`min_order`), the cap `size_entry` finds with no minimum (the same function
        asked again: what cut the dollars under it); "whole_shares" when no cap cut the dollars and `short` (the floor
        to whole shares took the buy under its target); None otherwise."""
        adapter = self._event_adapter()
        found = sized.binding
        if found == "min_order":
            found = Z.size_entry(replace(x, min_order_usd=ZERO)).binding
        named = adapter.binding_of(found)
        if named is None and found == "intent" and short:
            return "whole_shares"
        return named

    def _event_sized(self, intent: Intent, side: Mapping[str, Any], target: Decimal, binding: str | None,
                     sized: Decimal) -> None:
        """RELEASE 1019f, THE PROBE SIZE'S RECORD: an event buy's band target (`target_usd`, Decimal dollars: the band's
        `position_share` x E at the previous close, as `size_entry` was asked it), the constraint that cut it
        (`binding`, league/events/book.py `BINDINGS`; None when none did) and THE DOLLARS IT SENDS (`sized_usd`, Decimal:
        the whole shares this sizing sends x the limit, 0 when it sends none; release 1019f's integration, the honesty
        check: the Done reader's Probe size compares it with the target, never the fill's cost, which the open's gap
        moves) on its side row in `eq_event_intents`, written at each sizing of its send when they changed (the last
        sizing before the send is the one that sent; A80's one re-send is sized again, so its own). A state with no such
        columns (an adapter that did not migrate) is left as it is; one with the first two only gets those."""
        if "target_usd" not in side:
            return
        value, sent = text(target), text(sized)
        has_sized = "sized_usd" in side
        if side.get("target_usd") == value and side.get("binding") == binding and \
                (not has_sized or side.get("sized_usd") == sent):
            return
        if has_sized:
            self.state.execute("UPDATE eq_event_intents SET target_usd=?, binding=?, sized_usd=? WHERE iid=?",
                               (value, binding, sent, int(intent.iid)))
        else:
            self.state.execute("UPDATE eq_event_intents SET target_usd=?, binding=? WHERE iid=?",
                               (value, binding, int(intent.iid)))

    # ---------------------------------------------------------------- the fills handed back to the lane
    def _event_size_record(self, lot: Lot) -> dict[str, Any]:
        """RELEASE 1019f: {target_usd, binding, sized_usd} of an event lot's buy for the lane's `real_fills`, from its
        side row (`_event_sized`): the band target in dollars (a float, as the lane's columns hold money), the
        constraint that cut it, "venue" when none did, or only the whole shares did, and the venue filled less than one
        of its orders asked (`_event_short_fill`), and the dollars its send asked (the shares sent x the limit); all
        None when the side row holds no target (sized before the release), `sized_usd` None when it holds none."""
        side = self._event_row(lot.iid) if lot.iid is not None else None
        target = A.dec((side or {}).get("target_usd"))
        if target is None:
            return {"target_usd": None, "binding": None, "sized_usd": None}
        binding = side.get("binding") if side.get("binding") in self._event_adapter().BINDINGS else None
        if binding in (None, "whole_shares") and self._event_short_fill(lot):
            binding = "venue"
        sent = A.dec(side.get("sized_usd"))
        return {"target_usd": float(target), "binding": binding, "sized_usd": None if sent is None else float(sent)}

    def _event_short_fill(self, lot: Lot) -> bool:
        """Whether an order of the lot's buy that filled at all filled less than it asked (a partial auction fill)."""
        return lot.iid is not None and any(ZERO < o.filled_qty < o.qty for o in self._intent_orders(lot.iid))

    def _event_fills(self, adapter: Any, out: dict) -> None:
        """THE REAL FILLS HANDED BACK TO THE LANE (PREREG-EVL-3: the lane computes Sized, demotion and retirement from
        them; league/events/book.py `write_fills`): each real event lot's buy, once its buy has ended, and its sale, once
        the lot is closed (again when the broker's posted fees change it), one row a (program, version, event, side),
        written every minute until the lane's store takes them (a lot's `info.evl_fills` keeps what was written).
        RELEASE 1019f: a buy's row carries its side row's `target_usd` and `binding` (the probe size's record,
        `_event_sized`), "venue" for the binding when no cap cut it and the venue filled less than an order asked
        (`_event_short_fill`); NULL in both for a lot whose buy was sized before the release."""
        rows: list[dict[str, Any]] = []
        marks: list[tuple[Lot, dict[str, Any]]] = []
        for r in self.state.rows("SELECT * FROM eq_lots WHERE lane=? AND substr(instance, -2)=? ORDER BY lid",
                                 (EVENT_LANE, REAL_SUFFIX)):
            lot = Lot.of(r)
            evl = lot.info.get("evl") if isinstance(lot.info.get("evl"), Mapping) else None
            if not evl or not evl.get("event"):
                continue
            written = dict(lot.info.get("evl_fills") or {})
            want = dict(written)
            base = {"program": lot.family, "version": int(lot.version), "event": str(evl["event"]),
                    "band": str(evl.get("band") or "learning")}
            buy = self._intent(lot.iid) if lot.iid is not None else None
            if not written.get("buy") and (lot.status != LOT_OPEN or buy is None or buy.status not in INTENT_LIVE):
                rows.append({**base, "side": "buy", "qty": float(lot.opened_qty), "price": float(lot.entry_px), "fee": 0.0,
                             "filled_at": _lane_iso(lot.opened_at), **self._event_size_record(lot)})
                want["buy"] = True
            if lot.status == LOT_CLOSED and lot.exit_px is not None and written.get("sell") != text(lot.fees):
                sold = D(lot.info.get("exit_qty"), lot.opened_qty)
                rows.append({**base, "side": "sell", "qty": float(sold), "price": float(lot.exit_px),
                             "fee": float(lot.fees), "filled_at": _lane_iso(lot.closed_at or self.clock())})
                want["sell"] = text(lot.fees)
            if want != written:
                marks.append((lot, want))
        if not rows:
            return
        n = adapter.write_fills(self.root, rows)
        if n is None:
            out["event_fills"] = f"{len(rows)} real fill(s) wait: the lane's store holds no real_fills table yet"
            return
        with self.state.transaction():
            for lot, want in marks:
                lot.info["evl_fills"] = want
                self._save_lot(lot)
        out["event_fills"] = f"{n} real fill(s) written to the lane"



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


def _budget_asked(why: Any) -> bool:
    """Whether an intent's reason says THE LOSS BUDGET refused its buy, or cut it under the minimum order
    (`EquityBook._work_entry` writes "sizing (<binding>): <reason>"; `size_entry` names the cap that cut a skipped
    entry in its reason, in `BUDGET_WORDS`)."""
    text = str(why or "")
    return "sizing (budget)" in text or ("sizing (min_order)" in text and BUDGET_WORDS in text)


def _refused(windows: Any) -> str:
    """Why a session's open note (`OPEN_NOTE_KEY`: {window: {clear, why}}) says the House refused every open in one
    of its entry windows ("" when no window says so: every window it names is clear, or it names none)."""
    if not isinstance(windows, Mapping):
        return ""
    for name in sorted(windows, reverse=True):                   # "open" before "close": the session's order
        entry = windows[name]
        if isinstance(entry, Mapping) and not entry.get("clear"):
            return f"{name} window: {str(entry.get('why') or 'refused')[:200]}"
    return ""


def _pooled(pool: str) -> dict[str, str]:
    """What a seat record of the panel pool carries beside an ETF one's (an ETF pool's record is main's, to the key)."""
    return {} if pool == POOL_ETF else {"pool": pool}


def _reason_head(why: Any) -> str:
    """A refused session's reason as the seat plan carries it (the plan travels to health.json and the reports): the
    window and the head of the House's words, up to their first colon or bracket ("open window: the House is
    paused"; "close window: equity reconciliation"). What follows there may be a figure of the account's (shares,
    cash, a day's loss): it stays in the book's own note (`OPEN_NOTE_KEY`, live.sqlite)."""
    window, _, words = str(why or "").partition(" window: ")
    head = re.split(r"[:(]", words, maxsplit=1)[0].strip()
    return f"{window} window: {head or 'refused'}"[:160] if words else str(why or "")[:160]


def _counted(first: str, last: str, refused: Mapping[str, Any]) -> tuple[int, int]:
    """(the sessions in (first, last] that count for the idle test, those left out): `schedule.sessions_between`
    less the sessions in which the House refused every open (`EquityBook._refused_days`; A30 (2))."""
    out = sum(1 for day in refused if str(first) < str(day) <= str(last) and S.is_session(str(day)))
    return S.sessions_between(first, last) - out, out


def refused_days(held: Any) -> dict[str, str]:
    """THE SESSIONS IN WHICH THE HOUSE REFUSED EVERY OPEN, read from the open note's value (`OPEN_NOTE_KEY`: {day:
    {window: {clear, why}}}): {day: why}, a session with an entry window the House looked in and never once would have
    opened in (`_refused`). {} for a note that is not a mapping. The book's own reader (`EquityBook._refused_days`, the
    idle clock's) and the `dlane` report's span buy-and-hold (C1, which reads the kv read-only) both read it here, so
    the House has one meaning of the words."""
    if not isinstance(held, Mapping):
        return {}
    return {str(day): _refused(windows) for day, windows in held.items()
            if _refused(windows) and _DAY.fullmatch(str(day))}


def shut_days(held: Any) -> dict[str, str]:
    """THE SESSIONS IN WHICH THE HOUSE LET NO OPEN GO AT ALL (C1, A45: the span buy-and-hold's blocked sessions), read
    from the open note's value: {day: why}, a session whose note names at least one entry window and EVERY window it
    names was refused (never clear). Narrower than `refused_days` (the idle clock's), which reads ONE refused window as
    enough: on a session whose open window was refused and whose close window was clear a program could still open
    (at the close), so the House did not block it from opening. A window entry that is not a mapping shows nothing
    refused: such a session is not one. {} for a note that is not a mapping."""
    if not isinstance(held, Mapping):
        return {}
    out = {}
    for day, windows in held.items():
        if not _DAY.fullmatch(str(day)) or not isinstance(windows, Mapping) or not windows:
            continue
        if all(isinstance(entry, Mapping) and not entry.get("clear") for entry in windows.values()):
            out[str(day)] = _refused(windows)
    return out


def _finite(value: Decimal) -> bool:
    """Whether a Decimal figure is a float's too (a JSON reader's: 1e400 is finite here and infinite there)."""
    try:
        return math.isfinite(float(value))
    except (OverflowError, ValueError):
        return False


def _lot_field(lot: Any, name: str) -> Any:
    """A lot's field, from a `Lot` or from an `eq_lots`-shaped mapping alike (the report reads rows, the book Lots)."""
    return lot.get(name) if isinstance(lot, Mapping) else getattr(lot, name, None)


def _span_days(before: str, last: str) -> list[str]:
    """The sessions in (before, last], in order: the ones `schedule.sessions_between` counts."""
    out, day, end = [], dt.date.fromisoformat(str(before)[:10]), dt.date.fromisoformat(str(last)[:10])
    while day < end:
        day += dt.timedelta(days=1)
        if S.is_session(day):
            out.append(day.isoformat())
    return out


def _one_series(rows: Mapping[str, Any], days: Collection[str]) -> tuple[dict[str, Decimal] | None, str | None, str]:
    """({day: close}, sha, "") when each of `days` has a positive close in `rows` ({day: (close, series sha)}, the
    adjustment=all rows of `eq_bars`) and ONE series sha holds them all: one fetch, one basis (`_bh_pnl`'s rule: two
    fetches straddling an ex-date or a split are not one series). Else (None, None, why)."""
    missing = sorted(d for d in days if d not in rows)
    if missing:
        return None, None, f"no {SPAN_BASIS} close on {', '.join(missing[:4])} in the House's bar store (eq_bars)"
    closes, shas = {}, set()
    for day in days:
        close, sha = rows[day]
        close = A.dec(close)
        if close is None or close <= 0 or not _finite(close):
            return None, None, f"the {SPAN_BASIS} close of {day} is not a positive finite price"
        closes[day] = close
        shas.add(str(sha or ""))
    if len(shas) != 1 or "" in shas:
        return None, None, (f"the closes are not from one fetch ({len(shas)} series shas over {len(days)} days): no "
                            "single basis")
    return closes, shas.pop(), ""


def span_bh(lots: Sequence[Any], closes: Mapping[str, Mapping[str, Any]], blocked: Collection[str] = ()
            ) -> dict[str, Any]:
    """C1 (A45; the scaling plan's 2.4): THE SAME-RISK BUY-AND-HOLD OVER THE SAME SESSIONS of one program version's
    closed lots, by `EquityBook._bh_pnl`'s rule, with ONE CHANGE, stated as the plan states it. Per symbol: the span
    runs from the close before the first entry (`before`) to the close of the last exit (`last`); its sessions are in
    (before, last] (`sessions`, the calendar's count); each lot is held entry notional x the sessions in (entry, exit]
    (at least 1); the figure is the mean exposure x the adjustment=all close at `last` / at `before` - 1, every close
    from ONE fetch (`_one_series`). THE CHANGE: a session in `blocked` (the House blocked the program from opening:
    the caller says which) on which the program held nothing in the symbol is taken out of the span. The span splits
    there; the mean exposure is the same held dollar-sessions over the sessions left (`sessions_used`), and the figure
    sums it x each segment's return (from the close of the session before the segment's first to the close of its
    last). With no such session it is `_bh_pnl` exactly, to the Decimal. Were every session taken out, none is (the
    split is not made), as the plan's script reads it.

    `lots`: `Lot`s or `eq_lots` rows (symbol, opened_day, exit_day, entry_notional); a lot with no exit day is not
    held (as `_bh_pnl`). `closes`: {symbol: {day: (close, series sha)}}, the bar store's adjustment=all rows. Returns
    {priced, why, usd (Decimal, the sum over symbols), symbols: {symbol: {before, last, sessions, sessions_used,
    segments [[first, last] session of each], closes {day: Decimal} at every segment boundary (`before` and `last`
    among them), exposure (Decimal), usd (Decimal), sha}}}. FAIL CLOSED: a lot without a symbol, a day or a positive
    notional, a calendar that cannot place a day, a close missing, off one basis or not a finite price, or a figure
    a float cannot hold (the report writes floats: 1e400 would be Infinity there) is `priced` False with `why` and no
    figure, never a guess."""
    out: dict[str, Any] = {"priced": False, "why": None, "usd": None, "symbols": {}}
    blocked = {str(day)[:10] for day in blocked or ()}
    total = ZERO
    for symbol in sorted({str(_lot_field(lot, "symbol") or "") for lot in lots}):
        mine = [lot for lot in lots if str(_lot_field(lot, "symbol") or "") == symbol and _lot_field(lot, "exit_day")]
        if not mine:
            continue
        if not symbol:
            out["why"] = "a lot has no symbol"
            return out
        legs = []
        for lot in mine:
            notional = A.dec(_lot_field(lot, "entry_notional"))
            opened, exited = str(_lot_field(lot, "opened_day") or "")[:10], str(_lot_field(lot, "exit_day"))[:10]
            if notional is None or notional <= 0 or not _DAY.fullmatch(opened) or not _DAY.fullmatch(exited):
                out["why"] = f"{symbol}: a lot without a positive entry notional, an entry day or an exit day"
                return out
            legs.append((notional, opened, exited))
        first, last = min(o for _, o, _ in legs), max(x for _, _, x in legs)
        try:
            before = S.previous_session(first).isoformat()
            days = _span_days(before, last)
            held = {day: ZERO for day in days}
            weight = ZERO
            for notional, opened, exited in legs:
                inside = _span_days(opened, exited)
                for day in inside:
                    if day in held:
                        held[day] += notional
                weight += notional * max(1, len(inside))
            keep = [day for day in days if not (day in blocked and held[day] == 0)] or list(days) or [last]
            at = {day: i for i, day in enumerate(days)}
            segments: list[list[str]] = []
            for day in keep:
                if segments and day in at and segments[-1][-1] in at and at[day] == at[segments[-1][-1]] + 1:
                    segments[-1].append(day)
                else:
                    segments.append([day])
            bounds = [(S.previous_session(seg[0]).isoformat(), seg[-1]) for seg in segments]
        except ValueError as exc:
            out["why"] = f"{symbol}: the calendar cannot place the span ({str(exc)[:120]})"
            return out
        series, sha, why = _one_series(closes.get(symbol) or {}, {before, last} | {d for pair in bounds for d in pair})
        if series is None:
            out["why"] = f"{symbol}: {why}"
            return out
        exposure = weight / max(1, len(keep))
        usd = ZERO
        for start, end in bounds:
            usd += exposure * (series[end] / series[start] - 1)
        if not (_finite(exposure) and _finite(usd)):
            out["why"] = f"{symbol}: the figure is out of a float's range (a close or a notional is not a price's)"
            return out
        total += usd
        out["symbols"][symbol] = {"before": before, "last": last, "sessions": max(1, len(days)),
                                  "sessions_used": len(keep), "segments": [[seg[0], seg[-1]] for seg in segments],
                                  "closes": dict(sorted(series.items())), "exposure": exposure, "usd": usd, "sha": sha}
    if not _finite(total):
        out["why"] = "the figure is out of a float's range"
        return out
    out.update(priced=True, usd=total)
    return out


def b10_bh(lots: Sequence[Any], spy: Mapping[str, Any]) -> dict[str, Any]:
    """C1 (A45): B10, A PANEL PROGRAM'S SAME-RISK BUY-AND-HOLD (league/xs/book.py `date_record`, which
    `_panel_record_of` feeds the band rules): per closed lot, its entry notional x (SPY's adjustment=all close on its
    exit day / on the session before its entry day - 1), summed in `date_record`'s order, every close from ONE fetch
    (`_one_series`). No split: each lot is held over its own sessions only. `spy`: {day: (close, series sha)}. Returns
    {priced, why, usd (Decimal), closes {day: Decimal}, sha}; fail closed as `span_bh` (where `date_record` reads an
    unreadable notional as zero, this reads no figure)."""
    out: dict[str, Any] = {"priced": False, "why": None, "usd": None, "closes": {}, "sha": None}
    closed = sorted((lot for lot in lots if _lot_field(lot, "exit_day")),
                    key=lambda lot: (str(_lot_field(lot, "exit_day")), float(_lot_field(lot, "closed_at") or 0.0),
                                     int(_lot_field(lot, "lid") or 0)))
    legs, need = [], set()
    for lot in closed:
        notional = A.dec(_lot_field(lot, "entry_notional"))
        opened, exited = str(_lot_field(lot, "opened_day") or "")[:10], str(_lot_field(lot, "exit_day"))[:10]
        if notional is None or notional <= 0 or not _DAY.fullmatch(opened) or not _DAY.fullmatch(exited):
            out["why"] = "a lot without a positive entry notional, an entry day or an exit day"
            return out
        try:
            start = S.previous_session(opened).isoformat()
        except ValueError as exc:
            out["why"] = f"the calendar cannot place an entry day ({str(exc)[:120]})"
            return out
        legs.append((notional, start, exited))
        need |= {start, exited}
    if not legs:
        out.update(priced=True, usd=ZERO)            # no closed lot: nothing held (`date_record`'s zero)
        return out
    series, sha, why = _one_series(spy, need)
    if series is None:
        out["why"] = f"{B10_SYMBOL}: {why}"
        return out
    total = ZERO
    for notional, start, end in legs:
        total += notional * (series[end] / series[start] - 1)
    if not _finite(total):
        out["why"] = f"{B10_SYMBOL}: the figure is out of a float's range (a close or a notional is not a price's)"
        return out
    out.update(priced=True, usd=total, closes=dict(sorted(series.items())), sha=sha)
    return out


def record_edm1(why: Any) -> bool:
    """Whether `bands.next_band`'s reason for "candidate" is EDM1's own (never the wait for a seat, never a mark
    already sticky)."""
    return str(why or "").startswith("EDM1:")


def _ctx_reason(reason: Any) -> str:
    """A lot's close reason as a program sees it: "program", "max_hold" or "house" (every other House reason)."""
    return reason if reason in ("program", "max_hold") else "house"


def _version_of(instance: str) -> int:
    try:
        return int(str(instance).rsplit("@", 1)[1].split(":", 1)[0])
    except (IndexError, ValueError):
        return 0


def _bars_verdict(old_raw: Mapping[str, tuple], old_all: Mapping[str, tuple], fresh_raw: Mapping[str, Mapping],
                  fresh_all: Mapping[str, Mapping], day: str) -> str:
    """One symbol's stored rows ({day: (o, h, l, c, v)}, raw and all) against a later reading of the same span ({day:
    row}): "mismatch" when their sessions, a raw open, high, low or close, or the as-of prices at `day` differ;
    "volume" when only a raw volume does; else "ok"."""
    if set(fresh_raw) != set(old_raw) or set(fresh_all) != set(old_all) or day not in old_raw:
        return "mismatch"
    if any(A.dec(fresh_raw[d].get(k)) != A.dec(old_raw[d][i]) for d in old_raw
           for i, k in enumerate(("o", "h", "l", "c"))):
        return "mismatch"
    if not _as_of_equal(old_raw, old_all, fresh_raw, fresh_all, day):
        return "mismatch"
    if any(A.dec(fresh_raw[d].get("v")) != A.dec(old_raw[d][4]) for d in old_raw):
        return "volume"
    return "ok"


def _as_of_equal(old_raw: Mapping[str, tuple], old_all: Mapping[str, tuple], fresh_raw: Mapping[str, Mapping],
                 fresh_all: Mapping[str, Mapping], day: str) -> bool:
    """Whether two readings of the adjustment=all series give the same as-of prices at `day`: within a millionth, or
    within what the vendor's rounding allows when that is more. The vendor rounds its adjusted prices to the cent (the
    rehearsal on real SIP bars, Oct 11, 2026), and an as-of price is all_s x raw_t / all_t, so two readings of one
    series that an event restated in between (every ex-dividend morning) differ by the rounding of the four adjusted
    prices they are built from: `config.rounding_bound`, the bound the engine reads a ratio step with, so the Gym and
    this audit cannot drift apart. Compared to a millionth alone, every ex-dividend morning read as a mismatch, which
    cancels the decision's buys and counts a failed decide. A price that cannot be read is a difference."""
    try:
        old_c, new_c = float(old_all[day][3]), float(fresh_all[day]["c"])
        old_t = float(old_raw[day][3]) / old_c
        new_t = float(fresh_raw[day]["c"]) / new_c
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        return False
    for d, values in old_all.items():
        row = fresh_all.get(d)
        if row is None:
            return False
        for i, k in enumerate(("o", "h", "l", "c")):
            try:
                x, y = float(values[i]), float(row[k])
                rounding = config.rounding_bound(x, old_c, y, new_c)
            except (KeyError, TypeError, ValueError):
                return False
            a, b = x * old_t, y * new_t
            if not math.isfinite(a) or not math.isfinite(b):
                return False
            if abs(a - b) > max(1e-6, rounding) * max(abs(a), abs(b), 1.0):
                return False
    return True


__all__ = ["SCHEMA", "EQUITY_KIND", "INSTANCE_KIND", "INSTANCE_KIND_DDL", "WORKING", "TERMINAL", "LOT_OPEN", "LOT_CLOSING",
           "LOT_CLOSED", "REAL_SUFFIX", "SHARE_TOLERANCE",
           "CLIENT_PREFIX", "client_id", "ProbeFigures", "probe_figures", "expected_shares_rows", "working_buys_worst",
           "orders_today", "event_orders_today", "invested", "EquityBook", "Lot", "Order", "Intent", "Instance", "instance_key", "order_body",
           "limit_for", "collar_for", "house_minute", "export_row", "qty_text", "HOUSE_REASONS", "EXIT_KINDS"]
