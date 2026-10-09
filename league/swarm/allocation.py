"""THE ALLOCATOR (Release B, Oct 2026): research compute by expected information value, with structure and mechanism
diversity.

WHY. On Sept 30 the House's bandit put 0.75 of the allocation weight on one to three families whose validation t was
-0.73 to +0.33 (none at t >= 1), while 100% of the last eight hours' births were debit verticals. The weight barely moved
compute either: a family at 20x the average share ran 9 cycles an hour against 7 for one below half of it (the old turn
order bought a minute of head start per unit of relative share). This module replaces the bandit's share with a
deterministic allocation by expected information value, makes that share buy turns (`StrideTurns`, loop.py), lets the
number of researchers follow the queue of useful experiments and the spend plan (`effective_concurrency`), and caps the
births of one structure family (`BirthQuota`, architect.py).

THE SHARE (`value_shares`; `allocation.mode` "value", the default). Every living family's share of researcher turns and
Gym priority is the sum of three parts:
  - THE FLOOR (`floor_share`, 0.10) spread evenly and never capped: no family starves, so every family still reaches
    the rules that retire it;
  - THE EXPLORATION SHARE (`explore_share`, 0.35): breadth across MECHANISM CLASSES (structure x root group, the
    strategist's `mechanism_class`). Each class's slice is its families' value mass with diminishing returns in its size
    (the sum of their values over the square root of their number), then within a class by each family's value. So a
    small or unexplored class earns more a family than a crowded one, but only as much as its families' values justify:
    a class the account cannot open for real, or whose lineages are spent or deep, carries those discounts into its slice;
  - THE DECISION SHARE (the rest, 0.55) to every family by its value.
  Then the caps: no family above `family_cap` (0.05) and no mechanism class above `class_cap` (0.30) WHEN THE OTHER
  CLASSES CAN TAKE THE EXCESS. The excess goes to the families under both caps that are worth at least what the average
  unit of share buys (`relief`: the value-weighted mean value), in proportion to their values, none past `cap_boost` (3)
  times its own share (water-filling: a cap moves attention to other classes' families only where that does not dilute
  the information it funds). A cap relaxes when it cannot hold: at least 2/n a family and 1/k a class. What the family
  cap cuts that those families cannot take even with no class cap (they are the capped ones, or at their boost) is its
  SPILL (`family_cap_spill` in the report): it goes to every family under the family cap by value, the decision share's
  rule. When the class cap adds to what cannot be placed, it rises to the lowest level at which it adds nothing, the
  same level for every class (`class_cap_relaxed`); `class_cap_in_force` is that level, or the largest class's share
  when the spill took it past, and `largest_class` sets that class's share beside its share of the families. So the
  class cap binds at 30% only as far as other classes hold families worth the attention: while one or two classes are
  most of the population it rises (the Sept 30 replay: two classes held 70 of 78 living families).
  Exact ties are broken by value, then id, by a few parts in 10^12, so a "top N by weight" band holds N families.

THE VALUE of a family is the variance of its NEXT validation's pass or fail (the line's t check, `evidence.MIN_T`)
under an empirical-Bayes posterior, times three discounts:
  value = q (1 - q) x depth x exhaustion x execution, with p = P(next validation t >= MIN_T) and q = min(p, 1/2).
  - THE POSTERIOR. The validation t of every family validated in the last `lookback_hours` on the evaluator running now
    (its latest look; a look from another fingerprint is never pooled, even for attention) is a draw
    of (the family's true t) + (unit noise); a family's true t is its class's mean plus a within-class spread, and a
    class's mean is the swarm's mean plus a between-class spread. The swarm's mean and the two spreads are method-of-
    moments estimates from those looks, blended with the Sept 30 fit (PRIOR_*, worth PRIOR_LOOKS looks: an evidence reset
    starts from what the swarm last measured and moves to its own looks as they come, never jumping at a count). A
    family's own latest t (never when its validated version failed the drift screen) updates its prior; its class's
    statistics leave its own look out. The predictive of its next look adds the unit noise back. So a family near the
    line has p near 0.5 and the most value; a family far below it has almost none (R11-5's lesson without its rank
    weighting: an old family at zero or below never earns a large share); a young family draws its class's prior, and an
    UNEXPLORED class (no look) draws the swarm's mean with the widest spread. A family whose t check would pass but that
    is not at the gate and that the gate has not decided (another check of the line failed it) is as undecided as one
    on the line: q = min(p, 1/2), the most value. (Its look stays in its class's pool, as a drift-failed one's does.)
  - DEPTH = 1 / (1 + trials / `depth_trials` (80)), TRIALS BEING THE IDEA'S: its lineage set's now
    (`store.lineage_trials`: a fork's lineage, the dead lineages a new family was born on the slice of, and any lineage
    linked to it since, as a long_single's twins are; the count the deflated Sharpe records), and never fewer than its
    own plus those it inherited at birth (`inherited_trials`), so a reborn mechanism is not a young one. Sept 30 (40
    hours of the House's runs): the chance per trial of a family's first positive eligible Train version fell from
    0.35% over its first ten trials to 0.20% at 40-80 and none past 80, and first validations were 12.6% at t >= 1
    against 5% for second looks and 0 of 6 after (breadth beats depth; the Sept 29 ROI study: heavily worked versions
    validate weaker).
  - EXHAUSTION = 0 when the lineage has spent its holdout looks (`evidence.LOOKS_PER_LINEAGE`: the gate can never look
    again), 0.5 when its validated version failed the drift screen, 0.5 when THE GATE IS DONE WITH ITS VALIDATED
    VERSION (`gate_spent`: its holdout look failed, or the review refused it for lookahead, leakage or fill abuse; its t
    is then no evidence of the next look, so the family reads as an unvalidated one of its class, at half), 0.5 while
    its researcher holds in a streak (`hold_streak` >= 3: it says it has nothing to run). A family at the gate, with a
    look out, or outside the Gym band gets the floor only: the gate or its forward record decides it next, not research
    (the leaderboard lists such families first, so the architect's and strategist's first 60 rows always hold them).
  - EXECUTION: a family whose declared structure the account cannot open for real (`real_structures`, the constitution's
    `options_money.real_types` and `long_single`, whose every order is one of them) is worth `shadow_value` (0.5) of one
    it can: its pass could not trade real money until the owner's equity and grant change.
The allocation reads Validation's numbers exactly as the bandit did (into the weight only; researchers still see pass or
fail and a count of checks, D2a). The architect and the strategist see each family's share on the leaderboard, as they
did under the bandit, as `research_share` with a legend (it measures how undecided a family is and how fresh its idea,
not its evidence): among validated families it is a function of the validation t (it was then too), never the t
itself. Nothing on the way to validation, the gate, the bands or money reads the weight (practice.py's CannotPromote
test). The practice bonus (practice.py) rides on top of the caps as it rode on the bandit (at most +25% of a family's
share and 10% of all share: a capped family may sit up to a quarter above its cap). `allocation.mode` "bandit" restores
R11-5's Thompson bandit (`evidence.thompson`) with no deploy.

THE TURNS (`StrideTurns`, used by loop.Scheduler; `allocation.scheduler` "stride", the default). Start-time fair
queueing: a turn moves a family's finish tag 1 / (its share x n) past its start, and among the families ready now the
lowest start tag goes first; a family joining (born, back from a hold) starts at the virtual time (the last start
served), so it neither jumps the queue with credit it never earned nor waits behind the others' history. Under
contention a family's turns follow its share; without it every ready family runs. Nothing starves: the floor share
bounds every stride at 1 / `floor_share` (10) average strides. `max_wait_seconds` (0: off) optionally sends a ready family
that has had no turn for that long first; that turn is out of order, so it moves the family's own tag but never the
virtual time. "legacy" restores the minute-per-share head start.

THE CONCURRENCY (`effective_concurrency`). `researcher.concurrency` is the spend plan's level, and with no explicit
`plan_usd_per_hour` (null, the default) it is the level, full stop: the controller never expands or contracts on a plan
it was not given. With one, the research spend it drives (`RESEARCH_SPEND`: Sail models and Gym boxes in the last hour)
is measured against it: the level CONTRACTS in proportion while that spend runs over the plan, never below
`min_concurrency` (4), and EXPANDS up to `max_concurrency` (null: never) while distinct useful experiments wait and the
spend is under `expand_below` (0.8) of the plan. A USEFUL EXPERIMENT is a ready family whose value is at least
`useful_value` (0.5) of a fresh family's in an unexplored class (the tournament's last allocation names them; none
before its first round, and none under the bandit): its lineage has looks left, it is not deep, not holding, and it is
a structure real money can open, or its evidence makes up for it. Every worker the ceiling allows is started; the ones
above the effective level sleep. It cuts nothing by itself: the cut is a lower `researcher.concurrency`.

THE BIRTH QUOTA (`BirthQuota`, architect.py). A STRUCTURE FAMILY (`STRUCTURE_BUCKETS`: single = long_single, long_call,
long_put; butterfly; vertical; straddle; condor; calendar) may hold at most `births.max_share` (0.6) of the births of the
last `births.window_hours` (24) once there were `births.min_window` (10), and at most that share of a pass's want (one
quota a pass, the truncation retry's admits included); the first `births.per_pass_min` (1) of a structure family in a
pass is always allowed, so a pass is never barred outright. THE POPULATION GUARD: below `births.min_alive` living
families (null: three quarters of `population.start`: 36 at the default start of 48, 72 at a start of 96) the whole
quota rests, so proposals that stay one structure family can thin the population to the guard but never below it. The
architect's request shows the counts and which families are full (while `architect.structures` is set, only the
families of its types: `BirthQuota.text(allowed)`); a refused proposal is counted in the pass's event
(`structure_capped`).

THE DIRECTION QUOTA (release D-1, Oct 9, 2026; `DirectionQuota`, re-exported here beside `BirthQuota` from
league/swarm/dlane.py, the direction lane's protected home). Across the two research lanes rather than the structure
families: while the direction lane is behind `dlane.birth_share` (0.5) of the last `dlane.window_hours` (24) of births and
fewer than `dlane.max_alive` (24) direction families live, the first max(`dlane.min_per_pass`, ceil(0.5 x want)) births
of a pass are reserved for direction and never filled with alpha; the lane never holds more than `dlane.max_share` (0.6)
of the window (once it holds `dlane.min_window` births) nor of the pass. It reads the `lane` of the window's `swarm.born`
payloads (absent: alpha). The architect holds a pass to both quotas (`Architect.lane_quota`); with `dlane.mode` "off" it
builds none, so every birth is admitted as before.

THE LEARNING GAME (Oct 8, 2026; league/swarm/game.py). A game-arm family in mode "gate" never feeds its Validation t into
its own row (`row_of`'s `blind`, set by `allocate_from_store`): its share comes from its class prior and the discounts
alone, so compute never follows a version the game's private confirmation sent to Validation. Its depth reads its
lineage's trials without the game's children beside it (`game.shown_trials`): a parent's share never falls because it
bred. Control and legacy families, and the game off or in "shadow", read exactly as before.

Every knob lives in swarm.json's `allocation` block (read every loop, no deploy; `settings.py` has no entry: this module's
DEFAULTS are the defaults, and a misread value falls back to its default). Standard library only. Nothing on the live
path imports this module.
"""

