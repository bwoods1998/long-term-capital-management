"""THE SKILL-FREE CONTROLS of the forward record (release E3, D5): a lot list drawn by a counter hash, never by a price.

Owner: A (league/ops/E3_INTERFACES.md). Protected. A control (g, n) is a base group g of `elane_train.GROUPS` and a
number n in 0..`controls_per_group` - 1. Its lots are a PURE FUNCTION of (g, n, its symbols, the sessions): the draw
reads no bar, price, event or ctx, so it has no skill by construction. It trades only its group's symbols under a
program's position caps, fill points, half-spreads, fees and minimum hold, on an exposure grid spanning the feasible
range; it is NOT matched to any program's turnover, which is why every comparison with the controls reads its
COST-FREE series (`cost_free`).

THE DRAW (`control_lots`), on sessions S[0] = `first_close`, S[1] = `first_day`, ...:
- `symbols = group_symbols(g, universe)`; `f = F_GRID[n // 10]`; `p = min(1.0, f / (MEAN_HOLD * (1 - f)))`;
  `omega = min(0.25, float(config.POSITION_SHARE[class]))`;
- `u(g, n, i, j) = int.from_bytes(sha256(f"fwd-control-1|{g}|{n}|{i}|{j}".encode()).digest()[:8], "big") / 2**64`;
- at each decision index i >= 0, for slot k = 0..`SLOTS` - 1 in order, when the slot is flat (no lot, or its lot's exit
  index x <= i): enter iff `u(g,n,i,4k) < p`; symbol = `symbols[floor(u(g,n,i,4k+1) * len(symbols))]`; `entry_at` =
  "open" if `u(g,n,i,4k+2) < 0.5` else "close"; `H = 1 + floor(u(g,n,i,4k+3) * 20)` (uniform over `HOLD`); entry
  index e = i + 1; exit index x = e + H; `exit_at` = "open";
- the entry is skipped (the slot stays flat that session) when omega plus the weight of the other slots' lots in that
  symbol with x > i (those entered at this same i included) would exceed `config.POSITION_SHARE[class]`;
- a lot whose x is past the last session is open. Lot row: {"lid": 1000 * k + seq, "symbol", "class", "weight":
  omega, "entry_day": S[e], "entry_at", "exit_day": S[x] | None, "exit_at": "open", "hs": None}.

ITS SERIES (league/ops/forward_shadow.py `controls`): `screen.series` of the lots on `bars(symbols, "forward",
history=1, start=first_day)` with capital `config.SLEEVE_USD`; `r15` from the same lots with `"hs": config.K_STRESS *
config.half_spread(symbol)`. THE COST-FREE SERIES r0 (`cost_free`): the r of `screen.series` on the same lots with
`"hs": 0.0`, plus, on each exit session, the fee that series charged for the lot (`"hs": 0.0` alone would leave the
SEC and TAF fees, each rounded up to a cent); x0 = r0 - w * b.

Standard library and numpy only (numpy inside functions).
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Mapping, Sequence

VERSION = "fwd-control-1"
#: Lots a control may hold at once.
SLOTS = 4
#: The exposure grid: controls 0-9 of a group aim at the first, 10-19 at the second, ...
F_GRID = (0.10, 0.25, 0.50, 0.75, 0.95)
#: The mean hold in sessions of a uniform draw over `HOLD` (the entry probability's denominator).
MEAN_HOLD = 10.5
#: A lot's hold in sessions, the shortest and the longest (drawn uniformly: 1..20).
HOLD = (1, 20)


def group_symbols(group: str, universe: Sequence[str]) -> tuple[str, ...]:
    """The `universe` symbols of a base group, in `config.UNIVERSE` order (index: `config.INDEX_ETFS`; sectors: ETFs
    named XL*; defensive: TLT, GLD; stocks: class "stock"); () for a group with none (it has no control)."""
    raise NotImplementedError("A: league/ops/forward_controls.py group_symbols")


def u(group: str, n: int, i: int, j: int) -> float:
    """The counter hash in [0, 1): `int.from_bytes(sha256(f"fwd-control-1|{group}|{n}|{i}|{j}".encode()).digest()[:8],
    "big") / 2**64`."""
    raise NotImplementedError("A: league/ops/forward_controls.py u")


def spec(group: str, n: int, symbols: Sequence[str]) -> dict[str, Any]:
    """A control's spec: {"control": VERSION, "group", "n", "f" (`F_GRID[n // 10]`), "symbols"}. Its registry `code`
    is `results.canonical(spec(...))`."""
    raise NotImplementedError("A: league/ops/forward_controls.py spec")


def control_lots(spec: Mapping[str, Any], sessions: Sequence[dt.date], *, k: float = 1.0) -> list[dict[str, Any]]:
    """THE DRAW (the module docstring) over `sessions` (`sessions[0]` is `first_close`): the control's lot rows, in
    lid order. `k` 1.0 leaves `"hs": None` (the screen's own half-spread); `k` 1.5 fills `hs` with `config.K_STRESS *
    config.half_spread(symbol)` for the stress series; `k` 0.0 fills `"hs": 0.0`. Deterministic; reads no price."""
    raise NotImplementedError("A: league/ops/forward_controls.py control_lots")


def cost_free(lots0: Sequence[Mapping[str, Any]], bars: Any, *, capital: Any) -> Any:
    """D5's r0 (a float64 ndarray over the run sessions of `bars`): the `r` of `screen.series(lots0, bars,
    universe=list(bars.symbols), capital=capital)` for the `"hs": 0.0` lots (the benchmark does not enter r), plus on
    each exit session the fee that series charged for the lot: `float(config.sell_fees(Decimal(str(omega)) * E0,
    Decimal(str(omega * float(E0) / p_entry)))) / float(E0)`, p_entry the lot's adjusted open or close on its entry
    day. Costs only subtract: a control's net r is at or below its r0 on every session."""
    raise NotImplementedError("A: league/ops/forward_controls.py cost_free")


__all__ = ["VERSION", "SLOTS", "F_GRID", "MEAN_HOLD", "HOLD", "group_symbols", "u", "spec", "control_lots",
           "cost_free"]
