"""The equity Gym: a daily-bar replay of one program over one window, with fills at the official open or close.

Owner: core. Inputs are arrays (`store.Bars`), never a path: the same function runs in the decider-isolated child on
the House (Validation, the sealed look, the screen's Train-era runs; amendment A3: no Gym box) and in tests.

THE DAY (amendment A2). The program decides once a session, after the close of t, on `ctx.build(inputs_from_bars(...,
t))`. Its intents execute in session t+1, in this order: (1) open exits, (2) open entries, (3) close exits, (4) close
entries. A fill is `fill_price(official, side, hs, k)`: the official open (or close) of t+1 x (1 + k x hs) for a buy,
x (1 - k x hs) for a sell, hs = `config.half_spread(sym)`, k = `cfg.k` (1.0; 1.5 for the stress twin). Fees on sells:
`config.sell_fees`. An entry's size is `league.equity.sizing.size_entry` (the book's own function: the same caps,
sleeve and cash rule as live; no loss-budget room in the Gym), its quantity floored to `config.QTY_PLACES`.

THE HOUSE'S EXIT RULES, identical live (A8.5): a lot is never sold in the session it was bought (`MIN_HOLD_SESSIONS`;
a close-bought lot may sell at the next open: `config.may_sell`); a lot is held at most `needs.max_hold_sessions`: one
whose `held_sessions` at a decision close (sessions since its entry session; 0 at the entry session's own close) will
reach it by the next open exits at that open (reason "max_hold": `config.max_hold_due`); `config.FAILED_DECIDES_EXIT` sessions of failed decides in a
row (an error, a timeout, a disqualified runner; never a malformed intent) exit every lot at the next open (reason
"house"). In a phase the program's own exits go first, then the House's (a lot both name exits once, as the
program's). An exit with no official price that session waits for the next (the House's rules name it again). The
sleeve's cash is >= 0 after every fill (asserted: an AssertionError is an engine bug, never a program's).

EVERY INTENT IS JUDGED WHEN IT EXECUTES: a buy of a symbol outside NEEDS, a sell of a lot that is not open (closed
earlier, never opened) or was bought in this session, a cancel (the Gym holds no pending order at a decision), an
entry sized to nothing (`size_entry`'s binding) or a missing official price are refused with the reason in the next
`ctx.rejects`.

DIVIDENDS AND SPLITS come through the two series: the cash book holds raw shares at raw prices. At the start of each
session the step of the all/raw close ratio from a symbol's previous bar, g = (all/raw)_prev / (all/raw)_now, names
what happened in between: within the step's tolerance of 1 nothing; a split of factor F where g x F is within
`SPLIT_RESIDUAL` of 1 for a small ratio F = p/q (p, q <= `SPLIT_TERMS`) at least `SPLIT_MIN_STEP` from 1 (shares x F,
entry price / F); what remains below 1 by more than the tolerance, r = g x F, a cash dividend of (1 - r) x the
previous raw close a pre-split share, credited to every lot held at that close (to the cent). THE TOLERANCE
(`ratio_tolerance`) is `RATIO_TOLERANCE` or, when that is more, the vendor's cent rounding of the two adjusted closes
(`config.rounding_bound`, the bound the book's morning audit uses too): the adjustment=all series is rounded to the
cent, so its ratio to the raw close jitters from bar to bar with no event at all, and a split's own step lands a
little above or below its exact factor. With the fixed bound alone the engine read that jitter as dividends (cash
credited) and as anomalies, and took a neighbouring fraction for a split whose step the rounding had pushed above its
factor (the rehearsal on real SIP bars, Oct 11, 2026). A dividend smaller than the rounding of its two closes cannot
be told from it and is not credited. The program sees as-of prices only (`ctx.as_of`).

THE RESULT (`run`), shaped like the options `league.gym.results` record: {run_id, program, program_sha, run_sha,
params, window, symbols, engine, data_version, capital, k, status ("ok" | "disqualified" | "no_data"), needs,
summary, by_year, trades, entry_days, exposure, bh, mte, daily, lots, runtime, result_sha}; `results.view(result,
window)` is what leaves each window. `lots` is the screen's input (league/equity/screen.py `series`): one row a
lot {lid, symbol, class, weight (entry notional / capital), qty, entry_day, entry_at, entry_px, exit_day, exit_at,
exit_px, fees, div, hs, reason, held_sessions} (a lot still open at the run's end has exit_day, exit_at and exit_px
None and reason "open", marked at the last close in `daily`); the House alone ever sees it.

DECISIONS run at the close of every session from the one before the run's first (a history session: its intents
execute on the run's first session) to the one before its last (a decision at the last close could never execute).
ctx at a decision: the open lots marked at that close, the lots closed and the intents refused since the last call,
the sleeve's cash and equity, `budget` = the capital E0 (the sleeve equity entries are sized on), and `caps[sym]` =
max(0, min(position share x E0 - the program's marked value of sym, cash)).
"""

