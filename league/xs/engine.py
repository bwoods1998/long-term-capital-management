"""The panel's daily replay: the KEEP rule's orders, E1's fills, fees and sizing, the House exits, the holdings log.

Owner: package D.

ONE SESSION. At the close of t the House exits are planned (below, `ctx.ineligible` included) and, on a decision day
(`config.decision_due`), the program is called on `ctx.build(ctx.inputs_from_panel(bars, t, ...))` and its target
planned (`plan_orders`); on every other close the STANDING target's buys are planned. In t + 1: open exits, open
entries, close exits, close entries (E1's order), at E1's own functions, imported, never copied:
`league.equity.engine.fill_price(official, side, hs, k)` with hs = `bars.hs[col, 0 | 1]`, `league.equity.config
.sell_fees`, `league.equity.sizing.size_entry` (class "stock", the sleeve `cfg.capital`, `config.POSITION_SHARE`,
`config.RISK_WEIGHT`, no budget room, `config.MIN_NAME_USD`), `league.equity.config.may_sell` and `max_hold_due`, and
splits and dividends by `league.equity.engine.split_factor` on the adj/raw ratio step, each step read with
`config.rounding_bound` (the vendor's cents: `ratio_tolerance`, `split_of`). Sleeve cash >= 0 after every fill
(asserted). Deterministic: the same inputs give the same `result_sha`. There is no state reset inside a run.
DECISIONS run at the close of every session from the one before the run's first (a history session: its orders
execute on the run's first session) to the one before its last (a decision at the last close could never execute).

THE KEEP RULE (the pinned pre-registration's C3; it overrides E4-SPEC D10's top-ups and dropped orders), in
`plan_orders`, ONE pure function for the Gym and the live child:
1. sells, in lot id order: every open lot of an id that is absent from the target;
2. buys, by descending w then ascending id: an id with no open lot is bought as ONE lot of `w x budget` dollars
   (floored to the cent; `budget` is the run's capital E0 in the Gym, so a lot of weight w is w x E0 and nothing
   compounds; live it is the sleeve's size); a buy under `min_order` is rejected ("under the minimum order");
3. an id that is held and in the target is KEPT: no trade, no resize, no partial close, whatever its weight;
4. a target that needs more than `max_sells` sells or more than `max_buys` buys is REFUSED WHOLE: no order, the reject
   "order cap", the decision is a hold (a rule that wants more staggers itself).
Sells are `{"sell": lid, "at"}`, buys `{"buy_id": id, "usd", "at"}`.

THE STANDING TARGET (E4-SPEC D10 (4); the pre-registration is silent on it; kept so a buy live could not make is
tried again in the Gym and live by ONE rule). The last valid target of a called decision stands until the next one
replaces it (a hold, a None, a malformed answer or a target the order cap refused leaves it standing). At every close
where the program is NOT called, `plan_orders(standing, at, lots, budget, standing=True, exited=..., eligible=...)`
plans BUYS ONLY: the standing target's ids that are eligible at this close and have no open lot, no buy pending and no
House exit since the target was set (`exited`), each for w x budget when that is >= `min_order`; never a sell, no
program code. Such a buy is a lot with its own decision day (the close it was planned at): its cell and its placebo
counterparts are that day's.

THE HOUSE EXITS (the pre-registration's C6, 3.5 and 5.5; the Gym and live alike), at the next open: a lot at its
`max_hold_sessions` ("max_hold"); every lot after `league.equity.config.FAILED_DECIDES_EXIT` failed CALLED decides
("house"); a lot whose name is not in U(t) at ANY close, called or not ("house", tag "ineligible"). A lot the House
exits goes at the open whatever the target planned for it. An exit with no valid price that session waits for the
next. VANISHED: a held name with no valid close on `config.VANISH_SESSIONS` sessions in a row
(`placebo.vanish_sessions`) is closed on the last of them, no fee, reason "vanished", at its last marked close x
(1 - `cfg.haircut`), whatever way its spell ended (the kinds are counted in `summary.vanished`, with the sensitivity
at haircut 0 and 1). ENTRY VALIDITY (the pre-registration's 5.3; `placebo.entry_validity`): a buy needs a valid open
and close of its name at the fill session and a valid close the session after, else it is not opened (the reject "no
bar"); so NO LOT IS OPENED AT THE SLICE'S LAST SESSION (it has no session after: the study's runs open nothing there
either). Each such refusal is counted (`summary.refused`): the peek at the session after is the one validity the Gym
reads and live cannot yet know.

THE HOLDINGS LOG (`Log`; the pre-registration's C7) is what `placebo.residual` and `placebo.run` read, with the bars
and nothing else: for every lot its column, weight (entry notional / capital), decision session, entry session and
point, exit session and point (if any), reason, hs at both points, and its CELL: the cell id and the member columns of
the name's cell at the decision close (`ctx.derive`), less the members that fail entry validity at the entry session.
And U(t) at EVERY close the engine read (a decision row each, called or not: the exit law of the residual needs the
first close after a lot's decision at which a member is out). It never leaves the child.

WHAT A PROGRAM IS TOLD OF ITS OWN BOOK: lot ids, slot ids, weights and reasons, never a session, a day or a price
(`ctx.build` forms what it sees from the rows this module hands `ctx.inputs_from_panel`); every reject text names
slots and lots only.

Evidence module (in the xs identity; one of its roots).
"""

from __future__ import annotations

import hashlib
import inspect
import math
import time
from dataclasses import dataclass
from decimal import ROUND_DOWN, ROUND_HALF_EVEN, Decimal
from fractions import Fraction
from pathlib import Path
from typing import Any, Collection, Mapping, Sequence

import numpy as np

from ..equity import config as _e1
from ..equity import engine as _e1_engine
from ..equity import sizing
from ..equity.store import from_ordinal
from . import XS_ENGINE_VERSION, config, placebo, results
from . import ctx as _ctx
from . import style as _style

