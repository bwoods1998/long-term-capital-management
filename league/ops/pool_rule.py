"""POOL1, THE POOLED-BY-MECHANISM FORWARD SCREEN's rule (the owner's A55, pre-registered in A55a:
scratch/pooled-screen/PREREG-POOL1.md sha256 f42bcdc1..., `PREREG_SHA256`), pure: the pin, the receipt it pins (THE
RECEIPT CONTRACT POOL1-RECEIPT-1, scratch/pooled-screen/RECEIPT-CONTRACT.md: `CONTRACT`), the calibration's own pinned
code it computes every gated definition with (`calib`), the conformance vectors that hold the two together
(`conform`), the forward statistic, the caps, the bar, the placebo leg, the void, the demotion, the route and the
words. No store, no file but the repository's policy.json, the receipt and the vendored calibration code, no clock.

Owner: the POOL1 build (league/ops/pool_screen.py is its job). Protected (league/ops/ is FORBIDDEN to every role): the
judge is never a role's to move. Ops only: no module of league/swarm, league/equity, league/live or league/gym imports
it (the swarm reads the job's permit file of ids and words, league/swarm/elane_forward.py `pool_listed`).

THE CALIBRATION IS AUTHORITATIVE (the contract's 0.1). Every definition the calibration gates is computed here with
the calibration's own pinned functions, VENDORED BYTE FOR BYTE in league/ops/pool_calib/ (`CALIB_FILES`, each file's
sha256 in `CALIB_SHA256` and in the receipt's `calibration.vendored`; `calib` loads them and refuses on any
difference): the statistic in its null worlds N0, N0R and N1, the world weighting, the windows, the regime cells and
their cutpoints, the bootstrap and its 97.5% bound, the floors (R-REG, POOLED) and the raise to the wall, c_own, the
copy merge, the cells, the clusters and the member rule, rho_assign, the ticket kinds and the bar
(league/ops/pool_calib/p1cluster.py: `member_from_runs`, `merge_copies`, `cells_and_clusters`, `join_clusters`,
`z_on_calendar`, `corr_common`, `cluster_cells`, `cluster_point`, `cluster_boot_one`, `shares_from`, `cluster_floor`,
`caps_rule`, `k_used_for`, `event_word`). The founders, their cells, clusters, tickets, U_u by checkpoint count, the
pin's floors, stage 1, the matched-family minimum and the regime cutpoints are READ FROM THE RECEIPT. What P1 keeps of
its own is what the calibration never computes: the forward days and their statistic (`alpha`, `w_hat`, `cell_day`,
`t_stat`, `look`, `legs_pass`, held to the receipt's conformance vectors CV1 and CV2), the placebo leg, the zeroed-days
void, the demotion, routes, permits and words.

THE RULE (the PREREG's sections, each function naming its own):
1. THE UNIT (section 1). A CELL is (class, group), both read by the House: a founder's are the receipt's; a later
   lineage's group is `member_from_runs`' (the base group over 2/3 of its Train exposure) and its cell is ASSIGNED
   (`assign`) to the cell of its group whose FOUNDERS' Train D (the nanmean of their `z_on_calendar`) its own Train z
   correlates with most (`corr_common`, at least 30 common finite sessions), when that is at least the receipt's
   rho_assign (null: never). OUT (`excluded`, then `member_from_runs`): panels, stock programs, the beta class
   equity_premium, event readers (card input `event_calendar`, or a frozen code `reads_events`: the House job's word
   scan `\\bevents(?:_next)?\\b` anywhere, a ctx-field AST scan and unparseable text, their union), no declared class,
   a Train mean total exposure under 1%, no base group above 2/3. A MEMBER is a lineage's first passing version
   (`member_pid`). THE COPY MERGE (`merge_copy`: `merge_copies`' rule against every earlier member by pid) keeps the
   earlier pid. The clusters are the receipt's; at a look they are re-tested by `join_clusters` (`cluster`).
2. THE STATISTIC (section 2). On a counted day t of member i: r^g = r - g sides (r_ll in place of r where `fwd_ll` has
   a row, and r15 + (r_ll - r) in place of r15: FWD1's), a_t = r^g_t - sum_s w_st mu_s - sum_s what_st (R_st - mu_s),
   a15 = a - (r - r15) (`alpha`); what_st = (PRIOR wbar_s + the sum of w_s over the member's earlier counted days since
   it joined) / (PRIOR + their count), decided at t-1 (`w_hat`); mu, wbar and sigma are the vendored `fit_constants`'
   at the 2 bp floor haircut (the same sigma serves the floor's z and the forward z); z = a / sigma_used,
   sigma_used = max(sigma, 5 bp, sigma_tilde / 3), sigma_tilde = 1 / median(1 / sigma_j) over the cell's founders.
   D_t = the mean of z over the cell's ACTIVE members, an absent row 0 (`cell_day`); a CELL SESSION has at least
   `M_MIN` counted rows. T_k = mean / sd (ddof 1) x sqrt(k) by math.fsum at k in `PLAN`; PASS_k: T_k >= c_used,
   fsum(D15_1..k) > 1e-12, and the placebo leg (`placebo_holds`).
3. THE BAR (section 3.3; the contract's 3.2 and 4.1). c_own is the vendored `cluster_floor`'s IN-fitted c_own of the
   receipt's floor definition, on the cluster's members active through the look (their joins, the receipt's boot seed,
   the caps of the checkpoint count read), through `house_floor`; k_own = max(c_own, the matched-family minimum read
   from the receipt's table, `Receipt.matched`); c_used = max(c_G, k_own + margin) on the 0.01 grid, INELIGIBLE (no
   verdict, stated) without c_own or above 5.00 (`k_used`, held to `k_used_for` by CV12). THE CAPS (`caps`, held to
   `caps_rule` by CV10): CAP_u = 0.12 - U_u, WALL_u = 0.15 - max(U_u(97.5%), U_u); REPORT-ONLY when U_u >= 0.12, when
   U_u's bound >= 0.15 (WALL_u <= 0), when a ticket could not be computed, or when a figure is not finite.
4. THE REST: the zeroed-days void (`mar_void`, section 2.2), the placebo leg's seed, draws and count (section 2.1),
   the cell demotion (`demote`, section 7.1), the POOL route (`on_pool_route`, section 7.2), the words (`words`,
   section 8), the operator's sentence beside a pooled trade (`beside`) and the floor-wide expected zero-edge passes
   (`expected_passes`, section 4.5, per cluster).

THE PIN (`pin`, `load`): policy.json `elane.pool_screen` of the REPOSITORY (never the box's swarm.json), {"name":
"POOL1", "prereg_sha256", "receipt_sha256", every constant of `CONSTANTS` (the receipt's `constants`, checked twice)
and "p1": `P1_RULE` (P1's own constants)}. `load` refuses (None, why) a missing or malformed key, a sha that is not 64
lower-case hex characters, the wrong PREREG and any constant other than this code's. THE RECEIPT (`load_receipt`,
`parse_receipt`, the contract's sections 2 and 3): docs/benchmarks/pool_screen_1.json, read only when its sha256 is
the pin's, parsed with NaN and Infinity refused, refused whole on any missing, mistyped or unknown key; then the
vendored code's shas are checked against `CALIB_SHA256` and the receipt's, and every conformance vector is reproduced
(`conform`, to 1e-9; integers exact). NO PIN, NO RECEIPT, NO CONFORMANCE, NO VERDICT: the job records nothing judged,
writes no route list and starts no clock.

Standard library at import; numpy (and the vendored calibration code) inside the functions that read arrays.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import math
import re
import sys
import warnings
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from typing import Any, Callable, Collection, Iterable, Mapping, Sequence

from . import fwd1_rule as F

NAME = "POOL1"
SCREEN = "POOL1"
#: policy.json `elane.<PIN_BLOCK>` of the REPOSITORY (the settings of the job are `elane.pool`).
PIN_BLOCK = "pool_screen"
RECEIPT_PATH = "docs/benchmarks/pool_screen_1.json"
#: The receipt contract this code parses (scratch/pooled-screen/RECEIPT-CONTRACT.md) and its conformance version.
CONTRACT = "POOL1-RECEIPT-1"
CONFORMANCE = "POOL1-CONF-1"
TOLERANCE = 1e-9
#: The pre-registration this code implements (scratch/pooled-screen/PINS.log; the captain's A55a).
PREREG_SHA256 = "f42bcdc1d694d9be910da298fc2e62e0d4898003645af9a0a04523eb34ac38da"

# ------------------------------------------------------------------------------------------------------ constants
#: THE RECEIPT'S CONSTANTS (the contract's 3.3), as this code holds them: the receipt's `constants` must be exactly
#: these, and so must the pin's.
PLAN = (40, 60, 120)
WINDOW = 120
M_MIN = 3
PRIOR = 20
SIGMA_FLOOR = 5e-4
WEIGHT_CAP = 3.0
GROUP_SHARE = Fraction(2, 3)
COPY_RHO = 0.7
MIN_EXPOSURE = 0.01
EXPOSURE_MIN = MIN_EXPOSURE
CAP = 0.12
WALL = 0.15
WORST = 0.15
N1_OFFSETS = (262, 409, 535, 661, 787)
#: The null worlds' haircut (FWD1-R's 2 bp a side, the calibration's D9); the forward statistic's is the measured one.
FLOOR_HAIRCUT = 2e-4
K_STRESS = 1.5
K_MAX = F.K_MAX
BOOT_RESAMPLES = 2000
BOOT_BLOCK = 120
SEED_ROOT = 20261026
BOUND = "max(q975, point + q975 - mean)"
STAGE1_Z = -1.0
STAGE1_LAG = 5
RHO_ASSIGN_Q = 0.25
#: The FWD1-R checkpoint counts U_u is tabulated by (0: S2 alone), and the count the calibration's G6 read.
U_COUNTS = (0, 5, 10, 15, 20, 30, 40, 60)
U_PIN_COUNT = 5
PLACEBO_DRAWS = 999
PLACEBO_COUNT_MAX = 149
CONSTANTS: dict[str, Any] = {
    "plan": list(PLAN), "window": WINDOW, "m_min": M_MIN, "prior": PRIOR, "sigma_floor": SIGMA_FLOOR,
    "weight_cap": WEIGHT_CAP, "group_share": "2/3", "copy_rho": COPY_RHO, "min_exposure": MIN_EXPOSURE, "cap": CAP,
    "wall": WALL, "worst": WORST, "n1_offsets": list(N1_OFFSETS), "floor_haircut": FLOOR_HAIRCUT,
    "k_stress": K_STRESS, "k_max": K_MAX, "boot_resamples": BOOT_RESAMPLES, "boot_block_mean": BOOT_BLOCK,
    "seed_root": SEED_ROOT, "bound": BOUND, "stage1": {"z": STAGE1_Z, "lag": STAGE1_LAG},
    "rho_assign_q": RHO_ASSIGN_Q, "u_counts": list(U_COUNTS), "u_pin_count": U_PIN_COUNT,
    "placebo": {"draws": PLACEBO_DRAWS, "count_max": PLACEBO_COUNT_MAX},
}
#: P1'S OWN CONSTANTS (never the calibration's: the forward days' rules), pinned beside them as the pin's "p1".
NO_FREE_RIDE = 20
PLACEBO_CONTROLS = 50
MAR_FACTOR = 2
MAR_P = 0.05
MAR_DECILE = Fraction(1, 10)
DEMOTE_EVERY = 20
DEMOTE_T_POST = -1.0
DEMOTE_T_ALL = 0.0
DEMOTE_STRESS_AT = (60, 120)
P1_RULE: dict[str, Any] = {
    "no_free_ride": NO_FREE_RIDE, "placebo_controls": PLACEBO_CONTROLS,
    "mar": {"factor": MAR_FACTOR, "p": MAR_P, "decile": "1/10"},
    "demote": {"every": DEMOTE_EVERY, "t_post": DEMOTE_T_POST, "t_all": DEMOTE_T_ALL,
               "stress_at": list(DEMOTE_STRESS_AT)},
}
PIN_KEYS = ("name", "prereg_sha256", "receipt_sha256", *CONSTANTS, "p1")
#: A unit's floor definitions and margins (the calibration adopts one of the six), and c_G's grid range.
FLOORS = ("R-REG", "POOLED")
MARGINS_K = (0, 3, 5)
C_G_K_RANGE = (140, 250)
ZERO = F.ZERO
NULLS = ("N0", "N0R", "N1")
SPANS = ("e0", "e1", "IN")
#: The base groups a cell may be of, and the classes that are out of every cell (a beta claim: S2 and FWD1-R judge it).
BASE_GROUPS = ("index", "sectors", "defensive")
CLASSES_OUT = ("equity_premium",)
#: An event reader: the card input; the ctx fields a frozen code may name; the House job's word scan (`EVENT_WORD`,
#: league/ops/pool_calib/pool1_house_job.py's and p1cluster.event_word's).
EVENT_INPUT = "event_calendar"
EVENT_FIELDS = ("events", "events_next")
EVENT_WORD = re.compile(r"\bevents(?:_next)?\b")
#: The registry reasons a member is the first of (FWD1's representative reasons).
PASSING = ("train_pass", "seed", "live")
#: The House job's Train parts of a member (a Train era at k 1.0 and 1.5).
PARTS = ("e0k10", "e0k15", "e1k10", "e1k15")
#: The words a unit may stand at. "pending" until its verdict; a final word is one of `FINAL`; a report-only
#: cluster's units carry "report_only" in every file but the operator's report.
PENDING = "pending"
FINAL = ("PASS", "FAIL", "DEMOTED", "VOID", "REFUTED")
REPORT_ONLY = "report_only"
#: A unit with no bar on the grid (c_used above 5.00, or no common span: the receipt's `ineligible`): no verdict,
#: stated (section 3.3). Its looks are over, so no lineage joins it, but no generator is told a word for it.
INELIGIBLE = "ineligible"
#: A founding cluster whose floors at the clock are not the receipt's (the contract's 6.4): not clocked, its members
#: stay on their per-program routes; only a captain amendment can clock it.
NONCONFORMING = "nonconforming"
WORDS = (PENDING, REPORT_ONLY, INELIGIBLE, NONCONFORMING, *FINAL)
SECTOR_ETFS = ("XLB", "XLC", "XLE", "XLF", "XLI", "XLK", "XLP", "XLRE", "XLU", "XLV", "XLY")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_CELL = re.compile(r"^[a-z_]+/(index|sectors|defensive)$")
_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


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
    extra = sorted(str(k) for k in block if k not in PIN_KEYS)
    if extra:
        return None, f"the pooled screen's pin holds keys this code does not read: {', '.join(extra)}"
    if block.get("name") != NAME:
        return None, f"the pin names {block.get('name')!r}, this code runs {NAME}"
    if block.get("prereg_sha256") != PREREG_SHA256:
        return None, "the pin names another pre-registration than the one this code implements"
    sha = block.get("receipt_sha256")
    if not isinstance(sha, str) or not _HEX64.match(sha):
        return None, "the pin's receipt_sha256 is not 64 lower-case hex characters"
    for key, want in CONSTANTS.items():
        if not _same(block.get(key), want):
            return None, f"the pin's {key} is not this code's"
    if not _same(block.get("p1"), P1_RULE):
        return None, "the pin's p1 constants are not this code's"
    return Pin(receipt_sha256=sha), None


# --------------------------------------------------------------------------------------- the vendored calibration
#: THE CALIBRATION'S PINNED CODE, vendored byte for byte (the contract's section 5): league/ops/pool_calib/, no
#: __init__.py, never edited, reformatted or linted into shape. Loaded in this order, each registered in
#: `sys.modules[<stem>]` before it runs, so their own `import p1const` resolves (sys.path is not touched).
CALIB_DIR = Path(__file__).resolve().parent / "pool_calib"
CALIB_FILES = ("p1const.py", "p1stat.py", "p1members.py", "p1units.py", "p1engine.py", "p1cluster.py", "p1conform.py",
               "pool1_house_job.py")
#: Each vendored file's sha256 (the receipt's `calibration.vendored` must name the same; scratch/pooled-screen/PINS.log
#: "THE VENDORED SET"): p1const, p1stat, p1members, p1units and p1engine at CODE PIN 1 (18:30:54Z Oct 16: the
#: preparation's PREP_CODE), pool1_house_job.py at CODE PIN 1, p1cluster and p1conform at CODE PIN 3 (22:23:50Z Oct 16).
#: A value of None would be a file not pinned yet: nothing loads, nothing is judged.
CALIB_SHA256: dict[str, str | None] = {
    "p1const.py": "e2bd332870afece7fd2e420c15f1f71b4d944cfff1e6d4835273b9097f54f549",
    "p1stat.py": "2dc117dfec825609b531a6075c067320d4a9cc78a104c6f5e88cf2c54fbfa986",
    "p1members.py": "c6e61f896d5c3fcc88f0500316c9d6837e4e9eb237dc2ad09dd6a7e9839bbe9a",
    "p1units.py": "3ca473f68017366c559d3c2d09a7dd35d3793f523133f0e7dccb47ff9309066e",
    "p1engine.py": "d9fdf13eff203557f65c44eaff30ee029e2e5b7f68e1c80ae0b270d1cc60e920",
    "p1cluster.py": "97ccad275e34d35394329cc2a66abb25c52ddf433475a28286b6e88aa8af9b62",
    "p1conform.py": "829b76672bba59dc46af7839b4813f2b10249426e719029c0112568056735632",
    "pool1_house_job.py": "9f6ab090b3e06226ccedd28ec99b3317c81138bd656d425e156c216045ccadc9",
}
#: THE CALIBRATION'S CODE AT ITS PIN (the conformance review's finding 6; scratch/pooled-screen/PINS.log): the
#: calibration's run code (its p1run `CODE_FILES`), each file at the sha of its LATEST pin (CODE PIN 1's but for the
#: driver, CODE PIN 2's, and the seven CODE PIN 3 changed or added). A pinned receipt (`parse_receipt` outside a test's
#: own constants) must print `CODE_PIN` as its code pin and name every one of these files at exactly this sha in
#: `calibration.code_sha256`: a file reverted to an earlier pin's sha (which the calibration's preconditions accept,
#: since they look a sha up anywhere in PINS.log) is refused here, whatever label the run printed.
CODE_PIN = "CODE PIN 3"
CODE_PIN_SHA256: dict[str, str] = {
    "p1const.py": "e2bd332870afece7fd2e420c15f1f71b4d944cfff1e6d4835273b9097f54f549",
    "p1data.py": "5152b1ccbd7b804ac92602710d2421ef499ba1aa06cd463fcd0253d21d55e17f",
    "p1stat.py": "2dc117dfec825609b531a6075c067320d4a9cc78a104c6f5e88cf2c54fbfa986",
    "p1members.py": "c6e61f896d5c3fcc88f0500316c9d6837e4e9eb237dc2ad09dd6a7e9839bbe9a",
    "p1units.py": "3ca473f68017366c559d3c2d09a7dd35d3793f523133f0e7dccb47ff9309066e",
    "p1engine.py": "d9fdf13eff203557f65c44eaff30ee029e2e5b7f68e1c80ae0b270d1cc60e920",
    "p1fam.py": "b74d64eef27323d2a188ed83f1af36ee8b38dfc9a521e542f0de20a0d27dba8a",
    "p1twins.py": "fffd9f7b92e7d5b1447bcce5928204be66459ae91a0c3a199bf9520697ace4e0",
    "p1synth.py": "d34a5540ff12b1d6de8575a88c5ebc1249b8266cbbbaccb92a23268e1b246043",
    "p1prep.py": "5c5fd5046cca9ed626d81de5fbdb81de477b1d7382acbed35812af2eef6aa60b",
    "p1house.py": "325b0579612091906ee77e2eb081227f7ae2cc04a175e5ecfce3f0425d674656",
    "p1tickets.py": "a9aff2b253a125c2e311ea652df40814cbdf3acb4d15c95ac890672f36508590",
    "p1gates.py": "89967249ee0a0a723ba576a24f0aeeb26d175bee2488d9826f09cd3e079eeaa1",
    "p1run.py": "db61f2c80a9cab55aa064477c9603e53da84c9f1f0796960d40521d4ee391d98",
    "p1report.py": "59c55c78edd62a8dceacffd684dc16df0c1a62118bb365696397174eead0b17c",
    "p1cluster.py": "97ccad275e34d35394329cc2a66abb25c52ddf433475a28286b6e88aa8af9b62",
    "p1conform.py": "829b76672bba59dc46af7839b4813f2b10249426e719029c0112568056735632",
    "house_job/pool1_house_job.py": "9f6ab090b3e06226ccedd28ec99b3317c81138bd656d425e156c216045ccadc9",
    "house_job/drive.py": "2684e305ee9fc81d9768ddb7d7ac95390e5af51965a006c42ad09196cca5d020",
    "read_decision.py": "a3e6bb2472adb909518eb2b908c866743a3d74bc8b69e1fddbe429f78c915bf0",
}


@dataclass(frozen=True)
class Calib:
    """The vendored calibration code, loaded and checked (`calib`): its modules and every file's sha256."""

    K: Any
    stat: Any
    members: Any
    units: Any
    engine: Any
    cluster: Any
    conform: Any
    house_job: Any
    sha256: Mapping[str, str]
    root: str


