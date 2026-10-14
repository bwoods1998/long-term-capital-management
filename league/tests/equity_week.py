"""THE SEATED ETF PROGRAMS' WEEK, ORDER FOR ORDER: the harness of league/tests/test_equity_etf_orders.py.

The REAL `EquityBook`, schedule, sizing, `StockPaperProof` and decider kind, wired as league/live/equity_hook.py
`build_book` wires them, over a FAKE venue (two accounts: the real one and the practice one) and a scripted market of
INVENTED prices: six seated share programs trade the week of Monday Oct 12, 2026 (the lane's first real session), the
normal way and every way the rehearsal of that Monday found a buy or a sale can go wrong. Nothing here reaches the
House, a broker, the gateway or a secret, and no price is a market's.

WHY IT IS IN THE TREE. Release E4 put the panel kind into the live book (league/equity/live.py, package H). The ship
check's warning was that one of its rules (the spec's decision 27, B8) changed the entry of EVERY instance. The
captain's ruling: a share program's live behaviour is main's, order for order, at every position of the panel lane's
switch. `record(tree)` ran these scenarios on main 8ab31e32 (the release the six programs trade their first session
under: the seat rule "activity-1-free", the exit wait's end, the re-based twin) and kept what the book did
(league/tests/fixtures/equity_etf_orders.json); the test runs them on the tree it is in and holds every intent, order,
fill, lot, instance row, seat plan, alert, record and minute's answer to that file, and for the scenarios that run
the forward nights every twin row, re-base and reading. A LATER CHANGE OF THE ETF PATH FAILS IT: when the change is
meant, record again on the new tree and say in the commit what moved.

    House                the wiring, in memory: `reader` "memory" (`MemoryEquityFamilies`, as the rehearsal ran) or
                         "store" (the REAL `EquityFamilies` over a real `SwarmStore` of six seated ETF families; `panel`:
                         the lane's switch in the root's swarm.json, and at "train" a panel family in Train research)
    Market, Venue        quotes by the clock; an Alpaca account's shapes, a fill `fill_delay` seconds after the POST
    SCENARIOS            name -> {kind, setup, ...}: "monday" (the open window), "next" (and Tuesday's), "week"
                         (five sessions), "fortnight" (thirteen sessions: the seat rule's idle test needs ten), "twin"
                         (eight sessions on a synthetic store's bars, with the forward record's night after each:
                         league/ops/forward_twins.py `finish`, as the rehearsal's phase harness ran it)
    run, snapshot        one scenario on this tree; everything it left, as plain JSON
    record               every scenario of a tree, for the fixture:
                             python league/tests/equity_week.py --tree <a clean tree's root> --out <file>

Every id is counted, never drawn (the venue's order ids, the state's nonce), so two runs of one tree are equal to the
byte. Standard library only, but for a "twin" scenario's synthetic store (numpy, as the Gym's)."""

from __future__ import annotations

import sys

if __name__ == "__main__" and "--tree" in sys.argv:  # (the recorder: the tree under record, before any league import)
    sys.dont_write_bytecode = True
    sys.path.insert(0, sys.argv[sys.argv.index("--tree") + 1])

import datetime as dt  # noqa: E402
import hashlib  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import shutil  # noqa: E402
import tempfile  # noqa: E402
from decimal import Decimal as D  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import Any, Callable  # noqa: E402
from zoneinfo import ZoneInfo  # noqa: E402

from league.equity import config  # noqa: E402
from league.equity import live as L  # noqa: E402
from league.equity import schedule as S  # noqa: E402
from league.equity.families import MemoryEquityFamilies  # noqa: E402
from league.live import money as M  # noqa: E402
from league.live.decider import InlineDecider  # noqa: E402
from league.live.paper import STOCK_BUY_KEY, STOCK_KEY, STOCK_SELL_KEY, StockPaperProof  # noqa: E402
from league.live.state import LiveState  # noqa: E402
from league.live.venue import Submitted  # noqa: E402

NY = ZoneInfo("America/New_York")
FRIDAY, MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY2 = (dt.date(2026, 10, d) for d in (9, 12, 13, 14, 15, 16))
#: The fortnight's last session (thirteen sessions from Monday Oct 12) and the twin scenarios' (eight).
FORTNIGHT_END, TWIN_END = dt.date(2026, 10, 28), dt.date(2026, 10, 21)
#: The synthetic store a "twin" scenario's market and replay twins read (league/equity/synth.py; invented, seeded).
SYMBOLS = ("SPY", "QQQ", "IWM", "DIA")
STORE_START, STORE_END, STORE_SEED = dt.date(2026, 6, 1), dt.date(2026, 12, 18), 11
#: The forward record's settings in a "twin" scenario (no minute bars exist here: the fill columns are off).
FORWARD = {"elane": {"forward": {"mode": "record", "fill_minutes": False}}}
WORKING = ("new", "accepted", "partially_filled")
INF = float("inf")
#: The panel lane's switch positions the comparison is held at ("" stands for no key at all: policy.json's "off").
SWITCHES = ("", "off", "train")


def at(day: dt.date, hh: int, mm: int, ss: float = 3) -> float:
    return dt.datetime(day.year, day.month, day.day, hh, mm, tzinfo=NY).timestamp() + float(ss)


def said(t: float) -> str:
    """An epoch as the fixture writes it: the New York day and second."""
    return dt.datetime.fromtimestamp(t, NY).strftime("%m-%d %H:%M:%S")


def iso(t: float) -> str:
    return dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f") + "123Z"


def stamp(day: dt.date) -> str:
    """An Alpaca 1Day bar's `t`: the session's New York midnight in UTC."""
    return dt.datetime.combine(day, dt.time(0), NY).astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Clock:
    def __init__(self, t: float):
        self.t = float(t)

    def __call__(self) -> float:
        return self.t

    def set(self, t: float) -> None:
        self.t = float(t)


class Market:
    """Invented quotes by the clock. `days[(day, symbol)] = {"open": o, "close": c}`; `move(day, symbol, seconds since
    the open) -> basis points` over the official open until ten minutes before the close, then the official close;
    `spread_bp(day, symbol, seconds) -> full spread in bp` (default twice the lane's half-spread); `stale(day, symbol,
    seconds) -> a quote stamp (epoch) or None` (None: a second ago); `dark(day, seconds)`: the snapshot read raises."""

    def __init__(self, clock: Clock):
        self.clock = clock
        self.days: dict[tuple[dt.date, str], dict[str, float]] = {}
        self.move: Callable[[dt.date, str, float], float] = lambda day, symbol, secs: 0.0
        self.spread_bp: Callable[[dt.date, str, float], float] | None = None
        self.stale: Callable[[dt.date, str, float], float | None] = lambda day, symbol, secs: None
        self.dark: Callable[[dt.date, float], bool] = lambda day, secs: False
        self.bar_rows: dict[str, dict[str, list[dict]]] = {"raw": {}, "all": {}}
        self.default = {"SPY": 600.0, "QQQ": 500.0, "IWM": 220.0, "DIA": 450.0}

    def official(self, day: dt.date, symbol: str) -> dict[str, float]:
        row = self.days.get((day, symbol))
        if row is None:
            px = self.default.get(symbol, 100.0)
            row = {"open": px, "close": px}
        return row

    def mid_at(self, symbol: str, t: float) -> D:
        day = S.ny_day(t)
        m = S.moments(day)
        row = self.official(day, symbol)
        if m is None or t < m.open_at:
            return D(str(row["open"]))
        if t >= m.close_at - 600:
            return D(str(row["close"]))
        bp = float(self.move(day, symbol, t - m.open_at))
        return D(str(row["open"])) * (D(1) + D(str(bp)) / D(10000))

    def quote_at(self, symbol: str, t: float) -> tuple[D, D]:
        day = S.ny_day(t)
        m = S.moments(day)
        secs = t - m.open_at if m is not None else 0.0
        mid = self.mid_at(symbol, t)
        full = D(str(self.spread_bp(day, symbol, secs))) if self.spread_bp is not None else \
            D(str(2 * config.HALF_SPREAD_BP[symbol]))
        half = full / D(20000)
        bid = (mid * (1 - half)).quantize(D("0.01"))
        ask = (mid * (1 + half)).quantize(D("0.01"))
        return bid, max(ask, bid)

    def quote(self, symbol: str) -> tuple[D, D]:
        return self.quote_at(symbol, self.clock())

    def stocks(self, symbols):
        now = self.clock()
        day = S.ny_day(now)
        m = S.moments(day)
        secs = now - m.open_at if m is not None else 0.0
        if self.dark(day, secs):
            raise RuntimeError("stock snapshots: HTTP 503")
        out = {}
        for s in symbols:
            bid, ask = self.quote_at(s, now)
            t = self.stale(day, s, secs)
            t = iso(now - 1 if t is None else t)
            out[s] = {"latestQuote": {"bp": float(bid), "ap": float(ask), "t": t},
                      "latestTrade": {"p": float((bid + ask) / 2), "t": t}}
        return out

    def bars(self, symbols, *, timeframe, start, end=None, adjustment="raw"):
        return {s: [dict(r) for r in self.bar_rows[adjustment].get(s, [])
                    if start <= r["t"][:10] and (end is None or r["t"][:10] < end)] for s in symbols}

    def make_bars(self, symbol: str, sessions: list[dt.date], opens: list[float], closes: list[float]) -> None:
        raw = []
        for day, o, c in zip(sessions, opens, closes):
            raw.append({"t": stamp(day), "o": round(o, 4), "h": round(max(o, c) * 1.002, 4),
                        "l": round(min(o, c) * 0.998, 4), "c": round(c, 4), "v": 25_000_000.0})
            self.days[(day, symbol)] = {"open": round(o, 4), "close": round(c, 4)}
        self.bar_rows["raw"][symbol] = raw
        self.bar_rows["all"][symbol] = [dict(r) for r in raw]