from __future__ import annotations

import math
import time
from typing import Any, Callable, Iterable, Mapping, Sequence

from . import evidence, game
from .dlane import DirectionQuota  # THE DIRECTION QUOTA (the module docstring), beside `BirthQuota`; its code is dlane.py's

# ---------------------------------------------------------------------------------------------------------------- settings
DEFAULTS: dict[str, Any] = {
    "mode": "value",             # "value" | "bandit" (R11-5's Thompson bandit, evidence.thompson)
    "floor_share": 0.10,         # spread evenly over every living family
    "explore_share": 0.35,       # families without their own usable validation evidence, split by class first
    "family_cap": 0.05,          # the most share one family may hold (about 4x the average at 80 families)
    "class_cap": 0.30,           # the most share one mechanism class (structure x root group) may hold
    "cap_boost": 3.0,            # a family takes at most this multiple of its own share from the caps' excess
    "depth_trials": 80,          # the idea's trials (own + inherited) at which the depth discount halves a family's value
    "hold_streak": 3,            # a hold streak this long halves a family's value
    "lookback_hours": 168,       # the validations the posterior learns from
    # The structures real money can open (the constitution's options_money.real_types under $2,000 of equity, and
    # long_single, whose every order is a long call or put); any other structure's value is `shadow_value` of theirs.
    "real_structures": ["debit_vertical", "long_butterfly", "long_call", "long_put", "long_single"],
    "shadow_value": 0.5,
    "useful_value": 0.5,         # a useful experiment: at least this fraction of a fresh family's value in an unexplored class
    "scheduler": "stride",       # "stride" | "legacy"
    "max_wait_seconds": 0,       # 0: off (the floor share already bounds every wait); else a ready family waiting this long goes first
    "max_concurrency": None,     # null: never above researcher.concurrency
    "min_concurrency": 4,
    "plan_usd_per_hour": None,   # null: no plan, so neither expansion nor contraction (researcher.concurrency is the level)
    "expand_below": 0.8,
    # min_alive null: three quarters of population.start (36 at the default start of 48); below it the whole quota rests.
    "births": {"max_share": 0.6, "window_hours": 24, "min_window": 10, "per_pass_min": 1, "min_alive": None},
}
#: What the planners (the architect's LIVING FAMILIES, the strategist's BOARD) are told a family's `research_share` is:
#: under Release B it measures how undecided a family is, not how well it did (verification of #448).
SHARE_LEGEND = ("research_share is the family's share of research turns: how undecided its next validation is and how "
                "untried its idea, never a measure of its evidence or success; families at the gate or beyond hold the "
                "floor share and lead the list")
