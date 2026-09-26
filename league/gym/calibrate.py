"""Fitting the fill model from Train's `trade_quote` samples (never another window).

    python -m league.gym.calibrate --store /data/store --roots SPY,QQQ,IWM,XSP,SPXW \
        [--out /data/calibration/fill_model.json]      # the laptop default: .data/gym/fill_model.json

What it estimates: for a limit resting at level l (its distance from the mid toward its own natural,
in half-spreads: 0 at the mid, 1 at the natural), the chance that within one minute some trade on
that contract prints at or through it (a buy at l fills when a print lands at or below mid + l x
half-spread; a sell mirrors it). The exposure is every quoted contract-minute at 0-7 DTE in the
same day's NBBO file, including contracts with no prints. The NBBO strike band is deliberately
wider than the trade sample's band: this adds zero-hit exposure and makes the estimate conservative.
The prints are the day's `trade_quote` rows, each placed by
its own NBBO. Cells are (level bucket, single or multi-leg, days to expiry, moneyness, time of day),
the same as `fills.cell`; each bucket is measured at its LEAST aggressive level (a quarter-spread
bucket counts prints at or past its lower edge), so a fill is never credited to a price it did not reach.

Multi-leg: prints whose condition is a multi-leg execution (ThetaData's codes 130-134, 136, 137, 144,
and the legacy 35 SPREAD, 36 STRADDLE, 38 COMBO; stock-option packages 135 and 138-143 are excluded)
say how often complex orders trade on a contract, and where against its NBBO. A structure's package
needs a counterparty for all of it, which leg prints cannot show, so the multi-leg hazard is the
contract's complex-print rate HALVED and never above the single-leg rate: a deliberately low start
that real fills replace. Paper fills prove the route only and never calibrate the model.

Every cell's hazard is the Wilson 95% LOWER bound of its rate, and a cell with fewer than
`min_exposure` contract-minutes is left out (zero: natural fills only). The table goes to a
gitignored path: fitted parameters of licensed data never enter git or anything published.

numpy and pyarrow.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
from pathlib import Path
from typing import Sequence

import numpy as np

from . import fills as F
from .store import Store, StoreRefused, contract_key, window_of

MULTI_LEG = frozenset({35, 36, 38, 130, 131, 132, 133, 134, 136, 137, 144})
STOCK_OPTION = frozenset({135, 138, 139, 140, 141, 142, 143})
LEVELS = {1: -0.25, 2: 0.0, 3: 0.25, 4: 0.5, 5: 0.75}   # q bucket -> its least aggressive level
MULTI_HAIRCUT = 0.5
LAPTOP_OUT = Path(__file__).resolve().parents[2] / ".data" / "gym" / "fill_model.json"


def wilson_lower(k: float, n: float, z: float = 1.96) -> float:
    if n <= 0:
        return 0.0
    p = k / n
    denom = 1.0 + z * z / n
    centre = p + z * z / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0.0, (centre - margin) / denom)


def _cells(dte: np.ndarray, money: np.ndarray, minute: np.ndarray) -> np.ndarray:
    """An int code per (dte bucket, moneyness bucket, time bucket)."""
    d = np.searchsorted(np.array(F.DTE_EDGES[1:]), dte, side="right")
    k = np.searchsorted(np.array(F.MONEY_EDGES), np.abs(money), side="right")
    t = np.searchsorted(np.array(F.TOD_EDGES), minute, side="right")
    return (d * 10 + k) * 10 + t


def _decode(code: int) -> tuple[int, int, int]:
    return code // 100, (code // 10) % 10, code % 10


def fit(store: Store, roots: Sequence[str], *, days: Sequence[dt.date] | None = None, min_exposure: int = 300) -> dict:
    """The fitted table and what it was fitted on (see the module docstring)."""
    exposure: dict[int, float] = {}
    hits = {cls: {q: {} for q in LEVELS} for cls in ("s", "m")}
    seen = {"days": 0, "prints": 0, "single": 0, "multi": 0, "stock_option": 0, "dropped": 0}
    codes: dict[int, int] = {}
    for root in roots:
        candidates = days if days is not None else [d for d in store.trading_days() if window_of(d) == "train"
                                                     and store.has("trade_quote", root, d) and store.has("nbbo", root, d)]
        for day in candidates:
            if window_of(day) != "train":
                raise StoreRefused("calibration reads Train days only")
            tq = store.trade_quote(root, day)
            chain = store.chain(root, day)
            seen["days"] += 1
            exp = tq.column("expiration").cast("int32").to_numpy().astype(np.int64) if str(tq.column("expiration").type) == "date32[day]" \
                else np.asarray([(d - dt.date(1970, 1, 1)).days for d in tq.column("expiration").to_pylist()])
            calls = np.array([str(r).upper().startswith("C") for r in tq.column("right").to_pylist()])
            idx = chain.index_of(contract_key(exp, tq.column("strike").to_numpy(), calls))
            minute = (tq.column("ms_of_day").to_numpy() // 60000).astype(np.int64) - chain.open_min
            spot = chain.underlying.price
            eligible = (chain.dte >= 0) & (chain.dte <= 7)
            quoted = (np.isfinite(chain.bid) & np.isfinite(chain.ask) & (chain.ask > chain.bid)
                      & (chain.bid >= 0) & (chain.bid_size > 0) & (chain.ask_size > 0)
                      & np.isfinite(spot[:, None]) & (spot[:, None] > 0) & eligible[None, :])
            # Prices are whole cents (sub-penny at most): the float32 columns' noise is rounded away.
            price = np.round(tq.column("price").to_numpy().astype(np.float64), 4)
            bid = np.round(tq.column("bid").to_numpy().astype(np.float64), 4)
            ask = np.round(tq.column("ask").to_numpy().astype(np.float64), 4)
            cond = tq.column("condition").to_numpy().astype(np.int64)
            for c, n in zip(*np.unique(cond, return_counts=True)):
                codes[int(c)] = codes.get(int(c), 0) + int(n)
            ok = ((idx >= 0) & (minute >= 1) & (minute < chain.minutes - 1) & (ask > bid) & (bid >= 0)
                  & (price > 0) & np.isfinite(price) & np.isfinite(bid) & np.isfinite(ask))
            # A hit must belong to the same contract-minute population as its denominator.
            hit = np.flatnonzero(ok)
            ok[hit] &= quoted[minute[hit], idx[hit]]
            ok &= ~np.isin(cond, list(STOCK_OPTION))
            seen["stock_option"] += int(np.isin(cond, list(STOCK_OPTION)).sum())
            seen["dropped"] += int((~ok).sum())
            idx, minute, price, bid, ask, cond = idx[ok], minute[ok], price[ok], bid[ok], ask[ok], cond[ok]
            half = 0.5 * (ask - bid)
            pos = np.round((price - 0.5 * (ask + bid)) / half, 6)   # -1 at the bid, +1 at the ask
            multi = np.isin(cond, list(MULTI_LEG))
            seen["prints"] += int(idx.size)
            seen["multi"] += int(multi.sum())
            seen["single"] += int((~multi).sum())
            # Never condition exposure on a trade having occurred: zero-print contracts count too.
            mm, contract = np.nonzero(quoted[1:-1])
            mm = mm + 1
            money = chain.strike[contract] / spot[mm] - 1.0
            cell = _cells(chain.dte[contract], money, chain.open_min + mm)
            for code, n in zip(*np.unique(cell, return_counts=True)):
                exposure[int(code)] = exposure.get(int(code), 0.0) + float(n)
            # Hits: contract-minutes with a print at or past each level, buys and sells separately.
            pmoney = chain.strike[idx] / spot[minute] - 1.0
            pcell = _cells(chain.dte[idx], pmoney, chain.open_min + minute)
            key = idx * 10_000 + minute
            for cls, mask in (("s", ~multi), ("m", multi)):
                for q, level in LEVELS.items():
                    for side in (pos <= level, pos >= -level):     # a resting buy; a resting sell
                        sel = mask & side
                        uniq, first = np.unique(key[sel], return_index=True)
                        cells = pcell[sel][first]
                        for code, n in zip(*np.unique(cells, return_counts=True)):
                            hits[cls][q][int(code)] = hits[cls][q].get(int(code), 0.0) + float(n)
    hazard: dict[str, float] = {}
    for code, n in exposure.items():
        if n < min_exposure:
            continue
        d, k, t = _decode(code)
        for q in LEVELS:
            single = wilson_lower(hits["s"][q].get(code, 0.0), 2.0 * n)   # buys and sells: two exposures
            multi = min(single, MULTI_HAIRCUT * wilson_lower(hits["m"][q].get(code, 0.0), 2.0 * n))
            for cls, p in (("s", single), ("m", multi)):
                rounded = round(p, 6)
                if rounded > 0:
                    hazard[f"q{q}|{cls}|d{d}|k{k}|t{t}"] = rounded
    return {"source": "league.gym.calibrate", "hazard": dict(sorted(hazard.items())),
            "meta": {"fitted_on": seen, "roots": list(roots), "cells_with_exposure": len(exposure),
                     "min_exposure": min_exposure, "conditions": dict(sorted(codes.items())),
                     "fitted_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                     "rule": "Wilson 95% lower bound; each level bucket at its least aggressive edge; multi-leg halved and capped by single"}}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m league.gym.calibrate")
    parser.add_argument("--store", default="/data/store")
    parser.add_argument("--roots", default="SPY,QQQ,IWM,XSP,SPXW")
    parser.add_argument("--out", default=None)
    parser.add_argument("--min-exposure", type=int, default=300)
    args = parser.parse_args(argv)
    store = Store(args.store)
    roots = [r.strip().upper() for r in args.roots.split(",") if r.strip()]
    roots = [r for r in roots if any(store.has("trade_quote", r, d) for d in store.trading_days() if window_of(d) == "train")]
    if not roots:
        print(f"no Train trade_quote samples in {args.store}")
        return 3
    table = fit(store, roots, min_exposure=args.min_exposure)
    out = Path(args.out) if args.out else (Path("/data/calibration/fill_model.json") if Path("/data").is_dir() and Path("/data/store").is_dir()
                                           else LAPTOP_OUT)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(table, indent=1, sort_keys=True))
    tmp.chmod(0o600)
    tmp.replace(out)
    print(json.dumps({"out": str(out), "cells": len(table["hazard"]), **table["meta"]["fitted_on"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
