"""FWD1-R, THE FORWARD SCREEN's rule (the captain's A33: adopted exactly as its review wrote it), pure: the pin, the bar,
the statistic, the own floor, the haircut and the sentence beside a trade. No store, no file but the repository's
policy.json, no clock.

Owner: the FWD1-R build (league/ops/forward_screen.py is its job). Protected (league/ops/ is FORBIDDEN to every role):
the judge is never a role's to move. Ops only: no module of league/swarm, league/equity, league/live or league/gym
imports it (the swarm reads the job's permit file of ids and words, league/swarm/elane_forward.py).

THE RULE (FWD1-R, the review's section 4, with every defect's fix):
1. WHO. A LINEAGE of the forward registry (league/ops/forward_db.py `fwd_registry.lineage`), judged on ONE program,
   its REPRESENTATIVE: of the lineage's rows whose `first_day` is the lineage's earliest (the rows that existed before
   any forward day of the lineage could), the lowest pid whose reason is train_pass, seed or live, else the lowest pid
   (`representative`). TYPE: "PANEL" (a panel row: `forward_xs.is_panel`) or "ETF" (a family of structure "etf").
   CASE, read at FWD1_START: "N" when no version of the lineage ever reached a sealed pre-check (an S1, S2 or XS1
   Validation try, its pre-check, or a look); a PANEL lineage that reached XS1's is case "XS1"; an ETF lineage that
   reached any is NOT judged (no forward verdict for an S1/S2 look: the review's F3). A case-N lineage takes no sealed
   look afterwards (league/swarm/elane_forward.py refuses its Validation try while the seat switch is on; a pending
   lineage that reached one anyway is VOID, never judged further).
2. DAYS. The counted rows of `fwd_days` (status "ok", no `audit_mismatch` event: `forward_db.counted_days`) of the
   representative under ONE engine id, from FWD1_START = max(its first_day, the first session after the receipt's
   pin: `start_after`).
3. SERIES (`series`). ETF: r and r15, where `fwd_ll` has a row its live-like re-price r_ll in place of r (and
   r15 + (r_ll - r) in place of r15: the stress series is the same fills less 1.5 times the spread); PANEL: the
   residual x = r - w b and x15 = r15 - w b. Each day less g x sides (the weights of the shadow's lots entering or
   exiting that session). g (`haircut_bp`): ETF 2 bp a side, raised to the measured mean adverse gap a side of the
   closed live ETF lots (`fwd_lotgap.side_gap_bp`), rounded up; PANEL 3 bp until 20 live panel lots are measured, then
   the larger of 2 bp and their measured mean adverse gap, rounded up.
4. STATISTIC (`checkpoint`). t_k = mean / sd (ddof 1) x sqrt(k) over the first k counted days, summed by math.fsum,
   at k in `PLAN`; S_k and S15_k the fsums. pass_k: t_k >= c_used, S_k > 1e-12 and S15_k > 1e-12; PANEL also the
   PLACEBO LEG: of 999 matched placebo portfolios (XS1's law) at most 119 have t >= t_k (`placebo_holds`). PASS at the
   first checkpoint that passes; FAIL for good when none has by 60. One verdict per lineage, written once.
5. BAR (`c_used`). c_used = max(c_G, c_own + 0.05) on the 0.01 grid; above 5.00 (or no own floor) the lineage is
   ineligible (no verdict, stated). c_G: PANEL N 2.06, PANEL XS1 3.16 (E3's D2 3% kept beside the look's 12%), ETF N
   2.61. c_own (`own_floor_k`): the study's exact own floor at cap 0.12 (case N) or 0.024 (case XS1) on the program's
   Train-era 60-session windows (the study's fwdcore.own_floor_k, to the integer: the conformance vectors).
6. LIMITS. At most one live forward seat per mechanism cell at a time (league/swarm/elane_forward.py); FGS (E3's
   20/60/120/250 at 3%) is never also applied to a lineage FWD1 judges; nothing judges a lineage after its FWD1 fail;
   the beside line carries the program's own drift-kept rate (ETF), the WEAK flag (ETF always; PANEL at k <= 10), the
   registry's expected zero-edge passes against the observed, and "contamination zero by construction for the judged
   sessions" (`beside`).

THE PIN (`pin`, `load`): policy.json `elane.screens.forward` of the REPOSITORY (never the box's swarm.json: a judge is
pinned by a reviewed pull request), {"name": "FWD1", "screen": "FWD1-R", "receipt_sha256", "plan", "c_G",
"c_margin", "haircut_bp", "haircut_floor_bp", "panel_lots", "own_cap", "placebo", "owner_wall", "figures"}. `load`
refuses (None, why): a missing or malformed key, a sha that is not 64 hex characters, a plan, bar, margin, haircut,
cap or placebo law other than this code's (an off-grid bar is one), a figure block that misses a type and case. CI
holds the sha to docs/benchmarks/forward_screen_fwd1.json and every figure to the receipt's
(league/tests/test_fwd1_rule.py). NO PIN, NO VERDICT: the forward record keeps recording, nothing is judged.

Standard library at import; numpy inside the functions that read arrays.
"""

