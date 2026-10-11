"""THE SHARE SCREENS. S1 as adopted (sscreen-1010 with its review's fixes F1, D3, D5, D6; amendment A9): S1-R gates,
S1-X labels; and, beside it, S2 (sscreen2-1010, amendment A11): THE HOUSE'S GATE. Code only.

Owner: screen. This module implements the pinned pre-registration EXACTLY (its sections 2.2-2.5, 5, 6, 7 and 9 as they
bind a program) with A9's fixes, and states its one deviation (`DEVIATIONS`) beside every verdict. Its calibrated
constants are NOT here: they come from the receipt `docs/benchmarks/equity_screen_1.json` (the study's receipt, which
the integrator copies VERBATIM from the captain's scratch and pins), whose sha256 and figures the repository's
policy.json carries in `elane.screens.<lane>` (a test holds the sha to the file; docs/benchmarks/ never reaches the
House box). A screen with no pinned receipt refuses every program (`pinned_receipt` -> None; `verdict` raises
`ScreenRefused`; `load_receipt` raises it on a sha that is not the pinned one, or on a receipt that is malformed or
states another pre-check). Receipt 2 (equity_screen_2.json, the follow-up study sscreen2-1010) landed as a new file and
a new screen beside this one, S2 (amendment A11, below), never by editing receipt 1.

THE HOUSE SCREEN IS S2 (A11, the captain's amendment of Oct 10, 23:10-23:30Z; sscreen2-1010: the gate is the pre-check
AND sum_H > 1e-12 AND t_H >= c_H,used = max(c_H_floor, c_pF1 + c_H_margin), c_R = 0, c_pF1 by exact enumeration of
holdout starts over IND22-NO and IND1622-NO at L 194 and 251; S1-X unchanged). Both lanes' blocks of the repository's
policy.json pin its receipt (docs/benchmarks/equity_screen_2.json, the study's receipt copied verbatim, sha256
45634dfc...: c_H_floor 0.95, c_H_margin 0.05, the look capped at 2026-10-09), so every look runs S2's code below
(`floor_s2`, `verdict_s2`). S1+F1, the first half of this module, stays as receipt 1's screen: its receipt stays in the
repository, its loader refuses receipt 2, and no lane pins it.

THE DAILY SERIES (pre-registration section 2.2; `series`). Constant weights on the program's equity E0 (the engine's
sleeve, `capital`): a lot's weight omega = its entry notional / E0 (the engine's `weight`). Prices o and c are the
store's adjustment=all opens and closes at the lot's sessions (the engine's `Bars.adj`, so dividends are in the
return); hs is the half-spread the lot was filled at (its `hs`; `config.half_spread` when a row lacks it). Each lot
contributes one leg a session t:
- held from close t-1 through close t: omega (c_t / c_{t-1} - 1);
- entered at the open of t: omega (c_t / (o_t (1 + hs)) - 1);
- exited at the open of t: omega (o_t (1 - hs) / c_{t-1} - 1) - fee / E0;
- exited at the close of t: omega (c_t (1 - hs) / c_{t-1} - 1) - fee / E0 (the pre-registration's forced close-exit
  leg; A2 makes it any close exit, not only a segment's last session's);
- (A2 EXTENSION, the stated deviation) entered at the CLOSE of t: its half-spread is paid at t, omega (c_t / (c_t (1 +
  hs)) - 1) = omega (1 / (1 + hs) - 1), and it is held from then on (its first market leg is t+1's); an exit at the
  next OPEN after a close entry is the open-exit leg above (o_{t+1} (1 - hs) / c_t: the overnight). The
  pre-registration knew open entries and open exits only (and the forced close exit).
- weights reset to omega at every close, uncharged; a lot never sells in its entry session (ValueError).
The fee is the pre-registration's for a constant-weight sale (section 4): `config.sell_fees(proceeds = omega E0,
shares = omega E0 / (p_entry (1 + hs)))`, p_entry the adjusted official open (an open entry) or close (a close entry)
of the entry session, SEC and TAF each rounded up to the cent. A lot still open at the series' last session is marked
at that close (the holdout's P&L is mark-to-market); an engine that closes a lot at the run's last close books it as a
close exit, which is the pre-registration's forced close-exit leg.
Effective exposure w_t: omega of lots held through t (a close exit counts as held through), plus half omega for each
open entry and each open exit of t; a CLOSE ENTRY counts 0 at t (it holds no part of t's session; A2 extension).
Benchmark b_t: the equal-weight cost-free close-to-close return of the program's own instruments (`universe`: its NEEDS
symbols with closes at t-1 and t; 0 when none has both, as at a store's first session). Excess over a window W: x_t =
r_t - w_t m_W, m_W the mean of b over W (`excess`, the window's own mean: V's for V, H's for H). Round trips RT_W:
full exits in W (`exits`); invested days ID_W: sessions of W with a position held at the close (`invested`; a close
entry and a close exit count).

S1-R, THE GATE (`verdict`):
- step 0, the program floor (`floor`, A9 D5 and F1): on the program's own Train-era series (one a
  `config.TRAIN_ERA_SEGMENTS` span, the engine's runs on true history), 20,000 null worlds per world set and holdout
  length L in (194, 251): V = 250 and H = L consecutive sessions, each block independently a piece of the set's pool
  with probability proportional to its length, a uniform start, circular inside the piece (the study's IND
  construction and draw order, worlds.py `_ind_block`), seeds `numpy.random.default_rng([20261010, 1010, set_id, L,
  0])`, set_id 3 = IND22 (the 2022-01-03..2024-12-31 pool), 5 = IND1622 (2016-01-04..2019-12-31 plus 2022-24), each set
  where the program has that history (a pool of >= 300 sessions in its span). A pool is the series from its first
  decision + 2 sessions to its end (section 4); the engine decides from the run's first close (NEEDS history lies
  before it), so a pool drops each series' first two sessions. Null N0: r0 = r - w kappa (kappa = sum r / sum w over
  the set's pool); N1 (drift kept): r1 = r - w (kappa - m_P), m_P the pool's mean b. t* = the pooled t when the
  pre-check and the holdout condition hold, else -inf. c_p = the smallest c on the 0.00..5.00 grid (0.01) with the
  pass rate <= fp_cap (0.12) at BOTH L; c_H = the smallest c with share(t_H >= c and sum_H > 0) <= fp_cap at both L
  (the holdout-only guard F1: 2025 is known to authors); each the maximum over the world sets. INELIGIBLE with no pool
  of >= 300 sessions, no exposure in a pool, a series outside the Train-era spans, or c_p > 5.00 or c_H > 5.00. The
  same run gives the program's own FP and its drift-kept pass rate (N1), kept as pass-count curves on the grid
  (`curves`), so `verdict` reads them at c_used and the S1-X rate at c_X; computed on the House, never committed.
  IND1622 is the adopted rule (A9 D5), not a deviation: it replaces the pre-registration's IND13 fallback, and no
  world ever holds a 2020, 2021, 2025 or 2026 session (the floor refuses such a series).
- step 1, the pre-check on Validation (`precheck`): (RT_V >= 20 or ID_V >= 120) and sum_V r > 1e-12.
- step 2, after the one look (`look`): the pooled t over the 250 + |H| daily r of V and H (mean / sd(ddof 1) x
  sqrt(n)) >= c_used = max(c_R, c_p), sum_H r > 1e-12, AND t_H (the holdout-only t) >= c_H; sd < 1e-12 fails.
- the windows (`verdict` checks them, failing closed on a mis-sliced run): V is calendar 2025's 250 sessions; the
  holdout (A9 D6) is 2026-01-02 .. min(the last close before the look, `config.LOOK_CAP`), 194..251 sessions, the
  lengths the receipt was calibrated for (A12 caps it at 2026-10-09: exactly 194).
S1-X, THE LABEL (`label`): steps 1-2 on x with c_X, no floor, no holdout guard: "alpha" or "beta"; never a gate. Its FP
is the program's own at c_X (N0 and N1 give the same x: r - w kappa - w (m_W - m_P) either way, so one curve serves
both).
BESIDE EVERY LIVE TRADE (`beside_line`): the receipt's `stated_beside_every_live_trade` filled with the program's
c_used, c_H, own FP, drift-kept rate, S1-X label and FP (it carries the contamination sentence); every R4 flag that
applies (the receipt's, every archetype's: a program has no named archetype).
THE LINEAGE (A9 D3; the store-side ration is league/swarm/elane.py's, calling these): one holdout look per lineage,
only after a passed pre-check (`look_permitted`); a Validation-only retry (R3, `retry_permitted`) only when the
receipt permits it, the first try FAILED its pre-check (no look spent), and the retry is the version whose hash was
recorded at the first try; SAME LINEAGE (`same_lineage`): Train daily returns correlating >= 0.7 (on common sessions)
with a program already looked at, or the same template. Look and Validation outcomes of share programs are never fed
back to generators or the diagnostician (the swarm's rule).

S2, THE SHARE SCREEN OF AMENDMENT A11 (sscreen2-1010 as adopted with its review's fixes; `floor_s2`, `look_s2`,
`verdict_s2`, `beside_line_s2`), BESIDE S1, never a settings switch inside it. The pinned block's `screen` (or `name`)
picks the screen (`screen_of`), and the public entry points route on the receipt they are handed: `pinned_receipt`
(an "S2" block gives a `ReceiptS2`), `load_receipt(..., screen=)`, `floor(..., receipt=)`, `verdict`, `beside_line`.
Receipt 1 (`Receipt`) runs S1 exactly as above; receipt 2 (`ReceiptS2`, `RECEIPT_PATH_S2`) runs S2:
- unchanged from S1: the series and their accounting (with the A2 deviation), the pre-check, the S1-X label (c_X; its
  FP read from an S1 floor's "X" curve when one is given, else "unmeasured"), the lineage and the no-feedback rule;
- the look: pre-check AND sum_H r > 1e-12 AND t_H >= c_H,used. c_R = 0: the pooled t is reported, never a bar;
- c_H,used = max(c_H_floor, c_pF1 + c_H_margin) in integer grid steps (k = 100 c), the floor and the margin read from
  the receipt at run time; k_used > 500 makes the program INELIGIBLE;
- c_pF1 (`floor_s2`): the largest, over the program's eligible cells (IND22-NO: its 2022-24 pool of >= 550 sessions;
  IND1622-NO: its 2016-19 and 2022-24 pools of >= 251 each; L 194 and 251), of each cell's smallest k on 0..500 with
  HO[k] x den <= num x T (fp_cap as an exact fraction). A world is V (250) and H (L) consecutive sessions, each
  circular inside one pool piece, never sharing a session, every valid (V piece, V start, H piece, H start) equally
  likely; the rates are counted EXACTLY over all of them (no seeds, no world count). Nulls per role,
  inclusion-weighted: N0 x = r - w kappa_role (the FP null), N1 x = r - w (kappa_role - m_role) (drift kept). The
  program's own FP (the gate under N0), holdout-only rate and drift-kept rate at c_H,used, each the largest over its
  cells, are stated beside every live trade (computed on the House, never committed);
- the windows: V calendar 2025's 250 sessions; H 194..251 sessions inside 2026-01-02 .. min(`config.LOOK_CAP`,
  `S2_LOOK_CAP`), A12's cap 2026-10-09: exactly the 194 sessions the receipt is calibrated on; later days are forward
  days only.

DEVIATION (stated beside every verdict): the A2 close-fill legs above (the pre-registration knew open fills only).

Standard library and numpy only; nothing of league.live or league.swarm (an evidence module).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import re
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from . import config

SCREEN = "S1"
C_GRID_STEP = 0.01
C_GRID_MAX = 5.00
H_LENGTHS = (194, 251)
V_LENGTH = 250
WORLDS = 20_000
MIN_POOL = 300
#: World sets of the floor and their seed ids (the receipt's `floor.seed`).
WORLD_SETS = {"IND22": 3, "IND1622": 5}
ACTIVITY_ROUND_TRIPS = 20
ACTIVITY_INVESTED_DAYS = 120
SAME_LINEAGE_CORR = 0.7
ZERO = 1e-12
#: The receipt file (the integrator copies it verbatim; docs/benchmarks/ never reaches the House box).
RECEIPT_PATH = "docs/benchmarks/equity_screen_1.json"
DEVIATIONS = (
    "A2 close fills: an entry at the close of t pays its half-spread at t; an exit at the next open is the open leg; "
    "an exit at the close is the pre-registered close-exit leg",
)
#: One holdout look a lineage; one Validation try, plus R3's one retry when the receipt permits it.
LOOKS_PER_LINEAGE = 1
VALIDATION_TRIES = 1
#: The c grid, exactly the study's: c = k / 100 for k = 0..500.
GRID = np.arange(0, int(round(C_GRID_MAX / C_GRID_STEP)) + 1) / 100.0
#: The floor's seeds: default_rng([*SEED_ROOT, set_id, L, FLOOR_FAMILY]).
SEED_ROOT = (20261010, 1010)
FLOOR_FAMILY = 0
#: A pool starts this many sessions after the first decision (pre-registration section 4).
POOL_SKIP = 2
#: Which `config.TRAIN_ERA_SEGMENTS` spans each world set draws from (2016-19 is index 0, 2022-24 index 1).
SET_SEGMENTS = {"IND22": (1,), "IND1622": (0, 1)}
#: Worlds evaluated at a time (memory only: the draws are made for all worlds at once, in the study's order).
WORLD_CHUNK = 2_000
#: The receipt file's keys (the study's receipt; the fake fixture carries the same).
RECEIPT_KEYS = ("name", "study", "rule", "fp_cap", "owner_wall", "c_R", "c_X", "precheck", "look", "floor", "windows",
                "lineage", "fp_zero_edge_at_cR", "power_at_cR", "binding_R", "R3_retry_permitted", "R4_flags",
                "stated_beside_every_live_trade", "note", "sha256")
#: The placeholders of the receipt's beside-every-trade template, each filled by `beside_line`.
BESIDE_FIELDS = ("c_used", "c_H", "own_fp", "n1", "alpha|beta", "fpx")
FILLS = ("open", "close")

_HEX64 = re.compile(r"[0-9a-f]{64}")
_EPOCH = dt.date(1970, 1, 1)


class ScreenRefused(RuntimeError):
    """No pinned receipt (or a malformed one): the screen judges no program."""


@dataclass(frozen=True)
class Receipt:
    """The pinned receipt as policy.json carries it (copied from the receipt file's keys): `receipt_sha256` (the
    file's bytes, 64 hex), `c_R`, `c_X`, `fp_cap` (0.12), `owner_wall` (0.15; None when the block names none), `retry`
    (`R3_retry_permitted`), `r4` (`R4_flags`: archetype -> flags), `beside` (`stated_beside_every_live_trade`, a
    template with {c_used}, {c_H}, {own_fp}, {n1}, {alpha|beta}, {fpx}), `fp` (`fp_zero_edge_at_cR` and the other
    figures stated beside)."""

    receipt_sha256: str
    c_R: float
    c_X: float
    fp_cap: float
    owner_wall: float | None
    retry: bool
    r4: Mapping[str, tuple[str, ...]]
    beside: str
    fp: Mapping[str, Any]


@dataclass(frozen=True)
class Series:
    """A program's daily series over one window or segment (section 2.2): `days` int32 ordinals; `r` (daily P&L on
    E0), `w` (effective exposure), `b` (benchmark) float64; `exits` int (full exits that session); `invested` bool
    (a position held at the close). Equal lengths."""

    days: np.ndarray
    r: np.ndarray
    w: np.ndarray
    b: np.ndarray
    exits: np.ndarray
    invested: np.ndarray


# ------------------------------------------------------------------------------------------------------- the receipt
def receipt_sha256(path: str | Path) -> str | None:
    """sha256 of the receipt file's bytes, None when it cannot be read."""
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def _number(value: Any, lo: float, hi: float) -> float | None:
    """A finite real number in [lo, hi] (never a bool), else None."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    v = float(value)
    return v if math.isfinite(v) and lo <= v <= hi else None


def _flags(value: Any) -> dict[str, tuple[str, ...]] | None:
    """R4's flags as {archetype: (flag, ...)}, None when malformed (a flag must never be lost to a bad shape)."""
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


