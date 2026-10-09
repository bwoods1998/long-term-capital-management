"""The `dlane` job (at the House's start and daily 01:30Z) and THE DIRECTION LANE's report (release D-1, Oct 9, 2026;
`league/swarm/dlane.py`; the plan of Oct 9, D8 and its section 6; the operator's decisions 8 and 9): one operator-only
file, `<state>/dlane-report.json`, that says each day what the two research lanes did, what the Probe envelope holds,
where the goal's Done stands under its pinned reading rule, and which of the lane's alarms hold.

OPERATOR-ONLY AND REPORTED: no agent reads it, and no module of league/swarm, league/live or league/gym imports this
module or names its file (`league/tests/test_dlane_report.py` pins that). It changes no site data contract: the website
reads nothing new. It is written whatever the figures say; it never pauses, slows or stops a program or a route.

READ-ONLY, BUT FOR K5. The swarm store is opened read-only and the live book through `guard.read` (`mode=ro`), inside
`guard.readonly()` (every SQLite open in the child is a `mode=ro` URI). The one write is K5's (decision 9): when the
direction lane's realized net over every route since the options swarm began is at or below K5's line (`dlane.k5_line`:
`dlane.k5_net_usd`, -$600, below the net at the operator's last clear; -$600 itself before any), the job writes the swarm
store's kv `dlane_k5` {at, net, line} once (`dlane.k5_trip`, a writable open AFTER the read-only report). While it is
set the lane reads "shadow" (`dlane.mode_effective`: no new direction Candidate, no incubator direction mark) until the
operator clears it (swarm.json `dlane.k5_clear` true, or deleting the kv). The job records a clear on its next run
(`dlane.k5_rearm`, before the trip check: the kv deleted, the kv `dlane_k5_base` at the net then), so the clear holds
and K5 is armed again at -$600 below that net (the review of Oct 9, 2026). While `dlane.k5_clear` is true K5 can
neither hold nor trip: the report raises a K5 warning every run until the operator takes it out. A tightening, never a
trade, never an order.

WITH THE LANE OFF (`dlane.mode` "off", THE ROLLBACK) the job writes nothing and returns a `skipped` receipt.

THE DONE METER (DONE-RULE.md, pinned Oct 9, 2026 before release L-D or D-1 shipped; `dlane.DONE` holds its sha256 and
constants), read exactly as pinned:
- WHAT COUNTS: every real close of an agent program (a swarm family; never a House route: the calibration round trips,
  the House live test, any `house:*` family) closed since 2026-09-26T06:23Z on Probe/Sized `:r`, tuition `:t` or the
  incubator `:i` (`economics.route_of`), the Oct 8 tuition close included. Nothing is dropped after the fact: a close on
  an agent route the rule does not name is listed apart with a House warning, never silently counted or lost.
- P&L: realized after all fees: the book's cash (fees included at the book's estimate) plus the broker's posted fee
  correction where it has posted (`publish.json`'s saved activity reading, `fees_by_pid`: `league/account_activity.py`),
  each close labelled `broker` or `estimate`. A close the book could not price (`unpriced_close`) makes a meter's net
  unknown, never an invented zero.
- TWO METERS: `done_screen` (`:r` only, the evidence route) and `done_all` (`:r` + `:t` + `:i`, the goal's letter).
- THE BAR: at least 30 closes, at least 5 closes from each of at least 2 programs, and net > 0 after fees.
- CONSISTENT WITH REPLAY: every program with 5 or more MATCHED closes (closes of a version on a day its nightly replay
  also traded: D5's measure, `money.forward_stats`, read here live minus replay and pooled over the program's versions)
  has a mean gap within +/-0.10 a dollar of maximum loss. A program under 5 matched closes is listed with its gap,
  never dropped.
- READ ONLY AT CHECKPOINTS: the 30th counted close, then every 10th; each reading is over exactly the first K closes in
  close order (`checkpoints`). The running figures between checkpoints are counts, never a reading. A8 (an `info` alert)
  names a checkpoint that holds the first time a report sees it.
- BESIDE IT, ALWAYS: P(Done | zero edge) (`dlane.done_zero_edge_p`, MONEY's simulation of this same reading rule,
  labelled as such); the same-risk buy-and-hold two ways (below); the world-conditional false-positive rate beside the
  unconditional one for the screen that admitted each Candidate, Probe or Sized family (`probes`); every loosened rule
  with its cost (`LOOSENED`); the contamination statement (`CONTAMINATION`); and `dlane.LABEL` on every direction figure.

THE SAME-RISK BUY-AND-HOLD (the plan's section 6, item 3), per counted close, summed beside each meter and checkpoint.
Both are labelled approximations from the `direction` job's daily closes (`direction-closes.json`):
- delta-matched: the structure's entry delta (Black-Scholes at ONE implied volatility solved from its entry value, the
  entry day's close as the spot: `league.options_history`), times 100 x its units, held in the root's own stock from the
  entry day's close to the exit day's close. An index root with no stock bars (XSP, SPXW) is not priced this way.
- dollars at risk: the close's maximum loss held in the root (SPY standing in for XSP and SPXW) over the same closes.

THE REST OF THE REPORT:
- `funnel`, per lane over the last 24 hours and 7 days, each count from the record that is the event itself: births
  (`swarm.born`; the payload's lane, else the family's declared lane), Gym runs by window and the program-years they
  cost (the Gym is shared: direction runs slow alpha's), Validation tries and passes (`swarm.tournament`), reviews and
  audits (`swarm.gate`), holdout looks and passes by the screen each look recorded, band moves, real closes by route; the
  bands now; and the direction lane's Train-bar failure counts (`dlane.failure_counts`).
- `fp_beside_trades` (release D-1b; the owner's goal of Oct 9, item 4): every real Probe trade (`:r`, open or closed)
  and every agent real close, each with its program's screen and that screen's false-positive rates at zero edge
  ({screen, fp_lane_mixed, fp_lane_2224, receipt}: the passed look of the version it trades, `trade_screens`), and the
  contamination statement beside them.
- `probe_envelope`: THE PROBE LOSS BUDGET as release L-D's money table reads it from the constitution (`loss_basis`
  "net", $400 of worst net stretch in any `loss_window_sessions` 20 sessions AND $400 net in total, `max_open`,
  `demotion`): the code in force's own figure (`fast_lane.probe_budget`, which names its basis and the envelope that
  binds), and under each basis, GROSS and NET, the window's and the total's realized figures (`real.probe_figures`, told
  the basis by name), both rooms, the binding one and the room in units of today's cap.
- `account`: the equity change since E0 (the first equity reading this report saw: it is written into the file and read
  back next day) beside the agents' and the House's realized closes since then and the account's other activity; what
  is left is labelled unexplained (open positions' marks included).
- `costs`: the swarm's research spend by meter since the options swarm began and since the lane started: LTCM's profit is
  trading net minus these, and the report says so (the gateway's own spend is the gateway's meter, not read here).
- `contamination.meters`: (a) the holdout's head-minus-tail Sharpe gap per lane (`fast_lane.pooled_contamination` over
  the fast lane report's looks), (b) the mean excess over the same-risk buy-and-hold in the known window (Validation)
  against the unknown one (live), per lane, (c) live against the holdout per band (the fast lane report's rows).
- `alarms`: A1-A9 and K5 (HARNESS section 5, as amended by the plan and the operator's decisions; K5 also while
  `dlane.k5_clear` disarms it), each a House alert through `ctx.alert` (warning, or info for A8 and A9), never an action
  on money.

Standard library only, except the Probe envelope's figures (`fast_lane.probe_budget` and `real.probe_figures` read
`league.live.real`, whose Gym legs need numpy, as the House box has): they are an `error` entry where that cannot load.
"""
from __future__ import annotations

import json
import math
import statistics
import time
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

FILE = "dlane-report.json"
SCHEMA = 1
#: The House's state files this report reads (never writes, but its own).
LIVE_DB = "live.sqlite"
PUBLISH_FILE = "publish.json"
FAST_LANE_FILE = "fast-lane-report.json"
HEALTH_FILE = "health.json"
#: `economics.route_of`'s agent routes, as the Done rule names them; the House's routes are never counted.
ROUTE_CODES = {"d2_real": ":r", "tuition": ":t", "incubator": ":i"}
HOUSE_ROUTES = ("calibration", "house_test", "house_other")
#: The funnel's windows, in hours.
WINDOWS = {"24h": 24.0, "7d": 168.0}
#: The Gym windows the funnel counts.
RUN_WINDOWS = ("train", "validation", "holdout", "mechanism", "forward", "probe")
#: A run row with one of these statuses is not a Gym evaluation (`funnel.NOT_RUN`).
NOT_RUN = ("refused", "error")
#: A3's waits (HARNESS section 5): a direction best that cleared every Train bar waits for its Validation more than this
#: many hours; a direction Validation pass waits for its holdout look more than this many.
A3_VALIDATION_HOURS = 6.0
A3_GATE_HOURS = 12.0
#: A2: a direction version cleared every Train bar this long ago and no direction Validation try or look since.
A2_HOURS = 24.0
#: A6 (K7): fewer than 1 eligible direction version per this many direction births over 48 hours, judged once the 48
#: hours hold at least this many births (fewer cannot show the ratio).
A6_BIRTHS = 50
A6_HOURS = 48.0
#: A9: every live direction program has opened nothing for this many sessions.
A9_SESSIONS = 10
#: The label of the zero-edge figure (decision 8).
ZERO_EDGE_LABEL = "P(Done | zero edge), simulation"

#: THE CONTAMINATION STATEMENT (the plan's section 6, extended by the critic's N10 and the operator's decision 8: the
#: 2017-19 census is spent for the direction lane as a whole). In every report, verbatim but for two figures of the
#: operator's private studies, which stay private (the operator's rule: no private-study figure in the repository).
CONTAMINATION = (
    "Train (2022-24), Validation (2025) and most of the holdout (Jan-Sep 2026) lie inside the training data of every "
    "author: the swarm's models and the operators who designed this lane (Claude Opus 5.5, data to June 2026). They know "
    "which of those windows rose. A direction program passes Validation and the look almost only when both windows rose "
    "(nearly every pass in the operator's simulated worlds). So the screen's false-positive rate is a property of the "
    "procedure across historical worlds, not a guarantee in this one. Choosing to open a direction lane now was itself "
    "made by authors who know those years, and that cannot be measured. The 2017-19 census is spent: for the operator's "
    "gates (in-sample, unconfirmed) and for the direction lane as a whole (its guidance on deltas and holds came from "
    "it), so a 2017-19 era is no clean confirmation for a direction program. The clean evidence is the holdout tail after "
    "2026-07-01 (partly) and the live record from the first real close. Done is decided on that record. Measured each "
    "day: (a) the holdout's Sharpe gap before and after 2026-07-01 per look, pooled with its t; (b) the excess over the "
    "same-risk buy-and-hold, in known windows minus unknown ones; (c) live against the holdout, per dollar of maximum "
    "loss, per band."
)