from __future__ import annotations

import datetime as dt
import math
import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

NAME = "FWD1"
SCREEN = "FWD1-R"
#: policy.json `elane.screens.<SCREEN_KEY>`.
SCREEN_KEY = "forward"
RECEIPT_PATH = "docs/benchmarks/forward_screen_fwd1.json"
#: The checkpoints (counted forward sessions) and the windows' length.
PLAN = (5, 10, 15, 20, 30, 40, 60)
KMAX = 60
#: The bar's grid: c = k / 100, k in 0..K_MAX (c 5.00 at most).
K_MAX = 500
ZERO = 1e-12
TYPES = ("ETF", "PANEL")
#: The cases each type is judged in (an ETF lineage with a sealed look is not judged at all: the review's F3).
CASES: dict[str, tuple[str, ...]] = {"ETF": ("N",), "PANEL": ("N", "XS1")}
#: The global bars, the margin over the own floor and the own floor's cap by case (A33).
C_G: dict[str, dict[str, float]] = {"ETF": {"N": 2.61}, "PANEL": {"N": 2.06, "XS1": 3.16}}
C_MARGIN = 0.05
OWN_CAP: dict[str, float] = {"N": 0.12, "XS1": 0.024}
#: The haircut a side, in bp, before any live lot is measured; its floor once lots are; the panel's lots measured
#: before the measured gap replaces its 3 bp.
HAIRCUT_BP: dict[str, int] = {"ETF": 2, "PANEL": 3}
HAIRCUT_FLOOR_BP = 2
PANEL_LOTS = 20
#: The panel's placebo leg: XS1's law, 999 draws, held when at most 119 are at or above the program's t.
PLACEBO_DRAWS = 999
PLACEBO_COUNT_MAX = 119
PLACEBO_SEED = "FWD1|{receipt}|{row_hash}|placebo"
OWNER_WALL = 0.15
#: The earlier look's per-program cap a case-XS1 lineage carries (XS1's own cap: 12%), and its forward budget (D2: 3%).
XS1_LOOK_CAP = 0.12
XS1_FORWARD_BUDGET = 0.03
#: A PANEL pass at or before this checkpoint is flagged WEAK (45% of zero-edge panel passes come at checkpoint 5).
PANEL_WEAK_K = 10
#: The keys a pin carries, and the figure keys of each (type, case) in its `figures`.
PIN_KEYS = ("name", "screen", "receipt_sha256", "plan", "c_G", "c_margin", "haircut_bp", "haircut_floor_bp",
            "panel_lots", "own_cap", "placebo", "owner_wall", "figures")
FIGURE_KEYS = ("budget", "fp_point", "fp_ub", "zero_edge_by_checkpoint", "edge", "power", "fp_avg")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


# ------------------------------------------------------------------------------------------------------------- the pin
@dataclass(frozen=True)
class Rule:
    """A loaded pin (`load`): the receipt's sha and its figures by "TYPE|CASE" ({budget, fp_point, fp_ub,
    zero_edge_by_checkpoint [7], edge, power, fp_avg, and for ETF drift_avg; for XS1 look_cap, combined})."""

    receipt_sha256: str
    figures: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)

    def c_G(self, typ: str, case: str) -> float:
        return C_G[typ][case]

    def figure(self, typ: str, case: str) -> Mapping[str, Any]:
        return self.figures[f"{typ}|{case}"]


