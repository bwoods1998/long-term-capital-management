"""What an equity program sees at the decision close of session t: built by one function, in the Gym and live (I6).

Owner: core. The Gym engine builds `Inputs` from the store's `Bars` (`inputs_from_bars`); the live book builds them from
the 16:20 ET fetch of the same two series (`inputs_from_fetch`), and the decider child calls `build` on them. Both
paths end in `build`, so a program sees byte-identical inputs for the same decision day (`ctx_bytes`; the hooks
package's I6 test feeds the live builder the store's bars for 20 random days and compares the bytes).

ctx at the decision close of session t (EQUITY.md, "ctx"):

    ctx.symbols                  the program's NEEDS symbols, in its order
    ctx.bars[sym]                a `SymbolBars`: open, high, low, close, volume, ret (float64 read-only arrays, oldest
                                 first, the last element session t; NEEDS["history"] + 1 long at most; prices as of t:
                                 all_s x raw_t / all_t, `as_of`; volume raw shares; ret close-to-close of the as-of
                                 closes, NaN first; NaN where the symbol had no bar)
    ctx.prices[sym]              session t's close (raw, which equals its as-of close)
    ctx.weekday                  0 Monday .. 4 Friday, of session t
    ctx.events, ctx.events_next  the Gym's event booleans (league/gym/events.py `flags_for`) for t and t+1
    ctx.session_of_month         1 for the month's first session ..
    ctx.sessions_to_month_end    0 on the month's last session ..
    ctx.positions                open lots: `lot_row` dicts {id, symbol, class, qty, entry, mark, value, pnl,
                                 held_sessions, at ("open" | "close": how it was filled), tag}
    ctx.orders                   pending orders the program may cancel: {id, side, symbol, at, usd, tag} (usually [])
    ctx.closed                   lots closed since the last call: `closed_row` dicts
    ctx.rejects                  why intents of the last call were refused (strings)
    ctx.cash, ctx.equity         the sleeve's free cash and equity (cash + marked lots), dollars, floats
    ctx.budget                   the sleeve's equity the program sizes against (dollars)
    ctx.caps[sym]                dollars the program may still add to sym now (the sizing caps, `league.equity.sizing`)
    ctx.params                   the merged PARAMS

A program never sees a date or a year. Every array is read-only over an immutable buffer (the Gym ctx's `_ro`).
Prices are rounded to 4 decimals (the venue's precision) after the as-of product, so a live fetch and a store written
on a later day agree to the byte except at a rounding boundary.

THE AS-OF FACTOR is read from session t's close (raw_t / all_t of the closes); a symbol with no bar at t takes its last
bar's (its prices then end before t, and `ctx.prices[sym]` is NaN). THE CALENDAR a program's counts and event flags
read (`trading_days`, `early`) is `league.equity.store.nyse_sessions` for t's month and the next session's month, the
same function on both paths, so the Gym and the House cannot disagree about it.
"""

from __future__ import annotations

import copy
import datetime as dt
import math
import struct
from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache
from typing import Any, Mapping, Sequence

import numpy as np

from ..gym import events as _events
from .store import FIRST_YEAR, as_date, from_ordinal, nyse_sessions, ordinal

_NAN = float("nan")
#: Minutes since midnight ET of a regular session's open and close, and of an early close (the event flags' half day).
_OPEN_MIN, _CLOSE_MIN, _EARLY_MIN = 570, 960, 780


def _ro(array: np.ndarray) -> np.ndarray:
    """A read-only array over an IMMUTABLE buffer (a bytes object): numpy refuses to make it writeable again, whatever
    a program tries, so nothing a program does reaches the engine's arrays (league/gym/ctx.py `_ro`)."""
    array = np.ascontiguousarray(array)
    out = np.frombuffer(array.tobytes(), dtype=array.dtype)
    return out if array.ndim == 1 else out.reshape(array.shape)