OPEN, CLOSE = "open", "close"
#: The first words of the reject of a target the order cap refused WHOLE (the KEEP rule's 4): the decision is a hold.
ORDER_CAP = "order cap"
#: The reasons a lot leaves for, as its row and the next ctx say them.
PROGRAM, HOUSE, MAX_HOLD, VANISHED = "program", "house", "max_hold", placebo.VANISHED
INELIGIBLE = "ineligible"
#: The kinds of buy entry validity did not open (`summary.refused`).
REFUSED = ("no_bar", "ahead", "last")
_PRICE = Decimal("0.000001")
_QTY = Decimal(1).scaleb(-_e1.QTY_PLACES)
#: Whether E1's `split_factor` takes the step's own tolerance (it gained it with the vendor's cents, after this build's
#: base): `split_of` calls it when it does.
_E1_SPLIT_TOLERANCE = "tolerance" in inspect.signature(_e1_engine.split_factor).parameters


@dataclass(frozen=True)
class EngineConfig:
    """One run's settings, each part of its identity: `capital` the sleeve E0 (dollars, Decimal), `k` the half-spread
    multiple, `timeout` and `max_errors` the runner's (1 s a call, 25 errors), `budget_seconds` all the run's decide
    calls together (None: no limit), `haircut` the vanish haircut."""

    capital: Decimal = config.XS_SLEEVE_USD
    k: float = 1.0
    timeout: float = 1.0
    max_errors: int = 25
    budget_seconds: float | None = 600.0
    haircut: float = config.VANISH_HAIRCUT

    def identity(self) -> dict[str, Any]:
        """{capital, k, timeout, max_errors, haircut}: what of the settings names a run."""
        return {"capital": str(Decimal(str(self.capital))), "k": float(self.k), "timeout": float(self.timeout),
                "max_errors": int(self.max_errors), "haircut": float(self.haircut)}


class Log:
    """A run's holdings log (the module docstring): the decisions in time order with their `ctx.Derived`, and every
    lot's row. Built by `run`, read by `placebo.residual` and `placebo.run`; it never leaves the child and is never
    stored. `lots`: rows {lid, col, weight, decided (session index), entry, entry_at, exit (None while open), exit_at,
    reason, hs_open, hs_close, cell, members (int32 columns, ascending id)}; `decisions`: rows {t, called, derived},
    ONE A CLOSE THE ENGINE READ (called or not: U(t) is each row's `derived.elig`)."""

    __slots__ = ("lots", "decisions")

    def __init__(self) -> None:
        self.lots: list[dict[str, Any]] = []
        self.decisions: list[dict[str, Any]] = []

    def decision(self, t: int) -> dict[str, Any]:
        """The decision row of the close of session index `t` (KeyError when the engine read none there)."""
        for row in self.decisions:
            if int(row["t"]) == int(t):
                return row
        raise KeyError(f"the log holds no decision at the close of session {t}")


# --------------------------------------------------------------------------------------------- the KEEP rule
def _cents(value: Decimal) -> Decimal:
    return value.quantize(_e1.CENT, rounding=ROUND_DOWN)


def refused_whole(rejects: Sequence[str]) -> bool:
    """Whether `plan_orders`' rejects say the order cap refused the target whole (the decision is then a hold)."""
    return bool(rejects) and str(rejects[0]).startswith(ORDER_CAP)


def plan_orders(target: Mapping[int, float], at: str, lots: Sequence[Mapping[str, Any]], budget: Any, *,
                min_order: Decimal = config.MIN_NAME_USD, max_buys: int = config.MAX_BUYS,
                max_sells: int = config.MAX_SELLS, standing: bool = False, exited: Sequence[int] = (),
                eligible: Collection[int] | None = None) -> tuple[list[dict[str, Any]], list[str]]:
    """THE KEEP RULE (the module docstring): (orders, rejects) of a valid `target` {id: w} at fill point `at`, given
    the open `lots` (rows {lid, id, pending (a buy of the id is working)}) and the sleeve's `budget` dollars. With
    `standing` the buys of the standing target and nothing else, skipping the ids of `exited` and, when `eligible` is
    given, every id outside it (the ids of U at this close). Pure: no clock, no store, no program code; the same
    function in the engine and in the live child. A target's keys are read with `int()` (one that came back through
    JSON is the same target); a weight of zero or less is the id's absence."""
    if at not in (OPEN, CLOSE):
        raise ValueError(f"'at' is open or close, not {at!r}")
    wanted: dict[int, float] = {}
    for key, weight in dict(target).items():
        weight = float(weight)
        if not math.isfinite(weight):
            raise ValueError(f"the target's weight of {key} is not a number")
        if weight > 0:
            wanted[int(key)] = weight
    room = Decimal(str(budget))
    if not room.is_finite() or room < 0:
        raise ValueError(f"the budget is a number of dollars, not {budget!r}")
    floor = Decimal(str(min_order))
    held = {int(row["id"]) for row in lots if row.get("id") is not None}
    sells: list[dict[str, Any]] = []
    if not standing:
        mine = [row for row in lots if row.get("lid") is not None and not row.get("pending")]
        for row in sorted(mine, key=lambda row: int(row["lid"])):
            if int(row["id"]) not in wanted:
                sells.append({"sell": int(row["lid"]), "at": at})
    skip = {int(i) for i in exited} if standing else set()
    allowed = None if eligible is None or not standing else {int(i) for i in eligible}
    buys: list[dict[str, Any]] = []
    rejects: list[str] = []
    for slot, weight in sorted(wanted.items(), key=lambda item: (-item[1], item[0])):
        if slot in held or slot in skip or (allowed is not None and slot not in allowed):
            continue
        usd = _cents(Decimal(str(weight)) * room)
        if usd < floor:
            rejects.append(f"buy {slot}: under the minimum order (${usd} of a ${floor} minimum)")
            continue
        buys.append({"buy_id": slot, "usd": float(usd), "at": at})
    if len(sells) > int(max_sells) or len(buys) > int(max_buys):
        return [], [f"{ORDER_CAP}: the target needs {len(sells)} sells and {len(buys)} buys, and a decision makes at "
                    f"most {int(max_sells)} and {int(max_buys)}: refused whole, the decision is a hold"]
    return [*sells, *buys], rejects


