"""The panel's daily replay: the KEEP rule's orders, E1's fills, fees and sizing, the House exits, the holdings log.

Owner: package D. STEP 0 STUB: `EngineConfig` is the contract; everything else raises NotImplementedError until D lands.

ONE SESSION. At the close of t the House exits are planned (below, `ctx.ineligible` included) and, on a decision day
(`config.decision_due`), the program is called on `ctx.build(ctx.inputs_from_panel(bars, t, ...))` and its target
planned (`plan_orders`); on every other close the STANDING target's buys are planned. In t + 1: open exits, open
entries, close exits, close entries (E1's order), at E1's own functions, imported, never copied:
`league.equity.engine.fill_price(official, side, hs, k)` with hs = `bars.hs[col, 0 | 1]`, `league.equity.config
.sell_fees`, `league.equity.sizing.size_entry` (class "stock", the sleeve `cfg.capital`, `config.POSITION_SHARE`,
`config.RISK_WEIGHT`, no budget room, `config.MIN_NAME_USD`), `league.equity.config.may_sell` and `max_hold_due`, and
splits and dividends by `league.equity.engine.split_factor` on the adj/raw ratio step, each step read with
`config.rounding_bound` (the vendor's cents). Sleeve cash >= 0 after every fill (asserted). Deterministic: the same
inputs give the same `result_sha`. There is no state reset inside a run.

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
replaces it (a hold, a None or a malformed answer leaves it standing). At every close where the program is NOT called,
`plan_orders(standing, at, lots, budget, standing=True, exited=...)` plans BUYS ONLY: the standing target's ids that
are eligible at this close and have no open lot, no buy pending and no House exit since the target was set
(`exited`), each for w x budget when that is >= `min_order`; never a sell, no program code. Such a buy is a lot with
its own decision day (the close it was planned at): its cell and its placebo counterparts are that day's.

THE HOUSE EXITS (the pre-registration's C6, 3.5 and 5.5; the Gym and live alike), at the next open: a lot at its
`max_hold_sessions` ("max_hold"); every lot after `league.equity.config.FAILED_DECIDES_EXIT` failed CALLED decides
("house"); a lot whose name is not in U(t) at ANY close, called or not ("house", tag "ineligible"). A lot the House
exits goes at the open whatever the target planned for it. VANISHED: a held name with no valid bar on
`config.VANISH_SESSIONS` sessions in a row is closed on the last of them, no fee, reason "vanished", at its last valid
close x (1 - `cfg.haircut`), whatever way its spell ended (the kinds are counted in `summary.vanished`, with the
sensitivity at haircut 0 and 1). ENTRY VALIDITY (the pre-registration's 5.3): a buy needs a valid open and close of
its name at the fill session and a valid close the session after, else it is not opened (the reject "no bar").

THE HOLDINGS LOG (`Log`; the pre-registration's C7) is what `placebo.residual` and `placebo.run` read, with the bars
and nothing else: for every lot its column, weight (entry notional / capital), decision session, entry session and
point, exit session and point (if any), reason, hs at both points, and its CELL: the cell id and the member columns of
the name's cell at the decision close (`ctx.derive`), less the members that fail entry validity at the entry session.
It never leaves the child.

Evidence module (in the xs identity; one of its roots).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Mapping, Sequence

from . import config

_STUB = "league.xs.engine is a Step 0 stub: package D builds it (league/xs/E4_INTERFACES.md)"


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
    reason, hs_open, hs_close, cell, members (int32 columns, ascending id)}; `decisions`: rows {t, called, derived}."""

    __slots__ = ("lots", "decisions")

    def __init__(self) -> None:
        raise NotImplementedError(_STUB)


def plan_orders(target: Mapping[int, float], at: str, lots: Sequence[Mapping[str, Any]], budget: Any, *,
                min_order: Decimal = config.MIN_NAME_USD, max_buys: int = config.MAX_BUYS,
                max_sells: int = config.MAX_SELLS, standing: bool = False,
                exited: Sequence[int] = ()) -> tuple[list[dict[str, Any]], list[str]]:
    """THE KEEP RULE (the module docstring): (orders, rejects) of a valid `target` {id: w} at fill point `at`, given
    the open `lots` (rows {lid, id, pending (a buy of the id is working)}) and the sleeve's `budget` dollars. With
    `standing` the buys of the standing target and nothing else, skipping the ids of `exited`. Pure: no clock, no
    store, no program code; the same function in the engine and in the live child."""
    raise NotImplementedError(_STUB)


def run(program: Any, bars: Any, *, cfg: EngineConfig = EngineConfig(), placebos: int = 0,
        calls: bool = False, seed: int | None = None, style: bool = False) -> dict[str, Any]:
    """Replay `program` (a `program.XsProgram`) over `bars` (a `store.PanelBars`) and return the result record
    (`league.xs.results`). `placebos`: also draw that many matched placebos on the run's sessions (`placebo.run`;
    `seed` is the draw's, None: derived from the run's sha) and put their block in `result["placebo"]`. `calls`: also
    return `result["calls"]`, the book facts of every CALLED decision (for the restart check; never stored). `style`:
    also put `league.xs.style.block(bars, log)` in `result["style"]` (the captain's A22: the run's holdings read on
    size, beta, momentum and volatility; ONE call, the rule is package E's)."""
    raise NotImplementedError(_STUB)


def run_isolated(program: Any, bars: Any, *, cfg: EngineConfig = EngineConfig(), placebos: int = 0,
                 calls: bool = False, seed: int | None = None, style: bool = False) -> dict[str, Any]:
    """`run`, an exception becoming `results.failed` (status "error")."""
    raise NotImplementedError(_STUB)


__all__ = ["EngineConfig", "Log", "plan_orders", "run", "run_isolated"]
