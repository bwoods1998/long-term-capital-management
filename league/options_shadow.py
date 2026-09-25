"""The options shadow account: every level-3 structure on PRACTICE, held as one position.

Sept 25, 2026 (the options-desk run, `docs/goals/LTCM_OPTIONS_DESK.md` and the owner's amendment of
06:01Z in `docs/runs/2026-09-25-options-desk.md`, Track S). `OptionsShadowBroker` is a `Broker`
(`ltcm/broker.py`) over a simulated options account, as `KalshiShadowBroker` (`league/paper.py`) is for
Kalshi: it reads real, live option quotes, fills under the conservative rules below, charges the
replay's fee and never sends an order anywhere (it holds no credential; its only I/O is two
market-data readers the service injects). `league.book.Book` drives it as it drives every venue, so a
structure agent's practice record is kept by the same code that keeps a real one.

It trades STRUCTURES ONLY (`league/structures.py`): a structure is held as ONE long option-class
instrument whose `market_id` names its type and legs, priced at S = net value + collateral K a share,
so its cost is its maximum loss, an open is a BUY of it, a close is a SELL, and no negative leg exists
anywhere. Anything that is not a structure is refused with the reason, and no order is recorded.

**The touch.** A structure's quote is `structures.quote(spec, touches)` over its legs' live quotes (to
open, long legs at the ask and short legs at the bid; to close, the reverse), and its time is the
OLDEST leg's, so the book's `max_option_quote_age_seconds` judges it by its stalest leg. The legs come
from Alpaca's `/v1beta1/options/quotes/latest` (`alpaca_leg_quotes`, the OPRA feed on the House box),
several symbols a request: every leg of every structure an `advance` needs is ONE request (chunks of
`MAX_SYMBOLS`), and `quote` reads the legs of everything held or resting with the one asked for, held
`ttl` seconds, so a mark pass is one request too. Each leg keeps its `bid_size`/`ask_size` (`bs`/`as`).

**Fill rules.** Conservative means: where the tape cannot say whether a real order would have filled,
this account says it did not. The owner (Sept 25, 2026): never relax them.

1. A structure is a LIMIT order at its held price S (`structures.held_limit` turns a trader's natural
   limit into it), a `day` order, in whole structures, inside the regular US session of a trading day
   (`ltcm.data.market_open_at`). Anything else raises `RejectedOrder` and no order is recorded; so does
   a structure whose earliest expiry's session has closed.
2. `submit` is idempotent on the intent id and NEVER fills: nothing fills in the quote the decision
   saw. The order rests (`accepted`) with a floor: the later of its submission time and the time of
   the structure's quote (its oldest leg's) read fresh as it is accepted, and it may fill only in
   `advance()`, on a quote strictly NEWER than that: every leg quoted again after the order was
   accepted, so no quote the decision could have seen fills it (the House's chain is its own read). The rule is applied to closes as to opens: a close
   filled in the quote its decision saw would flatter a profit target exactly as an open would flatter
   an entry. After each fill the rest waits for a quote newer than the one that filled.
3. A BUY (an open) fills when the structure's ask <= its limit, AT that ask; a SELL (a close) when the
   bid >= its limit, AT that bid. Every leg must be quoted two-sided (0 < bid <= ask).
4. No fill takes more than 10% of any leg's shown size on the side it trades (an open takes a long
   leg's ask size and a short leg's bid size; a close the reverse), divided by the leg's ratio: a
   butterfly's body of 30 contracts bid lets one structure through, not one and a half. A leg that
   shows no size, or under ten contracts, gives no fill. The 10% is shared by every order filled on
   that leg's same quote, across passes, so a quote that does not change cannot be taken twice. What
   the size does not allow rests: partial fills are allowed. Measured on the House box on Sept 25, 2026
   (the latest OPRA quotes, from the Sept 24 close): SPY's Sept 28 legs a strike or two from the money
   showed 17 to 156 contracts a side, and one showed 2 on its ask.
5. Day orders: what has not filled when the session of its acceptance closes is `expired` (Alpaca's
   word for a day order at the bell).
6. No leverage and no shorts at the account level (the Book checks each agent; this is the backstop):
   a buy needs free cash for its limit x 100 x quantity plus the fee, a sell the free position; resting
   buys hold their cash and resting sells their structures. What cannot be carried is `rejected`, or
   `cancelled` if it cannot be carried when its fill comes.
7. Fees: `structures.fee_per_unit(spec)` a structure a fill, $0.05 a contract a leg (a vertical $0.10,
   a condor or a butterfly $0.20), the replay's assumption. The book's own fee model charges the same
   for this venue (`league.fees.Fees.charge`, the `options-shadow` rule), so the two agree to the cent.
8. The mark is the structure's bid (the book marks at `Quote.bid`).

**The expiry safety net.** The House closes a structure from 15:30 New York on its earliest expiry day.
One still held once that expiry's session has closed is settled by `structure_settlements()`, which the
book calls from `Book.expire_options` (never at zero there: it books the value this account paid, as a
`book.settle`): a single-expiry structure at `structures.intrinsic(spec, close)` on the underlying's
regular-session close (`alpaca_underlying_close`), a calendar or diagonal at what closing it then would
get, the far leg's bid less the near leg's intrinsic (plus K), floored at zero (a far leg the source
cannot quote waits for a read: it is never valued at zero for want of one); the value a share is
floored to $0.0001. Resting orders on it expire with it. It settles only when asked: settled on its own
at the bell, it would disagree with the book until the book's next New York day and freeze the book.

What is NOT modelled: queue position (a fill is at the touch, as a taker, when the whole structure's
touch meets the limit); price improvement; assignment before expiry.

State (cash, positions by structure code, every order, every fill, every settlement, the counters) is
one JSON file, `<root>/options-shadow.json`, money as decimal strings, rewritten atomically (temp file,
fsync, `os.replace`, mode 0600) after every mutation and loaded on construction, so a House restart loses
nothing: resting orders, positions and cash come back as they were. A write that fails undoes the
mutation in memory and raises `VenueUnavailable`. `starting_cash` only matters when the file does not
exist yet (the service reads it from `config.json` `options_structures.shadow.starting_cash`).
"""