from __future__ import annotations

import hashlib
import math
import time
from dataclasses import dataclass
from decimal import ROUND_DOWN, ROUND_HALF_EVEN, Decimal
from fractions import Fraction
from pathlib import Path
from typing import Any

import numpy as np

from . import EQUITY_ENGINE_VERSION, config, results, sizing
from .ctx import build, closed_row, inputs_from_bars, lot_row
from .store import from_ordinal

OPEN, CLOSE = "open", "close"
#: A ratio step closer to 1 than this is the series' rounding, not an event (the floor of `ratio_tolerance`).
RATIO_TOLERANCE = 2e-5
#: A split moves the all/raw ratio by at least this much (a dividend of a quarter of the price is not a split).
SPLIT_MIN_STEP = 0.2
#: After a split's factor is taken out, what remains is within this of 1 (it is the same day's dividend).
SPLIT_RESIDUAL = 0.15
#: The largest numerator and denominator of a split factor (20-for-1, 1-for-50, 3-for-2 ...).
SPLIT_TERMS = 50
#: The open-risk weights only size live entries against the loss budget; the Gym has no budget (`budget_room` None).
_GYM_WEIGHT = {config.ETF: Decimal("0.20"), config.STOCK: Decimal("0.40")}
_PRICE = Decimal("0.000001")
_QTY = Decimal(1).scaleb(-config.QTY_PLACES)


@dataclass(frozen=True)
class EngineConfig:
    """One run's settings, each part of its identity: `capital` the sleeve E0 (dollars, Decimal), `k` the half-spread
    multiple, `timeout` and `max_errors` the runner's (1 s a call, 25 errors), `budget_seconds` all the run's decide
    calls together (None: no limit)."""

    capital: Decimal = config.SLEEVE_USD
    k: float = config.K_BASE
    timeout: float = 1.0
    max_errors: int = 25
    budget_seconds: float | None = 900.0

    def identity(self) -> dict[str, Any]:
        return {"capital": str(Decimal(str(self.capital))), "k": float(self.k), "timeout": float(self.timeout),
                "max_errors": int(self.max_errors)}


def fill_price(official: float, side: str, hs: float, k: float) -> float:
    """official x (1 + k x hs) for "buy", x (1 - k x hs) for "sell" (ValueError for another side or a price that is not
    a positive finite number). The engine's, the book's twin and league/ops/twins.py's one fill function."""
    if side not in ("buy", "sell"):
        raise ValueError(f"a fill's side is buy or sell, not {side!r}")
    price, hs, k = float(official), float(hs), float(k)
    if not (math.isfinite(price) and price > 0):
        raise ValueError(f"an official price is a positive number, not {official!r}")
    if not (math.isfinite(hs) and hs >= 0 and math.isfinite(k) and k >= 0) or k * hs >= 1:
        raise ValueError("the half-spread and its multiple are small non-negative numbers")
    return price * (1.0 + k * hs) if side == "buy" else price * (1.0 - k * hs)