def pin(policy: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
    """THE PIN: `elane.screens.forward` of the REPOSITORY's policy.json (`policy`: a parsed document, or its `elane`
    block; default `league.swarm.settings.read_policy()`). {} when there is none."""
    if policy is None:
        try:
            from ..swarm import settings as settings_mod

            policy, _ = settings_mod.read_policy()
        except Exception:  # noqa: BLE001 - no file: no pin
            policy = {}
    block = policy.get("elane") if isinstance(policy, Mapping) and isinstance(policy.get("elane"), Mapping) else policy
    screens = block.get("screens") if isinstance(block, Mapping) and isinstance(block.get("screens"), Mapping) else {}
    found = screens.get(SCREEN_KEY)
    return found if isinstance(found, Mapping) else {}


def _same(value: Any, want: Any) -> bool:
    """`value` is `want` (numbers compared exactly as floats; mappings and sequences element by element)."""
    if isinstance(want, Mapping):
        return isinstance(value, Mapping) and set(value) == set(want) and all(_same(value[k], want[k]) for k in want)
    if isinstance(want, (list, tuple)):
        return isinstance(value, (list, tuple)) and len(value) == len(want) and all(_same(a, b) for a, b in zip(value, want))
    if isinstance(want, bool) or isinstance(value, bool):
        return value is want
    if isinstance(want, (int, float)):
        return isinstance(value, (int, float)) and math.isfinite(float(value)) and float(value) == float(want)
    return value == want


def _figure_problem(key: str, block: Any) -> str | None:
    if not isinstance(block, Mapping):
        return f"figures.{key} is not an object"
    for name in FIGURE_KEYS:
        if name not in block:
            return f"figures.{key} has no {name}"
    for name in ("budget", "fp_point", "fp_ub", "power", "fp_avg"):
        value = block[name]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0.0 <= float(value) <= 1.0:
            return f"figures.{key}.{name} is not a share"
    curve = block["zero_edge_by_checkpoint"]
    if not isinstance(curve, (list, tuple)) or len(curve) != len(PLAN) or any(
            isinstance(v, bool) or not isinstance(v, (int, float)) or not 0.0 <= float(v) <= 1.0 for v in curve):
        return f"figures.{key}.zero_edge_by_checkpoint is not {len(PLAN)} shares"
    if float(block["budget"]) > OWNER_WALL + 1e-12 or float(block["fp_ub"]) > float(block["budget"]) + 1e-12:
        return f"figures.{key}: the bound is over its budget, or the budget over the owner's wall"
    return None


def load(block: Mapping[str, Any] | None) -> tuple[Rule | None, str | None]:
    """(the rule, None) from a pin block (`pin`), or (None, why it pins nothing). Every constant must be this code's
    (a pin cannot move a bar, a cap, the haircut or the plan: that is a captain's release with its cost stated)."""
    if not isinstance(block, Mapping) or not block:
        return None, "no forward screen is pinned (elane.screens.forward)"
    missing = [key for key in PIN_KEYS if key not in block]
    if missing:
        return None, f"the forward screen's pin lacks {', '.join(missing)}"
    if block.get("name") != NAME or block.get("screen") != SCREEN:
        return None, f"the pin names {block.get('name')!r}/{block.get('screen')!r}, this code runs {NAME}/{SCREEN}"
    sha = block.get("receipt_sha256")
    if not isinstance(sha, str) or not _HEX64.match(sha):
        return None, "the pin's receipt_sha256 is not 64 lower-case hex characters"
    wants = {"plan": list(PLAN), "c_G": C_G, "c_margin": C_MARGIN, "haircut_bp": HAIRCUT_BP,
             "haircut_floor_bp": HAIRCUT_FLOOR_BP, "panel_lots": PANEL_LOTS, "own_cap": OWN_CAP,
             "placebo": {"draws": PLACEBO_DRAWS, "count_max": PLACEBO_COUNT_MAX}, "owner_wall": OWNER_WALL}
    for key, want in wants.items():
        if not _same(block.get(key), want):
            return None, f"the pin's {key} is not this code's ({want!r})"
    for typ, cases in C_G.items():
        for case, c in cases.items():
            if abs(c * 100 - round(c * 100)) > 1e-9 or not 0.0 <= c <= K_MAX / 100:
                return None, f"the bar {typ} {case} is off the 0.01 grid"
    figures = block.get("figures")
    if not isinstance(figures, Mapping):
        return None, "the pin's figures are not an object"
    held: dict[str, Mapping[str, Any]] = {}
    for typ, cases in CASES.items():
        for case in cases:
            key = f"{typ}|{case}"
            problem = _figure_problem(key, figures.get(key))
            if problem is not None:
                return None, f"the pin's {problem}"
            held[key] = dict(figures[key])
    return Rule(receipt_sha256=sha, figures=held), None


def rule(policy: Mapping[str, Any] | None = None) -> tuple[Rule | None, str | None]:
    """`load(pin(policy))`."""
    return load(pin(policy))


# --------------------------------------------------------------------------------------------------------- the clock
def start_after(pinned_at: float) -> dt.date:
    """THE CLOCK: the first session FWD1 judges, from the time the release carrying the pin began running: the session
    after the first close after it (`forward_db.first_day(forward_db.first_close(pinned_at))`, the rule E3's D2 gives a
    program's code: no session whose decision or fill could have been seen when the judge was pinned is judged)."""
    from . import forward_db

    return forward_db.first_day(forward_db.first_close(float(pinned_at)))


def forward_start(first_day: dt.date, pin_start: dt.date) -> dt.date:
    """FWD1_START of a program: max(its first forward day, the pin's first judged session)."""
    return max(first_day, pin_start)


# ----------------------------------------------------------------------------------------------------------- the bar
def grid_index(t: float | None) -> int:
    """The largest k in 0..K_MAX with k / 100 <= t; -1 when t is None, not finite and below 0, or below 0 (the study's
    fwdcore.grid_index for one value). +inf is K_MAX."""
    if t is None or (isinstance(t, float) and math.isnan(t)) or float(t) < 0.0:
        return -1
    if math.isinf(float(t)) or float(t) >= K_MAX / 100.0:
        return K_MAX
    k = int(math.floor(float(t) * 100.0))
    while k + 1 <= K_MAX and (k + 1) / 100.0 <= float(t):
        k += 1
    while k >= 0 and k / 100.0 > float(t):
        k -= 1
    return min(k, K_MAX)


def k_used(typ: str, case: str, k_own: int | None) -> int | None:
    """The bar on the grid: max(100 c_G, k_own + 5); None (ineligible) without an own floor or above `K_MAX`."""
    if k_own is None:
        return None
    k = max(int(round(C_G[typ][case] * 100)), int(k_own) + int(round(C_MARGIN * 100)))
    return k if k <= K_MAX else None


def c_used(typ: str, case: str, k_own: int | None) -> float | None:
    """c_used = k_used / 100 (the same float as the grid's, so `t >= c_used` is `grid_index(t) >= k_used`)."""
    k = k_used(typ, case, k_own)
    return None if k is None else k / 100.0


# ------------------------------------------------------------------------------------------------------ the haircut
def haircut_bp(typ: str, side_gaps: Sequence[float]) -> int:
    """g in bp a side from the closed live lots' measured gaps a side of this type (`fwd_lotgap.side_gap_bp`, adverse
    positive): ETF the larger of 2 and the mean rounded up; PANEL 3 until `PANEL_LOTS` lots, then the larger of 2 and
    the mean rounded up. A gap that is not finite is not a measurement."""
    gaps = [float(v) for v in side_gaps if v is not None and math.isfinite(float(v))]
    if typ == "PANEL" and len(gaps) < PANEL_LOTS:
        return HAIRCUT_BP["PANEL"]
    if not gaps:
        return HAIRCUT_BP[typ]
    mean = math.fsum(gaps) / len(gaps)
    return max(HAIRCUT_FLOOR_BP, int(math.ceil(mean - 1e-9)))


# ----------------------------------------------------------------------------------------------------------- series
def series(typ: str, rows: Sequence[Mapping[str, Any]], *, g_bp: float, sides: Sequence[float],
           live_like: Mapping[str, float] | None = None) -> tuple[list[float], list[float]]:
    """(x, x15) of counted rows (dicts with day, r, w, b, r15), the haircut taken: THE SERIES of the module docstring.
    `sides` one value a row; `live_like` {day: r_ll} (ETF: in place of r). ValueError on a row that is not finite or
    lacks r15 (a series with a gap judges nothing)."""
    if len(sides) != len(rows):
        raise ValueError("the sides are not aligned with the counted rows")
    g = float(g_bp) * 1e-4
    ll = live_like or {}
    x: list[float] = []
    x15: list[float] = []
    for row, s in zip(rows, sides):
        r, w, b, r15 = (row.get(k) for k in ("r", "w", "b", "r15"))
        if any(v is None for v in (r, w, b, r15, s)):
            raise ValueError(f"the row of {row.get('day')} lacks a value")
        r, w, b, r15, s = float(r), float(w), float(b), float(r15), float(s)
        base = float(ll[str(row.get("day"))]) if str(row.get("day")) in ll else r
        stress = r15 + (base - r)
        if typ == "PANEL":
            base, stress = base - w * b, stress - w * b
        values = (base - g * s, stress - g * s)
        if not all(math.isfinite(v) for v in values):
            raise ValueError(f"the row of {row.get('day')} is not finite")
        x.append(values[0])
        x15.append(values[1])
    return x, x15


# -------------------------------------------------------------------------------------------------------- statistic
def t_stat(values: Sequence[float]) -> float | None:
    """mean / sd (ddof 1) x sqrt(n), every sum by math.fsum; None when n < 2, the sd is below 1e-12 or t is not
    finite."""
    n = len(values)
    if n < 2:
        return None
    mean = math.fsum(values) / n
    var = math.fsum((v - mean) ** 2 for v in values) / (n - 1)
    sd = math.sqrt(var) if var > 0 else 0.0
    if not sd >= ZERO:
        return None
    t = mean / sd * math.sqrt(n)
    return t if math.isfinite(t) else None


def checkpoint(x: Sequence[float], x15: Sequence[float], k: int) -> dict[str, Any]:
    """{t, S, S15} over the first k values (ValueError when fewer)."""
    if len(x) < k or len(x15) < k:
        raise ValueError(f"a checkpoint of {k} needs {k} counted days")
    head, head15 = list(x[:k]), list(x15[:k])
    return {"t": t_stat(head), "S": math.fsum(head), "S15": math.fsum(head15)}


def legs_pass(point: Mapping[str, Any], c_used_value: float | None) -> bool:
    """pass_k without the placebo leg: t defined and >= c_used, S > 1e-12, S15 > 1e-12."""
    t = point.get("t")
    return (c_used_value is not None and t is not None and float(t) >= float(c_used_value)
            and float(point["S"]) > ZERO and float(point["S15"]) > ZERO)


def placebo_count(t: float | None, placebo_t: Sequence[float | None]) -> int | None:
    """#{m : placebo_t[m] >= t}; an undefined placebo t counts as not above; None when t is undefined."""
    if t is None or not math.isfinite(float(t)):
        return None
    return sum(1 for v in placebo_t if v is not None and math.isfinite(float(v)) and float(v) >= float(t))


def placebo_holds(count: int | None, draws: int) -> bool:
    """The leg: `draws` is the law's 999 and at most 119 are at or above."""
    return count is not None and int(draws) == PLACEBO_DRAWS and int(count) <= PLACEBO_COUNT_MAX


def placebo_seed(receipt_sha256: str, row_hash: str) -> int:
    """int.from_bytes(sha256("FWD1|" + receipt sha256 + "|" + the representative's registry row_hash +
    "|placebo").digest()[:16], "big")."""
    import hashlib

    text = PLACEBO_SEED.format(receipt=str(receipt_sha256), row_hash=str(row_hash))
    return int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:16], "big")


