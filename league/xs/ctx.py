"""What a panel program sees at the decision close of session t: built by one function, in the Gym and live (I6).

Owner: package C.

The Gym engine builds `Inputs` from the run's `store.PanelBars` (`inputs_from_panel`); the live book builds them from
its chunked 16:20 ET fetch (`inputs_from_arrays`), and the decider child calls `build` on them. Both paths end in
`build`, so a program sees the same ctx for the same decision day, columns and run key (`ctx_bytes`; package D's
`test_xs_i6.py` holds it on synthetic panels, the nightly I6 on real bars).

THE CONTRACT IS THE PINNED PRE-REGISTRATION'S C1 (XSCREEN-1 revision 2, section 2; it overrides E4-SPEC D7 where they
differ: no price array, no event flag, no `dv_decile`; the builder may make it narrower, never wider, without a new
receipt). ctx at the decision close of session t (n = the eligible names U(t), rows in ASCENDING id; h = NEEDS history):

    ctx.n                         how many slots
    ctx.ids                       int32 (n,): the salted slot ids (stable inside one run, unrelated across runs)
    ctx.ret                       float64 (n, h + 1): close-to-close total return (NaN first, NaN where no bar)
    ctx.oret                      (n, h + 1): open over the previous close - 1
    ctx.iret                      (n, h + 1): close over open - 1
    ctx.range                     (n, h + 1): (high - low) / close
    ctx.rel_volume                (n, h + 1): the session's volume over the median of the name's own trailing
                                  `config.REL_VOLUME_SESSIONS` sessions
    ctx.sector                    int8 (n,): the statistical sector code, relabelled by the run's salt
    ctx.beta                      float64 (n,): beta to SPY over the 252 returns through t, `config.BETA_PLACES` decimals
    ctx.mkt                       a `Fields` of SPY: the same five arrays, shape (h + 1,)
    ctx.positions                 open lots: {id (the lot's), slot, weight, ret, held_sessions, at, tag}
    ctx.closed                    lots closed since the last call: {id, slot, net_ret, held_sessions, reason, tag}
    ctx.rejects                   why orders of the last target were refused (strings)
    ctx.cash, ctx.equity          the sleeve's free cash and equity, dollars, floats
    ctx.budget                    the sleeve's size the program's weights are of (dollars)
    ctx.weekday                   0 Monday .. 4 Friday, of session t
    ctx.session_of_month          1 for the month's first session ..
    ctx.sessions_left_in_month    0 on the month's last session ..
    ctx.last_session_of_week      whether t is the last session of its ISO week
    ctx.max_names                 the program's NEEDS max_names
    ctx.params                    the merged PARAMS

NO ticker, NO aid, NO date, NO year, NO month, NO event flag, NO price level, NO share count, NO dollar volume, NO
market value and no rank of one. Every array is read-only over an immutable buffer (E1's `_ro`); every figure is
rounded to `config.CTX_PLACES` decimals.

THE LEVEL IS REMOVED, NOT HIDDEN (E4-SPEC D7, kept under the pre-registration's fields: it only adds noise). A ratio
of two cent prices keeps the cent grid, and the grid gives the price back (a lattice search over 60 days of ratios
leaves one survivor; the ratio of two small price moves is a ratio of two small whole numbers of cents). So:
(1) THE DITHER, at the source of the grid: each ADJUSTED price p of (name, session s, field) becomes p + u, u uniform on
[-`config.DITHER_HALF`, +`config.DITHER_HALF`) dollars: u = (int.from_bytes(sha256(dither_key | b"|" | str(id) | b"|" |
str(session ordinal) | b"|" | field)[:8], "big") / 2**64 - 0.5) x 0.01, field one of b"o", b"h", b"l", b"c"; SPY's
arrays use the id -1. One (id, session, field) has one dither for the whole run. (2) the five fields are formed from
the DITHERED prices only (`ret` from two dithered closes, never from two grid prices) and rounded. A held lot's
`weight` (qty x the name's dithered RAW close at t / equity) and `ret` (that close over the lot's entry price moved by
a dither keyed b"lot" and the lot id, minus 1) are dithered the same way, to 4 decimals. Fills, marks, the residual
and every statistic read the undithered store: only what a program SEES carries the noise (at most half a cent a
price).

WHERE THIS DEPARTS FROM D7'S WORDS, AND WHY (the vendor's cents, found after the designs). D7 moves each bar's RAW
price by half a raw cent and carries it through the as-of factor, on the reading that adjustment=all is the raw price
times an exact factor. THE VENDOR ROUNDS adjustment=all TO THE CENT, so the grid a ratio of two history prices keeps
is the ADJUSTED price's own cent grid, and half a raw cent covers only part of an adjusted cent wherever a later
dividend or split has shrunk the adjusted price (after a 20-for-1 split the adjusted grid is twenty times coarser
than that dither): the search then finds the gaps. So each adjusted price is moved by half a cent OF ITS OWN grid:
uniform over exactly one cell, never less noise than D7's. And NO AS-OF PRODUCT IS FORMED: every field is a ratio, so
the factor of `league.equity.ctx.as_of` cancels, and with it its 4-decimal rounding, which differs from one decision
day to the next. A bar's fields are therefore THE SAME NUMBERS IN EVERY CTX OF A RUN: two views of one bar give a
program nothing to compare (the bound a known dither range puts on a level needs two views that differ). What is
left, stated: on the LIVE path a fetch made after the vendor restates a name's history shows its bars under another
vintage, each moved by the vendor's own cent rounding; a program that kept the earlier view across an ex-date could
read the scale of those moves. It exists only where nothing is hindsight (a live decision), never in a run on the
store (one vintage), and it is what the code review's "no search for a price level" is for.

THREE MORE GRIDS ARE CLOSED THE SAME WAY (each narrower than the registered contract, none wider):
- THE SHARE COUNT. A session's volume is a whole number of shares, and a ratio of two of them over one median is the
  same lattice: for a thinly traded name it gives the exact counts back, and an exact count dates a session and names
  the stock. So `rel_volume` reads the volume moved by a RELATIVE dither (x (1 + u_v), at most half a percent: the same
  hash under the field b"v") and put on the total-return basis first (x raw close / adjusted close: a split then
  leaves no step in it that would date the session). Its median is over the valid bars of the
  `config.REL_VOLUME_SESSIONS` sessions through that session; NaN when fewer than `REL_VOLUME_MIN_VALID` of them
  have a valid bar.
- THE SLEEVE'S DOLLARS. `equity` is the cash plus the open lots marked at their DITHERED closes, and `cash` and
  `equity` are rounded to the cent: with one lot held, an exact equity series is that lot's exact marks.
- A NAME WITH NO VALID BAR AT t is not a slot (it is outside U(t)); a held lot of it is marked at its last bar's
  dithered close (E1's `_factor_row`: the row its as-of factor would be read from).

`derive` IS THE ONE READER of eligibility and the characteristics (the pre-registration's 3.1-3.3): the ctx's rows,
the engine's cells, the placebos' cells and the House exit "ineligible" all read it, in the Gym and live alike. Its
arithmetic is `characteristics` and `cells`, on plain arrays: the study's conformance vector CH is held on them.

THE SUMS. A characteristic is a ratio of numpy reductions over a fixed (252, m) layout (numpy's own pairwise sum: the
same on the CI's two interpreters, which the built-in `sum` is not); nothing here calls the built-in `sum` on floats
or a BLAS product, whose rounding differs by machine.

Evidence module (in the xs identity). It imports three PRIVATE names of E1 and no other: `league.equity.ctx._encode`,
`_ro` and `_factor_row` (`test_xs_identity.py` pins them by name).
"""