#: The spend kinds the researchers' concurrency drives (a cycle's Sail model calls and the Gym boxes its Train jobs keep
#: busy): THE CONCURRENCY's plan is measured against their sum over the last hour.
RESEARCH_SPEND = ("sail_model", "gym_box")
MODES = ("value", "bandit")
SCHEDULERS = ("stride", "legacy")
#: The posterior's defaults, and the bounds on its estimates. They are the fit to the House's 119 latest validation looks
#: of the week to 16:00Z Sept 30 (mean -0.97, between-class variance 0.09, within-class 2.84; median t -0.68), worth
#: PRIOR_LOOKS looks: the estimates blend them with the running evaluator's own looks (n of them) at n / (n + PRIOR_LOOKS),
#: so after an evidence reset the allocation starts where the swarm last measured and never jumps at a count. Below
#: MIN_OBS looks the moments are not computed at all.
MIN_OBS = 3
PRIOR_LOOKS = 20
PRIOR_MEAN = -0.97
PRIOR_BETWEEN = 0.09   # between-class variance of the class means
PRIOR_WITHIN = 2.84    # within-class variance of the families' true t
MEAN_BOUNDS = (-3.0, 1.0)
VAR_BOUNDS = (0.05, 4.0)
NOISE = 1.0            # a validation t's own sampling variance
#: A validation t is read inside +-T_CLIP: a near-constant daily series can report a t of -1,509 (Sept 30), which says no
#: more about the line than -6 does and would swamp the moments.
T_CLIP = 6.0


def clip_t(t: Any) -> float | None:
    """A validation t as the posterior reads it: finite, inside +-T_CLIP; None when it is not a number."""
    if isinstance(t, bool) or not isinstance(t, (int, float)) or not math.isfinite(float(t)):
        return None
    return max(-T_CLIP, min(T_CLIP, float(t)))


#: What the value discounts a family by (EXHAUSTION in the module docstring).
DRIFT_FAILED = 0.5
GATE_DONE = 0.5
HOLDING = 0.5


def _number(raw: Any, default: float, lo: float, hi: float) -> float:
    if isinstance(raw, bool) or not isinstance(raw, (int, float)) or not math.isfinite(float(raw)) or not lo <= float(raw) <= hi:
        return float(default)
    return float(raw)


def _count(raw: Any, default: int | None, lo: int, hi: int) -> int | None:
    if raw is None:
        return default
    if isinstance(raw, bool) or not isinstance(raw, (int, float)) or not math.isfinite(float(raw)) or not lo <= float(raw) <= hi:
        return default
    return int(raw)


def cfg(settings: Mapping[str, Any] | None) -> dict[str, Any]:
    """The `allocation` block over DEFAULTS, every value checked: a misread one is its default (never an error)."""
    raw = (settings or {}).get("allocation")
    raw = raw if isinstance(raw, Mapping) else {}
    births_raw = raw.get("births") if isinstance(raw.get("births"), Mapping) else {}
    d, b = DEFAULTS, DEFAULTS["births"]
    out = {
        "mode": raw.get("mode") if raw.get("mode") in MODES else d["mode"],
        "floor_share": _number(raw.get("floor_share"), d["floor_share"], 0.0, 1.0),
        "explore_share": _number(raw.get("explore_share"), d["explore_share"], 0.0, 1.0),
        "family_cap": _number(raw.get("family_cap"), d["family_cap"], 0.01, 1.0),
        "class_cap": _number(raw.get("class_cap"), d["class_cap"], 0.01, 1.0),
        "cap_boost": _number(raw.get("cap_boost"), d["cap_boost"], 1.0, 100.0),
        "depth_trials": _number(raw.get("depth_trials"), d["depth_trials"], 1.0, 1e6),
        "hold_streak": _count(raw.get("hold_streak"), d["hold_streak"], 1, 10 ** 6),
        "lookback_hours": _number(raw.get("lookback_hours"), d["lookback_hours"], 1.0, 24 * 90),
        "real_structures": (list(raw["real_structures"]) if isinstance(raw.get("real_structures"), list)
                            and all(isinstance(x, str) for x in raw["real_structures"]) else list(d["real_structures"])),
        "shadow_value": _number(raw.get("shadow_value"), d["shadow_value"], 0.0, 1.0),
        "useful_value": _number(raw.get("useful_value"), d["useful_value"], 0.0, 100.0),
        "scheduler": raw.get("scheduler") if raw.get("scheduler") in SCHEDULERS else d["scheduler"],
        "max_wait_seconds": _number(raw.get("max_wait_seconds"), d["max_wait_seconds"], 0.0, 86400.0 * 7),
        "max_concurrency": _count(raw.get("max_concurrency"), None, 1, 512),
        "min_concurrency": _count(raw.get("min_concurrency"), d["min_concurrency"], 1, 512),
        "plan_usd_per_hour": (None if raw.get("plan_usd_per_hour") is None else
                              _number(raw.get("plan_usd_per_hour"), -1.0, 0.0, 1e6)),
        "expand_below": _number(raw.get("expand_below"), d["expand_below"], 0.0, 10.0),
        "births": {
            "max_share": _number(births_raw.get("max_share"), b["max_share"], 0.05, 1.0),
            "window_hours": _number(births_raw.get("window_hours"), b["window_hours"], 1.0, 24 * 30),
            "min_window": _count(births_raw.get("min_window"), b["min_window"], 0, 10 ** 6),
            "per_pass_min": _count(births_raw.get("per_pass_min"), b["per_pass_min"], 0, 1000),
            "min_alive": _count(births_raw.get("min_alive"), None, 0, 10 ** 6),
        },
    }
    if out["plan_usd_per_hour"] is not None and out["plan_usd_per_hour"] < 0:
        out["plan_usd_per_hour"] = None  # a misread plan is no plan (the pace's limit)
    if out["floor_share"] + out["explore_share"] > 1.0:
        out["floor_share"], out["explore_share"] = d["floor_share"], d["explore_share"]
    return out


# ------------------------------------------------------------------------------------------------------ mechanism classes
def mechanism_class(structure: Any, roots: Sequence[str]) -> str:
    """The strategist's own `mechanism_class` (structure by root group): imported lazily, since the strategist imports the
    architect, which imports this module."""
    from .strategist import mechanism_class as of

    return of(structure, roots)


# ------------------------------------------------------------------------------------------------------ the posterior
def _phi_upper(z: float) -> float:
    """P(Z >= z) for a standard normal."""
    return 0.5 * math.erfc(z / math.sqrt(2.0))


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


