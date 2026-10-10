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
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import numpy as np


class SymbolBars:
    """One symbol's daily history as a program sees it (read-only arrays, oldest first, last = session t)."""

    __slots__ = ("symbol", "open", "high", "low", "close", "volume", "ret")

    def __init__(self, symbol: str, open: np.ndarray, high: np.ndarray, low: np.ndarray, close: np.ndarray,
                 volume: np.ndarray, ret: np.ndarray):
        raise NotImplementedError("core: league/equity/ctx.py SymbolBars")


class Ctx:
    """What decide(ctx) receives (EQUITY.md). Read its attributes; never assign them."""

    __slots__ = ("symbols", "bars", "prices", "weekday", "events", "events_next", "session_of_month",
                 "sessions_to_month_end", "positions", "orders", "closed", "rejects", "cash", "equity", "budget", "caps",
                 "params")

    def __init__(self, **values: Any):
        raise NotImplementedError("core: league/equity/ctx.py Ctx")


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
    raise NotImplementedError("core: league/equity/ctx.py as_of")


def build(inputs: Inputs) -> Ctx:
    """THE constructor of an equity ctx (the Gym's and the live path's one)."""
    raise NotImplementedError("core: league/equity/ctx.py build")


def inputs_from_bars(bars: Any, t: int, *, needs: Any, positions: Sequence[dict] = (), orders: Sequence[dict] = (),
                     closed: Sequence[dict] = (), rejects: Sequence[str] = (), cash: float, equity: float,
                     budget: float, caps: Mapping[str, float], params: Mapping[str, Any]) -> Inputs:
    """The Gym's inputs at session index `t` of a `store.Bars` (never a row after t): `needs` is a
    `program.Needs`."""
    raise NotImplementedError("core: league/equity/ctx.py inputs_from_bars")


def inputs_from_fetch(raw_rows: Mapping[str, Sequence[Mapping[str, Any]]],
                      all_rows: Mapping[str, Sequence[Mapping[str, Any]]], *, day: Any, needs: Any,
                      positions: Sequence[dict] = (), orders: Sequence[dict] = (), closed: Sequence[dict] = (),
                      rejects: Sequence[str] = (), cash: float, equity: float, budget: float,
                      caps: Mapping[str, float], params: Mapping[str, Any]) -> Inputs:
    """The live path's inputs from the 16:20 fetch: Alpaca 1Day bar rows ({t, o, h, l, c, v}) per symbol for
    adjustment=raw and adjustment=all through `day` (an ISO day or date: session t). ValueError when session t's bar is
    missing for a NEEDS symbol or the two series disagree on their sessions."""
    raise NotImplementedError("core: league/equity/ctx.py inputs_from_fetch")


def lot_row(*, lid: int, symbol: str, klass: str, qty: float, entry: float, mark: float, held_sessions: int, at: str,
            tag: str = "") -> dict:
    """One open lot as a program sees it: {id, symbol, class, qty, entry, mark, value (qty x mark), pnl ((mark - entry)
    x qty), held_sessions, at, tag}; floats rounded to 4 decimals (qty to 6)."""
    raise NotImplementedError("core: league/equity/ctx.py lot_row")


def closed_row(*, lid: int, symbol: str, qty: float, entry: float, exit: float, net: float, held_sessions: int,
               reason: str, tag: str = "") -> dict:
    """One lot closed since the last call: {id, symbol, qty, entry, exit, net (dollars after fees and dividends),
    held_sessions, reason ("program" | "max_hold" | "house"), tag}."""
    raise NotImplementedError("core: league/equity/ctx.py closed_row")


def ctx_bytes(ctx: Ctx) -> bytes:
    """A canonical byte string of everything a ctx holds (arrays by dtype, shape and bytes; dicts sorted): the I6
    test's equality, and the decision's provenance hash (league/equity/live.py records its sha256)."""
    raise NotImplementedError("core: league/equity/ctx.py ctx_bytes")


__all__ = ["SymbolBars", "Ctx", "Inputs", "as_of", "build", "inputs_from_bars", "inputs_from_fetch", "lot_row",
           "closed_row", "ctx_bytes"]
