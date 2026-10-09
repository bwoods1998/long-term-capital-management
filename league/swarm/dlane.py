"""THE DIRECTION LANE (release D-1, Oct 9, 2026): a second research lane, beside the unchanged alpha lane, in which the
profit of the index's direction counts, reported beside the same-risk buy-and-hold and never called alpha.

WHY. Across 534 pre-registered tests no options alpha survived one-lot costs. The only after-cost profit ever measured is
index direction carried by cheap out-of-the-money calls held a few sessions, and no affordable structure beat holding the
same delta in the stock: it is LEVERAGED INDEX BETA MINUS OPTION COSTS, not alpha. The owner's goal (Oct 7, item 4)
counts direction profit when it is reported beside the same-risk buy-and-hold. Until this release every instruction and
judge the swarm reads still charged drift: the researcher's role said drift is never validated, the worst-year Train score
ranked a 2022-exposed long program last, and the game's F = min(t_net, t_alpha) scored an always-long program at about
zero by construction. Since fast lane v2 (Oct 7) 115 core-five direction births self-refuted, none reached Validation.
This module is the lane's one home: its settings and their bounds, the Train bar it is judged by, the unit it must fit,
the screen its holdout look uses, its birth quota and the text its agents read. The alpha lane's rules are not here and
do not change: nothing in this module is called for an alpha family, and with `dlane.mode` "off" nothing here acts at all.

THE LANE (`lane_of`). A family's lane is its card's (`card.lane`, "alpha" by default, "direction" declared by the architect;
the family's `spec.lane` carries the same word): immutable, inherited by a fork or a game child through the card. A card
with no lane, and every family born before this release, is alpha. A direction card is admitted only inside the lane's
box (`card_errors`): mechanism class in `dlane.classes` (`equity_premium`, NEW, or `trend_momentum`), structure in
`dlane.structures`, roots inside `dlane.roots` (SPY, QQQ, IWM: the roots `TRAIN_CLOSE_2024` prices), holding in
`dlane.holding`, and a real ablation switch (never a flat comparison). Every refusal names every reason.

THE TRAIN BAR, direction-v2 (`train_score`, `robust_verdict`; PLAN D3 and the operator's decision 2 of Oct 9, 05:30Z).
On the version's Train run (2022-24 only, whatever older year a result carries: `FIRST_YEAR`) and its 1.5x robustness run,
per Train year y (the Gym's `by_year` and the drift block's year row): t_y the all-days t of the year's daily dollar P&L
(the game's t_net: `_t_of(pnl, sum_pp, days, sum_pp)`), x_y = held_days / days its exposure share, and ACTIVE(y) when it
has at least 40 trades on 20 traded days (`evidence.TRAIN_YEAR_MIN_TRADES`, `TRAIN_YEAR_MIN_DAYS`) and x_y is at least
`active_share` (0.5) of its busiest year's; otherwise the year is OUT. Bars on the 1.0x run:
  E1  ACTIVE in at least `min_active_years` (2) Train years;
  E3  every OUT year: t_y >= `out_t_floor` (-1.0) and P&L >= -`out_loss_share` (0.5) x the mean P&L of its ACTIVE years
      (a year with no variance, flat all year, reads t 0);
  E4  every ACTIVE year: at least `min_entry_days` (60) entry sessions;
  E5  THE UNIT: the median one-lot maximum loss with fees of its 2024 trades, times today's price scale (the House's last
      close in `CLOSES_FILE`, the `direction` job's, over `TRAIN_CLOSE_2024`, the largest over the roots it traded), at most
      the unit cap (`unit_cap_usd`, else `unit_share` (10%) of the equity the live path last wrote to `health.json`). Read
      live, never a fixed scale (decision 3); a missing closes file, equity or 2024 trade reads "unknown", which PASSES:
      the live path prices every real open again (`unit_context`).
  C1  CALLS ONLY (release D-1b, Oct 9, 2026): every Train trade's legs are long calls (`calls_only`; D2 was measured on
      long calls and a `long_single` program may send a put by its code). Judged first.
The score S_D is the pooled t of daily P&L over the Train years at 1.0x. On the 1.5x run (`robust_verdict`), each a
demotion when it fails:
  P1  the run's P&L above zero (the House's existing 1.5x rule, unchanged);
  R2  E1 and E3 hold at 1.5x;
  R3  the 1.5x P&L at least `cost_ratio` (0.5) x the 1.0x P&L (both summed over the Train years).
REPORTED, NEVER A BAR (decision 2): E2 (every ACTIVE year t >= 0), R1 (the pooled t at 1.5x against `c_train`, 1.5) and
the mechanism or ablation figures. Holds of 2 to 8 sessions are all admissible: there is no hold bar. Every view, brief
and status line says plainly that AN ALWAYS-IN CALL PROGRAM CAN PASS THIS BAR, the gate is not tested by it, and profit
here is leveraged index beta minus option costs, not alpha (`ALWAYS_IN_NOTE`). Why this bar and not HARNESS's
direction-v1: v1 admitted no program of the census at all; Train is in-sample and the screen's measured false-positive
rate is the out-of-sample chain's, so loosening the Train bar leaves the false-positive rate per program screened where
it was (its cost is more paid reviews and audits).

THE SCREEN (`screen_effective`; decision 6). The direction lane's holdout look is "S-C": the Validation line as coded,
then one look at p <= 0.20 (`look_level`) with a holdout Sharpe at least 0.25 (`sharpe_share`) of Validation's; the alpha
lane keeps "S-B" (`evidence.LOOK_LEVEL` 0.10, `HOLDOUT_SHARPE_SHARE` 0.5) byte for byte. "D2" (a pre-check then a pooled
test) is REFUSED unless a receipt's sha256 is pinned in the repository's own policy.json
(`dlane.screens.D2.receipt_sha256`, read from the file, never from the box's swarm.json) together with its calibrated `c`;
CI holds that sha to `docs/benchmarks/direction_screen_2.json` (`docs/benchmarks/` never reaches the box). Every look
event records the lane, the screen and the receipt the effective screen names.
D2 IS ON (release D-1b, Oct 9, 2026; the operator's decision DSCREEN-ADOPT, a REPORTED LOOSENING): policy.json sets
`dlane.screen` "D2" and pins the receipt of DSCREEN-2 (sha c3605947, c 1.00). The rule, exactly as pre-registered
(`d2_precheck`, `d2_pooled_t`, the gate's `look_line`): on Validation at 1.0x at least 50 trades on at least 25 entry
days with a mean entry-day return above zero; after the one sealed look, the pooled entry-day t over the Validation and
holdout entry days at least `c` AND the holdout's P&L above zero. Its measured false-positive rate per program at zero
edge is 10.37% on mixed worlds and 12.39% on 2022-24 worlds (the receipt's lane figures; the owner's ceiling is 15%),
stated beside every look and every Probe trade (`fp_lane_mixed`, `fp_lane_2224`). It is adopted for a CALLS-ONLY lane:
D2 is refused while `dlane.structures` admits anything but single calls (`D2_STRUCTURES`). TIGHTENED with it: one
Validation try and one holdout look per direction lineage (`val_tries`, `looks_per_lineage`; `lineage_tries`,
`try_open`, `lineage_spent`), so a lineage's false-positive rate is the program's. THE ROLLBACK is instant and is a
tightening: swarm.json `dlane.screen` "S-C" (a setting may always choose S-C; it can never pin a receipt).

THE BIRTH QUOTA (`DirectionQuota`; decision 1). While the lane is behind `birth_share` (0.5) of the last
`window_hours` (24) of births and fewer than `max_alive` (24) direction families live, at least
max(`min_per_pass`, ceil(0.5 x want)) of a pass's births are reserved for direction and never filled with alpha (a pass
short of them records `lane_short`); the lane never holds more than `max_share` (0.6) of the window, so the alpha lane
keeps at least 40%. The cost, said in the CHANGELOG and the game's metrics: alpha births fall from about 73 to about 36
a day mid-way through the game's T0 experiment.

MODES (`MODES`; `mode_effective`). "off": THE ROLLBACK. Every lane is alpha (`lane_of`), no direction card is admitted,
no quota, text, score or screen of this module is used: every path is the release before it (ccfa48d5), byte for byte.
It is also the code's default, so a missing or dropped policy layer is the rollback, and the tests (which read an empty
policy layer) run the release before it unless they switch the lane on. "shadow": births, the direction objective,
research and Validation run; no direction family becomes a Candidate and the incubator takes no direction mark.
"gate": everything. A malformed `mode` reads "shadow". K5 (decision 9): while the store's kv `dlane_k5` is set (the
`dlane` report job sets it when the lane's realized net over every route is at or below its line, `k5_net_usd`, -$600,
below the net at the operator's last clear), a "gate" lane reads "shadow"; only the operator clears it (swarm.json
`dlane.k5_clear` true, or deleting the kv). A tightening, never a trade. THE CLEAR IS DURABLE (the review of Oct 9,
2026; `k5_rearm`): the job's next run records it (kv `dlane_k5_base`: the net then) and re-arms K5 at `k5_net_usd`
below that net, so a cleared K5 neither trips again at once on the same losses nor stays off for good. While
`k5_clear` is true K5 cannot trip at all: that is a loosening while it stays, and the report warns every run until the
operator takes it out.

SETTINGS. Every default is in league/swarm/policy.json's "dlane" block (the owner's deploy); swarm.json overrides it; each
value is held inside its bound here (`cfg`): a malformed value is its default, a number past a bound is the bound. The
evidence numbers (the screen, the leakage alarm, K5) are bounded so that a setting can only TIGHTEN them past the reviewed
policy.

WHAT AGENTS SEE. Rules and Train-year (2022-24) facts only: never a hidden-year figure, never a Validation or holdout
figure, never a number from the operator's private studies but THE TRAIN MAP's, below (`brief_text`, `status_text`,
`view`, `lanes_text` are tested for it). E5 is shown as its verdict alone (`UNIT_HINT`, the review of Oct 9, 2026):
today's price scale (the House's last closes over 2024's) and the unit cap (a share of the account's equity) are 2026
figures, kept in the family state and the operator's report only.

THE TRAIN MAP (Oct 9, 2026; `train_map`, `train_map_text`, `train_map_brief`). The operator's census scored every
SPY/QQQ/IWM call shape (delta, expiry rule, hold, entry minute, gate; one lot at natural prices) by this module's own
direction-v2 on the Train years 2022-24 only; league/swarm/dlane_map.json holds what agents may see of it: the passing
shapes in its own words with their pooled S_D to one decimal and the unit's verdict as a word, and its lessons. While
the lane is on and `dlane.train_map` is true (policy.json true; swarm.json false hides it at once; the code's default
is off), the architect's LANES block lists the passing shapes and the lessons and a direction researcher's brief the
lessons and the best passing shapes on its roots, every one labelled "in-sample: Train years 2022-24, from the
operator's census at one-lot natural prices; the screen decides" (`MAP_LABEL`). It is the one figure from an operator
study agents read, and it is Train-year only: no dollar figure, price level or price ratio, no per-year figure, no year
but 2022-24 (`map_text_problems` holds every text field of the file to that, or the file is no map). Its cost: births
aim at in-sample winners; the screen's false-positive rate per program is unchanged, and more programs reach the
screen, so more false passes in count.

Standard library only (the House box runs it without numpy).
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import time
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from . import evidence

# ----------------------------------------------------------------------------------------------------------- vocabulary
OBJECTIVE = "direction-v2"
ALPHA, DIRECTION = "alpha", "direction"
LANES = (ALPHA, DIRECTION)
MODES = ("off", "shadow", "gate")
#: The direction lane's screens (decision 6); the alpha lane's look is "S-B" (`evidence.LOOK_LEVEL`, `HOLDOUT_SHARPE_SHARE`).
SCREENS = ("S-C", "D2")
ALPHA_SCREEN = "S-B"
#: The Train years the lane is judged on: the seen span (2022-24). An older year a result carries (the 2020-21 switch, a
#: 2017 Train) is never read, so no hidden year reaches a direction score or a view.
FIRST_YEAR, LAST_YEAR = 2022, 2024
#: The mean 15:30 close of each lane root over 2024 (the operator's 2024 data, pinned Oct 9, 2026): E5's price scale is
#: the House's last close over this.
TRAIN_CLOSE_2024: dict[str, float] = {"SPY": 540.9, "QQQ": 464.4, "IWM": 211.0}
ROOTS = tuple(TRAIN_CLOSE_2024)
#: The structures a direction card may name (a direction `long_single` buys calls only: the agenda and the brief say so).
STRUCTURES = ("long_single", "debit_vertical", "long_call")
#: THE CALLS-ONLY LANE (release D-1b, Oct 9, 2026): D2 was measured on, and adopted for, single calls (DSCREEN-2's lane:
#: 0.20/0.30-delta calls held 5 or 8 sessions). While `dlane.structures` names any other (a debit vertical), D2 is
#: refused and the lane's look is S-C (`screen_effective`). A put is no lane structure at all; a direction program's
#: Train trades must all be long calls (`calls_only`, the bar C1).
D2_STRUCTURES = ("long_single", "long_call")
#: The mechanism classes of the lane. `equity_premium` is NEW (cards.MECHANISM_CLASSES gains it with this sentence).
CLASSES = ("equity_premium", "trend_momentum")
EQUITY_PREMIUM = ("the equity risk premium: index ETFs drift up on average because holders are paid to bear market risk; "
                  "a long call or call vertical rents that drift and earns only when its cost (time decay, implied over "
                  "realized volatility, the spread) is below the drift it captures")
#: The card holdings of the lane: 2 to 8 sessions lie in these two buckets (decision 2: no hold bar).
HOLDINGS = ("days_1_3", "days_4_10")
#: The plain statement every direction view, brief and status line carries (decision 2).
ALWAYS_IN_NOTE = ("an always-in call program can pass this bar; the gate is not tested by it; profit here is leveraged "
                  "index beta minus option costs, not alpha")
#: The label every direction figure in an operator's report carries (PLAN section 6).
LABEL = "direction lane: leveraged index beta minus option costs; not alpha"
#: The files the unit reads (`unit_context`), in the House's state directory (the swarm store's root).
CLOSES_FILE = "direction-closes.json"
HEALTH_FILE = "health.json"
#: The family state's key of the lane's verdicts (`record`), and how many versions it keeps.
STATE_KEY = "dlane"
#: The family state's key of its direction lineage's Validation try (release D-1b, `Tournament._verdict`): {version, at,
#: first, entered}: the version judged, whether it was its lineage's FIRST try (only the first may enter the gate) and
#: whether it entered the gate (met the line, or D2's pre-check while D2 was in force). `lineage_spent` reads it.
TRY_KEY = "dlane_try"
#: What an agent is told when E5 fails (the review of Oct 9, 2026): the verdict and this scale-free hint, never a figure
#: priced at today's closes or the account's equity (`unit_of`'s `why`, `view`, `status_text`, the architect's LANES
#: block). A dollar figure at today's prices over a 2024 one is today's index level against 2024's, a 2026 market figure
#: (the holdout's tail included), and the cap is a share of the account's equity, a 2026 P&L figure; agents may read rules
#: and Train-year (2022-24) facts only. The figures stay in the family state (`record`) and the operator's report.
UNIT_HINT = ("choose a further out-of-the-money strike or a nearer expiry: one lot's premium is its maximum loss, and the "
             "cap is a share of the account")
VERSIONS_KEPT = 12
#: The store's kv keys: K5 (`k5_state`), K5's re-arm base (`k5_rearm`: the net at the operator's last clear, and the trip
#: not yet cleared), the lane's first switch-on (`started_at`) and the last `lane_only` request.
K5_KEY = "dlane_k5"
K5_BASE_KEY = "dlane_k5_base"
STARTED_KEY = "dlane_started_at"
LANE_ONLY_KEY = "dlane_lane_only_at"
#: ACTIVE's frequency floor: the Train score's own (40 trades on 20 traded days).
ACTIVE_MIN_TRADES = evidence.TRAIN_YEAR_MIN_TRADES
ACTIVE_MIN_DAYS = evidence.TRAIN_YEAR_MIN_DAYS
#: The architect reads at most this many characters of its locked agenda (`architect.AGENDA_LOCKED_MAX`; a test holds
#: them equal): `agenda_problems` refuses a longer text.
AGENDA_MAX = 4000
#: The hidden years: never named to an agent (the agenda guard refuses them as digits).
HIDDEN_YEAR_DIGITS = ("2020", "2021")
#: THE DONE RULE (DONE-RULE.md, pinned Oct 9, 2026 before L-D or D-1 shipped; decision 8). Not settings: how Done is read
#: is fixed before any number is seen. The `dlane` report job reads them.
DONE: dict[str, Any] = {
    "rule_sha256": "0d007696c9a6a1cbbd7d2cc345811359ab1cec389cf88f75ceff295bbbc48dca",
    "inception": "2026-09-26T06:23:00Z",       # the options swarm's start: every agent real close since counts
    "routes_all": (":r", ":t", ":i"),           # done_all: Probe/Sized, tuition, incubator
    "routes_screen": (":r",),                    # done_screen: the evidence route alone
    "min_closes": 30, "min_programs": 2, "min_closes_per_program": 5,
    "gap_limit": 0.10, "gap_min_matched": 5,     # consistent: mean live-minus-replay gap within +/-0.10 over 5+ matched
    "first_checkpoint": 30, "checkpoint_every": 10,
}

DEFAULTS: dict[str, Any] = {
    # The code's default is the rollback; policy.json switches the lane on ("gate").
    "mode": "off",
    "roots": list(ROOTS), "structures": ["long_single", "debit_vertical"], "classes": list(CLASSES),
    "holding": list(HOLDINGS),
    # THE BIRTH QUOTA (decision 1).
    "birth_share": 0.5, "max_share": 0.6, "min_per_pass": 1, "max_alive": 24, "window_hours": 24, "min_window": 10,
    "lane_only_hours": 12,
    # THE TRAIN BAR, direction-v2 (decision 2).
    "active_share": 0.5, "min_active_years": 2, "out_t_floor": -1.0, "out_loss_share": 0.5, "min_entry_days": 60,
    "cost_ratio": 0.5, "c_train": 1.5,
    # THE UNIT (decision 3): null `unit_cap_usd` is `unit_share` of the live equity.
    "unit_cap_usd": None, "unit_share": 0.10, "unit_pref_usd": 75,
    # No hidden look for direction (decision 5): `game._arm` returns None for a direction lineage.
    "arm_fraction": 0.0,
    # THE SCREEN (decision 6). S-C's `fp_unconditional` is its lane false-positive rate at zero edge on MONEY's mixed worlds
    # (1.41%), so it is also its `fp_lane_mixed`; `fp_lane_2224` is S-C's lane rate on DSCREEN-2's 2022-24 worlds (2.09%,
    # measured beside D2 on the same worlds, not a decision input): each look and each Probe trade states both.
    "screen": "S-C",
    "screens": {"S-C": {"look_level": 0.20, "sharpe_share": 0.25, "fp_unconditional": 0.0141, "fp_both_windows_rose": 0.0222,
                        "fp_lane_2224": 0.0209},
                "D2": {"receipt_sha256": None}},
    # ONE TRY AND ONE LOOK PER DIRECTION LINEAGE (release D-1b, Oct 9, 2026; DSCREEN-ADOPT): D2's false-positive rate is
    # the program's; a lineage that could try again would multiply it (DSCREEN-2's per-lineage reading A, two tries:
    # 16.4% on mixed worlds). Bounded at 1: a setting can never loosen them (the alpha lane keeps `evidence`'s counts).
    "val_tries": 1, "looks_per_lineage": 1,
    # THE LEAKAGE ALARM of the direction lane (decision 7; the alpha lane's is `evidence.leakage_alarm`, unchanged).
    "alarm_min_looks": 10, "alarm_pass_share": 0.60,
    # THE DONE METER's zero-edge figure (decision 8: "P(Done | zero edge), simulation").
    "done_zero_edge_p": 0.13,
    # K5 (decision 9).
    "k5_net_usd": -600, "k5_clear": False,
    # THE TRAIN MAP (Oct 9, 2026; `train_map`): shown to the architect and direction researchers only when true. The
    # code's default is off (a dropped policy layer shows nothing); policy.json sets it true; swarm.json false hides it.
    "train_map": False,
}

_SHA = re.compile(r"^[0-9a-f]{64}$")


# ----------------------------------------------------------------------------------------------------------- settings
def _num(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(float(value)) else None


def _token(value: Any) -> str:
    return re.sub(r"[\s\-]+", "_", str(value or "").strip().lower())


def cfg(settings: Mapping[str, Any] | None) -> dict[str, Any]:
    """`dlane` in the swarm's settings, each value inside its bound (the module docstring's SETTINGS): a malformed value is
    its default, a number past a bound is the bound, a count that is not a whole number is malformed. A missing `mode` is
    "off" (the rollback); a malformed one is "shadow". Lists keep only the lane's own words (`ROOTS`, `STRUCTURES`,
    `CLASSES`, `HOLDINGS`) and an empty one is the default. `max_share` is never under `birth_share`. The screen, the
    leakage alarm and K5 can only be TIGHTENED past the policy's (`look_level` <= 0.20, `sharpe_share` >= 0.25,
    `alarm_pass_share` <= 0.60, `k5_net_usd` >= -600). A direction lineage's Validation tries and holdout looks
    (`val_tries`, `looks_per_lineage`, release D-1b) are 1 whatever is written: D2's measured rate is per program."""
    raw = (settings or {}).get("dlane") if isinstance(settings, Mapping) else None
    raw = raw if isinstance(raw, Mapping) else {}

    def number(key: str, low: float, high: float, *, count: bool = False, block: Mapping[str, Any] | None = None,
               default: Any = None) -> float:
        src = raw if block is None else block
        fallback = DEFAULTS[key] if default is None else default
        value = src.get(key, fallback)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) \
                or (count and not float(value).is_integer()):
            value = fallback
        return float(min(high, max(low, value)))

    def whole(key: str, low: int, high: int) -> int:
        return int(number(key, low, high, count=True))

    def words(key: str, allowed: Sequence[str], *, upper: bool = False) -> list[str]:
        value = raw.get(key)
        if not isinstance(value, list):
            return list(DEFAULTS[key])
        norm = [(str(v).strip().upper() if upper else _token(v)) for v in value if isinstance(v, str)]
        kept = list(dict.fromkeys(v for v in norm if v in allowed))
        return kept or list(DEFAULTS[key])

    mode = raw.get("mode", DEFAULTS["mode"])
    mode = mode if mode in MODES else "shadow"
    birth = number("birth_share", 0.0, 0.6)
    cap = raw.get("unit_cap_usd")
    cap = None if cap is None or _num(cap) is None else float(min(129.0, max(25.0, float(cap))))
    screen = raw.get("screen")
    screens_raw = raw.get("screens") if isinstance(raw.get("screens"), Mapping) else {}
    sc_raw = screens_raw.get("S-C") if isinstance(screens_raw.get("S-C"), Mapping) else {}
    d2_raw = screens_raw.get("D2") if isinstance(screens_raw.get("D2"), Mapping) else {}
    sc_default = DEFAULTS["screens"]["S-C"]
    return {
        "mode": mode,
        "roots": words("roots", ROOTS, upper=True), "structures": words("structures", STRUCTURES),
        "classes": words("classes", CLASSES), "holding": words("holding", HOLDINGS),
        "birth_share": birth, "max_share": number("max_share", birth, 0.8),
        "min_per_pass": whole("min_per_pass", 0, 3), "max_alive": whole("max_alive", 0, 96),
        "window_hours": number("window_hours", 1.0, 168.0), "min_window": whole("min_window", 1, 1000),
        "lane_only_hours": number("lane_only_hours", 1.0, 168.0),
        "active_share": number("active_share", 0.3, 0.8), "min_active_years": whole("min_active_years", 2, 3),
        "out_t_floor": number("out_t_floor", -1.5, 0.0), "out_loss_share": number("out_loss_share", 0.0, 1.0),
        "min_entry_days": whole("min_entry_days", 40, 200),
        "cost_ratio": number("cost_ratio", 0.3, 1.0), "c_train": number("c_train", 1.28, 3.0),
        "unit_cap_usd": cap, "unit_share": number("unit_share", 0.01, 0.10),
        "unit_pref_usd": number("unit_pref_usd", 25.0, 129.0),
        "arm_fraction": number("arm_fraction", 0.0, 1.0),
        "screen": screen if screen in SCREENS else DEFAULTS["screen"],
        "screens": {
            "S-C": {"look_level": number("look_level", 0.01, 0.20, block=sc_raw, default=sc_default["look_level"]),
                    "sharpe_share": number("sharpe_share", 0.25, 1.0, block=sc_raw, default=sc_default["sharpe_share"]),
                    "fp_unconditional": number("fp_unconditional", 0.0, 1.0, block=sc_raw,
                                               default=sc_default["fp_unconditional"]),
                    "fp_both_windows_rose": number("fp_both_windows_rose", 0.0, 1.0, block=sc_raw,
                                                   default=sc_default["fp_both_windows_rose"]),
                    "fp_lane_2224": number("fp_lane_2224", 0.0, 1.0, block=sc_raw, default=sc_default["fp_lane_2224"])},
            "D2": _d2_block(d2_raw)},
        "val_tries": whole("val_tries", 1, 1), "looks_per_lineage": whole("looks_per_lineage", 1, 1),
        "alarm_min_looks": whole("alarm_min_looks", 10, 1000),
        "alarm_pass_share": number("alarm_pass_share", 0.30, 0.60),
        "done_zero_edge_p": number("done_zero_edge_p", 0.0, 1.0),
        "k5_net_usd": number("k5_net_usd", -600.0, -50.0),
        "k5_clear": raw.get("k5_clear") is True,
        "train_map": raw.get("train_map") is True,
    }


