"""The Gym's replay: day-major batching, the engine's clock, honest fills, the venue's rules.

    results = run(programs, store, RunConfig(window="train", roots=("SPY",)))

For each trading day of the window the engine loads each root's chain ONCE (`store.Store.chain`),
then steps every program of the batch through the day minute by minute: a snapshot of a root at a
minute is built once and shared by every program that looks at it that minute, and dropped after.
A program is called at its NEEDS cadence and sees only minute m's row (and the underlying up to m,
and the prior sessions); its orders meet the NBBO of minute m + 1 and later (`fills.py`). Nothing a
program sees at minute m is computed from anything after m: the engine owns the clock.

The day of a program, minute index i from 1 (09:31) to the last minute before the close:
1. its working orders meet row i (arrivals first sent at i - 1);
2. the venue acts at row i: opening orders on an expiring contract are cancelled at the open
   cutoff (15:00), closing ones at the close cutoff (15:10; 15:25 SPY/QQQ), and from the
   liquidation minute (15:30) every equity position with a leg expiring today is closed at the
   natural price;
3. on a decision minute, decide(ctx) runs and its intents become orders arriving at i + 1.
At the close: working orders expire; positions expiring today settle (index: cash at the closing
level; equity legs that could not be liquidated: exercised at $0.01 in the money, and a net share
position is marked to the next session's first price); every position is marked at the mid; the
day's P&L is the change in cash plus marks. At the window's end every open position is closed at
the natural price of the last minute (or marked, where a leg has no quote).

Deterministic: the same programs, parameters, store files, fill model and window give the same
result (`results.py` hashes it). numpy only here; the store reader brings pyarrow.
"""

from __future__ import annotations

import datetime as dt
import math
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Sequence

import numpy as np

from . import ENGINE_VERSION, fills as F, legs as L, venue
from .ctx import Snapshot, build_ctx, order_row, position_row, underlying_view
from .events import EVENT_NAMES, EventCalendar, rate_on
from .runtime import Program

if TYPE_CHECKING:  # pragma: no cover
    from .store import DayChain, Store


@dataclass
class RunConfig:
    """One run's settings (every one of them is part of the run's hash)."""

    window: str = "train"
    roots: tuple[str, ...] = ()      # the run's universe; a program trades its NEEDS roots within it (all, if empty)
    capital: float = 10_000.0        # each program's account
    stress: float = 1.0              # half-spread multiplier on every fill (1.5 = the gate's stress run)
    timeout: float = 1.0             # seconds a decide call may take
    max_errors: int = 25             # errors before a program is disqualified
    max_orders_day: int = 60         # orders (opens and closes) a program may send a day
    start: dt.date | None = None     # cut the window (the inner loop's segments)
    end: dt.date | None = None
    fill_model: F.FillModel = field(default_factory=F.FillModel)

    def identity(self) -> dict[str, Any]:
        return {"window": self.window, "roots": sorted(self.roots), "capital": self.capital, "stress": self.stress,
                "max_orders_day": self.max_orders_day, "start": self.start.isoformat() if self.start else None,
                "end": self.end.isoformat() if self.end else None, "fill_model": self.fill_model.version,
                "engine": ENGINE_VERSION}


# --------------------------------------------------------------------------- one day of data
class History:
    """Each root's prior sessions (open, high, low, close), oldest first, as the run moves on."""

    def __init__(self, depth: int):
        self.depth = max(0, int(depth))
        self.rows: dict[str, list[tuple[float, float, float, float]]] = {}

    def add(self, root: str, prices: np.ndarray) -> None:
        p = prices[np.isfinite(prices)]
        if p.size == 0 or self.depth == 0:
            return
        rows = self.rows.setdefault(root, [])
        rows.append((float(p[0]), float(p.max()), float(p.min()), float(p[-1])))
        del rows[:-self.depth]

    def arrays(self, root: str, n: int) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        rows = self.rows.get(root, [])[-n:] if n > 0 else []
        if not rows:
            empty = np.zeros(0)
            return empty, empty, empty, empty
        a = np.array(rows, dtype=np.float64)
        return a[:, 0], a[:, 1], a[:, 2], a[:, 3]


