"""Test material for the deep key (league/deep): synthetic deep stores, synthetic equity stores and the in-process runs.

EVERY FIGURE HERE IS GENERATED: geometric Brownian motion on the deep calendar's dates (league/deep/calendar.py, dates
only), with injected splits and dividends, never a market row. Nothing here reads a vendor file, the House or a
sealed key.
"""

from __future__ import annotations

import datetime as dt
import math
import tempfile
import zlib
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from league.deep import blocks, calendar, config

#: A calendar-blind program: momentum over a look-back, entries at the open or the close.
BLIND = '''NEEDS = {"symbols": %(symbols)s, "history": %(history)d, "max_hold_sessions": %(hold)d}
PARAMS = {"look": %(look)d, "gate": %(gate)s}


def decide(ctx):
    out = []
    for p in ctx.positions:
        if p["held_sessions"] >= ctx.params["look"] // 2:
            out.append({"sell": p["id"], "at": %(exit_at)s, "tag": "t"})
    best, score = None, ctx.params["gate"]
    for s in ctx.symbols:
        c = ctx.bars[s].close
        n = ctx.params["look"]
        if len(c) > n and c[-1] == c[-1] and c[-1 - n] == c[-1 - n]:
            r = c[-1] / c[-1 - n] - 1.0
            if r > score:
                best, score = s, r
    held = {p["symbol"] for p in ctx.positions}
    if best is not None and best not in held and len(ctx.positions) < 2:
        out.append({"buy": best, "share": 0.4, "at": %(entry_at)s, "tag": "t"})
    return out
'''


def blind_program(symbols: Sequence[str] = ("SPY", "QQQ"), *, history: int = 40, hold: int = 20, look: int = 10,
                  gate: float = 0.0, entry_at: str = "open", exit_at: str = "open") -> str:
    return BLIND % {"symbols": list(symbols), "history": history, "hold": hold, "look": look, "gate": repr(gate),
                    "entry_at": repr(entry_at), "exit_at": repr(exit_at)}


def gbm(symbol: str, days: Sequence[dt.date], *, seed: int, drift: float = 0.06, vol: float = 0.2,
        splits: Sequence[tuple[dt.date, float]] = (), dividends: Sequence[tuple[dt.date, float]] = ()) -> dict:
    """{"days", "open", "high", "low", "close", "volume", "div", "split"} of a synthetic raw series on `days`."""
    n = len(days)
    index = {d: i for i, d in enumerate(days)}
    div, split = np.zeros(n), np.ones(n)
    for day, amount in dividends:
        div[index[day]] += float(amount)
    for day, factor in splits:
        split[index[day]] *= float(factor)
    rng = np.random.default_rng([int(seed), zlib.crc32(symbol.encode())])
    sd = vol / math.sqrt(252.0)
    mu = drift / 252.0 - 0.5 * sd * sd
    over = rng.normal(0.2 * mu, sd * math.sqrt(0.2), n)
    intra = rng.normal(0.8 * mu, sd * math.sqrt(0.8), n)
    wick = np.abs(rng.normal(0.0, 0.3 * sd, (n, 2)))
    price = 40.0 + float(zlib.crc32(symbol.encode()) % 300)
    o, h, lo, c = (np.empty(n) for _ in range(4))
    for i in range(n):
        o[i] = round(max((price - div[i]) / split[i], 0.01) * math.exp(over[i]), 4)
        c[i] = round(o[i] * math.exp(intra[i]), 4)
        h[i] = round(max(o[i], c[i]) * (1 + wick[i, 0]), 4)
        lo[i] = round(min(o[i], c[i]) * (1 - wick[i, 1]), 4)
        price = c[i]
    return {"days": list(days), "open": o, "high": h, "low": lo, "close": c,
            "volume": rng.integers(1_000_000, 9_000_000, n).astype(float), "div": div, "split": split}


