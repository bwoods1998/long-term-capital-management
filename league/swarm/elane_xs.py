"""THE PANEL LANE in the swarm (release E4): structure "panel", its agenda cells, the Train bar equity-xs-v1,
Validation, the one look under XS1, lineage and seats.

Owner: package G. E1's and E2's modules get one-line dispatches to this one (package G's patches in
league/swarm/e4_patches/G.md), never new bodies. Every call into league.xs goes through the names of
league/xs/E4_INTERFACES.md; where one of them is not built, or its answer cannot be read, the lane reads "off" or the
step is the House's failure (nothing scored, nothing spent), never a crash in a House job.

A panel family: lane "equity", structure "panel", `roots` [], spec {`lane`, `agenda`, `panel`, `max_names`,
`rebalance`, `weekday`, `e2_route`, `hidden_year`, `gid`}. Its Train record is the family-state key `STATE_KEY`
(generator-readable through `train_facts` only); everything after Train is SEALED (`SEALED`: no generator, brief,
request, map or route choice ever reads it).

THE SWITCH is `elane.panel.mode` (`MODES`): "off" -> "train" (births and the Train bar) -> "gate" (Validation and XS1
looks) -> "live" (a passer may take a seat). THE EFFECTIVE MODE is `mode`: "off" unless `elane.mode` is "gate"; "off"
when the panel manifest is missing or its coverage verdict is "insufficient"; at most "train" without a pinned XS1
receipt (`league.xs.screen.pinned_receipt`: NO RECEIPT, NO LOOK) or with `hs_share` under `spreads_min_share`; at most
"gate" unless `live_ready`. WITH EVERY SWITCH OFF NOTHING OF E4 RUNS, SPENDS OR TRADES.

`live_ready(root, settings)`: THE STORE IS FRESH BY THE CALENDAR AND THE CLOCK (the manifest's `fetched_through` is
the last closed NYSE session or the one before: `CLOCK`, `_last_closed`), the universe deploy is in force (`live_from`
set), today's tradable share of eligible names is at least `live_min_tradable_share`, the committed universe is
younger than `universe_max_age_days`, the last nightly `i6.equal` is True, AND THE TWIN MARKER
(`league.xs.book.TWINS_FILE`, package J's): the file exists, its `through` is the panel store's `fetched_through` or
the session before AND no older than the session before the last closed one, and no listed instance is more than one
session behind its `due` day. So with J unmerged, or its nightly run stopped for two nights, "live" reads as "gate";
and so does a panel store that stopped being written: every other leg is read from the last manifest, and without
the clock a store five nights stale kept the lane "live" on its last good I6 for as long as its files stayed as they
were. One missed night is tolerated at the next morning's sends; a second holds every open.
The swarm process reads that one file and never the forward record's own store (release E3's seal T1).

THE TRAIN BAR equity-xs-v1 (in-sample filter; never evidence; E4-SPEC 8.3). One run a SEEN SPAN (`seen_spans`), each
starting flat; per span the full universe at k 1.0 and at k 1.5 (the 1.5 run with `placebos_train` placebos and
`calls=True`) and each asset half at k 1.5; read pooled (`league.xs.results.pooled`, `league.xs.placebo.stat`); then
the restart check on the k 1.5 runs (E2's `elane_train.restart_check` pattern through the panel kind: `state_check`);
then, AFTER the verdict is recorded, the hidden run, whose result goes to `OOF_KEY` and nowhere else. `BAR_XS` and
`FAILS_XS` name the rules: XA0 (activity: the program's, refutes nothing), XT1, XY1, XH1, XP1, XR1 (`JUDGED_XS`: a
family is REFUTED only on one of these), STATE, WINDOW. THE LOOSENING, stated: six panel Train years, five of them
seen by a family with a hidden year (E2's bar reads seven and six).

THE RESEARCHER'S STEP of a panel family is `step` (E2's `EquityResearcher.step` forwards it, `may_run` first): score
its newest version, review a bar pass under the panel rubric (`review_step`, `REVIEW_XS`), write its next program on
its birth route (`write`), or retire it REFUTED (a version judged on a `JUDGED_XS` rule) or STALLED. Its record has
E2's own shape (`status`, `versions`, `passed_version`, `review`, `passed_review`, `attempts`, `refused`, `infra`), so
E2's queue, upkeep and guard read it through `elane_train.record_of` (patch 7 makes that reader key-aware).

VALIDATION AND THE LOOK FOLLOW THE PINNED PRE-REGISTRATION (XSCREEN-1 revision 2, section 4; `league.xs.screen`), and
the pre-registration gives the House three duties, kept here:
1. BOTH TRAIN SERIES OF EVERY PROGRAM THAT REACHES THE PRE-CHECK ARE KEPT, passed or refused: the residual x
   (`TRAIN_X_KEY`) and the universe excess u (`TRAIN_U_KEY`), by session, from the two whole Train segments at k 1.0
   (`league.xs.runner.Isolated.segments`). `validate` runs them BEFORE the Validation run.
2. THE LINEAGE RULE (`same_lineage`): the same template, or a Train correlation of 0.7 or more IN EITHER SERIES with a
   panel program already looked at OR ALREADY REFUSED AT THE PRE-CHECK (`PRECHECK_KEY`). It is asked before the
   Validation try (a program refused at the pre-check has spent its lineage's try: a clone with a new code sha is the
   same lineage) and again before the look. No Validation-only retry. A lineage that took an XS1 look can take no S2
   look, and the reverse. Neither record is ever cleared by an adoption.
3. THE LOOKS OF EACH AGENDA CELL ARE COUNTED (`cell_looks`), and the count is stated beside every live trade: the
   receipt's sentence (`league.xs.screen.beside_line`, {n_cell}) is recorded with the look (`LOOK_KEY`) and
   `beside_line` hands it to the reports, which print it beside EVERY live panel trade.

THE CAPTAIN'S A22 (from the study's review; binding): BEFORE ANY REAL MONEY ON AN XS1 PASS THE HOUSE ALSO HOLDS
1. A STYLE-OPEN PROGRAM TAKES NO LIVE SEAT ON AN XS1 PASS ALONE. `score` asks the seen spans' full-universe k 1.0
   runs for their style blocks (`league.xs.runner.Isolated.train(..., style=True)`), reads them as one
   (`league.xs.style.pooled`) and keeps the rule's verdict (`league.xs.style.style_open`) in the version's Train
   record under `STYLE_FIELD`. At the look, a passer whose verdict is open, or missing, or made under other figures
   (`league.xs.style.seat_refusal`) is RECORDED AND SHADOWED, NEVER SEATED: the look event and `LOOK_KEY` say passed
   with `seat` `SEAT_STYLE`, the family takes NO band and no proof (so no reader of the bands can seat it), it stays
   alive in the Gym band (`lineage_spent` retires no style-open passer) and the forward record goes on shadowing it;
   the forward route is its way to a seat. Only a passer the rule reads as not open becomes a Candidate.
2. AT MOST `MAX_CELL_LOOKS` XS1 LOOKS AN AGENDA CELL until a forward verdict exists in that cell (`look_room`; the
   study measured that one zero-edge mechanism given eight looks passes at least one in most worlds). No forward
   verdict can exist before the forward route is measured and built, so in this release the cap is flat. A look the
   cap holds back is not spent: the family waits.
3. THE CODE REVIEW AND THE CONTAMINATION PROBE COME BEFORE A LOOK. The equity review of a panel program carries the
   rubric `REVIEW_XS` (no embedded return table, no calendar recognition, and the spec's three); and `probed` holds
   the look back until E3's contamination probe has a published result, with the panel strata `PROBE_STRATA`, for
   the route that wrote the program (`<root>/contamination.json`, aggregates only; while release E3 or its panel
   strata are not merged there is none, and every panel look waits). The probe's reading is recorded with the look.
4. The screen reproduces the study's conformance vectors and one more for the second segment's floor cell alone
   (package E's; `league.xs.screen`).

Imports nothing of league.live at import time (the panel's own decider is built in `runner`). league.xs is imported
inside the functions that need it, as E1's `elane` imports league.equity; this module reads the panel manifest and the
twin marker as JSON (`_manifest`, `_twins`: no numpy), so the live process's band reader (`seatable`) pays a file read.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import threading
import time
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from ..xs import PANELS, STRUCTURE

# ----------------------------------------------------------------------------------------------------------- vocabulary
OBJECTIVE = "equity-xs-v1"
LANE = "equity"
MODES = ("off", "train", "gate", "live")
#: The family-state key of a panel family's Train record: {status, versions {n: {n, at, identity (`xs_identity()`),
#: verdict, fails, facts, state (the restart check's counts), style}}, passed_version, review, passed_review, attempts,
#: refused, infra}: E2's record's shape under the panel's own key.
STATE_KEY = "elane_xs"
#: SEALED family-state keys (package G's patch adds them to `elane_seal.SEALED_KEYS`): the program's floor; its two
#: Train series by session (the lineage rule's, kept from the pre-check on); the pre-check's record (which version
#: reached it and whether it was refused); the Train placebo ranks; the halves' figures; the hidden run; the look.
FLOOR_KEY = "elane_xs_floor"
TRAIN_X_KEY = "elane_xs_train_x"
TRAIN_U_KEY = "elane_xs_train_u"
PRECHECK_KEY = "elane_xs_precheck"
PLACEBO_KEY = "elane_xs_placebo"
HALVES_KEY = "elane_xs_halves"
OOF_KEY = "elane_xs_oof"
LOOK_KEY = "elane_xs_look"
SEALED = (FLOOR_KEY, TRAIN_X_KEY, TRAIN_U_KEY, PRECHECK_KEY, PLACEBO_KEY, HALVES_KEY, OOF_KEY, LOOK_KEY)
#: Store kv keys: the day's child seconds of panel Train {utc_day: seconds}; the zero-edge job's weeks; the alerts.
CPU_KEY = "elane_xs_cpu"
ZERO_KEY = "elane_xs_zero_edge"
ALERTS_KEY = "elane_xs_alerts"
#: The store's kv key of the last time a panel Train judgment completed (a child that fails one program while this
#: moves on is that program's fault: "RUN", E2's rule with the panel's own clock).
TRAIN_OK_KEY = "elane_xs_train_ok_at"
#: THE CAPTAIN'S A22. The Train record's field of the style verdict (per version: `league.xs.style.style_open`'s
#: answer); what a look's record says of a passer's seat; the cap on a cell's XS1 looks (a House rule, never a
#: setting); E3's probe file under the root and the panel strata a route's result must hold before a look; and what
#: the equity review's rubric gains for a panel program.
STYLE_FIELD = "style"
SEAT_CANDIDATE = "candidate"
SEAT_STYLE = "style-open"
#: A pass whose sentence could not be filled (duty 3: the sentence is stated beside EVERY live panel trade, so a pass
#: that has none is recorded and never seated by the look).
SEAT_UNSTATED = "unstated"
MAX_CELL_LOOKS = 2
PROBE_FILE = "contamination.json"
PROBE_STRATA = ("P4", "P5", "P6")
REVIEW_XS = (
    "an embedded return table: constants, a string or a structure that could hold returns, ranks or outcomes of "
    "past sessions or names",
    "calendar recognition: any test that could tell which year, month or event a session is from the calendar "
    "counts, the market's path or the slots' histories",
    "any use of ctx.ids beyond naming targets",
    "any constant that could name a calendar period",
    "any search for a price level",
)
#: The panel review's objective (the record E1's `reviewed` reads names it: a look takes no review of another rubric).
REVIEW_OBJECTIVE = "equity-xs-review-1"
#: The settings block (`elane.panel`) and the screen's pin (`elane.screens.equity_xs`).
SETTINGS_KEY = "panel"
SCREEN_KEY = "equity_xs"
#: The panel decider's log, under the swarm's root.
DECIDER_LOG = "xs-decider.log"
#: The House's daily store (E1's root: `elane.STORE_DIR`), the panel manifest and the universe manifest under it, as
#: league/xs/store.py lays them out (a test holds the three to that module's names).
STORE_DIR = "equity-daily"
PANEL_MANIFEST = "panel/PANEL_MANIFEST.json"
UNIVERSE_MANIFEST = "universe/UNIVERSE_MANIFEST.json"

#: `elane.panel` (policy.json; swarm.json over it): the defaults, and each key's bound. A value outside its bound reads
#: as its default. `census_notes` is swarm.json only (policy.json ships {}: no census word is ever committed).
DEFAULTS: dict[str, Any] = {
    "mode": "off", "panels": ["sp500"], "birth_share": 0.5, "max_alive": 12, "max_names": 12,
    "rebalance": ["weekly", "monthly"], "train_budget": 4, "placebos_train": 200, "cpu_seconds_day": 14400,
    "run_budget_seconds": 600, "zero_edge_programs": 100, "coverage_min": 0.97, "spreads_min_share": 0.90,
    "membership_max_stale_days": 45, "universe_max_age_days": 400, "live_min_tradable_share": 0.95,
    "census_notes": {},
}
BOUNDS: dict[str, tuple[float, float]] = {
    "birth_share": (0.0, 1.0), "max_alive": (0, 100), "max_names": (5, 40), "train_budget": (1, 4),
    "placebos_train": (200, 1000), "cpu_seconds_day": (0, 36000), "run_budget_seconds": (60, 600),
    "zero_edge_programs": (20, 400), "coverage_min": (0.97, 1.0), "spreads_min_share": (0.5, 1.0),
    "membership_max_stale_days": (7, 120), "universe_max_age_days": (30, 500),
    "live_min_tradable_share": (0.90, 1.0),
}
CENSUS_NOTE_MAX = 200
#: The label every census note is shown under (E4-SPEC 8.2): the captain's reading of a cell, never evidence.
CENSUS_LABEL = "in-sample 2010-24, best of 7; not evidence"
#: `elane.screens.equity_xs` as policy.json ships it: `league.xs.screen.PIN_KEYS` in order, EVERY value a null (a
#: pin is whole or it is nulls: the screen's own test holds a half-filled block to be neither), and with nulls every
#: panel look waits. The integrator fills it from the receipt in the commit that lands the receipt.
SCREEN_NULLS: dict[str, Any] = dict.fromkeys((
    "name", "screen", "receipt_sha256", "c_XS", "c_margin", "alpha_plac", "placebo_draws", "rung", "fp_cap",
    "owner_wall", "validation_tries", "holdout_looks", "retry", "flags", "screen_flags", "beside"))

#: THE PANEL AGENDA: the spec's `agenda` keys, each with its published prior (no figure). `earnings_drift` stays
#: unavailable (no earnings dates on the House).
PANEL_AGENDA: dict[str, dict[str, Any]] = {
    "xs_reversal": {"what": "1-week and 1-month reversal", "prior": "Lehmann 1990; Jegadeesh 1990"},
    "xs_momentum": {"what": "12-1 momentum", "prior": "Jegadeesh and Titman 1993"},
    "xs_industry_momentum": {"what": "industry momentum (sectors are the ctx's salted codes)",
                             "prior": "Moskowitz and Grinblatt 1999"},
    "xs_low_vol": {"what": "low volatility, low beta",
                   "prior": "Ang, Hodrick, Xing and Zhang 2006; Frazzini and Pedersen 2014"},
    "xs_52w_high": {"what": "nearness to the 52-week high", "prior": "George and Hwang 2004"},
    "xs_rotation": {"what": "rank within sectors, hold the leaders", "prior": "named in the card"},
    "xs_other": {"what": "another cross-sectional rule", "prior": "its own prior, named in the card"},
}
#: The agenda key of a card that names none of the panel's.
OTHER = "xs_other"

#: The bar's rules (rules, never market figures).
BAR_XS: dict[str, Any] = {"min_rebalances": 40, "min_invested": 0.5, "t_min": 2.0, "year_share": 2 / 3,
                          "placebo_rank": 0.95, "cost_ratio": 0.5, "state_resets": (3, 7), "state_match": 0.99}
FAILS_XS: dict[str, str] = {
    "XA0": "fewer than 40 rebalances with a non-empty target, or invested on fewer than half the sessions",
    "XT1": "the residual's t at 1.5x the half-spread is under 2.0 on the seen spans pooled",
    "XY1": "the residual's sum at 1.5x is positive in too few of the seen years, or in no seen year of a segment",
    "XH1": "the residual's sum at 1.5x is not positive in both asset halves",
    "XP1": "the pooled t at 1.5x ranks under 95% of the matched placebos' on the same sessions",
    "XR1": "the residual's sum at 1.0x is not positive, or its sum at 1.5x is under half of it",
    "STATE": "asked again after a fresh load, the program's targets matched the uninterrupted run's on fewer than 99% "
             "of its calls",
    "WINDOW": "the Train result carried a day outside its seen spans, or of 2016, 2020 or 2021, and was refused whole",
}
#: The verdicts of a program that could not be judged (E2's words, in the panel's): they judge a program, never the
#: mechanism, and with `STATE` and `XA0` they refute nothing.
PROGRAM_FAILS: dict[str, str] = {
    "RUN": "the panel's decider child failed this program's Train run again and again while other programs' runs "
           "completed",
    "DQ": "the program was disqualified on Train by its own errors or timeouts",
    "LOAD": "the panel's decider child refused to load the program",
    "REVIEW": "the equity review refused the program under the panel rubric (an embedded table, calendar recognition, "
              "a use of the slot ids beyond naming targets, a level search or lookahead)",
}
#: The fails that judge the MECHANISM on Train: a family is REFUTED only with a version judged by one of these.
JUDGED_XS = ("XT1", "XY1", "XH1", "XP1", "XR1")
#: The half-spread multiples of the bar's runs (E1's `K_BASE` and `K_STRESS`: a test holds them equal).
K_BASE, K_STRESS = 1.0, 1.5
#: The asset halves (D18).
HALVES = (0, 1)
#: What a decide of the restart check is loaded with (XS.md: 1 second a call, 25 errors), and the weight tolerance of
#: a matching call.
DECIDE_TIMEOUT, DECIDE_MAX_ERRORS = 1.0, 25
WEIGHT_TOL = 1e-6
#: The flags beside a Train verdict (never a bar): a pass that fails at a 100% vanish haircut; a verdict made while
#: fewer than `spreads_min_share` of the Train eras' member-days were charged a sampled half-spread of their own name
#: (the manifest's `hs_share`: league/ops/equity_panel.py `hs_share`).
FLAG_SURVIVORSHIP = "survivorship-sensitive"
FLAG_COSTS = "provisional costs"
#: The researcher's settings a panel family shares with E2 (`elane.e2`: attempts, errors, pace, tokens, the cap of
#: refutations that closes a cell); `train_budget` is the panel's own (`elane.panel.train_budget`).
MAP_LABEL = ("in-sample: the swarm's own panel Train runs, Train years 2017-19 and 2022-24 (one of them hidden from "
             "each family), the residual against matched placebos at 1.0x and 1.5x the half-spread; the screen XS1 "
             "decides")
REFUTED_TAG = "REFUTED"
STALLED_TAG = "STALLED"
#: The longest backoff after a failure of the House's (E2's figure).
BACKOFF_MAX = 6 * 3600.0
#: Seconds the effective mode is reused for a root in one process (`seatable` is asked by the live process's band
#: reader every minute; the settings and two small JSON files are then read at most this often).
MODE_TTL = 30.0
#: The public causes of a panel retirement before any look (`lineage_spent`): rules only, no figure.
SAME_LINEAGE_XS = ("its program is the same lineage as a panel program already looked at or already refused at its "
                   "Validation pre-check (XS1: the same template, or Train residuals or universe excesses correlating "
                   "at 0.7 or more): one Validation try and one sealed look a lineage, so it took neither")
TRAIN_ENDED = ("its program was ended by its own errors on a whole Train segment: no Train series could be kept for "
               "it, so it took no Validation try")
EARLY_CAUSES = {"same lineage": SAME_LINEAGE_XS, "train run": TRAIN_ENDED}

#: THE CLOCK the lane's freshness is read by (`_live_legs`: epoch seconds). The process's own; a test hands in its own.
CLOCK: Callable[[], float] = time.time

_runners: dict[str, Any] = {}
_deciders: dict[str, Any] = {}
_runners_lock = threading.Lock()
_mode_cache: dict[tuple[str, str], tuple[float, str]] = {}
_json_cache: dict[str, tuple[tuple[int, int], Any]] = {}
_cache_lock = threading.Lock()


# ------------------------------------------------------------------------------------------------------ small helpers
def _num(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def _spec(fam: Mapping[str, Any] | None) -> Mapping[str, Any]:
    spec = (fam or {}).get("spec") if isinstance(fam, Mapping) else None
    if isinstance(spec, str):
        try:
            spec = json.loads(spec)
        except (TypeError, ValueError):
            spec = None
    return spec if isinstance(spec, Mapping) else {}


def _state(fam: Mapping[str, Any] | None) -> Mapping[str, Any]:
    state = (fam or {}).get("state") if isinstance(fam, Mapping) else None
    return state if isinstance(state, Mapping) else {}


def _plain(value: Any, depth: int = 0) -> Any:
    """A JSON-safe copy of a screen answer (numpy scalars and arrays to floats and lists; non-finite floats to None)."""
    if depth > 8:
        return None
    if isinstance(value, Mapping):
        return {str(k): _plain(v, depth + 1) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v, depth + 1) for v in value]
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return value
    if isinstance(value, int):
        return int(value)
    tolist = getattr(value, "tolist", None)
    if callable(tolist):
        return _plain(tolist(), depth + 1)
    try:
        f = float(value)
    except (TypeError, ValueError):
        return str(value)
    return f if math.isfinite(f) else None


def _read_json(path: Path) -> Any:
    """A small JSON file, re-read only when its size or modification time moved; None when it cannot be read."""
    key = str(path)
    try:
        stat = path.stat()
    except OSError:
        return None
    mark = (int(stat.st_mtime_ns), int(stat.st_size))
    with _cache_lock:
        held = _json_cache.get(key)
    if held is not None and held[0] == mark:
        return held[1]
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    with _cache_lock:
        _json_cache[key] = (mark, value)
    return value


def _day(value: Any) -> dt.date | None:
    """An ISO day (or a timestamp that begins with one) as a date; None when it is not one."""
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------------------------------------- settings and mode
def cfg(settings: Mapping[str, Any] | None) -> dict[str, Any]:
    """`elane.panel` with every key held to its bound (a malformed value is its default), plus "screen": the
    `elane.screens.equity_xs` block as it is."""
    lane = settings.get("elane") if isinstance(settings, Mapping) else None
    lane = lane if isinstance(lane, Mapping) else {}
    raw = lane.get(SETTINGS_KEY)
    raw = raw if isinstance(raw, Mapping) else {}
    out: dict[str, Any] = {key: (list(value) if isinstance(value, list) else dict(value) if isinstance(value, dict)
                                 else value) for key, value in DEFAULTS.items()}
    if raw.get("mode") in MODES:
        out["mode"] = raw["mode"]
    for key, (lo, hi) in BOUNDS.items():
        x = _num(raw.get(key))
        if x is None or not lo <= x <= hi:
            continue
        if isinstance(DEFAULTS[key], int):
            if float(x).is_integer():
                out[key] = int(x)
        else:
            out[key] = float(x)

    def words(key: str, allowed: Sequence[str]) -> None:
        value = raw.get(key)
        if isinstance(value, list):
            kept = list(dict.fromkeys(str(v) for v in value if isinstance(v, str) and v in allowed))
            if kept:
                out[key] = kept

    words("panels", PANELS)
    words("rebalance", _rebalances())
    notes = raw.get("census_notes")
    if isinstance(notes, Mapping):
        out["census_notes"] = {str(k): " ".join(str(v).split())[:CENSUS_NOTE_MAX] for k, v in notes.items()
                               if k in PANEL_AGENDA and isinstance(v, str) and v.strip()}
    screens = lane.get("screens")
    block = screens.get(SCREEN_KEY) if isinstance(screens, Mapping) else None
    out["screen"] = dict(block) if isinstance(block, Mapping) else {}
    return out


def _rebalances() -> tuple[str, ...]:
    """`league.xs.config.REBALANCE` (the schedules a panel program may declare)."""
    from ..xs import config as xconfig

    return tuple(xconfig.REBALANCE)


def _lane_on(settings: Mapping[str, Any] | None) -> bool:
    """`elane.mode` is "gate" (E1's `elane.on`); an `elane` that cannot be read is off."""
    try:
        from . import elane

        return bool(elane.on(settings))
    except Exception:  # noqa: BLE001 - an unreadable switch is off
        return False


def pin(policy: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
    """THE PIN: `elane.screens.equity_xs` of the REPOSITORY's policy.json (`policy`: a parsed document, or its `elane`
    block), never the box's swarm.json: a receipt is pinned by a reviewed pull request, not by a setting. {} when
    there is none."""
    if policy is None:
        try:
            from . import settings as settings_mod

            policy, _ = settings_mod.read_policy()
        except Exception:  # noqa: BLE001 - no file: no receipt
            policy = {}
    block = policy.get("elane") if isinstance(policy, Mapping) and isinstance(policy.get("elane"), Mapping) else policy
    screens = block.get("screens") if isinstance(block, Mapping) and isinstance(block.get("screens"), Mapping) else {}
    return screens.get(SCREEN_KEY) if isinstance(screens.get(SCREEN_KEY), Mapping) else {}


def receipt(*, policy: Mapping[str, Any] | None = None, repo: str | Path | None = None) -> tuple[Any, str | None]:
    """(the pinned XS1 receipt, None) or (None, why): `pin`, then `league.xs.screen.pinned_receipt` (a block of
    nulls, a missing or malformed value, a figure the pre-registration does not allow: None), then THE RECEIPT'S BYTES
    as E1 holds its own: where a file sits at `screen.RECEIPT_PATH` under `repo` (default: this release),
    `screen.load_receipt` must read it under the pinned sha256 to the very figures the pin carries; where nothing is
    there, there is nothing to compare (docs/benchmarks/ never reaches the House box, and CI holds the pin to the file
    on the commit the box runs). NO RECEIPT, NO LOOK."""
    block = dict(pin(policy))
    try:
        from ..xs import screen as S

        pinned = S.pinned_receipt(block)
    except Exception as exc:  # noqa: BLE001 - a receipt that cannot be read judges nothing (a stub that is not built too)
        return None, f"XS1 refused: the pinned receipt cannot be read ({type(exc).__name__})"
    if pinned is None:
        return None, ("XS1 refused: no receipt is pinned in the repository's policy.json (elane.screens.equity_xs), or "
                      "the screen does not accept its figures")
    try:
        import dataclasses

        from . import elane

        path = Path(elane.REPO if repo is None else repo) / S.RECEIPT_PATH
        if path.exists():
            loaded = S.load_receipt(path, pinned_sha256=pinned.receipt_sha256)
            if dataclasses.replace(loaded, fp={}) != dataclasses.replace(pinned, fp={}):
                return None, f"XS1 refused: the figures pinned in policy.json are not the receipt file's ({S.RECEIPT_PATH})"
    except Exception as exc:  # noqa: BLE001 - a receipt file that cannot be judged judges nothing
        return None, f"XS1 refused: the receipt file cannot be checked ({type(exc).__name__}: {str(exc)[:160]})"
    return pinned, None


def _manifest(root: str | Path | None) -> Mapping[str, Any] | None:
    """panel/PANEL_MANIFEST.json under the state root's daily store, as `league.xs.store.write_panel` wrote it; None
    when it is missing or is no object."""
    if root is None:
        return None
    doc = _read_json(Path(root) / STORE_DIR / PANEL_MANIFEST)
    return doc if isinstance(doc, Mapping) else None


def _settings_of(root: str | Path | None, settings: Mapping[str, Any] | None) -> Mapping[str, Any]:
    """`settings`, else the settings of the state root (`settings.load`), else {} (every switch off)."""
    if settings is not None:
        return settings
    try:
        from . import settings as settings_mod

        return settings_mod.load(root) if root is not None else settings_mod.load()
    except Exception:  # noqa: BLE001 - settings that cannot be read are off
        return {}


def _mode_why(settings: Mapping[str, Any] | None, root: str | Path | None = None, *,
              policy: Mapping[str, Any] | None = None, legs: Callable[..., tuple[bool, str | None]] | None = None
              ) -> tuple[str, str | None]:
    """(THE EFFECTIVE MODE, why it is not the setting's own or None): `mode`'s rule. `legs`: the reader of the live
    legs: `live_ready` (the default: a leg it cannot read is not ready, so the mode reads "gate") or `_live_legs`
    (which raises on one: `seat_word` then says it cannot tell). It raises on a setting it cannot read: `mode`
    reads that as "off"."""
    if not _lane_on(settings):
        return "off", "the equity lanes are off (elane.mode)"
    c = cfg(settings)
    wanted = MODES.index(c["mode"])
    if wanted == 0:
        return "off", None
    cap, why = MODES.index("live"), None
    if root is None:
        cap, why = MODES.index("gate"), "no state root: the store's side cannot be read"
    else:
        manifest = _manifest(root)
        if manifest is None or manifest.get("verdict") not in ("ok", "low_coverage"):
            # no panel store, or a coverage the lane cannot stand on ("insufficient")
            return "off", ("the panel store has no manifest" if manifest is None else
                           f"the panel store's coverage verdict is {str(manifest.get('verdict'))[:40]!r}")
        share = _num(manifest.get("hs_share"))
        if share is None or share < c["spreads_min_share"]:
            # provisional costs: research only
            cap, why = min(cap, MODES.index("train")), "the spreads' share is under elane.panel.spreads_min_share"
    if min(wanted, cap) > MODES.index("train"):
        pinned, refusal = receipt(policy=policy)
        if pinned is None:
            cap, why = min(cap, MODES.index("train")), refusal  # NO RECEIPT, NO LOOK
    if min(wanted, cap) > MODES.index("gate"):
        ready, leg = (legs or live_ready)(root, settings) if root is not None else (False, None)
        if not ready:
            cap, why = min(cap, MODES.index("gate")), leg
    return MODES[min(wanted, cap)], (why if cap < wanted else None)


def mode(settings: Mapping[str, Any] | None, root: str | Path | None = None, *,
         policy: Mapping[str, Any] | None = None) -> str:
    """THE EFFECTIVE MODE (the module docstring), one of `MODES`. Without a `root` the store-side conditions cannot be
    read: at most the settings' own mode, and never "live". Never raises: whatever cannot be read lowers the mode."""
    try:
        return _mode_why(settings, root, policy=policy)[0]
    except Exception:  # noqa: BLE001 - a mode that cannot be read is off
        return "off"


def status(settings: Mapping[str, Any] | None, root: str | Path | None = None, *, now: float | None = None
           ) -> dict[str, Any]:
    """THE LANE'S MODE AS A REPORT SAYS IT (the swarm's heartbeat `equity.panel`, the dlane report's panel section):
    {"setting": `elane.panel.mode` as set, "mode": the effective mode, "why": the leg that holds the effective mode
    under the setting, or None}. The reason was computed by `_mode_why` and reached no status, heartbeat or alert:
    a captain who set "gate" with the spreads' share under its bound read "train" nowhere, and no line said why.
    Never raises (a status never fails its reader)."""
    try:
        setting = cfg(settings)["mode"]
    except Exception:  # noqa: BLE001
        setting = "off"
    try:
        legs = (lambda r, s: live_ready(r, s, now=now)) if now is not None else None
        found, why = _mode_why(settings, root, legs=legs)
    except Exception as exc:  # noqa: BLE001 - what `mode` reads as "off"
        found, why = "off", f"the lane's settings or files could not be read ({type(exc).__name__})"
    return {"setting": setting, "mode": found, "why": None if why is None else str(why)[:300]}


#: `health`'s alarms (each a `swarm.status` alert, once a UTC day; the days are kept in the kv `ALERTS_KEY`).
HEALTH = ("mode", "spreads", "universe_age", "stale")


def health(store: Any, settings: Mapping[str, Any] | None, root: str | Path | None, now: float) -> list[str]:
    """THE LANE'S OWN ALARMS (E4-SPEC 17; the review's spec-6: three of them had no detector, and a lane stopped by a
    leg said so nowhere), raised by the swarm loop once an equity round and each said once a UTC day. All warnings
    (what is critical while a panel program is live is the book's and the pre-open's): with the lane's switch up,
    - "mode": the effective mode is under the setting, with the leg that holds it there;
    - "spreads": the setting is "gate" or above and the spreads' share is under `spreads_min_share` (the lane reads
      "train": no Validation, no look);
    - "universe_age": the committed stock universe is older than `universe_max_age_days` (an owner step: regenerate);
    - "stale": the panel store's last session is older than the session before the last closed one (the nightly
      `equity_panel` job has not written it for two nights).
    Returns the alarms it raised now. Never raises; with the switch off it reads nothing."""
    raised: list[str] = []
    try:
        c = cfg(settings)
        if c["mode"] == "off" or not _lane_on(settings) or root is None:
            return raised
        said = status(settings, root, now=now)
        found: dict[str, str] = {}
        if said["mode"] != said["setting"]:
            found["mode"] = (f"elane.panel.mode is set \"{said['setting']}\" and the lane reads \"{said['mode']}\": "
                             f"{said['why'] or 'no leg named'}")
        manifest = _manifest(root)
        if manifest is not None:
            share = _num(manifest.get("hs_share"))
            if MODES.index(c["mode"]) >= MODES.index("gate") and (share is None or share < c["spreads_min_share"]):
                found["spreads"] = (f"the spreads' share ({'unknown' if share is None else f'{share:.3f}'}) is under "
                                    f"elane.panel.spreads_min_share ({c['spreads_min_share']}): a Train pass is under "
                                    "provisional costs, and no Validation try and no look runs")
            through = _day(manifest.get("fetched_through"))
            since = _day(manifest.get("live_from")) if manifest.get("live_from") else None
            born = (_day(manifest.get("universe_at")) if manifest.get("universe_at") else None) or since
            if through is not None and born is not None and (through - born).days > c["universe_max_age_days"]:
                found["universe_age"] = ("the committed stock universe is older than elane.panel.universe_max_age_days "
                                         f"({c['universe_max_age_days']}): regenerate it (an owner deploy)")
            floor = _fresh_floor(now)
            if through is not None and floor is not None and through < floor:
                found["stale"] = (f"{STALE}: its last session is {through.isoformat()} (the nightly equity_panel job has "
                                  "not written it for two nights)")
        if not found:
            return raised
        day = _utc_day(now)
        with store.atomic():
            held = store.get(ALERTS_KEY)
            held = dict(held) if isinstance(held, Mapping) else {}
            told = dict(held.get("health") or {}) if isinstance(held.get("health"), Mapping) else {}
            fresh = [name for name in HEALTH if name in found and told.get(name) != day]
            if fresh:
                store.put(ALERTS_KEY, {**held, "health": {**told, **{name: day for name in fresh}}})
        for name in fresh:
            store.event("swarm.status", None, {"action": f"elane_xs_{name}", "alert": True,
                                                "text": f"the panel lane: {found[name]}"[:400]})
            raised.append(name)
    except Exception:  # noqa: BLE001 - an alarm that cannot be read or written stops no round
        pass
    return raised


def _sessions_between(first: dt.date, last: dt.date) -> list[dt.date]:
    """The NYSE sessions from `first` through `last` (`league.equity.store.nyse_sessions`)."""
    from ..equity.store import nyse_sessions

    return [day for day, _ in nyse_sessions(first, last)]


def _session_before(day: dt.date) -> dt.date | None:
    """The NYSE session before `day`."""
    days = _sessions_between(day - dt.timedelta(days=10), day - dt.timedelta(days=1))
    return days[-1] if days else None


def _last_closed(now: float) -> dt.date | None:
    """The last NYSE session whose close has passed at epoch `now` (`league.equity.schedule.moments`: 16:00 New York,
    13:00 on an early close), None when the calendar holds none in ten days."""
    from ..equity import schedule as S

    day = S.ny_day(float(now))
    for _ in range(10):
        m = S.moments(day)
        if m is not None and m.close_at <= float(now):
            return day
        day -= dt.timedelta(days=1)
    return None


def _fresh_floor(now: float) -> dt.date | None:
    """The oldest session a nightly file may be through and still be FRESH at `now`: the session before the last closed
    one (one missed night is tolerated at the next morning's sends; from that day's close on it is stale)."""
    last = _last_closed(now)
    return None if last is None else _session_before(last)


def _twins_ready(root: str | Path, through: dt.date, floor: dt.date | None = None) -> str | None:
    """THE TWIN MARKER's leg of `live_ready`: why it fails, or None (the module docstring). `floor`: the oldest
    session the marker may be through by the clock (`_fresh_floor`)."""
    from ..xs import book as xbook

    doc = _read_json(Path(root) / STORE_DIR / xbook.TWINS_FILE)
    if not isinstance(doc, Mapping) or doc.get("version") != xbook.TWINS_VERSION:
        return "the twin marker is missing (the forward record's nightly run has not written it: package J)"
    marked = _day(doc.get("through"))
    before = _session_before(through)
    if marked is None or marked not in (through, before) or (floor is not None and marked < floor):
        return "the twin marker is behind the panel store (the forward record's nightly run stopped)"
    instances = doc.get("instances")
    if not isinstance(instances, Mapping):
        return "the twin marker lists no instances"
    for key, row in instances.items():
        row = row if isinstance(row, Mapping) else {}
        due = _day(row.get("due")) if row.get("due") is not None else None
        if row.get("due") is not None and due is None:
            return f"the twin marker's row of {key} cannot be read"
        if due is None:
            continue
        last = _day(row.get("last"))
        floor = _session_before(due)
        if last is None or floor is None or last < floor:
            return f"the shadow twin of {key} is more than one session behind"
    return None


def _tradable_share(root: str | Path, day: dt.date) -> float | None:
    """Today's tradable share of the index's unmasked members (`league.xs.store.Universe`): the members of `day` whose
    symbol is in the constitution's stock universe in force, over the members. None when it cannot be read."""
    from ..xs.store import Universe

    universe = Universe(Path(root) / STORE_DIR)
    members = list(universe.members(day))
    if not members:
        return None
    allowed = set(universe.tradable(day))
    return sum(1 for _, symbol in members if symbol in allowed) / len(members)


STALE = "the panel store is stale"


def _live_legs(root: str | Path, settings: Mapping[str, Any] | None, *, now: float | None = None
               ) -> tuple[bool, str | None]:
    """`live_ready`'s legs, in its order: (ready, the first leg that fails). It RAISES on a leg it cannot read. `now`:
    epoch seconds (`CLOCK()` when None)."""
    c = cfg(settings)
    manifest = _manifest(root)
    if manifest is None:
        return False, "the panel store has no manifest"
    through = _day(manifest.get("fetched_through"))
    if through is None:
        return False, "the panel manifest names no last session"
    floor = _fresh_floor(CLOCK() if now is None else now)
    if floor is None:
        return False, "the calendar names no closed session (the panel store's freshness cannot be read)"
    if through < floor:
        return False, (f"{STALE}: its last session is {through.isoformat()} and the session before the last closed one "
                       f"is {floor.isoformat()} (the nightly equity_panel job has not written it for two nights)")
    since = _day(manifest.get("live_from")) if manifest.get("live_from") else None
    if since is None:
        return False, "the universe deploy is not in force (the panel manifest's live_from is not set)"
    share = _tradable_share(root, through)
    if share is None or share < c["live_min_tradable_share"]:
        return False, ("the tradable share of the index's members is under elane.panel.live_min_tradable_share "
                       "(regenerate the universe: an owner deploy)")
    born = (_day(manifest.get("universe_at")) if manifest.get("universe_at") else None) or since
    if (through - born).days > c["universe_max_age_days"]:
        return False, "the committed universe is older than elane.panel.universe_max_age_days"
    i6 = manifest.get("i6")
    if not isinstance(i6, Mapping) or i6.get("equal") is not True:
        return False, "the last nightly I6 did not hold (the live ctx is not proved equal to the Gym's)"
    why = _twins_ready(root, through, floor)
    if why is not None:
        return False, why
    return True, None


def live_ready(root: str | Path, settings: Mapping[str, Any] | None, *, now: float | None = None
               ) -> tuple[bool, str | None]:
    """(ready, the first leg that fails): the store's freshness by the clock, the universe deploy, the tradable share,
    the universe's age, the last I6, the twin marker (the module docstring). THE UNIVERSE'S AGE is read from the
    manifest's `universe_at` (the first session the stock list now in force was read by the panel job) and, where the
    job writes none, from `live_from` (the first deploy): it fails closed `universe_max_age_days` after whichever it
    reads. `now`: epoch seconds (`CLOCK()` when None). Never raises."""
    try:
        return _live_legs(root, settings, now=now)
    except Exception as exc:  # noqa: BLE001 - a leg that cannot be read is not ready
        return False, f"the live legs cannot be read ({type(exc).__name__})"


#: `seat_word`'s answers (league/equity/families.py `standing` hands them to the book): the lane is live; THE CAPTAIN'S
#: SWITCH is under "live" (positive evidence: the book retires the instance and its lots exit at the next open); A
#: STORE-SIDE LEG of the lane failed (its opens stop, its exits go on, nothing is retired: E4-SPEC 17); it cannot be told.
SEAT_LIVE, SEAT_DEMOTED, SEAT_HELD, SEAT_UNKNOWN = "live", "demoted", "held", "unknown"


def seat_word(root: str | Path) -> tuple[str, str]:
    """THE LANE'S OWN WORD ON A SEAT, for a panel program that is ALREADY SEATED (`bands.equity_seat_withdrawn`, which
    E1's `league.equity.families.EquityFamilies.standing` asks before the book retires an instance whose family has no
    row): (code, why).

    - `SEAT_LIVE` while the effective mode is "live".
    - `SEAT_DEMOTED` ONLY WHEN THE SETTING SAYS SO: the box's swarm.json was read and `elane.panel.mode` is under
      "live", or `elane.mode` is not "gate" (the captain put a switch down: the rollback of E4-SPEC 15's patch 16).
      The book retires the instance and its lots exit at the next open by E1's rule.
    - `SEAT_HELD` when the setting is "live" and a STORE-SIDE LEG fails (the coverage verdict, the spreads' share, the
      receipt, any leg of `live_ready`: the universe deploy, the tradable share, the universe's age, THE STORE'S
      FRESHNESS, the nightly I6, the twin marker), the leg named. E4-SPEC 17: "`live_ready` False while a panel
      instance is live: its opens stop, exits go on". Nothing is retired and nothing is sold on it: one restated bar
      among 515 columns, a marker two sessions old or a share that slipped under its bound is no reason to liquidate
      a basket the Gym twin goes on holding.
    - `SEAT_UNKNOWN` when it cannot be told (a swarm.json, a manifest or a marker that is there and cannot be read:
      a file being rewritten; a leg that raised). The book retires only on positive evidence (A8.5).

    In every case but the first `bands.read` gives the family no row, so it OPENS nothing (`live._seat_block` holds
    every entry at the send). Never raises."""
    try:
        root = Path(root)
        from . import settings as settings_mod

        from ..xs import book as xbook

        for path, what in ((root / "swarm.json", "the box's swarm.json"),
                           (root / STORE_DIR / PANEL_MANIFEST, "the panel manifest"),
                           (root / STORE_DIR / xbook.TWINS_FILE, "the twin marker")):
            try:
                if not isinstance(json.loads(path.read_text(encoding="utf-8")), Mapping):
                    return SEAT_UNKNOWN, f"{what} is no object"
            except FileNotFoundError:
                continue  # no file: the policy alone decides; a missing manifest or marker is a leg of the rule
            except (OSError, ValueError) as exc:
                return SEAT_UNKNOWN, f"{what} could not be read ({type(exc).__name__})"
        settings = settings_mod.load(root)
        found, why = _mode_why(settings, root, legs=_live_legs)
        if found == "live":
            return SEAT_LIVE, ""
        said = (f"the panel lane is not live (its mode reads \"{found}\"): "
                f"{why or 'elane.panel.mode is set so'}")[:300]
        if not _lane_on(settings) or cfg(settings)["mode"] != "live":
            return SEAT_DEMOTED, said       # the captain's switch
        return SEAT_HELD, said              # a store-side leg: opens stop, exits go on, nobody is retired
    except Exception as exc:  # noqa: BLE001 - no evidence either way
        return SEAT_UNKNOWN, f"the panel lane could not be read ({type(exc).__name__}: {str(exc)[:120]})"


def seat_standing(root: str | Path) -> tuple[bool | None, str]:
    """`seat_word` as three states: (True, "") while the lane is live; (False, why) on POSITIVE EVIDENCE that the
    captain's switch is down; (None, why) when the seat is neither given nor taken away: a store-side leg failed
    (held: the leg named) or the lane cannot be read. Never raises."""
    code, why = seat_word(root)
    return (True if code == SEAT_LIVE else False if code == SEAT_DEMOTED else None), why


def is_panel(fam: Mapping[str, Any] | None) -> bool:
    """Whether a family row is a panel family (structure `STRUCTURE`)."""
    return isinstance(fam, Mapping) and str(fam.get("structure") or "") == STRUCTURE


def _cached_mode(root: str | Path) -> str:
    """`mode` of a state root's own settings, reused for `MODE_TTL` seconds a process."""
    key = (str(Path(root)), "mode")
    now = time.monotonic()
    with _cache_lock:
        held = _mode_cache.get(key)
    if held is not None and 0.0 <= now - held[0] < MODE_TTL:
        return held[1]
    value = mode(_settings_of(root, None), root)
    with _cache_lock:
        _mode_cache[key] = (now, value)
    return value


def seatable(root: str | Path) -> Callable[[Any], bool]:
    """The seat rule `bands.equity_seating` is handed: E1's for "etf" and "stock"; "panel" iff the effective mode is
    "live". (A style-open passer never reaches this rule: `look` gives it no band, A22.) The mode is read only when a
    panel family is asked about, so with no panel Candidate nothing of E4 is read."""
    def rule(structure: Any) -> bool:
        word = str(structure or "")
        if word == STRUCTURE:
            return _cached_mode(root) == "live"
        from .store import EQUITY_STRUCTURES

        return word in EQUITY_STRUCTURES

    return rule


# ----------------------------------------------------------------------------------------------- families and records
def panel_families(store: Any, *, alive: bool | None = None) -> list[dict[str, Any]]:
    """The panel families of the store (lane "equity", structure "panel"), alive or retired unless `alive` says."""
    from . import elane_seal

    return [fam for fam in elane_seal.equity_families(store, alive=alive) if is_panel(fam)]


def record_of(fam: Mapping[str, Any] | None) -> dict[str, Any]:
    """A panel family's Train record (its state's `STATE_KEY`), a dict ({} for none)."""
    value = _state(fam).get(STATE_KEY)
    return dict(value) if isinstance(value, Mapping) else {}


def versions_of(rec: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    versions = rec.get("versions") if isinstance(rec.get("versions"), Mapping) else {}
    return {str(k): dict(v) for k, v in versions.items() if isinstance(v, Mapping) and str(k).isdigit()}


def passed_version(fam: Mapping[str, Any] | None) -> int | None:
    n = record_of(fam).get("passed_version")
    return int(n) if isinstance(n, int) and not isinstance(n, bool) else None


def judged(rec: Mapping[str, Any]) -> int:
    """How many of a record's versions the bar judged on the mechanism (a fail among `JUDGED_XS`)."""
    return sum(1 for v in versions_of(rec).values() if any(f in JUDGED_XS for f in (v.get("fails") or [])))


def _update(store: Any, fid: str, change: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
    """Read-modify-write the family's Train record under the store's lock."""
    with store.atomic():
        rec = record_of(store.family(fid) or {})
        rec.setdefault("status", "researching")
        rec.setdefault("versions", {})
        change(rec)
        rec["last_at"] = store.now()
        store.set_state(fid, **{STATE_KEY: rec})
    return rec


def identity() -> dict[str, str] | None:
    """The xs identity verdicts are judged under now (`league.xs.identity.xs_identity`), or None when it cannot be
    read (then no pass reads as stale by it, and no look is taken: a band proof needs it)."""
    try:
        from ..xs.identity import xs_identity

        value = xs_identity()
    except Exception:  # noqa: BLE001 - no identity: nothing is judged stale by it
        return None
    return dict(value) if isinstance(value, Mapping) else None


def hidden_year_of(fam: Mapping[str, Any] | None) -> int | None:
    """The hidden year a panel family was born with (its spec's `hidden_year`, one of the panel's Train years)."""
    from ..xs import config as xconfig

    year = _spec(fam).get("hidden_year")
    return int(year) if isinstance(year, int) and not isinstance(year, bool) and year in xconfig.TRAIN_YEARS else None


# ------------------------------------------------------------------------------------------- cards, cells and births
#: What a panel program may condition on, in the card vocabulary's words (league/swarm/cards.py `INPUTS`): returns and
#: ranges, realized volatility, relative volume, the calendar counts, other slots and the market. NO event flag (the
#: registered contract's calendar is four counts), no implied vol, chain or open interest.
INPUTS = ("underlying_price", "realized_vol", "share_volume", "clock", "cross_asset")


def _token(value: Any) -> str:
    return "_".join(str(value or "").strip().lower().replace("-", " ").split())


def cell_of(lane: Any, agenda: Any, panel: Any) -> tuple[str, str, str]:
    """A panel family's agenda cell: (lane, agenda, "panel:" + panel) (E2's 3-tuple shape; never built by E2's
    `cell_of(lane, agenda, symbols)`)."""
    return (str(lane), str(agenda) if agenda in PANEL_AGENDA else OTHER, f"panel:{panel}")


def family_cell(fam: Mapping[str, Any] | None) -> tuple[str, str, str]:
    """The agenda cell of a panel family (its spec's lane, agenda and panel)."""
    spec = _spec(fam)
    return cell_of(spec.get("lane") or LANE, spec.get("agenda"), spec.get("panel") or PANELS[0])


def cell_text(cell: Sequence[str]) -> str:
    return f"{cell[0]} / {cell[1]} / {cell[2]}"


def card_errors(card: Any, settings: Mapping[str, Any] | None, *, store: Any = None) -> list[str]:
    """Why a panel card is refused ([]: it is not): lane "equity"; `panel` in `panels`; `max_names` between 5 and the
    lane's cap; an allowed `rebalance`; a `weekday` only on a weekly card; an agenda key of `PANEL_AGENDA`; no
    `symbols`; the mode at least "train" ("the panel lane is closed"); the cell not closed (asked only with a
    `store`: the admission's)."""
    from ..xs import config as xconfig

    card = card if isinstance(card, Mapping) else {}
    c = cfg(settings)
    root = getattr(store, "root", None)
    errors: list[str] = []
    if MODES.index(mode(settings, root)) < MODES.index("train"):
        errors.append("lane: the panel lane is closed (elane.panel.mode); a card may not declare structure \"panel\"")
    if _token(card.get("lane")) != LANE:
        errors.append(f"lane: a panel card declares \"lane\": \"{LANE}\" ({card.get('lane')!r} given)")
    panel = card.get("panel")
    if panel not in c["panels"]:
        errors.append(f"panel: one of {', '.join(c['panels'])} ({panel!r} given)")
    names = card.get("max_names")
    if isinstance(names, bool) or not isinstance(names, int) or not xconfig.MIN_NAMES <= names <= c["max_names"]:
        errors.append(f"max_names: a whole number from {xconfig.MIN_NAMES} to {c['max_names']} (elane.panel.max_names; "
                      f"{names!r} given)")
    rebalance = card.get("rebalance")
    if rebalance not in c["rebalance"]:
        errors.append(f"rebalance: one of {', '.join(c['rebalance'])} ({rebalance!r} given)")
    weekday = card.get("weekday")
    if rebalance == "weekly":
        if weekday is not None and (isinstance(weekday, bool) or not isinstance(weekday, int) or not 0 <= weekday <= 4):
            errors.append(f"weekday: 0 (Monday) to 4 (Friday) on a weekly card ({weekday!r} given)")
    elif rebalance == "monthly" and weekday is not None:
        errors.append("weekday: only a weekly card declares one")
    agenda = card.get("agenda")
    if agenda is not None and agenda not in PANEL_AGENDA:
        errors.append(f"agenda: {agenda!r} is not one of {', '.join(PANEL_AGENDA)}")
    symbols = card.get("symbols")
    if symbols not in (None, [], ()):
        errors.append("symbols: a panel card names no symbol (a panel program sees salted slots, never a ticker)")
    inputs = card.get("inputs")
    if isinstance(inputs, str):
        inputs = [x for x in inputs.replace(";", ",").replace("/", ",").replace("+", ",").replace("|", ",").split(",")
                  if x.strip()]
    unknown = [n for n in (_token(x) for x in inputs or []) if n not in INPUTS] if isinstance(inputs, list) else []
    if unknown:
        errors.append(f"inputs: a panel program reads returns, ranges, relative volume, the calendar counts, the other "
                      f"slots and the market only: one to five of {', '.join(INPUTS)} ({', '.join(unknown)} given)")
    ablation = card.get("ablation")
    if ablation == "flat" or (isinstance(ablation, Mapping) and ablation.get("flat") is True):
        errors.append("ablation: a panel card's comparison is its matched placebo portfolios, never flat")
    if store is not None and agenda in PANEL_AGENDA and panel in c["panels"]:
        cell = cell_of(LANE, agenda, panel)
        if cell in closed_cells(store, settings):
            errors.append(f"agenda: its cell {cell_text(cell)} is CLOSED: refuted on Train too often with no pass")
    return errors


def zero_edge_rate(store: Any) -> dict[str, Any]:
    """THE ZERO-EDGE EXPECTED column's rate: over every week the `xs_zero_edge` job kept (kv `ZERO_KEY`), the
    random-score programs run through the whole bar and how many passed: {programs, passes, rate (None before any)}."""
    programs = passes = 0
    try:
        weeks = store.get(ZERO_KEY)
    except Exception:  # noqa: BLE001 - a kv that cannot be read is no measurement
        weeks = None
    for row in (weeks.values() if isinstance(weeks, Mapping) else ()):
        if not isinstance(row, Mapping):
            continue
        n, p = row.get("programs"), row.get("passes")
        if isinstance(n, int) and isinstance(p, int) and not isinstance(n, bool) and not isinstance(p, bool) \
                and 0 <= p <= n:
            programs, passes = programs + n, passes + p
    return {"programs": programs, "passes": passes, "rate": (passes / programs) if programs else None}


def train_map(store: Any) -> list[dict[str, Any]]:
    """The panel Train map's rows, one a cell, with the ZERO-EDGE EXPECTED column (`ZERO_KEY`): {cell, births, scored,
    passed, refuted, stalled, best_t, sensitive (passes flagged survivorship-sensitive), zero_rate, zero_expected
    (births x the zero-edge pass rate; None before the job's first week)}. Train facts only: a family's fate after
    Train never moves its row."""
    cells: dict[tuple[str, str, str], dict[str, Any]] = {}
    for fam in panel_families(store):
        rec = record_of(fam)
        cell = family_cell(fam)
        row = cells.setdefault(cell, {"cell": cell, "births": 0, "scored": 0, "passed": 0, "refuted": 0, "stalled": 0,
                                      "best_t": None, "sensitive": 0})
        row["births"] += 1
        versions = versions_of(rec)
        row["scored"] += int(bool(versions))
        n = rec.get("passed_version")
        if isinstance(n, int) and not isinstance(n, bool):
            row["passed"] += 1
            verdict = versions.get(str(n)) or {}
            t = _num(verdict.get("score"))
            if t is not None and (row["best_t"] is None or t > row["best_t"]):
                row["best_t"] = t
            row["sensitive"] += int(FLAG_SURVIVORSHIP in (verdict.get("flags") or []))
        refuted = rec.get("status") == "refuted"
        row["refuted"] += int(refuted and judged(rec) > 0)
        row["stalled"] += int(rec.get("status") == "stalled" or (refuted and judged(rec) == 0))
    zero = zero_edge_rate(store)
    for row in cells.values():
        row["zero_rate"] = zero["rate"]
        row["zero_expected"] = round(row["births"] * zero["rate"], 2) if zero["rate"] is not None else None
    return sorted(cells.values(), key=lambda r: (-r["passed"], -r["births"], r["cell"]))


def closed_cells(store: Any, settings: Mapping[str, Any] | None) -> list[tuple[str, str, str]]:
    """The panel cells with E2's `refuted_cell_cap` families refuted on a `JUDGED_XS` rule and no pass: no birth
    there."""
    from . import elane_train

    cap = elane_train.cfg(settings)["refuted_cell_cap"]
    return [r["cell"] for r in train_map(store) if r["refuted"] >= cap and not r["passed"]]


def map_notes(root: str | Path | None, settings: Mapping[str, Any] | None = None) -> list[str]:
    """What the panel store says of the bar's data, for the Train map's label (rules and counts of the House's own
    data job, never a price): the Train years dropped for coverage, a thin history year (under the lane's own
    `coverage_min`: `cfg(settings)`, the floor the data job judged the store at), and the Train-era index exits whose
    kind the changes table could not say (they take the vanish haircut)."""
    from ..xs import config as xconfig

    manifest = _manifest(root)
    if manifest is None:
        return []
    notes = []
    ok = manifest.get("train_years_ok")
    if isinstance(ok, list):
        dropped = [str(y) for y in xconfig.TRAIN_YEARS if y not in ok]
        if dropped:
            notes.append(f"dropped from the bar for thin coverage: {', '.join(dropped)}")
    coverage = manifest.get("coverage") if isinstance(manifest.get("coverage"), Mapping) else {}
    thin = [str(y) for y in xconfig.HISTORY_YEARS
            if (_num((coverage.get(str(y)) or {}).get("share")) or 1.0) < cfg(settings)["coverage_min"]]
    if thin:
        notes.append(f"thin look-back in the first months after {', '.join(thin)}")
    listed = _read_json(Path(root) / STORE_DIR / UNIVERSE_MANIFEST) if root is not None else None
    exits = listed.get("exits") if isinstance(listed, Mapping) and isinstance(listed.get("exits"), Mapping) else {}
    unknown = exits.get("unknown")
    if isinstance(unknown, int) and not isinstance(unknown, bool) and unknown > 0:
        notes.append(f"{unknown} index exits of unknown kind take the vanish haircut")
    return notes


def train_map_text(store: Any, settings: Mapping[str, Any] | None, *, limit: int = 40) -> str:
    """THE PANEL TRAIN MAP for the architect's request ("" with no panel family yet). Train facts only, with the
    ZERO-EDGE EXPECTED column beside each cell's passes."""
    rows = train_map(store)
    if not rows:
        return ""
    closed = set(closed_cells(store, settings))
    zero = zero_edge_rate(store)
    notes = map_notes(getattr(store, "root", None), settings)
    said = (f"the bar passed {zero['passes']} of {zero['programs']} random-score programs with no edge"
            if zero["programs"] else "the zero-edge rate is not measured yet")
    lines = [f"PANEL TRAIN MAP (lane / mechanism / panel; {MAP_LABEL}" + ("; " + "; ".join(notes) if notes else "")
             + f"). Each cell: births, families Train-scored, passed {OBJECTIVE} and the review (the best passing pooled "
             "t of the residual at 1.0x), ZERO-EDGE EXPECTED (the passes that many births would give with no edge: "
             f"{said}), refuted on Train by the bar, stalled (no program of the family could be judged):"]
    for r in rows[:limit]:
        best = f" (best t {r['best_t']:.1f})" if r["best_t"] is not None else ""
        expected = f"{r['zero_expected']:.2f}" if r["zero_expected"] is not None else "unmeasured"
        sens = f", {r['sensitive']} {FLAG_SURVIVORSHIP}" if r["sensitive"] else ""
        shut = "; CLOSED: no birth here" if r["cell"] in closed else ""
        lines.append(f"- {cell_text(r['cell'])}: births {r['births']}, scored {r['scored']}, passed {r['passed']}{best}"
                     f"{sens}, zero-edge expected {expected}, refuted {r['refuted']}, stalled {r['stalled']}{shut}")
    if len(rows) > limit:
        lines.append(f"- ... and {len(rows) - limit} more cells")
    return "\n".join(lines)


def request_map_text(store: Any, settings: Mapping[str, Any] | None, *, limit: int = 40) -> str:
    """The panel Train map as the architect's equity request carries it, after E2's own map
    (`elane_train.train_map_text`): "" while the panel lane bears nothing (a closed lane shows no map of itself
    beside a request that says nothing of the panel), else `train_map_text`."""
    if MODES.index(mode(settings, getattr(store, "root", None))) < MODES.index("train"):
        return ""
    return train_map_text(store, settings, limit=limit)


def cell_looks(store: Any, cell: Sequence[str]) -> int:
    """THE HOUSE'S COUNT (duty 3): the XS1 looks already taken by panel families of `cell`, in flight included."""
    cell = tuple(str(part) for part in cell)
    count = 0
    for fam in panel_families(store):
        if family_cell(fam) != cell:
            continue
        state = _state(fam)
        marker = state.get("look_inflight")
        count += int(isinstance(state.get(LOOK_KEY), Mapping)
                     or bool(isinstance(marker, Mapping) and marker.get("sha")))
    return count


def forward_verdicts(store: Any, cell: Sequence[str]) -> int:
    """The forward verdicts (route F-GS-XS) recorded in `cell`. No such verdict can exist in this release (the forward
    route is specified, not measured or built), so the count is 0 and A22 (2)'s cap is flat."""
    return 0


def look_room(store: Any, cell: Sequence[str]) -> str | None:
    """A22 (2): why `cell` has no XS1 look left, or None: `cell_looks(store, cell)` has reached `MAX_CELL_LOOKS` and
    no forward verdict exists in the cell (none can in this release: the cap is flat). The look it holds back is not
    spent."""
    taken = cell_looks(store, cell)
    if taken < MAX_CELL_LOOKS or forward_verdicts(store, cell) > 0:
        return None
    return (f"its agenda cell {cell_text(tuple(str(p) for p in cell))} has taken {taken} XS1 looks: at most "
            f"{MAX_CELL_LOOKS} a cell until a forward verdict exists there (the captain's A22)")


def probe_reading(root: str | Path, route: str) -> dict[str, Any] | None:
    """The contamination probe's published reading for a model route (`<root>/PROBE_FILE`: aggregates only), cut to the
    panel strata: {route, at, model, strata {stratum: {era: {readable, recalled}}}}; None when the file, the route or
    its published result is missing."""
    doc = _read_json(Path(root) / PROBE_FILE)
    routes = doc.get("routes") if isinstance(doc, Mapping) and isinstance(doc.get("routes"), Mapping) else {}
    row = routes.get(str(route))
    if not isinstance(row, Mapping) or not row.get("at") or not isinstance(row.get("cells"), Mapping):
        return None
    strata = {}
    for stratum in PROBE_STRATA:
        eras = row["cells"].get(stratum)
        if isinstance(eras, Mapping) and eras:
            strata[stratum] = {str(era): {"readable": bool((cell or {}).get("readable")),
                                          "recalled": bool((cell or {}).get("recalled"))}
                               for era, cell in eras.items() if isinstance(cell, Mapping)}
    return {"route": str(route), "at": str(row.get("at")), "model": row.get("model"), "strata": strata}


def probed(root: str | Path, fam: Mapping[str, Any]) -> str | None:
    """A22 (3): why the look must wait on the contamination probe, or None: `<root>/PROBE_FILE` (E3's
    `league.ops.contam_probe.FILE`, read by name: aggregates only) holds a published result (`at`) for the route that
    wrote the family's program (its spec's `e2_route`) whose cells carry every stratum of `PROBE_STRATA`. No file, no
    such route, no panel stratum, an unreadable file: the reason, and the look waits (nothing spent)."""
    route = str(_spec(fam).get("e2_route") or "")
    if not route:
        return "the family names no birth route: the contamination probe cannot be read for it"
    try:
        reading = probe_reading(root, route)
    except Exception as exc:  # noqa: BLE001 - a probe that cannot be read holds the look
        return f"the contamination probe's file cannot be read ({type(exc).__name__})"
    if reading is None:
        return (f"the contamination probe has no published result for {route} ({PROBE_FILE}: release E3's probe has "
                "not run for the route that wrote this program)")
    missing = [s for s in PROBE_STRATA if not reading["strata"].get(s)]
    if missing:
        return (f"the contamination probe's result for {route} carries no panel stratum {', '.join(missing)} (the "
                "probe's panel strata are not merged or have not run)")
    return None


def style_of(fam: Mapping[str, Any], version: int | None = None) -> dict[str, Any] | None:
    """A22 (1): the style verdict the Train record keeps for a version (default: the banded or latest judged one),
    or None when it has none (read as style-open: `league.xs.style.seat_refusal(None)`)."""
    rec = record_of(fam)
    versions = versions_of(rec)
    if version is None:
        for n in (_state(fam).get("banded_version"), rec.get("passed_version")):
            if isinstance(n, int) and not isinstance(n, bool) and str(n) in versions:
                version = n
                break
        else:
            scored = sorted(int(k) for k in versions)
            version = scored[-1] if scored else None
    verdict = (versions.get(str(version)) or {}).get(STYLE_FIELD) if version is not None else None
    return dict(verdict) if isinstance(verdict, Mapping) else None


def assign(store: Any, cell: Sequence[str], settings: Mapping[str, Any] | None = None) -> int | None:
    """THE HIDDEN YEAR of a new panel family: `league.xs.config.TRAIN_YEARS[(k_c + elane_folds.cell_hash(cell)) % 6]`,
    k_c = the panel families already born in that cell with a hidden year; None while E3 is not merged or its folds
    are not recording (the bar then reads all six Train years, stated on the map). Never E3's own `assign` (it rotates
    over seven years) and never `elane_folds.birth_fields` (it takes no cell). `settings`: the swarm's (default: the
    store root's)."""
    from ..xs import config as xconfig

    try:
        from . import elane_folds
    except ImportError:
        return None
    try:
        if elane_folds.mode(_settings_of(getattr(store, "root", None), settings)) != "record":
            return None
        cell = tuple(str(part) for part in cell)
        born = sum(1 for fam in panel_families(store) if family_cell(fam) == cell and hidden_year_of(fam) is not None)
        return int(xconfig.TRAIN_YEARS[(born + int(elane_folds.cell_hash(cell))) % len(xconfig.TRAIN_YEARS)])
    except Exception:  # noqa: BLE001 - a fold that cannot be drawn hides nothing (six Train years, no out-of-fold row)
        return None


def _gid() -> str:
    """E3's first genome id (`elane_folds.GID0`), "g0" while E3 is not merged."""
    try:
        from . import elane_folds

        return str(elane_folds.GID0)
    except Exception:  # noqa: BLE001
        return "g0"


def run_spans(hidden: int | None, years_ok: Iterable[int] | None = None) -> tuple[tuple[dt.date, dt.date], ...]:
    """The Train bar's run spans: each stretch of consecutive Train years of one segment of
    `league.xs.config.TRAIN_SEGMENTS` that is neither the hidden year nor outside `years_ok` (None: every Train year),
    from its first year's start (the segment's, for the segment's first year) through its last year's end. No session
    of the hidden year, of a dropped year, or of 2016, 2020 or 2021 is inside one."""
    from ..xs import config as xconfig

    ok = set(xconfig.TRAIN_YEARS if years_ok is None else years_ok) & set(xconfig.TRAIN_YEARS)
    ok.discard(hidden)
    spans: list[tuple[dt.date, dt.date]] = []
    for first, last in xconfig.TRAIN_SEGMENTS:
        stretch: list[int] = []
        for year in [*range(first.year, last.year + 1), None]:
            if year is not None and year in ok:
                stretch.append(year)
                continue
            if stretch:
                spans.append((max(first, dt.date(stretch[0], 1, 1)), min(last, dt.date(stretch[-1], 12, 31))))
                stretch = []
    return tuple(spans)


def seen_spans(hidden: int | None) -> tuple[tuple[dt.date, dt.date], ...]:
    """The Train bar's run spans: `league.xs.config.TRAIN_SEGMENTS` with the hidden year cut out (a segment without it
    as it is; the one with it cut into the stretch before and the stretch after: two or three spans; both whole
    segments for None)."""
    return run_spans(hidden, None)


def hidden_span(hidden: int) -> tuple[dt.date, dt.date]:
    """The hidden year's own sessions (the out-of-fold run's span). ValueError for a year that is no Train year."""
    from ..xs import config as xconfig

    for first, last in xconfig.TRAIN_SEGMENTS:
        if first.year <= int(hidden) <= last.year:
            return max(first, dt.date(int(hidden), 1, 1)), min(last, dt.date(int(hidden), 12, 31))
    raise ValueError(f"{hidden!r} is no panel Train year")


def agenda_text(settings: Mapping[str, Any] | None = None) -> str:
    """The panel agenda as the architect's request shows it (`PANEL_AGENDA`; the captain's census notes under the
    label "in-sample 2010-24, best of 7; not evidence")."""
    notes = cfg(settings)["census_notes"]
    lines = ["THE PANEL AGENDA (a panel proposal's \"agenda\" names one key; each a published prior, a hypothesis for "
             "Train, never evidence):"]
    for key, row in PANEL_AGENDA.items():
        note = f" [census_informed; {CENSUS_LABEL}: {notes[key]}]" if notes.get(key) else ""
        lines.append(f"- {key}: {row['what']}. Priors: {row['prior']}.{note}")
    lines.append("- earnings_drift is REFUSED until earnings dates exist on the House.")
    return "\n".join(lines)


#: The panel program's contract in brief, when league/xs/XS.md (package C's file, the contract shown to authors)
#: cannot be read: the pinned pre-registration's C-XS-1 in the House's narrower limits. Rules only.
CONTRACT_FALLBACK = (
    "A PANEL PROGRAM is one Python file: NEEDS = {\"panel\": \"sp500\", \"history\": 20..252, \"max_names\": 5..12, "
    "\"rebalance\": \"weekly\" | \"monthly\", \"weekday\": 0..4 (weekly only), \"max_hold_sessions\": 5..60}, PARAMS = "
    "{...}, and decide(ctx). decide(ctx) is called only at the close before a rebalance session and returns "
    "{\"target\": {slot id: weight}, \"at\": \"open\" | \"close\"}, {\"hold\": True} or None. A target holds no name "
    "(all cash) or 5 to max_names names, each weight above 0 and at most 0.20, their sum at most 1. THE KEEP RULE: a "
    "held slot absent from the target is sold whole at the next fill point; a slot not held is bought as ONE lot of "
    "its weight; a held slot in the target is kept as it is (no resize); a target that needs more than 12 buys or 12 "
    "sells is refused whole. WHAT ctx HOLDS at the decision close, one row a slot (the eligible index members, in "
    "ascending slot id): ctx.n, ctx.ids (salted, stable inside one run, unrelated across runs), ctx.ret, ctx.oret, "
    "ctx.iret, ctx.range, ctx.rel_volume (arrays n x (history + 1), scale-free, six decimals, the last column the "
    "decision session), ctx.sector (a statistical sector code, relabelled every run), ctx.beta (two decimals), "
    "ctx.mkt (the same five fields of the market), ctx.positions ({id, slot, weight, ret, held_sessions, at, tag}), "
    "ctx.closed, ctx.rejects, ctx.cash, ctx.equity, ctx.budget, ctx.weekday, ctx.session_of_month, "
    "ctx.sessions_left_in_month, ctx.last_session_of_week, ctx.max_names, ctx.params. NO ticker, NO date, NO year, NO "
    "event flag, NO price level, NO share count, NO dollar volume or market value and no rank of one. The House sells "
    "a lot whose name left the eligible set, and every lot at its max_hold_sessions, at the next open. math and numpy "
    "only.")


def contract_text() -> str:
    """XS.md in brief (what a panel program is and sees), for the architect's request and the researcher's brief."""
    try:
        return (Path(__file__).resolve().parents[1] / "xs" / "XS.md").read_text(encoding="utf-8")[:12000]
    except OSError:
        return CONTRACT_FALLBACK


def bar_text() -> str:
    """The Train bar in words (`BAR_XS`, `FAILS_XS`), with what it loosens stated (five seen years, not six)."""
    first, gap = BAR_XS["state_resets"]
    return (f"THE PANEL TRAIN BAR ({OBJECTIVE}), on the House's panel Train years 2017-19 and 2022-24 (2016 and 2021 are "
            "look-back only; one Train year may be held out from you and is never named or shown). A version is run "
            "once on each stretch of the years you see, each run starting flat, at 1.0x and at 1.5x the half-spread, "
            "and the runs are read together. It is judged on its daily RESIDUAL x: its P&L after costs minus the "
            "cost-free P&L of the cells its names were picked from (the same sector, beta group and 12-1 momentum "
            "group on the decision day), one number a session, never on raw P&L. It PASSES when all hold: (XA0) at "
            f"least {BAR_XS['min_rebalances']} rebalances with a non-empty target and a lot held on at least "
            f"{BAR_XS['min_invested']:.0%} of the sessions; (XT1) the residual's t at 1.5x at least "
            f"{BAR_XS['t_min']:g}; (XY1) the residual's sum at 1.5x above zero in at least two thirds of the years you "
            "see (four of five) and in at least one year of each stretch of the calendar; (XH1) the same sum above "
            "zero in each of two halves of the names, run apart (a rule must find names in a universe it never "
            f"searched); (XP1) its t at 1.5x at or above {BAR_XS['placebo_rank']:.0%} of matched random portfolios that "
            "hold the same number of names at the same weights from the same cells on the same days; (XR1) the "
            f"residual's sum above zero at 1.0x and at least {BAR_XS['cost_ratio']:g} of it at 1.5x; (STATE) asked "
            f"again after a fresh load (after {first} calls, then {gap} more, and so on), its targets match the "
            f"uninterrupted run's on at least {BAR_XS['state_match']:.0%} of its calls: the House's decider restarts on "
            "every deploy and a restart empties STATE, so read holdings from ctx.positions and keep in STATE only what "
            "ctx gives again. THE LOOSENING, stated: this bar reads six Train years, five of them seen (the ETF bar "
            "reads seven and six). Beside, never a bar: the raw P&L's t, turnover, the cost share, and whether the "
            "names you held lean on size, beta, momentum or volatility (a program that leans on a style can pass the "
            "screen and still take no live seat). The first version that passes the bar and the review is the "
            "lineage's ONE Validation try, then ONE sealed look under the screen XS1; their outcomes are sealed and "
            "never shown to anyone who writes programs.")


def researching(store: Any) -> int:
    """Panel families in Train research (the record's status: neither passed nor refuted nor closed). Outcome-free."""
    return sum(1 for fam in panel_families(store) if record_of(fam).get("status", "researching") == "researching")


def quota(store: Any, settings: Mapping[str, Any] | None, births: int) -> int:
    """How many of a pass's `births` equity births are the panel's: `birth_share` of them, never past `max_alive` panel
    families in Train research; 0 under mode "train". THE SHARE IS HELD OVER THE WINDOW (E2's `window_hours` of
    births), not pass by pass: the panel is asked for the births that bring it to `birth_share` of the equity lanes'
    births in the window with this pass's among them, so a pass of one birth alternates and never gives the panel
    every birth or none."""
    try:
        births = max(0, int(births))
        root = getattr(store, "root", None)
        if not births or MODES.index(mode(settings, root)) < MODES.index("train"):
            return 0
        c = cfg(settings)
        room = max(0, int(c["max_alive"]) - researching(store))
        if not room or c["birth_share"] <= 0:
            return 0
        from . import elane_births
        from .store import EQUITY_LANES, iso, loads

        hours = elane_births.cfg(settings)["window_hours"]
        since = iso(float(store.clock()) - float(hours) * 3600.0)
        equity = panel = 0
        for row in store._all("SELECT payload FROM events WHERE kind='swarm.born' AND at>=?", (since,)):
            payload = loads(row.get("payload"), {}) or {}
            if isinstance(payload, Mapping) and payload.get("lane") in EQUITY_LANES:
                equity += 1
                panel += int(payload.get("structure") == STRUCTURE)
        target = math.ceil(c["birth_share"] * (equity + births) - 1e-9) - panel
        return max(0, min(births, room, target))
    except Exception:  # noqa: BLE001 - a quota that cannot be read bears nothing
        return 0


#: The architect's PANEL block (`request_text`): what a panel family is and how to propose one. Rules only.
PANEL_PROPOSAL = (
    "A PANEL proposal is an equity-lane family whose structure is \"panel\": {\"slug\", \"lane\": \"equity\", "
    "\"structure\": \"panel\", \"panel\": \"sp500\", \"agenda\": \"<one key of THE PANEL AGENDA>\", \"max_names\": "
    "5..MAX_NAMES, \"rebalance\": \"weekly\" or \"monthly\", \"weekday\": 0..4 (weekly only), \"mechanism\", "
    "\"rejection\", \"sketch\", \"card\": {\"lane\": \"equity\", \"structure\": \"panel\", \"panel\": \"sp500\", "
    "\"max_names\": ..., \"rebalance\": ..., the card's other fields; NO \"symbols\"}, \"program\": \"<the whole "
    "Python file under THE PANEL CONTRACT>\"}.")


def request_text(store: Any, settings: Mapping[str, Any] | None, births: int) -> str:
    """The PANEL block of the architect's equity request ("" while the panel lane bears nothing): what a panel
    program is, XS.md in brief, the panel agenda, the panel quota and the closed panel cells. Train facts and rules
    only. The panel Train map, with its ZERO-EDGE EXPECTED column, is not in this block: it follows E2's own map in
    the request (`elane_train.train_map_text`, by `request_map_text`), so the request shows it once."""
    root = getattr(store, "root", None)
    if MODES.index(mode(settings, root)) < MODES.index("train"):
        return ""
    c = cfg(settings)
    want = quota(store, settings, births)
    closed = closed_cells(store, settings)
    parts = [
        "THE PANEL (structure \"panel\", lane equity): programs that pick 5 to "
        f"{c['max_names']} names out of the day's S&P 500 members by a symmetric cross-sectional rule. A panel program "
        "sees salted slots: no ticker, no date, no price level, no size. It is judged on its daily RESIDUAL against "
        "matched placebo portfolios (the same number of names at the same weights from the same sector, beta and "
        "momentum cells on the same days), by the bar below on Train and then by the screen XS1; market, sector, beta "
        "and momentum direction are not counted as edge, so a rule that only tilts to a style earns nothing here.",
        PANEL_PROPOSAL.replace("MAX_NAMES", str(c["max_names"])),
        f"PANEL QUOTA: of this pass's births, {want} may be panel families (elane.panel.birth_share "
        f"{c['birth_share']:.0%} of the equity lanes' births over the window; panel families in Train research: "
        f"{researching(store)} of at most {c['max_alive']}). Rebalance schedules offered: {', '.join(c['rebalance'])}.",
        agenda_text(settings),
        bar_text(),
        ("CLOSED PANEL CELLS (no birth: refuted on Train too often with no pass): "
         + "; ".join(cell_text(cell) for cell in closed) + ".") if closed else "",
        "THE PANEL CONTRACT (league/xs/XS.md):\n" + contract_text(),
    ]
    return "\n\n".join(p for p in parts if p)


def check_code(code: Any, fam: Mapping[str, Any], settings: Mapping[str, Any] | None = None) -> str | None:
    """Why a program cannot be a version of the panel family `fam`, or None: the Gym's static rules
    (`league.gym.safety.check_program`, never executed here); NEEDS a literal dict naming the family's panel, its
    rebalance schedule (and weekday) and at most its `max_names`; and, once package C's parser is built,
    `league.xs.program.parse_needs` on it."""
    from ..gym.safety import CodeRefused, check_program
    from ..xs import config as xconfig
    from . import elane_train

    text = str(code or "")
    try:
        check_program(text)
    except CodeRefused as exc:
        return f"refused by the code rules: {str(exc)[:300]}"
    except Exception as exc:  # noqa: BLE001 - an unreadable program is refused
        return f"refused: {type(exc).__name__}"
    needs = elane_train.needs_literal(text)
    if needs is None:
        return ("NEEDS must be a literal dict at the top level ({\"panel\": \"sp500\", \"history\": n, \"max_names\": n, "
                "\"rebalance\": \"weekly\" | \"monthly\", \"weekday\": n, \"max_hold_sessions\": n})")
    spec = _spec(fam)
    if "symbols" in needs:
        return "NEEDS names symbols: a panel program names its panel, never a symbol"
    if needs.get("panel") != (spec.get("panel") or PANELS[0]):
        return f"NEEDS[\"panel\"] must be the family's panel ({spec.get('panel') or PANELS[0]!r})"
    if needs.get("rebalance") != spec.get("rebalance"):
        return f"NEEDS[\"rebalance\"] must be the family's schedule ({spec.get('rebalance')!r})"
    if spec.get("rebalance") == "weekly" and int(needs.get("weekday") or 0) != int(spec.get("weekday") or 0):
        return f"NEEDS[\"weekday\"] must be the family's ({int(spec.get('weekday') or 0)})"
    cap = spec.get("max_names") if isinstance(spec.get("max_names"), int) else cfg(settings)["max_names"]
    names = needs.get("max_names", 10)
    if isinstance(names, bool) or not isinstance(names, int) or not xconfig.MIN_NAMES <= names <= cap:
        return f"NEEDS[\"max_names\"] must be a whole number from {xconfig.MIN_NAMES} to the family's {cap}"
    try:
        from ..xs.program import parse_needs

        parse_needs(needs)
    except NotImplementedError:
        pass  # package C's parser is not built in this tree: the child's own load is then the judge ("LOAD")
    except Exception as exc:  # noqa: BLE001 - E1's NeedsRefused, in its own words
        return f"NEEDS refused: {str(exc)[:300]}"
    return None


def admit(equity_pass: Any, row: Mapping[str, Any], *, slug: str, lane: str, mechanism: str, quota: Any,
          route: Any, fams: Sequence[Mapping[str, Any]] = ()) -> str | None:
    """THE ADMISSION of a panel proposal (E2's `EquityPass.admit` forwards a row whose structure is "panel"): born
    when the panel lane bears (`mode` at least "train"), its card fits the panel's box (`card_errors`: the panel, the
    names, the schedule, the agenda, no symbols, the cell not closed), no panel family in Train research holds the
    same idea in its cell, the lineage it continues has taken no Validation try (outcome-free), its card is valid
    (`cards.validate`, which patch 5 teaches the panel's fields) and the quota admits it. The family id, or None with
    the refusal named (`equity_pass.refuse`)."""
    from . import cards, elane_births
    from .architect import same_idea

    store, settings = equity_pass.store, equity_pass.settings
    raw = dict(row.get("card")) if isinstance(row.get("card"), Mapping) else {}
    card = {**raw, "lane": lane, "structure": STRUCTURE}
    for key in ("panel", "max_names", "rebalance", "weekday"):
        if row.get(key) is not None and card.get(key) is None:
            card[key] = row[key]
        elif row.get(key) is not None and card.get(key) != row[key]:
            equity_pass.refuse(slug, f"{key}: the proposal and its card declare different values")
            return None
    card.setdefault("panel", PANELS[0])
    if card.get("rebalance") == "weekly":
        card.setdefault("weekday", 0)
    agenda = str(row.get("agenda") or "").strip().lower()
    if agenda not in PANEL_AGENDA:
        equity_pass.refuse(slug, f"agenda: {agenda or 'none'!r} is not one of {', '.join(PANEL_AGENDA)} (a panel "
                                 "proposal names a key of THE PANEL AGENDA)")
        return None
    problems = card_errors({**card, "agenda": agenda}, settings, store=store)
    if problems:
        equity_pass.refuse(slug, "card: " + "; ".join(problems)[:500])
        return None
    if len(mechanism) < elane_births.MIN_MECHANISM:
        equity_pass.refuse(slug, "mechanism: one or two sentences saying why it should make money")
        return None
    cell = cell_of(lane, agenda, card["panel"])
    same_cell = [f for f in fams if is_panel(f) and family_cell(f) == cell
                 and same_idea(str(f.get("mechanism") or ""), mechanism)]
    busy = [f for f in same_cell if record_of(f).get("status", "researching") == "researching"]
    if busy:
        equity_pass.refuse(slug, f"the same idea in the same panel cell is in Train research: {busy[-1]['id']}")
        return None
    parent = None
    declared = str(row.get("parent") or "").strip()
    if declared:
        mother = store.family(declared)
        if mother is not None and is_panel(mother):
            parent = mother
    if parent is None and same_cell:
        parent = same_cell[-1]
    if parent is not None and equity_pass.lineage_tried(parent):
        equity_pass.refuse(slug, f"it continues {parent['id']}'s lineage, which has its one Validation try (outcome "
                                 "sealed): propose a different idea")
        return None
    try:
        checked, problems = cards.validate(card, STRUCTURE, roots=[], settings=settings)
    except Exception as exc:  # noqa: BLE001 - a card that cannot be checked is not born
        checked, problems = None, [f"the card could not be checked: {type(exc).__name__}"]
    if checked is None:
        equity_pass.refuse(slug, "card: " + "; ".join(problems)[:500])
        return None
    split = _takes_structure(quota)
    admitted = quota.admits(lane, STRUCTURE) if split else quota.admits(lane)
    if not admitted:
        equity_pass.refuse(slug, (quota.why_not(lane, STRUCTURE) if split else quota.why_not(lane)) or "the quota")
        return None
    return birth(equity_pass, row, slug=slug, lane=lane, agenda=agenda, mechanism=mechanism, card=checked,
                 fields={k: card.get(k) for k in ("panel", "max_names", "rebalance", "weekday")}, parent=parent,
                 route=route)


def _takes_structure(quota: Any) -> bool:
    """Whether E2's quota is the patched one (its `why_not(lane, structure)` splits the pass's births by structure)."""
    return bool(getattr(quota, "by_structure", False))


def birth(equity_pass: Any, row: Mapping[str, Any], *, slug: str, lane: str, agenda: str, mechanism: str,
          card: Mapping[str, Any], fields: Mapping[str, Any], parent: Mapping[str, Any] | None,
          route: Any) -> str | None:
    """One panel birth: the family (its spec stamped with `hidden_year` by `assign` and `gid`), its card, its first
    version when its program passes the static checks, its Train record and the `swarm.born` event (which names no
    hidden year). None when the store refused it (named among the refusals)."""
    from . import cards

    store, settings = equity_pass.store, equity_pass.settings
    key = getattr(route, "key", str(route))
    panel = str(fields.get("panel") or PANELS[0])
    spec = {"id": slug, "mechanism": mechanism, "structure": STRUCTURE, "roots": [], "lane": lane, "agenda": agenda,
            "panel": panel, "max_names": int(fields["max_names"]), "rebalance": str(fields["rebalance"]),
            "weekday": int(fields.get("weekday") or 0) if fields.get("rebalance") == "weekly" else None,
            "rejection": " ".join(str(row.get("rejection") or "").split())[:400],
            "sketch": " ".join(str(row.get("sketch") or "").split())[:800], "lessons": [],
            "card_sha": cards.card_sha(card), "e2_route": key,
            "hidden_year": assign(store, cell_of(lane, agenda, panel), settings), "gid": _gid()}
    code = row.get("program") if isinstance(row.get("program"), str) else None
    why_code = check_code(code, {"spec": spec}, settings) if code else "the proposal carried no program"
    try:
        with store.atomic():
            fam = store.add_family(spec, origin="architect", parent=str(parent["id"]) if parent else None)
            fid = str(fam["id"])
            cards.put(store, fid, card, STRUCTURE)
            record: dict[str, Any] = {"status": "researching", "versions": {}, "agenda": agenda, "born_route": key,
                                      "last_at": ""}
            if why_code is None:
                store.add_version(fid, str(code), {}, author=f"architect:{key}", note="the architect's program at birth")
            elif code:
                record["refused"] = [{"at": store.now(), "why": f"the architect's program: {why_code}"}]
            store.set_state(fid, **{STATE_KEY: record})
    except Exception as exc:  # noqa: BLE001 - not born; the next request names why
        equity_pass.refuse(slug, f"not born: {type(exc).__name__}: {str(exc)[:200]}")
        return None
    if spec["sketch"]:
        store.note(fid, f"The architect's sketch: {spec['sketch']}")
    store.event("swarm.born", fid, {"parent": str(parent["id"]) if parent else None, "mechanism": mechanism,
                                    "structure": STRUCTURE, "roots": [], "origin": "architect", "lane": lane,
                                    "agenda": agenda, "panel": panel, "route": key,
                                    "card": {"sha": spec["card_sha"], "class": card.get("mechanism_class")},
                                    "program": "v1" if why_code is None else "none"})
    return fid


# -------------------------------------------------------------------------------------------------- runs and the bar
def runner(root: str | Path, settings: Mapping[str, Any] | None = None) -> Any:
    """The panel's `league.xs.runner.Isolated` over its OWN `league.live.decider.Decider(log=<root>/xs-decider.log)`,
    built once a process, nice 19, its hash seed pinned to E1's `elane.EVIDENCE_HASH_SEED`: never
    `elane.isolated_runner`'s child, never the live decider. `settings`: where the run budget is read at the build
    (`elane.panel.run_budget_seconds`; default: the root's)."""
    key = str(Path(root).resolve())
    with _runners_lock:
        held = _runners.get(key)
        if held is None:
            from ..live.decider import Decider
            from ..xs.runner import NICE, Isolated
            from . import elane

            decider = Decider(log=Path(root) / DECIDER_LOG)
            decider.hash_seed = elane.EVIDENCE_HASH_SEED  # the evidence child is deterministic across its restarts
            budget = float(cfg(_settings_of(root, settings))["run_budget_seconds"])
            held = Isolated(decider, Path(root) / STORE_DIR, budget_seconds=budget, nice=NICE)
            _runners[key], _deciders[key] = held, decider
        return held


def _runner_of(owner: Any) -> Any:
    """The owner's panel runner (`xs_runner`: tests hand one in), else the process's (`runner`)."""
    held = getattr(owner, "xs_runner", None)
    if held is not None:
        return held
    root = getattr(owner, "root", None)
    if root is None:
        root = owner.store.root
    return runner(root, getattr(owner, "settings", None))


def _decider_of(run_through: Any, root: str | Path | None = None) -> Any:
    """The decider a panel runner asks its child through (its `decider`, else the one `runner` built for the root)."""
    held = getattr(run_through, "decider", None)
    if held is None and root is not None:
        held = _deciders.get(str(Path(root).resolve()))
    return held


def _root_of(owner: Any) -> Any:
    root = getattr(owner, "root", None)
    return root if root is not None else getattr(getattr(owner, "store", None), "root", None)


def _utc_day(now: float) -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(float(now)))


def cpu_spent(store: Any, now: float) -> float:
    """The child seconds of panel Train booked on the UTC day of `now` (`CPU_KEY`)."""
    held = store.get(CPU_KEY)
    return float(_num((held or {}).get(_utc_day(now)) if isinstance(held, Mapping) else None) or 0.0)


def may_run(store: Any, settings: Mapping[str, Any] | None, now: float) -> str | None:
    """Why a panel run may not START now, or None: `league.xs.config.quiet(now, run_budget_seconds)` (asked before
    EACH run of a version), then the day's CPU (`cpu_seconds_day` less `CPU_KEY`). A quiet rule that is not built or
    cannot be read starts nothing (no panel run may be running at a wall on an unread clock)."""
    c = cfg(settings)
    try:
        from ..xs import config as xconfig

        why = xconfig.quiet(float(now), float(c["run_budget_seconds"]))
    except Exception as exc:  # noqa: BLE001 - fail closed: nothing starts on a rule that cannot be read
        return f"the panel's quiet windows cannot be read ({type(exc).__name__}): no run starts"
    if why is not None:
        return str(why)
    try:
        spent = cpu_spent(store, now)
    except Exception as exc:  # noqa: BLE001
        return f"the day's panel CPU cannot be read ({type(exc).__name__}): no run starts"
    if spent >= float(c["cpu_seconds_day"]):
        if c["cpu_seconds_day"] > 0:
            _cpu_alert(store, now)
        return "the day's panel Train CPU is spent (elane.panel.cpu_seconds_day): the round waits for the next UTC day"
    return None


def _cpu_alert(store: Any, now: float) -> None:
    """THE DAY'S CPU SPENT EARLY (E4-SPEC 17): spent before 12:00Z on three UTC days running is one warning (a
    `swarm.status` alert, once a day; the days are kept in the kv `ALERTS_KEY`). Never raises."""
    try:
        if time.gmtime(float(now)).tm_hour >= 12:
            return
        day = _utc_day(now)
        with store.atomic():
            held = store.get(ALERTS_KEY)
            held = dict(held) if isinstance(held, Mapping) else {}
            early = [str(d) for d in (held.get("cpu_early") or []) if isinstance(d, str)]
            if day in early:
                return
            early = sorted({*early, day})[-3:]
            store.put(ALERTS_KEY, {**held, "cpu_early": early})
        if all(_utc_day(float(now) - 86400.0 * back) in early for back in range(3)):
            store.event("swarm.status", None, {
                "action": "elane_xs_cpu", "alert": True,
                "text": "the panel lane's CPU for the day (elane.panel.cpu_seconds_day) was spent before 12:00Z on "
                        "three days running: its Train rounds wait most of each day"})
    except Exception:  # noqa: BLE001 - an alert that cannot be written stops no round
        pass


def book_cpu(store: Any, seconds: float, now: float) -> None:
    """Add a run's child seconds to the UTC day's count (`CPU_KEY`; the last eight days are kept)."""
    seconds = float(seconds)
    if not math.isfinite(seconds) or seconds <= 0:
        return
    day = _utc_day(now)
    with store.atomic():
        held = store.get(CPU_KEY)
        days = {str(k): float(v) for k, v in (held.items() if isinstance(held, Mapping) else ()) if _num(v) is not None}
        days[day] = round(days.get(day, 0.0) + seconds, 3)
        store.put(CPU_KEY, {k: days[k] for k in sorted(days)[-8:]})


def outside(result: Mapping[str, Any] | None, span: tuple[dt.date, dt.date]) -> list[str]:
    """What of a Train result lies outside its own span (WINDOW): a by-year row of another year, a run day (its start,
    its end, a daily row, a lot's entry or exit, a pick's execution day) outside the span or of 2016, 2020 or 2021,
    another window than "train". A decision day is not a run session (a span's first decision is taken at the close
    before it) and is not read here."""
    from ..xs import config as xconfig

    result = result if isinstance(result, Mapping) else {}
    first, last = span
    years = set(range(first.year, last.year + 1))
    barred = set(xconfig.HISTORY_YEARS) | set(xconfig.RESERVE_YEARS)
    out: list[str] = []
    rows = result.get("by_year")
    for key in (rows if isinstance(rows, Mapping) else ()):
        try:
            year = int(str(key)[:4])
        except ValueError:
            year = None
        if year is None or year not in years:
            out.append(str(key))
    days: list[Any] = [result.get("start"), result.get("end")]
    daily = result.get("daily")
    days += [row[0] for row in (daily if isinstance(daily, (list, tuple)) else ())
             if isinstance(row, (list, tuple)) and row]
    for name, keys in (("lots", ("entry_day", "exit_day")), ("picks", ("exec",))):
        rows = result.get(name)
        for row in (rows if isinstance(rows, (list, tuple)) else ()):
            if isinstance(row, Mapping):
                days += [row.get(k) for k in keys]
    for value in days:
        if value in (None, ""):
            continue
        day = _day(value)
        if day is None or not first <= day <= last or day.year in barred:
            out.append(str(value)[:10])
    window = result.get("window")
    if window not in (None, "train"):
        out.append(str(window))
    return list(dict.fromkeys(out))


def _pooled(results: Sequence[Mapping[str, Any]]) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    """Several runs of one version at one k read as one (`league.xs.results.pooled`): (its summary, its year rows).
    ValueError when the answer is no reading (the House's failure, never the program's)."""
    from ..xs import results as R

    out = R.pooled([dict(r) for r in results])
    if not isinstance(out, Mapping):
        raise ValueError("the pooled reading of the seen spans' runs is no mapping")
    summary = out.get("summary") if isinstance(out.get("summary"), Mapping) else out
    years = out.get("by_year") if isinstance(out.get("by_year"), Mapping) else {}
    if _num(summary.get("sum_x")) is None:
        raise ValueError("the pooled reading of the seen spans' runs carries no residual sum")
    return summary, {str(k): v for k, v in years.items() if isinstance(v, Mapping)}


def _round(value: Any, places: int) -> float | None:
    x = _num(value)
    return round(x, places) if x is not None else None


def train_score_xs(runs: Mapping[str, Any], *, years_ok: Sequence[int]) -> dict[str, Any]:
    """The bar's verdict on one version's seen-span runs: `runs` {"spans": [(first, last)], "base": [result a span, k
    1.0], "stress": [result a span, k 1.5, with its placebo block], "halves": {0: [...], 1: [...]} (k 1.5), "placebo":
    [block a span] (default: the stress results' own)}; `years_ok` the Train years the panel store covers. -> {objective,
    passed, fails, why, judged (the bar read the mechanism: a pass or a fail of `JUDGED_XS`), score (the residual's
    pooled t at 1.0x), facts (the seen spans' facts at both k and each rule's pass or fail, NO calendar year: the
    years are counted in time order, so no fact names the hidden one), sealed {"halves", "placebo"} (the caller moves
    them to the sealed keys: never in the record)}. A result outside its span is WINDOW and a run that did not end
    "ok" is RUN, each judged on nothing else. ValueError for runs that do not fit their spans or cannot be pooled
    (the House's)."""
    from ..xs import config as xconfig
    from ..xs import placebo as P

    spans = [tuple(s) for s in (runs.get("spans") or ())]
    base, stress = [dict(r) for r in runs.get("base") or ()], [dict(r) for r in runs.get("stress") or ()]
    halves = runs.get("halves") if isinstance(runs.get("halves"), Mapping) else {}
    sides = [[dict(r) for r in (halves.get(h) or halves.get(str(h)) or ())] for h in HALVES]
    out: dict[str, Any] = {"objective": OBJECTIVE, "passed": False, "fails": [], "why": None, "judged": False,
                           "score": None, "facts": {}, "sealed": {}}
    groups = [base, stress, *sides]
    if not spans or any(len(group) != len(spans) for group in groups):
        raise ValueError("the Train runs do not fit their seen spans (one run a span at each k and for each half)")
    if any(outside(result, span) for group in groups for result, span in zip(group, spans)):
        out["fails"], out["why"] = ["WINDOW"], FAILS_XS["WINDOW"]
        return out
    if any(str(result.get("status")) != "ok" for group in groups for result in group):
        out["fails"], out["why"] = ["RUN"], PROGRAM_FAILS["RUN"]
        return out
    ok = set(int(y) for y in years_ok)
    seen = [y for first, last in spans for y in range(first.year, last.year + 1)
            if y in ok and y in xconfig.TRAIN_YEARS]
    s10, y10 = _pooled(base)
    s15, y15 = _pooled(stress)
    side_sums = [_num(_pooled(side)[0].get("sum_x")) for side in sides]
    sum10, sum15 = _num(s10.get("sum_x")), _num(s15.get("sum_x"))
    t10, t15 = _num(s10.get("t_x")), _num(s15.get("t_x"))
    days = int(_num(s10.get("days")) or 0)
    invested = int(_num(s10.get("invested_days")) or 0)
    rebalances = int(_num(s10.get("rebalances")) or 0)
    year_sums = [(y, _num((y10.get(str(y)) or {}).get("sum_x")), _num((y15.get(str(y)) or {}).get("sum_x")),
                  int(_num((y10.get(str(y)) or {}).get("days")) or 0)) for y in seen]
    positive = [y for y, _, at15, _ in year_sums if at15 is not None and at15 > 0]
    need = int(math.ceil(BAR_XS["year_share"] * len(seen) - 1e-9))
    segments_ok = all(any(y in positive for y in seen if first.year <= y <= last.year)
                      for first, last in xconfig.TRAIN_SEGMENTS if any(first.year <= y <= last.year for y in seen))
    blocks = list(runs.get("placebo") or [result.get("placebo") for result in stress])
    count = draws = None
    identity_share = None
    if all(isinstance(b, Mapping) for b in blocks) and blocks:
        stat = [float(x) for x in P.stat([dict(b) for b in blocks], "run")]
        draws = len(stat)
        count = sum(1 for t in stat if math.isfinite(t) and t15 is not None and t >= t15)
        shares = [_num(b.get("identity_share")) for b in blocks]
        identity_share = round(math.fsum(x for x in shares if x is not None) / len(shares), 4) \
            if all(x is not None for x in shares) else None
    allowed = int(math.floor(draws * (1.0 - BAR_XS["placebo_rank"]) + 1e-9)) if draws else None
    rules = {
        "XA0": rebalances >= BAR_XS["min_rebalances"] and days > 0 and invested >= BAR_XS["min_invested"] * days,
        "XT1": t15 is not None and t15 >= BAR_XS["t_min"],
        "XY1": bool(seen) and len(positive) >= need and segments_ok,
        "XH1": all(x is not None and x > 0 for x in side_sums),
        "XP1": t15 is not None and bool(draws) and count is not None and count <= allowed,
        "XR1": sum10 is not None and sum10 > 0 and sum15 is not None and sum15 >= BAR_XS["cost_ratio"] * sum10,
    }
    # XA0 is the program's (it refutes nothing): an inactive program is judged on no other rule.
    fails = ["XA0"] if not rules["XA0"] else [code for code in JUDGED_XS if not rules[code]]
    vanished = s10.get("vanished") if isinstance(s10.get("vanished"), Mapping) else {}
    flags = []
    worst = _num(s15.get("sum_x_h1"))
    if not fails and worst is not None and worst <= 0:
        flags.append(FLAG_SURVIVORSHIP)
    out.update({
        "passed": not fails, "fails": fails, "why": "; ".join(FAILS_XS[f] for f in fails) or None,
        "judged": not fails or any(f in JUDGED_XS for f in fails), "score": _round(t10, 4), "flags": flags,
        "facts": {
            "seen_years": len(seen), "years_positive": len(positive), "years_needed": need,
            "years": [{"sum_x_10": _round(at10, 6), "sum_x_15": _round(at15, 6), "days": n}
                      for _, at10, at15, n in year_sums],
            "k10": {"sum_x": _round(sum10, 6), "t_x": _round(t10, 4), "t_r": _round(s10.get("t_r"), 4),
                    "rebalances": rebalances, "days": days,
                    "invested_share": round(invested / days, 4) if days else None,
                    "names_mean": _round(s10.get("names_mean"), 2), "turnover": _round(s10.get("turnover"), 4),
                    "cost_share": _round(s10.get("cost_share"), 4),
                    "exposure_mean": _round(s10.get("exposure_mean"), 4)},
            "k15": {"sum_x": _round(sum15, 6), "t_x": _round(t15, 4)},
            "rules": {code: bool(held) for code, held in rules.items()},
            "vanished": {str(k): int(_num(v) or 0) for k, v in vanished.items()},
            "haircut": {"sum_x_h0": _round(s15.get("sum_x_h0"), 6), "sum_x_h1": _round(worst, 6)},
        },
        "sealed": {
            "halves": {"sum_x": [_round(x, 6) for x in side_sums]},
            "placebo": {"draws": draws, "count": count, "allowed": allowed,
                        "rank": round(1.0 - count / draws, 4) if draws and count is not None else None,
                        "identity_share": identity_share},
        },
    })
    return out


def _reset_due(call: int, resets: Sequence[int] = BAR_XS["state_resets"]) -> bool:
    """Whether instance B of the restart check is loaded fresh before call `call` (0-based): after calls 3, 10, 13, 20,
    23, 30 and on (gaps of `resets`: 3 and 7 calls, so no counter of any period stays in phase with the resets)."""
    first, gap = int(resets[0]), int(resets[1])
    period = first + gap
    return call > 0 and call % period in (first % period, 0)


def same_targets(a: Mapping[str, Any], b: Mapping[str, Any]) -> bool:
    """WHAT MATCHES in the restart check: two decide answers both hold, or name the same fill point and the same ids
    with every weight within `WEIGHT_TOL` (a target that came back through JSON has string keys: read with `int`)."""
    def held(row: Mapping[str, Any]) -> bool:
        return bool(row.get("hold")) or not isinstance(row.get("target"), Mapping)

    if held(a) or held(b):
        return held(a) and held(b)
    if a.get("at") != b.get("at"):
        return False
    try:
        ta = {int(k): float(v) for k, v in a["target"].items()}
        tb = {int(k): float(v) for k, v in b["target"].items()}
    except (TypeError, ValueError):
        return False
    return set(ta) == set(tb) and all(abs(ta[k] - tb[k]) <= WEIGHT_TOL for k in ta)


def _asked(row: Mapping[str, Any]) -> tuple[int | None, int | None, bool]:
    """(the decides the answering instance has run since it was loaded, the errors it has counted since, whether it is
    disqualified) from one job's answer (`stats`); a None for a count the answer does not carry."""
    stats = row.get("stats")
    stats = stats if isinstance(stats, Mapping) else {}
    calls, errors = (None if isinstance(x, bool) or not isinstance(x, int) else x
                     for x in (stats.get("calls"), stats.get("errors")))
    return calls, errors, bool(stats.get("disqualified"))


#: What of a restart check the record keeps (`with_state`): counts only, no market figure.
STATE_KEYS = ("calls", "matched", "share", "resets", "need", "disqualified", "failed", "first_miss")


def state_check(decider: Any, code: str, params: Mapping[str, Any] | None, *, name: str,
                runs: Sequence[Any]) -> dict[str, Any]:
    """THE RESTART CHECK on the k 1.5 runs (`league.xs.runner.state_stream`): instance A loaded once, instance B
    loaded fresh after calls 3, 10, 13, 20, 23, 30 and on, both deciding on THE SAME `Inputs` at every called
    decision. A call matches when `at` is equal, the two targets name the same ids, every weight is within 1e-6 and
    the errors moved by the same count. Never a silent pass: `elane_train.StateCheckInterrupted` when an answer's
    `stats.calls` is not what its instance was asked, or the decider restarted. -> {calls, matched, share, resets,
    need, held, disqualified (the calls an instance was disqualified at: they match nothing), failed (the calls the
    two decides did not count the same errors), first_miss {span, call, after_reset}}. The decider's own errors pass
    through (a child that failed; a program it would not load). Every instance is dropped at the end."""
    from ..xs import KIND
    from ..xs import runner as xrunner
    from .elane_train import StateCheckInterrupted

    if decider is None:
        raise StateCheckInterrupted("the panel runner has no decider: the restart check cannot run")
    need = float(BAR_XS["state_match"])
    payload = {"code": str(code), "params": dict(params or {}), "name": str(name), "timeout": DECIDE_TIMEOUT,
               "max_errors": DECIDE_MAX_ERRORS}
    restarts = getattr(decider, "restarts", None)
    loaded: list[str] = []
    calls = matched = disqualified = failed = 0
    first_miss: dict[str, int] | None = None

    def load(key: str) -> dict[str, int]:
        loaded.append(key)
        decider.kind_load(KIND, key, payload)
        return {"asked": 0, "errors": 0}

    def drop(key: str) -> None:
        loaded.remove(key)
        decider.kind_drop(KIND, key)

    try:
        for span, run in enumerate(runs):
            a, b = f"xs-state:{name}:{span}:a", ""
            tally = {a: load(a)}
            seen = resets = since = 0
            for i, inputs in enumerate(xrunner.state_stream(run)):
                if i == 0 or _reset_due(i):
                    if b:
                        drop(b)
                        tally.pop(b, None)
                    b, resets, since = f"xs-state:{name}:{span}:b{resets}", resets + 1, i
                    tally[b] = load(b)
                answer = decider.kind(KIND, "decide", {"jobs": [{"key": a, "inputs": inputs, "called": True},
                                                                {"key": b, "inputs": inputs, "called": True}]})
                if getattr(decider, "restarts", None) != restarts:
                    raise StateCheckInterrupted("the panel's decider child restarted during the restart check (its "
                                                "instances were reloaded with fresh memory)")
                results = answer.get("results") if isinstance(answer, Mapping) and answer.get("ok") else None
                if not isinstance(results, Mapping):
                    why = answer.get("error") if isinstance(answer, Mapping) else type(answer).__name__
                    raise StateCheckInterrupted(f"the panel's decider child did not answer a decide: {str(why)[:200]}")
                ra, rb = results.get(a), results.get(b)
                if not isinstance(ra, Mapping) or not isinstance(rb, Mapping) or ra.get("missing") or rb.get("missing"):
                    raise StateCheckInterrupted("an instance of the restart check went missing in the decider child")
                if ra.get("error") or rb.get("error"):
                    raise StateCheckInterrupted("the child could not build a ctx: "
                                                f"{str(ra.get('error') or rb.get('error'))[:200]}")
                out = False
                erred: list[int] = []
                for key, row in ((a, ra), (b, rb)):
                    mine = tally[key]
                    mine["asked"] += 1
                    asked, errors, gone = _asked(row)
                    if asked is None or errors is None:
                        raise StateCheckInterrupted("a decide answer carries no call count or no error count "
                                                    "(stats.calls, stats.errors): a reloaded instance or a failed "
                                                    "decide could not be told from a sound one")
                    if gone:
                        out = True  # a disqualified instance answers nothing and counts no call: no match
                    elif asked != mine["asked"] or errors < mine["errors"]:
                        raise StateCheckInterrupted(f"the decider child reloaded an instance during the restart check "
                                                    f"(it answered its decide {asked}, not {mine['asked']}): its "
                                                    "memory was lost")
                    else:
                        erred.append(errors - mine["errors"])
                        mine["errors"] = errors
                calls, seen = calls + 1, seen + 1
                same = False
                if out:
                    disqualified += 1
                elif erred[0] != erred[1]:
                    failed += 1  # one decide failed (or answered a malformed target) and the other did not: no match
                else:
                    same = same_targets(ra, rb)
                if same:
                    matched += 1
                elif first_miss is None:
                    first_miss = {"span": span, "call": i, "after_reset": i - since}
            if not seen:
                raise StateCheckInterrupted(f"seen span {span} gave the restart check no called decision")
    finally:
        for key in list(loaded):
            try:
                decider.kind_drop(KIND, key)
            except Exception:  # noqa: BLE001 - a drop that fails leaves an instance a restart clears
                pass
    if not calls:
        raise StateCheckInterrupted("the restart check had no called decision to compare")
    return {"calls": calls, "matched": matched, "share": round(matched / calls, 4),
            "resets": list(BAR_XS["state_resets"]), "need": need, "disqualified": disqualified, "failed": failed,
            "held": matched >= need * calls - 1e-9, "first_miss": first_miss}


def restart(researcher: Any, code: str, params: Mapping[str, Any] | None, *, name: str,
            runs: Sequence[Any]) -> dict[str, Any]:
    """THE RESTART CHECK of a panel version through the panel's own decider (E2's `EquityResearcher.restart` forwards a
    panel family here): `state_check` on the k 1.5 seen-span runs."""
    return state_check(_decider_of(_runner_of(researcher), _root_of(researcher)), code, params, name=name, runs=runs)


def with_state(verdict: Mapping[str, Any], check: Mapping[str, Any]) -> dict[str, Any]:
    """A bar verdict with its restart check: as it was when the check held, else failed STATE (its Train facts kept).
    A check with no call compared never holds."""
    out = dict(verdict)
    out["state"] = {k: check.get(k) for k in STATE_KEYS}
    if not check.get("held") or not check.get("calls"):
        out.update(passed=False, fails=["STATE"],
                   why=f"{FAILS_XS['STATE']}: {check.get('matched')} of {check.get('calls')} calls matched")
    return out


def program_fault(code: str, why: str) -> dict[str, Any]:
    """The verdict of a version judged on its program alone (RUN, DQ, LOAD): no figure."""
    return {"objective": OBJECTIVE, "passed": False, "fails": [code], "why": f"{PROGRAM_FAILS[code]}: {why}"[:400],
            "judged": False, "score": None, "facts": {}, "flags": []}


def compact(n: int, verdict: Mapping[str, Any], *, at: str, ident: Mapping[str, Any] | None,
            style: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """A version's verdict as the record keeps it: {n, at, objective, identity, verdict, passed, fails, why, score,
    facts, flags, state (the restart check's counts), style (A22's verdict)}. Train facts and counts only; nothing
    sealed (the halves, the placebo rank and the hidden run go to their own keys)."""
    out = {"n": int(n), "at": at, "objective": OBJECTIVE, "identity": dict(ident) if isinstance(ident, Mapping) else None,
           "verdict": "pass" if verdict.get("passed") else "fail", "passed": bool(verdict.get("passed")),
           "fails": list(verdict.get("fails") or []), "why": verdict.get("why"), "score": verdict.get("score"),
           "facts": _plain(verdict.get("facts") or {}), "flags": list(verdict.get("flags") or [])}
    if isinstance(verdict.get("state"), Mapping):
        out["state"] = dict(verdict["state"])
    if isinstance(style, Mapping):
        out[STYLE_FIELD] = _plain(style)
    return out


def _style(results: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
    """A22 (1): the style verdict of a version from its seen spans' full-universe k 1.0 runs (`league.xs.style.pooled`
    then `style_open`). None when the rule cannot be asked (read as style-open at the look)."""
    try:
        from ..xs import style as Y

        return dict(Y.style_open(Y.pooled([r.get("style") for r in results])))
    except Exception:  # noqa: BLE001 - no reading: unmeasured, which opens (the rule fails closed at the seat)
        return None


def _named(exc: BaseException, names: Sequence[str]) -> bool:
    return any(cls.__name__ in names for cls in type(exc).__mro__)


class _Waits(RuntimeError):
    """A run that may not start now (`may_run`): the version's judgment waits, nothing scored."""


def house_failure(researcher: Any, fam: Mapping[str, Any], n: int, why: str, *, kind: str) -> dict[str, Any] | None:
    """A failure of the House's (E2's rule, on the panel's record): nothing scored, no budget, no model call; a backoff
    that doubles with every failure of the version, of any kind. COUNTED BY KIND: for a child's run failure ("run")
    whose streak reaches `train_max_errors` while other programs' panel judgments completed since the streak's first,
    None: the caller judges the program RUN. A result outside its span ("window") is an alert at once; a restart check
    that could not run or finish ("state") once, at its `train_max_errors`-th."""
    from . import elane_train

    c = elane_train.cfg(researcher.settings)
    store = researcher.store
    fid = str(fam["id"])
    now = researcher.clock()
    held = record_of(store.family(fid) or fam).get("infra")
    held = dict(held) if isinstance(held, Mapping) and held.get("version") == n else {}
    count = int(held.get("count") or 0) + 1
    first = _num(held.get("first_at")) or now
    again = held.get("kind") == kind
    streak = (int(held.get("streak") or 0) if again else 0) + 1
    since = (_num(held.get("streak_at")) if again else None) or now
    kinds = {str(k): int(v) for k, v in (held.get("kinds") if isinstance(held.get("kinds"), Mapping) else {}).items()
             if isinstance(v, int) and not isinstance(v, bool)}
    kinds[kind] = kinds.get(kind, 0) + 1
    alerted = [str(k) for k in (held.get("alerted") if isinstance(held.get("alerted"), list) else [])]
    if kind == "run" and streak >= c["train_max_errors"] and (_num(store.get(TRAIN_OK_KEY)) or 0.0) > since:
        return None
    delay = min(float(c["train_every_seconds"]) * (2 ** min(count - 1, 12)), BACKOFF_MAX)
    tell = kind == "state" and kinds[kind] >= c["train_max_errors"] and kind not in alerted
    if tell:
        alerted.append(kind)
    record = {"version": n, "count": count, "first_at": first, "next_at": now + delay, "kind": kind, "why": why[:240],
              "streak": streak, "streak_at": since, "kinds": kinds, "alerted": alerted}
    _update(store, fid, lambda r: r.update(infra=record))
    if kind == "window":
        store.event("swarm.status", fid, {"action": "elane_xs_window", "alert": True, "version": n,
                                          "text": "a panel Train result carried a day outside its seen span, or of "
                                                  "2016, 2020 or 2021: refused whole; nothing is judged on it (check "
                                                  "the panel runner)"})
    if tell:
        store.event("swarm.status", fid, {"action": "elane_xs_state", "alert": True, "version": n,
                                          "text": f"the panel Train bar's restart check (STATE) could not finish "
                                                  f"{kinds[kind]} times since this version was last judged: "
                                                  f"{why[:160]}; the version is not scored and cannot pass until it "
                                                  "does (check the panel's decider)"})
    return {"family": fid, "version": n, "house": kind, "why": why[:200], "retry_in": delay}


def fault(researcher: Any, fam: Mapping[str, Any], n: int, exc: BaseException, *,
          check: bool = False) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """A Train run's exception, or the restart check's (`check`), judged as E2 judges its own: (the program's verdict,
    None) for LOAD, or for RUN once the child failed it `train_max_errors` times in a row while other programs'
    judgments completed; else (None, the House's backoff answer)."""
    from . import elane_train

    why = f"{type(exc).__name__}: {str(exc)[:200]}"
    if _named(exc, elane_train.LOAD_REFUSALS):
        return program_fault("LOAD", str(exc)[:300]), None
    kind = "run" if _named(exc, elane_train.RUN_FAILURES) else ("state" if check else "store")
    out = house_failure(researcher, fam, n, why, kind=kind)
    return (None, out) if out is not None else (program_fault("RUN", why), None)


def years_ok(root: Any) -> list[int] | None:
    """The Train years the panel store covers (its manifest's `train_years_ok`), or None when it names none."""
    from ..xs import config as xconfig

    manifest = _manifest(root)
    ok = manifest.get("train_years_ok") if manifest is not None else None
    if not isinstance(ok, list):
        return None
    return [int(y) for y in ok if isinstance(y, int) and not isinstance(y, bool) and y in xconfig.TRAIN_YEARS]


def _stored(result: Mapping[str, Any], k: float) -> dict[str, Any]:
    """What of a seen-span run the store's `runs` keep: its Train view (`league.xs.results.view`: status, summary,
    by-year rows, the picks' counts, the runtime), its id and span. Never a daily row, a lot, an id or a placebo."""
    try:
        from ..xs import results as R

        view = dict(R.view(result, "train"))
    except Exception:  # noqa: BLE001 - the verdict stands; the row then keeps the status alone
        view = {"status": result.get("status")}
    return {**view, "run_id": result.get("run_id"), "trials": int(result.get("trials") or 1), "window": "train",
            "k": float(k), "start": result.get("start"), "end": result.get("end")}


def _hidden_run(researcher: Any, fam: Mapping[str, Any], version: Mapping[str, Any], hidden: int,
                years_ok: Sequence[int]) -> None:
    """THE HIDDEN RUN, after the verdict is recorded: one run at each k over `hidden_span(hidden)`, starting flat, its
    sum, t, days and status into the sealed `OOF_KEY` and nowhere else (never `add_run`, never the record, no event).
    A hidden run the House failed, or that may not start now, writes nothing and is not tried again."""
    if hidden not in years_ok:
        return
    store, settings = researcher.store, researcher.settings
    fid, n = str(fam["id"]), int(version["n"])
    code, params = str(version.get("code") or ""), dict(version.get("params") or {})
    first, last = hidden_span(hidden)
    row: dict[str, Any] = {}
    try:
        run_through = _runner_of(researcher)
        for k in (K_BASE, K_STRESS):
            if may_run(store, settings, researcher.clock()) is not None:
                return
            began = time.monotonic()
            try:
                run = run_through.train(code, params, name=fid, start=first, end=last, k=float(k))
            finally:
                book_cpu(store, time.monotonic() - began, researcher.clock())
            result = dict(getattr(run, "result", None) or {})
            summary = result.get("summary") if isinstance(result.get("summary"), Mapping) else {}
            row[f"{k:g}"] = {"status": str(result.get("status") or "unknown"), "sum_x": _round(summary.get("sum_x"), 6),
                             "t_x": _round(summary.get("t_x"), 4), "days": int(_num(summary.get("days")) or 0)}
    except Exception:  # noqa: BLE001 - the House's: no out-of-fold row for this version
        return
    held = _state(store.family(fid) or {}).get(OOF_KEY)
    store.set_state(fid, **{OOF_KEY: {**(dict(held) if isinstance(held, Mapping) else {}), str(n): row}})


def score(researcher: Any, fam: Mapping[str, Any], version: Mapping[str, Any], *,
          rescore: bool = False) -> dict[str, Any]:
    """One version's Train judgment (`may_run` first; the runs, the bar, the restart check, the record, then the
    hidden run). It writes E3's scored event for every version judged on the bar (`swarm.elane` {"pass": "scored",
    version, sha, bar_passed, fails, objective: OBJECTIVE, judged}), which is the forward registry's time evidence.
    THE STYLE READING (A22 (1)) is taken here, from the seen spans' full-universe k 1.0 runs, and kept in the record
    under `STYLE_FIELD` whatever the bar said. `rescore` (a pass judged under another xs identity, or under
    provisional costs): passed again it stands, else the pass is withdrawn."""
    store, settings = researcher.store, researcher.settings
    root = _root_of(researcher)
    c = cfg(settings)
    fid, n = str(fam["id"]), int(version["n"])
    code, params = str(version.get("code") or ""), dict(version.get("params") or {})
    if MODES.index(mode(settings, root)) < MODES.index("train"):
        return {"family": fid, "version": n, "skipped": "the panel lane is closed (elane.panel.mode)"}
    covered = years_ok(root)
    hidden = hidden_year_of(fam)
    spans = run_spans(hidden, covered) if covered is not None else ()
    if not spans:
        return house_failure(researcher, fam, n, "the panel store names no Train year the bar can run on",
                             kind="store") or {}
    run_through = _runner_of(researcher)

    def run_one(**kw: Any) -> Any:
        why = may_run(store, settings, researcher.clock())
        if why is not None:
            raise _Waits(why)
        began = time.monotonic()
        try:
            return run_through.train(code, params, name=fid, **kw)
        finally:
            book_cpu(store, time.monotonic() - began, researcher.clock())

    runs: dict[Any, list[Any]] = {"base": [], "stress": [], 0: [], 1: []}
    verdict: dict[str, Any] | None = None
    try:
        for first, last in spans:
            runs["base"].append(run_one(start=first, end=last, k=K_BASE, style=True))
            runs["stress"].append(run_one(start=first, end=last, k=K_STRESS, placebos=int(c["placebos_train"]),
                                          calls=True))
            for half in HALVES:
                runs[half].append(run_one(start=first, end=last, k=K_STRESS, half=half))
    except _Waits as wait:
        return {"family": fid, "version": n, "skipped": str(wait)}
    except Exception as exc:  # noqa: BLE001 - a refusal is the program's; a run failure is judged below
        verdict, out = fault(researcher, fam, n, exc)
        if out is not None:
            return out
    sealed: dict[str, Any] = {}
    style: dict[str, Any] | None = None
    if verdict is None:
        parts = {key: [dict(getattr(run, "result", None) or {}) for run in rs] for key, rs in runs.items()}
        if any(outside(result, span) for rs in parts.values() for result, span in zip(rs, spans)):
            return house_failure(researcher, fam, n, "a panel Train result carried a day outside its seen span",
                                 kind="window") or {}
        statuses = {str(result.get("status")) for rs in parts.values() for result in rs}
        if "disqualified" in statuses:
            why = next((str(r["reason"]) for rs in parts.values() for r in rs if r.get("reason")),
                       "its own errors or timeouts")
            verdict = program_fault("DQ", why)
        elif statuses != {"ok"}:
            return house_failure(researcher, fam, n, f"the panel Train runs ended {', '.join(sorted(statuses))}",
                                 kind="store") or {}
        else:
            try:
                verdict = train_score_xs({"spans": spans, "base": parts["base"], "stress": parts["stress"],
                                          "halves": {0: parts[0], 1: parts[1]}}, years_ok=covered or ())
            except Exception as exc:  # noqa: BLE001 - a reading that cannot be made is the House's
                return house_failure(researcher, fam, n, f"the bar could not read the runs ({type(exc).__name__}: "
                                                         f"{str(exc)[:160]})", kind="store") or {}
            sealed = dict(verdict.pop("sealed", None) or {})
            through = True
            if verdict["passed"]:
                # THE RESTART CHECK: no pass without it (E2's rule: what stops it is the House's, or, for a child that
                # keeps failing it while other programs are judged, the program's).
                try:
                    check = restart(researcher, code, params, name=fid, runs=runs["stress"])
                except Exception as exc:  # noqa: BLE001 - judged as a run's failure is
                    verdict, out = fault(researcher, fam, n, exc, check=True)
                    if out is not None:
                        return out
                    through = False
                else:
                    verdict = with_state(verdict, check)
            if through:
                store.put(TRAIN_OK_KEY, researcher.clock())
            style = _style(parts["base"])  # A22 (1): kept whatever the bar said
            share = _num((_manifest(root) or {}).get("hs_share"))
            if share is None or share < c["spreads_min_share"]:
                verdict["flags"] = [*(verdict.get("flags") or []), FLAG_COSTS]
            for key, k in (("base", K_BASE), ("stress", K_STRESS)):
                for result in parts[key]:
                    try:
                        store.add_run(fid, n, _stored(result, k), window="train", stress=float(k),
                                      purpose="elane_xs_train")
                    except Exception:  # noqa: BLE001 - the verdict stands without the stored run
                        pass
    at = store.now()
    entry = compact(n, verdict, at=at, ident=identity(), style=style)
    if rescore:
        return rescored(researcher, fam, n, entry, sealed)
    fresh = str(n) not in versions_of(record_of(store.family(fid) or fam))

    def put(r: dict[str, Any]) -> None:
        r.pop("infra", None)
        r["versions"] = {**(r.get("versions") or {}), str(n): entry}
        if entry["passed"] and r.get("passed_version") is None:
            r["review"] = {"version": n, "unclear": {}, "at": at}  # THE REVIEW, before the pass is the try
    rec = _update(store, fid, put)
    _seal(store, fid, n, sealed)
    if fresh:
        try:  # E3's scored event, E2's own kind: the forward registry's time evidence of a panel version
            store.event("swarm.elane", fid, {"pass": "scored", "version": n, "sha": str(version.get("sha") or ""),
                                             "bar_passed": bool(entry["passed"]), "fails": list(entry["fails"]),
                                             "objective": OBJECTIVE, "judged": bool(entry["facts"]),
                                             "structure": STRUCTURE})
            # ...and the lane's own status line (E4-SPEC 13: a count and a verdict, never a figure)
            store.event("swarm.status", fid, {"action": "elane_xs_train", "version": n, "structure": STRUCTURE,
                                              "passed": bool(entry["passed"]), "fails": list(entry["fails"])})
        except Exception:  # noqa: BLE001 - the verdict stands; the registry then dates the version from its sighting
            pass
    if entry["facts"] and hidden is not None:
        _hidden_run(researcher, fam, version, hidden, covered or ())  # AFTER the verdict is recorded
    out: dict[str, Any] = {"family": fid, "version": n, "passed": bool(entry["passed"]), "fails": list(entry["fails"])}
    if entry["passed"]:
        out["review"] = review_step(researcher, store.family(fid) or fam, n)
        return out
    if len(versions_of(rec)) >= c["train_budget"]:
        out["retired"] = finish(researcher, store.family(fid) or fam, "its Train budget is spent with no version passing")
    return out


def _seal(store: Any, fid: str, n: int, sealed: Mapping[str, Any]) -> None:
    """A version's sealed Train figures (the halves' sums, the placebo rank) into their own keys, by version."""
    if not sealed:
        return
    state = _state(store.family(fid) or {})
    values = {}
    for key, name in ((HALVES_KEY, "halves"), (PLACEBO_KEY, "placebo")):
        if isinstance(sealed.get(name), Mapping):
            held = state.get(key)
            values[key] = {**(dict(held) if isinstance(held, Mapping) else {}), str(n): _plain(sealed[name])}
    if values:
        store.set_state(fid, **values)


def rescored(researcher: Any, fam: Mapping[str, Any], n: int, entry: Mapping[str, Any],
             sealed: Mapping[str, Any]) -> dict[str, Any]:
    """A stale pass judged again (another xs identity, or costs no longer provisional). Passed, its verdict is stamped
    with the identity in force (the review stands: the program is the same); failed, the pass is withdrawn (no
    `passed_version`, no `best_version`, no review record) and the family researches again with its budget."""
    from . import elane_review

    store = researcher.store
    fid = str(fam["id"])
    kept = bool(entry.get("passed"))

    def put(r: dict[str, Any]) -> None:
        r.pop("infra", None)
        old = dict((r.get("versions") or {}).get(str(n)) or {})
        fresh = dict(entry)
        if kept:
            fresh["rescored_from"] = old.get("identity")
        r["versions"] = {**(r.get("versions") or {}), str(n): fresh}
        if not kept:
            r["passed_version"], r["status"] = None, "researching"
            r["withdrawn"] = [*(r.get("withdrawn") or []), {"version": n, "at": entry.get("at"),
                                                           "fails": list(entry.get("fails") or [])}][-5:]
            r.pop("passed_review", None)
    _update(store, fid, put)
    _seal(store, fid, n, sealed)
    if kept:
        store.note(fid, f"v{n} passed {OBJECTIVE} on Train again under the xs identity now in force.")
        return {"family": fid, "version": n, "rescored": "kept"}
    store.update_family(fid, best_version=None, best_train=None)
    store.set_state(fid, **{elane_review.STATE_REVIEW: None})
    store.note(fid, f"v{n} no longer passes {OBJECTIVE} on Train under the xs identity now in force: its pass is "
                    "withdrawn and its Train research goes on.")
    return {"family": fid, "version": n, "rescored": "withdrawn", "fails": list(entry.get("fails") or [])}


# ------------------------------------------------------------------------------------------------- the researcher
RESEARCHER_SYSTEM = """You write ONE program for one family of the swarm's PANEL lane: long-only programs that pick 5 to 12 names out
of the day's S&P 500 members by a cross-sectional rule and hold them to the next rebalance, the House trading each change
at the next session's open or close with real money. You see your own family's Train runs and nothing else: no Validation
figure, no holdout figure and no other program's outcome. Validation (2025) and ONE sealed holdout look per lineage judge
every program, and nothing of them ever reaches a program's author, so a program cannot be fitted to them: write the
mechanism, not the history. The first version that passes the Train bar in the request AND the review is your lineage's
ONE Validation try: send the version you would stake the lineage on.
A PANEL PROGRAM IS JUDGED ON ITS RESIDUAL: its P&L after costs minus the P&L of random portfolios that hold the same
number of names at the same weights from the same sector, beta and 12-1 momentum cells on the same days. So market
direction, a sector bet and a tilt to high or low beta or momentum earn NOTHING; only which names you pick inside those
cells counts. A program whose holdings lean on size, beta, momentum or volatility can pass the screen and still take no
live seat. You see SALTED SLOTS: ctx.ids are labels that change every run, in no order that means anything; use them
only to name your targets. ctx holds no ticker, no date, no price level and no event flag: every field is a return, a
range, a relative volume, a sector code, a beta or a calendar count.
THE REVIEW (two other models) refuses: a table or constant that could hold returns, ranks or outcomes of past sessions
or names; any test that could tell which year, month or event a session is (from the calendar counts, the market's
path or the slots' histories); any use of ctx.ids beyond naming targets; any constant that could name a calendar
period; any search for a price level; and lookahead. THE STATE RULE (part of the bar): the House's decider restarts on
every deploy and a restart empties STATE, so the bar asks your program again after fresh loads and fails it (STATE)
unless its targets match the uninterrupted run's on 99% of its calls. Read holdings from ctx.positions, never from a
count or a list you keep; your decide must work on an empty STATE at any call.

Reply with ONE JSON object: {"program": "<the whole Python file>", "note": "what this version changes and why, one or two
sentences"}; or, once a version of yours was judged by the bar (XT1, XY1, XH1, XP1 or XR1) and no honest revision is
left, {"stop": "why, in one or two sentences"}. PARAMS are your program's own declaration (the House runs it as written).

THE PANEL CONTRACT (league/xs/XS.md):
"""
#: What a review failure of a panel program may cite, by `REVIEW_XS`'s line (the references are E2's own four:
#: `elane_review.FACTS`, which `elane_review.grounded` holds a failure to).
REVIEW_REFERENCES = ("calendar", "calendar", "context", "calendar", "levels")
REVIEW_SYSTEM = (
    "You review long-only PANEL programs before their ONE Validation try and ONE sealed holdout look. A panel program is "
    "one Python file (NEEDS, PARAMS, decide(ctx)) that picks 5 to 12 names out of the day's S&P 500 members at each "
    "rebalance: on the Train years (2017-19 and 2022-24), then unchanged on Validation (2025), the holdout and real "
    "money. It sees salted slots: no ticker, no date, no price level, no event flag; ctx.ids are labels re-drawn every "
    "run. Its author saw only its Train runs, but the models that write programs remember the market's history, so a "
    "program can encode a remembered period or remembered winners without any figure in sight.\n"
    "Refuse it (verdict \"fail\") for any of:\n"
    + "".join(f"- {line} (cite the reference \"{ref}\").\n" for line, ref in zip(REVIEW_XS, REVIEW_REFERENCES))
    + "- lookahead: anything that could know the future inside the replay (it only sees ctx at the decision close; its "
    "orders fill at the NEXT session's open or close) (cite \"fills\").\n"
    "Relative measures (returns, ranges, relative volume, ranks across the slots of one call, the sector codes and "
    "betas ctx gives) and ctx's own calendar counts used as a clock for a rebalance are fine; a warm-up that waits for "
    "enough history is fine. Use the contract in this prompt as the execution contract. Do not invent unavailable "
    "fields. Distinguish a verified defect from an unresolved concern; reply unclear when the evidence is "
    "insufficient.\n"
    "For EACH failure provide a verbatim code excerpt present in the submitted file, a contract_reference (one of: "
    "levels, calendar, context, fills), and a causal counterexample: exact input conditions and the bad decision that "
    "follows. Otherwise pass it. Reply with ONE JSON object: {\"verdict\": \"pass\" or \"fail\" or \"unclear\", "
    "\"reasons\": [\"...\"], \"findings\": [{\"code_excerpt\": \"...\", \"contract_reference\": \"...\", "
    "\"counterexample\": \"...\"}], \"notes\": \"...\"}.\n\nTHE PANEL CONTRACT (league/xs/XS.md):\n")
#: The one sentence a hidden-year family's brief gains (no year is named).
HIDDEN_NOTE = ("One of the six Train years is held out from you: the bar reads the other five, each stretch of them its "
               "own run starting flat, and the held-out year's results are never shown.")


def rubric_sha() -> str:
    """The panel review's rubric as a review record names it (sha256 of `REVIEW_SYSTEM`, 16 hex): its provenance."""
    return hashlib.sha256(REVIEW_SYSTEM.encode("utf-8")).hexdigest()[:16]


def _pct(x: Any) -> str:
    v = _num(x)
    return "n/a" if v is None else f"{100 * v:.1f}%"


def _f(x: Any, places: int = 2) -> str:
    v = _num(x)
    return "n/a" if v is None else f"{v:.{places}f}"


def version_text(n: Any, v: Mapping[str, Any]) -> str:
    """One scored version in words (its seen-span Train facts, each rule's pass or fail, its restart check's counts,
    its style reading and the review's reasons). Never a half's figure, a placebo rank, an id or a year's name."""
    fails = list(v.get("fails") or [])
    facts = v.get("facts") if isinstance(v.get("facts"), Mapping) else {}
    if not facts:
        code = fails[0] if fails else "RUN"
        return f"v{n}: {v.get('why') or PROGRAM_FAILS.get(code) or FAILS_XS.get(code) or code}."
    if "REVIEW" in fails:
        status = "passed the Train bar but the REVIEW refused it"
    elif "STATE" in fails:
        status = "met XA0, XT1, XY1, XH1, XP1 and XR1 but failed STATE"
    else:
        status = "PASSED" if v.get("passed") else "failed " + ", ".join(fails)
    k10 = facts.get("k10") if isinstance(facts.get("k10"), Mapping) else {}
    k15 = facts.get("k15") if isinstance(facts.get("k15"), Mapping) else {}
    head = (f"v{n}: {status}. Residual at 1.0x: sum {_pct(k10.get('sum_x'))} of the sleeve, pooled t "
            f"{_f(k10.get('t_x'))}; at 1.5x: sum {_pct(k15.get('sum_x'))}, pooled t {_f(k15.get('t_x'))}. "
            f"{int(_num(k10.get('rebalances')) or 0)} rebalances, a lot held on {_pct(k10.get('invested_share'))} of "
            f"sessions, {_f(k10.get('names_mean'), 1)} names on average, turnover {_f(k10.get('turnover'))}, cost share "
            f"{_pct(k10.get('cost_share'))}; the raw P&L's t {_f(k10.get('t_r'))} (beside, never a bar).")
    years = "; ".join(f"year {i} {_pct(row.get('sum_x_10'))} / {_pct(row.get('sum_x_15'))}"
                      for i, row in enumerate(facts.get("years") or [], 1) if isinstance(row, Mapping))
    by_year = (f"Residual sum by seen year, in time order (1.0x / 1.5x): {years}; positive at 1.5x in "
               f"{facts.get('years_positive')} of {facts.get('seen_years')} ({facts.get('years_needed')} needed)."
               if years else "")
    rules = facts.get("rules") if isinstance(facts.get("rules"), Mapping) else {}
    ruled = ("Rules: " + ", ".join(f"{code} {'pass' if rules.get(code) else 'FAIL'}" for code in ("XA0", *JUDGED_XS)
                                   if code in rules) + ".") if rules else ""
    words = " ".join(f"({f}) {FAILS_XS[f]}." for f in fails if f in FAILS_XS and f != "STATE")
    flags = [str(f) for f in (v.get("flags") or [])]
    flagged = f"Flags: {', '.join(flags)}." if flags else ""
    review = v.get("review") if isinstance(v.get("review"), Mapping) else {}
    said = "; ".join(str(r) for r in (review.get("reasons") or [])[:3])
    told = (f"(REVIEW) the {review.get('stage') or 'review'} refused it: {said or PROGRAM_FAILS['REVIEW']}."
            if "REVIEW" in fails else "")
    return " ".join(x for x in (head, by_year, ruled, words, restart_text(v), style_text(v), flagged, told) if x)


def restart_text(v: Mapping[str, Any]) -> str:
    """A version's restart check in words ("" when it had none)."""
    state = v.get("state") if isinstance(v.get("state"), Mapping) else None
    if not state or not state.get("calls"):
        return ""
    miss = state.get("first_miss") if isinstance(state.get("first_miss"), Mapping) else None
    where = f"; they first differed on call {int(_num(miss.get('after_reset')) or 0) + 1} after a fresh load" if miss else ""
    gone = int(_num(state.get("disqualified")) or 0)
    lost = f"; on {gone} calls an instance was disqualified by its own errors (no match)" if gone else ""
    broke = int(_num(state.get("failed")) or 0)
    fell = (f"; on {broke} calls the decide failed (raised, timed out or answered a malformed target) in one run and "
            "not in the other (no match): a decide must work on an empty STATE at any call" if broke else "")
    return (f"Restart check: asked again after fresh loads, its targets matched the uninterrupted run's on "
            f"{state.get('matched')} of {state.get('calls')} calls ({_pct(state.get('share'))}; {_pct(state.get('need'))} "
            f"needed){where}{lost}{fell}.")


def style_text(v: Mapping[str, Any]) -> str:
    """A version's style reading in words ("" when it has none): whether its Train holdings read style-open and on
    which characteristics. A Train fact: a style-open program can pass the look and still take no seat."""
    style = v.get(STYLE_FIELD) if isinstance(v.get(STYLE_FIELD), Mapping) else None
    if style is None:
        return ""
    if not style.get("open"):
        return "Style reading: its Train holdings lean on no style (size, beta, momentum, volatility)."
    tilts = ", ".join(f"{name} {'high' if int(sign) > 0 else 'low'}" for name, sign in (style.get("tilts") or [])
                      if isinstance(name, str))
    return ("Style reading: STYLE-OPEN (" + (tilts or str(style.get("why") or "unmeasured")) + "): what it held sits "
            "in the top or bottom third of the day's names by that characteristic. A style-open program takes no live "
            "seat on a screen pass alone.")


def train_facts(fam: Mapping[str, Any]) -> dict[str, Any]:
    """What a researcher sees of its own family: the seen-span facts at both k and each rule's pass or fail, and
    whether its Train holdings read style-open and on which characteristics (a Train fact: a style-open program can
    pass the look and still take no seat). NEVER a half's figure, a placebo rank, an id, the hidden year, or anything
    after Train. Built by whitelist from the family's birth and its `STATE_KEY` record alone."""
    spec, rec = _spec(fam), record_of(fam)
    versions = {}
    for key, v in versions_of(rec).items():
        style = v.get(STYLE_FIELD) if isinstance(v.get(STYLE_FIELD), Mapping) else None
        versions[key] = {name: v.get(name) for name in ("n", "at", "objective", "verdict", "passed", "fails", "why",
                                                        "score", "facts", "flags", "state", "review", "bar_passed")
                         if name in v}
        if style is not None:
            versions[key][STYLE_FIELD] = {"open": bool(style.get("open")), "why": style.get("why"),
                                          "tilts": list(style.get("tilts") or [])}
    record = {name: rec.get(name) for name in ("status", "passed_version", "attempts", "refused", "refuted", "stalled",
                                               "withdrawn") if name in rec}
    record["versions"] = versions
    return {"id": str(fam.get("id")), "lineage": str(fam.get("lineage") or fam.get("id")), "lane": LANE,
            "structure": STRUCTURE, "agenda": str(spec.get("agenda") or OTHER), "panel": str(spec.get("panel") or PANELS[0]),
            "max_names": spec.get("max_names"), "rebalance": spec.get("rebalance"), "weekday": spec.get("weekday"),
            "mechanism": " ".join(str(fam.get("mechanism") or "").split()), "born_at": str(fam.get("born_at") or ""),
            "route": str(spec.get("e2_route") or ""), "held_out": hidden_year_of(fam) is not None, "record": record}


def brief(researcher: Any, fam: Mapping[str, Any]) -> str:
    """The question's user turn for a panel family: its card, its agenda prior, the bar and its own Train versions
    (`train_facts` only)."""
    from . import cards

    c = cfg(researcher.settings)
    facts = train_facts(fam)
    rec = facts["record"]
    agenda = PANEL_AGENDA.get(facts["agenda"], PANEL_AGENDA[OTHER])
    try:
        card = (cards.card_of(researcher.store, facts["id"]) or {}).get("card") or {}
    except Exception:  # noqa: BLE001 - the brief goes without the card
        card = {}
    when = (f"weekly (the first session of the week on or after weekday {int(facts['weekday'] or 0)})"
            if facts["rebalance"] == "weekly" else "monthly (the month's first session)")
    lines = [f"YOUR FAMILY: {facts['id']}, lane EQUITY, structure PANEL ({facts['panel']}): at most {facts['max_names']} "
             f"names, rebalanced {when}. Mechanism: {facts['mechanism']}",
             f"ITS AGENDA MECHANISM: {facts['agenda']}: {agenda['what']}. Published priors: {agenda['prior']}."]
    note = c["census_notes"].get(facts["agenda"])
    if note:
        lines.append(f"A NOTE ON ITS CELL ({CENSUS_LABEL}): {note}")
    for name in ("hypothesis", "comparison", "falsification"):
        if card.get(name):
            lines.append(f"CARD {name.upper()}: {card[name]}")
    lines.append(bar_text())
    if facts["held_out"]:
        lines.append(HIDDEN_NOTE)
    done = sorted(((int(k), v) for k, v in rec["versions"].items()), key=lambda kv: kv[0])
    if done:
        lines.append("YOUR VERSIONS ON TRAIN (the years you see):\n" + "\n".join(f"- {version_text(n, v)}" for n, v in done))
    refused = [r for r in (rec.get("refused") or []) if isinstance(r, Mapping)][-3:]
    if refused:
        lines.append("PROGRAMS REFUSED BEFORE THEY RAN:\n" + "\n".join(f"- {r.get('why')}" for r in refused))
    latest = researcher.store.latest_version(facts["id"])
    if latest is not None and latest.get("code"):
        lines.append(f"YOUR NEWEST PROGRAM (v{latest['n']}):\n```python\n{str(latest['code'])[:12000]}\n```")
    left = c["train_budget"] - len(done)
    lines.append(f"TRAIN BUDGET: {left} of {c['train_budget']} scored versions left"
                 + ("" if judged(record_of(fam)) else "; none judged by the bar yet, so a stop is not accepted")
                 + f". Write version {(latest['n'] + 1) if latest is not None else 1}: the whole file.")
    return "\n\n".join(lines)


def blocked(researcher: Any) -> str | None:
    """Why NO panel family may take a step now, or None: the lane is closed (the effective mode under "train"), or no
    panel run may start (`may_run`: a wall is near, the day's CPU is spent). E2's researcher asks it once a round
    (patch 7, `EquityResearcher.queue`): a panel family that cannot move takes no place in the round, so a closed
    or waiting panel lane never slows the ETF families' research."""
    try:
        if MODES.index(mode(researcher.settings, _root_of(researcher))) < MODES.index("train"):
            return "the panel lane is closed (elane.panel.mode)"
        return may_run(researcher.store, researcher.settings, researcher.clock())
    except Exception as exc:  # noqa: BLE001 - a lane that cannot be read does not move
        return f"the panel lane cannot be read ({type(exc).__name__})"


def _waits(store: Any, fid: str, why: str) -> dict[str, Any]:
    """A step that could not be taken now: the family goes to the back of the researcher's queue (its record's
    `last_at` moves; E2's queue works the least recently worked first), nothing else of it changes."""
    _update(store, fid, lambda r: None)
    return {"family": fid, "skipped": why}


def step(researcher: Any, fam: Mapping[str, Any]) -> dict[str, Any]:
    """One step of a panel family (E2's `EquityResearcher.step` forwards it): re-score a stale pass; review a bar
    pass; score its newest unscored version (`may_run` first: a run that could still be working at a wall, or past
    the day's CPU, waits); else, with budget left, ask for a program; else retire it."""
    from . import elane_train, elane_yield

    store, settings = researcher.store, researcher.settings
    fid = str(fam["id"])
    if MODES.index(mode(settings, _root_of(researcher))) < MODES.index("train"):
        return _waits(store, fid, "the panel lane is closed (elane.panel.mode)")
    c, ec = cfg(settings), elane_train.cfg(settings)
    rec = record_of(fam)
    if rec.get("status") == "passed":
        n = passed_version(fam)
        version = store.version(fid, n) if n is not None else None
        if version is None:
            return {"family": fid, "skipped": "its passing version cannot be read"}
        if pass_current(store, fam):
            return {"family": fid, "skipped": "its pass stands"}
        why = may_run(store, settings, researcher.clock())
        return _waits(store, fid, why) if why is not None else score(researcher, fam, version, rescore=True)
    pending = rec.get("review") if isinstance(rec.get("review"), Mapping) else None
    if pending is not None and pending.get("version") is not None:
        return review_step(researcher, fam, int(pending["version"]))
    latest = store.latest_version(fid)
    versions = versions_of(rec)
    if latest is not None and str(latest["n"]) not in versions:
        why = may_run(store, settings, researcher.clock())
        return _waits(store, fid, why) if why is not None else score(researcher, fam, latest)
    if len(versions) >= c["train_budget"] or int(rec.get("attempts") or 0) >= ec["train_max_attempts"]:
        return finish(researcher, fam, "its Train budget is spent with no version passing")
    if elane_yield.room(store, settings, researcher.clock()) <= 0:
        return {"family": fid, "skipped": "E2's model dollars for the day are spent (elane.e2.usd_day)"}
    return write(researcher, fam)


def write(researcher: Any, fam: Mapping[str, Any]) -> dict[str, Any]:
    """Ask the family's birth route for its next program; store it as a version once it passes the static checks
    (`check_code`; a refusal is recorded and counts as an attempt), then score it."""
    from . import elane_train, elane_yield

    store, settings = researcher.store, researcher.settings
    ec = elane_train.cfg(settings)
    fid = str(fam["id"])
    born_on = str(_spec(fam).get("e2_route") or "")
    first = elane_yield.Route.of(born_on) if born_on else None
    answer, route, errors = elane_yield.ask(
        researcher.router, store, settings, first=first, role=elane_yield.ROLE,
        system=RESEARCHER_SYSTEM + contract_text(), user=brief(researcher, fam),
        key=f"swarm:elane:xs:train:{fid}:{int(researcher.clock())}", max_output=ec["train_max_output_tokens"],
        effort=ec["train_effort"], purpose="research", now=researcher.clock(), family=fid)
    if answer is None:
        return {"family": fid, "error": "no route answered", "errors": errors[:3]}
    _update(store, fid, lambda r: r.update(attempts=int(r.get("attempts") or 0) + 1))
    code, note, stop = elane_train.program_of(answer)
    key = route.key if route else None

    def refuse(why: str) -> dict[str, Any]:
        def change(r: dict[str, Any]) -> None:
            r["refused"] = [*(r.get("refused") or []), {"at": store.now(), "why": why}][-5:]
        _update(store, fid, change)
        return {"family": fid, "refused": why, "route": key}

    if stop is not None:
        if not judged(record_of(store.family(fid) or fam)):
            return refuse((f"a stop is accepted only once a version was judged by the bar ({', '.join(JUDGED_XS)}); "
                           f"none was: {stop}")[:400])
        store.note(fid, f"The panel researcher stopped: {stop}")
        return finish(researcher, store.family(fid) or fam,
                      f"its researcher found the mechanism refuted on Train: {stop}")
    why = check_code(code, fam, settings) if code else "the answer held no program"
    if why is not None:
        return refuse(why)
    known = versions_of(record_of(store.family(fid) or fam))
    version = store.add_version(fid, str(code), {}, author=f"elane:{key or 'model'}",
                                note=note or "the panel researcher's version")
    if str(version["n"]) in known:
        return refuse(f"the same program as v{version['n']}, already scored")
    out = {"family": fid, "version": version["n"], "route": key}
    out["score"] = score(researcher, store.family(fid) or fam, version)
    return out


def review_question(fam: Mapping[str, Any], version: Mapping[str, Any], *, card: Mapping[str, Any] | None,
                    train: str, stage: str) -> str:
    """The panel review's user turn: the family's birth facts and card, the exact program, its PARAMS and its own
    Train verdict (Train facts only: never a Validation or look figure)."""
    spec = _spec(fam)
    lines = [f"{'AUDIT. ' if stage == 'audit' else ''}Family {fam.get('id')}, lane EQUITY, structure PANEL "
             f"({spec.get('panel') or PANELS[0]}): at most {spec.get('max_names')} names, rebalanced "
             f"{spec.get('rebalance')}. Mechanism: {' '.join(str(fam.get('mechanism') or '').split())[:600]}"]
    for name in ("hypothesis", "comparison", "falsification"):
        if (card or {}).get(name):
            lines.append(f"Card {name}: {' '.join(str(card[name]).split())[:600]}")
    if train:
        lines.append(f"Its Train verdict (panel Train years 2017-19 and 2022-24, the only data its author saw): {train}")
    lines.append(f"```python\n{str(version.get('code') or '')[:16000]}\n```\nPARAMS overrides: "
                 f"{json.dumps(version.get('params') or {}, sort_keys=True)}")
    return "\n\n".join(lines)


def review_step(researcher: Any, fam: Mapping[str, Any], n: int) -> dict[str, Any]:
    """THE REVIEW of a panel bar pass, under the panel rubric (`REVIEW_SYSTEM`: `REVIEW_XS`, A22 (3)): the review and
    the audit on two different models (E2's review machinery and settings). Both pass: the version is the family's
    pass (its lineage's one Validation try) and the record E1's `reviewed` reads is written, naming this rubric
    (`REVIEW_OBJECTIVE`, `rubric_sha`). A failure (or `review_max_unclear` unclear reads of one stage) is a Train
    failure of the version ("REVIEW"). A question no route answered counts nothing and is asked again next round."""
    from . import cards, elane_review, elane_yield
    from .gate import run_sha

    store, settings = researcher.store, researcher.settings
    fid = str(fam["id"])
    rec = record_of(fam)
    pending = dict(rec.get("review") or {}) if isinstance(rec.get("review"), Mapping) else {"version": n}
    version = store.version(fid, n)
    if version is None or not version.get("code"):
        return {"family": fid, "version": n, "error": "the version cannot be read"}
    code = str(version["code"])
    if elane_yield.room(store, settings, researcher.clock()) <= 0:
        return {"family": fid, "version": n, "skipped": "E2's model dollars for the day are spent (elane.e2.usd_day)"}
    rc = elane_review.cfg(settings)
    served = elane_yield.served([elane_yield.Route.of(k) for k in rc["review_routes"]], researcher.router)
    try:
        card = (cards.card_of(store, fid) or {}).get("card") or {}
    except Exception:  # noqa: BLE001
        card = {}
    train = version_text(n, versions_of(rec).get(str(n)) or {})
    unclear = dict(pending.get("unclear") or {})
    for stage in ("review", "audit"):
        done = pending.get(stage)
        if isinstance(done, Mapping) and done.get("verdict") == "pass":
            continue
        reader = (pending.get("review") or {}).get("route") if stage == "audit" else None
        if stage == "audit":
            taken = elane_review.model_of(str(reader or ""))
            candidates = [r for r in served if elane_review.model_of(r.key) != taken]
        else:
            candidates = list(served)
        if not candidates:
            return {"family": fid, "version": n, "error": f"no {stage} route on a second model (elane.e2.review_routes)"}
        tries = int(unclear.get(stage) or 0)
        answer, route, errors = elane_yield.ask(
            researcher.router, store, settings, first=None, role=elane_yield.ROLE,
            system=REVIEW_SYSTEM + contract_text(),
            user=review_question(fam, version, card=card, train=train, stage=stage),
            key=f"swarm:elane:xs:{stage}:{fid}:{n}:{tries}", max_output=rc["review_max_output_tokens"],
            effort=rc["review_effort"], purpose="review", now=researcher.clock(), family=fid, candidates=candidates,
            book_as=lambda r: f"review:{r.key}")
        if answer is None or route is None:
            _update(store, fid, lambda r: r.update(review={**pending, "unclear": unclear}))
            return {"family": fid, "version": n, "error": f"no {stage} route answered", "errors": errors[:3]}
        read = {**elane_review.grounded(answer, code), "route": route.key}
        if read["verdict"] == "fail":
            return review_failed(researcher, fam, n, stage, read["reasons"] or [f"the {stage} failed it"], read=read)
        if read["verdict"] != "pass":
            unclear[stage] = tries + 1
            if unclear[stage] >= rc["review_max_unclear"]:
                return review_failed(researcher, fam, n, stage,
                                     [f"the {stage} stayed unclear after {unclear[stage]} reads"] + read["reasons"][:2],
                                     read=read)
            _update(store, fid, lambda r: r.update(review={**pending, "unclear": unclear}))
            return {"family": fid, "version": n, stage: "unclear", "reads": unclear[stage]}
        if stage == "audit" and elane_review.model_of(route.key) == elane_review.model_of(str(reader or "")):
            return {"family": fid, "version": n, "error": "the audit was answered by the reviewer's model"}
        pending[stage] = {k: read.get(k) for k in ("verdict", "route", "model", "reasons")}
        _update(store, fid, lambda r: r.update(review={**pending, "unclear": unclear}))
    at = store.now()
    held = {**elane_review.record(run_sha(version), pending["review"], pending["audit"], at=at, version=n),
            "objective": REVIEW_OBJECTIVE, "source": "elane_xs", "rubric": rubric_sha()}
    score_ = (versions_of(rec).get(str(n)) or {}).get("score")

    def put(r: dict[str, Any]) -> None:
        r.pop("review", None)
        if r.get("passed_version") is None:
            r["passed_version"], r["status"] = n, "passed"
            r["passed_review"] = held
    rec = _update(store, fid, put)
    if rec.get("passed_version") == n:
        store.set_state(fid, **{elane_review.STATE_REVIEW: held})
        store.update_family(fid, best_version=n, best_train=score_)
        store.note(fid, f"v{n} passed {OBJECTIVE} on Train and the review: it is the lineage's one Validation try.")
    return {"family": fid, "version": n, "passed": True, "review": "pass"}


def review_failed(researcher: Any, fam: Mapping[str, Any], n: int, stage: str, reasons: Sequence[str], *,
                  read: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """The review refused version `n`: a Train failure of it ("REVIEW", its reasons in the next brief); the family's
    research goes on with its budget, or ends (`finish`) once the budget is spent. No Validation try is spent."""
    store = researcher.store
    fid = str(fam["id"])
    said = [" ".join(str(x).split())[:400] for x in reasons][:4]

    def put(r: dict[str, Any]) -> None:
        r.pop("review", None)
        v = dict((r.get("versions") or {}).get(str(n)) or {})
        v.update(passed=False, verdict="fail", bar_passed=True, fails=["REVIEW"],
                 review={"stage": stage, "reasons": said, "route": (read or {}).get("route"),
                         "model": (read or {}).get("model")})
        r["versions"] = {**(r.get("versions") or {}), str(n): v}
    rec = _update(store, fid, put)
    store.note(fid, f"v{n} passed the panel Train bar but the {stage} refused it: {'; '.join(said)[:600]}")
    out: dict[str, Any] = {"family": fid, "version": n, "passed": False, "fails": ["REVIEW"], "stage": stage}
    if len(versions_of(rec)) >= cfg(researcher.settings)["train_budget"]:
        out["retired"] = finish(researcher, store.family(fid) or fam, "its Train budget is spent with no version passing")
    return out


def finish(researcher: Any, fam: Mapping[str, Any], why: str) -> dict[str, Any]:
    """The research ends with no pass: REFUTED on Train when the bar judged a version on a `JUDGED_XS` rule, else
    STALLED (no graveyard row, no cell count: nothing is said of the mechanism)."""
    store = researcher.store
    fid = str(fam["id"])
    rec = record_of(store.family(fid) or fam)
    versions = versions_of(rec)
    codes = sorted({f for v in versions.values() for f in (v.get("fails") or [])})
    refuted = judged(rec) > 0
    at = store.now()
    name = "refuted" if refuted else "stalled"

    def put(r: dict[str, Any]) -> None:
        r["status"] = name
        r.pop("review", None)
        r[name] = {"at": at, "codes": codes, "versions": len(versions), "why": why[:300]}
    _update(store, fid, put)
    if refuted:
        facts = train_facts(store.family(fid) or fam)
        words = "; ".join(f"({c}) {FAILS_XS.get(c) or PROGRAM_FAILS.get(c)}" for c in codes
                          if c in FAILS_XS or c in PROGRAM_FAILS) or "no version was scored"
        what = PANEL_AGENDA.get(facts["agenda"], PANEL_AGENDA[OTHER])["what"]
        store.bury(fid, f"{REFUTED_TAG} on Train ({OBJECTIVE}, panel {facts['panel']}, {what}): {why}. {len(versions)} "
                        f"versions scored; their fails: {words}.",
                   {"objective": OBJECTIVE, "codes": codes, "versions": len(versions)})
        store.retire(fid, f"{REFUTED_TAG} on Train ({OBJECTIVE}): {why}"[:2000],
                     public_reason="refuted on Train by the panel lane's bar")
    else:
        store.retire(fid, f"{STALLED_TAG} on Train ({OBJECTIVE}): no version could be judged by the bar; {why}"[:2000],
                     public_reason="stalled on Train: no version of its program could be judged by the panel lane's bar")
    store.event("swarm.elane", fid, {"pass": name, "codes": codes, "versions": len(versions), "structure": STRUCTURE})
    return {"family": fid, name: codes}


def _tried(store: Any, fid: str, n: int) -> bool:
    """Whether version `n` has had its Validation try (E2's `elane_train.tried`: outcome-free)."""
    from . import elane_train

    return bool(elane_train.tried(store, fid, n))


def pass_current(store: Any, fam: Mapping[str, Any] | None) -> bool:
    """Whether a panel family's pass stands: it was judged under the xs identity in force (or no identity can be
    read), and not under provisional costs that are no longer provisional; or its version has had its Validation try
    (the gate owns it from there)."""
    n = passed_version(fam)
    if n is None:
        return False
    fid = str((fam or {}).get("id"))
    if _tried(store, fid, n):
        return True
    verdict = versions_of(record_of(fam)).get(str(n)) or {}
    if FLAG_COSTS in (verdict.get("flags") or []):
        root = getattr(store, "root", None)
        share = _num((_manifest(root) or {}).get("hs_share"))
        if share is not None and share >= cfg(_settings_of(root, None))["spreads_min_share"]:
            return False  # the half-spreads are sampled now: the pass is scored again at what live pays
    now = identity()
    return now is None or verdict.get("identity") == now


def may_validate(store: Any, fam: Mapping[str, Any] | None, n: Any) -> bool:
    """THE GUARD E1'S TOURNAMENT APPLIES for a panel family (E2's `elane_train.may_validate` forwards it): only its
    pass (the first version that passed the bar AND the review under the panel rubric), while the effective mode is
    at least "gate" (a pinned receipt, sampled spreads: a pass under provisional costs takes no try), the review E1's
    look reads is in its state for that exact program, and the pass is current (`pass_current`)."""
    fam = fam or {}
    p = passed_version(fam)
    if n is None or p is None or fam.get("retired_at"):
        return False
    try:
        if int(n) != p:
            return False
        root = getattr(store, "root", None)
        if MODES.index(mode(_settings_of(root, None), root)) < MODES.index("gate"):
            return False
        version = store.version(str(fam["id"]), p)
        if version is None or not version.get("code"):
            return False
        from .gate import run_sha

        return _reviewed(_state(fam), run_sha(version)) and pass_current(store, fam)
    except Exception:  # noqa: BLE001 - a guard that cannot be read admits nothing
        return False


def _reviewed(state: Mapping[str, Any], sha: str) -> bool:
    """A passed review AND a passed audit of program `sha` UNDER THE PANEL RUBRIC in the family's state (E1's
    `reviewed` shape, naming `REVIEW_OBJECTIVE`: a rubric that changes what is refused takes a new objective; the
    record's `rubric` is its provenance)."""
    review = state.get("review") if isinstance(state.get("review"), Mapping) else {}
    audit = review.get("audit") if isinstance(review.get("audit"), Mapping) else {}
    return (review.get("sha") == sha and review.get("verdict") == "pass" and audit.get("verdict") == "pass"
            and review.get("objective") == REVIEW_OBJECTIVE)


# ------------------------------------------------------------------------------------- Validation, the look, lineage
#: The screen every panel Validation, look and event names.
SCREEN_NAME = "XS1"


def _now(owner: Any) -> float:
    clock = getattr(owner, "clock", None)
    try:
        return float(clock()) if callable(clock) else time.time()
    except Exception:  # noqa: BLE001
        return time.time()


def _status(run: Any) -> str:
    result = getattr(run, "result", None)
    return str((result if isinstance(result, Mapping) else {}).get("status") or "unknown")


def _timed(store: Any, owner: Any, call: Callable[[], Any]) -> Any:
    """`call()`, its seconds booked to the day's panel CPU whatever it does. A RUN FOUND RUNNING AT A WALL (E4-SPEC
    17, critical: a bug in `quiet`, which every run asks before it starts): the wall clock from its start to its end
    is held to `league.xs.config.quiet` again, and a run that met a wall is one `swarm.status` alert a UTC day."""
    began, started = time.monotonic(), time.time()
    try:
        return call()
    finally:
        try:
            seconds = time.monotonic() - began
            book_cpu(store, seconds, _now(owner))
            _wall_alert(store, started, seconds)
        except Exception:  # noqa: BLE001 - the books never fail a run
            pass


def _wall_alert(store: Any, started: float, seconds: float) -> None:
    """One critical `swarm.status` alert a UTC day when [started, started + seconds] (wall clock) met a wall."""
    from ..xs import config as xconfig

    met = xconfig.quiet(float(started), max(0.0, float(seconds)))
    if met is None:
        return
    day = _utc_day(started)
    with store.atomic():
        held = store.get(ALERTS_KEY)
        held = dict(held) if isinstance(held, Mapping) else {}
        if held.get("wall") == day:
            return
        store.put(ALERTS_KEY, {**held, "wall": day})
    store.event("swarm.status", None, {
        "action": "elane_xs_wall", "alert": True, "level": "critical",
        "text": f"a panel run was found RUNNING at a wall of the session ({seconds:.0f} s from its start): {met}"[:400]})


def _by_session(series: Any, name: str) -> dict[int, float]:
    """A kept Train series ({"days": [ordinal], name: [value]}) as {session: value}."""
    series = series if isinstance(series, Mapping) else {}
    days, values = series.get("days") or [], series.get(name) or []
    return {int(d): float(v) for d, v in zip(days, values)} if len(days) == len(values) else {}


def _train_series(S: Any, runs: Sequence[Any], n: int) -> tuple[dict[str, Any], dict[str, Any], list[Any]]:
    """THE TWO TRAIN SERIES the lineage rule keeps (duty 1), from the two whole Train segments' runs at k 1.0: (the
    residual {"version", "days", "x"}, the universe excess {"version", "days", "u"}, the residual `Series` a segment:
    the floor's inputs). ValueError when a series cannot be read."""
    x: dict[str, Any] = {"version": int(n), "days": [], "x": []}
    u: dict[str, Any] = {"version": int(n), "days": [], "u": []}
    segments = []
    for run in runs:
        result = getattr(run, "result", None) or {}
        sx, su = S.series(result, "x"), S.series(result, "u")
        segments.append(sx)
        for held, series, name in ((x, sx, "x"), (u, su, "u")):
            days, values = [int(d) for d in series.days], [float(v) for v in series.r]
            if len(days) != len(values) or not all(math.isfinite(v) for v in values):
                raise ValueError(f"a Train segment's {name} series cannot be read")
            held["days"] += days
            held[name] += [round(v, 10) for v in values]
    if not x["days"] or x["days"] != u["days"]:
        raise ValueError("the two Train series do not cover the same sessions")
    return x, u, segments


class LineageUnread(RuntimeError):
    """THE LINEAGE cannot be judged: `family` was looked at, has its look in flight, or was refused at the pre-check,
    and keeps no Train series for the correlation test. The asking program waits; it never passes the rule unjudged."""

    def __init__(self, family: str):
        super().__init__(f"{family} keeps no Train series of its pre-check")
        self.family = str(family)


def same_lineage(store: Any, fam: Mapping[str, Any], *, template: str, train_x: Mapping[str, Sequence],
                 train_u: Mapping[str, Sequence]) -> str | None:
    """THE LINEAGE (duty 2): the panel family already looked at, in flight, or refused at the pre-check that `fam`'s
    program is the same lineage as, or None. FAILS CLOSED as E1's (`LineageUnread`): a family that reached the
    pre-check and keeps no Train series is never skipped (a retired family's marker of a look that never landed is:
    nothing was looked at). The same template, or `league.xs.screen.same_lineage` on the two residual series OR the
    two universe-excess series (0.7 or more on the common Train sessions)."""
    from ..xs import screen as S
    from . import elane

    mine_x, mine_u = _by_session(train_x, "x"), _by_session(train_u, "u")
    for other in panel_families(store):
        if str(other["id"]) == str(fam["id"]):
            continue
        state = _state(other)
        looked = isinstance(state.get(LOOK_KEY), Mapping)
        marker = state.get("look_inflight")
        inflight = bool(isinstance(marker, Mapping) and marker.get("sha"))
        pre = state.get(PRECHECK_KEY) if isinstance(state.get(PRECHECK_KEY), Mapping) else {}
        refused = pre.get("reached") is True and pre.get("passed") is False
        if not (looked or inflight or refused):
            continue
        if state.get(elane.TEMPLATE_KEY) == template:
            return str(other["id"])
        their_x, their_u = _by_session(state.get(TRAIN_X_KEY), "x"), _by_session(state.get(TRAIN_U_KEY), "u")
        if not their_x or not their_u:
            if looked or refused or not other.get("retired_at"):
                raise LineageUnread(str(other["id"]))
            continue
        if bool(S.same_lineage(mine_x, mine_u, their_x, their_u, same_template=False)):
            return str(other["id"])
    return None


def _restore_series(owner: Any, fid: str) -> bool:
    """THE LINEAGE RECORD written again: a pre-checked family's missing Train series, from the Train-era runs of the
    version its pre-check (or its look) names (`Isolated.segments`: Train-era data only, nothing sealed, no try and no
    look). False when it cannot be."""
    store = owner.store
    other = store.family(str(fid)) or {}
    state = _state(other)
    named = None
    for key in (LOOK_KEY, PRECHECK_KEY):
        held = state.get(key)
        if isinstance(held, Mapping) and isinstance(held.get("version"), int):
            named = int(held["version"])
            break
    version = store.version(str(fid), named) if named is not None else None
    if not version or not version.get("code"):
        return False
    try:
        from ..xs import screen as S

        runs = _timed(store, owner, lambda: _runner_of(owner).segments(version["code"], dict(version.get("params") or {}),
                                                                      name=str(fid)))
        if any(_status(run) != "ok" for run in runs):
            raise ValueError("a Train-era run did not end ok")
        x, u, _ = _train_series(S, runs, named)
    except Exception as exc:  # noqa: BLE001 - it stays unread, and the program that asked waits
        store.event("swarm.gate", str(fid), {"action": "panel_lineage_unread", "version": named,
                                             "error": type(exc).__name__})
        return False
    store.set_state(str(fid), **{TRAIN_X_KEY: x, TRAIN_U_KEY: u})
    store.event("swarm.gate", str(fid), {"action": "panel_lineage_restored", "version": named,
                                         "sessions": len(x["days"])})
    return True


def _ask_lineage(owner: Any, fam: Mapping[str, Any], template: str, x: Mapping[str, Any],
                 u: Mapping[str, Any]) -> tuple[str | None, str | None]:
    """(the family `fam`'s program is the same lineage as, None), (None, None), or (None, why the rule cannot be
    judged yet): `same_lineage`, a family that keeps no series restored once (`_restore_series`)."""
    restored: set[str] = set()
    while True:
        try:
            return same_lineage(owner.store, fam, template=template, train_x=x, train_u=u), None
        except LineageUnread as exc:
            if exc.family in restored or not _restore_series(owner, exc.family):
                return None, (f"the lineage cannot be judged: {exc.family} reached its pre-check and keeps no Train "
                              "series to compare with")
            restored.add(exc.family)


def validate(tournament: Any, fam: Mapping[str, Any], version: Mapping[str, Any]) -> dict[str, Any]:
    """A panel version's ONE Validation try (mode at least "gate"; E1's rations): the two Train segments' series kept
    (duty 1), the lineage asked (duty 2), the 2025 run at k 1.0 and 1.5, the line `league.xs.screen.precheck` on the
    k 1.0 residual, `PRECHECK_KEY` written, and the k 1.0 run's `summary.sd_date_return` under E1's `elane.SIGMA_KEY`
    (EDM1's sigma for a panel program: a sd per close DATE). A program the lineage rule refuses takes no try (its
    family retires for it: `lineage_spent`); no Validation-only retry is ever registered (`retry_sha` None). Returns
    the tournament's verdict dict."""
    from . import elane

    store, settings = tournament.store, tournament.settings
    fid, n = str(fam["id"]), int(version["n"])
    out: dict[str, Any] = {"version": n, "passed": False, "entered": False, "screen": SCREEN_NAME, "lane": LANE,
                           "structure": STRUCTURE}
    if not is_panel(fam):
        return {**out, "refused": "not a panel family"}
    if MODES.index(mode(settings, store.root)) < MODES.index("gate"):
        return {**out, "refused": "the panel lane's gate is closed (elane.panel.mode, the pinned receipt, the spreads)"}
    if not elane.try_open(store, fam, n, settings):
        return {**out, "refused": elane.SPENT_TRY}
    if not version.get("code"):
        return {**out, "refused": "the version's program cannot be read"}
    state = _state(fam)
    early = state.get(PRECHECK_KEY) if isinstance(state.get(PRECHECK_KEY), Mapping) else {}
    if early.get("version") == n and early.get("reached") is False:
        return {**out, "refused": EARLY_CAUSES.get(str(early.get("why")), SAME_LINEAGE_XS)}
    why = may_run(store, settings, _now(tournament))
    if why is not None:
        return {**out, "waits": why}
    from ..xs import screen as S

    run_through = _runner_of(tournament)
    code, params = version["code"], dict(version.get("params") or {})
    template = elane.lineage_key(LANE, str(version.get("sha") or ""))

    def trouble(stage: str, exc: BaseException | str) -> dict[str, Any]:
        name = exc if isinstance(exc, str) else type(exc).__name__
        store.event("swarm.status", fid, {"action": "elane_validation_error", "version": n, "lane": LANE,
                                         "structure": STRUCTURE, "stage": stage, "error": name})
        return {**out, "error": name}

    # DUTY 1: both Train series, from the two whole segments at k 1.0, BEFORE the Validation run.
    try:
        segments = _timed(store, tournament, lambda: run_through.segments(code, params, name=fid))
    except Exception as exc:  # noqa: BLE001 - no result is no try (nothing is recorded)
        return trouble("train", exc)
    ended = [_status(run) for run in segments]
    if "disqualified" in ended:
        # The program's own errors ended a whole Train segment: no series can be kept, so the lineage rule cannot be
        # asked of it now or of any later program against it. It takes no try.
        store.refuse(fid, n, "train run", "a whole Train segment's run was ended by the program's own errors")
        store.set_state(fid, **{PRECHECK_KEY: {"version": n, "at": store.now(), "reached": False, "why": "train run"}})
        store.event("swarm.status", fid, {"action": "elane_validation_refused", "version": n, "lane": LANE,
                                         "structure": STRUCTURE, "screen": SCREEN_NAME, "stage": "train run"})
        return {**out, "refused": TRAIN_ENDED}
    if any(status != "ok" for status in ended) or not segments:
        return trouble("train", "the Train segments' runs ended " + ", ".join(sorted(set(ended))))
    try:
        train_x, train_u, _ = _train_series(S, segments, n)
    except Exception as exc:  # noqa: BLE001
        return trouble("series", exc)
    store.set_state(fid, **{TRAIN_X_KEY: train_x, TRAIN_U_KEY: train_u, elane.TEMPLATE_KEY: template})
    # DUTY 2: the lineage, before the try.
    try:
        twin, waits = _ask_lineage(tournament, fam, template, train_x, train_u)
    except Exception as exc:  # noqa: BLE001 - a lineage that cannot be read spends no try
        return trouble("lineage", exc)
    if waits is not None:
        return {**out, "waits": waits}
    if twin is not None:
        store.refuse(fid, n, "same lineage", f"the same lineage as {twin} (XS1: the template, or 0.7 in x or in u)")
        store.set_state(fid, **{PRECHECK_KEY: {"version": n, "at": store.now(), "reached": False,
                                               "why": "same lineage", "twin": twin}})
        store.event("swarm.status", fid, {"action": "elane_validation_refused", "version": n, "lane": LANE,
                                         "structure": STRUCTURE, "screen": SCREEN_NAME, "stage": "same lineage",
                                         "_twin": twin})
        return {**out, "refused": SAME_LINEAGE_XS}
    # THE TRY: the 2025 run at k 1.0 and 1.5.
    why = may_run(store, settings, _now(tournament))
    if why is not None:
        return {**out, "waits": why}
    try:
        base = _timed(store, tournament, lambda: run_through.validation(code, params, name=fid, k=K_BASE))
        stressed = _timed(store, tournament, lambda: run_through.validation(code, params, name=fid, k=K_STRESS))
    except Exception as exc:  # noqa: BLE001 - no result is no try (nothing is recorded)
        return trouble("validation", exc)
    result = dict(base.result or {})
    status = str(result.get("status") or "unknown")
    summary = result.get("summary") if isinstance(result.get("summary"), Mapping) else {}
    years = float(_num(summary.get("days")) or 0.0) / 252.0
    try:
        from ..xs import results as R

        shown = dict(R.view(result, "validation"))
    except Exception:  # noqa: BLE001 - the row then keeps the status alone
        shown = {"status": status}
    row = store.add_run(fid, n, {**shown, "run_id": result.get("run_id"), "status": status,
                                 "trials": int(result.get("trials") or 1)},
                        window="validation", stress=K_BASE, purpose="validation", program_years=years)
    twin_run = dict(stressed.result or {})
    store.add_run(fid, n, {"run_id": f"{row['run_id']}-s15", "status": twin_run.get("status") or "unknown",
                           "trials": int(twin_run.get("trials") or 1)},
                  window="validation", stress=K_STRESS, purpose="validation", program_years=years)
    if status in elane.NOT_A_TRY:
        return trouble("validation", status)
    if status != "ok":
        pre: dict[str, Any] = {"passed": False, "checks": {"status": False}}
    else:
        try:
            pre = dict(S.precheck(S.series(result, "x")))
        except Exception as exc:  # noqa: BLE001 - a pre-check that cannot be read admits nothing
            pre = {"passed": False, "checks": {"readable": False}, "error": type(exc).__name__}
    entered = bool(pre.get("passed")) and status == "ok"
    tries = elane.lineage_tries(store, fid)
    k = int(elane.cfg(settings)["val_tries"])
    first = any(t["family"] == fid and t["version"] == n for t in tries[:k])
    sd = _num(summary.get("sd_date_return"))
    sigma = dict(state.get(elane.SIGMA_KEY) or {}) if isinstance(state.get(elane.SIGMA_KEY), Mapping) else {}
    if sd is not None and sd > 0:
        sigma[str(n)] = round(sd, 8)  # EDM1's sigma for a panel program: one observation a close DATE
    sha = elane._run_sha(version)
    looked = sha is not None and (store.looked(sha) or state.get("gated_sha") == sha)
    checks = {str(key): bool(value) for key, value in (pre.get("checks") or {}).items()}
    verdicts = dict(state.get(elane.VERDICTS_KEY) or {}) if isinstance(state.get(elane.VERDICTS_KEY), Mapping) else {}
    verdicts[str(n)] = {"entered": entered, "at": store.now(), "stale": False}
    with store.atomic():
        current = store.family(fid)
        if current is None or current.get("retired_at"):
            return {**out, "refused": "retired"}
        store.update_family(fid, validated_version=n)
        store.bump(fid, validations=1)
        store.set_state(fid, validation_version=n, gate_ready=entered and not looked,
                        **{elane.VALIDATION_KEY: {"version": n, "passed": entered, "precheck": checks,
                                                  "screen": SCREEN_NAME, "status": status, "at": store.now(),
                                                  "result_sha": result.get("result_sha"), "stale": False},
                           elane.SIGMA_KEY: sigma, elane.VERDICTS_KEY: verdicts,
                           elane.TRY_KEY: {"version": n, "at": store.now(), "first": first,
                                           "precheck": bool(pre.get("passed")), "entered": entered, "retry_sha": None},
                           PRECHECK_KEY: {"version": n, "at": store.now(), "reached": True,
                                          "passed": bool(pre.get("passed")) and status == "ok"}})
    store.event("swarm.status", fid, {"action": "elane_validation", "version": n, "lane": LANE, "label": "EQUITY",
                                     "structure": STRUCTURE, "screen": SCREEN_NAME, "entered": entered, "first": first,
                                     "checks": checks})
    return {**out, "passed": entered, "entered": entered, "first": first}


def _refuse(gate: Any, fid: str, n: int, sha: str, stage: str, why: str) -> None:
    """A refusal before the look (no look spent): the refusal row, `gated_sha` with `gate_ready` cleared, the outcome,
    and one private `swarm.gate` event (E1's `_refuse`, for a panel family)."""
    store = gate.store
    store.refuse(fid, n, stage, why)
    store.compare_and_set_state(fid, {"validation_version": n}, gated_sha=sha, gate_ready=False)
    store.set_state(fid, gate_outcome={"sha": sha, "result": "refused", "at": gate.clock()}, gate=f"refused ({why})")
    store.event("swarm.gate", fid, {"action": "refused", "version": n, "stage": stage, "lane": LANE,
                                    "structure": STRUCTURE, "screen": SCREEN_NAME, "why": why})


def _wait(gate: Any, fid: str, n: int, sha: str, why: str) -> None:
    """The look waits (no look spent, `gate_ready` stays): its outcome "waiting" and one private event, written once
    for a reason (a family held by its cell's cap or by the probe is asked every round)."""
    store = gate.store
    said = f"waiting ({why})"
    if _state(store.family(fid) or {}).get("gate") == said:
        return
    store.set_state(fid, gate_outcome={"sha": sha, "result": "waiting", "at": gate.clock()}, gate=said)
    store.event("swarm.gate", fid, {"action": "equity_look_waits", "version": n, "screen": SCREEN_NAME,
                                    "structure": STRUCTURE, "why": why})


def _holdout_gap(root: str | Path) -> str | None:
    """Why the panel store cannot give the sealed look its whole calibrated holdout yet, or None: its last session
    (the manifest's, never a bar) reaches `league.equity.config.LOOK_CAP` (A12) and its coverage verdict stands."""
    from ..equity import config as econfig

    manifest = _manifest(root)
    if manifest is None or manifest.get("verdict") not in ("ok", "low_coverage"):
        return "the panel store has no manifest the look can stand on"
    through = _day(manifest.get("fetched_through"))
    if through is None or through < econfig.LOOK_CAP:
        return (f"the panel store ends {through.isoformat() if through else 'nowhere'}: the sealed look reads the "
                f"calibrated holdout through {econfig.LOOK_CAP.isoformat()} (A12), so it waits for the data job")
    return None


def _membership_gap(root: str | Path, settings: Mapping[str, Any] | None) -> str | None:
    """Why the index membership is too stale for a look, or None (`membership_max_stale_days`)."""
    from ..xs.store import Universe

    manifest = _manifest(root) or {}
    through = _day(manifest.get("fetched_through"))
    if through is None:
        return "the panel manifest names no last session"
    universe = Universe(Path(root) / STORE_DIR)
    stale = int(universe.stale_days(through))
    if stale > int(cfg(settings)["membership_max_stale_days"]):
        return (f"the index membership is {stale} days behind the panel store (elane.panel.membership_max_stale_days): "
                "no look until the universe job has caught up")
    return None


def _refused_cause(store: Any, fid: str, n: int) -> str:
    """The public cause of a panel version the gate refused before its look: rules only, no figure."""
    from . import elane

    try:
        rows = [r for r in store.refusals(str(fid)) if r.get("version") == int(n)]
    except Exception:  # noqa: BLE001
        rows = []
    stage = str(rows[-1].get("stage") or "") if rows else ""
    return {"same lineage": SAME_LINEAGE_XS, "screen floor": elane.FLOOR_INELIGIBLE,
            "train run": TRAIN_ENDED}.get(stage, elane.REFUSED_BEFORE_LOOK)


def lineage_spent(store: Any, fam: Mapping[str, Any], settings: Mapping[str, Any] | None) -> str | None:
    """Why a panel family's lineage can take no look, or None (E1's `elane.lineage_spent` forwards a panel family):
    its one look used and FAILED, or used elsewhere in its lineage (`elane.SPENT_LOOK`); refused before its Validation
    try by the lineage rule or for a Train run its own errors ended (`EARLY_CAUSES`); its one try failed
    (`elane.SPENT_TRY`); its version refused at the gate before any look. A PASSER THE STYLE RULE HOLDS BACK IS NOT
    SPENT (A22 (1)): it is recorded and shadowed, alive in the Gym band, never seated by the look. None on any error
    (a rule that cannot be read retires nothing)."""
    from . import elane

    try:
        if not is_panel(fam):
            return None
        state = _state(fam)
        fid = str(fam["id"])
        looked = state.get(LOOK_KEY)
        if isinstance(looked, Mapping):
            verdict = looked.get("verdict") if isinstance(looked.get("verdict"), Mapping) else {}
            held_back = verdict.get("passed") is True and looked.get("seat") in (SEAT_STYLE, SEAT_UNSTATED)
            return None if held_back else elane.SPENT_LOOK
        early = state.get(PRECHECK_KEY) if isinstance(state.get(PRECHECK_KEY), Mapping) else {}
        if early.get("reached") is False:
            return EARLY_CAUSES.get(str(early.get("why")), SAME_LINEAGE_XS)
        c = elane.cfg(settings)
        if store.lineage_looks(fid, include_inflight=True) >= c["looks_per_lineage"]:
            return elane.SPENT_LOOK
        tries = elane.lineage_tries(store, fid)
        if len(tries) < c["val_tries"]:
            return None
        mine = [t for t in tries if t["family"] == fid]
        if not mine:
            return elane.SPENT_TRY
        last = mine[-1]
        held = state.get(elane.TRY_KEY) if isinstance(state.get(elane.TRY_KEY), Mapping) else {}
        if held.get("version") != last["version"]:
            return None  # its own try has no verdict yet: it is owed one, never retired unjudged
        if held.get("entered") is True:
            sha = elane._run_sha(store.version(fid, last["version"]))
            if sha is not None and not store.looked(sha) and state.get("gated_sha") != sha:
                return None  # it entered the gate and waits for its one look (the cell's cap, the probe, the store)
            if sha is not None and not store.looked(sha):
                return _refused_cause(store, fid, last["version"])
        return elane.SPENT_TRY
    except Exception:  # noqa: BLE001
        return None


def look(gate: Any, fam: Mapping[str, Any], version: Mapping[str, Any], sha: str) -> bool | None:
    """A panel family's ONE sealed look under XS1 (mode at least "gate"): the pinned receipt (none: wait, nothing
    spent); one look a lineage; the cell's looks (`look_room`, A22 (2): wait); E2's review under `REVIEW_XS` and the
    contamination probe (`probed`, A22 (3): wait); the panel store holds the whole calibrated holdout; the floor (kept
    a version while it fits the receipt; an ineligible floor spends no look); E1's gate capability; the look's run
    with the receipt's draws under `league.xs.placebo.look_seed`; `league.xs.screen.verdict`; the look event records
    the screen "XS1", the receipt sha, c_used, p_plac, the probe's reading and the sentence beside (duty 3). THE RUN'S
    STATUS FIRST, by E1's rules word for word (a run sent whole and never answered is owed once, then spent and
    failed). True passed, False failed, None not run. A PASS SEATS ONLY A PROGRAM THAT IS NOT STYLE-OPEN (A22 (1)):
    `league.xs.style.seat_refusal(style_of(fam))` None: a Candidate, proof {"engine": XS_ENGINE_VERSION, "xs_sha256",
    "run_sha"}, `seat` `SEAT_CANDIDATE`; else the pass is recorded with `seat` `SEAT_STYLE` and its reason, the
    family takes no band and no proof, and the forward record shadows it. THE SEALED RUN IS ONE RUN (Validation's
    first session through the holdout): a verdict that fails at its own pre-check was still made on the sealed run, so
    the look is spent and failed."""
    from . import elane

    store, settings = gate.store, gate.settings
    fid, n = str(fam["id"]), int(version["n"])
    root = store.root
    if not is_panel(fam) or MODES.index(mode(settings, root)) < MODES.index("gate"):
        return None
    pinned, why = receipt()
    if pinned is None:
        _wait(gate, fid, n, sha, why or "XS1 refused: no pinned receipt")  # NO RECEIPT, NO LOOK
        return None
    c = elane.cfg(settings)
    if store.looked(sha) or store.lineage_looks(fid, include_inflight=True) >= c["looks_per_lineage"]:
        _refuse(gate, fid, n, sha, "rations", "the equity lineage's one sealed look is spent")
        return None
    state = _state(fam)
    held = state.get(elane.TRY_KEY) if isinstance(state.get(elane.TRY_KEY), Mapping) else {}
    if held.get("version") != n or held.get("entered") is not True or state.get("validation_version") != n:
        return None  # not this version's entry: the tournament owes its Validation first
    cell = family_cell(fam)
    full = look_room(store, cell)
    if full is not None:
        _wait(gate, fid, n, sha, full)  # A22 (2): held back, not spent
        return None
    if not _reviewed(state, sha):
        _wait(gate, fid, n, sha, "a panel look needs the review and the audit of this exact program under the panel "
                                 "rubric (the captain's A22)")
        return None
    unprobed = probed(root, fam)
    if unprobed is not None:
        _wait(gate, fid, n, sha, unprobed)  # A22 (3): the probe before the look
        return None
    from ..equity.runner import RunFailed, RunLost
    from ..equity.store import mint_equity_gate_capability
    from ..xs import XS_ENGINE_VERSION
    from ..xs import placebo as P
    from ..xs import screen as S
    from ..xs import style as Y
    from ..xs.identity import xs_fingerprint

    try:
        gap = _holdout_gap(root) or _membership_gap(root, settings)
    except Exception as exc:  # noqa: BLE001 - a store that cannot be read gives no look (nothing spent)
        store.event("swarm.gate", fid, {"action": "look_failed", "version": n, "stage": "store",
                                        "error": type(exc).__name__})
        return None
    if gap is not None:
        _wait(gate, fid, n, sha, gap)
        return None
    try:
        proof = {"engine": XS_ENGINE_VERSION, "xs_sha256": str(xs_fingerprint()), "run_sha": sha}
    except Exception as exc:  # noqa: BLE001 - no identity, no band proof: no look
        store.event("swarm.gate", fid, {"action": "look_failed", "version": n, "stage": "identity",
                                        "error": type(exc).__name__})
        return None
    busy = may_run(store, settings, _now(gate))
    if busy is not None:
        _wait(gate, fid, n, sha, busy)
        return None
    run_through = _runner_of(gate)
    code, params = version["code"], dict(version.get("params") or {})
    floors = state.get(FLOOR_KEY) if isinstance(state.get(FLOOR_KEY), Mapping) else {}
    try:
        runs = _timed(store, gate, lambda: run_through.segments(code, params, name=fid))
        ended = [_status(run) for run in runs]
        cached = floors.get(str(n))
        if any(status != "ok" for status in ended) or not runs:
            if "disqualified" not in ended:
                raise ValueError("the Train segments' runs ended " + ", ".join(sorted(set(ended))))
            floor = {"eligible": False, "why": "a Train-era run ended disqualified: its series is partial"}
            train_x = train_u = None
        else:
            train_x, train_u, segments = _train_series(S, runs, n)
            # THE FLOOR IS ALWAYS COMPUTED FROM THE SEGMENTS JUST RUN (an exact enumeration: no seed, and cheap beside
            # the two runs it reads). A floor kept from an earlier attempt of this look was once reused whenever it fit
            # the receipt's figures: nothing tied it to the Train series it was computed from, so after the panel job
            # restated a name's adjusted history or the spreads job rewrote the half-spreads between two attempts (a
            # look that waited on its lineage, on Validation, or lost its run once), the look was judged at the OLD
            # k_used and its sentence stated the old c_p and own_fp beside every live trade. Validation has a staleness
            # check (`result_sha`); the floor had none. What is kept under `FLOOR_KEY` is the record of the last one
            # computed, never an input.
            floor = _plain(dict(S.floor(segments, receipt=pinned)))
            if not S.floor_fits(floor, pinned):
                raise ValueError("the program floor does not fit the pinned receipt")
            if floor != cached:
                store.set_state(fid, **{FLOOR_KEY: {**dict(floors), str(n): floor}})
    except Exception as exc:  # noqa: BLE001 - no floor, no look (nothing spent)
        store.event("swarm.gate", fid, {"action": "look_failed", "version": n, "stage": "floor",
                                        "error": type(exc).__name__})
        return None
    if not floor.get("eligible"):
        _refuse(gate, fid, n, sha, "screen floor",
                f"{SCREEN_NAME}'s program floor is not eligible: {floor.get('why') or 'no reason given'}")
        return None
    template = elane.lineage_key(LANE, str(version.get("sha") or ""))
    try:
        twin, waits = _ask_lineage(gate, fam, template, train_x, train_u)
    except Exception as exc:  # noqa: BLE001 - a lineage that cannot be read spends no look
        store.event("swarm.gate", fid, {"action": "look_failed", "version": n, "stage": "lineage",
                                        "error": type(exc).__name__})
        return None
    if waits is not None:
        _wait(gate, fid, n, sha, waits)
        return None
    if twin is not None:
        _refuse(gate, fid, n, sha, "same lineage",
                f"the same lineage as {twin}, already looked at or refused at its pre-check (XS1: the template, or 0.7 "
                "in the residual or in the universe excess)")
        return None
    try:
        recorded = _timed(store, gate, lambda: run_through.validation(code, params, name=fid, k=K_BASE))
        if _status(recorded) != "ok":
            raise ValueError(f"the Validation run ended {_status(recorded)}")
        pre = dict(S.precheck(S.series(recorded.result, "x")))
    except Exception as exc:  # noqa: BLE001
        store.event("swarm.gate", fid, {"action": "look_failed", "version": n, "stage": "validation",
                                        "error": type(exc).__name__})
        return None
    noted = state.get(elane.VALIDATION_KEY) if isinstance(state.get(elane.VALIDATION_KEY), Mapping) else {}
    if (recorded.result or {}).get("result_sha") != noted.get("result_sha"):
        # The recorded Validation run did not reproduce (the store was refetched, or the identity moved): the
        # tournament validates it again (the same try) before any look.
        verdicts = dict(state.get(elane.VERDICTS_KEY) or {}) if isinstance(state.get(elane.VERDICTS_KEY), Mapping) else {}
        verdicts[str(n)] = {**dict(verdicts.get(str(n)) or {}), "stale": True}
        store.compare_and_set_state(fid, {"validation_version": n}, gate_ready=False,
                                    **{elane.VALIDATION_KEY: {**dict(noted), "stale": True},
                                       elane.VERDICTS_KEY: verdicts})
        store.event("swarm.gate", fid, {"action": "equity_validation_moved", "version": n, "structure": STRUCTURE})
        return None
    if not pre.get("passed"):
        _refuse(gate, fid, n, sha, "precheck", f"{SCREEN_NAME}'s Validation pre-check does not pass on the recorded run")
        return None
    # A22 (1), read BEFORE the look: the seat rule is fixed before the holdout is.
    try:
        unseated = Y.seat_refusal(style_of(fam, n))
    except Exception as exc:  # noqa: BLE001 - a rule that cannot be asked seats nothing
        unseated = f"{SEAT_STYLE}: the style rule could not be asked ({type(exc).__name__})"
    n_cell = cell_looks(store, cell)  # the XS1 looks ALREADY taken in its cell (duty 3)
    try:
        reading = probe_reading(root, str(_spec(fam).get("e2_route") or ""))
    except Exception:  # noqa: BLE001 - `probed` held; the reading beside is then left out
        reading = None
    code_sha = hashlib.sha256(str(code).encode("utf-8")).hexdigest()
    unstated: str | None = None
    marker = {"sha": sha, "n": n, "at": gate.clock(), "lane": LANE}
    with store.atomic():
        current = store.family(fid) or {}
        if current.get("retired_at") or (current.get("state") or {}).get("gate_hold") or store.looked(sha) or \
                store.lineage_looks(fid, include_inflight=True) >= c["looks_per_lineage"] or \
                look_room(store, cell) is not None:
            return None
        if not store.compare_and_set_state(fid, {"validation_version": n, "look_inflight": None}, gate_ready=False,
                                           look_inflight=marker):
            return None
    try:
        capability = mint_equity_gate_capability(Path(root) / STORE_DIR, reason=f"the panel look of {fid} v{n}")
        seed = P.look_seed(pinned.receipt_sha256, code_sha)
        ran = _timed(store, gate, lambda: run_through.look(code, params, name=fid, gate=capability, k=K_BASE,
                                                           placebos=int(pinned.placebo_draws), seed=seed))
        ended_look = _status(ran)
        if ended_look in elane.NOT_A_TRY:
            raise RunFailed(f"the look's run ended {ended_look}")  # the House could not run it: no look, owed again
        if ended_look != "ok":
            # THE RUN'S STATUS FIRST: a sealed run its own errors ended left a partial series. It is never judged:
            # the look is spent and FAILED.
            verdict = {"screen": SCREEN_NAME, "passed": False, "status": ended_look,
                       "why": f"the look's run ended {ended_look}: a partial series is never judged"}
            beside = f"no verdict: {verdict['why']}"
        else:
            verdict = _plain(S.verdict(ran.result, receipt=pinned, program_floor=floor, code_sha256=code_sha,
                                       french=None))
            try:
                beside = str(S.beside_line(verdict, pinned, n_cell=n_cell))
            except Exception as exc:  # noqa: BLE001 - the sentence is never stated with a hole in it
                beside = None
                unstated = f"{SEAT_UNSTATED}: the receipt's sentence could not be filled ({type(exc).__name__})"
    except RunLost as exc:
        # THE SEALED RUN WAS SENT AND DID NOT RETURN (E1's `LOOK_SENDS`): owed again once; the second time the look is
        # spent and FAILED, so no program is shown its holdout a third time.
        lost = _state(store.family(fid) or {}).get(elane.LOST_KEY)
        lost = lost if isinstance(lost, Mapping) else {}
        count = (int(lost.get("count") or 0) if lost.get("sha") == sha else 0) + 1
        spent = count >= elane.LOOK_SENDS
        store.event("swarm.gate", fid, {"action": "look_lost", "version": n, "lane": LANE, "structure": STRUCTURE,
                                        "count": count, "spent": spent, "error": type(exc).__name__})
        store.event("swarm.status", fid, {
            "action": "equity_look_lost", "alert": True, "version": n, "count": count, "spent": spent,
            "text": f"the sealed panel look of {fid} v{n} was sent and did not return ({count} of {elane.LOOK_SENDS}): "
                    + ("its look is spent and failed" if spent else f"it is owed once more; read {DECIDER_LOG}")})
        if not spent:
            store.compare_and_set_state(fid, {"look_inflight": marker}, look_inflight=None, gate_ready=True,
                                        **{elane.LOST_KEY: {"sha": sha, "count": count, "at": store.now()}})
            return None
        verdict = {"screen": SCREEN_NAME, "passed": False, "status": "lost",
                   "why": f"the sealed run was sent {elane.LOOK_SENDS} times and did not return"}
        beside = f"no verdict: {verdict['why']}"
    except Exception as exc:  # noqa: BLE001 - the look did not land: owed again next round (no look row)
        store.compare_and_set_state(fid, {"look_inflight": marker}, look_inflight=None, gate_ready=True)
        store.event("swarm.gate", fid, {"action": "look_failed", "version": n, "stage": "look",
                                        "error": type(exc).__name__})
        return None
    passed = bool(verdict.get("passed"))
    # DUTY 3: no sentence, no seat (a pass whose sentence cannot be stated beside its trades is recorded, never
    # seated); then A22 (1).
    seat = (SEAT_UNSTATED if unstated is not None else SEAT_CANDIDATE if unseated is None else SEAT_STYLE) \
        if passed else None
    unseated = unstated if unstated is not None else unseated
    beside = beside if beside is not None else f"no sentence: {unstated}"
    detail = {"lane": LANE, "label": "EQUITY", "structure": STRUCTURE, "screen": SCREEN_NAME,
              "receipt": pinned.receipt_sha256, "c_used": verdict.get("c_used"), "p_plac": verdict.get("p_plac"),
              "cell": list(cell), "n_cell": n_cell, "seat": seat, "seat_why": unseated if passed else None,
              "probe": reading, "seeded": False, "beside": beside, "passed": passed,
              **({"status": verdict["status"], "why": verdict.get("why")} if verdict.get("status") else {})}
    with store.atomic():
        store.add_look(fid, n, sha, passed=passed, p_value=_num(verdict.get("p_plac")), detail=detail)
        store.compare_and_set_state(fid, {"look_inflight": marker}, look_inflight=None)
        kept = {} if train_x is None else {TRAIN_X_KEY: train_x, TRAIN_U_KEY: train_u}
        store.set_state(fid, gated_sha=sha, gate_ready=False, gate="pass" if passed else "fail", dormant_cycles=0,
                        gate_outcome={"sha": sha, "result": "passed" if passed else "failed", "at": gate.clock()},
                        # (`passed` beside the verdict's own: the operator report's `style_open_passers`, package
                        # H's, reads the record's top level)
                        **{LOOK_KEY: {"version": n, "at": store.now(), "passed": passed, "verdict": verdict,
                                      "beside": beside, "seat": seat, "seat_why": unseated if passed else None,
                                      "cell": list(cell), "n_cell": n_cell, "probe": reading},
                           FLOOR_KEY: {**dict(floors), str(n): floor}, elane.TEMPLATE_KEY: template, **kept})
        current = store.family(fid) or {}
        if passed and seat == SEAT_CANDIDATE and current.get("band") == "gym" and not current.get("retired_at"):
            store.set_state(fid, banded_version=n, banded_sha=version.get("sha"), banded_at=gate.clock(),
                            banded_evaluator=proof)
            store.set_band(fid, "candidate", reason=f"passed its sealed look ({SCREEN_NAME}, EQUITY panel)")
    store.event("swarm.gate", fid, {"action": "look", "version": n, "passed": passed, "lane": LANE,
                                    "structure": STRUCTURE, "screen": SCREEN_NAME, "receipt": pinned.receipt_sha256,
                                    "seat": seat, "_verdict": verdict, "_beside": beside, "_probe": reading})
    if passed and seat != SEAT_CANDIDATE:
        store.event("swarm.status", fid, {
            "action": "panel_style_open" if seat == SEAT_STYLE else "panel_unstated", "alert": seat == SEAT_UNSTATED,
            "version": n, "lane": LANE, "structure": STRUCTURE,
            "text": f"{fid} v{n} passed {SCREEN_NAME} and takes no live seat on that pass alone ({unseated}): it is "
                    "recorded and shadowed, never seated by the look (the captain's A22)"})
    return passed


def beside_line(fam: Mapping[str, Any]) -> str | None:
    """The sentence recorded with the family's look (duty 3): what the reports state beside every live panel trade.
    None when it took no look."""
    looked = _state(fam).get(LOOK_KEY)
    line = looked.get("beside") if isinstance(looked, Mapping) else None
    return str(line) if isinstance(line, str) and line else None


def view(fam: Mapping[str, Any], *, lane: str | None = LANE) -> dict[str, Any]:
    """A panel family's line in a status or report (E1's `elane.view` forwards it): {lane, label, structure, seeded,
    screen (the screen that judged its recorded look; None before it), try, look, seat, beside, notes}."""
    from . import elane

    state = _state(fam)
    held = state.get(elane.TRY_KEY) if isinstance(state.get(elane.TRY_KEY), Mapping) else None
    looked = state.get(LOOK_KEY) if isinstance(state.get(LOOK_KEY), Mapping) else None
    verdict = (looked.get("verdict") if isinstance(looked.get("verdict"), Mapping) else {}) if looked else {}
    notes = []
    if looked and looked.get("seat") in (SEAT_STYLE, SEAT_UNSTATED):
        notes.append(f"passed {SCREEN_NAME}; takes no live seat on that pass alone ({looked.get('seat_why')}): recorded "
                     "and shadowed (the captain's A22)")
    return {"lane": lane, "label": "EQUITY", "structure": STRUCTURE, "seeded": False,
            "screen": SCREEN_NAME if looked else None,
            "try": {"version": held.get("version"), "entered": bool(held.get("entered"))} if held else None,
            "look": {"version": looked.get("version"), "passed": bool(verdict.get("passed"))} if looked else None,
            "seat": looked.get("seat") if looked else None, "beside": looked.get("beside") if looked else None,
            "notes": notes}


__all__ = ["STRUCTURE", "PANELS", "OBJECTIVE", "LANE", "MODES", "STATE_KEY", "FLOOR_KEY", "TRAIN_X_KEY",
           "TRAIN_U_KEY", "PRECHECK_KEY", "PLACEBO_KEY", "HALVES_KEY", "OOF_KEY", "LOOK_KEY", "SEALED", "CPU_KEY",
           "ZERO_KEY", "ALERTS_KEY", "TRAIN_OK_KEY", "STYLE_FIELD", "SEAT_CANDIDATE", "SEAT_STYLE", "SEAT_UNSTATED",
           "MAX_CELL_LOOKS",
           "PROBE_FILE", "PROBE_STRATA", "REVIEW_XS", "REVIEW_OBJECTIVE", "REVIEW_SYSTEM", "RESEARCHER_SYSTEM",
           "SETTINGS_KEY", "SCREEN_KEY", "SCREEN_NAME", "DECIDER_LOG", "STORE_DIR", "PANEL_MANIFEST",
           "UNIVERSE_MANIFEST", "DEFAULTS", "BOUNDS", "CENSUS_NOTE_MAX", "CENSUS_LABEL", "SCREEN_NULLS", "PANEL_AGENDA",
           "INPUTS", "BAR_XS", "FAILS_XS", "PROGRAM_FAILS", "JUDGED_XS", "MAP_LABEL", "K_BASE", "K_STRESS",
           "SAME_LINEAGE_XS", "TRAIN_ENDED", "EARLY_CAUSES", "LineageUnread", "cfg", "pin", "receipt", "mode",
           "live_ready", "status", "health", "HEALTH", "seat_word", "seat_standing", "is_panel", "seatable", "panel_families", "record_of", "versions_of", "passed_version",
           "judged", "identity", "hidden_year_of", "card_errors", "cell_of", "family_cell", "cell_text",
           "closed_cells", "cell_looks", "forward_verdicts", "look_room", "probe_reading", "probed", "style_of",
           "assign", "run_spans", "seen_spans", "hidden_span", "agenda_text", "contract_text", "bar_text",
           "request_text", "researching", "quota", "check_code", "admit", "birth", "runner", "cpu_spent", "may_run",
           "book_cpu", "outside", "train_score_xs", "same_targets", "state_check", "restart", "with_state",
           "program_fault", "compact", "house_failure", "fault", "years_ok", "score", "rescored", "version_text",
           "restart_text", "style_text", "train_facts", "brief", "blocked", "step", "write", "review_question",
           "review_step", "review_failed", "rubric_sha", "finish", "pass_current", "may_validate", "zero_edge_rate",
           "train_map", "map_notes", "train_map_text", "request_map_text", "same_lineage", "validate",
           "lineage_spent", "look", "beside_line", "view"]
