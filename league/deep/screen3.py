"""S3, THE TWO-KEY SCREEN (PREREG-H): the deep key on DVAL, the recent key on R + V + H, their bars and own floors, and
the eligibility rules. Code only; the pinned figures are `config`'s.

Owner: R1. Reused by import, never copied: league/equity/screen.py `series` (the accounting), `holdout_t` and
`pooled_t` (the t), its c grid (k / 100, k = 0..500). Nothing here reads a store: the look (league/deep/gate.py) hands
in series.

THE DEEP KEY (`deep_key`): pass iff t(x2) >= c_D on BOTH the masked series (the 1,709 sessions outside the nine
windows, when the whole of DVAL is scored) and the full series (1,944), AND the k 3.0 stress sum of x2 is above zero.
Losses in the famous windows count; gains made only there do not (the mask is one-sided). c_D = max(the receipt's
bar at 15% zero-edge FP alone, the program's own floor + 0.05), in whole grid steps (`bar`).

THE RECENT KEY (`recent_key`): the pooled t of the lane's S2 variant (r at k 1.0) over R + V + H >= c_R, with
sum_H > 0. c_R = max(the receipt's bar at 12% alone, own floor + 0.05). The receipt calibrates it with the reserve in
it; D2 is "judged" (A58), so every real look reads both keys, and with the reserve sealed no look is made at all
(league/deep/gate.py: both keys or neither).

PASS = both keys (`verdict`). A canary is judged on the deep key alone.

THE OWN FLOORS (`deep_floor`, `recent_floor`; the receipt's `floor`, docs/benchmarks/equity_screen_3.json): the
program's own sessions on TRAIN and TRAIN-D (its 2016-19 and 2022-24 runs and its relabeled 2010-15 run, each from its
first decision + 2 sessions: `stat.piece`), null N0 per key (x0 = x - w kappa, kappa = sum x / sum w over the pool),
worlds of the key's geometry filled by a stationary block bootstrap (mean block 120, each block circular inside one
piece, the piece drawn in proportion to its length), 20,000 a world set: BASE, and CRASH (the deep world's mask
positions, and the recent world's 2020-02-20..03-23 positions, filled with blocks that start in the pool's stress
sessions: the top 5% by trailing 20-session realized vol of the equal-weight cost-free return; TRAIN-D brings August
2011 and August 2015). In each world the key is computed as judged (x2 with each world's own mu, full and masked).
A floor is the smallest c on the grid whose pass rate is at most the key's FP in BOTH sets; none (INELIGIBLE) with
no pool piece of 300 sessions, no exposure, or a floor past 5.00. Seeds: default_rng([20261017, 3, 7, set, key,
int(version sha256[:8], 16)]).

THE RULES (`layout`, `rules`): ETF only (DVAL's 15); at most 50 round trips a year and at most 25% close-to-next-open
lots on the Train-era runs; segment A only for the liquid core, a late SPDR in B only when its stale-close audit is
clean; no segment where a NEEDS symbol misses a session after its first bar (the data audit's gaps: a lot held through
a missing session has no price, and the look would fail on the data, not the program); at least 750 scored DVAL
sessions after inception and look-back; never a strong-recall route.
"""

from __future__ import annotations

import datetime as dt
import math
from typing import Any, Mapping, Sequence

import numpy as np

from ..equity import screen
from . import calendar, config
from . import stat as S

ZERO = 1e-12


# ----------------------------------------------------------------------------------------------------------- the bars
def grid_k(c: float, *, up: bool = True) -> int:
    """c in whole grid steps (k = 100 c): rounded up for a receipt's figure (`up`), to the nearest for a grid value."""
    value = round(float(c) * 100.0, 6)
    return int(math.ceil(value)) if up else int(round(value))


def bar(receipt_c: float, floor_c: float | None) -> float | None:
    """max(the receipt's bar, own floor + `config.FLOOR_MARGIN`) on the grid; None (INELIGIBLE) without a floor or
    past 5.00."""
    if floor_c is None or not math.isfinite(float(receipt_c)):
        return None
    k = max(grid_k(receipt_c), grid_k(floor_c, up=False) + grid_k(config.FLOOR_MARGIN, up=False))
    return None if k > config.GRID_MAX_K else k / 100.0