class DayData:
    """One trading day: each root's chain once, and one shared snapshot per root and minute."""

    def __init__(self, store: "Store", day: dt.date, roots: Sequence[str], events: EventCalendar, history: History,
                 ordinal: int):
        self.day = day
        self.ordinal = ordinal
        self.weekday = day.weekday()
        self.open_min, self.close_min = store.session(day)
        self.minutes = self.close_min - self.open_min + 1
        self.rate = rate_on(day)
        self.chains: dict[str, "DayChain"] = {}
        for root in roots:
            if store.has("nbbo", root, day) and store.has("underlying", root, day):
                self.chains[root] = store.chain(root, day)
        self.rules = {root: venue.rules_for(root, open_minute=self.open_min, close_minute=self.close_min) for root in roots}
        self.rules_rows = {root: r.as_dict() for root, r in self.rules.items()}
        self.events = events.flags(day)
        self.events_next = events.flags(events.next_day(day))
        self.history = history
        self._snaps: dict[tuple[str, int], Snapshot] = {}
        self._last: dict[str, Snapshot] = {}
        self._unders: dict[tuple[str, int, int], Any] = {}
        self._minute = -1

    def advance(self, mi: int) -> None:
        """Drop the caches of earlier minutes (keeping each root's last snapshot for the warm start)."""
        if mi != self._minute:
            self._snaps.clear()
            self._unders.clear()
            self._minute = mi

    def snapshot(self, root: str, mi: int) -> Snapshot | None:
        key = (root, mi)
        found = self._snaps.get(key)
        if found is not None:
            return found
        chain = self.chains.get(root)
        if chain is None:
            return None
        prev = self._last.get(root)
        snap = Snapshot(root, self.open_min + mi, float(chain.underlying.price[mi]), chain.dte, chain.strike, chain.is_call,
                        chain.bid[mi], chain.ask[mi], chain.bid_size[mi], chain.ask_size[mi], oi=chain.oi, rate=self.rate,
                        close_minute=self.close_min, keys=chain.key,
                        iv_guess=prev.iv_known if prev is not None else None)
        self._snaps[key] = snap
        self._last[root] = snap
        return snap

    def under(self, root: str, mi: int, history: int):
        key = (root, mi, history)
        found = self._unders.get(key)
        if found is None:
            chain = self.chains[root]
            opens, highs, lows, closes = self.history.arrays(root, history)
            found = underlying_view(root, chain.underlying.price[: mi + 1], closes=closes, opens=opens, highs=highs, lows=lows)
            self._unders[key] = found
        return found

    def regime(self, root: str) -> dict[str, float]:
        """The day's regime features (engine-side, for the results' terciles): the realized vol of
        the prior ten sessions and the at-the-money implied vol at 10:00 of the nearest expiry."""
        out = {"rv": math.nan, "iv": math.nan}
        opens, highs, lows, closes = self.history.arrays(root, 11)
        if closes.size >= 3:
            r = np.diff(np.log(closes))
            out["rv"] = float(np.std(r, ddof=1) * math.sqrt(252.0))
        mi = min(30, self.minutes - 2)
        snap = self.snapshot(root, mi)
        if snap is not None and np.isfinite(snap.spot):
            pool = np.flatnonzero(snap.valid)
            if pool.size:
                first = int(snap.dte[pool].min())
                pool = pool[snap.dte[pool] == first]
                near = pool[np.argsort(np.abs(snap.strike[pool] - snap.spot))[:4]]
                iv = snap.greeks_for(near)[0]
                if np.isfinite(iv).any():
                    out["iv"] = float(np.nanmean(iv))
        return out


# --------------------------------------------------------------------------- one program's account
@dataclass
class Position:
    pid: int
    type: str
    root: str
    legs: tuple[L.LegFill, ...]
    keys: np.ndarray
    expirations: np.ndarray       # expiration day ordinal of each leg
    qty: int
    opened_qty: int
    entry: float                  # value a share (average over the open's fills)
    max_loss_share: float
    collateral: float
    opened_day: int               # ordinal
    opened_mi: int
    opened_session: int
    info: dict
    tag: str = ""
    note: str = ""
    cash: float = 0.0             # every cash flow of this trade, fees included
    fees: float = 0.0
    exit_value_qty: float = 0.0   # sum of exit value x quantity closed
    exit_day: int = 0
    exit_mi: int = 0
    reason: str = ""
    idx: np.ndarray | None = None  # today's snapshot index of each leg (-1: not in today's chain)
    last_mark: float = math.nan
    closing: int = 0              # working close order id (0: none)

    @property
    def credit(self) -> bool:
        return self.type in L.CREDIT

    def legs_today(self) -> tuple[L.LegFill, ...]:
        return tuple(L.LegFill(int(i), leg.key, leg.side, leg.ratio, leg.dte, leg.strike, leg.is_call)
                     for leg, i in zip(self.legs, self.idx))


@dataclass
class Working:
    oid: int
    order: L.Order
    remaining: int
    placed_mi: int
    arrival_mi: int
    expires_mi: int | None
    reserve_left: float
    pid: int = 0                  # the position an open creates / a close closes
    forced: bool = False          # the venue's liquidation
    filled: int = 0


