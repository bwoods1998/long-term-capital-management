"""Rung 0: the mechanical replay simulator.

A strategy file (see `league/CONTRACT.md`) is walked over a recorded tape one step at a time. At
step i the simulator first fills the orders that were already resting and settles what closed,
using step i's data only; then it marks the account, builds `ctx` from data at or before step i,
calls `decide`, and applies what came back. The strategy is never handed the tape, a later step or
a recorded result, so it cannot look ahead; an order it places at step i can rest-fill no earlier
than step i + 1. The strategy file is run from the top in a fresh namespace for every step, as a
live wake runs it: module-level globals do not persist, only `memory` does.

Fills are conservative:

- a market order, or a limit order that crosses, fills at the touch of the same step as a taker
  (a crossing `post_only` order is refused);
- a resting limit order fills at its own price, as a maker, only when a later step's range trades
  strictly through it (`low < price` for a buy, `high > price` for a sell). Touching is not enough:
  the tape knows nothing of the queue ahead of the order or the depth behind the touch;
- the touch is the tape's own quote where it carries one (`step["quotes"]`: the NBBO prevailing
  when an order decided at the step's close reaches the venue, `league.history` probes), and the
  close plus or minus `half_spread_bps` where it does not. A quote older than
  `STALE_QUOTE_SECONDS` says where the market WAS: the touch is then centred on the close and no
  narrower than twice the assumed spread. `spread_stress` (2.0 for the double-spread variant)
  widens every touch about its middle. A tape with quotes or stress reports how each step was
  priced in `execution`;
- all or nothing: the tape carries no sizes, so an order fills whole or not at all, and the rung's
  order cap is what keeps that honest;
- Alpaca crypto pays 0.25% as a taker and 0.15% as a maker, equities nothing. The live venue takes
  a crypto buy's fee out of the coins received; here every fee is charged in dollars. The
  economics are the same and the quantities stay round;
- Kalshi pays `0.07 x contracts x price x (1 - price)` rounded up to $0.0001 as a taker and nothing
  as a maker. A held contract pays $1 or $0 at the first step at or after its close, on the tape's
  recorded result; a market with no recorded result refunds the price paid (fees stay paid).

This file is self-contained on purpose: standard library plus `safety.py`. It is uploaded as it is
into the agent's box and run there as `python3 replay.py --spec spec.json`; the House reads the last
`REPLAY-RESULT <token> <json>` line and nothing else (`parse_result`). Floats are fine here: this
is statistics, not the money ledger.
"""

from __future__ import annotations

import argparse
import bisect
import builtins
import contextlib
import copy
import hashlib
import io
import json
import math
import os
import random
import signal
import sys
import threading
import time
from datetime import datetime, timezone
from decimal import ROUND_CEILING, ROUND_DOWN, Decimal, InvalidOperation
from typing import Any

try:
    from league.safety import CodeRefused, check_code
except ImportError:  # in the agent's box the two files sit side by side
    from safety import CodeRefused, check_code

RESULT_PREFIX = "REPLAY-RESULT"

CRYPTO_TAKER = 0.0025
CRYPTO_MAKER = 0.0015
KALSHI_TAKER_RATE = 0.07
FEES = {"crypto_taker": CRYPTO_TAKER, "crypto_maker": CRYPTO_MAKER, "kalshi_taker_rate": KALSHI_TAKER_RATE}
DEFAULT_LIMITS = {"max_position_usd": 100.0, "max_order_usd": 75.0}

MIN_EVENT_PRICE = 0.15  # the House's firm rule: no opening Kalshi buy under 15 cents
#: Alpaca refuses a crypto order under $10 (55 paper orders in 48 hours to Sept 22, 2026), and the
#: House refuses a crypto buy asked under it (`league/venues.py`), so none fills here either. As in
#: the House it is the dollars ASKED that are held to it: one asked at $10 and floored a hair under
#: by the step is raised one step there and fills here at the floored size. Sells are not held to it.
ALPACA_CRYPTO_MIN_ORDER_USD = 10.0
MAX_INTENTS = 8
MAX_CANCELS = 20
MAX_ERRORS = 20
MAX_MEMORY_BYTES = 8 * 1024
DEFAULT_BARS = 120
MAX_BARS = 500
DEFAULT_HALF_SPREAD_BPS = 2.0
#: A quote older than this at the moment it is used is stale (Sept 22, 2026: SPY's touch changes
#: many times a second in the session; a quote ten seconds old is from another market).
STALE_QUOTE_SECONDS = 10.0
RUIN_LOG_GROWTH = -13.8  # ln(1e-6): the block in which the account is wiped out, and the floor for any block
RUIN_EQUITY = 1e-9  # equity at or under this is zero (float dust after spending the last cent)
EPS = 1e-9

_FINE_STEP = Decimal("0.000000001")
_WHOLE_STEP = Decimal(1)
_FEE_GRID = Decimal("0.0001")
_SCALARS = (str, int, float, bool, type(None))
_MARKET_FIELDS = ("market", "series", "title", "yes_bid", "yes_ask", "close_time", "hours_to_resolve", "volume_24h", "open_interest", "strike")


# ------------------------------------------------------------------------------------ helpers
class _DecideTimeout(BaseException):
    """Raised inside a strategy call that outlives its deadline. Not an `Exception`, so an
    ordinary `except Exception` in the strategy does not swallow it."""


class _Null(io.TextIOBase):
    """Where a strategy's prints go: nowhere, and without holding them in memory."""

    def writable(self) -> bool:
        return True

    def write(self, text: str) -> int:  # type: ignore[override]
        return len(text)


def _num(value: Any) -> float | None:
    """A finite number as a float; None for anything else (a bool is not a number here)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _parse_ts(value: Any) -> float | None:
    """ISO-8601 to epoch seconds. A time without an offset is UTC."""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text[-1] in "Zz":
        text = text[:-1] + "+00:00"
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.timestamp()


def _bars_until(bars: Any, now_ts: float | None) -> list[dict[str, Any]]:
    """The recorded bars stamped at or before this step. A tape carries the whole window in one
    piece -- far smaller than a copy per step -- and each step sees only its own past."""
    if not isinstance(bars, (list, tuple)) or now_ts is None:
        return []
    out = []
    for bar in bars:
        if not isinstance(bar, dict):
            continue
        stamp = _parse_ts(bar.get("t"))
        if stamp is None:
            continue
        if stamp > now_ts:
            break  # the tape is in order: everything after this is the strategy's future
        out.append(bar)
    return out


def _feed_index(feeds: Any) -> dict[str, dict[str, tuple[list[float], list[dict[str, Any]]]]]:
    """A tape's recorded live feeds (`league/feeds.py`: {feed: {key: [row, ...]}}, each row stamped
    `t` with when the House received it) as (stamps, rows) in time order, read once a replay. A row
    without a readable `t` cannot be placed in time, so it is never shown."""
    out: dict[str, dict[str, tuple[list[float], list[dict[str, Any]]]]] = {}
    if not isinstance(feeds, dict):
        return out
    for feed, keys in feeds.items():
        if not isinstance(feed, str) or not isinstance(keys, dict):
            continue
        for key, rows in keys.items():
            if not isinstance(key, str) or not isinstance(rows, list):
                continue
            stamped = sorted(((stamp, row) for row in rows if isinstance(row, dict)
                              for stamp in (_parse_ts(row.get("t")),) if stamp is not None), key=lambda pair: pair[0])
            out.setdefault(feed, {})[key] = ([stamp for stamp, _ in stamped], [row for _, row in stamped])
    return out


def _feeds_until(index: dict, now_ts: float) -> dict[str, dict[str, Any]]:
    """The row of each feed key received last at or before this step -- `_bars_until`'s rule, found
    by bisection because a feed tape has up to a row a step -- copied, so a strategy that edits what
    it is shown cannot edit a later step's view. A key with nothing received yet is absent."""
    out: dict[str, dict[str, Any]] = {}
    for feed, keys in index.items():
        out[feed] = {}
        for key, (stamps, rows) in keys.items():
            found = bisect.bisect_right(stamps, now_ts)
            if found:
                out[feed][key] = copy.deepcopy(rows[found - 1])
        if not out[feed]:
            del out[feed]
    return out


def _block_key(ts: float, horizon: str) -> str:
    """`t[:13]` for an hour block and `t[:10]` for a day block, taken in UTC."""
    moment = datetime.fromtimestamp(ts, timezone.utc)
    return moment.strftime("%Y-%m-%dT%H" if horizon == "hour" else "%Y-%m-%d")


def _floor_to_step(quantity: float, whole: bool) -> float:
    """Round a quantity DOWN to the instrument's step. A hair of relative slack keeps a float
    quotient such as 46.5 / 0.93 from landing on 49.999999 and losing a whole contract."""
    try:
        exact = Decimal(repr(float(quantity) * (1.0 + 1e-12)))
        return float(exact.quantize(_WHOLE_STEP if whole else _FINE_STEP, rounding=ROUND_DOWN))
    except (InvalidOperation, ValueError, OverflowError):
        return 0.0


def _price6(value: Any) -> float | None:
    """A Kalshi price strictly inside (0, 1), on a clean six-decimal grid; None otherwise."""
    number = _num(value)
    if number is None:
        return None
    number = round(number, 6)
    return number if 0.0 < number < 1.0 else None