class Venue:
    """One Alpaca account as the gateway shows it (the shapes of league/tests/test_equity_book.py's Venue), with time:
    `fill_delay(order) -> seconds` from the POST to the fill (INF: it rests for good; the fill is at the quote of that
    moment when the limit is marketable then, else at the first later reading whose quote crosses it); `positions_delay`
    and `activity_delay`: seconds positions() and the FILL activities trail a fill; `script(body) -> None | "rate" |
    "reject" | "gateway" | "retry_cap" | "lost" | "lost_absent"` decides each POST's answer; `fail_reads(what) -> bool`.
    Its ids are counted (`<name>-<n>`)."""

    def __init__(self, market: Market, clock: Clock, *, cash: str = "2229", name: str = "alpaca"):
        self.market, self.clock, self.name = market, clock, name
        self.cash = D(cash)
        self.held: dict[str, D] = {}
        self.moves: list[tuple[float, str, D]] = []
        self.book: list[dict] = []
        self.sent: list[dict] = []
        self.sent_at: list[float] = []
        self.cancels: list[str] = []
        self.cancel_at: list[float] = []
        self.fill_delay: Callable[[dict], float] = lambda order: 0.4
        self.positions_delay = 0.0
        self.activity_delay = 0.0
        self.script: Callable[[dict], str | None] = lambda body: None
        self.fail_reads: Callable[[str], bool] = lambda what: False
        self.activity_rows: list[dict] = []
        self.fills: list[dict] = []
        self.n = 0

    def _id(self, kind: str) -> str:
        self.n += 1
        return f"{self.name}-{kind}-{self.n:05d}"

    # ---------------------------------------------------------------- reads
    def account(self) -> dict:
        if self.fail_reads("account"):
            raise RuntimeError(f"{self.name} account: HTTP 503")
        self._advance()
        value = sum((q * sum(self.market.quote(s)) / 2 for s, q in self.held.items()), D(0))
        return {"equity": str(self.cash + value), "last_equity": str(self.cash + value), "cash": str(self.cash),
                "short_market_value": "0", "buying_power": str(self.cash), "multiplier": "1"}

    def positions(self) -> list[dict]:
        if self.fail_reads("positions"):
            raise RuntimeError(f"{self.name} positions: HTTP 503")
        self._advance()
        shown: dict[str, D] = {}
        cut = self.clock() - self.positions_delay
        for t, symbol, dq in self.moves:
            if t <= cut:
                shown[symbol] = shown.get(symbol, D(0)) + dq
        return [{"symbol": s, "asset_class": "us_equity", "qty": str(q), "qty_available": str(q),
                 "side": "long" if q > 0 else "short", "market_value": str(q * sum(self.market.quote(s)) / 2)}
                for s, q in sorted(shown.items()) if q != 0]

    def orders(self, *, status="all", after=None, limit=500) -> list[dict]:
        if self.fail_reads("orders"):
            raise RuntimeError(f"{self.name} orders: HTTP 503")
        self._advance()
        rows = [self._public(o) for o in self.book]
        if status == "open":
            rows = [r for r in rows if r["status"] in WORKING + ("pending_cancel",)]
        return rows

    def order_by_client_id(self, client_order_id: str):
        if self.fail_reads("order"):
            raise RuntimeError(f"{self.name} order by client id: HTTP 503")
        self._advance()
        for o in self.book:
            if o["client_order_id"] == client_order_id:
                return self._public(o)
        return None

    def activities(self, types, *, after=None) -> list[dict]:
        if self.fail_reads("activities"):
            raise RuntimeError(f"{self.name} activities: HTTP 503")
        self._advance()
        now = self.clock()
        return [{k: v for k, v in r.items() if not k.startswith("_")} for r in self.activity_rows
                if r["activity_type"] in set(types) and r.get("_visible", 0.0) <= now]

    # ---------------------------------------------------------------- writes
    def submit(self, body, *, exit: bool) -> Submitted:
        body = dict(body)
        self.sent.append(body)
        self.sent_at.append(self.clock())
        mode = self.script(body)
        if mode == "rate":
            return Submitted(False, None, f"{self.name}: 150 requests this minute already", sent=False)
        if mode == "reject":
            return Submitted(False, {"code": 40310000, "message": "invented: the venue rejects the order"},
                             "HTTP 403 invented: the venue rejects the order", status=403)
        if mode == "gateway":
            return Submitted(False, {"error": "invented: a gateway cap", "cap": "stock_buys_off"},
                             "HTTP 403 invented: a gateway cap", status=403)
        if mode == "retry_cap":
            return Submitted(False, {"error": "invented: the account's positions could not be read", "cap": "positions"},
                             "HTTP 424 invented: the account's positions could not be read", status=424)
        now = self.clock()
        order = {"id": self._id("o"), "client_order_id": body["client_order_id"], "status": "accepted",
                 "symbol": body["symbol"], "side": body["side"], "qty": body["qty"], "limit_price": body["limit_price"],
                 "type": body["type"], "time_in_force": body["time_in_force"], "filled_qty": "0",
                 "filled_avg_price": None, "submitted_at": iso(now), "order_class": "simple", "legs": None,
                 "_fill_at": now + float(self.fill_delay(body)), "_tried": False}
        if mode == "lost_absent":
            return Submitted(False, None, "no answer: timed out", unknown=True)
        self.book.append(order)
        if mode == "lost":
            return Submitted(False, None, "no answer: timed out", unknown=True)
        return Submitted(True, self._public(order), "", status=200)

    def cancel(self, venue_id: str):
        self._advance()
        self.cancels.append(venue_id)
        self.cancel_at.append(self.clock())
        for o in self.book:
            if o["id"] == venue_id and o["status"] in WORKING:
                o["status"], o["canceled_at"] = "canceled", iso(self.clock())
                return True, ""
        return False, "HTTP 422 order is not cancelable"

    # ---------------------------------------------------------------- the venue's side
    def _advance(self) -> None:
        now = self.clock()
        for o in self.book:
            if o["status"] not in WORKING or now < o["_fill_at"]:
                continue
            moments = ([] if o["_tried"] else [o["_fill_at"]]) + [now]
            o["_tried"] = True
            for t in moments:
                if self._try_fill(o, t):
                    break

    def _try_fill(self, o: dict, t: float) -> bool:
        bid, ask = self.market.quote_at(o["symbol"], t)
        limit = D(o["limit_price"])
        buying = o["side"] == "buy"
        if (buying and ask > limit) or (not buying and bid < limit):
            return False
        qty, done = D(o["qty"]), D(o["filled_qty"])
        add = qty - done
        if add <= 0:
            return False
        price = ask if buying else bid
        o["filled_avg_price"] = str(price)
        o["filled_qty"] = str(done + add)
        o["status"], o["filled_at"] = "filled", iso(t)
        self.held[o["symbol"]] = self.held.get(o["symbol"], D(0)) + (add if buying else -add)
        self.moves.append((t, o["symbol"], add if buying else -add))
        self.cash += -price * add if buying else price * add
        self.fills.append({"t": t, "symbol": o["symbol"], "side": o["side"], "qty": add, "px": price,
                           "cid": o["client_order_id"]})
        self.activity_rows.append({"id": self._id("a"), "activity_type": "FILL", "order_id": o["id"],
                                   "symbol": o["symbol"], "side": o["side"], "qty": str(add), "price": str(price),
                                   "transaction_time": iso(t), "date": S.ny_day(t).isoformat(),
                                   "_visible": t + self.activity_delay})
        return True

    @staticmethod
    def _public(o: dict) -> dict:
        return {k: v for k, v in o.items() if not k.startswith("_")}


class OptionsBook:
    """The options `RealBook` at the interface the equity book reads (its tests' stub): nothing working by default."""

    def __init__(self):
        self.busy_symbols: set[str] = set()
        self.count = 0
        self.reserve_n = 0
        self.reserved_usd = 0.0
        self.book_loss = D(0)

    def busy(self):
        return set(self.busy_symbols)

    def count_today(self, day):
        return self.count

    def exit_reserve(self):
        return self.reserve_n

    def reserved(self):
        return self.reserved_usd

    def exposure(self, family, *, day, week_start):
        return M.Exposure(book_loss=self.book_loss)


