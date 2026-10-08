"""THE LEARNING GAME v1 (Oct 8, 2026): years no agent sees decide which programs reproduce and which reach Validation.

WHY. Every researcher, the architect and the strategist had tuned on every Train year they were shown, so a version that
looked better on Train was mostly a version fitted harder to those days: a gain of under 0.5 t on Train carried to a
left-out year at chance (51.7-53.9% sign agreement, the learning map's 7a). The game keeps two years out of every agent's
sight and lets them, not Train, decide selection. It raises the odds of finding an edge that exists and cuts false
Probes; it cannot make an edge that one-lot spreads remove. The design, its measurement plan and its numbers are the
build spec of Oct 8, 2026 (its sections 3 to 7).

THE CALENDAR. SEEN is 2022-01-03 to 2024-12-31: the swarm's Train span (`gym.train_from` "2022-01-03"), every view as
today. HIDDEN (`HIDDEN`) is the two years before it: from T0 no agent sees a figure, a tier, a year label or a result of
them, ever. Validation (2025), the holdout and the forward record are unchanged. A hidden run is one Train job over
`HIDDEN` at 1.5x the half-spread, `purpose="private"` (the pool runs it on the 2020 image, `pool.py` THE GAME'S PRIVATE
JOBS); its result never enters `runs`, trials, a notebook, an event or any view: it is scored here and kept in the game's
own tables.

WHO PLAYS. T0 is the first start with `game.enabled` (`t0`, the store's kv `game_t0`, written once). `arm` is None
(LEGACY: today's rules, no looks) for a family born before T0 or with a root outside the core five (`CORE`: only they have
2020-21 data), else "game" or "control" by the canary's pure hash split of its LINEAGE (`canary.in_arm`), so a child stays
in its parent's arm. Half play the game; half keep today's rules on the same seen years and are measured the same way
(their looks are records only): a concurrent comparison, never a before/after one.

THE FOLDS. `fold(lineage)` names each lineage's SELECT year (the one selection reads) and its CONFIRM year (read once, by
the gate on the way to Validation, and by the operator's metrics). A child keeps its parent's lineage
(`SwarmStore.add_family(parent=...)`), so it keeps both years: inherited luck on the SELECT year never lands on a
relative's CONFIRM year (the critique's clade fix). A crossover child joins its SIGNAL parent's lineage only, and its
donor comes from the same fold group.

THE FITNESS (`fitness`). For a hidden run and one of its years, at 1.5x: t_net is the all-days t of the year's daily dollar
P&L (the Gym's own `_t_of` over the drift row's pnl, sum of squares and days), t_alpha the drift-adjusted alpha t (the
same exposure held on average days is the placebo), and F = min(t_net, t_alpha): a program must make money after
stressed costs AND beat its own exposure's drift. A year is eligible with at least 40 trades on 20 traded days (the Train
score's constants), every root of the program with data in it, and both t values; an ineligible year scores minus
infinity (stored as null).

THE LADDER (`maybe_look`, both arms; on the pool's dispatcher thread, after a version's 1.5x seen run landed with a
profit). Version n is looked at when its family plays, n is its best by Train score, its seen 1.5x run made money, its
Train score beats the family's last looked score by `eta` (0.5; the first such version is look 1), the family has used
fewer than `looks` (4) and has none in flight, and its program (the version's sha) was never looked at in its lineage, so
a child's unchanged copy of its parent's program never is. Control also looks (records only) at every version the
tournament validates that was not looked at already (`shadow_validated`). A job that fails is queued again after
`look_retry_hours` (2), at most `look_attempts` (3) in all, then the look is recorded failed and does not count against
`looks` (`requeue_stale`).

SELECT, CONFIRM, VALIDATION (game arm, mode "gate"). `landed` scores both years and records the SELECT tier: PASS at F of
at least `c_select` (1.28, one-sided 10% a year), ALIVE from 0, FAIL below 0 or ineligible. On a PASS it reads the
CONFIRM year once, while the family has read fewer than `confirms_family` (2) and its lineage fewer than
`confirms_lineage` (3, as the holdout's looks): CONFIRMED at F of at least `c_confirm` (1.28). The family's candidate for
Validation is its latest CONFIRMED version (`candidate`), none without one, and it has `val_tries` (2) Validation tries
(`validations_left`). The Validation line, the gate, the holdout and Probe sizing are unchanged.

THE TWO ACCESSORS. Every decision here reads a look's result through `select_view` or `confirm_view`, and `confirm_view`
RAISES unless the look has a `game_confirms` row: the CONFIRM year is read by the one-shot gate (`landed`) and by the
operator's metrics (`metrics`, through `_operator_years`), never by reproduction, compute or retirement, the architect or
the strategist. A look row read without its confirm row (`_rows(confirms=False)`, what `parents` and `reproduce` read)
cannot open it at all.

REPRODUCTION (`parents`, `reproduce`; mode "gate"). A game-arm look is a parent when its SELECT year is eligible with F
above zero, in the top `parent_quantile` (decile) of the game-arm looks landed in the last `parent_window_hours` (72) once
there are `parent_min_looks` (30) of them (before that, F of at least `parent_bootstrap_f`, 1.0: at 1.0x only about 4% of
years clear 1.28, so ranking keeps the pressure on), its family has fewer than `children_per_parent` (3) living children
and has not bred in `child_cooldown_hours` (6). At most `children_per_round` (4) a round and `children_per_day` (24) a
day, inside `population.ceiling`. A child is `add_family(origin="game", parent=...)` with a neutral id (`g-<8 hex>`),
version 1 the parent's looked version (code and params, as `Tournament.fork` seeds a fork), the parent's card copied
(`cards.put`), and one change: MUTATE (the rest) gives it a structural directive, `DIRECTIVES[(hash(parent) + k) % 6]` for
its k-th sibling (structural steps carry to unseen years, parameter tweaks do not: 73% sign agreement for the largest fifth
of steps against about 52%); CROSSOVER (`crossover_share`, 20%, when a donor exists) shows it another parent-qualified
program of the same fold group and another lineage, at most `donor_max_chars` (6,000), to adopt its execution while it
keeps its own signal.

RETIREMENT (`retire_reason`, before today's rules; Gym band only, `retire_gym`'s floor applies): the family spent its
`looks` without a SELECT PASS; or two of its CONFIRM reads failed; or it used its `val_tries` Validation tries and all
failed. Today's rules still apply after these.

WHAT AGENTS SEE (`status_text`, `brief_text`, `visible_families`, `visible_graveyard`). A game-arm researcher in "gate"
sees one status line on the exam (how many looks it used, never a figure, a tier, a year or a result) and, a child, its
change. The architect and the strategist never see game-arm families (`visible_families`); every reader's graveyard drops
game-arm rows (their reasons reveal SELECT outcomes) and the rows of families born before T0 and retired since the
2020-21 switch (`SWITCH_AT`: they learned on the hidden years). With the game off (or before T0) both are exactly the
store's own reads.

MODES. "shadow": looks are recorded for both arms and the game-arm rules are off (no CONFIRM read, candidate, Validation
cap, reproduction or retirement). "gate": all of the above. `enabled` false: nothing here acts and every family is legacy.

THE TABLES (`GAME_SQL`), created on first use on the store's own connection (as `cards.CARDS_SQL`), append-only by
trigger, so `store.py` is unchanged: `game_looks` (one row a look), `game_results` (its attempts and its one terminal
row: "ok" with both years' figures and the SELECT tier, "failed" or "cancelled"), `game_confirms` (the one CONFIRM read
of a look) and `game_children`. No module but this one reads them.

Standard library only.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import random
import re
import threading
import time
from typing import Any, Callable, Mapping, Sequence

from . import canary, cards, evidence
from . import settings as settings_mod
from .pool import GymJob

#: The 2020-21 switch's deploy (Sept 28, 2026): a family born before T0 and retired since learned on the hidden years.
SWITCH_AT = "2026-09-28T16:10:00Z"
#: The hidden years' first and last day, and the seen span's first (`gym.train_from`).
HIDDEN = ("2020-01-02", "2021-12-31")
HIDDEN_YEARS = (2020, 2021)
SEEN_FROM = "2022-01-03"
#: The core five: only they have 2020-21 data (`docs/design.md`: "the core five from 2020").
CORE = ("SPY", "QQQ", "IWM", "XSP", "SPXW")
T0_KEY = "game_t0"
#: The canary key of the arm split (`canary.in_arm(salt, ARM_KEY, lineage, arm_fraction)`) and the fold's salt.
ARM_KEY = "game-v1"
FOLD_SALT = "ltcm-game-v1"
MODES = ("shadow", "gate")
ARMS = ("game", "control")
#: A ladder look (the version beat its family's last looked score) or control's record of a validated version.
ROLES = ("ladder", "validated")
#: A look's terminal statuses; any other look is in flight (queued, or waiting for its retry).
TERMINAL = ("ok", "failed", "cancelled")
TIERS = ("PASS", "ALIVE", "FAIL")
OPS = ("mutate", "crossover")
#: The pool purpose of a hidden run (`pool.GymPool.submit`: never stamped with the span, and it must end before it).
PURPOSE = "private"
#: A hidden run's place in the queue: with Validation's (it is a step on the way there), above a researcher's run.
PRIVATE_PRIORITY = 1.0
ORIGIN = "game"
#: The game's one event, a look queued ({family, version, look}), never a figure or a result: kept in the swarm's own table
#: (`hook.SKIPPED_KINDS`), never mirrored to the House's ledger or the site.
EVENT = "swarm.game"
#: The fitness's eligibility: the Train score's own (`evidence.TRAIN_YEAR_MIN_TRADES`, `TRAIN_YEAR_MIN_DAYS`).
MIN_TRADES = evidence.TRAIN_YEAR_MIN_TRADES
MIN_DAYS = evidence.TRAIN_YEAR_MIN_DAYS
#: The family-cluster bootstrap of the operator's metrics (section 7 of the spec): draws and the two-sided level.
BOOT_DRAWS = 2000
BOOT_LEVEL = 0.90

DEFAULTS: dict[str, Any] = {
    "enabled": False, "mode": "shadow", "arm_fraction": 0.5, "salt": FOLD_SALT, "roots": list(CORE),
    "seen_from": SEEN_FROM, "hidden": list(HIDDEN), "stress": 1.5,
    "eta": 0.5, "looks": 4, "c_select": 1.28, "c_confirm": 1.28,
    "confirms_family": 2, "confirms_lineage": 3, "val_tries": 2,
    "parent_quantile": 0.10, "parent_window_hours": 72, "parent_min_looks": 30, "parent_bootstrap_f": 1.0,
    "children_per_parent": 3, "children_per_round": 4, "children_per_day": 24, "child_cooldown_hours": 6,
    "crossover_share": 0.2, "donor_max_chars": 6000,
    "look_retry_hours": 2, "look_attempts": 3,
}

#: A MUTATE child's change, by `(hash(parent) + k) % 6` (the spec's six structural directives).
DIRECTIVES = (
    "Replace the signal's market input with another one.",
    "Replace the exit rule (target, stop or time stop): change the rule, not its numbers.",
    "Change how entries and exits are priced (mid vs natural, patience, time in force).",
    "Move the holding horizon to another expiry bucket.",
    "Add one regime filter that switches the signal off in a market condition you can name.",
    "Flip the signal's logic (fade instead of follow, or the reverse).",
)
CROSSOVER = "Keep your signal; adopt the donor's entry pricing, exits and position management."
CHILD_NOTE = ("Your version 1 is a program that passed this game's private exam. Make the change below before anything "
              "else, then improve on your Train years as usual.")
STATUS = ("PRIVATE EXAM: every version that beats your last examined Train score by {eta:g} and makes money at {stress:g}x "
          "is scored on market years you never see, at {stress:g}x and net of its market exposure's drift. Only versions "
          "that pass go to Validation, and passing families have children. You get no figures from it; tune nothing to "
          "it. Looks used: {used} of {looks}; after {looks} without a pass the family retires. Parameter tweaks almost "
          "never survive unseen years; structural changes sometimes do.")
_WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six"}
_TIMES = {1: "once", 2: "twice", 3: "three times"}

#: The game's tables, one statement each: `ensure` runs them through the store's `_exec`, never `executescript` (which
#: would commit a caller's open transaction first).
GAME_SQL = (
    "CREATE TABLE IF NOT EXISTS game_looks (seq INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, family TEXT NOT NULL, "
    "lineage TEXT NOT NULL, arm TEXT NOT NULL, role TEXT NOT NULL, version INTEGER NOT NULL, sha TEXT NOT NULL, "
    "generation INTEGER NOT NULL, parent TEXT, select_year INTEGER NOT NULL, seen_score REAL, seen_run TEXT, seen_f REAL, "
    "private_job TEXT NOT NULL)",
    "CREATE INDEX IF NOT EXISTS game_looks_family ON game_looks(family, seq)",
    "CREATE INDEX IF NOT EXISTS game_looks_lineage ON game_looks(lineage, sha)",
    "CREATE TRIGGER IF NOT EXISTS game_looks_no_update BEFORE UPDATE ON game_looks "
    "BEGIN SELECT RAISE(ABORT, 'game looks are append-only'); END",
    "CREATE TRIGGER IF NOT EXISTS game_looks_no_delete BEFORE DELETE ON game_looks "
    "BEGIN SELECT RAISE(ABORT, 'game looks are append-only'); END",
    "CREATE TABLE IF NOT EXISTS game_results (seq INTEGER PRIMARY KEY AUTOINCREMENT, look_seq INTEGER NOT NULL, "
    "at TEXT NOT NULL, status TEXT NOT NULL, years_json TEXT NOT NULL, tier TEXT)",
    "CREATE INDEX IF NOT EXISTS game_results_look ON game_results(look_seq, seq)",
    "CREATE TRIGGER IF NOT EXISTS game_results_no_update BEFORE UPDATE ON game_results "
    "BEGIN SELECT RAISE(ABORT, 'game results are append-only'); END",
    "CREATE TRIGGER IF NOT EXISTS game_results_no_delete BEFORE DELETE ON game_results "
    "BEGIN SELECT RAISE(ABORT, 'game results are append-only'); END",
    "CREATE TABLE IF NOT EXISTS game_confirms (seq INTEGER PRIMARY KEY AUTOINCREMENT, look_seq INTEGER NOT NULL UNIQUE, "
    "at TEXT NOT NULL, f_confirm REAL, confirmed INTEGER NOT NULL)",
    "CREATE TRIGGER IF NOT EXISTS game_confirms_no_update BEFORE UPDATE ON game_confirms "
    "BEGIN SELECT RAISE(ABORT, 'game confirms are append-only'); END",
    "CREATE TRIGGER IF NOT EXISTS game_confirms_no_delete BEFORE DELETE ON game_confirms "
    "BEGIN SELECT RAISE(ABORT, 'game confirms are append-only'); END",
    "CREATE TABLE IF NOT EXISTS game_children (seq INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, "
    "child TEXT NOT NULL UNIQUE, parent TEXT NOT NULL, op TEXT NOT NULL, directive INTEGER, donor TEXT, parent_look INTEGER)",
    "CREATE INDEX IF NOT EXISTS game_children_parent ON game_children(parent, seq)",
    "CREATE TRIGGER IF NOT EXISTS game_children_no_update BEFORE UPDATE ON game_children "
    "BEGIN SELECT RAISE(ABORT, 'game children are append-only'); END",
    "CREATE TRIGGER IF NOT EXISTS game_children_no_delete BEFORE DELETE ON game_children "
    "BEGIN SELECT RAISE(ABORT, 'game children are append-only'); END",
)

#: The hidden runs this process has in the pool, by (store, look): `requeue_stale` never queues one of them again.
_inflight: dict[tuple[str, int], GymJob] = {}
_inflight_lock = threading.Lock()


class Sealed(LookupError):
    """A look's CONFIRM year was asked for without its one-shot read (`confirm_view`)."""