def _complement(price: float | None) -> float | None:
    """A YES price seen from the NO leg (NO ask = 1 - YES bid), kept on the six-decimal grid."""
    return None if price is None else round(1.0 - price, 6)


def _short(text: Any, limit: int = 200) -> str:
    try:
        return str(text)[:limit]
    except BaseException:  # noqa: BLE001 - a hostile __str__ is not worth a crash
        return "unprintable"


def is_equity(symbol: str) -> bool:
    """On Alpaca anything without a slash is an equity; `BTC/USD` is crypto."""
    return "/" not in symbol


def kalshi_taker_fee(contracts: float, price: float) -> float:
    """0.07 x C x P x (1 - P), rounded UP to $0.0001, computed exactly."""
    p = Decimal(str(round(float(price), 6)))
    c = Decimal(str(round(float(contracts), 9)))
    return float((Decimal("0.07") * c * p * (1 - p)).quantize(_FEE_GRID, rounding=ROUND_CEILING))


def kalshi_maker_fee(contracts: float, price: float) -> float:
    """What a RESTING fill pays on the series that charge makers (the winner, spread and total
    markets of the big leagues, among others): 0.0175 x C x P x (1 - P), rounded UP to $0.0001.
    Every other series charges a maker nothing."""
    p = Decimal(str(round(float(price), 6)))
    c = Decimal(str(round(float(contracts), 9)))
    return float((Decimal("0.0175") * c * p * (1 - p)).quantize(_FEE_GRID, rounding=ROUND_CEILING))


class _Deadline:
    """Calls strategy code with a wall-clock limit. On a Unix main thread a timer interrupts a
    call that runs over; everywhere else the call is timed and an overrun is counted after the
    fact. (A strategy that swallows the interrupt in a bare `except` inside an endless loop is
    left to the box's own time limit.)"""

    def __init__(self, seconds: float):
        self.seconds = max(0.001, float(seconds))
        self.armed = False
        self._old: Any = None

    def __enter__(self) -> "_Deadline":
        try:
            if hasattr(signal, "setitimer") and threading.current_thread() is threading.main_thread():
                self._old = signal.signal(signal.SIGALRM, self._fire)
                self.armed = True
        except (ValueError, OSError, AttributeError):
            self.armed = False
        return self

    def __exit__(self, *exc: Any) -> None:
        if self.armed:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, self._old if self._old is not None else signal.SIG_DFL)
            self.armed = False

    @staticmethod
    def _fire(signum: int, frame: Any) -> None:
        raise _DecideTimeout()

    def call(self, fn: Any, *args: Any) -> tuple[Any, str | None]:
        """`(value, None)`, or `(None, why)` when the call raised or ran over."""
        started = time.monotonic()
        try:
            try:
                if self.armed:
                    signal.setitimer(signal.ITIMER_REAL, self.seconds)
                value = fn(*args)
            finally:
                if self.armed:
                    signal.setitimer(signal.ITIMER_REAL, 0)
        except _DecideTimeout:
            return None, f"took longer than {self.seconds:g}s"
        except KeyboardInterrupt:
            raise
        except BaseException as exc:  # noqa: BLE001 - SystemExit and friends are strategy errors too
            return None, f"{type(exc).__name__}: {_short(exc, 160)}"
        if time.monotonic() - started > self.seconds:
            return None, f"took longer than {self.seconds:g}s"
        return value, None


# ------------------------------------------------------------------------------- one step's data
class _View:
    """What one step of the tape says, keyed the way the account keys its instruments:
    an Alpaca symbol, or `<market>|<leg>` on Kalshi."""

    def __init__(self) -> None:
        self.quotes: dict[str, tuple[float | None, float | None]] = {}  # key -> (bid, ask)
        self.ranges: dict[str, tuple[float | None, float | None]] = {}  # key -> (lowest ask, highest bid)
        self.marks: dict[str, float] = {}  # key -> liquidation value of one unit
        self.bars: dict[str, dict[str, Any]] = {}  # alpaca: symbol -> the bar that closed now
        self.markets: dict[str, dict[str, Any]] = {}  # kalshi: ticker -> cleaned market row
        self.quote_age: dict[str, float] = {}  # alpaca: seconds a recorded quote is older than now


def _touch(close: float, quote: Any, half_spread: float, stress: float) -> tuple[float, float, str]:
    """(bid, ask, how) a taker meets at this step: `quoted`, `stale` or `assumed` (see above)."""
    assumed = (close * (1.0 - half_spread * stress), close * (1.0 + half_spread * stress), "assumed")
    if not isinstance(quote, dict):
        return assumed
    bid, ask, age = _num(quote.get("bid")), _num(quote.get("ask")), _num(quote.get("age"))
    if bid is None or ask is None or not 0.0 < bid <= ask:
        return assumed
    if age is None or age < 0 or age > STALE_QUOTE_SECONDS:
        half = max((ask - bid) / 2.0, close * half_spread * 2.0) * stress
        return close - half, close + half, "stale"
    middle, half = (bid + ask) / 2.0, (ask - bid) / 2.0 * stress
    return middle - half, middle + half, "quoted"


def _alpaca_view(step: dict, half_spread: float, stress: float = 1.0, priced: "dict[str, int] | None" = None) -> _View:
    view = _View()
    bars = step.get("execution_bars", step.get("bars"))
    if not isinstance(bars, dict):
        return view
    quotes = step.get("quotes") if isinstance(step.get("quotes"), dict) else {}
    for symbol, bar in bars.items():
        if not isinstance(symbol, str) or not isinstance(bar, dict):
            continue
        close = _num(bar.get("c"))
        if close is None or close <= 0:
            continue
        open_ = _num(bar.get("o"))
        high = _num(bar.get("h"))
        low = _num(bar.get("l"))
        volume = _num(bar.get("v"))
        open_ = close if open_ is None or open_ <= 0 else open_
        high = max(close, high) if high is not None else close
        low = min(close, low) if low is not None and low > 0 else close
        bid, ask, how = _touch(close, quotes.get(symbol), half_spread, stress)
        if priced is not None:
            priced[how] = priced.get(how, 0) + 1
        age = _num((quotes.get(symbol) or {}).get("age")) if how != "assumed" else None
        if age is not None and age > 0:
            view.quote_age[symbol] = age
        view.bars[symbol] = {"t": step["t"], "o": open_, "h": high, "l": low, "c": close, "v": volume or 0.0}
        view.quotes[symbol] = (bid, ask)
        view.ranges[symbol] = (low, high)  # trades: a buy needs a print under it, a sell one over it
        view.marks[symbol] = bid
    if "execution_bars" in step:
        view.bars = {}  # signal history is appended separately, with its actual availability time
    return view


def _kalshi_view(step: dict) -> _View:
    view = _View()
    rows = step.get("markets")
    if not isinstance(rows, list):
        return view
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("market"), str) or not row["market"]:
            continue
        ticker = row["market"]
        yes_bid, yes_ask = _price6(row.get("yes_bid")), _price6(row.get("yes_ask"))
        ask_low, bid_high = _price6(row.get("yes_ask_low")), _price6(row.get("yes_bid_high"))
        ask_low = yes_ask if ask_low is None else (ask_low if yes_ask is None else min(ask_low, yes_ask))
        bid_high = yes_bid if bid_high is None else (bid_high if yes_bid is None else max(bid_high, yes_bid))
        clean = {field: row.get(field) for field in _MARKET_FIELDS if field in row}
        clean["close_ts"] = _parse_ts(row.get("close_time"))
        view.markets[ticker] = clean
        flip = _complement
        view.quotes[f"{ticker}|yes"] = (yes_bid, yes_ask)
        view.quotes[f"{ticker}|no"] = (flip(yes_ask), flip(yes_bid))  # NO bid = 1 - YES ask
        view.ranges[f"{ticker}|yes"] = (ask_low, bid_high)
        view.ranges[f"{ticker}|no"] = (flip(bid_high), flip(ask_low))
        if yes_bid is not None:
            view.marks[f"{ticker}|yes"] = yes_bid
        if yes_ask is not None:
            view.marks[f"{ticker}|no"] = flip(yes_ask)
    return view


