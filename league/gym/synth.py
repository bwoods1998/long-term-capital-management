"""A synthetic store-v1: for the Gym's tests and benchmarks. Never licensed data.

Two layers:

- `Writer` writes exactly the files of the fixed layout (VERSION, calendar, expiries, per-day nbbo,
  underlying, oi, trade_quote, manifest, the gate's mark) from arrays the caller chooses: the tests
  build tiny stores with hand-set quotes so a P&L can be checked to the cent.
- `generate` writes a plausible market (a random walk of the underlying, daily expiries 0-14 days
  out, strikes around the money priced by Black-Scholes with a skew, spreads and sizes) for speed
  measurements and smoke runs. Its numbers mean nothing about any real market.

Needs numpy and pyarrow.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import math
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from . import STORE_VERSION
from . import greeks as G
from .store import GATE_MARK, window_of


def _write(table: pa.Table, path: Path) -> tuple[int, str, int]:
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, path, compression="zstd")
    data = path.read_bytes()
    return table.num_rows, hashlib.sha256(data).hexdigest(), len(data)


class Writer:
    """Writes one store root. Call `finish()` last (it writes the manifest)."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "VERSION").write_text(STORE_VERSION + "\n")
        self.rows: list[dict[str, Any]] = []

    def calendar(self, days: Sequence[dt.date], half_days: Iterable[dt.date] = ()) -> None:
        half = set(half_days)
        table = pa.table({"date": pa.array(list(days), pa.date32()),
                          "open_min": pa.array([570] * len(days), pa.int16()),
                          "close_min": pa.array([780 if d in half else 960 for d in days], pa.int16())})
        _write(table, self.root / "calendar.parquet")

    def expiries(self, rows: Sequence[tuple[str, dt.date, dt.date]]) -> None:
        table = pa.table({"root": pa.array([r[0] for r in rows], pa.string()),
                          "date": pa.array([r[1] for r in rows], pa.date32()),
                          "expiration": pa.array([r[2] for r in rows], pa.date32())})
        _write(table, self.root / "expiries.parquet")

    def _record(self, kind: str, root: str, day: dt.date, stat: tuple[int, str, int]) -> None:
        self.rows.append({"kind": kind, "root": root, "date": day, "rows": stat[0], "sha256": stat[1], "bytes": stat[2],
                          "window": window_of(day), "source": "synthetic"})

    def nbbo(self, root: str, day: dt.date, *, expiration: Sequence[dt.date], strike: Any, right: Sequence[str], minute: Any,
             bid: Any, ask: Any, bid_size: Any, ask_size: Any) -> None:
        exp = pa.array(list(expiration), pa.date32())
        order = np.lexsort((np.asarray(minute), np.asarray([0 if r == "C" else 1 for r in right]), np.asarray(strike, dtype=np.float64),
                            np.asarray([d.toordinal() for d in expiration])))
        table = pa.table({
            "expiration": exp.take(pa.array(order)), "strike": pa.array(np.asarray(strike, dtype=np.float64)[order]),
            "right": pa.array(np.asarray(right)[order].tolist(), pa.string()),
            "minute": pa.array(np.asarray(minute)[order].astype(np.int16)),
            "bid": pa.array(np.asarray(bid, dtype=np.float32)[order]), "ask": pa.array(np.asarray(ask, dtype=np.float32)[order]),
            "bid_size": pa.array(np.asarray(bid_size, dtype=np.int32)[order]),
            "ask_size": pa.array(np.asarray(ask_size, dtype=np.int32)[order])})
        self._record("nbbo", root, day, _write(table, self.root / "nbbo" / root / f"{day.isoformat()}.parquet"))

    def underlying(self, root: str, day: dt.date, minute: Any, price: Any) -> None:
        table = pa.table({"minute": pa.array(np.asarray(minute).astype(np.int16)), "price": pa.array(np.asarray(price, dtype=np.float64))})
        self._record("underlying", root, day, _write(table, self.root / "underlying" / root / f"{day.isoformat()}.parquet"))

    def oi(self, root: str, day: dt.date, *, expiration: Sequence[dt.date], strike: Any, right: Sequence[str], open_interest: Any) -> None:
        table = pa.table({"expiration": pa.array(list(expiration), pa.date32()), "strike": pa.array(np.asarray(strike, dtype=np.float64)),
                          "right": pa.array(list(right), pa.string()),
                          "open_interest": pa.array(np.asarray(open_interest, dtype=np.int64))})
        self._record("oi", root, day, _write(table, self.root / "oi" / root / f"{day.isoformat()}.parquet"))

    def trade_quote(self, root: str, day: dt.date, columns: Mapping[str, Any]) -> None:
        types = {"expiration": pa.date32(), "strike": pa.float64(), "right": pa.string(), "ms_of_day": pa.int32(),
                 "price": pa.float64(), "size": pa.int32(), "condition": pa.int16(), "exchange": pa.int16(), "bid": pa.float32(),
                 "ask": pa.float32(), "bid_size": pa.int32(), "ask_size": pa.int32()}
        table = pa.table({k: pa.array(list(columns[k]) if k in ("expiration", "right") else np.asarray(columns[k]), types[k])
                          for k in types})
        self._record("trade_quote", root, day, _write(table, self.root / "trade_quote" / root / f"{day.isoformat()}.parquet"))

    def gate_mark(self) -> None:
        (self.root / GATE_MARK).write_text("gate\n")

    def finish(self) -> None:
        rows = self.rows
        table = pa.table({"kind": pa.array([r["kind"] for r in rows], pa.string()),
                          "root": pa.array([r["root"] for r in rows], pa.string()),
                          "date": pa.array([r["date"] for r in rows], pa.date32()),
                          "rows": pa.array([r["rows"] for r in rows], pa.int64()),
                          "sha256": pa.array([r["sha256"] for r in rows], pa.string()),
                          "bytes": pa.array([r["bytes"] for r in rows], pa.int64()),
                          "window": pa.array([r["window"] for r in rows], pa.string()),
                          "fetched_at": pa.array([dt.datetime(2026, 9, 26, tzinfo=dt.timezone.utc)] * len(rows), pa.timestamp("us", tz="UTC")),
                          "source": pa.array([r["source"] for r in rows], pa.string())})
        _write(table, self.root / "manifest.parquet")