#: EVERY LOOSENED RULE WITH ITS COST (HARNESS 7.4, the plan's section 2 and the operator's decisions of Oct 9): the
#: header of every report (the plan's section 6, item 5). Costs are the operator's measurements (MONEY's simulation and
#: the critic's), stated as measured; release L-D's rows are its own release's, listed because they ride beside every
#: Done figure.
LOOSENED: tuple[dict[str, str], ...] = (
    {"rule": "beat your own exposure", "was": "every family (agenda v19 item 2)", "now": "the alpha lane only",
     "cost": "programs whose profit is index beta reach Validation; the lane is leveraged index beta minus option "
             "costs, reported beside the same-risk buy-and-hold, never called alpha"},
    {"rule": "the Train objective", "was": "the worst Train year's t",
     "now": "direction-v2 for the direction lane: E1, E3, E4, E5 on the 1.0x run; P1, R2, R3 on the 1.5x run; E2, R1 "
            "and the mechanism test reported only; holds of 2 to 8 sessions all admissible",
     "cost": "an always-in call program can pass this bar and the gate is not tested by it; more null programs reach "
             "Validation (more paid reviews and audits, more false passes in count); the false-positive rate per "
             "program screened is unchanged (Train is in-sample)"},
    {"rule": "the hidden look (the learning game)", "was": "every core-five lineage may play",
     "now": "no direction lineage plays (dlane.arm_fraction 0)",
     "cost": "the game's selection pressure is lost for direction; the lane's false-positive rate at zero edge rises "
             "from 0.02% to 0.70% before the screen change below"},
    {"rule": "the holdout look (screen S-C)", "was": "p <= 0.10 and a Sharpe of at least 0.5 of Validation's (S-B)",
     "now": "direction lane only: p <= 0.20 and a Sharpe share of 0.25; the Validation line as coded (since release "
            "D-1b the rollback screen: swarm.json dlane.screen \"S-C\")",
     "cost": "false-positive rate at zero edge: the lane 0.70% -> 1.41% (cluster interval 0.54-2.43%), all cells "
             "0.80% -> 1.53%, swarm placebos 0.18% -> 0.27%; 2.22% when both windows rose; power at +10%: "
             "1.68% -> 3.22%"},
    {"rule": "the holdout look (screen D2, release D-1b)", "was": "S-C (above)",
     "now": "direction lane only, calls only: on Validation at least 50 trades on 25 entry days with a mean entry-day "
            "return above zero; after the one look, the pooled entry-day t over Validation and the holdout at least "
            "c = 1.00 and the holdout's P&L above zero (receipt docs/benchmarks/direction_screen_2.json, sha c3605947)",
     "cost": "the lane's false-positive rate per program at zero edge 1.41% -> 10.37% on mixed worlds (95% world "
             "interval 9.57-11.16%, cluster 7.90-12.76%) and 12.39% on 2022-24 worlds (upper bound 13.29%); all "
             "census cells 13.37% (upper bound 14.08%) and 14.11% on 2022-24 worlds (upper bound 15.01%); swarm "
             "placebos 4.76%; power at +10% 3.22% -> 19.95%. Adopted AFTER it failed the operator's own pre-registered "
             "adoption rule (every upper bound at most 12%): a post-hoc loosening of that ceiling. The lane's rate "
             "stays under the owner's 15% per program; all cells (verticals included) reach 15.01% at the upper bound "
             "on 2022-24 worlds, which is why D2 runs only while the lane is calls only. Weak discrimination: it "
             "passes mostly programs whose screen windows rose; the Probe loss budget (release L-D: $400 of worst net "
             "stretch in any 20 sessions and $400 net in total) bounds the money"},
    {"rule": "the leakage alarm", "was": "one count over every look: 10 looks, over 30% passing",
     "now": "per lane: alpha unchanged; direction 10 looks, over 60% passing",
     "cost": "a real holdout leak in a direction program trips later; the paid review and audit and the post-cutoff "
             "tail still check every look"},
    {"rule": "the incubator mark", "was": "the drift screen alone (the owner's term, Sept 29-30)",
     "now": "direction families: the direction-v2 verdict",
     "cost": "with no edge about -$36 a week expected, at most $150 a week (about $650 a month); its closes are never "
             "evidence"},
    {"rule": "graveyard DRIFT rows", "was": "bind every card", "now": "do not bind a direction card",
     "cost": "direction ideas the drift screen buried may return, once each, inside the rebirth budgets"},
    {"rule": "graveyard alpha rows (PR #519, deployed 12:44Z Oct 9)", "was": "bind every card",
     "now": "a direction card is bound only by direction families' graveyard rows (DRIFT rows never); alpha cards are "
            "bound by every row, as before",
     "cost": "more direction births may retry ideas similar to dead alpha ones; each lineage still gets one Validation "
             "try and one holdout look, at D2's measured false-positive rate of 10.4% per program (mixed worlds)"},
    {"rule": "the birth quota", "was": "no lane",
     "now": "direction gets at least half of a pass's births while under half of the last 24 hours' (at most 60%)",
     "cost": "alpha births fall from about 73 to about 36 a day mid-way through the game's T0 experiment; the "
             "researcher's ROLE prompt (a shared prefix) changes for alpha researchers too, so 'alpha golden' holds "
             "for code paths only"},
    {"rule": "the unit", "was": "MONEY's pre-registered $75 lane cap",
     "now": "10% of equity on the swarm side (E5) as on the live side",
     "cost": "Probe-stage Done averaged over holds 6.3% against 7.8%; P(net <= -$360 in 8 weeks) 0.35 against 0.27"},
    {"rule": "K5's clear (dlane.k5_clear)", "was": "no K5 before D-1",
     "now": "true clears a set K5 at once and disarms K5 while it stays set; the job's next run records the clear and "
            "re-arms K5 at -$600 below the net then (deleting the kv clears the same way, with no setting)",
     "cost": "while dlane.k5_clear stays true the lane can lose past any line with no K5 (the report warns every run "
             "until it is taken out); after a clear, K5 measures a further -$600 from the net at clearing, not from "
             "inception"},
    # THE TRAIN MAP (Oct 9, 2026; PR #520). The graveyard fix's row sits beside the DRIFT rows' above.
    {"rule": "the TRAIN MAP (dlane.train_map; PR #520, deployed 16:17Z Oct 9)",
     "was": "agents read the lane's rules and their own runs, never an operator study's figure",
     "now": "the architect's LANES block lists the call shapes that pass direction-v2 on the Train years in the "
            "operator's census (one line each: S_D to one decimal, the unit's verdict as a word) and the census's "
            "lessons; a direction researcher's brief the lessons and the 5 best passing shapes on its roots; labelled "
            "in-sample (league/swarm/dlane_map.json); swarm.json dlane.train_map false hides it",
     "cost": "births aim at in-sample winners, so more programs whose Train profit is index beta reach the screen; the "
             "screen's false-positive rate per program is unchanged (Train is in-sample), and more programs screened "
             "means more false passes in count (more paid reviews and audits)"},
    {"rule": "release L-D: the Probe budget read NET", "was": "GROSS: a gain never offsets a loss",
     "now": "NET over closed Probe positions (Sized never offsets): in the window its worst net stretch (a gain offsets "
            "only the losses closed before it), in total from inception",
     "cost": "P(net <= -$360 in 8 weeks, no edge) 0.19 -> 0.27; gross Probe losses can pass $400"},
    {"rule": "release L-D: Probe slots", "was": "3", "now": "8 (the $400 envelopes bind first)",
     "cost": "P(net <= -$360) 0.30 -> 0.35; P(net < -$400) 2.1%, through Sized"},
    {"rule": "release L-D: DM1 demotion", "was": "D5's loss leg (-3 x mean maximum loss)",
     "now": "sticky demotion when 10+ real trades sum below -1.645 sigma sqrt(n)",
     "cost": "a losing program trades longer: P(net <= -$360) 0.27 -> 0.30"},
)
#: And what D-1 TIGHTENED (said beside the loosenings), with release L-D's rolling budget, a tightening of its NET.
TIGHTENED: tuple[str, ...] = (
    "K5: the lane reads shadow (no new direction Candidate, no incubator direction mark) once its realized net over every "
    "route is at or below -$600 (after a clear: -$600 below the net at clearing), until the operator clears it",
    "the screen, the leakage alarm and K5's line can only be tightened by a setting (dlane.cfg's bounds); the one "
    "setting that loosens K5 is dlane.k5_clear, which disarms it while it is true (listed with its cost among the "
    "loosened rules)",
    "D2 is refused unless a receipt's sha256 and its c are pinned in the repository's policy.json and CI holds the "
    "receipt to it, and unless the lane is calls only (release D-1b)",
    "E5: one lot at today's prices within 10% of equity before Validation",
    "release D-1b: ONE Validation try and ONE holdout look per direction lineage (was: the alpha lane's three looks and "
    "tries until retirement), so a lineage's false-positive rate is the program's; a lineage that spends either without "
    "a pass still in play retires",
    "release D-1b: calls only: dlane.structures [\"long_single\"] (no debit vertical, no put) and every Train trade a long "
    "call (bar C1)",
    "release L-D's rolling Probe budget (L9, beside NET above): the $400 is a wall over any 20 New York sessions, read "
    "as the window's worst net stretch, AND $400 net in total from inception (the owner's ceiling is $800; raising it "
    "is CON-only); a bad stretch that ages out of the window frees no room in the total. Measured cost (the budget "
    "simulation, post-hoc, as traded, holds 2/3/5): P(Done) at 12 weeks 6.0/3.3/1.0% against 10.0/7.6/4.5% with the "
    "$400 total alone, at 24 weeks 11.1/8.7/5.9% against 11.0/9.0/7.6%",
)


# ------------------------------------------------------------------------------------------------- small helpers
def _num(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        value = float(value)
    if isinstance(value, str):
        try:
            value = float(value)
        except ValueError:
            return None
    if not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(float(value)) else None


def _dec(value: Any) -> Decimal | None:
    try:
        out = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return out if out.is_finite() else None


def _usd(value: Decimal | float | None) -> float | None:
    return None if value is None else round(float(value), 2)


def _iso(epoch: float | None) -> str | None:
    if epoch is None:
        return None
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(float(epoch)))