from __future__ import annotations

import dataclasses
import json
import os
import re
import threading
import time
import urllib.parse
from datetime import datetime, time as clock_time, timedelta
from decimal import ROUND_FLOOR, Decimal
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo

from ltcm.broker import (
    Balance,
    BrokerError,
    Fill,
    Instrument,
    Order,
    OrderIntent,
    Position,
    Quote,
    RejectedOrder,
    VenueUnavailable,
    instant,
    money,
)
from ltcm.data import market_open_at, previous_session, us_equity_session

from . import structures
from .ledger import now_iso
from .paper import _at_or_after, _cursor, _fill_from_dict, _order_from_dict, _order_to_dict

VENUE = "options-shadow"
ZERO = Decimal(0)
TEN = Decimal(10)
CENT = Decimal("0.01")
#: The settlement value a share is floored to this: never a fraction of a cent in the account's favour.
SETTLE_PLACES = Decimal("0.0001")
STATE_VERSION = 1
CAPABILITIES = frozenset({"option", "limit", "structures", "shadow"})
#: Alpaca's latest option quotes take at most 100 symbols a request.
MAX_SYMBOLS = 100
#: How long a leg's quote serves `quote()` (marks, the book's checks) before it is read again. An
#: `advance` always reads fresh.
QUOTE_TTL_SECONDS = 5.0
#: How long a failed read of an underlying's close waits before it is tried again.
CLOSE_RETRY_SECONDS = 300.0
DATA_URL = "https://data.alpaca.markets"
OPTION_QUOTES_PATH = "/v1beta1/options/quotes/latest"
NEW_YORK = ZoneInfo("America/New_York")
OPEN_STATUSES = ("accepted", "partially_filled")

#: `leg_quotes(occs) -> {occ: {"bid", "ask", "bid_size", "ask_size", "as_of"}}`: a leg the source has no
#: quote for is simply absent. `underlying_close(symbol, "YYYY-MM-DD") -> Decimal | None`.
LegQuotes = Callable[[Sequence[str]], Mapping[str, Mapping[str, Any]]]
UnderlyingClose = Callable[[str, str], Any]


def _text(value: Decimal | None) -> str | None:
    return None if value is None else format(value, "f")


def _number(value: Any) -> Decimal | None:
    """A market-data number as a Decimal, or None: through the House's `VenueClient` a price arrives as a
    Decimal and a size as an int (measured on the House box, Sept 25, 2026); plain JSON gives floats."""
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = Decimal(str(value)) if isinstance(value, (float, int)) else money(value)
    except (ValueError, ArithmeticError):
        return None
    return parsed if parsed.is_finite() else None


_FRACTION = re.compile(r"(\.\d{1,6})\d*")


def stamp(value: Any) -> str | None:
    """A quote time as `YYYY-MM-DDTHH:MM:SS.ffffffZ` (UTC, microseconds), or None. Alpaca stamps OPRA
    quotes to the nanosecond (`2026-09-24T19:59:59.992106043Z`, read on the House box Sept 25, 2026); the
    fraction is cut to microseconds before parsing, so one quote time has one spelling whatever reads it."""
    if not isinstance(value, str) or not value.strip():
        return None
    moment = instant(_FRACTION.sub(r"\1", value.strip(), count=1))
    return None if moment is None else moment.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _newer(candidate: str | None, floor: str | None) -> bool:
    """Strictly later than `floor` (a missing floor is no bar; a missing time is never newer)."""
    a = instant(candidate) if candidate else None
    if a is None:
        return False
    b = instant(floor) if floor else None
    return b is None or a > b