def official(bars: Any, symbol: str, index: int, at: str) -> float | None:
    """The official raw open (`at` "open") or close ("close") of `symbol` at session `index` of `bars`, None when the
    symbol had no bar (the twins' and the engine's one reader)."""
    if at not in (OPEN, CLOSE):
        raise ValueError(f"'at' is open or close, not {at!r}")
    raw = bars.raw.get(symbol)
    if raw is None or not 0 <= int(index) < raw.shape[0]:
        return None
    value = float(raw[int(index), 0 if at == OPEN else 3])
    return value if math.isfinite(value) and value > 0 else None


def _decimal_price(value: float) -> Decimal:
    return Decimal(f"{value:.6f}")


def ratio_tolerance(adj_prev: float, adj_now: float) -> float:
    """How far from 1 the all/raw ratio's step between two bars may lie and still be the series' rounding:
    `RATIO_TOLERANCE`, or the vendor's cent rounding of the two adjusted closes when that is more
    (`config.rounding_bound`). A close that is no positive finite number has no rounding to allow for."""
    try:
        return max(RATIO_TOLERANCE, config.rounding_bound(adj_prev, adj_now))
    except (TypeError, ValueError):
        return RATIO_TOLERANCE


def split_factor(step: float, tolerance: float = RATIO_TOLERANCE) -> Fraction | None:
    """The split a ratio step g names (`SPLIT_MIN_STEP` ... `SPLIT_TERMS`, the module docstring), or None. `tolerance`:
    the step's own (`ratio_tolerance`): g x F may lie that far above 1 and F still be the factor (the rounding of the
    two adjusted closes; what lies below 1 is the same day's dividend, up to `SPLIT_RESIDUAL`)."""
    if not (math.isfinite(step) and step > 0) or abs(step - 1.0) < SPLIT_MIN_STEP:
        return None
    best: tuple[float, Fraction] | None = None
    for q in range(1, SPLIT_TERMS + 1):
        for p in range(1, SPLIT_TERMS + 1):
            factor = Fraction(p, q)
            if factor == 1 or math.gcd(p, q) != 1:
                continue
            residual = step * float(factor)
            if residual > 1.0 + tolerance or residual < 1.0 - SPLIT_RESIDUAL:
                continue
            gap = abs(1.0 - residual)
            if best is None or gap < best[0]:
                best = (gap, factor)
    return best[1] if best else None


class _Lot:
    __slots__ = ("lid", "symbol", "klass", "qty", "opened_qty", "entry_px", "notional", "entry_index", "entry_at",
                 "hs", "tag", "fees", "div", "mark", "exit_index", "exit_at", "exit_px", "proceeds", "reason")

    def __init__(self, lid: int, symbol: str, klass: str, qty: Decimal, entry_px: Decimal, entry_index: int,
                 entry_at: str, hs: float, tag: str, mark: float):
        self.lid, self.symbol, self.klass = lid, symbol, klass
        self.qty, self.opened_qty, self.entry_px = qty, qty, entry_px
        self.notional = qty * entry_px
        self.entry_index, self.entry_at, self.hs, self.tag = entry_index, entry_at, hs, tag
        self.fees = Decimal(0)
        self.div = Decimal(0)
        self.mark = mark
        self.exit_index: int | None = None
        self.exit_at: str | None = None
        self.exit_px: Decimal | None = None
        self.proceeds = Decimal(0)
        self.reason: str | None = None

    @property
    def net(self) -> Decimal:
        return self.proceeds - self.notional - self.fees + self.div


