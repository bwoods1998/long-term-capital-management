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
  strictly through it (`low < price` for a buy, `high > price` for a sell). Touching is not enough;
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
MAX_INTENTS = 8
MAX_CANCELS = 20
MAX_ERRORS = 20
MAX_MEMORY_BYTES = 8 * 1024
DEFAULT_BARS = 120
MAX_BARS = 500
DEFAULT_HALF_SPREAD_BPS = 2.0
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


def _alpaca_view(step: dict, half_spread: float) -> _View:
    view = _View()
    bars = step.get("execution_bars", step.get("bars"))
    if not isinstance(bars, dict):
        return view
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
        bid, ask = close * (1.0 - half_spread), close * (1.0 + half_spread)
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


def run_replay(code: str, params: dict | None, tape: dict, *, stake: float = 200.0,
               limits: dict | None = None, oos_fraction: float = 0.34,
               max_decide_seconds: float = 5.0, audit: bool = False) -> dict:
    """Walk `tape` with the strategy in `code` and return the per-block after-cost log growth.

    Never raises for a bad strategy or a bad tape: those come back as `{"ok": False, "error"}`.
    `audit=True` adds every fill (`fill_log`) and the strategy's last memory (`final_memory`)
    to the result, for tests and for a person checking a run; the box never asks for it."""
    code = code if isinstance(code, str) else str(code or "")
    sha = hashlib.sha256(code.encode("utf-8", "replace")).hexdigest()

    def failed(error: str, **more: Any) -> dict:
        return {"ok": False, "error": error, **more, "code_sha256": sha}

    try:
        check_code(code)
    except CodeRefused as exc:
        return failed(f"refused: {_short(exc)}")
    problem = _tape_problem(tape)
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
                           bool(audit), failed)
    finally:
        random.setstate(random_state)


def _replay(code: str, sha: str, params: dict | None, tape: dict, stake: float, limits: dict[str, float],
            oos_fraction: float, deadline: _Deadline, audit: bool, failed: Any) -> dict:
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
    half_spread_bps = _num(tape.get("half_spread_bps"))
    half_spread = (DEFAULT_HALF_SPREAD_BPS if half_spread_bps is None or half_spread_bps < 0 else half_spread_bps) / 10000.0
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
    for step in tape["steps"]:
        now = step["t"]
        now_ts = _parse_ts(now)
        assert now_ts is not None  # _tape_problem checked every step
        key = _block_key(now_ts, horizon)
        if key != block_key:
            if block_key is not None:
                close_block()
            block_key, block_active = key, False
        steps_walked += 1
        view = _alpaca_view(step, half_spread) if venue == "alpaca" else _kalshi_view(step)
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
                ctx["bars"] = {s: [dict(b) for b in history.get(s, [])[-bar_limit:]] for s in shown}
                ctx["quotes"] = {s: {"bid": view.quotes[s][0], "ask": view.quotes[s][1]} for s in shown if s in view.quotes}
                if watched_symbols:
                    ctx["observed"] = {
                        "bars": {s: [dict(b) for b in history.get(s, [])[-bar_limit:]] for s in watched_symbols},
                        "quotes": {s: {"bid": view.quotes[s][0], "ask": view.quotes[s][1]} for s in watched_symbols if s in view.quotes},
                    }
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
                            s: [dict(b) for b in _bars_until(observed_bars.get(s) or (), now_ts)[-observed_limit:]]
                            for s in watched_symbols
                        }

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
    (`hard_exit=False` returns instead, for a caller in the same process.)"""
    parser = argparse.ArgumentParser(description="Replay a strategy over a recorded tape (rung 0).")
    parser.add_argument("--spec", help="a JSON spec file; standard input when absent")
    args = parser.parse_args(argv)
    real = sys.__stdout__
    kept = sys.stdout, sys.stderr
    sys.stdout = sys.stderr = _Null()
    token = ""
    try:
        if args.spec:
            with open(args.spec, encoding="utf-8") as handle:
                raw = handle.read()
        else:
            raw = sys.stdin.read()
        spec = json.loads(raw)
        if not isinstance(spec, dict):
            raise ValueError("the spec is a JSON object")
        token = "".join(str(spec.get("token") or "").split())
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