# ------------------------------------------------------------------------------ market data
def alpaca_leg_quotes(client: Any, *, feed: str = "indicative", data_url: str = DATA_URL) -> LegQuotes:
    """The production leg source: Alpaca's latest option quotes (`/v1beta1/options/quotes/latest`,
    documented at https://docs.alpaca.markets/reference/optionlatestquotes) through `client`, a
    `ltcm.adapters.VenueClient` in gateway mode or anything with `request(method, url, *, headers, what)
    -> (status, payload)` (the service passes the House's market-data client: read-only GETs). Several
    symbols a request, at most `MAX_SYMBOLS`. A transport failure or a non-200 answer raises."""

    def read(occs: Sequence[str]) -> dict[str, dict[str, Any]]:
        names = sorted({str(o).strip().upper() for o in occs if str(o).strip()})
        out: dict[str, dict[str, Any]] = {}
        for start in range(0, len(names), MAX_SYMBOLS):
            chunk = names[start:start + MAX_SYMBOLS]
            query = urllib.parse.urlencode({"symbols": ",".join(chunk), "feed": feed}, safe=",")
            what = f"options-shadow leg quotes ({len(chunk)})"
            status, payload = client.request("GET", f"{data_url}{OPTION_QUOTES_PATH}?{query}", headers={}, what=what)
            if status != 200 or not isinstance(payload, dict):
                raise VenueUnavailable(f"{what}: HTTP {status}")
            rows = payload.get("quotes")
            for symbol, row in (rows.items() if isinstance(rows, dict) else ()):
                if str(symbol).upper() in chunk and isinstance(row, dict):
                    out[str(symbol).upper()] = {
                        "bid": _number(row.get("bp")), "ask": _number(row.get("ap")),
                        "bid_size": _number(row.get("bs")), "ask_size": _number(row.get("as")),
                        "as_of": stamp(row.get("t")),
                    }
        return out

    return read


def alpaca_underlying_close(data: Any) -> UnderlyingClose:
    """The production close source: the underlying's last regular-session minute bar of `day` (the one
    closing at the session's close, 16:00 New York or 13:00 on an early close), from
    `league.tapes.AlpacaData.bars`, which stamps a bar with its close. None when the day had no
    session or the venue has no bar for it yet."""

    def close(symbol: str, day: str) -> Decimal | None:
        session = us_equity_session(day)
        if session is None:
            return None
        end = instant(session.close_at)
        start = end - timedelta(minutes=30)
        rows = (data.bars([symbol], "1Min", start=start.strftime("%Y-%m-%dT%H:%M:%SZ"), end=session.close_at, limit=60)
                or {}).get(str(symbol).upper()) or []
        return _number(rows[-1].get("c")) if rows else None

    return close


def _expiry_session(expiry: str):
    """The session an expiry's value is read on: its own day's, or the last before it on a holiday."""
    try:
        day = datetime.strptime(str(expiry), "%Y-%m-%d").date()
    except ValueError:
        return None
    return previous_session(datetime.combine(day, clock_time(23, 59), NEW_YORK))


