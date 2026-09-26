"""Live option chains as the Gym's day grids: one root's session as [minute, contract] arrays, filled a minute at a time.

The options-swarm run, Wave 5 (Sept 26, 2026). The Gym's replay (`league/gym/engine.py`) reads a recorded day as a
`DayChain` (dense [minute, contract] grids, contracts sorted by expiry, strike, call before put, keyed by
`contract_key`) and hands its accounts a `DayData`. The live path builds the SAME two shapes from live reads, so the
Gym's own `Account` (the shadow book), `Snapshot`, `build_ctx` and `legs.resolve_*` run unchanged on live quotes and the
Gym and the House can never disagree about what a program saw or how its order filled:

- `LiveChain` holds one root's session: the grids fill as each minute's chain read arrives (row `mi` is the NBBO in
  force at minute `mi`'s start, as in the store), the underlying's price row by row. A quote stamped before today's
  open is not in force today (it is the last session's) and stays NaN. The contract set grows when a read shows a new
  contract (the band follows spot): the arrays are rebuilt in the store's order and every account's indices remapped
  (`LiveDay.remap`).
- `LiveDay` is the `DayData` the Gym's `Account` reads: `snapshot(root, mi)`, `under(root, mi, history)`, the venue's
  rules for the session (a half day's too), the event flags (`league/gym/events.py`) and the rate.
- XSP and SPXW have no index feed at the venue: their level is put-call parity on the nearest expiry's at-the-money
  options (`league.gym.ctx.parity_spot`), the way the Gym's store checks its recorded level.

numpy only (the House has no pyarrow). `contract_key` repeats the store's formula exactly (a test pins them together
where pyarrow is installed).
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

from ..gym import venue as V
from ..gym.ctx import Snapshot, parity_spot, underlying_view
from ..gym.events import EventCalendar, rate_on
from .venue import occ_parts, quote_of

EPOCH = dt.date(1970, 1, 1)
INDEX_UNDERLYING = {"XSP": "XSP", "SPXW": "SPXW", "SPX": "SPX"}


def ordinal(day: dt.date) -> int:
    return (day - EPOCH).days


def from_ordinal(value: int) -> dt.date:
    return EPOCH + dt.timedelta(days=int(value))


def contract_key(expiration: Any, strike: Any, is_call: Any) -> np.ndarray:
    """The store's contract identity (`league.gym.store.contract_key`): (expiration ordinal, strike to the tenth of a
    cent, right), sortable in the store's order (expiry, strike, calls first)."""
    e = np.asarray(expiration, dtype=np.int64)
    k = np.rint(np.asarray(strike, dtype=np.float64) * 1000.0).astype(np.int64)
    c = np.where(np.asarray(is_call, dtype=bool), 0, 1).astype(np.int64)
    return (e * 100_000_000 + k) * 2 + c


def uses_parity(root: str) -> bool:
    return V.is_index(root)


@dataclass
class Underlying:
    """The session's underlying price row by row (NaN before a price is known)."""

    price: np.ndarray


