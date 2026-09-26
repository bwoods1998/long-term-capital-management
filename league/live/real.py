"""The real book: every structure real money holds at the Brokerage Account, which family holds it, and the order path.

The options-swarm run, Wave 5 (Sept 26, 2026; the plan's "Money" -> "The order path" and "Reconciliation"). The venue
holds legs, netted per contract across the whole account; this book knows which family's structure each leg belongs
to. It is the only writer of real orders, and every rule of the order path is enforced here before anything leaves
(the gateway enforces its own caps again from its own reading of the account):

- **Written before sent.** An order's row (`<root>/live.sqlite`) is committed with status `pending` and its client
  order id (`lv-<oid>-<family>`, from the row's own id) BEFORE the POST. A lost answer is `unknown` and is looked up by
  that id; a restart finds `pending`/`unknown` rows and looks them up the same way. Nothing is ever re-sent: an intent
  is a minute's decision, and the program decides again.
- **One order stream per contract.** No order goes while another working order (any family's) touches one of its
  contracts: the venue refuses opposing orders on one contract (403, wash-trade protection), and one stream a contract
  is the simple rule that can never cross.
- **No opposite side.** An open that would take the opposite side of a contract the account holds (any family, this one
  included) is refused: positions net per contract across the account, so one family's sale would close another's leg.
- **Buying power reserved:** maximum loss plus fees plus `order_path.bp_buffer` of it, against the account's
  `options_buying_power` less what working opens already reserve.
- **The day's order count:** every leg of every order and of every cancel counts (until the venue's counting is
  verified), under `order_path.max_orders_day`; opens stop early enough to leave every open structure room to close.
- **Expiry day.** No new opening order on an expiring contract from the open cutoff (15:00 ET; index 0DTE included);
  working opens on expiring contracts are cancelled there. An expiring EQUITY-option structure with any leg in or
  within `near_money_share` of the money is closed with one multi-leg order from `expiry_close_lead_minutes` before the
  close cutoff (15:10 ET; 15:25 SPY/QQQ), re-sent at the natural each minute with a growing concession until it fills
  (legs left at a physically settled expiry become shares the account cannot carry).
- **Types.** Real money opens only the five one-order-closeable types (`options_money.real_types`), credit types only
  once credit is allowed; `day` time in force; an order is never replaced, only cancelled and sent anew.

Fills: a multi-leg parent's `legs` give each leg's cumulative `filled_qty` and `filled_avg_price`; the structure has
filled as many whole units as every leg covers (a leg ahead of the others waits), at the value sum(side x ratio x leg
price). A leg that ends ahead of the others (an uneven multi-leg fill) is a mismatch: reconciliation freezes new entries
and says so.

Reconciliation: the account's option positions per contract against this book's legs (open positions and the filled
part of working opens), and the account's working orders against this book's; the legacy LTC dust (0.000373062,
below the venue's minimum) is a known holding outside P&L. A mismatch seen on two readings in a row freezes new real
entries (exits pass) and says why; two clean readings in a row lift it.
"""

from __future__ import annotations

import datetime as dt
import math
import re
import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Callable, Iterable, Mapping, Sequence

from .. import structure_core as core
from ..gym import legs as L
from ..gym import venue as V
from . import money as M
from .state import LiveState, dumps, loads
from .venue import TERMINAL, WORKING, Account, Submitted, dec, occ_parts

PREFIX = "lv-"
#: The Brokerage Account's legacy crypto dust, below the venue's minimum order: a known holding outside P&L.
KNOWN_DUST = {"LTCUSD": Decimal("0.000373062")}
_SLUG = re.compile(r"[^a-z0-9-]+")


def client_id(oid: int, family: str, *, nonce: str = "") -> str:
    """`lv-<process nonce>-<row id>-<family>`: the nonce is drawn at every process start (`LiveState.nonce`), so a new or
    rolled-back state's ids are new even where its row ids repeat."""
    head = f"{PREFIX}{nonce}-" if nonce else PREFIX
    return f"{head}{int(oid):07d}-{_SLUG.sub('-', str(family).lower())[:40].strip('-')}"


def limit_price(value: float, action: str) -> str:
    """The Gym's value a share as Alpaca's signed multi-leg `limit_price`: a debit positive, a credit negative. An open
    pays its value (a credit structure's value is negative); a close receives its value, so its price is the negative."""
    x = value if action == "open" else -value
    x = round(x + 0.0, 2)
    return "0.00" if x == 0 else f"{x:.2f}"


@dataclass
class RLeg:
    symbol: str
    side: int          # +1 long, -1 short (in the structure)
    ratio: int
    is_call: bool
    strike: float
    expiry: str        # YYYY-MM-DD
    key: int

    def row(self) -> dict:
        return {"symbol": self.symbol, "side": self.side, "ratio": self.ratio, "is_call": self.is_call,
                "strike": self.strike, "expiry": self.expiry, "key": self.key}

    @classmethod
    def of(cls, x: Mapping[str, Any]) -> "RLeg":
        return cls(str(x["symbol"]), int(x["side"]), int(x["ratio"]), bool(x["is_call"]), float(x["strike"]),
                   str(x["expiry"]), int(x["key"]))


def legs_json(legs: Sequence[RLeg]) -> str:
    return dumps([leg.row() for leg in legs])