def pinned_receipt(block: Mapping[str, Any] | None) -> Receipt | ReceiptS2 | None:
    """The receipt a lane's screen block pins (the REPOSITORY's policy.json `elane.screens.<lane>`, never swarm.json),
    ROUTED by the block's screen (`screen_of`: its `screen` or `name`, A11): an "S2" block is `pinned_receipt_s2`'s (a
    `ReceiptS2`); an "S1" block (or one naming neither) is receipt 1's: None unless it carries a 64-hex
    `receipt_sha256`, finite `c_R` and `c_X` in [0, 5], `fp_cap` in (0, 1) and the beside template with every
    placeholder (`BESIDE_FIELDS`). A block naming another screen, an `owner_wall` or `r4` that is present but malformed
    also refuse (None): a pin is read whole or not at all."""
    if not isinstance(block, Mapping):
        return None
    which = screen_of(block)
    if which == SCREEN_S2:
        return pinned_receipt_s2(block)
    if which != SCREEN:
        return None
    if block.get("name", SCREEN) != SCREEN:
        return None
    sha = block.get("receipt_sha256")
    if not isinstance(sha, str) or not _HEX64.fullmatch(sha):
        return None
    c_R = _number(block.get("c_R"), 0.0, C_GRID_MAX)
    c_X = _number(block.get("c_X"), 0.0, C_GRID_MAX)
    fp_cap = _number(block.get("fp_cap"), 0.0, 1.0)
    if c_R is None or c_X is None or fp_cap is None or not 0.0 < fp_cap < 1.0:
        return None
    wall = block.get("owner_wall")
    owner_wall = None
    if wall is not None:
        owner_wall = _number(wall, 0.0, 1.0)
        if owner_wall is None or owner_wall <= 0.0:
            return None
    beside = block.get("beside")
    if not isinstance(beside, str) or not all("{" + f + "}" in beside for f in BESIDE_FIELDS):
        return None
    raw_r4 = block.get("r4")
    r4 = _flags({} if raw_r4 is None else raw_r4)
    if r4 is None:
        return None
    fp = block.get("fp")
    return Receipt(receipt_sha256=sha, c_R=c_R, c_X=c_X, fp_cap=fp_cap, owner_wall=owner_wall,
                   retry=block.get("retry") is True, r4=r4, beside=beside,
                   fp=dict(fp) if isinstance(fp, Mapping) else {})


def load_receipt(path: str | Path, *, pinned_sha256: str, screen: str = SCREEN) -> Receipt | ReceiptS2:
    """Read a receipt file and check its sha256 against the pinned one (ScreenRefused on a mismatch or a malformed
    file): CI's and the tests' reader (a fake receipt under league/tests/fixtures only). ROUTED by `screen`, the pinned
    block's (`screen_of`): "S2" reads receipt 2 (`load_receipt_s2`); "S1" (the default) reads receipt 1 and refuses
    receipt 2 (it lacks receipt 1's keys); another screen refuses. Receipt 1 malformed: not JSON, a key of
    `RECEIPT_KEYS` missing, `R3_retry_permitted` not a bool, a pre-check other than this module's (`rt_min` 20,
    `id_min` 120) or a lineage with more than one holdout look, or figures `pinned_receipt` refuses."""
    if screen == SCREEN_S2:
        return load_receipt_s2(path, pinned_sha256=pinned_sha256)
    if screen != SCREEN:
        raise ScreenRefused(f"the share screen refuses: no screen {screen!r}")
    if not isinstance(pinned_sha256, str) or not _HEX64.fullmatch(pinned_sha256):
        raise ScreenRefused("the share screen refuses: no receipt sha256 is pinned")
    try:
        raw = Path(path).read_bytes()
    except OSError as exc:
        raise ScreenRefused(f"the share screen refuses: the receipt {path} cannot be read ({exc})") from exc
    sha = hashlib.sha256(raw).hexdigest()
    if sha != pinned_sha256:
        raise ScreenRefused(f"the share screen refuses: the receipt's sha256 {sha[:12]} is not the pinned "
                            f"{pinned_sha256[:12]}")
    try:
        doc = json.loads(raw)
    except ValueError as exc:
        raise ScreenRefused(f"the share screen refuses: the receipt is not JSON ({exc})") from exc
    if not isinstance(doc, Mapping):
        raise ScreenRefused("the share screen refuses: the receipt is not an object")
    missing = [k for k in RECEIPT_KEYS if k not in doc]
    if missing:
        raise ScreenRefused(f"the share screen refuses: the receipt lacks {', '.join(missing)}")
    if not isinstance(doc["R3_retry_permitted"], bool):
        raise ScreenRefused("the share screen refuses: the receipt's R3_retry_permitted is not a bool")
    pre = doc["precheck"] if isinstance(doc["precheck"], Mapping) else {}
    lineage = doc["lineage"] if isinstance(doc["lineage"], Mapping) else {}
    if (pre.get("rt_min") != ACTIVITY_ROUND_TRIPS or pre.get("id_min") != ACTIVITY_INVESTED_DAYS
            or lineage.get("holdout_looks") != LOOKS_PER_LINEAGE):
        raise ScreenRefused("the share screen refuses: the receipt states another pre-check or lineage than this code")
    receipt = pinned_receipt({
        "name": SCREEN, "receipt_sha256": sha, "c_R": doc["c_R"], "c_X": doc["c_X"], "fp_cap": doc["fp_cap"],
        "owner_wall": doc["owner_wall"], "retry": doc["R3_retry_permitted"], "r4": doc["R4_flags"],
        "beside": doc["stated_beside_every_live_trade"],
        "fp": {k: doc[k] for k in ("fp_zero_edge_at_cR", "power_at_cR", "binding_R")}})
    if receipt is None:
        raise ScreenRefused("the share screen refuses: the receipt's figures are malformed")
    return receipt


# ---------------------------------------------------------------------------------------------- the daily series
def _ordinal(day: Any) -> int:
    """A session as an int32 ordinal since 1970-01-01 (`league.gym.day.ordinal`): from an ordinal, a date or an ISO
    string."""
    if isinstance(day, (int, np.integer)) and not isinstance(day, bool):
        return int(day)
    if isinstance(day, dt.datetime):
        day = day.date()
    if isinstance(day, dt.date):
        return (day - _EPOCH).days
    if isinstance(day, str):
        return (dt.date.fromisoformat(day[:10]) - _EPOCH).days
    raise ValueError(f"not a session day: {day!r}")


def _float(value: Any, what: str) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{what} is not a number: {value!r}") from exc
    if not math.isfinite(v):
        raise ValueError(f"{what} is not finite: {value!r}")
    return v