#: The figures a D2 block carries beside its sha and `c` (release D-1b: the receipt's lane figures, reported only, never
#: a bar): the lane's false-positive rate at zero edge on mixed worlds and on 2022-24 worlds, its 95% world-bootstrap and
#: cluster-bootstrap intervals on mixed worlds, and the lane's power at +10% of maximum loss a trade (mixed worlds).
D2_RATES = ("fp_lane_mixed", "fp_lane_2224", "power10", "fp_unconditional", "fp_both_windows_rose")
D2_INTERVALS = ("fp_lane_ci_mixed", "fp_lane_cluster_mixed")


def _d2_block(raw: Mapping[str, Any]) -> dict[str, Any]:
    """The D2 screen's block as written: a receipt sha (64 lower-case hex, else None), its calibrated pooled-t bar `c`
    (0.5-4.0, else None) and the figures its receipt measured (`D2_RATES`, each in [0, 1], else None; `D2_INTERVALS`, each
    [low, high] in [0, 1] with low <= high, else None), reported only."""
    sha = raw.get("receipt_sha256")
    sha = sha if isinstance(sha, str) and _SHA.match(sha) else None
    c = _num(raw.get("c"))
    out: dict[str, Any] = {"receipt_sha256": sha, "c": c if c is not None and 0.5 <= c <= 4.0 else None}
    for key in D2_RATES:
        v = _num(raw.get(key))
        out[key] = v if v is not None and 0.0 <= v <= 1.0 else None
    for key in D2_INTERVALS:
        pair = raw.get(key)
        lo, hi = (_num(pair[0]), _num(pair[1])) if isinstance(pair, (list, tuple)) and len(pair) == 2 else (None, None)
        out[key] = [lo, hi] if lo is not None and hi is not None and 0.0 <= lo <= hi <= 1.0 else None
    return out


def on(settings: Mapping[str, Any] | None) -> bool:
    """The lane is switched on (`dlane.mode` "shadow" or "gate"). False is THE ROLLBACK: every path as before D-1. Reads the
    settings alone (no store)."""
    return cfg(settings)["mode"] != "off"


def mode_effective(store: Any, settings: Mapping[str, Any] | None) -> str:
    """The lane's mode now: the setting's, except that a "gate" lane reads "shadow" while K5 holds (`k5_state`)."""
    mode = cfg(settings)["mode"]
    if mode == "gate" and k5_state(store, settings)["tripped"]:
        return "shadow"
    return mode


def candidates_open(store: Any, settings: Mapping[str, Any] | None) -> bool:
    """A direction family may become a Candidate (and the incubator take a direction mark): the effective mode is "gate"."""
    return mode_effective(store, settings) == "gate"


# ----------------------------------------------------------------------------------------------------------- K5
def _k5_base(store: Any) -> dict[str, Any]:
    """K5's re-arm base (kv `K5_BASE_KEY`): {net, at, trip, cleared}. `net` is the lane's realized net at the operator's
    last clear (0.0 before any: the line is then `k5_net_usd` itself), `trip` the trip not yet cleared ({at, net}, or
    None), `cleared` the last clear ({trip, how, at}, or None). A missing, malformed or unreadable base is the inception's.
    Never raises."""
    try:
        value = store.get(K5_BASE_KEY) if store is not None else None
    except Exception:  # noqa: BLE001 - an unreadable store: the inception's base
        value = None
    value = value if isinstance(value, Mapping) else {}
    trip = value.get("trip") if isinstance(value.get("trip"), Mapping) else None
    cleared = value.get("cleared") if isinstance(value.get("cleared"), Mapping) else None
    return {"net": _num(value.get("net")) or 0.0, "at": value.get("at"), "trip": dict(trip) if trip else None,
            "cleared": dict(cleared) if cleared else None}


def k5_line(store: Any, settings: Mapping[str, Any] | None) -> float:
    """K5's line now: `k5_net_usd` (-$600) below the net at the operator's last clear (`_k5_base`; 0.0 before any, so the
    first line is -$600 since the options swarm began)."""
    return round(_k5_base(store)["net"] + cfg(settings)["k5_net_usd"], 2)


def k5_state(store: Any, settings: Mapping[str, Any] | None) -> dict[str, Any]:
    """{tripped, at, net, cleared, set, line, base_net, trip_open, last_clear}: K5 holds (`tripped`) while the store's kv
    `K5_KEY` is `set` and swarm.json's `dlane.k5_clear` is not true (`cleared`; while it is, K5 can neither hold nor trip:
    `k5_trip`). `line` is the line a trip is judged by (`k5_line`), `base_net` the net it is measured from, `trip_open`
    a trip the job has not yet seen cleared (`k5_rearm`), `last_clear` the last clear it recorded. A kv that is set but
    malformed holds (fail-closed); a store that cannot be read holds nothing (it is read again on the next call). Never
    raises."""
    cleared = cfg(settings)["k5_clear"]
    try:
        value = store.get(K5_KEY) if store is not None else None
    except Exception:  # noqa: BLE001 - an unreadable store: nothing to hold yet
        value = None
    base = _k5_base(store)
    out = {"tripped": False, "at": None, "net": None, "cleared": cleared, "set": value is not None,
           "line": round(base["net"] + cfg(settings)["k5_net_usd"], 2), "base_net": base["net"],
           "trip_open": base["trip"] is not None, "last_clear": base["cleared"]}
    if value is None:
        return out
    at = value.get("at") if isinstance(value, Mapping) else None
    net = _num(value.get("net")) if isinstance(value, Mapping) else None
    return {**out, "tripped": not cleared, "at": at, "net": net}


def k5_trip(store: Any, settings: Mapping[str, Any] | None, net_usd: Any, *, at: str | None = None) -> bool:
    """K5 (decision 9), for the `dlane` report job: write the kv {at, net, line} when the direction lane's realized net over
    every route is at or below K5's line (`k5_line`: `k5_net_usd` below the net at the last clear), it is not set already
    and `dlane.k5_clear` is not true (while it is, K5 is disarmed: the report says so every run). The trip is also kept in
    the re-arm base (`trip`), so that the job sees it cleared however the operator clears it (`k5_rearm`). A trip the base
    holds open with no kv is a clear by hand that `k5_rearm` has not recorded yet: nothing is written then (the job
    records the clear first). True when this call wrote it. A tightening only: it never trades, and nothing here ever
    clears it."""
    c = cfg(settings)
    net = _num(net_usd)
    if net is None or c["k5_clear"] or getattr(store, "readonly", False):
        return False
    with store.atomic():
        line = k5_line(store, settings)
        if net > line or store.get(K5_KEY) is not None or _k5_base(store)["trip"] is not None:
            return False
        stamp = at or store.now()
        store.put(K5_KEY, {"at": stamp, "net": round(net, 2), "line": line})
        base = _k5_base(store)
        store.put(K5_BASE_KEY, {**base, "trip": {"at": stamp, "net": round(net, 2)}})
    return True


def k5_rearm(store: Any, settings: Mapping[str, Any] | None, net_usd: Any, *, at: str | None = None) -> dict[str, Any] | None:
    """THE OPERATOR'S CLEAR, MADE DURABLE (the review of release D-1, Oct 9, 2026), for the `dlane` job before `k5_trip`:
    when the operator has cleared a trip, by `dlane.k5_clear` true while the kv is set or by deleting the kv (a trip the
    base still holds open, `trip`, with no kv), the clear is recorded: the kv is deleted (so taking `k5_clear` out does
    not bring the old trip back) and the base becomes the lane's realized net now (`net_usd`; the trip's own net when it
    is unknown, which re-arms sooner), so K5's next line is `k5_net_usd` below the net at clearing. Without this, the net
    since inception never resets: a deleted kv was written again on the next run while the net stayed under -$600, and
    the only lasting clear was leaving `k5_clear` true, which disarmed K5 for every later loss. Returns the new base, or
    None when there is nothing to record (or the store is read-only). Never trades."""
    c = cfg(settings)
    if getattr(store, "readonly", False):
        return None
    with store.atomic():
        value = store.get(K5_KEY)
        base = _k5_base(store)
        if value is not None and c["k5_clear"]:
            how = "dlane.k5_clear"
            trip = ({"at": value.get("at"), "net": _num(value.get("net"))} if isinstance(value, Mapping)
                    else {"at": None, "net": None})
        elif value is None and base["trip"] is not None:
            how = "the kv deleted"
            trip = base["trip"]
        else:
            return None
        net = _num(net_usd)
        if net is None:
            net = _num(trip.get("net"))
        if net is None:
            net = base["net"]
        stamp = at or store.now()
        record = {"net": round(net, 2), "at": stamp, "trip": None, "cleared": {"trip": trip, "how": how, "at": stamp}}
        if value is not None:
            store._exec("DELETE FROM kv WHERE key=?", (K5_KEY,))
        store.put(K5_BASE_KEY, record)
    return record


# ----------------------------------------------------------------------------------------------------------- the lane
def lane_value(card: Any) -> tuple[str, str | None]:
    """(the lane a card or proposal declares, the problem with it or None). No lane is "alpha"."""
    raw = card.get("lane") if isinstance(card, Mapping) else None
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return ALPHA, None
    word = _token(raw)
    if word in LANES:
        return word, None
    return ALPHA, f"lane: {raw!r} is not one of {', '.join(LANES)}"


def declared_lane(store: Any, fam: Mapping[str, Any] | None) -> str:
    """The lane a family was born in, whatever the mode: its spec's `lane`, else its card's (a fork or a game child reads
    its parent's card through the spec's `card_sha`), else "alpha". Never raises."""
    if not isinstance(fam, Mapping):
        return ALPHA
    spec = fam.get("spec")
    if isinstance(spec, Mapping) and spec.get("lane") in LANES:
        return str(spec["lane"])
    fid = str(fam.get("id") or "")
    if not fid or store is None:
        return ALPHA
    try:
        from . import cards  # the cards module imports this one: read lazily

        row = cards.card_of(store, fid)
    except Exception:  # noqa: BLE001 - an unreadable card is no lane
        return ALPHA
    card = (row or {}).get("card") if isinstance(row, Mapping) else None
    return DIRECTION if isinstance(card, Mapping) and lane_value(card)[0] == DIRECTION else ALPHA


def lane_of(store: Any, fam: Mapping[str, Any] | None, settings: Mapping[str, Any] | None) -> str:
    """The lane a family is judged in NOW: "alpha" for every family while the lane is "off" (THE ROLLBACK, read from the
    settings alone, with no store read), else its declared lane (`declared_lane`)."""
    if not on(settings):
        return ALPHA
    return declared_lane(store, fam)