@dataclass
class RPosition:
    pid: int
    instance: str
    family: str
    type: str
    root: str
    legs: list[RLeg]
    qty: int
    opened_qty: int
    entry: float                 # value a share, averaged over the open's fills
    max_loss_share: float
    collateral: float
    fees: float = 0.0
    cash: float = 0.0            # every cash flow of this trade, fees included
    opened_at: float = 0.0
    opened_day: str = ""
    opened_minute: int = 0
    tag: str = ""
    note: str = ""
    status: str = "open"         # open | closed | awaiting_expiry
    closed_at: float | None = None
    exit_value_qty: float = 0.0
    reason: str = ""
    tuition: bool = False
    info: dict = field(default_factory=dict)

    @property
    def expiry(self) -> str:
        return min(leg.expiry for leg in self.legs)

    @property
    def max_loss(self) -> float:
        return self.max_loss_share * V.MULTIPLIER * self.qty

    def code(self) -> str:
        spec = core.classify(self.type, [core.leg(leg.symbol, leg.side, leg.ratio) for leg in self.legs])
        return spec.code

    def row(self) -> dict:
        return {"pid": self.pid, "instance": self.instance, "family": self.family, "type": self.type, "root": self.root,
                "legs": legs_json(self.legs), "qty": self.qty, "opened_qty": self.opened_qty, "entry": self.entry,
                "max_loss_share": self.max_loss_share, "collateral": self.collateral, "fees": self.fees, "cash": self.cash,
                "opened_at": self.opened_at, "opened_day": self.opened_day, "opened_minute": self.opened_minute,
                "tag": self.tag, "note": self.note, "status": self.status, "closed_at": self.closed_at,
                "exit_value_qty": self.exit_value_qty, "reason": self.reason, "tuition": int(self.tuition),
                "info": dumps(self.info)}

    @classmethod
    def of(cls, r: Mapping[str, Any]) -> "RPosition":
        return cls(int(r["pid"]), r["instance"], r["family"], r["type"], r["root"], [RLeg.of(x) for x in loads(r["legs"], [])],
                   int(r["qty"]), int(r["opened_qty"]), float(r["entry"]), float(r["max_loss_share"]), float(r["collateral"]),
                   float(r["fees"]), float(r["cash"]), float(r["opened_at"]), r["opened_day"], int(r["opened_minute"]),
                   r["tag"] or "", r["note"] or "", r["status"], r["closed_at"], float(r["exit_value_qty"]), r["reason"] or "",
                   bool(r["tuition"]), loads(r["info"], {}) or {})


@dataclass
class ROrder:
    oid: int
    client_id: str
    instance: str
    family: str
    action: str                  # open | close
    type: str
    root: str
    legs: list[RLeg]
    qty: int
    limit_value: float
    limit_price: str
    tif: int | None              # minutes; None the day; 0 immediate-or-cancel
    placed_at: float
    day: str
    placed_minute: int
    status: str = "pending"      # pending | working | unknown | filled | cancelled | expired | rejected | refused | lost
    venue_id: str | None = None
    filled_qty: int = 0
    fill_value: float = 0.0      # the average value a share of what has filled
    pid: int | None = None
    forced: bool = False
    reserve: float = 0.0         # buying power it holds while it works (an open)
    max_loss: float = 0.0        # an open's maximum loss at its limit, all of it
    fees_est: float = 0.0
    tuition: bool = False
    why: str = ""
    answer: dict = field(default_factory=dict)
    updated_at: float = 0.0
    cancel_sent: float | None = None
    attempts: int = 0
    dispatched: bool = False     # reached the venue (the gateway reserved it)
    uneven: bool = False

    @property
    def working(self) -> bool:
        return self.status in ("pending", "working", "unknown")

    @property
    def remaining(self) -> int:
        return max(0, self.qty - self.filled_qty)

    @property
    def contracts(self) -> int:
        return sum(leg.ratio for leg in self.legs) * self.qty

    def row(self) -> dict:
        answer = dict(self.answer)
        answer["dispatched"] = self.dispatched
        answer["uneven"] = self.uneven
        return {"oid": self.oid, "client_id": self.client_id, "venue_id": self.venue_id, "instance": self.instance,
                "family": self.family, "action": self.action, "type": self.type, "root": self.root,
                "legs": legs_json(self.legs), "qty": self.qty, "limit_value": self.limit_value, "limit_price": self.limit_price,
                "tif": self.tif, "placed_at": self.placed_at, "day": self.day, "placed_minute": self.placed_minute,
                "status": self.status, "filled_qty": self.filled_qty, "fill_value": self.fill_value, "pid": self.pid,
                "forced": int(self.forced), "reserve": self.reserve, "max_loss": self.max_loss, "fees_est": self.fees_est,
                "tuition": int(self.tuition), "why": self.why, "answer": dumps(answer), "updated_at": self.updated_at,
                "cancel_sent": self.cancel_sent, "attempts": self.attempts}

    @classmethod
    def of(cls, r: Mapping[str, Any]) -> "ROrder":
        answer = loads(r["answer"], {}) or {}
        return cls(int(r["oid"]), r["client_id"], r["instance"], r["family"], r["action"], r["type"], r["root"],
                   [RLeg.of(x) for x in loads(r["legs"], [])], int(r["qty"]), float(r["limit_value"]), r["limit_price"],
                   r["tif"], float(r["placed_at"]), r["day"], int(r["placed_minute"]), r["status"], r["venue_id"],
                   int(r["filled_qty"]), float(r["fill_value"]), r["pid"], bool(r["forced"]), float(r["reserve"]),
                   float(r["max_loss"]), float(r["fees_est"]), bool(r["tuition"]), r["why"] or "", answer,
                   float(r["updated_at"]), r["cancel_sent"], int(r["attempts"] or 0), bool(answer.get("dispatched")),
                   bool(answer.get("uneven")))


def mleg_body(order: ROrder) -> dict[str, Any]:
    """Alpaca's multi-leg order (the gateway's `structureOrder` reads exactly these fields)."""
    opening = order.action == "open"
    legs = []
    for leg in order.legs:
        buys = (leg.side > 0) == opening
        intent = ("buy_to_open" if leg.side > 0 else "sell_to_open") if opening else ("sell_to_close" if leg.side > 0 else "buy_to_close")
        legs.append({"symbol": leg.symbol, "ratio_qty": str(leg.ratio), "side": "buy" if buys else "sell", "position_intent": intent})
    return {"order_class": "mleg", "qty": str(order.qty), "type": "limit", "limit_price": order.limit_price,
            "time_in_force": "day", "legs": legs, "client_order_id": order.client_id}


def single_leg_body(order: ROrder) -> dict[str, Any]:
    """One leg of a broken structure closed alone (the gateway admits a sell_to_close of a contract held long and a
    buy_to_close of one held short): `qty` contracts at a positive premium limit."""
    leg = order.legs[0]
    selling = leg.side > 0
    return {"symbol": leg.symbol, "qty": str(order.qty), "side": "sell" if selling else "buy", "type": "limit",
            "limit_price": order.limit_price, "time_in_force": "day",
            "position_intent": "sell_to_close" if selling else "buy_to_close", "client_order_id": order.client_id}


