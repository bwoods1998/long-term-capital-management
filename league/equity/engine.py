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
a close-bought lot may sell at the next open); a lot held `needs.max_hold_sessions` sessions exits at the next open
(reason "max_hold"); `config.FAILED_DECIDES_EXIT` sessions of failed decides in a row (an error, a timeout) exit every
lot at the next open (reason "house"). The sleeve's cash is >= 0 after every fill (asserted: an AssertionError is an
engine bug, never a program's).

DIVIDENDS AND SPLITS come through the two series: the cash book holds raw shares at raw prices, credits a dividend on
the ex-date from the all/raw ratio's step, and scales shares at a split (the raw/all ratio's jump); the program sees
as-of prices only (`ctx.as_of`).

THE RESULT (`run`), shaped like the options `league.gym.results` record: {run_id, program, program_sha, run_sha,
params, window, symbols, engine, data_version, capital, k, status ("ok" | "disqualified" | "no_data"), needs,
summary, by_year, trades, entry_days, exposure, bh, mte, daily, lots, runtime, result_sha}; `results.view(result,
window)` is what leaves each window. `lots` is the screen's input (league/equity/screen.py `series`): one row a
lot {lid, symbol, class, weight (entry notional / capital), qty, entry_day, entry_at, entry_px, exit_day, exit_at,
exit_px, fees, div, hs, reason, held_sessions}; the House alone ever sees it.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from . import config


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


def fill_price(official: float, side: str, hs: float, k: float) -> float:
    """official x (1 + k x hs) for "buy", x (1 - k x hs) for "sell" (ValueError for another side or a price that is not
    a positive finite number). The engine's, the book's twin and league/ops/twins.py's one fill function."""
    raise NotImplementedError("core: league/equity/engine.py fill_price")


def run(program: Any, bars: Any, *, cfg: EngineConfig = EngineConfig()) -> dict[str, Any]:
    """Replay `program` (a `program.EquityProgram`) over the run sessions of `bars` (a `store.Bars`: from `bars.first`
    to its last session; earlier rows are history only). Returns the result (the module docstring); deterministic: the
    same inputs give the same `result_sha`."""
    raise NotImplementedError("core: league/equity/engine.py run")


def run_isolated(program: Any, bars: Any, *, cfg: EngineConfig = EngineConfig()) -> dict[str, Any]:
    """`run`, with an exception that ends the run turned into `results.failed(program.name, why)` (no trial)."""
    raise NotImplementedError("core: league/equity/engine.py run_isolated")


def official(bars: Any, symbol: str, index: int, at: str) -> float | None:
    """The official raw open (`at` "open") or close ("close") of `symbol` at session `index` of `bars`, None when the
    symbol had no bar (the twins' and the engine's one reader)."""
    raise NotImplementedError("core: league/equity/engine.py official")


__all__ = ["EngineConfig", "fill_price", "run", "run_isolated", "official"]

