"""Per-desk sub-ledgers derived from the event log.

A desk never holds a balance of its own. Its book is a *fold* of three kinds of public event:

* `committee.allocation` -- the committee's capital target for the desk. The difference between
  a new target and the previous one is an external flow (a deposit or a withdrawal), exactly the
  way a brokerage transfer is. Flows move cash and `net_deposits`; they never move return.
* `broker.fill` -- cash, positions, average cost, realized profit and fees.
* `ledger.mark` -- a valuation observation: equity, cash, marks per position and the daily P&L.

Returns are time-weighted: growth is chained across sub-periods that are broken by every external
flow, so adding money cannot look like skill (see `docs/history/lessons/06-portfolio-returns.md`).
Growth is carried as an exact `Fraction` and only rendered to `Decimal` at the edge. Drawdown is
measured on the same flow-neutral growth index rather than on raw equity.

Folding is incremental: the state is cached against the last sequence number consumed, so calling
`state()` in a tick loop reads only the events appended since the previous call.
"""

from __future__ import annotations

import datetime as _dt
import functools
import threading
from dataclasses import dataclass, field
from decimal import Decimal
from fractions import Fraction
from typing import Any, Iterable, Iterator, Mapping

from .broker import Instrument, Position, Quote, money, text
from .events import EventLog, Event

ZERO = Decimal(0)
ONE = Fraction(1)

#: Event kinds a desk ledger folds. Everything else is ignored.
LEDGER_KINDS = ("committee.allocation", "broker.fill", "ledger.mark")

_HISTORY_LIMIT = 1000


# --------------------------------------------------------------------------- time helpers

def iso_time(value: Any = None) -> str:
    """Normalize a timestamp to the log's `YYYY-MM-DDTHH:MM:SS.mmmZ` shape.

    Accepts an ISO string (returned unchanged), a `datetime` (naive values are read as UTC),
    a POSIX float/int, or `None` for "now".
    """
    if value is None:
        value = _dt.datetime.now(_dt.timezone.utc)
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        value = _dt.datetime.fromtimestamp(float(value), _dt.timezone.utc)
    if isinstance(value, _dt.datetime):
        moment = value if value.tzinfo else value.replace(tzinfo=_dt.timezone.utc)
        moment = moment.astimezone(_dt.timezone.utc)
        return moment.strftime("%Y-%m-%dT%H:%M:%S") + f".{moment.microsecond // 1000:03d}Z"
    raise TypeError(f"cannot read {value!r} as a timestamp")


def parse_iso(value: str) -> _dt.datetime:
    """Parse a log timestamp into an aware UTC datetime."""
    stamp = value.replace("Z", "+00:00")
    moment = _dt.datetime.fromisoformat(stamp)
    return moment if moment.tzinfo else moment.replace(tzinfo=_dt.timezone.utc)


def day_of(value: str) -> str:
    """The UTC calendar day of a log timestamp."""
    return value[:10]


def days_between(start: str, end: str) -> int:
    return max(0, (parse_iso(end).date() - parse_iso(start).date()).days)


# --------------------------------------------------------------------------- value helpers

def price_of(value: Any) -> Decimal | None:
    """Read a mark out of a `Quote`, a `Decimal`, a numeric string or a mapping."""
    if value is None:
        return None
    if isinstance(value, Quote):
        return value.mid
    if isinstance(value, Decimal):
        return value
    if isinstance(value, Mapping):
        for key in ("mark", "price", "last", "mid"):
            if value.get(key) is not None:
                return money(value[key])
        bid, ask = value.get("bid"), value.get("ask")
        if bid is not None and ask is not None:
            return (money(bid) + money(ask)) / 2
        return None
    return money(value)


def quote_prices(quotes: Any) -> dict[str, Decimal]:
    """Normalize a quote collection to `{instrument key: price}`.

    Accepts a mapping keyed by `Instrument.key` or by `Instrument`, or any iterable of `Quote`.
    """
    out: dict[str, Decimal] = {}
    if quotes is None:
        return out
    if isinstance(quotes, Mapping):
        items: Iterable[tuple[Any, Any]] = quotes.items()
    else:
        items = ((getattr(q, "instrument", None), q) for q in quotes)
    for key, value in items:
        if isinstance(key, Instrument):
            key = key.key
        elif key is None and isinstance(value, Quote):
            key = value.instrument.key
        if not isinstance(key, str):
            continue
        price = price_of(value)
        if price is not None and price > 0:
            out[key] = price
    return out


def _fraction(value: Decimal) -> Fraction:
    return Fraction(value)


