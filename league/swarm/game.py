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

WHO PLAYS. T0 is the first start with `game.enabled` under the seen span (`t0`, the store's kv `game_t0`, written once
an epoch). `arm` is None (LEGACY: today's rules, no looks) for a family born before T0 or born with a root outside the
core five (`CORE`: only they have 2020-21 data; its BIRTH roots, `spec.roots`, which a later change of roots never moves),
else "game" or "control" by the canary's pure hash split of its LINEAGE (`canary.in_arm`), so a child stays in its
parent's arm. The first arm a family is given is kept (`game_arms`): neither its roots, a setting (`arm_fraction` 1.0 at
GO-WIDE is for new births) nor the game switched off moves it. Half play the game; half keep today's rules on the same
seen years and are measured the same way (their looks are records only): a concurrent comparison, never a before/after
one. Nobody plays while the running Train span shows a hidden year (`seen_only`), and a start under such a span after T0
voids the epoch (`void`): the next start under the seen span with the game on writes a new T0, and every family born
before it, alive across the break, is legacy.

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
fewer than `looks` (4) and has no look of either role in flight, and its program (the version's sha) was never looked at
in its lineage, so a child's unchanged copy of its parent's program never is. The triggers are a STATE, not a moment: a
best that met them while a look was out, or one the family fell back to whose 1.5x run had landed already, is looked at
when the look lands and at each round (`recheck`, from the stored 1.5x run). Control also looks (records only) at every
version the tournament validates that was not looked at already (`shadow_validated`, once a program). A hidden run is
split as the retro split it (`HIDDEN_SPLIT`). A job that fails is queued again after `look_retry_hours` (2), at most
`look_attempts` (3) in all, then the look is recorded failed and does not count against `looks` (`requeue_stale`); a
program the Gym itself ends on the hidden years (disqualified, no data, refused: `PROGRAM_ENDS`) is no failure but a
landed look, both years ineligible.

SELECT, CONFIRM, VALIDATION (game arm, mode "gate"). `landed` scores both years and records the SELECT tier: PASS at F of
at least `c_select` (1.28, one-sided 10% a year), ALIVE from 0, FAIL below 0 or ineligible. On a PASS it reads the
CONFIRM year once, while the family has read fewer than `confirms_family` (2) and its lineage fewer than
`confirms_lineage` (3, as the holdout's looks): CONFIRMED at F of at least `c_confirm` (1.28). A PASS that landed while
the rules were off ("shadow") is read at the first "gate" round under the same budgets (`confirm_waiting`). The family's
candidate for Validation is its latest CONFIRMED version not yet judged (`candidate`), none without one, and it has
`val_tries` (2) Validation tries (`validations_left`: Validations of its CONFIRMED versions, never one it had under
today's rules). The Validation line, the gate, the holdout and Probe sizing are unchanged.

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
(`cards.put`), and one change: MUTATE (the rest) gives it a structural directive,
`DIRECTIVES[ROTATION[(hash(parent) + k) % 12]]` for its k-th sibling, a rotation that favours pricing, structure and
regime filters (structural steps carry to unseen years, parameter tweaks do not: 73% sign agreement for the largest fifth
of steps against about 52%; the planted-edge arena of Oct 8 found pricing, structure and filters carried and input swaps
and exit rewrites broke a half-found edge); CROSSOVER (`crossover_share`, 20%, when a donor exists) shows it another parent-qualified
program of the same fold group and another lineage, at most `donor_max_chars` (6,000), to adopt its execution while it
keeps its own signal.

RETIREMENT (`retire_reason`, before today's rules; Gym band only, `retire_gym`'s floor applies): the family spent its
`looks` without a SELECT PASS; or two of its CONFIRM reads failed; or it used its `val_tries` Validation tries and all
failed. Today's rules still apply after these. The reason it retires with is the same words for all three (`RETIRED`):
it is a public `swarm.retired` cause, and which rule it was would tell a SELECT or CONFIRM outcome; the rule is the
operator's (`retire_rule`, the report's R5).

WHAT AGENTS SEE (`status_text`, `brief_text`, `visible_families`, `visible_graveyard`, `shown_trials`). A game-arm
researcher in "gate" sees one status line on the exam (how many looks it used, never a figure, a tier, a year or a
result) and, a child, its change. The architect and the strategist never see game-arm families (`visible_families`);
every reader's graveyard drops game-arm rows (their reasons reveal SELECT outcomes) and the rows of families born before
T0 and retired since the 2020-21 switch (`SWITCH_AT`: they learned on the hidden years). A family's own views count no
trial of a child the game bore beside it (`shown_trials`): a parent would read in its lineage's trials that it bred.
Once a T0 exists the hiding holds whatever the switch says: the game off (a REVERT, a rollback) releases nothing it hid.
A store that never had a T0 reads exactly the store's own lists.

MODES. "shadow": looks are recorded for both arms and the game-arm rules are off (no CONFIRM read, candidate, Validation
cap, reproduction or retirement). "gate": all of the above. `enabled` false: nothing here acts and every family is legacy.

THE TABLES (`GAME_SQL`), created on first use on the store's own connection (as `cards.CARDS_SQL`), append-only by
trigger, so `store.py` is unchanged: `game_looks` (one row a look), `game_results` (its attempts and its one terminal
row: "ok" with both years' figures and the SELECT tier, "failed" or "cancelled"), `game_confirms` (the one CONFIRM read
of a look), `game_children` and `game_arms` (each playing family's first arm). No module but this one reads them.

THE DIRECTION LANE (release D-1, Oct 9, 2026; PLAN D4, the operator's decision 5; `league/swarm/dlane.py`). A family
whose declared lane is "direction" sits the game out (`_sits_out`): `arm` is None for its lineage, the legacy route,
today's rules with no hidden look, unless `dlane.arm_fraction` (0) admits its lineage to the game's own split. The
alpha lane's game is unchanged (`arm_fraction` 0.5, F = min(t_net, t_alpha), SELECT then CONFIRM). Why, and its cost,
are `_sits_out`'s. A family that was given an arm keeps it (a direction lineage given one while the lane was off keeps
playing the game's own rules). The operator's metrics keep direction looks out of R1(b) and R2 and say what the release
changed mid-way through the T0 experiment (`DIRECTION_NOTES`: the birth quota halves the alpha lane's births; the
researcher's shared role text changed every arm's prompt). While `dlane.mode` is "off" (THE ROLLBACK) every path here is
the release before it's, byte for byte: no lane is read.

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

from . import canary, cards, dlane, evidence
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
#: A start under a span that shows the hidden years after T0 voids the epoch (`void`); the T0s a void ended.
VOID_KEY = "game_void_at"
EPOCHS_KEY = "game_t0_before"
#: The canary key of the arm split (`canary.in_arm(salt, ARM_KEY, lineage, arm_fraction)`) and the fold's salt.
ARM_KEY = "game-v1"
FOLD_SALT = "ltcm-game-v1"
#: THE DIRECTION LANE's own canary key (release D-1): the share `dlane.arm_fraction` of direction lineages that enter the
#: game's split at all (`_sits_out`; 0 by the operator's decision 5, so none does).
DIRECTION_ARM_KEY = "game-v1-direction"
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
#: A hidden run's Train split: 8 per three years of its window, rounded up (8 over 2020-21), as the M0b retro ran it
#: (`settings.BASE_TRAIN_SPLIT`). Left to the pool, the split would follow the span from 2020 (five years: 16).
HIDDEN_SPLIT = settings_mod.BASE_TRAIN_SPLIT * max(1, math.ceil(len(HIDDEN_YEARS) / 3))
#: A delivered result the Gym ended for the PROGRAM (its load refused, a disqualification, no data in its window): the
#: same program ends the same way again, so it is a landed look with both years ineligible, never a retried failure.
PROGRAM_ENDS = ("disqualified", "no_data", "refused")
ORIGIN = "game"
#: The reason a game rule retires a family with, whichever rule it was (the module docstring's RETIREMENT): it becomes a
#: public `swarm.retired` cause. `RULES` are the operator's words for each (`retire_rule`).
RETIRED = "retired under the learning game's rules"
RULES = {1: "spent its {looks} private looks without a pass", 2: "failed its private confirmation twice",
         3: "used its {tries} Validation tries"}
#: The game's one event, a look queued ({family, version, look}), never a figure or a result: kept in the swarm's own table
#: (`hook.SKIPPED_KINDS`), never mirrored to the House's ledger or the site.
EVENT = "swarm.game"
#: The fitness's eligibility: the Train score's own (`evidence.TRAIN_YEAR_MIN_TRADES`, `TRAIN_YEAR_MIN_DAYS`).
MIN_TRADES = evidence.TRAIN_YEAR_MIN_TRADES
MIN_DAYS = evidence.TRAIN_YEAR_MIN_DAYS
#: The family-cluster bootstrap of the operator's metrics (section 7 of the spec): draws and the two-sided level.
BOOT_DRAWS = 2000
BOOT_LEVEL = 0.90
#: R1(b) judges D1 only from this many founder lineages (its SE is over lineages: under it the 2.5 SE bar would fail by
#: chance far more often than its nominal 1.2%), and reads "passed" below it, z still reported.
D1_MIN_LINEAGES = 20

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

#: A MUTATE child's change (the spec's six structural directives, and the structure's shape): its index is
#: `ROTATION[(hash(parent) + k) % len(ROTATION)]` for the k-th sibling. Indices are stable (the report counts by them).
DIRECTIVES = (
    "Replace the signal's market input with another one.",
    "Replace the exit rule (target, stop or time stop): change the rule, not its numbers.",
    "Change how entries and exits are priced (mid vs natural, patience, time in force). When the signal is a move "
    "already under way, try a marketable limit (the natural plus a few cents): a limit fixed at the decision minute's "
    "natural rests and misses the trades that move your way.",
    "Move the holding horizon to another expiry bucket.",
    "Add one regime filter that switches the signal off in a market condition you can name.",
    "Flip the signal's logic (fade instead of follow, or the reverse).",
    "Change the structure's shape (width, strikes against spot, a single leg or a vertical) and keep the signal.",
)
#: The planted-edge arena (Oct 8, scratch/arena-1008/REPORT.md): pricing, structure and a regime filter carried a half-found
#: edge to unseen years (a pricing child took the same signal from Validation t 1.56 to 2.85); a forced input swap or exit
#: rewrite broke it. So those three come round most often and the other three once each in 12.
ROTATION = (2, 4, 6, 2, 3, 4, 2, 6, 0, 4, 1, 5)
CROSSOVER = "Keep your signal; adopt the donor's entry pricing, exits and position management."
CHILD_NOTE = ("Your version 1 is a program that ranked near the top of this game's private exam. Make the change below "
              "before anything else, then improve on your Train years as usual.")
STATUS = ("PRIVATE EXAM: every version that beats your last examined Train score by {eta:g} and makes money at {stress:g}x "
          "is scored on market years you never see, at {stress:g}x and net of its market exposure's drift. Only versions "
          "that pass go to Validation, and passing families have children. You get no figures from it; tune nothing to "
          "it. Looks used: {used} of {looks}; after {looks} without a pass the family retires. Parameter tweaks almost "
          "never survive unseen years; structural changes sometimes do.")
_WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six"}

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
    "CREATE TABLE IF NOT EXISTS game_arms (family TEXT PRIMARY KEY, at TEXT NOT NULL, lineage TEXT NOT NULL, arm TEXT NOT NULL)",
    "CREATE INDEX IF NOT EXISTS game_arms_lineage ON game_arms(lineage)",
    "CREATE TRIGGER IF NOT EXISTS game_arms_no_update BEFORE UPDATE ON game_arms "
    "BEGIN SELECT RAISE(ABORT, 'game arms are append-only'); END",
    "CREATE TRIGGER IF NOT EXISTS game_arms_no_delete BEFORE DELETE ON game_arms "
    "BEGIN SELECT RAISE(ABORT, 'game arms are append-only'); END",
)

#: The hidden runs this process has in the pool, by (store, look): `requeue_stale` never queues one of them again.
_inflight: dict[tuple[str, int], GymJob] = {}
_inflight_lock = threading.Lock()


class Sealed(LookupError):
    """A look's CONFIRM year was asked for without its one-shot read (`confirm_view`)."""


# ----------------------------------------------------------------------------------------------------------- settings
def cfg(settings: Mapping[str, Any] | None) -> dict[str, Any]:
    """`game` in the swarm's settings, each value inside its bounds (a malformed one is its default; a number past a bound
    is the bound, `arm_fraction` 0 included: no new lineage in the game arm). A count that is not a whole number is
    malformed. `roots` keeps only the core five (no other root has the hidden years' data). A malformed `enabled` is off;
    a malformed `mode` is "shadow" (the game-arm rules off)."""
    raw = (settings or {}).get("game")
    raw = raw if isinstance(raw, Mapping) else {}

    def number(key: str, low: float, high: float, *, count: bool = False) -> float:
        value = raw.get(key, DEFAULTS[key])
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) \
                or (count and not float(value).is_integer()):
            value = DEFAULTS[key]
        return float(min(high, max(low, value)))

    def whole(key: str, low: int, high: int) -> int:
        return int(number(key, low, high, count=True))

    roots = raw.get("roots")
    roots = ([str(r).strip().upper() for r in roots if isinstance(r, str) and str(r).strip().upper() in CORE]
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
            "arm_fraction": number("arm_fraction", 0.0, 1.0),
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


def birth_roots(store: Any, settings: Mapping[str, Any] | None) -> list[str] | None:
    """The roots the architect's births may use once the game has started (`started`: the core five, `cfg`'s `roots`),
    else None (its own `gym.roots`, as today, while the game is off or waits for its T0)."""
    return list(cfg(settings)["roots"]) if started(store, settings) else None


def seen_only(store: Any, settings: Mapping[str, Any] | None) -> bool:
    """The running swarm's Train span (its store's migrated objective, `settings.objective_span`) starts on or after the
    seen span's first day: no agent is shown a hidden day. Until a start migrates the span there, no look is made (the
    years would not be hidden)."""
    span = settings_mod.objective_span(store.get("train_objective"))
    return span.isoformat() >= cfg(settings)["seen_from"]


# ----------------------------------------------------------------------------------------------------------- assignment
def t0(store: Any, settings: Mapping[str, Any] | None = None) -> str | None:
    """T0 of the game's current epoch, the store's kv (`T0_KEY`), None before the first. With `settings` that switch the
    game on (the swarm's start under the seen span) it is written when it is missing, and written anew when a void ended
    the last epoch (`void`): every family born before the new T0 is legacy. Without, it is only read (a voided T0 too:
    the quarantine still reads it; `live_t0` is the one the game plays under)."""
    value = store.get(T0_KEY)
    value = value if isinstance(value, str) and value else None
    if settings is None or not cfg(settings)["enabled"] or getattr(store, "readonly", False):
        return value
    if value is not None and not _voided(store, value):
        return value
    with store.atomic():
        value = store.get(T0_KEY)
        value = value if isinstance(value, str) and value else None
        if value is None or _voided(store, value):
            if value is not None:
                store.put(EPOCHS_KEY, [*(store.get(EPOCHS_KEY) or []), {"t0": value, "void_at": store.get(VOID_KEY)}])
                store.put(VOID_KEY, None)
            value = store.now()
            store.put(T0_KEY, value)
    return value


def _voided(store: Any, start: str) -> bool:
    mark = store.get(VOID_KEY)
    return isinstance(mark, str) and bool(mark) and mark >= start


def live_t0(store: Any) -> str | None:
    """The T0 the game plays under: the current epoch's, unless a void ended it (None then, and before the first)."""
    value = t0(store)
    return value if value is not None and not _voided(store, value) else None


def void(store: Any) -> bool:
    """THE VOID: a start after T0 under a Train span that shows the hidden years (a rollback to 2020-24) ends the epoch:
    its families saw a hidden year, so they never play again (the next epoch's T0 is after their birth). Written once
    (kv `VOID_KEY`); True when this call wrote it."""
    value = t0(store)
    if value is None or getattr(store, "readonly", False):
        return False
    with store.atomic():
        if _voided(store, value):
            return False
        store.put(VOID_KEY, store.now())
    return True


def started(store: Any, settings: Mapping[str, Any] | None) -> bool:
    """The game is on and playing: `enabled`, a live T0, and the running Train span is the seen span. Births on the core
    five, the strategist's "years" rule and the input card's span follow this, not the switch alone, so a deploy that
    waits for its T0 changes nothing."""
    return cfg(settings)["enabled"] and live_t0(store) is not None and seen_only(store, settings)


def fold(lineage: Any) -> tuple[int, int]:
    """(select year, confirm year) of a lineage: 2020 first when the first byte of sha256("ltcm-game-v1\\0" + lineage)
    is even, else 2021 first. Every member of a lineage has the same pair."""
    digest = hashlib.sha256(f"{FOLD_SALT}\0{lineage}".encode("utf-8")).digest()
    first, second = HIDDEN_YEARS
    return (first, second) if digest[0] % 2 == 0 else (second, first)


def arm(store: Any, fam: Mapping[str, Any] | None, settings: Mapping[str, Any] | None) -> str | None:
    """"game", "control", or None (legacy: the game off, no live T0, a span that shows the hidden years, born before T0,
    or born with a root outside the core five). The first arm a family is given is kept (`game_arms`)."""
    c = cfg(settings)
    if not c["enabled"] or not isinstance(fam, Mapping):
        return None
    start = live_t0(store)
    if start is None or not seen_only(store, settings):
        return None
    return _arm(store, fam, c, start, settings)


def _arm(store: Any, fam: Mapping[str, Any], c: Mapping[str, Any], start: str,
         settings: Mapping[str, Any] | None = None) -> str | None:
    """The family's arm under the live T0 `start`, kept the first time it is given. A direction lineage that sits the
    game out (`_sits_out`, read from `settings`) is legacy: None, and nothing is kept."""
    fid = str(fam.get("id") or "")
    born = str(fam.get("born_at") or "")
    if not born or born < start:
        return None
    lineage = str(fam.get("lineage") or fid)
    registry = _registry(store, fid, lineage)
    side = _arm_of(fam, c, start, registry, sits_out=lambda: _sits_out(store, fam, settings, c))
    if side is not None and fid not in registry[0]:
        _register(store, [(fid, lineage, side)])
    return side


def _arm_of(fam: Mapping[str, Any], c: Mapping[str, Any], start: str | None,
            registry: tuple[Mapping[str, str], Mapping[str, str]] | None = None, *,
            sits_out: Callable[[], bool] | None = None) -> str | None:
    """The arm of a family under `start` (a pure read of the family, the settings and `registry`, the kept arms by family
    and by lineage): its kept arm, else its lineage's, else None when `sits_out` says it is a direction lineage that
    sits the game out (asked last, so a family with a kept arm, or a root outside the core five, reads nothing for it),
    else the hash's."""
    if start is None:
        return None
    born = str(fam.get("born_at") or "")
    if not born or born < start:
        return None
    fid = str(fam.get("id") or "")
    by_family, by_lineage = registry or ({}, {})
    if fid in by_family:
        return by_family[fid]
    core = set(c["roots"])
    roots = _birth_roots(fam)
    if not roots or any(r not in core for r in roots):
        return None
    unit = str(fam.get("lineage") or fid)
    if unit in by_lineage:
        return by_lineage[unit]
    if sits_out is not None and sits_out():
        return None
    return "game" if canary.in_arm(c["salt"], ARM_KEY, unit, c["arm_fraction"]) else "control"


def _sits_out(store: Any, fam: Mapping[str, Any], settings: Mapping[str, Any] | None, c: Mapping[str, Any]) -> bool:
    """THE DIRECTION LANE SITS THE GAME OUT (release D-1, Oct 9, 2026; PLAN D4, the operator's decision 5): a family
    whose declared lane is "direction" (`dlane.lane_of`: its spec's `lane`, else its card's) is legacy, today's rules
    with no hidden look, unless its LINEAGE falls in the share `dlane.arm_fraction` of direction lineages that enter the
    game's own split (`DIRECTION_ARM_KEY`; 0, so none does). Why: in the operator's measurement the hidden look cost the
    lane most of its power to buy a false-positive rate that was already small, and F = min(t_net, t_alpha) scores an
    always-long program at about zero by construction (t_alpha is about zero for it). Its cost: the game's selection
    pressure is lost for direction, and the lane's screen is the gate's (`dlane.screen_effective`). A direction lineage a
    non-zero share admits plays the game's own rules (the alpha fitness): the direction ladder is deferred. While the
    lane is off nothing sits out (`dlane.lane_of` reads "alpha" with no store read): THE ROLLBACK, byte for byte. Never
    raises (an unreadable lane is alpha's)."""
    if not dlane.on(settings):
        return False
    spec = fam.get("spec")
    spec = _loads(spec, {}) if isinstance(spec, str) else spec
    try:
        lane = dlane.lane_of(store, {**dict(fam), "spec": spec if isinstance(spec, Mapping) else {}}, settings)
    except Exception:  # noqa: BLE001 - an unreadable lane is alpha's
        return False
    if lane != dlane.DIRECTION:
        return False
    unit = str(fam.get("lineage") or fam.get("id") or "")
    return not canary.in_arm(c["salt"], DIRECTION_ARM_KEY, unit, dlane.cfg(settings)["arm_fraction"])


def _birth_roots(fam: Mapping[str, Any]) -> list[str]:
    """The roots a family was born with (`spec.roots`, which `add_family` writes and a change of roots never moves), else
    its roots."""
    spec = fam.get("spec")
    spec = _loads(spec, {}) if isinstance(spec, str) else spec
    roots = spec.get("roots") if isinstance(spec, Mapping) else None
    if not isinstance(roots, (list, tuple)) or not roots:
        roots = fam.get("roots")
        roots = _loads(roots, []) if isinstance(roots, str) else roots
    return [str(r).upper() for r in roots] if isinstance(roots, (list, tuple)) else []


def _registry(store: Any, fid: str | None = None, lineage: str | None = None) -> tuple[dict[str, str], dict[str, str]]:
    """The kept arms ({family: arm}, {lineage: arm}): every one, or those of `fid` and its `lineage`."""
    if not _tables(store):
        return {}, {}
    rows = (store._all("SELECT family, lineage, arm FROM game_arms WHERE family=? OR lineage=? ORDER BY at, family",
                       (fid, lineage)) if fid is not None else
            store._all("SELECT family, lineage, arm FROM game_arms ORDER BY at, family"))
    by_family = {str(r["family"]): str(r["arm"]) for r in rows}
    by_lineage: dict[str, str] = {}
    for r in rows:
        by_lineage.setdefault(str(r["lineage"]), str(r["arm"]))
    return by_family, by_lineage


def _register(store: Any, rows: Sequence[tuple[str, str, str]]) -> None:
    """Keep each (family, lineage, arm) given for the first time (a read-only store keeps nothing)."""
    if not rows or not ensure(store):
        return
    with store.atomic():
        for fid, lineage, side in rows:
            store._exec("INSERT OR IGNORE INTO game_arms(family, at, lineage, arm) VALUES(?,?,?,?)",
                        (str(fid), store.now(), str(lineage), str(side)))


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
        out["why"] = (f"the Gym ended the program: {result['status']}" if isinstance(result, Mapping)
                      and result.get("status") in PROGRAM_ENDS else "the run did not complete")
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


def _rows(store: Any, where: str = "1=1", args: Sequence[Any] = (), *, confirms: bool = False,
          operator: bool = False) -> list[dict[str, Any]]:
    """The game's looks (`where` over `game_looks`), oldest first, each with what its results say: `status` (its terminal
    row's, else "queued": in flight or waiting for its retry), `tier`, `years` (an "ok" row's SELECT year's figures, read
    through `select_view`; both years' only for the OPERATOR's read, `operator`, which `metrics` alone asks for, through
    `_operator_years`), `result_at`, `attempts` (its submissions), `errors` and `last_at` (its newest row, or the look
    itself). With `confirms`, `confirm` (its one CONFIRM read or None); without it the confirm table is never read and
    `confirm_view` refuses the row. No decision ever holds a CONFIRM year's figure but through `confirm_view`."""
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
        years = _loads(final["years_json"], {}) if final and final["status"] == "ok" else None
        if isinstance(years, dict) and not operator:
            years = {k: v for k, v in years.items() if k == str(look["select_year"])}
        row.update(status=final["status"] if final else "queued", tier=final.get("tier") if final else None, years=years,
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
    """A look at this program (the version's sha) in the lineage, of either role and whatever its end but "cancelled" (its
    family retired): a program is looked at once. A look that failed bars it too, or the round's `recheck` and control's
    `shadow_validated` would open one after another for as long as the program stays the family's."""
    return any(r["status"] != "cancelled" for r in _rows(store, "lineage=? AND sha=?", (lineage, sha)))


# ----------------------------------------------------------------------------------------------------------- looks
def maybe_look(researcher: Any, fid: str, n: int, seen_result: Mapping[str, Any]) -> dict[str, Any] | None:
    """THE LADDER (the module docstring), called on the pool's dispatcher thread after version `n`'s 1.5x seen run landed
    with a profit and was not demoted (`researcher.robust_landed`). Opens the look and queues its hidden run when every
    trigger holds: {"look": seq} then, {"look": None, "why": ...} when the family plays but one does not, None when it
    does not play. Never raises."""
    try:
        settings = getattr(researcher, "settings", None) or {}
        return _ladder(researcher.store, settings, getattr(researcher, "pool", None), str(fid), int(n), seen_result,
                       lambda: getattr(researcher, "settings", None) or settings)
    except Exception:  # noqa: BLE001 - on the dispatcher's thread: the game never breaks the pool
        return None


def _ladder(store: Any, settings: Mapping[str, Any], pool: Any, fid: str, n: int, seen_result: Mapping[str, Any] | None,
            settings_of: Callable[[], Mapping[str, Any] | None]) -> dict[str, Any] | None:
    """The ladder's triggers for version `n` of family `fid` and, when every one holds, its look (`maybe_look` with the
    1.5x run that just landed, `recheck` with the stored one)."""
    c = cfg(settings)
    if not c["enabled"]:
        return None
    fam = store.family(fid)
    start = live_t0(store)
    side = _arm(store, fam, c, start, settings) if fam is not None and not fam.get("retired_at") and start is not None else None
    if side is None:
        return None
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
    version = store.version(fid, n) if why is None else None
    if why is None and (version is None or not version.get("code")):
        why = "its program is not kept"
    if why is not None:
        return {"look": None, "why": why}
    seq = None
    with store.atomic():
        ensure(store)
        fam = store.family(fid) or fam
        rows = _rows(store, "family=?", (fid,))
        used = [r for r in rows if r["role"] == "ladder" and r["status"] not in ("failed", "cancelled")]
        score = float(fam["best_train"])
        best = (fam.get("state") or {}).get("best_train_version")
        if fam.get("retired_at"):
            why = "the family retired"
        elif best is None or int(best) != n:
            why = "not the family's best by Train score"
        elif any(r["status"] not in TERMINAL for r in rows):
            why = "a look is in flight"  # of either role: control's record of a validated version too
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
    _submit(store, pool, seq, fam, version, c, settings_of)  # type: ignore[arg-type]
    store.event(EVENT, fid, {"family": fid, "version": n, "look": "queued"})
    return {"look": seq}


def _submit(store: Any, pool: Any, look_seq: int, fam: Mapping[str, Any], version: Mapping[str, Any], c: Mapping[str, Any],
            settings_of: Callable[[], Mapping[str, Any] | None]) -> GymJob | None:
    """Queue a look's hidden run: one Train job over the hidden window at `stress`, purpose "private", split as the retro
    split it (`HIDDEN_SPLIT`), its result to `landed` and its failure to the look's attempts (both on the dispatcher's
    thread, never raising)."""
    from .researcher import needs_roots  # a local import: the researcher calls this module

    code = str(version.get("code") or "")
    job = GymJob(family=str(fam["id"]), version=int(version["n"]), code=code, params=dict(version.get("params") or {}),
                 window="train", roots=tuple(needs_roots(code, fam.get("roots") or ())), stress=float(c["stress"]),
                 purpose=PURPOSE, start=c["hidden"][0], end=c["hidden"][1], priority=PRIVATE_PRIORITY, split=HIDDEN_SPLIT)
    key = (str(getattr(store, "path", id(store))), int(look_seq))
    job.late = lambda result: _deliver(store, look_seq, result, settings_of, pool)
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


def _deliver(store: Any, look_seq: int, result: Mapping[str, Any], settings_of: Callable[[], Mapping[str, Any] | None],
             pool: Any = None) -> None:
    """A hidden run's result: `landed`, then the ladder's state for its family (`recheck`: a best that met the triggers
    while this look was out is looked at now)."""
    try:
        settings = settings_of()
        out = landed(store, look_seq, result, settings)
        if pool is not None and (out or {}).get("status") == "ok":
            row = store._one("SELECT family FROM game_looks WHERE seq=?", (int(look_seq),))
            if row is not None:
                recheck(store, settings, pool, family=str(row["family"]))
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
    """A look's hidden run came back: both years scored (`fitness`) and recorded with the SELECT tier. A result the Gym
    ended for the program (`PROGRAM_ENDS`) lands too, both years ineligible; any other that is not "ok" is a failed
    attempt (`requeue_stale` queues it again). In mode "gate", a game-arm look's SELECT PASS reads the CONFIRM year once
    (`_confirm`) while its family plays in the game arm and is alive. Idempotent: a look that has its terminal row is left
    as it is. Returns {status, tier, confirmed} (None for no such look)."""
    c = cfg(settings)
    ensure(store)
    with store.atomic():
        look = store._one("SELECT * FROM game_looks WHERE seq=?", (int(look_seq),))
        if look is None:
            return None
        if store._one("SELECT 1 AS done FROM game_results WHERE look_seq=? AND status IN ('ok','failed','cancelled')",
                      (int(look_seq),)):
            return {"status": "done", "tier": None, "confirmed": None}
        status = result.get("status") if isinstance(result, Mapping) else None
        if status != "ok" and status not in PROGRAM_ENDS:
            reason = (result or {}).get("reason") if isinstance(result, Mapping) else None
            _result(store, look_seq, "error", {"why": f"{status}: {str(reason or '')[:200]}"})
            return {"status": "error", "tier": None, "confirmed": None}
        select = int(look["select_year"])
        other = next(y for y in HIDDEN_YEARS if y != select)
        years = {str(y): fitness(result, y) for y in (select, other)}
        stored = {y: {**v, "F": v["F"] if math.isfinite(v["F"]) else None} for y, v in years.items()}
        tier = tier_of(stored[str(select)]["F"], c["c_select"])
        _result(store, look_seq, "ok", stored, tier)
        confirmed = None
        if c["mode"] == "gate" and look["arm"] == "game" and tier == "PASS":
            fam = store.family(str(look["family"])) or {}
            if fam and not fam.get("retired_at") and arm(store, fam, settings) == "game":
                confirmed = _confirm(store, look, stored[str(other)], c)
    return {"status": "ok", "tier": tier, "confirmed": confirmed}


def _confirm(store: Any, look: Mapping[str, Any], figures: Mapping[str, Any], c: Mapping[str, Any]) -> bool | None:
    """THE ONE-SHOT READ of a SELECT PASS's CONFIRM year (`figures`, inside the caller's transaction): written to
    `game_confirms` while the look's family has read fewer than `confirms_family` and its lineage fewer than
    `confirms_lineage`. Whether it CONFIRMED, None when the budgets left no read."""
    family_reads = store._one("SELECT COUNT(*) AS n FROM game_confirms k JOIN game_looks l ON l.seq=k.look_seq "
                              "WHERE l.family=?", (look["family"],))["n"]
    lineage_reads = store._one("SELECT COUNT(*) AS n FROM game_confirms k JOIN game_looks l ON l.seq=k.look_seq "
                               "WHERE l.lineage=?", (look["lineage"],))["n"]
    if int(family_reads) >= c["confirms_family"] or int(lineage_reads) >= c["confirms_lineage"]:
        return None
    f = _num(figures.get("F"))
    confirmed = bool(figures.get("eligible")) and f is not None and f >= c["c_confirm"]
    store._exec("INSERT INTO game_confirms(look_seq, at, f_confirm, confirmed) VALUES(?,?,?,?)",
                (int(look["seq"]), store.now(), f, 1 if confirmed else 0))
    return confirmed


def confirm_waiting(store: Any, settings: Mapping[str, Any] | None) -> list[int]:
    """THE ONE-SHOT READ, caught up (mode "gate", each round before Validation): a game-arm SELECT PASS with no read (it
    landed while the rules were off, in "shadow") is read now, oldest first, under the same budgets, while its family is
    alive and plays in the game arm. A PASS the budgets refused at its landing stays unread (they only grow). The looks
    read."""
    c = cfg(settings)
    if c["mode"] != "gate" or not started(store, settings) or not _tables(store):
        return []
    read = []
    for p in store._all("SELECT l.seq, l.family FROM game_looks l JOIN game_results r ON r.look_seq=l.seq "
                        "WHERE l.arm='game' AND l.role='ladder' AND r.status='ok' AND r.tier='PASS' "
                        "AND l.seq NOT IN (SELECT look_seq FROM game_confirms) ORDER BY l.seq"):
        with store.atomic():
            fam = store.family(str(p["family"]))
            if fam is None or fam.get("retired_at") or arm(store, fam, settings) != "game":
                continue
            look = store._one("SELECT * FROM game_looks WHERE seq=?", (int(p["seq"]),))
            final = store._one("SELECT years_json FROM game_results WHERE look_seq=? AND status='ok'", (int(p["seq"]),))
            other = str(next(y for y in HIDDEN_YEARS if y != int(look["select_year"])))  # type: ignore[index]
            figures = (_loads((final or {}).get("years_json"), {}) or {}).get(other) or {}
            if _confirm(store, look, figures, c) is not None:  # type: ignore[arg-type]
                read.append(int(p["seq"]))
    return read


def _open(store: Any) -> list[dict[str, Any]]:
    """The looks that have not landed (queued, out, or waiting for a retry)."""
    return _rows(store, "seq NOT IN (SELECT look_seq FROM game_results WHERE status IN ('ok','failed','cancelled'))")


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
    for row in _open(store):
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


def recheck(store: Any, settings: Mapping[str, Any] | None, pool: Any, clock: Callable[[], float] | None = None, *,
            family: str | None = None) -> list[int]:
    """THE LADDER'S STATE (the module docstring): each living family that plays and has no look out (or `family` alone,
    as its look lands) whose best by Train score has a stored, profitable 1.5x seen run under the running span and the
    Gym in force, and was not demoted, is asked the ladder's triggers with that run (`_ladder`). A best that met them
    while a look was out, or one the family fell back to whose 1.5x run had landed before, is looked at so. The
    tournament's round calls it after Validation; `_deliver` as a look lands. The looks opened."""
    c = cfg(settings)
    if not started(store, settings) or not _tables(store):
        return []
    from .evaluator import KEY, row_matches

    span = settings_mod.objective_span(store.get("train_objective")).isoformat()
    current = store.get(KEY)
    busy = {str(r["family"]) for r in _open(store)}
    opened = []
    for fam in ([store.family(family)] if family is not None else store.families(alive=True)):
        if fam is None or fam.get("retired_at") or str(fam["id"]) in busy:
            continue
        state = fam.get("state") or {}
        n = state.get("best_train_version")
        if not isinstance(n, int) or isinstance(n, bool) or n in (state.get("robust_failed") or []) \
                or arm(store, fam, settings) is None:
            continue
        version = store.version(str(fam["id"]), n)
        if version is None or not version.get("code") or _sha_looked(store, str(fam["lineage"]), str(version["sha"])):
            continue
        seen = None
        for row in store.version_runs(str(fam["id"]), n, window="train", stress=c["stress"], limit=20):
            s = row.get("summary") or {}
            if row.get("status") == "ok" and str(s.get("train_from") or settings_mod.TRAIN_CORE_START.isoformat()) == span \
                    and (current is None or row_matches(store, row, current)):
                seen = {"status": "ok", "summary": s, "drift": s.get("drift")}
                break
        if seen is None or not (_num(seen["summary"].get("pnl")) or 0.0) > 0:
            continue
        out = _ladder(store, settings or {}, pool, str(fam["id"]), n, seen, lambda s=settings: s)
        if (out or {}).get("look"):
            opened.append(int(out["look"]))  # type: ignore[index]
    return opened


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
    """CONTROL'S EXTRA LOOKS (records only): every version of a living control-arm family the tournament validated (a
    stress-1.0 `validation` row, its own or an inherited verdict's; not only its latest) whose program its lineage never
    looked at gets a look ("validated": it counts against nothing), once a program whatever that look's end, one a family
    at a time and none while a look of the family is out (the next round takes the rest). The tournament's round calls it
    after Validation. The looks opened."""
    c = cfg(settings)
    start = live_t0(store)
    if not c["enabled"] or start is None or not seen_only(store, settings):
        return []
    ensure(store)
    busy = {str(r["family"]) for r in _open(store)}
    opened = []
    for row in store._all("SELECT DISTINCT r.family, r.version FROM runs r JOIN families f ON f.id=r.family "
                          "WHERE r.window='validation' AND r.stress=1.0 AND r.version IS NOT NULL AND f.retired_at IS NULL "
                          "AND f.born_at>=? ORDER BY r.family, r.version", (start,)):
        fid, n = str(row["family"]), int(row["version"])
        if fid in busy:
            continue
        fam = store.family(fid)
        if fam is None or arm(store, fam, settings) != "control":
            continue
        version = store.version(fid, n)
        if version is None or not version.get("code") or _sha_looked(store, str(fam["lineage"]), str(version["sha"])):
            continue  # read first: the run rows below are parsed only for a program not looked at
        score, run, seen = _seen_of(store, fam, n, c)
        with store.atomic():
            if _sha_looked(store, str(fam["lineage"]), str(version["sha"])) \
                    or any(r["status"] not in TERMINAL for r in _rows(store, "family=?", (fid,))):
                continue
            seq = _record_look(store, fam, "control", "validated", version, c, seen_score=score, seen_run=run, seen_f=seen)
        busy.add(fid)
        _submit(store, pool, seq, fam, version, c, lambda s=settings: s)
        store.event(EVENT, fid, {"family": fid, "version": n, "look": "queued"})
        opened.append(seq)
    return opened


# ----------------------------------------------------------------------------------------------------------- decisions
def _fid(fam: Any) -> str:
    return str(fam["id"]) if isinstance(fam, Mapping) else str(fam)


def _confirmed(store: Any, fid: str) -> list[int]:
    """The family's CONFIRMED versions, in the order of their CONFIRM reads."""
    return [int(r["version"]) for r in sorted(_rows(store, "family=?", (fid,), confirms=True),
                                              key=lambda r: (r.get("confirm") or {}).get("seq") or 0)
            if r.get("confirm") is not None and confirm_view(r)["confirmed"]]


def candidate(store: Any, fam: Any) -> int | None:
    """The game-arm family's version for Validation (mode "gate"): its latest CONFIRMED version the tournament has not
    judged yet (no verdict in its state's `validation_verdicts`), else its latest CONFIRMED version (judged, so
    `Tournament.validate` skips it unless the Gym changed, and `judge`'s stale check holds while a Validation is out), or
    None without one."""
    from .researcher import VERDICTS_KEY  # a local import: the researcher calls this module

    confirmed = _confirmed(store, _fid(fam))
    if not confirmed:
        return None
    row = fam if isinstance(fam, Mapping) else (store.family(_fid(fam)) or {})
    verdicts = (row.get("state") or {}).get(VERDICTS_KEY)
    verdicts = verdicts if isinstance(verdicts, Mapping) else {}
    waiting = [v for v in confirmed if str(v) not in verdicts]
    return (waiting or confirmed)[-1]


def _validated(store: Any, fid: str) -> list[int]:
    """The versions of a family that have had a Validation run (its own or an inherited verdict's rows)."""
    return [int(r["version"]) for r in store._all("SELECT DISTINCT version FROM runs WHERE family=? AND window='validation' "
                                                  "AND stress=1.0 AND version IS NOT NULL ORDER BY version", (fid,))]


def _tried(store: Any, fid: str) -> list[int]:
    """The game's Validation tries of a family: its CONFIRMED versions that have had a Validation run. A version validated
    under today's rules (mode "shadow", before a switch to "gate") is no try."""
    confirmed = set(_confirmed(store, fid))
    return [v for v in _validated(store, fid) if v in confirmed] if confirmed else []


def validations_left(store: Any, fam: Any, settings: Mapping[str, Any] | None) -> int:
    """Validation tries a game-arm family has left: `val_tries` less its tries (`_tried`), never below 0."""
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
    """The game's reason to retire a living game-arm Gym family in mode "gate" (the module docstring), else None:
    `RETIRED`, the same words whichever rule it was (`retire_rule`): the reason is a public `swarm.retired` cause."""
    return RETIRED if retire_rule(store, fam, settings) is not None else None


def retire_rule(store: Any, fam: Mapping[str, Any], settings: Mapping[str, Any] | None) -> tuple[int, str] | None:
    """(rule, the operator's words) of the game's retirement rule a living game-arm Gym family in mode "gate" meets, else
    None: 1, its looks spent without a SELECT PASS (all landed); 2, two failed CONFIRM reads (or every read its family may
    have, `confirms_family`, when that is fewer); 3, its Validation tries used and every one failed (the tournament's own
    verdicts, `validation_verdicts`). Never a figure, a tier or a year in the words."""
    c = cfg(settings)
    if c["mode"] != "gate" or not isinstance(fam, Mapping) or fam.get("retired_at"):
        return None
    if (fam.get("band") or "gym") != "gym" or arm(store, fam, settings) != "game" or not _tables(store):
        return None
    return _rule(store, fam, c)


def _rule(store: Any, fam: Mapping[str, Any], c: Mapping[str, Any]) -> tuple[int, str] | None:
    """`retire_rule`'s three rules on the family's looks, reads and verdicts alone (the report reads them for a retired
    family too)."""
    rows = _rows(store, "family=?", (str(fam["id"]),), confirms=True)
    ladder = [r for r in rows if r["role"] == "ladder" and r["status"] not in ("failed", "cancelled")]
    if len(ladder) >= c["looks"] and all(r["status"] == "ok" for r in ladder) \
            and not any((select_view(r) or {}).get("tier") == "PASS" for r in ladder):
        return 1, RULES[1].format(looks=_WORDS.get(c["looks"], str(c["looks"])))
    failed = sum(1 for r in rows if r.get("confirm") is not None and not confirm_view(r)["confirmed"])
    if failed >= min(2, c["confirms_family"]):
        return 2, RULES[2]
    tried = _tried(store, str(fam["id"]))
    verdicts = (fam.get("state") or {}).get("validation_verdicts") or {}
    if len(tried) >= c["val_tries"] and all(isinstance(verdicts.get(str(v)), Mapping) and verdicts[str(v)].get("passed") is False
                                            for v in tried):
        return 3, RULES[3].format(tries=_WORDS.get(c["val_tries"], str(c["val_tries"])))
    return None


def parents(store: Any, settings: Mapping[str, Any] | None, clock: Callable[[], float] | None = None) -> list[dict[str, Any]]:
    """The game-arm families that may breed now, best first: {family, look, version, lineage, select_year, F} for each
    one's best qualifying look (the module docstring's REPRODUCTION). Reads the SELECT year only (`select_view`), and never
    the confirm table."""
    c = cfg(settings)
    start = live_t0(store)
    if start is None or not _tables(store):
        return []
    now = float((clock or store.clock)())
    since = max(_iso(now - c["parent_window_hours"] * 3600.0), start)  # a look of an epoch a void ended is no parent's
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
    if c["mode"] != "gate" or not started(store, settings):
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
    # Its roots are its parent's birth roots (the core five's: a later change of the parent's roots is no child's).
    spec.update(id=f"g-{_seed(fid, version['n'], k, store.now()):016x}"[:10], mechanism=fam["mechanism"],
                structure=fam["structure"], roots=_birth_roots(fam) or list(fam["roots"]))
    directive = donor = None
    if op == "mutate":
        directive = ROTATION[(_seed(fid) + k) % len(ROTATION)]
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
    _register(store, [(str(child["id"]), str(child["lineage"]), "game")])  # its parent's arm, kept from its birth
    # No `swarm.born` event: the site's tape, the births' quota (`allocation.BirthQuota`) and the funnel read those, and a
    # child's birth tells that its parent passed a private look. The game's own table is its record.
    return str(child["id"])


# ----------------------------------------------------------------------------------------------------------- visibility
def _hidden(store: Any, settings: Mapping[str, Any] | None) -> tuple[str | None, frozenset[str]]:
    """(the current T0, the families that play or played in the game arm): the kept arms, and while the game is playing
    (`started`) every family born since T0 that has no kept arm yet is given its arm now (and kept). None and nothing for a
    store that never had a T0. Whatever the switch says once a T0 exists: the game off keeps what it hid hidden."""
    start = t0(store)
    if start is None:
        return None, frozenset()
    by_family, by_lineage = _registry(store)
    ids = {fid for fid, side in by_family.items() if side == "game"}
    live = live_t0(store)
    if started(store, settings) and live is not None:
        c, fresh = cfg(settings), []
        for f in store._all("SELECT id, lineage, born_at, roots, spec FROM families WHERE born_at>=? ORDER BY born_at, id",
                            (live,)):
            if str(f["id"]) in by_family:
                continue
            side = _arm_of(f, c, live, (by_family, by_lineage), sits_out=lambda f=f: _sits_out(store, f, settings, c))
            if side is None:
                continue
            fresh.append((str(f["id"]), str(f["lineage"]), side))
            by_lineage.setdefault(str(f["lineage"]), side)
            if side == "game":
                ids.add(str(f["id"]))
        _register(store, fresh)
    return start, frozenset(ids)


def _learners(store: Any, start: str) -> frozenset[str]:
    """The families born before T0 and retired since `SWITCH_AT`: they learned on the hidden years."""
    return frozenset(str(r["id"]) for r in store._all("SELECT id FROM families WHERE born_at<? AND retired_at IS NOT NULL "
                                                      "AND retired_at>=?", (start, SWITCH_AT)))


def visible_families(store: Any, *, alive: bool | None = None, settings: Mapping[str, Any] | None,
                     learners: bool = False) -> list[dict[str, Any]]:
    """`store.families(alive=...)` less the game arm's, alive or retired (`_hidden`), and less the dead families that
    learned on the hidden years (the quarantine's (a), `_learners`): the architect's and the strategist's content reads.
    `learners` keeps those (`Architect.admit`'s lineage accounting: a birth on their slice still counts their trials). A
    store that never had a T0: exactly the store's list."""
    fams = store.families(alive=alive)
    start, played = _hidden(store, settings)
    if start is None:
        return fams
    learned = frozenset() if learners or alive else _learners(store, start)
    return [f for f in fams if f["id"] not in played and f["id"] not in learned]


def visible_graveyard(store: Any, query: str = "", limit: int = 8, *, settings: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    """`store.graveyard(query, limit=...)` for every reader (the researchers' tool, the architect, the strategist) less two
    kinds of row, ranked over the rows that are left: a family born before T0 and retired since `SWITCH_AT` (it learned
    on the hidden years), and a game-arm family (its reasons and notes tell its SELECT outcomes). A store that never had a
    T0: exactly the store's read."""
    start, played = _hidden(store, settings)
    if start is None:
        return store.graveyard(query, limit=limit)
    from .store import rank_graveyard

    rows = store._all("SELECT g.*, f.born_at AS _born, f.retired_at AS _retired, f.id AS _id FROM graveyard g "
                      "LEFT JOIN families f ON f.id=g.family ORDER BY g.at DESC, g.family")
    kept = [r for r in rows if not _quarantined(r, start, played)]
    out = []
    for r in rank_graveyard(kept, query)[:limit]:
        r["roots"] = _loads(r["roots"], [])
        r["best"] = _loads(r["best"], {})
        out.append(r)
    return out


def _quarantined(row: dict[str, Any], start: str, played: frozenset[str]) -> bool:
    """Whether a graveyard row joined with its family's columns (`_born`, `_retired`, `_id`, which this pops) is one no
    reader sees: (a) its family was born before T0 and retired since `SWITCH_AT` (it learned on the hidden years), or (b)
    its family plays or played in the game arm (its lesson tells its SELECT outcomes)."""
    fid, born, retired = row.pop("_id"), row.pop("_born"), row.pop("_retired")
    if fid is None:
        return False
    if str(born or "") < start and str(retired or row["at"]) >= SWITCH_AT:
        return True
    return str(fid) in played


def quarantined(store: Any, settings: Mapping[str, Any] | None) -> frozenset[str]:
    """The families whose graveyard rows `visible_graveyard` drops, for a reader that reads the table itself (the rebirth
    index, `cards.RebirthIndex`; the architect's and the strategist's own SQL): empty for a store that never had a T0."""
    start, played = _hidden(store, settings)
    if start is None:
        return frozenset()
    rows = store._all("SELECT g.family, g.at, f.born_at AS _born, f.retired_at AS _retired, f.id AS _id FROM graveyard g "
                      "LEFT JOIN families f ON f.id=g.family")
    return frozenset(str(r["family"]) for r in rows if _quarantined(r, start, played))


def visible_shares(store: Any, board: Sequence[Any], ids: Any) -> dict[str, Any]:
    """The research shares of the leaderboard's rows for the families `ids` (those a reader may read), as the architect and
    the strategist show them: once a T0 exists, renormalized over those rows to 4 places. The allocation's shares sum to
    one over every family, the game arm's included, so each child the game bore would dilute every visible share and say
    that some look was in its SELECT year's top decile. A store that never had a T0: the board's own shares."""
    wanted = set(ids)
    shares = {r["family"]: r.get("share") for r in board if isinstance(r, Mapping) and r.get("family") in wanted}
    if t0(store) is None:
        return shares
    total = math.fsum(float(v) for v in shares.values() if _num(v) is not None)
    if total <= 0:
        return shares
    return {fid: round(float(v) / total, 4) if _num(v) is not None else v for fid, v in shares.items()}


def unrelated_children(store: Any, fam: Any) -> frozenset[str]:
    """The game's children a family's own views must not count: every child the game bore that is neither the family
    itself nor one of its game ancestors. A parent would read in its lineage's trials or its hypothesis's record that it
    bred (that a look of it was in the SELECT year's top decile), a child that its parent bred again."""
    if not _tables(store):
        return frozenset()
    parent_of = {str(r["child"]): str(r["parent"]) for r in store._all("SELECT child, parent FROM game_children")}
    if not parent_of:
        return frozenset()
    keep, cur = {_fid(fam)}, _fid(fam)
    while cur in parent_of and parent_of[cur] not in keep:
        cur = parent_of[cur]
        keep.add(cur)
    return frozenset(child for child in parent_of if child not in keep)


def shown_trials(store: Any, fam: Any) -> int:
    """The lineage's trials as the family's own views show them (its status, its run views, its sweep table, its
    allocation row): `store.lineage_trials` less every trial of a child the game bore beside it (`unrelated_children`).
    The gate and Validation keep the full count. Exactly `store.lineage_trials` for a family with no such child."""
    fid = _fid(fam)
    full = int(store.lineage_trials(fid))
    skip = unrelated_children(store, fid)
    lines = store.lineages(fid) if skip else []
    if not lines:
        return full
    row = store._one(f"SELECT COALESCE(SUM(trials), 0) AS n FROM families WHERE lineage IN ({','.join('?' * len(lines))}) "
                     f"AND id IN ({','.join('?' * len(skip))})", (*lines, *sorted(skip)))
    return max(0, full - int((row or {}).get("n") or 0))


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
#: A figure as the scan compares it: a number with four places that is not a piece of a longer one (a run's 343.4697
#: holds no 3.4697).
_FIGURE = re.compile(r"(?<![\d.])-?\d+\.\d{4}(?!\d)")


def _shown(items: Any) -> list[str]:
    """The texts of a stored conversation (`convo`'s items, by cycle) that its researcher was SHOWN: the user turns (the
    brief, the status, a queued run's answer) and the tool outputs. Never its own words (the model's messages, its calls
    and its queued call), and never the library's answers: a paper's dates are its own (THE LIBRARY's known gap)."""
    from .library import TOOL_NAME  # a local import, as every other

    flat: list[Mapping[str, Any]] = []

    def walk(node: Any) -> None:
        if isinstance(node, list):
            for x in node:
                walk(x)
        elif isinstance(node, Mapping):
            if isinstance(node.get("items"), list) and "role" not in node and "type" not in node:
                walk(node["items"])  # a cycle
            else:
                flat.append(node)

    walk(items)
    library = {i.get("call_id") for i in flat if i.get("type") == "function_call" and i.get("name") == TOOL_NAME}
    out = []
    for item in flat:
        if item.get("type") == "function_call_output":
            if item.get("call_id") not in library:
                body = item.get("output")
                out.append(body if isinstance(body, str) else _dumps(body))
        elif item.get("role") in ("user", "tool", "system") and item.get("type") in (None, "message"):
            body = item.get("content")
            out.append(body if isinstance(body, str) else _dumps(body))
    return out


def _leak_scan(store: Any, rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Each game-arm family's conversation, what it was shown (`_shown`), searched for a hidden year key or date, and for
    its looks' hidden figures to four places: a hit is a text that holds two of one look's figures (all of them, when it
    has fewer), never one figure alone, which a run's numbers hold by chance."""
    families = sorted({str(r["family"]) for r in rows if r["arm"] == "game"})
    figures: dict[str, list[set[str]]] = {}
    for r in rows:
        if r["arm"] != "game":
            continue
        mine = set()
        for fig in (r.get("years") or {}).values():
            for key in ("t_net", "t_alpha", "F"):
                value = _num((fig or {}).get(key))
                if value is not None and abs(value) >= 0.01:
                    mine.add(f"{value:.4f}")
        if mine:
            figures.setdefault(str(r["family"]), []).append(mine)
    hits = []
    for fid in families:
        texts = _shown(store.convo(fid)[0])
        if any(_HIDDEN_TEXT.search(text) for text in texts):
            hits.append({"family": fid, "kind": "hidden year"})
        tokens = [set(_FIGURE.findall(text)) for text in texts]
        if any(len(look & found) >= min(2, len(look)) for look in figures.get(fid, ()) for found in tokens):
            hits.append({"family": fid, "kind": "hidden figure"})
    return {"families": len(families), "hits": hits, "passed": not hits}


def metrics(store: Any, *, settings: Mapping[str, Any] | None = None, now: float | None = None, draws: int = BOOT_DRAWS,
            seed: int = 0) -> dict[str, Any]:
    """The operator's measurement (the spec's section 7), aggregate only: R1 plumbing, R2 selection carry, R3 out-of-fold
    quality of what each arm would validate, R4 generation gain, R5 flow and cost (the last 24 hours and in all) and R6
    Validation and money per arm. Intervals are family-cluster bootstraps (`draws`, 90% two-sided, seeded). Reads both
    hidden years of every landed look of the current epoch (since T0; a void's new T0 leaves the void epoch's looks out:
    `_operator_years`): called only by the operator's report, which no agent reads."""
    rng = random.Random(seed)
    now = float(store.clock() if now is None else now)
    epoch = t0(store) or ""
    rows = [r for r in _rows(store, confirms=True, operator=True) if str(r["at"]) >= epoch]
    landed_rows = [r for r in rows if r["status"] == "ok"]
    looks = []
    for r in landed_rows:
        f_sel, f_conf = _operator_years(r)
        looks.append({"seq": int(r["seq"]), "family": str(r["family"]), "lineage": str(r["lineage"]), "arm": r["arm"],
                      "role": r["role"], "version": int(r["version"]), "sha": str(r["sha"]), "generation": int(r["generation"]),
                      "tier": r["tier"], "seen": _num(r["seen_score"]), "seen_f": _num(r["seen_f"]), "sel": f_sel,
                      "conf": f_conf, "at": r["result_at"]})
    # THE DIRECTION LANE (release D-1; PLAN D4): its looks (a direction lineage a non-zero `dlane.arm_fraction` admitted,
    # or one whose arm was kept from before) are kept out of R1(b), whose D1 needs a random fold, and out of R2, whose
    # selection carry needs a CONFIRM year the lane has no use for. None while the lane is off.
    direction = _direction_families(store, {x["family"] for x in looks}, settings)

    # R1: plumbing. D1 by LINEAGE: the roles are the lineage's, so every look of one (and of versions of one program) shares
    # its sign of F2020 - F2021; each lineage's mean is one draw, and the SE is over the lineages.
    founders: dict[str, list[float]] = {}
    for x in looks:
        if x["generation"] == 0 and x["sel"] is not None and x["conf"] is not None and x["family"] not in direction:
            founders.setdefault(x["lineage"], []).append(x["sel"] - x["conf"])
    by_lineage = [sum(d) / len(d) for _, d in sorted(founders.items())]
    d_mean = _mean(by_lineage)
    d_se = (math.sqrt(sum((d - d_mean) ** 2 for d in by_lineage) / (len(by_lineage) - 1) / len(by_lineage))
            if d_mean is not None and len(by_lineage) >= 2 else None)
    z = d_mean / d_se if d_mean is not None and d_se else None
    submissions = len(rows) + sum(int(r["attempts"]) - 1 for r in rows)
    errors = sum(int(r["errors"]) for r in rows)
    years = [fig for r in landed_rows for fig in (r["years"] or {}).values()]
    ineligible = sum(1 for fig in years if not (fig or {}).get("eligible"))
    r1 = {"leak": _leak_scan(store, rows),
          "d1_founders": {"n": sum(len(d) for d in founders.values()), "lineages": len(by_lineage), "mean": d_mean,
                          "se": d_se, "z": z,
                          "passed": z is None or len(by_lineage) < D1_MIN_LINEAGES or abs(z) <= 2.5},
          "failure_rate": {"submissions": submissions, "errors": errors,
                           "rate": errors / submissions if submissions else None,
                           "passed": not submissions or errors / submissions < 0.05},
          "ineligible": {"years": len(years), "ineligible": ineligible, "share": ineligible / len(years) if years else None,
                         "flag": bool(years) and ineligible / len(years) > 0.5}}

    # R2: does one hidden year predict the other better than the seen years do (the same looks, both arms).
    both = [x for x in looks if x["sel"] is not None and x["conf"] is not None and x["seen"] is not None
            and x["family"] not in direction]

    def carry(items: list[Mapping[str, Any]]) -> float | None:
        hidden = spearman([x["sel"] for x in items], [x["conf"] for x in items])
        seen = spearman([x["seen"] for x in items], [x["conf"] for x in items])
        return None if hidden is None or seen is None else hidden - seen

    r2 = {"n": len(both), "rho_hidden": spearman([x["sel"] for x in both], [x["conf"] for x in both]),
          "rho_seen": spearman([x["seen"] for x in both], [x["conf"] for x in both]), "delta_rho": carry(both),
          "ci": _cluster_ci(both, carry, draws=draws, rng=rng)}

    # R3: the CONFIRM year of what each arm would send to Validation (game SELECT passers, control's validated versions: every
    # control look, of either role, at a version with a Validation run, one a program; a validated version the ladder looked
    # at first is in it too).
    passers = [x for x in looks if x["arm"] == "game" and x["role"] == "ladder" and x["tier"] == "PASS" and x["conf"] is not None]
    tried = {(str(r["family"]), int(r["version"])) for r in store._all(
        "SELECT DISTINCT family, version FROM runs WHERE window='validation' AND stress=1.0 AND version IS NOT NULL")}
    programs: dict[tuple[str, str], Mapping[str, Any]] = {}
    for x in looks:
        if x["arm"] == "control" and x["conf"] is not None and (x["family"], x["version"]) in tried:
            programs.setdefault((x["lineage"], x["sha"]), x)
    validated = sorted(programs.values(), key=lambda x: x["seq"])

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
    children = store._all("SELECT * FROM game_children WHERE at>=? ORDER BY seq", (epoch,)) if _tables(store) else []
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
    # The game's retirements by rule (their reason is the same words for all three, `RETIRED`): the rule they met.
    rules = {str(k): 0 for k in RULES}
    c = cfg(settings)
    for f in store._all("SELECT id FROM families WHERE retire_reason=? ORDER BY id", (RETIRED,)):
        met = _rule(store, store.family(str(f["id"])) or {"id": f["id"]}, c)
        if met is not None:
            rules[str(met[0])] += 1
    r5 = {"day": flow(since), "all": flow(""), "children_beat_founder": {"n": len(beats),
                                                                        "share": sum(beats) / len(beats) if beats else None},
          "hidden_submissions": submissions, "spend_24h": spend, "retired_by_rule": rules}

    # R6: Validation and money per arm (the families the game looked at, or every family with the settings).
    arms: dict[str, str] = {str(r["family"]): r["arm"] for r in rows}
    if settings is not None:
        start, registry = live_t0(store), _registry(store)
        for fam in store.families():
            side = _arm_of(fam, c, start, registry, sits_out=lambda f=fam: _sits_out(store, f, settings, c)) \
                if c["enabled"] else None
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
            for v in _validated(store, str(fam["id"])):
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
    out = {"at": _iso(now), "looks": len(rows), "landed": len(landed_rows), "R1": r1, "R2": r2, "R3": r3, "R4": r4, "R5": r5,
           "R6": r6}
    if dlane.on(settings):
        out["dlane"] = {
            "label": dlane.LABEL, "excluded_from": ["R1.d1_founders", "R2"],
            "excluded_families": len(direction), "excluded_looks": sum(1 for x in looks if x["family"] in direction),
            "births_24h": dlane.born_counts(store, 24.0, now=now),
            "notes": list(DIRECTION_NOTES)}
    return out


#: What the operator's report says about the game's T0 experiment while the direction lane is on (release D-1; the
#: operator's decision 1): two changes made mid-way through it, so its arms' flow and prompts before and after the release
#: are not one series, and what the lane is to the game. The operator's report (league/ops/game_report.py) carries them
#: through `metrics` (its `dlane` block), the one place they are said.
DIRECTION_NOTES = (
    "the direction lane's birth quota (dlane.birth_share 0.5, max_share 0.6) takes up to half the births: the alpha "
    "lane's fall from about 73 to about 36 a day mid-way through the game's T0 experiment (births_24h counts them by lane)",
    "the researcher's role text became lane-aware at the same release; it is the shared prefix, so the alpha arms' "
    "prompts changed mid-experiment too: 'alpha golden' means the code paths only, not the prompts",
    "direction lineages never play the game (dlane.arm_fraction 0: no hidden look) and their looks are kept out of R1(b) "
    "and R2",
)


def _direction_families(store: Any, ids: Any, settings: Mapping[str, Any] | None) -> frozenset[str]:
    """The families among `ids` whose lane is "direction" now (`dlane.lane_of`); empty while the lane is off (no store
    read: THE ROLLBACK). Never raises (an unreadable family is alpha's)."""
    if not dlane.on(settings):
        return frozenset()
    out = set()
    for fid in sorted({str(i) for i in ids}):
        try:
            if dlane.lane_of(store, store.family(fid), settings) == dlane.DIRECTION:
                out.add(fid)
        except Exception:  # noqa: BLE001
            continue
    return frozenset(out)


__all__ = ["SWITCH_AT", "HIDDEN", "HIDDEN_YEARS", "SEEN_FROM", "CORE", "DEFAULTS", "DIRECTIVES", "ROTATION", "GAME_SQL", "HIDDEN_SPLIT",
           "PROGRAM_ENDS", "RETIRED", "RULES", "Sealed", "cfg", "birth_roots", "seen_only", "t0", "live_t0", "void", "started",
           "fold", "arm", "fitness", "seen_fitness", "tier_of", "ensure", "select_view", "confirm_view", "maybe_look", "landed",
           "confirm_waiting", "requeue_stale", "recheck", "shadow_validated", "candidate", "validations_left",
           "seen_robust_ok", "look_seen_run", "in_flight", "looks_used", "retire_reason", "retire_rule", "parents",
           "reproduce", "visible_families", "visible_graveyard", "quarantined", "visible_shares", "unrelated_children",
           "shown_trials", "status_text", "brief_text", "spearman", "metrics", "DIRECTION_ARM_KEY", "DIRECTION_NOTES"]