class Posterior:
    """The empirical-Bayes model of validation t (THE VALUE in the module docstring), fitted from `looks`: {family: (class,
    t)}, each family's latest validation in the lookback."""

    def __init__(self, looks: Mapping[str, tuple[str, float]]):
        self.looks = {str(f): (str(c), clip_t(t)) for f, (c, t) in looks.items() if clip_t(t) is not None}
        ts = [t for _, t in self.looks.values()]
        self.n = len(ts)
        by_class: dict[str, list[float]] = {}
        for c, t in self.looks.values():
            by_class.setdefault(c, []).append(t)
        self.by_class = {c: (len(v), sum(v)) for c, v in by_class.items()}
        self.mean, self.between, self.within, self.weight = PRIOR_MEAN, PRIOR_BETWEEN, PRIOR_WITHIN, 0.0
        if self.n >= MIN_OBS:
            mean = sum(ts) / self.n
            var = sum((t - mean) ** 2 for t in ts) / (self.n - 1)
            # Between-class variance: the spread of the class means beyond what their own sampling explains (one-way
            # method of moments), the rest of the excess over the unit noise is within-class.
            groups = [(len(v), sum(v) / len(v)) for v in by_class.values()]
            k = len(groups)
            if k >= 2:
                weighted = sum(n * (m - mean) ** 2 for n, m in groups) / (k - 1)
                within_pooled = (sum((t - sum(v) / len(v)) ** 2 for v in by_class.values() for t in v)
                                 / max(1, self.n - k))
                n0 = (self.n - sum(n * n for n, _ in groups) / self.n) / (k - 1)
                between = (weighted - within_pooled) / max(n0, 1.0)
            else:
                within_pooled, between = var, PRIOR_BETWEEN
            # Each estimate is bounded, then blended with the Sept 30 fit, the looks weighing n / (n + PRIOR_LOOKS).
            w = self.n / (self.n + PRIOR_LOOKS)
            self.weight = w
            self.mean = _clamp(w * _clamp(mean, *MEAN_BOUNDS) + (1 - w) * PRIOR_MEAN, *MEAN_BOUNDS)
            self.between = _clamp(w * _clamp(between, *VAR_BOUNDS) + (1 - w) * PRIOR_BETWEEN, *VAR_BOUNDS)
            self.within = _clamp(w * _clamp(within_pooled - NOISE, *VAR_BOUNDS) + (1 - w) * PRIOR_WITHIN, *VAR_BOUNDS)

    def class_prior(self, cls: str, *, leave_out: str | None = None) -> tuple[float, float]:
        """(mean, variance) of a new family's true t in class `cls`: the class mean's posterior (its looks, less the family
        `leave_out`'s own) plus the within-class spread."""
        n, total = self.by_class.get(cls, (0, 0.0))
        own = self.looks.get(leave_out) if leave_out is not None else None
        if own is not None and own[0] == cls:
            n, total = n - 1, total - own[1]
        precision = 1.0 / self.between + n / (self.within + NOISE)
        mean = (self.mean / self.between + total / (self.within + NOISE)) / precision
        return mean, 1.0 / precision + self.within

    def family(self, cls: str, own_t: float | None, *, fid: str | None = None) -> tuple[float, float]:
        """(mean, variance) of a family's true t: its class prior, updated by its own latest look when it has one."""
        mean, var = self.class_prior(cls, leave_out=fid)
        own = clip_t(own_t)
        if own is None:
            return mean, var
        post = 1.0 / (1.0 / var + 1.0 / NOISE)
        return post * (mean / var + own / NOISE), post

    @staticmethod
    def pass_probability(mean: float, var: float, line: float = evidence.MIN_T) -> float:
        """P(the next look's t >= the line): the predictive adds the look's unit noise back."""
        return _phi_upper((line - mean) / math.sqrt(max(var, 1e-9) + NOISE))

    def summary(self) -> dict[str, Any]:
        return {"looks": self.n, "weight": round(self.weight, 4), "mean": round(self.mean, 4), "between": round(self.between, 4),
                "within": round(self.within, 4)}


# ------------------------------------------------------------------------------------------------------------ the rows
def row_of(fam: Mapping[str, Any], *, cls: str, looks_spent: bool, gate_done: bool = False,
           lineage_trials: int | None = None, blind: bool = False) -> dict[str, Any]:
    """What the allocation reads of a family row (`store.families`). `gate_done`: the gate is done with its validated
    version (`gate_spent`). `lineage_trials`: its lineage set's trials now (`store.lineage_trials`), when read. `blind`
    (THE LEARNING GAME: a game-arm family in mode "gate"): its Validation t is never read (`t` None)."""
    from .researcher import validation_drift_failed  # the tournament's own rule: a drift-failed validation earns nothing

    state = fam.get("state") or {}
    nums = state.get("validation_numbers") or {}
    t = nums.get("t") if isinstance(nums, Mapping) else None
    drift = bool(validation_drift_failed(fam))
    usable = int(fam.get("validations") or 0) > 0 and isinstance(t, (int, float)) and not isinstance(t, bool) \
        and math.isfinite(float(t)) and not drift
    # A validated version the gate is done with (its holdout look made, or refused at review) says nothing more of the
    # line: its t is no longer the next look's evidence (the holdout refuted it, or the reviewer found it unsound).
    gate_done = bool(gate_done) and usable
    streak = state.get("hold_streak")
    own = int(fam.get("trials") or 0)
    # DEPTH reads the idea's trials: its lineage set's now (`store.lineage_trials`: every member's, and every lineage it
    # was born on the slice of or was linked to since, the N the deflated Sharpe counts), and never fewer than its own and
    # those it inherited at birth (a fork's lineage, or the dead lineages it was born on the slice of): a reborn
    # mechanism is not a young one.
    idea = own + max(0, int(fam.get("inherited_trials") or 0))
    if isinstance(lineage_trials, int) and not isinstance(lineage_trials, bool):
        idea = max(idea, lineage_trials)
    return {"id": str(fam["id"]), "cls": cls, "structure": fam.get("structure"),
            "t": float(t) if usable and not gate_done and not blind else None, "drift_failed": drift, "gate_done": gate_done,
            "trials": idea, "own_trials": own, "looks_spent": bool(looks_spent),
            "hold_streak": int(streak) if isinstance(streak, int) and not isinstance(streak, bool) else 0,
            "gate": bool(state.get("gate_ready") or state.get("look_inflight") or (fam.get("band") or "gym") != "gym")}


def gate_spent(store: Any, fam: Mapping[str, Any]) -> bool:
    """The gate is done with the family's validated version (`Tournament.gate_spent`'s rule, R4): its holdout look was
    made (`store.looked`) or the gate refused it (`gated_sha`, the review's refusals and a failed look's mark alike), so
    it never goes back to `gate_ready`."""
    from .gate import run_sha  # a local import: the allocation only reads the gate's mark

    state = fam.get("state") or {}
    n = state.get("validation_version")
    if n is None or isinstance(n, bool):
        return False
    version = store.version(str(fam["id"]), n)
    if version is None or not version.get("sha"):
        return False
    sha = run_sha(version)
    return bool(state.get("gated_sha") == sha or store.looked(sha))


