"""The residual, the stress residual, the universe excess and the matched placebos: from the holdings log and the bars.

Owner: package D.

THIS MODULE IS THE PINNED PRE-REGISTRATION'S SECTION 3, to the letter (XSCREEN-1 revision 2; where E4-SPEC D13 and D14
differ, the pre-registration wins). THE STUDY'S CONFORMANCE VECTORS ARE COMMITTED (synthetic inputs, no market data):
league/tests/fixtures/xs1_conformance.json (the file the study's own vector builder writes at the bar of the receipt
the House runs, byte for byte: the captain's A23 moved that bar above the registered one, and every vector was
computed again there) and
league/tests/fixtures/xs1_conformance_inputs.npz (for V1-V6: the prices O and C, the eligible set U, entry validity,
every lot of the holdings log with its cell, members and each member's leaving session, and the study's plain
reference's series r, B, x, x15, s, f, w, exits, invested, u, the 999 placebo t's on the holdout and the counterpart
positions of draws 0 and 998; the file's "manifest" says which vector reads which world). `test_xs_placebo
.TheStudyVectors` reproduces them: every integer exactly (the vectors' lot, member and counterpart-position counts
and sums, exits, invested), x, x15 and u to 1e-12, the placebo t's to 1e-9, and the hand vector H. THE COLUMN ORDER
STANDS FOR THE STUDY'S ASSET ID: a fixture hands its names 0..23 as columns in that order, so "ascending asset id" is
ascending column, as it is ascending salted id on the House. Neither implementation is rewritten to fit the other
after the receipt exists. One thing the reference does that a reader may not expect, and the vectors hold: on a
session where a lot's OWN leg is invalid, r itself carries the cell's mean (so x is 0 there), so r is not the same
number under one cell (u) as under the lot's cell.

WHAT IS READ: `bars` (a `store.PanelBars`: its `adj` opens and closes are the total-return prices, its `raw` closes
and volumes say which are valid, its `hs` is not read: a lot carries its own) and the run's `engine.Log` (every lot's
row, and U(t) at every close the engine read: each decision row's `derived.elig`). Nothing else: no store, no ctx, no
program. A PRICE IS VALID when its raw price is above zero, its session's raw volume is above zero (the vendor's flat
volume-0 bar of a halted name is no valid bar) and its adjusted price is above zero; an invalid price is NaN in every
expression below (`prices`).

THE ACCOUNTING is E1's constant-weight accounting on E0 (`league.equity.screen.series`'s leg expressions): a lot of
weight w (its entry notional over the run's capital) earns w times each leg's simple return on total-return
(adjustment=all) prices; nothing compounds; the cash book is the engine's and is not read here.

THE COST-FREE LEG RETURN of a name j at session t, for a lot l (decision close d, entry session e = d + 1 at point
a_e, exit session q at point a_q or none yet):

    entry at the open    t = e                 c_j(e) / o_j(e) - 1            exposure w / 2
    entry at the close   t = e                 0                              0
    held                 e < t < q             c_j(t) / c_j(t-1) - 1          w
    exit at the open     t = q                 o_j(q) / c_j(q-1) - 1          w / 2
    exit at the close    t = q                 c_j(q) / c_j(q-1) - 1          w

THE DAILY SERIES, summed over the lots with a leg at t (hs = k x the lot's half-spread at the fill point):
- r_t: the program's P&L, each leg with its costs: an open entry w (c / (o (1 + hs)) - 1), a close entry w (1 / (1 +
  hs) - 1), an open exit w (o (1 - hs) / c_prev - 1) - fee, a close exit w (c (1 - hs) / c_prev - 1) - fee, with fee =
  `league.equity.config.sell_fees`(proceeds = w E0, shares = w E0 / (P_e (1 + hs))) / E0;
- B_t = the sum over lots of w x m_l(t), m_l(t) = the mean of the leg return over the members j of the lot's cell C_l
  whose leg return is valid at t (0 if none): the cost-free P&L of the lot's matched cell;
- x_t = r_t - B_t, THE RESIDUAL (0 on a session with no lot leg);
- s_t: the spread part of the costs; f_t: the sell fees booked at t; x15_t = x_t - `config.STRESS_SPREAD` x s_t -
  `config.STRESS_FEES` x f_t, THE STRESS RESIDUAL (1.5 times the half-spread, every sell fee charged twice);
- c_t (the cost series), g_t = x_t + c_t (the gross residual), delta_t (the diluted exposure), w_t (the exposure),
  exits_t (lots fully exited at t), invested_t (a lot held at the close);
- u_t, THE UNIVERSE EXCESS (the pre-registration's 4.6): the same residual with ONE cell, every name of U(d_l) that
  passes entry validity at e (rung R3). u keeps what two variants of one rule share (their sector, beta and momentum
  tilts), which x removes: the lineage rule reads both.
An invalid leg return of the lot's own name is replaced by m_l(t): the lot's residual is 0 that session and it pays no
cost.

A LOT'S CELL C_l is the member list of its name's cell at the decision close (`ctx.derive`, `Derived.cell`), less the
members that fail entry validity at e (a valid open and close at e and a valid close the session after), FIXED for the
lot's life: the engine writes it in the lot's row and this module reads it there. ONE EXIT LAW for the lot's name, its
counterparts and its cell's members: a member j that is not in U(d') at the first close d' after the decision LEAVES
at the open of d' + 1 while the lot is still open: its leg there is the open exit's, and from the next session on its
leg is invalid (out of the mean; as a counterpart, replaced by m_l).

A NAME WHOSE BARS END (the pre-registration's 5.5, the House's side of the exit law) takes the vanish haircut the same
way, lot, counterpart and member alike, so the haircut makes and destroys no residual: at a VANISH SESSION v of j (its
`config.VANISH_SESSIONS`-th session in a row with no valid close, after a valid one) its leg is -haircut, a valid leg
with no cost, and it is gone after it, WHEN the House could not have sold it since it left (no valid open of j from
its leaving session through v - 1) and the lot is held through v's close. `vanish_sessions` is the engine's own
reader, so the lot the cash book closes "vanished" and the leg booked here are one event.

THE PLACEBOS. A draw gives every lot a COUNTERPART in its cell; its series is cost-free: P^m_t = the sum over lots of
w x (the counterpart's leg return), x^m_t = P^m_t - B_t. THE LAW OF A DRAW (sequential, distinct names): decisions in
time order (a standing-target day is a decision); at a decision the counterparts of the lots that exit at the next
fill are released; the lots opened at this decision are grouped by cell, cells in ascending id, and within a cell
ordered by (w descending, column ascending); for a cell with member list C (ascending column) and k new lots, ONE call
`rng.random((draws, len(C)))` gives one uniform key a member and a draw, the keys of the members the draw currently
holds as a counterpart are raised by 2, and the k members with the smallest keys (a stable sort) are the counterparts,
in that order. One `numpy.random.default_rng(seed)` a run, the calls in that order and no other call (no `choice`,
`shuffle` or `permutation`: their streams are not promised across numpy versions; `random` is).

THE RANK: p_plac = (1 + #{m : T(x^m) >= T(x)}) / (draws + 1), T by `results.t_stat` on the SAME sessions; an undefined
placebo T counts as not above. Under the sharp null (new names are a uniform draw from their cells) the gross residual
is one more draw of the same law, so the rank is exact for any dependence; the gate ranks the NET residual against
cost-free placebos, which is harder to pass.

Evidence module (in the xs identity; a fixed judge: league/ci.py holds league/xs/ out of every role's reach).
"""