# ----------------------------------------------------------------------------------------------------------- the keys
def deep_key(x_full: np.ndarray, x_masked: np.ndarray, x3_sum: float, c: float) -> dict[str, Any]:
    """{"passed", "checks": {"full", "masked", "stress"}}: booleans only (a t is never returned: DVAL figures beyond
    pass or fail stay inside the look)."""
    t_full, t_masked = S.t(x_full), S.t(x_masked)
    checks = {"full": t_full is not None and t_full >= c, "masked": t_masked is not None and t_masked >= c,
              "stress": float(x3_sum) > ZERO}
    return {"passed": all(checks.values()), "checks": checks}


def recent_key(parts: Sequence[np.ndarray], c: float) -> dict[str, Any]:
    """`parts`: the recent windows' daily r in order, H last ([V, H] or [R, V, H]). {"passed", "checks": {"t",
    "sum_h"}}: booleans only."""
    if len(parts) < 2:
        raise ValueError("the recent key reads V and H at least")
    pooled = screen.pooled_t(np.concatenate([np.asarray(p, dtype=np.float64) for p in parts[:-1]]),
                             np.asarray(parts[-1], dtype=np.float64))
    checks = {"t": pooled is not None and pooled >= c, "sum_h": float(np.sum(parts[-1])) > ZERO}
    return {"passed": all(checks.values()), "checks": checks}


def verdict(deep: Mapping[str, Any], recent: Mapping[str, Any] | None) -> dict[str, Any]:
    """PASS = both keys: {"passed", "deep", "recent"} (`recent` None: a canary, judged on the deep key alone)."""
    d = bool(deep.get("passed"))
    r = None if recent is None else bool(recent.get("passed"))
    return {"passed": d and (r is None or r), "deep": d, "recent": r}


# ---------------------------------------------------------------------------------------------------------- the floors
class Pool:
    """The program's own-floor pool: its pieces (`stat.piece`, each `config.MIN_PIECE` sessions or longer) joined, with
    each piece's length and offset, and the stress sessions of the CRASH set."""

    def __init__(self, pieces: Sequence[Mapping[str, np.ndarray]]):
        usable = [p for p in pieces if len(p["w"]) >= config.MIN_PIECE]
        if not usable:
            raise ValueError("no pool piece of 300 sessions")
        self.lens = np.array([len(p["w"]) for p in usable], dtype=np.int64)
        self.offsets = np.concatenate([[0], np.cumsum(self.lens)[:-1]]).astype(np.int64)
        self.r2 = np.concatenate([np.asarray(p["r2"], dtype=np.float64) for p in usable])
        self.r1 = np.concatenate([np.asarray(p["r1"], dtype=np.float64) for p in usable])
        self.w = np.concatenate([np.asarray(p["w"], dtype=np.float64) for p in usable])
        self.W = np.concatenate([np.asarray(p["W"], dtype=np.float64) for p in usable], axis=1)
        self.RET = np.concatenate([np.asarray(p["RET"], dtype=np.float64) for p in usable], axis=1)
        self.stress = self._stress([np.asarray(p["b"], dtype=np.float64) for p in usable])

    def _stress(self, bs: Sequence[np.ndarray]) -> np.ndarray:
        """The top `STRESS_SHARE` of the pool's sessions by the trailing `STRESS_LOOKBACK`-session realized vol of the
        equal-weight cost-free return (inside each piece), as indices into the joined pool."""
        vols = []
        for b in bs:
            n, look = len(b), config.STRESS_LOOKBACK
            vol = np.zeros(n)
            for t in range(n):
                window = b[max(0, t - look + 1):t + 1]
                vol[t] = float(np.std(window)) if window.size > 1 else 0.0
            vols.append(vol)
        joined = np.concatenate(vols)
        cut = np.quantile(joined, 1.0 - config.STRESS_SHARE)
        return np.flatnonzero(joined >= cut)

    @staticmethod
    def kappa(x: np.ndarray, w: np.ndarray) -> float | None:
        total = float(np.sum(w))
        return float(np.sum(x)) / total if total > ZERO else None

    def mu(self) -> np.ndarray:
        """Each symbol's mean cost-free return over the pool (0 for one with none)."""
        ok = np.isfinite(self.RET)
        count = ok.sum(1)
        return np.where(count > 0, np.where(ok, self.RET, 0.0).sum(1) / np.maximum(count, 1), 0.0)


def _rng(world_set: int, key: int, version_tag: int) -> np.random.Generator:
    return np.random.default_rng([*config.FLOOR_SEED, int(world_set), int(key), int(version_tag)])


