"""THE PANEL LANE in the swarm (release E4): structure "panel", its agenda cells, the Train bar equity-xs-v1,
Validation, the one look under XS1, lineage and seats.

Owner: package G. STEP 0 STUB: the names, the settings and the keys are the contract; every function raises
NotImplementedError until G lands. E1's and E2's modules get one-line dispatches to this one (package G's patches in
league/swarm/e4_patches/G.md), never new bodies.

A panel family: lane "equity", structure "panel", `roots` [], spec {`lane`, `agenda`, `panel`, `max_names`,
`rebalance`, `weekday`, `e2_route`, `hidden_year`, `gid`}. Its Train record is the family-state key `STATE_KEY`
(generator-readable through `train_facts` only); everything after Train is SEALED (`SEALED`: no generator, brief,
request, map or route choice ever reads it).

THE SWITCH is `elane.panel.mode` (`MODES`): "off" -> "train" (births and the Train bar) -> "gate" (Validation and XS1
looks) -> "live" (a passer may take a seat). THE EFFECTIVE MODE is `mode`: "off" unless `elane.mode` is "gate"; "off"
when the panel manifest is missing or its coverage verdict is "insufficient"; at most "train" without a pinned XS1
receipt (`league.xs.screen.pinned_receipt`: NO RECEIPT, NO LOOK) or with `hs_share` under `spreads_min_share`; at most
"gate" unless `live_ready`. WITH EVERY SWITCH OFF NOTHING OF E4 RUNS, SPENDS OR TRADES.

`live_ready(root, settings)`: the universe deploy is in force (`live_from` set), today's tradable share of eligible
names is at least `live_min_tradable_share`, the committed universe is younger than `universe_max_age_days`, the last
nightly `i6.equal` is True, AND THE TWIN MARKER (`league.xs.book.TWINS_FILE`, package J's): the file exists, its
`through` is the panel store's `fetched_through` or the session before, and no listed instance is more than one
session behind its `due` day. So with J unmerged, or its nightly run stopped for two nights, "live" reads as "gate".
The swarm process reads that one file and never forward.sqlite.

THE TRAIN BAR equity-xs-v1 (in-sample filter; never evidence; E4-SPEC 8.3). One run a SEEN SPAN (`seen_spans`), each
starting flat; per span the full universe at k 1.0 and at k 1.5 (the 1.5 run with `placebos_train` placebos and
`calls=True`) and each asset half at k 1.5; read pooled (`league.xs.results.pooled`, `league.xs.placebo.stat`); then
the restart check on the k 1.5 runs (E2's `elane_train.restart_check` pattern through the panel kind: `state_check`);
then, AFTER the verdict is recorded, the hidden run, whose result goes to `OOF_KEY` and nowhere else. `BAR_XS` and
`FAILS_XS` name the rules: XA0 (activity: the program's, refutes nothing), XT1, XY1, XH1, XP1, XR1 (`JUDGED_XS`: a
family is REFUTED only on one of these), STATE, WINDOW.

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
   with `seat` `SEAT_STYLE`, the family takes NO band and no proof (so no reader of the bands can seat it), and the
   forward record goes on shadowing it; the forward route is its way to a seat. Only a passer the rule reads as not
   open becomes a Candidate.
2. AT MOST `MAX_CELL_LOOKS` XS1 LOOKS AN AGENDA CELL until a forward verdict exists in that cell (`look_room`; the
   study measured that one zero-edge mechanism given eight looks passes at least one in most worlds). No forward
   verdict can exist before the forward route is measured and built, so in this release the cap is flat. A look the
   cap holds back is not spent: the family waits.
3. THE CODE REVIEW AND THE CONTAMINATION PROBE COME BEFORE A LOOK. E2's equity review of a panel program carries the
   rubric `REVIEW_XS` (no embedded return table, no calendar recognition, and the spec's three); and `probed` holds
   the look back until E3's contamination probe has a published result, with the panel strata `PROBE_STRATA`, for
   the route that wrote the program (`<root>/contamination.json`, aggregates only; while release E3 or its panel
   strata are not merged there is none, and every panel look waits). The probe's reading is recorded with the look.
4. The screen reproduces the study's conformance vectors and one more for the second segment's floor cell alone
   (package E's; `league.xs.screen`).

Imports nothing of league.live at import time (the panel's own decider is built in `runner`). league.xs is imported
inside the functions that need it, as E1's `elane` imports league.equity.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from ..xs import PANELS, STRUCTURE

# ----------------------------------------------------------------------------------------------------------- vocabulary
OBJECTIVE = "equity-xs-v1"
LANE = "equity"
MODES = ("off", "train", "gate", "live")
#: The family-state key of a panel family's Train record: per version {n, at, identity (`xs_identity()`), verdict,
#: fails, facts, state (the restart check's counts)}.
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
#: THE CAPTAIN'S A22. The Train record's field of the style verdict (per version: `league.xs.style.style_open`'s
#: answer); what a look's record says of a passer's seat; the cap on a cell's XS1 looks (a House rule, never a
#: setting); E3's probe file under the root and the panel strata a route's result must hold before a look; and what
#: the equity review's rubric gains for a panel program.
STYLE_FIELD = "style"
SEAT_CANDIDATE = "candidate"
SEAT_STYLE = "style-open"
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
#: The settings block (`elane.panel`) and the screen's pin (`elane.screens.equity_xs`).
SETTINGS_KEY = "panel"
SCREEN_KEY = "equity_xs"
#: The panel decider's log, under the swarm's root.
DECIDER_LOG = "xs-decider.log"

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
#: `elane.screens.equity_xs` as policy.json ships it: every value a null, and with nulls every panel look waits.
SCREEN_NULLS: dict[str, Any] = {
    "name": "XS1", "screen": "XS1", "receipt_sha256": None, "c_XS": None, "c_margin": None, "alpha_plac": None,
    "placebo_draws": None, "rung": None, "fp_cap": None, "owner_wall": None, "validation_tries": None,
    "holdout_looks": None, "retry": False, "flags": {}, "screen_flags": [], "beside": None,
}

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
#: The fails that judge the MECHANISM on Train: a family is REFUTED only with a version judged by one of these.
JUDGED_XS = ("XT1", "XY1", "XH1", "XP1", "XR1")

_STUB = "league.swarm.elane_xs is a Step 0 stub: package G builds it (league/xs/E4_INTERFACES.md)"


# ------------------------------------------------------------------------------------------------- settings and mode
def cfg(settings: Mapping[str, Any] | None) -> dict[str, Any]:
    """`elane.panel` with every key held to its bound (a malformed value is its default), plus "screen": the
    `elane.screens.equity_xs` block as it is."""
    raise NotImplementedError(_STUB)


def mode(settings: Mapping[str, Any] | None, root: str | Path | None = None) -> str:
    """THE EFFECTIVE MODE (the module docstring), one of `MODES`. Without a `root` the store-side conditions cannot be
    read: at most the settings' own mode, and never "live"."""
    raise NotImplementedError(_STUB)


