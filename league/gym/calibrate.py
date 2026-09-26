"""Fitting the fill model from Train's `trade_quote` samples (never another window).

    python -m league.gym.calibrate --store /data/store --roots SPY,QQQ,IWM,XSP,SPXW \
        [--out /data/calibration/fill_model.json]      # the laptop default: .data/gym/fill_model.json
        [--prior 600] [--sample-strikes 10]

WHAT IT ESTIMATES. For a limit resting at level l (its distance from the mid toward its own natural, in
half-spreads: 0 at the mid, 1 at the natural), the per-minute hazard that some trade on that contract
prints at or through it (a buy at l fills when a print lands at or below mid + l x half-spread; a sell
mirrors it). The engine draws against it once a minute while the limit works (`fills.py`), after the
next-minute adverse-selection rule (`engine.py`) and before the stress charge. Cells are (level
bucket, single or multi-leg, days to expiry, moneyness, time of day), the same as `fills.cell`; each
level bucket is measured at its LEAST aggressive level (a quarter-spread bucket counts prints at or
past its lower edge), so a fill is never credited to a price it did not reach.

The touch (bucket 0: a buy resting at the bid, a sell at the ask, up to a quarter-spread short of the
mid) is measured at the touch itself, where an order joins a queue: a contract-minute counts only when
the prints at or through the touch in that minute add up to MORE contracts than the NBBO showed there
at the minute's start (the queue ahead of an order arriving then). Prints the queue absorbed fill
nothing.

THE ESTIMATOR: a point estimate, not a bound.
- Exposure: every contract-minute (09:31 to the minute before the close) at 0-7 days to expiry on
  which the contract was QUOTED two-sided with size (the same population as the hits), within the
  trade sample's strike band: per expiry, `sample_strikes` listed strikes each side of the money at
  the day's first underlying price (ThetaData's `strike_range` of the sample), widened to every strike
  that printed. Contracts outside that band were never sampled, so their minutes are not counted as
  misses; contracts inside it with no print count, as they should (zero-print contracts are real zeros).
  Each contract-minute is two exposures: a resting buy and a resting sell.
- Hits: contract-minutes with a print at or past the level, buys and sells separately.
- Single-leg cells take the single-leg prints; MULTI-LEG cells take the complex prints directly
  (conditions 130-134, 136, 137, 144 and the legacy 35 SPREAD, 36 STRADDLE, 38 COMBO; stock-option
  packages 135 and 138-143 are excluded from both), no haircut and no cap by the single-leg rate.
- The rate is the MLE hits / exposure, shrunk toward the next coarser cell where data is thin:
  (dte, moneyness, time) -> (dte, moneyness) -> (dte) -> the level's pooled rate, each level
  estimated as (hits + prior x parent rate) / (exposure + prior), `prior` pseudo side-minutes. A cell
  with no exposure takes its parent's rate: nothing falls to zero merely for lack of data. Weights do
  not depend on the level, so the table stays monotone in it (a nearer-the-natural limit never fills
  less often). A days-to-expiry bucket the sample never saw (8+ days: the sample stops at 7) takes
  the nearest sampled bucket's cells (3-7 days); back months print less often per minute than that,
  so their passive fills are the one place the table may flatter (named in `meta.borrowed_dte`).
- A level with no exposure at all is left out (the engine reads zero: natural fills only).

Paper fills prove the route only and never calibrate the model; real fills will. The table goes to a
gitignored path: fitted parameters of licensed data never enter git or anything published.

WHERE IT GOES. `scripts/data/calibration.py` runs this on the sealed Gym image with the current code,
writes the same file to `/data/calibration/fill_model.json` on both the Gym and the gate image, and
checkpoints them. Every loader (`fills.FillModel.load`) takes, in order: an explicit path (`batch.py
--fill-model`, `RunConfig.fill_model`), `GYM_FILL_MODEL`, `/data/calibration/fill_model.json`, then
`.data/gym/fill_model.json` under the code's root; none found is natural-only.

numpy and pyarrow.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
from typing import Sequence

import numpy as np

from . import fills as F
from .store import Store, StoreRefused, contract_key, window_of

MULTI_LEG = frozenset({35, 36, 38, 130, 131, 132, 133, 134, 136, 137, 144})
STOCK_OPTION = frozenset({135, 138, 139, 140, 141, 142, 143})
LEVELS = {1: -0.25, 2: 0.0, 3: 0.25, 4: 0.5, 5: 0.75}   # q bucket -> its least aggressive level
TOUCH_BUCKET = 0                                         # measured at F.TOUCH, behind the displayed queue
Q_BUCKETS = (TOUCH_BUCKET, *LEVELS)
#: Pseudo side-minutes a cell borrows from its coarser parent (the shrinkage's strength).
PRIOR = 600.0
#: The trade sample's strikes each side of the money (scripts/data/storelib.py TQ_STRIKE_RANGE), and its reach.
SAMPLE_STRIKES = 10
SAMPLE_MAX_DTE = 7
D_BUCKETS = tuple(range(len(F.DTE_EDGES)))
K_BUCKETS = tuple(range(len(F.MONEY_EDGES) + 1))
T_BUCKETS = tuple(range(len(F.TOD_EDGES) + 1))
LAPTOP_OUT = Path(__file__).resolve().parents[2] / ".data" / "gym" / "fill_model.json"


def _cells(dte: np.ndarray, money: np.ndarray, minute: np.ndarray) -> np.ndarray:
    """An int code per (dte bucket, moneyness bucket, time bucket)."""
    d = np.searchsorted(np.array(F.DTE_EDGES[1:]), dte, side="right")
    k = np.searchsorted(np.array(F.MONEY_EDGES), np.abs(money), side="right")
    t = np.searchsorted(np.array(F.TOD_EDGES), minute, side="right")
    return (d * 10 + k) * 10 + t


def _decode(code: int) -> tuple[int, int, int]:
    return code // 100, (code // 10) % 10, code % 10


def sampled_band(chain, eligible: np.ndarray, printed: np.ndarray, strikes_each_side: int) -> np.ndarray:
    """Which contracts the day's trade sample covered: per expiry, `strikes_each_side` listed strikes
    each side of the money at the first underlying price, widened to every strike that printed."""
    band = np.zeros(chain.contracts, dtype=bool)
    spot = chain.underlying.price
    known = spot[np.isfinite(spot)]
    ref = float(known[0]) if known.size else float("nan")
    for expiry in np.unique(chain.expiration[eligible]):
        members = np.flatnonzero(eligible & (chain.expiration == expiry))
        strikes = np.unique(chain.strike[members])
        lo, hi = np.inf, -np.inf
        if np.isfinite(ref) and strikes.size:
            at = int(np.argmin(np.abs(strikes - ref)))
            lo = float(strikes[max(0, at - strikes_each_side)])
            hi = float(strikes[min(strikes.size - 1, at + strikes_each_side)])
        hit = printed[chain.expiration[printed] == expiry]
        if hit.size:
            lo, hi = min(lo, float(chain.strike[hit].min())), max(hi, float(chain.strike[hit].max()))
        band[members] = (chain.strike[members] >= lo) & (chain.strike[members] <= hi)
    return band


def shrink(exposure: dict[int, float], hits: dict[int, float], prior: float) -> tuple[dict[tuple[int, int, int], float], list[int]]:
    """{(d, k, t): rate} for every cell, from exposures (side-minutes) and hits per cell code: the MLE
    shrunk toward (d, k), then (d), then the pooled rate (the module docstring). Also the DTE buckets
    that borrowed a sampled neighbour's cells. Empty when there is no exposure at all."""
    total_n = sum(exposure.values())
    if total_n <= 0:
        return {}, []
    pooled = sum(hits.values()) / total_n
    n1: dict[int, float] = {}
    k1: dict[int, float] = {}
    n2: dict[tuple[int, int], float] = {}
    k2: dict[tuple[int, int], float] = {}
    for code, n in exposure.items():
        d, k, _ = _decode(code)
        h = hits.get(code, 0.0)
        n1[d] = n1.get(d, 0.0) + n
        k1[d] = k1.get(d, 0.0) + h
        n2[d, k] = n2.get((d, k), 0.0) + n
        k2[d, k] = k2.get((d, k), 0.0) + h
    out: dict[tuple[int, int, int], float] = {}
    seen = sorted(d for d in D_BUCKETS if n1.get(d, 0.0) > 0)
    for d in seen:
        r1 = (k1[d] + prior * pooled) / (n1[d] + prior)
        for k in K_BUCKETS:
            r2 = (k2.get((d, k), 0.0) + prior * r1) / (n2.get((d, k), 0.0) + prior)
            for t in T_BUCKETS:
                code = (d * 10 + k) * 10 + t
                out[d, k, t] = (hits.get(code, 0.0) + prior * r2) / (exposure.get(code, 0.0) + prior)
    borrowed = [d for d in D_BUCKETS if d not in seen]
    for d in borrowed:  # never sampled: the nearest sampled horizon's cells (the shorter one on a tie)
        near = min(seen, key=lambda s: (abs(s - d), s))
        for k in K_BUCKETS:
            for t in T_BUCKETS:
                out[d, k, t] = out[near, k, t]
    return out, borrowed


