"""A synthetic equity store for tests: geometric Brownian motion on the true NYSE calendar, never market data.

Owner: core. Every package's tests that need a store build one here (the engine's golden P&L, the screen's floor on a
synthetic store, the I6 test, the book's bar reads, ops' audit), through `store.write_store`, so the layout is one.
Splits and dividends are injected where asked, so the as-of adjustment, the dividend booking and the audit's split
detection have something to find. A synthetic store is marked `"source": "synthetic"` in its manifest.

THE PATH: per symbol (its own seeded stream, so adding a symbol moves no other), a session's overnight and intraday
log-moves are normal with the year's `drift` and `vol` split 20/80 between them; the raw open is the previous raw close
less the session's dividend, divided by its split factor, times the overnight move; high and low wrap open and close.
Prices are rounded to 4 decimals (the venue's precision). adjustment=all is computed from the raw path and the events
on or before the fetch day (`as_of`, default `end`): every price before an event's ex-day is multiplied by
(1 - dividend / the previous raw close) / split factor, then rounded to 4 decimals, as a vendor's would be. A store
written `as_of` an earlier day holds that day's fetch: the same raw path through it, the later events not yet applied.

THE I6 HELPERS (the hooks package's same-ctx test, and core's): `bar_rows` turns a slice's arrays into Alpaca 1Day
rows ({t, o, h, l, c, v}, t the session's New York midnight in UTC), and `same_ctx_cases` draws sessions of a store and
returns, for each, the Gym's `ctx.Inputs` and the rows a live fetch through that session would hold, so a test feeds
the rows to the live builder (`ctx.inputs_from_fetch`, or the book's path) and compares `ctx.ctx_bytes`.

Standard library and numpy only.
"""

from __future__ import annotations

import datetime as dt
import math
import random
import zlib
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from . import config
from .store import (ALL_COLUMNS, RAW_COLUMNS, EquityStore, as_date, from_ordinal, nyse_sessions, write_store)


def _class(symbol: str) -> str:
    return config.class_of(symbol) or config.ETF


def synthetic_store(root: str | Path, *, symbols: Sequence[str] = ("SPY", "QQQ", "IWM", "DIA"),
                    start: dt.date = dt.date(2016, 1, 4), end: dt.date = dt.date(2026, 10, 9), seed: int = 7,
                    drift: float = 0.0, vol: float = 0.18,
                    splits: Mapping[str, Sequence[tuple[dt.date, float]]] | None = None,
                    dividends: Mapping[str, Sequence[tuple[dt.date, float]]] | None = None, gate: bool = False,
                    gaps: Mapping[str, Sequence[dt.date]] | None = None, as_of: dt.date | None = None) -> Path:
    """Write a synthetic store at `root` (the sessions of `store.nyse_sessions(start, end)`) and
    return its path. `splits[sym]`: (ex-day, factor) pairs (2.0 = a 2-for-1). `dividends[sym]`: (ex-day, dollars a
    share). `gaps[sym]`: sessions the symbol has no bar on (an audit failure to find). Deterministic in `seed`.
    `as_of`: the fetch day (default `end`): bars through it, adjustment=all applying the events through it only."""
    sessions = nyse_sessions(start, end)
    if not sessions:
        raise ValueError(f"no session from {start} to {end}")
    days = [d for d, _ in sessions]
    through = days[-1] if as_of is None else max((d for d in days if d <= as_of), default=None)
    if through is None:
        raise ValueError(f"no session on or before {as_of}")
    index = {d: i for i, d in enumerate(days)}
    n = len(days)
    series: dict[str, dict[str, Any]] = {}
    for symbol in symbols:
        sym = str(symbol).strip().upper()
        div = np.zeros(n)
        split = np.ones(n)
        for day, amount in (dividends or {}).get(sym, ()):
            if as_date(day) not in index:
                raise ValueError(f"{sym}'s dividend ex-day {day} is not a session")
            div[index[as_date(day)]] += float(amount)
        for day, factor in (splits or {}).get(sym, ()):
            if as_date(day) not in index:
                raise ValueError(f"{sym}'s split ex-day {day} is not a session")
            split[index[as_date(day)]] *= float(factor)
        rng = np.random.default_rng([int(seed), zlib.crc32(sym.encode())])
        sd = float(vol) / math.sqrt(252.0)
        mu = float(drift) / 252.0 - 0.5 * sd * sd
        overnight = rng.normal(0.2 * mu, sd * math.sqrt(0.2), n)
        intraday = rng.normal(0.8 * mu, sd * math.sqrt(0.8), n)
        wicks = np.abs(rng.normal(0.0, 0.3 * sd, (n, 2)))
        volume = rng.integers(1_000_000, 50_000_000, n).astype(np.float64)
        price = 50.0 + float(zlib.crc32(sym.encode()) % 400)
        o, h, low, c = (np.empty(n) for _ in range(4))
        for i in range(n):
            o[i] = round(max((price - div[i]) / split[i], 0.01) * math.exp(overnight[i]), 4)
            c[i] = round(o[i] * math.exp(intraday[i]), 4)
            h[i] = round(max(o[i], c[i]) * (1.0 + wicks[i, 0]), 4)
            low[i] = round(min(o[i], c[i]) * (1.0 - wicks[i, 1]), 4)
            price = c[i]
        # adjustment=all as of the fetch day: each event on or before it scales every earlier price.
        factor = np.ones(n)
        step = 1.0
        for i in range(n - 1, 0, -1):
            if days[i] <= through and (div[i] or split[i] != 1.0):
                step *= (1.0 - div[i] / c[i - 1]) / split[i]
            factor[i - 1] = step
        missing = {as_date(d) for d in (gaps or {}).get(sym, ())}
        keep = [i for i, d in enumerate(days) if d <= through and d not in missing]
        series[sym] = {"days": [days[i] for i in keep]}
        for name, values in zip(RAW_COLUMNS, (o, h, low, c, volume)):
            series[sym][name] = [float(values[i]) for i in keep]
        for name, values in zip(ALL_COLUMNS, (o, h, low, c)):
            series[sym][name] = [round(float(values[i] * factor[i]), 4) for i in keep]
    write_store(root, calendar=[(d, e) for d, e in sessions if d <= through], series=series,
                classes={s: _class(s) for s in series}, fetched_through=through, source="synthetic", gate=gate)
    return Path(root)


