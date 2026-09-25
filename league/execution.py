"""An agent's own execution: how often its orders fill and how long they take (X1 of the forward-first run).

Sept 25, 2026. The real fill rate was 37% per order at T0 (Kalshi 62 of 89 orders, Alpaca 13 of 113 at 10:36Z),
and the gap is Alpaca's crypto dip bids: they rest under the touch and are cancelled unfilled. Read per agent on
the T0 snapshot (04:23Z) over seven days, the Kalshi agents with five or more finished real orders fill 38-100% of
them (hilibrand-lc04657 25 of 33, median 1.4 minutes to fill) while the crypto-alts probes fill 0-18% (haghani-56 2
of 23, haghani-r42c38c 0 of 18, haghani-62 2 of 17, haghani-63 4 of 22; unfilled orders cancelled after a median
29-52 minutes). No agent could see that: its snapshot carried its last 12 order outcomes, never a rate, and a
strategy that never learns its bids do not fill keeps bidding the same way. So every wake's snapshot carries
the agent's own fill rate and median time to fill on the real book of its venue (`House.snapshot`,
`ctx["execution"]`), and the research brief asks for a requote rule where the rate is under `REQUOTE_BELOW`
on at least `REQUOTE_MIN_ORDERS` finished orders (`Researcher._state`).

The measure, per (agent, book), over the orders the agent had a share of that were first placed in the last
`WINDOW_DAYS` days (`book.order`: an order is one `order_id`, whatever status rows follow it):

- `orders`: every such order the venue did not reject (a rejection -- an unfunded Kalshi shard, say -- is not a
  question of price); `filled`: those with a venue fill of the agent's (`book.fill` `source: venue`, partial
  fills included); `unfilled`: those that ended cancelled or expired with none; `resting`: the rest, still
  working. `fill_rate` = filled / (filled + unfilled): an order still resting has not answered yet.
- `median_minutes_to_fill`: from the order's first row (written before the order is sent) to the agent's first
  fill of it; `median_minutes_unfilled`: from the first row to the row that ended it, how long an unfilled
  order was left to rest.
- `entries`: the same counts for buy orders only, the orders a requote rule is about.

The counts are folded from the ledger once and afterwards only from the rows appended since, one index per
ledger (`_INDEXES`, as `auditor.order_outcomes` keeps its own): 27,099 order and fill rows on the T0 snapshot
parse in 0.25 s, and every later wake reads only what is new. Read-only: nothing here writes anything.
"""

from __future__ import annotations

import statistics
import threading
import weakref
from datetime import datetime
from typing import Any, Mapping

#: How far back an agent's execution is measured: a week holds a probe's whole stay so far (the five crypto-alts
#: probes of Sept 24-25 placed 17-23 real orders each in it), and old habits of a rewritten program fall out.
WINDOW_DAYS = 7.0
#: The research brief asks for a requote rule under this fill rate (the plan's row 6 target, 25%)...
REQUOTE_BELOW = 0.25
#: ... on at least this many finished orders: 0 of 3 is a question, not a finding (haghani-58 and -59 at T0).
REQUOTE_MIN_ORDERS = 5
#: The real book of each venue, whose rate the snapshot carries and the brief reads.
REAL_BOOK = {"alpaca": "alpaca", "kalshi": "kalshi"}
_KINDS = ("book.order", "book.fill")
_ENDED = ("filled", "cancelled", "canceled", "expired", "done_for_day")
DAY = 86400.0