# ----------------------------------------------------------------------------------- the vendor's cents (splits)
def ratio_tolerance(adj_prev: float, adj_now: float) -> float:
    """How far from 1 the all/raw ratio's step between two bars may lie and still be the series' rounding: E1's
    `RATIO_TOLERANCE`, or the vendor's cent rounding of the two adjusted closes when that is more
    (`config.rounding_bound`). A close that is no positive finite number has no rounding to allow for."""
    try:
        return max(_e1_engine.RATIO_TOLERANCE, config.rounding_bound(adj_prev, adj_now))
    except (TypeError, ValueError):
        return _e1_engine.RATIO_TOLERANCE


def _split_own(step: float, tolerance: float) -> Fraction | None:
    """E1's `split_factor` with the step's own tolerance, to the letter of its commit 547206fa: league/xs's own copy
    until that E1 is in this build's base (`split_of` calls E1's as soon as it takes the tolerance)."""
    if not (math.isfinite(step) and step > 0) or abs(step - 1.0) < _e1_engine.SPLIT_MIN_STEP:
        return None
    best: tuple[float, Fraction] | None = None
    for q in range(1, _e1_engine.SPLIT_TERMS + 1):
        for p in range(1, _e1_engine.SPLIT_TERMS + 1):
            factor = Fraction(p, q)
            if factor == 1 or math.gcd(p, q) != 1:
                continue
            residual = step * float(factor)
            if residual > 1.0 + tolerance or residual < 1.0 - _e1_engine.SPLIT_RESIDUAL:
                continue
            gap = abs(1.0 - residual)
            if best is None or gap < best[0]:
                best = (gap, factor)
    return best[1] if best else None


def split_of(step: float, tolerance: float) -> Fraction | None:
    """The split a ratio step names, read with the step's own tolerance (`ratio_tolerance`): g x F may lie that far
    above 1 and F still be the factor. E1's `split_factor` when it takes the tolerance, else `_split_own`."""
    if _E1_SPLIT_TOLERANCE:
        return _e1_engine.split_factor(step, tolerance)
    return _split_own(step, tolerance)


def _decimal_price(value: float) -> Decimal:
    return Decimal(f"{value:.6f}")


def _money(value: Decimal) -> float:
    return float(value.quantize(_e1.CENT, rounding=ROUND_HALF_EVEN))


class _Lot:
    __slots__ = ("lid", "col", "slot", "qty", "entry_px", "notional", "decided", "entry_index", "entry_at", "fees",
                 "div", "mark", "exit_index", "exit_at", "exit_px", "proceeds", "reason", "tag", "row")

    def __init__(self, lid: int, col: int, slot: int, qty: Decimal, entry_px: Decimal, decided: int, entry_index: int,
                 entry_at: str, mark: float, row: dict[str, Any]):
        self.lid, self.col, self.slot = lid, col, slot
        self.qty, self.entry_px = qty, entry_px
        self.notional = qty * entry_px
        self.decided, self.entry_index, self.entry_at = decided, entry_index, entry_at
        self.fees = Decimal(0)
        self.div = Decimal(0)
        self.mark = mark
        self.exit_index: int | None = None
        self.exit_at: str | None = None
        self.exit_px: Decimal | None = None
        self.proceeds = Decimal(0)
        self.reason: str | None = None
        self.tag = ""
        self.row = row                # its row of the holdings log (the exit is written there when it comes)

    @property
    def net(self) -> Decimal:
        return self.proceeds - self.notional - self.fees + self.div