def _pct(growth: Fraction, places: str = "0.0001") -> Decimal:
    value = Decimal(growth.numerator) / Decimal(growth.denominator)
    return (value * 100).quantize(Decimal(places))


def _ratio(value: Fraction, places: str = "0.000001") -> Decimal:
    return (Decimal(value.numerator) / Decimal(value.denominator)).quantize(Decimal(places))


# --------------------------------------------------------------------------- state

@dataclass(frozen=True)
class LedgerState:
    """One desk's book at a moment in time. All money is `Decimal`."""

    desk_id: str
    as_of: str
    cash: Decimal
    positions: dict[str, Position]
    equity: Decimal
    net_deposits: Decimal
    realized_pnl: Decimal  # trading gains and losses only; fees are reported separately
    fees: Decimal
    daily_pnl: Decimal
    start_of_day_equity: Decimal
    max_drawdown_pct: Decimal  # 0..1, measured on the flow-neutral growth index
    time_weighted_return_pct: Decimal  # percentage points, e.g. Decimal("19.6630")
    history: list[dict[str, Any]] = field(default_factory=list)
    allocation: Decimal = ZERO  # the committee's current capital target
    decisions: int = 0  # fills recorded for the desk
    started_at: str | None = None
    days_live: int = 0
    seq: int = 0

    @property
    def gross_exposure(self) -> Decimal:
        total = ZERO
        for position in self.positions.values():
            value = position.market_value
            total += abs(value if value is not None else position.cost_basis)
        return total

    @property
    def pnl_pct(self) -> Decimal:
        """Total return in percentage points; the same number as `time_weighted_return_pct`."""
        return self.time_weighted_return_pct

    def to_dict(self) -> dict[str, Any]:
        return {
            "desk_id": self.desk_id,
            "as_of": self.as_of,
            "cash": text(self.cash),
            "equity": text(self.equity),
            "positions": [p.to_dict() for p in self.positions.values()],
            "net_deposits": text(self.net_deposits),
            "realized_pnl": text(self.realized_pnl),
            "fees": text(self.fees),
            "daily_pnl": text(self.daily_pnl),
            "start_of_day_equity": text(self.start_of_day_equity),
            "max_drawdown_pct": text(self.max_drawdown_pct),
            "time_weighted_return_pct": text(self.time_weighted_return_pct),
            "allocation": text(self.allocation),
            "decisions": self.decisions,
            "started_at": self.started_at,
            "days_live": self.days_live,
        }


# --------------------------------------------------------------------------- the ledger

def _locked(method):
    """Run the method under the ledger's lock. The fold is not re-entrant across threads: on
    Sept 16, 2026 a strategy worker and the tick folded one ledger at once, a pre-allocation
    mark landed after a capital withdrawal, the return index spiked 90 percent, and the next
    mark read as a 47 percent drawdown that zeroed every live sleeve."""

    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)

    return wrapper