# ------------------------------------------------------------------------------------ the account
class _Account:
    """One agent's simulated account on one venue: cash, holdings, resting orders and the tally."""

    def __init__(self, venue: str, stake: float, limits: dict[str, float], results: dict[str, str], record_fills: bool,
                 maker_fee_series: Any = (), settlements: dict | None = None):
        self.venue = venue
        self.maker_fee_series = {str(x).upper() for x in (maker_fee_series or ())}
        self.stake = stake
        self.cash = stake
        self.limits = limits
        self.results = results
        self.settlements = settlements
        self.positions: dict[str, dict[str, Any]] = {}
        self.orders: dict[str, dict[str, Any]] = {}
        self.order_seq = 0
        self.fills = 0
        self.maker_fills = 0
        self.fees_usd = 0.0
        self.refused = 0
        self.refusal_reasons: dict[str, int] = {}
        self.unresolved = 0
        self.expired_orders = 0
        self.trade_returns: list[float] = []
        self.trade_log: list[dict[str, Any]] = []  # one row a closed trade, for `digest`
        #: (symbols, series) the strategy may trade; None means "anything on the tape". What it
        #: only WATCHES is refused, as the House's book refuses anything outside its specialty.
        self.tradeable: tuple[set[str] | None, set[str] | None] = (None, None)
        self.fill_log: list[dict[str, Any]] | None = [] if record_fills else None

    # -- money -------------------------------------------------------------------------------
    def fee(self, key: str, quantity: float, price: float, liquidity: str) -> float:
        if self.venue == "kalshi":
            if liquidity == "maker":
                return kalshi_maker_fee(quantity, price) if str(key).split("-", 1)[0].upper() in self.maker_fee_series else 0.0
            return kalshi_taker_fee(quantity, price)
        if is_equity(key):
            return 0.0
        return quantity * price * (CRYPTO_MAKER if liquidity == "maker" else CRYPTO_TAKER)

    def equity(self) -> float:
        return self.cash + sum(p["quantity"] * p["mark"] for p in self.positions.values())

    def mark(self, view: _View) -> float:
        """Holdings at their bid; an instrument the step does not show keeps its last mark."""
        for key, position in self.positions.items():
            if key in view.marks:
                position["mark"] = view.marks[key]
        return self.equity()

    def reserved_cash(self) -> float:
        return sum(
            o["quantity"] * o["limit_price"] + self.fee(o["key"], o["quantity"], o["limit_price"], "maker")
            for o in self.orders.values() if o["side"] == "buy"
        )

    def _resting(self, key: str, side: str) -> list[dict[str, Any]]:
        return [o for o in self.orders.values() if o["key"] == key and o["side"] == side]

    def _closed(self, position: dict[str, Any], how: str, now: str) -> None:
        if len(self.trade_log) < 2000:
            name = str(position.get("market") or position.get("symbol") or position.get("key"))
            self.trade_log.append({"name": name, "group": name.split("-", 1)[0] if position.get("market") else name, "leg": position.get("leg"),
                                   "pnl": position["pnl"], "entry": position.get("entry"), "opened_at": position.get("opened_at"),
                                   "closed_at": now, "close_time": position.get("close_time"), "how": how})

    # -- fills -------------------------------------------------------------------------------
    def _fill(self, ident: dict[str, Any], key: str, side: str, quantity: float, price: float,
              liquidity: str, now: str, reason: str, close: tuple[float | None, Any]) -> None:
        fee = self.fee(key, quantity, price, liquidity)
        notional = quantity * price
        position = self.positions.get(key)
        if side == "buy":
            self.cash -= notional + fee
            if position is None:
                position = self.positions[key] = {
                    **ident, "key": key, "quantity": 0.0, "cost": 0.0, "pnl": 0.0, "mark": price,
                    "opened_at": now, "reason": reason, "close_ts": close[0], "close_time": close[1], "entry": price,
                }
            position["quantity"] = round(position["quantity"] + quantity, 9)
            position["cost"] += notional
            position["pnl"] -= fee
        else:
            assert position is not None  # the no-shorts check ran before any sell reaches here
            average = position["cost"] / position["quantity"]
            self.cash += notional - fee
            position["pnl"] += quantity * (price - average) - fee
            position["quantity"] = round(position["quantity"] - quantity, 9)
            position["cost"] = average * position["quantity"]
            if position["quantity"] <= 0:
                self.trade_returns.append(position["pnl"] / self.stake)
                self._closed(position, "sold", now)
                del self.positions[key]
        self.fills += 1
        self.maker_fills += 1 if liquidity == "maker" else 0
        self.fees_usd += fee
        if self.fill_log is not None:
            self.fill_log.append({"t": now, **ident, "side": side, "quantity": quantity, "price": price,
                                  "fee": fee, "liquidity": liquidity})

    def work_resting(self, view: _View, now: str, now_ts: float) -> None:
        """Step (a): orders placed at an earlier step meet this step's range (a closing step's
        range counts if the tape still shows the market: the last minutes are where a resting
        bid is picked off). Then an order still resting in a closed market dies, and closed
        holdings settle."""
        for order_id in list(self.orders):
            order = self.orders[order_id]
            ask_low, bid_high = view.ranges.get(order["key"], (None, None))
            price = order["limit_price"]
            through = (ask_low is not None and ask_low < price) if order["side"] == "buy" else (
                bid_high is not None and bid_high > price)
            if through:
                del self.orders[order_id]
                self._fill(order["ident"], order["key"], order["side"], order["quantity"], price, "maker",
                           now, order["reason"], (order["close_ts"], order["close_time"]))
        for order_id in list(self.orders):
            close_ts = self.orders[order_id]["close_ts"]
            if close_ts is not None and now_ts >= close_ts:
                del self.orders[order_id]
                self.expired_orders += 1
        for key in list(self.positions):
            position = self.positions[key]
            if position["close_ts"] is None or now_ts < position["close_ts"]:
                continue
            if self.settlements is not None:
                settled = _parse_ts(self.settlements.get(position["market"]))
                if settled is None or now_ts < settled:
                    continue  # trading stopped, but the cash is still locked
            result = str(self.results.get(position["market"]) or "").strip().lower()
            if result in ("yes", "no"):
                payout = position["quantity"] if position["leg"] == result else 0.0
                self.cash += payout
                position["pnl"] += payout - position["cost"]
                self.trade_returns.append(position["pnl"] / self.stake)
                self._closed(position, "won" if payout > 0 else "lost", now)
            elif self.settlements is not None:
                continue  # unknown outcome is neither a cash refund nor a win
            else:  # legacy tapes: archived evaluators retain their old contract
                self.cash += position["cost"]
                self.unresolved += 1
            del self.positions[key]

    def refresh_closes(self, view: _View) -> None:
        """A held or working market's close time is whatever the tape last said it was."""
        for item in list(self.positions.values()) + list(self.orders.values()):
            market = view.markets.get(item.get("market") or item.get("ident", {}).get("market"))
            if market and market.get("close_ts") is not None:
                item["close_ts"], item["close_time"] = market["close_ts"], market.get("close_time")

    # -- intents -----------------------------------------------------------------------------
    def refuse(self, why: str) -> None:
        self.refused += 1
        self.refusal_reasons[why] = self.refusal_reasons.get(why, 0) + 1

    def cancel(self, order_id: Any) -> None:
        if isinstance(order_id, str) and order_id in self.orders:
            del self.orders[order_id]
        else:
            self.refuse("cancel: no such open order")

    def submit(self, intent: Any, view: _View, now: str, now_ts: float) -> None:
        """Apply one intent the way the House's book would: refuse it with a reason, fill it at
        the touch, or rest it."""
        if not isinstance(intent, dict):
            return self.refuse("malformed: an intent is a dict")
        side, order_type = intent.get("side"), intent.get("type")
        if side not in ("buy", "sell"):
            return self.refuse("malformed: side is buy or sell")
        if order_type not in ("market", "limit"):
            return self.refuse("malformed: type is market or limit")
        if not isinstance(intent.get("reason"), str) or not intent["reason"].strip():
            return self.refuse("malformed: every intent needs a reason")
        close: tuple[float | None, Any] = (None, None)
        if self.venue == "kalshi":
            ticker, leg = intent.get("market"), intent.get("leg", "yes")
            if not isinstance(ticker, str) or leg not in ("yes", "no"):
                return self.refuse("malformed: a kalshi intent names a market and a yes or no leg")
            allowed = self.tradeable[1]
            if allowed is not None and str(ticker).split("-", 1)[0] not in allowed and market_series(view, ticker) not in allowed:
                return self.refuse("this market is one you watch, not one you trade")
            market = view.markets.get(ticker)
            if market is None:
                return self.refuse("no quote for this market at this step")
            if market["close_ts"] is not None and market["close_ts"] <= now_ts:
                return self.refuse("the market has closed")
            ident, key = {"market": ticker, "leg": leg}, f"{ticker}|{leg}"
            close = (market["close_ts"], market.get("close_time"))
        else:
            symbol = intent.get("symbol")
            if not isinstance(symbol, str) or not symbol:
                return self.refuse("malformed: an alpaca intent names a symbol")
            if self.tradeable[0] is not None and symbol not in self.tradeable[0]:
                return self.refuse("this symbol is one you watch, not one you trade")
            ident, key = {"symbol": symbol}, symbol
        has_quantity, has_notional = intent.get("quantity") is not None, intent.get("notional_usd") is not None
        if has_quantity == has_notional:
            return self.refuse("malformed: give quantity or notional_usd, one of them")
        amount = _num(intent["quantity"] if has_quantity else intent["notional_usd"])
        if amount is None or amount <= 0:
            return self.refuse("malformed: the size is a positive number")
        bid, ask = view.quotes.get(key, (None, None))
        touch = ask if side == "buy" else bid
        if touch is not None and touch <= 0:
            touch = None
        # With nothing on the far side there is no touch to take or to convert dollars at. Only a
        # limit order sized in units can still go in (it rests); a symbol with no bar gets nothing.
        if touch is None and (key not in view.quotes or order_type != "limit" or not has_quantity):
            return self.refuse("no quote for this instrument at this step")
        whole = self.venue == "kalshi" or (is_equity(key) and order_type == "limit")
        quantity = _floor_to_step(amount if has_quantity else amount / touch, whole)
        if quantity <= 0:
            return self.refuse("the size rounds down to nothing at this instrument's step")
        post_only = bool(intent.get("post_only"))
        if order_type == "limit":
            limit_price = _num(intent.get("limit_price"))
            if limit_price is None or limit_price <= 0:
                return self.refuse("malformed: a limit order needs a positive limit_price")
            if self.venue == "kalshi":
                limit_price = round(limit_price, 6)
                if not 0.0 < limit_price < 1.0:
                    return self.refuse("malformed: a kalshi price is between 0 and 1")
            crosses = touch is not None and (limit_price >= touch if side == "buy" else limit_price <= touch)
            if crosses and post_only:
                return self.refuse("post_only order would cross the touch")
        else:
            limit_price, crosses = None, True
            if post_only:
                return self.refuse("post_only needs a limit order")
        price = touch if crosses else limit_price
        notional = quantity * price
        if side == "sell":
            held = self.positions.get(key, {}).get("quantity", 0.0)
            committed = sum(o["quantity"] for o in self._resting(key, "sell"))
            if quantity > held - committed + 1e-12:
                return self.refuse("no shorts: a sell is limited to what is held and not already offered")
        else:
            if self.venue == "kalshi" and price < MIN_EVENT_PRICE - EPS:
                return self.refuse("kalshi buys under $0.15 are refused")
            if (self.venue != "kalshi" and not is_equity(key)
                    and (amount if has_notional else amount * (price if limit_price is None else limit_price)) < ALPACA_CRYPTO_MIN_ORDER_USD - EPS):
                return self.refuse("alpaca refuses a crypto buy under $10")
            if notional > self.limits["max_order_usd"] + EPS:
                return self.refuse("over the order cap")
            held_value = self.positions.get(key, {}).get("quantity", 0.0) * price
            working = sum(o["quantity"] * o["limit_price"] for o in self._resting(key, "buy"))
            if held_value + working + notional > self.limits["max_position_usd"] + EPS:
                return self.refuse("over the position cap")
            fee = self.fee(key, quantity, price, "taker" if crosses else "maker")
            if notional + fee > self.cash - self.reserved_cash() + EPS:
                return self.refuse("no leverage: not enough free cash for the order and its fee")
        reason = intent["reason"].strip()[:500]
        if crosses:
            self._fill(ident, key, side, quantity, price, "taker", now, reason, close)
            if key in self.positions:
                self.positions[key]["mark"] = view.marks.get(key, self.positions[key]["mark"])
            return None
        self.order_seq += 1
        order_id = f"ord-{self.order_seq:06d}"
        self.orders[order_id] = {
            "order_id": order_id, "ident": ident, "key": key, "side": side, "quantity": quantity,
            "limit_price": limit_price, "submitted_at": now, "reason": reason,
            "close_ts": close[0], "close_time": close[1],
        }
        return None

    # -- what the strategy is shown ------------------------------------------------------------
    def positions_view(self) -> list[dict[str, Any]]:
        return [
            {**{k: p[k] for k in ("symbol", "market", "leg") if k in p}, "quantity": p["quantity"],
             "average_cost": p["cost"] / p["quantity"], "mark": p["mark"], "opened_at": p["opened_at"],
             "reason": p["reason"]}
            for p in self.positions.values()
        ]

    def orders_view(self) -> list[dict[str, Any]]:
        return [
            {"order_id": o["order_id"], **o["ident"], "side": o["side"], "quantity": o["quantity"],
             "limit_price": o["limit_price"], "filled": 0.0, "submitted_at": o["submitted_at"]}
            for o in self.orders.values()
        ]