class SymbolBars:
    """One symbol's daily history as a program sees it (read-only arrays, oldest first, last = session t)."""

    __slots__ = ("symbol", "open", "high", "low", "close", "volume", "ret")

    def __init__(self, symbol: str, open: np.ndarray, high: np.ndarray, low: np.ndarray, close: np.ndarray,
                 volume: np.ndarray, ret: np.ndarray):
        self.symbol = str(symbol)
        self.open = _ro(np.asarray(open, dtype=np.float64))
        self.high = _ro(np.asarray(high, dtype=np.float64))
        self.low = _ro(np.asarray(low, dtype=np.float64))
        self.close = _ro(np.asarray(close, dtype=np.float64))
        self.volume = _ro(np.asarray(volume, dtype=np.float64))
        self.ret = _ro(np.asarray(ret, dtype=np.float64))

    def __repr__(self) -> str:
        return f"SymbolBars({self.symbol}, {self.close.shape[0]} sessions)"


class Ctx:
    """What decide(ctx) receives (EQUITY.md). Read its attributes; never assign them."""

    __slots__ = ("symbols", "bars", "prices", "weekday", "events", "events_next", "session_of_month",
                 "sessions_to_month_end", "positions", "orders", "closed", "rejects", "cash", "equity", "budget", "caps",
                 "params")

    def __init__(self, **values: Any):
        for name in self.__slots__:
            object.__setattr__(self, name, values.get(name))

    def __repr__(self) -> str:
        return f"Ctx({', '.join(self.symbols or ())})"


@dataclass(frozen=True)
class Inputs:
    """Everything one decision's ctx is built from (pickled to the decider child live; built in-process in the Gym).

    `symbols`: NEEDS symbols. `history`: NEEDS history. `days`: int32 ordinals of the sessions the arrays cover, oldest
    first, the last session t. `raw[sym]`: float64 (n, 5) raw open, high, low, close, volume. `adj[sym]`: float64 (n, 4)
    adjustment=all open, high, low, close (as fetched on any day >= t). `trading_days`: int32 ordinals of the
    calendar around t (at least t's month and the next session; events and the month counts read them). `early`: bool
    per `trading_days` entry. `positions`, `orders`, `closed`: rows as `lot_row` / order dicts / `closed_row`.
    `rejects`: strings. `cash`, `equity`, `budget`: dollars (floats). `caps`: {sym: dollars}. `params`: merged PARAMS."""

    symbols: tuple[str, ...]
    history: int
    days: np.ndarray
    raw: Mapping[str, np.ndarray]
    adj: Mapping[str, np.ndarray]
    trading_days: np.ndarray
    early: np.ndarray
    positions: tuple[dict, ...]
    orders: tuple[dict, ...]
    closed: tuple[dict, ...]
    rejects: tuple[str, ...]
    cash: float
    equity: float
    budget: float
    caps: Mapping[str, float]
    params: Mapping[str, Any]


def as_of(adj: np.ndarray, raw_t: float, adj_t: float) -> np.ndarray:
    """all_s x raw_t / all_t for every s (a column of `adj` through t), rounded to 4 decimals: prices adjusted only
    for events in (s, t], whatever day `adj` was fetched on."""
    adj = np.asarray(adj, dtype=np.float64)
    raw_t, adj_t = float(raw_t), float(adj_t)
    if not (math.isfinite(raw_t) and math.isfinite(adj_t) and raw_t > 0 and adj_t > 0):
        return np.full(adj.shape, np.nan)
    return np.round(adj * (raw_t / adj_t), 4)


def _factor_row(raw: np.ndarray, adj: np.ndarray) -> int | None:
    """The row whose closes set the as-of factor: session t's (the last), else the symbol's last bar before it."""
    ok = np.isfinite(raw[:, 3]) & np.isfinite(adj[:, 3]) & (raw[:, 3] > 0) & (adj[:, 3] > 0)
    hits = np.flatnonzero(ok)
    return int(hits[-1]) if hits.size else None


def _symbol_bars(sym: str, raw: np.ndarray, adj: np.ndarray) -> tuple[SymbolBars, float]:
    raw = np.asarray(raw, dtype=np.float64).reshape(-1, 5)
    adj = np.asarray(adj, dtype=np.float64).reshape(-1, 4)
    if raw.shape[0] != adj.shape[0]:
        raise ValueError(f"{sym}'s raw and all arrays differ in length")
    row = _factor_row(raw, adj)
    n = raw.shape[0]
    if row is None:
        cols = [np.full(n, np.nan) for _ in range(4)]
    else:
        cols = [as_of(adj[:, k], raw[row, 3], adj[row, 3]) for k in range(4)]
    close = cols[3]
    ret = np.full(n, np.nan)
    if n > 1:
        with np.errstate(divide="ignore", invalid="ignore"):
            ret[1:] = close[1:] / close[:-1] - 1.0
    price = float(close[-1]) if n and row == n - 1 else _NAN
    return SymbolBars(sym, cols[0], cols[1], cols[2], close, raw[:, 4], ret), price