class LiveChain:
    """One root's session so far as the store's `DayChain` shapes."""

    def __init__(self, root: str, day: dt.date, open_min: int, close_min: int):
        self.root = root.upper()
        self.day = day
        self.day_ordinal = ordinal(day)
        self.open_min, self.close_min = int(open_min), int(close_min)
        self.m = self.close_min - self.open_min + 1
        self.key = np.zeros(0, dtype=np.int64)
        self.expiration = np.zeros(0, dtype=np.int32)
        self.dte = np.zeros(0, dtype=np.int16)
        self.strike = np.zeros(0, dtype=np.float64)
        self.is_call = np.zeros(0, dtype=bool)
        self.symbol: list[str] = []
        self.bid = np.full((self.m, 0), np.nan)
        self.ask = np.full((self.m, 0), np.nan)
        self.bid_size = np.zeros((self.m, 0), dtype=np.int32)
        self.ask_size = np.zeros((self.m, 0), dtype=np.int32)
        self.oi = np.zeros(0, dtype=np.int64)
        self.underlying = Underlying(np.full(self.m, np.nan))
        self._col: dict[str, int] = {}
        self.generation = 0          # bumped at every rebuild (indices change)

    @property
    def minutes(self) -> int:
        return self.m

    @property
    def contracts(self) -> int:
        return int(self.strike.shape[0])

    def index_of(self, keys: Any) -> np.ndarray:
        keys = np.asarray(keys, dtype=np.int64)
        if self.key.shape[0] == 0:
            return np.full(keys.shape, -1, dtype=np.int64)
        pos = np.clip(np.searchsorted(self.key, keys), 0, self.key.shape[0] - 1)
        return np.where(self.key[pos] == keys, pos, -1)

    def column(self, symbol: str) -> int:
        return self._col.get(symbol.upper(), -1)

    def _admit(self, symbols: Iterable[str]) -> bool:
        """Add contracts not yet held; rebuild in the store's order. True when the indices changed."""
        fresh = []
        for symbol in symbols:
            s = symbol.upper()
            if s in self._col:
                continue
            parts = occ_parts(s)
            if parts is None or parts[0] != self.root:
                continue
            expiry = dt.date.fromisoformat(parts[1])
            if expiry < self.day:
                continue  # listed yet expired: not tradable today
            fresh.append((s, ordinal(expiry), parts[3], parts[2]))
        if not fresh:
            return False
        old_symbols = list(self.symbol)
        symbols_all = old_symbols + [f[0] for f in fresh]
        exp = np.concatenate([self.expiration.astype(np.int64), np.array([f[1] for f in fresh], dtype=np.int64)])
        strike = np.concatenate([self.strike, np.array([f[2] for f in fresh], dtype=np.float64)])
        call = np.concatenate([self.is_call, np.array([f[3] for f in fresh], dtype=bool)])
        key = contract_key(exp, strike, call)
        order = np.argsort(key, kind="stable")
        n_old = len(old_symbols)
        new_of_old = np.empty(n_old, dtype=np.int64)
        inverse = np.empty(order.shape[0], dtype=np.int64)
        inverse[order] = np.arange(order.shape[0])
        new_of_old[:] = inverse[:n_old]
        c = order.shape[0]
        bid = np.full((self.m, c), np.nan)
        ask = np.full((self.m, c), np.nan)
        bsz = np.zeros((self.m, c), dtype=np.int32)
        asz = np.zeros((self.m, c), dtype=np.int32)
        oi = np.zeros(c, dtype=np.int64)
        if n_old:
            bid[:, new_of_old] = self.bid
            ask[:, new_of_old] = self.ask
            bsz[:, new_of_old] = self.bid_size
            asz[:, new_of_old] = self.ask_size
            oi[new_of_old] = self.oi
        self.key = key[order]
        self.expiration = exp[order].astype(np.int32)
        self.dte = (self.expiration - self.day_ordinal).astype(np.int16)
        self.strike = strike[order]
        self.is_call = call[order]
        self.symbol = [symbols_all[i] for i in order]
        self.bid, self.ask, self.bid_size, self.ask_size, self.oi = bid, ask, bsz, asz, oi
        self._col = {s: i for i, s in enumerate(self.symbol)}
        self.generation += 1
        return True

    def record(self, mi: int, rows: Mapping[str, Mapping[str, Any]], *, open_epoch: float) -> bool:
        """Minute `mi`'s chain read ({OCC: snapshot row}). A quote stamped before today's open, or not two-sided and
        ordered (0 <= bid <= ask, ask > 0), stays NaN. True when the contract set changed."""
        changed = self._admit(rows.keys())
        if not 0 <= mi < self.m:
            return changed
        for symbol, row in rows.items():
            col = self._col.get(symbol.upper())
            if col is None:
                continue
            bid, ask, bs, as_, stamp = quote_of(row)
            if stamp is not None and stamp < open_epoch:
                continue
            if not (math.isfinite(bid) and math.isfinite(ask) and ask > 0 and 0 <= bid <= ask):
                continue
            self.bid[mi, col] = round(bid, 4)
            self.ask[mi, col] = round(ask, 4)
            self.bid_size[mi, col] = bs
            self.ask_size[mi, col] = as_
        return changed

    def set_price(self, mi: int, price: float) -> None:
        """The underlying at minute `mi`; minutes skipped since the last known price hold it (the price in force)."""
        if not 0 <= mi < self.m or not (math.isfinite(price) and price > 0):
            return
        known = np.flatnonzero(np.isfinite(self.underlying.price[:mi]))
        if known.size:
            last = int(known[-1])
            self.underlying.price[last + 1:mi] = self.underlying.price[last]
        self.underlying.price[mi] = price

    def mids(self, mi: int) -> np.ndarray:
        return 0.5 * (self.bid[mi] + self.ask[mi])

    def parity(self, mi: int, near: float) -> float:
        """The root's own level from put-call parity at minute `mi` (NaN when no strike has both sides quoted)."""
        if self.contracts == 0:
            return float("nan")
        mid = self.mids(mi)
        if not math.isfinite(near):
            near = self.crossing(mi)
        return parity_spot(self.dte, self.strike, self.is_call, mid, near)

    def crossing(self, mi: int) -> float:
        """A first guess at the level with nothing known: the nearest expiry's strike where call and put mids cross."""
        mid = self.mids(mi)
        ok = np.isfinite(mid)
        if not ok.any():
            return float("nan")
        first = int(self.dte[ok].min())
        best, gap = float("nan"), float("inf")
        calls = {float(k): float(m) for k, m, c, d, o in zip(self.strike, mid, self.is_call, self.dte, ok) if o and c and d == first}
        puts = {float(k): float(m) for k, m, c, d, o in zip(self.strike, mid, self.is_call, self.dte, ok) if o and not c and d == first}
        for k in set(calls) & set(puts):
            g = abs(calls[k] - puts[k])
            if g < gap:
                best, gap = k, g
        return best