class _Account:
    """One program's sleeve over one run: its cash, its lots, the orders it is owed, the holdings log and the daily
    cash book."""

    def __init__(self, program: Any, bars: Any, cfg: EngineConfig, *, keep_calls: bool = False):
        self.program, self.bars, self.cfg = program, bars, cfg
        self.needs = program.needs
        self.capital = Decimal(str(cfg.capital))
        if not (self.capital.is_finite() and self.capital > 0):
            raise ValueError("a run's capital is a positive number of dollars")
        self.k = float(cfg.k)
        self.haircut = float(cfg.haircut)
        if not 0.0 <= self.haircut <= 1.0:
            raise ValueError("the vanish haircut is a share between 0 and 1")
        self.raw = np.asarray(bars.raw, dtype=np.float64)
        self.adj = np.asarray(bars.adj, dtype=np.float64)
        self.open_ok, self.close_ok = placebo.validity(bars)
        self.n, self.m = self.open_ok.shape
        self.ref = int(bars.ref)
        ids = np.asarray(bars.ids, dtype=np.int64)
        if ids.shape != (self.m - self.ref,):
            raise ValueError("the slice's ids do not name its member columns")
        self.ids = ids
        self.col_of = {int(slot): self.ref + i for i, slot in enumerate(ids)}
        if len(self.col_of) != len(ids):
            raise ValueError("two member columns of the slice share an id")
        self.hs = np.asarray(bars.hs, dtype=np.float64)
        if self.hs.shape != (self.m, 2):
            raise ValueError("the slice's half-spreads are one pair a column")
        self.entry_ok = placebo.entry_validity(self.open_ok, self.close_ok)
        self.vanish = placebo.vanish_sessions(self.close_ok)
        self.days = [from_ordinal(int(d)) for d in np.asarray(bars.days)]
        self.iso = [d.isoformat() for d in self.days]
        self.cash = self.capital
        self.lots: dict[int, _Lot] = {}
        self.closed: list[_Lot] = []
        self.next_lid = 1
        self.pending: list[dict[str, Any]] = []
        self.house: dict[int, tuple[str, str]] = {}
        self.rejects: list[str] = []
        self.closed_since: list[_Lot] = []
        self.fails = 0
        self.equity: list[float] = []
        self.actions: list[dict[str, Any]] = []
        self.log = Log()
        self.derived: Any = None             # the last close's `ctx.Derived`: the cells of the orders now pending
        self.decided: int | None = None      # that close's session index
        self.pick: dict[str, Any] | None = None
        self.picks: list[dict[str, Any]] = []
        self.calls: list[dict[str, Any]] | None = [] if keep_calls else None
        self.standing: dict[str, Any] | None = None
        self.exited: set[int] = set()
        self.refused = {kind: 0 for kind in REFUSED}
        self.vanished = {"deal": 0, "other": 0}
        self.runner = program.start(timeout=cfg.timeout, max_errors=cfg.max_errors, budget_seconds=cfg.budget_seconds)

    # ------------------------------------------------------------------ helpers
    def reject(self, text: str) -> None:
        self.rejects.append(text)

    def _assert_cash(self, what: str) -> None:
        assert self.cash >= 0, f"the sleeve's cash went below zero after {what} (an engine bug): {self.cash}"

    def _value(self, *, col: int | None = None, marks: Mapping[int, float] | None = None) -> Decimal:
        total = Decimal(0)
        for lot in self.lots.values():
            if col is not None and lot.col != col:
                continue
            total += lot.qty * _decimal_price((marks or {}).get(lot.col, lot.mark))
        return total

    def official(self, col: int, j: int, at: str) -> float | None:
        """The official raw open or close of column `col` at session `j`, None when that price is not valid."""
        if at == OPEN:
            return float(self.raw[j, col, 0]) if self.open_ok[j, col] else None
        return float(self.raw[j, col, 3]) if self.close_ok[j, col] else None

    # ------------------------------------------------------------------ a session
    def session(self, j: int) -> None:
        """Execute the last close's orders in session j: corporate actions first, then (1) open exits, (2) open
        entries, (3) close exits, (4) close entries; then the vanish rule at the close."""
        self._corporate_actions(j)
        for at in (OPEN, CLOSE):
            self._exits(j, at)
            self._entries(j, at)
        self.pending = []
        self._vanish(j)

    def _corporate_actions(self, j: int) -> None:
        if j == 0:
            return
        for col in sorted({lot.col for lot in self.lots.values()}):
            if not self.close_ok[j, col]:
                continue                 # no bar today: judged when the next bar comes
            before = np.flatnonzero(self.close_ok[:j, col])
            if not before.size:
                continue
            prev = int(before[-1])
            raw_c, adj_c = self.raw[:, col, 3], self.adj[:, col, 3]
            step = (adj_c[prev] / raw_c[prev]) / (adj_c[j] / raw_c[j])
            # the vendor rounds the adjusted closes to the cent: the step's own tolerance, for all three readings
            tolerance = ratio_tolerance(adj_c[prev], adj_c[j])
            if abs(step - 1.0) <= tolerance:
                continue
            factor = split_of(step, tolerance)
            residual = step * (float(factor) if factor else 1.0)
            per_share = (1.0 - residual) * float(raw_c[prev]) if residual < 1.0 - tolerance else 0.0
            slot = int(self.ids[col - self.ref]) if col >= self.ref else None
            if factor is None and per_share == 0.0:
                self.actions.append({"id": slot, "day": self.iso[j], "kind": "anomaly", "step": round(step, 8)})
                continue
            dividend = _decimal_price(per_share) if per_share > 0 else Decimal(0)
            for lot in self.lots.values():
                if lot.col != col:
                    continue
                if dividend > 0:
                    cash = (lot.qty * dividend).quantize(_e1.CENT, rounding=ROUND_HALF_EVEN)
                    lot.div += cash
                    self.cash += cash
                if factor is not None:
                    lot.qty = (lot.qty * factor.numerator / factor.denominator).quantize(_QTY, rounding=ROUND_HALF_EVEN)
                    lot.entry_px = (lot.entry_px * factor.denominator / factor.numerator).quantize(
                        _PRICE, rounding=ROUND_HALF_EVEN)
                    lot.mark = lot.mark * factor.denominator / factor.numerator
            if dividend > 0:
                self.actions.append({"id": slot, "day": self.iso[j], "kind": "dividend",
                                     "per_share": float(dividend)})
            if factor is not None:
                self.actions.append({"id": slot, "day": self.iso[j], "kind": "split",
                                     "factor": f"{factor.numerator}:{factor.denominator}"})

    def _close_lot(self, lot: _Lot, j: int, at: str, reason: str, tag: str, fill: Decimal, fees: Decimal) -> None:
        proceeds = lot.qty * fill
        self.cash += proceeds - fees
        self._assert_cash(f"closing lot {lot.lid}")
        lot.exit_index, lot.exit_at, lot.exit_px, lot.proceeds, lot.reason = j, at, fill, proceeds, reason
        lot.tag = tag
        lot.fees += fees
        lot.mark = float(fill)
        lot.row.update(exit=j, exit_at=at, reason=reason)
        del self.lots[lot.lid]
        self.house.pop(lot.lid, None)
        self.closed.append(lot)
        self.closed_since.append(lot)

    def _sell(self, lot: _Lot, j: int, at: str, reason: str, tag: str = "") -> bool:
        price = self.official(lot.col, j, at)
        if price is None:
            self.reject(f"sell {lot.lid} ({reason}): no valid {at} for slot {lot.slot} this session; the lot stays "
                        "open")
            return False
        fill = _decimal_price(_e1_engine.fill_price(price, "sell", float(self.hs[lot.col, 0 if at == OPEN else 1]),
                                                    self.k))
        proceeds = lot.qty * fill
        fees = min(_e1.sell_fees(proceeds, lot.qty), proceeds)   # a sale never costs more than it brings
        self._close_lot(lot, j, at, reason, tag, fill, fees)
        return True

    def _exits(self, j: int, at: str) -> None:
        for order in self.pending:
            if "sell" not in order or order["at"] != at:
                continue
            lot = self.lots.get(int(order["sell"]))
            if lot is None:
                self.reject(f"sell {order['sell']}: no open lot {order['sell']}")
            elif not _e1.may_sell(lot.entry_index, j):
                self.reject(f"sell {lot.lid}: bought this session (a lot never sells in the session it was bought)")
            else:
                self._sell(lot, j, at, PROGRAM)
        if at != OPEN:
            return
        for lid, (reason, tag) in list(self.house.items()):
            lot = self.lots.get(lid)
            if lot is None:
                del self.house[lid]
            elif _e1.may_sell(lot.entry_index, j):
                self._sell(lot, j, at, reason, tag)

    def _drop(self, slot: int, why: str) -> None:
        """A buy the session did not make: the program reads why, and the decision's pick row keeps it."""
        self.reject(f"buy {slot}: {why}")
        if self.pick is not None:
            self.pick["dropped"].append([int(slot), why])

    def _entries(self, j: int, at: str) -> None:
        for order in self.pending:
            if "buy_id" not in order or order["at"] != at:
                continue
            slot = int(order["buy_id"])
            col = self.col_of.get(slot)
            derived, decided = self.derived, self.decided
            if col is None or derived is None or decided is None:
                self._drop(slot, "not a slot of this run")
                continue
            cell = int(np.asarray(derived.cell)[col])
            if cell < 0 or not bool(np.asarray(derived.elig)[col]):
                self._drop(slot, "not eligible at the decision")
                continue
            if j >= self.n - 1:
                self.refused["last"] += 1
                self._drop(slot, "no bar (the run's last session opens no lot)")
                continue
            if not (self.open_ok[j, col] and self.close_ok[j, col]):
                self.refused["no_bar"] += 1
                self._drop(slot, "no bar at the fill")
                continue
            if not self.close_ok[j + 1, col]:
                self.refused["ahead"] += 1
                self._drop(slot, "no bar (its data do not hold through the session after the fill)")
                continue
            price = self.official(col, j, at)
            assert price is not None
            limit = _decimal_price(_e1_engine.fill_price(price, "buy", float(self.hs[col, 0 if at == OPEN else 1]),
                                                         self.k))
            marks = {col: price}
            own = self._value(col=col, marks=marks)
            sized = sizing.size_entry(sizing.SizingInputs(
                symbol=f"slot {slot}", klass=_e1.STOCK, share=None, usd=Decimal(str(order["usd"])), limit_price=limit,
                E=self.capital, sleeve_equity=self.capital, sleeve_free_cash=self.cash, sleeve_symbol_value=own,
                position_share=config.POSITION_SHARE, account_symbol_value=own,
                invested_now=self._value(marks=marks), invested_share=Decimal("1.00"), available_cash=self.cash,
                cash=self.cash, any_short=False, budget_room=None, weight=config.RISK_WEIGHT,
                min_order_usd=config.MIN_NAME_USD))
            qty = Decimal(sized.qty).quantize(_QTY, rounding=ROUND_DOWN) if sized.qty > 0 else Decimal(0)
            if qty <= 0:
                self._drop(slot, f"sized to nothing ({sized.binding}: {sized.reason})")
                continue
            members = np.flatnonzero((np.asarray(derived.cell) == cell) & self.entry_ok[j]).astype(np.int32)
            notional = qty * limit
            row = {"lid": self.next_lid, "col": col, "id": slot, "weight": float(notional / self.capital),
                   "decided": decided, "entry": j, "entry_at": at, "exit": None, "exit_at": None, "reason": "open",
                   "hs_open": float(self.hs[col, 0]), "hs_close": float(self.hs[col, 1]), "cell": cell,
                   "members": members}
            lot = _Lot(self.next_lid, col, slot, qty, limit, decided, j, at, price, row)
            self.cash -= lot.notional
            self._assert_cash(f"buying lot {lot.lid}")
            self.lots[lot.lid] = lot
            self.log.lots.append(row)
            self.next_lid += 1

    def _vanish(self, j: int) -> None:
        """THE VANISH RULE (the module docstring): a held name at its vanish session is closed there, no fee, at its
        last marked close x (1 - haircut)."""
        for lot in list(self.lots.values()):
            if not self.vanish[j, lot.col] or not _e1.may_sell(lot.entry_index, j):
                continue
            fill = _decimal_price(max(lot.mark, 0.0) * (1.0 - self.haircut))
            self._close_lot(lot, j, CLOSE, VANISHED, "", fill, Decimal(0))
            kind = "deal" if int(np.asarray(self.bars.exit)[lot.col]) == 1 else "other"
            self.vanished[kind] += 1
            self.exited.add(lot.slot)
            self.actions.append({"id": lot.slot, "day": self.iso[j], "kind": VANISHED, "exit": kind})

    # ------------------------------------------------------------------ the close and the decision
    def mark_close(self, j: int) -> None:
        for lot in self.lots.values():
            price = self.official(lot.col, j, CLOSE)
            if price is not None:
                lot.mark = price
        self.equity.append(float((self.cash + self._value()).quantize(_e1.CENT)))

    def _positions(self, j: int) -> list[dict[str, Any]]:
        return [{"lid": lot.lid, "col": lot.col, "qty": float(lot.qty),
                 "value": float(lot.qty * _decimal_price(lot.mark)), "entry_value": float(lot.notional),
                 "held_sessions": j - lot.entry_index, "at": lot.entry_at, "tag": lot.tag}
                for lot in self.lots.values()]

    def _closed_rows(self, j: int) -> list[dict[str, Any]]:
        return [{"lid": lot.lid, "col": lot.col,
                 "net_ret": round(float(lot.net / lot.notional), 4) if lot.notional > 0 else 0.0,
                 "held_sessions": (j if lot.exit_index is None else int(lot.exit_index)) - lot.entry_index,
                 "reason": str(lot.reason), "tag": lot.tag} for lot in self.closed_since]

    def close(self, j: int) -> None:
        """The close of session j: U(j) and the cells (`ctx.derive`), the House exits, then the program's call on a
        decision day, or the standing target's buys on every other."""
        positions, closed = self._positions(j), self._closed_rows(j)
        book = {"positions": positions, "closed": closed, "rejects": list(self.rejects), "cash": float(self.cash),
                "equity": float(self.cash + self._value()), "budget": float(self.capital)}
        inputs = _ctx.inputs_from_panel(self.bars, j, needs=self.needs, params=self.program.params, **book)
        derived = _ctx.derive(inputs)
        called = bool(config.decision_due(self.days[j], self.needs.rebalance, self.needs.weekday))
        self.log.decisions.append({"t": j, "called": called, "derived": derived})
        self.derived, self.decided, self.pick = derived, j, None
        # THE HOUSE EXITS, read at every close
        for lid in _ctx.ineligible(inputs, derived):
            lot = self.lots.get(int(lid))
            if lot is not None and lot.lid not in self.house:
                self.house[lot.lid] = (HOUSE, INELIGIBLE)
                self.exited.add(lot.slot)
        for lot in self.lots.values():
            if _e1.max_hold_due(j - lot.entry_index, self.needs.max_hold_sessions) and lot.lid not in self.house:
                self.house[lot.lid] = (MAX_HOLD, "")
                self.exited.add(lot.slot)
        rows = [{"lid": lot.lid, "id": lot.slot, "pending": False} for lot in self.lots.values()]
        orders: list[dict[str, Any]] = []
        if called:
            ctx = _ctx.build(inputs)
            ctx_sha = hashlib.sha256(_ctx.ctx_bytes(ctx)).hexdigest()
            if self.calls is not None:
                self.calls.append({"t": j, **book})
            answer = self.runner.decide(ctx)
            self.rejects, self.closed_since = [], []
            self.fails = self.fails + 1 if self.runner.last_failed else 0
            target = answer.get("target") if isinstance(answer, Mapping) and not answer.get("hold") else None
            at = str(answer.get("at") or OPEN) if isinstance(answer, Mapping) else OPEN
            pick = {"decided": self.iso[j], "exec": self.iso[j + 1], "at": at if target is not None else None,
                    "called": 1, "targets": [], "buys": [], "sells": [], "dropped": [],
                    "budget": book["budget"], "equity": round(book["equity"], 2), "ctx_sha": ctx_sha}
            if target is not None:
                wanted = {int(slot): float(weight) for slot, weight in dict(target).items()}
                orders, rejects = plan_orders(wanted, at, rows, self.capital)
                self.rejects.extend(rejects)
                if refused_whole(rejects):
                    pick["dropped"].append([None, ORDER_CAP])
                    pick["at"] = None
                else:
                    pick["targets"] = [[slot, wanted[slot]] for slot in sorted(wanted)]
                    held = {row["id"] for row in rows}
                    bought = {int(order["buy_id"]) for order in orders if "buy_id" in order}
                    for slot in sorted(wanted):
                        if wanted[slot] > 0 and slot not in held and slot not in bought:
                            pick["dropped"].append([slot, "under the minimum order"])
                    self.standing = {"target": wanted, "at": at}
                    self.exited = {self.lots[lid].slot for lid in self.house if lid in self.lots}
            self.pick = pick
            self.picks.append(pick)
            if self.fails >= _e1.FAILED_DECIDES_EXIT:
                for lot in self.lots.values():
                    self.house[lot.lid] = (HOUSE, "")
                    self.exited.add(lot.slot)
        elif self.standing is not None:
            eligible = [int(slot) for slot, col in self.col_of.items() if bool(np.asarray(derived.elig)[col])]
            orders, rejects = plan_orders(self.standing["target"], self.standing["at"], rows, self.capital,
                                          standing=True, exited=sorted(self.exited), eligible=eligible)
            self.rejects.extend(rejects)
            if orders:
                wanted = self.standing["target"]
                self.pick = {"decided": self.iso[j], "exec": self.iso[j + 1], "at": self.standing["at"], "called": 0,
                             "targets": [[slot, wanted[slot]] for slot in sorted(wanted)], "buys": [], "sells": [],
                             "dropped": [], "budget": book["budget"], "equity": round(book["equity"], 2),
                             "ctx_sha": None}
                self.picks.append(self.pick)
        if self.pick is not None:
            for order in orders:
                if "sell" in order:
                    lot = self.lots[int(order["sell"])]
                    self.pick["sells"].append([lot.lid, lot.slot, self.iso[lot.entry_index]])
                else:
                    self.pick["buys"].append([int(order["buy_id"]), float(order["usd"])])
        self.pending = orders