def build(inputs: Inputs) -> Ctx:
    """THE constructor of an equity ctx (the Gym's and the live path's one)."""
    days = np.asarray(inputs.days, dtype=np.int32)
    if days.size == 0:
        raise ValueError("a ctx needs session t")
    t = from_ordinal(int(days[-1]))
    bars: dict[str, SymbolBars] = {}
    prices: dict[str, float] = {}
    for sym in inputs.symbols:
        bars[sym], prices[sym] = _symbol_bars(sym, inputs.raw[sym], inputs.adj[sym])
    trading = [from_ordinal(int(d)) for d in np.asarray(inputs.trading_days, dtype=np.int32)]
    early = {d: bool(e) for d, e in zip(trading, np.asarray(inputs.early, dtype=bool))}
    if t not in early:
        raise ValueError("session t is not in the ctx's calendar")
    today, upcoming = _events.flags_for(t, trading, lambda d: (_OPEN_MIN, _EARLY_MIN if early.get(d) else _CLOSE_MIN))
    month = [d for d in trading if d.year == t.year and d.month == t.month]
    return Ctx(
        symbols=tuple(inputs.symbols), bars=bars, prices=prices, weekday=int(t.weekday()), events=dict(today),
        events_next=dict(upcoming), session_of_month=sum(1 for d in month if d <= t),
        sessions_to_month_end=sum(1 for d in month if d > t),
        positions=[dict(p) for p in inputs.positions], orders=[dict(o) for o in inputs.orders],
        closed=[dict(c) for c in inputs.closed], rejects=[str(r) for r in inputs.rejects], cash=float(inputs.cash),
        equity=float(inputs.equity), budget=float(inputs.budget),
        caps={str(k): float(v) for k, v in inputs.caps.items()}, params=copy.deepcopy(dict(inputs.params)),
    )


@lru_cache(maxsize=512)
def _month(year: int, month: int) -> tuple[tuple[int, bool], ...]:
    first = dt.date(year, month, 1)
    last = (dt.date(year + (month == 12), month % 12 + 1, 1) - dt.timedelta(days=1))
    return tuple((ordinal(d), bool(e)) for d, e in nyse_sessions(first, last))


def calendar_around(day: dt.date) -> tuple[np.ndarray, np.ndarray]:
    """(trading_days, early) for a decision on `day`: every session of its month and of the next session's month, from
    `store.nyse_sessions` (both paths read this one)."""
    rows = list(_month(day.year, day.month))
    later = [o for o, _ in rows if o > ordinal(day)]
    if not later:
        year, month = (day.year + 1, 1) if day.month == 12 else (day.year, day.month + 1)
        rows += list(_month(year, month))
    return (np.array([o for o, _ in rows], dtype=np.int32), np.array([e for _, e in rows], dtype=bool))


def _common(symbols: Sequence[str], history: int, days: np.ndarray, raw: Mapping[str, np.ndarray],
            adj: Mapping[str, np.ndarray], *, positions: Sequence[dict], orders: Sequence[dict], closed: Sequence[dict],
            rejects: Sequence[str], cash: float, equity: float, budget: float, caps: Mapping[str, float],
            params: Mapping[str, Any]) -> Inputs:
    trading, early = calendar_around(from_ordinal(int(days[-1])))
    return Inputs(symbols=tuple(symbols), history=int(history), days=np.asarray(days, dtype=np.int32),
                  raw={s: np.asarray(raw[s], dtype=np.float64) for s in symbols},
                  adj={s: np.asarray(adj[s], dtype=np.float64) for s in symbols},
                  trading_days=trading, early=early, positions=tuple(dict(p) for p in positions),
                  orders=tuple(dict(o) for o in orders), closed=tuple(dict(c) for c in closed),
                  rejects=tuple(str(r) for r in rejects), cash=float(cash), equity=float(equity), budget=float(budget),
                  caps={str(k): float(v) for k, v in caps.items()}, params=copy.deepcopy(dict(params)))