class _Account:
    """One program's sleeve over one run: its cash, its lots, the intents it is owed, and the daily record."""

    def __init__(self, program: Any, bars: Any, cfg: EngineConfig):
        self.program, self.bars, self.cfg = program, bars, cfg
        self.needs = program.needs
        missing = [s for s in self.needs.symbols if s not in bars.raw or s not in bars.adj]
        if missing:
            raise ValueError(f"the slice lacks {', '.join(missing)} (NEEDS slices the store)")
        self.capital = Decimal(str(cfg.capital))
        if not self.capital > 0:
            raise ValueError("a run's capital is a positive number of dollars")
        self.k = float(cfg.k)
        self.cash = self.capital
        self.lots: dict[int, _Lot] = {}
        self.closed: list[_Lot] = []
        self.next_lid = 1
        self.pending: list[dict[str, Any]] = []
        self.house: dict[int, str] = {}
        self.rejects: list[str] = []
        self.closed_since: list[_Lot] = []
        self.fails = 0
        self.daily: list[list[Any]] = []
        self.equity_prev = self.capital
        self.entry_days: set[str] = set()
        self.actions: list[dict[str, Any]] = []
        self.days = [from_ordinal(int(d)).isoformat() for d in bars.days]
        # The last session index at or before each index with a usable close on both series (the ratio's reader).
        self.prev_valid: dict[str, np.ndarray] = {}
        for sym in self.needs.symbols:
            raw_c, adj_c = bars.raw[sym][:, 3], bars.adj[sym][:, 3]
            ok = np.isfinite(raw_c) & np.isfinite(adj_c) & (raw_c > 0) & (adj_c > 0)
            idx = np.where(ok, np.arange(ok.shape[0]), -1)
            self.prev_valid[sym] = np.maximum.accumulate(idx) if idx.size else idx
        self.runner = program.start(timeout=cfg.timeout, max_errors=cfg.max_errors, budget_seconds=cfg.budget_seconds)

    # ------------------------------------------------------------------ helpers
    def reject(self, text: str) -> None:
        self.rejects.append(text)

    def _assert_cash(self, what: str) -> None:
        assert self.cash >= 0, f"the sleeve's cash went below zero after {what} (an engine bug): {self.cash}"

    def _value(self, *, symbol: str | None = None, prices: dict[str, float] | None = None) -> Decimal:
        total = Decimal(0)
        for lot in self.lots.values():
            if symbol is not None and lot.symbol != symbol:
                continue
            mark = (prices or {}).get(lot.symbol, lot.mark)
            total += lot.qty * _decimal_price(mark)
        return total

    # ------------------------------------------------------------------ a session
    def session(self, j: int) -> None:
        """Execute the last decision's intents in session j: corporate actions first, then (1) open exits, (2) open
        entries, (3) close exits, (4) close entries."""
        self._corporate_actions(j)
        for intent in self.pending:
            if "cancel" in intent:
                self.reject(f"cancel {intent['cancel']}: no pending order (every intent executes in the next session)")
        for at in (OPEN, CLOSE):
            self._exits(j, at)
            self._entries(j, at)
        self.pending = []

    def _corporate_actions(self, j: int) -> None:
        held = sorted({lot.symbol for lot in self.lots.values()})
        for sym in held:
            valid = self.prev_valid[sym]
            if valid[j] != j or j == 0 or valid[j - 1] < 0:
                continue   # no bar today (judged when the next bar comes), or no earlier bar to compare with
            prev = int(valid[j - 1])
            raw_c, adj_c = self.bars.raw[sym][:, 3], self.bars.adj[sym][:, 3]
            step = (adj_c[prev] / raw_c[prev]) / (adj_c[j] / raw_c[j])
            # The vendor rounds the adjusted closes to the cent: the step's own tolerance, for all three readings.
            tolerance = ratio_tolerance(adj_c[prev], adj_c[j])
            if abs(step - 1.0) <= tolerance:
                continue
            factor = split_factor(step, tolerance)
            residual = step * (float(factor) if factor else 1.0)
            per_share = (1.0 - residual) * float(raw_c[prev]) if residual < 1.0 - tolerance else 0.0
            if factor is None and per_share == 0.0:
                self.actions.append({"symbol": sym, "day": self.days[j], "kind": "anomaly", "step": round(step, 8)})
                continue
            dividend = _decimal_price(per_share) if per_share > 0 else Decimal(0)
            for lot in self.lots.values():
                if lot.symbol != sym:
                    continue
                if dividend > 0:
                    cash = (lot.qty * dividend).quantize(config.CENT, rounding=ROUND_HALF_EVEN)
                    lot.div += cash
                    self.cash += cash
                if factor is not None:
                    lot.qty = (lot.qty * factor.numerator / factor.denominator).quantize(_QTY, rounding=ROUND_HALF_EVEN)
                    lot.entry_px = (lot.entry_px * factor.denominator / factor.numerator).quantize(
                        _PRICE, rounding=ROUND_HALF_EVEN)
                    lot.mark = lot.mark * factor.denominator / factor.numerator
            if dividend > 0:
                self.actions.append({"symbol": sym, "day": self.days[j], "kind": "dividend",
                                     "per_share": float(dividend)})
            if factor is not None:
                self.actions.append({"symbol": sym, "day": self.days[j], "kind": "split",
                                     "factor": f"{factor.numerator}:{factor.denominator}"})

    def _sell(self, lot: _Lot, j: int, at: str, reason: str) -> bool:
        price = official(self.bars, lot.symbol, j, at)
        if price is None:
            self.reject(f"sell {lot.lid} ({reason}): no official {at} for {lot.symbol} this session; "
                        "the lot stays open")
            return False
        fill = _decimal_price(fill_price(price, "sell", lot.hs, self.k))
        proceeds = lot.qty * fill
        fees = min(config.sell_fees(proceeds, lot.qty), proceeds)   # a sale never costs more than it brings
        self.cash += proceeds - fees
        self._assert_cash(f"selling lot {lot.lid}")
        lot.exit_index, lot.exit_at, lot.exit_px, lot.proceeds, lot.reason = j, at, fill, proceeds, reason
        lot.fees += fees
        lot.mark = float(fill)
        del self.lots[lot.lid]
        self.closed.append(lot)
        self.closed_since.append(lot)
        return True

    def _exits(self, j: int, at: str) -> None:
        for intent in self.pending:
            if "sell" not in intent or intent["at"] != at:
                continue
            lot = self.lots.get(int(intent["sell"]))
            if lot is None:
                self.reject(f"sell {intent['sell']}: no open lot {intent['sell']}")
            elif not config.may_sell(lot.entry_index, j):
                self.reject(f"sell {lot.lid}: bought this session (a lot never sells in the session it was bought)")
            else:
                self._sell(lot, j, at, "program")
        if at != OPEN:
            return
        for lid, reason in list(self.house.items()):
            lot = self.lots.get(lid)
            if lot is None:
                del self.house[lid]
            elif config.may_sell(lot.entry_index, j) and self._sell(lot, j, at, reason):
                del self.house[lid]

    def _entries(self, j: int, at: str) -> None:
        for intent in self.pending:
            if "buy" not in intent or intent["at"] != at:
                continue
            sym = intent["buy"]
            if sym not in self.needs.symbols:
                self.reject(f"buy {sym}: not one of the program's NEEDS symbols")
                continue
            klass = config.class_of(sym)
            price = official(self.bars, sym, j, at)
            if price is None or klass is None:
                self.reject(f"buy {sym}: no official {at} this session")
                continue
            hs = config.half_spread(sym)
            limit = _decimal_price(fill_price(price, "buy", hs, self.k))
            prices = {sym: price}
            own = self._value(symbol=sym, prices=prices)
            sized = sizing.size_entry(sizing.SizingInputs(
                symbol=sym, klass=klass,
                share=Decimal(str(intent["share"])) if intent.get("share") is not None else None,
                usd=Decimal(str(intent["usd"])) if intent.get("usd") is not None else None,
                limit_price=limit, E=self.capital, sleeve_equity=self.capital, sleeve_free_cash=self.cash,
                sleeve_symbol_value=own, position_share=config.POSITION_SHARE[klass], account_symbol_value=own,
                invested_now=self._value(prices=prices), invested_share=Decimal("1.00"), available_cash=self.cash,
                cash=self.cash, any_short=False, budget_room=None, weight=_GYM_WEIGHT[klass],
                min_order_usd=config.MIN_ORDER_USD))
            qty = Decimal(sized.qty).quantize(_QTY, rounding=ROUND_DOWN) if sized.qty > 0 else Decimal(0)
            if qty <= 0:
                self.reject(f"buy {sym}: sized to nothing ({sized.binding}: {sized.reason})")
                continue
            lot = _Lot(self.next_lid, sym, klass, qty, limit, j, at, hs, str(intent.get("tag") or ""), price)
            self.cash -= lot.notional
            self._assert_cash(f"buying lot {lot.lid}")
            self.lots[lot.lid] = lot
            self.next_lid += 1
            self.entry_days.add(self.days[j])

    # ------------------------------------------------------------------ the close and the decision
    def mark_close(self, j: int) -> None:
        for lot in self.lots.values():
            price = official(self.bars, lot.symbol, j, CLOSE)
            if price is not None:
                lot.mark = price
        value = self._value()
        equity = self.cash + value
        pnl, self.equity_prev = equity - self.equity_prev, equity
        self.daily.append([self.days[j], float(pnl.quantize(config.CENT)), float(equity.quantize(config.CENT)),
                           round(float(value / self.capital), 4)])

    def decide(self, j: int) -> None:
        positions = [lot_row(lid=lot.lid, symbol=lot.symbol, klass=lot.klass, qty=float(lot.qty),
                             entry=float(lot.entry_px), mark=lot.mark, held_sessions=j - lot.entry_index,
                             at=lot.entry_at, tag=lot.tag) for lot in self.lots.values()]
        closed = [closed_row(lid=lot.lid, symbol=lot.symbol, qty=float(lot.qty), entry=float(lot.entry_px),
                             exit=float(lot.exit_px or 0), net=float(lot.net),
                             held_sessions=(j if lot.exit_index is None else int(lot.exit_index)) - lot.entry_index,
                             reason=str(lot.reason),
                             tag=lot.tag) for lot in self.closed_since]
        caps = {}
        for sym in self.needs.symbols:
            room = config.POSITION_SHARE[config.class_of(sym) or config.ETF] * self.capital - self._value(symbol=sym)
            caps[sym] = round(float(max(Decimal(0), min(room, self.cash))), 2)
        inputs = inputs_from_bars(self.bars, j, needs=self.needs, positions=positions, closed=closed,
                                  rejects=self.rejects, cash=float(self.cash), equity=float(self.cash + self._value()),
                                  budget=float(self.capital), caps=caps, params=self.program.params)
        intents = self.runner.decide(build(inputs))
        self.rejects, self.closed_since = [], []
        self.fails = self.fails + 1 if self.runner.last_failed else 0
        self.pending = list(intents)
        for lot in self.lots.values():
            if config.max_hold_due(j - lot.entry_index, self.needs.max_hold_sessions):
                self.house.setdefault(lot.lid, "max_hold")
            if self.fails >= config.FAILED_DECIDES_EXIT:
                self.house[lot.lid] = "house"