def _benchmark(bars: Any, universe: Sequence[str], lo: int, hi: int) -> np.ndarray:
    """b_t over sessions lo..hi: the equal-weight cost-free close-to-close return of the universe members with closes
    at t-1 and t (0 when none has both)."""
    if not universe:
        raise ValueError("the benchmark needs the program's instruments (an empty universe)")
    closes = []
    for sym in universe:
        if sym not in bars.adj:
            raise ValueError(f"the benchmark's {sym} is not in the bars")
        closes.append(np.asarray(bars.adj[sym], dtype=np.float64)[:, 3])
    c = np.vstack(closes)
    n = hi - lo + 1
    b = np.zeros(n)
    start = 1 if lo == 0 else 0                 # a store's first session has no prior close
    if n - start <= 0:
        return b
    now = c[:, lo + start:hi + 1]
    prev = c[:, lo + start - 1:hi]
    ok = np.isfinite(now) & np.isfinite(prev) & (prev > 0)
    with np.errstate(divide="ignore", invalid="ignore"):
        ret = np.where(ok, now / np.where(ok, prev, 1.0) - 1.0, 0.0)
    count = ok.sum(0)
    b[start:] = np.where(count > 0, ret.sum(0) / np.maximum(count, 1), 0.0)
    return b


def series(lots: Sequence[Mapping[str, Any]], bars: Any, *, universe: Sequence[str], capital: Any,
           first: int | None = None, last: int | None = None) -> Series:
    """Section 2.2's accounting (with the A2 extension) of a run's `lots` (league/equity/engine.py result["lots"])
    over the sessions [first, last] of `bars` (a `store.Bars`; default its run sessions), on E0 = `capital`. ValueError
    (fail closed: no series, no verdict) on a lot that names a session or symbol the bars lack, a fill point other than
    "open" / "close", a sale in the entry session, a weight or price that is not finite, or a window outside the
    bars."""
    days = np.asarray(bars.days, dtype=np.int32)
    total = len(days)
    lo = int(bars.first) if first is None else int(first)
    hi = total - 1 if last is None else int(last)
    if not 0 <= lo <= hi < total:
        raise ValueError(f"the window [{lo}, {hi}] is outside the bars' {total} sessions")
    e0 = _float(capital, "E0")
    if e0 <= 0:
        raise ValueError(f"E0 must be above zero: {capital!r}")
    e0_dec = Decimal(str(capital))
    where = {int(d): i for i, d in enumerate(days)}
    n = hi - lo + 1
    r = np.zeros(n)
    w = np.zeros(n)
    exits = np.zeros(n, dtype=np.int64)
    invested = np.zeros(n, dtype=bool)
    b = _benchmark(bars, universe, lo, hi)

    for lot in lots:
        lid = lot.get("lid")
        sym = lot.get("symbol")
        if sym not in bars.adj:
            raise ValueError(f"lot {lid}: {sym} is not in the bars")
        adj = np.asarray(bars.adj[sym], dtype=np.float64)
        o, c = adj[:, 0], adj[:, 3]
        e = where.get(_ordinal(lot.get("entry_day")))
        if e is None:
            raise ValueError(f"lot {lid}: its entry day {lot.get('entry_day')} is not a session of the bars")
        at_e = lot.get("entry_at") or "open"
        if at_e not in FILLS:
            raise ValueError(f"lot {lid}: entry at {at_e!r}")
        x, at_x = None, "open"
        if lot.get("exit_day") not in (None, ""):
            x = where.get(_ordinal(lot.get("exit_day")))
            if x is None:
                raise ValueError(f"lot {lid}: its exit day {lot.get('exit_day')} is not a session of the bars")
            at_x = lot.get("exit_at") or "open"
            if at_x not in FILLS:
                raise ValueError(f"lot {lid}: exit at {at_x!r}")
            if x <= e:
                raise ValueError(f"lot {lid}: sold in its entry session (or before it)")
        om = _float(lot.get("weight"), f"lot {lid}'s weight")
        if om <= 0:
            raise ValueError(f"lot {lid}: weight {om} is not above zero")
        hs = lot.get("hs")
        hs = config.half_spread(sym) if hs is None else _float(hs, f"lot {lid}'s half-spread")
        if hs < 0:
            raise ValueError(f"lot {lid}: a negative half-spread")
        if e > hi or (x is not None and x < lo):
            continue
        legs: list[tuple[int, float, float, bool]] = []      # (session, P&L on E0, exposure, held at the close)
        if e >= lo:
            if at_e == "open":
                legs.append((e, om * (c[e] / (o[e] * (1.0 + hs)) - 1.0), om / 2.0, True))
            else:
                legs.append((e, om * (1.0 / (1.0 + hs) - 1.0), 0.0, True))
        h0 = max(e + 1, lo)
        h1 = hi if x is None else min(x - 1, hi)
        if h1 >= h0:
            held = om * (c[h0:h1 + 1] / c[h0 - 1:h1] - 1.0)
            if not np.isfinite(held).all():
                bad = h0 + int(np.argmin(np.isfinite(held)))
                raise ValueError(f"lot {lid}: no price for {sym} at session {int(days[bad])}")
            r[h0 - lo:h1 - lo + 1] += held
            w[h0 - lo:h1 - lo + 1] += om
            invested[h0 - lo:h1 - lo + 1] = True
        if x is not None and lo <= x <= hi:
            p_entry = o[e] if at_e == "open" else c[e]
            fill = p_entry * (1.0 + hs)
            if not (math.isfinite(fill) and fill > 0):
                raise ValueError(f"lot {lid}: no entry price for {sym}")
            proceeds = Decimal(str(om)) * e0_dec
            shares = Decimal(str(om * e0 / fill))
            fee = float(config.sell_fees(proceeds, shares)) / e0
            if at_x == "open":
                legs.append((x, om * (o[x] * (1.0 - hs) / c[x - 1] - 1.0) - fee, om / 2.0, False))
            else:
                legs.append((x, om * (c[x] * (1.0 - hs) / c[x - 1] - 1.0) - fee, om, True))
            exits[x - lo] += 1
        for t, value, exposure, held_at_close in legs:
            if not math.isfinite(value):
                raise ValueError(f"lot {lid}: no price for {sym} at session {int(days[t])}")
            r[t - lo] += value
            w[t - lo] += exposure
            invested[t - lo] |= held_at_close
    return Series(days=days[lo:hi + 1].copy(), r=r, w=w, b=b, exits=exits, invested=invested)


def excess(s: Series) -> np.ndarray:
    """x_t = r_t - w_t m_W over the series' own window W."""
    r = np.asarray(s.r, dtype=np.float64)
    if len(r) == 0:
        return r.copy()
    return r - np.asarray(s.w, dtype=np.float64) * float(np.mean(s.b))


def _values(s: Series, variant: str) -> np.ndarray:
    if variant == "R":
        return np.asarray(s.r, dtype=np.float64)
    if variant == "X":
        return excess(s)
    raise ValueError(f"variant {variant!r} is neither 'R' nor 'X'")


# ---------------------------------------------------------------------------------------------- steps 1 and 2
def precheck(v: Series, *, variant: str = "R") -> dict[str, Any]:
    """Step 1 on Validation: {passed, round_trips, invested_days, sum, sessions, variant, checks}; `variant` "R" on r,
    "X" on x. Checks: activity (RT_V >= 20 or ID_V >= 120) and sum_positive (sum_V > 1e-12)."""
    values = _values(v, variant)
    rt = int(np.sum(v.exits))
    inv = int(np.sum(v.invested))
    total = float(values.sum())
    checks = {"activity": rt >= ACTIVITY_ROUND_TRIPS or inv >= ACTIVITY_INVESTED_DAYS, "sum_positive": total > ZERO}
    return {"passed": all(checks.values()), "round_trips": rt, "invested_days": inv, "sum": total,
            "sessions": len(values), "variant": variant, "checks": checks}


def _t(x: np.ndarray) -> float | None:
    x = np.asarray(x, dtype=np.float64)
    n = len(x)
    if n < 2 or not np.isfinite(x).all():
        return None
    sd = float(np.std(x, ddof=1))
    if not sd >= ZERO:
        return None
    t = float(np.mean(x)) / sd * math.sqrt(n)
    return t if math.isfinite(t) else None


def pooled_t(v: np.ndarray, h: np.ndarray) -> float | None:
    """The pooled t over the concatenated daily values (mean / sd(ddof 1) x sqrt(n)); None when sd < 1e-12."""
    return _t(np.concatenate([np.asarray(v, dtype=np.float64), np.asarray(h, dtype=np.float64)]))


def holdout_t(h: np.ndarray) -> float | None:
    """The holdout-only t (F1's t_H); None when sd < 1e-12."""
    return _t(h)


def look(v: Series, h: Series, *, c: float, c_H: float | None, variant: str = "R") -> dict[str, Any]:
    """Step 2 after the one look: {passed, t, t_H, sum_h, n, variant, checks}; `c_H` None (S1-X) skips the holdout
    guard. Checks: t (the pooled t >= c; None, from sd < 1e-12, fails), sum_h (sum_H > 1e-12), and t_H (>= c_H)."""
    xv, xh = _values(v, variant), _values(h, variant)
    t = pooled_t(xv, xh)
    sum_h = float(xh.sum())
    t_h = holdout_t(xh)
    checks = {"t": t is not None and t >= c, "sum_h": sum_h > ZERO}
    if c_H is not None:
        checks["t_H"] = t_h is not None and t_h >= c_H
    return {"passed": all(checks.values()), "t": t, "t_H": t_h, "sum_h": sum_h, "n": len(xv) + len(xh),
            "variant": variant, "checks": checks}


def label(v: Series, h: Series, *, c_X: float) -> str:
    """S1-X: "alpha" when steps 1-2 pass on x with c_X (no floor, no holdout guard), else "beta"."""
    ok = precheck(v, variant="X")["passed"] and look(v, h, c=c_X, c_H=None, variant="X")["passed"]
    return "alpha" if ok else "beta"


# --------------------------------------------------------------------------------------------- step 0: the floor
def _cap(fp_cap: Any) -> Fraction:
    v = _number(fp_cap, 0.0, 1.0)
    if v is None or not 0.0 < v < 1.0:
        raise ValueError(f"fp_cap must lie in (0, 1): {fp_cap!r}")
    return Fraction(str(fp_cap))


def _draw(rng: np.random.Generator, lens: np.ndarray, length: int, n: int) -> tuple[np.ndarray, np.ndarray]:
    """One block of every world, in the study's draw order (worlds.py `_ind_block`): a piece with probability
    proportional to its length among the pieces at least `length` long, then a uniform start inside it."""
    ok = lens >= length
    if not ok.any():
        raise ValueError(f"no pool piece holds {length} sessions")
    p = np.where(ok, lens, 0).astype(float)
    p /= p.sum()
    piece = rng.choice(len(lens), size=n, p=p)
    start = rng.integers(0, lens[piece])
    return piece, start


def _block(g0: np.ndarray, lens: np.ndarray, piece: np.ndarray, start: np.ndarray, length: int) -> np.ndarray:
    """Global indices of each world's block: `length` consecutive sessions from `start`, circular inside its piece."""
    off = (start[:, None] + np.arange(length)[None, :]) % lens[piece][:, None]
    return g0[piece][:, None] + off


def _moments(r: np.ndarray, w: np.ndarray, idx: np.ndarray) -> dict[str, Any]:
    """Sums over each world's block of r, w, r^2, r w and w^2 (screen.py `block_moments`)."""
    R, W = r[idx], w[idx]
    return {"Sr": R.sum(1), "Sw": W.sum(1), "Srr": np.einsum("ij,ij->i", R, R), "Srw": np.einsum("ij,ij->i", R, W),
            "Sww": np.einsum("ij,ij->i", W, W), "n": idx.shape[1]}