from __future__ import annotations

import copy
import datetime as dt
import hashlib
import math
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import numpy as np

from ..equity.ctx import _encode, _factor_row, _ro, calendar_around
from ..equity.store import as_date, from_ordinal, nyse_sessions, ordinal
from . import config

#: The five scale-free fields of a slot and of the market, in the order `ctx_bytes` writes them.
FIELDS = ("ret", "oret", "iret", "range", "rel_volume")
#: `ctx_bytes`' prefix (E1's is its own: the two byte strings can never be confused).
CTX_PREFIX = b"xs-ctx-1;"
#: The id the market's (SPY's) dither is drawn under.
MARKET_ID = -1
#: The dither's fields: a bar's four prices (dollars, +-`config.DITHER_HALF`) and its volume (the same number read as
#: a share of the volume: +-half a percent), and the key a held lot's entry price is dithered under.
DITHER_FIELDS = (b"o", b"h", b"l", b"c", b"v")
DITHER_LOT = b"lot"
#: `rel_volume` needs this many valid bars among its `config.REL_VOLUME_SESSIONS` sessions.
REL_VOLUME_MIN_VALID = 32
#: A held lot's `weight` and `ret`, and a closed lot's `net_ret`, are rounded to this many decimals; dollars to cents.
LOT_PLACES = 4
USD_PLACES = 2
#: How many sessions' dithers one process keeps (a run's look-back and three years of sessions; about 25 MB).
_DITHER_ROWS = 1400


class Fields:
    """The five scale-free arrays of the market as a program sees them (read-only, oldest first, last = session t)."""

    __slots__ = FIELDS

    def __init__(self, **values: Any):
        for name in self.__slots__:
            object.__setattr__(self, name, values.get(name))

    def __repr__(self) -> str:
        return "Fields(" + ", ".join(self.__slots__) + ")"


class XsCtx:
    """What decide(ctx) receives (XS.md; the module docstring). Read its attributes; never assign them."""

    __slots__ = ("n", "ids", "ret", "oret", "iret", "range", "rel_volume", "sector", "beta", "mkt", "positions",
                 "closed", "rejects", "cash", "equity", "budget", "weekday", "session_of_month",
                 "sessions_left_in_month", "last_session_of_week", "max_names", "params")

    def __init__(self, **values: Any):
        for name in self.__slots__:
            object.__setattr__(self, name, values.get(name))

    def __repr__(self) -> str:
        return f"XsCtx({self.n} slots)"


@dataclass(frozen=True)
class Inputs:
    """Everything one decision's ctx is built from (pickled to the decider child live; built in-process in the Gym).
    NO aid, NO symbol.

    `days` int32: the ordinals of up to `config.DERIVE_SESSIONS` sessions through t, oldest first. `raw` float64 (len,
    m, 5) and `adj` (len, m, 4): the columns' bars (REF first, then members in ascending id). `elig0` bool (m,): the
    parent's part of eligibility at t (`store.PanelBars.elig0`'s row). `ref`: the leading REF columns (12). `ids` int32
    (m - ref,). `dither_key`, `sector_perm`: the run's. `history`, `max_names`: NEEDS'. `trading_days` int32 and
    `early` bool: the calendar around t (t's month and the next session's: `league.equity.ctx.calendar_around`).
    `positions`: rows {lid, col (the lot's column), qty, value, entry_value, held_sessions, at, tag} (the qty and the
    dollars never reach the program: `build` turns them into the dithered `weight` and `ret`). `closed`: rows {lid,
    col, net_ret, held_sessions, reason, tag}.
    `rejects`: strings. `cash`, `equity`, `budget`: dollars (floats). `params`: merged PARAMS."""

    days: np.ndarray
    raw: np.ndarray
    adj: np.ndarray
    elig0: np.ndarray
    ref: int
    ids: np.ndarray
    dither_key: bytes
    sector_perm: np.ndarray
    history: int
    max_names: int
    trading_days: np.ndarray
    early: np.ndarray
    positions: tuple[dict, ...]
    closed: tuple[dict, ...]
    rejects: tuple[str, ...]
    cash: float
    equity: float
    budget: float
    params: Mapping[str, Any]