def weekdays(start: dt.date, count: int, skip: Iterable[dt.date] = ()) -> list[dt.date]:
    """`count` weekdays from `start` (skipping `skip`)."""
    out, day, skip = [], start, set(skip)
    while len(out) < count:
        if day.weekday() < 5 and day not in skip:
            out.append(day)
        day += dt.timedelta(days=1)
    return out


def flat_day(writer: Writer, root: str, day: dt.date, contracts: Sequence[Mapping[str, Any]], *, prices: Any,
             open_min: int = 570, close_min: int = 960, size: int = 100) -> None:
    """A hand-set day: each contract {"expiration", "strike", "right", "quotes"[, "size"]} where quotes
    maps a minute to (bid, ask[, size]) and holds until the next listed minute (a minute before the
    first listed one has no row; a (None, None) entry ends the rows); `prices` is one price for the
    whole day, or a {minute: price} step function."""
    minutes = np.arange(open_min, close_min + 1)
    exp, strike, right, minute, bid, ask, sizes = [], [], [], [], [], [], []
    for c in contracts:
        steps = sorted((int(m), q) for m, q in c["quotes"].items())
        for m in minutes:
            current = None
            for start, q in steps:
                if start <= m:
                    current = q
            if current is None or current[0] is None:
                continue
            exp.append(c["expiration"])
            strike.append(float(c["strike"]))
            right.append(c["right"])
            minute.append(int(m))
            bid.append(float(current[0]))
            ask.append(float(current[1]))
            sizes.append(int(current[2]) if len(current) > 2 else int(c.get("size", size)))
    writer.nbbo(root, day, expiration=exp, strike=strike, right=right, minute=minute, bid=bid, ask=ask, bid_size=sizes, ask_size=sizes)
    if isinstance(prices, Mapping):
        steps = sorted((int(m), float(p)) for m, p in prices.items())
        series = [next((p for s, p in reversed(steps) if s <= m), steps[0][1]) for m in minutes]
    else:
        series = [float(prices)] * len(minutes)
    writer.underlying(root, day, minutes, series)