# --------------------------------------------------------------------------- the result
_EVIDENCE_MODULES = ("__init__", "config", "store", "program", "ctx", "engine", "results", "sizing")


def _code_sha() -> str:
    """The evidence modules' source (this package's): part of every run's identity, as the options run's `code`."""
    digest = hashlib.sha256()
    here = Path(__file__).resolve().parent
    for name in _EVIDENCE_MODULES:
        digest.update(name.encode() + b"\0" + (here / f"{name}.py").read_bytes() + b"\0")
    return digest.hexdigest()[:24]


def _tables_sha() -> str:
    return results.sha({"universe": config.UNIVERSE, "half_spread_bp": config.HALF_SPREAD_BP,
                        "sec": str(config.SEC_FEE_PER_MILLION), "taf": [str(config.TAF_PER_SHARE), str(config.TAF_MAX)],
                        "position_share": {k: str(v) for k, v in config.POSITION_SHARE.items()},
                        "min_order": str(config.MIN_ORDER_USD), "qty_places": config.QTY_PLACES,
                        "holds": [config.MIN_HOLD_SESSIONS, config.FAILED_DECIDES_EXIT],
                        "ratio": [RATIO_TOLERANCE, SPLIT_MIN_STEP, SPLIT_RESIDUAL, SPLIT_TERMS]})[:24]