_CALIB: dict[tuple, tuple[Calib | None, str | None]] = {}


def file_sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def calib(*, root: str | Path | None = None, shas: Mapping[str, str | None] | None = None
          ) -> tuple[Calib | None, str | None]:
    """THE VENDORED CALIBRATION (the contract's section 5), loaded once a process (`root`, `shas`: a test's own
    directory and shas; default `CALIB_DIR`, `CALIB_SHA256`): (the modules, None), or (None, why) when a file is
    missing, a sha is not pinned or is not its file's, a module does not load, or p1const is not the real run's
    (`FAKE` not False, `B_BOOT` not 2000, another PREREG). Nothing is judged without it."""
    base = Path(root) if root is not None else CALIB_DIR
    want = dict(CALIB_SHA256 if shas is None else shas)
    key = (str(base), tuple(sorted((k, v) for k, v in want.items() if v is not None)),
           tuple(sorted(k for k, v in want.items() if v is None)))
    if key in _CALIB:
        return _CALIB[key]
    out = _load_calib(base, want)
    _CALIB[key] = out
    return out


def _load_calib(base: Path, want: Mapping[str, str | None]) -> tuple[Calib | None, str | None]:
    got: dict[str, str] = {}
    for name in CALIB_FILES:
        sha = want.get(name)
        if not isinstance(sha, str) or not _HEX64.match(sha):
            return None, f"the vendored calibration's {name} is not pinned yet (no CODE PIN sha in this code)"
        path = base / name
        try:
            got[name] = file_sha256(path)
        except OSError:
            return None, f"the vendored calibration's {name} is missing"
        if got[name] != sha:
            return None, f"the vendored calibration's {name} is not the pinned file (sha256 differs)"
    mods: dict[str, Any] = {}
    try:
        for name in CALIB_FILES:
            stem = name[:-3]
            spec = importlib.util.spec_from_file_location(stem, base / name)
            if spec is None or spec.loader is None:
                return None, f"the vendored calibration's {name} cannot be loaded"
            mod = importlib.util.module_from_spec(spec)
            sys.modules[stem] = mod
            spec.loader.exec_module(mod)
            mods[stem] = mod
    except BaseException as exc:  # noqa: BLE001 - p1const raises SystemExit on a fake run's paths
        if isinstance(exc, (KeyboardInterrupt, GeneratorExit)):
            raise
        return None, f"the vendored calibration does not load ({type(exc).__name__})"
    K = mods["p1const"]
    if getattr(K, "FAKE", None) is not False:
        return None, "the vendored p1const is a dry run's (FAKE): nothing is judged"
    if getattr(K, "B_BOOT", None) != BOOT_RESAMPLES:
        return None, "the vendored p1const's B_BOOT is not 2000"
    if getattr(K, "PREREG_SHA256", None) != PREREG_SHA256:
        return None, "the vendored p1const names another pre-registration"
    return Calib(K=K, stat=mods["p1stat"], members=mods["p1members"], units=mods["p1units"], engine=mods["p1engine"],
                 cluster=mods["p1cluster"], conform=mods["p1conform"], house_job=mods["pool1_house_job"],
                 sha256=dict(got), root=str(base)), None


# -------------------------------------------------------------------------------------------------------- the receipt
#: THE RECEIPT'S TOP-LEVEL KEYS (the contract's section 2): every one required, none other allowed.
RECEIPT_KEYS = ("name", "contract", "prereg_sha256", "status", "run", "calibration", "rule", "constants", "regimes",
                "rho_assign", "founders", "units", "clusters", "matched_floor", "market", "conformance", "record")
REGIME_AXES = ("vol", "ret", "disp", "gap")
BESIDE_KEYS = ("fp_point", "fp_bound", "fp_worst", "fp_n1", "power_05", "power_10")
FOUNDER_KEYS = ("pid", "family", "version", "lane", "ugroup", "first_day", "class", "infer_key_class", "status", "why",
                "merged_into", "group", "cell", "judged", "cluster", "ticket", "fwd1_type", "fwd1_case", "fwd1_judged",
                "reached_sealed", "seat_shape", "program_sha", "train_sha256")
UNIT_KEYS = ("class", "group", "cluster", "members", "m", "refuted", "report_only", "ineligible")
CLUSTER_KEYS = ("cells", "classes", "members", "joins", "boot_seed", "span", "windows", "tickets", "U", "caps_at_pin",
                "report_only", "ineligible", "ineligible_why", "stage1", "c_own_at_pin", "seat_members", "expected",
                "beside")
PIN_FLOOR_KEYS = ("N0", "N0R", "N1", "c_own", "minimum", "k_used")
CALIBRATION_KEYS = ("code_pin", "code_pin_utc", "code_sha256", "vendored", "pins_log_sha256", "deviations_log_sha256",
                    "decision_sha256", "decision_in_sha256", "prep_manifest_sha256", "house_export", "python", "numpy")
HOUSE_EXPORT_KEYS = ("meta_sha256", "prices_sha256", "status_sha256", "units", "saved", "failed_twice")
CAPS_WHY = ("u_point", "u_bound", "tickets_dropped")
CV_IDS = tuple(f"CV{i}" for i in range(1, 13))


class ReceiptRefused(ValueError):
    """A receipt that is not the contract's: the first defect, in words."""


@dataclass(frozen=True)
class Founder:
    lineage: str
    pid: int
    family: str
    version: Any
    lane: str
    ugroup: str
    first_day: str
    cls: str | None
    infer_key_class: str | None
    status: str
    why: str | None
    merged_into: str | None
    group: str | None
    cell: str | None
    judged: bool
    cluster: str | None
    ticket: str | None
    fwd1_type: str | None
    fwd1_case: str | None
    fwd1_judged: int | None
    reached_sealed: bool
    seat_shape: bool
    program_sha: str | None
    train_sha256: Mapping[str, str] | None

    @property
    def member(self) -> bool:
        return self.status == "member"