def fit(store: Store, roots: Sequence[str], *, days: Sequence[dt.date] | None = None, prior: float = PRIOR,
        sample_strikes: int = SAMPLE_STRIKES) -> dict:
    """The fitted table and what it was fitted on (see the module docstring)."""
    exposure: dict[int, float] = {}
    hits = {cls: {q: {} for q in Q_BUCKETS} for cls in ("s", "m")}
    seen = {"days": 0, "prints": 0, "single": 0, "multi": 0, "stock_option": 0, "dropped": 0, "contract_minutes": 0}
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
            eligible = (chain.dte >= 0) & (chain.dte <= SAMPLE_MAX_DTE)
            band = sampled_band(chain, eligible, np.unique(idx[idx >= 0]), int(sample_strikes))
            quoted = (np.isfinite(chain.bid) & np.isfinite(chain.ask) & (chain.ask > chain.bid)
                      & (chain.bid >= 0) & (chain.bid_size > 0) & (chain.ask_size > 0)
                      & np.isfinite(spot[:, None]) & (spot[:, None] > 0) & (eligible & band)[None, :])
            # Prices are whole cents (sub-penny at most): the float32 columns' noise is rounded away.
            price = np.round(tq.column("price").to_numpy().astype(np.float64), 4)
            bid = np.round(tq.column("bid").to_numpy().astype(np.float64), 4)
            ask = np.round(tq.column("ask").to_numpy().astype(np.float64), 4)
            cond = tq.column("condition").to_numpy().astype(np.int64)
            size = tq.column("size").to_numpy().astype(np.int64)
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
            idx, minute, price, bid, ask, cond, size = idx[ok], minute[ok], price[ok], bid[ok], ask[ok], cond[ok], size[ok]
            half = 0.5 * (ask - bid)
            pos = np.round((price - 0.5 * (ask + bid)) / half, 6)   # -1 at the bid, +1 at the ask
            multi = np.isin(cond, list(MULTI_LEG))
            seen["prints"] += int(idx.size)
            seen["multi"] += int(multi.sum())
            seen["single"] += int((~multi).sum())
            # Never condition exposure on a trade having occurred: zero-print contracts in the band count too.
            mm, contract = np.nonzero(quoted[1:-1])
            mm = mm + 1
            seen["contract_minutes"] += int(mm.size)
            money = chain.strike[contract] / spot[mm] - 1.0
            cell = _cells(chain.dte[contract], money, chain.open_min + mm)
            for code, n in zip(*np.unique(cell, return_counts=True)):
                exposure[int(code)] = exposure.get(int(code), 0.0) + 2.0 * float(n)   # a resting buy and a resting sell
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
                # The touch: a buy at the bid (a sell at the ask) behind the queue the NBBO showed at the minute.
                for side, queue in ((pos <= F.TOUCH, chain.bid_size), (pos >= -F.TOUCH, chain.ask_size)):
                    sel = mask & side
                    if not sel.any():
                        continue
                    uniq, inverse = np.unique(key[sel], return_inverse=True)
                    volume = np.bincount(inverse, weights=size[sel].astype(np.float64), minlength=uniq.size)
                    ahead = np.zeros(uniq.size, dtype=np.float64)
                    ahead[inverse] = queue[minute[sel], idx[sel]]
                    cells = np.zeros(uniq.size, dtype=np.int64)
                    cells[inverse] = pcell[sel]
                    for code, n in zip(*np.unique(cells[volume > ahead], return_counts=True)):
                        hits[cls][TOUCH_BUCKET][int(code)] = hits[cls][TOUCH_BUCKET].get(int(code), 0.0) + float(n)
    hazard: dict[str, float] = {}
    borrowed: list[int] = []
    for cls in ("s", "m"):
        for q in Q_BUCKETS:
            rates, borrowed = shrink(exposure, hits[cls][q], float(prior))
            for (d, k, t), p in rates.items():
                rounded = round(min(1.0, max(0.0, p)), 6)
                if rounded > 0:
                    hazard[f"q{q}|{cls}|d{d}|k{k}|t{t}"] = rounded
    return {"source": "league.gym.calibrate", "hazard": dict(sorted(hazard.items())),
            "meta": {"fitted_on": seen, "roots": list(roots), "cells_with_exposure": len(exposure),
                     "prior": float(prior), "sample_strikes": int(sample_strikes), "borrowed_dte": borrowed,
                     "conditions": dict(sorted(codes.items())),
                     "fitted_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                     "rule": "per-minute MLE over quoted contract-minutes in the sample's strike band, shrunk toward coarser "
                             "cells (time -> moneyness -> dte -> pooled) with `prior` pseudo side-minutes; each level at its "
                             "least aggressive edge; the touch (q0) only where the minute's volume there exceeded the "
                             "displayed queue; multi-leg from complex prints directly"}}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m league.gym.calibrate")
    parser.add_argument("--store", default="/data/store")
    parser.add_argument("--roots", default="SPY,QQQ,IWM,XSP,SPXW")
    parser.add_argument("--out", default=None)
    parser.add_argument("--prior", type=float, default=PRIOR, help="pseudo side-minutes a cell borrows from its coarser parent")
    parser.add_argument("--sample-strikes", type=int, default=SAMPLE_STRIKES, help="the trade sample's strikes each side of the money")
    args = parser.parse_args(argv)
    store = Store(args.store)
    roots = [r.strip().upper() for r in args.roots.split(",") if r.strip()]
    roots = [r for r in roots if any(store.has("trade_quote", r, d) for d in store.trading_days() if window_of(d) == "train")]
    if not roots:
        print(f"no Train trade_quote samples in {args.store}")
        return 3
    table = fit(store, roots, prior=args.prior, sample_strikes=args.sample_strikes)
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
