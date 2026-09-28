"""What Profit holds outside the live book's positions, read from the Brokerage Account's own activity record.

The site's positions table (the owner, Sept 28, 2026) lists every real-options position since the performance reset
with its P&L, and those lines plus an "Other account activity" line must add up to Profit to the cent
(`league/trading_profit.py`). The live book prices a position from its own fills less its own fee ESTIMATE
(`league/gym/venue.py` `leg_fee`); the broker charges the real fees as separate FEE activities, one per leg fill, dated
but not timed, often a day or more later (Sept 28, 2026: $0.03 an OCC clearing fee per leg against the book's $0.05).
The account also paid crypto fees selling the legacy coins at the reset, and it can earn interest. So `classify` reads
the account's activities and orders since `performance.start_at`, beside the book's orders and fills, and says, each
exact to the cent:

- `fees_by_pid`: per position, the broker's charged option fees less the book's estimates for the same orders, taken
  per book order once every leg that filled has its fee posted (until then the estimate stands). They go into that
  position's own row (`trading_profit.complete`).
- `fees_usd`: fees no position carries: the broker's pass-through charges and rebates (PTC, PTR), a broker
  liquidation's fee true-up (`RealBook.recover_expired` keeps no order to tie it to), and any fee on an order the book
  does not hold (alerted).
- `crypto_usd`: crypto fees (CFEE). The coins' sale itself and the dust left over (`league/live/real.py` `KNOWN_DUST`)
  are not Profit: their value at the reset was never recorded, so no figure for them is exact.
- `interest_usd`: interest (INT, INTNRA, INTTW).
- `misc_usd`: dividends and the other return types `ltcm.performance.ALPACA_RETURNS` knows.
- `unreconciled_usd`: what the account shows that the book cannot account for: an option fill on an order the book
  does not hold (after `SETTLE_SECONDS`), a finished order whose fills at the broker differ from the book's (after
  `SETTLE_SECONDS`), an option event on a contract no position of the book held, a cash event the book never counts
  (OPCSH, OPTRD, OPCA or an OPEXP with an amount, on a contract of a position it did not settle itself), the
  difference between the broker's cash for an assignment or an exercise (the event and its shares' fills) or for the
  cash settlement of the index positions the book settled itself and the book's own value for them, or an activity of
  a type nobody classified. Each also yields a `problem` for the owner's alerts. Never hidden.
- `blocking`: what makes Profit unknown until it settles, never a guess: shares an assignment or an exercise left on
  the account (or no reading of whether any are left), an assignment or an exercise on a contract of the book that the
  book has not taken yet (or on a position the broker also liquidated, which no record ties to one position), or a
  broker fill on a contract a position of the book still holds that the book has not matched (a liquidation, after
  `SETTLE_SECONDS`). Also alerted.

Positions opened before the reset are not Profit, and nor is anything of theirs: an order is the reset's when its
position is (`read_book`), whenever it was placed, and a fill or fee on an order of an older position is left out.

Funding (`ltcm.performance.ALPACA_FUNDING`) is never any of these: deposits are not profit.

`problems` and `blocking` are for the House's alerts only and never published; they name order and activity ids,
never a price or a contract. The live book is read read-only (`<state>/live.sqlite`), never written: the live path
(`league/live/`) is unchanged. Reads go through the publisher's broker (`_call`, the gateway), off the publishing path,
every five minutes (`ActivityLedger`); a reading older than ten minutes is none, and Profit is then unknown.
"""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import threading
import time
from contextlib import closing
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping
from zoneinfo import ZoneInfo

from ltcm.performance import ALPACA_FUNDING, ALPACA_RETURNS

from .trading_profit import OTHER_PARTS, cents

ZERO = Decimal(0)
NEW_YORK = ZoneInfo("America/New_York")
HALF_CENT = Decimal("0.005")
#: How often the account is read, and how long a reading counts (the funding check's cadence, `league/publish.py`).
EVERY_SECONDS = 300
FRESH_SECONDS = 600
#: A finished order's fills are compared with the broker's this long after its last change: the broker's activity
#: record can trail its order answers by a moment, and the book reads the orders once a minute.
SETTLE_SECONDS = 900
#: After the first whole read since the reset, each read covers the last few days only (activities are immutable, and a
#: fee posts dated the day it posts); the whole record is read again every few hours.
WINDOW_SECONDS = 3 * 86400
FULL_EVERY_SECONDS = 6 * 3600
MAX_PAGES = 200
PAGE = 100
ORDER_PAGE = 500