def _shifted(m: Mapping[str, Any], g: Any) -> tuple[np.ndarray, np.ndarray]:
    """The sum and the sum of squares of (r + g w) over each block (g a scalar or one a world)."""
    return m["Sr"] + g * m["Sw"], m["Srr"] + 2.0 * g * m["Srw"] + g * g * m["Sww"]


def _tstar(mv: Mapping[str, Any], mh: Mapping[str, Any], gv: Any, gh: Any, act: np.ndarray) -> np.ndarray:
    """t* of the series r + g w over V and H (screen.py `tstar_vec`): the pooled t where the pre-check (activity and
    sum_V > 1e-12), sum_H > 1e-12 and sd >= 1e-12 hold, else -inf."""
    sv, ssv = _shifted(mv, gv)
    sh, ssh = _shifted(mh, gh)
    n = mv["n"] + mh["n"]
    s, ss = sv + sh, ssv + ssh
    sd = np.sqrt(np.maximum((ss - s * s / n) / (n - 1), 0.0))
    ok = act & (sv > ZERO) & (sh > ZERO) & (sd >= ZERO)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(ok, (s / n) / np.where(sd > 0, sd, 1.0) * math.sqrt(n), -np.inf)


def _tstar_h(mh: Mapping[str, Any], g: float) -> np.ndarray:
    """F1's statistic: the holdout-only t of r + g w where sum_H > 1e-12 and sd >= 1e-12, else -inf."""
    s, ss = _shifted(mh, g)
    n = mh["n"]
    sd = np.sqrt(np.maximum((ss - s * s / n) / (n - 1), 0.0))
    ok = (s > ZERO) & (sd >= ZERO)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(ok, (s / n) / np.where(sd > 0, sd, 1.0) * math.sqrt(n), -np.inf)


def _pass_counts(tstar: np.ndarray) -> np.ndarray:
    """How many worlds have t* >= c at each grid c (screen.py `pass_counts`)."""
    s = np.sort(np.asarray(tstar, dtype=np.float64))
    return len(s) - np.searchsorted(s, GRID, side="left")


def _c_needed(counts: np.ndarray, worlds: int, cap: Fraction) -> float:
    """The smallest grid c whose pass share is <= cap (exact: counts x den <= num x worlds); inf when none is."""
    ok = counts * cap.denominator <= cap.numerator * worlds
    return float(GRID[int(np.argmax(ok))]) if ok.any() else math.inf


def _train_segment(days: np.ndarray) -> int | None:
    """The index of the `config.TRAIN_ERA_SEGMENTS` span holding every one of `days`, None when they leave it."""
    lo, hi = int(days.min()), int(days.max())
    for k, (first, last) in enumerate(config.TRAIN_ERA_SEGMENTS):
        if _ordinal(first) <= lo and hi <= _ordinal(last):
            return k
    return None


def _cell(arrays: Mapping[str, np.ndarray], g0: np.ndarray, lens: np.ndarray, consts: Mapping[str, float],
          set_id: int, L: int, worlds: int) -> dict[str, np.ndarray]:
    """One (world set, L) cell: pass counts on the grid of S1-R under N0 and N1, of S1-X, and of F1's t_H under N0."""
    rng = np.random.default_rng([*SEED_ROOT, set_id, L, FLOOR_FAMILY])
    pv, sv = _draw(rng, lens, V_LENGTH, worlds)
    ph, sh = _draw(rng, lens, L, worlds)
    kappa, m_p = consts["kappa"], consts["m_P"]
    a_p = kappa - m_p
    out = {key: np.empty(worlds) for key in ("R_N0", "R_N1", "X", "H")}
    r, w, b = arrays["r"], arrays["w"], arrays["b"]
    for i in range(0, worlds, WORLD_CHUNK):
        j = min(i + WORLD_CHUNK, worlds)
        v = _block(g0, lens, pv[i:j], sv[i:j], V_LENGTH)
        h = _block(g0, lens, ph[i:j], sh[i:j], L)
        mv, mh = _moments(r, w, v), _moments(r, w, h)
        act = ((arrays["exits"][v].sum(1) >= ACTIVITY_ROUND_TRIPS)
               | (arrays["invested"][v].sum(1) >= ACTIVITY_INVESTED_DAYS))
        bv, bh = b[v].sum(1) / V_LENGTH, b[h].sum(1) / L
        out["R_N0"][i:j] = _tstar(mv, mh, -kappa, -kappa, act)
        out["R_N1"][i:j] = _tstar(mv, mh, -a_p, -a_p, act)
        out["X"][i:j] = _tstar(mv, mh, -kappa - (bv - m_p), -kappa - (bh - m_p), act)
        out["H"][i:j] = _tstar_h(mh, -kappa)
    return {key: _pass_counts(t) for key, t in out.items()}


def _finite(c: float) -> float | None:
    """A grid threshold, None for "none on the grid" (inf)."""
    return c if math.isfinite(c) else None


def _trimmed(counts: np.ndarray) -> list[int]:
    """A pass-count curve without its trailing zeros (JSON-sized for the family state)."""
    nz = np.nonzero(counts)[0]
    return [int(x) for x in counts[:int(nz[-1]) + 1]] if len(nz) else []


def floor(segments: Sequence[Series | None], *, fp_cap: float | None = None,
          receipt: Receipt | ReceiptS2 | None = None) -> dict[str, Any]:
    """The program floor, ROUTED by `receipt` (A11): a `ReceiptS2` runs `floor_s2`; a `Receipt` runs S1's floor at its
    fp_cap (an `fp_cap` given beside it must be the same); `fp_cap` alone runs S1's (E1's call). ScreenRefused with
    neither, or with a receipt that is neither.

    S1's step 0 from the program's Train-era series (one `Series` per `config.TRAIN_ERA_SEGMENTS` entry, on true
    history; a None or empty entry is a span the program has no history in): {screen, eligible, why, c_p, c_H, fp_cap,
    sets {"IND22": {pool, c_p, c_H, by_L {"194": {c_p, c_H}, "251": ...}}, "IND1622": {...}}, own_fp (at c_p),
    drift_kept (N1 at c_p), worlds, seeds {set: {L: seed}}, curves {set: {L: {"R_N0", "R_N1", "X": pass counts on the
    grid}}}}. Deterministic (the receipt's seeds). Each series is placed by its days, never by its position; one that
    leaves the Train-era spans makes the program ineligible (a 2020, 2021, 2025 or 2026 session never enters a world).
    `own_fp` and `drift_kept` are the largest over the floor's cells (its sets and both L); `verdict` reads the curves
    at c_used."""
    if isinstance(receipt, ReceiptS2):
        return floor_s2(segments, receipt=receipt)
    if isinstance(receipt, Receipt):
        if fp_cap is not None and _cap(fp_cap) != _cap(receipt.fp_cap):
            raise ValueError(f"fp_cap {fp_cap!r} is not the receipt's {receipt.fp_cap}")
        fp_cap = receipt.fp_cap
    elif receipt is not None or fp_cap is None:
        raise ScreenRefused("the share screen refuses: no receipt is pinned (a floor needs one)")
    cap = _cap(fp_cap)
    out: dict[str, Any] = {"screen": SCREEN, "eligible": False, "why": None, "c_p": None, "c_H": None,
                           "fp_cap": float(fp_cap), "sets": {}, "own_fp": None, "drift_kept": None, "worlds": WORLDS,
                           "seeds": {}, "curves": {}}
    placed: dict[int, Series] = {}
    for s in segments:
        if s is None or len(s.days) == 0:
            continue
        lengths = {len(s.days), len(s.r), len(s.w), len(s.b), len(s.exits), len(s.invested)}
        if len(lengths) != 1:
            raise ValueError("a series whose arrays differ in length")
        k = _train_segment(np.asarray(s.days))
        if k is None:
            out["why"] = "a series leaves the Train-era spans (2016-01-04..2019-12-31, 2022-01-03..2024-12-31)"
            return out
        if k in placed:
            out["why"] = "two series for one Train-era span"
            return out
        placed[k] = s
    have = {k: s for k, s in placed.items() if len(s.days) - POOL_SKIP >= MIN_POOL}
    chosen = {}
    for name, members in SET_SEGMENTS.items():
        if members[0] in have:
            chosen[name] = [k for k in members if k in have]
    if not chosen:
        out["why"] = f"no pool of >= {MIN_POOL} sessions in the Train-era spans"
        return out

    need_p: list[float] = []
    need_h: list[float] = []
    for name, members in chosen.items():
        parts = [have[k] for k in members]
        arrays = {key: np.concatenate([np.asarray(getattr(p, key), dtype=dtype) for p in parts])
                  for key, dtype in (("r", np.float64), ("w", np.float64), ("b", np.float64), ("exits", np.int64),
                                     ("invested", np.int64))}
        sizes = np.array([len(p.days) for p in parts], dtype=np.int64)
        offsets = np.concatenate([[0], np.cumsum(sizes)[:-1]])
        g0, lens = offsets + POOL_SKIP, sizes - POOL_SKIP
        pool = np.concatenate([np.arange(g, g + n) for g, n in zip(g0, lens)])
        sum_w = float(arrays["w"][pool].sum())
        if not sum_w > 0:
            out["why"] = f"{name}: no exposure in the pool (kappa is undefined)"
            return out
        consts = {"kappa": float(arrays["r"][pool].sum()) / sum_w, "m_P": float(arrays["b"][pool].mean())}
        if not all(math.isfinite(v) for v in consts.values()):
            out["why"] = f"{name}: the pool's series are not finite"
            return out
        row: dict[str, Any] = {"pool": int(len(pool)), "c_p": None, "c_H": None, "by_L": {}}
        set_id = WORLD_SETS[name]
        set_p, set_h = [], []
        for L in H_LENGTHS:
            counts = _cell(arrays, g0, lens, consts, set_id, L, WORLDS)
            cp, ch = _c_needed(counts["R_N0"], WORLDS, cap), _c_needed(counts["H"], WORLDS, cap)
            set_p.append(cp)
            set_h.append(ch)
            row["by_L"][str(L)] = {"c_p": _finite(cp), "c_H": _finite(ch)}
            out["seeds"].setdefault(name, {})[str(L)] = [*SEED_ROOT, set_id, L, FLOOR_FAMILY]
            out["curves"].setdefault(name, {})[str(L)] = {key: _trimmed(counts[key]) for key in ("R_N0", "R_N1", "X")}
        row["c_p"], row["c_H"] = _finite(max(set_p)), _finite(max(set_h))
        out["sets"][name] = row
        need_p += set_p
        need_h += set_h
    c_p, c_h = max(need_p), max(need_h)
    out["c_p"], out["c_H"] = _finite(c_p), _finite(c_h)
    if c_p > C_GRID_MAX or c_h > C_GRID_MAX:
        over = [k for k, c in (("c_p", c_p), ("c_H", c_h)) if c > C_GRID_MAX]
        out["why"] = f"a threshold above {C_GRID_MAX:.2f} ({' and '.join(over)}: no grid c holds the cap)"
        return out
    out["eligible"] = True
    out["own_fp"] = fp_at(out, "R_N0", c_p)
    out["drift_kept"] = fp_at(out, "R_N1", c_p)
    return out


