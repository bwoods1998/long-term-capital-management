"""POOL1, THE POOLED-BY-MECHANISM FORWARD SCREEN's rule (the owner's A55, pre-registered in A55a:
scratch/pooled-screen/PREREG-POOL1.md sha256 f42bcdc1..., `PREREG_SHA256`), pure: the pin, the receipt it pins, the
cell key, the statistic, the own floor, the caps, the placebo leg, stage 1, the void, the demotion, the route and the
words. No store, no file but the repository's policy.json and the receipt, no clock.

Owner: the POOL1 build (league/ops/pool_screen.py is its job). Protected (league/ops/ is FORBIDDEN to every role): the
judge is never a role's to move. Ops only: no module of league/swarm, league/equity, league/live or league/gym imports
it (the swarm reads the job's permit file of ids and words, league/swarm/elane_forward.py `pool_listed`).

THE RULE (the PREREG's sections, each function naming its own):
1. THE UNIT (section 1). A CELL is (class, group), both read by the House. GROUP (`group_of`): the base group (index,
   sectors, defensive) holding MORE than 2/3 of the member's Train-era exposure (sum over its Train pools of |w_s|, each
   symbol's group `elane_train.symbols_group([s])`); a member with any stocks symbol, or none above 2/3, is out of
   cells. CLASS: a founding lineage's is its declared birth card's `mechanism_class` (the receipt lists founders, their
   House groups and cells); a later lineage is ASSIGNED (`assign`) to the clocked cell of its group whose founders'
   Train D its own Train z correlates with most, when that correlation is at least the receipt's rho_assign. OUT
   (`excluded`): panels, stock programs, the beta class equity_premium, event readers (card input `event_calendar` or a
   frozen code naming the ctx fields `events` / `events_next`: `reads_events`), a Train mean total exposure under 1%,
   no base group above 2/3. A MEMBER is a lineage's first passing version (`member_pid`: the lowest pid of reason
   train_pass, seed or live); the House's COPY MERGE (`merge_copy`: Train z correlation >= 0.7 on common sessions, or
   the same program sha) keeps the earlier pid. All judged cells of one declared class are one CLUSTER; clusters of
   different classes join by the member rule (`member_join`).
2. THE STATISTIC (section 2). On a counted day t of member i: r^g = r - g sides (r_ll in place of r where `fwd_ll` has
   a row, and r15 + (r_ll - r) in place of r15: FWD1's), a_t = r^g_t - sum_s w_st mu_s - sum_s what_st (R_st - mu_s),
   a15 = a - (r - r15) (`alpha`); what_st = (PRIOR wbar_s + the sum of w_s over the member's earlier counted days since
   it joined) / (PRIOR + their count), decided at t-1 (`w_hat`); z = a / sigma_used, sigma_used = max(sigma,
   `SIGMA_FLOOR`, sigma_tilde / 3) (`sigma_used`), sigma_tilde = 1 / median(1 / sigma_j) over the cell's founders
   (`sigma_tilde`). D_t = the mean of z over the cell's ACTIVE members, an absent row 0 (`cell_day`); a CELL SESSION
   has at least `M_MIN` counted rows. T_k = mean / sd (ddof 1) x sqrt(k) by math.fsum at k in `PLAN`; PASS_k: T_k >=
   c_used, fsum(D15_1..k) > 1e-12, and the placebo leg (`placebo_holds`).
3. THE BAR (section 3.3, 4.4). c_used(unit) = max(c_G, c_own + margin) on the 0.01 grid, ineligible above 5.00
   (`k_used`). The unit is the cluster. c_own (`own_floor`): the smallest c at which the share of Train-era worlds
   where ANY cell of the unit passes at ANY look is at or under CAP_u (POOLED: over all worlds; R-REG: in every regime
   cell, the largest of the per-cell floors), raised until the stationary block bootstrap's 97.5% bound of that share
   is at or under WALL_u; under N0, N0R and N1 (`NULLS`), the largest floor; at least the receipt's matched-family N1
   floor. CAP_u = 0.12 - U_u, WALL_u = 0.15 - U_u(97.5%) (`caps`); U_u >= 0.12 is report-only, judged at 0.12 / 0.15.
4. THE REST: the zeroed-days void (`mar_void`, section 2.2), stage 1 (`stage1`, section 5), the placebo leg's seed,
   draws and count (section 2.1), the cell demotion (`demote`, section 7.1), the POOL route (`on_pool_route`, section
   7.2), the words (`words`, section 8), the operator's sentence beside a pooled trade (`beside`) and the floor-wide
   expected zero-edge passes (`expected_passes`, section 4.5).

THE NULL WORLDS (`own_floor`; the reference definitions the calibration's code must reproduce, its conformance vectors
in the receipt): every contiguous `WINDOW`-session window inside one era of the unit's members' Train pools aligned by
date, what restarted at the window start, the plan and the stress leg; each member at its own join offset (a member
joins the window at the cell session it joined the cell at), z at its frozen sigma_used.
- N0: each member's window alpha less its long-run pool mean (the mean of its era-restart alpha over both pools).
- N0R: the same, but the mean is taken inside the window's SPY volatility tercile (the mean of its era-restart alpha
  over the sessions of every window of that tercile, each session once a window it is in).
- N1 (drift kept, timing killed): each member's per-symbol weight path rolled circularly inside its era by one common
  offset of `N1_OFFSETS` below the era's sessions less `WINDOW` (every offset is a world), its P&L recomputed on the
  rolled path by close-to-close legs (sum_s w'_s R_s less (hs_s + g) |dw'_s|, the stress leg 1.5 hs_s), read RAW.
- REGIME CELLS (`regime_labels`): terciles, at the receipt's cutpoints, of SPY's realized volatility (sd ddof 1 of
  its daily returns over the window) and SPY's window return (compounded); a unit holding a sector cell adds the
  window's mean cross-sectional sd (ddof 1) of the sector ETFs' daily returns (those with a return on every session
  of the window), one holding a defensive cell the TLT less GLD window return.
- THE BOUND (`bootstrap_histograms`): per resample, each cell's members drawn with replacement, each era's aligned
  sessions drawn by a stationary block bootstrap (mean block `BOOT_BLOCK`, circular), N1's offset drawn once an era,
  every window recomputed (the demeaning constants and the regime labels on the resample too); the bound at c is
  the ceil(0.975 B)-th smallest share. Seeds `numpy.random.default_rng([SEED_ROOT, unit id, draw])`.

THE PIN (`pin`, `load`): policy.json `elane.pool_screen` of the REPOSITORY (never the box's swarm.json), {"name":
"POOL1", "prereg_sha256", "receipt_sha256", and every constant of `CONSTANTS`}. `load` refuses (None, why) a missing
or malformed key, a sha that is not 64 lower-case hex characters, the wrong PREREG and any constant other than this
code's. THE RECEIPT (`load_receipt`, `RECEIPT_KEYS`): docs/benchmarks/pool_screen_1.json, written by the calibration,
read only when its sha256 is the pin's; refused whole on any malformed part (a receipt that adopted no rule pins
nothing). NO PIN, NO RECEIPT, NO VERDICT: the job records nothing judged, writes no route list and starts no clock.

Standard library at import; numpy inside the functions that read arrays.
"""

from __future__ import annotations

import ast
import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from . import fwd1_rule as F

NAME = "POOL1"
SCREEN = "POOL1"
#: policy.json `elane.<PIN_BLOCK>` of the REPOSITORY (the settings of the job are `elane.pool`).
PIN_BLOCK = "pool_screen"
RECEIPT_PATH = "docs/benchmarks/pool_screen_1.json"
#: The pre-registration this code implements (scratch/pooled-screen/PINS.log; the captain's A55a).
PREREG_SHA256 = "f42bcdc1d694d9be910da298fc2e62e0d4898003645af9a0a04523eb34ac38da"

# ------------------------------------------------------------------------------------------------------ constants
#: The looks, in counted cell sessions, and the null worlds' window.
PLAN = (40, 60, 120)
WINDOW = 120
M_MIN = 3
PRIOR = 20
SIGMA_FLOOR_BP = 5
SIGMA_FLOOR = SIGMA_FLOOR_BP * 1e-4
WEIGHT_CAP = 3
GROUP_SHARE = Fraction(2, 3)
COPY_RHO = 0.7
NO_FREE_RIDE = 20
EXPOSURE_MIN = 0.01
CAP = 0.12
WALL = 0.15
STAGE1_Z = -1.0
STAGE1_LAG = 5
N1_OFFSETS = (262, 409, 535, 661, 787)
PLACEBO_DRAWS = 999
PLACEBO_COUNT_MAX = 149
PLACEBO_CONTROLS = 50
MAR_FACTOR = 2
MAR_P = 0.05
MAR_DECILE = Fraction(1, 10)
BOOT_RESAMPLES = 2000
BOOT_BLOCK = 120
BOOT_QUANTILE = Fraction(39, 40)
DEMOTE_EVERY = 20
DEMOTE_T_POST = -1.0
DEMOTE_T_ALL = 0.0
DEMOTE_STRESS_AT = (60, 120)
#: A unit's floor definitions and margins (the calibration adopts one of the six), and c_G's range.
FLOORS = ("R-REG", "POOLED")
MARGINS = (0.0, 0.03, 0.05)
C_G_RANGE = (1.40, 2.50)
#: The bar's grid: c = k / 100, k in 0..K_MAX (above 5.00 a unit is ineligible).
K_MAX = F.K_MAX
ZERO = F.ZERO
SEED_ROOT = 20261026
#: The base groups a cell may be of, and the classes that are out of every cell (a beta claim: S2 and FWD1-R judge it).
BASE_GROUPS = ("index", "sectors", "defensive")
CLASSES_OUT = ("equity_premium",)
#: An event reader (A25 R1 until its census ships): the card input, and the ctx fields a frozen code may name.
EVENT_INPUT = "event_calendar"
EVENT_FIELDS = ("events", "events_next")
#: The registry reasons a member is the first of (FWD1's representative reasons).
PASSING = ("train_pass", "seed", "live")
#: The words a unit may stand at. "pending" until its verdict; a final word is one of `FINAL`; a report-only
#: cluster's units carry "report_only" in every file but the operator's report.
PENDING = "pending"
FINAL = ("PASS", "FAIL", "DEMOTED", "VOID", "REFUTED")
REPORT_ONLY = "report_only"
#: A unit that reached its last look with no bar on the grid (c_used above 5.00): no verdict, stated (section 3.3). Its
#: looks are over, so no lineage joins it, but no generator is told a word for it.
INELIGIBLE = "ineligible"
WORDS = (PENDING, REPORT_ONLY, INELIGIBLE, *FINAL)
#: The FWD1-R checkpoint counts U_u is tabulated by (the receipt's `u` rows; 0: none read before the clock).
U_COUNTS = (0, 5, 10, 15, 20, 30, 40, 60)
#: The three nulls every gate holds under; c_own is the largest of their floors.
NULLS = ("N0", "N0R", "N1")
#: The regime axes (SPY's volatility and return: every unit; dispersion: a unit with a sector cell; the TLT-GLD gap:
#: one with a defensive cell).
AXES = ("vol", "ret", "disp", "tltgld")
SECTOR_ETFS = ("XLB", "XLC", "XLE", "XLF", "XLI", "XLK", "XLP", "XLRE", "XLU", "XLV", "XLY")