def card_errors(card: Any, structure: Any, roots: Any, settings: Mapping[str, Any] | None) -> list[str]:
    """Every reason a DIRECTION card is refused ([] for an alpha card, or a direction card inside the lane's box). `card` is
    the proposal's card (raw or canonical); `structure` and `roots` the proposal's. A malformed lane is refused too."""
    lane, problem = lane_value(card)
    if problem:
        return [problem]
    if lane != DIRECTION:
        return []
    c = cfg(settings)
    errors: list[str] = []
    if c["mode"] == "off":
        errors.append("lane: the direction lane is closed (dlane.mode is off); a card may only be alpha")
    cls = _token(card.get("mechanism_class"))
    if cls not in c["classes"]:
        errors.append(f"mechanism_class: a direction card is one of {', '.join(c['classes'])} ({card.get('mechanism_class')!r} given)")
    if str(structure or "") not in c["structures"]:
        errors.append(f"structure: a direction card is one of {', '.join(c['structures'])} ({structure!r} given); a direction "
                      "long_single buys calls only")
    names = [str(r).strip().upper() for r in roots] if isinstance(roots, (list, tuple)) else []
    outside = [r for r in names if r not in c["roots"]]
    if not names or outside:
        errors.append(f"roots: a direction card trades only {', '.join(c['roots'])}"
                      + (f" ({', '.join(outside)} given)" if outside else " (none given)"))
    holding = _token(card.get("holding"))
    if holding not in c["holding"]:
        errors.append(f"holding: a direction card holds {', '.join(c['holding'])} (2 to 8 sessions; {card.get('holding')!r} "
                      "given)")
    ablation = card.get("ablation")
    if ablation == "flat" or (isinstance(ablation, Mapping) and ablation.get("flat") is True):
        errors.append("ablation: a direction card's comparison is the same structure entered every session at the same "
                      "minute (a switch that turns its regime gate off), never flat")
    elif ablation is not None and not (isinstance(ablation, Mapping) and str(ablation.get("param") or "").strip()):
        errors.append("ablation: a direction card names the PARAMS switch that turns its regime gate off "
                      "({\"param\": ..., \"off\": ...})")
    return errors


# ----------------------------------------------------------------------------------------------------------- the years
def exposure(row: Mapping[str, Any] | None) -> float | None:
    """The exposure share of a drift year row: held days over days, or None without both (or no day)."""
    if not isinstance(row, Mapping):
        return None
    held, days = row.get("held_days"), row.get("days")
    if isinstance(held, bool) or isinstance(days, bool) or not isinstance(held, (int, float)) \
            or not isinstance(days, (int, float)) or days <= 0:
        return None
    return float(held) / float(days)


def _span(first_year: Any) -> tuple[int, int]:
    try:
        first = int(first_year) if first_year is not None else FIRST_YEAR
    except (TypeError, ValueError):
        first = FIRST_YEAR
    return max(FIRST_YEAR, first), LAST_YEAR


def year_rows(result: Mapping[str, Any], first_year: Any = None) -> dict[str, dict[str, Any]]:
    """The direction objective's per-year rows of a Train result (or of a run row rebuilt as one: `by_year` and the drift
    figures), for the Train years from `first_year` (never before `FIRST_YEAR`, never after `LAST_YEAR`):
    {year: {trades, days_traded, t_daily, pnl, days, held_days, sum_pp, t, exposure, figures}}. `pnl` is the drift row's
    (the year's daily account P&L; the by-year trade P&L only without it), `t` the all-days t of daily dollar P&L
    (`_t_of(pnl, sum_pp, days, sum_pp)`, the game's t_net), `figures` False when the drift row lacks what t and the
    exposure need (a run from before the figures). A count the result does not carry is None."""
    from ..gym.results import _t_of  # standard library only, like this module

    if not isinstance(result, Mapping):
        return {}
    lo, hi = _span(first_year)
    by = evidence.years_of(result)
    numbers = evidence.drift_numbers(result.get("drift"))
    drift = (numbers or {}).get("years") or {}
    out: dict[str, dict[str, Any]] = {}
    for y in sorted(set(by) | set(drift)):
        if not (y[:4].isdigit() and len(y) == 4 and lo <= int(y) <= hi):
            continue
        b = by.get(y) if isinstance(by.get(y), Mapping) else {}
        d = drift.get(y) if isinstance(drift.get(y), Mapping) else {}
        trades = b.get("trades")
        traded = b.get("days_traded")
        pnl, pp = _num(d.get("pnl")), _num(d.get("sum_pp"))
        days = d.get("days") if isinstance(d.get("days"), int) and not isinstance(d.get("days"), bool) else None
        held = _num(d.get("held_days"))
        figures = pnl is not None and pp is not None and days is not None and held is not None
        t = _num(_t_of(pnl, pp, days, pp)) if figures else None
        out[y] = {"trades": int(trades) if isinstance(trades, int) and not isinstance(trades, bool) else None,
                  "days_traded": int(traded) if isinstance(traded, int) and not isinstance(traded, bool) else None,
                  "t_daily": _num(b.get("t_daily")),
                  "pnl": pnl if pnl is not None else _num(b.get("pnl")),
                  "days": days, "held_days": held, "sum_pp": pp, "t": t,
                  "exposure": exposure(d) if figures else None, "figures": figures}
    return out


def _classify(rows: Mapping[str, Mapping[str, Any]], c: Mapping[str, Any]) -> dict[str, bool]:
    """ACTIVE (True) or OUT (False) for each year: at least `ACTIVE_MIN_TRADES` trades on `ACTIVE_MIN_DAYS` traded days and
    an exposure share of at least `active_share` of the busiest year's (which must have held something)."""
    top = max((r["exposure"] for r in rows.values() if r.get("exposure") is not None), default=0.0)
    out = {}
    for y, r in rows.items():
        x = r.get("exposure")
        out[y] = bool(top > 0 and x is not None and x >= c["active_share"] * top
                      and (r.get("trades") or 0) >= ACTIVE_MIN_TRADES and (r.get("days_traded") or 0) >= ACTIVE_MIN_DAYS)
    return out


def _e3(rows: Mapping[str, Mapping[str, Any]], active: Mapping[str, bool], c: Mapping[str, Any]) -> tuple[bool, str | None]:
    """E3 on one run's rows: (holds, why not). The mean is over the run's own ACTIVE years (0 without one)."""
    act = [rows[y]["pnl"] or 0.0 for y in rows if active.get(y)]
    mean = sum(act) / len(act) if act else 0.0
    floor = -c["out_loss_share"] * mean
    for y, r in rows.items():
        if active.get(y):
            continue
        t = r.get("t") if r.get("t") is not None else 0.0  # no variance: a flat year
        pnl = r.get("pnl") or 0.0
        if t < c["out_t_floor"]:
            return False, f"{y} is out of the market and its t is {t:.2f}, below {c['out_t_floor']:g}"
        if pnl < floor:
            return False, (f"{y} is out of the market and lost {_usd(pnl)}, more than {c['out_loss_share']:g} of the "
                           f"in-market years' mean P&L ({_usd(mean)}) allows")
    return True, None


def _pooled_t(rows: Mapping[str, Mapping[str, Any]]) -> float | None:
    from ..gym.results import _t_of  # standard library only, like this module

    if not rows or any(not r.get("figures") for r in rows.values()):
        return None
    total = sum(r["pnl"] for r in rows.values())
    pp = sum(r["sum_pp"] for r in rows.values())
    days = sum(int(r["days"]) for r in rows.values())
    return _num(_t_of(total, pp, days, pp))


def _usd(x: Any) -> str:
    """Whole dollars with a thousands comma (so a figure never reads as a year)."""
    v = _num(x)
    if v is None:
        return "n/a"
    return f"-${abs(v):,.0f}" if v < 0 else f"${v:,.0f}"