def _money(value: Decimal) -> float:
    return float(value.quantize(config.CENT, rounding=ROUND_HALF_EVEN))


def _trade(acct: _Account, lot: _Lot) -> dict[str, Any]:
    days = acct.days
    notional = lot.notional
    return {"id": lot.lid, "symbol": lot.symbol, "class": lot.klass, "day": days[lot.entry_index],
            "entry_day": days[lot.entry_index], "entry_at": lot.entry_at, "entry_px": float(lot.entry_px),
            "exit_day": days[lot.exit_index] if lot.exit_index is not None else None, "exit_at": lot.exit_at,
            "exit_px": float(lot.exit_px) if lot.exit_px is not None else None, "qty": float(lot.qty),
            "notional": _money(notional), "fees": _money(lot.fees), "div": _money(lot.div), "net": _money(lot.net),
            "pnl": _money(lot.net), "return": round(float(lot.net / notional), 8) if notional > 0 else None,
            "held_sessions": int(lot.exit_index) - lot.entry_index if lot.exit_index is not None else None,
            "reason": lot.reason, "tag": lot.tag}


def _lot(acct: _Account, lot: _Lot) -> dict[str, Any]:
    days, last = acct.days, acct.bars.n - 1
    return {"lid": lot.lid, "symbol": lot.symbol, "class": lot.klass,
            "weight": round(float(lot.notional / acct.capital), 8), "qty": float(lot.qty),
            "entry_day": days[lot.entry_index], "entry_at": lot.entry_at, "entry_px": float(lot.entry_px),
            "exit_day": days[lot.exit_index] if lot.exit_index is not None else None, "exit_at": lot.exit_at,
            "exit_px": float(lot.exit_px) if lot.exit_px is not None else None, "fees": _money(lot.fees),
            "div": _money(lot.div), "hs": lot.hs, "reason": lot.reason or "open",
            "held_sessions": (int(lot.exit_index) if lot.exit_index is not None else last) - lot.entry_index}