def live_ready(root: str | Path, settings: Mapping[str, Any] | None) -> tuple[bool, str | None]:
    """(ready, the first leg that fails): the universe deploy, the tradable share, the universe's age, the last I6,
    the twin marker (the module docstring)."""
    raise NotImplementedError(_STUB)


def is_panel(fam: Mapping[str, Any] | None) -> bool:
    """Whether a family row is a panel family (structure `STRUCTURE`)."""
    raise NotImplementedError(_STUB)


def seatable(root: str | Path) -> Callable[[Any], bool]:
    """The seat rule `bands.equity_seating` is handed: E1's for "etf" and "stock"; "panel" iff the effective mode is
    "live". (A style-open passer never reaches this rule: `look` gives it no band, A22.)"""
    raise NotImplementedError(_STUB)


# ------------------------------------------------------------------------------------------- cards, cells and births
def card_errors(card: Any, settings: Mapping[str, Any] | None) -> list[str]:
    """Why a panel card is refused ([]: it is not): lane "equity"; `panel` in `panels`; `max_names` between 5 and the
    lane's cap; an allowed `rebalance`; a `weekday` only on a weekly card; an agenda key of `PANEL_AGENDA`; no
    `symbols`; the mode at least "train" ("the panel lane is closed"); the cell not closed."""
    raise NotImplementedError(_STUB)


def cell_of(lane: Any, agenda: Any, panel: Any) -> tuple[str, str, str]:
    """A panel family's agenda cell: (lane, agenda, "panel:" + panel) (E2's 3-tuple shape; never built by E2's
    `cell_of(lane, agenda, symbols)`)."""
    raise NotImplementedError(_STUB)


def closed_cells(store: Any, settings: Mapping[str, Any] | None) -> list[tuple[str, str, str]]:
    """The panel cells with E2's `refuted_cell_cap` families refuted on a `JUDGED_XS` rule and no pass: no birth
    there."""
    raise NotImplementedError(_STUB)


def cell_looks(store: Any, cell: Sequence[str]) -> int:
    """THE HOUSE'S COUNT (duty 3): the XS1 looks already taken by panel families of `cell`, in flight included."""
    raise NotImplementedError(_STUB)