class DeskLedger:
    """Derived, append-only view of one desk's capital. Never stores anything of its own."""

    def __init__(self, log: EventLog, desk_id: str, *, until: str | None = None):
        self.log = log
        self.desk_id = desk_id
        self.stream = f"ledger:{desk_id}"
        #: When set, the fold stops at this timestamp, giving the book as it stood then. Used for
        #: trailing-window measurements (a week of realized profit, say) without a second store.
        self.until = until
        self._lock = threading.RLock()
        self._reset()

    # ------------------------------------------------------------------ fold state
    def _reset(self) -> None:
        self._seq = 0
        self._cash = ZERO
        self._positions: dict[str, Position] = {}
        self._marks: dict[str, Decimal] = {}
        self._net_deposits = ZERO
        self._realized = ZERO
        self._fees = ZERO
        self._allocation = ZERO
        self._growth = ONE
        self._base_equity = ZERO
        self._peak_capital = ZERO
        self._peak_growth = ONE
        self._max_dd = Fraction(0)
        self._day: str | None = None
        self._start_of_day = ZERO
        self._last_mark_equity = ZERO
        self._history: list[dict[str, Any]] = []
        self._started_at: str | None = None
        self._last_at: str | None = None
        self._decisions = 0
        self._fill_ids: set[str] = set()

    @_locked
    def reset(self) -> None:
        """Drop the cache and refold from the beginning on the next read."""
        self._reset()

    # ------------------------------------------------------------------ equity
    def _equity_with(self, marks: Mapping[str, Decimal] | None = None) -> Decimal:
        total = self._cash
        for key, position in self._positions.items():
            if position.quantity == 0:
                continue
            price = None
            if marks is not None:
                price = marks.get(key)
            if price is None:
                price = self._marks.get(key)
            if price is None:
                price = position.average_cost
            total += position.quantity * price * position.instrument.multiplier
        return total

    # ------------------------------------------------------------------ folding
    @_locked
    def _consume(self) -> None:
        while True:
            batch = self.log.read(after=self._seq, limit=2000)
            if not batch:
                return
            for event in batch:
                if self.until is not None and event.at > self.until:
                    return
                if event.kind in LEDGER_KINDS:
                    self._apply(event)
                self._seq = event.seq
                self._last_at = event.at
            if len(batch) < 2000:
                return

    def _apply(self, event: Event) -> None:
        if event.kind == "committee.allocation":
            self._apply_allocation(event)
        elif event.kind == "broker.fill":
            self._apply_fill(event)
        elif event.kind == "ledger.mark" and event.stream == self.stream:
            self._apply_mark(event)

    # -- external flows ------------------------------------------------------
    def _apply_allocation(self, event: Event) -> None:
        allocations = event.payload.get("allocations") or {}
        if not isinstance(allocations, Mapping) or self.desk_id not in allocations:
            return
        try:
            target = money(allocations[self.desk_id])
        except (TypeError, ValueError):
            return
        if target < 0:
            return
        flow = target - self._allocation
        self._allocation = target
        if flow == 0:
            return
        equity_before = self._equity_with()
        if self._started_at is None:
            self._started_at = event.at
            self._day = day_of(event.at)
            self._base_equity = equity_before + flow
            self._start_of_day = equity_before + flow
            self._last_mark_equity = equity_before + flow
        else:
            if self._base_equity > 0 and not self._unfunded():
                self._growth *= _fraction(equity_before) / _fraction(self._base_equity)
            self._base_equity = equity_before + flow
            self._start_of_day += flow
            self._last_mark_equity += flow
        self._cash += flow
        self._net_deposits += flow
        if self._net_deposits > self._peak_capital:
            self._peak_capital = self._net_deposits
        self._observe(event.at, equity_before + flow, flow=True)

    # -- fills ---------------------------------------------------------------
    def _apply_fill(self, event: Event) -> None:
        payload = event.payload
        if payload.get("desk_id") != self.desk_id:
            return
        fill_id = payload.get("fill_id") or payload.get("id") or event.id
        if fill_id in self._fill_ids:
            return
        try:
            instrument = Instrument.from_dict(payload["instrument"])
            side = payload["side"]
            quantity = money(payload["quantity"])
            price = money(payload["price"])
            fee = money(payload.get("fee", "0"))
        except (KeyError, TypeError, ValueError):
            # A malformed fill is not silently absorbed into the book: it is skipped so the
            # rest of the fold stays truthful, and `verify()` still proves nothing was edited.
            return
        if side not in ("buy", "sell") or quantity <= 0 or price < 0 or fee < 0:
            return
        self._fill_ids.add(fill_id)
        multiplier = instrument.multiplier
        notional = quantity * price * multiplier

        self._cash += (-notional - fee) if side == "buy" else (notional - fee)
        self._fees += fee
        self._decisions += 1
        self._marks[instrument.key] = price

        signed = quantity if side == "buy" else -quantity
        position = self._positions.get(instrument.key)
        if position is None or position.quantity == 0:
            self._positions[instrument.key] = Position(
                instrument=instrument, quantity=signed, average_cost=price, mark=price, as_of=event.at
            )
            return
        held = position.quantity
        average = position.average_cost
        if (held > 0) == (signed > 0):  # adding to the same side
            after = held + signed
            position.average_cost = (held * average + signed * price) / after
            position.quantity = after
        else:  # reducing, closing or flipping
            closing = min(abs(signed), abs(held))
            direction = Decimal(1) if held > 0 else Decimal(-1)
            self._realized += closing * (price - average) * direction * multiplier
            after = held + signed
            position.quantity = after
            if after == 0:
                position.average_cost = ZERO
            elif (after > 0) != (held > 0):
                position.average_cost = price
        position.mark = price
        position.as_of = event.at
        if position.quantity == 0:
            self._positions.pop(instrument.key, None)

    # -- marks ---------------------------------------------------------------
    def _apply_mark(self, event: Event) -> None:
        payload = event.payload
        as_of = payload.get("as_of") or event.at
        for row in payload.get("positions") or []:
            try:
                key = Instrument.from_dict(row["instrument"]).key
                raw = row.get("mark")
                if raw is None:
                    raw = row.get("price")
                mark = None if raw is None else money(raw)
            except (KeyError, TypeError, ValueError):
                continue
            if mark is not None:
                self._marks[key] = mark
                position = self._positions.get(key)
                if position is not None:
                    position.mark = mark
                    position.as_of = as_of
        try:
            equity = money(payload["equity"]) if payload.get("equity") is not None else self._equity_with()
        except (TypeError, ValueError):
            equity = self._equity_with()
        day = day_of(as_of)
        if self._day is None:
            self._day = day
            self._start_of_day = equity
        elif day != self._day:
            self._start_of_day = self._last_mark_equity
            self._day = day
        if self._started_at is None:
            self._started_at = as_of
            self._base_equity = equity
        self._last_mark_equity = equity
        self._observe(as_of, equity)

    # -- the growth index ----------------------------------------------------
    def _unfunded(self) -> bool:
        """True while the book holds less than a tenth of the most capital it ever had. Its return
        index is then frozen: measured against a few dollars of leftover P&L, a sleeve cut to zero
        read a $2.50 mark move as a 38 percent drawdown (Sept 16, 2026), and the committee acted
        on it."""
        return self._peak_capital > 0 and self._base_equity < self._peak_capital / 10

    def _growth_at(self, equity: Decimal) -> Fraction:
        if self._base_equity <= 0 or self._unfunded():
            return self._growth
        return self._growth * (_fraction(equity) / _fraction(self._base_equity))

    def _observe(self, at: str, equity: Decimal, *, flow: bool = False) -> None:
        growth = self._growth if flow else self._growth_at(equity)
        if growth > self._peak_growth:
            self._peak_growth = growth
        if self._peak_growth > 0:
            drawdown = (self._peak_growth - growth) / self._peak_growth
            if drawdown > self._max_dd:
                self._max_dd = drawdown
        point = {
            "at": at,
            "equity": text(equity),
            "time_weighted_return_pct": text(_pct(growth - ONE)),
        }
        if self._history and self._history[-1]["at"] == at:
            self._history[-1] = point
        else:
            self._history.append(point)
            if len(self._history) > _HISTORY_LIMIT:
                del self._history[0]

    # ------------------------------------------------------------------ reads
    @_locked
    def state(self, now: Any = None) -> LedgerState:
        """Fold every event appended since the last call and return the desk's book."""
        self._consume()
        as_of = iso_time(now) if now is not None else (self._last_at or iso_time())
        equity = self._equity_with()
        growth = self._growth_at(equity)
        max_dd = self._max_dd
        if self._peak_growth > 0:
            current_dd = (self._peak_growth - growth) / self._peak_growth
            if current_dd > max_dd:
                max_dd = current_dd
        positions = {
            key: Position(
                instrument=p.instrument,
                quantity=p.quantity,
                average_cost=p.average_cost,
                mark=self._marks.get(key, p.mark),
                as_of=p.as_of,
            )
            for key, p in self._positions.items()
        }
        start_of_day = self._start_of_day
        if self._day is not None and day_of(as_of) != self._day:
            start_of_day = self._last_mark_equity
        return LedgerState(
            desk_id=self.desk_id,
            as_of=as_of,
            cash=self._cash,
            positions=positions,
            equity=equity,
            net_deposits=self._net_deposits,
            realized_pnl=self._realized,
            fees=self._fees,
            daily_pnl=equity - start_of_day,
            start_of_day_equity=start_of_day,
            max_drawdown_pct=_ratio(max_dd),
            time_weighted_return_pct=_pct(growth - ONE),
            history=[dict(point) for point in self._history],
            allocation=self._allocation,
            decisions=self._decisions,
            started_at=self._started_at,
            days_live=days_between(self._started_at, as_of) if self._started_at else 0,
            seq=self._seq,
        )

    def positions(self, now: Any = None) -> dict[str, Position]:
        return self.state(now).positions

    def equity(self, now: Any = None) -> Decimal:
        return self.state(now).equity

    # ------------------------------------------------------------------ writes
    @_locked
    def mark(self, quotes: Any, now: Any = None, *, shadow: bool = False) -> Event:
        """Append a `ledger.mark` valuation. Idempotent on `mark:<desk>:<as_of>`.

        `shadow` marks the valuation of a scoring book: the numbers are hypothetical and the
        site must never fold them into the floor's real equity.
        """
        as_of = iso_time(now)
        state = self.state(as_of)
        prices = quote_prices(quotes)
        rows = []
        equity = state.cash
        for key, position in sorted(state.positions.items()):
            price = prices.get(key, position.mark)
            if price is None:
                price = position.average_cost
            valued = Position(
                instrument=position.instrument,
                quantity=position.quantity,
                average_cost=position.average_cost,
                mark=price,
                as_of=as_of,
            )
            equity += valued.market_value or ZERO
            # `price` is the site's name for the mark; both are written so a reader of either
            # vocabulary gets the same number.
            rows.append({**valued.to_dict(), "price": text(price)})
        start_of_day = state.start_of_day_equity
        if self._day is not None and day_of(as_of) != self._day:
            start_of_day = self._last_mark_equity
        payload = {
            "desk_id": self.desk_id,
            "equity": text(equity),
            "cash": text(state.cash),
            "positions": rows,
            "daily_pnl": text(equity - start_of_day),
            "as_of": as_of,
        }
        if shadow:
            payload["shadow"] = True
        return self.log.append(
            self.stream, "ledger.mark", payload, id=f"mark:{self.desk_id}:{as_of}", at=as_of
        )


