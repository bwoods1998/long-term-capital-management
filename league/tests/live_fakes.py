"""Fakes for the live path's tests: a market and an Alpaca account with the SHAPES the gateway answered on Sept 26, 2026
(league/live/venue.py's docstring), and invented numbers (Black-Scholes on a made-up spot and vol: the data licence
forbids committing real quotes)."""

from __future__ import annotations

import datetime as dt
import math
import uuid
from decimal import Decimal
from typing import Any, Callable, Iterable, Mapping
from zoneinfo import ZoneInfo

import numpy as np

from league.gym import greeks as G
from league.live.venue import Rate, Submitted, occ_parts, occ_symbol
from league.data import TransportError

NY = ZoneInfo("America/New_York")
MONDAY = dt.date(2026, 9, 28)


def at(day: dt.date, hh: int, mm: int, ss: int = 3) -> float:
    return dt.datetime(day.year, day.month, day.day, hh, mm, ss, tzinfo=NY).timestamp()


def iso(t: float) -> str:
    return dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f") + "123Z"


class Clock:
    def __init__(self, t: float):
        self.t = float(t)

    def __call__(self) -> float:
        return self.t

    def set(self, t: float) -> None:
        self.t = float(t)


class Market:
    """Option chains for SPY (and XSP, SPX/10) from Black-Scholes on a spot the test moves; $1 strikes, a 2-cent
    spread (wider away from the money), sizes 50/60."""

    def __init__(self, clock: Clock, *, spot: float = 600.0, vol: float = 0.18, day: dt.date = MONDAY,
                 expiries: Iterable[int] = (0, 1, 2, 3, 4, 7), width: int = 30):
        self.clock, self.spot, self.vol, self.day = clock, float(spot), vol, day
        self.center = float(spot)        # the listed strikes stay where they were listed as the spot moves
        self.expiries, self.width = tuple(expiries), width
        self.calls = 0
        self.minute_calls = Rate(100000)
        self.dead: set[str] = set()      # roots whose chain read fails
        self.overrides: dict[str, tuple[float, float, int, int]] = {}

    def level(self, root: str) -> float:
        return self.spot * (10.0 if root in ("SPXW", "SPX") else 1.0) * (1.001 if root == "XSP" else 1.0)

    def rows(self, root: str) -> dict[str, dict]:
        t = self.clock()
        local = dt.datetime.fromtimestamp(t, NY)
        minute = local.hour * 60 + local.minute
        level = self.level(root)
        step = 5.0 if root in ("SPXW", "SPX") else 1.0
        listed = self.center * (10.0 if root in ("SPXW", "SPX") else 1.0) * (1.001 if root == "XSP" else 1.0)
        base = round(listed / step) * step
        out = {}
        for d in self.expiries:
            expiry = self.day + dt.timedelta(days=d)
            strikes = base + step * np.arange(-self.width, self.width + 1)
            for is_call in (True, False):
                years = G.years_to_expiry(np.full(strikes.size, d), minute)
                mid = G.bs_price(level, strikes, years, 0.04, self.vol, is_call)
                for k, m in zip(strikes, mid):
                    sym = occ_symbol(root, expiry.isoformat(), is_call, float(k))
                    half = 0.01 + 0.002 * abs(k - level) / step
                    bid, ask = max(0.0, round(m - half, 2)), round(max(m + half, 0.01), 2)
                    if sym in self.overrides:
                        bid, ask, bs, as_ = self.overrides[sym]
                    else:
                        bs, as_ = 50, 60
                    out[sym] = {"latestQuote": {"ap": ask, "as": as_, "ax": "Q", "bp": bid, "bs": bs, "bx": "Q", "c": " ",
                                                "t": iso(t - 1)}}
        return out

    def quote(self, symbol: str) -> tuple[float, float]:
        parts = occ_parts(symbol)
        row = self.rows(parts[0]).get(symbol)
        q = row["latestQuote"]
        return float(q["bp"]), float(q["ap"])

    def chain(self, underlying: str, *, expiry_from: str, expiry_to: str, strike_from=None, strike_to=None) -> dict:
        self.calls += 1
        self.minute_calls.take(force=True)
        if underlying in self.dead:
            raise RuntimeError("market data HTTP 500")
        out = {}
        for sym, row in self.rows(underlying).items():
            _, expiry, _, strike = occ_parts(sym)
            if not expiry_from <= expiry <= expiry_to:
                continue
            if strike_from is not None and strike < strike_from:
                continue
            if strike_to is not None and strike > strike_to:
                continue
            out[sym] = row
        return out

    def contracts(self, symbols: Iterable[str]) -> dict:
        self.calls += 1
        out = {}
        for sym in symbols:
            rows = self.rows(occ_parts(sym)[0])
            if sym in rows:
                out[sym] = rows[sym]
        return out

    def stocks(self, symbols: Iterable[str]) -> dict:
        self.calls += 1
        t = self.clock()
        return {s: {"latestTrade": {"p": self.spot if s == "SPY" else 400.0, "t": iso(t - 2)},
                    "latestQuote": {"bp": self.spot - 0.01, "ap": self.spot + 0.01, "t": iso(t - 1)}} for s in symbols}

    def bars(self, symbols: Iterable[str], *, timeframe: str, start: str, end: str | None = None) -> dict:
        return {s: [{"o": 590.0 + i, "h": 595.0 + i, "l": 588.0 + i, "c": 592.0 + i, "t": f"2026-09-{i + 1:02d}T04:00:00Z"}
                    for i in range(10)] for s in symbols}