def _worlds(rng: np.random.Generator, pool: Pool, n: int, length: int, stress_at: np.ndarray | None) -> np.ndarray:
    """(n, length) indices into the joined pool: THE STATIONARY BLOCK BOOTSTRAP (a new block at each position with
    probability 1 / `FLOOR_BLOCK`, each block circular inside one piece drawn in proportion to its length, a uniform
    start). `stress_at` (bool per position, the CRASH set): those positions are filled with blocks that START in the
    pool's stress sessions (a new block at each stretch's first position and as above inside it), and the position
    after a stretch starts a BASE block again."""
    new = rng.random((n, length)) < 1.0 / config.FLOOR_BLOCK
    new[:, 0] = True
    piece = rng.choice(len(pool.lens), size=(n, length), p=pool.lens / pool.lens.sum())
    start = np.floor(rng.random((n, length)) * pool.lens[piece]).astype(np.int64)
    if stress_at is not None:
        at = np.asarray(stress_at, dtype=bool)
        edges = at & ~np.concatenate([[False], at[:-1]])
        after = ~at & np.concatenate([[False], at[:-1]])
        new[:, edges | after] = True
        pick = pool.stress[rng.integers(0, len(pool.stress), size=(n, int(at.sum())))]
        owner = np.searchsorted(pool.offsets, pick, side="right") - 1
        piece[:, at] = owner
        start[:, at] = pick - pool.offsets[owner]
    steps = np.arange(length)
    begun = np.maximum.accumulate(np.where(new, steps[None, :], 0), axis=1)
    p_at = np.take_along_axis(piece, begun, axis=1)
    s_at = np.take_along_axis(start, begun, axis=1)
    return pool.offsets[p_at] + (s_at + (steps[None, :] - begun)) % pool.lens[p_at]