# ------------------------------------------------------------------------------------------------------- own floor
def _tstats(x: Any, x15: Any) -> tuple[Any, Any, Any]:
    """The study's fwdcore.tstats over windows (n, >= KMAX): numpy's mean and std (ddof 1), as the receipt's integers
    were computed (`own_floor_k` must reproduce them exactly)."""
    import numpy as np

    n = x.shape[0]
    t = np.full((n, len(PLAN)), np.nan)
    S = np.zeros((n, len(PLAN)))
    S15 = np.zeros((n, len(PLAN)))
    for j, k in enumerate(PLAN):
        xs = x[:, :k]
        m = xs.mean(axis=1)
        sd = xs.std(axis=1, ddof=1)
        with np.errstate(divide="ignore", invalid="ignore"):
            tk = m / sd * math.sqrt(k)
        ok = (sd >= ZERO) & np.isfinite(tk)
        t[:, j] = np.where(ok, tk, np.nan)
        S[:, j] = xs.sum(axis=1)
        S15[:, j] = x15[:, :k].sum(axis=1)
    return t, S, S15


def _grid(M: Any) -> Any:
    """fwdcore.grid_index over an array."""
    import numpy as np

    grid = np.arange(K_MAX + 1) / 100.0
    M = np.where(np.isfinite(M) | (M == np.inf), M, -np.inf)
    g = np.searchsorted(grid, M, side="right") - 1
    return np.minimum(g, K_MAX).astype(np.int64)


