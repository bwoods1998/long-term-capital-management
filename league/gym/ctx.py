"""Building `ctx` from plain arrays for one minute: what a program sees, in a replay and live alike.

The replay (`engine.py`) builds a `Snapshot` per root and minute from its recorded grid; the live
path builds one from a chain read (per contract: days to expiry, strike, right, bid, ask, sizes, open
interest) and the underlying's price. Everything a program sees comes out of the functions here, so
the Gym and the House can never disagree about it:

    snap = Snapshot(root, minute, spot, dte, strike, is_call, bid, ask, bid_size, ask_size, oi=oi, rate=r)
    chain = snap.view(snap.slice_index(needs.dte_min, needs.dte_max, needs.band))
    under = underlying_view(root, prices_today, closes=..., highs=..., lows=..., opens=...)
    ctx = build_ctx(minute=..., open_minute=..., close_minute=..., weekday=..., chains={root: chain},
                    underlyings={root: under}, positions=[position_row(...)], orders=[order_row(...)],
                    cash=..., equity=..., budget=..., buying_power=..., params=program.params,
                    rules={root: rules_for(root).as_dict()}, events=..., events_next=...)

A program never sees a date or a year: days to expiry, minutes since midnight ET, the weekday, and
event booleans only. Every array it is handed is a read-only copy (a view of the engine's day grid
would carry the rest of the day in its `.base`, and `base` is refused by the safety check as well).

Implied vol and the greeks are computed on the mid (`greeks.py`) only when a program first reads one,
for the contracts it was shown, and cached in the snapshot (so a batch of programs pays once).
numpy only; Python 3.11+.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

import numpy as np

from . import greeks as G

_NAN = float("nan")


def _ro(array: np.ndarray) -> np.ndarray:
    array.flags.writeable = False
    return array


class Snapshot:
    """One root's whole chain at one minute. Arrays are per contract; a missing quote is NaN.
    `keys` are the contracts' identities (the engine's int64 keys; the live path may pass any stable
    int64 per contract); `iv_guess` warm-starts the implied-vol solve (the previous minute's)."""

    def __init__(self, root: str, minute: int, spot: float, dte: Any, strike: Any, is_call: Any, bid: Any, ask: Any,
                 bid_size: Any = None, ask_size: Any = None, *, oi: Any = None, rate: float = 0.0,
                 close_minute: int = 960, keys: Any = None, iv_guess: Any = None, greeks_source: Any = None,
                 clean: bool = False):
        self.root = str(root).upper()
        self.minute = int(minute)
        self.spot = float(spot) if spot is not None and np.isfinite(spot) and spot > 0 else _NAN
        self.dte = np.asarray(dte, dtype=np.int16)
        self.strike = np.asarray(strike, dtype=np.float64)
        self.is_call = np.asarray(is_call, dtype=bool)
        n = self.strike.shape[0]
        if clean:
            # The replay's rows: already float64, rounded, and NaN wherever the quote is not two-sided.
            self.bid = bid
            self.ask = ask
            self.valid = ~np.isnan(bid)
        else:
            # Quotes come in whole cents (sub-penny at most); float32 carries ~1e-7 of noise, so prices
            # are rounded to 1e-4 here.
            bid = np.round(np.asarray(bid, dtype=np.float64), 4)
            ask = np.round(np.asarray(ask, dtype=np.float64), 4)
            with np.errstate(invalid="ignore"):
                self.valid = np.isfinite(bid) & np.isfinite(ask) & (ask > 0) & (bid >= 0) & (ask >= bid)
            self.bid = np.where(self.valid, bid, _NAN)
            self.ask = np.where(self.valid, ask, _NAN)
        self.mid = 0.5 * (self.bid + self.ask)
        zeros = np.zeros(n, dtype=np.int32)
        if clean:
            self.bid_size = bid_size
            self.ask_size = ask_size
        else:
            self.bid_size = np.where(self.valid, np.asarray(bid_size if bid_size is not None else zeros, dtype=np.int32), 0)
            self.ask_size = np.where(self.valid, np.asarray(ask_size if ask_size is not None else zeros, dtype=np.int32), 0)
        self.oi = np.asarray(oi, dtype=np.int64) if oi is not None else np.zeros(n, dtype=np.int64)
        self.keys = np.asarray(keys, dtype=np.int64) if keys is not None else np.arange(n, dtype=np.int64)
        self.rate = float(rate)
        self.close_minute = int(close_minute)
        self._guess = None if iv_guess is None else np.asarray(iv_guess, dtype=np.float64)
        #: The replay's block cache (`engine.GreekBlocks`): computes this minute's greeks together with
        #: the batch's next decision minutes, engine-side. None live: solved here, per minute.
        self._source = greeks_source
        greeks = np.full((5, n), _NAN)
        self._iv, self._delta, self._gamma, self._theta, self._vega = greeks
        self._done = np.zeros(n, dtype=bool)
        self._views: dict[tuple, "ChainView"] = {}

    @property
    def n(self) -> int:
        return int(self.strike.shape[0])

    def greeks_for(self, idx: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """(iv, delta, gamma, theta, vega) of the contracts at `idx`, computing what is not yet known."""
        idx = np.asarray(idx, dtype=np.int64)
        need = idx[~self._done[idx]]
        if need.size and self._source is not None:
            iv, d, g, t, v = self._source(need)
            quoted = self.valid[need]
            for store, values in ((self._iv, iv), (self._delta, d), (self._gamma, g), (self._theta, t), (self._vega, v)):
                store[need] = np.where(quoted, values, _NAN)
        elif need.size and np.isfinite(self.spot):
            need = np.unique(need)
            years = G.years_to_expiry(self.dte[need], self.minute, close_minute=self.close_minute)
            guess = None if self._guess is None else self._guess[need]
            iv = G.implied_vol(self.mid[need], self.spot, self.strike[need], years, self.rate, self.is_call[need], guess=guess)
            d, g, t, v = G.greeks(self.spot, self.strike[need], years, self.rate, iv, self.is_call[need])
            quoted = self.valid[need]
            self._iv[need] = np.where(quoted, iv, _NAN)
            self._delta[need] = np.where(quoted, d, _NAN)
            self._gamma[need] = np.where(quoted, g, _NAN)
            self._theta[need] = np.where(quoted, t, _NAN)
            self._vega[need] = np.where(quoted, v, _NAN)
        self._done[need] = True
        return self._iv[idx], self._delta[idx], self._gamma[idx], self._theta[idx], self._vega[idx]

    @property
    def iv_known(self) -> np.ndarray:
        """The implied vols computed so far (NaN elsewhere): the next minute's warm start."""
        return self._iv

    def slice_index(self, dte_min: int, dte_max: int, band: float) -> np.ndarray:
        """Contracts with a two-sided quote, dte_min <= days to expiry <= dte_max and a strike within
        +-band of spot, in the store's order (expiry, strike, call before put)."""
        if not np.isfinite(self.spot):
            return np.zeros(0, dtype=np.int64)
        with np.errstate(invalid="ignore"):
            mask = self.valid & (self.dte >= dte_min) & (self.dte <= dte_max) & \
                (np.abs(self.strike / self.spot - 1.0) <= band)
        return np.flatnonzero(mask)

    def view(self, idx: np.ndarray, key: tuple | None = None) -> "ChainView":
        """The program-facing chain for contracts `idx` (read-only copies; cached by `key`)."""
        if key is not None and key in self._views:
            return self._views[key]
        found = ChainView(self, np.asarray(idx, dtype=np.int64))
        if key is not None:
            self._views[key] = found
        return found


class ChainView:
    """One root's chain slice at one minute (PROGRAM.md, "ctx.chain"). Arrays, one entry a contract,
    sorted by expiry, strike, call before put: `id` (the contract's id today: name it in a leg as
    {"id": ...}), `dte`, `strike`, `is_call`, `bid`, `ask`, `mid`, `spread`, `bid_size`, `ask_size`,
    `oi`; computed on first read: `iv`, `delta`, `gamma`, `theta` (a calendar day), `vega` (a vol
    point). `expiries` lists the days to expiry present; `spot` is the underlying now."""

    __slots__ = ("root", "spot", "minute", "n", "id", "dte", "strike", "is_call", "bid", "ask", "mid", "spread",
                 "bid_size", "ask_size", "oi", "expiries", "_snap", "_idx", "_greeks")

    def __init__(self, snap: Snapshot, idx: np.ndarray):
        self._snap = snap
        self._idx = idx
        self._greeks = None
        self.root = snap.root
        self.spot = snap.spot
        self.minute = snap.minute
        self.n = int(idx.shape[0])
        self.id = _ro(idx.astype(np.int32))
        self.dte = _ro(snap.dte[idx].astype(np.int32))
        self.strike = _ro(snap.strike[idx])
        self.is_call = _ro(snap.is_call[idx])
        self.bid = _ro(snap.bid[idx])
        self.ask = _ro(snap.ask[idx])
        self.mid = _ro(snap.mid[idx])
        self.spread = _ro(self.ask - self.bid)
        self.bid_size = _ro(snap.bid_size[idx])
        self.ask_size = _ro(snap.ask_size[idx])
        self.oi = _ro(snap.oi[idx])
        self.expiries = _ro(np.unique(self.dte))

    def __len__(self) -> int:
        return self.n

    def _g(self, k: int) -> np.ndarray:
        if self._greeks is None:
            self._greeks = tuple(_ro(np.array(a)) for a in self._snap.greeks_for(self._idx))
        return self._greeks[k]

    @property
    def iv(self) -> np.ndarray:
        return self._g(0)

    @property
    def delta(self) -> np.ndarray:
        return self._g(1)

    @property
    def gamma(self) -> np.ndarray:
        return self._g(2)

    @property
    def theta(self) -> np.ndarray:
        return self._g(3)

    @property
    def vega(self) -> np.ndarray:
        return self._g(4)


class UnderlyingView:
    """The underlying of one root (PROGRAM.md, "ctx.under"): `price` now; today's one-minute `prices`
    from the open to now; `open`, `high`, `low` of today so far; the prior sessions (oldest first,
    up to NEEDS["history"]) as `closes`, `opens`, `highs`, `lows`; `prior_close`."""

    __slots__ = ("root", "price", "prices", "open", "high", "low", "prior_close", "closes", "opens", "highs", "lows")

    def __init__(self, root: str, prices: np.ndarray, closes: np.ndarray, opens: np.ndarray, highs: np.ndarray,
                 lows: np.ndarray):
        self.root = root
        self.prices = _ro(prices)
        self.price = float(prices[-1]) if prices.shape[0] else _NAN
        self.open = float(prices[0]) if prices.shape[0] else _NAN
        self.high = float(prices.max()) if prices.shape[0] else _NAN
        self.low = float(prices.min()) if prices.shape[0] else _NAN
        self.closes = _ro(closes)
        self.opens = _ro(opens)
        self.highs = _ro(highs)
        self.lows = _ro(lows)
        self.prior_close = float(closes[-1]) if closes.shape[0] else _NAN


def underlying_view(root: str, prices_today: Sequence[float], *, closes: Sequence[float] = (), opens: Sequence[float] = (),
                    highs: Sequence[float] = (), lows: Sequence[float] = ()) -> UnderlyingView:
    """`prices_today`: the price at each minute from the open through NOW (never later); missing
    minutes should already hold the price in force before them. The history is the prior sessions."""
    prices = np.asarray(prices_today, dtype=np.float64)
    prices = prices[np.isfinite(prices)].copy()
    as_array = lambda xs: np.asarray(xs, dtype=np.float64).copy()  # noqa: E731
    return UnderlyingView(str(root).upper(), prices, as_array(closes), as_array(opens), as_array(highs), as_array(lows))


def parity_spot(dte: Any, strike: Any, is_call: Any, mid: Any, near: float, *, strikes: int = 3) -> float:
    """The index level from put-call parity on the nearest expiry: the median over the `strikes`
    strikes nearest `near` (a rough level: the last known one) of K + C_mid - P_mid. NaN when no
    strike has both a call and a put quoted. The live path's spot for XSP and SPXW (Alpaca has no
    index feed); the Gym's store carries the recorded level, which this reproduces within a spread."""
    dte = np.asarray(dte)
    strike = np.asarray(strike, dtype=np.float64)
    is_call = np.asarray(is_call, dtype=bool)
    mid = np.asarray(mid, dtype=np.float64)
    ok = np.isfinite(mid)
    if not ok.any() or not np.isfinite(near):
        return _NAN
    first = int(dte[ok].min())
    sel = ok & (dte == first)
    calls = {float(k): float(m) for k, m in zip(strike[sel & is_call], mid[sel & is_call])}
    puts = {float(k): float(m) for k, m in zip(strike[sel & ~is_call], mid[sel & ~is_call])}
    both = sorted(set(calls) & set(puts), key=lambda k: abs(k - near))[:strikes]
    if not both:
        return _NAN
    return float(np.median([k + calls[k] - puts[k] for k in both]))


class Ctx:
    """What decide(ctx) receives (PROGRAM.md). Read its attributes; never assign them."""

    __slots__ = ("minute", "open_minute", "close_minute", "minutes_to_close", "weekday", "events", "events_next",
                 "roots", "root", "chains", "chain", "underlyings", "under", "positions", "orders", "closed", "rejects",
                 "cash", "equity", "budget", "buying_power", "params", "rules")

    def __init__(self, **values: Any):
        for name in self.__slots__:
            object.__setattr__(self, name, values.get(name))


def build_ctx(*, minute: int, open_minute: int, close_minute: int, weekday: int, chains: Mapping[str, ChainView],
              underlyings: Mapping[str, UnderlyingView], positions: Sequence[dict], orders: Sequence[dict],
              cash: float, equity: float, budget: float, buying_power: float, params: Mapping[str, Any],
              rules: Mapping[str, Mapping[str, Any]], events: Mapping[str, bool], events_next: Mapping[str, bool],
              closed: Sequence[dict] = (), rejects: Sequence[str] = (), roots: Sequence[str] | None = None) -> Ctx:
    """The ctx of one decision (the replay's and the live path's one constructor)."""
    roots = tuple(roots or chains.keys())
    first = roots[0] if roots else None
    return Ctx(
        minute=int(minute), open_minute=int(open_minute), close_minute=int(close_minute),
        minutes_to_close=int(close_minute) - int(minute), weekday=int(weekday),
        events=dict(events), events_next=dict(events_next), roots=roots, root=first,
        chains=dict(chains), chain=chains.get(first) if first else None,
        underlyings=dict(underlyings), under=underlyings.get(first) if first else None,
        positions=[dict(p) for p in positions], orders=[dict(o) for o in orders], closed=[dict(c) for c in closed],
        rejects=list(rejects), cash=float(cash), equity=float(equity), budget=float(budget),
        buying_power=float(buying_power), params=dict(params), rules={k: dict(v) for k, v in rules.items()},
    )


def position_row(*, pid: int, type_: str, root: str, qty: int, legs: Sequence[dict], entry: float, max_loss: float,
                 mark: float, natural: float, held_minutes: int, held_days: int, tag: str = "") -> dict:
    """One open position as a program sees it. `legs`: [{"id", "dte", "strike", "is_call", "side", "ratio"}]
    (id -1 when the contract is not in today's chain). `entry`, `mark` and `natural` are the structure's
    value a share (positive: worth paying for; a credit structure's is negative): what it was opened at,
    its mid now, and what closing it now at the natural price would get. `pnl` is at the mark."""
    return {"id": int(pid), "type": type_, "root": root, "qty": int(qty), "legs": [dict(x) for x in legs],
            "entry": round(float(entry), 4), "credit": float(entry) < 0, "max_loss": round(float(max_loss), 2),
            "mark": None if not np.isfinite(mark) else round(float(mark), 4),
            "natural": None if not np.isfinite(natural) else round(float(natural), 4),
            "pnl": None if not np.isfinite(mark) else round((float(mark) - float(entry)) * 100.0 * int(qty), 2),
            "held_minutes": int(held_minutes), "held_days": int(held_days), "tag": str(tag or "")}


def order_row(*, oid: int, kind: str, type_: str, root: str, qty: int, filled: int, limit: float, age_minutes: int,
              position: int | None = None, tag: str = "") -> dict:
    """One working order as a program sees it (`kind` is "open" or "close")."""
    return {"id": int(oid), "kind": kind, "type": type_, "root": root, "qty": int(qty), "filled": int(filled),
            "limit": round(float(limit), 4), "age_minutes": int(age_minutes), "position": position, "tag": str(tag or "")}


__all__ = ["Snapshot", "ChainView", "UnderlyingView", "Ctx", "build_ctx", "underlying_view", "position_row", "order_row",
           "parity_spot"]