# ----------------------------------------------------------------------------------------------- the invented programs
#: One ETF at share 0.4, max hold 3 sessions (the House exits it), bought again the session after.
HOLD3 = '''NEEDS = {"symbols": ["QQQ"], "history": 5, "max_hold_sessions": 3}
PARAMS = {}


def decide(ctx):
    if ctx.positions or ctx.orders:
        return []
    return [{"buy": "QQQ", "share": 0.4, "at": "open", "tag": "hold3"}]
'''
#: SPY 0.2 and QQQ 0.2 at the open when flat, each lot sold at the next open.
RANGE = '''NEEDS = {"symbols": ["SPY", "QQQ"], "history": 5, "max_hold_sessions": 5}
PARAMS = {}


def decide(ctx):
    if ctx.positions:
        return [{"sell": p["id"], "at": "open", "tag": "range-compress"} for p in ctx.positions]
    return [{"buy": "SPY", "share": 0.2, "at": "open", "tag": "range-compress"},
            {"buy": "QQQ", "share": 0.2, "at": "open", "tag": "range-compress"}]
'''
#: An overnight program whose first buy is decided at the second close it is asked: bought at a close, sold at the
#: next open.
OVERNIGHT = '''NEEDS = {"symbols": ["QQQ"], "history": 5, "max_hold_sessions": 2}
PARAMS = {}
STATE = {"n": 0}


def decide(ctx):
    STATE["n"] += 1
    out = [{"sell": p["id"], "at": "open", "tag": "overnight"} for p in ctx.positions]
    if STATE["n"] >= 2:
        out.append({"buy": "QQQ", "share": 0.5, "at": "close", "tag": "overnight"})
    return out
'''
#: Every session: each lot sold and 0.3 of the sleeve of one ETF bought again in the SAME window (`{at}`: "open" or
#: "close"). A sale and a buy of ONE program in one window, the buy cut by the sleeve's own cap on one ETF while the
#: lot is still held: the case the panel kind's rule B8 holds a cut buy for, and the book's own kind never does.
ROLL = '''NEEDS = {"symbols": ["IWM"], "history": 5, "max_hold_sessions": 5}
PARAMS = {}


def decide(ctx):
    out = [{"sell": p["id"], "at": "{at}", "tag": "roll"} for p in ctx.positions]
    out.append({"buy": "IWM", "share": 0.3, "at": "{at}", "tag": "roll"})
    return out
'''
#: Two ETFs at 0.35 of the sleeve each, sold the next session for ONE at 0.5, and back: the new buy is cut by the
#: sleeve's own cash while the lots it replaces are still held, and it names another symbol than its own sales (so
#: "one order a symbol" does not hold it). `{at}` as `ROLL`'s.
ROTATE = '''NEEDS = {"symbols": ["SPY", "IWM", "DIA"], "history": 5, "max_hold_sessions": 5}
PARAMS = {}


def decide(ctx):
    held = sorted(p["symbol"] for p in ctx.positions)
    out = [{"sell": p["id"], "at": "{at}", "tag": "rotate"} for p in ctx.positions]
    if held == ["DIA", "IWM"]:
        out.append({"buy": "SPY", "share": 0.5, "at": "{at}", "tag": "rotate"})
    elif not ctx.orders:
        out.append({"buy": "IWM", "share": 0.35, "at": "{at}", "tag": "rotate"})
        out.append({"buy": "DIA", "share": 0.35, "at": "{at}", "tag": "rotate"})
    return out
'''
#: A seated program that asks for nothing.
IDLE = '''NEEDS = {"symbols": ["SPY", "QQQ", "IWM", "DIA"], "history": 5, "max_hold_sessions": 5}
PARAMS = {}


def decide(ctx):
    return []
'''
#: A PASSED PROGRAM WAITING FOR A SEAT (THE SEAT RULE): `{symbol}` at 0.3 of the sleeve at the open when flat, each lot
#: sold at the next open.
WAIT = '''NEEDS = {"symbols": ["{symbol}"], "history": 5, "max_hold_sessions": 3}
PARAMS = {}


def decide(ctx):
    if ctx.positions:
        return [{"sell": p["id"], "at": "open", "tag": "wait"} for p in ctx.positions]
    return [{"buy": "{symbol}", "share": 0.3, "at": "open", "tag": "wait"}]
'''
#: An invented panel program for the swarm's store at "train" (never run here: it is in Train research, band "gym").
PANEL = '''NEEDS = {"panel": "sp500", "history": 30, "max_names": 5, "rebalance": "weekly", "weekday": 0}
PARAMS = {}


def decide(ctx):
    return []
'''


def family_row(family: str, code: str, *, lane: str = "beta", seeded: bool = False, symbols=("QQQ",),
               band: str = "probe", k: tuple[int, int] | None = None) -> dict:
    """A seated program's row as the swarm's reader gives it (a scenario's `candidates` are put back at "candidate":
    passed their look, seated by the book's own band sync at the next decide). `k` (THE SEAT RULE's scenarios): the
    row carries what the reader's `queued` rows carry, `passed_at` (every look passed at the House's start) and
    `seat_activity` (K's two counts: `k` Validation close days, and `k[1]` Train-era ones in 1000 sessions)."""
    row = {"family": family, "band": band, "lane": lane, "structure": "etf", "symbols": list(symbols),
           "seeded": seeded, "holdout_passed": True, "validation_passed": True, "version": 1, "code": code,
           "params": {}, "run_sha": f"run-{family}-1", "validation_r_sd": None}
    if k is not None:
        row.update(passed_at=at(FRIDAY, 16, 0), seat_activity=activity(*k))
    return row


def activity(validation_days: int, train_days: int) -> dict:
    """K's two counts as a family's state keeps them (league/swarm/elane.py `SEAT_KEY`), invented."""
    return {"validation": {"close_days": int(validation_days), "sessions": 250},
            "train": {"close_days": int(train_days), "sessions": 1000}}


def six_programs(*, a_first: bool = True, roll: str = "", rotate: str = "") -> list[dict]:
    """Six seated share programs at Probe: A (`HOLD3`) and B (`RANGE`) plan Monday's three buys. `a_first` names them
    so A's instance id sorts before B's (the decide asks instances in id order, so its intents get the lower iids).
    `roll`, `rotate` ("open" | "close"): the fifth program sells and buys again in that window of every session
    (`ROLL`), and the sixth rotates between ETFs in it (`ROTATE`), where each is idle otherwise."""
    a = "bred-a-hold3" if a_first else "bred-z-hold3"
    everything = ("SPY", "QQQ", "IWM", "DIA")
    return [family_row(a, HOLD3, symbols=("QQQ",)),
            family_row("bred-b-range", RANGE, symbols=("SPY", "QQQ")),
            family_row("seed-overnight-qqq", OVERNIGHT, seeded=True, symbols=("QQQ",)),
            family_row("seed-reversal-index", IDLE, seeded=True, symbols=everything),
            family_row("bred-c-roll", ROLL.replace("{at}", roll), symbols=("IWM",)) if roll
            else family_row("bred-c-idle", IDLE, symbols=everything),
            family_row("bred-d-rotate", ROTATE.replace("{at}", rotate), symbols=("SPY", "IWM", "DIA")) if rotate
            else family_row("bred-d-idle", IDLE, symbols=everything)]


def ranked_programs(waiting: int = 0) -> list[dict]:
    """THE SEAT RULE's programs: the six seated ones, each with K's counts (the three that never ask are the idle
    seats: the lowest K yields first, `bred-d-idle`, then the seeded `seed-reversal-index`, then `bred-c-idle`), and
    `waiting` passed Candidates behind them (`bred-e-wait` ranks before `bred-f-wait`)."""
    everything = ("SPY", "QQQ", "IWM", "DIA")
    rows = [family_row("bred-a-hold3", HOLD3, symbols=("QQQ",), k=(80, 300)),
            family_row("bred-b-range", RANGE, symbols=("SPY", "QQQ"), k=(120, 500)),
            family_row("seed-overnight-qqq", OVERNIGHT, seeded=True, symbols=("QQQ",), k=(100, 420)),
            family_row("seed-reversal-index", IDLE, seeded=True, symbols=everything, k=(25, 110)),
            family_row("bred-c-idle", IDLE, symbols=everything, k=(40, 180)),
            family_row("bred-d-idle", IDLE, symbols=everything, k=(12, 60))]
    extra = [family_row("bred-e-wait", WAIT.replace("{symbol}", "DIA"), symbols=("DIA",), band="candidate", k=(60, 250)),
             family_row("bred-f-wait", WAIT.replace("{symbol}", "IWM"), symbols=("IWM",), band="candidate", k=(30, 130))]
    return rows + extra[:waiting]


def sessions_from(first: dt.date, n: int) -> list[dt.date]:
    out, d = [], first
    while len(out) < n:
        if S.is_session(d):
            out.append(d)
        d += dt.timedelta(days=1)
    return out


def sessions_before(last: dt.date, n: int) -> list[dt.date]:
    out, d = [], last
    while len(out) < n:
        if S.is_session(d):
            out.append(d)
        d -= dt.timedelta(days=1)
    return sorted(out)