def value_of(row: Mapping[str, Any], post: Posterior, c: Mapping[str, Any]) -> dict[str, Any]:
    """A family's value and its parts (THE VALUE in the module docstring)."""
    if row.get("gate"):
        return {"value": 0.0, "p": None, "depth": None, "exhaustion": 0.0, "why": "gate"}
    mean, var = post.family(row["cls"], row.get("t"), fid=row["id"])
    p = post.pass_probability(mean, var)
    # A family whose t check would pass but that is not at the gate failed another check: as undecided as one on the line.
    q = min(p, 0.5)
    depth = 1.0 / (1.0 + max(0, int(row.get("trials") or 0)) / float(c["depth_trials"]))
    ex, why = 1.0, []
    if row.get("looks_spent"):
        ex, why = 0.0, ["looks spent"]
    else:
        if row.get("drift_failed"):
            ex *= DRIFT_FAILED
            why.append("drift-failed validation")
        elif row.get("gate_done"):  # (the gate refuses a drift-failed version too: one discount for one verdict)
            ex *= GATE_DONE
            why.append("gate done with its validated version")
        if c["hold_streak"] and int(row.get("hold_streak") or 0) >= int(c["hold_streak"]):
            ex *= HOLDING
            why.append("holding")
    execution = 1.0 if str(row.get("structure")) in c["real_structures"] else c["shadow_value"]
    return {"value": q * (1.0 - q) * depth * ex * execution, "p": p, "mean": mean, "var": var, "depth": depth, "exhaustion": ex,
            "execution": execution, "why": ", ".join(why) or None}


def fresh_value(post: Posterior) -> float:
    """The value of a fresh family (no trials, a structure real money can open) in a class with no look: the reference a
    useful experiment is measured against (THE CONCURRENCY)."""
    mean, var = post.class_prior("\x00unexplored")
    q = min(post.pass_probability(mean, var), 0.5)
    return q * (1.0 - q)


def _fill(shares: dict[str, float], targets: Sequence[str], amount: float, weights: Mapping[str, float],
          cap: Mapping[str, float], *, evenly: bool = False) -> float:
    """Give `amount` to `targets` in proportion to `weights`, none past its `cap`, never to a target worth nothing; with
    `evenly`, when every target is worth nothing, evenly. In place. What could not be placed."""
    targets = [f for f in targets if shares[f] < cap[f] - 1e-12]
    w = {f: max(0.0, float(weights.get(f, 0.0))) for f in targets}
    if any(v > 0 for v in w.values()):
        targets = [f for f in targets if w[f] > 0]
    elif evenly:
        w = {f: 1.0 for f in targets}
    else:
        return amount
    while amount > 1e-12 and targets:
        mass = sum(w[f] for f in targets)
        spill, keep = 0.0, []
        for f in targets:
            add, room = amount * w[f] / mass, cap[f] - shares[f]
            if add >= room - 1e-15:
                shares[f] = cap[f]
                spill += add - room
            else:
                shares[f] += add
                keep.append(f)
        amount, targets = spill, keep
    return amount


def _cap_pass(shares: dict[str, float], cls_of: Mapping[str, str], weights: Mapping[str, float], family_cap: float,
              class_cap: float, floor: float, relief: float, limit: Mapping[str, float]) -> tuple[set[str], float]:
    """One water-filling at `class_cap`, in place: cap each family at `family_cap` and each class at `class_cap`, never
    taking a family below `floor` (only what a family holds above the floor share moves), and give the excess to the
    families under both caps whose `weights` (values) are at least `relief`, in proportion to their values, none past its
    `limit`. (the classes capped, what could not be placed: the caps do not hold at this level when it is above zero)"""
    capped: set[str] = set()
    for _ in range(100):
        excess, full = 0.0, set()
        for fid, s in shares.items():
            if s > family_cap + 1e-12:
                excess += s - family_cap
                shares[fid] = family_cap
            if shares[fid] >= family_cap - 1e-12:
                full.add(fid)
        totals: dict[str, float] = {}
        for fid, s in shares.items():
            totals[cls_of[fid]] = totals.get(cls_of[fid], 0.0) + s
        for cls, total in totals.items():
            if total < class_cap - 1e-12:
                continue
            members = [f for f in shares if cls_of[f] == cls]
            above = sum(max(0.0, shares[f] - floor) for f in members)
            cut = min(total - class_cap, above) if total > class_cap + 1e-12 else 0.0
            if cut > 1e-12:
                scale = 1.0 - cut / above
                for f in members:
                    part = max(0.0, shares[f] - floor)
                    excess += part * (1.0 - scale)
                    shares[f] = floor + part * scale
                capped.add(cls)
            full.update(members)
        if excess <= 1e-12:
            return capped, 0.0
        left = _fill(shares, [f for f in shares if f not in full and float(weights.get(f, 0.0)) >= relief], excess, weights,
                     limit)
        if left > 1e-12:
            return capped, left
        # a class that took the excess may now be over its own cap: check again
    return capped, 0.0


def _water_fill(shares: dict[str, float], cls_of: Mapping[str, str], weights: Mapping[str, float], family_cap: float,
                class_cap: float, boost: float, floor: float, relief: float = 0.0) -> tuple[set[str], bool, float, float]:
    """THE CAPS, in place (THE SHARE in the module docstring): each family at most `family_cap` and each class at most
    `class_cap`, never below `floor`; the excess to the families under both caps worth at least `relief` (what the
    average unit of share buys: a cap moves attention to other classes' families only where it buys at least that), in
    proportion to their values, none past `boost` times its own share. What they cannot take even with no class cap is
    THE FAMILY CAP'S SPILL (the families worth the relief are the capped ones, or at their boost): it goes to every family
    under the family cap by value (never to one worth nothing while any is worth something), then evenly. When the class
    cap adds to what cannot be placed, it RELAXES to the lowest level at which it adds nothing (bisection), every class
    held to that same level. (the classes capped, whether the class cap relaxed, the class cap's level, the spill)"""
    original = dict(shares)
    limit = {f: max(s, min(family_cap, boost * s)) for f, s in original.items()}

    def attempt(level: float) -> tuple[dict[str, float], set[str], float]:
        trial = dict(original)
        capped, left = _cap_pass(trial, cls_of, weights, family_cap, level, floor, relief, limit)
        return trial, capped, left

    trial, capped, left = attempt(class_cap)
    level, relaxed = class_cap, False
    if left > 1e-9:
        # With no class cap (level 1) nothing is cut by class: what is left then is the family cap's alone, and the class
        # cap relaxes only for what it adds to that (verification of #448: the family cap's spill read as the class cap's).
        family_left = attempt(1.0)[2]
        if left > family_left + 1e-9:
            relaxed = True
            lo, hi = class_cap, 1.0
            for _ in range(40):
                mid = 0.5 * (lo + hi)
                if attempt(mid)[2] > family_left + 1e-9:
                    lo = mid
                else:
                    hi = mid
            level = hi
            trial, capped, left = attempt(level)
    spill = left if left > 1e-12 else 0.0
    if spill:
        left = _fill(trial, list(trial), left, weights, {f: family_cap for f in trial}, evenly=True)
        if left > 1e-12:  # the family cap cannot hold either (it is at least 2/n, so this never happens): evenly
            for f in trial:
                trial[f] += left / len(trial)
    shares.update(trial)
    return capped, relaxed, level, spill


#: THE SHARE's tie step (`_break_ties`): far below any share that matters, far above a float's resolution at one.
TIE_STEP = 1e-12


def _break_ties(shares: dict[str, float], values: Mapping[str, Mapping[str, Any]]) -> None:
    """Exact ties (the family cap, the floor) broken in place by value, then id: each later member of a tie gives up a few
    parts in 10^12 a place, so a "top N by weight" band (researcher.is_top) holds N families, never every tied one."""
    order = sorted(shares, key=lambda f: (-round(shares[f], 12), -float(values[f]["value"]), f))
    prev, k = None, 0
    for fid in order:
        key = round(shares[fid], 12)
        k = k + 1 if key == prev else 0
        prev = key
        shares[fid] -= k * TIE_STEP