def fp_at(program_floor: Mapping[str, Any] | None, key: str, c: float) -> float | None:
    """The largest pass share over a floor's cells of curve `key` ("R_N0" the program's FP at zero edge, "R_N1" its
    drift-kept pass rate, "X" its S1-X FP) at threshold `c` (read at the grid point at or below c: never smaller than
    the share at c). None when the floor carries no such curve."""
    fl = program_floor if isinstance(program_floor, Mapping) else {}
    curves = fl.get("curves") if isinstance(fl.get("curves"), Mapping) else {}
    worlds = fl.get("worlds")
    if not curves or isinstance(worlds, bool) or not isinstance(worlds, int) or worlds <= 0:
        return None
    k = min(max(int(math.floor(float(c) * 100.0 + 1e-9)), 0), len(GRID) - 1)
    shares = []
    for by_l in curves.values():
        for cell in (by_l.values() if isinstance(by_l, Mapping) else ()):
            curve = cell.get(key) if isinstance(cell, Mapping) else None
            if not isinstance(curve, Sequence):
                return None
            shares.append((int(curve[k]) if k < len(curve) else 0) / worlds)
    return max(shares) if shares else None


# ---------------------------------------------------------------------------------------------------- the verdict
def _windows(v: Series, h: Series, *, cap: dt.date | None = None) -> dict[str, Any]:
    """The windows the receipt was calibrated for: V calendar 2025's `V_LENGTH` sessions, H inside [LOOK_FIRST,
    LOOK_CAP] with 194..251 sessions (A9 D6; `cap` an earlier last session, S2's A12 cap). {ok, validation, holdout,
    why}."""
    look_cap = config.LOOK_CAP if cap is None else cap
    v_first, v_last = config.WINDOWS["validation"]
    nv, nh = len(v.days), len(h.days)
    why = None
    if nv != V_LENGTH or (nv and not (_ordinal(v_first) <= int(np.min(v.days))
                                      and int(np.max(v.days)) <= _ordinal(v_last))):
        why = f"the Validation series is not calendar 2025's {V_LENGTH} sessions ({nv})"
    elif not (H_LENGTHS[0] <= nh <= H_LENGTHS[-1]) or not (
            _ordinal(config.LOOK_FIRST) <= int(np.min(h.days)) and int(np.max(h.days)) <= _ordinal(look_cap)):
        why = (f"the holdout is not {H_LENGTHS[0]}..{H_LENGTHS[-1]} sessions inside "
               f"{config.LOOK_FIRST}..{look_cap} ({nh})")
    return {"ok": why is None, "validation": nv, "holdout": nh, "why": why}