class OptionsShadowBroker:
    """A simulated options account that trades structures only. See the module docstring."""

    def __init__(
        self,
        state_path: str | os.PathLike,
        leg_quotes: LegQuotes,
        *,
        underlying_close: UnderlyingClose | None = None,
        venue: str = VENUE,
        starting_cash: Any = "100000",
        clock: Callable[[], float] = time.time,
        quote_ttl: float = QUOTE_TTL_SECONDS,
        feed: str = "opra",
    ):
        if not callable(leg_quotes):
            raise TypeError("leg_quotes must be a callable: (occ symbols) -> {occ: leg quote}")
        self.venue = venue
        self.state_path = Path(state_path)
        self.leg_quotes = leg_quotes
        self.underlying_close = underlying_close
        self.clock = clock
        self.quote_ttl = float(quote_ttl)
        self.feed = str(feed)
        self._lock = threading.RLock()
        self._cache_lock = threading.Lock()
        self._cash = money(starting_cash)
        if self._cash < 0:
            raise ValueError("starting_cash must not be negative")
        #: structure code -> {"instrument", "quantity", "cost"}; cost is price x 100 x quantity, fees apart
        self._positions: dict[str, dict[str, Any]] = {}
        self._orders: dict[str, Order] = {}  # by "ord-..." id, in submission order
        self._by_broker_id: dict[str, str] = {}
        self._fills: list[Fill] = []
        self._settlements: list[dict[str, Any]] = []
        self._next_order = 1
        self._next_fill = 1
        #: occ -> (read at, the leg's row): what `quote` serves for `quote_ttl` seconds.
        self._legs: dict[str, tuple[float, dict[str, Any]]] = {}
        #: (occ, "bid" | "ask") -> (the leg quote's time, contracts already filled on it): rule 4's share.
        self._used: dict[tuple[str, str], tuple[str | None, Decimal]] = {}
        #: (symbol, day) -> the close, once read; and when a failed read was last tried.
        self._closes: dict[tuple[str, str], Decimal] = {}
        self._close_tried: dict[tuple[str, str], float] = {}
        with self._lock:
            if self.state_path.exists():
                self._load()
            else:
                self._save()

    # ------------------------------------------------------------------ state
    def _now(self) -> str:
        return now_iso(self.clock)

    def _save(self) -> None:
        state = {
            "version": STATE_VERSION,
            "venue": self.venue,
            "cash": _text(self._cash),
            "next_order": self._next_order,
            "next_fill": self._next_fill,
            "positions": {
                code: {"instrument": held["instrument"].to_dict(), "quantity": _text(held["quantity"]), "cost": _text(held["cost"])}
                for code, held in self._positions.items()
            },
            "orders": [_order_to_dict(order) for order in self._orders.values()],
            "fills": [fill.to_dict() for fill in self._fills],
            # Rule 4's shares of the leg quotes last filled on, so a restart cannot take the same quote's 10% twice.
            "used": [[occ, side, as_of, _text(used)] for (occ, side), (as_of, used) in sorted(self._used.items())],
            "settlements": [
                {**row, "instrument": row["instrument"].to_dict(), **{k: _text(row[k]) for k in ("quantity", "price", "spot", "cost", "value")}}
                for row in self._settlements
            ],
        }
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state_path.with_name(f".{self.state_path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(state, handle, separators=(",", ":"), sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, self.state_path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def _commit(self) -> None:
        """Write the mutation just made, or take it back (as the Kalshi shadow does, `paper.py`)."""
        try:
            self._save()
        except OSError as exc:
            self._load()
            raise VenueUnavailable(f"{self.venue}: the account could not be written, nothing was changed: {exc}") from exc

    def _load(self) -> None:
        """Read the account back. A file that cannot be read is an error, never a fresh account."""
        try:
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
            if not isinstance(state, dict) or state.get("version") != STATE_VERSION:
                raise ValueError(f"not a version {STATE_VERSION} options shadow account")
            if state.get("venue") != self.venue:
                raise ValueError(f"it is the account of {state.get('venue')!r}, not {self.venue!r}")
            self._cash = money(state["cash"])
            self._next_order = int(state["next_order"])
            self._next_fill = int(state["next_fill"])
            self._positions = {
                code: {"instrument": Instrument.from_dict(held["instrument"]), "quantity": money(held["quantity"]), "cost": money(held["cost"])}
                for code, held in state["positions"].items()
            }
            self._orders, self._by_broker_id = {}, {}
            for row in state["orders"]:
                order = _order_from_dict(row)
                self._orders[order.id] = order
                if order.broker_order_id:
                    self._by_broker_id[order.broker_order_id] = order.id
            self._fills = [_fill_from_dict(row) for row in state["fills"]]
            self._used = {(str(occ), str(side)): (as_of, money(used)) for occ, side, as_of, used in state.get("used") or []}
            self._settlements = [
                {**row, "instrument": Instrument.from_dict(row["instrument"]),
                 **{k: money(row[k]) for k in ("quantity", "price", "spot", "cost", "value")}}
                for row in state["settlements"]
            ]
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
            raise BrokerError(f"options shadow account {self.state_path} cannot be read: {exc}") from exc

    # ------------------------------------------------------------ market data
    def _wanted(self) -> set[str]:
        """Every leg of every structure held or resting: read with any leg asked for, in one request."""
        with self._lock:
            instruments = [held["instrument"] for held in self._positions.values()]
            instruments += [order.instrument for order in self._orders.values() if order.status in OPEN_STATUSES]
        legs: set[str] = set()
        for inst in instruments:
            try:
                legs.update(leg.occ for leg in structures.spec_of(inst).legs)
            except ValueError:
                continue
        return legs

    def _read_legs(self, occs: Iterable[str], *, fresh: bool = False) -> dict[str, dict[str, Any]]:
        """The legs' latest quotes, by OCC. Raises when the source cannot be read."""
        occs = {str(o).upper() for o in occs}
        now = float(self.clock())
        if not fresh:
            with self._cache_lock:
                hits = {occ: self._legs[occ] for occ in occs if occ in self._legs}
            if len(hits) == len(occs) and all(now - at < self.quote_ttl for at, _ in hits.values()):
                return {occ: row for occ, (_, row) in hits.items()}
            occs = occs | self._wanted()
        rows = self.leg_quotes(sorted(occs)) or {}
        read = {str(occ).upper(): dict(row) for occ, row in rows.items() if isinstance(row, Mapping)}
        with self._cache_lock:
            for occ in occs:
                # A leg the source did not answer for has no quote now: it must not be served from the cache.
                self._legs[occ] = (now, read.get(occ, {}))
        return {occ: read.get(occ, {}) for occ in occs}

    @staticmethod
    def _touches(spec: structures.Spec, rows: Mapping[str, Mapping[str, Any]], *, no_bid: Decimal | None = None) -> dict[str, tuple[Any, Any]]:
        """Each leg's (bid, ask), a side the venue shows as zero or not at all being None, or for the bid
        `no_bid`: `quote` passes zero, because a leg quoted with no bid is worth nothing to sell (so a long
        wing with no bid marks the structure lower, and a short leg with no bid makes opening it dearer),
        while a leg with no ask still has no price to buy it back at. Fills never read `no_bid`."""
        out = {}
        for leg in spec.legs:
            row = rows.get(leg.occ) or {}
            bid, ask = _number(row.get("bid")), _number(row.get("ask"))
            out[leg.occ] = (bid if bid is not None and bid > 0 else no_bid, ask if ask is not None and ask > 0 else None)
        return out

    @staticmethod
    def _oldest(spec: structures.Spec, rows: Mapping[str, Mapping[str, Any]]) -> str | None:
        """The structure's quote time: its oldest leg's (None when any leg has none)."""
        times = [(rows.get(leg.occ) or {}).get("as_of") for leg in spec.legs]
        moments = [instant(t) if t else None for t in times]
        if not moments or any(m is None for m in moments):
            return None
        return min(zip(moments, times))[1]

    def _spec(self, instrument: Instrument) -> structures.Spec:
        if not structures.is_structure(instrument):
            raise RejectedOrder(f"{self.venue} trades level-3 structures held as one position (league/structures.py), not {instrument.key}")
        if instrument.venue != self.venue:
            raise RejectedOrder(f"instrument venue {instrument.venue!r} is not {self.venue!r}")
        try:
            spec = structures.spec_of(instrument)
        except ValueError as exc:
            raise RejectedOrder(f"not an admitted structure: {exc}") from exc
        if instrument.multiplier != spec.legs[0].instrument.multiplier:
            raise RejectedOrder(f"a structure's multiplier is its legs' ({spec.legs[0].instrument.multiplier}), not {instrument.multiplier}")
        return spec

    def quote(self, instrument: Instrument) -> Quote:
        """The structure's touch (`structures.quote`) at its oldest leg's time; the mark is its bid."""
        try:
            spec = self._spec(instrument)
        except RejectedOrder as exc:
            raise VenueUnavailable(f"{self.venue}: no quote: {exc}") from exc
        try:
            rows = self._read_legs([leg.occ for leg in spec.legs])
        except BrokerError:
            raise
        except Exception as exc:  # noqa: BLE001 - one error family for every caller
            raise VenueUnavailable(f"{self.venue}: no leg quotes for {instrument.market_id}: {exc}") from exc
        as_of = self._oldest(spec, rows)
        if as_of is None:
            raise VenueUnavailable(f"{self.venue}: a leg of {instrument.market_id} has no quote")
        bid, ask = structures.quote(spec, self._touches(spec, rows, no_bid=ZERO))
        return Quote(instrument, bid, ask, None, as_of, f"{self.venue}:{self.feed}", delayed=self.feed != "opra")

    # ------------------------------------------------------------- accounting
    @staticmethod
    def _fee(spec: structures.Spec, quantity: Decimal) -> Decimal:
        return structures.fee_per_unit(spec) * quantity

    def _hold(self, order: Order) -> Decimal:
        """What a resting buy keeps aside: its limit's cost and the fee it would pay."""
        spec = structures.spec_of(order.instrument)
        return order.remaining * order.limit_price * order.instrument.multiplier + self._fee(spec, order.remaining)

    def _free_cash(self, *, excluding: str | None = None) -> Decimal:
        held = sum((self._hold(o) for o in self._orders.values()
                    if o.status in OPEN_STATUSES and o.side == "buy" and o.id != excluding), ZERO)
        return self._cash - held

    def _free_position(self, code: str, *, excluding: str | None = None) -> Decimal:
        quantity = self._positions[code]["quantity"] if code in self._positions else ZERO
        for order in self._orders.values():
            if order.status in OPEN_STATUSES and order.side == "sell" and order.id != excluding and order.instrument.market_id == code:
                quantity -= order.remaining
        return quantity

    def _refusal(self, order: Order, spec: structures.Spec, quantity: Decimal, price: Decimal) -> str:
        """Why the account cannot carry `quantity` of this order at `price`, or ""."""
        if order.side == "buy":
            need = quantity * price * order.instrument.multiplier + self._fee(spec, quantity)
            free = self._free_cash(excluding=order.id)
            if need > free:
                return f"insufficient cash: needs ${need:.2f} with fees, the account has ${free:.2f} free"
            return ""
        free = self._free_position(str(order.instrument.market_id), excluding=order.id)
        if quantity > free:
            return f"no structure to sell: {quantity} asked, {free} held and free (a structure is sold only from a holding)"
        return ""

    def _fill(self, order: Order, spec: structures.Spec, quantity: Decimal, price: Decimal, now: str) -> None:
        """`quantity` of the order at one price. The caller has checked `_refusal`."""
        instrument, code = order.instrument, str(order.instrument.market_id)
        fee = self._fee(spec, quantity)
        gross = quantity * price * instrument.multiplier
        if order.side == "buy":
            self._cash -= gross + fee
            held = self._positions.setdefault(code, {"instrument": instrument, "quantity": ZERO, "cost": ZERO})
            held["quantity"] += quantity
            held["cost"] += gross
        else:
            self._cash += gross - fee
            held = self._positions[code]
            held["cost"] -= held["cost"] * quantity / held["quantity"]
            held["quantity"] -= quantity
            if held["quantity"] <= 0:
                del self._positions[code]
        before = order.filled_quantity
        order.average_price = price if before == 0 else (order.average_price * before + price * quantity) / (before + quantity)
        order.filled_quantity = before + quantity
        order.fees = order.fees + fee
        order.status = "filled" if order.filled_quantity >= order.quantity else "partially_filled"
        order.updated_at = now
        self._fills.append(Fill(id=f"{self.venue}-fill-{self._next_fill}", order_id=order.id, desk_id=order.desk_id,
                                instrument=instrument, side=order.side, quantity=quantity, price=price, fee=fee, at=now))
        self._next_fill += 1

    @staticmethod
    def _close(order: Order, status: str, reason: str, now: str) -> None:
        order.status = status
        order.reason = reason
        order.updated_at = now

    @staticmethod
    def _copy(order: Order) -> Order:
        return dataclasses.replace(order, _raw=dict(order._raw))

    # --------------------------------------------------------------- protocol
    def capabilities(self) -> set[str]:
        return set(CAPABILITIES)

    def balance(self) -> Balance:
        """Equity is cash plus positions at cost: no quote is read, so it never fails. Cash is the
        account's own; what resting buys hold is not taken out of it (the book compares cash as such)."""
        with self._lock:
            at_cost = sum((held["cost"] for held in self._positions.values()), ZERO)
            return Balance(self.venue, self._cash, self._cash + at_cost, self._free_cash(), self._now())

    def positions(self) -> list[Position]:
        with self._lock:
            now = self._now()
            return [
                Position(held["instrument"], held["quantity"], held["cost"] / (held["quantity"] * held["instrument"].multiplier), as_of=now)
                for held in self._positions.values() if held["quantity"] != 0
            ]

    def _validate(self, intent: OrderIntent, now: str) -> structures.Spec:
        """Refuse what this account never takes, before any order is recorded (rule 1)."""
        spec = self._spec(intent.instrument)
        if intent.order_type != "limit" or intent.limit_price is None:
            raise RejectedOrder("a structure is a limit order at its net price a share: it has no touch to take")
        if intent.limit_price <= 0 or intent.limit_price != intent.limit_price.quantize(CENT):
            raise RejectedOrder(f"a structure's limit is a positive price a share in whole cents, not {intent.limit_price}")
        if intent.quantity != intent.quantity.to_integral_value() or intent.quantity < 1:
            raise RejectedOrder(f"a structure order is for whole structures, not {intent.quantity}")
        if intent.time_in_force != "day":
            raise RejectedOrder(f"a structure order is a day order, not {intent.time_in_force}")
        session = _expiry_session(spec.expiry)
        if session is not None and instant(session.close_at) <= instant(now):
            raise RejectedOrder(f"{spec.code} has expired: its first leg's session ({session.date}) has closed")
        if not market_open_at(now):
            raise RejectedOrder("the options market is closed: structures trade in the regular US session of a trading day only")
        return spec

    def submit(self, intent: OrderIntent) -> Order:
        with self._lock:
            order = Order.from_intent(intent, venue=self.venue)
            stored = self._orders.get(order.id)
            if stored is not None:
                return self._copy(stored)
            now = self._now()
            spec = self._validate(intent, now)
            # Rule 2's floor: the later of the submission time and the quote read fresh now. The decision may
            # have seen a quote newer than anything this account had cached (the House's chain is its own
            # read), so only a quote of every leg made after the order was accepted can fill it.
            try:
                in_hand = self._oldest(spec, self._read_legs([leg.occ for leg in spec.legs], fresh=True))
            except Exception:  # noqa: BLE001 - no quote in hand: the submission time is the floor
                in_hand = None
            if in_hand is None or not _newer(in_hand, stamp(now)):
                in_hand = stamp(now)
            session = us_equity_session(instant(now))  # New York's day: a datetime, never the UTC date of a string
            order.broker_order_id = f"{self.venue}-{self._next_order}"
            self._next_order += 1
            order.submitted_at = order.updated_at = now
            order._raw = {"quote_floor": in_hand, "session_close": session.close_at if session else now,
                          "post_only": bool(intent.post_only)}
            self._orders[order.id] = order
            self._by_broker_id[order.broker_order_id] = order.id
            refusal = self._refusal(order, spec, order.quantity, order.limit_price)
            if refusal:
                self._close(order, "rejected", refusal, now)
            else:
                order.status = "accepted"
            self._commit()
            return self._copy(order)

    def _find(self, order_id: str) -> Order:
        order = self._orders.get(order_id) or self._orders.get(self._by_broker_id.get(order_id, ""))
        if order is None:
            raise RejectedOrder(f"{self.venue} has no order {order_id}")
        return order

    def get_order(self, order_id: str) -> Order:
        with self._lock:
            return self._copy(self._find(order_id))

    def cancel(self, order_id: str) -> Order:
        with self._lock:
            order = self._find(order_id)
            if not order.terminal:
                self._close(order, "cancelled", "cancelled by request", self._now())
                self._commit()
            return self._copy(order)

    def open_orders(self) -> list[Order]:
        with self._lock:
            return [self._copy(order) for order in self._orders.values() if not order.terminal]

    def fills(self, since: str | None = None) -> list[Fill]:
        floor = _cursor(since)
        with self._lock:
            return [fill for fill in self._fills if _at_or_after(fill.at, floor)]

    # ---------------------------------------------------------------- advance
    def _room(self, spec: structures.Spec, side: str, rows: Mapping[str, Mapping[str, Any]]) -> Decimal:
        """Rule 4: how many structures the legs' shown sizes let through now (10% of each leg's size on
        the side it trades, less what this quote has already given, divided by the leg's ratio)."""
        room: Decimal | None = None
        for leg in spec.legs:
            takes_ask = (leg.sign > 0) == (side == "buy")
            row = rows.get(leg.occ) or {}
            size = _number(row.get("ask_size" if takes_ask else "bid_size"))
            if size is None or size <= 0:
                return ZERO
            seen, used = self._used.get((leg.occ, "ask" if takes_ask else "bid"), (None, ZERO))
            used = used if seen == row.get("as_of") else ZERO
            contracts = (size / TEN).to_integral_value(rounding=ROUND_FLOOR) - used
            units = (contracts / leg.ratio).to_integral_value(rounding=ROUND_FLOOR)
            room = units if room is None else min(room, units)
        return max(ZERO, room or ZERO)

    def _prune_used(self, now: str) -> None:
        """Rule 4's shares of quotes older than a day can never be met again: they leave the file."""
        cutoff = instant(now) - timedelta(days=1)
        self._used = {key: row for key, row in self._used.items() if row[0] and instant(row[0]) is not None and instant(row[0]) > cutoff}

    def _take(self, spec: structures.Spec, side: str, rows: Mapping[str, Mapping[str, Any]], units: Decimal) -> None:
        for leg in spec.legs:
            takes_ask = (leg.sign > 0) == (side == "buy")
            key = (leg.occ, "ask" if takes_ask else "bid")
            as_of = (rows.get(leg.occ) or {}).get("as_of")
            seen, used = self._used.get(key, (None, ZERO))
            self._used[key] = (as_of, (used if seen == as_of else ZERO) + units * leg.ratio)

    def advance(self) -> int:
        """Expire day orders past their session's close, then re-quote every leg of every resting
        order in one read and fill by rules 2-4 and 6. Returns how many orders changed. A source that
        cannot be read changes nothing: the orders wait for the next call."""
        with self._lock:
            resting = [order for order in self._orders.values() if order.status in OPEN_STATUSES]
            if not resting:
                return 0
            now = self._now()
            changed = 0
            live = []
            for order in resting:
                close = order._raw.get("session_close")
                if close and instant(close) is not None and instant(close) <= instant(now):
                    self._close(order, "expired", "a day order: what had not filled was expired at the close", now)
                    changed += 1
                else:
                    live.append(order)
            rows: dict[str, dict[str, Any]] | None = None
            if live and market_open_at(now):
                specs = {order.id: structures.spec_of(order.instrument) for order in live}
                try:
                    rows = self._read_legs({leg.occ for spec in specs.values() for leg in spec.legs}, fresh=True)
                except Exception:  # noqa: BLE001 - no quote decides no fill
                    rows = None
            for order in live if rows is not None else ():
                spec = specs[order.id]
                touches = self._touches(spec, rows)
                if any(bid is None or ask is None or bid > ask for bid, ask in touches.values()):
                    continue  # every leg two-sided (rule 3)
                as_of = self._oldest(spec, rows)
                if not _newer(as_of, order._raw.get("quote_floor")):
                    continue  # nothing fills in the quote the decision saw, nor twice in one quote (rule 2)
                bid, ask = structures.quote(spec, touches)
                if order.side == "buy":
                    price = ask if ask is not None and ZERO < ask <= order.limit_price else None
                else:
                    price = bid if bid is not None and ZERO < bid and bid >= order.limit_price else None
                if price is None:
                    continue
                units = min(order.remaining, self._room(spec, order.side, rows))
                if units < 1:
                    continue
                refusal = self._refusal(order, spec, units, price)
                if refusal:  # holds make this unreachable for a buy; an account that cannot pay still never fills
                    self._close(order, "cancelled", refusal, now)
                else:
                    self._fill(order, spec, units, price, now)
                    self._take(spec, order.side, rows, units)
                    order._raw["quote_floor"] = as_of  # the rest waits for a newer quote
                changed += 1
            if changed:
                self._prune_used(now)
                self._commit()  # rule 4's shares are in the file too: a failed write takes them back with the fill
            return changed

    # ---------------------------------------------------------------- expiry
    def _close_of(self, symbol: str, day: str) -> Decimal | None:
        key = (symbol.upper(), day)
        if key in self._closes:
            return self._closes[key]
        if self.underlying_close is None or float(self.clock()) - self._close_tried.get(key, float("-inf")) < CLOSE_RETRY_SECONDS:
            return None
        self._close_tried[key] = float(self.clock())
        try:
            spot = _number(self.underlying_close(symbol.upper(), day))
        except Exception:  # noqa: BLE001 - not knowing the close settles nothing yet
            spot = None
        if spot is None or spot <= 0:
            return None
        self._closes[key] = spot
        return spot

    def _settle_value(self, spec: structures.Spec, spot: Decimal) -> Decimal | None:
        """The held price S a share once the earliest expiry has closed (the module docstring)."""
        if spec.type not in structures.TWO_EXPIRIES:
            value = structures.intrinsic(spec, spot)
        else:
            far = [leg for leg in spec.legs if leg.expiry != spec.expiry]
            try:
                rows = self._read_legs([leg.occ for leg in far], fresh=True)
            except Exception:  # noqa: BLE001 - a far leg that cannot be read now is read again next time
                return None
            if any(not rows.get(leg.occ) for leg in far):
                return None  # the source has no quote for it: never valued at zero for want of a read
            value = spec.collateral
            for leg in spec.legs:
                if leg.expiry == spec.expiry:
                    worth = max(ZERO, spot - leg.strike) if leg.right == "call" else max(ZERO, leg.strike - spot)
                else:
                    bid, ask = self._touches(spec, rows)[leg.occ]
                    # What closing it would get: a long far leg sells at its bid (nothing when the venue shows it
                    # with no bid); a short far leg (none is admitted) would buy back at its ask.
                    worth = (bid or ZERO) if leg.sign > 0 else ask
                    if worth is None:
                        return None
                value += leg.sign * leg.ratio * worth
        return max(ZERO, value).quantize(SETTLE_PLACES, rounding=ROUND_FLOOR)

    def structure_settlements(self, codes: Iterable[str] | None = None) -> dict[str, Decimal]:
        """Settle the held structures named by `codes` (every held one when None) whose earliest expiry
        is past by New York's calendar and whose session has closed (the module docstring), once, and
        return the value a share of EVERY structure this account has settled, by its code
        (`market_id`), so a caller that crashed between this call and its own bookkeeping reads the
        same value again. `Book.expire_options` calls it with the structures it is settling: its own
        rule (an expiry before New York's today) is this one, so the two never disagree about what
        is still held."""
        wanted = None if codes is None else {str(code) for code in codes}
        with self._lock:
            now = self._now()
            today = instant(now).astimezone(NEW_YORK).strftime("%Y-%m-%d")
            applied = False
            for code, held in list(self._positions.items()):
                if wanted is not None and code not in wanted:
                    continue
                spec = structures.spec_of(held["instrument"])
                session = _expiry_session(spec.expiry)
                if spec.expiry >= today or session is None or instant(session.close_at) > instant(now):
                    continue
                spot = self._close_of(spec.underlying, session.date)
                if spot is None:
                    continue
                price = self._settle_value(spec, spot)
                if price is None:
                    continue
                inst, quantity = held["instrument"], held["quantity"]
                value = price * inst.multiplier * quantity
                self._cash += value
                del self._positions[code]
                for order in self._orders.values():
                    if order.status in OPEN_STATUSES and order.instrument.market_id == code:
                        self._close(order, "expired", f"the structure expired and was settled at {price} a share", now)
                self._settlements.append({"code": code, "instrument": inst, "quantity": quantity, "price": price, "spot": spot,
                                          "cost": held["cost"], "value": value, "session": session.date, "settled_time": now})
                applied = True
            if applied:
                self._commit()
            return {row["code"]: row["price"] for row in self._settlements}

    def settled(self) -> list[dict[str, Any]]:
        """Every settlement applied, oldest first (for the record; `structure_settlements` applies them)."""
        with self._lock:
            return [dict(row) for row in self._settlements]


__all__ = ["OptionsShadowBroker", "CAPABILITIES", "VENUE", "alpaca_leg_quotes", "alpaca_underlying_close", "stamp"]
