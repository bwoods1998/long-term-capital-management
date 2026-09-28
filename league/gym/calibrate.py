"""Fitting the fill model from Train's `trade_quote` samples (never another window).

    python -m league.gym.calibrate --store /data/store --roots SPY,QQQ,IWM,XSP,SPXW \
        [--out /data/calibration/fill_model.json]      # the laptop default: .data/gym/fill_model.json
        [--prior 600] [--sample-strikes 10] [--min-bucket 6000]
        [--adverse unconditional|conditional]          # conditional: see ADVERSE SELECTION below

WHAT IT ESTIMATES. For a limit resting at level l (its distance from the mid toward its own natural, in
half-spreads: 0 at the mid, 1 at the natural), the per-minute hazard that some trade on that contract
prints at or through it (a buy at l fills when a print lands at or below mid + l x half-spread; a sell
mirrors it). The engine draws against it once a minute while the limit works (`fills.py`), under the
next-minute adverse-selection rule (`engine.py`) and before the stress charge. Cells are (level
bucket, single or multi-leg, days to expiry, moneyness, time of day), the same as `fills.cell`; each
level bucket is measured at its LEAST aggressive level (a quarter-spread bucket counts prints at or
past its lower edge), so a fill is never credited to a price it did not reach.

ADVERSE SELECTION. `hazard` is measured over every quoted minute. With `--adverse conditional` the table
also carries each cell measured twice with the same exposure and hit definitions, split by where the
contract's mid goes over the NEXT minute from the resting order's side: `hazard_adverse` on
adverse-or-flat minutes (a resting buy's mid falls or holds, a resting sell's rises or holds: a flat
minute is adverse for both sides) and `hazard_favourable` on the rest, with the marker
`"adverse": "conditional"`. The test is the engine's (`engine.Account._next_move`, the same 1e-9
tolerance on the same mid 0.5 x (bid + ask)); a contract-minute whose next minute has no two-sided quote
is in neither (the engine fills nothing passively there). Each condition is shrunk toward its own
coarser cells with the same prior, on exactly the unconditional table's buckets (the `min_bucket`
rule reads the unconditional exposure; as everywhere, a rate that rounds to zero at six decimals is
left out, so a table may lack a cell another holds at 1e-6), so exposure-weighted the two rates are the
unconditional one up to the shrinkage. Sizes are not split. An unconditional fit's output is unchanged.

The touch (bucket 0: a buy resting at the bid, a sell at the ask, up to a quarter-spread short of the
mid) is measured at the touch itself, where an order joins a queue: a contract-minute counts only when
the prints at or through the touch in that minute add up to MORE contracts than the NBBO showed there
at the minute's start (the queue ahead of an order arriving then). Prints the queue absorbed fill
nothing.

THE ESTIMATOR: a point estimate, not a bound, per root.
- Exposure: every contract-minute (09:31 to the minute before the close) at 0-7 days to expiry on
  which the contract was QUOTED two-sided with size (the same population as the hits), within the
  trade sample's strike band: per expiry, `sample_strikes` listed strikes each side of the money at
  the day's first underlying price (ThetaData's `strike_range` of the sample), widened to every strike
  that printed. Contracts outside that band were never sampled, so their minutes are not counted as
  misses; contracts inside it with no print count, as they should (zero-print contracts are real zeros).
  Each contract-minute is two exposures: a resting buy and a resting sell.
- Hits: contract-minutes with a print at or past the level, buys and sells separately.
- Single-leg cells take the single-leg prints; MULTI-LEG cells take the complex prints (conditions
  130-134, 136, 137, 144 and the legacy 35 SPREAD, 36 STRADDLE, 38 COMBO; stock-option packages 135
  and 138-143 are excluded from both), measured leg by leg: the rate at which a complex order traded
  on that contract at that level. The engine prices a package at the LOWEST of its legs' rates, each
  at the leg's own days to expiry and moneyness and capped by the leg's single-leg rate (`fills.py`):
  a package needs a counterparty for every leg, which leg-by-leg prints cannot show, so this is an
  upper bound on a package's rate that real fills will correct.
- The rate is the MLE hits / exposure, shrunk toward the next coarser cell where data is thin:
  (root, dte, moneyness, time) -> (root, dte, moneyness) -> (root, dte) -> (root) -> every root
  pooled, each level estimated as (hits + prior x parent rate) / (exposure + prior), `prior` pseudo
  side-minutes. A time cell with no exposure takes its (root, dte, moneyness) parent's rate. Weights
  do not depend on the level, so the table stays monotone in it (a nearer-the-natural limit never
  fills less often).
- A root, a root's days-to-expiry bucket, or a (root, dte, moneyness) bucket with fewer than
  `min_bucket` side-minutes of exposure has NO cells: the engine reads zero there (natural fills
  only). So 8 or more days to expiry (the sample stops at 7) is never modelled, a wing or
  far-out-of-the-money contract the sample's band barely reaches (10 strikes each side: about 1% on
  SPXW, 2% on SPY and XSP) never borrows the near-the-money rate that dominates its (root, dte)
  parent, and no root borrows another's liquidity except through the shrinkage of cells it did sample.
- Size: for each (root, level, single or multi-leg, days to expiry), the LOWER median over Train's
  hits of the contracts that traded at or through the level in that contract-minute beyond the queue
  ahead (at the touch, the volume less the displayed size; inside the spread, the volume), at least 1. The engine caps a passive fill at it (one structure where the table has no size).

Paper fills prove the route only and never calibrate the model; real fills will. The table goes to a
gitignored path: fitted parameters of licensed data never enter git or anything published.

WHERE IT GOES. `scripts/data/calibration.py` runs this on the sealed Gym image with the current code,
writes the same file to `/data/calibration/fill_model.json` on both the Gym and the gate image, and
checkpoints them. Every loader (`fills.FillModel.load`) takes, in order: an explicit path (`batch.py
--fill-model`, `RunConfig.fill_model`), `GYM_FILL_MODEL`, `/data/calibration/fill_model.json`, then
`.data/gym/fill_model.json` under the code's root; none found is natural-only. A conditional fit is a
candidate until adopted: without `--out` it goes to `fill_model.conditional.json` beside the default,
and it is refused at a default path (where every loader would pick it up) unless `--adopt` says so.

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
#: Side-minutes of exposure a (root, dte, moneyness) bucket needs to have cells at all (10x the prior).
MIN_BUCKET = 6000.0
#: The trade sample's strikes each side of the money (scripts/data/storelib.py TQ_STRIKE_RANGE), and its reach.
SAMPLE_STRIKES = 10
SAMPLE_MAX_DTE = F.MODELLED_DTE
#: The size histogram's bins: 0 .. SIZE_BINS - 1 contracts beyond the queue (larger fills count in the last).
SIZE_BINS = 5001
D_BUCKETS = tuple(range(len(F.DTE_EDGES)))
K_BUCKETS = tuple(range(len(F.MONEY_EDGES) + 1))
T_BUCKETS = tuple(range(len(F.TOD_EDGES) + 1))
LAPTOP_OUT = Path(__file__).resolve().parents[2] / ".data" / "gym" / "fill_model.json"
#: The adverse-selection rules a fit can carry (`fills.py`): `hazard` alone, or also its two conditional tables.
ADVERSE_RULES = ("unconditional", F.CONDITIONAL)
#: The engine's flat tolerance on the next minute's mid (`engine.Account._next_move`).
FLAT = 1e-9


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


def lower_median(counts: np.ndarray) -> int:
    """The lower median of a histogram of whole contracts (bin i holds the hits that found i), at least 1."""
    total = int(counts.sum())
    if total <= 0:
        return 1
    return max(1, int(np.searchsorted(np.cumsum(counts), (total + 1) // 2)))


def _rate(hits: float, exposure: float, prior: float, parent: float) -> float:
    """One level of the shrinkage: hits over exposure, pulled toward `parent` by `prior` pseudo side-minutes
    (the parent itself where there is neither: a conditional cell with no minute of its condition)."""
    return (hits + prior * parent) / (exposure + prior) if exposure + prior > 0 else parent


def _totals(exposure: dict[tuple[str, int], float], hits: dict[tuple[str, int], float] | None = None) -> tuple[dict, ...]:
    """Exposure (and hits) summed to (root), (root, d) and (root, d, k)."""
    n0: dict[str, float] = {}
    k0: dict[str, float] = {}
    n1: dict[tuple[str, int], float] = {}
    k1: dict[tuple[str, int], float] = {}
    n2: dict[tuple[str, int, int], float] = {}
    k2: dict[tuple[str, int, int], float] = {}
    for (root, code), n in exposure.items():
        d, k, _ = _decode(code)
        h = hits.get((root, code), 0.0) if hits is not None else 0.0
        for nd, kd, key in ((n0, k0, root), (n1, k1, (root, d)), (n2, k2, (root, d, k))):
            nd[key] = nd.get(key, 0.0) + n
            kd[key] = kd.get(key, 0.0) + h
    return n0, k0, n1, k1, n2, k2


def shrink(exposure: dict[tuple[str, int], float], hits: dict[tuple[str, int], float],
           prior: float, min_bucket: float = MIN_BUCKET, *,
           gate: dict[tuple[str, int], float] | None = None) -> dict[tuple[str, int, int, int], float]:
    """{(root, d, k, t): rate} for every cell of every (root, days-to-expiry, moneyness) bucket with at least
    `min_bucket` side-minutes of exposure, from exposures and hits keyed by (root, cell code): the MLE shrunk
    toward (root, d, k), (root, d), (root), then every root pooled (the module docstring). Nothing else.
    `gate`: the exposure that decides which roots and buckets have cells (a conditional table's exposure
    and hits, with the unconditional exposure as the gate, get exactly the unconditional table's buckets)."""
    total_n = sum(exposure.values())
    if total_n <= 0:
        return {}
    pooled = sum(hits.values()) / total_n
    n0, k0, n1, k1, n2, k2 = _totals(exposure, hits)
    g0, _, g1, _, g2, _ = (n0, k0, n1, k1, n2, k2) if gate is None else _totals(gate)
    out: dict[tuple[str, int, int, int], float] = {}
    for root in sorted(g0):
        r0 = _rate(k0.get(root, 0.0), n0.get(root, 0.0), prior, pooled)
        for d in D_BUCKETS:
            if g1.get((root, d), 0.0) <= 0:
                continue  # never sampled: no cells (natural fills only)
            r1 = _rate(k1.get((root, d), 0.0), n1.get((root, d), 0.0), prior, r0)
            for k in K_BUCKETS:
                if g2.get((root, d, k), 0.0) <= 0.0 or g2[root, d, k] < min_bucket:
                    continue  # never or too little sampled (a wing the band barely reaches): no cells, natural fills only
                r2 = _rate(k2.get((root, d, k), 0.0), n2.get((root, d, k), 0.0), prior, r1)
                for t in T_BUCKETS:
                    code = (d * 10 + k) * 10 + t
                    out[root, d, k, t] = _rate(hits.get((root, code), 0.0), exposure.get((root, code), 0.0), prior, r2)
    return out


def next_moves(chain) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(known, up, down) per [minute, contract]: whether the next minute has a two-sided quote, and whether its
    mid is above or below this minute's by more than the engine's flat tolerance (`engine.Account._next_move`
    on one leg: a resting buy is adversely selected unless `up`, a resting sell unless `down`)."""
    mid = 0.5 * (chain.bid + chain.ask)
    known = np.zeros(mid.shape, dtype=bool)
    up = np.zeros(mid.shape, dtype=bool)
    down = np.zeros(mid.shape, dtype=bool)
    now, nxt = mid[:-1], mid[1:]
    with np.errstate(invalid="ignore"):
        known[:-1] = np.isfinite(now) & np.isfinite(nxt)
        up[:-1] = known[:-1] & (nxt > now + FLAT)
        down[:-1] = known[:-1] & (nxt < now - FLAT)
    return known, up, down


def fit(store: Store, roots: Sequence[str], *, days: Sequence[dt.date] | None = None, prior: float = PRIOR,
        sample_strikes: int = SAMPLE_STRIKES, min_bucket: float = MIN_BUCKET, adverse: str = "unconditional") -> dict:
    """The fitted table and what it was fitted on (see the module docstring). `adverse="conditional"` adds
    the cells measured per next-minute condition and the table's marker."""
    if adverse not in ADVERSE_RULES:
        raise ValueError(f"adverse is one of {', '.join(ADVERSE_RULES)}, not {adverse!r}")
    conditional = adverse == F.CONDITIONAL
    exposure: dict[tuple[str, int], float] = {}
    hits: dict[str, dict[int, dict[tuple[str, int], float]]] = {cls: {q: {} for q in Q_BUCKETS} for cls in ("s", "m")}
    # The conditional fit: exposure and hits split by the next minute, "a" adverse-or-flat, "f" favourable.
    cond_exposure: dict[str, dict[tuple[str, int], float]] = {"a": {}, "f": {}}
    cond_hits: dict[str, dict[str, dict[int, dict[tuple[str, int], float]]]] = {
        c: {cls: {q: {} for q in Q_BUCKETS} for cls in ("s", "m")} for c in ("a", "f")}
    split = {"adverse_side_minutes": 0, "favourable_side_minutes": 0, "no_next_quote_contract_minutes": 0}
    # (root, q, class, dte bucket) -> a histogram of the contracts beyond the queue at each hit (capped at SIZE_BINS - 1)
    excess: dict[tuple[str, int, str, int], np.ndarray] = {}
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
                exposure[root, int(code)] = exposure.get((root, int(code)), 0.0) + 2.0 * float(n)   # a resting buy and a resting sell
            if conditional:
                known, up, down = next_moves(chain)
                k, u, dn = known[mm, contract], up[mm, contract], down[mm, contract]
                # Per contract-minute: a resting buy is adverse unless the mid rises, a resting sell unless it falls
                # (flat: adverse for both), so a known minute is two side-minutes split between the conditions.
                side_minutes = {"a": (k & ~u).astype(np.float64) + (k & ~dn), "f": u.astype(np.float64) + dn}
                codes_u, inverse = np.unique(cell, return_inverse=True)
                for c, weight in side_minutes.items():
                    sums = np.bincount(inverse, weights=weight, minlength=codes_u.size)
                    for code, n in zip(codes_u, sums):
                        if n > 0:
                            cond_exposure[c][root, int(code)] = cond_exposure[c].get((root, int(code)), 0.0) + float(n)
                split["adverse_side_minutes"] += int(side_minutes["a"].sum())
                split["favourable_side_minutes"] += int(side_minutes["f"].sum())
                split["no_next_quote_contract_minutes"] += int((~k).sum())
            # Hits: contract-minutes with a print at or past each level, buys and sells separately.
            pmoney = chain.strike[idx] / spot[minute] - 1.0
            pcell = _cells(chain.dte[idx], pmoney, chain.open_min + minute)
            key = idx * 10_000 + minute
            pdte = np.searchsorted(np.array(F.DTE_EDGES[1:]), chain.dte[idx], side="right")

            def count(cls: str, q: int, sel: np.ndarray, queue: np.ndarray | None, buyer: bool) -> None:
                """The contract-minutes of `sel`'s prints that fill a resting order at level q: per contract-minute,
                the contracts traded at or through it beyond `queue` (the displayed size ahead; None inside the spread).
                `buyer`: the resting order's side (a conditional fit splits its hits by the next minute's move)."""
                if not sel.any():
                    return
                uniq, inverse = np.unique(key[sel], return_inverse=True)
                volume = np.bincount(inverse, weights=size[sel].astype(np.float64), minlength=uniq.size)
                ahead = np.zeros(uniq.size, dtype=np.float64)
                if queue is not None:
                    ahead[inverse] = queue[minute[sel], idx[sel]]
                cells = np.zeros(uniq.size, dtype=np.int64)
                cells[inverse] = pcell[sel]
                dbucket = np.zeros(uniq.size, dtype=np.int64)
                dbucket[inverse] = pdte[sel]
                filled = volume > ahead
                for code, n in zip(*np.unique(cells[filled], return_counts=True)):
                    hits[cls][q][root, int(code)] = hits[cls][q].get((root, int(code)), 0.0) + float(n)
                if conditional:
                    at, contract_u = uniq % 10_000, uniq // 10_000
                    k = known[at, contract_u]
                    against = ~(up if buyer else down)[at, contract_u]    # adverse or flat for this side
                    for c, which in (("a", filled & k & against), ("f", filled & k & ~against)):
                        book = cond_hits[c][cls][q]
                        for code, n in zip(*np.unique(cells[which], return_counts=True)):
                            book[root, int(code)] = book.get((root, int(code)), 0.0) + float(n)
                beyond = np.minimum(np.rint(volume - ahead)[filled], SIZE_BINS - 1).astype(np.int64)
                for d in np.unique(dbucket[filled]):
                    counts = np.bincount(beyond[dbucket[filled] == d], minlength=SIZE_BINS)
                    group = (root, q, cls, int(d))
                    excess[group] = counts if group not in excess else excess[group] + counts

            for cls, mask in (("s", ~multi), ("m", multi)):
                for q, level in LEVELS.items():
                    for side, buyer in ((pos <= level, True), (pos >= -level, False)):     # a resting buy; a resting sell
                        count(cls, q, mask & side, None, buyer)
                # The touch: a buy at the bid (a sell at the ask) behind the queue the NBBO showed at the minute.
                for side, queue, buyer in ((pos <= F.TOUCH, chain.bid_size, True), (pos >= -F.TOUCH, chain.ask_size, False)):
                    count(cls, TOUCH_BUCKET, mask & side, queue, buyer)
    def table(side_exposure: dict[tuple[str, int], float], side_hits: dict[str, dict[int, dict[tuple[str, int], float]]],
              gate: dict[tuple[str, int], float] | None = None) -> dict[str, float]:
        out: dict[str, float] = {}
        for cls in ("s", "m"):
            for q in Q_BUCKETS:
                for (root, d, k, t), p in shrink(side_exposure, side_hits[cls][q], float(prior), float(min_bucket), gate=gate).items():
                    rounded = round(min(1.0, max(0.0, p)), 6)
                    if rounded > 0:
                        out[f"{root}|q{q}|{cls}|d{d}|k{k}|t{t}"] = rounded
        return dict(sorted(out.items()))

    hazard = table(exposure, hits)
    sizes = {f"{root}|q{q}|{cls}|d{d}": lower_median(counts) for (root, q, cls, d), counts in excess.items()}
    fitted = {"source": "league.gym.calibrate", "hazard": hazard, "size": dict(sorted(sizes.items())),
              "meta": {"fitted_on": seen, "roots": list(roots), "cells_with_exposure": len(exposure),
                       "prior": float(prior), "min_bucket": float(min_bucket), "sample_strikes": int(sample_strikes),
                       "modelled_dte": F.MODELLED_DTE,
                       "conditions": dict(sorted(codes.items())),
                       "fitted_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                       "rule": "per-root per-minute MLE over quoted contract-minutes in the sample's strike band, shrunk toward "
                               "coarser cells (time -> moneyness -> dte -> root -> every root) with `prior` pseudo side-minutes; "
                               "unsampled roots and dte buckets have no cells; each level at its least aggressive edge; the touch "
                               "(q0) only where the minute's volume there exceeded the displayed queue; multi-leg from complex "
                               "prints leg by leg; size the median contracts beyond the queue"}}
    if conditional:
        fitted["adverse"] = F.CONDITIONAL
        fitted["hazard_adverse"] = table(cond_exposure["a"], cond_hits["a"], gate=exposure)
        fitted["hazard_favourable"] = table(cond_exposure["f"], cond_hits["f"], gate=exposure)
        fitted["meta"]["fitted_on"].update(split)
        fitted["meta"]["adverse_rule"] = (
            "each cell also measured on the side-minutes whose next minute's mid moves against the resting order or holds "
            "(hazard_adverse) and on those where it moves the order's way (hazard_favourable), the engine's own test; a "
            "contract-minute with no next two-sided quote is in neither; each condition shrunk toward its own coarser cells "
            "with the same prior, on the unconditional table's buckets")
    return fitted


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m league.gym.calibrate")
    parser.add_argument("--store", default="/data/store")
    parser.add_argument("--roots", default="SPY,QQQ,IWM,XSP,SPXW")
    parser.add_argument("--out", default=None)
    parser.add_argument("--prior", type=float, default=PRIOR, help="pseudo side-minutes a cell borrows from its coarser parent")
    parser.add_argument("--sample-strikes", type=int, default=SAMPLE_STRIKES, help="the trade sample's strikes each side of the money")
    parser.add_argument("--min-bucket", type=float, default=MIN_BUCKET,
                        help="side-minutes a (root, dte, moneyness) bucket needs to have cells")
    parser.add_argument("--adverse", choices=ADVERSE_RULES, default="unconditional",
                        help="conditional: also fit each cell per next-minute condition (the module docstring)")
    parser.add_argument("--adopt", action="store_true",
                        help="allow a conditional fit at a default loader path (adopting it for every run that loads the default)")
    args = parser.parse_args(argv)
    default = Path("/data/calibration/fill_model.json") if Path("/data").is_dir() and Path("/data/store").is_dir() else LAPTOP_OUT
    conditional = args.adverse == F.CONDITIONAL
    out = Path(args.out) if args.out else (default.with_name("fill_model.conditional.json") if conditional else default)
    loaded_by_default = {Path(p).resolve() for p in (*F.DEFAULT_PATHS, LAPTOP_OUT)}
    if conditional and not args.adopt and out.resolve() in loaded_by_default:
        print(f"refused: {out} is where every loader finds its table; a conditional fit goes elsewhere until it is adopted (--adopt)")
        return 2
    store = Store(args.store)
    roots = [r.strip().upper() for r in args.roots.split(",") if r.strip()]
    roots = [r for r in roots if any(store.has("trade_quote", r, d) for d in store.trading_days() if window_of(d) == "train")]
    if not roots:
        print(f"no Train trade_quote samples in {args.store}")
        return 3
    table = fit(store, roots, prior=args.prior, sample_strikes=args.sample_strikes, min_bucket=args.min_bucket,
                adverse=args.adverse)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(table, indent=1, sort_keys=True))
    tmp.chmod(0o600)
    tmp.replace(out)
    extra = {"adverse": F.CONDITIONAL, "cells_adverse": len(table["hazard_adverse"]),
             "cells_favourable": len(table["hazard_favourable"])} if conditional else {}
    print(json.dumps({"out": str(out), "cells": len(table["hazard"]), **extra, **table["meta"]["fitted_on"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