def invented_week(market: Market, *, through: dt.date = FRIDAY2, history: int = 30) -> None:
    """Invented daily bars for SPY, QQQ, IWM and DIA: `history` sessions through Friday Oct 9, then the sessions
    through `through`; a slow drift, no market's prices."""
    days = sessions_before(FRIDAY, history) + sessions_from(MONDAY, S.sessions_between(FRIDAY, through))
    for symbol, base in (("SPY", 600.0), ("QQQ", 500.0), ("IWM", 220.0), ("DIA", 450.0)):
        opens, closes = [], []
        px = base * 0.97
        for i, _ in enumerate(days):
            o = px * (1.0 + 0.0004 * math.sin(i * 1.7 + len(symbol)))
            c = o * (1.0 + 0.0011 * math.cos(i * 0.9 + len(symbol)))
            opens.append(o)
            closes.append(c)
            px = c
        market.make_bars(symbol, days, opens, closes)


# ------------------------------------------------------------------------------------------------------------ the House
def store_families(root: Path, programs: list[dict], clock: Clock, panel: str, *, forced: tuple[str, ...] = ()) -> Any:
    """THE REAL READER: a `SwarmStore` at `root` holding `programs` as ETF families seated at Probe (each with its
    version's file and a band proof under the equity identity of the tree that runs this), and the `EquityFamilies`
    the House's book reads them through. `panel`: the panel lane's switch as the root's swarm.json says it ("": no
    key); at "train" the store also holds one panel family in Train research, as the lane bears them. `forced`
    (bands): WHAT STEP ONE CANNOT MAKE, put there by hand: one panel family in each of these bands, passed and with
    a band proof that is current under the xs identity, so that the lane's mode alone decides whether the book ever
    sees it (league/tests/test_equity_panel_on_main.py)."""
    from league.equity.families import EquityFamilies
    from league.swarm.evaluator import equity_identity
    from league.swarm.gate import run_sha
    from league.swarm.store import SwarmStore

    layer: dict[str, Any] = {"elane": {"mode": "gate"}}
    if panel:
        layer["elane"]["panel"] = {"mode": panel}
    (root / "swarm.json").write_text(json.dumps(layer), encoding="utf-8")
    store = SwarmStore(root, clock=clock)
    try:
        identity = equity_identity()
        for row in programs:
            fam = store.add_family({"id": row["family"], "mechanism": f"An invented mechanism of {row['family']}.",
                                    "structure": "etf", "roots": list(row["symbols"]), "lane": row["lane"],
                                    "symbols": list(row["symbols"]), **({"seeded": True} if row["seeded"] else {})},
                                   origin="seed" if row["seeded"] else "architect")
            version = store.add_version(fam["id"], row["code"], {}, author="architect:invented")
            sha = run_sha(store.version(fam["id"], version["n"]))
            store.update_family(fam["id"], best_version=version["n"], validated_version=version["n"])
            store.set_state(fam["id"], banded_version=version["n"], banded_at=clock(), gate="pass", holdout_passed=True,
                            banded_evaluator={"engine": identity["engine"], "equity_sha256": identity["equity"],
                                              "run_sha": sha})
            if row.get("seat_activity") is not None:
                # K's two counts beside the look (league/swarm/elane.py `SEAT_KEY`: this version's, this run sha's).
                store.set_state(fam["id"], elane_seat={"version": version["n"], "run_sha": sha, "floor": "0.25",
                                                       **row["seat_activity"], "at": clock(), "source": "invented"})
            store.set_band(fam["id"], "candidate", reason="an invented look")
            if row["band"] != "candidate":
                store.set_band(fam["id"], row["band"], reason="an invented seat")
        if panel == "train":
            fam = store.add_family({"id": "xs-in-train", "mechanism": "An invented cross-sectional mechanism.",
                                    "structure": "panel", "roots": [], "lane": "equity", "agenda": "xs_reversal",
                                    "panel": "sp500", "max_names": 5, "rebalance": "weekly", "weekday": 0,
                                    "e2_route": "invented-route", "hidden_year": None, "gid": "g0"}, origin="architect")
            store.add_version(fam["id"], PANEL, {}, author="architect:invented")
            store.set_state(fam["id"], elane_xs={"status": "researching", "versions": {}})
        for band in forced:
            from league.xs import XS_ENGINE_VERSION
            from league.xs.identity import xs_fingerprint

            fam = store.add_family({"id": f"xs-forced-{band}", "mechanism": "An invented cross-sectional mechanism.",
                                    "structure": "panel", "roots": [], "lane": "equity", "agenda": "xs_reversal",
                                    "panel": "sp500", "max_names": 5, "rebalance": "weekly", "weekday": 0,
                                    "e2_route": "invented-route", "hidden_year": None, "gid": "g0"}, origin="architect")
            version = store.add_version(fam["id"], PANEL, {}, author="architect:invented")
            sha = run_sha(store.version(fam["id"], version["n"]))
            store.update_family(fam["id"], best_version=version["n"], validated_version=version["n"])
            store.set_state(fam["id"], banded_version=version["n"], banded_at=clock(), gate="pass", holdout_passed=True,
                            banded_evaluator={"engine": XS_ENGINE_VERSION, "xs_sha256": str(xs_fingerprint()),
                                              "run_sha": sha})
            store.set_band(fam["id"], "candidate", reason="an invented look")
            if band != "candidate":
                store.set_band(fam["id"], band, reason="an invented seat")
    finally:
        store.close()
    return EquityFamilies(root)


class House:
    """The House's equity lane as `equity_hook.build_book` wires it: the REAL `EquityBook` over the REAL
    `StockPaperProof` (the practice account `paper`), the money table in force (`Table.from_constitution()`), the real
    decider kind (`InlineDecider`: the child's own code in this process) and the swarm's rows through `reader`
    ("memory" | "store": `store_families`). `lag`: seconds into the House minute the equity tick runs (it follows the
    options minute)."""

    def __init__(self, root: Path, programs: list[dict], *, cash: str = "2229", grant: str = "2229", lag: float = 8.0,
                 reader: str = "memory", panel: str = "", forced: tuple[str, ...] = ()):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.clock = Clock(at(FRIDAY, 16, 0))
        self.market = Market(self.clock)
        self.venue = Venue(self.market, self.clock, cash=cash, name="alpaca")
        self.paper = Venue(self.market, self.clock, cash="100000", name="paper")
        self.starts = 0
        self.state = self.new_state()
        self.table = M.Table.from_constitution()
        self.families = (store_families(self.root, programs, self.clock, panel, forced=forced) if reader == "store"
                         else MemoryEquityFamilies(programs))
        self.decider = InlineDecider()
        self.events: list[tuple[float, str, dict]] = []
        self.alerts: list[tuple[float, str, str]] = []
        self.grant = D(grant)
        self.lag = float(lag)
        self.blocked: str | None = None
        self.kill = False
        self.options = OptionsBook()
        self.proof = self.new_proof()
        self.book = self.new_book()
        self.ticks: list[tuple[float, dict]] = []
        #: THE FORWARD RECORD beside the book (`Forward`; a "twin" scenario's), else None.
        self.forward: Forward | None = None

    def _record(self, kind, payload, agent=None):
        self.events.append((self.clock(), kind, dict(payload)))

    def _alert(self, level, text):
        self.alerts.append((self.clock(), level, text))

    def new_state(self) -> LiveState:
        """The live state opened by a starting process: its nonce counted here, where the House draws it."""
        state = LiveState(self.root / "live.sqlite", clock=self.clock)
        self.starts += 1
        state.nonce = f"{self.starts:08x}"
        return state

    def new_proof(self) -> StockPaperProof:
        return StockPaperProof(self.state, self.paper, record=self._record, clock=self.clock, alert=self._alert)

    def new_book(self) -> L.EquityBook:
        return L.EquityBook(self.state, self.venue, self.market, self.table, self.families, decider=self.decider,
                            stock_proof=self.proof, sizing_equity=self.sizing_equity, options_book=self.options,
                            root=self.root, clock=self.clock, record=self._record, alert=self._alert)

    def restart(self) -> None:
        """The House process ends and starts again on the same state file (a new nonce, book, proof and decider)."""
        self.state.close()
        self.state = self.new_state()
        self.proof = self.new_proof()
        self.decider = InlineDecider()
        self.book = self.new_book()

    def sizing_equity(self) -> D | None:
        try:
            return min(D(self.venue.account()["equity"]), self.grant)
        except Exception:  # noqa: BLE001
            return None

    def pass_proof(self, *, buy: bool = True, sell: bool = True) -> None:
        from league.live.paper import STOCK_BUY_WITNESSES, STOCK_WITNESSES

        if buy:
            self.state.put(STOCK_BUY_KEY, {"schema": 1, "status": "passed", **{k: True for k in STOCK_BUY_WITNESSES}})
        if sell:
            self.state.put(STOCK_SELL_KEY, {"schema": 1, "status": "passed", **{k: True for k in STOCK_WITNESSES}})

    def tick(self, day: dt.date, hh: int, mm: int) -> dict:
        """One House minute: the options path's reads at the minute's start (hh:mm:03), then the equity tick `lag`
        seconds later (the wall clock every send reads)."""
        now = at(day, hh, mm, 3)
        self.clock.set(now)
        account_row = positions = open_orders = None
        try:
            account_row = self.venue.account()
            positions = self.venue.positions()
            open_orders = self.venue.orders(status="open")
        except Exception:  # noqa: BLE001 - the options path's read failed: the book reads what it needs itself
            pass
        self.clock.set(now + self.lag)
        out = self.book.tick(now, account_row=account_row, positions=positions, open_orders=open_orders,
                             real_block=lambda opening=True: self.blocked, killed=lambda: self.kill)
        self.ticks.append((now, out))
        return out

    def close(self) -> None:
        if self.forward is not None:
            self.forward.close()
        self.state.close()
        store = getattr(self.families, "_store", None)
        if store is not None:
            store.close()