#: Every constant a pin must carry, as this code holds it (`load` refuses any other value).
CONSTANTS: dict[str, Any] = {
    "plan": list(PLAN), "window": WINDOW, "m_min": M_MIN, "prior": PRIOR, "sigma_floor_bp": SIGMA_FLOOR_BP,
    "weight_cap": WEIGHT_CAP, "group_share": "2/3", "copy_rho": COPY_RHO, "no_free_ride": NO_FREE_RIDE,
    "exposure_min": EXPOSURE_MIN, "cap": CAP, "wall": WALL, "stage1": {"z": STAGE1_Z, "lag": STAGE1_LAG},
    "n1_offsets": list(N1_OFFSETS),
    "placebo": {"draws": PLACEBO_DRAWS, "count_max": PLACEBO_COUNT_MAX, "controls": PLACEBO_CONTROLS},
    "mar": {"factor": MAR_FACTOR, "p": MAR_P, "decile": "1/10"},
    "bootstrap": {"resamples": BOOT_RESAMPLES, "block": BOOT_BLOCK, "quantile": "39/40"},
    "demote": {"every": DEMOTE_EVERY, "t_post": DEMOTE_T_POST, "t_all": DEMOTE_T_ALL,
               "stress_at": list(DEMOTE_STRESS_AT)},
    "floors": list(FLOORS), "margins": list(MARGINS), "c_G_range": list(C_G_RANGE),
}
PIN_KEYS = ("name", "prereg_sha256", "receipt_sha256", *CONSTANTS)
#: THE RECEIPT's keys (docs/benchmarks/pool_screen_1.json, written by the calibration; the module docstring):
#: - "name" "POOL1"; "prereg_sha256" `PREREG_SHA256`; "calibration" {"code_sha256", "decision_sha256"} (ids);
#: - "decision" {"floor": one of `FLOORS`, "margin": one of `MARGINS`, "c_G": on the grid inside `C_G_RANGE`} (null:
#:   the calibration adopted no rule, and nothing is pinned);
#: - "rho_assign" (a correlation, -1..1); "regimes" {axis: [q1, q2]} for every axis of `AXES` (IN's cutpoints);
#: - "founders" {lineage: {"pid", "class", "group", "cell", "why", "merged_into"}}: every lineage the calibration's
#:   House job read (cell "<class>/<group>" or null; why: null or the words of its exclusion);
#: - "units" {cell: {"class", "group", "cluster", "stage1": {"refuted": bool, "z": [...]}}}: the cells judged at the
#:   clock (each with at least `M_MIN` founders in it);
#: - "clusters" {id: {"cells": [cell], "u": {count: [point, bound]}}}: U_u by the FWD1-R checkpoint count read at the
#:   clock (every count of `U_COUNTS`);
#: - "matched_floor" {group: {class: {m: k}}}: the matched stand-in family's cross-fitted N1 floor, on the grid;
#: - "beside" {cluster: {"fp_point", "fp_bound", "fp_worst", "fp_n1", "power_05", "power_10"}}: shares;
#: - "expected" {cluster: [p40, p60, p120]}: its zero-edge pass probability by each look (the floor-wide meter).
RECEIPT_KEYS = ("name", "prereg_sha256", "calibration", "decision", "rho_assign", "regimes", "founders", "units",
                "clusters", "matched_floor", "beside", "expected")
BESIDE_KEYS = ("fp_point", "fp_bound", "fp_worst", "fp_n1", "power_05", "power_10")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_CELL = re.compile(r"^[a-z_]+/(index|sectors|defensive)$")


# ------------------------------------------------------------------------------------------------------------ the pin
@dataclass(frozen=True)
class Pin:
    """A loaded pin (`load`): the receipt's sha."""

    receipt_sha256: str