def _row_t(x: np.ndarray) -> np.ndarray:
    n = x.shape[1]
    if n < 2:
        return np.full(x.shape[0], -np.inf)
    sd = x.std(axis=1, ddof=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        t = x.mean(axis=1) / sd * math.sqrt(n)
    return np.where(sd >= ZERO, t, -np.inf)


def _first_k(stat: np.ndarray, fp: float) -> int | None:
    """The smallest grid k whose pass rate (stat >= k / 100) is at most `fp`; None past the grid."""
    worlds = stat.shape[0]
    allowed = math.floor(fp * worlds + 1e-9)
    srt = np.sort(stat)
    for k in range(config.GRID_MAX_K + 1):
        if worlds - int(np.searchsorted(srt, k / 100.0, side="left")) <= allowed:
            return k
    return None


def _x2_rows(pool: Pool, idx: np.ndarray, base: np.ndarray, cols: np.ndarray | None) -> np.ndarray:
    """x2 of each world row over its positions `cols` (None: all): base - sum_s w_s mu_s, mu_s the symbol's mean
    cost-free return over THOSE sessions of the row (the statistic as judged)."""
    sub = idx if cols is None else idx[:, cols]
    out = (base if cols is None else base[:, cols]).copy()
    for s in range(pool.W.shape[0]):
        ret = pool.RET[s][sub]
        ok = np.isfinite(ret)
        count = ok.sum(1)
        mu = np.where(count > 0, np.where(ok, ret, 0.0).sum(1) / np.maximum(count, 1), 0.0)
        out -= pool.W[s][sub] * mu[:, None]
    return out


def deep_floor(pieces: Sequence[Mapping[str, np.ndarray]], keep: np.ndarray, *, version_tag: int,
               fp: float = config.DEEP_FP, worlds: int = config.FLOOR_WORLDS) -> float | None:
    """c_pD (the receipt's `floor`): the smallest c on the grid with share(t_mask >= c AND t_full >= c) <= `fp` in
    BOTH world sets (BASE 1, CRASH 2: the mask's positions filled from the stress sessions), on worlds of the
    program's scored layout (`keep`: its unmasked flags, joined), null N0 (x0 = x - w kappa, kappa = sum x2 / sum w
    over the pool), x2 recomputed with each world's own mu. None: INELIGIBLE (no pool, no exposure, past 5.00)."""
    try:
        pool = Pool(pieces)
    except ValueError:
        return None
    keep = np.asarray(keep, dtype=bool)
    x_pool = pool.r2 - (pool.W * pool.mu()[:, None]).sum(0)
    kappa = pool.kappa(x_pool, pool.w)
    if kappa is None or keep.sum() < 2:
        return None
    cols = np.flatnonzero(keep)
    worst = 0
    for world_set, stress_at in ((1, None), (2, ~keep)):
        rng = _rng(world_set, 1, version_tag)
        stats = []
        for begin in range(0, worlds, config.FLOOR_CHUNK):
            n = min(config.FLOOR_CHUNK, worlds - begin)
            idx = _worlds(rng, pool, n, keep.shape[0], stress_at)
            base = pool.r2[idx] - pool.w[idx] * kappa
            stats.append(np.minimum(_row_t(_x2_rows(pool, idx, base, None)), _row_t(_x2_rows(pool, idx, base, cols))))
        k = _first_k(np.concatenate(stats), fp)
        if k is None:
            return None
        worst = max(worst, k)
    return worst / 100.0


def recent_stress_positions() -> np.ndarray:
    """The recent world's CRASH positions: R's sessions 2020-02-20..2020-03-23, in the R + V + H geometry."""
    from ..equity import store as estore

    r_days = [d for d, _ in estore.nyse_sessions(*config.RESERVE)]
    lens = config.RECENT_LENGTHS
    at = np.zeros(lens["R"] + lens["V"] + lens["H"], dtype=bool)
    first, last = config.RECENT_STRESS
    for i, day in enumerate(r_days[:lens["R"]]):
        at[i] = first <= day <= last
    return at


def recent_floor(pieces: Sequence[Mapping[str, np.ndarray]], *, version_tag: int, fp: float = config.RECENT_FP,
                 worlds: int = config.FLOOR_WORLDS) -> float | None:
    """c_pR (the receipt's `floor`): the smallest c with share(pooled t of R+V+H >= c AND sum_H > 1e-12) <= `fp` in
    BOTH world sets (CRASH: R's 2020-02-20..03-23 positions filled from the stress sessions), null N0 on r at k 1.0.
    None: INELIGIBLE."""
    try:
        pool = Pool(pieces)
    except ValueError:
        return None
    kappa = pool.kappa(pool.r1, pool.w)
    if kappa is None:
        return None
    lens = config.RECENT_LENGTHS
    length, h = lens["R"] + lens["V"] + lens["H"], lens["H"]
    worst = 0
    for world_set, stress_at in ((1, None), (2, recent_stress_positions())):
        rng = _rng(world_set, 2, version_tag)
        stats = []
        for begin in range(0, worlds, config.FLOOR_CHUNK):
            n = min(config.FLOOR_CHUNK, worlds - begin)
            idx = _worlds(rng, pool, n, length, stress_at)
            x = pool.r1[idx] - pool.w[idx] * kappa
            stats.append(np.where(x[:, -h:].sum(axis=1) > ZERO, _row_t(x), -np.inf))
        k = _first_k(np.concatenate(stats), fp)
        if k is None:
            return None
        worst = max(worst, k)
    return worst / 100.0


# ----------------------------------------------------------------------------------------------------------- the rules
def etf_only(symbols: Sequence[str]) -> bool:
    """Every NEEDS symbol is one of DVAL's 15 ETFs."""
    return bool(symbols) and all(str(s).upper() in config.DEEP_UNIVERSE for s in symbols)


def round_trips_a_year(runs: Sequence[tuple[Sequence[Mapping[str, Any]], int]]) -> float:
    """Closed lots a year over runs given as (lots, run sessions): sum closed / (sum sessions / 252)."""
    closed = sum(1 for lots, _ in runs for lot in lots if lot.get("exit_day") not in (None, ""))
    sessions = sum(int(n) for _, n in runs)
    return closed / (sessions / 252.0) if sessions > 0 else 0.0


def overnight_share(lots: Sequence[Mapping[str, Any]]) -> float:
    """The share of lots bought at a close and sold at the next session's open (0 with no lot)."""
    lots = list(lots)
    hits = sum(1 for lot in lots if lot.get("entry_at") == "close" and lot.get("exit_at") == "open"
               and int(lot.get("held_sessions") or 0) == 1)
    return hits / len(lots) if lots else 0.0


def layout(symbols: Sequence[str], history: int, first_days: Mapping[str, dt.date | None],
           late_clean: Mapping[str, bool], gaps: Mapping[str, Mapping[str, int]] | None = None) -> dict[str, Any]:
    """THE SCORED LAYOUT of a program over DVAL: {"segments": {name: {"start": the first scored session (an index
    into the segment's sessions, look-back first), "sessions": scored sessions} | None}, "scored", "masked"
    (sessions outside the mask), "why": None or why a segment is not scored}. A segment is scored from the first
    session at which every NEEDS symbol has `history` bars before the first decision's close, so history + 1 at that
    decision (the engine's ctx: league/equity/store.py `_slice` gives a run history + 1 sessions before its first; its
    first bar is `first_days[sym]`); A only for the liquid core; B with a late SPDR only when `late_clean[sym]`;
    neither where a NEEDS symbol has a gap (`gaps[sym][span]` > 0, the audit's count of sessions missing after its
    first bar) in a span the segment reads (`config.SEGMENT_SPANS`)."""
    names = [str(s).upper() for s in symbols]
    masked = set(calendar.mask())
    gaps = gaps or {}
    out: dict[str, Any] = {"segments": {}, "scored": 0, "masked": 0, "why": {}}
    for name in config.DVAL_SEGMENTS:
        back, scored = calendar.segment(name)
        days = back + scored
        if name == "A" and any(s not in config.LIQUID_CORE for s in names):
            out["segments"][name] = None
            out["why"][name] = "segment A is the liquid core only"
            continue
        if name == "B" and any(s in config.LATE_SPDRS and not late_clean.get(s) for s in names):
            out["segments"][name] = None
            out["why"][name] = "a late SPDR's stale-close audit is not clean"
            continue
        if any(int((gaps.get(s) or {}).get(span) or 0) > 0 for s in names for span in config.SEGMENT_SPANS[name]):
            out["segments"][name] = None
            out["why"][name] = "a NEEDS symbol misses a session of the segment (the data audit's gaps)"
            continue
        start = len(back)
        for s in names:
            first = first_days.get(s)
            if first is None or first > days[-1]:
                start = len(days)
                break
            i0 = next(i for i, d in enumerate(days) if d >= first)
            start = max(start, i0 + int(history) + 1)
        n = len(days) - start
        if n <= 0:
            out["segments"][name] = None
            out["why"][name] = "no scored session after inception and look-back"
            continue
        out["segments"][name] = {"start": start, "sessions": n}
        out["scored"] += n
        out["masked"] += sum(1 for d in days[start:] if d not in masked)
    return out


def rules(*, symbols: Sequence[str], history: int, first_days: Mapping[str, dt.date | None],
          late_clean: Mapping[str, bool], round_trips: float, overnight: float, strong_recall: bool | None,
          blind: bool, gaps: Mapping[str, Mapping[str, int]] | None = None) -> dict[str, Any]:
    """PREREG-H's eligibility, in order: {"eligible", "why" (the first rule failed, None), "wait", "layout"}. A route
    whose 2001-08 recall the probe has not measured yet (`strong_recall` None) is no refusal: the look WAITS
    (`wait` True) until it is measured, so no look is spent on a route the probe may yet find remembers the era.
    `gaps`: the data audit's gaps by symbol and span (`layout`)."""
    plan = layout(symbols, history, first_days, late_clean, gaps) if etf_only(symbols) else None
    checks = (
        (etf_only(symbols), "not ETF only (DVAL's 15)"),
        (bool(blind), "not calendar-blind"),
        (round_trips <= config.MAX_ROUND_TRIPS_A_YEAR, "more than 50 round trips a year"),
        (overnight <= config.MAX_OVERNIGHT_SHARE, "more than 25% close-to-next-open lots"),
        (plan is not None and plan["scored"] >= config.MIN_SCORED_SESSIONS, "fewer than 750 scored DVAL sessions"),
        (strong_recall is not True, "a strong-recall route on contam_probe's 2001-08 cells"),
    )
    why = next((text for ok, text in checks if not ok), None)
    if why is None and strong_recall is None:
        return {"eligible": False, "why": "the route's 2001-08 recall is not measured yet", "wait": True,
                "layout": plan}
    return {"eligible": why is None, "why": why, "wait": False, "layout": plan}


__all__ = ["ZERO", "grid_k", "bar", "deep_key", "recent_key", "verdict", "Pool", "deep_floor", "recent_stress_positions",
           "recent_floor", "etf_only", "round_trips_a_year", "overnight_share", "layout", "rules"]