class Forward:
    """THE FORWARD RECORD BESIDE THE HOUSE (a "twin" scenario; the rehearsal's phase harness, on the tree's own code):
    a synthetic store at the root, whose invented bars are the market the book trades AND the bars its replay twins
    read; every program in the real registry (`forward_db.append_registry`, reason "live"); each morning the equity
    twins of the closed lots (league/ops/twins.py `equity_round`, into the swarm's store); each evening the night's
    twins (league/ops/forward_twins.py `finish` over the real `forward_shadow.Shadow`: E1's engine in the decider's
    equity kind). `left()` is what the forward store holds at the end."""

    def __init__(self, house: House, programs: list[dict]):
        from league.equity import synth
        from league.equity.store import STORE_DIR, EquityStore, from_ordinal, mint_equity_gate_capability
        from league.ops import forward_db, forward_shadow
        from league.swarm import elane_train
        from league.swarm.store import SwarmStore

        self.house = house
        root = house.root
        store_root = synth.synthetic_store(root / STORE_DIR, symbols=SYMBOLS, start=STORE_START, end=STORE_END,
                                           gate=True, seed=STORE_SEED)
        capability = mint_equity_gate_capability(store_root, "the harness plays the market")
        bars = EquityStore(store_root, gate=capability).bars(list(SYMBOLS), "forward", history=60, start=MONDAY, end=None)
        for symbol in SYMBOLS:
            house.market.bar_rows["raw"][symbol] = synth.bar_rows(bars, symbol, bars.n - 1, adjustment="raw")
            house.market.bar_rows["all"][symbol] = synth.bar_rows(bars, symbol, bars.n - 1, adjustment="all")
            for i in range(bars.n):
                house.market.days[(from_ordinal(int(bars.days[i])), symbol)] = {
                    "open": float(bars.raw[symbol][i, 0]), "close": float(bars.raw[symbol][i, 3])}
        self.swarm = SwarmStore(root, clock=house.clock)
        self.db = forward_db.open_db(root)
        created = at(FRIDAY, 15, 0)
        for row in programs:
            forward_db.append_registry(self.db, {
                "key": f"{row['family']}@{row['version']}", "family": row["family"], "version": int(row["version"]),
                "lane": row["lane"], "reason": "live", "ugroup": "index", "lineage": f"{row['lane']}:{row['family']}",
                "code": row["code"], "params": dict(row["params"]), "needs": elane_train.needs_literal(row["code"]),
                "program_sha": hashlib.sha256(row["code"].encode()).hexdigest(), "run_sha": self.run_sha(row),
                "author": "the harness", "created_at": created, "evidence": "registry",
                "first_close": forward_db.first_close(created),
                "first_day": forward_db.first_day(forward_db.first_close(created)), "registered_at": created,
                "route": forward_db.E3_ROUTE, "alpha_f": forward_db.E3_ALPHA_F})
        self.shadow = forward_shadow.Shadow(root, self.db, decider=InlineDecider(), settings=FORWARD, clock=house.clock)
        self.nights: list[list] = []

    def run_sha(self, row: dict) -> str:
        """The run sha the BOOK holds for the program (the registry's must be it): the row's own through the test
        double, the swarm store's through the real reader."""
        if isinstance(self.house.families, MemoryEquityFamilies):
            return str(row["run_sha"])
        return str(next(r["run_sha"] for r in self.house.families.read() if r["family"] == row["family"]))

    def morning(self, day: dt.date) -> None:
        """09:00: the equity twins of the lots closed so far (EDM1's twin leg and A14's gap read them)."""
        from league.ops import twins as TW

        self.house.clock.set(at(day, 9, 0, 0))
        TW.equity_round(self.house.root, now=self.house.clock(), store=self.swarm)
        if isinstance(self.house.families, MemoryEquityFamilies):
            self.house.families.twin_rows = dict(TW.equity_records(self.swarm))   # (what the real reader reads there)

    def night(self, day: dt.date) -> None:
        """18:35: the forward night that closed `day`: the twin rows of every session before it."""
        from league.ops import forward_twins

        self.house.clock.set(at(day, 18, 35, 0))
        self.shadow.through, self.shadow.night_day = day, day.isoformat()
        receipt = forward_twins.finish(self.house.root, self.db, self.shadow, now=self.house.clock())
        self.nights.append([day.isoformat(), {k: v for k, v in sorted(receipt.items()) if v}])

    def left(self) -> dict[str, Any]:
        """What the forward store holds: every `fwd_twins`, `fwd_part` and `fwd_lotgap` row (every column), every twin
        event (a re-base among them), each night's receipt, and A14's reading over each instance's closes and over
        them all (`a14_reading`, with the re-bases beside)."""
        from league.ops import dlane_report as DR
        from league.ops import forward_db, forward_twins

        def table(name: str, order: str) -> list[dict]:
            return [dict(r) for r in self.db.execute(f"SELECT * FROM {name} ORDER BY {order}")]

        kinds = sorted(k for k in forward_db.EVENT_KINDS if k.startswith("twin_") or k in ("live_bars", "no_minute"))
        lots = [dict(r) for r in self.house.state.rows("SELECT * FROM eq_lots ORDER BY lid")]
        counted = DR.equity_closes(lots, since=0.0)
        by_instance = sorted({str(c["instance"]) for c in counted})
        return {"twins": table("fwd_twins", "instance, day"), "twin_part": table("fwd_part", "instance, through"),
                "twin_lotgap": table("fwd_lotgap", "1, 2"),
                "twin_events": [[e["kind"], e["day"], e["pid"], e["payload"]]
                                for kind in kinds for e in forward_db.events(self.db, kind)],
                "twin_nights": self.nights,
                "a14": [["all", forward_twins.a14_reading(self.house.root, counted)]]
                + [[i, forward_twins.a14_reading(self.house.root, [c for c in counted if c["instance"] == i])]
                   for i in by_instance]}

    def close(self) -> None:
        self.db.close()
        self.swarm.close()


# ------------------------------------------------------------------------------------------------------- the setups
def practice_seen_after(minutes: float):
    """The practice buy fills `minutes` House minutes after its send (seen by the tick that many minutes later)."""
    def setup(house: House) -> None:
        house.paper.fill_delay = lambda body: INF if minutes == INF else max(0.4, minutes * 60.0 - 30.0)
    return setup


def first_post(mode: str, n: int = 1):
    """The first `n` POSTs of the practice account are answered `mode`."""
    def setup(house: House) -> None:
        seen = {"n": 0}

        def answer(body):
            seen["n"] += 1
            return mode if seen["n"] <= n else None
        house.paper.script = answer
    return setup


def paper_positions_trail(seconds: float):
    def setup(house: House) -> None:
        house.paper.positions_delay = seconds
    return setup


def paper_reads_fail(until_mm: int):
    def setup(house: House) -> None:
        house.paper.fail_reads = lambda what: house.clock() < at(MONDAY, 9, until_mm, 0)
    return setup


def stale_quotes(until_mm: int, symbols=("QQQ", "SPY")):
    """The snapshot's quote stamp is from before the open until 09:`until_mm` (the entry path's `fresh`)."""
    def setup(house: House) -> None:
        open_at = S.moments(MONDAY).open_at
        house.market.stale = lambda day, symbol, secs: (open_at - 5.0 if symbol in symbols and day == MONDAY
                                                        and secs < (until_mm - 30) * 60 else None)
    return setup


def wide_quotes(until_mm: int, bp: float, symbols=("QQQ",)):
    def setup(house: House) -> None:
        house.market.spread_bp = lambda day, symbol, secs: (bp if symbol in symbols and day == MONDAY
                                                            and secs < (until_mm - 30) * 60
                                                            else 2 * config.HALF_SPREAD_BP[symbol])
    return setup


def rests(symbol: str, sends: float):
    """The first `sends` real buys of `symbol` rest unfilled (the quote jumped through each limit before it arrived)."""
    def setup(house: House) -> None:
        seen = {"n": 0}

        def delay(body):
            if body["symbol"] != symbol or body["side"] != "buy":
                return 0.4
            seen["n"] += 1
            return INF if seen["n"] <= sends else 0.4
        house.venue.fill_delay = delay
    return setup


def jumps_through(symbol: str, bp: float, sends: int):
    """Each of the first `sends` real buys of `symbol` sees the ask jump `bp` in the 0.4 s between the House's quote and
    the order's arrival (a step up at the send, kept)."""
    def setup(house: House) -> None:
        steps: list[float] = []
        real_submit = house.venue.submit

        def submit(body, *, exit):
            if body["symbol"] == symbol and body["side"] == "buy" and len(steps) < sends:
                steps.append(house.clock() + 0.2)
            return real_submit(body, exit=exit)
        house.venue.submit = submit
        open_at = S.moments(MONDAY).open_at
        house.market.move = lambda day, s, secs: (bp * sum(1 for t in steps if t <= open_at + secs) if s == symbol else 0.0)
    return setup