def _window_T(r: Any, r15: Any, w: Any, kappa: float, drift: float = 0.0) -> Any:
    """The best checkpoint's t (-inf where no checkpoint passes its legs) of every contiguous `KMAX`-window of one pool
    under x0 = r - w (kappa - drift), stress x0 - (r - r15): plan K_5's maximum."""
    import numpy as np

    n = len(r)
    starts = np.arange(n - KMAX + 1)
    idx = starts[:, None] + np.arange(KMAX)[None, :]
    x0 = r - w * (kappa - drift)
    s0 = x0 - (r - r15)
    t, S, S15 = _tstats(x0[idx], s0[idx])
    ok = np.isfinite(t) & (S > ZERO) & (S15 > ZERO)
    T = np.where(ok, t, -np.inf)
    return T.max(axis=1)


def _inclusion(n: int) -> Any:
    """How many of a pool's contiguous `KMAX`-windows hold each session."""
    import numpy as np

    starts = np.arange(n - KMAX + 1)
    cnt = np.zeros(n + 1, dtype=np.int64)
    np.add.at(cnt, starts, 1)
    np.add.at(cnt, starts + KMAX, -1)
    return np.cumsum(cnt)[:n].astype(np.float64)


def own_floor_k(cells: Sequence[Sequence[Sequence[Any]]], cap: float) -> dict[str, Any]:
    """THE OWN FLOOR (the study's fwdcore.own_floor_k on plan K_5, to the integer): `cells` a list of cells, each a list
    of pools (r, r15, w[, b]) of float64 arrays; every contiguous 60-session window inside one pool is a world. Per cell:
    kappa = the inclusion-weighted fsum of r over fsum of w; the windows' best t under x0 = r - w kappa (stress
    x0 - (r - r15)); k_cell = the smallest k in 0..500 with passes(k) x 10^4 <= round(cap x 10^4) x worlds (exact
    integers). -> {k_own (the largest over the cells, or None), cells {index: k_cell}, why (None, or why it is
    ineligible: no cell, no window, no exposure, a series that is not finite)}."""
    import numpy as np

    capn = int(round(float(cap) * 10000))
    found: dict[str, int] = {}
    if not cells:
        return {"k_own": None, "cells": found, "why": "no cell"}
    for ci, pools in enumerate(cells):
        num = den = 0.0
        held = []
        for pool in pools:
            r, r15, w = (np.asarray(pool[i], dtype=np.float64) for i in range(3))
            if not (len(r) == len(r15) == len(w)) or not (np.isfinite(r).all() and np.isfinite(r15).all()
                                                          and np.isfinite(w).all()):
                return {"k_own": None, "cells": found, "why": f"cell {ci}: a series that is not finite or aligned"}
            if len(r) < KMAX:
                continue
            iw = _inclusion(len(r))
            num += math.fsum((iw * r).tolist())
            den += math.fsum((iw * w).tolist())
            held.append((r, r15, w))
        if not den > 0:
            return {"k_own": None, "cells": found, "why": f"cell {ci}: no exposure"}
        kappa = num / den
        if not math.isfinite(kappa):
            return {"k_own": None, "cells": found, "why": f"cell {ci}: non-finite"}
        if not held:
            return {"k_own": None, "cells": found, "why": f"cell {ci}: no window"}
        g = _grid(np.concatenate([_window_T(r, r15, w, kappa) for (r, r15, w) in held]))
        worlds = len(g)
        cnt = np.zeros(K_MAX + 2, dtype=np.int64)
        np.add.at(cnt, g[g >= 0], 1)
        passes = cnt[:K_MAX + 1][::-1].cumsum()[::-1]
        ok = passes * 10000 <= capn * worlds
        if not ok.any():
            return {"k_own": None, "cells": found, "why": f"cell {ci}: no k <= {K_MAX}"}
        found[str(ci)] = int(np.argmax(ok))
    return {"k_own": max(found.values()), "cells": found, "why": None}