def leg_fees(root: str, legs: Sequence[RLeg], prices: Sequence[float], qty: int, action: str) -> float:
    total = 0.0
    for leg, price in zip(legs, prices):
        selling = (leg.side > 0) != (action == "open")
        total += V.leg_fee(root, leg.ratio * qty, price if math.isfinite(price) else 0.0, sell=selling)
    return round(total, 2)


def structure_fill(order: ROrder, row: Mapping[str, Any]) -> tuple[int, float | None, list[float], bool] | None:
    """(whole structures filled, their average value a share, each leg's average price, uneven) from a venue order row,
    or None when its legs cannot be read yet."""
    rows = row.get("legs")
    if not isinstance(rows, list) or not rows:
        return None
    by_symbol = {str(r.get("symbol") or "").upper(): r for r in rows if isinstance(r, Mapping)}
    parent = dec(row.get("filled_qty"))
    units = int(parent) if parent is not None else 0
    prices, leg_units = [], []
    for leg in order.legs:
        r = by_symbol.get(leg.symbol)
        if r is None:
            return None
        filled = dec(r.get("filled_qty")) or Decimal(0)
        leg_units.append((filled, leg.ratio))
        price = dec(r.get("filled_avg_price"))
        prices.append(float(price) if price is not None else math.nan)
    whole = min([int(f // ratio) for f, ratio in leg_units] + [units])
    uneven = any(f != whole * ratio for f, ratio in leg_units)
    if whole <= 0:
        return 0, None, prices, uneven
    if any(not math.isfinite(p) for p in prices):
        return None
    value = sum(leg.side * leg.ratio * p for leg, p in zip(order.legs, prices))
    return whole, round(value, 6), prices, uneven


class RealBook:
    """The real book and its order path (the module docstring)."""

    def __init__(self, state: LiveState, account: Account, table: M.Table, *, clock: Callable[[], float] = time.time,
                 record: Callable[..., Any] | None = None):
        self.state, self.account, self.table, self.clock = state, account, table, clock
        self.record = record or (lambda *a, **k: None)
        self.positions: dict[int, RPosition] = {}
        self.orders: dict[int, ROrder] = {}
        self.frozen = ""                 # why new real entries are frozen by reconciliation ("" none)
        self.mismatch: list[str] = []
        self._streak = {"bad": 0, "good": 0}
        self.closed_since: dict[str, list[dict]] = {}
        self.rejects_since: dict[str, list[str]] = {}
        self.load()

    # ------------------------------------------------------------------ state
    def load(self) -> None:
        self.positions = {p.pid: p for p in (RPosition.of(r) for r in self.state.rows(
            "SELECT * FROM positions WHERE status IN ('open', 'awaiting_expiry')"))}
        self.orders = {o.oid: o for o in (ROrder.of(r) for r in self.state.rows(
            "SELECT * FROM orders WHERE status IN ('pending', 'working', 'unknown')"))}
        frozen = self.state.get("recon", {}) or {}
        self.frozen = str(frozen.get("frozen") or "")
        self._streak = {"bad": int(frozen.get("bad") or 0), "good": int(frozen.get("good") or 0)}

    def _save_order(self, order: ROrder) -> None:
        order.updated_at = self.clock()
        self.state.upsert("orders", order.row(), "oid")
        if not order.working:
            self.orders.pop(order.oid, None)
        else:
            self.orders[order.oid] = order

    def _save_position(self, pos: RPosition) -> None:
        self.state.upsert("positions", pos.row(), "pid")
        if pos.status in ("closed", "unpriced_close"):
            self.positions.pop(pos.pid, None)
        else:
            self.positions[pos.pid] = pos

    def _next(self, table: str, column: str) -> int:
        row = self.state.rows(f"SELECT COALESCE(MAX({column}), 0) AS top FROM {table}")
        return int(row[0]["top"]) + 1

    # ------------------------------------------------------------------ what is at risk
    def family_positions(self, family: str) -> list[RPosition]:
        return [p for p in self.positions.values() if p.family == family and p.qty > 0]

    def instance_positions(self, instance: str) -> list[RPosition]:
        return [p for p in self.positions.values() if p.instance == instance and p.qty > 0]

    def instance_orders(self, instance: str) -> list[ROrder]:
        return [o for o in self.orders.values() if o.instance == instance and o.working]

    def exposure(self, family: str, *, day: str, week_start: str) -> M.Exposure:
        fam_open = sum(1 for p in self.family_positions(family)) + sum(
            1 for o in self.orders.values() if o.working and o.action == "open" and o.family == family and o.pid is None)
        fam_loss = sum(p.max_loss for p in self.family_positions(family)) + sum(
            o.max_loss * o.remaining / max(1, o.qty) for o in self.orders.values() if o.working and o.action == "open" and o.family == family)
        book = sum(p.max_loss for p in self.positions.values() if p.qty > 0) + sum(
            o.max_loss * o.remaining / max(1, o.qty) for o in self.orders.values() if o.working and o.action == "open")
        sent = self.state.rows("SELECT day, max_loss, qty, filled_qty, status, tuition, answer FROM orders WHERE action='open' AND day>=?",
                               (week_start,))
        day_opened = Decimal(0)
        tuition_day = Decimal(0)
        tuition_week = Decimal(0)
        for r in sent:
            answer = loads(r["answer"], {}) or {}
            dispatched = bool(answer.get("dispatched")) or r["status"] in ("pending", "unknown")
            if r["day"] == day and dispatched:
                day_opened += M.D(r["max_loss"])
            if r["tuition"]:
                # What tuition risks: the filled part, and what a working order may still fill.
                live = r["status"] in ("pending", "working", "unknown")
                units = int(r["qty"]) if live else int(r["filled_qty"])
                loss = M.D(r["max_loss"]) * units / max(1, int(r["qty"]))
                tuition_week += loss
                if r["day"] == day:
                    tuition_day += loss
        return M.Exposure(family_open=fam_open, family_loss=M.D(round(fam_loss, 2)), book_loss=M.D(round(book, 2)),
                          day_opened=day_opened, tuition_day=tuition_day, tuition_week=tuition_week)

    def reserved(self) -> float:
        return sum(o.reserve * o.remaining / max(1, o.qty) for o in self.orders.values() if o.working and o.action == "open")

    def held_net(self) -> dict[str, int]:
        """Contracts per OCC symbol this book holds or may hold (open positions, and working opens' remaining units),
        signed (long +)."""
        out: dict[str, int] = {}
        for p in self.positions.values():
            for leg in p.legs:
                out[leg.symbol] = out.get(leg.symbol, 0) + leg.side * self.leg_remaining(p, leg)
        for o in self.orders.values():
            if o.working and o.action == "open":
                for leg in o.legs:
                    out[leg.symbol] = out.get(leg.symbol, 0) + leg.side * leg.ratio * o.remaining
        return out

    @staticmethod
    def leg_remaining(pos: RPosition, leg: RLeg) -> int:
        """Contracts of one leg the account still holds for this position: its units x ratio, less what an expiry, an
        assignment or an exercise took out (`gone`) and what single-leg closes sold or bought back (`leg_closed`)."""
        gone = int((pos.info.get("gone") or {}).get(leg.symbol, 0))
        closed = int((pos.info.get("leg_closed") or {}).get(leg.symbol, 0))
        return max(0, leg.ratio * pos.qty - gone - closed)

    def expected_positions(self) -> dict[str, int]:
        """What the venue should hold per contract: open positions (their filled units, less legs gone) only."""
        out: dict[str, int] = {}
        for p in self.positions.values():
            if p.qty <= 0:
                continue
            for leg in p.legs:
                out[leg.symbol] = out.get(leg.symbol, 0) + leg.side * self.leg_remaining(p, leg)
        return {k: v for k, v in out.items() if v != 0}

    def closing_order(self, pid: int) -> ROrder | None:
        """The working close of a position, if one is out."""
        for order in self.orders.values():
            if order.working and order.action == "close" and order.pid == pid:
                return order
        return None

    def busy(self) -> set[str]:
        return {leg.symbol for o in self.orders.values() if o.working for leg in o.legs}

    # ------------------------------------------------------------------ the order count
    def count_today(self, day: str) -> int:
        by_day = self.state.get("counts_by_day", {}) or {}
        if day in by_day:
            return int(by_day[day])
        row = self.state.get("count", {}) or {}
        return int(row.get("legs") or 0) if row.get("day") == day else 0

    def _count(self, day: str, legs: int) -> None:
        by_day = self.state.get("counts_by_day", {}) or {}
        row = self.state.get("count", {}) or {}
        if row.get("day"):
            by_day.setdefault(row["day"], int(row.get("legs") or 0))
        by_day[day] = max(0, int(by_day.get(day, 0)) + int(legs))
        self.state.put("counts_by_day", dict(sorted(by_day.items())[-14:]))
        if day >= str(row.get("day") or ""):
            self.state.put("count", {"day": day, "legs": by_day[day]})

    def _count_dispatch(self, order: ROrder) -> None:
        """Reserve before I/O; recovered venue orders acquire the same durable, idempotent reservation."""
        with self.state.transaction():
            inserted = self.state.execute("INSERT OR IGNORE INTO dispatch_counts(oid, day, legs) VALUES(?,?,?)",
                                           (order.oid, order.day, len(order.legs))).rowcount
            if inserted and not order.dispatched:
                self._count(order.day, len(order.legs))

    def _refund_dispatch(self, order: ROrder) -> None:
        with self.state.transaction():
            rows = self.state.rows("SELECT day, legs FROM dispatch_counts WHERE oid=?", (order.oid,))
            if rows:
                self._count(rows[0]["day"], -int(rows[0]["legs"]))
                self.state.execute("DELETE FROM dispatch_counts WHERE oid=?", (order.oid,))

    def exit_reserve(self) -> int:
        """Order-count room every open structure needs to close: its legs, twice (a close and one cancel of it)."""
        return sum(2 * len(p.legs) for p in self.positions.values() if p.qty > 0)

    # ------------------------------------------------------------------ the order path's refusals
    def forced_reserve(self, day: str) -> int:
        """Order-count room only the House's own exits may use: every structure expiring today or broken, its legs
        twice (a close and a re-price), and room for an assignment's share sales."""
        legs = sum(2 * len(p.legs) for p in self.positions.values()
                   if p.qty > 0 and (p.expiry <= day or p.info.get("broken")))
        return legs + 4

    def blockers(self, legs: Sequence[RLeg], *, pid: int | None = None) -> list[ROrder]:
        """The working orders (any family's) on these contracts, but a position's own close."""
        symbols = {leg.symbol for leg in legs}
        return [o for o in self.orders.values() if o.working and not (pid is not None and o.pid == pid and o.action != "open")
                and any(leg.symbol in symbols for leg in o.legs)]

    def path_refusal(self, legs: Sequence[RLeg], *, opening: bool, day: str, extra_legs: int = 0,
                     house: bool = False) -> str | None:
        """Why this order may not go now (the contract rules and the day's count), or None. An open must leave room
        for every open structure's close; a program's close (or cancel) must leave the room only the House's forced
        exits may use (`forced_reserve`); the House's own exits (`house`) meet only the gateway's count."""
        busy = self.busy()
        clash = [leg.symbol for leg in legs if leg.symbol in busy]
        if clash:
            return (f"one order stream per contract: {', '.join(sorted(set(clash)))} already has a working order "
                    "(the venue refuses opposing orders on one contract)")
        if opening:
            held = self.held_net()
            opposite = [leg.symbol for leg in legs if held.get(leg.symbol, 0) * leg.side < 0]
            if opposite:
                return (f"positions net across the account: this open takes the other side of {', '.join(sorted(set(opposite)))}, "
                        "which the account holds")
            count = len(legs) + extra_legs
            room = self.table.max_orders_day - self.count_today(day) - self.exit_reserve()
            if count > room:
                return (f"the day's order count: {self.count_today(day)} legs sent of {self.table.max_orders_day}, and "
                        f"{self.exit_reserve()} kept for closing what is open")
        elif not house:
            return self.count_refusal(len(legs) + extra_legs, day=day)
        return None

    def count_refusal(self, legs: int, *, day: str) -> str | None:
        """A program's close or cancel of `legs` legs: refused when it would eat the House's forced-exit room."""
        room = self.table.max_orders_day - self.count_today(day) - self.forced_reserve(day)
        if legs > room:
            return (f"the day's order count: {self.count_today(day)} legs sent of {self.table.max_orders_day}, and "
                    f"{self.forced_reserve(day)} kept for the House's own exits (expiring and broken structures)")
        return None

    # ------------------------------------------------------------------ sending
    def new_order(self, *, instance: str, family: str, action: str, type_: str, root: str, legs: list[RLeg], qty: int,
                  limit_value: float, tif: int | None, day: str, minute: int, pid: int | None = None, forced: bool = False,
                  reserve: float = 0.0, max_loss: float = 0.0, fees_est: float = 0.0, tuition: bool = False, why: str = "") -> ROrder:
        with self.state.transaction():
            oid = self._next("orders", "oid")
            price = f"{round(abs(limit_value), 2):.2f}" if action == "close_leg" else limit_price(limit_value, action)
            order = ROrder(oid, client_id(oid, family, nonce=self.state.nonce), instance, family, action,
                           type_, root, list(legs), int(qty),
                           float(limit_value), price, tif, self.clock(), day, int(minute),
                           pid=pid, forced=forced, reserve=float(reserve), max_loss=float(max_loss), fees_est=float(fees_est),
                           tuition=tuition, why=str(why)[:300])
            order.updated_at = self.clock()
            self.state.upsert("orders", order.row(), "oid")
        self.orders[oid] = order
        return order

    def send(self, order: ROrder) -> ROrder:
        """POST the order written as `pending`. Never retried (the module docstring)."""
        body = single_leg_body(order) if order.action == "close_leg" else mleg_body(order)
        self._count_dispatch(order)
        result: Submitted = self.account.submit(body, exit=order.action != "open")
        order.attempts += 1
        if result.ok:
            order.dispatched = True
            order.venue_id = str(result.order.get("id"))
            order.status = "working"
            order.answer = {"status": result.order.get("status"), "at": self.clock()}
            self._absorb(order, result.order)
        elif result.unknown:
            order.dispatched = True
            order.status = "unknown"
            order.answer = {"error": result.error}
        elif not result.sent:
            self._refund_dispatch(order)
            order.status = "refused"
            order.answer = {"error": result.error, "house": True}
        else:
            # A gateway refusal says {"error": ...} and never reached the venue; the venue's own answer carries its
            # "message" (and "code"): that one did, and the gateway's caps counted it.
            payload = result.order or {}
            gateway = "error" in payload and "code" not in payload
            order.dispatched = not gateway
            order.status = "refused" if gateway else "rejected"
            order.answer = {"error": result.error, "status": result.status, "gateway": gateway}
            if gateway:
                self._refund_dispatch(order)
        self._save_order(order)
        self.record("live.order", {"oid": order.oid, "client_id": order.client_id, "family": order.family,
                                   "instance": order.instance, "action": order.action, "type": order.type, "root": order.root,
                                   "qty": order.qty, "status": order.status, "forced": order.forced, "tuition": order.tuition,
                                   "why": order.why, "_limit_price": order.limit_price, "_legs": [l.symbol for l in order.legs],
                                   "_answer": order.answer}, agent=order.family)
        if order.status in ("refused", "rejected"):
            self._reject(order.instance, f"the {'gateway' if order.status == 'refused' else 'venue'} refused the order: {order.answer.get('error')}")
        return order

    def cancel(self, order: ROrder, why: str) -> bool:
        if not order.working or order.venue_id is None:
            return False
        if order.cancel_sent and self.clock() - order.cancel_sent < 50:
            return False
        from zoneinfo import ZoneInfo

        # The DELETE belongs to today's action count, even for an earlier session's resting order. Persist the
        # reservation before I/O, so a crash after the venue accepts the cancel cannot erase it.
        with self.state.transaction():
            order.cancel_sent = self.clock()
            today = dt.datetime.fromtimestamp(order.cancel_sent, ZoneInfo("America/New_York")).date().isoformat()
            self._count(today, len(order.legs))
            self._save_order(order)
        done, error = self.account.cancel(order.venue_id)
        order.answer = {**order.answer, "cancel": why[:200], "cancel_error": error or None}
        self._save_order(order)
        self.record("live.cancel", {"oid": order.oid, "family": order.family, "why": why[:200], "ok": done,
                                    "_error": error}, agent=order.family)
        return done

    # ------------------------------------------------------------------ reading the venue's orders
    def ingest(self, rows: Iterable[Mapping[str, Any]]) -> list[dict]:
        """The venue's order rows (this session's): each of this book's orders brought up to date. Returns the foreign
        working orders (not this book's)."""
        by_client = {}
        foreign = []
        for row in rows:
            cid = str(row.get("client_order_id") or "")
            if cid.startswith(PREFIX + "shares-"):
                continue  # the close of an assignment's shares (`OptionsLive._close_shares`): not a structure's order
            if cid.startswith(PREFIX):
                by_client[cid] = row
            elif str(row.get("status") or "") in WORKING:
                foreign.append(dict(row))
        mine = {o.client_id for o in self.orders.values()}
        for cid, row in by_client.items():
            if cid in mine:
                continue
            known = self.state.rows("SELECT * FROM orders WHERE client_id=?", (cid,))
            if known and known[0]["status"] in ("lost", "refused"):
                # An order this book had given up on turned up at the venue: take it back and book what it did.
                order = ROrder.of(known[0])
                order.status = "working"
                self.orders[order.oid] = order
                self.record("live.order", {"oid": order.oid, "family": order.family, "status": "found",
                                           "venue_status": str(row.get("status") or "")}, agent=order.family)
            elif not known and str(row.get("status") or "") in WORKING:
                foreign.append(dict(row))
        for order in list(self.orders.values()):
            row = by_client.get(order.client_id)
            if row is not None:
                self._absorb(order, row)
                self._save_order(order)
        return foreign

    def look_up(self, *, today: str, seen: Iterable[str] = (), limit: int = 5) -> None:
        """Orders whose outcome is unknown (a lost answer, or `pending` found after a restart), and working orders the
        session's order read did not show (an earlier day's): asked for by client id."""
        shown = set(seen)
        stale = [o for o in self.orders.values() if o.status == "working" and o.client_id not in shown and o.day < today]
        for order in ([o for o in self.orders.values() if o.status in ("unknown", "pending")] + stale)[:limit]:
            if order.status == "pending" and self.clock() - order.placed_at < 30:
                continue  # being sent right now
            try:
                row = self.account.order_by_client_id(order.client_id)
            except Exception as exc:  # noqa: BLE001 - asked again next minute
                order.answer = {**order.answer, "lookup_error": str(exc)[:200]}
                continue
            if row is None and order.status == "working":
                order.answer = {**order.answer, "lookup": "a working order the venue no longer shows"}
                order.status = "lost"
            elif row is None:
                order.attempts += 1
                if order.attempts >= 4 or self.clock() - order.placed_at > 600:
                    order.status = "lost"
                    order.answer = {**order.answer, "lookup": "not found at the venue by its client id"}
                    self.record("live.order", {"oid": order.oid, "family": order.family, "status": "lost"}, agent=order.family)
            else:
                self._absorb(order, row)
            self._save_order(order)

    def _absorb(self, order: ROrder, row: Mapping[str, Any]) -> None:
        """Bring one order up to the venue's row: new whole-structure fills booked, the status carried."""
        self._count_dispatch(order)
        order.dispatched = True
        order.venue_id = str(row.get("id") or order.venue_id or "") or order.venue_id
        status = str(row.get("status") or "")
        if order.action == "close_leg":
            fill = _single_fill(order, row)
        else:
            fill = structure_fill(order, row)
        if fill is not None:
            units, value, prices, uneven = fill
            order.uneven = uneven
            if units > order.filled_qty and value is not None:
                dq = units - order.filled_qty
                increment = (value * units - order.fill_value * order.filled_qty) / dq
                # The fill, the position and the order's progress commit together: a crash between them would book the
                # same fill again at the next reading.
                with self.state.transaction():
                    if order.action == "close_leg":
                        self._book_leg(order, dq, increment)
                    else:
                        self._book(order, dq, increment, prices)
                    order.fill_value = value
                    order.filled_qty = units
                    order.updated_at = self.clock()
                    self.state.upsert("orders", order.row(), "oid")
        if status in TERMINAL:
            if fill is None and dec(row.get("filled_qty")) not in (None, Decimal(0)):
                # Filled at the venue, legs not readable yet: keep it working until they are.
                order.status = "working"
                return
            order.status = {"filled": "filled", "canceled": "cancelled", "expired": "expired", "done_for_day": "expired",
                            "rejected": "rejected", "replaced": "cancelled", "stopped": "cancelled", "suspended": "cancelled"}[status]
            if order.status == "filled" and order.filled_qty < order.qty:
                order.status = "working"  # the parent says filled; its legs have not all said so yet
                return
            order.answer = {**order.answer, "final": status, "reject_reason": row.get("reject_reason") if status == "rejected" else None}
            if status == "rejected":
                self._reject(order.instance, f"the venue rejected the order: {str(row.get('reject_reason') or '')[:160]}")
        elif status:
            order.status = "working"

    # ------------------------------------------------------------------ fills
    def _book(self, order: ROrder, dq: int, value: float, prices: Sequence[float]) -> None:
        now = self.clock()
        fees = leg_fees(order.root, order.legs, prices, dq, order.action)
        if order.action == "open":
            pos = self.positions.get(order.pid) if order.pid else None
            collateral = float(_collateral(order.type, order.legs))
            if pos is None:
                with self.state.transaction():
                    pid = self._next("positions", "pid")
                    pos = RPosition(pid, order.instance, order.family, order.type, order.root, list(order.legs), 0, 0, value,
                                    _loss_share(order.type, value, collateral), collateral, opened_at=now, opened_day=order.day,
                                    opened_minute=order.placed_minute, tag=order.why[:80], tuition=order.tuition,
                                    info={"order": order.oid})
                    self.state.upsert("positions", pos.row(), "pid")
                order.pid = pid
            total = pos.opened_qty + dq
            pos.entry = (pos.entry * pos.opened_qty + value * dq) / total
            pos.max_loss_share = _loss_share(pos.type, pos.entry, pos.collateral)
            pos.qty += dq
            pos.opened_qty = total
            pos.cash += -value * V.MULTIPLIER * dq - fees
            pos.fees += fees
            self._save_position(pos)
            self.state.execute("INSERT INTO fills(oid, pid, qty, value, fees, at) VALUES(?,?,?,?,?,?)",
                               (order.oid, pos.pid, dq, value, fees, now))
            code = _code(pos)
            self.record("book.fill", {"source": "venue", "side": "buy", "real_money": True, "quantity": dq,
                                      "instrument": {"market_id": code, "asset_class": "option", "multiplier": 100},
                                      "max_loss_usd": round(pos.max_loss_share * V.MULTIPLIER * dq, 2),
                                      "reason": order.why[:240], "_price": value, "_fees": fees, "_order": order.oid},
                        agent=order.family)
        else:
            pos = self.positions.get(order.pid or -1)
            if pos is None:
                self.record("live.alert", {"what": "a close filled for a position the book does not hold", "oid": order.oid},
                            agent=order.family)
                return
            dq = min(dq, pos.qty)
            pos.qty -= dq
            pos.exit_value_qty += value * dq
            pos.cash += value * V.MULTIPLIER * dq - fees
            pos.fees += fees
            self.state.execute("INSERT INTO fills(oid, pid, qty, value, fees, at) VALUES(?,?,?,?,?,?)",
                               (order.oid, pos.pid, dq, value, fees, now))
            if pos.qty <= 0:
                self._close(pos, "forced" if order.forced else "program", now)
            else:
                self._save_position(pos)

    def _book_leg(self, order: ROrder, dq: int, price: float) -> None:
        """A single-leg close of a broken structure's leg: `dq` contracts at `price` a share."""
        pos = self.positions.get(order.pid or -1)
        if pos is None:
            return
        leg = order.legs[0]
        fee = leg_fees(order.root, [RLeg(leg.symbol, leg.side, 1, leg.is_call, leg.strike, leg.expiry, leg.key)], [price], dq, "close")
        closed = dict(pos.info.get("leg_closed") or {})
        closed[leg.symbol] = int(closed.get(leg.symbol, 0)) + dq
        pos.info["leg_closed"] = closed
        pos.cash += leg.side * price * V.MULTIPLIER * dq - fee
        pos.fees += fee
        pos.exit_value_qty += leg.side * price * dq / max(1, leg.ratio)
        self.state.execute("INSERT INTO fills(oid, pid, qty, value, fees, at) VALUES(?,?,?,?,?,?)",
                           (order.oid, pos.pid, dq, leg.side * price, fee, self.clock()))
        self._finish_broken(pos, "broken: legs closed alone")

    def remove_contracts(self, symbol: str, contracts: int, *, value_share: float, why: str) -> int:
        """An expiry, an assignment or an exercise took `contracts` of `symbol` out of the account: the positions
        holding it lose them (oldest first), each contract worth `value_share` a share at that moment (its intrinsic;
        zero at an expiry out of the money), and the position is broken (its other legs close alone). Returns how many
        contracts the book found."""
        left = int(contracts)
        unpriced = [RPosition.of(r) for r in self.state.rows("SELECT * FROM positions WHERE status='unpriced_close'")]
        for pos in sorted([*self.positions.values(), *unpriced], key=lambda p: p.pid):
            if left <= 0:
                break
            for leg in pos.legs:
                if leg.symbol != symbol or left <= 0:
                    continue
                remaining = pos.info.get("unpriced_remaining") if pos.status == "unpriced_close" else None
                take = min(int(remaining.get(symbol, 0)) if remaining is not None else self.leg_remaining(pos, leg), left)
                if take <= 0:
                    continue
                gone = dict(pos.info.get("gone") or {})
                gone[symbol] = int(gone.get(symbol, 0)) + take
                pos.info["gone"] = gone
                pos.info["broken"] = why[:200]
                pos.cash += leg.side * value_share * V.MULTIPLIER * take
                pos.exit_value_qty += leg.side * value_share * take / max(1, leg.ratio)
                left -= take
                if remaining is not None:
                    remaining[symbol] -= take
                    if not any(remaining.values()):
                        pos.info.pop("unpriced_remaining", None)
                        pos.info.pop("unpriced_qty", None)
                        self._close(pos, why, self.clock())
                    else:
                        self._save_position(pos)
                else:
                    self._finish_broken(pos, why)
        return int(contracts) - left

    def _finish_broken(self, pos: RPosition, why: str) -> None:
        if all(self.leg_remaining(pos, leg) == 0 for leg in pos.legs):
            pos.qty = 0
            self._close(pos, why[:120], self.clock())
        else:
            self._save_position(pos)

    def _close(self, pos: RPosition, reason: str, now: float) -> None:
        pos.status, pos.closed_at, pos.reason = "closed", now, reason
        self._save_position(pos)
        pnl = round(pos.cash, 2)
        self.closed_since.setdefault(pos.instance, []).append({"id": pos.pid, "type": pos.type, "root": pos.root, "pnl": pnl,
                                                               "reason": reason, "tag": pos.tag})
        self.record("book.fill", {"source": "venue", "side": "sell", "real_money": True, "quantity": pos.opened_qty,
                                  "instrument": {"market_id": _code(pos), "asset_class": "option", "multiplier": 100},
                                  "realized": pnl, "entry_reason": pos.tag, "reason": reason,
                                  "_exit_value": pos.exit_value_qty / max(1, pos.opened_qty), "_pid": pos.pid},
                    agent=pos.family)

    def settle(self, pos: RPosition, value: float, reason: str) -> None:
        """A position that ended at the venue's expiry: its remaining units at `value` a share (no fee)."""
        dq = pos.qty
        pos.exit_value_qty += value * dq
        pos.cash += value * V.MULTIPLIER * dq
        pos.qty = 0
        self._close(pos, reason, self.clock())

    def closed_trades(self, since_pid: int = 0, *, unexported: bool = False) -> list[dict]:
        """Closed real trades with pid above `since_pid`, as forward-record rows."""
        out = []
        query = "SELECT * FROM positions WHERE status='closed' AND pid>?"
        if unexported:
            query += " AND pid NOT IN (SELECT pid FROM forward_exports)"
        for r in self.state.rows(query + " ORDER BY pid", (since_pid,)):
            pos = RPosition.of(r)
            out.append({"pid": pos.pid, "family": pos.family, "instance": pos.instance, "tuition": pos.tuition, "id": f"real:{pos.pid}",
                        "day": pos.opened_day, "pnl": round(pos.cash, 2),
                        "max_loss": round(pos.max_loss_share * V.MULTIPLIER * pos.opened_qty, 2)})
        return out

    def recover_expired(self, held: Mapping[str, int], fills: Sequence[Mapping[str, Any]], *, day: str) -> list[str]:
        """Attribute external liquidation fills oldest-position first. Missing expired contracts release exposure;
        without every leg's actual fill value they become unpriced, never measured forward evidence. Retry those
        rows on later reads. A fill quantity can be used once across families and process restarts."""
        pending = [RPosition.of(r) for r in self.state.rows("SELECT * FROM positions WHERE status='unpriced_close' ORDER BY pid")]
        pending += [p for p in self.positions.values() if p.status == "awaiting_expiry" and p.expiry <= day]
        alerts = []
        for pos in sorted(pending, key=lambda p: p.pid):
            if any(held.get(l.symbol, 0) for l in pos.legs) or self.blockers(pos.legs):
                continue
            remaining = pos.info.get("unpriced_remaining") or {l.symbol: self.leg_remaining(pos, l) for l in pos.legs}
            takes = []
            available = {r["id"]: {"qty": int(r["qty"]), "value": r["value_qty"]}
                         for r in self.state.rows("SELECT * FROM external_fill_usage")}
            complete = True
            for leg in pos.legs:
                need = int(remaining.get(leg.symbol, 0))
                for fill in fills:
                    if (fill["symbol"] != leg.symbol or fill["side"] != ("sell" if leg.side > 0 else "buy")
                            or fill["at"] < pos.opened_at or need <= 0):
                        continue
                    consumed = available.get(fill["id"], {"qty": 0, "value": 0.0})
                    left = int(fill["qty"]) - consumed["qty"]
                    if left <= 0 or consumed["value"] is None:
                        continue
                    unconsumed_value = float(fill["price"]) * int(fill["qty"]) - consumed["value"]
                    if unconsumed_value < -0.000001:
                        continue  # a correction or incomplete cumulative history cannot invent a negative fill price
                    price = max(0.0, unconsumed_value / left)
                    take = min(need, left)
                    if take:
                        takes.append((leg, fill, take, price))
                        available[fill["id"]] = {"qty": consumed["qty"] + take,
                                                  "value": consumed["value"] + price * take}
                        need -= take
                complete &= need == 0
            if not complete:
                if pos.status != "unpriced_close":
                    pos.info["unpriced_remaining"] = remaining
                    pos.info["unpriced_qty"] = pos.qty
                    pos.qty, pos.status = 0, "unpriced_close"
                    pos.reason = "expired contracts absent at venue; external fill values not yet reconciled"
                    self._save_position(pos)
                    alerts.append(f"{pos.family}'s {pos.type}: expired legs are absent; exposure cleared, P&L awaiting venue fills")
                continue
            with self.state.transaction():
                for leg, fill, take, price in takes:
                    single = RLeg(leg.symbol, leg.side, 1, leg.is_call, leg.strike, leg.expiry, leg.key)
                    fee = leg_fees(pos.root, [single], [price], take, "close")
                    pos.cash += leg.side * price * V.MULTIPLIER * take - fee
                    pos.fees += fee
                    pos.exit_value_qty += leg.side * price * take
                    self.state.upsert("external_fill_usage", {"id": fill["id"], "qty": available[fill["id"]]["qty"],
                                                             "value_qty": available[fill["id"]]["value"]}, "id")
                pos.qty = 0
                pos.info.pop("unpriced_remaining", None)
                pos.info.pop("unpriced_qty", None)
                self._close(pos, "venue liquidation reconciled from external fills", self.clock())
            alerts.append(f"{pos.family}'s {pos.type}: external liquidation and fees reconciled from venue fills")
        return alerts

    def _reject(self, instance: str, why: str) -> None:
        rows = self.rejects_since.setdefault(instance, [])
        if len(rows) < 20:
            rows.append(why[:200])

    # ------------------------------------------------------------------ reconciliation
    def reconcile(self, positions: Sequence[Mapping[str, Any]], foreign_orders: Sequence[Mapping[str, Any]], *,
                  day: dt.date, after_close: bool, shares: Mapping[str, int] | None = None,
                  include_expired: bool = False) -> list[str]:
        """The account against this book (the module docstring). Returns the mismatches of THIS reading; the freeze
        follows two readings in a row."""
        expected = self.expected_positions()
        held: dict[str, int] = {}
        problems = []
        for row in positions:
            symbol = str(row.get("symbol") or "").upper()
            klass = str(row.get("asset_class") or "")
            qty = dec(row.get("qty")) or Decimal(0)
            side = str(row.get("side") or "")
            signed = -abs(qty) if side == "short" else qty
            if klass == "crypto":
                if symbol in KNOWN_DUST and abs(signed) <= KNOWN_DUST[symbol]:
                    continue
                problems.append(f"{symbol}: {signed} held, a crypto position the options book never trades")
                continue
            if klass == "us_equity":
                want = int((shares or {}).get(symbol, 0))
                if signed != want:
                    problems.append(f"{symbol}: {signed} shares held, {want} expected (an assignment's shares)")
                continue
            if klass != "us_option" and occ_parts(symbol) is None:
                problems.append(f"{symbol}: an unknown holding ({klass})")
                continue
            if signed != signed.to_integral_value():
                problems.append(f"{symbol}: {signed} contracts, not a whole number")
                continue
            held[symbol] = int(signed)
        for symbol in set(expected) | set(held):
            parts = occ_parts(symbol)
            if parts is not None:
                expiry = dt.date.fromisoformat(parts[1])
                if not include_expired and (expiry < day or (after_close and expiry <= day)):
                    continue  # expired: the venue settles it (after the close); its events adjust the book
                if include_expired and after_close and expiry <= day and V.is_index(parts[0]):
                    continue  # cash settlement is already booked; the venue can retain its expired index rows overnight
            if expected.get(symbol, 0) != held.get(symbol, 0):
                problems.append(f"{symbol}: the account holds {held.get(symbol, 0)}, the book {expected.get(symbol, 0)}")
        for row in foreign_orders:
            problems.append(f"a working order that is not the live path's: {str(row.get('client_order_id') or row.get('id'))[:60]}")
        for order in self.orders.values():
            if order.uneven:
                problems.append(f"order {order.client_id}: its legs filled unevenly")
        self._streak["bad" if problems else "good"] += 1
        self._streak["good" if problems else "bad"] = 0
        was = self.frozen
        if problems and self._streak["bad"] >= 2:
            self.frozen = "; ".join(problems[:6])
        elif not problems and self._streak["good"] >= 2:
            self.frozen = ""
        self.mismatch = problems
        self.state.put("recon", {"frozen": self.frozen, "bad": self._streak["bad"], "good": self._streak["good"],
                                 "problems": problems[:20], "at": self.clock()})
        if self.frozen != was:
            self.record("live.freeze", {"frozen": bool(self.frozen), "why": self.frozen or f"cleared (was: {was[:300]})"})
        return problems


def _single_fill(order: ROrder, row: Mapping[str, Any]) -> tuple[int, float | None, list[float], bool] | None:
    """A single-leg order's fill: its own `filled_qty` contracts at `filled_avg_price` (a premium, positive)."""
    filled = dec(row.get("filled_qty"))
    if filled is None:
        return None
    units = int(filled)
    price = dec(row.get("filled_avg_price"))
    if units > 0 and price is None:
        return None
    return units, (float(price) if price is not None else None), [float(price) if price is not None else math.nan], False


def _collateral(type_: str, legs: Sequence[RLeg]) -> Decimal:
    spec = core.classify(type_, [core.leg(leg.symbol, leg.side, leg.ratio) for leg in legs])
    return spec.collateral


def _loss_share(type_: str, value: float, collateral: float) -> float:
    try:
        return L.max_loss_share(type_, value, collateral)
    except L.Refused:
        # A fill outside what the structure can be worth (never at a sane venue): count its worst case.
        return abs(value) + collateral


def _code(pos: RPosition) -> str:
    try:
        return pos.code()
    except ValueError:
        return ""


def real_legs(order: L.Order, chain: Any) -> list[RLeg]:
    """A resolved Gym order's legs as OCC contracts of today's chain."""
    out = []
    for leg in order.legs:
        symbol = chain.symbol[leg.idx]
        parts = occ_parts(symbol)
        out.append(RLeg(symbol, leg.side, leg.ratio, leg.is_call, leg.strike, parts[1] if parts else "", int(leg.key)))
    return out


__all__ = ["RealBook", "RLeg", "RPosition", "ROrder", "mleg_body", "single_leg_body", "limit_price", "client_id", "structure_fill", "real_legs",
           "leg_fees", "PREFIX", "KNOWN_DUST"]