def window_loss(usd: str, *, option_at_risk: str = "43.05"):
    """The options book's rows: Probe closes worth -`usd` inside the 20-session window, and one open option position
    with a maximum loss of `option_at_risk`."""
    def setup(house: House) -> None:
        s = house.state
        if D(usd) > 0:
            s.execute("INSERT INTO positions(pid, instance, family, type, root, legs, qty, opened_qty, entry, "
                      "max_loss_share, collateral, fees, cash, opened_at, opened_day, opened_minute, status, closed_at, "
                      "tuition, info) VALUES(901, 'opt-x@1:r', 'opt-x', 'long_call', 'SPY', '[]', 0, 1, 1.0, 1.0, 0, 0, ?, "
                      "?, '2026-10-08', 600, 'closed', ?, 0, ?)",
                      (-float(usd), at(dt.date(2026, 10, 8), 10, 0), at(dt.date(2026, 10, 8), 15, 0), '{"probe": true}'))
        if D(option_at_risk) > 0:
            s.execute("INSERT INTO positions(pid, instance, family, type, root, legs, qty, opened_qty, entry, "
                      "max_loss_share, collateral, fees, cash, opened_at, opened_day, opened_minute, status, tuition, info) "
                      "VALUES(902, 'opt-y@1:r', 'opt-y', 'long_call', 'SPY', '[]', 1, 1, 0.4305, ?, 0, 0, ?, ?, "
                      "'2026-10-09', 600, 'open', 0, ?)",
                      (float(D(option_at_risk) / 100), -float(option_at_risk), at(FRIDAY, 10, 0), '{"probe": true}'))
    return setup


def blocked_until(mm: int, why: str):
    """The House's `real_block` answers `why` until 09:`mm` (stage BUY is passed beforehand in this scenario)."""
    def setup(house: House) -> None:
        house.pass_proof(buy=True, sell=False)
        real_tick = house.tick

        def tick(day, hh, m):
            house.blocked = why if (day == MONDAY and (hh, m) < (9, mm)) else None
            return real_tick(day, hh, m)
        house.tick = tick
    return setup


def options_count(count: int, reserve: int):
    def setup(house: House) -> None:
        house.options.count, house.options.reserve_n = count, reserve
    return setup


def equity_orders_already(n: int):
    """`n` equity orders already counted today (the count's own line)."""
    def setup(house: House) -> None:
        for k in range(n):
            eid = 9000 + k
            house.book._save_order(L.Order(eid, f"lq-x-{eid}", "x@1:r", "x", "buy", "IWM", "etf", "open", D("0.1"),
                                           D("220"), 10, "canceled", at(MONDAY, 9, 20), MONDAY.isoformat()))
    return setup


def restart_at(minutes: tuple[int, ...]):
    def setup(house: House) -> None:
        real_tick = house.tick

        def tick(day, hh, mm):
            if day == MONDAY and hh == 9 and mm in minutes:
                house.restart()
            return real_tick(day, hh, mm)
        house.tick = tick
    return setup


def restated_bar(symbol: str, cents: float):
    """Friday's raw close of `symbol` reads `cents` different on Monday morning (the vendor restated it)."""
    def setup(house: House) -> None:
        for name in ("raw", "all"):
            for row in house.market.bar_rows[name][symbol]:
                if row["t"].startswith(FRIDAY.isoformat()):
                    row["c"] = round(row["c"] + cents / 100.0, 4)
        house.tick(MONDAY, 8, 31)
    return setup


def kill_until(mm: int):
    def setup(house: House) -> None:
        real_tick = house.tick

        def tick(day, hh, m):
            house.kill = day == MONDAY and (hh, m) < (9, mm)
            return real_tick(day, hh, m)
        house.tick = tick
    return setup


def skipped(minutes: tuple[int, ...]):
    """The equity book's minute is skipped (the options path's reads hung) in these minutes of Monday's 09h."""
    def setup(house: House) -> None:
        real_tick = house.tick

        def tick(day, hh, mm):
            if day == MONDAY and hh == 9 and mm in minutes:
                house.clock.set(at(day, hh, mm, 3))
                return {"skipped": "the harness"}
            return real_tick(day, hh, mm)
        house.tick = tick
    return setup


def activities_late(seconds: float):
    """The practice account lists its FILL activities `seconds` late (INF: never: stage SELL cannot pass)."""
    def setup(house: House) -> None:
        house.paper.activity_delay = seconds
    return setup


def practice_sale_rests(house: House) -> None:
    """The practice SALE never fills (its buy does)."""
    house.paper.fill_delay = lambda body: INF if body["side"] == "sell" else 0.4


def both(*setups):
    def setup(house: House) -> None:
        for one in setups:
            one(house)
    return setup


def sales_rest(symbols: tuple[str, ...], seconds: float):
    """Every real SALE of `symbols` fills `seconds` after its POST (the bid stepped under its limit and came back)."""
    def setup(house: House) -> None:
        house.venue.fill_delay = lambda body: seconds if body["side"] == "sell" and body["symbol"] in symbols else 0.4
    return setup


def refused_all(day: dt.date, why: str = "the House is paused"):
    """The House's `real_block` refuses every open through the whole of `day` (stage BUY passed long before)."""
    def setup(house: House) -> None:
        real_tick = house.tick

        def tick(d, hh, mm):
            house.blocked = why if d == day else None
            return real_tick(d, hh, mm)
        house.tick = tick
    return setup


def refused_open(day: dt.date, why: str = "the account could not be read this minute"):
    """`real_block` refuses every open in the OPEN window of `day` (a buy planned for that open is missed)."""
    def setup(house: House) -> None:
        real_tick = house.tick

        def tick(d, hh, mm):
            house.blocked = why if d == day and hh < 10 else None
            return real_tick(d, hh, mm)
        house.tick = tick
    return setup


def withdrawn(family: str, day: dt.date):
    """The swarm retires `family` before the decide of `day` (its seat is free at that band sync)."""
    def setup(house: House) -> None:
        real_tick = house.tick

        def tick(d, hh, mm):
            if (d, hh, mm) == (day, 16, 21):
                if isinstance(house.families, MemoryEquityFamilies):
                    house.families.rows[family]["band"] = "retired"
                else:
                    with house.families.lock:
                        house.families._db().retire(family, "an invented retirement")
            return real_tick(d, hh, mm)
        house.tick = tick
    return setup