def inputs_from_bars(bars: Any, t: int, *, needs: Any, positions: Sequence[dict] = (), orders: Sequence[dict] = (),
                     closed: Sequence[dict] = (), rejects: Sequence[str] = (), cash: float, equity: float,
                     budget: float, caps: Mapping[str, float], params: Mapping[str, Any]) -> Inputs:
    """The Gym's inputs at session index `t` of a `store.Bars` (never a row after t): `needs` is a
    `program.Needs`."""
    t = int(t)
    if not 0 <= t < bars.n:
        raise ValueError(f"session index {t} is outside the slice")
    missing = [s for s in needs.symbols if s not in bars.raw or s not in bars.adj]
    if missing:
        raise ValueError(f"the slice lacks {', '.join(missing)}")
    lo = max(0, t - int(needs.history))
    days = np.array(bars.days[lo:t + 1], dtype=np.int32)
    raw = {s: np.array(bars.raw[s][lo:t + 1], dtype=np.float64) for s in needs.symbols}
    adj = {s: np.array(bars.adj[s][lo:t + 1], dtype=np.float64) for s in needs.symbols}
    return _common(needs.symbols, needs.history, days, raw, adj, positions=positions, orders=orders, closed=closed,
                   rejects=rejects, cash=cash, equity=equity, budget=budget, caps=caps, params=params)


def _row_day(row: Mapping[str, Any]) -> dt.date:
    stamp = row.get("t")
    if isinstance(stamp, str) and len(stamp) > 10:
        return as_date(dt.datetime.fromisoformat(stamp.replace("Z", "+00:00")))
    return as_date(stamp)


def _rows(rows: Sequence[Mapping[str, Any]] | None, sym: str, which: str, through: dt.date) -> dict[dt.date, Mapping]:
    out: dict[dt.date, Mapping[str, Any]] = {}
    for row in rows or ():
        day = _row_day(row)
        if day > through:
            continue
        if day in out:
            raise ValueError(f"{sym}'s {which} bars name {day} twice")
        out[day] = row
    return out


def inputs_from_fetch(raw_rows: Mapping[str, Sequence[Mapping[str, Any]]],
                      all_rows: Mapping[str, Sequence[Mapping[str, Any]]], *, day: Any, needs: Any,
                      positions: Sequence[dict] = (), orders: Sequence[dict] = (), closed: Sequence[dict] = (),
                      rejects: Sequence[str] = (), cash: float, equity: float, budget: float,
                      caps: Mapping[str, float], params: Mapping[str, Any]) -> Inputs:
    """The live path's inputs from the 16:20 fetch: Alpaca 1Day bar rows ({t, o, h, l, c, v}) per symbol for
    adjustment=raw and adjustment=all through `day` (an ISO day or date: session t). ValueError when session t's bar is
    missing for a NEEDS symbol or the two series disagree on their sessions.

    The sessions are the calendar's (`store.nyse_sessions`): the `history` sessions before t and t itself, as the
    store's slice has them, each symbol's rows placed on their days (NaN where it has none)."""
    t = as_date(day)
    lookback = int(needs.history)
    # 2 x history + 14 calendar days always hold history + 1 sessions; the calendar starts with the store's first year.
    since = max(t - dt.timedelta(days=lookback * 2 + 14), dt.date(FIRST_YEAR, 1, 1))
    sessions = [d for d, _ in nyse_sessions(since, t)] if t.year >= FIRST_YEAR else []
    if not sessions or sessions[-1] != t:
        raise ValueError(f"{t} is not a session")
    sessions = sessions[-(lookback + 1):]
    index = {d: i for i, d in enumerate(sessions)}
    raw: dict[str, np.ndarray] = {}
    adj: dict[str, np.ndarray] = {}
    for sym in needs.symbols:
        mine = _rows(raw_rows.get(sym), sym, "raw", t)
        alls = _rows(all_rows.get(sym), sym, "all", t)
        if set(mine) != set(alls):
            raise ValueError(f"{sym}'s raw and all bars disagree on their sessions")
        if t not in mine:
            raise ValueError(f"{sym} has no bar for session {t}")
        r = np.full((len(sessions), 5), np.nan)
        a = np.full((len(sessions), 4), np.nan)
        for d, row in mine.items():
            i = index.get(d)
            if i is None:
                if d >= sessions[0]:
                    raise ValueError(f"{sym} has a bar on {d}, not a session")
                continue
            r[i] = [float(row[k]) for k in ("o", "h", "l", "c", "v")]
            a[i, :] = [float(alls[d][k]) for k in ("o", "h", "l", "c")]
        raw[sym], adj[sym] = r, a
    days = np.array([ordinal(d) for d in sessions], dtype=np.int32)
    return _common(needs.symbols, needs.history, days, raw, adj, positions=positions, orders=orders, closed=closed,
                   rejects=rejects, cash=cash, equity=equity, budget=budget, caps=caps, params=params)