# ----------------------------------------------------------------------------------------------------------- the unit
def unit_context(where: Any, settings: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """THE UNIT's live context (E5; decision 3), read from the House's state directory (`where`: a swarm store, whose root
    it is, or a path): {known, closes, close_day, scale, equity_usd, cap_usd, pref_usd, why}.

    - closes: each lane root's last split-adjusted close in `CLOSES_FILE` (the House's `direction` job, daily); scale its
      ratio to `TRAIN_CLOSE_2024`;
    - equity_usd: the lower of the start-of-day equity and the latest reading the live path's stops last wrote to
      `HEALTH_FILE` (`options_live.stops.sod_equity`, `options_live.stops.last_reading[1]`); the live cap is a share of the
      sizing equity, which is never above the account's;
    - cap_usd: `unit_cap_usd` when set (never above `unit_share` x equity when that is known), else `unit_share` x equity.
    `known` is False, and `why` says which, when a close or the equity is missing: E5 then reads "unknown" and passes, and
    the live path prices every real open again. Never raises."""
    c = cfg(settings)
    out: dict[str, Any] = {"known": False, "closes": {}, "close_day": {}, "scale": {}, "equity_usd": None, "cap_usd": None,
                           "pref_usd": c["unit_pref_usd"], "why": None}
    try:
        root = Path(where) if isinstance(where, (str, Path)) else Path(getattr(where, "root"))
    except (TypeError, AttributeError):
        out["why"] = "no state directory"
        return out
    whys = []
    try:
        doc = json.loads((root / CLOSES_FILE).read_text(encoding="utf-8"))
        closes = doc.get("closes") if isinstance(doc, Mapping) else None
        for r in ROOTS:
            rows = closes.get(r) if isinstance(closes, Mapping) else None
            if not isinstance(rows, Mapping):
                continue
            good = [(str(d), _num(v)) for d, v in rows.items() if _num(v) is not None and _num(v) > 0]
            if good:
                day, close = max(good)
                out["closes"][r], out["close_day"][r] = close, day
                out["scale"][r] = close / TRAIN_CLOSE_2024[r]
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    if not out["scale"]:
        whys.append(f"no index close in {CLOSES_FILE}")
    try:
        doc = json.loads((root / HEALTH_FILE).read_text(encoding="utf-8"))
        stops = ((doc.get("options_live") or {}).get("stops") or {}) if isinstance(doc, Mapping) else {}
        readings = []
        if isinstance(stops, Mapping):
            readings.append(_reading(stops.get("sod_equity")))
            last = stops.get("last_reading")
            if isinstance(last, (list, tuple)) and len(last) >= 2:
                readings.append(_reading(last[1]))
        readings = [x for x in readings if x is not None and x > 0]
        if readings:
            out["equity_usd"] = min(readings)
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    share_cap = None if out["equity_usd"] is None else round(c["unit_share"] * out["equity_usd"], 2)
    if c["unit_cap_usd"] is not None:
        out["cap_usd"] = c["unit_cap_usd"] if share_cap is None else min(c["unit_cap_usd"], share_cap)
    else:
        out["cap_usd"] = share_cap
    if out["cap_usd"] is None:
        whys.append(f"no account equity in {HEALTH_FILE}")
    out["known"] = bool(out["scale"]) and out["cap_usd"] is not None
    out["why"] = "; ".join(whys) or None
    return out


def _reading(value: Any) -> float | None:
    """A money figure as the live path writes it (a decimal string or a number), or None."""
    if isinstance(value, str):
        try:
            value = float(value)
        except ValueError:
            return None
    return _num(value)


def _median(xs: Sequence[float]) -> float | None:
    xs = sorted(xs)
    k = len(xs)
    if not k:
        return None
    return xs[k // 2] if k % 2 else 0.5 * (xs[k // 2 - 1] + xs[k // 2])


def unit_of(result: Mapping[str, Any], unit: Mapping[str, Any] | None, *, median_2024_usd: Any = None,
            n_2024: Any = None, roots: Iterable[str] | None = None) -> dict[str, Any]:
    """E5 on a Train result: {median_2024_usd, n_2024, roots, scale, scaled_usd, cap_usd, verdict, why}. The median one-lot
    maximum loss with fees ((max_loss + fees) / qty) of its trades entered in 2024, times the largest price scale over the
    roots those trades were in (`unit_context`). A run row whose trades were pruned passes its stored `median_2024_usd`,
    `n_2024` and `roots` instead (`lane_verdict`). verdict "pass", "fail", or "unknown" (no 2024 trade, a root without a
    close, or no cap), which passes. `scale`, `scaled_usd` and `cap_usd` are today's figures: kept for the code, the
    family state (`record`) and the operator's report, never shown to an agent (`UNIT_HINT`); `why` names no figure."""
    if median_2024_usd is None:
        per, traded = [], set()
        for t in (result.get("trades") or []) if isinstance(result, Mapping) else []:
            if not isinstance(t, Mapping) or str(t.get("day") or "")[:4] != str(LAST_YEAR):
                continue
            loss, fees = _num(t.get("max_loss")), _num(t.get("fees")) or 0.0
            qty = t.get("qty") if isinstance(t.get("qty"), int) and not isinstance(t.get("qty"), bool) else 1
            if loss is None or loss <= 0:
                continue
            per.append((loss + fees) / max(1, qty))
            if t.get("root"):
                traded.add(str(t["root"]).upper())
        median, n = _median(per), len(per)
        roots = sorted(traded) if traded else sorted({str(r).upper() for r in (result.get("roots") or [])}) \
            if isinstance(result, Mapping) else []
    else:
        median, n = _num(median_2024_usd), int(n_2024 or 0)
        roots = sorted({str(r).upper() for r in (roots or [])})
    out: dict[str, Any] = {"median_2024_usd": None if median is None else round(median, 2), "n_2024": n, "roots": list(roots),
                           "scale": None, "scaled_usd": None, "cap_usd": None, "verdict": "unknown", "why": None}
    unit = unit if isinstance(unit, Mapping) else {}
    out["cap_usd"] = _num(unit.get("cap_usd"))
    scales = unit.get("scale") if isinstance(unit.get("scale"), Mapping) else {}
    if median is None:
        out["why"] = f"no {LAST_YEAR} trade to price"
        return out
    if not roots or any(r not in scales for r in roots):
        out["why"] = "no live close for " + (", ".join(r for r in roots if r not in scales) or "its roots")
        return out
    out["scale"] = round(max(float(scales[r]) for r in roots), 6)
    out["scaled_usd"] = round(median * out["scale"], 2)
    if out["cap_usd"] is None:
        out["why"] = "no live unit cap (the account's equity is unknown)"
        return out
    if out["scaled_usd"] <= out["cap_usd"]:
        out["verdict"] = "pass"
    else:
        out["verdict"] = "fail"
        # Figure-free (`UNIT_HINT`): this `why` reaches the agents (a score's `why`, a sweep row, a view, a status line).
        out["why"] = f"one lot's maximum loss with fees at today's index prices is over the unit cap: {UNIT_HINT}"
    return out


# ----------------------------------------------------------------------------------------------------------- the bar
def train_score(result: Mapping[str, Any], *, first_year: Any = None, unit: Mapping[str, Any] | None = None,
                settings: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """THE DIRECTION OBJECTIVE, direction-v2 (the module docstring), on a Train run at 1.0x:
    {objective, score, eligible, why, fails, t_pool, pnl, years, active, worst_year, quarters, unit, reported, beside}.

    score = S_D, the pooled t of daily P&L over the Train years (set whenever it can be computed, eligible or not);
    eligible = C1 (calls only, release D-1b: `calls_only`), E1, E3, E4 and E5 hold (E5 "unknown" and C1 unread hold) and
    S_D exists; `fails` names the failing bars in order and `why` the first. `years` {year: {active, t, exposure, pnl, trades, days_traded, entry_days, t_daily}}; `reported` E2
    (every ACTIVE year t >= 0; never a bar) and R1 (None until `robust_verdict`); `beside` the drift figures (beta per 1%
    move, drift share, drift-adjusted alpha t, the same exposure held every session). `worst_year` (the lowest-t ACTIVE
    year) and `quarters` keep the shape the researcher's view reads from `evidence.train_score`. `unit` is
    `unit_context`'s (None: E5 "unknown")."""
    c = cfg(settings)
    summary = result.get("summary") if isinstance(result, Mapping) and isinstance(result.get("summary"), Mapping) else {}
    k, n = evidence.quarters_positive(summary)
    out: dict[str, Any] = {"objective": OBJECTIVE, "score": None, "eligible": False, "why": None, "fails": [], "t_pool": None,
                           "pnl": None, "years": {}, "active": [], "worst_year": None, "quarters": f"{k}/{n}",
                           "unit": unit_of(result, unit) if isinstance(result, Mapping) else unit_of({}, unit),
                           "reported": {"E2": None, "R1": None}, "beside": {}}
    if not isinstance(result, Mapping) or result.get("status") != "ok":
        out["why"] = "no completed Train run"
        return out
    rows = year_rows(result, first_year)
    if not rows:
        out["why"] = "no Train year in the run"
        return out
    if any(not r["figures"] for r in rows.values()):
        out["why"] = "its Train run predates the daily figures the direction objective reads: it is run again"
        return out
    active = _classify(rows, c)
    out["active"] = [y for y in sorted(rows) if active[y]]
    out["years"] = {y: {"active": active[y], "t": None if r["t"] is None else round(r["t"], 4),
                        "exposure": None if r["exposure"] is None else round(r["exposure"], 4),
                        "pnl": None if r["pnl"] is None else round(r["pnl"], 2), "trades": r["trades"],
                        "days_traded": r["days_traded"], "entry_days": r["days_traded"], "t_daily": r["t_daily"]}
                    for y, r in sorted(rows.items())}
    t_pool = _pooled_t(rows)
    out["t_pool"] = None if t_pool is None else round(t_pool, 6)
    out["score"] = out["t_pool"]
    out["pnl"] = round(sum(r["pnl"] for r in rows.values()), 2)
    ts = {y: rows[y]["t"] for y in out["active"]}
    if ts:
        out["worst_year"] = min(ts, key=lambda y: (ts[y] if ts[y] is not None else -math.inf, y))
        out["reported"]["E2"] = all(t is not None and t >= 0 for t in ts.values())
    else:
        out["reported"]["E2"] = False
    out["beside"] = beside(result, first_year)
    whys: list[tuple[str, str]] = []
    if calls_only(result, first_year) is False:
        whys.append(("C1", CALLS_ONLY_WHY))
    if len(out["active"]) < c["min_active_years"]:
        whys.append(("E1", f"it is in the market in {len(out['active'])} of {len(rows)} Train years; the lane needs "
                           f"{c['min_active_years']} (in the market: {ACTIVE_MIN_TRADES}+ trades on {ACTIVE_MIN_DAYS}+ days and "
                           f"at least {c['active_share']:.0%} of its busiest year's exposure)"))
    ok, why = _e3(rows, active, c)
    if not ok:
        whys.append(("E3", str(why)))
    short = [y for y in out["active"] if (rows[y]["days_traded"] or 0) < c["min_entry_days"]]
    if short:
        y = short[0]
        whys.append(("E4", f"{y} is in the market with {rows[y]['days_traded'] or 0} entry sessions; every in-market year "
                           f"needs {c['min_entry_days']}"))
    if out["unit"]["verdict"] == "fail":
        whys.append(("E5", str(out["unit"]["why"])))
    out["fails"] = [rule for rule, _ in whys]
    if whys:
        out["why"] = f"fails {whys[0][0]}: {whys[0][1]}"
    elif t_pool is None:
        out["why"] = "its pooled daily t cannot be computed (no variance)"
    else:
        out["eligible"] = True
    return out


#: C1's words (release D-1b): rules only, no figure.
CALLS_ONLY_WHY = "the direction lane buys calls only: a Train trade held a put or a short leg"


def calls_only(result: Mapping[str, Any] | None, first_year: Any = None) -> bool | None:
    """THE CALLS-ONLY BAR, C1 (release D-1b, Oct 9, 2026): D2 was measured on long calls, and a `long_single` card may send
    a put by its code, so a direction program whose Train trades (2022-24: `_span`) include a leg that is not a long call
    (`right` "C", `side` "long", as the Gym writes each trade's legs) fails it. True when every leg read is a long call,
    None when nothing can be read (no trade list, no Train-year trade, or no legs written: a stored score or a fixture),
    which is no failure."""
    trades = result.get("trades") if isinstance(result, Mapping) else None
    if not isinstance(trades, list):
        return None
    lo, hi = _span(first_year)
    seen = False
    for trade in trades:
        if not isinstance(trade, Mapping):
            continue
        year = str(trade.get("day") or "")[:4]
        legs = trade.get("legs")
        if not (year.isdigit() and lo <= int(year) <= hi) or not isinstance(legs, list) or not legs:
            continue
        for leg in legs:
            if not isinstance(leg, Mapping) or leg.get("right") != "C" or leg.get("side") != "long":
                return False
        seen = True
    return True if seen else None


#: THE CALLS-ONLY CODE CHECK's words (release D-1b, the review's finding 3): rules only, no figure.
CALLS_ONLY_CODE_WHY = ("the direction lane buys calls only: a direction program names no structure but long_call, no put "
                       "and no short leg")
#: The literals a direction program may not hold (`calls_only_code`), lower case: a put, a short leg; the structure types
#: other than `long_call` are read from the Gym's own list (league/gym/venue.py `STRUCTURE_TYPES`) when it is checked.
_NOT_A_CALL = ("p", "put", "short")


def _literals(code: str) -> list[str]:
    """The string literals of a program's code that it could open with: every one but a docstring (a string standing alone
    as a statement), a dict key and a subscript (`ctx.params["p"]`: a name, never an order's field value)."""
    import ast

    tree = ast.parse(code)
    skip: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            skip.add(id(node.value))
        elif isinstance(node, ast.Dict):
            skip.update(id(k) for k in node.keys if k is not None)
        elif isinstance(node, ast.Subscript):
            skip.add(id(node.slice))
    return [node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in skip]


def _param_strings(value: Any) -> list[str]:
    """The string values of a parameter override, at any depth (keys are names, never values)."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        return [s for v in value.values() for s in _param_strings(v)]
    if isinstance(value, (list, tuple)):
        return [s for v in value for s in _param_strings(v)]
    return []


def calls_only_code(code: Any, params: Mapping[str, Any] | None = None) -> str | None:
    """THE CALLS-ONLY CODE CHECK (release D-1b, Oct 9, 2026; the review's finding 3). C1 reads the Train trades only, and
    the Gym's Validation and holdout views carry no trades, so a `long_single` program whose code buys a put only in
    conditions absent from 2022-24 (a crash hedge when VIX is above any 2022-24 close) passes C1 and would send puts at
    Probe, where D2's rates were measured on long calls. This static check reads the program's text before any version,
    job or look: a string literal of its code (`_literals`: docstrings, dict keys and subscripts aside) or of its parameter
    overrides that names an open of any structure type but `long_call`, a put ("P", "put") or a short leg ("short"),
    whatever its case, refuses it. Why that suffices for a literal: a `long_call` open is ONE LONG CALL wherever the Gym's
    classifier judges it, and the live path resolves an intent with the same module (league/gym/legs.py `classify`), so a
    program that names no other type opens nothing else. What it cannot see: a type assembled at run time from pieces that
    are not these words, and the live path has no direction calls-only check of its own (release L-D; league/live is
    frozen here): docs/operations.md states both. Returns the refusal's words (`CALLS_ONLY_CODE_WHY` and the literal it
    found), or None. Code that does not parse is None here (`check_experiment` refuses it first)."""
    from ..gym.venue import STRUCTURE_TYPES

    banned = set(_NOT_A_CALL) | {t for t in STRUCTURE_TYPES if t != "long_call"}
    try:
        words = _literals(str(code or ""))
    except (SyntaxError, ValueError):
        return None
    words += _param_strings(dict(params or {}))
    for word in words:
        if word.strip().lower() in banned:
            return f"{CALLS_ONLY_CODE_WHY} (it names {word.strip()!r})"
    return None


def beside(result: Mapping[str, Any], first_year: Any = None) -> dict[str, Any]:
    """The drift figures reported beside a direction score, never a bar: {beta_per_1pct (dollars per 1% move of the held
    roots), drift_share, alpha_t (the drift-adjusted alpha's pooled t), always_in_usd (the same exposure held every
    session: the sum over the years of each year's beta times its roots' mean return over the year, when the result
    carries the drift statistics; else None)}, over the Train years from `first_year` (never before `FIRST_YEAR`)."""
    lo, _ = _span(first_year)
    numbers = evidence.drift_numbers(result.get("drift")) if isinstance(result, Mapping) else None
    out: dict[str, Any] = {"beta_per_1pct": None, "drift_share": None, "alpha_t": None, "always_in_usd": None}
    if numbers is None:
        return out
    # `first_year` leaves out every older year AND re-pools the rest (`evidence.drift_years`), so an older year a result
    # carries never reaches the pooled figures.
    lean = evidence.drift_lean(numbers, first_year=lo)
    screen = evidence.drift_screen(numbers, first_year=lo)
    if lean.get("beta") is not None:
        out["beta_per_1pct"] = round(float(lean["beta"]) * 0.01, 2)
    if lean.get("share") is not None:
        out["drift_share"] = round(float(lean["share"]), 4)
    if screen.get("t") is not None:
        out["alpha_t"] = round(float(screen["t"]), 4)
    block = result.get("drift") if isinstance(result.get("drift"), Mapping) else {}
    total, seen = 0.0, False
    for y, row in (block.get("years") or {}).items():
        if not (str(y)[:4].isdigit() and lo <= int(str(y)[:4]) <= LAST_YEAR) or not isinstance(row, Mapping):
            continue
        st = row.get("stats")
        beta = _num(row.get("beta"))
        roots = (st or {}).get("roots") if isinstance(st, Mapping) else None
        if beta is None or not isinstance(roots, Mapping) or not roots:
            return out
        rets = [float(acc[1]) + float(acc[2]) for acc in roots.values() if isinstance(acc, (list, tuple)) and len(acc) >= 3]
        if not rets:
            return out
        total += beta * sum(rets) / len(rets)
        seen = True
    out["always_in_usd"] = round(total, 2) if seen else None
    return out


def robust_verdict(base: Mapping[str, Any] | None, result_15: Mapping[str, Any], *, first_year: Any = None,
                   settings: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """THE 1.5x RULES of direction-v2 on version n's 1.5x Train run, against its 1.0x score `base` (`train_score`):
    {objective, known, passed, why, fails, checks: {P1, R2, R3}, t_pool_15, pnl_15, pnl_10, ratio, reported: {R1}, years}.

    P1 the run's P&L above zero (its summary's `pnl`, the House's existing rule); R2 E1 and E3 at 1.5x (a year's trade
    and entry-day counts the 1.5x run does not carry are the 1.0x run's: the same program); R3 the 1.5x P&L summed over
    the Train years at least `cost_ratio` x the 1.0x's. R1 (the pooled t at 1.5x against `c_train`) is reported, never a
    bar. `known` is False when the run did not complete or lacks the figures, or there is no 1.0x score: nothing to
    demote on (the run is owed again), and `passed` is False."""
    c = cfg(settings)
    out: dict[str, Any] = {"objective": OBJECTIVE, "known": False, "passed": False, "why": None, "fails": [],
                           "checks": {"P1": None, "R2": None, "R3": None}, "t_pool_15": None, "pnl_15": None,
                           "pnl_10": None, "ratio": None, "reported": {"R1": None}, "years": {}}
    if not isinstance(result_15, Mapping) or result_15.get("status") != "ok":
        out["why"] = "its 1.5x Train run did not complete"
        return out
    rows = year_rows(result_15, first_year)
    base_years = (base or {}).get("years") if isinstance(base, Mapping) else None
    base_years = base_years if isinstance(base_years, Mapping) else {}
    for y, r in rows.items():
        b = base_years.get(y) if isinstance(base_years.get(y), Mapping) else {}
        if r["trades"] is None:
            r["trades"] = b.get("trades")
        if r["days_traded"] is None:
            r["days_traded"] = b.get("days_traded")
    if not rows or any(not r["figures"] for r in rows.values()):
        out["why"] = "its 1.5x Train run lacks the daily figures the direction objective reads"
        return out
    summary = result_15.get("summary") if isinstance(result_15.get("summary"), Mapping) else {}
    pnl_run = _num(summary.get("pnl"))
    pnl_15 = sum(r["pnl"] for r in rows.values())
    out["pnl_15"] = round(pnl_15, 2)
    t15 = _pooled_t(rows)
    out["t_pool_15"] = None if t15 is None else round(t15, 6)
    out["reported"]["R1"] = t15 is not None and t15 >= c["c_train"]
    active = _classify(rows, c)
    out["years"] = {y: {"active": active[y], "t": None if r["t"] is None else round(r["t"], 4),
                        "exposure": None if r["exposure"] is None else round(r["exposure"], 4),
                        "pnl": round(r["pnl"], 2)} for y, r in sorted(rows.items())}
    whys: list[tuple[str, str]] = []
    p1 = (pnl_run if pnl_run is not None else pnl_15) > 0
    out["checks"]["P1"] = p1
    if not p1:
        whys.append(("P1", f"it lost money on Train at 1.5x the half-spread ({_usd(pnl_run if pnl_run is not None else pnl_15)})"))
    n_active = sum(1 for v in active.values() if v)
    e3, e3_why = _e3(rows, active, c)
    r2 = n_active >= c["min_active_years"] and e3
    out["checks"]["R2"] = r2
    if not r2:
        whys.append(("R2", f"at 1.5x it is in the market in {n_active} Train years (needs {c['min_active_years']})"
                           if n_active < c["min_active_years"] else f"at 1.5x {e3_why}"))
    pnl_10 = _num((base or {}).get("pnl")) if isinstance(base, Mapping) else None
    out["pnl_10"] = pnl_10
    if pnl_10 is None:
        out["why"] = "no 1.0x direction score to compare its 1.5x run with"
        out["fails"] = [rule for rule, _ in whys]
        return out
    out["known"] = True
    out["ratio"] = round(pnl_15 / pnl_10, 4) if pnl_10 > 0 else None
    r3 = pnl_15 >= c["cost_ratio"] * pnl_10
    out["checks"]["R3"] = r3
    if not r3:
        whys.append(("R3", f"its 1.5x P&L ({_usd(pnl_15)}) is under {c['cost_ratio']:g} of its 1.0x P&L ({_usd(pnl_10)})"))
    out["fails"] = [rule for rule, _ in whys]
    if whys:
        out["why"] = f"fails {whys[0][0]}: {whys[0][1]}"
    else:
        out["passed"] = True
    return out


def sort_key(score: Mapping[str, Any] | None) -> float:
    """A direction family's place in a sweep table or a ranking: S_D, minus infinity without one."""
    v = _num((score or {}).get("score")) if isinstance(score, Mapping) else None
    return -math.inf if v is None else v


# ----------------------------------------------------------------------------------------------------------- records
def compact(score: Mapping[str, Any] | None, *, priced: bool = False) -> dict[str, Any] | None:
    """A direction score as a run row's summary or the family state keeps it (no per-trade data): {objective, score,
    eligible, fails, why, pnl, active, years, unit, reported}. Its `unit` keeps the 2024 facts E5 is re-priced from
    (`median_2024_usd`, `n_2024`, `roots`) and the verdict; today's figures (`scaled_usd`, `cap_usd`) only with `priced`
    (the family state, `record`, which the operator's report reads): a run row's summary is not, because a researcher
    reads it back (`read_run` of a pruned run) and no agent sees a figure priced today (`UNIT_HINT`)."""
    if not isinstance(score, Mapping):
        return None
    unit = score.get("unit") if isinstance(score.get("unit"), Mapping) else {}
    keys = ("median_2024_usd", "n_2024", "roots", "scaled_usd", "cap_usd", "verdict") if priced else \
        ("median_2024_usd", "n_2024", "roots", "verdict")
    return {"objective": score.get("objective", OBJECTIVE), "score": score.get("score"),
            "eligible": bool(score.get("eligible")), "fails": list(score.get("fails") or []), "why": score.get("why"),
            "pnl": score.get("pnl"), "active": list(score.get("active") or []),
            "years": {y: {k: r.get(k) for k in ("active", "t", "exposure", "pnl", "trades", "days_traded")}
                      for y, r in (score.get("years") or {}).items() if isinstance(r, Mapping)},
            "unit": {k: unit.get(k) for k in keys}, "reported": dict(score.get("reported") or {})}


def compact_robust(robust: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(robust, Mapping):
        return None
    return {"known": bool(robust.get("known")), "passed": bool(robust.get("passed")), "fails": list(robust.get("fails") or []),
            "why": robust.get("why"), "t_pool_15": robust.get("t_pool_15"), "pnl_15": robust.get("pnl_15"),
            "ratio": robust.get("ratio"), "reported": dict(robust.get("reported") or {})}


def record(store: Any, fid: str, n: int, *, score: Mapping[str, Any] | None = None,
           robust: Mapping[str, Any] | None = None) -> None:
    """Keep version `n`'s direction verdicts in the family's state (`STATE_KEY`: {objective, versions: {n: {at, train,
    robust}}}, the newest `VERSIONS_KEPT`): what `failure_counts` (the architect's and the strategist's counts, the report's
    A6 and A7) reads. The researcher calls it when a 1.0x score or a 1.5x verdict lands."""
    if score is None and robust is None:
        return
    with store.atomic():
        fam = store.family(fid)
        if fam is None:
            return
        block = (fam.get("state") or {}).get(STATE_KEY)
        versions = dict((block or {}).get("versions") or {}) if isinstance(block, Mapping) else {}
        row = dict(versions.get(str(int(n))) or {})
        if score is not None:
            row["train"] = compact(score, priced=True)  # today's unit figures too: the operator's report (A7) reads them
        if robust is not None:
            row["robust"] = compact_robust(robust)
        row["at"] = store.now()
        versions[str(int(n))] = row
        keep = sorted((k for k in versions if str(k).isdigit()), key=int)[-VERSIONS_KEPT:]
        store.set_state(fid, **{STATE_KEY: {"objective": OBJECTIVE, "versions": {k: versions[k] for k in keep}}})


def failure_counts(store: Any, hours: float = 48.0, *, now: float | None = None,
                   exclude: Iterable[str] = ()) -> dict[str, Any]:
    """The direction lane's failure counts over the last `hours`: ids and counts only, never a figure (for the architect's
    request, the strategist's inputs and the report's A6/A7). {hours, families, versions, eligible, fails {E1, E3, E4, E5},
    robust {P1, R2, R3}, robust_passed, reported_misses {E2, R1}, unit_only, ids}. A version counts once, by its newest
    verdicts recorded in the window (`record`). `exclude`: families left out (the architect's and the strategist's
    `Architect.unseen`, THE LEARNING GAME's: a count never moves with the game arm). Never raises: {} figures on a store
    error."""
    from .store import iso, loads

    now = time.time() if now is None else float(now)
    since = iso(now - float(hours) * 3600.0)
    out: dict[str, Any] = {"hours": float(hours), "families": 0, "versions": 0, "eligible": 0,
                           "fails": {"E1": 0, "E3": 0, "E4": 0, "E5": 0}, "robust": {"P1": 0, "R2": 0, "R3": 0},
                           "robust_passed": 0, "reported_misses": {"E2": 0, "R1": 0}, "unit_only": 0, "ids": []}
    try:
        rows = store._all("SELECT id, state FROM families WHERE retired_at IS NULL OR retired_at>=?", (since,))
    except Exception:  # noqa: BLE001
        return out
    ids = []
    skip = frozenset(str(x) for x in exclude)
    for row in rows:
        if str(row.get("id")) in skip:
            continue
        state = loads(row.get("state"), {}) or {}
        block = state.get(STATE_KEY) if isinstance(state, Mapping) else None
        versions = block.get("versions") if isinstance(block, Mapping) else None
        if not isinstance(versions, Mapping):
            continue
        counted = False
        for v in versions.values():
            if not isinstance(v, Mapping) or str(v.get("at") or "") < since:
                continue
            counted = True
            out["versions"] += 1
            train = v.get("train") if isinstance(v.get("train"), Mapping) else {}
            fails = [f for f in train.get("fails") or [] if f in out["fails"]]
            for f in fails:
                out["fails"][f] += 1
            if train.get("eligible"):
                out["eligible"] += 1
            if list(train.get("fails") or []) == ["E5"]:  # E5 alone (a C1 failure beside it is not the unit only)
                out["unit_only"] += 1
            if (train.get("reported") or {}).get("E2") is False:
                out["reported_misses"]["E2"] += 1
            rob = v.get("robust") if isinstance(v.get("robust"), Mapping) else {}
            for f in rob.get("fails") or []:
                if f in out["robust"]:
                    out["robust"][f] += 1
            if rob.get("passed"):
                out["robust_passed"] += 1
            if (rob.get("reported") or {}).get("R1") is False:
                out["reported_misses"]["R1"] += 1
        if counted:
            ids.append(str(row["id"]))
    out["families"] = len(ids)
    out["ids"] = sorted(ids)[:40]
    return out


def lane_verdict(store: Any, fam: Mapping[str, Any], n: Any, settings: Mapping[str, Any] | None, *,
                 run: Mapping[str, Any] | None = None, unit: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """THE INCUBATOR'S DIRECTION MARK (D5; in place of the drift screen for a direction family): direction-v2 on version
    `n`, the 1.0x bars on its eligible Train run (`run`, the incubator's `eligible_train_run`; else the newest completed
    1.0x Train row) and the 1.5x rules on its newest completed 1.5x Train row. {known, passed, drop, why, score, robust}
    (`score` and `robust` compact). A full result is read when the store still keeps it (E5 priced at today's closes);
    else the row's stored compact score (its `dlane` summary key, E5 re-priced from its stored median) and, for the 1.5x
    run, the row's drift figures with the family state's robustness view. `known` False (figures owed, never a reason to
    drop a mark) when a run or its figures are missing; `drop` True when a known bar failed for good (E1, E3, E4 or a
    1.5x rule: the same program fails them again; an E5 failure is today's prices', so it never drops). Never raises."""
    out: dict[str, Any] = {"known": False, "passed": False, "drop": False, "why": None, "score": None, "robust": None,
                           "lane": DIRECTION, "objective": OBJECTIVE}
    try:
        fid = str(fam["id"])
        n = int(n)
        unit = unit if unit is not None else unit_context(store, settings)
        if run is None:
            rows = [r for r in store.version_runs(fid, n, window="train", stress=1.0, limit=20) if r.get("status") == "ok"]
            run = rows[0] if rows else None
        if not isinstance(run, Mapping):
            out["why"] = "no completed Train run"
            return out
        summary = run.get("summary") if isinstance(run.get("summary"), Mapping) else {}
        span = str(summary.get("train_from") or "")
        first_year = int(span[:4]) if span[:4].isdigit() else FIRST_YEAR
        full = store.run_result(run["run_id"]) if run.get("run_id") else None
        if isinstance(full, Mapping):
            score = train_score(full, first_year=first_year, unit=unit, settings=settings)
        else:
            stored = summary.get(STATE_KEY)
            score = _score_from_compact(stored, unit, settings)
            if score is None:
                out["why"] = "its direction figures are owed (the run's full result was pruned before they were kept)"
                return out
        out["score"] = compact(score)
        if not score["eligible"]:
            out["why"] = score["why"]
            out["known"] = score["score"] is not None or bool(score["fails"])
            out["drop"] = out["known"] and any(f != "E5" for f in score["fails"])
            return out
        rows15 = [r for r in store.version_runs(fid, n, window="train", stress=1.5, limit=10) if r.get("status") == "ok"]
        if not rows15:
            out["why"] = "its 1.5x Train run has not landed"
            return out
        full15 = store.run_result(rows15[0]["run_id"]) if rows15[0].get("run_id") else None
        if not isinstance(full15, Mapping):
            view = (((fam.get("state") or {}).get("robustness") or {}).get(str(n)) or {}).get("stress_1.5") or {}
            summary = rows15[0].get("summary") or {}
            full15 = {"status": "ok", "summary": {"pnl": summary.get("pnl", view.get("pnl"))},
                      "drift": summary.get("drift"),
                      "by_year": {y: {"trades": r.get("trades"), "pnl": r.get("pnl"), "t_daily": r.get("t_daily")}
                                  for y, r in (view.get("by_year") or {}).items() if isinstance(r, Mapping)}}
        robust = robust_verdict(score, full15, first_year=first_year, settings=settings)
        out["robust"] = compact_robust(robust)
        if not robust["known"]:
            out["why"] = robust["why"]
            return out
        out["known"] = True
        out["passed"] = bool(robust["passed"])
        out["drop"] = not robust["passed"]
        out["why"] = robust["why"]
        return out
    except Exception as exc:  # noqa: BLE001 - a mark is never written on an error, nor dropped
        out.update(known=False, passed=False, drop=False, why=f"the direction figures could not be read ({type(exc).__name__})")
        return out


def _score_from_compact(stored: Any, unit: Mapping[str, Any] | None, settings: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """A full-shaped direction score rebuilt from a run row's stored compact one (`compact`), E5 re-priced at today's
    context; None when there is none."""
    if not isinstance(stored, Mapping) or stored.get("objective") != OBJECTIVE:
        return None
    u = stored.get("unit") if isinstance(stored.get("unit"), Mapping) else {}
    if u.get("median_2024_usd") is None:
        priced = unit_of({}, unit)  # nothing to price: "unknown"
    else:
        priced = unit_of({}, unit, median_2024_usd=u.get("median_2024_usd"), n_2024=u.get("n_2024"),
                         roots=u.get("roots") or [])
    # E1, E3 and E4 are the program's, as stored; E5 is today's (it is the last in order, so a stored `why` that names
    # another bar still names the first failing one).
    kept = [f for f in stored.get("fails") or [] if f != "E5"]
    fails = kept + (["E5"] if priced["verdict"] == "fail" else [])
    score = {**dict(stored), "unit": priced, "fails": fails,
             "years": {y: dict(r) for y, r in (stored.get("years") or {}).items() if isinstance(r, Mapping)}}
    score["eligible"] = not fails and stored.get("score") is not None
    if kept:
        score["why"] = stored.get("why")
    elif fails:
        score["why"] = f"fails E5: {priced['why']}"
    else:
        score["why"] = None if score["eligible"] else stored.get("why")
    return score


# ----------------------------------------------------------------------------------------------------------- the screen
def screen_effective(settings: Mapping[str, Any] | None, lane: str = DIRECTION, *,
                     policy: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """The holdout look a family's lane uses (decision 6): {lane, screen, look_level, sharpe_share, receipt, c,
    fp_unconditional, fp_both_windows_rose, fp_lane_mixed, fp_lane_2224, fp_lane_ci_mixed, fp_lane_cluster_mixed,
    power10, validation, why}.

    - alpha, or any lane while the lane is "off": "S-B", `evidence.LOOK_LEVEL` and `HOLDOUT_SHARPE_SHARE`, exactly (its
      rates are FAST_LANE_SCREEN_1's, not a lane's: every `fp_*` is None);
    - direction: "S-C" (`dlane.screens.S-C`: p <= 0.20, a Sharpe share of 0.25; the Validation line as coded), its lane
      rates `fp_lane_mixed` (= its `fp_unconditional`, MONEY's mixed worlds) and `fp_lane_2224`;
    - direction with `dlane.screen` "D2": D2 only when the REPOSITORY's policy.json (`policy`: its parsed `dlane` block;
      default the file `settings.read_policy` reads, never swarm.json) pins a receipt sha256 and a calibrated `c`, and
      the lane is calls only (`dlane.structures` inside `D2_STRUCTURES`, release D-1b: D2 was measured on single calls);
      CI holds that sha to `docs/benchmarks/direction_screen_2.json`. Otherwise S-C, and `why` says D2 was refused. Under
      D2 `validation` is "precheck" (`d2_precheck`), which never opens tuition: tuition stays on the coded Validation
      line; every figure is the pinned receipt's (from the repository's policy.json, never a setting's).
    Every look event records `lane`, `screen` and `receipt` from here, and a direction look its `fp_lane_mixed` and
    `fp_lane_2224` too (release D-1b: the false-positive rate beside every look and every Probe trade)."""
    rates = {"fp_lane_mixed": None, "fp_lane_2224": None, "fp_lane_ci_mixed": None, "fp_lane_cluster_mixed": None,
             "power10": None}
    alpha = {"lane": ALPHA, "screen": ALPHA_SCREEN, "look_level": evidence.LOOK_LEVEL,
             "sharpe_share": evidence.HOLDOUT_SHARPE_SHARE, "receipt": None, "c": None, "fp_unconditional": None,
             "fp_both_windows_rose": None, **rates, "validation": "line", "why": None}
    if lane != DIRECTION or not on(settings):
        return alpha
    c = cfg(settings)
    sc = c["screens"]["S-C"]
    out = {"lane": DIRECTION, "screen": "S-C", "look_level": sc["look_level"], "sharpe_share": sc["sharpe_share"],
           "receipt": None, "c": None, "fp_unconditional": sc["fp_unconditional"],
           "fp_both_windows_rose": sc["fp_both_windows_rose"],
           **rates, "fp_lane_mixed": sc["fp_unconditional"], "fp_lane_2224": sc["fp_lane_2224"],
           "validation": "line", "why": None}
    if c["screen"] != "D2":
        return out
    pinned = _policy_d2(policy)
    wider = [s for s in c["structures"] if s not in D2_STRUCTURES]
    if pinned["receipt_sha256"] is None:
        out["why"] = "D2 refused: no receipt sha256 is pinned in the repository's policy.json"
    elif pinned["c"] is None:
        out["why"] = "D2 refused: the pinned receipt has no calibrated c in the repository's policy.json"
    elif wider:
        out["why"] = (f"D2 refused: it was measured on single calls and the lane admits {', '.join(wider)} "
                      "(dlane.structures)")
    else:
        # `fp_unconditional` keeps D-1's meaning (the lane's rate at zero edge, unconditional on the market): the
        # receipt's mixed-world lane rate unless the block names its own.
        unconditional = pinned["fp_unconditional"] if pinned["fp_unconditional"] is not None else pinned["fp_lane_mixed"]
        out.update(screen="D2", receipt=pinned["receipt_sha256"], c=pinned["c"], look_level=None, sharpe_share=None,
                   fp_unconditional=unconditional, fp_both_windows_rose=pinned["fp_both_windows_rose"],
                   **{k: pinned[k] for k in rates}, validation="precheck")
    return out


def fp_beside(screen: Mapping[str, Any] | None) -> dict[str, Any]:
    """THE FALSE-POSITIVE RATE BESIDE A LOOK OR A PROBE TRADE (release D-1b; the owner's goal of Oct 9, item 4: "stated
    beside every Probe trade"): {screen, fp_lane_mixed, fp_lane_2224, receipt} of a `screen_effective` answer (or a look's
    recorded detail). Operator-facing only: the figures are measured on worlds built from 2017-19 and 2022-24 blocks, so
    no prompt, view, brief, status or agenda carries them."""
    s = screen if isinstance(screen, Mapping) else {}
    return {"screen": s.get("screen"), "fp_lane_mixed": s.get("fp_lane_mixed"), "fp_lane_2224": s.get("fp_lane_2224"),
            "receipt": s.get("receipt")}


def fp_of_look(detail: Mapping[str, Any] | None, settings: Mapping[str, Any] | None, *,
               policy: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """`fp_beside` for the look that admitted a program (its `detail`, the gate's recorded line), for the operator's
    reports (release D-1b): the rates the look recorded; for a direction look made before D-1b recorded them, its
    screen's rates now ("S-C": `dlane.screens.S-C`; "D2": the repository policy's pinned figures, only when its receipt is
    the one the look recorded, else None); a look with no screen recorded is the alpha lane's "S-B" (no lane rate: its
    figure is FAST_LANE_SCREEN_1's bound, which the report states beside it)."""
    d = detail if isinstance(detail, Mapping) else {}
    if "fp_lane_mixed" in d or "fp_lane_2224" in d:
        return fp_beside(d)
    screen = d.get("screen") or ALPHA_SCREEN
    out = {"screen": screen, "fp_lane_mixed": None, "fp_lane_2224": None, "receipt": d.get("receipt")}
    if screen == "S-C":
        sc = cfg(settings)["screens"]["S-C"]
        out.update(fp_lane_mixed=sc["fp_unconditional"], fp_lane_2224=sc["fp_lane_2224"])
    elif screen == "D2":
        pinned = _policy_d2(policy)
        if pinned["receipt_sha256"] is not None and pinned["receipt_sha256"] == d.get("receipt"):
            out.update(fp_lane_mixed=pinned["fp_lane_mixed"], fp_lane_2224=pinned["fp_lane_2224"])
    return out


def _policy_d2(policy: Mapping[str, Any] | None) -> dict[str, Any]:
    """The D2 block of the repository's policy.json (`policy`: a parsed `dlane` block, or a whole policy document), never the
    box's swarm.json: a receipt is pinned by a reviewed pull request, not by a setting."""
    if policy is None:
        try:
            from . import settings as settings_mod

            layer, _ = settings_mod.read_policy()
        except Exception:  # noqa: BLE001 - no file: no receipt
            layer = {}
        policy = layer
    block = policy.get("dlane") if isinstance(policy, Mapping) and isinstance(policy.get("dlane"), Mapping) else policy
    screens = block.get("screens") if isinstance(block, Mapping) and isinstance(block.get("screens"), Mapping) else {}
    return _d2_block(screens.get("D2") if isinstance(screens.get("D2"), Mapping) else {})


def receipt_sha256(path: str | Path) -> str | None:
    """The sha256 of a receipt file's bytes (`docs/benchmarks/direction_screen_2.json`), or None when it cannot be read."""
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


#: D2's pre-check on Validation (PLAN J3): at least this many trades on this many entry days, and a 1.0x mean above zero.
D2_MIN_TRADES = evidence.MIN_TRADES
D2_MIN_DAYS = evidence.MIN_DAYS


def d2_precheck(summary: Mapping[str, Any] | None) -> dict[str, Any]:
    """D2's Validation pre-check, as DSCREEN-2 pre-registered it (PREREG section 2; dscreen2.py `p_`): {passed, checks}:
    at least 50 trades, at least 25 entry days and a mean entry-day return on maximum loss above zero, on the Validation
    run at 1.0x (the Gym's `trades`, `days_traded`, `mean_return_on_max_loss_daily`). It never opens tuition (decision
    6)."""
    s = summary if isinstance(summary, Mapping) else {}
    mean = evidence.daily_mean(s)
    checks = {"trades": int(s.get("trades") or 0) >= D2_MIN_TRADES, "days": int(s.get("days_traded") or 0) >= D2_MIN_DAYS,
              "mean_positive": mean is not None and mean > 0}
    return {"passed": all(checks.values()), "checks": checks}


def _entry_moments(summary: Mapping[str, Any] | None) -> tuple[int, float, float] | None:
    """A window's entry-day returns on maximum loss as (k, their sum, the sum of their squares), from its Gym summary: k
    the entry days (`days_traded`), m their mean (`mean_return_on_max_loss_daily`) and t their one-sample t (`t_daily`,
    sd with ddof 1), so sd = |m| sqrt(k) / |t|. One entry day is exact (no t: the Gym has none under two points). None
    when the sd cannot be had from the figures (FAIL-CLOSED, release D-1b): no entry day or no mean; a t of None over
    two or more days (the Gym gives none when the returns do not vary); a mean or a t that is zero as the summary rounds
    it (6 and 4 decimals), which leaves the sd undetermined."""
    s = summary if isinstance(summary, Mapping) else {}
    m, t = evidence.daily_mean(s), evidence.daily_t(s)
    raw = s.get("days_traded")
    k = int(raw) if isinstance(raw, (int, float)) and not isinstance(raw, bool) and float(raw).is_integer() else 0
    if k < 1 or m is None:
        return None
    if k == 1:
        return 1, m, m * m
    if t is None or t == 0 or m == 0:
        return None
    sd = abs(m) * math.sqrt(k) / abs(t)
    return k, m * k, (k - 1) * sd * sd + k * m * m


def _pooled(parts: Sequence[tuple[int, float, float]]) -> float | None:
    """The pooled one-sample t of windows given as (k, sum, sum of squares): mean / sd(ddof 1) x sqrt(n). None under two
    returns, with no variance or not finite."""
    n = sum(p[0] for p in parts)
    if n < 2:
        return None
    total = sum(p[1] for p in parts)
    sq = sum(p[2] for p in parts)
    var = (sq - total * total / n) / (n - 1)
    if not var > 0:
        return None
    t = (total / n) / math.sqrt(var / n)
    return t if math.isfinite(t) else None


def d2_pooled_t(validation: Mapping[str, Any] | None, holdout: Mapping[str, Any] | None) -> float | None:
    """D2's statistic, as DSCREEN-2 pre-registered it (PREREG section 2; dscreen2.py `eval_world2`, MONEY's
    `mlib.entry_moments`): the pooled entry-day t over the Validation and holdout entry days together,
    t = mean / sd(ddof 1) x sqrt(n), every entry day one return (an entry day of both windows counts twice). Built from
    each window's sufficient figures (`_entry_moments`), so on exact figures it IS that statistic (BUILD.md's fixtures:
    within 3e-15 of dscreen2's own code); on the Gym's summaries, which round the mean to 6 decimals and the t to 4, it
    is their point estimate (`d2_pooled_t_low` bounds it from below). None when either window cannot give its moments,
    or the pooled returns do not vary (fail-closed: D2 then fails, as dscreen2's -inf does)."""
    parts = [_entry_moments(validation), _entry_moments(holdout)]
    if any(p is None for p in parts):
        return None
    return _pooled(parts)  # type: ignore[arg-type]


#: The Gym's summary rounds a window's daily mean on maximum loss to 6 decimals and its daily t to 4
#: (league/gym/results.py `summarize`): half a unit of each is the most either figure is off.
GYM_MEAN_ROUNDING = 5e-7
GYM_T_ROUNDING = 5e-5


def _corners(summary: Mapping[str, Any] | None) -> list[tuple[int, float, float]] | None:
    """A window's (k, sum, sum of squares) at the corners of its summary's rounding (`GYM_MEAN_ROUNDING`,
    `GYM_T_ROUNDING`), as `_entry_moments` reads it (None where it does)."""
    if _entry_moments(summary) is None:
        return None
    s = summary if isinstance(summary, Mapping) else {}
    m, t, k = evidence.daily_mean(s), evidence.daily_t(s), int(s.get("days_traded"))  # type: ignore[arg-type]
    means = (m - GYM_MEAN_ROUNDING, m + GYM_MEAN_ROUNDING)  # type: ignore[operator]
    if k == 1:
        return [(1, mm, mm * mm) for mm in means]
    out = []
    for mm in means:
        for tt in (abs(t) - GYM_T_ROUNDING, abs(t) + GYM_T_ROUNDING):  # type: ignore[arg-type]
            sd = abs(mm) * math.sqrt(k) / tt
            out.append((k, mm * k, (k - 1) * sd * sd + k * mm * mm))
    return out


def d2_pooled_t_low(validation: Mapping[str, Any] | None, holdout: Mapping[str, Any] | None) -> float | None:
    """THE D2 STATISTIC'S LOWER BOUND ON THE GYM'S SUMMARIES (release D-1b): the least `d2_pooled_t` over the corners of
    both windows' rounding (their means within half a unit of the 6th decimal, their t within half a unit of the 4th;
    first-order exact over so small a box). D2 passes on it, so a pass here is a pass of DSCREEN-2's statistic on the
    exact returns, and the two can differ only within the rounding (BUILD.md: 2,000 fixtures, median gap under 3e-5).
    None when any corner cannot be computed (fail-closed)."""
    a, b = _corners(validation), _corners(holdout)
    if a is None or b is None:
        return None
    values = [_pooled([x, y]) for x in a for y in b]
    return None if any(v is None for v in values) else min(values)  # type: ignore[type-var]


def d2_verdict(validation: Mapping[str, Any] | None, holdout: Mapping[str, Any] | None, c: Any) -> dict[str, Any]:
    """THE D2 SCREEN after its one look (release D-1b; DSCREEN-2's rule, `screen_effective` "D2"): {passed, checks:
    {precheck, pnl, pooled}, pooled_t, pooled_t_low, c}. `precheck`: the Validation summary passes `d2_precheck` (how the
    version entered the gate; held again here); `pnl`: the holdout's P&L after fees above zero (the Gym's summary
    `pnl`); `pooled`: the statistic at least `c`, judged on its lower bound over the summaries' rounding
    (`d2_pooled_t_low`; `pooled_t` is the point figure), so the Gym's rounding can never pass a program DSCREEN-2's exact
    statistic fails. A missing figure fails its check."""
    hold = holdout if isinstance(holdout, Mapping) else {}
    pnl = _num(hold.get("pnl"))
    pooled = d2_pooled_t(validation, holdout)
    low = d2_pooled_t_low(validation, holdout)
    bar = _num(c)
    checks = {"precheck": bool(d2_precheck(validation)["passed"]), "pnl": pnl is not None and pnl > 0,
              "pooled": low is not None and bar is not None and low >= bar}
    return {"passed": all(checks.values()), "checks": checks, "pooled_t": pooled, "pooled_t_low": low, "c": bar}


def validation_r_sd(summary: Mapping[str, Any] | None) -> float | None:
    """THE SIGMA WRITER's figure (decision 4, for release L-D's DM1): the standard deviation of per-trade P&L per dollar of
    maximum loss in a Validation run, from its summary's per-trade mean (`mean_return_on_max_loss`), per-trade t (`t_stat`)
    and trades: |mean| x sqrt(n) / |t|. None (the key is then omitted) unless finite and above zero."""
    s = summary if isinstance(summary, Mapping) else {}
    mean, t = _num(s.get("mean_return_on_max_loss")), _num(s.get("t_stat"))
    n = s.get("trades")
    if mean is None or t is None or t == 0 or isinstance(n, bool) or not isinstance(n, int) or n < 2:
        return None
    sd = abs(mean) * math.sqrt(n) / abs(t)
    return round(sd, 6) if math.isfinite(sd) and sd > 0 else None


def leakage_alarm(looks: int, passes: int, settings: Mapping[str, Any] | None) -> bool:
    """THE DIRECTION LANE'S LEAKAGE ALARM (decision 7): at least `alarm_min_looks` (10) direction holdout looks and more than
    `alarm_pass_share` (60%) of them passed. The alpha lane's is `evidence.leakage_alarm`, unchanged, over alpha looks."""
    c = cfg(settings)
    return int(looks) >= c["alarm_min_looks"] and int(passes) > c["alarm_pass_share"] * int(looks)


# ----------------------------------------------------------------------------------------------------------- the ration
#: A Validation run that is no try: the Gym could not run it (`results.failed`, no data). A program's own errors
#: ("disqualified") are its try.
NOT_A_TRY = ("error", "no_data")
#: The public causes of `lineage_spent` (a `swarm.retired` cause and a graveyard lesson): rules only, no figure.
SPENT_LOOK = "its direction lineage has used its one holdout look (one Validation try and one look a direction lineage)"
SPENT_TRY = "its direction lineage has used its one Validation try (one Validation try and one look a direction lineage)"


def _connected_families(store: Any, fid: str) -> list[str]:
    """The families of `fid`'s connected lineages: the set `SwarmStore.lineage_looks` counts holdout looks over."""
    row = store._one("SELECT lineage FROM families WHERE id=?", (str(fid),))
    if row is None:
        return []
    lines = store._connected_lineages(row["lineage"])
    return [r["id"] for r in store._all(f"SELECT id FROM families WHERE lineage IN ({','.join('?' * len(lines))})",
                                        tuple(lines))]


def lineage_tries(store: Any, fid: str) -> list[dict[str, Any]]:
    """A DIRECTION LINEAGE'S VALIDATION TRIES (release D-1b, Oct 9, 2026): [{family, version, at}], oldest first, one per
    distinct (family, version) with a Validation run at 1.0x anywhere in `fid`'s connected lineages (the set its holdout
    looks are counted over), its own run or an inherited verdict's rows (F1), whatever its lane or its verdict: a run the
    Gym could not make (`NOT_A_TRY`) is none. `at` is the version's first such run: a version validated again (a new Gym
    image, an adoption) is the same try."""
    fams = _connected_families(store, fid)
    if not fams:
        return []
    rows = store._all(f"SELECT family, version, MIN(at) AS at FROM runs WHERE family IN ({','.join('?' * len(fams))}) "
                      "AND \"window\"='validation' AND stress=1.0 AND version IS NOT NULL "
                      f"AND COALESCE(status, '') NOT IN ({','.join('?' * len(NOT_A_TRY))}) GROUP BY family, version",
                      (*fams, *NOT_A_TRY))
    out = [{"family": str(r["family"]), "version": int(r["version"]), "at": str(r["at"] or "")} for r in rows]
    out.sort(key=lambda r: (r["at"], r["family"], r["version"]))
    return out


def looks_ration(store: Any, fam: Mapping[str, Any] | None, settings: Mapping[str, Any] | None) -> int:
    """The holdout looks a family's connected lineage may spend: `looks_per_lineage` (1) for a DIRECTION lineage (release
    D-1b), `evidence.LOOKS_PER_LINEAGE` (3) for every other, and for every family while the lane is off (THE ROLLBACK).
    `store` None reads the lane from the spec alone (`lane_of`)."""
    if lane_of(store, fam, settings) == DIRECTION:
        return int(cfg(settings)["looks_per_lineage"])
    return evidence.LOOKS_PER_LINEAGE


def try_open(store: Any, fam: Mapping[str, Any], n: Any, settings: Mapping[str, Any] | None) -> bool:
    """May version `n` of `fam` be validated (release D-1b)? Always for an alpha family and while the lane is off. A
    direction family: while its lineage has a Validation try left (`lineage_tries` under `val_tries`), or when `n` is
    one of the lineage's first `val_tries` tries already (validated again on a new Gym image: the same try). Never
    raises (an unreadable lineage is no try)."""
    if lane_of(store, fam, settings) != DIRECTION:
        return True
    try:
        tries = lineage_tries(store, str(fam["id"]))
        k = int(cfg(settings)["val_tries"])
        mine = any(t["family"] == str(fam["id"]) and t["version"] == int(n) for t in tries[:k])
        return mine or len(tries) < k
    except Exception:  # noqa: BLE001 - an unreadable lineage buys no try
        return False


def first_try(store: Any, fid: str, n: Any, settings: Mapping[str, Any] | None) -> bool:
    """Version `n` of `fid` is one of its lineage's first `val_tries` Validation tries (`lineage_tries`): only such a try may
    enter the gate (`Tournament._verdict`'s backstop: a second try that raced past `try_open`, a result landing late, is
    judged and recorded and never enters). False on a store error."""
    try:
        k = int(cfg(settings)["val_tries"])
        return any(t["family"] == str(fid) and t["version"] == int(n) for t in lineage_tries(store, str(fid))[:k])
    except Exception:  # noqa: BLE001
        return False


def try_owed(store: Any, fam: Mapping[str, Any], settings: Mapping[str, Any] | None, *, image: Any = None,
             bundle: Any = None) -> int | None:
    """THE LINEAGE'S TRY, VALIDATED AGAIN (release D-1b, Oct 9, 2026; the review's finding 1): the version of `fam` that is
    its direction lineage's one Validation try, when the tournament owes that try a verdict on the Gym in use (`image`,
    `bundle`) although the family's candidate has moved on to a version that can never be validated (`try_open`). Owed:
    - the try has NO VERDICT (no `TRY_KEY` for it): its result was dropped as stale (a new Gym image or bundle while its job
      was out) or never judged, so the run spent the lineage's try with nothing judged;
    - or its verdict ENTERED THE GATE (`TRY_KEY` `entered`), the gate is not done with it (no look, no refusal:
      `gated_sha`) and the verdict is on another Gym image or bundle, which the gate never looks past (`Gate.run`).
    Why the try's version and not the candidate: the run is the lineage's try whatever happens (`lineage_tries`), so the
    false-positive accounting stays conservative, and judging that very version is the only verdict the lineage can still
    have. None for every alpha family, while the lane is off, for a lineage whose try is another family's, and on any
    store error (no try is bought by an error)."""
    if lane_of(store, fam, settings) != DIRECTION:
        return None
    try:
        fid = str(fam["id"])
        mine = [t for t in lineage_tries(store, fid)[:int(cfg(settings)["val_tries"])] if t["family"] == fid]
        if not mine:
            return None
        n = int(mine[0]["version"])
        state = fam.get("state") or {}
        held = state.get(TRY_KEY) if isinstance(state.get(TRY_KEY), Mapping) else {}
        if held.get("version") != n:
            return n
        if held.get("entered") is not True:
            return None  # judged, and it did not enter the gate: the try is spent
        if state.get("validation_image") == image and state.get("validation_bundle") == bundle:
            return None  # its verdict is on the Gym in use: the gate has it
        version = store.version(fid, n)
        sha = _run_sha(version) if version is not None and version.get("sha") else None
        if sha is None or store.looked(sha) or state.get("gated_sha") == sha:
            return None  # the gate is done with it
        return n
    except Exception:  # noqa: BLE001 - an unreadable lineage buys nothing
        return None


def _run_sha(version: Mapping[str, Any]) -> str:
    """`gate.run_sha` (a version's program as the gate marks and looks at it: its code sha and its params), computed here
    because the gate imports this module (a test holds the two equal)."""
    from .store import dumps

    return hashlib.sha256((str(version["sha"]) + dumps(version.get("params") or {})).encode()).hexdigest()


def lineage_spent(store: Any, fam: Mapping[str, Any], settings: Mapping[str, Any] | None) -> str | None:
    """THE RATION'S RETIREMENT (release D-1b): the public cause to retire a living Gym-band DIRECTION family whose lineage
    has spent its ration without a pass that is still in play, else None (every alpha family; every family while the lane
    is off):
    - `SPENT_LOOK`: its connected lineage's holdout looks (in flight too) reach `looks_per_lineage` (a passed look moved
      its family out of the Gym band; every other member can have none);
    - `SPENT_TRY`: its lineage's Validation tries reach `val_tries`, unless the family holds the lineage's try itself
      and either that try has NO VERDICT yet (the review's finding 1: its result was dropped as stale, and `try_owed` has
      it judged; the run still counts as the try) or it entered the gate (`TRY_KEY` `entered`: the line, or D2's
      pre-check) and the gate has not finished with it (no look, no refusal: `gated_sha`), so it waits for its one look
      even while a new Gym image has it validated again.
    The tournament asks after the gate's own holds (`gate_ready`, a look in flight). Never raises: None on a store error."""
    try:
        if lane_of(store, fam, settings) != DIRECTION:
            return None
        c = cfg(settings)
        fid = str(fam["id"])
        if store.lineage_looks(fid, include_inflight=True) >= c["looks_per_lineage"]:
            return SPENT_LOOK
        tries = lineage_tries(store, fid)
        if len(tries) < c["val_tries"]:
            return None
        mine = [t for t in tries[:c["val_tries"]] if t["family"] == fid]
        state = fam.get("state") or {}
        held = state.get(TRY_KEY) if isinstance(state.get(TRY_KEY), Mapping) else {}
        if mine and held.get("version") != mine[0]["version"]:
            return None  # its own try has no verdict yet: it is owed one (`try_owed`), not retired unjudged
        if mine and held.get("entered") is True and held.get("version") == mine[0]["version"]:
            version = store.version(fid, mine[0]["version"])
            sha = _run_sha(version) if version is not None and version.get("sha") else None
            if sha is not None and not store.looked(sha) and state.get("gated_sha") != sha:
                return None
        return SPENT_TRY
    except Exception:  # noqa: BLE001 - a rule that cannot be read retires nothing
        return None


# ----------------------------------------------------------------------------------------------------------- the quota
def _born(store: Any, since: str | None = None) -> list[dict[str, Any]]:
    """`swarm.born` payloads (with their `at`) since `since` (every one when None), oldest first."""
    from .store import loads

    sql, args = "SELECT at, payload FROM events WHERE kind='swarm.born'", []
    if since is not None:
        sql, args = sql + " AND at>=?", [since]
    out = []
    for row in store._all(sql + " ORDER BY at, seq", tuple(args)):
        payload = loads(row.get("payload"), {}) or {}
        lane = payload.get("lane") if isinstance(payload, Mapping) else None
        out.append({"at": row.get("at"), "lane": lane if lane in LANES else ALPHA})
    return out


def born_counts(store: Any, hours: float, *, now: float | None = None) -> dict[str, int]:
    """Births by lane over the last `hours` ({"alpha": n, "direction": n}); a payload without a lane is alpha."""
    from .store import iso

    now = time.time() if now is None else float(now)
    out = {ALPHA: 0, DIRECTION: 0}
    for row in _born(store, iso(now - float(hours) * 3600.0)):
        out[row["lane"]] += 1
    return out


def last_direction_birth(store: Any) -> str | None:
    """When the newest direction birth was (its `swarm.born` event's `at`), or None."""
    rows = [r for r in _born(store) if r["lane"] == DIRECTION]
    return rows[-1]["at"] if rows else None


def alive_direction(store: Any, settings: Mapping[str, Any] | None) -> int:
    """How many living families are in the direction lane (0 while the lane is off)."""
    if not on(settings):
        return 0
    return sum(1 for fam in store.families(alive=True) if declared_lane(store, fam) == DIRECTION)


def started_at(store: Any, settings: Mapping[str, Any] | None, *, now: float | None = None) -> str | None:
    """When the lane was first switched on in this store (kv `STARTED_KEY`, written once by the first call that finds it on
    and may write), or None while it is off: the `lane_only` clock never runs before the lane does."""
    if not on(settings):
        return None
    value = store.get(STARTED_KEY)
    if isinstance(value, str) and value:
        return value
    if getattr(store, "readonly", False):
        return None
    from .store import iso

    stamp = iso(time.time() if now is None else float(now))
    with store.atomic():
        value = store.get(STARTED_KEY)
        if isinstance(value, str) and value:
            return value
        store.put(STARTED_KEY, stamp)
    return stamp


def lane_only_due(store: Any, settings: Mapping[str, Any] | None, *, now: float | None = None, alive: int | None = None,
                  ceiling: int | None = None) -> tuple[bool, str]:
    """(due, why): the architect's pass asks for direction proposals only (`lane_only`, HARNESS section 5 item 1, alarm A1)
    when the lane is on, no direction birth has landed in `lane_only_hours` (12) since the lane started, the population
    (`alive`) is under its `ceiling`, and no `lane_only` request was made in the last `lane_only_hours` (`lane_only_mark`)."""
    from .store import iso

    if not on(settings):
        return False, "the direction lane is off"
    c = cfg(settings)
    now = time.time() if now is None else float(now)
    if alive is not None and ceiling is not None and int(alive) >= int(ceiling):
        return False, "the population is at its ceiling"
    edge = iso(now - c["lane_only_hours"] * 3600.0)
    start = started_at(store, settings, now=now)
    if start is None or start > edge:
        return False, "the lane started less than the window ago"
    last = last_direction_birth(store)
    if last is not None and last > edge:
        return False, "a direction family was born inside the window"
    asked = store.get(LANE_ONLY_KEY)
    if isinstance(asked, str) and asked > edge:
        return False, "a lane_only request was made inside the window"
    return True, f"no direction birth in {c['lane_only_hours']:g} h"


def lane_only_mark(store: Any, *, now: float | None = None) -> None:
    """Record that a `lane_only` request was made now (kv `LANE_ONLY_KEY`)."""
    from .store import iso

    if not getattr(store, "readonly", False):
        store.put(LANE_ONLY_KEY, iso(time.time() if now is None else float(now)))


class DirectionQuota:
    """THE DIRECTION QUOTA for one architect pass (the module docstring; decision 1), beside `allocation.BirthQuota`:
    the window's births by lane, read once, and this pass's so far.

    - floor: while the lane is on, fewer than `max_alive` direction families live, the window's direction share is under
      `birth_share` (or the window holds under `min_window` births) and the window cap is not reached, the first
      max(`min_per_pass`, ceil(`birth_share` x want)) births of the pass (at most `want`) are reserved for direction: alpha
      never fills them (`short` counts the unfilled ones);
    - cap: a direction birth is refused once the lane would hold more than `max_share` of the window and this pass (once the
      window holds `min_window` births), or past `max_alive` living direction families, or past the pass's own direction
      cap, max(floor, `min_per_pass`, floor(`max_share` x want));
    - while the lane is off it refuses every direction birth and limits no alpha birth (the architect then never builds
      one: the rollback is byte for byte).

    THE CLASS CAP (the review of release D-1, Oct 9, 2026). The architect's `max_alive_per_class` (12 living families a
    mechanism class, structure x root group) refuses a proposal before this quota is asked, and every direction card falls
    in one of the lane's few classes (`Architect.lane_classes`: long_single or debit_vertical on the ETF roots), which
    alpha's core five births share. `class_room` ({class: free places at the pass's start}, from the architect; None: no
    cap) bounds the reservation: the floor is never more than the room, and as births of either lane fill those classes within the
    pass (`born(lane, cls)`) the births still reserved shrink with it (`reserved`), so alpha is never refused places no
    direction card could take. A direction card the class cap refused is counted apart (`capped_by_class`; the event's
    `lane_class_capped`), so the next request names the full classes rather than blaming the card's form."""

    def __init__(self, store: Any, settings: Mapping[str, Any] | None, *, now: float | None = None, want: int = 0,
                 alive: int | None = None, class_room: Mapping[str, int] | None = None, class_cap: int | None = None):
        from .store import iso

        c = cfg(settings)
        self.c = c
        self.on = on(settings)
        self.mode = mode_effective(store, settings) if self.on else "off"
        self.want = max(0, int(want))
        now = time.time() if now is None else float(now)
        self.window = {ALPHA: 0, DIRECTION: 0}
        if self.on:
            for row in _born(store, iso(now - c["window_hours"] * 3600.0)):
                self.window[row["lane"]] += 1
        self.alive = (int(alive) if alive is not None else alive_direction(store, settings)) if self.on else 0
        # THE CLASS CAP's room in the lane's classes (None: no cap read, the quota as built before the review).
        self.class_room = ({str(k): max(0, int(v)) for k, v in class_room.items()}
                           if isinstance(class_room, Mapping) and self.on else None)
        self.class_cap = int(class_cap) if class_cap else None
        self.class_capped = 0
        total = sum(self.window.values())
        behind = total < c["min_window"] or self.window[DIRECTION] < c["birth_share"] * total
        self.floor = 0
        if self.on and self.want and self.alive < c["max_alive"] and behind and not self._full(0, 0):
            self.floor = min(self.want, max(c["min_per_pass"], math.ceil(c["birth_share"] * self.want - 1e-9)))
            if self.class_room is not None:
                self.floor = min(self.floor, self.room())
        self.pass_cap = max(self.floor, c["min_per_pass"], math.floor(c["max_share"] * self.want + 1e-9)) if self.on else 0
        self.passed = {ALPHA: 0, DIRECTION: 0}
        self.refused = {ALPHA: 0, DIRECTION: 0}
        self.reasons: list[str] = []

    def room(self) -> int:
        """The places left now in the lane's classes under the class cap (a large number when no cap was read)."""
        return sum(self.class_room.values()) if self.class_room is not None else 10 ** 9

    def reserved(self) -> int:
        """The pass's births reserved for direction now: the floor, less any the lane's classes can no longer hold (the
        class cap; the review of Oct 9). The floor itself while no cap was read."""
        if self.class_room is None:
            return self.floor
        return min(self.floor, self.passed[DIRECTION] + self.room())

    def full_classes(self) -> list[str]:
        """The lane's classes with no place left under the class cap, sorted ([] while no cap was read)."""
        return sorted(k for k, v in (self.class_room or {}).items() if v <= 0)

    def capped_by_class(self, lane: str) -> None:
        """A proposal the architect's class cap refused (before this quota was asked): counted when it is a direction
        card (the event's `lane_class_capped`)."""
        if lane == DIRECTION:
            self.class_capped += 1

    def _full(self, direction: int, total: int) -> bool:
        """One more direction birth would put the lane over `max_share` of the window and the pass (once the window and
        the pass hold `min_window` births)."""
        n = sum(self.window.values()) + total
        d = self.window[DIRECTION] + direction
        return n >= self.c["min_window"] and d + 1 > self.c["max_share"] * (n + 1)

    def why_not(self, lane: str) -> str | None:
        """Why one more birth of `lane` may not be born in this pass, or None when it may."""
        if lane != DIRECTION:
            reserved = self.reserved() if self.on else 0
            if not self.on or not reserved:
                return None
            if self.passed[ALPHA] >= self.want - reserved:
                return (f"the pass's {reserved} reserved direction births are never filled with alpha "
                        f"(dlane.birth_share {self.c['birth_share']:g})")
            return None
        if not self.on:
            return "the direction lane is off (dlane.mode)"
        if self.alive + self.passed[DIRECTION] >= self.c["max_alive"]:
            return f"{self.c['max_alive']} direction families live already (dlane.max_alive)"
        if self.class_room is not None and self.room() <= 0:
            return (f"the lane's classes are full under the class cap (architect.max_alive_per_class"
                    + (f" {self.class_cap}" if self.class_cap else "") + f": {', '.join(self.full_classes())})")
        if self.passed[DIRECTION] < self.reserved():
            return None
        if self.passed[DIRECTION] >= self.pass_cap:
            return f"the pass's direction cap of {self.pass_cap} is reached"
        if self._full(self.passed[DIRECTION], sum(self.passed.values())):
            return (f"the direction lane would hold more than {self.c['max_share']:.0%} of the last "
                    f"{self.c['window_hours']:g} h of births (dlane.max_share)")
        return None

    def admits(self, lane: str) -> bool:
        """May one more birth of `lane` be born in this pass? A refusal is counted (`refused`) with its reason."""
        lane = DIRECTION if lane == DIRECTION else ALPHA
        why = self.why_not(lane)
        if why is not None:
            self.refused[lane] += 1
            self.reasons.append(f"{lane}: {why}")
        return why is None

    def born(self, lane: str, cls: str | None = None) -> None:
        """A birth of `lane` in mechanism class `cls`: a birth of either lane in one of the lane's classes takes a place
        under the class cap (`reserved`)."""
        self.passed[DIRECTION if lane == DIRECTION else ALPHA] += 1
        if self.class_room is not None and cls is not None and str(cls) in self.class_room:
            self.class_room[str(cls)] = max(0, self.class_room[str(cls)] - 1)

    def short(self) -> int:
        """The pass's reserved direction births left unfilled (its event's `lane_short`): only those the lane's classes
        still had room for (`reserved`)."""
        return max(0, self.reserved() - self.passed[DIRECTION])

    def event(self) -> dict[str, Any]:
        """The pass event's lane keys: {lane_births, lane_refused, lane_short}, and `lane_class_capped` (direction cards
        the class cap refused, with the lane's classes then full) when there were any."""
        out: dict[str, Any] = {"lane_births": dict(self.passed), "lane_refused": dict(self.refused),
                               "lane_short": self.short()}
        if self.class_capped:
            out["lane_class_capped"] = {"cards": self.class_capped, "full": self.full_classes()}
        return out

    def text(self) -> str:
        """The architect's request's quota lines for the direction lane ("" while it is off)."""
        if not self.on:
            return ""
        total = sum(self.window.values())
        d = self.window[DIRECTION]
        share = (100.0 * d / total) if total else 0.0
        lines = [f"DIRECTION QUOTA (the last {self.c['window_hours']:g} h of births): direction {d} of {total} ({share:.0f}%); "
                 f"the lane holds at most {self.c['max_share']:.0%} of births and aims at {self.c['birth_share']:.0%}. "
                 f"Direction families alive: {self.alive} of at most {self.c['max_alive']}."]
        full = self.full_classes()
        if self.floor:
            lines.append(f"This pass: at least {self.floor} of its {self.want} births are DIRECTION and are never filled with "
                         f"alpha; up to {self.pass_cap} may be.")
        elif self.alive >= self.c["max_alive"]:
            lines.append("This pass: the lane is full; propose alpha.")
        elif self.class_room is not None and self.room() <= 0:
            lines.append("This pass: no direction birth: every class a direction card can be in is full under the class "
                         f"cap ({', '.join(full)}); propose alpha.")
        else:
            lines.append(f"This pass: up to {self.pass_cap} direction births, none reserved (the lane is at its share).")
        if full and self.class_room is not None and self.room() > 0:
            lines.append(f"Full under the class cap (no birth of these classes, either lane): {', '.join(full)}; a direction "
                         "card of another structure has room.")
        if self.mode == "shadow":
            lines.append("The lane is in shadow: its families research and validate, and none becomes a Candidate yet.")
        return "\n".join(lines)


# ----------------------------------------------------------------------------------------------------------- the text
def lanes_text(settings: Mapping[str, Any] | None) -> str:
    """The architect's LANES block: each lane's rules in a few lines (the quota's counts are `DirectionQuota.text`). ""
    while the lane is off. Rules and Train-year facts only."""
    if not on(settings):
        return ""
    c = cfg(settings)
    return "\n".join([
        "LANES. Two research lanes; every card declares one: \"lane\": \"alpha\" (the default) or \"direction\".",
        "- ALPHA: the rules as before: the WORST Train year's score, and a program must beat what its own market exposure "
        "earns on average days; index long calls are not alpha.",
        f"- DIRECTION ({OBJECTIVE}): profit from the index's direction counts and is reported beside the same-risk "
        f"buy-and-hold; {ALWAYS_IN_NOTE}. A direction card: mechanism_class {' or '.join(c['classes'])}; structure "
        f"{' or '.join(c['structures'])} (a direction long_single buys calls only: one out-of-the-money call near 0.20-0.30 "
        f"delta fits the unit"
        + ("; no put, no vertical, no short leg" if all(s in D2_STRUCTURES for s in c["structures"]) else "") +
        f"); roots from {', '.join(c['roots'])}; holding {' or '.join(c['holding'])} (2 to 8 sessions); "
        "an ablation switch that enters the same structure every session at the same minute (never flat). "
        + ration_text(settings) + " A dead direction idea proposed again on its own slice continues its lineage, with "
        "no try left.",
        f"- DIRECTION BAR on Train: in the market in at least {c['min_active_years']} of the 3 Train years ({ACTIVE_MIN_TRADES}+ "
        f"trades on {ACTIVE_MIN_DAYS}+ days and at least {c['active_share']:.0%} of its busiest year's exposure) with "
        f"{c['min_entry_days']}+ entry sessions in each; a year it stays mostly out loses no worse than t {c['out_t_floor']:g} "
        f"and {c['out_loss_share']:g} of its average in-market year; one lot at today's prices within the unit cap; at 1.5x "
        f"the half-spread: P&L above zero, the same years rules, and at least {c['cost_ratio']:g} of the 1.0x P&L. Its score is "
        "the pooled t of daily P&L at 1.0x. A gate that leaves a falling market is the edge to find; the bar does not test it.",
    ])


def ration_text(settings: Mapping[str, Any] | None) -> str:
    """THE RATION in words (release D-1b): rules only, no figure; "" while the lane is off."""
    if not on(settings):
        return ""
    return ("ONE VALIDATION TRY AND ONE HOLDOUT LOOK A DIRECTION LINEAGE: the first version the lineage sends to Validation "
            "is its only try, and the lineage retires when that try or its one look is spent without a pass; send the "
            "version you would stake the lineage on.")


def brief_text(settings: Mapping[str, Any] | None, roots: Iterable[str] | None = None) -> str:
    """A direction family's brief (static per family, so it is cached with the family's prefix): what its lane counts, the
    bar it is judged by, what is reported beside it, and `ALWAYS_IN_NOTE`; then, while `dlane.train_map` is on, THE
    TRAIN MAP's lessons and best passing shapes on its roots (`train_map_brief`). "" while the lane is off. No figure:
    today's unit cap is in `status_text`."""
    if not on(settings):
        return ""
    c = cfg(settings)
    names = [str(r).upper() for r in roots or () if str(r).upper() in c["roots"]] or list(c["roots"])
    # CALLS ONLY (release D-1b): with the lane's structures single calls alone, the brief says so and names C1; a lane
    # that still admits verticals keeps D-1's words.
    calls = all(s in D2_STRUCTURES for s in c["structures"])
    # The review's finding 3: a program whose code names a put, a short leg or any open but long_call is refused before it
    # runs (`calls_only_code`), in any condition, not only the Train years' (C1).
    what = ("and nothing else, in any condition (no put, no vertical, no short leg: a program whose code names one, or any "
            "open but long_call, is refused before it runs, and a Train trade holding one fails C1): one out-of-the-money "
            "call near 0.20-0.30 delta fits the unit" if calls else
            "one out-of-the-money call near 0.20-0.30 delta fits the unit (the lane steers to single calls; narrow "
            "verticals rarely fit after costs)")
    text = (
        f"YOUR LANE: DIRECTION ({OBJECTIVE}). Profit from the index's direction counts in this lane, and every figure of it is "
        f"reported beside the same-risk buy-and-hold, never hidden: {ALWAYS_IN_NOTE}. Your program buys calls on "
        f"{', '.join(names)} {what}, one lot per entry, never sized by capital, held 2 to 8 sessions. "
        f"{ration_text(settings)} YOUR "
        "TRAIN SCORE is the pooled t "
        "of your daily P&L over the Train years at 1.0x the half-spread, not the worst year. A version is eligible when "
        + ("(C1) every trade is a long call; " if calls else "") +
        f"(E1) it is in the market in at least {c['min_active_years']} of the 3 Train years (in the market: "
        f"{ACTIVE_MIN_TRADES}+ trades on {ACTIVE_MIN_DAYS}+ days and at least {c['active_share']:.0%} of its busiest year's "
        f"exposure); (E3) a year it stays mostly out loses no worse than t {c['out_t_floor']:g} and {c['out_loss_share']:g} "
        f"of its average in-market year's P&L; (E4) it enters on {c['min_entry_days']}+ sessions in every in-market year; "
        f"(E5) one lot's maximum loss with fees at today's index prices fits the unit cap (at most {c['unit_share']:.0%} of "
        f"the account's equity; ${c['unit_pref_usd']:.0f} or less also fits the incubator). Its 1.5x run must then show "
        f"(P1) P&L above zero, (R2) E1 and E3 again, and (R3) at least {c['cost_ratio']:g} of the 1.0x P&L, or the version is "
        f"demoted. Reported beside it, never a bar: whether every in-market year's t is at least 0, the pooled t at 1.5x "
        f"against {c['c_train']:g}, your gate against the same structure entered every session (your card's ablation), "
        "beta, drift share and the drift-adjusted alpha. The edge to find is the REGIME GATE: in when the index's drift is "
        "reliable, out when it is not. You know the market's history: a rule that works only because you know which years "
        "fell is not a gate. Use scale-free state (implied vol against its own trailing year, implied against realized, "
        "term structure, price against its own moving average or recent high), never price levels or dates.")
    # THE TRAIN MAP (Oct 9, 2026): its lessons and the best passing shapes on this family's roots ("" while it is off).
    shown = train_map_brief(settings, names)
    return text + ("\n" + shown if shown else "")


def _yes(v: Any) -> str:
    return "n/a" if v is None else ("yes" if v else "no")


def _t(v: Any) -> str:
    x = _num(v)
    return "n/a" if x is None else f"{x:.2f}"


def status_text(score: Mapping[str, Any] | None, robust: Mapping[str, Any] | None = None, *, version: Any = None,
                mechanism: str | None = None, settings: Mapping[str, Any] | None = None) -> str:
    """The direction objective's status line for a cycle (`score` the best version's `train_score`, `robust` its
    `robust_verdict`; `mechanism` "passed", "failed" or None: not tested). Train-year figures only. "" while the lane is
    off."""
    if not on(settings):
        return ""
    c = cfg(settings)
    head = f"DIRECTION OBJECTIVE ({OBJECTIVE})" + (f", version {version}" if version is not None else "")
    if not isinstance(score, Mapping) or score.get("objective") != OBJECTIVE:
        return f"{head}: no scored Train run yet. Note: {ALWAYS_IN_NOTE}."
    parts = [f"{head}: score {_t(score.get('score'))} (the pooled t of daily P&L over Train at 1.0x)."]
    years = []
    for y, r in sorted((score.get("years") or {}).items()):
        if not (str(y).isdigit() and FIRST_YEAR <= int(y) <= LAST_YEAR) or not isinstance(r, Mapping):
            continue
        x = _num(r.get("exposure"))
        years.append(f"{y} {'IN' if r.get('active') else 'OUT'} t {_t(r.get('t'))} exposure "
                     f"{'n/a' if x is None else f'{100 * x:.0f}%'} P&L {_usd(r.get('pnl'))} entry sessions "
                     f"{r.get('days_traded') if r.get('days_traded') is not None else 'n/a'}")
    if years:
        parts.append("; ".join(years) + ".")
    # THE UNIT (E5): its verdict only, never a figure priced today (`UNIT_HINT`; the review of Oct 9, 2026).
    unit = score.get("unit") if isinstance(score.get("unit"), Mapping) else {}
    if unit.get("verdict") == "pass":
        parts.append("Unit: one lot fits the unit cap at today's index prices.")
    elif unit.get("verdict") == "fail":
        parts.append(f"Unit: one lot is OVER the unit cap at today's index prices: {UNIT_HINT}.")
    else:
        parts.append(f"Unit: unknown today ({unit.get('why') or 'no live context'}); the live path prices every open.")
    if isinstance(robust, Mapping) and robust.get("known"):
        checks = robust.get("checks") or {}
        parts.append(f"At 1.5x: P&L {_usd(robust.get('pnl_15'))} (P1 {_yes(checks.get('P1'))}), the years rules again "
                     f"(R2 {_yes(checks.get('R2'))}), 1.5x/1.0x P&L {_t(robust.get('ratio'))} (R3, needs "
                     f"{c['cost_ratio']:g}: {_yes(checks.get('R3'))}).")
    elif isinstance(robust, Mapping):
        parts.append(f"At 1.5x: {robust.get('why') or 'not landed'}.")
    else:
        parts.append("At 1.5x: not landed.")
    verdict = "eligible" if score.get("eligible") else (score.get("why") or "not eligible")
    if isinstance(robust, Mapping) and robust.get("known") and not robust.get("passed"):
        verdict = robust.get("why") or "fails at 1.5x"
    parts.append(f"Verdict: {verdict}.")
    rep = score.get("reported") or {}
    rob_rep = (robust or {}).get("reported") or {} if isinstance(robust, Mapping) else {}
    side = score.get("beside") or {}
    gate = {"passed": "passed", "failed": "failed"}.get(str(mechanism), "not tested")
    extra = []
    if _num(side.get("beta_per_1pct")) is not None:
        extra.append(f"beta ${_num(side['beta_per_1pct']):,.2f} per 1% move")
    if _num(side.get("drift_share")) is not None:
        extra.append(f"drift share {100 * _num(side['drift_share']):.0f}%")
    if _num(side.get("alpha_t")) is not None:
        extra.append(f"drift-adjusted alpha t {_t(side['alpha_t'])}")
    if _num(side.get("always_in_usd")) is not None:
        extra.append(f"the same exposure held every session {_usd(side['always_in_usd'])}")
    t15 = (robust or {}).get("t_pool_15") if isinstance(robust, Mapping) else None
    parts.append(f"Reported, never a bar: every in-market year t >= 0: {_yes(rep.get('E2'))}; pooled t at 1.5x {_t(t15)} "
                 f"against {c['c_train']:g}: {_yes(rob_rep.get('R1'))}; gate vs the every-session twin: {gate}"
                 + (f"; {', '.join(extra)}" if extra else "") + ".")
    parts.append(f"Note: {ALWAYS_IN_NOTE}.")
    return " ".join(parts)


def view(score: Mapping[str, Any] | None, robust: Mapping[str, Any] | None = None, *,
         mechanism: str | None = None) -> dict[str, Any] | None:
    """The `lane` block a direction family's `gym_run` view carries (Train-year figures only): {lane, objective, score,
    t_pool, t_pool_15, years {y: {active, t, exposure, pnl, entry_days}}, unit, verdict, why, fails, reported, beside,
    note}. Its `unit` is E5's verdict alone ({verdict}, and `hint` on a fail): no figure priced at today's closes or the
    account's equity (`UNIT_HINT`; the review of Oct 9, 2026 overrides HARNESS 6's `scale` here on secrecy grounds).
    None without a direction score."""
    if not isinstance(score, Mapping) or score.get("objective") != OBJECTIVE:
        return None
    unit = score.get("unit") if isinstance(score.get("unit"), Mapping) else {}
    rob = robust if isinstance(robust, Mapping) else {}
    years = {y: {"active": bool(r.get("active")), "t": r.get("t"), "exposure": r.get("exposure"), "pnl": r.get("pnl"),
                 "entry_days": r.get("days_traded")}
             for y, r in sorted((score.get("years") or {}).items())
             if str(y).isdigit() and FIRST_YEAR <= int(y) <= LAST_YEAR and isinstance(r, Mapping)}
    eligible = bool(score.get("eligible")) and (not rob.get("known") or bool(rob.get("passed")))
    why = score.get("why") if not score.get("eligible") else (rob.get("why") if rob.get("known") and not rob.get("passed")
                                                               else None)
    return {"lane": DIRECTION, "objective": OBJECTIVE, "score": score.get("score"), "t_pool": score.get("t_pool"),
            "t_pool_15": rob.get("t_pool_15"), "years": years,
            "unit": {"verdict": unit.get("verdict"), **({"hint": UNIT_HINT} if unit.get("verdict") == "fail" else {})},
            "verdict": "eligible" if eligible else "not eligible", "why": why,
            "fails": list(score.get("fails") or []) + list(rob.get("fails") or []),
            "reported": {"E2": (score.get("reported") or {}).get("E2"), "R1": (rob.get("reported") or {}).get("R1"),
                         "mechanism": {"passed": "passed", "failed": "failed"}.get(str(mechanism), "not tested")},
            "beside": dict(score.get("beside") or {}), "note": ALWAYS_IN_NOTE}


# ----------------------------------------------------------------------------------------------------------- the train map
#: THE TRAIN MAP (Oct 9, 2026, after release D-1b): which call shapes pass direction-v2 on the Train years, from the
#: operator's census (every SPY/QQQ/IWM call cell by delta, expiry rule, hold, entry minute and gate, one lot at natural
#: prices, scored by this module's own `train_score` and `robust_verdict` on 2022-24 only), so births aim at shapes that
#: pass rather than search for them. IN-SAMPLE, and labelled so everywhere it is shown (`MAP_LABEL`): the D2 screen
#: (Validation, then one sealed holdout look) decides, unchanged. The file is league/swarm/dlane_map.json (protected like
#: this module); `train_map` reads it (cached, never raises: a missing, malformed or unsafe file is no map) and
#: `train_map_text` (the architect's LANES block) and `train_map_brief` (a direction researcher's brief) show it, only
#: while the lane is on and `dlane.train_map` is true (`map_on`; policy.json true, swarm.json false turns it off at once).
#: What agents read of it: shapes in the map's own words, each with its pooled S_D to one decimal and the unit's verdict
#: as a word ("fits the unit at today's prices: yes/no/borderline"), and the census's lessons; never a dollar figure, a
#: price level or a price ratio, never a per-year figure, never a year but 2022-24 (`map_text_problems` holds every text
#: field of the file to that before any of it is shown).
MAP_PATH = Path(__file__).with_name("dlane_map.json")
MAP_SCHEMA = 1
MAP_LABEL = "in-sample: Train years 2022-24, from the operator's census at one-lot natural prices; the screen decides"
#: The unit's verdict words (E5 priced at today's prices by the operator, privately; shown as a word only).
MAP_UNITS = ("yes", "borderline", "no")
#: The bar settings the map was scored under (the file's `bar`); a setting that differs makes the text say so.
MAP_BAR_KEYS = ("active_share", "min_active_years", "out_t_floor", "out_loss_share", "min_entry_days", "cost_ratio",
                "unit_share", "unit_cap_usd")
#: Bounds: the file's rows and lessons, and what each reader shows (the architect at most `MAP_ARCHITECT_ROWS` shapes,
#: one line each; a researcher the `MAP_BRIEF_ROWS` best on its roots).
MAP_ROWS_MAX, MAP_LESSONS_MAX, MAP_LESSON_CHARS, MAP_WORD_CHARS, MAP_HOW_CHARS = 60, 5, 900, 160, 400
MAP_ARCHITECT_ROWS, MAP_BRIEF_ROWS = 30, 5
#: The only years a map text may name; a digit run of four or more is refused unless it is one of them.
MAP_YEARS = (str(FIRST_YEAR), str(FIRST_YEAR + 1), str(LAST_YEAR))
#: Years never named in a map text, even inside a longer digit run (the hidden years, Validation, the holdout).
MAP_REFUSED_YEARS = ("2017", "2018", "2019", "2020", "2021", "2025", "2026")
_MAP_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
#: A decimal a map text may carry: a delta target (0.2, 0.20 ... 0.9) or a one-decimal figure under 10 (a t, 1.5x).
_MAP_DECIMAL = re.compile(r"0\.[1-9]0?|\d\.\d")
_MAP_CLOCK = re.compile(r"(?:[01]\d|2[0-3]):[0-5]\d")
#: A count of three digits stands only in an "N of M" phrase (416 of 448 cells): alone it could be a price level.
_MAP_COUNT = re.compile(r"(?<![\d.,])\d{1,3} of \d{1,3}(?!\d|[.,]\d)")
_MAP_WORD_KEY = re.compile(r"[a-z0-9][a-z0-9_-]{0,15}")
_MAP_CACHE: dict[str, tuple[Any, Any]] = {}


def map_text_problems(text: Any) -> list[str]:
    """Why a map text may not reach an agent ([] when it may): it must be plain one-line ASCII and carry no dollar sign,
    no year but 2022-24 (none of `MAP_REFUSED_YEARS` anywhere, even inside a longer digit run), no grouped number
    (1,234), no digit run of four or more but those years, no three-digit number outside an "N of M" count, and no
    decimal but a delta target or a one-decimal figure under 10 (`_MAP_DECIMAL`): so no dollar amount, price level or
    price ratio."""
    if not isinstance(text, str) or not text.strip():
        return ["empty"]
    problems = []
    if not text.isascii() or any(ord(ch) < 32 or ord(ch) == 127 for ch in text):
        problems.append("not plain one-line ASCII")
    if "$" in text:
        problems.append("a dollar sign")
    problems += [f"names {y}" for y in MAP_REFUSED_YEARS if y in text]
    counts = [m.span() for m in _MAP_COUNT.finditer(text)]
    for m in _MAP_NUMBER.finditer(text):
        tok = m.group()
        if "," in tok:
            problems.append(f"a grouped number ({tok})")
        elif "." in tok:
            if not _MAP_DECIMAL.fullmatch(tok):
                problems.append(f"a figure ({tok})")
        elif len(tok) > 3 and tok not in MAP_YEARS:
            problems.append(f"a number ({tok})")
        elif len(tok) == 3 and not any(a <= m.start() and m.end() <= b for a, b in counts):
            problems.append(f"a three-digit number outside a count ({tok})")
    return problems


def _map_words(raw: Any) -> dict[str, dict[str, str]] | None:
    """The file's glossary {expiry: {key: words}, gate: {key: words}}, each key a short token and each text safe; None
    when either is missing or one entry is not."""
    if not isinstance(raw, Mapping):
        return None
    out: dict[str, dict[str, str]] = {}
    for kind in ("expiry", "gate"):
        block = raw.get(kind)
        if not isinstance(block, Mapping) or not block or len(block) > 12:
            return None
        out[kind] = {}
        for key, words in block.items():
            if not (isinstance(key, str) and _MAP_WORD_KEY.fullmatch(key) and not map_text_problems(key)
                    and isinstance(words, str) and len(words) <= MAP_WORD_CHARS and not map_text_problems(words)):
                return None
            out[kind][key] = words
    return out


def _map_row(raw: Any, words: Mapping[str, Mapping[str, str]]) -> dict[str, Any] | None:
    """One passing shape, normalized, or None when any field is outside the map's vocabulary: roots from `ROOTS` joined
    by "+", a delta target in tenths, an expiry and gates the glossary names, a hold of 1-20 sessions, an HH:MM entry,
    S_D under 10 in size, the unit's verdict word and 0-3 in-market years."""
    if not isinstance(raw, Mapping):
        return None
    roots = raw.get("root").split("+") if isinstance(raw.get("root"), str) else []
    gates = raw.get("gate").split("+") if isinstance(raw.get("gate"), str) else []
    delta, sd = _num(raw.get("delta")), _num(raw.get("S_D"))
    hold, years, entry = raw.get("hold"), raw.get("in_market_years"), raw.get("entry")
    whole = (lambda v, lo, hi: isinstance(v, int) and not isinstance(v, bool) and lo <= v <= hi)
    if not roots or len(set(roots)) != len(roots) or any(r not in ROOTS for r in roots):
        return None
    if not gates or len(set(gates)) != len(gates) or any(g not in words["gate"] for g in gates):
        return None
    if delta is None or not 0.1 <= delta <= 0.9 or abs(delta * 10 - round(delta * 10)) > 1e-9:
        return None
    if sd is None or abs(sd) >= 9.95 or raw.get("expiry") not in words["expiry"] or raw.get("unit") not in MAP_UNITS:
        return None
    if not whole(hold, 1, 20) or not whole(years, 0, 3) or not (isinstance(entry, str) and _MAP_CLOCK.fullmatch(entry)):
        return None
    return {"root": "+".join(roots), "delta": round(delta, 1), "expiry": raw["expiry"], "hold": hold, "entry": entry,
            "gate": "+".join(gates), "S_D": round(sd, 1), "unit": raw["unit"], "in_market_years": years}


def _map_doc(raw: Any) -> dict[str, Any] | None:
    """The map as agents may read it, or None: the schema, `MAP_LABEL` word for word and this module's `OBJECTIVE`; a
    safe glossary, `how` and 1-`MAP_LESSONS_MAX` lessons; 1-`MAP_ROWS_MAX` passing shapes, every one well-formed (one
    bad row and the whole map is refused), sorted by S_D, best first (the file's order among equals)."""
    if not isinstance(raw, Mapping) or raw.get("schema") != MAP_SCHEMA or raw.get("label") != MAP_LABEL \
            or raw.get("objective") != OBJECTIVE:
        return None
    words = _map_words(raw.get("words"))
    how, lessons, passing = raw.get("how"), raw.get("lessons"), raw.get("passing")
    if words is None or not isinstance(how, str) or len(how) > MAP_HOW_CHARS or map_text_problems(how):
        return None
    if not isinstance(lessons, list) or not 1 <= len(lessons) <= MAP_LESSONS_MAX or any(
            not isinstance(x, str) or len(x) > MAP_LESSON_CHARS or map_text_problems(x) for x in lessons):
        return None
    if not isinstance(passing, list) or not 1 <= len(passing) <= MAP_ROWS_MAX:
        return None
    rows = [_map_row(r, words) for r in passing]
    if any(r is None for r in rows):
        return None
    bar_raw = raw.get("bar") if isinstance(raw.get("bar"), Mapping) else {}
    bar = {k: (None if bar_raw[k] is None else _num(bar_raw[k])) for k in MAP_BAR_KEYS if k in bar_raw}
    return {"label": MAP_LABEL, "how": how, "words": words, "lessons": list(lessons),
            "passing": sorted(rows, key=lambda r: -r["S_D"]), "bar": bar,
            # The operator's provenance: never shown to an agent.
            "built_at": str(raw.get("built_at") or ""), "inputs_sha256": str(raw.get("inputs_sha256") or "")}


def train_map(path: str | Path | None = None) -> dict[str, Any] | None:
    """THE TRAIN MAP as agents may read it (`_map_doc`), from `path` (default `MAP_PATH`), or None: a missing, unreadable,
    malformed or unsafe file is no map. Cached on the file's size and mtime; never raises."""
    try:
        p = Path(path) if path is not None else Path(MAP_PATH)
        st = p.stat()
        stamp = (st.st_mtime_ns, st.st_size)
    except Exception:  # noqa: BLE001 - no file, no map
        return None
    hit = _MAP_CACHE.get(str(p))
    if hit is not None and hit[0] == stamp:
        return hit[1]
    try:
        doc = _map_doc(json.loads(p.read_text(encoding="utf-8")))
    except Exception:  # noqa: BLE001 - garbage reads as no map
        doc = None
    _MAP_CACHE[str(p)] = (stamp, doc)
    return doc


def map_on(settings: Mapping[str, Any] | None) -> bool:
    """The map is shown: the lane is on and `dlane.train_map` is true (policy.json; swarm.json false turns it off)."""
    return on(settings) and cfg(settings)["train_map"]


def _map_shape(row: Mapping[str, Any]) -> str:
    """One passing shape on one line, in the map's own words (the key line explains them)."""
    gate = "every session" if row["gate"] == "every" else row["gate"]
    return (f"{row['root']} {row['delta']:.2f}-delta call, expiry {row['expiry']}, hold {row['hold']}, enter "
            f"{row['entry']} ET, gate {gate}: S_D {row['S_D']:.1f}; fits the unit at today's prices: {row['unit']}")


def _map_key(doc: Mapping[str, Any]) -> str:
    words = doc["words"]
    return ("Key: " + "; ".join([f"expiry {k} = {v}" for k, v in words["expiry"].items()]
                                + [f"gate {k} = {v}" for k, v in words["gate"].items()]
                                + ["gate a+b = both at once", "root SPY+QQQ+IWM = one call on each root",
                                   "hold = sessions held", "S_D = the pooled t of daily P&L over Train at 1.0x"]) + ".")


def _map_head(doc: Mapping[str, Any], settings: Mapping[str, Any] | None) -> str:
    c = cfg(settings)
    changed = [k for k, v in doc["bar"].items()
               if (c.get(k) is None) != (v is None) or (v is not None and abs(float(c[k]) - v) > 1e-9)]
    return (f"TRAIN MAP ({MAP_LABEL}). Each shape is {doc['how']}. {ALWAYS_IN_NOTE[0].upper()}{ALWAYS_IN_NOTE[1:]}."
            + (f" The bar's settings have changed since the map was built ({', '.join(changed)}): read it as a guide."
               if changed else ""))


def train_map_text(settings: Mapping[str, Any] | None) -> str:
    """THE TRAIN MAP for the architect's LANES block: the label, the passing shapes one line each (at most
    `MAP_ARCHITECT_ROWS`, best S_D first), the lessons, and where births should aim. "" while the lane is off, while
    `dlane.train_map` is false, or with no map."""
    doc = train_map() if map_on(settings) else None
    if doc is None:
        return ""
    rows = doc["passing"]
    shown = rows[:MAP_ARCHITECT_ROWS]
    lines = [_map_head(doc, settings), _map_key(doc),
             f"THE {len(rows)} PASSING SHAPES (best S_D first"
             + (f"; the first {len(shown)} shown" if len(shown) < len(rows) else "") + "):"]
    lines += [f"- {_map_shape(r)}" for r in shown]
    lines += [f"LESSON {i}: {x}" for i, x in enumerate(doc["lessons"], 1)]
    lines.append("AIM direction cards at these shapes and vary the gate, the hold or the root: a gate is the edge to find "
                 "and this bar does not test it. Each version is still judged on its own Train run, and each lineage gets "
                 "one Validation try and one holdout look: the screen decides, not this map.")
    return "\n".join(lines)


def train_map_brief(settings: Mapping[str, Any] | None, roots: Iterable[str] | None = None) -> str:
    """THE TRAIN MAP for a direction researcher's brief: the label, the lessons and the `MAP_BRIEF_ROWS` best-scoring
    passing shapes on the family's roots (a shape whose roots it all holds), then the best on other roots when it has
    fewer. "" while the lane is off, while `dlane.train_map` is false, or with no map."""
    doc = train_map() if map_on(settings) else None
    if doc is None:
        return ""
    names = [str(r).upper() for r in roots or () if str(r).upper() in ROOTS] or list(ROOTS)
    mine = [r for r in doc["passing"] if set(r["root"].split("+")) <= set(names)]
    others = [r for r in doc["passing"] if r not in mine]
    picked = mine[:MAP_BRIEF_ROWS]
    extra = others[:MAP_BRIEF_ROWS - len(picked)]
    head = (f"THE {len(picked) + len(extra)} BEST-SCORING PASSING SHAPES on your roots ({', '.join(names)})"
            if not extra else
            f"THE BEST-SCORING PASSING SHAPES: {len(picked)} on your roots ({', '.join(names)}), then {len(extra)} on "
            "other roots")
    lines = [_map_head(doc, settings)]
    lines += [f"LESSON {i}: {x}" for i, x in enumerate(doc["lessons"], 1)]
    lines.append(head + ":")
    lines += [f"- {_map_shape(r)}" for r in picked]
    lines += [f"- (other roots) {_map_shape(r)}" for r in extra]
    lines.append(_map_key(doc))
    lines.append("Your own Train run is your score; the screen decides, not this map.")
    return "\n".join(lines)


# ----------------------------------------------------------------------------------------------------------- the agenda
def agenda_problems(text: Any, *, limit: int = AGENDA_MAX) -> list[str]:
    """Why an agenda text may not be installed (D9: the House warns at swarm start, the operator's tool refuses): longer
    than the architect reads (`AGENDA_MAX`, `architect.AGENDA_LOCKED_MAX`), not ASCII, or naming a hidden year. []
    when it may."""
    text = str(text or "")
    problems = []
    if not text.strip():
        problems.append("the agenda is empty")
    if len(text) > int(limit):
        problems.append(f"the agenda is {len(text):,} characters; the architect reads {int(limit):,} and would silently cut "
                        "the rest")
    if not text.isascii():
        problems.append("the agenda is not ASCII")
    named = [y for y in HIDDEN_YEAR_DIGITS if y in text]
    if named:
        problems.append(f"the agenda names a hidden year ({', '.join(named)})")
    return problems


__all__ = ["OBJECTIVE", "ALPHA", "DIRECTION", "LANES", "MODES", "SCREENS", "ALPHA_SCREEN", "FIRST_YEAR", "LAST_YEAR",
           "TRAIN_CLOSE_2024", "ROOTS", "STRUCTURES", "CLASSES", "EQUITY_PREMIUM", "HOLDINGS", "ALWAYS_IN_NOTE", "LABEL",
           "CLOSES_FILE", "HEALTH_FILE", "STATE_KEY", "UNIT_HINT", "K5_KEY", "STARTED_KEY", "LANE_ONLY_KEY", "AGENDA_MAX", "DONE",
           "DEFAULTS", "cfg", "on", "mode_effective", "candidates_open", "k5_state", "k5_trip", "k5_line", "k5_rearm",
           "K5_BASE_KEY", "lane_value",
           "declared_lane", "lane_of", "card_errors", "exposure", "year_rows", "unit_context", "unit_of", "train_score",
           "beside", "robust_verdict", "sort_key", "compact", "compact_robust", "record", "failure_counts", "lane_verdict",
           "screen_effective", "receipt_sha256", "d2_precheck", "d2_pooled_t", "validation_r_sd", "leakage_alarm", "born_counts",
           "last_direction_birth", "alive_direction", "started_at", "lane_only_due", "lane_only_mark", "DirectionQuota",
           "lanes_text", "brief_text", "status_text", "view", "agenda_problems",
           # release D-1b
           "TRY_KEY", "D2_STRUCTURES", "D2_RATES", "D2_INTERVALS", "fp_beside", "fp_of_look", "d2_verdict", "d2_pooled_t_low",
           "GYM_MEAN_ROUNDING", "GYM_T_ROUNDING", "NOT_A_TRY", "SPENT_LOOK",
           "SPENT_TRY", "lineage_tries", "looks_ration", "try_open", "first_try", "try_owed", "lineage_spent", "calls_only",
           "CALLS_ONLY_WHY", "ration_text",
           # the train map (Oct 9, 2026)
           "MAP_PATH", "MAP_LABEL", "MAP_UNITS", "MAP_ARCHITECT_ROWS", "MAP_BRIEF_ROWS", "map_text_problems", "train_map",
           "map_on", "train_map_text", "train_map_brief"]