# ------------------------------------------------------------------------------------------------------ the scenarios
#: name -> {kind, setup, and the House's own arguments}. "monday": Friday's decide and Monday's open window; "next":
#: that, Monday's close and decide, and Tuesday's open window; "week": Monday to Friday, every open window, three
#: minutes of the day, the close window and the decide (`flatten`: the owner's flatten that morning). "fortnight": the
#: week's days for thirteen sessions, over `ranked_programs(waiting)` (THE SEAT RULE: an idle seat is named at the
#: tenth seated session's decide). "twin": the week's days for eight sessions on a synthetic store's bars, with the
#: forward record's morning and night (`Forward`; A29: the twin is re-based after a differing session).
SCENARIOS: dict[str, dict[str, Any]] = {
    # the normal Monday
    "normal": {"kind": "monday"},
    "normal, B's intents first": {"kind": "monday", "a_first": False},
    "normal, the equity tick 50 s into the minute": {"kind": "monday", "lag": 50.0},
    "two Candidates take their seats at Friday's decide": {
        "kind": "next", "candidates": ("bred-a-hold3", "seed-overnight-qqq")},
    # the practice order
    **{f"practice fill seen after {m} min": {"kind": "monday", "setup": practice_seen_after(m)}
       for m in (2, 5, 10, 12, 13, 14)},
    "practice fill never seen": {"kind": "monday", "setup": practice_seen_after(INF)},
    "practice POST refused by the House's own rate": {"kind": "next", "setup": first_post("rate")},
    "practice POST rejected by the venue": {"kind": "monday", "setup": first_post("reject")},
    "practice POST's answer lost, the order exists": {"kind": "monday", "setup": first_post("lost")},
    "practice POST's answer lost, no order made": {"kind": "monday", "setup": first_post("lost_absent")},
    "practice positions trail the fill by 90 s": {"kind": "monday", "setup": paper_positions_trail(90.0)},
    "practice account unreadable until 09:36": {"kind": "monday", "setup": paper_reads_fail(36)},
    "practice account unreadable until 09:44": {"kind": "monday", "setup": paper_reads_fail(44)},
    "practice account unreadable until 09:45": {"kind": "monday", "setup": paper_reads_fail(45)},
    # the quote
    "quotes stamped before the open until 09:35": {"kind": "monday", "setup": stale_quotes(35)},
    "QQQ quoted 250 bp wide until 09:36": {"kind": "monday", "setup": wide_quotes(36, 250.0)},
    "QQQ quoted 150 bp wide all window": {"kind": "monday", "setup": wide_quotes(60, 150.0)},
    # the ladder and the shared symbol
    "A's QQQ buy rests one send": {"kind": "monday", "setup": rests("QQQ", 1)},
    "A's QQQ buy needs all five sends": {"kind": "monday", "setup": rests("QQQ", 4)},
    "QQQ jumps 12 bp through A's first four limits": {"kind": "monday", "setup": jumps_through("QQQ", 12.0, 4)},
    "no QQQ buy ever fills": {"kind": "monday", "setup": rests("QQQ", INF)},
    "no QQQ buy ever fills, stage BUY already passed": {
        "kind": "monday", "setup": both(lambda h: h.pass_proof(sell=False), rests("QQQ", INF))},
    # sizing: the loss budget and the caps
    **{f"window loss ${usd} realized and an option position at risk": {"kind": "monday", "setup": window_loss(usd)}
       for usd in ("0", "250", "270", "300", "330", "345", "356")},
    "account cash $300": {"kind": "monday", "cash": "300"},
    # the order count and the House's block
    "56 equity orders already counted today": {"kind": "monday", "setup": equity_orders_already(56)},
    "58 equity orders already counted today": {"kind": "monday", "setup": equity_orders_already(58)},
    "options book: 249 of 250 House orders sent": {"kind": "monday", "setup": options_count(249, 0)},
    "real_block until 09:40": {"kind": "monday", "setup": blocked_until(40, "the account could not be read this minute")},
    "real_block until 09:45": {"kind": "monday", "setup": blocked_until(45, "the daily stop")},
    # the House itself
    "restart before the 09:32 minute": {"kind": "monday", "setup": restart_at((32,))},
    "restart before the 09:33 minute": {"kind": "monday", "setup": restart_at((33,))},
    "restart before 09:31, 09:32, 09:33 and 09:34": {"kind": "monday", "setup": restart_at((31, 32, 33, 34))},
    "Friday's QQQ close restated before the 08:30 audit": {"kind": "next", "setup": restated_bar("QQQ", 1.0)},
    "Friday's IWM close restated before the 08:30 audit": {"kind": "monday", "setup": restated_bar("IWM", 1.0)},
    "the kill switch engaged until 09:38": {"kind": "monday", "setup": kill_until(38)},
    "the equity minute skipped at 09:31 and 09:32": {"kind": "monday", "setup": skipped((31, 32))},
    "the equity minute skipped 09:31 to 09:43": {"kind": "monday", "setup": skipped(tuple(range(31, 44)))},
    # the week
    "week: normal": {"kind": "week"},
    "week: FILL activities listed 5 minutes late": {"kind": "week", "setup": activities_late(300.0)},
    "week: stage SELL cannot pass, no FILL activity": {"kind": "week", "setup": activities_late(INF)},
    "week: stage SELL cannot pass, the practice sale rests": {"kind": "week", "setup": practice_sale_rests},
    "week: the owner's flatten on Tuesday, stage SELL not passing": {
        "kind": "week", "setup": activities_late(INF), "flatten": TUESDAY},
    # programs that sell and buy in one window (the case the panel kind's rule B8 holds a cut buy for)
    "week: a program sells and buys again at every open": {"kind": "week", "roll": "open"},
    "week: a rolling program's sale rests five minutes at every open": {
        "kind": "week", "roll": "open", "setup": sales_rest(("IWM",), 300.0)},
    "week: a rolling program's sale never fills": {"kind": "week", "roll": "open", "setup": sales_rest(("IWM",), INF)},
    "week: a rolling program while stage SELL cannot pass": {
        "kind": "week", "roll": "open", "setup": activities_late(INF)},
    "week: a program sells and buys again at every close": {"kind": "week", "roll": "close"},
    "week: a rolling program's sale rests two minutes at every close": {
        "kind": "week", "roll": "close", "setup": sales_rest(("IWM",), 130.0)},
    "week: a program rotates between ETFs at every open": {"kind": "week", "rotate": "open"},
    "week: a rotating program's sales rest five minutes at every open": {
        "kind": "week", "rotate": "open", "setup": sales_rest(("SPY", "IWM", "DIA"), 300.0)},
    "week: a rotating program's sales never fill": {
        "kind": "week", "rotate": "open", "setup": sales_rest(("SPY", "IWM", "DIA"), INF)},
    "week: a rotating program while stage SELL cannot pass": {
        "kind": "week", "rotate": "open", "setup": activities_late(INF)},
    "week: a rotating program's sales rest two minutes at every close": {
        "kind": "week", "rotate": "close", "setup": sales_rest(("SPY", "IWM", "DIA"), 130.0)},
    "week: a rolling and a rotating program, sales resting five minutes": {
        "kind": "week", "roll": "open", "rotate": "open", "setup": sales_rest(("SPY", "IWM", "DIA"), 300.0)},
    # THE SEAT RULE (release E5-A, A24 with A30): the idle seat, the waiting programs, the return
    "fortnight: nobody waits, the idle seats are kept": {"kind": "fortnight"},
    "fortnight: an idle seat yields to the waiting program": {"kind": "fortnight", "waiting": 1},
    "fortnight: two programs wait, one idle seat yields a decision day": {"kind": "fortnight", "waiting": 2},
    "fortnight: the House refused every open one session, the idle clock leaves it out": {
        "kind": "fortnight", "waiting": 1, "setup": refused_all(dt.date(2026, 10, 20))},
    "fortnight: a yielded program returns into a seat the swarm freed": {
        "kind": "fortnight", "waiting": 1, "setup": withdrawn("bred-b-range", dt.date(2026, 10, 26))},
    "fortnight: a waiting program, stage SELL never passing": {
        "kind": "fortnight", "waiting": 1, "setup": activities_late(INF)},
    # THE FORWARD TWINS (release E3.1, A29): the nights' twin rows beside the book
    "twin: every buy fills, nothing is re-based": {"kind": "twin"},
    "twin: Monday's buys missed, the twins re-based": {"kind": "twin", "setup": first_post("rate")},
    "twin: Wednesday's open refused, a rebuy missed and the twin re-based": {
        "kind": "twin", "setup": refused_open(WEDNESDAY)},
    "twin: the practice sale never witnessed, exits at the cut-off": {"kind": "twin", "setup": practice_sale_rests},
}
#: The scenarios run again through the REAL reader (`store_families`), at every position of the panel lane's switch:
#: all of them.
STORE_SCENARIOS = tuple(SCENARIOS)


def open_window(house: House, day: dt.date, last: tuple[int, int]) -> None:
    """Every House minute from the pre-open (09:25) to `last`."""
    hh, mm = 9, 25
    while (hh, mm) <= last:
        house.tick(day, hh, mm)
        hh, mm = (hh, mm + 1) if mm < 59 else (hh + 1, 0)


def close_and_decide(house: House, day: dt.date) -> None:
    for mm in (54, 55, 56, 57, 58, 59):
        house.tick(day, 15, mm)
    for hh, mm in ((16, 0), (16, 21), (16, 31)):
        house.tick(day, hh, mm)


def panel_rows(bands: tuple[str, ...]) -> list[dict]:
    """RELEASE E4 STEP TWO: one PANEL program's row in each of these bands, as the swarm's reader gives it once the
    panel lane reads "live" (structure "panel"; passed, with K's counts above every ETF program's, so a panel program
    that could rank in the ETF pool would take its seat first). The test double of the reader gives them to the book;
    the book's panel pool is the only one they may enter (league/tests/test_equity_panel_seats.py)."""
    rows = []
    for band in bands:
        row = family_row(f"xs-row-{band}", PANEL, lane="equity", symbols=(), band=band, k=(900, 4000))
        rows.append({**row, "structure": "panel"})
    return rows


def run(name: str, *, reader: str = "memory", panel: str = "", forced: tuple[str, ...] = (),
        panels: tuple[str, ...] = ()) -> dict[str, Any]:
    """Scenario `name` on the tree this module was imported from: `snapshot` of what it left. `forced`: the real
    reader's store also holds a panel family in each of these bands (`store_families`). `panels` (the test double of
    the reader): it also gives the book a panel program's row in each of these bands (`panel_rows`)."""
    spec = SCENARIOS[name]
    root = Path(tempfile.mkdtemp(prefix="equity-week-"))
    programs = six_programs(a_first=spec.get("a_first", True), roll=spec.get("roll", ""), rotate=spec.get("rotate", ""))
    if spec["kind"] == "fortnight":
        programs = ranked_programs(spec.get("waiting", 0))
    for row in programs:
        if row["family"] in spec.get("candidates", ()):
            row["band"] = "candidate"
    programs = programs + panel_rows(panels)
    house = House(root, programs, cash=spec.get("cash", "2229"), lag=spec.get("lag", 8.0), reader=reader, panel=panel,
                  forced=forced)
    try:
        if spec["kind"] == "twin":
            house.forward = Forward(house, programs)
        else:
            invented_week(house.market, through=FORTNIGHT_END if spec["kind"] == "fortnight" else FRIDAY2)
        house.tick(FRIDAY, 16, 21)      # Friday's bars, then its decide: the instances made, Monday's intents planned
        house.tick(FRIDAY, 16, 31)
        if spec.get("setup") is not None:
            spec["setup"](house)
        if spec["kind"] in ("week", "fortnight", "twin"):
            last = {"week": FRIDAY2, "fortnight": FORTNIGHT_END, "twin": TWIN_END}[spec["kind"]]
            for day in sessions_from(MONDAY, S.sessions_between(FRIDAY, last)):
                house.tick(day, 8, 31)
                if house.forward is not None:
                    house.forward.morning(day)
                if spec.get("flatten") == day:
                    house.state.put(L.OWNER_FLATTEN, {"why": "the harness's flatten", "by": "the owner", "at": 0})
                open_window(house, day, (9, 50))
                for hh in (11, 13, 15):
                    house.tick(day, hh, 0)
                close_and_decide(house, day)
                if house.forward is not None:
                    house.forward.night(day)
        else:
            open_window(house, MONDAY, (9, 47))
            if spec["kind"] == "next":
                house.tick(MONDAY, 15, 55)
                house.tick(MONDAY, 16, 21)
                house.tick(MONDAY, 16, 31)
                open_window(house, TUESDAY, (9, 40))
        return snapshot(house)
    finally:
        house.close()
        shutil.rmtree(root, ignore_errors=True)