@dataclass(frozen=True)
class UnitSpec:
    cell: str
    cls: str
    group: str
    cluster: str
    members: tuple[str, ...]
    m: int
    refuted: bool
    report_only: bool
    ineligible: bool

    @property
    def founders(self) -> tuple[str, ...]:
        return self.members


@dataclass(frozen=True)
class ClusterSpec:
    cid: str
    cells: tuple[str, ...]
    classes: tuple[str, ...]
    members: tuple[str, ...]
    joins: tuple[tuple[str, str], ...]
    boot_seed: int
    span: Mapping[str, Any]
    windows: Mapping[str, int]
    tickets: Mapping[str, Any]
    U: Mapping[int, tuple[float, float]]
    caps_at_pin: Mapping[str, Any]
    report_only: bool
    ineligible: bool
    ineligible_why: str | None
    stage1: Mapping[str, Any]
    c_own_at_pin: Mapping[str, Mapping[str, int | None]]
    seat_members: tuple[str, ...]
    expected: Mapping[str, tuple[float, ...]]
    beside: Mapping[str, float | None]

    @property
    def refuted(self) -> bool:
        return bool(self.stage1.get("refuted"))

    @property
    def dropped(self) -> tuple[Mapping[str, Any], ...]:
        return tuple(self.tickets.get("dropped") or ())


@dataclass(frozen=True)
class Rule:
    name: str
    floor_def: str
    margin_k: int
    c_G_k: int

    @property
    def margin(self) -> float:
        return self.margin_k / 100.0

    @property
    def c_G(self) -> float:
        return self.c_G_k / 100.0


@dataclass(frozen=True)
class Receipt:
    """A parsed receipt (`parse_receipt`; the contract's sections 2 and 3): the adopted rule, the constants, the IN
    cutpoints, rho_assign, the founders, the judged cells and the founding clusters, the matched-family table, the
    market's ids, the conformance vectors and the ids the receipt rests on."""

    sha256: str
    rule: Rule
    constants: Mapping[str, Any]
    regimes: tuple[tuple[float, float], ...]
    rho_assign: float | None
    founders: Mapping[str, Founder]
    units: Mapping[str, UnitSpec]
    clusters: Mapping[str, ClusterSpec]
    matched_floor: Mapping[str, Mapping[str, Mapping[str, Any]]]
    market: Mapping[str, Mapping[str, Any]]
    conformance: Mapping[str, Any]
    calibration: Mapping[str, Any]
    run: Mapping[str, Any]
    doc: Mapping[str, Any] = field(default_factory=dict, repr=False)

    # the adopted rule under its old names
    @property
    def floor(self) -> str:
        return self.rule.floor_def

    @property
    def c_G(self) -> float:
        return self.rule.c_G

    @property
    def margin(self) -> float:
        return self.rule.margin

    @property
    def B(self) -> int:
        """The resamples of every bound (the receipt's `boot_resamples`: 2000 outside a test's own constants)."""
        return int(self.constants["boot_resamples"])

    def cluster_of(self, cell: str) -> str | None:
        unit = self.units.get(cell)
        return None if unit is None else unit.cluster

    def cuts(self) -> Any:
        """The (4, 2) IN tercile cutpoints in the order vol, ret, disp, gap (p1members.cells_of's)."""
        import numpy as np

        return np.array([list(c) for c in self.regimes], dtype=np.float64)

    def u_at(self, cid: str, count: int) -> tuple[float, float] | None:
        """U_u (point, bound) of a founding cluster at the FWD1-R checkpoint count read before the clock (P1 D7): the
        row of the smallest tabulated count at or above it; None above the table (60): the cluster is report-only."""
        table = self.clusters[cid].U
        for c in sorted(table):
            if c >= int(count):
                return table[c]
        return None

    def matched(self, group: str, cls: str, m: int, floor_def: str | None = None) -> int | None:
        """The matched stand-in family's N1 floor (the contract's 3.9: a lookup, no rule of P1's own) of a cell of `m`
        members; None when the table has no row (above 60: no bar, the look waits)."""
        rows = ((self.matched_floor.get(group) or {}).get(cls) or {}).get(floor_def or self.rule.floor_def) or {}
        v = rows.get(str(int(m)))
        return None if v is None else int(v)


def _no_constant(token: str) -> Any:
    raise ReceiptRefused(f"the receipt holds the token {token}: no NaN or Infinity is allowed")


def _is_int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _is_num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(float(v))


def _is_share(v: Any) -> bool:
    return _is_num(v) and 0.0 <= float(v) <= 1.0


def _is_hex(v: Any) -> bool:
    return isinstance(v, str) and bool(_HEX64.match(v))


def _is_str_or_none(v: Any) -> bool:
    return v is None or isinstance(v, str)


def _is_k(v: Any, *, top: int = K_MAX) -> bool:
    return _is_int(v) and 0 <= v <= top


def _need(ok: bool, why: str) -> None:
    if not ok:
        raise ReceiptRefused(why)


def _keys(obj: Any, keys: Sequence[str], where: str) -> None:
    _need(isinstance(obj, Mapping), f"{where} is not an object")
    have = set(obj)
    missing = [k for k in keys if k not in have]
    _need(not missing, f"{where} lacks {', '.join(missing)}")
    extra = sorted(str(k) for k in have if k not in keys)
    _need(not extra, f"{where} holds keys outside the contract: {', '.join(extra)}")


def _rising(curve: Any, n: int) -> bool:
    return isinstance(curve, list) and len(curve) == n and all(_is_share(v) for v in curve) \
        and all(float(curve[i]) <= float(curve[i + 1]) for i in range(n - 1))


def _check_founders(doc: Mapping[str, Any]) -> None:
    founders = doc["founders"]
    _need(isinstance(founders, Mapping) and bool(founders), "the receipt lists no founders")
    for lineage, f in founders.items():
        w = f"founder {lineage}"
        _need(isinstance(lineage, str) and bool(lineage), "a founder's lineage is not text")
        _keys(f, FOUNDER_KEYS, w)
        _need(_is_int(f["pid"]) and f["pid"] >= 1, f"{w}: no pid")
        for key in ("family", "lane", "ugroup"):
            _need(isinstance(f[key], str), f"{w}: its {key} is not text")
        _need(isinstance(f["first_day"], str) and bool(_DAY.match(f["first_day"])), f"{w}: its first_day is not a date")
        _need(_is_int(f["version"]) or isinstance(f["version"], str), f"{w}: its version is neither a number nor text")
        for key in ("class", "infer_key_class", "fwd1_type", "fwd1_case", "program_sha"):
            _need(_is_str_or_none(f[key]), f"{w}: its {key} is neither text nor null")
        _need(f["fwd1_judged"] is None or _is_int(f["fwd1_judged"]), f"{w}: fwd1_judged is neither a count nor null")
        _need(isinstance(f["reached_sealed"], bool) and isinstance(f["seat_shape"], bool) and isinstance(f["judged"], bool),
              f"{w}: reached_sealed, seat_shape and judged are not booleans")
        status = f["status"]
        _need(status in ("member", "merged", "out"), f"{w}: status {status!r} is not member, merged or out")
        if status == "out":
            _need(isinstance(f["why"], str) and bool(f["why"]), f"{w}: out with no why")
            _need(f["merged_into"] is None and f["cell"] is None and f["cluster"] is None and f["ticket"] is None
                  and f["group"] is None and not f["judged"], f"{w}: out but placed")
            _need(f["train_sha256"] is None or isinstance(f["train_sha256"], Mapping), f"{w}: train_sha256")
            continue
        _need(f["why"] is None, f"{w}: a why while {status}")
        _need(f["group"] in BASE_GROUPS, f"{w}: a group outside the base groups")
        _need(isinstance(f["class"], str) and bool(f["class"]), f"{w}: no declared class")
        tsha = f["train_sha256"]
        _need(isinstance(tsha, Mapping) and set(tsha) == set(PARTS) and all(_is_hex(v) for v in tsha.values()),
              f"{w}: train_sha256 is not one sha a Train part")
        if status == "merged":
            into = f["merged_into"]
            _need(isinstance(into, str) and into in founders, f"{w}: merged into no founder")
            other = founders[into]
            _need(isinstance(other, Mapping) and other.get("status") == "member" and _is_int(other.get("pid"))
                  and other["pid"] < f["pid"], f"{w}: merged into a founder that is no earlier member")
            _need(f["cell"] is None and f["cluster"] is None and f["ticket"] is None and not f["judged"],
                  f"{w}: merged but placed in a cell")
            continue
        _need(f["merged_into"] is None, f"{w}: a member merged into another")
        _need(f["cell"] == f"{f['class']}/{f['group']}" and bool(_CELL.match(str(f["cell"]))),
              f"{w}: its cell is not <class>/<group>")
        _need(f["ticket"] in (None, "S2", "FWD1"), f"{w}: a ticket that is not S2, FWD1 or null")
        if f["judged"]:
            _need(isinstance(f["cluster"], str) and f["cluster"] in doc["clusters"], f"{w}: judged in no cluster")
        else:
            _need(f["cluster"] is None, f"{w}: in a cluster but not judged")


def _check_units(doc: Mapping[str, Any]) -> None:
    founders, units, clusters = doc["founders"], doc["units"], doc["clusters"]
    _need(isinstance(units, Mapping), "the receipt's units are not an object")
    for cell, u in units.items():
        w = f"unit {cell}"
        _need(isinstance(cell, str) and bool(_CELL.match(cell)), f"{w}: not <class>/<base group>")
        _keys(u, UNIT_KEYS, w)
        _need(f"{u['class']}/{u['group']}" == cell, f"{w}: its class and group are not its cell")
        _need(u["cluster"] in clusters, f"{w}: its cluster is not a founding cluster")
        ms = u["members"]
        _need(isinstance(ms, list) and all(isinstance(x, str) and x in founders for x in ms), f"{w}: members unknown")
        _need(len(set(ms)) == len(ms), f"{w}: a member listed twice")
        for x in ms:
            f = founders[x]
            _need(f["status"] == "member" and f["cell"] == cell and f["judged"] is True and f["cluster"] == u["cluster"],
                  f"{w}: {x} is not a judged member of it")
        pids = [founders[x]["pid"] for x in ms]
        _need(pids == sorted(pids), f"{w}: members not in pid order")
        held = sorted(x for x, f in founders.items() if f["status"] == "member" and f["cell"] == cell and f["judged"])
        _need(sorted(ms) == held, f"{w}: its judged members are not all listed")
        _need(_is_int(u["m"]) and u["m"] == len(ms) >= M_MIN, f"{w}: m is not its member count of at least {M_MIN}")
        for key in ("refuted", "report_only", "ineligible"):
            _need(isinstance(u[key], bool), f"{w}: {key} is not a boolean")
    judged_cells = {f["cell"] for f in founders.values() if f["status"] == "member" and f["judged"]}
    _need(judged_cells == set(units), "the units are not the judged members' cells")


