"""The deep key's constants: PREREG-H's eras, mask, segments, rules and bars, and how this release reads them.

Owner: R1. Every figure here is a rule, a calendar fact or a pinned receipt figure, never a market result.

PREREG-H (pinned 2026-10-17T19:12:02Z, sha256 6ca65b3e8c9db50aae6d1305ec7fd1a9b5bf7357c2e9219459ac60840ba896dd) is the
authority; `READINGS` states every place where its words leave a choice and the choice this code makes. A reading is
never a loosening of a pinned figure: where two readings were possible the stricter one is taken, or the reason is
given.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Mapping

D = dt.date

PREREG_SHA256 = "6ca65b3e8c9db50aae6d1305ec7fd1a9b5bf7357c2e9219459ac60840ba896dd"

# ----------------------------------------------------------------------------------------------------------- the store
STORE_DIR = "equity-deep"
OPEN_DIR = "open"
SEALED_DIR = "sealed"
STAGING_DIR = ".staging"
GATE_MARK = "DEEP_GATE"
MANIFEST = "manifest.json"
LEDGER = "ledger.json"
#: The ledger as it stood before its last save (`gate.Ledger.save`): what the captain restores a damaged ledger from.
LEDGER_PREV = "ledger.json.prev"
REPORT = "report.json"
#: The data job's marker of a failed audit (counts and verdicts only): no request is made again until the job setting
#: `refetch` asks for it (league/ops/equity_deep.py).
AUDIT_FAILED = "audit-failed.json"
#: THE LOOKS' TEMPORARY STORES (`blocks.looks_dir`): `<state>/equity-deep/sealed/.looks/`, inside the sealed tree (0700,
#: the DEEP_GATE mark). Every relabeled segment, TRAIN-D's and the behavioural test's stores included, is written into
#: a `deep-*` directory there that names its process (`TEMP_PREFIX`, `-p<pid>-`); a look's own block removes it, and a
#: directory a killed process left is SWEPT (`blocks.sweep`) at the start of every deep_report, equity_deep and
#: contamination-probe run and before every new one is made: its process is gone, or it is older than `TEMP_STALE_S`.
LOOKS_DIR = ".looks"
TEMP_PREFIX = "deep-"
TEMP_STALE_S = 2 * 3600
#: The block spans the data job writes: two open, one sealed. The 2016-19 overlap is fetched for the SIP audit only
#: and never kept (`AUDIT_SPAN`).
SPANS: dict[str, tuple[dt.date, dt.date]] = {
    "history": (D(1999, 1, 4), D(2001, 4, 6)),      # look-back for segment A only, never scored
    "dval": (D(2001, 4, 9), D(2008, 12, 31)),       # THE DEEP KEY: sealed
    "traind": (D(2009, 1, 2), D(2015, 12, 31)),     # 2009 look-back + TRAIN-D: open
}
OPEN_SPANS = ("history", "traind")
SEALED_SPANS = ("dval",)
AUDIT_SPAN = ("overlap", D(2016, 1, 4), D(2019, 12, 31))

# ------------------------------------------------------------------------------------------------------------ the eras
FIRST_DAY, LAST_DAY = D(1999, 1, 4), D(2015, 12, 31)
#: Full closures no rule of the repo's calendar produces (PREREG-H "Calendar").
CLOSURES = frozenset({D(2001, 9, 11), D(2001, 9, 12), D(2001, 9, 13), D(2001, 9, 14), D(2004, 6, 11), D(2007, 1, 2),
                      D(2012, 10, 29), D(2012, 10, 30)})
ERAS: dict[str, tuple[dt.date, dt.date]] = {
    "history": (D(1999, 1, 4), D(2001, 4, 6)),
    "dval": (D(2001, 4, 9), D(2008, 12, 31)),
    "lookback": (D(2009, 1, 2), D(2009, 12, 31)),
    "traind": (D(2010, 1, 4), D(2015, 12, 31)),
}
#: The plan's session counts (section 4.1), held to the calendar by a test.
ERA_SESSIONS = {"history": 571, "dval": 1944, "lookback": 252, "traind": 1510}
#: PREREG-H's one-sided mask: nine windows, 235 sessions.
MASK_WINDOWS: tuple[tuple[dt.date, dt.date], ...] = (
    (D(2001, 9, 10), D(2001, 10, 12)),
    (D(2002, 7, 1), D(2002, 7, 31)), (D(2002, 10, 1), D(2002, 10, 31)),
    (D(2003, 3, 10), D(2003, 3, 31)),
    (D(2007, 2, 26), D(2007, 3, 9)), (D(2007, 7, 23), D(2007, 8, 31)),
    (D(2008, 1, 14), D(2008, 1, 31)), (D(2008, 3, 10), D(2008, 3, 31)), (D(2008, 9, 1), D(2008, 12, 31)),
)
MASK_SESSIONS = 235
MASK_BY_WINDOW = (21, 22, 23, 16, 10, 30, 13, 15, 85)
DVAL_MASKED = 1709
#: The fixtures (dates only, one ISO day a line), pinned in the scratch PINS.log: byte-identical copies.
CALENDAR_FIXTURE = "calendar_1999_2015.txt"
CALENDAR_SHA256 = "32383168faa724e3555bc288a8a9d701c03d090796bf903e57520f735f10bd22"
MASK_FIXTURE = "mask_dval_235.txt"
MASK_SHA256 = "a8c00b59e6f3e47ec2b5840cbb0dbe77f5d9deecc08eb5af391216a47f653079"

# -------------------------------------------------------------------------------------------------------- the segments
#: Each segment: (its look-back span, its scored span). A's look-back is the history-only era; B's the 504 sessions
#: of 2003-2004 (scored in A, look-back only in B); TRAIN-D's the 2009 sessions.
SEGMENTS: dict[str, tuple[tuple[dt.date, dt.date], tuple[dt.date, dt.date]]] = {
    "A": ((D(1999, 1, 4), D(2001, 4, 6)), (D(2001, 4, 9), D(2004, 12, 31))),
    "B": ((D(2003, 1, 2), D(2004, 12, 31)), (D(2005, 1, 3), D(2008, 12, 31))),
    "traind": ((D(2009, 1, 2), D(2009, 12, 31)), (D(2010, 1, 4), D(2015, 12, 31))),
}
#: (look-back, scored) sessions of each segment (plan section 5.1), held to the calendar by a test.
SEGMENT_SESSIONS = {"A": (571, 937), "B": (504, 1007), "traind": (252, 1510)}
DVAL_SEGMENTS = ("A", "B")
#: Where the relabeled sessions begin: the Train window's first session (league/equity/config.py WINDOWS["train"]).
PSEUDO_FIRST = D(2016, 1, 4)
#: The block spans each segment reads (A crosses from the open history into the sealed era).
SEGMENT_SPANS = {"A": ("history", "dval"), "B": ("dval",), "traind": ("traind",)}

# -------------------------------------------------------------------------------------------------------- the universe
#: What the gateway's route and the data job fetch: the 16 ETFs of the House universe with a pre-2016 history (XLC
#: starts in 2018 and is never asked for).
FETCH_UNIVERSE = ("SPY", "QQQ", "IWM", "DIA", "XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLRE", "XLU", "XLV", "XLY",
                  "TLT", "GLD")
#: DVAL's 15 (no XLRE, no XLC: plan section 4.1).
DEEP_UNIVERSE = ("SPY", "QQQ", "IWM", "DIA", "XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY", "TLT",
                 "GLD")
#: 2001-04 is the liquid core only (segment A).
LIQUID_CORE = ("SPY", "QQQ", "IWM", "DIA", "XLF", "XLE", "XLK", "TLT")
#: The other sector SPDRs join in 2005 (segment B) when their stale-close audit is clean.
LATE_SPDRS = ("XLB", "XLI", "XLP", "XLU", "XLV", "XLY")
#: First trading days, PUBLIC CALENDAR FACTS (the funds' launch dates), used only where no block says better: the
#: census before the deep store exists. On the House the blocks' own first day is the rule.
INCEPTION: dict[str, dt.date] = {
    "SPY": D(1993, 1, 29), "DIA": D(1998, 1, 20), "QQQ": D(1999, 3, 10), "IWM": D(2000, 5, 26),
    **{s: D(1998, 12, 22) for s in ("XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY")},
    "TLT": D(2002, 7, 30), "GLD": D(2004, 11, 18), "XLRE": D(2015, 10, 8),
}

# ----------------------------------------------------------------------------------------------------- eligibility
CALENDAR_FIELDS = ("weekday", "session_of_month", "sessions_to_month_end", "events", "events_next")
MAX_ROUND_TRIPS_A_YEAR = 50
MAX_OVERNIGHT_SHARE = 0.25
MIN_SCORED_SESSIONS = 750
#: contam_probe's strong recall: a readable cell of the deep era with m above this at p_perm at most `STRONG_P`.
STRONG_M = 0.15
STRONG_P = 0.01
STRONG_ERAS = ("2001-08",)
#: The behavioural test's two labelings of one synthetic store: the store's own sessions from 2016-01-04 (a Monday)
#: and the same arrays from 2019-06-05 (a Wednesday, another month phase and other event days).
BEHAVIOUR_SECOND = D(2019, 6, 5)
BEHAVIOUR_SESSIONS = 760
BEHAVIOUR_SEED = 58

# ------------------------------------------------------------------------------------------------------------ the keys
K_JUDGED = 2.0
K_STRESS = 3.0
#: The recent key's cost: the lane's S2 variant (S2 judges r at k 1.0).
K_RECENT = 1.0
DEEP_FP = 0.15
RECENT_FP = 0.12
FLOOR_MARGIN = 0.05
JOINT_FP_MAX = 0.025
WORST_NO_EDGE_NOW_MAX = 0.12
#: The c grid: k / 100 for k = 0..500 (league/equity/screen.py GRID); a bar past it is INELIGIBLE.
GRID_MAX_K = 500
#: The recent key's windows (the receipt's geometry, H last): R (2020-21, read only inside a begun look: D2 "judged"),
#: V (2025), H (the look's 194 sessions). With `elane.deep.reserve` "sealed" no look is made at all (`gate.look`).
RESERVE = (D(2020, 1, 2), D(2021, 12, 31))
RECENT_LENGTHS = {"R": 505, "V": 250, "H": 194}
#: The recent world's crash-stress positions: R's sessions 2020-02-20..2020-03-23 (the receipt's CRASH set).
RECENT_STRESS = (D(2020, 2, 20), D(2020, 3, 23))
#: OWN FLOORS (the receipt's `floor`): a stationary block bootstrap of the program's own sessions (mean block
#: `FLOOR_BLOCK`, each block circular inside one piece, the piece drawn in proportion to its length), `FLOOR_WORLDS` a
#: world set, BASE and CRASH; each piece from its first decision + `POOL_SKIP` sessions; seeds
#: default_rng([*FLOOR_SEED, set (BASE 1, CRASH 2), key (deep 1, recent 2), int(version sha256[:8], 16)]).
FLOOR_WORLDS = 20_000
FLOOR_CHUNK = 1_000
FLOOR_SEED = (20261017, 3, 7)
FLOOR_BLOCK = 120
POOL_SKIP = 2
MIN_PIECE = 300
#: The CRASH set's stress sessions: the top `STRESS_SHARE` of the pool by the trailing `STRESS_LOOKBACK`-session
#: realized volatility of the equal-weight cost-free return of the program's universe (TRAIN-D: August 2011, 2015).
STRESS_SHARE = 0.05
STRESS_LOOKBACK = 20

# ----------------------------------------------------------------------------------------------------------- the looks
LOOKS_PER_VERSION = 1
LOOKS_PER_CELL = 3
LOOK_BUDGET = 150
CANARY_EVERY = 10
CANARY_RATE = 0.15
CANARY_BAND = 0.95
#: The canary's slot in each block of ten looks: default_rng([*CANARY_SLOT_SEED, block]).integers(10); its timing:
#: default_rng([*CANARY_SEED, look index]) (the receipt's `canary`).
CANARY_SLOT_SEED = (20261017, 3, 8)
CANARY_SEED = (20261017, 3, 9)
#: The canary's schedule covers this many decisions a run (the longest run it takes: TRAIN-D's 1,510 + its look-back).
CANARY_STEPS = 2_048
#: A look begun whose sealed run was sent and did not return (league/equity/runner.py `RunLost`), or whose process was
#: killed, is owed again once; the second time it is spent and failed (league/swarm/elane.py `LOOK_SENDS`'s rule).
LOOK_ATTEMPTS = 2
#: A version whose look the House could not make (an error of the House's, before or after the look was begun: the
#: look is never spent by it) is tried again on later nights; after this many errors under one deep identity it is
#: refused (no look spent) with a House warning, until a release moves the identity.
HOUSE_ERRORS_MAX = 3
#: The canaries' REPORT-ONLY alarm (not a halt; the review of Oct 17): the receipt's own synthetic canary deep-key pass
#: rate, its largest over D1-D5 (docs/benchmarks/equity_screen_3.json canary.synthetic_canary_deep_pass_raw_k2, D4).
#: The alarm fires when the canaries' deep passes exceed the upper end of the central 95% band at THIS rate; the
#: pre-registered halt stays at 15% (PREREG-H), which only gross breakage reaches (`LIMITS`).
CANARY_REFERENCE = 0.00778

# -------------------------------------------------------------------------------------------------------- the receipt
#: The candidate receipt: history-1017 item 5's synthetic S3 receipt, copied VERBATIM from the captain's scratch
#: (receipt/equity_screen_3.json, its code pinned in PINS.log at 19:38:19Z before its one run, all gates G1-G8 passed).
#: docs/benchmarks/ never reaches the House box, so the figures a look reads are these; a test holds them and the sha
#: to the file. `c_R` is the R+V+H bar: the receipt calibrates the recent key with the reserve in it.
RECEIPT_PATH = "docs/benchmarks/equity_screen_3.json"
RECEIPT_SHA256 = "4ff8435b99de84367fb3d0c45adb0750c929a39755b94eebcf1276c356cdee91"
RECEIPT: dict[str, Any] = {"c_D": 1.02, "c_R": 1.2, "fp_zero_edge": 0.01666, "fp_deep": 0.14781,
                           "fp_recent": 0.11763, "worst_no_edge_now": 0.103}

# ----------------------------------------------------------------------------------------------------- the legacy ids
#: The engine the relabel equivalence battery was proven on (league/tests/test_deep_relabel.py): R1 moves neither id,
#: and a release that moves one re-runs the battery and names the new ids here (league/tests/test_deep_identity.py).
LEGACY_IDS = {"equity": "78022ca6", "options": "b60410ad"}

# ------------------------------------------------------------------------------------------------------------ settings
MODES = ("off", "report")
RESERVE_MODES = ("sealed", "judged")
#: THE OWNER'S D2 IS DECIDED (the captain's A58, by the owner's delegation): the 2020-21 reserve IS judged, inside S3
#: beside the deep key and never alone. "judged" is the default; "sealed" is the switch back, under which NO look is
#: made at all (a version is judged on both keys or not at all: `gate.look`).
DEFAULTS: dict[str, Any] = {"mode": "off", "reserve": "judged", "looks_per_run": 2}
LOOKS_PER_RUN_BOUNDS = (0, 10)
#: The deep_report job's wall (league/ops/registry.py, held equal by a test) and the room a look needs: no version is
#: begun with less than `LOOK_ROOM_S` of the wall left, so the wall's SIGKILL does not land inside a look.
JOB_WALL_S = 3300
LOOK_ROOM_S = 1200
#: THE LEVEL TEST (report-only; the review of Oct 17): the behavioural test's store run again with every price times
#: `LEVEL_PRICE` and every volume times `LEVEL_VOLUME`. A program whose entries and exits move is a LEVEL READER (it
#: reads price or volume levels, which tell 2001-08 from 2016-24): counted in the report beside the verdicts, never a
#: refusal (PREREG-H names no such rule; an amendment would make it one).
LEVEL_PRICE = 2.5
LEVEL_VOLUME = 0.4

#: THE READINGS: where PREREG-H's words (and the receipt's floor and canary specification) leave a choice, the choice
#: made (league/deep/DEEP.md points here; the captain's report carries their count).
READINGS = (
    "x2's mu_s is the mean over the series being scored: all scored DVAL sessions for the full t, the unmasked ones "
    "for the masked t (the receipt's rule); so a mechanism whose only edge is the masked windows passes neither",
    "the k 3.0 stress re-costs the k 2.0 run's lots at 3 x hs in the constant-weight accounting (no second run)",
    "the scored sessions of a segment start once every NEEDS symbol has NEEDS history bars; a segment a symbol is "
    "not allowed in (a non-core fund before 2005, a late SPDR whose stale-close audit failed) is not scored",
    "round trips and the close-to-next-open share are measured on the version's Train-era runs, before the look",
    "the recent key is S2's r at k 1.0 pooled over R+V+H, raw (no drift removed: the S2 variant); the receipt "
    "computed its recent null at k 2.0 with the true drift removed, and under N0 the null rate does not depend on k, "
    "so c_R holds at k 1.0",
    "D2 is 'judged' (A58): a real look reads BOTH keys or neither; with elane.deep.reserve 'sealed' no look is made "
    "(no DVAL and no reserve run); the reserve's runs are made only inside a begun look, after the deep key's",
    "the scored sessions of a segment start once every NEEDS symbol has history + 1 bars at the first decision (the "
    "engine's ctx, league/equity/store.py `_slice`): at history 504 segment B scores 1,006 sessions, not the plan's "
    "1,007 (the census counts history bars before the first scored session: one session looser, an upper bound)",
    "a segment where a NEEDS symbol misses a session after its first bar (the audit's gaps) is not scored, so no "
    "look is spent on a gap; the audit itself fails closed on any gap of a DVAL fund in dval and traind",
    "a family with no route named: a captain's seed (or its lineage) has no generator's recall to read and is "
    "measured as not strong-recall, counted apart by source; any other is refused (its recall cannot be read)",
    "the deep floor's worlds take the program's own scored layout (1,944 sessions and the mask's positions when it is "
    "scored on all of DVAL); the pool is the Train-era and TRAIN-D runs' lots re-costed at the key's k",
    "a canary halt fires when the canaries' deep-key passes exceed the upper end of the central 95% binomial band "
    "at 15% (its 97.5% quantile); a canary slot before the block's first real look moves to the next slot",
    "strong recall is read on contam_probe's 2001-08 cells; a route not yet measured there waits (no look spent)",
    "a sealed or recent-window run the program's own errors ended ('disqualified') is a look spent and failed; one "
    "sent whole and not answered (RunLost), or a look whose process was killed, is owed once, then spent and failed; "
    "any other error of the House's spends nothing (the attempt is withdrawn) and, three under one identity, refuses",
)

#: THE LIMITS the receipt does not state (both reviews of Oct 17), carried in the captain's report beside the counts;
#: each is for a re-pinned receipt builder or a PREREG amendment before H-lite gates a seat.
LIMITS = (
    "the canary halt at 15% catches gross breakage only: synthetic canaries pass the deep key 0.4-0.8%, so a bug that "
    "lifts that tenfold halts by the 15th canary about 1.8% of the time; the report-only alarm reads the receipt's "
    "own rate (CANARY_REFERENCE)",
    "x2's t divides by the sd of x2, which carries the variance of simply holding positions: invested programs' "
    "zero-edge rates collapse, and the receipt's power, PPV and Sharpe-for-50% figures are in units of x2's sd, not "
    "the program's return Sharpe",
    "the recent key re-reads Validation and the holdout, which S2 used to seat a version: a seated version's recent "
    "pass overstates the evidence, so the report counts seated versions apart",
    "the relabel hides dates, not price or volume levels: the level test counts level readers, refusing none",
    "seeds carry mechanisms published in 2008 whose discovery samples overlap DVAL: the report counts by source",
)


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def cfg(settings: Mapping[str, Any] | None) -> dict[str, Any]:
    """`elane.deep` of the swarm's settings: `mode` ("off" | "report"), `reserve` ("judged", the owner's D2 as
    decided, | "sealed", the switch back: no look at all), `looks_per_run` (0-10). A malformed value is its default;
    an unreadable block is `DEFAULTS` (mode off)."""
    out = dict(DEFAULTS)
    lane = settings.get("elane") if isinstance(settings, Mapping) else None
    block = lane.get("deep") if isinstance(lane, Mapping) else None
    if not isinstance(block, Mapping):
        return out
    if block.get("mode") in MODES:
        out["mode"] = block["mode"]
    if block.get("reserve") in RESERVE_MODES:
        out["reserve"] = block["reserve"]
    n = _num(block.get("looks_per_run"))
    if n is not None and n.is_integer() and LOOKS_PER_RUN_BOUNDS[0] <= n <= LOOKS_PER_RUN_BOUNDS[1]:
        out["looks_per_run"] = int(n)
    return out


__all__ = [name for name in dir() if name.isupper() and len(name) > 1] + ["cfg"]