def look_room(store: Any, cell: Sequence[str]) -> str | None:
    """A22 (2): why `cell` has no XS1 look left, or None: `cell_looks(store, cell)` has reached `MAX_CELL_LOOKS` and
    no forward verdict exists in the cell (none can in this release: the cap is flat). The look it holds back is not
    spent."""
    raise NotImplementedError(_STUB)


def probed(root: str | Path, fam: Mapping[str, Any]) -> str | None:
    """A22 (3): why the look must wait on the contamination probe, or None: `<root>/PROBE_FILE` (E3's
    `league.ops.contam_probe.FILE`, read by name: aggregates only) holds a published result (`at`) for the route that
    wrote the family's program (its spec's `e2_route`) whose cells carry every stratum of `PROBE_STRATA`. No file, no
    such route, no panel stratum, an unreadable file: the reason, and the look waits (nothing spent)."""
    raise NotImplementedError(_STUB)


def style_of(fam: Mapping[str, Any], version: int | None = None) -> dict[str, Any] | None:
    """A22 (1): the style verdict the Train record keeps for a version (default: the banded or latest judged one),
    or None when it has none (read as style-open: `league.xs.style.seat_refusal(None)`)."""
    raise NotImplementedError(_STUB)


def assign(store: Any, cell: Sequence[str]) -> int | None:
    """THE HIDDEN YEAR of a new panel family: `league.xs.config.TRAIN_YEARS[(k_c + elane_folds.cell_hash(cell)) % 6]`,
    k_c = the panel families already born in that cell with a hidden year; None while E3 is not merged or its folds
    are not recording (the bar then reads all six Train years, stated on the map). Never E3's own `assign` (it rotates
    over seven years) and never `elane_folds.birth_fields` (it takes no cell)."""
    raise NotImplementedError(_STUB)


def seen_spans(hidden: int | None) -> tuple[tuple[Any, Any], ...]:
    """The Train bar's run spans: `league.xs.config.TRAIN_SEGMENTS` with the hidden year cut out (a segment without it
    as it is; the one with it cut into the stretch before and the stretch after: two or three spans; both whole
    segments for None)."""
    raise NotImplementedError(_STUB)


def hidden_span(hidden: int) -> tuple[Any, Any]:
    """The hidden year's own sessions (the out-of-fold run's span)."""
    raise NotImplementedError(_STUB)


def agenda_text() -> str:
    """The panel agenda as the architect's request shows it (`PANEL_AGENDA`; the captain's census notes under the
    label "in-sample 2010-24, best of 7; not evidence")."""
    raise NotImplementedError(_STUB)


def contract_text() -> str:
    """XS.md in brief (what a panel program is and sees), for the architect's request and the researcher's brief."""
    raise NotImplementedError(_STUB)


def bar_text() -> str:
    """The Train bar in words (`BAR_XS`, `FAILS_XS`), with what it loosens stated (five seen years, not six)."""
    raise NotImplementedError(_STUB)


def quota(store: Any, settings: Mapping[str, Any] | None, births: int) -> int:
    """How many of a pass's `births` equity births are the panel's: `birth_share` of them, never past `max_alive` panel
    families in Train research; 0 under mode "train"."""
    raise NotImplementedError(_STUB)


# -------------------------------------------------------------------------------------------------- runs and the bar
def runner(root: str | Path) -> Any:
    """The panel's `league.xs.runner.Isolated` over its OWN `league.live.decider.Decider(log=<root>/xs-decider.log)`,
    built once a process, nice 19, its hash seed pinned to E1's `elane.EVIDENCE_HASH_SEED`: never
    `elane.isolated_runner`'s child, never the live decider."""
    raise NotImplementedError(_STUB)


def may_run(store: Any, settings: Mapping[str, Any] | None, now: float) -> str | None:
    """Why a panel run may not START now, or None: `league.xs.config.quiet(now, run_budget_seconds)` (asked before
    EACH run of a version), then the day's CPU (`cpu_seconds_day` less `CPU_KEY`)."""
    raise NotImplementedError(_STUB)


def book_cpu(store: Any, seconds: float, now: float) -> None:
    """Add a run's child seconds to the UTC day's count (`CPU_KEY`)."""
    raise NotImplementedError(_STUB)


def train_score_xs(runs: Mapping[str, Any], *, years_ok: Sequence[int]) -> dict[str, Any]:
    """The bar's verdict on one version's seen-span runs ({"base", "stress", "halves", "placebo"} by span): {passed,
    fails, facts, judged}."""
    raise NotImplementedError(_STUB)