def _epoch(text: Any) -> float | None:
    if isinstance(text, (int, float)) and not isinstance(text, bool):
        return float(text)
    try:
        return datetime.fromisoformat(str(text).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return None


def _ny_day(epoch: float | None) -> str | None:
    from zoneinfo import ZoneInfo

    if epoch is None:
        return None
    try:
        return datetime.fromtimestamp(float(epoch), ZoneInfo("America/New_York")).date().isoformat()
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _loads(text: Any, default: Any) -> Any:
    if isinstance(text, (dict, list)):
        return text
    try:
        return json.loads(text) if text not in (None, "") else default
    except (TypeError, ValueError):
        return default


def version_of(instance: Any) -> int | None:
    """The program version an instance key names (`<family>@<version>:<kind>`), as `league/live/step.py` reads it."""
    try:
        return int(str(instance).rsplit("@", 1)[1].split(":", 1)[0])
    except (IndexError, ValueError):
        return None


def inception() -> float:
    """The Done rule's start (`dlane.DONE["inception"]`) as epoch seconds."""
    from ..swarm import dlane

    return float(_epoch(dlane.DONE["inception"]))


# ------------------------------------------------------------------------------------------------- the lanes
class Lanes:
    """Each family's declared lane (`dlane.declared_lane`: its spec's, else its card's), read once a family."""

    def __init__(self, store: Any):
        self.store = store
        self.cache: dict[str, str] = {}

    def of(self, fid: Any, fam: Mapping[str, Any] | None = None) -> str:
        from ..swarm import dlane

        fid = str(fid or "")
        if fid not in self.cache:
            try:
                fam = fam if fam is not None else self.store.family(fid)
            except Exception:  # noqa: BLE001 - an unreadable family is alpha (the lane's default)
                fam = None
            self.cache[fid] = dlane.declared_lane(self.store, fam) if fam is not None else dlane.ALPHA
        return self.cache[fid]


# ------------------------------------------------------------------------------------------------- the book
def read_book(live_path: str | Path) -> dict[str, list[dict[str, Any]]]:
    """The live book's positions and instances (read-only; an absent book is an empty one: nothing traded)."""
    from . import guard

    path = Path(live_path)
    if not path.exists():
        return {"positions": [], "instances": []}

    def read(db: Any) -> dict[str, list[dict[str, Any]]]:
        tables = set(guard.ids(db, "SELECT name FROM sqlite_master WHERE type='table'"))
        positions = guard.rows(db, "SELECT pid, instance, family, type, root, legs, qty, opened_qty, entry, max_loss_share, "
                                   "fees, cash, opened_at, opened_day, status, closed_at, tuition, info FROM positions "
                                   "ORDER BY pid") if "positions" in tables else []
        instances = guard.rows(db, "SELECT id, family, version, band, tuition, mode, created_at, retired_at FROM instances"
                               ) if "instances" in tables else []
        return {"positions": positions, "instances": instances}

    return guard.read(path, read)


def fee_corrections(root: str | Path) -> dict[str, Any]:
    """The broker's posted fee corrections per position (`publish.json`'s saved activity reading: `fees_by_pid`, the
    broker's charged fees less the book's estimates, `league/account_activity.py`) and the account's other activity, or
    {} parts with `why` when there is no reading."""
    out: dict[str, Any] = {"by_pid": {}, "as_of": None, "read_at": None, "other": None, "why": None}
    try:
        saved = json.loads((Path(root) / PUBLISH_FILE).read_text(encoding="utf-8")).get("activity")
        reading = saved["reading"]
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        out["why"] = "no saved activity reading in publish.json: every close's fees are the book's estimate"
        return out
    for pid, value in (reading.get("fees_by_pid") or {}).items():
        d = _dec(value)
        if d is not None and str(pid).isdigit():
            out["by_pid"][int(pid)] = d
    out["as_of"], out["read_at"] = reading.get("as_of"), saved.get("read_at")
    out["other"] = {k: _usd(_dec(reading.get(k))) for k in ("fees_usd", "crypto_usd", "interest_usd", "misc_usd",
                                                            "unreconciled_usd")}
    return out


def closes(positions: Sequence[Mapping[str, Any]], corrections: Mapping[int, Decimal], *, since: float,
           lanes: Lanes | None = None) -> list[dict[str, Any]]:
    """Every real close since `since` (epoch) in close order (closed_at, then pid), routed (`economics.route_of`):
    {pid, family, instance, version, route, code, house, lane, closed_at, day, opened_day, opened_at, root, type, legs,
    entry, opened_qty, max_loss_usd, cash_usd, pnl_usd, fee_basis, priced}. `pnl_usd` is the book's cash plus the
    broker's posted correction (None for a close the book could not price)."""
    from .economics import route_of

    out = []
    for p in positions:
        status, closed_at = str(p.get("status") or ""), _num(p.get("closed_at"))
        if status == "open" or closed_at is None or closed_at < since:
            continue
        route = route_of(p)
        house = route in HOUSE_ROUTES
        pid = int(p["pid"])
        cash = _dec(p.get("cash"))
        priced = status == "closed" and cash is not None and int(p.get("qty") or 0) == 0
        fix = corrections.get(pid)
        pnl = (cash + (fix or Decimal(0))) if priced else None
        opened_qty = int(p.get("opened_qty") or 0)
        loss = (_num(p.get("max_loss_share")) or 0.0) * 100.0 * opened_qty
        out.append({"pid": pid, "family": str(p.get("family") or ""), "instance": str(p.get("instance") or ""),
                    "version": version_of(p.get("instance")), "route": route, "code": ROUTE_CODES.get(route),
                    "house": house, "lane": None if house or lanes is None else lanes.of(p.get("family")),
                    "closed_at": closed_at, "day": _ny_day(closed_at), "opened_day": str(p.get("opened_day") or ""),
                    "opened_at": _num(p.get("opened_at")), "root": str(p.get("root") or "").upper(),
                    "type": str(p.get("type") or ""), "legs": _loads(p.get("legs"), []), "entry": _num(p.get("entry")),
                    "opened_qty": opened_qty, "max_loss_usd": round(loss, 2), "cash_usd": cash, "pnl_usd": pnl,
                    "fee_basis": "broker" if fix is not None else "estimate", "priced": priced, "status": status})
    out.sort(key=lambda c: (c["closed_at"], c["pid"]))
    return out


# ------------------------------------------------------------------------------------------------- buy-and-hold
def _close_on(series: Mapping[str, float], day: str | None) -> float | None:
    """The symbol's close on `day`, else its last close before it (None without one)."""
    if not series or not day:
        return None
    if day in series:
        return _num(series[day])
    before = [d for d in series if d <= day]
    return _num(series[max(before)]) if before else None


def entry_delta(close: Mapping[str, Any], spot: float) -> float | None:
    """The structure's delta per share at entry: Black-Scholes at one implied volatility, solved by bisection so the legs'
    signed values sum to its entry value, the entry day's close as the spot. None when no volatility in [1%, 300%] gives
    the entry value (or a leg is unreadable)."""
    from ..options_history import bs_delta, bs_price, years_to

    entry, at = _num(close.get("entry")), _num(close.get("opened_at"))
    legs = []
    for leg in close.get("legs") or []:
        if not isinstance(leg, Mapping):
            return None
        strike, side, ratio = _num(leg.get("strike")), _num(leg.get("side")), _num(leg.get("ratio"))
        if strike is None or side is None or ratio is None or not leg.get("expiry"):
            return None
        try:
            years = years_to(str(leg["expiry"]), at or 0.0)
        except (TypeError, ValueError):
            return None
        legs.append((strike, side * ratio, years, "call" if leg.get("is_call") else "put"))
    if not legs or entry is None or at is None or spot <= 0 or any(y <= 0 for _, _, y, _ in legs):
        return None

    def value(vol: float) -> float:
        return sum(w * bs_price(spot, k, y, vol, right) for k, w, y, right in legs)

    # A single option's value rises with the volatility; a vertical's need not (it falls again past its peak), so the
    # lowest volatility that prices the entry is taken: the first sign change on a log grid from 1% to 300%, then bisected.
    grid = [0.01 * (300.0 ** (i / 60.0)) for i in range(61)]
    found = None
    f_prev = value(grid[0]) - entry
    for a, b in zip(grid, grid[1:]):
        f_next = value(b) - entry
        if f_prev == 0 or f_prev * f_next < 0:
            found = (a, b, f_prev)
            break
        f_prev = f_next
    if found is None:
        return None
    lo, hi, f_lo = found
    if f_lo == 0:
        hi = lo
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        f_mid = value(mid) - entry
        if (f_mid < 0) == (f_lo < 0):
            lo, f_lo = mid, f_mid
        else:
            hi = mid
        if hi - lo < 1e-6:
            break
    vol = 0.5 * (lo + hi)
    return sum(w * bs_delta(spot, k, y, vol, right) for k, w, y, right in legs)


def buy_and_hold(close: Mapping[str, Any], closes_doc: Mapping[str, Mapping[str, float]]) -> dict[str, Any]:
    """The same-risk buy-and-hold of one close, two ways (the module docstring): {delta_usd, risk_usd, why}."""
    from .direction import PROXY

    root = str(close.get("root") or "").upper()
    symbol = PROXY.get(root, root)
    series = closes_doc.get(symbol) or {}
    start, end = _close_on(series, close.get("opened_day")), _close_on(series, close.get("day"))
    out: dict[str, Any] = {"delta_usd": None, "risk_usd": None, "why": None}
    if start is None or end is None or start <= 0:
        out["why"] = f"no daily close of {symbol or 'its root'} for its days (the direction job's file)"
        return out
    out["risk_usd"] = round(float(close.get("max_loss_usd") or 0.0) * (end / start - 1.0), 2)
    if root in PROXY:
        out["why"] = f"{root} has no stock bars: not delta-matched"
        return out
    delta = entry_delta(close, start)
    if delta is None:
        out["why"] = "no implied volatility gives its entry value: not delta-matched"
        return out
    out["delta_usd"] = round(delta * 100.0 * int(close.get("opened_qty") or 0) * (end - start), 2)
    return out


def _bh_sum(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    rows = list(rows)
    d = [r["bh"]["delta_usd"] for r in rows if (r.get("bh") or {}).get("delta_usd") is not None]
    k = [r["bh"]["risk_usd"] for r in rows if (r.get("bh") or {}).get("risk_usd") is not None]
    return {"delta_matched_usd": round(sum(d), 2) if d else None, "delta_priced": len(d),
            "dollars_at_risk_usd": round(sum(k), 2) if k else None, "risk_priced": len(k), "closes": len(rows),
            "basis": "approximation: daily closes of the direction job; delta from Black-Scholes at one implied "
                     "volatility solved from the entry value, the entry day's close as the spot"}


# ------------------------------------------------------------------------------------------------- the Done meter
def nightly_rows(store: Any, fid: str) -> list[dict[str, Any]]:
    """The family's nightly replay rows of the forward record (`source` "nightly"), [] on a store error."""
    try:
        return [r for r in store.forward(fid) if str(r.get("source") or "") == "nightly"]
    except Exception:  # noqa: BLE001 - no replay rows: no matched closes
        return []


def replay_gap(program_closes: Sequence[Mapping[str, Any]], nightly: Sequence[Mapping[str, Any]], *,
               limit: float, min_matched: int) -> dict[str, Any]:
    """D5's measure, live minus replay, pooled over the program's versions: on every (version, day) on which the program's
    counted closes (by their entry day, as the forward record dates a real trade) and its version's nightly replay both
    traded, sum(live P&L) / sum(live maximum loss) - sum(replay P&L) / sum(replay maximum loss), over the BOOK's cash (as
    D5 reads it). {matched, gap, consistent}: consistent is None under `min_matched` matched closes (listed, never
    dropped), else |gap| <= `limit`."""
    replay: dict[tuple[int, str], list[Mapping[str, Any]]] = {}
    for r in nightly:
        v = r.get("version")
        if v is None:
            continue
        replay.setdefault((int(v), str(r.get("day") or "")), []).append(r)
    live_pnl = live_loss = replay_pnl = replay_loss = 0.0
    matched = 0
    cells: set[tuple[int, str]] = set()
    for c in program_closes:
        key = (c.get("version"), str(c.get("opened_day") or ""))
        if key[0] is None or key not in replay:
            continue
        cash = _num(c.get("cash_usd"))
        loss = _num(c.get("max_loss_usd"))
        if cash is None or loss is None or loss <= 0:
            continue
        matched += 1
        live_pnl += cash
        live_loss += loss
        cells.add(key)  # type: ignore[arg-type]
    for key in cells:
        for r in replay[key]:
            p, m = _num(r.get("pnl")), _num(r.get("max_loss"))
            if p is not None and m is not None and m > 0:
                replay_pnl += p
                replay_loss += m
    gap = (live_pnl / live_loss - replay_pnl / replay_loss) if matched and live_loss > 0 and replay_loss > 0 else None
    consistent = None if matched < min_matched or gap is None else abs(gap) <= limit
    return {"matched": matched, "gap": None if gap is None else round(gap, 4), "consistent": consistent}


def reading(counted: Sequence[Mapping[str, Any]], store: Any, *, nightly_cache: dict[str, list] | None = None,
            done: Mapping[str, Any] | None = None, lanes: Lanes | None = None) -> dict[str, Any]:
    """The Done rule over exactly `counted` (the meter's closes, in close order): {closes, programs, net_usd, net_known,
    estimate_closes, unpriced, per_program_ok, consistent_ok, holds, why, by_route, by_program, bh}."""
    from ..swarm import dlane

    rule = dict(done or dlane.DONE)
    cache = nightly_cache if nightly_cache is not None else {}
    by_program: dict[str, list[Mapping[str, Any]]] = {}
    for c in counted:
        by_program.setdefault(c["family"], []).append(c)
    unpriced = sum(1 for c in counted if c.get("pnl_usd") is None)
    net = sum((c["pnl_usd"] for c in counted if c.get("pnl_usd") is not None), Decimal(0))
    programs = []
    for fid, rows in sorted(by_program.items()):
        if fid not in cache:
            cache[fid] = nightly_rows(store, fid)
        gap = replay_gap(rows, cache[fid], limit=float(rule["gap_limit"]), min_matched=int(rule["gap_min_matched"]))
        routes: dict[str, int] = {}
        for c in rows:
            routes[c.get("code") or c["route"]] = routes.get(c.get("code") or c["route"], 0) + 1
        known = [c["pnl_usd"] for c in rows if c.get("pnl_usd") is not None]
        lane = lanes.of(fid) if lanes is not None else rows[0].get("lane")
        row = {"family": fid, "lane": lane, "closes": len(rows), "routes": routes,
               "net_usd": _usd(sum(known, Decimal(0))) if len(known) == len(rows) else None,
               "replay": gap, "bh": _bh_sum(rows)}
        if lane == dlane.DIRECTION:
            row["label"] = dlane.LABEL
        programs.append(row)
    enough = [p for p in programs if p["closes"] >= int(rule["min_closes_per_program"])]
    per_program_ok = len(enough) >= int(rule["min_programs"])
    inconsistent = [p["family"] for p in programs if p["replay"]["consistent"] is False]
    net_known = unpriced == 0
    whys = []
    if len(counted) < int(rule["min_closes"]):
        whys.append(f"{len(counted)} closes of the {int(rule['min_closes'])} needed")
    if not per_program_ok:
        whys.append(f"{len(enough)} programs with {int(rule['min_closes_per_program'])}+ closes of the "
                    f"{int(rule['min_programs'])} needed")
    if not net_known:
        whys.append(f"{unpriced} closes the book could not price: the net is unknown")
    elif net <= 0:
        whys.append("the net after fees is not above $0")
    if inconsistent:
        whys.append(f"live fills inconsistent with replay: {', '.join(inconsistent[:8])}")
    by_route: dict[str, dict[str, Any]] = {}
    for c in counted:
        key = c.get("code") or c["route"]
        slot = by_route.setdefault(key, {"closes": 0, "programs": set(), "net": Decimal(0), "unpriced": 0})
        slot["closes"] += 1
        slot["programs"].add(c["family"])
        if c.get("pnl_usd") is None:
            slot["unpriced"] += 1
        else:
            slot["net"] += c["pnl_usd"]
    return {"closes": len(counted), "programs": len(programs), "programs_with_min_closes": len(enough),
            "net_usd": _usd(net) if net_known else None, "net_known": net_known, "unpriced": unpriced,
            "estimate_closes": sum(1 for c in counted if c.get("priced") and c.get("fee_basis") == "estimate"),
            "per_program_ok": per_program_ok, "consistent_ok": not inconsistent,
            "holds": not whys, "why": "; ".join(whys) or None,
            "by_route": {k: {"closes": v["closes"], "programs": len(v["programs"]),
                             "net_usd": None if v["unpriced"] else _usd(v["net"]), "unpriced": v["unpriced"]}
                         for k, v in sorted(by_route.items())},
            "by_program": programs, "bh": _bh_sum(counted)}


def meter(all_closes: Sequence[Mapping[str, Any]], routes: Sequence[str], store: Any, *,
          nightly_cache: dict[str, list] | None = None, lanes: Lanes | None = None) -> dict[str, Any]:
    """One Done meter (`done_screen` or `done_all`): the agent closes on `routes`, the running figures (never a reading),
    and a reading at every checkpoint reached (the first K closes, K = 30, 40, ...: `dlane.DONE`)."""
    from ..swarm import dlane

    rule = dlane.DONE
    counted = [c for c in all_closes if not c["house"] and c.get("code") in routes]
    cache = nightly_cache if nightly_cache is not None else {}
    running = reading(counted, store, nightly_cache=cache, lanes=lanes)
    checkpoints = []
    k = int(rule["first_checkpoint"])
    while k <= len(counted):
        at = reading(counted[:k], store, nightly_cache=cache, lanes=lanes)
        checkpoints.append({"at_close": k, "closed_at": _iso(counted[k - 1]["closed_at"]), "holds": at["holds"],
                            "why": at["why"], "closes": at["closes"], "programs": at["programs"],
                            "programs_with_min_closes": at["programs_with_min_closes"], "net_usd": at["net_usd"],
                            "consistent_ok": at["consistent_ok"], "by_route": at["by_route"], "bh": at["bh"]})
        k += int(rule["checkpoint_every"])
    nxt = int(rule["first_checkpoint"]) if not checkpoints else checkpoints[-1]["at_close"] + int(rule["checkpoint_every"])
    return {"routes": list(routes), "running": {**running, "holds": None, "reading": False,
                                                "note": "counts between checkpoints are never a Done reading"},
            "checkpoints": checkpoints, "latest": checkpoints[-1] if checkpoints else None,
            "holds": bool(checkpoints and checkpoints[-1]["holds"]), "next_checkpoint": nxt,
            "closes": [{"pid": c["pid"], "family": c["family"], "route": c.get("code") or c["route"], "lane": c.get("lane"),
                        "closed_at": _iso(c["closed_at"]), "pnl_usd": _usd(c["pnl_usd"]), "fee_basis": c["fee_basis"],
                        "bh": c.get("bh")} for c in counted]}


# ------------------------------------------------------------------------------------------------- the funnel
def funnel(store: Any, lanes: Lanes, all_closes: Sequence[Mapping[str, Any]], *, now: float, hours: float) -> dict[str, Any]:
    """Each lane's counts over the last `hours` (the module docstring), from the swarm store opened read-only."""
    from ..swarm import dlane

    since = _iso(now - hours * 3600.0)
    out: dict[str, Any] = {lane: {"births": 0, "gym_runs": {w: 0 for w in RUN_WINDOWS}, "program_years": 0.0,
                                  "validations": {"judged": 0, "passed": 0}, "reviews": 0, "audits": 0,
                                  "looks": {"taken": 0, "passed": 0, "by_screen": {}},
                                  "band_moves": {"candidate": 0, "probe": 0, "sized": 0},
                                  "real_closes": {":r": 0, ":t": 0, ":i": 0, "other": 0}}
                           for lane in dlane.LANES}
    for row in store._all("SELECT family, payload FROM events WHERE kind='swarm.born' AND at>=?", (since,)):
        payload = _loads(row.get("payload"), {}) or {}
        lane = payload.get("lane") if isinstance(payload, Mapping) else None
        lane = lane if lane in dlane.LANES else lanes.of(row.get("family"))
        out[lane]["births"] += 1
    for row in store._all('SELECT family, "window" AS w, status, trials, program_years FROM runs WHERE at>=?', (since,)):
        if row["status"] in NOT_RUN or not int(row.get("trials") or 0):
            continue
        lane = lanes.of(row["family"])
        if row["w"] in out[lane]["gym_runs"]:
            out[lane]["gym_runs"][row["w"]] += 1
        out[lane]["program_years"] += float(row.get("program_years") or 0.0)
    for row in store._all("SELECT payload FROM events WHERE kind='swarm.tournament' AND at>=?", (since,)):
        judged = ((_loads(row.get("payload"), {}) or {}).get("validation") or {}).get("judged")
        for fid, verdict in (judged or {}).items() if isinstance(judged, Mapping) else ():
            lane = lanes.of(fid)
            out[lane]["validations"]["judged"] += 1
            out[lane]["validations"]["passed"] += 1 if isinstance(verdict, Mapping) and verdict.get("passed") is True else 0
    for row in store._all("SELECT family, payload FROM events WHERE kind='swarm.gate' AND at>=?", (since,)):
        action = (_loads(row.get("payload"), {}) or {}).get("action")
        if action in ("review", "audit") and row.get("family"):
            out[lanes.of(row["family"])]["reviews" if action == "review" else "audits"] += 1
    for row in store._all("SELECT family, passed, detail FROM looks WHERE at>=?", (since,)):
        lane = lanes.of(row["family"])
        detail = _loads(row.get("detail"), {}) or {}
        screen = str(detail.get("screen") or (dlane.ALPHA_SCREEN if lane == dlane.ALPHA else "unrecorded"))
        looks = out[lane]["looks"]
        looks["taken"] += 1
        looks["passed"] += 1 if row.get("passed") else 0
        looks["by_screen"][screen] = looks["by_screen"].get(screen, 0) + 1
    for row in store._all("SELECT family, payload FROM events WHERE kind='swarm.band' AND at>=?", (since,)):
        to = (_loads(row.get("payload"), {}) or {}).get("band_to")
        if to in out[dlane.ALPHA]["band_moves"]:
            out[lanes.of(row.get("family"))]["band_moves"][to] += 1
    edge = now - hours * 3600.0
    for c in all_closes:
        if c["house"] or c["closed_at"] < edge:
            continue
        out[c.get("lane") or dlane.ALPHA]["real_closes"][c.get("code") or "other"] += 1
    for lane in out.values():
        lane["program_years"] = round(lane["program_years"], 2)
    out[dlane.DIRECTION]["train_bar"] = dlane.failure_counts(store, hours, now=now)
    return out


def bands_now(store: Any, lanes: Lanes) -> dict[str, dict[str, int]]:
    from ..swarm import dlane

    out = {lane: {"gym": 0, "candidate": 0, "probe": 0, "sized": 0, "alive": 0} for lane in dlane.LANES}
    for fam in store.families(alive=True):
        lane = lanes.of(fam["id"], fam)
        out[lane][str(fam.get("band") or "gym")] = out[lane].get(str(fam.get("band") or "gym"), 0) + 1
        out[lane]["alive"] += 1
    return out


# ------------------------------------------------------------------------------------------------- Probes and screens
def probes(store: Any, lanes: Lanes, settings: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    """Every living Candidate, Probe or Sized family with the screen that admitted it (its banded version's newest
    passing look: the screen the look recorded, else its lane's) and that screen's false-positive rates, the
    world-conditional one (both windows rose) beside the unconditional one (decision 8)."""
    from ..swarm import dlane

    c = dlane.cfg(settings)
    looks: dict[tuple[str, int], Mapping[str, Any]] = {}
    for look in store.looks():
        if look.get("passed"):
            looks[(str(look["family"]), int(look["version"]))] = look
    out = []
    for fam in store.families(alive=True):
        if fam.get("band") not in ("candidate", "probe", "sized"):
            continue
        lane = lanes.of(fam["id"], fam)
        n = (fam.get("state") or {}).get("banded_version")
        look = looks.get((fam["id"], int(n))) if isinstance(n, int) else None
        detail = (look or {}).get("detail") or {}
        screen = detail.get("screen") or (dlane.ALPHA_SCREEN if lane == dlane.ALPHA else c["screen"])
        figures = c["screens"].get(screen) or {}
        row = {"family": fam["id"], "band": fam["band"], "lane": lane, "version": n, "look_at": (look or {}).get("at"),
               "screen": screen, "receipt": detail.get("receipt"), "screen_recorded": bool(detail.get("screen")),
               "fp_unconditional": figures.get("fp_unconditional"),
               "fp_both_windows_rose": figures.get("fp_both_windows_rose")}
        if look is not None:  # release D-1b: the lane rates of the screen that admitted it (`dlane.fp_of_look`)
            row.update({k: v for k, v in dlane.fp_of_look(detail, settings).items() if k.startswith("fp_")})
        if screen == dlane.ALPHA_SCREEN:
            row["fp_why"] = "the alpha screen's (S-B) rates are FAST_LANE_SCREEN_1's receipt (docs/benchmarks), not the lane's"
            row.update(ALPHA_FP)
        if lane == dlane.DIRECTION:
            row["label"] = dlane.LABEL
        out.append(row)
    return out


#: The alpha screen's (S-B) false-positive figure, stated beside an alpha program's Probe trade (release D-1b): it has no
#: lane rate; its pre-registered benchmark's acceptance bound held (FAST_LANE_SCREEN_1, Oct 7, 2026).
ALPHA_FP = {"fp_upper_bound": 0.02,
            "fp_source": "FAST_LANE_SCREEN_1 (docs/benchmarks/fast_lane_screen_1.json): the per-program rate's one-sided 95% "
                         "upper bound at most 2% in every null world"}


def trade_screens(store: Any, lanes: Lanes, settings: Mapping[str, Any] | None, positions: Sequence[Mapping[str, Any]],
                  all_closes: Sequence[Mapping[str, Any]], *, since: float) -> dict[str, Any]:
    """THE FALSE-POSITIVE RATE BESIDE EVERY PROBE TRADE AND EVERY REAL CLOSE (release D-1b; the owner's goal of Oct 9,
    item 4: "a pre-registered screen whose false-positive rate you have measured ... stated beside every Probe trade").
    `probe_trades`: every real position on the Probe/Sized route `:r` opened since `since`, open or closed; `closes`:
    every agent real close (every route, the Done rule's set), each with its program's screen (the passed holdout look of
    the version the position trades: its recorded line) and that screen's rates at zero edge, {screen, fp_lane_mixed,
    fp_lane_2224, receipt} (`dlane.fp_of_look`), the alpha screen's bound beside an S-B row (`ALPHA_FP`), the lane's
    label beside a direction row. Only a Probe/Sized trade (`d2_real`) opened at or after its version's passed look carries
    that look's screen (the review's finding 5): a tuition or incubator close, a close with no passed look on record, and
    a position opened before the look say so (`fp_why`), never an invented screen. The contamination statement rides
    beside them."""
    from ..swarm import dlane
    from .economics import route_of

    passed: dict[tuple[str, int], Mapping[str, Any]] = {}
    for look in store.looks():
        if look.get("passed"):
            passed[(str(look["family"]), int(look["version"]))] = look

    def screen_of(family: str, version: int | None, route: str, opened_at: float | None) -> dict[str, Any]:
        # A SCREEN ADMITS A PROBE TRADE ONLY (release D-1b, the review's finding 5, Oct 9, 2026): a passed look's screen is
        # stated beside a close or a position only when it is on the Probe/Sized route (`d2_real`, `:r`) and opened at
        # or after that look. A tuition or incubator close of a version that LATER passed its look was admitted by no
        # screen (tuition runs while a validated version waits in the gate), so it keeps the no-screen row.
        look = passed.get((family, int(version))) if isinstance(version, int) else None
        lane = lanes.of(family)
        look_at = _epoch(look.get("at")) if look is not None else None
        why = None
        if route != "d2_real":
            why = (f"the {route} route: no screen admits it (tuition and the incubator trade beside the gate, never by "
                   "its look)")
        elif look is None:
            why = "no passed holdout look of this version is on record"
        elif opened_at is None or look_at is None or look_at > opened_at:
            why = "its version's passed holdout look is not on record before this position opened"
        if why is not None or look is None:
            out = {"screen": None, "fp_lane_mixed": None, "fp_lane_2224": None, "receipt": None, "look_at": None,
                   "fp_why": why}
        else:
            detail = look.get("detail") or {}
            out = {**dlane.fp_of_look(detail, settings), "look_at": look.get("at"),
                   "screen_recorded": bool(detail.get("screen"))}
            if out["screen"] == dlane.ALPHA_SCREEN:
                out.update(ALPHA_FP)
        out["lane"] = lane
        if lane == dlane.DIRECTION:
            out["label"] = dlane.LABEL
        return out

    probe_trades = []
    for p in positions:
        opened = _num(p.get("opened_at"))
        if route_of(p) != "d2_real" or opened is None or opened < since:
            continue
        family, version = str(p.get("family") or ""), version_of(p.get("instance"))
        probe_trades.append({"pid": int(p["pid"]), "family": family, "instance": str(p.get("instance") or ""),
                             "version": version, "status": str(p.get("status") or ""), "opened_at": _iso(opened),
                             "closed_at": _iso(_num(p.get("closed_at"))), "root": str(p.get("root") or "").upper(),
                             "type": str(p.get("type") or ""), **screen_of(family, version, "d2_real", opened)})
    closes_rows = [{"pid": c["pid"], "family": c["family"], "route": c.get("code") or c["route"], "version": c["version"],
                    "closed_at": _iso(c["closed_at"]), "pnl_usd": _usd(c["pnl_usd"]), "fee_basis": c["fee_basis"],
                    **screen_of(c["family"], c["version"], str(c["route"]), _num(c.get("opened_at")))}
                   for c in all_closes if not c["house"]]
    return {"probe_trades": probe_trades, "closes": closes_rows, "contamination": CONTAMINATION,
            "note": "each row's rates are its screen's per program at zero edge, measured on historical worlds (a property "
                    "of the procedure, not a guarantee in this world); reported, never a bar"}


# ------------------------------------------------------------------------------------------------- the envelope
def probe_envelope(live_path: Path, positions: Sequence[Mapping[str, Any]], *, today: str, unit_usd: float | None
                   ) -> dict[str, Any]:
    """THE PROBE LOSS BUDGET as the money table in force reads it (release L-D, live since 09:04Z Oct 9, 2026; THE ROLLING
    PROBE BUDGET): the constitution's `options_money.probe` row through `money.Table` (`constitution`: `loss_basis`,
    `loss_budget_usd` over the last `loss_window_sessions` New York sessions, `loss_total_usd` from inception, `max_open`,
    `demotion`), never a figure of its own, and the realized figures `real.probe_figures` gives `money.plan_open` (through
    `RealBook.exposure`), each read in one read-only transaction of the live book with the basis named:
    - `in_force`: the fast lane report's own figure (`fast_lane.probe_budget`: the basis in force, the window's and the
      total's figures, `room_usd` and the envelope that binds);
    - `by_basis`: under each basis ("gross" and "net"; `basis_in_force` is the table's, the other rides beside it), the
      window's figure (`window_usd`: `real.probe_realized` from `window_start`, under "net" the window's WORST NET
      STRETCH), the total's (`total_usd`: `real.probe_tally`, from inception), both rooms (`fast_lane.probe_rooms`: each
      envelope's budget less its figure less every real position's open maximum loss), the room left (the tighter
      envelope's, floored at $0), which envelope binds, and that room in units of today's cap;
    - `window_<basis>_usd`, `realized_<basis>_usd` (the total, from inception, as before release L-D's window),
      `room_<basis>_usd` and `room_<basis>_units` repeat each basis's figures (alarm A4 reads the basis in force).
    `probe_closes` counts the closed Probe-marked `:r` positions. A book that is absent leaves every figure None; one
    that cannot be read (the House box has numpy; a test or a laptop may not) is an `error` entry."""
    from dataclasses import replace

    from ..live import money as M

    table = M.Table.from_constitution()
    marked = sum(1 for p in positions
                 if p.get("status") == "closed" and str(p.get("instance") or "").endswith(":r")
                 and not int(p.get("tuition") or 0) and (_loads(p.get("info"), {}) or {}).get("probe") is True)
    out: dict[str, Any] = {
        "constitution": {"loss_basis": table.probe_loss_basis, "loss_budget_usd": _usd(table.probe_loss_budget),
                         "loss_window_sessions": table.probe_loss_window, "loss_total_usd": _usd(table.probe_loss_total),
                         "max_open": table.probe_max_open, "demotion": table.probe_demotion},
        "basis_in_force": table.probe_loss_basis, "budget_usd": _usd(table.probe_loss_budget),
        "window_sessions": table.probe_loss_window, "total_budget_usd": _usd(table.probe_loss_total),
        "max_open": table.probe_max_open, "probe_closes": marked, "unit_usd": unit_usd, "in_force": None,
        "window_start": None, "at_risk_usd": None, "open": None, "binding": None, "by_basis": None}
    for basis in M.LOSS_BASES:
        for key in ("window", "realized", "room"):
            out[f"{key}_{basis}_usd"] = None
        out[f"room_{basis}_units"] = None
    path = Path(live_path)
    if not path.exists():
        return out
    try:
        from . import fast_lane

        out["in_force"] = fast_lane.probe_budget(path, today)
    except Exception as exc:  # noqa: BLE001 - the House box has numpy; a test or a laptop may not
        out["in_force"] = {"error": f"{type(exc).__name__}: {str(exc)[:160]}"}
    try:
        from ..live.real import probe_figures
        from . import guard

        def read(db: Any) -> dict[str, tuple]:
            def rows(sql: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
                return guard.rows(db, sql, params)

            # The table in force with each basis in turn: the code path `RealBook.exposure` takes, the basis named.
            return {basis: probe_figures(rows, day=today, table=replace(table, probe_loss_basis=basis))
                    for basis in M.LOSS_BASES}

        figures = guard.read(path, read)
    except Exception as exc:  # noqa: BLE001 - as above: no figure, never an invented one
        out["error"] = f"{type(exc).__name__}: {str(exc)[:160]}"
        return out
    from .fast_lane import probe_rooms

    by_basis: dict[str, Any] = {}
    for basis, (open_n, window, total, at_risk, since) in figures.items():
        rooms, binding = probe_rooms(table, window, total, at_risk)
        room = max(M.ZERO, rooms[binding])
        units = round(float(room) / unit_usd, 2) if unit_usd else None
        by_basis[basis] = {"window_usd": _usd(window), "total_usd": _usd(total), "room_window_usd": _usd(rooms["window"]),
                           "room_total_usd": _usd(rooms["total"]), "room_usd": _usd(room), "binding": binding,
                           "room_units": units}
        out[f"window_{basis}_usd"], out[f"realized_{basis}_usd"] = _usd(window), _usd(total)
        out[f"room_{basis}_usd"], out[f"room_{basis}_units"] = _usd(room), units
    open_n, _, _, at_risk, since = figures[table.probe_loss_basis]
    out.update(by_basis=by_basis, window_start=since, at_risk_usd=_usd(at_risk), open=open_n,
               binding=by_basis[table.probe_loss_basis]["binding"])
    return out


# ------------------------------------------------------------------------------------------------- the account
def _health(root: Path) -> dict[str, Any]:
    try:
        doc = json.loads((root / HEALTH_FILE).read_text(encoding="utf-8"))
        stops = ((doc.get("options_live") or {}).get("stops") or {}) if isinstance(doc, Mapping) else {}
    except (OSError, ValueError, TypeError, AttributeError):
        return {}
    last = stops.get("last_reading") if isinstance(stops, Mapping) else None
    out: dict[str, Any] = {"sod_equity_usd": _num(stops.get("sod_equity")) if isinstance(stops, Mapping) else None}
    if isinstance(last, (list, tuple)) and len(last) >= 2:
        out["equity_usd"], out["equity_at"] = _num(last[1]), _iso(_num(last[0]))
    return out


def account(root: Path, all_closes: Sequence[Mapping[str, Any]], activity: Mapping[str, Any],
            previous: Mapping[str, Any] | None, *, now: float) -> dict[str, Any]:
    """The account beside the trading figures (the module docstring)."""
    health = _health(root)
    equity, at = health.get("equity_usd"), health.get("equity_at")
    e0 = ((previous or {}).get("account") or {}).get("e0") if isinstance(previous, Mapping) else None
    if not (isinstance(e0, Mapping) and _num(e0.get("usd")) is not None and e0.get("at")):
        e0 = {"usd": equity, "at": at or _iso(now),
              "basis": "the first equity reading the dlane report saw (release L-D's deploy reading is the plan's E0)"}
    out: dict[str, Any] = {"e0": e0, "equity_usd": equity, "equity_at": at, "sod_equity_usd": health.get("sod_equity_usd"),
                           "change_usd": None, "agents_usd": None, "house_usd": None, "other_activity": activity.get("other"),
                           "other_as_of": activity.get("as_of"), "unexplained_usd": None}
    start = _epoch(e0.get("at"))
    if equity is None or _num(e0.get("usd")) is None or start is None:
        out["why"] = "no equity reading in health.json"
        return out
    out["change_usd"] = round(equity - float(e0["usd"]), 2)
    since = [c for c in all_closes if c["closed_at"] >= start]
    agents = [c["pnl_usd"] for c in since if not c["house"]]
    house = [c["pnl_usd"] for c in since if c["house"]]
    if all(x is not None for x in agents):
        out["agents_usd"] = _usd(sum(agents, Decimal(0)))
    if all(x is not None for x in house):
        out["house_usd"] = _usd(sum(house, Decimal(0)))
    if out["agents_usd"] is not None and out["house_usd"] is not None:
        out["unexplained_usd"] = round(out["change_usd"] - out["agents_usd"] - out["house_usd"], 2)
    out["note"] = ("unexplained = the equity change less the realized closes since E0: open positions' marks, fees no "
                   "position carries, interest and anything else the account holds")
    return out


def costs(store: Any, *, since: float, lane_since: float | None) -> dict[str, Any]:
    """The swarm's research spend by meter (`funnel.METER_KINDS`) since `since` and since the lane started."""
    from .funnel import METER_KINDS

    def spent(start: float | None) -> dict[str, float] | None:
        if start is None:
            return None
        meters = {m: 0.0 for m in METER_KINDS}
        for row in store._all("SELECT kind, coalesce(sum(usd), 0) AS usd FROM spend WHERE epoch>=? GROUP BY kind", (start,)):
            for m, kinds in METER_KINDS.items():
                if row["kind"] in kinds:
                    meters[m] += float(row["usd"] or 0.0)
        return {**{m: round(v, 2) for m, v in meters.items()}, "total": round(sum(meters.values()), 2)}

    return {"since_inception": spent(since), "since_lane_start": spent(lane_since),
            "note": "LTCM's profit is trading net minus these costs; the gateway's own spend is the gateway's meter, not "
                    "read here"}


# ------------------------------------------------------------------------------------------------- contamination
def contamination_meters(root: Path, lanes: Lanes) -> dict[str, Any]:
    """M-D (a)-(c) per lane, from the fast lane report (`fast-lane-report.json`, written daily at 01:00Z after the
    `direction` job): its looks' head-minus-tail Sharpe gaps pooled per lane, the excess over the same-risk buy-and-hold
    on Validation (a known window) against live (unknown), and each band's live against its holdout."""
    from ..swarm import dlane
    from .fast_lane import pooled_contamination

    try:
        doc = json.loads((root / FAST_LANE_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"why": "no fast lane report yet"}
    screen = doc.get("screen") or []
    bands = doc.get("bands") or []
    out: dict[str, Any] = {"fast_lane_report_at": doc.get("at"), "reported_only": True}
    for lane in dlane.LANES:
        rows = [r for r in screen if lanes.of(r.get("family")) == lane]
        known = [float(r["pnl"]) - float(r["bh"]["usd"]) for r in rows
                 if r.get("window") == "validation" and _num(r.get("pnl")) is not None
                 and _num((r.get("bh") or {}).get("usd")) is not None]
        live = [float(b["live"]["realized_usd"]) - float(b["live"]["bh"]["usd"]) for b in bands
                if lanes.of(b.get("family")) == lane and _num(((b.get("live") or {}).get("bh") or {}).get("usd")) is not None
                and _num((b.get("live") or {}).get("realized_usd")) is not None]
        excess_known = statistics.fmean(known) if known else None
        excess_live = statistics.fmean(live) if live else None
        out[lane] = {
            "a_head_minus_tail": pooled_contamination(rows),
            "b_excess_over_bh": {"known_validation_mean_usd": None if excess_known is None else round(excess_known, 2),
                                 "known_n": len(known),
                                 "unknown_live_mean_usd": None if excess_live is None else round(excess_live, 2),
                                 "unknown_n": len(live),
                                 "known_minus_unknown_usd": (round(excess_known - excess_live, 2)
                                                             if excess_known is not None and excess_live is not None
                                                             else None)},
            "c_live_vs_holdout": [{"family": b.get("family"), "band": b.get("band"), **(b.get("live_vs_holdout") or {})}
                                  for b in bands if lanes.of(b.get("family")) == lane]}
        if lane == dlane.DIRECTION:
            out[lane]["label"] = dlane.LABEL
    return out


# ------------------------------------------------------------------------------------------------- the alarms
def _sessions_back(today: str, n: int) -> str:
    """The NYSE session `n` sessions before `today` (ISO), counting `today` when it is one."""
    from .direction import sessions

    first = (datetime.fromisoformat(today) - timedelta(days=3 * n + 10)).date().isoformat()
    days = sessions(first, today)
    return days[-n] if len(days) >= n else first


def alarms(store: Any, settings: Mapping[str, Any] | None, lanes: Lanes, book: Mapping[str, Any],
           all_closes: Sequence[Mapping[str, Any]], envelope: Mapping[str, Any], done: Mapping[str, Any],
           k5: Mapping[str, Any], unit: Mapping[str, Any], previous: Mapping[str, Any] | None, *, now: float,
           today: str) -> list[dict[str, Any]]:
    """A1-A9 and K5 (HARNESS section 5 as amended; the module docstring): [{id, level, text, ...}]. Each names counts and
    family ids, never a hidden-year figure."""
    from ..live import money as M
    from ..swarm import dlane

    c = dlane.cfg(settings)
    out: list[dict[str, Any]] = []
    alive = [f for f in store.families(alive=True) if lanes.of(f["id"], f) == dlane.DIRECTION]
    # A1: no direction birth in `lane_only_hours`, the quota open (the lane on and under `max_alive`).
    edge = _iso(now - c["lane_only_hours"] * 3600.0)
    started = store.get(dlane.STARTED_KEY)
    births = [r for r in store._all("SELECT family, at, payload FROM events WHERE kind='swarm.born' ORDER BY at, seq")
              if ((_loads(r.get("payload"), {}) or {}).get("lane") == dlane.DIRECTION
                  or lanes.of(r.get("family")) == dlane.DIRECTION)]
    last = births[-1]["at"] if births else None
    if (dlane.mode_effective(store, settings) != "off" and isinstance(started, str) and started <= edge
            and (last is None or last <= edge) and len(alive) < c["max_alive"]):
        out.append({"id": "A1", "level": "warning", "last_birth": last,
                    "text": f"A1: no direction birth in {c['lane_only_hours']:g} h with the quota open "
                            f"({len(alive)} direction families alive of {c['max_alive']}): the architect's next pass asks "
                            "for direction proposals only (lane_only)"})
    counts48 = dlane.failure_counts(store, 48.0, now=now)
    # A2: a direction version cleared every Train bar 24 h ago or more, and no direction Validation try or look since.
    cleared = []
    for fam in alive:
        versions = (((fam.get("state") or {}).get(dlane.STATE_KEY) or {}).get("versions") or {})
        for n, v in versions.items() if isinstance(versions, Mapping) else ():
            if ((v or {}).get("robust") or {}).get("passed") and ((v or {}).get("train") or {}).get("eligible"):
                cleared.append((fam, int(n), str(v.get("at") or "")))
    day_ago = _iso(now - A2_HOURS * 3600.0)
    if cleared and min(at for _, _, at in cleared) <= day_ago:
        ids = {f["id"] for f, _, _ in cleared}
        tries = sum(1 for r in store._all("SELECT family FROM runs WHERE \"window\"='validation' AND purpose='validation' "
                                          "AND at>=?", (day_ago,)) if r["family"] in {f["id"] for f in alive})
        looks = sum(1 for r in store._all("SELECT family FROM looks WHERE at>=?", (day_ago,))
                    if lanes.of(r["family"]) == dlane.DIRECTION)
        if not tries and not looks:
            out.append({"id": "A2", "level": "warning", "families": sorted(ids)[:12],
                        "text": f"A2: {len(cleared)} direction versions in {len(ids)} families cleared every Train bar "
                                f"24 h ago or more, and no direction Validation try or holdout look since (plumbing; "
                                f"48 h: {counts48['eligible']} eligible, {counts48['robust_passed']} passed at 1.5x)"})
    # A3: a cleared best waits for Validation over 6 h; a direction Validation pass waits for its look over 12 h.
    waits_val, waits_gate = [], []
    looked = {(str(r["family"]), int(r["version"])) for r in store.looks()}
    for fam, n, at in cleared:
        if fam.get("best_version") != n or fam.get("band") != "gym" or at > _iso(now - A3_VALIDATION_HOURS * 3600.0):
            continue
        if not [r for r in store.version_runs(fam["id"], n, window="validation", stress=1.0, limit=5)]:
            waits_val.append(fam["id"])
    for fam in alive:
        verdicts = (fam.get("state") or {}).get("validation_verdicts") or {}
        for n, v in verdicts.items() if isinstance(verdicts, Mapping) else ():
            if (isinstance(v, Mapping) and v.get("passed") is True and fam.get("band") == "gym"
                    and str(v.get("at") or "9") <= _iso(now - A3_GATE_HOURS * 3600.0)
                    and str(n).isdigit() and (fam["id"], int(n)) not in looked):
                waits_gate.append(fam["id"])
    if waits_val or waits_gate:
        out.append({"id": "A3", "level": "warning", "validation": sorted(set(waits_val))[:12],
                    "gate": sorted(set(waits_gate))[:12],
                    "text": f"A3: {len(set(waits_val))} direction bests wait for Validation over "
                            f"{A3_VALIDATION_HOURS:g} h and {len(set(waits_gate))} direction Validation passes wait for "
                            f"their holdout look over {A3_GATE_HOURS:g} h (a stall)"})
    # A4: room under one unit while a direction Candidate or Probe has fewer than 5 real closes.
    real_n: dict[str, int] = {}
    for cl in all_closes:
        if cl.get("code") == ":r":
            real_n[cl["family"]] = real_n.get(cl["family"], 0) + 1
    young = sorted(f["id"] for f in alive if f.get("band") in ("candidate", "probe") and real_n.get(f["id"], 0) < 5)
    # The room is the tighter of release L-D's two envelopes under the basis in force (`probe_envelope`: the
    # constitution's `loss_budget_usd` over `loss_window_sessions` sessions and `loss_total_usd` in total, `loss_basis`).
    basis = str(envelope.get("basis_in_force") or "gross")
    units = envelope.get(f"room_{basis}_units")
    if young and units is not None and units < 1:
        binding = ((envelope.get("by_basis") or {}).get(basis) or {}).get("binding")
        which = {"window": (f"the window's: ${_num(envelope.get('budget_usd')) or 0:,.2f} in any "
                            f"{envelope.get('window_sessions')} sessions binds"),
                 "total": f"the total's: ${_num(envelope.get('total_budget_usd')) or 0:,.2f} in total binds"}.get(binding)
        out.append({"id": "A4", "level": "warning", "families": young[:12], "basis": basis, "binding": binding,
                    "text": f"A4: the Probe loss budget has under one unit of room ({basis} basis"
                            + (f"; {which}" if which else "") + f") while {len(young)} direction Candidates or "
                            "Probes have fewer than 5 real closes: no path to Sized (a Probe gain, or under the "
                            "window a loss leaving its sessions, frees room)"})
    # A5: a direction Probe or Sized program's live fills below its replay by more than 0.10 over 5+ matched closes.
    table = M.Table.from_constitution()
    gaps = []
    for fam in alive:
        n = (fam.get("state") or {}).get("banded_version")
        if fam.get("band") not in ("probe", "sized") or n is None:
            continue
        try:
            fwd = M.forward_stats(store.forward(fam["id"]), table.sized_confidence, version=n)
        except Exception:  # noqa: BLE001 - an unreadable record: no figure, no alarm
            continue
        if fwd.replay_n >= M.REPLAY_GAP_MIN_TRADES and fwd.replay_gap is not None and fwd.replay_gap > dlane.DONE["gap_limit"]:
            gaps.append(fam["id"])
    if gaps:
        # The demotion in force is the constitution's `probe.demotion` (release L-D): D5's replay-gap leg demotes a
        # Candidate or a Probe under "dm0" and "dm1" alike, never a Sized family.
        out.append({"id": "A5", "level": "warning", "families": gaps[:12], "demotion": table.probe_demotion,
                    "text": f"A5: {len(gaps)} direction Probe or Sized programs' live fills run more than "
                            f"{dlane.DONE['gap_limit']:g} a dollar of maximum loss below their replay over "
                            f"{M.REPLAY_GAP_MIN_TRADES}+ matched closes (D5's replay-gap leg demotes a Probe at "
                            f"{M.REPLAY_GAP_BOUND:g} under probe.demotion \"{table.probe_demotion}\")"})
    # A6: under 1 eligible direction version per 50 direction births over 48 h (judged from 50 births).
    born48 = sum(1 for r in births if str(r.get("at") or "") >= _iso(now - A6_HOURS * 3600.0))
    if born48 >= A6_BIRTHS and counts48["eligible"] * A6_BIRTHS < born48:
        out.append({"id": "A6", "level": "warning", "fails": counts48["fails"], "robust": counts48["robust"],
                    "text": f"A6: {counts48['eligible']} eligible direction versions from {born48} direction births in "
                            f"48 h, under 1 per {A6_BIRTHS} (the lane's objective looks unreachable; failure counts E1 "
                            f"{counts48['fails']['E1']}, E3 {counts48['fails']['E3']}, E4 {counts48['fails']['E4']}, E5 "
                            f"{counts48['fails']['E5']}). Never a loosening without a new pinned measurement"})
    # A7: more than half of the versions that clear E1, E3 and E4 fail E5 (the unit).
    unit_only, eligible = counts48["unit_only"], counts48["eligible"]
    if unit_only and unit_only * 2 > unit_only + eligible:
        failing = []
        for fam in alive:
            for v in ((((fam.get("state") or {}).get(dlane.STATE_KEY) or {}).get("versions") or {}).values()):
                train = (v or {}).get("train") or {}
                if train.get("fails") == ["E5"] and _num((train.get("unit") or {}).get("scaled_usd")) is not None:
                    failing.append(float(train["unit"]["scaled_usd"]))
        median = statistics.median(failing) if failing else None
        out.append({"id": "A7", "level": "warning", "cap_usd": unit.get("cap_usd"), "median_failing_usd": median,
                    "text": f"A7: {unit_only} of {unit_only + eligible} direction versions that clear E1, E3 and E4 fail "
                            f"the unit (E5): today's cap is "
                            f"{'unknown' if unit.get('cap_usd') is None else '$' + format(unit['cap_usd'], '.2f')}"
                            + (f", the median failing one lot ${median:.2f}" if median is not None else "")})
    # A8: a checkpoint holds that no earlier report saw (info; it stops nothing).
    seen = set()
    for meter_name in ("all", "screen"):
        for cp in (((previous or {}).get("done") or {}).get(meter_name) or {}).get("checkpoints") or []:
            if cp.get("holds"):
                seen.add((meter_name, cp.get("at_close")))
    for meter_name in ("all", "screen"):
        for cp in done[meter_name]["checkpoints"]:
            if cp["holds"] and (meter_name, cp["at_close"]) not in seen:
                out.append({"id": "A8", "level": "info", "meter": f"done_{meter_name}", "at_close": cp["at_close"],
                            "text": f"A8: Done criteria hold for done_{meter_name} at the checkpoint of close "
                                    f"{cp['at_close']} (read beside the same-risk buy-and-hold and P(Done | zero edge); "
                                    "it stops nothing)"})
    # A9: every live direction program opened nothing for 10 sessions.
    since_day = _sessions_back(today, A9_SESSIONS)
    live_programs = {i["family"] for i in book.get("instances") or []
                     if not i.get("retired_at") and str(i.get("id") or "").endswith((":r", ":t", ":i"))
                     and lanes.of(i["family"]) == dlane.DIRECTION and (_ny_day(_num(i.get("created_at"))) or "9") <= since_day}
    if live_programs:
        recent = {p["family"] for p in book.get("positions") or [] if str(p.get("opened_day") or "") >= since_day}
        if not live_programs & recent:
            out.append({"id": "A9", "level": "info", "families": sorted(live_programs)[:12],
                        "text": f"A9: every live direction program ({len(live_programs)}) has opened nothing for "
                                f"{A9_SESSIONS} sessions: the lane is flat by design"})
    # K5.
    if k5.get("tripped"):
        out.append({"id": "K5", "level": "warning", "new": bool(k5.get("new")),
                    "text": "K5 tripped: the direction lane's realized net over every route is at or below its line; "
                            "the lane reads shadow (no new direction Candidate, no incubator direction mark) until the "
                            "operator clears it (swarm.json dlane.k5_clear, or the kv dlane_k5)"})
    elif k5.get("cleared"):
        # THE CLEAR'S LOOSENING (the review of Oct 9): while `dlane.k5_clear` is true K5 can neither hold nor trip.
        line = _num(k5.get("line"))
        out.append({"id": "K5", "level": "warning", "new": False, "disarmed": True,
                    "text": "K5 is disarmed: dlane.k5_clear is true in swarm.json, so no loss trips it; "
                            + ("the clear is recorded (the next line is "
                               + ("unknown" if line is None else f"${line:,.2f}") + "): take dlane.k5_clear out"
                               if not k5.get("set") and not k5.get("trip_open") else
                               "the dlane job records the clear on its next run; then take dlane.k5_clear out")})
    return out


# ------------------------------------------------------------------------------------------------- the report
def report(root: str | Path, *, settings: Mapping[str, Any] | None = None, now: float | None = None,
           previous: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """The report (the module docstring), from the state root `root`: the swarm store opened read-only, the live book
    read-only, the closes, health and publish files. `settings` the swarm's (`settings.load(root)` when None). No write."""
    from ..swarm import dlane
    from ..swarm import settings as settings_mod
    from ..swarm.store import SwarmStore
    from . import direction as DIR

    root = Path(root)
    settings = settings if settings is not None else settings_mod.load(root)
    now = time.time() if now is None else float(now)
    today = _ny_day(now) or time.strftime("%Y-%m-%d", time.gmtime(now))
    start = inception()
    activity = fee_corrections(root)
    book = read_book(root / LIVE_DB)
    closes_doc = DIR.load_closes(root / DIR.FILE)
    unit = dlane.unit_context(root, settings)
    store = SwarmStore(root, readonly=True)
    try:
        lanes = Lanes(store)
        every = closes(book["positions"], activity["by_pid"], since=start, lanes=lanes)
        for c in every:
            if not c["house"]:
                c["bh"] = buy_and_hold(c, closes_doc)
        cache: dict[str, list] = {}
        done = {"all": meter(every, dlane.DONE["routes_all"], store, nightly_cache=cache, lanes=lanes),
                "screen": meter(every, dlane.DONE["routes_screen"], store, nightly_cache=cache, lanes=lanes)}
        other = [c for c in every if not c["house"] and c.get("code") is None]
        direction = [c for c in every if not c["house"] and c.get("lane") == dlane.DIRECTION and c.get("code")]
        known = [c["pnl_usd"] for c in direction if c.get("pnl_usd") is not None]
        lane_net = {"closes": len(direction), "net_usd": _usd(sum(known, Decimal(0))), "unpriced": len(direction) - len(known),
                    "by_route": {code: _usd(sum((c["pnl_usd"] for c in direction if c["code"] == code and c["pnl_usd"]
                                                 is not None), Decimal(0))) for code in dlane.DONE["routes_all"]},
                    "bh": _bh_sum(direction), "label": dlane.LABEL, "k5_line_usd": dlane.k5_line(store, settings)}
        envelope = probe_envelope(root / LIVE_DB, book["positions"], today=today, unit_usd=unit.get("cap_usd"))
        k5 = dlane.k5_state(store, settings)
        started = store.get(dlane.STARTED_KEY)
        out: dict[str, Any] = {
            "schema": SCHEMA, "at": _iso(now), "day": today, "operator_only": True, "reported_only": True,
            "label": dlane.LABEL,
            "rule": {"sha256": dlane.DONE["rule_sha256"], **{k: (list(v) if isinstance(v, tuple) else v)
                                                              for k, v in dlane.DONE.items() if k != "rule_sha256"}},
            "lane": {"mode": dlane.cfg(settings)["mode"], "mode_effective": dlane.mode_effective(store, settings),
                     "started_at": started if isinstance(started, str) else None,
                     "screen": dlane.screen_effective(settings), "always_in_note": dlane.ALWAYS_IN_NOTE},
            "loosened": [dict(r) for r in LOOSENED], "tightened": list(TIGHTENED),
            "contamination": {"statement": CONTAMINATION, "meters": contamination_meters(root, lanes)},
            "funnel": {name: funnel(store, lanes, every, now=now, hours=hours) for name, hours in WINDOWS.items()},
            "bands_now": bands_now(store, lanes),
            "probe_envelope": envelope, "unit": {k: unit.get(k) for k in ("known", "cap_usd", "equity_usd", "closes",
                                                                          "close_day", "why")},
            "done": {**done, "p_done_zero_edge": {"value": dlane.cfg(settings)["done_zero_edge_p"], "label": ZERO_EDGE_LABEL},
                     "other_routes": [{"pid": c["pid"], "family": c["family"], "instance": c["instance"],
                                       "route": c["route"], "pnl_usd": _usd(c["pnl_usd"])} for c in other],
                     "inception": dlane.DONE["inception"],
                     "fees": {"as_of": activity["as_of"], "why": activity["why"]}},
            "probes": probes(store, lanes, settings),
            "fp_beside_trades": trade_screens(store, lanes, settings, book["positions"], every, since=start),
            "direction_net": lane_net,
            "account": account(root, every, activity, previous, now=now),
            "costs": costs(store, since=start, lane_since=_epoch(started) if isinstance(started, str) else None),
            "k5": dict(k5),
        }
        out["alarms"] = alarms(store, settings, lanes, book, every, envelope, done, k5, unit, previous, now=now,
                               today=today)
    finally:
        store.close()
    return out


# ------------------------------------------------------------------------------------------------- the job
def run(ctx: Any) -> dict[str, Any]:
    """The job: the report written atomically to `<state>/dlane-report.json`, read-only on every store; then K5's writes
    (the operator's clear recorded, `dlane.k5_rearm`, then the trip when its line is crossed, `dlane.k5_trip`), each only
    when due; then each alarm a House alert (warning, or info for A8 and A9)."""
    from ..swarm import dlane
    from ..swarm import settings as settings_mod
    from ..swarm.store import SwarmStore
    from . import guard
    from .context import read_json, write_json

    root = Path(ctx.root)
    settings = settings_mod.load(root, config=getattr(ctx, "config", None))
    if not dlane.on(settings):
        return {"status": "skipped", "why": "the direction lane is off (dlane.mode): nothing to report"}
    previous = read_json(root / FILE, None)
    with guard.readonly():
        out = report(root, settings=settings, now=ctx.now(), previous=previous if isinstance(previous, Mapping) else None)
    net = out["direction_net"]["net_usd"]
    tripped = False
    k5 = out["k5"]
    # K5's writes, each only when due (the store is opened writable for nothing else): a clear the operator made since
    # the last run (`k5_clear` true while the kv is set, or the kv deleted while a trip is open), then a trip.
    clear_due = (k5.get("set") and k5.get("cleared")) or (not k5.get("set") and k5.get("trip_open"))
    line = _num(k5.get("line"))
    trip_due = (net is not None and not k5.get("set") and not k5.get("cleared")
                and net <= (line if line is not None else dlane.cfg(settings)["k5_net_usd"]))
    rearmed = None
    if clear_due or trip_due:
        store = SwarmStore(root)
        try:
            rearmed = dlane.k5_rearm(store, settings, net, at=out["at"])
            tripped = dlane.k5_trip(store, settings, net, at=out["at"])
            out["k5"] = {**dlane.k5_state(store, settings), "new": tripped}
            if rearmed is not None:
                out["k5"]["rearmed"] = rearmed
                out["direction_net"]["k5_line_usd"] = dlane.k5_line(store, settings)
        finally:
            store.close()
        if rearmed is not None:
            out["alarms"] = [a for a in out["alarms"] if a["id"] != "K5"]
            if out["k5"].get("cleared"):
                out["alarms"].append({"id": "K5", "level": "warning", "new": False, "disarmed": True,
                                      "text": "K5 is disarmed: dlane.k5_clear is true in swarm.json, so no loss trips "
                                              f"it; the clear is recorded (the next line is ${out['k5']['line']:,.2f}): "
                                              "take dlane.k5_clear out"})
            else:
                out["alarms"].append({"id": "K5", "level": "info", "new": True, "rearmed": True,
                                      "text": f"K5 cleared ({rearmed['cleared']['how']}) and re-armed: its next line is "
                                              f"${out['k5']['line']:,.2f}, "
                                              f"${abs(dlane.cfg(settings)['k5_net_usd']):,.0f} below the lane's net at "
                                              "clearing"})
        if tripped and not any(a["id"] == "K5" for a in out["alarms"]):
            out["alarms"].append({"id": "K5", "level": "warning", "new": True,
                                  "text": "K5 tripped: the direction lane's realized net over every route is at or below "
                                          "its line; the lane reads shadow (no new direction Candidate, no incubator "
                                          "direction mark) until the operator clears it (swarm.json dlane.k5_clear, or "
                                          "the kv dlane_k5)"})
    write_json(root / FILE, out)
    for alarm in out["alarms"]:
        ctx.alert(alarm["level"], f"dlane: {alarm['text']}")
    if out["done"]["other_routes"]:
        ctx.alert("warning", f"dlane: {len(out['done']['other_routes'])} agent real closes on a route the Done rule does not "
                             "name: listed apart in the report, never counted or dropped silently")
    return {"ok": True, "path": str(root / FILE), "closes_all": len(out["done"]["all"]["closes"]),
            "closes_screen": len(out["done"]["screen"]["closes"]), "alarms": [a["id"] for a in out["alarms"]],
            "k5_tripped": bool(out["k5"].get("tripped")), "k5_new": tripped, "k5_rearmed": rearmed is not None}


__all__ = ["run", "report", "FILE", "CONTAMINATION", "LOOSENED", "TIGHTENED", "closes", "meter", "reading", "replay_gap",
           "buy_and_hold", "entry_delta", "funnel", "probes", "probe_envelope", "alarms", "fee_corrections", "read_book",
           "version_of", "inception", "Lanes", "ZERO_EDGE_LABEL", "trade_screens", "ALPHA_FP"]