def _check_clusters(doc: Mapping[str, Any]) -> None:
    units, clusters, rule = doc["units"], doc["clusters"], doc["rule"]
    _need(isinstance(clusters, Mapping), "the receipt's clusters are not an object")
    seen: set[str] = set()
    for cid, cl in clusters.items():
        w = f"cluster {cid}"
        _need(isinstance(cid, str) and bool(cid), "a cluster id is not text")
        _keys(cl, CLUSTER_KEYS, w)
        cells = cl["cells"]
        _need(isinstance(cells, list) and bool(cells) and all(c in units for c in cells), f"{w}: cells are not units")
        for c in cells:
            _need(c not in seen and units[c]["cluster"] == cid, f"{w}: cell {c} is in two clusters or not its own")
            seen.add(c)
        _need(isinstance(cl["classes"], list) and sorted(set(cl["classes"])) == sorted({units[c]["class"] for c in cells}),
              f"{w}: classes are not its cells'")
        _need(isinstance(cl["members"], list) and sorted(cl["members"]) == sorted(x for c in cells
                                                                                 for x in units[c]["members"]),
              f"{w}: members are not its cells'")
        _need(isinstance(cl["joins"], list) and all(isinstance(j, list) and len(j) == 2 and all(isinstance(x, str) for x in j)
                                                   for j in cl["joins"]), f"{w}: joins are not pairs of ids")
        _need(_is_int(cl["boot_seed"]) and cl["boot_seed"] >= 0, f"{w}: no boot seed")
        span = cl["span"]
        _need(isinstance(span, Mapping) and set(span) == {"e0", "e1"}, f"{w}: span is not by era")
        for e, s in span.items():
            _need(s is None or (isinstance(s, list) and len(s) == 3 and isinstance(s[0], str) and isinstance(s[1], str)
                                and _is_int(s[2])), f"{w}: span {e} is not [first, last, n] or null")
        win = cl["windows"]
        _need(isinstance(win, Mapping) and set(win) == {"e0", "e1"} and all(_is_int(v) and v >= 0 for v in win.values()),
              f"{w}: windows are not counts by era")
        tk = cl["tickets"]
        _keys(tk, ("members", "s2_members", "fwd1_members", "dropped"), f"{w} tickets")
        _need(isinstance(tk["members"], Mapping) and all(x in cl["members"] and v in ("S2", "FWD1")
                                                         for x, v in tk["members"].items()),
              f"{w}: ticket members are not its members' kinds")
        _need(_is_int(tk["s2_members"]) and _is_int(tk["fwd1_members"]), f"{w}: ticket counts are not counts")
        _need(isinstance(tk["dropped"], list), f"{w}: dropped tickets are not a list")
        for d in tk["dropped"]:
            _keys(d, ("lineage", "kind", "why"), f"{w} dropped ticket")
            _need(isinstance(d["lineage"], str) and d["kind"] in ("S2", "FWD1") and isinstance(d["why"], str),
                  f"{w}: a dropped ticket is not (lineage, kind, why)")
        U = cl["U"]
        _need(isinstance(U, Mapping) and set(U) == {str(k) for k in U_COUNTS}, f"{w}: U is not by the counts {list(U_COUNTS)}")
        for k, pair in U.items():
            _need(isinstance(pair, list) and len(pair) == 2 and all(_is_share(v) for v in pair)
                  and float(pair[1]) >= float(pair[0]), f"{w}: U at {k} is not [point, bound >= point] shares")
        cp = cl["caps_at_pin"]
        _keys(cp, ("count", "cap", "wall", "report_only", "why"), f"{w} caps_at_pin")
        _need(cp["count"] == U_PIN_COUNT, f"{w}: caps_at_pin is not at count {U_PIN_COUNT}")
        _need(_is_num(cp["cap"]) and _is_num(cp["wall"]) and isinstance(cp["report_only"], bool)
              and cp["why"] in (None, *CAPS_WHY), f"{w}: caps_at_pin is not (cap, wall, report_only, why)")
        mine = caps(*U[str(U_PIN_COUNT)], tk["dropped"])
        _need(mine.report_only == cp["report_only"] and mine.why == cp["why"]
              and abs(mine.cap - float(cp["cap"])) <= 1e-12 and abs(mine.wall - float(cp["wall"])) <= 1e-12,
              f"{w}: caps_at_pin is not the caps rule on its own U at count {U_PIN_COUNT}")
        for key in ("report_only", "ineligible"):
            _need(isinstance(cl[key], bool), f"{w}: {key} is not a boolean")
        _need(cl["report_only"] == cp["report_only"], f"{w}: report_only is not its caps at the pin's")
        _need(_is_str_or_none(cl["ineligible_why"]) and ((cl["ineligible_why"] is None) == (not cl["ineligible"])),
              f"{w}: ineligible_why is text exactly when ineligible")
        s1 = cl["stage1"]
        _keys(s1, ("refuted", "readable_members", "era_refutes"), f"{w} stage1")
        _need(isinstance(s1["refuted"], bool) and _is_int(s1["readable_members"]), f"{w}: stage1 is not (refuted, count)")
        er = s1["era_refutes"]
        _need(isinstance(er, Mapping) and set(er) == {"e0", "e1"} and all(v is None or isinstance(v, bool)
                                                                           for v in er.values()),
              f"{w}: stage1's era_refutes are not by era")
        own = cl["c_own_at_pin"]
        _need(isinstance(own, Mapping) and set(own) == set(FLOORS), f"{w}: c_own_at_pin is not by floor definition")
        for fd, row in own.items():
            _keys(row, PIN_FLOOR_KEYS, f"{w} c_own_at_pin {fd}")
            for key in ("N0", "N0R", "N1", "c_own", "k_used"):
                _need(row[key] is None or _is_k(row[key]), f"{w}: c_own_at_pin {fd} {key} is not a grid k or null")
            _need(_is_k(row["minimum"], top=K_MAX + 1), f"{w}: c_own_at_pin {fd} minimum is not a grid k")
            nulls = [row[n] for n in NULLS]
            _need(row["c_own"] == (None if any(v is None for v in nulls) else max(nulls)),
                  f"{w}: c_own_at_pin {fd} c_own is not the largest of its nulls")
            _need(row["k_used"] == k_used(rule["c_G_k"], rule["margin_k"], row["c_own"], row["minimum"]),
                  f"{w}: c_own_at_pin {fd} k_used is not the bar of its c_own and minimum")
        if own[rule["floor_def"]]["k_used"] is None:
            _need(cl["ineligible"], f"{w}: no bar at the pin but not ineligible")
        for u in cells:
            _need(units[u]["refuted"] == s1["refuted"] and units[u]["report_only"] == cl["report_only"]
                  and units[u]["ineligible"] == cl["ineligible"], f"{w}: unit {u}'s flags are not its cluster's")
        _need(isinstance(cl["seat_members"], list) and all(x in cl["members"] for x in cl["seat_members"]),
              f"{w}: seat members are not its members")
        ex = cl["expected"]
        _keys(ex, ("passes", "seats"), f"{w} expected")
        _need(_rising(ex["passes"], len(PLAN)) and _rising(ex["seats"], len(PLAN)),
              f"{w}: expected passes and seats are not {len(PLAN)} rising shares")
        bs = cl["beside"]
        _keys(bs, BESIDE_KEYS, f"{w} beside")
        _need(all(v is None or _is_share(v) for v in bs.values()), f"{w}: beside figures are not shares or null")
    _need(seen == set(units), "a unit is in no founding cluster")


def _check_matched(doc: Mapping[str, Any]) -> None:
    matched, units = doc["matched_floor"], doc["units"]
    _need(isinstance(matched, Mapping), "the receipt's matched floors are not an object")
    want = {str(m) for m in range(M_MIN, 61)}
    for grp, by_class in matched.items():
        _need(grp in BASE_GROUPS and isinstance(by_class, Mapping), f"matched floor {grp}: not a base group's")
        for cls, row in by_class.items():
            w = f"matched floor {grp}/{cls}"
            _keys(row, ("family", "sizes", *FLOORS), w)
            _need(isinstance(row["family"], str) and isinstance(row["sizes"], list)
                  and all(_is_int(s) for s in row["sizes"]), f"{w}: family and sizes")
            for fd in FLOORS:
                _need(isinstance(row[fd], Mapping) and set(row[fd]) == want
                      and all(_is_k(v, top=K_MAX + 1) for v in row[fd].values()), f"{w}: {fd} is not grid k by m 3..60")
    for cell, u in units.items():
        _need(isinstance((matched.get(u["group"]) or {}).get(u["class"]), Mapping),
              f"unit {cell}: no matched stand-in family's N1 floor for its group and class")


def _check_conformance(doc: Mapping[str, Any]) -> None:
    cf = doc["conformance"]
    _keys(cf, ("version", "tolerance", "vectors"), "the conformance block")
    _need(cf["version"] == CONFORMANCE, f"the conformance block is not {CONFORMANCE}")
    _need(_is_num(cf["tolerance"]) and float(cf["tolerance"]) == TOLERANCE, f"the conformance tolerance is not {TOLERANCE}")
    vec = cf["vectors"]
    _need(isinstance(vec, Mapping) and set(vec) == set(CV_IDS), "the conformance vectors are not CV1-CV12")
    for vid, v in vec.items():
        _keys(v, ("what", "calib", "p1_route", "inputs", "outputs"), f"vector {vid}")
        _need(isinstance(v["what"], str) and isinstance(v["calib"], str) and isinstance(v["p1_route"], str),
              f"vector {vid}: what, calib and p1_route are not text")
        _need(isinstance(v["inputs"], Mapping) and isinstance(v["outputs"], Mapping), f"vector {vid}: inputs, outputs")
        gen = v["inputs"].get("generator") if isinstance(v["inputs"], Mapping) else None
        if gen is not None:
            _need(all(k in v["inputs"] for k in ("generator", "id", "seed", "sha256")),
                  f"vector {vid}: its generated inputs name no (generator, id, seed, sha256)")
            _need(v["inputs"]["generator"] == "p1conform.inputs" and v["inputs"]["id"] == vid and _is_int(v["inputs"]["seed"]) and _is_hex(v["inputs"]["sha256"]),
                  f"vector {vid}: its generated inputs are not (id, seed, sha256)")


def _check_calibration(doc: Mapping[str, Any], *, test: bool = False) -> None:
    cal = doc["calibration"]
    _keys(cal, CALIBRATION_KEYS, "the calibration block")
    if test:                                              # a dry run's receipt (a test's own constants): UNPINNED
        _need(isinstance(cal["code_pin"], str) and _is_str_or_none(cal["code_pin_utc"]), "the calibration's code pin")
    else:
        _need(isinstance(cal["code_pin"], str) and cal["code_pin"].startswith("CODE PIN ")
              and isinstance(cal["code_pin_utc"], str), "the receipt's code is not at a CODE PIN")
        _need(cal["code_pin"] == CODE_PIN, f"the receipt's code pin is not {CODE_PIN}")
    _need(isinstance(cal["code_sha256"], Mapping) and all(isinstance(k, str) and _is_hex(v)
                                                          for k, v in cal["code_sha256"].items()),
          "the calibration's code shas are not 64-hex shas")
    if not test:
        # THE CODE AT ITS PIN (the conformance review's finding 6): every run file at its latest pin's sha
        wrong = sorted(name for name, sha in CODE_PIN_SHA256.items() if cal["code_sha256"].get(name) != sha)
        _need(not wrong, f"the receipt's calibration code is not {CODE_PIN}'s: {', '.join(wrong)}")
    _need(isinstance(cal["vendored"], Mapping) and set(cal["vendored"]) == set(CALIB_FILES)
          and all(_is_hex(v) for v in cal["vendored"].values()), "the receipt does not name every vendored file's sha")
    for key in ("pins_log_sha256", "deviations_log_sha256", "decision_sha256", "decision_in_sha256",
                "prep_manifest_sha256"):
        _need(_is_hex(cal[key]), f"the calibration's {key} is not a 64-hex sha")
    he = cal["house_export"]
    _keys(he, HOUSE_EXPORT_KEYS, "the House export block")
    _need(all(_is_hex(he[k]) for k in ("meta_sha256", "prices_sha256", "status_sha256")), "the House export's shas")
    _need(_is_int(he["units"]) and _is_int(he["saved"]) and isinstance(he["failed_twice"], list)
          and all(isinstance(x, str) for x in he["failed_twice"]), "the House export's counts")
    _need(isinstance(cal["python"], str) and isinstance(cal["numpy"], str), "the calibration's python and numpy")


def receipt_problem(doc: Any, *, expect_constants: Mapping[str, Any] | None = None) -> str | None:
    """The receipt's first defect against the contract (sections 2 and 3), in words; None when it is the contract's.
    `expect_constants`: a TEST's own constants (the dry run's B 40); default `CONSTANTS`."""
    try:
        _keys(doc, RECEIPT_KEYS, "the receipt")
        _need(doc["name"] == NAME, f"the receipt names {doc['name']!r}, not {NAME}")
        _need(doc["contract"] == CONTRACT, f"the receipt is not of the contract {CONTRACT}")
        _need(doc["prereg_sha256"] == PREREG_SHA256, "the receipt is not POOL1's under this pre-registration")
        _need(doc["status"] == "PINNED", "the calibration pinned no rule: nothing is pinned and nothing is judged")
        run = doc["run"]
        _keys(run, ("index", "second_run_amendment", "at"), "the run block")
        _need(run["index"] in (1, 2) and not isinstance(run["index"], bool), "the run index is not 1 or 2")
        _need(_is_str_or_none(run["second_run_amendment"]) and (run["index"] == 1 or bool(run["second_run_amendment"])),
              "a second run with no named amendment")
        _need(isinstance(run["at"], str), "the run's time is not text")
        _check_calibration(doc, test=expect_constants is not None)
        rule = doc["rule"]
        _keys(rule, ("name", "floor_def", "margin", "margin_k", "c_G", "c_G_k"), "the rule")
        _need(isinstance(rule["name"], str) and rule["floor_def"] in FLOORS, "the rule names no floor definition")
        _need(rule["margin_k"] in MARGINS_K and _is_int(rule["margin_k"]) and _is_num(rule["margin"])
              and abs(float(rule["margin"]) * 100 - rule["margin_k"]) <= 1e-9, "the rule's margin is not the menu's")
        _need(_is_int(rule["c_G_k"]) and C_G_K_RANGE[0] <= rule["c_G_k"] <= C_G_K_RANGE[1] and _is_num(rule["c_G"])
              and abs(float(rule["c_G"]) * 100 - rule["c_G_k"]) <= 1e-9, "the rule's c_G is off the grid or outside 1.40-2.50")
        _need(_same(doc["constants"], dict(CONSTANTS if expect_constants is None else expect_constants)),
              "the receipt's constants are not this code's")
        reg = doc["regimes"]
        _keys(reg, REGIME_AXES, "the regimes")
        for axis in REGIME_AXES:
            cut = reg[axis]
            _need(isinstance(cut, list) and len(cut) == 2 and all(_is_num(v) for v in cut) and float(cut[0]) <= float(cut[1]),
                  f"the receipt's {axis} cutpoints are not two ascending numbers")
        rho = doc["rho_assign"]
        _need(rho is None or (_is_num(rho) and -1.0 <= float(rho) <= 1.0), "the receipt's rho_assign is not a correlation")
        _need(isinstance(doc["clusters"], Mapping), "the receipt's clusters are not an object")
        _check_founders(doc)
        _check_units(doc)
        _check_clusters(doc)
        _check_matched(doc)
        mk = doc["market"]
        _need(isinstance(mk, Mapping) and set(mk) == {"e0", "e1"}, "the market block is not by era")
        for e, row in mk.items():
            _keys(row, ("first", "last", "sessions", "sha256"), f"the market's {e}")
            _need(isinstance(row["first"], str) and isinstance(row["last"], str) and _is_int(row["sessions"])
                  and _is_hex(row["sha256"]), f"the market's {e} is not (first, last, sessions, sha256)")
        _check_conformance(doc)
        _need(isinstance(doc["record"], Mapping), "the record block is not an object")
    except ReceiptRefused as exc:
        return str(exc)
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        return f"the receipt is not the contract's ({type(exc).__name__})"
    return None