def drift_kept(cells: Sequence[Sequence[Sequence[Any]]], k: int) -> float | None:
    """THE PROGRAM'S OWN DRIFT-KEPT RATE (the review's F7, ETF): the share of its own Train-era windows that pass at grid
    k under N1, the market's drift kept (x1 = r - w (kappa - m_P), m_P the inclusion-weighted mean of the benchmark b
    over the cell's windows); the largest over the cells. Pools carry (r, r15, w, b). None when a cell cannot be read.
    Direction, not a false positive: the goal counts it, and the line beside the trade says so."""
    import numpy as np

    best: float | None = None
    for pools in cells:
        num = den = bsum = isum = 0.0
        held = []
        for pool in pools:
            if len(pool) < 4:
                return None
            r, r15, w, b = (np.asarray(pool[i], dtype=np.float64) for i in range(4))
            if len(r) < KMAX:
                continue
            iw = _inclusion(len(r))
            num += math.fsum((iw * r).tolist())
            den += math.fsum((iw * w).tolist())
            bsum += math.fsum((iw * b).tolist())
            isum += math.fsum(iw.tolist())
            held.append((r, r15, w))
        if not den > 0 or not isum > 0 or not held:
            return None
        kappa, m_p = num / den, bsum / isum
        g = _grid(np.concatenate([_window_T(r, r15, w, kappa, m_p) for (r, r15, w) in held]))
        share = float((g >= int(k)).sum()) / len(g)
        best = share if best is None else max(best, share)
    return best