# ----------------------------------------------------------------------------------------------------------- settings
def cfg(settings: Mapping[str, Any] | None) -> dict[str, Any]:
    """`game` in the swarm's settings, each value inside its bounds (a malformed one is its default; a number past a bound
    is the bound). A malformed `enabled` is off; a malformed `mode` is "shadow" (the game-arm rules off)."""
    raw = (settings or {}).get("game")
    raw = raw if isinstance(raw, Mapping) else {}

    def number(key: str, low: float, high: float) -> float:
        value = raw.get(key, DEFAULTS[key])
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            value = DEFAULTS[key]
        return float(min(high, max(low, value)))

    def whole(key: str, low: int, high: int) -> int:
        return int(number(key, low, high))

    fraction = raw.get("arm_fraction", DEFAULTS["arm_fraction"])
    if isinstance(fraction, bool) or not isinstance(fraction, (int, float)) or not math.isfinite(fraction) or fraction <= 0:
        fraction = DEFAULTS["arm_fraction"]
    roots = raw.get("roots")
    roots = ([str(r).strip().upper() for r in roots if isinstance(r, str) and r.strip()]
             if isinstance(roots, list) else [])
    salt = raw.get("salt")
    seen = _day(raw.get("seen_from")) or SEEN_FROM
    if seen <= HIDDEN[1]:
        seen = SEEN_FROM  # the seen span never reaches back into the hidden years
    hidden = raw.get("hidden")
    first, last = (_day(hidden[0]), _day(hidden[1])) if isinstance(hidden, list) and len(hidden) == 2 else (None, None)
    # The hidden window narrows inside the two hidden years only, and ends before the seen span: never a seen day.
    if not (first and last and first <= last and last < seen and int(first[:4]) == HIDDEN_YEARS[0]
            and int(last[:4]) == HIDDEN_YEARS[1]):
        first, last = HIDDEN
    lineage = whole("confirms_lineage", 1, 3)
    day = whole("children_per_day", 0, 48)
    return {"enabled": raw.get("enabled", DEFAULTS["enabled"]) is True,
            "mode": raw.get("mode") if raw.get("mode") in MODES else DEFAULTS["mode"],
            "arm_fraction": float(min(1.0, fraction)),
            "salt": salt.strip() if isinstance(salt, str) and salt.strip() else DEFAULTS["salt"],
            "roots": list(dict.fromkeys(roots)) or list(DEFAULTS["roots"]),
            "seen_from": seen, "hidden": [first, last], "stress": number("stress", 1.0, 3.0),
            "eta": number("eta", 0.25, 1.0), "looks": whole("looks", 1, 6),
            "c_select": number("c_select", 1.0, 2.33), "c_confirm": number("c_confirm", 1.0, 2.33),
            "confirms_family": min(lineage, whole("confirms_family", 1, 3)), "confirms_lineage": lineage,
            "val_tries": whole("val_tries", 1, 4),
            "parent_quantile": number("parent_quantile", 0.01, 0.5),
            "parent_window_hours": number("parent_window_hours", 1.0, 720.0),
            "parent_min_looks": whole("parent_min_looks", 1, 10000),
            "parent_bootstrap_f": number("parent_bootstrap_f", 0.0, 5.0),
            "children_per_parent": whole("children_per_parent", 1, 12),
            "children_per_round": min(day, whole("children_per_round", 0, 48)), "children_per_day": day,
            "child_cooldown_hours": number("child_cooldown_hours", 0.0, 168.0),
            "crossover_share": number("crossover_share", 0.0, 1.0),
            "donor_max_chars": whole("donor_max_chars", 0, 20000),
            "look_retry_hours": number("look_retry_hours", 0.25, 48.0), "look_attempts": whole("look_attempts", 1, 5)}


def _day(value: Any) -> str | None:
    """An ISO day as written ("2022-01-03"), or None."""
    if not isinstance(value, str):
        return None
    try:
        return dt.date.fromisoformat(value.strip()).isoformat()
    except ValueError:
        return None