class Venue:
    """An Alpaca account as the gateway shows it (orders, positions, activities), in memory. `fill` decides what a
    multi-leg order does when it arrives and at each read: "natural" fills whole when its limit meets the legs'
    natural, "none" rests, "partial" fills one structure a read, "uneven" fills the first leg only."""

    def __init__(self, market: Market, *, venue: str = "alpaca", equity: str = "5481.65", last_equity: str | None = None,
                 clock: Clock | None = None):
        self.market, self.venue = market, venue
        self.clock = clock or market.clock
        self.equity = Decimal(equity)
        self.last_equity = Decimal(last_equity or equity)
        self.bp = Decimal(equity)
        self.book: list[dict] = []
        self.held: dict[str, Decimal] = {}
        self.extra_positions: list[dict] = [{"symbol": "LTCUSD", "asset_class": "crypto", "qty": "0.000373062",
                                             "qty_available": "0.000373062", "side": "long"}]
        self.activity_rows: list[dict] = []
        self.fill = "natural"
        self.submit_mode = "ok"      # ok | reject | gateway | lost | lost_absent | ratelimited
        self.sent: list[dict] = []
        self.cancels: list[str] = []
        self.states_at_submit: list[Any] = []
        self.on_submit: Callable[[dict], Any] | None = None
        self.rate = Rate(150)
        self.real = venue == "alpaca"

    # ---------------------------------------------------------------- reads
    def account(self) -> dict:
        return {"equity": str(self.equity), "last_equity": str(self.last_equity), "options_buying_power": str(self.bp),
                "buying_power": str(self.bp), "cash": str(self.equity), "multiplier": "1", "options_trading_level": 3}

    def positions_rows(self) -> list[dict]:
        rows = []
        for sym, qty in sorted(self.held.items()):
            if qty == 0:
                continue
            rows.append({"symbol": sym, "asset_class": "us_option" if occ_parts(sym) else "us_equity", "qty": str(qty),
                         "qty_available": str(qty), "side": "long" if qty > 0 else "short"})
        return rows + [dict(r) for r in self.extra_positions]

    def positions(self) -> list[dict]:
        self._advance()
        return self.positions_rows()

    def orders_rows(self) -> list[dict]:
        return [self._public(o) for o in self.book]

    def orders(self, *, status: str = "all", after: str | None = None, limit: int = 500) -> list[dict]:
        self._advance()
        rows = self.orders_rows()
        if status == "open":
            rows = [r for r in rows if r["status"] in ("new", "accepted", "partially_filled")]
        return rows

    def order_by_client_id(self, client_order_id: str) -> dict | None:
        for o in self.book:
            if o["client_order_id"] == client_order_id:
                return self._public(o)
        return None

    def activities(self, types, *, after=None) -> list[dict]:
        return [dict(r) for r in self.activity_rows if r["activity_type"] in set(types)]

    # ---------------------------------------------------------------- writes
    def submit(self, body: Mapping[str, Any], *, exit: bool) -> Submitted:
        body = dict(body)
        self.sent.append(body)
        if self.on_submit is not None:
            self.on_submit(body)
        if self.submit_mode == "reject":
            return Submitted(False, {"code": 40310000, "message": "potential wash trade detected"},
                             "HTTP 403 potential wash trade detected", status=403)
        if self.submit_mode == "gateway":
            return Submitted(False, {"error": "Order maximum loss exceeds the per-order cap", "cap": "order"},
                             "HTTP 403 Order maximum loss exceeds the per-order cap", status=403)
        if self.submit_mode == "ratelimited":
            return Submitted(False, None, "rate", sent=False)
        order = self._create(body)
        if self.submit_mode == "lost":
            return Submitted(False, None, "no answer: timed out", unknown=True)
        if self.submit_mode == "lost_absent":
            self.book.remove(order)
            return Submitted(False, None, "no answer: timed out", unknown=True)
        self._try_fill(order)
        return Submitted(True, self._public(order), "", status=200)

    cancel_delay = 0.0   # seconds a cancel shows as pending_cancel (still working) before it is done

    def cancel(self, venue_id: str) -> tuple[bool, str]:
        self.cancels.append(venue_id)
        for o in self.book:
            if o["id"] == venue_id and o["status"] in ("new", "accepted", "partially_filled"):
                if self.cancel_delay:
                    o["status"], o["_cancel_at"] = "pending_cancel", self.clock() + self.cancel_delay
                else:
                    o["status"] = "canceled"
                return True, ""
        return False, "HTTP 422 order is not cancelable"

    # ---------------------------------------------------------------- the venue's side
    def _create(self, body: dict) -> dict:
        legs = body.get("legs")
        order = {"id": str(uuid.uuid4()), "client_order_id": body.get("client_order_id"), "status": "new",
                 "order_class": "mleg" if legs else "simple", "qty": body["qty"], "filled_qty": "0",
                 "limit_price": body.get("limit_price"), "type": body.get("type"), "symbol": body.get("symbol", ""),
                 "side": body.get("side", ""), "time_in_force": body.get("time_in_force"), "_body": body,
                 "legs": [{"id": str(uuid.uuid4()), "symbol": l["symbol"], "side": l["side"], "position_intent": l["position_intent"],
                           "ratio_qty": l["ratio_qty"], "qty": str(int(body["qty"]) * int(l["ratio_qty"])), "filled_qty": "0",
                           "filled_avg_price": None, "status": "new"} for l in legs or []]}
        self.book.append(order)
        return order

    def _advance(self) -> None:
        for o in self.book:
            if o["status"] == "pending_cancel":
                if self.clock() >= o["_cancel_at"]:
                    o["status"] = "canceled"
            elif o["status"] in ("new", "accepted", "partially_filled"):
                self._try_fill(o)

    def _natural(self, order: dict) -> tuple[float, list[float]]:
        prices = []
        value = 0.0
        opening = order["legs"][0]["position_intent"].endswith("open")
        for leg in order["legs"]:
            bid, ask = self.market.quote(leg["symbol"])
            buying = leg["side"] == "buy"
            price = ask if buying else bid
            prices.append(price)
            role = 1 if leg["position_intent"] in ("buy_to_open", "sell_to_close") else -1
            value += role * int(leg["ratio_qty"]) * price
        return value, prices

    def _try_fill(self, order: dict) -> None:
        if not order["legs"] or self.fill == "none":
            if not order["legs"] and order["type"] == "market":
                order["status"] = "filled"
                order["filled_qty"] = order["qty"]
                order["filled_avg_price"] = str(self.market.spot)
                sym = order["symbol"]
                sign = Decimal(1) if order["side"] == "buy" else Decimal(-1)
                self.held[sym] = self.held.get(sym, Decimal(0)) + sign * Decimal(order["qty"])
            elif not order["legs"] and occ_parts(order["symbol"]) and self.fill != "none":
                bid, ask = self.market.quote(order["symbol"])
                limit = float(order["limit_price"])
                buying = order["side"] == "buy"
                if (buying and ask <= limit + 1e-9) or (not buying and bid >= limit - 1e-9):
                    order["status"] = "filled"
                    order["filled_qty"] = order["qty"]
                    order["filled_avg_price"] = str(ask if buying else bid)
                    sign = Decimal(1) if buying else Decimal(-1)
                    self.held[order["symbol"]] = self.held.get(order["symbol"], Decimal(0)) + sign * Decimal(order["qty"])
            return
        value, prices = self._natural(order)
        opening = order["legs"][0]["position_intent"].endswith("open")
        limit = float(order["limit_price"])
        signed = limit if opening else -limit           # the Gym's value a share
        ok = (value <= signed + 1e-9) if opening else (value >= signed - 1e-9)
        if not ok:
            return
        qty = int(order["qty"])
        done = int(order["filled_qty"])
        units = qty - done if self.fill in ("natural", "uneven") else min(qty - done, 1)
        if units <= 0:
            return
        for leg, price in zip(order["legs"], prices):
            if self.fill == "uneven" and leg is not order["legs"][0]:
                continue
            before = Decimal(leg["filled_qty"])
            add = min(Decimal(units * int(leg["ratio_qty"])), Decimal(leg["qty"]) - before)
            if add <= 0:
                continue  # a later read of an uneven order cannot fill its already-complete leg again
            old = Decimal(str(leg["filled_avg_price"] or 0))
            leg["filled_avg_price"] = str(round((old * before + Decimal(str(price)) * add) / (before + add), 4))
            leg["filled_qty"] = str(before + add)
            sign = Decimal(1) if leg["side"] == "buy" else Decimal(-1)
            self.held[leg["symbol"]] = self.held.get(leg["symbol"], Decimal(0)) + sign * add
        if self.fill == "uneven":
            order["status"] = "partially_filled"
            return
        order["filled_qty"] = str(done + units)
        order["status"] = "filled" if done + units >= qty else "partially_filled"

    @staticmethod
    def _public(o: dict) -> dict:
        return {k: (v if not isinstance(v, list) else [dict(x) for x in v]) for k, v in o.items() if not k.startswith("_")}