def parse_receipt(doc: Mapping[str, Any], sha256: str, *, expect_constants: Mapping[str, Any] | None = None
                  ) -> tuple[Receipt | None, str | None]:
    """A receipt document checked whole against the contract (`receipt_problem`); (None, why) on its first defect."""
    problem = receipt_problem(doc, expect_constants=expect_constants)
    if problem is not None:
        return None, problem
    founders = {}
    for k, f in doc["founders"].items():
        founders[str(k)] = Founder(
            lineage=str(k), pid=int(f["pid"]), family=str(f["family"]), version=f["version"], lane=str(f["lane"]),
            ugroup=str(f["ugroup"]), first_day=str(f["first_day"]), cls=f["class"], infer_key_class=f["infer_key_class"],
            status=str(f["status"]), why=f["why"], merged_into=f["merged_into"], group=f["group"], cell=f["cell"],
            judged=bool(f["judged"]), cluster=f["cluster"], ticket=f["ticket"], fwd1_type=f["fwd1_type"],
            fwd1_case=f["fwd1_case"], fwd1_judged=f["fwd1_judged"], reached_sealed=bool(f["reached_sealed"]),
            seat_shape=bool(f["seat_shape"]), program_sha=f["program_sha"],
            train_sha256=None if f["train_sha256"] is None else dict(f["train_sha256"]))
    units = {str(c): UnitSpec(cell=str(c), cls=str(u["class"]), group=str(u["group"]), cluster=str(u["cluster"]),
                              members=tuple(str(x) for x in u["members"]), m=int(u["m"]), refuted=bool(u["refuted"]),
                              report_only=bool(u["report_only"]), ineligible=bool(u["ineligible"]))
             for c, u in doc["units"].items()}
    clusters = {}
    for cid, cl in doc["clusters"].items():
        clusters[str(cid)] = ClusterSpec(
            cid=str(cid), cells=tuple(str(c) for c in cl["cells"]), classes=tuple(str(c) for c in cl["classes"]),
            members=tuple(str(x) for x in cl["members"]), joins=tuple((str(a), str(b)) for a, b in cl["joins"]),
            boot_seed=int(cl["boot_seed"]), span=dict(cl["span"]), windows={k: int(v) for k, v in cl["windows"].items()},
            tickets=json.loads(json.dumps(cl["tickets"])),
            U={int(k): (float(v[0]), float(v[1])) for k, v in cl["U"].items()}, caps_at_pin=dict(cl["caps_at_pin"]),
            report_only=bool(cl["report_only"]), ineligible=bool(cl["ineligible"]), ineligible_why=cl["ineligible_why"],
            stage1=json.loads(json.dumps(cl["stage1"])),
            c_own_at_pin={fd: dict(row) for fd, row in cl["c_own_at_pin"].items()},
            seat_members=tuple(str(x) for x in cl["seat_members"]),
            expected={k: tuple(float(x) for x in v) for k, v in cl["expected"].items()},
            beside={k: (None if v is None else float(v)) for k, v in cl["beside"].items()})
    rule_ = doc["rule"]
    return Receipt(sha256=sha256, rule=Rule(name=str(rule_["name"]), floor_def=str(rule_["floor_def"]),
                                            margin_k=int(rule_["margin_k"]), c_G_k=int(rule_["c_G_k"])),
                   constants=json.loads(json.dumps(doc["constants"])),
                   regimes=tuple((float(doc["regimes"][a][0]), float(doc["regimes"][a][1])) for a in REGIME_AXES),
                   rho_assign=None if doc["rho_assign"] is None else float(doc["rho_assign"]),
                   founders=founders, units=units, clusters=clusters,
                   matched_floor=json.loads(json.dumps(doc["matched_floor"])), market=json.loads(json.dumps(doc["market"])),
                   conformance=doc["conformance"], calibration=json.loads(json.dumps(doc["calibration"])),
                   run=dict(doc["run"]), doc=doc), None


def read_receipt(raw: bytes, *, expect_constants: Mapping[str, Any] | None = None) -> tuple[Receipt | None, str | None]:
    """A receipt from its exact bytes (its sha is theirs): JSON with every NaN and Infinity token refused, then
    `parse_receipt`."""
    try:
        doc = json.loads(raw.decode("utf-8"), parse_constant=_no_constant)
    except ReceiptRefused as exc:
        return None, str(exc)
    except (UnicodeDecodeError, ValueError):
        return None, "the receipt is not JSON"
    return parse_receipt(doc, hashlib.sha256(raw).hexdigest(), expect_constants=expect_constants)


def load_receipt(path: str | Path, pin_: Pin, *, expect_constants: Mapping[str, Any] | None = None,
                 conformed: Callable[[Receipt, Calib], tuple[bool, str | None]] | bool = True,
                 calib_: tuple[Calib | None, str | None] | None = None) -> tuple[Receipt | None, str | None]:
    """THE RECEIPT the pin names (the contract's 6.3): read only when its sha256 is the pin's; parsed (`read_receipt`);
    its vendored code's shas checked against `CALIB_SHA256` and the vendored files (`calib`); then every conformance
    vector reproduced (`conformed`: True runs `conform`; a callable is the job's cache of it; False is a test's
    parse alone). (None, why) on any defect, mismatch or failed vector: nothing is judged."""
    try:
        raw = Path(path).read_bytes()
    except OSError:
        return None, f"no receipt at {RECEIPT_PATH}: nothing is judged"
    if hashlib.sha256(raw).hexdigest() != pin_.receipt_sha256:
        return None, "the receipt's sha256 is not the pin's: nothing is judged"
    rec, why = read_receipt(raw, expect_constants=expect_constants)
    if rec is None:
        return None, why
    named = rec.calibration["vendored"]
    for name in CALIB_FILES:
        if CALIB_SHA256.get(name) != named.get(name):
            return None, f"the receipt's vendored {name} is not this code's pinned file"
    if conformed is False:
        return rec, None
    cal, why = calib_ if calib_ is not None else calib()
    if cal is None:
        return None, why
    if any(cal.sha256.get(name) != named.get(name) for name in CALIB_FILES):
        return None, "the vendored calibration files are not the receipt's"
    ok, why = (conform(rec, cal) if conformed is True else conformed(rec, cal))[:2]
    if not ok:
        return None, f"the receipt's conformance vectors fail on this box: {why}"
    return rec, None


def rule(policy: Mapping[str, Any] | None = None, *, repo: str | Path | None = None,
         conformed: Callable[[Receipt, Calib], tuple[bool, str | None]] | bool = True) -> tuple[Receipt | None, str | None]:
    """`load(pin(policy))` and then `load_receipt` under the repository (`repo`; default this checkout: on the House
    /workspace/current)."""
    held, why = load(pin(policy))
    if held is None:
        return None, why
    base = Path(repo) if repo is not None else Path(__file__).resolve().parents[2]
    return load_receipt(base / RECEIPT_PATH, held, conformed=conformed)


# ----------------------------------------------------------------------------------------------------- the cell key
def cell_name(cls: str, group: str) -> str:
    return f"{cls}/{group}"


def cell_key(cell: str) -> tuple[str, str]:
    """A cell's (class, group) key, as the vendored code keys its cells."""
    cls, grp = str(cell).split("/")
    return cls, grp


def member_pid(rows: Sequence[Mapping[str, Any]]) -> int | None:
    """A lineage's MEMBER (section 1.3): its first passing version, the lowest pid whose reason is train_pass, seed or
    live, fixed by pid and never by outcome; None for a Train-fail-only lineage (not a member)."""
    pids = sorted(int(r["pid"]) for r in rows if str(r.get("reason")) in PASSING)
    return pids[0] if pids else None


def reads_events(code: Any) -> bool:
    """THE EVENT-CODE SCAN (section 1.2; the contract's 4.4): the UNION of the House job's word scan (`EVENT_WORD`,
    the word events or events_next anywhere: p1cluster.event_word's, CV11), a static scan naming the ctx fields as an
    attribute or a string constant, and text that is not text or does not parse (fail closed: out of cells). A
    tightening of either scan alone: it can only put more programs out."""
    if not isinstance(code, str):
        return True
    if EVENT_WORD.search(code):
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


def excluded(*, panel: bool, symbols: Sequence[str], card: Mapping[str, Any] | None, code: Any) -> str | None:
    """Why a LATER lineage is OUT of every cell at its first reading (section 1.2), None when it is not: a panel, a
    stocks symbol, the beta class equity_premium, no declared class, an event reader (its card's inputs or its frozen
    code: `reads_events`). Its Train exposure rules (under 1%, no base group above 2/3, a stock in its universe) are
    the vendored `member_from_runs`', read once its Train series is written."""
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
        return "an event reader (its frozen code names events or events_next): out until A25's calendar covers its windows"
    if not cls:
        return "no declared class (no birth card): out of cells"
    return None


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
    sum_s (ws_st - what_st)(R_st - mu_s) less the costs: a static tilt earns none. Held to p1stat.alpha_windows (CV1)."""
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
    weight is infinite); None with no founder (p1stat.sigma_tilde's; a test holds the two equal)."""
    vals = sorted(1.0 / max(float(s), SIGMA_FLOOR) for s in sigmas if s is not None and math.isfinite(float(s)))
    if not vals:
        return None
    n = len(vals)
    med = vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2.0
    return 1.0 / med


def sigma_used(sigma: float, tilde: float | None) -> float:
    """sigma_used = max(sigma, `SIGMA_FLOOR`, sigma_tilde / 3): no member's weight exceeds 3x the founders' median
    (p1stat.sigma_used's)."""
    out = max(float(sigma), SIGMA_FLOOR)
    if tilde is not None:
        out = max(out, float(tilde) / WEIGHT_CAP)
    return out


def train_sigma(eras: Sequence[tuple[Any, Any, Any, Any]], mu: Any, wbar: Any) -> float | None:
    """A CONTROL's sigma (section 2.1, the placebo leg's scale): the sd (ddof 1) of a over its Train replays, what
    restarted at each era start. `eras`: (rg, gap, ws, R) a pool. None with fewer than 2 days or a series that is not
    finite. (A member's sigma is the vendored `fit_constants`'.)"""
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
    """T: mean / sd (ddof 1) x sqrt(n), every sum by math.fsum (fwd1_rule's; held to p1stat.t_direct by CV2)."""
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


def look_t(D: Sequence[float], D15: Sequence[float], k: int) -> float | None:
    """A look's valid T (None where the sd is under 1e-12, T is not finite or fsum(D15_1..k) is not above 1e-12):
    p1stat.t_direct's per look (CV2)."""
    p = look(D, D15, k)
    return p["T"] if p["T"] is not None and float(p["S15"]) > ZERO else None