def floor_cells(typ: str, pool_d: Sequence[Any] | None, pool_c: Sequence[Any] | None) -> list[list[Sequence[Any]]]:
    """The floor's cells from the program's two Train-era pools (2016-19 "D", 2022-24 "C"; each from its first decision
    + 2 sessions). ETF (S2's): both when each holds >= 251 sessions; C alone when >= 550. PANEL (XS1's): both when each
    >= 251; EACH alone when >= 550."""
    def size(p: Sequence[Any] | None) -> int:
        return 0 if p is None else len(p[0])

    cells: list[list[Sequence[Any]]] = []
    if size(pool_d) >= 251 and size(pool_c) >= 251:
        cells.append([pool_d, pool_c])            # type: ignore[list-item]
    if typ == "PANEL" and size(pool_d) >= 550:
        cells.append([pool_d])                    # type: ignore[list-item]
    if size(pool_c) >= 550:
        cells.append([pool_c])                    # type: ignore[list-item]
    return cells


# ----------------------------------------------------------------------------------------------- the registry beside
def expected_passes(rule_: Rule, read: Sequence[tuple[str, str, int]]) -> dict[str, float]:
    """THE REGISTRY'S EXPECTED ZERO-EDGE PASSES (the review's F5): for each judged lineage (type, case, the last
    checkpoint it was read at), the receipt's zero-edge share passing by that checkpoint, summed by "TYPE|CASE"."""
    out: dict[str, float] = {}
    for typ, case, k in read:
        key = f"{typ}|{case}"
        if int(k) not in PLAN or key not in rule_.figures:
            continue
        p0 = float(rule_.figure(typ, case)["zero_edge_by_checkpoint"][PLAN.index(int(k))])
        out[key] = out.get(key, 0.0) + p0
    return {key: round(value, 4) for key, value in out.items()}


def weak(typ: str, k: int) -> bool:
    """The WEAK flag: every ETF pass; a PANEL pass at checkpoint 10 or earlier."""
    return typ == "ETF" or int(k) <= PANEL_WEAK_K


def _pct(x: Any) -> str:
    return "n/a" if x is None else f"{100.0 * float(x):.1f}"


def _c(x: Any) -> str:
    return "n/a" if x is None else f"{float(x):.2f}"


def words(rule_: Rule, *, typ: str, case: str, k: int, start: Any, c_used_value: float, k_own: int | None,
          observed: int, judged: int, expected: float | None) -> str:
    """The sentence of a forward pass IN IDS AND WORDS (the permit file's: no figure of P&L and no t, only the rule's
    own figures): what the swarm may record beside the seat it permits."""
    fig = rule_.figure(typ, case)
    weak_text = ("WEAK SCREEN: at realistic ETF timing edges a forward pass is about as likely without edge as with it. "
                 if typ == "ETF" else
                 "WEAK at this checkpoint: 45% of zero-edge panel passes come at checkpoint 5. " if weak(typ, k) else "")
    look = (f"; with its XS1 look (at most {_pct(XS1_LOOK_CAP)}% a program) the combined rate is at most "
            f"{_pct(XS1_LOOK_CAP + XS1_FORWARD_BUDGET)}%" if case == "XS1" else "")
    return (f"{SCREEN} forward screen ({typ}, case {case}): passed at checkpoint {k} of 5-60 counted forward sessions "
            f"since {start} (after the code was frozen and the screen pinned); bar {_c(c_used_value)} (global "
            f"{_c(C_G[typ][case])}, own floor {_c(None if k_own is None else k_own / 100)} + 0.05). Measured "
            f"false-positive rate at zero edge in the worst Train-era volatility regime: {_pct(fig['fp_point'])}% (97.5% "
            f"bound {_pct(fig['fp_ub'])}%; forward budget {_pct(fig['budget'])}%){look}; owner's wall 15%. "
            f"Contamination is zero by construction for the judged sessions. {weak_text}Registry: {observed} forward "
            f"passes of {judged} {typ} case {case} lineages judged so far, against "
            f"{'n/a' if expected is None else f'{expected:.2f}'} expected at zero edge. Failures stay on record.")