class Grant:
    def __init__(self, active: bool = True, capital: str = "5500"):
        self.active, self.capital = active, capital

    def current(self) -> dict:
        return {"active": self.active, "policy": {"capital_usd": self.capital}}


VERTICAL = '''
NEEDS = {"roots": ["SPY"], "dte": [0, 3], "band": 0.03, "cadence": 1, "history": 2, "start": 571, "end": 958}
PARAMS = {"hold": 3, "opens": 1, "qty": 2, "dte": 1}
STATE = {"opened": 0}

def decide(ctx):
    out = []
    for p in ctx.positions:
        if p["held_minutes"] >= ctx.params["hold"]:
            out.append({"close": p["id"], "limit": "natural", "note": "held long enough"})
    if not ctx.positions and not ctx.orders and STATE["opened"] < ctx.params["opens"]:
        STATE["opened"] += 1
        out.append({"open": "debit_vertical", "root": "SPY", "qty": ctx.params["qty"], "limit": "natural", "tag": "t",
                    "note": "a test vertical",
                    "legs": [{"side": "long", "right": "C", "dte": ctx.params["dte"], "atm": 0},
                             {"side": "short", "right": "C", "rel": 0, "offset": 1.0}]})
    return out
'''

CONDOR = '''
NEEDS = {"roots": ["SPY"], "dte": [0, 3], "band": 0.03, "cadence": 1, "history": 0, "start": 571, "end": 958}
PARAMS = {"hold": 3}
STATE = {"opened": 0}

def decide(ctx):
    if STATE["opened"] or ctx.positions or ctx.orders:
        return []
    STATE["opened"] += 1
    return [{"open": "iron_condor", "root": "SPY", "qty": 1, "limit": "natural",
             "legs": [{"side": "long", "right": "P", "rel": 1, "offset": -1.0},
                      {"side": "short", "right": "P", "dte": 1, "atm": -3},
                      {"side": "short", "right": "C", "dte": 1, "atm": 3},
                      {"side": "long", "right": "C", "rel": 2, "offset": 1.0}]}]
'''


def family(name: str, code: str, *, band: str = "probe", structure: str = "debit_vertical", holdout: bool = True,
           validation: bool = True, version: int = 1, typical: Any = 50.0, params: Mapping[str, Any] | None = None) -> dict:
    return {"family": name, "band": band, "structure": structure, "roots": ["SPY"], "holdout_passed": holdout,
            "validation_passed": validation, "version": version, "code": code, "params": dict(params or {}),
            "run_sha": f"sha-{name}-{version}", "typical_max_loss_usd": typical, "seed_era": True,
            "real_promoted_at": at(MONDAY - dt.timedelta(days=7), 9, 0) if band in ("probe", "sized") else None,
            "forward": {"trades": 0, "negative": False}}