# ---------------------------------------------------------------------------------------- replay
def _tape_problem(tape: Any) -> str | None:
    if not isinstance(tape, dict):
        return "the tape is not a dict"
    if tape.get("venue") not in ("alpaca", "kalshi"):
        return "the tape's venue is alpaca or kalshi"
    steps = tape.get("steps")
    if not isinstance(steps, list) or not steps:
        return "the tape has no steps"
    last = None

    def history_problem(series, cutoff, *, warmup=False):
        if not isinstance(series, dict):
            return 'history must map symbols to bar lists'
        for rows in series.values():
            if not isinstance(rows, list):
                return 'history bars must be a list'
            previous = None
            for bar in rows:
                stamp = _parse_ts(bar.get('t')) if isinstance(bar, dict) else None
                if stamp is None or stamp > cutoff or (warmup and stamp == cutoff) or (previous is not None and stamp <= previous):
                    return 'history contains future or unordered bars'
                previous = stamp
        return None

    for index, step in enumerate(steps):
        ts = _parse_ts(step.get("t")) if isinstance(step, dict) else None
        if ts is None:
            return f"step {index} has no ISO-8601 time"
        if last is not None and ts <= last:
            return f"step {index} is not later than the step before it"
        last = ts
        problem = history_problem(step.get('history_bars', {}), ts)
        if problem:
            return problem
    first = _parse_ts(steps[0]['t'])
    problem = history_problem(tape.get('warmup_bars', {}), first, warmup=True)
    if problem:
        return problem
    return None


def _clean_memory(value: Any) -> dict[str, Any]:
    """What `decide` returned as memory, as the next `decide` will see it: plain JSON, a dict,
    at most 8 KB. Anything else is dropped."""
    if not isinstance(value, dict):
        return {}
    try:
        text = json.dumps(value, allow_nan=False)
        if len(text.encode("utf-8")) > MAX_MEMORY_BYTES:
            return {}
        restored = json.loads(text)
    except (TypeError, ValueError, RecursionError):
        return {}
    return restored if isinstance(restored, dict) else {}


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _spread_of(tape: dict) -> tuple[float, float]:
    """(half spread as a fraction, spread stress) a tape declares, as every replay reads them."""
    half_spread_bps = _num(tape.get("half_spread_bps"))
    half_spread = (DEFAULT_HALF_SPREAD_BPS if half_spread_bps is None or half_spread_bps < 0 else half_spread_bps) / 10000.0
    stress = _num(tape.get("spread_stress"))
    stress = 1.0 if stress is None or stress < 1.0 else min(stress, 10.0)
    return half_spread, stress


def _bars_index(bars: Any) -> tuple[list[float], list[dict[str, Any]]] | None:
    """`_bars_until` read once for a whole replay: the rows it can ever show, in tape order, with the
    running maximum of their stamps. The rows shown at `now_ts` are the first `k` of them, `k` the
    first place that maximum passes `now_ts` -- exactly where `_bars_until` stops reading."""
    if not isinstance(bars, (list, tuple)):
        return None
    tops: list[float] = []
    rows: list[dict[str, Any]] = []
    top = -math.inf
    for bar in bars:
        if not isinstance(bar, dict):
            continue
        stamp = _parse_ts(bar.get("t"))
        if stamp is None:
            continue
        top = max(top, stamp)
        tops.append(top)
        rows.append(bar)
    return tops, rows


class _Prepared:
    """What a tape says that no strategy can change, read once.

    A single replay reads each step as it walks it (`eager=False`), as it always has. A batch
    (`run_batch`) reads the whole tape once, `eager=True`, before any candidate runs: the step
    times, the block keys, every step's view of the market and the indexes over the recorded bars
    and feeds are then shared by every candidate. A view is a pure function of its step and the
    tape's spread, and nothing in the simulator writes to one, so a candidate walks exactly the
    views it would have built itself."""

    def __init__(self, tape: Any, *, eager: bool = False):
        self.tape = tape
        self.eager = eager
        self.problem = _tape_problem(tape)
        self._stamps: list[float] | None = None
        self._keys: dict[str, list[str]] = {}
        self._views: list[_View] | None = None
        self._priced: list[dict[str, int]] | None = None
        self._indexes: dict[tuple[str, str], Any] = {}
        self._feeds: Any = None
        if eager and self.problem is None:
            self._read_all()

    def _read_all(self) -> None:
        tape = self.tape
        steps = tape["steps"]
        self._stamps = [_parse_ts(step["t"]) for step in steps]  # type: ignore[misc]
        for horizon in ("hour", "day"):
            self._keys[horizon] = [_block_key(ts, horizon) for ts in self._stamps]
        if tape.get("asset_class") != "option":
            if tape["venue"] == "alpaca":
                half_spread, stress = _spread_of(tape)
                self._views, self._priced = [], []
                for step in steps:
                    priced: dict[str, int] = {}
                    self._views.append(_alpaca_view(step, half_spread, stress, priced))
                    self._priced.append(priced)
            else:
                self._views = [_kalshi_view(step) for step in steps]
        if isinstance(tape.get("feeds"), dict):
            self._feeds = _feed_index(tape["feeds"])
        for source in ("options_features", "observed_bars"):
            series = tape.get(source)
            if isinstance(series, dict):
                for symbol, bars in series.items():
                    self.index(source, symbol, bars or ())

    def stamp(self, index: int, step: dict) -> float:
        if self._stamps is not None:
            return self._stamps[index]
        stamp = _parse_ts(step["t"])
        assert stamp is not None  # _tape_problem checked every step
        return stamp

    def block_key(self, index: int, ts: float, horizon: str) -> str:
        keys = self._keys.get(horizon)
        return keys[index] if keys is not None else _block_key(ts, horizon)

    def view(self, index: int, step: dict, venue: str, half_spread: float, stress: float, priced: dict[str, int]) -> _View:
        if self._views is not None:
            for how, count in self._priced[index].items() if self._priced is not None else ():
                priced[how] = priced.get(how, 0) + count
            return self._views[index]
        return _alpaca_view(step, half_spread, stress, priced) if venue == "alpaca" else _kalshi_view(step)

    def feed_index(self) -> Any:
        if self._feeds is None:
            self._feeds = _feed_index(self.tape.get("feeds"))
        return self._feeds

    def index(self, source: str, symbol: str, bars: Any) -> Any:
        key = (source, symbol)
        if key not in self._indexes:
            self._indexes[key] = _bars_index(bars)
        return self._indexes[key]

    def bars_until(self, source: str, symbol: str, bars: Any, now_ts: float, last: int | None = None) -> list[dict[str, Any]]:
        """`_bars_until(bars, now_ts)`, or its `last` rows, answered from the index (`bars` is the
        tape's own series for this symbol, the same object at every step of a replay)."""
        found = self.index(source, symbol, bars)
        if found is None:
            return []
        tops, rows = found
        count = bisect.bisect_right(tops, now_ts)
        return rows[max(0, count - last):count] if last else rows[:count]


