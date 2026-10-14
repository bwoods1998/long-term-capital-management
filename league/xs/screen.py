"""XS1, the panel screen: the pre-check, the program's own floor, the one look, and the sentence beside every trade.

Owner: package E. `ScreenRefused`, `Series`, `look_permitted` and `holdout_t` are E1's own, re-exported.

THE RULE IS THE PINNED PRE-REGISTRATION, EXACTLY: XSCREEN-1 revision 2 (sha256 c46aec17..., pinned 2026-10-11
03:03:08Z), section 4. Where E4-SPEC section 9 differs (it was revised in parallel without seeing it), the
pre-registration wins. THE THRESHOLDS ARE THE RECEIPT'S, READ AT RUNTIME, NEVER WRITTEN HERE: the study finished and
adopted XS1 by its own mechanical rule (rung R0). THE RECEIPT THE HOUSE RUNS, docs/benchmarks/equity_screen_xs_1.json,
pinned in policy.json `elane.screens.equity_xs`, IS THAT STUDY'S RECEIPT REBUILT AT THE CAPTAIN'S BAR (decision A23):
the threshold of the study's own bias-raised rule (the registered rule with the measured finite-pool bias added to
every real-signal cell), which is above the registered one. The study's own builder wrote it from the study's saved
run; its key `house_bar` says so, and names the registered bar and the registered receipt's sha256. The captain may
replace it again: so no figure of a receipt is a constant of this module (the constants below are the
PRE-REGISTRATION's fixed figures, which every receipt must state, and the loader refuses one that states another).
A SCREEN WITH NO PINNED RECEIPT REFUSES EVERY PROGRAM (`ScreenRefused`); tests use the fixture marked fake
(league/tests/fixtures/equity_screen_xs_fake.json), shaped as the real receipt is (`RECEIPT_KEYS`).

THE CONFORMANCE VECTORS (the study's HOUSE-RULE-XS1, section 9; synthetic inputs, no market data) are committed:
league/tests/fixtures/xs1_conformance.json, the file the study's own vector builder writes at the bar of the receipt
the House runs (the file's `k_XS`; at the registered bar the same builder gives the study's pinned file again), byte
for byte (eight vectors: V1 pass, V2 fail, V3 refused at the pre-check, V4 the stress leg, V5 the own floor, V6
ineligible, CH the characteristics and cells, H the hand vector), and
league/tests/fixtures/xs1_conformance_inputs.npz, the synthetic inputs V1-V6 were computed from
(prices, the eligible set, every lot with its cell, members and leaving sessions, the Train pools) with the study's
plain reference's daily series beside (r, B, x, x15, s, f, w, exits, invested, the universe excess u, and the 999
placebo t's on the holdout). `test_xs_screen.TheStudyVectors` reproduces EVERY integer and verdict exactly and every
float to 1e-12 (the floor from the pools; the pre-check, the look and the verdict from the series and the placebo
t's); `test_xs_placebo.TheStudyVectors` (package D) reproduces the series from the prices and the lots. AND A NINTH,
THE CAPTAIN'S A22 (4): no study vector has a 2022-24 pool of 550 sessions or more alone, which is the House's own
third floor cell ("C": its second Train segment is 753 sessions). It is derived BY HAND (a brute-force loop over
every (Validation block, holdout block) pair of a small synthetic pool, never this module) and committed as
league/tests/fixtures/xs1_conformance_c.json, with a tenth beside it of the House's own shape (pools of 752 and 751
sessions: all three cells, the second segment's binding); `test_xs_screen` holds `floor` to both. Neither
implementation is rewritten to fit the other after the receipt exists. THE VECTORS RUN UNDER THE BAR THEIR OWN FILE
STATES, never a pin's; and CI holds that bar equal to the pinned receipt's (`test_xs_screen.TheCommittedPin`), so a
receipt at another bar lands with its vectors computed again at it.

x is the residual, x15 the stress residual (`league.xs.placebo`), one observation a session.

1. THE WINDOWS (4.1). V = calendar 2025 (250 sessions); H = 2026-01-02..2026-10-09, exactly 194 sessions
   (`league.equity.config.LOOK_FIRST`, `LOOK_CAP`). The look's run starts flat at V's first session and runs through
   H; `split` cuts its series in two. One sealed look a lineage; days after the cap are forward days only.
2. THE PRE-CHECK on V (4.2): (lots fully exited >= 20 or sessions with a lot held at the close >= 120) AND sum_V x >
   1e-12: E1's pre-check on x, its sum taken with `math.fsum` as the study's is. A failed pre-check spends no look,
   and spends the lineage's one Validation try.
3. THE PROGRAM'S OWN FLOOR (4.4), before the look, no look spent when ineligible: S2's exact enumeration applied to
   the residual, at L = 194 ONLY. Pools: the program's own (x, w) on each Train-era span, from its first decision + 2
   sessions to the span's last session. Floor cells: (i) both pools together, when both exist and each has at least
   `MIN_POOL_BOTH` sessions; (ii) each single pool that has at least `MIN_POOL_ALONE`, alone. A world is a holdout
   block of 194 consecutive pool sessions, circular inside one pool, weighted by its number of non-overlapping
   Validation blocks. The null is N0: x0 = x - w x kappa_H. In each cell k_cell = the smallest k in 0..500 with
   HO[k] x 100 <= 12 x T; k_p = the largest k_cell; c_p = k_p / 100. The cells are named as the study names them
   (`FLOOR_CELLS`): "both", "D" (the first Train segment's pool alone) and "C" (the second's alone); on the House's
   two segments (754 and 753 sessions) all three exist. THIS IS NOT `league.equity.screen.floor_s2` (that reads L 194
   and 251 and has no first-span-alone cell), and it calls no private name of E1: THE ENUMERATION IS WRITTEN HERE
   (`_enumerate`), in the study's plain reference's own arithmetic: every block's t by `holdout_t` (the look's and
   the placebos' expression, block by block), every sum and kappa_H by `math.fsum`, every count an integer.
   INELIGIBLE: no floor cell, a cell with T = 0 or with no such k, zero exposure, a series that is not finite, a
   session outside the spans, k_used above 500.
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
   until a route to them exists: the receipt's "style-open" flag then attaches, and the sentence says so). THE SEAT
   RULE IS NOT THIS LABEL'S: the captain's A22 reads style-open from the House's own loadings (`league.xs.style`),
   and a style-open passer takes no live seat on an XS1 pass alone (`league.swarm.elane_xs.look`).
7. LINEAGE (4.6): one look a lineage; the same lineage = the same template, or a Train daily correlation of 0.7 or
   more (`league.equity.screen.same_lineage`) with a program already looked at OR already refused at the pre-check, IN
   EITHER SERIES, the residual x or the universe excess u. No Validation-only retry (`VALIDATION_TRIES` 1). A lineage
   that took an XS1 look can take no S2 look, and the reverse.
8. STATED BESIDE EVERY LIVE PANEL TRADE: the receipt's sentence (`beside_line`), its per-program placeholders
   `BESIDE_FIELDS` filled on the House: {c_used}, {c_p}, {own_fp} (the largest, over the program's floor cells, of
   HO[k_used] / T: in-sample, at most 12% by construction, and said so), {n_cell} (the XS1 looks already taken in the
   program's agenda cell, counted by the House), {basket}, {label}, {flags}. A PASS is never stated with a hole in it
   (ValueError); a verdict that did not pass has no trade to stand beside, and reads "unmeasured" where it lacks a
   figure, so the look's record can always keep its sentence.

Failure order of `verdict` (the first is `why`): no receipt (ScreenRefused); the floor ineligible, or run under other
figures than the receipt's; a run that did not end "ok" at k 1.0 on the receipt's rung, or a placebo block of another
rung, another number of draws or another seed than the receipt and the program's code fix; the windows; the
pre-check; the look. After a receipt, `verdict` never raises: a look is spent by the time it is asked, so whatever it
cannot read fails the program closed, with its reason.

EVERY "POSITIVE" TEST is `> 1e-12` on a sum taken with `math.fsum` (the built-in `sum` is not the same sum on Python
3.11 and 3.14, and the CI runs both); every bar is held in integers (grid steps, counts, exact fractions).

WHAT THE HOUSE HOLDS BEFORE A LOOK, BESIDE THIS MODULE (the captain's A22; `league.swarm.elane_xs.look` keeps them,
never this judge): at most `league.swarm.elane_xs.MAX_CELL_LOOKS` XS1 looks an agenda cell until a forward verdict
exists there; the equity code review (no embedded return table, no calendar recognition) and the contamination probe
before the look; and the style reading above before a seat.

THE FORWARD ROUTE F-GS-XS (the pre-registration's section 11; measured by a later study, read by package J and E6):
checkpoints at `CHECKPOINTS` forward sessions, a pass = t_n >= c_FX AND sum x > 1e-12 AND sum x15 > 1e-12 AND the
placebo rank over the same sessions <= alpha_f, alpha_f = `ALPHA_F`["fresh"] for a lineage that declares the route at
registration (it can never take an XS1 look) and `ALPHA_F`["looked"] after an XS1 look.

Evidence module (in the xs identity; one of its roots; a fixed judge). It imports E1's PUBLIC names of
`league.equity.screen` only, and of this package the constants of `config`, `results.DAILY` and `placebo.LOOK_SEED`.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import re
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from ..equity import config as e1
from ..equity.screen import ScreenRefused, Series, holdout_t, look_permitted
from ..equity.screen import same_lineage as _e1_same_lineage
from . import config
from .placebo import LOOK_SEED
from .results import DAILY

SCREEN = "XS1"
RECEIPT_NAME = "equity_screen_xs_1"
RECEIPT_PATH = "docs/benchmarks/equity_screen_xs_1.json"
CONTRACT = "C-XS-1"
#: The keys a receipt must carry (the pre-registration's 10.1); the loader refuses a receipt that lacks one, and
#: lets a receipt carry more (the study's adds "eligibility" and "beside_calibrated_reading"; the one rebuilt at the
#: captain's bar adds "house_bar" beside them: what it is, the registered bar and receipt, how it was built).
RECEIPT_KEYS = ("name", "screen", "study", "rule", "contract", "fp_cap", "owner_wall", "c_XS", "c_margin",
                "alpha_plac", "placebo_draws", "stratum", "residual", "precheck", "look", "floor", "windows", "lineage",
                "R3_retry_permitted", "labels", "flags", "screen_flags", "ladder", "fp_zero_edge", "fp_zero_edge_B",
                "fp_zero_edge_max", "fp_validation_known_max", "family_wise_zero_edge", "family_wise_8_max",
                "finite_pool_bias", "finite_pool_bias_max", "style_known_rate", "style_known_max", "power",
                "cost_of_rule", "study_program_floors", "limits", "stated_beside_every_live_trade", "note", "sha256")
#: What policy.json `elane.screens.equity_xs` pins, every value copied from the receipt (it ships with nulls, and with
#: nulls every panel look waits).
PIN_KEYS = ("name", "screen", "receipt_sha256", "c_XS", "c_margin", "alpha_plac", "placebo_draws", "rung", "fp_cap",
            "owner_wall", "validation_tries", "holdout_looks", "retry", "flags", "screen_flags", "beside")
#: Where each pinned value sits in the receipt file (a dotted path): what `pinned_receipt` is held equal to
#: (`receipt_sha256` is the sha256 of the file's own bytes).
PIN_SOURCES = {"name": "screen", "screen": "screen", "c_XS": "c_XS", "c_margin": "c_margin",
               "alpha_plac": "alpha_plac", "placebo_draws": "placebo_draws", "rung": "stratum.rung",
               "fp_cap": "fp_cap", "owner_wall": "owner_wall", "validation_tries": "lineage.validation_tries",
               "holdout_looks": "lineage.holdout_looks", "retry": "R3_retry_permitted", "flags": "flags",
               "screen_flags": "screen_flags", "beside": "stated_beside_every_live_trade"}
#: The per-program placeholders of the sentence beside every live trade (the receipt fills its own figures once).
BESIDE_FIELDS = ("c_used", "c_p", "own_fp", "n_cell", "basket", "label", "flags")
#: The receipt's rule-level figures `load_receipt` keeps in `ReceiptXS.fp` (stated beside; never a bar).
FP_KEYS = ("fp_zero_edge_max", "fp_validation_known_max", "family_wise_8_max", "finite_pool_bias_max",
           "style_known_rate", "style_known_max")
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
#: The floor's cells, by the study's names: both pools together, the first Train segment's alone, the second's alone.
FLOOR_CELLS = ("both", "D", "C")
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
#: The French label's two measured readings (the second is followed by the factors that load).
NO_STYLE = "no style loading found"
STYLE_LOADED = "style-loaded: "
#: The receipt's screen-level flag, attached to every panel program whose French label is style-loaded or unmeasured.
STYLE_OPEN = "style-open"
#: THE FORWARD ROUTE (F-GS-XS; read by package J and E6, never by the look).
CHECKPOINTS = (20, 60, 120, 250)
ALPHA_F = {"fresh": 0.12, "looked": 0.03}
#: The floor's method (the receipt's `floor.method`): an exact enumeration, no seeds and no world count.
METHOD = "exact"
#: The c grid, the study's own: c = k / 100 for k = 0..500.
GRID = np.arange(K_MAX + 1) / 100.0
#: The columns of a run's `daily` rows `series` reads as a series.
SERIES_COLUMNS = ("x", "x15", "u", "r")
#: The floor's first reason of ineligibility, in the study's words (its vector V6).
NO_CELL_WHY = "no floor cell"
#: The Newey-West lag of the t reported beside (never a bar).
NW_LAG = 5

_WHO = "the panel screen XS1"
_HEX64 = re.compile(r"[0-9a-f]{64}")
_ISO_DAY = re.compile(r"\d{4}-\d{2}-\d{2}")
_EPOCH = dt.date(1970, 1, 1)


@dataclass(frozen=True)
class ReceiptXS:
    """The pinned XS1 receipt as policy.json carries it (`PIN_KEYS`, copied from the receipt file's keys):
    `receipt_sha256` (the file's bytes, 64 hex), `c_XS` and `c_margin` (on the 0.01 grid), `alpha_plac` (0.12),
    `placebo_draws` (999), `rung` (the adopted stratum: "R0", or "R1" when the ladder fell back), `fp_cap` (0.12),
    `owner_wall` (0.15), `validation_tries` and `holdout_looks` (1 and 1: `lineage`'s), `retry`
    (`R3_retry_permitted`: False), `flags` ({archetype: (flag, ...)}, DR4's), `screen_flags` (("style-open",) or ()),
    `beside` (`stated_beside_every_live_trade`: the sentence, with `BESIDE_FIELDS` as placeholders) and `fp` (the
    receipt's rule-level figures stated beside, `style_known_rate` among them)."""

    receipt_sha256: str
    c_XS: float
    c_margin: float
    alpha_plac: float
    placebo_draws: int
    rung: str
    fp_cap: float
    owner_wall: float
    validation_tries: int
    holdout_looks: int
    retry: bool
    flags: Mapping[str, tuple[str, ...]]
    screen_flags: tuple[str, ...]
    beside: str
    fp: Mapping[str, Any]


class _Ineligible(ValueError):
    """XS1: the program has no floor (it cannot be looked at)."""


# ------------------------------------------------------------------------------------------------------ small readers
def _number(value: Any, lo: float, hi: float) -> float | None:
    """A finite real number in [lo, hi] (never a bool), else None."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    v = float(value)
    return v if math.isfinite(v) and lo <= v <= hi else None


def _whole(value: Any) -> int | None:
    """An integer (never a bool; a float only when it is whole), else None."""
    if isinstance(value, bool) or not isinstance(value, (int, float, np.integer)):
        return None
    if isinstance(value, float) and not (math.isfinite(value) and value == int(value)):
        return None
    return int(value)


def _on_grid(value: Any, k_max: int = K_MAX) -> float | None:
    """A number on the 0.01 grid in [0, k_max / 100], else None."""
    v = _number(value, 0.0, k_max / 100.0)
    if v is None or abs(v * 100.0 - round(v * 100.0)) > 1e-9:
        return None
    return v


def _k(c: float) -> int:
    """A grid threshold as its integer step k = 100 c."""
    return int(round(float(c) * 100.0))


def _fraction(value: Any, what: str) -> Fraction:
    """A rate in (0, 1) as the exact fraction its decimal figure names (0.12 is 3 / 25): what a bar is held on."""
    v = _number(value, 0.0, 1.0)
    if v is None or not 0.0 < v < 1.0:
        raise ValueError(f"{what} must lie in (0, 1): {value!r}")
    return Fraction(str(v))


def _flags(value: Any) -> dict[str, tuple[str, ...]] | None:
    """The receipt's flags as {archetype: (flag, ...)}, None when malformed (a flag must never be lost to a bad
    shape)."""
    if not isinstance(value, Mapping):
        return None
    out: dict[str, tuple[str, ...]] = {}
    for key, flags in value.items():
        if not isinstance(key, str) or isinstance(flags, (str, bytes)) or not isinstance(flags, Sequence):
            return None
        if not all(isinstance(f, str) for f in flags):
            return None
        out[key] = tuple(flags)
    return out


def _ordinal(day: Any) -> int:
    """A session as an int32 ordinal since 1970-01-01 (`league.equity.store.ordinal`): from an ordinal, a date or an
    ISO string."""
    if isinstance(day, (int, np.integer)) and not isinstance(day, bool):
        return int(day)
    if isinstance(day, dt.datetime):
        day = day.date()
    if isinstance(day, dt.date):
        return (day - _EPOCH).days
    if isinstance(day, str):
        try:
            return (dt.date.fromisoformat(day[:10]) - _EPOCH).days
        except ValueError:
            pass
    raise ValueError(f"not a session day: {day!r}")


def _iso(value: int) -> str:
    return (_EPOCH + dt.timedelta(days=int(value))).isoformat()


def _fsum(values: Any) -> float:
    """The exact sum of a float array (`math.fsum`): one sum on every Python. NaN where there is none (a value that is
    not finite, or a sum past the largest float): a sum that is no number is never "above zero"."""
    try:
        return math.fsum(np.asarray(values, dtype=np.float64).ravel().tolist())
    except (OverflowError, ValueError):
        return math.nan


def _stated(total: float) -> float | None:
    """A sum as a result states it: None where there is none (a record never holds a NaN)."""
    return total if math.isfinite(total) else None


# ------------------------------------------------------------------------------------------------------- the receipt
def receipt_sha256(path: str | Path) -> str | None:
    """sha256 of the receipt file's bytes (64 hex), or None when there is no such file."""
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def _pin(block: Any) -> ReceiptXS | str:
    """A pin read whole or not at all: the receipt, or the first reason it is none (`pinned_receipt`'s None;
    `load_receipt` says it)."""
    if not isinstance(block, Mapping):
        return "no pin block"
    if block.get("screen") != SCREEN or block.get("name") != SCREEN:
        return f"the pin names screen {block.get('screen')!r} / {block.get('name')!r}, not {SCREEN}"
    sha = block.get("receipt_sha256")
    if not isinstance(sha, str) or not _HEX64.fullmatch(sha):
        return "no receipt sha256 is pinned"
    c_xs, c_margin = _on_grid(block.get("c_XS"), K_XS_MAX), _on_grid(block.get("c_margin"))
    if c_xs is None:
        return f"c_XS {block.get('c_XS')!r} is not on the 0.01 grid in 0.00..{K_XS_MAX / 100:.2f}"
    if c_margin is None or _k(c_margin) < _k(C_MARGIN):
        return f"c_margin {block.get('c_margin')!r} is not on the 0.01 grid at or above {C_MARGIN}"
    rates = {}
    for key, cap in (("alpha_plac", ALPHA_PLAC), ("fp_cap", FP_CAP), ("owner_wall", OWNER_WALL)):
        v = _number(block.get(key), 0.0, 1.0)
        if v is None or not 0.0 < v <= cap + ZERO:
            return f"{key} {block.get(key)!r} is not in (0, {cap}]"
        rates[key] = v
    if rates["fp_cap"] > rates["owner_wall"] + ZERO:
        return f"fp_cap {rates['fp_cap']} is above the owner's wall {rates['owner_wall']}"
    if _whole(block.get("placebo_draws")) != PLACEBO_DRAWS:
        return f"placebo_draws {block.get('placebo_draws')!r} is not {PLACEBO_DRAWS}"
    rung = block.get("rung")
    if not isinstance(rung, str) or rung not in RUNGS or rung not in config.RUNGS:
        return f"rung {rung!r} is not one of {', '.join(RUNGS)}"
    if _whole(block.get("validation_tries")) != VALIDATION_TRIES:
        return f"validation_tries {block.get('validation_tries')!r} is not {VALIDATION_TRIES}"
    if _whole(block.get("holdout_looks")) != LOOKS_PER_LINEAGE:
        return f"holdout_looks {block.get('holdout_looks')!r} is not {LOOKS_PER_LINEAGE}"
    if block.get("retry") is not False:
        return "a Validation-only retry is not false (XS1 has none)"
    flags = _flags(block.get("flags"))
    if flags is None:
        return "the flags are malformed"
    raw = block.get("screen_flags")
    if isinstance(raw, (str, bytes)) or not isinstance(raw, Sequence) or len(raw) > 1 \
            or not all(isinstance(f, str) and f == STYLE_OPEN for f in raw):
        return f"the screen flags are not () or ({STYLE_OPEN!r},)"
    beside = block.get("beside")
    if not isinstance(beside, str):
        return "the sentence beside every live trade is missing"
    lacking = [f for f in BESIDE_FIELDS if "{" + f + "}" not in beside]
    if lacking:
        return f"the sentence beside every live trade lacks {{{'}, {'.join(lacking)}}}"
    fp = block.get("fp")
    return ReceiptXS(receipt_sha256=sha, c_XS=c_xs, c_margin=c_margin, alpha_plac=rates["alpha_plac"],
                     placebo_draws=PLACEBO_DRAWS, rung=str(rung), fp_cap=rates["fp_cap"],
                     owner_wall=rates["owner_wall"], validation_tries=VALIDATION_TRIES,
                     holdout_looks=LOOKS_PER_LINEAGE, retry=False, flags=flags, screen_flags=tuple(raw),
                     beside=beside, fp=dict(fp) if isinstance(fp, Mapping) else {})


def pinned_receipt(block: Mapping[str, Any] | None) -> ReceiptXS | None:
    """The receipt as policy.json pins it (`elane.screens.equity_xs`), or None: a block of nulls, a missing or
    malformed value, a figure the pre-registration does not allow. None refuses every look.

    A pin is read whole or not at all: `screen` and `name` "XS1"; a 64-hex `receipt_sha256`; `c_XS` on the 0.01 grid
    in 0.00..3.00; `c_margin` on the grid and at least `C_MARGIN` (the bar may be made narrower, never wider);
    `alpha_plac`, `fp_cap` and `owner_wall` in (0, the pre-registration's figure], the cap never above the wall;
    `placebo_draws` `PLACEBO_DRAWS`; `rung` one of `RUNGS`; one Validation try and one look a lineage; `retry` a
    literal false; well-formed `flags`; `screen_flags` () or ("style-open",); the sentence with every placeholder of
    `BESIDE_FIELDS`."""
    got = _pin(block)
    return got if isinstance(got, ReceiptXS) else None


def _read(path: str | Path, *, pinned: bool, pinned_sha256: Any = None) -> tuple[Mapping[str, Any], str]:
    """A receipt file's JSON object and sha256; `pinned`: refused unless its bytes are the ones `pinned_sha256` names
    (64 hex: a pin that is none refuses, it never reads as "any file")."""
    if pinned and (not isinstance(pinned_sha256, str) or not _HEX64.fullmatch(pinned_sha256)):
        raise ScreenRefused(f"{_WHO} refuses: no receipt sha256 is pinned")
    try:
        raw = Path(path).read_bytes()
    except OSError as exc:
        raise ScreenRefused(f"{_WHO} refuses: the receipt {path} cannot be read ({exc})") from exc
    sha = hashlib.sha256(raw).hexdigest()
    if pinned and sha != pinned_sha256:
        raise ScreenRefused(f"{_WHO} refuses: the receipt's sha256 {sha[:12]} is not the pinned {pinned_sha256[:12]}")
    try:
        doc = json.loads(raw)
    except ValueError as exc:
        raise ScreenRefused(f"{_WHO} refuses: the receipt is not JSON ({exc})") from exc
    if not isinstance(doc, Mapping):
        raise ScreenRefused(f"{_WHO} refuses: the receipt is not an object")
    return doc, sha


def _dig(doc: Mapping[str, Any], source: str) -> Any:
    """The value at a dotted path of the receipt (`PIN_SOURCES`); ScreenRefused when the path is not there."""
    value: Any = doc
    for part in source.split("."):
        if not isinstance(value, Mapping) or part not in value:
            raise ScreenRefused(f"{_WHO} refuses: the receipt lacks {source}")
        value = value[part]
    return value


def _pin_of(doc: Mapping[str, Any], sha: str) -> dict[str, Any]:
    block: dict[str, Any] = {}
    for key in PIN_KEYS:
        block[key] = sha if key == "receipt_sha256" else _dig(doc, PIN_SOURCES[key])
    return block


def pin(path: str | Path) -> dict[str, Any]:
    """What policy.json `elane.screens.equity_xs` pins for the receipt file at `path`: `PIN_KEYS` in order, each
    value copied from the place `PIN_SOURCES` names, `receipt_sha256` the sha256 of the file's bytes. The
    INTEGRATOR's one call when the receipt lands (and CI's: `test_xs_screen.TheCommittedPin` holds the committed block
    equal to it). ScreenRefused for a file that cannot be read, is no JSON object or lacks a pinned value; whether
    the pin is one this screen runs is `pinned_receipt`'s to say."""
    doc, sha = _read(path, pinned=False)
    return _pin_of(doc, sha)


def load_receipt(path: str | Path, *, pinned_sha256: str) -> ReceiptXS:
    """The receipt file, verified against its pin. ScreenRefused on: a sha that is not the pin's; a missing key of
    `RECEIPT_KEYS`; a `screen` other than "XS1" or a `contract` other than `CONTRACT`; c_XS or c_margin off the 0.01
    grid, c_XS outside 0..3.00; alpha_plac above `ALPHA_PLAC`; fp_cap above `FP_CAP`; an owner_wall above
    `OWNER_WALL`; placebo_draws other than `PLACEBO_DRAWS`; a rung outside `RUNGS`; `lineage.validation_tries` other
    than `VALIDATION_TRIES` or `lineage.holdout_looks` other than `LOOKS_PER_LINEAGE`; `R3_retry_permitted` true; a
    sentence that lacks a placeholder of `BESIDE_FIELDS`. A key beyond `RECEIPT_KEYS` is not refused.

    AND A RECEIPT THAT STATES ANOTHER RULE THAN THIS CODE RUNS: a pre-check other than `ACTIVITY_ROUND_TRIPS` round
    trips or `ACTIVITY_INVESTED_DAYS` invested days; a floor that is not the exact enumeration; a calibrated holdout
    other than `H_LENGTH` sessions from `league.equity.config.LOOK_FIRST` through `LOOK_CAP`; lineage series other
    than `LINEAGE_SERIES`; a stratum whose window, valid-return minimum, smallest cell, funds or market are not
    `league.xs.config`'s (the residual and every placebo are drawn under that stratum)."""
    doc, sha = _read(path, pinned=True, pinned_sha256=pinned_sha256)
    missing = [k for k in RECEIPT_KEYS if k not in doc]
    if missing:
        raise ScreenRefused(f"{_WHO} refuses: the receipt lacks {', '.join(missing)}")
    if doc["screen"] != SCREEN:
        raise ScreenRefused(f"{_WHO} refuses: the receipt is for screen {doc['screen']!r}, not {SCREEN}")
    contract = doc["contract"]
    if (contract.get("name") if isinstance(contract, Mapping) else contract) != CONTRACT:
        raise ScreenRefused(f"{_WHO} refuses: the receipt's contract is not {CONTRACT}")
    if not isinstance(doc["R3_retry_permitted"], bool):
        raise ScreenRefused(f"{_WHO} refuses: the receipt's R3_retry_permitted is not a bool")

    def part(key: str) -> Mapping[str, Any]:
        return doc[key] if isinstance(doc[key], Mapping) else {}

    pre, lineage, fl, windows, stratum = (part(k) for k in ("precheck", "lineage", "floor", "windows", "stratum"))
    if pre.get("rt_min") != ACTIVITY_ROUND_TRIPS or pre.get("id_min") != ACTIVITY_INVESTED_DAYS:
        raise ScreenRefused(f"{_WHO} refuses: the receipt states another pre-check than this code")
    if fl.get("method") != METHOD:
        raise ScreenRefused(f"{_WHO} refuses: the receipt's floor is not the exact enumeration")
    days = _ISO_DAY.findall(str(windows.get("holdout") or ""))
    if days[:2] != [e1.LOOK_FIRST.isoformat(), e1.LOOK_CAP.isoformat()] or windows.get("calibrated_L") != H_LENGTH:
        raise ScreenRefused(f"{_WHO} refuses: the receipt's holdout is not the {H_LENGTH} sessions "
                            f"{e1.LOOK_FIRST}..{e1.LOOK_CAP}")
    series_ = lineage.get("series")
    if isinstance(series_, (str, bytes)) or not isinstance(series_, Sequence) or tuple(series_) != LINEAGE_SERIES:
        raise ScreenRefused(f"{_WHO} refuses: the receipt's lineage series are not {', '.join(LINEAGE_SERIES)}")
    funds = stratum.get("funds")
    funds = tuple(funds) if isinstance(funds, Sequence) and not isinstance(funds, (str, bytes)) else None
    if (stratum.get("window"), stratum.get("min_valid"), stratum.get("min_cell"), funds, stratum.get("market")) != (
            config.WINDOW, config.MIN_VALID, config.MIN_CELL, config.FUNDS, config.REF[config.MARKET_COLUMN]):
        raise ScreenRefused(f"{_WHO} refuses: the receipt's stratum is not the one league/xs/config.py draws")
    got = _pin({**_pin_of(doc, sha), "fp": {key: doc[key] for key in FP_KEYS}})
    if not isinstance(got, ReceiptXS):
        raise ScreenRefused(f"{_WHO} refuses: {got}")
    return got


# -------------------------------------------------------------------------------------------- the series and windows
def _column(result: Any, column: str) -> Series:
    """One column of a run's `daily` rows as a `Series` (the module's reader: `series` names the columns a caller may
    ask)."""
    rows = result.get("daily") if isinstance(result, Mapping) else None
    if isinstance(rows, (str, bytes)) or not isinstance(rows, Sequence) or len(rows) == 0:
        raise ValueError("a result without its daily rows")
    at = {name: DAILY.index(name) for name in ("day", column, "w", "exits", "invested")}
    n = len(rows)
    days = np.empty(n, dtype=np.int64)
    values, w = np.empty(n), np.empty(n)
    exits = np.empty(n, dtype=np.int64)
    invested = np.empty(n, dtype=bool)
    for i, row in enumerate(rows):
        if isinstance(row, (str, bytes)) or not isinstance(row, Sequence) or len(row) != len(DAILY):
            raise ValueError(f"daily row {i} is not the {len(DAILY)} columns of a run's daily series")
        days[i] = _ordinal(row[at["day"]])
        for name, into in ((column, values), ("w", w)):
            cell = row[at[name]]
            if isinstance(cell, bool) or not isinstance(cell, (int, float, np.integer, np.floating)) \
                    or not math.isfinite(float(cell)):
                raise ValueError(f"daily row {i}: {name} is not a finite number ({cell!r})")
            into[i] = float(cell)
        count, held = _whole(row[at["exits"]]), row[at["invested"]]
        if count is None or count < 0:
            raise ValueError(f"daily row {i}: exits is not a count ({row[at['exits']]!r})")
        if not isinstance(held, (bool, np.bool_)) and held not in (0, 1):
            raise ValueError(f"daily row {i}: invested is not a flag ({held!r})")
        exits[i], invested[i] = count, bool(held)
    if n > 1 and not (np.diff(days) > 0).all():
        raise ValueError("the daily rows are not one a session, oldest first")
    return Series(days=days.astype(np.int32), r=values, w=w, b=np.zeros(n), exits=exits, invested=invested)


def series(result: Mapping[str, Any], column: str = "x") -> Series:
    """A run's daily series as E1's `Series`: `days` the run's sessions, `r` the named column of `result["daily"]`
    ("x" the residual, "x15" the stress residual, "u" the universe excess, "r" the raw P&L), `w` the exposure, `b` 0,
    `exits`, `invested`. ValueError (fail closed) on a result without its daily rows or with a value that is not
    finite, on a column that is none of the four, and on rows that are not one a session, oldest first."""
    if column not in SERIES_COLUMNS:
        raise ValueError(f"no series {column!r} (one of {', '.join(SERIES_COLUMNS)})")
    return _column(result, column)


def _take(s: Series, keep: np.ndarray) -> Series:
    return Series(days=np.asarray(s.days)[keep], r=np.asarray(s.r, dtype=np.float64)[keep],
                  w=np.asarray(s.w, dtype=np.float64)[keep], b=np.asarray(s.b, dtype=np.float64)[keep],
                  exits=np.asarray(s.exits)[keep], invested=np.asarray(s.invested, dtype=bool)[keep])


def _window_ordinals() -> tuple[int, int, int, int]:
    v_first, v_last = e1.WINDOWS["validation"]
    return _ordinal(v_first), _ordinal(v_last), _ordinal(e1.LOOK_FIRST), _ordinal(e1.LOOK_CAP)


def split(s: Series) -> tuple[Series, Series]:
    """The look run's series cut into (V, H) by `league.equity.config.WINDOWS["validation"]` and `LOOK_FIRST`..
    `LOOK_CAP`. ValueError when a session lies in neither."""
    if len({len(s.days), len(s.r), len(s.w), len(s.b), len(s.exits), len(s.invested)}) != 1:
        raise ValueError("a series whose arrays differ in length")
    days = np.asarray(s.days, dtype=np.int64)
    v0, v1, h0, h1 = _window_ordinals()
    in_v, in_h = (days >= v0) & (days <= v1), (days >= h0) & (days <= h1)
    stray = ~(in_v | in_h)
    if stray.any():
        raise ValueError(f"{int(stray.sum())} session(s) in neither Validation nor the holdout (the first: "
                         f"{_iso(days[int(np.argmax(stray))])})")
    return _take(s, in_v), _take(s, in_h)


def windows(v: Series, h: Series) -> dict[str, Any]:
    """{ok, why, validation: {first, last, sessions}, holdout: {...}}: V is 2025's `V_LENGTH` sessions and H exactly
    `H_LENGTH` sessions from `LOOK_FIRST` through `LOOK_CAP`, sharing no session."""
    v0, v1, h0, h1 = _window_ordinals()

    def facts(s: Series) -> tuple[np.ndarray, dict[str, Any]]:
        days = np.asarray(s.days, dtype=np.int64)
        n = len(days)
        return days, {"first": _iso(days[0]) if n else None, "last": _iso(days[-1]) if n else None, "sessions": n}

    (dv, fv), (dh, fh) = facts(v), facts(h)
    why = None
    if len(dv) != V_LENGTH or dv.min() < v0 or dv.max() > v1 or not (np.diff(dv) > 0).all():
        why = f"the Validation series is not calendar 2025's {V_LENGTH} sessions ({len(dv)})"
    elif len(dh) != H_LENGTH or dh.min() < h0 or dh.max() > h1 or not (np.diff(dh) > 0).all():
        why = f"the holdout is not the {H_LENGTH} sessions {e1.LOOK_FIRST}..{e1.LOOK_CAP} ({len(dh)})"
    elif set(dv.tolist()) & set(dh.tolist()):
        why = "Validation and the holdout share a session"
    return {"ok": why is None, "why": why, "validation": fv, "holdout": fh}


# ------------------------------------------------------------------------------------------------ step 2: the pre-check
def precheck(v: Series) -> dict[str, Any]:
    """Step 2 on Validation (E1's `precheck` on the residual): {passed, round_trips, invested_days, sum, sessions,
    checks {activity, sum_positive}}. The sum is `math.fsum`'s (the study's)."""
    rt = int(np.sum(np.asarray(v.exits, dtype=np.int64)))
    inv = int(np.sum(np.asarray(v.invested, dtype=bool)))
    total = _fsum(v.r)
    checks = {"activity": rt >= ACTIVITY_ROUND_TRIPS or inv >= ACTIVITY_INVESTED_DAYS,
              "sum_positive": bool(total > ZERO)}
    return {"passed": all(checks.values()), "round_trips": rt, "invested_days": inv, "sum": _stated(total),
            "sessions": len(v.r), "checks": checks}


# ------------------------------------------------------------------------------------- step 3: the program's own floor
def _span(days: np.ndarray) -> int | None:
    """The index of the Train-era span (`league.equity.config.TRAIN_ERA_SEGMENTS`: the pre-registration's 2016-19 and
    2022-24) holding every one of `days`, None when they leave it."""
    lo, hi = int(days.min()), int(days.max())
    for k, (first, last) in enumerate(e1.TRAIN_ERA_SEGMENTS):
        if _ordinal(first) <= lo and hi <= _ordinal(last):
            return k
    return None


def _pools(segments: Sequence[Series | None]) -> dict[int, tuple[np.ndarray, np.ndarray]]:
    """The program's pools (x, w) by Train-era span index: each series placed by its days, never by its position,
    from `POOL_SKIP` to its end. _Ineligible for a series that leaves the spans or two series for one span;
    ValueError for arrays of unequal length or sessions out of order."""
    placed: dict[int, Series] = {}
    for s in segments:
        if s is None or len(s.days) == 0:
            continue
        if len({len(s.days), len(s.r), len(s.w), len(s.b), len(s.exits), len(s.invested)}) != 1:
            raise ValueError("a series whose arrays differ in length")
        days = np.asarray(s.days, dtype=np.int64)
        if not (np.diff(days) > 0).all():
            raise ValueError("a series whose sessions are not one a row, oldest first")
        k = _span(days)
        if k is None:
            spans = ", ".join(f"{a}..{b}" for a, b in e1.TRAIN_ERA_SEGMENTS)
            raise _Ineligible(f"a session outside the Train-era spans ({spans})")
        if k in placed:
            raise _Ineligible("two series for one Train-era span")
        placed[k] = s
    return {k: (np.ascontiguousarray(s.r, dtype=np.float64)[POOL_SKIP:],
                np.ascontiguousarray(s.w, dtype=np.float64)[POOL_SKIP:]) for k, s in placed.items()}


def _cells(pools: Mapping[int, tuple[np.ndarray, np.ndarray]]) -> dict[str, list[tuple[np.ndarray, np.ndarray]]]:
    """The program's floor cells in `FLOOR_CELLS`' order: both pools together (each at least `MIN_POOL_BOTH`), the
    first span's alone and the second's alone (each at least `MIN_POOL_ALONE`)."""
    first, second = pools.get(0), pools.get(1)
    n_first = 0 if first is None else len(first[0])
    n_second = 0 if second is None else len(second[0])
    out: dict[str, list[tuple[np.ndarray, np.ndarray]]] = {}
    if first is not None and second is not None and n_first >= MIN_POOL_BOTH and n_second >= MIN_POOL_BOTH:
        out[FLOOR_CELLS[0]] = [first, second]
    if first is not None and n_first >= MIN_POOL_ALONE:
        out[FLOOR_CELLS[1]] = [first]
    if second is not None and n_second >= MIN_POOL_ALONE:
        out[FLOOR_CELLS[2]] = [second]
    return out


def _tuple_weights(lens: Sequence[int], L: int = H_LENGTH, lv: int = V_LENGTH) -> tuple[list[int], int]:
    """Per pool: W = the number of Validation blocks (`lv` sessions, circular inside one pool) sharing no session with
    one holdout block (`L` sessions) of that pool: every block of the other pools that hold one, and in its own pool
    of n sessions the n - lv - L + 1 that fit beside it. T = the (V, H) pairs of the cell."""
    nv = [n if n >= lv else 0 for n in lens]
    weights = []
    for k, n in enumerate(lens):
        same = max(0, n - lv - L + 1) if (n >= lv and n >= L) else 0
        weights.append(sum(nv) - nv[k] + same if n >= L else 0)
    return weights, sum(n * weights[k] for k, n in enumerate(lens) if n >= L)


def _grid_index(t: float | None) -> int:
    """The largest k in 0..`K_MAX` with k / 100 <= t, or -1 (an undefined or negative t)."""
    if t is None or not t >= 0.0:
        return -1
    return int(np.searchsorted(GRID, t, side="right") - 1)


def _enumerate(pools: Sequence[tuple[np.ndarray, np.ndarray]], *, L: int = H_LENGTH,
               lv: int = V_LENGTH) -> tuple[np.ndarray, int, float, list[int]]:
    """One floor cell, exactly: (HO, T, kappa_H, W). HO[k] for k = 0..500 = the weight of the holdout blocks (every
    start of every pool, `L` consecutive sessions, circular inside the pool, weighted by its pool's W) with sum x0 >
    1e-12 AND a defined t AND t >= k / 100, on the null N0: x0 = x - w kappa_H, kappa_H = sum_k W_k sum(x_k) / sum_k
    W_k sum(w_k). The study's plain reference's arithmetic: `math.fsum` for every sum, `holdout_t` for every block's
    t. `L` and `lv` shrink the blocks for the brute-force tests. _Ineligible on a series that is not finite, on no
    (V, H) pair, and on no exposure."""
    if not all(np.isfinite(x).all() and np.isfinite(w).all() for x, w in pools):
        raise _Ineligible("the pool series are not finite")
    lens = [len(x) for x, _ in pools]
    weights, total = _tuple_weights(lens, L, lv)
    if total <= 0:
        raise _Ineligible("no valid (V, H) tuple")
    exposure = _fsum([weights[k] * _fsum(w) for k, (_, w) in enumerate(pools)])
    total_x = _fsum([weights[k] * _fsum(x) for k, (x, _) in enumerate(pools)])
    if not (math.isfinite(exposure) and math.isfinite(total_x)):
        raise _Ineligible("the pool series are not finite")
    if not exposure > 0:
        raise _Ineligible("no exposure in the pool (kappa is undefined)")
    kappa = total_x / exposure
    if not math.isfinite(kappa):
        raise _Ineligible("the pool series are not finite")
    hits = np.zeros(K_MAX + 1, dtype=np.int64)
    for k, (x, w) in enumerate(pools):
        n = lens[k]
        if n < L:
            continue
        x0 = x - w * kappa
        twice = np.concatenate([x0, x0])            # a circular block is one contiguous run of the doubled pool
        for start in range(n):
            block = twice[start:start + L]
            t = holdout_t(block)
            g = _grid_index(t if t is not None and _fsum(block) > ZERO else None)
            if g >= 0:
                hits[g] += weights[k]
    # HO[k] = the weight of the blocks whose grid index is at least k
    return hits[::-1].cumsum()[::-1], total, kappa, weights


def floor(segments: Sequence[Series | None], *, receipt: ReceiptXS) -> dict[str, Any]:
    """Step 3: the program's own floor from its Train-era residual series (one `Series` per `config.TRAIN_SEGMENTS`
    entry, `r` = x; None or empty where it has none). Deterministic: an exact enumeration, no seed. -> {screen "XS1",
    eligible, why, method "exact", L 194, c_p, k_p, c_used, k_used, own_fp, fp_cap, c_XS, c_margin (as run:
    `floor_fits` checks them against the receipt), cells {"both" | "D" | "C" (`FLOOR_CELLS`): {pools [lengths], T,
    k_cell, kappa_H, HO_0, HO_used}}} (the conformance vectors' integers: T, k_cell, HO[0], HO[k_used]).
    Computed on the House, never committed. ScreenRefused without a receipt; ValueError on arrays of unequal length.

    A series is placed by its days in the pre-registration's Train-era spans (`league.equity.config
    .TRAIN_ERA_SEGMENTS`; the House's own Train segments lie inside them), and its pool starts `POOL_SKIP` sessions in.
    INELIGIBLE (eligible False, `why`, no cells): no floor cell; a cell with no (V, H) pair, no exposure, a value
    that is not finite or no k on 0..500 holding the cap; a session outside the spans or two series for one span;
    k_used above `K_MAX` (k_p and c_p are then stated)."""
    if not isinstance(receipt, ReceiptXS):
        raise ScreenRefused(f"{_WHO} refuses: no receipt is pinned (a floor needs one)")
    cap = _fraction(receipt.fp_cap, "fp_cap")
    out: dict[str, Any] = {"screen": SCREEN, "eligible": False, "why": None, "method": METHOD, "L": H_LENGTH,
                           "c_p": None, "k_p": None, "c_used": None, "k_used": None, "own_fp": None,
                           "fp_cap": receipt.fp_cap, "c_XS": receipt.c_XS, "c_margin": receipt.c_margin, "cells": {}}
    try:
        cells = _cells(_pools(segments))
        if not cells:
            raise _Ineligible(NO_CELL_WHY)
        found: dict[str, tuple[np.ndarray, int]] = {}
        for name, pools in cells.items():
            try:
                ho, total, kappa, _ = _enumerate(pools)
            except _Ineligible as exc:
                raise _Ineligible(f"cell {name}: {exc}") from None
            holds = ho * cap.denominator <= cap.numerator * total
            if not holds.any():
                raise _Ineligible(f"cell {name}: no k on 0..{K_MAX} holds the holdout-only rate at "
                                  f"{float(cap) * 100:g}%")
            found[name] = (ho, total)
            out["cells"][name] = {"pools": [len(x) for x, _ in pools], "T": int(total),
                                  "k_cell": int(np.argmax(holds)), "kappa_H": kappa, "HO_0": int(ho[0]),
                                  "HO_used": None}
        k_p = max(cell["k_cell"] for cell in out["cells"].values())
        k_used = max(_k(receipt.c_XS), k_p + _k(receipt.c_margin))
        out.update(k_p=k_p, c_p=k_p / 100)
        if k_used > K_MAX:
            raise _Ineligible(f"k_used > {K_MAX} (c_used {k_used / 100:.2f} is off the grid)")
        for name, (ho, total) in found.items():
            out["cells"][name]["HO_used"] = int(ho[k_used])
        out.update(eligible=True, k_used=k_used, c_used=k_used / 100,
                   own_fp=max(cell["HO_used"] / cell["T"] for cell in out["cells"].values()))
    except _Ineligible as exc:
        out["why"] = str(exc)
        out["cells"] = {}
    return out


def _floor_misfit(program_floor: Mapping[str, Any], receipt: ReceiptXS) -> str | None:
    """Why a floor was not run by this receipt (None when it was): another screen, method or L, or another fp_cap,
    c_XS or c_margin than the receipt's. Eligibility is not judged here."""
    fl = program_floor
    if fl.get("screen") != SCREEN:
        return f"not an XS1 floor ({fl.get('screen') or 'none'})"
    if fl.get("method") != METHOD or fl.get("L") != H_LENGTH:
        return f"not an exact floor at L {H_LENGTH} ({fl.get('method')!r}, L {fl.get('L')!r})"
    for key in ("fp_cap", "c_XS", "c_margin"):
        ran = _number(fl.get(key), 0.0, K_MAX / 100.0)
        if ran is None or abs(ran - float(getattr(receipt, key))) > ZERO:
            return f"run at {key} {fl.get(key)!r}, the receipt's is {getattr(receipt, key)}"
    return None


def floor_fits(program_floor: Any, receipt: Any) -> bool:
    """Whether a (cached) floor was run by this receipt's figures (fp_cap, c_XS, c_margin, L), eligible or not; False
    for anything else (run the floor again)."""
    if not isinstance(program_floor, Mapping) or "eligible" not in program_floor or not isinstance(receipt, ReceiptXS):
        return False
    return _floor_misfit(program_floor, receipt) is None


def _floor_reading(program_floor: Any, receipt: ReceiptXS) -> tuple[str | None, int | None, int | None, float | None]:
    """(why the floor judges nothing or None, k_p, k_used, own_fp): an eligible exact XS1 floor run at the receipt's
    figures, whose k_used is max(k_XS, k_p + the margin) AGAIN from its k_p and the RECEIPT's own figures (a floor, or
    a cached copy, whose k_used is another number judges nothing)."""
    fl = program_floor if isinstance(program_floor, Mapping) else {}
    if fl.get("screen") == SCREEN and fl.get("eligible") is not True:
        return str(fl.get("why") or "not eligible"), None, None, None
    why = _floor_misfit(fl, receipt)
    if why is not None:
        return why, None, None, None
    k_p, used = _whole(fl.get("k_p")), _whole(fl.get("k_used"))
    if k_p is None or not 0 <= k_p <= K_MAX:
        return f"k_p {fl.get('k_p')!r} is not a grid step", None, None, None
    k_used = max(_k(receipt.c_XS), k_p + _k(receipt.c_margin))
    if k_used > K_MAX or used != k_used:
        return (f"k_used {fl.get('k_used')!r} is not max(k_XS, k_p + the margin) on 0..{K_MAX} "
                f"(k_p {k_p})"), None, None, None
    own = _number(fl.get("own_fp"), 0.0, 1.0)
    if own is None:
        return f"own_fp {fl.get('own_fp')!r} is not a rate", None, None, None
    return None, k_p, k_used, own


# -------------------------------------------------------------------------------------------------- step 5: the look
def _placebo_count(t: float | None, placebo_t: Sequence[float | None]) -> int | None:
    """#{m : placebo_t[m] >= t}: an undefined placebo t (None, or not finite) counts as not above; None when `t`
    itself is undefined. ValueError for a placebo t that is neither a number nor None."""
    count = 0
    for value in placebo_t:
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float, np.integer, np.floating)):
            raise ValueError(f"a placebo t that is no number: {value!r}")
        m = float(value)
        if t is not None and math.isfinite(m) and m >= t:
            count += 1
    return None if t is None else count


def look(v: Series, h: Series, *, h15: Series, c_used: float, placebo_t: Sequence[float | None],
         alpha: float = ALPHA_PLAC) -> dict[str, Any]:
    """Step 5 after the one look: {passed, t_H, sum_h, sum_h15, count, n_placebo, p_plac, c_used, checks {precheck,
    sum_h, sum_h15, t_H, placebo}}. `h15`: the stress residual on H; `placebo_t`: the placebos' t on H's sessions
    (None where undefined: not above). The placebo bar is held in integers.

    Also `grid_index` (the largest k with k / 100 <= t_H, -1 when there is none) and `precheck_result` (step 2's own
    answer on V). The t bar is held on the grid: t_H >= k_used / 100 with k_used = 100 c_used. ValueError for a
    `c_used` off the 0.01 grid, an `alpha` outside (0, 1), a stress series on other sessions than H's, or a placebo t
    that is neither a number nor None."""
    c = _on_grid(c_used)
    if c is None:
        raise ValueError(f"c_used must lie on the 0.01 grid in 0.00..{K_MAX / 100:.2f}: {c_used!r}")
    bar = _fraction(alpha, "alpha")
    if len(h15.days) != len(h.days) or not np.array_equal(np.asarray(h15.days), np.asarray(h.days)):
        raise ValueError("the stress residual is not on the holdout's own sessions")
    pre = precheck(v)
    xh = np.ascontiguousarray(h.r, dtype=np.float64)
    sum_h, sum_h15 = _fsum(xh), _fsum(h15.r)
    t_h = holdout_t(xh)
    g = _grid_index(t_h)
    n = len(placebo_t)
    count = _placebo_count(t_h, placebo_t)
    ranked = count is not None and n > 0
    checks = {"precheck": bool(pre["passed"]), "sum_h": bool(sum_h > ZERO), "sum_h15": bool(sum_h15 > ZERO),
              "t_H": g >= _k(c),
              "placebo": ranked and (1 + count) * bar.denominator <= bar.numerator * (n + 1)}
    return {"passed": all(checks.values()), "t_H": t_h, "sum_h": _stated(sum_h), "sum_h15": _stated(sum_h15),
            "count": count, "n_placebo": n, "p_plac": (1 + count) / (n + 1) if ranked else None,
            "c_used": _k(c) / 100, "grid_index": g, "precheck_result": pre, "checks": checks}


# ------------------------------------------------------------------------------------------- step 6: the labels beside
def _solve(a: list[list[float]]) -> list[list[float]]:
    """The inverse of a small symmetric positive matrix by Gauss-Jordan with partial pivoting; ValueError when it is
    singular (collinear factors)."""
    p = len(a)
    m = [list(row) + [1.0 if i == j else 0.0 for j in range(p)] for i, row in enumerate(a)]
    for col in range(p):
        pivot = max(range(col, p), key=lambda r: abs(m[r][col]))
        if not abs(m[pivot][col]) > 1e-10:
            raise ValueError("the factors are collinear")
        m[col], m[pivot] = m[pivot], m[col]
        scale = m[col][col]
        m[col] = [value / scale for value in m[col]]
        for r in range(p):
            if r != col and m[r][col] != 0.0:
                factor = m[r][col]
                m[r] = [value - factor * lead for value, lead in zip(m[r], m[col])]
    return [row[p:] for row in m]


def loadings(x: Sequence[float], factors: Sequence[Sequence[float]], names: Sequence[str]) -> dict[str, Any]:
    """OLS of x on the daily `factors` (columns named by `names`) with an intercept and plain OLS standard errors:
    {"alpha": {"a", "t"}, name: {"b", "t"}}. Beside, never a gate.

    `factors` is one row a day, one column a name. The normal equations are formed with `math.fsum` on columns
    scaled to unit length, so the answer does not hang on a library's solver. A t is None where its
    standard error is not a positive finite number (a perfect fit). ValueError on shapes that do not agree, a value
    that is not finite, no more days than coefficients, or collinear factors."""
    y = np.asarray(x, dtype=np.float64).ravel()
    f = np.asarray(factors, dtype=np.float64)
    n, k = len(y), len(names)
    if f.ndim != 2 or f.shape != (n, k) or k == 0:
        raise ValueError(f"the factors are not one row a day and one column a name ({f.shape} for {n} days, {k} names)")
    if len(set(names)) != k or "alpha" in names:
        raise ValueError("the factor names are not distinct (or one is 'alpha')")
    if not (np.isfinite(y).all() and np.isfinite(f).all()):
        raise ValueError("a value of x or of a factor is not finite")
    p = k + 1
    if n <= p:
        raise ValueError(f"{n} days cannot fit {p} coefficients")
    columns = [[1.0] * n] + [f[:, j].tolist() for j in range(k)]
    scale = [math.sqrt(math.fsum(value * value for value in col)) for col in columns]
    if not all(s > 0 for s in scale):
        raise ValueError("a factor is zero on every day")
    columns = [[value / s for value in col] for col, s in zip(columns, scale)]
    target = y.tolist()
    gram = [[math.fsum(a * b for a, b in zip(columns[i], columns[j])) for j in range(p)] for i in range(p)]
    inverse = _solve(gram)
    moments = [math.fsum(a * b for a, b in zip(col, target)) for col in columns]
    beta = [math.fsum(inverse[i][j] * moments[j] for j in range(p)) for i in range(p)]
    residual = [target[t] - math.fsum(beta[i] * columns[i][t] for i in range(p)) for t in range(n)]
    variance = math.fsum(e * e for e in residual) / (n - p)

    def t_of(i: int) -> float | None:
        se = math.sqrt(variance * inverse[i][i]) if variance * inverse[i][i] > 0 else 0.0
        t = beta[i] / se if se > 0 else math.nan
        return t if math.isfinite(t) else None

    out: dict[str, Any] = {"alpha": {"a": beta[0] / scale[0], "t": t_of(0)}}
    for j, name in enumerate(names, start=1):
        out[str(name)] = {"b": beta[j] / scale[j], "t": t_of(j)}
    return out


def _french_label(sx: Series, french: Mapping[str, Any] | None) -> tuple[str, dict[str, Any], int]:
    """(the French label, the loadings, the days read): the OLS of x on French's five factors over the sessions of V
    and H the release covers. Anything short of a clean reading is "unmeasured", never an exception."""
    if not isinstance(french, Mapping) or not isinstance(french.get("factors"), Mapping):
        return UNMEASURED, {}, 0
    try:
        listed = french.get("days")
        covered = {_ordinal(day): i for i, day in enumerate(() if listed is None else listed)}
        table = french["factors"]
        columns = [np.asarray(table[name], dtype=np.float64) for name in FRENCH_FACTORS]
        if any(col.ndim != 1 or len(col) != len(covered) for col in columns):
            return UNMEASURED, {}, 0
        mine = [(i, covered[int(d)]) for i, d in enumerate(np.asarray(sx.days).tolist()) if int(d) in covered]
        mine = [(i, j) for i, j in mine if all(math.isfinite(float(col[j])) for col in columns)]
        if len(mine) < FRENCH_MIN_DAYS:
            return UNMEASURED, {}, len(mine)
        x = np.asarray(sx.r, dtype=np.float64)[[i for i, _ in mine]]
        rows = [[float(col[j]) for col in columns] for _, j in mine]
        got = loadings(x, rows, FRENCH_FACTORS)
    except (KeyError, TypeError, ValueError):
        return UNMEASURED, {}, 0
    ts = [got[name]["t"] for name in FRENCH_FACTORS]
    if any(t is None for t in ts):
        return UNMEASURED, got, len(mine)
    loaded = [name for name, t in zip(FRENCH_FACTORS, ts) if abs(t) >= FRENCH_T]
    return (STYLE_LOADED + ", ".join(loaded)) if loaded else NO_STYLE, got, len(mine)


def labels(result: Mapping[str, Any], *, french: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Step 6 for the look run's result: {"basket": one of `BASKET_LABELS`, "label": the French label, "loadings"}.
    `french` None (no French factors on the House) is "unmeasured".

    The basket share reads the run's sessions of V and H: "basket-led" when the sum of the cells' P&L (`bench`) is at
    least the sum of x, else "selection-led" (`sum_bench`, `sum_x` beside). `french`: {"days": [day...], "factors":
    {name: [value a day]}} with every name of `FRENCH_FACTORS` (package B's reader's shape); the label is the OLS of x
    on them over the covered sessions of V and H (`french_days`), "unmeasured" under `FRENCH_MIN_DAYS` of them or
    when the reading fails. ValueError only for a result whose daily series cannot be read or summed."""
    sx = series(result, "x")
    xv, xh = split(sx)
    bv, bh = split(_column(result, "bench"))
    sum_x = _fsum(np.concatenate([xv.r, xh.r]))
    sum_bench = _fsum(np.concatenate([bv.r, bh.r]))
    if not (math.isfinite(sum_x) and math.isfinite(sum_bench)):
        raise ValueError("the run's series do not sum to a number")
    label, got, days = _french_label(sx, french)
    return {"basket": BASKET_LABELS[0] if sum_bench >= sum_x else BASKET_LABELS[1], "label": label, "loadings": got,
            "sum_bench": sum_bench, "sum_x": sum_x, "french_days": days}


def flags_of(receipt: ReceiptXS, label: str | None) -> list[str]:
    """The receipt's flags that attach to a program: every archetype's (each prefixed with its archetype: a House
    program has no named archetype), then the screen's own (`screen_flags`: "style-open") whenever the French label
    is style-loaded or unmeasured, or there is none to read."""
    out = [f"{a}: {f}" for a in sorted(receipt.flags) for f in receipt.flags[a]]
    if label != NO_STYLE:
        out += [f for f in receipt.screen_flags if f not in out]
    return out


def _t_nw(x: np.ndarray, lag: int = NW_LAG) -> float | None:
    """The Newey-West t of the mean (Bartlett weights, `lag` lags): mean / sqrt(S / n), S = g_0 + 2 sum_l (1 - l /
    (lag + 1)) g_l, g_l = (1 / n) sum_t (x_t - m)(x_{t - l} - m). Reported beside, never a bar; None when undefined."""
    values = np.asarray(x, dtype=np.float64).ravel().tolist()
    n = len(values)
    if n < 2 or not all(math.isfinite(value) for value in values):
        return None
    mean = math.fsum(values) / n
    d = [value - mean for value in values]
    s = math.fsum(e * e for e in d) / n
    for step in range(1, min(lag, n - 1) + 1):
        s += 2.0 * (1.0 - step / (lag + 1.0)) * math.fsum(d[t] * d[t - step] for t in range(step, n)) / n
    if not s > ZERO * ZERO:
        return None
    t = mean / math.sqrt(s / n)
    return t if math.isfinite(t) else None


# ---------------------------------------------------------------------------------------------------- the verdict
def look_seed(receipt_sha256: str, code_sha256: str) -> int:
    """The seed the one sealed look's placebos must have been drawn under (the pre-registration's 3.5; `league.xs
    .placebo.look_seed`'s expression on `placebo.LOOK_SEED`): fixed by the receipt and the program's code before the
    look. ValueError unless both are 64 hex."""
    for what, value in (("receipt", receipt_sha256), ("program code", code_sha256)):
        if not isinstance(value, str) or not _HEX64.fullmatch(value):
            raise ValueError(f"the {what}'s sha256 is not 64 hex: {value!r}")
    text = LOOK_SEED.format(receipt=receipt_sha256, code=code_sha256)
    return int.from_bytes(hashlib.sha256(text.encode()).digest()[:16], "big")


def _run_misfit(result: Mapping[str, Any], receipt: ReceiptXS) -> str | None:
    """Why the look's run is not one this receipt judges: it did not end "ok" (a partial series is never judged), it
    is not at k 1.0, or its residual was taken at another rung than the receipt's."""
    if result.get("status") != "ok":
        return f"the run ended {result.get('status')!r}: a partial series is never judged"
    k = _number(result.get("k"), 0.0, 100.0)
    if k is None or abs(k - 1.0) > ZERO:
        return f"the run is at k {result.get('k')!r}, the look's is 1.0"
    if result.get("rung") != receipt.rung:
        return f"the run's residual is at rung {result.get('rung')!r}, the receipt's is {receipt.rung}"
    return None


def _placebo_block(result: Mapping[str, Any], receipt: ReceiptXS, code_sha256: Any,
                   holdout: int) -> tuple[str | None, list[float | None], Any]:
    """(why the placebo block judges nothing or None, the placebos' t on H, the block's identity share): the block
    must be the receipt's rung and number of draws, drawn under the seed the receipt and the program's code fix, and
    read on the holdout's own sessions."""
    block = result.get("placebo")
    if not isinstance(block, Mapping):
        return "the run carries no placebo block", [], None
    share = block.get("identity_share")
    if block.get("rung") != receipt.rung:
        return f"drawn at rung {block.get('rung')!r}, the receipt's is {receipt.rung}", [], share
    if _whole(block.get("n")) != receipt.placebo_draws:
        return f"{block.get('n')!r} draws, the receipt's are {receipt.placebo_draws}", [], share
    try:
        seed = look_seed(receipt.receipt_sha256, code_sha256)
    except ValueError as exc:
        return str(exc), [], share
    drawn = block.get("seed")
    if isinstance(drawn, bool) or not isinstance(drawn, (int, str)) or str(drawn) != str(seed):
        return "drawn under another seed than the receipt and the program's code fix", [], share
    spans = block.get("spans")
    span = spans.get("H") if isinstance(spans, Mapping) else None
    ts = span.get("t") if isinstance(span, Mapping) else None
    if isinstance(ts, (str, bytes)) or not isinstance(ts, Sequence) or len(ts) != receipt.placebo_draws:
        return "no t for every draw on the holdout (span H)", [], share
    days = span.get("days")
    count = _whole(days) if not isinstance(days, Sequence) or isinstance(days, (str, bytes)) else len(days)
    if count != holdout:
        return f"read on {days if count is None else count!r} sessions, the holdout's are {holdout}", [], share
    out: list[float | None] = []
    for value in ts:
        if value is None:
            out.append(None)
        elif isinstance(value, bool) or not isinstance(value, (int, float, np.integer, np.floating)):
            return f"a placebo t that is no number ({value!r})", [], share
        else:
            out.append(float(value) if math.isfinite(float(value)) else None)
    return None, out, share


def verdict(look_result: Mapping[str, Any], *, receipt: ReceiptXS | None, program_floor: Mapping[str, Any],
            code_sha256: str, french: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """The whole rule on the look run's result (its daily series over V and H and its placebo block): {screen "XS1",
    passed, why, c_used, c_p, k_used, t_H, sum_h, sum_h15, p_plac, count, n_placebo, rung, own_fp, t_raw (the raw
    P&L's t on H), t_nw5, basket, label, loadings, identity_share, precheck, look, windows, flags (the receipt's for
    the program, "style-open" attached when it applies), receipt (its sha)}. The module docstring's failure order;
    `code_sha256` fixes the seed the placebo block must have been drawn under. ScreenRefused without a receipt.

    After a receipt it never raises: what it cannot read (a result with no readable series, a floor that is not the
    receipt's, a placebo block of another draw) fails the program closed with its reason in `why`, the labels left
    at what could be read ("unmeasured" for a label that could not)."""
    if not isinstance(receipt, ReceiptXS):
        raise ScreenRefused(f"{_WHO} refuses: no receipt is pinned")
    result = look_result if isinstance(look_result, Mapping) else {}
    out: dict[str, Any] = {
        "screen": SCREEN, "passed": False, "why": None, "c_used": None, "c_p": None, "k_used": None, "t_H": None,
        "sum_h": None, "sum_h15": None, "p_plac": None, "count": None, "n_placebo": None, "rung": receipt.rung,
        "own_fp": None, "t_raw": None, "t_nw5": None, "basket": None, "label": UNMEASURED, "loadings": {},
        "identity_share": None, "precheck": None, "look": None, "windows": None,
        "flags": flags_of(receipt, None), "receipt": receipt.receipt_sha256}
    # What is read beside comes first: a failed verdict still says what it can.
    read: tuple[Series, Series, Series] | None = None
    unread = None
    try:
        v, h = split(series(result, "x"))
        h15 = split(series(result, "x15"))[1]
        raw = split(series(result, "r"))[1]
        beside = labels(result, french=french)
        read = (v, h, h15)
        out.update(windows=windows(v, h), precheck=precheck(v), t_raw=holdout_t(raw.r), t_nw5=_t_nw(h.r),
                   basket=beside["basket"], label=beside["label"], loadings=beside["loadings"],
                   flags=flags_of(receipt, beside["label"]))
    except (ValueError, TypeError, KeyError, IndexError, AttributeError, OverflowError) as exc:
        unread = f"the look's series cannot be read ({exc})"
    floor_why, k_p, k_used, own = _floor_reading(program_floor, receipt)
    if floor_why is not None:
        out["why"] = f"the floor: {floor_why}"
        return out
    out.update(c_p=k_p / 100, k_used=k_used, c_used=k_used / 100, own_fp=own)
    run_why = _run_misfit(result, receipt)
    if run_why is not None:
        out["why"] = f"the run: {run_why}"
        return out
    block_why, placebo_t, share = _placebo_block(result, receipt, code_sha256, H_LENGTH)
    out["identity_share"] = _number(share, 0.0, 1.0)
    if block_why is not None:
        out["why"] = f"the placebo block: {block_why}"
        return out
    if read is None:
        out["why"] = f"the windows: {unread}"
        return out
    v, h, h15 = read
    if not out["windows"]["ok"]:
        out["why"] = f"the windows: {out['windows']['why']}"
        return out
    lk = look(v, h, h15=h15, c_used=k_used / 100, placebo_t=placebo_t, alpha=receipt.alpha_plac)
    out.update(t_H=lk["t_H"], sum_h=lk["sum_h"], sum_h15=lk["sum_h15"], p_plac=lk["p_plac"], count=lk["count"],
               n_placebo=lk["n_placebo"], look=lk)
    if not lk["checks"]["precheck"]:
        failed = [key for key, ok in out["precheck"]["checks"].items() if not ok]
        out["why"] = "the pre-check: " + ", ".join(failed)
    elif not lk["passed"]:
        out["why"] = "the look: " + ", ".join(k for k in ("sum_h", "sum_h15", "t_H", "placebo") if not lk["checks"][k])
    else:
        out["passed"] = True
    return out


# ------------------------------------------------------------------------------------------------------ the lineage
def same_lineage(x: Any, u: Any, other_x: Any, other_u: Any, *, same_template: bool = False) -> bool:
    """Step 7: the same template, or E1's `same_lineage` (Pearson on the common Train-era sessions, pairs with a value
    that is not finite dropped, 0.7 or more) on the two residual series OR on the two universe-excess series. Each
    side as E1's function takes it (a `Series`, a mapping {session: value}, or aligned arrays).

    A "no" needs BOTH series read: the residual first, and when it does not bind the universe excess (ValueError,
    E1's, when a pair cannot be aligned: a program whose series is missing is never read as a new lineage; the caller
    fails closed)."""
    if same_template:
        return True
    return bool(_e1_same_lineage(x, other_x)) or bool(_e1_same_lineage(u, other_u))


def retry_permitted(receipt: Any = None, **facts: Any) -> bool:
    """Always False under XS1 (the pre-registration's R-g: no Validation-only retry; a program refused at the
    pre-check has spent its lineage's try). Kept so the swarm asks the panel's screen as it asks the share screen's."""
    return False


# ------------------------------------------------------------------------------------- stated beside every live trade
def beside_line(result: Mapping[str, Any], receipt: ReceiptXS, *, n_cell: int) -> str:
    """Step 8: the receipt's sentence with `BESIDE_FIELDS` filled from a `verdict` and the House's count of earlier
    XS1 looks in the program's agenda cell. ValueError when a placeholder cannot be filled (the sentence is never
    stated with a hole in it).

    Thresholds at the grid's two decimals, the program's own rate as a percentage at two, the flags joined by "; "
    ("none" when there is none). ScreenRefused without a receipt; ValueError for a verdict of another screen and for
    an `n_cell` that is no count.

    THE HOLE RULE BINDS A PASS, the only verdict a trade can stand beside: a verdict that PASSED and lacks a figure
    is a ValueError. A verdict that did not pass has no live trade; what it lacks reads "unmeasured", so the House
    can record the sentence with a failed look as it does with a passed one (a look is spent either way, and an
    exception there must never read as "the look did not land")."""
    if not isinstance(receipt, ReceiptXS):
        raise ScreenRefused(f"{_WHO} refuses: no receipt is pinned")
    if not isinstance(result, Mapping) or result.get("screen") != SCREEN:
        raise ValueError(f"a {result.get('screen') if isinstance(result, Mapping) else None} verdict beside XS1's "
                         f"sentence")
    looks = _whole(n_cell)
    if looks is None or looks < 0:
        raise ValueError(f"n_cell is the count of earlier XS1 looks in the program's agenda cell, not {n_cell!r}")
    c_used, c_p = _on_grid(result.get("c_used")), _on_grid(result.get("c_p"))
    own = _number(result.get("own_fp"), 0.0, 1.0)
    basket, label, flags = result.get("basket"), result.get("label"), result.get("flags")
    listed = not isinstance(flags, (str, bytes)) and isinstance(flags, Sequence) \
        and all(isinstance(f, str) and f for f in flags)
    fill = {"c_used": None if c_used is None else f"{c_used:.2f}", "c_p": None if c_p is None else f"{c_p:.2f}",
            "own_fp": None if own is None else f"{100.0 * own:.2f}", "n_cell": str(looks),
            "basket": basket if basket in BASKET_LABELS else None,
            "label": label if isinstance(label, str) and label.strip() else None,
            "flags": ("; ".join(flags) if flags else "none") if listed else None}
    holes = [key for key in BESIDE_FIELDS if fill[key] is None]
    if holes and result.get("passed") is not False:
        raise ValueError(f"the sentence beside a trade cannot be filled: {', '.join(holes)}")
    line = receipt.beside
    for key in BESIDE_FIELDS:
        if "{" + key + "}" not in line:
            raise ValueError(f"the receipt's sentence lacks {{{key}}}")
        line = line.replace("{" + key + "}", UNMEASURED if fill[key] is None else str(fill[key]))
    return line


__all__ = ["SCREEN", "RECEIPT_NAME", "RECEIPT_PATH", "CONTRACT", "RECEIPT_KEYS", "PIN_KEYS", "PIN_SOURCES",
           "BESIDE_FIELDS", "FP_KEYS",
           "FP_CAP", "OWNER_WALL", "ALPHA_PLAC", "PLACEBO_DRAWS", "PLACEBO_COUNT_MAX", "C_MARGIN", "C_GRID_STEP",
           "K_XS_MAX", "K_MAX", "RUNGS", "H_LENGTH", "V_LENGTH", "MIN_POOL_BOTH", "MIN_POOL_ALONE", "FLOOR_CELLS",
           "POOL_SKIP",
           "ACTIVITY_ROUND_TRIPS", "ACTIVITY_INVESTED_DAYS", "SAME_LINEAGE_CORR", "LINEAGE_SERIES",
           "LOOKS_PER_LINEAGE", "VALIDATION_TRIES", "ZERO", "BASKET_LABELS", "FRENCH_FACTORS", "FRENCH_MIN_DAYS",
           "FRENCH_T", "UNMEASURED", "NO_STYLE", "STYLE_LOADED", "STYLE_OPEN", "CHECKPOINTS", "ALPHA_F", "METHOD",
           "GRID", "SERIES_COLUMNS", "NO_CELL_WHY", "NW_LAG", "ScreenRefused", "Series", "ReceiptXS",
           "holdout_t", "look_permitted", "receipt_sha256", "pinned_receipt", "pin", "load_receipt", "series", "split",
           "windows", "precheck", "floor", "floor_fits", "look", "loadings", "labels", "flags_of", "look_seed",
           "verdict", "same_lineage", "retry_permitted", "beside_line"]