def constant_store(root: str | Path, *, symbol: str = "SPY", start: dt.date = dt.date(2025, 1, 2), sessions: int = 20,
                   price: float = 100.0, step: float = 0.0, gate: bool = False) -> Path:
    """A store whose one symbol opens and closes at `price` + i x `step` on session i (open = close of the same day,
    high = low = close): hand-checkable golden P&L."""
    days = nyse_sessions(start, start + dt.timedelta(days=int(sessions) * 2 + 14))[:int(sessions)]
    if len(days) < int(sessions):
        raise ValueError("not enough sessions after start")
    sym = symbol.strip().upper()
    values = [round(float(price) + i * float(step), 4) for i in range(len(days))]
    row: dict[str, Any] = {"days": [d for d, _ in days], "raw_v": [1_000_000.0] * len(days)}
    for name in ("raw_o", "raw_h", "raw_l", "raw_c", "all_o", "all_h", "all_l", "all_c"):
        row[name] = list(values)
    write_store(root, calendar=days, series={sym: row}, classes={sym: _class(sym)}, fetched_through=days[-1][0],
                source="synthetic", gate=gate)
    return Path(root)


def _stamp(day: dt.date) -> str:
    from ltcm.data import NEW_YORK

    return dt.datetime.combine(day, dt.time(0), NEW_YORK).astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def bar_rows(bars: Any, symbol: str, t: int, *, adjustment: str) -> list[dict[str, Any]]:
    """The Alpaca 1Day rows ({t, o, h, l, c, v}) a fetch of `symbol` through session index `t` of `bars` holds, for
    adjustment "raw" or "all" (the all rows' v is the raw volume: the ctx reads volume from the raw rows only)."""
    if adjustment not in ("raw", "all"):
        raise ValueError("adjustment is raw or all")
    raw, adj = bars.raw[symbol], bars.adj[symbol]
    out = []
    for i in range(int(t) + 1):
        if not np.isfinite(raw[i, 3]):
            continue
        prices = raw[i, :4] if adjustment == "raw" else adj[i, :4]
        out.append({"t": _stamp(from_ordinal(int(bars.days[i]))), "o": float(prices[0]), "h": float(prices[1]),
                    "l": float(prices[2]), "c": float(prices[3]), "v": float(raw[i, 4])})
    return out


def same_ctx_cases(store_root: str | Path, *, symbols: Sequence[str] = ("SPY", "QQQ"), history: int = 20,
                   count: int = 20, seed: int = 0, window: str = "validation", gate: Any = None,
                   cash: float = 1000.0, equity: float = 1000.0, budget: float = 1000.0,
                   params: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    """`count` sessions of `window` drawn with `seed`, each {"day" (ISO), "index", "needs" (a `program.Needs`), "gym"
    (the Gym's `ctx.Inputs` at that session), "raw_rows" and "all_rows" ({sym: Alpaca rows through that session}),
    "common" (the keyword arguments both builders take: positions, cash, equity, budget, caps, params)}. The I6 test
    builds the live ctx from the rows and compares `ctx.ctx_bytes` with the Gym's."""
    from .ctx import inputs_from_bars
    from .program import Needs

    names = tuple(str(s).strip().upper() for s in symbols)
    needs = Needs(names, int(history), config.DEFAULT_MAX_HOLD)
    bars = EquityStore(store_root, gate=gate).bars(names, window, history=int(history))
    picks = sorted(random.Random(seed).sample(range(bars.first, bars.n), min(int(count), bars.n - bars.first)))
    cases = []
    for t in picks:
        common = {"positions": [{"id": 1, "symbol": names[0], "class": _class(names[0]), "qty": 1.5, "entry": 100.0,
                                 "mark": 101.0, "value": 151.5, "pnl": 1.5, "held_sessions": 2, "at": "close",
                                 "tag": "i6"}],
                  "cash": float(cash), "equity": float(equity), "budget": float(budget),
                  "caps": {s: 100.0 for s in names}, "params": dict(params or {"theta": 0.02})}
        cases.append({"day": from_ordinal(int(bars.days[t])).isoformat(), "index": t, "needs": needs,
                      "gym": inputs_from_bars(bars, t, needs=needs, **common),
                      "raw_rows": {s: bar_rows(bars, s, t, adjustment="raw") for s in names},
                      "all_rows": {s: bar_rows(bars, s, t, adjustment="all") for s in names}, "common": common})
    return cases


__all__ = ["synthetic_store", "constant_store", "bar_rows", "same_ctx_cases"]