def run_replay(code: str, params: dict | None, tape: dict, *, stake: float = 200.0,
               limits: dict | None = None, oos_fraction: float = 0.34,
               max_decide_seconds: float = 5.0, audit: bool = False, prepared: "_Prepared | None" = None) -> dict:
    """Walk `tape` with the strategy in `code` and return the per-block after-cost log growth.

    Never raises for a bad strategy or a bad tape: those come back as `{"ok": False, "error"}`.
    `audit=True` adds every fill (`fill_log`) and the strategy's last memory (`final_memory`)
    to the result, for tests and for a person checking a run; the box never asks for it.
    `prepared` is this same tape already read (`run_batch` reads it once for every candidate)."""
    code = code if isinstance(code, str) else str(code or "")
    sha = hashlib.sha256(code.encode("utf-8", "replace")).hexdigest()

    def failed(error: str, **more: Any) -> dict:
        return {"ok": False, "error": error, **more, "code_sha256": sha}

    try:
        check_code(code)
    except CodeRefused as exc:
        return failed(f"refused: {_short(exc)}")
    if prepared is None or prepared.tape is not tape:
        prepared = _Prepared(tape)
    problem = prepared.problem
    if problem:
        return failed(f"bad tape: {problem}")
    stake_usd = _num(stake)
    if stake_usd is None or stake_usd <= 0:
        return failed("the stake is a positive number of dollars")
    rung_limits = dict(DEFAULT_LIMITS)
    for name in DEFAULT_LIMITS:
        given = _num((limits or {}).get(name))
        if given is not None and given >= 0:
            rung_limits[name] = given
    sink = _Null()
    random_state = random.getstate()
    random.seed(int(sha[:16], 16))  # a strategy that draws random numbers replays the same way twice
    try:
        with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink), _Deadline(max_decide_seconds) as deadline:
            return _replay(code, sha, params, tape, stake_usd, rung_limits, float(oos_fraction), deadline,
                           bool(audit), failed, prepared)
    finally:
        random.setstate(random_state)