def deep_store(root: Path, symbols: Sequence[str] = ("SPY", "QQQ"), *, seed: int = 5,
               inception: Mapping[str, dt.date] | None = None, stale_clean: bool = True,
               edge: Mapping[str, float] | None = None) -> Path:
    """A synthetic deep store at `root` (league/deep/blocks.py `write_store`): every symbol's bars on the deep
    calendar from its inception (default 1999-01-04), quarterly dividends, a split for the first symbol in 2004, the
    three spans written as the data job writes them (`sealed/` with the mark), an audit whose stale-close verdicts
    are `stale_clean`."""
    days = calendar.deep_sessions()
    by_span: dict[str, dict[str, bytes]] = {span: {} for span in config.SPANS}
    for k, sym in enumerate(symbols):
        first = (inception or {}).get(sym, days[0])
        mine = [d for d in days if d >= first]
        dividends = [(mine[i], 0.25 + 0.01 * k) for i in range(50, len(mine), 63)]
        split_day = next(d for d in mine if d >= dt.date(2004, 3, 1))
        splits = [(split_day, 2.0)] if k == 0 else []
        series = gbm(sym, mine, seed=seed, drift=(edge or {}).get(sym, 0.06), splits=splits, dividends=dividends)
        for span, (lo, hi) in config.SPANS.items():
            keep = [i for i, d in enumerate(mine) if lo <= d <= hi]
            if not keep:
                continue
            by_span[span][sym] = blocks.block_bytes([mine[i] for i in keep],
                                                    {c: np.asarray(series[c])[keep] for c in blocks.COLUMNS})
    audit = {"ok": True, "stale": {s: {"clean": stale_clean} for s in symbols}}
    blocks.write_store(root, by_span, audit=audit, source="synthetic", written_at="2026-10-17T00:00:00Z")
    return root


class InlineRuns:
    """`league.deep.gate.Runs` over the in-process decider (tests only): the Train-era runs on a synthetic equity
    store, a run on any store root, and the recent windows' r arrays from that store's Validation and look windows."""

    def __init__(self, equity_root: Path):
        from league.equity.runner import Isolated
        from league.live.decider import InlineDecider

        self.decider = InlineDecider()
        self.equity_root = Path(equity_root)
        self.isolated = Isolated(self.decider, self.equity_root)
        self.calls: list[tuple[str, Any]] = []

    def needs(self, code: str, params: Mapping[str, Any]) -> Mapping[str, Any]:
        return self.isolated.needs(code, params, name="deep")

    def segments(self, code: str, params: Mapping[str, Any]) -> list[Any]:
        self.calls.append(("segments", None))
        return self.isolated.segments(code, params, name="deep")

    def on_store(self, root: Path, code: str, params: Mapping[str, Any], start: dt.date, end: dt.date,
                 k: float) -> Any:
        from league.equity.runner import Isolated

        self.calls.append(("on_store", Path(root)))
        return Isolated(self.decider, root).train(code, params, name="deep", start=start, end=end, k=k)

    def recent(self, code: str, params: Mapping[str, Any]) -> list[np.ndarray]:
        from league.equity import screen
        from league.equity.store import mint_equity_gate_capability

        self.calls.append(("recent", None))
        needs = self.needs(code, params)
        r = self.isolated.train(code, params, name="deep", start=config.RESERVE[0], end=config.RESERVE[1], k=1.0)
        v = self.isolated.validation(code, params, name="deep", k=1.0)
        cap = mint_equity_gate_capability(self.equity_root, "deep-test")
        h = self.isolated.look(code, params, name="deep", gate=cap, k=1.0)
        return [screen.series(run.result["lots"], run.bars, universe=needs["symbols"], capital=1000).r
                for run in (r, v, h)]


def equity_store(root: Path, symbols: Sequence[str] = ("SPY", "QQQ"), *, seed: int = 9) -> Path:
    """A synthetic equity store 2016-01-04..2026-10-09 with the GATE mark (the look window opens for the test's
    capability)."""
    from league.equity import synth

    return synth.synthetic_store(root, symbols=symbols, start=dt.date(2016, 1, 4), end=dt.date(2026, 10, 9),
                                 seed=seed, drift=0.06, vol=0.2, gate=True)


def tmpdir(case: Any) -> Path:
    tmp = tempfile.TemporaryDirectory(prefix="deep-test-")
    case.addCleanup(tmp.cleanup)
    return Path(tmp.name)


__all__ = ["BLIND", "blind_program", "gbm", "deep_store", "InlineRuns", "equity_store", "tmpdir"]
