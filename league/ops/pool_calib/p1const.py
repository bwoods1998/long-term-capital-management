"""POOL1 calibration: the constants, every one read from PREREG-POOL1.md (sha256 f42bcdc1...) or stated in
DEVIATIONS.log. PRIVATE scratch code of the calibration (section 4); pinned by sha256 in PINS.log before any run.

Nothing here reads a file. Paths are absolute so every process of the run sees the same inputs."""
from __future__ import annotations

import os
from pathlib import Path

PREREG_SHA256 = "f42bcdc1d694d9be910da298fc2e62e0d4898003645af9a0a04523eb34ac38da"

# ------------------------------------------------------------------------------------------------------------- paths
ROOT = Path("/home/bwoods1998/Work/.ltcm-main/scratch/pooled-screen")
CAL = ROOT / "calib"
REAL_WORK = CAL / "work"
REAL_DATA = Path("/home/bwoods1998/Work/.ltcm-main/scratch/eqlane-1010/data")
REAL_HOUSE_RAW = CAL / "house" / "raw"
#: THE DRY RUN ONLY: POOL1_DATA (an invented market), POOL1_WORK and POOL1_HOUSE (an invented House export) point the
#: code elsewhere; an invented market never writes into the real work directory.
DATA = Path(os.environ.get("POOL1_DATA", str(REAL_DATA)))
WORK = Path(os.environ.get("POOL1_WORK", str(REAL_WORK)))   # prep and run outputs (arrays the code reads)
HOUSE_RAW = Path(os.environ.get("POOL1_HOUSE", str(REAL_HOUSE_RAW)))   # the House job's export
FAKE = DATA != REAL_DATA or HOUSE_RAW != REAL_HOUSE_RAW
if FAKE and WORK == REAL_WORK:
    raise SystemExit("an invented market or House export cannot write into the real work directory")
FW9 = Path("/home/bwoods1998/Work/ltcm-v3/fw9")   # the live code (e136c251); imported read-only for its pure functions

# ------------------------------------------------------------------------------------------------------- data (4.1)
#: A row of one of these years aborts the run (POOL1-F's guard).
SEALED_YEARS = frozenset({"2020", "2021", "2025", "2026"})
#: IN: the House's Train eras (config.TRAIN_ERA_SEGMENTS). No 2015 row is read for IN (DEVIATIONS D3): the House's
#: store starts 2016-01-04, so the stand-ins warm up inside each era.
IN_ERAS = (("2016-01-04", "2019-12-31"), ("2022-01-03", "2024-12-31"))
#: OUT: 2010-15, with 2009 as warm-up; read ONCE after selection on IN (the OUT gate in p1data).
OUT_ERA = ("2010-01-04", "2015-12-31")
OUT_WARM_FIRST = "2009-01-02"
#: Stand-in warm-up inside each IN era (sessions): the longest stand-in lookback (DEVIATIONS D3).
WARM_IN = 120

IDX = ("SPY", "QQQ", "IWM", "DIA")
#: The stand-ins' sector universe: the nine SPDR sectors with rows on every IN and OUT session (XLC starts 2018-06,
#: XLRE 2015-10).
SEC9 = ("XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY")
SEC_ALL = ("XLB", "XLC", "XLE", "XLF", "XLI", "XLK", "XLP", "XLRE", "XLU", "XLV", "XLY")
DEFN = ("TLT", "GLD")
ETFS = IDX + SEC_ALL + DEFN
#: config.HALF_SPREAD_BP (fw9): 1 bp index, 3 bp sectors, 5 bp TLT and GLD.
HS_BP = {**{s: 3 for s in SEC_ALL}, **{s: 1 for s in IDX}, "TLT": 5, "GLD": 5}

# ------------------------------------------------------------------------------------------------- statistic (2)
PLAN = (40, 60, 120)
L = 120
M_MIN = 3
PRIOR = 20
SIGMA_FLOOR = 5e-4                       # 5 bp
WEIGHT_CAP = 3.0                         # sigma_used >= sigma_tilde / 3
GROUP_SHARE = 2.0 / 3.0
COPY_RHO = 0.7
MIN_EXPOSURE = 0.01                      # 1.2: members with Train-era mean total exposure under 1% are out
ZERO = 1e-12
#: FWD1-R's ETF haircut before any live lot is measured (2 bp a side); the calibration uses it (DEVIATIONS D9).
HAIRCUT = 2e-4
K_STRESS = 1.5

# --------------------------------------------------------------------------------------------------- caps (0.5, 7.2)
CAP = 0.12
WALL = 0.15
WORST = 0.15

# ---------------------------------------------------------------------------------------------------- nulls (4.3)
NULLS = ("N0", "N0R", "N1")
N1_OFFSETS = (262, 409, 535, 661, 787)