def _replay(code: str, sha: str, params: dict | None, tape: dict, stake: float, limits: dict[str, float],
            oos_fraction: float, deadline: _Deadline, audit: bool, failed: Any, prepared: _Prepared) -> dict:
    seed = int(sha[:16], 16)
    try:
        compiled = compile(code, "<strategy>", "exec")  # once; the module body itself runs at every step
    except (SyntaxError, ValueError) as exc:
        return failed(f"the strategy did not load: {type(exc).__name__}: {_short(exc, 160)}")

    def fresh_module() -> dict[str, Any]:
        """The strategy file, run from the top in a namespace of its own. A live wake does exactly
        this for every decision (`league/runner.py`), so a module-level global never carries from
        one `decide` to the next: `memory` is the only state a strategy keeps."""
        namespace: dict[str, Any] = {"__name__": "strategy", "__builtins__": builtins}
        exec(compiled, namespace)  # noqa: S102 - check_code passed it
        if not callable(namespace.get("decide")):
            raise TypeError("the strategy defines no decide(ctx)")
        return namespace

    def load() -> list:
        # Whatever the strategy hands over is turned into plain JSON data while its deadline is
        # still running: an object with methods of its own never reaches the simulator's code.
        namespace = fresh_module()
        declared = [namespace.get("NEEDS"), namespace.get("PARAMS")]
        return json.loads(json.dumps([d if isinstance(d, dict) else {} for d in declared], allow_nan=False))

    declared, error = deadline.call(load)
    if error:
        return failed(f"the strategy did not load: {error}")
    needs, defaults = declared
    try:
        effective = json.loads(json.dumps({**defaults, **(params if isinstance(params, dict) else {})}, allow_nan=False))
    except (TypeError, ValueError, RecursionError):
        return failed("params must be plain JSON data")

    def decide(ctx: dict) -> dict:
        # One deadline covers loading the module and deciding, as it does live.
        answer = fresh_module()["decide"](ctx)
        if not isinstance(answer, dict):
            raise TypeError(f"decide returned {type(answer).__name__}, not a dict")
        return json.loads(json.dumps(answer))  # as it would cross the wire from the agent's box

    venue = tape["venue"]
    if needs.get("venue") not in (None, venue):
        return failed(f"the strategy trades {_short(needs.get('venue'), 20)} and the tape is {venue}")
    horizon = tape.get("horizon") or needs.get("horizon") or "hour"
    if horizon not in ("hour", "day"):
        return failed("bad tape: the horizon is hour or day")
    if tape.get("asset_class") == "option":
        # The options desk's tape (`league/options_history.py`): its own simulator, same result shape.
        try:
            from league.options_replay import replay_options
        except ImportError:  # in the agent's box the files sit side by side
            from options_replay import replay_options  # type: ignore
        return replay_options(decide, needs, effective, tape, stake, limits, oos_fraction, deadline, audit, failed, seed, sha, horizon)
    half_spread, stress = _spread_of(tape)
    priced: dict[str, int] = {}
    results = tape.get("results") if isinstance(tape.get("results"), dict) else {}

    bars_need = needs.get("bars") if isinstance(needs.get("bars"), dict) else {}
    if venue == 'alpaca' and tape.get('timeframe') and bars_need.get('timeframe') and tape['timeframe'] != bars_need['timeframe']:
        return failed('unsupported input: tape timeframe does not match declared bars')
    bar_limit = _num(bars_need.get("limit"))
    bar_limit = DEFAULT_BARS if bar_limit is None else max(1, min(MAX_BARS, int(bar_limit)))
    wanted_symbols = [s for s in needs.get("symbols") or [] if isinstance(s, str)] if isinstance(needs.get("symbols"), list) else []
    wanted_series = {s for s in needs.get("series") or [] if isinstance(s, str)} if isinstance(needs.get("series"), list) else set()
    # What the strategy WATCHES rides on the same tape but may not be traded, here as in the House.
    observe = needs.get("observe") if isinstance(needs.get("observe"), dict) else {}
    watched_symbols = [s for s in (observe.get("symbols") or []) if isinstance(s, str)][:6]
    watched_series = {s for s in (observe.get("series") or []) if isinstance(s, str)}
    # Bars of what it watches on another venue, recorded once for the whole window and sliced at
    # each step: a Kalshi tape carries no bars of its own, and an hourly BTC strike is a bet about
    # a price the strategy could not see until now.
    observed_bars = tape.get("observed_bars") if isinstance(tape.get("observed_bars"), dict) else {}
    observed_need = bars_need  # the same NEEDS.bars declaration used by the live House
    observed_limit = _num(observed_need.get('limit'))
    observed_limit = 60 if observed_limit is None else max(1, min(200, int(observed_limit)))
    if venue == 'kalshi' and watched_symbols and tape.get('observed_timeframe') and tape['observed_timeframe'] != (observed_need.get('timeframe') or '1Hour'):
        return failed('unsupported input: observed timeframe does not match declaration')
    if venue == 'kalshi' and watched_symbols and any(not observed_bars.get(s) for s in watched_symbols):
        return failed('unsupported input: required observed bars are missing')
    max_hours = _num(needs.get("max_hours_to_close"))
    # Recorded live feeds (`league/feeds.py`), shown only to a strategy that declares them.
    feeds = prepared.feed_index() if needs.get("feeds") and isinstance(tape.get("feeds"), dict) else None

    account = _Account(venue, stake, limits, results, audit, tape.get("maker_fee_series") if isinstance(tape.get("maker_fee_series"), list) else (),
                       tape.get('settlements') if isinstance(tape.get('settlements'), dict) else None)
    account.tradeable = (set(wanted_symbols) if wanted_symbols else None, wanted_series or None)
    history: dict[str, list[dict[str, Any]]] = {s: [dict(b) for b in rows[-MAX_BARS:]] for s, rows in (tape.get('warmup_bars') or {}).items()}
    memory: dict[str, Any] = {}
    errors, last_error = 0, ""
    blocks: list[dict[str, Any]] = []
    block_key, block_active, block_equity = None, False, stake
    previous_equity = stake
    peak, max_drawdown = stake, 0.0
    equity = stake
    ruined = False
    steps_walked = 0

    def close_block(log_growth: float | None = None) -> None:
        nonlocal previous_equity
        if log_growth is None:  # never worse than ruin, so one block cannot outweigh the rest of the series
            log_growth = max(RUIN_LOG_GROWTH, math.log(block_equity / previous_equity))
        blocks.append({"key": block_key, "log_growth": round(log_growth, 12), "active": block_active})
        previous_equity = block_equity

    decisions_walked = 0
    for index, step in enumerate(tape["steps"]):
        now = step["t"]
        now_ts = prepared.stamp(index, step)
        key = prepared.block_key(index, now_ts, horizon)
        if key != block_key:
            if block_key is not None:
                close_block()
            block_key, block_active = key, False
        steps_walked += 1
        view = prepared.view(index, step, venue, half_spread, stress, priced)
        held_before, fills_before = bool(account.positions), account.fills

        # (a) orders from earlier steps meet this step's range; closed markets settle.
        if venue == "kalshi":
            account.refresh_closes(view)
        account.work_resting(view, now, now_ts)
        # (b) mark.
        equity = account.mark(view)
        for symbol, bar in view.bars.items():
            series = history.setdefault(symbol, [])
            series.append(bar)
            del series[:-MAX_BARS]
        for symbol, bars in (step.get('history_bars') or {}).items():
            series = history.setdefault(symbol, [])
            series.extend(dict(bar) for bar in bars)
            del series[:-MAX_BARS]

        if equity > RUIN_EQUITY and step.get("execution_only") is not True:
            # Closing execution events are not new snapshots or wakes. Besides avoiding an empty
            # universe decision, keep their insertion from changing later regular random draws.
            decisions_walked += 1
            random.seed(seed + decisions_walked)
            # (c) what the strategy may know: this step and the past, never the tape itself.
            ctx: dict[str, Any] = {
                "now": now, "venue": venue, "rung": 0,
                "params": copy.deepcopy(effective), "memory": copy.deepcopy(memory),
                "cash": account.cash, "equity": equity,
                "limits": dict(limits), "fees": dict(FEES),
                "positions": account.positions_view(), "open_orders": account.orders_view(),
            }
            if venue == "alpaca":
                shown = wanted_symbols or sorted(history)
                # Every history row is a plain dict this simulator made, so `dict.copy` is `dict(b)`,
                # a third faster: these copies are most of a long equity replay's time.
                ctx["bars"] = {s: list(map(dict.copy, history.get(s, [])[-bar_limit:])) for s in shown}
                # A replay quote is made at this decision step, so it carries the step's own time as
                # `t`, as a live quote carries its venue timestamp (CONTRACT.md). Without it, every
                # strategy that refuses a stale or undated quote -- the careful ones -- never traded
                # in replay: measured Sept 22, 2026, four frontier-written megacaps cards made 0
                # trades each, and 14, 31, 5 and 14 once replay quotes were dated.
                # A recorded quote (league.history probes) is dated when it was quoted: now less its age.
                def dated(s):
                    age = view.quote_age.get(s)
                    t = now if not age else datetime.fromtimestamp(now_ts - age, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
                    return {"bid": view.quotes[s][0], "ask": view.quotes[s][1], "t": t}
                ctx["quotes"] = {s: dated(s) for s in shown if s in view.quotes}
                if watched_symbols:
                    ctx["observed"] = {
                        "bars": {s: list(map(dict.copy, history.get(s, [])[-bar_limit:])) for s in watched_symbols},
                        "quotes": {s: dated(s) for s in watched_symbols if s in view.quotes},
                    }
                if needs.get("options_features") and isinstance(tape.get("options_features"), dict):
                    # Options-derived features, each row stamped with when it became available:
                    # the latest at or before this step, exactly what a live wake is handed.
                    ctx["options_features"] = {s: dict(rows[-1]) for s, rows in
                                               ((s, prepared.bars_until("options_features", s, tape["options_features"].get(s) or (), now_ts, 1))
                                                for s in shown) if rows}
            else:
                shown_markets, watched_markets = [], []
                for market in view.markets.values():
                    close_ts = market["close_ts"]
                    if close_ts is not None and close_ts <= now_ts:
                        continue
                    hours = None if close_ts is None else round((close_ts - now_ts) / 3600.0, 6)
                    mine = not wanted_series or market.get("series") in wanted_series
                    watched = market.get("series") in watched_series
                    if not mine and not watched:
                        continue
                    if mine and max_hours is not None and (hours is None or hours > max_hours):
                        mine = False  # past its horizon to trade, but still something it may watch
                        if not watched:
                            continue
                    row = {k: v if isinstance(v, _SCALARS) else copy.deepcopy(v) for k, v in market.items() if k != "close_ts"}
                    row["hours_to_close"] = hours
                    if mine:
                        shown_markets.append(row)
                    if watched:
                        watched_markets.append(row if mine else dict(row))
                ctx["markets"] = shown_markets
                # A market it WATCHES is not one it trades, so it is not cut to its own series or
                # its own horizon. Underlier bars ride on the tape (see `House.tape_for`): six of
                # the floor's agents asked the toolsmith for the spot price behind their strikes,
                # and it rightly answered that no strategy helper can put it there.
                if watched_series or (watched_symbols and observed_bars):
                    ctx["observed"] = {}
                    if watched_series:
                        ctx["observed"]["markets"] = watched_markets
                    if watched_symbols and observed_bars:
                        ctx["observed"]["bars"] = {
                            s: [dict(b) for b in prepared.bars_until("observed_bars", s, observed_bars.get(s) or (), now_ts, observed_limit)]
                            for s in watched_symbols
                        }
            if feeds is not None:
                # Each row is stamped with when the House received it: the latest at or before this
                # step, exactly what a live wake is handed. Nothing received later is ever shown.
                ctx["feeds"] = _feeds_until(feeds, now_ts)

            # (d) decide.
            answer, error = deadline.call(decide, ctx)
            if error is not None:
                errors += 1
                last_error = error
                if errors >= MAX_ERRORS:
                    return failed("too many errors", errors=errors, last_error=last_error, steps=steps_walked)
            else:
                memory = _clean_memory(answer.get("memory"))
                # (e) cancels, then intents.
                cancels, intents = answer.get("cancels"), answer.get("intents")
                if cancels is not None and not isinstance(cancels, list):
                    account.refuse("malformed: cancels is a list of order ids")
                    cancels = []
                if intents is not None and not isinstance(intents, list):
                    account.refuse("malformed: intents is a list")
                    intents = []
                for index, order_id in enumerate(cancels or []):
                    if index >= MAX_CANCELS:
                        account.refuse("over 20 cancels in one decision")
                    else:
                        account.cancel(order_id)
                for index, intent in enumerate(intents or []):
                    if index >= MAX_INTENTS:
                        account.refuse("over 8 intents in one decision")
                    else:
                        account.submit(intent, view, now, now_ts)
            equity = account.equity()

        if held_before or account.positions or account.fills > fills_before:
            block_active = True
        block_equity = equity
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, (peak - equity) / peak)
        if equity <= RUIN_EQUITY:  # nothing left to trade with: the run ends here
            ruined = True
            close_block(RUIN_LOG_GROWTH)
            block_key = None
            break
    if block_key is not None:
        close_block()

    out_count = max(0, min(len(blocks), int(math.floor(len(blocks) * max(0.0, min(1.0, oos_fraction)) + 1e-9))))
    inside, outside = blocks[: len(blocks) - out_count], blocks[len(blocks) - out_count:]
    result = {
        "ok": True,
        "blocks": blocks,
        "trades": len(account.trade_returns),
        "trade_returns": [round(r, 12) for r in account.trade_returns],
        "fills": account.fills,
        "maker_fills": account.maker_fills,
        "fees_usd": round(account.fees_usd, 10),
        "refused": account.refused,
        "refusal_reasons": dict(sorted(account.refusal_reasons.items())),
        "errors": errors,
        "last_error": last_error,
        "unresolved": account.unresolved + (sum(1 for p in account.positions.values() if p['close_ts'] is not None and p['close_ts'] <= now_ts) if account.settlements is not None else 0),
        "expired_orders": account.expired_orders,
        "open_positions": len(account.positions),
        "open_orders": len(account.orders),
        "final_equity": round(equity, 10),
        "return_pct": round((equity / stake - 1.0) * 100.0, 10),
        "max_drawdown": round(max_drawdown, 12),
        "ruined": ruined,
        "steps": steps_walked,
        "horizon": horizon,
        "venue": venue,
        "stake": stake,
        "in_sample": {"blocks": len(inside), "mean_log_growth": round(_mean([b["log_growth"] for b in inside]), 12)},
        "out_of_sample": {
            "blocks": len(outside),
            "mean_log_growth": round(_mean([b["log_growth"] for b in outside]), 12),
            "active_blocks": sum(1 for b in outside if b["active"]),
        },
        "needs": needs,
        "params": effective,
        "code_sha256": sha,
    }
    if venue == "alpaca" and (stress != 1.0 or priced.get("quoted") or priced.get("stale")):
        # Only a tape that carries quotes or stress says so: every older tape's result is unchanged.
        result["execution"] = {"touch": dict(sorted(priced.items())), "spread_stress": stress,
                               "stale_after_seconds": STALE_QUOTE_SECONDS,
                               "limits": "no queue position, no depth: a resting limit fills only when later prints trade through it"}
    result["digest"] = digest(account.trade_log)
    if audit:
        result["fill_log"] = account.fill_log
        result["final_memory"] = memory
    return result


def market_series(view: Any, ticker: str) -> str:
    market = view.markets.get(ticker)
    return str((market or {}).get("series") or "")