class Account:
    """One program in one run: its runner, cash, positions, orders and the record."""

    def __init__(self, program: Program, cfg: RunConfig, roots: tuple[str, ...]):
        self.program = program
        self.cfg = cfg
        self.roots = roots
        self.needs = program.needs
        self.runner = program.start(timeout=cfg.timeout, max_errors=cfg.max_errors)
        self.cash = float(cfg.capital)
        self.equity_prev = float(cfg.capital)
        self.positions: dict[int, Position] = {}
        self.orders: dict[int, Working] = {}
        self.next_id = 1
        self.trades: list[dict] = []
        self.daily: list[tuple[str, float, float]] = []
        self.fill_rows: list[tuple[str, float, float, bool]] = []  # (action, slip a share, slip in half-spreads, at natural)
        self.counts = {"orders": 0, "opens": 0, "closes": 0, "filled": 0, "partial_fills": 0, "cancelled": 0, "expired": 0,
                       "rejected": 0, "liquidated": 0, "settled": 0, "exercised": 0, "fills": 0}
        self.reject_reasons: dict[str, int] = {}
        self.pending_shares: list[tuple[Position, str, float, float]] = []  # (trade, root, shares, reference price)
        self.closed_since: list[dict] = []
        self.rejects_since: list[str] = []
        self.orders_today = 0
        self.session = 0
        self.traded_days: set[int] = set()

    # ------------------------------------------------------------------ helpers
    def _id(self) -> int:
        self.next_id += 1
        return self.next_id - 1

    def _reject(self, why: str) -> None:
        self.counts["rejected"] += 1
        key = why.split(":")[0][:80]
        self.reject_reasons[key] = self.reject_reasons.get(key, 0) + 1
        if len(self.rejects_since) < 20:
            self.rejects_since.append(why[:200])

    def buying_power(self) -> float:
        held = sum(p.collateral * venue.MULTIPLIER * p.qty for p in self.positions.values() if p.credit)
        working = sum(w.reserve_left for w in self.orders.values() if w.order.action == "open")
        return self.cash - held - working

    def equity(self) -> float:
        return self.cash + sum((p.last_mark if math.isfinite(p.last_mark) else p.entry) * venue.MULTIPLIER * p.qty
                               for p in self.positions.values())

    def decision_minutes(self, day: DayData) -> set[int]:
        first = max(self.needs.start, day.open_min + 1) - day.open_min
        last = min(self.needs.end - day.open_min, day.minutes - 3)
        return set(range(first, last + 1, self.needs.cadence)) if first <= last else set()

    # ------------------------------------------------------------------ the day
    def begin_day(self, day: DayData) -> None:
        self.orders_today = 0
        for pos, root, shares, ref in self.pending_shares:
            chain = day.chains.get(root)
            price = chain.underlying.price if chain is not None else np.zeros(0)
            first = price[np.isfinite(price)]
            gap = float(shares) * ((float(first[0]) if first.size else ref) - ref)
            self.cash += gap
            pos.cash += gap
            pos.info["share_gap"] = round(gap, 2)
            self._finish(pos, day)
        self.pending_shares = []
        for pos in self.positions.values():
            chain = day.chains.get(pos.root)
            pos.idx = chain.index_of(pos.keys) if chain is not None else np.full(len(pos.legs), -1)

    def step(self, day: DayData, mi: int, decide: bool) -> None:
        if self.orders:
            self._work(day, mi)
        self._venue(day, mi)
        if decide and not self.runner.disqualified:
            self._decide(day, mi)

    def _work(self, day: DayData, mi: int) -> None:
        for oid in sorted(self.orders):
            work = self.orders.get(oid)
            if work is None or mi < work.arrival_mi:
                continue
            if work.expires_mi is not None and mi > work.expires_mi:
                self._drop(work, "expired")
                continue
            self._try_fill(day, mi, work)

    def _try_fill(self, day: DayData, mi: int, work: Working) -> None:
        order = work.order
        snap = day.snapshot(order.root, mi)
        if snap is None:
            return
        if order.action == "close":
            pos = self.positions.get(work.pid)
            if pos is None:
                self._drop(work, "cancelled")
                return
            legs = pos.legs_today()
            if any(leg.idx < 0 for leg in legs):
                return
        else:
            legs = order.legs
        stress = self.cfg.stress
        natural, cap = L.natural_value(snap, legs, order.action, stress=stress)
        if not math.isfinite(natural):
            return
        mid = L.mid_value(snap, legs)
        opening = order.action == "open"
        if work.forced:
            price, qty = natural, work.remaining
        else:
            marketable = natural <= order.limit + 1e-9 if opening else natural >= order.limit - 1e-9
            if marketable:
                price = natural if mi == work.arrival_mi else order.limit
            else:
                span = natural - mid
                q = (order.limit - mid) / span if abs(span) > 1e-12 else 1.0
                strikes = [leg.strike for leg in legs]
                money = (sum(strikes) / len(strikes)) / snap.spot - 1.0 if np.isfinite(snap.spot) else 0.0
                dte = min(int(snap.dte[leg.idx]) for leg in legs)
                p = self.cfg.fill_model.p(q, len(legs), dte, money, snap.minute)
                if p <= 0.0 or F.draw([leg.key for leg in legs], day.ordinal, snap.minute, "buy" if opening else "sell") >= p:
                    return
                price = order.limit
            qty = min(work.remaining, cap)
            if qty <= 0:
                return
        leg_prices = []
        for leg in legs:
            buying = (leg.side > 0) == opening
            leg_prices.append(float(snap.ask[leg.idx] if buying else snap.bid[leg.idx]))
        fees = L.order_fees(order.root, legs, leg_prices, qty, order.action)
        half = abs(natural - mid)
        slip = (price - mid) if opening else (mid - price)
        self.fill_rows.append((order.action, slip, slip / half if half > 1e-12 else 0.0, abs(price - natural) < 1e-9))
        self.counts["fills"] += 1
        if opening:
            self._open_fill(day, mi, work, price, qty, fees)
        else:
            self._close_fill(day, mi, work, price, qty, fees, "liquidated" if work.forced else "program")
        work.remaining -= qty
        work.filled += qty
        if work.order.action == "open":
            work.reserve_left = work.order.reserve * work.remaining / max(1, work.order.qty)
        if work.remaining <= 0:
            self.counts["filled"] += 1
            self._drop(work, None)
        elif work.filled == qty:
            self.counts["partial_fills"] += 1

    def _open_fill(self, day: DayData, mi: int, work: Working, price: float, qty: int, fees: float) -> None:
        order = work.order
        cash = -price * venue.MULTIPLIER * qty - fees
        self.cash += cash
        pos = self.positions.get(work.pid) if work.pid else None
        if pos is None:
            pid = self._id()
            work.pid = pid
            snap_legs = order.legs
            keys = np.array([leg.key for leg in snap_legs], dtype=np.int64)
            pos = Position(
                pid=pid, type=order.type, root=order.root, legs=snap_legs, keys=keys,
                expirations=np.array([day.ordinal + leg.dte for leg in snap_legs], dtype=np.int64), qty=0, opened_qty=0,
                entry=price, max_loss_share=L.max_loss_share(order.type, price, order.collateral) if self._defined(order, price) else order.max_loss_share,
                collateral=order.collateral, opened_day=day.ordinal, opened_mi=mi, opened_session=self.session,
                info={**order.extra, "filled_minute": day.open_min + mi}, tag=order.tag, note=order.note,
                idx=np.array([leg.idx for leg in snap_legs], dtype=np.int64))
            self.positions[pid] = pos
            self.traded_days.add(day.ordinal)
        else:
            total = pos.opened_qty + qty
            pos.entry = (pos.entry * pos.opened_qty + price * qty) / total
            pos.max_loss_share = L.max_loss_share(pos.type, pos.entry, pos.collateral) if self._defined(order, pos.entry) else pos.max_loss_share
        pos.qty += qty
        pos.opened_qty += qty
        pos.cash += cash
        pos.fees += fees
        pos.last_mark = pos.entry if not math.isfinite(pos.last_mark) else pos.last_mark

    @staticmethod
    def _defined(order: L.Order, value: float) -> bool:
        try:
            L.max_loss_share(order.type, value, order.collateral)
            return True
        except L.Refused:
            return False

    def _close_fill(self, day: DayData, mi: int, work: Working, price: float, qty: int, fees: float, reason: str) -> None:
        pos = self.positions[work.pid]
        cash = price * venue.MULTIPLIER * qty - fees
        self.cash += cash
        pos.cash += cash
        pos.fees += fees
        pos.exit_value_qty += price * qty
        pos.qty -= qty
        if pos.qty <= 0:
            pos.exit_day, pos.exit_mi, pos.reason = day.ordinal, mi, reason
            if reason == "liquidated":
                self.counts["liquidated"] += 1
            self._finish(pos, day)

    def _finish(self, pos: Position, day: DayData) -> None:
        self.positions.pop(pos.pid, None)
        if pos.closing:
            self.orders.pop(pos.closing, None)
        self.trades.append(self._trade_row(pos))
        self.closed_since.append({"id": pos.pid, "type": pos.type, "root": pos.root, "pnl": round(pos.cash, 2),
                                  "reason": pos.reason, "tag": pos.tag})

    def _trade_row(self, pos: Position) -> dict:
        from .store import from_ordinal

        max_loss = pos.max_loss_share * venue.MULTIPLIER * pos.opened_qty
        exit_value = pos.exit_value_qty / pos.opened_qty if pos.opened_qty else math.nan
        return {
            "id": pos.pid, "root": pos.root, "type": pos.type, "tag": pos.tag, "qty": pos.opened_qty,
            "legs": [{"dte": leg.dte, "strike": leg.strike, "right": "C" if leg.is_call else "P",
                      "side": "long" if leg.side > 0 else "short", "ratio": leg.ratio} for leg in pos.legs],
            "day": from_ordinal(pos.opened_day).isoformat(), "entry_minute": pos.info.get("minute"),
            "filled_minute": pos.info.get("filled_minute"),
            "exit_day": from_ordinal(pos.exit_day).isoformat() if pos.exit_day else None,
            "exit_minute": pos.exit_mi + pos.info.get("open_min", 570) if pos.exit_mi else None,
            "sessions_held": self.session - pos.opened_session,
            "entry": round(pos.entry, 4), "exit": None if not math.isfinite(exit_value) else round(exit_value, 4),
            "max_loss": round(max_loss, 2), "fees": round(pos.fees, 2), "pnl": round(pos.cash, 2),
            "return_on_max_loss": round(pos.cash / max_loss, 4) if max_loss > 0 else None,
            "exit_reason": pos.reason, "context": pos.info.get("context", {}), "note": pos.note,
        }

    def _drop(self, work: Working, why: str | None) -> None:
        self.orders.pop(work.oid, None)
        if work.order.action == "close":
            pos = self.positions.get(work.pid)
            if pos is not None and pos.closing == work.oid:
                pos.closing = 0
        if why == "expired":
            self.counts["expired"] += 1
        elif why == "cancelled":
            self.counts["cancelled"] += 1

    # ------------------------------------------------------------------ the venue
    def _venue(self, day: DayData, mi: int) -> None:
        minute = day.open_min + mi
        for root in self.roots:
            rules = day.rules.get(root)
            if rules is None:
                continue
            if minute == rules.open_cutoff:
                for work in list(self.orders.values()):
                    if work.order.action == "open" and work.order.root == root and any(leg.dte == 0 for leg in work.order.legs):
                        self._drop(work, "cancelled")
            if minute == rules.close_cutoff:
                for work in list(self.orders.values()):
                    pos = self.positions.get(work.pid)
                    if work.order.action == "close" and not work.forced and pos is not None and pos.root == root and \
                            int(pos.expirations.min()) == day.ordinal:
                        self._drop(work, "cancelled")
            if rules.liquidation is not None and minute >= rules.liquidation:
                for pos in list(self.positions.values()):
                    if pos.root != root or int(pos.expirations.min()) != day.ordinal or pos.pid not in self.positions:
                        continue
                    if pos.closing and self.orders.get(pos.closing) is not None and self.orders[pos.closing].forced:
                        continue
                    if pos.closing:
                        self._drop(self.orders[pos.closing], "cancelled")
                    order = L.Order("close", pos.type, root, pos.legs_today(), pos.qty, math.nan, math.nan, math.nan, 0.0,
                                    0.0, 0.0, 0.0, None, pos.tag, "liquidation", position=pos.pid)
                    work = Working(self._id(), order, pos.qty, mi, mi, None, 0.0, pid=pos.pid, forced=True)
                    self.orders[work.oid] = work
                    pos.closing = work.oid
                    self._try_fill(day, mi, work)

    # ------------------------------------------------------------------ decisions
    def _position_rows(self, day: DayData, mi: int) -> list[dict]:
        rows = []
        for pos in self.positions.values():
            snap = day.snapshot(pos.root, mi)
            legs = pos.legs_today()
            mark = natural = math.nan
            if snap is not None and all(leg.idx >= 0 for leg in legs):
                mark = L.mid_value(snap, legs)
                natural = L.natural_value(snap, legs, "close")[0]
                if math.isfinite(mark):
                    pos.last_mark = mark
            leg_rows = [{"id": int(leg.idx), "dte": int(exp - day.ordinal), "strike": leg.strike, "is_call": leg.is_call,
                         "side": "long" if leg.side > 0 else "short", "ratio": leg.ratio}
                        for leg, exp in zip(legs, pos.expirations)]
            held = (self.session - pos.opened_session) * 390 + mi - pos.opened_mi
            rows.append(position_row(pid=pos.pid, type_=pos.type, root=pos.root, qty=pos.qty, legs=leg_rows, entry=pos.entry,
                                     max_loss=pos.max_loss_share * venue.MULTIPLIER * pos.qty, mark=mark, natural=natural,
                                     held_minutes=held, held_days=self.session - pos.opened_session, tag=pos.tag))
        return rows

    def _order_rows(self, day: DayData, mi: int) -> list[dict]:
        return [order_row(oid=w.oid, kind=w.order.action, type_=w.order.type, root=w.order.root, qty=w.order.qty,
                          filled=w.filled, limit=w.order.limit, age_minutes=mi - w.placed_mi, position=w.pid or None,
                          tag=w.order.tag) for w in self.orders.values() if not w.forced]

    def _decide(self, day: DayData, mi: int) -> None:
        chains, unders = {}, {}
        needs = self.needs
        for root in self.roots:
            snap = day.snapshot(root, mi)
            if snap is None:
                continue
            chains[root] = snap.view(snap.slice_index(needs.dte_min, needs.dte_max, needs.band),
                                     key=(needs.dte_min, needs.dte_max, needs.band))
            unders[root] = day.under(root, mi, needs.history)
        if not chains:
            return
        positions = self._position_rows(day, mi)
        ctx = build_ctx(minute=day.open_min + mi, open_minute=day.open_min, close_minute=day.close_min, weekday=day.weekday,
                        chains=chains, underlyings=unders, positions=positions, orders=self._order_rows(day, mi),
                        cash=self.cash, equity=self.equity(), budget=self.cfg.capital, buying_power=self.buying_power(),
                        params=self.program.params, rules={r: day.rules_rows[r] for r in chains}, events=day.events,
                        events_next=day.events_next, closed=self.closed_since, rejects=self.rejects_since,
                        roots=tuple(chains))
        self.closed_since = []
        self.rejects_since = []
        for intent in self.runner.decide(ctx):
            try:
                self._intent(day, mi, intent)
            except L.Refused as exc:
                self._reject(str(exc))

    def _intent(self, day: DayData, mi: int, intent: dict) -> None:
        arrival = mi + 1
        minute = day.open_min + arrival
        if "cancel" in intent:
            work = self.orders.get(intent["cancel"]) if isinstance(intent["cancel"], int) else None
            if work is None or work.forced:
                raise L.Refused("cancel: no such working order")
            self._drop(work, "cancelled")
            return
        if self.orders_today >= self.cfg.max_orders_day:
            raise L.Refused(f"order budget: {self.cfg.max_orders_day} orders a day")
        if "close" in intent:
            pos = self.positions.get(intent["close"]) if isinstance(intent["close"], int) else None
            if pos is None:
                raise L.Refused("close: no such open position")
            if pos.closing:
                raise L.Refused("close: this position already has a working close (cancel it first)")
            rules = day.rules[pos.root]
            if int(pos.expirations.min()) == day.ordinal and minute >= rules.close_cutoff:
                raise L.Refused(f"expiry cutoff: closing orders on expiring contracts end at {rules.close_cutoff // 60}:{rules.close_cutoff % 60:02d} ET")
            snap = day.snapshot(pos.root, mi)
            if snap is None:
                raise L.Refused("close: no chain for this root now")
            order = L.resolve_close(intent, pos.type, pos.legs_today(), pos.qty, snap, rules, position=pos.pid,
                                    stress=self.cfg.stress)
            work = Working(self._id(), order, order.qty, mi, arrival, self._expiry(order, arrival), 0.0, pid=pos.pid)
            self.orders[work.oid] = work
            pos.closing = work.oid
            self.orders_today += 1
            self.counts["orders"] += 1
            self.counts["closes"] += 1
            if order.tif == 0:
                self._ioc(day, work)
            return
        root = str(intent.get("root") or (self.roots[0] if len(self.roots) == 1 else "")).upper()
        if root not in self.roots:
            raise L.Refused(f"open: root {root or '?'} is not one this program trades ({', '.join(self.roots)}); name 'root'")
        snap = day.snapshot(root, mi)
        if snap is None:
            raise L.Refused(f"open: no {root} chain today")
        rules = day.rules[root]
        order = L.resolve_open(intent, snap, rules, buying_power=self.buying_power(), stress=self.cfg.stress)
        if any(leg.dte == 0 for leg in order.legs) and minute >= rules.open_cutoff:
            raise L.Refused(f"expiry cutoff: no new opening order on an expiring contract from {rules.open_cutoff // 60}:{rules.open_cutoff % 60:02d} ET")
        order.extra = {"minute": day.open_min + mi, "open_min": day.open_min, "context": self._context(day, snap, order)}
        work = Working(self._id(), order, order.qty, mi, arrival, self._expiry(order, arrival), order.reserve)
        self.orders[work.oid] = work
        self.orders_today += 1
        self.counts["orders"] += 1
        self.counts["opens"] += 1
        if order.tif == 0:
            self._ioc(day, work)

    def _ioc(self, day: DayData, work: Working) -> None:
        """An immediate-or-cancel order meets its arrival minute and no other."""
        work.expires_mi = work.arrival_mi

    @staticmethod
    def _expiry(order: L.Order, arrival: int) -> int | None:
        return None if order.tif is None else arrival + max(0, int(order.tif))

    def _context(self, day: DayData, snap: Snapshot, order: L.Order) -> dict:
        idx = np.array([leg.idx for leg in order.legs], dtype=np.int64)
        iv, delta, _, _, _ = snap.greeks_for(idx)
        strikes = [leg.strike for leg in order.legs]
        return {"spot": round(snap.spot, 4) if np.isfinite(snap.spot) else None, "minute": snap.minute,
                "weekday": day.weekday, "dte": int(min(leg.dte for leg in order.legs)),
                "moneyness": round((sum(strikes) / len(strikes)) / snap.spot - 1.0, 5) if np.isfinite(snap.spot) else None,
                "iv": [None if not np.isfinite(v) else round(float(v), 4) for v in iv],
                "delta": [None if not np.isfinite(v) else round(float(v), 4) for v in delta],
                "natural": round(order.natural, 4), "mid": round(order.mid, 4), "limit": round(order.limit, 4),
                "events": [k for k in EVENT_NAMES if day.events.get(k)]}

    # ------------------------------------------------------------------ the close
    def end_day(self, day: DayData, *, last: bool) -> None:
        for work in list(self.orders.values()):
            self._drop(work, "expired")
        close_mi = day.minutes - 1
        for pos in list(self.positions.values()):
            if int(pos.expirations.min()) == day.ordinal:
                self._expire(day, pos)
        for pos in list(self.positions.values()):
            self._mark(day, pos, close_mi)
        if last:
            for pos in list(self.positions.values()):
                self._window_end(day, pos)
            for pos, root, shares, ref in self.pending_shares:
                pos.info["share_gap"] = 0.0
                self._finish(pos, day)
            self.pending_shares = []
        equity = self.equity()
        self.daily.append((day.day.isoformat(), round(equity - self.equity_prev, 6), round(equity, 6)))
        self.equity_prev = equity
        self.session += 1

    def _expire(self, day: DayData, pos: Position) -> None:
        chain = day.chains.get(pos.root)
        price = chain.underlying.price if chain is not None else np.zeros(0)
        known = price[np.isfinite(price)]
        level = float(known[-1]) if known.size else math.nan
        near = int(pos.expirations.min())
        value = 0.0
        shares = 0.0
        later = False
        for leg, exp, i in zip(pos.legs, pos.expirations, pos.idx):
            if int(exp) != near:
                later = True
                mid = self._last_mid(day, pos.root, int(i))
                value += leg.side * leg.ratio * (mid if math.isfinite(mid) else 0.0)
                continue
            intrinsic = max(0.0, level - leg.strike) if leg.is_call else max(0.0, leg.strike - level)
            if not math.isfinite(intrinsic) or intrinsic < 0.01:
                continue
            value += leg.side * leg.ratio * intrinsic
            if not venue.is_index(pos.root):
                shares += (1.0 if leg.is_call else -1.0) * leg.side * leg.ratio * venue.MULTIPLIER * pos.qty
        cash = value * venue.MULTIPLIER * pos.qty
        self.cash += cash
        pos.cash += cash
        pos.exit_value_qty += value * pos.qty
        pos.exit_day, pos.exit_mi = day.ordinal, day.minutes - 1
        if later:
            pos.reason = "forced_mark"
        elif venue.is_index(pos.root):
            pos.reason = "settled"
            self.counts["settled"] += 1
        else:
            pos.reason = "exercised"
            self.counts["exercised"] += 1
        pos.qty = 0
        if shares and math.isfinite(level):
            pos.info["shares"] = shares
            self.positions.pop(pos.pid, None)
            self.pending_shares.append((pos, pos.root, shares, level))
        else:
            self._finish(pos, day)

    @staticmethod
    def _last_mid(day: DayData, root: str, i: int, back: int = 30) -> float:
        """A contract's mid at the close, or at the last minute of the final half hour that quoted it."""
        chain = day.chains.get(root)
        if chain is None or i < 0:
            return math.nan
        for m in range(day.minutes - 1, max(-1, day.minutes - 1 - back), -1):
            bid, ask = round(float(chain.bid[m, i]), 4), round(float(chain.ask[m, i]), 4)
            if math.isfinite(bid) and math.isfinite(ask):
                return 0.5 * (bid + ask)
        return math.nan

    def _mark(self, day: DayData, pos: Position, mi: int) -> None:
        chain = day.chains.get(pos.root)
        if chain is None or (pos.idx < 0).any():
            return
        for m in range(mi, max(0, mi - 30), -1):
            bid = np.round(chain.bid[m, pos.idx].astype(np.float64), 4)
            ask = np.round(chain.ask[m, pos.idx].astype(np.float64), 4)
            if np.isfinite(bid).all() and np.isfinite(ask).all():
                sides = np.array([leg.side * leg.ratio for leg in pos.legs], dtype=np.float64)
                pos.last_mark = float(np.sum(sides * 0.5 * (bid + ask)))
                return

    def _window_end(self, day: DayData, pos: Position) -> None:
        snap = day.snapshot(pos.root, day.minutes - 2) if pos.root in day.chains else None
        legs = pos.legs_today()
        value = math.nan
        fees = 0.0
        if snap is not None and all(leg.idx >= 0 for leg in legs):
            value, _ = L.natural_value(snap, legs, "close", stress=self.cfg.stress)
            if math.isfinite(value):
                prices = [float(snap.bid[leg.idx] if leg.side > 0 else snap.ask[leg.idx]) for leg in legs]
                fees = L.order_fees(pos.root, legs, prices, pos.qty, "close")
        reason = "window_end"
        if not math.isfinite(value):
            value = pos.last_mark if math.isfinite(pos.last_mark) else pos.entry
            reason = "window_end_mark"
        cash = value * venue.MULTIPLIER * pos.qty - fees
        self.cash += cash
        pos.cash += cash
        pos.fees += fees
        pos.exit_value_qty += value * pos.qty
        pos.qty = 0
        pos.exit_day, pos.exit_mi, pos.reason = day.ordinal, day.minutes - 2, reason
        self._finish(pos, day)