def generate(root_dir: str | Path, *, roots: Sequence[str] = ("SPY",), days: Sequence[dt.date], seed: int = 7,
             strikes_each_side: int = 25, max_dte: int = 14, vol: float = 0.16, spread_frac: float = 0.03,
             trade_quote: bool = False, gate: bool = False) -> Writer:
    """A plausible synthetic market over `days` (see the module docstring)."""
    rng = np.random.default_rng(seed)
    writer = Writer(root_dir)
    writer.calendar(days)
    minutes = np.arange(570, 961)
    expiry_rows = []
    for root in roots:
        spot = {"SPY": 450.0, "QQQ": 380.0, "IWM": 190.0, "XSP": 450.0, "SPXW": 4500.0}.get(root, 100.0)
        step = 5.0 if root == "SPXW" else 1.0
        for day in days:
            path = spot * np.exp(np.cumsum(rng.normal(0.0, vol / math.sqrt(252 * 390), minutes.size)))
            path[0] = spot
            expiries = [d for d in (day + dt.timedelta(days=k) for k in range(max_dte + 1)) if d.weekday() < 5]
            atm = round(spot / step) * step
            ks = atm + step * np.arange(-strikes_each_side, strikes_each_side + 1)
            exp_l, k_l, r_l = [], [], []
            for e in expiries:
                expiry_rows.append((root, day, e))
                for k in ks:
                    for r in ("C", "P"):
                        exp_l.append(e)
                        k_l.append(k)
                        r_l.append(r)
            c = len(k_l)
            k_a = np.array(k_l)
            call = np.array([r == "C" for r in r_l])
            dte = np.array([(e - day).days for e in exp_l])
            years = G.years_to_expiry(dte[:, None], minutes[None, :])
            moneyness = np.log(k_a / spot)[:, None]
            sigma = vol * (1.0 - 1.5 * moneyness + 8.0 * moneyness ** 2)
            mid = G.bs_price(path[None, :], k_a[:, None], years, 0.04, sigma, call[:, None])
            tick = 0.01
            half = np.maximum(tick, np.round(mid * spread_frac / 2 / tick) * tick)
            bid = np.maximum(0.0, np.round((mid - half) / tick) * tick)
            ask = np.maximum(bid + tick, np.round((mid + half) / tick) * tick)
            bsz = rng.integers(5, 400, size=(c, minutes.size))
            asz = rng.integers(5, 400, size=(c, minutes.size))
            bid[:, 0] = np.nan  # the 09:30 row: no quote yet
            keep = np.isfinite(bid)
            ci, mi = np.nonzero(keep)
            writer.nbbo(root, day, expiration=[exp_l[i] for i in ci], strike=k_a[ci], right=[r_l[i] for i in ci], minute=minutes[mi],
                        bid=bid[keep], ask=ask[keep], bid_size=bsz[keep], ask_size=asz[keep])
            writer.underlying(root, day, minutes, path)
            writer.oi(root, day, expiration=exp_l, strike=k_a, right=r_l, open_interest=rng.integers(0, 50_000, size=c))
            if trade_quote:
                n = 400
                pick = rng.integers(0, c, n)
                at = rng.integers(1, minutes.size - 1, n)
                b, a = bid[pick, at], ask[pick, at]
                where = rng.choice([0.0, 0.25, 0.5, 0.75, 1.0], n, p=[0.3, 0.1, 0.25, 0.1, 0.25])
                writer.trade_quote(root, day, {
                    "expiration": [exp_l[i] for i in pick], "strike": k_a[pick], "right": [r_l[i] for i in pick],
                    "ms_of_day": (minutes[at] * 60_000 + rng.integers(0, 60_000, n)).astype(np.int32),
                    "price": np.round(b + where * (a - b), 2), "size": rng.integers(1, 20, n),
                    "condition": rng.choice([18, 130], n, p=[0.8, 0.2]), "exchange": rng.integers(1, 20, n),
                    "bid": b, "ask": a, "bid_size": bsz[pick, at], "ask_size": asz[pick, at]})
            spot = float(path[-1])
    writer.expiries(expiry_rows)
    if gate:
        writer.gate_mark()
    writer.finish()
    return writer


__all__ = ["Writer", "generate", "flat_day", "weekdays"]