def birth_roots(settings: Mapping[str, Any] | None) -> list[str] | None:
    """The roots the architect's births may use while the game is on (the core five, `cfg`'s `roots`), else None (its
    own `gym.roots`, as today)."""
    c = cfg(settings)
    return list(c["roots"]) if c["enabled"] else None


def seen_only(store: Any, settings: Mapping[str, Any] | None) -> bool:
    """The running swarm's Train span (its store's migrated objective, `settings.objective_span`) starts on or after the
    seen span's first day: no agent is shown a hidden day. Until a start migrates the span there, no look is made (the
    years would not be hidden)."""
    span = settings_mod.objective_span(store.get("train_objective"))
    return span.isoformat() >= cfg(settings)["seen_from"]


# ----------------------------------------------------------------------------------------------------------- assignment
def t0(store: Any, settings: Mapping[str, Any] | None = None) -> str | None:
    """T0: the first start with the game on, written once to the store's kv (`T0_KEY`). With `settings` that switch the
    game on (the swarm's start), it is written when it is missing; without, it is only read. None before."""
    value = store.get(T0_KEY)
    if isinstance(value, str) and value:
        return value
    if settings is None or not cfg(settings)["enabled"] or getattr(store, "readonly", False):
        return None
    with store.atomic():
        value = store.get(T0_KEY)
        if not (isinstance(value, str) and value):
            value = store.now()
            store.put(T0_KEY, value)
    return value


def fold(lineage: Any) -> tuple[int, int]:
    """(select year, confirm year) of a lineage: 2020 first when the first byte of sha256("ltcm-game-v1\\0" + lineage)
    is even, else 2021 first. Every member of a lineage has the same pair."""
    digest = hashlib.sha256(f"{FOLD_SALT}\0{lineage}".encode("utf-8")).digest()
    first, second = HIDDEN_YEARS
    return (first, second) if digest[0] % 2 == 0 else (second, first)


def arm(store: Any, fam: Mapping[str, Any] | None, settings: Mapping[str, Any] | None) -> str | None:
    """"game", "control", or None (legacy: the game off, no T0 yet, born before T0, or a root outside the core five)."""
    c = cfg(settings)
    if not c["enabled"] or not isinstance(fam, Mapping):
        return None
    return _arm_of(fam, c, t0(store))


def _arm_of(fam: Mapping[str, Any], c: Mapping[str, Any], start: str | None) -> str | None:
    if start is None:
        return None
    born = str(fam.get("born_at") or "")
    if not born or born < start:
        return None
    roots = fam.get("roots")
    roots = _loads(roots, []) if isinstance(roots, str) else roots
    core = set(c["roots"])
    if not isinstance(roots, (list, tuple)) or not roots or any(str(r).upper() not in core for r in roots):
        return None
    unit = str(fam.get("lineage") or fam.get("id") or "")
    return "game" if canary.in_arm(c["salt"], ARM_KEY, unit, c["arm_fraction"]) else "control"


def _loads(text: Any, default: Any = None) -> Any:
    if text is None or text == "":
        return default
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return default


def _dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _iso(t: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))


