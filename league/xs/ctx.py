"""What a panel program sees at the decision close of session t: built by one function, in the Gym and live (I6).

Owner: package C. STEP 0 STUB: `XsCtx`, `Fields`, `Inputs` and `Derived` are the contract; every function raises
NotImplementedError until C lands.

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
leaves one survivor). So, in this order: (1) the as-of prices of each bar (`league.equity.ctx.as_of`, the factor read
from session t's close; a name with no bar at t takes its last bar's, E1's `_factor_row`). (2) THE DITHER, at the
source of the grid: each as-of price p of (name, session s, field) becomes p x (1 + u / raw), raw = that bar's RAW
price of the field, u uniform on [-`config.DITHER_HALF`, +`config.DITHER_HALF`) dollars: u = (int.from_bytes(sha256(
dither_key | b"|" | str(id) | b"|" | str(session ordinal) | b"|" | field)[:8], "big") / 2**64 - 0.5) x 0.01, field one
of b"o", b"h", b"l", b"c"; SPY's arrays use the id -1. One (id, session, field) has one dither for the whole run and it
scales with every later restatement, so two days' views of one bar stay proportional. (3) the five fields are formed
from the DITHERED prices only (`ret` from two dithered closes, never from two grid prices) and rounded. A held lot's
`weight` (qty x the name's dithered close at t / equity) and `ret` (that close over the lot's entry price moved by a
dither keyed b"lot" and the lot id, minus 1) are dithered the same way, to 4 decimals. Fills, marks, the residual and
every statistic read the undithered store: only what a program SEES carries the noise (at most half a cent a price).

`derive` IS THE ONE READER of eligibility and the characteristics (the pre-registration's 3.1-3.3): the ctx's rows,
the engine's cells, the placebos' cells and the House exit "ineligible" all read it, in the Gym and live alike.

Evidence module (in the xs identity). It imports three PRIVATE names of E1 and no other: `league.equity.ctx._encode`,
`_ro` and `_factor_row` (`test_xs_identity.py` pins them by name).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import numpy as np

#: The five scale-free fields of a slot and of the market, in the order `ctx_bytes` writes them.
FIELDS = ("ret", "oret", "iret", "range", "rel_volume")
#: `ctx_bytes`' prefix (E1's is its own: the two byte strings can never be confused).
CTX_PREFIX = b"xs-ctx-1;"
#: The id the market's (SPY's) dither is drawn under.
MARKET_ID = -1

_STUB = "league.xs.ctx is a Step 0 stub: package C builds it (league/xs/E4_INTERFACES.md)"


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


def derive(inputs: Inputs, *, rung: str | None = None) -> Derived:
    """The eligible set and the characteristics at t (`Derived`), from the decision's own arrays and nothing stored:
    the Gym and live cannot disagree. `rung` None is `config.RUNG`."""
    raise NotImplementedError(_STUB)


def ineligible(inputs: Inputs, derived: Derived) -> list[int]:
    """THE HOUSE EXIT "ineligible" (the pre-registration's C6): the lids of the open lots whose column is not in U(t).
    Read at EVERY close, called or not, by the engine and by the child alike; the lot is sold at the next open."""
    raise NotImplementedError(_STUB)


def build(inputs: Inputs) -> XsCtx:
    """The ctx of the module docstring, the dither included. Deterministic: the same `Inputs` give the same bytes."""
    raise NotImplementedError(_STUB)


def inputs_from_panel(bars: Any, t: int, *, needs: Any, positions: Sequence[dict] = (), closed: Sequence[dict] = (),
                      rejects: Sequence[str] = (), cash: float, equity: float, budget: float,
                      params: Mapping[str, Any]) -> Inputs:
    """The Gym's `Inputs` for the decision at the close of session index `t` of a `store.PanelBars`: never a row after
    t (the membership look-ahead of `elig0` is the store's own, baked in by the parent)."""
    raise NotImplementedError(_STUB)


def inputs_from_arrays(days: np.ndarray, raw: np.ndarray, adj: np.ndarray, *, day: dt.date, elig0: np.ndarray,
                       ids: np.ndarray, dither_key: bytes, sector_perm: np.ndarray, needs: Any,
                       positions: Sequence[dict] = (), closed: Sequence[dict] = (), rejects: Sequence[str] = (),
                       cash: float, equity: float, budget: float, params: Mapping[str, Any]) -> Inputs:
    """The live `Inputs` for the decision of `day`: the parent's chunked fetch already turned into arrays in column
    order. ValueError when SPY has no bar of `day` or the two series disagree on their sessions."""
    raise NotImplementedError(_STUB)


def rows_to_arrays(raw_rows: Mapping[str, Sequence[Mapping[str, Any]]],
                   all_rows: Mapping[str, Sequence[Mapping[str, Any]]], *, day: dt.date,
                   columns: Sequence[str]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(days, raw (n, len(columns), 5), adj (n, len(columns), 4)) of the venue's 1Day rows {t, o, h, l, c, v} per symbol
    (one chunk at a time), for the sessions through `day`; NaN where a symbol has no bar. Parent side only: `columns`
    are symbols."""
    raise NotImplementedError(_STUB)


def inputs_from_fetch(raw_rows: Mapping[str, Sequence[Mapping[str, Any]]],
                      all_rows: Mapping[str, Sequence[Mapping[str, Any]]], *, day: dt.date, columns: Sequence[str],
                      **common: Any) -> Inputs:
    """`rows_to_arrays` then `inputs_from_arrays` (`common`: its keywords): the I6 helper's entry, and small
    fixtures'."""
    raise NotImplementedError(_STUB)


def ctx_bytes(ctx: XsCtx) -> bytes:
    """The ctx as bytes, for the I6 comparison and a decision's `ctx_sha`: `CTX_PREFIX`, then for each name of
    `XsCtx.__slots__` E1's `_encode` of the name and of the slot's value, a `Fields` first turned into a dict of its
    five arrays."""
    raise NotImplementedError(_STUB)


__all__ = ["FIELDS", "CTX_PREFIX", "MARKET_ID", "Fields", "XsCtx", "Inputs", "Derived", "derive", "ineligible",
           "build", "inputs_from_panel", "inputs_from_arrays", "rows_to_arrays", "inputs_from_fetch", "ctx_bytes"]