from __future__ import annotations

import hashlib
import math
from decimal import Decimal
from typing import Any, Mapping, Sequence

import numpy as np

from ..equity import config as _e1
from . import config, results

#: The House look's draws (the pre-registration's M): the receipt names the figure in force and `screen` refuses a
#: block drawn with another.
DRAWS = 999
#: The seed labels: the one sealed look's (fixed by the receipt and the program's code before the look) and a Train
#: run's (the Train bar's rank, never evidence).
LOOK_SEED = "XS1|{receipt}|{code}|placebo"
TRAIN_SEED = "XS1|train|{run_sha}|{window}|placebo"
#: The arrays `residual` returns, each one value a session.
SERIES = ("r", "bench", "x", "x15", "u", "w", "s", "f", "c", "g", "delta", "exits", "invested")
OPEN, CLOSE = "open", "close"
#: The reason of a lot the engine closed by the vanish rule (the module docstring): its exit leg is the haircut's.
VANISHED = "vanished"
#: A key raised by this much is a member the draw already holds: it is taken only when the cell has no free member.
HELD_KEY = 2.0
#: A lot still open stands in for its counterpart for good (the last exit session a counterpart is held through).
_OPEN_END = 10 ** 9


def _seed(text: str) -> int:
    return int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:16], "big")


def look_seed(receipt_sha256: str, code_sha256: str) -> int:
    """The sealed look's seed: int.from_bytes(sha256(`LOOK_SEED` filled).digest()[:16], "big"). Fixed before the
    look."""
    return _seed(LOOK_SEED.format(receipt=str(receipt_sha256), code=str(code_sha256)))