def digest(trades: list) -> dict:
    """What a strategy's closed trades say, small enough to hand a research model: the record by
    series (or symbol), by how long before the market's end it got IN (on Kalshi, where a bid
    left resting into the last hours is the one that gets picked off), and the worst of them.
    A replay's headline number says a strategy lost; this says where."""
    def hours(row):
        try:
            a = datetime.fromisoformat(str(row["opened_at"]).replace("Z", "+00:00"))
            b = datetime.fromisoformat(str(row["close_time"]).replace("Z", "+00:00"))
            return (b - a).total_seconds() / 3600.0
        except (KeyError, TypeError, ValueError):
            return None

    def tally(rows):
        return {"trades": len(rows), "wins": sum(1 for r in rows if r["pnl"] > 0), "losses": sum(1 for r in rows if r["pnl"] <= 0),
                "pnl_usd": round(sum(r["pnl"] for r in rows), 4),
                "mean_entry": round(sum(r["entry"] for r in rows if r.get("entry")) / max(1, sum(1 for r in rows if r.get("entry"))), 4)}

    groups: dict = {}
    timing: dict = {}
    for row in trades:
        groups.setdefault(row["group"], []).append(row)
        h = hours(row)
        if h is not None:
            bucket = "under 1h" if h < 1 else "1 to 3h" if h < 3 else "3 to 12h" if h < 12 else "over 12h"
            timing.setdefault(bucket, []).append(row)
    ranked = sorted(groups.items(), key=lambda kv: -len(kv[1]))[:12]
    worst = sorted(trades, key=lambda r: r["pnl"])[:5]
    return {
        "all": tally(trades),
        "by_group": {name: tally(rows) for name, rows in ranked},
        "by_hours_from_entry_to_the_markets_end": {name: tally(rows) for name, rows in timing.items()},
        "worst": [{"name": r["name"], "leg": r.get("leg"), "pnl_usd": round(r["pnl"], 4), "entry": r.get("entry"), "opened_at": r.get("opened_at"), "how": r["how"]} for r in worst if r["pnl"] < 0],
    }


# ------------------------------------------------------------------------------------- the batch
#: The error a candidate the batch's time budget did not reach (or did not let finish) comes back with.
NOT_EVALUATED = "not evaluated: batch budget"
#: The error of a candidate whose process the box could not start (`os.fork` refused: out of processes
#: or memory). The box's failure, never the candidate's: it comes back not evaluated and marked
#: `infrastructure`, to be sent again, as a budget cut-off is.
NOT_STARTED = "not evaluated: the box could not start its process"


def not_evaluated(result: Any) -> bool:
    """Did the batch leave this candidate unjudged (its budget, or the box failing to start it)?"""
    return isinstance(result, dict) and str(result.get("error") or "").startswith("not evaluated")
#: A candidate's own wall-clock limit in a batch. A single replay has only the box's limit, and a
#: strategy that swallows its decide deadline inside an endless loop would hold the whole batch.
CANDIDATE_SECONDS = 300.0
#: Memory one candidate may add to what its process inherits, so a runaway one fails alone.
CANDIDATE_MEMORY_MB = 2048


def _batch_failure(exc: BaseException) -> dict:
    """What `main` prints when a replay raises past `run_replay` (it never should)."""
    return {"ok": False, "error": f"replay failed: {type(exc).__name__}: {_short(exc)}"}


def _candidate_text(candidate: dict, tape: Any, prepared: "_Prepared | None", options: dict) -> str:
    """One candidate's result as the JSON a single box run prints for it (`main`)."""
    try:
        result = run_replay(candidate.get("code"), candidate.get("params"), tape, prepared=prepared, **options)
        return json.dumps(result, allow_nan=False)
    except KeyboardInterrupt:
        raise
    except BaseException as exc:  # noqa: BLE001 - the box always answers
        return json.dumps(_batch_failure(exc))


def _malformed(candidate: Any) -> str | None:
    if not isinstance(candidate, dict):
        return "malformed candidate: a candidate is a dict"
    if not isinstance(candidate.get("id"), str) or not candidate["id"]:
        return "malformed candidate: every candidate has a string id"
    return None


def _workers() -> int:
    try:
        return max(1, len(os.sched_getaffinity(0)))  # type: ignore[attr-defined]
    except (AttributeError, OSError):
        return max(1, os.cpu_count() or 1)


def run_batch(candidates: list[dict], tape: dict, *, stake: float = 200.0, limits: dict | None = None,
              oos_fraction: float = 0.34, max_decide_seconds: float = 5.0, budget_seconds: float | None = None,
              workers: int | None = None, candidate_seconds: float | None = None,
              memory_mb: int | None = CANDIDATE_MEMORY_MB, clock: Any = time.monotonic) -> list[dict]:
    """Replay many strategies over ONE tape, read once.

    `candidates` is `[{"id": str, "code": str, "params": dict}]`. The result is one dict per
    candidate, in order: exactly what `run_replay(code, params, tape, stake=..., limits=...,
    oos_fraction=..., max_decide_seconds=...)` returns for it, plus its `id`.

    The tape is validated and read once (`_Prepared(eager=True)`: step times, block keys, every
    step's market view, bar and feed indexes). Each candidate then runs in a process of its own,
    forked from that one (`workers` at a time, one a CPU by default), so it is isolated as a single
    replay is -- its own seed from its code, its own decide deadline, its prints sunk, the same
    `check_code` refusal -- and nothing one candidate does to its interpreter reaches another. A
    candidate that crashes its process, outlives `candidate_seconds` or outgrows `memory_mb` comes
    back `{"ok": False, "error": ...}`; it never takes the batch down. Once `budget_seconds` (from
    the call) is spent, no candidate starts and any still running is stopped: those come back
    `{"ok": False, "error": "not evaluated: batch budget"}`. A candidate the box cannot start at all
    (`os.fork` refused with nothing running: the box is out of processes or memory) is the box's
    failure, not its own: it comes back `{"ok": False, "error": "not evaluated: the box could not
    start its process (...)", "infrastructure": True}` (`not_evaluated` is true of both), to be sent
    again. Where `os.fork` does not exist the candidates run one after another in this process,
    without that isolation."""
    started = clock()
    candidates = list(candidates or [])
    options = {"stake": stake, "limits": limits, "oos_fraction": oos_fraction, "max_decide_seconds": max_decide_seconds}
    results: list[dict | None] = [None] * len(candidates)
    todo: list[int] = []
    for index, candidate in enumerate(candidates):
        problem = _malformed(candidate)
        if problem:
            results[index] = {"ok": False, "error": problem, "id": candidate.get("id") if isinstance(candidate, dict) else None}
        else:
            todo.append(index)
    try:
        prepared: _Prepared | None = _Prepared(tape, eager=True)
    except Exception:  # noqa: BLE001 - a tape the reader chokes on is read by each candidate as it always was
        prepared = None
    deadline = None if budget_seconds is None else started + max(0.0, float(budget_seconds))
    limit = CANDIDATE_SECONDS if candidate_seconds is None else max(0.001, float(candidate_seconds))

    def finish(index: int, text: str | None, error: str | None = None, *, infrastructure: bool = False) -> None:
        if infrastructure:
            results[index] = {"ok": False, "error": error or NOT_STARTED, "infrastructure": True, "id": candidates[index]["id"]}
            return
        if text is not None:
            try:
                value = json.loads(text)
            except ValueError:
                value = None
            if isinstance(value, dict):
                value["id"] = candidates[index]["id"]
                results[index] = value
                return
            error = error or "the candidate's process answered no result"
        results[index] = {"ok": False, "error": error or "the candidate's process answered no result", "id": candidates[index]["id"]}

    if not hasattr(os, "fork") or workers == 0:
        for index in todo:
            if deadline is not None and clock() >= deadline:
                finish(index, None, NOT_EVALUATED)
                continue
            finish(index, _candidate_text(candidates[index], tape, prepared, options))
    else:
        _forked(candidates, todo, tape, prepared, options, finish, workers=max(1, int(workers or _workers())),
                deadline=deadline, limit=limit, memory_mb=memory_mb, clock=clock)
    return [r if r is not None else {"ok": False, "error": NOT_EVALUATED, "id": candidates[i].get("id")}
            for i, r in enumerate(results)]