def verdict(v: Series, h: Series, *, receipt: Receipt | ReceiptS2 | None, program_floor: Mapping[str, Any],
            s1_floor: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """ROUTED by `receipt` (A11): a `ReceiptS2` is `verdict_s2` (`s1_floor`, an S1 floor for S1-X's FP, is S2's only).

    The whole S1 after the look: {screen "S1", passed (S1-R), why (the first failed condition), c_R, c_X, c_p, c_H,
    c_used, t, t_H, sum_h, n, precheck, look, windows, label (S1-X), own_fp (the program's FP at c_used), drift_kept
    (its N1 pass rate at c_used), fp_x (its S1-X FP at c_X), fp_cap, r4, deviations, receipt}. ScreenRefused when
    `receipt` is None; a floor that is not eligible, or was run at another fp_cap than the receipt's, fails the program
    (no look should have been spent: the swarm runs the floor before the look); so do windows outside the calibrated
    ones."""
    if isinstance(receipt, ReceiptS2):
        return verdict_s2(v, h, receipt=receipt, program_floor=program_floor, s1_floor=s1_floor)
    if receipt is None:
        raise ScreenRefused("the share screen refuses: no receipt is pinned")
    fl = program_floor if isinstance(program_floor, Mapping) else {}
    windows = _windows(v, h)
    pre = precheck(v)
    out: dict[str, Any] = {
        "screen": SCREEN, "passed": False, "why": None, "c_R": receipt.c_R, "c_X": receipt.c_X, "c_p": None,
        "c_H": None, "c_used": None, "t": None, "t_H": None, "sum_h": None, "n": None, "precheck": pre, "look": None,
        "windows": windows, "label": label(v, h, c_X=receipt.c_X), "own_fp": None, "drift_kept": None,
        "fp_x": fp_at(fl, "X", receipt.c_X), "fp_cap": receipt.fp_cap, "r4": r4_flags(receipt),
        "deviations": list(DEVIATIONS), "receipt": receipt.receipt_sha256}
    c_p = _number(fl.get("c_p"), 0.0, C_GRID_MAX)
    c_h = _number(fl.get("c_H"), 0.0, C_GRID_MAX)
    floor_cap = _number(fl.get("fp_cap"), 0.0, 1.0)
    if fl.get("eligible") is not True or c_p is None or c_h is None:
        out["why"] = f"step 0, the floor: {fl.get('why') or 'not eligible'}"
        return out
    if floor_cap is None or abs(floor_cap - receipt.fp_cap) > ZERO:
        out["why"] = f"step 0, the floor: run at fp_cap {fl.get('fp_cap')!r}, the receipt's is {receipt.fp_cap}"
        return out
    c_used = max(receipt.c_R, c_p)
    lk = look(v, h, c=c_used, c_H=c_h)
    out.update(c_p=c_p, c_H=c_h, c_used=c_used, t=lk["t"], t_H=lk["t_H"], sum_h=lk["sum_h"], n=lk["n"], look=lk,
               own_fp=fp_at(fl, "R_N0", c_used), drift_kept=fp_at(fl, "R_N1", c_used))
    if not windows["ok"]:
        out["why"] = f"the windows: {windows['why']}"
    elif not pre["passed"]:
        out["why"] = "step 1, the pre-check: " + ", ".join(k for k, ok in pre["checks"].items() if not ok)
    elif not lk["passed"]:
        out["why"] = "step 2, the look: " + ", ".join(k for k, ok in lk["checks"].items() if not ok)
    else:
        out["passed"] = True
    return out


def _pct(x: Any) -> str:
    v = _number(x, 0.0, 1.0)
    return "unmeasured" if v is None else f"{100.0 * v:.2f}"


def _c(x: Any) -> str:
    v = _number(x, 0.0, C_GRID_MAX)
    return "unmeasured" if v is None else f"{v:.2f}"


def beside_line(result: Mapping[str, Any], receipt: Receipt | ReceiptS2) -> str:
    """The receipt's `beside` template filled from a `verdict` (stated beside every live trade of the program), R4
    flags appended. Percentages at two decimals, thresholds at the grid's; a figure the verdict lacks reads
    "unmeasured". ROUTED by `receipt` (A11): a `ReceiptS2` fills receipt 2's template (`beside_line_s2`); a verdict of
    the other screen than the receipt's is a ValueError; no receipt refuses."""
    if isinstance(receipt, ReceiptS2):
        return beside_line_s2(result, receipt)
    if not isinstance(receipt, Receipt):
        raise ScreenRefused("the share screen refuses: no receipt is pinned")
    if result.get("screen", SCREEN) != SCREEN:
        raise ValueError(f"a {result.get('screen')} verdict beside receipt 1's line")
    lab = result.get("label")
    fill = {"c_used": _c(result.get("c_used")), "c_H": _c(result.get("c_H")), "own_fp": _pct(result.get("own_fp")),
            "n1": _pct(result.get("drift_kept")), "alpha|beta": lab if lab in ("alpha", "beta") else "unlabelled",
            "fpx": _pct(result.get("fp_x"))}
    line = receipt.beside
    for key, value in fill.items():
        line = line.replace("{" + key + "}", value)
    flags = list(result.get("r4") or ())
    if flags:
        line += "; R4 flags: " + "; ".join(str(f) for f in flags)
    return line


# ------------------------------------------------------------------------------------------------------ the lineage
def retry_permitted(receipt: Receipt | None, *, first_precheck_failed: bool, tries: int = 1, looks: int = 0,
                    retry_sha: str | None = None, recorded_sha: str | None = None) -> bool:
    """R3: a second, Validation-only try of a lineage only when the receipt permits it AND the first try FAILED its
    pre-check (no look spent). Never a second look, never a third try: `tries` (the lineage's Validation tries so far)
    must be exactly 1 and `looks` 0. When either hash is given, the retry must be the version whose hash was recorded
    at the first try (`recorded_sha` == `retry_sha`, A9 D3)."""
    if receipt is None or not receipt.retry or first_precheck_failed is not True:
        return False
    if tries != VALIDATION_TRIES or looks != 0:
        return False
    if retry_sha is not None or recorded_sha is not None:
        return isinstance(retry_sha, str) and bool(retry_sha) and retry_sha == recorded_sha
    return True


def look_permitted(looks: int, *, precheck_passed: bool) -> bool:
    """One holdout look a lineage, and only after a Validation pre-check that passed (a failed pre-check fails the
    program with its look unspent)."""
    return looks < LOOKS_PER_LINEAGE and precheck_passed is True


def _by_session(x: Any) -> dict[int, float] | None:
    if isinstance(x, Series):
        return {int(d): float(v) for d, v in zip(x.days, x.r)}
    if isinstance(x, Mapping):
        return {_ordinal(d): float(v) for d, v in x.items()}
    return None


def same_lineage(train_r: Any, other_train_r: Any, *, same_template: bool = False) -> bool:
    """A9 D3: True when the two programs' Train daily returns (aligned on common sessions) correlate >= 0.7, or they
    use the same template. Each side is a `Series` (its days and r), a mapping {session: r} (an ordinal, a date or an
    ISO day) or an array already aligned with the other (equal lengths, else ValueError). Pairs with a value that is not
    finite are dropped; fewer than two common sessions, or a side with no variance, is not a correlation (False)."""
    if same_template:
        return True
    a_map, b_map = _by_session(train_r), _by_session(other_train_r)
    if a_map is not None or b_map is not None:
        if a_map is None or b_map is None:
            raise ValueError("align two programs' Train returns on sessions: both need their days")
        common = sorted(set(a_map) & set(b_map))
        a = np.array([a_map[d] for d in common], dtype=np.float64)
        b = np.array([b_map[d] for d in common], dtype=np.float64)
    else:
        a = np.asarray(train_r, dtype=np.float64).ravel()
        b = np.asarray(other_train_r, dtype=np.float64).ravel()
        if len(a) != len(b):
            raise ValueError("two Train series without days must be aligned (equal lengths)")
    ok = np.isfinite(a) & np.isfinite(b)
    a, b = a[ok], b[ok]
    if len(a) < 2 or not (np.std(a) >= ZERO and np.std(b) >= ZERO):
        return False
    corr = float(np.corrcoef(a, b)[0, 1])
    return math.isfinite(corr) and corr >= SAME_LINEAGE_CORR


def r4_flags(receipt: Receipt | None, archetype: str | None = None) -> list[str]:
    """R4's wall flags that apply (the receipt's, for the program's nearest archetype, or every archetype's, each
    prefixed with its archetype, when None)."""
    if receipt is None:
        return []
    if archetype is not None:
        return [str(f) for f in receipt.r4.get(archetype, ())]
    return [f"{a}: {f}" for a in sorted(receipt.r4) for f in receipt.r4[a]]


# ===================================================================================== S2, the share screen of A11
SCREEN_S2 = "S2"
#: The screens a pinned block may name (`screen_of`).
SCREENS = (SCREEN, SCREEN_S2)
#: Receipt 2 (the integrator copies it verbatim; docs/benchmarks/ never reaches the House box).
RECEIPT_PATH_S2 = "docs/benchmarks/equity_screen_2.json"
#: S2's world sets: their `config.TRAIN_ERA_SEGMENTS` indices, in piece order (the study's IND-NO sets).
S2_SETS = {"IND22-NO": (1,), "IND1622-NO": (0, 1)}
#: The pool lengths (sessions, after `POOL_SKIP`) that make a set eligible.
S2_MIN = {"IND22-NO": {1: 550}, "IND1622-NO": {0: 251, 1: 251}}
#: A12: an S2 look's holdout ends at this session at the latest (with `config.LOOK_CAP`, whichever is earlier): the
#: 194 sessions 2026-01-02..2026-10-09 the receipt is calibrated on; later sessions are forward days only.
S2_LOOK_CAP = dt.date(2026, 10, 9)
#: Receipt 2's keys (the fake fixture carries the same).
RECEIPT_KEYS_S2 = ("name", "screen", "study", "rule", "fp_cap", "owner_wall", "c_R", "c_H_floor", "c_H_margin", "c_X",
                   "precheck", "look", "floor", "windows", "lineage", "R3_retry_permitted", "R4_flags", "fp_zero_edge",
                   "power", "stated_beside_every_live_trade", "note", "sha256")
#: The placeholders of receipt 2's beside-every-trade template, each filled by `beside_line_s2`.
BESIDE_FIELDS_S2 = ("c_H", "own_fp", "honly", "n1", "alpha|beta", "fpx")
#: The floor's method (receipt 2's `floor.method`): an exact enumeration, no seeds and no world count.
S2_METHOD = "exact"
NO_SET_WHY = ("no eligible floor set (IND22-NO needs a 2022-24 pool >= 550; IND1622-NO needs 2016-19 and 2022-24 pools "
              ">= 251 each)")
_K_MAX = len(GRID) - 1                          # 500: c = 5.00
_ISO_DAY = re.compile(r"\d{4}-\d{2}-\d{2}")


@dataclass(frozen=True)
class ReceiptS2:
    """Receipt 2 as policy.json pins it (`elane.screens.<lane>` with `screen` / `name` "S2"): `receipt_sha256` (the
    file's bytes, 64 hex), `c_R` (always 0.0: no pooled-t bar), `c_H_floor` and `c_H_margin` (on the 0.01 grid), `c_X`
    (S1-X's label threshold), `fp_cap`, `owner_wall` (None when the block names none), `retry` (`R3_retry_permitted`),
    `r4` (`R4_flags`), `beside` (`stated_beside_every_live_trade`, a template with {c_H}, {own_fp}, {honly}, {n1},
    {alpha|beta}, {fpx}) and `fp` (the receipt's `fp_zero_edge` and `power`, as `load_receipt_s2` reads them)."""

    receipt_sha256: str
    c_R: float
    c_H_floor: float
    c_H_margin: float
    c_X: float
    fp_cap: float
    owner_wall: float | None
    retry: bool
    r4: Mapping[str, tuple[str, ...]]
    beside: str
    fp: Mapping[str, Any]


class _Ineligible(ValueError):
    """S2: the program has no floor (it cannot be looked at under S2)."""


def screen_of(pin: Any) -> str | None:
    """Which screen a pin runs: "S1" for a `Receipt`, "S2" for a `ReceiptS2`; for a policy block, its `screen` or its
    `name` ("S1" when it names neither, as receipt 1's blocks may be written). None for anything else: a block naming
    another screen, or whose `screen` and `name` disagree."""
    if isinstance(pin, ReceiptS2):
        return SCREEN_S2
    if isinstance(pin, Receipt):
        return SCREEN
    if not isinstance(pin, Mapping):
        return None
    named = [pin[key] for key in ("screen", "name") if key in pin]
    if not named:
        return SCREEN
    if not all(isinstance(x, str) for x in named) or len(set(named)) != 1:
        return None
    return named[0] if named[0] in SCREENS else None


def receipt_path(pin: Any) -> str | None:
    """The repository path of the receipt file a pin (a receipt or a policy block) names, None for no screen."""
    return {SCREEN: RECEIPT_PATH, SCREEN_S2: RECEIPT_PATH_S2}.get(screen_of(pin) or "")


def _on_grid(value: Any) -> float | None:
    """A number on the 0.01 grid in [0, 5], else None."""
    v = _number(value, 0.0, C_GRID_MAX)
    if v is None or abs(v * 100.0 - round(v * 100.0)) > 1e-9:
        return None
    return v


def _k(c: float) -> int:
    """A grid threshold as its integer step k = 100 c."""
    return int(round(float(c) * 100.0))


def pinned_receipt_s2(block: Mapping[str, Any] | None) -> ReceiptS2 | None:
    """The receipt 2 a lane's screen block pins (the REPOSITORY's policy.json `elane.screens.<lane>`, never swarm.json):
    None unless the block names S2 (`screen` or `name`), carries a 64-hex `receipt_sha256`, `c_R` exactly 0,
    `c_H_floor` and `c_H_margin` on the 0.01 grid in [0, 5], `c_X` in [0, 5], `fp_cap` in (0, 1), `owner_wall` absent or
    in (0, 1], the beside template with every `BESIDE_FIELDS_S2` placeholder, and a well-formed `r4`."""
    if not isinstance(block, Mapping) or screen_of(block) != SCREEN_S2:
        return None
    sha = block.get("receipt_sha256")
    if not isinstance(sha, str) or not _HEX64.fullmatch(sha):
        return None
    c_R = _number(block.get("c_R"), 0.0, C_GRID_MAX)
    c_floor, c_margin = _on_grid(block.get("c_H_floor")), _on_grid(block.get("c_H_margin"))
    c_X = _number(block.get("c_X"), 0.0, C_GRID_MAX)
    fp_cap = _number(block.get("fp_cap"), 0.0, 1.0)
    if c_R != 0.0 or c_floor is None or c_margin is None or c_X is None or fp_cap is None or not 0.0 < fp_cap < 1.0:
        return None
    wall = block.get("owner_wall")
    owner_wall = None
    if wall is not None:
        owner_wall = _number(wall, 0.0, 1.0)
        if owner_wall is None or owner_wall <= 0.0:
            return None
    beside = block.get("beside")
    if not isinstance(beside, str) or not all("{" + f + "}" in beside for f in BESIDE_FIELDS_S2):
        return None
    raw_r4 = block.get("r4")
    r4 = _flags({} if raw_r4 is None else raw_r4)
    if r4 is None:
        return None
    fp = block.get("fp")
    return ReceiptS2(receipt_sha256=sha, c_R=0.0, c_H_floor=c_floor, c_H_margin=c_margin, c_X=c_X, fp_cap=fp_cap,
                     owner_wall=owner_wall, retry=block.get("retry") is True, r4=r4, beside=beside,
                     fp=dict(fp) if isinstance(fp, Mapping) else {})


def _read_receipt(path: str | Path, pinned_sha256: str, who: str) -> tuple[Mapping[str, Any], str]:
    """A receipt file's JSON object and sha256, refused (ScreenRefused) unless its bytes are the pinned ones."""
    if not isinstance(pinned_sha256, str) or not _HEX64.fullmatch(pinned_sha256):
        raise ScreenRefused(f"{who} refuses: no receipt sha256 is pinned")
    try:
        raw = Path(path).read_bytes()
    except OSError as exc:
        raise ScreenRefused(f"{who} refuses: the receipt {path} cannot be read ({exc})") from exc
    sha = hashlib.sha256(raw).hexdigest()
    if sha != pinned_sha256:
        raise ScreenRefused(f"{who} refuses: the receipt's sha256 {sha[:12]} is not the pinned {pinned_sha256[:12]}")
    try:
        doc = json.loads(raw)
    except ValueError as exc:
        raise ScreenRefused(f"{who} refuses: the receipt is not JSON ({exc})") from exc
    if not isinstance(doc, Mapping):
        raise ScreenRefused(f"{who} refuses: the receipt is not an object")
    return doc, sha


def load_receipt_s2(path: str | Path, *, pinned_sha256: str) -> ReceiptS2:
    """Read receipt 2 and check its sha256 against the pinned one: CI's and the tests' reader. ScreenRefused on a sha
    mismatch (or none pinned), a file that cannot be read or is not a JSON object, a key of `RECEIPT_KEYS_S2` missing,
    `screen` not "S2", `R3_retry_permitted` not a bool, a pre-check other than this code's (`rt_min` 20, `id_min` 120),
    a lineage other than one look and two Validation tries (one try plus R3's retry), a `floor.method` other than
    "exact", a holdout window other than `config.LOOK_FIRST` .. `S2_LOOK_CAP` (A12), or figures `pinned_receipt_s2`
    refuses."""
    who = "the share screen S2"
    doc, sha = _read_receipt(path, pinned_sha256, who)
    missing = [k for k in RECEIPT_KEYS_S2 if k not in doc]
    if missing:
        raise ScreenRefused(f"{who} refuses: the receipt lacks {', '.join(missing)}")
    if doc["screen"] != SCREEN_S2:
        raise ScreenRefused(f"{who} refuses: the receipt is for screen {doc['screen']!r}, not S2")
    if not isinstance(doc["R3_retry_permitted"], bool):
        raise ScreenRefused(f"{who} refuses: the receipt's R3_retry_permitted is not a bool")
    pre = doc["precheck"] if isinstance(doc["precheck"], Mapping) else {}
    lineage = doc["lineage"] if isinstance(doc["lineage"], Mapping) else {}
    fl = doc["floor"] if isinstance(doc["floor"], Mapping) else {}
    windows = doc["windows"] if isinstance(doc["windows"], Mapping) else {}
    if pre.get("rt_min") != ACTIVITY_ROUND_TRIPS or pre.get("id_min") != ACTIVITY_INVESTED_DAYS:
        raise ScreenRefused(f"{who} refuses: the receipt states another pre-check than this code")
    if lineage.get("holdout_looks") != LOOKS_PER_LINEAGE or lineage.get("validation_tries") != VALIDATION_TRIES + 1:
        raise ScreenRefused(f"{who} refuses: the receipt states another lineage than this code")
    if fl.get("method") != S2_METHOD:
        raise ScreenRefused(f"{who} refuses: the receipt's floor is not the exact enumeration")
    days = _ISO_DAY.findall(str(windows.get("holdout") or ""))
    if days[:2] != [config.LOOK_FIRST.isoformat(), S2_LOOK_CAP.isoformat()]:
        raise ScreenRefused(f"{who} refuses: the receipt's holdout is not {config.LOOK_FIRST}..{S2_LOOK_CAP} (A12)")
    receipt = pinned_receipt_s2({
        "screen": SCREEN_S2, "receipt_sha256": sha, "c_R": doc["c_R"], "c_H_floor": doc["c_H_floor"],
        "c_H_margin": doc["c_H_margin"], "c_X": doc["c_X"], "fp_cap": doc["fp_cap"], "owner_wall": doc["owner_wall"],
        "retry": doc["R3_retry_permitted"], "r4": doc["R4_flags"], "beside": doc["stated_beside_every_live_trade"],
        "fp": {k: doc[k] for k in ("fp_zero_edge", "power")}})
    if receipt is None:
        raise ScreenRefused(f"{who} refuses: the receipt's figures are malformed")
    return receipt


# ------------------------------------------------------------------------------------------ S2's floor, exactly
def _pools_s2(segments: Sequence[Series | None]) -> dict[int, dict[str, np.ndarray]]:
    """The program's pools by `config.TRAIN_ERA_SEGMENTS` index: each series placed by its days (as `floor`), from
    `POOL_SKIP` to its end. _Ineligible for a series that leaves the spans or two series for one span; ValueError for
    arrays of unequal length."""
    placed: dict[int, Series] = {}
    for s in segments:
        if s is None or len(s.days) == 0:
            continue
        if len({len(s.days), len(s.r), len(s.w), len(s.b), len(s.exits), len(s.invested)}) != 1:
            raise ValueError("a series whose arrays differ in length")
        k = _train_segment(np.asarray(s.days))
        if k is None:
            raise _Ineligible("a series leaves the Train-era spans (2016-01-04..2019-12-31, 2022-01-03..2024-12-31)")
        if k in placed:
            raise _Ineligible("two series for one Train-era span")
        placed[k] = s
    return {k: {"r": np.asarray(s.r, dtype=np.float64)[POOL_SKIP:], "w": np.asarray(s.w, dtype=np.float64)[POOL_SKIP:],
                "b": np.asarray(s.b, dtype=np.float64)[POOL_SKIP:],
                "exits": np.asarray(s.exits, dtype=np.int64)[POOL_SKIP:],
                "invested": np.asarray(s.invested, dtype=bool)[POOL_SKIP:]} for k, s in placed.items()}


def _sets_s2(pools: Mapping[int, Mapping[str, np.ndarray]]) -> dict[str, list[Mapping[str, np.ndarray]]]:
    """The eligible world sets, {name: [pools in piece order]} (`S2_SETS`, `S2_MIN`)."""
    n = {k: len(p["r"]) for k, p in pools.items()}
    return {name: [pools[k] for k in members] for name, members in S2_SETS.items()
            if all(n.get(k, 0) >= S2_MIN[name][k] for k in members)}


def _tuple_counts(lens: Sequence[int], L: int, lv: int = V_LENGTH) -> tuple[np.ndarray, np.ndarray, int]:
    """Per piece: U = the valid H starts per V start, W = the valid V starts per H start; T = the valid tuples. In one
    piece of length n, H start d is valid for V start b iff (d - b) mod n lies in [lv, n - L]."""
    lens = np.asarray(lens, dtype=np.int64)
    NV = np.where(lens >= lv, lens, 0)
    NH = np.where(lens >= L, lens, 0)
    same = np.where((lens >= lv) & (lens >= L), np.maximum(0, lens - lv - L + 1), 0)
    U = np.where(lens >= lv, NH.sum() - NH + same, 0)
    W = np.where(lens >= L, NV.sum() - NV + same, 0)
    return U, W, int((NV * U).sum())


def _starts(n: int, length: int) -> np.ndarray:
    """Every circular block start of a piece of n sessions: an (n, length) index array."""
    d = np.arange(n)
    return (d[:, None] + np.arange(length)[None, :]) % n


def _role_constants(pools: Sequence[Mapping[str, np.ndarray]], L: int, *, lv: int = V_LENGTH) -> dict[str, float]:
    """kappa_V, kappa_H (inclusion-weighted sum r / sum w) and m_V, m_H (inclusion-weighted mean b): a session of piece
    k lies in U_k lv V blocks and W_k L H blocks of the valid tuples. _Ineligible on a series that is not finite or on
    no exposure."""
    if not all(np.isfinite(p[key]).all() for p in pools for key in ("r", "w", "b")):
        raise _Ineligible("the pool series are not finite")
    lens = [len(p["r"]) for p in pools]
    U, W, _ = _tuple_counts(lens, L, lv)
    sr = np.array([float(np.sum(p["r"])) for p in pools])
    sw = np.array([float(np.sum(p["w"])) for p in pools])
    sb = np.array([float(np.sum(p["b"])) for p in pools])
    n = np.array(lens, dtype=float)
    if not (U * sw).sum() > 0 or not (W * sw).sum() > 0:
        raise _Ineligible("no exposure in the pool (kappa is undefined)")
    out = {"kappa_V": float((U * sr).sum() / (U * sw).sum()), "kappa_H": float((W * sr).sum() / (W * sw).sum()),
           "m_V": float((U * sb).sum() / (U * n).sum()), "m_H": float((W * sb).sum() / (W * n).sum())}
    if not all(math.isfinite(v) for v in out.values()):
        raise _Ineligible("the pool series are not finite")
    return out


def _grid_index(t: np.ndarray, ok: np.ndarray) -> np.ndarray:
    """The largest k with k / 100 <= t where ok, else -1: (ok and t >= k / 100) <=> index >= k."""
    return np.searchsorted(GRID, np.where(ok, t, -np.inf), side="right") - 1


def _curve(ix: np.ndarray, weights: Any) -> np.ndarray:
    """The sum of the integer weights of the entries with index >= k, for k = 0..500 (exact, int64)."""
    m = ix >= 0
    acc = np.zeros(len(GRID), dtype=np.int64)
    np.add.at(acc, ix[m], np.asarray(weights, dtype=np.int64)[m])
    return acc[::-1].cumsum()[::-1]


def _exact_cell(pools: Sequence[Mapping[str, np.ndarray]], L: int, *, null: str = "N0", edge: float = 0.0,
                lv: int = V_LENGTH, act: tuple[int, int] = (ACTIVITY_ROUND_TRIPS, ACTIVITY_INVESTED_DAYS)
                ) -> dict[str, Any]:
    """One (world set, L) cell's exact counts over its valid tuples, for k = 0..500 (c = k / 100):
      holdout_only[k] = #(sum_H > 1e-12 AND sd_H >= 1e-12 AND t_H >= c)                    (F1's rate x T; no pre-check)
      gate[k]         = #(pre-check(V) AND sum_H > 1e-12 AND sd_H >= 1e-12 AND t_H >= c)   (the S2 gate x T)
    on the null `null` ("N0": x = r - w kappa_role; "N1": x = r - w (kappa_role - m_role)), plus w edge / 252 (`edge`,
    a per-invested-dollar edge a year; tests only). `lv` and `act` (round trips, invested days) shrink V for the
    brute-force tests. -> {holdout_only, gate, T, consts}. _Ineligible as `_role_constants`, or with no valid tuple."""
    rc = _role_constants(pools, L, lv=lv)
    if null == "N0":
        g_v, g_h = rc["kappa_V"], rc["kappa_H"]
    elif null == "N1":
        g_v, g_h = rc["kappa_V"] - rc["m_V"], rc["kappa_H"] - rc["m_H"]
    else:
        raise ValueError(f"null {null!r} is neither 'N0' nor 'N1'")
    g_v, g_h = g_v - edge / 252.0, g_h - edge / 252.0
    lens = np.array([len(p["r"]) for p in pools], dtype=np.int64)
    U, W, T = _tuple_counts(lens, L, lv)
    if T <= 0:
        raise _Ineligible(f"no valid (V, H) tuple at L {L}")
    pre = []                                    # the pre-check of every V start, per piece
    for p, n in zip(pools, lens):
        if n < lv:
            pre.append(np.zeros(0, dtype=np.int64))
            continue
        ix = _starts(int(n), lv)
        x = np.asarray(p["r"], float)[ix] - np.asarray(p["w"], float)[ix] * g_v
        active = (np.asarray(p["exits"])[ix].sum(1) >= act[0]) | (np.asarray(p["invested"])[ix].sum(1) >= act[1])
        pre.append((active & (x.sum(1) > ZERO)).astype(np.int64))
    PV = np.array([int(v.sum()) for v in pre], dtype=np.int64)
    ho = np.zeros(len(GRID), dtype=np.int64)
    gate = np.zeros(len(GRID), dtype=np.int64)
    for j, (p, n) in enumerate(zip(pools, lens)):
        n = int(n)
        if n < L:
            continue
        ix = _starts(n, L)
        x = np.asarray(p["r"], float)[ix] - np.asarray(p["w"], float)[ix] * g_h
        s = x.sum(1)
        sd = x.std(1, ddof=1)
        with np.errstate(divide="ignore", invalid="ignore"):
            t = x.mean(1) / sd * math.sqrt(L)
        k = _grid_index(t, (s > ZERO) & (sd >= ZERO) & np.isfinite(t))
        # The pre-check-passing V starts compatible with each H start d: every V start of the other pieces, plus the
        # V starts b of this piece with (d - b) mod n in [lv, n - L] (one circular window sum over the doubled array).
        a = np.full(n, int(PV.sum() - PV[j]), dtype=np.int64)
        if n >= lv and n - lv - L + 1 > 0:
            c = np.concatenate([[0], np.cumsum(np.concatenate([pre[j], pre[j]]))])
            d = np.arange(n)
            a += c[d + n - lv + 1] - c[d + L]
        ho += _curve(k, np.full(n, int(W[j]), dtype=np.int64))
        gate += _curve(k, a)
    return {"holdout_only": ho, "gate": gate, "T": T, "consts": rc}


def _first_k(counts: np.ndarray, T: int, cap: Fraction) -> int | None:
    """The smallest grid step k with counts[k] / T <= cap, in exact integers; None when none on 0..500."""
    ok = counts * cap.denominator <= cap.numerator * T
    return int(np.argmax(ok)) if ok.any() else None


def floor_s2(segments: Sequence[Series | None], *, receipt: ReceiptS2) -> dict[str, Any]:
    """S2's program floor (HOUSE-RULE sections 3-7) from the program's Train-era series (one `Series` per
    `config.TRAIN_ERA_SEGMENTS` entry, on true history; None or empty where it has none). Deterministic: an exact
    enumeration, no seeds. -> {screen "S2", eligible, why, method "exact", c_pF1, c_H_used, k_F1, k_used, fp_cap,
    c_H_floor, c_H_margin (as run: `verdict_s2` checks them against the receipt), sets {name: {pools [lengths], by_L
    {"194" | "251": {k_F1, T}}}}, own_fp, holdout_only, drift_kept (each the largest over the cells at k_used), cells
    {"<set>|<L>": {T, HO_used, G_N0_used, G_N1_used}}}. Computed on the House, never committed. INELIGIBLE (eligible
    False, `why`): no eligible set, a cell with no valid tuple or no c <= 5.00, c_H,used above 5.00, zero exposure, a
    series that is not finite, a series outside the Train-era spans or two series for one span. ScreenRefused without
    an S2 receipt; ValueError on arrays of unequal length."""
    if not isinstance(receipt, ReceiptS2):
        raise ScreenRefused("the share screen S2 refuses: no S2 receipt is pinned")
    cap = _cap(receipt.fp_cap)
    k_floor, k_margin = _k(receipt.c_H_floor), _k(receipt.c_H_margin)
    out: dict[str, Any] = {"screen": SCREEN_S2, "eligible": False, "why": None, "method": S2_METHOD, "c_pF1": None,
                           "c_H_used": None, "k_F1": None, "k_used": None, "fp_cap": receipt.fp_cap,
                           "c_H_floor": receipt.c_H_floor, "c_H_margin": receipt.c_H_margin, "sets": {},
                           "own_fp": None, "holdout_only": None, "drift_kept": None, "cells": {}}
    try:
        sets = _sets_s2(_pools_s2(segments))
        if not sets:
            raise _Ineligible(NO_SET_WHY)
        found: dict[str, tuple[Sequence[Mapping[str, np.ndarray]], int, dict[str, Any]]] = {}
        for name, pools in sets.items():
            row: dict[str, Any] = {"pools": [len(p["r"]) for p in pools], "by_L": {}}
            out["sets"][name] = row
            for L in H_LENGTHS:
                try:
                    e0 = _exact_cell(pools, L, null="N0")
                except _Ineligible as exc:
                    raise _Ineligible(f"{name} L {L}: {exc}") from None
                k = _first_k(e0["holdout_only"], e0["T"], cap)
                row["by_L"][str(L)] = {"k_F1": k, "T": e0["T"]}
                if k is None:
                    raise _Ineligible(f"{name} L {L}: no c <= {C_GRID_MAX:.2f} holds the holdout-only rate at "
                                      f"{float(cap) * 100:g}%")
                found[f"{name}|{L}"] = (pools, L, e0)
        k_f1 = max(row["k_F1"] for set_row in out["sets"].values() for row in set_row["by_L"].values())
        k_used = max(k_floor, k_f1 + k_margin)
        out.update(k_F1=k_f1, c_pF1=k_f1 / 100)
        if k_used > _K_MAX:
            raise _Ineligible(f"c_H,used {k_used / 100:.2f} is above {C_GRID_MAX:.2f}")
        for cell, (pools, L, e0) in found.items():
            e1 = _exact_cell(pools, L, null="N1")
            out["cells"][cell] = {"T": int(e0["T"]), "HO_used": int(e0["holdout_only"][k_used]),
                                  "G_N0_used": int(e0["gate"][k_used]), "G_N1_used": int(e1["gate"][k_used])}
        rows = out["cells"].values()
        out.update(eligible=True, k_used=k_used, c_H_used=k_used / 100,
                   own_fp=max(r["G_N0_used"] / r["T"] for r in rows),
                   holdout_only=max(r["HO_used"] / r["T"] for r in rows),
                   drift_kept=max(r["G_N1_used"] / r["T"] for r in rows))
    except _Ineligible as exc:
        out["why"] = str(exc)
        out["cells"] = {}
    return out


def _floor_misfit_s2(program_floor: Mapping[str, Any], receipt: ReceiptS2) -> str | None:
    """Why an S2 floor was not run by this receipt (None when it was): another screen or method, or another fp_cap,
    c_H_floor or c_H_margin than the receipt's. Eligibility is not judged here."""
    fl = program_floor
    if fl.get("screen") != SCREEN_S2:
        return f"not an S2 floor ({fl.get('screen') or 'none'})"
    if fl.get("method") != S2_METHOD:
        return f"not an exact floor ({fl.get('method')!r})"
    for key in ("fp_cap", "c_H_floor", "c_H_margin"):
        ran = _number(fl.get(key), 0.0, C_GRID_MAX)
        if ran is None or abs(ran - float(getattr(receipt, key))) > ZERO:
            return f"run at {key} {fl.get(key)!r}, the receipt's is {getattr(receipt, key)}"
    return None


def floor_fits(program_floor: Any, receipt: Any) -> bool:
    """Whether a (cached) floor was run by this receipt's screen and settings, eligible or not: an S1 floor at the
    receipt's fp_cap for a `Receipt`; an exact S2 floor at the receipt's fp_cap, c_H_floor and c_H_margin for a
    `ReceiptS2`. False for anything else (run the floor again)."""
    if not isinstance(program_floor, Mapping) or "eligible" not in program_floor:
        return False
    if isinstance(receipt, ReceiptS2):
        return _floor_misfit_s2(program_floor, receipt) is None
    if isinstance(receipt, Receipt):
        ran = _number(program_floor.get("fp_cap"), 0.0, 1.0)
        return (program_floor.get("screen", SCREEN) == SCREEN and ran is not None
                and abs(ran - receipt.fp_cap) <= ZERO)
    return False


# ------------------------------------------------------------------------------------------- S2's look and verdict
def look_s2(v: Series, h: Series, *, c_H: float) -> dict[str, Any]:
    """S2's look after the one holdout look: {passed, t_H, sum_h, t (the pooled t, reported, never a bar), n, c_H,
    checks {precheck, sum_h, t_H}}: the pre-check on V (`precheck`), sum_H r > 1e-12, and t_H (mean / sd(ddof 1) x
    sqrt(L), None when sd < 1e-12 or not finite) >= c_H. There is no c_R: the pooled t never gates."""
    if isinstance(c_H, bool) or not isinstance(c_H, (int, float)) or not math.isfinite(float(c_H)):
        raise ValueError(f"c_H must be a finite number: {c_H!r}")
    pre = precheck(v)
    rh = np.asarray(h.r, dtype=np.float64)
    sum_h = float(rh.sum())
    t_h = holdout_t(rh)
    checks = {"precheck": bool(pre["passed"]), "sum_h": sum_h > ZERO, "t_H": t_h is not None and t_h >= float(c_H)}
    return {"passed": all(checks.values()), "t_H": t_h, "sum_h": sum_h, "t": pooled_t(v.r, rh),
            "n": len(v.r) + len(rh), "c_H": float(c_H), "checks": checks}


def verdict_s2(v: Series, h: Series, *, receipt: ReceiptS2 | None, program_floor: Mapping[str, Any],
               s1_floor: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """The whole S2 after the look: {screen "S2", passed, why (the first failed condition), c_R 0.0, c_pF1, c_H
    (= c_H,used), t_H, sum_h, t (pooled, report only), n, precheck, look, windows, label (S1-X, unchanged), own_fp,
    holdout_only, drift_kept (the program's own, from its S2 floor at c_H,used), fp_x (S1-X's FP at c_X, read from an
    eligible S1 floor's "X" curve; None, "unmeasured", without one), fp_cap, r4, deviations, receipt}.
    Failure order: no receipt raises ScreenRefused; then step 0 the floor (not an eligible exact S2 floor run at the
    receipt's fp_cap, c_H_floor and c_H_margin, or a c_H,used that is not max(c_H_floor, c_pF1 + c_H_margin) on the
    grid); the windows (V calendar 2025's 250 sessions, H 194..251 sessions inside 2026-01-02 .. min(config.LOOK_CAP,
    S2_LOOK_CAP)); step 1 the pre-check; step 2 the look (sum_h, t_H)."""
    if not isinstance(receipt, ReceiptS2):
        raise ScreenRefused("the share screen S2 refuses: no S2 receipt is pinned")
    fl = program_floor if isinstance(program_floor, Mapping) else {}
    windows = _windows(v, h, cap=min(config.LOOK_CAP, S2_LOOK_CAP))
    pre = precheck(v)
    s1 = s1_floor if isinstance(s1_floor, Mapping) and s1_floor.get("eligible") is True else None
    out: dict[str, Any] = {
        "screen": SCREEN_S2, "passed": False, "why": None, "c_R": 0.0, "c_pF1": None, "c_H": None, "t_H": None,
        "sum_h": None, "t": None, "n": None, "precheck": pre, "look": None, "windows": windows,
        "label": label(v, h, c_X=receipt.c_X), "own_fp": None, "holdout_only": None, "drift_kept": None,
        "fp_x": fp_at(s1, "X", receipt.c_X) if s1 is not None else None, "fp_cap": receipt.fp_cap,
        "r4": r4_flags(receipt), "deviations": list(DEVIATIONS), "receipt": receipt.receipt_sha256}
    if fl.get("screen") == SCREEN_S2 and fl.get("eligible") is not True:
        why = fl.get("why") or "not eligible"
    else:
        why = _floor_misfit_s2(fl, receipt)
    c_pf1 = _on_grid(fl.get("c_pF1"))
    k_used = None
    if why is None:
        # c_H,used again from the floor's c_pF1 and the RECEIPT's floor and margin, in grid steps: a floor (or a cached
        # copy) whose c_H,used is not that number judges nothing.
        used = _on_grid(fl.get("c_H_used"))
        k_used = None if c_pf1 is None else max(_k(receipt.c_H_floor), _k(c_pf1) + _k(receipt.c_H_margin))
        if k_used is None or k_used > _K_MAX or used is None or _k(used) != k_used:
            why = (f"c_H,used {fl.get('c_H_used')!r} is not max(c_H_floor, c_pF1 + c_H_margin) on 0.00..5.00 "
                   f"(c_pF1 {fl.get('c_pF1')!r})")
    if why is not None or k_used is None:
        out["why"] = f"step 0, the floor: {why}"
        return out
    c_H = k_used / 100
    lk = look_s2(v, h, c_H=c_H)
    out.update(c_pF1=c_pf1, c_H=c_H, t_H=lk["t_H"], sum_h=lk["sum_h"], t=lk["t"], n=lk["n"], look=lk,
               own_fp=_number(fl.get("own_fp"), 0.0, 1.0), holdout_only=_number(fl.get("holdout_only"), 0.0, 1.0),
               drift_kept=_number(fl.get("drift_kept"), 0.0, 1.0))
    if not windows["ok"]:
        out["why"] = f"the windows: {windows['why']}"
    elif not pre["passed"]:
        out["why"] = "step 1, the pre-check: " + ", ".join(k for k, ok in pre["checks"].items() if not ok)
    elif not lk["passed"]:
        out["why"] = "step 2, the look: " + ", ".join(k for k in ("sum_h", "t_H") if not lk["checks"][k])
    else:
        out["passed"] = True
    return out


def beside_line_s2(result: Mapping[str, Any], receipt: ReceiptS2) -> str:
    """Receipt 2's `beside` template filled from a `verdict_s2` (stated beside every live trade of the program): {c_H}
    c_H,used, {own_fp} its FP at zero edge, {honly} its holdout-only rate, {n1} its drift-kept rate, {alpha|beta} the
    S1-X label, {fpx} S1-X's FP; R4 flags appended as S1's. Percentages at two decimals, thresholds at the grid's; a
    figure the verdict lacks reads "unmeasured"."""
    if not isinstance(receipt, ReceiptS2):
        raise ScreenRefused("the share screen S2 refuses: no S2 receipt is pinned")
    if result.get("screen", SCREEN_S2) != SCREEN_S2:
        raise ValueError(f"a {result.get('screen')} verdict beside receipt 2's line")
    lab = result.get("label")
    fill = {"c_H": _c(result.get("c_H")), "own_fp": _pct(result.get("own_fp")),
            "honly": _pct(result.get("holdout_only")), "n1": _pct(result.get("drift_kept")),
            "alpha|beta": lab if lab in ("alpha", "beta") else "unlabelled", "fpx": _pct(result.get("fp_x"))}
    line = receipt.beside
    for key, value in fill.items():
        line = line.replace("{" + key + "}", value)
    flags = list(result.get("r4") or ())
    if flags:
        line += "; R4 flags: " + "; ".join(str(f) for f in flags)
    return line


__all__ = ["SCREEN", "C_GRID_STEP", "C_GRID_MAX", "H_LENGTHS", "V_LENGTH", "WORLDS", "MIN_POOL", "WORLD_SETS",
           "ACTIVITY_ROUND_TRIPS", "ACTIVITY_INVESTED_DAYS", "SAME_LINEAGE_CORR", "RECEIPT_PATH", "DEVIATIONS",
           "LOOKS_PER_LINEAGE", "VALIDATION_TRIES", "GRID", "SET_SEGMENTS", "RECEIPT_KEYS", "BESIDE_FIELDS",
           "ScreenRefused", "Receipt", "Series", "receipt_sha256", "pinned_receipt", "load_receipt", "series", "excess",
           "precheck", "pooled_t", "holdout_t", "look", "floor", "fp_at", "label", "verdict", "beside_line",
           "retry_permitted", "look_permitted", "same_lineage", "r4_flags",
           "SCREEN_S2", "SCREENS", "RECEIPT_PATH_S2", "S2_SETS", "S2_MIN", "S2_LOOK_CAP", "RECEIPT_KEYS_S2",
           "BESIDE_FIELDS_S2", "S2_METHOD", "NO_SET_WHY", "ReceiptS2", "screen_of", "receipt_path", "pinned_receipt_s2",
           "load_receipt_s2", "floor_s2", "floor_fits", "look_s2", "verdict_s2", "beside_line_s2"]