def train_seed(run_sha: str, window: str) -> int:
    """A Train run's seed, the same expression on `TRAIN_SEED`."""
    return _seed(TRAIN_SEED.format(run_sha=str(run_sha), window=str(window)))


# ------------------------------------------------------------------------------------------- what the bars say
def validity(bars: Any) -> tuple[np.ndarray, np.ndarray]:
    """(open_ok, close_ok), bool (n, m): which opens and closes of `bars` are VALID (the module docstring): the raw
    price above zero, the session's raw volume above zero, the adjusted price above zero, all finite. The engine's
    fills, its entry validity and its vanish rule read this one function."""
    raw = np.asarray(bars.raw, dtype=np.float64)
    adj = np.asarray(bars.adj, dtype=np.float64)
    if raw.ndim != 3 or adj.ndim != 3 or raw.shape[:2] != adj.shape[:2] or raw.shape[2] != 5 or adj.shape[2] != 4:
        raise ValueError("the bars' raw is (n, m, 5) and their adj (n, m, 4), on the same sessions and columns")
    with np.errstate(invalid="ignore"):
        traded = np.isfinite(raw[:, :, 4]) & (raw[:, :, 4] > 0)
        open_ok = traded & np.isfinite(raw[:, :, 0]) & (raw[:, :, 0] > 0) & np.isfinite(adj[:, :, 0]) & \
            (adj[:, :, 0] > 0)
        close_ok = traded & np.isfinite(raw[:, :, 3]) & (raw[:, :, 3] > 0) & np.isfinite(adj[:, :, 3]) & \
            (adj[:, :, 3] > 0)
    return open_ok, close_ok


def prices(bars: Any) -> tuple[np.ndarray, np.ndarray]:
    """(O, C), float64 (n, m): the total-return (adjustment=all) opens and closes, NaN where the price is not valid."""
    open_ok, close_ok = validity(bars)
    adj = np.asarray(bars.adj, dtype=np.float64)
    return np.where(open_ok, adj[:, :, 0], np.nan), np.where(close_ok, adj[:, :, 3], np.nan)


def entry_validity(open_ok: np.ndarray, close_ok: np.ndarray) -> np.ndarray:
    """bool (n, m): THE ENTRY RULE (the pre-registration's 5.3) at each fill session: a valid open and close at the
    session and a valid close the session after (data validity, never a return). At the slice's LAST session there is
    no session after to read: the row is the fill session's own validity (the engine opens nothing there; a lot a log
    holds there keeps its cell)."""
    ok = open_ok & close_ok
    if ok.shape[0] > 1:
        ok[:-1] &= close_ok[1:]
    return ok


def vanish_sessions(close_ok: np.ndarray, sessions: int = config.VANISH_SESSIONS) -> np.ndarray:
    """bool (n, m): True at a name's VANISH SESSION: its `sessions`-th session in a row with no valid close, the one
    before them valid. A held name is closed there (the engine) and its leg is the haircut's (`residual`)."""
    close_ok = np.asarray(close_ok, dtype=bool)
    n = close_ok.shape[0]
    out = np.zeros(close_ok.shape, dtype=bool)
    if n > sessions:
        gone = ~close_ok
        run = gone[sessions:].copy()
        for back in range(1, sessions):
            run &= gone[sessions - back:n - back]
        out[sessions:] = run & close_ok[:n - sessions]
    return out


class _Tables:
    """One slice's price tables, built once a call: the three cost-free returns of every (session, column), which
    prices are valid, the vanish sessions, U at every close the log holds, and each name's next close out of U."""

    __slots__ = ("n", "m", "first", "days", "O", "C", "open_ok", "close_ok", "cc", "co", "oc", "van", "entry_ok", "U",
                 "next_out")

    def __init__(self, bars: Any, log: Any):
        self.open_ok, self.close_ok = validity(bars)
        self.n, self.m = self.open_ok.shape
        self.first = int(bars.first)
        self.days = np.asarray(bars.days, dtype=np.int32)
        if self.days.shape[0] != self.n or not 0 <= self.first <= self.n:
            raise ValueError("the bars' days and their first run session do not fit their arrays")
        adj = np.asarray(bars.adj, dtype=np.float64)
        self.O = np.where(self.open_ok, adj[:, :, 0], np.nan)
        self.C = np.where(self.close_ok, adj[:, :, 3], np.nan)
        nan = np.full((1, self.m), np.nan)
        with np.errstate(invalid="ignore", divide="ignore"):
            self.cc = np.vstack([nan, self.C[1:] / self.C[:-1] - 1.0]) if self.n else self.C.copy()
            self.co = self.C / self.O - 1.0
            self.oc = np.vstack([nan, self.O[1:] / self.C[:-1] - 1.0]) if self.n else self.O.copy()
        self.van = vanish_sessions(self.close_ok)
        self.entry_ok = entry_validity(self.open_ok, self.close_ok)
        # U(t) at every close the engine read; a close it did not read (before the run, the last one) holds no leave.
        self.U = np.ones((self.n, self.m), dtype=bool)
        for row in getattr(log, "decisions", None) or ():
            t = int(row["t"])
            elig = np.asarray(row["derived"].elig, dtype=bool)
            if not 0 <= t < self.n or elig.shape != (self.m,):
                raise ValueError(f"a decision row of the log does not fit the bars (close {t})")
            self.U[t] = elig
        # next_out[t, j]: the first close at or after t at which j is not in U (n when there is none).
        self.next_out = np.full((self.n + 1, self.m), self.n, dtype=np.int64)
        for t in range(self.n - 1, -1, -1):
            self.next_out[t] = np.where(self.U[t], self.next_out[t + 1], t)