def _epoch(at: Any) -> float:
    try:
        return datetime.fromisoformat(str(at).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return 0.0


class _Order:
    __slots__ = ("placed", "side", "filled", "ended", "rejected")

    def __init__(self, placed: float, side: str):
        self.placed, self.side = placed, side
        self.filled: float | None = None
        self.ended: float | None = None
        self.rejected = False


class FillIndex:
    """Every agent's orders on every book, folded from one ledger after a cursor: (agent, book) -> {order id: _Order}.
    Orders placed more than `WINDOW_DAYS` + 1 days before the newest row are dropped as the index advances."""

    def __init__(self) -> None:
        self.cursor = 0
        self.orders: dict[tuple[str, str], dict[str, _Order]] = {}
        self._owners: dict[str, list[tuple[str, str]]] = {}  # order id -> the (agent, book) keys that hold it
        self.newest = 0.0
        self._pruned = 0.0
        self.lock = threading.Lock()

    def refresh(self, ledger: Any) -> None:
        with self.lock:
            for entry in ledger.iter(kinds=_KINDS, after=self.cursor):
                self._fold(entry)
                self.cursor = entry.seq
            if self.newest - self._pruned > DAY / 4:
                self._prune()

    def _fold(self, entry: Any) -> None:
        p = entry.payload
        at = _epoch(entry.at)
        self.newest = max(self.newest, at)
        book, order_id = str(p.get("book") or ""), str(p.get("order_id") or "")
        if not book or not order_id:
            return
        if entry.kind == "book.fill":
            if p.get("source") != "venue":
                return
            order = self.orders.get((str(entry.agent), book), {}).get(order_id)
            if order is not None and order.filled is None:
                order.filled = at
            return
        owners = self._owners.get(order_id)
        if owners is None:
            agents = dict.fromkeys(str(s["agent"]) for s in p.get("shares") or [] if isinstance(s, Mapping) and s.get("agent"))
            owners = self._owners[order_id] = [(agent, book) for agent in agents]
            for key in owners:
                self.orders.setdefault(key, {})[order_id] = _Order(at, str(p.get("side") or ""))
        status = str(p.get("status") or "").lower()
        for key in owners:
            order = self.orders.get(key, {}).get(order_id)
            if order is None:
                continue
            if status == "rejected":
                order.rejected = True
            if status in _ENDED or status == "rejected":
                order.ended = order.ended or at

    def _prune(self) -> None:
        oldest = self.newest - (WINDOW_DAYS + 1) * DAY
        for key in list(self.orders):
            kept = {oid: o for oid, o in self.orders[key].items() if o.placed >= oldest}
            for oid in set(self.orders[key]) - set(kept):
                self._owners[oid] = []  # known and out of the window: a late status row starts no new order
            if kept:
                self.orders[key] = kept
            else:
                del self.orders[key]
        self._pruned = self.newest

    def stats(self, agent: str, book: str, now: float, *, days: float = WINDOW_DAYS) -> dict[str, Any]:
        with self.lock:
            rows = [o for o in (self.orders.get((str(agent), str(book))) or {}).values()
                    if now - days * DAY <= o.placed <= now and not (o.rejected and o.filled is None)]
            return {"book": book, "days": days, **_measure(rows),
                    "entries": {k: v for k, v in _measure([o for o in rows if o.side == "buy"]).items()
                                if k in ("orders", "filled", "unfilled", "resting", "fill_rate")}}


def _measure(rows: list[_Order]) -> dict[str, Any]:
    filled = [o for o in rows if o.filled is not None]
    unfilled = [o for o in rows if o.filled is None and o.ended is not None]
    finished = len(filled) + len(unfilled)
    to_fill = [max(0.0, o.filled - o.placed) / 60.0 for o in filled]
    left = [max(0.0, o.ended - o.placed) / 60.0 for o in unfilled]
    return {"orders": len(rows), "filled": len(filled), "unfilled": len(unfilled), "resting": len(rows) - finished,
            "fill_rate": round(len(filled) / finished, 4) if finished else None,
            "median_minutes_to_fill": round(statistics.median(to_fill), 1) if to_fill else None,
            "median_minutes_unfilled": round(statistics.median(left), 1) if left else None}


_INDEXES: "weakref.WeakKeyDictionary[Any, FillIndex]" = weakref.WeakKeyDictionary()
_INDEXES_LOCK = threading.Lock()


def _index(ledger: Any) -> FillIndex:
    try:
        with _INDEXES_LOCK:
            index = _INDEXES.get(ledger)
            if index is None:
                index = _INDEXES[ledger] = FillIndex()
    except TypeError:  # a ledger that cannot be weakly referenced (a test's fake): folded afresh
        index = FillIndex()
    index.refresh(ledger)
    return index


def fill_stats(ledger: Any, agent: str, book: str, now: float, *, days: float = WINDOW_DAYS) -> dict[str, Any]:
    """The agent's own execution on `book` over the last `days` days (the module docstring has the measure)."""
    return _index(ledger).stats(agent, book, now, days=days)


def real_fill_stats(ledger: Any, agent: str, venue: str, now: float) -> dict[str, Any] | None:
    """`fill_stats` on the real book of the agent's venue, or None for a venue with none."""
    book = REAL_BOOK.get(str(venue))
    return fill_stats(ledger, agent, book, now) if book else None


def needs_requote(stats: Mapping[str, Any] | None) -> bool:
    """Whether the research brief asks for a requote rule: at least `REQUOTE_MIN_ORDERS` finished orders on the real
    book and a fill rate under `REQUOTE_BELOW`."""
    if not stats:
        return False
    finished = int(stats.get("filled") or 0) + int(stats.get("unfilled") or 0)
    rate = stats.get("fill_rate")
    return finished >= REQUOTE_MIN_ORDERS and rate is not None and float(rate) < REQUOTE_BELOW
