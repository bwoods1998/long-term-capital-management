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
import hashlib
import math
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
    named XL*; defensive: TLT, GLD; stocks: class "stock"); () for a group with none (it has no control). The group of
    a symbol is `elane_train.symbols_group`'s, the rule the registry's `ugroup` and the Train map's cells are made by."""
    from ..equity import config
    from ..swarm import elane_train

    if group not in elane_train.GROUPS or isinstance(universe, (str, bytes)):
        return ()
    names = {str(s).strip().upper() for s in universe}
    return tuple(sym for sym in config.UNIVERSE if sym in names and elane_train.symbols_group([sym]) == group)


def u(group: str, n: int, i: int, j: int) -> float:
    """The counter hash in [0, 1): `int.from_bytes(sha256(f"fwd-control-1|{group}|{n}|{i}|{j}".encode()).digest()[:8],
    "big") / 2**64`."""
    digest = hashlib.sha256(f"{VERSION}|{group}|{int(n)}|{int(i)}|{int(j)}".encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2 ** 64


def _whole(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"a control's {name} is a whole number: {value!r}")
    return value


def spec(group: str, n: int, symbols: Sequence[str]) -> dict[str, Any]:
    """A control's spec: {"control": VERSION, "group", "n", "f" (`F_GRID[n // 10]`), "symbols"}. Its registry `code`
    is `results.canonical(spec(...))`. ValueError for an n outside 0..`10 * len(F_GRID) - 1` or with no symbol."""
    n = _whole(n, "n")
    if not 0 <= n < 10 * len(F_GRID):
        raise ValueError(f"a control's n is 0 to {10 * len(F_GRID) - 1}: {n}")
    names = [str(s) for s in symbols] if not isinstance(symbols, (str, bytes)) else []
    if not names:
        raise ValueError("a control trades its group's symbols: none given")
    return {"control": VERSION, "group": str(group), "n": n, "f": F_GRID[n // 10], "symbols": names}


def control_lots(spec: Mapping[str, Any], sessions: Sequence[dt.date], *, k: float = 1.0) -> list[dict[str, Any]]:
    """THE DRAW (the module docstring) over `sessions` (`sessions[0]` is `first_close`): the control's lot rows, in lid
    order. `k` 1.0 leaves `"hs": None` (the screen's own half-spread); `k` 1.5 fills `hs` with `config.K_STRESS *
    config.half_spread(symbol)` for the stress series; `k` 0.0 fills `"hs": 0.0`. Deterministic; reads no price.

    The last session decides nothing here: its lots enter at a session that does not exist yet, and appear, the same,
    the night it does (a longer `sessions` only ever adds lots and closes open ones). A lot's `seq` counts its slot's
    lots from 1. ValueError for a spec of another version, a symbol outside `config.UNIVERSE` or a k below zero."""
    from ..equity import config

    if spec.get("control") != VERSION:
        raise ValueError(f"not a {VERSION} control: {spec.get('control')!r}")
    group, n = str(spec["group"]), _whole(spec["n"], "n")
    symbols = [str(s) for s in spec["symbols"]]
    if not 0 <= n < 10 * len(F_GRID) or not symbols:
        raise ValueError("a control names its n on the exposure grid and at least one symbol")
    classes = {}
    for sym in symbols:
        if config.class_of(sym) is None:
            raise ValueError(f"a control's {sym} is outside the lane's universe")
        classes[sym] = config.class_of(sym)
    k = float(k)
    if not (math.isfinite(k) and k >= 0.0):
        raise ValueError(f"k is a half-spread multiple, at least 0: {k!r}")
    days = [day if isinstance(day, dt.date) else dt.date.fromisoformat(str(day)[:10]) for day in sessions]
    f = F_GRID[n // 10]
    p = min(1.0, f / (MEAN_HOLD * (1.0 - f)))
    low, high = HOLD
    lots: list[dict[str, Any]] = []
    held: list[tuple[str, float, int] | None] = [None] * SLOTS      # a slot's lot: (symbol, weight, exit index)
    count = [0] * SLOTS
    for i in range(len(days) - 1):
        for slot in range(SLOTS):
            if held[slot] is not None and held[slot][2] > i:           # type: ignore[index]
                continue                                                # the slot holds a lot past this close
            held[slot] = None
            if not u(group, n, i, 4 * slot) < p:
                continue
            sym = symbols[min(int(math.floor(u(group, n, i, 4 * slot + 1) * len(symbols))), len(symbols) - 1)]
            entry_at = "open" if u(group, n, i, 4 * slot + 2) < 0.5 else "close"
            hold = low + min(int(math.floor(u(group, n, i, 4 * slot + 3) * (high - low + 1))), high - low)
            cap = float(config.POSITION_SHARE[classes[sym]])
            omega = min(0.25, cap)
            others = math.fsum(lot[1] for other, lot in enumerate(held)
                               if other != slot and lot is not None and lot[0] == sym and lot[2] > i)
            if omega + others > cap + 1e-12:
                continue                                                # the class cap: the slot stays flat this session
            e = i + 1
            x = e + hold
            held[slot] = (sym, omega, x)
            count[slot] += 1
            lots.append({"lid": 1000 * slot + count[slot], "symbol": sym, "class": classes[sym], "weight": omega,
                         "entry_day": days[e].isoformat(), "entry_at": entry_at,
                         "exit_day": days[x].isoformat() if x < len(days) else None, "exit_at": "open",
                         "hs": None if k == 1.0 else k * config.half_spread(sym)})
    return sorted(lots, key=lambda lot: lot["lid"])


def cost_free(lots0: Sequence[Mapping[str, Any]], bars: Any, *, capital: Any) -> Any:
    """D5's r0 (a float64 ndarray over the run sessions of `bars`): the `r` of `screen.series(lots0, bars,
    universe=list(bars.symbols), capital=capital)` for the `"hs": 0.0` lots (the benchmark does not enter r), plus on
    each exit session the fee that series charged for the lot: `float(config.sell_fees(Decimal(str(omega)) * E0,
    Decimal(str(omega * float(E0) / p_entry)))) / float(E0)`, p_entry the lot's adjusted open or close on its entry
    day. Costs only subtract: a control's net r is at or below its r0 on every session.

    ValueError for a lot whose `hs` is not 0.0 (the series would not be cost-free), and as `screen.series` raises it."""
    from decimal import Decimal

    import numpy as np

    from ..equity import config, screen

    for lot in lots0:
        if lot.get("hs") is None or float(lot["hs"]) != 0.0:
            raise ValueError(f"lot {lot.get('lid')}: the cost-free series is drawn at k 0.0 (hs 0.0), not {lot.get('hs')!r}")
    series = screen.series(lots0, bars, universe=list(bars.symbols), capital=capital)
    r0 = np.array(series.r, dtype=np.float64)
    e0 = float(capital)
    e0_dec = Decimal(str(capital))
    lo = int(bars.first)
    where = {int(day): index for index, day in enumerate(np.asarray(bars.days, dtype=np.int32))}
    for lot in lots0:
        if lot.get("exit_day") in (None, ""):
            continue
        e, x = where[screen._ordinal(lot["entry_day"])], where[screen._ordinal(lot["exit_day"])]
        if x < lo:
            continue
        adj = np.asarray(bars.adj[lot["symbol"]], dtype=np.float64)
        p_entry = float(adj[e, 0] if (lot.get("entry_at") or "open") == "open" else adj[e, 3])
        omega = float(lot["weight"])
        r0[x - lo] += float(config.sell_fees(Decimal(str(omega)) * e0_dec, Decimal(str(omega * e0 / p_entry)))) / e0
    return r0


__all__ = ["VERSION", "SLOTS", "F_GRID", "MEAN_HOLD", "HOLD", "group_symbols", "u", "spec", "control_lots",
           "cost_free"]