def floor_totals(
    ledgers: Mapping[str, DeskLedger], now: Any = None, *, include: Any = None
) -> dict[str, Decimal]:
    """Equity, cash and daily P&L summed across desk sub-ledgers.

    `include` is an optional container of desk ids to count. The floor's real book is the sum of
    the **live** sleeves only: a shadow desk's book is a score, not money, and adding it to the
    floor's equity would publish a number nobody owns.
    """
    equity = cash = daily = deposits = ZERO
    for desk_id, ledger in ledgers.items():
        if include is not None and desk_id not in include:
            continue
        state = ledger.state(now)
        equity += state.equity
        cash += state.cash
        daily += state.daily_pnl
        deposits += state.net_deposits
    return {"equity": equity, "cash": cash, "daily_pnl": daily, "net_deposits": deposits}


def position_walk(fills: Iterable[Mapping[str, Any]], *, shorts: bool = False) -> Iterator[dict[str, Any]]:
    """One desk's fills in one instrument, walked in log order the way the ledger folds them: for
    each fill, when the position it touched was opened and what share of the opening fills' fees
    the quantity it closed carries.

    A position opens with the first fill after it was flat, so a round trip four days after the
    last one is its own position, not a 97-hour hold. Fees are pooled at average cost, like the
    price: a reducing fill takes pool x closed / held, whatever order the adds and partial sells
    came in, so the shares of one position's partial sells add up to its entry fees. A reducing
    fill's own fee is not in `entry_fees`: it is the exit's fee, which the gateway already charges
    to the outcome's P&L. With `shorts=False` (the floor holds no shorts) a sell closes at most
    what is held and a sell with nothing held is passed over, so a window of the tape that begins
    mid-position cannot invent one.

    Each row carries `fill_id`, `at`, `side`, `quantity`, `opened_at` (of the position the fill
    added to or closed), `closed` (quantity closed, zero for an add), `entry_fees` (the closed
    quantity's share) and `held` (after the fill), as Decimals where they are amounts.
    """
    held = ZERO
    pool = ZERO
    opened_at: str | None = None
    for fill in fills:
        try:
            quantity = Decimal(str(fill["quantity"]))
            fee = Decimal(str(fill.get("fee") or "0"))
        except (KeyError, TypeError, ValueError, ArithmeticError):
            continue
        side = fill.get("side")
        if side not in ("buy", "sell") or not quantity.is_finite() or quantity <= 0 or not fee.is_finite() or fee < 0:
            continue
        at = str(fill.get("at") or "")
        row: dict[str, Any] = {
            "fill_id": str(fill.get("fill_id") or fill.get("id") or ""),
            "at": at,
            "side": side,
            "quantity": quantity,
            "opened_at": opened_at,
            "closed": ZERO,
            "entry_fees": ZERO,
            "held": held,
        }
        signed = quantity if side == "buy" else -quantity
        if held == 0 and signed < 0 and not shorts:
            yield row  # nothing held to sell
            continue
        if held == 0 or (held > 0) == (signed > 0):
            if held == 0:
                opened_at, pool = at, ZERO
            held += signed
            pool += fee
            row.update(opened_at=opened_at, held=held)
            yield row
            continue
        closing = min(abs(signed), abs(held))
        share = pool * closing / abs(held)
        pool -= share
        before = held
        held = held + signed if shorts or abs(signed) <= abs(held) else ZERO
        row.update(opened_at=opened_at, closed=closing, entry_fees=share, held=held)
        if held == 0:
            pool = ZERO
        elif (held > 0) != (before > 0):  # flipped: the remainder opens a new position here
            opened_at, pool = at, fee * abs(held) / quantity
        yield row