def value_shares(rows: Sequence[Mapping[str, Any]], post: Posterior,
                 settings: Mapping[str, Any] | None = None) -> tuple[dict[str, float], dict[str, Any]]:
    """Each family's share (THE SHARE in the module docstring): ({id: share} summing to 1, a report). `rows` as `row_of`
    makes them. The report's `useful_ids` are the families THE CONCURRENCY counts as useful experiments (the tournament
    keeps them and leaves them out of its event)."""
    c = cfg(settings)
    rows = [r for r in rows if r.get("id")]
    if not rows:
        return {}, {"mode": "value", "families": 0, "useful_ids": []}
    n = len(rows)
    values = {r["id"]: value_of(r, post, c) for r in rows}
    cls_of = {r["id"]: str(r.get("cls") or "none") for r in rows}
    eligible = [r for r in rows if not r.get("gate")]
    floor, explore_share = c["floor_share"], c["explore_share"]
    if not eligible:
        floor, explore_share = 1.0, 0.0
    decide_share = 1.0 - floor - explore_share
    shares = {r["id"]: floor / n for r in rows}
    pools: dict[str, float] = {"floor": floor, "explore": 0.0, "decide": 0.0}

    def spread(members: Sequence[Mapping[str, Any]], total: float) -> float:
        """`total` over `members` in proportion to their values; what it placed (nothing when every value is zero)."""
        weights = {r["id"]: values[r["id"]]["value"] for r in members}
        mass = sum(weights.values())
        if total <= 0 or mass <= 0:
            return 0.0
        for fid, w in weights.items():
            shares[fid] += total * w / mass
        return total

    # THE EXPLORATION SHARE: breadth across mechanism classes. A class's slice is its families' value mass with
    # diminishing returns in its size (sum / sqrt(count)): every discount its families carry (execution, depth,
    # exhaustion, a hold) carries into its slice, and a class whose every member is worth nothing takes none of it.
    by_class: dict[str, list[Mapping[str, Any]]] = {}
    for r in eligible:
        by_class.setdefault(cls_of[r["id"]], []).append(r)
    class_weight = {cls: sum(values[r["id"]]["value"] for r in members) / math.sqrt(len(members))
                    for cls, members in by_class.items()}
    mass = sum(class_weight.values())
    for cls, members in sorted(by_class.items()):
        if mass > 0 and class_weight[cls] > 0:
            pools["explore"] += spread(members, explore_share * class_weight[cls] / mass)
    # THE DECISION SHARE: every family outside the gate by its value.
    pools["decide"] = spread(eligible, decide_share)
    # What no family's value could take (every value zero) is spread evenly: the floor's.
    leftover = 1.0 - sum(shares.values())
    if leftover > 1e-12:
        pools["floor"] += leftover
        for fid in shares:
            shares[fid] += leftover / n
    total = sum(shares.values())
    shares = {f: s / total for f, s in shares.items()} if total > 0 else {f: 1.0 / n for f in shares}
    base = pools["floor"] / n / total if total > 0 else 1.0 / n  # every family's floor share: the caps never cut into it
    classes = set(cls_of.values())
    family_cap = max(c["family_cap"], 2.0 / n)
    class_cap = max(c["class_cap"], 1.0 / max(1, len(classes)))
    # A cap's excess goes only to families worth at least what the average unit of share buys (attention follows value,
    # so that is the value-weighted mean value): moving it never dilutes the information it funds.
    mass = sum(values[r["id"]]["value"] for r in eligible)
    relief = sum(values[r["id"]]["value"] ** 2 for r in eligible) / mass if mass > 0 else 0.0
    capped, relaxed, level, spill = _water_fill(shares, cls_of, {f: v["value"] for f, v in values.items()}, family_cap,
                                                class_cap, c["cap_boost"], base, relief)
    total = sum(shares.values())
    shares = {f: s / total for f, s in shares.items()} if total > 0 else {f: 1.0 / n for f in shares}
    _break_ties(shares, values)
    by_cls: dict[str, float] = {}
    heads: dict[str, int] = {}
    for fid, s in shares.items():
        by_cls[cls_of[fid]] = by_cls.get(cls_of[fid], 0.0) + s
        heads[cls_of[fid]] = heads.get(cls_of[fid], 0) + 1
    largest = max(sorted(by_cls), key=lambda k: by_cls[k])
    top = sorted(shares, key=lambda f: (-shares[f], f))[:5]
    reference = fresh_value(post)
    useful_ids = sorted(r["id"] for r in eligible if values[r["id"]]["value"] >= c["useful_value"] * reference > 0)
    report = {"mode": "value", "families": n, "gate_families": n - len(eligible),
              "unvalidated_families": sum(1 for r in eligible if r.get("t") is None),
              "pools": {k: round(v, 4) for k, v in pools.items()}, "posterior": post.summary(),
              "family_cap": round(family_cap, 4), "class_cap": round(class_cap, 4), "capped_classes": sorted(capped),
              # The class cap in force: its level, or the largest class's share when the family cap's spill took it past.
              "class_cap_relaxed": relaxed, "class_cap_in_force": round(max(level, by_cls[largest]), 4),
              "family_cap_spill": round(spill, 4),
              "largest_class": {"class": largest, "share": round(by_cls[largest], 4), "head_share": round(heads[largest] / n, 4)},
              "classes": {k: round(v, 4) for k, v in sorted(by_cls.items(), key=lambda kv: -kv[1])[:12]},
              "exhausted": sorted(f for f, v in values.items() if v["exhaustion"] == 0.0 and v["why"] != "gate")[:20],
              "fresh_value": round(reference, 5), "useful": len(useful_ids), "useful_ids": useful_ids,
              "top": [{"family": f, "share": round(shares[f], 4), "p": None if values[f]["p"] is None else round(values[f]["p"], 4),
                       "depth": None if values[f]["depth"] is None else round(values[f]["depth"], 3)} for f in top]}
    return shares, report


# ------------------------------------------------------------------------------------------------- the store's side
def looks_from_store(store: Any, *, since: float, class_of: Callable[[str], str | None]) -> dict[str, tuple[str, float]]:
    """{family: (class, t)}: each family's latest validation (normal spread) since `since`, its `t_daily`, made on the
    evaluator the swarm runs now (its image and bundle, `evaluator.KEY`; every look while none is recorded): evidence
    from another fingerprint is never pooled with this one's, even for attention."""
    from .evaluator import KEY, matches
    from .store import iso, loads

    current = store.get(KEY)
    rows = store._all("SELECT family, at, summary FROM runs WHERE window='validation' AND stress=1.0 AND trials>0 AND at>=? "
                      "ORDER BY at, rowid", (iso(since),))
    out: dict[str, tuple[str, float]] = {}
    for row in rows:
        summary = loads(row["summary"], {}) or {}
        if current is not None and not matches(summary, current):
            continue
        t = summary.get("t_daily")
        cls = class_of(str(row["family"]))
        if cls is None or isinstance(t, bool) or not isinstance(t, (int, float)) or not math.isfinite(float(t)):
            continue
        out[str(row["family"])] = (cls, float(t))  # the latest wins
    return out