# --------------------------------------------------------------------------- the result
_EVIDENCE_MODULES = ("__init__", "config", "store", "ctx", "program", "engine", "results", "placebo", "style")


def _code_sha() -> str:
    """The evidence modules' source (this package's): part of every run's identity, as E1's run's `code`."""
    digest = hashlib.sha256()
    here = Path(__file__).resolve().parent
    for name in _EVIDENCE_MODULES:
        digest.update(name.encode() + b"\0" + (here / f"{name}.py").read_bytes() + b"\0")
    return digest.hexdigest()[:24]


def _tables_sha() -> str:
    return results.sha({
        "sleeve": str(config.XS_SLEEVE_USD), "min_name": str(config.MIN_NAME_USD),
        "position_share": str(config.POSITION_SHARE), "risk_weight": str(config.RISK_WEIGHT),
        "names": [config.MIN_NAMES, config.MAX_NAMES, config.MAX_WEIGHT], "caps": [config.MAX_BUYS, config.MAX_SELLS],
        "rung": config.RUNG, "rungs": {k: [[least, list(groups)] for least, groups in v] for k, v in config.RUNGS.items()},
        "cells": [config.MIN_CELL, config.SMALL_CELL, config.CELL_SECTOR, config.CELL_BETA],
        "derive": [config.DERIVE_SESSIONS, config.MIN_VALID, config.MOM_SKIP, config.MOM_BACK, config.MEMBER_AHEAD],
        "stress": [config.STRESS_SPREAD, config.STRESS_FEES], "vanish": [config.VANISH_SESSIONS, config.VANISH_HAIRCUT],
        "rounding": [config.ADJUSTED_HALF_STEP, config.ROUNDING_GUARD],
        "sec": str(_e1.SEC_FEE_PER_MILLION), "taf": [str(_e1.TAF_PER_SHARE), str(_e1.TAF_MAX)],
        "qty_places": _e1.QTY_PLACES, "holds": [_e1.MIN_HOLD_SESSIONS, _e1.FAILED_DECIDES_EXIT],
        "ratio": [_e1_engine.RATIO_TOLERANCE, _e1_engine.SPLIT_MIN_STEP, _e1_engine.SPLIT_RESIDUAL,
                  _e1_engine.SPLIT_TERMS]})[:24]