def lot_row(*, lid: int, symbol: str, klass: str, qty: float, entry: float, mark: float, held_sessions: int, at: str,
            tag: str = "") -> dict:
    """One open lot as a program sees it: {id, symbol, class, qty, entry, mark, value (qty x mark), pnl ((mark - entry)
    x qty), held_sessions, at, tag}; floats rounded to 4 decimals (qty to 6)."""
    qty, entry, mark = float(qty), float(entry), float(mark)
    known = math.isfinite(mark)
    return {"id": int(lid), "symbol": str(symbol), "class": str(klass), "qty": round(qty, 6), "entry": round(entry, 4),
            "mark": round(mark, 4) if known else None, "value": round(qty * mark, 4) if known else None,
            "pnl": round((mark - entry) * qty, 4) if known else None, "held_sessions": int(held_sessions),
            "at": str(at), "tag": str(tag or "")}


def closed_row(*, lid: int, symbol: str, qty: float, entry: float, exit: float, net: float, held_sessions: int,
               reason: str, tag: str = "") -> dict:
    """One lot closed since the last call: {id, symbol, qty, entry, exit, net (dollars after fees and dividends),
    held_sessions, reason ("program" | "max_hold" | "house"), tag}."""
    return {"id": int(lid), "symbol": str(symbol), "qty": round(float(qty), 6), "entry": round(float(entry), 4),
            "exit": round(float(exit), 4), "net": round(float(net), 4), "held_sessions": int(held_sessions),
            "reason": str(reason), "tag": str(tag or "")}


def _encode(value: Any, out: list[bytes]) -> None:
    if value is None:
        out.append(b"N")
    elif isinstance(value, (bool, np.bool_)):
        out.append(b"T" if value else b"F")
    elif isinstance(value, (int, np.integer)):
        out.append(b"i" + str(int(value)).encode() + b";")
    elif isinstance(value, (float, np.floating)):
        out.append(b"f" + struct.pack(">d", float(value)))
    elif isinstance(value, Decimal):
        out.append(b"D" + str(value).encode() + b";")
    elif isinstance(value, str):
        data = value.encode("utf-8")
        out.append(b"s" + str(len(data)).encode() + b":" + data)
    elif isinstance(value, np.ndarray):
        array = np.ascontiguousarray(value)
        out.append(b"a" + array.dtype.str.encode() + b"|" + ",".join(map(str, array.shape)).encode() + b"|" +
                   str(array.nbytes).encode() + b":" + array.tobytes())
    elif isinstance(value, SymbolBars):
        _encode({name: getattr(value, name) for name in SymbolBars.__slots__}, out)
    elif isinstance(value, Mapping):
        out.append(b"d" + str(len(value)).encode() + b"{")
        for key in sorted(value, key=str):
            _encode(str(key), out)
            _encode(value[key], out)
        out.append(b"}")
    elif isinstance(value, (list, tuple)):
        out.append(b"l" + str(len(value)).encode() + b"[")
        for item in value:
            _encode(item, out)
        out.append(b"]")
    else:
        raise TypeError(f"a ctx holds no {type(value).__name__}")


def ctx_bytes(ctx: Ctx) -> bytes:
    """A canonical byte string of everything a ctx holds (arrays by dtype, shape and bytes; dicts sorted): the I6
    test's equality, and the decision's provenance hash (league/equity/live.py records its sha256)."""
    out: list[bytes] = [b"equity-ctx-1;"]
    for name in Ctx.__slots__:
        _encode(name, out)
        _encode(getattr(ctx, name), out)
    return b"".join(out)


__all__ = ["SymbolBars", "Ctx", "Inputs", "as_of", "build", "calendar_around", "inputs_from_bars", "inputs_from_fetch",
           "lot_row", "closed_row", "ctx_bytes"]