# ------------------------------------------------------------------------------------------------------ what it left
def _plain(value: Any) -> Any:
    """A value as JSON holds it, exactly (a Decimal as its string, a float as its repr)."""
    return json.loads(json.dumps(value, sort_keys=True, default=str))


def snapshot(house: House) -> dict[str, Any]:
    """EVERYTHING THE BOOK DID, in the order it did it: `posts` (every order POSTed to either account, refused ones
    too), `cancels`, `fills`; the book's rows at the end, every column (`intents`, `orders`, `lots`, `instances`,
    `rebalances` when the table exists) and its own keys of the kv (`kv`: `eq_*` and the stock proof's; the seat plan
    `eq_seat`, the open note and the unproven-sale note are among them); what it said on the way (`alerts`,
    `records`, each minute's answer `ticks`, and `errors`: the book's own events in the state, an error it caught
    among them); `seats`: THE SEAT RULE as it went, each decision's line of the plan and every change of hands
    (`seat_lines`); and, when the forward record ran beside it (`Forward.left`), `twins`, `twin_part`,
    `twin_lotgap`, `twin_events`, `twin_nights` and `a14`."""
    rows = house.state.rows
    posts = sorted([(t, v.name, b) for v in (house.venue, house.paper) for b, t in zip(v.sent, v.sent_at)],
                   key=lambda r: (r[0], r[1]))
    cancels = sorted([(t, v.name, i) for v in (house.venue, house.paper) for i, t in zip(v.cancels, v.cancel_at)])
    fills = sorted([(f["t"], v.name, f) for v in (house.venue, house.paper) for f in v.fills],
                   key=lambda r: (r[0], r[1], r[2]["cid"]))
    tables = {str(r["name"]) for r in rows("SELECT name FROM sqlite_master WHERE type='table'")}
    out = {
        "posts": [f"{said(t)} {name} {b['side']} {b['symbol']} {b['qty']} @ {b['limit_price']} {b['type']} "
                  f"{b['time_in_force']} {b['client_order_id']}" for t, name, b in posts],
        "cancels": [f"{said(t)} {name} {i}" for t, name, i in cancels],
        "fills": [f"{said(t)} {name} {f['side']} {f['symbol']} {f['qty']} @ {f['px']} {f['cid']}" for t, name, f in fills],
        "intents": rows("SELECT * FROM eq_intents ORDER BY iid"),
        "orders": rows("SELECT * FROM eq_orders ORDER BY eid"),
        "lots": rows("SELECT * FROM eq_lots ORDER BY lid"),
        "instances": rows("SELECT * FROM eq_instances ORDER BY id"),
        "rebalances": rows("SELECT * FROM eq_rebalances ORDER BY rid") if "eq_rebalances" in tables else [],
        "kv": {r["key"]: r["value"] for r in rows("SELECT key, value FROM kv WHERE key LIKE 'eq\\_%' ESCAPE '\\' "
                                                  "OR key LIKE 'paper\\_proof\\_stock%' ESCAPE '\\' ORDER BY key")},
        "alerts": [f"{said(t)} {level}: {text}" for t, level, text in house.alerts],
        "records": [[said(t), kind, payload] for t, kind, payload in house.events],
        "ticks": [[said(t), tick] for t, tick in house.ticks],
        "errors": [[r["kind"], (json.loads(r["payload"]) or {}).get("where")]
                   for r in rows("SELECT kind, payload FROM events WHERE kind LIKE 'equity.%' ORDER BY seq")],
        "tables": sorted(t for t in tables if t.startswith("eq_")),
        "seats": seat_lines(house),
        **(house.forward.left() if house.forward is not None else
           {"twins": [], "twin_part": [], "twin_lotgap": [], "twin_events": [], "twin_nights": [], "a14": []}),
    }
    return _plain(out)


def seat_lines(house: House) -> list[str]:
    """THE SEAT RULE as the book said it, in order: each decision's line of the plan (the minute's `seats`: who holds
    each seat, for how many sessions, who is idle, who waits and at what rank) and every `equity.seat` record (a seat
    taken, yielded, returned into, a seating passed over, a waiting program demoted). The plan the book holds at the
    end (`eq_seat`) is in `kv`."""
    said_ = [(t, 0, f"{said(t)} plan: {tick['seats']}") for t, tick in house.ticks if tick.get("seats")]
    said_ += [(t, 1, f"{said(t)} {p.get('action')}: {p.get('family')}"
               + (f" for {p['for']}" if p.get("for") else "") + (f" (rank {p['rank']})" if p.get("rank") else "")
               + f": {p.get('why')}") for t, kind, p in house.events if kind == "equity.seat"]
    return [line for _, _, line in sorted(said_, key=lambda r: (r[0], r[1]))]


#: WHAT RELEASE E4 ADDS TO THE STATE OF A BOOK THAT HOLDS NO PANEL PROGRAM, and nothing else: the column
#: `eq_instances.kind` (league/equity/live.py `INSTANCE_KIND_DDL`: "equity" on every share program's row) and the panel
#: adapter's table `eq_rebalances` (league/xs/book.py `SCHEMA`), empty. Both are made when the book starts, at any
#: position of the lane's switch; main's book reads neither and writes its rows as before on a state that holds them
#: (a rollback: the column's default fills it).
E4_COLUMN, E4_TABLE = "kind", "eq_rebalances"


def main_shape(snap: dict[str, Any]) -> dict[str, Any]:
    """A snapshot of a tree that carries release E4, as main's book would have left it: `E4_COLUMN` and `E4_TABLE`
    taken out, EACH HELD FIRST to what it must be for a book of share programs (ValueError otherwise). A snapshot of
    main is returned as it is."""
    kinds = {row.get(E4_COLUMN, "equity") for row in snap["instances"]}
    if kinds - {"equity"}:
        raise ValueError(f"a share program's instance row reads kind {sorted(kinds)}")
    if snap["rebalances"]:
        raise ValueError(f"{len(snap['rebalances'])} rebalance row(s) in a book of share programs")
    return {**snap, "instances": [{k: v for k, v in row.items() if k != E4_COLUMN} for row in snap["instances"]],
            "tables": [t for t in snap["tables"] if t != E4_TABLE]}


#: A snapshot's parts the fixture keeps WHOLE (what an operator reads first); the others it keeps as a digest.
WHOLE = ("posts", "cancels", "fills", "alerts", "seats")


def digest(part: Any) -> str:
    return hashlib.sha256(json.dumps(part, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:20]


def kept(snap: dict[str, Any], *, whole: bool = True) -> dict[str, Any]:
    """A snapshot as the fixture keeps it, in main's shape (`main_shape`): `WHOLE` parts as they are, every other part
    by its count and its digest. `whole` False (the real reader's record, whose orders are the test double's own):
    every part by its count and its digest."""
    snap = main_shape(snap)
    apart = WHOLE if whole else ()
    return {**{k: snap[k] for k in apart},
            "sha": {k: [len(v), digest(v)] for k, v in sorted(snap.items()) if k not in apart}}


def record() -> dict[str, Any]:
    """Every scenario of the tree this module runs on, as the fixture keeps it: {"memory": {name: kept}, "store":
    {name: kept, by digest}} (the real reader's with no panel key in swarm.json: main has no such lane)."""
    return {"memory": {name: kept(run(name)) for name in SCENARIOS},
            "store": {name: kept(run(name, reader="store"), whole=False) for name in STORE_SCENARIOS}}


if __name__ == "__main__":  # pragma: no cover - the recorder
    import subprocess

    tree = Path(sys.argv[sys.argv.index("--tree") + 1]).resolve()
    assert Path(L.__file__).resolve().is_relative_to(tree), f"league was imported from {L.__file__}, not {tree}"
    where = sys.argv[sys.argv.index("--out") + 1]
    if "--full" in sys.argv:        # every snapshot whole, for a diff by hand (never committed)
        doc: dict[str, Any] = {"memory": {name: run(name) for name in SCENARIOS},
                               "store": {name: run(name, reader="store", panel=sys.argv[sys.argv.index("--panel") + 1]
                                                   if "--panel" in sys.argv else "") for name in STORE_SCENARIOS}}
    else:
        doc = record()
    try:
        sha = subprocess.run(["git", "-C", str(tree), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    except OSError:
        sha = ""
    doc = {"_recorded_on": sys.argv[sys.argv.index("--sha") + 1] if "--sha" in sys.argv else sha, **doc}
    Path(where).write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"recorded {len(doc['memory'])} + {len(doc['store'])} scenarios of {tree} in {where}")