# --------------------------------------------------------------------------- the run
def run(programs: Sequence[Program], store: "Store", cfg: RunConfig, *, days: Sequence[dt.date] | None = None,
        progress: Any = None, keep: list | None = None) -> list[dict]:
    """Run a batch of programs over the window, day-major; return one result dict per program
    (`results.build`), in the order given. `keep`, a list, receives the accounts (for inspection)."""
    from . import results as R

    began = time.perf_counter()
    universe = tuple(r.upper() for r in cfg.roots)
    accounts: list[Account] = []
    for program in programs:
        roots = tuple(r for r in program.needs.roots if not universe or r in universe)
        accounts.append(Account(program, cfg, roots))
    if keep is not None:
        keep.extend(accounts)
    all_roots = tuple(sorted({r for a in accounts for r in a.roots}))
    if days is None:
        days = [d for d in store.days(cfg.window, [], start=cfg.start, end=cfg.end)
                if any(store.has("nbbo", r, d) for r in all_roots)] if all_roots else []
    days = list(days)
    for day in days:
        store.check(day)
    depth = max([a.needs.history for a in accounts] + [11])
    history = History(depth)
    if days:
        for prior in store.history_days(days[0], depth):
            for root in all_roots:
                if store.has("underlying", root, prior):
                    history.add(root, store.underlying(root, prior).price)
    events = EventCalendar(store.trading_days(), store.session)
    regimes: dict[str, dict[str, dict[str, float]]] = {}
    from .store import ordinal as to_ordinal

    for n, day in enumerate(days):
        data = DayData(store, day, all_roots, events, history, to_ordinal(day))
        regimes[day.isoformat()] = {root: data.regime(root) for root in data.chains}
        live = [a for a in accounts if a.roots]
        for account in live:
            account.begin_day(data)
        schedules = [account.decision_minutes(data) for account in live]
        events_minutes = set()
        for rules in data.rules.values():
            for minute in (rules.open_cutoff, rules.close_cutoff, rules.liquidation):
                if minute is not None and data.open_min < minute < data.close_min:
                    events_minutes.update(range(minute - data.open_min, data.minutes - 1) if minute == rules.liquidation
                                          else [minute - data.open_min])
        for mi in range(1, data.minutes - 1):
            data.advance(mi)
            for account, schedule in zip(live, schedules):
                wants = mi in schedule
                if wants or account.orders or (account.positions and mi in events_minutes):
                    account.step(data, mi, wants)
        for account in live:
            account.end_day(data, last=n == len(days) - 1)
        for root, chain in data.chains.items():
            history.add(root, chain.underlying.price)
        if progress is not None:
            progress(n + 1, len(days), day)
    elapsed = time.perf_counter() - began
    data_version = store.data_version(all_roots, days) if days else "no-days"
    return [R.build(a, cfg, days, data_version, regimes, elapsed / max(1, len(accounts))) for a in accounts]


__all__ = ["RunConfig", "run", "Account", "DayData", "History"]