def state_check(decider: Any, code: str, params: Mapping[str, Any] | None, *, name: str,
                runs: Sequence[Any]) -> dict[str, Any]:
    """THE RESTART CHECK on the k 1.5 runs (`league.xs.runner.state_stream`): instance A loaded once, instance B
    loaded fresh after calls 3, 10, 13, 20, 23, 30 and on, both deciding on THE SAME `Inputs` at every called
    decision. A call matches when `at` is equal, the two targets name the same ids, every weight is within 1e-6 and
    the errors moved by the same count. Never a silent pass: `elane_train.StateCheckInterrupted` when an answer's
    `stats.calls` is not what its instance was asked, or the decider restarted."""
    raise NotImplementedError(_STUB)


def score(researcher: Any, fam: Mapping[str, Any], version: Mapping[str, Any], *,
          rescore: bool = False) -> dict[str, Any]:
    """One version's Train judgment (`may_run` first; the runs, the bar, the restart check, the record, then the
    hidden run). It writes E2's scored event for every version judged on the bar (`swarm.elane` {"pass": "scored",
    version, sha, bar_passed, fails, objective: OBJECTIVE, judged}), which is the forward registry's time evidence.
    THE STYLE READING (A22 (1)) is taken here, from the seen spans' full-universe k 1.0 runs, and kept in the record
    under `STYLE_FIELD` whatever the bar said."""
    raise NotImplementedError(_STUB)


def train_facts(fam: Mapping[str, Any]) -> dict[str, Any]:
    """What a researcher sees of its own family: the seen-span facts at both k and each rule's pass or fail, and
    whether its Train holdings read style-open and on which characteristics (a Train fact: a style-open program can
    pass the look and still take no seat). NEVER a half's figure, a placebo rank, an id, the hidden year, or anything
    after Train."""
    raise NotImplementedError(_STUB)


def train_map(store: Any) -> list[dict[str, Any]]:
    """The panel Train map's rows, one a cell, with the ZERO-EDGE EXPECTED column (`ZERO_KEY`)."""
    raise NotImplementedError(_STUB)


# ------------------------------------------------------------------------------------- Validation, the look, lineage
def same_lineage(store: Any, fam: Mapping[str, Any], *, template: str, train_x: Mapping[str, Sequence],
                 train_u: Mapping[str, Sequence]) -> str | None:
    """THE LINEAGE (duty 2): the panel family already looked at, in flight, or refused at the pre-check that `fam`'s
    program is the same lineage as, or None. FAILS CLOSED as E1's (`elane.LineageUnread`): a family that reached the
    pre-check and keeps no Train series is never skipped."""
    raise NotImplementedError(_STUB)


def validate(tournament: Any, fam: Mapping[str, Any], version: Mapping[str, Any]) -> dict[str, Any]:
    """A panel version's ONE Validation try (mode at least "gate"; E1's rations): the two Train segments' series kept
    (duty 1), the lineage asked (duty 2), the 2025 run at k 1.0 and 1.5, the line `league.xs.screen.precheck` on the
    k 1.0 residual, `PRECHECK_KEY` written, and the k 1.0 run's `summary.sd_date_return` under E1's `elane.SIGMA_KEY`
    (EDM1's sigma for a panel program: a sd per close DATE)."""
    raise NotImplementedError(_STUB)


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
    family takes no band and no proof, and the forward record shadows it."""
    raise NotImplementedError(_STUB)


def beside_line(fam: Mapping[str, Any]) -> str | None:
    """The sentence recorded with the family's look (duty 3): what the reports state beside every live panel trade.
    None when it took no look."""
    raise NotImplementedError(_STUB)


__all__ = ["STRUCTURE", "PANELS", "OBJECTIVE", "LANE", "MODES", "STATE_KEY", "FLOOR_KEY", "TRAIN_X_KEY",
           "TRAIN_U_KEY", "PRECHECK_KEY", "PLACEBO_KEY", "HALVES_KEY", "OOF_KEY", "LOOK_KEY", "SEALED", "CPU_KEY",
           "ZERO_KEY", "ALERTS_KEY", "STYLE_FIELD", "SEAT_CANDIDATE", "SEAT_STYLE", "MAX_CELL_LOOKS", "PROBE_FILE",
           "PROBE_STRATA", "REVIEW_XS", "SETTINGS_KEY", "SCREEN_KEY", "DECIDER_LOG", "DEFAULTS", "BOUNDS",
           "CENSUS_NOTE_MAX", "SCREEN_NULLS", "PANEL_AGENDA", "BAR_XS", "FAILS_XS", "JUDGED_XS", "cfg", "mode",
           "live_ready", "is_panel", "seatable", "card_errors", "cell_of", "closed_cells", "cell_looks", "look_room",
           "probed", "style_of", "assign",
           "seen_spans", "hidden_span", "agenda_text", "contract_text", "bar_text", "quota", "runner", "may_run",
           "book_cpu", "train_score_xs", "state_check", "score", "train_facts", "train_map", "same_lineage",
           "validate", "look", "beside_line"]