INTEREST = frozenset({"INT", "INTNRA", "INTTW"})
#: The option lifecycle: assignment, exercise, expiry, cash settlement, and the other option events.
OPTION_EVENTS = frozenset({"OPASN", "OPEXC", "OPEXP", "OPCSH", "OPTRD", "OPCA"})
#: The broker's pass-through charges and rebates (regulatory fees it passes on): fees, though no order names them.
PASS_THROUGH = frozenset({"PTC", "PTR"})
MISC = frozenset(ALPACA_RETURNS) - {"FILL", "FEE", "CFEE"} - INTEREST - OPTION_EVENTS - PASS_THROUGH
FUNDING = frozenset(ALPACA_FUNDING)
#: The book's order statuses that end an order (`league/live/real.py` `ROrder.status`).
FINISHED = frozenset({"filled", "cancelled", "expired", "rejected", "refused", "lost"})
#: The events the live path takes itself (`league/live/step.py` `_activities`, `RealBook.remove_contracts`): an
#: assignment or an exercise at the contract's intrinsic value then, an expiry at zero.
ASSIGNMENTS = frozenset({"OPASN", "OPEXC"})
#: A position's statuses while the book still holds (or still awaits the broker's word on) its contracts.
HOLDING = frozenset({"open", "awaiting_expiry", "unpriced_close"})
#: The book's own settlement of an index position at its expiry (`RealBook.settle`: "settled", "settled at the last
#: recorded level ..."): its value stands until the broker's events for every contract of that expiry have posted.
SETTLED = "settled"
#: A settlement the broker has not posted this long after the expiry's close is said (not unknown: the book's value stands).
LATE_SETTLEMENT_SECONDS = 3 * 86400
#: The activity fields a reading keeps (never the whole row: nothing of it is published, but less is kept).
KEEP = ("id", "activity_type", "symbol", "side", "qty", "price", "order_id", "net_amount", "transaction_time", "date")


class Unreadable(ValueError):
    """An activity or an order the reading cannot put a number on: no reading at all, never a guessed one."""