@dataclass(frozen=True)
class Derived:
    """Eligibility and the characteristics at one decision close, per column (the pre-registration's 3.1-3.3).

    `elig` bool (m,): U(t): `elig0` AND a valid close at t and at t - 1 (raw close > 0 and raw volume > 0: the vendor's
    flat volume-0 bar of a halted name is no valid bar) AND the three characteristics exist. `beta` float64 (m,): cov
    with SPY over var of SPY on the name's valid returns of the 252 through t, at least `config.MIN_VALID`, else NaN.
    `mom` float64 (m,): c[t - 21] / c[t - 252] - 1, NaN unless both closes are valid. `sector` int8 (m,): the index in
    `config.FUNDS` of the fund whose MARKET-RESIDUAL returns (R - beta x R_SPY) correlate most with the name's, over
    the returns valid for both (at least `config.MIN_VALID`; a fund with fewer valid returns is skipped; ties: the
    first), -1 where none. `bg`, `mg` int8 (m,): the beta group and the momentum group inside the sector (`config
    .RUNGS[rung]` by the sector's eligible count; ranks ascend by (value, id)), -1 outside U. `cell` int32 (m,): the
    cell id (`config.CELL_SECTOR` x sector + `config.CELL_BETA` x bg + mg; `config.SMALL_CELL` for a name of a sector
    with fewer than `config.MIN_CELL` eligible names), -1 outside U. `rung`: the stratum's rung ("R0")."""

    elig: np.ndarray
    beta: np.ndarray
    mom: np.ndarray
    sector: np.ndarray
    bg: np.ndarray
    mg: np.ndarray
    cell: np.ndarray
    rung: str


# ----------------------------------------------------------------------------------- the characteristics (3.2, 3.3)
def _frozen(array: np.ndarray) -> np.ndarray:
    array = np.ascontiguousarray(array)
    array.setflags(write=False)
    return array