def _universe_sha(bars: Any) -> str:
    """24 hex over what of the slice's columns names a run beside its data version: the ids, the parent's part of
    eligibility (a half run differs here and nowhere else) and the half-spreads."""
    digest = hashlib.sha256()
    for name, kind in (("ids", np.int64), ("elig0", np.bool_), ("hs", np.float64), ("exit", np.int8)):
        array = np.ascontiguousarray(np.asarray(getattr(bars, name), dtype=kind))
        digest.update(name.encode() + b"\0" + str(array.shape).encode() + b"\0" + array.tobytes() + b"\0")
    digest.update(str(int(bars.ref)).encode())
    return digest.hexdigest()[:24]


def look_spans(bars: Any) -> dict[str, tuple[int, int]] | None:
    """The spans a run's placebos are read on: for the sealed look's run ("look": Validation's first session through
    the holdout) {"V": Validation's sessions, "H": the holdout's (`league.equity.config.LOOK_FIRST` .. `LOOK_CAP`)} as
    session indices of `bars`; None (the run's own sessions, one span "run") for every other window."""
    if getattr(bars, "window", None) != "look":
        return None
    days = [from_ordinal(int(d)) for d in np.asarray(bars.days)]
    first = int(bars.first)
    v_first, v_last = _e1.WINDOWS["validation"]
    spans: dict[str, tuple[int, int]] = {}
    for name, lo, hi in (("V", v_first, v_last), ("H", _e1.LOOK_FIRST, _e1.LOOK_CAP)):
        inside = [i for i in range(first, len(days)) if lo <= days[i] <= hi]
        if inside:
            spans[name] = (inside[0], inside[-1])
    return spans