def series_sha(days: Sequence[str], D: Sequence[float], D15: Sequence[float]) -> str:
    """The sha256 of a cell's D_1..k (the checkpoint of record of a non-final look: the word and this sha only): the
    canonical JSON of {"days", "D", "D15"}, floats in repr."""
    doc = {"days": [str(d) for d in days], "D": [repr(float(x)) for x in D], "D15": [repr(float(x)) for x in D15]}
    return hashlib.sha256(json.dumps(doc, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


# ----------------------------------------------------------------------------------------------- the bar and the caps
def k_used(c_G_k: int, margin_k: int, c_own_k: int | None, minimum_k: int | None) -> int | None:
    """THE BAR on the grid (section 3.3; the contract's 3.2; p1cluster.k_used_for's, held to it by CV12): k_own =
    max(c_own, minimum) (a minimum of None leaves c_own), c_used = max(c_G, k_own + margin); None (INELIGIBLE, stated)
    without c_own or when k_own + margin is above 500 (an ineligible matched floor is 501)."""
    if c_own_k is None:
        return None
    k_own = int(c_own_k) if minimum_k is None else max(int(c_own_k), int(minimum_k))
    if k_own + int(margin_k) > K_MAX:
        return None
    return max(int(c_G_k), k_own + int(margin_k))


@dataclass(frozen=True)
class Caps:
    cap: float
    wall: float
    report_only: bool
    u_point: float
    u_bound: float
    why: str | None = None
    u_worst: float = 0.0


def caps(u_point: float | None, u_bound: float | None, dropped: Sequence[Any] = ()) -> Caps:
    """THE CAPS (section 7.2; the contract's 3.8 rule; p1cluster.caps_rule's, held to it by CV10): REPORT-ONLY, judged
    at CAP 0.12 and WALL 0.15 for the operator's report alone and seating nothing, when U_u's point is 0.12 or more
    (CAP_u <= 0, "u_point"), when its bound is 0.15 or more (WALL_u <= 0, "u_bound"), when any ticket could not be
    computed ("tickets_dropped"), or when either figure is not finite; otherwise CAP_u = 0.12 - point and WALL_u =
    0.15 - max(bound, point)."""
    up = float("nan") if u_point is None else float(u_point)
    ub = float("nan") if u_bound is None else float(u_bound)
    why = None
    if not math.isfinite(up) or up >= CAP:
        why = "u_point"
    elif not math.isfinite(ub) or max(ub, up) >= WALL:
        why = "u_bound"
    elif dropped:
        why = "tickets_dropped"
    if why is not None:
        return Caps(cap=CAP, wall=WALL, report_only=True, u_point=up, u_bound=ub, why=why, u_worst=0.0)
    return Caps(cap=CAP - up, wall=WALL - max(ub, up), report_only=False, u_point=up, u_bound=ub, why=None, u_worst=up)


def joined_u(parts: Sequence[tuple[float, float]]) -> tuple[float, float]:
    """U_u of clusters joined at a look (section 1.4: "their joint floor and U_u are recomputed"; P1 D5): the union
    bound of their parts (the sum, at most 1), an upper bound of the union's rate, so a cap only falls."""
    return min(1.0, math.fsum(p for p, _ in parts)), min(1.0, math.fsum(b for _, b in parts))


def u_count(rows: Iterable[Mapping[str, Any] | None]) -> int:
    """THE CHECKPOINT COUNT U_u is read at (P1 D7, the contract's 3.8): the largest FWD1 checkpoint count read before
    the clock among the cluster's members FWD1 judges as case N or that hold an FWD1-R pass (their `fwd1_facts` rows),
    0 for none."""
    count = 0
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        if (str(row.get("type")) == "ETF" and str(row.get("case_")) == "N" and int(row.get("judged") or 0) == 1) \
                or str(row.get("status")) == "pass":
            count = max(count, int(row.get("k_read") or 0))
    return count


def joined_seed(cid: str, look_key: str) -> int:
    """The boot seed of a cluster first made by a join at a look (the contract's 4.1): int(sha256("<cid>|<look>")[:8],
    16)."""
    return int(hashlib.sha256(f"{cid}|{look_key}".encode()).hexdigest()[:8], 16)


# ------------------------------------------------------------------------------ the calibration's functions, adapted
class _Quiet:
    """numpy's "Mean of empty slice" and division warnings of the vendored code (an all-NaN session of a nanmean is
    NaN by design there), kept out of the job's log."""

    def __enter__(self) -> None:
        import numpy as np

        self._w = warnings.catch_warnings()
        self._w.__enter__()
        warnings.simplefilter("ignore", RuntimeWarning)
        self._e = np.errstate(all="ignore")
        self._e.__enter__()

    def __exit__(self, *exc: Any) -> None:
        self._e.__exit__(*exc)
        self._w.__exit__(*exc)


def quiet() -> _Quiet:
    return _Quiet()


def group_of_symbol(symbols: Sequence[str]) -> str:
    """The House's group of a symbol list (league/swarm/elane_train.py `symbols_group`): the argument the vendored
    `member_from_runs` takes."""
    from ..swarm import elane_train

    return elane_train.symbols_group(list(symbols))


def house_context(cal: Calib, prices: Mapping[str, Any], receipt: Receipt) -> dict[str, Any]:
    """The House's Train calendar and regime cells at the receipt's IN cutpoints (vendored `house_context`). `prices`:
    {"e0": the House job's prices()["e0"] record, "e1": ...} (`pool_market`)."""
    return cal.cluster.house_context({"e0": prices["e0"], "e1": prices["e1"]}, receipt.cuts())


def member_meta(*, lineage: str, pid: int, family: str, version: Any, lane: str, ugroup: str, first_day: str,
                declared_class: str | None, program_sha: str | None, panel: bool = False, inputs: Sequence[str] = (),
                event_word: bool = False, infer_key_class: str | None = None, seat_shape: bool = False,
                reached_sealed: bool = False, fwd1_type: str | None = None, fwd1_case: str | None = None
                ) -> dict[str, Any]:
    """One lineage's House meta row, the shape the vendored `member_from_runs` reads (the House job's `meta`)."""
    return {"lineage": lineage, "pid": int(pid), "family": family, "version": version, "lane": lane, "ugroup": ugroup,
            "first_day": first_day, "declared_class": declared_class, "infer_key_class": infer_key_class,
            "program_sha": program_sha, "panel": bool(panel), "inputs": list(inputs), "event_word": bool(event_word),
            "seat_shape": bool(seat_shape), "reached_sealed": bool(reached_sealed), "fwd1_type": fwd1_type,
            "fwd1_case": fwd1_case, "seen_spans": [], "hidden": False}


def founder_meta(f: Founder) -> dict[str, Any]:
    """A founder's House meta row from the receipt (its class, ids and ticket inputs are the receipt's)."""
    return member_meta(lineage=f.lineage, pid=f.pid, family=f.family, version=f.version, lane=f.lane, ugroup=f.ugroup,
                       first_day=f.first_day, declared_class=f.cls, program_sha=f.program_sha,
                       infer_key_class=f.infer_key_class, seat_shape=f.seat_shape, reached_sealed=f.reached_sealed,
                       fwd1_type=f.fwd1_type, fwd1_case=f.fwd1_case)


def runs_of(pid: int, records: Mapping[str, Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    """{"<pid>_<part>": record}: a member's Train parts as the vendored code keys the House export."""
    return {f"{int(pid)}_{part}": rec for part, rec in records.items()}


def house_member(cal: Calib, meta: Mapping[str, Any], records: Mapping[str, Mapping[str, Any]], hc: Mapping[str, Any]
                 ) -> tuple[dict[str, Any], Any]:
    """(the lineage's record of ids and words, its Member on the House eras or None: out) by the vendored
    `member_from_runs` on its `pool_train` records ({part: the House job's one_run record})."""
    with quiet():
        return cal.cluster.member_from_runs(dict(meta), runs_of(int(meta["pid"]), records), hc, group_of_symbol)


def train_z(cal: Calib, mm: Any, hc: Mapping[str, Any]) -> Any:
    """A member's raw Train z on the two eras' concatenated House calendar (vendored `z_on_calendar`)."""
    return cal.cluster.z_on_calendar(mm, hc)


def assign(cal: Calib, z: Any, cells: Mapping[str, Sequence[Any]], rho_assign: float | None
           ) -> tuple[str | None, dict[str, float]]:
    """THE ASSIGNMENT (section 1.1; the contract's 3.5): the vendored `assign_cell`: (the cell of its group whose
    founders' Train D (the nanmean of their z) its Train z correlates with most (30 common finite sessions at least),
    when that is >= rho_assign; else None: it counts toward a new cell), with every cell's correlation. `cells`: {cell:
    [its founders' Train z]}, its own group's cells only. A null rho_assign assigns nothing."""
    import numpy as np

    with quiet():
        cell, corr = cal.cluster.assign_cell(z, {c: np.array([np.asarray(v, dtype=np.float64) for v in zs])
                                                 for c, zs in cells.items()}, rho_assign)
    return cell, {str(c): float(v) for c, v in corr.items()}


def merge_copy(cal: Calib, new: Any, earlier: Sequence[Any], hc: Mapping[str, Any]) -> str | None:
    """THE HOUSE'S COPY MERGE (section 1.3; the contract's 4.5): the vendored `merge_copies` on every earlier member by
    pid and this one: the name ("P<pid>") of the earliest member it merges into (the same program sha, or Train z
    correlation >= 0.7 on 30 common finite sessions at least), or None."""
    pid = int(new.meta.get("pid") or str(new.name)[1:])
    ahead = sorted((m for m in earlier if int(m.meta.get("pid") or str(m.name)[1:]) < pid),
                   key=lambda m: int(m.meta.get("pid") or str(m.name)[1:]))
    with quiet():
        _, merged = cal.cluster.merge_copies([*ahead, new], hc)
    return merged.get(new.name)


def cell_within(cal: Calib, ms: Sequence[Any], Z: Mapping[str, Any]) -> float:
    """A cell's mean within-cell member-pair correlation of Train z (cells_and_clusters' own `within`): the member
    rule's within figure."""
    import numpy as np

    names = [x.name for x in ms]
    cs = [float(cal.cluster.corr_common(Z[a], Z[b])) for i, a in enumerate(names) for b in names[i + 1:]]
    cs = [c for c in cs if math.isfinite(c)]
    return float(np.mean(cs)) if cs else float("nan")


def cluster(cal: Calib, clusters: Mapping[str, Sequence[tuple[str, str]]], judged: Mapping[tuple[str, str], Sequence[Any]],
            hc: Mapping[str, Any]) -> tuple[dict[str, list[tuple[str, str]]], list[dict[str, Any]]]:
    """THE CLUSTERS RE-TESTED (section 1.4) by the vendored member rule (`join_clusters`: average linkage, the strongest
    join first) on the members as they stand: (clusters {id: [cell key]}, joins). `clusters`: {id: [cell key]};
    `judged`: {cell key: [Member]}."""
    with quiet():
        Z = {mm.name: train_z(cal, mm, hc) for ms in judged.values() for mm in ms}
        within = {k: cell_within(cal, ms, Z) for k, ms in judged.items()}
        out, joins = cal.cluster.join_clusters({cid: list(keys) for cid, keys in clusters.items()},
                                               {k: list(v) for k, v in judged.items()}, Z, within)
    return {cid: list(keys) for cid, keys in out.items()}, list(joins)


#: `house_floor`'s boot hook: (null, era, variant key, compute) -> the (B, nJ) resamples (the job's store of them).
BootHook = Callable[[str, int, str, Callable[[], Any]], Any]


def house_floor(cal: Calib, *, cid: str, keys: Sequence[tuple[str, str]], judged: Mapping[tuple[str, str], Sequence[Any]],
                hc: Mapping[str, Any], B: int, boot_seed: int, caps_: Caps, joins: Mapping[str, int] | None = None,
                founders_sigma: Mapping[tuple[str, str], Sequence[float]] | None = None, boot: BootHook | None = None
                ) -> dict[str, Any] | None:
    """THE FLOOR PIPELINE (the contract's 4.1): the vendored `cluster_floor`'s steps, in its order and with its calls
    (`cluster_cells`, EraBoot [SEED_ROOT, 902, boot_seed, e], `cluster_point`, per null `cluster_boot_one` for every era
    and variant, `shares_from`, `fit_floors` at the caps), each variant's resamples through `boot` (the job keeps them
    across nights; a test holds this equal to `cluster_floor`). None when no era has a common span (ineligible).
    -> {"floor": fit_floors' {"floor", "c_own"}, "point", "shares", "weights", "span", "cols", "windows"}."""
    with quiet():
        return _house_floor(cal, cid=cid, keys=keys, judged=judged, hc=hc, B=B, boot_seed=boot_seed, caps_=caps_,
                            joins=joins, founders_sigma=founders_sigma, boot=boot)


def _house_floor(cal: Calib, *, cid: str, keys: Sequence[tuple[str, str]],
                 judged: Mapping[tuple[str, str], Sequence[Any]], hc: Mapping[str, Any], B: int, boot_seed: int,
                 caps_: Caps, joins: Mapping[str, int] | None, founders_sigma: Mapping[tuple[str, str], Sequence[float]] | None,
                 boot: BootHook | None) -> dict[str, Any] | None:
    import numpy as np

    C = cal.cluster
    keys = [tuple(k) for k in keys]
    cbe = C.cluster_cells(cid, keys, judged, hc, joins=None if joins is None else dict(joins),
                          founders_sigma=None if founders_sigma is None else dict(founders_sigma))
    if not cbe:
        return None
    span = {e: units[0].span[e] for e, units in cbe.items()}
    cols = C.cluster_cols(keys)
    proxy = C.Proxy(span, np.array(cols), f"H:{cid}")
    shares: dict[str, Any] = {}
    boots: dict[str, dict[tuple[int, str], Any]] = {}
    weights: dict[str, dict[tuple[int, str], float]] = {}
    ebs: dict[int, Any] = {}

    def eb(e: int) -> Any:
        if e not in ebs:
            P0, P1 = span[e]
            ebs[e] = cal.units.EraBoot(hc["bases"][e], P0, P1, hc["cuts"], int(B), [cal.K.SEED_ROOT, 902, int(boot_seed), e])
        return ebs[e]

    for null in cal.K.NULLS:
        boots[null] = {}
        for e, units in cbe.items():
            for key, n, o, _w in cal.engine.variants(units[0], e, null):
                compute = (lambda e=e, key=key, n=n, o=o: C.cluster_boot_one(cbe, {e: eb(e)}, e, key, n, o))
                boots[null][(e, key)] = compute() if boot is None else boot(null, e, key, compute)
        weights[null] = {(e, kk): w for e in span for kk, n, o, w in cal.engine.variants(proxy, e, null)}
    point = C.cluster_point(cbe, hc)
    for null in cal.K.NULLS:
        shares[null] = C.shares_from(boots[null], proxy, null)
    fl = cal.engine.fit_floors(proxy, point, hc["cells"], shares, cap=float(caps_.cap), wall=float(caps_.wall))
    windows = {f"e{e}": int(sum(len(point[(e, k)][0]) for k, n, o, w in cal.engine.variants(proxy, e, "N0"))) for e in span}
    return {"floor": fl, "point": point, "shares": shares, "weights": weights, "span": span, "cols": cols,
            "proxy": proxy, "windows": windows}


def pin_floors(fl: Mapping[str, Any] | None, receipt: Receipt, minimum: Mapping[str, int | None]
               ) -> dict[str, dict[str, int | None]]:
    """A cluster's IN-fitted floors in the receipt's `c_own_at_pin` shape (the contract's 3.8), from `house_floor`'s
    result: each null's floor, c_own, the minimum and the bar at the rule's c_G and margin, per floor definition."""
    out: dict[str, dict[str, int | None]] = {}
    for fd in FLOORS:
        if fl is None:
            row: dict[str, int | None] = {n: None for n in NULLS}
            row["c_own"] = None
        else:
            row = {n: fl["floor"]["floor"][n][fd].get("IN") for n in NULLS}
            row["c_own"] = fl["floor"]["c_own"][fd].get("IN")
        row["minimum"] = minimum.get(fd)
        row["k_used"] = k_used(receipt.rule.c_G_k, receipt.rule.margin_k, row["c_own"], row["minimum"])
        out[fd] = {k: (None if v is None else int(v)) for k, v in row.items()}
    return out


def minimum_of(receipt: Receipt, m_by_cell: Mapping[str, int]) -> dict[str, int | None]:
    """A cluster's matched-family minimum by floor definition (the contract's 3.9): the largest over its cells of the
    table's row at each cell's m; None for a definition when a cell has no row (m above 60: no bar, the look waits)."""
    out: dict[str, int | None] = {}
    for fd in FLOORS:
        vals = []
        for cell, m in m_by_cell.items():
            cls, grp = cell_key(cell)
            vals.append(receipt.matched(grp, cls, int(m), fd))
        out[fd] = None if not vals or any(v is None for v in vals) else max(vals)       # type: ignore[type-var]
    return out


# ------------------------------------------------------------------------------------------- the conformance vectors
def canonical(obj: Any) -> str:
    """Canonical JSON (sorted keys, no spaces, ASCII, no NaN): the text a `pool_market` record is kept as, and what a
    generated vector's inputs' sha256 is over (p1conform.canonical's)."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def _f(v: Any) -> Any:
    """A vector's value with "inf", "-inf" and "nan" read back as floats (the contract's 6.1)."""
    if isinstance(v, str) and v in ("inf", "-inf", "nan"):
        return float(v)
    if isinstance(v, list):
        return [_f(x) for x in v]
    return v


def _arr(v: Any, dtype: Any = None) -> Any:
    import numpy as np

    return np.asarray(_f(v), dtype=np.float64 if dtype is None else dtype)


def vector_inputs(cal: Calib, vid: str, inputs: Mapping[str, Any]) -> dict[str, Any]:
    """A vector's inputs: inline, or the vendored `p1conform.inputs(id, seed)` (merged with the inline keys beside
    them), first checked against the sha256 the receipt names."""
    if inputs.get("generator") is None:
        return dict(inputs)
    made = cal.conform.inputs(vid, int(inputs["seed"]))
    if cal.conform.sha256_of(made) != inputs["sha256"]:
        raise ReceiptRefused(f"{vid}'s generated inputs on this box are not the receipt's (sha256 differs)")
    return {**{k: v for k, v in inputs.items() if k not in ("generator", "id", "seed", "sha256")}, **made}


def conform(receipt: Receipt, cal: Calib) -> tuple[bool, str | None, dict[str, str | None]]:
    """EVERY CONFORMANCE VECTOR (the contract's 6.2 and 6.3) reproduced on this box through P1's own route (its forward
    statistic, its caps, bar and event scan, its market path and its floor adapter, each held to the vendored function
    where both exist) and compared with the receipt's outputs by the vendored `p1conform.match` (6.1's rule): (all held,
    the first failure in words, {vector: its first mismatch or None})."""
    import numpy as np

    results: dict[str, str | None] = {}
    for vid in CV_IDS:
        v = receipt.conformance["vectors"][vid]
        try:
            with warnings.catch_warnings(), np.errstate(all="ignore"):
                warnings.simplefilter("ignore", RuntimeWarning)
                got = CV_ROUTES[vid](cal, vector_inputs(cal, vid, v["inputs"]))
            bad = cal.conform.match(got, v["outputs"], vid)
            results[vid] = None if not bad else str(bad[0])[:240]
        except Exception as exc:  # noqa: BLE001 - a vector that cannot be computed fails
            results[vid] = f"{vid}: it raised {type(exc).__name__}: {str(exc)[:160]}"
    bad_ids = [vid for vid in CV_IDS if results[vid] is not None]
    if bad_ids:
        return False, results[bad_ids[0]], results
    return True, None, results


def _held(cal: Calib, mine: Any, theirs: Any, what: str) -> None:
    """P1's own route and the vendored function must agree (6.1's rule) before the receipt's outputs are compared."""
    bad = cal.conform.match(mine, theirs, what)
    if bad:
        raise ReceiptRefused(f"P1's {what} is not the calibration's: {str(bad[0])[:160]}")


def _cv_alpha(cal: Calib, x: Mapping[str, Any]) -> dict[str, Any]:
    """CV1: the legs (vendored `legs_close`), the base, and the per-symbol alpha with what restarted at each start J by
    P1's forward `alpha` on days J.. (rg = r less the haircut's sides), held to the vendored `alpha_windows`."""
    import numpy as np

    W, R, mu, wbar, hs = _arr(x["W"]), _arr(x["R"]), _arr(x["mu"]), _arr(x["wbar"]), _arr(x["hs"])
    g, starts, nlag, prior = float(x["haircut"]), [int(j) for j in x["starts"]], int(x["nlag"]), int(x["prior"])
    r, r15, sides, gross = cal.stat.legs_close(W, R, hs, k15=float(x["k15"]))
    base = r - g * sides - (W * mu[:, None]).sum(0)
    T = W.shape[1]
    mine = np.full((len(starts), nlag), np.nan)
    for i, J in enumerate(starts):
        a, _ = alpha(r[J:] - g * sides[J:], np.zeros(T - J), W[:, J:], R[:, J:], mu, wbar, prior=prior)
        n = min(nlag, T - J)
        mine[i, :n] = a[:n]
    _held(cal, mine, cal.stat.alpha_windows(base, W, R - mu[:, None], wbar, np.array(starts), nlag, prior),
          "forward alpha (CV1)")
    return {"r": r, "r15": r15, "sides": sides, "gross": gross, "base": base, "a": mine}


def _cv_t(cal: Calib, x: Mapping[str, Any]) -> dict[str, Any]:
    """CV2: each look's T by P1's fsum `t_stat` with the stress leg (`look_t`), held to the vendored `t_direct`; the
    vendored `tby`."""
    D = _arr(x["D"])
    D15 = D if x.get("D15") == "D" else _arr(x["D15"])
    plan = tuple(int(k) for k in x.get("plan", PLAN))
    mine = [[look_t(list(D[i]), list(D15[i]), k) for k in plan] for i in range(D.shape[0])]
    _held(cal, mine, [cal.stat.t_direct(D[i], D15[i], plan) for i in range(D.shape[0])], "look T (CV2)")
    return {"t_direct": mine, "tby": cal.stat.tby(D, D15, plan)}


def _cv_grid(cal: Calib, x: Mapping[str, Any]) -> dict[str, Any]:
    return {"k": cal.stat.grid_index(_arr(x["T"]))}


def _cv_floors(cal: Calib, x: Mapping[str, Any]) -> dict[str, Any]:
    import numpy as np

    g, w, cells = _arr(x["g"], np.int64), _arr(x["w"]), np.asarray(x["cells"], dtype=bool)
    out = {}
    for cap in x["caps"]:
        tot = float(w.sum())
        out[str(float(cap))] = {"floor_k": cal.stat.floor_k(g, w, float(cap)),
                                "rreg_floor": cal.stat.rreg_floor(g, w, cells, float(cap)),
                                "smallest_k": cal.stat.smallest_k(cal.stat.curve(g, w) / tot, float(cap))}
    return {"by_cap": out, "curve": cal.stat.curve(g, w)}


def _cv_bound(cal: Calib, x: Mapping[str, Any]) -> dict[str, Any]:
    import numpy as np

    gb, gp, w = _arr(x["g_b"], np.int64), _arr(x["g"], np.int64), float(x["w"])
    counts = cal.units.share_curves(gb, w)
    ps = cal.engine.point_share(gp, np.full(len(gp), w))
    bd = cal.units.bound_curve(counts / (w * gb.shape[1]), ps)
    return {"share_curves": counts, "point_share": ps, "bound_curve": bd,
            "raise_to_wall": cal.engine.raise_to_wall(int(x["k0"]), bd, float(x["wall"]))}


def _cv_idx(cal: Calib, x: Mapping[str, Any]) -> dict[str, Any]:
    return {"idx": cal.units.stationary_idx(int(x["n"]), int(x["B"]), [int(s) for s in x["seed"]],
                                            int(x.get("mean_block", BOOT_BLOCK)))}


def market_record(prices: Mapping[str, Any]) -> dict[str, Any]:
    """P1'S MARKET PATH: the House job's prices() records as the job keeps them (`pool_market`: each era's record as
    canonical JSON, read back) into the shape the vendored `house_context` reads."""
    return {f"e{e}": json.loads(canonical(prices[f"e{e}"])) for e in (0, 1)}


def _cv_market(cal: Calib, x: Mapping[str, Any]) -> dict[str, Any]:
    """CV7: the regime cells through P1's market path (`market_record`) into the vendored `house_context`."""
    import numpy as np

    M, K = cal.members, cal.K
    prices = market_record(x)
    hc0 = cal.cluster.house_context(prices, np.zeros((4, 2)))
    stats = {e: M.window_stats(hc0["bases"][e], None, np.arange(0, hc0["eras"][e].T - K.L + 1)) for e in (0, 1)}
    cuts = M.cutpoints(np.concatenate([stats[0], stats[1]]))
    hc = cal.cluster.house_context(prices, cuts)
    return {"stats": {f"e{e}": stats[e] for e in (0, 1)}, "cuts": cuts,
            "cells": {f"e{e}": hc["cells"][e] for e in (0, 1)},
            "cells_direct": {f"e{e}": M.cells_of(stats[e], cuts) for e in (0, 1)},
            "vt": {f"e{e}": hc["vt"][e] for e in (0, 1)}}


def _cv_path(cal: Calib, x: Mapping[str, Any]) -> dict[str, Any]:
    M = cal.members
    p0, p1, off = int(x["p0"]), int(x["p1"]), int(x["offset"])
    part = M.EraPart(p0=p0, p1=p1, W=_arr(x["W"]), r=_arr(x["r"]), r15=_arr(x["r15"]), sides=_arr(x["sides"]),
                     R=_arr(x["R"]), lots=True)
    mm = M.Member(name="CV8", family="cv8", group="index", cls="trend_momentum", syms=tuple(x["syms"]), parts=[part],
                  mu=_arr(x["mu"]), wbar=_arr(x["wbar"]), sigma=0.01)
    span = (p0, p1)
    Wr, base, c15, dS = mm.path(0, off, span)
    a_first, A = mm.A(0, off, span)
    _W0, base0, c150, _ = mm.path(0)
    return {"hs": mm.hs, "rolled": {"W": Wr, "base": base, "c15": c15, "dS": dS}, "A_first": a_first,
            "A_rows": A[:3, :p1 - p0], "a_era": mm.a_era(0, off, span),
            "unrolled": {"base": base0, "c15": c150, "a_era": mm.a_era(0)}}


def _cv_house(cal: Calib, x: Mapping[str, Any]) -> dict[str, Any]:
    """CV9: THE HOUSE PIPELINE end to end through P1's adapter (a look's code path): the records as `pool_train` rows
    (a member's four Train parts) into `house_member` (the vendored `member_from_runs`, the House's group of a symbol),
    the copy merge member by member (`merge_copy`), the cells and clusters (vendored), stage 1 (vendored, beside), the
    floor adapter (`house_floor`) with joins 0 and with one sector member joining at lag 25, the bar (`k_used`) for the
    6 rules, and a later lineage's assignment (`assign`)."""
    import numpy as np

    C, K = cal.cluster, cal.K
    prices = market_record(x["prices"])
    cuts = _arr(x["cuts"])
    hc = C.house_context(prices, cuts)
    runs = x["runs"]
    B, cap, wall, cg, mk = int(x["B"]), float(x["cap"]), float(x["wall"]), int(x["c_G_k"]), int(x["minimum_k"])
    capsv = Caps(cap=cap, wall=wall, report_only=False, u_point=CAP - cap, u_bound=WALL - wall)
    records, members = [], []
    for m in sorted(x["meta"]["members"], key=lambda r: r["pid"]):
        recs = {part: runs[f"{m['pid']}_{part}"] for part in PARTS if f"{m['pid']}_{part}" in runs}
        rec, mm = house_member(cal, m, recs, hc)
        records.append(rec)
        if mm is not None:
            members.append(mm)
    kept, merged = [], {}
    for mm in members:
        into = merge_copy(cal, mm, kept, hc)
        if into is None:
            kept.append(mm)
        else:
            merged[mm.name] = into
    cc = C.cells_and_clusters(kept, hc)
    lin = {mm.name: mm.family for mm in members}
    cell_id = {k: f"{k[0]}/{k[1]}" for k in cc["cells"]}
    out: dict[str, Any] = {
        "records": [{"lineage": r["lineage"], "status": r["status"], "group": r.get("group")} for r in records],
        "merged": {lin[a]: lin[b] for a, b in merged.items()},
        "constants": {mm.family: {"mu": mm.mu, "wbar": mm.wbar, "sigma": mm.sigma, "abar": mm.abar,
                                  "abar_v": mm.abar_v, "kind": mm.meta["kind"], "group": mm.group} for mm in kept},
        "cells": {cell_id[k]: [lin[m.name] for m in v] for k, v in cc["cells"].items()},
        "below": cc["below"], "cell_within": {cell_id[k]: v for k, v in cc["cell_within"].items()},
        "clusters": {cid: [cell_id[k] for k in keys] for cid, keys in cc["clusters"].items()},
        "joins": [j["joined"] for j in cc["joins"]], "rho_assign": cc["rho_assign"], "loo": cc["loo"]}
    floors = {}
    for ci, (cname, keys) in enumerate(sorted(cc["clusters"].items())):
        ms = [mm for k in keys for mm in cc["cells"][k]]
        sig_u = {}
        for k in keys:
            st = cal.stat.sigma_tilde([m.sigma for m in cc["cells"][k]])
            for m in cc["cells"][k]:
                sig_u[m.name] = float(cal.stat.sigma_used(np.array([m.sigma]), st)[0])
        res: dict[str, Any] = {"stage1": C.stage1(ms, sig_u, runs, hc), "boot_seed": ci}
        sector = [m for k in keys if k[1] == "sectors" for m in cc["cells"][k]]
        plans: dict[str, Any] = {"joins_0": None}
        if sector:
            plans["join_25"] = {sector[0].name: 25}
        for label, joins in plans.items():
            fl = house_floor(cal, cid=cname, keys=keys, judged=cc["cells"], hc=hc, B=B, boot_seed=ci, caps_=capsv,
                             joins=joins)
            if fl is None:
                res[label] = None
                continue
            near: dict[str, Any] = {}
            for null in K.NULLS:
                g, w, _ = cal.engine.worlds(fl["proxy"], fl["point"], "IN", null, hc["cells"])
                ps = cal.engine.point_share(g, w)
                bd = cal.units.bound_curve(fl["shares"][null]["IN"], ps)
                for fd in K.FLOOR_DEFS:
                    f = fl["floor"]["floor"][null][fd]["IN"]
                    near[f"{null}|{fd}"] = None if f is None else {str(k): [ps[k], bd[k]] for k in (f - 1, f, f + 1)
                                                                  if 0 <= k <= K.K_MAX}
            res[label] = {"joins": {lin[n]: v for n, v in (joins or {}).items()},
                          "span": {f"e{e}": list(v) for e, v in fl["span"].items()},
                          "floor": fl["floor"]["floor"], "c_own": fl["floor"]["c_own"], "near_floor_IN": near,
                          "windows": {f"e{e}|{key}": int(len(J)) for (e, key), (J, _) in sorted(fl["point"].items())},
                          "k_used": {f"{fd}+{mg}": k_used(cg, mg, fl["floor"]["c_own"][fd]["IN"], mk)
                                     for fd, mg in K.RULES}}
        floors[cname] = res
    out["floors"] = floors
    later = x["later"]
    rec, mm = house_member(cal, later, {part: runs[f"{later['pid']}_{part}"] for part in PARTS
                                        if f"{later['pid']}_{part}" in runs}, hc)
    assignment = None
    if mm is not None:
        Z = {m.name: train_z(cal, m, hc) for m in kept}
        cand = {cell_id[k]: [Z[m.name] for m in v] for k, v in cc["cells"].items() if k[1] == mm.group}
        cell, corr = assign(cal, train_z(cal, mm, hc), cand, cc["rho_assign"])
        assignment = {"group": mm.group, "kind": mm.meta["kind"], "corr": corr, "cell": cell}
    out["later"] = {"lineage": later["lineage"], "status": rec["status"], "assignment": assignment}
    return out


def _cv_caps(cal: Calib, x: Mapping[str, Any]) -> dict[str, Any]:
    """CV10: P1's `caps` on each case."""
    out = []
    for case in x["cases"]:
        c = caps(case["u_point"], case["u_bound"], case.get("dropped") or ())
        out.append({"cap": c.cap, "wall": c.wall, "u_worst": c.u_worst, "report_only": c.report_only, "why": c.why})
    return {"caps": out}


def _cv_events(cal: Calib, x: Mapping[str, Any]) -> dict[str, Any]:
    """CV11: the House job's word scan (vendored `event_word`); P1's `reads_events` (the union) is True wherever it
    is."""
    theirs = [bool(cal.cluster.event_word(t)) for t in x["texts"]]
    if any(w and not reads_events(t) for w, t in zip(theirs, x["texts"])):
        raise ReceiptRefused("pool_rule.reads_events misses an event reader the House job's scan finds")
    return {"event_word": theirs}


def _cv_bar(cal: Calib, x: Mapping[str, Any]) -> dict[str, Any]:
    """CV12: P1's `k_used` on each case."""
    return {"k_used": [k_used(int(c["c_G"]), int(c["margin"]), c["c_own"], c["minimum"]) for c in x["cases"]]}


CV_ROUTES: dict[str, Callable[[Calib, Mapping[str, Any]], dict[str, Any]]] = {
    "CV1": _cv_alpha, "CV2": _cv_t, "CV3": _cv_grid, "CV4": _cv_floors, "CV5": _cv_bound, "CV6": _cv_idx,
    "CV7": _cv_market, "CV8": _cv_path, "CV9": _cv_house, "CV10": _cv_caps, "CV11": _cv_events, "CV12": _cv_bar,
}


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
    """THE FLOOR-WIDE EXPECTED ZERO-EDGE PASSES (section 4.5): for each founding cluster judged so far, the receipt's
    zero-edge pass share (`clusters[cid].expected["passes"]`) by the LAST look read in ANY of its cells (one entry a
    cluster: its curve already covers every cell), summed. `read`: (cluster id, a look read) pairs, any number a
    cluster."""
    last: dict[str, int] = {}
    for cid, k in read:
        if int(k) in PLAN and str(cid) in receipt.clusters:
            last[str(cid)] = max(last.get(str(cid), 0), int(k))
    total = [float(receipt.clusters[cid].expected["passes"][PLAN.index(k)]) for cid, k in sorted(last.items())]
    return round(math.fsum(total), 4)


def _pct(x: Any) -> str:
    return "n/a" if x is None else f"{100.0 * float(x):.1f}"


def beside(receipt: Receipt, *, cell: str, cluster: str, k: int, T: float, c_used_value: float, own_t: float | None,
           passes: int, judged: int, expected: float, u_point: float, u_bound: float, bh_text: str = "") -> str:
    """THE SENTENCE BESIDE A POOLED TRADE (section 8; operator-only, it carries T and the program's own t); the figures
    beside are the founding cluster's (`clusters[cid].beside`; a null prints "n/a")."""
    found = receipt.clusters.get(cluster)
    fig = dict(found.beside) if found is not None else {}
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


def u_cap(u_point: float, u_bound: float, dropped: Sequence[Any] = ()) -> Caps:
    """`caps` under the PREREG's name: CAP_u, WALL_u and report-only from U_u (section 7.2)."""
    return caps(u_point, u_bound, dropped)


def route_of(fwd1: Mapping[str, Any] | None, *, unit_judged: bool, refuted: bool, report_only: bool) -> str:
    """"pool" on THE POOL ROUTE (`on_pool_route`), else "per_program" (S2 or FWD1-R, as today)."""
    return "pool" if on_pool_route(fwd1, unit_judged=unit_judged, refuted=refuted, report_only=report_only) \
        else "per_program"


# ------------------------------------------------------------------------------------------- what a generator may see
_DECIMAL = re.compile(r"\d+\.\d+|%|\bbp\b")


def figure_free(doc: Any, *, ints: Sequence[str] = ("version",), ids: Collection[str] = (),
                id_keys: Collection[str] = (), path: str = "", at: str | None = None) -> list[str]:
    """The places a document a generator-visible process reads holds a FIGURE (section 8: ids and words only): any
    float, any whole number but at a key of `ints`, any text with a decimal number, a "%" or "bp" (a key of a mapping
    too). IDS ARE NOT FIGURES (the conformance review's finding 1: a lineage slug like "gap-50-bp-fade" is an id): the
    text at a key of `ids` (a value, or each text of a list there) and the keys of a mapping at a key of `id_keys` are
    not read for figures (a number there still is one). [] when none. (`at`: the key the value sits at, by default the
    last part of `path`.)"""
    key = path.rsplit(".", 1)[-1] if at is None else at
    if isinstance(doc, bool) or doc is None:
        return []
    if isinstance(doc, float):
        return [path or "<root>"]
    if isinstance(doc, int):
        return [] if key in ints else [path or "<root>"]
    if isinstance(doc, str):
        return [] if key in ids else [path] if _DECIMAL.search(doc) else []
    found: list[str] = []
    if isinstance(doc, Mapping):
        for k, value in doc.items():
            if key not in id_keys and _DECIMAL.search(str(k)):
                found.append(f"{path}.{k}")
            found.extend(figure_free(value, ints=ints, ids=ids, id_keys=id_keys,
                                     path=f"{path}.{k}" if path else str(k), at=str(k)))
        return found
    if isinstance(doc, (list, tuple)):
        for i, value in enumerate(doc):
            found.extend(figure_free(value, ints=ints, ids=ids, id_keys=id_keys, path=f"{path}[{i}]", at=key))
        return found
    return [path or "<root>"]


def scrub_figures(doc: Any, *, word: str, ints: Sequence[str] = ("version",), ids: Collection[str] = (),
                  id_keys: Collection[str] = (), path: str = "", at: str | None = None
                  ) -> tuple[Any, list[str], list[str]]:
    """`figure_free`'s walk, MENDING instead of refusing (the conformance review's finding 1: one bad text never freezes
    a whole document): (a copy of `doc` with every value `figure_free` would name replaced by the fixed `word`, the
    places replaced, the places it cannot mend: a mapping KEY holding a figure outside `id_keys`, which the caller must
    fail closed on)."""
    key = path.rsplit(".", 1)[-1] if at is None else at
    if isinstance(doc, bool) or doc is None:
        return doc, [], []
    if isinstance(doc, float) or (isinstance(doc, int) and key not in ints) or (
            isinstance(doc, str) and key not in ids and _DECIMAL.search(doc)):
        return word, [path or "<root>"], []
    if isinstance(doc, (int, str)):
        return doc, [], []
    mended: list[str] = []
    stuck: list[str] = []
    if isinstance(doc, Mapping):
        out: dict[Any, Any] = {}
        for k, value in doc.items():
            if key not in id_keys and _DECIMAL.search(str(k)):
                stuck.append(f"{path}.{k}")
            v, m, st = scrub_figures(value, word=word, ints=ints, ids=ids, id_keys=id_keys,
                                     path=f"{path}.{k}" if path else str(k), at=str(k))
            out[k] = v
            mended.extend(m)
            stuck.extend(st)
        return out, mended, stuck
    if isinstance(doc, (list, tuple)):
        items = []
        for i, value in enumerate(doc):
            v, m, st = scrub_figures(value, word=word, ints=ints, ids=ids, id_keys=id_keys, path=f"{path}[{i}]",
                                     at=key)
            items.append(v)
            mended.extend(m)
            stuck.extend(st)
        return items, mended, stuck
    return word, [path or "<root>"], []



__all__ = ["NAME", "SCREEN", "PIN_BLOCK", "RECEIPT_PATH", "CONTRACT", "CONFORMANCE", "TOLERANCE", "PREREG_SHA256", "PLAN",
           "WINDOW", "M_MIN", "PRIOR", "SIGMA_FLOOR", "WEIGHT_CAP", "GROUP_SHARE", "COPY_RHO", "MIN_EXPOSURE", "CAP",
           "WALL", "WORST", "N1_OFFSETS", "FLOOR_HAIRCUT", "K_STRESS", "K_MAX", "BOOT_RESAMPLES", "BOOT_BLOCK",
           "SEED_ROOT", "STAGE1_Z", "STAGE1_LAG", "RHO_ASSIGN_Q", "U_COUNTS", "U_PIN_COUNT", "PLACEBO_DRAWS",
           "PLACEBO_COUNT_MAX", "CONSTANTS", "NO_FREE_RIDE", "PLACEBO_CONTROLS", "MAR_FACTOR", "MAR_P", "DEMOTE_EVERY",
           "P1_RULE", "PIN_KEYS", "FLOORS", "MARGINS_K", "C_G_K_RANGE", "NULLS", "SPANS", "BASE_GROUPS", "CLASSES_OUT",
           "EVENT_INPUT", "EVENT_FIELDS", "EVENT_WORD", "PASSING", "PARTS", "PENDING", "FINAL", "REPORT_ONLY",
           "INELIGIBLE", "NONCONFORMING", "WORDS", "Pin", "pin", "load", "CALIB_DIR", "CALIB_FILES", "CALIB_SHA256",
           "CODE_PIN", "CODE_PIN_SHA256",
           "Calib", "calib", "file_sha256", "RECEIPT_KEYS", "REGIME_AXES", "BESIDE_KEYS", "PIN_FLOOR_KEYS", "CV_IDS",
           "ReceiptRefused", "Founder", "UnitSpec", "ClusterSpec", "Rule", "Receipt", "receipt_problem",
           "parse_receipt", "read_receipt", "load_receipt", "rule", "cell_name", "cell_key", "member_pid",
           "reads_events", "excluded", "w_hat", "alpha", "sigma_tilde", "sigma_used", "train_sigma", "cell_day",
           "t_stat", "look", "legs_pass", "look_t", "series_sha", "k_used", "Caps", "caps", "joined_u", "u_count",
           "joined_seed", "quiet", "group_of_symbol", "house_context", "member_meta", "founder_meta", "runs_of", "house_member",
           "train_z", "assign", "merge_copy", "cell_within", "cluster", "BootHook", "house_floor",
           "pin_floors", "minimum_of", "canonical", "market_record", "vector_inputs", "conform",
           "CV_ROUTES", "binom_tail", "mar_void", "placebo_seed", "placebo_draws", "placebo_count", "placebo_holds",
           "control_wbar", "demote", "on_pool_route", "words", "expected_passes", "beside", "alpha_series", "member_z",
           "t_k", "pass_k", "u_cap", "route_of", "figure_free", "scrub_figures"]