def beside(rule_: Rule, *, typ: str, case: str, k: int, start: Any, t: float, c_used_value: float,
           k_own: int | None, g_bp: float, pnl: float | None, drift: float | None, observed: int, judged: int,
           expected: float | None) -> str:
    """THE SENTENCE BESIDE A FORWARD-PASSED TRADE (HOUSE-RULE-FWD1 section 5 with the review's fixes F5, F6, F7, F8):
    every placeholder filled; operator-only (it carries the program's t and its shadow P&L)."""
    fig = rule_.figure(typ, case)
    look = (f"; with its XS1 look (at most {_pct(XS1_LOOK_CAP)}% a program) the combined rate is at most "
            f"{_pct(XS1_LOOK_CAP + XS1_FORWARD_BUDGET)}%" if case == "XS1" else "")
    weak_text = ("WEAK SCREEN: at realistic ETF timing edges a forward pass is about as likely without edge as with it. "
                 if typ == "ETF" else
                 "WEAK at this checkpoint: 45% of zero-edge panel passes come at checkpoint 5 (a likelihood ratio of "
                 "about 1.55 there). " if weak(typ, k) else "")
    etf = (f"An ETF pass also reads the window's market trend: this program keeps the market's drift and passes "
           f"{_pct(drift)}% of its own Train-era 60-session windows at this bar: direction, not skill. "
           if typ == "ETF" else "")
    return (f"{SCREEN} forward screen ({typ}, case {case}): passed at checkpoint {k} of 5-60 counted forward sessions "
            f"since {start} (after the code was frozen and the screen pinned); t = {float(t):.2f} >= bar "
            f"{_c(c_used_value)} (global {_c(C_G[typ][case])}, own floor "
            f"{_c(None if k_own is None else k_own / 100)} + 0.05); "
            f"{'shadow residual (its P&L less its matched cells' + chr(39) + ' P&L)' if typ == 'PANEL' else 'shadow P&L'} "
            f"over the judged sessions after costs and a {float(g_bp):g} bp-a-side fill haircut "
            f"{'n/a' if pnl is None else f'{100.0 * float(pnl):+.2f}% of the sleeve'}. Measured "
            f"false-positive rate at zero edge in the worst Train-era volatility regime of matching length: "
            f"{_pct(fig['fp_point'])}% (97.5% bound {_pct(fig['fp_ub'])}%; forward budget {_pct(fig['budget'])}%){look}; "
            f"owner's wall 15%. Memory: the judged sessions came after the program's code was frozen and after every "
            f"authoring model's training data, so no model can have memorized them; contamination is zero by "
            f"construction for the judged sessions. Skill: a pass inside 60 sessions is weak evidence. At a true edge "
            f"of {fig['edge']} a year a program like this passes about {_pct(fig['power'])}% of the time against "
            f"{_pct(fig['fp_avg'])}% at zero edge in the same fill world, so most forward passers have no edge. "
            f"{weak_text}{etf}Registry: {observed} forward passes of {judged} {typ} case {case} lineages judged so "
            f"far, against {'n/a' if expected is None else f'{expected:.2f}'} expected at zero edge. Failures stay on "
            f"record.")


__all__ = ["NAME", "SCREEN", "SCREEN_KEY", "RECEIPT_PATH", "PLAN", "KMAX", "K_MAX", "ZERO", "TYPES", "CASES", "C_G",
           "C_MARGIN", "OWN_CAP", "HAIRCUT_BP", "HAIRCUT_FLOOR_BP", "PANEL_LOTS", "PLACEBO_DRAWS",
           "PLACEBO_COUNT_MAX", "OWNER_WALL", "XS1_LOOK_CAP", "XS1_FORWARD_BUDGET", "PANEL_WEAK_K", "PIN_KEYS",
           "FIGURE_KEYS", "Rule", "pin", "load", "rule", "start_after", "forward_start", "grid_index", "k_used",
           "c_used", "haircut_bp", "series", "t_stat", "checkpoint", "legs_pass", "placebo_count", "placebo_holds",
           "placebo_seed", "own_floor_k", "drift_kept", "floor_cells", "expected_passes", "weak", "words", "beside"]