def _epoch(text: Any) -> float:
    try:
        return dt.datetime.fromisoformat(str(text).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return float("-inf")


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(float(value)) else None


# ----------------------------------------------------------------------------------------------------------- fitness
def fitness(result: Mapping[str, Any], year: Any) -> dict[str, Any]:
    """F of one year of a hidden run (the module docstring): {eligible, trades, days_traded, t_net, t_alpha, F, why}. F is
    min(t_net, t_alpha) when the year is eligible, else minus infinity (`why` says what failed)."""
    from ..gym.results import _t_of, roots_in_year  # standard library only, like this module

    y = str(year)
    out: dict[str, Any] = {"eligible": False, "trades": 0, "days_traded": 0, "t_net": None, "t_alpha": None,
                           "F": float("-inf"), "why": None}
    row = evidence.years_of(result).get(y) if isinstance(result, Mapping) else None
    block = result.get("drift") if isinstance(result, Mapping) else None
    years = block.get("years") if isinstance(block, Mapping) else None
    drift = years.get(y) if isinstance(years, Mapping) else None
    drift = drift if isinstance(drift, Mapping) else None
    if isinstance(row, Mapping):
        out["trades"], out["days_traded"] = int(row.get("trades") or 0), int(row.get("days_traded") or 0)
    if drift is not None:
        pnl, pp, days = _num(drift.get("pnl")), _num(drift.get("sum_pp")), drift.get("days")
        if pnl is not None and pp is not None and isinstance(days, int) and not isinstance(days, bool):
            out["t_net"] = _num(_t_of(pnl, pp, days, pp))
        out["t_alpha"] = _num(drift.get("t"))
    # The program's own roots: its NEEDS within the batch's, as the Train score reads them (`evidence.train_score`).
    wanted = {str(r).upper() for r in (result.get("roots") or ())} if isinstance(result, Mapping) else set()
    needs = result.get("needs") if isinstance(result, Mapping) else None
    declared = needs.get("roots") if isinstance(needs, Mapping) else None
    if isinstance(declared, (list, tuple)) and declared:
        wanted &= {str(r).upper() for r in declared}
    had = row.get("roots") if isinstance(row, Mapping) else None
    if not isinstance(had, list) and drift is not None and isinstance(drift.get("root_days"), Mapping):
        had = roots_in_year(drift["root_days"], int(drift.get("days") or 0))
    if not isinstance(result, Mapping) or result.get("status") != "ok":
        out["why"] = "the run did not complete"
    elif not isinstance(row, Mapping):
        out["why"] = "the run has no row for the year"
    elif out["trades"] < MIN_TRADES or out["days_traded"] < MIN_DAYS:
        out["why"] = f"{out['trades']} trades on {out['days_traded']} days (needs {MIN_TRADES} on {MIN_DAYS})"
    elif not isinstance(had, list) or not wanted or wanted - {str(r).upper() for r in had}:
        out["why"] = "a root of the program had no data in the year"
    elif out["t_net"] is None or out["t_alpha"] is None:
        out["why"] = "a t is null"
    else:
        out.update(eligible=True, F=min(out["t_net"], out["t_alpha"]))
    return out


def seen_fitness(block: Any, first_year: int | None = None) -> float | None:
    """F on a seen run's drift block (`drift_numbers` of a 1.5x Train run), pooled over its seen years (from `first_year`)
    and divided by the root of their count, so it reads per year: the metrics' seen_F. None when a figure is missing."""
    from ..gym.results import _t_of  # standard library only, like this module

    numbers = evidence.drift_numbers(block)
    if numbers is None:
        return None
    first = int(first_year if first_year is not None else SEEN_FROM[:4])
    years = {y: r for y, r in numbers["years"].items() if y[:4].isdigit() and int(y[:4]) >= first}
    if not years:
        return None
    total = pp = 0.0
    days = 0
    for row in years.values():
        pnl, sq = _num(row.get("pnl")), _num(row.get("sum_pp"))
        if pnl is None or sq is None or not isinstance(row.get("days"), int):
            return None
        total, pp, days = total + pnl, pp + sq, days + int(row["days"])
    t_net = _num(_t_of(total, pp, days, pp))
    could, t_alpha = evidence.pooled_drift_t(years)
    if not could or t_net is None or _num(t_alpha) is None:
        return None
    return min(t_net, float(t_alpha)) / math.sqrt(len(years))


def tier_of(f: Any, c_select: float) -> str:
    """The SELECT tier of F: PASS from `c_select`, ALIVE from 0, FAIL below (an ineligible year is minus infinity)."""
    value = _num(f)
    if value is None:
        return "FAIL"
    return "PASS" if value >= c_select else "ALIVE" if value >= 0 else "FAIL"


# ----------------------------------------------------------------------------------------------------------- storage
def ensure(store: Any) -> bool:
    """Create the game's tables on the store's connection (idempotent). False on a read-only store, which may still read
    them when a writer made them."""
    if getattr(store, "readonly", False):
        return False
    if getattr(store, "_game_ready", False):
        return True
    with store.lock:
        inside = bool(store._db.in_transaction)
        for statement in GAME_SQL:
            store._exec(statement)
        # Inside a caller's transaction the tables exist only if it commits: remember them only when they are durable.
        if not inside:
            store._game_ready = True
    return True


def _tables(store: Any) -> bool:
    if ensure(store):
        return True
    return bool(store._one("SELECT 1 AS ok FROM sqlite_master WHERE type='table' AND name='game_looks'"))


def _rows(store: Any, where: str = "1=1", args: Sequence[Any] = (), *, confirms: bool = False) -> list[dict[str, Any]]:
    """The game's looks (`where` over `game_looks`), oldest first, each with what its results say: `status` (its terminal
    row's, else "queued": in flight or waiting for its retry), `tier`, `years` (both years' figures of an "ok" row: read
    them only through `select_view`, and `_operator_years` for the metrics), `result_at`, `attempts` (its submissions),
    `errors` and `last_at` (its newest row, or the look itself). With `confirms`, `confirm` (its one CONFIRM read or None);
    without it the confirm table is never read and `confirm_view` refuses the row."""
    if not _tables(store):
        return []
    looks = store._all(f"SELECT * FROM game_looks WHERE {where} ORDER BY seq", tuple(args))
    if not looks:
        return []
    inner = f"SELECT seq FROM game_looks WHERE {where}"
    results: dict[int, list[dict[str, Any]]] = {}
    for r in store._all(f"SELECT * FROM game_results WHERE look_seq IN ({inner}) ORDER BY seq", tuple(args)):
        results.setdefault(int(r["look_seq"]), []).append(r)
    reads = ({int(r["look_seq"]): r for r in store._all(f"SELECT * FROM game_confirms WHERE look_seq IN ({inner})", tuple(args))}
             if confirms else {})
    out = []
    for look in looks:
        rows = results.get(int(look["seq"]), [])
        final = next((r for r in rows if r["status"] in TERMINAL), None)
        row = dict(look)
        row.update(status=final["status"] if final else "queued", tier=final.get("tier") if final else None,
                   years=_loads(final["years_json"], {}) if final and final["status"] == "ok" else None,
                   result_at=final["at"] if final else None,
                   attempts=1 + sum(1 for r in rows if r["status"] == "requeued"),
                   errors=sum(1 for r in rows if r["status"] == "error"),
                   last_at=rows[-1]["at"] if rows else look["at"])
        if confirms:
            read = reads.get(int(look["seq"]))
            row["confirm"] = ({"seq": int(read["seq"]), "f_confirm": read["f_confirm"], "confirmed": bool(read["confirmed"]),
                               "at": read["at"]} if read else None)
        out.append(row)
    return out


def select_view(row: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """A landed look's SELECT year: {year, F (minus infinity when ineligible), eligible, tier, t_net, t_alpha, trades,
    days_traded}; None for a look that has not landed "ok". What every decision but the gate reads of a result."""
    if not isinstance(row, Mapping) or row.get("status") != "ok" or not isinstance(row.get("years"), Mapping):
        return None
    year = int(row["select_year"])
    figures = row["years"].get(str(year)) or {}
    f = _num(figures.get("F"))
    eligible = bool(figures.get("eligible")) and f is not None
    return {"year": year, "F": f if eligible else float("-inf"), "eligible": eligible, "tier": row.get("tier"),
            "t_net": _num(figures.get("t_net")), "t_alpha": _num(figures.get("t_alpha")),
            "trades": int(figures.get("trades") or 0), "days_traded": int(figures.get("days_traded") or 0)}


def confirm_view(row: Mapping[str, Any] | None) -> dict[str, Any]:
    """A look's CONFIRM year as the one-shot gate read it: {year, F (minus infinity when ineligible), confirmed}. RAISES
    `Sealed` unless the look has its `game_confirms` row (a row read without confirms never has one)."""
    read = row.get("confirm") if isinstance(row, Mapping) else None
    if not isinstance(read, Mapping):
        raise Sealed("a look's CONFIRM year is read only through its one-shot read (no game_confirms row for it)")
    f = _num(read.get("f_confirm"))
    select = int(row["select_year"])  # type: ignore[index]
    year = next(y for y in HIDDEN_YEARS if y != select)
    return {"year": year, "F": f if f is not None else float("-inf"), "confirmed": bool(read.get("confirmed"))}


def _operator_years(row: Mapping[str, Any]) -> tuple[float | None, float | None]:
    """(F on the SELECT year, F on the CONFIRM year) of a landed look, None for an ineligible year: THE OPERATOR'S READ,
    for `metrics` alone (the report no agent reads). No decision may call it."""
    years = row.get("years") if isinstance(row, Mapping) else None
    if not isinstance(years, Mapping):
        return None, None
    select = int(row["select_year"])
    other = next(y for y in HIDDEN_YEARS if y != select)

    def f_of(year: int) -> float | None:
        figures = years.get(str(year)) or {}
        return _num(figures.get("F")) if figures.get("eligible") else None

    return f_of(select), f_of(other)


def _result(store: Any, look_seq: int, status: str, years: Mapping[str, Any], tier: str | None = None) -> bool:
    """One `game_results` row; a second terminal row for a look is never written (False)."""
    with store.atomic():
        if store._one("SELECT 1 AS done FROM game_results WHERE look_seq=? AND status IN ('ok','failed','cancelled')",
                      (int(look_seq),)):
            return False
        store._exec("INSERT INTO game_results(look_seq, at, status, years_json, tier) VALUES(?,?,?,?,?)",
                    (int(look_seq), store.now(), status, _dumps(years), tier))
    return True


def _ancestry(store: Any, fid: str) -> tuple[int, str | None]:
    """(generation, game parent) of a family: 0 and None for a founder, else one more than its parent's."""
    row = store._one("SELECT parent FROM game_children WHERE child=?", (fid,))
    parent = str(row["parent"]) if row else None
    generation, seen = 0, {fid}
    while row is not None and str(row["parent"]) not in seen and generation < 1000:
        generation += 1
        seen.add(str(row["parent"]))
        row = store._one("SELECT parent FROM game_children WHERE child=?", (str(row["parent"]),))
    return generation, parent


def _record_look(store: Any, fam: Mapping[str, Any], side: str, role: str, version: Mapping[str, Any], c: Mapping[str, Any],
                 *, seen_score: Any = None, seen_run: Any = None, seen_f: Any = None) -> int:
    """One `game_looks` row (inside the caller's transaction)."""
    ensure(store)
    generation, parent = _ancestry(store, str(fam["id"]))
    job = {"start": c["hidden"][0], "end": c["hidden"][1], "stress": c["stress"], "purpose": PURPOSE}
    cur = store._exec("INSERT INTO game_looks(at, family, lineage, arm, role, version, sha, generation, parent, select_year, "
                      "seen_score, seen_run, seen_f, private_job) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                      (store.now(), str(fam["id"]), str(fam["lineage"]), side, role, int(version["n"]), str(version["sha"]),
                       generation, parent, fold(fam["lineage"])[0], _num(seen_score), None if seen_run is None else str(seen_run),
                       _num(seen_f), _dumps(job)))
    return int(cur.lastrowid or 0)


def _sha_looked(store: Any, lineage: str, sha: str) -> bool:
    """A look at this program (the version's sha) in the lineage that did not end failed or cancelled."""
    return any(r["status"] not in ("failed", "cancelled") for r in _rows(store, "lineage=? AND sha=?", (lineage, sha)))


# ----------------------------------------------------------------------------------------------------------- looks
def maybe_look(researcher: Any, fid: str, n: int, seen_result: Mapping[str, Any]) -> dict[str, Any] | None:
    """THE LADDER (the module docstring), called on the pool's dispatcher thread after version `n`'s 1.5x seen run landed
    with a profit and was not demoted (`researcher.robust_landed`). Opens the look and queues its hidden run when every
    trigger holds: {"look": seq} then, {"look": None, "why": ...} when the family plays but one does not, None when it
    does not play. Never raises."""
    try:
        store = researcher.store
        settings = getattr(researcher, "settings", None) or {}
        c = cfg(settings)
        if not c["enabled"]:
            return None
        fam = store.family(str(fid))
        side = arm(store, fam, settings) if fam is not None and not fam.get("retired_at") else None
        if side is None:
            return None
        n = int(n)
        state = fam.get("state") or {}
        why = None
        summary = (seen_result or {}).get("summary") or {}
        run = store.run(str(state.get("best_train_run"))) if state.get("best_train_run") else None
        span = (run or {}).get("summary", {}).get("train_from") if run else None
        if not seen_only(store, settings):
            why = "the running Train span is not the seen span yet"
        elif state.get("best_train_version") is None or int(state["best_train_version"]) != n:
            why = "not the family's best by Train score"
        elif _num(fam.get("best_train")) is None or run is None or run.get("version") != n \
                or (run.get("summary") or {}).get("train_eligible") is False or (span is not None and str(span) < c["seen_from"]):
            why = "its Train score is not an eligible score over the seen span"
        elif n in (state.get("robust_failed") or []) or (seen_result or {}).get("status") != "ok" \
                or not (_num(summary.get("pnl")) or 0.0) > 0:
            why = "its 1.5x seen run did not make money"
        version = store.version(str(fid), n) if why is None else None
        if why is None and (version is None or not version.get("code")):
            why = "its program is not kept"
        if why is not None:
            return {"look": None, "why": why}
        seq = None
        with store.atomic():
            ensure(store)
            fam = store.family(str(fid)) or fam
            ladder = [r for r in _rows(store, "family=? AND role='ladder'", (str(fid),))]
            used = [r for r in ladder if r["status"] not in ("failed", "cancelled")]
            score = float(fam["best_train"])
            best = (fam.get("state") or {}).get("best_train_version")
            if fam.get("retired_at"):
                why = "the family retired"
            elif best is None or int(best) != n:
                why = "not the family's best by Train score"
            elif any(r["status"] not in TERMINAL for r in ladder):
                why = "a look is in flight"
            elif len(used) >= c["looks"]:
                why = "its looks are spent"
            elif used and _num(used[-1]["seen_score"]) is not None and score < float(used[-1]["seen_score"]) + c["eta"]:
                why = "its Train score does not beat the last looked score by eta"
            elif _sha_looked(store, str(fam["lineage"]), str(version["sha"])):  # type: ignore[index]
                why = "its program was looked at in its lineage"
            else:
                seq = _record_look(store, fam, side, "ladder", version, c, seen_score=score,  # type: ignore[arg-type]
                                   seen_run=state.get("best_train_run"),
                                   seen_f=seen_fitness((seen_result or {}).get("drift"), int(c["seen_from"][:4])))
        if seq is None:
            return {"look": None, "why": why}
        _submit(store, getattr(researcher, "pool", None), seq, fam, version, c,  # type: ignore[arg-type]
                lambda: getattr(researcher, "settings", None) or settings)
        store.event(EVENT, str(fid), {"family": str(fid), "version": n, "look": "queued"})
        return {"look": seq}
    except Exception:  # noqa: BLE001 - on the dispatcher's thread: the game never breaks the pool
        return None


def _submit(store: Any, pool: Any, look_seq: int, fam: Mapping[str, Any], version: Mapping[str, Any], c: Mapping[str, Any],
            settings_of: Callable[[], Mapping[str, Any] | None]) -> GymJob | None:
    """Queue a look's hidden run: one Train job over the hidden window at `stress`, purpose "private", its result to
    `landed` and its failure to the look's attempts (both on the dispatcher's thread, never raising)."""
    from .researcher import needs_roots  # a local import: the researcher calls this module

    code = str(version.get("code") or "")
    job = GymJob(family=str(fam["id"]), version=int(version["n"]), code=code, params=dict(version.get("params") or {}),
                 window="train", roots=tuple(needs_roots(code, fam.get("roots") or ())), stress=float(c["stress"]),
                 purpose=PURPOSE, start=c["hidden"][0], end=c["hidden"][1], priority=PRIVATE_PRIORITY)
    key = (str(getattr(store, "path", id(store))), int(look_seq))
    job.late = lambda result: _deliver(store, look_seq, result, settings_of)
    job.late_fail = lambda why: _undelivered(store, look_seq, why)
    with _inflight_lock:
        _inflight[key] = job
    submit = getattr(pool, "submit", None)
    if submit is None:
        _undelivered(store, look_seq, "no Gym pool")
        return None
    try:
        submit(job)
    except Exception as exc:  # noqa: BLE001
        _undelivered(store, look_seq, f"the pool refused it: {type(exc).__name__}")
        return None
    return job


def _deliver(store: Any, look_seq: int, result: Mapping[str, Any], settings_of: Callable[[], Mapping[str, Any] | None]) -> None:
    try:
        landed(store, look_seq, result, settings_of())
    except Exception:  # noqa: BLE001 - on the dispatcher's thread
        pass
    finally:
        with _inflight_lock:
            _inflight.pop((str(getattr(store, "path", id(store))), int(look_seq)), None)


def _undelivered(store: Any, look_seq: int, why: Any) -> None:
    try:
        _result(store, look_seq, "error", {"why": str(why or "")[:300]})
    except Exception:  # noqa: BLE001 - on the dispatcher's thread
        pass
    finally:
        with _inflight_lock:
            _inflight.pop((str(getattr(store, "path", id(store))), int(look_seq)), None)


def landed(store: Any, look_seq: int, result: Mapping[str, Any], settings: Mapping[str, Any] | None = None) -> dict[str, Any] | None:
    """A look's hidden run came back: both years scored (`fitness`) and recorded with the SELECT tier; a result that is not
    "ok" is a failed attempt (`requeue_stale` queues it again). In mode "gate", a game-arm look's SELECT PASS reads the
    CONFIRM year once (`game_confirms`) while its family has read fewer than `confirms_family` and its lineage fewer than
    `confirms_lineage`, and its family is alive. Idempotent: a look that has its terminal row is left as it is. Returns
    {status, tier, confirmed} (None for no such look)."""
    c = cfg(settings)
    ensure(store)
    with store.atomic():
        look = store._one("SELECT * FROM game_looks WHERE seq=?", (int(look_seq),))
        if look is None:
            return None
        if store._one("SELECT 1 AS done FROM game_results WHERE look_seq=? AND status IN ('ok','failed','cancelled')",
                      (int(look_seq),)):
            return {"status": "done", "tier": None, "confirmed": None}
        if not isinstance(result, Mapping) or result.get("status") != "ok":
            reason = (result or {}).get("reason") if isinstance(result, Mapping) else None
            _result(store, look_seq, "error", {"why": f"{(result or {}).get('status') if isinstance(result, Mapping) else None}: "
                                                      f"{str(reason or '')[:200]}"})
            return {"status": "error", "tier": None, "confirmed": None}
        select = int(look["select_year"])
        other = next(y for y in HIDDEN_YEARS if y != select)
        years = {str(y): fitness(result, y) for y in (select, other)}
        stored = {y: {**v, "F": v["F"] if math.isfinite(v["F"]) else None} for y, v in years.items()}
        tier = tier_of(stored[str(select)]["F"], c["c_select"])
        _result(store, look_seq, "ok", stored, tier)
        confirmed = None
        if c["enabled"] and c["mode"] == "gate" and look["arm"] == "game" and tier == "PASS":
            fam = store.family(str(look["family"])) or {}
            family_reads = store._one("SELECT COUNT(*) AS n FROM game_confirms k JOIN game_looks l ON l.seq=k.look_seq "
                                      "WHERE l.family=?", (look["family"],))["n"]
            lineage_reads = store._one("SELECT COUNT(*) AS n FROM game_confirms k JOIN game_looks l ON l.seq=k.look_seq "
                                       "WHERE l.lineage=?", (look["lineage"],))["n"]
            if fam and not fam.get("retired_at") and int(family_reads) < c["confirms_family"] \
                    and int(lineage_reads) < c["confirms_lineage"]:
                figures = stored[str(other)]
                confirmed = bool(figures["eligible"]) and figures["F"] is not None and figures["F"] >= c["c_confirm"]
                store._exec("INSERT INTO game_confirms(look_seq, at, f_confirm, confirmed) VALUES(?,?,?,?)",
                            (int(look_seq), store.now(), figures["F"], 1 if confirmed else 0))
    return {"status": "ok", "tier": tier, "confirmed": confirmed}


def requeue_stale(store: Any, settings: Mapping[str, Any] | None, pool: Any, clock: Callable[[], float] | None = None) -> dict[str, int]:
    """The looks whose hidden run failed or was lost (a restart) and has not been in this process's pool for
    `look_retry_hours`: queued again, up to `look_attempts` submissions in all; past them recorded "failed" (it does not
    count against the family's looks). A look of a retired family is "cancelled". The tournament's round calls it."""
    c = cfg(settings)
    out = {"requeued": 0, "failed": 0, "cancelled": 0}
    if not c["enabled"] or not _tables(store):
        return out
    now = float((clock or store.clock)())
    path = str(getattr(store, "path", id(store)))
    open_looks = _rows(store, "seq NOT IN (SELECT look_seq FROM game_results WHERE status IN ('ok','failed','cancelled'))")
    for row in open_looks:
        with _inflight_lock:
            busy = (path, int(row["seq"])) in _inflight
        if busy or now - _epoch(row["last_at"]) < c["look_retry_hours"] * 3600.0:
            continue
        fam = store.family(str(row["family"]))
        if fam is None or fam.get("retired_at"):
            out["cancelled"] += _result(store, row["seq"], "cancelled", {"why": "the family retired"})
            continue
        version = store.version(str(row["family"]), int(row["version"]))
        if row["attempts"] >= c["look_attempts"] or version is None or not version.get("code"):
            out["failed"] += _result(store, row["seq"], "failed",
                                     {"why": f"{row['attempts']} attempts" if version and version.get("code") else "no program"})
            continue
        if not _result(store, row["seq"], "requeued", {}):
            continue  # it landed meanwhile
        _submit(store, pool, int(row["seq"]), fam, version, c, lambda s=settings: s)
        out["requeued"] += 1
    return out


def _seen_of(store: Any, fam: Mapping[str, Any], n: int, c: Mapping[str, Any]) -> tuple[float | None, str | None, float | None]:
    """(Train score, its run, seen_F) of version `n` over the running span: its newest eligible Train run at the normal
    spread, and its newest 1.5x run's drift figures."""
    span = settings_mod.objective_span(store.get("train_objective")).isoformat()
    score = run = seen = None
    for row in store.version_runs(str(fam["id"]), int(n), window="train", stress=1.0, limit=50):
        s = row.get("summary") or {}
        if row.get("status") == "ok" and s.get("train_eligible") is True and _num(s.get("train_score")) is not None \
                and str(s.get("train_from") or settings_mod.TRAIN_CORE_START.isoformat()) == span:
            score, run = float(s["train_score"]), str(row["run_id"])
            break
    for row in store.version_runs(str(fam["id"]), int(n), window="train", stress=1.5, limit=20):
        s = row.get("summary") or {}
        if row.get("status") == "ok" and s.get("drift") \
                and str(s.get("train_from") or settings_mod.TRAIN_CORE_START.isoformat()) == span:
            seen = seen_fitness(s["drift"], int(c["seen_from"][:4]))
            break
    return score, run, seen


def shadow_validated(store: Any, settings: Mapping[str, Any] | None, pool: Any,
                     clock: Callable[[], float] | None = None) -> list[int]:
    """CONTROL'S EXTRA LOOKS (records only): every control-arm family's validated version (`validation_version`) whose
    program its lineage has not looked at gets a look ("validated": it counts against nothing). The tournament's round
    calls it after Validation. The looks opened."""
    c = cfg(settings)
    if not c["enabled"] or not seen_only(store, settings):
        return []
    ensure(store)
    start = t0(store)
    opened = []
    for fam in store.families(alive=True):
        n = (fam.get("state") or {}).get("validation_version")
        if n is None or _arm_of(fam, c, start) != "control":
            continue
        version = store.version(str(fam["id"]), int(n))
        if version is None or not version.get("code"):
            continue
        score, run, seen = _seen_of(store, fam, int(n), c)
        with store.atomic():
            if _sha_looked(store, str(fam["lineage"]), str(version["sha"])):
                continue
            seq = _record_look(store, fam, "control", "validated", version, c, seen_score=score, seen_run=run, seen_f=seen)
        _submit(store, pool, seq, fam, version, c, lambda s=settings: s)
        store.event(EVENT, str(fam["id"]), {"family": str(fam["id"]), "version": int(n), "look": "queued"})
        opened.append(seq)
    return opened


# ----------------------------------------------------------------------------------------------------------- decisions
def _fid(fam: Any) -> str:
    return str(fam["id"]) if isinstance(fam, Mapping) else str(fam)


def candidate(store: Any, fam: Any) -> int | None:
    """The game-arm family's version for Validation (mode "gate"): its latest CONFIRMED version (by its CONFIRM read), or
    None without one."""
    read = [r for r in _rows(store, "family=?", (_fid(fam),), confirms=True)
            if r.get("confirm") is not None and confirm_view(r)["confirmed"]]
    return int(max(read, key=lambda r: r["confirm"]["seq"])["version"]) if read else None


def _tried(store: Any, fid: str) -> list[int]:
    """The versions of a family that have had a Validation run (its own or an inherited verdict's rows): its tries."""
    return [int(r["version"]) for r in store._all("SELECT DISTINCT version FROM runs WHERE family=? AND window='validation' "
                                                  "AND stress=1.0 AND version IS NOT NULL ORDER BY version", (fid,))]


def validations_left(store: Any, fam: Any, settings: Mapping[str, Any] | None) -> int:
    """Validation tries a game-arm family has left: `val_tries` less the versions already validated, never below 0."""
    return max(0, cfg(settings)["val_tries"] - len(_tried(store, _fid(fam))))


def seen_robust_ok(store: Any, fam: Any, n: Any) -> bool:
    """A game-arm version's robustness requirement is met by its ladder look: a look needed a positive 1.5x seen run, and
    the family's state keeps only its last six versions' robustness figures."""
    if n is None or not _tables(store):
        return False
    return store._one("SELECT 1 AS ok FROM game_looks WHERE family=? AND version=? AND role='ladder' LIMIT 1",
                      (_fid(fam), int(n))) is not None


def look_seen_run(store: Any, fam: Any, n: Any) -> str | None:
    """The seen Train run a game-arm version's ladder look recorded (`Tournament.validate`'s eligible Train run for it), or
    None."""
    if n is None or not _tables(store):
        return None
    row = store._one("SELECT seen_run FROM game_looks WHERE family=? AND version=? AND role='ladder' AND seen_run IS NOT NULL "
                     "ORDER BY seq DESC LIMIT 1", (_fid(fam), int(n)))
    return str(row["seen_run"]) if row else None


def in_flight(store: Any, fam: Any) -> bool:
    """A look of the family's has not landed (its hidden run is queued, out, or waiting for its retry): THE GAME'S
    VALIDATION WAIT reads it (`Tournament.game_dormant`), never a figure."""
    if not _tables(store):
        return False
    return any(r["status"] not in TERMINAL for r in _rows(store, "family=?", (_fid(fam),)))


def looks_used(store: Any, fam: Any) -> int:
    """The family's ladder looks that count against `looks` (in flight or landed; a failed or cancelled one does not)."""
    if not _tables(store):
        return 0
    return sum(1 for r in _rows(store, "family=? AND role='ladder'", (_fid(fam),)) if r["status"] not in ("failed", "cancelled"))


def retire_reason(store: Any, fam: Mapping[str, Any], settings: Mapping[str, Any] | None) -> str | None:
    """The game's reason to retire a living game-arm Gym family in mode "gate" (the module docstring), else None: its
    looks spent without a SELECT PASS (all landed), two failed CONFIRM reads, or its Validation tries used and every one
    failed (the tournament's own verdicts, `validation_verdicts`). Never a figure, a tier or a year in the reason."""
    c = cfg(settings)
    if not (c["enabled"] and c["mode"] == "gate") or not isinstance(fam, Mapping) or fam.get("retired_at"):
        return None
    if (fam.get("band") or "gym") != "gym" or arm(store, fam, settings) != "game" or not _tables(store):
        return None
    rows = _rows(store, "family=?", (str(fam["id"]),), confirms=True)
    ladder = [r for r in rows if r["role"] == "ladder" and r["status"] not in ("failed", "cancelled")]
    if len(ladder) >= c["looks"] and all(r["status"] == "ok" for r in ladder) \
            and not any((select_view(r) or {}).get("tier") == "PASS" for r in ladder):
        return f"spent its {_WORDS.get(c['looks'], str(c['looks']))} private looks without a pass"
    failed = sum(1 for r in rows if r.get("confirm") is not None and not confirm_view(r)["confirmed"])
    if failed >= c["confirms_family"]:
        return f"failed its private confirmation {_TIMES.get(c['confirms_family'], str(c['confirms_family']) + ' times')}"
    tried = _tried(store, str(fam["id"]))
    verdicts = (fam.get("state") or {}).get("validation_verdicts") or {}
    if len(tried) >= c["val_tries"] and all(isinstance(verdicts.get(str(v)), Mapping) and verdicts[str(v)].get("passed") is False
                                            for v in tried):
        return f"used its {_WORDS.get(c['val_tries'], str(c['val_tries']))} Validation tries"
    return None


def parents(store: Any, settings: Mapping[str, Any] | None, clock: Callable[[], float] | None = None) -> list[dict[str, Any]]:
    """The game-arm families that may breed now, best first: {family, look, version, lineage, select_year, F} for each
    one's best qualifying look (the module docstring's REPRODUCTION). Reads the SELECT year only (`select_view`), and never
    the confirm table."""
    c = cfg(settings)
    if not _tables(store):
        return []
    now = float((clock or store.clock)())
    since = _iso(now - c["parent_window_hours"] * 3600.0)
    landed_rows = [r for r in _rows(store, "arm='game'") if r["status"] == "ok" and str(r["result_at"] or "") >= since]
    figures = [(r, select_view(r)["F"]) for r in landed_rows]  # type: ignore[index]
    if len(figures) >= c["parent_min_looks"]:
        ranked = sorted((f for _, f in figures), reverse=True)
        bar = ranked[max(1, math.ceil(c["parent_quantile"] * len(ranked))) - 1]
    else:
        bar = c["parent_bootstrap_f"]
    best: dict[str, tuple[float, dict[str, Any]]] = {}
    for row, f in figures:
        if not (math.isfinite(f) and f > 0 and f >= bar):
            continue
        held = best.get(str(row["family"]))
        if held is None or (f, row["seq"]) > (held[0], held[1]["seq"]):
            best[str(row["family"])] = (f, row)
    cooldown = _iso(now - c["child_cooldown_hours"] * 3600.0)
    out = []
    for fid, (f, row) in best.items():
        kids = store._all("SELECT g.child, g.at, f.retired_at FROM game_children g LEFT JOIN families f ON f.id=g.child "
                          "WHERE g.parent=?", (fid,))
        if sum(1 for k in kids if k["retired_at"] is None) >= c["children_per_parent"]:
            continue
        if any(str(k["at"]) > cooldown for k in kids):
            continue
        out.append({"family": fid, "look": int(row["seq"]), "version": int(row["version"]), "lineage": str(row["lineage"]),
                    "select_year": int(row["select_year"]), "F": f})
    out.sort(key=lambda p: (-p["F"], p["family"]))
    return out


def reproduce(store: Any, settings: Mapping[str, Any] | None, clock: Callable[[], float] | None = None) -> list[str]:
    """REPRODUCTION (mode "gate"): children of the qualifying parents (`parents`), best first, at most `children_per_round`
    a round and `children_per_day` in any 24 hours, while the living population is under `population.ceiling`. Each child
    is born in one store transaction. The children's ids."""
    c = cfg(settings)
    if not (c["enabled"] and c["mode"] == "gate"):
        return []
    ensure(store)
    clock = clock or store.clock
    now = float(clock())
    ceiling = int(((settings or {}).get("population") or {}).get("ceiling", 96))
    today = int(store._one("SELECT COUNT(*) AS n FROM game_children WHERE at>=?", (_iso(now - 86400.0),))["n"])
    room = min(c["children_per_round"], c["children_per_day"] - today)
    if room <= 0:
        return []
    qualified = parents(store, settings, clock=clock)
    born: list[str] = []
    for parent in qualified:
        if len(born) >= room:
            break
        with store.atomic():
            if int(store._one("SELECT COUNT(*) AS n FROM families WHERE retired_at IS NULL")["n"]) >= ceiling:
                break
            child = _breed(store, c, parent, qualified)
        if child:
            born.append(child)
    return born


def _seed(*parts: Any) -> int:
    return int.from_bytes(hashlib.sha256("\0".join(str(p) for p in parts).encode("utf-8")).digest()[:8], "big")


def _breed(store: Any, c: Mapping[str, Any], parent: Mapping[str, Any], qualified: Sequence[Mapping[str, Any]]) -> str | None:
    """One child of `parent` (inside the caller's transaction): MUTATE or CROSSOVER (the module docstring)."""
    fid = str(parent["family"])
    fam = store.family(fid)
    version = store.version(fid, int(parent["version"]))
    if fam is None or version is None or not version.get("code"):
        return None
    k = int(store._one("SELECT COUNT(*) AS n FROM game_children WHERE parent=?", (fid,))["n"])
    rng = random.Random(_seed(c["salt"], "child", fid, k))
    donors = []
    for other in qualified:
        if other["family"] == fid or other["select_year"] != parent["select_year"] or other["lineage"] == parent["lineage"]:
            continue
        program = store.version(str(other["family"]), int(other["version"]))
        if program is not None and program.get("code") and len(program["code"]) <= c["donor_max_chars"]:
            donors.append(other)
    op = "crossover" if donors and rng.random() < c["crossover_share"] else "mutate"
    spec = {key: value for key, value in dict(fam.get("spec") or {}).items()
            if key not in ("signal", "game_directive", "game_donor", "id", "slug")}
    spec.update(id=f"g-{_seed(fid, version['n'], k, store.now()):016x}"[:10], mechanism=fam["mechanism"],
                structure=fam["structure"], roots=list(fam["roots"]))
    directive = donor = None
    if op == "mutate":
        directive = (_seed(fid) + k) % len(DIRECTIVES)
        spec["game_directive"] = directive
    else:
        pick = donors[rng.randrange(len(donors))]
        donor = {"family": str(pick["family"]), "version": int(pick["version"])}
        spec["game_donor"] = donor
    # The child joins its (signal) parent's lineage: its trials, its holdout looks, and its fold.
    child = store.add_family(spec, origin=ORIGIN, parent=fid)
    store.add_version(child["id"], version["code"], version.get("params") or {}, author="game",
                      note=f"the parent's version {version['n']}")
    card = cards.card_of(store, fid)
    if card is not None:
        cards.put(store, child["id"], card["card"], fam["structure"])
    store.note(child["id"], f"{CHILD_NOTE} The change: {DIRECTIVES[directive] if directive is not None else CROSSOVER}"
                            + ("" if directive is not None else " The donor's program is in your brief."))
    store._exec("INSERT INTO game_children(at, child, parent, op, directive, donor, parent_look) VALUES(?,?,?,?,?,?,?)",
                (store.now(), child["id"], fid, op, directive, _dumps(donor) if donor else None, int(parent["look"])))
    # No `swarm.born` event: the site's tape, the births' quota (`allocation.BirthQuota`) and the funnel read those, and a
    # child's birth tells that its parent passed a private look. The game's own table is its record.
    return str(child["id"])


# ----------------------------------------------------------------------------------------------------------- visibility
def _playing(store: Any, settings: Mapping[str, Any] | None) -> tuple[dict[str, Any], str | None]:
    c = cfg(settings)
    return c, (t0(store) if c["enabled"] else None)


def visible_families(store: Any, *, alive: bool | None = None, settings: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    """`store.families(alive=...)` less the game arm's (the architect's and the strategist's content reads): with the game
    off or before T0, exactly the store's list."""
    fams = store.families(alive=alive)
    c, start = _playing(store, settings)
    if start is None:
        return fams
    return [f for f in fams if _arm_of(f, c, start) != "game"]


def visible_graveyard(store: Any, query: str = "", limit: int = 8, *, settings: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    """`store.graveyard(query, limit=...)` for every reader (the researchers' tool, the architect, the strategist) less two
    kinds of row, ranked over the rows that are left: a family born before T0 and retired since `SWITCH_AT` (it learned
    on the hidden years), and a game-arm family (its reasons and notes tell its SELECT outcomes). With the game off or
    before T0, exactly the store's read."""
    c, start = _playing(store, settings)
    if start is None:
        return store.graveyard(query, limit=limit)
    from .store import rank_graveyard

    rows = store._all("SELECT g.*, f.born_at AS _born, f.retired_at AS _retired, f.lineage AS _lineage, f.roots AS _roots, "
                      "f.id AS _id FROM graveyard g LEFT JOIN families f ON f.id=g.family ORDER BY g.at DESC, g.family")
    kept = [r for r in rows if not _quarantined(r, c, start)]
    out = []
    for r in rank_graveyard(kept, query)[:limit]:
        r["roots"] = _loads(r["roots"], [])
        r["best"] = _loads(r["best"], {})
        out.append(r)
    return out


def _quarantined(row: dict[str, Any], c: Mapping[str, Any], start: str) -> bool:
    """Whether a graveyard row joined with its family's columns (`_born`, `_retired`, `_lineage`, `_roots`, `_id`, which
    this pops) is one no reader sees: (a) its family was born before T0 and retired since `SWITCH_AT` (it learned on the
    hidden years), or (b) its family plays in the game arm (its lesson tells its SELECT outcomes)."""
    fam = {"id": row.pop("_id"), "born_at": row.pop("_born"), "lineage": row.pop("_lineage"), "roots": row.pop("_roots")}
    retired = row.pop("_retired")
    if fam["id"] is None:
        return False
    if str(fam["born_at"] or "") < start and str(retired or row["at"]) >= SWITCH_AT:
        return True
    return _arm_of(fam, c, start) == "game"


def quarantined(store: Any, settings: Mapping[str, Any] | None) -> frozenset[str]:
    """The families whose graveyard rows `visible_graveyard` drops, for a reader that reads the table itself (the rebirth
    index, `cards.RebirthIndex`; the architect's and the strategist's own SQL): empty with the game off or before T0."""
    c, start = _playing(store, settings)
    if start is None:
        return frozenset()
    rows = store._all("SELECT g.family, g.at, f.born_at AS _born, f.retired_at AS _retired, f.lineage AS _lineage, "
                      "f.roots AS _roots, f.id AS _id FROM graveyard g LEFT JOIN families f ON f.id=g.family")
    return frozenset(str(r["family"]) for r in rows if _quarantined(r, c, start))


# ----------------------------------------------------------------------------------------------------------- text
def status_text(store: Any, fam: Mapping[str, Any], settings: Mapping[str, Any] | None) -> str:
    """The game-arm researcher's one status line in mode "gate" (how many looks it used; never a figure, a tier, a year
    or a result), else ""."""
    c = cfg(settings)
    if not (c["enabled"] and c["mode"] == "gate") or arm(store, fam, settings) != "game":
        return ""
    return STATUS.format(eta=c["eta"], stress=c["stress"], used=looks_used(store, fam), looks=c["looks"])


def brief_text(store: Any, fam: Mapping[str, Any], settings: Mapping[str, Any] | None) -> str:
    """A game child's change for its brief (its directive, or the donor's program to take execution from), else ""."""
    c = cfg(settings)
    if not c["enabled"] or arm(store, fam, settings) != "game":
        return ""
    spec = fam.get("spec") or {}
    directive, donor = spec.get("game_directive"), spec.get("game_donor")
    if isinstance(directive, int) and not isinstance(directive, bool) and 0 <= directive < len(DIRECTIVES):
        return f"THE GAME: {CHILD_NOTE}\nThe change: {DIRECTIVES[directive]}"
    if isinstance(donor, Mapping) and donor.get("family") and isinstance(donor.get("version"), int):
        program = store.version(str(donor["family"]), int(donor["version"])) or {}
        code = str(program.get("code") or "")[: c["donor_max_chars"]]
        if code:
            return f"THE GAME: {CHILD_NOTE}\nThe change: {CROSSOVER} The donor's program:\n```python\n{code}\n```"
    return ""


# ----------------------------------------------------------------------------------------------------------- metrics
def _ranks(xs: Sequence[float]) -> list[float]:
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2.0 + 1.0
        i = j + 1
    return ranks


def spearman(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    """Spearman's rank correlation with average ranks for ties; None under three pairs or with no spread."""
    if len(xs) != len(ys) or len(xs) < 3:
        return None
    rx, ry = _ranks(xs), _ranks(ys)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    sxy = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    sxx, syy = sum((a - mx) ** 2 for a in rx), sum((b - my) ** 2 for b in ry)
    return sxy / math.sqrt(sxx * syy) if sxx > 0 and syy > 0 else None


def _mean(xs: Sequence[float]) -> float | None:
    return sum(xs) / len(xs) if xs else None


def _cluster_ci(items: Sequence[Mapping[str, Any]], stat: Callable[[list[Mapping[str, Any]]], float | None], *,
                draws: int, rng: random.Random) -> list[float] | None:
    """The family-cluster bootstrap interval (`BOOT_LEVEL`, two-sided) of `stat` over `items` (each with its `family`):
    families drawn with replacement, all their items with them. None when fewer than two families or no draw has a value."""
    groups: dict[str, list[Mapping[str, Any]]] = {}
    for item in items:
        groups.setdefault(str(item["family"]), []).append(item)
    names = sorted(groups)
    if len(names) < 2 or draws <= 0:
        return None
    values = []
    for _ in range(draws):
        sample = [item for _n in names for item in groups[names[rng.randrange(len(names))]]]
        value = stat(sample)
        if value is not None and math.isfinite(value):
            values.append(value)
    if not values:
        return None
    values.sort()
    tail = (1.0 - BOOT_LEVEL) / 2.0

    def pick(q: float) -> float:
        return values[min(len(values) - 1, max(0, int(round(q * (len(values) - 1)))))]

    return [pick(tail), pick(1.0 - tail)]


#: THE LEAK SCAN (R1a): a hidden year as a quoted key or an ISO date in what a game-arm researcher was shown. A tool's
#: answer is JSON text inside the conversation's JSON, so its quotes come escaped (`\\"2020\\"`): any backslashes before a
#: quote are read through.
_HIDDEN_TEXT = re.compile(r'\\*"20(?:20|21)\\*"|(?<!\d)20(?:20|21)-\d\d-\d\d')


def _leak_scan(store: Any, rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Each game-arm family's conversation (`convo`, every tool output it was shown) searched for a hidden year key or
    date and for any of its looks' hidden figures to four places."""
    families = sorted({str(r["family"]) for r in rows if r["arm"] == "game"})
    figures: dict[str, set[str]] = {}
    for r in rows:
        for fig in (r.get("years") or {}).values() if r["arm"] == "game" else ():
            for key in ("t_net", "t_alpha", "F"):
                value = _num((fig or {}).get(key))
                if value is not None and abs(value) >= 0.01:
                    figures.setdefault(str(r["family"]), set()).add(f"{value:.4f}")
    hits = []
    for fid in families:
        items, pending = store.convo(fid)
        text = _dumps([items, pending])
        if _HIDDEN_TEXT.search(text):
            hits.append({"family": fid, "kind": "hidden year"})
        if any(f in text for f in figures.get(fid, ())):
            hits.append({"family": fid, "kind": "hidden figure"})
    return {"families": len(families), "hits": hits, "passed": not hits}


def metrics(store: Any, *, settings: Mapping[str, Any] | None = None, now: float | None = None, draws: int = BOOT_DRAWS,
            seed: int = 0) -> dict[str, Any]:
    """The operator's measurement (the spec's section 7), aggregate only: R1 plumbing, R2 selection carry, R3 out-of-fold
    quality of what each arm would validate, R4 generation gain, R5 flow and cost (the last 24 hours and in all) and R6
    Validation and money per arm. Intervals are family-cluster bootstraps (`draws`, 90% two-sided, seeded). Reads both
    hidden years of every landed look (`_operator_years`): called only by the operator's report, which no agent reads."""
    rng = random.Random(seed)
    now = float(store.clock() if now is None else now)
    rows = _rows(store, confirms=True)
    landed_rows = [r for r in rows if r["status"] == "ok"]
    looks = []
    for r in landed_rows:
        f_sel, f_conf = _operator_years(r)
        looks.append({"seq": int(r["seq"]), "family": str(r["family"]), "arm": r["arm"], "role": r["role"],
                      "generation": int(r["generation"]), "tier": r["tier"], "seen": _num(r["seen_score"]),
                      "seen_f": _num(r["seen_f"]), "sel": f_sel, "conf": f_conf, "at": r["result_at"]})

    # R1: plumbing.
    founders = [x["sel"] - x["conf"] for x in looks if x["generation"] == 0 and x["sel"] is not None and x["conf"] is not None]
    d_mean = _mean(founders)
    d_se = (math.sqrt(sum((d - d_mean) ** 2 for d in founders) / (len(founders) - 1) / len(founders))
            if d_mean is not None and len(founders) >= 2 else None)
    z = d_mean / d_se if d_mean is not None and d_se else None
    submissions = len(rows) + sum(int(r["attempts"]) - 1 for r in rows)
    errors = sum(int(r["errors"]) for r in rows)
    years = [fig for r in landed_rows for fig in (r["years"] or {}).values()]
    ineligible = sum(1 for fig in years if not (fig or {}).get("eligible"))
    r1 = {"leak": _leak_scan(store, rows),
          "d1_founders": {"n": len(founders), "mean": d_mean, "se": d_se, "z": z, "passed": z is None or abs(z) <= 2.5},
          "failure_rate": {"submissions": submissions, "errors": errors,
                           "rate": errors / submissions if submissions else None,
                           "passed": not submissions or errors / submissions < 0.05},
          "ineligible": {"years": len(years), "ineligible": ineligible, "share": ineligible / len(years) if years else None,
                         "flag": bool(years) and ineligible / len(years) > 0.5}}

    # R2: does one hidden year predict the other better than the seen years do (the same looks, both arms).
    both = [x for x in looks if x["sel"] is not None and x["conf"] is not None and x["seen"] is not None]

    def carry(items: list[Mapping[str, Any]]) -> float | None:
        hidden = spearman([x["sel"] for x in items], [x["conf"] for x in items])
        seen = spearman([x["seen"] for x in items], [x["conf"] for x in items])
        return None if hidden is None or seen is None else hidden - seen

    r2 = {"n": len(both), "rho_hidden": spearman([x["sel"] for x in both], [x["conf"] for x in both]),
          "rho_seen": spearman([x["seen"] for x in both], [x["conf"] for x in both]), "delta_rho": carry(both),
          "ci": _cluster_ci(both, carry, draws=draws, rng=rng)}

    # R3: the CONFIRM year of what each arm would send to Validation (game SELECT passers, control's validated versions).
    passers = [x for x in looks if x["arm"] == "game" and x["role"] == "ladder" and x["tier"] == "PASS" and x["conf"] is not None]
    validated = [x for x in looks if x["arm"] == "control" and x["role"] == "validated" and x["conf"] is not None]

    def selection(items: list[Mapping[str, Any]]) -> float | None:
        a = _mean([x["conf"] for x in items if x["arm"] == "game"])
        b = _mean([x["conf"] for x in items if x["arm"] == "control"])
        return None if a is None or b is None else a - b

    def gap(items: list[Mapping[str, Any]]) -> float | None:
        return _mean([x["seen_f"] - x["conf"] for x in items if x["seen_f"] is not None])

    r3 = {"n_game": len(passers), "n_control": len(validated), "delta_sel": selection(passers + validated),
          "ci": _cluster_ci(passers + validated, selection, draws=draws, rng=rng),
          "gap_game": gap(passers), "gap_control": gap(validated)}

    # R4: children against founders on the year no selection read, and the SELECT burn meter.
    game = [x for x in looks if x["arm"] == "game" and x["role"] == "ladder"]

    def gain(key: str) -> Callable[[list[Mapping[str, Any]]], float | None]:
        def stat(items: list[Mapping[str, Any]]) -> float | None:
            kids = _mean([x[key] for x in items if x["generation"] >= 1 and x[key] is not None])
            roots = _mean([x[key] for x in items if x["generation"] == 0 and x[key] is not None])
            return None if kids is None or roots is None else kids - roots
        return stat

    g, g_sel = gain("conf")(game), gain("sel")(game)
    generations = sorted({x["generation"] for x in game})
    r4 = {"G": g, "ci": _cluster_ci(game, gain("conf"), draws=draws, rng=rng), "G_SEL": g_sel,
          "burn": None if g is None or g_sel is None else g_sel - g,
          "by_generation": {str(k): {"n": sum(1 for x in game if x["generation"] == k),
                                     "conf": _mean([x["conf"] for x in game if x["generation"] == k and x["conf"] is not None]),
                                     "sel": _mean([x["sel"] for x in game if x["generation"] == k and x["sel"] is not None])}
                            for k in generations}}

    # R5: flow and cost.
    since = _iso(now - 86400.0)
    children = store._all("SELECT * FROM game_children ORDER BY seq") if _tables(store) else []
    by_seq = {x["seq"]: x for x in looks}
    first_look: dict[str, Mapping[str, Any]] = {}
    for x in looks:
        if x["role"] == "ladder" and x["family"] not in first_look:
            first_look[x["family"]] = x
    parent_of = {str(k["child"]): k for k in children}

    def founder_look(child: str) -> Mapping[str, Any] | None:
        row, hops = parent_of.get(child), 0
        while row is not None and str(row["parent"]) in parent_of and hops < 1000:
            row, hops = parent_of[str(row["parent"])], hops + 1
        return by_seq.get(int(row["parent_look"])) if row is not None and row["parent_look"] is not None else None

    beats = []
    for k in children:
        mine, theirs = first_look.get(str(k["child"])), founder_look(str(k["child"]))
        if mine is not None and theirs is not None and mine["conf"] is not None and theirs["conf"] is not None:
            beats.append(mine["conf"] > theirs["conf"])

    def flow(after: str) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for side in ARMS:
            mine = [r for r in rows if r["arm"] == side and str(r["at"]) >= after]
            out[side] = {"looks": len(mine), "landed": sum(1 for r in mine if r["status"] == "ok"),
                         "select_passes": sum(1 for r in mine if r["tier"] == "PASS"),
                         "confirm_reads": sum(1 for r in mine if r.get("confirm") is not None),
                         "confirmed": sum(1 for r in mine if (r.get("confirm") or {}).get("confirmed"))}
        kids = [k for k in children if str(k["at"]) >= after]
        out["children"] = {"by_op": {op: sum(1 for k in kids if k["op"] == op) for op in OPS},
                           "by_directive": {str(i): sum(1 for k in kids if k["directive"] == i) for i in range(len(DIRECTIVES))}}
        return out

    spend = {str(r["kind"]): float(r["usd"]) for r in store._all("SELECT kind, SUM(usd) AS usd FROM spend WHERE epoch>=? "
                                                                  "GROUP BY kind ORDER BY kind", (now - 86400.0,))}
    r5 = {"day": flow(since), "all": flow(""), "children_beat_founder": {"n": len(beats),
                                                                        "share": sum(beats) / len(beats) if beats else None},
          "hidden_submissions": submissions, "spend_24h": spend}

    # R6: Validation and money per arm (the families the game looked at, or every family with the settings).
    arms: dict[str, str] = {str(r["family"]): r["arm"] for r in rows}
    if settings is not None:
        start = t0(store)
        c = cfg(settings)
        for fam in store.families():
            side = _arm_of(fam, c, start) if c["enabled"] else None
            if side is not None:
                arms[str(fam["id"])] = side
    confirmed_versions = {(str(r["family"]), int(r["version"])) for r in rows if (r.get("confirm") or {}).get("confirmed")}
    score_of = {}
    for r in rows:
        f_sel, f_conf = _operator_years(r) if r["status"] == "ok" else (None, None)
        key = (str(r["family"]), int(r["version"]))
        if r["arm"] == "game" and f_sel is not None and f_conf is not None:
            score_of[key] = f_sel + f_conf
        elif r["arm"] == "control" and _num(r["seen_score"]) is not None:
            score_of.setdefault(key, float(r["seen_score"]))
    r6: dict[str, Any] = {}
    holdout = store.looks()
    for side in ARMS:
        fams = [store.family(fid) for fid, a in sorted(arms.items()) if a == side]
        fams = [f for f in fams if f is not None]
        tried, passed, ts, pairs = 0, 0, [], []
        for fam in fams:
            verdicts = (fam.get("state") or {}).get("validation_verdicts") or {}
            for v in _tried(store, str(fam["id"])):
                if side == "game" and (str(fam["id"]), v) not in confirmed_versions:
                    continue
                tried += 1
                passed += bool((verdicts.get(str(v)) or {}).get("passed"))
                run = store.version_runs(str(fam["id"]), v, window="validation", stress=1.0, limit=1)
                t = _num(((run[0].get("summary") or {}) if run else {}).get("t_daily"))
                if t is not None:
                    ts.append(t)
                    if (str(fam["id"]), v) in score_of:
                        pairs.append((score_of[(str(fam["id"]), v)], t))
        ts.sort()
        names = {str(f["id"]) for f in fams}
        r6[side] = {"families": len(fams), "validation_tries": tried, "validation_passes": passed,
                    "pass_rate": passed / tried if tried else None,
                    "median_t": (ts[len(ts) // 2] if len(ts) % 2 else (ts[len(ts) // 2 - 1] + ts[len(ts) // 2]) / 2.0) if ts else None,
                    "spearman_selection_validation": spearman([a for a, _ in pairs], [b for _, b in pairs]),
                    "holdout_looks": sum(1 for x in holdout if str(x["family"]) in names),
                    "holdout_passes": sum(1 for x in holdout if str(x["family"]) in names and x["passed"]),
                    "probes": sum(1 for f in fams if f.get("band") in ("probe", "sized"))}
    return {"at": _iso(now), "looks": len(rows), "landed": len(landed_rows), "R1": r1, "R2": r2, "R3": r3, "R4": r4, "R5": r5,
            "R6": r6}


__all__ = ["SWITCH_AT", "HIDDEN", "HIDDEN_YEARS", "SEEN_FROM", "CORE", "DEFAULTS", "DIRECTIVES", "GAME_SQL", "Sealed", "cfg",
           "birth_roots", "seen_only", "t0", "fold", "arm", "fitness", "seen_fitness", "tier_of", "ensure", "select_view",
           "confirm_view", "maybe_look", "landed", "requeue_stale", "shadow_validated", "candidate", "validations_left",
           "seen_robust_ok", "look_seen_run", "in_flight", "looks_used", "retire_reason", "parents", "reproduce",
           "visible_families", "visible_graveyard", "quarantined", "status_text", "brief_text", "spearman", "metrics"]