def _forked(candidates: list[dict], todo: list[int], tape: Any, prepared: "_Prepared | None", options: dict, finish: Any, *,
            workers: int, deadline: float | None, limit: float, memory_mb: int | None, clock: Any) -> None:
    """Run `todo` in forked children, `workers` at a time; `finish(index, text, error)` gets each answer
    (`finish(index, None, error, infrastructure=True)` one the box itself could not run)."""

    def results_infra(index: int, error: str) -> None:
        finish(index, None, error, infrastructure=True)
    import gc
    import selectors
    import warnings

    queue = list(todo)
    running: dict[int, dict[str, Any]] = {}  # read fd -> {index, pid, chunks, started}
    selector = selectors.DefaultSelector()
    gc.collect()
    gc.freeze()  # the tape and its reading are shared by every child: the collector leaves them be

    def reap(fd: int, error: str | None) -> None:
        job = running.pop(fd)
        selector.unregister(fd)
        os.close(fd)
        if error is not None:
            try:
                os.kill(job["pid"], signal.SIGKILL)
            except OSError:
                pass
        try:
            _, status = os.waitpid(job["pid"], 0)
        except ChildProcessError:
            status = 0
        text = b"".join(job["chunks"]).decode("utf-8", "replace") if error is None else None
        if error is None and not text:
            how = (f"signal {os.WTERMSIG(status)}" if os.WIFSIGNALED(status) else f"exit {os.WEXITSTATUS(status)}")
            error = f"the candidate's process died ({how}) before it answered"
        finish(job["index"], text, error)

    try:
        while queue or running:
            now = clock()
            if deadline is not None and now >= deadline:
                return  # `finally` stops what runs and answers what waits: not evaluated
            while queue and len(running) < workers:
                index = queue[0]
                try:
                    read_fd, write_fd = os.pipe()
                    try:
                        with warnings.catch_warnings():
                            warnings.simplefilter("ignore", DeprecationWarning)  # a multi-threaded caller: the child only replays
                            pid = os.fork()
                    except OSError:
                        os.close(read_fd)
                        os.close(write_fd)
                        raise
                except OSError as exc:
                    if running:
                        break  # the box is out of processes or memory for now: wait for one to finish
                    # Nothing runs and none can start: the box is out of processes or memory. That is
                    # the box's failure, not any waiting candidate's, so none of them is answered as
                    # if it had run (review of PR 167): each comes back not evaluated, marked
                    # infrastructure, and is sent again.
                    for waiting in queue:
                        results_infra(waiting, f"{NOT_STARTED} ({type(exc).__name__}: {_short(exc, 120)})")
                    queue.clear()
                    return
                queue.pop(0)
                if pid == 0:  # the child: replay one candidate, write its answer, and leave without cleanup
                    try:
                        os.close(read_fd)
                        _child(write_fd, candidates[index], tape, prepared, options, memory_mb)
                    finally:
                        os._exit(0)
                os.close(write_fd)
                running[read_fd] = {"index": index, "pid": pid, "chunks": [], "started": clock()}
                selector.register(read_fd, selectors.EVENT_READ)
            waits = [job["started"] + limit for job in running.values()] + ([deadline] if deadline is not None else [])
            timeout = max(0.0, min(waits) - clock()) if waits else None
            for key, _ in selector.select(timeout=min(timeout, 1.0) if timeout is not None else 1.0):
                chunk = os.read(key.fd, 1 << 20)
                if chunk:
                    running[key.fd]["chunks"].append(chunk)
                else:
                    reap(key.fd, None)
            now = clock()
            for fd, job in list(running.items()):
                if now - job["started"] >= limit:
                    reap(fd, f"timed out after {limit:g}s")
    finally:
        for fd in list(running):
            reap(fd, NOT_EVALUATED)
        for index in queue:
            finish(index, None, NOT_EVALUATED)
        selector.close()
        gc.unfreeze()


def _child(fd: int, candidate: dict, tape: Any, prepared: "_Prepared | None", options: dict, memory_mb: int | None) -> None:
    """In a forked child: nothing it or the strategy prints reaches the box's stdout, its memory is
    capped above what it inherited, and its one answer goes down the pipe."""
    try:
        sink = os.open(os.devnull, os.O_WRONLY)
        os.dup2(sink, 1)
        os.dup2(sink, 2)
        sys.stdout = sys.stderr = _Null()
        if memory_mb:
            try:
                import resource

                with open("/proc/self/statm", encoding="ascii") as handle:
                    inherited = int(handle.read().split()[0]) * os.sysconf("SC_PAGE_SIZE")
                cap = inherited + int(memory_mb) * 1024 * 1024
                resource.setrlimit(resource.RLIMIT_AS, (cap, cap))
            except (ImportError, OSError, ValueError):
                pass  # no cap where the platform has none; the box's own limit is the backstop
        text = _candidate_text(candidate, tape, prepared, options)
    except BaseException as exc:  # noqa: BLE001 - a child always answers if it can
        text = json.dumps(_batch_failure(exc))
    data = text.encode("utf-8")
    view = memoryview(data)
    while view:
        written = os.write(fd, view)
        view = view[written:]
    os.close(fd)


def load_tape(path: str, digest: str | None = None) -> tuple[Any, str | None]:
    """(tape, None), or (None, why) when the file is missing or is not the tape `digest` names.
    A tape is kept gzipped, as the canonical JSON its digest is the SHA-256 of."""
    import gzip
    import zlib

    try:
        with gzip.open(path, "rb") as handle:
            raw = handle.read()
    except (OSError, EOFError):
        return None, "tape missing"
    except zlib.error:
        # A corrupt deflate stream is not an OSError: before this it failed the whole batch as the
        # box's error, the tape stayed recorded as held, and every later batch over it failed the
        # same way. Reported missing, it is sent again (review of PR 167).
        return None, "tape unreadable (corrupt gzip); send it again"
    if digest and hashlib.sha256(raw).hexdigest() != digest:
        return None, "tape does not match its digest"
    try:
        return json.loads(raw), None
    except ValueError:
        return None, "tape unreadable (not JSON); send it again"


def _main_batch(spec: dict) -> dict:
    """The box's batch: run `run_batch` over the spec and answer a summary (the full results go to
    `result_path`, gzipped, when the spec names one; the summary then carries their SHA-256)."""
    started = time.monotonic()
    tape = spec.get("tape")
    if tape is None and spec.get("tape_path"):
        tape, why = load_tape(str(spec["tape_path"]), spec.get("tape_digest"))
        if why:
            return {"ok": False, "error": why, "tape_missing": True}
    loaded = time.monotonic() - started
    options = {name: spec[name] for name in ("stake", "limits", "oos_fraction", "max_decide_seconds", "budget_seconds",
                                               "workers", "candidate_seconds", "memory_mb") if spec.get(name) is not None}
    if "budget_seconds" in options:  # the budget runs from the start of the program, loading included
        options["budget_seconds"] = max(0.0, float(options["budget_seconds"]) - loaded)
    results = run_batch(spec.get("candidates") or [], tape, **options)
    body = {"results": results, "evaluated": sum(1 for r in results if not not_evaluated(r)),
            "seconds": round(time.monotonic() - started, 3), "load_seconds": round(loaded, 3), "workers": int(options.get("workers") or _workers())}
    if not spec.get("result_path"):
        return {"ok": True, **body}
    import gzip

    data = gzip.compress(json.dumps(body, allow_nan=False).encode("utf-8"), 6, mtime=0)
    path = str(spec["result_path"])
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path + ".tmp", "wb") as handle:
        handle.write(data)
    os.replace(path + ".tmp", path)
    return {"ok": True, "result_path": path, "sha256": hashlib.sha256(data).hexdigest(), "count": len(results),
            "evaluated": body["evaluated"], "seconds": body["seconds"], "load_seconds": body["load_seconds"], "workers": body["workers"]}


# ------------------------------------------------------------------------------ the box's entry
def parse_result(stdout: str, token: str) -> dict | None:
    """The result a box run printed: the LAST line that starts `REPLAY-RESULT <token> `. A line
    that is not a JSON object is no result, and an earlier line is never a fallback for it."""
    prefix = f"{RESULT_PREFIX} {token} "
    found = None
    for line in str(stdout or "").splitlines():
        if line.startswith(prefix):
            found = line[len(prefix):]
    if found is None:
        return None
    try:
        value = json.loads(found)
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def main(argv: list[str] | None = None, *, hard_exit: bool = True) -> int:
    """`python3 replay.py --spec spec.json`: run the spec and print one `REPLAY-RESULT <token> <json>`
    line, the last thing on the real stdout. Everything else the run prints goes nowhere, and the
    process ends with `os._exit` so nothing a strategy left behind can print after the result.
    (`hard_exit=False` returns instead, for a caller in the same process.)

    `python3 replay.py --batch spec.json` runs `run_batch` instead (`_main_batch`): the spec holds
    `candidates` and the tape, inline or as `tape_path` (gzipped, checked against `tape_digest`)."""
    parser = argparse.ArgumentParser(description="Replay a strategy over a recorded tape (rung 0).")
    parser.add_argument("--spec", help="a JSON spec file; standard input when absent")
    parser.add_argument("--batch", help="a JSON batch spec file: many candidates over one tape")
    args = parser.parse_args(argv)
    real = sys.__stdout__
    kept = sys.stdout, sys.stderr
    sys.stdout = sys.stderr = _Null()
    token = ""
    try:
        if args.spec or args.batch:
            with open(args.batch or args.spec, encoding="utf-8") as handle:
                raw = handle.read()
        else:
            raw = sys.stdin.read()
        spec = json.loads(raw)
        if not isinstance(spec, dict):
            raise ValueError("the spec is a JSON object")
        token = "".join(str(spec.get("token") or "").split())
        if args.batch:
            result = _main_batch(spec)
        else:
            options = {name: spec[name] for name in ("stake", "limits", "oos_fraction", "max_decide_seconds")
                       if spec.get(name) is not None}
            result = run_replay(spec.get("code"), spec.get("params"), spec.get("tape"), **options)
        text = json.dumps(result, allow_nan=False)
    except KeyboardInterrupt:
        raise
    except BaseException as exc:  # noqa: BLE001 - the box always answers
        text = json.dumps({"ok": False, "error": f"replay failed: {type(exc).__name__}: {_short(exc)}"})
    finally:
        sys.stdout, sys.stderr = kept
    real.write(f"{RESULT_PREFIX} {token} {text}\n")
    real.flush()
    if hard_exit:
        os._exit(0)
    return 0


if __name__ == "__main__":
    main()