def _thirds(values: np.ndarray, elig: np.ndarray) -> tuple[np.ndarray, np.ndarray] | None:
    """(the bottom third's columns, the top third's) of `values` among the eligible columns with a finite value,
    ranked ascending by (value, column); None when a third would be empty."""
    cols = np.flatnonzero(elig & np.isfinite(values))
    third = len(cols) // 3
    if third < 1:
        return None
    order = cols[np.lexsort((cols, values[cols]))]
    return order[:third], order[-third:]


def _factors(acct: _Account) -> list[list[Any]]:
    """The House panel factors over the run's days (results' docstring): beside, never a bar."""
    first, n = int(acct.bars.first), acct.n
    _, closes = placebo.prices(acct.bars)
    with np.errstate(invalid="ignore", divide="ignore"):
        move = np.vstack([np.full((1, acct.m), np.nan), closes[1:] / closes[:-1] - 1.0]) if n else closes
    rows = {int(row["t"]): row["derived"] for row in acct.log.decisions}
    sides: dict[str, tuple[np.ndarray, np.ndarray] | None] = {"mom": None, "strev": None, "beta": None}
    out: list[list[Any]] = []
    for j in range(first, n):
        f = j - 1
        if f in rows and (j == first or acct.days[j].month != acct.days[f].month):
            derived = rows[f]
            elig = np.asarray(derived.elig, dtype=bool)
            with np.errstate(invalid="ignore", divide="ignore"):
                week = closes[f] / closes[f - 5] - 1.0 if f >= 5 else np.full(acct.m, np.nan)
            sides = {"mom": _thirds(np.asarray(derived.mom, dtype=np.float64), elig),
                     "strev": _thirds(-week, elig),
                     "beta": _thirds(np.asarray(derived.beta, dtype=np.float64), elig)}
        market = float(move[j, config.MARKET_COLUMN]) if acct.ref > config.MARKET_COLUMN else float("nan")
        row: list[Any] = [acct.iso[j], round(market, 10) if math.isfinite(market) else 0.0]
        for name in ("mom", "strev", "beta"):
            value = 0.0
            if sides[name] is not None:
                low, high = (move[j, cols] for cols in sides[name])
                low, high = low[np.isfinite(low)], high[np.isfinite(high)]
                if low.size and high.size:
                    value = math.fsum(high.tolist()) / high.size - math.fsum(low.tolist()) / low.size
            row.append(round(value, 10))
        out.append(row)
    return out


def _lot_row(acct: _Account, lot: _Lot) -> dict[str, Any]:
    iso, last = acct.iso, acct.n - 1
    exited = lot.exit_index is not None
    return {"lid": lot.lid, "id": lot.slot, "cell": int(lot.row["cell"]),
            "weight": round(float(lot.notional / acct.capital), 8), "decided_day": iso[lot.decided],
            "entry_day": iso[lot.entry_index], "entry_at": lot.entry_at,
            "exit_day": iso[lot.exit_index] if exited else None, "exit_at": lot.exit_at,
            "net": _money(lot.net) if exited else None, "fees": _money(lot.fees), "div": _money(lot.div),
            "hs": float(acct.hs[lot.col, 0 if lot.entry_at == OPEN else 1]),
            "hs_exit": float(acct.hs[lot.col, 0 if lot.exit_at == OPEN else 1]) if exited else None,
            "reason": lot.reason or "open", "tag": lot.tag,
            "held_sessions": (int(lot.exit_index) if exited else last) - lot.entry_index}