def pin(policy: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
    """THE PIN: `elane.pool_screen` of the REPOSITORY's policy.json (`policy`: a parsed document, or its `elane` block;
    default `league.swarm.settings.read_policy()`), never the box's swarm.json. {} when there is none."""
    if policy is None:
        try:
            from ..swarm import settings as settings_mod

            policy, _ = settings_mod.read_policy()
        except Exception:  # noqa: BLE001 - no file: no pin
            policy = {}
    block = policy.get("elane") if isinstance(policy, Mapping) and isinstance(policy.get("elane"), Mapping) else policy
    found = block.get(PIN_BLOCK) if isinstance(block, Mapping) else None
    return found if isinstance(found, Mapping) else {}


def _same(value: Any, want: Any) -> bool:
    """fwd1_rule's exact comparison (numbers as floats, mappings and sequences element by element)."""
    return F._same(value, want)


def load(block: Mapping[str, Any] | None) -> tuple[Pin | None, str | None]:
    """(the pin, None) from a pin block (`pin`), or (None, why it pins nothing). Every constant must be this code's (a
    pin moves no bar, cap, plan or haircut: that is a new pre-registration)."""
    if not isinstance(block, Mapping) or not block:
        return None, "no pooled screen is pinned (elane.pool_screen)"
    missing = [key for key in PIN_KEYS if key not in block]
    if missing:
        return None, f"the pooled screen's pin lacks {', '.join(missing)}"
    if block.get("name") != NAME:
        return None, f"the pin names {block.get('name')!r}, this code runs {NAME}"
    if block.get("prereg_sha256") != PREREG_SHA256:
        return None, "the pin names another pre-registration than the one this code implements"
    sha = block.get("receipt_sha256")
    if not isinstance(sha, str) or not _HEX64.match(sha):
        return None, "the pin's receipt_sha256 is not 64 lower-case hex characters"
    for key, want in CONSTANTS.items():
        if not _same(block.get(key), want):
            return None, f"the pin's {key} is not this code's ({want!r})"
    return Pin(receipt_sha256=sha), None


# -------------------------------------------------------------------------------------------------------- the receipt
@dataclass(frozen=True)
class Founder:
    lineage: str
    pid: int
    cls: str | None
    group: str | None
    cell: str | None
    why: str | None
    merged_into: str | None


@dataclass(frozen=True)
class UnitSpec:
    cell: str
    cls: str
    group: str
    cluster: str
    refuted: bool
    founders: tuple[str, ...]
    stage1: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ClusterSpec:
    cid: str
    cells: tuple[str, ...]
    u: Mapping[int, tuple[float, float]]


@dataclass(frozen=True)
class Receipt:
    """A loaded receipt (`load_receipt`): the adopted rule, rho_assign, the regime cutpoints, the founders, the units
    and clusters judged at the clock, the matched floors, the beside figures and the expected zero-edge passes."""

    sha256: str
    floor: str
    margin: float
    c_G: float
    rho_assign: float
    regimes: Mapping[str, tuple[float, float]]
    founders: Mapping[str, Founder]
    units: Mapping[str, UnitSpec]
    clusters: Mapping[str, ClusterSpec]
    matched_floor: Mapping[str, Mapping[str, Mapping[int, int]]]
    beside: Mapping[str, Mapping[str, float]]
    expected: Mapping[str, tuple[float, float, float]]
    doc: Mapping[str, Any] = field(default_factory=dict, repr=False)

    def cluster_of(self, cell: str) -> str | None:
        unit = self.units.get(cell)
        return None if unit is None else unit.cluster

    def u_at(self, cid: str, count: int) -> tuple[float, float] | None:
        """U_u (point, bound) of a founding cluster at the FWD1-R checkpoint count read before the clock: the row of
        that count, else the next larger count's (U only rises with the count read); None above the table."""
        table = self.clusters[cid].u
        for c in sorted(table):
            if c >= int(count):
                return table[c]
        return None

    def matched(self, group: str, cls: str, m: int) -> int | None:
        """The matched stand-in family's cross-fitted N1 floor (grid k) for a unit of `m` members: the row of m, else
        the larger of the two nearest rows (none: None, and the unit waits)."""
        rows = (self.matched_floor.get(group) or {}).get(cls) or {}
        if not rows:
            return None
        if int(m) in rows:
            return int(rows[int(m)])
        below = [k for k in rows if k < m]
        above = [k for k in rows if k > m]
        near = ([max(below)] if below else []) + ([min(above)] if above else [])
        return max(int(rows[k]) for k in near) if near else None


def _share(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(float(value)) \
        and 0.0 <= float(value) <= 1.0


def _receipt_problem(doc: Any) -> str | None:
    if not isinstance(doc, Mapping):
        return "the receipt is not an object"
    missing = [k for k in RECEIPT_KEYS if k not in doc]
    if missing:
        return f"the receipt lacks {', '.join(missing)}"
    if doc.get("name") != NAME or doc.get("prereg_sha256") != PREREG_SHA256:
        return "the receipt is not POOL1's under this pre-registration"
    cal = doc.get("calibration")
    if not isinstance(cal, Mapping) or not all(isinstance(cal.get(k), str) and _HEX64.match(cal[k])
                                               for k in ("code_sha256", "decision_sha256")):
        return "the receipt's calibration ids are not 64-hex shas"
    dec = doc.get("decision")
    if dec is None:
        return "the calibration adopted no rule: nothing is pinned and nothing is judged"
    if not isinstance(dec, Mapping) or dec.get("floor") not in FLOORS:
        return "the receipt's decision names no floor definition of this code"
    if not any(_same(dec.get("margin"), m) for m in MARGINS):
        return "the receipt's margin is not one of the menu's"
    c = dec.get("c_G")
    if isinstance(c, bool) or not isinstance(c, (int, float)) or not math.isfinite(float(c)) \
            or abs(float(c) * 100 - round(float(c) * 100)) > 1e-9 or not C_G_RANGE[0] - 1e-9 <= float(c) <= C_G_RANGE[1] + 1e-9:
        return "the receipt's c_G is off the grid or outside 1.40-2.50"
    rho = doc.get("rho_assign")
    if isinstance(rho, bool) or not isinstance(rho, (int, float)) or not math.isfinite(float(rho)) or not -1.0 <= float(rho) <= 1.0:
        return "the receipt's rho_assign is not a correlation"
    regimes = doc.get("regimes")
    if not isinstance(regimes, Mapping):
        return "the receipt's regimes are not an object"
    for axis in AXES:
        cut = regimes.get(axis)
        if not isinstance(cut, (list, tuple)) or len(cut) != 2 or not all(
                not isinstance(v, bool) and isinstance(v, (int, float)) and math.isfinite(float(v)) for v in cut) \
                or float(cut[0]) > float(cut[1]):
            return f"the receipt's {axis} cutpoints are not two ascending numbers"
    founders = doc.get("founders")
    if not isinstance(founders, Mapping) or not founders:
        return "the receipt lists no founders"
    for lineage, row in founders.items():
        if not isinstance(row, Mapping) or isinstance(row.get("pid"), bool) or not isinstance(row.get("pid"), int) \
                or int(row["pid"]) < 1:
            return f"founder {lineage}: no pid"
        if row.get("cell") is not None and not (isinstance(row["cell"], str) and _CELL.match(row["cell"])):
            return f"founder {lineage}: a cell that is not <class>/<base group>"
        if row.get("group") is not None and row.get("group") not in BASE_GROUPS:
            return f"founder {lineage}: a group outside the base groups"
    units = doc.get("units")
    clusters = doc.get("clusters")
    if not isinstance(units, Mapping) or not isinstance(clusters, Mapping):
        return "the receipt's units or clusters are not objects"
    for cell, unit in units.items():
        if not isinstance(unit, Mapping) or not _CELL.match(str(cell)) or f"{unit.get('class')}/{unit.get('group')}" != cell:
            return f"unit {cell}: its class and group are not its cell"
        if unit.get("cluster") not in clusters or cell not in (clusters[unit["cluster"]] or {}).get("cells", []):
            return f"unit {cell}: its cluster does not list it"
        stage = unit.get("stage1")
        if not isinstance(stage, Mapping) or not isinstance(stage.get("refuted"), bool):
            return f"unit {cell}: no stage 1"
        held = [k for k, r in founders.items() if r.get("cell") == cell and not r.get("why") and not r.get("merged_into")]
        if len(held) < M_MIN:
            return f"unit {cell}: fewer than {M_MIN} founders"
    seen: set[str] = set()
    for cid, cl in clusters.items():
        if not isinstance(cl, Mapping) or not isinstance(cl.get("cells"), list) or not cl["cells"]:
            return f"cluster {cid}: no cells"
        for cell in cl["cells"]:
            if cell not in units or cell in seen or units[cell].get("cluster") != cid:
                return f"cluster {cid}: cell {cell} is not one of its units, or is in two clusters"
            seen.add(cell)
        table = cl.get("u")
        if not isinstance(table, Mapping) or {str(k) for k in table} != {str(k) for k in U_COUNTS}:
            return f"cluster {cid}: its U_u table is not by the counts {list(U_COUNTS)}"
        for k, pair in table.items():
            if not isinstance(pair, (list, tuple)) or len(pair) != 2 or not all(_share(v) for v in pair) \
                    or float(pair[1]) < float(pair[0]):
                return f"cluster {cid}: U_u at {k} is not (point, bound) shares"
    matched = doc.get("matched_floor")
    if not isinstance(matched, Mapping):
        return "the receipt's matched floors are not an object"
    for grp, by_class in matched.items():
        if grp not in BASE_GROUPS or not isinstance(by_class, Mapping):
            return f"matched floor {grp}: not a base group's"
        for cls, rows in by_class.items():
            if not isinstance(rows, Mapping) or not all(
                    str(m).isdigit() and not isinstance(k, bool) and isinstance(k, int) and 0 <= k <= K_MAX
                    for m, k in rows.items()):
                return f"matched floor {grp}/{cls}: not {{m: grid k}}"
    for cell, unit in units.items():
        rows = (matched.get(unit.get("group")) or {}).get(unit.get("class"))
        if not isinstance(rows, Mapping) or not rows:
            return f"unit {cell}: no matched stand-in family's N1 floor for its group and class"
    beside = doc.get("beside")
    expected = doc.get("expected")
    if not isinstance(beside, Mapping) or not isinstance(expected, Mapping):
        return "the receipt's beside or expected figures are not objects"
    for cid in clusters:
        row = beside.get(cid)
        if not isinstance(row, Mapping) or not all(_share(row.get(k)) for k in BESIDE_KEYS):
            return f"cluster {cid}: its beside figures are not shares"
        curve = expected.get(cid)
        if not isinstance(curve, (list, tuple)) or len(curve) != len(PLAN) or not all(_share(v) for v in curve) \
                or any(float(curve[i]) > float(curve[i + 1]) for i in range(len(curve) - 1)):
            return f"cluster {cid}: its expected zero-edge passes are not {len(PLAN)} rising shares"
    return None


def parse_receipt(doc: Mapping[str, Any], sha256: str) -> tuple[Receipt | None, str | None]:
    """A receipt document (`RECEIPT_KEYS`) checked whole; (None, why) on its first defect."""
    problem = _receipt_problem(doc)
    if problem is not None:
        return None, problem
    founders = {str(k): Founder(lineage=str(k), pid=int(r["pid"]), cls=r.get("class"), group=r.get("group"),
                                cell=r.get("cell"), why=r.get("why"), merged_into=r.get("merged_into"))
                for k, r in doc["founders"].items()}
    units = {}
    for cell, u in doc["units"].items():
        held = tuple(sorted(k for k, f in founders.items() if f.cell == cell and not f.why and not f.merged_into))
        units[str(cell)] = UnitSpec(cell=str(cell), cls=str(u["class"]), group=str(u["group"]), cluster=str(u["cluster"]),
                                    refuted=bool(u["stage1"]["refuted"]), founders=held, stage1=dict(u["stage1"]))
    clusters = {str(cid): ClusterSpec(cid=str(cid), cells=tuple(str(c) for c in cl["cells"]),
                                      u={int(k): (float(v[0]), float(v[1])) for k, v in cl["u"].items()})
                for cid, cl in doc["clusters"].items()}
    matched = {str(g): {str(c): {int(m): int(k) for m, k in rows.items()} for c, rows in by.items()}
               for g, by in doc["matched_floor"].items()}
    dec = doc["decision"]
    return Receipt(sha256=sha256, floor=str(dec["floor"]), margin=float(dec["margin"]), c_G=float(dec["c_G"]),
                   rho_assign=float(doc["rho_assign"]),
                   regimes={a: (float(doc["regimes"][a][0]), float(doc["regimes"][a][1])) for a in AXES},
                   founders=founders, units=units, clusters=clusters, matched_floor=matched,
                   beside={str(k): {b: float(v[b]) for b in BESIDE_KEYS} for k, v in doc["beside"].items()},
                   expected={str(k): tuple(float(x) for x in v) for k, v in doc["expected"].items()},  # type: ignore[misc]
                   doc=doc), None


def load_receipt(path: str | Path, pin_: Pin) -> tuple[Receipt | None, str | None]:
    """THE RECEIPT the pin names: read only when its sha256 is the pin's; (None, why) otherwise or on any defect."""
    try:
        raw = Path(path).read_bytes()
    except OSError:
        return None, f"no receipt at {RECEIPT_PATH}: nothing is judged"
    sha = hashlib.sha256(raw).hexdigest()
    if sha != pin_.receipt_sha256:
        return None, "the receipt's sha256 is not the pin's: nothing is judged"
    try:
        doc = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None, "the receipt is not JSON"
    return parse_receipt(doc, sha)


def rule(policy: Mapping[str, Any] | None = None, *, repo: str | Path | None = None) -> tuple[Receipt | None, str | None]:
    """`load(pin(policy))` and then `load_receipt` under the repository (`repo`; default this checkout)."""
    held, why = load(pin(policy))
    if held is None:
        return None, why
    base = Path(repo) if repo is not None else Path(__file__).resolve().parents[2]
    return load_receipt(base / RECEIPT_PATH, held)


# ----------------------------------------------------------------------------------------------------- the cell key
def cell_name(cls: str, group: str) -> str:
    return f"{cls}/{group}"


def member_pid(rows: Sequence[Mapping[str, Any]]) -> int | None:
    """A lineage's MEMBER (section 1.3): its first passing version, the lowest pid whose reason is train_pass, seed or
    live, fixed by pid and never by outcome; None for a Train-fail-only lineage (not a member)."""
    pids = sorted(int(r["pid"]) for r in rows if str(r.get("reason")) in PASSING)
    return pids[0] if pids else None


def group_of(exposure: Mapping[str, float], symbols: Iterable[str] = ()) -> tuple[str | None, str | None]:
    """THE GROUP (section 1.1): (the base group holding MORE than 2/3 of the member's Train-era exposure, None) or
    (None, why it is out of cells): a stocks symbol among `symbols` or `exposure`'s, a symbol outside the base groups,
    no exposure, or no base group above 2/3. `exposure`: {symbol: sum over the Train pools of |w_s|}."""
    from ..equity import config
    from ..swarm import elane_train

    names = [str(s).strip().upper() for s in (*symbols, *exposure)]
    if any(config.class_of(s) == config.STOCK for s in names):
        return None, "a member with a stocks symbol is out of cells"
    by: dict[str, float] = {g: 0.0 for g in BASE_GROUPS}
    values: list[float] = []
    for sym, value in exposure.items():
        v = abs(float(value))
        if not math.isfinite(v):
            return None, f"{sym}'s Train exposure is not finite"
        grp = elane_train.symbols_group([str(sym)])
        if grp not in BASE_GROUPS:
            if v > 0:
                return None, f"{sym} is outside the base groups"
            continue
        by[grp] += v
        values.append(v)
    total = math.fsum(values)
    if not total > 0:
        return None, "no Train-era exposure"
    for grp in BASE_GROUPS:
        if Fraction(by[grp]) * GROUP_SHARE.denominator > Fraction(total) * GROUP_SHARE.numerator:
            return grp, None
    return None, "no base group holds more than 2/3 of its Train-era exposure"


def reads_events(code: Any) -> bool:
    """THE EVENT-CODE SCAN (section 1.2): whether frozen program text names the ctx fields `events` or `events_next`
    (an attribute, or a string constant: `getattr(ctx, "events")`, `ctx["events"]`). Text that does not parse is an
    event reader (fail closed: out of cells)."""
    if not isinstance(code, str):
        return True
    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError):
        return True
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in EVENT_FIELDS:
            return True
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value in EVENT_FIELDS:
            return True
    return False


def excluded(*, panel: bool, symbols: Sequence[str], card: Mapping[str, Any] | None, code: Any,
             mean_exposure: float | None = None, group_why: str | None = None) -> str | None:
    """Why a lineage is OUT of every cell (section 1.2), None when it is not: a panel, a stocks symbol, the beta class
    equity_premium, an event reader (its card's inputs or its frozen code), a Train mean total exposure under 1%, or no
    base group above 2/3 (`group_why`, `group_of`'s). The last two need its Train series (`mean_exposure` None: not
    read yet)."""
    from ..equity import config

    if panel:
        return "a panel program: this receipt is calibrated on ETFs only"
    if any(config.class_of(str(s)) == config.STOCK for s in symbols):
        return "a member with a stocks symbol is out of cells"
    cls = (card or {}).get("mechanism_class") if isinstance(card, Mapping) else None
    if cls in CLASSES_OUT:
        return "class equity_premium: a beta claim, judged by S2 and FWD1-R"
    inputs = (card or {}).get("inputs") if isinstance(card, Mapping) else None
    if isinstance(inputs, (list, tuple)) and EVENT_INPUT in {str(x) for x in inputs}:
        return "an event reader (its card reads the event calendar): out until A25's calendar covers its windows"
    if reads_events(code):
        return "an event reader (its frozen code names ctx.events or ctx.events_next): out until A25's calendar covers its windows"
    if mean_exposure is not None and not float(mean_exposure) >= EXPOSURE_MIN:
        return "a Train-era mean total exposure under 1%: no position to time"
    if group_why is not None:
        return group_why
    return None


# ----------------------------------------------------------------------------------------------------- the exposure
def _index(days: Sequence[str]) -> dict[str, int]:
    return {str(d)[:10]: i for i, d in enumerate(days)}


def lot_exposure(lots: Sequence[Mapping[str, Any]], days: Sequence[str], symbols: Sequence[str]) -> Any:
    """PER-SYMBOL EXPOSURE (section 2): `league.equity.screen.series`' exposure accounting applied per symbol (an (S, n)
    float64 array over `days`, the series' sessions in order, rows in `symbols` order): a lot entered at the open counts
    half its weight on its entry session, one at the close nothing; it counts its weight on each session it is held
    through; an exit at the open counts half, one at the close all of it. A lot entered before the first session is
    held from it. Reads weights and days only (no price): the controls' replay of their hash law uses it as is.
    ValueError for a lot of a symbol outside `symbols`, a day that is not one of the sessions inside their span, or a
    weight that is not a finite positive number."""
    import numpy as np

    where = _index(days)
    n = len(days)
    first, last = (str(days[0])[:10], str(days[-1])[:10]) if n else ("", "")
    out = np.zeros((len(symbols), n))
    rows = {str(s): i for i, s in enumerate(symbols)}

    def at(day: Any, what: str) -> int | None:
        d = str(day)[:10]
        if d in where:
            return where[d]
        if d < first:
            return -1
        if d > last:
            return None
        raise ValueError(f"a lot's {what} day {d} is not a session of the series")

    for lot in lots:
        sym = str(lot.get("symbol"))
        if sym not in rows:
            raise ValueError(f"lot {lot.get('lid')}: {sym} is outside the symbols")
        om = lot.get("weight")
        if isinstance(om, bool) or not isinstance(om, (int, float)) or not math.isfinite(float(om)) or float(om) <= 0:
            raise ValueError(f"lot {lot.get('lid')}: a weight that is not a positive number")
        om = float(om)
        e = at(lot.get("entry_day"), "entry")
        if e is None:
            continue                                           # entered after the series
        x = None if lot.get("exit_day") in (None, "") else at(lot["exit_day"], "exit")
        if x is not None and x < 0:
            continue                                           # closed before the series
        row = out[rows[sym]]
        if e >= 0 and (lot.get("entry_at") or "open") == "open":
            row[e] += om / 2.0
        h0 = max(e + 1, 0)
        h1 = n - 1 if x is None else min(x - 1, n - 1)
        if h1 >= h0:
            row[h0:h1 + 1] += om
        if x is not None and 0 <= x < n:
            row[x] += om / 2.0 if (lot.get("exit_at") or "open") == "open" else om
    return out


def lot_sides(lots: Sequence[Mapping[str, Any]], days: Sequence[str]) -> Any:
    """The weights entering or exiting each session (forward_screen.lot_sides over `days`: 0 where none)."""
    import numpy as np

    where = _index(days)
    out = np.zeros(len(days))
    for lot in lots:
        for key in ("entry_day", "exit_day"):
            day = lot.get(key)
            if day not in (None, "") and str(day)[:10] in where:
                out[where[str(day)[:10]]] += abs(float(lot["weight"]))
    return out


# ------------------------------------------------------------------------------------------------------ the statistic
def w_hat(ws: Any, wbar: Any, *, include: Any = None, prior: int = PRIOR) -> Any:
    """THE PREDICTABLE EXPOSURE (section 2, step 2): what[:, t] = (prior wbar + the sum of ws[:, u] over the earlier
    days u < t that `include` marks) / (prior + their count), decided at t-1. `ws` (S, n); `wbar` (S,)."""
    import numpy as np

    ws = np.asarray(ws, dtype=np.float64)
    n = ws.shape[1]
    inc = np.ones(n, dtype=bool) if include is None else np.asarray(include, dtype=bool)
    held = np.where(inc[None, :], ws, 0.0)
    csum = np.zeros_like(held)
    csum[:, 1:] = np.cumsum(held, axis=1)[:, :-1]
    count = np.zeros(n)
    count[1:] = np.cumsum(inc.astype(np.float64))[:-1]
    return (prior * np.asarray(wbar, dtype=np.float64)[:, None] + csum) / (prior + count)[None, :]


def alpha(rg: Any, gap: Any, ws: Any, R: Any, mu: Any, wbar: Any, *, include: Any = None,
          prior: int = PRIOR) -> tuple[Any, Any]:
    """THE TIMING ALPHA (section 2, step 2), per symbol: (a, a15) over n days, a_t = rg_t - sum_s ws_st mu_s -
    sum_s what_st (R_st - mu_s), a15 = a - gap (gap = r - r15: the stress leg's extra cost). `rg` the day's net return
    less the haircut; `ws`, `R` (S, n); `mu`, `wbar` (S,). For pure exposure P&L (rg = sum_s ws R less costs) a_t is
    sum_s (ws_st - what_st)(R_st - mu_s) less the costs: a static tilt earns none."""
    import numpy as np

    rg = np.asarray(rg, dtype=np.float64)
    ws = np.asarray(ws, dtype=np.float64)
    R = np.asarray(R, dtype=np.float64)
    mu = np.asarray(mu, dtype=np.float64)
    what = w_hat(ws, wbar, include=include, prior=prior)
    a = rg - (ws * mu[:, None]).sum(axis=0) - (what * (R - mu[:, None])).sum(axis=0)
    return a, a - np.asarray(gap, dtype=np.float64)


def sigma_tilde(sigmas: Sequence[float]) -> float | None:
    """sigma_tilde = 1 / median(1 / sigma_j) over the cell's founders (each held at `SIGMA_FLOOR` at least, so no
    weight is infinite); None with no founder."""
    vals = sorted(1.0 / max(float(s), SIGMA_FLOOR) for s in sigmas if s is not None and math.isfinite(float(s)))
    if not vals:
        return None
    n = len(vals)
    med = vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2.0
    return 1.0 / med


def sigma_used(sigma: float, tilde: float | None) -> float:
    """sigma_used = max(sigma, `SIGMA_FLOOR`, sigma_tilde / 3): no member's weight exceeds 3x the founders' median."""
    out = max(float(sigma), SIGMA_FLOOR)
    if tilde is not None:
        out = max(out, float(tilde) / WEIGHT_CAP)
    return out


def train_sigma(eras: Sequence[tuple[Any, Any, Any, Any]], mu: Any, wbar: Any) -> float | None:
    """sigma (section 2, step 3): the sd (ddof 1) of a over the member's Train pools, what restarted at each era start.
    `eras`: (rg, gap, ws, R) a pool. None with fewer than 2 days or a series that is not finite."""
    import numpy as np

    parts = [alpha(rg, gap, ws, R, mu, wbar)[0] for rg, gap, ws, R in eras if len(rg)]
    if not parts:
        return None
    a = np.concatenate(parts)
    if len(a) < 2 or not np.isfinite(a).all():
        return None
    m = math.fsum(a.tolist()) / len(a)
    return math.sqrt(math.fsum(((a - m) ** 2).tolist()) / (len(a) - 1))


def cell_day(z: Any, active: Any) -> Any:
    """D_t (section 2, step 4): the equal-weight mean of z over the ACTIVE members (`active` (m, n) bool; an absent row's
    z is 0 and it counts); 0 where none is active."""
    import numpy as np

    z = np.asarray(z, dtype=np.float64)
    act = np.asarray(active, dtype=bool)
    n = act.sum(axis=0)
    return np.where(n > 0, np.where(act, z, 0.0).sum(axis=0) / np.maximum(n, 1), 0.0)


def t_stat(values: Sequence[float]) -> float | None:
    """T: mean / sd (ddof 1) x sqrt(n), every sum by math.fsum (fwd1_rule's)."""
    return F.t_stat(list(values))


def look(D: Sequence[float], D15: Sequence[float], k: int) -> dict[str, Any]:
    """{T, S15} over the first k cell days (ValueError when fewer)."""
    if len(D) < k or len(D15) < k:
        raise ValueError(f"a look at {k} needs {k} cell sessions")
    return {"T": t_stat(list(D[:k])), "S15": math.fsum(list(D15[:k]))}


def legs_pass(point: Mapping[str, Any], c_used_value: float | None) -> bool:
    """PASS_k without the placebo leg: T defined and >= c_used, fsum(D15_1..k) > 1e-12."""
    t = point.get("T")
    return c_used_value is not None and t is not None and float(t) >= float(c_used_value) and float(point["S15"]) > ZERO


def k_used(c_G: float, margin: float, k_own: int | None) -> int | None:
    """The bar on the grid (section 3.3): max(100 c_G, k_own + 100 margin); None (ineligible, stated) without an own
    floor or above `K_MAX`."""
    if k_own is None:
        return None
    k = max(int(round(float(c_G) * 100)), int(k_own) + int(round(float(margin) * 100)))
    return k if k <= K_MAX else None


def series_sha(days: Sequence[str], D: Sequence[float], D15: Sequence[float]) -> str:
    """The sha256 of a cell's D_1..k (the checkpoint of record of a non-final look: the word and this sha only): the
    canonical JSON of {"days", "D", "D15"}, floats in repr."""
    doc = {"days": [str(d) for d in days], "D": [repr(float(x)) for x in D], "D15": [repr(float(x)) for x in D15]}
    return hashlib.sha256(json.dumps(doc, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


# ----------------------------------------------------------------------------------------------------- correlations
def corr_common(a_days: Sequence[str], a: Sequence[float], b_days: Sequence[str], b: Sequence[float], *,
                min_common: int = 2 * WINDOW) -> float | None:
    """Pearson correlation of two daily series on their common days; None with fewer than `min_common` common days or
    a variance of zero."""
    import numpy as np

    left = {str(d): float(v) for d, v in zip(a_days, a)}
    pairs = [(left[str(d)], float(v)) for d, v in zip(b_days, b) if str(d) in left]
    if len(pairs) < max(2, int(min_common)):
        return None
    x = np.array([p[0] for p in pairs])
    y = np.array([p[1] for p in pairs])
    if not (np.isfinite(x).all() and np.isfinite(y).all()):
        return None
    x, y = x - x.mean(), y - y.mean()
    den = math.sqrt(float((x * x).sum()) * float((y * y).sum()))
    return None if not den > 0 else float((x * y).sum()) / den


def mean_series(series: Sequence[tuple[Sequence[str], Sequence[float]]]) -> tuple[list[str], list[float]]:
    """The founders' Train D: on each day, the mean of the members' values that day (days in order)."""
    sums: dict[str, list[float]] = {}
    for days, values in series:
        for d, v in zip(days, values):
            sums.setdefault(str(d), []).append(float(v))
    days = sorted(sums)
    return days, [math.fsum(sums[d]) / len(sums[d]) for d in days]


def assign(z: tuple[Sequence[str], Sequence[float]], cells: Mapping[str, tuple[Sequence[str], Sequence[float]]],
           rho_assign: float) -> tuple[str | None, dict[str, float | None]]:
    """THE ASSIGNMENT (section 1.1): (the clocked cell of the lineage's group whose founders' Train D its Train z
    correlates with most, when that is >= rho_assign, else None: it counts toward a new cell under its declared
    class), with every cell's correlation. `cells`: {cell: (days, founders' Train D)}, its own group's only."""
    found = {cell: corr_common(z[0], z[1], d[0], d[1]) for cell, d in sorted(cells.items())}
    best = max(((v, c) for c, v in found.items() if v is not None), default=None)
    if best is None or not best[0] >= float(rho_assign):
        return None, found
    return best[1], found


def merge_copy(z: tuple[Sequence[str], Sequence[float]], program_sha: str,
               earlier: Sequence[tuple[str, int, tuple[Sequence[str], Sequence[float]] | None, str]]) -> str | None:
    """THE HOUSE'S COPY MERGE (section 1.3): the earliest member (by pid) of `earlier` ((lineage, pid, Train z, program
    sha)) whose Train z correlates >= `COPY_RHO` with this one's on common sessions, or whose program sha is this
    one's; None when none."""
    for lineage, _pid, other, sha in sorted(earlier, key=lambda row: int(row[1])):
        if str(sha) == str(program_sha):
            return lineage
        if other is not None:
            c = corr_common(z[0], z[1], other[0], other[1])
            if c is not None and c >= COPY_RHO:
                return lineage
    return None


# ------------------------------------------------------------------------------------------------------- the clusters
def _pair_mean(values: Sequence[float | None]) -> float | None:
    vals = [float(v) for v in values if v is not None]
    return math.fsum(vals) / len(vals) if vals else None


def member_join(clusters: Mapping[str, Mapping[str, Sequence[tuple[Sequence[str], Sequence[float]]]]]) -> list[list[str]]:
    """THE MEMBER RULE (section 1.4), by average linkage: two clusters join when the mean correlation of their members'
    Train z ACROSS them is above zero and at least half the smaller of their WITHIN figures (each cluster's: the mean
    over its cells of the mean within-cell member-pair correlation). Repeatedly the qualifying pair with the largest
    cross mean is joined (a joined cluster's within is the mean over all its cells). `clusters` {cid: {cell: [member
    z]}}. -> the groups of cluster ids, each sorted, in order of their first id."""
    cells: dict[str, list[list[tuple[Sequence[str], Sequence[float]]]]] = {
        cid: [list(m) for _, m in sorted(by.items())] for cid, by in clusters.items()}
    pair_cache: dict[tuple[int, int], float | None] = {}
    flat: list[tuple[Sequence[str], Sequence[float]]] = []
    ids: dict[str, list[list[int]]] = {}
    for cid, cs in cells.items():
        ids[cid] = []
        for members in cs:
            idx = []
            for m in members:
                flat.append(m)
                idx.append(len(flat) - 1)
            ids[cid].append(idx)

    def corr(i: int, j: int) -> float | None:
        key = (min(i, j), max(i, j))
        if key not in pair_cache:
            pair_cache[key] = corr_common(flat[i][0], flat[i][1], flat[j][0], flat[j][1])
        return pair_cache[key]

    def within(groups: list[list[int]]) -> float | None:
        per = [_pair_mean([corr(a, b) for x, a in enumerate(g) for b in g[x + 1:]]) for g in groups]
        return _pair_mean(per)

    groups: dict[str, tuple[list[str], list[list[int]]]] = {cid: ([cid], ids[cid]) for cid in sorted(ids)}
    while True:
        best = None
        keys = sorted(groups)
        for x, a in enumerate(keys):
            for b in keys[x + 1:]:
                ma = [i for g in groups[a][1] for i in g]
                mb = [i for g in groups[b][1] for i in g]
                cross = _pair_mean([corr(i, j) for i in ma for j in mb])
                wa, wb = within(groups[a][1]), within(groups[b][1])
                if cross is None or wa is None or wb is None:
                    continue
                if cross > 0 and cross >= 0.5 * min(wa, wb) and (best is None or cross > best[0]):
                    best = (cross, a, b)
        if best is None:
            break
        _, a, b = best
        groups[a] = (sorted(groups[a][0] + groups[b][0]), groups[a][1] + groups[b][1])
        del groups[b]
    return sorted((sorted(g[0]) for g in groups.values()), key=lambda g: g[0])


@dataclass(frozen=True)
class Caps:
    cap: float
    wall: float
    report_only: bool
    u_point: float
    u_bound: float


def caps(u_point: float, u_bound: float) -> Caps:
    """THE CAPS (section 7.2): CAP_u = 0.12 - U_u, WALL_u = 0.15 - U_u(97.5%); a cluster whose U_u point is 0.12 or
    more is REPORT-ONLY, judged at CAP 0.12 and WALL 0.15 for the operator's report alone."""
    p, b = float(u_point), float(u_bound)
    if p >= CAP - 1e-12:
        return Caps(cap=CAP, wall=WALL, report_only=True, u_point=p, u_bound=b)
    return Caps(cap=CAP - p, wall=WALL - b, report_only=False, u_point=p, u_bound=b)


def joined_u(parts: Sequence[tuple[float, float]]) -> tuple[float, float]:
    """U_u of clusters joined at a look (section 1.4: "their joint floor and U_u are recomputed"): the union bound of
    their parts (the sum, at most 1), an upper bound of the union's rate, so a cap only falls."""
    return min(1.0, math.fsum(p for p, _ in parts)), min(1.0, math.fsum(b for _, b in parts))


# ------------------------------------------------------------------------------------------------------- the own floor
@dataclass(frozen=True)
class Era:
    """One Train era of one member, aligned: `days` ISO in order; `rg` its k 1.0 return less the haircut, `gap` r - r15,
    `ws` and `R` (S, n) per-symbol exposure and cost-free return, `hs` (S,) half-spreads (N1's recomputed costs)."""

    days: tuple[str, ...]
    rg: Any
    gap: Any
    ws: Any
    R: Any
    hs: Any


@dataclass(frozen=True)
class FloorMember:
    """A unit's member as the own floor reads it: its lineage, cell, join offset (the cell session it joined at, 0 for
    a founder), its frozen mu, wbar (S,), sigma_used and haircut g (a fraction a side), and its two eras (None: no
    history there)."""

    key: str
    cell: str
    join: int
    mu: Any
    wbar: Any
    sigma: float
    g: float
    eras: tuple[Era | None, ...]


@dataclass(frozen=True)
class Market:
    """One era's market series for the regime cells, aligned to `days`: SPY's daily return, the sector ETFs' (k, n;
    NaN where a symbol has no return), TLT's and GLD's."""

    days: tuple[str, ...]
    spy: Any
    sectors: Any
    tlt: Any
    gld: Any


def _sub(era: Era, keep: Sequence[int]) -> Era:
    import numpy as np

    k = np.asarray(keep, dtype=np.int64)
    return Era(days=tuple(era.days[i] for i in keep), rg=np.asarray(era.rg)[k], gap=np.asarray(era.gap)[k],
               ws=np.asarray(era.ws)[:, k], R=np.asarray(era.R)[:, k], hs=np.asarray(era.hs))


def aligned(members: Sequence[FloorMember], markets: Sequence[Market]) -> tuple[list[FloorMember], list[Market]]:
    """The unit's Train pools aligned by date (section 3.3): in each era the days every member with history there
    and the market have; a member with none in an era has None there."""
    import numpy as np

    out_members = list(members)
    out_markets = []
    for e, market in enumerate(markets):
        common = set(market.days)
        for m in members:
            if e < len(m.eras) and m.eras[e] is not None:
                common &= set(m.eras[e].days)
        days = tuple(sorted(common))
        idx = [i for i, d in enumerate(market.days) if d in common]
        out_markets.append(Market(days=days, spy=np.asarray(market.spy)[idx],
                                  sectors=np.asarray(market.sectors)[:, idx] if np.asarray(market.sectors).size
                                  else np.zeros((0, len(idx))), tlt=np.asarray(market.tlt)[idx],
                                  gld=np.asarray(market.gld)[idx]))
        for j, m in enumerate(out_members):
            era = m.eras[e] if e < len(m.eras) else None
            if era is None:
                continue
            keep = [i for i, d in enumerate(era.days) if d in common]
            eras = list(m.eras)
            eras[e] = _sub(era, keep)
            out_members[j] = FloorMember(key=m.key, cell=m.cell, join=m.join, mu=m.mu, wbar=m.wbar, sigma=m.sigma,
                                         g=m.g, eras=tuple(eras))
    return out_members, out_markets


def window_alpha(rg: Any, gap: Any, ws: Any, R: Any, mu: Any, wbar: Any, *, L: int = WINDOW,
                 prior: int = PRIOR) -> tuple[Any, Any]:
    """(A, A15), each (W, L): the alpha of every contiguous L-window of one era, what restarted at the window start
    (`alpha` over [s, s + L) for every s; exactly, by prefix sums: what_st = (prior wbar + C_t - C_s) / (prior + t - s),
    C the exclusive cumulative exposure)."""
    import numpy as np
    from numpy.lib.stride_tricks import sliding_window_view as view

    rg = np.asarray(rg, dtype=np.float64)
    gap = np.asarray(gap, dtype=np.float64)
    ws = np.asarray(ws, dtype=np.float64)
    R = np.asarray(R, dtype=np.float64)
    mu = np.asarray(mu, dtype=np.float64)
    wbar = np.asarray(wbar, dtype=np.float64)
    n = rg.shape[0]
    W = n - L + 1
    if W < 1:
        return np.zeros((0, L)), np.zeros((0, L))
    e = R - mu[:, None]
    x = rg - (ws * mu[:, None]).sum(axis=0)
    C = np.zeros_like(ws)
    C[:, 1:] = np.cumsum(ws, axis=1)[:, :-1]
    u = (wbar[:, None] * e).sum(axis=0)
    v = (C * e).sum(axis=0)
    M = np.einsum("sw,swl->wl", C[:, :W], view(e, L, axis=1))
    denom = prior + np.arange(L, dtype=np.float64)[None, :]
    A = view(x, L) - (prior * view(u, L) + view(v, L) - M) / denom
    return A, A - view(gap, L)


def era_alpha(rg: Any, gap: Any, ws: Any, R: Any, mu: Any, wbar: Any, *, prior: int = PRIOR) -> Any:
    """The era-restart alpha of one era (what restarted at its first session): `alpha`'s a."""
    return alpha(rg, gap, ws, R, mu, wbar, prior=prior)[0]


def n1_path(era: Era, offset: int, g: float) -> Era:
    """N1's rolled era (section 4.3): every symbol's weight rolled circularly by `offset` sessions (w'_t = w_{t-offset}),
    its P&L recomputed by close-to-close legs: rg' = sum_s w'_s R_s - (hs_s + g) |dw'_s|, gap' = 0.5 hs_s |dw'_s| (the
    stress leg 1.5 hs), the first session's change from flat."""
    import numpy as np

    ws = np.roll(np.asarray(era.ws, dtype=np.float64), int(offset), axis=1)
    R = np.asarray(era.R, dtype=np.float64)
    hs = np.asarray(era.hs, dtype=np.float64)[:, None]
    dw = np.abs(np.diff(np.concatenate([np.zeros((ws.shape[0], 1)), ws], axis=1), axis=1))
    rg = (ws * R).sum(axis=0) - ((hs + float(g)) * dw).sum(axis=0)
    gap = (0.5 * hs * dw).sum(axis=0)
    return Era(days=era.days, rg=rg, gap=gap, ws=ws, R=R, hs=era.hs)


def n1_offsets(n: int) -> tuple[int, ...]:
    """The N1 offsets an era of n sessions draws from: those of `N1_OFFSETS` under n - `WINDOW`."""
    return tuple(o for o in N1_OFFSETS if o < n - WINDOW)


def _window_returns(x: Any, L: int) -> Any:
    import numpy as np
    from numpy.lib.stride_tricks import sliding_window_view as view

    return np.prod(1.0 + view(np.asarray(x, dtype=np.float64), L), axis=1) - 1.0


def regime_stats(market: Market, *, L: int = WINDOW) -> dict[str, Any]:
    """Every window's regime statistics (the module docstring): {"vol", "ret", "disp", "tltgld"}, each (W,)."""
    import numpy as np
    from numpy.lib.stride_tricks import sliding_window_view as view

    spy = np.asarray(market.spy, dtype=np.float64)
    n = len(spy)
    if n < L:
        return {a: np.zeros(0) for a in AXES}
    vol = view(spy, L).std(axis=1, ddof=1)
    ret = _window_returns(spy, L)
    sec = np.asarray(market.sectors, dtype=np.float64)
    W = n - L + 1
    disp = np.full(W, np.nan)
    if sec.size:
        for s in range(W):
            block = sec[:, s:s + L]
            full = np.isfinite(block).all(axis=1)
            if full.sum() >= 2:
                disp[s] = float(block[full].std(axis=0, ddof=1).mean())
    tltgld = _window_returns(market.tlt, L) - _window_returns(market.gld, L)
    return {"vol": vol, "ret": ret, "disp": disp, "tltgld": tltgld}


def regime_labels(stats: Mapping[str, Any], cuts: Mapping[str, tuple[float, float]], axes: Sequence[str]) -> dict[str, Any]:
    """Each axis's tercile label (0, 1, 2) of every window at the receipt's cutpoints: 0 at or under q1, 1 at or under
    q2, else 2; -1 where the statistic is not finite (no regime cell)."""
    import numpy as np

    out = {}
    for axis in axes:
        x = np.asarray(stats[axis], dtype=np.float64)
        q1, q2 = cuts[axis]
        lab = np.where(x <= q1, 0, np.where(x <= q2, 1, 2))
        out[axis] = np.where(np.isfinite(x), lab, -1)
    return out


def unit_axes(cells: Iterable[str]) -> tuple[str, ...]:
    """The regime axes of a unit: SPY's volatility and return always; dispersion with a sector cell; the TLT-GLD gap
    with a defensive cell (6 or 9 regime cells)."""
    groups = {str(c).split("/")[-1] for c in cells}
    return ("vol", "ret") + (("disp",) if "sectors" in groups else ()) + (("tltgld",) if "defensive" in groups else ())


def _best_T(D: Any, D15: Any) -> Any:
    """(W,): the largest T_k over the plan of one cell's (W, L) D whose stress sum is above 1e-12; -inf where none."""
    import numpy as np

    best = np.full(D.shape[0], -np.inf)
    for k in PLAN:
        x = D[:, :k]
        m = x.mean(axis=1)
        sd = x.std(axis=1, ddof=1)
        with np.errstate(divide="ignore", invalid="ignore"):
            t = m / sd * math.sqrt(k)
        ok = (sd >= ZERO) & np.isfinite(t) & (D15[:, :k].sum(axis=1) > ZERO)
        best = np.maximum(best, np.where(ok, t, -np.inf))
    return best


def _cell_D(zs: Sequence[tuple[Any, Any, int]], L: int) -> tuple[Any, Any]:
    """One cell's (W, L) D and D15 from its members' (Z, Z15, join) (each (W, L)): the mean over the members active at
    each window session (a member joins at its join offset)."""
    import numpy as np

    W = zs[0][0].shape[0]
    num = np.zeros((W, L))
    num15 = np.zeros((W, L))
    cnt = np.zeros(L)
    for Z, Z15, join in zs:
        act = np.arange(L) >= int(join)
        num += np.where(act[None, :], Z, 0.0)
        num15 += np.where(act[None, :], Z15, 0.0)
        cnt += act
    cnt = np.maximum(cnt, 1)
    return num / cnt[None, :], num15 / cnt[None, :]


def _world_T(members: Sequence[FloorMember], markets: Sequence[Market], null: str, *, axes: Sequence[str],
             cuts: Mapping[str, tuple[float, float]], L: int = WINDOW, offsets: Mapping[int, Sequence[int]] | None = None
             ) -> tuple[Any, dict[str, Any]]:
    """Every world's best T for one null (`own_floor`), with each world's regime labels: (T (worlds,), {axis: labels}).
    Worlds are the windows of each era (N0, N0R) or (window, offset) pairs (N1; `offsets` {era: offsets}, default every
    offset the era draws from)."""
    import numpy as np

    Ts: list[Any] = []
    labels: dict[str, list[Any]] = {a: [] for a in axes}
    cells = sorted({m.cell for m in members})
    # the long-run constants of N0 and N0R (era-restart alpha over both pools; N0R inside each SPY-vol tercile)
    n0: dict[str, float] = {}
    n0r: dict[str, dict[int, float]] = {}
    if null in ("N0", "N0R"):
        per_member: dict[str, list[Any]] = {m.key: [] for m in members}
        incl: dict[str, list[tuple[Any, Any]]] = {m.key: [] for m in members}
        for e, market in enumerate(markets):
            if len(market.days) < L:
                continue
            vlab = regime_labels(regime_stats(market, L=L), cuts, ("vol",))["vol"]
            for m in members:
                era = m.eras[e] if e < len(m.eras) else None
                if era is None:
                    continue
                a = era_alpha(era.rg, era.gap, era.ws, era.R, m.mu, m.wbar)
                per_member[m.key].append(a)
                if null == "N0R":
                    # each session weighted by how many windows of each tercile hold it
                    for k in range(3):
                        starts = np.nonzero(vlab == k)[0]
                        cnt = np.zeros(len(a) + 1)
                        np.add.at(cnt, starts, 1.0)
                        np.add.at(cnt, starts + L, -1.0)
                        incl[m.key].append((k, (np.cumsum(cnt)[:len(a)], a)))
        for m in members:
            if per_member[m.key]:
                allx = np.concatenate(per_member[m.key])
                n0[m.key] = math.fsum(allx.tolist()) / len(allx)
            if null == "N0R":
                n0r[m.key] = {}
                for k in range(3):
                    num = math.fsum(math.fsum((w * a).tolist()) for kk, (w, a) in incl[m.key] if kk == k)
                    den = math.fsum(math.fsum(w.tolist()) for kk, (w, a) in incl[m.key] if kk == k)
                    n0r[m.key][k] = num / den if den > 0 else n0.get(m.key, 0.0)
    for e, market in enumerate(markets):
        if len(market.days) < L:
            continue
        stats = regime_stats(market, L=L)
        lab = regime_labels(stats, cuts, tuple(axes) + (() if "vol" in axes else ("vol",)))
        offs = (offsets or {}).get(e) if offsets is not None else None
        variants = [None] if null != "N1" else list(offs if offs is not None else n1_offsets(len(market.days)))
        for off in variants:
            best = None
            for cell in cells:
                zs = []
                for m in members:
                    if m.cell != cell:
                        continue
                    era = m.eras[e] if e < len(m.eras) else None
                    if era is None:
                        continue
                    if null == "N1":
                        era = n1_path(era, int(off), m.g)
                    A, A15 = window_alpha(era.rg, era.gap, era.ws, era.R, m.mu, m.wbar, L=L)
                    if null == "N0":
                        A, A15 = A - n0.get(m.key, 0.0), A15 - n0.get(m.key, 0.0)
                    elif null == "N0R":
                        g = np.array([n0r[m.key].get(int(k), n0.get(m.key, 0.0)) for k in lab["vol"]])[:, None]
                        A, A15 = A - g, A15 - g
                    zs.append((A / m.sigma, A15 / m.sigma, m.join))
                if not zs:
                    continue
                D, D15 = _cell_D(zs, L)
                bt = _best_T(D, D15)
                best = bt if best is None else np.maximum(best, bt)
            if best is None:
                continue
            Ts.append(best)
            for a in axes:
                labels[a].append(lab[a])
    if not Ts:
        return np.zeros(0), {a: np.zeros(0, dtype=np.int64) for a in axes}
    return np.concatenate(Ts), {a: np.concatenate(v) for a, v in labels.items()}


def grid(T: Any) -> Any:
    """Each world's grid index: the largest k with k / 100 <= T (fwd1_rule's), -1 for -inf or below 0."""
    return F._grid(T)


def _floor_k(g: Any, cap: float) -> int | None:
    """The smallest grid k with #(g >= k) <= cap x worlds (exact rationals); None with no world or none <= `K_MAX`."""
    import numpy as np

    worlds = int(len(g))
    if worlds == 0:
        return None
    capq = Fraction(repr(float(cap))) if not isinstance(cap, Fraction) else cap
    cnt = np.zeros(K_MAX + 2, dtype=np.int64)
    np.add.at(cnt, g[g >= 0], 1)
    passes = cnt[:K_MAX + 1][::-1].cumsum()[::-1]
    for k in range(K_MAX + 1):
        if Fraction(int(passes[k])) <= capq * worlds:
            return k
    return None


def floors(g: Any, labels: Mapping[str, Any], cap: float) -> dict[str, Any]:
    """The POOLED floor (every world) and the R-REG floor (the largest, over every regime cell of every axis with a
    world, of the cell's smallest k meeting the cap), with the cells' own: {"POOLED", "R-REG", "cells"}."""
    import numpy as np

    pooled = _floor_k(g, cap)
    out: dict[str, Any] = {"POOLED": pooled, "cells": {}}
    per: list[int | None] = []
    for axis, lab in labels.items():
        for k in range(3):
            sel = np.asarray(lab) == k
            if not sel.any():
                continue                                   # a regime cell with no world sets no floor
            fk = _floor_k(g[sel], cap)
            out["cells"][f"{axis}{k}"] = fk
            per.append(fk)
    if any(fk is None for fk in per):
        out["R-REG"] = None                                # a regime cell no grid bar holds: none holds the unit
    else:
        out["R-REG"] = max([pooled] + per) if pooled is not None else None   # type: ignore[type-var]
    return out


def _stationary(rng: Any, n: int, block: int) -> Any:
    """A stationary bootstrap's index sequence of length n (circular; a new block starts with probability 1/block)."""
    import numpy as np

    out = np.empty(n, dtype=np.int64)
    jumps = rng.random(n) < (1.0 / float(block))
    starts = rng.integers(0, n, size=n)
    cur = int(starts[0])
    for i in range(n):
        if i > 0:
            cur = int(starts[i]) if jumps[i] else (cur + 1) % n
        out[i] = cur
    return out


def _take(era: Era | None, idx: Any) -> Era | None:
    import numpy as np

    if era is None:
        return None
    return Era(days=tuple(era.days[i] for i in idx), rg=np.asarray(era.rg)[idx], gap=np.asarray(era.gap)[idx],
               ws=np.asarray(era.ws)[:, idx], R=np.asarray(era.R)[:, idx], hs=era.hs)


def unit_seed(unit: str) -> int:
    """The unit id a unit's bootstrap seeds read (`SEED_ROOT`, this, the draw): sha256 of the unit's name, 8 bytes."""
    return int.from_bytes(hashlib.sha256(str(unit).encode()).digest()[:8], "big")


def bootstrap_histograms(members: Sequence[FloorMember], markets: Sequence[Market], null: str, *, unit: str,
                         draws: Iterable[int], cuts: Mapping[str, tuple[float, float]], axes: Sequence[str],
                         block: int = BOOT_BLOCK, L: int = WINDOW) -> dict[int, dict[str, Any]]:
    """THE BOUND's resamples (the module docstring), `draws` of them (any subset of 0..B-1: a job may spread them over
    nights; each draw's seed is its own): {draw: {"worlds": n, "hist": {k: worlds at grid k}}} (k -1 for a world that
    passes at no grid value). Each cell's members drawn with replacement, each era's sessions by a stationary bootstrap,
    N1's offset drawn once an era; every window recomputed."""
    import numpy as np

    out: dict[int, dict[str, Any]] = {}
    by_cell: dict[str, list[FloorMember]] = {}
    for m in members:
        by_cell.setdefault(m.cell, []).append(m)
    uid = unit_seed(unit)
    for draw in draws:
        rng = np.random.default_rng([SEED_ROOT, uid, int(draw)])
        drawn: list[FloorMember] = []
        for cell in sorted(by_cell):
            pool = by_cell[cell]
            picks = rng.integers(0, len(pool), size=len(pool))
            for j, p in enumerate(picks):
                m = pool[int(p)]
                drawn.append(FloorMember(key=f"{m.key}#{j}", cell=m.cell, join=pool[j].join, mu=m.mu, wbar=m.wbar,
                                         sigma=m.sigma, g=m.g, eras=m.eras))
        new_markets: list[Market] = []
        idxs: list[Any] = []
        offsets: dict[int, list[int]] = {}
        for e, market in enumerate(markets):
            n = len(market.days)
            idx = _stationary(rng, n, block) if n else np.zeros(0, dtype=np.int64)
            idxs.append(idx)
            sec = np.asarray(market.sectors)
            new_markets.append(Market(days=market.days, spy=np.asarray(market.spy)[idx],
                                      sectors=sec[:, idx] if sec.size else sec, tlt=np.asarray(market.tlt)[idx],
                                      gld=np.asarray(market.gld)[idx]))
            if null == "N1":
                allowed = n1_offsets(n)
                offsets[e] = [int(rng.choice(allowed))] if allowed else []
        resampled = []
        for m in drawn:
            eras = []
            for e, era in enumerate(m.eras):
                if era is None or e >= len(idxs):
                    eras.append(None)
                    continue
                if null == "N1" and offsets.get(e):
                    era = n1_path(era, offsets[e][0], m.g)     # the timing killed on the era, then resampled
                eras.append(_take(era, idxs[e]))
            resampled.append(FloorMember(key=m.key, cell=m.cell, join=m.join, mu=m.mu, wbar=m.wbar, sigma=m.sigma,
                                         g=m.g, eras=tuple(eras)))
        # N1 already rolled: read the resampled worlds raw (one variant an era)
        T, _ = _world_T(resampled, new_markets, "RAW" if null == "N1" else null, axes=axes, cuts=cuts, L=L)
        g = grid(T)
        hist: dict[str, int] = {}
        for k in g.tolist():
            hist[str(int(k))] = hist.get(str(int(k)), 0) + 1
        out[int(draw)] = {"worlds": int(len(g)), "hist": hist}
    return out


def bound_k(hists: Mapping[int, Mapping[str, Any]], wall: float, *, start: int = 0) -> int | None:
    """The smallest grid k >= `start` at which the bootstrap's 97.5% bound of the pass share is at or under `wall`:
    at least ceil(39/40 x B) resamples have #(g >= k) <= wall x worlds (exact rationals). None with no resample or none
    <= `K_MAX`."""
    import numpy as np

    B = len(hists)
    if B == 0:
        return None
    need = math.ceil(BOOT_QUANTILE * B)
    wallq = Fraction(repr(float(wall)))
    tails = []
    for row in hists.values():
        cnt = np.zeros(K_MAX + 2, dtype=np.int64)
        for k, v in (row.get("hist") or {}).items():
            k = int(k)
            if k >= 0:
                cnt[min(k, K_MAX)] += int(v)
        tails.append((cnt[:K_MAX + 1][::-1].cumsum()[::-1], int(row.get("worlds") or 0)))
    for k in range(max(0, int(start)), K_MAX + 1):
        ok = sum(1 for passes, worlds in tails if worlds > 0 and Fraction(int(passes[k])) <= wallq * worlds)
        if ok >= need:
            return k
    return None


def own_floor(members: Sequence[FloorMember], markets: Sequence[Market], *, unit: str, floor_def: str,
              caps_: Caps, cuts: Mapping[str, tuple[float, float]], matched_k: int | None,
              hists: Mapping[str, Mapping[int, Mapping[str, Any]]] | None = None, L: int = WINDOW) -> dict[str, Any]:
    """THE OWN FLOOR c_own (section 3.3; the module docstring): for each null of `NULLS`, the floor of `floor_def`
    (R-REG or POOLED) at CAP_u, raised until the bootstrap's bound is at or under WALL_u (`hists` {null: {draw: ...}}:
    `bootstrap_histograms`' over all `BOOT_RESAMPLES` draws; without them the bound is not read and the floor waits);
    k_own = the largest over the nulls, at least the matched stand-in family's N1 floor (`matched_k`; None: waits).
    -> {"k_own" (None: waits or ineligible), "why", "nulls": {null: {"floor", "bound", "worlds", "cells"}}}."""
    aligned_members, aligned_markets = aligned(members, markets)
    axes = unit_axes(m.cell for m in members)
    out: dict[str, Any] = {"k_own": None, "why": None, "nulls": {}}
    best = None
    for null in NULLS:
        T, labels = _world_T(aligned_members, aligned_markets, null, axes=axes, cuts=cuts, L=L)
        g = grid(T)
        fl = floors(g, labels, caps_.cap)
        k_floor = fl[floor_def]
        row: dict[str, Any] = {"floor": k_floor, "worlds": int(len(g)), "cells": fl["cells"], "bound": None}
        out["nulls"][null] = row
        if k_floor is None:
            out["why"] = f"{null}: no grid bar holds CAP_u (no world, or none at or under 5.00)"
            return out
        boot = (hists or {}).get(null)
        if not boot or len(boot) < BOOT_RESAMPLES:
            out["why"] = f"{null}: the bootstrap's {BOOT_RESAMPLES} resamples are not all read"
            return out
        kb = bound_k(boot, caps_.wall, start=k_floor)
        row["bound"] = kb
        if kb is None:
            out["why"] = f"{null}: no grid bar holds WALL_u at the 97.5% bound"
            return out
        best = kb if best is None else max(best, kb)
    if matched_k is None:
        out["why"] = "the matched stand-in family's N1 floor is not in the receipt"
        return out
    out["k_own"] = max(int(best), int(matched_k))   # type: ignore[arg-type]
    return out


# ------------------------------------------------------------------------------------------------- the zeroed days
def binom_tail(x: int, n: int, p: float) -> float:
    """P(X >= x) for X ~ Binomial(n, p), exactly (math.comb, fsum)."""
    if x <= 0:
        return 1.0
    if x > n:
        return 0.0
    return min(1.0, math.fsum(math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(int(x), int(n) + 1)))


def mar_void(cells: Sequence[tuple[float, int, int]]) -> dict[str, Any]:
    """THE ZEROED-DAYS VOID (section 2.2): `cells` one (b_t, zeroed member-days, member-day slots) a cell session (b_t the
    session's benchmark |b|; zeroed: absent rows, audit marks, days not reproduced, a stopped member's left out). The
    sessions in the top decile of |b| (the ceil(k / 10) largest, ties by order) hold `top` of the `zeroed`; the unit is
    VOID when that share exceeds twice the overall share of slots on those sessions AND a one-sided binomial test of
    `top` against 10% gives p <= 0.05. -> {"void", "top", "zeroed", "share", "overall", "p", "by_decile"}."""
    k = len(cells)
    out: dict[str, Any] = {"void": False, "top": 0, "zeroed": 0, "share": None, "overall": None, "p": None,
                           "by_decile": []}
    if k == 0:
        return out
    order = sorted(range(k), key=lambda i: (-abs(float(cells[i][0])), i))
    ntop = max(1, math.ceil(k * MAR_DECILE))
    top = set(order[:ntop])
    zeroed = sum(int(c[1]) for c in cells)
    slots = sum(int(c[2]) for c in cells)
    ztop = sum(int(cells[i][1]) for i in top)
    stop = sum(int(cells[i][2]) for i in top)
    deciles = []
    for d in range(10):
        part = order[math.floor(d * k / 10):math.floor((d + 1) * k / 10)]
        deciles.append(sum(int(cells[i][1]) for i in part))
    out.update(top=ztop, zeroed=zeroed, by_decile=deciles)
    if zeroed == 0 or slots == 0:
        return out
    share = ztop / zeroed
    overall = stop / slots
    p = binom_tail(ztop, zeroed, float(MAR_DECILE))
    out.update(share=share, overall=overall, p=p, void=bool(share > MAR_FACTOR * overall and p <= MAR_P))
    return out


# ---------------------------------------------------------------------------------------------------------- stage 1
def newey_west_z(x: Sequence[float], lag: int = STAGE1_LAG) -> float | None:
    """A Newey-West z of a series' mean (Bartlett weights to `lag`): mean / sqrt(the HAC variance / n); None with fewer
    than lag + 2 values or a variance that is not above zero."""
    n = len(x)
    if n < lag + 2:
        return None
    m = math.fsum(x) / n
    d = [float(v) - m for v in x]
    g0 = math.fsum(v * v for v in d) / n
    var = g0
    for l in range(1, lag + 1):
        gl = math.fsum(d[t] * d[t - l] for t in range(l, n)) / n
        var += 2.0 * (1.0 - l / (lag + 1.0)) * gl
    if not var > 0:
        return None
    return m / math.sqrt(var / n)


def stage1(eras: Sequence[Sequence[float]], readable: int) -> dict[str, Any]:
    """STAGE 1 (section 5): the unit's pooled D on its founders' stored seen-span Train runs, one series an era; a
    Newey-West z (lag 5) an era; REFUTED when either era's z is -1.0 or lower. A unit with fewer than `M_MIN` members
    whose seen-span series could be read is not refuted. Refute only: it earns no FP credit."""
    zs = [newey_west_z(list(e)) for e in eras]
    if int(readable) < M_MIN:
        return {"z": zs, "refuted": False, "why": f"fewer than {M_MIN} readable seen-span series: not refuted"}
    refuted = any(z is not None and z <= STAGE1_Z for z in zs)
    return {"z": zs, "refuted": refuted, "why": "an era's Newey-West z at or under -1.0" if refuted else None}


# ---------------------------------------------------------------------------------------------------- the placebo leg
def placebo_seed(receipt_sha256: str, cell: str, k: int) -> int:
    """The placebo draw's seed (section 2.1): int.from_bytes(sha256(receipt | cell | k)[:16], "big")."""
    text = f"{receipt_sha256}|{cell}|{int(k)}"
    return int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:16], "big")


def placebo_draws(controls: int, m: int, seed: int, *, draws: int = PLACEBO_DRAWS) -> list[tuple[int, ...]]:
    """The 999 pseudo-cells: each `m` controls drawn WITHOUT replacement from `controls` (the group's skill-free
    controls), under `seed`. ValueError when m is above the controls there are."""
    import numpy as np

    if int(m) > int(controls) or int(m) < 1:
        raise ValueError(f"a pseudo-cell of {m} from {controls} controls")
    rng = np.random.default_rng(int(seed))
    return [tuple(int(i) for i in rng.choice(int(controls), size=int(m), replace=False)) for _ in range(int(draws))]


def placebo_count(T: float | None, pseudo: Sequence[float | None]) -> int | None:
    """#{pseudo-cells with T at or above the cell's}; an undefined pseudo T counts as below; None when T is undefined."""
    return F.placebo_count(T, pseudo)


def placebo_holds(count: int | None, draws: int) -> bool:
    """The leg holds when the draws are the law's 999 and at most 149 are at or above."""
    return count is not None and int(draws) == PLACEBO_DRAWS and int(count) <= PLACEBO_COUNT_MAX


def control_wbar(spec: Mapping[str, Any]) -> dict[str, float]:
    """A control's wbar_s (section 2.1): its exposure-grid target f spread evenly over its symbols, as its law draws a
    symbol uniformly at every entry."""
    syms = [str(s) for s in spec.get("symbols") or []]
    f = float(spec.get("f") or 0.0)
    return {s: f / len(syms) for s in syms} if syms else {}


# ---------------------------------------------------------------------------------------------------------- demotion
def demote(post: Sequence[float], post15: Sequence[float], every: Sequence[float]) -> str | None:
    """THE CELL DEMOTION (section 7.1 (2)) read at a post-pass count n = len(post) (a multiple of 20): DEMOTED when the
    post-pass T is -1.0 or lower or T over all the cell's sessions (`every`) is 0 or lower; at n 60 and 120 also when
    fsum(D15_post) is 0 or lower. The words of why, or None."""
    n = len(post)
    if n == 0 or n % DEMOTE_EVERY:
        return None
    tp, ta = t_stat(list(post)), t_stat(list(every))
    if tp is not None and tp <= DEMOTE_T_POST:
        return f"post-pass T at or under {DEMOTE_T_POST} after {n} post-pass sessions"
    if ta is not None and ta <= DEMOTE_T_ALL:
        return f"T over all cell sessions at or under {DEMOTE_T_ALL} after {n} post-pass sessions"
    if n in DEMOTE_STRESS_AT and not math.fsum(list(post15)) > 0:
        return f"the stress leg's post-pass sum at or under 0 at {n} post-pass sessions"
    return None


# ---------------------------------------------------------------------------------------------------------- the route
def on_pool_route(fwd1: Mapping[str, Any] | None, *, unit_judged: bool, refuted: bool, report_only: bool) -> bool:
    """THE POOL ROUTE (section 7.2): an ETF lineage FWD1 judges as case N (never sealed; `fwd1` its `fwd1_lineages`
    row with its `status`), with no FWD1-R pass, whatever checkpoint FWD1 has read, in a judged unit that stage 1 did
    not refute, of a cluster that is not report-only."""
    if not isinstance(fwd1, Mapping) or not unit_judged or refuted or report_only:
        return False
    return (str(fwd1.get("type")) == "ETF" and str(fwd1.get("case_")) == "N" and int(fwd1.get("judged") or 0) == 1
            and str(fwd1.get("status")) != "pass" and str(fwd1.get("status")) != "void")


# ------------------------------------------------------------------------------------------------------- the words
def words(cell: str, word: str) -> str:
    """The words a unit's verdict crosses as (ids and a word, no figure): "POOL1 unit <cell>: <word>"."""
    if word not in WORDS:
        raise ValueError(f"no POOL1 word {word!r}")
    return f"{NAME} unit {cell}: {word}"


def expected_passes(read: Sequence[tuple[str, int]], receipt: Receipt) -> float:
    """THE FLOOR-WIDE EXPECTED ZERO-EDGE PASSES (section 4.5): for each judged cluster (its id, the last look read), the
    receipt's zero-edge pass probability by that look, summed."""
    total = []
    for cid, k in read:
        curve = receipt.expected.get(str(cid))
        if curve is None or int(k) not in PLAN:
            continue
        total.append(float(curve[PLAN.index(int(k))]))
    return round(math.fsum(total), 4)


def _pct(x: Any) -> str:
    return "n/a" if x is None else f"{100.0 * float(x):.1f}"


def beside(receipt: Receipt, *, cell: str, cluster: str, k: int, T: float, c_used_value: float, own_t: float | None,
           passes: int, judged: int, expected: float, u_point: float, u_bound: float, bh_text: str = "") -> str:
    """THE SENTENCE BESIDE A POOLED TRADE (section 8; operator-only, it carries T and the program's own t)."""
    fig = receipt.beside.get(cluster) or {}
    return (f"{NAME} pooled screen (receipt {receipt.sha256[:12]}): cell {cell}, cluster {cluster}, passed at look {k} "
            f"of 40/60/120 counted cell sessions after the release that carries the receipt; T = {float(T):.2f} >= bar "
            f"{float(c_used_value):.2f}. The unit's measured zero-edge rate: {_pct(fig.get('fp_point'))}% (97.5% bound "
            f"{_pct(fig.get('fp_bound'))}%), worst Train-era regime cell {_pct(fig.get('fp_worst'))}% (no bound); under "
            f"N1 (drift kept) {_pct(fig.get('fp_n1'))}%. Power at member Sharpe 0.5: {_pct(fig.get('power_05'))}%, at "
            f"1.0: {_pct(fig.get('power_10'))}%. WEAK. Chosen within the cell by the Train-era close-rate key; ranked "
            f"at the roster by K. The program's own forward t: {'n/a' if own_t is None else f'{float(own_t):.2f}'} "
            f"(shown, never deciding). {passes} passes of {judged} units; {float(expected):.2f} expected at zero edge. "
            f"The cluster's U_u {_pct(u_point)}% (bound {_pct(u_bound)}%): pool plus U_u at most 12% point and 15% at "
            f"the bound. Contamination zero by construction for the judged sessions. {bh_text}").strip()


# ------------------------------------------------------------------------------------- the PREREG's names (11 P1 1)
def alpha_series(rg: Any, gap: Any, ws: Any, R: Any, mu: Any, wbar: Any, *, include: Any = None) -> tuple[Any, Any]:
    """`alpha` under the PREREG's name (section 11 P1 item 1)."""
    return alpha(rg, gap, ws, R, mu, wbar, include=include)


def member_z(a: Any, sigma_used_value: float) -> Any:
    """z_{i,t} = a_t / sigma_used,i (section 2, step 3)."""
    import numpy as np

    return np.asarray(a, dtype=np.float64) / float(sigma_used_value)


def t_k(D: Sequence[float], k: int) -> float | None:
    """T_k = mean / sd (ddof 1) x sqrt(k) of D_1..k by math.fsum (section 2, step 5); ValueError with fewer days."""
    return look(D, D, k)["T"]


def pass_k(D: Sequence[float], D15: Sequence[float], k: int, c_used_value: float | None, placebo_ok: bool) -> bool:
    """PASS_k (section 2, step 5): (a) T_k >= c_used, (b) fsum(D15_1..k) > 1e-12, (c) the placebo leg."""
    return legs_pass(look(D, D15, k), c_used_value) and bool(placebo_ok)


def u_cap(u_point: float, u_bound: float) -> Caps:
    """`caps` under the PREREG's name: CAP_u, WALL_u and report-only from U_u (section 7.2)."""
    return caps(u_point, u_bound)


def cluster(cells: Mapping[str, tuple[str, Sequence[tuple[Sequence[str], Sequence[float]]]]]) -> list[list[str]]:
    """THE CLUSTERS (section 1.4): every judged cell of one declared class is one cluster (the class rule), and clusters
    of different classes join by the member rule (`member_join`). `cells` {cell: (its class, its members' Train z)}.
    -> the clusters as sorted lists of cells, in order of their first cell."""
    by_class: dict[str, dict[str, Sequence[Any]]] = {}
    for cell, (cls, zs) in cells.items():
        by_class.setdefault(str(cls), {})[str(cell)] = zs
    groups = member_join(by_class)
    return sorted((sorted(c for cls in g for c in by_class[cls]) for g in groups), key=lambda g: g[0])


def route_of(fwd1: Mapping[str, Any] | None, *, unit_judged: bool, refuted: bool, report_only: bool) -> str:
    """"pool" on THE POOL ROUTE (`on_pool_route`), else "per_program" (S2 or FWD1-R, as today)."""
    return "pool" if on_pool_route(fwd1, unit_judged=unit_judged, refuted=refuted, report_only=report_only) \
        else "per_program"


# ------------------------------------------------------------------------------------------- what a generator may see
_DECIMAL = re.compile(r"\d+\.\d+|%|\bbp\b")


def figure_free(doc: Any, *, ints: Sequence[str] = ("version",), path: str = "") -> list[str]:
    """The places a document a generator-visible process reads holds a FIGURE (section 8: ids and words only): any
    float, any whole number but at a key of `ints`, any text with a decimal number, a "%" or "bp". [] when none."""
    found: list[str] = []
    if isinstance(doc, bool) or doc is None:
        return found
    if isinstance(doc, float):
        return [path or "<root>"]
    if isinstance(doc, int):
        return [] if path.rsplit(".", 1)[-1] in ints else [path or "<root>"]
    if isinstance(doc, str):
        return [path] if _DECIMAL.search(doc) else []
    if isinstance(doc, Mapping):
        for key, value in doc.items():
            if _DECIMAL.search(str(key)):
                found.append(f"{path}.{key}")
            found.extend(figure_free(value, ints=ints, path=f"{path}.{key}" if path else str(key)))
        return found
    if isinstance(doc, (list, tuple)):
        for i, value in enumerate(doc):
            found.extend(figure_free(value, ints=ints, path=f"{path}[{i}]"))
        return found
    return [path or "<root>"]


__all__ = ["NAME", "SCREEN", "PIN_BLOCK", "RECEIPT_PATH", "PREREG_SHA256", "PLAN", "WINDOW", "M_MIN", "PRIOR",
           "SIGMA_FLOOR", "WEIGHT_CAP", "GROUP_SHARE", "COPY_RHO", "NO_FREE_RIDE", "EXPOSURE_MIN", "CAP", "WALL",
           "STAGE1_Z", "STAGE1_LAG", "N1_OFFSETS", "PLACEBO_DRAWS", "PLACEBO_COUNT_MAX", "PLACEBO_CONTROLS",
           "MAR_FACTOR", "MAR_P", "BOOT_RESAMPLES", "BOOT_BLOCK", "DEMOTE_EVERY", "FLOORS", "MARGINS", "C_G_RANGE",
           "K_MAX", "BASE_GROUPS", "CLASSES_OUT", "EVENT_INPUT", "EVENT_FIELDS", "PASSING", "PENDING", "FINAL",
           "REPORT_ONLY", "INELIGIBLE", "WORDS", "U_COUNTS", "NULLS", "AXES", "CONSTANTS", "PIN_KEYS", "RECEIPT_KEYS", "Pin",
           "Founder", "UnitSpec", "ClusterSpec", "Receipt", "pin", "load", "parse_receipt", "load_receipt", "rule",
           "cell_name", "member_pid", "group_of", "reads_events", "excluded", "lot_exposure", "lot_sides", "w_hat",
           "alpha", "sigma_tilde", "sigma_used", "train_sigma", "cell_day", "t_stat", "look", "legs_pass", "k_used",
           "series_sha", "corr_common", "mean_series", "assign", "merge_copy", "member_join", "Caps", "caps",
           "joined_u", "Era", "FloorMember", "Market", "aligned", "window_alpha", "era_alpha", "n1_path",
           "n1_offsets", "regime_stats", "regime_labels", "unit_axes", "grid", "floors", "unit_seed",
           "bootstrap_histograms", "bound_k", "own_floor", "binom_tail", "mar_void", "newey_west_z", "stage1",
           "placebo_seed", "placebo_draws", "placebo_count", "placebo_holds", "control_wbar", "demote",
           "on_pool_route", "words", "expected_passes", "beside", "alpha_series", "member_z", "t_k", "pass_k", "u_cap",
           "cluster", "route_of", "figure_free"]