def classes_from_store(store: Any) -> dict[str, str]:
    """{family: mechanism class} for every family the store knows (one query, no state decoded)."""
    from .store import loads

    return {str(r["id"]): mechanism_class(r["structure"], loads(r["roots"], []) or [])
            for r in store._all("SELECT id, structure, roots FROM families")}


def allocate_from_store(store: Any, fams: Sequence[Mapping[str, Any]], settings: Mapping[str, Any], *,
                        now: float) -> tuple[dict[str, float], dict[str, Any]]:
    """The tournament's call: the living families' shares and the report, read from the store."""
    c = cfg(settings)
    classes = classes_from_store(store)
    for fam in fams:
        classes.setdefault(str(fam["id"]), mechanism_class(fam.get("structure"), fam.get("roots") or []))
    gated = game.cfg(settings)["mode"] == "gate"
    post = Posterior(looks_from_store(store, since=now - c["lookback_hours"] * 3600.0, class_of=classes.get))
    rows = []
    for fam in fams:
        fid = str(fam["id"])
        try:
            spent = store.lineage_looks(fid, include_inflight=True) >= evidence.LOOKS_PER_LINEAGE
        except Exception:  # noqa: BLE001 - an unreadable lineage is not a spent one
            spent = False
        try:  # THE LEARNING GAME: no trial of a child the game bore beside it (`game.shown_trials`; the store's count else)
            trials: int | None = int(game.shown_trials(store, fam))
        except Exception:  # noqa: BLE001 - its own and inherited trials still count
            trials = None
        state = fam.get("state") or {}
        done = False
        if int(fam.get("validations") or 0) > 0 and (fam.get("band") or "gym") == "gym" \
                and not (state.get("gate_ready") or state.get("look_inflight")):
            try:
                done = gate_spent(store, fam)
            except Exception:  # noqa: BLE001 - an unreadable version: its validation reads as it stands
                done = False
        try:  # THE LEARNING GAME: a game-arm family's Validation t never steers its compute
            blind = gated and game.arm(store, fam, settings) == "game"
        except Exception:  # noqa: BLE001 - its row as before
            blind = False
        rows.append(row_of(fam, cls=classes[fid], looks_spent=spent, gate_done=done, lineage_trials=trials, blind=blind))
    return value_shares(rows, post, settings)


# ---------------------------------------------------------------------------------------------------------- the turns
class StrideTurns:
    """THE TURNS (the module docstring): start-time fair queueing over the families' shares. Each family carries a finish
    tag; a ready family's start tag is its finish tag, or the virtual time (the start tag of the last family served) when
    that is later (a family that was holding, or new, banks no credit); the lowest start tag goes first (the larger share
    on a tie), and a turn moves the family's finish tag one stride, 1 / (its share x n), past its start. So families that
    are always ready are served in proportion to their shares. Not thread-safe by itself: the Scheduler calls it under its
    own lock."""

    #: A share below this fraction of the average is treated as this (a family's stride is at most 1 / MIN_REL).
    MIN_REL = 0.02

    def __init__(self) -> None:
        self.passes: dict[str, float] = {}  # finish tags
        self.now_pass = 0.0                 # the virtual time

    @staticmethod
    def stride(share: Any, n: int) -> float:
        rel = float(share) * n if isinstance(share, (int, float)) and not isinstance(share, bool) and math.isfinite(share) and share > 0 \
            else 1.0  # no share yet (a newborn before its first round): the average
        return 1.0 / max(StrideTurns.MIN_REL, rel)

    def key(self, fid: str, share: Any, n: int) -> float:
        """The family's start tag now."""
        return max(self.passes.get(fid, float("-inf")), self.now_pass)

    @staticmethod
    def starving(fid: str, *, now: float, last: Mapping[str, float], max_wait: float) -> bool:
        """The family has had no turn for `max_wait` seconds (0: the rule is off)."""
        return max_wait > 0 and fid in last and now - float(last[fid]) >= max_wait

    def order(self, ready: Sequence[Mapping[str, Any]], n: int, *, now: float, last: Mapping[str, float],
              max_wait: float) -> list[Mapping[str, Any]]:
        """The ready families in turn order: with `max_wait`, any that has waited that long since its last turn first (the
        longest wait first); then by start tag, the larger share first on a tie."""
        def rank(f: Mapping[str, Any]) -> tuple:
            if self.starving(f["id"], now=now, last=last, max_wait=max_wait):
                return (0, -(now - float(last[f["id"]])), 0.0, f["id"])
            return (1, self.key(f["id"], f.get("weight"), n), self.stride(f.get("weight"), n), f["id"])
        return sorted(ready, key=rank)

    def took(self, fid: str, share: Any, n: int, *, out_of_order: bool = False) -> None:
        """A turn: the family's finish tag moves one stride past its start. A turn served `out_of_order` (the starvation
        rule) never moves the virtual time, so the other families keep their places."""
        start = self.key(fid, share, n)
        if not out_of_order:
            self.now_pass = max(self.now_pass, start)
        self.passes[fid] = start + self.stride(share, n)

    def forget(self, alive: Iterable[str]) -> None:
        keep = set(alive)
        for fid in [f for f in self.passes if f not in keep]:
            del self.passes[fid]


def legacy_order(ready: Sequence[Mapping[str, Any]], n: int, *, last: Mapping[str, float]) -> list[Mapping[str, Any]]:
    """The turn order before Release B: a share at the average is worth nothing, twice it is worth a minute of waiting."""
    return sorted(ready, key=lambda f: (last.get(f["id"], 0) - 60.0 * (float(f.get("weight") or (1.0 / n)) * n - 1.0), f["id"]))


def queued_useful(ordered: Sequence[Mapping[str, Any]], useful_ids: Iterable[str]) -> int:
    """The distinct useful experiments left waiting (THE CONCURRENCY): the ready families after the one served that the
    tournament's last allocation named useful (`value_shares`' `useful_ids`; a family born since, or any family under the
    bandit, is not counted: nothing expands on a family nobody has valued)."""
    ids = useful_ids if isinstance(useful_ids, (set, frozenset)) else set(useful_ids)
    return sum(1 for f in ordered if f.get("id") in ids)


# ---------------------------------------------------------------------------------------------------- the concurrency
def concurrency_bounds(settings: Mapping[str, Any] | None) -> tuple[int, int, int]:
    """(the plan's level, the ceiling, the floor): `researcher.concurrency` (48), `allocation.max_concurrency` (never below
    the plan's level), `allocation.min_concurrency` (never above it)."""
    raw = ((settings or {}).get("researcher") or {}).get("concurrency", 48)
    base = _count(raw, 48, 0, 512)
    c = cfg(settings)
    ceiling = max(base, c["max_concurrency"] or base)
    return base, ceiling, min(base, c["min_concurrency"])