def _result(acct: _Account, seconds: float, *, placebos: int, seed: int | None, style: bool) -> dict[str, Any]:
    program, bars, needs = acct.program, acct.bars, acct.needs
    first, n = int(bars.first), acct.n
    run_days = acct.iso[first:]
    capital, k = acct.capital, acct.k
    series = placebo.residual(bars, acct.log, capital=capital, k=k, haircut=acct.haircut)
    sum_x = math.fsum(series["x"].tolist())
    sum_h0 = sum_h1 = sum_x
    if acct.log.lots and acct.vanish[first:].any():
        sum_h0, sum_h1 = (math.fsum(placebo.residual(bars, acct.log, capital=capital, k=k, haircut=h)["x"].tolist())
                          for h in (0.0, 1.0))
    daily = [[run_days[i], float(series["r"][i]), float(series["x"][i]), float(series["x15"][i]),
              float(series["u"][i]), float(series["w"][i]), float(series["bench"][i]), int(series["exits"][i]),
              bool(series["invested"][i]), acct.equity[i]] for i in range(len(run_days))]
    lots = [_lot_row(acct, lot) for lot in sorted([*acct.closed, *acct.lots.values()], key=lambda lot: lot.lid)]
    picks = acct.picks
    beside = {"costs": math.fsum(series["c"].tolist()), "gross": math.fsum(series["g"].tolist()),
              "delta": math.fsum(series["delta"].tolist()), "cells": series["cells"], "vanished": dict(acct.vanished),
              "refused": dict(acct.refused), "sum_x_h0": sum_h0, "sum_x_h1": sum_h1}
    summary = results.summarize(daily, lots, picks, capital, beside=beside)
    summary["open_lots"] = len(acct.lots)
    market = config.MARKET_COLUMN if acct.ref > config.MARKET_COLUMN else None
    has_bar = bool(acct.close_ok[first:, market].any() if market is not None else acct.close_ok[first:].any()) \
        if run_days else False
    status = "disqualified" if acct.runner.disqualified else ("ok" if run_days and has_bar else "no_data")
    identity = {"program_sha": program.sha, "run_sha": program.run_sha, "params": program.params,
                "window": bars.window, "panel": needs.panel, "data_version": bars.data_version,
                "universe": _universe_sha(bars), "engine": XS_ENGINE_VERSION, "code": _code_sha(),
                "tables": _tables_sha(), "rung": series["rung"], **acct.cfg.identity(),
                "start": run_days[0] if run_days else None, "end": run_days[-1] if run_days else None}
    stats = acct.runner.stats()
    result: dict[str, Any] = {
        "run_id": results.sha(identity)[:24], "program": program.name, **identity, "half": None, "trials": 1,
        "status": status, "needs": needs.as_dict(), "summary": summary,
        "by_year": results.by_year(daily, lots, picks), "daily": daily, "lots": lots, "picks": picks,
        "picks_sha": results.sha(picks), "factors": _factors(acct), "actions": acct.actions,
        "runtime": {key: value for key, value in stats.items() if key != "seconds"},
    }
    if int(placebos) > 0:
        draw_seed = placebo.train_seed(program.run_sha, bars.window) if seed is None else int(seed)
        result["placebo"] = placebo.run(bars, acct.log, n=int(placebos), seed=draw_seed, spans=look_spans(bars),
                                        capital=capital, k=k, haircut=acct.haircut)
    if style:
        result["style"] = _style.block(bars, acct.log)
    if acct.runner.disqualified:
        result["reason"] = str(acct.runner.disqualified)
    result["result_sha"] = results.sha(result)
    if acct.calls is not None:
        result["calls"] = acct.calls        # never stored, and outside the result's sha: the restart check's
    result["seconds"] = round(seconds, 3)
    result["runtime"]["decide_seconds"] = stats.get("seconds")
    return result


def run(program: Any, bars: Any, *, cfg: EngineConfig = EngineConfig(), placebos: int = 0,
        calls: bool = False, seed: int | None = None, style: bool = False) -> dict[str, Any]:
    """Replay `program` (a `program.XsProgram`) over `bars` (a `store.PanelBars`) and return the result record
    (`league.xs.results`). `placebos`: also draw that many matched placebos on the run's sessions (`placebo.run`;
    `seed` is the draw's, None: derived from the run's sha) and put their block in `result["placebo"]`. `calls`: also
    return `result["calls"]`, the book facts of every CALLED decision (for the restart check; never stored). `style`:
    also put `league.xs.style.block(bars, log)` in `result["style"]` (the captain's A22: the run's holdings read on
    size, beta, momentum and volatility; ONE call, the rule is package E's)."""
    began = time.perf_counter()
    acct = _Account(program, bars, cfg, keep_calls=bool(calls))
    n, first = acct.n, int(bars.first)
    if first < n:
        for j in range(max(first - 1, 0), n):
            if j >= first:
                acct.session(j)
                acct.mark_close(j)
            if j < n - 1:
                acct.close(j)
    return _result(acct, time.perf_counter() - began, placebos=placebos, seed=seed, style=bool(style))


def run_isolated(program: Any, bars: Any, *, cfg: EngineConfig = EngineConfig(), placebos: int = 0,
                 calls: bool = False, seed: int | None = None, style: bool = False) -> dict[str, Any]:
    """`run`, an exception becoming `results.failed` (status "error")."""
    try:
        return run(program, bars, cfg=cfg, placebos=placebos, calls=calls, seed=seed, style=style)
    except Exception as exc:  # noqa: BLE001 - one program's run ends; the caller sees why
        return results.failed(str(getattr(program, "name", "program")), f"{type(exc).__name__}: {exc}")


__all__ = ["EngineConfig", "Log", "plan_orders", "refused_whole", "ratio_tolerance", "split_of", "look_spans", "run",
           "run_isolated", "ORDER_CAP"]