# ------------------------------------------------------------------------------------------------- the bar (3.3)
K_MAX = 500                              # the grid: c = k / 100, k = 0..500
CG_LO, CG_HI = 140, 250                  # c_G is searched on [1.40, 2.50]
MARGINS = (0, 3, 5)                      # 0.00 / 0.03 / 0.05 in grid steps
FLOOR_DEFS = ("R-REG", "POOLED")
RULES = tuple((fd, mg) for fd in FLOOR_DEFS for mg in MARGINS)

# ---------------------------------------------------------------------------------------------- worlds and draws
M_SIZES = (3, 4, 7, 10, 15)
DRAWS = 16
PATTERNS = ("day0", "stagger")
STAGGER_MAX = 40                         # a third of members join uniformly over sessions 0-40
LAG_MAX = L + STAGGER_MAX                # lags a member's window matrix holds
B_BOOT = 2000
BLOCK_MEAN = 120
SEED_ROOT = 20261026

# --------------------------------------------------------------------------------------------------------- gates
G3_WORSE = 2e-4                          # shadow fills 2 bp a side worse
G3_NOISE = 10e-4                         # plus 10 bp per-side noise (sd)
G7_COPIES = (5, 8, 15)
G7_NOISE = 0.05
G7_MOVE = 0.01
G8_WORLDS = ("normal", "t4", "ar1", "garch", "skewjump")
G8_RHOS = (0.13, 0.26)
G8_M = (3, 7, 15)                        # DEVIATIONS D13
G8_PATHS = 200_000
G8_TRAIN = 1750
G8_B = 200                               # resamples of a synthetic Train path's own bound (DEVIATIONS D13)
G9_SR = 0.5
G9_RATIO = 1.5
POWER_SRS = (0.5, 1.0)
G11_DRAWS = 100
G11_SHARE = 0.90
RHO_ASSIGN_Q = 0.25
STAGE1_Z = -1.0
STAGE1_LAG = 5
#: FWD1-R checkpoint counts U_u is tabulated by (fwd1_rule.PLAN), and the count read at the target clock (Mon Oct 26).
FWD1_PLAN = (5, 10, 15, 20, 30, 40, 60)
U_TARGET_N = 5

# ---------------------------------------------------------------------------------------- the matched family (3.3)
#: (declared class, group) -> the stand-in family whose cross-fitted N1 floor is a House unit's minimum ("same group,
#: nearest class"; pinned here before any figure; DEVIATIONS D12).
MATCH = {
    ("trend_momentum", "index"): "TRD", ("reversal_liquidity", "index"): "REV", ("calendar_flow", "index"): "CAL",
    ("relative_value", "index"): "RV", ("equity_premium", "index"): "VOL", ("event_premium", "index"): "CAL",
    ("dispersion", "index"): "RV",
    ("trend_momentum", "sectors"): "SROT", ("reversal_liquidity", "sectors"): "SREV",
    ("relative_value", "sectors"): "SRV", ("calendar_flow", "sectors"): "SROT", ("equity_premium", "sectors"): "SROT",
    ("event_premium", "sectors"): "SROT", ("dispersion", "sectors"): "SRV",
    ("trend_momentum", "defensive"): "DEF", ("reversal_liquidity", "defensive"): "DREV",
    ("relative_value", "defensive"): "DREV", ("calendar_flow", "defensive"): "DEF",
    ("equity_premium", "defensive"): "DEF", ("event_premium", "defensive"): "DEF", ("dispersion", "defensive"): "DREV",
}
#: A class the table does not name takes the group's default.
MATCH_DEFAULT = {"index": "TRD", "sectors": "SROT", "defensive": "DEF"}

#: The stand-in families' declared class and group (G11's two labels are drawn from the classes).
FAMILY_CLASS = {
    "REV": ("reversal_liquidity", "index"), "TRD": ("trend_momentum", "index"), "CAL": ("calendar_flow", "index"),
    "RV": ("relative_value", "index"), "VOL": ("equity_premium", "index"),
    "SROT": ("trend_momentum", "sectors"), "SREV": ("reversal_liquidity", "sectors"),
    "SRV": ("relative_value", "sectors"), "DEF": ("trend_momentum", "defensive"),
    "DREV": ("reversal_liquidity", "defensive"),
}
CLASSES = ("trend_momentum", "reversal_liquidity", "calendar_flow", "relative_value", "equity_premium",
           "event_premium", "dispersion")

# ------------------------------------------------------------------------------------------- the dry run's scale
#: THE DRY RUN ONLY (an invented market): POOL1_SCALE=small shrinks the draws so the whole pipeline runs in minutes.
if FAKE and os.environ.get("POOL1_SCALE") == "small":
    B_BOOT, DRAWS, G8_PATHS, G8_B, G11_DRAWS = 40, 2, 1500, 20, 10
    M_SIZES = (3, 4, 7)

# ------------------------------------------------------------------------------------------------- the House job
#: Section 12: the one read-only House job runs after this time and stops at the hard stop.
HOUSE_NOT_BEFORE = "2026-10-19T20:05:00Z"
HOUSE_HARD_STOP = "2026-10-19T22:15:00Z"