def effective_concurrency(settings: Mapping[str, Any] | None, *, queued_useful: int, running: int,
                          spent_usd_hour: float) -> dict[str, Any]:
    """THE CONCURRENCY (the module docstring): {workers, base, ceiling, floor, plan, why}. `spent_usd_hour`: the research
    spend (`RESEARCH_SPEND`) in the last hour."""
    base, ceiling, floor = concurrency_bounds(settings)
    c = cfg(settings)
    plan = c["plan_usd_per_hour"]
    out = {"base": base, "ceiling": ceiling, "floor": floor, "plan_usd_per_hour": plan, "spend_kinds": list(RESEARCH_SPEND),
           "queued_useful": int(queued_useful), "spent_usd_hour": round(float(spent_usd_hour), 4), "workers": base,
           "why": "the plan's level"}
    if plan is None or plan <= 0:
        out["why"] = "no allocation.plan_usd_per_hour: the plan's level"
    elif spent_usd_hour > plan:
        out["workers"] = max(floor, min(base, int(base * plan / spent_usd_hour)))
        out["why"] = "over the spend plan: contracted"
    elif ceiling > base and queued_useful > 0 and spent_usd_hour < c["expand_below"] * plan:
        out["workers"] = min(ceiling, max(base, int(running) + int(queued_useful)))
        out["why"] = "useful experiments queued: expanded" if out["workers"] > base else out["why"]
    return out


# ---------------------------------------------------------------------------------------------------- the birth quota
STRUCTURE_BUCKETS: dict[str, tuple[str, ...]] = {
    "single": ("long_single", "long_call", "long_put"),
    "butterfly": ("long_butterfly", "iron_butterfly"),
    "vertical": ("debit_vertical", "credit_vertical"),
    "straddle": ("long_straddle", "long_strangle"),
    "condor": ("iron_condor",),
    "calendar": ("calendar", "diagonal"),
}
_BUCKET_OF = {s: b for b, members in STRUCTURE_BUCKETS.items() for s in members}


def bucket_of(structure: Any) -> str:
    """A structure type's structure family (`STRUCTURE_BUCKETS`); an unknown type is its own."""
    return _BUCKET_OF.get(str(structure), str(structure))


class BirthQuota:
    """THE BIRTH QUOTA (the module docstring) for one architect pass: the window's births by structure family, read once,
    and this pass's so far."""

    def __init__(self, store: Any, settings: Mapping[str, Any] | None, *, now: float | None = None, want: int = 0,
                 alive: int | None = None):
        c = cfg(settings)["births"]
        self.max_share, self.min_window, self.per_pass_min = c["max_share"], int(c["min_window"]), int(c["per_pass_min"])
        self.window_hours = c["window_hours"]
        self.want = max(0, int(want))
        start = _count(((settings or {}).get("population") or {}).get("start", 48), 48, 0, 10 ** 6) or 0
        self.min_alive = c["min_alive"] if c["min_alive"] is not None else (3 * start) // 4
        # THE POPULATION GUARD: below `min_alive` living families the whole quota rests (the window's rule and the pass's
        # cap), so a swarm whose proposals stay one structure family thins to the guard but never below it.
        self.on = alive is None or int(alive) >= self.min_alive
        now = time.time() if now is None else float(now)
        self.window: dict[str, int] = {}
        from .store import iso, loads

        for row in store._all("SELECT payload FROM events WHERE kind='swarm.born' AND at>=?", (iso(now - self.window_hours * 3600.0),)):
            b = bucket_of((loads(row["payload"], {}) or {}).get("structure"))
            self.window[b] = self.window.get(b, 0) + 1
        self.passed: dict[str, int] = {}
        self.refused: dict[str, int] = {}

    def per_pass(self) -> int:
        return max(self.per_pass_min, int(self.max_share * self.want))

    def full(self, bucket: str) -> bool:
        """The structure family's window share is at its cap (only once the window holds `min_window` births, and only
        while the population guard lets the window's rule hold)."""
        if not self.on:
            return False
        total = sum(self.window.values()) + sum(self.passed.values())
        mine = self.window.get(bucket, 0) + self.passed.get(bucket, 0)
        return total >= self.min_window and mine + 1 > self.max_share * (total + 1)

    def admits(self, structure: Any) -> bool:
        """May one more family of `structure` be born in this pass? A refusal is counted (`refused`)."""
        b = bucket_of(structure)
        mine = self.passed.get(b, 0)
        ok = not self.on or mine < self.per_pass_min or (mine < self.per_pass() and not self.full(b))
        if not ok:
            self.refused[b] = self.refused.get(b, 0) + 1
        return ok

    def born(self, structure: Any) -> None:
        b = bucket_of(structure)
        self.passed[b] = self.passed.get(b, 0) + 1

    def text(self, allowed: Iterable[str] | None = None) -> str:
        """The architect's request's lines: the window's counts, which families are full, the pass's cap. `allowed`
        (THE STRUCTURES, architect.py `architect.structures`; None: every type, the lines as before): only the structure
        families with an allowed member, naming only their allowed members, so the quota never invites a type no birth
        may be. The counts, the shares and FULL stay the window's, every type's births included."""
        allow = None if allowed is None else set(allowed)
        buckets = {b: (m if allow is None else tuple(s for s in m if s in allow)) for b, m in STRUCTURE_BUCKETS.items()}
        buckets = {b: m for b, m in buckets.items() if m}
        note = ("" if allow is None else " Only the families of the allowed types are shown; a family's count is its births "
                "of every type in the window.")
        total = sum(self.window.values())
        lines = []
        for bucket, members in buckets.items():
            n = self.window.get(bucket, 0)
            state = (f"FULL: at most {self.per_pass_min} this pass" if self.full(bucket) else f"open: up to {self.per_pass()} this pass")
            lines.append(f"- {bucket} ({', '.join(members)}): {n} of {total} ({(100.0 * n / total) if total else 0.0:.0f}%), {state}")
        if not self.on:
            return (f"BIRTH QUOTAS (structure families; the last {self.window_hours:g} h of births): they rest in this pass "
                    f"(fewer than {self.min_alive} families live), so every well-formed proposal may be born; still, propose "
                    f"across the structure families.{note}\n" + "\n".join(f"- {b} ({', '.join(m)}): {self.window.get(b, 0)} of {total}"
                                                                           for b, m in buckets.items()))
        return (f"BIRTH QUOTAS (structure families; the last {self.window_hours:g} h of births): one structure family may hold at "
                f"most {self.max_share:.0%} of them once there are {self.min_window}, and at most {self.per_pass()} of one "
                f"in this pass. A proposal past its family's quota is not born; propose across the open families.{note}\n"
                + "\n".join(lines))


__all__ = ["DEFAULTS", "RESEARCH_SPEND", "SHARE_LEGEND", "cfg", "Posterior", "row_of", "value_of", "fresh_value", "value_shares",
           "allocate_from_store", "gate_spent", "looks_from_store", "classes_from_store", "StrideTurns", "legacy_order", "queued_useful",
           "effective_concurrency", "concurrency_bounds", "STRUCTURE_BUCKETS", "bucket_of", "BirthQuota", "DirectionQuota",
           "mechanism_class"]
