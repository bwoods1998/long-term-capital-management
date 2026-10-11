"""XS1, the panel screen: the pre-check, the program's own floor, the one look, and the sentence beside every trade.

Owner: package E. STEP 0 STUB: the constants and `ReceiptXS` are the contract; `ScreenRefused`, `look_permitted` and
`holdout_t` are E1's own, re-exported; everything else raises NotImplementedError until E lands.

THE RULE IS THE PINNED PRE-REGISTRATION, EXACTLY: XSCREEN-1 revision 2 (sha256 c46aec17..., pinned 2026-10-11
03:03:08Z), section 4. Where E4-SPEC section 9 differs (it was revised in parallel without seeing it), the
pre-registration wins. THE THRESHOLDS ARE THE RECEIPT'S: docs/benchmarks/equity_screen_xs_1.json, which the captain
lands when the study finishes and pins in policy.json `elane.screens.equity_xs`. UNTIL THEN THERE IS NO RECEIPT, AND A
SCREEN WITH NO PINNED RECEIPT REFUSES EVERY PROGRAM (`ScreenRefused`): tests use the fixture marked fake
(league/tests/fixtures/equity_screen_xs_fake.json).

x is the residual, x15 the stress residual (`league.xs.placebo`), one observation a session.

1. THE WINDOWS (4.1). V = calendar 2025 (250 sessions); H = 2026-01-02..2026-10-09, exactly 194 sessions
   (`league.equity.config.LOOK_FIRST`, `LOOK_CAP`). The look's run starts flat at V's first session and runs through
   H; `split` cuts its series in two. One sealed look a lineage; days after the cap are forward days only.
2. THE PRE-CHECK on V (4.2): (lots fully exited >= 20 or sessions with a lot held at the close >= 120) AND sum_V x >
   1e-12: E1's `precheck` on x. A failed pre-check spends no look, and spends the lineage's one Validation try.
3. THE PROGRAM'S OWN FLOOR (4.4), before the look, no look spent when ineligible: S2's exact enumeration applied to
   the residual, at L = 194 ONLY. Pools: the program's own (x, w) on each Train-era span, from its first decision + 2
   sessions to the span's last session. Floor cells: (i) both pools together, when both exist and each has at least
   `MIN_POOL_BOTH` sessions; (ii) each single pool that has at least `MIN_POOL_ALONE`, alone. A world is a holdout
   block of 194 consecutive pool sessions, circular inside one pool, weighted by its number of non-overlapping
   Validation blocks. The null is N0: x0 = x - w x kappa_H. In each cell k_cell = the smallest k in 0..500 with
   HO[k] x 100 <= 12 x T; k_p = the largest k_cell; c_p = k_p / 100. THIS IS NOT `league.equity.screen.floor_s2` AS IT
   STANDS (that reads L 194 and 251 and has no first-span-alone cell): package E's note in E4_INTERFACES.md says how
   the enumeration is reused. INELIGIBLE: no floor cell, a cell with T = 0 or with no such k, zero exposure, a series
   that is not finite, a session outside the spans, k_used above 500.
4. THE THRESHOLD: c_used = max(c_XS, c_p + c_margin) on the 0.01 grid (k_used = max(k_XS, k_p + 5)). c_XS is the bar
   every program meets whatever its own floor is (it is calibrated with the own floors switched off); the own floor
   can only raise a program's bar above it.
5. THE LOOK on H (4.3): t_H = mean(x_H) / std(x_H, ddof=1) x sqrt(194), by `holdout_t`'s expression (undefined, a
   fail, when the std is below 1e-12 or the result is not finite).
   pass = pre-check AND sum_H x > 1e-12 AND sum_H x15 > 1e-12 AND t_H >= c_used AND p_plac <= alpha_plac,
   the last held in integers: (1 + count) x 100 <= 12 x (draws + 1), i.e. count <= 119 of 999 placebos on H's sessions.
6. THE LABELS BESIDE, never a gate (4.5): the basket share ("basket-led" when the sum over V and H of the cells' P&L
   is at least the sum of x, else "selection-led"); the French label ("no style loading found", "style-loaded: ...",
   or "unmeasured" when fewer than `FRENCH_MIN_DAYS` days of French's factors are on the House, which is the case
   until a route to them exists: the receipt's "style-open" flag then attaches).
7. LINEAGE (4.6): one look a lineage; the same lineage = the same template, or a Train daily correlation of 0.7 or
   more (`league.equity.screen.same_lineage`) with a program already looked at OR already refused at the pre-check, IN
   EITHER SERIES, the residual x or the universe excess u. No Validation-only retry (`VALIDATION_TRIES` 1). A lineage
   that took an XS1 look can take no S2 look, and the reverse.
8. STATED BESIDE EVERY LIVE PANEL TRADE: the receipt's sentence (`beside_line`), its per-program placeholders
   `BESIDE_FIELDS` filled on the House: {c_used}, {c_p}, {own_fp} (the largest, over the program's floor cells, of
   HO[k_used] / T: in-sample, at most 12% by construction, and said so), {n_cell} (the XS1 looks already taken in the
   program's agenda cell, counted by the House), {basket}, {label}, {flags}.

Failure order of `verdict` (the first is `why`): no receipt (ScreenRefused); the floor ineligible, or run under other
figures than the receipt's; a placebo block of another rung, another number of draws or another seed than the
receipt and the program's code fix; the windows; the pre-check; the look.

THE FORWARD ROUTE F-GS-XS (the pre-registration's section 11; measured by a later study, read by package J and E6):
checkpoints at `CHECKPOINTS` forward sessions, a pass = t_n >= c_FX AND sum x > 1e-12 AND sum x15 > 1e-12 AND the
placebo rank over the same sessions <= alpha_f, alpha_f = `ALPHA_F`["fresh"] for a lineage that declares the route at
registration (it can never take an XS1 look) and `ALPHA_F`["looked"] after an XS1 look.

Evidence module (in the xs identity; one of its roots; a fixed judge). It imports E1's PUBLIC names of
`league.equity.screen` only.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from ..equity.screen import ScreenRefused, Series, holdout_t, look_permitted

SCREEN = "XS1"
RECEIPT_NAME = "equity_screen_xs_1"
RECEIPT_PATH = "docs/benchmarks/equity_screen_xs_1.json"
CONTRACT = "C-XS-1"
#: The keys a receipt must carry (the pre-registration's 10.1); the loader refuses a receipt that lacks one.
RECEIPT_KEYS = ("name", "screen", "study", "rule", "contract", "fp_cap", "owner_wall", "c_XS", "c_margin",
                "alpha_plac", "placebo_draws", "stratum", "residual", "precheck", "look", "floor", "windows", "lineage",
                "R3_retry_permitted", "labels", "flags", "screen_flags", "ladder", "fp_zero_edge", "fp_zero_edge_B",
                "fp_zero_edge_max", "fp_validation_known_max", "family_wise_zero_edge", "family_wise_8_max",
                "finite_pool_bias", "finite_pool_bias_max", "style_known_rate", "style_known_max", "power",
                "cost_of_rule", "study_program_floors", "limits", "stated_beside_every_live_trade", "note", "sha256")
#: What policy.json `elane.screens.equity_xs` pins, every value copied from the receipt (it ships with nulls, and with
#: nulls every panel look waits).
PIN_KEYS = ("name", "screen", "receipt_sha256", "c_XS", "c_margin", "alpha_plac", "placebo_draws", "rung", "fp_cap",
            "owner_wall", "retry", "flags", "screen_flags", "beside")
#: The per-program placeholders of the sentence beside every live trade (the receipt fills its own figures once).
BESIDE_FIELDS = ("c_used", "c_p", "own_fp", "n_cell", "basket", "label", "flags")
#: The figures the pre-registration fixes; a receipt that states another is refused.
FP_CAP = 0.12
OWNER_WALL = 0.15
ALPHA_PLAC = 0.12
PLACEBO_DRAWS = 999
#: The placebo bar in integers: count <= this of `PLACEBO_DRAWS`.
PLACEBO_COUNT_MAX = 119
C_MARGIN = 0.05
C_GRID_STEP = 0.01
#: c_XS lies on 0.00..3.00 (k_XS in 0..300); a program's k_used above `K_MAX` (c 5.00) is ineligible.
K_XS_MAX = 300
K_MAX = 500
#: The rungs a receipt may adopt (R2 and R3 are never adopted: they would count sector, beta or momentum direction as
#: selection).
RUNGS = ("R0", "R1")
H_LENGTH = 194
V_LENGTH = 250
MIN_POOL_BOTH = 251
MIN_POOL_ALONE = 550
POOL_SKIP = 2
ACTIVITY_ROUND_TRIPS = 20
ACTIVITY_INVESTED_DAYS = 120
SAME_LINEAGE_CORR = 0.7
LINEAGE_SERIES = ("x", "u")
LOOKS_PER_LINEAGE = 1
VALIDATION_TRIES = 1
ZERO = 1e-12
BASKET_LABELS = ("basket-led", "selection-led")
FRENCH_FACTORS = ("Mkt-RF", "SMB", "HML", "Mom", "ST_Rev")
FRENCH_MIN_DAYS = 120
FRENCH_T = 2.0
UNMEASURED = "unmeasured"
#: The receipt's screen-level flag, attached to every panel program whose French label is style-loaded or unmeasured.
STYLE_OPEN = "style-open"
#: THE FORWARD ROUTE (F-GS-XS; read by package J and E6, never by the look).
CHECKPOINTS = (20, 60, 120, 250)
ALPHA_F = {"fresh": 0.12, "looked": 0.03}

_STUB = "league.xs.screen is a Step 0 stub: package E builds it (league/xs/E4_INTERFACES.md)"


@dataclass(frozen=True)
class ReceiptXS:
    """The pinned XS1 receipt as policy.json carries it (`PIN_KEYS`, copied from the receipt file's keys):
    `receipt_sha256` (the file's bytes, 64 hex), `c_XS` and `c_margin` (on the 0.01 grid), `alpha_plac` (0.12),
    `placebo_draws` (999), `rung` (the adopted stratum: "R0", or "R1" when the ladder fell back), `fp_cap` (0.12),
    `owner_wall` (0.15), `retry` (`R3_retry_permitted`: False), `flags` ({archetype: (flag, ...)}, DR4's),
    `screen_flags` (("style-open",) or ()), `beside` (`stated_beside_every_live_trade`: the sentence, with
    `BESIDE_FIELDS` as placeholders) and `fp` (the receipt's rule-level figures stated beside)."""

    receipt_sha256: str
    c_XS: float
    c_margin: float
    alpha_plac: float
    placebo_draws: int
    rung: str
    fp_cap: float
    owner_wall: float
    retry: bool
    flags: Mapping[str, tuple[str, ...]]
    screen_flags: tuple[str, ...]
    beside: str
    fp: Mapping[str, Any]


def receipt_sha256(path: str | Path) -> str | None:
    """sha256 of the receipt file's bytes (64 hex), or None when there is no such file."""
    raise NotImplementedError(_STUB)


def pinned_receipt(block: Mapping[str, Any] | None) -> ReceiptXS | None:
    """The receipt as policy.json pins it (`elane.screens.equity_xs`), or None: a block of nulls, a missing or
    malformed value, a figure the pre-registration does not allow. None refuses every look."""
    raise NotImplementedError(_STUB)


def load_receipt(path: str | Path, *, pinned_sha256: str) -> ReceiptXS:
    """The receipt file, verified against its pin. ScreenRefused on: a sha that is not the pin's; a missing key of
    `RECEIPT_KEYS`; a `screen` other than "XS1" or a `contract` other than `CONTRACT`; c_XS or c_margin off the 0.01
    grid, c_XS outside 0..3.00; alpha_plac above `ALPHA_PLAC`; fp_cap above `FP_CAP`; an owner_wall above
    `OWNER_WALL`; placebo_draws other than `PLACEBO_DRAWS`; a rung outside `RUNGS`; `R3_retry_permitted` true; a
    sentence that lacks a placeholder of `BESIDE_FIELDS`."""
    raise NotImplementedError(_STUB)


def series(result: Mapping[str, Any], column: str = "x") -> Series:
    """A run's daily series as E1's `Series`: `days` the run's sessions, `r` the named column of `result["daily"]`
    ("x" the residual, "x15" the stress residual, "u" the universe excess, "r" the raw P&L), `w` the exposure, `b` 0,
    `exits`, `invested`. ValueError (fail closed) on a result without its daily rows or with a value that is not
    finite."""
    raise NotImplementedError(_STUB)


def split(s: Series) -> tuple[Series, Series]:
    """The look run's series cut into (V, H) by `league.equity.config.WINDOWS["validation"]` and `LOOK_FIRST`..
    `LOOK_CAP`. ValueError when a session lies in neither."""
    raise NotImplementedError(_STUB)


def windows(v: Series, h: Series) -> dict[str, Any]:
    """{ok, why, validation: {first, last, sessions}, holdout: {...}}: V is 2025's `V_LENGTH` sessions and H exactly
    `H_LENGTH` sessions from `LOOK_FIRST` through `LOOK_CAP`, sharing no session."""
    raise NotImplementedError(_STUB)


def precheck(v: Series) -> dict[str, Any]:
    """Step 2 on Validation (E1's `precheck` on the residual): {passed, round_trips, invested_days, sum, sessions,
    checks {activity, sum_positive}}."""
    raise NotImplementedError(_STUB)


def floor(segments: Sequence[Series | None], *, receipt: ReceiptXS) -> dict[str, Any]:
    """Step 3: the program's own floor from its Train-era residual series (one `Series` per `config.TRAIN_SEGMENTS`
    entry, `r` = x; None or empty where it has none). Deterministic: an exact enumeration, no seed. -> {screen "XS1",
    eligible, why, method "exact", L 194, c_p, k_p, c_used, k_used, own_fp, fp_cap, c_XS, c_margin (as run:
    `floor_fits` checks them against the receipt), cells {"both" | "0" | "1": {pools [lengths], T, k_cell, HO_used}}}.
    Computed on the House, never committed. ScreenRefused without a receipt; ValueError on arrays of unequal length."""
    raise NotImplementedError(_STUB)


def floor_fits(program_floor: Any, receipt: Any) -> bool:
    """Whether a (cached) floor was run by this receipt's figures (fp_cap, c_XS, c_margin, L), eligible or not; False
    for anything else (run the floor again)."""
    raise NotImplementedError(_STUB)


def look(v: Series, h: Series, *, h15: Series, c_used: float, placebo_t: Sequence[float | None],
         alpha: float = ALPHA_PLAC) -> dict[str, Any]:
    """Step 5 after the one look: {passed, t_H, sum_h, sum_h15, count, n_placebo, p_plac, c_used, checks {precheck,
    sum_h, sum_h15, t_H, placebo}}. `h15`: the stress residual on H; `placebo_t`: the placebos' t on H's sessions
    (None where undefined: not above). The placebo bar is held in integers."""
    raise NotImplementedError(_STUB)


def loadings(x: Sequence[float], factors: Sequence[Sequence[float]], names: Sequence[str]) -> dict[str, Any]:
    """OLS of x on the daily `factors` (columns named by `names`) with an intercept and plain OLS standard errors:
    {"alpha": {"a", "t"}, name: {"b", "t"}}. Beside, never a gate."""
    raise NotImplementedError(_STUB)


def labels(result: Mapping[str, Any], *, french: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Step 6 for the look run's result: {"basket": one of `BASKET_LABELS`, "label": the French label, "loadings"}.
    `french` None (no French factors on the House) is "unmeasured"."""
    raise NotImplementedError(_STUB)


def verdict(look_result: Mapping[str, Any], *, receipt: ReceiptXS | None, program_floor: Mapping[str, Any],
            code_sha256: str, french: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """The whole rule on the look run's result (its daily series over V and H and its placebo block): {screen "XS1",
    passed, why, c_used, c_p, k_used, t_H, sum_h, sum_h15, p_plac, count, n_placebo, rung, own_fp, t_raw (the raw
    P&L's t on H), t_nw5, basket, label, loadings, identity_share, precheck, look, windows, flags (the receipt's for
    the program, "style-open" attached when it applies), receipt (its sha)}. The module docstring's failure order;
    `code_sha256` fixes the seed the placebo block must have been drawn under. ScreenRefused without a receipt."""
    raise NotImplementedError(_STUB)


def same_lineage(x: Any, u: Any, other_x: Any, other_u: Any, *, same_template: bool = False) -> bool:
    """Step 7: the same template, or E1's `same_lineage` (Pearson on the common Train-era sessions, pairs with a value
    that is not finite dropped, 0.7 or more) on the two residual series OR on the two universe-excess series. Each
    side as E1's function takes it (a `Series`, a mapping {session: value}, or aligned arrays)."""
    raise NotImplementedError(_STUB)


def retry_permitted(receipt: Any = None, **facts: Any) -> bool:
    """Always False under XS1 (the pre-registration's R-g: no Validation-only retry; a program refused at the
    pre-check has spent its lineage's try). Kept so the swarm asks the panel's screen as it asks the share screen's."""
    raise NotImplementedError(_STUB)


def beside_line(result: Mapping[str, Any], receipt: ReceiptXS, *, n_cell: int) -> str:
    """Step 8: the receipt's sentence with `BESIDE_FIELDS` filled from a `verdict` and the House's count of earlier
    XS1 looks in the program's agenda cell. ValueError when a placeholder cannot be filled (the sentence is never
    stated with a hole in it)."""
    raise NotImplementedError(_STUB)


__all__ = ["SCREEN", "RECEIPT_NAME", "RECEIPT_PATH", "CONTRACT", "RECEIPT_KEYS", "PIN_KEYS", "BESIDE_FIELDS",
           "FP_CAP", "OWNER_WALL", "ALPHA_PLAC", "PLACEBO_DRAWS", "PLACEBO_COUNT_MAX", "C_MARGIN", "C_GRID_STEP",
           "K_XS_MAX", "K_MAX", "RUNGS", "H_LENGTH", "V_LENGTH", "MIN_POOL_BOTH", "MIN_POOL_ALONE", "POOL_SKIP",
           "ACTIVITY_ROUND_TRIPS", "ACTIVITY_INVESTED_DAYS", "SAME_LINEAGE_CORR", "LINEAGE_SERIES",
           "LOOKS_PER_LINEAGE", "VALIDATION_TRIES", "ZERO", "BASKET_LABELS", "FRENCH_FACTORS", "FRENCH_MIN_DAYS",
           "FRENCH_T", "UNMEASURED", "STYLE_OPEN", "CHECKPOINTS", "ALPHA_F", "ScreenRefused", "Series", "ReceiptXS",
           "holdout_t", "look_permitted", "receipt_sha256", "pinned_receipt", "load_receipt", "series", "split",
           "windows", "precheck", "floor", "floor_fits", "look", "loadings", "labels", "verdict", "same_lineage",
           "retry_permitted", "beside_line"]