def _slope(r: np.ndarray, v: np.ndarray, rm: np.ndarray) -> np.ndarray:
    """The OLS slope of each column of `r` (w, k) on `rm` (w,) over that column's valid returns `v` (w, k): sum (r -
    mean r)(rm - mean rm) / sum (rm - mean rm)^2, both means over the column's own valid returns; NaN with fewer than
    `config.MIN_VALID` of them or a market that did not move."""
    count = v.sum(axis=0)
    enough = count >= config.MIN_VALID
    size = np.maximum(count, 1).astype(np.float64)
    market = np.where(v, rm[:, None], 0.0)
    mean_r = np.where(v, r, 0.0).sum(axis=0) / size
    mean_m = market.sum(axis=0) / size
    dr = np.where(v, r - mean_r[None, :], 0.0)
    dm = np.where(v, rm[:, None] - mean_m[None, :], 0.0)
    num, den = (dr * dm).sum(axis=0), (dm * dm).sum(axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(enough & (den > 0), num / np.where(den > 0, den, 1.0), np.nan)


def characteristics(closes: np.ndarray, market: np.ndarray,
                    funds: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """The pre-registration's 3.2 at a decision close d, on plain arrays: (beta, mom, sector) of each name.

    `closes` (L, k): the names' total-return closes of the sessions through d, oldest first, NaN where invalid;
    `market` (L,): SPY's; `funds` (L, f): the sector funds' in `config.FUNDS`' order (all NaN where a fund has no
    bar). The WINDOW is the last `config.WINDOW` returns (R(t) = c(t) / c(t - 1) - 1; a return is valid when both
    closes are, and the market's is). With fewer sessions than `config.DERIVE_SESSIONS` the returns there are still
    read (beta and the sector need `config.MIN_VALID` of them) and mom, which reads c(d - 252), is NaN.
    - beta = sum (R_i - mean R_i)(R_M - mean R_M) / sum (R_M - mean R_M)^2 over the name's valid returns;
    - mom = c(d - `config.MOM_SKIP`) / c(d - `config.MOM_BACK`) - 1, both closes valid;
    - sector = the fund, among those with at least `config.MIN_VALID` valid returns, whose market-residual returns e_s
      = R_s - beta_s R_M correlate most (Pearson, over the returns valid for both, at least `config.MIN_VALID`) with
      the name's e_i = R_i - beta_i R_M; ties go to the first fund; -1 where no fund qualifies or beta is undefined."""
    closes = np.asarray(closes, dtype=np.float64)
    market = np.asarray(market, dtype=np.float64).reshape(-1)
    funds = np.asarray(funds, dtype=np.float64)
    if closes.ndim != 2 or funds.ndim != 2 or closes.shape[0] != market.shape[0] or funds.shape[0] != market.shape[0]:
        raise ValueError("characteristics: closes (L, k), market (L,) and funds (L, f) share their sessions")
    length, k = closes.shape
    beta, mom = np.full(k, np.nan), np.full(k, np.nan)
    sector = np.full(k, -1, dtype=np.int8)
    if length >= config.DERIVE_SESSIONS:
        near, far = closes[length - 1 - config.MOM_SKIP], closes[length - 1 - config.MOM_BACK]
        with np.errstate(invalid="ignore", divide="ignore"):
            value = near / far - 1.0
        mom = np.where(np.isfinite(near) & np.isfinite(far) & (near > 0) & (far > 0) & np.isfinite(value), value, np.nan)
    if length < 2 or not k:
        return beta, mom, sector
    lo = max(0, length - config.DERIVE_SESSIONS)

    def returns(c: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        with np.errstate(invalid="ignore", divide="ignore"):
            r = c[lo + 1:] / c[lo:-1] - 1.0
        ok = np.isfinite(r) & (c[lo + 1:] > 0) & (c[lo:-1] > 0)
        return np.where(ok, r, 0.0), ok

    rm, vm = returns(market)
    r, v = returns(closes)
    v = v & vm[:, None]
    beta = _slope(r, v, rm)
    rs, vs = returns(funds)
    vs = vs & vm[:, None]
    beta_s = _slope(rs, vs, rm)
    known = np.isfinite(beta)
    e_i = np.where(v, r - np.where(known, beta, 0.0)[None, :] * rm[:, None], 0.0)
    best = np.full(k, -np.inf)
    for s in range(funds.shape[1]):
        if not math.isfinite(float(beta_s[s])):
            continue
        both = v & vs[:, s][:, None]
        count = both.sum(axis=0)
        size = np.maximum(count, 1).astype(np.float64)
        e_s = rs[:, s] - float(beta_s[s]) * rm
        mean_i = np.where(both, e_i, 0.0).sum(axis=0) / size
        mean_s = np.where(both, e_s[:, None], 0.0).sum(axis=0) / size
        di = np.where(both, e_i - mean_i[None, :], 0.0)
        ds = np.where(both, e_s[:, None] - mean_s[None, :], 0.0)
        den = (di * di).sum(axis=0) * (ds * ds).sum(axis=0)
        ok = known & (count >= config.MIN_VALID) & (den > 0)
        with np.errstate(invalid="ignore", divide="ignore"):
            rho = (di * ds).sum(axis=0) / np.sqrt(np.where(den > 0, den, 1.0))
        better = ok & (rho > best)                          # a tie keeps the first fund in the order
        best = np.where(better, rho, best)
        sector = np.where(better, np.int8(s), sector).astype(np.int8)
    return beta, mom, sector


def group_counts(n: int, rung: str) -> tuple[int, int] | None:
    """3.3: (beta groups, momentum groups) of a sector with `n` eligible names under `rung` (`config.RUNGS`), or None
    when it has fewer than `config.MIN_CELL` (its names go to the pooled cell)."""
    if rung not in config.RUNGS:
        raise ValueError(f"no rung {rung!r}; one of {', '.join(config.RUNGS)}")
    for least, groups in config.RUNGS[rung]:
        if n >= least:
            return groups
    return None


def cells(elig: np.ndarray, sector: np.ndarray, beta: np.ndarray, mom: np.ndarray, *,
          rung: str | None = None) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """The pre-registration's 3.3: (bg, mg, cell) of each column, -1 outside `elig`.

    Per sector of n eligible names: (nb, nm) = `group_counts(n, rung)`. Sort by (beta ascending, then column): rank q
    (0-based) gets beta group floor(q x nb / n). Within a beta group of size m sort by (mom ascending, then column):
    rank q gets momentum group floor(q x nm / m). cell = `config.CELL_SECTOR` x sector + `config.CELL_BETA` x beta
    group + momentum group. The sectors under `config.MIN_CELL` names share ONE cell, `config.SMALL_CELL` (bg and mg
    0). THE COLUMN ORDER STANDS FOR THE ASSET ID (ascending salted id on the House, the study's own order in its
    vectors)."""
    rung = config.RUNG if rung is None else rung
    elig = np.asarray(elig, dtype=bool)
    sector, beta, mom = np.asarray(sector), np.asarray(beta, dtype=np.float64), np.asarray(mom, dtype=np.float64)
    m = elig.shape[0]
    bg, mg = np.full(m, -1, dtype=np.int8), np.full(m, -1, dtype=np.int8)
    cell = np.full(m, -1, dtype=np.int32)
    for g in sorted({int(s) for s in sector[elig].tolist()}):
        names = np.flatnonzero(elig & (sector == g))
        n = int(names.shape[0])
        groups = group_counts(n, rung)
        if groups is None:
            bg[names], mg[names], cell[names] = 0, 0, config.SMALL_CELL
            continue
        nb, nm = groups
        by_beta = names[np.lexsort((names, beta[names]))]
        group = (np.arange(n) * nb) // n
        for b in range(nb):
            inside = by_beta[group == b]
            by_mom = inside[np.lexsort((inside, mom[inside]))]
            size = int(by_mom.shape[0])
            ranks = (np.arange(size) * nm) // max(size, 1)
            bg[by_mom], mg[by_mom] = b, ranks
            cell[by_mom] = config.CELL_SECTOR * g + config.CELL_BETA * b + ranks
    return bg, mg, cell


# -------------------------------------------------------------------------------------------------------- validity
def _valid(raw: np.ndarray, adj: np.ndarray) -> np.ndarray:
    """bool (L, m): a VALID CLOSE: a raw close above 0 with a raw volume above 0 (`store.valid_bars`' rule: the
    vendor's flat volume-0 bar is no bar) and a positive adjusted close."""
    close, volume, total = raw[:, :, 3], raw[:, :, 4], adj[:, :, 3]
    with np.errstate(invalid="ignore"):
        return (np.isfinite(close) & np.isfinite(volume) & np.isfinite(total) & (close > 0) & (volume > 0)
                & (total > 0))


def _arrays(inputs: Inputs) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    days = np.asarray(inputs.days, dtype=np.int32)
    raw = np.asarray(inputs.raw, dtype=np.float64)
    adj = np.asarray(inputs.adj, dtype=np.float64)
    if raw.ndim != 3 or adj.ndim != 3 or raw.shape[2] != 5 or adj.shape[2] != 4 or raw.shape[:2] != adj.shape[:2] \
            or raw.shape[0] != days.shape[0]:
        raise ValueError("a decision's raw (len, m, 5) and adj (len, m, 4) share their sessions and columns")
    ref = int(inputs.ref)
    if ref != len(config.REF) or raw.shape[1] < ref or np.asarray(inputs.ids).shape != (raw.shape[1] - ref,) or \
            np.asarray(inputs.elig0).shape != (raw.shape[1],):
        raise ValueError("a decision's columns are the REF columns, then one id and one elig0 flag a member column")
    if days.shape[0] > config.DERIVE_SESSIONS:
        raise ValueError(f"a decision reads at most {config.DERIVE_SESSIONS} sessions")
    return days, raw, adj


def derive(inputs: Inputs, *, rung: str | None = None) -> Derived:
    """The eligible set and the characteristics at t (`Derived`), from the decision's own arrays and nothing stored:
    the Gym and live cannot disagree. `rung` None is `config.RUNG`."""
    rung = config.RUNG if rung is None else rung
    if rung not in config.RUNGS:
        raise ValueError(f"no rung {rung!r}; one of {', '.join(config.RUNGS)}")
    days, raw, adj = _arrays(inputs)
    length, m = raw.shape[:2]
    ref = int(inputs.ref)
    elig = np.zeros(m, dtype=bool)
    beta, mom = np.full(m, np.nan), np.full(m, np.nan)
    sector = np.full(m, -1, dtype=np.int8)
    if length >= 2:
        valid = _valid(raw, adj)
        closes = np.where(valid, adj[:, :, 3], np.nan)          # total-return closes: one fetch's series a column
        funds = closes[:, list(config.FUND_COLUMNS)]
        beta, mom, found = characteristics(closes, closes[:, config.MARKET_COLUMN], funds)
        sector[ref:] = found[ref:]
        elig = (np.asarray(inputs.elig0, dtype=bool) & valid[-1] & valid[-2] & np.isfinite(beta) & np.isfinite(mom)
                & (sector >= 0))
        elig[:ref] = False
    bg, mg, cell = cells(elig, sector, beta, mom, rung=rung)
    return Derived(elig=_frozen(elig), beta=_frozen(beta), mom=_frozen(mom), sector=_frozen(sector), bg=_frozen(bg),
                   mg=_frozen(mg), cell=_frozen(cell), rung=rung)


def ineligible(inputs: Inputs, derived: Derived) -> list[int]:
    """THE HOUSE EXIT "ineligible" (the pre-registration's C6): the lids of the open lots whose column is not in U(t).
    Read at EVERY close, called or not, by the engine and by the child alike; the lot is sold at the next open."""
    elig = np.asarray(derived.elig, dtype=bool)
    out = []
    for row in inputs.positions:
        col = int(row["col"])
        if not (0 <= col < elig.shape[0] and bool(elig[col])):
            out.append(int(row["lid"]))
    return out


# -------------------------------------------------------------------------------------------------------- the dither
def dither(key: bytes, ident: int, session: int, field: bytes) -> float:
    """D7's u for one (id, session ordinal, field): (int.from_bytes(sha256(key | b"|" | str(id) | b"|" | str(session) |
    b"|" | field)[:8], "big") / 2**64 - 0.5) x 0.01: uniform on [-`config.DITHER_HALF`, +`config.DITHER_HALF`). Dollars
    for a price field (added to the bar's adjusted price); for the volume's (b"v") a share of the volume."""
    digest = hashlib.sha256(bytes(key) + b"|" + str(int(ident)).encode() + b"|" + str(int(session)).encode() + b"|"
                            + bytes(field)).digest()
    return (int.from_bytes(digest[:8], "big") / 2.0 ** 64 - 0.5) * (2.0 * config.DITHER_HALF)


def lot_dither(key: bytes, lid: int) -> float:
    """The dither of a held lot's entry price: the same expression under the field `DITHER_LOT` and the lot id."""
    digest = hashlib.sha256(bytes(key) + b"|" + DITHER_LOT + b"|" + str(int(lid)).encode()).digest()
    return (int.from_bytes(digest[:8], "big") / 2.0 ** 64 - 0.5) * (2.0 * config.DITHER_HALF)


#: (dither key, the ids' bytes) -> {session ordinal: float64 (len(ids), 5)}: one run's dithers, each drawn once.
_DITHERS: "OrderedDict[tuple[bytes, bytes], OrderedDict[int, np.ndarray]]" = OrderedDict()
_DITHER_RUNS = 4


def _dithers(key: bytes, idents: np.ndarray, sessions: np.ndarray) -> np.ndarray:
    """float64 (len(sessions), len(idents), 5): `dither` for every (session, id, field of `DITHER_FIELDS`). One (id,
    session, field) has one dither for the whole run, so a process keeps what it drew (`_DITHERS`): a run's next
    decision draws its new sessions only."""
    idents = np.ascontiguousarray(idents, dtype=np.int64)
    name = (bytes(key), idents.tobytes())
    rows = _DITHERS.get(name)
    if rows is None:
        rows = _DITHERS[name] = OrderedDict()
        while len(_DITHERS) > _DITHER_RUNS:
            _DITHERS.popitem(last=False)
    else:
        _DITHERS.move_to_end(name)
    out = np.empty((sessions.shape[0], idents.shape[0], len(DITHER_FIELDS)))
    prefixes = None
    scale = 2.0 * config.DITHER_HALF
    for at, session in enumerate(int(s) for s in sessions.tolist()):
        row = rows.get(session)
        if row is None:
            if prefixes is None:
                prefixes = [hashlib.sha256(bytes(key) + b"|" + str(i).encode() + b"|") for i in idents.tolist()]
            tails = [str(session).encode() + b"|" + field for field in DITHER_FIELDS]
            row = np.empty((idents.shape[0], len(DITHER_FIELDS)))
            for i, prefix in enumerate(prefixes):
                for f, tail in enumerate(tails):
                    digest = prefix.copy()
                    digest.update(tail)
                    row[i, f] = (int.from_bytes(digest.digest()[:8], "big") / 2.0 ** 64 - 0.5) * scale
            row.setflags(write=False)
            rows[session] = row
            while len(rows) > _DITHER_ROWS:
                rows.popitem(last=False)
        out[at] = row
    return out


# ------------------------------------------------------------------------------------------------ the volume field
#: (the window's own bytes' digest) -> float64 (k,): a session's `rel_volume` row, kept by CONTENT: the digest names
#: the 63 sessions' dithered volumes of every column, so a kept row is the row a fresh computation would give.
_REL: "OrderedDict[bytes, np.ndarray]" = OrderedDict()


def _rel_volume(basis: np.ndarray, first: int) -> np.ndarray:
    """float64 (L, k): each session's volume over the median of the column's valid volumes on the
    `config.REL_VOLUME_SESSIONS` sessions through it (those the inputs hold), for the rows from `first` on (NaN
    before; NaN with fewer than `REL_VOLUME_MIN_VALID` valid bars among them, so a session the inputs do not hold and
    a session without a bar read alike). `basis` (L, k): the dithered volumes, NaN where no valid bar. A row is a
    pure function of its window, and is kept by the window's digest (`_REL`): a run's next decision computes its new
    sessions only."""
    length, k = basis.shape
    span = config.REL_VOLUME_SESSIONS
    out = np.full((length, k), np.nan)
    first = max(0, first)
    if first >= length or not k:
        return out
    block = np.ascontiguousarray(basis)
    low = max(0, first - span + 1)
    marks = [hashlib.blake2b(block[row].tobytes(), digest_size=16).digest() for row in range(low, length)]
    blank = hashlib.blake2b(np.full(k, np.nan).tobytes(), digest_size=16).digest()
    for row in range(first, length):
        start = max(0, row - span + 1)
        # a session the inputs do not hold is a session without a bar: the same digest, the same row
        held = [blank] * (span - (row - start + 1)) + marks[start - low:row - low + 1]
        name = hashlib.blake2b(b"".join(held), digest_size=16).digest()
        found = _REL.get(name)
        if found is None or found.shape != (k,):
            window = block[start:row + 1]
            known = np.isfinite(window)
            count = known.sum(axis=0)
            ordered = np.sort(np.where(known, window, np.inf), axis=0)
            safe = np.maximum(count, 1)
            lower = np.take_along_axis(ordered, ((safe - 1) // 2)[None, :], axis=0)[0]
            upper = np.take_along_axis(ordered, (safe // 2)[None, :], axis=0)[0]
            with np.errstate(invalid="ignore", divide="ignore"):
                median = 0.5 * (lower + upper)
                found = np.where((count >= REL_VOLUME_MIN_VALID) & np.isfinite(median) & (median > 0),
                                 block[row] / median, np.nan)
            found.setflags(write=False)
            _REL[name] = found
            while len(_REL) > _DITHER_ROWS:
                _REL.popitem(last=False)
        else:
            _REL.move_to_end(name)
        out[row] = found
    return out


# ------------------------------------------------------------------------------------------------------ the ctx
def _fields(adj: np.ndarray, valid: np.ndarray, u: np.ndarray, rel: np.ndarray, history: int) -> dict[str, np.ndarray]:
    """The five scale-free fields of columns (L, k): `adj` (L, k, 4) adjusted o h l c, `valid` (L, k), `u` (L, k, 5)
    their dithers, `rel` (L, k) their `rel_volume`; each (k, history + 1), oldest first, the last session t,
    NaN-padded on the left when the inputs hold fewer sessions. Formed from the DITHERED prices only (each adjusted
    price moved by its own u; a price that is not above zero after it reads as no price), rounded to
    `config.CTX_PLACES` decimals."""
    length, k = valid.shape
    with np.errstate(invalid="ignore", divide="ignore"):
        moved = adj + u[:, :, :4]
        prices = np.where(valid[:, :, None] & (adj > 0) & (moved > 0), moved, np.nan)
        o, h, low, c = prices[:, :, 0], prices[:, :, 1], prices[:, :, 2], prices[:, :, 3]
        ret, oret = np.full((length, k), np.nan), np.full((length, k), np.nan)
        if length > 1:
            ret[1:] = c[1:] / c[:-1] - 1.0
            oret[1:] = o[1:] / c[:-1] - 1.0
        iret = c / o - 1.0
        spread = (h - low) / c
    out = {}
    for name, values in zip(FIELDS, (ret, oret, iret, spread, rel)):
        values = np.where(np.isfinite(values), values, np.nan)
        tail = values[max(0, length - (history + 1)):]
        if tail.shape[0] < history + 1:
            tail = np.concatenate([np.full((history + 1 - tail.shape[0], k), np.nan), tail], axis=0)
        out[name] = np.round(tail.T, config.CTX_PLACES)
    return out


def _calendar(inputs: Inputs, t: dt.date) -> tuple[int, int, bool]:
    """(session_of_month, sessions_left_in_month, last_session_of_week) of t, from the decision's own calendar."""
    trading = [from_ordinal(int(d)) for d in np.asarray(inputs.trading_days, dtype=np.int32).tolist()]
    if t not in trading:
        raise ValueError("session t is not in the ctx's calendar")
    month = [d for d in trading if d.year == t.year and d.month == t.month]
    later = [d for d in trading if d > t]
    if not later:
        raise ValueError("the ctx's calendar does not hold the session after t")
    last_of_week = later[0].isocalendar()[:2] != t.isocalendar()[:2]
    return len([d for d in month if d <= t]), len([d for d in month if d > t]), bool(last_of_week)


def build(inputs: Inputs, derived: Derived | None = None) -> XsCtx:
    """The ctx of the module docstring, the dither included. Deterministic: the same `Inputs` give the same bytes.
    `derived`: the decision's own `derive(inputs)` when the caller already holds it (the engine does); None: computed."""
    days, raw, adj = _arrays(inputs)
    length, m = raw.shape[:2]
    if not length:
        raise ValueError("a ctx needs session t")
    history = int(inputs.history)
    if not config.MIN_HISTORY <= history <= config.MAX_HISTORY:
        raise ValueError(f"history is {config.MIN_HISTORY} to {config.MAX_HISTORY} sessions")
    ref, market = int(inputs.ref), config.MARKET_COLUMN
    ids = np.asarray(inputs.ids, dtype=np.int32)
    if derived is None:
        derived = derive(inputs)
    elig = np.asarray(derived.elig, dtype=bool)
    if elig.shape != (m,):
        raise ValueError("the derived arrays are another decision's")
    t = from_ordinal(int(days[-1]))
    key = bytes(inputs.dither_key)
    valid = _valid(raw, adj)
    market_row = _factor_row(raw[:, market], adj[:, market])
    if market_row != length - 1 or not bool(valid[-1, market]):
        raise ValueError(f"the market ({config.REF[market]}) has no valid bar at session t")
    # SPY and the member columns only: no other REF column reaches a program.
    shown = np.array([market, *range(ref, m)], dtype=np.int64)
    idents = np.array([MARKET_ID, *ids.tolist()], dtype=np.int64)
    shown_raw, shown_adj, shown_valid = raw[:, shown], adj[:, shown], valid[:, shown]
    u = _dithers(key, idents, days)
    with np.errstate(invalid="ignore", divide="ignore"):
        # the volume on the total-return basis (a split leaves no step in it), then its own relative dither
        basis = np.where(shown_valid, shown_raw[:, :, 4] * shown_raw[:, :, 3] / shown_adj[:, :, 3]
                         * (1.0 + u[:, :, 4]), np.nan)
    rel = _rel_volume(basis, max(0, length - (history + 1)))
    slots = np.flatnonzero(elig)
    keep = np.array([0, *(slots - ref + 1).tolist()], dtype=np.int64)        # into `shown`: the market, then U(t)
    fields = _fields(shown_adj[:, keep], shown_valid[:, keep], u[:, keep], rel[:, keep], history)

    def dithered_close(col: int) -> float | None:
        """The column's dithered RAW close at its last bar (session t's when it has one): E1's `_factor_row`."""
        row = _factor_row(raw[:, col], adj[:, col])
        if row is None:
            return None
        return float(raw[row, col, 3]) + float(u[row, col - ref + 1, 3])

    cash = float(inputs.cash)
    lots, marked, readable = [], cash, True
    for row in inputs.positions:
        col, qty, lid = int(row["col"]), float(row["qty"]), int(row["lid"])
        if not ref <= col < m:
            raise ValueError("a held lot's column is a member column of the decision")
        close = dithered_close(col)
        if close is None or not close > 0 or not qty > 0:
            readable = False
            value, ret = float(row["value"]), None
        else:
            value = qty * close
            basis_price = float(row["entry_value"]) / qty + lot_dither(key, lid)
            ret = round(close / basis_price - 1.0, LOT_PLACES) if basis_price > 0 else None
        marked += value
        lots.append((value, {"id": lid, "slot": int(ids[col - ref]), "weight": None, "ret": ret,
                             "held_sessions": int(row["held_sessions"]), "at": str(row["at"]),
                             "tag": str(row.get("tag") or "")}))
    equity = round(marked if readable else float(inputs.equity), USD_PLACES)
    positions = []
    for value, lot in lots:
        lot["weight"] = round(value / equity, LOT_PLACES) if equity > 0 else None
        positions.append(lot)
    closed = []
    for row in inputs.closed:
        col = int(row["col"])
        if not ref <= col < m:
            raise ValueError("a closed lot's column is a member column of the decision")
        net = row.get("net_ret")
        closed.append({"id": int(row["lid"]), "slot": int(ids[col - ref]),
                       "net_ret": None if net is None else round(float(net), LOT_PLACES),
                       "held_sessions": int(row["held_sessions"]), "reason": str(row["reason"]),
                       "tag": str(row.get("tag") or "")})
    session_of_month, left, last_of_week = _calendar(inputs, t)
    perm = np.asarray(inputs.sector_perm, dtype=np.int8)
    if perm.shape != (len(config.FUNDS),) or sorted(perm.tolist()) != list(range(len(config.FUNDS))):
        raise ValueError("the sector relabelling is a permutation of the sector codes")
    return XsCtx(
        n=int(slots.shape[0]), ids=_ro(ids[slots - ref].astype(np.int32)),
        **{name: _ro(np.ascontiguousarray(fields[name][1:])) for name in FIELDS},
        sector=_ro(perm[np.asarray(derived.sector, dtype=np.int64)[slots]].astype(np.int8)),
        beta=_ro(np.round(np.asarray(derived.beta, dtype=np.float64)[slots], config.BETA_PLACES)),
        mkt=Fields(**{name: _ro(np.ascontiguousarray(fields[name][0])) for name in FIELDS}),
        positions=positions, closed=closed, rejects=[str(r) for r in inputs.rejects],
        cash=round(cash, USD_PLACES), equity=equity, budget=round(float(inputs.budget), USD_PLACES),
        weekday=int(t.weekday()), session_of_month=session_of_month, sessions_left_in_month=left,
        last_session_of_week=last_of_week, max_names=int(inputs.max_names),
        params=copy.deepcopy(dict(inputs.params)))


# ------------------------------------------------------------------------------------------------- building inputs
def _rows(rows: Sequence[Mapping[str, Any]]) -> tuple[dict, ...]:
    return tuple(dict(row) for row in rows)


def _inputs(days: np.ndarray, raw: np.ndarray, adj: np.ndarray, *, elig0: np.ndarray, ids: np.ndarray,
            dither_key: bytes, sector_perm: np.ndarray, needs: Any, positions: Sequence[dict], closed: Sequence[dict],
            rejects: Sequence[str], cash: float, equity: float, budget: float, params: Mapping[str, Any]) -> Inputs:
    trading, early = calendar_around(from_ordinal(int(days[-1])))
    return Inputs(days=days, raw=raw, adj=adj, elig0=elig0, ref=len(config.REF), ids=ids,
                  dither_key=bytes(dither_key), sector_perm=sector_perm, history=int(needs.history),
                  max_names=int(needs.max_names), trading_days=trading, early=early, positions=_rows(positions),
                  closed=_rows(closed), rejects=tuple(str(r) for r in rejects), cash=float(cash),
                  equity=float(equity), budget=float(budget), params=copy.deepcopy(dict(params)))


def inputs_from_panel(bars: Any, t: int, *, needs: Any, positions: Sequence[dict] = (), closed: Sequence[dict] = (),
                      rejects: Sequence[str] = (), cash: float, equity: float, budget: float,
                      params: Mapping[str, Any]) -> Inputs:
    """The Gym's `Inputs` for the decision at the close of session index `t` of a `store.PanelBars`: never a row after
    t (the membership look-ahead of `elig0` is the store's own, baked in by the parent)."""
    t = int(t)
    if not 0 <= t < bars.n:
        raise ValueError(f"session index {t} is outside the slice")
    lo = max(0, t + 1 - config.DERIVE_SESSIONS)
    return _inputs(np.asarray(bars.days[lo:t + 1], dtype=np.int32), np.asarray(bars.raw[lo:t + 1], dtype=np.float64),
                   np.asarray(bars.adj[lo:t + 1], dtype=np.float64), elig0=np.asarray(bars.elig0[t], dtype=bool),
                   ids=np.asarray(bars.ids, dtype=np.int32), dither_key=bars.dither_key,
                   sector_perm=np.asarray(bars.sector_perm, dtype=np.int8), needs=needs, positions=positions,
                   closed=closed, rejects=rejects, cash=cash, equity=equity, budget=budget, params=params)


def inputs_from_arrays(days: np.ndarray, raw: np.ndarray, adj: np.ndarray, *, day: dt.date, elig0: np.ndarray,
                       ids: np.ndarray, dither_key: bytes, sector_perm: np.ndarray, needs: Any,
                       positions: Sequence[dict] = (), closed: Sequence[dict] = (), rejects: Sequence[str] = (),
                       cash: float, equity: float, budget: float, params: Mapping[str, Any]) -> Inputs:
    """The live `Inputs` for the decision of `day`: the parent's chunked fetch already turned into arrays in column
    order. ValueError when SPY has no bar of `day` or the two series disagree on their sessions."""
    t = as_date(day)
    days = np.asarray(days, dtype=np.int32)
    raw, adj = np.asarray(raw, dtype=np.float64), np.asarray(adj, dtype=np.float64)
    if days.ndim != 1 or not days.size or raw.shape[:1] != days.shape or adj.shape[:1] != days.shape or \
            raw.ndim != 3 or adj.ndim != 3 or raw.shape[1] != adj.shape[1] or raw.shape[2] != 5 or adj.shape[2] != 4:
        raise ValueError("a fetch's raw (len, m, 5) and adj (len, m, 4) share their sessions and columns")
    if int(days[-1]) != ordinal(t) or bool(np.any(np.diff(days) <= 0)):
        raise ValueError(f"the fetch's sessions ascend and end on {t}")
    with np.errstate(invalid="ignore"):
        if not np.array_equal(np.isfinite(raw[:, :, 3]), np.isfinite(adj[:, :, 3])):
            raise ValueError("the raw and all bars disagree on their sessions")
        market = raw[-1, config.MARKET_COLUMN] if raw.shape[1] > config.MARKET_COLUMN else np.full(5, np.nan)
        if not (np.isfinite(market[3]) and market[3] > 0 and np.isfinite(market[4]) and market[4] > 0):
            raise ValueError(f"{config.REF[config.MARKET_COLUMN]} has no bar for session {t}")
    lo = max(0, days.shape[0] - config.DERIVE_SESSIONS)
    return _inputs(days[lo:], raw[lo:], adj[lo:], elig0=np.asarray(elig0, dtype=bool),
                   ids=np.asarray(ids, dtype=np.int32), dither_key=dither_key,
                   sector_perm=np.asarray(sector_perm, dtype=np.int8), needs=needs, positions=positions,
                   closed=closed, rejects=rejects, cash=cash, equity=equity, budget=budget, params=params)


def fetch_sessions(day: dt.date) -> list[dt.date]:
    """The sessions a live decision of `day` reads: the last `config.DERIVE_SESSIONS` sessions through `day` of the
    panel's own calendar (`store.nyse_sessions`, the reserve left out and never crossed: the look-back stays inside
    `day`'s span of `config.SPANS`, as a slice's does). ValueError when `day` is no session of a span."""
    t = as_date(day)
    span = [(a, b) for _, a, b in config.SPANS if a <= t and (b is None or t <= b)]
    if not span:
        raise ValueError(f"{t} is outside the panel's spans")
    # 2 x the sessions + 14 calendar days always hold them
    since = max(t - dt.timedelta(days=2 * config.DERIVE_SESSIONS + 14), span[0][0])
    sessions = [d for d, _ in nyse_sessions(since, t)]
    if not sessions or sessions[-1] != t:
        raise ValueError(f"{t} is not a session")
    return sessions[-config.DERIVE_SESSIONS:]


def _row_day(row: Mapping[str, Any]) -> dt.date:
    stamp = row.get("t")
    if isinstance(stamp, str) and len(stamp) > 10:
        return as_date(dt.datetime.fromisoformat(stamp.replace("Z", "+00:00")))
    return as_date(stamp)


def rows_to_arrays(raw_rows: Mapping[str, Sequence[Mapping[str, Any]]],
                   all_rows: Mapping[str, Sequence[Mapping[str, Any]]], *, day: dt.date,
                   columns: Sequence[str]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(days, raw (n, len(columns), 5), adj (n, len(columns), 4)) of the venue's 1Day rows {t, o, h, l, c, v} per symbol
    (one chunk at a time), for the sessions through `day` (`fetch_sessions`); NaN where a symbol has no bar. Parent
    side only: `columns` are symbols. A row after `day` is dropped (the fetch may run past the decision's session);
    ValueError for a symbol whose rows name a day twice or a day that is no session."""
    t = as_date(day)
    sessions = fetch_sessions(t)
    index = {d: i for i, d in enumerate(sessions)}
    raw = np.full((len(sessions), len(columns), 5), np.nan)
    adj = np.full((len(sessions), len(columns), 4), np.nan)
    for col, symbol in enumerate(columns):
        for which, rows, target, keys in (("raw", raw_rows.get(symbol), raw, ("o", "h", "l", "c", "v")),
                                          ("all", all_rows.get(symbol), adj, ("o", "h", "l", "c"))):
            seen: set[dt.date] = set()
            for row in rows or ():
                at = _row_day(row)
                if at > t:
                    continue
                if at in seen:
                    raise ValueError(f"{symbol}'s {which} bars name {at} twice")
                seen.add(at)
                i = index.get(at)
                if i is None:
                    if at >= sessions[0]:
                        raise ValueError(f"{symbol} has a bar on {at}, not a session")
                    continue
                target[i, col, :] = [float(row[k]) for k in keys]
    return np.array([ordinal(d) for d in sessions], dtype=np.int32), raw, adj


def inputs_from_fetch(raw_rows: Mapping[str, Sequence[Mapping[str, Any]]],
                      all_rows: Mapping[str, Sequence[Mapping[str, Any]]], *, day: dt.date, columns: Sequence[str],
                      **common: Any) -> Inputs:
    """`rows_to_arrays` then `inputs_from_arrays` (`common`: its keywords): the I6 helper's entry, and small
    fixtures'."""
    days, raw, adj = rows_to_arrays(raw_rows, all_rows, day=day, columns=columns)
    return inputs_from_arrays(days, raw, adj, day=as_date(day), **common)


def ctx_bytes(ctx: XsCtx) -> bytes:
    """The ctx as bytes, for the I6 comparison and a decision's `ctx_sha`: `CTX_PREFIX`, then for each name of
    `XsCtx.__slots__` E1's `_encode` of the name and of the slot's value, a `Fields` first turned into a dict of its
    five arrays."""
    out: list[bytes] = [CTX_PREFIX]
    for name in XsCtx.__slots__:
        value = getattr(ctx, name)
        if isinstance(value, Fields):
            value = {field: getattr(value, field) for field in Fields.__slots__}
        _encode(name, out)
        _encode(value, out)
    return b"".join(out)


__all__ = ["FIELDS", "CTX_PREFIX", "MARKET_ID", "DITHER_FIELDS", "DITHER_LOT", "REL_VOLUME_MIN_VALID",
           "LOT_PLACES", "USD_PLACES", "Fields", "XsCtx", "Inputs", "Derived", "characteristics", "group_counts",
           "cells", "derive", "ineligible", "dither", "lot_dither", "build", "inputs_from_panel",
           "inputs_from_arrays", "fetch_sessions", "rows_to_arrays", "inputs_from_fetch", "ctx_bytes"]