def _point(value: Any, what: str, lid: Any) -> str:
    if value not in (OPEN, CLOSE):
        raise ValueError(f"lot {lid}: {what} at {value!r}")
    return str(value)


class _Lot:
    """One row of the holdings log, checked against the bars (ValueError: fail closed, no series)."""

    __slots__ = ("lid", "col", "weight", "decided", "entry", "entry_at", "exit", "exit_at", "reason", "hs_entry",
                 "hs_exit", "cell", "members", "last")

    def __init__(self, row: Mapping[str, Any], tables: _Tables, k: float):
        self.lid = row.get("lid")
        try:
            self.col, self.decided, self.entry = int(row["col"]), int(row["decided"]), int(row["entry"])
            self.weight = float(row["weight"])
            self.cell = int(row["cell"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"lot {self.lid}: a malformed row ({type(exc).__name__}: {exc})") from None
        n, m = tables.n, tables.m
        if not 0 <= self.col < m:
            raise ValueError(f"lot {self.lid}: its column {self.col} is not one of the bars' {m}")
        if not 0 <= self.decided < self.entry < n:
            raise ValueError(f"lot {self.lid}: its decision and entry sessions ({self.decided}, {self.entry}) are not "
                             f"two sessions of the bars' {n}, in that order")
        if not (math.isfinite(self.weight) and self.weight > 0):
            raise ValueError(f"lot {self.lid}: weight {self.weight} is not a number above zero")
        self.entry_at = _point(row.get("entry_at"), "entry", self.lid)
        self.exit, self.exit_at = None, None
        if row.get("exit") is not None:
            self.exit = int(row["exit"])
            self.exit_at = _point(row.get("exit_at"), "exit", self.lid)
            if self.exit <= self.entry:
                raise ValueError(f"lot {self.lid}: sold in its entry session (or before it)")
            if self.exit >= n:
                raise ValueError(f"lot {self.lid}: its exit session {self.exit} is not one of the bars' {n}")
        self.reason = str(row.get("reason") or "")
        self.last = n - 1 if self.exit is None else self.exit
        hs_open, hs_close = float(row.get("hs_open", 0.0)), float(row.get("hs_close", 0.0))
        for hs in (hs_open, hs_close):
            if not (math.isfinite(hs) and hs >= 0 and k * hs < 1):
                raise ValueError(f"lot {self.lid}: a half-spread that is no small non-negative number")
        self.hs_entry = k * (hs_open if self.entry_at == OPEN else hs_close)
        self.hs_exit = k * (hs_open if self.exit_at == OPEN else hs_close) if self.exit is not None else 0.0
        members = np.asarray(row.get("members") if row.get("members") is not None else (), dtype=np.int64).ravel()
        if members.size and (members.min() < 0 or members.max() >= m or np.any(np.diff(members) <= 0)):
            raise ValueError(f"lot {self.lid}: its members are columns of the bars, ascending and distinct")
        self.members = members


def _legs(tables: _Tables, lot: _Lot, members: np.ndarray, haircut: float) -> np.ndarray:
    """rho_j(l, t) for the members j (rows) over the sessions e..last (columns), NaN where invalid: the table of the
    module docstring, the exit law and the vanish leg."""
    e, last = lot.entry, lot.last
    legs = tables.cc[e:last + 1, members].T.copy()
    legs[:, 0] = tables.co[e, members] if lot.entry_at == OPEN else 0.0
    if lot.exit is not None and lot.exit_at == OPEN:
        legs[:, lot.exit - e] = tables.oc[lot.exit, members]
    length = last - e + 1
    # THE EXIT LAW: the first close after the decision at which j is not in U, then the open after it.
    out = tables.next_out[min(lot.decided + 1, tables.n), members]
    leave = np.where(out < tables.n, out + 1, tables.n)
    gone = np.flatnonzero(leave <= last)
    if gone.size:
        at = leave[gone] - e
        legs[gone, at] = tables.oc[leave[gone], members[gone]]
        steps = np.arange(length)[None, :]
        legs[gone] = np.where(steps > at[:, None], np.nan, legs[gone])
    # THE VANISH LEG: a name whose bars end takes the haircut, lot, counterpart and member alike.
    if length > 1:
        hits = tables.van[e + 1:last + 1, members]
        if hits.any():
            done: set[int] = set()
            for step, a in zip(*np.nonzero(hits)):        # in session order: a name vanishes once
                v, a = e + 1 + int(step), int(a)
                if a in done:
                    continue
                if lot.exit is not None and v == lot.exit and lot.exit_at == OPEN:
                    continue                              # the lot was sold at this open: it is not held to the close
                if tables.open_ok[int(leave[a]):v, int(members[a])].any():
                    continue                              # the House sold it at an open before its bars had ended
                legs[a, v - e] = -float(haircut)
                legs[a, v - e + 1:] = np.nan
                done.add(a)
    legs[~np.isfinite(legs)] = np.nan
    return legs


def _fee(lot: _Lot, tables: _Tables, capital: float, capital_dec: Decimal) -> float:
    """The lot's sell fee as a share of E0 (E1's `league.equity.screen.series`): proceeds = w E0, shares = w E0 / (P_e
    (1 + hs))."""
    price = tables.O[lot.entry, lot.col] if lot.entry_at == OPEN else tables.C[lot.entry, lot.col]
    fill = float(price) * (1.0 + lot.hs_entry)
    if not (math.isfinite(fill) and fill > 0):
        raise ValueError(f"lot {lot.lid}: no entry price at session {int(tables.days[lot.entry])}")
    proceeds = Decimal(str(lot.weight)) * capital_dec
    shares = Decimal(str(lot.weight * capital / fill))
    return float(_e1.sell_fees(proceeds, shares)) / capital


def _accumulate(tables: _Tables, lots: Sequence[_Lot], cells: Sequence[np.ndarray], capital: Any, haircut: float,
                keep: bool) -> tuple[dict[str, np.ndarray], list[np.ndarray]]:
    """The daily series of `lots`, each with its member list of `cells`, over the run's sessions; with `keep`, also
    each lot's member legs with the invalid ones replaced by the cell's mean (what a counterpart contributes)."""
    e0 = float(capital)
    if not (math.isfinite(e0) and e0 > 0):
        raise ValueError(f"E0 must be above zero: {capital!r}")
    e0_dec = Decimal(str(capital))
    lo, n = tables.first, tables.n
    size = max(n - lo, 0)
    z = {name: np.zeros(size) for name in ("r", "bench", "s", "f", "w", "c", "delta")}
    exits = np.zeros(size, dtype=np.int64)
    invested = np.zeros(size, dtype=bool)
    filled: list[np.ndarray] = []
    for lot, members in zip(lots, cells):
        if lot.entry < lo:
            raise ValueError(f"lot {lot.lid}: it was opened before the run's first session")
        where = np.flatnonzero(members == lot.col)
        if where.size != 1:
            raise ValueError(f"lot {lot.lid}: its own name is not a member of its cell")
        own_row = int(where[0])
        e, last, om, i = lot.entry, lot.last, lot.weight, lot.col
        legs = _legs(tables, lot, members, haircut)
        ok = np.isfinite(legs)
        count = ok.sum(0)
        mean = np.where(count > 0, np.where(ok, legs, 0.0).sum(0) / np.maximum(count, 1), 0.0)
        if keep:
            filled.append(np.where(ok, legs, mean[None, :]))
        own = legs[own_row]
        fine = np.isfinite(own)
        length = last - e + 1
        is_exit = lot.exit is not None
        vanished = is_exit and lot.reason == VANISHED
        if vanished and not (fine[-1] and lot.exit_at == CLOSE and own[-1] == -float(haircut)):
            raise ValueError(f"lot {lot.lid}: closed as vanished at a session that is no vanish session of its name")
        expo = np.full(length, om)
        expo[0] = om / 2.0 if lot.entry_at == OPEN else 0.0
        held = np.ones(length, dtype=bool)
        pnl = om * np.where(fine, own, 0.0)
        spread = np.zeros(length)
        fees = np.zeros(length)
        o_e, c_e = tables.O[e, i], tables.C[e, i]
        if lot.entry_at == OPEN:
            pnl[0] = om * (c_e / (o_e * (1.0 + lot.hs_entry)) - 1.0)
            spread[0] = om * (c_e / o_e) * (1.0 - 1.0 / (1.0 + lot.hs_entry))
        else:
            pnl[0] = om * (1.0 / (1.0 + lot.hs_entry) - 1.0)
            spread[0] = om * (1.0 - 1.0 / (1.0 + lot.hs_entry))
        if is_exit:
            exits[last - lo] += 1
            if lot.exit_at == OPEN:
                expo[-1] = om / 2.0
                held[-1] = False
            if not vanished and fine[-1]:
                fee = _fee(lot, tables, e0, e0_dec)
                price = tables.O[last, i] if lot.exit_at == OPEN else tables.C[last, i]
                before = tables.C[last - 1, i]
                pnl[-1] = om * (price * (1.0 - lot.hs_exit) / before - 1.0) - fee
                spread[-1] = om * lot.hs_exit * price / before
                fees[-1] = fee
        # an invalid leg of the lot's own name: the lot earns its cell's mean, and pays no cost
        pnl = np.where(fine, pnl, om * mean)
        spread = np.where(fine, spread, 0.0)
        fees = np.where(fine, fees, 0.0)
        if not np.isfinite(pnl).all():
            bad = e + int(np.argmin(np.isfinite(pnl)))
            raise ValueError(f"lot {lot.lid}: no price at session {int(tables.days[bad])}")
        a, b = e - lo, last - lo + 1
        z["r"][a:b] += pnl
        z["bench"][a:b] += om * mean
        z["s"][a:b] += spread
        z["f"][a:b] += fees
        z["w"][a:b] += expo
        z["c"][a:b] += np.where(fine, om * np.where(fine, own, 0.0) - pnl, 0.0)
        z["delta"][a:b] += expo * (1.0 - 1.0 / len(members))
        invested[a:b] |= held
    z["x"] = z["r"] - z["bench"]
    z["x15"] = z["x"] - config.STRESS_SPREAD * z["s"] - config.STRESS_FEES * z["f"]
    z["g"] = z["x"] + z["c"]
    z["exits"], z["invested"] = exits, invested
    return z, filled


def _capital(capital: Any) -> Any:
    return config.XS_SLEEVE_USD if capital is None else capital


def _rung(log: Any, rung: str | None) -> str:
    """The rung the log's cells were cut at (every decision row's `derived.rung`), held to the one asked for."""
    wanted = config.RUNG if rung is None else str(rung)
    if wanted not in config.RUNGS:
        raise ValueError(f"no stratum rung {wanted!r} (known: {', '.join(config.RUNGS)})")
    found = {str(row["derived"].rung) for row in getattr(log, "decisions", None) or ()
             if getattr(row["derived"], "rung", None) is not None}
    if found - {wanted}:
        raise ValueError(f"the log's cells are rung {', '.join(sorted(found))}, not {wanted}: a residual is read on "
                         "the cells its lots were given")
    return wanted


def _haircut(haircut: float | None) -> float:
    value = config.VANISH_HAIRCUT if haircut is None else float(haircut)
    if not (math.isfinite(value) and 0.0 <= value <= 1.0):
        raise ValueError(f"the vanish haircut is a share between 0 and 1, not {haircut!r}")
    return value


def _rows(tables: _Tables, log: Any, k: float) -> list[_Lot]:
    k = float(k)
    if not (math.isfinite(k) and k >= 0):
        raise ValueError(f"the half-spread multiple is a non-negative number, not {k!r}")
    return [_Lot(row, tables, k) for row in getattr(log, "lots", None) or ()]


def _universe(tables: _Tables, lot: _Lot) -> np.ndarray:
    """The ONE cell of the universe excess: every name of U(d_l) that passes entry validity at e."""
    return np.flatnonzero(tables.U[lot.decided] & tables.entry_ok[lot.entry])


def _residual(tables: _Tables, lots: Sequence[_Lot], capital: Any, haircut: float,
              keep: bool) -> tuple[dict[str, Any], list[np.ndarray]]:
    z, filled = _accumulate(tables, lots, [lot.members for lot in lots], capital, haircut, keep)
    one, _ = _accumulate(tables, lots, [_universe(tables, lot) for lot in lots], capital, haircut, False)
    out: dict[str, Any] = {"days": tables.days[tables.first:].copy()}
    out.update({name: z[name] for name in SERIES if name != "u"})
    out["u"] = one["x"]
    out["cells"] = {"small": sum(1 for lot in lots if lot.cell == config.SMALL_CELL),
                    "under5": sum(1 for lot in lots if len(lot.members) < config.MIN_CELL)}
    return out, filled


def residual(bars: Any, log: Any, *, capital: Any = None, k: float = 1.0, rung: str | None = None,
             haircut: float | None = None) -> dict[str, Any]:
    """The daily series of the module docstring over the run's sessions of `bars` (a `store.PanelBars`), from the
    run's `engine.Log`: {"days": int32 ordinals, each name of `SERIES`: an array, "cells": {small, under5}, "rung"}
    (the lots in the pooled small cell, and in a cell left with fewer than `config.MIN_CELL` members). `capital` None
    is `config.XS_SLEEVE_USD`; `rung` None is `config.RUNG` (the log's cells must be that rung's); `haircut` None is
    `config.VANISH_HAIRCUT`. ValueError (fail closed: no series, no verdict) on a lot that names a session or column
    the bars lack, a sale in the entry session, a weight or price that is not finite."""
    rung = _rung(log, rung)
    tables = _Tables(bars, log)
    out, _ = _residual(tables, _rows(tables, log, k), _capital(capital), _haircut(haircut), False)
    out["rung"] = rung
    return out


def _draw(lots: Sequence[_Lot], draws: int, seed: int, columns: int) -> tuple[list[np.ndarray], int]:
    """THE LAW OF A DRAW (the module docstring): per lot, the position of its counterpart in its member list for each
    of `draws` draws; and how many (draw, lot) pairs took a member the draw already held."""
    rng = np.random.default_rng(int(seed))
    positions: list[np.ndarray] = [np.zeros(draws, dtype=np.int64) for _ in lots]
    held = np.full((draws, columns), -1, dtype=np.int64)   # the last exit session each column stands in for
    rows = np.arange(draws)
    decisions: dict[int, dict[int, list[int]]] = {}
    for index, lot in enumerate(lots):
        decisions.setdefault(lot.decided, {}).setdefault(lot.cell, []).append(index)
    reused = 0
    for d in sorted(decisions):
        for cell in sorted(decisions[d]):
            group = sorted(decisions[d][cell], key=lambda index: (-lots[index].weight, lots[index].col))
            members = lots[group[0]].members
            for index in group[1:]:
                if not np.array_equal(lots[index].members, members):
                    raise ValueError(f"lot {lots[index].lid}: the lots one decision opened in one cell hold one "
                                     "member list")
            if len(group) > len(members):
                raise ValueError(f"lot {lots[group[0]].lid}: its cell holds fewer members than the decision's lots")
            keys = rng.random((draws, len(members)))       # ONE call a decision and cell
            busy = held[:, members] > d + 1                # lots that exit at the next fill are released
            order = np.argsort(keys + HELD_KEY * busy, axis=1, kind="stable")
            for rank, index in enumerate(group):
                took = order[:, rank]
                positions[index] = took.astype(np.int64)
                reused += int(busy[rows, took].sum())
                until = _OPEN_END if lots[index].exit is None else lots[index].exit
                cols = members[took]
                held[rows, cols] = np.maximum(held[rows, cols], until)
    return positions, reused


def _spans(spans: Mapping[str, tuple[int, int]] | None, tables: _Tables) -> dict[str, tuple[int, int]]:
    if spans is None:
        return {"run": (tables.first, tables.n - 1)} if tables.n > tables.first else {}
    out = {}
    for name, (first, last) in spans.items():
        first, last = int(first), int(last)
        if not tables.first <= first <= last < tables.n:
            raise ValueError(f"the span {name!r} [{first}, {last}] is outside the run's sessions")
        out[str(name)] = (first, last)
    return out


def run(bars: Any, log: Any, *, n: int, seed: int, spans: Mapping[str, tuple[int, int]] | None = None,
        capital: Any = None, k: float = 1.0, rung: str | None = None,
        haircut: float | None = None) -> dict[str, Any]:
    """`n` matched placebos of the run (the module docstring's law, one `default_rng(seed)`), drawn over the WHOLE run
    and read on each of `spans` ({name: (first session index, last)}, indices of `bars`; None: {"run": the run's
    sessions}; a sealed look's are "V" and "H"). -> {"n", "rung", "seed", "lots", "spans": {name: {"days", "t" [n]
    (None where undefined), "sum" [n], "sumsq" [n], "t_x" (the run's own T on the span), "count" (the draws at or
    above it; None when `t_x` is undefined)}}, "reused" (how many (draw, lot) pairs took a member the draw already
    held), "identity_share" (the share of draws that returned the program's own name: the power the cells cost)}.
    The x^m arithmetic is vectorized over the draws; every t is `results.t_stat`'s expression on that span's
    sessions, one draw at a time."""
    n = int(n)
    if n < 1:
        raise ValueError("a placebo block holds at least one draw")
    rung = _rung(log, rung)
    tables = _Tables(bars, log)
    lots = _rows(tables, log, k)
    series, filled = _residual(tables, lots, _capital(capital), _haircut(haircut), True)
    positions, reused = _draw(lots, n, seed, tables.m)
    lo = tables.first
    total = np.zeros((max(tables.n - lo, 0), n))
    own = 0
    for lot, legs, took in zip(lots, filled, positions):
        a = lot.entry - lo
        total[a:a + legs.shape[1]] += lot.weight * legs[took].T
        own += int(np.sum(lot.members[took] == lot.col))
    by_draw = np.ascontiguousarray((total - series["bench"][:, None]).T)
    x = np.ascontiguousarray(series["x"])
    out_spans: dict[str, Any] = {}
    for name, (first, last) in _spans(spans, tables).items():
        a, b = first - lo, last - lo + 1
        ts: list[float | None] = []
        sums: list[float] = []
        squares: list[float] = []
        for m in range(n):
            values = by_draw[m, a:b]
            ts.append(results.t_stat(values))
            listed = values.tolist()
            sums.append(math.fsum(listed))
            squares.append(math.fsum(v * v for v in listed))
        t_x = results.t_stat(x[a:b])
        out_spans[name] = {"days": b - a, "t": ts, "sum": sums, "sumsq": squares, "t_x": t_x,
                           "count": count_above(t_x, ts)}
    pairs = n * len(lots)
    return {"n": n, "rung": rung, "seed": int(seed), "lots": len(lots), "spans": out_spans, "reused": reused,
            "identity_share": own / pairs if pairs else None}


def count_above(t: float | None, placebo_t: Sequence[float | None]) -> int | None:
    """#{m : placebo_t[m] >= t}: the integer the gate's bar is held on (the pre-registration: count <= 119 of 999).
    An undefined placebo t (None or NaN) counts as not above; None when `t` itself is undefined."""
    if t is None or not math.isfinite(float(t)):
        return None
    t = float(t)
    return sum(1 for value in placebo_t if value is not None and float(value) >= t)


def p_value(t: float | None, placebo_t: Sequence[float | None]) -> float | None:
    """(1 + #{m : placebo_t[m] >= t}) / (len(placebo_t) + 1); an undefined placebo t counts as not above; None when
    `t` itself is undefined (the look then fails on its t)."""
    count = count_above(t, placebo_t)
    return None if count is None else (1 + count) / (len(placebo_t) + 1)


def stat(blocks: Sequence[Mapping[str, Any]], span: str = "run") -> np.ndarray:
    """T per placebo index over SEVERAL runs' blocks pooled from their sums (the seen-span runs of one version, for
    the Train bar's rank): placebo m of one run pairs with placebo m of the next, each an independent draw. NaN where
    undefined. Never the sealed look's statistic (that is `run`'s own `t`)."""
    blocks = list(blocks)
    if not blocks:
        raise ValueError("no placebo block to pool")
    sizes = {int(block["n"]) for block in blocks}
    if len(sizes) != 1:
        raise ValueError("the blocks pooled hold one number of draws")
    n = sizes.pop()
    parts = []
    for block in blocks:
        row = (block.get("spans") or {}).get(span)
        if row is None or len(row["sum"]) != n or len(row["sumsq"]) != n:
            raise ValueError(f"a placebo block has no span {span!r} of {n} draws")
        parts.append(row)
    days = sum(int(row["days"]) for row in parts)
    out = np.full(n, np.nan)
    if days < 2:
        return out
    for m in range(n):
        total = math.fsum(float(row["sum"][m]) for row in parts)
        squares = math.fsum(float(row["sumsq"][m]) for row in parts)
        mean = total / days
        var = (squares - days * mean * mean) / (days - 1)
        if var > 0 and math.sqrt(var) >= 1e-12:
            t = mean / math.sqrt(var) * math.sqrt(days)
            if math.isfinite(t):
                out[m] = t
    return out


__all__ = ["DRAWS", "LOOK_SEED", "TRAIN_SEED", "SERIES", "VANISHED", "look_seed", "train_seed", "validity", "prices",
           "entry_validity", "vanish_sessions", "residual", "run", "p_value", "count_above", "stat"]