class LiveDay:
    """The `DayData` the Gym's `Account` reads, over live chains (the module docstring)."""

    def __init__(self, day: dt.date, open_min: int, close_min: int, *, trading_days: Sequence[dt.date],
                 session: Any = None, roots: Sequence[str] = ()):
        self.day = day
        self.ordinal = ordinal(day)
        self.weekday = day.weekday()
        self.open_min, self.close_min = int(open_min), int(close_min)
        self.minutes = self.close_min - self.open_min + 1
        self.rate = rate_on(day)
        self.chains: dict[str, LiveChain] = {}
        self.rules: dict[str, V.Rules] = {}
        self.rules_rows: dict[str, dict] = {}
        calendar = EventCalendar(trading_days, session)
        self.events = calendar.flags(day)
        self.events_next = calendar.flags(calendar.next_day(day))
        self.history: dict[str, list[tuple[float, float, float, float]]] = {}  # root -> prior sessions (o, h, l, c)
        self._snaps: dict[tuple[str, int], Snapshot] = {}
        self._unders: dict[tuple[str, int, int], Any] = {}
        self._minute = -1
        for root in roots:
            self.chain(root)

    def chain(self, root: str) -> LiveChain:
        root = root.upper()
        found = self.chains.get(root)
        if found is None:
            found = self.chains[root] = LiveChain(root, self.day, self.open_min, self.close_min)
            self.rules[root] = V.rules_for(root, open_minute=self.open_min, close_minute=self.close_min)
            self.rules_rows[root] = self.rules[root].as_dict()
        return found

    def advance(self, mi: int) -> None:
        if mi != self._minute:
            self._snaps.clear()
            self._unders.clear()
            self._minute = mi

    def invalidate(self) -> None:
        self._snaps.clear()
        self._unders.clear()

    def snapshot(self, root: str, mi: int) -> Snapshot | None:
        """The root's snapshot at minute `mi`, or None when the root has no chain or no price there."""
        key = (root, mi)
        found = self._snaps.get(key)
        if found is not None:
            return found
        chain = self.chains.get(root)
        if chain is None or chain.contracts == 0 or not 0 <= mi < chain.m:
            return None
        spot = float(chain.underlying.price[mi])
        if not math.isfinite(spot):
            return None
        snap = Snapshot(root, self.open_min + mi, spot, chain.dte, chain.strike, chain.is_call, chain.bid[mi],
                        chain.ask[mi], chain.bid_size[mi], chain.ask_size[mi], oi=chain.oi, rate=self.rate,
                        close_minute=self.close_min, keys=chain.key)
        self._snaps[key] = snap
        return snap

    def under(self, root: str, mi: int, history: int):
        key = (root, mi, history)
        found = self._unders.get(key)
        if found is None:
            chain = self.chains[root]
            rows = self.history.get(root, [])[-history:] if history > 0 else []
            a = np.array(rows, dtype=np.float64) if rows else np.zeros((0, 4))
            found = underlying_view(root, chain.underlying.price[: mi + 1], opens=a[:, 0], highs=a[:, 1], lows=a[:, 2],
                                    closes=a[:, 3])
            self._unders[key] = found
        return found

    def remap(self, accounts: Iterable[Any]) -> None:
        """After a chain's contracts changed: every account's positions and working orders find their contracts again
        by identity (the Gym's `Position.idx`, and each working order's legs)."""
        from ..gym.legs import LegFill

        self.invalidate()
        for account in accounts:
            for pos in getattr(account, "positions", {}).values():
                chain = self.chains.get(pos.root)
                pos.idx = chain.index_of(pos.keys) if chain is not None else np.full(len(pos.legs), -1, dtype=np.int64)
            for work in getattr(account, "orders", {}).values():
                chain = self.chains.get(work.order.root)
                if chain is None:
                    continue
                where = chain.index_of(np.array([leg.key for leg in work.order.legs], dtype=np.int64))
                work.order.legs = tuple(LegFill(int(i), leg.key, leg.side, leg.ratio, leg.dte, leg.strike, leg.is_call)
                                        for leg, i in zip(work.order.legs, where))


def trading_days_around(day: dt.date, *, before: int = 90, after: int = 30) -> list[dt.date]:
    """The regular sessions near `day` (`ltcm.data.us_equity_session`, the NYSE calendar)."""
    from ltcm.data import us_equity_session

    out = []
    d = day - dt.timedelta(days=before)
    while d <= day + dt.timedelta(days=after):
        try:
            if us_equity_session(d) is not None:
                out.append(d)
        except ValueError:
            pass
        d += dt.timedelta(days=1)
    return out


def session_minutes(day: dt.date) -> tuple[int, int] | None:
    """(open, close) in minutes since midnight New York for a regular session, or None."""
    from ltcm.data import us_equity_session

    try:
        session = us_equity_session(day)
    except ValueError:
        return None
    if session is None:
        return None
    return 570, (780 if session.early_close else 960)


__all__ = ["LiveChain", "LiveDay", "contract_key", "ordinal", "from_ordinal", "trading_days_around", "session_minutes",
           "uses_parity", "Underlying"]