def dec(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        out = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return out if out.is_finite() else None


def epoch(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace("Z", "+00:00")
    if "T" not in text:
        text += "T00:00:00+00:00"
    if "." in text:  # nanoseconds: Python takes six digits
        head, _, rest = text.partition(".")
        digits = len(rest) - len(rest.lstrip("0123456789"))
        text = f"{head}.{rest[:digits][:6].ljust(6, '0')}{rest[digits:]}"
    try:
        stamp = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    return stamp.timestamp() if stamp.tzinfo is not None else None


def iso(seconds: float) -> str:
    return dt.datetime.fromtimestamp(seconds, dt.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def is_option(symbol: str) -> bool:
    """A standard OCC contract (`league/live/venue.py` `occ_parts`, without the import of the live path)."""
    s = str(symbol or "").strip().upper()
    return len(s) >= 16 and s[-9] in "CP" and s[-15:-9].isdigit() and s[-8:].isdigit() and s[:-15].isalpha()


def is_crypto(symbol: str) -> bool:
    s = str(symbol or "").upper()
    return "/" in s or (s.endswith(("USD", "USDT", "USDC")) and not is_option(s) and len(s) > 4)


# ------------------------------------------------------------------------------------------ the book
def read_book(root: str | Path, start_at: Any = None) -> dict[str, Any]:
    """The live book in one read transaction (read-only): the positions opened since `start_at` and their orders
    (`positions`, `orders`: an order is the reset's when its position is, whenever it was placed; one with no position
    when it was placed since), every order, fill and position (`every_order`, `fills`, `every_position`: to know an
    older position's order when its fills come, and whose contracts the book held), the consumed external fills, and
    `orders_from`: the earliest placing of an order that still changed after `start_at` (the broker's order list is
    read from there, so a leg's id always finds its order). An absent book is an empty one (nothing traded); an
    unreadable one raises."""
    path = Path(root) / "live.sqlite"
    empty = {"orders": [], "fills": [], "positions": [], "external": [], "every_order": [], "every_position": [], "orders_from": None}
    if not path.exists():
        return empty
    since = epoch(start_at)
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)) as db:
        db.row_factory = sqlite3.Row
        db.execute("BEGIN")
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        read = lambda table: [dict(row) for row in db.execute(f"SELECT * FROM {table}")] if table in tables else []  # noqa: E731
        every_order, fills, every_position, external = read("orders"), read("fills"), read("positions"), read("external_fill_usage")
        db.rollback()
    positions, orders = every_position, every_order
    if since is not None:
        positions = [p for p in every_position if float(p.get("opened_at") or 0) >= since]
        mine = {int(p["pid"]) for p in positions}
        owner = {int(f["oid"]): int(f["pid"]) for f in fills if f.get("pid") is not None}
        def reset_s(o: Mapping[str, Any]) -> bool:
            pid = o.get("pid") if o.get("pid") is not None else owner.get(int(o["oid"]))
            return int(pid) in mine if pid is not None else float(o.get("placed_at") or 0) >= since
        orders = [o for o in every_order if reset_s(o)]
    changed = [float(o.get("placed_at") or 0) for o in every_order if since is None or float(o.get("updated_at") or 0) >= since]
    return {"orders": orders, "fills": fills, "positions": positions, "external": [str(r.get("id") or "") for r in external],
            "every_order": every_order, "every_position": every_position, "orders_from": (min(changed) - 60) if changed else None}


# ------------------------------------------------------------------------------------------ the rule
def _signed_cash(side: Any, qty: Decimal, price: Decimal, multiplier: int) -> Decimal:
    if side == "sell":
        return qty * price * multiplier
    if side == "buy":
        return -qty * price * multiplier
    raise Unreadable("a fill without a side")


def _symbols(position: Mapping[str, Any]) -> set[str]:
    return {str(leg.get("symbol") or "").upper() for leg in _legs(position.get("legs")) if isinstance(leg, Mapping)}


def _info(position: Mapping[str, Any]) -> dict[str, Any]:
    try:
        out = json.loads(position.get("info") or "{}")
    except (TypeError, ValueError):
        return {}
    return out if isinstance(out, dict) else {}


def _expiry_close(day: str) -> float | None:
    try:
        return dt.datetime.combine(dt.date.fromisoformat(day), dt.time(16), tzinfo=NEW_YORK).timestamp()
    except (TypeError, ValueError):
        return None


def classify(activities: Iterable[Mapping[str, Any]], venue_orders: Iterable[Mapping[str, Any]],
             book: Mapping[str, Any], *, now: float, shares_held: Callable[[], bool | None] | None = None) -> dict[str, Any]:
    """{fees_usd, crypto_usd, interest_usd, misc_usd, unreconciled_usd, fees_by_pid, blocking, problems} (the module
    docstring): the dollars as Decimals exact to the cent (`fees_by_pid` keyed by the position's id as a string),
    `blocking` and `problems` lists of sentences for the alerts. `shares_held` says whether the account holds any
    shares now (None when it cannot tell); it is asked only after an assignment, an exercise or a share fill. Pure but
    for it. Raises `Unreadable` on an activity it cannot put a number on."""
    problems: list[str] = []
    blocking: list[str] = []
    parts = {part: ZERO for part in OTHER_PARTS}
    unreconciled = ZERO
    fees_by_pid: dict[int, Decimal] = {}

    # The broker's orders: every leg's id and the parent's own name its parent; which legs filled.
    parent: dict[str, str] = {}
    client: dict[str, str] = {}
    filled_legs: dict[str, list[str]] = {}
    for order in venue_orders:
        oid = str(order.get("id") or "")
        if not oid:
            continue
        parent[oid], client[oid] = oid, str(order.get("client_order_id") or "")
        legs = [leg for leg in order.get("legs") or [] if isinstance(leg, Mapping) and leg.get("id")]
        for leg in legs:
            parent[str(leg["id"])] = oid
        units = legs or [order]
        filled_legs[oid] = [str(unit["id"]) for unit in units if (dec(unit.get("filled_qty")) or ZERO) > 0]

    orders = list(book.get("orders") or [])
    every_order = list(book.get("every_order") or orders)
    mine = {int(o["oid"]) for o in orders}
    by_oid = {int(o["oid"]): o for o in every_order}
    by_venue = {str(o["venue_id"]): o for o in every_order if o.get("venue_id")}
    by_client = {str(o["client_id"]): o for o in every_order if o.get("client_id")}
    venue_of: dict[int, str] = {}
    for venue_id, owner in parent.items():
        if venue_id == owner:
            o = by_venue.get(venue_id) or by_client.get(client.get(venue_id, ""))
            if o is not None:
                venue_of[int(o["oid"])] = venue_id

    def book_order(order_id: str) -> tuple[Mapping[str, Any] | None, bool]:
        """(the book's order for a venue order or leg id, whether the broker's orders name the id at all)."""
        top = parent.get(order_id)
        if top is None:
            return by_venue.get(order_id), False
        return by_venue.get(top) or by_client.get(client.get(top, "")), True

    external_orders, external_activities = set(), set()
    for key in book.get("external") or []:  # `league/live/step.py` `_reconcile_expiry`: order:<id>:<symbol> or activity:<id>
        kind, _, rest = str(key).partition(":")
        if kind == "order":
            external_orders.add(rest.split(":", 1)[0])
        elif kind == "activity":
            external_activities.add(rest)
    positions = list(book.get("positions") or [])
    every_position = list(book.get("every_position") or positions)
    held = set().union(*(_symbols(p) for p in positions)) if positions else set()
    held_before = (set().union(*(_symbols(p) for p in every_position)) if every_position else set()) - held
    holding = set().union(*(_symbols(p) for p in every_position if p.get("status") in HOLDING)) if every_position else set()

    venue_cash: dict[int, Decimal] = {}
    charged: dict[int, Decimal] = {}
    charged_ids: dict[int, set[str]] = {}
    external_charged, external_charged_ids = ZERO, set()
    shares_cash, share_fills = ZERO, []
    assignments: list[tuple[str, Decimal, str, str]] = []   # (symbol, amount, kind, activity id)
    posted: dict[str, list[tuple[Decimal, str, str]]] = {}   # a held contract's events: symbol -> [(amount, kind, id)]
    for activity in activities:
        kind = str(activity.get("activity_type") or "")
        activity_id = str(activity.get("id") or "?")
        amount = dec(activity.get("net_amount"))
        order_id = str(activity.get("order_id") or "")
        if kind == "FILL":
            symbol = str(activity.get("symbol") or "")
            if is_crypto(symbol):
                continue  # the legacy coins sold at the reset: not Profit (the module docstring)
            qty, price = dec(activity.get("qty")), dec(activity.get("price"))
            if qty is None or price is None:
                raise Unreadable(f"fill {activity_id} without a quantity or a price")
            if not is_option(symbol):
                shares_cash += _signed_cash(activity.get("side"), qty, price, 1)  # an assignment's or an exercise's shares
                share_fills.append(activity_id)
                continue
            cash = _signed_cash(activity.get("side"), qty, price, 100)
            owner, known = book_order(order_id)
            if owner is not None:
                if int(owner["oid"]) in mine:
                    venue_cash[int(owner["oid"])] = venue_cash.get(int(owner["oid"]), ZERO) + cash
                continue  # else an order of a position from before the reset: not this record's
            if order_id in external_orders or activity_id in external_activities:
                continue  # a liquidation the book priced from this very fill (`RealBook.recover_expired`)
            if (epoch(activity.get("transaction_time")) or 0.0) > now - SETTLE_SECONDS:
                continue  # the book reads the broker once a minute and prices a liquidation after it: next reading
            if symbol.upper() in holding:
                # A broker fill (a liquidation) on a contract the book still holds and still values: counting it now
                # would count the same contracts twice; Profit waits for the book to take it.
                blocking.append(f"a broker fill on a contract a live position still holds, not yet taken by the book "
                                f"(order {order_id or 'none'}, activity {activity_id})")
                continue
            unreconciled += cash
            problems.append(f"an option fill on an order the live book does not hold (order {order_id or 'none'}, activity {activity_id})"
                            + ("" if known or not order_id else ": the broker's order list does not name it"))
        elif kind == "FEE":
            if amount is None:
                raise Unreadable(f"fee {activity_id} without an amount")
            owner, _known = book_order(order_id)
            if owner is not None:
                oid = int(owner["oid"])
                if oid in mine:
                    charged[oid] = charged.get(oid, ZERO) + amount
                    charged_ids.setdefault(oid, set()).add(order_id)
            elif order_id and order_id in external_orders:
                external_charged += amount
                external_charged_ids.add(order_id)
            else:
                parts["fees_usd"] += amount
                problems.append(f"a fee on an order the live book does not hold (order {order_id or 'none'}, activity {activity_id})")
        elif kind == "CFEE":
            if amount is None:
                raise Unreadable(f"crypto fee {activity_id} without an amount")
            parts["crypto_usd"] += amount
        elif kind in INTEREST:
            if amount is None:
                raise Unreadable(f"interest {activity_id} without an amount")
            parts["interest_usd"] += amount
        elif kind in PASS_THROUGH:
            if amount is None:
                raise Unreadable(f"pass-through {activity_id} without an amount")
            parts["fees_usd"] += amount
        elif kind in FUNDING:
            continue  # the owner's own money in or out: never profit
        elif kind in OPTION_EVENTS:
            symbol = str(activity.get("symbol") or "").upper()
            if symbol in held_before and symbol not in held:
                continue  # a contract only a position from before the reset held: not this record's
            if kind in ASSIGNMENTS:
                assignments.append((symbol, amount or ZERO, kind, activity_id))
            elif symbol in held:
                posted.setdefault(symbol, []).append((amount or ZERO, kind, activity_id))
            else:
                unreconciled += amount or ZERO
                problems.append(f"an option event ({kind}, activity {activity_id}) on a contract no position of the book held")
        elif kind in MISC:
            parts["misc_usd"] += amount or ZERO
        else:
            if amount:
                unreconciled += amount
            problems.append(f"an account activity of a type nobody classified ({kind or 'none'}, activity {activity_id})")

    # The book's finished orders against the broker's fills, and their fees once every filled leg's has posted.
    fills_of: dict[int, list[Mapping[str, Any]]] = {}
    fills_by_pid: dict[int, list[Mapping[str, Any]]] = {}
    for fill in book.get("fills") or []:
        fills_of.setdefault(int(fill["oid"]), []).append(fill)
        if fill.get("pid") is not None:
            fills_by_pid.setdefault(int(fill["pid"]), []).append(fill)
    for order in orders:
        oid = int(order["oid"])
        if order.get("status") not in FINISHED or now - float(order.get("updated_at") or 0) < SETTLE_SECONDS:
            continue
        own = fills_of.get(oid, [])
        sign = -1 if order.get("action") == "open" else 1
        book_cash = sum((sign * Decimal(str(f["value"])) * 100 * int(f["qty"]) for f in own), ZERO)
        difference = venue_cash.get(oid, ZERO) - book_cash
        if abs(difference) >= HALF_CENT:
            unreconciled += difference
            problems.append(f"order {order.get('client_id')}: the broker's fills and the book's differ")
        venue_id = venue_of.get(oid)
        legs = filled_legs.get(venue_id or "", [])
        if legs and all(leg in charged_ids.get(oid, set()) for leg in legs):
            correction = charged.get(oid, ZERO) + sum((Decimal(str(f["fees"])) for f in own), ZERO)
            pids = {int(f["pid"]) for f in own if f.get("pid") is not None} or ({int(order["pid"])} if order.get("pid") is not None else set())
            if len(pids) == 1:
                pid = pids.pop()
                fees_by_pid[pid] = fees_by_pid.get(pid, ZERO) + correction
            else:
                parts["fees_usd"] += correction  # no single position to carry it: Other's fees

    def nonfill(position: Mapping[str, Any]) -> Decimal:
        """What the book credited a position beyond its own fills: its value for an assignment, an exercise or its own
        settlement at expiry (and a broker liquidation's fills, less their fee estimates)."""
        cash = Decimal(str(position.get("cash") or 0))
        for fill in fills_by_pid.get(int(position["pid"]), []):
            action = (by_oid.get(int(fill["oid"])) or {}).get("action")
            sign = -1 if action == "open" else 1
            cash -= sign * Decimal(str(fill["value"])) * 100 * int(fill["qty"]) - Decimal(str(fill["fees"]))
        return cash

    # The index positions the book settled itself at expiry: their value stands until the broker has posted an event for
    # every contract of that expiry, then the broker's cash replaces it (the difference is Unreconciled, said).
    settled: dict[str, list[Mapping[str, Any]]] = {}
    for position in positions:
        if position.get("status") == "closed" and str(position.get("reason") or "").startswith(SETTLED):
            expiries = sorted({str(leg.get("expiry") or "") for leg in _legs(position.get("legs")) if isinstance(leg, Mapping)})
            settled.setdefault(expiries[-1] if expiries else "", []).append(position)
    taken: set[str] = set()
    waiting: set[str] = set()
    for day, group in sorted(settled.items()):
        symbols = set().union(*(_symbols(p) for p in group))
        if symbols and all(symbol in posted for symbol in symbols):
            cash = sum((amount for symbol in symbols for amount, _kind, _id in posted[symbol]), ZERO)
            difference = cash - sum((nonfill(p) for p in group), ZERO)
            unreconciled += difference
            taken |= symbols
            if abs(difference) >= HALF_CENT:
                problems.append(f"the broker's settlement of the {day} expiry differs from the book's own value for it "
                                f"(positions {', '.join('real:' + str(p['pid']) for p in group)})")
        else:
            waiting |= symbols  # the book's own value stands until the broker has posted the whole expiry
            if (_expiry_close(day) or now) < now - LATE_SETTLEMENT_SECONDS:
                problems.append(f"the broker has not posted the {day} expiry of positions the book settled itself: its value stands")
    for symbol, events in posted.items():
        if symbol in taken or symbol in waiting:
            continue
        for amount, kind, activity_id in events:
            if kind == "OPEXP" and not amount:
                continue  # an expiry the book took itself at zero (`remove_contracts`)
            unreconciled += amount  # a cash event the book never counts, on a contract it did not settle itself
            problems.append(f"an option event the live book does not count ({kind}, activity {activity_id}) on a contract it held")

    # Assignments and exercises: the book took each at the contract's intrinsic value when it saw it
    # (`remove_contracts`); the broker's truth is the event's own cash and its shares' fills. Once the book has taken
    # every one and the account holds no shares, the difference is Unreconciled; until then Profit is unknown.
    if assignments or share_fills:
        gone: dict[str, list[Mapping[str, Any]]] = {}
        for position in positions:
            for symbol, count in (_info(position).get("gone") or {}).items():
                if count:
                    gone.setdefault(str(symbol).upper(), []).append(position)
        untaken = [activity_id for symbol, _a, _k, activity_id in assignments if symbol in held and symbol not in gone]
        held_now = shares_held() if shares_held is not None else None
        ids = ", ".join([activity_id for *_rest, activity_id in assignments] + share_fills)
        touched = {int(p["pid"]): p for symbol, *_rest in assignments for p in gone.get(symbol, [])}
        fill_fees = {pid: sum((Decimal(str(f["fees"])) for f in fills_by_pid.get(pid, [])), ZERO) for pid in touched}
        # A touched position the broker also liquidated carries that liquidation's cash beyond its fills too, and no
        # record ties it to one position: the difference cannot be put on a line exactly, so Profit waits for the owner.
        liquidated = sorted(pid for pid, p in touched.items() if Decimal(str(p.get("fees") or 0)) - fill_fees[pid] >= HALF_CENT)
        if untaken:
            blocking.append(f"an assignment or an exercise the live book has not taken yet (activity {', '.join(untaken)})")
        elif held_now is not False:
            blocking.append(f"shares an assignment or an exercise left are {'still held' if held_now else 'not known to be sold'} "
                            f"(activities {ids})")
        elif liquidated:
            blocking.append(f"an assigned or exercised position the broker also liquidated (positions "
                            f"{', '.join('real:' + str(pid) for pid in liquidated)}): reconcile it by hand")
        else:
            cash = sum((amount for _s, amount, _k, _i in assignments), ZERO) + shares_cash
            unreconciled += cash - sum((nonfill(p) for p in touched.values()), ZERO)
            problems.append(f"an assignment or an exercise: the broker's cash and its shares' fills against the book's own value "
                            f"(activities {ids})")

    # The book's liquidation fees (`recover_expired` adds its estimates to the position, with no fill row): once every
    # liquidation order the book priced from has its fee posted, the charged fees replace them (Other's fees: no order
    # ties a liquidation to one position).
    if external_orders and external_orders <= external_charged_ids:
        fill_fees: dict[int, Decimal] = {}
        for fill in book.get("fills") or []:
            if fill.get("pid") is not None:
                fill_fees[int(fill["pid"])] = fill_fees.get(int(fill["pid"]), ZERO) + Decimal(str(fill["fees"]))
        estimate = sum((max(ZERO, Decimal(str(p.get("fees") or 0)) - fill_fees.get(int(p["pid"]), ZERO))
                        for p in positions), ZERO)
        parts["fees_usd"] += external_charged + estimate
    return {**{part: cents(value) for part, value in parts.items()}, "unreconciled_usd": cents(unreconciled),
            "fees_by_pid": {str(pid): cents(value) for pid, value in sorted(fees_by_pid.items())},
            "blocking": list(dict.fromkeys(blocking)), "problems": list(dict.fromkeys(problems))}


def _legs(text: Any) -> list[Any]:
    try:
        out = json.loads(text or "[]")
    except (TypeError, ValueError):
        return []
    return out if isinstance(out, list) else []


# ------------------------------------------------------------------------------------------ the reads
def activities_after(broker: Any, after: str) -> list[dict[str, Any]]:
    """Every account activity after `after`, oldest first, every page (`GET /v2/account/activities`)."""
    out: list[dict[str, Any]] = []
    token, seen = None, set()
    for _ in range(MAX_PAGES):
        params = {"after": after, "direction": "asc", "page_size": PAGE}
        if token:
            params["page_token"] = token
        rows = broker._call("GET", "/v2/account/activities", params=params, what="positions ledger activities")
        if not isinstance(rows, list):
            raise Unreadable("the activity history is not a list")
        fresh = [row for row in rows if isinstance(row, dict) and row.get("id") and row["id"] not in seen]
        for row in fresh:
            seen.add(row["id"])
            out.append({key: row.get(key) for key in KEEP})
        if not fresh or len(rows) < PAGE:
            return out
        token = rows[-1].get("id")
        if not token:
            return out
    raise Unreadable(f"the activity history runs past {MAX_PAGES} pages")


def orders_after(broker: Any, after: str) -> list[dict[str, Any]]:
    """Every order submitted after `after` with its legs (`GET /v2/orders?status=all&nested=true`), every page. Only
    ids, the client id and filled quantities are kept."""
    out: dict[str, dict[str, Any]] = {}
    cursor = after
    for _ in range(MAX_PAGES):
        rows = broker._call("GET", "/v2/orders", params={"status": "all", "nested": "true", "after": cursor, "limit": ORDER_PAGE,
                                                         "direction": "asc"}, what="positions ledger orders")
        if not isinstance(rows, list):
            raise Unreadable("the order list is not a list")
        new = 0
        for row in rows:
            if not isinstance(row, dict) or not row.get("id"):
                continue
            new += row["id"] not in out
            out[str(row["id"])] = {"id": str(row["id"]), "client_order_id": row.get("client_order_id"),
                                   "filled_qty": row.get("filled_qty"), "submitted_at": row.get("submitted_at"),
                                   "legs": [{"id": leg.get("id"), "filled_qty": leg.get("filled_qty")}
                                            for leg in row.get("legs") or [] if isinstance(leg, dict)]}
        if len(rows) < ORDER_PAGE or not new or not rows[-1].get("submitted_at"):
            return list(out.values())
        cursor = rows[-1]["submitted_at"]
    raise Unreadable(f"the order list runs past {MAX_PAGES} pages")


def shares_held(broker: Any) -> bool | None:
    """Whether the account holds any shares now (`GET /v2/positions`), None when it cannot tell."""
    try:
        rows = broker._call("GET", "/v2/positions", what="positions ledger shares")
    except Exception:  # noqa: BLE001 - unknown, never "none held"
        return None
    if not isinstance(rows, list):
        return None
    return any(isinstance(row, dict) and str(row.get("asset_class")) == "us_equity" and (dec(row.get("qty")) or ZERO) != 0
               for row in rows)


#: A reading's dollar fields, as saved across a restart (`ActivityLedger.saved`).
MONEY_FIELDS = (*OTHER_PARTS, "unreconciled_usd")


class ActivityLedger:
    """The account's side of the positions table, read off the publishing path (`Flows`' pattern, `league/publish.py`):
    every `EVERY_SECONDS` a background read of the book and the account; `read()` returns the last reading while it is
    under `FRESH_SECONDS` old, else None. A failed read keeps the last good reading until it ages out, and says why
    (`error`). The last reading survives a restart (`saved`, `restore`: the publisher keeps it in publish.json), so a
    restarted House has Profit at once rather than a dash until its first read."""

    def __init__(self, broker: Any, start_at: str, root: str | Path, *, clock: Callable[[], float] = time.time,
                 reader: Callable[[], Mapping[str, Any]] | None = None, threaded: bool = True):
        self.broker, self.start_at, self.root, self.clock, self.threaded = broker, start_at, Path(root), clock, threaded
        self.reader = reader or self._read
        self.lock = threading.Lock()
        self.busy, self.attempted = False, float("-inf")
        self.reading: dict[str, Any] | None = None
        self.read_at: float | None = None
        self.error: str | None = None
        self._activities: dict[str, dict[str, Any]] = {}
        self._orders: dict[str, dict[str, Any]] = {}
        self._full_at = float("-inf")

    def _read(self) -> dict[str, Any]:
        now = self.clock()
        # The book first: a fill the book holds is at the broker already, so the broker's record read after it has it.
        book = read_book(self.root, self.start_at)
        full = now - self._full_at >= FULL_EVERY_SECONDS
        start = epoch(self.start_at) or 0.0
        after = self.start_at if full else iso(max(start, now - WINDOW_SECONDS))
        # The broker's orders from the earliest placing of a book order that still changed since the reset: an order
        # placed before it that filled after it is the reset's, and its legs' ids must find it.
        orders_from = book.get("orders_from")
        order_after = iso(min(epoch(after) or start, orders_from)) if full and orders_from is not None else after
        activities, orders = activities_after(self.broker, after), orders_after(self.broker, order_after)
        if full:
            self._activities, self._orders, self._full_at = {}, {}, now
        self._activities.update((str(a["id"]), a) for a in activities)
        self._orders.update((o["id"], o) for o in orders)
        ordered = sorted(self._activities.values(), key=lambda a: str(a.get("id")))
        return {"as_of": iso(now), **classify(ordered, list(self._orders.values()), book, now=now,
                                              shares_held=lambda: shares_held(self.broker))}

    def _refresh(self) -> None:
        try:
            reading, error = dict(self.reader()), None
        except Exception as exc:  # noqa: BLE001 - an unreadable account is no reading, never a zero one
            reading, error = None, f"{type(exc).__name__}: {str(exc)[:200]}"
            if not isinstance(exc, Unreadable):
                self._full_at = float("-inf")  # the caches may be half-updated: the next read is a whole one
        with self.lock:
            if reading is not None:
                self.reading, self.read_at = reading, self.clock()
            self.error, self.busy = error, False

    def read(self) -> dict[str, Any] | None:
        now = self.clock()
        with self.lock:
            due = not self.busy and now - self.attempted >= EVERY_SECONDS
            if due:
                self.busy, self.attempted = True, now
        if due:
            if self.threaded:
                threading.Thread(target=self._refresh, daemon=True, name="positions-ledger").start()
            else:
                self._refresh()
        with self.lock:
            fresh = self.read_at is not None and 0 <= self.clock() - self.read_at <= FRESH_SECONDS
            return dict(self.reading) if fresh and self.reading is not None else None

    def problems(self) -> list[str]:
        """The latest reading's problems and what keeps Profit unknown (for the House's alerts; `error` is the latest
        read's failure, if it failed)."""
        with self.lock:
            reading = self.reading or {}
            return list(dict.fromkeys([*(reading.get("blocking") or []), *(reading.get("problems") or [])]))

    def saved(self) -> dict[str, Any] | None:
        """The last reading and when it was read, as JSON (Decimals as strings), for `restore` after a restart."""
        with self.lock:
            if self.reading is None or self.read_at is None:
                return None
            reading = dict(self.reading)
        for field in MONEY_FIELDS:
            if reading.get(field) is not None:
                reading[field] = format(Decimal(str(reading[field])), "f")
        reading["fees_by_pid"] = {str(pid): format(Decimal(str(value)), "f") for pid, value in (reading.get("fees_by_pid") or {}).items()}
        return {"read_at": self.read_at, "start_at": self.start_at, "reading": reading}

    def restore(self, saved: Any) -> bool:
        """Take a reading `saved` before a restart when it is this record's (the same reset) and still fresh."""
        try:
            read_at, reading = float(saved["read_at"]), dict(saved["reading"])
            if saved.get("start_at") != self.start_at or not 0 <= self.clock() - read_at <= FRESH_SECONDS:
                return False
            for field in MONEY_FIELDS:
                reading[field] = cents(reading[field])
            reading["fees_by_pid"] = {str(pid): cents(value) for pid, value in (reading.get("fees_by_pid") or {}).items()}
            reading["blocking"] = [str(x) for x in reading.get("blocking") or []]
            reading["problems"] = [str(x) for x in reading.get("problems") or []]
        except (KeyError, TypeError, ValueError, InvalidOperation, AttributeError):
            return False
        with self.lock:
            if self.reading is None:
                self.reading, self.read_at = reading, read_at
        return True