def _result(acct: _Account, seconds: float) -> dict[str, Any]:
    program, bars, needs = acct.program, acct.bars, acct.needs
    first, n = int(bars.first), bars.n
    run_days = acct.days[first:]
    closed = sorted(acct.closed, key=lambda lot: (lot.exit_index, lot.lid))
    trades = [_trade(acct, lot) for lot in closed]
    before = acct.days[first - 1] if first > 0 else "before"
    closes: dict[str, list[float]] = {}
    opens: dict[str, list[float]] = {}
    for sym in needs.symbols:
        for into, column in ((opens, 0), (closes, 3)):
            col = bars.adj[sym][:, column]
            series = [float(col[first - 1]) if first > 0 else float("nan")] + [float(x) for x in col[first:]]
            into[sym] = [x if math.isfinite(x) and x > 0 else float("nan") for x in series]
    bh_days = [before, *run_days]
    if run_days:
        for trade, excess in zip(trades, results.excess_returns(trades, closes, bh_days, opens)):
            trade["excess"] = None if excess is None else round(excess, 8)
    summary = results.summarize(trades, acct.daily, acct.capital)
    summary["open_lots"] = len(acct.lots)
    yearly = results.by_year(trades, acct.daily)
    bh = results.buy_and_hold(acct.daily, closes, acct.capital) if run_days else \
        {"pnl": 0.0, "by_year": {}, "exposure": 0.0, "basket_return": 0.0}
    for year, row in yearly.items():
        row["bh_pnl"] = bh["by_year"].get(year, 0.0)
    has_bar = all(bool(np.isfinite(bars.raw[s][first:, 3]).any()) for s in needs.symbols) if run_days else False
    status = "disqualified" if acct.runner.disqualified else ("ok" if run_days and has_bar else "no_data")
    identity = {"program_sha": program.sha, "run_sha": program.run_sha, "params": program.params,
                "symbols": list(needs.symbols), "window": bars.window, "data_version": bars.data_version,
                "engine": EQUITY_ENGINE_VERSION, "code": _code_sha(), "tables": _tables_sha(), **acct.cfg.identity(),
                "start": run_days[0] if run_days else None, "end": run_days[-1] if run_days else None}
    stats = acct.runner.stats()
    result = {
        "run_id": results.sha(identity)[:24], "program": program.name, **identity, "trials": 1, "status": status,
        "needs": needs.as_dict(), "summary": summary, "by_year": yearly, "trades": trades,
        "entry_days": sorted(acct.entry_days),
        "exposure": {"mean": summary["exposure_mean"], "by_year": {y: r["exposure_mean"] for y, r in yearly.items()}},
        "bh": bh,
        "mte": results.mte(trades, closes, days=bh_days, opens=opens) if run_days else
        {"mean": None, "t": None, "n": 0},
        "daily": acct.daily, "lots": [_lot(acct, lot) for lot in sorted([*acct.closed, *acct.lots.values()],
                                                                         key=lambda lot: lot.lid)],
        "actions": acct.actions, "runtime": {k: v for k, v in stats.items() if k != "seconds"},
    }
    if acct.runner.disqualified:
        result["reason"] = str(acct.runner.disqualified)
    result["result_sha"] = results.sha(result)
    result["seconds"] = round(seconds, 3)
    result["runtime"]["decide_seconds"] = stats["seconds"]
    return result


def run(program: Any, bars: Any, *, cfg: EngineConfig = EngineConfig()) -> dict[str, Any]:
    """Replay `program` (a `program.EquityProgram`) over the run sessions of `bars` (a `store.Bars`: from `bars.first`
    to its last session; earlier rows are history only). Returns the result (the module docstring); deterministic: the
    same inputs give the same `result_sha`."""
    began = time.perf_counter()
    acct = _Account(program, bars, cfg)
    n, first = bars.n, int(bars.first)
    if first < n:
        for j in range(max(first - 1, 0), n):
            if j >= first:
                acct.session(j)
                acct.mark_close(j)
            if j < n - 1:
                acct.decide(j)
    return _result(acct, time.perf_counter() - began)


def run_isolated(program: Any, bars: Any, *, cfg: EngineConfig = EngineConfig()) -> dict[str, Any]:
    """`run`, with an exception that ends the run turned into `results.failed(program.name, why)` (no trial)."""
    try:
        return run(program, bars, cfg=cfg)
    except Exception as exc:  # noqa: BLE001 - one program's run ends; the caller sees why
        return results.failed(str(getattr(program, "name", "program")), f"{type(exc).__name__}: {exc}")


__all__ = ["EngineConfig", "fill_price", "run", "run_isolated", "official", "split_factor", "ratio_tolerance", "RATIO_TOLERANCE",
           "SPLIT_MIN_STEP", "SPLIT_RESIDUAL", "SPLIT_TERMS"]
